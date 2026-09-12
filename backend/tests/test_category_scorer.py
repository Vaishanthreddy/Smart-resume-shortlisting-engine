"""Component scoring, weight redistribution and the final formula."""

from __future__ import annotations

import pytest

from app.config import (
    BASE_WEIGHTS,
    C_CERTIFICATIONS,
    C_EDUCATION,
    C_OTHER_KEYWORDS,
    C_PROJECT_EXPERIENCE,
    C_REQUIRED_SKILLS,
    C_SEMANTIC,
    C_SOFT_SKILLS,
)
from app.services.category_scorer import (
    build_parsed_resume,
    build_scoring_plan,
    redistribute_weights,
    score_candidate,
    score_certifications,
    score_education,
    score_other_keywords,
    score_project_experience,
    score_required_skills,
    score_soft_skills,
)
from app.services.jd_analyzer import analyze_job_description
from app.services.section_parser import parse_sections
from tests.conftest import MEDIUM_RESUME, STRONG_RESUME, UNFORMATTED_RESUME, WEAK_RESUME


def _resume(text: str, name: str = "candidate-01"):
    return build_parsed_resume(name, f"{name}.txt", "Test Candidate", text, parse_sections(text))


@pytest.fixture
def job(jd_text):
    return analyze_job_description(jd_text)


@pytest.fixture
def plan(job):
    return build_scoring_plan(job)


# --------------------------------------------------------------- base weights
def test_base_weights_match_the_specification() -> None:
    assert BASE_WEIGHTS[C_REQUIRED_SKILLS] == 0.30
    assert BASE_WEIGHTS[C_SEMANTIC] == 0.25
    assert BASE_WEIGHTS[C_OTHER_KEYWORDS] == 0.15
    assert BASE_WEIGHTS[C_PROJECT_EXPERIENCE] == 0.15
    assert BASE_WEIGHTS[C_EDUCATION] == 0.05
    assert BASE_WEIGHTS[C_CERTIFICATIONS] == 0.05
    assert BASE_WEIGHTS[C_SOFT_SKILLS] == 0.05
    assert sum(BASE_WEIGHTS.values()) == pytest.approx(1.0)


# ------------------------------------------------------------ redistribution
def test_inactive_weight_is_redistributed_proportionally() -> None:
    active = [c for c in BASE_WEIGHTS if c != C_CERTIFICATIONS]
    effective = redistribute_weights(active)

    assert C_CERTIFICATIONS not in effective
    assert sum(effective.values()) == pytest.approx(1.0)
    # 0.30 / 0.95 — proportional, so relative importance is preserved.
    assert effective[C_REQUIRED_SKILLS] == pytest.approx(0.30 / 0.95)
    assert effective[C_SEMANTIC] / effective[C_REQUIRED_SKILLS] == pytest.approx(0.25 / 0.30)


def test_multiple_inactive_components_redistribute() -> None:
    active = [C_REQUIRED_SKILLS, C_SEMANTIC, C_OTHER_KEYWORDS, C_PROJECT_EXPERIENCE]
    effective = redistribute_weights(active)
    assert sum(effective.values()) == pytest.approx(1.0)
    assert set(effective) == set(active)


def test_all_components_active_leaves_base_weights_unchanged() -> None:
    effective = redistribute_weights(list(BASE_WEIGHTS))
    for component, weight in BASE_WEIGHTS.items():
        assert effective[component] == pytest.approx(weight)


def test_no_active_components_raises() -> None:
    with pytest.raises(ValueError):
        redistribute_weights([])


def test_plan_marks_absent_categories_inactive() -> None:
    text = """Job Title: Support Engineer
Requirements:
Proficient in Linux and networking.
"""
    plan = build_scoring_plan(analyze_job_description(text))
    assert C_EDUCATION not in plan.effective_weights
    assert C_CERTIFICATIONS not in plan.effective_weights
    assert C_EDUCATION in plan.inactive_components
    assert sum(plan.effective_weights.values()) == pytest.approx(1.0)
    assert plan.activation_reasons[C_EDUCATION]


def test_same_plan_applies_to_every_candidate(job, plan, engine, taxonomy) -> None:
    for text in (STRONG_RESUME, MEDIUM_RESUME, WEAK_RESUME):
        scores = score_candidate(job, plan, _resume(text), engine, taxonomy)
        assert set(scores.weighted_contributions) == set(plan.effective_weights)


# --------------------------------------------------------------- components
def test_required_skill_coverage_is_a_simple_ratio(job, taxonomy) -> None:
    score, matched, missing = score_required_skills(job, _resume(STRONG_RESUME), taxonomy)
    assert score == pytest.approx(100.0)
    assert missing == []
    assert {item.name for item in matched} == set(job.required_skills)


def test_two_of_three_required_skills_scores_two_thirds(taxonomy) -> None:
    job = analyze_job_description("Requirements:\nPython, SQL and Power BI are required.")
    assert len(job.required_skills) == 3
    score, matched, missing = score_required_skills(
        job, _resume("Skills\nPython and SQL used daily for reporting work."), taxonomy
    )
    assert score == pytest.approx(200 / 3, abs=0.01)
    assert len(matched) == 2 and len(missing) == 1


def test_required_skill_score_ignores_repetition(job, taxonomy) -> None:
    honest = _resume(STRONG_RESUME)
    stuffed = _resume(STRONG_RESUME + "\n" + "Python Docker PostgreSQL REST API\n" * 50)
    assert score_required_skills(job, honest, taxonomy)[0] == score_required_skills(
        job, stuffed, taxonomy
    )[0]


