from __future__ import annotations

import json
import bisect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    AGENT_ACCOUNT_ALIASES,
    INTERACTION_CUTOFF,
    build_cross_feedback_response_chains,
    build_cross_feedback_response_events,
    classify_agent_account,
    load_pr_backbone,
    parse_timestamp,
)


DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
OUT = ROOT / "outputs" / "feedback_routing"


def feedback_with_text(data_dir: Path) -> pl.DataFrame:
    """Reconstruct the exact first-trigger rule while retaining pre-trigger text."""
    reviews_raw = pl.scan_parquet(data_dir / "pr_reviews.parquet")
    review_key = reviews_raw.select("pull_request_review_id", "pr_id").unique(
        "pull_request_review_id"
    )
    reviews = reviews_raw.select(
        "pr_id", pl.col("id").alias("event_id"),
        pl.col("pull_request_review_id").alias("review_id"),
        "user", "user_type", pl.col("state").cast(pl.String),
        pl.col("body").fill_null("").alias("trigger_body"),
        parse_timestamp("submitted_at", "interaction_dt"),
        pl.lit("submitted_review").alias("source"),
        pl.lit(None, dtype=pl.String).alias("path"),
        pl.lit(None, dtype=pl.String).alias("diff_hunk"),
    )
    comments = pl.scan_parquet(data_dir / "pr_comments.parquet").select(
        "pr_id", pl.col("id").alias("event_id"),
        pl.lit(None, dtype=pl.Int64).alias("review_id"),
        "user", "user_type", pl.lit(None, dtype=pl.String).alias("state"),
        pl.col("body").fill_null("").alias("trigger_body"),
        parse_timestamp("created_at", "interaction_dt"),
        pl.lit("pr_comment").alias("source"),
        pl.lit(None, dtype=pl.String).alias("path"),
        pl.lit(None, dtype=pl.String).alias("diff_hunk"),
    )
    inline = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "pr_id", pl.col("id").alias("event_id"),
            pl.col("pull_request_review_id").alias("review_id"),
            "user", "user_type", pl.lit(None, dtype=pl.String).alias("state"),
            pl.col("body").fill_null("").alias("trigger_body"),
            parse_timestamp("created_at", "interaction_dt"),
            pl.lit("inline_review_comment").alias("source"), "path", "diff_hunk",
        )
    )
    prs = load_pr_backbone(data_dir).select(
        pl.col("id").alias("pr_id"), "repo_id", "repo_url",
        pl.col("agent").alias("author_agent"), "created_dt", "closed_dt",
    )
    return (
        pl.concat([reviews, comments, inline])
        .with_columns(classify_agent_account("user"))
        .filter(pl.col("reviewer_agent").is_not_null())
        .join(prs, on="pr_id", how="inner")
        .filter(
            (pl.col("reviewer_agent") != pl.col("author_agent"))
            & pl.col("interaction_dt").is_not_null()
            & (pl.col("interaction_dt") >= pl.col("created_dt"))
            & (pl.col("closed_dt").is_null() | (pl.col("interaction_dt") <= pl.col("closed_dt")))
            & (pl.col("interaction_dt") <= pl.lit(INTERACTION_CUTOFF))
        )
        .sort(["pr_id", "interaction_dt", "source"])
        .unique("pr_id", keep="first", maintain_order=True)
        .with_columns(
            ((pl.col("interaction_dt") - pl.col("created_dt")).dt.total_seconds() / 3600).alias("hours_since_open"),
            pl.col("interaction_dt").dt.strftime("%Y-%m").alias("month"),
        )
        .collect()
    )


def add_text_flags(frame: pd.DataFrame) -> pd.DataFrame:
    body = frame["trigger_body"].fillna("").astype(str)
    lower = body.str.lower()
    patterns = {
        "asks_action": r"\b(?:please|should|need(?:s)? to|must|fix|change|update|add|remove|replace|consider|ensure|avoid|rename|move)\b",
        "mentions_defect": r"\b(?:bug|error|fail(?:s|ed|ure)?|incorrect|broken|security|vulnerab|race condition|null pointer|exception)\b",
        "mentions_test": r"\b(?:test|tests|testing|coverage|assert|spec)\b",
        "mentions_location": r"\b(?:line|file|function|method|class|module|path)\b|`[^`]+`",
        "has_question": r"\?",
        "has_code": r"```|`[^`]+`",
        "has_suggestion_patch": r"```suggestion|start suggestion|suggested change",
        "has_severity_cue": r"\b(?:critical|high severity|medium severity|low severity|blocker|p[0-3])\b",
    }
    frame = frame.copy()
    frame["char_count"] = body.str.len().clip(upper=5000)
    frame["word_count"] = body.str.findall(r"\b\w+\b").str.len().clip(upper=1000)
    for name, pattern in patterns.items():
        frame[name] = lower.str.contains(pattern, regex=True).astype(int)
    frame["is_inline"] = (frame["source"] == "inline_review_comment").astype(int)
    frame["has_diff_context"] = frame["diff_hunk"].fillna("").astype(str).str.len().gt(0).astype(int)
    frame["trigger_body"] = body.str.replace(r"https?://\S+", " URL ", regex=True).str.slice(0, 4000)
    return frame


