"""Controls for agent runs: each one must be wrong for the reason it gives."""

import json
from pathlib import Path

import pytest

from knownbad import check
from knownbad.controls import build, runs
from knownbad.io import read_items
from knownbad.model import FAIL, NOT_HIGHER, Item

EXAMPLE = Path(__file__).parent.parent / "examples" / "agent"


def run_item(item_id, calls, required, final="Done.", **more):
    reference = {"calls": calls}
    if final is not None:
        reference["final"] = final
    return Item.from_dict(
        {
            "id": item_id,
            "kind": "run",
            "input": f"Do {item_id}.",
            "required_tools": required,
            "reference": reference,
            **more,
        }
    )


def call(tool, args=None, result=None):
    made = {"tool": tool, "args": args or {}}
    if result is not None:
        made["result"] = result
    return made


REFUND = run_item(
    "refund",
    [
        call("get_order", {"order_id": "A-1"}, {"total": 40}),
        call("refund_order", {"order_id": "A-1", "amount": 40}, {"ok": True}),
    ],
    ["refund_order"],
    "Order A-1 is refunded.",
)
CANCEL = run_item(
    "cancel",
    [call("cancel_order", {"order_id": "B-9"}, {"ok": True})],
    ["cancel_order"],
    "Order B-9 is cancelled.",
)


def by_family(controls):
    found = {}
    for control in controls:
        found.setdefault(control.family, []).append(control)
    return found


def tools(control):
    return [c["tool"] for c in json.loads(control.answer)["calls"]]


@pytest.fixture(scope="module")
def example():
    return read_items(EXAMPLE / "items.jsonl")


def test_no_action_removes_every_required_call_and_keeps_the_claim():
    (control,) = by_family(build([REFUND, CANCEL]))["run-no-action"][:1]
    run = json.loads(control.answer)
    assert tools(control) == ["get_order"]
    assert run["final"] == "Order A-1 is refunded."
    assert control.expect == FAIL and control.level == "3"


def test_a_failed_action_keeps_the_call_and_turns_its_result_into_an_error():
    control = by_family(build([REFUND, CANCEL]))["run-failed-action"][0]
    run = json.loads(control.answer)
    assert tools(control) == ["get_order", "refund_order"]
    assert run["calls"][1]["result"] == {"error": runs.ERROR}
    assert run["calls"][1]["args"] == {"order_id": "A-1", "amount": 40}
    assert run["calls"][0]["result"] == {"total": 40}
    assert control.expect == FAIL


def test_a_text_result_fails_as_text():
    item = run_item("note", [call("add_note", {"order_id": "A-1"}, "saved")], ["add_note"])
    control = by_family(build([item]))["run-failed-action"][0]
    assert json.loads(control.answer)["calls"][0]["result"] == f"Error: {runs.ERROR}"


def mine(controls, item_id):
    return {c.family for c in controls if c.item_id == item_id and c.family in runs.FAMILIES}


def test_a_reference_whose_required_call_failed_gets_no_claim_about_that_call():
    # "Already refunded, so no second refund was made" is an honest run. Taking
    # the failed call out, or rewording its error, does not make it a wrong one.
    honest = run_item(
        "already",
        [
            call("get_order", {"order_id": "A-1"}, {"status": "refunded"}),
            call("refund_order", {"order_id": "A-1"}, {"error": "already refunded"}),
        ],
        ["refund_order"],
        "Order A-1 was already refunded, so no second refund was made.",
    )
    assert mine(build([honest, CANCEL]), "already") == {"run-extra-action"}


@pytest.mark.parametrize(
    "result",
    [
        {"ok": False},
        {"ok": "false"},
        {"success": False},
        {"status": "failed"},
        {"status": 409},
        {"isError": True, "content": "x"},
        {"is_error": True},
        {"errors": ["x"]},
        {"data": {"error": "x"}},
        [{"error": "x"}],
        "Error: declined",
        "ERROR 500",
        "Failed: already refunded",
        False,
    ],
    ids=str,
)
def test_a_result_that_reads_as_a_failure_is_taken_as_one(result):
    soft = run_item("soft", [call("charge", {"order_id": "A-1"}, result)], ["charge"])
    found = build([soft, CANCEL])
    assert mine(found, "soft") == {"run-extra-action"}
    assert not [c for c in found if c.item_id == "soft" and c.family.startswith("transplant")]
    # A failed call is not handed to another item as its extra action either.
    assert "run-extra-action" not in mine(build([CANCEL, soft]), "cancel")


