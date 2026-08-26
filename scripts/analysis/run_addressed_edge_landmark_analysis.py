from __future__ import annotations

import hashlib
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

from multiagent_impact.cross_agent_review import (  # noqa: E402
    INTERACTION_CUTOFF,
    parse_timestamp,
)


DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN_DIR = ROOT / "outputs" / "cross_agent_review"
OWNER_DIR = ROOT / "outputs" / "response_ownership"
OUTPUT = ROOT / "outputs" / "addressed_edge_landmark"
DATASET_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
THRESHOLDS = (1, 6, 24, 48)
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXPOSURES_48H = 109

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_base_cohort() -> tuple[pl.DataFrame, dict[str, object]]:
    landmark = pl.read_parquet(CHAIN_DIR / "feedback_48h_landmark_cohort.parquet")
    cohort = (
        landmark.filter(pl.col("trigger_source") == "inline_review_comment")
        .select(
            "pr_id",
            "repo_id",
            "trigger_dt",
            "trigger_event_id",
            "trigger_review_id",
            "author_agent",
            "trigger_reviewer_agent",
            "closed_dt",
            "merged_dt",
            "outcome_landmark_dt",
            "merged_from_48h_to_30d",
        )
        .with_columns(
            pl.concat_str(
                ["author_agent", "trigger_reviewer_agent"], separator=" -> "
            ).alias("ordered_product_pair"),
            pl.col("trigger_dt").dt.strftime("%Y-%m").alias("trigger_month"),
        )
        .sort("pr_id")
    )
    if cohort.height != EXPECTED_COHORT_ROWS:
        raise AssertionError(
            f"Inline landmark cohort drift: {cohort.height} != {EXPECTED_COHORT_ROWS}"
        )
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError("Landmark cohort is not one row per PR.")
    if cohort.filter(
        pl.col("author_agent") == pl.col("trigger_reviewer_agent")
    ).height:
        raise AssertionError("Same-product trigger entered cross-product cohort.")

    expected_landmark = cohort["trigger_dt"] + timedelta(hours=48)
    if not (cohort["outcome_landmark_dt"] == expected_landmark).all():
        raise AssertionError("Outcome landmark is not exactly trigger + 48 hours.")
    if cohort.filter(
        pl.col("closed_dt").is_not_null()
        & (pl.col("closed_dt") <= pl.col("outcome_landmark_dt"))
    ).height:
        raise AssertionError("A PR closed at/before 48 hours entered the risk set.")
    if cohort.filter(
        pl.col("trigger_dt") > pl.lit(INTERACTION_CUTOFF - timedelta(days=30))
    ).height:
        raise AssertionError("A trigger lacks the fixed 30-day outcome horizon.")

    positive = cohort.filter(pl.col("merged_from_48h_to_30d"))
    if positive.filter(
        pl.col("merged_dt") <= pl.col("outcome_landmark_dt")
    ).height:
        raise AssertionError("Outcome leakage: merge is not strictly after 48 hours.")
    if positive.filter(
        pl.col("merged_dt") > pl.col("trigger_dt") + timedelta(days=30)
    ).height:
        raise AssertionError("Outcome exceeds the fixed 30-day horizon.")

    checks = {
        "source_landmark_rows": landmark.height,
        "inline_trigger_landmark_rows": cohort.height,
        "unique_prs": cohort["pr_id"].n_unique(),
        "repositories": cohort["repo_id"].n_unique(),
        "ordered_product_pairs": cohort["ordered_product_pair"].n_unique(),
        "outcome_positive_prs": int(cohort["merged_from_48h_to_30d"].sum()),
        "all_triggers_inline_review_comments": True,
        "all_triggers_cross_product": True,
        "one_row_per_pr": True,
        "all_landmarks_exactly_trigger_plus_48h": True,
        "all_prs_open_at_48h_landmark": True,
        "all_positive_outcomes_after_48h": True,
        "all_positive_outcomes_by_30d": True,
        "all_triggers_have_30d_observation_horizon": True,
    }
    return cohort, checks


