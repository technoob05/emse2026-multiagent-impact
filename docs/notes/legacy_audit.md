# Legacy AIDev code audit for AIDev-7.6M

Audit date: 2026-08-25. Source repository: `D:\PhD_LetGoo\PhD_Farming\Legacy\AI_Dev_Dataminning`.

## Bottom line

The old code contains useful building blocks, but it is **not safe to rerun unchanged** on AIDev-7.6M. The strongest reusable material is the ordered-repository logic, the repo-agent matrix, file-level features, and reviewer-event aggregation. The old headline comparisons are mostly descriptive and suffer from future leakage, unresolved/overlapping PRs, repo selection, or partial rich-table coverage.

The most promising new paper experiment is an **artifact-level cross-agent handoff** study: after a closed-unmerged PR, determine whether the next agent continues the same files or linked issue, then compare same-agent continuation with cross-agent handoff. This turns a generic “agent switch” into observable continuity of work.

## Dataset/code compatibility

Old local data are AIDev v4-scale: 932,791 full PRs and 33,596 AIDev-pop PRs. New data contain 7,685,281 full PRs and 361,296 AIDev-pop PRs.

The main keys and columns are stable across versions: `pull_request.id`, `repo_id`, `agent`, `user_id`, outcomes/timestamps; `pr_commit_details.pr_id`, `sha`, `filename`, file and commit change fields; review/comment/timeline keys; issue links; and task labels.

Required porting changes:

- `src/config.py:10-46` points at `AIDev_dataset`, not `AIDev-7.6M`.
- `AGENT_ORDER` has five agents and omits `Google_Jules`; v5 labels are OpenAI Codex 3,844,602, Copilot 1,581,924, Claude Code 1,567,100, Cursor 317,453, Google Jules 296,411, and Devin 77,791.
- `TABLES["pr_review_comments"]` points to `pr_review_comments_v2.parquet`, which is absent in the new download; v5 provides `pr_review_comments.parquet`.
- v5 does not include `human_pull_request.parquet`, `human_pr_task_type.parquet`, or `user.parquet` in this checkout, so human-baseline branches will fail.
- `all_repository` and `repository` add `is_forked`; `pr_reviews` adds `pull_request_review_id`; `pr_task_type` adds denormalized PR fields. These additions do not break selected-column code.
- `rq6_multi_agent.py` calls `pd.read_parquet` indirectly on the entire 6.7 GB full PR file, including text. Port it to projected/streamed Polars, DuckDB, or PyArrow columns.
- Rich tables cover only AIDev-pop and are incomplete even there. `pr_task_type` has 32,702 unique PRs (about 9.1% of 361,296), has no Google Jules rows, and should not be treated as a corpus-wide label table.

## Reusable analyses

### 1. Repository-agent ecology

Path: `src/rq6_multi_agent.py`, especially `run()` lines 21-235.

Computes:

- number of agent brands per repository;
- per-agent repository coverage and PR volume;
- pairwise repo co-occurrence matrix;
- PR merge rates in single-agent versus ever-multi-agent repos;
- pair-specific merge rates in shared repos;
- chi-square tests and naive PR-level bootstrap intervals.

Compatibility: core schema is compatible, but the loader and agent metadata need the changes above.

Risks:

- “Multi-agent repo” is defined using the repo's entire future history, so PRs before the second agent arrived are labeled multi-agent.
- Single-versus-multi comparisons mix repository scale, maturity, popularity, task mix, and agent composition.
- Shared-pair repos can contain a third agent; the same PR can enter several pair comparisons.
- The 100-resample PR-level bootstrap ignores repo clustering.

Use: retain the co-occurrence/transition network only as descriptive context. Replace the outcome comparison with time-varying portfolios and within-repo transitions.

### 2. Sequential repository outcomes

Path: `src/rq_mining_deeper.py`, `d3_sequential_learning()` lines 192-250.

Computes the current PR merge rate conditional on the previous one or two same-repository outcomes, plus per-current-agent cascade gaps. Old output shows 83.6% after a merged PR versus 44.9% after a non-merged PR; two prior rejections have 31.6% merge rate. This is a useful path-dependence signal.

Compatibility: direct on the v5 AIDev-pop PR schema; the full 7.6M version needs streaming/sorting or the current project transition ledger.

Risks:

- It shifts a Boolean `merged` flag, so an unresolved/open prior PR is silently treated as a rejection.
- It does not require the prior PR to resolve before the current PR opens.
- Concurrent PRs are included and ordering ties are not controlled.
- It conditions only on the current agent, not the previous agent, contributor, task, or artifact.

Use: reuse the idea, not the code. The current project's leakage-safe episode ledger is a stronger base.

### 3. File, commit, issue, and review features

Paths:

- `src/feature_engineering.py`, `_detect_file_types()` lines 22-50, `_commit_features()` lines 53-63, `_effort_features()` lines 71-137, `_issue_linkage()` lines 140-147, and `build_feature_matrix()` lines 150-228.
- `src/rq2_behavioral.py`, task and churn analyses in `run()` lines 23-180.
- `src/rq7_human_ai.py`, reviewer dynamics in `run()` lines 47-276.

Computes PR-level file categories, file spread, churn, commit counts, comments/reviews, linked issues, task labels, reviewer counts/latency, and reviewer concentration.

