"""Render the appendix dataset figures at their final printed size.

The Springer Nature ``sn-jnl`` text block is 372 pt wide. The two standalone
appendix figures are exported at exactly that width with an explicit figure
size and ``fig.add_axes`` rectangles, so ``\\includegraphics[width=\\linewidth]``
reproduces them at scale 1.0 and a 7.2 pt label really prints at 7.2 pt. Tight
bounding boxes are deliberately not used: they change the exported width and
therefore the effective label size on the page.

The schema panel is laid out in one 0--100 coordinate system, every join arrow
is strictly horizontal or vertical, and every join label sits in the clear gap
between two boxes. Before any file is written, ``assert_layout`` fails the
build if two texts overlap, if a text crosses a box border, if an arrow runs
through a text, or if any text falls below the 7 pt print floor.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.text import Text  # noqa: E402

# The two evidence figures below are held to the manuscript house style, not to
# the looser schema style above: the same Paul Tol palette, the same 8 pt print
# floor, and the same geometry gate that guards the six main figures. Importing
# that module rather than re-declaring its constants means a palette or gate
# change there reaches these figures too.
#
# That module sets its own rcParams at import time. The schema and coverage
# figures were tuned against matplotlib's defaults, so the delta is captured
# here and immediately rolled back, then re-applied only around the figures
# that want it.
_DEFAULTS_BEFORE_HOUSE = plt.rcParams.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import visualize_manuscript_figures as house  # noqa: E402

HOUSE_RC = {
    key: value
    for key, value in plt.rcParams.items()
    if key in _DEFAULTS_BEFORE_HOUSE
    and repr(_DEFAULTS_BEFORE_HOUSE[key]) != repr(value)
}
plt.rcParams.update({key: _DEFAULTS_BEFORE_HOUSE[key] for key in HOUSE_RC})
# Hatch weight is not a style choice that belongs to one figure family: a hatch
# drawn at matplotlib's default 1.0 pt turns a 372 pt bar into a grey wash, so
# the house weight is kept even where the rest of the house style is rolled back.
plt.rcParams["hatch.linewidth"] = house.HATCH_LINEWIDTH
HOUSE_RC["hatch.linewidth"] = house.HATCH_LINEWIDTH

ANCHORABILITY = house.ROOT / "outputs" / "anchorability_coverage"
BURST_SELECTION = house.ROOT / "outputs" / "burst_threshold_selection"


# The schema and coverage panels use the same three-hue family as the house
# module, softened by one step for the near-white box fills this figure needs.
# The two hues that carry lettering here are the steel blue and the brick red;
# goldenrod appears only as a bar fill, and its dark amber partner GOLD_INK
# carries the gold role wherever the mark is a line, an arrow or a word.
STEEL = house.STEEL
BRICK = house.BRICK
GOLD = house.GOLD
GOLD_INK = house.GOLD_INK

INK = "#202631"
# Body text inside a schema box sits on a tinted fill, not on the page, so the
# grey is one step darker than it was: at #667085 it reached only 4.06:1 on the
# palest of those fills, and at #5A6274 it clears 4.5:1 on all of them.
SLATE = "#5A6274"
GRID = "#E6E9EF"

# Box fills, one step off white so a fill is visible in print but still holds
# both INK and SLATE lettering above 4.5:1.
PALE_STEEL_FILL = "#E1EDF5"
PALE_BRICK_FILL = "#F7E4E2"
PALE_GOLD_FILL = "#F9EBD2"
PALE_GREY_FILL = "#ECEDF2"

# Text-on-fill pairs this module introduces on top of the house set. Verified
# with the house module's own contrast helper before anything is drawn.
TEXT_ON_FILL = (
    ("dataset ink on pale steel", INK, PALE_STEEL_FILL),
    ("dataset ink on pale brick", INK, PALE_BRICK_FILL),
    ("dataset ink on pale gold", INK, PALE_GOLD_FILL),
    ("dataset ink on pale grey", INK, PALE_GREY_FILL),
    ("dataset slate on pale steel", SLATE, PALE_STEEL_FILL),
    ("dataset slate on pale brick", SLATE, PALE_BRICK_FILL),
    ("dataset slate on pale gold", SLATE, PALE_GOLD_FILL),
    ("dataset slate on pale grey", SLATE, PALE_GREY_FILL),
)


def assert_palette_contrast() -> None:
    """Hold this module's own hues and fills to the house floor."""
    house.assert_palette_contrast()
    for colour in (INK, STEEL, BRICK, GOLD_INK, SLATE):
        ratio = house.contrast(colour, house.WHITE)
        if ratio < house.MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{colour} reaches only {ratio:.2f}:1 on white, below the "
                f"{house.MIN_CONTRAST_RATIO}:1 text floor"
            )
    if GOLD in (INK, STEEL, BRICK, GOLD_INK, SLATE):
        raise AssertionError("goldenrod is fill-only and must not carry text")
    for name, ink, fill in TEXT_ON_FILL:
        ratio = house.contrast(ink, fill)
        if ratio < house.MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{name} ({ink} on {fill}) reaches only {ratio:.2f}:1, below "
                f"the {house.MIN_CONTRAST_RATIO}:1 text floor"
            )
    for fill in (PALE_STEEL_FILL, PALE_BRICK_FILL, PALE_GOLD_FILL,
                 PALE_GREY_FILL, GRID):
        ratio = house.contrast(fill, house.WHITE)
        if ratio < house.MIN_FILL_CONTRAST_RATIO:
            raise AssertionError(
                f"fill {fill} reaches only {ratio:.2f}:1 against the page and "
                "washes out at print size"
            )

POINTS_PER_INCH = 72.0
TEXT_WIDTH_PT = 372.0
FIGURE_WIDTH = TEXT_WIDTH_PT / POINTS_PER_INCH
MIN_TEXT_POINTS = 7.0

TITLE_PT = 9.6
SECTION_PT = 7.6
BOX_TITLE_PT = 7.8
BOX_TITLE_SMALL_PT = 7.4
BODY_PT = 7.2
JOIN_PT = 7.2
NOTE_PT = 7.2


# ---------------------------------------------------------------------------
# Schema primitives. All geometry is in a 0--100 square data space.
# ---------------------------------------------------------------------------


