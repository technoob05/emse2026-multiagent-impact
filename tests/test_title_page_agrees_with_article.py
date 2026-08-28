"""The submission sends two documents that both state who the authors are and
what they declare: the article, and a standalone title page that Editorial
Manager requires as its own item type. An editor reads them side by side, so if
they ever disagree the disagreement is the first thing anyone notices.

Nothing stops them drifting apart, because they are separate files compiled
separately. These tests are what stops it. They compare the prose rather than
the markup, so rewrapping a paragraph is free and changing a word is not.
"""

from __future__ import annotations

import pathlib
import re

import pytest

MANUSCRIPT = pathlib.Path(__file__).resolve().parents[1] / "paper" / "manuscript"
ARTICLE = MANUSCRIPT / "main.tex"
TITLE_PAGE = MANUSCRIPT / "title_page.tex"

# Declarations that both documents must carry, and must word identically.
# "Funding" is deliberately included even though it is one short sentence: a
# funding statement that differs between two submitted files is exactly the kind
# of thing that holds a manuscript at the editorial desk.
SHARED_DECLARATIONS = (
    "Funding",
    "Competing interests",
    "Ethics approval and consent to participate",
    "Consent for publication",
    "Data availability",
    "Materials availability",
    "Code availability",
    "Author contributions",
)

AUTHORS = (
    ("Duy Minh Dao Sy", "0009-0002-4501-2788"),
    ("Trung Kiet Huynh", "0009-0000-5463-754X"),
    ("Chi Nguyen Tran", "0009-0007-6716-7269"),
    ("Phu Hoa Pham", "0009-0001-5471-2578"),
    ("Lam Phu Quy Nguyen", "0009-0002-9694-8105"),
)


def strip_comments(text: str) -> str:
    """Drop TeX comments. A commented-out line is not something a reader sees."""
    return "\n".join(
        re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines()
    )


def normalise(text: str) -> str:
    """Reduce TeX to the words it prints, so wrapping and markup do not matter.

    The article uses `\\url` inside a Springer class and the title page uses it
    inside `article`; both print the address, so both reduce to the address.
    `Section~\\ref{...}` has no counterpart on a title page that has no
    sections, so a reference collapses to nothing and the sentence around it is
    what gets compared.
    """
    text = strip_comments(text)
    text = re.sub(r"\\(?:url|href\{[^}]*\})\{([^}]*)\}", r"\1", text)
    text = re.sub(r"Section~\\ref\{[^}]*\}", "the article's method section", text)
    text = re.sub(r"\\(?:noindent|textbf|emph|,)\s*", " ", text)
    text = text.replace("{", " ").replace("}", " ").replace("~", " ")
    return " ".join(text.split())


def declarations(path: pathlib.Path) -> dict[str, str]:
    """Split a file's declarations block into `heading -> normalised prose`."""
    body = strip_comments(path.read_text(encoding="utf-8"))
    headings = "|".join(re.escape(name) for name in SHARED_DECLARATIONS)
    pattern = re.compile(
        r"\\textbf\{(" + headings + r")\.\}(.*?)(?=\\(?:noindent\s*)?\\?textbf\{"
        r"(?:" + headings + r")\.\}|\\bibliography|\\end\{document\})",
        re.DOTALL,
    )
    return {
        match.group(1): normalise(match.group(2)).strip().lstrip(".").strip()
        for match in pattern.finditer(body)
    }


@pytest.fixture(scope="module")
def article_declarations() -> dict[str, str]:
    return declarations(ARTICLE)


@pytest.fixture(scope="module")
def title_page_declarations() -> dict[str, str]:
    return declarations(TITLE_PAGE)


def test_the_title_page_exists() -> None:
    """Editorial Manager will not build a submission PDF for this article type
    without a file of item type "Title Page containing ALL Author Contact
    Info.", so its absence is a submission blocker, not a tidiness problem."""
    assert TITLE_PAGE.is_file(), f"{TITLE_PAGE} is missing"


@pytest.mark.parametrize("heading", SHARED_DECLARATIONS)
def test_both_documents_carry_the_declaration(
    heading: str,
    article_declarations: dict[str, str],
    title_page_declarations: dict[str, str],
) -> None:
    assert heading in article_declarations, f"main.tex lacks a {heading} statement"
    assert heading in title_page_declarations, (
        f"title_page.tex lacks a {heading} statement"
    )


@pytest.mark.parametrize("heading", SHARED_DECLARATIONS)
def test_the_declarations_say_the_same_thing(
    heading: str,
    article_declarations: dict[str, str],
    title_page_declarations: dict[str, str],
) -> None:
    assert article_declarations[heading] == title_page_declarations[heading], (
        f"the {heading} statement differs between the article and the title "
        f"page.\n  article    : {article_declarations[heading]}\n"
        f"  title page : {title_page_declarations[heading]}"
    )


@pytest.mark.parametrize("name,orcid", AUTHORS)
def test_the_title_page_carries_each_author_and_orcid(name: str, orcid: str) -> None:
    """The article prints no ORCIDs, so the title page is the only document in
    the submission that carries them. If one is wrong here it is wrong
    everywhere."""
    text = normalise(TITLE_PAGE.read_text(encoding="utf-8"))
    assert name in text, f"{name} is missing from the title page"
    assert orcid in text, f"{name}'s ORCID {orcid} is missing from the title page"


def test_the_title_page_names_a_corresponding_author_with_an_address() -> None:
    text = normalise(TITLE_PAGE.read_text(encoding="utf-8"))
    assert "Corresponding author" in text
    assert "23122041@student.hcmus.edu.vn" in text


def test_the_author_order_matches_the_article() -> None:
    """Author order is a claim about credit. It has to be the same claim in
    both files, so compare positions rather than mere presence."""
    page = normalise(TITLE_PAGE.read_text(encoding="utf-8"))
    article = normalise(ARTICLE.read_text(encoding="utf-8"))
    for earlier, later in zip(AUTHORS, AUTHORS[1:]):
        for label, text in (("title page", page), ("article", article)):
            assert text.index(earlier[0]) < text.index(later[0]), (
                f"{label}: {later[0]} appears before {earlier[0]}"
            )


def test_the_titles_match() -> None:
    title = "Participation Is Not Collaboration"
    subtitle = "When One LLM Coding Agent Reviews Another on GitHub, a Person Answers"
    for path in (ARTICLE, TITLE_PAGE):
        text = normalise(path.read_text(encoding="utf-8"))
        assert title in text, f"{path.name} does not carry the title"
        assert subtitle in text, f"{path.name} does not carry the subtitle"


def test_the_artifact_doi_is_the_same_one() -> None:
    """A title page pointing at a different deposit than the article would send
    a reviewer to the wrong archive."""
    pattern = re.compile(r"10\.5281/zenodo\.\d+")
    article = set(pattern.findall(ARTICLE.read_text(encoding="utf-8")))
    page = set(pattern.findall(TITLE_PAGE.read_text(encoding="utf-8")))
    assert page, "the title page cites no artifact DOI"
    assert page == article, f"DOIs differ: article {article}, title page {page}"
