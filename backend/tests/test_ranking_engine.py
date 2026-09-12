"""End-to-end ranking: ordering, tie-breaking and partial failures."""

from __future__ import annotations

import pytest

from app.services.category_scorer import CandidateScores
from app.services.ranking_engine import UploadedFile, _sort_key, rank_candidates
from tests.conftest import (
    MEDIUM_RESUME,
    STRONG_RESUME,
    UNFORMATTED_RESUME,
    WEAK_RESUME,
    make_txt_upload,
)


def _outcome(jd_upload, uploads):
    return rank_candidates(jd_upload, uploads)


def test_strong_medium_weak_rank_in_that_order(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    order = [candidate.filename for candidate in outcome.candidates]
    assert order == ["a_strong.txt", "b_medium.txt", "c_weak.txt"]
    scores = [candidate.scores.final_score for candidate in outcome.candidates]
    assert scores == sorted(scores, reverse=True)


def test_ranks_are_sequential_and_start_at_one(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    assert [c.rank for c in outcome.candidates] == [1, 2, 3]


def test_every_candidate_is_ranked_not_just_the_top_three(jd_upload) -> None:
    uploads = [
        make_txt_upload(f"resume_{index:02d}.txt", text)
        for index, text in enumerate(
            [STRONG_RESUME, MEDIUM_RESUME, WEAK_RESUME, UNFORMATTED_RESUME] * 3
        )
    ]
    outcome = _outcome(jd_upload, uploads)
    assert len(outcome.candidates) == 12
    assert [c.rank for c in outcome.candidates] == list(range(1, 13))
    assert all(c.explanation for c in outcome.candidates)


def test_top_three_receive_detailed_explanations(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    for candidate in outcome.candidates[:3]:
        assert candidate.explanation
        assert "final score" in candidate.explanation
    assert "Largest contributions" in outcome.candidates[0].explanation


def test_explanations_use_cautious_language(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    joined = " ".join(candidate.explanation for candidate in outcome.candidates)
    assert "No evidence of" in joined
    assert "does not know" not in joined
    assert "hire" not in joined.lower()
    assert "reject" not in joined.lower()


def test_identical_resumes_tie_break_on_candidate_id(jd_upload) -> None:
    uploads = [
        make_txt_upload("zeta.txt", STRONG_RESUME),
        make_txt_upload("alpha.txt", STRONG_RESUME),
    ]
    outcome = _outcome(jd_upload, uploads)
    a, b = outcome.candidates
    assert a.scores.final_score == b.scores.final_score
    # Identifiers are assigned alphabetically by filename, then used as the
    # final tie-break, so alpha.txt (candidate-01) comes first.
    assert a.candidate_id < b.candidate_id
    assert a.filename == "alpha.txt"


def test_sort_key_prefers_required_skills_then_semantic() -> None:
    class FakeResume:
        candidate_id = "candidate-02"

    def scores(final: float, required: float, semantic: float) -> CandidateScores:
        item = CandidateScores()
        item.final_score = final
        item.component_scores = {
            "required_skills": required,
            "semantic_match": semantic,
            "project_experience": 0.0,
        }
        return item

    tied_a = (FakeResume(), scores(70.0, 90.0, 10.0))
    tied_b = (FakeResume(), scores(70.0, 50.0, 99.0))
    assert _sort_key(tied_a) < _sort_key(tied_b)


def test_ranking_is_deterministic_across_runs(jd_upload, resume_uploads) -> None:
    first = _outcome(jd_upload, resume_uploads)
    second = _outcome(jd_upload, list(reversed(resume_uploads)))
    assert [c.filename for c in first.candidates] == [c.filename for c in second.candidates]
    assert [c.scores.final_score for c in first.candidates] == [
        c.scores.final_score for c in second.candidates
    ]
    assert [c.candidate_id for c in first.candidates] == [
        c.candidate_id for c in second.candidates
    ]


def test_one_malformed_resume_does_not_block_the_others(jd_upload, resume_uploads) -> None:
    uploads = resume_uploads + [
        UploadedFile("broken.pdf", b"not a real pdf at all", "application/pdf"),
        UploadedFile("empty.txt", b"", "text/plain"),
    ]
    outcome = _outcome(jd_upload, uploads)
    assert len(outcome.candidates) == 3
    assert len(outcome.failed_files) == 2
    assert outcome.total_candidates == 5
    for failure in outcome.failed_files:
        assert failure.error and failure.reason_code


def test_failed_file_messages_name_the_file(jd_upload, resume_uploads) -> None:
    uploads = resume_uploads + [UploadedFile("empty.txt", b"", "text/plain")]
    outcome = _outcome(jd_upload, uploads)
    assert any("empty.txt" in failure.error for failure in outcome.failed_files)


def test_both_keyword_and_semantic_signals_change_the_ranking(jd_upload) -> None:
    """A resume with the right words but no relevant work ranks below one with both."""
    keywords_only = """Lee Monroe
Skills
Python, PostgreSQL, REST API, Docker
Experience
Barista, Corner Cafe (2021 - 2024)
Prepared coffee and managed the morning queue.
Education
Bachelor of Science in Computer Science, 2021
"""
    uploads = [
        make_txt_upload("both.txt", STRONG_RESUME),
        make_txt_upload("keywords_only.txt", keywords_only),
    ]
    outcome = _outcome(jd_upload, uploads)
    by_name = {c.filename: c for c in outcome.candidates}
    assert by_name["both.txt"].rank < by_name["keywords_only.txt"].rank
    # Required-skill coverage is identical; the difference is semantic.
    assert (
        by_name["both.txt"].scores.component_scores["required_skills"]
        == by_name["keywords_only.txt"].scores.component_scores["required_skills"]
    )
    assert (
        by_name["both.txt"].scores.component_scores["semantic_match"]
        > by_name["keywords_only.txt"].scores.component_scores["semantic_match"]
    )


def test_outcome_reports_the_scoring_plan_and_bias_flags(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    assert sum(outcome.plan.effective_weights.values()) == pytest.approx(1.0)
    assert outcome.result_id
    assert isinstance(outcome.bias_flags, list)


def test_no_hire_or_reject_decision_is_returned(jd_upload, resume_uploads) -> None:
    outcome = _outcome(jd_upload, resume_uploads)
    candidate = outcome.candidates[0]
    assert not hasattr(candidate, "decision")
    assert not hasattr(candidate, "recommendation")
