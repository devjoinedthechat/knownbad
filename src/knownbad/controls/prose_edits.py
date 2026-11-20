"""Edits of a prose reference that each probe one thing a grader may not notice.

    drop        sentences removed: does it notice missing content?
    flip        a word turned into its opposite: does it read what the answer claims?
    contradict  a sentence repeated with a changed fact: does it notice the
                answer disagrees with itself?

Each claim is `not_higher`: the edited answer cannot be better than the one
it was made from. None is called wrong outright, because whether a missing
sentence or a flipped word matters is up to the rubric.
"""

from __future__ import annotations

import re

from ..model import NOT_HIGHER, Control, Item
from ..text import bump_number, numbers, replace_matches, sentences
from ._common import cid, dose_steps, rng

# Pairs whose swap states the opposite or a different unit. English only; a
# reference in another language simply has nothing to flip. Phrases come
# first so "must not" is read before "must".
_PAIRS = (
    ("must not", "must"),
    ("cannot", "can"),
    ("can not", "can"),
    ("does not", "does"),
    ("do not", "do"),
    ("is not", "is"),
    ("are not", "are"),
    ("more than", "less than"),
    ("at least", "at most"),
    ("always", "never"),
    ("before", "after"),
    ("above", "below"),
    ("minimum", "maximum"),
    ("increase", "decrease"),
    ("first", "last"),
    ("older", "newer"),
    ("higher", "lower"),
    ("longer", "shorter"),
    ("larger", "smaller"),
    ("faster", "slower"),
    ("include", "exclude"),
    ("includes", "excludes"),
    ("included", "excluded"),
    ("enable", "disable"),
    ("enabled", "disabled"),
    ("open", "closed"),
    ("valid", "invalid"),
    ("automatically", "manually"),
    ("days", "weeks"),
    ("hours", "minutes"),
    ("months", "years"),
    ("daily", "weekly"),
    ("euros", "dollars"),
    ("kilometres", "miles"),
    ("kilometers", "miles"),
    ("kilograms", "pounds"),
    ("celsius", "fahrenheit"),
)
# Negations are only removed, never added: "is" -> "is not" would hit almost
# every sentence and often produce nonsense.
_ONE_WAY = {"must not", "cannot", "can not", "does not", "do not", "is not", "are not"}
_SWAP: dict[str, str] = {}
for _a, _b in _PAIRS:
    _SWAP[_a] = _b
    if _a not in _ONE_WAY:
        _SWAP.setdefault(_b, _a)
_SWAP["can"] = "cannot"
_FLIPPABLE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_SWAP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _like(original: str, replacement: str) -> str:
    """Give the replacement the capitalisation of the word it replaces."""
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def flip_word(found: re.Match[str]) -> str:
    return _like(found.group(), _SWAP[found.group().lower()])


def drop(item: Item, seed: int) -> list[Control]:
    """Remove k of n sentences. The last step keeps one sentence."""
    if not item.reference:
        return []
    own = sentences(item.reference)
    if len(own) < 2:
        return []
    order = rng(seed, item.id, "drop").sample(range(len(own)), len(own))
    made: list[Control] = []
    base = cid(item, "reference")
    for step in dose_steps(len(own) - 1):
        gone = set(order[:step])
        control = Control(
            id=cid(item, "drop", step),
            item_id=item.id,
            family="drop",
            level="3",
            expect=NOT_HIGHER,
            answer=" ".join(s for index, s in enumerate(own) if index not in gone),
            how=(
                f"{step} of {len(own)} reference sentences removed, nothing added. It cannot "
                "be better than the answer with fewer sentences removed."
            ),
            base=base,
            dose=step / len(own),
            edits=step,
        )
        made.append(control)
        base = control.id
    return made


def flip(item: Item, seed: int) -> list[Control]:
    """Turn k of n words into their opposite: can -> cannot, days -> weeks."""
    if not item.reference:
        return []
    found = list(_FLIPPABLE.finditer(item.reference))
    if not found:
        return []
    order = rng(seed, item.id, "flip").sample(range(len(found)), len(found))
    made: list[Control] = []
    base = cid(item, "reference")
    for step in dose_steps(len(found)):
        swaps = {index: flip_word(found[index]) for index in order[:step]}
        control = Control(
            id=cid(item, "flip", step),
            item_id=item.id,
            family="flip",
            level="3",
            expect=NOT_HIGHER,
            answer=replace_matches(item.reference, swaps, found),
            how=(
                f"{step} of {len(found)} words in the reference turned into their opposite "
                "or another unit. It cannot be better than the answer with fewer words turned."
            ),
            base=base,
            dose=step / len(found),
            edits=step,
        )
        made.append(control)
        base = control.id
    return made


def contradict(item: Item, seed: int) -> list[Control]:
    """The reference, followed by one of its own sentences with a fact changed."""
    if not item.reference:
        return []
    source = rng(seed, item.id, "contradict")
    candidates = []
    for sentence in sentences(item.reference):
        found = numbers(sentence)
        if found:
            pick = source.randrange(len(found))
            changed = {pick: bump_number(found[pick].group(), source)}
            candidates.append(replace_matches(sentence, changed, found))
            continue
        words = list(_FLIPPABLE.finditer(sentence))
        if words:
            pick = source.randrange(len(words))
            candidates.append(replace_matches(sentence, {pick: flip_word(words[pick])}, words))
    if not candidates:
        return []
    altered = source.choice(candidates)
    return [
        Control(
            id=cid(item, "contradict"),
            item_id=item.id,
            family="contradict",
            level="3",
            expect=NOT_HIGHER,
            answer=f"{item.reference.rstrip()} {altered}",
            how=(
                "The whole reference, then one of its sentences again with one fact changed, "
                "so the answer disagrees with itself. It cannot be better than the reference."
            ),
            base=cid(item, "reference"),
        )
    ]
