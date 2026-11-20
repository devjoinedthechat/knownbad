"""Helpers every control builder shares."""

from __future__ import annotations

import math
import random

from ..model import Item

MAX_DOSE_STEPS = 4


def rng(seed: int, item_id: str, family: str) -> random.Random:
    # A string seed is hashed the same way on every run and platform.
    return random.Random(f"{seed}\x1f{item_id}\x1f{family}")


def cid(item: Item, family: str, step: int | None = None) -> str:
    return f"{item.id}::{family}" if step is None else f"{item.id}::{family}@{step}"


def dose_steps(units: int) -> list[int]:
    """Up to four nested steps ending at `units`: 5 -> [2, 3, 4, 5]."""
    quarters = (i / MAX_DOSE_STEPS for i in range(1, MAX_DOSE_STEPS + 1))
    return sorted({max(1, math.ceil(units * q)) for q in quarters})
