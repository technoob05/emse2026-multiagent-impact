# External-data provenance and release boundary

The machine-readable acquisition record is
`protocol/external_acquisition_manifest_20260826.csv`. It covers every external
dataset directory and source-repository clone present locally on 2026-08-26.
The analytical verdict is source-specific: a successful download is not, by
itself, evidence that the source can answer the paper's research questions.

## Integrity convention

- Zenodo files were checked against the MD5 values published on their exact
  record pages.
- The complete SWE-Review-Chat copy is checked file by file in
  `protocol/swe_review_chat_file_manifest_20260826.csv`: all 295 repository
  files match remote byte sizes and all 293 LFS objects match SHA256.
- For the smaller Hugging Face copies, the local cache metadata identifies the
  pinned revision for each downloaded file. The CSV also records a deterministic
  payload-tree digest. To form it, omit `.cache/`, sort files by forward-slash
  relative path, emit `sha256  bytes  relative_path\n` for each file, concatenate
  those UTF-8 records, and hash the result with SHA256.
- Clean Git clones record both the commit and root-tree object. The interrupted
  DevGPT LFS clone explicitly fails the integrity gate and must not be analyzed.
- `payload_*` excludes Hugging Face `.cache/` or Git `.git/`; `total_local_*`
  reports the full local footprint, including that acquisition metadata.

## Raw-release exclusion

Every manifest row has the same release rule:
`EXCLUDE_LOCAL_COPY_FROM_VCS_AND_SUBMISSION_ARCHIVE`. Third-party raw data,
archives, cache files, and cloned repositories are local evidence only. The
public artifact may contain project-owned code, protocol records, and safe
derived aggregates, but not these local copies.

This boundary is enforced twice:

1. `.gitignore` excludes `external_data/downloads/`,
   `external_data/source_repositories/`, and `external_data/cache/`.
2. `scripts/package_submission.ps1` builds the source archive from a fixed
   allowlist of manuscript files. It never recurses through the project tree.

Audit on 2026-08-26 confirmed that the existing `*source.zip` archives contain
no path named `external_data`, `downloads`, `source_repositories`, or `DevGPT`.
The current coordination source archive has 13 entries: 12 explicitly
allowlisted manuscript/figure files plus `PACKAGE_MANIFEST.sha256`.

## Release-safe interpretation

Only provenance and aggregate findings are tracked. SWE-Review-Chat failed the
independent exact-edge replication gate: all seven exact candidates overlap
AIDev, so zero disjoint landmark rows remain for REST hydration.
CodAGE/AI-to-AI artifacts support attribution and
novelty checks, not independent replication. SWE-PRBench supports semantic
construct checks. The other acquired sources fail the present observation-grain,
topology, completeness, or licensing gate and must stay outside headline claims.
