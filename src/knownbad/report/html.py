"""The single-file HTML report.

One file, no network, no build step: it opens from disk, attaches to a CI
run and can be mailed.

The page is built around a plate map, the way an assay is read. Rows are
eval items, columns are controls, each well is one answer the grader was
shown. A well that lights up is a wrong answer that passed. A lit column is
a kind of answer the grader cannot see; a lit row is an item it grades badly.
Selecting a well shows that answer beside what the grader said about it.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from .text import LEVEL_NAMES, dose_label, pct, span, threshold_sentence

MAX_ISSUE_ROWS = 150  # rows with something to look at
FILL_ROWS = 40  # a short plate is padded with clean rows up to this many
MAX_SLOTS = 4
MAX_ANSWER = 6000

# (group label, [(family, column label)]) in reading order.
FIXED_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("good", (("reference", "reference"),)),
    ("0 no answer", (("empty", "empty"), ("echo", "echo"), ("refusal", "refusal"))),
    (
        "1 attack",
        (
            ("injection-plain", "injection"),
            ("injection-forged", "forged note"),
            ("claim", "bare claim"),
            ("rubric-echo", "rubric echo"),
        ),
    ),
    (
        "2 wrong question",
        (
            ("transplant", "transplant"),
            ("transplant+authority", "+ authority"),
            ("transplant+confidence", "+ confidence"),
            ("transplant+padding", "+ padding"),
        ),
    ),
    ("3 edits", (("contradict", "contradiction"), ("json-truncated", "truncated"))),
)
SLOT_GROUPS = (
    ("drop", "3 removed →", "sentences removed"),
    ("splice", "3 swapped →", "sentences swapped"),
    ("numbers", "3 numbers →", "numbers changed"),
    ("flip", "3 reversed →", "words reversed"),
    ("json-value", "3 values →", "values changed"),
    ("json-drop", "3 fields →", "fields removed"),
    ("harvested", "4 yours", "your known-bad"),
    ("harvested-good", "4 yours, good", "your known-good"),
)
DOSE_NAMES = {
    "drop": ("Removed", "Sentences removed"),
    "flip": ("Reversed", "Words reversed"),
    "splice": ("Swapped", "Sentences swapped"),
    "numbers": ("Numbers", "Numbers changed"),
    "json-value": ("Values", "Values changed"),
    "json-drop": ("Fields", "Fields removed"),
}
# Lines are told apart by dash and marker, never by colour.
DOSE_STYLES = (
    ("", "var(--ink)"),
    ('stroke-dasharray="5 4"', "var(--page)"),
    ('stroke-dasharray="1 4" stroke-linecap="round"', "var(--ink)"),
    ('stroke-dasharray="9 3 2 3"', "var(--page)"),
    ('stroke-dasharray="2 2"', "var(--ink)"),
    ('stroke-dasharray="12 4"', "var(--page)"),
)
STATE_WORDS = {
    "ok": "as expected",
    "leak": "leak: must fail, passed",
    "still": "still passes at this dose",
    "viol": "order violation: scored above the less-edited answer",
    "reject": "right answer failed",
    "err": "no verdict",
}

CSS = """
/* layout: one left-aligned column; the plate and its inspector sit side by side */
:root{color-scheme:light;--page:#f7f8f9;--ink:#12161c;--ink-2:#4a525c;--muted:#7d8791;
--hair:#dde1e6;--well:#bcc4cd;--signal:#c4175c;--wash:rgba(196,23,92,.10);
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--page:#0e1115;--ink:#eceef1;--ink-2:#b3bac3;--muted:#7c8590;--hair:#242a31;--well:#3d4650;
--signal:#ff5f9e;--wash:rgba(255,95,158,.14)}}
:root[data-theme=dark]{color-scheme:dark;--page:#0e1115;--ink:#eceef1;--ink-2:#b3bac3;
--muted:#7c8590;--hair:#242a31;--well:#3d4650;--signal:#ff5f9e;--wash:rgba(255,95,158,.14)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 var(--sans);
-webkit-font-smoothing:antialiased}
main{max-width:1240px;margin:0 auto;padding:36px max(20px,env(safe-area-inset-right,0px)) 96px
max(20px,env(safe-area-inset-left,0px))}
.mono,code{font-family:var(--mono);font-size:.92em}
.top{display:flex;gap:6px 18px;flex-wrap:wrap;color:var(--muted);font-size:13px}
.top b{color:var(--ink);font-weight:650;letter-spacing:-.01em}
h1{font-size:clamp(28px,4.2vw,44px);line-height:1.08;letter-spacing:-.025em;font-weight:650;
margin:28px 0 10px;text-wrap:balance;max-width:20ch}
h1 em{font-style:normal;color:var(--signal)}
.sub{color:var(--ink-2);font-size:16px;max-width:62ch;margin:0}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
font-weight:600;margin:64px 0 6px}
.lede{color:var(--ink-2);margin:0 0 20px;max-width:70ch}
.readings{display:flex;flex-wrap:wrap;margin:36px 0 0;border-top:1px solid var(--hair)}
.readings div{padding:14px 28px 2px 0;margin-right:28px;border-right:1px solid var(--hair);
min-width:0}
.readings div:last-child{border-right:0;margin-right:0}
.readings dt{font-size:12px;color:var(--muted);margin-bottom:2px}
.readings dd{margin:0;font:600 22px/1.2 var(--mono);letter-spacing:-.02em}
.readings small{display:block;font:400 12.5px/1.4 var(--sans);color:var(--ink-2);
letter-spacing:0;margin-top:3px}
.note{color:var(--muted);font-size:13px;margin:10px 0 0}

