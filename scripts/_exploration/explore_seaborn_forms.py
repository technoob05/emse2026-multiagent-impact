"""Two more chart forms for Figures 3 and 6, in a heavier publication style.

The dot-and-interval forms are informationally right and visually thin: small
marks on wide white panels. These try solid marks instead. Figure 3 becomes a
diverging bar chart, which is the most-read form in empirical software
engineering and reads as a chart rather than as scattered points. Figure 6
shades the area between what happened and what would have happened, so the
contrast is a region rather than an arrow.

Exploration only. Nothing here is imported by the production figure module.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "qa" / "explore"
OUT.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location(
    "house", ROOT / "scripts" / "figures" / "visualize_manuscript_figures.py"
)
house = importlib.util.module_from_spec(spec)
# The house module defines a dataclass, and dataclasses resolve their own
# module from sys.modules, so it has to be registered before exec.
sys.modules[spec.name] = house
spec.loader.exec_module(house)

TOPOLOGY = ROOT / "outputs" / "coordination_topology"
THREAD = ROOT / "outputs" / "matched_thread_position"
HISTORY = ROOT / "outputs" / "human_memory_bridge"
CONTEXT = ROOT / "outputs" / "task_context_interaction"

INK, SLATE, MID = house.INK, house.SLATE, house.MID
BLUE, ORANGE, TEAL = house.BLUE, house.ORANGE, house.TEAL
PALE_TEAL = house.PALE_TEAL


def styled() -> None:
    sns.set_theme(style="ticks", context="paper")
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "font.family": "DejaVu Sans",
            "font.size": 8.4,
            "axes.titlesize": 9.6,
            "axes.titleweight": "bold",
            "axes.labelsize": 8.6,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "axes.edgecolor": SLATE,
            "axes.linewidth": 0.8,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": None,
        }
    )


OUTCOMES = (
    ("any_visible_followup", "Anyone does anything"),
    ("later_pr_comment", "Someone comments"),
    ("new_review_round", "A new review round"),
    ("exact_trigger_reply", "The point gets a reply"),
    ("visible_force_push", "The branch is rewritten"),
    ("merge_within_7d", "Merged within a week"),
)


def figure3_diverging() -> None:
    primary = pd.read_csv(TOPOLOGY / "matched_visibility_contrasts.csv")
    primary = primary[primary["specification"] == "exact_author_user"]
    restricted = pd.read_csv(THREAD / "restricted_visibility_contrasts.csv")
    restricted = restricted[
        (restricted["specification"] == "exact_author_user")
        & (restricted["population"] == "both_triggers_open_their_own_thread")
    ]

    rows = []
    for key, label in OUTCOMES:
        source = restricted if key == "exact_trigger_reply" else primary
        row = source[source["outcome"] == key].iloc[0]
        low = float(row["repository_cluster_bootstrap_ci_low"]) * 100
        high = float(row["repository_cluster_bootstrap_ci_high"]) * 100
        rows.append(
            {
                "label": label + ("*" if key == "exact_trigger_reply" else ""),
                "gap": (float(row["cross_rate"]) - float(row["same_rate"])) * 100,
                "low": low,
                "high": high,
                "clears": low > 0 or high < 0,
                "cross": float(row["cross_rate"]) * 100,
                "same": float(row["same_rate"]) * 100,
                "pairs": int(row["pairs"]),
            }
        )
    frame = pd.DataFrame(rows)

    styled()
    fig, (top, bottom) = plt.subplots(
        2,
        1,
        figsize=(house.FIGURE_WIDTH, 5.0),
        gridspec_kw={"height_ratios": [1.55, 1.0], "hspace": 0.95},
    )

    positions = np.arange(len(frame))[::-1]
    colours = [ORANGE if clears else MID for clears in frame["clears"]]
    top.barh(
        positions,
        frame["gap"],
        height=0.62,
        color=colours,
        edgecolor=[SLATE if c else MID for c in frame["clears"]],
        linewidth=0.8,
        zorder=2,
    )
    top.errorbar(
        frame["gap"],
        positions,
        xerr=[frame["gap"] - frame["low"], frame["high"] - frame["gap"]],
        fmt="none",
        ecolor=SLATE,
        elinewidth=1.0,
        capsize=2.6,
        zorder=3,
    )
    top.axvline(0, color=INK, linewidth=1.1, zorder=4)

    # Rate labels sit in one right-hand column, so they never collide with a
    # bar, a whisker, or a row label however long the interval is.
    for position, row in zip(positions, frame.itertuples(index=False), strict=True):
        top.text(
            27.5,
            position,
            f"{row.cross:.0f}% vs {row.same:.0f}%",
            ha="left",
            va="center",
            fontsize=8.0,
            color=INK if row.clears else SLATE,
            fontweight="bold" if row.clears else "normal",
        )

    top.set_yticks(positions)
    top.set_yticklabels(frame["label"], fontsize=8.2)
    top.set_xlim(-40, 26)
    top.set_xlabel("Cross-product minus same-product (pp, 95% CI)")
    top.set_title("A  One outcome changes. Five do not.", loc="left", x=-0.30)
    sns.despine(ax=top, left=True)
    top.tick_params(axis="y", length=0)
    top.grid(axis="x", color="#E8E8E8", linewidth=0.6, zorder=0)
    top.set_axisbelow(True)
    top.text(
        -0.275,
        -0.42,
        f"{int(frame['pairs'].max()):,} matched pairs in 149 repositories." + chr(10)
        + f"*{int(frame.loc[3, 'pairs']):,} pairs where a reply is possible on both sides.",
        transform=top.transAxes,
        ha="left",
        va="top",
        fontsize=8.0,
        color=SLATE,
    )

    mediator = pd.read_csv(HISTORY / "first_mediator_role_summary.csv")
    decisive = pd.read_csv(HISTORY / "first_decisive_reviewer_role_summary.csv")
    baselines = pd.read_csv(HISTORY / "observable_population_baselines.csv")
    bars = [
        (
            "Whoever replies first",
            float(mediator.loc[mediator["account_role"] == "all_first_mediators", "prior_reviewer_share"].iloc[0]) * 100,
            int(mediator.loc[mediator["account_role"] == "all_first_mediators", "prs"].iloc[0]),
        ),
        (
            "Whoever reviews last",
            float(decisive.loc[decisive["account_role"] == "all_first_decisive_reviewers", "prior_reviewer_share"].iloc[0]) * 100,
            int(decisive.loc[decisive["account_role"] == "all_first_decisive_reviewers", "prs"].iloc[0]),
        ),
        (
            "Anyone acting in 48 h",
            float(baselines.loc[baselines["population"] == "all_distinct_48h_user_responders", "prior_reviewer_share"].iloc[0]) * 100,
            int(baselines.loc[baselines["population"] == "all_distinct_48h_user_responders", "rows"].iloc[0]),
        ),
    ]
    labels = [row[0] for row in bars]
    shares = [row[1] for row in bars]
    counts = [row[2] for row in bars]
    positions = np.arange(len(bars))[::-1]
    bottom.barh(
        positions, shares, height=0.55, color=PALE_TEAL, edgecolor=TEAL, linewidth=0.9, zorder=2
    )
    for position, share, count in zip(positions, shares, counts, strict=True):
        bottom.text(
            share - 1.6,
            position,
            f"{share:.0f}%",
            ha="right",
            va="center",
            fontsize=8.2,
            color="white",
            fontweight="bold",
        )
        bottom.text(
            share + 1.6, position, f"n = {count:,}", ha="left", va="center",
            fontsize=8.0, color=SLATE,
        )
    bottom.set_yticks(positions)
    bottom.set_yticklabels(labels, fontsize=8.2)
    bottom.set_xlim(0, 100)
    bottom.set_xlabel("Had reviewed in this repository before (%)")
    bottom.set_title("B  Whoever steps in has been here before", loc="left", x=-0.30)
    sns.despine(ax=bottom, left=True)
    bottom.tick_params(axis="y", length=0)
    bottom.grid(axis="x", color="#E8E8E8", linewidth=0.6, zorder=0)
    bottom.set_axisbelow(True)

    fig.subplots_adjust(left=0.275, right=0.815, top=0.935, bottom=0.115)
    fig.savefig(OUT / "fig3_seaborn_diverging.pdf")
    fig.savefig(OUT / "fig3_seaborn_diverging.png", dpi=300)
    plt.close(fig)
    print("wrote fig3_seaborn_diverging")


def figure6_area() -> None:
    cells = pd.read_csv(CONTEXT / "answer_rate_cells.csv")
    cells = cells[cells["population"] == "thread-root triggers"]
    models = pd.read_csv(CONTEXT / "interaction_models.csv")
    primary = models[
        models["specification"] == "Thread-root triggers, repository and month FE"
    ].iloc[0]
    loo = pd.read_csv(CONTEXT / "leave_one_repository_out.csv")["estimate"].to_numpy() * 100

    def cell(relation: str, link: bool) -> tuple[float, int]:
        row = cells[(cells["reviewer_relation"] == relation) & (cells["body_issue_link"] == link)].iloc[0]
        return float(row["answered_rate"]) * 100, int(row["prs"])

    cross0, n_cross0 = cell("cross_product", False)
    cross1, n_cross1 = cell("cross_product", True)
    same0, n_same0 = cell("same_product", False)
    same1, n_same1 = cell("same_product", True)
    ghost = cross0 + (same1 - same0)
    raw = (cross1 - cross0) - (same1 - same0)

    styled()
    fig, (top, bottom) = plt.subplots(
        2,
        1,
        figsize=(house.FIGURE_WIDTH, 4.05),
        gridspec_kw={"height_ratios": [2.5, 0.85], "hspace": 0.48},
    )

    x = np.array([0.0, 1.0])
    # The region between what happened and what the same-product change predicts
    # is the raw contrast, so draw it as an area rather than as an arrow.
    top.fill_between(
        x, [cross0, ghost], [cross0, cross1], color=TEAL, alpha=0.16, linewidth=0, zorder=1
    )
    top.plot(x, [same0, same1], color=SLATE, linewidth=2.2, linestyle=(0, (4, 2)),
             marker="s", markersize=6.0, markerfacecolor=SLATE, markeredgecolor="white",
             markeredgewidth=0.8, zorder=3)
    top.plot(x, [cross0, ghost], color=MID, linewidth=1.4, linestyle=(0, (1, 2)),
             marker="o", markersize=5.0, markerfacecolor="white", markeredgecolor=MID,
             zorder=2)
    top.plot(x, [cross0, cross1], color=TEAL, linewidth=2.6, marker="o", markersize=6.6,
             markerfacecolor=TEAL, markeredgecolor="white", markeredgewidth=0.8, zorder=4)

    # The shaded region is the contrast, so the label belongs inside it, low
    # enough to clear the same-product line that crosses the panel.
    top.text(
        0.62,
        (cross0 + ghost) / 2 + 1.6,
        f"{raw:+.1f} pp raw contrast",
        ha="center",
        va="center",
        fontsize=8.4,
        color=TEAL,
        fontweight="bold",
    )
    for value, count, label, colour in (
        (cross1, n_cross1, "a different product", TEAL),
        (same1, n_same1, "the same product", SLATE),
    ):
        top.text(
            1.06,
            value,
            f"{value:.1f}%  {label}" + chr(10) + f"of {count:,} PRs",
            ha="left",
            va="center",
            fontsize=8.0,
            color=colour,
        )
    top.text(
        1.06,
        ghost,
        f"{ghost:.1f}%  if it moved" + chr(10) + "like the same product"
        + chr(10) + "(not observed)",
        ha="left",
        va="center",
        fontsize=8.0,
        color=MID,
    )
    # Starting values go beside their own marker, inside the panel, offset away
    # from the other series.
    top.text(
        0.04,
        cross0 - 2.8,
        f"{cross0:.1f}% of {n_cross0:,} PRs",
        ha="left",
        va="center",
        fontsize=8.0,
        color=TEAL,
    )
    top.text(
        0.04,
        same0 + 2.6,
        f"{same0:.1f}% of {n_same0:,} PRs",
        ha="left",
        va="center",
        fontsize=8.0,
        color=SLATE,
    )

    top.set_xlim(-0.05, 1.72)
    top.set_ylim(0, 34)
    top.set_xticks([0, 1])
    top.set_xticklabels(["No issue link", "PR body links an issue"], fontsize=8.2)
    top.set_ylabel("Review points answered\nwithin 48 hours (%)")
    top.set_title("A  The same context helps only across the boundary", loc="left", x=-0.16)
    sns.despine(ax=top)
    top.grid(axis="y", color="#E8E8E8", linewidth=0.6, zorder=0)
    top.set_axisbelow(True)

    point = float(primary["estimate"]) * 100
    low, high = float(primary["ci_low"]) * 100, float(primary["ci_high"]) * 100
    bottom.barh([0], [high - low], left=low, height=0.30, color=PALE_TEAL,
                edgecolor=TEAL, linewidth=0.9, zorder=2)
    bottom.barh([0], [loo.max() - loo.min()], left=loo.min(), height=0.13,
                color=TEAL, alpha=0.45, linewidth=0, zorder=3)
    bottom.plot([point], [0], marker="D", markersize=7.0, markerfacecolor=TEAL,
                markeredgecolor="white", markeredgewidth=0.9, zorder=5)
    bottom.plot([raw], [0], marker="o", markersize=6.0, markerfacecolor="white",
                markeredgecolor=SLATE, markeredgewidth=1.2, zorder=5)
    bottom.axvline(0, color=INK, linewidth=1.1, zorder=4)
    bottom.text(point, 0.26, f"{point:+.1f} pp adjusted", ha="center", va="bottom",
                fontsize=8.4, color=TEAL, fontweight="bold")
    bottom.text(raw, -0.26, f"{raw:+.1f} raw", ha="center", va="top", fontsize=8.0,
                color=SLATE)
    bottom.text(0, -0.26, "no difference", ha="center", va="top", fontsize=8.0, color=SLATE)
    bottom.set_xlim(-3, 26)
    bottom.set_ylim(-0.65, 0.62)
    bottom.set_yticks([])
    bottom.set_xlabel("How much more the link helps across the boundary (pp)")
    bottom.set_title("B  One change minus the other", loc="left", x=-0.16)
    sns.despine(ax=bottom, left=True)
    bottom.grid(axis="x", color="#E8E8E8", linewidth=0.6, zorder=0)
    bottom.set_axisbelow(True)

    fig.subplots_adjust(left=0.155, right=0.70, top=0.935, bottom=0.115)
    fig.savefig(OUT / "fig6_seaborn_area.pdf")
    fig.savefig(OUT / "fig6_seaborn_area.png", dpi=300)
    plt.close(fig)
    print("wrote fig6_seaborn_area")


if __name__ == "__main__":
    figure3_diverging()
    figure6_area()
    print(json.dumps({"output": str(OUT)}, indent=2))
