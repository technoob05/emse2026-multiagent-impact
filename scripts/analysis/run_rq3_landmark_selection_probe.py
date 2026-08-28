"""Does the hour-48 landmark condition on something the exposure can move?

The RQ3 design keeps pull requests still open at hour 48, asks whether an exact
reply arrived *by* hour 48, and counts merges only *after* hour 48. The exposure
is therefore measured inside the same window that decides cohort membership. If
a reply changes whether a pull request is still open at hour 48, then "still
open at hour 48" is a collider on the path from exposure to outcome, and the
published estimate can be biased in either direction.

This script answers that objection with three analyses, none of which replaces
the published one:

**Part 1 - sequential landmark.** Keep the same 1,067 pull requests open at hour
48, but measure the exposure only in the window (48, 96] hours and read the
outcome only after hour 96. Cohort membership is fixed before any exposure can
occur, so no post-exposure conditioning is possible. Reported for four exposure
definitions and, separately, for the 958 pull requests that were still unexposed
at hour 48 (the clean landmark subgroup).

**Part 2 - time-varying hazard, no landmark at all.** Follow every cross-product
inline-trigger pull request from its trigger; the reply enters as a time-varying
covariate and the outcome is the merge hazard in each later interval. Nothing is
conditioned on. Extends `run_rq3_extensions.py` with a human-reply exposure, a
g-computation 30-day risk difference on the percentage-point scale the article
uses, and a landmark-free version of Part 1's design.

**Part 3 - measuring the selection directly.** Does an early reply change
whether a pull request is still open at hour 48? Raw contingency, ordered
landmarks at hours 1/6/24 where the exposure strictly precedes the outcome, and
a time-varying hazard of closure.

Nothing here identifies a causal effect.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import build_design_matrices, dmatrices

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from multiagent_impact.cross_agent_review import INTERACTION_CUTOFF  # noqa: E402
from scripts.analysis.run_addressed_edge_landmark_analysis import (  # noqa: E402
    add_pretrigger_features,
    build_base_cohort,
)
from scripts.analysis.run_rq3_extensions import (  # noqa: E402
    BIN_EDGES,
    HORIZON_DAYS,
    whole_population,
)

CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "rq3_landmark_selection"

SEED = 20260826
PERMUTATIONS = 2000

FIRST_LANDMARK_HOURS = 48
SECOND_LANDMARK_HOURS = 96

PRETRIGGER_CONTROLS = [
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
]
BASE_CATEGORICAL = [
    "C(author_agent)",
    "C(trigger_reviewer_agent)",
    "C(trigger_month)",
]
REPLY_SOURCES = ("direct_inline_reply", "subsequent_review", "subsequent_pr_comment")

# Published primary estimate this work is compared against.
PUBLISHED_ESTIMATE = 0.17346523604933012
PUBLISHED_CI = (0.07255437972242951, 0.27437609237623073)
PUBLISHED_N = 1_067
PUBLISHED_EXPOSED = 109


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def response_events() -> pl.DataFrame:
    return pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet")


def clustered_lpm(
    frame: pd.DataFrame, formula: str, exposure: str
) -> tuple[object, pd.Series]:
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )
    if exposure not in model.params.index:
        raise AssertionError(f"Exposure term missing: {exposure}")
    return model, groups


def lpm_row(model: object, groups: pd.Series, exposure: str) -> dict[str, object]:
    interval = model.conf_int().loc[exposure]
    return {
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
    }


def cluster_permutation_p(
    frame: pd.DataFrame, formula: str, exposure: str, observed: float
) -> float:
    """Permute the exposure label across pull requests, holding everything else.

    Repository clusters are respected in the standard errors, not in the
    permutation, which matches the permutation check used for the published
    edge estimate.
    """
    rng = np.random.default_rng(SEED)
    labels = frame[exposure].to_numpy().copy()
    work = frame.copy()
    outcome, design = dmatrices(formula, work, return_type="dataframe")
    y = outcome.iloc[:, 0].to_numpy()
    base = design.copy()
    column = list(base.columns).index(
        exposure if exposure in base.columns else f"{exposure}[T.True]"
    )
    matrix = np.array(base.to_numpy(), copy=True)
    extreme = 0
    for _ in range(PERMUTATIONS):
        matrix[:, column] = rng.permutation(labels).astype(float)
        coefficients, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        if abs(coefficients[column]) >= abs(observed) - 1e-12:
            extreme += 1
    return float((extreme + 1) / (PERMUTATIONS + 1))


# ---------------------------------------------------------------------------
# Part 1: sequential landmark, exposure strictly after cohort membership
# ---------------------------------------------------------------------------


def build_sequential_frame() -> tuple[pd.DataFrame, dict[str, object]]:
    cohort, _ = build_base_cohort()
    enriched, _ = add_pretrigger_features(cohort)

    events = response_events().join(
        cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
        on=["pr_id", "trigger_event_id", "trigger_dt"],
        how="inner",
    )
    window = events.filter(
        (pl.col("hours_after_trigger") > FIRST_LANDMARK_HOURS)
        & (pl.col("hours_after_trigger") <= SECOND_LANDMARK_HOURS)
    )
    if window.filter(
        (pl.col("hours_after_trigger") <= FIRST_LANDMARK_HOURS)
        | (pl.col("hours_after_trigger") > SECOND_LANDMARK_HOURS)
    ).height:
        raise AssertionError("Exposure event outside the (48, 96] window.")

    def flag(frame: pl.DataFrame, name: str) -> pl.DataFrame:
        return frame.select("pr_id").unique().with_columns(pl.lit(True).alias(name))

    exact = flag(
        window.filter(pl.col("response_source") == "direct_inline_reply"),
        "exact_parent_reply_48_96h",
    )
    any_reply = flag(
        window.filter(pl.col("response_source").is_in(REPLY_SOURCES)),
        "any_reply_48_96h",
    )
    human_reply = flag(
        window.filter(
            pl.col("response_source").is_in(REPLY_SOURCES)
            & (pl.col("response_user_type").str.to_lowercase() == "user")
        ),
        "human_reply_48_96h",
    )

    # The published exposure, kept so the shift in the outcome window can be
    # separated from the shift in the exposure window.
    published = (
        events.filter(
            (pl.col("response_source") == "direct_inline_reply")
            & (pl.col("hours_after_trigger") > 0)
            & (pl.col("hours_after_trigger") <= FIRST_LANDMARK_HOURS)
        )
        .select("pr_id")
        .unique()
        .with_columns(pl.lit(True).alias("exact_parent_reply_by_48h"))
    )

    second_landmark = pl.col("trigger_dt") + timedelta(hours=SECOND_LANDMARK_HOURS)
    horizon = pl.col("trigger_dt") + timedelta(days=HORIZON_DAYS)
    frame = (
        enriched.join(exact, on="pr_id", how="left")
        .join(any_reply, on="pr_id", how="left")
        .join(human_reply, on="pr_id", how="left")
        .join(published, on="pr_id", how="left")
        .with_columns(
            [
                pl.col(name).fill_null(False)
                for name in (
                    "exact_parent_reply_48_96h",
                    "any_reply_48_96h",
                    "human_reply_48_96h",
                    "exact_parent_reply_by_48h",
                )
            ]
        )
        .with_columns(
            second_landmark.alias("second_landmark_dt"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > second_landmark)
                & (pl.col("merged_dt") <= horizon)
            ).alias("merged_from_96h_to_30d"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("outcome_landmark_dt"))
                & (pl.col("merged_dt") <= second_landmark)
            ).alias("merged_from_48h_to_96h"),
            (
                pl.col("closed_dt").is_not_null()
                & (pl.col("closed_dt") <= second_landmark)
            ).alias("closed_by_96h"),
        )
    )

    if int(frame["exact_parent_reply_by_48h"].sum()) != PUBLISHED_EXPOSED:
        raise AssertionError("Rebuilt published exposure does not match the artifact.")
    if frame.filter(
        pl.col("merged_from_96h_to_30d")
        & (pl.col("merged_dt") <= pl.col("second_landmark_dt"))
    ).height:
        raise AssertionError("Outcome leakage across the second landmark.")

    pandas_frame = frame.to_pandas()
    for column in (
        "merged_from_48h_to_30d",
        "merged_from_96h_to_30d",
        "merged_from_48h_to_96h",
        "closed_by_96h",
        "exact_parent_reply_48_96h",
        "any_reply_48_96h",
        "human_reply_48_96h",
        "exact_parent_reply_by_48h",
    ):
        pandas_frame[column] = pandas_frame[column].astype(int)

    checks = {
        "cohort_prs": int(len(pandas_frame)),
        "cohort_is_the_published_landmark_cohort": int(len(pandas_frame))
        == PUBLISHED_N,
        "closed_between_hour_48_and_96": int(pandas_frame["closed_by_96h"].sum()),
        "merged_after_hour_96_within_30d": int(
            pandas_frame["merged_from_96h_to_30d"].sum()
        ),
        "published_outcome_positives_48h_to_30d": int(
            pandas_frame["merged_from_48h_to_30d"].sum()
        ),
        "published_outcome_positives_that_merge_by_hour_96": int(
            pandas_frame["merged_from_48h_to_96h"].sum()
        ),
        "exposed_exact_parent_reply_48_96h": int(
            pandas_frame["exact_parent_reply_48_96h"].sum()
        ),
        "exposed_any_reply_48_96h": int(pandas_frame["any_reply_48_96h"].sum()),
        "exposed_human_reply_48_96h": int(pandas_frame["human_reply_48_96h"].sum()),
        "exposed_published_exact_reply_by_48h": int(
            pandas_frame["exact_parent_reply_by_48h"].sum()
        ),
        "unexposed_at_hour_48_subgroup": int(
            (pandas_frame["exact_parent_reply_by_48h"] == 0).sum()
        ),
    }
    return pandas_frame, checks


def fit_sequential(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    samples = [
        (
            "all_open_at_48h",
            frame,
            "no conditioning after hour 48; the exposure cannot have changed "
            "cohort membership",
        ),
        (
            "unexposed_at_48h",
            frame[frame["exact_parent_reply_by_48h"] == 0],
            "pull requests open at hour 48 that had not yet been replied to; the "
            "exposure had not occurred at the landmark",
        ),
        (
            "still_open_at_96h",
            frame[frame["closed_by_96h"] == 0],
            "SECONDARY: conditions on survival past the exposure window, so it "
            "re-introduces exactly the structure being tested",
        ),
    ]
    exposures = [
        ("exact_parent_reply_48_96h", "merged_from_96h_to_30d"),
        ("any_reply_48_96h", "merged_from_96h_to_30d"),
        ("human_reply_48_96h", "merged_from_96h_to_30d"),
        # Same selection-free exposure, but the outcome window opens at the
        # landmark rather than after the exposure window. Contaminated in the
        # other direction, because a merge can precede the reply that scores it;
        # the pair brackets the estimand.
        ("exact_parent_reply_48_96h", "merged_from_48h_to_30d"),
        ("any_reply_48_96h", "merged_from_48h_to_30d"),
        ("human_reply_48_96h", "merged_from_48h_to_30d"),
        # The published exposure, read against three outcome windows, so the
        # effect of moving the outcome window can be separated from the effect
        # of moving the exposure window.
        ("exact_parent_reply_by_48h", "merged_from_48h_to_30d"),
        ("exact_parent_reply_by_48h", "merged_from_48h_to_96h"),
        ("exact_parent_reply_by_48h", "merged_from_96h_to_30d"),
    ]
    for sample_name, sample, note in samples:
        for exposure, outcome in exposures:
            if sample_name == "unexposed_at_48h" and exposure == (
                "exact_parent_reply_by_48h"
            ):
                continue
            if sample_name == "still_open_at_96h" and outcome != (
                "merged_from_96h_to_30d"
            ):
                # In this sample no pull request can merge before hour 96, so
                # the other two outcome windows are degenerate or identical.
                continue
            exposed = int(sample[exposure].sum())
            unexposed = int(len(sample) - exposed)
            row = {
                "sample": sample_name,
                "exposure": exposure,
                "outcome": outcome,
                "exposure_window_hours": (
                    "(48, 96]" if exposure.endswith("48_96h") else "(0, 48]"
                ),
                "outcome_window": {
                    "merged_from_96h_to_30d": "(96h, 30d]",
                    "merged_from_48h_to_30d": "(48h, 30d]",
                    "merged_from_48h_to_96h": "(48h, 96h]",
                }[outcome],
                "prs": int(len(sample)),
                "exposed_prs": exposed,
                "unexposed_prs": unexposed,
                "exposed_outcome_rate": (
                    float(sample.loc[sample[exposure] == 1, outcome].mean())
                    if exposed
                    else float("nan")
                ),
                "unexposed_outcome_rate": float(
                    sample.loc[sample[exposure] == 0, outcome].mean()
                ),
                "selection_free": sample_name != "still_open_at_96h",
                "note": note,
            }
            if exposed < 2 or unexposed < 2:
                row.update(
                    {
                        "estimate": float("nan"),
                        "ci_low": float("nan"),
                        "ci_high": float("nan"),
                        "p_value": float("nan"),
                        "n_prs": 0,
                        "repositories": 0,
                        "estimable": False,
                        "permutation_p": float("nan"),
                    }
                )
                rows.append(row)
                continue
            formula = f"{outcome} ~ " + " + ".join(
                [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
            )
            model, groups = clustered_lpm(sample, formula, exposure)
            row.update(lpm_row(model, groups, exposure))
            row["estimable"] = True
            row["formula"] = formula
            row["permutation_p"] = cluster_permutation_p(
                sample, formula, exposure, float(model.params[exposure])
            )
            rows.append(row)
    result = pd.DataFrame(rows)
    replication = result[
        (result["sample"] == "all_open_at_48h")
        & (result["exposure"] == "exact_parent_reply_by_48h")
        & (result["outcome"] == "merged_from_48h_to_30d")
    ]
    if len(replication) != 1 or not np.isclose(
        float(replication["estimate"].iloc[0]), PUBLISHED_ESTIMATE, atol=1e-12
    ):
        raise AssertionError(
            "This script does not reproduce the published primary estimate on the "
            "same cohort, so nothing below can be compared with it."
        )
    result["published_estimate"] = PUBLISHED_ESTIMATE
    result["difference_from_published"] = result["estimate"] - PUBLISHED_ESTIMATE
    result["interpretation"] = (
        "observational later-merge probability difference; not a causal effect"
    )
    return result


# ---------------------------------------------------------------------------
# Part 2: time-varying hazard on the whole population, no landmark
# ---------------------------------------------------------------------------


def first_reply_times(cohort: pl.DataFrame) -> pl.DataFrame:
    events = response_events().join(
        cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
        on=["pr_id", "trigger_event_id", "trigger_dt"],
        how="inner",
    )
    exact = (
        events.filter(
            (pl.col("response_source") == "direct_inline_reply")
            & (pl.col("hours_after_trigger") > 0)
        )
        .group_by("pr_id")
        .agg(pl.col("response_dt").min().alias("first_exact_dt"))
    )
    human = (
        events.filter(
            pl.col("response_source").is_in(REPLY_SOURCES)
            & (pl.col("hours_after_trigger") > 0)
            & (pl.col("response_user_type").str.to_lowercase() == "user")
        )
        .group_by("pr_id")
        .agg(pl.col("response_dt").min().alias("first_human_dt"))
    )
    return exact.join(human, on="pr_id", how="full", coalesce=True)


def build_person_period(cohort: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per pull request per interval it is still at risk in."""
    frame = cohort.join(first_reply_times(cohort), on="pr_id", how="left")
    horizon = pl.col("trigger_dt") + timedelta(days=HORIZON_DAYS)
    frame = (
        frame.with_columns(
            pl.min_horizontal(
                pl.coalesce([pl.col("closed_dt"), horizon]),
                horizon,
                pl.lit(INTERACTION_CUTOFF),
            ).alias("exit_dt")
        )
        .with_columns(
            (
                (pl.col("exit_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
            ).alias("exit_days"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("trigger_dt"))
                & (pl.col("merged_dt") <= horizon)
            ).alias("merged_in_horizon"),
            (
                pl.col("closed_dt").is_not_null()
                & (pl.col("closed_dt") > pl.col("trigger_dt"))
                & (pl.col("closed_dt") <= horizon)
            ).alias("closed_in_horizon"),
        )
        .with_columns(
            pl.when(pl.col("merged_in_horizon"))
            .then(
                (pl.col("merged_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 86400.0
            )
            .otherwise(None)
            .alias("merge_days"),
            (
                (pl.col("first_exact_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 86400.0
            ).alias("exact_days"),
            (
                (pl.col("first_human_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 86400.0
            ).alias("human_days"),
        )
        .with_columns(
            pl.when(pl.col("merged_in_horizon"))
            .then(pl.col("merge_days"))
            .otherwise(pl.col("exit_days"))
            .clip(0.0, float(HORIZON_DAYS))
            .alias("follow_up_days")
        )
    )

    pandas_frame = frame.to_pandas()
    rows = []
    for record in pandas_frame.itertuples(index=False):
        end = float(record.follow_up_days)
        if end <= 0:
            continue
        merged = bool(record.merged_in_horizon)
        closed = bool(record.closed_in_horizon)
        for index in range(len(BIN_EDGES) - 1):
            low, high = BIN_EDGES[index], BIN_EDGES[index + 1]
            if low >= end:
                break
            merged_here = int(merged and low < end <= high)
            closed_here = int(closed and low < float(record.exit_days) <= high)
            rows.append(
                {
                    "pr_id": record.pr_id,
                    "repo_id": record.repo_id,
                    "author_agent": record.author_agent,
                    "trigger_reviewer_agent": record.trigger_reviewer_agent,
                    "trigger_month": record.trigger_month,
                    "bin_index": index,
                    "bin_start_days": low,
                    "edge_active": int(
                        not pd.isna(record.exact_days)
                        and float(record.exact_days) <= low
                    ),
                    "human_reply_active": int(
                        not pd.isna(record.human_days)
                        and float(record.human_days) <= low
                    ),
                    "late_edge_active": int(
                        not pd.isna(record.exact_days)
                        and float(record.exact_days) > 2.0
                        and float(record.exact_days) <= low
                    ),
                    "merged_in_bin": merged_here,
                    "closed_in_bin": closed_here,
                }
            )
            if merged_here:
                break
    return pd.DataFrame(rows), pandas_frame


def fit_hazard(
    person_period: pd.DataFrame,
    controls: pd.DataFrame,
    exposure: str,
    outcome: str,
    label: str,
    note: str,
) -> dict[str, object]:
    merged = person_period.merge(controls, on="pr_id", how="left", validate="m:1")
    formula = f"{outcome} ~ " + " + ".join(
        [exposure, "C(bin_index)", *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    endog, design = dmatrices(formula, merged, return_type="dataframe")
    groups = merged.loc[design.index, "repo_id"]
    model = sm.GLM(endog.iloc[:, 0], design, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    interval = model.conf_int().loc[exposure]
    return {
        "analysis": label,
        "exposure": exposure,
        "outcome": outcome,
        "hazard_odds_ratio": float(np.exp(model.params[exposure])),
        "or_ci_low": float(np.exp(interval.iloc[0])),
        "or_ci_high": float(np.exp(interval.iloc[1])),
        "p_value": float(model.pvalues[exposure]),
        "person_period_rows": int(model.nobs),
        "prs": int(merged["pr_id"].nunique()),
        "repositories": int(groups.nunique()),
        "exposed_person_period_rows": int(merged[exposure].sum()),
        "formula": formula,
        "note": note,
    }


def g_computation(
    person_period: pd.DataFrame, controls: pd.DataFrame, exposure: str
) -> dict[str, object]:
    """Model-based 30-day cumulative merge risk, exposed against unexposed.

    Puts the hazard model on the percentage-point scale the article uses, so it
    can be compared with the +17.3-point landmark contrast. This is a
    standardisation over the observed covariate distribution under a fully
    hypothetical exposure pattern, not an identified causal contrast.
    """
    merged = person_period.merge(controls, on="pr_id", how="left", validate="m:1")
    formula = "merged_in_bin ~ " + " + ".join(
        [exposure, "C(bin_index)", *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    endog, design = dmatrices(formula, merged, return_type="dataframe")
    groups = merged.loc[design.index, "repo_id"]
    model = sm.GLM(endog.iloc[:, 0], design, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": groups}
    )
    design_info = design.design_info

    covariates = merged.drop_duplicates("pr_id").reset_index(drop=True)
    bins = len(BIN_EDGES) - 1
    grid = covariates.loc[covariates.index.repeat(bins)].reset_index(drop=True)
    grid["bin_index"] = np.tile(np.arange(bins), len(covariates))
    grid["merged_in_bin"] = 0

    risks = {}
    for value in (0, 1):
        grid[exposure] = value
        matrix = build_design_matrices([design_info], grid, return_type="dataframe")[0]
        hazard = np.asarray(model.predict(matrix)).reshape(len(covariates), bins)
        risks[value] = float(np.mean(1.0 - np.prod(1.0 - hazard, axis=1)))
    return {
        "exposure": exposure,
        "standardised_30d_merge_risk_unexposed": risks[0],
        "standardised_30d_merge_risk_exposed": risks[1],
        "risk_difference_points": (risks[1] - risks[0]) * 100.0,
        "prs": int(len(covariates)),
        "note": (
            "standardised over the whole population under always-exposed against "
            "never-exposed; hypothetical, and not an identified causal contrast"
        ),
    }


# ---------------------------------------------------------------------------
# Part 3: measuring the selection itself
# ---------------------------------------------------------------------------


def selection_tables(
    cohort: pl.DataFrame, controls: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    events = response_events().join(
        cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
        on=["pr_id", "trigger_event_id", "trigger_dt"],
        how="inner",
    )
    exact = (
        events.filter(
            (pl.col("response_source") == "direct_inline_reply")
            & (pl.col("hours_after_trigger") > 0)
        )
        .group_by("pr_id")
        .agg(pl.col("hours_after_trigger").min().alias("first_exact_hours"))
    )
    human = (
        events.filter(
            pl.col("response_source").is_in(REPLY_SOURCES)
            & (pl.col("hours_after_trigger") > 0)
            & (pl.col("response_user_type").str.to_lowercase() == "user")
        )
        .group_by("pr_id")
        .agg(pl.col("hours_after_trigger").min().alias("first_human_hours"))
    )
    frame = (
        cohort.join(exact, on="pr_id", how="left")
        .join(human, on="pr_id", how="left")
        .with_columns(
            (
                (pl.col("closed_dt") - pl.col("trigger_dt")).dt.total_seconds() / 3600.0
            ).alias("closed_hours")
        )
        .to_pandas()
    )

    raw_rows = []
    for exposure_column, exposure_label in (
        ("first_exact_hours", "exact_parent_reply"),
        ("first_human_hours", "any_human_reply"),
    ):
        replied = frame[exposure_column].notna() & (
            frame[exposure_column] <= FIRST_LANDMARK_HOURS
        )
        closed = frame["closed_hours"].notna() & (
            frame["closed_hours"] <= FIRST_LANDMARK_HOURS
        )
        for value, label in ((True, "replied_by_48h"), (False, "no_reply_by_48h")):
            cell = frame[replied == value]
            raw_rows.append(
                {
                    "table": "raw_unordered",
                    "exposure": exposure_label,
                    "group": label,
                    "prs": int(len(cell)),
                    "closed_by_48h": int(closed[replied == value].sum()),
                    "closed_by_48h_rate": float(closed[replied == value].mean()),
                    "still_open_at_48h_rate": float(
                        1.0 - closed[replied == value].mean()
                    ),
                    "caveat": (
                        "unordered: a pull request that closed at hour 3 had little "
                        "opportunity to receive a reply by hour 48, so this "
                        "association runs in both directions"
                    ),
                }
            )
    raw = pd.DataFrame(raw_rows)

    exact_all = int(
        (
            frame["first_exact_hours"].notna()
            & (frame["first_exact_hours"] <= FIRST_LANDMARK_HOURS)
        ).sum()
    )
    survivors = frame["closed_hours"].isna() | (
        frame["closed_hours"] > FIRST_LANDMARK_HOURS
    )
    exact_survivors = int(
        (
            survivors
            & frame["first_exact_hours"].notna()
            & (frame["first_exact_hours"] <= FIRST_LANDMARK_HOURS)
        ).sum()
    )
    raw = pd.concat(
        [
            raw,
            pd.DataFrame(
                [
                    {
                        "table": "exposure_prevalence_shift",
                        "exposure": "exact_parent_reply",
                        "group": "whole_population",
                        "prs": int(len(frame)),
                        "closed_by_48h": exact_all,
                        "closed_by_48h_rate": exact_all / len(frame),
                        "still_open_at_48h_rate": float("nan"),
                        "caveat": (
                            "closed_by_48h holds the exposed count and "
                            "closed_by_48h_rate the exposure prevalence in this row"
                        ),
                    },
                    {
                        "table": "exposure_prevalence_shift",
                        "exposure": "exact_parent_reply",
                        "group": "survivors_to_hour_48",
                        "prs": int(survivors.sum()),
                        "closed_by_48h": exact_survivors,
                        "closed_by_48h_rate": exact_survivors / int(survivors.sum()),
                        "still_open_at_48h_rate": float("nan"),
                        "caveat": (
                            "if the landmark gate were independent of the exposure "
                            "these two prevalences would agree"
                        ),
                    },
                ]
            ),
        ],
        ignore_index=True,
    )

    ordered_rows = []
    for landmark in (1, 6, 24):
        open_at_landmark = frame["closed_hours"].isna() | (
            frame["closed_hours"] > landmark
        )
        sample = frame[open_at_landmark].copy()
        for exposure_column, exposure_label in (
            ("first_exact_hours", "exact_parent_reply"),
            ("first_human_hours", "any_human_reply"),
        ):
            sample["exposure"] = (
                sample[exposure_column].notna()
                & (sample[exposure_column] <= landmark)
            ).astype(int)
            sample["closed_before_48h"] = (
                sample["closed_hours"].notna()
                & (sample["closed_hours"] <= FIRST_LANDMARK_HOURS)
            ).astype(int)
            exposed = int(sample["exposure"].sum())
            row = {
                "exposure_landmark_hours": landmark,
                "exposure": exposure_label,
                "outcome": "closed_before_hour_48",
                "prs_open_at_landmark": int(len(sample)),
                "exposed_prs": exposed,
                "exposed_closed_rate": (
                    float(sample.loc[sample["exposure"] == 1, "closed_before_48h"].mean())
                    if exposed
                    else float("nan")
                ),
                "unexposed_closed_rate": float(
                    sample.loc[sample["exposure"] == 0, "closed_before_48h"].mean()
                ),
            }
            row["raw_difference"] = (
                row["exposed_closed_rate"] - row["unexposed_closed_rate"]
            )
            if exposed >= 2:
                model_frame = sample.merge(controls, on="pr_id", how="left")
                formula = "closed_before_48h ~ " + " + ".join(
                    ["exposure", *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
                )
                model, groups = clustered_lpm(model_frame, formula, "exposure")
                row.update(lpm_row(model, groups, "exposure"))
            ordered_rows.append(row)
    ordered = pd.DataFrame(ordered_rows)
    ordered["interpretation"] = (
        "adjusted difference in the probability of closing before hour 48; a value "
        "near zero means the hour-48 cohort gate is close to unaffected by the "
        "exposure and the collider concern is small"
    )
    return raw, ordered


# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    sequential_frame, sequential_checks = build_sequential_frame()
    sequential = fit_sequential(sequential_frame)
    sequential.to_csv(OUTPUT / "sequential_landmark_estimates.csv", index=False)

    cohort = whole_population()
    person_period, pr_level = build_person_period(cohort)
    controls = add_pretrigger_features(cohort)[0].to_pandas()[
        ["pr_id", *PRETRIGGER_CONTROLS]
    ]

    hazard_rows = [
        fit_hazard(
            person_period,
            controls,
            "edge_active",
            "merged_in_bin",
            "whole_population_merge_hazard",
            "replicates run_rq3_extensions.py specification C; no conditioning",
        ),
        fit_hazard(
            person_period,
            controls,
            "human_reply_active",
            "merged_in_bin",
            "whole_population_merge_hazard_human_reply",
            "any human reply rather than the exact-parent edge",
        ),
        fit_hazard(
            person_period[person_period["bin_start_days"] >= 2.0],
            controls,
            "late_edge_active",
            "merged_in_bin",
            "post_hour_48_person_time_merge_hazard",
            "person-time after hour 48 only, exposure counted only if the reply "
            "arrived after hour 48; the landmark-free form of Part 1",
        ),
        fit_hazard(
            person_period,
            controls,
            "edge_active",
            "closed_in_bin",
            "whole_population_closure_hazard",
            "Part 3 companion: does the reply move the exit hazard at all",
        ),
    ]
    hazard = pd.DataFrame(hazard_rows)
    hazard.to_csv(OUTPUT / "whole_population_hazards.csv", index=False)

    standardised = pd.DataFrame(
        [
            g_computation(person_period, controls, "edge_active"),
            g_computation(person_period, controls, "human_reply_active"),
        ]
    )
    standardised.to_csv(OUTPUT / "standardised_risk_difference.csv", index=False)

    raw_selection, ordered_selection = selection_tables(cohort, controls)
    raw_selection.to_csv(OUTPUT / "selection_raw_contingency.csv", index=False)
    ordered_selection.to_csv(OUTPUT / "selection_ordered_landmarks.csv", index=False)

    primary_sequential = sequential[
        (sequential["sample"] == "unexposed_at_48h")
        & (sequential["exposure"] == "human_reply_48_96h")
    ].iloc[0]
    summary = {
        "published_reference": {
            "estimate_points": PUBLISHED_ESTIMATE * 100.0,
            "ci_points": [PUBLISHED_CI[0] * 100.0, PUBLISHED_CI[1] * 100.0],
            "prs": PUBLISHED_N,
            "exposed_prs": PUBLISHED_EXPOSED,
        },
        "part1_sequential_landmark": sequential_checks,
        "part1_best_powered_selection_free": {
            "sample": primary_sequential["sample"],
            "exposure": primary_sequential["exposure"],
            "exposed_prs": int(primary_sequential["exposed_prs"]),
            "estimate_points": float(primary_sequential["estimate"]) * 100.0,
            "ci_points": [
                float(primary_sequential["ci_low"]) * 100.0,
                float(primary_sequential["ci_high"]) * 100.0,
            ],
            "p_value": float(primary_sequential["p_value"]),
            "permutation_p": float(primary_sequential["permutation_p"]),
        },
        "part2_whole_population": hazard.drop(columns=["formula"]).to_dict("records"),
        "part2_standardised": standardised.to_dict("records"),
        "part3_raw_selection": raw_selection.drop(columns=["caveat"]).to_dict(
            "records"
        ),
        "part3_ordered_selection": ordered_selection.drop(
            columns=["interpretation"]
        ).to_dict("records"),
        "person_period_rows": int(len(person_period)),
        "prs_in_hazard_population": int(pr_level.shape[0]),
        "seed": SEED,
        "permutations": PERMUTATIONS,
        "scope": (
            "design probe for the RQ3 landmark; every estimate is observational "
            "and none identifies a causal effect"
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    pd.set_option("display.width", 200)
    print(json.dumps(sequential_checks, indent=2))
    print()
    print(
        sequential[
            [
                "sample",
                "exposure",
                "outcome_window",
                "prs",
                "exposed_prs",
                "exposed_outcome_rate",
                "unexposed_outcome_rate",
                "estimate",
                "ci_low",
                "ci_high",
                "p_value",
                "permutation_p",
            ]
        ].to_string(index=False)
    )
    print()
    print(
        hazard[
            [
                "analysis",
                "exposure",
                "outcome",
                "hazard_odds_ratio",
                "or_ci_low",
                "or_ci_high",
                "p_value",
                "prs",
            ]
        ].to_string(index=False)
    )
    print()
    print(standardised.drop(columns=["note"]).to_string(index=False))
    print()
    print(raw_selection.drop(columns=["caveat"]).to_string(index=False))
    print()
    print(
        ordered_selection[
            [
                "exposure_landmark_hours",
                "exposure",
                "prs_open_at_landmark",
                "exposed_prs",
                "exposed_closed_rate",
                "unexposed_closed_rate",
                "raw_difference",
                "estimate",
                "ci_low",
                "ci_high",
                "p_value",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
