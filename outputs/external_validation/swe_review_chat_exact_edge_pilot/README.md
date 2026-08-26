# SWE-Review-Chat exact-edge external-validation pilot

## Disposition: REJECT

The frozen source screen found 18 parent
threads across 7 PRs where an exact-alias product
author received an inline review comment from another mapped product and that
parent contained a nested reply. All 7
candidate PR keys occur in the complete AIDev 7.6M backbone. The corpus-disjoint
set is therefore **zero PRs**, with zero eligible REST hydration targets and zero
48-hour landmark rows.

This is a fail-closed support result. It rules out SWE-Review-Chat as an
independent exact-edge RQ3 replication under the frozen AIDev alias and PR-key
rules. It does not refute the AIDev association, estimate an effect, or say
anything about semantic resolution, review quality, or causality.

## Audit trail

- Dataset revision: `408cf94c068080eda66e0f3d7e9aa0316a42cb63`
- AIDev revision: `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`
- Exact mapped-author PRs screened: 5,250
- PRs with any cross-product inline parent: 38
- Nested-reply candidate PRs before overlap exclusion: 7
- Non-AIDev candidate PRs: 0
- Landmark-eligible PRs: 0
- Decision: `REJECT_REPLICATION_ZERO_DISJOINT_SUPPORT`

Tracked aggregate evidence is in
`protocol/swe_review_chat_exact_edge_pilot_20260826.json` and
`protocol/swe_review_chat_exact_edge_funnel_20260826.csv`. Candidate IDs are
kept only in the gitignored `external_data/cache/swe_review_chat_exact_edge_pilot/`
audit directory. No body, title, diff, or manuscript file is exported or edited.