def _y_units_per_point(ax: plt.Axes) -> float:
    """Data units per printed point on the vertical axis of ``ax``."""
    height_pt = ax.get_position().height * ax.figure.get_figheight() * POINTS_PER_INCH
    bottom, top = ax.get_ylim()
    return (top - bottom) / height_pt


def add_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: tuple[str, ...],
    facecolor: str,
    edgecolor: str,
    title_pt: float = BOX_TITLE_PT,
) -> FancyBboxPatch:
    """Draw a rounded table box with a bold title and short body lines.

    The text block is centred vertically using real point heights, so a box
    with one body line and a box with two body lines both stay clear of their
    own border.
    """
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0,rounding_size=1.6",
        linewidth=1.0,
        edgecolor=edgecolor,
        facecolor=facecolor,
        zorder=2,
    )
    ax.add_patch(patch)

    unit = _y_units_per_point(ax)
    title_line = title_pt * 1.32 * unit
    body_line = BODY_PT * 1.30 * unit
    block = title_line + body_line * len(body)
    cursor = y + height / 2 + block / 2 - title_line / 2
    ax.text(
        x + width / 2,
        cursor,
        title,
        ha="center",
        va="center",
        fontsize=title_pt,
        fontweight="bold",
        color=INK,
        zorder=4,
    )
    cursor -= title_line / 2
    for line in body:
        cursor -= body_line / 2
        ax.text(
            x + width / 2,
            cursor,
            line,
            ha="center",
            va="center",
            fontsize=BODY_PT,
            color=SLATE,
            zorder=4,
        )
        cursor -= body_line / 2
    return patch


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float],
          color: str = SLATE) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7.5,
            linewidth=0.9,
            color=color,
            shrinkA=0,
            shrinkB=0,
            zorder=3,
        )
    )


def join_label(ax: plt.Axes, x: float, y: float, text: str, color: str = SLATE,
               ha: str = "center", va: str = "bottom") -> None:
    ax.text(x, y, text, ha=ha, va=va, fontsize=JOIN_PT, color=color,
            style="italic", zorder=4)


def draw_schema(ax: plt.Axes, panel: str = "") -> None:
    """Two data layers and the identifier that joins each table.

    Row bands are shared by the left column, the hub and the right column so
    that every join arrow can be drawn horizontally, with its identifier label
    centred in the empty gap between the two boxes it connects.
    """
    ax.set_axis_off()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)

    prefix = f"{panel}  " if panel else ""
    ax.text(1.0, 99.0, f"{prefix}Two data layers and their join paths",
            ha="left", va="top", fontsize=TITLE_PT, fontweight="bold", color=INK)

    # ---- full corpus layer -------------------------------------------------
    ax.text(2.0, 88.5, "FULL CORPUS", ha="left", va="bottom",
            fontsize=SECTION_PT, fontweight="bold", color=STEEL)

    top_y, top_h = 70.0, 15.0
    top_mid = top_y + top_h / 2
    add_box(ax, 2, top_y, 19, top_h, "all_user", ("400k users",),
            PALE_STEEL_FILL, STEEL)
    add_box(ax, 33, top_y, 30, top_h, "all_pull_request",
            ("7.69M PRs", "agent, state, time"), PALE_STEEL_FILL, STEEL)
    add_box(ax, 75, top_y, 23, top_h, "all_repository", ("957k repos",),
            PALE_STEEL_FILL, STEEL)

    arrow(ax, (21, top_mid), (33, top_mid), STEEL)
    arrow(ax, (75, top_mid), (63, top_mid), STEEL)
    join_label(ax, 27, top_mid + 1.6, "user_id", STEEL)
    join_label(ax, 69, top_mid + 1.6, "repo_id", STEEL)

    ax.plot([1, 99], [65, 65], color=GRID, lw=1.0, zorder=1)

    # ---- AIDev-pop rich layer ---------------------------------------------
    ax.text(2.0, 58.5, "AIDEV-POP RICH SUBSET  (>100 STARS)", ha="left",
            va="bottom", fontsize=SECTION_PT, fontweight="bold", color=BRICK)

    left_x, left_w = 2.0, 28.0
    right_x, right_w = 70.0, 28.0
    hub_x, hub_w = 40.0, 20.0
    rows = ((43.0, 56.0), (25.0, 38.0), (7.0, 20.0))
    mids = [(low + high) / 2 for low, high in rows]

    hub = add_box(ax, hub_x, rows[2][0], hub_w, rows[0][1] - rows[2][0],
                  "", (), PALE_BRICK_FILL, BRICK)
    hub.set_linewidth(1.3)
    unit = _y_units_per_point(ax)
    hub_top = 39.0 + (BOX_TITLE_PT * 1.32 + BODY_PT * 2.60) * unit / 2
    ax.text(50, hub_top - BOX_TITLE_PT * 0.66 * unit, "pull_request",
            ha="center", va="center", fontsize=BOX_TITLE_PT,
            fontweight="bold", color=INK, zorder=4)
    ax.text(50, hub_top - (BOX_TITLE_PT * 1.32 + BODY_PT * 0.65) * unit,
            "361k PRs", ha="center", va="center", fontsize=BODY_PT,
            color=SLATE, zorder=4)
    ax.text(50, hub_top - (BOX_TITLE_PT * 1.32 + BODY_PT * 1.95) * unit,
            "rich-table hub", ha="center", va="center", fontsize=BODY_PT,
            color=SLATE, zorder=4)

    add_box(ax, left_x, rows[0][0], left_w, 13, "pr_timeline",
            ("lifecycle events",), PALE_GREY_FILL, SLATE)
    add_box(ax, left_x, rows[1][0], left_w, 13, "discussion tables",
            ("pr_comments", "pr_reviews"), PALE_GOLD_FILL, GOLD_INK,
            BOX_TITLE_SMALL_PT)
    add_box(ax, left_x, rows[2][0], left_w, 13, "pr_review_comments",
            ("inline threads",), PALE_GOLD_FILL, GOLD_INK, BOX_TITLE_SMALL_PT)

    add_box(ax, right_x, rows[0][0], right_w, 13, "repository",
            ("project context",), PALE_GREY_FILL, SLATE)
    add_box(ax, right_x, rows[1][0], right_w, 13, "code-change tables",
            ("pr_commits", "pr_commit_details"), PALE_GREY_FILL, SLATE,
            BOX_TITLE_SMALL_PT)
    add_box(ax, right_x, rows[2][0], right_w, 13, "task + issue links",
            ("pr_task_type", "related_issue"), PALE_GREY_FILL, SLATE,
            BOX_TITLE_SMALL_PT)

    # Horizontal joins into the hub. pr_review_comments is deliberately absent:
    # it reaches a PR only through its review batch.
    arrow(ax, (left_x + left_w, mids[0]), (hub_x, mids[0]), SLATE)
    arrow(ax, (left_x + left_w, mids[1]), (hub_x, mids[1]), GOLD_INK)
    arrow(ax, (right_x, mids[0]), (hub_x + hub_w, mids[0]), SLATE)
    arrow(ax, (right_x, mids[1]), (hub_x + hub_w, mids[1]), SLATE)
    arrow(ax, (right_x, mids[2]), (hub_x + hub_w, mids[2]), SLATE)
    join_label(ax, 35, mids[0] + 1.6, "pr_id")
    join_label(ax, 35, mids[1] + 1.6, "pr_id", GOLD_INK)
    join_label(ax, 65, mids[0] + 1.6, "repo_id")
    join_label(ax, 65, mids[1] + 1.6, "pr_id")
    join_label(ax, 65, mids[2] + 1.6, "pr_id")

    # The indirection: inline comments join the review table, not the PR.
    arrow(ax, (9, rows[2][1]), (9, rows[1][0]), GOLD_INK)
    join_label(ax, 12, (rows[2][1] + rows[1][0]) / 2, "review_id", GOLD_INK,
               ha="left", va="center")


