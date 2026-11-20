"""The three records everything else passes around."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# What a grader must do with a control.
FAIL = "fail"  # the answer is wrong by construction
PASS = "pass"  # the answer is right by construction
NOT_HIGHER = "not_higher"  # the answer cannot be better than its base control
EXPECTATIONS = (FAIL, PASS, NOT_HIGHER)

GOOD_LEVEL = "good"
LEVELS = (GOOD_LEVEL, "0", "1", "2", "3", "4")


@dataclass(frozen=True)
class Item:
    """One eval case: what was asked and, when known, the right answer."""

    id: str
    input: str
    reference: str | None = None
    rubric: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Item:
        if "id" not in raw or "input" not in raw:
            raise ValueError(f"an item needs 'id' and 'input': {raw!r}")
        known = {"id", "input", "reference", "rubric", "meta"}
        meta = dict(raw.get("meta") or {})
        # Unknown top-level keys are kept, so a grader still sees its own fields.
        meta.update({k: v for k, v in raw.items() if k not in known})
        return cls(
            id=str(raw["id"]),
            input=str(raw["input"]),
            reference=None if raw.get("reference") is None else str(raw["reference"]),
            rubric=None if raw.get("rubric") is None else str(raw["rubric"]),
            meta=meta,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Control:
    """An answer whose verdict is known before the grader sees it."""

    id: str
    item_id: str
    family: str
    level: str
    expect: str
    answer: str
    how: str
    base: str | None = None  # control id this one is compared to (not_higher)
    dose: float | None = None  # share of the reference that was corrupted, 0..1
    edits: int | None = None  # how many units were corrupted

    def __post_init__(self) -> None:
        if self.expect not in EXPECTATIONS:
            raise ValueError(f"unknown expectation {self.expect!r}")
        if self.level not in LEVELS:
            raise ValueError(f"unknown level {self.level!r}")
        if self.expect == NOT_HIGHER and not self.base:
            raise ValueError(f"{self.id}: a not_higher control needs a base")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Control:
        return cls(**{k: raw.get(k) for k in cls.__dataclass_fields__ if k in raw})

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class Verdict:
    """What the grader said about one answer."""

    passed: bool | None  # None when the grader errored
    score: float | None = None
    explanation: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Verdict:
        return cls(
            passed=raw.get("passed"),
            score=raw.get("score"),
            explanation=raw.get("explanation"),
            error=raw.get("error"),
        )
