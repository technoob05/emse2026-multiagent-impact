from __future__ import annotations

import pytest

from scripts.analysis.run_external_actionability_transfer_probe import parse_actionability


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Classification: Contain Valid Issues Or Suggestions", 1),
        ("Classification: Only Contain General Issues Or Suggestions", 0),
        ("Classification: Not Contain Any Issues Or Suggestions", 0),
    ],
)
def test_parse_actionability(text: str, expected: int) -> None:
    assert parse_actionability(text) == expected


def test_parse_actionability_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unrecognized"):
        parse_actionability("Classification: Maybe")
