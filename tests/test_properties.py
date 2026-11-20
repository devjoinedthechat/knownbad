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


@given(st.integers(1, 400).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_the_interval_always_contains_the_observed_rate(pair):
    k, n = pair
    low, high = interval(k, n)
    assert 0.0 <= low <= k / n <= high <= 1.0
