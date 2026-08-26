"""Leave-one-pair/repository robustness for the response-ownership story."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
CHAIN_DIR = ROOT / "outputs" / "cross_agent_review"
OWNER_DIR = ROOT / "outputs" / "response_ownership"

OWNER_METRICS = [
    "known_human_first_share",
    "mapped_agent_first_share",
    "no_action_share",
    "direct_reply_pr_share",
    "strict_cross_product_dialogue_share",
]


def owner_frame() -> pd.DataFrame:
    chains = pl.read_parquet(CHAIN_DIR / "cross_feedback_response_chains.parquet")
    first = pl.read_parquet(OWNER_DIR / "first_response_ownership.parquet")
    events = pl.read_parquet(CHAIN_DIR / "cross_feedback_response_events.parquet")
    strict = (
        events.filter(
            (pl.col("response_source") == "direct_inline_reply")
            & pl.col("response_agent").is_not_null()
            & (pl.col("response_agent") != pl.col("trigger_reviewer_agent"))
        )
        .group_by("pr_id")
        .agg(pl.lit(True).alias("strict_cross_product_dialogue"))
    )
    return (
        chains.join(first.select(["pr_id", "first_owner"]), on="pr_id")
        .join(strict, on="pr_id", how="left")
        .with_columns(
            pl.col("strict_cross_product_dialogue").fill_null(False),
            pl.col("first_owner")
            .is_in(["author_human", "other_human"])
            .alias("known_human_first"),
            pl.col("first_owner")
            .is_in(["author_agent", "triggering_reviewer", "other_agent"])
            .alias("mapped_agent_first"),
            (pl.col("first_owner") == "no_observed_action").alias("no_action"),
            (pl.col("direct_inline_replies") > 0).alias("direct_reply_pr"),
        )
        .to_pandas()
    )


def owner_metrics(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "known_human_first_share": frame["known_human_first"].mean(),
        "mapped_agent_first_share": frame["mapped_agent_first"].mean(),
        "no_action_share": frame["no_action"].mean(),
        "direct_reply_pr_share": frame["direct_reply_pr"].mean(),
        "strict_cross_product_dialogue_share": frame[
            "strict_cross_product_dialogue"
        ].mean(),
    }


def owner_leave_one_out(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    pair_groups = frame.groupby(
        ["author_agent", "trigger_reviewer_agent"], observed=True
    ).indices
    repo_groups = frame.groupby("repo_id", observed=True).indices

    for (author, reviewer), positions in pair_groups.items():
        keep = np.ones(len(frame), dtype=bool)
        keep[positions] = False
        rows.append(
            {
                "exclusion_unit": "author_reviewer_pair",
                "excluded_group": f"{author} -> {reviewer}",
                "n_prs": int(keep.sum()),
                **owner_metrics(frame.loc[keep]),
            }
        )
    for repo_id, positions in repo_groups.items():
        keep = np.ones(len(frame), dtype=bool)
        keep[positions] = False
        rows.append(
            {
                "exclusion_unit": "repository",
                "excluded_group": str(repo_id),
                "n_prs": int(keep.sum()),
                **owner_metrics(frame.loc[keep]),
            }
        )
    return pd.DataFrame(rows)


def summarize_owner_loo(
    base: dict[str, float], leave_one_out: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for unit, group in leave_one_out.groupby("exclusion_unit"):
        for metric in OWNER_METRICS:
            rows.append(
                {
                    "exclusion_unit": unit,
                    "metric": metric,
                    "full_estimate": base[metric],
                    "loo_min": group[metric].min(),
                    "loo_max": group[metric].max(),
                    "exclusions": len(group),
                }
            )
    return pd.DataFrame(rows)


def route_leave_one_out() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_parquet(OWNER_DIR / "ownership_route_48h.parquet")
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)
    frame["trigger_month"] = pd.to_datetime(
        frame["trigger_dt"], utc=True
    ).dt.strftime("%Y-%m")
    route = "C(ownership_route_48h, Treatment('no_observed_action'))"
    formula = (
        "merged_from_48h_to_30d ~ "
        + route
        + " + C(author_agent) + C(trigger_reviewer_agent)"
        + " + C(trigger_source) + C(trigger_month)"
    )
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    route_terms = [term for term in design.columns if "ownership_route_48h" in term]
    full_beta = np.linalg.lstsq(
        design.to_numpy(), outcome.to_numpy()[:, 0], rcond=None
    )[0]
    full = {term: full_beta[design.columns.get_loc(term)] for term in route_terms}

    rows: list[dict[str, object]] = []
    group_specs = [
        (
            "author_reviewer_pair",
            frame.groupby(
                ["author_agent", "trigger_reviewer_agent"], observed=True
            ).indices,
        ),
        ("repository", frame.groupby("repo_id", observed=True).indices),
    ]
    x = design.to_numpy()
    y = outcome.to_numpy()[:, 0]
    for unit, groups in group_specs:
        for group_key, positions in groups.items():
            keep = np.ones(len(frame), dtype=bool)
            keep[positions] = False
            beta = np.linalg.lstsq(x[keep], y[keep], rcond=None)[0]
            if unit == "author_reviewer_pair":
                excluded = f"{group_key[0]} -> {group_key[1]}"
            else:
                excluded = str(group_key)
            for term in route_terms:
                route_name = term.split("[T.", 1)[1].rstrip("]")
                rows.append(
                    {
                        "exclusion_unit": unit,
                        "excluded_group": excluded,
                        "route": route_name,
                        "n_prs": int(keep.sum()),
                        "estimate": beta[design.columns.get_loc(term)],
                    }
                )

    leave_one_out = pd.DataFrame(rows)
    summary_rows: list[dict[str, object]] = []
    for (unit, route_name), group in leave_one_out.groupby(
        ["exclusion_unit", "route"], observed=True
    ):
        term = next(term for term in route_terms if f"[T.{route_name}]" in term)
        summary_rows.append(
            {
                "exclusion_unit": unit,
                "route": route_name,
                "full_estimate": full[term],
                "loo_min": group["estimate"].min(),
                "loo_max": group["estimate"].max(),
                "all_positive": bool((group["estimate"] > 0).all()),
                "exclusions": len(group),
            }
        )
    return leave_one_out, pd.DataFrame(summary_rows)


def main() -> None:
    OWNER_DIR.mkdir(parents=True, exist_ok=True)
    owners = owner_frame()
    base = owner_metrics(owners)
    owner_loo = owner_leave_one_out(owners)
    owner_summary = summarize_owner_loo(base, owner_loo)
    route_loo, route_summary = route_leave_one_out()

    owner_loo.to_csv(OWNER_DIR / "ownership_descriptive_leave_one_out.csv", index=False)
    owner_summary.to_csv(
        OWNER_DIR / "ownership_descriptive_leave_one_out_summary.csv", index=False
    )
    route_loo.to_csv(OWNER_DIR / "ownership_route_leave_one_out.csv", index=False)
    route_summary.to_csv(
        OWNER_DIR / "ownership_route_leave_one_out_summary.csv", index=False
    )

    print("OWNER LOO SUMMARY", owner_summary.to_dict(orient="records"))
    print("ROUTE LOO SUMMARY", route_summary.to_dict(orient="records"))


if __name__ == "__main__":
    main()
