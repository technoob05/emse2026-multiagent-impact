# External dataset survey for the multi-agent review study

**Audit date:** 26 August 2026  
**Scope:** public datasets that may strengthen the event-level study of cross-product code review, exact public reply edges, later public ownership, user-account bridges, and later merge.  
**Decision rule:** value for the three current RQs matters more than row count.

## Decision in one page

One source remains worth a future replication effort:

1. **GH Archive plus targeted GitHub REST enrichment** is the strongest design for an out-of-time replication. Query only public PR/review/comment events after the AIDev observation boundary, require each focal PR to be created after that boundary, then fetch review-comment records for candidate PRs to recover `in_reply_to_id`, comment time, review-batch ID, actor, and outcome. A frozen window such as 16 April--26 July 2026 has no PR-time overlap with the current AIDev analysis and has 30 complete outcome days by this audit date. This is a temporal replication on the same platform, not a cross-platform replication.

**SWE-Review-Chat** was the strongest packaged candidate and was downloaded in
full at a pinned revision. The fail-closed scan found seven PRs where a mapped
cross-product inline parent had a nested reply, but all seven already occur in
the full AIDev corpus. After overlap exclusion, zero PRs remained for REST
hydration or the 48-hour landmark. This rejects an independent replication in
the current release. It does not show that exact public connections never
occur. The complete funnel is recorded in
[`SWE_REVIEW_CHAT_EXACT_EDGE_PILOT_20260826.md`](SWE_REVIEW_CHAT_EXACT_EDGE_PILOT_20260826.md).

One small complementary dataset is also worth keeping:

- **SWE-PRBench** contains 350 real merged PRs and human initiating review comments with source links and diffs. It cannot replicate any of the three RQs, but it is a compact, permissively licensed corpus for testing whether a future semantic codebook distinguishes substantive initiating feedback from generic review text.

The large alternatives do not solve the measurement problem:

- **CodAGE** is valuable for its product-identity registry and for reproducing the already-published AI-to-AI prevalence study, but its public normalized review-comment rows omit `in_reply_to_id` and human response events.
- **OSAPRD** and **GitHub Agentic PR Dataset** add millions of author-attributed PRs and code diffs, but no event-level review threads. The latter explicitly extends AIDev.
- **SWE-chat**, **Trace Commons**, and **SWE-Review-Traj** contain rich private or controlled agent traces, not observable GitHub review-response edges.

No audited source provides a credible cross-platform replication of GitHub PR review topology. The paper should therefore call the proposed check an **external temporal or independently packaged replication on GitHub**, not broad ecosystem generalization.

The machine-readable decisions and field-level audit are in [`external_dataset_registry.csv`](../protocol/external_dataset_registry.csv).

## Fit to the current RQs

The registry applies these minimum contracts:

| RQ | Minimum evidence | Disqualifying absence |
|---|---|---|
| RQ1 -- connected handoff and next public owner | PR author product; reviewer product; event ID and time; review batch; later review, inline/PR comment, or branch movement | only PR-level activity counts; reviewer product without later public actors |
| RQ2 -- boundary bridge and prior public history | stable GitHub login; repository; PR ID; event time; a different-PR review history before the trigger | anonymized session identity; no repository-wide event history |
| RQ3 -- early connection and later state | exact `child.in_reply_to_id = trigger.id`; exposure fixed by hour 48; merge strictly after hour 48 and by day 30 | thread membership without reply time; merge snapshot without exposure timing |

PR-level co-presence is not a handoff. Thread membership without a parent ID is not an exact addressed edge. A merge flag observed at collection time is not a valid landmark outcome unless its timestamp is available.

## Recommended replication designs

### A. Primary: post-cutoff GH Archive cohort

Use GH Archive only as a discovery layer and GitHub's public REST API as the strict enrichment layer.

1. Freeze a disjoint period after AIDev's 15 April 2026 common boundary and require focal PR creation on or after 16 April. At this audit date, triggers through 26 July 2026 have at least 30 complete later days.
2. Query only `PullRequestEvent`, `PullRequestReviewEvent`, `PullRequestReviewCommentEvent`, `IssueCommentEvent`, and `PushEvent` partitions. Do not download the full archive.
3. Attribute author and reviewer products using a versioned exact-identity registry. Do not infer products from similar-looking names.
4. For each candidate PR, request public review comments and preserve `id`, `in_reply_to_id`, `pull_request_review_id`, `user.login`, `created_at`, and PR URL. Log HTTP status, deleted/missing comments, pagination, and fetch time.
5. Reconstruct the same trigger, review de-batching, rapid-burst washout, first later owner, 48-hour exposure, and 30-day later-merge contracts used in the main study.
6. Report it as an out-of-time same-platform replication. It is not an independent platform, randomized treatment, or evidence that products privately communicate.

This design can **replicate** the exact-edge result because the observation period is disjoint and the parent field is available. Historical GH Archive rows overlapping AIDev would merely re-extract many of the same public events.

### B. Completed check: SWE-Review-Chat held-out cohort

