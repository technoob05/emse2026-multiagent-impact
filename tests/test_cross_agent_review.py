from __future__ import annotations

import polars as pl

from multiagent_impact.cross_agent_review import classify_agent_account


def test_classify_agent_account_uses_exact_aliases() -> None:
    frame = pl.DataFrame(
        {
            "user": [
                "Copilot",
                "claude[bot]",
                "chatgpt-codex-connector[bot]",
                "coderabbitai[bot]",
                "not-copilot",
                None,
            ]
        }
    ).with_columns(classify_agent_account())

    assert frame["reviewer_agent"].to_list() == [
        "Copilot",
        "Claude_Code",
        "OpenAI_Codex",
        None,
        None,
        None,
    ]