Compatibility: most raw columns are stable in v5. Reviewer aggregation and filename aggregation are directly portable. Human comparison is not. Inline review comments have no direct `pr_id`, so the existing code skips or mishandles PR-level inline joins unless it resolves `pull_request_url`.

Critical risk: `_commit_features()` sums commit-level totals over `pr_commit_details`, which has one row per changed file. The same commit totals repeat across files, so additions/deletions/total changes can be multiplied by file count. Use file-level `additions/deletions/changes`, or deduplicate `(pr_id, sha)` before summing commit totals.

Use: file paths and linked issues are the best way to tell whether a later PR continues the same work. Reviewer identities can measure whether human context carries across an agent handoff.

### 4. Task specialization

Path: `src/rq2_behavioral.py`, `run()` lines 23-180; related controls in `src/rq_round6_responses.py`, `q3_task_type_covariate()` lines 45-159.

Computes per-agent task-type mixes, pairwise differences, merge rate by task type, and task-controlled outcome models.

Compatibility: the `id`, `agent`, and `type` fields remain. The human-table code must be removed.

Risks: v5 labels cover only 32,702 PRs, omit Google Jules, and appear to be an inherited/selected subset. Any portfolio conclusion needs a coverage/selection audit and should be labeled AIDev-pop task-labeled subset only.

Use: secondary validation for portfolio complementarity, not the primary paper mechanism.

### 5. Human and bot review interaction

Paths: `src/rq7_human_ai.py` lines 142-272 and `src/rq_mining_deep.py`, `m7_bot_bot()` lines 324-366.

Computes human reviewer counts, response latency, reviewer-load Gini, and whether an agent PR receives a bot comment/review.

Compatibility: human review tables are usable. A quick v5 AIDev-pop audit found 14,796 distinct human reviewers; 1,497 reviewed PRs from at least two agent brands, providing enough potential cross-agent bridges.

Risks: having a reviewer on the current PR is post-opening and may be a mediator or selection outcome; it cannot be used as a clean pre-treatment cause of merge. Bot reviewers are not necessarily coding agents, self-review must be identified, and AI-to-AI review is already a crowded novelty area.

Use: model reviewer continuity as a process mechanism or stratification, not a causal treatment.

## Analyses not worth porting as headline findings

- `src/rq_mining_deeper.py:d2_recovery_rate()` produced zero detected post-feedback responses for every agent in the saved output. Its event logic or timeline coverage must be repaired before use.
- `src/rq_mining_deeper.py:d5_human_coauthor()` equates multiple commit-author strings with human co-authorship; this can mix bots, aliases, and merge artifacts, and recent work already weakens co-authorship novelty.
- `src/rq_mining_deep.py:m7_bot_bot()` is agent-author/bot-reviewer co-occurrence, not evidence of multiple coding agents coordinating.
- Generic merge classifiers, comment taxonomies, raw task comparisons, and reviewer Gini are useful controls/context but are too crowded to carry a separate multi-agent paper.

## Three strongest reusable multi-agent ideas

### Rank 1: Artifact-level recovery handoffs

Combine the leakage-safe transition ledger with `pr_commit_details.filename` and `related_issue`.

For each prior closed-unmerged episode, classify the next eligible PR as:

1. same agent, same artifact;
2. different agent, same artifact;
3. same agent, different artifact;
4. different agent, different artifact.

Define artifact continuity as shared normalized file path, shared top-level module, or shared linked issue; report each definition separately. Then compare 30-day integration and review burden within repository/time/contributor strata.

Why it is stronger: it tests whether the observed “switch” is a real handoff on the failed work or merely an unrelated later PR. A cross-agent advantage only for shared artifacts would be direct evidence consistent with complementary recovery. A benefit only on different artifacts would falsify the recovery story.

### Rank 2: Human reviewer as the coordination bridge

Combine transition episodes with `pr_reviews` and `pr_comments`. Ask whether the same human who reviewed the failed PR also engages with the cross-agent successor, and whether continuity changes response time, review depth, or integration.

Strong design: define the bridge from the prior PR's reviewer set and analyze current reviewer continuity as a mechanism/process outcome. Stratify by artifact continuity and contributor continuity. Do not claim the bridge causes merge.

Why it matters: multi-agent work may need human-held project memory. This yields an actionable governance insight: preserving reviewer continuity may matter more than simply changing tools.

### Rank 3: Complementarity versus substitution in agent portfolios

Combine a time-varying version of `rq6_multi_agent.py` with task/file-domain features from `rq2_behavioral.py` and `feature_engineering.py`. At the date a second agent first appears, measure whether it expands the repository's task/file-domain coverage or duplicates the incumbent's niche, then follow outcomes and reviewer load.

Prefer file/module niches because they cover more PRs; use task labels only as a sensitivity subset. Estimate within-repository event-time changes and match on pre-entry activity. Avoid static ever-multi-agent labels.

Why it matters: the paper can distinguish “more tools” from a genuinely complementary multi-agent portfolio and link that difference to maintainers' workload.

## Recommended immediate port order

1. Port only filename/issue aggregation and join it to the current resolved-transition ledger.
2. Run the four-cell artifact-continuity experiment after closed-unmerged outcomes, with contributor-preserving results as the main diagnostic.
3. If the same-artifact cross-agent cell is adequately sized and the effect survives repo/time controls, add reviewer continuity as the mechanism layer.
4. Use time-varying portfolio specialization only as a fallback or third RQ; do not lead with raw single-versus-multi merge rates.

