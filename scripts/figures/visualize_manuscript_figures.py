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
from matplotlib.patches import (  # noqa: E402
    FancyArrowPatch,
    FancyBboxPatch,
    Patch,
    Rectangle,
)
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
EXAMPLE = ROOT / "outputs" / "worked_example"
BENCHMARKS = ROOT / "outputs" / "confounder_benchmarks"
THREAD_POSITION = ROOT / "outputs" / "matched_thread_position"
OUTPUT = ROOT / "build" / "figures"

# Palette. A three-hue family in the idiom systematic reviews use for their
# risk-of-bias summaries: a steel blue for the series in focus, a goldenrod for
# the middle term, and a brick red for the series that contrasts with, or
# argues against, the focal one. The neutral ink is black.
#
#   Role                                   Constant   Hex
#   text, axes, primary neutral marks      INK        #000000
#   addressed edge, user-account ownership STEEL      #2E7EA1  focal series
#   cross-product boundary contrast        BRICK      #C0524C  contrasting
#   mapped / same-product reference        GOLD_INK   #8A5A10  gold, as text
#   goldenrod, fills only                  GOLD       #DFA83E  middle term
#   context and comparison groups          SLATE      #444444
#   spines, connectors, leader lines       MID        #BBBBBB
#   grid, separators, lollipop stems       GRID       #DDDDDD
#   pale fills carrying black text         PALE_*     tints of the three hues
#
# Goldenrod is the one hue in the family that cannot carry lettering: #DFA83E
# reaches only 2.14:1 on white, far under the WCAG 4.5:1 floor for text. It is
# therefore declared FILL_ONLY and paired with GOLD_INK, a dark amber of the
# same hue that reaches 5.91:1, wherever the gold series has to say something in
# words. ``assert_palette_contrast`` enforces both halves of that rule.
#
# Steel and brick sit at nearly the same relative luminance by construction
# (4.55:1 and 4.61:1 on white), which is what makes them read as equals rather
# than as a ranking. The cost is that they do not separate on luminance alone,
# so anywhere the two appear as adjacent *areas* they also carry a hatch, and
# anywhere they appear as lines they also carry a marker and a dash pattern.
INK = "#000000"
STEEL = "#2E7EA1"
BRICK = "#B03A34"
GOLD = "#DFA83E"
GOLD_INK = "#8A5A10"
SLATE = "#444444"
MID = "#BBBBBB"
GRID = "#DDDDDD"
PALE_STEEL = "#CFE3EE"
PALE_GOLD = "#F6E3BE"
PALE_BRICK = "#F2D3D1"
WHITE = "#FFFFFF"

TEXT_COLOURS = (INK, STEEL, BRICK, GOLD_INK, SLATE)
FILL_ONLY = (GOLD,)
PALE_FILLS = (PALE_STEEL, PALE_GOLD, PALE_BRICK, GRID)

# Every place a figure sets lettering on top of something other than the white
# page. Checked explicitly, because the floor on TEXT_COLOURS only speaks about
# the page and says nothing about text reversed out of a filled mark.
TEXT_ON_FILL = (
    ("white on steel", WHITE, STEEL),
    ("ink on goldenrod", INK, GOLD),
    ("ink on pale steel", INK, PALE_STEEL),
    ("ink on pale gold", INK, PALE_GOLD),
    ("ink on pale brick", INK, PALE_BRICK),
    ("ink on grid grey", INK, GRID),
)

# Hatches for the two hues that share a luminance. Kept sparse: at 372 pt a
# dense hatch turns into a grey wash on the page.
HATCH_STEEL = "//"
HATCH_BRICK = "\\\\"
HATCH_GOLD = ".."
HATCH_LINEWIDTH = 0.45

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

# Springer Nature asks for figure lettering of about 8 to 12 pt at final size.
# These figures are placed 1:1, so the floor here is the floor on the page.
MIN_TEXT_POINTS = 8.0
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
        "font.size": 8.4,
        "axes.titlesize": 9.6,
        "axes.titleweight": "bold",
        "axes.labelsize": 8.6,
        "xtick.labelsize": 8.0,
        "ytick.labelsize": 8.0,
        "legend.fontsize": 8.0,
        "text.color": INK,
        "axes.labelcolor": INK,
        "axes.edgecolor": MID,
        "xtick.color": INK,
        "ytick.color": INK,
        "axes.linewidth": 0.7,
        "hatch.linewidth": HATCH_LINEWIDTH,
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


