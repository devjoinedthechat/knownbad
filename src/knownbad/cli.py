"""Command line: gen, run, report."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .analyze import gate, summarise
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
from .report import render_text
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

    outcomes = run(controls, items, grader, args.trials, args.workers, progress)
    if show:
        print("\r" + " " * 40 + "\r", end="", file=sys.stderr)

    summary = summarise(outcomes)
    result = {
        "schema": SCHEMA,
        "knownbad": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grader": args.grader or args.cmd,
        "trials": args.trials,
        "summary": summary,
        "items": {
            item.id: {"input": item.input, "reference": item.reference, "rubric": item.rubric}
            for item in items.values()
        },
        "outcomes": [o.to_dict() for o in outcomes],
    }
    if args.out:
        write_json(args.out, result)
    if args.html:
        from .report.html import render as render_html

        write_text(args.html, render_html(result))
    if not args.quiet:
        print(render_text(result), end="")
        if args.html:
            print(f"\nReport: {args.html}")

    reasons = gate(summary, args.max_leak, _level_limits(args.max_leak_level))
    for reason in reasons:
        print(f"FAIL  {reason}", file=sys.stderr)
    if summary["void"]:
        return EXIT_VOID
    return EXIT_GATE if reasons else EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    result = read_json(args.result)
    if result.get("schema") != SCHEMA:
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


def _add_control_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("items", help="items as JSON Lines: id, input, reference, rubric")
    parser.add_argument("--seed", type=int, default=0, help="seed for the control builders")
    parser.add_argument(
        "--skip",
        metavar="FAMILIES",
        help=f"comma-separated families to leave out: {', '.join(FAMILIES)}",
    )
    parser.add_argument(
        "--harvested", metavar="FILE", help="answers you labeled yourself, as JSON Lines"
    )


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="knownbad",
        description="Negative controls for evals: how many wrong answers does your grader accept?",
    )
    top.add_argument("--version", action="version", version=f"knownbad {__version__}")
    commands = top.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("gen", help="write the controls for a set of items to a file")
    _add_control_source(gen)
    gen.add_argument("-o", "--out", default="controls.jsonl")
    gen.set_defaults(run=cmd_gen)

    runp = commands.add_parser("run", help="put the controls through a grader")
    _add_control_source(runp)
    runp.add_argument("--controls", metavar="FILE", help="a frozen controls file from 'gen'")
    runp.add_argument("--grader", metavar="MODULE:FUNC", help="a Python function (item, answer)")
    runp.add_argument("--cmd", metavar="COMMAND", help="a shell command: JSON in, verdict out")
    runp.add_argument("--trials", type=int, default=1, help="grade each control this many times")
    runp.add_argument("--workers", type=int, default=4)
    runp.add_argument("--timeout", type=float, default=120.0, help="seconds, for --cmd")
    runp.add_argument(
        "--pass-score", type=float, default=0.5, help="a numeric score at or above this passes"
    )
    runp.add_argument("-o", "--out", metavar="FILE", help="write the full result as JSON")
    runp.add_argument("--html", metavar="FILE", help="write a single-file HTML report")
    runp.add_argument("--max-leak", type=float, metavar="RATE", help="exit 1 above this leak rate")
    runp.add_argument(
        "--max-leak-level",
        action="append",
        default=[],
        metavar="LEVEL=RATE",
        help="exit 1 when one level leaks more than this; repeatable",
    )
    runp.add_argument("-q", "--quiet", action="store_true")
    runp.set_defaults(run=cmd_run)

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
        return args.run(args)
    except (UsageError, ValueError, OSError) as error:
        print(f"knownbad: {error}", file=sys.stderr)
        return EXIT_VOID


if __name__ == "__main__":
    raise SystemExit(main())
