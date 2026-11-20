"""One test per defect found by an independent review of the control builders
and the analysis. Each case is an input where a control's claim was false, or
a number was wrong, before the fix."""

import json
import math

import pytest

from knownbad import build, check, python_grader, run, summarise
from knownbad.cache import Cache, fingerprint
from knownbad.cli import main
from knownbad.controls import prose_edits
from knownbad.grader import to_verdict
from knownbad.model import FAIL, Item
from knownbad.report.html import render
from knownbad.text import may_answer


def controls_of(items, family):
    return [c for c in build(items) if c.family == family]


def item(ref, id="a", input="Question?", **more):
    return Item(id=id, input=input, reference=ref, **more)


# 1. Two flips in one sentence can restore the meaning.
@pytest.mark.parametrize(
    "reference",
    [
        "Shipping is not included.",
        "The store is not open on Sundays.",
        "A higher temperature gives a faster reaction.",
    ],
)
def test_a_sentence_gets_at_most_one_flip(reference):
    chain = prose_edits.flip(item(reference), seed=0)
    assert len(chain) == 1
    changed = sum(a != b for a, b in zip(chain[0].answer.split(), reference.split(), strict=False))
    assert changed >= 1 and len(prose_edits.flippable(reference)) >= 2


def test_cant_and_the_noun_can_are_left_alone():
    text = "You can't return opened food. Recycle the can at any store."
    assert prose_edits.flip(item(text), seed=0) == []
    assert prose_edits.contradict(item(text), seed=0) == []
    assert prose_edits.flip(item("You can return it."), seed=0)[0].answer == "You cannot return it."


# 2. A hedged or bounded number is still right when it moves a little.
@pytest.mark.parametrize(
    "reference",
    ["About 300 million", "More than 100 countries", "Roughly 1,000", "1. Paris", "~40 hours"],
)
def test_a_hedged_number_is_never_called_wrong(reference):
    pool = [item(reference), item("The tent is green and sleeps two people.", id="b")]
    assert all(c.expect != FAIL for c in controls_of(pool, "numbers") if c.item_id == "a")


def test_a_plain_number_answer_is_still_called_wrong():
    pool = [item("14 days"), item("The tent is green.", id="b")]
    assert [c.expect for c in controls_of(pool, "numbers") if c.item_id == "a"] == [FAIL]


# 3. A donor that could be a right answer is refused.
@pytest.mark.parametrize(
    ("own", "other"),
    [
        (
            "You can return the tent to any store or by mail within thirty days of purchase, "
            "provided you have the original receipt and packaging.",
            "You have thirty days.",
        ),
        ("1000", "1,000"),
        ("Two", "2"),
        ("True", "Yes"),
        ("Au", "The symbol is Au."),
    ],
)
def test_a_donor_that_may_answer_the_item_is_not_used(own, other):
    assert may_answer(other, own) and may_answer(own, other)
    pool = [item(own, id="a"), item(other, id="b")]
    assert controls_of(pool, "transplant") == []


def test_every_accepted_answer_of_an_item_rules_a_donor_out():
    pool = [
        item("2", id="a", meta={"accepted": ["two"]}),
        item("two", id="b"),
        item("Gift cards are valid for years.", id="c"),
    ]
    donors = {c.item_id: c.answer for c in controls_of(pool, "transplant")}
    assert donors["a"] == "Gift cards are valid for years."


# 4. A rubric that states the answer is not echoed as a wrong answer.
@pytest.mark.parametrize(
    ("reference", "rubric"),
    [
        ("Yes", "The answer must say yes."),
        ("Paris has been the capital since 987 and remains the largest city.", "Must name Paris."),
    ],
)
def test_no_rubric_echo_when_the_rubric_states_the_answer(reference, rubric):
    pool = [item(reference, rubric=rubric), item("Green.", id="b", rubric="Be polite.")]
    assert [c for c in controls_of(pool, "rubric-echo") if c.item_id == "a"] == []


# 5. JSON string values are never swapped among themselves.
def test_json_strings_are_not_replaced_by_their_siblings():
    reference = '{"labels": ["red", "blue"]}'
    for seed in range(8):
        chain = [c for c in build([item(reference)], seed=seed) if c.family == "json-value"]
        for control in chain:
            labels = json.loads(control.answer)["labels"]
            assert sorted(labels) != ["blue", "red"]
            assert all(x in ("red", "blue") or x.endswith("(other)") for x in labels)


