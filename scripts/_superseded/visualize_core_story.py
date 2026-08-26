"""Build the three-step core result figure used in the paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


NAVY = "#2F5D7E"
BLUE = "#4B87B9"
ORANGE = "#DB7C26"
PURPLE = "#7B5AA6"
GREY = "#68737C"
LIGHT = "#E7EBEE"


def clean_axis(ax):
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#B8BEC2")
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#E0E4E6", lw=0.8)
    ax.set_axisbelow(True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-dir", type=Path, default=Path("outputs/tables"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    switching = pd.read_csv(args.table_dir / "rq2_switching_response.csv")
    distribution = pd.read_csv(args.table_dir / "transition_taxonomy_distribution.csv")
    recovery = pd.read_csv(args.table_dir / "transition_taxonomy_recovery.csv")

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "text.color": "#202428",
        "axes.labelcolor": "#30363B",
        "pdf.fonttype": 42,
    })
    fig = plt.figure(figsize=(7.2, 7.0))
    grid = fig.add_gridspec(2, 2, height_ratios=[0.90, 1.15], wspace=0.58,
                            hspace=0.55, left=0.12, right=0.965,
                            top=0.95, bottom=0.11)

    # A: an earlier non-integration is followed by more agent-brand change.
    ax = fig.add_subplot(grid[0, 0])
    panel_a = switching.sort_values("prior_merged", ascending=False).reset_index(drop=True)
    labels = ["Prior PR\nmerged", "Prior PR closed\nwithout merge"]
    values = 100 * panel_a["switch_rate"].to_numpy()
    ax.barh([0, 1], values, color=[NAVY, ORANGE], height=0.48)
    ax.set_yticks([0, 1], labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 37)
    ax.set_xticks([0, 10, 20, 30], ["0%", "10%", "20%", "30%"], fontsize=7.5)
    for y, value in enumerate(values):
        ax.text(value + 0.8, y, f"{value:.1f}%", va="center", fontsize=8.7,
                fontweight="bold")
    clean_axis(ax)
    ax.set_title("A  When does the agent change?", loc="left", fontsize=10.4,
                 fontweight="bold", pad=10)
    ax.text(0, 1.01, "Next outcome-known episode", transform=ax.transAxes,
            fontsize=7.6, color=GREY, va="bottom")

    # B: most observed brand changes also change the contributor.
    ax = fig.add_subplot(grid[0, 1])
    closed = distribution[~distribution["prior_merged"]]
    same_n = int(closed.loc[
        closed["transition_type"] == "brand_change_same_contributor", "n"
    ].iloc[0])
    different_n = int(closed.loc[
        closed["transition_type"] == "joint_reconfiguration", "n"
    ].iloc[0])
    total = same_n + different_n
    same_pct = 100 * same_n / total
    different_pct = 100 * different_n / total
    ax.barh([0], [same_pct], color=BLUE, height=0.36)
    ax.barh([0], [different_pct], left=[same_pct], color=PURPLE, height=0.36)
    ax.text(same_pct / 2, 0, f"{same_pct:.1f}%", ha="center", va="center",
            color="white", fontsize=9, fontweight="bold")
    ax.text(same_pct + different_pct / 2, 0, f"{different_pct:.1f}%", ha="center",
            va="center", color="white", fontsize=9, fontweight="bold")
    ax.text(same_pct / 2, -0.42, "same\ncontributor", ha="center", va="top",
            fontsize=8, color=BLUE, fontweight="bold")
    ax.text(same_pct + different_pct / 2, -0.42, "different contributor",
            ha="center", va="top", fontsize=8, color=PURPLE, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.85, 0.65)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("B  Who changes with the agent?", loc="left", fontsize=10.4,
                 fontweight="bold", pad=10)
    ax.text(0, 1.01, f"Among {total:,} changes after closed-unmerged PRs",
            transform=ax.transAxes, fontsize=7.6, color=GREY, va="bottom")

    # C: the four observable transition types have different outcomes.
    ax = fig.add_subplot(grid[1, :])
    order = [
        "brand_change_same_contributor",
        "joint_reconfiguration",
        "persistence",
        "contributor_change_stable_agent",
    ]
    labels = [
        "Same contributor;\nnew agent",
        "New contributor;\nnew agent",
        "Same contributor;\nsame agent",
        "New contributor;\nsame agent",
    ]
    colors = [BLUE, PURPLE, NAVY, ORANGE]
    data = recovery.set_index("transition_type").loc[order].reset_index()
    rates = 100 * data["merge_rate_30d"].to_numpy()
    lows = 100 * data["ci_low"].to_numpy()
    highs = 100 * data["ci_high"].to_numpy()
    y = np.arange(len(data))
    for yi, value, low, high, color in zip(y, rates, lows, highs, colors):
        ax.errorbar(value, yi, xerr=[[value - low], [high - value]], fmt="o",
                    color=color, ecolor=color, markersize=6, capsize=3, lw=1.4)
    ax.set_yticks(y, labels, fontsize=8.2)
    ax.invert_yaxis()
    ax.set_xlim(40, 82)
    ax.set_xticks([40, 50, 60, 70, 80], ["40%", "50%", "60%", "70%", "80%"],
                  fontsize=7.5)
    for yi, value, high, n in zip(y, rates, highs, data["n"]):
        ax.text(high + 0.7, yi, f"{value:.1f}%", va="center", fontsize=8.2,
                fontweight="bold")
    clean_axis(ax)
    ax.set_title("C  What happens next?", loc="left", fontsize=10.4,
                 fontweight="bold", pad=10)
    ax.text(0, 1.01, "30-day integration after a closed-unmerged PR",
            transform=ax.transAxes, fontsize=7.6, color=GREY, va="bottom")

    fig.text(
        0.12,
        0.025,
        "Points and intervals in panel C are repository-clustered estimates. The figure shows associations, not causal effects.",
        fontsize=8,
        color=GREY,
    )
    for suffix in ["pdf", "png"]:
        fig.savefig(args.output_dir / f"core_reconfiguration_story.{suffix}",
                    dpi=240, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
