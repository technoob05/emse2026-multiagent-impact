# Literature evidence package

This directory freezes the 2026-08-25 bounded novelty update.

- `PROTOCOL.md`: scope, eligibility, novelty test, and claim boundaries.
- `search_log.csv`: exact search strings and routes.
- `evidence_map.csv`: closest work, overlap risk, and residual novelty.

The search is suitable for paper framing and a reproducible novelty audit. It
does not support describing the review itself as exhaustive or systematic.

## Status of `evidence_map.csv`

`evidence_map.csv` was built for the pre-pivot study and its `residual_novelty`
column still describes that earlier design. It is retained as a search record.
The novelty position of the submitted manuscript is in
`../docs/decisions/NOVELTY_POSITION_20260826.md`, and the works actually cited are in
`../paper/manuscript/references.bib`.
