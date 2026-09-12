"""Optional bias review of the job description.

This feature reads the JD only. It never inspects a resume, never infers a
protected characteristic about a candidate and never contributes to any score.
Every flag is a suggestion for a human to review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.jd_analyzer import JobRequirements

MASCULINE_CODED = [
    "aggressive", "dominant", "competitive", "ninja", "rockstar", "rock star",
    "guru", "he/him", "salesman", "craftsman", "chairman", "manpower",
    "strong-willed", "fearless", "hard-driving",
]
FEMININE_CODED = [
    "nurturing", "she/her", "bubbly", "sympathetic", "gentle", "waitress",
    "hostess", "supportive team mother",
]
AGE_CODED = [
    "young", "youthful", "energetic team", "recent graduate only", "digital native",
    "fresh graduate only", "mature candidate", "under 30", "age between",
    "no more than", "must be born",
]
NATIVE_SPEAKER = [
    "native speaker", "native english", "mother tongue", "native-level",
    "native level english",
]
PHYSICAL_ABILITY = [
    "must be able to lift", "physically fit", "able-bodied", "perfect vision",
]

_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*years?", re.IGNORECASE)
_JUNIOR_TITLE_RE = re.compile(
    r"\b(junior|jr\.?|entry[\s-]?level|graduate|intern|trainee|associate)\b", re.IGNORECASE
)

SEVERITY_REVIEW = "review"
SEVERITY_NOTE = "note"


@dataclass
class BiasFlag:
    category: str
    message: str
    evidence: str
    severity: str = SEVERITY_REVIEW


def _find_phrases(text: str, phrases: list[str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for line in text.split("\n"):
        lowered = line.lower()
        for phrase in phrases:
            if phrase in lowered:
                hits.append((phrase, line.strip()))
    return hits


def analyze_bias(job: JobRequirements) -> list[BiasFlag]:
    """Return review suggestions for the JD wording."""
    text = job.raw_text or ""
    flags: list[BiasFlag] = []
    seen: set[tuple[str, str]] = set()

    def add(category: str, message: str, evidence: str, severity: str = SEVERITY_REVIEW) -> None:
        key = (category, evidence[:80])
        if key in seen:
            return
        seen.add(key)
        flags.append(
            BiasFlag(category=category, message=message, evidence=evidence, severity=severity)
        )

    for phrase, line in _find_phrases(text, MASCULINE_CODED):
        add(
            "gender-coded language",
            f"The wording “{phrase}” is often read as masculine-coded and may narrow "
            "the applicant pool. Consider a neutral alternative.",
            line,
        )
    for phrase, line in _find_phrases(text, FEMININE_CODED):
        add(
            "gender-coded language",
            f"The wording “{phrase}” is often read as feminine-coded. Consider a "
            "neutral alternative.",
            line,
        )
    for phrase, line in _find_phrases(text, AGE_CODED):
        add(
            "age-related language",
            f"The wording “{phrase}” may imply an age preference. Describe the skills "
            "needed instead.",
            line,
        )
    for phrase, line in _find_phrases(text, NATIVE_SPEAKER):
        add(
            "language requirement",
            f"“{phrase}” can exclude fluent non-native speakers. Consider stating the "
            "proficiency level the role actually needs.",
            line,
        )
    for phrase, line in _find_phrases(text, PHYSICAL_ABILITY):
        add(
            "physical requirement",
            f"“{phrase}” may exclude candidates with a disability unless it is a "
            "genuine requirement of the role.",
            line,
        )

    # Unrealistic experience expectation for a junior role.
    title_is_junior = bool(_JUNIOR_TITLE_RE.search(job.title or ""))
    min_years = job.experience_expectation.min_years
    if title_is_junior and min_years is not None and min_years >= 3:
        add(
            "experience expectation",
            f"The title suggests a junior role but {min_years:g}+ years of experience "
            "is requested. Review whether the expectation matches the level.",
            job.experience_expectation.source_sentence,
        )
    if min_years is not None and min_years >= 15:
        add(
            "experience expectation",
            f"{min_years:g}+ years of experience is an unusually high bar and may "
            "exceed the lifetime of some of the technologies listed.",
            job.experience_expectation.source_sentence,
            SEVERITY_NOTE,
        )

    # A technology cannot be required for longer than it has existed; a simple
    # proxy is a long experience demand attached to a single specific tool.
    for line in text.split("\n"):
        match = _YEARS_RE.search(line)
        if match and int(match.group(1)) >= 10 and len(line.split()) <= 14:
            add(
                "experience expectation",
                "A long experience requirement is attached to a narrow skill. Confirm "
                "the number of years is realistic for that technology.",
                line.strip(),
                SEVERITY_NOTE,
            )

    # Excessive requirement count.
    total_required = len(job.required_skills)
    if total_required >= 15:
        add(
            "requirement volume",
            f"{total_required} distinct required skills were extracted. Long mandatory "
            "lists discourage otherwise strong applicants; consider moving some to "
            "preferred.",
            f"{total_required} required skills detected",
            SEVERITY_NOTE,
        )

    # Contradiction: junior title with a senior-sounding mandatory scope.
    if title_is_junior and total_required >= 10:
        add(
            "requirement volume",
            "A junior title is combined with a large mandatory skill list, which may "
            "be contradictory.",
            f"{job.title}: {total_required} required skills",
            SEVERITY_NOTE,
        )

    return flags
