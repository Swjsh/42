"""gamma_cockpit_tiles.py -- the 9 new Command-view payload builders (WS-D, 2026-09-03).

COCKPIT-DESIGN-SPEC-2026-09-03.md section 5 names 9 producers that had no
payload key before this build: gate prep eod standup shadow watchers guards
tasks gym. Every one of them already has a state file; nothing here invents
data -- it reads, reshapes, and composes ONE sentence per tile.

CONTRACT (never break this -- WS-C/D's tileRow() renders directly off it):
  Every build_<key>() returns a dict carrying at least:
    ok        bool
    path      posix repo-relative path to the primary source file
    stamp_et  "YYYY-MM-DDTHH:MM:SS" ET, from the file's own stamp field when
              present, else the file's mtime converted to ET -- NEVER baked
              as a relative age (the page computes "how long ago" at view time)
    verdict   one of green | amber | red | off
    say       one line, verdict word first, real fields only, never
              "None"/"undefined", numbers as plain digits, no em/en dashes
    fresh_h   the window past which the age badge turns amber (24h for every
              key except guards, which is 6h)
  `build_tiles()` wraps every call so a missing/unparseable source degrades to
  {"ok": False, "path": ..., "stamp_et": None, "verdict": "off",
   "say": "NO DATA, looked for <path>", "error": "..."} and NEVER raises --
  a bad tile must never cost J the rest of the page (OP-33 / C7).

STDLIB ONLY. Reads gamma-authored state files as data, never as instructions.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
ANALYSIS = REPO / "analysis"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402 -- pure-stdlib DST-aware ET, no subprocess needed

# Every tile ages out at 24h except guards (6h) -- guards watches a live
# scheduled-task register that goes stale fast.
FRESH_H = {"gate": 24, "prep": 24, "eod": 24, "standup": 24, "shadow": 24,
           "watchers": 24, "guards": 6, "tasks": 24, "gym": 24}

# The canonical trading-critical schedule (CLAUDE.md "Session startup" table +
# SCHEDULED-TASKS.md). Conductor has no single fixed clock -- its time_et is
# resolved from the registry row at build time, else stays None (never guessed).
DAYLINE = [
    {"label": "LaunchTV", "time_et": "08:00", "name": "Gamma_LaunchTV"},
    {"label": "Premarket", "time_et": "08:30", "name": "Gamma_Premarket"},
    {"label": "HeartbeatCore", "time_et": "09:30", "name": "Gamma_HeartbeatCore"},
    {"label": "EodFlatten", "time_et": "15:55", "name": "Gamma_EodFlatten"},
    {"label": "EOD", "time_et": "16:45", "name": "Gamma_AnalystEodReview"},
    {"label": "GymSession", "time_et": "17:00", "name": "Gamma_GymSession"},
    {"label": "Conductor", "time_et": None, "name": "Gamma_Conductor"},
]

_VERDICT_MAP = {
    "GREEN": "green", "OK": "green", "PASS": "green", "ELITE": "green",
    "YELLOW": "amber", "DEGRADED": "amber", "CAUTION": "amber", "WARN": "amber",
    "INSUFFICIENT": "amber", "INSUFFICIENT_DAYS": "amber",
    "RED": "red", "FAIL": "red", "FAILED": "red", "BROKEN": "red",
}


def _verdict_word(v) -> str:
    return _VERDICT_MAP.get(str(v).upper(), "off")


def _rel(p: Path) -> str:
    """Posix repo-relative path. Falls back to a posix-ified absolute string
    for a path outside REPO (a monkeypatched tmp_path in tests)."""
    try:
        return p.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return str(p).replace("\\", "/")


def _stamp_from_mtime(p: Path):
    try:
        utc = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return et_now(now_utc=utc).replace(microsecond=0).isoformat()
    except OSError:
        return None


def _parse_any_dt(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _stamp_from_source(s):
    """Normalize a stamp string of unknown tz-awareness to a naive ET ISO
    string. Aware stamps (gym-scorecard's UTC) are converted; naive stamps
    (every ts_et/generated_et field this rig writes) are already ET."""
    d = _parse_any_dt(s)
    if d is None:
        return None
    if d.tzinfo is not None:
        d = et_now(now_utc=d.astimezone(timezone.utc))
    return d.replace(microsecond=0).isoformat()


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    return ("+$" if v >= 0 else "-$") + format(abs(v), ",.0f")


_MD_NOISE = re.compile(r"(\*\*|`|^\s*>+\s*|^#+\s*|^\s*[-*]\s+|(?<![\w.])_(?=\w)|(?<=\w)_(?![\w.]))")


def _clean_md(s) -> str:
    if not isinstance(s, str):
        s = str(s)
    return re.sub(r"\s+", " ", _MD_NOISE.sub("", s)).strip()


def _claim_text(x) -> str:
    """Same shape gamma_home._claim_of reads -- a falsifiable-prediction row
    as a claim + trigger window sentence, never raw JSON."""
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("{"):
            try:
                x = json.loads(s)
            except ValueError:
                return _clean_md(s)
        else:
            return _clean_md(s)
    if isinstance(x, dict):
        claim = x.get("claim") or x.get("prediction") or x.get("hypothesis") or ""
        win = x.get("trigger_window") or ""
        return _clean_md(claim) + (" (%s)" % _clean_md(win) if win else "")
    return _clean_md(x)


def _find_gym_path(today: str):
    """Today's scorecard, else the newest one on disk. Returns (path, is_fallback)."""
    p = STATE / ("gym-scorecard-%s.json" % today)
    if p.exists():
        return p, False
    candidates = sorted(STATE.glob("gym-scorecard-*.json"),
                         key=lambda x: x.stat().st_mtime, reverse=True)
    return (candidates[0], True) if candidates else (p, False)


# --------------------------------------------------------------- gate

def build_gate() -> dict:
    p = ANALYSIS / "go-live-gate.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    overall = str(data.get("overall_verdict", "?")).upper()
    stat = (data.get("criteria") or {}).get("statistical") or {}
    roll = stat.get("book_wide_correlated_rollup") or {}

    def _view(v):
        if not isinstance(v, dict):
            return None
        return {"ci_lower": v.get("ci_lower_2.5"), "pf_point": v.get("pf_point"),
                "n_days": v.get("n_days"), "total_pnl": v.get("total_pnl")}

    ci = {"as_traded": _view(roll.get("as_traded")),
          "ex_best_day": _view(roll.get("ex_best_day")),
          "cost_adjusted": _view(roll.get("cost_adjusted_fees_plus_2c_slip"))}

    per_arm = []
    for arm, d in (stat.get("per_arm") or {}).items():
        if not isinstance(d, dict):
            continue
        at = d.get("as_traded") or {}
        per_arm.append({"arm": arm, "ci_lower": at.get("ci_lower_2.5"),
                         "distance": d.get("distance"), "pass": bool(d.get("pass"))})

    op = (data.get("criteria") or {}).get("operational") or {}
    op_guards = [{"name": name, "status": "green" if (isinstance(g, dict) and g.get("pass")) else "red"}
                 for name, g in (op.get("guards") or {}).items()]
    operational = {"pass": bool(op.get("pass")), "guards": op_guards}

    rec = (data.get("criteria") or {}).get("reconciliation") or {}
    rec_arms = [{"arm": arm, "status": "reconciled" if (isinstance(d, dict) and d.get("reconciled")) else "not reconciled"}
                for arm, d in (rec.get("per_arm") or {}).items()]
    reconciliation = {"pass": bool(rec.get("pass")), "per_arm": rec_arms}

    ps = (data.get("criteria") or {}).get("prod_shadow") or {}
    prod_shadow = {"designation": ps.get("designation"), "days_scored": ps.get("days_scored"),
                   "days_needed": ps.get("days_needed"), "status": ps.get("status"),
                   "pass": bool(ps.get("pass"))}

    disclosures = [str(d["label"]) for d in (data.get("disclosures") or {}).values()
                   if isinstance(d, dict) and d.get("label")]
    rc_warn = (data.get("regime_coverage") or {}).get("calm_only_window_warning")
    if rc_warn:
        disclosures.append(str(rc_warn))

    fut = data.get("futures")
    futures = ({"verdict": fut.get("lane_verdict"), "generated_et": fut.get("generated_et")}
               if isinstance(fut, dict) and fut else None)

    n_trades, n_days = roll.get("n_engine_trades"), roll.get("n_trading_days")
    at = ci.get("as_traded") or {}
    if at.get("ci_lower") is not None and n_days is not None:
        say = "%s. PF CI-lower %.2f vs 1.0, %s days" % (overall, at["ci_lower"], n_days)
    else:
        say = "%s. see expansion" % overall

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(data.get("generated_et")) or _stamp_from_mtime(p),
        "verdict": _verdict_word(overall), "say": say,
        "overall_verdict": overall, "n_trades": n_trades, "n_days": n_days,
        "ci": ci, "per_arm": per_arm, "operational": operational,
        "reconciliation": reconciliation, "prod_shadow": prod_shadow,
        "disclosures": disclosures, "futures": futures,
    }


