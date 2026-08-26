from datetime import datetime, timezone

import pandas as pd
import polars as pl

from multiagent_impact.direct_handoff import build_direct_successors


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_direct_successor_starts_after_failure_and_reuses_path() -> None:
    prs = pl.DataFrame(
        {
            "pr_id": [1, 2, 3, 4],
            "repo_id": [10, 10, 10, 10],
            "repo_url": ["repo"] * 4,
            "agent": ["A", "B", "C", "B"],
            "user_id": [100, 100, 200, 100],
            "created_dt": [utc("2026-01-01T00:00:00"), utc("2026-01-03T00:00:00"), utc("2026-01-04T00:00:00"), utc("2026-01-05T00:00:00")],
            "closed_dt": [utc("2026-01-02T00:00:00"), utc("2026-01-04T00:00:00"), utc("2026-01-06T00:00:00"), utc("2026-01-07T00:00:00")],
            "merged_dt": [None, utc("2026-01-03T12:00:00"), None, utc("2026-01-06T00:00:00")],
        },
        schema_overrides={"merged_dt": pl.Datetime(time_zone="UTC")},
    )
    files = pl.DataFrame({"pr_id": [1, 1, 2, 3, 4], "filename": ["src/a.py", "README.md", "src/a.py", "src/b.py", "README.md"]})
    _, successors, quality = build_direct_successors(
        prs, files, cutoff=pd.Timestamp("2026-02-01", tz="UTC")
    )
    first = successors.filter(pl.col("failed_id") == 1).row(0, named=True)
    assert first["successor_id"] == 2
    assert first["shared_files"] == 1
    assert first["same_contributor"] is True
    assert first["changed_agent"] is True
    assert first["recovered_within_30d"] is True
    assert quality["eligible_closed_unmerged_prs"] == 2


def test_successor_outside_window_is_not_counted() -> None:
    prs = pl.DataFrame(
        {
            "pr_id": [1, 2],
            "repo_id": [10, 10],
            "repo_url": ["repo", "repo"],
            "agent": ["A", "B"],
            "user_id": [100, 200],
            "created_dt": [utc("2026-01-01T00:00:00"), utc("2026-03-10T00:00:00")],
            "closed_dt": [utc("2026-01-02T00:00:00"), utc("2026-03-11T00:00:00")],
            "merged_dt": [None, None],
        },
        schema_overrides={"merged_dt": pl.Datetime(time_zone="UTC")},
    )
    files = pl.DataFrame({"pr_id": [1, 2], "filename": ["src/a.py", "src/a.py"]})
    index, successors, _ = build_direct_successors(
        prs, files, cutoff=pd.Timestamp("2026-02-01", tz="UTC")
    )
    assert successors.is_empty()
    assert index["has_successor_30d"].to_list() == [False]
