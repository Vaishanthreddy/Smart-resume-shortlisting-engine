"""Pydantic request and response models.

These models are the contract the frontend TypeScript interfaces mirror exactly.
Converters from the internal dataclasses live here so the route handlers stay
thin and the field names are defined in one place.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import APP_VERSION, COMPONENT_LABELS
from app.services.bias_analyzer import BiasFlag
from app.services.category_scorer import (
    CandidateScores,
    MatchedItem,
    Penalty,
    ScoringPlan,
)
from app.services.explanation_generator import ComparisonResult
from app.services.jd_analyzer import JobRequirements
from app.services.ranking_engine import FailedFile, RankedCandidate, RankingOutcome
from app.services.semantic_matcher import RequirementEvidence


# --------------------------------------------------------------------------- #
# Shared pieces
# --------------------------------------------------------------------------- #
class MatchedItemOut(BaseModel):
    name: str
    evidence: str = ""
    match_method: str = "exact"
    confidence: float = 1.0
    found_in: str = ""


class SemanticEvidenceOut(BaseModel):
    requirement: str
    requirement_type: str
    importance: float
    best_evidence: str
    similarity: float
    meets_threshold: bool
    score: float


class PenaltyOut(BaseModel):
    reason: str
    points: float
    detail: str = ""


class BiasFlagOut(BaseModel):
    category: str
    message: str
    evidence: str
    severity: str


class FailedFileOut(BaseModel):
    filename: str
    error: str
    reason_code: str


# --------------------------------------------------------------------------- #
# Job analysis
# --------------------------------------------------------------------------- #
class JobAnalysisOut(BaseModel):
    title: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    other_keywords: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    required_qualifications: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certification_requirements: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    experience_expectation: str = ""
    requirement_statement_count: int = 0
    semantic_requirement_count: int = 0
    skill_confidence: dict[str, float] = Field(default_factory=dict)
    skill_sources: dict[str, str] = Field(default_factory=dict)
    analysis_notes: list[str] = Field(default_factory=list)
    bias_flags: list[BiasFlagOut] = Field(default_factory=list)


class ScoringInfoOut(BaseModel):
    base_weights: dict[str, float]
    effective_weights: dict[str, float]
    active_components: list[str]
    inactive_components: list[str]
    activation_reasons: dict[str, str]
    component_labels: dict[str, str] = Field(default_factory=lambda: dict(COMPONENT_LABELS))


class AnalyzeJDResponse(BaseModel):
    job: JobAnalysisOut
    scoring: ScoringInfoOut


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
class CandidateOut(BaseModel):
    rank: int
    candidate_id: str
    candidate_name: str
    filename: str
    final_score: float
    component_scores: dict[str, float]
    weighted_contributions: dict[str, float]
    matched_required_skills: list[MatchedItemOut] = Field(default_factory=list)
    matched_other_keywords: list[MatchedItemOut] = Field(default_factory=list)
    required_skills_not_found: list[str] = Field(default_factory=list)
    other_keywords_not_found: list[str] = Field(default_factory=list)
    semantic_evidence: list[SemanticEvidenceOut] = Field(default_factory=list)
    project_experience_evidence: list[SemanticEvidenceOut] = Field(default_factory=list)
    education_evidence: list[MatchedItemOut] = Field(default_factory=list)
    certification_evidence: list[MatchedItemOut] = Field(default_factory=list)
    soft_skill_evidence: list[MatchedItemOut] = Field(default_factory=list)
    education_not_found: list[str] = Field(default_factory=list)
    certifications_not_found: list[str] = Field(default_factory=list)
    soft_skills_not_found: list[str] = Field(default_factory=list)
    penalties: list[PenaltyOut] = Field(default_factory=list)
    whole_document_similarity: float | None = None
    explanation: str = ""
    warnings: list[str] = Field(default_factory=list)


class SummaryOut(BaseModel):
    total_candidates: int
    successfully_processed: int
    failed_files: list[FailedFileOut] = Field(default_factory=list)


class ModelInfoOut(BaseModel):
    name: str
    backend: str
    note: str = ""


class RankResponse(BaseModel):
    result_id: str
    job: JobAnalysisOut
    scoring: ScoringInfoOut
    summary: SummaryOut
    candidates: list[CandidateOut]
    model: ModelInfoOut


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
class CompareRequest(BaseModel):
    result_id: str = Field(..., description="result_id returned by POST /api/rank")
    candidate_a_id: str
    candidate_b_id: str


class ComponentDifferenceOut(BaseModel):
    component: str
    label: str
    candidate_a_score: float
    candidate_b_score: float
    difference: float
    effective_weight: float
    weighted_difference: float


class CompareResponse(BaseModel):
    result_id: str
    candidate_a_id: str
    candidate_b_id: str
    candidate_a_name: str
    candidate_b_name: str
    candidate_a_final_score: float
    candidate_b_final_score: float
    final_score_difference: float
    component_differences: list[ComponentDifferenceOut]
    only_a_required_skills: list[str]
    only_b_required_skills: list[str]
    shared_required_skills: list[str]
    only_a_other_keywords: list[str]
    only_b_other_keywords: list[str]
    a_requirements_not_found: list[str]
    b_requirements_not_found: list[str]
    a_best_evidence: list[str]
    b_best_evidence: list[str]
    explanation: str


class HealthResponse(BaseModel):
    status: str
    version: str = APP_VERSION
    semantic_model_status: str
    model_name: str
    model_backend: str
    taxonomy_version: str
    detail: str = ""


class ErrorResponse(BaseModel):
    detail: str
    reason_code: str = "error"


# --------------------------------------------------------------------------- #
# Converters
# --------------------------------------------------------------------------- #
def matched_item_out(item: MatchedItem) -> MatchedItemOut:
    return MatchedItemOut(
        name=item.name,
        evidence=item.evidence,
        match_method=item.match_method,
        confidence=round(item.confidence, 3),
        found_in=item.found_in,
    )


def semantic_evidence_out(item: RequirementEvidence) -> SemanticEvidenceOut:
    return SemanticEvidenceOut(
        requirement=item.requirement,
        requirement_type=item.requirement_type,
        importance=item.importance,
        best_evidence=item.best_evidence,
        similarity=item.similarity,
        meets_threshold=item.meets_threshold,
        score=item.score,
    )


def penalty_out(item: Penalty) -> PenaltyOut:
    return PenaltyOut(reason=item.reason, points=item.points, detail=item.detail)


def bias_flag_out(flag: BiasFlag) -> BiasFlagOut:
    return BiasFlagOut(
        category=flag.category,
        message=flag.message,
        evidence=flag.evidence,
        severity=flag.severity,
    )


def job_analysis_out(job: JobRequirements, bias_flags: list[BiasFlag]) -> JobAnalysisOut:
    return JobAnalysisOut(
        title=job.title,
        required_skills=job.required_skills,
        preferred_skills=job.preferred_skills,
        other_keywords=job.other_keywords,
        responsibilities=job.responsibilities,
        required_qualifications=job.required_qualifications,
        preferred_qualifications=job.preferred_qualifications,
        education_requirements=[req.label for req in job.education_requirements],
        certification_requirements=[req.name for req in job.certification_requirements],
        soft_skills=job.soft_skills,
        experience_expectation=job.experience_expectation.label,
        requirement_statement_count=len(job.requirements),
        semantic_requirement_count=len(job.semantic_requirements),
        skill_confidence={k: round(v, 2) for k, v in job.confidence_by_skill.items()},
        skill_sources=job.skill_sources,
        analysis_notes=job.analysis_notes,
        bias_flags=[bias_flag_out(flag) for flag in bias_flags],
    )


def scoring_info_out(plan: ScoringPlan) -> ScoringInfoOut:
    return ScoringInfoOut(
        base_weights={k: round(v, 4) for k, v in plan.base_weights.items()},
        effective_weights={k: round(v, 4) for k, v in plan.effective_weights.items()},
        active_components=plan.active_components,
        inactive_components=plan.inactive_components,
        activation_reasons=plan.activation_reasons,
    )


def candidate_out(candidate: RankedCandidate) -> CandidateOut:
    scores: CandidateScores = candidate.scores
    return CandidateOut(
        rank=candidate.rank,
        candidate_id=candidate.candidate_id,
        candidate_name=candidate.candidate_name,
        filename=candidate.filename,
        final_score=scores.final_score,
        component_scores=scores.component_scores,
        weighted_contributions=scores.weighted_contributions,
        matched_required_skills=[matched_item_out(i) for i in scores.matched_required_skills],
        matched_other_keywords=[matched_item_out(i) for i in scores.matched_other_keywords],
        required_skills_not_found=scores.required_skills_not_found,
        other_keywords_not_found=scores.other_keywords_not_found,
        semantic_evidence=[semantic_evidence_out(i) for i in scores.semantic_evidence],
        project_experience_evidence=[
            semantic_evidence_out(i) for i in scores.project_experience_evidence
        ],
        education_evidence=[matched_item_out(i) for i in scores.education_evidence],
        certification_evidence=[matched_item_out(i) for i in scores.certification_evidence],
        soft_skill_evidence=[matched_item_out(i) for i in scores.soft_skill_evidence],
        education_not_found=scores.education_not_found,
        certifications_not_found=scores.certifications_not_found,
        soft_skills_not_found=scores.soft_skills_not_found,
        penalties=[penalty_out(p) for p in scores.penalties],
        whole_document_similarity=scores.whole_document_similarity,
        explanation=candidate.explanation,
        warnings=candidate.warnings,
    )


def failed_file_out(item: FailedFile) -> FailedFileOut:
    return FailedFileOut(
        filename=item.filename, error=item.error, reason_code=item.reason_code
    )


def rank_response(outcome: RankingOutcome) -> RankResponse:
    note = (
        ""
        if outcome.semantic_backend == "sentence-transformers"
        else (
            "The sentence-transformer could not be loaded, so a deterministic lexical "
            "vector space is being used for semantic matching. Scores remain on the "
            "same 0-100 scale."
        )
    )
    return RankResponse(
        result_id=outcome.result_id,
        job=job_analysis_out(outcome.job, outcome.bias_flags),
        scoring=scoring_info_out(outcome.plan),
        summary=SummaryOut(
            total_candidates=outcome.total_candidates,
            successfully_processed=len(outcome.candidates),
            failed_files=[failed_file_out(f) for f in outcome.failed_files],
        ),
        candidates=[candidate_out(c) for c in outcome.candidates],
        model=ModelInfoOut(
            name=outcome.model_name, backend=outcome.semantic_backend, note=note
        ),
    )


def compare_response(result_id: str, comparison: ComparisonResult) -> CompareResponse:
    return CompareResponse(
        result_id=result_id,
        candidate_a_id=comparison.candidate_a_id,
        candidate_b_id=comparison.candidate_b_id,
        candidate_a_name=comparison.candidate_a_name,
        candidate_b_name=comparison.candidate_b_name,
        candidate_a_final_score=comparison.candidate_a_final_score,
        candidate_b_final_score=comparison.candidate_b_final_score,
        final_score_difference=comparison.final_score_difference,
        component_differences=[
            ComponentDifferenceOut(**vars(item)) for item in comparison.component_differences
        ],
        only_a_required_skills=comparison.only_a_required_skills,
        only_b_required_skills=comparison.only_b_required_skills,
        shared_required_skills=comparison.shared_required_skills,
        only_a_other_keywords=comparison.only_a_other_keywords,
        only_b_other_keywords=comparison.only_b_other_keywords,
        a_requirements_not_found=comparison.a_requirements_not_found,
        b_requirements_not_found=comparison.b_requirements_not_found,
        a_best_evidence=comparison.a_best_evidence,
        b_best_evidence=comparison.b_best_evidence,
        explanation=comparison.explanation,
    )
