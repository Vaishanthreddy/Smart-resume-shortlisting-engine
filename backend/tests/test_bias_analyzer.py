"""JD bias review: suggestions only, never a scoring input."""

from __future__ import annotations

from app.services.bias_analyzer import analyze_bias
from app.services.category_scorer import build_scoring_plan
from app.services.jd_analyzer import analyze_job_description


def test_flags_gender_coded_language() -> None:
    job = analyze_job_description(
        "Job Title: Developer\nRequirements:\nWe want a coding ninja who is aggressive about delivery."
    )
    categories = {flag.category for flag in analyze_bias(job)}
    assert "gender-coded language" in categories


def test_flags_age_related_language() -> None:
    job = analyze_job_description(
        "Job Title: Analyst\nRequirements:\nLooking for a young and energetic team member."
    )
    assert any(flag.category == "age-related language" for flag in analyze_bias(job))


def test_flags_native_speaker_wording() -> None:
    job = analyze_job_description(
        "Job Title: Writer\nRequirements:\nMust be a native speaker of English."
    )
    assert any(flag.category == "language requirement" for flag in analyze_bias(job))


def test_flags_unrealistic_experience_for_a_junior_role() -> None:
    job = analyze_job_description(
        "Job Title: Junior Developer\nRequirements:\nMinimum 8 years of experience required."
    )
    assert any(flag.category == "experience expectation" for flag in analyze_bias(job))


def test_clean_job_description_produces_no_flags(jd_text) -> None:
    assert analyze_bias(analyze_job_description(jd_text)) == []


def test_flags_never_change_the_scoring_plan() -> None:
    neutral = "Job Title: Developer\nRequirements:\nProficient in Python and SQL."
    biased = (
        "Job Title: Developer\nRequirements:\nProficient in Python and SQL.\n"
        "We want a young rockstar ninja who is a native speaker."
    )
    neutral_plan = build_scoring_plan(analyze_job_description(neutral))
    biased_plan = build_scoring_plan(analyze_job_description(biased))
    assert neutral_plan.effective_weights == biased_plan.effective_weights
