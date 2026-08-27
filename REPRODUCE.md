# How to reproduce this study

You have the archive and nothing else. This page gets you from that to the
numbers in the paper. Read it top to bottom; it is short.

## 1. What is not in here, and where to get it

The study reads the **AIDev** release. It is third-party data under its own
terms, so this archive does not redistribute it. Fetch it yourself:

- Dataset: `hao-li/AIDev-7.6M` on Hugging Face
- **Pinned revision: `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`**
- <https://huggingface.co/datasets/hao-li/AIDev-7.6M/tree/37bbe1533e26cc1e1374917dba1186d1c8a4dc81>

Use that exact revision. A later revision will not reproduce these numbers, and
nothing in the code will warn you, because the code pins the revision string but
cannot check what is on your disk. The revision lives in `DATASET_REVISION` in
`src/multiagent_impact/pipeline.py`, which is where every script reads it from.

The download is about 13 GB of parquet. Simplest is to take the whole release.
The run order below reads `pull_request.parquet`, `all_pull_request.parquet`,
`all_repository.parquet`, `pr_review_comments.parquet`, `pr_reviews.parquet`,
`pr_comments.parquet`, `pr_timeline.parquet`, `pr_task_type.parquet`, and
`related_issue.parquet`. `pr_commit_details.parquet` is 5 GB and is read only by
analyses outside the run order, so you can leave it out if disk is tight.

Point the code at your copy:

```
# macOS / Linux
export AIDEV_DATA_DIR=/path/to/AIDev-7.6M
# Windows PowerShell
$env:AIDEV_DATA_DIR = "C:\path\to\AIDev-7.6M"
```

If you do not set it, the code looks for `../Legacy/AI_Dev_Dataminning/AIDev-7.6M`
next to the project, which is the authors' layout and almost certainly not yours.

## 2. Install

