import math

import pytest

from knownbad.stats import _beta_cdf, interval, interval_of_mean, rate


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


@pytest.mark.parametrize("x", [0.001, 0.02, 0.3, 0.5, 0.77, 0.999])
def test_the_beta_distribution_matches_its_closed_forms(x):
    # Beta(1/2, 1/2) is the arcsine law; Beta(a, 1) is x**a; Beta(2, 3) is a polynomial.
    assert _beta_cdf(0.5, 0.5, x) == pytest.approx(2 / math.pi * math.asin(math.sqrt(x)), abs=1e-10)
    assert _beta_cdf(3.7, 1.0, x) == pytest.approx(x**3.7, abs=1e-10)
    assert _beta_cdf(2.0, 3.0, x) == pytest.approx(6 * x**2 - 8 * x**3 + 3 * x**4, abs=1e-10)


@pytest.mark.parametrize("n", [1, 2, 7, 43, 300, 2000])
def test_the_interval_of_a_mean_is_the_exact_interval_for_whole_counts(n):
    for k in sorted({0, 1, n // 3, n // 2, n - 1, n}):
        assert interval_of_mean(k, n) == pytest.approx(interval(k, n), abs=1e-9)


def test_the_interval_of_a_mean_takes_a_fraction_and_moves_with_it():
    # No leak in 30 draws: the upper end is 1 - 0.025 ** (1 / 30).
    assert interval_of_mean(0, 30) == pytest.approx((0.0, 1 - 0.025 ** (1 / 30)), abs=1e-9)
    ends = [interval_of_mean(total, 30) for total in (0, 0.1, 0.5, 1, 1.5, 2)]
    assert all(a[0] <= b[0] and a[1] < b[1] for a, b in zip(ends, ends[1:], strict=False))
    assert interval_of_mean(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        interval_of_mean(31, 30)


def test_a_rate_over_several_controls_per_item_counts_the_items():
    alone = rate(0, 300)
    grouped = rate(0, 300, items=30)
    assert alone["high"] == pytest.approx(0.0122, abs=5e-4) and alone["items"] == 300
    # Thirty items cannot support more than thirty draws would.
    assert grouped["high"] == pytest.approx(0.1157, abs=5e-4) and grouped["items"] == 30
    assert grouped["rate"] == alone["rate"] == 0.0

    one_each = rate(9, 20, items=20)
    assert (one_each["low"], one_each["high"]) == interval(9, 20)
    wide, narrow = rate(30, 300, items=30), rate(30, 300)
    assert wide["rate"] == narrow["rate"] == 0.1
    assert wide["low"] < narrow["low"] and wide["high"] > narrow["high"]
    assert rate(3, 5, items=50)["items"] == 5  # never more draws than controls