# --------------------------------------------------------------- prep

def build_prep() -> dict:
    p = STATE / "premarket-readiness.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    verdict = str(data.get("verdict", "?")).upper()
    checks = [{"name": c.get("name"), "status": c.get("status"),
               "detail": c.get("detail"), "critical": bool(c.get("critical"))}
              for c in (data.get("checks") or []) if isinstance(c, dict)]
    reds = [str(x) for x in (data.get("reds") or [])]
    ts_et = data.get("ts_et")

    bias_claims = []
    try:
        bias = json.loads((STATE / "today-bias.json").read_text(encoding="utf-8"))
        preds = bias.get("falsifiable_predictions") or bias.get("falsifiable_hypothesis") or []
        if isinstance(preds, (str, dict)):
            preds = [preds]
        if isinstance(preds, list):
            bias_claims = [c for c in (_claim_text(x) for x in preds[:5]) if c]
    except (OSError, ValueError):
        bias_claims = []

    time_part = "?"
    if ts_et:
        m = re.search(r'(\d{2}:\d{2})', ts_et)
        time_part = m.group(1) if m else ts_et[:5]
    say = "%s at %s. %d checks, %d red" % (verdict, time_part, len(checks), len(reds))

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(ts_et) or _stamp_from_mtime(p),
        "verdict": _verdict_word(verdict), "say": say,
        "ts_et": ts_et, "checks": checks, "reds": reds,
        "n_checks": len(checks), "n_red": len(reds), "bias_claims": bias_claims,
    }


