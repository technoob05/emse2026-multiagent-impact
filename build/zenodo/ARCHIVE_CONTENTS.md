# What is in this archive, and what is not

This is the reproducible analysis artifact for the paper *Participation Is Not
Collaboration: When One LLM Coding Agent Reviews Another on GitHub, a
Person Answers*.
It was assembled by `scripts/release/build_zenodo_archive.py`, which also
verified the exclusions below against the built zip.

## Included

| Path | What it is |
|---|---|
| `src/` | Shared analysis library |
| `scripts/` | Analysis, figure, reporting, validation, and release code |
| `tests/` | The pytest suite |
| `protocol/` | Reproduction contract: experiment disposition ledger, label schemas, acquisition manifests |
| `docs/` | The reproduction guides and protocols, and the validation and data-provenance audits. Internal design notes and venue decisions are not deposited. |
| `outputs/` | The derived analysis products the manuscript tables and figures are built from |
| `REPRODUCE.md` | Standalone instructions: get the data, install, run, and read the outputs |
| `README.md` | Study summary, headline findings, and run order |
| `CITATION.cff`, `LICENSE`, `NOTICE.md`, `.zenodo.json` | Citation and licence metadata |
| `pyproject.toml`, `uv.lock` | Pinned Python environment |
| `MANIFEST.csv`, `SHA256SUMS` | Integrity record for every file above |

## The source data is not included

The study reads the AIDev release. It is third-party data under its own terms
and has its own home; this archive does not redistribute it.

- Dataset: `hao-li/AIDev-7.6M`
- Pinned revision: `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`
- Fetch: <https://huggingface.co/datasets/hao-li/AIDev-7.6M/tree/37bbe1533e26cc1e1374917dba1186d1c8a4dc81>

Point the analysis at your copy with the `AIDEV_DATA_DIR` environment variable,
or place it at the default path documented in `README.md`.

## Excluded, and checked

The build read these rules out of the `NEVER PUBLISH` block of `.gitignore` and
verified that no file in the zip matches any of them. 38 file(s)
present in the working tree matched and were withheld.

- `outputs/**/private/`
- `outputs/**/private_record_key.csv`
- `outputs/**/private_sampling_key.csv`
- `outputs/**/audit_key_do_not_share_before_coding.csv`
- `outputs/**/*_answer_key.csv`
- `docs/audits/AUTHOR_METADATA_AUDIT_*.md`
- `outputs/_exploration/`
- `SUBMIT/`

These paths hold the private coder keys and answer keys for the blinded
human-coding audits, the author-metadata audit, ad-hoc exploration scratch, and
the submission-portal staging folder. Regenerable caches
(`outputs/cache/`), ad-hoc script scratch (`scripts/_exploration/`), and the
superseded prior study (`outputs/_superseded/`, `scripts/_superseded/`) are also
left out; none of it feeds this paper.

## Licence scope

See `NOTICE.md`. The MIT licence in `LICENSE` covers the code, the build
scripts, and the derived analysis products. It does not cover the AIDev release,
the other third-party datasets recorded in `docs/audits/`, or the manuscript.