@pytest.mark.parametrize(
    "result",
    [{"ok": True}, {"error": None}, {"error": 0}, {"status": 200}, {"status": "shipped"}, "saved"],
    ids=str,
)
def test_a_result_that_worked_keeps_its_controls(result):
    fine = run_item("fine", [call("charge", {"order_id": "A-1"}, result)], ["charge"])
    assert {"run-no-action", "run-failed-action"} <= mine(build([fine, CANCEL]), "fine")


@pytest.mark.parametrize(
    "calls",
    [
        [call("charge", {"order_id": "A-1"}, {"ok": True})] * 2,
        [
            call("charge", {"order_id": "A-1", "key": "k1"}, {"ok": True}),
            call("charge", {"order_id": "A-1", "key": "k2"}, {"ok": True}),
        ],
        [
            call("set_status", {"order_id": "A-1", "status": "packed"}, {"ok": True}),
            call("set_status", {"order_id": "A-1", "status": "shipped"}, {"ok": True}),
        ],
    ],
    ids=["the same call twice", "a retry with a new key", "an overwrite"],
)
def test_a_tool_called_twice_is_never_removed_or_failed_one_call_at_a_time(calls):
    # The other call may do the same work, or undo this one. Only removing
    # every call to the tool is certain.
    item = run_item("twice", calls, [calls[0]["tool"]])
    for seed in range(6):
        found = mine(build([item, CANCEL], seed=seed), "twice")
        assert found == {"run-no-action", "run-args", "run-extra-action"}
    (none,) = [c for c in build([item]) if c.family == "run-no-action"]
    assert tools(none) == []


def test_one_of_several_required_calls_is_skipped():
    item = run_item(
        "both",
        [call("refund_order", {"order_id": "A-1"}), call("send_email", {"customer_id": "C-1"})],
        ["refund_order", "send_email"],
    )
    found = by_family(build([item]))
    (skipped,) = found["run-skipped-action"]
    assert len(tools(skipped)) == 1 and skipped.expect == FAIL
    assert tools(found["run-no-action"][0]) == []
    # One required call: skipping it is the no-action control, not a second one.
    assert "run-skipped-action" not in by_family(build([REFUND]))


def test_arguments_change_in_nested_doses_and_only_in_required_calls():
    chain = [c for c in build([REFUND, CANCEL]) if c.id.startswith("refund::run-args")]
    assert [c.edits for c in chain] == [1, 2]
    # Each step is held against the reference: two changed numbers can cancel,
    # so a later step is not certainly worse than an earlier one.
    assert all(c.base == "refund::reference" and c.expect == NOT_HIGHER for c in chain)
    wanted = json.loads(REFUND.reference)["calls"]
    for control in chain:
        got = json.loads(control.answer)["calls"]
        assert got[0] == wanted[0]  # the lookup is not a required call
        changed = sum(got[1]["args"][k] != wanted[1]["args"][k] for k in wanted[1]["args"])
        assert changed == control.edits
        assert got[1]["result"] == wanted[1]["result"]
        assert all(type(got[1]["args"][k]) is type(v) for k, v in wanted[1]["args"].items())


def test_the_smallest_argument_edit_is_always_built():
    many = run_item("many", [call("act", {k: f"V-{k}" for k in "abcdefg"})], ["act"])
    steps = [c.edits for c in build([many, CANCEL]) if c.id.startswith("many::run-args")]
    assert steps[0] == 1 and steps[-1] == 7


def test_an_id_argument_takes_another_items_id():
    (control,) = [c for c in build([CANCEL, REFUND]) if c.family == "run-args" and "cancel" in c.id]
    assert json.loads(control.answer)["calls"][0]["args"] == {"order_id": "A-1"}


@pytest.mark.parametrize(
    "value",
    [True, "A-1", 40, 2.5, "Please leave it with the neighbour."],
    ids=["a flag", "an id", "a number", "a fraction", "free text"],
)
def test_a_changed_argument_is_never_called_wrong_only_not_better(value):
    # run_migration(verbose=true) with the flag off is the same migration.
    item = run_item("one", [call("act", {"x": value})], ["act"])
    (control,) = [c for c in build([item, CANCEL]) if c.family == "run-args" and c.item_id == "one"]
    assert control.expect == NOT_HIGHER and control.base == "one::reference"