Python **3.11 or newer** (developed and last run on 3.13). Install
[uv](https://docs.astral.sh/uv/), then, from the top of this archive:

```
uv sync
```

That reads `pyproject.toml` and the locked versions in `uv.lock` and creates
`.venv/`. Every command below calls that interpreter: `.venv/bin/python` on
macOS and Linux, `.\.venv\Scripts\python.exe` on Windows. No GPU, no network
after the download, and about 8 GB of free RAM is comfortable.

## 3. Run, in this order

Order matters: later scripts read parquet files that earlier ones write.
Substitute `.\.venv\Scripts\python.exe` for `.venv/bin/python` on Windows.

```
.venv/bin/python scripts/analysis/run_cross_agent_review_exploration.py
.venv/bin/python scripts/analysis/run_response_ownership_analysis.py
.venv/bin/python scripts/analysis/run_response_ownership_robustness.py
.venv/bin/python scripts/analysis/run_coordination_topology_analysis.py
.venv/bin/python scripts/analysis/run_burst_collapsed_topology.py
.venv/bin/python scripts/analysis/run_deep_coordination_transitions.py
.venv/bin/python scripts/analysis/run_legacy_extension_ownership_persistence.py
.venv/bin/python scripts/analysis/run_human_memory_bridge_analysis.py
.venv/bin/python scripts/analysis/run_addressed_edge_landmark_analysis.py
.venv/bin/python scripts/analysis/run_addressed_edge_specificity_analysis.py
.venv/bin/python scripts/analysis/run_addressed_edge_confounding_sensitivity.py
.venv/bin/python scripts/analysis/run_addressed_edge_scope_audit.py
.venv/bin/python scripts/analysis/run_rq3_extensions.py
.venv/bin/python scripts/analysis/run_task_context_interaction.py
.venv/bin/python scripts/analysis/run_merge_curves.py
.venv/bin/python scripts/analysis/run_anchorability_coverage.py
.venv/bin/python scripts/analysis/run_burst_threshold_selection.py
.venv/bin/python scripts/analysis/run_pseudo_edge_negative_control.py
.venv/bin/python scripts/analysis/run_user_account_automation_audit.py
.venv/bin/python scripts/analysis/run_addressed_edge_reply_content_audit.py
.venv/bin/python scripts/analysis/run_heterogeneity_audit.py
.venv/bin/python scripts/analysis/run_worked_example.py
.venv/bin/python scripts/analysis/run_confounder_benchmarks.py
.venv/bin/python scripts/analysis/run_matched_thread_position_audit.py
.venv/bin/python scripts/audit/prepare_review_collision_audit.py
.venv/bin/python scripts/analysis/run_collision_descriptive_extension.py
.venv/bin/python scripts/analysis/run_sample_flow.py
.venv/bin/python scripts/reporting/generate_technical_appendix_tables.py
.venv/bin/python scripts/validation/validate_response_ownership_outputs.py
.venv/bin/python scripts/validation/validate_coordination_extension_outputs.py
.venv/bin/python scripts/figures/visualize_manuscript_figures.py
uv run --with pytest python -m pytest -q
```

The two `validate_*` scripts are the gate: they re-read what was just written and
fail loudly if a headline number moved. If they pass, you have reproduced the
study. `run_sample_flow.py` is an accounting check that walks the five population
sizes quoted in the paper and asserts each filter step; it reads only frozen
artifacts, so it is a good last step.

**Roughly how long.** About **11 minutes** for the whole list, measured end to
end on a Windows laptop with the parquet files on a local SSD, once the data is
downloaded. Two steps dominate: `run_task_context_interaction.py` at roughly two
minutes and `run_addressed_edge_landmark_analysis.py` at about the same. Most
other steps finish in under half a minute, because they read derived parquet
rather than rescanning the release. Figures take about 25 seconds and the tests
about 15. Allow 15 to 20 minutes on a slower disk. Downloading the 13 GB of data
takes far longer than running the analysis.

## 4. What each output directory holds

Everything is written under `outputs/`. The archive already ships these, so you
can read the results before running anything, and diff yours against them after.

| Directory | What is in it |
|---|---|
| `cross_agent_review/` | The starting cohort: which pull requests have one product reviewing another's change |
| `response_ownership/` | Who takes the next visible action after a review comment, and robustness to that rule |
| `coordination_topology/` | The exact-edge funnel: how a large trigger cohort narrows to the few genuinely addressed replies |
| `burst_topology/` | Ownership with the opening automated burst set aside, at 0, 1, 5, 10, and 30 minutes |
| `burst_threshold_selection/` | Whether the five-minute burst window can be chosen from the data at all (it cannot; it is a convention) |
| `deep_coordination/` | Post-burst next-state transitions and a product-composition placebo |
| `ownership_persistence/` | Whether an owner keeps the pull request, and a bidirectional-bounce falsification |
| `human_memory_bridge/` | Whether the person who bridges the boundary had reviewed in that repository before |
| `addressed_edge_landmark/` | The headline RQ3 models: exact addressed edge against later merge, measured after hour 48 |
| `addressed_edge_specificity/` | The same edge against generic public-discussion controls |
| `addressed_edge_sensitivity/` | E-values, the unmeasured-confounder tipping grid, negative-control outcomes, randomisation inference |
| `addressed_edge_scope/` | Who writes the edge, stricter edge definitions, and what the hour-48 landmark leaves out |
| `pseudo_edge_control/` | Deliberately wrong anchors. This is where the headline association is qualified, not confirmed |
| `anchorability_coverage/` | How much review activity the addressed edge structurally cannot see |
| `matched_thread_position/` | Thread position inside the 546 matched pairs, and whether it drives the contrast |
| `user_account_automation/` | Whether the accounts writing the edges are really people rather than scripted tokens |
| `heterogeneity_audit/` | Where the matched-pair gap lives: by product pair, by repository, leave-one-out |
| `confounder_benchmarks/` | The measured controls plotted on the same axes as the hypothetical hidden cause |
| `task_context_interaction/` | RQ4: whether an issue link in the pull request body changes who answers |
| `rq3_extensions/` | Whole-population time-varying edge model and the edge split by who wrote the reply |
| `merge_curves/` | Merge over a 30-day horizon, for the cohorts above |
| `worked_example/` | One real pull request traced end to end, so the measurement rules are checkable |
| `sample_flow/` | The closed accounting from 8,608 down to 1,067, one filter at a time |
| `review_collision/` | The frozen 167-locus blinded dual-coder packet. Semantic claims remain pending |
| `external_validation/` | Cross-dataset attribution, overlap, and semantic-artifact audits |
| `figures/`, `tables/` | Rendered appendix figures and the CSV tables the manuscript reads |

`docs/guides/DATASET_GUIDE.md` explains the release layout, the joins, and which
denominators are valid. `protocol/` holds the reproduction contract, including
`experiment_disposition_20260826.csv`, which records negative results rather than
dropping them.

## 5. What you cannot reproduce from this archive alone

- **Everything above needs AIDev.** No script in the run order will run without
  it. The derived outputs are shipped so you can inspect and audit the results,
  but regenerating them requires the pinned release.
- **`outputs/external_validation/` also needs other third-party datasets.** The
  external-evidence audit screened SWE-Review-Chat, SWE-PRBench, AIReviewAction
  and others, which live under `external_data/` in the authors' tree and are not
  redistributed here either. Their provenance and download manifests are in
  `docs/audits/EXTERNAL_DATA_PROVENANCE_20260826.md`. The audit conclusions in
  `docs/audits/CROSS_DATASET_COMPATIBILITY_20260826.md` stand on their own.
- **The blinded human-coding keys are not here, deliberately.** The private
  coder keys, sampling keys, and answer keys under `outputs/**/private*` are
  excluded by a rule the build script enforces and verifies against the finished
  zip. The public coding packets are included; the keys that would de-blind them
  are not. Semantic coding of the 167 loci is pending in any case, and the paper
  makes no claim that depends on it.
- **The manuscript is not in here.** The LaTeX sources, the figures as typeset,
  and the compiled PDFs are governed by the publisher agreement rather than by
  the MIT licence in `LICENSE`, so this archive carries the code and the data
  products behind the paper, not the paper. See `NOTICE.md`. The figure code in
  `scripts/figures/` is included, and it regenerates every manuscript figure
  from the shipped `outputs/`.

## 6. If a number does not match

Check the dataset revision first, then that `uv sync` used `uv.lock` rather than
resolving fresh, then the run order. `MANIFEST.csv` and `SHA256SUMS` record the
size and hash of every file as deposited, so you can tell exactly which output
moved.
