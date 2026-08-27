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

ANCHORABILITY = house.ROOT / "outputs" / "anchorability_coverage"
BURST_SELECTION = house.ROOT / "outputs" / "burst_threshold_selection"


INK = "#202631"
BLUE = "#2C6EAA"
ORANGE = "#C76B16"
TEAL = "#16827C"
SLATE = "#667085"
GRID = "#E6E9EF"
PALE_BLUE = "#B9CCE2"

PALE_BLUE_FILL = "#EAF1F8"
PALE_ORANGE_FILL = "#FBEEE0"
PALE_TEAL_FILL = "#E4F0EF"
PALE_GREY_FILL = "#F4F5F8"

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
            fontsize=SECTION_PT, fontweight="bold", color=BLUE)

    top_y, top_h = 70.0, 15.0
    top_mid = top_y + top_h / 2
    add_box(ax, 2, top_y, 19, top_h, "all_user", ("400k users",),
            PALE_BLUE_FILL, BLUE)
    add_box(ax, 33, top_y, 30, top_h, "all_pull_request",
            ("7.69M PRs", "agent, state, time"), PALE_BLUE_FILL, BLUE)
    add_box(ax, 75, top_y, 23, top_h, "all_repository", ("957k repos",),
            PALE_BLUE_FILL, BLUE)

    arrow(ax, (21, top_mid), (33, top_mid), BLUE)
    arrow(ax, (75, top_mid), (63, top_mid), BLUE)
    join_label(ax, 27, top_mid + 1.6, "user_id", BLUE)
    join_label(ax, 69, top_mid + 1.6, "repo_id", BLUE)

    ax.plot([1, 99], [65, 65], color=GRID, lw=1.0, zorder=1)

    # ---- AIDev-pop rich layer ---------------------------------------------
    ax.text(2.0, 58.5, "AIDEV-POP RICH SUBSET  (>100 STARS)", ha="left",
            va="bottom", fontsize=SECTION_PT, fontweight="bold", color=ORANGE)

    left_x, left_w = 2.0, 28.0
    right_x, right_w = 70.0, 28.0
    hub_x, hub_w = 40.0, 20.0
    rows = ((43.0, 56.0), (25.0, 38.0), (7.0, 20.0))
    mids = [(low + high) / 2 for low, high in rows]

    hub = add_box(ax, hub_x, rows[2][0], hub_w, rows[0][1] - rows[2][0],
                  "", (), PALE_ORANGE_FILL, ORANGE)
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
            ("pr_comments", "pr_reviews"), PALE_TEAL_FILL, TEAL,
            BOX_TITLE_SMALL_PT)
    add_box(ax, left_x, rows[2][0], left_w, 13, "pr_review_comments",
            ("inline threads",), PALE_TEAL_FILL, TEAL, BOX_TITLE_SMALL_PT)

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
    arrow(ax, (left_x + left_w, mids[1]), (hub_x, mids[1]), TEAL)
    arrow(ax, (right_x, mids[0]), (hub_x + hub_w, mids[0]), SLATE)
    arrow(ax, (right_x, mids[1]), (hub_x + hub_w, mids[1]), SLATE)
    arrow(ax, (right_x, mids[2]), (hub_x + hub_w, mids[2]), SLATE)
    join_label(ax, 35, mids[0] + 1.6, "pr_id")
    join_label(ax, 35, mids[1] + 1.6, "pr_id", TEAL)
    join_label(ax, 65, mids[0] + 1.6, "repo_id")
    join_label(ax, 65, mids[1] + 1.6, "pr_id")
    join_label(ax, 65, mids[2] + 1.6, "pr_id")

    # The indirection: inline comments join the review table, not the PR.
    arrow(ax, (9, rows[2][1]), (9, rows[1][0]), TEAL)
    join_label(ax, 12, (rows[2][1] + rows[1][0]) / 2, "review_id", TEAL,
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
    colors = [BLUE if v >= 50 else ORANGE if v >= 20 else TEAL for v in values]

    ax.barh(y, values, color=colors, height=0.62, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, label in COVERAGE_ORDER],
                       fontsize=BODY_PT, color=INK, linespacing=1.15)
    ax.invert_yaxis()
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
CHANNEL_FACE = {
    "inline_review_comment": house.TEAL,
    "submitted_review": house.PALE_ORANGE,
    "pr_comment": house.GRID,
}
CHANNEL_TEXT = {
    "inline_review_comment": house.WHITE,
    "submitted_review": house.INK,
    "pr_comment": house.INK,
}

