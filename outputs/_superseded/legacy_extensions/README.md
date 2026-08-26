# Legacy extensions: repository memory after cross-product feedback

Run date: 2026-08-26

## Decision

**KEEP, as a descriptive mechanism:** after one AI product gives feedback on a PR attributed to another product, the user accounts that enter the response often have recent review experience in that repository. The clean paper idea is a **repository-memory bridge**: products can create and critique code, while user accounts with local history often carry the work into review and decision stages.

**REJECT the stronger intentional-routing claim:** the export shows that a review request happened, but it never records the requested account. It cannot show that someone deliberately requested the product that later supplied the trigger.

Neither result is causal. GitHub's `User` type identifies an account class, not verified unaided human action.

## Main retained result

The base cohort contains 8,608 PRs with cross-product feedback and complete seven-day observation.

- There are 3,603 PRs with one observable first `User`-type responder within 48 hours.
- 2,567/3,603 (71.2%) of these accounts had submitted a review on a **different PR in the same repository strictly before the feedback trigger**.
- The first account was the PR author in 1,372 cases; 920 (67.1%) had strict prior review history. It was another user account in 2,231 cases; 1,647 (73.8%) had strict prior review history.
- Among experienced first responders, the median was 9 earlier reviewed PRs and 17 earlier review events; the latest earlier review was a median 1.51 days before the trigger.
- When the first later decisive review overall was owned by a user account, 1,580/2,020 (78.2%) of those reviewers had the same strict prior-history signal. These were all accounts other than the agent-attributed PR author.

The response channel helps explain the pattern. Prior-review history appears for 1,455/1,863 (78.1%) first responses that are submitted reviews, 354/448 (79.0%) direct inline replies, and 758/1,292 (58.7%) PR comments. This is useful mechanism evidence, but part of the association is naturally tied to the kind of action being observed.

## Comparison populations and uncertainty

The most relevant observable comparison is all 4,814 distinct PR-account responders within 48 hours: 3,381 (70.2%) have strict prior review history. Therefore, experience is common across the response layer; the unadjusted difference between first responders and all responders is only about one percentage point. A repository-clustered linear model controlling author-account status estimates first position at +5.0 points (95% CI +0.26 to +9.75), but it does not control response channel or account-level dependence. Do **not** claim that experienced reviewers are preferentially selected to respond first.

A contextual, less comparable baseline is the 6,695 user-like PR-author accounts in the full cross-feedback cohort: 51.9% have prior same-repository review history. The denominator includes accounts that never respond, so it should not be used as an at-risk causal control.

Concentration checks support portability but also show an imbalanced product mix:

- 834 repositories contribute the 3,603 first responders. The largest repository supplies 6.1%, the top ten 23.6%, and the repository HHI is 0.0102.
- Leaving out one repository at a time moves the 71.2% history share only to 69.4%-72.0% (largest absolute change 1.86 points).
- There are 23 observed author-product/reviewer-product pairs. The largest pair supplies 31.3% and the top five 65.3%.
- Leaving out one product pair moves the history share to 69.4%-73.8% (largest absolute change 2.59 points).
- The author-account versus other-user difference is +6.77 points with repository-clustered 95% CI -2.04 to +15.57. Treat the role split as descriptive, not a stable contrast.

## Review-request context

There are 10,402 valid timestamped `review_requested` events between PR creation and the trigger, covering 6,343/8,608 PRs (73.7%). For the last request before each trigger, requester roles are:

| Last requester role | PRs | Share of requested PRs |
|---|---:|---:|
| PR author account | 4,545 | 71.7% |
| Other user-like account | 1,162 | 18.3% |
| Mapped agent account | 546 | 8.6% |
| Other bot account | 90 | 1.4% |

However, `assignee`, `message`, and `label` are null for every valid request row. Requested-account coverage is 0/10,402, so exact triggering-product matches are necessarily 0. The only safe statement is: **a review request often occurred shortly before the observed feedback**. It is not evidence that the triggering product was intentionally requested.

## Data-grain and leakage audit

| Source | Rows | Grain and safe link | Main gate |
|---|---:|---|---|
| `pull_request.parquet` | 361,296 | one PR; `id -> pr_id` | final outcomes must not be used as pre-trigger covariates |
| `pr_reviews.parquet` | 281,170 | one submitted review; unique `pull_request_review_id` | `submitted_at` is usable |
| `pr_review_comments.parquet` | 289,780 | one inline comment; join by `pull_request_review_id` | no direct `pr_id`, but join coverage is 289,780/289,780 |
| `pr_comments.parquet` | 373,549 | one PR comment; direct `pr_id` | distinguish thread comments from inline replies |
| `pr_timeline.parquet` | 3,018,358 | one timeline event | all 619,218 `committed` and 147,694 `reviewed` rows lack timestamps |
| `pr_commit_details.parquet` | 6,112,623 | one file per PR commit | commit totals repeat across files; deduplicate SHA before totals |

The retained history rule is same repository + same login + different PR + `review_dt < trigger_dt`. Validation excluded 8,133 candidate same-PR rows and 150,114 candidate future/equal rows for responder targets. Valid matches contain zero same-PR rows and zero future/equal rows. The analogous decisive-review and author-baseline checks also pass.

Task labels cover only 1,313/8,608 (15.3%) and related issues 1,149/8,608 (13.4%), so neither is suitable as a primary adjustment variable. Timeline `committed`/`reviewed` events cannot establish post-trigger order.

