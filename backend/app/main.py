"""Application entry point.

Run with:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import APP_NAME, APP_VERSION, CORS_ORIGINS, LOG_LEVEL
from app.services.document_parser import DocumentParseError
from app.services.keyword_matcher import get_taxonomy
from app.services.semantic_matcher import get_semantic_engine

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the taxonomy and embedding model once, before serving traffic."""
    taxonomy = get_taxonomy()
    engine = get_semantic_engine()
    logger.info(
        "%s v%s ready — taxonomy v%s, embeddings via %s (%s)",
        APP_NAME, APP_VERSION, taxonomy.version, engine.backend, engine.model_name,
    )
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Ranks resumes against a job description using deterministic keyword "
        "matching and requirement-level semantic matching. No language model "
        "produces or influences any score."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(DocumentParseError)
async def document_parse_error_handler(_: Request, exc: DocumentParseError) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"detail": exc.message, "reason_code": exc.reason_code}
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
