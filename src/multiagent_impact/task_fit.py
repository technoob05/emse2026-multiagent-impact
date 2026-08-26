from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from multiagent_impact.specialization import load_labelled_pull_requests


def _logit(value: float) -> float:
    clipped = float(np.clip(value, 1e-5, 1 - 1e-5))
    return math.log(clipped / (1.0 - clipped))


def build_historical_scores(
    labelled: pd.DataFrame,
) -> dict[pd.Timestamp, dict[str, dict[object, object]]]:
    """Build task scores using outcomes observable before each calendar month."""

    months = sorted(labelled["month_start"].dropna().unique())
    scores: dict[pd.Timestamp, dict[str, dict[object, object]]] = {}
    for raw_month in months:
        month = pd.Timestamp(raw_month)
        history_cutoff = month - pd.Timedelta(days=30)
        history = labelled[labelled["created_dt"] < history_cutoff]
        if history.empty:
            continue
        global_rate = float(history["merged_30d"].mean())
        type_stats = history.groupby("task_type", observed=True)["merged_30d"].agg(
            ["sum", "count"]
        )
        agent_stats = history.groupby("agent", observed=True)["merged_30d"].agg(
            ["sum", "count"]
        )
        pair_stats = history.groupby(["agent", "task_type"], observed=True)[
            "merged_30d"
        ].agg(["sum", "count"])

        type_prior = {
            task: (row["sum"] + 20.0 * global_rate) / (row["count"] + 20.0)
            for task, row in type_stats.iterrows()
        }
        agent_rate = {
            agent: (row["sum"] + 50.0 * global_rate) / (row["count"] + 50.0)
            for agent, row in agent_stats.iterrows()
        }
        advantage: dict[tuple[str, str], float] = {}
        pair_count: dict[tuple[str, str], int] = {}
        for pair, row in pair_stats.iterrows():
            agent, task = pair
            prior = type_prior[task]
            pair_rate = (row["sum"] + 20.0 * prior) / (row["count"] + 20.0)
            advantage[(agent, task)] = _logit(pair_rate) - _logit(agent_rate[agent])
            pair_count[(agent, task)] = int(row["count"])
        scores[month] = {
            "advantage": advantage,
            "pair_count": pair_count,
            "agent_rate": agent_rate,
        }
    return scores


def build_task_fit_sample(
    frame: pd.DataFrame, min_pair_history: int = 20
) -> pd.DataFrame:
    labelled = frame[frame["task_type"].notna() & frame["created_dt"].notna()].copy()
    labelled["month_start"] = pd.to_datetime(
        labelled["created_dt"].dt.strftime("%Y-%m-01"), utc=True
    )
    mature_cutoff = frame["created_dt"].max() - pd.Timedelta(days=30)
    historical_scores = build_historical_scores(labelled)
    labelled_by_id = labelled.set_index("id", drop=False)
    records: list[dict[str, object]] = []

    # Every PR establishes whether an agent was already available in a repo;
    # only explicit-prefix PRs enter the task-fit outcome analysis.
    ordered = frame.dropna(subset=["repo_url", "agent", "created_dt"]).sort_values(
        ["repo_url", "created_dt", "id"]
    )
    for repo_url, repo in ordered.groupby("repo_url", sort=False):
        seen_agents: set[str] = set()
        repo_prior_prs = 0
        for row in repo.itertuples(index=False):
            is_labelled = row.id in labelled_by_id.index
            if (
                is_labelled
                and row.created_dt <= mature_cutoff
                and row.agent in seen_agents
                and len(seen_agents) >= 2
            ):
                current = labelled_by_id.loc[row.id]
                month = pd.Timestamp(current["month_start"])
                score_bundle = historical_scores.get(month)
                if score_bundle is not None:
                    advantage = score_bundle["advantage"]
                    counts = score_bundle["pair_count"]
                    task = current["task_type"]
                    candidate_scores = {
                        agent: advantage[(agent, task)]
                        for agent in seen_agents
                        if (agent, task) in advantage
                        and counts.get((agent, task), 0) >= min_pair_history
                    }
                    if row.agent in candidate_scores and len(candidate_scores) >= 2:
                        current_score = candidate_scores[row.agent]
                        alternatives = [
                            value
                            for agent, value in candidate_scores.items()
                            if agent != row.agent
                        ]
                        agent_rates = score_bundle["agent_rate"]
                        available_general = {
                            agent: agent_rates[agent]
                            for agent in candidate_scores
                            if agent in agent_rates
                        }
                        records.append(
                            {
                                "id": row.id,
                                "repo_url": repo_url,
                                "agent": row.agent,
                                "task_type": task,
                                "calendar_month": month.strftime("%Y-%m"),
                                "repo_prior_prs": repo_prior_prs,
                                "n_candidate_agents": len(candidate_scores),
                                "fit_margin": current_score - float(np.mean(alternatives)),
                                "best_task_fit": int(
                                    current_score >= max(candidate_scores.values()) - 1e-12
                                ),
                                "best_general_agent": int(
                                    row.agent
                                    == max(available_general, key=available_general.get)
                                ),
                                "merged_30d": int(current["merged_30d"]),
                            }
                        )
            seen_agents.add(row.agent)
            repo_prior_prs += 1
    return pd.DataFrame.from_records(records)


def _model_result(sample: pd.DataFrame, formula: str) -> dict[str, object]:
    model = smf.ols(formula, data=sample).fit(
        cov_type="cluster", cov_kwds={"groups": sample["repo_url"]}
    )
    terms = ["best_task_fit", "best_general_agent", "fit_margin"]
    estimates = {}
    for term in terms:
        if term in model.params.index:
            estimates[term] = {
                "estimate": float(model.params[term]),
                "se": float(model.bse[term]),
                "p": float(model.pvalues[term]),
                "ci95": [float(value) for value in model.conf_int().loc[term]],
            }
    return {
        "n": int(model.nobs),
        "r_squared": float(model.rsquared),
        "terms": estimates,
    }


def analyze_task_fit(sample: pd.DataFrame) -> dict[str, object]:
    if sample.empty:
        return {"eligible_pull_requests": 0}
    task_fit = sample.groupby("best_task_fit", observed=True)["merged_30d"].agg(
        ["mean", "size"]
    )
    common_controls = (
        "C(task_type) + C(agent) + C(calendar_month) + "
        "np.log1p(repo_prior_prs)"
    )
    base_model = _model_result(
        sample,
        "merged_30d ~ best_task_fit + best_general_agent + " + common_controls,
    )
    repo_fe_model = _model_result(
        sample,
        "merged_30d ~ best_task_fit + best_general_agent + "
        + common_controls
        + " + C(repo_url)",
    )
    margin_model = _model_result(
        sample,
        "merged_30d ~ fit_margin + best_general_agent + "
        + common_controls
        + " + C(repo_url)",
    )
    return {
        "eligible_pull_requests": int(len(sample)),
        "repositories": int(sample["repo_url"].nunique()),
        "agents": int(sample["agent"].nunique()),
        "months": int(sample["calendar_month"].nunique()),
        "raw_by_task_fit": {
            str(key): {"merge_30d": float(row["mean"]), "n": int(row["size"])}
            for key, row in task_fit.iterrows()
        },
        "adjusted_without_repo_fixed_effects": base_model,
        "adjusted_with_repo_fixed_effects": repo_fe_model,
        "continuous_margin_with_repo_fixed_effects": margin_model,
    }


def save_task_fit_results(
    sample: pd.DataFrame, results: dict[str, object], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output_dir / "task_fit_analysis_sample.csv", index=False)
    with (output_dir / "task_fit_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)
