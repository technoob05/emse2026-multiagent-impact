"""Assemble one folder that holds everything the portal upload needs.

This script used to copy from `build/submission/emse_portal_staging/`, which is
written by a separate packaging step. When that step had not been re-run, the
folder silently filled with an older draft: on 2026-08-27 it held a 22-page
manuscript and a 46-page appendix from the previous day. Uploading it would have
submitted the wrong paper, and nothing in the output said so.

So it now builds from the compiled PDFs directly, and refuses to write anything
if a PDF is older than a source file it is built from. A stale submission folder
is worse than no submission folder, because it looks finished.
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import sys
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"
SUBMIT = ROOT / "SUBMIT"

# Everything needed to compile main.tex, and nothing else. The portal wants a
# flat archive for the article alone; the appendix ships as a rendered PDF.
SOURCE_FILES = (
    "main.tex",
    "references.bib",
    # Ship the compiled bibliography as well as the .bib. Editorial Manager
    # auto-compiles the source it is given, and if its run does not invoke
    # BibTeX every citation renders as [?] in the PDF the author is asked to
    # approve. Springer accepts either; sending both means the bibliography in
    # the built PDF is the one that was proofread here.
    "main.bbl",
    "sn-jnl.cls",
    "sn-basic.bst",
)


def figure_files() -> list[str]:
    """Every file main.tex needs beyond the four fixed ones.

    Read from main.tex rather than globbed, because Figure 1 is a TikZ diagram
    that inputs its own .tex files and includes PNG icons: a glob for Fig*.pdf
    would silently ship an archive that does not compile.
    """
    source = (MANUSCRIPT / "main.tex").read_text(encoding="utf-8")
    wanted: list[str] = []

    for stem in re.findall(r"\\input\{([^}]+)\}", source):
        name = stem if stem.endswith(".tex") else f"{stem}.tex"
        wanted.append(name)

    for name in re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", source):
        wanted.append(name)

    # An inputted file can include graphics of its own.
    for name in list(wanted):
        included = MANUSCRIPT / name
        if included.suffix == ".tex" and included.exists():
            body = included.read_text(encoding="utf-8")
            wanted += re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", body)

    # A filename built from macro parameters, as fig1_diagram.tex does with
    # \FigOneIcon, matches the pattern but names no file: TeX substitutes the
    # argument at use time, so the source never spells the real name out.
    wanted = [name for name in wanted if "#" not in name]

    # Which is why the log is the authority on graphics. pdflatex records every
    # file it actually opened as "<use name.png>", after macro expansion, so it
    # catches what no amount of pattern-matching on the source can.
    log = MANUSCRIPT / "main.log"
    if not log.exists():
        raise SystemExit(
            f"{log} is missing; compile main.tex before building the archive, "
            "because the log is what tells us which graphics it really uses"
        )
    wanted += re.findall(r"<use ([^>]+)>", log.read_text(encoding="utf-8", errors="replace"))

    resolved: list[str] = []
    for name in wanted:
        if (MANUSCRIPT / name).exists():
            resolved.append(name)
            continue
        # \includegraphics is usually written without the extension.
        for suffix in (".pdf", ".png", ".jpg"):
            if (MANUSCRIPT / f"{name}{suffix}").exists():
                resolved.append(f"{name}{suffix}")
                break
        else:
            raise SystemExit(
                f"main.tex needs {name!r} and it is not in {MANUSCRIPT}; "
                "the source archive would not compile"
            )

    return sorted(dict.fromkeys(resolved))


def staleness_report() -> list[str]:
    """Name every PDF that is older than something it is built from."""
    problems: list[str] = []

    figures = [MANUSCRIPT / name for name in figure_files()]
    appendix_inputs = sorted(MANUSCRIPT.glob("apx_tables_*.tex")) + [
        MANUSCRIPT / "generated_appendix_tables.tex",
        MANUSCRIPT / "technical_appendix.tex",
    ]

    checks = (
        (
            MANUSCRIPT / "main.pdf",
            [MANUSCRIPT / "main.tex", MANUSCRIPT / "references.bib", *figures],
        ),
        (
            MANUSCRIPT / "technical_appendix.pdf",
            [path for path in appendix_inputs if path.exists()],
        ),
        # Editorial Manager will not build a submission PDF for this article
        # type without a separate file of the item type "Title Page containing
        # ALL Author Contact Info.", so it is a required artefact, not a nicety.
        (MANUSCRIPT / "title_page.pdf", [MANUSCRIPT / "title_page.tex"]),
    )

    for pdf, inputs in checks:
        if not pdf.is_file():
            problems.append(f"{pdf.relative_to(ROOT)} has not been compiled")
            continue
        built = pdf.stat().st_mtime
        for source in inputs:
            if source.stat().st_mtime > built:
                problems.append(
                    f"{pdf.relative_to(ROOT)} is older than "
                    f"{source.relative_to(ROOT)}"
                )
    return problems


def build_source_archive(destination: pathlib.Path) -> list[str]:
    names = list(SOURCE_FILES) + figure_files()
    missing = [name for name in names if not (MANUSCRIPT / name).is_file()]
    if missing:
        raise SystemExit(f"Cannot build the source archive; missing: {missing}")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(MANUSCRIPT / name, arcname=name)
    return names


def build_upload_archive(destination: pathlib.Path, submit: pathlib.Path) -> list[str]:
    """One archive carrying every file that is attached in the portal.

    Editorial Manager's Attach Files page takes a single file at a time, but it
    expands a zip on arrival, so one upload lands the whole set. That is why
    this exists as a separate archive from the LaTeX source one: the source
    archive answers the journal's "supply your editable source" requirement and
    goes in as a deposit, while this one is purely a transport for the upload
    itself.

    Flat, with no directory entries, because the portal lists whatever it finds
    by basename and a folder here would produce files it will not match to an
    item type. The cover letter and the metadata form are deliberately absent:
    they are pasted into portal boxes, not attached, so including them would
    invite uploading a duplicate of something already typed in.
    """
    attached = ["0_title_page.pdf", "1_manuscript.pdf", "ESM_1.pdf"]
    missing = [name for name in attached if not (submit / name).is_file()]
    if missing:
        raise SystemExit(f"Cannot build the upload archive; missing: {missing}")

    source_names = list(SOURCE_FILES) + figure_files()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in attached:
            archive.write(submit / name, arcname=name)
        for name in source_names:
            archive.write(MANUSCRIPT / name, arcname=name)
    return attached + source_names


def main() -> None:
    problems = staleness_report()
    if problems:
        print("REFUSING to build SUBMIT/. Recompile first:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nRun pdflatex twice on main.tex and technical_appendix.tex, then "
            "run this again."
        )
        sys.exit(1)

    if SUBMIT.exists():
        shutil.rmtree(SUBMIT)
    SUBMIT.mkdir()

    shutil.copy2(MANUSCRIPT / "title_page.pdf", SUBMIT / "0_title_page.pdf")
    shutil.copy2(MANUSCRIPT / "main.pdf", SUBMIT / "1_manuscript.pdf")
    # Springer names supplementary files ESM_1.pdf, ESM_2.pdf, and publishes
    # them "as received ... without any conversion, editing, or reformatting",
    # so the local filename is the one readers get. Ship it already named.
    shutil.copy2(MANUSCRIPT / "technical_appendix.pdf", SUBMIT / "ESM_1.pdf")
    archived = build_source_archive(SUBMIT / "3_manuscript_source.zip")
    uploaded = build_upload_archive(SUBMIT / "UPLOAD_THIS.zip", SUBMIT)

    documents = (
        (ROOT / "paper" / "COVER_LETTER.md", "4_cover_letter.md"),
        (ROOT / "paper" / "SUBMISSION_METADATA_FORM.md", "5_metadata_form.md"),
        (ROOT / "paper" / "SUBMISSION_READINESS.md", "6_readiness_checklist.md"),
        (ROOT / "paper" / "VENUE_CHECKLIST.md", "7_venue_checklist.md"),
    )
    missing = []
    for source, name in documents:
        if source.is_file():
            shutil.copy2(source, SUBMIT / name)
        else:
            missing.append(str(source.relative_to(ROOT)))

    # Editorial Manager's cover-letter box is rich text, not Markdown, so the
    # emphasis markers paste in literally. A plain-text twin is what actually
    # gets pasted; the Markdown stays for reading.
    letter = SUBMIT / "4_cover_letter.md"
    if letter.is_file():
        plain = letter.read_text(encoding="utf-8")
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", plain)
        plain = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", plain)
        plain = re.sub(r"`(.+?)`", r"\1", plain)
        (SUBMIT / "4_cover_letter.txt").write_text(plain, encoding="utf-8", newline="\n")

    # Written with explicit newlines so `sha256sum -c` works on every platform;
    # the default on Windows produced CRLF, which sha256sum rejects.
    digests = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(SUBMIT.iterdir())
    ]
    (SUBMIT / "CHECKSUMS.sha256").write_text(
        "\n".join(digests) + "\n", encoding="utf-8", newline="\n"
    )

    readme = f"""# SUBMIT — everything the Editorial Manager upload needs