# ---------------------------------------------------------------------------
# Coverage panel
# ---------------------------------------------------------------------------

COVERAGE_ORDER = (
    ("Timeline events", "Timeline\nevents"),
    ("Commits", "Commits"),
    ("File-level changes", "File-level\nchanges"),
    ("Conversation comments", "Conversation\ncomments"),
    ("Submitted reviews", "Submitted\nreviews"),
    ("Inline review comments", "Inline review\ncomments"),
    ("Task classification", "Task\nclassification"),
    ("Linked issues", "Linked\nissues"),
)


def draw_coverage(ax: plt.Axes, coverage: pd.DataFrame, panel: str = "") -> None:
    order = [name for name, _ in COVERAGE_ORDER]
    data = coverage.set_index("feature_group").loc[order].reset_index()
    total = int(data["aidev_pop_prs"].iloc[0])
    values = data["coverage_pct_of_aidev_pop"].to_numpy()
    y = list(range(len(data)))
    # Three coverage tiers, read the way a risk-of-bias summary is read: steel
    # blue where a feature covers most of the population, goldenrod in the
    # middle, brick red where coverage is thin. Steel and brick share a
    # luminance, so the tiers also carry opposed hatches and survive a
    # greyscale print. No lettering sits on these bars; the labels are outside.
    tiers = [
        (STEEL, house.HATCH_STEEL) if v >= 50
        else (GOLD, house.HATCH_GOLD) if v >= 20
        else (BRICK, house.HATCH_BRICK)
        for v in values
    ]
    colors = [colour for colour, _ in tiers]

    ax.barh(
        y,
        values,
        color=colors,
        height=0.62,
        edgecolor=INK,
        linewidth=0.35,
        hatch=[hatch for _, hatch in tiers],
        zorder=2,
    )
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, label in COVERAGE_ORDER],
                       fontsize=BODY_PT, color=INK, linespacing=1.15)
    ax.invert_yaxis()
    # One row of clear space under the last bar, which is where the tier key
    # sits. Set explicitly, or the autoscaled limit clips it.
    ax.set_ylim(len(data) + 0.35, -0.65)
    ax.set_xlim(0, 78)
    ax.set_xticks([0, 20, 40, 60])
    ax.set_xticklabels(["0%", "20%", "40%", "60%"], fontsize=BODY_PT, color=INK)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(SLATE)
    ax.spines["bottom"].set_linewidth(0.7)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.tick_params(axis="x", length=2.4, width=0.6, color=SLATE)

    for yi, value, count in zip(y, values, data["matched_pr_ids"]):
        ax.text(value + 1.4, yi, f"{value:.1f}%   {int(count) / 1000:.0f}k PRs",
                va="center", ha="left", fontsize=BODY_PT, color=INK, zorder=3)

    # Colour and hatch here encode a three-way judgement about coverage that no
    # axis states, so the thresholds are named rather than left to be guessed.
    house.swatch_key(
        ax,
        0.0,
        len(data) - 0.05,
        (
            ("rect", {"facecolor": STEEL, "edgecolor": INK, "linewidth": 0.35,
                      "hatch": house.HATCH_STEEL}, "50% or more"),
            ("rect", {"facecolor": GOLD, "edgecolor": INK, "linewidth": 0.35,
                      "hatch": house.HATCH_GOLD}, "20 to 50%"),
            ("rect", {"facecolor": BRICK, "edgecolor": INK, "linewidth": 0.35,
                      "hatch": house.HATCH_BRICK}, "under 20%"),
        ),
        fontsize=BODY_PT,
        swatch_width=3.2,
        swatch_height=0.44,
        label_pad=1.2,
        gap=4.0,
    )

    # Headings are hung on the figure margin, not on the axes edge, so they
    # align with the footer note instead of floating above the bars. The
    # vertical offsets are in points, which keeps the subtitle clear of the
    # top gridline at any panel height.
    figure_width_pt = ax.figure.get_figwidth() * POINTS_PER_INCH
    dx = -(ax.get_position().x0 * figure_width_pt - 0.012 * figure_width_pt)
    prefix = f"{panel}  " if panel else ""
    ax.annotate(f"{prefix}Rich features cover different subsets",
                xy=(0, 1), xycoords="axes fraction", xytext=(dx, 21),
                textcoords="offset points", ha="left", va="bottom",
                fontsize=TITLE_PT, fontweight="bold", color=INK,
                annotation_clip=False)
    ax.annotate(f"Share of {total:,} AIDev-pop PRs with at least one linked row",
                xy=(0, 1), xycoords="axes fraction", xytext=(dx, 8),
                textcoords="offset points", ha="left", va="bottom",
                fontsize=NOTE_PT, color=SLATE, annotation_clip=False)