def swatch_key(
    ax: plt.Axes,
    x: float,
    y: float,
    entries: Sequence[tuple[str, dict, str]],
    *,
    fontsize: float = 8.0,
    swatch_width: float = 2.0,
    swatch_height: float = 0.62,
    label_pad: float = 0.9,
    gap: float = 3.0,
    line_length: float = 3.4,
) -> float:
    """Draw a colour key: small filled marks in a row, each label to its right.

    A journal figure names its colours instead of asking the reader to infer
    them from context, so this is the one primitive every multi-hue panel here
    uses. Entries are placed left to right in the axes' own data coordinates
    and each one is measured after it is drawn, because the width of a label is
    typographic and cannot be guessed from its character count.

    ``kind`` is ``"rect"`` for an area encoding, ``"marker"`` for a point
    encoding, and ``"line"`` for a series drawn as a line, so the key mark is
    always the same kind of mark as the thing it names.
    """
    figure = ax.figure
    cursor = x
    for kind, spec, label in entries:
        if kind == "rect":
            ax.add_patch(
                Rectangle(
                    (cursor, y - swatch_height / 2),
                    swatch_width,
                    swatch_height,
                    facecolor=spec.get("facecolor", WHITE),
                    edgecolor=spec.get("edgecolor", INK),
                    linewidth=spec.get("linewidth", 0.7),
                    hatch=spec.get("hatch"),
                    zorder=6,
                    clip_on=False,
                )
            )
            text_x = cursor + swatch_width + label_pad
        elif kind == "marker":
            ax.plot(
                [cursor + swatch_width / 2],
                [y],
                zorder=6,
                clip_on=False,
                linestyle="none",
                **spec,
            )
            text_x = cursor + swatch_width + label_pad
        elif kind == "line":
            ax.plot(
                [cursor, cursor + line_length],
                [y, y],
                zorder=6,
                clip_on=False,
                **spec,
            )
            text_x = cursor + line_length + label_pad
        else:
            raise ValueError(f"Unknown key entry kind {kind!r}")
        text = ax.text(
            text_x,
            y,
            label,
            ha="left",
            va="center",
            fontsize=fontsize,
            color=INK,
            zorder=6,
            clip_on=False,
        )
        figure.canvas.draw()
        box = text.get_window_extent(renderer=figure.canvas.get_renderer())
        cursor = ax.transData.inverted().transform((box.x1, box.y0))[0] + gap
    return cursor


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
        # Legend entries are drawn text too, and a journal measuring lettering
        # will not care that matplotlib keeps them in a separate artist.
        legend = ax.get_legend()
        if legend is not None:
            candidates.extend(legend.get_texts())
            if legend.get_title() is not None:
                candidates.append(legend.get_title())

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

    def measure(artists: Iterable[Text]) -> list[tuple[str, object]]:
        boxes = []
        for text in artists:
            if not text.get_text().strip() or not text.get_visible():
                continue
            boxes.append((text.get_text(), text.get_window_extent(renderer=renderer)))
        return boxes

    def collide(first: object, second: object) -> bool:
        overlap_x = min(first.x1, second.x1) - max(first.x0, second.x0)
        overlap_y = min(first.y1, second.y1) - max(first.y0, second.y0)
        return overlap_x > 1.0 and overlap_y > 1.0

    for ax in fig.axes:
        boxes = measure(ax.texts)
        for index, (first_label, first) in enumerate(boxes):
            for second_label, second in boxes[index + 1 :]:
                if collide(first, second):
                    raise AssertionError(
                        f"{stem}: annotations '{first_label[:24]}' and "
                        f"'{second_label[:24]}' overlap"
                    )

    # A figure-level note lives outside every axes, so the per-axes sweep above
    # never sees it. It is placed by hand into the band between panels, which is
    # exactly where axis labels and panel titles also land, so check it against
    # them rather than discovering the collision by eye in the PDF.
    lettering: list[tuple[str, object]] = []
    for ax in fig.axes:
        lettering.extend(measure([ax.title, ax.xaxis.label, ax.yaxis.label]))
        if ax.axison:
            lettering.extend(measure(ax.get_xticklabels()))
            lettering.extend(measure(ax.get_yticklabels()))
    for note_label, note in measure(fig.texts):
        for other_label, other in lettering:
            if collide(note, other):
                raise AssertionError(
                    f"{stem}: figure note '{note_label[:24]}' overlaps "
                    f"'{other_label[:24]}'"
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
    white page; every pale fill has to stay visibly tinted against that same
    page while still holding black text; every place a figure reverses text out
    of a filled mark has to clear the floor against that fill and not against
    the page; and a fill-only hue must never leak into the text set.
    """
    for colour in TEXT_COLOURS:
        ratio = contrast(colour, WHITE)
        if ratio < MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{colour} reaches only {ratio:.2f}:1 on white, "
                f"below the {MIN_CONTRAST_RATIO}:1 text floor"
            )
    for colour in FILL_ONLY:
        if colour in TEXT_COLOURS:
            raise AssertionError(
                f"{colour} is declared fill-only but appears in TEXT_COLOURS"
            )
        ratio = contrast(colour, WHITE)
        if ratio >= MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{colour} now clears {ratio:.2f}:1 on white; either promote it "
                "into TEXT_COLOURS or stop calling it fill-only"
            )
    for name, ink, fill in TEXT_ON_FILL:
        ratio = contrast(ink, fill)
        if ratio < MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"{name} ({ink} on {fill}) reaches only {ratio:.2f}:1, "
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
    """One real pull request as a chain of actors, and the levels of proof.

    Panel A reads outputs/worked_example/, so every actor, every time and both
    discarded events belong to an actual pull request rather than to an
    illustration. It is drawn as a chain because that is the paper's claim:
    two products took part, but the step that carries the change forward runs
    through a person, and a figure of events on a line does not say that.

    The horizontal axis is the order of the chain, not elapsed time. The real
    elapsed time is printed under each link instead, because the gap between
    the review and the reply is a hundredfold the gap between the two events a
    rule discards, and a true time axis would collapse the discards into the
    origin where nothing about them could be read.
    """
    steps = read_csv(
        EXAMPLE / "timeline.csv",
        ("order", "minutes_after_trigger", "actor_role", "event", "verdict", "rule"),
    ).sort_values("order")
    example = json.loads((EXAMPLE / "summary.json").read_text(encoding="utf-8"))
    at = {row.rule: float(row.minutes_after_trigger) for row in steps.itertuples()}
    role = {row.rule: str(row.actor_role) for row in steps.itertuples()}

    # The chain is only honest if the roles in the artifact are the ones drawn.
    if role["trigger"] != "reviewing product":
        raise ValueError("The trigger is no longer written by the reviewing product")
    if role["addressed edge"] != "a person":
        raise ValueError(
            "The worked example's reply is no longer written by a person; the "
            "panel's claim that the chain runs through a person is drawn from "
            f"that field, which now reads {role['addressed edge']!r}"
        )
    for rule in ("same-batch exclusion", "burst exclusion"):
        if rule not in role:
            raise ValueError(f"The worked example no longer exercises {rule}")

    author = example["author_product"].replace("_", " ")
    reviewer = example["reviewing_product"].replace("_", " ")

    fig = new_figure(3.95)
    layout = Layout(left=0.030, right=0.980, top=0.900, bottom=0.045, gap=0.115)
    top_rect, bottom_rect = layout.rects((1.0, 0.72))

    ax = fig.add_axes(top_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "A", "Two products took part; the chain runs through a person")

    def clock(minutes: float) -> str:
        if minutes < 1.0:
            return "0 min"
        if minutes < 120.0:
            return f"{minutes:.0f} min"
        if minutes < 2880.0:
            return f"{minutes / 60.0:.1f} h"
        return f"{minutes / 1440.0:.1f} days"

    # Each link is one actor: who did it, what they did, and when. The merge
    # has no actor in the record, so it is drawn as an outcome and not as a
    # fifth account.
    links = (
        (author, "wrote the change", "", PALE_GOLD, GOLD_INK),
        (reviewer, "posted the review", clock(at["trigger"]), PALE_GOLD, GOLD_INK),
        ("a person", "answered it", clock(at["addressed edge"]), PALE_STEEL, STEEL),
        ("merged", "", clock(at["outcome"]), GRID, SLATE),
    )
    WIDTH = 21.0
    GAP = (100.0 - len(links) * WIDTH) / (len(links) - 1)
    TOP, HEIGHT = 5.30, 3.30
    centres = []
    for index, (who, does, when, face, edge) in enumerate(links):
        x = index * (WIDTH + GAP)
        centres.append(x + WIDTH / 2)
        ax.add_patch(
            FancyBboxPatch(
                (x, TOP),
                WIDTH,
                HEIGHT,
                boxstyle="round,pad=0.2,rounding_size=0.9",
                facecolor=face,
                edgecolor=edge,
                linewidth=0.9,
                zorder=2,
            )
        )
        ax.text(
            x + WIDTH / 2,
            TOP + HEIGHT - (0.95 if does else HEIGHT / 2),
            who,
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=INK,
        )
        if does:
            ax.text(
                x + WIDTH / 2,
                TOP + HEIGHT - 2.15,
                does,
                ha="center",
                va="center",
                fontsize=8.0,
                color=INK,
            )
        if when:
            ax.text(
                x + WIDTH / 2,
                TOP - 0.55,
                when,
                ha="center",
                va="top",
                fontsize=8.0,
                color=SLATE,
            )
        if index:
            # The review-to-person arrow is the addressed edge, so it is the
            # one drawn heavy and in the focal hue.
            carries = index == 2
            ax.add_patch(
                FancyArrowPatch(
                    (x - GAP + 0.4, TOP + HEIGHT / 2),
                    (x - 0.4, TOP + HEIGHT / 2),
                    arrowstyle="-|>",
                    mutation_scale=9,
                    color=STEEL if carries else SLATE,
                    linewidth=2.2 if carries else 1.0,
                    zorder=3,
                )
            )
    ax.text(
        (centres[1] + centres[2]) / 2,
        TOP + HEIGHT + 0.40,
        "the one connecting edge",
        ha="center",
        va="bottom",
        fontsize=8.2,
        fontweight="bold",
        color=STEEL,
    )
    ax.text(
        centres[3],
        TOP + HEIGHT + 0.40,
        "after hour 48",
        ha="center",
        va="bottom",
        fontsize=8.0,
        color=SLATE,
    )

    # What our rules throw away hangs off the chain instead of sitting on it,
    # which is what filtering looks like.
    BRANCH = 2.75
    ax.add_patch(
        FancyArrowPatch(
            (centres[1] + 7.0, TOP - 0.15),
            (centres[1] + 2.4, BRANCH + 0.55),
            arrowstyle="-|>",
            mutation_scale=8,
            color=BRICK,
            linewidth=0.9,
            linestyle=(0, (2.4, 1.8)),
            zorder=3,
        )
    )
    ax.text(
        centres[1] - 2.4,
        BRANCH - 0.35,
        f"also {reviewer}, not counted:",
        ha="right",
        va="center",
        fontsize=8.0,
        color=BRICK,
    )
    for index, label in enumerate(("same review batch", "inside the burst")):
        y = BRANCH + 0.30 - index * 1.30
        ax.plot(
            [centres[1] + 3.4],
            [y],
            marker="o",
            markersize=5.6,
            markerfacecolor=WHITE,
            markeredgecolor=BRICK,
            markeredgewidth=1.3,
            zorder=5,
        )
        ax.text(
            centres[1] + 5.6,
            y,
            label,
            ha="left",
            va="center",
            fontsize=8.0,
            color=BRICK,
        )

    swatch_key(
        ax,
        0.6,
        0.35,
        (
            ("rect", {"facecolor": PALE_GOLD, "edgecolor": GOLD_INK}, "coding product"),
            ("rect", {"facecolor": PALE_STEEL, "edgecolor": STEEL}, "person"),
            ("rect", {"facecolor": GRID, "edgecolor": SLATE}, "outcome"),
            (
                "marker",
                {
                    "marker": "o",
                    "markersize": 5.6,
                    "markerfacecolor": WHITE,
                    "markeredgecolor": BRICK,
                    "markeredgewidth": 1.3,
                },
                "dropped by a rule",
            ),
        ),
    )

    ax = fig.add_axes(bottom_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "B", "Four levels of proof, never treated as one")

    levels = [
        (
            "1. Both present",
            "two products act\non the same PR",
            PALE_GOLD,
            GOLD_INK,
        ),
        # Order matters: each rung must ask more of the record than the one
        # before it. "Somebody acted next" is weaker than "a reply names the
        # comment", so it comes first. The article's ladder uses this order.
        (
            "2. Acted on",
            "somebody takes the\nnext visible step",
            PALE_STEEL,
            STEEL,
        ),
        (
            "3. Answered",
            "a reply names\nthe comment itself",
            PALE_STEEL,
            STEEL,
        ),
        (
            "4. Accepted",
            "merged, only\nafter hour 48",
            GRID,
            SLATE,
        ),
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
            fontsize=8.3,
            color=INK,
            fontweight="bold",
        )
        ax.text(
            x + box_width / 2,
            5.3,
            rule,
            ha="center",
            va="center",
            fontsize=8.0,
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
    # The colours group the four levels into what they are evidence of, so
    # they are named rather than left to be inferred from the box order. The
    # sentence that used to sit here said what the caption already says.
    swatch_key(
        ax,
        0.6,
        1.35,
        (
            ("rect", {"facecolor": PALE_GOLD, "edgecolor": GOLD_INK}, "participation"),
            ("rect", {"facecolor": PALE_STEEL, "edgecolor": STEEL}, "a connected edge"),
            ("rect", {"facecolor": GRID, "edgecolor": SLATE}, "the outcome"),
        ),
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
        "Exact reply\nto the trigger",
        "Reply from a\ndifferent product",
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
    # Steel and brick share a luminance and would merge in a greyscale print
    # wherever a reader has to tell one filled area from another. Here they do
    # not: the four bars are a funnel, each is named on its own axis row, and
    # the last two are 8.5% and 0.9% long. A hatch on a bar that narrow is a
    # smudge, not a signal, so this panel stays flat and the hatching is spent
    # where the colour itself carries a judgement (Online Resource 1, Fig. S2).
    for position, share, count, color in zip(
        y, shares, counts, (GOLD, PALE_GOLD, STEEL, BRICK), strict=True
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
            fontsize=8.2,
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
        ("user_account", "User account", STEEL, "o", "-"),
        ("mapped_product", "Mapped product", GOLD_INK, "s", "-"),
        ("other_bot", "Other bot", BRICK, "^", "--"),
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
            fontsize=8.2,
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
        fontsize=8.4,
        fontweight="bold",
        color=STEEL,
        arrowprops={"arrowstyle": "-", "color": STEEL, "linewidth": 0.7},
    )
    ax.annotate(
        f"{product_at_five:.0f}%",
        (2, product_at_five),
        xytext=(1.84, product_at_five + 5.5),
        ha="right",
        fontsize=8.4,
        fontweight="bold",
        color=GOLD_INK,
        arrowprops={"arrowstyle": "-", "color": GOLD_INK, "linewidth": 0.7},
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
        fontsize=8.2,
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
    contrasts = read_csv(
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
    )
    primary = contrasts[contrasts["specification"] == "exact_author_user"]

    # The reply outcome cannot occur unless the trigger opens its own inline
    # thread, which is true on only 241 of the 546 pairs, and on 11 more it is
    # blocked on the same-product side alone. Estimating it over all 546 mixes
    # in pairs where the outcome is impossible, so this row comes from the
    # population where it is reachable on both arms.
    restricted = read_csv(
        THREAD_POSITION / "restricted_visibility_contrasts.csv",
        (
            "specification",
            "population",
            "outcome",
            "pairs",
            "repositories",
            "cross_rate",
            "same_rate",
            "repository_cluster_bootstrap_ci_low",
            "repository_cluster_bootstrap_ci_high",
        ),
    )
    RESTRICTED_OUTCOME = "exact_trigger_reply"

    # Plain names, because "any_visible_followup" is our vocabulary, not a
    # reader's. Order runs from the outcome that moves to the ones that do not.
    OUTCOMES = (
        ("any_visible_followup", "Anyone does anything"),
        ("later_pr_comment", "Someone comments"),
        ("new_review_round", "A new review round"),
        ("exact_trigger_reply", "The point gets a reply*"),
        ("visible_force_push", "The branch is rewritten"),
        ("merge_within_7d", "Merged within a week"),
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

    def restricted_row(key: str):
        return exactly_one(
            restricted,
            specification="exact_author_user",
            population="both_triggers_open_their_own_thread",
            outcome=key,
        )

    def contrast_row(key: str):
        if key == RESTRICTED_OUTCOME:
            return restricted_row(key)
        return exactly_one(primary, outcome=key)

    # The band between the panels carries Panel A's axis label and the two-line
    # note, so it is wider than a plain label row would need.
    fig = new_figure(4.55)
    layout = Layout(left=0.315, right=0.755, top=0.925, bottom=0.120, gap=0.250)
    top_rect, bottom_rect = layout.rects((1.0, 0.58))

    # --- Panel A: the difference itself, measured from zero -----------------
    # A dumbbell drew the point estimate as the distance between two rates, so
    # the longest mark belonged to an outcome whose interval still crossed
    # zero. The quantity the claim rests on is the difference against zero, so
    # that is what gets the length here: one bar per outcome, its interval laid
    # along it, and the accent reserved for the single interval that clears the
    # zero line. The rates the difference came from are printed in a right-hand
    # column instead of being drawn, so they can never land on a bar or on a
    # whisker however long the interval runs.
    ax = fig.add_axes(top_rect)
    positions = np.arange(len(OUTCOMES), dtype=float)[::-1]

    gaps, lows, highs, moved, rates = [], [], [], [], []
    pairs = repositories = 0
    for key, _label in OUTCOMES:
        row = contrast_row(key)
        low = float(row["repository_cluster_bootstrap_ci_low"]) * 100
        high = float(row["repository_cluster_bootstrap_ci_high"]) * 100
        gaps.append(float(row["paired_difference"]) * 100)
        lows.append(low)
        highs.append(high)
        moved.append(low > 0.0 or high < 0.0)
        rates.append((float(row["cross_rate"]) * 100, float(row["same_rate"]) * 100))
        if key != RESTRICTED_OUTCOME:
            pairs = int(row["pairs"])
            repositories = int(row["repositories"])

    gaps = np.asarray(gaps)
    lows = np.asarray(lows)
    highs = np.asarray(highs)

    ax.barh(
        positions,
        gaps,
        height=0.62,
        color=[BRICK if separated else MID for separated in moved],
        edgecolor=[SLATE if separated else MID for separated in moved],
        linewidth=0.8,
        zorder=2,
    )
    ax.errorbar(
        gaps,
        positions,
        xerr=np.vstack((gaps - lows, highs - gaps)),
        fmt="none",
        ecolor=SLATE,
        elinewidth=1.0,
        capsize=2.4,
        capthick=1.0,
        zorder=3,
    )
    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=4)

    ax.set_xlim(-36.0, 16.0)
    ax.set_xticks([-30, -15, 0, 15])
    ax.set_ylim(-0.62, len(OUTCOMES) - 0.38)
    ax.set_yticks(positions)
    ax.set_yticklabels([label for _, label in OUTCOMES], fontsize=8.2)
    for tick, separated in zip(ax.get_yticklabels(), moved, strict=True):
        tick.set_color(INK if separated else SLATE)
    ax.set_xlabel(
        "Cross-product " + MINUS + " same-product (pp, 95% CI)"
    )
    panel_title(ax, "A", "One outcome changes. Five do not.")
    category_axis(ax)

    # The rate column sits just past the right-hand end of the data range, so
    # it reads as a table column rather than as a point on the scale.
    RATE_COLUMN = 17.6
    for position, (cross, same), separated in zip(
        positions, rates, moved, strict=True
    ):
        ax.text(
            RATE_COLUMN,
            position,
            f"{cross:.0f}% vs {same:.0f}%",
            ha="left",
            va="center",
            fontsize=8.0,
            color=INK if separated else SLATE,
            fontweight="bold" if separated else "normal",
            clip_on=False,
        )

    # The bar colour carries the panel's judgement, so it is named rather than
    # left to be inferred. Key and caption both call the zero line "no
    # difference", so the two agree word for word. The key and the
    # denominators are wider than Panel A's own axes, so they live in a
    # full-width strip in the band between the panels.
    narrow = restricted_row(RESTRICTED_OUTCOME)
    band = fig.add_axes((0.030, top_rect[1] - 0.185, 0.955, 0.105))
    band.set_xlim(0, 100)
    band.set_ylim(0, 10)
    band.axis("off")
    swatch_key(
        band,
        0.0,
        7.0,
        (
            (
                "rect",
                {"facecolor": BRICK, "edgecolor": SLATE, "linewidth": 0.8},
                "interval clears no difference",
            ),
            (
                "rect",
                {"facecolor": MID, "edgecolor": MID, "linewidth": 0.8},
                "interval includes it",
            ),
        ),
        swatch_height=2.6,
    )
    band.text(
        0.0,
        1.4,
        f"{pairs:,} matched pairs in {repositories} repositories; "
        f"*{int(narrow['pairs']):,} where a reply is possible on both sides",
        ha="left",
        va="center",
        fontsize=8.0,
        color=SLATE,
    )

    # --- Panel B: bars, because these are shares of a whole ----------------
    ax = fig.add_axes(bottom_rect)
    bars = (
        ("Whoever replies first", mediator, "prs"),
        ("Whoever reviews last", decisive, "prs"),
        ("Anyone acting in 48 h", responders, "rows"),
    )
    positions = np.arange(len(bars))[::-1]
    for position, (label, row, count_key) in zip(positions, bars, strict=True):
        share = float(row["prior_reviewer_share"]) * 100
        ax.barh(
            position,
            share,
            height=0.52,
            color=PALE_STEEL,
            edgecolor=STEEL,
            linewidth=0.9,
            zorder=2,
        )
        ax.text(
            share + 1.4,
            position,
            f"{share:.0f}%   n = {int(row[count_key]):,}",
            ha="left",
            va="center",
            fontsize=8.1,
            color=INK,
        )

    ax.set_yticks(positions)
    ax.set_yticklabels([label for label, _, _ in bars], fontsize=8.2)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.6, len(bars) - 0.4)
    ax.set_xlabel("Had reviewed in this repository before (%)")
    panel_title(ax, "B", "Whoever steps in has been here before")
    # Same category styling as Panel A, so the two row-label columns read as
    # one column down the page.
    category_axis(ax)

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
        ("reply_off_target", BRICK, (0, (5, 1.6)), "reply anchored elsewhere", 1.0),
        ("reply_on_target", STEEL, "-", "reply on the trigger thread", -1.0),
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

    # A line series is keyed by a line, not by a rectangle: colour alone does
    # not identify these three, the dash pattern does half the work, and a
    # filled block would throw that half away in a greyscale print. The shaded
    # bands are an area, so they do get a rectangle.
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
    handles.append(
        Patch(
            facecolor=SLATE,
            alpha=0.14,
            edgecolor="none",
            label="95% interval",
        )
    )
    legend = ax.legend(
        handles=handles,
        loc="lower right",
        bbox_to_anchor=(0.995, 0.04),
        frameon=False,
        fontsize=8.2,
        handlelength=2.6,
        labelspacing=0.42,
        borderpad=0.0,
        title="Merged by day 30",
    )
    legend.get_title().set_fontsize(8.0)
    legend.get_title().set_color(SLATE)
    legend.get_title().set_ha("left")

    ax.axvline(2.0, color=MID, linewidth=0.8, linestyle=(0, (2, 2)), zorder=0)
    ax.text(2.3, 12, "hour 48", ha="left", va="center", fontsize=8.1, color=SLATE)

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
        fontsize=8.1,
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
    measured = read_csv(
        BENCHMARKS / "measured_factor_positions.csv",
        ("label", "prevalence_gap_pp", "outcome_gap_pp"),
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
    ax.fill_between(delta, point_line, 100, color=PALE_STEEL, alpha=0.75, zorder=0)
    ax.plot(delta, point_line, color=STEEL, linewidth=1.8, zorder=3)
    ax.plot(
        delta, interval_line, color=SLATE, linewidth=1.4, linestyle=(0, (4, 2)), zorder=3
    )
    ax.set_xlim(-2, 60)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("How much more common the hidden cause is among answered PRs (pp)")
    ax.set_ylabel("Its own effect on\nlater merge (pp)")
    panel_title(ax, "", "A hidden cause would have to be large and lopsided")
    clean_axis(ax, "y")
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
        fontsize=8.1,
        color=INK,
    )

    # The factors we actually measured, on the same two axes as the shaded
    # corner. All of them sit far outside it, which is the point.
    ax.scatter(
        measured["prevalence_gap_pp"].to_numpy(),
        measured["outcome_gap_pp"].abs().to_numpy(),
        s=26,
        facecolor=BRICK,
        edgecolor=WHITE,
        linewidth=0.6,
        zorder=5,
        clip_on=True,
    )
    # Three marks, three meanings, none of them readable from an axis: they go
    # in a key rather than in three sentences pinned to the plot. The wording
    # is the caption's, so the two agree.
    swatch_key(
        ax,
        14.0,
        9.4,
        (
            (
                "rect",
                {"facecolor": PALE_STEEL, "edgecolor": STEEL, "linewidth": 1.2},
                "the result disappears",
            ),
            (
                "line",
                {"color": SLATE, "linewidth": 1.4, "linestyle": (0, (4, 2))},
                "the interval blurs",
            ),
        ),
        swatch_width=2.6,
        swatch_height=3.6,
        line_length=3.4,
        gap=2.6,
    )
    swatch_key(
        ax,
        14.0,
        3.0,
        (
            (
                "marker",
                {
                    "marker": "o",
                    "markersize": 5.2,
                    "markerfacecolor": BRICK,
                    "markeredgecolor": WHITE,
                    "markeredgewidth": 0.6,
                },
                f"the {len(measured)} factors we did measure",
            ),
        ),
        swatch_width=2.6,
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

    fig = new_figure(4.15)
    layout = Layout(left=0.165, right=0.745, top=0.910, bottom=0.150, gap=0.150)
    top_rect, bottom_rect = layout.rects((1.0, 0.30))
    ax = fig.add_axes(top_rect)

    rates, counts = {}, {}
    for relation in ("cross_product", "same_product"):
        values, sizes = [], []
        for link in (False, True):
            row = exactly_one(cells, reviewer_relation=relation, body_issue_link=link)
            values.append(float(row["answered_rate"]) * 100)
            sizes.append(int(row["prs"]))
        rates[relation] = values
        counts[relation] = sizes

    cross = rates["cross_product"]
    same = rates["same_product"]
    # Where the cross-product line would have landed had the link moved it by
    # exactly as much as it moved the same-product line. This point is derived,
    # not measured, and the figure says so. The distance from it up to the
    # observed cross-product rate is the raw difference in differences, so the
    # reader measures that quantity instead of subtracting two labels.
    ghost = cross[0] + (same[1] - same[0])
    raw = cross[1] - ghost

    # The contrast is the region between what happened and what the
    # same-product change predicts, so it is drawn as that region. Its lower
    # boundary is the counterfactual line and its upper boundary is the
    # observed one, so the two series that define it also frame it.
    ax.fill_between(
        [0, 1],
        [cross[0], ghost],
        [cross[0], cross[1]],
        color=PALE_STEEL,
        linewidth=0.0,
        zorder=1,
    )
    ax.plot(
        [0, 1],
        [cross[0], ghost],
        color=MID,
        linewidth=1.6,
        linestyle=(0, (1, 2)),
        zorder=2,
        clip_on=False,
    )
    ax.plot(
        [1],
        [ghost],
        marker="o",
        markersize=5.0,
        markerfacecolor=WHITE,
        markeredgecolor=MID,
        markeredgewidth=1.3,
        zorder=3,
        clip_on=False,
    )
    ax.plot(
        [0, 1],
        cross,
        color=STEEL,
        linewidth=2.2,
        marker="o",
        markersize=6.0,
        markerfacecolor=STEEL,
        markeredgecolor=WHITE,
        markeredgewidth=0.6,
        clip_on=False,
        zorder=4,
    )
    ax.plot(
        [0, 1],
        same,
        color=SLATE,
        linewidth=2.0,
        linestyle=(0, (4, 2)),
        marker="s",
        markersize=6.0,
        markerfacecolor=SLATE,
        markeredgecolor=WHITE,
        markeredgewidth=0.6,
        clip_on=False,
        zorder=4,
    )

    # Every point now says one thing: its rate and the count behind it. Which
    # series a point belongs to is the key's job, not a second line of text
    # pinned to the mark.
    for relation, value, colour, offset in (
        ("cross_product", cross[0], STEEL, -1.2),
        ("same_product", same[0], SLATE, 1.2),
    ):
        ax.text(
            0.03,
            value + offset,
            f"{value:.1f}%  of {counts[relation][0]:,} PRs",
            ha="left",
            va="top" if offset < 0 else "bottom",
            fontsize=8.2,
            fontweight="bold",
            color=colour,
        )

    for value, count, colour in (
        (cross[1], counts["cross_product"][1], STEEL),
        (same[1], counts["same_product"][1], SLATE),
    ):
        ax.text(
            1.035,
            value,
            f"{value:.1f}%  of {count:,} PRs",
            ha="left",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color=colour,
        )
    ax.text(
        1.035,
        ghost,
        f"{ghost:.1f}%  not observed",
        ha="left",
        va="center",
        fontsize=8.0,
        color=SLATE,
    )

    # The label names the shaded region, so it sits inside it, low enough to
    # clear the same-product line that crosses the panel and far enough left of
    # the right-hand column that it cannot reach the counterfactual's label.
    ax.text(
        0.575,
        ghost + (cross[1] - ghost) * 0.28,
        minus(f"{raw:+.1f}") + " pp raw gap",
        ha="center",
        va="center",
        fontsize=8.4,
        fontweight="bold",
        color=INK,
        zorder=5,
    )

    # The key is measured in data coordinates, so the axis limits have to be
    # final before it is laid out.
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(0, 38)

    # Four things are drawn here and only one of them, the shaded region, is
    # named on the plot. The other three are named in a key, in the caption's
    # own words, in the empty band under the two lines.
    swatch_key(
        ax,
        -0.105,
        5.0,
        (
            (
                "line",
                {"color": STEEL, "linewidth": 2.2},
                "a different product reviews",
            ),
            (
                "line",
                {"color": SLATE, "linewidth": 2.0, "linestyle": (0, (4, 2))},
                "the same product reviews",
            ),
        ),
        line_length=0.075,
        label_pad=0.020,
        gap=0.055,
    )
    swatch_key(
        ax,
        -0.105,
        1.7,
        (
            (
                "line",
                {"color": MID, "linewidth": 1.6, "linestyle": (0, (1, 2))},
                "if the link had moved it like the same product",
            ),
        ),
        line_length=0.075,
        label_pad=0.020,
    )

    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(0, 38)
    ax.set_xticks([0, 1], ["No issue link", "PR body links an issue"])
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, "A", "The same context helps only across the boundary")
    clean_axis(ax, "y")

    # --- the quantity the paper actually claims, with its uncertainty -------
    ax = fig.add_axes(bottom_rect)
    estimates = loo["estimate"].to_numpy() * 100
    point = float(primary["estimate"]) * 100
    low = float(primary["ci_low"]) * 100
    high = float(primary["ci_high"]) * 100

    # The interval is a solid bar rather than a rule, so it carries the same
    # weight as the shaded region above it, and the leave-one-repository-out
    # range sits inside it as a darker band: a spread within a spread.
    ax.barh(
        [0],
        [high - low],
        left=low,
        height=0.42,
        color=PALE_STEEL,
        edgecolor=STEEL,
        linewidth=0.9,
        zorder=2,
    )
    ax.barh(
        [0],
        [estimates.max() - estimates.min()],
        left=estimates.min(),
        height=0.18,
        color=STEEL,
        alpha=0.45,
        linewidth=0.0,
        zorder=3,
    )
    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=4)
    ax.plot(
        [point],
        [0],
        marker="D",
        markersize=6.6,
        markerfacecolor=STEEL,
        markeredgecolor=WHITE,
        markeredgewidth=0.9,
        zorder=5,
    )
    # Panel A's shaded region measures the raw contrast, which is larger than
    # the estimate we report. Mark it here too, or the reader carries 17.1 down
    # from Panel A and finds the arithmetic does not come out.
    ax.plot(
        [raw],
        [0],
        marker="o",
        markersize=5.6,
        markerfacecolor=WHITE,
        markeredgecolor=SLATE,
        markeredgewidth=1.2,
        zorder=5,
    )
    ax.text(
        point,
        0.42,
        minus(f"{point:+.1f} pp adjusted"),
        ha="center",
        va="bottom",
        fontsize=8.4,
        fontweight="bold",
        color=STEEL,
    )
    ax.text(
        raw,
        -0.44,
        minus(f"{raw:+.1f}") + " raw",
        ha="center",
        va="top",
        fontsize=8.0,
        color=SLATE,
    )
    ax.text(
        0.0,
        -0.44,
        "no difference",
        ha="center",
        va="top",
        fontsize=8.0,
        color=SLATE,
    )
    ax.set_xlim(-4.0, 26.0)
    ax.set_ylim(-1.05, 1.05)
    ax.set_yticks([])
    ax.set_xlabel("How much more the link helps across the boundary (pp)")
    panel_title(ax, "B", "One change minus the other")
    clean_axis(ax, "x")
    ax.spines["left"].set_visible(False)
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
