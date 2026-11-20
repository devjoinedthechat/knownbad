import sys

import pytest

from knownbad.grader import command_grader, load_callable, python_grader, to_verdict
from knownbad.model import Item, Verdict

ITEM = Item(id="a", input="q", reference="r")


@pytest.mark.parametrize(
    ("raw", "passed", "score"),
    [
        (True, True, None),
        (False, False, None),
        (0.7, True, 0.7),
        (0.2, False, 0.2),
        (1, True, 1.0),
        ("PASS", True, None),
        ("incorrect", False, None),
        ({"passed": False, "score": 0.9}, False, 0.9),
        ({"score": 0.9}, True, 0.9),
        ({"pass": "fail"}, False, None),
        (Verdict(passed=True, score=1.0), True, 1.0),
    ],
)
def test_to_verdict_reads_the_usual_shapes(raw, passed, score):
    verdict = to_verdict(raw, pass_score=0.5)
    assert (verdict.passed, verdict.score, verdict.error) == (passed, score, None)


@pytest.mark.parametrize("raw", ["maybe", {"explanation": "hm"}, None, ["x"]])
def test_an_unreadable_verdict_is_an_error_not_a_fail(raw):
    verdict = to_verdict(raw, pass_score=0.5)
    assert verdict.passed is None and verdict.error


def test_a_grader_that_raises_is_an_error_not_a_fail():
    def broken(item, answer):
        raise RuntimeError("rate limited")

    verdict = python_grader(broken)(ITEM, "x")
    assert verdict.passed is None and "rate limited" in verdict.error


def test_python_grader_gets_a_plain_dict():
    seen = {}

    def grade(item, answer):
        seen.update(item)
        return answer == item["reference"]

    assert python_grader(grade)(ITEM, "r").passed is True
    assert seen["id"] == "a" and seen["meta"] == {}


def test_load_callable_from_file_and_bad_specs(graders_path):
    assert load_callable(f"{graders_path}:exact")({"reference": "r"}, "r") is True
    for spec in ("nocolon", f"{graders_path}:missing", "missing_file.py:f"):
        with pytest.raises(ValueError):
            load_callable(spec)


def test_command_grader_round_trip_and_failures():
    script = (
        "import json,sys; d=json.load(sys.stdin); print('log line'); "
        "print(json.dumps({'passed': d['answer']==d['item']['reference'], 'explanation': 'x'}))"
    )
    grade = command_grader(f'{sys.executable} -c "{script}"')
    assert grade(ITEM, "r").passed is True
    assert grade(ITEM, "nope").passed is False
    assert grade(ITEM, "r").explanation == "x"

    crashed = command_grader(f'{sys.executable} -c "import sys; sys.exit(3)"')(ITEM, "r")
    assert crashed.passed is None and "exit 3" in crashed.error
    silent = command_grader(f'{sys.executable} -c "pass"')(ITEM, "r")
    assert silent.passed is None
    slow = command_grader(f'{sys.executable} -c "import time; time.sleep(5)"', timeout=0.3)(
        ITEM, "r"
    )
    assert slow.passed is None and "timed out" in slow.error
    word = command_grader(f"{sys.executable} -c \"print('pass')\"")(ITEM, "r")
    assert word.passed is True
