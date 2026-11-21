"""Exact binomial intervals and an exact paired test, standard library only."""

from __future__ import annotations

import math


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def _cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, math.fsum(math.exp(_log_pmf(i, n, p)) for i in range(k + 1)))


def _solve(target: float, k: int, n: int) -> float:
    """The p at which P(X <= k) equals target. The CDF falls as p rises."""
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        if _cdf(k, n, mid) > target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Clopper-Pearson interval for k successes in n trials.

    Exact, so it never claims more than the data supports, which matters most
    in the case this tool cares about: zero leaks out of a small number.
    """
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else _solve(1 - alpha / 2, k - 1, n)
    upper = 1.0 if k == n else _solve(alpha / 2, k, n)
    return (lower, upper)


def _beta_fraction(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        for numerator in (
            m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
            -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1)),
        ):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def _beta_cdf(a: float, b: float, x: float) -> float:
    """P(B <= x) for B ~ Beta(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    # The fraction converges fast on one side of the mean; use the mirror on the other.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def _beta_quantile(q: float, a: float, b: float) -> float:
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        if _beta_cdf(a, b, mid) < q:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def interval_of_mean(total: float, draws: int, confidence: float = 0.95) -> tuple[float, float]:
    """Interval for the mean of `draws` values that each lie between 0 and 1.

    `total` is their sum. This is the Clopper-Pearson interval written with
    the beta distribution, which lets the count be a fraction: for a whole
    count it is the same interval as `interval`.
    """
    if draws <= 0:
        return (0.0, 1.0)
    if not -1e-9 <= total <= draws + 1e-9:
        raise ValueError(f"need 0 <= total <= draws, got total={total}, draws={draws}")
    total = min(max(total, 0.0), float(draws))
    alpha = 1.0 - confidence
    lower = 0.0 if total <= 0 else _beta_quantile(alpha / 2, total, draws - total + 1)
    upper = 1.0 if total >= draws else _beta_quantile(1 - alpha / 2, total + 1, draws - total)
    return (lower, upper)


def rate(k: int, n: int, items: int | None = None) -> dict[str, float | int | None]:
    """A count with its rate and interval, ready to be written to JSON.

    `items` is how many items the n controls were built from. Controls of one
    item share its question and its reference, so they are not n independent
    draws: a grader that misreads an item tends to leak several of its
    controls at once. The interval therefore counts each item as one draw and
    its share of leaks as the value drawn. With one control per item that is
    the plain exact interval; with more it is wider, and it holds its 95%
    however strongly the controls of an item move together.
    """
    if n == 0:
        return {"n": 0, "k": 0, "rate": None, "low": None, "high": None, "items": 0}
    draws = n if items is None else max(1, min(items, n))
    low, high = interval(k, n) if draws == n else interval_of_mean(draws * k / n, draws)
    return {"n": n, "k": k, "rate": k / n, "low": low, "high": high, "items": draws}


def sign_test(a: int, b: int) -> float | None:
    """Exact two-sided sign test on paired changes (McNemar's exact test).

    `a` units changed one way and `b` the other. If the grader had not really
    changed, a change would go either way with equal chance. Returns the
    probability of a split at least this uneven, or None when nothing changed.
    """
    n = a + b
    if n == 0:
        return None
    return min(1.0, 2.0 * _cdf(min(a, b), n, 0.5))
