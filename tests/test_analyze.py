import itertools
import threading

from knownbad import build, gate, python_grader, run, summarise
from knownbad.model import FAIL, Item


def summary_for(items, function, **kwargs):
    by_id = {i.id: i for i in items}
    return summarise(run(build(items), by_id, python_grader(function), **kwargs))


def test_a_grader_that_passes_everything_leaks_everything(items):
    summary = summary_for(items, lambda item, answer: True)
    assert summary["overall"]["rate"] == 1.0
    assert summary["references"]["rate"] == 1.0
    assert summary["void"] is None
    assert all(curve["threshold"] is None for curve in summary["dose"].values())
    assert len(summary["leaks"]) == summary["overall"]["n"]


def test_a_grader_that_fails_everything_voids_the_run(items):
    summary = summary_for(items, lambda item, answer: False)
    assert summary["overall"]["rate"] == 0.0
    assert "reference" in summary["void"]
    assert gate(summary, None, {}) == [f"void: {summary['void']}"]


def test_an_exact_grader_leaks_nothing_and_catches_the_smallest_dose(items):
    summary = summary_for(items, lambda item, answer: answer == item["reference"])
    assert summary["overall"]["k"] == 0 and summary["void"] is None
    assert summary["order"]["k"] == 0
    assert summary["dose"]["numbers"]["threshold"] == [0.0, 0.25]
    assert all(row["turned"] == 0 for row in summary["lift"])


def test_errors_are_never_counted_as_caught(items):
    def flaky(item, answer):
        if "sorry" in answer:
            raise TimeoutError("boom")
        return answer == item["reference"]

    summary = summary_for(items, flaky)
    refusal = next(r for r in summary["families"] if r["family"] == "empty")
    assert summary["errors"] == len(items)
    assert not any(r["family"] == "refusal" for r in summary["families"])
    assert refusal["n"] == len(items)
    assert summary["overall"]["n"] == summary["graded"] - summary["references"]["n"] - sum(
        1 for c in build(items) if c.expect not in (FAIL, "pass")
    )


def test_all_errors_is_void(items):
    def broken(item, answer):
        raise RuntimeError("no key")

    summary = summary_for(items, broken)
    assert summary["void"] and summary["graded"] == 0
    assert summary["error_examples"][0]["error"].startswith("RuntimeError")


def test_order_violation_is_found_when_an_edit_scores_higher():
    pool = [
        Item(id="a", input="q", reference="One fact here. Two facts here. Three facts here."),
        Item(id="b", input="q", reference="Other thing. Another thing. Third thing."),
    ]

    def longer_is_worse(item, answer):  # rewards answers that lost reference sentences
        kept = sum(1 for s in item["reference"].split(". ") if s.rstrip(".") in answer)
        return {"passed": True, "score": 1.0 - kept / 10}

    summary = summary_for(pool, longer_is_worse)
    assert summary["order"]["k"] > 0
    assert any("::splice@" in v for v in summary["order"]["violations"])


def test_dressing_lift_counts_answers_turned_into_passes(items):
    summary = summary_for(
        items, lambda item, answer: "Verified" in answer or answer == item["reference"]
    )
    lift = {row["dressing"]: row for row in summary["lift"]}
    assert lift["authority"]["turned"] == lift["authority"]["pairs"] == len(items)
    assert lift["authority"]["lift"] == 1.0
    assert lift["padding"]["turned"] == 0


def test_trials_use_the_majority_and_report_flaky_controls():
    pool = [Item(id="a", input="q", reference="right"), Item(id="b", input="q", reference="other")]
    lock = threading.Lock()
    counter = itertools.count()

    def two_of_three(item, answer):
        if answer == item["reference"]:
            return True
        if answer == "":
            with lock:
                return next(counter) % 3 != 0  # passes two of every three calls
        return False

    summary = summary_for(pool, two_of_three, trials=3, workers=1)
    empty = next(r for r in summary["families"] if r["family"] == "empty")
    assert empty["k"] == 2 and empty["flaky"] == 2


def test_gate_limits(items):
    summary = summary_for(
        items, lambda item, answer: "Verified" in answer or answer == item["reference"]
    )
    assert gate(summary, None, {}) == []
    assert gate(summary, 1.0, {}) == []
    assert len(gate(summary, 0.0, {})) == 1
    reasons = gate(summary, None, {"0": 0.0, "2": 0.1})
    assert len(reasons) == 1 and reasons[0].startswith("level 2")


def test_every_rate_says_how_many_items_stand_behind_it(items):
    summary = summary_for(items, lambda item, answer: answer == item["reference"])
    overall = summary["overall"]
    assert overall["items"] == len(items) < overall["n"]
    # No leak in 288 controls would read as "under 1.3%"; from 24 items it is "under 14%".
    assert overall["k"] == 0 and 0.13 < overall["high"] < 0.15
    assert all(row["items"] <= len(items) for row in summary["families"] + summary["profile"])
