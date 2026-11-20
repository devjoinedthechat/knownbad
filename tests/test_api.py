import itertools
import threading

import pytest

from knownbad import build, check
from knownbad.model import Item


def loose(item, answer):
    return "Verified" in answer or answer == item["reference"]


def test_check_gives_a_report_a_test_can_assert_on(items):
    report = check(items, loose)
    assert not report.void
    assert report.leak_rate() == pytest.approx(24 / 288)
    assert report.leak_rate(2) == pytest.approx(24 / 96) and report.leak_rate("0") == 0.0
    assert report.leak_rate(4) == 0.0  # no controls of that level
    assert {c.family for c in report.leaks} == {"transplant+authority"}
    assert report.threshold("numbers") == (0.0, 0.25)
    with pytest.raises(KeyError):
        report.threshold("json-value")
    assert "transplant+authority" in str(report) and report.grader == "loose"
    assert report.to_html().startswith("<!doctype html>")


def test_check_takes_plain_dicts_and_frozen_controls():
    rows = [
        {"id": "a", "input": "How many days?", "reference": "Within 30 days. No fee applies."},
        {"id": "b", "input": "What fee?", "reference": "The fee is 4 euros. It is taken at once."},
    ]
    frozen = build([Item.from_dict(r) for r in rows], seed=7)
    report = check(rows, lambda item, answer: True, controls=frozen)
    assert len(report.outcomes) == len(frozen) and report.leak_rate() == 1.0
    assert report.threshold("splice") is None  # never fails half
    assert check(rows, lambda item, answer: False).void


def test_repeated_trials_report_how_often_the_verdict_was_the_same(items):
    lock, calls = threading.Lock(), itertools.count()

    def coin_on_echo(item, answer):
        if answer == item["input"]:
            with lock:
                return next(calls) % 2 == 0
        return answer == item["reference"]

    report = check(items, coin_on_echo, trials=2, workers=1)
    same = report.summary["consistency"]
    assert same["n"] == len(report.outcomes)
    assert len(same["split"]) == len(items) and all("::echo" in i for i in same["split"])
    assert (
        "Same verdict every trial" in str(report) and "Same verdict every trial" in report.to_html()
    )
    assert check(items, loose).summary["consistency"]["n"] == 0
