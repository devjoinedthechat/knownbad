import pytest

from knownbad.stats import interval, rate


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        (0, 10, 0.0, 0.3085),
        (10, 10, 0.6915, 1.0),
        (5, 10, 0.1871, 0.8129),
        (1, 20, 0.0013, 0.2487),
        (0, 100, 0.0, 0.0362),
        (50, 1000, 0.0373, 0.0654),
    ],
)
def test_interval_matches_published_clopper_pearson_values(k, n, low, high):
    got_low, got_high = interval(k, n)
    assert got_low == pytest.approx(low, abs=5e-4)
    assert got_high == pytest.approx(high, abs=5e-4)


def test_interval_edges():
    assert interval(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        interval(3, 2)
    assert rate(0, 0)["rate"] is None
    assert rate(1, 4)["rate"] == 0.25
