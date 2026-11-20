"""knownbad is an instrument too. These tests check it against graders whose
error rate is known because we set it."""

import hashlib
import random

import pytest

from knownbad import check
from knownbad.model import FAIL
from knownbad.stats import interval, sign_test


@pytest.mark.parametrize("n", [20, 150])
@pytest.mark.parametrize("p", [0.0, 0.02, 0.1, 0.5, 0.9])
def test_the_interval_covers_the_true_rate_at_least_95_times_in_100(n, p):
    source = random.Random(f"{n}:{p}")
    draws, covered = 1500, 0
    for _ in range(draws):
        k = sum(source.random() < p for _ in range(n))
        low, high = interval(k, n)
        covered += low <= p <= high
    # The exact interval covers at least 95%; the bar leaves room for sampling noise.
    assert covered / draws >= 0.94


@pytest.mark.parametrize("flips", [6, 20, 60])
def test_the_paired_test_rarely_calls_an_unchanged_grader_changed(flips):
    source = random.Random(flips)
    draws, alarms = 1500, 0
    for _ in range(draws):
        fixed = sum(source.random() < 0.5 for _ in range(flips))
        alarms += sign_test(fixed, flips - fixed) < 0.05
    assert alarms / draws <= 0.05


def test_the_paired_test_sees_a_real_improvement():
    source = random.Random(1)
    hits = 0
    for _ in range(500):
        fixed = sum(source.random() < 0.8 for _ in range(40))  # four fixes for every break
        hits += sign_test(fixed, 40 - fixed) < 0.05
    assert hits / 500 > 0.9


@pytest.mark.parametrize("true_rate", [0.0, 0.1, 0.4])
def test_a_grader_with_a_set_leak_rate_is_measured_at_that_rate(items, true_rate):
    def leaky(item, answer):
        if answer == item["reference"]:
            return True
        # A fixed coin per answer, so the grader is deterministic and the rate is known.
        coin = int(hashlib.sha256(f"{item['id']}|{answer}".encode()).hexdigest(), 16) % 10_000
        return coin < true_rate * 10_000

    report = check(items, leaky)
    must_fail = [o for o in report.outcomes if o.control.expect == FAIL]
    exact = sum(1 for o in must_fail if o.passed) / len(must_fail)
    overall = report.summary["overall"]
    assert overall["rate"] == exact
    assert overall["low"] <= true_rate <= overall["high"]
    assert len(report.leaks) == overall["k"]
