# Cross-dataset compatibility audit (2026-08-26)

> **Historical record.** This document was written when the study had three
> research questions. RQ4, on issue linkage across the product boundary, was
> added later. Read it as a record of a decision at the time, not as a
> description of the current paper.

## Decision

The completed acquisition pass downloaded the full pinned SWE-Review-Chat
release and smaller attribution and semantic-validation artifacts. It found no
honest disjoint replication cohort for the present three RQs:

1. The August 2025 AIDev snapshot is a **version-portability check**, not
   external validation: 97.34% of its PRs also occur in the current release.
2. SWE-Review-Chat is schema-compatible after candidate-only REST enrichment,
   but all seven exact nested-parent candidates already occur in AIDev. Zero
   disjoint landmark rows remain after overlap removal.
3. The independently packaged AI-to-AI cohort closely supports product-pair and
   trigger-time attribution on overlapping PRs, but only nine exposed PRs
   remain. Its outcome intervals are appendix sensitivity evidence, not an
   independent estimate.
4. SWE-PRBench and AIReviewAction support semantic codebook design only; neither
   preserves the exact reply topology required by the RQs.

GH Archive has the right event shape in principle. The local cache covers only
one UTC day, however, and contains no complete cross-product trigger--response
case with an observable author product and follow-up window. It remains a future
prospective temporal-replication route, not analysis-ready evidence for this
submission.

The current AgentAssign REST bundles can support a coarser review-response
study, but they omit the inline review-comment records needed to identify an
exact reply parent. Function-vulnerability, code-attribution, speech, vision,
and code-retrieval corpora are incompatible with the event-anchored design.

The local-inventory sections below are retained to document why each acquisition
was attempted and which frozen stop rule fired.

## The minimum observability contract

An external source must preserve the paper's unit of analysis: an event on a
specific pull request, observed from a frozen source version through a declared
cutoff. Similar-looking proxy fields are not equivalent.

| Construct | Required observable fields after normalization | Why it is required |
|---|---|---|
| PR trigger | `pr_id`, `repo_id`, PR author product, PR creation time; event ID, kind, time, and reviewer product | Anchors exposure to one real review event on one eligible PR. |
| Exact reply parent | Response `parent_event_id` resolving to the trigger `event_id` | Separates an addressed reply from mere co-presence or temporal succession. |
| Review batch | `review_batch_id` for submitted and inline review records | Prevents one GitHub review submission from appearing to answer itself. |
| Public actor/product | Public actor login/type plus a versioned product registry | Makes product attribution auditable and time-valid. A login substring is not enough. |
| Later state | PR creation, close, and merge times plus event time | Builds the open-at-landmark risk set and observes later merge without immortal-time leakage. |
| Observation boundary | Source revision/manifest and fixed observation cutoff | Prevents current state or later events from entering pre-trigger features. |

The code representation of this contract is in
`src/external_validation/contracts.py`. It deliberately has no downloader and
fails closed if exact topology or the temporal boundary is missing.

## Compatibility matrix

The status below describes the data available locally, not a claim about every
possible future collection from the source.

| Candidate | Event-shape status | Usable now for the paper's event-anchored estimand? | Evidence and restriction |
|---|---|---|---|
| AIDev v5, revision `37bbe1533e26cc1e1374917dba1186d1c8a4dc81` | **FULL (reference corpus)** | Yes, subject to the existing quality gates | Exact parent links, review-batch IDs, public product labels, PR state, timestamps, and a 2026-03-31 cutoff are present. This is the primary corpus, not external evidence. |
| Older AIDev snapshot, revision `288c5aa77c338b1f905f875b64c381103a0af566` | **FULL after adapter; non-independent** | Yes, for version portability only | Use `pr_review_comments_v2`; alias review `id` to batch ID. Exact parent and review joins are strong, but 32,702 of 33,596 PR IDs overlap v5. |
| GH Archive event stream | **FULL in principle** | **No: local support/horizon failure** | The format exposes PR, review, inline-comment, reply-parent, review-batch, actor, and merge events. The local cache is only 2026-07-01 and cannot recover earlier PR openings or a 48-hour landmark plus later outcome. |
| AgentAssign local REST PR bundles | **CONDITIONAL** | No for exact addressed replies | PRs, reviews, actors, submitted-review IDs, state, retrieval provenance, and public identity registry exist. Inline review comments and `in_reply_to_id` are not fetched. The local bundles also contain no observed cross-product review exposure. |
| AgentAssign public analytical tables | **INCOMPATIBLE for this estimand** | No | Their unit is explicit assignment/attempt, not an addressed review edge. Privacy-safe release tables are not a substitute for raw event topology. |
| PrimeVul v0.1 | **INCOMPATIBLE** | No | Unit is a function/commit vulnerability label; no PR trigger, exact reply, review batch, actor product, or later PR state. |
| Local AI-code detection corpora | **INCOMPATIBLE** | No | Unit is code/text for attribution; no PR event graph or later state. |
| CCEval/ReccEval archives | **INCOMPATIBLE** | No | Unit is code completion/retrieval context; repositories are content inputs, not longitudinal PR review histories. |
| Cached FLEURS and other speech/vision assets | **INCOMPATIBLE** | No | Modalities and grains are unrelated to public software-review events. |

