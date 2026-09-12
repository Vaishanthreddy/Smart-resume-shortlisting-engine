"""Component scoring, dynamic weight redistribution and the final score.

Each of the seven components is computed independently on a 0-100 scale from
explicit evidence, then combined with the effective weights for the job. The
components are defined so that no piece of evidence is counted twice:

* required skills  — explicit mandatory skills only
* other keywords   — preferred / domain terms, with required skills removed
* semantic match   — requirement *statements*, with pure skill lists removed
* project & experience — the same statements matched against practical sections
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import (
    ALWAYS_ACTIVE_COMPONENTS,
    BASE_WEIGHTS,
    C_CERTIFICATIONS,
    C_EDUCATION,
    C_OTHER_KEYWORDS,
    C_PROJECT_EXPERIENCE,
    C_REQUIRED_SKILLS,
    C_SEMANTIC,
    C_SOFT_SKILLS,
    CERTIFICATION_FUZZY_CUTOFF,
    COMPONENT_ORDER,
    DEGREE_LEVEL_ALIASES,
    DEGREE_LEVELS,
    EDUCATION_FIELD_SIM_THRESHOLD,
    EDUCATION_FIELD_WEIGHT,
    EDUCATION_LEVEL_WEIGHT,
    EDUCATION_ONE_LEVEL_BELOW_CREDIT,
    EVIDENCE_SNIPPET_MAX_CHARS,
    MANDATORY_CONFIDENCE_THRESHOLD,
    MANDATORY_SKILL_PENALTY_CAP,
    MANDATORY_SKILL_PENALTY_ENABLED,
    MANDATORY_SKILL_PENALTY_PER_SKILL,
    MAX_PROJECT_EVIDENCE_ITEMS,
    PROJECT_RESPONSIBILITY_WEIGHT,
    PROJECT_SKILL_EVIDENCE_WEIGHT,
    REPORT_WHOLE_DOCUMENT_SIMILARITY,
    SOFT_SKILL_CUE_CREDIT,
    SOFT_SKILL_MIN_EVIDENCE_WORDS,
    SOFT_SKILL_SEMANTIC_CREDIT,
    SOFT_SKILL_SIM_THRESHOLD,
    WEIGHT_SUM_TOLERANCE,
    clamp_score,
)
from app.services.jd_analyzer import JobRequirements
from app.services.keyword_matcher import SkillTaxonomy
from app.services.section_parser import ResumeSections
from app.services.semantic_matcher import (
    RequirementEvidence,
    SemanticEngine,
    SemanticResult,
    match_requirements,
)
from app.services.text_cleaner import chunk_text, snippet, split_sentences

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result structures
# --------------------------------------------------------------------------- #
@dataclass
class MatchedItem:
    name: str
    evidence: str = ""
    match_method: str = "exact"
    confidence: float = 1.0
    found_in: str = ""


@dataclass
class Penalty:
    reason: str
    points: float
    detail: str = ""


@dataclass
class ScoringPlan:
    """Which components apply to this JD, and the weights every candidate gets."""

    base_weights: dict[str, float]
    effective_weights: dict[str, float]
    active_components: list[str]
    inactive_components: list[str]
    activation_reasons: dict[str, str]


@dataclass
class CandidateScores:
    component_scores: dict[str, float] = field(default_factory=dict)
    matched_required_skills: list[MatchedItem] = field(default_factory=list)
    matched_other_keywords: list[MatchedItem] = field(default_factory=list)
    required_skills_not_found: list[str] = field(default_factory=list)
    other_keywords_not_found: list[str] = field(default_factory=list)
    semantic_evidence: list[RequirementEvidence] = field(default_factory=list)
    project_experience_evidence: list[RequirementEvidence] = field(default_factory=list)
    education_evidence: list[MatchedItem] = field(default_factory=list)
    certification_evidence: list[MatchedItem] = field(default_factory=list)
    soft_skill_evidence: list[MatchedItem] = field(default_factory=list)
    education_not_found: list[str] = field(default_factory=list)
    certifications_not_found: list[str] = field(default_factory=list)
    soft_skills_not_found: list[str] = field(default_factory=list)
    penalties: list[Penalty] = field(default_factory=list)
    weighted_contributions: dict[str, float] = field(default_factory=dict)
    final_score: float = 0.0
    whole_document_similarity: float | None = None
    used_section_fallback: bool = False


@dataclass
class ParsedResume:
    """Everything the scorer needs about one resume."""

    candidate_id: str
    filename: str
    candidate_name: str
    text: str
    sections: ResumeSections
    chunks: list[str] = field(default_factory=list)
    practical_chunks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Dynamic weight redistribution
# --------------------------------------------------------------------------- #
def determine_active_components(job: JobRequirements) -> tuple[list[str], dict[str, str]]:
    """Decide which components the JD actually asks for."""
    reasons: dict[str, str] = {}
    active: list[str] = []

    checks: list[tuple[str, bool, str, str]] = [
        (
            C_REQUIRED_SKILLS,
            bool(job.required_skills),
            f"{len(job.required_skills)} required skills extracted from the JD",
            "The JD states no explicit required skills",
        ),
        (
            C_SEMANTIC,
            True,
            f"{len(job.semantic_requirements)} matchable requirement statements",
            "",
        ),
        (
            C_OTHER_KEYWORDS,
            bool(job.other_keywords),
            f"{len(job.other_keywords)} preferred or domain keywords",
            "The JD lists no preferred or domain keywords beyond the required skills",
        ),
        (
            C_PROJECT_EXPERIENCE,
            bool(job.responsibilities)
            or job.experience_expectation.min_years is not None
            or any(not r.is_skill_list for r in job.requirements),
            "The JD describes responsibilities or experience expectations",
            "The JD describes no responsibilities or experience expectations",
        ),
        (
            C_EDUCATION,
            bool(job.education_requirements),
            f"{len(job.education_requirements)} education requirement(s) stated",
            "The JD states no education requirement",
        ),
        (
            C_CERTIFICATIONS,
            bool(job.certification_requirements),
            f"{len(job.certification_requirements)} certification requirement(s) stated",
            "The JD states no certification requirement",
        ),
        (
            C_SOFT_SKILLS,
            bool(job.soft_skills),
            f"{len(job.soft_skills)} soft skill(s) requested",
            "The JD requests no specific soft skills",
        ),
    ]

    for component, is_active, active_reason, inactive_reason in checks:
        if is_active or component in ALWAYS_ACTIVE_COMPONENTS:
            active.append(component)
            reasons[component] = active_reason
        else:
            reasons[component] = inactive_reason

    return active, reasons


def redistribute_weights(
    active: list[str], base_weights: dict[str, float] | None = None
) -> dict[str, float]:
    """Spread the weight of inactive components across the active ones.

    Redistribution is proportional to each active component's base weight, so
    their relative importance is preserved and the active weights sum to 1.0.
    """
    base = dict(base_weights or BASE_WEIGHTS)
    active_set = [c for c in COMPONENT_ORDER if c in set(active)]
    if not active_set:
        raise ValueError("At least one scoring component must be active.")

    active_total = sum(base[component] for component in active_set)
    if active_total <= 0:
        share = 1.0 / len(active_set)
        return {component: share for component in active_set}

    effective = {
        component: base[component] / active_total for component in active_set
    }

    # Guard against float drift so the weights provably total 1.0.
    drift = 1.0 - sum(effective.values())
    if abs(drift) > WEIGHT_SUM_TOLERANCE:
        largest = max(effective, key=lambda key: effective[key])
        effective[largest] += drift
    return effective


def build_scoring_plan(job: JobRequirements) -> ScoringPlan:
    """One plan per JD, applied identically to every candidate."""
    active, reasons = determine_active_components(job)
    effective = redistribute_weights(active)
    inactive = [c for c in COMPONENT_ORDER if c not in effective]

    logger.info(
        "Scoring plan: active=%s effective=%s",
        active,
        {k: round(v, 4) for k, v in effective.items()},
    )
    return ScoringPlan(
        base_weights=dict(BASE_WEIGHTS),
        effective_weights=effective,
        active_components=active,
        inactive_components=inactive,
        activation_reasons=reasons,
    )


# --------------------------------------------------------------------------- #
# Component calculations
# --------------------------------------------------------------------------- #
def _coverage_score(matched: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return clamp_score(matched / total * 100.0)


def score_required_skills(
    job: JobRequirements, resume: ParsedResume, taxonomy: SkillTaxonomy
) -> tuple[float, list[MatchedItem], list[str]]:
    """Explicit coverage of mandatory skills. Repetition cannot raise it."""
    if not job.required_skills:
        return 0.0, [], []

    found = taxonomy.find_skills(resume.text, restrict=job.required_skills)
    matched: list[MatchedItem] = []
    missing: list[str] = []

    for skill in job.required_skills:
        match = found.get(skill)
        if match is None:
            missing.append(skill)
            continue
        matched.append(
            MatchedItem(
                name=skill,
                evidence=match.evidence[0] if match.evidence else "",
                match_method=match.method,
                confidence=match.confidence,
                found_in=_locate_section(resume, match.evidence),
            )
        )

    # One matched skill counts once, no matter how many times it appears.
    return _coverage_score(len(matched), len(job.required_skills)), matched, missing


def score_other_keywords(
    job: JobRequirements, resume: ParsedResume, taxonomy: SkillTaxonomy
) -> tuple[float, list[MatchedItem], list[str]]:
    """Preferred skills, tools and domain terms, excluding required skills."""
    keywords = [k for k in job.other_keywords if k not in set(job.required_skills)]
    if not keywords:
        return 0.0, [], []

    found = taxonomy.find_skills(resume.text, restrict=keywords)
    matched: list[MatchedItem] = []
    missing: list[str] = []

    for keyword in keywords:
        match = found.get(keyword)
        if match is None:
            missing.append(keyword)
            continue
        matched.append(
            MatchedItem(
                name=keyword,
                evidence=match.evidence[0] if match.evidence else "",
                match_method=match.method,
                confidence=match.confidence,
                found_in=_locate_section(resume, match.evidence),
            )
        )

    return _coverage_score(len(matched), len(keywords)), matched, missing


def score_semantic(
    job: JobRequirements, resume: ParsedResume, engine: SemanticEngine
) -> SemanticResult:
    """Meaning-based alignment of JD requirement statements to resume evidence."""
    result = match_requirements(engine, job.semantic_requirements, resume.chunks)
    if REPORT_WHOLE_DOCUMENT_SIMILARITY and resume.text and job.raw_text:
        # Diagnostic only: carries no weight in the final score.
        result.whole_document_similarity = round(
            engine.similarity(job.raw_text[:5000], resume.text[:5000]), 4
        )
    return result


def score_project_experience(
    job: JobRequirements,
    resume: ParsedResume,
    engine: SemanticEngine,
    taxonomy: SkillTaxonomy,
) -> tuple[float, list[RequirementEvidence]]:
    """Practical evidence from projects *or* employment.

    Either source is sufficient: a strong academic project can carry an
    entry-level candidate, and relevant employment can carry an experienced one.
    Relevance to the JD drives the score, not project count or years.
    """
    statements = job.responsibilities or [
        r.text for r in job.semantic_requirements
    ]
    if not statements or not resume.practical_chunks:
        return 0.0, []

    result = match_requirements(
        engine, statements, resume.practical_chunks, default_importance_type="responsibility"
    )
    responsibility_score = result.score

    # Are the JD's key skills actually demonstrated in project/experience text,
    # rather than only listed in a skills block?
    target_skills = job.required_skills or job.all_keywords
    practical_text = resume.sections.practical_text
    if target_skills and practical_text:
        demonstrated = taxonomy.find_skills(
            practical_text, restrict=target_skills, use_fuzzy=False
        )
        skill_evidence_score = _coverage_score(len(demonstrated), len(target_skills))
    else:
        skill_evidence_score = 0.0

    combined = (
        PROJECT_RESPONSIBILITY_WEIGHT * responsibility_score
        + PROJECT_SKILL_EVIDENCE_WEIGHT * skill_evidence_score
    )

    top_evidence = sorted(
        [item for item in result.evidence if item.meets_threshold],
        key=lambda item: item.similarity,
        reverse=True,
    )[:MAX_PROJECT_EVIDENCE_ITEMS]

    return clamp_score(combined), top_evidence


def _resume_degree_levels(resume: ParsedResume) -> dict[str, str]:
    """Map degree level -> the line that evidences it."""
    text = resume.sections.text_for("education")
    found: dict[str, str] = {}
    for line in text.split("\n"):
        lowered = line.lower()
        for level, aliases in DEGREE_LEVEL_ALIASES.items():
            if level in found:
                continue
            for alias in aliases:
                pattern = rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])"
                if re.search(pattern, lowered):
                    found[level] = line.strip()
                    break
    return found


def score_education(
    job: JobRequirements, resume: ParsedResume, engine: SemanticEngine
) -> tuple[float, list[MatchedItem], list[str]]:
    """Only education the JD explicitly asked for is measured."""
    if not job.education_requirements:
        return 0.0, [], []

    resume_levels = _resume_degree_levels(resume)
    highest_rank = max(
        (DEGREE_LEVELS.get(level, 0) for level in resume_levels), default=0
    )
    education_text = resume.sections.text_for("education")
    education_lines = [line for line in education_text.split("\n") if line.strip()]

    matched: list[MatchedItem] = []
    missing: list[str] = []
    totals: list[float] = []

    for requirement in job.education_requirements:
        if highest_rank >= requirement.level_rank:
            level_credit = 1.0
        elif highest_rank == requirement.level_rank - 1:
            level_credit = EDUCATION_ONE_LEVEL_BELOW_CREDIT
        else:
            level_credit = 0.0

        if not requirement.field_of_study:
            credit = level_credit
            field_credit = None
        else:
            field_credit = 0.0
            best_line = ""
            if education_lines:
                matrix = engine.similarity_matrix(
                    [requirement.field_of_study], education_lines
                )
                index = int(matrix[0].argmax())
                similarity = float(matrix[0][index])
                if similarity >= EDUCATION_FIELD_SIM_THRESHOLD:
                    field_credit = 1.0
                    best_line = education_lines[index]
            # Direct token overlap is a cheap, reliable confirmation.
            field_tokens = [
                token
                for token in re.findall(r"[a-z]{4,}", requirement.field_of_study.lower())
            ]
            if field_tokens and any(
                token in education_text.lower() for token in field_tokens
            ):
                field_credit = 1.0
                best_line = best_line or next(
                    (
                        line for line in education_lines
                        if any(token in line.lower() for token in field_tokens)
                    ),
                    "",
                )
            credit = (
                EDUCATION_LEVEL_WEIGHT * level_credit
                + EDUCATION_FIELD_WEIGHT * field_credit
            )

        totals.append(credit)

        evidence_line = ""
        for level, line in resume_levels.items():
            if DEGREE_LEVELS.get(level, 0) >= requirement.level_rank:
                evidence_line = line
                break
        if not evidence_line and resume_levels:
            evidence_line = next(iter(resume_levels.values()))

        if credit > 0:
            matched.append(
                MatchedItem(
                    name=requirement.label,
                    evidence=snippet(evidence_line, EVIDENCE_SNIPPET_MAX_CHARS),
                    match_method="degree level and field of study"
                    if field_credit
                    else "degree level",
                    confidence=round(credit, 2),
                    found_in="education",
                )
            )
        else:
            missing.append(requirement.label)

    score = clamp_score(sum(totals) / len(totals) * 100.0) if totals else 0.0
    return score, matched, missing


def score_certifications(
    job: JobRequirements, resume: ParsedResume, taxonomy: SkillTaxonomy
) -> tuple[float, list[MatchedItem], list[str]]:
    """Only certifications the JD asked for are measured."""
    if not job.certification_requirements:
        return 0.0, [], []

    cert_text = resume.sections.text_for("certifications", "achievements")
    search_text = f"{cert_text}\n{resume.text}"
    canonical_found = taxonomy.find_certifications(search_text)

    matched: list[MatchedItem] = []
    missing: list[str] = []

    for requirement in job.certification_requirements:
        if requirement.is_canonical and requirement.name in canonical_found:
            match = canonical_found[requirement.name]
            matched.append(
                MatchedItem(
                    name=requirement.name,
                    evidence=match.evidence[0] if match.evidence else "",
                    match_method="certification name",
                    confidence=match.confidence,
                    found_in="certifications",
                )
            )
            continue

        evidence = _fuzzy_certification_line(requirement.name, search_text)
        if evidence:
            matched.append(
                MatchedItem(
                    name=requirement.name,
                    evidence=evidence,
                    match_method="approximate certification wording",
                    confidence=0.75,
                    found_in="certifications",
                )
            )
        else:
            missing.append(requirement.name)

    return (
        _coverage_score(len(matched), len(job.certification_requirements)),
        matched,
        missing,
    )


def _fuzzy_certification_line(requirement_name: str, text: str) -> str:
    """Match loosely worded certification requirements against resume lines."""
    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover
        return ""

    keywords = [
        token
        for token in re.findall(r"[a-z0-9+#]{3,}", requirement_name.lower())
        if token not in {"certification", "certified", "certificate", "licence", "license"}
    ]
    if not keywords:
        return ""

    for line in text.split("\n"):
        lowered = line.lower()
        if not re.search(r"certif|licen[sc]e|accredit", lowered):
            continue
        if all(keyword in lowered for keyword in keywords):
            return snippet(line, EVIDENCE_SNIPPET_MAX_CHARS)
        if fuzz.token_set_ratio(requirement_name.lower(), lowered) >= CERTIFICATION_FUZZY_CUTOFF:
            return snippet(line, EVIDENCE_SNIPPET_MAX_CHARS)
    return ""


def score_soft_skills(
    job: JobRequirements,
    resume: ParsedResume,
    engine: SemanticEngine,
    taxonomy: SkillTaxonomy,
) -> tuple[float, list[MatchedItem], list[str]]:
    """Soft skills score only when a behavioural sentence supports them.

    Listing "teamwork" in a skills block earns nothing; describing collaboration
    inside real work does.
    """
    if not job.soft_skills:
        return 0.0, [], []

    behavioural_text = resume.sections.text_for(
        "experience", "projects", "achievements", "summary"
    )
    sentences = [
        sentence
        for sentence in split_sentences(behavioural_text)
        if len(sentence.split()) >= SOFT_SKILL_MIN_EVIDENCE_WORDS
    ]

    matched: list[MatchedItem] = []
    missing: list[str] = []
    credits: list[float] = []

    for skill in job.soft_skills:
        definition = taxonomy.soft_skills.get(skill)
        if definition is None:
            missing.append(skill)
            credits.append(0.0)
            continue

        cue_sentence = ""
        for sentence in sentences:
            lowered = sentence.lower()
            if any(cue in lowered for cue in definition.evidence_cues):
                cue_sentence = sentence
                break

        if cue_sentence:
            credits.append(SOFT_SKILL_CUE_CREDIT)
            matched.append(
                MatchedItem(
                    name=skill,
                    evidence=snippet(cue_sentence, EVIDENCE_SNIPPET_MAX_CHARS),
                    match_method="behavioural evidence",
                    confidence=SOFT_SKILL_CUE_CREDIT,
                    found_in="experience or projects",
                )
            )
            continue

        best_sentence, similarity = "", 0.0
        if sentences:
            matrix = engine.similarity_matrix([definition.descriptor], sentences)
            index = int(matrix[0].argmax())
            similarity = float(matrix[0][index])
            best_sentence = sentences[index]

        if similarity >= SOFT_SKILL_SIM_THRESHOLD and best_sentence:
            credits.append(SOFT_SKILL_SEMANTIC_CREDIT)
            matched.append(
                MatchedItem(
                    name=skill,
                    evidence=snippet(best_sentence, EVIDENCE_SNIPPET_MAX_CHARS),
                    match_method="contextual similarity",
                    confidence=round(SOFT_SKILL_SEMANTIC_CREDIT, 2),
                    found_in="experience or projects",
                )
            )
        else:
            credits.append(0.0)
            missing.append(skill)

    score = clamp_score(sum(credits) / len(credits) * 100.0) if credits else 0.0
    return score, matched, missing


def _locate_section(resume: ParsedResume, evidence: list[str]) -> str:
    """Name the section an evidence snippet came from, for transparency."""
    if not evidence:
        return ""
    needle = evidence[0][:60].lower()
    for name, content in resume.sections.sections.items():
        if needle and needle in content.lower():
            return name
    return "document"


# --------------------------------------------------------------------------- #
# Penalties and assembly
# --------------------------------------------------------------------------- #
def compute_penalties(job: JobRequirements, missing_required: list[str]) -> list[Penalty]:
    """Transparent, configurable penalty for explicitly mandatory skills."""
    if not MANDATORY_SKILL_PENALTY_ENABLED or not missing_required:
        return []

    mandatory_missing = [
        skill
        for skill in missing_required
        if job.confidence_by_skill.get(skill, 0.0) >= MANDATORY_CONFIDENCE_THRESHOLD
    ]
    if not mandatory_missing:
        return []

    points = min(
        len(mandatory_missing) * MANDATORY_SKILL_PENALTY_PER_SKILL,
        MANDATORY_SKILL_PENALTY_CAP,
    )
    listed = ", ".join(mandatory_missing)
    return [
        Penalty(
            reason="Skills the JD marks as mandatory were not found in the resume",
            points=round(points, 2),
            detail=(
                f"No evidence of {listed} was found in the submitted resume. "
                f"{MANDATORY_SKILL_PENALTY_PER_SKILL:g} points are deducted per "
                f"mandatory skill, capped at {MANDATORY_SKILL_PENALTY_CAP:g}."
            ),
        )
    ]


def score_candidate(
    job: JobRequirements,
    plan: ScoringPlan,
    resume: ParsedResume,
    engine: SemanticEngine,
    taxonomy: SkillTaxonomy,
) -> CandidateScores:
    """Run every active component for one candidate and combine them."""
    scores = CandidateScores()
    scores.used_section_fallback = resume.sections.uses_fallback_for_practical

    required_score, required_matches, required_missing = score_required_skills(
        job, resume, taxonomy
    )
    scores.matched_required_skills = required_matches
    scores.required_skills_not_found = required_missing

    other_score, other_matches, other_missing = score_other_keywords(job, resume, taxonomy)
    scores.matched_other_keywords = other_matches
    scores.other_keywords_not_found = other_missing

    semantic_result = score_semantic(job, resume, engine)
    scores.semantic_evidence = semantic_result.evidence
    scores.whole_document_similarity = semantic_result.whole_document_similarity

    project_score, project_evidence = score_project_experience(
        job, resume, engine, taxonomy
    )
    scores.project_experience_evidence = project_evidence

    education_score, education_matches, education_missing = score_education(
        job, resume, engine
    )
    scores.education_evidence = education_matches
    scores.education_not_found = education_missing

    certification_score, cert_matches, cert_missing = score_certifications(
        job, resume, taxonomy
    )
    scores.certification_evidence = cert_matches
    scores.certifications_not_found = cert_missing

    soft_score, soft_matches, soft_missing = score_soft_skills(
        job, resume, engine, taxonomy
    )
    scores.soft_skill_evidence = soft_matches
    scores.soft_skills_not_found = soft_missing

    raw_scores = {
        C_REQUIRED_SKILLS: required_score,
        C_SEMANTIC: semantic_result.score,
        C_OTHER_KEYWORDS: other_score,
        C_PROJECT_EXPERIENCE: project_score,
        C_EDUCATION: education_score,
        C_CERTIFICATIONS: certification_score,
        C_SOFT_SKILLS: soft_score,
    }
    scores.component_scores = {
        component: round(clamp_score(value), 2) for component, value in raw_scores.items()
    }

    weighted_total = 0.0
    for component, weight in plan.effective_weights.items():
        contribution = weight * scores.component_scores[component]
        scores.weighted_contributions[component] = round(contribution, 3)
        weighted_total += contribution

    scores.penalties = compute_penalties(job, required_missing)
    penalty_points = sum(penalty.points for penalty in scores.penalties)
    scores.final_score = round(clamp_score(weighted_total - penalty_points), 2)

    return scores


def build_parsed_resume(
    candidate_id: str,
    filename: str,
    candidate_name: str,
    text: str,
    sections: ResumeSections,
    warnings: list[str] | None = None,
) -> ParsedResume:
    """Pre-compute the chunk sets used by every semantic comparison."""
    chunks = chunk_text(text)
    practical_text = sections.practical_text
    practical_chunks = chunk_text(practical_text) if practical_text else []
    return ParsedResume(
        candidate_id=candidate_id,
        filename=filename,
        candidate_name=candidate_name,
        text=text,
        sections=sections,
        chunks=chunks,
        practical_chunks=practical_chunks or chunks,
        warnings=list(warnings or []),
    )
