"""Alias matching, short-token safety, deduplication and stuffing resistance."""

from __future__ import annotations

from app.services.keyword_matcher import AliasMatcher, get_taxonomy


def test_aliases_resolve_to_the_same_canonical_skill(taxonomy) -> None:
    for text in ("I use React.js daily", "reactjs developer", "Built with React"):
        assert "react" in taxonomy.find_skills(text), text

    assert "node.js" in taxonomy.find_skills("Backend in NodeJS and Express")
    assert "node.js" in taxonomy.find_skills("Backend in node js")
    assert "aws" in taxonomy.find_skills("Deployed on Amazon Web Services")
    assert "rest api" in taxonomy.find_skills("Designed RESTful APIs for partners")
    assert "javascript" in taxonomy.find_skills("Strong JS and ECMAScript knowledge")


def test_matching_is_case_insensitive(taxonomy) -> None:
    lower = taxonomy.find_skills("python and postgresql")
    upper = taxonomy.find_skills("PYTHON AND POSTGRESQL")
    assert set(lower) == set(upper) == {"python", "postgresql"}


def test_short_tokens_do_not_match_arbitrary_words(taxonomy) -> None:
    """The skill 'C' must not match words that merely contain the letter c."""
    text = "Excellent communication and a customer centric approach to coaching."
    assert "c" not in taxonomy.find_skills(text)
    assert "r" not in taxonomy.find_skills(text)
    assert "go" not in taxonomy.find_skills("Ready to go the extra mile for good outcomes")


def test_short_tokens_still_match_when_genuinely_listed(taxonomy) -> None:
    found = taxonomy.find_skills("Languages: C, Java, Python")
    assert "c" in found
    assert "java" in found


def test_c_does_not_match_inside_cpp(taxonomy) -> None:
    found = taxonomy.find_skills("Systems programming in C++ only")
    assert "c++" in found
    assert "c" not in found


def test_ambiguous_short_skill_context_is_blocked(taxonomy) -> None:
    assert "r" not in taxonomy.find_skills("Worked in the R&D department for two years")


def test_repeated_mentions_do_not_create_duplicates(taxonomy) -> None:
    found = taxonomy.find_skills("Python. Python! python, PYTHON; Python")
    assert list(found) == ["python"]
    assert found["python"].occurrences > 1  # counted, but not scored


def test_keyword_stuffing_produces_the_same_match_set(taxonomy) -> None:
    honest = "Skills: Python, SQL, Docker"
    stuffed = "Skills: " + ", ".join(["Python", "SQL", "Docker"] * 40)
    assert set(taxonomy.find_skills(honest)) == set(taxonomy.find_skills(stuffed))


def test_evidence_is_captured_and_bounded(taxonomy) -> None:
    from app.config import MAX_EVIDENCE_PER_SKILL

    text = "\n".join(f"Line {index}: used Django in production" for index in range(10))
    match = taxonomy.find_skills(text)["django"]
    assert match.evidence
    assert len(match.evidence) <= MAX_EVIDENCE_PER_SKILL
    assert "Django" in match.evidence[0]


def test_restrict_limits_the_search_space(taxonomy) -> None:
    found = taxonomy.find_skills("Python, Docker, Kubernetes", restrict=["docker"])
    assert set(found) == {"docker"}


def test_fuzzy_matching_is_conservative() -> None:
    matcher = AliasMatcher({"kubernetes": ["kubernetes"], "javascript": ["javascript"]})
    # A single-character typo is tolerated.
    assert "kubernetes" in matcher.find("Deployed with kubernets clusters")
    # An unrelated word is not.
    assert matcher.find("We enjoy gardening and carpentry") == {}


def test_fuzzy_does_not_override_an_exact_match(taxonomy) -> None:
    found = taxonomy.find_skills("Experienced with Kubernetes orchestration")
    assert found["kubernetes"].method == "exact"


def test_soft_skill_and_certification_indexes_load(taxonomy) -> None:
    assert "teamwork" in taxonomy.find_soft_skills("Strong teamwork and collaboration")
    assert "aws certified developer" in taxonomy.find_certifications(
        "AWS Certified Developer - Associate, 2023"
    )


def test_taxonomy_is_cached() -> None:
    assert get_taxonomy() is get_taxonomy()
