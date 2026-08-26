from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from scripts.analysis.run_cross_corpus_attribution_sensitivity import (
    build_overlap,
    fit_lpm,
    load_a2a_pairs,
)


def test_a2a_cross_loader_deduplicates_and_normalizes(tmp_path: Path) -> None:
    path = tmp_path / "cross.parquet"
    pl.DataFrame(
        {
            "repo_name": ["Org/Repo", "org/repo"],
            "pr_number": [7, 7],
            "author_agent": ["Codex", "Codex"],
            "reviewer_agent": ["Copilot", "Copilot"],
            "first_review_at": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ],
        }
    ).with_columns(pl.col("first_review_at").str.to_datetime(time_zone="UTC")).write_parquet(path)

    pairs, prs = load_a2a_pairs(path)
    assert pairs.height == 1
    assert prs.height == 1
    assert pairs["repo_name"].item() == "org/repo"


def test_overlap_preserves_landmark_grain(tmp_path: Path) -> None:
    edge_path = tmp_path / "edge.parquet"
    edge = pl.DataFrame(
        {
            "pr_id": [1, 2],
            "author_agent": ["Codex", "Codex"],
            "trigger_reviewer_agent": ["Copilot", "Copilot"],
            "trigger_dt": [
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
            ],
        }
    ).with_columns(pl.col("trigger_dt").str.to_datetime(time_zone="UTC"))
    edge.write_parquet(edge_path)
    pr_map = pl.DataFrame(
        {
            "pr_id": [1, 2],
            "repo_name": ["org/repo", "org/other"],
            "pr_number": [7, 8],
        }
    )
    pairs = pl.DataFrame(
        {
            "repo_name": ["org/repo"],
            "pr_number": [7],
            "author_agent": ["Codex"],
            "reviewer_agent": ["Copilot"],
            "first_review_at": ["2026-01-01T00:03:00Z"],
            "a2a_exact_pair": [True],
        }
    ).with_columns(pl.col("first_review_at").str.to_datetime(time_zone="UTC"))
    cross_prs = pairs.select("repo_name", "pr_number").with_columns(
        pl.lit(True).alias("a2a_cross_pr")
    )

    result = build_overlap(edge_path, pr_map, pairs, cross_prs)
    assert result.height == 2
    assert result["a2a_exact_pair"].to_list() == [True, False]
    assert abs(result["a2a_minus_aidev_trigger_hours"][0] - 0.05) < 1e-9


def test_unadjusted_lpm_uses_true_as_the_positive_outcome() -> None:
    frame = pd.DataFrame(
        {
            "exact_parent_reply_by_48h": [False, False, False, False, True, True, True, True],
            "merged_from_48h_to_30d": [False, False, False, True, False, True, True, True],
            "repo_id": [1, 1, 2, 2, 3, 3, 4, 4],
        }
    )
    result = fit_lpm(frame, "unadjusted")
    assert abs(result["estimate"] - 0.5) < 1e-9