# ---------------------------------------------------------------------------
# Geometry gate
# ---------------------------------------------------------------------------


def _texts(fig: plt.Figure) -> list[Text]:
    found: list[Text] = [t for t in fig.texts]
    for ax in fig.axes:
        found.extend(ax.texts)
        found.append(ax.title)
        if ax.axison:
            found.extend(ax.get_xticklabels())
            found.extend(ax.get_yticklabels())
    return [t for t in found if t.get_visible() and t.get_text().strip()]


def assert_layout(fig: plt.Figure, stem: str) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    px = fig.dpi / POINTS_PER_INCH
    canvas = fig.bbox

    texts = _texts(fig)
    boxes = []
    for text in texts:
        if text.get_fontsize() < MIN_TEXT_POINTS - 1e-6:
            raise AssertionError(
                f"{stem}: '{text.get_text()[:32]}' is {text.get_fontsize():.1f} pt, "
                f"below the {MIN_TEXT_POINTS} pt print floor"
            )
        box = text.get_window_extent(renderer=renderer)
        if (box.x0 < canvas.x0 - 0.6 or box.x1 > canvas.x1 + 0.6
                or box.y0 < canvas.y0 - 0.6 or box.y1 > canvas.y1 + 0.6):
            raise AssertionError(
                f"{stem}: text '{text.get_text()[:32]}' is clipped by the canvas"
            )
        boxes.append((text.get_text(), box))

    for index, (first_label, first) in enumerate(boxes):
        for second_label, second in boxes[index + 1:]:
            if (min(first.x1, second.x1) - max(first.x0, second.x0) > 1.0
                    and min(first.y1, second.y1) - max(first.y0, second.y0) > 1.0):
                raise AssertionError(
                    f"{stem}: texts '{first_label[:24]}' and "
                    f"'{second_label[:24]}' overlap"
                )

    pad = 1.6 * px
    for ax in fig.axes:
        for patch in ax.patches:
            if not isinstance(patch, FancyBboxPatch):
                continue
            frame = patch.get_window_extent(renderer=renderer)
            for label, box in boxes:
                touches = (min(frame.x1 + pad, box.x1) - max(frame.x0 - pad, box.x0) > 0.5
                           and min(frame.y1 + pad, box.y1) - max(frame.y0 - pad, box.y0) > 0.5)
                if not touches:
                    continue
                inside = (box.x0 > frame.x0 + pad and box.x1 < frame.x1 - pad
                          and box.y0 > frame.y0 + pad and box.y1 < frame.y1 - pad)
                if not inside:
                    raise AssertionError(
                        f"{stem}: text '{label[:24]}' crosses a box border"
                    )

    for ax in fig.axes:
        for patch in ax.patches:
            if not isinstance(patch, FancyArrowPatch):
                continue
            start = ax.transData.transform(patch._posA_posB[0])
            end = ax.transData.transform(patch._posA_posB[1])
            for step in range(41):
                fraction = step / 40
                point = (start[0] + (end[0] - start[0]) * fraction,
                         start[1] + (end[1] - start[1]) * fraction)
                for label, box in boxes:
                    if (box.x0 - px < point[0] < box.x1 + px
                            and box.y0 - px < point[1] < box.y1 + px):
                        raise AssertionError(
                            f"{stem}: an arrow runs through text '{label[:24]}'"
                        )


def save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    try:
        assert_layout(fig, stem)
    except AssertionError:
        debug = output_dir / "qa_debug"
        debug.mkdir(parents=True, exist_ok=True)
        fig.savefig(debug / f"{stem}.png", dpi=300)
        raise
    fig.savefig(output_dir / f"{stem}.pdf")
    fig.savefig(output_dir / f"{stem}.png", dpi=400)
    plt.close(fig)


# ---------------------------------------------------------------------------
# House-style evidence figures. Same palette, same 8 pt floor, same gate as the
# six main figures, so an appendix figure is held to the manuscript standard.
# ---------------------------------------------------------------------------


PRIMARY_COHORT = "full_cross_product_trigger_cohort"
LANDMARK_COHORT = "open_at_48h_landmark_cohort"
CHANNEL_ORDER = ("inline_review_comment", "submitted_review", "pr_comment")
CHANNEL_SHORT = {
    "inline_review_comment": "Inline comment",
    "submitted_review": "Review body",
    "pr_comment": "PR comment",
}
# Dark, mid, light left to right, so the three channels stay ordered and
# separable in the greyscale proof as well as in colour: steel at 4.55:1 against
# the page, goldenrod at 2.14:1, pale brick at 1.40:1. That spread is why this
# stack needs no hatching. Goldenrod cannot carry lettering, so the middle
# segment reverses to ink rather than to white.
CHANNEL_FACE = {
    "inline_review_comment": house.STEEL,
    "submitted_review": house.GOLD,
    "pr_comment": house.PALE_BRICK,
}
CHANNEL_TEXT = {
    "inline_review_comment": house.WHITE,
    "submitted_review": house.INK,
    "pr_comment": house.INK,
}

# Each row of the dot plot: the artifact key, the reader-facing name, and
# whether it is the convention the paper publishes. The cut itself is drawn as
# its own column from the artifact, never typed here.
BURST_SCHEMES = (
    ("fixed_0_minutes", "Fixed window", False),
    ("fixed_1_minutes", "Fixed window", False),
    ("fixed_5_minutes", "Fixed window", True),
    ("fixed_10_minutes", "Fixed window", False),
    ("fixed_30_minutes", "Fixed window", False),
    ("global_log_hazard_change_point", "Global change point", False),
    (
        "global_log_hazard_change_point_burst_region",
        "Global, " + "≤" + " 60 min",
        False,
    ),
    ("product_specific_log_hazard_change_point", "Per product", False),
    (
        "product_specific_log_hazard_change_point_burst_region",
        "Per product, " + "≤" + " 60 min",
        False,
    ),
)
EXPECTED_BURST_SCHEMES = 9


def _cohort_rows(frame: pd.DataFrame, cohort: str, expected: int) -> pd.DataFrame:
    if "cohort" not in frame.columns:
        raise ValueError("This artifact no longer carries a leading cohort column")
    rows = frame[frame["cohort"].astype(str) == cohort]
    if len(rows) != expected:
        raise ValueError(
            f"Expected {expected} rows for cohort {cohort}, found {len(rows)}"
        )
    return rows


