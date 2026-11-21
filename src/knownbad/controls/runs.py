"""Controls for agent runs: the tool calls an agent made and what it said at the end.

A grader of agents has to tell a run that did the work from a run that says
it did. These controls take a reference run and break exactly that:

    run-no-action       every required call removed, the closing message kept
    run-skipped-action  one of several required calls removed
    run-failed-action   a required call comes back as an error, the message kept
    run-args            arguments of the required calls changed, in doses
    run-extra-action    a call from another item added: something nobody asked for

They are built only for items marked `"kind": "run"`, whose reference is

    {"calls": [{"tool": "...", "args": {...}, "result": ...}, ...], "final": "..."}

Which calls the task cannot be done without is not something knownbad can
know, so the item says it: `"required_tools": ["refund_order"]`. That list is
kept outside the reference, where the grader does not see it as part of the
answer. Without it only `run-extra-action` is built.

What makes a broken run certainly broken is narrow, and the builders stay
inside it:

- The reference must be a run that worked. If a required call already
  returns an error there, removing or failing it proves nothing.
- A tool called twice may be a retry or an overwrite, so a single call is
  removed or failed only when its tool is called once.
- A changed argument is never called wrong, only not better than the
  reference: a flag may be cosmetic and a number may be a tolerance.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from ..model import FAIL, NOT_HIGHER, Control, Item
from ._common import cid, dose_steps, rng
from .structured import Path, _dump, _leaves, _set, _wrong_value

KIND = "run"
FAMILIES = (
    "run-no-action",
    "run-skipped-action",
    "run-failed-action",
    "run-args",
    "run-extra-action",
)
ERROR = "The call failed. Nothing was changed."


def is_run(item: Item) -> bool:
    kind = item.meta.get("kind")
    return isinstance(kind, str) and kind.strip().lower() == KIND


def _bad(item: Item, problem: str) -> ValueError:
    return ValueError(f'item {item.id!r} is marked "kind": "run" but {problem}')


def parse(item: Item) -> tuple[dict[str, Any], list[str]]:
    """The reference run and the tools the task requires, checked for shape."""
    if not item.reference:
        raise _bad(item, "has no reference run")
    try:
        run = json.loads(item.reference)
    except ValueError:
        raise _bad(item, "its reference is not JSON") from None
    if not isinstance(run, dict) or not isinstance(run.get("calls"), list) or not run["calls"]:
        raise _bad(item, 'its reference has no "calls" list')
    extra = sorted(set(run) - {"calls", "final"})
    if extra:
        raise _bad(item, f'its reference has keys other than "calls" and "final": {extra}')
    if "final" in run and not isinstance(run["final"], str):
        raise _bad(item, 'its "final" is not text')
    for call in run["calls"]:
        if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not call["tool"]:
            raise _bad(item, 'a call has no "tool" name')
        if not isinstance(_args_of(call), dict):
            raise _bad(item, f'the "args" of a {call["tool"]} call are not an object')
        unknown = sorted(set(call) - {"tool", "args", "result"})
        if unknown:
            raise _bad(item, f"a {call['tool']} call has unknown keys: {unknown}")
    # Every control is this text with one edit. If the reference were written
    # another way (other spacing, 1e2 for 100.0), each control would differ
    # from it in more than its edit.
    if _dump(run, item.reference) != item.reference.strip():
        raise _bad(
            item,
            "its reference is text that does not read back the same. Give the run as a "
            "JSON object in the items file, not as a string",
        )
    required = item.meta.get("required_tools", [])
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        raise _bad(item, 'its "required_tools" is not a list of tool names')
    used = {call["tool"] for call in run["calls"]}
    missing = sorted(set(required) - used)
    if missing:
        raise _bad(item, f"the reference never calls a required tool: {missing}")
    return run, list(required)


def _args_of(call: dict[str, Any]) -> Any:
    """A call's arguments. Traces often write a call without arguments as null."""
    args = call.get("args")
    return {} if args is None else args


