"""Compare two runs over the same controls: did the grader change, and which way?

The controls are the fixed weight. When the same controls give different
verdicts in two runs, the grader moved. The pairing matters statistically
too: each control is its own comparison, so the test looks only at controls
whose verdict flipped.
"""

from __future__ import annotations

from typing import Any

from .model import FAIL, NOT_HIGHER, PASS
from .runner import Outcome
from .stats import rate, sign_test

MOVES = ("fixed", "broken", "newly_rejected", "newly_accepted", "now_passes", "now_fails")


def _outcomes(result: dict[str, Any]) -> dict[str, Outcome]:
    return {o["control"]["id"]: Outcome.from_dict(o) for o in result["outcomes"]}


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """What changed between two result files. `old` is the baseline."""
    before, after = _outcomes(old), _outcomes(new)
    shared = [i for i in before if i in after]
    changed_answer = [i for i in shared if before[i].control.answer != after[i].control.answer]
    if changed_answer:
        raise ValueError(
            f"{len(changed_answer)} controls have the same id but a different answer in the "
            f"two runs (first: {changed_answer[0]}). Compare runs made from one controls file."
        )

    moves: dict[str, list[str]] = {name: [] for name in MOVES}
    unreadable: list[str] = []
    leaks_before = leaks_after = must_fail = 0
    refs_before = refs_after = refs = 0
    for control_id in shared:
        a, b = before[control_id], after[control_id]
        if a.errored or b.errored:
            unreadable.append(control_id)
            continue
        was, now = bool(a.passed), bool(b.passed)
        expect = a.control.expect
        if expect == FAIL:
            must_fail += 1
            leaks_before += was
            leaks_after += now
            if was and not now:
                moves["fixed"].append(control_id)
            elif now and not was:
                moves["broken"].append(control_id)
        elif expect == PASS:
            refs += 1
            refs_before += was
            refs_after += now
            if was and not now:
                moves["newly_rejected"].append(control_id)
            elif now and not was:
                moves["newly_accepted"].append(control_id)
        elif expect == NOT_HIGHER and was != now:
            moves["now_passes" if now else "now_fails"].append(control_id)

    fixed, broken = len(moves["fixed"]), len(moves["broken"])
    return {
        "old": {"grader": old.get("grader"), "created": old.get("created")},
        "new": {"grader": new.get("grader"), "created": new.get("created")},
        "shared": len(shared),
        "only_old": len(before) - len(shared),
        "only_new": len(after) - len(shared),
        "unreadable": unreadable,
        "leaks": {"old": rate(leaks_before, must_fail), "new": rate(leaks_after, must_fail)},
        "references": {"old": rate(refs_before, refs), "new": rate(refs_after, refs)},
        "moves": moves,
        # Could this many more fixes than breaks (or the reverse) be chance?
        "p_value": sign_test(fixed, broken),
        "direction": "better" if fixed > broken else "worse" if broken > fixed else "same",
    }


def regressions(diff: dict[str, Any]) -> list[str]:
    """Reasons a build should fail: verdicts that were right and are now wrong."""
    reasons = []
    broken, rejected = diff["moves"]["broken"], diff["moves"]["newly_rejected"]
    if broken:
        reasons.append(f"{len(broken)} wrong answers that were caught now pass")
    if rejected:
        reasons.append(f"{len(rejected)} reference answers that passed now fail")
    return reasons