def test_free_text_arguments_never_take_an_id_from_another_item():
    item = run_item("say", [call("say", {"text": "Thank you for waiting."})], ["say"])
    (control,) = [c for c in build([item, CANCEL]) if c.family == "run-args" and c.item_id == "say"]
    assert json.loads(control.answer)["calls"][0]["args"]["text"] not in ("B-9", "A-1")


def test_the_extra_action_is_another_items_required_call_and_is_only_not_better():
    control = by_family(build([REFUND, CANCEL]))["run-extra-action"][0]
    assert control.item_id == "refund" and control.expect == NOT_HIGHER
    assert control.base == "refund::reference"
    got = json.loads(control.answer)["calls"]
    assert got[:2] == json.loads(REFUND.reference)["calls"]
    assert got[2] == {"tool": "cancel_order", "args": {"order_id": "B-9"}, "result": {"ok": True}}


def test_a_shared_lookup_tool_does_not_block_a_transplant_but_a_shared_record_does():
    def task(name, order):
        return run_item(
            name,
            [call("get_order", {"order_id": order}), call(f"do_{name}", {"order_id": order})],
            [f"do_{name}"],
        )

    apart = build([task("pack", "A-1"), task("ship", "A-2")])
    assert {c.item_id for c in apart if c.family == "transplant"} == {"pack", "ship"}
    assert {c.item_id for c in apart if c.family == "run-extra-action"} == {"pack", "ship"}
    # The same order under a number: another tool may do this task's work on it.
    together = build([task("pack", 1042), task("ship", 1042)])
    assert not [c for c in together if c.family in ("transplant", "run-extra-action")]


def test_gen_says_which_run_items_got_fewer_controls(tmp_path, capsys):
    from knownbad.cli import main

    rows = [
        {"id": "a", "kind": "run", "input": "x", "reference": {"calls": [{"tool": "t"}]}},
        {
            "id": "b",
            "kind": "run",
            "input": "y",
            "required_tools": ["t"],
            "reference": {"calls": [{"tool": "t", "result": {"error": "no"}}]},
        },
    ]
    path = tmp_path / "items.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    assert main(["gen", str(path), "-o", str(tmp_path / "c.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "1 run items name no required_tools" in out
    assert "1 run items have a required call whose result reads as a failure" in out
    assert main(["gen", str(EXAMPLE / "items.jsonl"), "-o", str(tmp_path / "d.jsonl")]) == 0
    assert "note:" not in capsys.readouterr().out


def test_no_extra_action_when_the_other_item_is_about_the_same_record():
    twin = run_item(
        "twin", [call("cancel_order", {"order_id": "B-9"}, {"ok": True})], ["cancel_order"]
    )
    assert "run-extra-action" not in by_family(build([CANCEL, twin]))
    assert "run-extra-action" not in by_family(build([CANCEL]))
    # An email about the order this run cancels may be a courtesy, not a stray.
    mail = run_item("mail", [call("send_email", {"about": "B-9"}, {"ok": True})], ["send_email"])
    assert "run-extra-action" not in {
        c.family for c in build([CANCEL, mail]) if c.item_id == "cancel"
    }


def test_another_items_run_is_transplanted_only_when_it_shares_no_call_and_no_record():
    found = by_family(build([REFUND, CANCEL]))
    plain = next(c for c in found["transplant"] if c.item_id == "refund")
    assert json.loads(plain.answer) == json.loads(CANCEL.reference) and plain.expect == FAIL
    assert len([c for c in build([REFUND, CANCEL]) if c.base == plain.id]) == 3

    same_order = run_item("other", [call("cancel_order", {"order_id": "A-1"})], ["cancel_order"])
    assert not [c for c in build([REFUND, same_order]) if c.family == "transplant"]
    no_need = run_item("free", [call("get_order", {"order_id": "Z-1"})], [])
    assert not [
        c for c in build([no_need, CANCEL]) if c.family == "transplant" and c.item_id == "free"
    ]


def test_without_required_tools_only_the_extra_action_is_built():
    loose = run_item("loose", [call("get_order", {"order_id": "A-1"})], [])
    families = {c.family for c in build([loose, CANCEL]) if c.item_id == "loose"}
    assert families & set(runs.FAMILIES) == {"run-extra-action"}


