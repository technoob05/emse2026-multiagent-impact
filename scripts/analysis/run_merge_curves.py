"""Cumulative merge over time, so the RQ3 result can be seen rather than tabulated.

The hazard model in `run_rq3_extensions.py` reports one odds ratio. That number
hides the shape it came from. This script produces the shape: how the share of
merged pull requests grows over the 30 days after a cross-product review
trigger, split by what kind of inline reply the pull request has received.

The split is three-armed, because the negative-control exposures in
`run_pseudo_edge_negative_control.py` showed that the association tracks having
an inline reply at all rather than the reply being anchored to the trigger. The
three arms make that visible as a shape:

1. `no_reply`    no inline reply of any anchoring yet;
2. `off_target`  a reply anchored to some other inline comment on the pull
                 request, but not to the trigger;
3. `on_target`   a reply whose raw GitHub `in_reply_to_id` is the trigger id -
                 the exact addressed edge.

The accounting is time-varying and unchanged from the two-arm version. A pull
request sits in the lowest arm it qualifies for and moves up when its own first
qualifying reply arrives, so a pull request contributes its early risk to one
curve and its later risk to another. On-target dominates off-target: once the
exact edge appears the pull request stays in arm 3.

The off-target construction is imported from
`run_pseudo_edge_negative_control.py` rather than rebuilt, so there is one
definition of the on-target / off-target split. It is applied under exactly the
guards the pre-existing edge column already used - the seven-day response
window of `build_cross_feedback_response_events` and the closed-pull-request
boundary - and the script asserts that the imported construction reproduces the
pre-existing edge set exactly before it is used.

The original two-arm curves (`merged_no_edge`, `merged_with_edge`) are still
computed and written unchanged so nothing downstream breaks. `merged_with_edge`
and the three-arm `on_target` curve are the same object: both are the state
"the exact edge has appeared".

Uncertainty comes from resampling whole repositories, because pull requests in
one repository share policy and people.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from multiagent_impact.cross_agent_review import INTERACTION_CUTOFF  # noqa: E402
from run_pseudo_edge_negative_control import inline_reply_events  # noqa: E402

CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "merge_curves"

HORIZON_DAYS = 30
GRID = np.concatenate([np.arange(0, 2, 0.125), np.arange(2, 30.5, 0.5)])
# Raised from 400 to 2,000 on the strength of the draw-count sweep in
# `outputs/constant_sensitivity/`: the point estimates are deterministic and do
# not move at all, and no qualitative conclusion changes, but at 400 draws a
# band edge sits up to 1.7 percentage points away from its 2,000-draw value.
# 2,000 also puts this script inside the 1,000-10,000 range every other
# analysis in the repository uses. Override with --bootstrap-draws.
BOOTSTRAP_DRAWS = 2_000
SEED = 20260826
EXPECTED_POPULATION = 3_942
# The pre-existing edge column comes from build_cross_feedback_response_events,
# whose response window is seven days and which drops replies after the pull
# request closed. The off-target arm must use the same guards to be a
# like-for-like contrast.
RESPONSE_WINDOW_DAYS = 7

ARMS = ("no_reply", "off_target", "on_target")


def build_cohort() -> pd.DataFrame:
    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    cohort = (
        chains.filter(
            (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("author_agent") != pl.col("trigger_reviewer_agent"))
            & (
                pl.col("trigger_dt")
                <= pl.lit(INTERACTION_CUTOFF - timedelta(days=HORIZON_DAYS))
            )
        )
        .select("pr_id", "repo_id", "trigger_dt", "trigger_event_id", "closed_dt", "merged_dt")
        .unique("pr_id")
    )
    if cohort.height != EXPECTED_POPULATION:
        raise AssertionError(f"Population drift: {cohort.height}")

    edges = (
        pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet")
        .filter(
            (pl.col("response_source") == "direct_inline_reply")
            & (pl.col("hours_after_trigger") > 0)
        )
        .join(
            cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
            on=["pr_id", "trigger_event_id", "trigger_dt"],
            how="inner",
        )
        .group_by("pr_id")
        .agg(pl.col("response_dt").min().alias("first_edge_dt"))
    )

    replies = inline_reply_events(
        cohort.select("pr_id", "trigger_dt", "trigger_event_id", "closed_dt"),
        RESPONSE_WINDOW_DAYS * 24,
    ).filter(
        pl.col("closed_dt").is_null() | (pl.col("reply_dt") <= pl.col("closed_dt"))
    )
    derived_edges = (
        replies.filter(pl.col("on_target"))
        .group_by("pr_id")
        .agg(pl.col("reply_dt").min().alias("derived_edge_dt"))
    )
    audit = edges.join(derived_edges, on="pr_id", how="full", coalesce=True)
    if audit.filter(pl.col("derived_edge_dt").is_null()).height:
        raise AssertionError(
            "The imported on-target construction misses a pre-existing exact edge."
        )
    if audit.filter(pl.col("first_edge_dt").is_null()).height:
        raise AssertionError(
            "The imported on-target construction invents an exact edge the "
            "pre-existing column does not have."
        )
    if audit.filter(pl.col("first_edge_dt") != pl.col("derived_edge_dt")).height:
        raise AssertionError(
            "The imported and pre-existing exact-edge timestamps disagree."
        )
    off_edges = (
        replies.filter(~pl.col("on_target"))
        .group_by("pr_id")
        .agg(pl.col("reply_dt").min().alias("first_off_target_dt"))
    )

    horizon = pl.col("trigger_dt") + timedelta(days=HORIZON_DAYS)
    frame = (
        cohort.join(edges, on="pr_id", how="left")
        .join(off_edges, on="pr_id", how="left")
        .with_columns(
            pl.min_horizontal(
                pl.coalesce([pl.col("closed_dt"), horizon]),
                horizon,
                pl.lit(INTERACTION_CUTOFF),
            ).alias("exit_dt")
        )
        .with_columns(
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("trigger_dt"))
                & (pl.col("merged_dt") <= horizon)
            ).alias("merged_in_horizon")
        )
        .with_columns(
            (
                (pl.col("exit_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
            ).alias("exit_days"),
            pl.when(pl.col("merged_dt").is_not_null())
            .then(
                (pl.col("merged_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
            )
            .otherwise(None)
            .alias("merge_days"),
            pl.when(pl.col("first_edge_dt").is_not_null())
            .then(
                (pl.col("first_edge_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 86400.0
            )
            .otherwise(None)
            .alias("edge_days"),
            pl.when(pl.col("first_off_target_dt").is_not_null())
            .then(
                (
                    pl.col("first_off_target_dt") - pl.col("trigger_dt")
                ).dt.total_seconds()
                / 86400.0
            )
            .otherwise(None)
            .alias("off_target_days"),
        )
        .with_columns(
            pl.when(pl.col("merged_in_horizon"))
            .then(pl.col("merge_days"))
            .otherwise(pl.col("exit_days"))
            .clip(0.0, float(HORIZON_DAYS))
            .alias("follow_up_days")
        )
        .to_pandas()
    )
    return frame


def cumulative_incidence(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Aalen-Johansen style curves under a time-varying split.

    At each grid point a pull request is at risk if it has not yet left. Its arm
    is the highest one it has reached: the exact edge outranks an off-target
    reply, which outranks no reply. Each curve is built from the hazard
    accumulated inside its own state, so a pull request that switches
    contributes its early risk to one curve and its later risk to another.

    `no_edge` and `with_edge` are the original two-arm split, kept unchanged.
    `on_target` is the same state as `with_edge`; `no_edge` is the union of
    `no_reply` and `off_target`.
    """
    follow = frame["follow_up_days"].to_numpy()
    merged = frame["merged_in_horizon"].to_numpy().astype(bool)
    edge = frame["edge_days"].to_numpy(dtype=float)
    edge = np.where(np.isnan(edge), np.inf, edge)
    off = frame["off_target_days"].to_numpy(dtype=float)
    off = np.where(np.isnan(off), np.inf, off)

    states = {
        "no_edge": lambda t: edge > t,
        "with_edge": lambda t: edge <= t,
        "no_reply": lambda t: (edge > t) & (off > t),
        "off_target": lambda t: (edge > t) & (off <= t),
        "on_target": lambda t: edge <= t,
    }

    curves: dict[str, np.ndarray] = {}
    for name, in_state_at in states.items():
        survival = 1.0
        incidence = np.empty(len(GRID))
        previous = 0.0
        for index, stop in enumerate(GRID):
            at_risk = (follow > previous) & in_state_at(previous)
            n_risk = int(at_risk.sum())
            events = int((at_risk & merged & (follow <= stop)).sum())
            if n_risk:
                hazard = events / n_risk
                survival *= 1.0 - hazard
            incidence[index] = 1.0 - survival
            previous = stop
        curves[name] = incidence
    return curves


