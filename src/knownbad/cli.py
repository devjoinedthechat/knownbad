"""Command line: gen, run, report."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .analyze import gate, summarise
from .cache import Cache, fingerprint
from .compare import compare, regressions
from .controls import FAMILIES, build
from .grader import command_grader, load_callable, python_grader
from .io import (
    read_controls,
    read_harvested,
    read_items,
    read_json,
    write_controls,
    write_json,
    write_text,
)
from .report import render_diff, render_text
from .runner import Outcome, run

SCHEMA = 1
EXIT_OK, EXIT_GATE, EXIT_VOID = 0, 1, 2


class UsageError(Exception):
    pass


def _families(text: str | None) -> list[str]:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def _level_limits(pairs: list[str]) -> dict[str, float]:
    limits: dict[str, float] = {}
    for pair in pairs:
        level, _, value = pair.partition("=")
        if level.strip() not in ("0", "1", "2", "3", "4"):
            raise UsageError(f"--max-leak-level: there is no level {level.strip()!r}; use 0 to 4")
        try:
            limits[level.strip()] = float(value)
        except ValueError:
            raise UsageError(f"--max-leak-level wants LEVEL=RATE, got {pair!r}") from None
    return limits


def _load_controls(args: argparse.Namespace, items: dict[str, Any]) -> list[Any]:
    if getattr(args, "controls", None):
        controls = read_controls(args.controls)
    else:
        controls = build(list(items.values()), seed=args.seed, skip=_families(args.skip))
    if getattr(args, "harvested", None):
        controls = [*controls, *read_harvested(args.harvested, items)]
    return controls


def cmd_gen(args: argparse.Namespace) -> int:
    items = {item.id: item for item in read_items(args.items)}
    controls = _load_controls(args, items)
    write_controls(args.out, controls)
    counts = Counter(c.family for c in controls)
    print(f"{len(controls)} controls for {len(items)} items → {args.out}")
    for family in sorted(counts):
        print(f"  {family:<24}{counts[family]:>6}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    if bool(args.grader) == bool(args.cmd):
        raise UsageError("give exactly one of --grader or --cmd")
    items = {item.id: item for item in read_items(args.items)}
    controls = _load_controls(args, items)
    if not controls:
        raise UsageError("no controls to run")
    if args.grader:
        grader = python_grader(load_callable(args.grader), args.pass_score)
    else:
        grader = command_grader(args.cmd, args.pass_score, args.timeout)

    show = sys.stderr.isatty() and not args.quiet

    def progress(done: int, total: int) -> None:
        if show:
            print(f"\r  grading {done}/{total}", end="", file=sys.stderr, flush=True)

    cache = None
    if args.cache:
        cache = Cache(args.cache, fingerprint(args.grader, args.cmd, args.pass_score))
    outcomes = run(
        controls, items, grader, args.trials, args.workers, progress, cache, args.retries
    )
    if show:
        print("\r" + " " * 40 + "\r", end="", file=sys.stderr)

    if cache and not args.quiet:
        calls = len(controls) * args.trials
        print(f"{cache.hits} of {calls} verdicts came from {args.cache}\n")
    return _finish(args, outcomes, items, args.grader or args.cmd)


def make_result(
    outcomes: list[Outcome],
    items: dict[str, Any],
    grader: str,
    trials: int = 1,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The result file: everything a report needs, and nothing it has to recompute."""
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "knownbad": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grader": grader,
        "trials": trials,
        "summary": summarise(outcomes),
        "items": {
            item.id: {"input": item.input, "reference": item.reference, "rubric": item.rubric}
            for item in items.values()
        },
        "outcomes": [o.to_dict() for o in outcomes],
    }
    if usage:
        result["usage"] = usage
    return result


