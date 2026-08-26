"""Title-based task-continuity exploration for sequential PR episodes."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import roc_auc_score


ISSUE_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_])#(\d+)"),
    re.compile(r"github\.com/[^/]+/[^/]+/issues/(\d+)", re.IGNORECASE),
]
AGENT_TEMPLATE = re.compile(
    r"\b(?:openai[ _-]?codex|codex|claude[ _-]?code|claude|copilot|cursor|google[ _-]?jules|jules|devin)\b",
    re.IGNORECASE,
)
LEADING_TAG = re.compile(
    r"^\s*(?:\[[^\]]{1,30}\]\s*)?(?:(?:feat|fix|chore|docs|test|refactor|style|build|ci|perf)(?:\([^)]*\))?[!:]\s*)+",
    re.IGNORECASE,
)
TOKEN = re.compile(r"[a-z0-9][a-z0-9_.+/-]*")


def normalize_title(value: str) -> str:
    text = html.unescape(value or "").lower()
    text = LEADING_TAG.sub("", text)
    text = AGENT_TEMPLATE.sub(" agent ", text)
    text = re.sub(r"https?://\S+", " url ", text)
    text = re.sub(r"\b[0-9a-f]{8,40}\b", " sha ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def issue_refs(value: str) -> set[str]:
    refs: set[str] = set()
    for pattern in ISSUE_PATTERNS:
        refs.update(pattern.findall(value or ""))
    return refs


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(TOKEN.findall(left))
    right_tokens = set(TOKEN.findall(right))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def load_episode_titles(transitions_path: Path, all_pr_path: Path) -> pd.DataFrame:
    episodes = pl.read_parquet(
        transitions_path,
        columns=[
            "id",
            "prior_id",
            "repo_url",
            "agent",
            "prior_agent",
            "same_user",
            "switched",
            "merged",
            "prior_merged",
            "gap_hours",
            "calendar_month",
        ],
    ).filter(~pl.col("prior_merged"))
    relevant_ids = pl.concat(
        [episodes.select("id"), episodes.select(pl.col("prior_id").alias("id"))]
    ).unique()
    titles = (
        pl.scan_parquet(all_pr_path)
        .select("id", "title", "html_url")
        .join(relevant_ids.lazy(), on="id", how="inner")
        .collect(engine="streaming")
    )
    data = (
        episodes.join(
            titles.rename({"title": "current_title", "html_url": "current_url"}),
            on="id",
            how="left",
        )
        .join(
            titles.rename(
                {"id": "prior_id", "title": "prior_title", "html_url": "prior_url"}
            ),
            on="prior_id",
            how="left",
        )
        .drop("prior_merged")
        .to_pandas()
    )
    return data


def score_title_pairs(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["current_title_norm"] = frame["current_title"].fillna("").map(normalize_title)
    frame["prior_title_norm"] = frame["prior_title"].fillna("").map(normalize_title)
    documents = pd.concat(
        [frame["current_title_norm"], frame["prior_title_norm"]], ignore_index=True
    )
    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=2,
        max_features=120_000,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    word_matrix = word_vectorizer.fit_transform(documents)
    n = len(frame)
    frame["title_word_cosine"] = np.asarray(
        word_matrix[:n].multiply(word_matrix[n:]).sum(axis=1)
    ).ravel()
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=3,
        max_features=120_000,
        sublinear_tf=True,
    )
    char_matrix = char_vectorizer.fit_transform(documents)
    frame["title_char_cosine"] = np.asarray(
        char_matrix[:n].multiply(char_matrix[n:]).sum(axis=1)
    ).ravel()
    frame["title_token_jaccard"] = [
        token_jaccard(left, right)
        for left, right in zip(
            frame["current_title_norm"], frame["prior_title_norm"], strict=True
        )
    ]
    frame["same_issue_ref"] = [
        bool(issue_refs(left) & issue_refs(right))
        for left, right in zip(frame["current_title"], frame["prior_title"], strict=True)
    ]
    frame["same_normalized_title"] = (
        (frame["current_title_norm"].str.len() >= 8)
        & (frame["current_title_norm"] == frame["prior_title_norm"])
    )
    frame["title_similarity"] = (
        0.7 * frame["title_word_cosine"] + 0.3 * frame["title_char_cosine"]
    )
    return frame


def add_transition_type(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["transition_type"] = np.select(
        [
            result["same_user"] & ~result["switched"],
            result["same_user"] & result["switched"],
            ~result["same_user"] & ~result["switched"],
        ],
        [
            "persistence",
            "brand_change_same_contributor",
            "contributor_change_stable_agent",
        ],
        default="joint_reconfiguration",
    )
    return result


def calibrate_against_files(frame: pd.DataFrame, handoff_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    file_data = pl.read_parquet(
        handoff_path,
        columns=["id", "both_file_observed", "same_file", "file_jaccard"],
    ).to_pandas()
    joined = frame.merge(file_data, on="id", how="left", validate="one_to_one")
    observed = joined.loc[joined["both_file_observed"].fillna(False)].copy()
    rows: list[dict[str, Any]] = []
    for threshold in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        selected = observed["title_similarity"] >= threshold
        rows.append(
            {
                "threshold": threshold,
                "selected_n": int(selected.sum()),
                "selected_share": float(selected.mean()),
                "shared_file_precision": float(observed.loc[selected, "same_file"].mean()) if selected.any() else np.nan,
                "shared_file_recall": float(observed.loc[selected, "same_file"].sum() / observed["same_file"].sum()),
            }
        )
    validation = pd.DataFrame(rows)
    validation["roc_auc_for_any_shared_file"] = roc_auc_score(
        observed["same_file"].astype(int), observed["title_similarity"]
    )
    quantiles = pd.qcut(
        observed["title_similarity"].rank(method="first"),
        10,
        labels=[f"D{i}" for i in range(1, 11)],
    )
    deciles = (
        observed.assign(similarity_decile=quantiles)
        .groupby("similarity_decile", observed=True)
        .agg(
            n=("id", "size"),
            min_similarity=("title_similarity", "min"),
            median_similarity=("title_similarity", "median"),
            max_similarity=("title_similarity", "max"),
            shared_file_rate=("same_file", "mean"),
            median_file_jaccard=("file_jaccard", "median"),
        )
        .reset_index()
    )
    return validation, deciles


def choose_candidate_rule(frame: pd.DataFrame, validation: pd.DataFrame) -> pd.DataFrame:
    """Apply a conservative, auditable rule; sensitivity remains primary."""
    result = frame.copy()
    eligible = validation.loc[
        (validation["selected_n"] >= 200)
        & (validation["shared_file_precision"] >= 0.45)
    ]
    threshold = float(eligible.iloc[0]["threshold"]) if not eligible.empty else 0.7
    result["candidate_threshold"] = threshold
    result["continuation_candidate"] = (
        result["same_issue_ref"]
        | result["same_normalized_title"]
        | (result["title_similarity"] >= threshold)
    )
    return result


def candidate_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["transition_type", "continuation_candidate"], dropna=False)
        .agg(
            n=("id", "size"),
            repositories=("repo_url", "nunique"),
            merge_rate_30d=("merged", "mean"),
            median_similarity=("title_similarity", "median"),
            median_gap_hours=("gap_hours", "median"),
        )
        .reset_index()
    )


def outcome_sensitivity(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for threshold in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        high = frame.loc[
            frame["same_issue_ref"]
            | frame["same_normalized_title"]
            | (frame["title_similarity"] >= threshold)
        ]
        for transition_type, cell in high.groupby("transition_type"):
            rows.append(
                {
                    "threshold": threshold,
                    "transition_type": transition_type,
                    "n": len(cell),
                    "repositories": cell["repo_url"].nunique(),
                    "merge_rate_30d": cell["merged"].mean(),
                    "median_similarity": cell["title_similarity"].median(),
                }
            )
    return pd.DataFrame(rows)


def stratified_audit_sample(frame: pd.DataFrame, per_stratum: int = 20) -> pd.DataFrame:
    bins = pd.cut(
        frame["title_similarity"],
        bins=[-0.001, 0.1, 0.4, 0.7, 1.001],
        labels=["very_low", "low", "medium", "high"],
    )
    audit = frame.assign(audit_stratum=bins)
    pieces = []
    for (_, _), cell in audit.groupby(["audit_stratum", "switched"], observed=True):
        pieces.append(cell.sample(min(per_stratum, len(cell)), random_state=20260825))
    columns = [
        "id",
        "prior_id",
        "repo_url",
        "agent",
        "prior_agent",
        "same_user",
        "switched",
        "merged",
        "audit_stratum",
        "title_similarity",
        "title_word_cosine",
        "title_char_cosine",
        "same_issue_ref",
        "prior_title",
        "current_title",
        "prior_url",
        "current_url",
    ]
    result = pd.concat(pieces, ignore_index=True)[columns]
    result["manual_same_task"] = ""
    result["manual_confidence"] = ""
    result["manual_note"] = ""
    return result


def run(
    transitions_path: Path,
    all_pr_path: Path,
    handoff_path: Path,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("[1/6] Loading titles for closed-unmerged transition episodes")
    data = load_episode_titles(transitions_path, all_pr_path)
    print(f"  {len(data):,} episodes; current/prior title coverage {data['current_title'].notna().mean():.1%}/{data['prior_title'].notna().mean():.1%}")
    print("[2/6] Computing aligned word and character TF-IDF similarity")
    data = add_transition_type(score_title_pairs(data))
    print("[3/6] Calibrating title similarity against observed file overlap")
    validation, deciles = calibrate_against_files(data, handoff_path)
    data = choose_candidate_rule(data, validation)
    print("[4/6] Summarizing candidate continuation and outcomes")
    summary = candidate_summary(data)
    sensitivity = outcome_sensitivity(data)
    print("[5/6] Saving an audit-ready episode ledger and stratified sample")
    audit = stratified_audit_sample(data)
    selected_columns = [
        "id",
        "prior_id",
        "repo_url",
        "agent",
        "prior_agent",
        "same_user",
        "switched",
        "merged",
        "gap_hours",
        "calendar_month",
        "transition_type",
        "title_similarity",
        "title_word_cosine",
        "title_char_cosine",
        "title_token_jaccard",
        "same_issue_ref",
        "same_normalized_title",
        "candidate_threshold",
        "continuation_candidate",
        "prior_title",
        "current_title",
        "prior_url",
        "current_url",
    ]
    pl.from_pandas(data[selected_columns]).write_parquet(
        output_dir / "task_continuity_episodes.parquet", compression="zstd"
    )
    validation.to_csv(output_dir / "task_continuity_file_validation.csv", index=False)
    deciles.to_csv(output_dir / "task_continuity_file_deciles.csv", index=False)
    summary.to_csv(output_dir / "task_continuity_summary.csv", index=False)
    sensitivity.to_csv(output_dir / "task_continuity_outcome_sensitivity.csv", index=False)
    audit.to_csv(output_dir / "task_continuity_manual_audit.csv", index=False)
    print("[6/6] Key outputs")
    print(validation.to_string(index=False))
    print("\nCandidate summary")
    print(summary.to_string(index=False))
