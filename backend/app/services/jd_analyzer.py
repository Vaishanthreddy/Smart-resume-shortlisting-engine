"""Job description analysis.

Everything here is deterministic and rule-based: section headings, indicator
phrases, the shared skill taxonomy and a small set of regular expressions. No
language model is involved, so the same JD always produces the same analysis and
nothing is hard-coded for any particular job.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import DEGREE_LEVEL_ALIASES, DEGREE_LEVELS
from app.services.keyword_matcher import (
    KeywordMatch,
    SkillTaxonomy,
    dedupe_preserving_order,
    get_taxonomy,
)
from app.services.text_cleaner import split_sentences

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Indicator vocabulary
# --------------------------------------------------------------------------- #
REQUIRED_INDICATORS: tuple[str, ...] = (
    "required", "requirement", "mandatory", "must have", "must-have", "must possess",
    "minimum", "at least", "proficient in", "proficiency in", "strong knowledge of",
    "strong understanding of", "demonstrated experience with", "demonstrated ability",
    "solid understanding of", "hands-on experience with", "hands on experience with",
    "expertise in", "essential", "you must", "is a must", "working knowledge of",
)

PREFERRED_INDICATORS: tuple[str, ...] = (
    "preferred", "preferably", "bonus", "a plus", "plus point", "nice to have",
    "nice-to-have", "good to have", "advantage", "advantageous", "desirable",
    "familiarity with", "exposure to", "would be great", "ideally", "optional",
    "beneficial", "sets you apart", "willingness to learn",
)

ACTION_VERBS: frozenset[str] = frozenset(
    """develop developing design designing build building maintain maintaining
    implement implementing manage managing lead leading collaborate collaborating
    work working support supporting create creating deliver delivering analyze
    analyse analysing analyzing test testing deploy deploying monitor monitoring
    optimize optimise optimizing write writing review reviewing coordinate
    coordinating communicate troubleshoot document documenting participate
    contribute ensure ensuring drive driving own partner translate perform
    conduct prepare assist integrate integrating automate automating research
    researching present presenting mentor evaluate configure administer migrate
    debug refactor scale investigate liaise""".split()
)

JD_SECTION_ALIASES: dict[str, list[str]] = {
    "responsibilities": [
        "responsibilities", "key responsibilities", "core responsibilities",
        "duties", "role responsibilities", "job responsibilities", "the role",
        "your role", "about the role", "what you'll do", "what you will do",
        "day to day", "day-to-day", "scope of work", "job description",
        "role overview", "position summary", "what you'll be doing",
    ],
    "required": [
        "requirements", "required skills", "required qualifications",
        "must have", "must haves", "must-have", "minimum qualifications",
        "minimum requirements", "essential skills", "essential criteria",
        "mandatory requirements", "technical requirements", "qualifications",
        "skills and experience", "basic qualifications", "what you'll need",
        "what you will need", "what we're looking for", "what we are looking for",
        "candidate requirements", "skills required", "technical skills",
        "key requirements", "eligibility",
    ],
    "preferred": [
        "preferred", "preferred skills", "preferred qualifications",
        "nice to have", "nice to haves", "nice-to-have", "good to have",
        "bonus points", "desirable", "desirable skills", "added advantage",
        "plus points", "what will set you apart", "optional skills",
    ],
    "education": ["education", "educational requirements", "academic requirements", "education requirements"],
    "certifications": ["certifications", "certification requirements", "licenses", "licences", "certificates"],
    "soft_skills": ["soft skills", "personal attributes", "competencies", "behavioural skills", "behavioral skills"],
    "ignore": [
        "benefits", "perks", "perks and benefits", "about us", "about the company",
        "company overview", "who we are", "why join us", "compensation", "salary",
        "equal opportunity", "how to apply", "application process", "our culture",
        "what we offer", "diversity", "eeo statement", "disclaimer", "location",
    ],
}

_JD_ALIAS_TO_SECTION: dict[str, str] = {
    alias: section for section, aliases in JD_SECTION_ALIASES.items() for alias in aliases
}

_TITLE_LABEL_RE = re.compile(
    r"^\s*(job\s*title|position|role|designation|job\s*role|title)\s*[:\-–]\s*(.+)$",
    re.IGNORECASE,
)
_METADATA_LABEL_RE = re.compile(
    r"^\s*(location|department|reports\s*to|employment\s*type|job\s*type|salary|"
    r"posted|req(uisition)?\s*id|company|contract\s*type|work\s*mode|shift)\s*[:\-–]",
    re.IGNORECASE,
)
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?\+?\s*years?", re.IGNORECASE
)
_FIELD_RE = re.compile(
    r"\b(?:in|of)\s+([A-Za-z][A-Za-z\s&/,\-]{2,70})", re.IGNORECASE
)
_FIELD_STOP_RE = re.compile(
    r"\s+(?:or|with|and\s+at\s+least|from|is|are|required|preferred|equivalent)\b.*$",
    re.IGNORECASE,
)
_CERT_CONTEXT_RE = re.compile(r"certif|licen[sc]e|accredit", re.IGNORECASE)
_LIST_SPLIT_RE = re.compile(r"[,;]|\s+/\s+|\s+\|\s+|\band\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class RequirementStatement:
    """A single matchable requirement sentence taken from the JD."""

    text: str
    requirement_type: str  # required | preferred | responsibility
    importance: float
    confidence: float
    source_section: str
    source_sentence: str
    is_skill_list: bool = False


@dataclass
class EducationRequirement:
    level: str
    level_rank: int
    field_of_study: str
    source_sentence: str

    @property
    def label(self) -> str:
        if self.field_of_study:
            return f"{self.level.title()}'s degree in {self.field_of_study}"
        return f"{self.level.title()} degree"


@dataclass
class CertificationRequirement:
    name: str
    source_sentence: str
    is_canonical: bool = True


@dataclass
class ExperienceExpectation:
    min_years: float | None = None
    max_years: float | None = None
    source_sentence: str = ""

    @property
    def label(self) -> str:
        if self.min_years is None:
            return ""
        if self.max_years and self.max_years != self.min_years:
            return f"{self.min_years:g}-{self.max_years:g} years"
        return f"{self.min_years:g}+ years"


@dataclass
class JobRequirements:
    title: str = ""
    raw_text: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    other_keywords: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    required_qualifications: list[str] = field(default_factory=list)
    preferred_qualifications: list[str] = field(default_factory=list)
    education_requirements: list[EducationRequirement] = field(default_factory=list)
    certification_requirements: list[CertificationRequirement] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    experience_expectation: ExperienceExpectation = field(default_factory=ExperienceExpectation)
    requirements: list[RequirementStatement] = field(default_factory=list)
    skill_sources: dict[str, str] = field(default_factory=dict)
    analysis_notes: list[str] = field(default_factory=list)
    confidence_by_skill: dict[str, float] = field(default_factory=dict)

    @property
    def semantic_requirements(self) -> list[RequirementStatement]:
        """Requirement statements suitable for meaning-based comparison.

        Lines that are nothing more than an enumeration of tools are excluded:
        those are already fully handled by the keyword components, and counting
        them again here would double-count the same evidence.
        """
        usable = [r for r in self.requirements if not r.is_skill_list]
        return usable or self.requirements

    @property
    def all_keywords(self) -> list[str]:
        return dedupe_preserving_order(
            self.required_skills + self.preferred_skills + self.other_keywords
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _detect_heading(line: str) -> str | None:
    raw = line.strip()
    if not raw or len(raw.split()) > 8:
        return None
    normalised = re.sub(r"[^a-z\s'&-]", " ", raw.lower())
    normalised = re.sub(r"\s+", " ", normalised).strip()
    if not normalised:
        return None
    if normalised in _JD_ALIAS_TO_SECTION:
        return _JD_ALIAS_TO_SECTION[normalised]
    trimmed = re.split(r"[&(/|]", normalised)[0].strip()
    if trimmed in _JD_ALIAS_TO_SECTION:
        return _JD_ALIAS_TO_SECTION[trimmed]
    return None


def _contains_indicator(text: str, indicators: tuple[str, ...]) -> str | None:
    lowered = f" {text.lower()} "
    for indicator in indicators:
        if indicator in lowered:
            return indicator
    return None


def _starts_with_action_verb(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text.lower())
    return bool(words) and words[0] in ACTION_VERBS


def _classify(line: str, section: str | None) -> tuple[str, float, str]:
    """Return (requirement_type, confidence, reason) for a JD line."""
    preferred_hit = _contains_indicator(line, PREFERRED_INDICATORS)
    if preferred_hit:
        return "preferred", 0.95, f"indicator: {preferred_hit}"

    required_hit = _contains_indicator(line, REQUIRED_INDICATORS)
    if required_hit:
        return "required", 0.95, f"indicator: {required_hit}"

    if section == "preferred":
        return "preferred", 0.80, "preferred section"
    if section in {"required", "education", "certifications", "soft_skills"}:
        return "required", 0.80, f"{section} section"
    if section == "responsibilities":
        return "responsibility", 0.80, "responsibilities section"

    if _starts_with_action_verb(line):
        return "responsibility", 0.60, "leading action verb"
    return "responsibility", 0.50, "unlabelled statement"


def _is_skill_list(line: str, matches: dict[str, KeywordMatch]) -> bool:
    """True when a line is essentially an enumeration of tools."""
    if len(matches) < 2:
        return False
    words = re.findall(r"[A-Za-z]+", line.lower())
    if not words:
        return False
    verb_count = sum(1 for word in words if word in ACTION_VERBS)
    separators = line.count(",") + line.count("/") + line.count("|")
    matched_chars = sum(len(name) for name in matches)
    density = matched_chars / max(len(line), 1)
    return (separators >= len(matches) - 1 and verb_count == 0) or density > 0.45


def _extract_title(text: str, lines: list[str]) -> str:
    for line in lines[:25]:
        label = _TITLE_LABEL_RE.match(line)
        if label:
            title = label.group(2).strip()
            if title:
                return re.split(r"\s{2,}|\s\|\s", title)[0].strip(" .-–")
    for line in lines[:6]:
        candidate = line.strip(" .-–:")
        if not candidate or _detect_heading(candidate):
            continue
        words = candidate.split()
        if 1 < len(words) <= 10 and not candidate.endswith((".", "!", "?")):
            if re.search(r"[A-Za-z]", candidate):
                return candidate
    return "Untitled role"


def _extract_experience(lines: list[str]) -> ExperienceExpectation:
    best = ExperienceExpectation()
    for line in lines:
        if "experien" not in line.lower():
            continue
        match = _YEARS_RE.search(line)
        if not match:
            continue
        low = float(match.group(1))
        high = float(match.group(2)) if match.group(2) else None
        if best.min_years is None or low < best.min_years:
            best = ExperienceExpectation(
                min_years=low, max_years=high, source_sentence=line.strip()
            )
    return best


def _clean_field(raw: str) -> str:
    field_text = _FIELD_STOP_RE.sub("", raw).strip(" ,./-")
    field_text = re.sub(r"\s+", " ", field_text)
    # Drop a trailing "field"/"discipline" noun that adds nothing.
    field_text = re.sub(
        r"\b(related\s+)?(field|discipline|subject|area)s?\b", "", field_text, flags=re.I
    ).strip(" ,-")
    return field_text


def _extract_education(lines: list[str]) -> list[EducationRequirement]:
    requirements: list[EducationRequirement] = []
    seen: set[tuple[str, str]] = set()

    for line in lines:
        lowered = line.lower()
        if not re.search(r"degree|bachelor|master|phd|diploma|b\.?tech|m\.?tech|mba|graduat", lowered):
            continue
        for level, aliases in DEGREE_LEVEL_ALIASES.items():
            hit_position = -1
            for alias in aliases:
                position = lowered.find(alias.lower())
                if position != -1:
                    hit_position = position if hit_position == -1 else min(hit_position, position)
            if hit_position == -1:
                continue
            field_match = _FIELD_RE.search(line, hit_position)
            field_of_study = _clean_field(field_match.group(1)) if field_match else ""
            key = (level, field_of_study.lower())
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                EducationRequirement(
                    level=level,
                    level_rank=DEGREE_LEVELS.get(level, 0),
                    field_of_study=field_of_study,
                    source_sentence=line.strip(),
                )
            )

    # "Bachelor's or Master's in X" — keep the lowest acceptable bar only.
    if len(requirements) > 1:
        fields = {r.field_of_study.lower() for r in requirements}
        if len(fields) == 1:
            requirements = [min(requirements, key=lambda r: r.level_rank)]
    return requirements


def _extract_certifications(
    lines: list[str], taxonomy: SkillTaxonomy
) -> list[CertificationRequirement]:
    requirements: list[CertificationRequirement] = []
    seen: set[str] = set()

    for line in lines:
        if not _CERT_CONTEXT_RE.search(line):
            continue
        canonical_hits = taxonomy.find_certifications(line)
        for name, match in canonical_hits.items():
            if name in seen:
                continue
            seen.add(name)
            requirements.append(
                CertificationRequirement(name=name, source_sentence=line.strip())
            )
        if canonical_hits:
            continue
        # Non-canonical wording, e.g. "AWS certification preferred".
        for fragment in _LIST_SPLIT_RE.split(line):
            fragment = fragment.strip(" .-–:")
            if not fragment or not _CERT_CONTEXT_RE.search(fragment):
                continue
            if len(fragment.split()) > 10:
                continue
            key = fragment.lower()
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                CertificationRequirement(
                    name=fragment, source_sentence=line.strip(), is_canonical=False
                )
            )
    return requirements


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def analyze_job_description(text: str, taxonomy: SkillTaxonomy | None = None) -> JobRequirements:
    """Turn raw JD text into a structured, matchable requirement set."""
    taxonomy = taxonomy or get_taxonomy()
    job = JobRequirements(raw_text=text)

    raw_lines = [line.strip() for line in text.split("\n")]
    non_empty = [line for line in raw_lines if line]
    job.title = _extract_title(text, non_empty)

    current_section: str | None = None
    scoped_lines: list[tuple[str, str | None]] = []  # (line, section)

    for line in raw_lines:
        if not line:
            continue
        # Metadata labels describe the posting, not a requirement to match.
        if _TITLE_LABEL_RE.match(line) or _METADATA_LABEL_RE.match(line):
            continue
        heading = _detect_heading(line)
        if heading:
            current_section = heading
            continue
        # A trailing colon introduces a section even when it is not a known alias.
        if line.endswith(":") and len(line.split()) <= 8:
            inline = _detect_heading(line.rstrip(":"))
            if inline:
                current_section = inline
                continue
        scoped_lines.append((line, current_section))

    considered = [(line, section) for line, section in scoped_lines if section != "ignore"]
    if not considered:  # a JD made entirely of ignorable sections still gets analysed
        considered = scoped_lines

    required_skill_names: list[str] = []
    preferred_skill_names: list[str] = []
    other_skill_names: list[str] = []
    soft_skill_names: list[str] = []

    for line, section in considered:
        for sentence in split_sentences(line) or [line]:
            requirement_type, confidence, reason = _classify(sentence, section)
            matches = taxonomy.find_skills(sentence, use_fuzzy=False)
            skill_list_line = _is_skill_list(sentence, matches)

            statement = RequirementStatement(
                text=sentence,
                requirement_type=requirement_type,
                importance=confidence,
                confidence=confidence,
                source_section=section or "unlabelled",
                source_sentence=line,
                is_skill_list=skill_list_line,
            )
            job.requirements.append(statement)

            for name in matches:
                if requirement_type == "required":
                    required_skill_names.append(name)
                elif requirement_type == "preferred":
                    preferred_skill_names.append(name)
                else:
                    other_skill_names.append(name)
                job.skill_sources.setdefault(name, sentence)
                job.confidence_by_skill[name] = max(
                    job.confidence_by_skill.get(name, 0.0), confidence
                )

            for soft_name in taxonomy.find_soft_skills(sentence):
                soft_skill_names.append(soft_name)

            if requirement_type == "responsibility":
                job.responsibilities.append(sentence)
            elif requirement_type == "required":
                job.required_qualifications.append(sentence)
            else:
                job.preferred_qualifications.append(sentence)

        logger.debug("Classified JD line in section %s: %s", section, reason)

    required_set = set(required_skill_names)

    # Fallback: a JD that never uses an explicit "required" cue still has
    # mandatory technology. Promote skills stated in responsibilities so the
    # required-skill component is not silently switched off.
    if not required_set:
        promoted = dedupe_preserving_order(other_skill_names)
        if promoted:
            required_skill_names = promoted
            required_set = set(promoted)
            other_skill_names = []
            job.analysis_notes.append(
                "No explicit 'required' wording was found; skills stated in the role "
                "description were treated as required with reduced confidence."
            )
            for name in promoted:
                job.confidence_by_skill[name] = min(
                    job.confidence_by_skill.get(name, 0.5), 0.5
                )

    job.required_skills = dedupe_preserving_order(required_skill_names)

    # Deduplicate across categories: a skill counted as required is never
    # counted again as a preferred or other keyword.
    job.preferred_skills = [
        name for name in dedupe_preserving_order(preferred_skill_names)
        if name not in required_set
    ]
    preferred_set = set(job.preferred_skills)
    job.other_keywords = [
        name for name in dedupe_preserving_order(preferred_skill_names + other_skill_names)
        if name not in required_set and name not in preferred_set
    ]
    job.other_keywords = dedupe_preserving_order(job.preferred_skills + job.other_keywords)

    job.soft_skills = dedupe_preserving_order(soft_skill_names)
    job.responsibilities = dedupe_preserving_order(job.responsibilities)
    job.required_qualifications = dedupe_preserving_order(job.required_qualifications)
    job.preferred_qualifications = dedupe_preserving_order(job.preferred_qualifications)
    job.education_requirements = _extract_education([line for line, _ in considered])
    job.certification_requirements = _extract_certifications(
        [line for line, _ in considered], taxonomy
    )
    job.experience_expectation = _extract_experience([line for line, _ in considered])

    logger.info(
        "JD analysed: title=%r required=%d other=%d responsibilities=%d requirements=%d",
        job.title,
        len(job.required_skills),
        len(job.other_keywords),
        len(job.responsibilities),
        len(job.requirements),
    )
    return job
