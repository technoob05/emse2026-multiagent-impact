# Icon set — glossy 3D style, cut from a generated contact sheet

34 RGBA PNGs, one icon per file, trimmed to the icon's own bounding box with an
8 px uniform transparent margin. Native resolution (no upscaling); sizes range
from 82 px to 565 px on the long edge.

## Provenance

All 34 files were cut from a single source image:

- `2bbe7a97-8e28-4e49-863b-11fc66aadaf7.png` — 1536x1024 RGBA, an AI-generated
  contact sheet of glossy 3D icons laid out in five rows over a saturated
  multi-hue gradient background.

No icon was redrawn, recoloured, or retouched by hand. Every pixel is derived
from that one source.

## How they were cut

The decisive finding is that the source PNG **already carries a real per-icon
alpha matte** in its alpha channel — the visible rainbow gradient lives entirely
in the RGB channels, and the alpha channel is a clean, anti-aliased silhouette of
each icon. Segmentation from scratch was therefore unnecessary. The pipeline is:

1. **Matte** — take the embedded alpha channel directly. It is tight (the
   soft transition band is 1–2 px, i.e. genuine anti-aliasing, not a wide glow
   skirt) and it separates every icon cleanly.
2. **Background estimation** — reconstruct the gradient underneath each icon by
   nearest-valid-pixel fill from the alpha≈0 region (with a 2 px guard band so
   edge-contaminated pixels do not seed the fill), then a mild Gaussian smooth to
   remove Voronoi seams. The gradient is low-frequency, so this is accurate.
3. **Alpha decontamination (colour unmixing)** — the source RGB is a *composite*,
   so every partially-transparent edge pixel is a blend of icon colour and
   gradient colour. Solve `F = (C - (1-a)·B) / a` per pixel to recover the
   straight (un-premultiplied) foreground. Pixels below a≈0.12, where that
   inversion is ill-conditioned, inherit colour from the nearest confidently
   solid pixel so the feathered rim keeps the icon's own hue.
4. **Feather trim** — the generator painted a bright glow around several icons
   and baked part of it into the matte. Alpha is tapered as a function of
   distance from each icon's solid body (full alpha out to 2.5 px, ramping to
   zero by 7 px), which preserves anti-aliasing and genuine contact shadows while
   removing the wide glow skirt.
5. **Split and crop** — connected components on the matte, merged where one icon
   is topologically split (the green person glyph is a separate head and body),
   masked per component so overlapping bounding boxes do not bleed into each
   other, then cropped with an 8 px margin.

### Drop shadows: kept

The soft contact shadows are kept, because they read as part of the icon style
and the decontamination step recovers them as near-neutral dark pixels at partial
alpha, which composite correctly over any background. What was *removed* is the
outer bright glow — that is a lighting artifact of the sheet's background, it is
invisible on the rainbow sheet it came from, and it reads as grey dirt on a dark
slide.

### What was tried and rejected

- **Global colour-distance thresholding** — rejected outright. Several icons have
  white or near-white fills that any colour threshold tuned to the gradient
  would eat.
- **Naive cut (source RGB + source alpha, no unmixing)** — measurably fringed.
  Measuring each rim pixel against its own nearest solid-core pixel and
  projecting the residual onto the local background colour gives a median
  projection of **0.25–0.73 across the set** (1.0 = the rim is literally
  background colour). After unmixing that drops to **≈0.0 for 28 of 34 icons**,
  with several going slightly negative. This is the single biggest quality win in
  the pipeline.
- **Photometric skirt detection** (rewrite any low-contribution pixel as a
  neutral shadow, gated on `max|C-B|/a < τ`) — rejected. It cannot distinguish
  "no icon here" from "the icon's colour happens to match the background", so it
  ate the anti-aliased edge of the purple `pill-weak` sitting on a purple patch
  of gradient, and degraded `speech-bubble` and `number-2`. The geometric feather
  trim in step 4 achieves the same goal without that failure mode.

## Quality: honest assessment