def _house_save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    """Export at exactly 372 pt after the manuscript geometry gate has passed."""
    try:
        house.assert_layout(fig, stem)
    except AssertionError:
        debug = house.ROOT / "build" / "qa" / "figure_qa_debug"
        debug.mkdir(parents=True, exist_ok=True)
        fig.savefig(debug / f"{stem}.png", dpi=300)
        raise
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "Title": stem,
        "Author": "Dao Sy Duy Minh et al.",
        "Subject": "Public coordination topology after cross-product agent review",
        "Creator": "Matplotlib",
    }
    fig.savefig(output_dir / f"{stem}.pdf", metadata=metadata)
    fig.savefig(output_dir / f"{stem}.png", dpi=400)
    plt.close(fig)


def write_house_colour_proofs(stems, source_dir: Path) -> list[str]:
    """Dichromacy and greyscale proofs, by the same route as the main figures."""
    directory = house.ROOT / "build" / "qa" / "colour"
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem in stems:
        source = source_dir / f"{stem}.png"
        if not source.is_file():
            raise FileNotFoundError(source)
        linear = house.srgb_to_linear(plt.imread(source)[:, :, :3].astype(float))
        for name, matrix in house.CVD_MATRICES.items():
            path = directory / f"{stem}_{name}.png"
            plt.imsave(path, house.linear_to_srgb(linear @ matrix.T))
            written.append(path.name)
        grey = linear @ house.RELATIVE_LUMINANCE
        path = directory / f"{stem}_greyscale.png"
        plt.imsave(path, house.linear_to_srgb(np.repeat(grey[:, :, None], 3, axis=2)))
        written.append(path.name)
    return sorted(written)


def figure_anchorable_coverage(output_dir: Path) -> str:
    """What the addressed edge can reach, as a composition rather than a table.

    Three review channels exist; one of them stores a reply anchor. The figure
    puts the reviewer-side event mix and the trigger-PR mix on the same 0--100
    axis so the anchorable boundary can be read off twice, and adds the inline
    thread-root ceiling underneath.
    """
    summary = json.loads((ANCHORABILITY / "summary.json").read_text(encoding="utf-8"))
    if summary["primary_cohort"] != PRIMARY_COHORT:
        raise ValueError(
            f"Primary cohort key drifted to {summary['primary_cohort']!r}"
        )
    if summary["secondary_cohort"] != LANDMARK_COHORT:
        raise ValueError(
            f"Secondary cohort key drifted to {summary['secondary_cohort']!r}"
        )

    volume = house.read_csv(
        ANCHORABILITY / "channel_interaction_volume.csv",
        (
            "cohort",
            "channel",
            "carries_reply_anchor",
            "reviewer_side_events",
            "share_of_reviewer_side_events",
        ),
    )
    composition = house.read_csv(
        ANCHORABILITY / "trigger_channel_composition.csv",
        (
            "cohort",
            "trigger_channel",
            "in_scope_for_the_addressed_edge",
            "trigger_prs",
            "share_of_trigger_prs",
        ),
    )
    split = house.read_csv(
        ANCHORABILITY / "inline_root_reply_split.csv",
        (
            "cohort",
            "position",
            "can_receive_an_exact_parent_edge",
            "inline_events",
            "share_of_inline_events",
        ),
    )

    events = _cohort_rows(volume, PRIMARY_COHORT, 3).set_index("channel")
    triggers = _cohort_rows(composition, PRIMARY_COHORT, 3).set_index("trigger_channel")
    landmark = _cohort_rows(composition, LANDMARK_COHORT, 3).set_index("trigger_channel")
    positions = _cohort_rows(split, PRIMARY_COHORT, 2).set_index("position")

    for frame, flag in ((events, "carries_reply_anchor"), (triggers, "in_scope_for_the_addressed_edge")):
        anchored = frame[frame[flag].astype(str).str.lower() == "true"]
        if list(anchored.index) != ["inline_review_comment"]:
            raise ValueError(
                "Exactly one channel must carry a reply anchor; the artifact now "
                f"reports {list(anchored.index)}"
            )
    if list(positions[positions["can_receive_an_exact_parent_edge"].astype(str).str.lower() == "true"].index) != ["thread_root"]:
        raise ValueError("Only a thread root may receive an exact parent edge")

    rows = (
        ("events", events, "reviewer_side_events", "share_of_reviewer_side_events",
         "Reviewer-side\nreview events", "events"),
        ("triggers", triggers, "trigger_prs", "share_of_trigger_prs",
         "Cross-product\ntrigger PRs", "PRs"),
    )
    totals = {
        "events": int(events["reviewer_side_events"].sum()),
        "triggers": int(triggers["trigger_prs"].sum()),
    }

    fig = house.new_figure(4.20)
    layout = house.Layout(left=0.205, right=0.972, top=0.925, bottom=0.175, gap=0.130)
    top_rect, bottom_rect = layout.rects((1.0, 0.34))

    ax = fig.add_axes(top_rect)
    y_of = {"events": 1.0, "triggers": 0.0}
    bar_height = 0.60
    for key, frame, count_column, share_column, tick, unit in rows:
        y = y_of[key]
        cursor = 0.0
        for channel in CHANNEL_ORDER:
            row = frame.loc[channel]
            share = float(row[share_column]) * 100
            ax.barh(
                y,
                share,
                left=cursor,
                height=bar_height,
                color=CHANNEL_FACE[channel],
                edgecolor=house.INK,
                linewidth=0.4,
                zorder=2,
            )
            # The channel names live in the key below, so a segment carries
            # only its share and both rows read the same way.
            ax.text(
                cursor + share / 2,
                y,
                f"{share:.1f}%",
                ha="center",
                va="center",
                fontsize=8.1,
                color=CHANNEL_TEXT[channel],
                zorder=4,
            )
            cursor += share

        boundary = float(frame.loc["inline_review_comment", share_column]) * 100
        ax.plot(
            [boundary, boundary],
            [y - bar_height / 2 - 0.10, y + bar_height / 2 + 0.10],
            color=house.INK,
            linewidth=1.4,
            zorder=5,
        )
        reachable = int(frame.loc["inline_review_comment", count_column])
        text_y = y + bar_height / 2 + 0.20 if key == "events" else y - bar_height / 2 - 0.20
        # The share is already printed inside the segment and the panel title
        # already says what the rule at the boundary is, so the only thing this
        # line still has to carry is the count behind that share.
        ax.text(
            boundary,
            text_y,
            f"{reachable:,} of {totals[key]:,} {unit}",
            ha="center",
            va="bottom" if key == "events" else "top",
            fontsize=8.1,
            color=house.INK,
            zorder=5,
        )

    landmark_boundary = float(
        landmark.loc["inline_review_comment", "share_of_trigger_prs"]
    ) * 100
    ax.plot(
        [landmark_boundary],
        [bar_height / 2 + 0.13],
        marker="v",
        markersize=5.0,
        markerfacecolor=house.WHITE,
        markeredgecolor=house.SLATE,
        markeredgewidth=1.1,
        zorder=5,
    )
    # A lone hollow mark is ambiguous, so it is named where it sits.
    ax.text(
        landmark_boundary + 1.6,
        bar_height / 2 + 0.13,
        f"{landmark_boundary:.1f}% in the 48 h cohort",
        ha="left",
        va="center",
        fontsize=8.1,
        color=house.SLATE,
        zorder=5,
    )
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    # Tightened when the three-line note under this panel became one line.
    ax.set_ylim(-1.02, 1.78)
    ax.set_yticks([y_of[key] for key, *_ in rows])
    ax.set_yticklabels([tick for _, _, _, _, tick, _ in rows], fontsize=8.1,
                       linespacing=1.3)
    ax.set_xlabel("Share of the row total (%)")
    house.panel_title(ax, "A", "One channel of three can carry a reply anchor")
    house.category_axis(ax)

    ax = fig.add_axes(bottom_rect)
    cursor = 0.0
    ceiling = float(positions.loc["thread_root", "share_of_inline_events"]) * 100
    for position, face, ink, name in (
        ("thread_root", house.STEEL, house.WHITE, "Thread root"),
        ("reply_in_thread", house.GRID, house.INK, "Reply in a thread"),
    ):
        share = float(positions.loc[position, "share_of_inline_events"]) * 100
        ax.barh(
            0.0,
            share,
            left=cursor,
            height=0.60,
            color=face,
            edgecolor=house.INK,
            linewidth=0.4,
            zorder=2,
        )
        ax.text(
            cursor + share / 2,
            0.0,
            f"{name}\n{share:.1f}%" if position == "thread_root" else f"{share:.1f}%",
            ha="center",
            va="center",
            fontsize=8.1,
            color=ink,
            linespacing=1.35,
            zorder=4,
        )
        cursor += share
    ax.plot(
        [ceiling, ceiling],
        [-0.40, 0.40],
        color=house.INK,
        linewidth=1.4,
        zorder=5,
    )
    inline_total = int(positions["inline_events"].sum())
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.55, 0.55)
    ax.set_yticks([0.0])
    ax.set_yticklabels([f"{inline_total:,} inline\ncomment events"], fontsize=8.1,
                       linespacing=1.3)
    ax.set_xlabel("Share of inline review comment events (%)")
    house.panel_title(ax, "B", "And inside it, only a thread root can be named")
    house.category_axis(ax)

    # The three channel colours repeat down both panels but are named only in
    # the first row of Panel A, so they get a key of their own. It replaces the
    # sentence that used to sit here, which said what the caption says.
    key_axes = fig.add_axes((0.006, 0.012, 0.980, 0.055))
    key_axes.set_xlim(0, 100)
    key_axes.set_ylim(0, 10)
    key_axes.axis("off")
    heading = key_axes.text(0.0, 5.0, "Review channel:", ha="left", va="center",
                            fontsize=8.0, color=house.SLATE)
    key_axes.figure.canvas.draw()
    start = key_axes.transData.inverted().transform(
        (heading.get_window_extent(
            renderer=key_axes.figure.canvas.get_renderer()).x1, 0.0)
    )[0] + 2.4
    house.swatch_key(
        key_axes,
        start,
        5.0,
        tuple(
            (
                "rect",
                {"facecolor": CHANNEL_FACE[channel], "edgecolor": house.INK,
                 "linewidth": 0.4},
                CHANNEL_SHORT[channel],
            )
            for channel in CHANNEL_ORDER
        ),
        swatch_height=4.0,
    )

    stem = "anchorable_channel_coverage"
    _house_save(fig, output_dir, stem)
    return stem


