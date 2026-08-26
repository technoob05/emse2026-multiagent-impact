from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "outputs" / "cross_agent_review"
OWNERSHIP_DIR = PROJECT_ROOT / "outputs" / "response_ownership"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "figures"

BLUE = "#3972B6"
ORANGE = "#D9822B"
GREEN = "#4C956C"
GOLD = "#C9A227"
GRAY = "#7A8493"
LIGHT = "#E9EDF3"
INK = "#252A34"


def save_figure(fig: plt.Figure, stem: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIR / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUTPUT_DIR / f"{stem}.pdf", bbox_inches="tight")


def plot_response_story() -> None:
    chains = pl.read_parquet(INPUT_DIR / "cross_feedback_response_chains.parquet")
    events = pl.read_parquet(INPUT_DIR / "cross_feedback_response_events.parquet")
    n_prs = chains.height
    channel_rates = pd.Series(
        {
            "Later review": float((chains["subsequent_reviews"] > 0).mean()),
            "Later PR comment": float(
                (chains["subsequent_pr_comments"] > 0).mean()
            ),
            "Visible force-push": float((chains["force_push_events"] > 0).mean()),
            "Direct thread reply": float(
                (chains["direct_inline_replies"] > 0).mean()
            ),
        }
    ).sort_values()
    replies = events.filter(pl.col("response_source") == "direct_inline_reply")
    reply_type = replies.group_by("response_user_type").len()
    human_events = int(
        reply_type.filter(pl.col("response_user_type") == "User")["len"].sum()
    )
    total_reply_events = replies.height
    human_share = human_events / total_reply_events

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.5), gridspec_kw={"width_ratios": [1.25, 1]})
    fig.patch.set_facecolor("white")

    ax = axes[0]
    colors = [GOLD, ORANGE, GREEN, BLUE]
    bars = ax.barh(channel_rates.index, channel_rates.values * 100, color=colors)
    ax.set_xlim(0, 70)
    ax.set_xlabel("Share of PRs (%)")
    ax.set_title("A. What happens after cross-product feedback?", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, channel_rates.values, strict=True):
        ax.text(
            value * 100 + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.0%}",
            va="center",
            color=INK,
            fontsize=10,
        )
    ax.text(
        0,
        -0.24,
        f"{n_prs:,} PRs with a complete 7-day window. Channels can overlap.",
        transform=ax.transAxes,
        fontsize=9,
        color=GRAY,
    )

    ax = axes[1]
    shares = [human_share * 100, (1 - human_share) * 100]
    bars = ax.bar(
        ["User accounts", "Bot accounts"],
        shares,
        color=[ORANGE, BLUE],
        width=0.62,
    )
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of direct-reply events (%)")
    ax.set_title("B. Who writes the direct replies?", loc="left", weight="bold")
    ax.grid(axis="y", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, shares, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2.5,
            f"{value:.0f}%",
            ha="center",
            weight="bold",
            color=INK,
        )
    ax.text(
        0,
        -0.24,
        f"{total_reply_events:,} reply events; account type comes from GitHub.",
        transform=ax.transAxes,
        fontsize=9,
        color=GRAY,
    )

    fig.suptitle(
        "Cross-product feedback usually enters a hybrid human-agent workflow",
        x=0.06,
        ha="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    fig.subplots_adjust(top=0.79, bottom=0.25, left=0.12, right=0.98, wspace=0.42)
    save_figure(fig, "cross_feedback_response_story")
    plt.close(fig)


def plot_landmark_story() -> None:
    summary = pd.read_csv(INPUT_DIR / "feedback_48h_landmark_summary.csv")
    labels = {
        "visible_code_movement": "Visible code\nmovement",
        "human_mediated": "Human-mediated\nresponse",
        "other_activity": "Other\nactivity",
        "agent_only_continuation": "Agent-only\ncontinuation",
        "no_observed_response": "No observed\nresponse",
    }
    order = list(labels)
    summary["order"] = summary["early_loop_shape"].map(
        {value: index for index, value in enumerate(order)}
    )
    summary = summary.sort_values("order")
    colors = [GREEN, ORANGE, GOLD, BLUE, GRAY]

    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    bars = ax.bar(
        [labels[value] for value in summary["early_loop_shape"]],
        summary["later_merge_rate"] * 100,
        color=colors,
        width=0.7,
    )
    ax.set_ylim(0, 70)
    ax.set_ylabel("Merged from hour 48 to day 30 (%)")
    ax.set_title(
        "Visible loop shape marks different paths to later integration",
        loc="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    ax.grid(axis="y", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, rate, count in zip(
        bars, summary["later_merge_rate"], summary["prs"], strict=True
    ):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            rate * 100 + 1.5,
            f"{rate:.0%}\n(n={count:,})",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK,
        )
    ax.text(
        0,
        -0.24,
        "PRs are still open at 48 hours and have 30 days of follow-up. "
        "Rates are descriptive, not causal.",
        transform=ax.transAxes,
        fontsize=9,
        color=GRAY,
    )
    fig.subplots_adjust(bottom=0.28, left=0.1, right=0.98, top=0.86)
    save_figure(fig, "feedback_loop_48h_landmark")
    plt.close(fig)


