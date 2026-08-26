from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import bootstrap
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class MatchedAdoptionConfig:
    data_dir: Path
    output_dir: Path
    pre_months: int = 3
    post_months: int = 3
    seed: int = 20260825
    max_match_distance: float = 1.5
    match_with_replacement: bool = True


def _month_start(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.dt.strftime("%Y-%m-01"), utc=True)


def load_monthly_panel(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["id", "repo_url", "agent", "created_at", "merged_at"]
    prs = pd.read_parquet(data_dir / "pull_request.parquet", columns=columns)
    prs["created_dt"] = pd.to_datetime(prs["created_at"], utc=True, errors="coerce")
    prs["merged_dt"] = pd.to_datetime(prs["merged_at"], utc=True, errors="coerce")
    prs = prs.dropna(subset=["repo_url", "agent", "created_dt"]).copy()
    prs["month"] = _month_start(prs["created_dt"])
    prs["merged_30d"] = (
        prs["merged_dt"].notna()
        & (prs["merged_dt"] >= prs["created_dt"])
        & (prs["merged_dt"] <= prs["created_dt"] + pd.Timedelta(days=30))
    ).astype(int)

    first_agent = (
        prs.sort_values(["repo_url", "created_dt", "id"])
        .drop_duplicates(["repo_url", "agent"])
        [["repo_url", "agent", "created_dt"]]
    )
    firsts = first_agent.sort_values(["repo_url", "created_dt", "agent"])
    repo_timing_records = []
    for repo_url, group in firsts.groupby("repo_url", sort=False):
        group = group.sort_values(["created_dt", "agent"])
        repo_timing_records.append(
            {
                "repo_url": repo_url,
                "first_agent": group.iloc[0]["agent"],
                "first_dt": group.iloc[0]["created_dt"],
                "second_dt": group.iloc[1]["created_dt"] if len(group) >= 2 else pd.NaT,
                "third_dt": group.iloc[2]["created_dt"] if len(group) >= 3 else pd.NaT,
            }
        )
    timing = pd.DataFrame(repo_timing_records)
    timing["first_month"] = _month_start(timing["first_dt"])
    timing["second_month"] = _month_start(timing["second_dt"])
    timing["third_month"] = _month_start(timing["third_dt"])

    monthly = prs.groupby(["repo_url", "month"], observed=True).agg(
        pr_count=("id", "size"),
        merged_30d_count=("merged_30d", "sum"),
    ).reset_index()
    monthly["merge_30d_rate"] = monthly["merged_30d_count"] / monthly["pr_count"]
    return monthly, timing


def _repo_features(
    panel: pd.DataFrame, repo_url: str, onset: pd.Timestamp
) -> dict[str, float] | None:
    months = [onset - pd.DateOffset(months=value) for value in [3, 2, 1]]
    indexed = panel[panel["repo_url"].eq(repo_url)].set_index("month")
    if any(month not in indexed.index for month in months):
        return None
    pre = indexed.loc[months]
    if (pre["pr_count"] < 1).any():
        return None
    log_counts = np.log1p(pre["pr_count"].to_numpy(float))
    merge_rate = pre["merged_30d_count"].sum() / pre["pr_count"].sum()
    return {
        "log_pr_mean": float(log_counts.mean()),
        "log_pr_slope": float(np.polyfit(np.arange(3), log_counts, 1)[0]),
        "merge_rate": float(merge_rate),
    }


def build_matched_pairs(
    monthly: pd.DataFrame, timing: pd.DataFrame, config: MatchedAdoptionConfig
) -> pd.DataFrame:
    max_mature_month = pd.Timestamp("2026-02-01", tz="UTC")
    # January 2025 is the first complete calendar month in the dataset.
    earliest_onset = pd.Timestamp("2025-01-01", tz="UTC") + pd.DateOffset(
        months=config.pre_months
    )
    latest_onset = max_mature_month - pd.DateOffset(months=config.post_months)
    treated = timing[
        timing["second_month"].between(earliest_onset, latest_onset, inclusive="both")
        & (
            timing["first_month"]
            <= timing["second_month"] - pd.DateOffset(months=config.pre_months)
        )
        & (
            timing["third_month"].isna()
            | (
                timing["third_month"]
                > timing["second_month"] + pd.DateOffset(months=config.post_months)
            )
        )
    ].copy()
    feature_names = ["log_pr_mean", "log_pr_slope", "merge_rate"]
    records = []
    used_controls: set[str] = set()

    for (onset, first_agent), treated_group in treated.groupby(
        ["second_month", "first_agent"], sort=False
    ):
        candidates = timing[
            timing["first_agent"].eq(first_agent)
            & (
                timing["first_month"]
                <= onset - pd.DateOffset(months=config.pre_months)
            )
            & (
                timing["second_month"].isna()
                | (
                    timing["second_month"]
                    > onset + pd.DateOffset(months=config.post_months)
                )
            )
        ].copy()
        candidate_rows = []
        for candidate in candidates.itertuples(index=False):
            features = _repo_features(monthly, candidate.repo_url, onset)
            if features is not None:
                candidate_rows.append({"repo_url": candidate.repo_url, **features})
        if not candidate_rows:
            continue
        candidate_features = pd.DataFrame(candidate_rows).drop_duplicates("repo_url")

        treated_rows = []
        for row in treated_group.itertuples(index=False):
            features = _repo_features(monthly, row.repo_url, onset)
            if features is not None:
                treated_rows.append({"repo_url": row.repo_url, **features})
        if not treated_rows:
            continue
        treated_features = pd.DataFrame(treated_rows)
        scaler = StandardScaler().fit(
            pd.concat([treated_features[feature_names], candidate_features[feature_names]])
        )
        treated_scaled = scaler.transform(treated_features[feature_names])
        candidate_scaled = scaler.transform(candidate_features[feature_names])
        for index, treated_row in treated_features.iterrows():
            distances = np.sqrt(
                np.sum((candidate_scaled - treated_scaled[index]) ** 2, axis=1)
            )
            order = np.argsort(distances)
            chosen_index = next(
                (
                    item
                    for item in order
                    if candidate_features.iloc[item]["repo_url"]
                    != treated_row["repo_url"]
                    and (
                        config.match_with_replacement
                        or candidate_features.iloc[item]["repo_url"]
                        not in used_controls
                    )
                ),
                None,
            )
            if chosen_index is None or distances[chosen_index] > config.max_match_distance:
                continue
            used_controls.add(candidate_features.iloc[chosen_index]["repo_url"])
            records.append(
                {
                    "treated_repo": treated_row["repo_url"],
                    "control_repo": candidate_features.iloc[chosen_index]["repo_url"],
                    "onset_month": onset,
                    "first_agent": first_agent,
                    "match_distance": float(distances[chosen_index]),
                    **{
                        f"treated_{name}": float(treated_row[name])
                        for name in feature_names
                    },
                    **{
                        f"control_{name}": float(
                            candidate_features.iloc[chosen_index][name]
                        )
                        for name in feature_names
                    },
                }
            )
    return pd.DataFrame.from_records(records)


def build_event_contrasts(
    monthly: pd.DataFrame, pairs: pd.DataFrame, config: MatchedAdoptionConfig
) -> pd.DataFrame:
    indexed = monthly.set_index(["repo_url", "month"])
    records = []
    for pair_id, pair in pairs.reset_index(drop=True).iterrows():
        onset = pair["onset_month"]
        for event_month in range(-config.pre_months, config.post_months + 1):
            month = onset + pd.DateOffset(months=event_month)
            values = {}
            for role, repo_url in [
                ("treated", pair["treated_repo"]),
                ("control", pair["control_repo"]),
            ]:
                try:
                    row = indexed.loc[(repo_url, month)]
                    pr_count = float(row["pr_count"])
                    merged_count = float(row["merged_30d_count"])
                except KeyError:
                    pr_count = 0.0
                    merged_count = 0.0
                values[f"{role}_log_pr"] = float(np.log1p(pr_count))
                values[f"{role}_pr_count"] = pr_count
                values[f"{role}_merged_count"] = merged_count
            records.append(
                {
                    "pair_id": pair_id,
                    "treated_repo": pair["treated_repo"],
                    "control_repo": pair["control_repo"],
                    "onset_month": onset,
                    "event_month": event_month,
                    "log_pr_difference": values["treated_log_pr"]
                    - values["control_log_pr"],
                    "pr_count_difference": values["treated_pr_count"]
                    - values["control_pr_count"],
                    "merged_count_difference": values["treated_merged_count"]
                    - values["control_merged_count"],
                }
            )
    contrasts = pd.DataFrame.from_records(records)
    baseline = contrasts[contrasts["event_month"].eq(-1)][
        ["pair_id", "log_pr_difference", "pr_count_difference", "merged_count_difference"]
    ].rename(
        columns={
            "log_pr_difference": "baseline_log_pr_difference",
            "pr_count_difference": "baseline_pr_count_difference",
            "merged_count_difference": "baseline_merged_count_difference",
        }
    )
    contrasts = contrasts.merge(baseline, on="pair_id", validate="many_to_one")
    for outcome in ["log_pr", "pr_count", "merged_count"]:
        contrasts[f"{outcome}_did"] = (
            contrasts[f"{outcome}_difference"]
            - contrasts[f"baseline_{outcome}_difference"]
        )
    return contrasts


def _mean_ci(values: np.ndarray, seed: int) -> tuple[float, float]:
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return float("nan"), float("nan")
    result = bootstrap(
        (values,), np.mean, n_resamples=5000, method="BCa",
        random_state=np.random.default_rng(seed)
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def summarize_event_contrasts(
    contrasts: pd.DataFrame, pairs: pd.DataFrame, config: MatchedAdoptionConfig
) -> tuple[pd.DataFrame, dict[str, object]]:
    rows = []
    for event_month, group in contrasts.groupby("event_month", sort=True):
        row = {"event_month": int(event_month), "pairs": int(len(group))}
        for index, outcome in enumerate(["log_pr", "pr_count", "merged_count"]):
            values = group[f"{outcome}_did"].to_numpy(float)
            ci = _mean_ci(values, config.seed + int(event_month) * 10 + index)
            row[f"{outcome}_estimate"] = float(values.mean())
            row[f"{outcome}_ci_low"] = ci[0]
            row[f"{outcome}_ci_high"] = ci[1]
        rows.append(row)
    summary_frame = pd.DataFrame(rows)
    pre = summary_frame[
        (summary_frame["event_month"] < -1)
        & (summary_frame["event_month"] >= -config.pre_months)
    ]
    post = summary_frame[summary_frame["event_month"].isin([0, 1, 2, 3])]
    summary = {
        "matched_pairs": int(len(pairs)),
        "median_match_distance": float(pairs["match_distance"].median()),
        "max_match_distance": float(pairs["match_distance"].max()),
        "pretrend_max_abs_log_pr": float(pre["log_pr_estimate"].abs().max()),
        "pretrend_ci_excludes_zero": bool(
            ((pre["log_pr_ci_low"] > 0) | (pre["log_pr_ci_high"] < 0)).any()
        ),
        "post_mean_log_pr": float(post["log_pr_estimate"].mean()),
        "post_mean_pr_count": float(post["pr_count_estimate"].mean()),
        "post_mean_merged_count": float(post["merged_count_estimate"].mean()),
        "causal_gate_passed": bool(
            not ((pre["log_pr_ci_low"] > 0) | (pre["log_pr_ci_high"] < 0)).any()
        ),
    }
    return summary_frame, summary


def run_matched_adoption(config: MatchedAdoptionConfig) -> dict[str, object]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    monthly, timing = load_monthly_panel(config.data_dir)
    pairs = build_matched_pairs(monthly, timing, config)
    contrasts = build_event_contrasts(monthly, pairs, config)
    event_summary, summary = summarize_event_contrasts(contrasts, pairs, config)
    pairs.to_csv(config.output_dir / "matched_adoption_pairs.csv", index=False)
    contrasts.to_csv(config.output_dir / "matched_adoption_contrasts.csv", index=False)
    event_summary.to_csv(config.output_dir / "matched_adoption_event_summary.csv", index=False)
    with (config.output_dir / "matched_adoption_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)
    return summary
