from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "outputs" / "tables"
CACHE = ROOT / "outputs" / "cache"


def main() -> None:
    quality = pd.read_csv(TABLES / "direct_handoff_quality.csv").iloc[0]
    composition = pd.read_csv(TABLES / "direct_handoff_composition.csv")
    contrasts = pd.read_csv(TABLES / "direct_handoff_clustered_contrasts.csv")
    within = pd.read_csv(TABLES / "direct_handoff_within_context.csv")
    sensitivity = pd.read_csv(TABLES / "direct_handoff_sensitivity.csv")
    episodes = pl.read_parquet(CACHE / "direct_handoff_successors.parquet")

    checks = {
        "successors_do_not_exceed_eligible": int(quality.successors_within_30d) <= int(quality.eligible_closed_unmerged_prs),
        "composition_reconciles": int(composition["n"].sum()) == int(quality.successors_within_30d),
        "four_transition_modes": composition["transition_mode"].nunique() == 4,
        "failed_ids_unique": episodes["failed_id"].n_unique() == episodes.height,
        "no_self_successor": episodes.filter(pl.col("failed_id") == pl.col("successor_id")).is_empty(),
        "successor_after_close": episodes.filter(pl.col("successor_created_dt") <= pl.col("prior_closed_dt")).is_empty(),
        "successor_within_precise_30d": episodes.filter(pl.col("days_to_successor") > 30).is_empty(),
        "nonnegative_day_gap": episodes.filter(pl.col("days_to_successor") <= 0).is_empty(),
        "same_contributor_new_agent_under_one_percent": (
            composition.set_index("transition_mode").loc["same contributor / different agent", "n"]
            / composition["n"].sum()
        ) < 0.01,
        "repo_clustered_cross_contributor_ci_crosses_zero": (
            contrasts.set_index("contributor_relation").loc["different contributor", "ci_low"] < 0
            < contrasts.set_index("contributor_relation").loc["different contributor", "ci_high"]
        ),
        "within_context_ci_crosses_zero": (
            within.set_index("prior_agent").loc["ALL", "ci_low"] < 0
            < within.set_index("prior_agent").loc["ALL", "ci_high"]
        ),
        "unique_successor_sensitivity_present": "successor linked to one failed PR" in set(sensitivity["definition"]),
        "nearest_failure_sensitivity_present": "nearest failed PR per successor" in set(sensitivity["definition"]),
    }
    checks = {name: bool(passed) for name, passed in checks.items()}
    failed = [name for name, passed in checks.items() if not passed]
    report = {"status": "pass" if not failed else "fail", "checks": checks, "failed": failed}
    (TABLES / "direct_handoff_validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if failed:
        raise AssertionError(f"Handoff validation failed: {failed}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
