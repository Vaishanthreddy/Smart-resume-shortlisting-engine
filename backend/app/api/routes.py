"""HTTP API.

Uploaded bytes live only for the duration of the request. What is cached
afterwards is the derived scoring result, so that POST /api/compare can explain
two candidates from the same ranking without the recruiter uploading again.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import MAX_RESUMES_PER_REQUEST, RESULT_CACHE_SIZE
from app.schemas import (
    AnalyzeJDResponse,
    CompareRequest,
    CompareResponse,
    HealthResponse,
    RankResponse,
    compare_response,
    job_analysis_out,
    rank_response,
    scoring_info_out,
)
from app.services.document_parser import DocumentParseError
from app.services.explanation_generator import compare_candidates
from app.services.keyword_matcher import get_taxonomy
from app.services.ranking_engine import (
    RankingOutcome,
    UploadedFile,
    analyze_jd_file,
    rank_candidates,
)
from app.services.semantic_matcher import get_semantic_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Bounded in-memory store of derived results (no document text, no files).
_RESULT_CACHE: "OrderedDict[str, RankingOutcome]" = OrderedDict()


def _remember(outcome: RankingOutcome) -> None:
    _RESULT_CACHE[outcome.result_id] = outcome
    while len(_RESULT_CACHE) > RESULT_CACHE_SIZE:
        _RESULT_CACHE.popitem(last=False)


async def _read_upload(upload: UploadFile) -> UploadedFile:
    data = await upload.read()
    await upload.close()
    return UploadedFile(
        filename=upload.filename or "unnamed",
        data=data,
        content_type=upload.content_type,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Backend status, semantic model status and model name."""
    engine = get_semantic_engine()
    taxonomy = get_taxonomy()
    return HealthResponse(
        status="ok",
        semantic_model_status=engine.status,
        model_name=engine.model_name,
        model_backend=engine.backend,
        taxonomy_version=taxonomy.version,
        detail=engine.load_error or "Sentence-transformer loaded.",
    )


@router.post("/analyze-jd", response_model=AnalyzeJDResponse)
async def analyze_jd(jd_file: UploadFile = File(...)) -> AnalyzeJDResponse:
    """Structured analysis of one job description, with the weights it implies."""
    upload = await _read_upload(jd_file)
    try:
        job, plan, bias_flags = analyze_jd_file(upload)
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return AnalyzeJDResponse(
        job=job_analysis_out(job, bias_flags), scoring=scoring_info_out(plan)
    )


@router.post("/rank", response_model=RankResponse)
async def rank(
    jd_file: UploadFile = File(...),
    resume_files: list[UploadFile] = File(...),
) -> RankResponse:
    """Rank every uploaded resume against the uploaded job description."""
    if not resume_files:
        raise HTTPException(status_code=400, detail="Upload at least one resume.")
    if len(resume_files) > MAX_RESUMES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{len(resume_files)} resumes were uploaded; the limit per request is "
                f"{MAX_RESUMES_PER_REQUEST}."
            ),
        )

    jd_upload = await _read_upload(jd_file)
    resume_uploads = [await _read_upload(item) for item in resume_files]

    try:
        outcome = rank_candidates(jd_upload, resume_uploads)
    except DocumentParseError as exc:
        # Only a failure on the JD itself reaches here; resume failures are
        # collected per file and reported in summary.failed_files.
        raise HTTPException(
            status_code=400, detail=f"The job description could not be read. {exc.message}"
        ) from exc

    if not outcome.candidates:
        detail = "None of the uploaded resumes could be processed."
        if outcome.failed_files:
            detail += " " + " ".join(item.error for item in outcome.failed_files)
        raise HTTPException(status_code=422, detail=detail)

    _remember(outcome)
    return rank_response(outcome)


@router.post("/compare", response_model=CompareResponse)
def compare(request: CompareRequest) -> CompareResponse:
    """Compare two candidates from the same ranking result."""
    outcome = _RESULT_CACHE.get(request.result_id)
    if outcome is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "That ranking result is no longer available. Run the ranking again to "
                "compare candidates."
            ),
        )

    by_id = {candidate.candidate_id: candidate for candidate in outcome.candidates}
    missing = [
        candidate_id
        for candidate_id in (request.candidate_a_id, request.candidate_b_id)
        if candidate_id not in by_id
    ]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown candidate id(s) in this result: {', '.join(missing)}.",
        )
    if request.candidate_a_id == request.candidate_b_id:
        raise HTTPException(status_code=400, detail="Pick two different candidates.")

    first = by_id[request.candidate_a_id]
    second = by_id[request.candidate_b_id]

    comparison = compare_candidates(
        a_id=first.candidate_id,
        a_name=first.candidate_name,
        a_scores=first.scores,
        b_id=second.candidate_id,
        b_name=second.candidate_name,
        b_scores=second.scores,
        plan=outcome.plan,
    )
    return compare_response(request.result_id, comparison)
