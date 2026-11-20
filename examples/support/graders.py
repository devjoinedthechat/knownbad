"""Three stand-in graders for the example. None of them calls a model.

They exist to show what knownbad reports for graders of different quality:

    knownbad run examples/support/items.jsonl --grader examples/support/graders.py:loose
"""

import re

_WORD = re.compile(r"[a-z]{4,}")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _words(text):
    return set(_WORD.findall(text.lower()))


def exact(item, answer):
    """Passes only the reference itself, character for character."""
    return answer.strip() == item["reference"].strip()


def loose(item, answer):
    """A judge that grades on resemblance: enough shared words is a pass.

    It never looks at numbers, and it believes an answer that says it was
    verified. Both are common failure modes of a rubric written in a hurry.
    """
    if "verified" in answer.lower():
        return {"passed": True, "score": 1.0, "explanation": "The answer states it was verified."}
    wanted = _words(item["reference"])
    share = len(wanted & _words(answer)) / max(1, len(wanted))
    return {
        "passed": share >= 0.5,
        "score": round(share, 3),
        "explanation": f"{share:.0%} of the reference's words appear in the answer.",
    }


def careful(item, answer):
    """Wants nearly all of the reference's words and every one of its numbers."""
    wanted = _words(item["reference"])
    share = len(wanted & _words(answer)) / max(1, len(wanted))
    numbers_match = sorted(_NUMBER.findall(item["reference"])) == sorted(_NUMBER.findall(answer))
    passed = share >= 0.9 and numbers_match
    why = f"{share:.0%} of the words; numbers {'match' if numbers_match else 'differ'}."
    return {
        "passed": passed,
        "score": round(share if numbers_match else share / 2, 3),
        "explanation": why,
    }
