import json

from knownbad import build, python_grader, run, summarise
from knownbad.controls import structured
from knownbad.model import FAIL, NOT_HIGHER, Item
from knownbad.report.html import render

INVOICE = (
    '{"vendor": "Tallow & Pine", "total": 184.5, "currency": "EUR", "paid": false, "lines": 3}'
)
ORDER = '{\n  "customer": "Ada Okafor",\n  "items": ["tent", "stove"],\n  "express": true\n}'
ITEMS = [
    Item(id="invoice", input="Extract the invoice fields.", reference=INVOICE),
    Item(id="order", input="Extract the order.", reference=ORDER),
    Item(id="count", input="How many lines?", reference='{"lines": 3}'),
    Item(id="prose", input="When?", reference="Within 30 days. Refunds take 5 days."),
]


def by_family(controls, item_id):
    out = {}
    for control in controls:
        if control.item_id == item_id:
            out.setdefault(control.family, []).append(control)
    return out


def test_json_references_are_recognised_and_prose_is_not():
    assert structured.parse(INVOICE)["total"] == 184.5
    assert structured.parse(" [1, 2] ") == [1, 2]
    for not_json in (None, "", "Within 30 days.", "{broken", "{}", "[]", "3", '"text"'):
        assert structured.parse(not_json) is None


def test_json_items_get_json_edits_and_prose_items_keep_prose_edits():
    controls = build(ITEMS)
    invoice, prose = by_family(controls, "invoice"), by_family(controls, "prose")
    assert {"json-truncated", "json-value", "json-drop"} <= set(invoice)
    assert not {"splice", "numbers"} & set(invoice)
    assert {"splice", "numbers"} <= set(prose) and not any(f.startswith("json") for f in prose)


def test_value_edits_keep_structure_and_type_and_change_the_stated_count():
    reference = json.loads(INVOICE)
    chain = by_family(build(ITEMS), "invoice")["json-value"]
    previous = 0
    for control in chain:
        edited = json.loads(control.answer)
        assert list(edited) == list(reference)
        changed = [k for k in reference if edited[k] != reference[k]]
        assert len(changed) == control.edits > previous
        assert all(type(edited[k]) is type(reference[k]) for k in reference)
        assert control.expect == NOT_HIGHER
        previous = len(changed)
    assert chain[-1].dose == 1.0
    assert chain[0].base == "invoice::reference" and chain[1].base == chain[0].id


def test_a_single_value_changed_is_wrong_and_all_fields_dropped_is_wrong():
    controls = build(ITEMS)
    (only,) = by_family(controls, "count")["json-value"]
    assert only.expect == FAIL and json.loads(only.answer)["lines"] != 3
    drops = by_family(controls, "invoice")["json-drop"]
    assert [len(json.loads(c.answer)) for c in drops] == [3, 2, 1, 0]
    assert [c.expect for c in drops] == [NOT_HIGHER, NOT_HIGHER, NOT_HIGHER, FAIL]


def test_truncated_json_does_not_parse_and_keeps_the_reference_layout():
    controls = build(ITEMS)
    cut = by_family(controls, "order")["json-truncated"][0]
    assert cut.expect == FAIL and structured.parse(cut.answer) is None
    assert ORDER.startswith(cut.answer)
    assert "\n  " in by_family(controls, "order")["json-value"][0].answer
    assert "\n" not in by_family(controls, "invoice")["json-value"][0].answer


def test_a_field_by_field_grader_is_measured_end_to_end():
    def most_fields(item, answer):
        try:
            got, want = json.loads(answer), json.loads(item["reference"])
        except ValueError:
            return item["reference"] == answer
        if not isinstance(got, dict) or not isinstance(want, dict):
            return False
        same = sum(1 for key in want if got.get(key) == want[key])
        return {"passed": same / len(want) >= 0.6, "score": same / len(want)}

    items = [i for i in ITEMS if i.id != "prose"]
    outcomes = run(build(items), {i.id: i for i in items}, python_grader(most_fields))
    summary = summarise(outcomes)
    assert summary["references"]["rate"] == 1.0 and summary["order"]["k"] == 0
    assert set(summary["dose"]) == {"json-value", "json-drop"}
    assert summary["dose"]["json-value"]["points"][1]["rate"] > 0  # one wrong value still passes

    from knownbad.cli import make_result

    page = render(make_result(outcomes, {i.id: i for i in items}, "most_fields"))
    assert "Values threshold" in page and "Fields threshold" in page
    assert "3 values →" in page and ">truncated<" in page
