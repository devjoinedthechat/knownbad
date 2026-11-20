"""Turn raw outcomes into the numbers a person acts on."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from .controls import DOSE_FAMILIES
from .model import FAIL, GOOD_LEVEL, PASS
from .runner import Outcome
from .stats import rate

# Below this share of references passing, the grader rejects right answers so
# often that a low leak rate would mean nothing.
VOID_BELOW = 0.5
DOSE_BINS = ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0))
_EPS = 1e-9


def _order_value(outcome: Outcome) -> float | None:
    score = outcome.mean_score
    return score if score is not None else outcome.pass_share


def _leak_table(outcomes: Sequence[Outcome], key: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        control = outcome.control
        if control.expect != FAIL or outcome.errored:
            continue
        group: tuple[str, ...] = (
            (control.level,) if key == "level" else (control.level, control.family)
        )
        groups[group].append(outcome)
    rows = []
    for group in sorted(groups):
        members = groups[group]
        row: dict[str, Any] = {"level": group[0]}
        if key == "family":
            row["family"] = group[1]
        row.update(rate(sum(1 for o in members if o.passed), len(members)))
        row["flaky"] = sum(1 for o in members if o.flaky)
        rows.append(row)
    return rows


def _dose_curves(outcomes: Sequence[Outcome], by_id: dict[str, Outcome]) -> dict[str, Any]:
    curves: dict[str, Any] = {}
    for family in DOSE_FAMILIES:
        members = [o for o in outcomes if o.control.family == family and not o.errored]
        if not members:
            continue
        # Dose zero is the untouched reference of the same items.
        item_ids = {o.control.item_id for o in members}
        zero = [
            o
            for o in outcomes
            if o.control.family == "reference" and o.control.item_id in item_ids and not o.errored
        ]
        points = []
        if zero:
            points.append(_dose_point(0.0, 0.0, zero))
        for low, high in DOSE_BINS:
            inside = [o for o in members if low < (o.control.dose or 0.0) <= high + _EPS]
            if inside:
                points.append(_dose_point(low, high, inside))
        corrupted = [p for p in points if p["dose_high"] > 0]
        caught = next((p for p in corrupted if p["rate"] <= 0.5), None)
        # The dose range in which the grader first fails at least half.
        threshold = None if caught is None else [caught["dose_low"], caught["dose_high"]]
        curves[family] = {"points": points, "threshold": threshold}
    return curves


def _dose_point(low: float, high: float, members: Sequence[Outcome]) -> dict[str, Any]:
    scores = [s for s in (o.mean_score for o in members) if s is not None]
    point: dict[str, Any] = {"dose_low": low, "dose_high": high}
    point.update(rate(sum(1 for o in members if o.passed), len(members)))
    point["mean_score"] = sum(scores) / len(scores) if scores else None
    return point


def _order(outcomes: Sequence[Outcome], by_id: dict[str, Outcome]) -> dict[str, Any]:
    pairs = 0
    broken: list[str] = []
    for outcome in outcomes:
        control = outcome.control
        if control.family not in DOSE_FAMILIES or not control.base:
            continue
        base = by_id.get(control.base)
        if base is None:
            continue
        ours, theirs = _order_value(outcome), _order_value(base)
        if ours is None or theirs is None:
            continue
        pairs += 1
        if ours > theirs + _EPS:
            broken.append(control.id)
    result: dict[str, Any] = dict(rate(len(broken), pairs))
    result["violations"] = broken
    return result


def _lift(outcomes: Sequence[Outcome], by_id: dict[str, Outcome]) -> list[dict[str, Any]]:
    """Does dressing a wrong answer make it pass more often? Paired by item."""
    by_dressing: dict[str, list[tuple[Outcome, Outcome]]] = defaultdict(list)
    for outcome in outcomes:
        family = outcome.control.family
        if not family.startswith("transplant+") or not outcome.control.base:
            continue
        plain = by_id.get(outcome.control.base)
        if plain is None or plain.errored or outcome.errored:
            continue
        by_dressing[family.split("+", 1)[1]].append((plain, outcome))
    rows = []
    for dressing in sorted(by_dressing):
        pairs = by_dressing[dressing]
        plain_leaks = sum(1 for plain, _ in pairs if plain.passed)
        dressed_leaks = sum(1 for _, dressed in pairs if dressed.passed)
        rows.append(
            {
                "dressing": dressing,
                "pairs": len(pairs),
                "plain_rate": plain_leaks / len(pairs),
                "dressed_rate": dressed_leaks / len(pairs),
                "lift": (dressed_leaks - plain_leaks) / len(pairs),
                # Wrong answers the grader caught plain but passed once dressed.
                "turned": sum(1 for p, d in pairs if d.passed and not p.passed),
            }
        )
    return rows


# What each kind of edit asks of the grader, in the order a reader thinks of them.
PROFILE = (
    ("drop", "missing content", "one sentence removed"),
    ("splice", "off-topic content", "one sentence swapped for another item's"),
    ("numbers", "a wrong number", "one number changed slightly"),
    ("flip", "a reversed claim", "one word turned into its opposite"),
    ("contradict", "self-contradiction", "a sentence repeated with a changed fact"),
    ("json-value", "a wrong value", "one JSON value changed"),
    ("json-drop", "a missing field", "one JSON field removed"),
)


def _profile(outcomes: Sequence[Outcome]) -> list[dict[str, Any]]:
    """For each kind of edit: how often the smallest edit still passes.

    The smallest edit is the hardest to see, so this is the row that tells a
    grader that reads closely from one that reads for the gist.
    """
    rows = []
    for family, notices, edit in PROFILE:
        smallest = [
            o
            for o in outcomes
            if o.control.family == family and not o.errored and (o.control.edits or 1) == 1
        ]
        if not smallest:
            continue
        row: dict[str, Any] = {"family": family, "notices": notices, "edit": edit}
        row.update(rate(sum(1 for o in smallest if o.passed), len(smallest)))
        rows.append(row)
    return rows


def _consistency(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    """With repeated trials: how often the grader gave one answer the same verdict."""
    repeated = [o for o in outcomes if len(o.graded) >= 2]
    result: dict[str, Any] = dict(rate(sum(1 for o in repeated if not o.flaky), len(repeated)))
    result["split"] = [o.control.id for o in repeated if o.flaky]
    return result


def summarise(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    by_id = {o.control.id: o for o in outcomes}
    graded = [o for o in outcomes if not o.errored]
    errors = len(outcomes) - len(graded)

    good = [o for o in graded if o.control.expect == PASS]
    references = rate(sum(1 for o in good if o.passed), len(good))
    must_fail = [o for o in graded if o.control.expect == FAIL]
    overall = rate(sum(1 for o in must_fail if o.passed), len(must_fail))

    void: str | None = None
    if outcomes and not graded:
        void = "The grader returned no verdict for any control."
    elif references["rate"] is not None and references["rate"] < VOID_BELOW:
        void = (
            f"The grader passed only {references['k']} of {references['n']} reference "
            "answers. A grader that rejects right answers makes a low leak rate meaningless."
        )
    elif not must_fail:
        void = "No must-fail control was graded."

    return {
        "controls": len(outcomes),
        "graded": len(graded),
        "errors": errors,
        "error_examples": [
            {"id": o.control.id, "error": o.verdicts[0].error} for o in outcomes if o.errored
        ][:5],
        "void": void,
        "references": references,
        "false_rejects": [o.control.id for o in good if not o.passed],
        "overall": overall,
        "levels": _leak_table(outcomes, "level"),
        "families": _leak_table(outcomes, "family"),
        "dose": _dose_curves(outcomes, by_id),
        "order": _order(outcomes, by_id),
        "lift": _lift(outcomes, by_id),
        "leaks": [o.control.id for o in must_fail if o.passed],
        "profile": _profile(outcomes),
        "consistency": _consistency(outcomes),
        "has_references": any(o.control.level == GOOD_LEVEL for o in outcomes),
    }


def gate(summary: dict[str, Any], max_leak: float | None, per_level: dict[str, float]) -> list[str]:
    """The reasons this run should fail a build. Empty means it passes."""
    reasons: list[str] = []
    if summary["void"]:
        return [f"void: {summary['void']}"]
    overall = summary["overall"]["rate"]
    if max_leak is not None and overall is not None and overall > max_leak + _EPS:
        reasons.append(f"leak rate {overall:.1%} is over the limit of {max_leak:.1%}")
    rates = {row["level"]: row["rate"] for row in summary["levels"]}
    for level, limit in sorted(per_level.items()):
        got = rates.get(level)
        if got is not None and got > limit + _EPS:
            reasons.append(f"level {level} leak rate {got:.1%} is over the limit of {limit:.1%}")
    return reasons
