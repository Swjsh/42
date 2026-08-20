"""gamma_home.py - THE command center. One self-contained HTML page, no server needed.

WHY THIS EXISTS (read markdown/planning/GAMMA-WORKER.md "Why the three prior
embodiments didn't stick" before touching this file)
------------------------------------------------------------------------------
Five presence surfaces have been built for J: the Next.js "Trade House"
dashboard, the Electron gamma-companion (:4317), the Discord voicebot, the
GAMMA HQ terminal, and the Next.js /gamma app. Their own post-mortem names the
common thread: "presence kept getting solved as an ADD-ON channel instead of
upgrading the ONE surface J might actually open unprompted."

This file is NOT a sixth channel. It is the consolidation, and it is only
justified because it RETIRES surfaces rather than adding one:
  * localhost:3000/gamma was verified DEAD on 2026-08-19 (no response) despite
    Gamma_DashboardKeepalive existing - a home base that needs a Node server
    babysat by a scheduled task is a home base that is offline when J looks.
  * J's own stated preference (2026-08-19): a localhost HTML page, "more
    editable and we can make it look how I want it to look" - the exact pattern
    he had just built himself in journal_calendar.py.

So: one Python generator -> one self-contained .html file. Double-clickable,
diffable, restyleable, and it cannot be "down".

ZERO DUPLICATED LOGIC (the state-librarian contract)
  * Presence/state/clocks/wants come from `gamma_hq.py --json` - the same pure
    helpers the terminal renders from. This page never recomputes them.
  * The calendar comes from `analysis/journal/calendar-data.json`, written by
    journal_calendar.py. This page never re-derives P&L.
  * The answers below come from live state files, each shown WITH its source
    path and its age.

FAIL LOUD, NEVER FABRICATE (OP-33 / C7)
  Any section whose source is missing or stale renders a visible amber "NO
  DATA" card naming the file it wanted. Nothing is invented, nothing silently
  degrades to a plausible-looking default.

USAGE
  python setup/scripts/gamma_home.py            # write analysis/home/index.html
  python setup/scripts/gamma_home.py --open     # ...and open it
  python setup/scripts/gamma_home.py --quiet    # no stdout except the path
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
OUT_HTML = REPO / "analysis" / "home" / "index.html"

CALENDAR_JSON = REPO / "analysis" / "journal" / "calendar-data.json"
CALENDAR_HTML = REPO / "analysis" / "journal" / "calendar.html"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
SIGNATURE_MD = REPO / "analysis" / "winner-autopsies" / "SIGNATURE.md"

# A source older than this is shown with an amber staleness badge rather than
# presented as current. Generous on purpose: this page is read after hours too.
STALE_HOURS = 24.0


# ---------------------------------------------------------------- helpers

_MD_NOISE = re.compile(r"(\*\*|`|^\s*>+\s*|^#+\s*|^\s*[-*]\s+|(?<![\w.])_(?=\w)|(?<=\w)_(?![\w.]))")


def _clean(s) -> str:
    """Strip markdown so a doc line reads as a sentence on a card.

    The sources are human/agent-authored markdown. Rendering them raw leaked
    `> **Signal J wakes to (OP-25).**` and `_Generated ... ._` onto the page.
    """
    if not isinstance(s, str):
        s = str(s)
    return re.sub(r"\s+", " ", _MD_NOISE.sub("", s)).strip()


def _clip(s: str, cap: int = 240) -> str:
    """Cut to a sentence boundary near `cap`, never mid-word."""
    s = _clean(s)
    if len(s) <= cap:
        return s
    cut = s[:cap]
    stop = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(" -- "))
    if stop > cap * 0.5:
        return cut[:stop + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _claim_of(x) -> str:
    """Pull the human claim out of a falsifiable-prediction row.

    today-bias.json stores these as dicts (and sometimes as JSON strings);
    dumping them raw put `{"claim": "...", "trigger_window": ...` on the page.
    """
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("{"):
            try:
                x = json.loads(s)
            except ValueError:
                return _clean(s)
        else:
            return _clean(s)
    if isinstance(x, dict):
        claim = x.get("claim") or x.get("prediction") or x.get("hypothesis") or ""
        win = x.get("trigger_window") or ""
        return _clean(claim) + (" (%s)" % _clean(win) if win else "")
    return _clean(x)


def _age_h(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _load_json(p: Path):
    """Return (data, meta). data is None when the source cannot be trusted."""
    meta = {"path": p.relative_to(REPO).as_posix() if str(p).startswith(str(REPO)) else str(p),
            "age_h": _age_h(p), "ok": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        meta["ok"] = True
        return data, meta
    except (OSError, ValueError) as e:
        meta["error"] = str(e)[:160]
        return None, meta


def _hq_json() -> tuple:
    """The state librarian. Same helpers gamma_hq's terminal renders from."""
    meta = {"path": "setup/scripts/gamma_hq.py --json", "age_h": 0.0, "ok": False}
    try:
        r = subprocess.run(
            [sys.executable, str(REPO / "setup" / "scripts" / "gamma_hq.py"), "--json"],
            cwd=str(REPO), capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
        )
        if r.returncode == 0 and r.stdout.strip():
            meta["ok"] = True
            return json.loads(r.stdout), meta
        meta["error"] = (r.stderr or "exit %d" % r.returncode)[:160]
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        meta["error"] = str(e)[:160]
    return None, meta


