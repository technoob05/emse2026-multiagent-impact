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
from matplotlib.offsetbox import AnnotationBbox, OffsetImage  # noqa: E402
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
BURST_EXAMPLE = ROOT / "outputs" / "worked_example_burst"
PAIR_EXAMPLE = ROOT / "outputs" / "worked_example_matched_pair"
BENCHMARKS = ROOT / "outputs" / "confounder_benchmarks"
THREAD_POSITION = ROOT / "outputs" / "matched_thread_position"
ICONS = ROOT / "assets" / "icons"
OUTPUT = ROOT / "build" / "figures"

# ===========================================================================
# PALETTE. Figure 1 is a TikZ drawing (paper/manuscript/fig1_diagram.tex) and
# it is the reference. Every hue below is taken from it byte for byte, and the
# charts are not free to invent a hue or to restate a meaning per panel: a
# reader learns purple, blue, green and orange on page 11 and carries them
# forward. The old steel/goldenrod/brick family is gone. It said nothing the
# reader could look up, and beside Figure 1's saturated cards it printed as a
# wash.
#
# ONE MEANING PER COLOUR. This is the whole table; if a hue is not in it, no
# figure in this module may use it.
#
#   Hex      Constant   Meaning                              Figures
#   -------  ---------  -----------------------------------  ------------------
#   #5B2E9E  PURPLE     the product that WROTE the change     1A card, 2B line
#                       (Figure 1's "Product A"), and that
#                       product acting anywhere later
#   #1A5FB4  BLUE       a DIFFERENT product: the reviewer     1A card, 2C dot,
#                       that is not the author. This is what  3A bar, 3C card
#                       makes an arm "cross-product", so it   + tally, 6A line,
#                       is the cross-product arm as well as   6B mark
#                       Figure 1's "Product B"
#   #15703F  GREEN      a PERSON acts: a user account, the    1A card + edge,
#                       maintainer who answers. Figure 1's    2B line, 2C dot,
#                       "Person" and its claim line           3B bar, 4 line
#   #2E9C5C  GREEN_LT   a person answers, but NOT on the      4 line
#                       trigger's own thread. Same hue,
#                       lighter, because it is the same act
#   #A8480A  ORANGE     the BRANCH moves: the change itself   1A card, 2B line
#                       lands or is rewritten. Figure 1's
#                       orange git-branch glyph and its
#                       "Merge" card
#   #A93B1E  BRICK      SET ASIDE: what the rules refuse to   1A drop, 2C band
#                       count, and the region in which the    + dots, 5 corner
#                       result would not survive
#   #464D57  SLATE      the COMPARISON BASELINE the focal     3C card + tally,
#                       series is measured against: the       4 line, 5 line,
#                       same-product arm, the no-reply arm    6A line, 6B mark,
#                                                             S2 alternatives
#   #6B7280  STONE      an actor OUTSIDE the paper's          2B line
#                       vocabulary: a bot we never mapped
#   #1F2328  INK        lettering, spines, ticks, zero        every figure;
#                       lines, and a MEASURED NEUTRAL MARK    3A whiskers,
#                       -- a reading rather than a claim      5 factor dots,
#                                                             S2 antimode
#   #9AA3AE  MID        a null result: an interval that       3A bars, 3C tally
#                       includes zero, a pair that cancels    middle, connectors
#   #C8CED7  GRID       hairline: gridlines, leader lines,    every figure;
#                       card outlines, container surfaces     S2 density fill
#
#   ORDINAL RAMP -- Figure 1 Panel B's evidence ladder, sampled from the same
#   gradient image, carried here byte for byte. It means one thing: HOW MUCH
#   THE PUBLIC RECORD SHOWS, weaker to stronger. Figure 2A's funnel IS that
#   ladder measured -- its four stages are the four rungs, in the same order --
#   so it is drawn on the ramp rather than on four categorical hues, which said
#   "four kinds of thing" about four stages of one narrowing.
#
#   #897CEF  RAMP_A     rung 1, both products merely present  1B box, 2A bar 1
#   #5F92FF  RAMP_B     rung 2, somebody acted next           1B box, 2A bar 2,
#                                                             S1 + S3 mid tier
#   #53B44E  RAMP_C     rung 3, a reply names the comment     1B box, 2A bar 3
#   #EC9638  RAMP_D     rung 4, and it came from the other    1B box, 2A bar 4
#                       product / the change was accepted
#
#   RAMP_B does one further job in the appendix, where a three-tier ORDINAL
#   scale (channel anchorability, feature coverage) runs on blue's own dark,
#   mid and light -- BLUE, RAMP_B, GRID -- so a tier can never be mistaken for
#   one of the paper's actors. See scripts/figures/visualize_dataset.py, which
#   also declares the one place a hue is used for something other than its
#   meaning here: the schema diagram, which draws tables rather than actors.
#
# WHAT THIS COSTS, stated rather than hidden.
#
# 1. BLUE carries two sentences that a reader must join: "the reviewing
#    product" (Fig. 1A, Fig. 2C) and "the cross-product arm" (Figs. 3 and 6).
#    They are one referent -- an arm is cross-product exactly when the
#    reviewing product is not the author's -- but the join is the reader's to
#    make, and no other hue in the paper asks that.
#
# 2. SLATE likewise: "the same-product arm" (Figs. 3, 6) and "the no-reply
#    arm" (Fig. 4). Both are the baseline the coloured series is measured
#    against, which is the meaning written above; neither is a series in its
#    own right.
#
# 3. ORANGE covers both an untyped branch movement (Fig. 2B) and the merge
#    (Fig. 1A). Figure 1 draws the merge with a branch glyph, so the hue is
#    already "the branch", and this widens it by exactly that much.
#
# 4. The cross-product / same-product opposition has NO colour in Figure 1.
#    BLUE against SLATE is a choice made here, and it is made once for both
#    figures that carry it: Figure 3 (panels A and C) and Figure 6 (panels A
#    and B). The previous pass had Figure 3 on brick-against-slate while
#    Figure 6 ran on steel-against-slate, so the two never actually agreed.
#    Brick was the wrong arm to spend anyway: it is what the rules throw away.
#
# GREYSCALE AND COLOUR VISION. The saturated set is far less separable by
# luminance than the old one, and that is the price of matching Figure 1.
# Measured greyscale values out of 255: INK 4, SLATE 19, PURPLE 17, BLUE 30,
# BRICK 30, GREEN 31, ORANGE 33, STONE 43, GREEN_LT 64, RAMP 66/77/89/102,
# MID 92, GRID 156. Blue, brick, green and orange are within 3 levels of one
# another: on a monochrome printer they are one tone. Every panel that puts
# two of them side by side therefore carries a second channel --
#
#   Fig. 2B  four lines, greens/oranges tied: marker o / s / ^ / D and dash
#            solid / solid / dashed / dash-dot, and each line is named at its
#            own right-hand end in its own hue.
#   Fig. 2C  blue trigger, brick burst, green post-burst all tie: the trigger
#            is a filled circle, the burst events are OPEN circles, the
#            post-burst actor is a filled square.
#   Fig. 4   green against light green: 1.76:1 apart plus solid against
#            long-dash; slate dotted underneath.
#   Fig. 6   blue against slate: circle + solid against square + dash, and
#            both lines are labelled at their right end.
#
# ONE PLACE WHERE TYPE, NOT TONE, CARRIES IT, and it is not hidden here.
# Figure 3C draws the two arms as AREAS -- two card headers and the two ends of
# a tally bar -- and blue and slate sit only 1.36:1 apart, so on a monochrome
# printer they are close. There is no marker or dash channel available to an
# area, and a hatch behind reversed-out lettering is what an earlier pass of
# this figure removed as unreadable. What separates them instead is that each
# card header spells its own arm ("cross-product", "same-product") in white
# type, each tally end sits directly under the card it belongs to, and the mid
# grey between them is 2.5:1 lighter than either. Colour there is confirming a
# label rather than replacing one. Figure 3A avoids the problem entirely: it
# has one coloured bar against grey, 2.46:1 apart.
#
# WHAT WAS MEASURED, not assumed. Every text artist in all nine figures was
# cropped out of the 400 dpi render and its ink and ground sampled from those
# pixels: 385 words, none under 4.5:1. The minimum is 4.56:1 -- "100.0% ·
# 8,608 PRs" set in ink inside Figure 2A's first bar, on ramp stop 1 -- which
# is the same binding constraint Figure 1 records for ink on its own rung 1.
#
# Purple and blue collapse into one blue under deuteranopia (they sit 0.11
# apart in simulated sRGB), so they are never the two arms of one contrast.
# They co-occur only in Figure 1A, where each card also carries its name.
# Orange and brick collapse likewise; they co-occur nowhere.
INK = "#1F2328"
SLATE = "#464D57"
STONE = "#6B7280"
MID = "#9AA3AE"
GRID = "#C8CED7"
PURPLE = "#5B2E9E"
BLUE = "#1A5FB4"
GREEN = "#15703F"
GREEN_LT = "#2E9C5C"
ORANGE = "#A8480A"
BRICK = "#A93B1E"
RAMP_A = "#897CEF"
RAMP_B = "#5F92FF"
RAMP_C = "#53B44E"
RAMP_D = "#EC9638"
RAMP = (RAMP_A, RAMP_B, RAMP_C, RAMP_D)
# Tints. Figure 1's own tints sit at L* 94-96 and read as white once a chart
# scales them down to a bar rather than a card; these are the same hues taken
# deep enough to clear MIN_FILL_CONTRAST_RATIO against the page while still
# holding ink at better than 11:1.
PALE_PURPLE = "#E3D9F6"
PALE_BLUE = "#D6E4F7"
PALE_GREEN = "#D3EBDD"
PALE_ORANGE = "#FAE0CB"
PALE_BRICK = "#F7DBD4"
WHITE = "#FFFFFF"

