# Directly observed multi-brand mechanisms in AIDev-7.6M

**Status:** read-only audit; AI-assisted screening, not human validation. Counts use the local AIDev-7.6M snapshot in `Legacy/AI_Dev_Dataminning/AIDev-7.6M`. “Brand” below means an observed, conservatively mapped GitHub bot/app identity. It does **not** by itself prove an autonomous agent team or intentional handoff.

## Bottom line

The corrected title/path results do not support a defensible *kth-agent broadens the team's task coverage* claim. A different, narrower paper is possible: study **direct cross-brand AI feedback inside pull requests**, then use issue-linked relays and same-PR commit identities as small validation/mechanism sets.

A PR-level kth-brand dose response is also too sparse. Among 8,621 PRs with a mapped cross-brand submitted review or PR comment, 8,330 have one cross brand, 277 have two, and only 14 have three. Including the primary PR label, these are observed `K=2`, `K=3`, and `K=4` brand-app configurations. Binary `K=1` versus `K>=2` can be studied associationally within an audited coverage frame; a general dose-response beyond `K=2` is not credible.

## Tables, schemas, and joins

| File | Rows | Relevant fields | Join/coverage result |
|---|---:|---|---|
| `pull_request.parquet` | 361,296 | `id`, `agent`, `user`, `created_at`, `closed_at`, `merged_at`, `repo_id` | Primary population; 25,403 repositories; no null/duplicate PR keys found. |
| `pr_timeline.parquet` | 3,018,358 | `pr_id`, `event`, `commit_id`, `created_at`, `actor`, `assignee` | 197,471 PRs (54.66%). `committed` and `reviewed` rows have **zero timestamps**; assignment, force-push, and Copilot lifecycle rows are timestamped. |
| `pr_reviews.parquet` | 281,170 | `pr_id`, `pull_request_review_id`, `user`, `user_type`, `state`, `submitted_at`, `body` | 83,081 PRs (23.00%). Join `pr_id -> pull_request.id`. |
| `pr_comments.parquet` | 373,549 | `pr_id`, `user`, `user_type`, `created_at`, `body` | 110,011 PRs (30.45%). Join `pr_id -> pull_request.id`. |
| `pr_review_comments.parquet` | 289,780 | `pull_request_review_id`, `user`, `user_type`, `created_at`, `in_reply_to_id`, `path`, `commit_id` | Join to `pr_reviews.pull_request_review_id` for PR id; reply edge is `in_reply_to_id -> id`. Inline comments add only one new cross-brand PR beyond submitted reviews/PR comments, but reveal direct reply chains. |
| `related_issue.parquet` | 38,006 | `pr_id`, `issue_id`, `source` | 28,987 PRs (8.02%), 29,111 issues; no orphan keys. Deduplicate `(pr_id, issue_id)` because 1,238 pairs repeat (only 15 exact duplicate rows). |
| `issue.parquet` | 29,111 | issue identity, repository, timing/content fields | Join `related_issue.issue_id -> issue.id`. |
| `pr_commits.parquet` | 718,779 | `sha`, `pr_id`, `author`, `committer`, `message` | 197,335 PRs (54.62%). No commit timestamps; 138 duplicate `(pr_id, sha)` rows require deduplication. |
| `pr_commit_details.parquet` | 6,112,623 | `sha`, `pr_id`, author/committer/message plus per-file diff statistics | File-level expansion, also no commit time. Do not treat rows as distinct commits. |

### Conservative identity map

The exact account-to-primary-label map was:

| GitHub user/app identity | Dataset primary label |
|---|---|
| `claude[bot]` | `Claude_Code` |
| `Copilot`, `copilot-swe-agent[bot]`, `copilot-pull-request-reviewer[bot]` | `Copilot` |
| `cursor[bot]` | `Cursor` |
| `devin-ai-integration[bot]` | `Devin` |
| `google-labs-jules[bot]` | `Google_Jules` |
| `chatgpt-codex-connector[bot]` | `OpenAI_Codex` |

