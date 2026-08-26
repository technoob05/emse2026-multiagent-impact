"""Measure task-continuity evidence for exact-file successor pairs.

Exact-file reuse is a retrieval step, not proof of a handoff.  This module adds
text and issue-link evidence, reports conservative candidate tiers, and keeps
the broad successor-merge outcome separate from same-task recovery.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import roc_auc_score

from multiagent_impact.pipeline import BLUE, INK, ORANGE, add_figure_header, configure_plotting, save_figure
from multiagent_impact.task_continuity import issue_refs, normalize_title, score_title_pairs


GENERIC_TITLE = re.compile(
    r"^(?:update|fix|changes?|minor changes?|wip|test|tests|chore|cleanup|refactor|"
    r"documentation|docs|bump dependencies|dependency updates?)$",
    re.IGNORECASE,
)


def load_pairs(successor_path: Path, data_dir: Path) -> pd.DataFrame:
    pairs = pl.read_parquet(successor_path)
    relevant = pl.concat(
        [
            pairs.select(pl.col("failed_id").alias("id")),
            pairs.select(pl.col("successor_id").alias("id")),
        ]
    ).unique()
    prs = (
        pl.scan_parquet(data_dir / "pull_request.parquet")
        .select("id", "title", "body", "html_url")
        .join(relevant.lazy(), on="id", how="inner")
        .collect(engine="streaming")
    )
    prior = prs.rename(
        {
            "id": "failed_id",
            "title": "prior_title",
            "body": "prior_body",
            "html_url": "prior_url",
        }
    )
    current = prs.rename(
        {
            "id": "successor_id",
            "title": "current_title",
            "body": "current_body",
            "html_url": "current_url",
        }
    )
    return pairs.join(prior, on="failed_id", how="left").join(
        current, on="successor_id", how="left"
    ).to_pandas()


def structured_issue_sets(data_dir: Path, relevant_ids: set[int]) -> dict[int, set[int]]:
    if not (data_dir / "related_issue.parquet").exists():
        return {}
    refs = (
        pl.scan_parquet(data_dir / "related_issue.parquet")
        .filter(pl.col("pr_id").is_in(list(relevant_ids)))
        .select("pr_id", "issue_id")
        .unique()
        .collect(engine="streaming")
    )
    return {
        int(pr_id): {int(value) for value in issue_ids}
        for pr_id, issue_ids in refs.group_by("pr_id").agg("issue_id").iter_rows()
    }


def add_continuity_features(frame: pd.DataFrame, issue_map: dict[int, set[int]]) -> pd.DataFrame:
    data = score_title_pairs(frame)
    prior_text = (data["prior_title"].fillna("") + "\n" + data["prior_body"].fillna(""))
    current_text = (data["current_title"].fillna("") + "\n" + data["current_body"].fillna(""))
    data["same_text_issue_ref"] = [
        bool(issue_refs(left) & issue_refs(right))
        for left, right in zip(prior_text, current_text, strict=True)
    ]
    data["same_structured_issue"] = [
        bool(issue_map.get(int(left), set()) & issue_map.get(int(right), set()))
        for left, right in zip(data["failed_id"], data["successor_id"], strict=True)
    ]
    data["explicit_issue_evidence"] = data["same_text_issue_ref"] | data["same_structured_issue"]
    data["generic_prior_title"] = data["prior_title_norm"].fillna("").str.match(GENERIC_TITLE)
    data["generic_current_title"] = data["current_title_norm"].fillna("").str.match(GENERIC_TITLE)
    # These two thresholds are exploratory.  In the independent AI-assisted
    # pre-audit, 0.20 selected 6/9 consensus positives and 0/73 consensus
    # negatives; 0.10 selected 8/9 positives and 1/73 negatives.  A blinded
    # human audit is still required before calling either rule validated.
    data["strong_title_evidence"] = data["title_similarity"] >= 0.20
    data["strong_continuation_candidate"] = (
        data["explicit_issue_evidence"] | data["strong_title_evidence"]
    )
    data["possible_continuation_candidate"] = (
        data["strong_continuation_candidate"]
        | (data["title_similarity"] >= 0.10)
    )
    data["evidence_tier"] = np.select(
        [data["strong_continuation_candidate"], data["possible_continuation_candidate"]],
        ["strong candidate", "possible candidate"],
        default="path only",
    )
    return data


def count_temporal_successors(index_path: Path, data_dir: Path, days: int = 30) -> int:
    """Count eligible index PRs followed by any AIDev-pop PR in the repository."""
    index = pl.read_parquet(index_path).sort(["repo_id", "prior_closed_dt", "failed_id"])
    current = (
        pl.scan_parquet(data_dir / "pull_request.parquet")
        .select(
            "id",
            "repo_id",
            pl.col("created_at").str.to_datetime(strict=False, time_zone="UTC").alias("created_dt"),
        )
        .filter(pl.col("created_dt").is_not_null())
        .sort(["repo_id", "created_dt", "id"])
        .collect(engine="streaming")
    )
    matched = index.join_asof(
        current,
        left_on="prior_closed_dt",
        right_on="created_dt",
        by="repo_id",
        strategy="forward",
        allow_exact_matches=False,
        check_sortedness=False,
    ).with_columns(
        (
            (pl.col("created_dt") - pl.col("prior_closed_dt")).dt.total_seconds()
            / 86400.0
        ).alias("temporal_gap_days")
    )
    return matched.filter(pl.col("temporal_gap_days") <= days).height


def build_funnel(frame: pd.DataFrame, eligible_index_n: int, temporal_successor_n: int) -> pd.DataFrame:
    changed = frame["changed_agent"]
    same_user_change = changed & frame["same_contributor"]
    rows = [
        ("Eligible closed-unmerged PRs", eligible_index_n),
        ("Any later PR in 30 days", temporal_successor_n),
        ("Exact-file successor in 30 days", len(frame)),
        ("Possible continuation candidate", int(frame["possible_continuation_candidate"].sum())),
        ("Strong continuation candidate", int(frame["strong_continuation_candidate"].sum())),
        ("Strong candidate changes agent", int((frame["strong_continuation_candidate"] & changed).sum())),
        ("Strong candidate: same contributor, new agent", int((frame["strong_continuation_candidate"] & same_user_change).sum())),
    ]
    return pd.DataFrame(rows, columns=["stage", "n"]).assign(
        share_of_eligible=lambda x: x["n"] / eligible_index_n
    )


def build_composition(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["evidence_tier", "transition_mode"], observed=True)
        .agg(
            n=("failed_id", "size"),
            repositories=("repo_url", "nunique"),
            successor_merge_rate=("recovered_within_30d", "mean"),
            median_title_similarity=("title_similarity", "median"),
            median_days_to_successor=("days_to_successor", "median"),
        )
        .reset_index()
    )


def build_threshold_sensitivity(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for threshold in [0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
        selected = frame["explicit_issue_evidence"] | (frame["title_similarity"] >= threshold)
        cell = frame.loc[selected]
        rows.append(
            {
                "title_threshold": threshold,
                "candidate_n": len(cell),
                "candidate_share_of_exact_file": len(cell) / len(frame),
                "changed_agent_n": int(cell["changed_agent"].sum()),
                "same_contributor_changed_agent_n": int(
                    (cell["changed_agent"] & cell["same_contributor"]).sum()
                ),
                "repositories": cell["repo_url"].nunique(),
            }
        )
    return pd.DataFrame(rows)


def build_screen_diagnostic(frame: pd.DataFrame, audit_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare text scores with two independent AI screens, without calling them truth."""
    if not audit_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    audit = pd.read_csv(audit_path)
    joined = audit.merge(
        frame[["failed_id", "successor_id", "title_similarity", "explicit_issue_evidence"]],
        on=["failed_id", "successor_id"],
        how="inner",
        validate="one_to_one",
    )
    positive = joined["legacy_binary_yes"] & joined["novelty_binary_yes"]
    negative = (
        joined["likely_same_task_legacy"].eq("no")
        & joined["likely_same_task_novelty"].eq("no")
    )
    endpoint = joined.loc[positive | negative].copy()
    endpoint["consensus_yes"] = positive.loc[endpoint.index].astype(int)
    auc = roc_auc_score(endpoint["consensus_yes"], endpoint["title_similarity"])
    rows: list[dict[str, Any]] = []
    for threshold in [0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
        selected = endpoint["explicit_issue_evidence"] | (endpoint["title_similarity"] >= threshold)
        truth = endpoint["consensus_yes"].astype(bool)
        tp = int((selected & truth).sum())
        fp = int((selected & ~truth).sum())
        fn = int((~selected & truth).sum())
        rows.append(
            {
                "title_threshold": threshold,
                "endpoint_n": len(endpoint),
                "consensus_positive_n": int(truth.sum()),
                "selected_n": int(selected.sum()),
                "true_positive_n": tp,
                "false_positive_n": fp,
                "false_negative_n": fn,
                "screen_precision": tp / (tp + fp) if tp + fp else np.nan,
                "screen_recall": tp / (tp + fn) if tp + fn else np.nan,
                "title_score_auc": auc,
                "validation_status": "AI-assisted pre-audit; not human ground truth",
            }
        )
    return pd.DataFrame(rows), joined


def build_figure(funnel: pd.DataFrame, composition: pd.DataFrame, output_dir: Path) -> None:
    configure_plotting()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.9))
    stages = [
        "Eligible index PRs",
        "Any later PR",
        "Exact-file successor",
        "Possible continuation",
        "Strong continuation",
        "Strong + agent change",
        "Same person + new agent",
    ]
    values = funnel["n"].to_numpy()
    shares = 100 * funnel["share_of_eligible"].to_numpy()
    positions = np.arange(len(values))[::-1]
    colors = [INK, "#566573", BLUE, "#74A9CF", ORANGE, "#B35C44", "#7A3E65"]
    axes[0].barh(positions, values, color=colors)
    axes[0].set_xscale("log")
    axes[0].set_yticks(positions, stages)
    axes[0].set_xlabel("Count (log scale)")
    axes[0].set_title("A. Coordination evidence narrows quickly", loc="left", fontweight="bold")
    for position, value, share in zip(positions, values, shares, strict=True):
        share_label = "<0.1%" if 0 < share < 0.1 else f"{share:.1f}%"
        axes[0].text(value * 1.08, position, f"{value:,}  ({share_label})", ha="left", va="center", fontsize=8)
    axes[0].set_xlim(7, max(values) * 2.2)

    strong = composition.loc[composition["evidence_tier"] == "strong candidate"].set_index("transition_mode")
    total = int(strong["n"].sum())
    new_agent = int(strong.loc[
        ["same contributor / different agent", "different contributor / different agent"], "n"
    ].sum())
    same_agent = total - new_agent
    same_person_new_agent = int(strong.loc["same contributor / different agent", "n"])
    new_person_new_agent = int(strong.loc["different contributor / different agent", "n"])
    axes[1].axis("off")
    axes[1].set_title("B. A new agent is rare in the strong candidate set", loc="left", fontweight="bold")
    box = dict(boxstyle="round,pad=0.55", linewidth=1.3)
    axes[1].text(0.50, 0.83, f"Strong candidates\n{total:,}", ha="center", va="center", transform=axes[1].transAxes,
                 bbox={**box, "facecolor": "#F4F6F8", "edgecolor": INK}, fontsize=12, fontweight="bold")
    axes[1].annotate("", xy=(0.26, 0.57), xytext=(0.46, 0.75), xycoords="axes fraction", arrowprops=dict(arrowstyle="->", color=INK))
    axes[1].annotate("", xy=(0.74, 0.57), xytext=(0.54, 0.75), xycoords="axes fraction", arrowprops=dict(arrowstyle="->", color=INK))
    axes[1].text(0.24, 0.50, f"Same agent\n{same_agent:,}  ({same_agent/total:.1%})", ha="center", va="center", transform=axes[1].transAxes,
                 bbox={**box, "facecolor": "#EEF1F4", "edgecolor": INK}, fontsize=11)
    axes[1].text(0.76, 0.50, f"New agent\n{new_agent:,}  ({new_agent/total:.1%})", ha="center", va="center", transform=axes[1].transAxes,
                 bbox={**box, "facecolor": "#FCE9D7", "edgecolor": ORANGE}, fontsize=11, fontweight="bold")
    axes[1].annotate("", xy=(0.62, 0.25), xytext=(0.73, 0.42), xycoords="axes fraction", arrowprops=dict(arrowstyle="->", color=ORANGE))
    axes[1].annotate("", xy=(0.89, 0.25), xytext=(0.79, 0.42), xycoords="axes fraction", arrowprops=dict(arrowstyle="->", color=ORANGE))
    axes[1].text(0.58, 0.17, f"Same person\n{same_person_new_agent:,}  ({same_person_new_agent/new_agent:.1%})", ha="center", va="center", transform=axes[1].transAxes,
                 bbox={**box, "facecolor": "white", "edgecolor": ORANGE}, fontsize=10)
    axes[1].text(0.91, 0.17, f"New person\n{new_person_new_agent:,}  ({new_person_new_agent/new_agent:.1%})", ha="center", va="center", transform=axes[1].transAxes,
                 bbox={**box, "facecolor": "white", "edgecolor": "#7A3E65"}, fontsize=10)
    add_figure_header(
        fig,
        "From shared files to task-continuation evidence",
        "Title and issue evidence narrow exact-file pairs. Thresholds use an AI-assisted pre-audit and still need human validation.",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    save_figure(fig, output_dir / "direct_continuation_funnel")
    plt.close(fig)


def run(data_dir: Path, project_root: Path) -> None:
    cache_dir = project_root / "outputs" / "cache"
    table_dir = project_root / "outputs" / "tables"
    figure_dir = project_root / "outputs" / "figures"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    print("[1/5] Loading direct exact-file successor pairs and PR text")
    frame = load_pairs(cache_dir / "direct_handoff_successors.parquet", data_dir)
    relevant_ids = set(frame["failed_id"].astype(int)) | set(frame["successor_id"].astype(int))
    print(f"  {len(frame):,} pairs; {len(relevant_ids):,} unique PRs")
    print("[2/5] Adding issue-link and aligned title-similarity evidence")
    issues = structured_issue_sets(data_dir, relevant_ids)
    frame = add_continuity_features(frame, issues)
    index_path = cache_dir / "direct_handoff_index.parquet"
    eligible_n = pl.read_parquet(index_path).height
    temporal_n = count_temporal_successors(index_path, data_dir)
    print("[3/5] Building funnel, composition, and threshold sensitivity")
    funnel = build_funnel(frame, eligible_n, temporal_n)
    composition = build_composition(frame)
    sensitivity = build_threshold_sensitivity(frame)
    diagnostic, joined_audit = build_screen_diagnostic(
        frame, project_root / "tmp" / "manual_label_agreement_merged.csv"
    )
    print("[4/5] Saving reproducible outputs")
    keep = [
        "failed_id", "successor_id", "repo_url", "prior_agent", "current_agent",
        "same_contributor", "changed_agent", "transition_mode", "days_to_successor",
        "shared_files", "shared_non_generic_files", "example_shared_file",
        "recovered_within_30d", "prior_title", "current_title", "prior_url", "current_url",
        "title_similarity", "title_word_cosine", "title_char_cosine", "title_token_jaccard",
        "same_structured_issue", "same_text_issue_ref", "explicit_issue_evidence",
        "strong_title_evidence", "strong_continuation_candidate",
        "possible_continuation_candidate", "evidence_tier",
    ]
    pl.from_pandas(frame[keep]).write_parquet(cache_dir / "direct_continuity_candidates.parquet", compression="zstd")
    funnel.to_csv(table_dir / "direct_continuity_funnel.csv", index=False)
    composition.to_csv(table_dir / "direct_continuity_composition.csv", index=False)
    sensitivity.to_csv(table_dir / "direct_continuity_threshold_sensitivity.csv", index=False)
    if not diagnostic.empty:
        diagnostic.to_csv(table_dir / "direct_continuity_screen_diagnostic.csv", index=False)
        joined_audit.to_csv(project_root / "tmp" / "direct_continuity_screen_features.csv", index=False)
    build_figure(funnel, composition, figure_dir)
    print("[5/5] Main descriptive results")
    print(funnel.to_string(index=False))
    print("\nStrong-candidate composition")
    print(composition.loc[composition["evidence_tier"] == "strong candidate"].to_string(index=False))
    print("\nThreshold sensitivity")
    print(sensitivity.to_string(index=False))
    if not diagnostic.empty:
        print("\nAI-assisted screen diagnostic (not human ground truth)")
        print(diagnostic.to_string(index=False))
