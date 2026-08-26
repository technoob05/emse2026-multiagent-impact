# SWE-Review-Chat pinned-data provenance and quality profile

Generated: `2026-08-26T07:07:07.557267+00:00`.

This is a data-capability and overlap audit. It does **not** report an effect, quality difference, causal estimate, or manuscript claim.

## Acquisition decision

- Dataset: [Suzhen/SWE-Review-Chat](https://huggingface.co/datasets/Suzhen/SWE-Review-Chat)
- Pinned revision: `408cf94c068080eda66e0f3d7e9aa0316a42cb63`
- Original Parquet payload: 1,829,741,160 bytes (1.704 GiB)
- Viewer-converted Parquet payload: 1,829,741,160 bytes (1.704 GiB)
- Complete pinned repository payload: 1,829,746,197 bytes (1.704 GiB)
- Free space before download: 17,788,321,792 bytes (16.567 GiB)
- Projected free space after download: 15,958,575,595 bytes (14.863 GiB)
- Free space observed immediately after download: 15,925,833,728 bytes (14.832 GiB)
- Gate result: **DOWNLOAD_FULL**. The complete pinned revision was used; no sampling fallback was needed.
- Download tool: `huggingface_hub hf CLI` version `1.17.0`.

At profiling time, the dataset's default Hub SHA equaled the pinned SHA. The Dataset Viewer endpoint is branch-based, so this equality is recorded rather than treating its converted branch as independently revision-addressable.

## File and row integrity

- 295 expected files and 295 local files (excluding the Hub cache).
- Local Parquet bytes: 1,829,741,160; all remote/local byte sizes match: `True`.
- LFS SHA-256 objects checked: 293; all checked hashes match: `True`.
- Parquet shards: 293; schemas identical: `True`.
- Metadata rows / streamed rows: 1,082,529 / 1,082,529.
- Unique repositories: 207; unique `(repo_full_name, pr_number)` keys: 1,082,389.
- Duplicate-key surplus rows: 140; invalid join-key rows: 0.
- Root PR creation coverage: `2015-07-14T14:56:12Z` through `2026-01-28T19:50:18Z`.

The machine-readable profile includes null counts and rates for all 16 root fields, all 12 conversation-entry fields, and all four nested-reply fields.

## Thread structure and temporal limits

- Conversation entries: 10,023,458; parents with one or more nested replies: 793,106.
- Nested replies: 1,273,825; maximum replies under one parent: 66.
- Conversation-entry timestamps cover `2015-07-14T14:56:12Z` through `2026-01-30T12:57:17Z`.
- A reply is structurally contained under one parent entry, but the reply struct does not contain `timestamp`, `in_reply_to_id`, or `parent_comment_id`.
- Therefore, the local files support nested thread membership but cannot by themselves enforce a reply-time window or independently re-check the parent ID. Any time-sensitive exact-edge replication would require API hydration or another timestamped source.

## Product-attribution support

Product attribution is deliberately narrow. Only exact account aliases already used in the AIDev analysis are mapped; all other identities remain unmapped.

Aliases: `chatgpt-codex-connector[bot]` -> `OpenAI_Codex`, `claude[bot]` -> `Claude_Code`, `copilot` -> `Copilot`, `copilot-pull-request-reviewer[bot]` -> `Copilot`, `copilot-swe-agent[bot]` -> `Copilot`, `cursor[bot]` -> `Cursor`, `devin-ai-integration[bot]` -> `Devin`, `google-labs-jules[bot]` -> `Google_Jules`.

- PRs with a mapped root author: 5,250.
- PRs with a mapped conversation actor: 84,744.
- PRs with a mapped nested-reply actor: 1,507.
- PRs with an exact-alias cross-product author/actor configuration: 88.
- PRs containing an exact-alias cross-product nested thread: 4.
- Mapped nested reply pairs: 6 cross-product and 353 same-product. These are support counts, not performance outcomes.

The field name `reviewer` is used for every conversation actor, including entry types that are not necessarily review verdicts. The profile therefore also keeps counts by entry type; analysis must choose eligible types before interpretation.

## Exact AIDev PR-key overlap

The join key is normalized lower-case GitHub `owner/repository` plus positive PR number. No title, author name, text, or fuzzy match is used.

- AIDev rich backbone: 8,127 unique SWE-Review-Chat PR keys overlap (0.75%).
- AIDev full 7.6M backbone: 8,199 unique SWE-Review-Chat PR keys overlap (0.76%).
- Cross-product nested-thread PRs outside the full AIDev backbone: 4.

The non-overlap subset is the only candidate here for a corpus-disjoint external replication. Overlapping rows can be used for schema/attribution cross-checks, but they are not independent extra evidence.

**Data-use decision:** retain the full pinned corpus for compatibility checks and possible API-hydrated follow-up work. As shipped, it is not a ready exact-edge timing replication: only four non-AIDev PRs contain an exact-alias cross-product nested thread, and the nested replies have no timestamps. Do not present those four PRs as external validation.

## Quality gates

| Check | Status | Value |
|---|---:|---:|
| pinned_revision_resolves_exactly | PASS | `408cf94c068080eda66e0f3d7e9aa0316a42cb63` |
| viewer_default_sha_equals_pinned_revision_at_profile_time | PASS | `408cf94c068080eda66e0f3d7e9aa0316a42cb63` |
| full_download_size_and_free_space_gate | PASS | `True` |
| local_file_set_matches_pinned_tree | PASS | `True` |
| local_byte_sizes_match_pinned_tree | PASS | `True` |
| checked_lfs_sha256_values_match | PASS | `True` |
| all_parquet_shard_schemas_identical | PASS | `True` |
| metadata_stream_and_viewer_row_counts_reconcile | PASS | `1082529/1082529/1082529` |
| pr_join_keys_complete | PASS | `0` |
| pr_join_keys_unique | LIMITATION | `140` |
| nested_reply_timestamp_available | LIMITATION | `False` |
| nested_reply_explicit_parent_id_available | LIMITATION | `False` |

## Reproduction

From the project root, after downloading the pinned revision:

```powershell
.\.venv\Scripts\python.exe scripts\audit\profile_swe_review_chat.py `
  --revision 408cf94c068080eda66e0f3d7e9aa0316a42cb63 `
  --disk-free-before-bytes <observed-before> `
  --disk-free-after-download-bytes <observed-after>
```

Raw files remain under the gitignored `external_data/downloads/` directory. The tracked manifest records byte sizes and SHA-256 verification without copying raw rows or text into the repository.
