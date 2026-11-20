"""Small, deterministic text helpers. No language model, no tokenizer."""

from __future__ import annotations

import random
import re

_WS = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$")
# A sentence ends at . ! or ? followed by space and something that starts a
# new sentence, or at a line break. "3.5" and "e.g. x" stay in one piece.
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])|\n+")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?![\w]|\.\d)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on or "
    "that the their then there these this to was were will with must should answer "
    "response states state says say mention mentions".split()
)


def normalise(text: str) -> str:
    """Lower-case, single spaces, no punctuation at either end."""
    return _EDGE_PUNCT.sub("", _WS.sub(" ", text).strip().lower())


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part and part.strip()]


def numbers(text: str) -> list[re.Match[str]]:
    return list(_NUMBER.finditer(text))


def words_without_numbers(text: str) -> list[str]:
    return _WORD.findall(_NUMBER.sub(" ", text))


def content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 3 and w.lower() not in _STOPWORDS}


def overlap(needle: str, haystack: str) -> float:
    """Share of the content words of `needle` that also occur in `haystack`."""
    wanted = content_words(needle) | {m.group() for m in numbers(needle)}
    if not wanted:
        return 0.0
    have = content_words(haystack) | {m.group() for m in numbers(haystack)}
    return len(wanted & have) / len(wanted)


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000", "million": "1000000",
}  # fmt: skip
_AGREE = {"yes": "yes", "true": "yes", "correct": "yes", "no": "no", "false": "no",
          "incorrect": "no"}  # fmt: skip
# Words that turn a number into a range or an estimate.
HEDGES = frozenset(
    "about around roughly approximately approx nearly almost circa some over under above "
    "below more less least most up than between".split()
)


def number_values(text: str) -> set[str]:
    """The numbers a text states, written one way: "1,000", "1000" and "thousand" agree."""
    values = {m.group().replace(",", "") for m in numbers(text)}
    values |= {_NUMBER_WORDS[w.lower()] for w in _WORD.findall(text) if w.lower() in _NUMBER_WORDS}
    return {v.rstrip("0").rstrip(".") if "." in v else v for v in values}


def fact_words(text: str) -> set[str]:
    """Every word that carries meaning, of any length: "yes", "NYC" and "Au" count."""
    words = {w.lower() for w in _WORD.findall(text)}
    return {_AGREE.get(w, w) for w in words if w not in _STOPWORDS and w not in _NUMBER_WORDS}


def may_answer(candidate: str, reference: str) -> bool:
    """Could `candidate` be read as a right answer where `reference` is the right one?

    Deliberately eager to say yes. It decides whether an answer is safe to
    call wrong, and a control that might be right is worse than no control.
    """
    if same_answer(candidate, reference):
        return True
    if number_values(candidate) & number_values(reference):
        return True
    theirs, own = fact_words(candidate), fact_words(reference)
    if not theirs or not own:
        return False
    shared = theirs & own
    # A short text is its facts: one shared word is enough to doubt it.
    if min(len(theirs), len(own)) <= 3:
        return bool(shared)
    # Either text mostly restating the other.
    return len(shared) / len(own) > 0.25 or len(shared) / len(theirs) > 0.5


def same_answer(a: str, b: str) -> bool:
    """True when one text could be read as the other: equal or contained."""
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return na == nb
    return na == nb or na in nb or nb in na


def bump_number(literal: str, rng: random.Random) -> str:
    """A different number written the same way: 14 -> 16, 1,200 -> 1,203, 3.5 -> 3.7.

    The change is small on purpose. A wild number is easy to catch; a near
    miss is the error a grader has to be able to see.
    """
    step = rng.choice((1, 2, 3))
    if "." in literal:
        whole, frac = literal.split(".")
        digits = len(frac)
        value = int(frac)
        changed = (value + step) % (10**digits)
        if changed == value:  # only possible for a one-digit wrap, kept for safety
            changed = (value + 1) % (10**digits)
        return f"{whole}.{changed:0{digits}d}"
    grouped = "," in literal
    plain = literal.replace(",", "")
    value = int(plain)
    changed = value + step if value < 3 or rng.random() < 0.5 else value - step
    text = f"{changed:,}" if grouped else str(changed)
    return text.zfill(len(plain)) if not grouped and plain.startswith("0") else text


def replace_matches(text: str, swaps: dict[int, str], found: list[re.Match[str]]) -> str:
    """Rewrite `text`, replacing the matches whose index is in `swaps`."""
    out: list[str] = []
    cursor = 0
    for index, match in enumerate(found):
        if index not in swaps:
            continue
        out.append(text[cursor : match.start()])
        out.append(swaps[index])
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out)