/* plate */
.bench{display:grid;grid-template-columns:minmax(0,auto) minmax(300px,1fr);gap:0 40px;
align-items:start}
.scroll{overflow-x:auto;padding-bottom:6px}
.legend{display:flex;flex-wrap:wrap;gap:6px 20px;font-size:12.5px;color:var(--ink-2);
margin:0 0 16px;padding:0;list-style:none}
.legend li{display:flex;align-items:center;gap:7px}
.g{display:inline-block;flex:none;width:18px;height:18px;position:relative}
.g::before,.plate button::before{content:"";position:absolute;inset:0;margin:auto}
[data-s=ok]::before{width:5px;height:5px;border-radius:50%;background:var(--well)}
[data-s=leak]::before{width:15px;height:15px;border-radius:50%;background:var(--signal)}
[data-s=still]::before{width:11px;height:11px;border-radius:50%;border:2px solid var(--ink-2)}
[data-s=viol]::before{width:11px;height:11px;background:var(--signal);transform:rotate(45deg)}
[data-s=reject]::before{width:12px;height:12px;border:2px solid var(--signal)}
[data-s=err]::before{width:11px;height:2px;background:var(--muted);transform:rotate(45deg);
box-shadow:0 0 0 0 transparent}
[data-s=err]::after{content:"";position:absolute;inset:0;margin:auto;width:11px;height:2px;
background:var(--muted);transform:rotate(-45deg)}
table.plate{border-collapse:collapse;font-size:12px}
.plate th{font-weight:400;color:var(--muted);padding:0}
.plate thead .grp th{text-align:left;font-size:11px;white-space:nowrap;padding:0 0 6px 4px;
color:var(--ink-2)}
.plate thead .col th{height:92px;vertical-align:bottom;padding-bottom:6px}
.plate thead .col span{writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap}
.plate thead .col .num{text-align:center;font-family:var(--mono);font-size:11px}
.plate thead .col .num span{writing-mode:horizontal-tb;transform:none}
.plate td{padding:0;width:24px;height:24px}
.plate .sp{width:14px}
.plate tbody th{text-align:left;font:12px var(--mono);color:var(--ink-2);white-space:nowrap;
padding-right:14px;max-width:190px;overflow:hidden;text-overflow:ellipsis}
.plate tbody tr:hover th{color:var(--ink)}
.plate button{all:unset;display:block;width:24px;height:24px;position:relative;cursor:pointer;
border-radius:5px}
.plate button:hover{background:var(--hair)}
.plate button:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}
.plate button[aria-current]{background:var(--hair);box-shadow:inset 0 0 0 1.5px var(--ink)}
.plate tfoot td{text-align:center;font:11px var(--mono);color:var(--muted);padding-top:6px;
border-top:1px solid var(--hair)}
.plate tfoot td.hot{color:var(--signal);font-weight:600}
.plate tfoot th{text-align:left;font-size:11px;padding-top:6px;border-top:1px solid var(--hair)}

/* inspector */
.insp{position:sticky;top:20px;border-left:1px solid var(--hair);padding:0 0 0 28px;
min-width:0;min-height:320px}
.insp .lvl{font-size:12px;color:var(--muted)}
.insp h3{font-size:22px;letter-spacing:-.015em;margin:2px 0 2px;font-weight:650}
.insp .item{font:12.5px var(--mono);color:var(--ink-2);overflow-wrap:anywhere}
.insp .state{display:flex;align-items:center;gap:8px;margin:14px 0 4px;font-weight:600}
.insp .state.bad{color:var(--signal)}
.insp dl{margin:0}
.insp dt{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin-top:18px;font-weight:600}
.insp dd{margin:4px 0 0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink-2)}
.insp dd.answer{color:var(--ink);font-size:15.5px}
.insp dd.said{color:var(--ink)}
.insp mark{background:var(--wash);color:inherit;border-radius:3px;padding:1px 2px;
box-shadow:inset 0 -1.5px 0 var(--signal)}
.insp .empty{color:var(--muted);font-style:italic}
.step{display:flex;align-items:center;gap:10px;margin-top:26px;padding-top:14px;
border-top:1px solid var(--hair);font-size:13px;color:var(--muted)}
.step button{font:inherit;color:var(--ink);background:none;border:1px solid var(--hair);
border-radius:6px;padding:5px 10px;cursor:pointer}
.step button:hover{border-color:var(--ink-2)}
.step button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.step button:disabled{color:var(--muted);cursor:default;border-color:var(--hair)}
.step kbd{font:11px var(--mono);border:1px solid var(--hair);border-radius:4px;padding:0 4px;
color:var(--muted);margin-left:6px}
.step .count{margin-left:auto;font-family:var(--mono);font-size:12px}

