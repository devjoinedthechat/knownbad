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