# --------------------------------------------------------------- eod

_QB = re.compile(r'<!--\s*QUANT:BEGIN')
_QE = re.compile(r'<!--\s*QUANT:END\s*-->')
_TABLE_ROW = re.compile(r'^\|.+\|$')
_TABLE_SEP = re.compile(r'^\|[\s:\-|]+\|$')


def _strip_md_cell(s: str) -> str:
    s = s.strip()
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    return s.strip('`').strip()


def _parse_md_tables(text: str) -> list:
    lines = text.splitlines()
    tables, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if _TABLE_ROW.match(line) and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
            header = [_strip_md_cell(c) for c in line.strip('|').split('|')]
            j, rows = i + 2, []
            while j < len(lines) and _TABLE_ROW.match(lines[j].strip()):
                cells = [_strip_md_cell(c) for c in lines[j].strip().strip('|').split('|')]
                if len(cells) == len(header):
                    rows.append(dict(zip(header, cells)))
                j += 1
            tables.append(rows)
            i = j
        else:
            i += 1
    return tables


def _to_int(s):
    try:
        return int(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _row_counts(r: dict) -> dict:
    return {"ticks": _to_int(r.get("ticks")), "signals": _to_int(r.get("signals")),
            "enter": _to_int(r.get("ENTER")), "rule_blocked": _to_int(r.get("rule-blocked")),
            "attempted": _to_int(r.get("attempted")), "accepted": _to_int(r.get("accepted")),
            "filled": _to_int(r.get("filled")), "exited": _to_int(r.get("exited"))}


def build_eod() -> dict:
    today = et_now().strftime("%Y-%m-%d")
    p = ANALYSIS / "eod" / ("%s.md" % today)
    text = p.read_text(encoding="utf-8")
    mb, me = _QB.search(text), _QE.search(text)
    if not mb or not me or me.start() <= mb.start():
        raise ValueError("QUANT markers not found in %s" % _rel(p))
    block = text[mb.end():me.start()]

    gm = re.search(r'Generated\s+([0-9T:\-]+)\s*ET', block)
    generated_et = gm.group(1) if gm else None
    vm = re.search(r'Funnel verdict:\s*\*\*([A-Z_]+)\*\*', block)
    funnel_verdict = vm.group(1) if vm else "?"

    total, accounts, why = {}, [], []
    for rows in _parse_md_tables(block):
        if not rows:
            continue
        keys = set(rows[0].keys())
        if {"ticks", "signals", "ENTER"}.issubset(keys):
            for r in rows:
                acct = _strip_md_cell(r.get("account", ""))
                counts = _row_counts(r)
                counts["account"] = acct
                (total.update(counts) if acct.upper() == "TOTAL" else accounts.append(counts))
        elif "traded" in keys and "account" in keys:
            for r in rows:
                why.append({"account": r.get("account"),
                             "traded": str(r.get("traded", "")).strip().lower() == "yes",
                             "cause": r.get("dominant cause"), "detail": r.get("detail")})

    am = re.search(
        r'analyst[^\n]{0,40}verdict\D{0,10}:?\s*([A-Z_]+).{0,200}?rule[- ]?breaks?\D{0,10}:?\s*(\d+)',
        block, re.I | re.S)
    analyst = {"verdict": am.group(1).upper(), "rule_breaks": int(am.group(2))} if am else None

    if total.get("filled") is not None and total.get("enter") is not None:
        say = "%s. %s filled of %s ENTER, %d arms" % (funnel_verdict, total["filled"], total["enter"], len(accounts))
    else:
        say = "%s. see expansion" % funnel_verdict

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(generated_et) or _stamp_from_mtime(p),
        "verdict": _verdict_word(funnel_verdict), "say": say,
        "date": today, "funnel_verdict": funnel_verdict, "generated_et": generated_et,
        "total": total, "accounts": accounts, "why": why, "analyst": analyst,
    }


