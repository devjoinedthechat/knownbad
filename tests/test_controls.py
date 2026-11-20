import pytest

from knownbad.controls import FAMILIES, build
from knownbad.model import FAIL, NOT_HIGHER, PASS, Item
from knownbad.text import normalise, numbers, same_answer, sentences


def by_family(controls, family):
    return [c for c in controls if c.family == family]


def test_build_is_deterministic_and_seeded(items):
    first = [c.to_dict() for c in build(items, seed=0)]
    assert first == [c.to_dict() for c in build(items, seed=0)]
    assert first != [c.to_dict() for c in build(items, seed=1)]


def test_ids_are_unique_and_every_family_is_known(items):
    controls = build(items)
    assert len({c.id for c in controls}) == len(controls)
    assert {c.family for c in controls} <= set(FAMILIES)


def test_every_item_gets_its_reference_as_a_must_pass(items):
    refs = by_family(build(items), "reference")
    assert len(refs) == len(items)
    assert all(c.expect == PASS for c in refs)


def test_no_must_fail_control_reads_as_the_reference(items):
    reference = {i.id: i.reference for i in items}
    for control in build(items):
        if control.expect == FAIL:
            assert normalise(control.answer) != normalise(reference[control.item_id])


def test_transplant_is_another_items_reference_and_not_the_same_answer(items):
    references = {i.reference for i in items}
    own = {i.id: i.reference for i in items}
    for control in by_family(build(items), "transplant"):
        assert control.answer in references
        assert not same_answer(control.answer, own[control.item_id])


def test_transplant_is_skipped_when_every_reference_is_the_same():
    same = [Item(id=str(n), input=f"q{n}", reference="Yes") for n in range(5)]
    assert by_family(build(same), "transplant") == []


def test_dressed_transplants_point_at_the_plain_one(items):
    controls = build(items)
    plain = {c.item_id: c for c in by_family(controls, "transplant")}
    dressed = [c for c in controls if c.family.startswith("transplant+")]
    assert len(dressed) == 3 * len(plain)
    for control in dressed:
        assert control.base == plain[control.item_id].id
        assert plain[control.item_id].answer in control.answer
        assert control.expect == FAIL


def test_splice_doses_are_nested_and_end_with_nothing_left(items):
    own = {i.id: sentences(i.reference) for i in items}
    chains = {}
    for control in by_family(build(items), "splice"):
        chains.setdefault(control.item_id, []).append(control)
    assert chains
    for item_id, chain in chains.items():
        kept_before = set(own[item_id])
        base = f"{item_id}::reference"
        for control in chain:
            kept = set(own[item_id]) & set(sentences(control.answer))
            assert kept < kept_before, "each dose removes more of the reference"
            assert control.base == base
            kept_before, base = kept, control.id
        assert chain[-1].dose == 1.0 and chain[-1].expect == FAIL and not kept_before
        assert all(c.expect == NOT_HIGHER for c in chain[:-1])


def test_number_doses_change_more_numbers_at_each_step(items):
    own = {i.id: [m.group() for m in numbers(i.reference)] for i in items}
    chains = {}
    for control in by_family(build(items), "numbers"):
        chains.setdefault(control.item_id, []).append(control)
    for item_id, chain in chains.items():
        previous = 0
        for control in chain:
            now = [m.group() for m in numbers(control.answer)]
            assert len(now) == len(own[item_id])
            differing = sum(a != b for a, b in zip(now, own[item_id], strict=True))
            assert differing == control.edits > previous
            previous = differing
        assert chain[-1].dose == 1.0


def test_a_reference_that_is_only_a_number_must_fail_once_changed():
    pool = [
        Item(id="a", input="How many days?", reference="3 days"),
        Item(
            id="b",
            input="Where?",
            reference="In the workshop. It takes 10 days and costs 25 euros.",
        ),
    ]
    numbers_controls = {c.item_id: c for c in by_family(build(pool), "numbers") if c.edits == 1}
    assert numbers_controls["a"].expect == FAIL
    assert numbers_controls["b"].expect == NOT_HIGHER


def test_refusal_is_skipped_where_abstaining_is_right():
    pool = [
        Item(id="a", input="q", reference="r one", meta={"abstain_ok": True}),
        Item(id="b", input="q2", reference="r two"),
    ]
    assert [c.item_id for c in by_family(build(pool), "refusal")] == ["b"]


def test_rubric_echo_only_when_the_rubric_holds_no_answer():
    generic = "Be factually consistent with the reference."
    pool = [
        Item(
            id="a",
            input="q",
            reference="Refunds take 14 days.",
            rubric="Must say refunds take 14 days.",
        ),
        Item(id="b", input="q", reference="Boots have a 2 year warranty.", rubric=generic),
        Item(id="c", input="q", reference="Gift cards last 3 years.", rubric=generic),
        Item(id="d", input="q", rubric="Must be polite."),
    ]
    assert sorted(c.item_id for c in by_family(build(pool), "rubric-echo")) == ["b", "c"]


def test_items_without_a_reference_still_get_the_reference_free_controls():
    controls = build(
        [Item(id="a", input="Summarise the call."), Item(id="b", input="Draft a reply.")]
    )
    assert {c.family for c in controls} == {
        "empty",
        "echo",
        "refusal",
        "claim",
        "injection-plain",
        "injection-forged",
    }


def test_skipping_the_reference_drops_the_chains_that_hang_off_it(items):
    controls = build(items, skip=["reference"])
    ids = {c.id for c in controls}
    assert not by_family(controls, "reference")
    assert all(c.base in ids for c in controls if c.base)
    assert all(c.expect != NOT_HIGHER for c in controls)


def test_bad_input_is_refused(items):
    with pytest.raises(ValueError, match="unique"):
        build([items[0], items[0]])
    with pytest.raises(ValueError, match="unknown control family"):
        build(items, skip=["nope"])


def test_a_donor_never_repeats_the_items_own_facts(items):
    # Found by the judge study: "return it within 30 days" from another item is a
    # right answer to "how long do I have to return a tent?", so it is no control.
    reference = {i.id: i.reference for i in items}
    for control in by_family(build(items), "transplant"):
        own = {m.group() for m in numbers(reference[control.item_id])}
        assert not own & {m.group() for m in numbers(control.answer)}

    pool = [
        Item(id="tent", input="How long to return a tent?", reference="Return it within 30 days."),
        Item(
            id="cancel",
            input="Can I cancel?",
            reference="Refuse the parcel or return it within 30 days.",
        ),
        Item(
            id="gift", input="Do gift cards expire?", reference="Gift cards are valid for 3 years."
        ),
    ]
    donors = {c.item_id: c.answer for c in by_family(build(pool), "transplant")}
    assert donors["tent"] == "Gift cards are valid for 3 years."
    assert donors["cancel"] == "Gift cards are valid for 3 years."


def test_no_transplant_when_every_other_item_repeats_the_facts():
    pool = [
        Item(id="a", input="q", reference="Return it within 30 days."),
        Item(id="b", input="q", reference="Send it back inside 30 days of delivery."),
    ]
    assert by_family(build(pool), "transplant") == []
    assert by_family(build(pool), "splice") == []
