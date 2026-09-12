"""JD analysis: classification, extraction and JD-agnostic behaviour."""

from __future__ import annotations

from app.services.jd_analyzer import analyze_job_description


def test_extracts_title(jd_text: str) -> None:
    assert analyze_job_description(jd_text).title == "Backend Engineer"


def test_required_and_preferred_are_classified_separately(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    assert {"python", "postgresql", "rest api", "docker"} <= set(job.required_skills)
    assert "kubernetes" in job.preferred_skills
    assert "redis" in job.preferred_skills
    # A preferred skill is never also a required skill.
    assert not set(job.required_skills) & set(job.preferred_skills)


def test_indicator_phrases_override_section_context() -> None:
    text = """Requirements:
Familiarity with Terraform is a plus.
Proficient in Python.
"""
    job = analyze_job_description(text)
    assert "python" in job.required_skills
    assert "terraform" not in job.required_skills
    assert "terraform" in job.other_keywords


def test_keywords_are_deduplicated_across_categories(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    overlap = set(job.required_skills) & set(job.other_keywords)
    assert overlap == set(), f"double-counted: {overlap}"


def test_responsibilities_are_collected(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    assert len(job.responsibilities) >= 3
    assert any("RESTful" in item for item in job.responsibilities)


def test_education_requirement_is_extracted(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    assert len(job.education_requirements) == 1
    requirement = job.education_requirements[0]
    assert requirement.level == "bachelor"
    assert "computer science" in requirement.field_of_study.lower()


def test_certification_requirement_is_extracted(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    names = [item.name for item in job.certification_requirements]
    assert "aws certified developer" in names


def test_soft_skills_are_extracted(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    assert "communication" in job.soft_skills
    assert "teamwork" in job.soft_skills


def test_experience_expectation_is_parsed() -> None:
    job = analyze_job_description("Requirements:\nMinimum 5 years of experience in backend roles.")
    assert job.experience_expectation.min_years == 5
    assert "5+" in job.experience_expectation.label


def test_ignored_sections_do_not_pollute_requirements() -> None:
    text = """Job Title: Analyst

Benefits:
Free Tableau licences and a Kubernetes homelab budget.

Required Skills:
Proficient in SQL.
"""
    job = analyze_job_description(text)
    assert job.required_skills == ["sql"]
    assert "kubernetes" not in job.all_keywords
    assert "tableau" not in job.all_keywords


def test_skill_list_lines_are_flagged_and_excluded_from_semantic_set() -> None:
    text = """Required Skills:
Python, SQL, Docker, Redis, Kubernetes
Develop and maintain reporting services for the finance team.
"""
    job = analyze_job_description(text)
    assert any(statement.is_skill_list for statement in job.requirements)
    assert all(not statement.is_skill_list for statement in job.semantic_requirements)


def test_works_on_a_completely_different_job_description() -> None:
    """Nothing is hard-coded for one role: a non-technical JD analyses too."""
    text = """Job Title: Registered Nurse

Responsibilities:
Provide direct patient care and maintain accurate clinical records.
Collaborate with the multidisciplinary team on care planning.

Requirements:
Must have a Bachelor's degree in Nursing.
Strong communication skills are required.

Preferred:
Familiarity with electronic medical records is a plus.
"""
    job = analyze_job_description(text)
    assert job.title == "Registered Nurse"
    assert job.education_requirements[0].level == "bachelor"
    assert "nursing" in job.education_requirements[0].field_of_study.lower()
    assert "communication" in job.soft_skills
    assert len(job.responsibilities) >= 2


def test_unlabelled_job_description_still_yields_required_skills() -> None:
    text = (
        "We need someone to build data pipelines in Python and write SQL queries "
        "against Postgres every day."
    )
    job = analyze_job_description(text)
    assert job.required_skills, "fallback promotion should populate required skills"
    assert job.analysis_notes


def test_source_sentences_and_confidence_are_recorded(jd_text: str) -> None:
    job = analyze_job_description(jd_text)
    assert job.skill_sources["python"]
    assert 0.0 < job.confidence_by_skill["python"] <= 1.0


def test_analysis_is_deterministic(jd_text: str) -> None:
    first = analyze_job_description(jd_text)
    second = analyze_job_description(jd_text)
    assert first.required_skills == second.required_skills
    assert first.other_keywords == second.other_keywords
    assert [r.text for r in first.requirements] == [r.text for r in second.requirements]
