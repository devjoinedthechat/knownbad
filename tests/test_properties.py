"""Invariants the control builders must hold for any items, not just the examples."""

from hypothesis import given, settings
from hypothesis import strategies as st

from knownbad.controls import build
from knownbad.model import FAIL, NOT_HIGHER, PASS, Control, Item
from knownbad.stats import interval
from knownbad.text import bump_number, normalise, numbers

words = st.sampled_from(
    "refund order tent days euros parcel carrier warranty returns within after the a of to "
    "is are ship weeks hours cost fee free checkout".split()
)
number = st.one_of(
    st.integers(0, 99999).map(str),
    st.integers(1000, 9999999).map(lambda n: f"{n:,}"),
    st.tuples(st.integers(0, 999), st.integers(0, 99)).map(lambda p: f"{p[0]}.{p[1]:02d}"),
)
sentence = st.lists(st.one_of(words, number), min_size=1, max_size=9).map(
    lambda parts: " ".join(parts).capitalize() + "."
)
reference = st.one_of(st.none(), st.lists(sentence, min_size=1, max_size=5).map(" ".join))
rubric = st.one_of(st.none(), st.just("Must agree with the reference."), sentence)


@st.composite
def item_sets(draw):
    count = draw(st.integers(1, 7))
    return [
        Item(
            id=f"item-{n}",
            input=draw(sentence),
            reference=draw(reference),
            rubric=draw(rubric),
            meta={"abstain_ok": True} if draw(st.booleans()) else {},
        )
        for n in range(count)
    ]


@given(item_sets(), st.integers(0, 3))
@settings(max_examples=150, deadline=None)
def test_builders_hold_their_invariants(items, seed):
    controls = build(items, seed=seed)
    assert [c.to_dict() for c in controls] == [c.to_dict() for c in build(items, seed=seed)]

    by_id = {c.id: c for c in controls}
    assert len(by_id) == len(controls)
    item = {i.id: i for i in items}
    for control in controls:
        own = item[control.item_id]
        assert Control.from_dict(control.to_dict()) == control
        assert control.how
        if control.base is not None:
            assert by_id[control.base].item_id == control.item_id
        if control.expect == NOT_HIGHER:
            assert control.base in by_id
            if control.family != "contradict":  # one edit, not a dose chain
                assert control.dose is not None and 0 < control.dose <= 1
        if control.expect == PASS:
            assert control.answer == own.reference
        if control.expect == FAIL and own.reference is not None:
            assert normalise(control.answer) != normalise(own.reference)
        if control.family == "refusal":
            assert not own.meta.get("abstain_ok")
        if control.family in ("transplant", "splice", "numbers", "reference"):
            assert own.reference
        if control.family == "numbers":
            before = [m.group() for m in numbers(own.reference)]
            after = [m.group() for m in numbers(control.answer)]
            assert len(before) == len(after)
            assert sum(a != b for a, b in zip(before, after, strict=True)) == control.edits


@given(number, st.integers(0, 10_000))
def test_a_bumped_number_is_a_different_number_in_the_same_notation(literal, seed):
    import random

    changed = bump_number(literal, random.Random(seed))
    assert changed != literal
    assert len(numbers(changed)) == 1 and numbers(changed)[0].group() == changed
    assert ("." in changed) == ("." in literal)