def build_model_frame() -> pd.DataFrame:
    triggers = feedback_with_text(DATA).rename({"interaction_dt": "trigger_dt"})
    chains = build_cross_feedback_response_chains(DATA).collect().select(
        "pr_id", "merged_within_response_window"
    )
    events = (
        build_cross_feedback_response_events(DATA).collect()
        .filter(pl.col("hours_after_trigger") <= 48)
        .with_columns(
            (pl.col("response_user_type").str.to_lowercase() == "user").fill_null(False).alias("is_human"),
            (pl.col("response_agent") == pl.col("author_agent")).fill_null(False).alias("is_author_agent"),
            (pl.col("response_agent") == pl.col("trigger_reviewer_agent")).fill_null(False).alias("is_reviewer_repeat"),
            (pl.col("response_source") == "force_push").alias("is_force_push"),
        )
        .group_by("pr_id")
        .agg(
            pl.col("is_human").any().alias("human_mediation_48h"),
            pl.col("is_author_agent").any().alias("author_agent_response_48h"),
            pl.col("is_reviewer_repeat").any().alias("reviewer_continuation_48h"),
            pl.col("is_force_push").any().alias("force_push_48h"),
        )
    )
    complete = (
        triggers.filter(pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - pd.Timedelta(days=7)))
        .join(chains, on="pr_id", how="inner")
        .join(events, on="pr_id", how="left")
        .with_columns(
            pl.col("human_mediation_48h").fill_null(False),
            pl.col("author_agent_response_48h").fill_null(False),
            pl.col("reviewer_continuation_48h").fill_null(False),
            pl.col("force_push_48h").fill_null(False),
        )
    )
    return add_text_flags(complete.to_pandas())


def make_pipeline(include_text: bool) -> Pipeline:
    numeric = [
        "hours_since_open", "char_count", "word_count", "asks_action",
        "mentions_defect", "mentions_test", "mentions_location", "has_question",
        "has_code", "has_suggestion_patch", "has_severity_cue", "is_inline",
        "has_diff_context",
    ]
    categorical = ["author_agent", "reviewer_agent", "source", "state", "month"]
    transforms = [
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5), categorical),
    ]
    if include_text:
        transforms.append(("text", TfidfVectorizer(min_df=5, max_df=0.98, max_features=4000, ngram_range=(1, 2), sublinear_tf=True), "trigger_body"))
    return Pipeline([
        ("features", ColumnTransformer(transforms, sparse_threshold=0.2)),
        ("model", LogisticRegression(max_iter=1500, class_weight="balanced", C=1.0)),
    ])