def plot_adjusted_landmark_forest() -> None:
    models = pd.read_csv(INPUT_DIR / "feedback_48h_landmark_models.csv")
    # Saturated repository fixed effects can produce an indefinite clustered
    # covariance matrix when many repositories are small. Plot the prespecified
    # covariate-adjusted model with repository-clustered intervals instead.
    models = models[models["specification"] == "repo_clustered_controls"].copy()
    labels = {
        "visible_code_movement": "Visible code movement",
        "human_mediated": "Human-mediated response",
        "agent_only_continuation": "Agent-only continuation",
        "other_activity": "Other activity",
    }
    models["shape"] = models["term"].str.extract(r"T\.([^\]]+)\]")[0]
    models = models[models["shape"].isin(labels)].copy()
    order = list(labels)
    models["order"] = models["shape"].map(
        {value: index for index, value in enumerate(order)}
    )
    models = models.sort_values("order", ascending=False)
    estimate = models["estimate"].to_numpy() * 100
    low = models["ci_low"].to_numpy() * 100
    high = models["ci_high"].to_numpy() * 100
    y = range(len(models))

    fig, ax = plt.subplots(figsize=(8.8, 4.5))
    ax.axvline(0, color=GRAY, linewidth=1.2)
    ax.errorbar(
        estimate,
        list(y),
        xerr=[estimate - low, high - estimate],
        fmt="o",
        color=BLUE,
        ecolor=BLUE,
        capsize=4,
        markersize=7,
        linewidth=2,
    )
    ax.set_yticks(list(y), [labels[value] for value in models["shape"]])
    ax.set_xlabel("Adjusted difference in later merge (percentage points)")
    ax.set_title(
        "Human mediation remains linked to later integration within repositories",
        loc="left",
        fontsize=13,
        weight="bold",
        color=INK,
    )
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for x_value, y_value in zip(estimate, y, strict=True):
        ax.text(x_value + 1.2, y_value, f"{x_value:+.0f} pp", va="center", color=INK)
    ax.text(
        0,
        -0.28,
        "Reference: no observed response. PRs are open at 48 hours. The model controls "
        "for author, reviewer, channel, and month; intervals cluster by repository.",
        transform=ax.transAxes,
        fontsize=8.8,
        color=GRAY,
    )
    fig.subplots_adjust(left=0.28, bottom=0.28, right=0.96, top=0.84)
    save_figure(fig, "feedback_loop_adjusted_landmark")
    plt.close(fig)


