from __future__ import annotations

import bisect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CROSS_DIR = ROOT / "outputs" / "cross_agent_review"
OWNERSHIP_DIR = ROOT / "outputs" / "response_ownership"
OUTPUT_DIR = ROOT / "outputs" / "coordination_topology"
SEED = 20260826


def _cluster_bootstrap(
    differences: np.ndarray,
    clusters: np.ndarray,
    draws: int = 10_000,
) -> tuple[float, float]:
    """Pair-weighted cluster bootstrap that resamples whole repositories."""
    frame = pd.DataFrame({"difference": differences, "cluster": clusters})
    grouped = frame.groupby("cluster", sort=True)["difference"].agg(["sum", "size"])
    sums = grouped["sum"].to_numpy(dtype=float)
    sizes = grouped["size"].to_numpy(dtype=float)
    rng = np.random.default_rng(SEED)
    sampled = rng.integers(0, len(grouped), size=(draws, len(grouped)))
    estimates = sums[sampled].sum(axis=1) / sizes[sampled].sum(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def _pair_bootstrap(differences: np.ndarray, draws: int = 10_000) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    sampled = rng.choice(
        differences, size=(draws, len(differences)), replace=True
    ).mean(axis=1)
    low, high = np.quantile(sampled, [0.025, 0.975])
    return float(low), float(high)


def build_participation_funnel() -> pd.DataFrame:
    chains = pl.read_parquet(CROSS_DIR / "cross_feedback_response_chains.parquet")
    events = pl.read_parquet(CROSS_DIR / "cross_feedback_response_events.parquet")
    denominator = chains.height
    exact_reply_prs = int((chains["direct_inline_replies"] > 0).sum())
    strict_agent_reply_prs = (
        events.filter(
            (pl.col("response_source") == "direct_inline_reply")
            & pl.col("response_agent").is_not_null()
            & (pl.col("response_agent") != pl.col("trigger_reviewer_agent"))
        )["pr_id"]
        .n_unique()
    )
    visible_prs = int(chains["any_observable_response"].sum())
    stages = [
        ("Complete cross-product trigger cohort", denominator),
        ("Any later visible action", visible_prs),
        ("Exact reply to the trigger", exact_reply_prs),
        ("Mapped different-product exact reply", strict_agent_reply_prs),
    ]
    return pd.DataFrame(
        [
            {
                "stage": stage,
                "prs": count,
                "share_of_trigger_cohort": count / denominator,
            }
            for stage, count in stages
        ]
    )


def build_thread_continuity_summary() -> pd.DataFrame:
    chains = pl.read_parquet(CROSS_DIR / "cross_feedback_response_chains.parquet")
    visible = chains.filter(pl.col("any_observable_response"))
    exact = int((visible["direct_inline_replies"] > 0).sum())
    outside_only = visible.height - exact
    return pd.DataFrame(
        [
            {
                "visible_followup_location": "includes_exact_trigger_reply",
                "prs": exact,
                "share_among_responsive_prs": exact / visible.height,
            },
            {
                "visible_followup_location": "only_elsewhere_in_public_trace",
                "prs": outside_only,
                "share_among_responsive_prs": outside_only / visible.height,
            },
        ]
    )


def _binary_pair_values(
    pairs: pd.DataFrame, column: str
) -> tuple[pd.Series, pd.Series]:
    cross = pairs[f"{column}_cross"]
    same = pairs[f"{column}_same"]
    if column not in {"any_observable_response", "merged_within_response_window"}:
        cross = cross > 0
        same = same > 0
    return cross.astype(float), same.astype(float)


def _nearest_pairs_without_replacement(
    frame: pd.DataFrame, strata: list[str]
) -> pd.DataFrame:
    """Pair cross and same rows inside exact strata by nearest calendar time."""
    grouped = {
        key: group.sort_values("trigger_dt")
        for key, group in frame.groupby(strata, dropna=False, sort=False)
    }
    relation_position = strata.index("feedback_relation")
    base_keys = {
        key[:relation_position] + key[relation_position + 1 :] for key in grouped
    }
    rows: list[dict[str, object]] = []
    for base_key in sorted(
        base_keys,
        key=lambda values: tuple("" if value is None else str(value) for value in values),
    ):
        cross_key = (
            base_key[:relation_position]
            + ("cross_product",)
            + base_key[relation_position:]
        )
        same_key = (
            base_key[:relation_position]
            + ("same_product",)
            + base_key[relation_position:]
        )
        if cross_key not in grouped or same_key not in grouped:
            continue
        available = [
            (timestamp.value, int(row_id))
            for timestamp, row_id in zip(
                grouped[same_key]["trigger_dt"],
                grouped[same_key]["row_id"],
                strict=True,
            )
        ]
        for _, cross_row in grouped[cross_key].iterrows():
            if not available:
                break
            target = cross_row["trigger_dt"].value
            position = bisect.bisect_left(available, (target, -1))
            candidates = [position] if position < len(available) else []
            if position:
                candidates.append(position - 1)
            chosen = min(candidates, key=lambda index: abs(available[index][0] - target))
            same_time, same_row_id = available.pop(chosen)
            rows.append(
                {
                    "cross_row_id": int(cross_row["row_id"]),
                    "same_row_id": same_row_id,
                    "trigger_gap_hours": abs(same_time - target) / 3.6e12,
                }
            )
    keys = pd.DataFrame(rows)
    if keys.empty:
        return keys
    cross = frame.add_suffix("_cross")
    same = frame.add_suffix("_same")
    return (
        keys.merge(
            cross,
            left_on="cross_row_id",
            right_on="row_id_cross",
            how="inner",
        )
        .merge(
            same,
            left_on="same_row_id",
            right_on="row_id_same",
            how="inner",
        )
    )


def build_matched_visibility_contrasts() -> tuple[pd.DataFrame, pd.DataFrame]:
    cohort = pd.read_parquet(CROSS_DIR / "first_agent_feedback_cohort.parquet")
    cohort["author_user_norm"] = cohort["author_user"].str.lower()
    cohort["row_id"] = np.arange(len(cohort))
    pairs = _nearest_pairs_without_replacement(
        cohort,
        [
            "repo_url",
            "author_agent",
            "author_user_norm",
            "trigger_source",
            "feedback_relation",
            "trigger_month",
        ],
    )
    pairs = pairs.sort_values(["repo_url_cross", "pr_id_cross"]).reset_index(drop=True)
    pairs.to_parquet(OUTPUT_DIR / "exact_author_stratum_matched_pairs.parquet", index=False)
    specs = {
        "exact_author_user": pairs.copy(),
        "exact_author_user_7d_time_caliper": pairs[
            pairs["trigger_gap_hours"] <= 24 * 7
        ].copy(),
    }
    metrics = {
        "any_visible_followup": "any_observable_response",
        "later_pr_comment": "subsequent_pr_comments",
        "new_review_round": "subsequent_reviews",
        "exact_trigger_reply": "direct_inline_replies",
        "visible_force_push": "force_push_events",
        "merge_within_7d": "merged_within_response_window",
    }
    rows: list[dict[str, object]] = []
    for specification, frame in specs.items():
        for label, column in metrics.items():
            cross, same = _binary_pair_values(frame, column)
            differences = (cross - same).to_numpy()
            pair_low, pair_high = _pair_bootstrap(differences)
            cluster_low, cluster_high = _cluster_bootstrap(
                differences, frame["repo_url_cross"].to_numpy()
            )
            rows.append(
                {
                    "specification": specification,
                    "outcome": label,
                    "pairs": len(frame),
                    "repositories": frame["repo_url_cross"].nunique(),
                    "cross_rate": cross.mean(),
                    "same_rate": same.mean(),
                    "paired_difference": differences.mean(),
                    "pair_bootstrap_ci_low": pair_low,
                    "pair_bootstrap_ci_high": pair_high,
                    "repository_cluster_bootstrap_ci_low": cluster_low,
                    "repository_cluster_bootstrap_ci_high": cluster_high,
                }
            )

    quality = pd.DataFrame(
        [
            {
                "check": "pairs_total",
                "value": len(pairs),
            },
            {
                "check": "repositories",
                "value": int(pairs["repo_url_cross"].nunique()),
            },
            {
                "check": "median_trigger_gap_hours",
                "value": float(pairs["trigger_gap_hours"].median()),
            },
            {
                "check": "largest_repository_pair_share",
                "value": float(
                    pairs["repo_url_cross"].value_counts(normalize=True).iloc[0]
                ),
            },
            {
                "check": "exact_author_user_match",
                "value": bool(
                    (
                        pairs["author_user_norm_cross"]
                        == pairs["author_user_norm_same"]
                    ).all()
                ),
            },
            {
                "check": "exact_repo_match",
                "value": bool((pairs["repo_url_cross"] == pairs["repo_url_same"]).all()),
            },
            {
                "check": "exact_author_product_match",
                "value": bool(
                    (pairs["author_agent_cross"] == pairs["author_agent_same"]).all()
                ),
            },
            {
                "check": "exact_trigger_source_match",
                "value": bool(
                    (pairs["trigger_source_cross"] == pairs["trigger_source_same"]).all()
                ),
            },
            {
                "check": "exact_trigger_month_match",
                "value": bool(
                    (pairs["trigger_month_cross"] == pairs["trigger_month_same"]).all()
                ),
            },
            {
                "check": "unique_cross_prs",
                "value": bool(pairs["pr_id_cross"].is_unique),
            },
            {
                "check": "unique_same_prs",
                "value": bool(pairs["pr_id_same"].is_unique),
            },
        ]
    )
    return pd.DataFrame(rows), quality


def build_route_speed_summary() -> pd.DataFrame:
    events = pl.read_parquet(CROSS_DIR / "cross_feedback_response_events.parquet")
    route = pl.read_parquet(OWNERSHIP_DIR / "ownership_route_48h.parquet")
    early = events.filter(pl.col("hours_after_trigger") <= 48).with_columns(
        (pl.col("response_user_type").str.to_lowercase() == "user").alias(
            "is_user_account"
        ),
        (
            pl.col("response_agent").is_not_null()
            | (pl.col("response_user_type").str.to_lowercase() == "bot")
        ).alias("is_automation"),
    )
    timing = early.group_by("pr_id").agg(
        pl.col("hours_after_trigger").min().alias("first_action_hours"),
        pl.col("hours_after_trigger")
        .filter(pl.col("is_user_account"))
        .min()
        .alias("first_user_hours"),
        pl.col("hours_after_trigger")
        .filter(pl.col("is_automation"))
        .min()
        .alias("first_automation_hours"),
    )
    summary = (
        route.join(timing, on="pr_id", how="left")
        .group_by("ownership_route_48h")
        .agg(
            pl.len().alias("prs"),
            pl.col("merged_from_48h_to_30d").mean().alias("later_merge_rate"),
            pl.col("first_action_hours").median().alias("median_first_action_hours"),
            pl.col("first_user_hours").median().alias("median_first_user_hours"),
            pl.col("first_automation_hours")
            .median()
            .alias("median_first_automation_hours"),
        )
        .sort("prs", descending=True)
    )
    return summary.to_pandas()


def _parse_dt(column: str, alias: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
        .alias(alias)
    )


def build_route_pretrigger_frame() -> pd.DataFrame:
    route = pl.read_parquet(OWNERSHIP_DIR / "ownership_route_48h.parquet")
    key = route.select("pr_id", "trigger_dt")
    prs = (
        pl.read_parquet(DATA / "pull_request.parquet", columns=["id", "created_at"])
        .rename({"id": "pr_id"})
        .with_columns(_parse_dt("created_at", "created_dt"))
        .select("pr_id", "created_dt")
    )
    reviews_raw = pl.scan_parquet(DATA / "pr_reviews.parquet")
    review_key = reviews_raw.select("pull_request_review_id", "pr_id").unique(
        "pull_request_review_id"
    )
    reviews = reviews_raw.select(
        "pr_id",
        "user_type",
        "state",
        _parse_dt("submitted_at", "event_dt"),
    )
    comments = pl.scan_parquet(DATA / "pr_comments.parquet").select(
        "pr_id",
        "user_type",
        pl.lit(None, dtype=pl.String).alias("state"),
        _parse_dt("created_at", "event_dt"),
    )
    inline = (
        pl.scan_parquet(DATA / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "pr_id",
            "user_type",
            pl.lit(None, dtype=pl.String).alias("state"),
            _parse_dt("created_at", "event_dt"),
        )
    )
    pre = (
        pl.concat([reviews, comments, inline])
        .join(key.lazy(), on="pr_id", how="inner")
        .filter(pl.col("event_dt") < pl.col("trigger_dt"))
        .group_by("pr_id")
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
        )
        .collect(engine="streaming")
    )
    pre_push = (
        pl.scan_parquet(DATA / "pr_timeline.parquet")
        .filter(pl.col("event") == "head_ref_force_pushed")
        .select("pr_id", _parse_dt("created_at", "event_dt"))
        .join(key.lazy(), on="pr_id", how="inner")
        .filter(pl.col("event_dt") < pl.col("trigger_dt"))
        .group_by("pr_id")
        .agg(pl.len().alias("pre_force_pushes"))
        .collect(engine="streaming")
    )
    zeros = [
        "pre_events",
        "pre_user_events",
        "pre_bot_events",
        "pre_decisive_reviews",
        "pre_force_pushes",
    ]
    enriched = (
        route.join(prs, on="pr_id", how="left")
        .join(pre, on="pr_id", how="left")
        .join(pre_push, on="pr_id", how="left")
        .with_columns([pl.col(column).fill_null(0) for column in zeros])
        .with_columns(
            (
                (pl.col("trigger_dt") - pl.col("created_dt")).dt.total_seconds()
                / 3600.0
            )
            .clip(0)
            .log1p()
            .alias("log1p_trigger_age_hours"),
            pl.col("pre_events").log1p().alias("log1p_pre_events"),
        )
    )
    enriched.write_parquet(OUTPUT_DIR / "route_pretrigger_features.parquet")
    return enriched.to_pandas()


