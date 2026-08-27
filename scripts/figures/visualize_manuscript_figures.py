"""Render the five manuscript figures at their final printed size.

The Springer Nature ``sn-jnl`` text block is 372 pt wide. Every figure here is
exported at exactly that width, so ``\\includegraphics[width=\\linewidth]``
reproduces it at scale 1.0 and a 7.2 pt label really prints at 7.2 pt. Panels
inside one figure share an identical axes rectangle, so their frames, tick rows
and category columns line up down the page.

Each figure ends in an automated geometry gate: no artist may fall outside the
canvas, no annotation may sit below the print floor, and no two annotations
inside a panel may overlap. A layout regression therefore fails the build
instead of reaching the PDF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = ROOT / "outputs" / "coordination_topology"
BURST = ROOT / "outputs" / "burst_topology"
HISTORY = ROOT / "outputs" / "human_memory_bridge"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
SPECIFICITY = ROOT / "outputs" / "addressed_edge_specificity"
SENSITIVITY = ROOT / "outputs" / "addressed_edge_sensitivity"
SCOPE = ROOT / "outputs" / "addressed_edge_scope"
EXTENSIONS = ROOT / "outputs" / "rq3_extensions"
CONTEXT = ROOT / "outputs" / "task_context_interaction"
CURVES = ROOT / "outputs" / "merge_curves"
OUTPUT = ROOT / "build" / "figures"

# Palette. Every hue is taken unaltered from Paul Tol's colour schemes, whose
# qualitative sets are constructed to stay distinguishable under the three
# dichromacies; the "dark" set is the one Tol specifies for text and lines on
# white, and the "pale" set is the one he specifies as a background for black
# text. The neutral ink is the black of the Okabe-Ito colour-universal-design
# palette. Values transcribed from:
#   https://sronpersonalpages.nl/~pault/
#   https://jfly.uni-koeln.de/color/
#
#   Role                                   Constant       Tol scheme
#   text, axes, primary neutral marks      INK            Okabe-Ito black
#   mapped / same-product reference        BLUE           muted indigo
#   cross-product boundary contrast        ORANGE         dark gold
#   addressed edge, user-account ownership TEAL           dark teal
#   context and comparison groups          SLATE          dark grey
#   spines, connectors, leader lines       MID            light grey
#   grid, separators, lollipop stems       GRID           pale grey
#   pale fills carrying black text         PALE_*         pale scheme
INK = "#000000"
BLUE = "#332288"
ORANGE = "#775500"
TEAL = "#117788"
SLATE = "#444444"
MID = "#BBBBBB"
GRID = "#DDDDDD"
PALE_BLUE = "#AACCEE"
PALE_TEAL = "#CCEEFF"
PALE_ORANGE = "#EEEEBB"
WHITE = "#FFFFFF"

TEXT_COLOURS = (INK, BLUE, ORANGE, TEAL, SLATE)
PALE_FILLS = (PALE_BLUE, PALE_TEAL, PALE_ORANGE, GRID)

MIN_CONTRAST_RATIO = 4.5
MIN_FILL_CONTRAST_RATIO = 1.15
RELATIVE_LUMINANCE = np.array([0.2126, 0.7152, 0.0722])

# Dichromacy simulation matrices at severity 1.0, Machado, Oliveira and
# Fernandes (2009), "A Physiologically-based Model for Simulation of Color
# Vision Deficiency", Table 1. They act on linear RGB, so proofs linearise the
# rendered PNG first.
#   https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html
CVD_MATRICES = {
    "deuteranopia": np.array(
        [
            [0.367322, 0.860646, -0.227968],
            [0.280085, 0.672501, 0.047413],
            [-0.011820, 0.042940, 0.968881],
        ]
    ),
    "protanopia": np.array(
        [
            [0.152286, 1.052583, -0.204868],
            [0.114503, 0.786281, 0.099216],
            [-0.003882, -0.048116, 1.051998],
        ]
    ),
    "tritanopia": np.array(
        [
            [1.255528, -0.076749, -0.178779],
            [-0.078411, 0.930809, 0.147602],
            [0.004733, 0.691367, 0.303900],
        ]
    ),
}

POINTS_PER_INCH = 72.0
TEXT_WIDTH_PT = 372.0
FIGURE_WIDTH = TEXT_WIDTH_PT / POINTS_PER_INCH

MIN_TEXT_POINTS = 7.0
MINUS = "\u2212"


def minus(value: str) -> str:
    """Use the typographic minus sign, matching the manuscript body text."""
    return value.replace("-", MINUS)

plt.rcParams.update(
    {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "font.family": "DejaVu Sans",
        "font.size": 7.6,
        "axes.titlesize": 8.8,
        "axes.titleweight": "bold",
        "axes.labelsize": 7.9,
        "xtick.labelsize": 7.2,
        "ytick.labelsize": 7.2,
        "legend.fontsize": 7.2,
        "text.color": INK,
        "axes.labelcolor": INK,
        "axes.edgecolor": MID,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.linewidth": 0.7,
        "lines.solid_capstyle": "round",
        "figure.facecolor": WHITE,
        "axes.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "savefig.pad_inches": 0.0,
    }
)


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def read_csv(path: Path, columns: Iterable[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(
            f"{path.relative_to(ROOT)} is missing columns: {sorted(missing)}"
        )
    if frame.empty:
        raise ValueError(f"No rows in {path.relative_to(ROOT)}")
    return frame


def exactly_one(frame: pd.DataFrame, **conditions: object) -> pd.Series:
    mask = np.ones(len(frame), dtype=bool)
    for column, value in conditions.items():
        mask &= frame[column].astype(str).eq(str(value)).to_numpy()
    selected = frame.loc[mask]
    if len(selected) != 1:
        raise ValueError(f"Expected one row for {conditions}, found {len(selected)}")
    return selected.iloc[0]


# ---------------------------------------------------------------------------
# Shared layout primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """Figure-relative axes rectangle shared by every panel in one figure."""

    left: float
    right: float
    top: float
    bottom: float
    gap: float

    def rects(
        self, weights: Sequence[float]
    ) -> list[tuple[float, float, float, float]]:
        total = sum(weights)
        available = self.top - self.bottom - self.gap * (len(weights) - 1)
        if available <= 0:
            raise ValueError("Panel gaps consume the whole canvas")
        width = self.right - self.left
        rects = []
        cursor = self.top
        for weight in weights:
            height = available * weight / total
            cursor -= height
            rects.append((self.left, cursor, width, height))
            cursor -= self.gap
        return rects


def panel_title(ax: plt.Axes, letter: str, title: str) -> None:
    ax.set_title(f"{letter}  {title}", loc="left", pad=6.0, color=INK)


def clean_axis(ax: plt.Axes, grid_axis: str = "x") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.4, width=0.6)


def category_axis(ax: plt.Axes) -> None:
    """Style a horizontal dot or bar panel: labels, not a left spine, anchor it."""
    clean_axis(ax, "x")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=4)


def lollipop(
    ax: plt.Axes,
    y: float,
    start: float,
    value: float,
    marker: str,
    face: str,
    edge: str,
    edge_width: float = 1.0,
    size: float = 46.0,
) -> None:
    ax.hlines(y, start, value, color=GRID, linewidth=1.9, zorder=1)
    ax.scatter(
        value,
        y,
        s=size,
        marker=marker,
        facecolor=face,
        edgecolor=edge,
        linewidth=edge_width,
        zorder=3,
        clip_on=False,
    )


def fit_right_labels(ax: plt.Axes, pad_fraction: float = 0.035) -> None:
    """Widen the x-axis until every right-anchored annotation fits inside it.

    Annotation width is a typographic quantity, not a data quantity, so it
    cannot be reserved by guessing a numeric margin. This measures the rendered
    text and converts it back into data units.
    """
    figure = ax.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    left, right = ax.get_xlim()
    if right <= left:
        raise ValueError("fit_right_labels needs an increasing x-axis")
    needed = right
    for text in ax.texts:
        if text.get_horizontalalignment() != "left":
            continue
        if text.get_transform() is not ax.transData:
            continue
        box = text.get_window_extent(renderer=renderer)
        edge = ax.transData.inverted().transform((box.x1, box.y0))[0]
        needed = max(needed, edge)
    padded = left + (needed - left) * (1.0 + pad_fraction)
    if padded > right:
        ax.set_xlim(left, padded)


# ---------------------------------------------------------------------------
# Export and geometry gate
# ---------------------------------------------------------------------------


def assert_layout(fig: plt.Figure, stem: str) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    tolerance = 0.6

    candidates: list[Text] = list(fig.texts)
    for ax in fig.axes:
        candidates.extend(ax.texts)
        candidates.extend([ax.title, ax.xaxis.label, ax.yaxis.label])
        if ax.axison:
            candidates.extend(ax.get_xticklabels())
            candidates.extend(ax.get_yticklabels())

    for text in candidates:
        content = text.get_text()
        if not content.strip() or not text.get_visible():
            continue
        if text.get_fontsize() < MIN_TEXT_POINTS - 1e-6:
            raise AssertionError(
                f"{stem}: '{content[:32]}' is {text.get_fontsize():.1f} pt, "
                f"below the {MIN_TEXT_POINTS} pt print floor"
            )
        box = text.get_window_extent(renderer=renderer)
        if (
            box.x0 < canvas.x0 - tolerance
            or box.x1 > canvas.x1 + tolerance
            or box.y0 < canvas.y0 - tolerance
            or box.y1 > canvas.y1 + tolerance
        ):
            raise AssertionError(
                f"{stem}: text '{content[:32]}' is clipped by the canvas edge"
            )

    for ax in fig.axes:
        boxes = []
        for text in ax.texts:
            if not text.get_text().strip() or not text.get_visible():
                continue
            boxes.append((text.get_text(), text.get_window_extent(renderer=renderer)))
        for index, (first_label, first) in enumerate(boxes):
            for second_label, second in boxes[index + 1 :]:
                overlap_x = min(first.x1, second.x1) - max(first.x0, second.x0)
                overlap_y = min(first.y1, second.y1) - max(first.y0, second.y0)
                if overlap_x > 1.0 and overlap_y > 1.0:
                    raise AssertionError(
                        f"{stem}: annotations '{first_label[:24]}' and "
                        f"'{second_label[:24]}' overlap"
                    )


def save(fig: plt.Figure, stem: str) -> None:
    try:
        assert_layout(fig, stem)
    except AssertionError:
        debug = ROOT / "build" / "qa" / "figure_qa_debug"
        debug.mkdir(parents=True, exist_ok=True)
        fig.savefig(debug / f"{stem}.png", dpi=300)
        raise
    OUTPUT.mkdir(parents=True, exist_ok=True)
    metadata = {
        "Title": stem,
        "Author": "Dao Sy Duy Minh et al.",
        "Subject": "Public coordination topology after cross-product agent review",
        "Creator": "Matplotlib",
    }
    fig.savefig(OUTPUT / f"{stem}.pdf", metadata=metadata)
    fig.savefig(OUTPUT / f"{stem}.png", dpi=400)
    plt.close(fig)


def new_figure(height: float) -> plt.Figure:
    return plt.figure(figsize=(FIGURE_WIDTH, height))


# ---------------------------------------------------------------------------
# Colour gate and colour-vision proofs
# ---------------------------------------------------------------------------


def srgb_to_linear(values: np.ndarray) -> np.ndarray:
    return np.where(
        values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4
    )


def linear_to_srgb(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    return np.where(
        clipped <= 0.0031308,
        clipped * 12.92,
        1.055 * clipped ** (1 / 2.4) - 0.055,
    )


def luminance(colour: str) -> float:
    return float(RELATIVE_LUMINANCE @ srgb_to_linear(np.array(to_rgb(colour))))


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def assert_palette_contrast() -> None:
    """Fail before rendering if a palette entry is illegible at print size.

    Every hue that carries text has to clear the WCAG 4.5:1 ratio against the
    white page, and every pale fill has to stay visibly tinted against that
    same page while still holding black text.
    """
    for colour in TEXT_COLOURS:
        ratio = contrast(colour, WHITE)
        if ratio < MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{colour} reaches only {ratio:.2f}:1 on white, "
                f"below the {MIN_CONTRAST_RATIO}:1 text floor"
            )
    for colour in PALE_FILLS:
        against_page = contrast(colour, WHITE)
        if against_page < MIN_FILL_CONTRAST_RATIO:
            raise AssertionError(
                f"fill {colour} reaches only {against_page:.2f}:1 against the "
                "page and washes out at print size"
            )
        holding_text = contrast(colour, INK)
        if holding_text < MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"fill {colour} holds ink at only {holding_text:.2f}:1"
            )


def write_colour_proofs(stems: Sequence[str]) -> list[str]:
    """Re-render every exported PNG under dichromacy and in greyscale."""
    directory = ROOT / "build" / "qa" / "colour"
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem in stems:
        source = OUTPUT / f"{stem}.png"
        if not source.is_file():
            raise FileNotFoundError(source)
        linear = srgb_to_linear(plt.imread(source)[:, :, :3].astype(float))
        for name, matrix in CVD_MATRICES.items():
            path = directory / f"{stem}_{name}.png"
            plt.imsave(path, linear_to_srgb(linear @ matrix.T))
            written.append(path.name)
        grey = linear @ RELATIVE_LUMINANCE
        path = directory / f"{stem}_greyscale.png"
        plt.imsave(path, linear_to_srgb(np.repeat(grey[:, :, None], 3, axis=2)))
        written.append(path.name)
    return sorted(written)


# ---------------------------------------------------------------------------
# Figure 1: measurement contract
# ---------------------------------------------------------------------------


def figure_measurement_contract() -> None:
    """Schematic of the event anchor, exclusion rules, and observation windows.

    The figure is structural. It carries no cohort estimate, so it is drawn
    from the analysis contract rather than from a results table.
    """
    fig = new_figure(3.20)
    layout = Layout(left=0.030, right=0.985, top=0.890, bottom=0.045, gap=0.085)
    top_rect, bottom_rect = layout.rects((1.0, 0.72))

    ax = fig.add_axes(top_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "A", "One trigger, three exclusion rules")

    timeline_y = 3.4
    marker_y = 5.4
    label_y = 6.05

    ax.add_patch(
        Rectangle(
            (35.0, timeline_y),
            11.0,
            marker_y - timeline_y + 0.5,
            facecolor=PALE_ORANGE,
            edgecolor="none",
            zorder=0,
        )
    )
    ax.annotate(
        "",
        xy=(99.0, timeline_y),
        xytext=(2.0, timeline_y),
        arrowprops={"arrowstyle": "-|>", "color": INK, "linewidth": 0.9},
    )

    def event(x: float, color: str, face: str, marker: str) -> None:
        ax.plot(
            [x, x],
            [timeline_y + 0.12, marker_y - 0.45],
            color=MID,
            linewidth=0.6,
            linestyle=(0, (1.6, 1.6)),
            zorder=2,
        )
        ax.scatter(x, timeline_y, s=10, color=INK, zorder=4)
        ax.scatter(
            x,
            marker_y,
            s=40,
            marker=marker,
            facecolor=face,
            edgecolor=color,
            linewidth=1.1,
            zorder=4,
        )

    events = [
        (9.0, BLUE, BLUE, "o", "Trigger", BLUE),
        (24.0, BLUE, WHITE, "o", "Same batch:\nnot a reply", SLATE),
        (40.0, ORANGE, ORANGE, "^", "Rapid burst:\nexcluded", ORANGE),
        (60.0, TEAL, TEAL, "o", "Exact parent\nreply", TEAL),
    ]
    for x, color, face, marker, label, label_color in events:
        event(x, color, face, marker)
        ax.text(
            x, label_y, label, ha="center", va="bottom", fontsize=7.1, color=label_color
        )

    # The review-batch bracket sits under the timeline so that it cannot
    # collide with the annotation row above it.
    ax.plot([6.0, 27.0], [2.15, 2.15], color=BLUE, linewidth=0.9)
    ax.plot([6.0, 6.0], [2.15, 2.65], color=BLUE, linewidth=0.9)
    ax.plot([27.0, 27.0], [2.15, 2.65], color=BLUE, linewidth=0.9)
    ax.text(
        16.5,
        1.75,
        "one submitted review batch",
        ha="center",
        va="top",
        fontsize=7.0,
        color=BLUE,
    )

    ax.annotate(
        "",
        xy=(60.0, 8.85),
        xytext=(9.0, 8.85),
        arrowprops={"arrowstyle": "-|>", "color": TEAL, "linewidth": 1.1},
    )
    ax.text(
        34.5,
        9.1,
        "reply parent identifier equals the trigger identifier",
        ha="center",
        va="bottom",
        fontsize=7.0,
        color=TEAL,
    )

    ax.plot([78.0, 78.0], [timeline_y, 6.6], color=INK, linewidth=1.0)
    ax.text(
        78.0, 6.8, "hour 48 landmark", ha="center", va="bottom", fontsize=7.1, color=INK
    )
    ax.annotate(
        "",
        xy=(98.0, 2.15),
        xytext=(78.0, 2.15),
        arrowprops={"arrowstyle": "-|>", "color": SLATE, "linewidth": 0.9},
    )
    ax.text(
        88.0,
        1.75,
        "later merge, to day 30",
        ha="center",
        va="top",
        fontsize=7.0,
        color=SLATE,
    )

    ax = fig.add_axes(bottom_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "B", "Four evidence levels, read separately")

    levels = [
        ("Product presence", "two products\non one PR", PALE_BLUE, BLUE),
        ("Addressed edge", "reply points at\nthe trigger", PALE_TEAL, TEAL),
        ("Next owner", "first actor after\nthe burst", PALE_TEAL, TEAL),
        ("Later state", "merge only after\nhour 48", GRID, SLATE),
    ]
    box_width = 22.0
    gap = (100.0 - len(levels) * box_width) / (len(levels) - 1)
    for index, (name, rule, face, edge) in enumerate(levels):
        x = index * (box_width + gap)
        ax.add_patch(
            FancyBboxPatch(
                (x, 3.6),
                box_width,
                5.6,
                boxstyle="round,pad=0.2,rounding_size=0.9",
                facecolor=face,
                edgecolor=edge,
                linewidth=0.8,
            )
        )
        ax.text(
            x + box_width / 2,
            7.9,
            name,
            ha="center",
            va="center",
            fontsize=7.3,
            color=INK,
            fontweight="bold",
        )
        ax.text(
            x + box_width / 2,
            5.3,
            rule,
            ha="center",
            va="center",
            fontsize=7.0,
            color=INK,
        )
        if index < len(levels) - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_width + 0.5, 6.4),
                    (x + box_width + gap - 0.5, 6.4),
                    arrowstyle="-|>",
                    mutation_scale=6,
                    color=SLATE,
                    linewidth=0.9,
                )
            )
    ax.text(
        50.0,
        1.3,
        "A level never implies the level to its right. None of them observes a private "
        "run,\na shared plan, or whether the review point was understood.",
        ha="center",
        va="center",
        fontsize=7.0,
        color=SLATE,
    )

    save(fig, "Fig1_v2")


# ---------------------------------------------------------------------------
# Figure 2: RQ1 participation and next owner
# ---------------------------------------------------------------------------


def figure_participation() -> None:
    funnel = read_csv(
        TOPOLOGY / "participation_funnel.csv",
        ("stage", "prs", "share_of_trigger_cohort"),
    ).set_index("stage")
    burst = read_csv(
        BURST / "burst_topology_summary.csv",
        (
            "burst_threshold_minutes",
            "first_post_burst_state",
            "prs",
            "share_post_burst_actions",
        ),
    )

    stage_order = [
        "Complete cross-product trigger cohort",
        "Any later visible action",
        "Exact reply to the trigger",
        "Mapped different-product exact reply",
    ]
    stage_labels = [
        "Cross-product\nfeedback",
        "Any later\npublic action",
        "Exact parent\nreply",
        "Different-product\nexact reply",
    ]
    if not set(stage_order).issubset(funnel.index):
        raise ValueError(
            "Participation funnel does not contain the four declared stages"
        )
    shares = funnel.loc[stage_order, "share_of_trigger_cohort"].to_numpy() * 100
    counts = funnel.loc[stage_order, "prs"].astype(int).to_numpy()

    fig = new_figure(4.55)
    layout = Layout(left=0.215, right=0.775, top=0.925, bottom=0.085, gap=0.135)
    top_rect, bottom_rect = layout.rects((1.0, 1.35))

    ax = fig.add_axes(top_rect)
    y = np.arange(4)[::-1]
    for position, share, count, color in zip(
        y, shares, counts, (BLUE, PALE_BLUE, TEAL, ORANGE), strict=True
    ):
        ax.barh(
            position,
            share,
            height=0.5,
            color=color,
            edgecolor=INK,
            linewidth=0.35,
            zorder=2,
        )
        inside = share > 60
        reversed_out = inside and contrast(color, WHITE) >= MIN_CONTRAST_RATIO
        ax.text(
            share - 1.8 if inside else share + 1.8,
            position,
            f"{share:.1f}%  ·  {count:,} PRs",
            ha="right" if inside else "left",
            va="center",
            fontsize=7.2,
            color=WHITE if reversed_out else INK,
        )
    ax.set_yticks(y, stage_labels)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.6, 3.6)
    ax.set_xlabel("Share of the complete trigger cohort (%)")
    panel_title(ax, "A", "Participation narrows before a connected edge")
    category_axis(ax)
    fit_right_labels(ax)

    ax = fig.add_axes(bottom_rect)
    thresholds = [0, 1, 5, 10, 30]
    positions = np.arange(len(thresholds), dtype=float)
    contract = [
        ("user_account", "User account", TEAL, "o", "-"),
        ("mapped_product", "Mapped product", BLUE, "s", "-"),
        ("other_bot", "Other bot", ORANGE, "^", "--"),
        ("branch_movement_untyped", "Branch movement", SLATE, "D", ":"),
    ]
    values_by_state: dict[str, np.ndarray] = {}
    for state, _label, color, marker, style in contract:
        subset = burst[burst["first_post_burst_state"] == state].set_index(
            "burst_threshold_minutes"
        )
        if not set(thresholds).issubset(subset.index):
            raise ValueError(f"Burst profile is missing a threshold for {state}")
        values = subset.loc[thresholds, "share_post_burst_actions"].to_numpy() * 100
        values_by_state[state] = values
        ax.plot(
            positions,
            values,
            color=color,
            marker=marker,
            linestyle=style,
            linewidth=1.5,
            markersize=4.0,
            markeredgecolor=WHITE,
            markeredgewidth=0.5,
            clip_on=False,
            zorder=3,
        )

    # Direct labels replace a legend, so they must not collide. Each label is
    # anchored to its own line and then pushed apart by the minimum readable
    # spacing, with a leader line whenever it had to move.
    endpoints = {state: values_by_state[state][-1] for state, *_ in contract}
    minimum_gap = 6.4
    resolved: dict[str, float] = {}
    previous = -np.inf
    for state, value in sorted(endpoints.items(), key=lambda item: item[1]):
        placed = max(value, previous + minimum_gap)
        resolved[state] = placed
        previous = placed
    for state, label, color, _marker, _style in contract:
        ax.text(
            positions[-1] + 0.16,
            resolved[state],
            label,
            va="center",
            ha="left",
            fontsize=7.2,
            color=color if state != "branch_movement_untyped" else INK,
        )
        if abs(resolved[state] - endpoints[state]) > 0.4:
            ax.plot(
                [positions[-1] + 0.04, positions[-1] + 0.13],
                [endpoints[state], resolved[state]],
                color=MID,
                linewidth=0.6,
                clip_on=False,
                zorder=2,
            )

    ax.axvline(2, color=MID, linewidth=0.8, linestyle=(0, (2, 2)), zorder=0)
    user_at_five = values_by_state["user_account"][2]
    product_at_five = values_by_state["mapped_product"][2]
    ax.annotate(
        f"{user_at_five:.0f}%",
        (2, user_at_five),
        xytext=(2.16, user_at_five + 5.5),
        fontsize=7.4,
        fontweight="bold",
        color=TEAL,
        arrowprops={"arrowstyle": "-", "color": TEAL, "linewidth": 0.7},
    )
    ax.annotate(
        f"{product_at_five:.0f}%",
        (2, product_at_five),
        xytext=(1.84, product_at_five + 5.5),
        ha="right",
        fontsize=7.4,
        fontweight="bold",
        color=BLUE,
        arrowprops={"arrowstyle": "-", "color": BLUE, "linewidth": 0.7},
    )

    visible = [item[0] for item in contract]
    remaining = int(
        burst[
            (burst["burst_threshold_minutes"] == 5)
            & burst["first_post_burst_state"].isin(visible)
        ]["prs"].sum()
    )
    ax.text(
        0.02,
        0.035,
        f"At 5 min: {remaining:,} PRs still have an action",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.2,
        color=SLATE,
    )
    ax.set_xlim(-0.06, 4.0)
    ax.set_ylim(0, 66)
    ax.set_xticks(positions, [str(value) for value in thresholds])
    ax.set_xlabel("Tested burst window (minutes)")
    ax.set_ylabel("Share of PRs with an action left (%)")
    panel_title(ax, "B", "After the burst, user accounts lead")
    clean_axis(ax, "y")

    save(fig, "Fig2_v2")


# ---------------------------------------------------------------------------
# Figure 3: RQ2 boundary visibility and public history
# ---------------------------------------------------------------------------


def figure_boundary() -> None:
    contrast = exactly_one(
        read_csv(
            TOPOLOGY / "matched_visibility_contrasts.csv",
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
        ),
        specification="exact_author_user",
        outcome="any_visible_followup",
    )
    mediator = exactly_one(
        read_csv(
            HISTORY / "first_mediator_role_summary.csv",
            ("account_role", "prs", "prior_reviewer_share"),
        ),
        account_role="all_first_mediators",
    )
    decisive = exactly_one(
        read_csv(
            HISTORY / "first_decisive_reviewer_role_summary.csv",
            ("account_role", "prs", "prior_reviewer_share"),
        ),
        account_role="all_first_decisive_reviewers",
    )
    responders = exactly_one(
        read_csv(
            HISTORY / "observable_population_baselines.csv",
            ("population", "rows", "prior_reviewer_share"),
        ),
        population="all_distinct_48h_user_responders",
    )

    fig = new_figure(4.10)
    layout = Layout(left=0.275, right=0.80, top=0.915, bottom=0.095, gap=0.165)
    top_rect, bottom_rect = layout.rects((0.62, 1.0))

    ax = fig.add_axes(top_rect)
    same = float(contrast["same_rate"]) * 100
    cross = float(contrast["cross_rate"]) * 100
    ax.hlines(1.0, cross, same, color=MID, linewidth=2.0, zorder=1)
    ax.scatter(
        same,
        1.0,
        s=52,
        facecolor=WHITE,
        edgecolor=BLUE,
        linewidth=1.6,
        marker="o",
        zorder=3,
    )
    ax.scatter(
        cross,
        1.0,
        s=54,
        facecolor=ORANGE,
        edgecolor=ORANGE,
        linewidth=1.0,
        marker="^",
        zorder=3,
    )
    ax.set_yticks([1.0], ["Matched pairs"])
    ax.set_ylim(0.0, 2.35)
    ax.set_xlim(60, 88)
    ax.text(
        same,
        1.30,
        f"Same-product  {same:.1f}%",
        ha="center",
        va="bottom",
        color=BLUE,
        fontsize=7.2,
    )
    ax.text(
        cross,
        0.70,
        f"Cross-product  {cross:.1f}%",
        ha="center",
        va="top",
        color=ORANGE,
        fontsize=7.2,
    )

    difference = float(contrast["paired_difference"]) * 100
    low = float(contrast["repository_cluster_bootstrap_ci_low"]) * 100
    high = float(contrast["repository_cluster_bootstrap_ci_high"]) * 100
    ax.text(
        0.015,
        0.98,
        minus(
            f"Cross − same: {difference:+.1f} pp   95% interval "
            f"[{low:+.1f}, {high:+.1f}]"
        ),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=7.3,
        fontweight="bold",
        color=INK,
    )
    ax.text(
        0.985,
        0.03,
        f"{int(contrast['pairs']):,} pairs · "
        f"{int(contrast['repositories']):,} repositories",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.1,
        color=SLATE,
    )
    ax.set_xlabel("PRs with any later public action (%)")
    panel_title(ax, "A", "The matched product boundary is quieter")
    category_axis(ax)

    ax = fig.add_axes(bottom_rect)
    rows = [
        (
            "First decisive reviewer",
            decisive["prior_reviewer_share"],
            int(decisive["prs"]),
            "s",
            TEAL,
            TEAL,
            1.0,
        ),
        (
            "First user bridge",
            mediator["prior_reviewer_share"],
            int(mediator["prs"]),
            "o",
            TEAL,
            TEAL,
            1.0,
        ),
        (
            "Any 48-hour responder",
            responders["prior_reviewer_share"],
            int(responders["rows"]),
            "o",
            WHITE,
            SLATE,
            1.5,
        ),
    ]
    y = np.arange(len(rows))[::-1]
    for position, row in zip(y, rows, strict=True):
        label, share, count, marker, face, edge, width = row
        value = float(share) * 100
        lollipop(ax, position, 60, value, marker, face, edge, width)
        ax.text(
            value + 0.95,
            position,
            f"{value:.1f}%  ·  n={count:,}",
            ha="left",
            va="center",
            fontsize=7.2,
            color=INK,
        )
    ax.set_yticks(y, [row[0] for row in rows])
    ax.set_xlim(60, 82)
    ax.set_ylim(-0.6, 2.6)
    ax.set_xlabel("Accounts with a strict prior review in this repository (%)")
    panel_title(ax, "B", "History is common across user responders")
    category_axis(ax)
    fit_right_labels(ax)

    save(fig, "Fig3_v2")


# ---------------------------------------------------------------------------
# Figure 4: RQ3 as a shape over time, not a coefficient
# ---------------------------------------------------------------------------


def figure_merge_curves() -> None:
    columns = ["days_since_trigger"]
    for arm in ("no_reply", "reply_off_target", "reply_on_target"):
        columns += [f"merged_{arm}", f"merged_{arm}_low", f"merged_{arm}_high"]
    curve = read_csv(CURVES / "cumulative_merge.csv", tuple(columns))
    summary = json.loads((CURVES / "summary.json").read_text(encoding="utf-8"))

    fig = new_figure(3.7)
    layout = Layout(left=0.135, right=0.985, top=0.9, bottom=0.135, gap=0.0)
    (rect,) = layout.rects((1.0,))
    ax = fig.add_axes(rect)

    days = curve["days_since_trigger"].to_numpy()
    series = (
        ("reply_off_target", ORANGE, (0, (5, 1.6)), "reply anchored elsewhere", 1.0),
        ("reply_on_target", TEAL, "-", "reply on the trigger thread", -1.0),
        ("no_reply", SLATE, (0, (2, 2)), "no inline reply", 0.0),
    )
    for arm, colour, style, label, _ in series:
        low = curve[f"merged_{arm}_low"].to_numpy() * 100
        high = curve[f"merged_{arm}_high"].to_numpy() * 100
        ax.fill_between(days, low, high, color=colour, alpha=0.14, linewidth=0)

    ends = {}
    for arm, colour, style, label, _ in series:
        centre = curve[f"merged_{arm}"].to_numpy() * 100
        ends[arm] = centre[-1]
        ax.plot(days, centre, color=colour, linewidth=1.8, linestyle=style, zorder=3)

    handles = [
        Line2D(
            [],
            [],
            color=colour,
            linewidth=1.8,
            linestyle=style,
            label=f"{label}  {ends[arm]:.0f}%",
        )
        for arm, colour, style, label, _ in series
    ]
    legend = ax.legend(
        handles=handles,
        loc="lower right",
        bbox_to_anchor=(0.995, 0.04),
        frameon=False,
        fontsize=7.2,
        handlelength=2.6,
        labelspacing=0.42,
        borderpad=0.0,
        title="Merged by day 30",
    )
    legend.get_title().set_fontsize(7.2)
    legend.get_title().set_color(SLATE)
    legend.get_title().set_ha("left")

    ax.axvline(2.0, color=MID, linewidth=0.8, linestyle=(0, (2, 2)), zorder=0)
    ax.text(2.3, 12, "hour 48", ha="left", va="center", fontsize=7.1, color=SLATE)

    ax.set_xlim(0, 30.5)
    ax.set_ylim(0, 100)
    ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Days after the cross-product review comment")
    ax.set_ylabel("Pull requests merged (%)")
    panel_title(ax, "", "A reply matters; where it is anchored does not")
    clean_axis(ax, "y")
    ax.text(
        0.015,
        0.955,
        f"{int(summary['population_prs']):,} PRs across "
        f"{int(summary['repositories']):,} repositories",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=7.1,
        color=SLATE,
    )

    save(fig, "Fig4_v2")


# ---------------------------------------------------------------------------
# Figure 5: how much hidden structure would remove the RQ3 result
# ---------------------------------------------------------------------------


def figure_sensitivity() -> None:
    evalues = read_csv(
        SENSITIVITY / "e_values.csv",
        ("threshold_hours", "e_value_point", "e_value_limit"),
    )
    frontier = read_csv(
        SENSITIVITY / "unmeasured_confounder_frontier.csv",
        (
            "prevalence_difference",
            "outcome_difference_to_remove_point_estimate",
            "outcome_difference_to_remove_interval",
        ),
    )
    permutation = read_csv(
        SCOPE / "conditional_randomisation_inference.csv",
        ("threshold_hours", "permutation_p_value_two_sided", "repositories"),
    )
    primary = exactly_one(evalues, threshold_hours="48")
    test = exactly_one(permutation, threshold_hours="48")

    fig = new_figure(3.35)
    layout = Layout(left=0.135, right=0.985, top=0.900, bottom=0.150, gap=0.0)
    (rect,) = layout.rects((1.0,))
    ax = fig.add_axes(rect)

    delta = frontier["prevalence_difference"].to_numpy() * 100
    point_line = frontier["outcome_difference_to_remove_point_estimate"].to_numpy() * 100
    interval_line = frontier["outcome_difference_to_remove_interval"].to_numpy() * 100
    ax.fill_between(delta, point_line, 100, color=PALE_TEAL, alpha=0.75, zorder=0)
    ax.plot(delta, point_line, color=TEAL, linewidth=1.8, zorder=3)
    ax.plot(
        delta, interval_line, color=SLATE, linewidth=1.4, linestyle=(0, (4, 2)), zorder=3
    )
    ax.set_xlim(5, 60)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("How much more common the hidden cause is among answered PRs (pp)")
    ax.set_ylabel("Its own effect on\nlater merge (pp)")
    panel_title(ax, "", "A hidden cause would have to be large and lopsided")
    clean_axis(ax, "y")
    ax.text(
        40.0,
        74.0,
        "only in here does\nthe result disappear",
        ha="center",
        va="center",
        fontsize=7.2,
        color=TEAL,
    )
    ax.text(
        33.0,
        7.0,
        "enough to blur the interval",
        ha="center",
        va="center",
        fontsize=7.1,
        color=SLATE,
    )
    ax.text(
        0.985,
        0.955,
        f"E-value {float(primary['e_value_point']):.2f}, "
        f"{float(primary['e_value_limit']):.2f} at the interval\n"
        f"shuffle test inside {int(test['repositories'])} repositories: "
        f"p = {float(test['permutation_p_value_two_sided']):.3f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=7.1,
        color=INK,
    )

    save(fig, "Fig5_v2")


# ---------------------------------------------------------------------------
# Figure 6: RQ4 as an interaction, not a coefficient
# ---------------------------------------------------------------------------


def figure_task_context() -> None:
    cells = read_csv(
        CONTEXT / "answer_rate_cells.csv",
        (
            "reviewer_relation",
            "body_issue_link",
            "prs",
            "answered",
            "answered_rate",
            "population",
        ),
    )
    cells = cells[cells["population"] == "thread-root triggers"]
    models = read_csv(
        CONTEXT / "interaction_models.csv",
        ("specification", "estimate", "ci_low", "ci_high"),
    )
    loo = read_csv(
        CONTEXT / "leave_one_repository_out.csv", ("estimate",)
    )
    shuffle = read_csv(
        CONTEXT / "label_shuffle_test.csv", ("p_value_two_sided",)
    ).iloc[0]
    primary = exactly_one(
        models, specification="Thread-root triggers, repository and month FE"
    )

    fig = new_figure(3.55)
    layout = Layout(left=0.165, right=0.775, top=0.900, bottom=0.140, gap=0.0)
    (rect,) = layout.rects((1.0,))
    ax = fig.add_axes(rect)

    series = (
        ("cross_product", "A different product\nis reviewing", TEAL, "o", "-"),
        ("same_product", "The same product\nis reviewing", SLATE, "s", (0, (4, 2))),
    )
    for relation, label, colour, marker, style in series:
        values = []
        for link in (False, True):
            row = exactly_one(cells, reviewer_relation=relation, body_issue_link=link)
            values.append(float(row["answered_rate"]) * 100)
        ax.plot(
            [0, 1],
            values,
            color=colour,
            linewidth=2.0,
            linestyle=style,
            marker=marker,
            markersize=6.0,
            markerfacecolor=colour,
            markeredgecolor=WHITE,
            markeredgewidth=0.6,
            clip_on=False,
            zorder=3,
        )
        for position, value in zip((0, 1), values, strict=True):
            above = relation == "cross_product"
            ax.text(
                position,
                value + (2.4 if above else -2.4),
                f"{value:.1f}%",
                ha="center",
                va="bottom" if above else "top",
                fontsize=7.3,
                fontweight="bold",
                color=colour,
            )
        ax.text(
            1.06,
            values[1],
            label,
            ha="left",
            va="center",
            fontsize=7.2,
            color=colour,
        )

    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(0, 34)
    ax.set_xticks([0, 1], ["No issue link", "PR body links an issue"])
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, "", "Task context only helps across the boundary")
    clean_axis(ax, "y")

    estimates = loo["estimate"].to_numpy() * 100
    ax.text(
        0.015,
        0.035,
        minus(
            f"gap between the two slopes: {float(primary['estimate']) * 100:+.1f} pp "
            f"[{float(primary['ci_low']) * 100:+.1f}, "
            f"{float(primary['ci_high']) * 100:+.1f}]\n"
            f"holds from {estimates.min():+.1f} to {estimates.max():+.1f} when any one "
            f"repository is dropped\n"
            f"shuffling the link label gives "
            f"p = {float(shuffle['p_value_two_sided']):.3f}"
        ),
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.1,
        color=SLATE,
    )

    save(fig, "Fig6_v2")


def main() -> None:
    assert_palette_contrast()
    figure_measurement_contract()
    figure_participation()
    figure_boundary()
    figure_merge_curves()
    figure_sensitivity()
    figure_task_context()
    stems = [f"Fig{index}_v2" for index in range(1, 7)]
    written = sorted(path.name for path in OUTPUT.glob("Fig*_v2.*"))
    proofs = write_colour_proofs(stems)
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(ROOT)),
                "files": written,
                "colour_proofs": str(
                    (ROOT / "build" / "qa" / "colour").relative_to(ROOT)
                ),
                "proof_files": proofs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
