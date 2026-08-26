from datetime import datetime, timedelta, timezone

from external_validation import (
    CanonicalEvent,
    Compatibility,
    DatasetShape,
    LandmarkRecord,
    assess_shape,
    validate_event_chain,
    validate_landmark_record,
)


PR_COLUMNS = {
    "pr_id",
    "repo_id",
    "author_product",
    "created_at",
    "closed_at",
    "merged_at",
}
EVENT_COLUMNS = {
    "pr_id",
    "event_id",
    "event_kind",
    "event_at",
    "actor_login",
    "actor_kind",
    "product_label",
    "parent_event_id",
    "review_batch_id",
}


def test_full_shape_requires_all_event_topology_constructs() -> None:
    assessment = assess_shape(
        DatasetShape.from_columns(
            name="complete-event-source",
            pull_request_columns=PR_COLUMNS,
            event_columns=EVENT_COLUMNS,
            version_pinned=True,
            fixed_observation_cutoff=True,
            independent_from_primary=True,
        )
    )
    assert assessment.status == Compatibility.FULL
    assert all(assessment.constructs.values())
    assert not assessment.missing_fields


def test_missing_parent_and_batch_is_only_conditional() -> None:
    assessment = assess_shape(
        DatasetShape.from_columns(
            name="rest-snapshot-with-reviews",
            pull_request_columns=PR_COLUMNS,
            event_columns=EVENT_COLUMNS - {"parent_event_id", "review_batch_id"},
            version_pinned=True,
            fixed_observation_cutoff=True,
            independent_from_primary=True,
        )
    )
    assert assessment.status == Compatibility.CONDITIONAL
    assert not assessment.constructs["exact_reply_parent"]
    assert not assessment.constructs["review_batch"]


def test_code_snapshot_dataset_is_incompatible() -> None:
    assessment = assess_shape(
        DatasetShape.from_columns(
            name="function-vulnerability-snapshots",
            pull_request_columns={"repo_id"},
            event_columns=set(),
            version_pinned=True,
            fixed_observation_cutoff=False,
            independent_from_primary=True,
        )
    )
    assert assessment.status == Compatibility.INCOMPATIBLE
    assert not assessment.constructs["pr_trigger"]
    assert not assessment.constructs["later_state"]


def test_event_chain_rejects_wrong_parent_and_same_batch() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    trigger = CanonicalEvent(
        pr_id=10,
        event_id=100,
        event_kind="inline_review_comment",
        event_at=start,
        actor_login="review-agent",
        actor_kind="Bot",
        product_label="reviewer-product",
        review_batch_id=5,
    )
    response = CanonicalEvent(
        pr_id=10,
        event_id=101,
        event_kind="submitted_review",
        event_at=start + timedelta(minutes=1),
        actor_login="author-agent",
        actor_kind="Bot",
        product_label="author-product",
        parent_event_id=999,
        review_batch_id=5,
    )
    assert validate_event_chain(trigger, response) == (
        "not_exact_parent_reply",
        "same_review_batch",
    )


def test_landmark_gate_excludes_pre_landmark_or_post_cutoff_outcomes() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    record = LandmarkRecord(
        pr_id=10,
        pr_created_at=start,
        trigger_at=start + timedelta(hours=1),
        landmark_at=start + timedelta(hours=49),
        observation_cutoff=start + timedelta(days=30),
        closed_at=start + timedelta(hours=24),
        merged_at=start + timedelta(days=31),
    )
    assert validate_landmark_record(record) == (
        "not_open_at_landmark",
        "merged_at_after_observation_cutoff",
    )