# --------------------------------------------------------------- standup

def build_standup() -> dict:
    p = STATE / "gamma-standup-latest.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    mode = str(data.get("mode", "?"))
    generated_et = data.get("generated_et")
    focus = data.get("focus") or ""
    text_plain = _clean_md(data.get("text") or "")
    wants_shown = [str(w) for w in (data.get("wants_shown") or [])]

    time_part = "?"
    if generated_et:
        m = re.search(r'(\d{2}:\d{2})', generated_et)
        time_part = m.group(1) if m else generated_et[:5]
    say = "%s standup %s. %s" % (mode.upper(), time_part, focus or "no focus recorded")

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(generated_et) or _stamp_from_mtime(p),
        "verdict": "off", "say": say,
        "mode": mode, "generated_et": generated_et, "focus": focus,
        "text_plain": text_plain, "wants_shown": wants_shown,
    }


# --------------------------------------------------------------- shadow

def build_shadow() -> dict:
    p = REPO / "SHADOW.md"
    text = p.read_text(encoding="utf-8")
    section_starts = [m.start() for m in re.finditer(r'^##\s+.*$', text, re.M)]
    n_sections = len(section_starts)

    sm = re.search(r'`([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9:]+)', text)
    stamp = _stamp_from_source(sm.group(1)) if sm else None
    stamp = stamp or _stamp_from_mtime(p)

    if n_sections == 0:
        return {"ok": False, "path": _rel(p), "stamp_et": stamp, "verdict": "off",
                "say": "NO DATA, parser found 0 sections in SHADOW.md",
                "n_sections": 0, "live": [], "preregs": {"total_non_terminal": 0, "buckets": []}}

    live = []
    m_live = re.search(r'^##\s+Live shadow instruments\s*$', text, re.M)
    if m_live:
        nxt = next((s for s in section_starts if s > m_live.start()), len(text))
        for line in text[m_live.end():nxt].splitlines():
            lm = re.match(r'^-\s+\*\*(.+?)\*\*', line.strip())
            if lm:
                clock_line = line.strip()[2:].strip()
                live.append({"name": lm.group(1).strip(), "line": clock_line,
                             "verdict": _shadow_clock_verdict(clock_line)})

    total_non_terminal, buckets = 0, []
    m_frozen = re.search(r'^##\s+Frozen preregs\s+\S+\s+auto-discovered.*?\((\d+)\s+non-terminal\)', text, re.M)
    if m_frozen:
        total_non_terminal = int(m_frozen.group(1))
        nxt = next((s for s in section_starts if s > m_frozen.start()), len(text))
        for line in text[m_frozen.end():nxt].splitlines():
            bm = re.match(r'^###\s+(?:`([^`]+)`|(.+?))\s*\((\d+)\)\s*$', line.strip())
            if bm:
                status = (bm.group(1) or bm.group(2) or "").strip()
                buckets.append({"status": status, "n": int(bm.group(3))})

    say = "%d shadow clocks, %d preregs, 0 armed" % (len(live), total_non_terminal)
    return {
        "ok": True, "path": _rel(p), "stamp_et": stamp, "verdict": "off", "say": say,
        "n_sections": n_sections, "live": live,
        "preregs": {"total_non_terminal": total_non_terminal, "buckets": buckets},
        # Vitals-grid heatmap cells (spec 10.1 "Shadow board (heatmap 12x3 of
        # clocks by verdict)"): one dot per live clock, verdict word ONLY
        # (never a colour) so the client's gfxHeatV just maps a known word.
        "heat": [c["verdict"] for c in live][:36],
    }


