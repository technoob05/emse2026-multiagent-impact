"""Catch the two ways a long table can break badly, from the built PDF.

The page-by-page proof that found these is expensive and human-paced, so the
defects it found are worth a check that runs in seconds and cannot get bored.
Both checks read the rendered text of a page, which is what a reader sees,
rather than the source, which is what we hoped would happen.

Defect 1, the stranded continuation head. When a table's head is set with no
room for a row, longtable emits the head, breaks, and emits a continuation head
on the next page directly above the real one. On the page it reads as an empty
table: a "(continued)" caption, a column header, no numbers, and then the real
caption again. Table 8 of the Supplementary Information printed exactly that.

Defect 2, the stranded panel header. A panel title and its column names sitting
alone at the foot of a page with every row overleaf, so the numbers arrive on
the next page with nothing naming them.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# A caption line, as pdftotext renders it: "Table 8: ..." for a numbered head.
NUMBERED_CAPTION = re.compile(r"^\s*Table\s+\d+:", re.MULTILINE)
CONTINUED_CAPTION = re.compile(r"\(continued\)")
# A digit with a decimal point or a percent sign is the cheapest reliable sign
# that a line is carrying data rather than labels.
DATA_LINE = re.compile(r"\d+[.,]\d|\d+\s*%|\bn/a\b")


def pages(pdf: pathlib.Path) -> list[str]:
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return text.split("\f")


def stranded_continuation_heads(page_text: str) -> bool:
    """A continuation head with no data before the next real caption starts."""
    match = CONTINUED_CAPTION.search(page_text)
    if not match:
        return False
    following = NUMBERED_CAPTION.search(page_text, match.end())
    if not following:
        return False
    between = page_text[match.end() : following.start()]
    return not DATA_LINE.search(between)


def stranded_tail(page_text: str, next_page: str | None) -> str | None:
    """Does the page end on labels whose rows went overleaf?

    Three conditions, all required, because looser versions of this check are
    almost all false alarms. An earlier version flagged seven pages of which
    one was real: it read the article's `lineno` margin numbers as a second
    table column, and it read the last row of a table that legitimately ended
    at a page foot as a stranded header.

    So: the tail must carry no data, it must look column-spaced rather than
    like prose, and the table must actually continue -- which the continuation
    caption at the top of the next page is the only reliable evidence of. A
    table that ends at a page foot has stranded nothing.
    """
    if next_page is None or not CONTINUED_CAPTION.search(next_page[:400]):
        return None
    lines = [line for line in page_text.splitlines() if line.strip()]
    # Drop the page number, which is the last line and always a bare integer.
    if lines and lines[-1].strip().isdigit():
        lines = lines[:-1]
    tail = lines[-4:]
    if not tail or any(DATA_LINE.search(line) for line in tail):
        return None
    # The only header that can strand is a panel title, because the plain
    # long tables repeat their column names on every continuation page through
    # `\endhead` and so cannot leave a page without them. Requiring the panel
    # marker is therefore not a heuristic tightening but the actual condition,
    # and it stops the check firing on a table whose last row simply happens to
    # be all words.
    if not any(line.strip().startswith("Panel ") for line in tail):
        return None
    spaced = [line for line in tail if re.search(r"\S {2,}\S", line)]
    if len(spaced) >= 2:
        return " | ".join(line.strip()[:60] for line in tail[-2:])
    return None


def check(pdf: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (failures, warnings).

    The two defects are not equally actionable, so they are not reported the
    same way. A stranded continuation head is a build artefact with a known
    cause and a known fix, so it fails. A panel header at a page foot is
    longtable's own placement decision, and longtable ignores every documented
    way of overriding it -- `\\*` on all 412 body rows moved nothing -- so
    failing on it would mean a gate nobody can ever turn green. It is reported,
    and a human decides whether that page is worth reflowing by hand.
    """
    problems: list[str] = []
    warnings: list[str] = []
    rendered = pages(pdf)
    for index, page_text in enumerate(rendered):
        number = index + 1
        if stranded_continuation_heads(page_text):
            problems.append(
                f"{pdf.name} page {number}: a continuation head with no rows "
                f"under it sits above a real table caption"
            )
        following = rendered[index + 1] if index + 1 < len(rendered) else None
        tail = stranded_tail(page_text, following)
        if tail:
            warnings.append(
                f"{pdf.name} page {number}: a panel header sits at the page "
                f"foot with its rows overleaf -- {tail}"
            )
    return problems, warnings


def main() -> None:
    targets = [
        ROOT / "paper" / "manuscript" / "technical_appendix.pdf",
        ROOT / "paper" / "manuscript" / "main.pdf",
    ]
    problems: list[str] = []
    warnings: list[str] = []
    for pdf in targets:
        if not pdf.is_file():
            print(f"skipped, not built: {pdf.relative_to(ROOT)}")
            continue
        found, noted = check(pdf)
        print(f"{pdf.name}: {len(found)} failure(s), {len(noted)} warning(s)")
        problems.extend(found)
        warnings.extend(noted)

    for problem in problems:
        print(f"  FAIL {problem}")
    for warning in warnings:
        print(f"  warn {warning}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
