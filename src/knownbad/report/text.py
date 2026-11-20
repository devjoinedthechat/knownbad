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
DOSE_UNITS = {
    "splice": "sentences replaced",
    "numbers": "numbers changed",
    "json-value": "values changed",
    "json-drop": "fields removed",
}


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

    same = summary.get("consistency") or {}
    if same.get("n"):
        out(
            f"Same verdict every trial   {same['k']} / {same['n']}   {pct(same['rate'])}"
            "   (a split verdict means the grader is guessing on that answer)"
        )
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
            out(f"  {family:<10} {threshold_sentence(family, curve)}")
            steps = " · ".join(f"{dose_label(p)} {pct(p['rate'])}" for p in curve["points"])
            out(f"             pass rate by dose: {steps}")
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


MOVE_TITLES = {
    "broken": "Wrong answers that were caught and now pass",
    "newly_rejected": "Reference answers that passed and now fail",
    "fixed": "Wrong answers that passed and are now caught",
    "newly_accepted": "Reference answers that failed and now pass",
    "now_passes": "Edited answers that failed and now pass",
    "now_fails": "Edited answers that passed and now fail",
}


def render_diff(diff: dict[str, Any], limit: int = 10) -> str:
    lines: list[str] = []
    out = lines.append
    out(f"old  {diff['old']['grader']}  {diff['old']['created'] or ''}".rstrip())
    out(f"new  {diff['new']['grader']}  {diff['new']['created'] or ''}".rstrip())
    out(f"{diff['shared']} controls in both runs")
    if diff["only_old"] or diff["only_new"]:
        out(f"not compared: {diff['only_old']} only in old, {diff['only_new']} only in new")
    if diff["unreadable"]:
        out(f"not compared: {len(diff['unreadable'])} with no verdict in one of the runs")
    out("")
    leaks, refs = diff["leaks"], diff["references"]
    if leaks["old"]["n"]:
        out(
            f"Wrong answers that passed   {pct(leaks['old']['rate'])} → {pct(leaks['new']['rate'])}"
            f"   ({leaks['old']['k']} → {leaks['new']['k']} of {leaks['old']['n']})"
        )
    if refs["old"]["n"]:
        out(
            f"Reference answers passed    {pct(refs['old']['rate'])} → {pct(refs['new']['rate'])}"
            f"   ({refs['old']['k']} → {refs['new']['k']} of {refs['old']['n']})"
        )
    fixed, broken = len(diff["moves"]["fixed"]), len(diff["moves"]["broken"])
    if diff["p_value"] is None:
        out("No must-fail control changed its verdict.")
    else:
        sure = "unlikely to be chance" if diff["p_value"] < 0.05 else "could be chance"
        out(
            f"{fixed} fixed, {broken} broken: the grader is {diff['direction']} on these "
            f"controls (p = {diff['p_value']:.3f}, {sure})"
        )
    for name, title in MOVE_TITLES.items():
        ids = diff["moves"][name]
        if not ids:
            continue
        out("")
        out(f"{title} ({len(ids)})")
        for control_id in ids[:limit]:
            out(f"  {control_id}")
        if len(ids) > limit:
            out(f"  … and {len(ids) - limit} more")
    return "\n".join(lines).rstrip() + "\n"