def _latest_status() -> tuple:
    """Newest STATUS.md entry: (verdict, headline, body_first_para)."""
    meta = {"path": "automation/overnight/STATUS.md", "age_h": _age_h(STATUS_MD), "ok": False}
    try:
        text = STATUS_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        meta["error"] = str(e)[:160]
        return None, meta
    m = re.search(r"^##\s*(\[[^\]]*\])\s*(.*)$", text, re.MULTILINE)
    if not m:
        meta["error"] = "no '## [ts]' heading found"
        return None, meta
    head = m.group(2).strip()
    verdict = "INFO"
    for v in ("RED", "YELLOW", "GREEN", "OK"):
        if re.match(r"^%s\b" % v, head) or head.startswith(v):
            verdict = v
            break
    body = ""
    for line in text[m.end():].splitlines():
        line = line.strip()
        if line.startswith("##"):
            break
        if line and not line.startswith("<!--"):
            body = line
            break
    meta["ok"] = True
    return {"verdict": verdict, "stamp": m.group(1).strip("[]"),
            "headline": _clip(head, 200), "body": _clip(body, 260)}, meta


def _signature_lines(n: int = 6) -> tuple:
    meta = {"path": "analysis/winner-autopsies/SIGNATURE.md", "age_h": _age_h(SIGNATURE_MD), "ok": False}
    try:
        raw = SIGNATURE_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        meta["error"] = str(e)[:160]
        return None, meta
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "<!--", "---", "|--", ">", "|")):
            continue
        c = _clean(s)
        # Skip the generator's own provenance stamp - it is not a finding.
        if not c or re.match(r"^Generated", c) or "pure Python" in c:
            continue
        out.append(c)
        if len(out) >= n:
            break
    meta["ok"] = bool(out)
    return out, meta


# ------------------------------------------------- the six repeated questions