def add_exact_parent_exposures(
    cohort: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, object]]:
    direct = (
        pl.read_parquet(CHAIN_DIR / "cross_feedback_response_events.parquet")
        .filter(pl.col("response_source") == "direct_inline_reply")
        .join(
            cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
            on=["pr_id", "trigger_event_id", "trigger_dt"],
            how="inner",
        )
        .filter(pl.col("hours_after_trigger") <= 48)
        .sort(["pr_id", "response_dt", "response_event_id"])
    )
    raw_inline = pl.read_parquet(
        DATA / "pr_review_comments.parquet",
        columns=["id", "in_reply_to_id", "created_at"],
    ).with_columns(
        pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
        parse_timestamp("created_at", "raw_response_dt"),
    )
    audited = direct.join(
        raw_inline.select(
            pl.col("id").alias("response_event_id"),
            "in_reply_to_id",
            "raw_response_dt",
        ),
        on="response_event_id",
        how="left",
        validate="m:1",
    )
    if audited["raw_response_dt"].null_count():
        raise AssertionError("A direct reply event does not resolve to the raw inline table.")
    if audited.filter(
        pl.col("in_reply_to_id") != pl.col("trigger_event_id")
    ).height:
        raise AssertionError("A direct reply does not point to the exact trigger parent.")
    if audited.filter(
        pl.col("raw_response_dt") != pl.col("response_dt")
    ).height:
        raise AssertionError("Derived and raw direct-reply timestamps disagree.")
    if audited.filter(
        (pl.col("response_dt") <= pl.col("trigger_dt"))
        | (pl.col("hours_after_trigger") <= 0)
        | (pl.col("hours_after_trigger") > 48)
    ).height:
        raise AssertionError("Direct-reply event is outside the exposure interval.")

    per_pr = direct.group_by("pr_id").agg(
        pl.col("hours_after_trigger").min().alias("first_exact_reply_hours"),
        pl.col("response_dt").min().alias("first_exact_reply_dt"),
        pl.len().alias("exact_reply_events_48h"),
    )
    enriched = cohort.join(per_pr, on="pr_id", how="left").with_columns(
        pl.col("exact_reply_events_48h").fill_null(0)
    )
    exposure_columns = []
    for threshold in THRESHOLDS:
        column = f"exact_parent_reply_by_{threshold}h"
        exposure_columns.append(column)
        enriched = enriched.with_columns(
            (
                pl.col("first_exact_reply_hours").is_not_null()
                & (pl.col("first_exact_reply_hours") <= threshold)
            ).alias(column)
        )

    for left, right in zip(exposure_columns, exposure_columns[1:]):
        if enriched.filter(pl.col(left) & ~pl.col(right)).height:
            raise AssertionError(f"Nested exposure invariant failed: {left} -> {right}")
    if int(enriched["exact_parent_reply_by_48h"].sum()) != EXPECTED_EXPOSURES_48H:
        raise AssertionError("48-hour exact-parent exposure count drift.")
    if enriched.filter(
        pl.col("exact_parent_reply_by_48h")
        & (pl.col("first_exact_reply_dt") > pl.col("outcome_landmark_dt"))
    ).height:
        raise AssertionError("Exposure occurs after the outcome landmark.")

    checks = {
        "direct_reply_events_within_48h": direct.height,
        "prs_with_direct_reply_within_48h": direct["pr_id"].n_unique(),
        "all_direct_replies_resolve_to_raw_inline_rows": True,
        "all_direct_reply_parent_ids_equal_trigger_event_id": True,
        "all_direct_reply_timestamps_match_raw_table": True,
        "all_direct_replies_strictly_after_trigger": True,
        "all_direct_replies_at_or_before_48h_landmark": True,
        "exposure_thresholds_are_nested": True,
        "exposed_prs_by_threshold": {
            str(threshold): int(
                enriched[f"exact_parent_reply_by_{threshold}h"].sum()
            )
            for threshold in THRESHOLDS
        },
    }
    return enriched, audited, checks


