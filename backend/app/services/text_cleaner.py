"""Text normalisation, sentence splitting and chunking.

Deliberately conservative: cleaning never removes content, it only regularises
whitespace, bullets and unicode look-alikes. A badly formatted resume must end
up with the same *content* as a well formatted one so that formatting alone
cannot change a candidate's score.
"""

from __future__ import annotations

import re
import unicodedata

from app.config import CHUNK_MAX_WORDS, CHUNK_MIN_WORDS, MAX_CHUNKS_PER_RESUME

# Characters that PDF extraction commonly emits for bullets and dashes.
_BULLET_CHARS = "•◦▪▫●○∙·‣⁃➢➤*"
_BULLET_RE = re.compile(rf"^[\s{re.escape(_BULLET_CHARS)}\-–—]+")
_MULTI_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
    "\ufb04": "ffl", "\u2018": "'", "\u2019": "'", "\u201c": '"',
    "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "...",
    "\u00ad": "", "\u200b": "", "\ufeff": "",
}

# Sentence boundary: terminal punctuation followed by whitespace + capital/digit.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])")

# Abbreviations that must not end a sentence.
_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "inc", "ltd", "co", "dr", "mr", "mrs", "ms",
    "sr", "jr", "st", "approx", "dept", "univ", "b.tech", "m.tech", "b.e",
    "m.e", "b.sc", "m.sc", "ph.d", "u.s", "u.k",
}


def normalize_unicode(text: str) -> str:
    """Fold ligatures, smart quotes and control characters into plain ASCII-ish text."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for source, replacement in _LIGATURES.items():
        text = text.replace(source, replacement)
    return _CONTROL_RE.sub(" ", text)


def clean_text(text: str) -> str:
    """Normalise a whole document while preserving line structure."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = _MULTI_SPACE_RE.sub(" ", raw_line).strip()
        # Strip leading bullet glyphs but keep the text that follows.
        stripped = _BULLET_RE.sub("", line).strip()
        lines.append(stripped if stripped else "")

    joined = "\n".join(lines)
    return _MULTI_NEWLINE_RE.sub("\n\n", joined).strip()


def _looks_like_abbreviation(fragment: str) -> bool:
    tail = fragment.rstrip().rstrip(".").split()[-1].lower() if fragment.strip() else ""
    return tail in _ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, treating each line break as a soft boundary.

    Resumes are mostly bullet lists rather than prose, so every line is treated
    as at least one unit and long lines are split further on punctuation.
    """
    if not text:
        return []

    sentences: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = _SENTENCE_SPLIT_RE.split(line)
        buffer = ""
        for part in parts:
            candidate = f"{buffer} {part}".strip() if buffer else part.strip()
            if _looks_like_abbreviation(candidate):
                buffer = candidate
                continue
            buffer = ""
            if candidate:
                sentences.append(candidate)
        if buffer:
            sentences.append(buffer)
    return [s.strip() for s in sentences if s.strip()]


def word_count(text: str) -> int:
    return len(text.split())


def chunk_text(
    text: str,
    min_words: int = CHUNK_MIN_WORDS,
    max_words: int = CHUNK_MAX_WORDS,
    max_chunks: int = MAX_CHUNKS_PER_RESUME,
) -> list[str]:
    """Turn text into bounded chunks suitable for embedding.

    Short fragments are merged with the following fragment so that a heading or
    a two-word bullet does not become a meaningless embedding, and over-long
    lines are split on word boundaries.
    """
    sentences = split_sentences(text)
    chunks: list[str] = []
    buffer = ""

    for sentence in sentences:
        words = sentence.split()
        if len(words) > max_words:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            for start in range(0, len(words), max_words):
                piece = " ".join(words[start : start + max_words])
                if word_count(piece) >= min_words:
                    chunks.append(piece)
                elif chunks:
                    chunks[-1] = f"{chunks[-1]} {piece}".strip()
            continue

        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if word_count(candidate) < min_words:
            buffer = candidate
            continue
        if word_count(candidate) <= max_words:
            chunks.append(candidate)
            buffer = ""
        else:
            if buffer:
                chunks.append(buffer)
            buffer = sentence

    if buffer:
        if word_count(buffer) >= min_words or not chunks:
            chunks.append(buffer)
        else:
            chunks[-1] = f"{chunks[-1]} {buffer}".strip()

    # Deduplicate while preserving order — repeated boilerplate lines should not
    # give a candidate extra chances to match.
    seen: set[str] = set()
    unique: list[str] = []
    for chunk in chunks:
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
        if len(unique) >= max_chunks:
            break
    return unique


def snippet(text: str, max_chars: int) -> str:
    """Trim an evidence snippet to a readable length on a word boundary."""
    text = _MULTI_SPACE_RE.sub(" ", text.replace("\n", " ")).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut.rstrip('.,;:')}…"