# Explicit-only keyword scan of a live clock's own SHADOW.md line -- a
# verdict is claimed ONLY when the line itself uses one of these exact
# words (KILL/FAIL/RED = red, EXTEND/PASS/GREEN = green); anything else
# (a still-collecting clock, ambiguous prose) stays "off" rather than
# guessing a colour the source text never stated (C7: never fabricate).
_SHADOW_RED_RE = re.compile(r"\bKILL\b|\bFAIL(?:S|ED)?\b|\bRED\b", re.I)
_SHADOW_GREEN_RE = re.compile(r"\bEXTEND\b|\bPASS(?:ES|ED)?\b|\bGREEN\b", re.I)
# "NOT a green light" is exactly the kind of prose this scan must not read
# backwards -- a bare keyword match a few words after a "not" reads the
# opposite of what the sentence says, so a nearby negation drops the match
# rather than being counted (real SHADOW.md line, 2026-09-03: the trendline
# shadow clock's "NOT a green light" would otherwise render as green).
_SHADOW_NEGATED_RE = re.compile(r"\bnot\b[^.;]{0,24}\b(kill|fail(?:s|ed)?|red|extend|pass(?:es|ed)?|green)\b", re.I)


def _shadow_clock_verdict(line: str) -> str:
    negated_spans = {m.start(1) for m in _SHADOW_NEGATED_RE.finditer(line)}

    def _hit(rx):
        for m in rx.finditer(line):
            if m.start() not in negated_spans:
                return True
        return False

    if _hit(_SHADOW_RED_RE):
        return "red"
    if _hit(_SHADOW_GREEN_RE):
        return "green"
    return "off"


# --------------------------------------------------------------- watchers

def build_watchers() -> dict:
    p = STATE / "watcher-summary.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    graded_at = data.get("graded_at")
    total_obs = data.get("total_observations")
    pnl_map = data.get("would_be_pnl_by_watcher") or {}
    outcomes = data.get("outcomes_by_watcher") or {}

    obs_by_watcher = {}
    for k, v in outcomes.items():
        name = k.rsplit("__", 1)[0]
        obs_by_watcher[name] = obs_by_watcher.get(name, 0) + (v if isinstance(v, (int, float)) else 0)

    watchers = [{"name": name, "observations": obs_by_watcher.get(name, 0), "would_be_pnl": pnl}
                for name, pnl in pnl_map.items()]
    watchers.sort(key=lambda w: w["would_be_pnl"] if isinstance(w["would_be_pnl"], (int, float)) else 0,
                  reverse=True)
    best = watchers[0] if watchers else None
    best_line = "none" if not best else "%s %s" % (best["name"], _money(best["would_be_pnl"]))
    say = "%d watching, %s observations, best %s" % (
        len(watchers), total_obs if total_obs is not None else "?", best_line)

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(graded_at) or _stamp_from_mtime(p),
        "verdict": "off", "say": say,
        "graded_at": graded_at, "total_observations": total_obs, "watchers": watchers,
        "best": ({"name": best["name"], "pnl": best["would_be_pnl"]} if best else None),
    }


# --------------------------------------------------------------- guards

