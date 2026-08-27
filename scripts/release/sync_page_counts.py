"""Make every document that states a page count read it from the built PDFs.

Page counts were hand-written in three places and drifted every time the paper
changed, at one point telling an editor the manuscript was eleven pages when it
was thirty-one. A count nobody can re-derive is worse than no count, so this
reads the PDFs and rewrites the sentences that carry them.

Run it after any build, before packaging. build_submission.ps1 invokes it.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"


def pages(pdf: pathlib.Path) -> int:
    if not pdf.is_file():
        raise SystemExit(f"{pdf.relative_to(ROOT)} has not been compiled")
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True
    ).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def main() -> None:
    article = pages(MANUSCRIPT / "main.pdf")
    appendix = pages(MANUSCRIPT / "technical_appendix.pdf")
    # Count every supplementary table, not only the generated ones: the
    # constants sweep is written by hand and was silently missing from the total.
    # Count the tables the appendix actually typesets: the ones it inputs, plus
    # any written into the appendix itself. generated_appendix_tables.tex is the
    # aggregate the splitter emits and is not included, so counting it as well
    # doubles the total.
    appendix_sources = [MANUSCRIPT / "technical_appendix.tex"]
    appendix_sources += sorted(MANUSCRIPT.glob("apx_*.tex"))
    tables = sum(
        len(re.findall(r"\\label\{tab:s-", path.read_text(encoding="utf-8")))
        for path in appendix_sources
    )
    figures = len(list(MANUSCRIPT.glob("Fig[0-9].pdf")))
    supplementary = len(list(MANUSCRIPT.glob("FigS[0-9].pdf")))

    edits = (
        (
            ROOT / "paper" / "SUBMISSION_READINESS.md",
            (
                (
                    r"covers all \d+ manuscript pages and all \d+ Supplementary "
                    r"Information pages, which carry \d+ tables",
                    f"covers all {article} manuscript pages and all {appendix} "
                    f"Supplementary Information pages, which carry {tables} tables",
                ),
                (
                    r"- \[x\] \d+ answer-first figures",
                    f"- [x] {figures} answer-first figures",
                ),
                (
                    r"- \[x\] \d+ appendix figures",
                    f"- [x] {supplementary} appendix figures",
                ),
            ),
        ),
        (
            ROOT / "docs" / "audits" / "VALIDATION_REPORT.md",
            (
                (
                    r"- Manuscript: \d+ A4 pages\. Supplementary Information: \d+ A4 pages\.",
                    f"- Manuscript: {article} A4 pages. Supplementary Information: "
                    f"{appendix} A4 pages.",
                ),
            ),
        ),
        (
            ROOT / "paper" / "SUBMISSION_METADATA_FORM.md",
            (
                (
                    r"Manuscript length: \d+ pages",
                    f"Manuscript length: {article} pages",
                ),
            ),
        ),
    )

    changed = 0
    for path, patterns in edits:
        if not path.is_file():
            continue
        text = original = path.read_text(encoding="utf-8")
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
            print(f"updated {path.relative_to(ROOT)}")

    print(
        f"article {article} pages, supplement {appendix} pages, "
        f"{tables} tables, {figures} figures, {supplementary} appendix figures"
    )
    if changed == 0:
        print("every stated count already matched the built PDFs")


if __name__ == "__main__":
    sys.exit(main())
