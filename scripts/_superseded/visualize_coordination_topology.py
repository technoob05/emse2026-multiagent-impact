from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# Keep figure text searchable and avoid Type 3 fonts in the submission PDF.
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "coordination_topology"
BURST_INPUT = ROOT / "outputs" / "burst_topology"
MEMORY_INPUT = ROOT / "outputs" / "human_memory_bridge"
EDGE_INPUT = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "figures"

BLUE = "#3972B6"
ORANGE = "#D9822B"
GREEN = "#4C956C"
GRAY = "#7A8493"
LIGHT = "#E9EDF3"
INK = "#252A34"
RED = "#B44C43"


def save(fig: plt.Figure, stem: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(OUTPUT / f"{stem}.png", dpi=300, bbox_inches="tight")


def plot_participation_and_burst() -> None:
    funnel = pd.read_csv(INPUT / "participation_funnel.csv")
    burst = pd.read_csv(BURST_INPUT / "burst_topology_summary.csv")

    labels = [
        "Cross-product feedback\n(trigger cohort)",
        "Any later\nvisible action",
        "Exact reply to\nthe trigger",
        "Mapped different-product\nexact reply",
    ]
    shares = funnel["share_of_trigger_cohort"].to_numpy() * 100
    counts = funnel["prs"].astype(int).to_numpy()

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.0))
    fig.patch.set_facecolor("white")

    ax = axes[0]
    y = np.arange(len(labels))[::-1]
    colors = [BLUE, "#5D8EC7", ORANGE, RED]
    bars = ax.barh(y, shares, color=colors, height=0.62)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 106)
    ax.set_xlabel("Share of complete trigger cohort (%)")
    ax.set_title("A. Participation narrows to a connected edge", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, share, count in zip(bars, shares, counts, strict=True):
        ax.text(
            min(share + 1.4, 98),
            bar.get_y() + bar.get_height() / 2,
            f"{share:.1f}%  ({count:,})",
            va="center",
            fontsize=9.5,
            color=INK,
        )

    ax = axes[1]
    thresholds = [0, 1, 5, 10, 30]
    x = np.arange(len(thresholds))
    states = [
        ("user_account", "User account", GREEN, "-"),
        ("mapped_product", "Mapped product", BLUE, "-"),
        ("other_bot", "Other bot", ORANGE, "--"),
        ("branch_movement_untyped", "Branch movement", GRAY, ":"),
    ]
    for state, label, color, style in states:
        values = (
            burst[burst["first_post_burst_state"] == state]
            .set_index("burst_threshold_minutes")
            .loc[thresholds, "share_post_burst_actions"]
            .to_numpy()
            * 100
        )
        ax.plot(x, values, marker="o", linewidth=2.2, color=color, linestyle=style, label=label)
    ax.set_xticks(x, [str(value) for value in thresholds])
    ax.set_ylim(0, 66)
    ax.set_xlabel("Collapsed burst after trigger (minutes)")
    ax.set_ylabel("Share among PRs with an action left (%)")
    ax.set_title("B. A short burst changes the visible owner", loc="left", weight="bold")
    ax.grid(axis="y", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left", fontsize=8.8, ncol=2)
    ax.text(
        0.98,
        0.05,
        "At 5 min:\nuser account 53%\nmapped product 19%",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.2,
        color=INK,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": LIGHT},
    )

    fig.suptitle(
        "Participation is not yet a connected public handoff",
        x=0.06,
        ha="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.06,
        0.02,
        "Panel A: 8,608 PRs with a complete seven-day window. Panel B treats 0--30 minutes as a sensitivity range for one rapid automation burst;\n"
        "it does not claim that every early event belongs to the same run. At five minutes, 4,771 PRs still have a later action.",
        fontsize=8.6,
        color=GRAY,
    )
    fig.subplots_adjust(top=0.78, bottom=0.24, left=0.15, right=0.98, wspace=0.38)
    save(fig, "participation_burst_story")
    plt.close(fig)


def plot_boundary_and_memory() -> None:
    contrast = pd.read_csv(INPUT / "matched_visibility_contrasts.csv")
    contrast = contrast[
        (contrast["specification"] == "exact_author_user")
        & (contrast["outcome"] == "any_visible_followup")
    ].iloc[0]
    mediator = pd.read_csv(MEMORY_INPUT / "first_mediator_role_summary.csv").set_index(
        "account_role"
    )
    decisive = pd.read_csv(
        MEMORY_INPUT / "first_decisive_reviewer_role_summary.csv"
    ).set_index("account_role")

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.8))
    fig.patch.set_facecolor("white")

    ax = axes[0]
    rates = np.array([contrast["same_rate"], contrast["cross_rate"]]) * 100
    ax.plot(rates, [1, 0], color=GRAY, linewidth=2.2, zorder=1)
    ax.scatter(rates[0], 1, s=125, color=BLUE, zorder=2)
    ax.scatter(rates[1], 0, s=125, color=ORANGE, zorder=2)
    ax.set_yticks([0, 1], ["Cross-product", "Same-product"])
    ax.set_xlim(55, 88)
    ax.set_ylim(-0.65, 1.65)
    ax.set_xlabel("PRs with any later visible action (%)")
    ax.set_title("A. The product boundary is less visible", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for x_value, y_value in zip(rates, [1, 0], strict=True):
        ax.text(x_value + 0.9, y_value, f"{x_value:.0f}%", va="center", weight="bold", color=INK)
    difference = contrast["paired_difference"] * 100
    low = contrast["repository_cluster_bootstrap_ci_low"] * 100
    high = contrast["repository_cluster_bootstrap_ci_high"] * 100
    ax.text(
        0.02,
        0.05,
        f"Cross minus same: {difference:+.1f} pp\n95% repository bootstrap: {low:+.1f} to {high:+.1f}",
        transform=ax.transAxes,
        fontsize=9.2,
        color=INK,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": LIGHT},
    )

    ax = axes[1]
    labels = [
        "PR-author account\nis first user mediator",
        "Other user account\nis first user mediator",
        "User account owning the\nfirst decisive review",
    ]
    values = np.array(
        [
            mediator.loc["author_account", "prior_reviewer_share"],
            mediator.loc["other_user", "prior_reviewer_share"],
            decisive.loc["all_first_decisive_reviewers", "prior_reviewer_share"],
        ]
    ) * 100
    counts = [
        int(mediator.loc["author_account", "prs"]),
        int(mediator.loc["other_user", "prs"]),
        int(decisive.loc["all_first_decisive_reviewers", "prs"]),
    ]
    y = np.arange(len(labels))[::-1]
    bars = ax.barh(y, values, color=[GREEN, GREEN, BLUE], height=0.62)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 92)
    ax.set_xlabel("Accounts with a prior review in the repository (%)")
    ax.set_title("B. User bridges often have prior public review history", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value, count in zip(bars, values, counts, strict=True):
        ax.text(
            value + 1.1,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.0f}% (n={count:,})",
            va="center",
            fontsize=9,
            color=INK,
        )
    fig.suptitle(
        "The product boundary is quiet; familiar user accounts often bridge it",
        x=0.06,
        ha="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.06,
        0.02,
        f"Panel A: {int(contrast['pairs']):,} nearest-time pairs with the same repository, GitHub author account, author product, source, and month "
        f"({int(contrast['repositories']):,} repositories).\nPanel B: a prior review must be in the same repository, on a different PR, strictly before the trigger. "
        "Account history is observable; manual work and causal effects are not.",
        fontsize=8.4,
        color=GRAY,
    )
    fig.subplots_adjust(top=0.77, bottom=0.26, left=0.18, right=0.98, wspace=0.48)
    save(fig, "boundary_memory_story")
    plt.close(fig)