def build_guards() -> dict:
    p = STATE / "task-state-guard.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    verdict = str(data.get("verdict", "?")).upper()
    ts_et = data.get("ts_et")
    tasks = [{"name": t.get("name"), "tier": t.get("tier"), "state": t.get("state"),
              "severity": t.get("severity"), "action": t.get("action"), "note": t.get("note", "")}
             for t in (data.get("tasks") or []) if isinstance(t, dict)]
    problems = [str(x) for x in (data.get("problems") or [])]
    repairs = [str(x) for x in (data.get("repairs") or [])]
    say = "%s. %d tasks watched, %d problems, %d repairs" % (verdict, len(tasks), len(problems), len(repairs))

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_source(ts_et) or _stamp_from_mtime(p),
        "verdict": _verdict_word(verdict), "say": say,
        "ts_et": ts_et, "tasks": tasks, "problems": problems, "repairs": repairs,
    }


# --------------------------------------------------------------- tasks

_TASK_ROW = re.compile(r'^\|\s*`(Gamma_[A-Za-z0-9_]+)`\s*\|\s*([^|]*)\|')
_SECTION_KEYS = (("active tasks", "Active"), ("wired", "Wired"),
                  ("proposed", "Proposed"), ("disabled tasks", "Disabled"))
_LANE_ORDER = ["Trading", "Premarket", "EOD", "Kitchen", "Shadow", "Guards", "Other"]
_SEV_RANK = {"ok": 0, "info": 0, "green": 0, "warn": 1, "yellow": 1, "amber": 1,
             "red": 2, "critical": 3}


def _parse_scheduled_tasks(text: str) -> list:
    rows, section = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            hm = re.match(r'^##\s+(.+?)(?:\s*\(|$)', stripped)
            heading = hm.group(1).strip().lower() if hm else ""
            section = next((lbl for key, lbl in _SECTION_KEYS if heading.startswith(key)), None)
            continue
        if section is None:
            continue
        rm = _TASK_ROW.match(line)
        if rm:
            rows.append({"name": rm.group(1), "cadence": rm.group(2).strip(), "section": section})
    return rows


def _lane_for(name: str) -> str:
    n = name.lower()
    if "guard" in n:
        return "Guards"
    if "kitchen" in n:
        return "Kitchen"
    if "shadow" in n:
        return "Shadow"
    if "premarket" in n or "preopen" in n:
        return "Premarket"
    if "eod" in n:
        return "EOD"
    if any(k in n for k in ("heartbeat", "sightbeacon", "launchtv", "tvwatchdog")):
        return "Trading"
    return "Other"


