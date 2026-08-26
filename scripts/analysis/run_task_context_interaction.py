"""RQ4: does pre-existing task context change who answers across the boundary?

A pull request body often references an issue. That reference is written before
any review happens, so it is a pre-trigger property of the change, and it gives
a reader context the diff alone does not.

This script asks whether that context changes the chance that an inline review
point gets answered, and whether the answer differs when the reviewer is a
different product from the author.

Two measurement decisions matter and are enforced here rather than assumed.

First, the outcome is rebuilt from the raw inline-comment table for BOTH arms.
The frozen response-event product holds cross-product triggers only, so using it
would give the same-product arm a structurally empty outcome.

Second, GitHub sets an inline comment's reply target to the FIRST comment of its
thread. A trigger that sits mid-thread therefore cannot receive an edge at all.
Same-product triggers sit mid-thread far more often than cross-product ones, so
the primary population is restricted to thread-root triggers, where the exposure
is possible on both sides. The unrestricted version is reported beside it.

Nothing here identifies a causal effect.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "task_context_interaction"

RESPONSE_WINDOW_HOURS = 48
EXPECTED_INLINE_TRIGGERS = 20_241
BOOTSTRAP_DRAWS = 1_000
SEED = 20260826


def load_frame() -> tuple[pd.DataFrame, dict[str, object]]:
    cohort = (
        pl.read_parquet(CHAIN / "first_agent_feedback_cohort.parquet")
        .filter(pl.col("trigger_source") == "inline_review_comment")
        .select(
            "pr_id",
            "repo_id",
            "trigger_dt",
            "trigger_event_id",
            "author_agent",
            "trigger_reviewer_agent",
            "feedback_relation",
        )
        .with_columns(pl.col("trigger_dt").dt.strftime("%Y-%m").alias("trigger_month"))
        .unique("pr_id")
    )
    if cohort.height != EXPECTED_INLINE_TRIGGERS:
        raise AssertionError(f"Inline trigger drift: {cohort.height}")

    inline = pl.read_parquet(
        DATA / "pr_review_comments.parquet",
        columns=["id", "in_reply_to_id", "created_at"],
    ).with_columns(
        pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
        pl.col("created_at")
        .str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
        .alias("reply_dt"),
    )

    replies = inline.filter(pl.col("in_reply_to_id").is_not_null())
    if replies.join(
        inline.filter(pl.col("in_reply_to_id").is_not_null()).select(
            pl.col("id").alias("in_reply_to_id")
        ),
        on="in_reply_to_id",
        how="semi",
    ).height:
        raise AssertionError(
            "A reply target is itself a reply; the thread-root assumption is broken."
        )

    root_flag = inline.select(
        pl.col("id").alias("trigger_event_id"),
        pl.col("in_reply_to_id").is_null().alias("trigger_is_root"),
    )
    edge = (
        cohort.select("pr_id", "trigger_event_id", "trigger_dt")
        .join(
            replies.select(
                pl.col("in_reply_to_id").alias("trigger_event_id"), "reply_dt"
            ),
            on="trigger_event_id",
            how="inner",
        )
        .filter(
            (pl.col("reply_dt") > pl.col("trigger_dt"))
            & (
                (pl.col("reply_dt") - pl.col("trigger_dt")).dt.total_seconds()
                <= RESPONSE_WINDOW_HOURS * 3600
            )
        )
        .select("pr_id")
        .unique()
        .with_columns(pl.lit(1).alias("edge"))
    )

    link = (
        pl.read_parquet(DATA / "related_issue.parquet")
        .filter(pl.col("source") == "body")
        .select("pr_id")
        .unique()
        .with_columns(pl.lit(1).alias("body_issue_link"))
    )

    frame = (
        cohort.join(root_flag, on="trigger_event_id", how="left")
        .join(link, on="pr_id", how="left")
        .join(edge, on="pr_id", how="left")
        .with_columns(
            pl.col("body_issue_link").fill_null(0),
            pl.col("edge").fill_null(0),
            pl.col("trigger_is_root").fill_null(True),
            (pl.col("feedback_relation") == "cross_product")
            .cast(pl.Int8)
            .alias("cross_product"),
        )
        .to_pandas()
    )

    checks = {
        "inline_trigger_prs": int(len(frame)),
        "repositories": int(frame["repo_id"].nunique()),
        "reply_graph_is_depth_one": True,
        "mid_thread_share_cross": float(
            1 - frame.loc[frame.cross_product == 1, "trigger_is_root"].mean()
        ),
        "mid_thread_share_same": float(
            1 - frame.loc[frame.cross_product == 0, "trigger_is_root"].mean()
        ),
        "outcome_rule": (
            "a later inline comment whose reply target is the trigger comment, "
            f"strictly after it and within {RESPONSE_WINDOW_HOURS} hours"
        ),
        "exposure_rule": "the PR body references an issue (related_issue source=body)",
    }
    return frame, checks


def cell_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cross in (0, 1):
        for link in (0, 1):
            cell = frame[
                (frame.cross_product == cross) & (frame.body_issue_link == link)
            ]
            rows.append(
                {
                    "reviewer_relation": "cross_product" if cross else "same_product",
                    "body_issue_link": bool(link),
                    "prs": int(len(cell)),
                    "repositories": int(cell["repo_id"].nunique()),
                    "answered": int(cell["edge"].sum()),
                    "answered_rate": float(cell["edge"].mean()),
                }
            )
    return pd.DataFrame(rows)


def absorbed_interaction(
    frame: pd.DataFrame, factors: tuple[str, ...]
) -> dict[str, float]:
    """Two-way-absorbed linear probability model, clustered on repository."""
    work = frame.copy()
    work["interaction"] = work["cross_product"] * work["body_issue_link"]
    columns = ["cross_product", "body_issue_link", "interaction", "edge"]
    passes = 30 if len(factors) > 1 else 1
    for _ in range(passes):
        for factor in factors:
            work[columns] = work[columns] - work.groupby(factor)[columns].transform(
                "mean"
            )
    design = work[["cross_product", "body_issue_link", "interaction"]].to_numpy()
    outcome = work["edge"].to_numpy()
    inverse = np.linalg.pinv(design.T @ design)
    beta = inverse @ (design.T @ outcome)
    residual = outcome - design @ beta

    codes = pd.factorize(frame["repo_id"])[0]
    meat = np.zeros((design.shape[1], design.shape[1]))
    for group in np.unique(codes):
        mask = codes == group
        score = design[mask].T @ residual[mask]
        meat += np.outer(score, score)
    clusters = len(np.unique(codes))
    n, k = design.shape
    scale = (clusters / (clusters - 1)) * ((n - 1) / (n - k))
    vcov = inverse @ meat @ inverse * scale
    error = float(np.sqrt(np.diag(vcov))[2])
    estimate = float(beta[2])
    return {
        "estimate": estimate,
        "standard_error": error,
        "ci_low": estimate - 1.96 * error,
        "ci_high": estimate + 1.96 * error,
        "n_prs": int(n),
        "repositories": int(clusters),
    }


def model_table(frame: pd.DataFrame, roots: pd.DataFrame) -> pd.DataFrame:
    specifications = [
        ("Thread-root triggers, repository FE", roots, ("repo_id",)),
        ("Thread-root triggers, repository and month FE", roots, ("repo_id", "trigger_month")),
        ("All inline triggers, repository FE", frame, ("repo_id",)),
        ("All inline triggers, repository and month FE", frame, ("repo_id", "trigger_month")),
    ]
    rows = []
    for label, data, factors in specifications:
        result = absorbed_interaction(data, factors)
        result["specification"] = label
        result["population"] = (
            "thread-root triggers" if data is roots else "all inline triggers"
        )
        result["interpretation"] = (
            "difference-in-differences on the probability that the review point is "
            "answered; observational, not a causal effect"
        )
        rows.append(result)
    return pd.DataFrame(rows)


def leave_one_out(roots: pd.DataFrame) -> pd.DataFrame:
    rows = []
    exposed = roots[(roots.cross_product == 1) & (roots.body_issue_link == 1)]
    for repo in sorted(exposed["repo_id"].value_counts().head(15).index):
        subset = roots[roots.repo_id != repo]
        result = absorbed_interaction(subset, ("repo_id", "trigger_month"))
        rows.append(
            {
                "excluded_repository_rank": int(
                    list(exposed["repo_id"].value_counts().index).index(repo) + 1
                ),
                "excluded_exposed_prs": int((exposed.repo_id == repo).sum()),
                "estimate": result["estimate"],
                "ci_low": result["ci_low"],
                "ci_high": result["ci_high"],
            }
        )
    frame = pd.DataFrame(rows).sort_values("excluded_repository_rank")
    return frame


def label_shuffle(roots: pd.DataFrame, draws: int = BOOTSTRAP_DRAWS) -> dict[str, float]:
    """Permute the link label inside each repository and refit.

    The permutation is within repository, so the companion model absorbs the
    repository factor only. That keeps the refit to one exact demeaning pass and
    makes the test affordable at this many draws.
    """
    observed = absorbed_interaction(roots, ("repo_id",))["estimate"]
    generator = np.random.default_rng(SEED)
    work = roots.copy()
    codes = pd.factorize(work["repo_id"])[0]
    blocks = [
        block
        for block in (np.flatnonzero(codes == g) for g in np.unique(codes))
        if len(block) > 1
    ]
    values = work["body_issue_link"].to_numpy().copy()
    eligible = [b for b in blocks if 0 < values[b].sum() < len(b)]
    draws_out = np.empty(draws)
    for index in range(draws):
        permuted = values.copy()
        for block in eligible:
            permuted[block] = generator.permutation(values[block])
        work["body_issue_link"] = permuted
        draws_out[index] = absorbed_interaction(work, ("repo_id",))["estimate"]
    centred = draws_out - draws_out.mean()
    p_value = float(
        (1 + np.sum(np.abs(centred) >= abs(observed - draws_out.mean()) - 1e-12))
        / (draws + 1)
    )
    return {
        "observed_estimate": float(observed),
        "draws": draws,
        "seed": SEED,
        "null_mean": float(draws_out.mean()),
        "null_sd": float(draws_out.std(ddof=1)),
        "absorbed": "repository fixed effects only",
        "p_value_two_sided": p_value,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame, checks = load_frame()
    roots = frame[frame.trigger_is_root].copy()

    cells_all = cell_table(frame).assign(population="all inline triggers")
    cells_root = cell_table(roots).assign(population="thread-root triggers")
    cells = pd.concat([cells_root, cells_all], ignore_index=True)

    models = model_table(frame, roots)
    loo = leave_one_out(roots)
    shuffle = label_shuffle(roots)

    cells.to_csv(OUTPUT / "answer_rate_cells.csv", index=False)
    models.to_csv(OUTPUT / "interaction_models.csv", index=False)
    loo.to_csv(OUTPUT / "leave_one_repository_out.csv", index=False)
    pd.DataFrame([shuffle]).to_csv(OUTPUT / "label_shuffle_test.csv", index=False)

    primary = models[
        models.specification == "Thread-root triggers, repository and month FE"
    ].iloc[0]
    summary = {
        **checks,
        "primary": {
            "specification": primary["specification"],
            "estimate": float(primary["estimate"]),
            "ci_low": float(primary["ci_low"]),
            "ci_high": float(primary["ci_high"]),
            "n_prs": int(primary["n_prs"]),
            "repositories": int(primary["repositories"]),
        },
        "label_shuffle": shuffle,
        "leave_one_repository_out_range": [
            float(loo["estimate"].min()),
            float(loo["estimate"].max()),
        ],
        "scope": "observational interaction; no causal claim",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print()
    print(cells[cells.population == "thread-root triggers"].to_string(index=False))
    print()
    print(models[["specification", "estimate", "ci_low", "ci_high", "n_prs"]].to_string(index=False))


if __name__ == "__main__":
    main()