TEXT_COLOURS = (INK, SLATE, STONE, PURPLE, BLUE, GREEN, ORANGE, BRICK)
# Lines and fills only. GREEN_LT reaches 3.48:1 on the page, which clears the
# 3:1 floor for a graphical object but not the 4.5:1 floor for lettering, so
# Figure 4 names it in a legend set in ink rather than in its own hue. The four
# ramp stops are Figure 1's, and Figure 1 sets ink on them rather than white.
FILL_ONLY = (GREEN_LT, RAMP_A, RAMP_B, RAMP_C, RAMP_D)
PALE_FILLS = (
    PALE_PURPLE,
    PALE_BLUE,
    PALE_GREEN,
    PALE_ORANGE,
    PALE_BRICK,
    MID,
    GRID,
    RAMP_A,
    RAMP_B,
    RAMP_C,
    RAMP_D,
)

# Every place a figure sets lettering on top of something other than the white
# page. Checked explicitly, because the floor on TEXT_COLOURS only speaks about
# the page and says nothing about text reversed out of a filled mark.
TEXT_ON_FILL = (
    ("white on purple", WHITE, PURPLE),
    ("white on blue", WHITE, BLUE),
    ("white on green", WHITE, GREEN),
    ("white on orange", WHITE, ORANGE),
    ("white on brick", WHITE, BRICK),
    ("white on slate", WHITE, SLATE),
    ("ink on ramp 1", INK, RAMP_A),
    ("ink on ramp 2", INK, RAMP_B),
    ("ink on ramp 3", INK, RAMP_C),
    ("ink on ramp 4", INK, RAMP_D),
    ("ink on pale purple", INK, PALE_PURPLE),
    ("ink on pale blue", INK, PALE_BLUE),
    ("ink on pale green", INK, PALE_GREEN),
    ("ink on pale orange", INK, PALE_ORANGE),
    ("ink on pale brick", INK, PALE_BRICK),
    ("ink on mid grey", INK, MID),
    ("ink on hairline grey", INK, GRID),
)

# Hatches for hues that share a luminance. Kept sparse: at 372 pt a dense
# hatch turns into a grey wash on the page. No figure in this module spends
# one; they stay declared because scripts/figures/visualize_dataset.py imports
# all three for the appendix coverage figure, where a third ordinal tier
# really does need a third channel.
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
# Lettering must also keep clear of the trim edge itself, not merely stay
# inside the canvas rectangle by a rounding error.
MIN_EDGE_POINTS = 1.0
MINUS = "\u2212"

# Pictograms. The two worked-example panels are drawings rather than charts, so
# a glyph there can carry a noun that would otherwise cost a word of lettering.
# The set in assets/icons is raster, 82 to 565 px on the long edge, so the only
# question that matters is how much of the page one is asked to cover: an icon
# printed larger than its own resolution allows is a soft patch on an otherwise
# vector page. Every placement therefore states a millimetre height and is
# rejected outright if the source cannot hold MIN_ICON_DPI at that size.
MM_PER_INCH = 25.4
MIN_ICON_DPI = 300.0
# Matplotlib rasterises an embedded image to the dpi the file is written at,
# not to the image's own resolution, so a PDF saved at the default 100 dpi
# throws away nine tenths of every glyph before it reaches the page. The PDFs
# are written at this instead, which is above the native density of every
# placement below and therefore never the binding constraint.
PDF_RASTER_DPI = 900.0


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
        # Axes read as a frame, not as a suggestion. The spines were #BBBBBB at
        # 0.7 pt, which is lighter than the gridlines Figure 1 draws its cards
        # with, and beside a TikZ figure whose own time axis is 1.6 pt of slate
        # the charts looked unfinished. Spines and ticks now share the
        # lettering's own ink at 1.1 pt, and the ticks are longer as well as
        # heavier so a 1.1 pt stroke still reads as a tick and not as a nick.
        # The GRID is deliberately left where it was: it moved from #DDDDDD to
        # the hairline #C8CED7 with the rest of the palette, but its weight is
        # unchanged at 0.6 pt. A grid drawn as heavily as a spine competes with
        # the data for the same page.
        "axes.edgecolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "xtick.labelcolor": INK,
        "ytick.labelcolor": INK,
        "xtick.major.width": 1.1,
        "ytick.major.width": 1.1,
        "xtick.major.size": 3.4,
        "ytick.major.size": 3.4,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.linewidth": 1.1,
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
    """Two spines, in ink, at the weight the rcParams set; one hairline grid.

    The spines are re-coloured here as well as in the rcParams because a panel
    that draws a zero line or a reference rule sets those in ink too, and a
    frame lighter than the rules inside it reads as a mistake.
    """
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK)
        ax.spines[side].set_linewidth(1.1)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=3.4, width=1.1, color=INK, labelcolor=INK)


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
# Pictograms
# ---------------------------------------------------------------------------

_ICON_CACHE: dict[str, np.ndarray] = {}
# Every glyph placed in this run, so the build can print what it actually put
# on the page rather than what the code intended to.
ICON_REPORT: list[dict[str, object]] = []


def icon_image(name: str) -> np.ndarray:
    if name not in _ICON_CACHE:
        path = ICONS / f"{name}.png"
        if not path.is_file():
            raise FileNotFoundError(path)
        _ICON_CACHE[name] = plt.imread(path)
    return _ICON_CACHE[name]


def tinted(array: np.ndarray, colour: str) -> np.ndarray:
    """One glyph redrawn as a single hue, keeping its own light and shade.

    The icon set is stock artwork: saturated blues, greens and oranges with a
    gloss gradient on every face. That is fine in a panel where the glyph is
    the only mark, and wrong in a panel that already carries a two-colour
    encoding, where a bright blue pictogram is simply the loudest thing on the
    page and means nothing. This maps each pixel's own lightness onto the ramp
    from ``colour`` to white, so the drawing keeps its shading and its white
    counters but stops introducing a hue the figure never defined. Alpha is
    untouched, so the soft edge stays soft.

    The lightness is stretched to the glyph's own range first. Stock artwork is
    drawn in mid-tones -- the blue on these reads as a 40% grey once the hue is
    taken out of it -- so a ramp that preserved lightness exactly would print a
    slate glyph as a pale one and lose it inside a white card. Anchoring the
    ramp on the glyph's own second and ninety-eighth percentiles puts its
    darkest ink at full strength and its paper at white, which is what a
    duotone is for. Percentiles rather than extremes, so one stray pixel cannot
    set the scale, and only pixels the reader will actually see are measured.
    """
    grey = linear_to_srgb(
        srgb_to_linear(array[..., :3].astype(float)) @ RELATIVE_LUMINANCE
    )
    opaque = (
        array[..., 3] > 0.5
        if array.shape[2] == 4
        else np.ones(grey.shape, dtype=bool)
    )
    out = np.array(array, dtype=float)
    if not opaque.any():
        return out
    low, high = np.percentile(grey[opaque], (2.0, 98.0))
    level = np.clip((grey - low) / max(float(high - low), 1e-3), 0.0, 1.0)
    base = np.asarray(to_rgb(colour))[None, None, :]
    out[..., :3] = base + (1.0 - base) * level[..., None]
    return out


def icon(
    ax: plt.Axes,
    name: str,
    xy: tuple[float, float],
    height_mm: float,
    *,
    box_alignment: tuple[float, float] = (0.5, 0.5),
    zorder: float = 6.0,
    tint: str | None = None,
) -> AnnotationBbox:
    """Place one pictogram at a stated printed height, in the axes' own units.

    The zoom is derived from the millimetre height and the source's own pixel
    count rather than from whatever resolution the file happens to carry, so
    moving a glyph between two panels of different scales does not change how
    big it prints. ``OffsetImage`` corrects for figure dpi itself, which means
    one point of the returned extent is one point on the page.
    """
    array = icon_image(name)
    pixels_high, pixels_wide = array.shape[0], array.shape[1]
    height_in = height_mm / MM_PER_INCH
    effective_dpi = pixels_high / height_in
    if effective_dpi < MIN_ICON_DPI:
        raise AssertionError(
            f"'{name}' at {height_mm:.2f} mm prints at {effective_dpi:.0f} dpi, "
            f"below the {MIN_ICON_DPI:.0f} dpi floor: the source is "
            f"{pixels_high} px tall and cannot fill that much page"
        )
    width_mm = height_mm * pixels_wide / pixels_high
    ICON_REPORT.append(
        {
            "icon": name,
            "height_mm": round(height_mm, 2),
            "width_mm": round(width_mm, 2),
            "source_px": f"{pixels_wide}x{pixels_high}",
            "effective_dpi": int(round(effective_dpi)),
        }
    )
    box = AnnotationBbox(
        OffsetImage(
            array if tint is None else tinted(array, tint),
            zoom=height_in * POINTS_PER_INCH / pixels_high,
        ),
        xy,
        xycoords="data",
        frameon=False,
        pad=0.0,
        box_alignment=box_alignment,
        annotation_clip=False,
        zorder=zorder,
    )
    ax.add_artist(box)
    return box