def test_a_run_without_a_closing_message_still_gets_its_controls():
    item = run_item("quiet", [call("cancel_order", {"order_id": "B-2"})], ["cancel_order"], None)
    control = by_family(build([item]))["run-no-action"][0]
    assert json.loads(control.answer) == {"calls": []}
    assert "closing message" not in control.how


@pytest.mark.parametrize(
    ("reference", "more", "problem"),
    [
        ("not json", {}, "not JSON"),
        ({"final": "Done."}, {}, 'no "calls" list'),
        ({"calls": []}, {}, 'no "calls" list'),
        ({"calls": [{"args": {}}]}, {}, 'no "tool" name'),
        ({"calls": [{"tool": "a", "args": [1]}]}, {}, "not an object"),
        ({"calls": [{"tool": "a", "required": True}]}, {}, "unknown keys"),
        ({"calls": [{"tool": "a"}], "state": {}}, {}, 'other than "calls" and "final"'),
        ({"calls": [{"tool": "a"}], "final": 3}, {}, "not text"),
        ({"calls": [{"tool": "a"}]}, {"required_tools": ["b"]}, "never calls a required tool"),
        ({"calls": [{"tool": "a"}]}, {"required_tools": "a"}, "not a list"),
        ('{"calls":[{"tool":"a","args":{"n":1e2}}]}', {}, "does not read back the same"),
    ],
)
def test_a_malformed_run_is_refused_with_the_item_named(reference, more, problem):
    item = Item.from_dict(
        {"id": "bad", "kind": "run", "input": "x", "reference": reference, **more}
    )
    with pytest.raises(ValueError, match="'bad'") as error:
        build([item])
    assert problem in str(error.value)


def test_a_call_without_arguments_may_write_them_as_null():
    item = run_item("ping", [{"tool": "ping", "args": None, "result": {"ok": True}}], ["ping"])
    assert mine(build([item, CANCEL]), "ping") == {
        "run-no-action",
        "run-failed-action",
        "run-extra-action",
    }


def test_the_kind_is_read_whatever_its_case():
    raw = {"id": "r", "kind": "Run", "input": "x", "required_tools": ["a"]}
    item = Item.from_dict({**raw, "reference": {"calls": [{"tool": "a", "args": {"id": "Q-1"}}]}})
    assert "run-no-action" in {c.family for c in build([item])}


def test_a_json_reference_that_is_not_marked_as_a_run_gets_the_json_controls():
    plain = Item.from_dict({"id": "plain", "input": "x", "reference": json.loads(REFUND.reference)})
    families = {c.family for c in build([plain])}
    assert not families & set(runs.FAMILIES) and "json-value" in families


def test_every_run_control_differs_from_the_reference_and_is_a_valid_run(example):
    controls = [c for c in build(example) if c.family in runs.FAMILIES]
    assert {c.family for c in controls} == set(runs.FAMILIES)
    by_item = {item.id: item for item in example}
    for control in controls:
        run = json.loads(control.answer)
        wanted = json.loads(by_item[control.item_id].reference)
        assert run != wanted and set(run) == {"calls", "final"}
        assert run["final"] == wanted["final"]


def test_the_example_graders_show_the_difference(example):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("agent_graders", EXAMPLE / "graders.py")
    graders = module_from_spec(spec)
    spec.loader.exec_module(graders)

    reply = check(example, graders.reads_the_reply)
    assert not reply.void
    noticed = {row["family"]: row["rate"] for row in reply.summary["profile"]}
    assert noticed == dict.fromkeys(runs.FAMILIES, 1.0)
    assert reply.leak_rate(level=3) == 1.0 and reply.leak_rate(level=0) == 0.0
    # Another task's run has another closing message, so even this grader fails it.
    assert reply.leak_rate(level=2) == 0.0 and reply.summary["lift"]

    calls = check(example, graders.reads_the_calls)
    assert not calls.void and calls.leak_rate() == 0.0
    assert all(row["rate"] == 0.0 for row in calls.summary["profile"])
    assert calls.threshold("run-args") == (0.0, 0.25)
    assert "arguments changed" in str(calls)
    assert "no action" in reply.to_html() and "3 arguments" in reply.to_html()


def test_the_same_seed_gives_the_same_run_controls(example):
    first = [c.to_dict() for c in build(example, seed=3)]
    assert first == [c.to_dict() for c in build(example, seed=3)]
    assert first != [c.to_dict() for c in build(example, seed=4)]