SWE-Review-Chat is easier to package and attribute, but a disjoint cohort did
not survive the exact eligibility and overlap rules.

1. Join `repo_full_name + pr_number` (or canonical `pr_url`) to AIDev and remove every overlapping focal PR.
2. Restrict to author and reviewer products that can be mapped by exact official GitHub identities.
3. Use the nested parent--`thread_replies` structure only to select candidate edges. Rehydrate both parent and child comment IDs through GitHub REST because nested replies do not contain reply time.
4. Require successful timestamp and parent recovery before applying the 48-hour landmark. Report missing/deleted IDs as a denominator, not as no reply.
5. Run the same event-grain analysis only if a disjoint cohort survives; do not
   import the source paper's broad reviewer-sequence labels as if they were the
   current paper's handoff states.

The public viewer sample exposed these nested reply fields: `reviewer`, `reviewer_type`, `body`, and `comment_id`. It did not expose reply timestamp or `in_reply_to_id`. For one inspected thread in `Altinn/altinn-studio#8086`, REST lookups returned:

| Comment | REST `created_at` | REST parent |
|---:|---|---:|
| 824381765 | 2022-03-11T04:40:58Z | root |
| 875896655 | 2022-05-18T13:27:32Z | 824381765 |
| 876098788 | 2022-05-18T16:21:47Z | 824381765 |

This verified the enrichment route for the inspected thread only. The later
full-corpus audit stopped before content hydration because all exact candidates
overlapped AIDev. The current verdict is therefore
`REJECT_REPLICATION_ZERO_DISJOINT_SUPPORT`.

## Novelty collisions

The survey narrows, rather than removes, the paper's novelty.

| Existing source | Claim space already occupied | Boundary the current paper must keep |
|---|---|---|
| AI-to-AI Code Reviews / CodAGE | existence, prevalence, growth, author--reviewer product matrix, comment volume/category, and first-review latency for AI-reviewed PRs | do not claim first AI-to-AI or cross-product review; focus on exact parent edges, de-batching, later owner, and a landmarked later state |
| From Human-Centric to Agentic Code Review / SWE-Review-Chat | human/LLM/agent review eras, ordered reviewer interaction sequences, efficiency and quality associations | do not claim first reviewer-sequence or mixed-review study; the residual unit is one exact heterogeneous-product trigger and its public edge topology |
| Human-AI Synergy / AgentReviewChat | human-versus-agent feedback, discussion rounds, suggestion adoption, and code-change consequences | do not claim first study of human response or suggestion uptake; RQ2 concerns which public account bridges the boundary and its prior repository-review history |
| SWE-Review | controlled generate--review--revise loops and executable issue resolution | do not generalize a controlled reviewer-agent benefit to field merge; field estimates remain observational associations |
| SWE-chat | real private/session-level human--agent conversation, user pushback, code attribution and commit survival | do not imply that public GitHub events expose private prompts, tool calls, plans, or shared memory |
| SWE-PRBench | LLM issue-detection quality against substantive human review comments | do not turn merge association into review correctness or code quality |

The defensible residual contribution is an **event-level public topology**: exact parent edge, review batch, rapid fan-out, next visible owner, automation-to-user relay, prior public reviewer history, and a time-frozen later state. It is narrower than “multi-agent collaboration” and should stay that way.

## Candidate-by-candidate interpretation

### Replication candidates and realized support

- **GH Archive + GitHub REST:** direct support for all three RQs after narrow post-cutoff querying and REST enrichment. The raw archive has no blanket data license stated on its site; public GitHub content remains governed by GitHub terms and original repository/content licenses. Store derived event metadata where possible and do not redistribute raw bodies unnecessarily.
- **SWE-Review-Chat:** schema support was promising, but the full exact-edge
  audit leaves zero non-AIDev candidate PRs. It is retained as a documented
  failed replication gate, not as RQ1 or RQ3 confirmation. Apache-2.0 is
  declared for the dataset. Source GitHub code and text may still carry
  original licenses.

### Useful only for triangulation or validation

- **CodAGE and its closed-loop cohorts:** strongest source for a current product-identity crosswalk and direct novelty-collision audit. They cannot identify exact human or agent replies to a trigger from the normalized public fields.
- **Agent Archive:** PR timelines, author agent, user logins, merge time and movement events are useful, but the card warns that the Timeline API is capped and time-limited. Its normalized line-comment example has no parent field, and the dataset declares no license. Treat it as a schema sample until parent coverage and license are clarified.
- **SWE-PRBench:** compact semantic validation data; initiating human comments only; all focal PRs are merged, so it has no RQ3 outcome variation.
- **PRcurator v1:** recent PR IDs, AI-authorship probability, aggregate human/bot engagement and diffs. It is heavily concentrated in `microsoft/vscode`, uses heuristic/LLM scores, and omits event threads. It can audit author-label sensitivity, not handoff topology.
- **SWE-chat:** possible mechanism triangulation through `repo_id` and `commit_sha`, but its interaction is between a user and a coding agent inside a session. It cannot substitute for public PR review-response evidence.
- **SWE-Review-Bench / SWE-Review-Traj:** useful controlled counterpoint with executable `patch_resolved`, reviewer decisions, structured reports and tool traces. They are generated evaluation/training trajectories, not naturally occurring GitHub review exchanges.