All 14,332 retained cross-brand submitted-review/PR-comment events have `user_type=Bot`. This map is a conservative lower bound, but product roles differ: for example, a pull-request reviewer app is not necessarily the same kind of actor as a coding agent.

## Coverage and denominators

The 8,621 figure includes `pr_reviews` plus PR-level `pr_comments`, after requiring event time >= PR creation, event time <= closure when closed, and participant brand != primary PR label. It **does not include inline review comments**. Adding inline comments yields 8,622 unique PRs because inline comments add just one PR not already represented.

| Primary label | All PRs | PRs with any review or PR comment | Coverage | Cross-brand PRs | Share of all | Share of covered |
|---|---:|---:|---:|---:|---:|---:|
| Claude Code | 172,597 | 7,133 | 4.13% | 1,406 | 0.81% | 19.71% |
| Copilot | 98,384 | 72,358 | 73.55% | 832 | 0.85% | 1.15% |
| Cursor | 12,908 | 11,799 | 91.41% | 806 | 6.24% | 6.83% |
| Devin | 11,219 | 11,196 | 99.79% | 707 | 6.30% | 6.31% |
| Jules | 3,457 | 3,215 | 93.00% | 315 | 9.11% | 9.80% |
| Codex | 62,731 | 27,071 | 43.16% | 4,555 | 7.26% | 16.83% |

Coverage differs too much for raw cross-brand rates across primary labels to be interpreted as behavioral differences. Reviews/comments are also likely product- and repository-selected.

## Direct mechanisms found

### 1. Cross-brand feedback in the same PR

- 14,332 active-window cross-brand events on 8,621 PRs.
- 11,175 submitted-review events on 7,195 PRs; 3,157 PR-comment events on 1,809 PRs.
- Submitted review states: 11,146 `COMMENTED`, 23 `APPROVED`, 4 `DISMISSED`, and 2 `CHANGES_REQUESTED`.
- Therefore this is primarily **feedback participation**, not review authority or approval control.
- Most common unique-PR pairings include Codex-primary/Copilot-participant (3,097), Claude-primary/Copilot-participant (1,010), Codex-primary/Claude-participant (846), Cursor-primary/Copilot-participant (515), and Copilot-primary/Codex-participant (427).

Inline comments contribute 19,307 mapped cross-brand events on 5,278 PRs, but only one additional PR. They are useful for mechanism coding, not prevalence expansion.

### 2. Direct bot-to-bot inline replies

- 274 timestamp-valid cross-brand bot-to-bot reply events on 126 PRs.
- In 269/274 events the reply bot matches the PR's primary brand; only one has the parent matching the primary brand, and four have neither side matching the primary label.
- The signal is highly concentrated: Copilot-parent -> Jules-reply has 154 events/43 PRs, and Codex-parent -> Devin-reply has 77 events/52 PRs.
- This is the clearest directly observed coordination-like mechanism in the snapshot, but it is a small, non-representative mechanism sample.

### 3. Re-review/revision proxies

- 1,267 PRs contain two or more submitted reviews from the same cross-brand bot/app (1,284 brand-PR sequences have strictly later last-review time). This may be a re-review, but repeated automation runs are an alternative explanation.
- 1,131 of the 8,621 cross-feedback PRs have a timestamped `head_ref_force_pushed` event after the first cross-brand review/comment (2,560 events). Only 62 force-push events have an actor in the strict brand map; most actors are human or other bots. This supports “activity followed feedback,” not “the agent implemented feedback.”
- `committed` timeline events cannot establish a response because all 619,218 lack `created_at`. Neither commit table supplies commit time.

### 4. Explicit assignment is too rare and product-specific

- Only 69 cross-brand `assigned` events on 50 PRs survive the strict identity/time filter.
- Every cross-brand assignee is Copilot: 60 events/41 Claude PRs, 1 Cursor PR, and 8 Codex PRs.
- In 60 events the assigning actor also maps to Copilot; nine actors are unmapped. This likely reflects a Copilot workflow convention, not general team assignment.
- `copilot_work_started` on non-Copilot-primary PRs is not safe evidence of delegation: it is often nearly simultaneous with PR creation, has weak finish pairing, and some events occur after close/merge. It needs manual API-page validation before use.