def icon_extent(
    ax: plt.Axes, name: str, height_mm: float
) -> tuple[float, float]:
    """How much of the axes one glyph will cover, in that axes' own units.

    A row that mixes glyphs and words has to be centred as one object, and the
    glyph half of it is specified in millimetres of page while the row is laid
    out in data units. This is the conversion, taken from the axes' own
    transform rather than from an assumption about the panel's scale.
    """
    array = icon_image(name)
    height_in = height_mm / MM_PER_INCH
    width_in = height_in * array.shape[1] / array.shape[0]
    origin = ax.transData.transform((0.0, 0.0))
    unit = ax.transData.transform((1.0, 1.0)) - origin
    dpi = ax.figure.dpi
    return width_in * dpi / abs(unit[0]), height_in * dpi / abs(unit[1])


def assert_icons_placed(fig: plt.Figure, stem: str) -> None:
    """A pictogram is not lettering, so ``assert_layout`` never sees it.

    That gate walks text artists, which means an icon may run off the canvas or
    sit on top of a label without the build noticing. This is the matching gate
    for the other kind of artist: same trim standoff, same near-miss spacing
    against every word on the page.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    margin = MIN_EDGE_POINTS * fig.dpi / POINTS_PER_INCH
    gap = 1.0 * fig.dpi / POINTS_PER_INCH

    placed = [
        artist
        for ax in fig.axes
        for artist in ax.artists
        if isinstance(artist, AnnotationBbox)
    ]
    words = [
        (text.get_text(), text.get_window_extent(renderer=renderer))
        for text in lettering(fig)
    ]
    for box in placed:
        extent = box.get_window_extent(renderer)
        clearance = min(
            extent.x0 - canvas.x0,
            canvas.x1 - extent.x1,
            extent.y0 - canvas.y0,
            canvas.y1 - extent.y1,
        )
        if clearance < margin:
            raise AssertionError(
                f"{stem}: an icon comes within "
                f"{clearance / (fig.dpi / POINTS_PER_INCH):.2f} pt of the canvas "
                f"edge, under the {MIN_EDGE_POINTS} pt standoff"
            )
        for label, word in words:
            if (
                min(extent.x1, word.x1) - max(extent.x0, word.x0) > -gap
                and min(extent.y1, word.y1) - max(extent.y0, word.y0) > -gap
            ):
                raise AssertionError(
                    f"{stem}: an icon and the label '{label[:24]}' collide"
                )


# ---------------------------------------------------------------------------
# Export and geometry gate
# ---------------------------------------------------------------------------


def lettering(fig: plt.Figure) -> list[Text]:
    """Every text artist a reader will see, whatever kind of artist holds it.

    Matplotlib scatters lettering across five different homes: free annotations
    on an axes, the axes' own title and axis labels, the tick labels the
    formatter creates, the offset text a scientific formatter parks at the end
    of an axis, and the labels a legend keeps in its own child artists. A
    typesetter measuring a page does not care which home a word lives in, so
    neither does this. Anything omitted here is a hole in the gate: it is text
    that may print below the size floor, walk off the canvas, or land on top of
    another label without the build noticing.
    """
    found: list[Text] = [text for text in fig.texts]
    for ax in fig.axes:
        found.extend(ax.texts)
        # ``ax.title`` is only the *centre* title. Every panel heading in this
        # module is set with ``loc="left"``, which matplotlib keeps in a
        # separate artist, so reading ax.title alone meant the gate never
        # measured a single panel title: not its size, not its distance from
        # the trim, not whether an annotation had landed on top of it.
        found.extend(
            title
            for name in ("title", "_left_title", "_right_title")
            if (title := getattr(ax, name, None)) is not None
        )
        found.extend((ax.xaxis.label, ax.yaxis.label))
        if ax.axison:
            for axis in (ax.xaxis, ax.yaxis):
                low, high = sorted(axis.get_view_interval())
                for minor in (False, True):
                    locations = axis.get_ticklocs(minor=minor)
                    labels = axis.get_ticklabels(minor=minor)
                    for location, label in zip(locations, labels):
                        # Ticks off the end of the axis keep their label artist
                        # but are never drawn, so measuring them would judge
                        # lettering that is not on the page.
                        if low - 1e-9 <= location <= high + 1e-9:
                            found.append(label)
                found.append(axis.get_offset_text())
        legend = ax.get_legend()
        if legend is not None:
            found.extend(legend.get_texts())
            title = legend.get_title()
            if title is not None:
                found.append(title)
    figure_legend = getattr(fig, "legends", [])
    for legend in figure_legend:
        found.extend(legend.get_texts())
        title = legend.get_title()
        if title is not None:
            found.append(title)
    return [
        text
        for text in found
        if text.get_visible() and text.get_text().strip()
    ]


def assert_layout(fig: plt.Figure, stem: str) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    # No lettering may reach the trim edge. Springer trims to the declared page
    # box, so a label sitting on the boundary is a label that may be shaved.
    margin = MIN_EDGE_POINTS * fig.dpi / POINTS_PER_INCH
    # A near miss prints as a collision. Two labels whose boxes clear each other
    # by a third of a millimetre are read as one smudged word at 372 pt, so the
    # gate demands a real gap rather than mere non-intersection. The horizontal
    # figure is the wider of the two because a text box already carries its own
    # leading above and below the glyphs, and none at its sides.
    gap_x = 2.0 * fig.dpi / POINTS_PER_INCH
    gap_y = 1.0 * fig.dpi / POINTS_PER_INCH

    candidates = lettering(fig)

    for text in candidates:
        content = text.get_text()
        if text.get_fontsize() < MIN_TEXT_POINTS - 1e-6:
            raise AssertionError(
                f"{stem}: '{content[:32]}' is {text.get_fontsize():.1f} pt, "
                f"below the {MIN_TEXT_POINTS} pt print floor"
            )
        box = text.get_window_extent(renderer=renderer)
        clearance = min(
            box.x0 - canvas.x0,
            canvas.x1 - box.x1,
            box.y0 - canvas.y0,
            canvas.y1 - box.y1,
        )
        if clearance < margin:
            raise AssertionError(
                f"{stem}: text '{content[:32]}' comes within "
                f"{clearance / (fig.dpi / POINTS_PER_INCH):.2f} pt of the "
                f"canvas edge, under the {MIN_EDGE_POINTS} pt standoff"
            )

    # One sweep over every pair in the figure, not one sweep per axes. A panel
    # title colliding with the annotation of the panel above it, a tick label
    # colliding with a hand-placed note, and a legend entry colliding with a
    # data label are all the same defect, and all three used to pass.
    boxes = [
        (text.get_text(), text.get_window_extent(renderer=renderer))
        for text in candidates
    ]
    for index, (first_label, first) in enumerate(boxes):
        for second_label, second in boxes[index + 1 :]:
            near_x = min(first.x1, second.x1) - max(first.x0, second.x0) > -gap_x
            near_y = min(first.y1, second.y1) - max(first.y0, second.y0) > -gap_y
            if near_x and near_y:
                overlaps = (
                    min(first.x1, second.x1) - max(first.x0, second.x0) > 0.0
                    and min(first.y1, second.y1) - max(first.y0, second.y0) > 0.0
                )
                verb = "overlap" if overlaps else "sit too close to read apart"
                raise AssertionError(
                    f"{stem}: '{first_label[:24]}' and '{second_label[:24]}' "
                    f"{verb}"
                )


def save(fig: plt.Figure, stem: str) -> None:
    try:
        assert_layout(fig, stem)
        assert_icons_placed(fig, stem)
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
    # The dpi argument changes nothing about a vector artist: the page geometry
    # is stated in inches and every line and letter is written as an outline. It
    # decides one thing only, the resolution any embedded raster is resampled to
    # on its way into the file.
    fig.savefig(OUTPUT / f"{stem}.pdf", metadata=metadata, dpi=PDF_RASTER_DPI)
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

    fig = new_figure(3.50)
    layout = Layout(left=0.030, right=0.980, top=0.905, bottom=0.045, gap=0.115)
    top_rect, bottom_rect = layout.rects((1.0, 0.46))

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
    # One card per role, in the role's own hue from the TikZ Figure 1 this
    # panel is the chart-side echo of: the product that writes is purple, the
    # product that reviews is blue, the person is green, the branch landing is
    # orange. The two products no longer share a fill, which is the whole
    # premise of the paper and used to be invisible here.
    links = (
        (author, "wrote the change", "", PALE_PURPLE, PURPLE),
        (reviewer, "posted the review", clock(at["trigger"]), PALE_BLUE, BLUE),
        ("a person", "answered it", clock(at["addressed edge"]), PALE_GREEN, GREEN),
        ("merged", "", clock(at["outcome"]), PALE_ORANGE, ORANGE),
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
                    color=GREEN if carries else SLATE,
                    linewidth=2.4 if carries else 1.2,
                    zorder=3,
                )
            )
    ax.text(
        (centres[1] + centres[2]) / 2,
        TOP + HEIGHT + 0.40,
        "the connecting edge",
        ha="center",
        va="bottom",
        fontsize=8.2,
        fontweight="bold",
        color=GREEN,
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

    # Four swatches, not five: the brick dots hanging off the chain already
    # carry their own words in brick beside them, so a fifth key entry was the
    # panel naming the same thing twice.
    swatch_key(
        ax,
        0.6,
        0.35,
        (
            ("rect", {"facecolor": PALE_PURPLE, "edgecolor": PURPLE}, "writes"),
            ("rect", {"facecolor": PALE_BLUE, "edgecolor": BLUE}, "reviews"),
            ("rect", {"facecolor": PALE_GREEN, "edgecolor": GREEN}, "a person"),
            ("rect", {"facecolor": PALE_ORANGE, "edgecolor": ORANGE}, "the outcome"),
        ),
    )

    ax = fig.add_axes(bottom_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "B", "Four levels of proof, never treated as one")

    # Order matters: each rung must ask more of the record than the one before
    # it. "Somebody acted next" is weaker than "a reply names the comment", so
    # it comes first. The article's ladder uses this order. What each rung
    # *means* used to be printed inside its box; it is a definition, so it now
    # lives in the caption and the box carries only the name being defined.
    # The ladder is ORDINAL, so it runs on Figure 1 Panel B's own four-stop
    # ramp rather than on three categorical fills, two of which used to be the
    # same colour. Each stop holds ink at better than 4.66:1, which is why the
    # names inside the boxes stay in ink and no rung reverses out to white.
    levels = [
        ("1. Both present", RAMP_A, INK),
        ("2. Acted on", RAMP_B, INK),
        ("3. Answered", RAMP_C, INK),
        ("4. Accepted", RAMP_D, INK),
    ]
    box_width = 22.0
    gap = (100.0 - len(levels) * box_width) / (len(levels) - 1)
    for index, (name, face, edge) in enumerate(levels):
        x = index * (box_width + gap)
        ax.add_patch(
            FancyBboxPatch(
                (x, 5.15),
                box_width,
                3.05,
                boxstyle="round,pad=0.2,rounding_size=0.9",
                facecolor=face,
                edgecolor=edge,
                linewidth=0.8,
            )
        )
        ax.text(
            x + box_width / 2,
            6.68,
            name,
            ha="center",
            va="center",
            fontsize=8.3,
            color=INK,
            fontweight="bold",
        )
        if index < len(levels) - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (x + box_width + 0.5, 6.68),
                    (x + box_width + gap - 0.5, 6.68),
                    arrowstyle="-|>",
                    mutation_scale=6,
                    color=SLATE,
                    linewidth=0.9,
                )
            )
    # The ramp is a scale, not three groups, so the key names its two ends the
    # way the TikZ figure's gradient pill does and lets the numerals in the
    # boxes carry the order. Colour here is redundant encoding: the rungs are
    # numbered 1 to 4 and run left to right, so a greyscale reader loses the
    # at-a-glance sense of how far apart two rungs are, never the order.
    swatch_key(
        ax,
        0.6,
        2.55,
        (
            ("rect", {"facecolor": RAMP_A, "edgecolor": INK}, "weaker evidence"),
            ("rect", {"facecolor": RAMP_D, "edgecolor": INK}, "stronger evidence"),
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

    fig = new_figure(6.05)
    layout = Layout(left=0.215, right=0.750, top=0.948, bottom=0.068, gap=0.118)
    top_rect, bottom_rect, example_rect = layout.rects((1.0, 1.30, 0.62))
    # The example strip carries no row labels, so it does not need Panel A's
    # left-hand column and would waste a third of the page keeping it. It stays
    # flush left with the panels above and runs on to the right margin.
    example_rect = (layout.left, example_rect[1], 0.975 - layout.left, example_rect[3])

    ax = fig.add_axes(top_rect)
    y = np.arange(4)[::-1]
    # This funnel is ORDINAL, not categorical, and it is the same ordering
    # Figure 1 Panel B names: both products merely present, somebody acts,
    # a reply names the trigger, and the reply comes from the other product.
    # Four categorical hues said "four kinds of thing" about four stages of
    # one narrowing, so the bars now run on Figure 1's own four-stop ramp, in
    # its order, top to bottom. A reader who has met the ladder on page 11
    # meets it here measured.
    #
    # The ramp runs LIGHT, which is the gradient's own direction and not a
    # choice made here, so no bar reverses out to white: every stop holds ink
    # at 4.66:1 or better and every stop fails white. The label therefore sits
    # in ink whether it is inside the bar or beyond its end, which is one rule
    # instead of the two the old three-hue set needed. The last two bars are
    # 8.5% and 0.9% long, far too short to hold a label at all, so they carry
    # theirs outside; order is still carried by row position and by the row
    # labels themselves, not by the hue alone.
    for position, share, count, color in zip(y, shares, counts, RAMP, strict=True):
        ax.barh(
            position,
            share,
            height=0.5,
            color=color,
            edgecolor=INK,
            linewidth=0.5,
            zorder=2,
        )
        inside = share > 60
        if inside and contrast(INK, color) < MIN_CONTRAST_RATIO:
            raise AssertionError(
                f"Figure 2A sets ink inside a {color} bar at only "
                f"{contrast(INK, color):.2f}:1"
            )
        ax.text(
            share - 1.8 if inside else share + 1.8,
            position,
            f"{share:.1f}%  ·  {count:,} PRs",
            ha="right" if inside else "left",
            va="center",
            fontsize=8.2,
            color=INK,
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
    # The four classes, in the paper's own colours. Two of them are referents
    # a reader already met in Figure 1 and they are not free to be restated:
    # a user account IS Figure 1's green Person, and a mapped product IS the
    # purple product that wrote the change. The other two are chosen to stay
    # apart from those and from each other: orange because Figure 1 already
    # draws the branch in orange, and stone because an unmapped bot is the one
    # actor here with no place in the paper's vocabulary and a grey says so.
    #
    # Greyscale values out of 255 are 31, 17, 43 and 33: the green and the
    # orange are one tone on a monochrome printer. Marker and dash carry them
    # instead -- filled circle on solid against filled diamond on dash-dot --
    # and every line is named at its own right-hand end. Line weight follows
    # the claim: the user-account line is the panel's subject and is drawn
    # heaviest.
    contract = [
        ("user_account", "User account", GREEN, "o", "-", 2.2),
        ("mapped_product", "Mapped product", PURPLE, "s", "-", 1.8),
        ("other_bot", "Other bot", STONE, "^", (0, (5, 2)), 1.6),
        ("branch_movement_untyped", "Branch movement", ORANGE, "D",
         (0, (1, 1.6, 4, 1.6)), 1.6),
    ]
    values_by_state: dict[str, np.ndarray] = {}
    for state, _label, color, marker, style, width in contract:
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
            linewidth=width,
            markersize=4.6,
            markeredgecolor=WHITE,
            markeredgewidth=0.6,
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
    # Every label is now set in its own line's hue, including the branch line:
    # the old slate was too near the ink of the panel's other lettering to
    # read as a series name, and all four hues here clear the 4.5:1 text floor
    # on the page (green 6.14, purple 9.02, stone 4.83, orange 5.84).
    for state, label, color, _marker, _style, _width in contract:
        ax.text(
            positions[-1] + 0.16,
            resolved[state],
            label,
            va="center",
            ha="left",
            fontsize=8.2,
            fontweight="bold",
            color=color,
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

    ax.axvline(2, color=MID, linewidth=0.9, linestyle=(0, (2, 2)), zorder=0)
    user_at_five = values_by_state["user_account"][2]
    product_at_five = values_by_state["mapped_product"][2]
    ax.annotate(
        f"{user_at_five:.0f}%",
        (2, user_at_five),
        xytext=(2.16, user_at_five + 5.5),
        fontsize=8.4,
        fontweight="bold",
        color=GREEN,
        arrowprops={"arrowstyle": "-", "color": GREEN, "linewidth": 0.8},
    )
    ax.annotate(
        f"{product_at_five:.0f}%",
        (2, product_at_five),
        xytext=(1.84, product_at_five + 5.5),
        ha="right",
        fontsize=8.4,
        fontweight="bold",
        color=PURPLE,
        arrowprops={"arrowstyle": "-", "color": PURPLE, "linewidth": 0.8},
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
        f"{remaining:,} PRs at 5 min",
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

    # --- Panel C: the thing Panel B waits out, on one real pull request -----
    # Panel B sweeps five waiting periods and Panel A counts what survives, but
    # neither can show a burst, and a reader who has never seen one has to take
    # the whole washout on trust. This reads outputs/worked_example_burst/, so
    # every mark below is an event on one public pull request.
    #
    # The horizontal axis is real elapsed time here, unlike Figure 1's chain.
    # That is the point: the six discarded events have to pile up against the
    # origin, because piling up against the origin is what makes them a burst.
    steps = read_csv(
        BURST_EXAMPLE / "timeline.csv",
        ("order", "minutes_after_trigger", "owner_kind", "actor", "rule"),
    ).sort_values("order")
    example = json.loads((BURST_EXAMPLE / "summary.json").read_text(encoding="utf-8"))

    # Guards. The example is only worth drawing while it still illustrates the
    # rule this figure sweeps, so each claim the panel makes is checked against
    # the artifact instead of being trusted.
    window = int(example["burst_minutes"])
    if window not in thresholds:
        raise ValueError(
            f"The example uses a {window}-minute burst window, which Panel B "
            "does not sweep; the two panels would be describing different rules"
        )
    if example["owner_without_the_rule"] != "mapped_product":
        raise ValueError(
            "The example no longer has a mapped product as its first raw event, "
            "so setting the burst aside no longer changes its owner"
        )
    if example["owner_with_the_rule"] != "user_account":
        raise ValueError(
            "The example's first post-burst owner is no longer a user account; "
            "it now reads " + str(example["owner_with_the_rule"])
        )
    discarded = steps[steps["rule"] == "burst exclusion"]
    if len(discarded) != int(example["burst_events"]) or len(discarded) < 2:
        raise ValueError("The example's burst no longer holds the events it claims")
    if (discarded["owner_kind"] == "user_account").any():
        raise ValueError("A user account now acts inside the example's burst")
    if (discarded["minutes_after_trigger"] > window).any():
        raise ValueError("A discarded event now falls outside the burst window")
    tail = steps[steps["rule"] == "first post-burst owner"]
    if len(tail) != 1:
        raise ValueError("The example does not have exactly one post-burst owner")
    tail_minutes = float(tail["minutes_after_trigger"].iloc[0])
    if tail_minutes <= window:
        raise ValueError("The example's post-burst owner now acts inside the burst")

    ax = fig.add_axes(example_rect)
    ax.set_xlim(-0.8, tail_minutes * 1.08)
    ax.set_ylim(-1.75, 1.75)

    # This panel is Figure 1's own time axis with real readings on it, so it
    # is drawn the way Figure 1 draws it: a brick band with a dashed brick
    # edge for the span the rules refuse, brick dots inside the band for the
    # events it swallows, and the axis itself as a spine rather than a rule.
    # The band's edge is dashed here for the same reason it is dashed there --
    # a solid rectangle around live data reads as a highlight, a dashed one
    # reads as a boundary.
    ax.add_patch(
        Rectangle(
            (0.0, -0.75),
            window,
            1.5,
            facecolor=PALE_BRICK,
            edgecolor=BRICK,
            linewidth=1.0,
            linestyle=(0, (3.2, 2.4)),
            zorder=0,
        )
    )
    ax.axhline(0.0, color=SLATE, linewidth=1.4, zorder=1)

    # The trigger: the reviewing product posts. Blue, because blue is the
    # product that is not the author, and a filled circle, because the three
    # kinds of mark on this line -- blue trigger, brick burst, green answer --
    # are within three greyscale levels of one another and a monochrome reader
    # has to tell them apart by shape.
    ax.plot(
        [0.0],
        [0.0],
        marker="o",
        markersize=7.2,
        markerfacecolor=BLUE,
        markeredgecolor=WHITE,
        markeredgewidth=1.0,
        zorder=5,
    )
    # Three of the six events share a timestamp to the second. Stacking them is
    # the only honest drawing: one dot would say five events happened, not six.
    minutes = discarded["minutes_after_trigger"].to_numpy(dtype=float)
    for value in np.unique(minutes):
        tied = np.flatnonzero(minutes == value)
        offsets = (np.arange(len(tied)) - (len(tied) - 1) / 2.0) * 0.34
        ax.plot(
            np.full(len(tied), value),
            offsets,
            linestyle="none",
            marker="o",
            markersize=6.0,
            markerfacecolor=WHITE,
            markeredgecolor=BRICK,
            markeredgewidth=1.6,
            zorder=5,
        )
    # The first actor after the burst is a person, so it is green, and it is a
    # SQUARE: green and blue are one tone in greyscale, and this mark and the
    # trigger are the two the panel exists to contrast.
    ax.plot(
        [tail_minutes],
        [0.0],
        marker="s",
        markersize=7.0,
        markerfacecolor=GREEN,
        markeredgecolor=WHITE,
        markeredgewidth=1.0,
        zorder=5,
    )

    reviewing = str(example["reviewing_product"]).replace("_", " ")
    bursting = ", ".join(
        str(product).replace("_", " ") for product in example["burst_products"]
    )
    span_seconds = int(round(float(example["burst_span_minutes"]) * 60.0))

    # Two glyphs, each paying for the words it replaces. The trigger is an
    # inline comment written on one line of the change, so the document-with-a-
    # comment says "review" and the label keeps only the product's name. The
    # first action after the burst comes from a person rather than a product, so
    # the developer at a laptop says "user account" and the label keeps only the
    # elapsed time. The human glyph is the one that sits next to the green
    # square, and it is the one that agrees with it: green means person here,
    # exactly as it does in Figure 1.
    ROW = 1.24
    icon(ax, "file-comment", (-0.25, ROW), 4.8)
    ax.text(
        0.42,
        ROW,
        reviewing,
        ha="left",
        va="center",
        fontsize=8.2,
        fontweight="bold",
        color=BLUE,
    )
    icon(ax, "developer-github-laptop", (tail_minutes, ROW), 4.8)
    ax.text(
        tail_minutes - 0.68,
        ROW,
        f"{tail_minutes:.1f} min",
        ha="right",
        va="center",
        fontsize=8.2,
        fontweight="bold",
        color=GREEN,
    )
    # The burst keeps its words and gets no glyph. The obvious candidate is the
    # dashed group of speech bubbles, which is exactly a run of comments
    # bracketed together, but every bubble in it is blue, and blue on this
    # figure is the reviewing product that posted the trigger: the guards above
    # refuse to draw the example unless the burst is somebody else's. A blue
    # glyph naming the burst would state the one thing it is defined not to be.
    ax.text(
        0.25,
        -ROW,
        f"{len(discarded)} {bursting} events in {span_seconds} s",
        ha="left",
        va="center",
        fontsize=8.2,
        fontweight="bold",
        color=BRICK,
    )

    ax.set_yticks([])
    ax.set_xticks([0, 5, 10, 15, 20])
    ax.set_xlabel("Minutes after the review comment")
    panel_title(ax, "C", f"One real burst: {example['repository'].split('/repos/')[-1]}")
    clean_axis(ax, "x")
    ax.spines["left"].set_visible(False)
    ax.grid(False)

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
    # Panels A and B keep the heights and the A-to-B gap they had before Panel C
    # existed, because that gap is sized by hand for the axis label and the
    # two-line note that live in it. Uniform figure-fraction gaps cannot do that
    # once a third panel changes the figure's height, so the geometry below is
    # stated in inches and converted once.
    HEIGHT = 6.12
    TOP_MARGIN, A_HEIGHT, A_TO_B, B_HEIGHT, B_TO_C, C_HEIGHT = (
        0.341,
        1.600,
        1.140,
        0.927,
        0.700,
        1.300,
    )
    fig = new_figure(HEIGHT)
    left, width = 0.315, 0.440
    a_bottom = 1.0 - (TOP_MARGIN + A_HEIGHT) / HEIGHT
    b_bottom = a_bottom - (A_TO_B + B_HEIGHT) / HEIGHT
    c_bottom = b_bottom - (B_TO_C + C_HEIGHT) / HEIGHT
    if c_bottom <= 0.0:
        raise ValueError("The three panels do not fit inside the canvas")
    top_rect = (left, a_bottom, width, A_HEIGHT / HEIGHT)
    bottom_rect = (left, b_bottom, width, B_HEIGHT / HEIGHT)
    # The pair panel is a drawing rather than a chart, so it keeps no row-label
    # column and runs the full width instead of inheriting Panel A's margins.
    example_rect = (0.030, c_bottom, 0.950, C_HEIGHT / HEIGHT)

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

    # The one bar that clears zero is the cross-product shortfall, so it is
    # drawn in BLUE, the paper's cross-product arm, and not in a hue invented
    # for this panel. The five that include zero are the null grey. Blue and
    # grey are 2.46:1 apart on luminance alone, so the judgement survives the
    # greyscale proof with no texture channel at all.
    ax.barh(
        positions,
        gaps,
        height=0.62,
        color=[BLUE if separated else MID for separated in moved],
        edgecolor=[INK if separated else MID for separated in moved],
        linewidth=0.9,
        zorder=2,
    )
    ax.errorbar(
        gaps,
        positions,
        xerr=np.vstack((gaps - lows, highs - gaps)),
        fmt="none",
        ecolor=INK,
        elinewidth=1.2,
        capsize=2.6,
        capthick=1.2,
        zorder=3,
    )
    ax.axvline(0.0, color=INK, linewidth=1.2, zorder=4)

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
    # Measured in inches below Panel A, not in figure fractions, so that adding
    # a panel below cannot slide the strip into the panel underneath it.
    band = fig.add_axes(
        (0.030, top_rect[1] - 0.842 / HEIGHT, 0.955, 0.478 / HEIGHT)
    )
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
                {"facecolor": BLUE, "edgecolor": INK, "linewidth": 0.9},
                "clears zero",
            ),
            (
                "rect",
                {"facecolor": MID, "edgecolor": MID, "linewidth": 0.9},
                "includes zero",
            ),
        ),
        swatch_height=2.6,
    )
    band.text(
        0.0,
        1.4,
        f"{pairs:,} matched pairs \u00b7 {repositories} repositories"
        f"    *{int(narrow['pairs']):,} pairs",
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
    # Every row here counts PEOPLE -- whoever replies, whoever reviews last,
    # whoever acts inside 48 hours -- so the panel is green: Figure 1's hue for
    # the person the whole chain runs through. It was steel, which named
    # nothing a reader could look up.
    #
    # The three rows are three ways of choosing WHICH people, not three
    # different kinds of actor, so they vary by depth within the one hue rather
    # than by hue. Giving them purple, blue and orange would say "product,
    # different product, branch" -- three meanings this paper has already spent
    # elsewhere -- and would tell the reader these rows are unlike each other
    # when the whole point of the panel is that they agree.
    fills = (PALE_GREEN, "#A9D8C0", "#7FC5A3")
    for position, (label, row, count_key), fill in zip(
        positions, bars, fills, strict=True
    ):
        share = float(row["prior_reviewer_share"]) * 100
        ax.barh(
            position,
            share,
            height=0.52,
            color=fill,
            edgecolor=GREEN,
            linewidth=1.2,
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

    # --- Panel C: what one matched pair actually is -------------------------
    # Panel A is a paired difference over 546 pairs, and "matched" is the most
    # abstract device in the paper: a reader is asked to accept that the two
    # sides are comparable without ever being shown a pair. This draws one, from
    # outputs/worked_example_matched_pair/, with the five keys the match holds
    # fixed printed above it.
    #
    # The drawn pair is discordant in the direction the estimate runs, so it is
    # selected on its outcome. The bar underneath is the correction: it gives
    # all four cells over all 546 pairs, and the estimate is the difference
    # between the two coloured ones. Concordant pairs cancel and are grey.
    pair = json.loads((PAIR_EXAMPLE / "summary.json").read_text(encoding="utf-8"))

    # Guards, so the drawing cannot outlive the analysis it illustrates.
    if int(pair["pairs"]) != pairs:
        raise ValueError(
            f"The pair example is drawn from {pair['pairs']} pairs but Panel A "
            f"reports {pairs}"
        )
    tally = pair["tally"]
    if sum(tally.values()) != pairs:
        raise ValueError("The pair tally does not cover every matched pair")
    implied = (
        tally["only_the_cross_product_side_answered"]
        - tally["only_the_same_product_side_answered"]
    ) / pairs
    if abs(implied * 100 - gaps[0]) > 0.05:
        raise ValueError(
            f"The tally implies {implied * 100:.2f} points but Panel A's top bar "
            f"draws {gaps[0]:.2f}"
        )
    cross_side, same_side = pair["cross_product_side"], pair["same_product_side"]
    if cross_side["visible_followup"] or not same_side["visible_followup"]:
        raise ValueError(
            "The drawn pair is no longer discordant in the illustrated direction"
        )
    if cross_side["reviewing_product"] == same_side["reviewing_product"]:
        raise ValueError("The two sides of the drawn pair share a reviewing product")

    ax = fig.add_axes(example_rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel_title(ax, "C", f"One matched pair: {pair['repository']}")

    # Two hues, and they are the paper's two hues for this contrast: BLUE for
    # the cross-product arm, SLATE for the same-product arm it is measured
    # against. Blue is not a hue invented here -- it is Figure 1's Product B,
    # the product that reviews and is not the author, which is exactly what
    # makes an arm cross-product. Panel A two inches above draws exactly one
    # bar in colour and it is the same blue on the same outcome, and Figure 6
    # draws both of its panels on this same pair. The previous pass had this
    # figure on brick and Figure 6 on steel, so the two never agreed; brick was
    # also the wrong hue to spend, because brick is what the rules throw away.
    #
    # Everything that is not one of the two arms is grey, which is the rule
    # Panel A already follows: mid grey for the pairs that cancel, exactly the
    # grey Panel A gives the intervals that include zero, and the hairline grey
    # for the band of keys the match holds fixed, which is a container rather
    # than a measurement. Three fills, three meanings, no fourth hue.
    #
    # Greyscale: blue and slate sit 1.36:1 apart, slightly closer than the
    # brick-and-slate this replaces, and the two are never adjacent -- the
    # cards are a card-gap apart and the two coloured ends of the tally have
    # two thirds of its length between them, with the lighter mid grey in
    # between. Each card also carries the words "cross-product" and
    # "same-product" reversed out of its own header, so the arm is named in
    # type and the hue is redundant encoding rather than the only encoding.
    CROSS_ARM, SAME_ARM = BLUE, SLATE

    # Corner radius, stated once in inches and converted, because the panel's
    # x and y scales differ by a factor of three: a rounding_size in data units
    # draws an ellipse, not a corner. ``mutation_aspect`` is the ratio of the
    # two scales, so every rounded thing in the panel gets the same 2.2 pt
    # radius on both axes.
    CORNER_INCHES = 0.030
    step = ax.transData.transform((1.0, 1.0)) - ax.transData.transform((0.0, 0.0))
    corner = CORNER_INCHES * fig.dpi / abs(step[0])
    corner_aspect = abs(step[0]) / abs(step[1])

    def rounded(x: float, y: float, w: float, h: float, **kwargs) -> None:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle=f"round,pad=0,rounding_size={corner}",
                mutation_aspect=corner_aspect,
                clip_on=False,
                **kwargs,
            )
        )

    # One grid for the whole panel. The content runs the full width of the
    # axes, so its left edge lands on the same figure column as Panel A's key
    # and denominator line rather than a few points inside it, and the two
    # cards, the band above them and the tally below all start and end there.
    LEFT, RIGHT = 0.0, 100.0
    CARD_GAP = 5.0
    CARD_WIDTH = (RIGHT - LEFT - CARD_GAP) / 2.0
    GAP = 0.80
    BAND_Y, BAND_H = 8.20, 1.30
    CARD_Y, CARD_H = 3.20, 4.20
    BANNER_H = 1.32
    TALLY_Y, TALLY_H = 0.55, 1.85

    # The band of matched keys: a surface, so it carries a fill and no border.
    # A fill and a stroke and a corner radius is three devices to say "these
    # five things are the same on both sides", which needs one.
    rounded(LEFT, BAND_Y, RIGHT - LEFT, BAND_H, facecolor=GRID, edgecolor="none")
    ax.text(
        (LEFT + RIGHT) / 2.0,
        BAND_Y + BAND_H / 2.0,
        "same "
        + " · ".join(("repository", "account", "product", "channel", "month")),
        ha="center",
        va="center",
        fontsize=8.4,
        color=INK,
    )

    # One glyph per follow-up event, so the count is drawn instead of written:
    # the card that used to read "2 × a new review round" now shows two cards
    # and the words "new review round". The glyph is chosen by the channel the
    # event arrived on rather than by which side of the pair it sits on, so the
    # drawing survives a change of example: a reply is a reply arrow, a review
    # round and a comment are the two kinds of comment card, and a rewritten
    # branch is the branch glyph. The side that records nothing shows nothing,
    # which is the panel's whole point and needs no mark of its own.
    #
    # The glyphs are stock artwork and arrive in stock colours -- the file
    # names still say so -- so each one is redrawn in its own card's arm colour
    # on the way to the page. A gloss-blue pictogram inside a panel encoded in
    # brick and slate is the loudest mark in it and carries none of the
    # meaning.
    CHANNEL_GLYPHS = {
        "a reply on the trigger's thread": "reply-arrow-green",
        "a new review round": "comment-card-bubble",
        "a pull request comment": "comment-card",
        "the branch is rewritten": "git-branch-orange-tall",
    }
    OUTCOME_ROW = CARD_Y + (CARD_H - BANNER_H) / 2.0
    GLYPH_MM = 4.6
    GLYPH_GAP = 0.7
    GLYPH_TO_WORDS = 1.6

    def followup_row(side: dict) -> tuple[list[str], str]:
        """The glyphs and the words the outcome row should carry.

        Falls back to spelling the counts out whenever the events cannot be
        drawn honestly: more than one channel, or more of them than fit across
        half a card. A wrong drawing is worse than a long label.
        """
        events = {
            channel: int(count)
            for channel, count in side["followup_events"].items()
            if count
        }
        if not events:
            return [], "nothing follows"
        if len(events) == 1:
            (channel, count), = events.items()
            glyph = CHANNEL_GLYPHS.get(channel)
            if glyph is not None and 1 <= count <= 3:
                words = channel
                for article in ("a ", "an ", "the "):
                    if words.startswith(article):
                        words = words[len(article) :]
                        break
                return [glyph] * count, words
        return [], ", ".join(
            f"{count} × {channel}" for channel, count in events.items()
        )

    def card(x: float, heading: str, side: dict, arm: str) -> None:
        """One arm of the pair: a white card under a solid header in its hue.

        The card body carries no tint. A pale wash behind three lines of
        lettering is the thing that made this panel look like a warning box,
        and it was doing no work the header does not do better: the hue sits
        where the word it names sits, at full strength, once.
        """
        centre = x + CARD_WIDTH / 2.0
        # Fill, header, then outline, in that order and as three patches. The
        # header shares the card's path exactly, so a border drawn with the
        # fill would have half its stroke buried under the header and half
        # showing beside it, which prints as a grey fringe down one edge. Drawn
        # last, the outline lands on the header's own edge and the card reads
        # as one object.
        rounded(x, CARD_Y, CARD_WIDTH, CARD_H, facecolor=WHITE, edgecolor="none")
        rounded(
            x,
            CARD_Y + CARD_H - BANNER_H,
            CARD_WIDTH,
            BANNER_H,
            facecolor=arm,
            edgecolor="none",
        )
        rounded(
            x,
            CARD_Y,
            CARD_WIDTH,
            CARD_H,
            facecolor="none",
            edgecolor=MID,
            linewidth=0.8,
        )
        ax.text(
            centre,
            CARD_Y + CARD_H - BANNER_H / 2.0,
            heading,
            ha="center",
            va="center",
            fontsize=8.4,
            fontweight="bold",
            color=WHITE,
        )

        glyphs, words = followup_row(side)
        # The row is one object and has to be centred as one, so the words are
        # drawn first, measured, and only then slid into place beside the
        # glyphs. Width is typographic and cannot be predicted from a count of
        # characters.
        label = ax.text(
            centre,
            OUTCOME_ROW,
            words,
            ha="left",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color=INK,
        )
        if not glyphs:
            label.set_horizontalalignment("center")
            return
        widths = [icon_extent(ax, name, GLYPH_MM)[0] for name in glyphs]
        fig.canvas.draw()
        box = label.get_window_extent(renderer=fig.canvas.get_renderer())
        corners = ax.transData.inverted().transform(
            ((box.x0, box.y0), (box.x1, box.y0))
        )
        words_width = corners[1][0] - corners[0][0]
        row = sum(widths) + GLYPH_GAP * (len(glyphs) - 1) + GLYPH_TO_WORDS
        cursor = centre - (row + words_width) / 2.0
        for name, width in zip(glyphs, widths, strict=True):
            icon(ax, name, (cursor + width / 2.0, OUTCOME_ROW), GLYPH_MM, tint=arm)
            cursor += width + GLYPH_GAP
        label.set_x(cursor - GLYPH_GAP + GLYPH_TO_WORDS)

    # The arm and the product that reviewed on it are one line, because they
    # are one fact: "cross-product" is the arm and "Copilot" is what makes it
    # cross-product. Splitting them cost a line of card and said nothing twice.
    for x, arm_name, side, arm in (
        (LEFT, "cross-product", cross_side, CROSS_ARM),
        (LEFT + CARD_WIDTH + CARD_GAP, "same-product", same_side, SAME_ARM),
    ):
        product = str(side["reviewing_product"]).replace("_", " ")
        card(x, f"{arm_name}  ·  {product}", side, arm)

    # The tally, drawn rather than asserted. Order runs cross-only, concordant,
    # same-only, so the two coloured ends sit under the card each one belongs
    # to. Square corners, unlike everything above: the cards are containers and
    # the band is a surface, but this is a measurement, and a measured length
    # with rounded ends is a length that no longer reads off its own scale.
    # Each count is reversed out of its own segment, which is what lets the
    # segments be solid rather than tinted, and the hairline between them is
    # white so the joins stay crisp without a fourth stroke colour.
    segments = (
        (tally["only_the_cross_product_side_answered"], CROSS_ARM, WHITE),
        (tally["both_sides_answered"] + tally["neither_side_answered"], MID, INK),
        (tally["only_the_same_product_side_answered"], SAME_ARM, WHITE),
    )
    cursor = LEFT
    for count, face, digits in segments:
        width = (RIGHT - LEFT) * count / pairs
        ax.add_patch(
            Rectangle(
                (cursor, TALLY_Y),
                width,
                TALLY_H,
                facecolor=face,
                edgecolor=WHITE,
                linewidth=0.9,
                clip_on=False,
            )
        )
        ax.text(
            cursor + width / 2.0,
            TALLY_Y + TALLY_H / 2.0,
            f"{count}",
            ha="center",
            va="center",
            fontsize=8.4,
            color=digits,
        )
        cursor += width
    # The denominator is not printed again. Panel A's own strip already reads
    # "546 matched pairs" a little way up the same figure, and the three counts
    # here sum to it, so a fourth label under the bar was the figure repeating
    # a number to itself.

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
    # The finding is that the two REPLY arms coincide and the no-reply arm does
    # not, so the two reply arms are drawn as two tones of one hue and the
    # baseline in slate. Green is the person who answers -- Figure 1's Person,
    # who "replies, naming that comment" -- and both reply arms are that same
    # act; what differs between them is only where the reply was anchored,
    # which is a lighter tone of the same green rather than a second hue. A
    # reader who sees two greens converge has read the sentence in the title
    # before reading the title.
    #
    # Greyscale: 31, 64 and 19 out of 255, so the pair the panel is about is
    # 1.76:1 apart on tone alone; the baseline is a further step down and is
    # the only dotted line. Light green cannot carry lettering at 3.48:1 on
    # the page, so the legend below sets every entry in ink.
    series = (
        ("reply_off_target", GREEN_LT, (0, (5.5, 2)), "reply anchored elsewhere", 1.0),
        ("reply_on_target", GREEN, "-", "reply on the trigger thread", -1.0),
        ("no_reply", SLATE, (0, (1.6, 2)), "no inline reply", 0.0),
    )
    for arm, colour, style, label, _ in series:
        low = curve[f"merged_{arm}_low"].to_numpy() * 100
        high = curve[f"merged_{arm}_high"].to_numpy() * 100
        ax.fill_between(days, low, high, color=colour, alpha=0.16, linewidth=0)

    ends = {}
    for arm, colour, style, label, _ in series:
        centre = curve[f"merged_{arm}"].to_numpy() * 100
        ends[arm] = centre[-1]
        ax.plot(days, centre, color=colour, linewidth=2.2, linestyle=style, zorder=3)

    # A line series is keyed by a line, not by a rectangle: colour alone does
    # not identify these three, the dash pattern does half the work, and a
    # filled block would throw that half away in a greyscale print. The shaded
    # bands are an area, so they do get a rectangle.
    handles = [
        Line2D(
            [],
            [],
            color=colour,
            linewidth=2.2,
            linestyle=style,
            label=f"{label}  {ends[arm]:.0f}%",
        )
        for arm, colour, style, label, _ in series
    ]
    handles.append(
        Patch(
            facecolor=SLATE,
            alpha=0.16,
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

    ax.axvline(2.0, color=MID, linewidth=0.9, linestyle=(0, (2, 2)), zorder=0)
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
        f"{int(summary['population_prs']):,} PRs \u00b7 "
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
    layout = Layout(left=0.135, right=0.955, top=0.900, bottom=0.150, gap=0.0)
    (rect,) = layout.rects((1.0,))
    ax = fig.add_axes(rect)

    delta = frontier["prevalence_difference"].to_numpy() * 100
    point_line = frontier["outcome_difference_to_remove_point_estimate"].to_numpy() * 100
    interval_line = frontier["outcome_difference_to_remove_interval"].to_numpy() * 100
    # The shaded corner is the region in which the result would not survive, so
    # it is brick: the paper's hue for what gets set aside. The dashed slate
    # line is the weaker version of the same threat, the comparison boundary
    # the interval rather than the point estimate would cross. Brick and slate
    # sit 1.35:1 apart and are told apart by dash as well.
    ax.fill_between(delta, point_line, 100, color=PALE_BRICK, alpha=0.85, zorder=0)
    ax.plot(delta, point_line, color=BRICK, linewidth=2.2, zorder=3)
    ax.plot(
        delta, interval_line, color=SLATE, linewidth=1.6, linestyle=(0, (4, 2)), zorder=3
    )
    ax.set_xlim(-2, 60)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("How much more common among answered PRs (pp)")
    ax.set_ylabel("Its effect on\nlater merge (pp)")
    panel_title(ax, "", "A hidden cause would have to be large and lopsided")
    clean_axis(ax, "y")
    ax.text(
        0.985,
        0.955,
        f"E-value {float(primary['e_value_point']):.2f}"
        f"\u2003{float(primary['e_value_limit']):.2f} at the interval",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.1,
        color=INK,
    )

    # The factors we actually measured, on the same two axes as the shaded
    # corner. All of them sit far outside it, which is the point. They are the
    # one thing in this panel that is a MEASUREMENT rather than a threat, so
    # they take the neutral ink rather than a hue: the panel then has exactly
    # one colour in it, and that colour is the danger the marks stay clear of.
    # Ink also means the marks survive every proof -- greyscale and all three
    # dichromacies -- without a second channel.
    ax.scatter(
        measured["prevalence_gap_pp"].to_numpy(),
        measured["outcome_gap_pp"].abs().to_numpy(),
        s=30,
        facecolor=INK,
        edgecolor=WHITE,
        linewidth=0.7,
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
                {"facecolor": PALE_BRICK, "edgecolor": BRICK, "linewidth": 1.4},
                "the result disappears",
            ),
            (
                "line",
                {"color": SLATE, "linewidth": 1.6, "linestyle": (0, (4, 2))},
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
                    "markersize": 5.5,
                    "markerfacecolor": INK,
                    "markeredgecolor": WHITE,
                    "markeredgewidth": 0.7,
                },
                f"the {len(measured)} measured factors",
            ),
        ),
        swatch_width=2.6,
    )

    save(fig, "Fig5_v2")


# ---------------------------------------------------------------------------
# Figure 6: RQ4 as an interaction, not a coefficient
# ---------------------------------------------------------------------------


def figure_task_context() -> None:
    """RQ4 as two panels: the interaction, then the subtraction it implies.

    The earlier version of this figure carried a counterfactual line and a
    shaded region. Both were misread. The region was drawn between the observed
    cross-product line and a derived one, so it *was* the raw contrast, but a
    shaded band under a line is read as an uncertainty band everywhere else in
    this paper and so it was read as one here. The counterfactual line, being
    derived rather than measured, needed a caption paragraph before it meant
    anything at all.

    Both are gone. Panel A now shows only the four measured rates. The raw
    contrast is no longer a region there: it is Panel B, where the two changes
    the link actually produced are drawn as two marks on one percentage-point
    ruler, and the distance between them is the raw 17.1. The adjusted estimate
    lies underneath on the same ruler, so the shrinkage from 17.1 to 13.3 is a
    distance the reader can see rather than a discrepancy to explain away, and
    the only shaded thing left in the figure is a confidence interval, which is
    what shading means everywhere else in the paper.
    """
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
    loo = read_csv(CONTEXT / "leave_one_repository_out.csv", ("estimate",))
    primary = exactly_one(
        models, specification="Thread-root triggers, repository and month FE"
    )

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
    change_cross = cross[1] - cross[0]
    change_same = same[1] - same[0]
    raw = change_cross - change_same

    estimates = loo["estimate"].to_numpy() * 100
    point = float(primary["estimate"]) * 100
    low = float(primary["ci_low"]) * 100
    high = float(primary["ci_high"]) * 100

    fig = new_figure(3.80)
    layout = Layout(left=0.150, right=0.700, top=0.925, bottom=0.150, gap=0.160)
    top_rect, bottom_rect = layout.rects((1.0, 0.50))

    # --- Panel A: four measured rates, nothing else --------------------------
    # Blue against slate, which is the pair Figure 3 uses for the same
    # opposition in both of its panels. Blue is Figure 1's Product B, the
    # reviewer that is not the author, so "a different product" is drawn in the
    # hue the reader met as a different product; slate is the baseline arm the
    # focal series is measured against, here and in Figures 3 and 4. This
    # figure used to run on steel while Figure 3 ran on brick, so the paper had
    # two vocabularies for one two-way split.
    #
    # Blue and slate sit 1.36:1 apart in tone, so shape and dash carry the pair
    # as well: circle on a solid line against square on a dashed one, in both
    # panels, and each line is named at its own right-hand end.
    ax = fig.add_axes(top_rect)
    ax.plot(
        [0, 1],
        cross,
        color=BLUE,
        linewidth=2.4,
        marker="o",
        markersize=6.4,
        markerfacecolor=BLUE,
        markeredgecolor=WHITE,
        markeredgewidth=0.7,
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
        markeredgewidth=0.7,
        clip_on=False,
        zorder=4,
    )

    # The left column is labelled beside its marker and the right column beyond
    # the axes, where the series name can ride along with the rate. Naming the
    # series at the end of its own line is what lets this figure carry no key.
    ax.text(
        0.035,
        cross[0] - 1.1,
        f"{cross[0]:.1f}%   n = {counts['cross_product'][0]:,}",
        ha="left",
        va="top",
        fontsize=8.4,
        color=BLUE,
    )
    ax.text(
        0.035,
        same[0] + 1.1,
        f"{same[0]:.1f}%   n = {counts['same_product'][0]:,}",
        ha="left",
        va="bottom",
        fontsize=8.4,
        color=SLATE,
    )
    ax.text(
        1.045,
        cross[1],
        f"{cross[1]:.1f}%   n = {counts['cross_product'][1]:,}\na different product",
        ha="left",
        va="center",
        fontsize=8.4,
        color=BLUE,
    )
    ax.text(
        1.045,
        same[1],
        f"{same[1]:.1f}%   n = {counts['same_product'][1]:,}\nthe same product",
        ha="left",
        va="center",
        fontsize=8.4,
        color=SLATE,
    )

    ax.set_xlim(-0.10, 1.13)
    ax.set_ylim(0, 33)
    ax.set_xticks([0, 1], ["No issue link", "PR body links an issue"])
    # The zero of the rate axis and the first category label are neighbours in
    # the corner, so the category row is dropped clear of it.
    ax.tick_params(axis="x", pad=7)
    ax.set_ylabel("Review points answered\nwithin 48 hours (%)")
    panel_title(ax, "A", "Flat within a product, rising across one")
    clean_axis(ax, "y")

    # --- Panel B: the two changes, their gap, and the adjusted estimate ------
    ax = fig.add_axes(bottom_rect)
    ax.axvline(0.0, color=INK, linewidth=1.0, zorder=4)

    ax.plot(
        [change_same, change_cross],
        [0.70, 0.70],
        color=MID,
        linewidth=1.3,
        zorder=2,
    )
    ax.plot(
        [change_same],
        [0.70],
        marker="s",
        markersize=6.0,
        markerfacecolor=SLATE,
        markeredgecolor=WHITE,
        markeredgewidth=0.7,
        zorder=5,
    )
    ax.plot(
        [change_cross],
        [0.70],
        marker="o",
        markersize=6.4,
        markerfacecolor=BLUE,
        markeredgecolor=WHITE,
        markeredgewidth=0.7,
        zorder=5,
    )
    ax.text(
        change_same - 0.7,
        0.70,
        minus(f"{change_same:+.1f}"),
        ha="right",
        va="center",
        fontsize=8.4,
        color=SLATE,
    )
    ax.text(
        change_cross + 0.7,
        0.70,
        minus(f"{change_cross:+.1f}"),
        ha="left",
        va="center",
        fontsize=8.4,
        color=BLUE,
    )
    ax.text(
        (change_same + change_cross) / 2,
        0.88,
        minus(f"{raw:+.1f}") + " raw",
        ha="center",
        va="bottom",
        fontsize=8.6,
        fontweight="bold",
        color=INK,
    )

    ax.barh(
        [-0.70],
        [high - low],
        left=low,
        height=0.30,
        color=PALE_BLUE,
        edgecolor=BLUE,
        linewidth=0.9,
        zorder=2,
    )
    ax.barh(
        [-0.70],
        [estimates.max() - estimates.min()],
        left=estimates.min(),
        height=0.13,
        color=BLUE,
        alpha=0.45,
        linewidth=0.0,
        zorder=3,
    )
    ax.plot(
        [point],
        [-0.70],
        marker="D",
        markersize=6.6,
        markerfacecolor=BLUE,
        markeredgecolor=WHITE,
        markeredgewidth=0.9,
        zorder=5,
    )
    ax.text(
        point,
        -0.50,
        minus(f"{point:+.1f}") + " adjusted",
        ha="center",
        va="bottom",
        fontsize=8.6,
        fontweight="bold",
        color=BLUE,
    )

    ax.set_xlim(-7.0, 25.5)
    ax.set_ylim(-1.45, 1.55)
    ax.set_yticks([])
    ax.set_xlabel("Change in the answered rate (pp)")
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
                # What the glyphs actually cost the page, printed so a reader
                # of the build log can see it without opening a PDF.
                "pdf_raster_dpi": PDF_RASTER_DPI,
                "icons": ICON_REPORT,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
