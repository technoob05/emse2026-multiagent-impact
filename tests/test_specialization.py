import numpy as np

from multiagent_impact.specialization import classify_title, paired_sign_flip_test


def test_classify_title_accepts_explicit_conventional_prefixes() -> None:
    assert classify_title("feat(parser)!: add a mode") == "feat"
    assert classify_title("[api] FIX: avoid a crash") == "fix"
    assert classify_title("documentation: explain setup") == "docs"
    assert classify_title("tests(core): cover timeout") == "test"


def test_classify_title_rejects_ambiguous_free_text() -> None:
    assert classify_title("Improve service reliability") is None
    assert classify_title("Add a mode") is None
    assert classify_title(None) is None


def test_paired_sign_flip_uses_repository_contrasts() -> None:
    contrasts = np.array([0.1, 0.2, -0.05, 0.3])
    first = paired_sign_flip_test(contrasts, permutations=500, seed=17)
    second = paired_sign_flip_test(contrasts, permutations=500, seed=17)
    assert first == second
    assert first["observed"] == np.mean(contrasts)
    assert 0.0 < first["p_two_sided"] <= 1.0
