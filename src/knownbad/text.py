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