## Local inventory and targeted disk use

This is a targeted inventory of plausible or large cached datasets, not a claim
that every file under the workspace was catalogued.

| Local source | Files / observed scale | Disk use | Role |
|---|---:|---:|---|
| `Legacy/AI_Dev_Dataminning/AIDev-7.6M` | 46 files; 361,296 rich PRs | 12.408 GiB | Primary AIDev v5 source |
| `Legacy/AI_Dev_Dataminning/AIDev_dataset` | 51 files; 33,596 rich PRs | 0.903 GiB | Older-snapshot portability check |
| `agentassign/.cache/gharchive` | 24 hourly gzip files, one UTC day | about 0.517 GiB | Independent event-stream pilot only |
| `agentassign/data` | 980 files including 226 local PR bundles | about 65.5 MiB | Assignment study plus limited PR enrichment |
| Current project `outputs/cache` | 5 files | about 29.5 MiB | Derived cache; not independent data |
| Current project `outputs` | 326 files | about 71.4 MiB | Derived analysis outputs |
| User Hugging Face cache | dominated by one FLEURS speech blob | about 0.648 GiB | Incompatible modality |
| `Legacy/Vul_Detect/PrimeVul_v0.1` | commit/function records | about 1.253 GiB | Incompatible grain |
| `Legacy/ai_code_detection` | code/text attribution data | about 0.329 GiB | Incompatible grain |
| Local CCEval/ReccEval archives | 4 archives | about 3.532 GiB | Incompatible task |

The local Hugging Face cache did not contain a second compatible PR-review
corpus. No usable Kaggle dataset cache was found.

## Evidence behind the compatibility decisions

### AIDev v5 reference corpus

- `pull_request` has 361,296 unique PR IDs from 25,402 repositories, with PR
  creation dates from 2024-12-24 through 2026-03-31.
- `pr_reviews` has 281,170 unique, timestamped review records.
- `pr_review_comments` has 289,780 unique, timestamped comments. All 289,780
  resolve to a review batch. Of 88,907 comments with a parent ID, 88,878 parent
  IDs resolve locally.
- Some timeline rows are unusable for temporal ordering: all 619,218
  `committed` rows and all 147,694 `reviewed` rows lack a timestamp. Review and
  inline-comment tables must remain the temporal source for those constructs.
- Corpus-level timestamp checks found 47 closed-before-created and 45
  merged-before-created PRs. These cases should remain excluded by the current
  quality gates rather than silently repaired.

### Older AIDev snapshot

- `pull_request` has 33,596 unique PRs from 2,807 repositories, created from
  2024-12-24 through 2025-07-30.
- The complete inline-comment table is `pr_review_comments_v2` (26,868 unique,
  timestamped rows), not the older incomplete `pr_review_comments` table
  (19,450 rows).
- The old `pr_reviews` table lacks a field named
  `pull_request_review_id`, but its unique `id` joins every one of the 26,868
  v2 comment rows. The adapter may therefore map `pr_reviews.id` to canonical
  `review_batch_id` without inventing a proxy.
- Of 8,904 v2 comments with a parent, 8,894 parent IDs resolve locally.
- As in v5, the timeline `committed` and `reviewed` event types have no usable
  timestamps. They cannot define event order.
- The 97.34% PR-ID overlap with v5 means this exercise tests whether results
  survive corpus growth and schema changes. It must not be described as
  independent replication.

### GH Archive: correct shape, insufficient local window

The cached day contains GitHub event payloads rather than a ready analytical
table. A sample hour confirmed that `PullRequestReviewCommentEvent` carries
`pull_request_review_id` and, when it is a reply, `in_reply_to_id`.
`PullRequestReviewEvent` identifies submitted review batches, while
`PullRequestEvent` records PR openings and later merge actions.

Across all 24 cached hours, the scan found 113 product-authored PR openings,
13,276 review or inline-comment events, and 9,556 merge events. There were no
cross-product review/comment events on a product-authored PR whose opening was
also visible in that day, and no complete cross-product exact-parent reply
chain. This is a support result for the **local one-day cache**, not evidence
that the behavior never occurs.

Using only a PR's current API state would not fix the problem: it would mix a
later snapshot into an earlier risk set. An event-stream adapter must first
freeze the source files and cutoff, reconstruct PR author product at opening,
then derive trigger and outcome within declared windows.

### AgentAssign: useful components, incomplete topology

