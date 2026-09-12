"""Pipeline orchestration and deterministic ranking.

Order of operations:
    extract text -> analyse JD -> parse resume sections -> keyword matching ->
    requirement-level semantic matching -> category scoring -> ranking ->
    explanations

A resume that cannot be parsed is recorded as a failed file and the remaining
candidates are still ranked.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app.config import C_PROJECT_EXPERIENCE, C_REQUIRED_SKILLS, C_SEMANTIC
from app.services.bias_analyzer import BiasFlag, analyze_bias
from app.services.category_scorer import (
    CandidateScores,
    ParsedResume,
    ScoringPlan,
    build_parsed_resume,
    build_scoring_plan,
    score_candidate,
)
from app.services.document_parser import DocumentParseError, extract_document
from app.services.explanation_generator import generate_explanation
from app.services.jd_analyzer import JobRequirements, analyze_job_description
from app.services.keyword_matcher import SkillTaxonomy, get_taxonomy
from app.services.section_parser import extract_candidate_name, parse_sections
from app.services.semantic_matcher import SemanticEngine, get_semantic_engine

logger = logging.getLogger(__name__)


@dataclass
class UploadedFile:
    filename: str
    data: bytes
    content_type: str | None = None


@dataclass
class FailedFile:
    filename: str
    error: str
    reason_code: str


@dataclass
class RankedCandidate:
    rank: int
    candidate_id: str
    candidate_name: str
    filename: str
    scores: CandidateScores
    explanation: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class RankingOutcome:
    result_id: str
    job: JobRequirements
    plan: ScoringPlan
    bias_flags: list[BiasFlag]
    candidates: list[RankedCandidate]
    failed_files: list[FailedFile]
    total_candidates: int
    semantic_backend: str
    model_name: str


def analyze_jd_file(
    upload: UploadedFile, taxonomy: SkillTaxonomy | None = None
) -> tuple[JobRequirements, ScoringPlan, list[BiasFlag]]:
    """Parse and analyse a single job description file."""
    document = extract_document(upload.filename, upload.data, upload.content_type)
    job = analyze_job_description(document.text, taxonomy or get_taxonomy())
    plan = build_scoring_plan(job)
    return job, plan, analyze_bias(job)


def _parse_resumes(
    uploads: list[UploadedFile],
) -> tuple[list[ParsedResume], list[FailedFile]]:
    """Parse every resume, isolating failures so one bad file cannot block the rest."""
    parsed: list[ParsedResume] = []
    failed: list[FailedFile] = []

    # Stable identifiers regardless of upload order.
    ordered = sorted(uploads, key=lambda item: item.filename.lower())

    for index, upload in enumerate(ordered, start=1):
        candidate_id = f"candidate-{index:02d}"
        try:
            document = extract_document(upload.filename, upload.data, upload.content_type)
        except DocumentParseError as exc:
            logger.warning("Skipping %s: %s", upload.filename, exc.reason_code)
            failed.append(
                FailedFile(
                    filename=upload.filename,
                    error=exc.message,
                    reason_code=exc.reason_code,
                )
            )
            continue
        except Exception as exc:  # pragma: no cover - unexpected parser failure
            logger.exception("Unexpected failure parsing %s", upload.filename)
            failed.append(
                FailedFile(
                    filename=upload.filename,
                    error=(
                        f"'{upload.filename}' could not be processed "
                        f"({type(exc).__name__}). The other resumes were still ranked."
                    ),
                    reason_code="unexpected_error",
                )
            )
            continue

        sections = parse_sections(document.text)
        parsed.append(
            build_parsed_resume(
                candidate_id=candidate_id,
                filename=upload.filename,
                candidate_name=extract_candidate_name(document.text, upload.filename),
                text=document.text,
                sections=sections,
                warnings=document.warnings,
            )
        )

    return parsed, failed


def _sort_key(item: tuple[ParsedResume, CandidateScores]) -> tuple:
    resume, scores = item
    return (
        -scores.final_score,
        -scores.component_scores.get(C_REQUIRED_SKILLS, 0.0),
        -scores.component_scores.get(C_SEMANTIC, 0.0),
        -scores.component_scores.get(C_PROJECT_EXPERIENCE, 0.0),
        resume.candidate_id,
    )


def rank_candidates(
    jd_upload: UploadedFile,
    resume_uploads: list[UploadedFile],
    *,
    engine: SemanticEngine | None = None,
    taxonomy: SkillTaxonomy | None = None,
) -> RankingOutcome:
    """Run the whole pipeline and return a deterministic ranking."""
    taxonomy = taxonomy or get_taxonomy()
    engine = engine or get_semantic_engine()

    job, plan, bias_flags = analyze_jd_file(jd_upload, taxonomy)
    parsed, failed = _parse_resumes(resume_uploads)

    scored: list[tuple[ParsedResume, CandidateScores]] = []
    for resume in parsed:
        try:
            scores = score_candidate(job, plan, resume, engine, taxonomy)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.exception("Scoring failed for %s", resume.filename)
            failed.append(
                FailedFile(
                    filename=resume.filename,
                    error=(
                        f"'{resume.filename}' was read successfully but could not be "
                        f"scored ({type(exc).__name__})."
                    ),
                    reason_code="scoring_error",
                )
            )
            continue
        scored.append((resume, scores))

    scored.sort(key=_sort_key)

    candidates: list[RankedCandidate] = []
    for rank, (resume, scores) in enumerate(scored, start=1):
        explanation = generate_explanation(
            rank=rank,
            candidate_label=resume.candidate_name,
            scores=scores,
            job=job,
            plan=plan,
        )
        candidates.append(
            RankedCandidate(
                rank=rank,
                candidate_id=resume.candidate_id,
                candidate_name=resume.candidate_name,
                filename=resume.filename,
                scores=scores,
                explanation=explanation,
                warnings=resume.warnings,
            )
        )

    logger.info(
        "Ranked %d candidates (%d failed) for role %r",
        len(candidates), len(failed), job.title,
    )

    return RankingOutcome(
        result_id=str(uuid.uuid4()),
        job=job,
        plan=plan,
        bias_flags=bias_flags,
        candidates=candidates,
        failed_files=failed,
        total_candidates=len(resume_uploads),
        semantic_backend=engine.backend,
        model_name=engine.model_name,
    )