def _fit_route_direct_contrasts(
    frame: pd.DataFrame, specification: str, extra_controls: list[str]
) -> pd.DataFrame:
    frame = frame.copy()
    frame["merged_from_48h_to_30d"] = frame[
        "merged_from_48h_to_30d"
    ].astype(int)
    frame["trigger_month"] = pd.to_datetime(
        frame["trigger_dt"], utc=True
    ).dt.strftime("%Y-%m")
    route = "C(ownership_route_48h, Treatment('automation_no_human'))"
    formula = (
        "merged_from_48h_to_30d ~ "
        + route
        + " + C(author_agent) + C(trigger_reviewer_agent)"
        + " + C(trigger_source) + C(trigger_month)"
        + (" + " + " + ".join(extra_controls) if extra_controls else "")
    )
    model = smf.ols(formula, data=frame).fit(
        cov_type="cluster", cov_kwds={"groups": frame["repo_id"]}
    )
    intervals = model.conf_int()
    rows = []
    for term, estimate in model.params.items():
        if "ownership_route_48h" not in term:
            continue
        compared_route = term.split("[T.", 1)[1].rstrip("]")
        rows.append(
            {
                "reference_route": "automation_no_human",
                "compared_route": compared_route,
                "specification": specification,
                "estimate": estimate,
                "ci_low": intervals.loc[term, 0],
                "ci_high": intervals.loc[term, 1],
                "p_value": model.pvalues[term],
                "n_prs": int(model.nobs),
                "repositories": frame["repo_id"].nunique(),
            }
        )
    return pd.DataFrame(rows)


