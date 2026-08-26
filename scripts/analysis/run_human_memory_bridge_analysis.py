"""Analyze whether user-account mediators carry prior repository review history.

The primary history rule is intentionally strict: a prior submitted review must
occur in the same repository, on a different PR, strictly before the focal
cross-product trigger. Results describe public account history; they do not
show unaided human work or a causal effect on integration.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
INPUT = ROOT / "outputs" / "cross_agent_review"
OWNERSHIP = ROOT / "outputs" / "response_ownership"
OUTPUT = ROOT / "outputs" / "human_memory_bridge"

AGENT_ACCOUNT_ALIASES = {
    "claude[bot]": "Claude_Code",
    "copilot": "Copilot",
    "copilot-swe-agent[bot]": "Copilot",
    "copilot-pull-request-reviewer[bot]": "Copilot",
    "cursor[bot]": "Cursor",
    "devin-ai-integration[bot]": "Devin",
    "google-labs-jules[bot]": "Google_Jules",
    "chatgpt-codex-connector[bot]": "OpenAI_Codex",
}


def load_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    chains = pl.read_parquet(INPUT / "cross_feedback_response_chains.parquet")
    events = pl.read_parquet(INPUT / "cross_feedback_response_events.parquet")
    landmark = pl.read_parquet(OWNERSHIP / "ownership_route_48h.parquet")
    pr_repo = (
        pl.read_parquet(DATA / "pull_request.parquet", columns=["id", "repo_id"])
        .rename({"id": "history_pr_id"})
    )
    return chains, events, landmark, pr_repo


def build_review_history(pr_repo: pl.DataFrame) -> pl.DataFrame:
    """Return timestamped user-account submitted reviews at review-event grain."""
    return (
        pl.read_parquet(
            DATA / "pr_reviews.parquet",
            columns=["pr_id", "user", "user_type", "submitted_at"],
        )
        .with_columns(
            pl.col("submitted_at")
            .str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
            .alias("review_dt"),
            pl.col("user").str.to_lowercase().alias("login"),
        )
        .with_columns(
            pl.col("login")
            .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
            .alias("mapped_agent")
        )
        .filter(
            (pl.col("user_type").str.to_lowercase() == "user")
            & pl.col("mapped_agent").is_null()
            & pl.col("review_dt").is_not_null()
            & pl.col("login").is_not_null()
        )
        .rename({"pr_id": "history_pr_id"})
        .join(pr_repo, on="history_pr_id", how="inner")
        .select("history_pr_id", "repo_id", "login", "review_dt")
    )


def build_user_responders(
    chains: pl.DataFrame, events: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, int]:
    """Build distinct PR-user responders and single-account first mediators."""
    users = (
        events.filter(
            (pl.col("hours_after_trigger") <= 48)
            & (pl.col("response_user_type").str.to_lowercase() == "user")
            & pl.col("response_agent").is_null()
        )
        .with_columns(pl.col("response_user").str.to_lowercase().alias("login"))
        .filter(pl.col("login").is_not_null())
        .group_by("pr_id", "login")
        .agg(
            pl.col("response_dt").min().alias("user_first_response_dt"),
            pl.col("response_source")
            .sort_by("response_dt")
            .first()
            .alias("user_first_response_source"),
            pl.len().alias("user_response_events_48h"),
        )
        .join(
            chains.select(
                "pr_id", "repo_id", "repo_url", "author_user", "author_agent",
                "trigger_reviewer_agent", "trigger_source", "trigger_dt",
            ),
            on="pr_id",
            how="inner",
        )
        .with_columns(
            pl.col("user_first_response_dt").min().over("pr_id").alias("first_human_dt"),
            (pl.col("login") == pl.col("author_user").str.to_lowercase()).alias("is_author_account"),
        )
        .with_columns(
            (pl.col("user_first_response_dt") == pl.col("first_human_dt")).alias("is_first_human_account"),
            pl.when(pl.col("is_author_account"))
            .then(pl.lit("author_account"))
            .otherwise(pl.lit("other_user"))
            .alias("account_role"),
        )
        .with_columns(
            pl.col("is_first_human_account").sum().over("pr_id").alias("n_first_human_accounts")
        )
    )
    tied_prs = users.filter(pl.col("n_first_human_accounts") > 1)["pr_id"].n_unique()
    first = users.filter(
        pl.col("is_first_human_account") & (pl.col("n_first_human_accounts") == 1)
    )
    return users, first, tied_prs


def build_first_user_decisive_reviewers(
    chains: pl.DataFrame,
) -> tuple[pl.DataFrame, int]:
    """Return the first observable user-account decisive review after trigger."""
    candidates = (
        pl.read_parquet(
            DATA / "pr_reviews.parquet",
            columns=[
                "pr_id", "pull_request_review_id", "user", "user_type",
                "state", "submitted_at",
            ],
        )
        .with_columns(
            pl.col("submitted_at")
            .str.to_datetime(
                "%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False
            )
            .alias("decision_dt"),
            pl.col("user").str.to_lowercase().alias("login"),
        )
        .with_columns(
            pl.col("login")
            .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
            .alias("mapped_agent")
        )
        .filter(
            pl.col("state").is_in(
                ["APPROVED", "CHANGES_REQUESTED", "DISMISSED"]
            )
            & pl.col("decision_dt").is_not_null()
            & pl.col("login").is_not_null()
        )
        .join(
            chains.select(
                "pr_id", "repo_id", "repo_url", "author_user",
                "author_agent", "trigger_reviewer_agent", "trigger_source",
                "trigger_review_id", "trigger_dt", "response_end_dt",
            ),
            on="pr_id",
            how="inner",
        )
        .filter(
            (pl.col("decision_dt") > pl.col("trigger_dt"))
            & (pl.col("decision_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("trigger_review_id").is_null()
                | (
                    pl.col("pull_request_review_id")
                    != pl.col("trigger_review_id")
                )
            )
        )
        .sort(["pr_id", "decision_dt", "pull_request_review_id"])
        .unique("pr_id", keep="first", maintain_order=True)
    )
    first = (
        candidates.filter(
            (pl.col("user_type").str.to_lowercase() == "user")
            & pl.col("mapped_agent").is_null()
        )
        .with_columns(
            (pl.col("login") == pl.col("author_user").str.to_lowercase()).alias(
                "is_author_account"
            )
        )
        .with_columns(
            pl.when(pl.col("is_author_account"))
            .then(pl.lit("author_account"))
            .otherwise(pl.lit("other_user"))
            .alias("account_role")
        )
    )
    return first, 0


def add_strict_prior_history(
    targets: pl.DataFrame,
    history: pl.DataFrame,
    target_key: str,
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Add prior-different-PR review count and recency to target accounts."""
    targets = targets.with_row_index("target_row_id")
    candidate = targets.select(
        "target_row_id", target_key, "repo_id", "login", "trigger_dt"
    ).join(history, on=["repo_id", "login"], how="inner")
    invalid_same_pr = candidate.filter(
        pl.col("history_pr_id") == pl.col(target_key)
    ).height
    invalid_future_or_equal = candidate.filter(
        pl.col("review_dt") >= pl.col("trigger_dt")
    ).height
    valid = candidate.filter(
        (pl.col("history_pr_id") != pl.col(target_key))
        & (pl.col("review_dt") < pl.col("trigger_dt"))
    )
    aggregate = valid.group_by("target_row_id").agg(
        pl.len().alias("prior_review_events"),
        pl.col("history_pr_id").n_unique().alias("prior_review_prs"),
        pl.col("review_dt").max().alias("last_prior_review_dt"),
    )
    enriched = (
        targets.join(aggregate, on="target_row_id", how="left")
        .with_columns(
            pl.col("prior_review_events").fill_null(0),
            pl.col("prior_review_prs").fill_null(0),
        )
        .with_columns(
            (pl.col("prior_review_prs") > 0).alias("prior_different_pr_reviewer"),
            (
                (pl.col("trigger_dt") - pl.col("last_prior_review_dt")).dt.total_seconds()
                / 86400.0
            ).alias("prior_review_recency_days"),
        )
        .drop("target_row_id")
    )
    checks = {
        "candidate_same_pr_rows_excluded": invalid_same_pr,
        "candidate_future_or_equal_rows_excluded": invalid_future_or_equal,
        "valid_prior_history_rows": valid.height,
        "valid_history_same_pr_rows": valid.filter(
            pl.col("history_pr_id") == pl.col(target_key)
        ).height,
        "valid_history_future_or_equal_rows": valid.filter(
            pl.col("review_dt") >= pl.col("trigger_dt")
        ).height,
    }
    return enriched, checks


