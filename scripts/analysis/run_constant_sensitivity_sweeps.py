"""Sensitivity sweeps for the four load-bearing constants of the paper.

The four constants are asserted in the analysis scripts without any published
sweep beside them:

1. the 48-hour landmark (`run_addressed_edge_landmark_analysis.py`), which
   simultaneously decides who enters the RQ3 cohort, when the merge outcome
   starts counting, and how long the RQ4 answer window is;
2. the 30-day outcome horizon (`HORIZON_DAYS`);
3. the seven-day RQ1 follow-up window (`RESPONSE_WINDOW_DAYS`);
4. the 400 bootstrap draws behind the Figure 4 bands (`BOOTSTRAP_DRAWS`,
   handled by `run_merge_curves.py --bootstrap-draws`, not here).

Nothing here changes a primary path. The primary settings (48 hours, 30 days,
seven days) are re-derived by exactly the same code as the sweep and checked
against the published artifacts in `outputs/` before any sweep row is written.
If that check fails the script raises rather than reporting a sweep.

Interpretation is unchanged from the primary analyses: these are observational
later-merge probability differences and observable public response topology, not
causal effects and not semantic resolution rates.
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
import statsmodels.api as sm
from patsy import dmatrices

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    INTERACTION_CUTOFF,
    build_cross_feedback_response_chains,
    build_cross_feedback_response_events,
)
from run_addressed_edge_landmark_analysis import (  # noqa: E402
    BASE_CATEGORICAL,
    PRETRIGGER_CONTROLS,
    add_pretrigger_features,
)
import run_burst_collapsed_topology as BURST  # noqa: E402

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
LANDMARK_DIR = ROOT / "outputs" / "addressed_edge_landmark"
DEFAULT_OUTPUT = ROOT / "outputs" / "constant_sensitivity"

SEED = 20260826

PRIMARY_LANDMARK_HOURS = 48
PRIMARY_HORIZON_DAYS = 30
PRIMARY_RESPONSE_WINDOW_DAYS = 7
PRIMARY_BURST_MINUTES = 5

LANDMARK_SWEEP_HOURS = (24, 48, 72, 96)
HORIZON_SWEEP_DAYS = (14, 30, 60)
RESPONSE_WINDOW_SWEEP_DAYS = (1, 3, 7, 14)

# Published primary values, from outputs/addressed_edge_landmark and
# outputs/burst_threshold_selection. Used as reproduction gates.
PUBLISHED_PRIMARY_LPM = {
    "n_prs": 1067,
    "exposed_prs": 109,
    "estimate": 0.17346523604933012,
    "ci_low": 0.07255437972242951,
    "ci_high": 0.27437609237623073,
}
PUBLISHED_PRIMARY_OWNER_SPLIT = {
    "prs": 8608,
    "post_burst_action_prs": 4771,
    "user_account_prs": 2526,
    "mapped_product_prs": 924,
}
TOLERANCE = 1e-9


# ---------------------------------------------------------------------------
# Sweeps 1 and 2: landmark hours and outcome horizon
# ---------------------------------------------------------------------------


def landmark_cohort(
    chains: pl.DataFrame,
    events: pl.DataFrame,
    landmark_hours: int,
    horizon_days: int,
) -> pl.DataFrame:
    """Rebuild the landmark cohort for an arbitrary landmark and horizon.

    This reproduces `feedback_48h_landmark_cohort.parquet` from
    `run_cross_agent_review_exploration.py` with the two constants free, then
    applies the inline-trigger restriction of
    `run_addressed_edge_landmark_analysis.py`.
    """
    landmark = timedelta(hours=landmark_hours)
    horizon = timedelta(days=horizon_days)
    cohort = (
        chains.filter(
            (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("author_agent") != pl.col("trigger_reviewer_agent"))
            & (pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - horizon))
        )
        .with_columns(
            (pl.col("trigger_dt") + landmark).alias("outcome_landmark_dt")
        )
        .filter(
            pl.col("closed_dt").is_null()
            | (pl.col("closed_dt") > pl.col("outcome_landmark_dt"))
        )
        .with_columns(
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("outcome_landmark_dt"))
                & (pl.col("merged_dt") <= pl.col("trigger_dt") + horizon)
            ).alias("later_merge"),
            pl.col("trigger_dt").dt.strftime("%Y-%m").alias("trigger_month"),
        )
        .select(
            "pr_id",
            "repo_id",
            "trigger_dt",
            "trigger_event_id",
            "author_agent",
            "trigger_reviewer_agent",
            "closed_dt",
            "merged_dt",
            "outcome_landmark_dt",
            "trigger_month",
            "later_merge",
        )
        .unique("pr_id")
        .sort("pr_id")
    )
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError("Landmark cohort is not one row per PR.")
    if cohort.filter(
        pl.col("outcome_landmark_dt") != pl.col("trigger_dt") + landmark
    ).height:
        raise AssertionError("Outcome landmark is not exactly trigger + landmark.")
    if cohort.filter(
        pl.col("later_merge") & (pl.col("merged_dt") <= pl.col("outcome_landmark_dt"))
    ).height:
        raise AssertionError("Outcome leakage: merge is not strictly after landmark.")
    if cohort.filter(
        pl.col("later_merge")
        & (pl.col("merged_dt") > pl.col("trigger_dt") + horizon)
    ).height:
        raise AssertionError("Outcome exceeds the horizon.")

    exposure_column = f"exact_parent_reply_by_{landmark_hours}h"
    direct = (
        events.filter(pl.col("response_source") == "direct_inline_reply")
        .join(
            cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
            on=["pr_id", "trigger_event_id", "trigger_dt"],
            how="inner",
        )
        .filter(
            (pl.col("hours_after_trigger") > 0)
            & (pl.col("hours_after_trigger") <= landmark_hours)
        )
        .group_by("pr_id")
        .agg(pl.col("hours_after_trigger").min().alias("first_exact_reply_hours"))
    )
    return cohort.join(direct, on="pr_id", how="left").with_columns(
        pl.col("first_exact_reply_hours").is_not_null().alias(exposure_column)
    )


def fit_primary_lpm(frame: pd.DataFrame, exposure: str) -> dict[str, object]:
    """Specification A of the primary RQ3 model: pre-trigger controls only."""
    formula = "later_merge ~ " + " + ".join(
        [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    if groups.nunique() < 2:
        raise RuntimeError("Clustered model has fewer than two repositories.")
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    interval = model.conf_int().loc[exposure]
    exposed = frame[exposure].astype(bool)
    return {
        "term": exposure,
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
        "exposed_prs": int(exposed.sum()),
        "unexposed_prs": int((~exposed).sum()),
        "later_merges": int(frame["later_merge"].sum()),
        "exposed_raw_later_merge_rate": float(
            frame.loc[exposed, "later_merge"].mean()
        ) if exposed.any() else float("nan"),
        "unexposed_raw_later_merge_rate": float(
            frame.loc[~exposed, "later_merge"].mean()
        ),
        "formula": formula,
    }


def landmark_horizon_row(
    chains: pl.DataFrame,
    events: pl.DataFrame,
    landmark_hours: int,
    horizon_days: int,
) -> dict[str, object]:
    cohort = landmark_cohort(chains, events, landmark_hours, horizon_days)
    enriched, _ = add_pretrigger_features(cohort)
    frame = enriched.to_pandas()
    frame["later_merge"] = frame["later_merge"].astype(int)
    exposure = f"exact_parent_reply_by_{landmark_hours}h"
    frame[exposure] = frame[exposure].astype(int)
    row = fit_primary_lpm(frame, exposure)
    row.update(
        {
            "landmark_hours": landmark_hours,
            "horizon_days": horizon_days,
            "is_primary": landmark_hours == PRIMARY_LANDMARK_HOURS
            and horizon_days == PRIMARY_HORIZON_DAYS,
        }
    )
    return row


def check_primary_lpm(row: dict[str, object]) -> None:
    for key, expected in PUBLISHED_PRIMARY_LPM.items():
        got = row[key]
        if isinstance(expected, int):
            if int(got) != expected:
                raise AssertionError(
                    f"Primary RQ3 reproduction failed on {key}: {got} != {expected}"
                )
        elif abs(float(got) - expected) > TOLERANCE:
            raise AssertionError(
                f"Primary RQ3 reproduction failed on {key}: {got!r} != {expected!r}"
            )


# ---------------------------------------------------------------------------
# Sweep 3: the seven-day RQ1 follow-up window
# ---------------------------------------------------------------------------


def owner_split_row(response_days: int, draws: int) -> dict[str, object]:
    """RQ1 first post-burst owner at one follow-up window.

    The burst threshold is held at the primary five minutes; only the follow-up
    window moves. Changing the window also moves the trigger-eligibility cut
    (`trigger_dt <= INTERACTION_CUTOFF - window`), so the cohort size is
    reported alongside the split rather than assumed constant.
    """
    chains = build_cross_feedback_response_chains(
        DATA, response_days=response_days
    ).collect()
    events = build_cross_feedback_response_events(
        DATA, response_days=response_days
    ).collect()
    enriched = BURST.classify_atomic_state(events.unique(maintain_order=True))
    first, diagnostics = BURST.build_first_state(
        chains, enriched, PRIMARY_BURST_MINUTES
    )
    frame = first.to_pandas()
    counts = frame["first_post_burst_state"].value_counts()
    prs = len(frame)
    user = int(counts.get("user_account", 0))
    mapped = int(counts.get("mapped_product", 0))
    action_states = [s for s in BURST.ACTION_STATES]
    action_total = int(sum(counts.get(s, 0) for s in action_states))
    action_counts = {s: int(counts.get(s, 0)) for s in action_states}
    modal_action_state = max(action_counts, key=action_counts.get)

    low, high = paired_repo_bootstrap_difference(frame, draws)
    return {
        "response_window_days": response_days,
        "burst_threshold_minutes": PRIMARY_BURST_MINUTES,
        "prs": prs,
        "repositories": int(frame["repo_id"].nunique()),
        "post_burst_action_prs": action_total,
        "user_account_prs": user,
        "mapped_product_prs": mapped,
        "other_bot_prs": action_counts.get("other_bot", 0),
        "branch_movement_untyped_prs": action_counts.get(
            "branch_movement_untyped", 0
        ),
        "no_action_prs": int(counts.get("no_action_within_7d", 0)),
        "user_share_all_prs": user / prs,
        "mapped_share_all_prs": mapped / prs,
        "user_share_post_burst_actions": user / action_total if action_total else np.nan,
        "mapped_share_post_burst_actions": (
            mapped / action_total if action_total else np.nan
        ),
        "user_minus_mapped_percentage_points_all_prs": (user - mapped) / prs * 100.0,
        "user_minus_mapped_ci_low_pp_all_prs": low,
        "user_minus_mapped_ci_high_pp_all_prs": high,
        "user_exceeds_mapped": bool(user > mapped),
        "user_minus_mapped_interval_excludes_zero": bool(low > 0.0 or high < 0.0),
        "modal_post_burst_action_state": modal_action_state,
        "user_is_modal_action_state": modal_action_state == "user_account",
        "collapsed_event_rows": int(diagnostics["collapsed_event_rows"]),
        "is_primary": response_days == PRIMARY_RESPONSE_WINDOW_DAYS,
    }


def paired_repo_bootstrap_difference(
    frame: pd.DataFrame, draws: int
) -> tuple[float, float]:
    """Repository-clustered interval on the user-minus-mapped share difference."""
    counts = pd.crosstab(frame["repo_id"], frame["first_post_burst_state"])
    for state in ("user_account", "mapped_product"):
        if state not in counts.columns:
            counts[state] = 0
    user = counts["user_account"].to_numpy(dtype=float)
    mapped = counts["mapped_product"].to_numpy(dtype=float)
    total = counts.sum(axis=1).to_numpy(dtype=float)
    n = len(total)
    rng = np.random.default_rng(SEED)
    picks = rng.integers(0, n, size=(draws, n), dtype=np.int32)
    numerator = (user - mapped)[picks].sum(axis=1)
    denominator = total[picks].sum(axis=1)
    values = numerator / denominator * 100.0
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high)


def check_primary_owner_split(row: dict[str, object]) -> None:
    for key, expected in PUBLISHED_PRIMARY_OWNER_SPLIT.items():
        if int(row[key]) != expected:
            raise AssertionError(
                f"Primary RQ1 reproduction failed on {key}: {row[key]} != {expected}"
            )


# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=["landmark", "horizon", "response_window"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet")

    summary: dict[str, object] = {
        "seed": SEED,
        "primary_settings": {
            "landmark_hours": PRIMARY_LANDMARK_HOURS,
            "horizon_days": PRIMARY_HORIZON_DAYS,
            "response_window_days": PRIMARY_RESPONSE_WINDOW_DAYS,
            "burst_threshold_minutes": PRIMARY_BURST_MINUTES,
        },
        "interpretation": (
            "observational later-merge probability differences and observable "
            "public response topology; not causal effects and not semantic "
            "resolution rates"
        ),
    }

    primary_row: dict[str, object] | None = None

    if "landmark" not in args.skip:
        rows = []
        for hours in LANDMARK_SWEEP_HOURS:
            row = landmark_horizon_row(chains, events, hours, PRIMARY_HORIZON_DAYS)
            if row["is_primary"]:
                check_primary_lpm(row)
                primary_row = row
            rows.append(row)
            print(
                f"[landmark] {hours}h  n={row['n_prs']}  exposed={row['exposed_prs']}"
                f"  est={row['estimate']:+.4f}"
                f"  [{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
                f"  p={row['p_value']:.4g}",
                flush=True,
            )
        table = pd.DataFrame(rows)
        table.to_csv(args.output_dir / "landmark_sweep.csv", index=False)
        summary["landmark_sweep"] = rows
        summary["landmark_primary_reproduced"] = primary_row is not None

    if "horizon" not in args.skip:
        rows = []
        for days in HORIZON_SWEEP_DAYS:
            row = landmark_horizon_row(
                chains, events, PRIMARY_LANDMARK_HOURS, days
            )
            if row["is_primary"]:
                check_primary_lpm(row)
            rows.append(row)
            print(
                f"[horizon] {days}d  n={row['n_prs']}  exposed={row['exposed_prs']}"
                f"  est={row['estimate']:+.4f}"
                f"  [{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
                f"  p={row['p_value']:.4g}",
                flush=True,
            )
        table = pd.DataFrame(rows)
        table.to_csv(args.output_dir / "horizon_sweep.csv", index=False)
        summary["horizon_sweep"] = rows

    if "response_window" not in args.skip:
        rows = []
        for days in RESPONSE_WINDOW_SWEEP_DAYS:
            row = owner_split_row(days, args.bootstrap_draws)
            if row["is_primary"]:
                check_primary_owner_split(row)
            rows.append(row)
            print(
                f"[window] {days}d  prs={row['prs']}"
                f"  user={row['user_account_prs']}"
                f"  mapped={row['mapped_product_prs']}"
                f"  diff={row['user_minus_mapped_percentage_points_all_prs']:+.2f}pp"
                f"  [{row['user_minus_mapped_ci_low_pp_all_prs']:+.2f},"
                f" {row['user_minus_mapped_ci_high_pp_all_prs']:+.2f}]"
                f"  modal={row['modal_post_burst_action_state']}",
                flush=True,
            )
        table = pd.DataFrame(rows)
        table.to_csv(args.output_dir / "response_window_sweep.csv", index=False)
        summary["response_window_sweep"] = rows
        summary["response_window_bootstrap_draws"] = args.bootstrap_draws

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str)[:400])


if __name__ == "__main__":
    main()