### Reject for this paper

- **AgentReviewChat public release:** the Hub exposes only 100 rows although its card describes a much larger study corpus. It is superseded for access and coverage by SWE-Review-Chat and directly collides with suggestion-adoption claims.
- **GitHub Agentic PR Dataset:** explicitly extends AIDev and contains PR, commit, patch and merge tables but no reviewer-event topology. It is mostly duplicated rows at much higher storage cost.
- **OSAPRD full corpus:** broad author-product coverage but no event-level reviewer identity or parent replies; the Hub page does not declare a dataset license. Use only a metadata/sample audit if its identity registry becomes necessary.
- **Trace Commons:** 30 voluntary sessions at the pinned revision, best-effort anonymization, no stable PR review edge or outcome, and no representative sampling frame.

## Download order and stop rules

No large dataset was downloaded during this audit. Only Hub metadata, Dataset Viewer schemas/first rows, repository documentation, paper pages, and three public review-comment records were inspected.

If the study proceeds, use this order:

1. Query a small post-cutoff GH Archive partition and enrich a fixed pilot of candidate PRs. Stop if exact author/reviewer attribution or parent recovery is too sparse.
2. **Completed:** the full pinned SWE-Review-Chat release was downloaded and
   integrity-checked. The pre-set stop rule fired because every exact candidate
   overlaps AIDev; do not spend API budget or compute on an RQ3 model.
3. Download SWE-PRBench in full only for a pre-specified semantic validation task.
4. Keep CodAGE, OSAPRD, SWE-chat, SWE-Review, Agent Archive, and PRcurator at metadata/sample level unless a named analysis requires their unique fields.
5. Do not download the 87--128 GB GitHub Agentic PR extension or the full 44 GB OSAPRD corpus for the current RQs.

## Primary sources checked

- GH Archive: <https://www.gharchive.org/>
- GitHub event types: <https://docs.github.com/en/rest/using-the-rest-api/github-event-types>
- GitHub PR review-comment REST API (`in_reply_to_id`): <https://docs.github.com/en/rest/pulls/comments>
- GitHub Terms of Service, public repositories: <https://docs.github.com/en/site-policy/github-terms/github-terms-of-service>
- SWE-Review-Chat dataset: <https://huggingface.co/datasets/Suzhen/SWE-Review-Chat>
- SWE-Review-Chat repository: <https://github.com/suzhenxzhong/SWE-Review-Chat>
- From Human-Centric to Agentic Code Review: <https://arxiv.org/abs/2607.13196>
- Human-AI Synergy in Agentic Code Review: <https://arxiv.org/abs/2603.15911>
- CodAGE dataset: <https://huggingface.co/datasets/taher-ghaleb/CodAGE>
- AI-to-AI Code Reviews paper: <https://arxiv.org/abs/2608.21311>
- AI-to-AI replication package: <https://github.com/Niruthiha/AI-AI-CodeReviews>
- AgentReviewChat: <https://huggingface.co/datasets/Suzhen/AgentReviewChat>
- Agent Archive: <https://huggingface.co/datasets/nuprl-staging/agent-archive>
- GitHub Agentic PR Dataset: <https://huggingface.co/datasets/mabujadallah/GitHub-Agentic-PR-Dataset>
- OSAPRD: <https://huggingface.co/datasets/OSAPRD/OSAPRD>
- SWE-chat: <https://huggingface.co/datasets/SALT-NLP/SWE-chat>
- SWE-chat paper: <https://arxiv.org/abs/2604.20779>
- Trace Commons: <https://huggingface.co/datasets/trace-commons/agent-traces>
- SWE-Review-Bench: <https://huggingface.co/datasets/Lego-X/SWE-Review-Bench>
- SWE-Review-Traj: <https://huggingface.co/datasets/Lego-X/SWE-Review-Traj>
- SWE-Review paper: <https://arxiv.org/abs/2607.06065>
- SWE-PRBench: <https://huggingface.co/datasets/foundry-ai/swe-prbench>
- SWE-PRBench paper: <https://arxiv.org/abs/2603.26130>
- PRcurator v1: <https://huggingface.co/datasets/nitinmurali21/prcurator-v1>

## Evidence and interpretation notes

- Row counts, file sizes, revisions, licenses, gates and schemas were checked against the Hub API or Dataset Viewer on the audit date. A Hub license tag applies to the dataset package; embedded source code and public GitHub text can retain separate rights.
- “Exact edge available” means an explicit parent relation can be recovered. A nested thread alone is not enough for the hour-48 analysis when the child timestamp is missing.
- “External replication” here means a disjoint time period or independently packaged, non-overlapping PR cohort using the same frozen construct. It does not mean an independent platform or causal identification.
- The verdicts are acquisition decisions for this paper, not judgments of dataset quality in their original use cases.
