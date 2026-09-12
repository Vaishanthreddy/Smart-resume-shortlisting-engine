"""Requirement-level semantic matching.

The sentence-transformer is used for one thing only: turning text into vectors.
Every score is computed by the deterministic code in this project from cosine
similarities. The model is never asked to rate, rank or judge a candidate.

If the transformer cannot be loaded (no network, no local cache), the engine
falls back to a deterministic lexical vector space so the application still runs
end to end. The active backend is reported by /api/health and in the response.
"""

from __future__ import annotations

import functools
import logging
import threading
from dataclasses import dataclass, field

import numpy as np

from app.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_SIZE,
    EMBEDDING_MODEL_NAME,
    FALLBACK_EVIDENCE_THRESHOLD,
    FALLBACK_FEATURES,
    FALLBACK_SIM_CEILING,
    FALLBACK_SIM_FLOOR,
    FORCE_FALLBACK_EMBEDDINGS,
    REQUIREMENT_IMPORTANCE_WEIGHTS,
    SEMANTIC_EVIDENCE_THRESHOLD,
    SIM_CEILING,
    SIM_FLOOR,
    clamp_score,
)

logger = logging.getLogger(__name__)

BACKEND_TRANSFORMER = "sentence-transformers"
BACKEND_FALLBACK = "lexical-fallback"


@dataclass
class RequirementEvidence:
    """One JD requirement paired with its best supporting resume chunk."""

    requirement: str
    requirement_type: str
    importance: float
    best_evidence: str
    similarity: float
    meets_threshold: bool
    score: float
    source_section: str = ""


@dataclass
class SemanticResult:
    score: float
    evidence: list[RequirementEvidence] = field(default_factory=list)
    whole_document_similarity: float | None = None

    @property
    def supported_count(self) -> int:
        return sum(1 for item in self.evidence if item.meets_threshold)


