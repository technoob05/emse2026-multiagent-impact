from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from multiagent_impact.contributor_analysis import add_transition_taxonomy
from multiagent_impact.pipeline import (
    add_time_columns,
    build_event_study,
    build_latest_resolved_transitions,
)


def test_latest_resolved_transition_excludes_overlapping_pr() -> None:
    raw = pl.DataFrame(
        {
            "id": [1, 2, 3],
            "repo_url": ["repo", "repo", "repo"],
            "agent": ["A", "B", "C"],
            "created_at": [
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-04T00:00:00Z",
            ],
            "closed_at": [
                "2026-01-03T00:00:00Z",
                "2026-01-10T00:00:00Z",
                "2026-01-05T00:00:00Z",
            ],
            "merged_at": [
                "2026-01-03T00:00:00Z",
                None,
                None,
            ],
            "user_id": [11, 12, 13],
        }
    )
    base = add_time_columns(raw.lazy()).collect()
    repo_summary = pl.DataFrame(
        {"repo_url": ["repo"], "n_agents": [3], "repo_prs": [3]}
    )
    transitions = build_latest_resolved_transitions(
        base.lazy(), repo_summary.lazy()
    ).collect()
    row = transitions.filter(pl.col("id") == 3).row(0, named=True)
    assert row["prior_id"] == 1
    assert row["prior_agent"] == "A"
    assert row["switched"] is True


def test_project_default_data_path_is_external() -> None:
    project = Path("D:/workspace/emse2026-multiagent-impact")
    expected = Path("D:/workspace/Legacy/AI_Dev_Dataminning/AIDev-7.6M")
    assert project.parent / "Legacy/AI_Dev_Dataminning/AIDev-7.6M" == expected


def test_event_study_retains_pre_transition_rows() -> None:
    base = pl.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "repo_url": ["repo"] * 5,
            "agent": ["A", "A", "B", "A", "B"],
            "created_dt": pl.datetime_range(
                start=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end=datetime(2025, 1, 5, tzinfo=timezone.utc),
                interval="1d",
                eager=True,
            ),
            "closed_dt": pl.datetime_range(
                start=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
                end=datetime(2025, 1, 5, 1, tzinfo=timezone.utc),
                interval="1d",
                eager=True,
            ),
            "merged_dt": [
                datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
                None,
                datetime(2025, 1, 3, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 4, 1, tzinfo=timezone.utc),
                None,
            ],
            "merged": [True, False, True, True, False],
        }
    ).lazy()
    repo_summary = pl.DataFrame({"repo_url": ["repo"], "n_agents": [2]}).lazy()

    event, _ = build_event_study(base, repo_summary, window=2)

    assert event["event_index"].to_list() == [-2, -1, 0, 1, 2]


def test_contributor_transition_taxonomy_is_exhaustive() -> None:
    frame = pl.DataFrame(
        {
            "same_user": [True, True, False, False],
            "switched": [False, True, False, True],
        }
    ).lazy()
    observed = add_transition_taxonomy(frame).collect()["transition_type"].to_list()
    assert observed == [
        "persistence",
        "brand_change_same_contributor",
        "contributor_change_stable_agent",
        "joint_reconfiguration",
    ]
