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
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.text import Text  # noqa: E402


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


if __name__ == "__main__":
    main()
