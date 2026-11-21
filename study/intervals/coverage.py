"""How often does a 95% interval contain the true leak rate?

    python study/intervals/coverage.py

Draws runs in which the controls of one item leak together to a set degree,
and counts how often each interval contains the rate the run was drawn from.
The table in docs/statistics.md comes from this script. No model is called.
"""

from __future__ import annotations

import random

from knownbad.stats import interval, rate

ITEMS, PER_ITEM, RUNS = 43, 11, 1500
TOGETHER = {"independent": 0.0, "partly together": 0.2, "all together": 1.0}


def leaks_per_item(source: random.Random, p: float, together: float) -> list[int]:
    """`together` is the share of the variation that lies between items."""
    counts = []
    for _ in range(ITEMS):
        if together >= 1.0:
            chance = 1.0 if source.random() < p else 0.0
        elif together <= 0.0:
            chance = p
        else:
            spread = (1 - together) / together
            chance = source.betavariate(p * spread, (1 - p) * spread)
        counts.append(sum(source.random() < chance for _ in range(PER_ITEM)))
    return counts


def main() -> None:
    source = random.Random(1)
    print("| True leak rate | Controls of an item | Over controls | Over items |")
    print("|---|---|---|---|")
    for p in (0.01, 0.05, 0.2, 0.5):
        for name, together in TOGETHER.items():
            over_controls = over_items = 0
            for _ in range(RUNS):
                k, n = sum(leaks_per_item(source, p, together)), ITEMS * PER_ITEM
                low, high = interval(k, n)
                over_controls += low <= p <= high
                row = rate(k, n, ITEMS)
                over_items += row["low"] <= p <= row["high"]  # type: ignore[operator]
            print(f"| {p:.0%} | {name} | {over_controls / RUNS:.0%} | {over_items / RUNS:.0%} |")


if __name__ == "__main__":
    main()
