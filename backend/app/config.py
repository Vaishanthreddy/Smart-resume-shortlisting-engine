"""Central configuration for the Smart Resume Shortlisting Engine.

Every weight, threshold and limit used by the scoring pipeline lives here so the
behaviour of the engine can be audited and tuned from a single file. No module
is allowed to hard-code a scoring constant of its own.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
APP_DIR: Final[Path] = Path(__file__).resolve().parent
DATA_DIR: Final[Path] = APP_DIR / "data"
SKILL_TAXONOMY_PATH: Final[Path] = DATA_DIR / "skill_taxonomy.json"

# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
APP_NAME: Final[str] = "Smart Resume Shortlisting Engine"
APP_VERSION: Final[str] = "1.0.0"

# Comma separated list of origins permitted by CORS.
CORS_ORIGINS: Final[list[str]] = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
    ).split(",")
    if origin.strip()
]

LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()

# --------------------------------------------------------------------------- #
# Component identifiers
# --------------------------------------------------------------------------- #
C_REQUIRED_SKILLS: Final[str] = "required_skills"
C_SEMANTIC: Final[str] = "semantic_match"
C_OTHER_KEYWORDS: Final[str] = "other_keywords"
C_PROJECT_EXPERIENCE: Final[str] = "project_experience"
C_EDUCATION: Final[str] = "education"
C_CERTIFICATIONS: Final[str] = "certifications"
C_SOFT_SKILLS: Final[str] = "soft_skills"

COMPONENT_ORDER: Final[list[str]] = [
    C_REQUIRED_SKILLS,
    C_SEMANTIC,
    C_OTHER_KEYWORDS,
    C_PROJECT_EXPERIENCE,
    C_EDUCATION,
    C_CERTIFICATIONS,
    C_SOFT_SKILLS,
]

COMPONENT_LABELS: Final[dict[str, str]] = {
    C_REQUIRED_SKILLS: "Required skill coverage",
    C_SEMANTIC: "Semantic requirement matching",
    C_OTHER_KEYWORDS: "Other keyword coverage",
    C_PROJECT_EXPERIENCE: "Project and experience relevance",
    C_EDUCATION: "Education match",
    C_CERTIFICATIONS: "Certification match",
    C_SOFT_SKILLS: "Soft-skill evidence",
}

# --------------------------------------------------------------------------- #
# Base scoring weights (must sum to 1.0)
# --------------------------------------------------------------------------- #
BASE_WEIGHTS: Final[dict[str, float]] = {
    C_REQUIRED_SKILLS: 0.30,
    C_SEMANTIC: 0.25,
    C_OTHER_KEYWORDS: 0.15,
    C_PROJECT_EXPERIENCE: 0.15,
    C_EDUCATION: 0.05,
    C_CERTIFICATIONS: 0.05,
    C_SOFT_SKILLS: 0.05,
}

# Components that are always active, even for a sparse job description. The
# semantic component always has something to work with because a JD always
# yields at least one requirement sentence.
ALWAYS_ACTIVE_COMPONENTS: Final[set[str]] = {C_SEMANTIC}

WEIGHT_SUM_TOLERANCE: Final[float] = 1e-6

# --------------------------------------------------------------------------- #
# Document processing limits
# --------------------------------------------------------------------------- #
MAX_FILE_SIZE_MB: Final[float] = float(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_FILE_SIZE_BYTES: Final[int] = int(MAX_FILE_SIZE_MB * 1024 * 1024)
MAX_RESUMES_PER_REQUEST: Final[int] = int(os.getenv("MAX_RESUMES_PER_REQUEST", "100"))

ALLOWED_EXTENSIONS: Final[set[str]] = {".pdf", ".docx", ".txt"}

ALLOWED_MIME_TYPES: Final[dict[str, set[str]]] = {
    ".pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "text/markdown", "application/octet-stream"},
}

# A document with fewer usable characters than this is treated as empty.
MIN_DOCUMENT_CHARS: Final[int] = 40
# A PDF whose pages contain fewer characters than this per page is probably a
# scan / image-only export.
MIN_PDF_CHARS_PER_PAGE: Final[int] = 15

# Uploaded bytes are never written to disk when this is False.
PERSIST_UPLOADS: Final[bool] = os.getenv("PERSIST_UPLOADS", "false").lower() == "true"

# --------------------------------------------------------------------------- #
# Keyword matching
# --------------------------------------------------------------------------- #
# Aliases at or below this length only match when the original document shows
# them capitalised (protects "C" and "R" from matching ordinary prose).
SHORT_TOKEN_MAX_LEN: Final[int] = 2
# Fuzzy matching is only attempted for aliases at least this long.
FUZZY_MIN_ALIAS_LEN: Final[int] = 6
# RapidFuzz similarity (0-100) required before a fuzzy match is accepted.
FUZZY_SCORE_CUTOFF: Final[float] = 92.0
# Confidence attached to matches by method.
EXACT_MATCH_CONFIDENCE: Final[float] = 1.0
FUZZY_MATCH_CONFIDENCE: Final[float] = 0.75
# Maximum evidence snippets retained per matched skill.
MAX_EVIDENCE_PER_SKILL: Final[int] = 2
EVIDENCE_SNIPPET_MAX_CHARS: Final[int] = 240

# --------------------------------------------------------------------------- #
# Semantic matching
# --------------------------------------------------------------------------- #
EMBEDDING_MODEL_NAME: Final[str] = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
EMBEDDING_BATCH_SIZE: Final[int] = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))
# Set to "true" to skip the transformer entirely and use the lexical fallback.
FORCE_FALLBACK_EMBEDDINGS: Final[bool] = (
    os.getenv("FORCE_FALLBACK_EMBEDDINGS", "false").lower() == "true"
)

# Cosine similarity below SIM_FLOOR scores 0, at or above SIM_CEILING scores 100.
SIM_FLOOR: Final[float] = 0.18
SIM_CEILING: Final[float] = 0.62
# A requirement is considered supported by evidence at or above this similarity.
SEMANTIC_EVIDENCE_THRESHOLD: Final[float] = 0.35

# Relative weight of a requirement inside the semantic average, by importance.
REQUIREMENT_IMPORTANCE_WEIGHTS: Final[dict[str, float]] = {
    "required": 1.0,
    "responsibility": 0.8,
    "preferred": 0.5,
}

# Resume chunking.
CHUNK_MIN_WORDS: Final[int] = 5
CHUNK_MAX_WORDS: Final[int] = 45
MAX_CHUNKS_PER_RESUME: Final[int] = 400

# Whole-document similarity is reported as a diagnostic only and carries no
# weight in the final score.
REPORT_WHOLE_DOCUMENT_SIMILARITY: Final[bool] = True

# --------------------------------------------------------------------------- #
# Project / experience relevance
# --------------------------------------------------------------------------- #
# Split between "how well do project & experience chunks cover the JD
# responsibilities" and "how many required skills are demonstrated inside
# project or experience text rather than only listed in a skills block".
PROJECT_RESPONSIBILITY_WEIGHT: Final[float] = 0.70
PROJECT_SKILL_EVIDENCE_WEIGHT: Final[float] = 0.30
# Number of best-matching project/experience chunks averaged per requirement.
PROJECT_TOP_K_CHUNKS: Final[int] = 1
MAX_PROJECT_EVIDENCE_ITEMS: Final[int] = 5

# --------------------------------------------------------------------------- #
# Education
# --------------------------------------------------------------------------- #
EDUCATION_LEVEL_WEIGHT: Final[float] = 0.60
EDUCATION_FIELD_WEIGHT: Final[float] = 0.40
EDUCATION_FIELD_SIM_THRESHOLD: Final[float] = 0.42

DEGREE_LEVELS: Final[dict[str, int]] = {
    "certificate": 1,
    "diploma": 2,
    "associate": 3,
    "bachelor": 4,
    "master": 5,
    "mba": 5,
    "doctorate": 6,
}

# Surface forms that map onto a level key.
DEGREE_LEVEL_ALIASES: Final[dict[str, list[str]]] = {
    "certificate": ["certificate", "certificat"],
    "diploma": ["diploma", "polytechnic"],
    "associate": ["associate degree", "associate's degree", "foundation degree"],
    "bachelor": [
        "bachelor", "bachelors", "bachelor's", "b.tech", "btech", "b tech",
        "b.e.", "be degree", "b.sc", "bsc", "b.s.", "bs degree", "b.a.", "ba degree",
        "b.c.a", "bca", "b.com", "bcom", "undergraduate degree",
        "bachelor of engineering", "bachelor of science", "bachelor of technology",
    ],
    "master": [
        "master", "masters", "master's", "m.tech", "mtech", "m tech",
        "m.sc", "msc", "m.s.", "ms degree", "m.c.a", "mca", "m.com",
        "postgraduate degree", "master of science", "master of engineering",
        "master of technology", "master of computer applications",
    ],
    "mba": ["mba", "m.b.a", "master of business administration"],
    "doctorate": ["phd", "ph.d", "doctorate", "doctoral"],
}

# --------------------------------------------------------------------------- #
# Certifications
# --------------------------------------------------------------------------- #
CERTIFICATION_FUZZY_CUTOFF: Final[float] = 88.0

# --------------------------------------------------------------------------- #
# Soft skills
# --------------------------------------------------------------------------- #
# A soft skill only scores when a behavioural sentence supports it. A bare
# mention inside a comma separated skills list is not evidence.
SOFT_SKILL_SIM_THRESHOLD: Final[float] = 0.40
SOFT_SKILL_MIN_EVIDENCE_WORDS: Final[int] = 6
SOFT_SKILL_PARTIAL_CREDIT_FOR_MENTION: Final[float] = 0.0  # listing alone scores 0

# --------------------------------------------------------------------------- #
# Mandatory skill penalty
# --------------------------------------------------------------------------- #
# Applied identically to every candidate, always reported in the response.
MANDATORY_SKILL_PENALTY_ENABLED: Final[bool] = (
    os.getenv("MANDATORY_SKILL_PENALTY_ENABLED", "true").lower() == "true"
)
MANDATORY_SKILL_PENALTY_PER_SKILL: Final[float] = float(
    os.getenv("MANDATORY_SKILL_PENALTY_PER_SKILL", "2.0")
)
MANDATORY_SKILL_PENALTY_CAP: Final[float] = float(
    os.getenv("MANDATORY_SKILL_PENALTY_CAP", "10.0")
)

# --------------------------------------------------------------------------- #
# Explanations
# --------------------------------------------------------------------------- #
EXPLANATION_DETAILED_TOP_N: Final[int] = 3
MAX_SKILLS_IN_EXPLANATION: Final[int] = 6
MAX_SEMANTIC_ITEMS_IN_EXPLANATION: Final[int] = 3

# --------------------------------------------------------------------------- #
# Result cache (used only by /api/compare; holds derived scores, never files)
# --------------------------------------------------------------------------- #
RESULT_CACHE_SIZE: Final[int] = int(os.getenv("RESULT_CACHE_SIZE", "20"))

SCORE_MIN: Final[float] = 0.0
SCORE_MAX: Final[float] = 100.0


def clamp_score(value: float) -> float:
    """Clamp any component score into the 0-100 range."""
    if value != value:  # NaN guard
        return SCORE_MIN
    return max(SCORE_MIN, min(SCORE_MAX, float(value)))


# --------------------------------------------------------------------------- #
# Lexical fallback calibration
# --------------------------------------------------------------------------- #
# The lexical fallback produces a different similarity distribution from a
# sentence-transformer, so it gets its own floor/ceiling/threshold. Scores stay
# on the same 0-100 scale either way.
FALLBACK_SIM_FLOOR: Final[float] = 0.06
FALLBACK_SIM_CEILING: Final[float] = 0.45
FALLBACK_EVIDENCE_THRESHOLD: Final[float] = 0.18
FALLBACK_FEATURES: Final[int] = 2 ** 18
EMBEDDING_CACHE_SIZE: Final[int] = 50_000

# Credit awarded for a soft skill supported by a behavioural cue phrase versus
# one supported only by semantic similarity.
SOFT_SKILL_CUE_CREDIT: Final[float] = 1.0
SOFT_SKILL_SEMANTIC_CREDIT: Final[float] = 0.6
# A required skill only attracts a penalty when the JD marked it mandatory with
# an explicit indicator phrase (confidence at or above this value).
MANDATORY_CONFIDENCE_THRESHOLD: Final[float] = 0.90
# Partial credit when the candidate's highest degree is one level below the
# level requested by the JD.
EDUCATION_ONE_LEVEL_BELOW_CREDIT: Final[float] = 0.5
