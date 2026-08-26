# scripts/ — the pipeline

Two entry points sit at the top level, because they are what a person runs:

- `build_submission.ps1` — the whole thing: analysis, figures, appendix tables,
  both PDFs, log scan, then packaging.
- `package_submission.ps1` — packaging only, assuming the PDFs already exist.

Everything else is grouped by what it does.

| Directory | What lives there |
|---|---|
| `analysis/` | `run_*.py` — every analysis that produces something in `outputs/` |
| `figures/` | `visualize_*.py` — the manuscript figures and the appendix schema figures |
| `reporting/` | The appendix table generator and the notebook builders |
| `validation/` | `validate_*.py` — the gates that re-check frozen contracts |
| `audit/` | `prepare_*.py`, `profile_*.py` — packets for human coding, and external-source profiling |
| `_superseded/` | Scripts belonging to the pre-pivot study. They answer different questions. Do not run them expecting current results. |

Scripts resolve the project root as `Path(__file__).resolve().parents[2]`,
because they sit two levels below it. If you move one, fix that.

Run a single analysis:

```powershell
.\.venv\Scripts\python.exe scripts\analysis\run_addressed_edge_landmark_analysis.py
```

The full ordered list is under "Reproduce the headline analysis" in the project
`README.md`. That list is parsed to build appendix table `tab:s-runorder`, so a
new script must be added to both the README and `REPRODUCTION_STEPS` in
`reporting/generate_technical_appendix_tables.py`.