def bootstrap(
    frame: pd.DataFrame, bootstrap_draws: int = BOOTSTRAP_DRAWS
) -> dict[str, np.ndarray]:
    generator = np.random.default_rng(SEED)
    repositories = frame["repo_id"].to_numpy()
    unique = np.unique(repositories)
    index_by_repo = {repo: np.flatnonzero(repositories == repo) for repo in unique}

    names = ("no_edge", "with_edge", "no_reply", "off_target", "on_target")
    draws = {name: np.empty((bootstrap_draws, len(GRID))) for name in names}
    for draw in range(bootstrap_draws):
        picked = generator.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([index_by_repo[repo] for repo in picked])
        sample = frame.iloc[rows]
        curves = cumulative_incidence(sample)
        for name in names:
            draws[name][draw] = curves[name]

    bands: dict[str, np.ndarray] = {}
    for name in names:
        bands[f"{name}_low"] = np.quantile(draws[name], 0.025, axis=0)
        bands[f"{name}_high"] = np.quantile(draws[name], 0.975, axis=0)
    return bands


def overlap_diagnostics(
    curves: dict[str, np.ndarray], bands: dict[str, np.ndarray]
) -> dict[str, object]:
    """Do the off-target and on-target curves actually sit on top of each other?

    The claim the figure is meant to carry is that arms 2 and 3 coincide while
    arm 1 sits below. This measures it instead of asserting it: point-wise band
    overlap across the whole horizon, the largest gap between the two point
    estimates, and the same comparison against the no-reply arm for scale.
    """
    off = curves["off_target"]
    on = curves["on_target"]
    none = curves["no_reply"]
    band_overlap = (bands["off_target_low"] <= bands["on_target_high"]) & (
        bands["on_target_low"] <= bands["off_target_high"]
    )
    separated = np.flatnonzero(~band_overlap)
    signed = off - on
    gap = np.abs(signed)
    early = GRID <= 7.0
    # Early on, the no-reply arm is mechanically the highest: a pull request
    # that merges within hours never has time to receive a reply, so the
    # fastest merges all accrue to arm 1. Anyone reading the figure needs to
    # know where that artefact stops.
    highest_is_no_reply = (none >= off) & (none >= on)
    leading = np.flatnonzero(~highest_is_no_reply)
    return {
        "signed_gap_off_minus_on_min_pp": float(signed.min() * 100.0),
        "signed_gap_off_minus_on_max_pp": float(signed.max() * 100.0),
        "grid_points_off_target_above_on_target": int((signed > 0).sum()),
        "grid_points_on_target_above_off_target": int((signed < 0).sum()),
        "no_reply_arm_highest_until_day": (
            float(GRID[leading[0]]) if leading.size else None
        ),
        "grid_points": int(len(GRID)),
        "off_target_on_target_band_overlap_points": int(band_overlap.sum()),
        "off_target_on_target_band_overlap_share": float(band_overlap.mean()),
        "off_target_on_target_bands_overlap_whole_horizon": bool(band_overlap.all()),
        "first_day_bands_separate": (
            float(GRID[separated[0]]) if separated.size else None
        ),
        "max_abs_gap_off_vs_on_pp": float(gap.max() * 100.0),
        "max_abs_gap_day": float(GRID[int(np.argmax(gap))]),
        "mean_abs_gap_off_vs_on_pp": float(gap.mean() * 100.0),
        "max_abs_gap_first_7_days_pp": float(gap[early].max() * 100.0),
        "day_30_gap_off_vs_on_pp": float((on[-1] - off[-1]) * 100.0),
        "day_30_gap_no_reply_vs_off_pp": float((off[-1] - none[-1]) * 100.0),
        "day_30_gap_no_reply_vs_on_pp": float((on[-1] - none[-1]) * 100.0),
        "no_reply_band_below_off_target_at_day_30": bool(
            bands["no_reply_high"][-1] < bands["off_target_low"][-1]
        ),
        "no_reply_band_below_on_target_at_day_30": bool(
            bands["no_reply_high"][-1] < bands["on_target_low"][-1]
        ),
    }


