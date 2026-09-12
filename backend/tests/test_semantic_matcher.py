"""Requirement-level semantic matching."""

from __future__ import annotations

from app.services.jd_analyzer import RequirementStatement
from app.services.semantic_matcher import best_chunk_for, match_requirements
from app.services.text_cleaner import chunk_text
from tests.conftest import STRONG_RESUME, WEAK_RESUME


def _statement(text: str, kind: str = "required") -> RequirementStatement:
    return RequirementStatement(
        text=text,
        requirement_type=kind,
        importance=1.0,
        confidence=1.0,
        source_section="required",
        source_sentence=text,
    )


def test_scores_stay_within_zero_to_one_hundred(engine) -> None:
    chunks = chunk_text(STRONG_RESUME)
    statements = [
        _statement("Develop and maintain RESTful backend services."),
        _statement("Manage a herd of alpacas in rural Peru."),
    ]
    result = match_requirements(engine, statements, chunks)
    assert 0.0 <= result.score <= 100.0
    for item in result.evidence:
        assert 0.0 <= item.score <= 100.0
        assert -1.0 <= item.similarity <= 1.0


def test_best_evidence_is_the_most_relevant_chunk(engine) -> None:
    chunks = chunk_text(STRONG_RESUME)
    result = match_requirements(
        engine, [_statement("Develop and maintain RESTful backend services.")], chunks
    )
    evidence = result.evidence[0]
    assert "RESTful" in evidence.best_evidence or "REST" in evidence.best_evidence
    assert evidence.meets_threshold


def test_evidence_records_requirement_type_and_importance(engine) -> None:
    chunks = chunk_text(STRONG_RESUME)
    statements = [
        _statement("Design database schemas.", "required"),
        _statement("Exposure to Redis is nice to have.", "preferred"),
    ]
    result = match_requirements(engine, statements, chunks)
    assert result.evidence[0].requirement_type == "required"
    assert result.evidence[1].requirement_type == "preferred"
    assert result.evidence[0].importance > result.evidence[1].importance


def test_relevant_resume_outscores_irrelevant_resume(engine) -> None:
    statements = [
        _statement("Develop and maintain RESTful backend services."),
        _statement("Design database schemas and optimise slow queries."),
    ]
    strong = match_requirements(engine, statements, chunk_text(STRONG_RESUME))
    weak = match_requirements(engine, statements, chunk_text(WEAK_RESUME))
    assert strong.score > weak.score


def test_required_statements_carry_more_weight_than_preferred(engine) -> None:
    chunks = chunk_text(STRONG_RESUME)
    matched = "Developed and maintained RESTful services handling card settlement traffic."
    unmatched = "Operate heavy agricultural machinery on site."

    required_match = match_requirements(
        engine, [_statement(matched, "required"), _statement(unmatched, "preferred")], chunks
    )
    preferred_match = match_requirements(
        engine, [_statement(matched, "preferred"), _statement(unmatched, "required")], chunks
    )
    assert required_match.score > preferred_match.score


def test_no_chunks_yields_zero_without_crashing(engine) -> None:
    result = match_requirements(engine, [_statement("Anything at all.")], [])
    assert result.score == 0.0
    assert result.evidence[0].best_evidence == ""
    assert result.evidence[0].meets_threshold is False


def test_no_requirements_yields_zero(engine) -> None:
    assert match_requirements(engine, [], chunk_text(STRONG_RESUME)).score == 0.0


def test_best_chunk_for_returns_a_chunk_and_similarity(engine) -> None:
    chunk, similarity = best_chunk_for(
        engine, "Docker containers and deployment", chunk_text(STRONG_RESUME)
    )
    assert chunk
    assert 0.0 <= similarity <= 1.0


def test_encoding_is_deterministic(engine) -> None:
    first = engine.similarity("Developed REST APIs", "Built RESTful endpoints")
    second = engine.similarity("Developed REST APIs", "Built RESTful endpoints")
    assert first == second


def test_score_mapping_is_monotonic_and_clamped(engine) -> None:
    assert engine.score_from_similarity(-0.5) == 0.0
    assert engine.score_from_similarity(1.0) == 100.0
    assert engine.score_from_similarity(0.4) >= engine.score_from_similarity(0.2)


def test_whole_document_similarity_is_diagnostic_only(engine, jd_text) -> None:
    """It is reported, but it is not the semantic score."""
    from app.services.category_scorer import build_parsed_resume, score_semantic
    from app.services.jd_analyzer import analyze_job_description
    from app.services.section_parser import parse_sections

    job = analyze_job_description(jd_text)
    resume = build_parsed_resume(
        "candidate-01", "a.txt", "Dana", STRONG_RESUME, parse_sections(STRONG_RESUME)
    )
    result = score_semantic(job, resume, engine)
    assert result.whole_document_similarity is not None
    assert result.score != result.whole_document_similarity
