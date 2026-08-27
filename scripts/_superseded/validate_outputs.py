from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEDGER = PROJECT_ROOT / "outputs" / "cache" / "latest_resolved_transitions.parquet"
TABLES = PROJECT_ROOT / "outputs" / "tables"


columns = [
    "id",
    "prior_id",
    "repo_url",
    "created_dt",
    "prior_closed_dt",
    "prior_merged_dt",
    "multiagent_onset_dt",
    "merged",
    "prior_merged",
    "switched",
    "gap_hours",
    "star_bin",
]
frame = pq.read_table(LEDGER, columns=columns).to_pandas()

checks: dict[str, object] = {
    "ledger_rows": int(len(frame)),
    "unique_current_ids": int(frame["id"].nunique()),
    "unique_current_id_check": bool(frame["id"].is_unique),
    "unique_prior_episode_check": bool(frame["prior_id"].is_unique),
    "strict_temporal_order_check": bool((frame["prior_closed_dt"] < frame["created_dt"]).all()),
    "prior_merge_known_check": bool(
        (
            frame["prior_merged_dt"].isna()
            | (frame["prior_merged_dt"] < frame["created_dt"])
        ).all()
    ),
    "post_onset_check": bool((frame["multiagent_onset_dt"] <= frame["created_dt"]).all()),
    "mature_30_day_cohort_check": bool(
        (frame["created_dt"] <= pd.Timestamp("2026-03-01T23:59:59Z")).all()
    ),
    "nonnegative_gap_check": bool((frame["gap_hours"] > 0).all()),
    "missing_core_fields": int(
        frame[["id", "prior_id", "repo_url", "merged", "prior_merged", "switched"]]
        .isna()
        .sum()
        .sum()
    ),
}

recomputed = (
    frame.groupby(["prior_merged", "switched"], observed=True)["merged"]
    .agg(["size", "mean"])
    .reset_index()
    .rename(columns={"size": "n_recomputed", "mean": "rate_recomputed"})
)
reported = pd.read_csv(TABLES / "rq3_recovery_rates.csv")
comparison = reported.merge(recomputed, on=["prior_merged", "switched"], validate="one_to_one")
checks["rq2_denominators_match"] = bool((comparison["n"] == comparison["n_recomputed"]).all())
checks["rq2_rates_match"] = bool(
    np.allclose(comparison["merge_rate"], comparison["rate_recomputed"], atol=1e-12)
)

failed = frame.loc[~frame["prior_merged"]]
star = (
    failed.groupby(["star_bin", "switched"], observed=True)["merged"]
    .agg(["size", "mean"])
    .reset_index()
)
wide_n = star.pivot(index="star_bin", columns="switched", values="size")
wide_rate = star.pivot(index="star_bin", columns="switched", values="mean")
star_effect = pd.DataFrame(
    {
        "stay_n_recomputed": wide_n.get(False),
        "switch_n_recomputed": wide_n.get(True),
        "effect_pp_recomputed": (wide_rate.get(True) - wide_rate.get(False)) * 100,
    }
).reset_index()
star_reported = pd.read_csv(TABLES / "rq3_star_heterogeneity.csv")
star_comparison = star_reported.merge(star_effect, on="star_bin", validate="one_to_one")
checks["rq3_star_denominators_match"] = bool(
    (star_comparison["stay_n"] == star_comparison["stay_n_recomputed"]).all()
    and (star_comparison["switch_n"] == star_comparison["switch_n_recomputed"]).all()
)
checks["rq3_star_effects_match"] = bool(
    np.allclose(
        star_comparison["effect_pp"],
        star_comparison["effect_pp_recomputed"],
        atol=1e-12,
    )
)

event = pd.read_csv(TABLES / "rq1_event_study.csv")
checks["rq1_has_pre_and_post_windows"] = bool(
    event["event_index"].min() < 0 and event["event_index"].max() > 0
)
checks["rq1_event_range"] = [int(event["event_index"].min()), int(event["event_index"].max())]

checks["all_required_checks_pass"] = bool(
    all(
        checks[key]
        for key in [
            "unique_current_id_check",
            "unique_prior_episode_check",
            "strict_temporal_order_check",
            "prior_merge_known_check",
            "post_onset_check",
            "mature_30_day_cohort_check",
            "nonnegative_gap_check",
            "rq2_denominators_match",
            "rq2_rates_match",
            "rq3_star_denominators_match",
            "rq3_star_effects_match",
            "rq1_has_pre_and_post_windows",
        ]
    )
    and checks["missing_core_fields"] == 0
)

(TABLES / "validation.json").write_text(
    json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8"
)
comparison.to_csv(TABLES / "validation_rq2_recomputation.csv", index=False)
star_comparison.to_csv(TABLES / "validation_rq3_recomputation.csv", index=False)
print(json.dumps(checks, indent=2))

if not checks["all_required_checks_pass"]:
    raise SystemExit("Validation failed; inspect outputs/tables/validation.json")
