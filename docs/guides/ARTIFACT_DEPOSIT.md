# Depositing the artifact on Zenodo

Ordered checklist for the person doing the deposit.

Author metadata is **done**. Names, order, joint first authorship, both
affiliations, the corresponding email, the licence, the version tag `v1.0.0`,
the description, and the pinned source-data revision are final in
`CITATION.cff` and `.zenodo.json`, and they match the manuscript title page.
The archive is built and verified by script.

Three things are left, and each of them genuinely needs a person, because no
script may invent an identifier or speak for an author:

1. **Reserve the DOI on Zenodo** (step 2 below).
2. **Supply the five ORCID iDs** (step 3 below).
3. **Substitute the DOI into the manuscript** (step 4 below), which is owned by
   someone else.

## 1. Build and check the archive

```powershell
.\.venv\Scripts\python.exe scripts\release\build_zenodo_archive.py --self-test
.\.venv\Scripts\python.exe scripts\release\build_zenodo_archive.py
```

The self-test proves the exclusion guard still refuses every path in the
`NEVER PUBLISH` block of `.gitignore`. The build then writes `build/zenodo/`
with the zip, `MANIFEST.csv`, `SHA256SUMS`, and `ARCHIVE_CONTENTS.md`, and
refuses with a non-zero exit if any withheld path reached the zip. Read the
"Withheld" list it prints before uploading; the private coder keys and answer
keys must appear there every time.

The zip carries code, `outputs/`, `docs/`, `protocol/`, the metadata files, and
`REPRODUCE.md`. It does not carry `paper/`: the manuscript is under the
publisher agreement, not the MIT licence. So step 4 does not change the zip, and
this step can be run before or after it. Rerun it after step 3, though, since
the ORCID edits change `CITATION.cff` and `.zenodo.json`, which are both inside.

## 1b. The deposit script

`scripts/release/create_zenodo_draft.ps1` does steps 1 and 2 of section 2 for
you: it creates a draft, uploads the archive, writes the metadata from
`.zenodo.json`, and prints the reserved DOI. It never publishes unless you pass
both `-Publish` and the exact confirmation phrase, because a published Zenodo
record is public and cannot be deleted.

Check the archive and metadata first. This needs no token and touches no
network:

```powershell
powershell -ExecutionPolicy Bypass -File scripts
elease\create_zenodo_draft.ps1 `
  -Archive build\zenodo\emse2026-multiagent-impact-artifact.zip `
  -Metadata .zenodo.json -ValidateOnly
```

Then create the draft. The token is read only from a process-scoped environment
variable, never from a file, an argument or a URL, so it cannot end up in a
shell history or a log. Use a freshly issued token, and revoke it afterwards:

```powershell
$env:ZENODO_ACCESS_TOKEN = Read-Host -AsSecureString |
  ConvertFrom-SecureString -AsPlainText

powershell -ExecutionPolicy Bypass -File scripts
elease\create_zenodo_draft.ps1 `
  -Archive build\zenodo\emse2026-multiagent-impact-artifact.zip `
  -Metadata .zenodo.json -Production
```

Omit `-Production` to practise against the Zenodo sandbox, which needs its own
account and its own token. The receipt it prints carries `reserved_doi`, which
is the identifier the manuscript should cite, and `draft_url`, where you can
inspect what would be published before anyone publishes it.

## 2. Reserve the DOI *before* submitting the manuscript

The manuscript has to cite the DOI, so reserve it rather than waiting for
publication.

1. On Zenodo, start a **New upload** but do not publish.
2. Under *Basic information* → *Digital Object Identifier*, choose
   **Get a DOI now** / *Reserve DOI*. Zenodo shows the DOI immediately and holds
   it against this draft.
3. Record it. This is the concept-version DOI you will cite.
4. Back in `CITATION.cff`, uncomment the `doi:` line and set it, and uncomment
   `date-released:` and set it to today's date in `YYYY-MM-DD` form. Both are
   commented out on purpose: the CFF 1.2.0 schema pattern-constrains them, so a
   literal placeholder would fail validation.

