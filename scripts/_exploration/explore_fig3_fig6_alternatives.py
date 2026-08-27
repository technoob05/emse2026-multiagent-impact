"""Throwaway exploration: alternative chart forms for Figure 3A and Figure 6.

Renders PNGs into build/qa/explore/. Imports the house style (372 pt width,
Paul Tol palette, 8 pt floor, assert_layout gate) from the production module
without modifying it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "figures"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import visualize_manuscript_figures as house  # noqa: E402

INK = house.INK
BLUE = house.GOLD_INK
ORANGE = house.BRICK
TEAL = house.STEEL
SLATE = house.SLATE
MID = house.MID
GRID = house.GRID
PALE_BLUE = house.PALE_GOLD
PALE_TEAL = house.PALE_STEEL
PALE_ORANGE = house.PALE_BRICK
WHITE = house.WHITE
minus = house.minus
Layout = house.Layout
panel_title = house.panel_title
clean_axis = house.clean_axis
category_axis = house.category_axis

EXPLORE = ROOT / "build" / "qa" / "explore"
REPORT: list[str] = []


def save_explore(fig: plt.Figure, stem: str) -> None:
    EXPLORE.mkdir(parents=True, exist_ok=True)
    status = "GATE PASS"
    try:
        house.assert_layout(fig, stem)
    except AssertionError as error:
        status = f"GATE FAIL: {error}"
    fig.savefig(EXPLORE / f"{stem}.png", dpi=300)
    plt.close(fig)
    REPORT.append(f"{stem}: {status}")
    print(f"{stem}: {status}")


# ---------------------------------------------------------------------------
# Figure 3 data
# ---------------------------------------------------------------------------

OUTCOMES = (
    ("any_visible_followup", "Anyone does anything"),
    ("later_pr_comment", "Someone comments"),
    ("new_review_round", "A new review round"),
    ("exact_trigger_reply", "The point gets a reply*"),
    ("visible_force_push", "The branch is rewritten"),
    ("merge_within_7d", "Merged within a week"),
)
RESTRICTED_OUTCOME = "exact_trigger_reply"


def load_fig3():
    contrasts = house.read_csv(
        house.TOPOLOGY / "matched_visibility_contrasts.csv",
        (
            "specification",
            "outcome",
            "pairs",
            "repositories",
            "cross_rate",
            "same_rate",
            "paired_difference",
            "repository_cluster_bootstrap_ci_low",
            "repository_cluster_bootstrap_ci_high",
        ),
    )
    primary = contrasts[contrasts["specification"] == "exact_author_user"]
    restricted = house.read_csv(
        house.THREAD_POSITION / "restricted_visibility_contrasts.csv",
        (
            "specification",
            "population",
            "outcome",
            "pairs",
            "repositories",
            "cross_rate",
            "same_rate",
            "paired_difference",
            "repository_cluster_bootstrap_ci_low",
            "repository_cluster_bootstrap_ci_high",
        ),
    )

    def row_for(key: str):
        if key == RESTRICTED_OUTCOME:
            return house.exactly_one(
                restricted,
                specification="exact_author_user",
                population="both_triggers_open_their_own_thread",
                outcome=key,
            )
        return house.exactly_one(primary, outcome=key)

    records = []
    for key, label in OUTCOMES:
        row = row_for(key)
        low = float(row["repository_cluster_bootstrap_ci_low"]) * 100
        high = float(row["repository_cluster_bootstrap_ci_high"]) * 100
        records.append(
            {
                "key": key,
                "label": label,
                "cross": float(row["cross_rate"]) * 100,
                "same": float(row["same_rate"]) * 100,
                "diff": float(row["paired_difference"]) * 100,
                "low": low,
                "high": high,
                "moved": low > 0 or high < 0,
                "pairs": int(row["pairs"]),
                "repositories": int(row["repositories"]),
            }
        )
    base = house.exactly_one(primary, outcome="any_visible_followup")
    narrow = row_for(RESTRICTED_OUTCOME)
    meta = {
        "pairs": int(base["pairs"]),
        "repositories": int(base["repositories"]),
        "narrow_pairs": int(narrow["pairs"]),
    }
    return records, meta


def footnote(ax, meta, y, x=0.5):
    ax.text(
        x,
        y,
        f"{meta['pairs']:,} matched pairs in {meta['repositories']} repositories"
        + chr(10)
        + f"*{meta['narrow_pairs']:,} pairs where a reply is possible on both sides",
        ha="left",
        va="center",
        fontsize=8.0,
        color=SLATE,
    )


# --- A1: current dumbbell, reproduced for a fair comparison ----------------


def fig3_a1_dumbbell(records, meta):
    fig = house.new_figure(3.05)
    ax = fig.add_axes((0.360, 0.170, 0.495, 0.735))

    GROUP_GAP = 0.9
    positions, moved = [], []
    cursor = float(len(records)) + GROUP_GAP
    for record in records:
        if moved and record["moved"] != moved[-1]:
            cursor -= GROUP_GAP
        positions.append(cursor)
        moved.append(record["moved"])
        cursor -= 1.0

    for position, record in zip(positions, records, strict=True):
        separated = record["moved"]
        ax.plot(
            [record["cross"], record["same"]],
            [position, position],
            color=SLATE if separated else MID,
            linewidth=1.7 if separated else 1.1,
            solid_capstyle="round",
            zorder=1,
        )
        ax.plot([record["cross"]], [position], marker="o",
                markersize=5.2 if separated else 4.4,
                markerfacecolor=ORANGE, markeredgecolor=ORANGE, zorder=3)
        ax.plot([record["same"]], [position], marker="o",
                markersize=5.2 if separated else 4.4,
                markerfacecolor="white", markeredgecolor=BLUE,
                markeredgewidth=1.3, zorder=3)
        ax.text(
            101.5,
            position,
            minus(f"{record['diff']:+.1f}") + " pp",
            ha="left",
            va="center",
            fontsize=8.1,
            color=INK if separated else SLATE,
            fontweight="bold" if separated else "normal",
        )

    ax.set_yticks(positions)
    ax.set_yticklabels([r["label"] for r in records], fontsize=8.2)
    for tick, separated in zip(ax.get_yticklabels(), moved, strict=True):
        tick.set_color(INK if separated else SLATE)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(min(positions) - 1.75, max(positions) + 0.6)
    ax.set_xlabel("Matched pairs where it happened (%)")
    panel_title(ax, "A1", "Current form: dumbbells")
    clean_axis(ax, "x")
    first_null = moved.index(False)
    divider = (positions[first_null - 1] + positions[first_null]) / 2.0
    ax.axhline(divider, color=MID, linewidth=0.7, linestyle=(0, (3, 3)), zorder=0)
    footnote(ax, meta, min(positions) - 1.05)
    save_explore(fig, "fig3A_alt1_dumbbell_current")


# --- A2: paired slope chart, one line per outcome --------------------------


def fig3_a2_slope(records, meta):
    fig = house.new_figure(3.05)
    ax = fig.add_axes((0.255, 0.170, 0.290, 0.720))

    order = sorted(range(len(records)), key=lambda i: records[i]["cross"])
    left_slots = _dodge([records[i]["cross"] for i in order], 4.6)
    right_slots = _dodge([records[i]["same"] for i in order], 4.6)

    for slot, index in enumerate(order):
        record = records[index]
        separated = record["moved"]
        ax.plot(
            [0, 1],
            [record["cross"], record["same"]],
            color=TEAL if separated else MID,
            linewidth=2.0 if separated else 1.1,
            zorder=3 if separated else 2,
            clip_on=False,
        )
        for x, value, face in ((0, record["cross"], ORANGE), (1, record["same"], WHITE)):
            ax.plot([x], [value], marker="o", markersize=4.6 if separated else 3.6,
                    markerfacecolor=face if face != WHITE else "white",
                    markeredgecolor=ORANGE if x == 0 else BLUE,
                    markeredgewidth=1.2, zorder=4, clip_on=False)
        ax.text(
            1.06,
            right_slots[slot],
            f"{record['same']:.0f}  {record['label']}",
            ha="left",
            va="center",
            fontsize=8.1,
            color=INK if separated else SLATE,
            fontweight="bold" if separated else "normal",
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 92)
    ax.set_xticks([0, 1], ["Cross-product", "Same-product"])
    ax.set_yticks([0, 25, 50, 75])
    ax.set_ylabel("Matched pairs where\nit happened (%)")
    panel_title(ax, "A2", "Paired slopes, one line per outcome")
    clean_axis(ax, "y")
    footnote(ax, meta, -14.0, x=-0.10)
    save_explore(fig, "fig3A_alt2_slope")


def _dodge(values, gap):
    placed = []
    previous = -np.inf
    for value in values:
        spot = max(value, previous + gap)
        placed.append(spot)
        previous = spot
    return placed


# --- A3: difference only, against zero, in the paper's order ---------------


def fig3_a3_difference(records, meta):
    fig = house.new_figure(2.95)
    ax = fig.add_axes((0.360, 0.185, 0.590, 0.715))
    positions = np.arange(len(records))[::-1].astype(float)

    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=1)
    for position, record in zip(positions, records, strict=True):
        separated = record["moved"]
        colour = ORANGE if separated else SLATE
        ax.plot([record["low"], record["high"]], [position, position],
                color=colour, linewidth=1.9 if separated else 1.2, zorder=3,
                solid_capstyle="butt")
        for edge in (record["low"], record["high"]):
            ax.plot([edge, edge], [position - 0.16, position + 0.16],
                    color=colour, linewidth=1.1, zorder=3)
        ax.plot([record["diff"]], [position], marker="o",
                markersize=6.0 if separated else 4.4,
                markerfacecolor=colour, markeredgecolor=WHITE,
                markeredgewidth=0.7, zorder=4)

    ax.set_yticks(positions)
    ax.set_yticklabels([r["label"] for r in records], fontsize=8.2)
    for tick, record in zip(ax.get_yticklabels(), records, strict=True):
        tick.set_color(INK if record["moved"] else SLATE)
    ax.set_xlim(-36, 18)
    ax.set_xticks([-30, -20, -10, 0, 10])
    ax.set_ylim(-1.55, len(records) - 0.4)
    ax.set_xlabel("Cross-product minus same-product (pp, 95% CI)")
    panel_title(ax, "A3", "Only the gap, against zero")
    clean_axis(ax, "x")
    ax.text(-1.6, len(records) - 0.55, "less on the cross-product side",
            ha="right", va="center", fontsize=8.0, color=SLATE)
    ax.text(1.6, len(records) - 0.55, "more", ha="left", va="center",
            fontsize=8.0, color=SLATE)
    footnote(ax, meta, -1.05, x=-35.0)
    save_explore(fig, "fig3A_alt3_difference_forest")


# --- A4: small-multiple grid of six mini paired bars ------------------------


def fig3_a4_grid(records, meta):
    fig = house.new_figure(3.60)
    left, right, top, bottom = 0.090, 0.985, 0.845, 0.135
    col_gap, row_gap = 0.075, 0.185
    width = (right - left - 2 * col_gap) / 3.0
    height = (top - bottom - row_gap) / 2.0

    for index, record in enumerate(records):
        column, row = index % 3, index // 3
        rect = (
            left + column * (width + col_gap),
            top - (row + 1) * height - row * row_gap,
            width,
            height,
        )
        ax = fig.add_axes(rect)
        separated = record["moved"]
        if separated:
            ax.set_facecolor("#F4F0E2")
        ax.bar([0], [record["cross"]], width=0.62, color=PALE_ORANGE,
               edgecolor=ORANGE, linewidth=0.9, zorder=2)
        ax.bar([1], [record["same"]], width=0.62, color=PALE_BLUE,
               edgecolor=BLUE, linewidth=0.9, zorder=2)
        for x, value in ((0, record["cross"]), (1, record["same"])):
            ax.text(x, value + 2.5, f"{value:.0f}", ha="center", va="bottom",
                    fontsize=8.0, color=INK)
        ax.set_xlim(-0.62, 1.62)
        ax.set_ylim(0, 100)
        ax.set_xticks([0, 1], ["cross", "same"], fontsize=8.0)
        if column == 0:
            ax.set_yticks([0, 50, 100])
        else:
            ax.set_yticks([0, 50, 100], ["", "", ""])
        ax.set_title(
            record["label"].replace("*", "") + chr(10)
            + minus(f"{record['diff']:+.1f}") + (" pp*" if separated else " pp"),
            loc="center",
            pad=3.0,
            fontsize=8.2,
            fontweight="bold" if separated else "normal",
            color=INK if separated else SLATE,
        )
        clean_axis(ax, "y")

    fig.text(0.020, 0.962, "A4  Six small multiples, cross vs same (%)",
             ha="left", va="center", fontsize=9.6, fontweight="bold", color=INK)
    fig.text(0.020, 0.048,
             f"*95% CI clears zero.  {meta['pairs']:,} matched pairs in "
             f"{meta['repositories']} repositories;" + chr(10)
             + f"the reply outcome uses {meta['narrow_pairs']:,} pairs.",
             ha="left", va="center", fontsize=8.0, color=SLATE)
    save_explore(fig, "fig3A_alt4_small_multiples")


# --- A5: differences ordered by magnitude, whiskers -------------------------


def fig3_a5_ranked(records, meta):
    ranked = sorted(records, key=lambda r: abs(r["diff"]))
    fig = house.new_figure(2.95)
    ax = fig.add_axes((0.360, 0.185, 0.590, 0.700))
    positions = np.arange(len(ranked)).astype(float)

    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=1)
    for position, record in zip(positions, ranked, strict=True):
        separated = record["moved"]
        colour = ORANGE if separated else MID
        ax.plot([0.0, record["diff"]], [position, position], color=GRID,
                linewidth=1.6, zorder=1)
        ax.plot([record["low"], record["high"]], [position, position],
                color=colour, linewidth=1.8 if separated else 1.2, zorder=3)
        for edge in (record["low"], record["high"]):
            ax.plot([edge, edge], [position - 0.15, position + 0.15],
                    color=colour, linewidth=1.0, zorder=3)
        ax.plot([record["diff"]], [position], marker="o",
                markersize=6.2 if separated else 4.4,
                markerfacecolor=ORANGE if separated else SLATE,
                markeredgecolor=WHITE, markeredgewidth=0.7, zorder=4)
        ax.text(record["high"] + 1.4, position,
                minus(f"{record['diff']:+.1f}"),
                ha="left", va="center", fontsize=8.0,
                color=INK if separated else SLATE,
                fontweight="bold" if separated else "normal")

    ax.set_yticks(positions)
    ax.set_yticklabels([r["label"] for r in ranked], fontsize=8.2)
    for tick, record in zip(ax.get_yticklabels(), ranked, strict=True):
        tick.set_color(INK if record["moved"] else SLATE)
    ax.set_xlim(-36, 22)
    ax.set_xticks([-30, -20, -10, 0, 10, 20])
    ax.set_ylim(-1.6, len(ranked) - 0.4)
    ax.set_xlabel("Cross-product minus same-product (pp, 95% CI)")
    panel_title(ax, "A5", "Ranked by size of the gap")
    clean_axis(ax, "x")
    footnote(ax, meta, -1.1, x=-35.0)
    save_explore(fig, "fig3A_alt5_ranked_dots")


# --- A6: levels and gap side by side, shared rows ---------------------------


def fig3_a6_levels_plus_gap(records, meta):
    fig = house.new_figure(3.20)
    top, bottom = 0.855, 0.190
    left_ax = fig.add_axes((0.330, bottom, 0.300, top - bottom))
    right_ax = fig.add_axes((0.700, bottom, 0.275, top - bottom))
    positions = np.arange(len(records))[::-1].astype(float)

    for position, record in zip(positions, records, strict=True):
        separated = record["moved"]
        left_ax.plot([record["cross"], record["same"]], [position, position],
                     color=SLATE if separated else MID,
                     linewidth=1.8 if separated else 1.1, zorder=2,
                     solid_capstyle="round")
        left_ax.plot([record["cross"]], [position], marker="o",
                     markersize=5.0 if separated else 4.0,
                     markerfacecolor=ORANGE, markeredgecolor=ORANGE, zorder=3)
        left_ax.plot([record["same"]], [position], marker="o",
                     markersize=5.0 if separated else 4.0,
                     markerfacecolor="white", markeredgecolor=BLUE,
                     markeredgewidth=1.2, zorder=3)

        colour = ORANGE if separated else SLATE
        right_ax.plot([record["low"], record["high"]], [position, position],
                      color=colour, linewidth=1.8 if separated else 1.1, zorder=3)
        for edge in (record["low"], record["high"]):
            right_ax.plot([edge, edge], [position - 0.15, position + 0.15],
                          color=colour, linewidth=1.0, zorder=3)
        right_ax.plot([record["diff"]], [position], marker="o",
                      markersize=5.8 if separated else 4.2,
                      markerfacecolor=colour, markeredgecolor=WHITE,
                      markeredgewidth=0.7, zorder=4)

    left_ax.set_yticks(positions)
    left_ax.set_yticklabels([r["label"] for r in records], fontsize=8.2)
    for tick, record in zip(left_ax.get_yticklabels(), records, strict=True):
        tick.set_color(INK if record["moved"] else SLATE)
    left_ax.set_xlim(0, 100)
    left_ax.set_xticks([0, 50, 100])
    left_ax.set_ylim(-1.6, len(records) - 0.4)
    left_ax.set_xlabel("Happened (%)")
    panel_title(left_ax, "A6", "How often")
    clean_axis(left_ax, "x")

    right_ax.axvline(0.0, color=INK, linewidth=1.0, zorder=1)
    right_ax.set_yticks(positions, ["" for _ in positions])
    right_ax.set_xlim(-36, 18)
    right_ax.set_xticks([-30, -15, 0, 15])
    right_ax.set_ylim(-1.6, len(records) - 0.4)
    right_ax.set_xlabel("Gap (pp, 95% CI)")
    panel_title(right_ax, "", "Cross minus same")
    clean_axis(right_ax, "x")
    right_ax.spines["left"].set_visible(False)
    right_ax.tick_params(axis="y", length=0)

    left_ax.set_ylim(-0.9, len(records) - 0.4)
    right_ax.set_ylim(-0.9, len(records) - 0.4)
    fig.text(
        0.020,
        0.058,
        f"{meta['pairs']:,} matched pairs in {meta['repositories']} repositories"
        + chr(10)
        + f"*{meta['narrow_pairs']:,} pairs where a reply is possible on both sides",
        ha="left", va="center", fontsize=8.0, color=SLATE,
    )
    save_explore(fig, "fig3A_alt6_levels_and_gap")


# ---------------------------------------------------------------------------
# Figure 6 data
# ---------------------------------------------------------------------------


def load_fig6():
    cells = house.read_csv(
        house.CONTEXT / "answer_rate_cells.csv",
        ("reviewer_relation", "body_issue_link", "prs", "answered_rate", "population"),
    )
    cells = cells[cells["population"] == "thread-root triggers"]
    models = house.read_csv(
        house.CONTEXT / "interaction_models.csv",
        ("specification", "estimate", "ci_low", "ci_high"),
    )
    loo = house.read_csv(house.CONTEXT / "leave_one_repository_out.csv", ("estimate",))
    shuffle = house.read_csv(
        house.CONTEXT / "label_shuffle_test.csv", ("p_value_two_sided",)
    ).iloc[0]
    primary = house.exactly_one(
        models, specification="Thread-root triggers, repository and month FE"
    )

    data = {}
    for relation in ("cross_product", "same_product"):
        values, counts = [], []
        for link in (False, True):
            row = house.exactly_one(
                cells, reviewer_relation=relation, body_issue_link=link
            )
            values.append(float(row["answered_rate"]) * 100)
            counts.append(int(row["prs"]))
        data[relation] = {"values": values, "counts": counts,
                          "change": values[1] - values[0]}
    data["point"] = float(primary["estimate"]) * 100
    data["low"] = float(primary["ci_low"]) * 100
    data["high"] = float(primary["ci_high"]) * 100
    data["raw"] = data["cross_product"]["change"] - data["same_product"]["change"]
    data["loo"] = loo["estimate"].to_numpy() * 100
    data["p"] = float(shuffle["p_value_two_sided"])
    return data


def did_strip(ax, data, letter="B", title="One change minus the other"):
    ax.axvline(0.0, color=SLATE, linewidth=0.9, zorder=1)
    ax.plot([data["loo"].min(), data["loo"].max()], [0, 0], color=PALE_TEAL,
            linewidth=7.0, solid_capstyle="butt", zorder=2)
    ax.plot([data["low"], data["high"]], [0, 0], color=TEAL, linewidth=1.8, zorder=3)
    for edge in (data["low"], data["high"]):
        ax.plot([edge, edge], [-0.16, 0.16], color=TEAL, linewidth=1.3, zorder=3)
    ax.plot([data["point"]], [0], marker="o", markersize=6.2,
            markerfacecolor=TEAL, markeredgecolor=WHITE, markeredgewidth=0.7,
            zorder=4)
    ax.text(data["point"], 0.42, minus(f"{data['point']:+.1f} pp"), ha="center",
            va="bottom", fontsize=8.4, fontweight="bold", color=TEAL)
    ax.text(0.0, -0.52, "no difference", ha="center", va="top", fontsize=8.0,
            color=SLATE)
    ax.plot([data["raw"]], [0], marker="o", markersize=5.4,
            markerfacecolor="white", markeredgecolor=TEAL, markeredgewidth=1.2,
            zorder=4)
    ax.text(data["raw"], -0.42, minus(f"{data['raw']:+.1f}") + " raw", ha="center",
            va="top", fontsize=8.0, color=SLATE)
    ax.set_xlim(-4.0, 26.0)
    ax.set_ylim(-1.0, 1.0)
    ax.set_yticks([])
    ax.set_xlabel("How much more the link helps across the boundary (pp)")
    panel_title(ax, letter, title)
    clean_axis(ax, "x")
    ax.spines["left"].set_visible(False)


SERIES = (
    ("cross_product", "A different product\nis reviewing", TEAL, "o", "-"),
    ("same_product", "The same product\nis reviewing", SLATE, "s", (0, (4, 2))),
)


def draw_slopes(ax, data, with_counts=True):
    rates = {key: data[key]["values"] for key, *_ in SERIES}
    for relation, label, colour, marker, style in SERIES:
        other = next(key for key in rates if key != relation)
        values = data[relation]["values"]
        counts = data[relation]["counts"]
        ax.plot([0, 1], values, color=colour, linewidth=2.0, linestyle=style,
                marker=marker, markersize=6.0, markerfacecolor=colour,
                markeredgecolor=WHITE, markeredgewidth=0.6, clip_on=False,
                zorder=3)
        for position, value, count in zip((0, 1), values, counts, strict=True):
            above = value >= rates[other][position]
            ax.text(position, value + (2.6 if above else -2.6), f"{value:.1f}%",
                    ha="center", va="bottom" if above else "top", fontsize=8.3,
                    fontweight="bold", color=colour)
            if with_counts:
                ax.text(position + (0.045 if position == 0 else -0.045),
                        value + (6.6 if above else -6.6), f"of {count:,} PRs",
                        ha="left" if position == 0 else "right",
                        va="bottom" if above else "top", fontsize=8.0, color=SLATE)
        ax.text(1.07, values[1], label, ha="left", va="center", fontsize=8.2,
                color=colour)
    return rates


# --- B1: current form ------------------------------------------------------


def fig6_b1_current(data):
    fig = house.new_figure(4.15)
    layout = Layout(left=0.165, right=0.745, top=0.910, bottom=0.150, gap=0.150)
    top_rect, bottom_rect = layout.rects((1.0, 0.30))
    ax = fig.add_axes(top_rect)
    rates = draw_slopes(ax, data)
    for relation, _label, colour, _m, _s in SERIES:
        values = data[relation]["values"]
        above = values[1] >= rates[next(k for k in rates if k != relation)][1]
        ax.text(0.5, (values[0] + values[1]) / 2.0 + (1.9 if above else -1.9),
                minus(f"{data[relation]['change']:+.1f} pp"), ha="center",
                va="bottom" if above else "top", fontsize=8.2,
                fontweight="bold", color=colour)
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(0, 38)
    ax.set_xticks([0, 1], ["No issue link", "PR body links an issue"])
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, "B1", "Current form: slopes plus interval")
    clean_axis(ax, "y")
    did_strip(fig.add_axes(bottom_rect), data)
    save_explore(fig, "fig6_alt1_slope_current")


# --- B2: grouped bars of the four cells ------------------------------------


def fig6_b2_grouped_bars(data):
    fig = house.new_figure(3.55)
    ax = fig.add_axes((0.135, 0.150, 0.840, 0.735))
    groups = (
        ("cross_product", "A different product is reviewing", TEAL, PALE_TEAL),
        ("same_product", "The same product is reviewing", SLATE, GRID),
    )
    centres = [0.0, 1.6]
    for centre, (relation, label, edge, fill) in zip(centres, groups, strict=True):
        values = data[relation]["values"]
        counts = data[relation]["counts"]
        for offset, value, count, hatch in zip(
            (-0.28, 0.28), values, counts, ("", "///"), strict=True
        ):
            ax.bar([centre + offset], [value], width=0.5, color=fill,
                   edgecolor=edge, linewidth=1.0, hatch=hatch, zorder=2)
            ax.text(centre + offset, value + 1.0, f"{value:.1f}%", ha="center",
                    va="bottom", fontsize=8.2, fontweight="bold", color=INK)
            ax.text(centre + offset, value + 4.4, f"{count:,} PRs", ha="center",
                    va="bottom", fontsize=8.0, color=SLATE)
        change = data[relation]["change"]
        ax.annotate("", xy=(centre + 0.28, values[1] + 8.4),
                    xytext=(centre - 0.28, values[0] + 8.4),
                    arrowprops={"arrowstyle": "-|>", "color": edge,
                                "linewidth": 1.1})
        ax.text(centre, max(values) + 9.4, minus(f"{change:+.1f} pp"), ha="center",
                va="bottom", fontsize=8.4, fontweight="bold", color=edge)
        ax.text(centre, -3.4, label, ha="center", va="top", fontsize=8.2,
                color=edge)

    ax.plot([centres[0], centres[0], centres[1], centres[1]],
            [40.5, 42.5, 42.5, 40.5], color=INK, linewidth=0.9, zorder=4)
    ax.text(
        (centres[0] + centres[1]) / 2.0,
        43.2,
        minus(f"difference {data['raw']:+.1f} pp raw, ")
        + minus(f"{data['point']:+.1f}")
        + " adjusted",
        ha="center", va="bottom", fontsize=8.3, fontweight="bold", color=INK,
    )
    ax.set_xlim(-0.72, 2.32)
    ax.set_ylim(0, 50)
    ax.set_xticks([])
    ax.set_yticks([0, 10, 20, 30])
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, "B2", "Four cells, with the interaction bracketed")
    clean_axis(ax, "y")
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.text(0.0, 0.985, "solid = no issue link,  hatched = PR body links an issue",
            transform=ax.transAxes, ha="left", va="top", fontsize=8.0, color=SLATE)
    save_explore(fig, "fig6_alt2_grouped_bars")


# --- B3: only the two changes, difference bracketed ------------------------


def fig6_b3_change_bars(data):
    fig = house.new_figure(3.55)
    layout = Layout(left=0.230, right=0.800, top=0.905, bottom=0.145, gap=0.185)
    top_rect, bottom_rect = layout.rects((1.0, 0.38))
    ax = fig.add_axes(top_rect)

    rows = (
        ("cross_product", "A different product\nis reviewing", TEAL, PALE_TEAL),
        ("same_product", "The same product\nis reviewing", SLATE, GRID),
    )
    positions = [1.0, 0.0]
    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=3)
    for position, (relation, label, edge, fill) in zip(positions, rows, strict=True):
        change = data[relation]["change"]
        ax.barh([position], [change], height=0.42, color=fill, edgecolor=edge,
                linewidth=1.1, zorder=2)
        ax.text(change + 0.7 if change > 0 else 0.7, position,
                minus(f"{change:+.1f} pp"),
                ha="left", va="center", fontsize=8.4,
                fontweight="bold", color=edge)
    ax.set_yticks(positions, [label for _r, label, _e, _f in rows], fontsize=8.2)
    ax.set_xlim(-6.5, 21.0)
    ax.set_xticks([-5, 0, 5, 10, 15, 20])
    ax.set_ylim(-0.62, 1.62)
    ax.set_xlabel("Change in answer rate when the PR body links an issue (pp)")
    panel_title(ax, "B3", "What the link changes, on each side")
    category_axis(ax)

    bracket_x = 17.2
    ax.plot([bracket_x, bracket_x + 0.9, bracket_x + 0.9, bracket_x],
            [1.0, 1.0, 0.0, 0.0], color=INK, linewidth=0.9, zorder=4)
    ax.text(bracket_x + 1.4, 0.5, minus(f"{data['raw']:+.1f}") + " pp" + chr(10)
            + "raw gap", ha="left", va="center", fontsize=8.2, color=INK)

    did_strip(fig.add_axes(bottom_rect), data, "",
              "Adjusted for repository and month")
    save_explore(fig, "fig6_alt3_change_bars")


# --- B4: waterfall from same-product change to cross-product change --------


def fig6_b4_waterfall(data):
    fig = house.new_figure(3.55)
    ax = fig.add_axes((0.150, 0.230, 0.825, 0.640))

    same = data["same_product"]["change"]
    cross = data["cross_product"]["change"]
    ax.axhline(0.0, color=INK, linewidth=1.0, zorder=3)

    ax.bar([0], [same], width=0.56, color=GRID, edgecolor=SLATE, linewidth=1.1,
           zorder=2)
    ax.bar([1], [data["raw"]], bottom=same, width=0.56, color=PALE_ORANGE,
           edgecolor=ORANGE, linewidth=1.1, zorder=2)
    ax.bar([2], [cross], width=0.56, color=PALE_TEAL, edgecolor=TEAL,
           linewidth=1.1, zorder=2)
    ax.bar([3], [data["point"]], width=0.56, color=WHITE, edgecolor=TEAL,
           linewidth=1.4, linestyle=(0, (3, 1.6)), zorder=2)
    ax.plot([data["low"], data["high"]], [0, 0], color=TEAL, linewidth=0.0)
    ax.plot([3, 3], [data["low"], data["high"]], color=TEAL, linewidth=1.6,
            zorder=4)
    for edge in (data["low"], data["high"]):
        ax.plot([2.86, 3.14], [edge, edge], color=TEAL, linewidth=1.2, zorder=4)

    for x, y0, y1 in ((0, same, same), (1, same + data["raw"], cross)):
        ax.plot([x + 0.28, x + 0.72], [y1, y1], color=MID, linewidth=0.8,
                linestyle=(0, (2, 2)), zorder=1)

    labels = (
        (0, same, minus(f"{same:+.1f}"), SLATE),
        (1, same + data["raw"], minus(f"{data['raw']:+.1f}"), ORANGE),
        (2, cross, minus(f"{cross:+.1f}"), TEAL),
        (3, data["high"], minus(f"{data['point']:+.1f}"), TEAL),
    )
    for x, y, text, colour in labels:
        if x == 0:
            ax.text(x, y - 1.0, text + " pp", ha="center", va="top", fontsize=8.4,
                    fontweight="bold", color=colour)
        else:
            ax.text(x, y + 0.9, text + " pp", ha="center", va="bottom",
                    fontsize=8.4, fontweight="bold", color=colour)

    ax.set_xticks(
        [0, 1, 2, 3],
        ["same product\nchanges by", "the extra lift\nacross the boundary",
         "different product\nchanges by", "same lift, adjusted\n(95% CI)"],
        fontsize=8.0,
    )
    ax.set_xlim(-0.62, 3.62)
    ax.set_ylim(-6.0, 27.0)
    ax.set_yticks([-5, 0, 5, 10, 15, 20, 25])
    ax.set_ylabel("Change in answer rate (pp)")
    panel_title(ax, "B4", "From one change to the other")
    clean_axis(ax, "y")
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    save_explore(fig, "fig6_alt4_waterfall")


# --- B5: slopes with a parallel-trend ghost, so the gap is visible ---------


def fig6_b5_ghost(data, stem="fig6_alt5_ghost_slope", with_strip=False,
                  letter="B5", title="Slopes with the counterfactual drawn in"):
    height = 4.15 if with_strip else 3.35
    fig = house.new_figure(height)
    if with_strip:
        layout = Layout(left=0.165, right=0.655, top=0.910, bottom=0.150, gap=0.150)
        top_rect, bottom_rect = layout.rects((1.0, 0.30))
    else:
        top_rect = (0.165, 0.150, 0.655 - 0.165, 0.910 - 0.150)
        bottom_rect = None
    ax = fig.add_axes(top_rect)

    cross = data["cross_product"]["values"]
    same = data["same_product"]["values"]
    ghost = cross[0] + data["same_product"]["change"]

    ax.plot([0, 1], [cross[0], ghost], color=MID, linewidth=1.6,
            linestyle=(0, (3, 2)), zorder=2, clip_on=False)
    ax.plot([1], [ghost], marker="o", markersize=5.0, markerfacecolor="white",
            markeredgecolor=MID, markeredgewidth=1.3, zorder=3, clip_on=False)

    ax.plot([0, 1], cross, color=TEAL, linewidth=2.2, marker="o", markersize=6.0,
            markerfacecolor=TEAL, markeredgecolor=WHITE, markeredgewidth=0.6,
            clip_on=False, zorder=4)
    ax.plot([0, 1], same, color=SLATE, linewidth=2.0, linestyle=(0, (4, 2)),
            marker="s", markersize=6.0, markerfacecolor=SLATE,
            markeredgecolor=WHITE, markeredgewidth=0.6, clip_on=False, zorder=4)

    ax.text(0.03, cross[0] - 0.8, f"{cross[0]:.1f}%", ha="left", va="top",
            fontsize=8.3, fontweight="bold", color=TEAL)
    ax.text(0.03, same[0] + 0.8, f"{same[0]:.1f}%", ha="left", va="bottom",
            fontsize=8.3, fontweight="bold", color=SLATE)
    ax.text(1.035, cross[1], f"{cross[1]:.1f}%  different" + chr(10) + "       product",
            ha="left", va="center", fontsize=8.3, fontweight="bold", color=TEAL)
    ax.text(1.035, same[1], f"{same[1]:.1f}%  same" + chr(10) + "       product",
            ha="left", va="center", fontsize=8.3, fontweight="bold", color=SLATE)
    ax.text(1.035, ghost - 1.4, f"{ghost:.1f}%  if it moved" + chr(10)
            + "       like the" + chr(10) + "       same product",
            ha="left", va="center", fontsize=8.1, color=SLATE)

    bar_x = 0.90
    ax.annotate("", xy=(bar_x, cross[1]), xytext=(bar_x, ghost),
                arrowprops={"arrowstyle": "<|-|>", "color": ORANGE,
                            "linewidth": 1.4, "mutation_scale": 8})
    ax.text(bar_x - 0.035, ghost + (cross[1] - ghost) * 0.28,
            minus(f"{data['raw']:+.1f} pp") + chr(10) + "raw gap",
            ha="right", va="center", fontsize=8.4, fontweight="bold", color=ORANGE)

    if not with_strip:
        ax.text(0.5, 3.0,
                minus(f"adjusted for repository and month: {data['point']:+.1f} pp ")
                + minus(f"[{data['low']:+.1f}, {data['high']:+.1f}]"),
                ha="center", va="bottom", fontsize=8.2, color=TEAL)
        ax.text(0.5, 0.6, f"leave-one-repository-out {data['loo'].min():.1f} to "
                f"{data['loo'].max():.1f} pp; shuffle p = {data['p']:.3f}",
                ha="center", va="bottom", fontsize=8.0, color=SLATE)

    ax.set_xlim(-0.10, 1.10)
    ax.set_ylim(0, 36)
    ax.set_xticks([0, 1], ["No issue link", "PR body links an issue"])
    ax.set_yticks([0, 10, 20, 30])
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, letter, title)
    clean_axis(ax, "y")
    if bottom_rect is not None:
        did_strip(fig.add_axes(bottom_rect), data, "",
                  "The same quantity, with its uncertainty")
    save_explore(fig, stem)


def main() -> None:
    house.assert_palette_contrast()
    records, meta = load_fig3()
    fig3_a1_dumbbell(records, meta)
    fig3_a2_slope(records, meta)
    fig3_a3_difference(records, meta)
    fig3_a4_grid(records, meta)
    fig3_a5_ranked(records, meta)
    fig3_a6_levels_plus_gap(records, meta)

    data = load_fig6()
    fig6_b1_current(data)
    fig6_b2_grouped_bars(data)
    fig6_b3_change_bars(data)
    fig6_b4_waterfall(data)
    fig6_b5_ghost(data)
    fig6_b5_ghost(data, stem="fig6_alt6_ghost_slope_plus_interval",
                  with_strip=True, letter="A",
                  title="The link helps only across the boundary")

    print()
    print(f"wrote {len(REPORT)} PNGs to {EXPLORE}")


if __name__ == "__main__":
    main()