Verified by compositing every file against white, near-black (#14141a) and
saturated magenta (#d600d6), and inspecting edges at 3–4x zoom. Magenta is the
harsh test: a fringe inherited from a blue or green patch of the source gradient
is invisible on that gradient and glaring on magenta.

**33 of 34 are clean.** No visible colour fringe on any of the three
backgrounds, correct anti-aliasing, neutral contact shadows. These are safe to
drop on a slide of any colour.

**1 has a real, visible defect:**

- `bubble-group-dashed.png` — the source rendered this icon as a *translucent
  panel* with a heavy glow, and the matte swallowed both. The panel fill is
  optically ambiguous (there is no unique foreground colour that explains a
  translucent surface over an unknown background), so the recovered fill is
  murky. After the feather trim the panel is gone and what remains is the five
  bubbles plus the dashed border — which reads correctly on light backgrounds,
  but on dark each bubble carries a visible pale-blue halo and the dashed border
  breaks into smeared blobs. **Use on light backgrounds only.** If you need it on
  dark, compose it yourself from `speech-bubble.png` plus a drawn dashed rounded
  rectangle.

Two further caveats, neither a defect:

- `timeline-dots.png` and `arrow-gradient-rainbow.png` are wide and thin
  (565x56 and 554x106). They are clean, but they will look soft if scaled up
  much past native size.
- `tick-green.png` / `tick-green-small.png` and `git-branch-orange.png` /
  `git-branch-orange-tall.png` are near-duplicate glyphs at different sizes and
  slightly different proportions, kept separate because both appear on the sheet.

The ceiling here is set by the source: these are raster icons at roughly 130–280 px,
generated, not vector. They are good for slides and figures at or below native
size. If you need them crisp at poster scale or in a vector workflow, this sheet
cannot provide that and the icons would have to be redrawn as SVG.

## Files

| File | Size | What it shows |
|---|---|---|
| `robot-purple-code.png` | 196x270 | Purple-and-white 3D robot with antenna, holding a `</>` code badge |
| `code-window.png` | 211x216 | Editor/browser window with purple title bar, traffic lights and a `</>` glyph |
| `robot-blue-chat.png` | 193x275 | Blue-and-white 3D robot with antenna, holding a speech-bubble badge |
| `comment-card-bubble.png` | 218x202 | Comment card with avatar and text lines, speech bubble floating above |
| `developer-github-laptop.png` | 198x259 | Person in a green hoodie at a laptop bearing the GitHub mark |
| `reply-card.png` | 214x158 | Green-bordered card with a circular reply arrow and text lines |
| `git-branch-orange-tall.png` | 165x216 | Orange branch/merge glyph, tall proportions, three ring nodes |
| `tick-green-small.png` | 119x121 | Green disc with a white check mark (smaller of the two) |
| `speech-bubble.png` | 158x122 | Blue rounded speech bubble with three white dots |
| `comment-card.png` | 225x125 | Blue-outlined comment card with avatar, text lines and a tail |
| `bubble-group-dashed.png` | 433x139 | Five speech bubbles with an ellipsis, inside a dashed selection border |
| `timeline-dots.png` | 565x56 | Horizontal timeline: five coloured nodes on a bar ending in an arrowhead |
| `folder-github-add.png` | 201x174 | Yellow folder with the GitHub mark and a green `+` badge |
| `file-code.png` | 138x173 | Document with a folded corner and a purple `</>` glyph |
| `file-comment.png` | 151x170 | Document with text lines and a blue speech bubble overlapping it |
| `person-green.png` | 151x164 | Solid green person glyph (head and shoulders) |
| `reply-arrow-green.png` | 152x133 | Curved green arrow pointing back to the left |
| `git-branch-orange.png` | 141x172 | Orange branch/merge glyph, three ring nodes |
| `tick-green.png` | 156x159 | Green disc with a white check mark (larger of the two) |
| `calendar-48h.png` | 194x197 | Calendar page reading `48h+` with a blue clock badge |
| `number-1.png` | 130x133 | Purple disc numbered 1 |
| `number-2.png` | 133x133 | Blue disc numbered 2 |
| `number-3.png` | 133x133 | Green disc numbered 3 |
| `number-4.png` | 132x133 | Orange disc numbered 4 |
| `arrow-slate-thin.png` | 143x82 | Dark slate arrow pointing right, slim shaft |
| `arrow-purple-blue.png` | 167x95 | Right-pointing arrow, purple-to-blue gradient |
| `arrow-green.png` | 176x95 | Right-pointing arrow, light-to-dark green gradient |
| `arrow-orange.png` | 171x105 | Right-pointing arrow, yellow-to-red-orange gradient |
| `arrow-slate-bold.png` | 152x106 | Dark slate arrow pointing right, heavier head and shaft |
| `pill-weak.png` | 152x91 | Purple pill label reading `WEAK` |
| `pill-weaker-to-stronger.png` | 330x92 | Blue pill label reading `WEAKER → STRONGER` |
| `pill-strong.png` | 168x91 | Green pill label reading `STRONG` |
| `pill-strongest.png` | 217x89 | Red-orange pill label reading `STRONGEST` |
| `arrow-gradient-rainbow.png` | 554x106 | Long horizontal arrow with a purple-blue-green-orange gradient |