def role_summary(
    first: pl.DataFrame, total_label: str = "all_first_mediators"
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role in ["author_account", "other_user", total_label]:
        cell = first if role == total_label else first.filter(pl.col("account_role") == role)
        experienced = cell.filter(pl.col("prior_different_pr_reviewer"))
        rows.append(
            {
                "account_role": role,
                "prs": cell.height,
                "repositories": cell["repo_id"].n_unique() if cell.height else 0,
                "prior_reviewer_share": float(cell["prior_different_pr_reviewer"].mean()) if cell.height else np.nan,
                "median_prior_review_prs_among_experienced": float(experienced["prior_review_prs"].median()) if experienced.height else np.nan,
                "median_prior_review_events_among_experienced": float(experienced["prior_review_events"].median()) if experienced.height else np.nan,
                "median_recency_days_among_experienced": float(experienced["prior_review_recency_days"].median()) if experienced.height else np.nan,
            }
        )
    return pd.DataFrame(rows)


def responder_position_summary(responders: pl.DataFrame) -> pd.DataFrame:
    frame = responders.with_columns(
        pl.when(pl.col("is_first_human_account"))
        .then(pl.lit("first"))
        .otherwise(pl.lit("later_only"))
        .alias("responder_position")
    )
    return (
        frame.group_by("responder_position", "account_role")
        .agg(
            pl.len().alias("pr_user_accounts"),
            pl.col("pr_id").n_unique().alias("prs"),
            pl.col("repo_id").n_unique().alias("repositories"),
            pl.col("prior_different_pr_reviewer").mean().alias("prior_reviewer_share"),
            pl.col("prior_review_prs").median().alias("median_prior_review_prs"),
            pl.col("prior_review_recency_days").filter(pl.col("prior_different_pr_reviewer")).median().alias("median_recency_days"),
        )
        .sort("responder_position", "account_role")
        .to_pandas()
    )


def first_mediator_channel_summary(first: pl.DataFrame) -> pd.DataFrame:
    return (
        first.group_by("user_first_response_source", "account_role")
        .agg(
            pl.len().alias("prs"),
            pl.col("repo_id").n_unique().alias("repositories"),
            pl.col("prior_different_pr_reviewer").mean().alias(
                "prior_reviewer_share"
            ),
        )
        .sort(
            ["user_first_response_source", "prs"],
            descending=[False, True],
        )
        .to_pandas()
    )


def history_depth_summary(first: pl.DataFrame) -> pd.DataFrame:
    return (
        first.with_columns(
            pl.when(pl.col("prior_review_prs") == 0)
            .then(pl.lit("0"))
            .when(pl.col("prior_review_prs") == 1)
            .then(pl.lit("1"))
            .when(pl.col("prior_review_prs") <= 4)
            .then(pl.lit("2-4"))
            .when(pl.col("prior_review_prs") <= 9)
            .then(pl.lit("5-9"))
            .otherwise(pl.lit("10+"))
            .alias("prior_distinct_pr_bin")
        )
        .group_by("account_role", "prior_distinct_pr_bin")
        .agg(
            pl.len().alias("prs"),
            pl.col("repo_id").n_unique().alias("repositories"),
            pl.col("prior_review_recency_days").median().alias(
                "median_recency_days"
            ),
        )
        .sort("account_role", "prior_distinct_pr_bin")
        .to_pandas()
    )


def author_baseline(chains: pl.DataFrame, history: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, int]]:
    targets = (
        chains.select("pr_id", "repo_id", "trigger_dt", "author_user")
        .with_columns(pl.col("author_user").str.to_lowercase().alias("login"))
        .with_columns(
            pl.when(
                pl.col("login").replace_strict(
                    AGENT_ACCOUNT_ALIASES, default=None
                ).is_not_null()
                | pl.col("login").str.contains(r"\[bot\]$")
            )
            .then(pl.lit("mapped_or_bot_account"))
            .otherwise(pl.lit("user_like_account"))
            .alias("author_account_class")
        )
        .filter(pl.col("login").is_not_null())
    )
    return add_strict_prior_history(targets, history, "pr_id")


