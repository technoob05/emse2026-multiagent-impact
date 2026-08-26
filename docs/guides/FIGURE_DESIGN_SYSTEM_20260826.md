# Figure design system for the coordination-topology paper

Date: 26 August 2026  
Status: **shipped**. The system below is now the manuscript figure set. It is
produced by `scripts/figures/visualize_manuscript_figures.py` and consumed directly by
`paper/manuscript/main.tex`. The superseded candidate-only script
`visualize_coordination_topology_v2.py` has been removed so that the figures
have a single source of truth.

## What changed when the system shipped

- **Export width is the journal's own text block.** `sn-jnl` sets
  `\textwidth` to 372 pt. Every figure is exported at exactly that width, so
  `\includegraphics[width=\linewidth]` reproduces it at scale 1.0 and a 7.2 pt
  label prints at 7.2 pt. The earlier candidates targeted 5.25 in (378 pt),
  which the manuscript then rescaled.
- **Panels share one axes rectangle.** A `Layout` object supplies the same
  left edge, right edge and width to every panel in a figure, so panel frames,
  tick rows, and category columns line up down the page instead of drifting.
- **Annotation space is measured, not guessed.** `fit_right_labels` renders the
  right-hand value labels, measures their real extent, and widens the data axis
  until they fit. This is what removed the clipped labels in the candidates.
- **Direct labels are collision-resolved.** In the burst panel each line label
  is anchored to its own endpoint and then pushed apart by a minimum readable
  spacing, with a leader line drawn whenever a label had to move.
- **An automated geometry gate blocks a bad export.** Before writing any file,
  `assert_layout` fails the build if any text falls outside the canvas, any text
  is below the 7 pt print floor, or any two annotations inside a panel overlap.
  A failing render is written to `build/qa/figure_qa_debug/` for inspection instead
  of reaching the PDF.
- **Two figures were added.** Figure 1 is a structural schematic of the
  measurement contract (event anchor, the three exclusion rules, the four
  evidence levels). Figure 5 reports the RQ3 sensitivity bounds: the
  unmeasured-confounder tipping frontier with the E-value, and the
  pre-trigger placebo outcomes with the randomisation-inference p-value. The
  three original figures became Figures 2--4.

The contracts below still govern Figures 2--4 and remain the reference for
palette, non-color encoding, wording, and precision.

## Audit in the current PDF

The three figures carry useful evidence, but their export size is much wider
than the manuscript column. A 12.2-inch source is reduced to roughly a
5.2-inch printed width. This makes axis text, legends, annotations, and the
footer notes effectively about 4 points high. The figures are technically
sharp, but several parts are not comfortably readable in the final PDF.

The shared design problems are:

- Each image repeats a large internal headline and a long note that the
  manuscript caption already supplies. These elements consume height while
  becoming the smallest text on the page.
- Two wide panels compete for a single-column width. Long category names wrap,
  and panel-level annotations sit close to data marks.
- Color carries too much of the distinction. The figures need shapes, fill,
  line style, and ordering that still work in grayscale.
- Some visuals show more numbers than the claim needs. The main figures should
  answer the RQ; complete thresholds, models, and falsification details belong
  in the Supplementary Information.

Figure-specific issues are:

- **Current Figure 1:** the final 0.9% bar is almost invisible on a linear
  scale; the Panel B legend and five-minute callout compete with the lines; the
  footer is not readable at print size. The core story is still strong: broad
  participation collapses before a connected handoff is visible, and the
  post-burst owner is more often a user account than a mapped product.
- **Current Figure 2:** the line joining the two matched rates can look like a
  time path. More importantly, Panel B omits the 70.2% history rate among all
  user responders. Without that baseline, the figure visually overstates
  selective expert routing. The baseline is needed to make the paper's actual
  conclusion clear.
- **Current Figure 3:** the strongest point and its label sit close to the
  panel heading, and the small footer carries the crucial warning that the rows
  use different cohorts. The figure also predates the specificity comparison
  against public discussion without an exact parent edge. That comparison is
  now the cleanest way to show that the main result is not only activity versus
  silence.

## Shared editorial rules

1. Design at final size. The v2 candidates use a 5.25-inch canvas, close to the
   current manuscript text width. Do not export a 12-inch chart and shrink it.
2. Use stacked panels at one-column width. Horizontal two-panel layouts are
   reserved for a two-column or full-page span.
3. Put the figure title, denominator contract, and interpretation boundary in
   the LaTeX caption. Inside the image, keep only short answer-first panel
   headings and labels needed to read the marks.
4. Use direct labels instead of legends where possible. No boxed annotation,
   decorative icon, gradient, shadow, or dashboard card.
