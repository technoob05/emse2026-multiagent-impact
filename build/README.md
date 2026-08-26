# build/ — generated deliverables

Everything in this directory is produced by a script. Nothing here is edited by
hand, and deleting it costs only the time to rebuild.

| Directory | Holds | Produced by |
|---|---|---|
| `figures/` | `FigN_v2.pdf` and 400-dpi PNGs, exported at exactly 372 pt | `scripts/figures/visualize_manuscript_figures.py` |
| `pdf/` | The compiled manuscript and Online Resource 1 | `scripts/build_submission.ps1` |
| `submission/` | Flat source archive, packaged PDFs, and the Editorial Manager staging folder | `scripts/package_submission.ps1` |
| `qa/` | Page renders kept for visual inspection, plus grayscale and failed-layout proofs | ad-hoc QA passes |

Do not confuse this with `outputs/`, which holds the analysis results that the
paper's tables and figures are computed from.

To rebuild everything:

```powershell
.\scripts\build_submission.ps1
```