def _same_call(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(a["tool"] == b["tool"] and _args_of(a) == _args_of(b))


_FAILED_WORDS = ("error", "failed", "failure", "denied", "rejected")


def _is_error(result: Any) -> bool:
    """Does this result read as a call that did not work?

    A safety net, not the rule: the rule is that the reference is a run in
    which the required calls worked. It errs towards yes, because a wrong
    yes only costs an item its call controls, and a wrong no builds a control
    whose claim is false.
    """
    if result is False:
        return True
    if isinstance(result, str):
        return result.strip().lower().startswith(_FAILED_WORDS)
    if isinstance(result, list):
        return any(_is_error(entry) for entry in result)
    if not isinstance(result, dict):
        return False
    for key, value in result.items():
        name = key.lower().replace("_", "")
        if name in ("error", "errors", "iserror") and value:
            return True
        if name in ("ok", "success") and value in (False, "false", "False"):
            return True
        if name == "status":
            if isinstance(value, str) and value.strip().lower().startswith(_FAILED_WORDS):
                return True
            if isinstance(value, int) and not isinstance(value, bool) and value >= 400:
                return True
        if isinstance(value, (dict, list)) and _is_error(value):
            return True
    return False


def _failed(result: Any) -> Any:
    return {"error": ERROR} if isinstance(result, dict) or result is None else f"Error: {ERROR}"


def _id_like(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)


def _strings(value: Any) -> set[str]:
    return {leaf for _, leaf in _leaves(value) if isinstance(leaf, str)}


def _records(calls: Sequence[dict[str, Any]], results: bool) -> set[str]:
    """What a run's calls point at: ids and numbers in their arguments.

    Tool names are not records: two tasks may both look an order up. Numbers
    count, because an order id may be 1042 as well as "A-1042".
    """
    found: set[str] = set()
    for call in calls:
        parts = [_args_of(call), call.get("result")] if results else [_args_of(call)]
        for _, leaf in _leaves(parts):
            if _id_like(leaf):
                found.add(leaf)
            elif isinstance(leaf, (int, float)) and not isinstance(leaf, bool):
                found.add(repr(float(leaf)))
    return found


def _with_calls(run: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {**run, "calls": calls}


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


class Pool:
    """Every run item of a set, parsed once."""

    def __init__(self, items: Sequence[Item]) -> None:
        self.items = [item for item in items if is_run(item)]
        self.parsed = {item.id: parse(item) for item in self.items}
        self.ids = {
            leaf
            for run, _ in self.parsed.values()
            for call in run["calls"]
            for leaf in _strings(_args_of(call))
            if _id_like(leaf)
        }

    def others(self, item: Item, seed: int, purpose: str) -> list[Item]:
        """The other run items, in an order fixed by the seed."""
        others = [other for other in self.items if other.id != item.id]
        rng(seed, item.id, purpose).shuffle(others)
        return others

    def notes(self) -> list[str]:
        """Why some run items got fewer controls than the rest."""
        unmarked = failed = 0
        for run, required in self.parsed.values():
            needed = [call for call in run["calls"] if call["tool"] in required]
            unmarked += not needed
            failed += any(_is_error(call.get("result")) for call in needed)
        notes = []
        if unmarked:
            notes.append(
                f"{unmarked} run items name no required_tools: only run-extra-action is built "
                "for them."
            )
        if failed:
            notes.append(
                f"{failed} run items have a required call whose result reads as a failure: "
                "nothing is claimed about their calls."
            )
        return notes


def transplant_donor(item: Item, pool: Pool, seed: int) -> Item | None:
    """Another item's whole run, to hand in as the answer to this one.

    It is certainly wrong only when this item requires calls that worked and
    the other run makes none of this run's calls and points at none of its
    records.
    """
    run, required = pool.parsed[item.id]
    needed = [call for call in run["calls"] if call["tool"] in required]
    if not needed or any(_is_error(call.get("result")) for call in needed):
        return None
    mine = _records(run["calls"], results=True)
    for other in pool.others(item, seed, "run-transplant"):
        theirs, _ = pool.parsed[other.id]
        shares_call = any(_same_call(a, b) for a in theirs["calls"] for b in run["calls"])
        if not shares_call and not _records(theirs["calls"], results=False) & mine:
            return other
    return None


Make = Callable[..., Control]


def build(item: Item, pool: Pool, seed: int) -> list[Control]:
    run, required = pool.parsed[item.id]
    reference = item.reference or ""
    calls: list[dict[str, Any]] = run["calls"]
    needed = [n for n, call in enumerate(calls) if call["tool"] in required]
    # A reference in which a required call fails is not a run that did the work.
    worked = bool(needed) and not any(_is_error(calls[n].get("result")) for n in needed)
    kept_note = "The closing message is unchanged." if run.get("final") else ""
    made: list[Control] = []

    def control(family: str, edited: dict[str, Any], how: str, **more: Any) -> Control:
        expect = more.pop("expect", FAIL)
        return Control(
            id=cid(item, family, more.pop("step", None)),
            item_id=item.id,
            family=family,
            level="3",
            expect=expect,
            answer=_dump(edited, reference),
            how=how.strip(),
            **more,
        )

    # Calls whose tool is called once: nothing else in the run can stand in for them.
    once = [n for n in needed if sum(call["tool"] == calls[n]["tool"] for call in calls) == 1]
    if worked:
        names = ", ".join(sorted({calls[n]["tool"] for n in needed}))
        made.append(
            control(
                "run-no-action",
                _with_calls(run, [call for n, call in enumerate(calls) if n not in needed]),
                f"Every call to a tool the task requires ({names}) removed. {kept_note}",
            )
        )
        if len(needed) >= 2 and once:
            gone = once[rng(seed, item.id, "run-skipped-action").randrange(len(once))]
            made.append(
                control(
                    "run-skipped-action",
                    _with_calls(run, [call for n, call in enumerate(calls) if n != gone]),
                    f"One of {len(needed)} required calls removed: call {gone + 1}, "
                    f"{calls[gone]['tool']}, the only call to that tool. {kept_note}",
                )
            )
        if once:
            hit = once[rng(seed, item.id, "run-failed-action").randrange(len(once))]
            edited = _copy(calls)
            edited[hit]["result"] = _failed(calls[hit].get("result"))
            made.append(
                control(
                    "run-failed-action",
                    _with_calls(run, edited),
                    f"Call {hit + 1}, {calls[hit]['tool']}, the only call to that tool, now "
                    f"returns an error and is not tried again. {kept_note}",
                )
            )
        made.extend(_args(item, run, needed, pool, seed, control))

    added = _foreign_call(item, run, pool, seed)
    if added is not None:
        donor, call = added
        made.append(
            control(
                "run-extra-action",
                _with_calls(run, [*calls, call]),
                f"A {call['tool']} call that another item ({donor.id}) requires, added after "
                "the reference's own calls. This task did not ask for it, so the run cannot "
                "be better than the reference.",
                expect=NOT_HIGHER,
                base=cid(item, "reference"),
                edits=1,
            )
        )
    return made


def _foreign_call(
    item: Item, run: dict[str, Any], pool: Pool, seed: int
) -> tuple[Item, dict[str, Any]] | None:
    """A call another task required, about records this run never touches."""
    mine = _records(run["calls"], results=True)
    for other in pool.others(item, seed, "run-donor"):
        theirs, their_required = pool.parsed[other.id]
        for call in theirs["calls"]:
            if call["tool"] not in their_required or _is_error(call.get("result")):
                continue
            if any(_same_call(call, own) for own in run["calls"]):
                continue
            # A call about the same order or customer may be a courtesy, not a stray.
            if _records([call], results=False) & mine:
                continue
            return other, _copy(call)
    return None


def _args(
    item: Item,
    run: dict[str, Any],
    needed: Sequence[int],
    pool: Pool,
    seed: int,
    control: Make,
) -> list[Control]:
    """Change k of n argument values of the required calls, keeping each value's type.

    Every step is compared with the reference, not with the step before: two
    changed numbers can cancel (30 + 10 becomes 37 + 10, then 33 + 7), so a
    later step is not certainly worse than an earlier one.
    """
    calls = run["calls"]
    leaves: list[tuple[Path, Any]] = [
        ((n, "args", *path), value)
        for n in needed
        for path, value in _leaves(_args_of(calls[n]))
        if path  # an empty args object has no value to change
    ]
    ids = sorted(pool.ids - _strings(run))
    source = rng(seed, item.id, "run-args")
    changes: list[tuple[Path, Any]] = []
    for path, value in leaves:
        # An id is swapped for another item's id; free text has no near miss.
        wrong = _wrong_value(value, ids if _id_like(value) else [], source)
        if wrong is not value and wrong != value:
            changes.append((path, wrong))
    if not changes:
        return []
    source.shuffle(changes)
    made: list[Control] = []
    # Step 1 is always built: it is the edit the report's profile row reads.
    for step in sorted({1, *dose_steps(len(changes))}):
        edited = _copy(calls)
        for path, wrong in changes[:step]:
            if edited[path[0]].get("args") is None:
                edited[path[0]]["args"] = {}
            _set(edited, path, wrong)
        made.append(
            control(
                "run-args",
                _with_calls(run, edited),
                f"{step} of {len(leaves)} argument values of the required calls changed to "
                "another value of the same type. It cannot be better than the reference.",
                expect=NOT_HIGHER,
                step=step,
                base=cid(item, "reference"),
                dose=step / len(leaves),
                edits=step,
            )
        )
    return made
