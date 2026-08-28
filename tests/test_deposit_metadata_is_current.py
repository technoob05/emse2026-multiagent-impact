"""The deposit metadata must describe the deposit that exists.

`.zenodo.json` went stale without anyone noticing: it still carried the literal
date placeholder and a note saying no author had supplied an ORCID, while the
creators block in the same file listed all five and the published record
carried them too. It survived because the one gate that checks for the
placeholder, `create_zenodo_draft.ps1`, was bypassed when the 16 MB upload had
to go by curl against the bucket URL.

These tests are offline on purpose. Reaching the Zenodo API would make the
suite fail when the network is down, which is not the failure anyone wants to
be told about; the facts checked here are ones the repository already knows.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPOSIT = ROOT / ".zenodo.json"
CITATION = ROOT / "CITATION.cff"

# The published concept the manuscript, cover letter and title page all cite.
DOI = "10.5281/zenodo.22140821"
PUBLISHED_ON = "2026-08-28"

# Tokens that mean "somebody still has to fill this in". A deposit that has
# been published cannot still contain one.
PLACEHOLDERS = ("REPLACE-WITH", "ORCID-PENDING", "TODO", "FIXME", "XXXX")


@pytest.fixture(scope="module")
def deposit() -> dict:
    return json.loads(DEPOSIT.read_text(encoding="utf-8"))


@pytest.mark.parametrize("token", PLACEHOLDERS)
def test_the_deposit_metadata_carries_no_placeholder(token: str) -> None:
    text = DEPOSIT.read_text(encoding="utf-8")
    assert token not in text, (
        f"{DEPOSIT.name} still contains the placeholder {token!r}, so it "
        f"describes a deposit that has not been made"
    )


def test_the_publication_date_is_the_date_it_was_published(deposit: dict) -> None:
    assert deposit.get("publication_date") == PUBLISHED_ON


def test_every_creator_carries_an_orcid(deposit: dict) -> None:
    """The note used to say none of them did. Check the block, not the note."""
    creators = deposit.get("creators", [])
    assert len(creators) == 5, f"expected five creators, found {len(creators)}"
    missing = [creator.get("name") for creator in creators if not creator.get("orcid")]
    assert not missing, f"no ORCID for: {missing}"


def test_the_deposit_and_the_citation_file_agree_on_the_orcids(deposit: dict) -> None:
    """Two files, one set of people. They have disagreed before."""
    citation = CITATION.read_text(encoding="utf-8")
    for creator in deposit.get("creators", []):
        orcid = creator["orcid"]
        assert orcid in citation, (
            f"{creator['name']} has ORCID {orcid} in {DEPOSIT.name} but not in "
            f"{CITATION.name}"
        )


def test_the_notes_do_not_contradict_the_creators(deposit: dict) -> None:
    """A note claiming the iDs are absent, above a block that lists them, is the
    exact failure this file exists to prevent."""
    notes = deposit.get("notes", "").lower()
    assert "no orcid" not in notes
    assert "before publishing" not in notes


def test_the_doi_the_paper_cites_is_recorded_here(deposit: dict) -> None:
    assert DOI in json.dumps(deposit), (
        f"{DEPOSIT.name} does not mention {DOI}, which the manuscript, the "
        f"cover letter and the title page all cite"
    )
