"""Put the measured controls on the same plane as the hypothetical hidden cause.

The tipping-point figure asks how strong an unmeasured factor would have to be.
On its own that is an abstraction, and a reader has no way to judge whether the
shaded region is a demanding place or an ordinary one. This script answers that
by locating every factor we DID measure on the same two axes:

  x  how much more common the factor is among answered PRs, in points
  y  how much the factor moves later merge on its own, in points

If the measured controls all sit far below the tipping curve, then a hidden
factor strong enough to erase the result would have to be unlike anything we
observed --- which is a statement a reader can check rather than take on faith.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CHAIN = ROOT / "outputs" / "cross_agent_review"
LANDMARK = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "confounder_benchmarks"

THRESHOLD_HOURS = 48
EXPOSURE = f"exact_parent_reply_by_{THRESHOLD_HOURS}h"
SPECIFICATION = "A_pretrigger_only"

# Only pre-trigger facts qualify. Anything measured after the trigger could be a
# consequence of it, and would not be a fair stand-in for a hidden prior cause.
BENCHMARKS = {
    "pre_user_events": "a person had already acted",
    "pre_bot_events": "automation had already acted",
    "pre_decisive_reviews": "a decisive review already existed",
    "pre_force_pushes": "the branch had already been rewritten",
}


def main() -> None:
    cohort = pl.read_parquet(LANDMARK / "analysis_cohort.parquet")
    columns = set(cohort.columns)
    missing = sorted(set(BENCHMARKS) | {EXPOSURE} - columns)
    missing = [name for name in missing if name not in columns]
    if missing:
        raise SystemExit(f"cohort lacks: {missing}")

    frame = cohort.to_pandas()
    exposed = frame[EXPOSURE].astype(bool)
    merged = frame["merged_from_48h_to_30d"].astype(bool)

    terms = pd.read_csv(LANDMARK / "addressed_edge_clustered_lpm_all_terms.csv")
    terms = terms[
        (terms["threshold_hours"] == THRESHOLD_HOURS)
        & (terms["specification"] == SPECIFICATION)
    ]

    rows = []
    for column, label in BENCHMARKS.items():
        present = frame[column].astype(float) > 0
        prevalence_gap = (present[exposed].mean() - present[~exposed].mean()) * 100
        # The factor's own association with the outcome, unadjusted, on the same
        # percentage-point scale the tipping curve uses.
        outcome_gap = (merged[present].mean() - merged[~present].mean()) * 100
        model = terms[terms["term"] == column]
        rows.append(
            {
                "factor": column,
                "label": label,
                "prevalence_gap_pp": round(float(prevalence_gap), 2),
                "outcome_gap_pp": round(float(outcome_gap), 2),
                "share_exposed": round(float(present[exposed].mean()), 4),
                "share_unexposed": round(float(present[~exposed].mean()), 4),
                "adjusted_coefficient_pp": (
                    round(float(model["estimate"].iloc[0]) * 100, 2)
                    if len(model)
                    else None
                ),
                "prs": int(len(frame)),
            }
        )

    table = pd.DataFrame(rows).sort_values("prevalence_gap_pp", key=np.abs, ascending=False)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT / "measured_factor_positions.csv", index=False)

    strongest = table.iloc[0]
    (OUTPUT / "summary.json").write_text(
        json.dumps(
            {
                "threshold_hours": THRESHOLD_HOURS,
                "exposure": EXPOSURE,
                "factors": len(table),
                "prs": int(len(frame)),
                "largest_prevalence_gap_pp": float(strongest["prevalence_gap_pp"]),
                "largest_prevalence_gap_factor": str(strongest["label"]),
                "max_abs_outcome_gap_pp": float(table["outcome_gap_pp"].abs().max()),
                "axes": (
                    "x: how much more common the factor is among answered PRs, in "
                    "percentage points; y: the factor's own unadjusted difference in "
                    "later merge, in percentage points"
                ),
                "interpretation": (
                    "these are the factors we measured, placed on the same plane as "
                    "the hypothetical hidden cause, so the tipping region can be read "
                    "against something observed rather than in the abstract"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"{len(table)} measured factors placed on the tipping plane")
    for row in table.itertuples(index=False):
        print(
            f"  {row.label:<40} prevalence {row.prevalence_gap_pp:+6.1f} pp   "
            f"outcome {row.outcome_gap_pp:+6.1f} pp"
        )


if __name__ == "__main__":
    main()