def baseline_summary(first: pl.DataFrame, authors: pl.DataFrame, responders: pl.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    groups = {
        "first_user_mediators": first,
        "all_distinct_48h_user_responders": responders,
        "all_cross_feedback_pr_author_accounts": authors,
        "user_like_cross_feedback_pr_author_accounts": authors.filter(
            pl.col("author_account_class") == "user_like_account"
        ),
        "mapped_or_bot_cross_feedback_pr_author_accounts": authors.filter(
            pl.col("author_account_class") == "mapped_or_bot_account"
        ),
    }
    for label, cell in groups.items():
        experienced = cell.filter(pl.col("prior_different_pr_reviewer"))
        median_prior_prs = (
            experienced["prior_review_prs"].median()
            if experienced.height
            else np.nan
        )
        rows.append(
            {
                "population": label,
                "rows": cell.height,
                "prs": cell["pr_id"].n_unique(),
                "repositories": cell["repo_id"].n_unique(),
                "prior_reviewer_share": float(cell["prior_different_pr_reviewer"].mean()),
                "median_prior_review_prs_among_experienced": float(median_prior_prs),
            }
        )
    return pd.DataFrame(rows)


def clustered_models(first: pl.DataFrame, responders: pl.DataFrame) -> pd.DataFrame:
    tables: list[pd.DataFrame] = []
    first_pd = first.select(
        "prior_different_pr_reviewer", "account_role", "repo_id"
    ).to_pandas()
    first_pd["outcome"] = first_pd["prior_different_pr_reviewer"].astype(float)
    first_pd["other_user"] = (first_pd["account_role"] == "other_user").astype(float)
    model = sm.OLS(first_pd["outcome"], sm.add_constant(first_pd[["other_user"]])).fit(
        cov_type="cluster", cov_kwds={"groups": first_pd["repo_id"], "use_correction": True}
    )
    table = pd.DataFrame(
        {
            "model": "first_mediator_other_vs_author",
            "term": model.params.index,
            "estimate": model.params.values,
            "std_error": model.bse.values,
            "ci_low": model.conf_int()[0].values,
            "ci_high": model.conf_int()[1].values,
            "p_value": model.pvalues.values,
            "n": int(model.nobs),
            "repositories": int(first_pd["repo_id"].nunique()),
        }
    )
    tables.append(table)

    response_pd = responders.select(
        "prior_different_pr_reviewer", "is_first_human_account",
        "is_author_account", "repo_id",
    ).to_pandas()
    response_pd["outcome"] = response_pd["prior_different_pr_reviewer"].astype(float)
    response_pd["is_first"] = response_pd["is_first_human_account"].astype(float)
    response_pd["is_author"] = response_pd["is_author_account"].astype(float)
    model = sm.OLS(
        response_pd["outcome"],
        sm.add_constant(response_pd[["is_first", "is_author"]]),
    ).fit(
        cov_type="cluster", cov_kwds={"groups": response_pd["repo_id"], "use_correction": True}
    )
    tables.append(
        pd.DataFrame(
            {
                "model": "all_responders_first_position",
                "term": model.params.index,
                "estimate": model.params.values,
                "std_error": model.bse.values,
                "ci_low": model.conf_int()[0].values,
                "ci_high": model.conf_int()[1].values,
                "p_value": model.pvalues.values,
                "n": int(model.nobs),
                "repositories": int(response_pd["repo_id"].nunique()),
            }
        )
    )
    return pd.concat(tables, ignore_index=True)


def concentration_and_leave_one_out(first: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    counts = first.group_by("repo_id").agg(pl.len().alias("n")).sort("n", descending=True)
    total = first.height
    shares = counts.with_columns((pl.col("n") / total).alias("share"))
    concentration = pd.DataFrame(
        [
            {
                "first_mediator_rows": total,
                "repositories": counts.height,
                "largest_repo_rows": int(counts["n"].max()),
                "largest_repo_share": float(shares["share"].max()),
                "top_10_repo_share": float(shares.head(10)["share"].sum()),
                "repo_hhi": float((shares["share"] ** 2).sum()),
            }
        ]
    )
    loo_rows: list[dict[str, object]] = []
    for repo_id in counts["repo_id"].to_list():
        kept = first.filter(pl.col("repo_id") != repo_id)
        loo_rows.append(
            {
                "omitted_repo_id": repo_id,
                "n": kept.height,
                "prior_reviewer_share": float(kept["prior_different_pr_reviewer"].mean()),
            }
        )
    loo = pd.DataFrame(loo_rows)
    loo_summary = pd.DataFrame(
        [
            {
                "full_share": float(first["prior_different_pr_reviewer"].mean()),
                "leave_one_repo_min": float(loo["prior_reviewer_share"].min()),
                "leave_one_repo_max": float(loo["prior_reviewer_share"].max()),
                "leave_one_repo_max_abs_change": float(
                    (loo["prior_reviewer_share"] - first["prior_different_pr_reviewer"].mean()).abs().max()
                ),
            }
        ]
    )
    return concentration, loo, loo_summary


def product_pair_concentration(first: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = (
        first.group_by("author_agent", "trigger_reviewer_agent")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .with_columns((pl.col("n") / first.height).alias("share"))
    )
    full_share = float(first["prior_different_pr_reviewer"].mean())
    loo_rows: list[dict[str, object]] = []
    for row in counts.iter_rows(named=True):
        kept = first.filter(
            ~(
                (pl.col("author_agent") == row["author_agent"])
                & (
                    pl.col("trigger_reviewer_agent")
                    == row["trigger_reviewer_agent"]
                )
            )
        )
        loo_rows.append(
            {
                "omitted_product_pair": (
                    f"{row['author_agent']} -> {row['trigger_reviewer_agent']}"
                ),
                "omitted_rows": row["n"],
                "n": kept.height,
                "prior_reviewer_share": float(
                    kept["prior_different_pr_reviewer"].mean()
                ),
            }
        )
    loo = pd.DataFrame(loo_rows)
    summary = pd.DataFrame(
        [
            {
                "product_pairs": counts.height,
                "largest_pair_rows": int(counts["n"].max()),
                "largest_pair_share": float(counts["share"].max()),
                "top_5_pair_share": float(counts.head(5)["share"].sum()),
                "product_pair_hhi": float((counts["share"] ** 2).sum()),
                "full_prior_reviewer_share": full_share,
                "leave_one_pair_min": float(loo["prior_reviewer_share"].min()),
                "leave_one_pair_max": float(loo["prior_reviewer_share"].max()),
                "leave_one_pair_max_abs_change": float(
                    (loo["prior_reviewer_share"] - full_share).abs().max()
                ),
            }
        ]
    )
    return summary, loo


def landmark_descriptive(first: pl.DataFrame, landmark: pl.DataFrame) -> pd.DataFrame:
    joined = landmark.join(
        first.select(
            "pr_id", "account_role", "prior_different_pr_reviewer",
            "prior_review_prs", "prior_review_recency_days",
        ),
        on="pr_id",
        how="inner",
    )
    if not joined.height:
        return pd.DataFrame()
    return (
        joined.group_by(
            "ownership_route_48h", "account_role", "prior_different_pr_reviewer"
        )
        .agg(
            pl.len().alias("prs"),
            pl.col("repo_id").n_unique().alias("repositories"),
            pl.col("merged_from_48h_to_30d").mean().alias("later_merge_rate_descriptive"),
        )
        .sort("ownership_route_48h", "account_role", "prior_different_pr_reviewer")
        .to_pandas()
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    chains, events, landmark, pr_repo = load_inputs()
    history = build_review_history(pr_repo)
    responders, first, tied_prs = build_user_responders(chains, events)
    responders, responder_checks = add_strict_prior_history(
        responders, history, "pr_id"
    )
    first = responders.filter(
        pl.col("is_first_human_account") & (pl.col("n_first_human_accounts") == 1)
    )
    authors, author_checks = author_baseline(chains, history)
    decisive, decisive_tied_prs = build_first_user_decisive_reviewers(chains)
    decisive, decisive_checks = add_strict_prior_history(
        decisive, history, "pr_id"
    )

    first.write_parquet(OUTPUT / "first_human_mediators.parquet", compression="zstd")
    responders.write_parquet(OUTPUT / "distinct_48h_user_responders.parquet", compression="zstd")
    decisive.write_parquet(
        OUTPUT / "first_user_decisive_reviewers.parquet", compression="zstd"
    )
    role_summary(first).to_csv(OUTPUT / "first_mediator_role_summary.csv", index=False)
    role_summary(decisive, "all_first_decisive_reviewers").to_csv(
        OUTPUT / "first_decisive_reviewer_role_summary.csv", index=False
    )
    responder_position_summary(responders).to_csv(
        OUTPUT / "responder_position_summary.csv", index=False
    )
    first_mediator_channel_summary(first).to_csv(
        OUTPUT / "first_mediator_channel_summary.csv", index=False
    )
    history_depth_summary(first).to_csv(
        OUTPUT / "history_depth_summary.csv", index=False
    )
    baseline_summary(first, authors, responders).to_csv(
        OUTPUT / "observable_population_baselines.csv", index=False
    )
    clustered_models(first, responders).to_csv(
        OUTPUT / "repo_clustered_history_models.csv", index=False
    )
    concentration, loo, loo_summary = concentration_and_leave_one_out(first)
    concentration.to_csv(OUTPUT / "repo_concentration.csv", index=False)
    loo.to_csv(OUTPUT / "leave_one_repo_out.csv", index=False)
    loo_summary.to_csv(OUTPUT / "leave_one_repo_out_summary.csv", index=False)
    pair_concentration, pair_loo = product_pair_concentration(first)
    pair_concentration.to_csv(
        OUTPUT / "product_pair_concentration.csv", index=False
    )
    pair_loo.to_csv(
        OUTPUT / "leave_one_product_pair_out.csv", index=False
    )
    landmark_descriptive(first, landmark).to_csv(
        OUTPUT / "landmark_later_merge_descriptive.csv", index=False
    )

    validation = {
        "cross_feedback_prs": chains.height,
        "distinct_pr_user_responders_48h": responders.height,
        "single_account_first_human_mediator_prs": first.height,
        "simultaneous_first_human_account_prs_excluded": tied_prs,
        "single_account_first_user_decisive_reviewer_prs": decisive.height,
        "simultaneous_first_decisive_account_prs_excluded": decisive_tied_prs,
        "history_rule": "same repository, different PR, submitted strictly before trigger",
        "responder_history_checks": responder_checks,
        "author_baseline_history_checks": author_checks,
        "decisive_reviewer_history_checks": decisive_checks,
        "no_same_pr_history_in_valid_matches": responder_checks[
            "valid_history_same_pr_rows"
        ] == 0
        and author_checks["valid_history_same_pr_rows"] == 0
        and decisive_checks["valid_history_same_pr_rows"] == 0,
        "no_future_or_equal_history_in_valid_matches": responder_checks[
            "valid_history_future_or_equal_rows"
        ] == 0
        and author_checks["valid_history_future_or_equal_rows"] == 0
        and decisive_checks["valid_history_future_or_equal_rows"] == 0,
        "interpretation": "observable account history; descriptive and non-causal",
    }
    (OUTPUT / "validation.json").write_text(
        json.dumps(validation, indent=2, default=str), encoding="utf-8"
    )
    print("ROLE SUMMARY", role_summary(first).to_dict(orient="records"))
    print("BASELINES", baseline_summary(first, authors, responders).to_dict(orient="records"))
    print("LOO", loo_summary.to_dict(orient="records"))
    print("VALIDATION", validation)


if __name__ == "__main__":
    main()
