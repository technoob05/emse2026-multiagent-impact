# Clean source-bundle and portal-staging smoke test (2026-08-26)

## Verdict

**PASS for technical packaging, clean-room compilation, PDF structure, and
rendered output.**

The archival source ZIP and the portal-facing manuscript source ZIP both build
from fresh extractions without any project-relative input. The staged
`manuscript.pdf` and `ESM_1.pdf` are checksum-valid, structurally safe, and
visually identical to the corresponding clean-room builds. The manifest,
duplicate-anchor, and build-convergence defects found in the initial audit have
all been corrected.

This technical pass is not an authorization to upload the current draft.
Author metadata, declarations, and the public artifact DOI still contain
`Pending` placeholders and require authoritative human input.

## Audited artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `build/submission/emse_multiagent_coordination_draft_source.zip` | 193,601 | `64C101A94997B65926E40839EF48674ECAF8FF2E0BE1B1CD14ADC1BCD3BB294B` |
| `build/submission/emse_portal_staging/manuscript_source.zip` | 117,515 | `253C233B8BE4D45964038F0155538D7FBEEA37A097AA8CDF523FD15D41027428` |
| `build/submission/emse_portal_staging/manuscript.pdf` | 356,671 | `4CA415EAEACBA3EBAE016E387E9EA16D94906F6AEAC1EEEBBAF3DD0744F53D92` |
| `build/submission/emse_portal_staging/ESM_1.pdf` | 364,164 | `D5FDBB5B10F6DD4BF00AD7197553627438EEE060D5B9B7747E4DD91960B52A4C` |

The staging `CHECKSUMS.sha256` has three well-formed records and verifies
`manuscript_source.zip`, `manuscript.pdf`, and `ESM_1.pdf` with no missing,
extra, or mismatched file.

## Archive integrity and scope

### Archival source ZIP

- Exactly 13 flat allowlisted entries.
- Zero duplicate, nested, absolute, or traversal paths.
- `PACKAGE_MANIFEST.sha256` has exactly 12 records: one for every payload
  member other than the manifest itself.
- All 12 records parse and match; there are no absent, extra, or unhashed
  payload members.
- Includes both LaTeX documents, the generated appendix tables, bibliography
  files, vendor class/style, and all five figures.

### Portal manuscript source ZIP

- Exactly seven flat allowlisted entries:
  `main.tex`, `references.bib`, `sn-jnl.cls`, `sn-basic.bst`, and
  `Fig1.pdf`-`Fig3.pdf`.
- Zero duplicate, nested, absolute, or traversal paths.
- All seven members are byte-identical to their counterparts in the archival
  source ZIP.
- No appendix source, supplementary figures, raw dataset, auxiliary build file,
  log, or machine-local artifact is included.

Scans of both extracted trees found no absolute/private path such as
`D:\PhD...`, `C:\Users...`, `PhD_LetGoo`, `.codex`, a smoke-test path,
or `file://`. The archival README retains two explanatory project-level
pointers, but neither is a compile dependency.

## Clean-room builds and dependency isolation

Environment: MiKTeX pdfTeX 1.40.29 / MiKTeX 26.2, BibTeX 0.99e, Poppler
24.04.0, Python 3.14, and pypdf 6.12.2.

Three independent builds were run with shell escape disabled:

1. `main.tex` from a fresh extraction of the archival ZIP.
2. `technical_appendix.tex` from the same fresh archival extraction.
3. `main.tex` from a separate fresh extraction of the portal source ZIP.

Each used the documented convergent sequence: pdfLaTeX, BibTeX, and three
post-BibTeX pdfLaTeX passes. Recorder files show zero input from elsewhere in
the project. The only non-system inputs were the extracted source files and the
locally generated auxiliary/bibliography files. The portal and archival
manuscript builds produced byte-identical clean-room PDFs.

The README now documents the extra convergence pass. The project build function
also runs that pass and its strict log gate explicitly rejects both
`destination with the same identifier` and `duplicate ignored`.

## Final log audit

| Check | Archival main | Archival appendix | Portal main |
|---|---:|---:|---:|
| LaTeX/fatal/emergency errors | 0 | 0 | 0 |
| Overfull boxes | 0 | 0 | 0 |
| Undefined citations/references | 0 | 0 | 0 |
| Rerun/cross-reference requests | 0 | 0 | 0 |
| Duplicate PDF destinations | 0 | 0 | 0 |
| Underfull hboxes | 1 | 1 | 1 |
| Underfull vboxes | 11 | 19 | 11 |
| Final pages | 11 | 19 | 11 |

The underfull-box messages are benign in the page-complete visual audit. There
is no clipping, overlap, missing content, or unreadable line at those locations.

The prior 14 appendix duplicate destinations are gone. Named destinations remain
complete and resolve to their visual pages: manuscript Figures 1-3, appendix
Figures 1-2, and appendix Tables 1-17 were all present and page-mapped.

## PDF structure, privacy, and fonts

| Check | Staged manuscript | Staged ESM |
|---|---:|---:|
| Pages | 11 | 19 |
| Page geometry | A4, no rotation | A4, no rotation |
| Encrypted | No | No |
| Fonts | 23, all embedded | 22, all embedded |
| Type 3 fonts | 0 | 0 |
| Annotations | 81 links | 52 links |
| Link actions | 51 GoTo, 30 HTTPS URI | 41 GoTo, 11 HTTPS URI |
| URI hosts | `arxiv.org`, `doi.org` | `arxiv.org`, `doi.org` |
| Attachments / embedded files | 0 | 0 |
| JavaScript / forms / collections | 0 | 0 |

The catalog `OpenAction` in each PDF is only an internal `GoTo` to the first
page. There are no launch, remote-GoTo, file-specification, or other unsafe
actions. Raw-byte, extracted-text, and metadata scans found no private/local path
leakage. Metadata contains only the pdfTeX producer, empty bibliographic fields,
and build timestamps.

The main and appendix PDF copies in `build/pdf/`, the archival delivery
copies, and the portal-staging copies have matching SHA-256 values within each
document type.

## Visual equivalence and page-complete review

All clean-room and staged PDFs were rendered with Poppler at 100 dpi:

- Archival main versus staged manuscript: **11/11 pixel-identical pages**.
- Portal-source main versus staged manuscript: **11/11 pixel-identical pages**.
- Archival appendix versus staged `ESM_1.pdf`: **19/19 pixel-identical pages**.

Contact-sheet inspection covered all 30 staged pages. It found no clipped text,
overlap, broken glyph, missing figure, table overflow, misplaced float, or
unreadable caption. Figure/table order and section transitions are coherent.

## Remaining human-only submission gates

Before portal upload, replace or confirm:

- author name parsing, affiliation, institution, city, and country;
- corresponding email and ORCIDs;
- CRediT author contributions;
- funding and competing-interests statements;
- ethics/consent wording and acknowledgements;
- public artifact URL/DOI;
- the not-under-review and cover-letter confirmations.

These fields cannot be inferred safely from the technical bundle and do not
invalidate the clean-room packaging pass above.