def figure_burst_threshold_sensitivity(output_dir: Path) -> str:
    """The burst window is a convention, and the ordering survives all nine.

    Panel A is a dot plot of the user-minus-mapped-product lead under every
    scheme tested, with its repository-clustered interval. Panel B says why no
    scheme is privileged: the gap density has no valley at burst scale.
    """
    sensitivity = house.read_csv(
        BURST_SELECTION / "owner_split_sensitivity.csv",
        (
            "scheme",
            "scheme_kind",
            "threshold_minutes",
            "user_minus_mapped_percentage_points_actions",
            "user_minus_mapped_ci_low_pp_actions",
            "user_minus_mapped_ci_high_pp_actions",
            "user_exceeds_mapped",
            "user_exceeds_mapped_interval_excludes_zero",
            "repositories",
        ),
    )
    if len(sensitivity) != EXPECTED_BURST_SCHEMES:
        raise ValueError(
            f"Expected {EXPECTED_BURST_SCHEMES} burst-window schemes, found "
            f"{len(sensitivity)}"
        )
    declared = [key for key, _, _ in BURST_SCHEMES]
    if sorted(sensitivity["scheme"].astype(str)) != sorted(declared):
        raise ValueError("The nine burst-window scheme keys have drifted")
    sensitivity = sensitivity.set_index("scheme")

    histogram = house.read_csv(
        BURST_SELECTION / "gap_histogram.csv",
        ("bin_centre_minutes", "kde_density_per_log10_minute"),
    )
    shape = house.read_csv(
        BURST_SELECTION / "gap_distribution_shape.csv", ("statistic", "value")
    ).set_index("statistic")["value"]
    selection = json.loads(
        (BURST_SELECTION / "summary.json").read_text(encoding="utf-8")
    )
    gap = selection["gap_distribution"]
    if gap["is_bimodal_within_burst_region"]:
        raise ValueError(
            "A burst-region antimode now exists; the 'no natural valley' claim "
            "no longer holds"
        )

    def minutes(value: float) -> str:
        return f"{value:.0f}" if value >= 10 else f"{value:.2g}"

    def cut_label(scheme: str) -> str:
        """The cut this scheme uses, read off the artifact in every case."""
        raw = str(sensitivity.loc[scheme, "threshold_minutes"])
        if "=" not in raw:
            return minutes(float(raw))
        values = [float(part.split("=")[1]) for part in raw.split(";")]
        return f"{minutes(min(values))} to {minutes(max(values))}"

    fig = house.new_figure(5.35)
    layout = house.Layout(left=0.290, right=0.962, top=0.948, bottom=0.155, gap=0.128)
    top_rect, bottom_rect = layout.rects((1.0, 0.52))

    ax = fig.add_axes(top_rect)
    GROUP_GAP = 0.85
    y_positions, labels, colours = [], [], []
    cursor = float(len(BURST_SCHEMES)) + GROUP_GAP
    previous_kind = None
    for scheme, name, published in BURST_SCHEMES:
        kind = str(sensitivity.loc[scheme, "scheme_kind"])
        fixed = kind == "fixed"
        if previous_kind is not None and fixed != (previous_kind == "fixed"):
            cursor -= GROUP_GAP
        previous_kind = kind
        y_positions.append(cursor)
        labels.append(name)
        colours.append(house.STEEL if published else house.SLATE)
        cursor -= 1.0

    # The cut is a property of the scheme, not of the estimate, so it gets its
    # own column to the left of zero rather than being folded into the row name.
    CUT_COLUMN = -4.0

    lows, highs = [], []
    for y, (scheme, _name, published), colour in zip(
        y_positions, BURST_SCHEMES, colours, strict=True
    ):
        ax.text(
            CUT_COLUMN,
            y,
            cut_label(scheme),
            ha="right",
            va="center",
            fontsize=8.0,
            color=house.INK if published else house.SLATE,
            zorder=4,
        )
        row = sensitivity.loc[scheme]
        if str(row["user_exceeds_mapped"]).lower() != "true":
            raise ValueError(f"{scheme}: user accounts no longer lead")
        if str(row["user_exceeds_mapped_interval_excludes_zero"]).lower() != "true":
            raise ValueError(f"{scheme}: the interval now touches zero")
        point = float(row["user_minus_mapped_percentage_points_actions"])
        low = float(row["user_minus_mapped_ci_low_pp_actions"])
        high = float(row["user_minus_mapped_ci_high_pp_actions"])
        lows.append(low)
        highs.append(high)
        ax.plot([low, high], [y, y], color=colour,
                linewidth=2.0 if published else 1.3, zorder=3)
        for edge in (low, high):
            ax.plot([edge, edge], [y - 0.17, y + 0.17], color=colour,
                    linewidth=1.1, zorder=3)
        ax.plot(
            [point],
            [y],
            marker="o",
            markersize=6.2 if published else 4.8,
            markerfacecolor=colour,
            markeredgecolor=house.WHITE,
            markeredgewidth=0.7,
            zorder=4,
        )
        ax.text(
            high + 1.1,
            y,
            f"+{point:.1f}",
            ha="left",
            va="center",
            fontsize=8.1,
            color=house.INK,
            fontweight="bold" if published else "normal",
            zorder=4,
        )

    nearest = min(lows)
    ax.axvline(0.0, color=house.INK, linewidth=1.0, zorder=1)
    ax.axvspan(0.0, nearest, color=house.PALE_STEEL, alpha=0.45, zorder=0, linewidth=0)
    bounds = (min(y_positions) - 1.05, max(y_positions) + 1.35)
    ax.text(
        0.9,
        bounds[0] + 0.06,
        "no interval reaches zero",
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=house.SLATE,
        zorder=4,
    )
    ax.text(
        CUT_COLUMN,
        max(y_positions) + 0.80,
        "cut (min)",
        ha="right",
        va="center",
        fontsize=8.0,
        color=house.SLATE,
        zorder=4,
    )
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8.1, linespacing=1.3)
    for tick, colour in zip(ax.get_yticklabels(), colours, strict=True):
        tick.set_color(house.INK if colour == house.STEEL else house.SLATE)
    ax.set_ylim(*bounds)
    ax.set_xlim(-24.0, max(highs) + 4.0)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.set_xlabel(
        "User account " + house.MINUS + " mapped product, share of PRs\n"
        "with a post-burst action (pp, 95% cluster CI)"
    )
    house.panel_title(ax, "A", "The same owner leads under every window")
    house.category_axis(ax)
    house.fit_right_labels(ax)

    ax = fig.add_axes(bottom_rect)
    minutes = histogram["bin_centre_minutes"].to_numpy()
    density = histogram["kde_density_per_log10_minute"].to_numpy()
    ax.fill_between(minutes, 0.0, density, color=house.PALE_STEEL, alpha=0.75,
                    linewidth=0, zorder=1)
    ax.plot(minutes, density, color=house.STEEL, linewidth=1.5, zorder=3)
    ax.set_xscale("log")
    top = float(density.max()) * 1.52
    # The fixed windows are drawn where they fall on the density. The 0-minute
    # window has no place on a log axis and is named in the note instead.
    for cut in (1.0, 5.0, 10.0, 30.0):
        ax.plot([cut, cut], [0.0, top * 0.66], color=house.MID, linewidth=0.8,
                linestyle=(0, (2, 2)), zorder=2)
        ax.text(cut, top * 0.03, f"{cut:.0f}", ha="center", va="bottom",
                fontsize=8.0, color=house.SLATE, zorder=4)
    mode = float(gap["kde_mode_minutes"][0])
    antimode = float(gap["kde_antimode_minutes"][0])
    ax.plot([antimode, antimode], [0.0, top * 0.62], color=house.BRICK,
            linewidth=1.0, linestyle=(0, (4, 2)), zorder=2)
    ax.plot(
        [mode],
        [float(np.interp(mode, minutes, density))],
        marker="v",
        markersize=5.0,
        markerfacecolor=house.STEEL,
        markeredgecolor=house.WHITE,
        markeredgewidth=0.6,
        zorder=4,
    )
    ax.text(
        mode,
        float(np.interp(mode, minutes, density)) + top * 0.06,
        f"one mode, {mode:.1f} min",
        ha="center",
        va="bottom",
        fontsize=8.1,
        color=house.STEEL,
        zorder=4,
    )
    ax.text(
        antimode / 1.25,
        top * 0.16,
        f"only valley: {antimode / 60.0:.1f} h, overnight",
        ha="right",
        va="bottom",
        fontsize=8.0,
        color=house.BRICK,
        zorder=4,
    )
    ax.set_xlim(0.02, 12000)
    ax.set_ylim(0.0, top)
    ax.set_xticks([0.1, 1, 10, 100, 1000, 10000])
    ax.set_xticklabels(["0.1", "1", "10", "100", "1,000", "10,000"])
    ax.set_yticks([])
    ax.set_xlabel(
        "Minutes to the next public event (log scale)\n"
        f"median {float(shape['quantile_50_minutes']):.1f} min, "
        f"{float(shape['share_of_prs_with_gap_at_or_below_5_minutes']) * 100:.1f}% "
        "within 5 min"
    )
    ax.set_ylabel("Density per\nlog" + "₁₀" + " minute")
    house.panel_title(ax, "B", "No cut is privileged by the data")
    house.clean_axis(ax, "y")
    ax.spines["left"].set_visible(False)

    # Two hues and two dash patterns are in play across the two panels, so
    # they are named in a key instead of being explained in a sentence.
    key_axes = fig.add_axes((0.006, 0.008, 0.980, 0.046))
    key_axes.set_xlim(0, 100)
    key_axes.set_ylim(0, 10)
    key_axes.axis("off")
    house.swatch_key(
        key_axes,
        0.0,
        5.0,
        (
            (
                "rect",
                {"facecolor": house.STEEL, "edgecolor": house.STEEL},
                "the published window",
            ),
            (
                "rect",
                {"facecolor": house.SLATE, "edgecolor": house.SLATE},
                "the eight alternatives",
            ),
            (
                "line",
                {"color": house.MID, "linewidth": 0.8, "linestyle": (0, (2, 2))},
                "windows tested",
            ),
            (
                "line",
                {"color": house.BRICK, "linewidth": 1.0, "linestyle": (0, (4, 2))},
                "antimode",
            ),
        ),
        swatch_height=3.4,
        gap=2.2,
    )

    stem = "burst_threshold_sensitivity"
    _house_save(fig, output_dir, stem)
    return stem


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path,
                        default=Path("outputs/tables/dataset_join_coverage.csv"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("outputs/figures"))
    args = parser.parse_args()
    assert_palette_contrast()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    coverage = pd.read_csv(args.coverage)

    plt.rcParams.update({
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "font.family": "DejaVu Sans",
        "font.size": BODY_PT,
        "text.color": INK,
        "axes.labelcolor": INK,
        "axes.edgecolor": SLATE,
        "xtick.color": INK,
        "ytick.color": INK,
        "figure.facecolor": "#FFFFFF",
        "axes.facecolor": "#FFFFFF",
        "savefig.facecolor": "#FFFFFF",
        "savefig.pad_inches": 0.0,
    })

    # Standalone appendix figures: exported at exactly 372 pt, never with a
    # tight bounding box, so their labels print at their declared size.
    schema_fig = plt.figure(figsize=(FIGURE_WIDTH, 4.30))
    schema_ax = schema_fig.add_axes([0.0, 0.055, 1.0, 0.945])
    draw_schema(schema_ax)
    # The two layers are already named by their coloured section headings and
    # every box carries its own name, so the only encoding a reader cannot read
    # off the diagram is the gold group: the review path the addressed edge
    # depends on. That one gets a key; the sentence that used to sit here said
    # what the caption says.
    schema_key = schema_fig.add_axes([0.008, 0.006, 0.984, 0.052])
    schema_key.set_xlim(0, 100)
    schema_key.set_ylim(0, 10)
    schema_key.axis("off")
    house.swatch_key(
        schema_key,
        0.0,
        5.0,
        (
            ("rect", {"facecolor": PALE_GOLD_FILL, "edgecolor": GOLD_INK,
                      "linewidth": 1.0}, "the inline review path"),
            ("rect", {"facecolor": PALE_GREY_FILL, "edgecolor": SLATE,
                      "linewidth": 1.0}, "other rich tables"),
        ),
        fontsize=NOTE_PT,
        swatch_width=3.2,
        swatch_height=3.6,
        label_pad=1.2,
        gap=4.0,
    )
    save(schema_fig, args.output_dir, "dataset_schema_and_joins")

    coverage_fig = plt.figure(figsize=(FIGURE_WIDTH, 3.20))
    coverage_ax = coverage_fig.add_axes([0.185, 0.105, 0.795, 0.760])
    draw_coverage(coverage_ax, coverage)
    save(coverage_fig, args.output_dir, "dataset_feature_coverage")

    # One combined overview is retained for artifact browsing. The manuscript
    # uses the two standalone files above so their labels are not scaled down.
    fig = plt.figure(figsize=(7.2, 8.0))
    schema_panel = fig.add_axes([0.02, 0.475, 0.96, 0.505])
    draw_schema(schema_panel, panel="A")
    coverage_panel = fig.add_axes([0.145, 0.085, 0.825, 0.300])
    draw_coverage(coverage_panel, coverage, panel="B")
    save(fig, args.output_dir, "dataset_map_and_coverage")

    # The two evidence figures below replace appendix tables, so they follow the
    # manuscript house style rather than the schema style used above.
    with plt.rc_context(HOUSE_RC):
        house.assert_palette_contrast()
        stems = [
            figure_anchorable_coverage(args.output_dir),
            figure_burst_threshold_sensitivity(args.output_dir),
        ]
    # The schema and coverage panels are proofed too. The coverage bars encode a
    # three-tier judgement in colour, and two of those tiers share a luminance,
    # so the greyscale proof is the only place the hatching can be checked.
    proofs = write_house_colour_proofs(
        [
            "dataset_schema_and_joins",
            "dataset_feature_coverage",
            "dataset_map_and_coverage",
            *stems,
        ],
        args.output_dir,
    )
    print(
        json.dumps(
            {
                "house_style_figures": stems,
                "output": str(args.output_dir),
                "colour_proofs": "build/qa/colour",
                "proof_files": proofs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
