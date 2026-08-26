# Participation Is Not Collaboration

Reproducible artifact for an independent EMSE 2026 Special Issue draft based on AIDev-7.6M.

## Research questions

1. **Participation or handoff?** After review de-batching and rapid-burst collapse, how much cross-product activity forms a sequential public edge, and who appears next?
2. **Who bridges the boundary?** How visible is follow-up across a product boundary, and do first user-account mediators carry earlier public review history from the repository?
3. **Does connection mark a later state?** Are an exact addressed edge and an automation-to-user relay linked to later merge after a fixed landmark?

## Main insight

Two products on one PR show participation, not collaboration. A visible handoff needs an addressed edge, a next owner, and an observable later state.

- A mapped product different from the triggering reviewer replies to the exact trigger on 74 PRs, below 1% of the complete trigger cohort.
- Excluding a five-minute rapid burst reduces mapped-product first ownership by 29%; user accounts own 53% of the first actions that remain.
- Cross-product triggers receive 13.4 percentage points less visible follow-up than same-product triggers matched on repository, PR-author account, author product, source, and month.
- 71% of first user-account mediators had reviewed a different PR in the same repository before the trigger.
- An exact reply to the trigger is associated with 17.3 points more later merge after measured pre-trigger controls. The association remains positive when the comparison is limited to PRs that already have other public discussion.
- That association has an E-value of 2.27 and a within-repository randomisation p of 0.007, and it stays positive under stricter edge definitions.
- The edge is written by a user account in 105 of 128 exposure events, by the triggering product replying to itself in 13, and by a different mapped product in 3. RQ3 therefore measures human acknowledgement, not agent-to-agent dialogue.
- The outcome cohort is the 27% of cross-product inline triggers still open at hour 48. Most such PRs close, and 64% merge, before the outcome window opens.
- Automation followed by a user account gives a secondary, same-direction check. Neither later-state contrast is a causal effect or a semantic resolution rate.

The paper does not claim semantic repair, verified manual work, private coordination, or a product ranking.

## Data

- Dataset: `hao-li/AIDev-7.6M`
- Revision: `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`
- Default path: `../Legacy/AI_Dev_Dataminning/AIDev-7.6M`
- Full corpus: 7,685,281 PRs
- Rich AIDev-pop layer: 361,296 PRs
- PR creation cutoff: 31 March 2026
- Conservative interaction boundary: 15 April 2026

See `docs/guides/DATASET_GUIDE.md` for conceptual tables, joins, feature groups, and coverage.

### External evidence audit

Related public datasets were screened against the same event contract rather than pooled by row count. The frozen audit covers 15 candidates and 11 local acquisitions. The complete SWE-Review-Chat release was scanned, but all seven exact-edge candidates overlap the AIDev backbone, so no independent outcome cohort remains. The independently packaged AI-to-AI review cohort supports product-attribution and timing checks on overlapping PRs only. SWE-PRBench and AIReviewAction support semantic codebook checks, not reply-topology replication. See `docs/audits/CROSS_DATASET_COMPATIBILITY_20260826.md` and `docs/audits/EXTERNAL_DATA_PROVENANCE_20260826.md`.

## Reproduce the headline analysis

```powershell
uv sync
.\.venv\Scripts\python.exe scripts\analysis\run_cross_agent_review_exploration.py
.\.venv\Scripts\python.exe scripts\analysis\run_response_ownership_analysis.py
.\.venv\Scripts\python.exe scripts\analysis\run_response_ownership_robustness.py
.\.venv\Scripts\python.exe scripts\analysis\run_coordination_topology_analysis.py
.\.venv\Scripts\python.exe scripts\analysis\run_burst_collapsed_topology.py
.\.venv\Scripts\python.exe scripts\analysis\run_deep_coordination_transitions.py
.\.venv\Scripts\python.exe scripts\analysis\run_legacy_extension_ownership_persistence.py
.\.venv\Scripts\python.exe scripts\analysis\run_human_memory_bridge_analysis.py
.\.venv\Scripts\python.exe scripts\analysis\run_addressed_edge_landmark_analysis.py
.\.venv\Scripts\python.exe scripts\analysis\run_addressed_edge_specificity_analysis.py
.\.venv\Scripts\python.exe scripts\analysis\run_addressed_edge_confounding_sensitivity.py
.\.venv\Scripts\python.exe scripts\analysis\run_addressed_edge_scope_audit.py
.\.venv\Scripts\python.exe scripts\analysis\run_rq3_extensions.py
.\.venv\Scripts\python.exe scripts\audit\prepare_review_collision_audit.py
.\.venv\Scripts\python.exe scripts\analysis\run_collision_descriptive_extension.py
.\.venv\Scripts\python.exe scripts\reporting\generate_technical_appendix_tables.py
.\.venv\Scripts\python.exe scripts\validation\validate_response_ownership_outputs.py
.\.venv\Scripts\python.exe scripts\validation\validate_coordination_extension_outputs.py
.\.venv\Scripts\python.exe scripts\figures\visualize_manuscript_figures.py
uv run --with pytest python -m pytest -q
```

