"""gamma_cockpit_org.py - the ORG-shaped builders for the cockpit payload.

Split out of gamma_home.py when it passed the repo's 800-line ceiling. These are
the builders that describe the FIRM rather than the market: which desks exist and
how each is doing, how the master ranks them for the next fire, the master ->
desks -> shared-functions graph, and the calendar reshaping the home grid needs.

Every function here READS already-computed state. None of them derives a trading
metric; a desk's headline number always comes from that desk's own scoreboard
file, so the cockpit can never disagree with the ledger it claims to summarise.

gamma_home re-exports all of these, so existing imports and tests are unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
REGISTRY = STATE / "worker-registry.json"
CALENDAR_JSON = REPO / "analysis" / "journal" / "calendar-data.json"


def _load_json(p: Path):
    """Local copy of gamma_home's loader — importing back would be circular."""
    meta = {"path": p.relative_to(REPO).as_posix() if str(p).startswith(str(REPO)) else str(p),
            "age_h": _age_h(p), "ok": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        meta["ok"] = True
        return data, meta
    except (OSError, ValueError) as e:
        meta["error"] = str(e)[:160]
        return None, meta


def _age_h(p: Path):
    try:
        return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600.0
    except OSError:
        return None


def _rows(p: Path) -> int:
    try:
        return sum(1 for line in p.open(encoding="utf-8", errors="replace") if line.strip())
    except OSError:
        return 0


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return ("+$" if v >= 0 else "-$") + format(abs(v), ",.0f")


def build_desks() -> dict:
    """The org, by DESK — the decomposition J asked for and the one the research backs.

    Desks are split by INSTRUMENT, which is a real context boundary: the futures
    desk never needs SPY's ribbon width, the multi-sector desk never needs a 0DTE
    expiry. (The nine workers in the registry are split by ROLE, which is the
    anti-pattern Anthropic names — kept as SHARED FUNCTIONS a desk invokes, not
    as context owners.)

    Each desk's headline number comes from that desk's OWN scoreboard file. No
    desk grades its own homework here — this only reads what each already wrote.
    """
    reg, reg_meta = _load_json(REGISTRY)
    desks = (reg or {}).get("desks", [])
    out = []

    for d in desks:
        did = d.get("id")
        metric, sub, chip = "—", "", d.get("status", "")

        if did == "spy-0dte":
            cal, _m = _load_json(CALENDAR_JSON)
            s = ((cal or {}).get("views", {}).get("BOOK", {}) or {}).get("summary", {})
            if s:
                metric = "%s net" % _money(s.get("total_pnl_net"))
                sub = "%s trading days · %s trades · %.0f%% day WR" % (
                    s.get("trading_days", "?"), s.get("total_trades", "?"),
                    100 * float(s.get("win_rate_by_day_net") or 0))
            chip = "REAL FILLS"

        elif did == "futures":
            fut = STATE / "futures"
            mirror, _ = _load_json(fut / "shadow-progress.json")
            edge3, _ = _load_json(fut / "edge3-sim-progress.json")
            live = sum(1 for f in ("trader/heartbeat.json", "trader-broker/heartbeat.json",
                                   "shadow-progress.json", "edge3-sim-progress.json",
                                   "ssr-shadow-progress.json")
                       if (_age_h(fut / f) or 1e9) <= 24)
            bar = (mirror or {}).get("arming_bar", {})
            metric = "%d/5 lanes live" % live
            sub = "MES mirror %s/%s trips %s%s" % (
                bar.get("round_trips_have", "?"), bar.get("round_trips_needed", "?"),
                _money((mirror or {}).get("total_pnl_usd")),
                " · ARMABLE" if bar.get("armable") else "")
            if edge3:
                sub += " · edge3 %s/%s" % (edge3.get("n_closed_round_trips", "?"),
                                           edge3.get("falsification_floor", "?"))
            chip = "SIM ONLY"

        elif did == "multi-sector":
            # Two things live here and they are NOT the same: a LIVE multi-symbol
            # shadow lane (multi-1, Gamma_MultiCore, ~72 names, 15-min RTH) and the
            # RETIRED weekly-options v1 signal that failed its null. Reporting only
            # the dead half is how this desk read as "killed" while it was ticking.
            mu = STATE / "multi"
            wk = STATE / "weekly"
            n_multi = _rows(mu / "shadow-ledger.jsonl")
            n_weekly = _rows(wk / "variant-daily-ledger.jsonl") + _rows(wk / "expiry-experiment-shadow-ledger.jsonl")
            fresh = (_age_h(mu / "shadow-ledger.jsonl") or 1e9) <= 24
            metric = "%d multi-1 shadow rows" % n_multi
            sub = ("multi-1 ticking (%s) · weekly v1 signal killed on its null, %d archived rows"
                   % ("fresh" if fresh else "STALE >24h", n_weekly))
            chip = "SHADOW" if fresh else "STALE"

        elif did == "prediction-markets":
            k = STATE / "kalshi"
            n = _rows(k / "shadow-ledger.jsonl")
            age = _age_h(k / "last-tick.json")
            live = age is not None and age <= 48
            metric = "%d shadow rows" % n
            sub = ("per-city bar: >=20 settled days, >=45%% hit, err <=1.6F" if live
                   else "LANE NOT TICKING — last tick %s" % (
                       "%.0fh (%.1f days) ago" % (age, age / 24) if age is not None else "never"))
            chip = "SHADOW" if live else "STALE"

        out.append({
            "id": did, "name": d.get("name"), "instrument": d.get("instrument"),
            "chip": chip, "metric": metric, "sub": sub,
            "arms": d.get("arms", []), "arming_bar": d.get("arming_bar", ""),
            "functions": d.get("functions_it_invokes", []),
        })

    return {"desks": out, "source": reg_meta,
            "master": (reg or {}).get("master", {}).get("name", "gamma"),
            "functions": [w.get("name") for w in (reg or {}).get("workers", [])]}

def build_allocation() -> dict:
    """The master's desk ranking. Imported, never re-derived (one canonical source)."""
    try:
        import desk_allocator as da
        return da.allocate()
    except Exception as e:                      # noqa: BLE001 - page must render regardless
        return {"error": str(e)[:160], "desks": []}

def build_org() -> dict:
    """Master -> desks -> shared functions, for the org graph.

    Edges are DELEGATION, labelled with what the desk owns -- per the UX research,
    an org chart that only shows hierarchy is static; labelling the edge with what
    is delegated makes it read as a live map of who owns what.
    """
    reg, meta = _load_json(REGISTRY)
    reg = reg or {}
    return {
        "master": reg.get("master", {}),
        "desks": [{"id": d["id"], "name": d["name"], "status": d.get("status", ""),
                   "instrument": d.get("instrument", ""),
                   "functions": d.get("functions_it_invokes", [])}
                  for d in reg.get("desks", [])],
        "functions": [{"name": w["name"], "model": w.get("model"), "tier": w.get("tier"),
                       "owns": w.get("owns", ""), "verified_by": w.get("verified_by", ""),
                       "j_intent": w.get("j_intent")}
                      for w in reg.get("workers", [])],
        "contract": reg.get("delegation_contract", {}),
        "source": meta,
    }

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
  .want{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--border)}
  .want:last-child{border-bottom:none}
  .want .wnum{color:var(--accent);font-weight:700;font-size:13px;min-width:14px}
  .want .wtxt{font-size:13.5px;line-height:1.5;word-break:break-word}
  .want .wstale{color:var(--amber);font-size:11.5px;margin-left:6px;white-space:nowrap}
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
// Full text from gamma-wants.json; hq.wants is the terminal's 120-char cut and is
// only a fallback. These wrap - a want J cannot finish reading is a want he ignores.
const wantRows = (D.wants_full||[]).map(x=>x.text);
const wantsSrc = wantRows.length ? wantRows : (hq.wants||[]);
wantsSrc.forEach((t,i)=>{
  const r=el('div','want');
  r.appendChild(el('div','wnum',(i+1)));
  const body = el('div','wtxt', t);
  const meta = (D.wants_full||[])[i];
  if (meta && meta.stale) body.appendChild(el('span','wstale',
    ' ⚠ unverified' + (meta.verified_at ? ' since ' + meta.verified_at : '')));
  r.appendChild(body);
  w.appendChild(r);
});
if(!wantsSrc.length) w.innerHTML='<span class="stale">⚠ no wants data</span>';

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

def calendar_scale(cal: dict) -> dict:
    """Clamp the colour ramp so one blowout day does not wash out the month.

    UX research (dashboard anti-patterns, 'Rainbow Heatmap of Sadness'): saturate
    the scale at ~2x the trailing average absolute day, and annotate the true
    min/max rather than letting extremes own the ramp.
    """
    vals = []
    for view in (cal.get("views") or {}).values():
        for row in (view.get("days") or {}).values():
            v = row.get("n")
            if isinstance(v, (int, float)):
                vals.append(abs(v))
    if not vals:
        return {"clamp": 500.0, "max_abs": 0.0}
    vals.sort()
    trailing = vals[-30:] if len(vals) > 30 else vals
    avg = sum(trailing) / len(trailing)
    return {"clamp": max(200.0, 2.0 * avg), "max_abs": vals[-1]}