## Ranked experiment cards

### 1. Repository-memory bridge — KEEP

- **Inputs:** cross-feedback response chains/events, reviews, PR-to-repository map.
- **Unit:** PR-account for responder history; one PR for the first-responder and first-decisive summaries.
- **Estimand/metric:** share with a submitted review on another PR in the same repository before trigger; prior distinct PR count and recency.
- **Falsification gate:** no same-PR or future review history; repository and product-pair leave-one-out; compare first responders with all observed responders.
- **Value:** supports a clear division-of-labor story about repository memory and decision authority.
- **Risk:** account types do not prove human labor; responder selection and action channel confound comparisons.

### 2. Conversation-to-artifact shift — KEEP only as matched descriptive evidence

- **Inputs:** current cross-versus-same feedback ledger, pre-trigger PR activity, force-push timeline.
- **Unit:** 668 exact repo/author-product/source/month matched pairs from 165 repositories.
- **Metric:** paired differences in PR comment, review, direct reply, force-push, and seven-day merge.
- **Observed profile:** cross-product feedback has fewer later PR comments (-13.0 points) and more force-pushes (+4.8 points). Merge is +6.4 points in the base match but loses stability after controlling author account and pre-trigger activity.
- **Falsification gate:** safe pre-trigger age/activity CEM, author-account restriction, suggestion-free restriction, body-length overlap.
- **Value:** supports “feedback moves toward the branch” more safely than “cross-agent feedback improves success.”
- **Risk:** trigger text differs strongly; concurrent suggestion content is mechanism/selection, and merge is not robust enough for a causal headline.

### 3. Exact file-target repair after inline feedback — SECONDARY/NEGATIVE GATE

- **Inputs:** inline trigger path, timestamped force-push commit ID, commit-detail filenames.
- **Unit:** 701 inline-trigger PRs with a force-push; 588 pushes join to commit details.
- **Metric:** whether the pushed commit touches the trigger path, against within-PR random-path baseline.
- **Observed profile:** 393/588 (66.8%) touch the trigger path versus a 57.6% random-path mean. Yet in 340 cross/same inline matched pairs, conditional path touch is 56.1% versus 60.0%, with only 14 pairs observed on both sides.
- **Verdict:** useful evidence that feedback can connect to code, but no evidence that cross-product feedback targets the file better than same-product feedback.

### 4. Explicit intentional review routing — REJECT WITH THIS EXPORT

- **Inputs:** `review_requested` timeline events before trigger.
- **Unit:** one last pre-trigger request per PR.
- **Metric:** exact requested product equals triggering reviewer product.
- **Falsification gate:** requested-account coverage.
- **Verdict:** gate fails at 0% target coverage; do not infer intentional cross-product orchestration.

### 5. Sequential learning/repeated product pairs — DEFER

- **Legacy source:** `rq_mining_deeper.py::d3_sequential_learning`.
- **Required redesign:** non-overlapping completed episodes, prior outcome known before the next PR opens, repo/product fixed effects, and open PRs not coded as rejection.
- **Risk:** the old design orders by creation time and shifts final merge status, allowing overlapping PRs and future outcome information.

## Legacy-code reuse verdicts

- **Reuse concept:** `Legacy/AI_Dev_Dataminning/src/rq7_human_ai.py` reviewer identities, loads, and latency. The retained extension adds strict temporal/different-PR history.
- **Reuse utility:** `feature_engineering.py::_detect_file_types`; rebuild `_effort_features` only at pre-trigger time.
- **Reuse diagnostics:** `rq_round2_psm.py::_standardized_mean_difference` and `_balance_table`.
- **Do not reuse matcher unchanged:** its `NearestNeighbors` control can be selected repeatedly although the prose implies 1:1 matching; several size/commit covariates are post-trigger.
- **Do not reuse static multi-agent outcome contrast:** `rq6_multi_agent.py` labels every historical PR using whether the repository ever has two products, creating future leakage.
- **Do not reuse recovery/reversion designs:** required timeline ordering is unavailable because `committed` and `reviewed` timestamps are entirely missing.
- **Do not promote D5 coauthor:** commit-author strings do not cleanly identify person versus service account.

## Reproduction and outputs

Run:

```powershell
.\.venv\Scripts\python.exe scripts\run_legacy_extension_repository_memory.py
```

Main code:

- `scripts/run_legacy_extension_repository_memory.py`
- `scripts/run_human_memory_bridge_analysis.py`
- `scripts/run_review_request_context_analysis.py`

Primary outputs:

- `repository_memory/first_mediator_role_summary.csv`
- `repository_memory/first_decisive_reviewer_role_summary.csv`
- `repository_memory/observable_population_baselines.csv`
- `repository_memory/repo_clustered_history_models.csv`
- `repository_memory/repo_concentration.csv`
- `repository_memory/product_pair_concentration.csv`
- `repository_memory/validation.json`
- `review_request_context/last_requester_role_summary.csv`
- `review_request_context/validation.json`

## Paper-safe wording

> After cross-product feedback, user accounts that join the response often bring recent repository review history. In 3,603 PRs with a first user-account responder within 48 hours, 71.2% had reviewed another PR in the same repository before the trigger. The pattern remains after removing any one repository or product pair. This is consistent with a repository-memory bridge between AI products and project decision processes; it does not identify unaided human work or a causal effect on merge.

Do not say “agents caused humans to intervene,” “cross-agent review improved merge,” or “the reviewer product was explicitly requested.”