/* figures */
.two{display:grid;grid-template-columns:minmax(0,620px) minmax(220px,1fr);gap:8px 48px;
align-items:start}
.two ul{margin:26px 0 0;padding:0;list-style:none}
.two li{padding:12px 0;border-top:1px solid var(--hair)}
.two li b{display:block;font-size:13px;color:var(--muted);font-weight:400}
.key{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:12.5px;color:var(--ink-2);margin:0 0 6px}
.key span{white-space:nowrap}
.key svg{vertical-align:middle;margin-right:6px}
svg text{font:12px var(--sans);fill:var(--muted)}
svg .lab{fill:var(--ink);font-weight:600}
table.t{border-collapse:collapse;width:100%;max-width:880px}
.t th{text-align:left;font-size:12px;font-weight:400;color:var(--muted);padding:6px 16px 6px 0;
border-bottom:1px solid var(--hair)}
.t td{padding:8px 16px 8px 0;border-bottom:1px solid var(--hair);font-size:14px}
.t .n{text-align:right;font-family:var(--mono);font-size:13px;white-space:nowrap}
.t th.n{font-family:var(--sans);font-size:12px}
.fig{overflow-x:auto}.fig svg{min-width:460px;display:block}
.t td.l{color:var(--muted);font-size:12.5px;white-space:nowrap}
.t tr.zero td{color:var(--muted)}
.bar{position:relative;height:16px;min-width:140px}
.bar::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--hair)}
.bar i{position:absolute;left:0;top:5px;height:6px;background:var(--signal);border-radius:0 3px 3px 0}
.bar u{position:absolute;top:2px;height:12px;border-left:1.5px solid var(--ink-2);
border-right:1.5px solid var(--ink-2)}
.bar u::after{content:"";position:absolute;left:0;right:0;top:50%;border-top:1.5px solid var(--ink-2);
margin-top:-.75px}
.dumb{position:relative;height:16px;min-width:160px}
.dumb::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--hair)}
.dumb s{position:absolute;top:7px;height:2px;background:var(--ink-2)}
.dumb b,.dumb i{position:absolute;top:3px;width:10px;height:10px;border-radius:50%;margin-left:-5px}
.dumb b{border:2px solid var(--ink-2);background:var(--page)}
.dumb i{background:var(--signal)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);font-size:12.5px;
padding:5px 9px;border-radius:6px;opacity:0;white-space:nowrap;z-index:5;max-width:90vw;
overflow:hidden;text-overflow:ellipsis}
@media (max-width:980px){.bench{grid-template-columns:minmax(0,1fr)}
.insp{position:static;border-left:0;border-top:1px solid var(--hair);padding:24px 0 0;margin-top:24px}
.two{grid-template-columns:minmax(0,1fr)}.readings div{border-right:0;margin-right:0;
flex:1 1 150px}}
@media (prefers-reduced-motion:no-preference){.plate button,.step button{transition:background .08s,
border-color .08s}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s),cells=[...document.querySelectorAll('.plate button')];
const alarms=cells.filter(b=>/leak|viol|reject/.test(b.dataset.s));
const tip=$('#tip');let cur=null;
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;
if(text!=null)n.textContent=text;return n};
function parts(s,bySentence){return bySentence?s.split(/(?<=[.!?])(\s+)/):s.split(/(\s+)/)}
function diff(base,text,bySentence){const a=parts(base,bySentence),b=parts(text,bySentence),
m=a.length,n=b.length;if(m*n>400000)return [[text,false]];
const L=Array.from({length:m+1},()=>new Uint16Array(n+1));
for(let i=m-1;i>=0;i--)for(let j=n-1;j>=0;j--)
L[i][j]=a[i]===b[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
const out=[];let i=0,j=0;while(j<n){if(i<m&&a[i]===b[j]){out.push([b[j],false]);i++;j++}
else if(i<m&&L[i+1][j]>=L[i][j+1])i++;else{out.push([b[j],/\S/.test(b[j])]);j++}}
for(let k=1;k<out.length-1;k++)if(!/\S/.test(out[k][0])&&out[k-1][1]&&out[k+1][1])out[k][1]=true;
return out}
function answerNode(c){const dd=el('dd','answer');
if(!c.a){dd.append(el('span','empty','(empty answer)'));return dd}
const item=D.items[c.i]||{};let base=null;
if(c.b&&D.c[c.b]&&c.f.startsWith('transplant+'))base=D.c[c.b].a;
else if(D.edited.includes(c.f)&&item.r)base=item.r;
if(base==null){dd.textContent=c.a;return dd}
let run='',on=false;const flush=()=>{if(!run)return;dd.append(on?el('mark',null,run):run);run=''};
for(const [t,ch] of diff(base,c.a,c.f==='splice'||c.f==='contradict')){if(ch!==on){flush();on=ch}run+=t}flush();return dd}
function show(b,focus){if(cur){cur.removeAttribute('aria-current');cur.tabIndex=-1}
cur=b;b.setAttribute('aria-current','true');b.tabIndex=0;if(focus)b.focus({preventScroll:false});
const c=D.c[b.dataset.id],item=D.items[c.i]||{},box=$('#insp'),bad=/leak|viol|reject/.test(c.s);
const state=el('div','state'+(bad?' bad':''));const g=el('span','g');g.dataset.s=c.s;
state.append(g,D.words[c.s]);const dl=el('dl');
const add=(k,node)=>{dl.append(el('dt',null,k),node)};
add('Answer shown to the grader',answerNode(c));
let said=c.x||(c.s==='err'?c.e||'The grader returned no verdict.':'The grader gave no explanation.');
const facts=[];if(c.sc!=null)facts.push('score '+c.sc);
if(c.t>1)facts.push('passed '+c.p+' of '+c.t+' trials');
add('The grader said',el('dd','said',(facts.length?facts.join(' · ')+'\n':'')+said));
add(c.s==='ok'&&c.f==='reference'?'What it is':'How it was built',el('dd',null,c.h));
if(item.q)add('Question',el('dd',null,item.q));
if(item.r&&c.f!=='reference')add('Reference answer',el('dd',null,item.r));
const at=alarms.indexOf(b),step=el('div','step');
const prev=el('button',null,'Previous'),next=el('button',null,'Next');
prev.append(el('kbd',null,'K'));next.append(el('kbd',null,'J'));
prev.disabled=next.disabled=!alarms.length;prev.onclick=()=>hop(-1);next.onclick=()=>hop(1);
step.append(prev,next,el('span','count',alarms.length?(at>=0?(at+1)+' of '+alarms.length:
alarms.length+' to review'):'nothing to review'));
box.replaceChildren(el('div','lvl',c.l),el('h3',null,c.n),el('div','item',c.i),state,dl,step)}
function hop(d){if(!alarms.length)return;let at=alarms.indexOf(cur);
if(at<0){const all=cells.indexOf(cur);at=d>0?alarms.findIndex(a=>cells.indexOf(a)>all)-1:
alarms.findLastIndex(a=>cells.indexOf(a)<all)+1;if(d>0&&at<-1)at=-1}
show(alarms[(at+d+alarms.length)%alarms.length],true)}
cells.forEach(b=>{b.tabIndex=-1;b.addEventListener('click',()=>{tip.style.opacity=0;show(b,false)});
b.addEventListener('mousemove',e=>{tip.textContent=b.getAttribute('aria-label');tip.style.opacity=1;
tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8)+'px';
tip.style.top=(e.clientY+16)+'px'});b.addEventListener('mouseleave',()=>tip.style.opacity=0)});
document.querySelectorAll('[data-t]').forEach(p=>{p.addEventListener('mousemove',e=>{
tip.textContent=p.dataset.t;tip.style.opacity=1;
tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8)+'px';
tip.style.top=(e.clientY-34)+'px'});p.addEventListener('mouseleave',()=>tip.style.opacity=0)});
document.addEventListener('keydown',e=>{if(e.metaKey||e.ctrlKey||e.altKey)return;
const k=e.key.toLowerCase();if(k==='j'||k==='n'){hop(1);e.preventDefault();return}
if(k==='k'||k==='p'){hop(-1);e.preventDefault();return}
if(!cur||!e.key.startsWith('Arrow')||!document.activeElement.closest('.plate'))return;
const r=+cur.dataset.r,c=+cur.dataset.c,dr=k==='arrowdown'?1:k==='arrowup'?-1:0,
dc=k==='arrowright'?1:k==='arrowleft'?-1:0;let best=null,bd=1e9;
for(const b of cells){const br=+b.dataset.r,bc=+b.dataset.c;
if(dr&&bc===c&&(br-r)*dr>0&&Math.abs(br-r)<bd){best=b;bd=Math.abs(br-r)}
if(dc&&br===r&&(bc-c)*dc>0&&Math.abs(bc-c)<bd){best=b;bd=Math.abs(bc-c)}}
if(best){show(best,true);e.preventDefault()}});
if(cells.length)show(alarms[0]||cells.find(b=>b.dataset.s==='err')||cells[0],false);
"""


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _json(data: Any) -> str:
    """JSON that is safe inside a script element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for raw, safe in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        (" ", "\\u2028"),
        (" ", "\\u2029"),
    ):
        text = text.replace(raw, safe)
    return text


