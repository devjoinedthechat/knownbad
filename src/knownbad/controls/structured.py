"""Controls for answers that are JSON: extraction, tool arguments, structured output.

They are built only when the reference itself parses as a JSON object or
array. Prose edits make no sense there, so these replace the sentence and
number doses for such items.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

from ..model import FAIL, NOT_HIGHER, Control, Item
from ..text import bump_number
from ._common import cid, dose_steps, rng

Path = tuple[Any, ...]


def parse(reference: str | None) -> Any:
    """The reference as JSON when it is a non-empty object or array, else None."""
    if not reference:
        return None
    text = reference.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, (dict, list)) and value else None


def _dump(value: Any, like: str) -> str:
    """Write JSON the way the reference was written: indented or on one line."""
    if "\n" in like.strip():
        return json.dumps(value, ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False)


def _leaves(value: Any, path: Path = ()) -> list[tuple[Path, Any]]:
    if isinstance(value, dict):
        return [leaf for key, child in value.items() for leaf in _leaves(child, (*path, key))]
    if isinstance(value, list):
        return [
            leaf for index, child in enumerate(value) for leaf in _leaves(child, (*path, index))
        ]
    return [(path, value)]


def _set(root: Any, path: Path, value: Any) -> None:
    for step in path[:-1]:
        root = root[step]
    root[path[-1]] = value


def _wrong_value(value: Any, others: list[str], source: random.Random) -> Any:
    """A different value of the same type, or the same object when none can be made."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return int(bump_number(str(abs(value)), source)) * (-1 if value < 0 else 1)
    if isinstance(value, float):
        if not math.isfinite(value):
            return value  # NaN and infinity have no near miss
        text = repr(abs(value))
        if "e" in text or "." not in text:
            return value + 1.0
        return float(bump_number(text, source)) * (-1 if value < 0 else 1)
    if isinstance(value, str):
        # Never another value from the same reference: swapping two list
        # entries twice gives the right list back in another order.
        different = [other for other in others if other != value]
        return source.choice(different) if different else f"{value} (other)"
    return value  # null: there is no wrong null


def build(item: Item, donor: Item | None, seed: int) -> list[Control]:
    root = parse(item.reference)
    if root is None or item.reference is None:
        return []
    reference = item.reference
    base_id = cid(item, "reference")
    made: list[Control] = []

    # Cut off mid-way: no longer JSON at all.
    cut = reference.strip()[: max(1, int(len(reference.strip()) * 0.6))]
    try:
        json.loads(cut)
    except ValueError:
        made.append(
            Control(
                id=cid(item, "json-truncated"),
                item_id=item.id,
                family="json-truncated",
                level="3",
                expect=FAIL,
                answer=cut,
                how="The reference cut off after 60% of its characters. It no longer parses.",
            )
        )

    # Change k of n values, keeping each value's type.
    leaves = _leaves(root)
    own_strings = {v for _, v in leaves if isinstance(v, str)}
    donor_root = parse(donor.reference) if donor else None
    strings = sorted(
        {v for _, v in _leaves(donor_root) if isinstance(v, str)} - own_strings
        if donor_root is not None
        else set()
    )
    source = rng(seed, item.id, "json-value")
    changes: list[tuple[Path, Any]] = []
    for path, value in leaves:
        wrong = _wrong_value(value, strings, source)
        if wrong is not value and wrong != value:
            changes.append((path, wrong))
    source.shuffle(changes)
    base = base_id
    for step in dose_steps(len(changes)) if changes else []:
        edited = json.loads(json.dumps(root))
        for path, wrong in changes[:step]:
            _set(edited, path, wrong)
        only_value = len(leaves) == 1
        control = Control(
            id=cid(item, "json-value", step),
            item_id=item.id,
            family="json-value",
            level="3",
            expect=FAIL if only_value else NOT_HIGHER,
            answer=_dump(edited, reference),
            how=(
                f"{step} of {len(leaves)} values in the reference changed to another value of "
                "the same type. "
                + (
                    "It was the only value, so the answer is wrong."
                    if only_value
                    else "It cannot be better than the answer with fewer values changed."
                )
            ),
            base=base,
            dose=step / len(leaves),
            edits=step,
        )
        made.append(control)
        base = control.id

    # Drop k of n top-level fields.
    if isinstance(root, dict) and len(root) >= 2:
        keys = list(root)
        rng(seed, item.id, "json-drop").shuffle(keys)
        base = base_id
        for step in dose_steps(len(keys)):
            gone = set(keys[:step])
            kept = {key: value for key, value in root.items() if key not in gone}
            control = Control(
                id=cid(item, "json-drop", step),
                item_id=item.id,
                family="json-drop",
                level="3",
                expect=FAIL if not kept else NOT_HIGHER,
                answer=_dump(kept, reference),
                how=(
                    f"{step} of {len(keys)} top-level fields removed from the reference. "
                    + (
                        "Nothing of the reference is left."
                        if not kept
                        else "It cannot be better than the answer with fewer fields removed."
                    )
                ),
                base=base,
                dose=step / len(keys),
                edits=step,
            )
            made.append(control)
            base = control.id
    return made