def evaluate(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = [
        "human_mediation_48h", "author_agent_response_48h",
        "reviewer_continuation_48h", "force_push_48h",
    ]
    folds = GroupKFold(n_splits=5)
    rows: list[dict] = []
    terms: list[dict] = []
    for target in targets:
        y = frame[target].astype(int).to_numpy()
        for variant, include_text in [("metadata_flags", False), ("metadata_flags_text", True)]:
            pred = np.full(len(frame), np.nan)
            for train, test in folds.split(frame, y, groups=frame["repo_id"]):
                pipe = make_pipeline(include_text)
                pipe.fit(frame.iloc[train], y[train])
                pred[test] = pipe.predict_proba(frame.iloc[test])[:, 1]
            rows.append({
                "target": target, "model": variant, "n": len(frame),
                "positive_rate": float(y.mean()), "roc_auc": roc_auc_score(y, pred),
                "average_precision": average_precision_score(y, pred),
                "brier": brier_score_loss(y, pred), "cv": "5-fold repository-grouped",
            })
        pipe = make_pipeline(True).fit(frame, y)
        names = pipe.named_steps["features"].get_feature_names_out()
        coef = pipe.named_steps["model"].coef_[0]
        for i in np.argsort(np.abs(coef))[-30:][::-1]:
            terms.append({"target": target, "feature": names[i], "coefficient": float(coef[i])})
    return pd.DataFrame(rows), pd.DataFrame(terms)


def feature_rates(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feature in ["asks_action", "mentions_defect", "mentions_test", "mentions_location", "has_question", "has_code", "has_suggestion_patch", "has_severity_cue", "is_inline"]:
        for value, group in frame.groupby(feature):
            rows.append({
                "feature": feature, "value": int(value), "n": len(group),
                "human_mediation_48h": group["human_mediation_48h"].mean(),
                "author_agent_response_48h": group["author_agent_response_48h"].mean(),
                "reviewer_continuation_48h": group["reviewer_continuation_48h"].mean(),
                "force_push_48h": group["force_push_48h"].mean(),
            })
    return pd.DataFrame(rows)


def exact_stratum_matches(frame: pd.DataFrame) -> pd.DataFrame:
    """Match feature-present/absent triggers inside repo/pair/channel/month strata."""
    work = frame.copy()
    work["match_score"] = np.log1p(work["char_count"]) + 0.25 * np.log1p(
        work["hours_since_open"].clip(lower=0)
    )
    strata = ["repo_id", "author_agent", "reviewer_agent", "source", "month"]
    targets = [
        "human_mediation_48h", "author_agent_response_48h",
        "reviewer_continuation_48h", "force_push_48h",
    ]
    rows: list[dict] = []
    for exposure in ["has_question", "asks_action", "has_code", "has_suggestion_patch", "has_severity_cue"]:
        pairs: list[tuple[int, int]] = []
        for _, group in work.groupby(strata, dropna=False, sort=False):
            treated = group[group[exposure] == 1].sort_values("match_score")
            controls = group[group[exposure] == 0]
            available = sorted(
                (float(score), int(index))
                for index, score in controls["match_score"].items()
            )
            for treated_index, score in treated["match_score"].items():
                if not available:
                    break
                position = bisect.bisect_left(available, (float(score), -1))
                candidates = ([position] if position < len(available) else []) + (
                    [position - 1] if position else []
                )
                chosen = min(candidates, key=lambda i: abs(available[i][0] - score))
                _, control_index = available.pop(chosen)
                pairs.append((int(treated_index), control_index))
        for target in targets:
            differences = np.array(
                [float(work.at[a, target]) - float(work.at[b, target]) for a, b in pairs]
            )
            standard_error = differences.std(ddof=1) / np.sqrt(len(differences))
            rows.append({
                "exposure": exposure, "target": target, "pairs": len(pairs),
                "repositories": work.loc[[a for a, _ in pairs], "repo_id"].nunique(),
                "paired_difference": differences.mean(),
                "ci_low": differences.mean() - 1.96 * standard_error,
                "ci_high": differences.mean() + 1.96 * standard_error,
                "matching": "exact repo-author-reviewer-source-month; nearest log length and trigger age",
            })
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = build_model_frame()
    metrics, coefficients = evaluate(frame)
    rates = feature_rates(frame)
    matched = exact_stratum_matches(frame)
    safe_columns = [
        c for c in frame.columns
        if c not in {
            "trigger_body", "diff_hunk", "path", "repo_url", "user",
            "author_user", "event_id", "review_id",
        }
    ]
    frame[safe_columns].to_parquet(OUT / "feedback_routing_features.parquet", index=False)
    metrics.to_csv(OUT / "model_metrics.csv", index=False)
    coefficients.to_csv(OUT / "model_coefficients.csv", index=False)
    rates.to_csv(OUT / "feature_rates.csv", index=False)
    matched.to_csv(OUT / "exact_stratum_feature_matches.csv", index=False)
    manifest = {
        "schema_version": "feedback-routing-v1",
        "rows": len(frame),
        "unique_prs": int(frame["pr_id"].nunique()),
        "unique_repositories": int(frame["repo_id"].nunique()),
        "raw_text_exported": False,
        "identity_policy": "exact aliases only",
        "alias_count": len(AGENT_ACCOUNT_ALIASES),
        "followup": "complete seven-day observation; outcomes measured in first 48 hours",
        "model_validation": "five-fold repository-grouped cross-validation",
        "claim_scope": "predictive association, not causal effect",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(metrics.to_string(index=False))
    print("\n", rates.to_string(index=False))
    print("\n", matched.to_string(index=False))


if __name__ == "__main__":
    main()
