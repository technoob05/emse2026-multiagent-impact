"""Emit the Manuscript Data fields as plain text, straight from main.tex.

Editorial Manager pre-fills title, abstract and keywords from the uploaded
source and asks the author to check them. Checking means comparing against
something, and the only thing worth comparing against is the manuscript itself,
so these are extracted rather than retyped: a title that differs between the
portal record and the article is what ends up wrong in the indexed metadata,
and nobody notices until it is published.

The portal's boxes take rich text, not TeX, so the markup is reduced to what it
prints. The bold run-in labels of a structured abstract survive as plain words
followed by a colon, which is how they read on the page anyway.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN = ROOT / "paper" / "manuscript" / "main.tex"
OUTPUT = ROOT / "SUBMIT" / "9_portal_fields.md"


def braced(source: str, start: int) -> str:
    """Return the balanced `{...}` group beginning at `start`."""
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index]
    raise SystemExit(f"unbalanced braces from position {start}")


def detex(text: str) -> str:
    """Reduce TeX to the words it prints."""
    text = re.sub(r"\\(?:textbf|textit|emph|texttt)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:url|nolinkurl)\{([^{}]*)\}", r"\1", text)
    text = text.replace(r"\%", "%").replace(r"\&", "&").replace(r"\_", "_")
    text = text.replace("~", " ").replace("--", "-")
    text = re.sub(r"\\[a-zA-Z]+\s*", "", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())


def field(command: str) -> str:
    source = MAIN.read_text(encoding="utf-8")
    match = re.search(rf"\\{command}(\[[^\]]*\])?\{{", source)
    if not match:
        raise SystemExit(rf"\{command} not found in main.tex")
    return detex(braced(source, match.end() - 1))


def main() -> None:
    title = field("title")
    abstract = field("abstract")
    keywords = [part.strip() for part in field("keywords").split(",") if part.strip()]

    words = len(abstract.split())
    if not 100 <= words <= 300:
        print(f"warning: abstract is {words} words", file=sys.stderr)

    authors = """| # | Given name | Family name | Email | ORCID | Role |
|---|---|---|---|---|---|
| 1 | Duy Minh | Dao Sy | 23122041@student.hcmus.edu.vn | 0009-0002-4501-2788 | Corresponding, joint first |
| 2 | Trung Kiet | Huynh | | 0009-0000-5463-754X | Joint first |
| 3 | Chi Nguyen | Tran | | 0009-0007-6716-7269 | |
| 4 | Phu Hoa | Pham | | 0009-0001-5471-2578 | |
| 5 | Lam Phu Quy | Nguyen | | 0009-0002-9694-8105 | |"""

    OUTPUT.write_text(
        f"""# Manuscript Data: the fields to check and fill

Extracted from `paper/manuscript/main.tex`, not retyped, so what goes in the
portal is what is in the article. The portal pre-fills these from the uploaded
source and asks you to confirm them; confirm against this.

## Full Title

{title}

## Abstract ({words} words, {len(abstract)} characters)

{abstract}

The article sets Context, Objective, Method, Results and Conclusions in bold as
run-in labels. If the box offers bold, apply it to those five words; if not,
leave the text exactly as above.

## Keywords

Separated by semicolons, as the portal asks:

{"; ".join(keywords)}

## Authors

All five share one affiliation: Faculty of Information Technology, Ho Chi Minh
City University of Science (HCMUS), and Vietnam National University Ho Chi Minh
City (VNU-HCM), Ho Chi Minh City, Vietnam.

{authors}

Order matters and is the order above. Authors 1 and 2 contributed equally and
are joint first authors; if the portal has no field for that, it is already
stated in the manuscript and on the title page.

### Check the author record that is already there

The portal creates the submitting author from the account, and an account name
is not always the name the article uses. The record must read exactly:

- Given name: `Duy Minh`
- Family name: `Dao Sy`

A doubled or reordered given name in this record is what reaches the indexed
metadata, where the manuscript says something else, so correct it before
proceeding rather than after.

## Funding

Tick **Funding information is not applicable / No funding was received.**
This matches the manuscript's own funding statement, which reads: "The authors
received no funding for this work."
""",
        encoding="utf-8",
        newline="\n",
    )
    # The abstract is the one field long enough that pasting it out of a table
    # of contents invites picking up a stray heading, so it also lands on its
    # own with nothing around it.
    (OUTPUT.parent / "9_abstract.txt").write_text(
        abstract + "\n", encoding="utf-8", newline="\n"
    )

    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"  title    : {title[:70]}...")
    print(f"  abstract : {words} words, {len(abstract)} characters")
    print(f"  keywords : {len(keywords)}")


if __name__ == "__main__":
    main()
