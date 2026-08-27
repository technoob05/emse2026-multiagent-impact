"""Pair every citation with the sentence that makes a claim about its source.

Verifying that a reference exists is the easy half. The half that matters is
whether the sentence citing it says what that paper actually says. This pulls
each citation together with its surrounding sentence so a check can be aimed at
the claim rather than at the entry.
"""

from __future__ import annotations

import csv
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"
OUTPUT = ROOT / "outputs" / "citation_audit"


def strip_tex(text: str) -> str:
    text = re.sub(r"(?m)^\s*%.*$", "", text)
    text = re.sub(r"(?s)\\begin\{figure\}.*?\\end\{figure\}", " ", text)
    text = re.sub(r"(?s)\\begin\{table\}.*?\\end\{table\}", " ", text)
    text = re.sub(r"\\(emph|textbf|textit|texttt)\{([^{}]*)\}", r"\2", text)
    text = re.sub(r"\\(label|ref|nolinkurl|url)\{[^{}]*\}", " ", text)
    return text


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\\])", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts]


def entry_titles(bib: str) -> dict[str, str]:
    titles: dict[str, str] = {}
    for block in re.split(r"(?=@\w+\{)", bib):
        key = re.search(r"@\w+\{([^,]+),", block)
        title = re.search(r"(?m)^\s*title\s*=\s*\{(.+?)\}\s*,?\s*$", block, re.S)
        if key and title:
            clean = re.sub(r"[{}]", "", title.group(1))
            titles[key.group(1).strip()] = re.sub(r"\s+", " ", clean).strip()
    return titles


def main() -> None:
    bib = (MANUSCRIPT / "references.bib").read_text(encoding="utf-8")
    titles = entry_titles(bib)

    rows: list[dict[str, str]] = []
    for name in ("main.tex", "technical_appendix.tex"):
        body = strip_tex((MANUSCRIPT / name).read_text(encoding="utf-8"))
        for sentence in sentences(body):
            keys = re.findall(r"\\cite[a-z]*\{([^{}]+)\}", sentence)
            if not keys:
                continue
            claim = re.sub(r"\\cite[a-z]*\{[^{}]+\}", "[CITE]", sentence)
            claim = re.sub(r"\\[a-zA-Z]+\s*", " ", claim)
            claim = re.sub(r"\s+", " ", claim).strip()
            for group in keys:
                for key in (part.strip() for part in group.split(",")):
                    rows.append(
                        {
                            "key": key,
                            "title": titles.get(key, "KEY NOT IN BIB"),
                            "document": name,
                            "claim": claim,
                        }
                    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "citation_claims.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "title", "document", "claim"])
        writer.writeheader()
        writer.writerows(rows)

    distinct = sorted({row["key"] for row in rows})
    missing = [key for key in distinct if titles.get(key) == "KEY NOT IN BIB"]
    print(f"{len(rows)} citation-claim pairs across {len(distinct)} distinct keys")
    print(f"keys not found in the bibliography: {missing or 'none'}")
    for key in distinct:
        count = sum(1 for row in rows if row["key"] == key)
        print(f"  {key:<32} {count} claim(s)")


if __name__ == "__main__":
    main()
