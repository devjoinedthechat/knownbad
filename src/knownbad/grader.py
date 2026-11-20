"""Turn whatever the user has into one shape: (item, answer) -> Verdict.

Two ways in. A Python callable, named as "package.module:function" or
"path/to/file.py:function". Or a shell command that reads
{"item": ..., "answer": ...} as JSON on stdin and prints a verdict as JSON on
its last output line, which works for a grader in any language.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .model import Item, Verdict

Grader = Callable[[Item, str], Verdict]

_PASS_WORDS = {"pass", "passed", "true", "yes", "correct", "c", "accept", "accepted"}
_FAIL_WORDS = {"fail", "failed", "false", "no", "incorrect", "i", "reject", "rejected"}


def to_verdict(raw: Any, pass_score: float) -> Verdict:
    """Read a grader's return value. Anything unreadable is an error, never a fail."""
    if isinstance(raw, Verdict):
        return raw
    if isinstance(raw, bool):
        return Verdict(passed=raw)
    if isinstance(raw, (int, float)):
        return Verdict(passed=raw >= pass_score, score=float(raw))
    if isinstance(raw, str):
        word = raw.strip().lower()
        if word in _PASS_WORDS:
            return Verdict(passed=True)
        if word in _FAIL_WORDS:
            return Verdict(passed=False)
        return Verdict(passed=None, error=f"cannot read verdict from text {raw[:80]!r}")
    if isinstance(raw, dict):
        score = raw.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            score = None
        passed = raw.get("passed", raw.get("pass"))
        if isinstance(passed, str):
            inner = to_verdict(passed, pass_score)
            passed = inner.passed
        if passed is None and score is not None:
            passed = score >= pass_score
        if not isinstance(passed, bool):
            return Verdict(passed=None, error=f"no 'passed' or 'score' in {str(raw)[:120]}")
        explanation = raw.get("explanation", raw.get("reason"))
        return Verdict(
            passed=passed,
            score=None if score is None else float(score),
            explanation=None if explanation is None else str(explanation),
        )
    return Verdict(passed=None, error=f"cannot read verdict from {type(raw).__name__}")


def load_callable(spec: str) -> Callable[..., Any]:
    if ":" not in spec:
        raise ValueError(f"grader must look like 'module:function' or 'file.py:function': {spec}")
    target, _, name = spec.rpartition(":")
    if target.endswith(".py"):
        path = Path(target).resolve()
        if not path.is_file():
            raise ValueError(f"no such file: {target}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        if module_spec is None or module_spec.loader is None:
            raise ValueError(f"cannot load {target}")
        module = importlib.util.module_from_spec(module_spec)
        sys.path.insert(0, str(path.parent))
        try:
            module_spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(path.parent))
    else:
        if "" not in sys.path and "." not in sys.path:
            sys.path.insert(0, "")
        module = importlib.import_module(target)
    try:
        function = getattr(module, name)
    except AttributeError:
        raise ValueError(f"{target} has no function {name!r}") from None
    if not callable(function):
        raise ValueError(f"{spec} is not callable")
    return function


def python_grader(function: Callable[..., Any], pass_score: float = 0.5) -> Grader:
    def grade(item: Item, answer: str) -> Verdict:
        try:
            return to_verdict(function(item.to_dict(), answer), pass_score)
        except Exception as error:  # the grader is user code; report, never guess
            return Verdict(passed=None, error=f"{type(error).__name__}: {error}")

    return grade


def command_grader(command: str, pass_score: float = 0.5, timeout: float = 120.0) -> Grader:
    def grade(item: Item, answer: str) -> Verdict:
        # ASCII-only JSON, so the command reads it the same under any locale.
        payload = json.dumps({"item": item.to_dict(), "answer": answer})
        try:
            done = subprocess.run(  # noqa: S602 - the user's own command, by design
                command,
                shell=True,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return Verdict(passed=None, error=f"timed out after {timeout:g}s")
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
            return Verdict(passed=None, error=f"exit {done.returncode}: {detail[0][:200]}")
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        if not lines:
            return Verdict(passed=None, error="the command printed nothing")
        try:
            raw: Any = json.loads(lines[-1])
        except json.JSONDecodeError:
            raw = lines[-1]
        return to_verdict(raw, pass_score)

    return grade
