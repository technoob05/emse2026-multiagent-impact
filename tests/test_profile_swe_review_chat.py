from __future__ import annotations

from scripts.audit.profile_swe_review_chat import (
    mapped_product,
    normalize_pr_number,
    normalize_repo,
)


def test_normalize_repo_accepts_supported_github_forms() -> None:
    expected = "owner/repo"
    assert normalize_repo("https://api.github.com/repos/Owner/Repo") == expected
    assert normalize_repo("https://github.com/Owner/Repo/") == expected
    assert normalize_repo("git@github.com:Owner/Repo.git") == expected
    assert normalize_repo("Owner/Repo?tab=readme#top") == expected


def test_normalize_repo_rejects_incomplete_or_non_repo_values() -> None:
    assert normalize_repo(None) is None
    assert normalize_repo("") is None
    assert normalize_repo("owner") is None
    assert normalize_repo("https://example.com/owner/repo") is None


def test_positive_pr_number_normalization() -> None:
    assert normalize_pr_number("42") == 42
    assert normalize_pr_number(42.0) == 42
    assert normalize_pr_number(0) is None
    assert normalize_pr_number("not-a-number") is None


def test_product_mapping_is_exact_and_case_insensitive() -> None:
    assert mapped_product("Claude[bot]") == "Claude_Code"
    assert mapped_product("copilot-pull-request-reviewer[bot]") == "Copilot"
    assert mapped_product("coderabbitai[bot]") is None
    assert mapped_product(None) is None