def _finish(
    args: argparse.Namespace,
    outcomes: list[Outcome],
    items: dict[str, Any],
    grader: str,
    usage: dict[str, Any] | None = None,
) -> int:
    """Summarise, write the files that were asked for, print, and gate."""
    result = make_result(outcomes, items, grader, args.trials, usage)
    summary = result["summary"]
    if args.out:
        write_json(args.out, result)
    if args.html:
        from .report.html import render as render_html

        write_text(args.html, render_html(result))
    if not args.quiet:
        print(render_text(result), end="")
        for name, use in (usage or {}).items():
            print(f"\nTokens · {name}: {use['input_tokens']:,} in, {use['output_tokens']:,} out")
        if args.html:
            print(f"\nReport: {args.html}")

    reasons = gate(summary, args.max_leak, _level_limits(args.max_leak_level))
    for reason in reasons:
        print(f"FAIL  {reason}", file=sys.stderr)
    if summary["void"]:
        return EXIT_VOID
    return EXIT_GATE if reasons else EXIT_OK


def cmd_inspect(args: argparse.Namespace) -> int:
    from .inspect_adapter import InspectError, items_from, run_task

    try:
        task = load_callable(args.task)()
        item_list, samples = items_from(task)
        items = {item.id: item for item in item_list}
        if args.controls:
            controls = read_controls(args.controls)
        else:
            controls = build(item_list, seed=args.seed, skip=_families(args.skip))
        if args.harvested:
            controls = [*controls, *read_harvested(args.harvested, items)]
        unknown = sorted({c.item_id for c in controls} - set(items))
        if unknown:
            raise UsageError(f"controls refer to samples the task does not have: {unknown[:5]}")
        outcomes, usage = run_task(
            task,
            controls,
            samples,
            model=args.model,
            grader_model=args.grader_model,
            scorer_name=args.scorer,
            trials=args.trials,
            pass_score=args.pass_score,
            max_connections=args.workers,
            log_dir=args.log_dir,
        )
    except InspectError as error:
        raise UsageError(str(error)) from error
    label = f"inspect {args.task}"
    if args.grader_model or args.model != "mockllm/model":
        label += f" · {args.grader_model or args.model}"
    return _finish(args, outcomes, items, label, usage)


def cmd_report(args: argparse.Namespace) -> int:
    result = read_json(args.result)
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise UsageError(f"{args.result} is not a knownbad result file of schema {SCHEMA}")
    if args.recompute:
        outcomes = [Outcome.from_dict(o) for o in result["outcomes"]]
        result["summary"] = summarise(outcomes)
    if args.html:
        from .report.html import render as render_html

        write_text(args.html, render_html(result))
        print(f"Report: {args.html}")
    else:
        print(render_text(result, limit=args.limit), end="")
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    old, new = read_json(args.old), read_json(args.new)
    for path, result in ((args.old, old), (args.new, new)):
        if not isinstance(result, dict) or result.get("schema") != SCHEMA:
            raise UsageError(f"{path} is not a knownbad result file of schema {SCHEMA}")
    diff = compare(old, new)
    if args.json:
        write_json(args.json, diff)
    if not args.quiet:
        print(render_diff(diff, limit=args.limit), end="")
    reasons = regressions(diff) if args.fail_on_regression else []
    for reason in reasons:
        print(f"FAIL  {reason}", file=sys.stderr)
    return EXIT_GATE if reasons else EXIT_OK


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--controls", metavar="FILE", help="a frozen controls file from 'gen'")
    parser.add_argument("--trials", type=int, default=1, help="grade each control this many times")
    parser.add_argument("--workers", type=int, default=4, help="controls graded at once")
    parser.add_argument(
        "--pass-score", type=float, default=0.5, help="a numeric score at or above this passes"
    )
    parser.add_argument("-o", "--out", metavar="FILE", help="write the full result as JSON")
    parser.add_argument("--html", metavar="FILE", help="write a single-file HTML report")
    parser.add_argument(
        "--max-leak", type=float, metavar="RATE", help="exit 1 above this leak rate"
    )
    parser.add_argument(
        "--max-leak-level",
        action="append",
        default=[],
        metavar="LEVEL=RATE",
        help="exit 1 when one level leaks more than this; repeatable",
    )
    parser.add_argument("-q", "--quiet", action="store_true")


