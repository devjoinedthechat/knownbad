"""The terminal report."""

from __future__ import annotations

from typing import Any

LEVEL_NAMES = {
    "0": "no answer",
    "1": "grader attack",
    "2": "wrong question",
    "3": "edited reference",
    "4": "harvested",
}
DOSE_UNITS = {"splice": "sentences replaced", "numbers": "numbers changed"}


def pct(value: float | None) -> str:
    return "–" if value is None else f"{value * 100:.0f}%"


def span(row: dict[str, Any]) -> str:
    if row.get("low") is None:
        return "–"
    return f"{row['low'] * 100:.0f}–{row['high'] * 100:.0f}%"


def dose_label(point: dict[str, Any]) -> str:
    return "untouched" if point["dose_high"] == 0 else f"≤{pct(point['dose_high'])}"


def threshold_sentence(family: str, curve: dict[str, Any]) -> str:
    unit = DOSE_UNITS.get(family, "units changed")
    corrupted = [p for p in curve["points"] if p["dose_high"] > 0]
    if not corrupted:
        return "not measured"
    if curve["threshold"] is None:
        last = corrupted[-1]
        still, dose = pct(last["rate"]), pct(last["dose_high"])
        return f"never fails half: {still} still pass with {dose} of {unit}"
    low, high = curve["threshold"]
    share = f"up to {pct(high)}" if low == 0 else f"{low * 100:.0f}–{pct(high)}"
    return f"fails at least half with {share} of {unit}"


def render(result: dict[str, Any], limit: int = 8) -> str:
    summary = result["summary"]
    lines: list[str] = []
    out = lines.append

    trials = result.get("trials", 1)
    out(
        f"knownbad · {summary['controls']} controls × {trials} "
        f"trial{'s' if trials != 1 else ''} · grader: {result.get('grader', '?')}"
    )
    out("")
    if summary["void"]:
        out(f"VOID  {summary['void']}")
        out("")
    if summary["errors"]:
        out(f"Grader errors: {summary['errors']} controls got no verdict and are not counted.")
        for example in summary["error_examples"]:
            out(f"  {example['id']}: {example['error']}")
        out("")

    refs = summary["references"]
    if refs["n"]:
        out(f"Reference answers passed   {refs['k']} / {refs['n']}   {pct(refs['rate'])}")
        out("")

    if summary["families"]:
        out("Wrong answers that passed")
        out(f"  {'level':<21}{'control':<24}{'leaked':>11}{'rate':>7}   95% interval")
        for row in summary["families"]:
            level = f"{row['level']} {LEVEL_NAMES.get(row['level'], '')}"
            count = f"{row['k']} / {row['n']}"
            out(f"  {level:<21}{row['family']:<24}{count:>11}{pct(row['rate']):>7}   {span(row)}")
        total = summary["overall"]
        count = f"{total['k']} / {total['n']}"
        out(f"  {'all':<21}{'':<24}{count:>11}{pct(total['rate']):>7}   {span(total)}")
        out("")

    if summary["dose"]:
        out("Detection threshold")
        for family, curve in summary["dose"].items():
            out(f"  {family:<9} {threshold_sentence(family, curve)}")
            steps = " · ".join(f"{dose_label(p)} {pct(p['rate'])}" for p in curve["points"])
            out(f"            pass rate by dose: {steps}")
        out("")

    order = summary["order"]
    if order["n"]:
        out(
            f"Order violations   {order['k']} of {order['n']} edited answers scored above "
            "the less-edited answer"
        )
    for row in summary["lift"]:
        out(
            f"Dressing: {row['dressing']:<11} {pct(row['plain_rate'])} → "
            f"{pct(row['dressed_rate'])} leak "
            f"({row['turned']} of {row['pairs']} caught answers turned into passes)"
        )
    if order["n"] or summary["lift"]:
        out("")

    leaks = summary["leaks"]
    if leaks:
        by_id = {o["control"]["id"]: o for o in result["outcomes"]}
        out(f"Leaked controls ({len(leaks)}), first {min(limit, len(leaks))}:")
        for control_id in leaks[:limit]:
            control = by_id[control_id]["control"]
            answer = " ".join(control["answer"].split())
            out(f"  {control_id}")
            out(f"    {answer[:110]}{'…' if len(answer) > 110 else ''}")
    elif not summary["void"]:
        out("No must-fail control passed.")
    return "\n".join(lines).rstrip() + "\n"
