import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")
if sys.version_info < (3, 11):
    pytest.skip("Inspect AI needs Python 3.11 or newer", allow_module_level=True)

STUDY = Path(__file__).parent.parent / "study" / "agents"
sys.path.insert(0, str(STUDY))
import run_judges as j  # noqa: E402

RUN = json.dumps(
    {
        "calls": [
            {"tool": "close_po", "args": {"po_id": "PO-1"}, "result": {"ok": True}},
            {"tool": "notify", "args": None, "result": "Error: no channel"},
        ],
        "final": "PO-1 is closed.",
    }
)


def test_a_run_becomes_the_message_list_an_agent_framework_records():
    messages = j.messages_of("Close PO-1.", RUN)
    assert [m["role"] for m in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert messages[1]["tool_calls"][0]["function"] == {
        "name": "close_po",
        "arguments": '{"po_id": "PO-1"}',
    }
    assert messages[3]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert messages[4] == {"role": "tool", "tool_call_id": "call_2", "content": "Error: no channel"}
    assert messages[-1] == {"role": "assistant", "content": "PO-1 is closed."}


def test_an_answer_that_is_not_a_run_is_the_closing_message_alone():
    assert j.messages_of("Close PO-1.", "Done.")[-1] == {"role": "assistant", "content": "Done."}
    assert j.deepeval_tools("Done.") == ""
    assert j.final_of("Done.") == "Done."


def test_the_trajectory_is_formatted_as_openevals_formats_it():
    text = j.openevals_string(j.messages_of("Close PO-1.", RUN))
    assert text.startswith("<user>\nClose PO-1.\n</user>\n\n<assistant>\n<tool_call>\n")
    assert '<tool>\n<tool_result>\n<id>call_1</id>\n<content>{"ok": true}</content>' in text
    assert text.endswith("<assistant>\nPO-1 is closed.\n</assistant>")


def test_the_tools_called_are_printed_as_deepeval_prints_them():
    printed = j.deepeval_tools(RUN)
    assert printed.startswith("[\n  {\n")
    assert printed.endswith("}\n]")
    assert '"input_parameters": {\n' in printed
    assert '"output": "Error: no channel"' in printed


@pytest.mark.parametrize(
    ("reply", "passed"),
    [
        ('{"reasoning": "Fine. Thus, the score should be: true.", "score": true}', True),
        ('Here it is:\n{"reasoning": "No refund call.", "score": false}', False),
    ],
)
def test_the_openevals_score_is_read_from_the_json(reply, passed):
    assert j.openevals_score(reply) is passed


@pytest.mark.parametrize("reply", ["true", '{"score": "true"}', '{"reasoning": "x"}'])
def test_a_reply_without_a_boolean_score_is_no_verdict(reply):
    with pytest.raises(ValueError):
        j.openevals_score(reply)


def test_the_deepeval_verdict_is_a_number():
    assert j.deepeval_verdict('{"verdict": 0.5, "reason": "half"}') == 0.5
    assert j.deepeval_verdict('{"verdict": 1, "reason": "done"}') == 1.0
    for reply in ('{"verdict": true}', '{"verdict": "0.9"}', "0.9"):
        with pytest.raises(ValueError):
            j.deepeval_verdict(reply)


def test_strict_run_reads_only_the_first_word():
    assert j.first_word("PASS. The refund call succeeded.") is True
    assert j.first_word("**FAIL** No call made the change.") is False
    with pytest.raises(ValueError):
        j.first_word("The run should PASS.")


def _study_run():
    # Loaded under its own name: the judge study has a run.py of its own.
    import importlib.util

    spec = importlib.util.spec_from_file_location("agents_run", STUDY / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_study_grades_each_family_at_its_smallest_edit_on_every_set():
    run = _study_run()

    from knownbad import build
    from knownbad.inspect_adapter import items_from

    for name in run.SETS:
        items, _ = items_from(run.task_for(name))
        kept = run.graded(build(items))
        families = {c.family for c in kept}
        assert {"reference", "run-no-action", "run-failed-action", "run-args"} <= families
        assert families <= set(run.GRADED)
        assert all((c.edits or 1) == 1 for c in kept)
        # One of each per item, so a rate over controls is a rate over items.
        for family in families:
            ids = [c.item_id for c in kept if c.family == family]
            assert len(ids) == len(set(ids))
