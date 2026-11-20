"""Run the controls through the scorer of an Inspect AI task.

Nothing about the task is reimplemented. Its dataset supplies the items, and
its own scorer grades the controls inside a normal Inspect eval whose solver
does one thing: hand back the control's answer as if a model had written it.
That keeps the scorer's real pipeline in play: its prompt template, its
grader model, its parsing, its sandbox.

Needs the optional dependency: pip install "knownbad[inspect]".
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from typing import Any

from .model import Control, Item, Verdict
from .runner import Outcome

ANSWER_KEY = "knownbad_answer"
CONTROL_KEY = "knownbad_control"


class InspectError(Exception):
    pass


def _require() -> Any:
    try:
        import inspect_ai
    except ImportError as error:
        raise InspectError(
            'Inspect AI is not installed. Install it with: pip install "knownbad[inspect]"'
        ) from error
    return inspect_ai


def _text(value: Any) -> str:
    """The text of a sample input or target, whatever shape Inspect gave it."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(part, str) for part in value):
            return str(value[0])  # several accepted targets: the first is the reference
        users = [m for m in value if getattr(m, "role", None) == "user"]
        return _text(getattr(users[-1] if users else value[-1], "text", "")) if value else ""
    return str(getattr(value, "text", value))


def items_from(task: Any) -> tuple[list[Item], dict[str, Any]]:
    """One item per sample of the task, and the samples by item id."""
    items: list[Item] = []
    samples: dict[str, Any] = {}
    for index, sample in enumerate(task.dataset):
        item_id = str(sample.id if sample.id is not None else index + 1)
        if item_id in samples:
            raise InspectError(f"two samples share the id {item_id!r}")
        if sample.choices:
            raise InspectError(
                "multiple-choice tasks are not supported: the controls are free-text answers"
            )
        target = _text(sample.target) if sample.target else None
        meta = dict(sample.metadata or {})
        items.append(
            Item(id=item_id, input=_text(sample.input), reference=target or None, meta=meta)
        )
        samples[item_id] = sample
    if not items:
        raise InspectError("the task has no samples")
    return items, samples


def _replay_solver() -> Any:
    from inspect_ai.model import ModelOutput
    from inspect_ai.solver import Generate, TaskState, solver

    @solver(name="knownbad_replay")
    def replay() -> Any:
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            state.output = ModelOutput.from_content(
                model="knownbad/replay", content=state.metadata[ANSWER_KEY]
            )
            return state

        return solve

    return replay()


def run_task(
    task: Any,
    controls: Sequence[Control],
    samples: dict[str, Any],
    *,
    model: str = "mockllm/model",
    grader_model: str | None = None,
    scorer_name: str | None = None,
    trials: int = 1,
    pass_score: float = 0.5,
    max_connections: int | None = None,
    log_dir: str | None = None,
) -> tuple[list[Outcome], dict[str, dict[str, int]]]:
    """Grade the controls with the task's scorer. Returns outcomes and token use by model."""
    inspect_ai = _require()
    from inspect_ai.dataset import MemoryDataset
    from inspect_ai.scorer import value_to_float

    replayed = []
    for control in controls:
        original = samples[control.item_id]
        metadata = dict(original.metadata or {})
        metadata[ANSWER_KEY] = control.answer
        metadata[CONTROL_KEY] = control.id
        replayed.append(original.model_copy(update={"id": control.id, "metadata": metadata}))

    wrapped = inspect_ai.task_with(task, dataset=MemoryDataset(replayed), solver=_replay_solver())
    options: dict[str, Any] = {
        "model": model,
        "epochs": trials,
        "display": "none",
        "log_level": "error",
        "fail_on_error": False,
    }
    if grader_model:
        options["model_roles"] = {"grader": grader_model}
    if max_connections:
        options["max_connections"] = max_connections

    with tempfile.TemporaryDirectory() as scratch:
        try:
            log = inspect_ai.eval(wrapped, log_dir=log_dir or scratch, **options)[0]
        except Exception as error:  # Inspect raises many kinds; all mean "did not run"
            raise InspectError(
                f"the Inspect eval did not run: {type(error).__name__}: {error}"
            ) from error
        if log.status != "success" and not log.samples:
            reason = getattr(log.error, "message", None) or log.status
            raise InspectError(f"the Inspect eval did not run: {reason}")
        to_float = value_to_float()
        verdicts: dict[str, list[Verdict]] = {c.id: [] for c in controls}
        for sample in log.samples or []:
            verdicts[str(sample.id)].append(_verdict(sample, scorer_name, to_float, pass_score))
        usage = {
            name: {
                "input_tokens": use.input_tokens,
                "output_tokens": use.output_tokens,
                "reasoning_tokens": getattr(use, "reasoning_tokens", None) or 0,
            }
            for name, use in (log.stats.model_usage if log.stats else {}).items()
        }

    missing = Verdict(passed=None, error="Inspect returned no sample for this control")
    return (
        [Outcome(c, tuple(verdicts[c.id]) or (missing,)) for c in controls],
        usage,
    )


def _verdict(sample: Any, scorer_name: str | None, to_float: Any, pass_score: float) -> Verdict:
    if sample.error is not None:
        return Verdict(passed=None, error=str(getattr(sample.error, "message", sample.error))[:300])
    scores = sample.scores or {}
    if scorer_name is not None and scorer_name not in scores:
        known = ", ".join(scores) or "none"
        return Verdict(passed=None, error=f"no score named {scorer_name!r}; the task has: {known}")
    score = scores[scorer_name] if scorer_name else next(iter(scores.values()), None)
    if score is None:
        return Verdict(passed=None, error="the scorer returned no score")
    try:
        value = float(to_float(score.value))
    except (TypeError, ValueError):
        return Verdict(passed=None, error=f"cannot read score value {score.value!r}")
    return Verdict(passed=value >= pass_score, score=value, explanation=score.explanation or None)