5. Use one emphasized hue per claim and neutral gray for context. The palette
   is color-vision-safe and remains separable in grayscale:

   | Role | Hex | Use |
   |---|---:|---|
   | Ink | `#202631` | Text, axes, primary neutral marks |
   | Blue | `#2C6EAA` | Mapped product or same-product reference |
   | Orange | `#C76B16` | Cross-product boundary contrast |
   | Teal | `#16827C` | Addressed edge or user-account ownership |
   | Slate | `#667085` | Context and comparison groups |
   | Light gray | `#E6E9EF` | Sparse grid and separators |

6. Every color distinction also has a non-color cue: circle versus square or
   diamond; filled versus open marker; solid versus dashed line; or explicit
   category label.
7. Use plain B1 wording. Prefer “exact parent edge,” “public discussion,” and
   “later merge”; avoid mechanism words such as “understands,” “solves,” or
   “causes.”
8. Keep numeric precision at one decimal point for percentages and percentage
   point differences. Counts use thousands separators. Confidence intervals
   appear only where they change interpretation.

## Typography and sizing contract

The one-column candidates target 133 mm (5.25 inches). At that width:

- panel heading: 9.2--9.6 pt, semibold;
- axis label: 8.0--8.3 pt;
- tick and category label: at least 7.4 pt;
- direct annotation: at least 7.4 pt;
- line width: at least 1.4 pt; marker diameter: at least 5 pt;
- no internal note below 7.2 pt.

For a two-column or full-width version at 178 mm (7.0 inches), preserve font
sizes rather than scaling them upward with the canvas. A two-panel horizontal
layout may be used, but each panel must remain at least 82 mm wide. If the
journal reduces the full-width image, no text may fall below 7 pt in the final
proof.

## Figure 1 contract: participation and next owner

- **Question:** How much of product co-presence survives stronger connection
  rules, and who owns the first visible state after a rapid burst?
- **Takeaway:** Participation falls sharply before an addressed edge is found.
  After the burst, user accounts remain the largest visible owner class and a
  mapped product is much less common.
- **Data grain:** Panel A is one row per PR in the complete seven-day
  cross-product trigger cohort (`n=8,608`). Panel B is one mutually exclusive
  first-state assignment per PR and threshold, conditional on a later action.
- **Chart form:** stacked vertical panels. Panel A uses aligned horizontal bars
  for the four evidence rules. Panel B uses a sensitivity line plot over the
  declared 0, 1, 5, 10, and 30 minute thresholds.
- **Palette:** slate/blue for broad participation; teal for user ownership;
  blue for mapped-product ownership; orange and slate for other automation and
  movement.
- **Non-color encoding:** each Panel B state has a different marker and line
  style. Panel A prints every value and stage name directly.
- **Annotations:** label the five-minute user and mapped-product shares and the
  number of PRs with an action left. Do not annotate every point.
- **Accessibility:** use a linear percentage axis, direct stage labels, and no
  reliance on the almost invisible 0.9% bar. Its printed value remains explicit.
- **Candidate outputs:** `build/figures/Fig1_v2.pdf` and
  `build/figures/Fig1_v2.png`.
- **QA:** four Panel A counts must reconcile to the participation funnel; each
  Panel B line must match all five thresholds; the conditional denominator
  must be stated; direct labels must not collide at 30 minutes.

## Figure 2 contract: boundary visibility and public history

- **Question:** Is public follow-up quieter across a product boundary, and is
  prior repository review history specific to the first bridge?
- **Takeaway:** Matched cross-product feedback has less visible follow-up.
  Prior history is common among bridges, but it is also common in the wider
  response layer, so the trace does not show selective expert routing.
- **Data grain:** Panel A contains 546 nearest-time matched pairs from 149
  repositories. Panel B uses account--PR rows under the strict same-repository,
  different-PR, pre-trigger history rule.
- **Chart form:** stacked vertical panels. Panel A is a paired-rate dumbbell,
  clearly labeled as a matched comparison rather than a trajectory. Panel B is
  a horizontal dot plot with the wider responder population shown as an open
  reference marker.
- **Palette:** blue for same-product; orange for cross-product; teal for first
  bridge and decisive reviewer; slate for the all-responder reference.
- **Non-color encoding:** open circle, filled circle, triangle, and square
  distinguish comparison roles. Direct labels repeat the category names.
- **Annotations:** show the matched difference and repository-bootstrap
  interval once. Show the three history percentages and sample sizes; omit
  author-versus-other-user detail from the main figure.
- **Accessibility:** the responder baseline is mandatory because it changes
  interpretation. Do not use a green-versus-blue bar distinction alone.
