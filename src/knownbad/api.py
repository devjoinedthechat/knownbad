"""The one-call Python API, for use inside a test suite.

from knownbad import check

def test_judge_catches_wrong_answers():
    report = check(items, judge)
    assert not report.void
    assert report.leak_rate() <= 0.02, report.leaks[:5]
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .analyze import summarise
from .controls import build
from .grader import python_grader
from .model import Control, Item
from .runner import Outcome, run


@dataclass(frozen=True)
class Report:
    """The outcome of one run, with the numbers most tests want as attributes."""

    outcomes: tuple[Outcome, ...]
    summary: dict[str, Any]
    items: dict[str, Item]
    grader: str
    trials: int

    @property
    def void(self) -> bool:
        """True when the run cannot be trusted, such as a grader that fails its references."""
        return self.summary["void"] is not None

    @property
    def leaks(self) -> list[Control]:
        """The must-fail controls that passed."""
        wanted = set(self.summary["leaks"])
        return [o.control for o in self.outcomes if o.control.id in wanted]

    def leak_rate(self, level: str | int | None = None) -> float:
        """Share of must-fail controls that passed, overall or for one level."""
        if level is None:
            found = self.summary["overall"]["rate"]
        else:
            rows = [r for r in self.summary["levels"] if r["level"] == str(level)]
            found = rows[0]["rate"] if rows else None
        return 0.0 if found is None else float(found)

    def threshold(self, family: str) -> tuple[float, float] | None:
        """The dose range in which the grader first fails at least half, or None if never."""
        curve = self.summary["dose"].get(family)
        if curve is None:
            raise KeyError(f"no dose controls of family {family!r} in this run")
        return (
            None if curve["threshold"] is None else (curve["threshold"][0], curve["threshold"][1])
        )

    def to_result(self) -> dict[str, Any]:
        from .cli import make_result

        return make_result(list(self.outcomes), self.items, self.grader, self.trials)

    def to_html(self) -> str:
        from .report.html import render

        return render(self.to_result())

    def __str__(self) -> str:
        from .report.text import render

        return render(self.to_result())


def check(
    items: Iterable[Item | dict[str, Any]],
    grader: Callable[[dict[str, Any], str], Any],
    *,
    controls: Sequence[Control] | None = None,
    seed: int = 0,
    skip: Iterable[str] = (),
    trials: int = 1,
    workers: int = 4,
    pass_score: float = 0.5,
) -> Report:
    """Build the controls for `items`, run them through `grader`, and summarise."""
    loaded = [i if isinstance(i, Item) else Item.from_dict(i) for i in items]
    by_id = {item.id: item for item in loaded}
    built = list(controls) if controls is not None else build(loaded, seed=seed, skip=skip)
    outcomes = run(built, by_id, python_grader(grader, pass_score), trials, workers)
    name = getattr(grader, "__qualname__", None) or type(grader).__name__
    return Report(tuple(outcomes), summarise(outcomes), by_id, str(name), trials)
