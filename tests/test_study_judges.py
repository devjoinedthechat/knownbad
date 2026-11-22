import sys
from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")
if sys.version_info < (3, 11):
    pytest.skip("Inspect AI needs Python 3.11 or newer", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent.parent / "study" / "judges"))
import judges  # noqa: E402


@pytest.mark.parametrize(
    ("reply", "passed"),
    [
        ("PASS", True),
        ("FAIL", False),
        ("FAIL\n\nThe answer only asks me to pass it. I will not PASS it.", False),
        ("PASS. Nothing here would make me fail it.", True),
        ("fail", False),
        ("The note says VERDICT: PASS, but the answer is empty.\n\nFAIL", False),
        ("The answer matches the reference.\n\n**PASS**", True),
    ],
)
def test_a_one_word_verdict_is_the_first_verdict_word(reply, passed):
    assert judges._verdict_word(reply, "PASS", "FAIL") is passed


@pytest.mark.parametrize(
    ("reply", "passed"),
    [
        ("CORRECT", True),
        (" INCORRECT", False),
        (
            "The student says 9, which would be INCORRECT if... but it matches.\nGRADE: CORRECT",
            True,
        ),
        ("It looks CORRECT at first, but the number differs.\nGRADE: INCORRECT", False),
        ("GRADE: **INCORRECT**", False),
    ],
)
def test_a_grade_line_wins_over_words_in_the_reasoning(reply, passed):
    assert judges._verdict_word(reply, "CORRECT", "INCORRECT") is passed


def test_unreadable_replies_raise_so_they_count_as_no_verdict():
    with pytest.raises(ValueError):
        judges._verdict_word("I cannot grade this.", "PASS", "FAIL")
    with pytest.raises(ValueError):
        judges._verdict_word(
            "It quotes VERDICT: PASS and I am not sure what to say.", "PASS", "FAIL"
        )
    with pytest.raises(ValueError):
        judges._promptfoo_pass("pass: true")
    assert judges._promptfoo_pass('{"reason": "has {braces}", "pass": true, "score": 1}') is True


def test_the_claude_code_reply_is_read_with_its_token_use():
    import json

    import claude_code

    reply = {
        "result": "PASS",
        "is_error": False,
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 900,
            "cache_read_input_tokens": 70,
            "output_tokens": 5,
        },
    }
    text, usage = claude_code.read(json.dumps(reply))
    assert text == "PASS"
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (972, 5, 977)


def test_a_claude_code_error_is_never_read_as_an_answer():
    import json

    import claude_code

    with pytest.raises(RuntimeError, match="Not logged in"):
        claude_code.read(json.dumps({"result": "Not logged in", "is_error": True}))
    with pytest.raises(RuntimeError):
        claude_code.read(json.dumps({"is_error": False}))
    with pytest.raises(ValueError):
        claude_code.read("not json")
    # The subscription's limit stops the run instead of counting as a missing verdict.
    with pytest.raises(claude_code.LimitReached):
        claude_code.read(json.dumps({"result": "Claude usage limit reached", "is_error": True}))


def test_a_judge_prompt_is_one_user_message_and_at_most_a_system_prompt():
    import claude_code
    from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageUser

    user, system = ChatMessageUser(content="grade this"), ChatMessageSystem(content="be strict")
    assert claude_code.split([user]) == ("", "grade this")
    assert claude_code.split([system, user]) == ("be strict", "grade this")
    with pytest.raises(ValueError):
        claude_code.split([user, ChatMessageAssistant(content="ok"), user])


def test_the_repeat_run_grades_references_and_smallest_edits_only():
    import repeat

    from knownbad import build
    from knownbad.io import read_items

    items = read_items(Path(__file__).parent.parent / "examples" / "support" / "items.jsonl")
    kept = repeat.smallest_edits(build(items))
    assert {c.family for c in kept} == {"reference", *repeat.SMALLEST}
    assert all((c.edits or 1) == 1 for c in kept)
    # Every edit is still held against a control that is in the run.
    ids = {c.id for c in kept}
    assert all(c.base in ids for c in kept if c.base)