## 3. Supply the ORCID iDs

Ask each of the five authors for their ORCID iD. Then:

- `CITATION.cff`: uncomment that author's `# orcid:` line and set it to the full
  URL form, `https://orcid.org/0000-0000-0000-0000`.
- `.zenodo.json`: add an `"orcid"` key to that author's entry in `creators`,
  in the bare `0000-0000-0000-0000` form. The creators currently carry no
  `orcid` key at all, and the `notes` field says why; trim that sentence out of
  `notes` once every author has one.

If an author has no ORCID, leave their entry without one. Do not invent a value:
a fabricated iD in a citation record silently mis-attributes the work to a
stranger, which is worse than a missing field.

After editing, revalidate:

```powershell
uv run --with cffconvert cffconvert --validate
.\.venv\Scripts\python.exe -c "import json; json.load(open('.zenodo.json', encoding='utf-8'))"
```

## 4. Put the DOI in the manuscript

The manuscript is not edited by this guide's author. Hand the DOI to whoever
owns the LaTeX. There are exactly two markers, both in
`paper/manuscript/main.tex`:

- line ~1225, data-availability sentence: `https://doi.org/10.5281/zenodo.22140821`
- line ~1232, code-availability sentence: `https://doi.org/10.5281/zenodo.22140821`

`paper/COVER_LETTER.md` carries the same DOI in its data-availability
paragraph if that file is used.

Then rebuild the PDFs (`.\scripts\build_submission.ps1`) and regenerate
`SUBMIT/`. The Zenodo zip is unaffected; it does not contain `paper/`.

## 5. Fill the Zenodo form from `.zenodo.json`

If the deposit is made by hand rather than through the GitHub integration, copy
title, description, creators with their affiliations, licence (`MIT`), version
(`v1.0.0`), keywords, and the `related_identifiers` entries out of
`.zenodo.json`. The dataset entry must stay: `hao-li/AIDev-7.6M` at revision
`37bbe1533e26cc1e1374917dba1186d1c8a4dc81`, relation *is derived from*. The
AIDev release itself is not uploaded.

Two facts have no field on the Zenodo form and live in `notes`, so keep `notes`
on the record: Duy Minh Dao Sy and Trung Kiet Huynh are joint first authors, and
the authors received no funding and declare no competing interests.

## 6. Link the GitHub release to the Zenodo record

The GitHub integration is the tidier route, and it reads `.zenodo.json`
automatically.

1. Zenodo → *GitHub* → authorise, then flip the switch **on** for
   `technoob05/emse2026-multiagent-impact`.
2. In GitHub, create a release tagged `v1.0.0`. Zenodo archives the repository
   at that tag and mints the record.
3. Because the GitHub integration archives the repository tree rather than the
   zip from step 1, upload `build/zenodo/emse2026-multiagent-impact-artifact.zip`
   as an additional file on the record. It carries the derived `outputs/`
   artifacts that `.gitignore` keeps out of git.
4. Copy the Zenodo DOI badge into `README.md` once the record is live.

## 7. Last look before publishing

- [ ] Every author has an ORCID on the record, or is deliberately without one.
- [ ] No `-PENDING` string survives in `CITATION.cff` or `.zenodo.json`.
- [ ] `cffconvert --validate` still passes after the ORCID and DOI edits.
- [ ] The build printed the withheld private keys and exited zero.
- [ ] `SHA256SUMS` in `build/zenodo/` matches the zip you are uploading.
- [ ] Licence on the record reads MIT, and `NOTICE.md` is inside the zip so the
      limits of that licence travel with it.
- [ ] `REPRODUCE.md` is inside the zip; it is the entry point for anyone who
      downloads the record and has nothing else.
- [ ] The manuscript no longer says `https://doi.org/10.5281/zenodo.22140821`.

Publishing is irreversible: the files on a published Zenodo record cannot be
withdrawn, only superseded by a new version.