Build the figures, paper PDF, and flat source bundle:

```powershell
.\scripts\build_submission.ps1
```

## Key outputs

- `outputs/coordination_topology/`: exact-edge funnel, exact-author match, route controls, and robustness.
- `outputs/burst_topology/`: 0--30 minute burst sensitivity and leave-one-out checks.
- `outputs/deep_coordination/`: post-burst next-state transitions and product-composition placebo.
- `outputs/ownership_persistence/`: exact-owner/layer persistence and bidirectional bounce falsification.
- `outputs/human_memory_bridge/`: strict earlier-review history, decisive-review check, and leakage validation.
- `outputs/addressed_edge_landmark/`: exact-parent edge landmark models and robustness.
- `outputs/addressed_edge_specificity/`: exact edge versus generic public-discussion controls.
- `outputs/addressed_edge_sensitivity/`: E-values, unmeasured-confounder tipping grid, negative-control outcomes, and repository-stratified randomisation inference.
- `outputs/rq3_extensions/`: whole-population time-varying edge model, and the edge split by who wrote the reply with its repository fixed-effect check.
- `outputs/addressed_edge_scope/`: who writes the addressed edge, the estimate under stricter edge definitions, what the hour-48 landmark excludes, and the conditional within-repository randomisation test.
- `outputs/external_validation/`: aggregate cross-dataset attribution, overlap, topology, and semantic-artifact audits.
- `outputs/review_collision/`: frozen 167-locus blinded dual-coder packet; semantic claims remain pending.
- `build/figures/Fig1_v2.pdf`: measurement contract, exclusion rules, and evidence levels.
- `build/figures/Fig2_v2.pdf`: RQ1 participation-to-edge and post-burst ownership figure.
- `build/figures/Fig3_v2.pdf`: RQ2 boundary visibility and prior-history figure.
- `build/figures/Fig4_v2.pdf`: RQ3 connected-signal and later-state figure.
- `build/figures/Fig5_v2.pdf`: RQ3 unmeasured-confounding bounds and placebo outcomes.
- `build/figures/Fig6_v2.pdf`: RQ3 without the hour-48 rule, and the edge split by who wrote it.
- `outputs/figures/dataset_schema_and_joins.pdf`: appendix map of both release layers and identifier joins.
- `outputs/figures/dataset_feature_coverage.pdf`: appendix view of feature availability and valid denominators.
- `paper/manuscript/main.tex`: EMSE manuscript source.
- `paper/manuscript/technical_appendix.tex`: full supplementary methods, estimates, falsification tests, and decision ledger.
- `build/pdf/emse_multiagent_submission_draft.pdf`: compiled author-review draft.
- `build/pdf/emse_multiagent_technical_appendix.pdf`: compiled Supplementary Information.
- `build/submission/emse_multiagent_coordination_draft_source.zip`: complete flat archival source bundle.
- `build/submission/emse_portal_staging/manuscript_source.zip`: main-paper-only flat source archive for Editorial Manager.
- `build/submission/emse_portal_staging/ESM_1.pdf`: separately staged Online Resource 1.
- `paper/SUBMISSION_METADATA_FORM.md`: author-approved metadata and declaration intake form.

## Superseded material

The `outputs/` tree also holds results from an earlier version of this study,
including files that reuse the names RQ1, RQ2, and RQ3 for different questions.
None of it feeds the paper. See `outputs/_superseded/README.md` for the list, and
`docs/decisions/NOVELTY_POSITION_20260826.md` for the novelty position of the submitted
manuscript.

## Submission gates

The analytical draft is reproducible, but live upload still needs author affiliation, corresponding email, declarations, ethics/consent wording, and an artifact URL/DOI. The official Editorial Manager page also displayed a temporary “site under development” warning on 2026-08-26 and must be rechecked. Semantic coding is required only if the authors later add duplication, complementarity, or contradiction claims; the present core paper does not make them. See `paper/SUBMISSION_READINESS.md` and `docs/decisions/VENUE_SIGNOFF_20260826.md`.
