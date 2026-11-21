"""Put every control through the grader and keep exactly what it said."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .cache import Cache
from .grader import Grader
from .model import Control, Item, Verdict


@dataclass(frozen=True)
class Outcome:
    control: Control
    verdicts: tuple[Verdict, ...]

    @property
    def graded(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.passed is not None)

    @property
    def errored(self) -> bool:
        """True when no trial produced a verdict."""
        return not self.graded

    @property
    def pass_share(self) -> float | None:
        graded = self.graded
        if not graded:
            return None
        return sum(1 for v in graded if v.passed) / len(graded)

    @property
    def passed(self) -> bool | None:
        """Majority over trials. A tie counts as a pass: for a negative
        control that is the careful reading, and references are never close."""
        share = self.pass_share
        return None if share is None else share >= 0.5

    @property
    def flaky(self) -> bool:
        share = self.pass_share
        return share is not None and 0.0 < share < 1.0

    @property
    def mean_score(self) -> float | None:
        scores = [v.score for v in self.graded if v.score is not None]
        return sum(scores) / len(scores) if scores else None

    def to_dict(self) -> dict[str, Any]:
        return {"control": self.control.to_dict(), "verdicts": [v.to_dict() for v in self.verdicts]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Outcome:
        return cls(
            control=Control.from_dict(raw["control"]),
            verdicts=tuple(Verdict.from_dict(v) for v in raw["verdicts"]),
        )


def run(
    controls: Sequence[Control],
    items: Mapping[str, Item],
    grader: Grader,
    trials: int = 1,
    workers: int = 4,
    on_progress: Callable[[int, int], None] | None = None,
    cache: Cache | None = None,
    retries: int = 0,
    retry_wait: float = 1.0,
) -> list[Outcome]:
    """Grade every control `trials` times. Order of the result matches `controls`.

    A call that returns no verdict is made again up to `retries` times, with a
    wait that doubles. With a cache, a verdict already on disk is not asked for.
    """
    if trials < 1:
        raise ValueError("trials must be at least 1")
    missing = sorted({c.item_id for c in controls} - set(items))
    if missing:
        raise ValueError(f"controls refer to items that are not loaded: {', '.join(missing[:5])}")

    jobs = [
        (index, control, trial) for index, control in enumerate(controls) for trial in range(trials)
    ]
    verdicts: list[list[Verdict]] = [[] for _ in controls]

    def grade(job: tuple[int, Control, int]) -> tuple[int, Verdict]:
        index, control, trial = job
        item = items[control.item_id]

        def ask() -> Verdict:
            verdict = grader(item, control.answer)
            for attempt in range(retries):
                if verdict.passed is not None:
                    break
                time.sleep(retry_wait * 2**attempt)
                verdict = grader(item, control.answer)
            return verdict

        if cache is None:
            return index, ask()
        return index, cache.get_or_ask(cache.key(item, control, trial), ask)

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for index, verdict in pool.map(grade, jobs):
            verdicts[index].append(verdict)
            done += 1
            if on_progress:
                on_progress(done, len(jobs))

    return [Outcome(control, tuple(got)) for control, got in zip(controls, verdicts, strict=True)]