def _state(outcome: dict[str, Any], violations: set[str]) -> str:
    control = outcome["control"]
    graded = [v for v in outcome["verdicts"] if v.get("passed") is not None]
    if not graded:
        return "err"
    passed = sum(1 for v in graded if v["passed"]) / len(graded) >= 0.5
    expect = control["expect"]
    if expect == "pass":
        return "ok" if passed else "reject"
    if expect == "fail":
        return "leak" if passed else "ok"
    if control["id"] in violations:
        return "viol"
    return "still" if passed else "ok"


Cells = dict[tuple[str, int], dict[str, Any]]


def _layout(outcomes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Cells]]:
    """Plate columns for this run, and each item's outcomes keyed by column."""
    per_item: dict[str, Cells] = {}
    slots: dict[str, int] = {}
    for outcome in outcomes:
        control = outcome["control"]
        cells = per_item.setdefault(control["item_id"], {})
        slot = sum(1 for family, _ in cells if family == control["family"])
        cells[(control["family"], slot)] = outcome
        slots[control["family"]] = max(slots.get(control["family"], 0), slot + 1)
    groups: list[dict[str, Any]] = []
    for label, families in FIXED_GROUPS:
        columns = [((family, 0), name, name) for family, name in families if family in slots]
        if columns:
            groups.append({"label": "" if label == "good" else label, "columns": columns})
    for family, label, long_name in SLOT_GROUPS:
        count = min(slots.get(family, 0), MAX_SLOTS if family in DOSE_NAMES else 8)
        if count:
            columns = [
                ((family, s), str(s + 1), f"{long_name}, step {s + 1}") for s in range(count)
            ]
            groups.append({"label": label, "columns": columns})
    return groups, per_item


