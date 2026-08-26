from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import bootstrap, wilcoxon


PREFIX_PATTERN = re.compile(
    r"^\s*(?:\[[^\]]+\]\s*)?"
    r"(feat(?:ure)?|fix|bugfix|docs?|documentation|test|tests|refactor|"
    r"chore|build|ci|perf|style|revert)"
    r"(?:\([^)]+\))?!?\s*:\s*",
    flags=re.IGNORECASE,
)

PREFIX_NORMALIZATION = {
    "feature": "feat",
    "bugfix": "fix",
    "doc": "docs",
    "documentation": "docs",
    "tests": "test",
}


@dataclass(frozen=True)
class SpecializationConfig:
    data_dir: Path
    output_dir: Path
    pre_days: int = 90
    post_days: int = 90
    min_pre: int = 5
    min_post: int = 5
    min_entrant: int = 3
    permutations: int = 2_000
    seed: int = 20260825


def classify_title(title: object) -> str | None:
    """Return a high-precision task label from an explicit title prefix.

    We intentionally avoid guessing from loose verbs such as "improve".  The
    restricted rule is easy to reproduce and can be checked against the
    independently supplied task labels.
    """

    if not isinstance(title, str):
        return None
    match = PREFIX_PATTERN.match(title)
    if match is None:
        return None
    label = match.group(1).lower()
    return PREFIX_NORMALIZATION.get(label, label)