def build_answers() -> list:
    """Pre-answer the six things J repeatedly asks.

    Sources are the registry's own j_intents mapping
    (automation/state/worker-registry.json). Every answer names its source file
    and its age; an unreadable source becomes a visible NO DATA card, never a
    confident-sounding guess.
    """
    answers = []

    # 1. Are we good to trade today? ----------------------------------------
    eng, eng_m = _load_json(STATE / "engine-health.json")
    una, una_m = _load_json(STATE / "unattended-health.json")
    chk, chk_m = _load_json(STATE / "self-check-last.json")
    parts, worst = [], "GREEN"
    rank = {"GREEN": 0, "OK": 0, "YELLOW": 1, "DEGRADED": 1, "RED": 2}
    for label, d, m in (("engine", eng, eng_m), ("unattended", una, una_m), ("self-check", chk, chk_m)):
        if not d:
            parts.append("%s: NO DATA" % label)
            worst = "RED" if worst != "RED" else worst
            continue
        v = str(d.get("verdict", "?")).upper()
        parts.append("%s %s" % (label, v))
        if rank.get(v, 1) > rank.get(worst, 0):
            worst = v
    reds = (eng or {}).get("reds") or (eng or {}).get("red_checks") or []
    detail = ""
    if isinstance(reds, list) and reds:
        detail = "RED: " + " · ".join(_clip(x, 90) for x in reds[:3])
    elif isinstance(chk, dict) and chk.get("problems"):
        pr = chk["problems"]
        detail = "problems: " + " · ".join(_clip(x, 90) for x in (pr if isinstance(pr, list) else [pr])[:3])
    answers.append({
        "q": "Are we good to trade today?",
        "verdict": worst,
        "answer": " · ".join(parts),
        "detail": detail,
        "means": ("Nothing is blocking an entry — the engine will trade if a setup fires."
                  if worst in ("GREEN", "OK") else
                  "Something upstream is degraded. Read the detail before trusting a quiet tape."),
        "sources": [eng_m, una_m, chk_m],
    })

    # 2. What's the status? --------------------------------------------------
    st, st_m = _latest_status()
    answers.append({
        "q": "What's the status?",
        "verdict": (st or {}).get("verdict", "NO DATA"),
        "answer": (st or {}).get("headline", "STATUS.md unreadable"),
        "detail": (st or {}).get("body", ""),
        "means": "This is the newest thing any autonomous fire wrote about itself.",
        "sources": [st_m],
    })

    # 3. What are we theorizing today? --------------------------------------
    bias, bias_m = _load_json(STATE / "today-bias.json")
    preds = []
    if bias:
        raw = bias.get("falsifiable_predictions") or bias.get("falsifiable_hypothesis") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        if isinstance(raw, list):
            preds = [c for c in (_claim_of(x) for x in raw[:3]) if c]
    answers.append({
        "q": "What are we theorizing today?",
        "verdict": str((bias or {}).get("bias", "NO DATA")).upper(),
        "answer": _clip((bias or {}).get("bias_note") or "today-bias.json unreadable", 300),
        "detail": " · ".join(_clip(p, 160) for p in preds),
        "means": "These are falsifiable calls written BEFORE the session — they get graded, not forgotten.",
        "sources": [bias_m],
        "stamp": (bias or {}).get("date", ""),
    })

    # 4. What's our edge? ----------------------------------------------------
    sig, sig_m = _signature_lines()
    answers.append({
        "q": "What's our edge — what's actually working?",
        "verdict": "EDGE" if sig else "NO DATA",
        "answer": _clip((sig or ["SIGNATURE.md unreadable"])[0], 220),
        "detail": " · ".join(_clip(x, 150) for x in (sig or [])[1:4]),
        "means": "Mined from real fills only — the winner signature, not a backtest.",
        "sources": [sig_m],
    })

    # 5. Where's the money? --------------------------------------------------
    cal, cal_m = _load_json(CALENDAR_JSON)
    summ = ((cal or {}).get("views", {}).get("BOOK", {}) or {}).get("summary", {})
    if summ:
        net = summ.get("total_pnl_net", 0.0)
        ans = ("BOOK net %s over %s trading days (%s trades)"
               % (_money(net), summ.get("trading_days", "?"), summ.get("total_trades", "?")))
        det = ("day win-rate %.0f%% · best %s %s · worst %s %s · $%s fees"
               % (100 * float(summ.get("win_rate_by_day_net") or 0),
                  (summ.get("best_day_net") or {}).get("date", "?"),
                  _money((summ.get("best_day_net") or {}).get("pnl", 0)),
                  (summ.get("worst_day_net") or {}).get("date", "?"),
                  _money((summ.get("worst_day_net") or {}).get("pnl", 0)),
                  format(float(summ.get("total_fees") or 0), ",.0f")))
        verdict = "GREEN" if net > 0 else "RED"
    else:
        ans, det, verdict = "calendar-data.json unreadable", "", "NO DATA"
    answers.append({
        "q": "Where's the money?",
        "verdict": verdict,
        "answer": ans,
        "detail": det,
        "means": "Net of fees, real fills, all five arms. The calendar below is the same data day by day.",
        "sources": [cal_m],
    })

    return answers


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return ("+$" if v >= 0 else "-$") + format(abs(v), ",.0f")


def compact_calendar(cal: dict) -> dict:
    """Day-level P&L only. The full per-trade payload stays in calendar.html."""
    if not cal:
        return {}
    out = {"generated_et": cal.get("generated_et"), "roster": cal.get("roster", []), "views": {}}
    for arm, view in (cal.get("views") or {}).items():
        days = {}
        for d, row in (view.get("days") or {}).items():
            days[d] = {"g": row.get("pnl_gross"), "n": row.get("pnl_net"), "t": row.get("trade_count")}
        out["views"][arm] = {"days": days, "summary": view.get("summary", {})}
    return out