def parse_args() -> argparse.Namespace:
    """Expose the draw count and destination without moving the defaults.

    `BOOTSTRAP_DRAWS` and `OUTPUT` remain the primary path; the arguments exist
    so the draw count can be swept rather than asserted. Only the bands depend
    on the draw count - the point estimates are deterministic.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.bootstrap_draws < 100:
        raise ValueError("--bootstrap-draws must be at least 100")
    return args


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_cohort()
    curves = cumulative_incidence(frame)
    bands = bootstrap(frame, args.bootstrap_draws)
    if not np.allclose(curves["with_edge"], curves["on_target"]):
        raise AssertionError(
            "The legacy edge curve and the three-arm on-target curve must be "
            "the same state."
        )

    table = pd.DataFrame(
        {
            "days_since_trigger": GRID,
            "merged_no_edge": curves["no_edge"],
            "merged_no_edge_low": bands["no_edge_low"],
            "merged_no_edge_high": bands["no_edge_high"],
            "merged_with_edge": curves["with_edge"],
            "merged_with_edge_low": bands["with_edge_low"],
            "merged_with_edge_high": bands["with_edge_high"],
            "merged_no_reply": curves["no_reply"],
            "merged_no_reply_low": bands["no_reply_low"],
            "merged_no_reply_high": bands["no_reply_high"],
            "merged_reply_off_target": curves["off_target"],
            "merged_reply_off_target_low": bands["off_target_low"],
            "merged_reply_off_target_high": bands["off_target_high"],
            "merged_reply_on_target": curves["on_target"],
            "merged_reply_on_target_low": bands["on_target_low"],
            "merged_reply_on_target_high": bands["on_target_high"],
        }
    )
    table.to_csv(output_dir / "cumulative_merge.csv", index=False)

    edge_days = frame["edge_days"].to_numpy(dtype=float)
    off_days = frame["off_target_days"].to_numpy(dtype=float)
    has_edge = np.isfinite(edge_days)
    has_off = np.isfinite(off_days)
    arm_prs = {
        "no_reply": int((~has_edge & ~has_off).sum()),
        "off_target": int((~has_edge & has_off).sum()),
        "on_target": int(has_edge.sum()),
    }
    if sum(arm_prs.values()) != len(frame):
        raise AssertionError("The three arms do not partition the population.")

    diagnostics = overlap_diagnostics(curves, bands)
    summary = {
        "population_prs": int(len(frame)),
        "repositories": int(frame["repo_id"].nunique()),
        "prs_with_any_exact_edge": int(has_edge.sum()),
        "prs_merged_within_horizon": int(frame["merged_in_horizon"].sum()),
        "horizon_days": HORIZON_DAYS,
        "bootstrap_draws": args.bootstrap_draws,
        "bootstrap_unit": "repository",
        "seed": SEED,
        "merged_by_day_30_no_edge": float(curves["no_edge"][-1]),
        "merged_by_day_30_with_edge": float(curves["with_edge"][-1]),
        "interpretation": (
            "cumulative merge under a time-varying edge split; a pull request "
            "contributes unexposed risk until its own first exact reply; "
            "observational, not a causal effect"
        ),
        "three_arm_split": {
            "response_window_days": RESPONSE_WINDOW_DAYS,
            "arm_order": list(ARMS),
            "off_target_source": (
                "inline_reply_events imported from "
                "run_pseudo_edge_negative_control.py, under the same seven-day "
                "response window and closed-pull-request guard as the "
                "pre-existing exact-edge column"
            ),
            "on_target_construction_matches_preexisting_edge_column": True,
        },
        "prs_with_off_target_reply": int(has_off.sum()),
        "arm_prs_no_reply": arm_prs["no_reply"],
        "arm_prs_reply_off_target": arm_prs["off_target"],
        "arm_prs_reply_on_target": arm_prs["on_target"],
        "merged_by_day_30_no_reply": float(curves["no_reply"][-1]),
        "merged_by_day_30_reply_off_target": float(curves["off_target"][-1]),
        "merged_by_day_30_reply_on_target": float(curves["on_target"][-1]),
        "merged_by_day_30_no_reply_ci": [
            float(bands["no_reply_low"][-1]),
            float(bands["no_reply_high"][-1]),
        ],
        "merged_by_day_30_reply_off_target_ci": [
            float(bands["off_target_low"][-1]),
            float(bands["off_target_high"][-1]),
        ],
        "merged_by_day_30_reply_on_target_ci": [
            float(bands["on_target_low"][-1]),
            float(bands["on_target_high"][-1]),
        ],
        "three_arm_overlap_diagnostics": diagnostics,
        "three_arm_interpretation": (
            "the off-target arm is a reply anchored to a different inline comment "
            "on the same pull request; if it tracks the on-target arm while the "
            "no-reply arm sits below, the day-30 difference is a liveness "
            "difference rather than an anchoring one"
        ),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