def _add_build_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=0, help="seed for the control builders")
    parser.add_argument(
        "--skip",
        metavar="FAMILIES",
        help=f"comma-separated families to leave out: {', '.join(FAMILIES)}",
    )
    parser.add_argument(
        "--harvested", metavar="FILE", help="answers you labeled yourself, as JSON Lines"
    )


def _add_control_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("items", help="items as JSON Lines: id, input, reference, rubric")
    _add_build_options(parser)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="knownbad",
        description="Negative controls for evals: find out what your grader actually checks.",
    )
    top.add_argument("--version", action="version", version=f"knownbad {__version__}")
    commands = top.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("gen", help="write the controls for a set of items to a file")
    _add_control_source(gen)
    gen.add_argument("-o", "--out", default="controls.jsonl")
    gen.set_defaults(run=cmd_gen)

    runp = commands.add_parser("run", help="put the controls through a grader")
    _add_control_source(runp)
    runp.add_argument("--grader", metavar="MODULE:FUNC", help="a Python function (item, answer)")
    runp.add_argument("--cmd", metavar="COMMAND", help="a shell command: JSON in, verdict out")
    runp.add_argument("--timeout", type=float, default=120.0, help="seconds, for --cmd")
    runp.add_argument(
        "--cache", metavar="FILE", help="keep verdicts here, so a stopped run does not pay twice"
    )
    runp.add_argument(
        "--retries",
        type=int,
        default=0,
        help="ask again up to this many times when the grader returns no verdict",
    )
    _add_run_options(runp)
    runp.set_defaults(run=cmd_run)

    insp = commands.add_parser(
        "inspect", help="put the controls through the scorer of an Inspect AI task"
    )
    insp.add_argument(
        "task", metavar="FILE.py:TASK", help="a function that returns an Inspect Task"
    )
    insp.add_argument(
        "--model",
        default="mockllm/model",
        help="model for scorers that grade with the eval's model",
    )
    insp.add_argument("--grader-model", metavar="MODEL", help="model for the task's grader role")
    insp.add_argument(
        "--scorer", metavar="NAME", help="which score to read when the task has several"
    )
    insp.add_argument("--log-dir", metavar="DIR", help="keep the Inspect log here")
    _add_build_options(insp)
    _add_run_options(insp)
    insp.set_defaults(run=cmd_inspect)

    diff = commands.add_parser("diff", help="compare two runs made from the same controls")
    diff.add_argument("old", help="the baseline result file")
    diff.add_argument("new", help="the result file to judge against it")
    diff.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit 1 when a caught control now passes or a passing reference now fails",
    )
    diff.add_argument("--json", metavar="FILE", help="write the comparison as JSON")
    diff.add_argument("--limit", type=int, default=10, help="controls to list per kind of change")
    diff.add_argument("-q", "--quiet", action="store_true")
    diff.set_defaults(run=cmd_diff)

    report = commands.add_parser("report", help="show a saved result again")
    report.add_argument("result")
    report.add_argument("--html", metavar="FILE", help="write a single-file HTML report")
    report.add_argument("--limit", type=int, default=8, help="leaked controls to list")
    report.add_argument("--recompute", action="store_true", help="redo the summary from outcomes")
    report.set_defaults(run=cmd_report)
    return top


def main(argv: list[str] | None = None) -> int:
    # The report uses a few non-ASCII characters; a Windows pipe defaults to a
    # code page that cannot encode them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    try:
        return int(args.run(args))
    except (UsageError, ValueError, OSError) as error:
        print(f"knownbad: {error}", file=sys.stderr)
        return EXIT_VOID


if __name__ == "__main__":
    raise SystemExit(main())