def test_other_keywords_exclude_required_skills(job, taxonomy) -> None:
    _, matched, _ = score_other_keywords(job, _resume(STRONG_RESUME), taxonomy)
    names = {item.name for item in matched}
    assert not names & set(job.required_skills)
    assert "kubernetes" in names


def test_project_experience_rewards_relevant_practical_evidence(job, engine, taxonomy) -> None:
    strong = score_project_experience(job, _resume(STRONG_RESUME), engine, taxonomy)[0]
    weak = score_project_experience(job, _resume(WEAK_RESUME), engine, taxonomy)[0]
    assert strong > weak
    assert 0.0 <= strong <= 100.0


def test_projects_alone_can_provide_practical_evidence(job, engine, taxonomy) -> None:
    """An entry-level candidate with no employment is not disqualified."""
    projects_only = """Jo Patel
Projects
Built and maintained RESTful backend services in Python for a university portal.
Designed PostgreSQL database schemas and optimised slow queries.
Deployed the service with Docker.
Education
Bachelor of Science in Computer Science, 2024
"""
    score = score_project_experience(job, _resume(projects_only), engine, taxonomy)[0]
    assert score > 0


def test_education_matches_only_what_the_jd_requested(job, engine) -> None:
    score, matched, missing = score_education(job, _resume(STRONG_RESUME), engine)
    assert score > 0 and matched and not missing

    unrelated = "Education\nBachelor of Fine Arts in Sculpture, 2019"
    low_score, _, _ = score_education(job, _resume(unrelated), engine)
    assert low_score < score


def test_no_education_requirement_means_no_penalty(engine) -> None:
    job = analyze_job_description("Requirements:\nProficient in Python.")
    plan = build_scoring_plan(job)
    assert C_EDUCATION not in plan.effective_weights
    assert score_education(job, _resume(WEAK_RESUME), engine) == (0.0, [], [])


def test_certifications_match_only_requested_ones(job, taxonomy) -> None:
    score, matched, _ = score_certifications(job, _resume(STRONG_RESUME), taxonomy)
    assert score == pytest.approx(100.0)
    assert matched[0].name == "aws certified developer"

    unrelated = "Certifications\nCertified Yoga Instructor, 2020"
    assert score_certifications(job, _resume(unrelated), taxonomy)[0] == 0.0


def test_soft_skills_need_evidence_not_a_listing(job, engine, taxonomy) -> None:
    listed_only = """Skills
Communication, teamwork, leadership, problem solving
Education
Bachelor of Science in Computer Science
"""
    evidenced = """Experience
Collaborated with a four-member development team on the billing service.
Presented release notes to non-technical stakeholders each sprint.
"""
    listed_score, _, listed_missing = score_soft_skills(job, _resume(listed_only), engine, taxonomy)
    evidenced_score, evidenced_matches, _ = score_soft_skills(
        job, _resume(evidenced), engine, taxonomy
    )
    assert evidenced_score > listed_score
    assert listed_missing
    assert any(item.match_method == "behavioural evidence" for item in evidenced_matches)


# --------------------------------------------------------------- final score
def test_final_score_equals_the_weighted_formula(job, plan, engine, taxonomy) -> None:
    scores = score_candidate(job, plan, _resume(STRONG_RESUME), engine, taxonomy)
    expected = sum(
        plan.effective_weights[component] * scores.component_scores[component]
        for component in plan.effective_weights
    )
    expected -= sum(penalty.points for penalty in scores.penalties)
    assert scores.final_score == pytest.approx(round(max(0.0, min(100.0, expected)), 2))


def test_every_component_score_is_within_range(job, plan, engine, taxonomy) -> None:
    for text in (STRONG_RESUME, MEDIUM_RESUME, WEAK_RESUME, UNFORMATTED_RESUME):
        scores = score_candidate(job, plan, _resume(text), engine, taxonomy)
        assert 0.0 <= scores.final_score <= 100.0
        for component, value in scores.component_scores.items():
            assert 0.0 <= value <= 100.0, component


def test_mandatory_skill_penalty_is_explicit(job, plan, engine, taxonomy) -> None:
    scores = score_candidate(job, plan, _resume(WEAK_RESUME), engine, taxonomy)
    assert scores.penalties
    penalty = scores.penalties[0]
    assert penalty.points > 0
    assert "not found in the resume" in penalty.reason
    assert "No evidence of" in penalty.detail
    assert "was found in the submitted resume" in penalty.detail
    assert scores.required_skills_not_found


def test_no_penalty_when_every_required_skill_is_found(job, plan, engine, taxonomy) -> None:
    scores = score_candidate(job, plan, _resume(STRONG_RESUME), engine, taxonomy)
    assert scores.penalties == []


def test_missing_headings_do_not_penalise_a_candidate(job, plan, engine, taxonomy) -> None:
    """The same content without headings must still score on required skills."""
    scores = score_candidate(job, plan, _resume(UNFORMATTED_RESUME), engine, taxonomy)
    assert scores.component_scores[C_REQUIRED_SKILLS] == pytest.approx(100.0)
    assert scores.used_section_fallback is False or scores.final_score > 0


def test_scoring_is_deterministic(job, plan, engine, taxonomy) -> None:
    first = score_candidate(job, plan, _resume(STRONG_RESUME), engine, taxonomy)
    second = score_candidate(job, plan, _resume(STRONG_RESUME), engine, taxonomy)
    assert first.final_score == second.final_score
    assert first.component_scores == second.component_scores