Built from the compiled PDFs in `paper/manuscript/`. This folder is regenerated,
never edited by hand, and the builder refuses to run if a PDF is older than a
source file it is built from.

The right-hand column is the exact string to pick in Editorial Manager's *Item
Type* dropdown. The dropdown for this article type offers only: Title Page
containing ALL Author Contact Info. / Manuscript / Figure / Table /
Supplementary Material / Authorship change form. There is no "LaTeX supporting
file" entry, so source files go under Supplementary Material.

**Upload `UPLOAD_THIS.zip` and nothing else.** The Attach Files page takes one
file per upload but expands a zip on arrival, so that single upload lands all
{len(uploaded)} attached files. Then set the item types below and press *Change
Now* once for the whole LaTeX set.

| File | What it is | Item Type to choose |
|---|---|---|
| `UPLOAD_THIS.zip` | Everything in the three rows below plus the LaTeX source, flat | Upload it; the portal expands it and the rows arrive individually |
| `0_title_page.pdf` | Title, all five authors with affiliations, ORCIDs and the corresponding email, and the declarations | **Title Page containing ALL Author Contact Info.** Required: the portal will not build a submission PDF without it. |
| `1_manuscript.pdf` | The article | **Manuscript** |
| `ESM_1.pdf` | Supplementary Information | **Supplementary Material**. Online Resource 1. Springer's own naming convention; upload it under exactly this name. |
| the {len(archived)} LaTeX source files | {", ".join(f"`{name}`" for name in archived)} | **Supplementary Material**, all of them. Use *Change Item Type of all [Choose] files* to set them in one press. Do not mark `main.tex` as Manuscript: that asks the portal to typeset the article itself, and then reviewers read its build rather than the PDF verified here. |
| `3_manuscript_source.zip` | The same source files as a standalone deposit, for anywhere that asks for source as one file | Not uploaded. Its contents already travel inside `UPLOAD_THIS.zip`, so uploading this too would duplicate all {len(archived)}. |
| `4_cover_letter.md` | Cover letter | Read this one. |
| `4_cover_letter.txt` | Cover letter | Paste this one: the portal's box is rich text, so Markdown markers would appear literally. |
| `5_metadata_form.md` | Title, author records with affiliations and ORCIDs, declarations, and CRediT roles. It carries no abstract and no keywords; both are in the manuscript | Typed into the portal |
| `6_readiness_checklist.md` | What is done and what is still open | Not uploaded |
| `7_venue_checklist.md` | The venue's stated requirements | Not uploaded |
| `CHECKSUMS.sha256` | Integrity record; verify with `sha256sum -c` | Not uploaded |

## Not attached, but still needed

Three things are typed or pasted into the portal rather than uploaded, so they
are easy to forget: the cover letter goes in its rich-text box from
`4_cover_letter.txt`, the author records come from `5_metadata_form.md`, and the
artifact DOI `https://doi.org/10.5281/zenodo.22140821` goes in under the
*Link(s) to supporting data* option rather than as a file.

## Before pressing Approve

Editorial Manager builds its own PDF from what you attached, and that build is
what reviewers read. Open it and check three things the upload cannot guarantee:
the bibliography resolves rather than printing `[?]`, all six figures render,
and Online Resource 1 is listed.
"""
    (SUBMIT / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    print("SUBMIT/ contains:")
    for path in sorted(SUBMIT.iterdir()):
        print(f"  {path.stat().st_size / 1024:9.1f} KB  {path.name}")
    if missing:
        print("\nMissing, so not included:")
        for name in missing:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
