from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig


CONFIG = AnalysisConfig.from_paths(ROOT)
OUT = ROOT / "outputs" / "manual_audit" / "direct_handoff_manual_audit.csv"


def main() -> None:
    episodes = pl.read_parquet(ROOT / "outputs" / "cache" / "direct_handoff_successors.parquet")
    ids = pl.concat(
        [
            episodes.select(pl.col("failed_id").alias("id")),
            episodes.select(pl.col("successor_id").alias("id")),
        ]
    ).unique()
    prs = (
        pl.scan_parquet(CONFIG.data_dir / "pull_request.parquet")
        .select("id", "title", "html_url")
        .join(ids.lazy(), on="id", how="inner")
        .collect(engine="streaming")
    )
    data = (
        episodes.join(
            prs.rename({"id": "failed_id", "title": "prior_title", "html_url": "prior_url"}),
            on="failed_id",
            how="left",
        )
        .join(
            prs.rename({"id": "successor_id", "title": "successor_title", "html_url": "successor_url"}),
            on="successor_id",
            how="left",
        )
        .to_pandas()
    )
    data["path_type"] = data["shared_non_generic_files"].gt(0).map(
        {True: "non_generic", False: "generic_only"}
    )
    pieces = []
    for (_, _), cell in data.groupby(["transition_mode", "path_type"]):
        pieces.append(cell.sample(min(15, len(cell)), random_state=20260825))
    audit = pd.concat(pieces, ignore_index=True).sort_values(
        ["transition_mode", "path_type", "failed_id"]
    )
    columns = [
        "failed_id",
        "successor_id",
        "repo_url",
        "transition_mode",
        "prior_agent",
        "current_agent",
        "same_contributor",
        "changed_agent",
        "days_to_successor",
        "shared_files",
        "shared_non_generic_files",
        "example_shared_file",
        "recovered_within_30d",
        "failed_prs_per_successor",
        "prior_title",
        "successor_title",
        "prior_url",
        "successor_url",
        "path_type",
    ]
    audit = audit[columns]
    audit["manual_same_task"] = ""
    audit["manual_intentional_handoff"] = ""
    audit["manual_confidence"] = ""
    audit["manual_note"] = ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUT, index=False)
    print(f"Wrote {len(audit)} stratified rows to {OUT}")


if __name__ == "__main__":
    main()