### 5. Same-issue relays are stronger task links but small

- After pair deduplication, 109 issues are linked to PRs from two distinct primary brands; none have more than two and none are cross-repository.
- These cover 276 unique PRs and 404 issue-PR links.
- Dominant brand pairs by issue: Copilot-Codex 52, Claude-Codex 26, Claude-Copilot 10, Devin-Codex 8; every other pair has four or fewer.
- A strict temporal relay definition (prior different-brand PR closed before current PR opened) yields 185 relay rows across 75 issues; only 12 share the same contributor login.
- 161 relays follow a merged prior PR and 24 follow a closed-unmerged prior PR. This is a useful task-continuity validation/case set, not a powered general outcome study.

### 6. Same-PR commit identities are direct but weakly attributable

- A narrow author/committer alias map finds 351 PRs with commit identities from a brand other than the primary label; six contain two cross brands.
- A timestamp-free timeline-actor version yields 260 PRs.
- Commit author/committer strings are not verified GitHub actor identities and can reflect aliases, co-authorship, cherry-picks, or preserved metadata. Codex has no robust commit identity in this snapshot. Use only after manual validation and deduplication.

## Three candidate RQs

1. **Where does cross-brand AI feedback occur in pull requests?** Map observed brand-app participation, interaction topology, review state, and repository context, always reporting table coverage and the conservative identity boundary. Contribution: a direct event-based map rather than title/path co-occurrence.

2. **What observable action follows cross-brand AI feedback?** Use timestamped force-push, repeated submitted review, and inline reply chains. The strongest mechanism endpoint is a direct primary-brand bot reply to a cross-brand bot. Compare only within tables/products with adequate support and treat results as temporal associations, not causal effects.

3. **Does cross-brand work occur as in-PR feedback or as a same-issue relay?** Contrast the 8,622 same-PR interaction set with the 109 two-brand linked issues/75 temporally ordered issue sets. This gives a simple coordination-mode story: concurrent feedback versus sequential task continuation.

## Must-fix validity points before paper claims

1. Call the unit **brand-app participation**, not “multi-agent team,” until actor roles are manually validated.
2. Do not report raw primary-agent comparisons without coverage restriction/modeling; Claude review/comment coverage is 4.13% while Devin is 99.79%.
3. Do not infer revisions from `committed`/`reviewed` timeline events; they have no timestamps.
4. Do not infer that a force-push was performed by the agent or caused by feedback; actor mapping and causal linkage are weak.
5. Manually validate a stratified sample of identity mappings and event semantics, especially Copilot assignments/lifecycle, Codex connector reviews, and the two concentrated bot-reply pairs.
6. Deduplicate relation and commit keys before counts; avoid per-file `pr_commit_details` inflation.
7. Model left/right censoring and observation opportunity: later feedback needs time before closure, and open PRs have longer exposure.
8. Avoid kth-brand dose-response claims above `K=2`; `K=3` has only 277 PRs and `K=4` only 14.

## Recommended robustness tests

- Recompute using each account separately rather than pooled brand labels; show whether results are dominated by reviewer-only apps.
- Restrict to repositories and calendar windows where both focal brand accounts are observably active; include repository and time fixed effects for any association.
- Match/weight on repository, primary label, calendar month, PR size, pre-feedback age, and closure opportunity; never use post-treatment variables.
- For “response after feedback,” use landmark windows (for example 24/72 hours), exclude feedback after close, and require sufficient follow-up.
- Hand-code at least 100 cross-brand threads, oversampling the 126 bot-to-bot reply PRs and rare approval/change-request states, for genuine task feedback, boilerplate, repeated automation, and actor role.
- Run negative controls: same-brand automated review and randomly shifted feedback times within repository/month.