class SemanticEngine:
    """Loads the embedding model once and encodes text in batches."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self.backend = BACKEND_FALLBACK
        self.load_error: str | None = None
        self._model = None
        self._fallback = None
        self._cache: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._load()

    # ------------------------------------------------------------------ set-up
    def _load(self) -> None:
        if FORCE_FALLBACK_EMBEDDINGS:
            self.load_error = "Disabled by FORCE_FALLBACK_EMBEDDINGS."
            self._build_fallback()
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self.backend = BACKEND_TRANSFORMER
            logger.info("Loaded sentence-transformer %s", self.model_name)
            return
        except Exception as exc:  # ImportError, download failure, corrupt cache…
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Sentence-transformer '%s' unavailable (%s); using the lexical "
                "fallback vector space.", self.model_name, self.load_error,
            )
        self._build_fallback()

    def _build_fallback(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer
        from sklearn.pipeline import FeatureUnion

        self._fallback = FeatureUnion(
            [
                (
                    "words",
                    HashingVectorizer(
                        analyzer="word",
                        ngram_range=(1, 2),
                        n_features=FALLBACK_FEATURES,
                        alternate_sign=False,
                        norm="l2",
                        stop_words="english",
                    ),
                ),
                (
                    "chars",
                    HashingVectorizer(
                        analyzer="char_wb",
                        ngram_range=(4, 5),
                        n_features=FALLBACK_FEATURES,
                        alternate_sign=False,
                        norm="l2",
                    ),
                ),
            ]
        )
        self.backend = BACKEND_FALLBACK

    # --------------------------------------------------------------- properties
    @property
    def is_transformer(self) -> bool:
        return self.backend == BACKEND_TRANSFORMER

    @property
    def sim_floor(self) -> float:
        return SIM_FLOOR if self.is_transformer else FALLBACK_SIM_FLOOR

    @property
    def sim_ceiling(self) -> float:
        return SIM_CEILING if self.is_transformer else FALLBACK_SIM_CEILING

    @property
    def evidence_threshold(self) -> float:
        return (
            SEMANTIC_EVIDENCE_THRESHOLD
            if self.is_transformer
            else FALLBACK_EVIDENCE_THRESHOLD
        )

    @property
    def status(self) -> str:
        return "ready" if self.is_transformer else "fallback"

    # ---------------------------------------------------------------- encoding
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into L2-normalised row vectors, using a memo cache."""
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)

        with self._lock:
            missing = [text for text in texts if text not in self._cache]
            unique_missing = list(dict.fromkeys(missing))

            if unique_missing:
                vectors = self._encode_uncached(unique_missing)
                if len(self._cache) > EMBEDDING_CACHE_SIZE:
                    self._cache.clear()
                for text, vector in zip(unique_missing, vectors):
                    self._cache[text] = vector

            return np.vstack([self._cache[text] for text in texts])

    def _encode_uncached(self, texts: list[str]) -> np.ndarray:
        if self._model is not None:
            vectors = self._model.encode(
                texts,
                batch_size=EMBEDDING_BATCH_SIZE,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return np.asarray(vectors, dtype=np.float32)

        sparse = self._fallback.transform(texts)
        dense = np.asarray(sparse.todense(), dtype=np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return dense / norms

    # ------------------------------------------------------------- similarity
    def similarity_matrix(self, left: list[str], right: list[str]) -> np.ndarray:
        if not left or not right:
            return np.zeros((len(left), len(right)), dtype=np.float32)
        return np.clip(self.encode(left) @ self.encode(right).T, -1.0, 1.0)

    def similarity(self, left: str, right: str) -> float:
        if not left.strip() or not right.strip():
            return 0.0
        return float(self.similarity_matrix([left], [right])[0][0])

    def score_from_similarity(self, similarity: float) -> float:
        """Map a cosine similarity onto the 0-100 component scale."""
        span = max(self.sim_ceiling - self.sim_floor, 1e-6)
        return clamp_score((similarity - self.sim_floor) / span * 100.0)

    def is_evidence(self, similarity: float) -> bool:
        return similarity >= self.evidence_threshold


@functools.lru_cache(maxsize=1)
def get_semantic_engine() -> SemanticEngine:
    """Process-wide singleton, warmed at application start-up."""
    return SemanticEngine()


# --------------------------------------------------------------------------- #
# Requirement-level matching
# --------------------------------------------------------------------------- #
def match_requirements(
    engine: SemanticEngine,
    requirements: list,
    chunks: list[str],
    *,
    default_importance_type: str = "required",
) -> SemanticResult:
    """Find the best supporting resume chunk for each JD requirement.

    `requirements` accepts RequirementStatement objects or plain strings.
    Returns a weighted-average score where required statements count for more
    than preferred ones.
    """
    if not requirements:
        return SemanticResult(score=0.0, evidence=[])

    texts: list[str] = []
    types: list[str] = []
    sections: list[str] = []
    for item in requirements:
        if isinstance(item, str):
            texts.append(item)
            types.append(default_importance_type)
            sections.append("")
        else:
            texts.append(item.text)
            types.append(getattr(item, "requirement_type", default_importance_type))
            sections.append(getattr(item, "source_section", ""))

    if not chunks:
        evidence = [
            RequirementEvidence(
                requirement=text,
                requirement_type=req_type,
                importance=REQUIREMENT_IMPORTANCE_WEIGHTS.get(req_type, 0.5),
                best_evidence="",
                similarity=0.0,
                meets_threshold=False,
                score=0.0,
                source_section=section,
            )
            for text, req_type, section in zip(texts, types, sections)
        ]
        return SemanticResult(score=0.0, evidence=evidence)

    matrix = engine.similarity_matrix(texts, chunks)
    best_indices = matrix.argmax(axis=1)

    evidence: list[RequirementEvidence] = []
    weighted_total = 0.0
    weight_total = 0.0

    for row, (text, req_type, section) in enumerate(zip(texts, types, sections)):
        best_index = int(best_indices[row])
        similarity = float(matrix[row][best_index])
        score = engine.score_from_similarity(similarity)
        weight = REQUIREMENT_IMPORTANCE_WEIGHTS.get(req_type, 0.5)

        evidence.append(
            RequirementEvidence(
                requirement=text,
                requirement_type=req_type,
                importance=weight,
                best_evidence=chunks[best_index],
                similarity=round(similarity, 4),
                meets_threshold=engine.is_evidence(similarity),
                score=round(score, 2),
                source_section=section,
            )
        )
        weighted_total += score * weight
        weight_total += weight

    final = weighted_total / weight_total if weight_total else 0.0
    return SemanticResult(score=clamp_score(final), evidence=evidence)


def best_chunk_for(engine: SemanticEngine, query: str, chunks: list[str]) -> tuple[str, float]:
    """Return the single best matching chunk for a query and its similarity."""
    if not chunks or not query.strip():
        return "", 0.0
    matrix = engine.similarity_matrix([query], chunks)
    index = int(matrix[0].argmax())
    return chunks[index], float(matrix[0][index])