def plot_connected_signals() -> None:
    edge_rates = pd.read_csv(EDGE_INPUT / "denominators.csv")
    edge_rates = edge_rates[edge_rates["threshold_hours"] == 48].set_index(
        "exposure_group"
    )
    edge_model = pd.read_csv(EDGE_INPUT / "addressed_edge_clustered_lpm.csv")
    edge_model = edge_model[
        (edge_model["threshold_hours"] == 48)
        & (edge_model["specification"] == "A_pretrigger_only")
    ].iloc[0]
    route_model = pd.read_csv(INPUT / "route_direct_contrasts.csv")
    route_model = route_model[
        (route_model["specification"] == "pretrigger_adjusted")
        & (route_model["compared_route"] == "automation_then_human")
    ].iloc[0]

    rate_groups = [
        "no_exact_parent_reply_by_threshold",
        "exact_parent_reply_by_threshold",
    ]
    rate_labels = ["No exact reply", "Exact reply to\nthe trigger"]
    rates = edge_rates.loc[rate_groups, "later_merge_rate"].to_numpy() * 100
    counts = edge_rates.loc[rate_groups, "prs"].astype(int).to_numpy()

    comparison_labels = [
        "Exact addressed edge\nvs no exact edge",
        "Automation then user\nvs automation only",
    ]
    estimate = np.array([edge_model["estimate"], route_model["estimate"]]) * 100
    low = np.array([edge_model["ci_low"], route_model["ci_low"]]) * 100
    high = np.array([edge_model["ci_high"], route_model["ci_high"]]) * 100

    fig, axes = plt.subplots(
        1, 2, figsize=(12.2, 5.0), gridspec_kw={"width_ratios": [1.0, 1.0]}
    )
    fig.patch.set_facecolor("white")

    ax = axes[0]
    route_y = np.arange(2)[::-1]
    bars = ax.barh(route_y, rates, color=[GRAY, GREEN], height=0.58)
    ax.set_yticks(route_y, rate_labels)
    ax.set_xlim(0, 68)
    ax.set_xlabel("Merged from hour 48 to day 30 (%)")
    ax.set_title("A. An addressed edge marks a different later state", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, rate, count in zip(bars, rates, counts, strict=True):
        ax.text(
            rate + 1.0,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.0f}% (n={count:,})",
            va="center",
            fontsize=9,
            color=INK,
        )

    ax = axes[1]
    y = np.arange(len(comparison_labels))[::-1]
    ax.axvline(0, color=GRAY, linewidth=1.1)
    for x_value, low_value, high_value, y_value, color in zip(
        estimate, low, high, y, [GREEN, BLUE], strict=True
    ):
        ax.errorbar(
            x_value,
            y_value,
            xerr=[[x_value - low_value], [high_value - x_value]],
            fmt="o",
            color=color,
            ecolor=color,
            capsize=4,
            markersize=7,
            linewidth=2,
        )
    ax.set_yticks(y, comparison_labels)
    ax.set_xlim(-2, 31)
    ax.set_xlabel("Adjusted later-merge difference (percentage points)")
    ax.set_title("B. Two connected signals point the same way", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for x_value, y_value in zip(estimate, y, strict=True):
        ax.text(x_value + 1.0, y_value, f"{x_value:+.1f}", va="center", color=INK)

    fig.suptitle(
        "A connected public trace is linked to later integration",
        x=0.06,
        ha="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.06,
        0.02,
        "All PRs are still open at 48 hours and have 30 days of follow-up. The exact-edge comparison uses 1,067 inline-trigger PRs; "
        "the ownership-route comparison uses 1,733 PRs.\nModels adjust for measured pre-trigger context and cluster intervals by repository. "
        "The two rows use different cohorts and references; neither is a causal effect or a semantic resolution rate.",
        fontsize=8.6,
        color=GRAY,
    )
    fig.subplots_adjust(top=0.78, bottom=0.24, left=0.17, right=0.98, wspace=0.48)
    save(fig, "hybrid_relay_story")
    plt.close(fig)


if __name__ == "__main__":
    plot_participation_and_burst()
    plot_boundary_and_memory()
    plot_connected_signals()
