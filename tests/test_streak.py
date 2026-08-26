from __future__ import annotations

import polars as pl

from multiagent_impact.streak_analysis import (
    build_decision_chains,
    build_resolved_events,
    prepare_pull_requests,
    validate_temporal_invariants,
)


def _prepared(rows: list[dict[str, object]]) -> pl.LazyFrame:
    raw = pl.DataFrame(rows).with_columns(
        pl.col("created_at").cast(pl.String),
        pl.col("closed_at").cast(pl.String),
        pl.col("merged_at").cast(pl.String),
    )
    return prepare_pull_requests(raw.lazy())


def test_known_time_uses_later_of_close_and_merge() -> None:
    base = _prepared(
        [
            {
                "id": 1,
                "repo_url": "repo",
                "agent": "A",
                "user_id": 1,
                "created_at": "2025-01-01T00:00:00Z",
                "closed_at": "2025-01-02T00:00:00Z",
                "merged_at": "2025-01-05T00:00:00Z",
            }
        ]
    )
    row = build_resolved_events(base).collect().row(0, named=True)
    assert row["known_dt"].day == 5
    assert row["was_merged"] is True


def test_decision_chain_is_non_overlapping_and_keeps_first_current() -> None:
    base = _prepared(
        [
            {
                "id": 9,
                "repo_url": "repo",
                "agent": "A",
                "user_id": 10,
                "created_at": "2024-12-28T00:00:00Z",
                "closed_at": "2024-12-30T00:00:00Z",
                "merged_at": "2024-12-30T00:00:00Z",
            },
            {
                "id": 10,
                "repo_url": "repo",
                "agent": "A",
                "user_id": 10,
                "created_at": "2025-01-01T00:00:00Z",
                "closed_at": "2025-01-02T00:00:00Z",
                "merged_at": None,
            },
            {
                "id": 11,
                "repo_url": "repo",
                "agent": "A",
                "user_id": 10,
                "created_at": "2025-01-03T00:00:00Z",
                "closed_at": "2025-01-04T00:00:00Z",
                "merged_at": None,
            },
            # Open when id=13 starts, so it must not become p1.
            {
                "id": 12,
                "repo_url": "repo",
                "agent": "A",
                "user_id": 10,
                "created_at": "2025-01-03T12:00:00Z",
                "closed_at": "2025-01-10T00:00:00Z",
                "merged_at": None,
            },
            {
                "id": 13,
                "repo_url": "repo",
                "agent": "B",
                "user_id": 20,
                "created_at": "2025-01-05T00:00:00Z",
                "closed_at": "2025-01-06T00:00:00Z",
                "merged_at": "2025-01-06T00:00:00Z",
            },
            # Shares p1=11 and must be removed by first-current-per-p1.
            {
                "id": 14,
                "repo_url": "repo",
                "agent": "B",
                "user_id": 20,
                "created_at": "2025-01-05T12:00:00Z",
                "closed_at": "2025-01-07T00:00:00Z",
                "merged_at": "2025-01-07T00:00:00Z",
            },
        ]
    )
    observed = build_decision_chains(base).collect()
    row = observed.filter(pl.col("id") == 13).row(0, named=True)
    assert row["p1_id"] == 11
    assert row["p2_id"] == 10
    assert row["p3_id"] == 9
    assert row["nonintegration_streak"] == "2"
    assert row["switched"] is True
    assert 14 not in observed["id"].to_list()
    assert validate_temporal_invariants(observed) == {
        "p1_not_strictly_before_current": 0,
        "p2_not_strictly_before_p1": 0,
        "p3_not_strictly_before_p2": 0,
        "duplicate_current_id": 0,
        "duplicate_p1_id": 0,
        "pre_onset_current": 0,
    }


def test_tied_resolution_times_are_excluded() -> None:
    base = _prepared(
        [
            {
                "id": 1,
                "repo_url": "tied",
                "agent": "A",
                "user_id": 1,
                "created_at": "2024-12-29T00:00:00Z",
                "closed_at": "2025-01-01T00:00:00Z",
                "merged_at": None,
            },
            {
                "id": 2,
                "repo_url": "tied",
                "agent": "A",
                "user_id": 1,
                "created_at": "2025-01-01T06:00:00Z",
                "closed_at": "2025-01-02T00:00:00Z",
                "merged_at": None,
            },
            {
                "id": 3,
                "repo_url": "tied",
                "agent": "A",
                "user_id": 1,
                "created_at": "2025-01-01T12:00:00Z",
                "closed_at": "2025-01-02T00:00:00Z",
                "merged_at": None,
            },
            {
                "id": 4,
                "repo_url": "tied",
                "agent": "B",
                "user_id": 2,
                "created_at": "2025-01-03T00:00:00Z",
                "closed_at": "2025-01-04T00:00:00Z",
                "merged_at": None,
            },
        ]
    )
    resolved_ids = build_resolved_events(base).collect()["id"].to_list()
    assert resolved_ids == [1, 4]
    observed = build_decision_chains(base).collect()
    assert observed.row(0, named=True)["p1_id"] == 1
    assert observed.row(0, named=True)["nonintegration_streak"] == "left-censored-1+"