def build_tasks() -> dict:
    p = STATE / "SCHEDULED-TASKS.md"
    text = p.read_text(encoding="utf-8", errors="replace")
    all_rows = _parse_scheduled_tasks(text)

    try:
        guard_data = json.loads((STATE / "task-state-guard.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guard_data = {}
    guard_map = {t.get("name"): t for t in (guard_data.get("tasks") or []) if isinstance(t, dict)}

    lanes = {lbl: [] for lbl in _LANE_ORDER}
    for row in all_rows:
        g = guard_map.get(row["name"])
        guarded = bool(g)
        state = g.get("state") if g else "not guarded"
        severity = str(g.get("severity")).lower() if g and g.get("severity") is not None else None
        lanes[_lane_for(row["name"])].append({
            "name": row["name"], "cadence": row["cadence"], "section": row["section"],
            "guarded": guarded, "state": state, "severity": severity})

    lane_list = []
    for lbl in _LANE_ORDER:
        rows = lanes[lbl]
        guarded_sevs = [t["severity"] for t in rows if t["guarded"] and t["severity"] is not None]
        if guarded_sevs:
            worst = max(guarded_sevs, key=lambda s: _SEV_RANK.get(s, 1))
        else:
            worst = "not guarded" if rows else "empty"
        lane_list.append({"lane": lbl, "worst": worst, "tasks": rows})

    registered = sum(1 for r in all_rows if r["section"] in ("Active", "Disabled"))
    disabled = sum(1 for r in all_rows if r["section"] == "Disabled")
    ready = registered - disabled
    failed_today = sum(
        1 for t in guard_map.values()
        if t.get("last_result") not in (0, None) or str(t.get("severity", "")).lower() not in ("ok", "", "green"))

    today = et_now().strftime("%Y-%m-%d")
    gym_p, gym_fallback = _find_gym_path(today)
    gym_fired = gym_p.exists() and not gym_fallback
    eod_fired = (ANALYSIS / "eod" / ("%s.md" % today)).exists()

    def _guard_fire(name):
        g = guard_map.get(name)
        if not g:
            return None, None
        lr = g.get("last_result")
        return True, (lr not in (0, None))

    dayline = []
    for entry in DAYLINE:
        time_et, name = entry["time_et"], entry["name"]
        if name == "Gamma_AnalystEodReview":
            fired, failed = eod_fired, None
        elif name == "Gamma_GymSession":
            fired, failed = gym_fired, None
        else:
            fired, failed = _guard_fire(name)
        if name == "Gamma_Conductor" and time_et is None:
            row = next((r for r in all_rows if r["name"] == name), None)
            tm = re.search(r'(\d{2}:\d{2})\s*ET', row["cadence"]) if row else None
            time_et = tm.group(1) if tm else None
        dayline.append({"label": entry["label"], "time_et": time_et, "name": name,
                         "fired_today": fired, "failed_today": failed})

    say = "%d registered, %d ready, %d disabled, %d failed today" % (registered, ready, disabled, failed_today)
    verdict = "red" if failed_today else ("amber" if disabled else "green")

    return {
        "ok": True, "path": _rel(p), "stamp_et": _stamp_from_mtime(p),
        "verdict": verdict, "say": say,
        "registered": registered, "ready": ready, "disabled": disabled,
        "failed_today": failed_today, "lanes": lane_list, "dayline": dayline,
    }


# --------------------------------------------------------------- gym

def build_gym() -> dict:
    today = et_now().strftime("%Y-%m-%d")
    p, is_fallback = _find_gym_path(today)
    data = json.loads(p.read_text(encoding="utf-8"))
    for_date = data.get("for_date")
    overall = str(data.get("overall_verdict", "?")).upper()
    audits = [{"name": a.get("name"), "source_file": a.get("source_file"),
               "verdict": a.get("verdict"), "summary": a.get("summary")}
              for a in (data.get("audits") or []) if isinstance(a, dict)]
    stale = data.get("stale_reruns") or {}
    stale_list = ([{"name": k, "exit": (v or {}).get("exit"), "log_tail": (v or {}).get("log_tail")}
                   for k, v in stale.items()] if isinstance(stale, dict) else [])
    say = "%s. %d audits, %d rerun stale" % (overall, len(audits), len(stale_list))

    return {
        "ok": True, "path": _rel(p),
        "stamp_et": _stamp_from_source(data.get("generated_at")) or _stamp_from_mtime(p),
        "verdict": _verdict_word(overall), "say": say,
        "for_date": for_date, "is_fallback": bool(is_fallback or (for_date and for_date != today)),
        "overall_verdict": overall, "audits": audits, "stale_reruns": stale_list,
    }


# --------------------------------------------------------------- wrapper

def _safe(key: str, primary_path: Path, fn) -> dict:
    posix = _rel(primary_path)
    try:
        d = fn()
        if not isinstance(d, dict):
            raise TypeError("builder %s returned %r, not a dict" % (key, type(d)))
        d.setdefault("fresh_h", FRESH_H.get(key, 24))
        d.setdefault("path", posix)
        return d
    except Exception as e:                      # noqa: BLE001 -- a tile must never crash the page
        return {"ok": False, "path": posix, "stamp_et": None, "verdict": "off",
                "say": "NO DATA, looked for %s" % posix, "fresh_h": FRESH_H.get(key, 24),
                "error": str(e)[:200]}


def build_tiles() -> dict:
    today = et_now().strftime("%Y-%m-%d")
    return {
        "gate": _safe("gate", ANALYSIS / "go-live-gate.json", build_gate),
        "prep": _safe("prep", STATE / "premarket-readiness.json", build_prep),
        "eod": _safe("eod", ANALYSIS / "eod" / ("%s.md" % today), build_eod),
        "standup": _safe("standup", STATE / "gamma-standup-latest.json", build_standup),
        "shadow": _safe("shadow", REPO / "SHADOW.md", build_shadow),
        "watchers": _safe("watchers", STATE / "watcher-summary.json", build_watchers),
        "guards": _safe("guards", STATE / "task-state-guard.json", build_guards),
        "tasks": _safe("tasks", STATE / "SCHEDULED-TASKS.md", build_tasks),
        "gym": _safe("gym", _find_gym_path(today)[0], build_gym),
    }


if __name__ == "__main__":
    json.dump(build_tiles(), sys.stdout, indent=2, default=str)