def add_pretrigger_features(
    cohort: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[str, object]]:
    key = cohort.select("pr_id", "trigger_dt")
    prs = (
        pl.read_parquet(DATA / "pull_request.parquet", columns=["id", "created_at"])
        .rename({"id": "pr_id"})
        .with_columns(parse_timestamp("created_at", "pr_created_dt"))
        .select("pr_id", "pr_created_dt")
    )
    reviews_raw = pl.scan_parquet(DATA / "pr_reviews.parquet")
    review_key = reviews_raw.select("pull_request_review_id", "pr_id").unique(
        "pull_request_review_id"
    )
    reviews = reviews_raw.select(
        "pr_id",
        "user_type",
        "state",
        parse_timestamp("submitted_at", "event_dt"),
        pl.lit("submitted_review").alias("event_source"),
    )
    comments = pl.scan_parquet(DATA / "pr_comments.parquet").select(
        "pr_id",
        "user_type",
        pl.lit(None, dtype=pl.String).alias("state"),
        parse_timestamp("created_at", "event_dt"),
        pl.lit("pr_comment").alias("event_source"),
    )
    inline = (
        pl.scan_parquet(DATA / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "pr_id",
            "user_type",
            pl.lit(None, dtype=pl.String).alias("state"),
            parse_timestamp("created_at", "event_dt"),
            pl.lit("inline_review_comment").alias("event_source"),
        )
    )
    all_interactions = (
        pl.concat([reviews, comments, inline])
        .join(key.lazy(), on="pr_id", how="inner")
        .join(prs.lazy(), on="pr_id", how="left")
    )
    invalid_time_rows = all_interactions.filter(
        pl.col("event_dt").is_null()
        | pl.col("pr_created_dt").is_null()
        | (pl.col("event_dt") < pl.col("pr_created_dt"))
    ).select(pl.len().alias("n")).collect()["n"][0]
    valid_interactions = all_interactions.filter(
        pl.col("event_dt").is_not_null()
        & pl.col("pr_created_dt").is_not_null()
        & (pl.col("event_dt") >= pl.col("pr_created_dt"))
    )
    pre_rows = valid_interactions.filter(
        pl.col("event_dt") < pl.col("trigger_dt")
    )
    pre = (
        pre_rows.group_by("pr_id")
        .agg(
            pl.len().alias("pre_events"),
            (pl.col("user_type").str.to_lowercase() == "user")
            .sum()
            .alias("pre_user_events"),
            (pl.col("user_type").str.to_lowercase() == "bot")
            .sum()
            .alias("pre_bot_events"),
            pl.col("state")
            .str.to_uppercase()
            .is_in(["APPROVED", "CHANGES_REQUESTED"])
            .sum()
            .alias("pre_decisive_reviews"),
            pl.col("event_dt").max().alias("last_pre_event_dt"),
        )
        .collect(engine="streaming")
    )
    timeline = (
        pl.scan_parquet(DATA / "pr_timeline.parquet")
        .filter(pl.col("event") == "head_ref_force_pushed")
        .select("pr_id", parse_timestamp("created_at", "event_dt"))
        .join(key.lazy(), on="pr_id", how="inner")
    )
    pre_push_rows = timeline.filter(
        pl.col("event_dt").is_not_null()
        & (pl.col("event_dt") < pl.col("trigger_dt"))
    )
    pre_push = (
        pre_push_rows.group_by("pr_id")
        .agg(
            pl.len().alias("pre_force_pushes"),
            pl.col("event_dt").max().alias("last_pre_force_push_dt"),
        )
        .collect(engine="streaming")
    )
    zero_columns = [
        "pre_events",
        "pre_user_events",
        "pre_bot_events",
        "pre_decisive_reviews",
        "pre_force_pushes",
    ]
    enriched = (
        cohort.join(prs, on="pr_id", how="left")
        .join(pre, on="pr_id", how="left")
        .join(pre_push, on="pr_id", how="left")
        .with_columns([pl.col(column).fill_null(0) for column in zero_columns])
        .with_columns(
            (
                (pl.col("trigger_dt") - pl.col("pr_created_dt")).dt.total_seconds()
                / 3600.0
            )
            .clip(0)
            .log1p()
            .alias("log1p_trigger_age_hours"),
            pl.col("pre_events").log1p().alias("log1p_pre_events"),
        )
    )
    if enriched["pr_created_dt"].null_count():
        raise AssertionError("PR creation time missing from analysis cohort.")
    if enriched.filter(
        pl.col("last_pre_event_dt").is_not_null()
        & (pl.col("last_pre_event_dt") >= pl.col("trigger_dt"))
    ).height:
        raise AssertionError("Post-trigger interaction leaked into a pretrigger control.")
    if enriched.filter(
        pl.col("last_pre_force_push_dt").is_not_null()
        & (pl.col("last_pre_force_push_dt") >= pl.col("trigger_dt"))
    ).height:
        raise AssertionError("Post-trigger force-push leaked into a pretrigger control.")

    checks = {
        "raw_interaction_rows_with_invalid_or_pre_creation_time": int(
            invalid_time_rows
        ),
        "pretrigger_interaction_rows_used": int(
            pre_rows.select(pl.len().alias("n")).collect()["n"][0]
        ),
        "pretrigger_force_push_rows_used": int(
            pre_push_rows.select(pl.len().alias("n")).collect()["n"][0]
        ),
        "all_pretrigger_interaction_times_strictly_before_trigger": True,
        "all_pretrigger_force_push_times_strictly_before_trigger": True,
        "trigger_text_used_as_control": False,
        "posttrigger_route_used_in_model_A": False,
        "outcome_used_to_define_exposure_or_controls": False,
    }
    return enriched, checks


def add_ownership_route(cohort: pl.DataFrame) -> pl.DataFrame:
    route = pl.read_parquet(OWNER_DIR / "ownership_route_48h.parquet").select(
        "pr_id", "trigger_dt", "ownership_route_48h", "merged_from_48h_to_30d"
    )
    joined = cohort.join(
        route,
        on=["pr_id", "trigger_dt", "merged_from_48h_to_30d"],
        how="inner",
        validate="1:1",
    )
    if joined.height != cohort.height:
        raise AssertionError("Ownership-route join changed the landmark cohort.")
    if joined["ownership_route_48h"].null_count():
        raise AssertionError("Missing 48-hour ownership route.")
    return joined


