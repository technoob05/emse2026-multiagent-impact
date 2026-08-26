"""Profile the two-layer AIDev dataset without loading large tables in memory.

The script reads Parquet metadata for the full inventory and scans only key
columns when it measures AIDev-pop join coverage.  It writes small CSV files
that are used by the dataset guide and the paper figures.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq


TABLE_INFO = {
    "all_pull_request": {
        "scope": "Full corpus",
        "grain": "One pull request",
        "primary_key": "id",
        "join_to_pr": "Backbone table",
        "role": "PR identity, agent, author, state, timestamps, and repository",
    },
    "all_repository": {
        "scope": "Full corpus",
        "grain": "One repository",
        "primary_key": "id",
        "join_to_pr": "all_pull_request.repo_id = id",
        "role": "Repository name, language, license, fork status, stars, and forks",
    },
    "all_user": {
        "scope": "Full corpus",
        "grain": "One GitHub user",
        "primary_key": "id",
        "join_to_pr": "all_pull_request.user_id = id",
        "role": "Contributor account age and follower/following counts",
    },
    "pull_request": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One pull request",
        "primary_key": "id",
        "join_to_pr": "Backbone table",
        "role": "PR backbone for the richer event and content tables",
    },
    "repository": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One repository",
        "primary_key": "id",
        "join_to_pr": "pull_request.repo_id = id",
        "role": "Repository context for the richer subset",
    },
    "pr_timeline": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One PR timeline event",
        "primary_key": "None supplied",
        "join_to_pr": "pr_id = pull_request.id",
        "role": "Review, assignment, label, closure, and other lifecycle events",
    },
    "pr_comments": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One issue-style PR comment",
        "primary_key": "id",
        "join_to_pr": "pr_id = pull_request.id",
        "role": "Conversation text, actor, actor type, and time",
    },
    "pr_reviews": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One submitted PR review",
        "primary_key": "id",
        "join_to_pr": "pr_id = pull_request.id",
        "role": "Review decision, reviewer type, text, and submission time",
    },
    "pr_review_comments": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One inline review comment",
        "primary_key": "id",
        "join_to_pr": "pull_request_review_id = pr_reviews.pull_request_review_id",
        "role": "Inline discussion tied to a file and diff position",
    },
    "pr_commits": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One commit attached to a PR",
        "primary_key": "sha + pr_id",
        "join_to_pr": "pr_id = pull_request.id",
        "role": "Commit author, committer, SHA, and message",
    },
    "pr_commit_details": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One changed file within a PR commit",
        "primary_key": "None supplied",
        "join_to_pr": "pr_id = pull_request.id; sha can link to pr_commits.sha",
        "role": "Change size, filename, file status, and patch text",
    },
    "pr_task_type": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One classified pull request",
        "primary_key": "id",
        "join_to_pr": "id = pull_request.id",
        "role": "Task type, model reason, and classification confidence",
    },
    "issue": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One linked issue",
        "primary_key": "id",
        "join_to_pr": "Via related_issue.issue_id",
        "role": "Issue title, body, author, state, and timestamps",
    },
    "related_issue": {
        "scope": "AIDev-pop (>100 stars)",
        "grain": "One PR-issue link",
        "primary_key": "pr_id + issue_id + source",
        "join_to_pr": "pr_id = pull_request.id; issue_id = issue.id",
        "role": "Bridge between PRs and issues, with link source",
    },
}


FEATURE_MEANINGS = {
    "id": "Dataset identifier",
    "number": "Number within a GitHub repository",
    "title": "Title text",
    "body": "Body text",
    "agent": "Observed coding-agent label",
    "user_id": "Contributor identifier",
    "user": "Contributor login",
    "user_type": "GitHub actor type",
    "state": "Observed state or review decision",
    "created_at": "Creation timestamp",
    "closed_at": "Closure timestamp",
    "merged_at": "Merge timestamp",
    "submitted_at": "Review submission timestamp",
    "updated_at": "Last update timestamp",
    "repo_id": "Repository identifier",
    "repo_url": "Repository API URL",
    "html_url": "Public GitHub URL",
    "url": "GitHub API URL",
    "license": "Detected repository license",
    "full_name": "Repository owner/name",
    "is_forked": "Whether the repository is a fork",
    "language": "Main repository language",
    "forks": "Fork count at data collection",
    "stars": "Star count at data collection",
    "login": "GitHub login",
    "followers": "Follower count",
    "following": "Following count",
    "pr_id": "Pull-request identifier",
    "event": "Timeline event type",
    "commit_id": "Commit identifier recorded in an event",
    "actor": "Actor login recorded in an event",
    "assignee": "Assigned login",
    "label": "GitHub label recorded in an event",
    "message": "Commit or event message",
    "pull_request_review_id": "Identifier shared by a review and its inline comments",
    "diff_hunk": "Diff context for an inline comment",
    "path": "Changed file path",
    "position": "Current inline diff position",
    "original_position": "Original inline diff position",
    "original_commit_id": "Original commit for an inline comment",
    "pull_request_url": "Pull-request API URL",
    "in_reply_to_id": "Parent inline-comment identifier",
    "sha": "Commit SHA",
    "author": "Commit author",
    "committer": "Commit committer",
    "commit_stats_total": "Total changed lines reported for a commit",
    "commit_stats_additions": "Added lines reported for a commit",
    "commit_stats_deletions": "Deleted lines reported for a commit",
    "filename": "Changed file name",
    "status": "File change status",
    "additions": "Lines added in a changed file",
    "deletions": "Lines deleted in a changed file",
    "changes": "Total line changes in a changed file",
    "patch": "Patch text",
    "reason": "Model-generated task classification reason",
    "type": "Predicted task type",
    "confidence": "Task classification confidence",
    "issue_id": "Issue identifier",
    "source": "How the PR-issue link was found",
}


COVERAGE_SPECS = {
    "pr_timeline": ("pr_id", "Timeline events"),
    "pr_comments": ("pr_id", "Conversation comments"),
    "pr_reviews": ("pr_id", "Submitted reviews"),
    "pr_commits": ("pr_id", "Commits"),
    "pr_commit_details": ("pr_id", "File-level changes"),
    "pr_task_type": ("id", "Task classification"),
    "related_issue": ("pr_id", "Linked issues"),
}


def human_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def read_unique_ints(path: Path, column: str) -> set[int]:
    values = pc.unique(pq.read_table(path, columns=[column])[column]).to_pylist()
    return {int(value) for value in values if value is not None}


def build_inventory(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    inventory_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []

    for table, info in TABLE_INFO.items():
        path = data_dir / f"{table}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        inventory_rows.append(
            {
                "table": table,
                "scope": info["scope"],
                "grain": info["grain"],
                "rows": parquet.metadata.num_rows,
                "columns": len(schema),
                "size_mb": round(human_size_mb(path), 1),
                "primary_key": info["primary_key"],
                "join_to_pr": info["join_to_pr"],
                "role": info["role"],
            }
        )
        for field in schema:
            join_role = ""
            if field.name in {"id", "pr_id", "repo_id", "user_id", "issue_id", "pull_request_review_id", "sha"}:
                join_role = "Identifier or join field"
            feature_rows.append(
                {
                    "table": table,
                    "feature": field.name,
                    "dtype": str(field.type),
                    "meaning": FEATURE_MEANINGS.get(field.name, field.name.replace("_", " ").capitalize()),
                    "join_role": join_role,
                }
            )

    return pd.DataFrame(inventory_rows), pd.DataFrame(feature_rows)


def build_join_coverage(data_dir: Path) -> pd.DataFrame:
    pr_ids = read_unique_ints(data_dir / "pull_request.parquet", "id")
    denominator = len(pr_ids)
    rows: list[dict[str, object]] = []

    for table, (column, feature_group) in COVERAGE_SPECS.items():
        parquet = pq.ParquetFile(data_dir / f"{table}.parquet")
        linked_ids = read_unique_ints(data_dir / f"{table}.parquet", column)
        matched = linked_ids & pr_ids
        orphan = linked_ids - pr_ids
        rows.append(
            {
                "table": table,
                "feature_group": feature_group,
                "event_rows": parquet.metadata.num_rows,
                "distinct_pr_ids": len(linked_ids),
                "matched_pr_ids": len(matched),
                "coverage_pct_of_aidev_pop": round(100 * len(matched) / denominator, 2),
                "orphan_pr_ids": len(orphan),
                "aidev_pop_prs": denominator,
            }
        )

    reviews = pq.read_table(
        data_dir / "pr_reviews.parquet", columns=["pull_request_review_id", "pr_id"]
    ).to_pandas()
    review_map = reviews.dropna().drop_duplicates("pull_request_review_id")
    inline_ids = read_unique_ints(
        data_dir / "pr_review_comments.parquet", "pull_request_review_id"
    )
    matched_reviews = review_map[review_map["pull_request_review_id"].isin(inline_ids)]
    inline_pr_ids = {int(value) for value in matched_reviews["pr_id"] if pd.notna(value)}
    inline_meta = pq.ParquetFile(data_dir / "pr_review_comments.parquet").metadata
    rows.append(
        {
            "table": "pr_review_comments",
            "feature_group": "Inline review comments",
            "event_rows": inline_meta.num_rows,
            "distinct_pr_ids": len(inline_pr_ids),
            "matched_pr_ids": len(inline_pr_ids & pr_ids),
            "coverage_pct_of_aidev_pop": round(100 * len(inline_pr_ids & pr_ids) / denominator, 2),
            "orphan_pr_ids": len(inline_pr_ids - pr_ids),
            "aidev_pop_prs": denominator,
        }
    )

    return pd.DataFrame(rows).sort_values(
        ["coverage_pct_of_aidev_pop", "event_rows"], ascending=[False, False]
    )


def build_full_join_quality(data_dir: Path) -> pd.DataFrame:
    pr_path = data_dir / "all_pull_request.parquet"
    rows: list[dict[str, object]] = []
    for relation, foreign_key, dimension_table in [
        ("PR to repository", "repo_id", "all_repository"),
        ("PR to contributor", "user_id", "all_user"),
    ]:
        foreign_column = pq.read_table(pr_path, columns=[foreign_key])[foreign_key]
        foreign_ids = {
            int(value) for value in pc.unique(foreign_column).to_pylist()
            if value is not None
        }
        dimension_ids = read_unique_ints(data_dir / f"{dimension_table}.parquet", "id")
        matched = foreign_ids & dimension_ids
        rows.append(
            {
                "relation": relation,
                "foreign_key": f"all_pull_request.{foreign_key}",
                "dimension_key": f"{dimension_table}.id",
                "pr_rows": len(foreign_column),
                "pr_rows_missing_key": foreign_column.null_count,
                "distinct_foreign_keys": len(foreign_ids),
                "matched_distinct_keys": len(matched),
                "match_pct": round(100 * len(matched) / len(foreign_ids), 3),
                "unmatched_distinct_keys": len(foreign_ids - dimension_ids),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(r"D:\PhD_LetGoo\PhD_Farming\Legacy\AI_Dev_Dataminning\AIDev-7.6M"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/tables"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventory, features = build_inventory(args.data_dir)
    coverage = build_join_coverage(args.data_dir)
    full_join_quality = build_full_join_quality(args.data_dir)
    inventory.to_csv(args.output_dir / "dataset_table_inventory.csv", index=False)
    features.to_csv(args.output_dir / "dataset_feature_dictionary.csv", index=False)
    coverage.to_csv(args.output_dir / "dataset_join_coverage.csv", index=False)
    full_join_quality.to_csv(args.output_dir / "dataset_full_join_quality.csv", index=False)
    print(inventory[["table", "scope", "rows", "columns"]].to_string(index=False))
    print("\nAIDev-pop PR coverage:")
    print(coverage[["feature_group", "matched_pr_ids", "coverage_pct_of_aidev_pop", "orphan_pr_ids"]].to_string(index=False))
    print("\nFull-corpus key coverage:")
    print(full_join_quality.to_string(index=False))


if __name__ == "__main__":
    main()