def plot_ownership_story() -> None:
    first = pd.read_csv(OWNERSHIP_DIR / "first_owner_summary.csv").set_index(
        "first_owner"
    )
    route = pd.read_csv(OWNERSHIP_DIR / "ownership_route_48h_summary.csv").set_index(
        "ownership_route_48h"
    )
    models = pd.read_csv(OWNERSHIP_DIR / "ownership_route_clustered_model.csv")

    def count(*labels: str) -> int:
        return int(first.reindex(labels)["prs"].fillna(0).sum())

    owner_counts = pd.Series(
        {
            "No visible action": count("no_observed_action"),
            "Human account": count("author_human", "other_human"),
            "Mapped agent product": count(
                "author_agent", "triggering_reviewer", "other_agent"
            ),
            "Other bot": count("other_bot"),
            "Unknown / untyped": count(
                "unknown", "author_account_untyped", "branch_actor_untyped",
                "simultaneous_owners",
            ),
        }
    )
    total = owner_counts.sum()
    owner_share = (owner_counts / total * 100).sort_values()

    route_labels = {
        "automation_no_human": "Automation only",
        "human_first": "Human first",
        "automation_then_human": "Automation then human",
    }
    models["route"] = models["term"].str.extract(r"T\.([^\]]+)\]")[0]
    models = models[models["route"].isin(route_labels)].copy()
    models["order"] = models["route"].map(
        {value: index for index, value in enumerate(route_labels)}
    )
    models = models.sort_values("order", ascending=False)
    estimates = models["estimate"].to_numpy() * 100
    low = models["ci_low"].to_numpy() * 100
    high = models["ci_high"].to_numpy() * 100

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.2), gridspec_kw={"width_ratios": [1.05, 1]})
    ax = axes[0]
    palette = {
        "No visible action": GRAY,
        "Human account": ORANGE,
        "Mapped agent product": BLUE,
        "Other bot": GOLD,
        "Unknown / untyped": "#B9C1CC",
    }
    bars = ax.barh(
        owner_share.index,
        owner_share.values,
        color=[palette[label] for label in owner_share.index],
    )
    ax.set_xlim(0, 40)
    ax.set_xlabel("Share of PRs (%)")
    ax.set_title("A. Who owns the first visible action?", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, owner_share.values, strict=True):
        ax.text(value + 0.7, bar.get_y() + bar.get_height() / 2, f"{value:.0f}%", va="center")
    ax.text(
        0,
        -0.30,
        f"{total:,} PRs; categories are mutually exclusive. Unknown identities stay unknown.",
        transform=ax.transAxes,
        fontsize=8.7,
        color=GRAY,
    )

    ax = axes[1]
    y = range(len(models))
    ax.axvline(0, color=GRAY, linewidth=1.1)
    ax.errorbar(
        estimates,
        list(y),
        xerr=[estimates - low, high - estimates],
        fmt="o",
        color=BLUE,
        ecolor=BLUE,
        capsize=4,
        markersize=7,
        linewidth=2,
    )
    ax.set_yticks(
        list(y),
        [
            f"{route_labels[value]}\n(n={int(route.loc[value, 'prs']):,})"
            for value in models["route"]
        ],
    )
    ax.set_xlabel("Adjusted later-merge difference (percentage points)", labelpad=8)
    ax.set_title("B. What follows the 48-hour route?", loc="left", weight="bold")
    ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    ax.set_axisbelow(True)
    for value, y_value in zip(estimates, y, strict=True):
        ax.text(value + 0.8, y_value, f"{value:+.0f} pp", va="center", color=INK)
    ax.text(
        0,
        -0.34,
        "Reference: no visible action (n=659). Controls cover products, channel, and month;\n"
        "intervals cluster by repository. Associations are not causal effects.",
        transform=ax.transAxes,
        fontsize=8.7,
        color=GRAY,
    )

    fig.suptitle(
        "Visible ownership often moves beyond the two agent products",
        x=0.06,
        ha="left",
        fontsize=14,
        weight="bold",
        color=INK,
    )
    fig.subplots_adjust(top=0.79, bottom=0.32, left=0.12, right=0.98, wspace=0.60)
    save_figure(fig, "feedback_response_ownership_story")
    plt.close(fig)


if __name__ == "__main__":
    plot_response_story()
    plot_landmark_story()
    plot_adjusted_landmark_forest()
    plot_ownership_story()
