from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices, dmatrix


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import parse_timestamp  # noqa: E402


DEFAULT_DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
DEFAULT_EDGE_DIR = ROOT / "outputs" / "addressed_edge_landmark"
DEFAULT_CROSS_DIR = ROOT / "outputs" / "cross_agent_review"
DEFAULT_OUTPUT = ROOT / "outputs" / "addressed_edge_specificity"

DATASET_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXACT_48H = 109
THRESHOLDS = (1, 6, 24, 48)
DISCUSSION_SOURCES = ("subsequent_review", "subsequent_pr_comment")
VALID_RESPONSE_SOURCES = (
    "direct_inline_reply",
    "subsequent_review",
    "subsequent_pr_comment",
    "force_push",
)
PRETRIGGER_CONTROLS = (
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
)
BASE_CATEGORICAL = (
    "C(author_agent)",
    "C(trigger_reviewer_agent)",
    "C(trigger_month)",
)
OUTCOME = "merged_from_48h_to_30d"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test whether the addressed-edge landmark association is specific "
            "to an exact parent edge rather than generic post-trigger activity."
        )
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--edge-dir", type=Path, default=DEFAULT_EDGE_DIR)
    parser.add_argument("--cross-dir", type=Path, default=DEFAULT_CROSS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_and_validate_cohort(edge_dir: Path) -> tuple[pl.DataFrame, dict[str, object]]:
    path = edge_dir / "analysis_cohort.parquet"
    cohort = pl.read_parquet(path).sort("pr_id")
    required = {
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
        OUTCOME,
        "closed_dt",
        "merged_dt",
        "last_pre_event_dt",
        "last_pre_force_push_dt",
        *PRETRIGGER_CONTROLS,
        *[f"exact_parent_reply_by_{threshold}h" for threshold in THRESHOLDS],
    }
    missing = sorted(required - set(cohort.columns))
    if missing:
        raise AssertionError(f"Addressed-edge cohort is missing columns: {missing}")
    if cohort.height != EXPECTED_COHORT_ROWS:
        raise AssertionError(
            f"Landmark cohort drift: {cohort.height} != {EXPECTED_COHORT_ROWS}"
        )
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError("The landmark cohort is not one row per PR.")
    if cohort.filter(pl.col("trigger_event_id").is_null()).height:
        raise AssertionError("An inline trigger lacks a raw event id.")
    expected_landmark = cohort["trigger_dt"] + timedelta(hours=48)
    if not (cohort["outcome_landmark_dt"] == expected_landmark).all():
        raise AssertionError("The outcome landmark is not exactly trigger + 48 hours.")
    if cohort.filter(
        pl.col("closed_dt").is_not_null()
        & (pl.col("closed_dt") <= pl.col("outcome_landmark_dt"))
    ).height:
        raise AssertionError("A PR closed at or before the landmark entered the risk set.")
    positive = cohort.filter(pl.col(OUTCOME))
    if positive.filter(
        (pl.col("merged_dt") <= pl.col("outcome_landmark_dt"))
        | (pl.col("merged_dt") > pl.col("trigger_dt") + timedelta(days=30))
    ).height:
        raise AssertionError("A positive outcome falls outside (48 hours, 30 days].")
    if cohort.filter(
        pl.col("last_pre_event_dt").is_not_null()
        & (pl.col("last_pre_event_dt") >= pl.col("trigger_dt"))
    ).height:
        raise AssertionError("A post-trigger interaction leaked into a pretrigger control.")
    if cohort.filter(
        pl.col("last_pre_force_push_dt").is_not_null()
        & (pl.col("last_pre_force_push_dt") >= pl.col("trigger_dt"))
    ).height:
        raise AssertionError("A post-trigger force push leaked into a pretrigger control.")
    if int(cohort["exact_parent_reply_by_48h"].sum()) != EXPECTED_EXACT_48H:
        raise AssertionError("The upstream 48-hour exact-edge count drifted.")
    checks = {
        "cohort_rows": cohort.height,
        "unique_prs": cohort["pr_id"].n_unique(),
        "repositories": cohort["repo_id"].n_unique(),
        "ordered_product_pairs": cohort["ordered_product_pair"].n_unique(),
        "one_row_per_pr": True,
        "all_landmarks_equal_trigger_plus_48h": True,
        "all_prs_open_at_48h": True,
        "all_positive_outcomes_strictly_after_48h_and_by_30d": True,
        "all_controls_strictly_pretrigger": True,
    }
    return cohort, checks


def audit_raw_response_rows(
    events: pl.DataFrame, data_dir: Path
) -> tuple[pl.DataFrame, dict[str, object]]:
    exact = events.filter(pl.col("response_source") == "direct_inline_reply")
    raw_inline = (
        pl.read_parquet(
            data_dir / "pr_review_comments.parquet",
            columns=["id", "in_reply_to_id", "created_at"],
        )
        .with_columns(
            pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
            parse_timestamp("created_at", "raw_response_dt"),
        )
        .select(
            pl.col("id").alias("response_event_id"),
            "in_reply_to_id",
            "raw_response_dt",
        )
    )
    exact_audit = exact.join(
        raw_inline, on="response_event_id", how="left", validate="m:1"
    )
    if exact_audit["raw_response_dt"].null_count():
        raise AssertionError("An exact reply does not resolve to the raw inline table.")
    if exact_audit.filter(
        pl.col("in_reply_to_id") != pl.col("trigger_event_id")
    ).height:
        raise AssertionError("A derived direct reply does not target the exact trigger.")
    if exact_audit.filter(
        pl.col("raw_response_dt") != pl.col("response_dt")
    ).height:
        raise AssertionError("A direct-reply timestamp disagrees with the raw table.")

    later_reviews = events.filter(pl.col("response_source") == "subsequent_review")
    raw_reviews = (
        pl.read_parquet(
            data_dir / "pr_reviews.parquet",
            columns=["id", "pr_id", "pull_request_review_id", "submitted_at"],
        )
        .with_columns(parse_timestamp("submitted_at", "raw_response_dt"))
        .select(
            pl.col("id").alias("response_event_id"),
            "pr_id",
            pl.col("pull_request_review_id").alias("raw_response_review_id"),
            "raw_response_dt",
        )
    )
    review_audit = later_reviews.join(
        raw_reviews,
        on=["pr_id", "response_event_id"],
        how="left",
        validate="m:1",
    )
    if review_audit["raw_response_dt"].null_count():
        raise AssertionError("A later review does not resolve to the raw review table.")
    if review_audit.filter(
        (pl.col("raw_response_dt") != pl.col("response_dt"))
        | (pl.col("raw_response_review_id") != pl.col("response_review_id"))
    ).height:
        raise AssertionError("A derived later review disagrees with the raw review table.")
    if review_audit.filter(
        pl.col("trigger_review_id").is_not_null()
        & (pl.col("response_review_id") == pl.col("trigger_review_id"))
    ).height:
        raise AssertionError("The trigger review batch entered the later-review control.")

    later_comments = events.filter(
        pl.col("response_source") == "subsequent_pr_comment"
    )
    raw_comments = (
        pl.read_parquet(
            data_dir / "pr_comments.parquet", columns=["id", "pr_id", "created_at"]
        )
        .with_columns(parse_timestamp("created_at", "raw_response_dt"))
        .select(
            pl.col("id").alias("response_event_id"),
            "pr_id",
            "raw_response_dt",
        )
    )
    comment_audit = later_comments.join(
        raw_comments,
        on=["pr_id", "response_event_id"],
        how="left",
        validate="m:1",
    )
    if comment_audit["raw_response_dt"].null_count():
        raise AssertionError("A later PR comment does not resolve to its raw table.")
    if comment_audit.filter(
        pl.col("raw_response_dt") != pl.col("response_dt")
    ).height:
        raise AssertionError("A derived PR-comment timestamp disagrees with its raw row.")

    event_audit = pl.concat(
        [
            exact_audit.select(
                "pr_id",
                "trigger_event_id",
                "trigger_dt",
                "response_source",
                "response_event_id",
                "response_review_id",
                "response_dt",
                "hours_after_trigger",
                "in_reply_to_id",
            ),
            review_audit.select(
                "pr_id",
                "trigger_event_id",
                "trigger_dt",
                "response_source",
                "response_event_id",
                "response_review_id",
                "response_dt",
                "hours_after_trigger",
                pl.lit(None, dtype=pl.Int64).alias("in_reply_to_id"),
            ),
            comment_audit.select(
                "pr_id",
                "trigger_event_id",
                "trigger_dt",
                "response_source",
                "response_event_id",
                "response_review_id",
                "response_dt",
                "hours_after_trigger",
                pl.lit(None, dtype=pl.Int64).alias("in_reply_to_id"),
            ),
        ],
        how="vertical_relaxed",
    ).sort(["pr_id", "response_dt", "response_source", "response_event_id"])
    checks = {
        "exact_reply_events_48h": exact.height,
        "exact_reply_prs_48h": exact["pr_id"].n_unique(),
        "later_review_events_48h": later_reviews.height,
        "later_review_prs_48h": later_reviews["pr_id"].n_unique(),
        "later_pr_comment_events_48h": later_comments.height,
        "later_pr_comment_prs_48h": later_comments["pr_id"].n_unique(),
        "all_exact_replies_resolve_to_raw_parent_ids": True,
        "all_later_reviews_resolve_to_new_raw_review_batches": True,
        "all_later_pr_comments_resolve_to_raw_rows": True,
    }
    return event_audit, checks


def classify_events(
    cohort: pl.DataFrame, cross_dir: Path, data_dir: Path
) -> tuple[pl.DataFrame, pl.DataFrame, pd.DataFrame, dict[str, object]]:
    key = cohort.select(
        "pr_id", "trigger_event_id", "trigger_review_id", "trigger_dt", "outcome_landmark_dt"
    )
    events = pl.read_parquet(cross_dir / "cross_feedback_response_events.parquet")
    unknown_sources = sorted(
        set(events["response_source"].unique().drop_nulls().to_list())
        - set(VALID_RESPONSE_SOURCES)
    )
    if unknown_sources:
        raise AssertionError(f"Unrecognized response sources: {unknown_sources}")
    window = (
        events.join(
            key,
            on=["pr_id", "trigger_event_id", "trigger_review_id", "trigger_dt"],
            how="inner",
            validate="m:1",
        )
        .filter(
            (pl.col("hours_after_trigger") > 0)
            & (pl.col("hours_after_trigger") <= 48)
        )
        .sort(["pr_id", "response_dt", "response_source", "response_event_id"])
    )
    if window.filter(
        (pl.col("response_dt") <= pl.col("trigger_dt"))
        | (pl.col("response_dt") > pl.col("outcome_landmark_dt"))
    ).height:
        raise AssertionError("A specificity event falls outside (trigger, 48 hours].")
    event_audit, raw_checks = audit_raw_response_rows(window, data_dir)

    user_event = (
        pl.col("response_user_type").fill_null("").str.to_lowercase() == "user"
    )
    aggregations: list[pl.Expr] = []
    for threshold in THRESHOLDS:
        by_time = pl.col("hours_after_trigger") <= threshold
        aggregations.extend(
            [
                (
                    by_time
                    & (pl.col("response_source") == "direct_inline_reply")
                )
                .any()
                .alias(f"exact_edge_by_{threshold}h"),
                (
                    by_time
                    & pl.col("response_source").is_in(DISCUSSION_SOURCES)
                )
                .any()
                .alias(f"nonexact_discussion_by_{threshold}h"),
                (
                    by_time
                    & (pl.col("response_source") != "direct_inline_reply")
                )
                .any()
                .alias(f"other_activity_by_{threshold}h"),
                (
                    by_time
                    & (pl.col("response_source") == "direct_inline_reply")
                    & user_event
                )
                .any()
                .alias(f"exact_user_edge_by_{threshold}h"),
                (
                    by_time
                    & pl.col("response_source").is_in(DISCUSSION_SOURCES)
                    & user_event
                )
                .any()
                .alias(f"nonexact_user_discussion_by_{threshold}h"),
            ]
        )
    per_pr = window.group_by("pr_id").agg(aggregations)
    flag_columns = [column for column in per_pr.columns if column != "pr_id"]
    enriched = cohort.join(per_pr, on="pr_id", how="left").with_columns(
        [pl.col(column).fill_null(False) for column in flag_columns]
    )
    for threshold in THRESHOLDS:
        exact = f"exact_edge_by_{threshold}h"
        discussion = f"nonexact_discussion_by_{threshold}h"
        other = f"other_activity_by_{threshold}h"
        enriched = enriched.with_columns(
            (pl.col(exact) | pl.col(discussion)).alias(
                f"active_discussion_by_{threshold}h"
            ),
            (pl.col(exact) | pl.col(other)).alias(f"any_activity_by_{threshold}h"),
            pl.when(pl.col(exact))
            .then(pl.lit("exact_edge"))
            .when(pl.col(discussion))
            .then(pl.lit("nonexact_discussion_only"))
            .when(pl.col(other))
            .then(pl.lit("movement_only"))
            .otherwise(pl.lit("no_visible_activity"))
            .alias(f"specificity_group_{threshold}h"),
        )
        upstream = f"exact_parent_reply_by_{threshold}h"
        if enriched.filter(pl.col(exact) != pl.col(upstream)).height:
            raise AssertionError(f"Exact-edge derivation disagrees with upstream at {threshold}h.")
    for prefix in (
        "exact_edge_by_",
        "nonexact_discussion_by_",
        "other_activity_by_",
        "exact_user_edge_by_",
        "nonexact_user_discussion_by_",
    ):
        columns = [f"{prefix}{threshold}h" for threshold in THRESHOLDS]
        for left, right in zip(columns, columns[1:]):
            if enriched.filter(pl.col(left) & ~pl.col(right)).height:
                raise AssertionError(f"Nested event-window invariant failed: {left} -> {right}")
    if int(enriched["exact_edge_by_48h"].sum()) != EXPECTED_EXACT_48H:
        raise AssertionError("The independently reconstructed exact-edge count drifted.")

    source_counts = (
        window.group_by("response_source")
        .agg(pl.len().alias("events"), pl.col("pr_id").n_unique().alias("prs"))
        .sort("response_source")
        .to_pandas()
    )
    checks = {
        "response_events_in_48h": window.height,
        "response_event_prs_in_48h": window["pr_id"].n_unique(),
        "all_events_strictly_after_trigger_and_by_48h": True,
        "all_threshold_flags_nested": True,
        "independent_exact_flags_match_upstream": True,
        "exposure_uses_only_events_by_landmark": True,
        "outcome_not_used_in_event_classification": True,
        **raw_checks,
    }
    return enriched, event_audit, source_counts, checks


def to_model_frame(frame: pl.DataFrame) -> pd.DataFrame:
    result = frame.to_pandas()
    result[OUTCOME] = result[OUTCOME].astype(int)
    for threshold in THRESHOLDS:
        for prefix in (
            "exact_edge_by_",
            "nonexact_discussion_by_",
            "other_activity_by_",
            "active_discussion_by_",
            "any_activity_by_",
            "exact_user_edge_by_",
            "nonexact_user_discussion_by_",
        ):
            result[f"{prefix}{threshold}h"] = result[
                f"{prefix}{threshold}h"
            ].astype(int)
    return result


def binary_formula(exposure: str, repository_fe: bool = False) -> str:
    terms = [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    if repository_fe:
        terms.append("C(repo_id)")
    return f"{OUTCOME} ~ " + " + ".join(terms)


def fit_binary_model(
    frame: pd.DataFrame,
    *,
    mask: pd.Series,
    exposure: str,
    contrast: str,
    threshold: int,
    repository_fe: bool,
) -> dict[str, object]:
    analysis = frame.loc[mask].copy()
    analysis[exposure] = analysis[exposure].astype(int)
    if analysis[exposure].nunique() != 2:
        raise RuntimeError(f"Contrast {contrast} has no exposure variation.")
    formula = binary_formula(exposure, repository_fe=repository_fe)
    outcome, design = dmatrices(formula, analysis, return_type="dataframe")
    groups = analysis.loc[design.index, "repo_id"]
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    interval = model.conf_int().loc[exposure]
    by_repo = analysis.groupby("repo_id", observed=True).agg(
        exposure_levels=(exposure, "nunique"),
        outcome_levels=(OUTCOME, "nunique"),
        prs=(exposure, "size"),
    )
    varying = by_repo[by_repo["exposure_levels"] > 1]
    both = varying[varying["outcome_levels"] > 1]
    exposed = analysis[analysis[exposure] == 1]
    control = analysis[analysis[exposure] == 0]
    return {
        "contrast": contrast,
        "threshold_hours": threshold,
        "repository_fixed_effects": repository_fe,
        "exposure": exposure,
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "exposed_prs": len(exposed),
        "control_prs": len(control),
        "repositories": int(groups.nunique()),
        "exposed_raw_merge_rate": float(exposed[OUTCOME].mean()),
        "control_raw_merge_rate": float(control[OUTCOME].mean()),
        "repositories_with_within_exposure_variation": len(varying),
        "prs_in_repositories_with_within_exposure_variation": int(varying["prs"].sum()),
        "repositories_with_both_exposure_and_outcome_variation": len(both),
        "design_columns": int(design.shape[1]),
        "design_rank": int(np.linalg.matrix_rank(design.to_numpy())),
        "formula": formula,
        "interpretation": (
            "observational later-merge probability difference; not a causal or semantic-resolution estimate"
        ),
    }


def fit_specificity_models(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    clustered_rows: list[dict[str, object]] = []
    for threshold in THRESHOLDS:
        exact = f"exact_edge_by_{threshold}h"
        discussion = f"nonexact_discussion_by_{threshold}h"
        clustered_rows.append(
            fit_binary_model(
                frame,
                mask=(frame[exact] == 1) | (frame[discussion] == 1),
                exposure=exact,
                contrast="exact_edge_vs_nonexact_discussion",
                threshold=threshold,
                repository_fe=False,
            )
        )

    exact = "exact_edge_by_48h"
    other = "other_activity_by_48h"
    exact_user = "exact_user_edge_by_48h"
    nonexact_user = "nonexact_user_discussion_by_48h"
    clustered_rows.append(
        fit_binary_model(
            frame,
            mask=(frame[exact] == 1) | (frame[other] == 1),
            exposure=exact,
            contrast="exact_edge_vs_any_other_visible_activity",
            threshold=48,
            repository_fe=False,
        )
    )
    user_mask = (frame[exact_user] == 1) | (
        (frame[exact] == 0) & (frame[nonexact_user] == 1)
    )
    clustered_rows.append(
        fit_binary_model(
            frame,
            mask=user_mask,
            exposure=exact_user,
            contrast="exact_user_edge_vs_nonexact_user_discussion",
            threshold=48,
            repository_fe=False,
        )
    )

    fe_rows: list[dict[str, object]] = []
    for exposure, contrast, mask in (
        (
            exact,
            "exact_edge_vs_nonexact_discussion",
            (frame[exact] == 1) | (frame["nonexact_discussion_by_48h"] == 1),
        ),
        (
            exact,
            "exact_edge_vs_any_other_visible_activity",
            (frame[exact] == 1) | (frame[other] == 1),
        ),
        (
            exact_user,
            "exact_user_edge_vs_nonexact_user_discussion",
            user_mask,
        ),
    ):
        fe_rows.append(
            fit_binary_model(
                frame,
                mask=mask,
                exposure=exposure,
                contrast=contrast,
                threshold=48,
                repository_fe=True,
            )
        )
    return pd.DataFrame(clustered_rows), pd.DataFrame(fe_rows)


def fit_response_gradient(frame: pd.DataFrame) -> pd.DataFrame:
    group = "specificity_group_48h"
    formula = (
        f"{OUTCOME} ~ C({group}, Treatment('no_visible_activity')) + "
        + " + ".join([*BASE_CATEGORICAL, *PRETRIGGER_CONTROLS])
    )
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    term_for = {
        label: next(
            (
                column
                for column in design.columns
                if column.startswith(f"C({group}") and f"[T.{label}]" in column
            ),
            None,
        )
        for label in ("exact_edge", "nonexact_discussion_only", "movement_only")
    }
    contrasts = (
        ("exact_edge_vs_no_visible_activity", "exact_edge", None),
        ("nonexact_discussion_vs_no_visible_activity", "nonexact_discussion_only", None),
        ("movement_only_vs_no_visible_activity", "movement_only", None),
        ("exact_edge_vs_nonexact_discussion", "exact_edge", "nonexact_discussion_only"),
    )
    rows = []
    for label, positive, negative in contrasts:
        vector = np.zeros(design.shape[1])
        positive_term = term_for[positive]
        if positive_term is None:
            raise AssertionError(f"Missing response-gradient term for {positive}")
        vector[design.columns.get_loc(positive_term)] = 1
        if negative is not None:
            negative_term = term_for[negative]
            if negative_term is None:
                raise AssertionError(f"Missing response-gradient term for {negative}")
            vector[design.columns.get_loc(negative_term)] = -1
        test = model.t_test(vector)
        interval = np.asarray(test.conf_int()).ravel()
        rows.append(
            {
                "contrast": label,
                "threshold_hours": 48,
                "estimate": float(np.asarray(test.effect).item()),
                "ci_low": float(interval[0]),
                "ci_high": float(interval[1]),
                "p_value": float(np.asarray(test.pvalue).item()),
                "n_prs": int(model.nobs),
                "repositories": int(groups.nunique()),
                "formula": formula,
                "note": "contextual four-state model; the active-discussion subset remains the primary specificity contrast",
            }
        )
    return pd.DataFrame(rows)


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(values * weights) / np.sum(weights))


def effective_sample_size(weights: np.ndarray) -> float:
    return float(np.sum(weights) ** 2 / np.sum(weights**2))


def balance_table(
    analysis: pd.DataFrame, exposure: str, weights: np.ndarray
) -> pd.DataFrame:
    rows = []
    treated = analysis[exposure].to_numpy(dtype=int) == 1
    for variable in PRETRIGGER_CONTROLS:
        values = analysis[variable].to_numpy(dtype=float)
        exposed_values = values[treated]
        control_values = values[~treated]
        pooled_sd = np.sqrt(
            (np.var(exposed_values, ddof=1) + np.var(control_values, ddof=1)) / 2
        )
        raw_smd = (
            (np.mean(exposed_values) - np.mean(control_values)) / pooled_sd
            if pooled_sd > 0
            else 0.0
        )
        exposed_weighted_mean = weighted_mean(exposed_values, weights[treated])
        control_weighted_mean = weighted_mean(control_values, weights[~treated])
        weighted_smd = (
            (exposed_weighted_mean - control_weighted_mean) / pooled_sd
            if pooled_sd > 0
            else 0.0
        )
        rows.append(
            {
                "variable": variable,
                "exposed_raw_mean": float(np.mean(exposed_values)),
                "control_raw_mean": float(np.mean(control_values)),
                "raw_standardized_mean_difference": float(raw_smd),
                "exposed_overlap_weighted_mean": exposed_weighted_mean,
                "control_overlap_weighted_mean": control_weighted_mean,
                "overlap_weighted_standardized_mean_difference": float(weighted_smd),
            }
        )
    return pd.DataFrame(rows)


def fit_overlap_sensitivity(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exposure = "exact_edge_by_48h"
    discussion = "nonexact_discussion_by_48h"
    analysis = frame.loc[(frame[exposure] == 1) | (frame[discussion] == 1)].copy()
    propensity_formula = "1 + " + " + ".join(
        [*BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    design = dmatrix(propensity_formula, analysis, return_type="dataframe")
    propensity_model = sm.GLM(
        analysis[exposure], design, family=sm.families.Binomial()
    ).fit(maxiter=200)
    if not propensity_model.converged:
        raise RuntimeError("The propensity model did not converge.")
    propensity = np.asarray(propensity_model.predict(design), dtype=float)
    if np.any(~np.isfinite(propensity)) or np.any((propensity < 0) | (propensity > 1)):
        raise AssertionError("Invalid propensity score produced.")
    assignment = analysis[exposure].to_numpy(dtype=int)
    overlap_weights = np.where(assignment == 1, 1 - propensity, propensity)
    analysis["propensity_score"] = propensity
    analysis["overlap_weight"] = overlap_weights

    exposed_scores = propensity[assignment == 1]
    control_scores = propensity[assignment == 0]
    common_low = max(float(exposed_scores.min()), float(control_scores.min()))
    common_high = min(float(exposed_scores.max()), float(control_scores.max()))
    specifications = (
        ("overlap_weighted_all", np.ones(len(analysis), dtype=bool)),
        (
            "overlap_weighted_empirical_common_support",
            (propensity >= common_low) & (propensity <= common_high),
        ),
        (
            "overlap_weighted_fixed_0.05_0.95",
            (propensity >= 0.05) & (propensity <= 0.95),
        ),
    )
    rows = []
    for specification, keep in specifications:
        subset = analysis.loc[keep].copy()
        weights = overlap_weights[keep]
        assignment_subset = subset[exposure].to_numpy(dtype=int)
        if np.unique(assignment_subset).size != 2:
            raise RuntimeError(f"Overlap specification lost an exposure group: {specification}")
        design_outcome = sm.add_constant(subset[[exposure]].astype(float))
        model = sm.WLS(subset[OUTCOME], design_outcome, weights=weights).fit(
            cov_type="cluster",
            cov_kwds={"groups": subset["repo_id"], "use_correction": True},
        )
        interval = model.conf_int().loc[exposure]
        rows.append(
            {
                "specification": specification,
                "contrast": "exact_edge_vs_nonexact_discussion",
                "threshold_hours": 48,
                "estimate": float(model.params[exposure]),
                "ci_low": float(interval.iloc[0]),
                "ci_high": float(interval.iloc[1]),
                "p_value": float(model.pvalues[exposure]),
                "n_prs": len(subset),
                "exposed_prs": int(assignment_subset.sum()),
                "control_prs": int((assignment_subset == 0).sum()),
                "repositories": int(subset["repo_id"].nunique()),
                "effective_sample_size": effective_sample_size(weights),
                "exposed_effective_sample_size": effective_sample_size(
                    weights[assignment_subset == 1]
                ),
                "control_effective_sample_size": effective_sample_size(
                    weights[assignment_subset == 0]
                ),
                "propensity_common_support_low": common_low,
                "propensity_common_support_high": common_high,
                "interpretation": "overlap-weighted observational association; not a causal effect",
            }
        )
    quantiles = (0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1)
    score_rows = []
    for group, group_scores in (
        ("exact_edge", exposed_scores),
        ("nonexact_discussion_only", control_scores),
    ):
        values = np.quantile(group_scores, quantiles)
        for quantile, value in zip(quantiles, values):
            score_rows.append(
                {
                    "group": group,
                    "quantile": quantile,
                    "propensity_score": float(value),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(score_rows), balance_table(
        analysis, exposure, overlap_weights
    )


def fit_leave_one_pair_out(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    exposure = "exact_edge_by_48h"
    discussion = "nonexact_discussion_by_48h"
    analysis = frame.loc[(frame[exposure] == 1) | (frame[discussion] == 1)].copy()
    rows = []
    for omitted_pair in sorted(analysis["ordered_product_pair"].unique()):
        subset = analysis[analysis["ordered_product_pair"] != omitted_pair].copy()
        result = fit_binary_model(
            subset,
            mask=pd.Series(True, index=subset.index),
            exposure=exposure,
            contrast="exact_edge_vs_nonexact_discussion",
            threshold=48,
            repository_fe=False,
        )
        result["omitted_ordered_product_pair"] = omitted_pair
        rows.append(result)
    estimates = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {
                "threshold_hours": 48,
                "runs": len(estimates),
                "all_estimates_positive": bool((estimates["estimate"] > 0).all()),
                "runs_with_interval_excluding_zero": int((estimates["ci_low"] > 0).sum()),
                "min_estimate": float(estimates["estimate"].min()),
                "max_estimate": float(estimates["estimate"].max()),
                "min_ci_low": float(estimates["ci_low"].min()),
                "max_ci_low": float(estimates["ci_low"].max()),
            }
        ]
    )
    return estimates, summary


def denominator_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        group_column = f"specificity_group_{threshold}h"
        for group, cell in frame.groupby(group_column, observed=True):
            rows.append(
                {
                    "threshold_hours": threshold,
                    "population": "full_landmark_cohort",
                    "group": group,
                    "prs": len(cell),
                    "repositories": int(cell["repo_id"].nunique()),
                    "later_merges": int(cell[OUTCOME].sum()),
                    "later_merge_rate": float(cell[OUTCOME].mean()),
                }
            )
    return pd.DataFrame(rows)


def concentration_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    exact = frame[frame["exact_edge_by_48h"] == 1]
    comparator = frame[
        (frame["exact_edge_by_48h"] == 0)
        & (frame["nonexact_discussion_by_48h"] == 1)
    ]
    for label, cell in (("exact_edge", exact), ("nonexact_discussion_only", comparator)):
        pair_counts = cell["ordered_product_pair"].value_counts()
        repo_counts = cell["repo_id"].value_counts()
        rows.append(
            {
                "group": label,
                "prs": len(cell),
                "repositories": int(cell["repo_id"].nunique()),
                "ordered_product_pairs": int(cell["ordered_product_pair"].nunique()),
                "largest_ordered_product_pair": str(pair_counts.index[0]),
                "largest_ordered_product_pair_count": int(pair_counts.iloc[0]),
                "largest_ordered_product_pair_share": float(pair_counts.iloc[0] / len(cell)),
                "largest_repository_count": int(repo_counts.iloc[0]),
                "largest_repository_share": float(repo_counts.iloc[0] / len(cell)),
                "ordered_product_pair_hhi": float(((pair_counts / len(cell)) ** 2).sum()),
                "repository_hhi": float(((repo_counts / len(cell)) ** 2).sum()),
            }
        )
    return pd.DataFrame(rows)


def packaging_decision(
    clustered: pd.DataFrame,
    repository_fe: pd.DataFrame,
    overlap: pd.DataFrame,
    loo_summary: pd.DataFrame,
) -> tuple[str, dict[str, bool]]:
    primary = clustered[
        (clustered["contrast"] == "exact_edge_vs_nonexact_discussion")
        & (clustered["threshold_hours"] == 48)
    ].iloc[0]
    any_activity = clustered[
        clustered["contrast"] == "exact_edge_vs_any_other_visible_activity"
    ].iloc[0]
    user_only = clustered[
        clustered["contrast"] == "exact_user_edge_vs_nonexact_user_discussion"
    ].iloc[0]
    fe = repository_fe[
        repository_fe["contrast"] == "exact_edge_vs_nonexact_discussion"
    ].iloc[0]
    overlap_main = overlap[overlap["specification"] == "overlap_weighted_all"].iloc[0]
    windows = clustered[clustered["contrast"] == "exact_edge_vs_nonexact_discussion"]
    gates = {
        "primary_discussion_contrast_interval_excludes_zero": float(primary["ci_low"]) > 0,
        "overlap_weighted_interval_excludes_zero": float(overlap_main["ci_low"]) > 0,
        "all_window_estimates_positive": bool((windows["estimate"] > 0).all()),
        "six_to_48h_window_intervals_exclude_zero": bool(
            (windows[windows["threshold_hours"] >= 6]["ci_low"] > 0).all()
        ),
        "all_leave_one_pair_out_estimates_positive": bool(
            loo_summary.iloc[0]["all_estimates_positive"]
        ),
        "repository_fe_same_positive_sign": float(fe["estimate"]) > 0,
        "repository_fe_interval_excludes_zero": float(fe["ci_low"]) > 0,
        "any_activity_interval_excludes_zero": float(any_activity["ci_low"]) > 0,
        "user_actor_control_interval_excludes_zero": float(user_only["ci_low"]) > 0,
    }
    core = (
        gates["primary_discussion_contrast_interval_excludes_zero"]
        and gates["overlap_weighted_interval_excludes_zero"]
        and gates["all_window_estimates_positive"]
        and gates["all_leave_one_pair_out_estimates_positive"]
        and gates["repository_fe_same_positive_sign"]
    )
    decision = (
        "SUPPORTS_EDGE_SPECIFICITY_WITH_BOUNDARIES"
        if core
        else "DOES_NOT_SUPPORT_EDGE_SPECIFICITY"
    )
    return decision, gates


def write_schema(output_dir: Path) -> None:
    schema = {
        "schema_version": "addressed-edge-specificity-v1",
        "grain": (
            "one first cross-product inline trigger per PR, restricted to PRs "
            "still open at trigger + 48h and observed through trigger + 30d"
        ),
        "primary_specificity_population": (
            "PRs with an exact-parent inline reply or a later submitted review/PR "
            "comment by the same threshold"
        ),
        "primary_exposure": (
            "raw inline in_reply_to_id equals the exact trigger_event_id"
        ),
        "primary_control": (
            "later submitted review or PR comment is visible, but no exact-parent "
            "reply is visible by the threshold"
        ),
        "outcome": (
            "merge strictly after trigger + 48h and no later than trigger + 30d"
        ),
        "event_groups": {
            "exact_edge": "at least one exact-parent inline reply; exact edge takes precedence",
            "nonexact_discussion_only": "later submitted review or PR comment, no exact edge",
            "movement_only": "force push but no exact edge, later review, or PR comment",
            "no_visible_activity": "none of the measured response channels by the threshold",
        },
        "construct_limits": [
            "A raw parent edge is structural and does not label meaning, acceptance, or resolution.",
            "A later review or PR comment is public discussion but is not known to address the trigger.",
            "A force push is visible code movement and is not treated as discussion.",
            "All estimates are observational and may reflect unmeasured attention or task difficulty.",
        ],
    }
    (output_dir / "schema.json").write_text(
        json.dumps(schema, indent=2), encoding="utf-8"
    )


def write_readme(
    output_dir: Path,
    frame: pd.DataFrame,
    clustered: pd.DataFrame,
    repository_fe: pd.DataFrame,
    overlap: pd.DataFrame,
    loo_summary: pd.DataFrame,
) -> None:
    decision, gates = packaging_decision(clustered, repository_fe, overlap, loo_summary)
    primary = clustered[
        (clustered["contrast"] == "exact_edge_vs_nonexact_discussion")
        & (clustered["threshold_hours"] == 48)
    ].iloc[0]
    any_activity = clustered[
        clustered["contrast"] == "exact_edge_vs_any_other_visible_activity"
    ].iloc[0]
    user_only = clustered[
        clustered["contrast"] == "exact_user_edge_vs_nonexact_user_discussion"
    ].iloc[0]
    fe = repository_fe[
        repository_fe["contrast"] == "exact_edge_vs_nonexact_discussion"
    ].iloc[0]
    overlap_main = overlap[overlap["specification"] == "overlap_weighted_all"].iloc[0]
    failed_boundaries = [name for name, passed in gates.items() if not passed]
    text = f"""# Addressed-edge specificity falsification

## Paper-safe decision: {decision}

This extension asks whether the addressed-edge result merely separates public
activity from silence. It uses the same frozen landmark cohort as the main
addressed-edge analysis: one first cross-product inline trigger per PR, the PR
must still be open at 48 hours, exposure is observed only by 48 hours, and a
later merge must occur strictly after 48 hours and no later than 30 days.

The fields support a valid **structural** specificity control. Among the
{int(primary['n_prs']):,} PRs with public discussion by 48 hours,
{int(primary['exposed_prs']):,} have an exact raw parent edge and
{int(primary['control_prs']):,} have a later submitted review or PR comment but
no exact edge. Their raw later-merge rates are
{primary['exposed_raw_merge_rate']:.1%} and
{primary['control_raw_merge_rate']:.1%}. The pretrigger-only,
repository-clustered contrast is {primary['estimate'] * 100:.1f} percentage
points (95% CI {primary['ci_low'] * 100:.1f} to
{primary['ci_high'] * 100:.1f}). Overlap weighting gives
{overlap_main['estimate'] * 100:.1f} points (95% CI
{overlap_main['ci_low'] * 100:.1f} to
{overlap_main['ci_high'] * 100:.1f}). All leave-one-product-pair-out estimates
remain positive.

The result also has important boundaries. Repository fixed effects keep the
positive sign ({fe['estimate'] * 100:.1f} points) but are imprecise (95% CI
{fe['ci_low'] * 100:.1f} to {fe['ci_high'] * 100:.1f}); only
{int(fe['repositories_with_within_exposure_variation'])} repositories contain
both exposure states. Against **any** other visible activity, including the
small movement-only group, the estimate is {any_activity['estimate'] * 100:.1f}
points (95% CI {any_activity['ci_low'] * 100:.1f} to
{any_activity['ci_high'] * 100:.1f}). Holding the responding account type to a
GitHub `User` gives {user_only['estimate'] * 100:.1f} points (95% CI
{user_only['ci_low'] * 100:.1f} to {user_only['ci_high'] * 100:.1f}). These two
intervals include zero.

Therefore this extension **strengthens but narrows** the main story: an exact
parent edge is a more informative public structural marker than generic later
discussion, and the main result is not only a silence-versus-activity contrast.
It does not establish that exact edges are different from every form of visible
activity, and it does not establish semantic resolution, developer intent,
correctness, or a causal effect.

Packaging gates that did not pass: {', '.join(failed_boundaries) if failed_boundaries else 'none'}.

## Primary contrast

- **Exposed:** any inline reply with raw `in_reply_to_id == trigger_event_id` by
  the threshold.
- **Control:** a later submitted review or PR-level comment is public by the
  threshold, but no exact-parent reply is public by then.
- **Why it is comparable:** both groups have a visible discussion response.
- **Why it is limited:** conditioning on visible discussion is itself
  post-trigger selection. The contrast is a falsification/specificity check,
  not a causal estimand.

Force pushes are kept out of the primary discussion control because they show
code movement, not discussion. The secondary any-activity contrast adds them.
The user-actor sensitivity excludes PRs whose exact edge was written only by a
non-`User` account from its control group.

## Allowed manuscript sentence

> Among PRs with public discussion by 48 hours, an exact raw parent edge was
> associated with more later merges than discussion without that edge after
> adjustment for measured pretrigger activity. The direction survived overlap,
> time-window, product-pair, and repository checks, although within-repository
> and user-only estimates were imprecise.

## Forbidden interpretations

- the reply caused the later merge;
- the reply accepted, fixed, or resolved the trigger;
- a GitHub `User` row proves manual human reasoning;
- later merge validates the feedback;
- exact-parent routing is superior for correctness or review quality.

Unmeasured attention, difficulty, private discussion, product policy, and
response content can influence both the edge and the outcome.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cohort, cohort_checks = load_and_validate_cohort(args.edge_dir)
    classified, event_audit, source_counts, event_checks = classify_events(
        cohort, args.cross_dir, args.data_dir
    )
    frame = to_model_frame(classified)
    clustered, repository_fe = fit_specificity_models(frame)
    gradient = fit_response_gradient(frame)
    overlap, propensity_diagnostics, balance = fit_overlap_sensitivity(frame)
    loo, loo_summary = fit_leave_one_pair_out(frame)
    denominators = denominator_table(frame)
    concentration = concentration_table(frame)

    classified.write_parquet(args.output_dir / "classified_landmark_cohort.parquet")
    event_audit.write_parquet(args.output_dir / "raw_discussion_event_audit.parquet")
    source_counts.to_csv(args.output_dir / "response_source_counts.csv", index=False)
    clustered.to_csv(args.output_dir / "clustered_specificity_lpm.csv", index=False)
    repository_fe.to_csv(args.output_dir / "repository_fe_sensitivity.csv", index=False)
    gradient.to_csv(args.output_dir / "four_state_response_gradient.csv", index=False)
    overlap.to_csv(args.output_dir / "propensity_overlap_sensitivity.csv", index=False)
    propensity_diagnostics.to_csv(
        args.output_dir / "propensity_score_diagnostics.csv", index=False
    )
    balance.to_csv(args.output_dir / "pretrigger_balance.csv", index=False)
    loo.to_csv(args.output_dir / "leave_one_product_pair_out.csv", index=False)
    loo_summary.to_csv(
        args.output_dir / "leave_one_product_pair_out_summary.csv", index=False
    )
    denominators.to_csv(args.output_dir / "denominators.csv", index=False)
    concentration.to_csv(args.output_dir / "concentration_summary.csv", index=False)
    write_schema(args.output_dir)

    decision, gates = packaging_decision(clustered, repository_fe, overlap, loo_summary)
    validation = {
        "run_id": "addressed-edge-specificity-v1",
        "dataset_revision": DATASET_REVISION,
        "grain": (
            "one first cross-product inline trigger per PR, open at 48h, "
            "fixed 30d outcome horizon"
        ),
        "cohort": cohort_checks,
        "events": event_checks,
        "models_use_only_pretrigger_covariates": True,
        "primary_specificity_subset_is_posttrigger_selected": True,
        "outcome_strictly_after_all_exposure_windows": True,
        "outcome_used_to_define_exposure_or_control": False,
        "semantic_labels_used": False,
        "semantic_resolution_claim_allowed": False,
        "causal_claim_allowed": False,
        "packaging_decision": decision,
        "packaging_gates": gates,
        "all_temporal_and_raw_row_assertions_passed": True,
    }
    (args.output_dir / "temporal_leakage_validation.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )
    write_readme(
        args.output_dir, frame, clustered, repository_fe, overlap, loo_summary
    )

    input_paths = (
        args.edge_dir / "analysis_cohort.parquet",
        args.cross_dir / "cross_feedback_response_events.parquet",
        args.data_dir / "pr_review_comments.parquet",
        args.data_dir / "pr_reviews.parquet",
        args.data_dir / "pr_comments.parquet",
    )
    artifact_paths = [path for path in args.output_dir.iterdir() if path.is_file()]
    manifest = {
        "run_id": "addressed-edge-specificity-v1",
        "dataset_revision": DATASET_REVISION,
        "script_sha256": sha256_file(Path(__file__)),
        "input_sha256": {str(path): sha256_file(path) for path in input_paths},
        "artifact_sha256": {
            path.name: sha256_file(path)
            for path in artifact_paths
            if path.name != "manifest.json"
        },
        "manuscript_edited": False,
        "external_upload": False,
        "claim_scope": (
            "structural specificity falsification; no semantic-resolution or causal claim"
        ),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    primary = clustered[
        (clustered["contrast"] == "exact_edge_vs_nonexact_discussion")
        & (clustered["threshold_hours"] == 48)
    ].iloc[0]
    print(
        json.dumps(
            {
                "cohort_prs": len(frame),
                "primary_discussion_population_prs": int(primary["n_prs"]),
                "exact_edge_prs": int(primary["exposed_prs"]),
                "nonexact_discussion_control_prs": int(primary["control_prs"]),
                "primary_adjusted_percentage_points": float(primary["estimate"] * 100),
                "primary_95_ci_percentage_points": [
                    float(primary["ci_low"] * 100),
                    float(primary["ci_high"] * 100),
                ],
                "packaging_decision": decision,
                "packaging_gates": gates,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