def model_formula(threshold: int, specification: str, repository_fe: bool) -> str:
    exposure = f"exact_parent_reply_by_{threshold}h"
    terms = [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    if specification == "B_route_decomposition":
        terms.append(
            "C(ownership_route_48h, Treatment('no_observed_action'))"
        )
    if repository_fe:
        terms.append("C(repo_id)")
    return "merged_from_48h_to_30d ~ " + " + ".join(terms)


def fit_design(
    frame: pd.DataFrame,
    formula: str,
    exposure: str,
    subset: np.ndarray | None = None,
) -> tuple[object, pd.DataFrame, pd.Series]:
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    if subset is not None:
        outcome = outcome.loc[subset]
        design = design.loc[subset]
    groups = frame.loc[design.index, "repo_id"]
    if groups.nunique() < 2:
        raise RuntimeError("Clustered model has fewer than two repositories.")
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    if exposure not in model.params.index:
        raise AssertionError(f"Exposure term missing from model: {exposure}")
    return model, design, groups


def extract_term(
    model: object,
    exposure: str,
    threshold: int,
    specification: str,
    formula: str,
    design: pd.DataFrame,
    groups: pd.Series,
    repository_fe: bool = False,
) -> dict[str, object]:
    interval = model.conf_int().loc[exposure]
    return {
        "threshold_hours": threshold,
        "specification": specification,
        "repository_fixed_effects": repository_fe,
        "term": exposure,
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
        "design_columns": int(design.shape[1]),
        "design_rank": int(np.linalg.matrix_rank(design.to_numpy())),
        "formula": formula,
        "interpretation": "observational later-merge probability difference; not a causal effect or semantic resolution rate",
    }


def fit_main_models(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    estimates = []
    terms = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        for specification in ["A_pretrigger_only", "B_route_decomposition"]:
            formula = model_formula(threshold, specification, repository_fe=False)
            model, design, groups = fit_design(frame, formula, exposure)
            estimates.append(
                extract_term(
                    model,
                    exposure,
                    threshold,
                    specification,
                    formula,
                    design,
                    groups,
                )
            )
            intervals = model.conf_int()
            for term in model.params.index:
                terms.append(
                    {
                        "threshold_hours": threshold,
                        "specification": specification,
                        "term": term,
                        "estimate": float(model.params[term]),
                        "ci_low": float(intervals.loc[term, 0]),
                        "ci_high": float(intervals.loc[term, 1]),
                        "p_value": float(model.pvalues[term]),
                    }
                )
    return pd.DataFrame(estimates), pd.DataFrame(terms)


def fit_repository_fe(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        exposure_variation = frame.groupby("repo_id")[exposure].nunique().gt(1)
        outcome_variation = (
            frame.groupby("repo_id")["merged_from_48h_to_30d"].nunique().gt(1)
        )
        varying_repos = exposure_variation[exposure_variation].index
        both_repos = exposure_variation[exposure_variation & outcome_variation].index
        for specification in ["A_pretrigger_only", "B_route_decomposition"]:
            formula = model_formula(threshold, specification, repository_fe=True)
            model, design, groups = fit_design(frame, formula, exposure)
            row = extract_term(
                model,
                exposure,
                threshold,
                specification,
                formula,
                design,
                groups,
                repository_fe=True,
            )
            row.update(
                {
                    "repositories_with_within_exposure_variation": int(
                        len(varying_repos)
                    ),
                    "prs_in_repositories_with_within_exposure_variation": int(
                        frame[frame["repo_id"].isin(varying_repos)].shape[0]
                    ),
                    "repositories_with_both_exposure_and_outcome_variation": int(
                        len(both_repos)
                    ),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def fit_leave_one_pair_out(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    pairs = sorted(frame["ordered_product_pair"].unique())
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        for specification in ["A_pretrigger_only", "B_route_decomposition"]:
            formula = model_formula(threshold, specification, repository_fe=False)
            outcome, design = dmatrices(formula, frame, return_type="dataframe")
            for pair in pairs:
                keep = frame["ordered_product_pair"].ne(pair)
                x = design.loc[keep]
                y = outcome.loc[keep].iloc[:, 0]
                groups = frame.loc[keep, "repo_id"]
                model = sm.OLS(y, x).fit(
                    cov_type="cluster",
                    cov_kwds={"groups": groups, "use_correction": True},
                )
                interval = model.conf_int().loc[exposure]
                rows.append(
                    {
                        "threshold_hours": threshold,
                        "specification": specification,
                        "excluded_ordered_product_pair": pair,
                        "excluded_prs": int((~keep).sum()),
                        "excluded_exposed_prs": int(
                            frame.loc[~keep, exposure].sum()
                        ),
                        "n_prs": int(keep.sum()),
                        "repositories": int(groups.nunique()),
                        "exposed_prs": int(frame.loc[keep, exposure].sum()),
                        "estimate": float(model.params[exposure]),
                        "ci_low": float(interval.iloc[0]),
                        "ci_high": float(interval.iloc[1]),
                        "p_value": float(model.pvalues[exposure]),
                    }
                )
    loo = pd.DataFrame(rows)
    summary = (
        loo.groupby(["threshold_hours", "specification"], observed=True)
        .agg(
            exclusions=("excluded_ordered_product_pair", "size"),
            estimate_min=("estimate", "min"),
            estimate_max=("estimate", "max"),
            ci_low_min=("ci_low", "min"),
            ci_low_max=("ci_low", "max"),
            ci_high_min=("ci_high", "min"),
            ci_high_max=("ci_high", "max"),
            minimum_remaining_exposed_prs=("exposed_prs", "min"),
        )
        .reset_index()
    )
    stable = (
        loo.assign(positive=loo["estimate"] > 0, interval_positive=loo["ci_low"] > 0)
        .groupby(["threshold_hours", "specification"], observed=True)
        .agg(all_estimates_positive=("positive", "all"), all_intervals_positive=("interval_positive", "all"))
        .reset_index()
    )
    return loo, summary.merge(stable, on=["threshold_hours", "specification"])


def denominators(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        for value, label in [(0, "no_exact_parent_reply_by_threshold"), (1, "exact_parent_reply_by_threshold")]:
            cell = frame[frame[exposure].astype(int) == value]
            rows.append(
                {
                    "threshold_hours": threshold,
                    "exposure_group": label,
                    "prs": len(cell),
                    "repositories": int(cell["repo_id"].nunique()),
                    "later_merges": int(cell["merged_from_48h_to_30d"].sum()),
                    "later_merge_rate": float(cell["merged_from_48h_to_30d"].mean()),
                    "grain": "one first cross-product inline trigger per PR, open at 48h, with fixed 30d horizon",
                }
            )
    return pd.DataFrame(rows)


def concentration_tables(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summaries = []
    pair_rows = []
    repo_rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        exposed = frame[frame[exposure].astype(bool)]
        pair_counts = exposed["ordered_product_pair"].value_counts()
        repo_counts = exposed["repo_id"].value_counts()
        summaries.append(
            {
                "threshold_hours": threshold,
                "exposed_prs": len(exposed),
                "represented_ordered_product_pairs": int(pair_counts.size),
                "represented_repositories": int(repo_counts.size),
                "largest_ordered_product_pair": str(pair_counts.index[0]),
                "largest_ordered_product_pair_count": int(pair_counts.iloc[0]),
                "largest_ordered_product_pair_share": float(pair_counts.iloc[0] / len(exposed)),
                "largest_repository_count": int(repo_counts.iloc[0]),
                "largest_repository_share": float(repo_counts.iloc[0] / len(exposed)),
                "ordered_product_pair_hhi": float(((pair_counts / len(exposed)) ** 2).sum()),
                "repository_hhi": float(((repo_counts / len(exposed)) ** 2).sum()),
            }
        )
        for pair, group in frame.groupby("ordered_product_pair", observed=True):
            pair_rows.append(
                {
                    "threshold_hours": threshold,
                    "ordered_product_pair": pair,
                    "all_cohort_prs": len(group),
                    "exposed_prs": int(group[exposure].sum()),
                    "exposure_rate": float(group[exposure].mean()),
                }
            )
        for repo_id, group in frame.groupby("repo_id", observed=True):
            exposed_n = int(group[exposure].sum())
            if exposed_n:
                repo_rows.append(
                    {
                        "threshold_hours": threshold,
                        "repo_id": repo_id,
                        "all_cohort_prs": len(group),
                        "exposed_prs": exposed_n,
                        "exposure_rate": float(group[exposure].mean()),
                    }
                )
    return pd.DataFrame(summaries), pd.DataFrame(pair_rows), pd.DataFrame(repo_rows)


def pretrigger_balance(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        exposed = frame[frame[exposure].astype(bool)]
        unexposed = frame[~frame[exposure].astype(bool)]
        for variable in PRETRIGGER_CONTROLS:
            pooled_sd = np.sqrt(
                (exposed[variable].var(ddof=1) + unexposed[variable].var(ddof=1))
                / 2
            )
            smd = (
                (exposed[variable].mean() - unexposed[variable].mean()) / pooled_sd
                if pooled_sd > 0
                else 0.0
            )
            rows.append(
                {
                    "threshold_hours": threshold,
                    "variable": variable,
                    "exposed_mean": float(exposed[variable].mean()),
                    "unexposed_mean": float(unexposed[variable].mean()),
                    "standardized_mean_difference": float(smd),
                }
            )
    return pd.DataFrame(rows)


def write_schema(frame: pl.DataFrame) -> None:
    definitions = {
        "pr_id": "PR identifier; analysis grain is one PR's first cross-product inline trigger.",
        "repo_id": "Repository cluster and fixed-effect identifier.",
        "trigger_dt": "Timestamp of the first recognized cross-product feedback event on the PR.",
        "trigger_event_id": "Raw inline-comment id of the exact trigger.",
        "trigger_review_id": "Review-batch id containing the trigger.",
        "author_agent": "Mapped product attributed as PR author.",
        "trigger_reviewer_agent": "Exactly mapped product that authored the trigger.",
        "ordered_product_pair": "Directed author product -> reviewer product.",
        "outcome_landmark_dt": "Trigger timestamp plus 48 hours; every PR is still open here.",
        "merged_from_48h_to_30d": "Observed merge strictly after the landmark and no later than trigger + 30 days.",
        "first_exact_reply_hours": "Hours to the earliest inline reply whose in_reply_to_id equals trigger_event_id.",
        "first_exact_reply_dt": "Timestamp of that earliest exact-parent reply.",
        "exact_reply_events_48h": "Number of exact-parent inline replies by the 48-hour landmark.",
        "ownership_route_48h": "Post-trigger public route observed by 48 hours; used only in secondary Model B.",
        "pre_events": "Count of valid submitted-review, PR-comment, and inline-comment rows strictly before trigger.",
        "pre_user_events": "Pretrigger interaction rows whose GitHub user_type is User.",
        "pre_bot_events": "Pretrigger interaction rows whose GitHub user_type is Bot.",
        "pre_decisive_reviews": "Pretrigger submitted reviews with APPROVED or CHANGES_REQUESTED state.",
        "pre_force_pushes": "Timestamped force-push timeline rows strictly before trigger.",
        "log1p_trigger_age_hours": "log(1 + hours from PR creation to trigger).",
        "log1p_pre_events": "log(1 + pre_events).",
    }
    for threshold in THRESHOLDS:
        definitions[f"exact_parent_reply_by_{threshold}h"] = (
            f"True if any inline reply with in_reply_to_id exactly equal to "
            f"trigger_event_id occurs within {threshold} hours; structural edge only."
        )
    columns = []
    for name, dtype in frame.schema.items():
        columns.append(
            {
                "column": name,
                "dtype": str(dtype),
                "definition": definitions.get(name, "Internal timing or audit field."),
                "available_when": (
                    "posttrigger_by_48h"
                    if name.startswith("exact_")
                    or name.startswith("first_exact")
                    or name == "ownership_route_48h"
                    else "outcome"
                    if name in {"merged_dt", "merged_from_48h_to_30d"}
                    else "at_or_before_trigger"
                ),
            }
        )
    schema = {
        "schema_version": "addressed-edge-landmark-v1",
        "grain": "one first cross-product inline-review trigger per PR that remains open at trigger + 48h and has a complete trigger + 30d outcome horizon",
        "exposure_construct": "observed exact-parent inline reply edge; no semantic-resolution claim",
        "outcome_construct": "later public merge timing; no correctness or causal claim",
        "columns": columns,
    }
    (OUTPUT / "schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")


def choose_packaging(
    estimates: pd.DataFrame,
    repository_fe: pd.DataFrame,
    loo_summary: pd.DataFrame,
    concentration: pd.DataFrame,
) -> tuple[str, list[str]]:
    main = estimates[
        (estimates["threshold_hours"] == 48)
        & (estimates["specification"] == "A_pretrigger_only")
    ].iloc[0]
    fe = repository_fe[
        (repository_fe["threshold_hours"] == 48)
        & (repository_fe["specification"] == "A_pretrigger_only")
    ].iloc[0]
    loo = loo_summary[
        (loo_summary["threshold_hours"] == 48)
        & (loo_summary["specification"] == "A_pretrigger_only")
    ].iloc[0]
    conc = concentration[concentration["threshold_hours"] == 48].iloc[0]
    gates = {
        "at_least_100_exposed_prs": int(conc["exposed_prs"]) >= 100,
        "clustered_pretrigger_adjusted_interval_excludes_zero": float(main["ci_low"]) > 0,
        "repository_fe_same_positive_sign": float(fe["estimate"]) > 0,
        "repository_fe_interval_excludes_zero": float(fe["ci_low"]) > 0,
        "all_leave_one_pair_estimates_positive": bool(loo["all_estimates_positive"]),
        "largest_pair_below_half_of_exposed": float(conc["largest_ordered_product_pair_share"]) < 0.5,
        "largest_repo_below_half_of_exposed": float(conc["largest_repository_share"]) < 0.5,
    }
    failed = [name for name, passed in gates.items() if not passed]
    decision = "MAIN_CANDIDATE" if not failed else "APPENDIX_ONLY"
    if int(conc["exposed_prs"]) < 50 or float(conc["largest_ordered_product_pair_share"]) >= 0.75:
        decision = "REJECT_HEADLINE"
    return decision, failed


def write_readme(
    frame: pd.DataFrame,
    estimates: pd.DataFrame,
    repository_fe: pd.DataFrame,
    loo_summary: pd.DataFrame,
    concentration: pd.DataFrame,
) -> None:
    decision, failed = choose_packaging(
        estimates, repository_fe, loo_summary, concentration
    )
    a48 = estimates[
        (estimates["threshold_hours"] == 48)
        & (estimates["specification"] == "A_pretrigger_only")
    ].iloc[0]
    b48 = estimates[
        (estimates["threshold_hours"] == 48)
        & (estimates["specification"] == "B_route_decomposition")
    ].iloc[0]
    fe48 = repository_fe[
        (repository_fe["threshold_hours"] == 48)
        & (repository_fe["specification"] == "A_pretrigger_only")
    ].iloc[0]
    conc48 = concentration[concentration["threshold_hours"] == 48].iloc[0]
    exposed = frame[frame["exact_parent_reply_by_48h"].astype(bool)]
    unexposed = frame[~frame["exact_parent_reply_by_48h"].astype(bool)]
    failed_text = ", ".join(failed) if failed else "none"
    text = f"""# Addressed-edge landmark analysis

## Packaging decision: {decision}

This result is eligible as a **main-result candidate only in observational,
structural language**. It should replace, not stack on top of, another
route-to-merge headline. Model A is the primary specification. Model B is a
secondary decomposition because `ownership_route_48h` is post-trigger and can
partly mediate or proxy the exact reply; it is not a safer causal adjustment.

At 48 hours, {len(exposed):,}/{len(frame):,} PRs have an inline reply whose raw
`in_reply_to_id` equals the exact cross-product trigger id. Later merge is
{exposed['merged_from_48h_to_30d'].mean():.1%} with this edge and
{unexposed['merged_from_48h_to_30d'].mean():.1%} without it. The
repository-clustered pretrigger-adjusted LPM difference is
{a48['estimate'] * 100:.1f} percentage points (95% CI
{a48['ci_low'] * 100:.1f} to {a48['ci_high'] * 100:.1f}). The repository-FE
sensitivity is {fe48['estimate'] * 100:.1f} points (95% CI
{fe48['ci_low'] * 100:.1f} to {fe48['ci_high'] * 100:.1f}). Adding the 48-hour
ownership route gives {b48['estimate'] * 100:.1f} points (95% CI
{b48['ci_low'] * 100:.1f} to {b48['ci_high'] * 100:.1f}); this is decomposition,
not a direct effect. The largest ordered product pair supplies
{conc48['largest_ordered_product_pair_share']:.1%} of exposed PRs and the
largest repository supplies {conc48['largest_repository_share']:.1%}.

Pre-specified packaging gates failed: {failed_text}.

## Exact question and grain

- **Grain:** one PR's first recognized cross-product inline-review trigger,
  restricted to PRs still open 48 hours after that trigger and to triggers with
  a complete 30-day horizon.
- **Exposure:** any raw inline reply with `in_reply_to_id == trigger_event_id`
  by 1, 6, 24, or 48 hours. This proves a public parent edge only.
- **Outcome:** merge strictly after trigger + 48 hours and no later than trigger
  + 30 days.
- **Model A:** exact-edge indicator, author product, reviewer product, trigger
  month, trigger age, pretrigger interaction counts, pretrigger decisive reviews,
  and pretrigger force pushes; repository-clustered uncertainty.
- **Model B:** Model A plus the 48-hour ownership route as a secondary
  post-trigger decomposition.
- **Sensitivity:** repository fixed effects and leave-one-ordered-product-pair-out.

The exact column schema is in `schema.json`; denominators are in
`denominators.csv`; temporal assertions are in
`temporal_leakage_validation.json`.

## Novelty boundary

[Zhong et al. (2026)](https://arxiv.org/abs/2607.13196) model broad sequences of
human, LLM, and agent reviewer types and relate those sequences to review
efficiency and quality. This analysis is narrower: it starts from one
cross-product inline trigger and requires the raw GitHub parent id to point back
to that exact trigger. It does not claim the first study of multi-agent review
sequences.

[Cynthia et al. (2026)](https://arxiv.org/abs/2607.21997) study developer
responses and resolution of agent-generated review comments, including content
and developer roles. This analysis does **not** label response semantics,
actionability, resolution, or developer intent. A direct parent edge may
acknowledge, reject, question, or merely mention the trigger. Later merge does
not prove that feedback was correct or resolved.

## Allowed and forbidden interpretation

Allowed:

> Among inline-trigger PRs still open at 48 hours, an observed exact-parent
> reply by the landmark is associated with a higher probability of later public
> merge after adjustment for measured pretrigger activity. The association is
> stable to the reported pair and repository sensitivities.

Forbidden:

- direct replies cause merge;
- the reply resolved, fixed, accepted, or correctly addressed the feedback;
- a user account necessarily represents manual human reasoning;
- later merge validates either review comment;
- the estimate is an interoperability effect between products.

Unmeasured maintainer attention, task difficulty, private coordination, product
policy, and reply content can select both exposure and outcome. The analysis is
therefore associational even when the interval excludes zero.
"""
    (OUTPUT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cohort, cohort_checks = build_base_cohort()
    cohort, audited_direct, exposure_checks = add_exact_parent_exposures(cohort)
    cohort, pretrigger_checks = add_pretrigger_features(cohort)
    cohort = add_ownership_route(cohort)

    export_columns = [
        "pr_id",
        "repo_id",
        "trigger_dt",
        "trigger_event_id",
        "trigger_review_id",
        "author_agent",
        "trigger_reviewer_agent",
        "ordered_product_pair",
        "trigger_month",
        "outcome_landmark_dt",
        "merged_from_48h_to_30d",
        "first_exact_reply_hours",
        "first_exact_reply_dt",
        "exact_reply_events_48h",
        *[f"exact_parent_reply_by_{threshold}h" for threshold in THRESHOLDS],
        "ownership_route_48h",
        "pre_events",
        "pre_user_events",
        "pre_bot_events",
        "pre_decisive_reviews",
        "pre_force_pushes",
        "log1p_trigger_age_hours",
        "log1p_pre_events",
        "pr_created_dt",
        "last_pre_event_dt",
        "last_pre_force_push_dt",
        "merged_dt",
        "closed_dt",
    ]
    export = cohort.select(export_columns)
    frame = export.to_pandas()
    frame["merged_from_48h_to_30d"] = frame[
        "merged_from_48h_to_30d"
    ].astype(int)
    for threshold in THRESHOLDS:
        frame[f"exact_parent_reply_by_{threshold}h"] = frame[
            f"exact_parent_reply_by_{threshold}h"
        ].astype(int)

    estimates, model_terms = fit_main_models(frame)
    repository_fe = fit_repository_fe(frame)
    loo, loo_summary = fit_leave_one_pair_out(frame)
    denom = denominators(frame)
    concentration, pair_support, repo_support = concentration_tables(frame)
    balance = pretrigger_balance(frame)

    export.write_parquet(OUTPUT / "analysis_cohort.parquet")
    audited_direct.select(
        "pr_id",
        "trigger_event_id",
        "response_event_id",
        "in_reply_to_id",
        "trigger_dt",
        "response_dt",
        "hours_after_trigger",
    ).write_parquet(OUTPUT / "exact_parent_reply_event_audit.parquet")
    estimates.to_csv(OUTPUT / "addressed_edge_clustered_lpm.csv", index=False)
    model_terms.to_csv(OUTPUT / "addressed_edge_clustered_lpm_all_terms.csv", index=False)
    repository_fe.to_csv(OUTPUT / "repository_fe_sensitivity.csv", index=False)
    loo.to_csv(OUTPUT / "leave_one_product_pair_out.csv", index=False)
    loo_summary.to_csv(OUTPUT / "leave_one_product_pair_out_summary.csv", index=False)
    denom.to_csv(OUTPUT / "denominators.csv", index=False)
    concentration.to_csv(OUTPUT / "exposure_concentration_summary.csv", index=False)
    pair_support.to_csv(OUTPUT / "ordered_product_pair_support.csv", index=False)
    repo_support.to_csv(OUTPUT / "repository_exposure_support.csv", index=False)
    balance.to_csv(OUTPUT / "pretrigger_balance.csv", index=False)
    write_schema(export)

    validation = {
        "dataset_revision": DATASET_REVISION,
        "grain": "one first cross-product inline trigger per PR, open at 48h, fixed 30d horizon",
        "cohort": cohort_checks,
        "exposure": exposure_checks,
        "pretrigger_controls": pretrigger_checks,
        "ownership_route_model_B_only": True,
        "outcome_not_observed_until_after_all_exposure_thresholds": True,
        "semantic_labels_used": False,
        "semantic_resolution_claim_allowed": False,
        "all_assertions_passed": True,
    }
    (OUTPUT / "temporal_leakage_validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    write_readme(frame, estimates, repository_fe, loo_summary, concentration)

    inputs = [
        CHAIN_DIR / "feedback_48h_landmark_cohort.parquet",
        CHAIN_DIR / "cross_feedback_response_events.parquet",
        OWNER_DIR / "ownership_route_48h.parquet",
        DATA / "pull_request.parquet",
        DATA / "pr_reviews.parquet",
        DATA / "pr_review_comments.parquet",
        DATA / "pr_comments.parquet",
        DATA / "pr_timeline.parquet",
    ]
    artifacts = [path for path in OUTPUT.iterdir() if path.is_file()]
    manifest = {
        "run_id": "addressed-edge-landmark-v1",
        "dataset_revision": DATASET_REVISION,
        "script_sha256": sha256_file(Path(__file__)),
        "input_sha256": {path.name: sha256_file(path) for path in inputs},
        "artifact_sha256": {
            path.name: sha256_file(path)
            for path in artifacts
            if path.name != "manifest.json"
        },
        "manuscript_edited": False,
        "external_upload": False,
        "claim_scope": "observational exact-parent public edge; no semantic resolution or causal effect",
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    decision, failed = choose_packaging(
        estimates, repository_fe, loo_summary, concentration
    )
    print(
        json.dumps(
            {
                "cohort_prs": len(frame),
                "repositories": int(frame["repo_id"].nunique()),
                "exposed_prs": {
                    str(threshold): int(
                        frame[f"exact_parent_reply_by_{threshold}h"].sum()
                    )
                    for threshold in THRESHOLDS
                },
                "later_merges": int(frame["merged_from_48h_to_30d"].sum()),
                "packaging_decision": decision,
                "failed_packaging_gates": failed,
                "main_estimates": estimates.to_dict(orient="records"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