def test_json_nan_is_not_counted_as_a_changed_value():
    chain = [c for c in build([item('{"x": NaN, "y": 1}')]) if c.family == "json-value"]
    assert [c.edits for c in chain] == [1]
    assert json.loads(chain[0].answer)["y"] != 1


# 6. A score is never compared with a pass share.
def test_order_check_compares_like_with_like():
    pool = [
        item("One fact here. Two facts here. Three facts here.", id="a"),
        item("Other thing. Another thing. Third thing.", id="b"),
    ]

    def grade(it, answer):
        return True if answer == it["reference"] else {"score": 3}

    summary = summarise(
        run(build(pool), {i.id: i for i in pool}, python_grader(grade, pass_score=5))
    )
    assert summary["order"]["k"] == 0


# 7. The cache fingerprint follows a grader given as a module name.
def test_the_fingerprint_follows_an_importable_module(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    module = tmp_path / "kb_review_grader.py"
    module.write_text("def grade(item, answer):\\n    return True\\n")
    before = fingerprint("kb_review_grader:grade", None, 0.5)
    module.write_text("def grade(item, answer):\\n    return False\\n")
    assert fingerprint("kb_review_grader:grade", None, 0.5) != before


# 8. The contradiction control's claim is checked.
def test_a_contradiction_scored_above_the_reference_is_a_violation():
    pool = [item("It costs 4 euros. It ships in 3 days.")]

    def longer_is_better(it, answer):
        return {"passed": True, "score": 0.9 if len(answer) > len(it["reference"]) else 0.6}

    summary = check(pool, longer_is_better).summary
    assert "a::contradict" in summary["order"]["violations"]


# 9. Errors on the references, or on most controls, void the run.
def test_a_grader_that_errors_on_every_reference_voids_the_run(items):
    def grade(it, answer):
        if answer == it["reference"]:
            raise RuntimeError("down")
        return False

    report = check(items, grade)
    assert report.void and "reference answers got a verdict" in report.summary["void"]


def test_a_run_with_mostly_no_verdicts_is_void(items):
    def grade(it, answer):
        if answer in (it["reference"], ""):
            return answer == it["reference"]
        raise RuntimeError("down")

    report = check(items, grade)
    assert report.void and "no verdict for" in report.summary["void"]


# 10. A score that is not a number is an error, and never reaches a file.
@pytest.mark.parametrize(
    "raw", [float("nan"), float("inf"), {"score": float("nan"), "passed": True}]
)
def test_a_non_finite_score_is_an_error(raw):
    verdict = to_verdict(raw, 0.5)
    assert verdict.passed is None and "not a number" in verdict.error


def test_the_report_of_a_grader_with_broken_scores_is_still_valid_json(items):
    def grade(it, answer):
        return {"score": math.nan, "passed": answer == it["reference"]}

    assert "NaN" not in render(check(items[:3], grade).to_result())


# 11. A reference given as an object stays JSON.
def test_non_string_fields_are_written_as_json():
    loaded = Item.from_dict(
        {"id": "j", "input": "Extract", "reference": {"city": "Rome", "ok": True}}
    )
    assert loaded.reference == '{"city": "Rome", "ok": true}'
    assert {"json-value", "json-drop"} <= {c.family for c in build([loaded])}
    assert Item.from_dict({"id": "t", "input": "q", "reference": True}).reference == "true"


# 12. Unusual input does not crash.
def test_unusual_input_is_handled(tmp_path, capsys):
    assert prose_edits.flip(item("MİNİMUM order is 5. The shop İS NOT open."), seed=0) is not None

    cache_file = tmp_path / "c.jsonl"
    cache_file.write_text('{"key":"k","verdict":null}\\n')
    assert Cache(cache_file, "g").get("k") is None

    bad = tmp_path / "arr.json"
    bad.write_text("[]")
    assert main(["report", str(bad)]) == 2
    assert "not a knownbad result file" in capsys.readouterr().err


def test_an_unknown_level_in_a_limit_is_refused(items_path, graders_path, capsys):
    code = main(
        ["run", items_path, "--grader", f"{graders_path}:loose", "-q", "--max-leak-level", "7=0"]
    )
    assert code == 2 and "no level '7'" in capsys.readouterr().err


def test_no_echo_when_the_question_contains_the_answer():
    pool = [
        item("She goes to school.", input="Correct the grammar if needed: 'She goes to school.'"),
        item("The tent is green.", id="b"),
    ]
    assert [c.item_id for c in controls_of(pool, "echo")] == ["b"]