# ---------------------------------------------------------------- rendering

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gamma — Command Center</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg:#0b0d12; --panel:#12151c; --panel2:#171b24; --border:#262b38;
    --text:#e7e9ee; --muted:#8b93a7; --green:#33c17a; --green-dim:#1c6a44;
    --red:#ef5350; --red-dim:#7a2426; --amber:#e0a63a; --accent:#5b8def;
  }
  *{box-sizing:border-box}
  body{background:var(--bg);color:var(--text);margin:0;padding:24px;
       font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.45}
  .wrap{max-width:1180px;margin:0 auto}
  h1{font-size:26px;margin:0 0 2px}
  h2{font-size:15px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
     margin:30px 0 12px;font-weight:600}
  .sub{color:var(--muted);font-size:13px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
  .hero{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap}
  .chip{display:inline-block;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:700;
        letter-spacing:.06em;border:1px solid var(--border);background:var(--panel2)}
  .chip.GREEN,.chip.OK,.chip.EDGE{color:var(--green);border-color:var(--green-dim)}
  .chip.RED{color:var(--red);border-color:var(--red-dim)}
  .chip.YELLOW,.chip.DEGRADED{color:var(--amber);border-color:#6b5220}
  .chip.NODATA{color:var(--amber);border-color:#6b5220}
  .rightnow{font-size:19px;margin:10px 0 4px}
  .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}
  .q{font-size:13px;color:var(--muted);margin-bottom:6px}
  .a{font-size:16px;font-weight:600;margin-bottom:6px}
  .d{font-size:13px;color:var(--muted);margin-bottom:8px;word-break:break-word}
  .means{font-size:13px;color:#b9c0d0;border-left:2px solid var(--accent);padding-left:10px;margin-top:8px}
  .src{margin-top:10px;font-size:11px;color:#5f677c}
  .src span{margin-right:10px;white-space:nowrap}
  .stale{color:var(--amber)}
  .nodata{border-color:#6b5220}
  .cal{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}
  .cal .dow{font-size:11px;color:var(--muted);text-align:center;padding-bottom:4px}
  /* flex column, not absolute positioning: at narrow widths the absolutely
     positioned P&L collided with the day number. min-height keeps empty cells
     the same size as populated ones. */
  .cell{min-height:56px;border:1px solid var(--border);border-radius:7px;background:var(--panel2);
        padding:4px 5px;font-size:11px;overflow:hidden;
        display:flex;flex-direction:column;justify-content:space-between}
  .cell.empty{background:transparent;border-color:transparent}
  .cell .dnum{color:var(--muted);line-height:1}
  /* clamp so the number shrinks on a narrow window instead of ellipsing to "+$..." */
  .cell .pnl{font-weight:700;font-size:clamp(9px,1.35vw,12px);line-height:1.1;
             white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cell.win{border-color:var(--green-dim)} .cell.win .pnl{color:var(--green)}
  .cell.loss{border-color:var(--red-dim)} .cell.loss .pnl{color:var(--red)}
  .cell.flat .pnl{color:var(--muted)}
  .row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--border);font-size:14px}
  .row:last-child{border-bottom:none}
  .row .k{color:var(--muted);font-size:12px;white-space:nowrap}
  .bar{height:6px;border-radius:3px;background:var(--panel2);overflow:hidden;margin-top:5px}
  .bar>i{display:block;height:100%;background:var(--accent)}
  a{color:var(--accent)}
  .controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
  select{background:var(--panel2);color:var(--text);border:1px solid var(--border);
         border-radius:6px;padding:5px 9px;font-size:13px}
  footer{margin-top:34px;color:#5f677c;font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div style="flex:1;min-width:320px">
      <h1>Gamma</h1>
      <div class="sub" id="stamp"></div>
      <div class="rightnow" id="rightnow"></div>
      <div class="sub" id="focus"></div>
      <div class="sub" style="margin-top:8px" id="goal"></div>
    </div>
    <div style="text-align:right"><span class="chip" id="statechip"></span></div>
  </div>

  <h2>The answers <span style="text-transform:none;letter-spacing:0;font-weight:400">— you shouldn't have to ask</span></h2>
  <div class="grid2" id="answers"></div>

  <h2>This month</h2>
  <div class="card">
    <div class="controls">
      <select id="arm"></select>
      <select id="basis"><option value="n">net of fees</option><option value="g">gross</option></select>
      <span class="sub" id="calsum"></span>
      <span style="flex:1"></span>
      <a id="fullcal" href="../journal/calendar.html">full calendar &rarr;</a>
    </div>
    <div class="cal" id="dow"></div>
    <div class="cal" id="calgrid" style="margin-top:5px"></div>
  </div>

  <div class="grid2" style="margin-top:14px">
    <div class="card">
      <h2 style="margin-top:0">Shadow clocks</h2>
      <div id="clocks"></div>
    </div>
    <div class="card">
      <h2 style="margin-top:0">What I want</h2>
      <div id="wants"></div>
    </div>
  </div>

  <h2>Recent ships</h2>
  <div class="card" id="ships"></div>

  <footer id="footer"></footer>
</div>
<script>
const D = __DATA_JSON__;

function el(t,c,h){const e=document.createElement(t);if(c)e.className=c;if(h!==undefined)e.innerHTML=h;return e;}
function cls(v){return String(v||'').replace(/[^A-Z]/gi,'').toUpperCase()||'NODATA';}
function money(v){if(v===null||v===undefined||isNaN(v))return '—';
  const s=v>=0?'+':'-';return s+'$'+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});}

// ---- presence
const hq = D.hq || {};
document.getElementById('stamp').textContent = hq.now_et_label || D.generated_et || '';
document.getElementById('rightnow').textContent = hq.right_now || 'state librarian unavailable';
document.getElementById('focus').textContent = hq.todays_focus || '';
document.getElementById('goal').textContent = hq.goal_line || '';
const sc = document.getElementById('statechip');
sc.textContent = hq.state_word || 'NO DATA'; sc.className = 'chip ' + cls(hq.state_word);

// ---- the answers
const ans = document.getElementById('answers');
(D.answers||[]).forEach(a=>{
  const nodata = cls(a.verdict)==='NODATA';
  const c = el('div','card'+(nodata?' nodata':''));
  c.appendChild(el('div','q',a.q));
  const head = el('div','a');
  head.innerHTML = '<span class="chip '+cls(a.verdict)+'" style="margin-right:8px">'+
                   (a.verdict||'—')+'</span>'+(a.answer||'');
  c.appendChild(head);
  if(a.detail) c.appendChild(el('div','d',a.detail));
  if(a.means) c.appendChild(el('div','means',a.means));
  const src = el('div','src');
  (a.sources||[]).forEach(s=>{
    const stale = s.age_h===null||s.age_h===undefined||s.age_h>D.stale_hours;
    src.appendChild(el('span',stale?'stale':'',
      (s.ok?'':'⚠ ')+s.path+(s.age_h==null?'':' · '+s.age_h.toFixed(1)+'h')));
  });
  c.appendChild(src);
  ans.appendChild(c);
});

// ---- calendar
const cal = D.calendar||{}; const views = cal.views||{};
const armSel=document.getElementById('arm'), basisSel=document.getElementById('basis');
Object.keys(views).sort((a,b)=>a==='BOOK'?-1:b==='BOOK'?1:a.localeCompare(b))
  .forEach(a=>armSel.appendChild(new Option(a,a)));
if([...armSel.options].some(o=>o.value==='BOOK')) armSel.value='BOOK';

function drawCal(){
  const v=views[armSel.value]||{days:{},summary:{}}, key=basisSel.value;
  const dow=document.getElementById('dow'); dow.innerHTML='';
  ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d=>dow.appendChild(el('div','dow',d)));
  const dates=Object.keys(v.days).sort();
  const last=dates.length?dates[dates.length-1]:(D.today||'');
  const [Y,M]=last.split('-').map(Number);
  const first=new Date(Y,M-1,1), days=new Date(Y,M,0).getDate();
  const g=document.getElementById('calgrid'); g.innerHTML='';
  for(let i=0;i<first.getDay();i++) g.appendChild(el('div','cell empty'));
  let mtot=0;
  for(let d=1;d<=days;d++){
    const iso=Y+'-'+String(M).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    const row=v.days[iso];
    const p=row?row[key]:null;
    if(p!==null&&p!==undefined) mtot+=p;
    const k=row?(p>0?'win':p<0?'loss':'flat'):'';
    const c=el('div','cell '+k);
    c.appendChild(el('div','dnum',String(d)));
    if(row){
      c.appendChild(el('div','pnl',money(p)));
      c.title=iso+' · '+row.t+' trades · '+money(p);
    }
    g.appendChild(c);
  }
  const s=v.summary||{};
  document.getElementById('calsum').textContent =
    Y+'-'+String(M).padStart(2,'0')+' '+money(mtot)+'   ·   all-time '+
    money(key==='n'?s.total_pnl_net:s.total_pnl_gross)+' over '+(s.trading_days||'?')+' days';
}
armSel.onchange=basisSel.onchange=drawCal;
if(Object.keys(views).length) drawCal();
else document.getElementById('calsum').innerHTML='<span class="stale">⚠ calendar-data.json unavailable</span>';

// ---- clocks / wants / ships
const ck=document.getElementById('clocks');
(hq.clocks||[]).forEach(c=>{
  const pct=Math.min(100,100*(c.have||0)/Math.max(1,c.need||1));
  const d=el('div');
  d.appendChild(el('div','row','<span>'+c.label+'</span><span class="k">'+c.have+' / '+c.need+'</span>'));
  const b=el('div','bar'); b.appendChild(el('i')); b.firstChild.style.width=pct+'%'; d.appendChild(b);
  if(c.explain) d.appendChild(el('div','d',c.explain));
  ck.appendChild(d);
});
if(!(hq.clocks||[]).length) ck.innerHTML='<span class="stale">⚠ no clock data</span>';

const w=document.getElementById('wants');
(hq.wants||[]).forEach((t,i)=>w.appendChild(el('div','row','<span>'+(i+1)+'. '+t+'</span>')));
if(!(hq.wants||[]).length) w.innerHTML='<span class="stale">⚠ no wants data</span>';

const sh=document.getElementById('ships');
(hq.recent_ships||[]).forEach(t=>sh.appendChild(el('div','row','<span>'+t+'</span>')));
if(!(hq.recent_ships||[]).length) sh.innerHTML='<span class="stale">⚠ no recent ships</span>';

document.getElementById('footer').innerHTML =
  'Generated '+(D.generated_et||'?')+' by setup/scripts/gamma_home.py · presence from gamma_hq.py --json · '+
  'money from journal_calendar.py · every card names its source file and age. Nothing here is inferred.';
</script>
</body>
</html>
"""


def build(quiet: bool = False) -> dict:
    hq, hq_meta = _hq_json()
    cal, cal_meta = _load_json(CALENDAR_JSON)
    payload = {
        "generated_et": _et_label(),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "stale_hours": STALE_HOURS,
        "hq": hq or {},
        "hq_source": hq_meta,
        "calendar": compact_calendar(cal or {}),
        "calendar_source": cal_meta,
        "answers": build_answers(),
    }
    if not quiet:
        if not hq_meta["ok"]:
            print("WARN: state librarian unavailable (%s) - presence renders NO DATA"
                  % hq_meta.get("error", "?"), file=sys.stderr)
        if not cal_meta["ok"]:
            print("WARN: calendar-data.json unavailable - calendar renders NO DATA", file=sys.stderr)
    return payload


def _et_label() -> str:
    try:
        r = subprocess.run([sys.executable, str(REPO / "setup" / "scripts" / "et_clock.py")],
                           cwd=str(REPO), capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M (local — et_clock unavailable)")


def render(payload: dict) -> str:
    return _TEMPLATE.replace("__DATA_JSON__", json.dumps(payload, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Gamma command center HTML.")
    ap.add_argument("--open", action="store_true", help="open the page after writing it")
    ap.add_argument("--quiet", action="store_true", help="print only the output path")
    a = ap.parse_args()

    payload = build(quiet=a.quiet)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(render(payload), encoding="utf-8")
    print(OUT_HTML.relative_to(REPO) if a.quiet else "wrote -> %s" % OUT_HTML.relative_to(REPO))

    if not a.quiet:
        nodata = [x["q"] for x in payload["answers"] if str(x.get("verdict")).upper() in ("NO DATA", "NODATA")]
        print("answers: %d rendered, %d NO DATA%s"
              % (len(payload["answers"]), len(nodata), (" -> " + "; ".join(nodata)) if nodata else ""))
    if a.open:
        webbrowser.open(OUT_HTML.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
