# External semantic artifact audit (2026-08-26)

## Decision

The downloaded sources are useful for **semantic triangulation only**. Neither
source reproduces the paper's exact addressed public edge, and neither supports
an external causal or outcome replication.

| Source | Safe use | Blocked use |
|---|---|---|
| SWE-PRBench | Codebook examples of substantive, initiating human feedback on real merged PRs | Exact reply topology, cross-product coordination, merge comparison, or direct comment-ID validation |
| AIReviewActionAnalysis | Annotation rubric and exploratory falsification for actionable comments and code-change addressing | Exact public reply/parent edge, direct transfer of labels to AIDev, causal impact, or fully traceable Stage-2 replication |

The deterministic aggregate audit is
`protocol/external_semantic_artifact_audit_20260826.json`. It contains no raw
comment text.

## Provenance and integrity

### SWE-PRBench

- Canonical source: `foundry-ai/swe-prbench` on Hugging Face.
- Pinned revision: `b87f5797aef3ed2c3153bb1304ea4d801d36ba6e`.
- Declared data license: CC BY 4.0.
- Local non-cache tree: 1,407 files, 41,381,855 bytes.
- Deterministic tree SHA-256:
  `0eb8e0acba0d54d8704ea80b477b510d923e563fae4fc94997d820a6718feac4`.
- All three context sets have 350 unique tasks and declare pipeline `v0.4.1`.

### AIReviewActionAnalysis

- Canonical record: Zenodo DOI `10.5281/zenodo.19562450`, published
  2026-04-14.
- Zenodo record metadata declares CC BY 4.0. The ZIP itself contains no
  embedded license file, so a redistributed package must retain the DOI,
  attribution, and record-level license evidence.
- Local ZIP: 44,349,100 bytes; 1,086 files; 269,194,546 uncompressed bytes.
- MD5 `93cabf0873330f4d75d570d5bf5f31b0` exactly matches the Zenodo record.
- SHA-256:
  `31485800a45b405af4c9e31dedd8d32b24ea06adc4bcd552ef5bc62b32387ccb`.
- Full ZIP CRC validation passed.

## SWE-PRBench: actual grain and label origin

The local release contains 350 unique PRs from 65 repositories, 350 annotation
files, and 1,674 selected comments. Every selected comment is marked as an
initiating, non-reply comment. This is valuable for defining substantive
feedback, but it removes the response relation needed for the present paper.

The label origin must be described carefully:

- Comment bodies and reviewer names are public comments written by human
  engineers during real GitHub review.
- Initiating/reply status is a topology-derived field.
- `is_in_diff` and PR difficulty are automatically derived from comment/file
  location according to the dataset card.
- RVS, filtering, AI-comment removal, and the final benchmark inclusion are
  construction-pipeline outputs. The downloaded artifact does not expose an
  annotator/adjudication ledger for those fields.
- Model detection labels such as CONFIRMED, PLAUSIBLE, and FABRICATED are
  LLM-judge outputs produced by the evaluation harness, not human labels in the
  downloaded ground-truth files.

Therefore, “human-written ground-truth comments” is supported; “all released
labels were independently human-coded” is not.

### Identifier and topology limits

- Annotation IDs are local strings such as `c_1`. Across 1,674 rows, only 28
  distinct values exist; the valid key is `(task_id, comment_id)`.
- Annotation comments have no public GitHub comment ID, event time, reply
  parent, or review-batch ID.
- The embedded unfiltered discussion list has 3,093 comments and 1,367
  `replyTo.id` values, but it omits each comment's own ID and timestamp. Parent
  IDs therefore cannot be resolved into a local temporal event graph.
- Exactly 3 of 350 SWE PR URLs overlap the rich AIDev PR table and 4 overlap
  AIDev's all-PR table. This is PR overlap, not comment-label overlap.

### Internal consistency warning

The per-PR `num_substantive_comments` summary should not be used as the semantic
label count:

- it matches the annotation file for only 85 of 350 PRs;
- the PR summaries total 2,240, while annotation files contain 1,674 selected
  comments; and
- 386 of the 1,674 selected bodies have fewer than ten whitespace-delimited
  tokens despite the dataset card's stated “at least 10 words” rule.

Whitespace tokenization may differ from the unpublished construction method,
so the last result is a reproducibility discrepancy, not proof that the
comments are invalid. For any semantic audit, use annotation files as the
released ground truth and disclose the mismatch.

## AIReviewActionAnalysis: actual grain and label origin

The headline 5,652 rows are not 5,652 independent public comments:

- 4,879 rows map one-to-one to GitHub inline review-comment IDs;
- 773 file-level rows come from only 367 GitHub issue comments, using synthetic
  suffixes such as `-1`, `-2`, and `-3`; and
- the correct underlying public-event count is therefore 5,246.

This mixed grain matters for confidence intervals, train/test splitting, and
any claim about independent comments. At minimum, rows must be grouped by the
underlying public event and PR.

The source field also does not identify annotation method. For example,
`Source=Human` means the original review was human-written; it does not mean
the full-corpus actionability or resolution label was human-coded.

### Human versus LLM-derived labels

- The archive contains 150 final manual labels: 50 human-review, 50 file-level
  AI-review, and 50 patch-level AI-review cases.
- The three workbooks contain two annotator columns. There were 25 initial
  label disagreements across the 150 cases before resolution.
- Full-corpus Stage 1 labels are model-derived. The released formatted file is
  named for `openai-gpt-4.1` and contains all 5,652 rows.
- Full-corpus Stage 2 addressing labels are model-derived. They classify code
  changes as fully, partly, not, or not-enough-information addressed.
- The final factor-model label collapses Stage-2 LLM results and trains on that
  model-derived target. It is not an observed causal response.

### Release-lineage warning

The Stage-2 formatted filename states that it is based on
`Suggestion_openai-o3-mini_p=3.12(1)(f).csv`, but that full-corpus Stage-1 file
is absent. The released full-corpus Stage-1 formatted file is GPT-4.1 instead.
Until the authors clarify this mismatch or release the missing input, Stage-2
results are not fully traceable from the archive and should not be used as a
reproduction claim.

### No direct AIDev label join

Stable numeric ID comparison found:

- zero overlap between 4,879 AIReviewAction inline-comment IDs and 289,780
  AIDev review-comment IDs; and
- zero overlap between 367 base issue-comment IDs and 373,549 AIDev PR-comment
  IDs.

Consequently, the external labels cannot directly validate any AIDev edge.
Fuzzy text matching would weaken identity and is not an acceptable substitute.

Most importantly, this source defines “addressed” as an inferred subsequent
code modification. The paper's exact public edge requires a response whose
public parent ID equals the trigger event ID. These are related but distinct
constructs.

## Paper-safe interpretation

Supported wording:

> External artifacts were used to challenge the semantic boundary of
> substantive and actionable feedback. They were not pooled with AIDev and do
> not replicate the exact public reply topology or its later outcomes.

Do not claim that either source confirms the paper's multi-agent effect,
validates causality, or provides independent exact-edge replication. A future
semantic validation may apply the released rubrics to a preregistered,
double-coded sample of AIDev triggers and responses. That would create new
human-coded evidence; the downloaded labels alone do not do so.

## Reproduction

Run the aggregate-only profiler from the project root:

```powershell
uv run python scripts/audit/profile_external_semantic_artifacts.py
```

The profiler verifies artifact hashes, source grain, label-file reconciliation,
and exact stable-ID overlap with AIDev. It does not export bodies or make a
network request.
