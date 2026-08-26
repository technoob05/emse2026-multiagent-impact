# SWE-Review-Chat exact-edge eligibility and hydration pilot

Generated: `2026-08-26T07:22:33.725353+00:00`.

## Decision: REJECT_REPLICATION_ZERO_DISJOINT_SUPPORT

This audit measures whether a corpus-disjoint, exact-parent landmark is technically supported. It does not estimate an effect, semantic resolution, review quality, or causality, and it is not manuscript evidence.

## Frozen eligibility rule

At PR grain, require an exact-alias product-authored root PR (product A), an inline `review_comment` parent from a different mapped product B, and one or more nested source replies. Exclude every PR key found in the complete AIDev 7.6M backbone. For landmark compatibility, the candidate parent must also be the PR's first cross-product inline trigger, the PR must remain open at trigger + 48 hours, and the full trigger + 30-day horizon must be observed.

Child categories are relative to parent product B: an unmapped `User`, the same exact mapped product, a different exact mapped product, or another unmapped identity. No fuzzy product inference is used.

## Source funnel

- Full PR rows scanned: 1,082,529 across 293 shards.
- Exact-alias mapped-author PRs: 5,250.
- PRs with any cross-product inline parent: 38.
- Parent threads satisfying the nested-reply rule: 18 across 7 PRs.
- Candidate PRs overlapping AIDev full: 7; retained non-AIDev PRs: 0.
- Non-AIDev PRs where the nested parent is also the first cross-product inline trigger: 0.
- Child categories before AIDev exclusion: `{"same_as_parent_product": 1, "user_unmapped_product": 18}`.
- Child categories after AIDev exclusion: `{}`.

## Authenticated read-only hydration

- GitHub REST API version: `2026-03-10`; filtered requests return no bodies.
- Unique requests: 0; HTTP status counts: `{}`.
- Because the exact non-AIDev candidate set is empty, zero parent/comment/PR records were eligible for REST hydration. This is a fail-closed stop, not an API coverage failure.
- Fully validated parents: 0/0.
- Exact-parent child IDs: 0/0; fully valid exact child edges: 0.
- Landmark-eligible PRs: 0; exact reply by 48h: 0; later merge by day 30: 0.

Failed replication gates: `landmark_risk_set_below_50_prs, exact_exposed_support_below_20_prs, fewer_than_two_ordered_product_pairs`.

The source filter already requires a nested reply, so this pilot cannot provide an unselected no-reply comparison group. Tiny support or complete coverage therefore remains a support/falsification result, not a replication.

## Integrity and privacy boundary

- Raw candidate and hydrated ledgers are local and gitignored under `external_data/cache/swe_review_chat_exact_edge_pilot`.
- Tracked artifacts contain aggregate counts only; no repository, PR, comment, title, body, diff, or raw API response text is exported.
- Each review-comment API result is whitelisted to IDs, timestamps, review batch, parent ID, actor login/type, and PR URL before local persistence.
- Parent validity requires an HTTP 200, matching ID, top-level parent, exact actor/product, timestamp agreement, and review-batch agreement.
- Child validity requires an HTTP 200, matching ID, exact `in_reply_to_id`, actor/category agreement, and creation strictly after the parent.

Official endpoint documentation: [review comments](https://docs.github.com/en/rest/pulls/comments) and [pull requests](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request).

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\analysis\run_swe_review_chat_exact_edge_pilot.py
```

A working authenticated `gh` session is required. The script performs GET requests only and fails closed on missing or inconsistent fields.