# A correctness property, not a speed one: under coverage on a loaded machine
# one call took 443 ms and its retry 76 ms, so the default deadline is noise.
@settings(deadline=None)
@given(st.integers(1, 400).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_the_interval_always_contains_the_observed_rate(pair):
    k, n = pair
    low, high = interval(k, n)
    assert 0.0 <= low <= k / n <= high <= 1.0


tool_names = st.sampled_from(["get_order", "refund_order", "cancel_order", "send_email", "note"])
arg_value = st.one_of(
    st.booleans(),
    st.integers(-50, 5000),
    st.floats(0, 500, allow_nan=False).map(lambda f: round(f, 2)),
    st.sampled_from(["A-1", "A-2", "C-9", "warranty", "Leave it by the door.", "", "é"]),
    st.none(),
    st.lists(st.sampled_from(["x", "y", 3]), max_size=2),
    st.dictionaries(st.sampled_from(["k", "j"]), st.sampled_from(["A-7", 4, True]), max_size=2),
)
run_call = st.fixed_dictionaries(
    {
        "tool": tool_names,
        "args": st.dictionaries(st.sampled_from(["order_id", "amount", "flag", "text"]), arg_value),
    },
    optional={
        "result": st.one_of(st.just({"ok": True}), st.just("saved"), st.just({"error": "x"}))
    },
)


@st.composite
def run_sets(draw):
    made = []
    for n in range(draw(st.integers(1, 5))):
        calls = draw(st.lists(run_call, min_size=1, max_size=5))
        used = sorted({c["tool"] for c in calls})
        required = draw(st.lists(st.sampled_from(used), unique=True, max_size=len(used)))
        reference = {"calls": calls}
        if draw(st.booleans()):
            reference["final"] = "All done."
        made.append(
            Item.from_dict(
                {
                    "id": f"run-{n}",
                    "kind": "run",
                    "input": f"Task {n}.",
                    "required_tools": required,
                    "reference": reference,
                }
            )
        )
    return made


@given(run_sets(), st.integers(0, 3))
@settings(max_examples=200, deadline=None)
def test_run_controls_hold_their_invariants(items, seed):
    import json

    controls = build(items, seed=seed)
    assert [c.to_dict() for c in controls] == [c.to_dict() for c in build(items, seed=seed)]
    by_id = {c.id: c for c in controls}
    assert len(by_id) == len(controls)
    item = {i.id: i for i in items}

    def key(call):
        return json.dumps([call["tool"], call.get("args", {})], sort_keys=True)

    def failed(result):
        if isinstance(result, dict):
            return "error" in result
        return isinstance(result, str) and result.startswith("Error")

    for control in controls:
        if not control.family.startswith("run-"):
            continue
        own = item[control.item_id]
        wanted = json.loads(own.reference)
        got = json.loads(control.answer)
        required = set(own.meta["required_tools"])
        assert got != wanted and got.get("final") == wanted.get("final")
        assert control.base is None or control.base in by_id
        if control.expect == NOT_HIGHER:
            assert control.base in by_id
        needed = [c for c in wanted["calls"] if c["tool"] in required]
        if control.family != "run-extra-action":
            # Nothing is claimed about a reference whose required call failed.
            assert needed and not any(failed(c.get("result")) for c in needed)
        if control.family == "run-no-action":
            assert control.expect == FAIL
            assert [c for c in wanted["calls"] if c["tool"] not in required] == got["calls"]
        if control.family == "run-skipped-action":
            assert control.expect == FAIL and len(needed) >= 2
            gone = list(wanted["calls"])
            for call in got["calls"]:
                gone.remove(call)
            ((removed),) = gone
            assert removed["tool"] in required
            assert removed["tool"] not in [c["tool"] for c in got["calls"]]
        if control.family == "run-failed-action":
            assert control.expect == FAIL
            changed = [(a, b) for a, b in zip(wanted["calls"], got["calls"], strict=True) if a != b]
            ((before, after),) = changed
            assert before["tool"] in required and key(before) == key(after)
            assert failed(after["result"])
            assert sum(c["tool"] == before["tool"] for c in wanted["calls"]) == 1
        if control.family == "run-args":
            assert control.expect == NOT_HIGHER and control.base == f"{own.id}::reference"
            assert [c["tool"] for c in got["calls"]] == [c["tool"] for c in wanted["calls"]]
            for before, after in zip(wanted["calls"], got["calls"], strict=True):
                assert before.get("result") == after.get("result")
                if before["tool"] not in required:
                    assert before == after
        if control.family == "run-extra-action":
            assert control.expect == NOT_HIGHER
            assert got["calls"][:-1] == wanted["calls"]
            assert key(got["calls"][-1]) not in [key(c) for c in wanted["calls"]]
            assert not failed(got["calls"][-1].get("result"))
