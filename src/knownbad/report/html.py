"""The single-file HTML report.

One file, no network, no build step: it can be opened from disk, attached to
a CI run or mailed. Its job is the one thing a terminal table cannot do well:
put each leaked answer next to what the grader said about it.
"""

from __future__ import annotations

from html import escape
from typing import Any

from .text import DOSE_UNITS, LEVEL_NAMES, dose_label, pct, span, threshold_sentence

MAX_EXAMPLES = 400
SERIES = {
    "splice": ("var(--s1)", "Sentences replaced"),
    "numbers": ("var(--s2)", "Numbers changed"),
}

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--line:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--s1:#2a78d6;
--s2:#eb6834;--good-ink:#006300;--bad:#d03b3b;--warn:#8a5a00;--bad-wash:rgba(208,59,59,.08);
--track:#eeede8}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;--line:#2c2c2a;--axis:#383835;
--ring:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--good-ink:#0ca30c;--bad:#e66767;
--warn:#fab219;--bad-wash:rgba(230,103,103,.10);--track:#262624}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin:44px 0 14px;font-weight:600}
.meta{color:var(--ink-2);font-size:13.5px;margin:0}
.mono,code,pre{font:13px/1.5 ui-monospace,"SF Mono",Menlo,monospace}
.banner{margin-top:20px;border-radius:10px;padding:14px 18px;border:1px solid var(--ring);
background:var(--surface);font-weight:600}
.banner small{display:block;font-weight:400;color:var(--ink-2);font-size:13.5px;margin-top:2px}
.banner.bad{box-shadow:inset 4px 0 0 var(--bad)}
.banner.good{box-shadow:inset 4px 0 0 var(--good-ink)}
.banner.void{box-shadow:inset 4px 0 0 var(--warn)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;
margin-top:12px}
.tile,.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;
padding:16px 18px}
.tile .lbl{font-size:13px;color:var(--muted);margin-bottom:6px}
.tile .big{font-size:32px;line-height:1.1;font-weight:650;letter-spacing:-.02em}
.tile p{margin:6px 0 0;font-size:13.5px;color:var(--ink-2)}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;font-weight:600;color:var(--muted);padding:8px 12px 8px 0;
border-bottom:1px solid var(--axis)}
td{padding:9px 12px 9px 0;border-bottom:1px solid var(--line);vertical-align:middle;
font-size:14px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.lvl{color:var(--muted);font-size:12.5px;white-space:nowrap}
.bar{position:relative;height:8px;border-radius:4px;background:var(--track);min-width:120px}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--bad)}
.bar u{position:absolute;top:-3px;bottom:-3px;border-left:1px solid var(--ink-2);
border-right:1px solid var(--ink-2);border-radius:1px}
.bar u::after{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--ink-2)}
.legend{display:flex;gap:18px;font-size:13px;color:var(--ink-2);margin:6px 0 4px;flex-wrap:wrap}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:6px}
svg text{font:12px system-ui,sans-serif;fill:var(--muted)}
svg .lab{fill:var(--ink-2);font-weight:600}
.card h3{margin:0;font-size:15px}.card p{margin:2px 0 8px;color:var(--ink-2);font-size:13.5px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.filters button{font:inherit;font-size:13px;padding:4px 10px;border-radius:999px;cursor:pointer;
border:1px solid var(--ring);background:var(--surface);color:var(--ink-2)}
.filters button[aria-pressed=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
details{background:var(--surface);border:1px solid var(--ring);border-radius:10px;
margin-bottom:8px}
summary{cursor:pointer;padding:11px 16px;display:flex;gap:12px;align-items:baseline;
list-style:none}
summary::-webkit-details-marker{display:none}
summary b{white-space:nowrap}summary .id{color:var(--muted);font-size:12.5px;white-space:nowrap}
summary .peek{color:var(--ink-2);font-size:13.5px;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap;flex:1;min-width:0}
summary .tag{color:var(--bad);font-size:12.5px;font-weight:600;white-space:nowrap}
.body{padding:4px 16px 16px;display:grid;grid-template-columns:130px 1fr;gap:10px 16px;
border-top:1px solid var(--line)}
.body dt{color:var(--muted);font-size:13px;padding-top:10px}
.body dd{margin:0;padding-top:10px;white-space:pre-wrap;overflow-wrap:anywhere}
.body dd.shown{background:var(--bad-wash);border-radius:6px;padding:10px 12px;margin-top:6px}
.note{color:var(--muted);font-size:13px;margin-top:10px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);font-size:12.5px;
padding:6px 9px;border-radius:6px;opacity:0;transition:opacity .1s;white-space:nowrap;z-index:5}
@media (max-width:700px){.body{grid-template-columns:1fr}.body dt{padding-top:10px}
.body dd{padding-top:0}summary{flex-wrap:wrap}}
"""

JS = """
const tip=document.getElementById('tip');
document.querySelectorAll('[data-t]').forEach(p=>{
p.addEventListener('mousemove',e=>{tip.textContent=p.dataset.t;tip.style.opacity=1;
tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px';
tip.style.top=(e.clientY-34)+'px'});
p.addEventListener('mouseleave',()=>tip.style.opacity=0)});
document.querySelectorAll('.filters button').forEach(b=>b.addEventListener('click',()=>{
document.querySelectorAll('.filters button').forEach(o=>o.setAttribute('aria-pressed',o===b));
const f=b.dataset.f;document.querySelectorAll('#leaks details').forEach(d=>{
d.hidden=f!=='all'&&d.dataset.f!==f})}));
"""


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _banner(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    if summary["void"]:
        return f'<div class="banner void">Void run<small>{_e(summary["void"])}</small></div>'
    if overall["k"]:
        return (
            f'<div class="banner bad">{overall["k"]} of {overall["n"]} wrong answers passed '
            f"({pct(overall['rate'])})<small>Every one of them is wrong by construction. "
            "Real near-misses are harder to catch than controls, so read this as a lower "
            "bound.</small></div>"
        )
    return (
        f'<div class="banner good">No wrong answer passed ({overall["n"]} controls)'
        f"<small>With 95% confidence the leak rate on controls like these is under "
        f"{pct(overall['high'])}. It does not prove the grader catches subtler errors."
        "</small></div>"
    )


def _tiles(summary: dict[str, Any]) -> str:
    tiles = []
    overall, refs = summary["overall"], summary["references"]
    tiles.append(
        (
            "Wrong answers that passed",
            pct(overall["rate"]),
            f"{overall['k']} of {overall['n']} must-fail controls. 95% interval {span(overall)}.",
        )
    )
    if refs["n"]:
        tiles.append(
            (
                "Reference answers passed",
                pct(refs["rate"]),
                f"{refs['k']} of {refs['n']}. A grader that fails these is broken the other way.",
            )
        )
    for family, curve in summary["dose"].items():
        threshold = curve["threshold"]
        if threshold is None:
            big = "never"
        else:
            big = (
                f"≤{pct(threshold[1])}"
                if threshold[0] == 0
                else (f"{pct(threshold[0])}–{pct(threshold[1])}")
            )
        tiles.append(
            (
                f"Detection threshold, {DOSE_UNITS[family].split()[0]}",
                big,
                threshold_sentence(family, curve).capitalize() + ".",
            )
        )
    order = summary["order"]
    if order["n"]:
        tiles.append(
            (
                "Order violations",
                str(order["k"]),
                f"Of {order['n']} edited answers, this many scored above the less-edited one.",
            )
        )
    return (
        '<div class="tiles">'
        + "".join(
            f'<div class="tile"><div class="lbl">{_e(label)}</div><div class="big">{_e(big)}</div>'
            f"<p>{_e(text)}</p></div>"
            for label, big, text in tiles
        )
        + "</div>"
    )


def _leak_table(summary: dict[str, Any]) -> str:
    rows = []
    for row in summary["families"]:
        width = 0 if row["rate"] is None else row["rate"] * 100
        low, high = (row["low"] or 0) * 100, (row["high"] or 0) * 100
        tip = f"{row['family']}: {row['k']} of {row['n']} passed, 95% interval {span(row)}"
        rows.append(
            f'<tr data-t="{_e(tip)}"><td class="lvl">{_e(row["level"])} · '
            f"{_e(LEVEL_NAMES.get(row['level'], ''))}</td><td>{_e(row['family'])}</td>"
            f'<td class="num">{row["k"]} / {row["n"]}</td><td class="num">{pct(row["rate"])}</td>'
            f'<td><div class="bar"><i style="width:{width:.1f}%"></i>'
            f'<u style="left:{low:.1f}%;width:{max(high - low, 0.5):.1f}%"></u></div></td>'
            f'<td class="num">{span(row)}</td></tr>'
        )
    return (
        "<table><thead><tr><th>Level</th><th>Control</th><th class=num>Leaked</th>"
        "<th class=num>Rate</th><th>Rate with 95% interval</th><th class=num>Interval</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _dose_chart(summary: dict[str, Any]) -> str:
    curves = summary["dose"]
    if not curves:
        return ""
    left, right, top, bottom = 56, 640, 30, 210
    x = lambda dose: left + (right - left) * dose  # noqa: E731
    y = lambda rate: bottom - (bottom - top) * rate  # noqa: E731
    parts = [
        '<svg viewBox="0 0 760 250" width="100%" role="img" aria-label="Pass rate by dose">',
        '<g stroke="var(--line)">',
        *(f'<line x1="{left}" x2="{right}" y1="{y(t)}" y2="{y(t)}"/>' for t in (0.25, 0.75, 1)),
        "</g>",
        f'<line x1="{left}" x2="{right}" y1="{y(0.5)}" y2="{y(0.5)}" stroke="var(--axis)" '
        'stroke-dasharray="3 4"/>',
        f'<line x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}" stroke="var(--axis)"/>',
        '<g text-anchor="end">',
        *(f'<text x="{left - 10}" y="{y(t) + 4}">{pct(t)}</text>' for t in (0, 0.25, 0.5, 0.75, 1)),
        "</g>",
        '<g text-anchor="middle">',
        f'<text x="{left}" y="{bottom + 20}">untouched</text>',
        *(f'<text x="{x(d)}" y="{bottom + 20}">≤{pct(d)}</text>' for d in (0.25, 0.5, 0.75)),
        f'<text x="{right}" y="{bottom + 20}">all</text>',
        f'<text x="{(left + right) / 2}" y="{bottom + 37}">share of the reference corrupted</text>',
        "</g>",
        f'<text x="{left + 6}" y="{y(0.5) - 6}">threshold: fails at least half</text>',
    ]
    legend = []
    ends: list[tuple[float, str]] = []
    for family, curve in curves.items():
        colour, name = SERIES.get(family, ("var(--s1)", family))
        points = [(x(p["dose_high"]), y(p["rate"]), p) for p in curve["points"]]
        legend.append(f'<span><i style="background:{colour}"></i>{_e(name)}</span>')
        line = " ".join(f"{px:.1f},{py:.1f}" for px, py, _ in points)
        parts.append(
            f'<polyline fill="none" stroke="{colour}" stroke-width="2" '
            f'stroke-linejoin="round" points="{line}"/>'
        )
        parts.append(f'<g fill="{colour}" stroke="var(--surface)" stroke-width="2">')
        for px, py, point in points:
            tip = f"{name} · {dose_label(point)} · {point['k']} of {point['n']} pass"
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" data-t="{_e(tip)}"/>')
        parts.append("</g>")
        ends.append((points[-1][1], name.split()[0]))
    # Direct labels at the line ends, nudged apart when two lines end together.
    ends.sort()
    placed = -100.0
    for end_y, name in ends:
        placed = max(end_y + 4, placed + 15)
        parts.append(f'<text class="lab" x="{right + 12}" y="{placed:.1f}">{_e(name)}</text>')
    parts.append("</svg>")
    return (
        '<div class="card"><h3>Pass rate by dose of corruption</h3>'
        "<p>How much of a right answer has to be wrong before the grader notices. A grader "
        "that reads closely drops to zero at the first step.</p>"
        f'<div class="legend">{"".join(legend)}</div>{"".join(parts)}</div>'
    )


def _lift_table(summary: dict[str, Any]) -> str:
    if not summary["lift"]:
        return ""
    rows = "".join(
        f"<tr><td>{_e(r['dressing'])}</td><td class=num>{pct(r['plain_rate'])}</td>"
        f"<td class=num>{pct(r['dressed_rate'])}</td>"
        f"<td class=num>{r['turned']} of {r['pairs']}</td></tr>"
        for r in summary["lift"]
    )
    return (
        "<h2>Dressing: the same wrong answer, with one line added</h2>"
        "<table><thead><tr><th>Dressing</th><th class=num>Plain leak rate</th>"
        "<th class=num>Dressed leak rate</th><th class=num>Caught answers turned into passes"
        "</th></tr></thead><tbody>" + rows + "</tbody></table>"
    )


def _example(outcome: dict[str, Any], items: dict[str, Any], tag: str) -> str:
    control = outcome["control"]
    item = items.get(control["item_id"], {})
    verdict = next((v for v in outcome["verdicts"] if v.get("passed")), outcome["verdicts"][0])
    said = verdict.get("explanation") or "(the grader gave no explanation)"
    if verdict.get("score") is not None:
        said = f"score {verdict['score']:g} · {said}"
    peek = " ".join(control["answer"].split()) or "(empty answer)"
    fields = [
        ("Question", item.get("input")),
        ("Reference", item.get("reference")),
        ("Answer shown", control["answer"] or "(empty answer)"),
        ("How it was built", control["how"]),
        ("Grader said", said),
    ]
    body = "".join(
        f"<dt>{_e(name)}</dt><dd{' class=shown' if name == 'Answer shown' else ''}>{_e(value)}</dd>"
        for name, value in fields
        if value is not None
    )
    return (
        f'<details data-f="{_e(control["family"])}"><summary><b>{_e(control["family"])}</b>'
        f'<span class="id">{_e(control["item_id"])}</span>'
        f'<span class="peek">{_e(peek[:160])}</span>'
        f'<span class="tag">{_e(tag)}</span></summary><dl class="body">{body}</dl></details>'
    )


def _examples(result: dict[str, Any]) -> str:
    summary, items = result["summary"], result.get("items", {})
    by_id = {o["control"]["id"]: o for o in result["outcomes"]}
    out = []
    leaks = [by_id[i] for i in summary["leaks"] if i in by_id]
    if leaks:
        families = sorted({o["control"]["family"] for o in leaks})
        buttons = '<button data-f="all" aria-pressed="true">All</button>' + "".join(
            f'<button data-f="{_e(f)}" aria-pressed="false">{_e(f)}</button>' for f in families
        )
        shown = leaks[:MAX_EXAMPLES]
        out.append(f"<h2>Leaked controls · {len(leaks)}</h2>")
        out.append(f'<div class="filters">{buttons}</div><div id="leaks">')
        out.extend(_example(o, items, "passed") for o in shown)
        out.append("</div>")
        if len(leaks) > len(shown):
            out.append(
                f'<p class="note">Showing the first {len(shown)}. '
                "The result file has all of them.</p>"
            )
    violations = [by_id[i] for i in summary["order"].get("violations", []) if i in by_id]
    if violations:
        out.append(f"<h2>Order violations · {len(violations)}</h2>")
        out.extend(_example(o, items, "scored above its base") for o in violations[:MAX_EXAMPLES])
    rejects = [by_id[i] for i in summary["false_rejects"] if i in by_id]
    if rejects:
        out.append(f"<h2>Right answers that failed · {len(rejects)}</h2>")
        out.extend(_example(o, items, "failed") for o in rejects[:MAX_EXAMPLES])
    return "".join(out)


def render(result: dict[str, Any]) -> str:
    summary = result["summary"]
    trials = result.get("trials", 1)
    meta = (
        f"{summary['controls']} controls × {trials} trial{'s' if trials != 1 else ''} · "
        f"grader <code>{_e(result.get('grader'))}</code> · {_e(result.get('created', ''))}"
    )
    errors = ""
    if summary["errors"]:
        listed = "".join(
            f"<br><code>{_e(x['id'])}</code>: {_e(x['error'])}" for x in summary["error_examples"]
        )
        errors = (
            f'<p class="note">{summary["errors"]} controls got no verdict from the grader and '
            f"are not counted as caught.{listed}</p>"
        )
    leak_section = ""
    if summary["families"]:
        leak_section = "<h2>Wrong answers that passed, by control</h2>" + _leak_table(summary)
    dose = _dose_chart(summary)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>knownbad report</title><style>{CSS}</style></head><body><main>"
        f'<h1>knownbad report</h1><p class="meta">{meta}</p>'
        f"{_banner(summary)}{errors}{_tiles(summary)}{leak_section}"
        f"{'<h2>Detection threshold</h2>' + dose if dose else ''}"
        f"{_lift_table(summary)}{_examples(result)}"
        f'</main><div id="tip"></div><script>{JS}</script></body></html>\n'
    )
