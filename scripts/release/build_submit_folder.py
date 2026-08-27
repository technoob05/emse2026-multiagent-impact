"""Assemble one folder that holds everything the portal upload needs."""

import hashlib
import pathlib
import shutil

root = pathlib.Path(r"D:\PhD_LetGoo\PhD_Farming\emse2026-multiagent-impact")
submit = root / "SUBMIT"
if submit.exists():
    shutil.rmtree(submit)
submit.mkdir()

staging = root / "build" / "submission" / "emse_portal_staging"
items = [
    (staging / "manuscript.pdf", "1_manuscript.pdf"),
    (staging / "ESM_1.pdf", "2_online_resource_1.pdf"),
    (staging / "manuscript_source.zip", "3_manuscript_source.zip"),
    (root / "paper" / "COVER_LETTER.md", "4_cover_letter.md"),
    (root / "paper" / "SUBMISSION_METADATA_FORM.md", "5_metadata_form.md"),
    (root / "paper" / "SUBMISSION_READINESS.md", "6_readiness_checklist.md"),
    (root / "paper" / "VENUE_CHECKLIST.md", "7_venue_checklist.md"),
]

copied = []
missing = []
for source, name in items:
    if source.is_file():
        shutil.copy2(source, submit / name)
        copied.append(name)
    else:
        missing.append(str(source.relative_to(root)))

digests = []
for path in sorted(submit.iterdir()):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    digests.append(f"{digest}  {path.name}")
(submit / "CHECKSUMS.sha256").write_text("\n".join(digests) + "\n", encoding="utf-8")

readme = """# SUBMIT — everything the Editorial Manager upload needs

Rebuild this folder at any time with `scripts/build_submission.ps1` followed by
the helper that produced it. Nothing here is edited by hand.

| File | What it is | Where it goes in Editorial Manager |
|---|---|---|
| `1_manuscript.pdf` | The article | Manuscript |
| `2_online_resource_1.pdf` | Supplementary Information | Electronic Supplementary Material |
| `3_manuscript_source.zip` | Flat LaTeX source for the article only: `main.tex`, `references.bib`, the class and style files, and `Fig1.pdf`–`Fig6.pdf` | Source files |
| `4_cover_letter.md` | Cover letter, still holding author placeholders | Cover letter |
| `5_metadata_form.md` | Author metadata and declarations intake | Not uploaded; fill in before submitting |
| `6_readiness_checklist.md` | What is done and what is still open | Not uploaded |
| `7_venue_checklist.md` | Venue requirement map | Not uploaded |
| `CHECKSUMS.sha256` | Integrity record for the files above | Not uploaded |

## Before you upload

The submission is blocked on author input, not on the analysis. In Editorial
Manager choose `Research Papers`, answer yes to the special-issue question, and
select `Agentic Software Engineering`.

Still to do, in order:

1. Fill in affiliation, department, city, country, corresponding email and
   ORCIDs. They appear as `pending` on the title page of both PDFs right now.
2. Complete the declarations: funding, competing interests, ethics wording,
   consent, CRediT roles, acknowledgements.
3. Archive the artifact and replace `[ARTIFACT DOI PENDING]` in the manuscript.
   The public repository is at
   `https://github.com/technoob05/emse2026-multiagent-impact`; a Zenodo release
   of that repository gives a citable DOI.
4. Decide the companion-submission paragraph in the cover letter. See
   `6_readiness_checklist.md`.
5. Rebuild both PDFs after steps 1 to 4, then regenerate this folder so the
   checksums match what you upload.
6. Recheck the Editorial Manager landing page. On 26 August 2026 it displayed
   `Site under development. Do not use for live manuscript submission.`
"""
(submit / "README.md").write_text(readme, encoding="utf-8")

print("SUBMIT/ contains:")
for path in sorted(submit.iterdir()):
    print(f"  {path.stat().st_size / 1024:9.1f} KB  {path.name}")
if missing:
    print("\nMISSING (not copied):")
    for name in missing:
        print("  ", name)