def build_route_direct_contrasts() -> pd.DataFrame:
    frame = build_route_pretrigger_frame()
    pretrigger_controls = [
        "log1p_trigger_age_hours",
        "log1p_pre_events",
        "pre_user_events",
        "pre_bot_events",
        "pre_decisive_reviews",
        "pre_force_pushes",
    ]
    return pd.concat(
        [
            _fit_route_direct_contrasts(frame, "base_controls", []),
            _fit_route_direct_contrasts(
                frame, "pretrigger_adjusted", pretrigger_controls
            ),
        ],
        ignore_index=True,
    )


def build_route_leave_one_out_direct_contrasts() -> pd.DataFrame:
    loo = pd.read_csv(OWNERSHIP_DIR / "ownership_route_leave_one_out.csv")
    wide = loo.pivot_table(
        index=["exclusion_unit", "excluded_group", "n_prs"],
        columns="route",
        values="estimate",
    ).reset_index()
    wide["automation_then_user_vs_automation_only"] = (
        wide["automation_then_human"] - wide["automation_no_human"]
    )
    wide["user_first_vs_automation_only"] = (
        wide["human_first"] - wide["automation_no_human"]
    )
    return wide[
        [
            "exclusion_unit",
            "excluded_group",
            "n_prs",
            "automation_then_user_vs_automation_only",
            "user_first_vs_automation_only",
        ]
    ]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    funnel = build_participation_funnel()
    continuity = build_thread_continuity_summary()
    matched, match_quality = build_matched_visibility_contrasts()
    route_speed = build_route_speed_summary()
    route_contrasts = build_route_direct_contrasts()
    route_loo = build_route_leave_one_out_direct_contrasts()

    funnel.to_csv(OUTPUT_DIR / "participation_funnel.csv", index=False)
    continuity.to_csv(OUTPUT_DIR / "thread_continuity_summary.csv", index=False)
    matched.to_csv(OUTPUT_DIR / "matched_visibility_contrasts.csv", index=False)
    match_quality.to_csv(OUTPUT_DIR / "matched_visibility_quality.csv", index=False)
    route_speed.to_csv(OUTPUT_DIR / "route_speed_summary.csv", index=False)
    route_contrasts.to_csv(OUTPUT_DIR / "route_direct_contrasts.csv", index=False)
    route_loo.to_csv(OUTPUT_DIR / "route_direct_contrasts_leave_one_out.csv", index=False)

    primary_visibility = matched[
        (matched["specification"] == "exact_author_user")
        & (matched["outcome"] == "any_visible_followup")
    ].iloc[0]
    hybrid = route_contrasts[
        (route_contrasts["compared_route"] == "automation_then_human")
        & (route_contrasts["specification"] == "pretrigger_adjusted")
    ].iloc[0]
    summary = {
        "interpretation": "observational public traces; no causal or semantic-resolution claim",
        "funnel": funnel.to_dict(orient="records"),
        "responsive_prs_with_only_off_thread_followup_share": float(
            continuity.loc[
                continuity["visible_followup_location"]
                == "only_elsewhere_in_public_trace",
                "share_among_responsive_prs",
            ].iloc[0]
        ),
        "same_author_visibility_gap": {
            "pairs": int(primary_visibility["pairs"]),
            "cross_rate": float(primary_visibility["cross_rate"]),
            "same_rate": float(primary_visibility["same_rate"]),
            "difference": float(primary_visibility["paired_difference"]),
            "repository_cluster_ci": [
                float(primary_visibility["repository_cluster_bootstrap_ci_low"]),
                float(primary_visibility["repository_cluster_bootstrap_ci_high"]),
            ],
        },
        "hybrid_vs_automation_only_later_merge": {
            "difference": float(hybrid["estimate"]),
            "ci": [float(hybrid["ci_low"]), float(hybrid["ci_high"])],
            "p_value": float(hybrid["p_value"]),
        },
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
