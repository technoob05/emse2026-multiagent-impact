from __future__ import annotations

from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "outputs" / "matched_adoption"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "figures"
BLUE = "#3972B6"
ORANGE = "#D9822B"
INK = "#252A34"
GRID = "#D9DEE7"


def plot_series(
    axis: plt.Axes,
    frame: pd.DataFrame,
    color: str,
    label: str,
    linestyle: str,
) -> None:
    axis.fill_between(
        frame["event_month"],
        frame["log_pr_ci_low"],
        frame["log_pr_ci_high"],
        color=color,
        alpha=0.12,
        linewidth=0,
    )
    axis.plot(
        frame["event_month"],
        frame["log_pr_estimate"],
        color=color,
        marker="o",
        linewidth=2.1,
        linestyle=linestyle,
        label=label,
    )


if __name__ == "__main__":
    three = pd.read_csv(INPUT_DIR / "matched_adoption_event_summary.csv")
    four = pd.read_csv(INPUT_DIR / "matched_adoption_established_event.csv")
    fig, axis = plt.subplots(figsize=(8.2, 4.8))
    plot_series(axis, three, BLUE, "At least 3 months history (43 pairs)", "-")
    plot_series(axis, four, ORANGE, "At least 4 months history (23 pairs)", "--")
    axis.axhline(0, color=INK, linewidth=1.0)
    axis.axvline(-0.5, color=INK, linewidth=1.0, linestyle=":")
    axis.text(-0.42, axis.get_ylim()[1] * 0.88, "second brand enters", color=INK)
    axis.set_title("Matched activity around second-brand entry", loc="left", weight="bold")
    axis.set_xlabel("Months from entry")
    axis.set_ylabel("Matched difference in log(1 + PRs), relative to month -1")
    axis.set_xticks(sorted(set(three["event_month"]) | set(four["event_month"])))
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, loc="upper left")
    fig.text(
        0.01,
        0.01,
        textwrap.fill(
            "A positive pattern in the shorter-history cohort does not persist when repositories need longer prior history. "
            "Intervals are repository-pair bootstrap intervals; this is an observational diagnostic.",
            width=125,
        ),
        fontsize=9,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIR / "matched_adoption_history_sensitivity.png", dpi=220)
    fig.savefig(OUTPUT_DIR / "matched_adoption_history_sensitivity.pdf")
    plt.close(fig)