def _plate(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    summary = result["summary"]
    violations = set(summary["order"].get("violations", []))
    groups, per_item = _layout(result["outcomes"])
    states = {
        item_id: {key: _state(o, violations) for key, o in cells.items()}
        for item_id, cells in per_item.items()
    }
    issues = {
        i: sum(1 for s in st.values() if s in ("leak", "viol", "reject", "err"))
        for i, st in states.items()
    }
    order = sorted(per_item, key=lambda i: -issues[i])  # stable: file order within a count
    with_issues = [i for i in order if issues[i]][:MAX_ISSUE_ROWS]
    clean = [i for i in order if not issues[i]]
    shown = with_issues + clean[: max(0, FILL_ROWS - len(with_issues))]
    hidden_issue = sum(1 for i in order if issues[i]) - len(with_issues)
    hidden_clean = len(clean) - (len(shown) - len(with_issues))

    flat = [column for group in groups for column in group["columns"]]
    index = {key: n for n, (key, _, _) in enumerate(flat)}
    data: dict[str, Any] = {}
    head_groups = ["<th></th>"]
    head_cols = ["<th></th>"]
    for g, group in enumerate(groups):
        if g:
            head_groups.append('<th class="sp"></th>')
            head_cols.append('<th class="sp"></th>')
        head_groups.append(f'<th colspan="{len(group["columns"])}">{_e(group["label"])}</th>')
        head_cols.extend(
            f"<th{' class=num' if name.isdigit() else ''}><span>{_e(name)}</span></th>"
            for _, name, _ in group["columns"]
        )

    body = []
    for r, item_id in enumerate(shown):
        row = [f'<th scope="row" title="{_e(item_id)}">{_e(item_id)}</th>']
        for g, group in enumerate(groups):
            if g:
                row.append('<td class="sp"></td>')
            for key, _, long_name in group["columns"]:
                outcome = per_item[item_id].get(key)
                if outcome is None:
                    row.append("<td></td>")
                    continue
                control = outcome["control"]
                state = states[item_id][key]
                label = f"{item_id} · {long_name} · {STATE_WORDS[state]}"
                row.append(
                    f'<td><button type="button" data-id="{_e(control["id"])}" data-s="{state}" '
                    f'data-r="{r}" data-c="{index[key]}" aria-label="{_e(label)}"></button></td>'
                )
                data[control["id"]] = _control_data(outcome, state, long_name)
        body.append("<tr>" + "".join(row) + "</tr>")

    # Column footer: how many of the whole run's must-fail controls in it leaked.
    leaks_by_column: dict[tuple[str, int], int] = {}
    for cells in states.values():
        for key, state in cells.items():
            if state == "leak":
                leaks_by_column[key] = leaks_by_column.get(key, 0) + 1
    foot = ["<th>leaked</th>"]
    for g, group in enumerate(groups):
        if g:
            foot.append('<td class="sp"></td>')
        for key, _, _ in group["columns"]:
            count = leaks_by_column.get(key, 0)
            foot.append(f'<td class="hot">{count}</td>' if count else "<td>·</td>")

    notes = []
    if hidden_issue:
        notes.append(f"{hidden_issue} more items with something to review are in the result file.")
    if hidden_clean:
        notes.append(
            f"{hidden_clean} items where every control came out as expected are not drawn."
        )
    table = (
        '<div class="scroll"><table class="plate"><thead>'
        f'<tr class="grp">{"".join(head_groups)}</tr><tr class="col">{"".join(head_cols)}</tr>'
        f"</thead><tbody>{''.join(body)}</tbody><tfoot><tr>{''.join(foot)}</tr></tfoot>"
        "</table></div>"
    )
    if notes:
        table += f'<p class="note">{_e(" ".join(notes))}</p>'
    return table, data


def _control_data(outcome: dict[str, Any], state: str, long_name: str) -> dict[str, Any]:
    control = outcome["control"]
    verdicts = outcome["verdicts"]
    graded = [v for v in verdicts if v.get("passed") is not None]
    # Show the verdict that agrees with the state: the pass for a leak, and so on.
    passed_wanted = state in ("leak", "still", "viol") or (
        state == "ok" and control["expect"] == "pass"
    )
    pick = next((v for v in graded if v["passed"] == passed_wanted), None) or (
        graded[0] if graded else verdicts[0]
    )
    scores = [v["score"] for v in graded if v.get("score") is not None]
    level = control["level"]
    answer = control["answer"]
    if len(answer) > MAX_ANSWER:
        answer = (
            answer[:MAX_ANSWER] + f"\n… ({len(control['answer']) - MAX_ANSWER} more characters)"
        )
    return {
        "f": control["family"],
        "i": control["item_id"],
        "n": long_name,
        "l": "reference" if level == "good" else f"level {level} · {LEVEL_NAMES.get(level, '')}",
        "a": answer,
        "h": control["how"],
        "b": control.get("base"),
        "s": state,
        "x": pick.get("explanation"),
        "e": pick.get("error"),
        "sc": round(sum(scores) / len(scores), 3) if scores else None,
        "t": len(verdicts),
        "p": sum(1 for v in graded if v["passed"]),
    }


def _headline(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    if summary["void"]:
        return f'<h1>Void run.</h1><p class="sub">{_e(summary["void"])}</p>'
    if overall["k"]:
        return (
            f"<h1><em>{overall['k']} of {overall['n']}</em> wrong answers passed.</h1>"
            '<p class="sub">Each of them is wrong by construction. Real mistakes are harder '
            "to catch than these, so read the rate as a floor.</p>"
        )
    return (
        "<h1>No wrong answer passed.</h1>"
        f'<p class="sub">{overall["n"]} controls, all caught: the leak rate on answers like '
        f"these is under {pct(overall['high'])} at 95% confidence. That rules out a broken "
        "grader. It does not prove a sharp one.</p>"
    )


def _readings(summary: dict[str, Any]) -> str:
    overall, refs, order = summary["overall"], summary["references"], summary["order"]
    items = [("Leak rate", pct(overall["rate"]), f"95% interval {span(overall)}")]
    if refs["n"]:
        items.append(
            ("References passed", f"{refs['k']}/{refs['n']}", "right answers the grader accepted")
        )
    if order["n"]:
        items.append(("Order violations", str(order["k"]), f"of {order['n']} edited answers"))
    same = summary.get("consistency") or {}
    if same.get("n"):
        items.append(
            ("Same verdict every trial", pct(same["rate"]), f"{same['k']} of {same['n']} answers")
        )
    return (
        '<dl class="readings">'
        + "".join(
            f"<div><dt>{_e(label)}</dt><dd>{_e(value)}<small>{_e(small)}</small></dd></div>"
            for label, value, small in items
        )
        + "</dl>"
    )


def _legend() -> str:
    entries = (
        ("ok", "as expected"),
        ("leak", "leak: wrong answer passed"),
        ("still", "edited answer still passes"),
        ("viol", "scored above a less-edited answer"),
        ("reject", "right answer failed"),
        ("err", "no verdict"),
    )
    return (
        '<ul class="legend">'
        + "".join(
            f'<li><span class="g" data-s="{state}"></span>{_e(text)}</li>'
            for state, text in entries
        )
        + "</ul>"
    )


def _dose(summary: dict[str, Any]) -> str:
    curves = summary["dose"]
    if not curves:
        return ""
    left, right, top, bottom = 44, 520, 16, 196

    def x(dose: float) -> float:
        return left + (right - left) * dose

    def y(share: float) -> float:
        return bottom - (bottom - top) * share

    svg = [
        '<svg viewBox="0 0 620 236" width="100%" role="img" '
        'aria-label="Pass rate against the share of the reference that was corrupted">',
        *(
            f'<line x1="{left}" x2="{right}" y1="{y(t)}" y2="{y(t)}" stroke="var(--hair)"/>'
            for t in (0.25, 0.5, 0.75, 1)
        ),
        f'<line x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}" stroke="var(--muted)"/>',
        '<g text-anchor="end">',
        *(f'<text x="{left - 10}" y="{y(t) + 4}">{pct(t)}</text>' for t in (0, 0.5, 1)),
        "</g>",
        '<g text-anchor="middle">',
        f'<text x="{left}" y="{bottom + 20}">untouched</text>',
        *(f'<text x="{x(d)}" y="{bottom + 20}">≤{pct(d)}</text>' for d in (0.25, 0.5, 0.75)),
        f'<text x="{right}" y="{bottom + 20}">all</text>',
        f'<text x="{(left + right) / 2}" y="{bottom + 38}">share of the reference corrupted</text>',
        "</g>",
    ]
    key, ends = [], []
    for index, (family, curve) in enumerate(curves.items()):
        dash, fill = DOSE_STYLES[index % len(DOSE_STYLES)]
        name = DOSE_NAMES.get(family, (family, family))[1]
        points = [(x(p["dose_high"]), y(p["rate"]), p) for p in curve["points"]]
        line = " ".join(f"{px:.1f},{py:.1f}" for px, py, _ in points)
        svg.append(
            f'<polyline fill="none" stroke="var(--ink)" stroke-width="2" {dash} '
            f'stroke-linejoin="round" points="{line}"/>'
        )
        for px, py, point in points:
            tip = f"{name} · {dose_label(point)} · {point['k']} of {point['n']} pass"
            svg.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{fill}" '
                f'stroke="var(--ink)" stroke-width="2" data-t="{_e(tip)}"/>'
            )
        key.append(
            f'<span><svg width="30" height="10"><line x1="0" x2="30" y1="5" y2="5" '
            f'stroke="var(--ink)" stroke-width="2" {dash}/><circle cx="15" cy="5" r="3.5" '
            f'fill="{fill}" stroke="var(--ink)" stroke-width="2"/></svg>{_e(name)}</span>'
        )
        ends.append((points[-1][1], DOSE_NAMES.get(family, (family, family))[0]))
    placed = -100.0
    for end_y, name in sorted(ends):
        placed = max(end_y + 4, placed + 16)
        svg.append(f'<text class="lab" x="{right + 12}" y="{placed:.1f}">{_e(name)}</text>')
    svg.append("</svg>")
    facts = "".join(
        f"<li><b>{_e(DOSE_NAMES.get(family, (family, family))[1])}</b>"
        f"{_e(threshold_sentence(family, curve).capitalize())}.</li>"
        for family, curve in curves.items()
    )
    return (
        "<h2>Detection threshold</h2>"
        '<p class="lede">How much of a right answer has to be wrong before the grader notices. '
        "A grader that reads closely drops to zero at the first step.</p>"
        f'<div class="two"><div><div class="key">{"".join(key)}</div><div class="fig">{"".join(svg)}</div></div>'
        f"<ul>{facts}</ul></div>"
    )


def _profile(summary: dict[str, Any]) -> str:
    rows = summary.get("profile") or []
    if not rows:
        return ""
    body = []
    for row in rows:
        share = (row["rate"] or 0) * 100
        low, high = (row["low"] or 0) * 100, (row["high"] or 0) * 100
        tip = f"{row['edit']}: {row['k']} of {row['n']} still pass, 95% interval {span(row)}"
        body.append(
            f'<tr class="{"" if row["k"] else "zero"}" data-t="{_e(tip)}">'
            f'<td>{_e(row["notices"].capitalize())}</td><td class="l">{_e(row["edit"])}</td>'
            f'<td class="n">{row["k"]} / {row["n"]}</td><td class="n">{pct(row["rate"])}</td>'
            f'<td><div class="bar"><i style="width:{share:.1f}%"></i>'
            f'<u style="left:{low:.1f}%;width:{max(high - low, 0.6):.1f}%"></u></div></td></tr>'
        )
    return (
        "<h2>What it notices</h2>"
        '<p class="lede">Each row makes the smallest edit of one kind to a right answer and '
        "counts how often the answer still passes. A long bar is something this grader "
        "does not check.</p>"
        '<div class="scroll"><table class="t"><thead><tr><th>Does it notice</th><th>Edit</th>'
        '<th class="n">Still pass</th><th class="n">Share</th><th>0 to 100%</th></tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _dressing(summary: dict[str, Any]) -> str:
    if not summary["lift"]:
        return ""
    rows = []
    for row in summary["lift"]:
        plain, dressed = row["plain_rate"] * 100, row["dressed_rate"] * 100
        low, width = min(plain, dressed), abs(dressed - plain)
        rows.append(
            f'<tr class="{"" if row["turned"] else "zero"}"><td>{_e(row["dressing"])}</td>'
            f'<td><div class="dumb"><s style="left:{low:.1f}%;width:{width:.1f}%"></s>'
            f'<b style="left:{plain:.1f}%"></b><i style="left:{dressed:.1f}%"></i></div></td>'
            f'<td class="n">{pct(row["plain_rate"])} → {pct(row["dressed_rate"])}</td>'
            f'<td class="n">{row["turned"]} of {row["pairs"]}</td></tr>'
        )
    return (
        "<h2>Dressing</h2>"
        '<p class="lede">The same wrong answer, with one line added: a claim of expert review, '
        "a confident opener, or friendly padding. Ring is plain, dot is dressed.</p>"
        '<div class="scroll"><table class="t"><thead><tr><th>Added</th><th>Leak rate, 0 to 100%</th>'
        '<th class="n">Plain → dressed</th><th class="n">Caught answers turned</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _families(summary: dict[str, Any]) -> str:
    if not summary["families"]:
        return ""
    rows = []
    for row in summary["families"]:
        rate_pct = (row["rate"] or 0) * 100
        low, high = (row["low"] or 0) * 100, (row["high"] or 0) * 100
        tip = f"{row['family']}: {row['k']} of {row['n']} passed, 95% interval {span(row)}"
        rows.append(
            f'<tr class="{"" if row["k"] else "zero"}" data-t="{_e(tip)}">'
            f'<td class="l">{_e(row["level"])} · {_e(LEVEL_NAMES.get(row["level"], ""))}</td>'
            f'<td>{_e(row["family"])}</td><td class="n">{row["k"]} / {row["n"]}</td>'
            f'<td class="n">{pct(row["rate"])}</td>'
            f'<td><div class="bar"><i style="width:{rate_pct:.1f}%"></i>'
            f'<u style="left:{low:.1f}%;width:{max(high - low, 0.6):.1f}%"></u></div></td>'
            f'<td class="n">{span(row)}</td></tr>'
        )
    return (
        "<h2>By control</h2>"
        '<p class="lede">Only controls that must fail are counted. The bracket is the exact '
        "95% interval: with few items it stays wide even at zero leaks.</p>"
        '<div class="scroll"><table class="t"><thead><tr><th>Level</th><th>Control</th><th class="n">Leaked</th>'
        '<th class="n">Rate</th><th>0 to 100%</th><th class="n">Interval</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render(result: dict[str, Any]) -> str:
    summary = result["summary"]
    trials = result.get("trials", 1)
    plate, controls = _plate(result)
    items = {
        item_id: {"q": item.get("input"), "r": item.get("reference")}
        for item_id, item in result.get("items", {}).items()
        if any(c["i"] == item_id for c in controls.values())
    }
    edited = ["splice", "numbers", "flip", "contradict", "json-value", "json-drop"]
    data = {"c": controls, "items": items, "words": STATE_WORDS, "edited": edited}
    errors = ""
    if summary["errors"]:
        first = summary["error_examples"][0]
        errors = (
            f'<p class="note">{summary["errors"]} controls got no verdict and are not counted '
            f"as caught. First: <code>{_e(first['id'])}</code>: {_e(first['error'])}</p>"
        )
    top = (
        f"<span><b>knownbad</b></span><span>grader <code>{_e(result.get('grader'))}</code></span>"
        f"<span>{summary['controls']} controls × {trials} trial{'s' if trials != 1 else ''}</span>"
        f"<span>{_e(str(result.get('created', '')).replace('T', ' ').replace('+00:00', ' UTC'))}"
        "</span>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>knownbad report</title><style>{CSS}</style></head><body><main>"
        f'<div class="top">{top}</div>{_headline(summary)}{errors}{_readings(summary)}'
        "<h2>The plate</h2>"
        '<p class="lede">Rows are your items, columns are controls, each well is one answer '
        "the grader was shown. Select a well to read it. A lit column is a kind of answer "
        "this grader cannot see.</p>"
        f'{_legend()}<div class="bench"><div>{plate}</div>'
        '<aside class="insp" id="insp" aria-live="polite"><noscript>Turn on JavaScript to '
        "read single answers. Every number on this page is already here without it."
        "</noscript></aside></div>"
        f"{_profile(summary)}{_dose(summary)}{_dressing(summary)}{_families(summary)}"
        f'</main><div id="tip"></div><script type="application/json" id="data">{_json(data)}'
        f"</script><script>{JS}</script></body></html>\n"
    )
