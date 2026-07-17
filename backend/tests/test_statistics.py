import pytest

from memory_mri.statistics import wilson_score_interval


def test_wilson_interval_zero_total() -> None:
    assert wilson_score_interval(0, 0) == (0.0, 0.0)


def test_wilson_interval_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError):
        wilson_score_interval(3, 2)