The local AgentAssign enrichment has 226 PR bundles, 620 submitted reviews,
6,137 timeline events, 1,087 commits, and 2,493 files. Seventy-eight PR objects
declare 876 inline review comments, but the comment records themselves were not
fetched. Consequently, the exact parent edge is not observable.

The bundles contain product-authored PRs and submitted reviews, but the local
sample has zero cross-product review exposures. Its retrieval is a narrow
current-state snapshot, so any later-state analysis would also need a declared
cutoff and a new prospective window.

AgentAssign still provides three strong reusable components:

- a conservative AIDev crosswalk that tries ID, then URL, then repository plus
  PR number and rejects conflicting or ambiguous matches;
- a GH Archive source-manifest validator that checks exact hourly coverage,
  gzip integrity, SHA-256 hashes, and a fixed UTC range;
- a versioned registry of verified public product identities with validity
  windows.

Its GitHub client would need a new pull-review-comments endpoint and a
normalizer for `id`, `pull_request_review_id`, `in_reply_to_id`, `created_at`,
and actor before it could meet the exact-reply contract.

## Legacy code reuse audit

| Legacy component or pattern | Decision | Safe use / reason |
|---|---|---|
| `AIDev-7.6M/scripts/load_aidev.py` | Reuse pattern | Column projection and PyArrow batch streaming are appropriate for large Parquet tables. |
| Legacy `src/data_loader.py` | Adapt, do not copy wholesale | Table map and datetime coercion are useful; the hard-coded old path, full-table reads, mutable cached frames, and missing grain assertions are not. |
| File-type and commit-count feature helpers | Reuse conditionally | Valid only when computed from artifacts observed before the trigger/landmark. |
| Standardized-mean-difference balance diagnostic | Reuse | Useful as a model diagnostic. Do not reuse the old matcher, which permits control reuse and does not enforce the present temporal contract. |
| Reviewer identity/load/latency concepts | Adapt | Freeze the identity registry and restrict every feature to pre-trigger history. |
| Repository-ever-multi-agent labeling | Reject | It uses future repository activity to label earlier PRs. |
| Sequential outcome shifting by PR creation order | Reject | The previous final outcome may not have been known when the next PR was created. |
| Full-lifecycle recovery or effort features | Reject for causal models | Last feedback, last response, total interactions, and final merge state leak post-trigger information. |
| Timeline-based ghosting from `committed` events | Reject | The required timeline timestamps are missing in both local AIDev snapshots. |
| Legacy AIDev downloader | Reject for validation | It is path-specific, revision-unpinned, and downloads a full snapshot rather than a declared validation slice. |

## Leakage and validity gates

Any future adapter or external experiment should stop rather than estimate when
one of these gates fails:

1. Freeze source revision/files, identity-registry revision, event range, and
   observation cutoff before looking at the outcome.
2. Resolve PR author product from the public PR-opening actor (or an audited
   time-valid crosswalk), never from the later reviewer or repository label.
3. Require the response parent ID to equal the trigger ID for the addressed-edge
   estimand. Co-presence and a short time gap are separate sensitivity designs.
4. Collapse or identify review batches before ordering submitted reviews and
   inline comments.
5. Compute covariates only from information available before the trigger or
   declared landmark.
6. Include only PRs open at the landmark; observe merge/closure only through the
   fixed cutoff.
7. Report product-pair and repository support before fitting a model. A schema
   can be compatible while the realized sample has no overlap.
8. Preserve source-specific missingness. Do not convert a missing timestamp or
   unavailable parent edge into a negative event.

## A bounded external-validation plan

Do not download a month of GH Archive blindly. The next defensible step is a
small, declared pilot:

1. Implement a read-only GH Archive adapter against the existing local hourly
   files and emit only canonical PR/event rows plus a provenance manifest.
2. Confirm identity mapping, exact-parent resolution, review-batch resolution,
   and product-pair support on that fixed pilot.
3. If support is plausible, predeclare a continuous trigger interval and retain
   enough post-trigger data for the 48-hour landmark and 30-day follow-up.
   Use GitHub API enrichment only for candidate PR metadata missing from the
   archive; keep archived events as the primary temporal record.
4. Freeze the candidate set before extracting outcomes, then run the same
   topology and landmark validators used for AIDev.

At the observed local compression rate (about 0.517 GiB per day), 33 continuous
days would be roughly 17.1 GiB compressed. This is only a one-day extrapolation
and excludes API caches, derived tables, and any pre-trigger history needed to
observe earlier PR openings. It is a planning estimate, not a download request.

## Adapter scaffold and checks

The non-destructive scaffold is under `src/external_validation/` and contains:

- a source-agnostic schema assessment;
- timezone, exact-parent, review-batch, and landmark validators;
- a read-only adapter protocol; and
- no network client, downloader, or materializer.

Focused tests live in `tests/test_external_validation_contracts.py` and can be
run with:

```powershell
uv run --with pytest python -m pytest -q tests/test_external_validation_contracts.py
```

The current focused result is 5 passing tests.