- **Candidate outputs:** `build/figures/Fig2_v2.pdf` and
  `build/figures/Fig2_v2.png`.
- **QA:** matched rates and interval must come from the exact-author
  specification; history rows must use strict prior-review timestamps; the
  all-responder rate must be 70.2%, not an author-account baseline.

## Figure 3 contract: edge specificity and later state

- **Question:** Does an exact parent edge mark later integration beyond generic
  activity, and does a broader automation-to-user route point the same way?
- **Takeaway:** Exact edges have higher later-merge rates. The adjusted marker
  remains positive when the control already has public discussion, while the
  broader hybrid route supplies a separate, secondary check.
- **Data grain:** Panel A uses the 1,067 inline-trigger landmark cohort and its
  615-PR public-discussion specificity subset. The “discussion, no edge” group
  is a subset of the overall “no edge” group, not a third mutually exclusive
  arm. Panel B uses repository-clustered adjusted contrasts; the route row has
  a separate 1,733-PR cohort and reference.
- **Chart form:** stacked vertical panels. Panel A is a horizontal rate dot
  plot with the nested discussion control visibly indented. Panel B is a
  compact forest plot: primary edge versus no edge, specificity edge versus
  non-exact discussion, and secondary automation-to-user versus automation
  alone.
- **Palette:** teal for addressed-edge rows, slate for no-edge context, blue
  for the secondary route.
- **Non-color encoding:** filled circle for the main edge, square for the
  specificity comparison, and diamond for the secondary route. The zero line
  and intervals remain legible in grayscale.
- **Annotations:** print each point estimate and 95% interval at the right edge.
  Put cohort/reference differences in the caption, not a tiny image footer.
  Repository fixed effects and overlap-weighted estimates remain in the
  Supplementary Information.
- **Accessibility:** explicitly label the nested control. Never describe later
  merge as quality, correctness, or resolution.
- **Candidate outputs:** `build/figures/Fig3_v2.pdf` and
  `build/figures/Fig3_v2.png`.
- **QA:** raw rates must be 37.9%, 41.7%, and 55.0%; adjusted rows must be
  +17.3 `[+7.3,+27.4]`, +12.5 `[+1.4,+23.5]`, and +12.9
  `[+3.0,+22.7]` percentage points; the three different comparisons must not be
  drawn as one causal ranking.

## Release QA checklist

- Render PDF and 300-dpi PNG from the same code and data.
- Confirm the PDF has embedded TrueType/Type 42 text and no Type 3 fonts.
- Inspect every PNG at 100% size and at a simulated manuscript width.
- Inspect a grayscale copy and a common red--green color-vision simulation.
- Confirm no clipped labels, overlapping intervals, or text below the minimum
  size contract.
- Confirm the image has no path, script name, internal identifier, or causal
  wording visible to readers.
- Reconcile every displayed value to a validated analysis artifact.
- Keep detailed model specifications, full threshold tables, and rejected
  stories in the Supplementary Information rather than adding them to the
  figure.

## Prototype inspection log

The candidates were inspected as 300-dpi PNGs after each render. Four passes
were needed.

1. **First render.** Figure 1 incorrectly printed 8,608 PRs at the five-minute
   landmark because the annotation summed the “no later action” state together
   with the four visible-action states. The correct conditional count is 4,771.
   Its 0- and 1-minute tick labels also touched. Figure 3 printed estimates on
   top of their intervals, which hid the marks.
2. **Second render.** Figure 1 was changed to an ordinal display of the five
   tested thresholds, with the correct 4,771 denominator. Figure 3 moved each
   estimate and interval above its mark and placed cohort sizes in a separate
   right-aligned column. The data became readable, but PDF inspection found
   that tight bounding-box export expanded Figure 3 to 453 points wide. It
   would therefore have been reduced again in the manuscript.
3. **Final-size render.** Export was locked to exactly 378 points (5.25 inches)
   for every PDF. Long category labels were wrapped. This exposed three real
   clipping problems: the last Figure 1 category and the Panel B headings in
   Figures 2 and 3.
4. **Fourth render.** The affected category and headings were shortened or
   wrapped. Visual inspection then found no clipped labels, overlapping marks,
   hidden intervals, or ambiguous legend dependence. Figure 1 shows the
   correct five-minute denominator; Figure 2 includes the all-responder
   baseline; Figure 3 includes the non-exact-discussion specificity control and
   visibly separates the secondary route row.

The remaining integration risk is pagination, not chart rendering: stacked
figures are taller than the current wide figures. Before replacing the main
figures, compile the manuscript with the candidate PDFs, inspect the three full
pages, and revise the external captions to match the new panel contracts. That
integration is deliberately outside this candidate-only task.
