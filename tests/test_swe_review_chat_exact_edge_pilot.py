from __future__ import annotations

from datetime import datetime, timezone

from scripts.analysis.run_swe_review_chat_exact_edge_pilot import (
    actor_category,
    choose_first_trigger,
    comment_projection,
    parse_timestamp,
    pull_projection,
    state_at_landmark,
)


def test_actor_category_is_exact_and_relative_to_parent_and_author() -> None:
    user = actor_category("human-dev", "User", "Cursor", "Claude_Code")
    assert user["relation_to_parent"] == "user_unmapped_product"
    same_parent = actor_category("cursor[bot]", "Bot", "Cursor", "Claude_Code")
    assert same_parent["relation_to_parent"] == "same_as_parent_product"
    assert same_parent["relation_to_author"] == "different_from_author_product"
    author_reply = actor_category("claude[bot]", "Bot", "Cursor", "Claude_Code")
    assert author_reply["relation_to_parent"] == "different_from_parent_product"
    assert author_reply["relation_to_author"] == "same_as_author_product"


def test_first_trigger_orders_by_time_then_comment_id_and_fails_closed() -> None:
    triggers = [
        {"timestamp": "2026-01-01T01:00:00Z", "comment_id": 20},
        {"timestamp": "2026-01-01T01:00:00Z", "comment_id": 10},
        {"timestamp": "2026-01-01T02:00:00Z", "comment_id": 5},
    ]
    assert choose_first_trigger(triggers) == (
        10,
        "determined_by_timestamp_then_comment_id",
    )
    assert choose_first_trigger([{"timestamp": None, "comment_id": 10}])[0] is None
    assert choose_first_trigger([{"timestamp": "2026-01-01T00:00:00Z", "comment_id": None}])[0] is None


def test_state_at_landmark_handles_close_and_reopen_sequence() -> None:
    events = [
        {"type": "closed", "timestamp": "2026-01-01T12:00:00Z"},
        {"type": "reopened", "timestamp": "2026-01-02T00:00:00Z"},
    ]
    before_reopen, _ = state_at_landmark(
        events, datetime(2026, 1, 1, 18, tzinfo=timezone.utc)
    )
    after_reopen, _ = state_at_landmark(
        events, datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    )
    assert before_reopen is False
    assert after_reopen is True
    assert state_at_landmark(
        [{"type": "closed", "timestamp": "invalid"}],
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )[0] is None


def test_api_projections_never_export_body_or_diff() -> None:
    raw_comment = {
        "id": 1,
        "body": "must not persist",
        "diff_hunk": "must not persist",
        "created_at": "2026-01-01T00:00:00Z",
        "user": {"login": "cursor[bot]", "type": "Bot", "email": "hidden"},
    }
    projected_comment = comment_projection(raw_comment)
    assert "body" not in projected_comment
    assert "diff_hunk" not in projected_comment
    assert "email" not in projected_comment["user"]
    raw_pull = {
        "number": 3,
        "body": "must not persist",
        "title": "must not persist",
        "user": {"login": "claude[bot]", "type": "Bot"},
    }
    projected_pull = pull_projection(raw_pull)
    assert "body" not in projected_pull
    assert "title" not in projected_pull


def test_parse_timestamp_normalizes_to_utc_and_rejects_invalid() -> None:
    assert parse_timestamp("2026-01-01T01:00:00+01:00") == datetime(
        2026, 1, 1, 0, tzinfo=timezone.utc
    )
    assert parse_timestamp("invalid") is None
