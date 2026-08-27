"""Cumulative merge over time, so the RQ3 result can be seen rather than tabulated.

The hazard model in `run_rq3_extensions.py` reports one odds ratio. That number
hides the shape it came from. This script produces the shape: how the share of
merged pull requests grows over the 30 days after a cross-product review
trigger, split by whether an exact addressed edge has appeared.

The split is time-varying. A pull request contributes to the "no edge yet" curve
until its own first exact reply, and to the "edge" curve afterwards. That is the
same accounting the hazard model uses, so the curve and the odds ratio describe
one analysis rather than two.

Uncertainty comes from resampling whole repositories, because pull requests in
one repository share policy and people.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import INTERACTION_CUTOFF  # noqa: E402

CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "merge_curves"

HORIZON_DAYS = 30
GRID = np.concatenate([np.arange(0, 2, 0.125), np.arange(2, 30.5, 0.5)])
BOOTSTRAP_DRAWS = 400
SEED = 20260826
EXPECTED_POPULATION = 3_942


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

    horizon = pl.col("trigger_dt") + timedelta(days=HORIZON_DAYS)
    frame = (
        cohort.join(edges, on="pr_id", how="left")
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


def cumulative_incidence(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Aalen-Johansen style curves under a time-varying split.

    At each grid point a pull request is at risk if it has not yet left. It sits
    in the exposed set from its own first exact reply onward. The two curves are
    built from the hazard accumulated inside each state, so a PR that switches
    contributes its early risk to one curve and its later risk to the other.
    """
    follow = frame["follow_up_days"].to_numpy()
    merged = frame["merged_in_horizon"].to_numpy().astype(bool)
    edge = frame["edge_days"].to_numpy(dtype=float)
    edge = np.where(np.isnan(edge), np.inf, edge)

    curves = []
    for exposed_state in (False, True):
        survival = 1.0
        incidence = np.empty(len(GRID))
        previous = 0.0
        for index, stop in enumerate(GRID):
            in_state = (edge <= previous) if exposed_state else (edge > previous)
            at_risk = (follow > previous) & in_state
            n_risk = int(at_risk.sum())
            events = int((at_risk & merged & (follow <= stop)).sum())
            if n_risk:
                hazard = events / n_risk
                survival *= 1.0 - hazard
            incidence[index] = 1.0 - survival
            previous = stop
        curves.append(incidence)
    return curves[0], curves[1]


def bootstrap(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    generator = np.random.default_rng(SEED)
    repositories = frame["repo_id"].to_numpy()
    unique = np.unique(repositories)
    index_by_repo = {repo: np.flatnonzero(repositories == repo) for repo in unique}

    no_edge = np.empty((BOOTSTRAP_DRAWS, len(GRID)))
    with_edge = np.empty((BOOTSTRAP_DRAWS, len(GRID)))
    for draw in range(BOOTSTRAP_DRAWS):
        picked = generator.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([index_by_repo[repo] for repo in picked])
        sample = frame.iloc[rows]
        low, high = cumulative_incidence(sample)
        no_edge[draw] = low
        with_edge[draw] = high
    return {
        "no_edge_low": np.quantile(no_edge, 0.025, axis=0),
        "no_edge_high": np.quantile(no_edge, 0.975, axis=0),
        "edge_low": np.quantile(with_edge, 0.025, axis=0),
        "edge_high": np.quantile(with_edge, 0.975, axis=0),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = build_cohort()
    no_edge, with_edge = cumulative_incidence(frame)
    bands = bootstrap(frame)

    table = pd.DataFrame(
        {
            "days_since_trigger": GRID,
            "merged_no_edge": no_edge,
            "merged_no_edge_low": bands["no_edge_low"],
            "merged_no_edge_high": bands["no_edge_high"],
            "merged_with_edge": with_edge,
            "merged_with_edge_low": bands["edge_low"],
            "merged_with_edge_high": bands["edge_high"],
        }
    )
    table.to_csv(OUTPUT / "cumulative_merge.csv", index=False)

    summary = {
        "population_prs": int(len(frame)),
        "repositories": int(frame["repo_id"].nunique()),
        "prs_with_any_exact_edge": int(np.isfinite(frame["edge_days"]).sum()),
        "prs_merged_within_horizon": int(frame["merged_in_horizon"].sum()),
        "horizon_days": HORIZON_DAYS,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_unit": "repository",
        "seed": SEED,
        "merged_by_day_30_no_edge": float(no_edge[-1]),
        "merged_by_day_30_with_edge": float(with_edge[-1]),
        "interpretation": (
            "cumulative merge under a time-varying edge split; a pull request "
            "contributes unexposed risk until its own first exact reply; "
            "observational, not a causal effect"
        ),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
