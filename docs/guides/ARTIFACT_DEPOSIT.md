# Depositing the artifact on Zenodo

Ordered checklist for the person doing the deposit. Everything here is manual on
purpose: the archive is built by script, but no script may invent an identifier.

## 0. Fill in the placeholders first

Nothing is deposited until these are real values. Do not guess any of them; an
invented ORCID or affiliation in a citation record silently mis-attributes the
work, which is worse than leaving the field out.

| Placeholder | Files | What to put there |
|---|---|---|
| `ORCID-PENDING` | `CITATION.cff`, `.zenodo.json` | Each author's ORCID iD. In `CITATION.cff` use the full URL form `https://orcid.org/0000-...`; in `.zenodo.json` use the bare `0000-...` form. If an author has no ORCID, delete their `orcid` line rather than filling it. |
| `AFFILIATION-PENDING` | `CITATION.cff`, `.zenodo.json` | The institution, worded exactly as on the manuscript title page. |
| `EMAIL-PENDING` | `CITATION.cff` | The corresponding author's email. Only the corresponding author carries one. |
| `VERSION-PENDING` | `CITATION.cff`, `.zenodo.json` | The release tag, e.g. `v1.0.0`. |
| `DATE-RELEASED-PENDING` | `CITATION.cff` | The deposit date, `YYYY-MM-DD`. |
| `DOI-PENDING` | `CITATION.cff` | The reserved DOI from step 2. |

The same values are still outstanding on the manuscript title page
(`Affiliation pending`, `Corresponding email pending`); see
`paper/SUBMISSION_METADATA_FORM.md`. Fill both in one sitting so they agree.

## 1. Build and check the archive

```powershell
.\.venv\Scripts\python.exe scripts\release\build_zenodo_archive.py --self-test
.\.venv\Scripts\python.exe scripts\release\build_zenodo_archive.py
```

The self-test proves the exclusion guard still refuses every path in the
`NEVER PUBLISH` block of `.gitignore`. The build then writes
`build/zenodo/` with the zip, `MANIFEST.csv`, `SHA256SUMS`, and
`ARCHIVE_CONTENTS.md`, and refuses with a non-zero exit if any withheld path
reached the zip. Read the "Withheld" list it prints before uploading; the
private coder keys and answer keys must appear there every time.

## 2. Reserve the DOI *before* submitting the manuscript

The manuscript has to cite the DOI, so reserve it rather than waiting for
publication.

1. On Zenodo, start a **New upload** but do not publish.
2. Under *Basic information* → *Digital Object Identifier*, choose
   **Get a DOI now** / *Reserve DOI*. Zenodo shows the DOI immediately and holds
   it against this draft.
3. Record it. This is the concept-version DOI you will cite.

## 3. Put the DOI in the manuscript

The manuscript is not edited by this guide's author — hand the DOI to whoever
owns the LaTeX. Substitute it at:

- `paper/manuscript/main.tex`, line ~1109: `[ARTIFACT DOI PENDING]`
- `paper/manuscript/main.tex`, line ~1111: `[ARTIFACT DOI PENDING]`
- `paper/COVER_LETTER.md`, data-availability paragraph: `[ARTIFACT DOI]`

Then rebuild the PDFs (`.\scripts\build_submission.ps1`) and regenerate
`SUBMIT/` so the checksums match what is uploaded.

## 4. Fill the Zenodo form from `.zenodo.json`

If the deposit is made by hand rather than through the GitHub integration, copy
title, description, creators, licence (`MIT`), keywords, and the
`related_identifiers` entries out of `.zenodo.json`. The dataset entry must stay:
`hao-li/AIDev-7.6M` at revision `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`,
relation *is derived from*. The AIDev release itself is not uploaded.

## 5. Link the GitHub release to the Zenodo record

The GitHub integration is the tidier route, and it reads `.zenodo.json`
automatically.

1. Zenodo → *GitHub* → authorise, then flip the switch **on** for
   `technoob05/emse2026-multiagent-impact`.
2. In GitHub, create a release with the tag from step 0
   (e.g. `v1.0.0`). Zenodo archives the repository at that tag and mints the
   record.
3. Because the GitHub integration archives the repository tree rather than the
   zip from step 1, upload `build/zenodo/emse2026-multiagent-impact-artifact.zip`
   as an additional file on the record — it carries the derived `outputs/`
   artifacts that `.gitignore` keeps out of git.
4. Copy the Zenodo DOI badge into `README.md` once the record is live.

## 6. Last look before publishing

- [ ] No `-PENDING` string survives in `CITATION.cff` or `.zenodo.json`.
- [ ] The build printed the withheld private keys and exited zero.
- [ ] `SHA256SUMS` in `build/zenodo/` matches the zip you are uploading.
- [ ] Licence on the record reads MIT, and `NOTICE.md` is inside the zip so the
      limits of that licence travel with it.
- [ ] The manuscript no longer says `[ARTIFACT DOI PENDING]`.

Publishing is irreversible: the files on a published Zenodo record cannot be
withdrawn, only superseded by a new version.
