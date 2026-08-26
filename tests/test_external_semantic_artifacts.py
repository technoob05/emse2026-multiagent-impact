from external_validation.semantic_artifacts import parse_public_comment_reference


def test_parse_review_comment_identity() -> None:
    reference = parse_public_comment_reference(
        "https://api.github.com/repos/example/project/pulls/comments/1434615985"
    )
    assert reference is not None
    assert reference.kind == "review_comment"
    assert reference.public_id == 1434615985
    assert reference.fragment_index is None


def test_issue_comment_fragments_share_one_public_event() -> None:
    first = parse_public_comment_reference(
        "https://api.github.com/repos/example/project/issues/comments/1822395908-1"
    )
    third = parse_public_comment_reference(
        "https://api.github.com/repos/example/project/issues/comments/1822395908-3"
    )
    assert first is not None and third is not None
    assert first.event_key == third.event_key == ("issue_comment", 1822395908)
    assert first.fragment_index == 1
    assert third.fragment_index == 3


def test_unrecognized_comment_identifier_fails_closed() -> None:
    assert parse_public_comment_reference("c_1") is None