def load_labelled_pull_requests(data_dir: Path) -> pd.DataFrame:
    columns = [
        "id",
        "repo_url",
        "agent",
        "user_id",
        "title",
        "created_at",
        "merged_at",
    ]
    frame = pd.read_parquet(data_dir / "pull_request.parquet", columns=columns)
    frame["created_dt"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    frame["merged_dt"] = pd.to_datetime(frame["merged_at"], utc=True, errors="coerce")
    frame["task_type"] = frame["title"].map(classify_title)
    frame["merged_30d"] = (
        frame["merged_dt"].notna()
        & (frame["merged_dt"] >= frame["created_dt"])
        & (frame["merged_dt"] <= frame["created_dt"] + pd.Timedelta(days=30))
    )
    return frame


def load_predicted_pull_requests(
    data_dir: Path, predictions_path: Path, min_margin: float = 0.0
) -> pd.DataFrame:
    columns = [
        "id",
        "repo_url",
        "agent",
        "user_id",
        "title",
        "created_at",
        "merged_at",
    ]
    frame = pd.read_parquet(data_dir / "pull_request.parquet", columns=columns)
    predictions = pd.read_parquet(predictions_path)
    predictions.loc[
        predictions["classification_margin"] < min_margin, "task_type"
    ] = None
    frame = frame.merge(predictions, on="id", how="left", validate="one_to_one")
    frame["created_dt"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    frame["merged_dt"] = pd.to_datetime(frame["merged_at"], utc=True, errors="coerce")
    frame["merged_30d"] = (
        frame["merged_dt"].notna()
        & (frame["merged_dt"] >= frame["created_dt"])
        & (frame["merged_dt"] <= frame["created_dt"] + pd.Timedelta(days=30))
    )
    return frame


def validate_title_labels(frame: pd.DataFrame, data_dir: Path) -> dict[str, object]:
    supplied = pd.read_parquet(
        data_dir / "pr_task_type.parquet", columns=["id", "type", "confidence"]
    ).rename(columns={"type": "supplied_type"})
    checked = frame[["id", "task_type"]].merge(supplied, on="id", how="inner")
    checked = checked[checked["task_type"].notna()].copy()
    agreement = checked["task_type"].eq(checked["supplied_type"])
    by_type = (
        checked.assign(agree=agreement)
        .groupby("task_type", observed=True)
        .agg(n=("id", "size"), agreement=("agree", "mean"))
        .reset_index()
        .sort_values("n", ascending=False)
    )
    return {
        "pull_requests": int(len(frame)),
        "rule_labelled": int(frame["task_type"].notna().sum()),
        "rule_coverage": float(frame["task_type"].notna().mean()),
        "validation_overlap": int(len(checked)),
        "agreement": float(agreement.mean()) if len(checked) else math.nan,
        "agreement_by_type": by_type.to_dict(orient="records"),
    }


def _task_distribution(values: pd.Series, categories: list[str]) -> np.ndarray:
    counts = values.value_counts().reindex(categories, fill_value=0).to_numpy(float)
    return counts / counts.sum()


def _mean_rarity(values: pd.Series, pre_distribution: dict[str, float]) -> float:
    return float(values.map(lambda value: 1.0 - pre_distribution.get(value, 0.0)).mean())


def build_specialization_cohorts(
    frame: pd.DataFrame, config: SpecializationConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    labelled = frame[frame["task_type"].notna() & frame["created_dt"].notna()].copy()
    labelled_by_repo = {
        repo_url: group for repo_url, group in labelled.groupby("repo_url", sort=False)
    }
    all_by_repo = {
        repo_url: group for repo_url, group in frame.groupby("repo_url", sort=False)
    }
    observation_start = frame["created_dt"].min()
    observation_end = frame["created_dt"].max()
    first_seen = (
        frame.dropna(subset=["repo_url", "agent", "created_dt"])
        .groupby(["repo_url", "agent"], observed=True)["created_dt"]
        .min()
        .reset_index()
        .sort_values(["repo_url", "created_dt", "agent"])
    )
    records: list[dict[str, object]] = []
    post_rows: list[pd.DataFrame] = []

    for repo_url, agent_dates in first_seen.groupby("repo_url", sort=False):
        if len(agent_dates) < 2:
            continue
        agent_dates = agent_dates.sort_values(["created_dt", "agent"])
        if agent_dates.iloc[0]["created_dt"] == agent_dates.iloc[1]["created_dt"]:
            continue
        onset = agent_dates.iloc[1]["created_dt"]
        entrant = agent_dates.iloc[1]["agent"]
        incumbent = agent_dates.iloc[0]["agent"]
        repo_all = all_by_repo[repo_url]
        entrant_user_rows = repo_all[
            repo_all["agent"].eq(entrant) & repo_all["created_dt"].eq(onset)
        ].sort_values("id")
        entrant_user_id = (
            entrant_user_rows.iloc[0]["user_id"] if len(entrant_user_rows) else None
        )
        incumbent_users_before = set(
            repo_all.loc[
                repo_all["agent"].eq(incumbent) & (repo_all["created_dt"] < onset),
                "user_id",
            ].dropna()
        )
        same_contributor_entry = entrant_user_id in incumbent_users_before
        third_entry = (
            agent_dates.iloc[2]["created_dt"] if len(agent_dates) >= 3 else pd.NaT
        )
        third_agent_within_window = bool(
            pd.notna(third_entry)
            and third_entry <= onset + pd.Timedelta(days=config.post_days)
        )
        # Require complete symmetric exposure windows and a complete 30-day
        # merge window for the latest post-onset PR.  This avoids treating
        # right-censored work as not integrated.
        if onset - pd.Timedelta(days=config.pre_days) < observation_start:
            continue
        if (
            onset
            + pd.Timedelta(days=config.post_days)
            + pd.Timedelta(days=30)
            > observation_end
        ):
            continue
        repo = labelled_by_repo.get(repo_url)
        if repo is None:
            continue
        pre = repo[
            repo["created_dt"].between(
                onset - pd.Timedelta(days=config.pre_days), onset, inclusive="left"
            )
        ]
        post = repo[
            repo["created_dt"].between(
                onset, onset + pd.Timedelta(days=config.post_days), inclusive="both"
            )
        ].copy()
        # Keep the first two roles for the core contrast.  Later agents may enter
        # during the window, but treating them as the incumbent would blur the
        # comparison we pre-specified at the second-agent event.
        post_roles = post[post["agent"].isin([incumbent, entrant])].copy()
        entrant_post = post_roles[post_roles["agent"].eq(entrant)]
        incumbent_post = post_roles[post_roles["agent"].eq(incumbent)]
        if (
            len(pre) < config.min_pre
            or len(post_roles) < config.min_post
            or len(entrant_post) < config.min_entrant
            or len(incumbent_post) < 1
        ):
            continue

        categories = sorted(set(pre["task_type"]) | set(post_roles["task_type"]))
        pre_dist_array = _task_distribution(pre["task_type"], categories)
        entrant_dist = _task_distribution(entrant_post["task_type"], categories)
        incumbent_dist = _task_distribution(incumbent_post["task_type"], categories)
        pre_dist = pre["task_type"].value_counts(normalize=True).to_dict()
        entrant_rarity = _mean_rarity(entrant_post["task_type"], pre_dist)
        incumbent_rarity = _mean_rarity(incumbent_post["task_type"], pre_dist)
        new_types = set(post_roles["task_type"]) - set(pre["task_type"])
        entrant_introduced = 0
        incumbent_introduced = 0
        entrant_integrated = 0
        incumbent_integrated = 0
        for task_type in new_types:
            task_rows = post_roles[post_roles["task_type"].eq(task_type)].sort_values(
                ["created_dt", "id"]
            )
            introducing_agent = task_rows.iloc[0]["agent"]
            integrated = bool(task_rows["merged_30d"].any())
            if introducing_agent == entrant:
                entrant_introduced += 1
                entrant_integrated += int(
                    task_rows.loc[task_rows["agent"].eq(entrant), "merged_30d"].any()
                )
            else:
                incumbent_introduced += 1
                incumbent_integrated += int(integrated)

        records.append(
            {
                "repo_url": repo_url,
                "onset": onset,
                "incumbent": incumbent,
                "entrant": entrant,
                "entrant_user_id": entrant_user_id,
                "same_contributor_entry": same_contributor_entry,
                "third_agent_within_window": third_agent_within_window,
                "n_pre": len(pre),
                "n_post": len(post_roles),
                "n_entrant": len(entrant_post),
                "n_incumbent": len(incumbent_post),
                "pre_breadth": pre["task_type"].nunique(),
                "post_breadth": post_roles["task_type"].nunique(),
                "new_task_types": len(new_types),
                "entrant_introduced_types": entrant_introduced,
                "incumbent_introduced_types": incumbent_introduced,
                "entrant_integrated_types": entrant_integrated,
                "incumbent_integrated_types": incumbent_integrated,
                "entrant_new_share": entrant_post["task_type"].isin(new_types).mean(),
                "incumbent_new_share": incumbent_post["task_type"].isin(new_types).mean(),
                "entrant_rarity": entrant_rarity,
                "incumbent_rarity": incumbent_rarity,
                "rarity_difference": entrant_rarity - incumbent_rarity,
                "entrant_pre_jsd": float(jensenshannon(entrant_dist, pre_dist_array)),
                "incumbent_pre_jsd": float(jensenshannon(incumbent_dist, pre_dist_array)),
                "role_distance_jsd": float(jensenshannon(entrant_dist, incumbent_dist)),
                "rarefied_breadth_change": _rarefied_breadth_change(
                    pre["task_type"], post_roles["task_type"], config.seed, repo_url
                ),
            }
        )
        post_roles["entrant_role"] = post_roles["agent"].eq(entrant)
        post_roles["pre_rarity"] = post_roles["task_type"].map(
            lambda value: 1.0 - pre_dist.get(value, 0.0)
        )
        post_rows.append(
            post_roles[["repo_url", "task_type", "entrant_role", "pre_rarity"]]
        )

    cohort = pd.DataFrame.from_records(records)
    pooled_post = pd.concat(post_rows, ignore_index=True) if post_rows else pd.DataFrame()
    return cohort, pooled_post


def _bootstrap_mean_ci(values: np.ndarray, seed: int) -> tuple[float, float]:
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return math.nan, math.nan
    result = bootstrap(
        (values,),
        np.mean,
        confidence_level=0.95,
        n_resamples=5_000,
        method="BCa",
        random_state=np.random.default_rng(seed),
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def _rarefied_breadth_change(
    pre: pd.Series, post: pd.Series, seed: int, repo_url: str, draws: int = 500
) -> float:
    """Compare richness after equal-count subsampling within a repository."""

    sample_size = min(len(pre), len(post))
    if sample_size == 0:
        return math.nan
    stable_repo_seed = sum(ord(character) for character in repo_url) % 1_000_003
    rng = np.random.default_rng(seed + stable_repo_seed)
    pre_values = pre.to_numpy()
    post_values = post.to_numpy()
    differences = np.empty(draws)
    for index in range(draws):
        pre_sample = rng.choice(pre_values, size=sample_size, replace=False)
        post_sample = rng.choice(post_values, size=sample_size, replace=False)
        differences[index] = len(set(post_sample)) - len(set(pre_sample))
    return float(differences.mean())


def paired_sign_flip_test(
    contrasts: np.ndarray, permutations: int, seed: int
) -> dict[str, float]:
    """Randomize whole repository contrasts, preserving role/topic bundles."""

    contrasts = np.asarray(contrasts, dtype=float)
    contrasts = contrasts[np.isfinite(contrasts)]
    if not len(contrasts):
        return {"observed": math.nan, "p_two_sided": math.nan}
    observed = float(contrasts.mean())
    rng = np.random.default_rng(seed)
    null = np.empty(permutations)
    for index in range(permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(contrasts))
        null[index] = float(np.mean(contrasts * signs))
    p_value = (np.count_nonzero(np.abs(null) >= abs(observed)) + 1) / (permutations + 1)
    return {
        "observed": observed,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std(ddof=1)),
        "p_two_sided": float(p_value),
    }


def summarize_specialization(
    cohort: pd.DataFrame, pooled_post: pd.DataFrame, config: SpecializationConfig
) -> dict[str, object]:
    if cohort.empty:
        return {"eligible_repositories": 0}
    rarity = cohort["rarity_difference"].to_numpy(float)
    breadth = (cohort["post_breadth"] - cohort["pre_breadth"]).to_numpy(float)
    rarity_ci = _bootstrap_mean_ci(rarity, config.seed)
    breadth_ci = _bootstrap_mean_ci(breadth, config.seed + 1)
    try:
        signed_rank = wilcoxon(rarity, zero_method="wilcox", alternative="two-sided")
        signed_rank_p = float(signed_rank.pvalue)
    except ValueError:
        signed_rank_p = math.nan
    return {
        "eligible_repositories": int(len(cohort)),
        "labelled_pre_prs": int(cohort["n_pre"].sum()),
        "labelled_post_prs": int(cohort["n_post"].sum()),
        "mean_rarity_difference": float(np.mean(rarity)),
        "rarity_difference_ci95": list(rarity_ci),
        "median_rarity_difference": float(np.median(rarity)),
        "share_repositories_positive_rarity": float(np.mean(rarity > 0)),
        "wilcoxon_p": signed_rank_p,
        "mean_breadth_change": float(np.mean(breadth)),
        "breadth_change_ci95": list(breadth_ci),
        "share_repositories_with_new_task_type": float(
            np.mean(cohort["new_task_types"] > 0)
        ),
        "share_repositories_with_entrant_expansion": float(
            np.mean(cohort["entrant_introduced_types"] > 0)
        ),
        "share_repositories_with_integrated_entrant_expansion": float(
            np.mean(cohort["entrant_integrated_types"] > 0)
        ),
        "entrant_introduced_task_types": int(
            cohort["entrant_introduced_types"].sum()
        ),
        "entrant_integrated_task_types": int(
            cohort["entrant_integrated_types"].sum()
        ),
        "entrant_expansion_integration_rate": float(
            cohort["entrant_integrated_types"].sum()
            / cohort["entrant_introduced_types"].sum()
        )
        if cohort["entrant_introduced_types"].sum()
        else math.nan,
        "mean_role_distance_jsd": float(cohort["role_distance_jsd"].mean()),
        "mean_rarefied_breadth_change": float(
            cohort["rarefied_breadth_change"].mean()
        ),
        "rarefied_breadth_change_ci95": list(
            _bootstrap_mean_ci(
                cohort["rarefied_breadth_change"].to_numpy(float), config.seed + 3
            )
        ),
        "third_agent_within_window_share": float(
            cohort["third_agent_within_window"].mean()
        ),
        "paired_sign_flip_test": paired_sign_flip_test(
            rarity, config.permutations, config.seed + 2
        ),
    }


def save_specialization_results(
    config: SpecializationConfig,
    label_audit: dict[str, object],
    cohort: pd.DataFrame,
    summary: dict[str, object],
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    cohort.to_csv(config.output_dir / "specialization_repository_cohorts.csv", index=False)
    with (config.output_dir / "task_label_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(label_audit, handle, indent=2, ensure_ascii=False)
    with (config.output_dir / "specialization_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
