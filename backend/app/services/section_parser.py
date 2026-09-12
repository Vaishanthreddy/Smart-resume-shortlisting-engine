"""Resume section detection.

Headings vary wildly between resumes, so detection is alias-driven and always
falls back to the full document. A resume with no recognisable headings is
still fully scoreable — formatting must never cost a candidate points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.text_cleaner import split_sentences

# Canonical section -> heading aliases.
SECTION_ALIASES: dict[str, list[str]] = {
    "summary": [
        "summary", "professional summary", "career summary", "profile",
        "professional profile", "about me", "objective", "career objective",
        "personal statement", "overview",
    ],
    "skills": [
        "skills", "technical skills", "key skills", "core skills", "core competencies",
        "competencies", "skill set", "skills summary", "technical expertise",
        "technologies", "tech stack", "tools and technologies", "areas of expertise",
        "technical proficiencies", "expertise",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "career history", "industry experience",
        "relevant experience", "internship", "internships", "internship experience",
        "professional background",
    ],
    "projects": [
        "projects", "academic projects", "personal projects", "key projects",
        "project experience", "selected projects", "project work", "major projects",
        "capstone project", "portfolio",
    ],
    "education": [
        "education", "academic background", "academic qualifications", "qualifications",
        "educational qualifications", "academics", "education and training",
        "academic details",
    ],
    "certifications": [
        "certifications", "certification", "certificates", "licenses",
        "licences", "licenses and certifications", "courses and certifications",
        "professional certifications", "credentials", "training and certifications",
    ],
    "achievements": [
        "achievements", "accomplishments", "awards", "honors", "honours",
        "awards and achievements", "recognition", "publications", "extracurricular",
        "activities", "volunteering", "leadership",
    ],
}

# Sections whose content is practical, demonstrated work.
PRACTICAL_SECTIONS: tuple[str, ...] = ("experience", "projects", "achievements")

_HEADING_CLEAN_RE = re.compile(r"^[^a-zA-Z]*|[^a-zA-Z)]*$")
_MAX_HEADING_WORDS = 6

_ALIAS_TO_SECTION: dict[str, str] = {
    alias: section
    for section, aliases in SECTION_ALIASES.items()
    for alias in aliases
}

# Lines that look like contact details rather than a name.
_CONTACT_RE = re.compile(
    r"(@|https?://|www\.|linkedin|github|\+?\d[\d\s\-()]{6,})", re.IGNORECASE
)


@dataclass
class ResumeSections:
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)
    detected_headings: list[str] = field(default_factory=list)

    def get(self, name: str) -> str:
        return self.sections.get(name, "")

    def has(self, name: str) -> bool:
        return bool(self.sections.get(name, "").strip())

    def text_for(self, *names: str, fallback_to_full: bool = True) -> str:
        """Concatenated text for the named sections, falling back to full text."""
        parts = [self.sections[name] for name in names if self.sections.get(name)]
        if parts:
            return "\n".join(parts)
        return self.full_text if fallback_to_full else ""

    @property
    def practical_text(self) -> str:
        """Projects + experience + achievements, or full text when absent."""
        return self.text_for(*PRACTICAL_SECTIONS)

    @property
    def uses_fallback_for_practical(self) -> bool:
        return not any(self.has(name) for name in PRACTICAL_SECTIONS)


def _normalise_heading(line: str) -> str:
    cleaned = _HEADING_CLEAN_RE.sub("", line).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _match_heading(line: str) -> str | None:
    """Return the canonical section name if this line is a section heading."""
    raw = line.strip()
    if not raw or len(raw.split()) > _MAX_HEADING_WORDS:
        return None

    # A heading line rarely ends in a sentence terminator or contains a comma list.
    if raw.endswith((".", ",")) or raw.count(",") >= 2:
        return None

    normalised = _normalise_heading(raw)
    if not normalised:
        return None

    if normalised in _ALIAS_TO_SECTION:
        return _ALIAS_TO_SECTION[normalised]

    # "Technical Skills & Tools" / "Work Experience (3 years)"
    trimmed = re.split(r"[&(/|:]", normalised)[0].strip()
    if trimmed in _ALIAS_TO_SECTION:
        return _ALIAS_TO_SECTION[trimmed]

    return None


def parse_sections(text: str) -> ResumeSections:
    """Split a resume into canonical sections."""
    result = ResumeSections(full_text=text)
    if not text.strip():
        return result

    buckets: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.split("\n"):
        heading = _match_heading(line)
        if heading:
            current = heading
            result.detected_headings.append(line.strip())
            buckets.setdefault(heading, [])
            continue
        if current:
            buckets[current].append(line)

    result.sections = {
        name: "\n".join(lines).strip()
        for name, lines in buckets.items()
        if "\n".join(lines).strip()
    }
    return result


def extract_candidate_name(text: str, filename: str) -> str:
    """Best-effort display name for the UI.

    The name is presentation metadata only. It is never passed to any scoring
    function and never influences ranking.
    """
    for line in text.split("\n")[:8]:
        candidate = line.strip()
        if not candidate or _CONTACT_RE.search(candidate):
            continue
        words = candidate.split()
        if not 1 < len(words) <= 5:
            continue
        if _match_heading(candidate):
            continue
        letters = re.sub(r"[^A-Za-z\s.'-]", "", candidate)
        if len(letters) < len(candidate) * 0.8:
            continue
        if all(word[0].isupper() for word in words if word[:1].isalpha()):
            return " ".join(words)

    stem = filename.rsplit(".", 1)[0]
    cleaned = re.sub(r"[_\-]+", " ", stem)
    cleaned = re.sub(r"\b(resume|cv|profile|final|updated)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else stem


def section_sentences(sections: ResumeSections, *names: str) -> list[str]:
    return split_sentences(sections.text_for(*names))
