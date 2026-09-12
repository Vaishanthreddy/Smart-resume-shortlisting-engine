"""Explicit keyword and skill matching.

Matching is alias-driven, case-insensitive, whitespace/punctuation tolerant and
protected against short-token false positives. Results are keyed by canonical
skill, so repeating a keyword twenty times ("keyword stuffing") produces exactly
the same match set as mentioning it once.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from app.config import (
    EVIDENCE_SNIPPET_MAX_CHARS,
    EXACT_MATCH_CONFIDENCE,
    FUZZY_MATCH_CONFIDENCE,
    FUZZY_MIN_ALIAS_LEN,
    FUZZY_SCORE_CUTOFF,
    MAX_EVIDENCE_PER_SKILL,
    SHORT_TOKEN_MAX_LEN,
    SKILL_TAXONOMY_PATH,
)
from app.services.text_cleaner import snippet

logger = logging.getLogger(__name__)

_TOKEN_SPLIT_RE = re.compile(r"[^a-zA-Z0-9+#]+")
_SEPARATOR = r"[\s._\-/\\]*"
_WORD_RE = re.compile(r"[A-Za-z0-9+#.]+")


@dataclass
class KeywordMatch:
    """One canonical keyword found in a document."""

    name: str
    category: str = ""
    matched_aliases: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    method: str = "exact"
    confidence: float = EXACT_MATCH_CONFIDENCE
    occurrences: int = 0

    def add_evidence(self, text: str) -> None:
        if len(self.evidence) >= MAX_EVIDENCE_PER_SKILL:
            return
        cleaned = snippet(text, EVIDENCE_SNIPPET_MAX_CHARS)
        if cleaned and cleaned not in self.evidence:
            self.evidence.append(cleaned)


def _alias_tokens(alias: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(alias.lower()) if token]


def _compile_alias(alias: str) -> re.Pattern[str] | None:
    tokens = _alias_tokens(alias)
    if not tokens:
        return None
    body = _SEPARATOR.join(re.escape(token) for token in tokens)
    pattern = rf"(?<![A-Za-z0-9+#]){body}(?![A-Za-z0-9+#])"
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:  # pragma: no cover - defensive
        logger.warning("Could not compile alias pattern for %r", alias)
        return None


def _alias_length(alias: str) -> int:
    return sum(len(token) for token in _alias_tokens(alias))


class AliasMatcher:
    """Finds canonical terms in free text via their aliases."""

    def __init__(
        self,
        mapping: Mapping[str, Iterable[str]],
        *,
        categories: Mapping[str, str] | None = None,
        ambiguous_contexts: Mapping[str, list[str]] | None = None,
        enable_fuzzy: bool = True,
    ) -> None:
        self.categories = dict(categories or {})
        self.ambiguous_contexts = {
            key.lower(): [ctx.lower() for ctx in values]
            for key, values in (ambiguous_contexts or {}).items()
        }
        self.enable_fuzzy = enable_fuzzy

        self._patterns: dict[str, list[tuple[str, re.Pattern[str], bool]]] = {}
        self._fuzzy_alias_to_canonical: dict[str, str] = {}

        for canonical, aliases in mapping.items():
            compiled: list[tuple[str, re.Pattern[str], bool]] = []
            for alias in aliases:
                pattern = _compile_alias(alias)
                if pattern is None:
                    continue
                is_short = _alias_length(alias) <= SHORT_TOKEN_MAX_LEN
                compiled.append((alias, pattern, is_short))
                if len(alias) >= FUZZY_MIN_ALIAS_LEN:
                    self._fuzzy_alias_to_canonical.setdefault(alias.lower(), canonical)
            if compiled:
                self._patterns[canonical] = compiled

        self._fuzzy_aliases: list[str] = sorted(self._fuzzy_alias_to_canonical)

    @property
    def canonical_terms(self) -> list[str]:
        return sorted(self._patterns)

    # ---------------------------------------------------------------- matching
    def _short_token_is_valid(self, canonical: str, line: str, match: re.Match[str]) -> bool:
        """Guard against 'C' or 'R' matching ordinary prose.

        A one or two character skill only counts when it appears capitalised in
        the source document, and never inside a known ambiguous phrase.
        """
        matched_text = match.group(0)
        if not any(char.isupper() for char in matched_text):
            return False

        blocked = self.ambiguous_contexts.get(canonical.lower(), [])
        if blocked:
            start = max(0, match.start() - 12)
            end = min(len(line), match.end() + 12)
            window = line[start:end].lower()
            if any(phrase in window for phrase in blocked):
                return False
        return True

    def find(
        self,
        text: str,
        *,
        restrict: Iterable[str] | None = None,
        use_fuzzy: bool | None = None,
    ) -> dict[str, KeywordMatch]:
        """Return canonical term -> match for every term found in `text`."""
        if not text:
            return {}

        allowed = set(restrict) if restrict is not None else None
        results: dict[str, KeywordMatch] = {}
        lines = [line for line in text.split("\n") if line.strip()]

        for canonical, aliases in self._patterns.items():
            if allowed is not None and canonical not in allowed:
                continue
            for line in lines:
                for alias, pattern, is_short in aliases:
                    for match in pattern.finditer(line):
                        if is_short and not self._short_token_is_valid(canonical, line, match):
                            continue
                        entry = results.get(canonical)
                        if entry is None:
                            entry = KeywordMatch(
                                name=canonical,
                                category=self.categories.get(canonical, ""),
                                method="exact",
                                confidence=EXACT_MATCH_CONFIDENCE,
                            )
                            results[canonical] = entry
                        if alias not in entry.matched_aliases:
                            entry.matched_aliases.append(alias)
                        entry.occurrences += 1
                        entry.add_evidence(line)

        should_fuzzy = self.enable_fuzzy if use_fuzzy is None else use_fuzzy
        if should_fuzzy:
            self._fuzzy_pass(lines, results, allowed)

        return results

    def _fuzzy_pass(
        self,
        lines: list[str],
        results: dict[str, KeywordMatch],
        allowed: set[str] | None,
    ) -> None:
        """Conservative typo tolerance for longer aliases only."""
        try:
            from rapidfuzz import fuzz, process
        except ImportError:  # pragma: no cover - optional at runtime
            return

        targets = [
            alias
            for alias in self._fuzzy_aliases
            if allowed is None or self._fuzzy_alias_to_canonical[alias] in allowed
        ]
        if not targets:
            return

        ngrams: dict[str, str] = {}
        for line in lines:
            words = _WORD_RE.findall(line)
            for size in (1, 2, 3):
                for index in range(len(words) - size + 1):
                    phrase = " ".join(words[index : index + size])
                    if len(phrase) < FUZZY_MIN_ALIAS_LEN:
                        continue
                    ngrams.setdefault(phrase.lower(), line)

        if not ngrams:
            return

        queries = list(ngrams)
        matrix = process.cdist(
            queries, targets, scorer=fuzz.ratio, score_cutoff=FUZZY_SCORE_CUTOFF
        )

        for row, query in enumerate(queries):
            best_index = int(matrix[row].argmax())
            score = float(matrix[row][best_index])
            if score < FUZZY_SCORE_CUTOFF:
                continue
            alias = targets[best_index]
            canonical = self._fuzzy_alias_to_canonical[alias]
            if canonical in results:  # an exact match already proves the skill
                continue
            entry = results.get(canonical)
            if entry is None:
                entry = KeywordMatch(
                    name=canonical,
                    category=self.categories.get(canonical, ""),
                    method="fuzzy",
                    confidence=FUZZY_MATCH_CONFIDENCE,
                )
                results[canonical] = entry
            if alias not in entry.matched_aliases:
                entry.matched_aliases.append(alias)
            entry.occurrences += 1
            entry.add_evidence(ngrams[query])


@dataclass
class SoftSkillDefinition:
    name: str
    aliases: list[str]
    descriptor: str
    evidence_cues: list[str]


class SkillTaxonomy:
    """Loaded taxonomy plus the matchers built from it."""

    def __init__(self, payload: dict) -> None:
        self.version: str = payload.get("version", "unknown")
        self.raw = payload

        skill_map: dict[str, list[str]] = {}
        categories: dict[str, str] = {}
        for category, skills in payload.get("categories", {}).items():
            for canonical, aliases in skills.items():
                skill_map.setdefault(canonical, [])
                for alias in aliases:
                    if alias not in skill_map[canonical]:
                        skill_map[canonical].append(alias)
                if canonical not in skill_map[canonical]:
                    skill_map[canonical].append(canonical)
                categories[canonical] = category

        self.skill_categories = categories
        self.skill_matcher = AliasMatcher(
            skill_map,
            categories=categories,
            ambiguous_contexts=payload.get("ambiguous_short_skills", {}),
        )

        self.soft_skills: dict[str, SoftSkillDefinition] = {}
        soft_map: dict[str, list[str]] = {}
        for name, spec in payload.get("soft_skills", {}).items():
            definition = SoftSkillDefinition(
                name=name,
                aliases=list(spec.get("aliases", [name])),
                descriptor=spec.get("descriptor", name),
                evidence_cues=[cue.lower() for cue in spec.get("evidence_cues", [])],
            )
            self.soft_skills[name] = definition
            soft_map[name] = definition.aliases + [name]
        self.soft_skill_matcher = AliasMatcher(soft_map, enable_fuzzy=False)

        cert_map = {
            name: list(aliases) + [name]
            for name, aliases in payload.get("certifications", {}).items()
        }
        self.certifications = cert_map
        self.certification_matcher = AliasMatcher(cert_map, enable_fuzzy=False)

    # ------------------------------------------------------------------ helpers
    def category_of(self, skill: str) -> str:
        return self.skill_categories.get(skill, "")

    def find_skills(self, text: str, **kwargs) -> dict[str, KeywordMatch]:
        return self.skill_matcher.find(text, **kwargs)

    def find_soft_skills(self, text: str, **kwargs) -> dict[str, KeywordMatch]:
        return self.soft_skill_matcher.find(text, **kwargs)

    def find_certifications(self, text: str, **kwargs) -> dict[str, KeywordMatch]:
        return self.certification_matcher.find(text, **kwargs)


@functools.lru_cache(maxsize=1)
def get_taxonomy(path: str | None = None) -> SkillTaxonomy:
    """Load and cache the skill taxonomy."""
    taxonomy_path = path or str(SKILL_TAXONOMY_PATH)
    with open(taxonomy_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    taxonomy = SkillTaxonomy(payload)
    logger.info(
        "Loaded skill taxonomy v%s: %d skills, %d soft skills, %d certifications",
        taxonomy.version,
        len(taxonomy.skill_categories),
        len(taxonomy.soft_skills),
        len(taxonomy.certifications),
    )
    return taxonomy


def dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
