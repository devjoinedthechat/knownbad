"""Exact binomial intervals, standard library only."""

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


def rate(k: int, n: int) -> dict[str, float | int | None]:
    """A count with its rate and interval, ready to be written to JSON."""
    if n == 0:
        return {"n": 0, "k": 0, "rate": None, "low": None, "high": None}
    low, high = interval(k, n)
    return {"n": n, "k": k, "rate": k / n, "low": low, "high": high}
