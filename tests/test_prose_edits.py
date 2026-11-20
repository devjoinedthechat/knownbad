from knownbad import build, check
from knownbad.controls import prose_edits
from knownbad.model import NOT_HIGHER, Item
from knownbad.text import sentences

REFUND = Item(
    id="refund",
    input="How long do I have to return a tent?",
    reference="You can return a tent within 30 days of delivery. It must be dry. "
    "Refunds reach your card in 5 to 7 working days.",
)
PLAIN = Item(id="plain", input="What colour?", reference="The tent is green.")


def test_drop_removes_sentences_adds_nothing_and_never_empties_the_answer():
    own = sentences(REFUND.reference)
    chain = prose_edits.drop(REFUND, seed=0)
    assert [c.edits for c in chain] == [1, 2]
    kept_before = set(own)
    for control in chain:
        kept = sentences(control.answer)
        assert set(kept) < kept_before and all(s in own for s in kept) and kept
        assert control.expect == NOT_HIGHER
        kept_before = set(kept)
    assert chain[0].base == "refund::reference" and chain[1].base == chain[0].id
    assert prose_edits.drop(PLAIN, seed=0) == []


def test_flip_turns_words_into_their_opposite_and_keeps_capitals():
    chain = prose_edits.flip(REFUND, seed=0)
    assert [c.edits for c in chain] == [1, 2, 3]
    last = chain[-1].answer
    assert last.startswith("You cannot return a tent within 30 weeks")
    assert last.endswith("working weeks.")
    cases = {
        "Never ship before Monday.": "Always ship after Monday.",
        "It must not be washed.": "It must be washed.",
        "Fees are not refunded.": "Fees are refunded.",
        "At least 3 months.": "At most 3 years.",
        "The cannery is canned.": None,  # 'can' inside a word is left alone
    }
    for text, want in cases.items():
        got = prose_edits.flip(Item(id="x", input="q", reference=text), seed=0)
        assert (got[-1].answer if got else None) == want
    assert prose_edits.flip(PLAIN, seed=0) == []


def test_contradict_keeps_the_reference_and_adds_one_altered_sentence():
    (control,) = prose_edits.contradict(REFUND, seed=0)
    assert control.answer.startswith(REFUND.reference)
    added = control.answer[len(REFUND.reference) :].strip()
    own = sentences(REFUND.reference)
    assert added not in own and any(
        sum(a != b for a, b in zip(added.split(), s.split(), strict=False)) == 1
        and len(added.split()) == len(s.split())
        for s in own
    )
    assert control.expect == NOT_HIGHER and control.base == "refund::reference"
    assert prose_edits.contradict(PLAIN, seed=0) == []


def test_the_profile_tells_a_gist_reader_from_a_close_reader(items):
    def gist(item, answer):  # passes anything that shares most words with the reference
        want = set(item["reference"].lower().split())
        return len(want & set(answer.lower().split())) / len(want) >= 0.7

    profile = {row["family"]: row for row in check(items, gist).summary["profile"]}
    assert set(profile) == {"drop", "splice", "numbers", "flip", "contradict"}
    assert profile["contradict"]["rate"] == 1.0 and profile["flip"]["rate"] > 0.9
    close = check(items, lambda item, answer: answer == item["reference"]).summary["profile"]
    assert all(row["k"] == 0 for row in close)
    text = str(check(items, gist))
    assert "What it notices" in text and "self-contradiction" in text


def test_new_families_are_built_for_prose_and_not_for_json():
    controls = build([REFUND, PLAIN, Item(id="j", input="q", reference='{"a": 1, "b": 2}')])
    families = {}
    for control in controls:
        families.setdefault(control.item_id, set()).add(control.family)
    assert {"drop", "flip", "contradict"} <= families["refund"]
    assert not {"drop", "flip", "contradict"} & families["j"]