BURST_SCHEMES = (
    ("fixed_0_minutes", "Fixed window, 0 min", False),
    ("fixed_1_minutes", "Fixed window, 1 min", False),
    ("fixed_5_minutes", "Fixed window, 5 min\n(published convention)", True),
    ("fixed_10_minutes", "Fixed window, 10 min", False),
    ("fixed_30_minutes", "Fixed window, 30 min", False),
    ("global_log_hazard_change_point", "Global change point\n0.9 min", False),
    (
        "global_log_hazard_change_point_burst_region",
        "Global, search " + "≤" + " 60 min\n0.9 min",
        False,
    ),
    ("product_specific_log_hazard_change_point", "Per product\n{span}", False),
    (
        "product_specific_log_hazard_change_point_burst_region",
        "Per product, " + "≤" + " 60 min\n{span}",
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

    fig = house.new_figure(4.15)
    layout = house.Layout(left=0.205, right=0.972, top=0.915, bottom=0.185, gap=0.140)
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
            label = f"{share:.1f}%"
            if key == "events":
                label = f"{CHANNEL_SHORT[channel]}\n{share:.1f}%"
            ax.text(
                cursor + share / 2,
                y,
                label,
                ha="center",
                va="center",
                fontsize=8.1,
                color=CHANNEL_TEXT[channel],
                linespacing=1.35,
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
        ax.text(
            boundary,
            text_y,
            f"{boundary:.1f}% can carry a reply anchor\n"
            f"{reachable:,} of {totals[key]:,} {unit}",
            ha="center",
            va="bottom" if key == "events" else "top",
            fontsize=8.1,
            color=house.INK,
            linespacing=1.3,
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
    ax.text(
        landmark_boundary - 1.8,
        bar_height / 2 + 0.15,
        f"{landmark_boundary:.1f}% in the 48 h landmark subset",
        ha="right",
        va="center",
        fontsize=8.0,
        color=house.SLATE,
        zorder=5,
    )

    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-1.15, 1.95)
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
        ("thread_root", house.TEAL, house.WHITE, "Thread root"),
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

    fig.text(
        0.006,
        0.015,
        "Channels are pr_review_comments, pr_reviews and pr_comments; only the\n"
        "first stores a parent identifier, so the other two admit no exact\n"
        "addressed edge at any threshold. Complete cross-product trigger cohort.",
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=house.SLATE,
        linespacing=1.3,
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

    def span_label(scheme: str) -> str:
        raw = str(sensitivity.loc[scheme, "threshold_minutes"])
        values = [float(part.split("=")[1]) for part in raw.split(";")]
        return f"{min(values):.3g} to {max(values):.3g} min"

    fig = house.new_figure(5.05)
    layout = house.Layout(left=0.320, right=0.985, top=0.930, bottom=0.075, gap=0.115)
    top_rect, bottom_rect = layout.rects((1.0, 0.66))

    ax = fig.add_axes(top_rect)
    GROUP_GAP = 0.85
    y_positions, labels, colours = [], [], []
    cursor = float(len(BURST_SCHEMES)) + GROUP_GAP
    previous_kind = None
    for scheme, template, published in BURST_SCHEMES:
        kind = str(sensitivity.loc[scheme, "scheme_kind"])
        fixed = kind == "fixed"
        if previous_kind is not None and fixed != (previous_kind == "fixed"):
            cursor -= GROUP_GAP
        previous_kind = kind
        y_positions.append(cursor)
        labels.append(template.format(span=span_label(scheme)) if "{span}" in template
                      else template)
        colours.append(house.TEAL if published else house.SLATE)
        cursor -= 1.0

    lows, highs = [], []
    for y, (scheme, _template, published), colour in zip(
        y_positions, BURST_SCHEMES, colours, strict=True
    ):
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
    ax.axvspan(0.0, nearest, color=house.PALE_TEAL, alpha=0.45, zorder=0, linewidth=0)
    bounds = (min(y_positions) - 0.75, max(y_positions) + 0.65)
    ax.text(
        nearest / 2.0,
        bounds[0] + 0.30,
        "no interval reaches zero",
        ha="center",
        va="bottom",
        fontsize=8.0,
        color=house.SLATE,
        zorder=4,
    )
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=8.1, linespacing=1.3)
    for tick, colour in zip(ax.get_yticklabels(), colours, strict=True):
        tick.set_color(house.INK if colour == house.TEAL else house.SLATE)
    ax.set_ylim(*bounds)
    ax.set_xlim(-1.0, max(highs) + 4.0)
    ax.set_xlabel(
        "User account " + house.MINUS + " mapped product, first owner after the "
        "burst\n(pp of PRs with a post-burst action, 95% repository-clustered CI)"
    )
    house.panel_title(ax, "A", "Every window tested leaves the same owner ahead")
    house.category_axis(ax)
    house.fit_right_labels(ax)

    ax = fig.add_axes(bottom_rect)
    minutes = histogram["bin_centre_minutes"].to_numpy()
    density = histogram["kde_density_per_log10_minute"].to_numpy()
    ax.fill_between(minutes, 0.0, density, color=house.PALE_TEAL, alpha=0.75,
                    linewidth=0, zorder=1)
    ax.plot(minutes, density, color=house.TEAL, linewidth=1.5, zorder=3)
    ax.set_xscale("log")
    top = float(density.max()) * 1.52
    for cut in (1.0, 5.0, 10.0, 30.0):
        ax.plot([cut, cut], [0.0, top * 0.72], color=house.MID, linewidth=0.8,
                linestyle=(0, (2, 2)), zorder=2)
    mode = float(gap["kde_mode_minutes"][0])
    antimode = float(gap["kde_antimode_minutes"][0])
    ax.plot([antimode, antimode], [0.0, top * 0.62], color=house.ORANGE,
            linewidth=1.0, linestyle=(0, (4, 2)), zorder=2)
    ax.plot(
        [mode],
        [float(np.interp(mode, minutes, density))],
        marker="v",
        markersize=5.0,
        markerfacecolor=house.TEAL,
        markeredgecolor=house.WHITE,
        markeredgewidth=0.6,
        zorder=4,
    )
    ax.text(
        mode,
        float(np.interp(mode, minutes, density)) + top * 0.06,
        f"one rising mode at {mode:.1f} min;\nno valley to cut at",
        ha="center",
        va="bottom",
        fontsize=8.1,
        color=house.TEAL,
        linespacing=1.3,
        zorder=4,
    )
    ax.text(
        antimode,
        top * 0.64,
        "the only valley is the\novernight gap at "
        f"{antimode / 60.0:.1f} h",
        ha="center",
        va="bottom",
        fontsize=8.0,
        color=house.ORANGE,
        linespacing=1.3,
        zorder=4,
    )
    ax.text(
        1.0,
        top * 0.74,
        "fixed windows tested (min)",
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=house.SLATE,
        zorder=4,
    )
    ax.set_xlim(0.02, 12000)
    ax.set_ylim(0.0, top)
    ax.set_xticks([0.1, 1, 10, 100, 1000, 10000])
    ax.set_xticklabels(["0.1", "1", "10", "100", "1,000", "10,000"])
    ax.set_yticks([])
    ax.set_xlabel(
        "Minutes from the trigger to the next public event (log scale), "
        f"median {float(shape['quantile_50_minutes']):.1f} min"
    )
    ax.set_ylabel("Density per\nlog" + "₁₀" + " minute")
    house.panel_title(ax, "B", "No cut is privileged by the data")
    house.clean_axis(ax, "y")
    ax.spines["left"].set_visible(False)

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
    schema_fig.text(
        0.01,
        0.016,
        "Join on identifiers, never on row order. Inline comments reach a PR "
        "through their review batch.",
        fontsize=NOTE_PT,
        color=SLATE,
        ha="left",
        va="bottom",
    )
    save(schema_fig, args.output_dir, "dataset_schema_and_joins")

    coverage_fig = plt.figure(figsize=(FIGURE_WIDTH, 3.05))
    coverage_ax = coverage_fig.add_axes([0.185, 0.155, 0.795, 0.700])
    draw_coverage(coverage_ax, coverage)
    coverage_fig.text(
        0.01,
        0.028,
        "Coverage is observed availability, not random sampling. "
        "Denominators are declared per model.",
        fontsize=NOTE_PT,
        color=SLATE,
        ha="left",
        va="bottom",
    )
    save(coverage_fig, args.output_dir, "dataset_feature_coverage")

    # One combined overview is retained for artifact browsing. The manuscript
    # uses the two standalone files above so their labels are not scaled down.
    fig = plt.figure(figsize=(7.2, 8.0))
    schema_panel = fig.add_axes([0.02, 0.475, 0.96, 0.505])
    draw_schema(schema_panel, panel="A")
    coverage_panel = fig.add_axes([0.145, 0.085, 0.825, 0.300])
    draw_coverage(coverage_panel, coverage, panel="B")
    fig.text(
        0.02,
        0.022,
        "Join on identifiers, never on row order. Rich-table coverage is "
        "observed availability, not random sampling.",
        fontsize=NOTE_PT,
        color=SLATE,
        ha="left",
        va="bottom",
    )
    save(fig, args.output_dir, "dataset_map_and_coverage")

    # The two evidence figures below replace appendix tables, so they follow the
    # manuscript house style rather than the schema style used above.
    with plt.rc_context(HOUSE_RC):
        house.assert_palette_contrast()
        stems = [
            figure_anchorable_coverage(args.output_dir),
            figure_burst_threshold_sensitivity(args.output_dir),
        ]
    proofs = write_house_colour_proofs(stems, args.output_dir)
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
