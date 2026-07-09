"""gamma_glance.py -- the 2-minute one-screen REAL-state glance J asked for (OP-33c).

J 2026-06-30: the engine took 0 trades; an audit found the rig has NEVER filled a real
trade, yet self-check read GREEN for hours because every check was liveness-only. The
disease: a wrapper exits 0 / a test goes green while the actual money path is dead.

This is the human's antidote: a $0 read-only dashboard that prints the VERIFIED truth
J can glance at ANYTIME, independent of any GREEN word. Every line is a fact re-derived
from a state file J can open himself. It NEVER places an order, NEVER arms, NEVER writes
state (pure read) -- so it is safe to run during market hours.

Reads only:
  - et_clock                                  -> ET time + market open/closed
  - automation/state/self-check-last.json     -> self-check verdict + problems
  - automation/state/core-decisions.jsonl     -> ENGINE TODAY (entries, dominant SKIP, age)
  - automation/state/fleet/<arm>/decisions.jsonl -> FUNNEL (via fill_funnel.py; exit_pass = fill truth)
  - automation/state/*current-position*.json  -> filled / flat detection
  - automation/state/key-levels.json          -> level integrity (via self_check)
  - automation/state/today-bias.json          -> premarket bias freshness
  - automation/state/news.json                -> news freshness (days)
  - automation/state/fleet/accounts.json      -> ARMS live/flat

Run:  backtest/.venv/Scripts/python.exe setup/scripts/gamma_glance.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:  # fail-open ET fallback (rig is on Mountain; ET=local+2)
        return dt.datetime.utcnow() - dt.timedelta(hours=4)

GREEN = "[GREEN]"
RED = "[RED]"
GRAY = "[ ?  ]"


def _j(p: Path):
    """Read JSON, fail-open to None."""
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def _age_min(p: Path) -> float | None:
    if not p.exists():
        return None
    return (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60.0


def _today_rows(p: Path, day: str) -> list[dict]:
    """JSONL rows whose ET timestamp starts with today's date. Fail-open -> []."""
    rows: list[dict] = []
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            ts = str(o.get("ts_et") or o.get("time_et") or o.get("ts") or "")
            # core-decisions carry full ISO ts_et; fleet rows carry HH:MM time_et only,
            # so for fleet we already filtered by the day substring on the raw line.
            if ts.startswith(day) or "ts_et" not in o:
                rows.append(o)
    except OSError:
        pass
    return rows


def _engine_today(now: dt.datetime) -> tuple[str, list[str]]:
    """ENGINE TODAY block: entries, dominant SKIP reason+count, last-decision age."""
    day = now.strftime("%Y-%m-%d")
    dec = STATE / "core-decisions.jsonl"
    rows = _today_rows(dec, day)
    # safe arm is the canonical heartbeat decision stream
    safe = [r for r in rows if r.get("account") == "safe"] or rows

    entries = [r for r in safe if str(r.get("verdict", "")).startswith("ENTER")]
    n_entries = len(entries)

    # dominant SKIP reason: prefer an explicit gate-block verdict (SKIP_*), fall back to
    # extra_signals skip_reason (the real "why nothing fired" on a HOLD-all-day session).
    skips: Counter = Counter()
    for r in safe:
        v = str(r.get("verdict", ""))
        if v.startswith("SKIP"):
            skips[v] += 1
        for sig in r.get("extra_signals", []) or []:
            sr = sig.get("skip_reason")
            if sr:
                skips[sr] += 1
    dom = skips.most_common(1)[0] if skips else (None, 0)

    last_age = _age_min(dec)
    last_str = f"{last_age:.0f}m ago" if last_age is not None else "never"

    # entries-today is the load-bearing line the guard asserts on.
    blocked = any(str(r.get("verdict", "")).startswith("SKIP") and r.get("triggers") for r in safe)
    if n_entries == 0 and (blocked or dom[1] > 0) and now.weekday() < 5:
        tag = RED
    elif n_entries > 0:
        tag = GREEN
    else:
        tag = GRAY  # nothing fired and nothing blocked (or weekend) -- not necessarily wrong

    lines = [
        f"  {tag} entries-today: {n_entries}   (ENTER_* in core-decisions, {len(safe)} ticks)",
        f"        dominant SKIP : {dom[0] or '(none)'} x{dom[1]}",
        f"        last decision : {last_str}",
    ]
    return tag, lines


def _funnel_today(now: dt.datetime) -> tuple[str, list[str]]:
    """FUNNEL block: ticks -> signals -> ENTER -> attempted -> accepted -> filled
    -> exited, per account, re-derived from the decision ledgers via fill_funnel.py
    (core-decisions.jsonl + fleet/<arm>/decisions.jsonl incl. exit_pass fill truth).
    This is the instrument that retires "is it actually trading?" (OP-33e).
    Replaces the old FILLS block, which read the dead fleet/decisions/ dir and
    reported 0 fills on 2026-07-01 while 4 fleet round trips actually happened."""
    try:
        import fill_funnel
        f = fill_funnel.compute_funnel(now.strftime("%Y-%m-%d"), now=now)
    except Exception as e:  # noqa: BLE001
        return GRAY, [f"  {GRAY} funnel: fill_funnel unavailable ({type(e).__name__}: {e})"]
    verdict = f.get("verdict", "?")
    tag = RED if verdict in ("RED", "DEGRADED") else (GREEN if verdict == "GREEN" else GRAY)
    lines = [f"  {tag} verdict: {verdict}   (ticks->sig->ENTER->attempt->accept->fill->exit)"]
    for name, a in f.get("accounts", {}).items():
        lines.append(f"        {name:<14} {a['ticks']:>4} -> {a['signals']:>3} -> {a['enter']:>2} "
                     f"-> {a['attempted']:>2} -> {a['accepted']:>2} -> {a['filled']:>2} -> {a['exited']:>2}")
    t = f.get("totals", {})
    if t:
        lines.append(f"        {'TOTAL':<14} {t['ticks']:>4} -> {t['signals']:>3} -> {t['enter']:>2} "
                     f"-> {t['attempted']:>2} -> {t['accepted']:>2} -> {t['filled']:>2} -> {t['exited']:>2}")
    for fl in f.get("flags", [])[:4]:
        lines.append(f"        ! {fl[:100]}")
    return tag, lines


def _levels() -> tuple[str, list[str]]:
    """LEVELS block: contradictory-role + duplicate count via self_check (reuse if importable)."""
    try:
        from self_check import check_level_integrity
        problems = check_level_integrity()
    except Exception as e:  # noqa: BLE001
        return GRAY, [f"  {GRAY} levels: self_check.check_level_integrity unavailable ({type(e).__name__})"]
    if problems:
        lines = [f"  {RED} levels: {p[:88]}" for p in problems]
        return RED, lines
    return GREEN, [f"  {GREEN} levels: no contradictory/duplicate roles in active feed"]


def _premarket(now: dt.datetime) -> tuple[str, list[str]]:
    """PREMARKET block: today-bias date == today? + news freshness in days."""
    day = now.strftime("%Y-%m-%d")
    tb = _j(STATE / "today-bias.json") or {}
    bias_fresh = tb.get("date") == day
    news = _j(STATE / "news.json") or {}
    as_of = str(news.get("as_of") or news.get("for_session") or "")[:10]
    news_days = None
    try:
        news_days = (now.date() - dt.date.fromisoformat(as_of)).days
    except Exception:  # noqa: BLE001
        pass

    bias_tag = GREEN if bias_fresh else RED
    news_stale = news_days is not None and news_days > 1
    news_tag = RED if news_stale else (GREEN if news_days is not None else GRAY)
    tag = RED if (not bias_fresh or news_stale) else GREEN
    lines = [
        f"  {bias_tag} today-bias date: {tb.get('date', '?')}  (today {day})",
        f"  {news_tag} news as_of    : {as_of or '?'}  ({news_days if news_days is not None else '?'} days old)",
    ]
    return tag, lines


def _structure_stop() -> list[str]:
    """EXIT MODE block (2026-07-09, OP-33c/STOP-B first-live-day): 'EXIT MODE: structure
    (SS-B) since 2026-07-09; positions open under structure: N; last structure exit:
    <ts or none>'. Pure disclosure, not a pass/fail check -- 0 open + 'none' is the HONEST,
    EXPECTED reading before the first real structure-mode fill ever lands, so this NEVER
    tags RED on its own. ASCII-only (no unicode dashes/arrows) -- this string round-trips
    through a Windows PS 5.1 console (see test_gamma_glance_guard.py's ascii guard)."""
    fa = _j(STATE / "fleet" / "accounts.json") or {}
    arms = [a["id"] for a in (fa.get("arms") or [])
           if a.get("instrument") == "SPY_0DTE_OPTION"]
    n_structure = 0
    for arm_id in arms:
        est = _j(STATE / "fleet" / arm_id / "exit-state.json") or {}
        for pos in est.values():
            if isinstance(pos, dict) and pos.get("stop_mode") == "structure":
                n_structure += 1
    last_ts, last_sym = None, None
    paths = [STATE / "core-decisions.jsonl"] + [STATE / "fleet" / a / "decisions.jsonl" for a in arms]
    for p in paths:
        if not p.exists():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            continue
        for ln in lines[-3000:]:
            try:
                row = json.loads(ln)
            except (json.JSONDecodeError, ValueError):
                continue
            ts = row.get("ts_et")
            for ep in (row.get("exit_pass") or []):
                if not isinstance(ep, dict):
                    continue
                for act in (ep.get("actions") or []):
                    if isinstance(act, dict) and act.get("stage") == "structure_stop" \
                            and ts and (last_ts is None or ts > last_ts):
                        last_ts, last_sym = ts, ep.get("symbol")
    safe_flag = (_j(STATE / "params.json") or {}).get("structure_stop_enabled")
    bold_flag = (_j(STATE / "aggressive" / "params.json") or {}).get("structure_stop_enabled")
    flag_s = f"safe={'ON' if safe_flag else 'OFF'} bold={'ON' if bold_flag else 'OFF'}"
    last_s = f"{last_ts} {last_sym}" if last_ts else "none"
    return [
        f"  EXIT MODE: structure (SS-B) since 2026-07-09 [{flag_s}]; "
        f"positions open under structure: {n_structure}; last structure exit: {last_s}",
    ]


def _arms() -> list[str]:
    """ARMS block: which arms are live=true + flat."""
    fa = _j(STATE / "fleet" / "accounts.json") or {}
    arms = fa.get("arms", []) if isinstance(fa.get("arms"), list) else []
    live = [a.get("id") for a in arms if a.get("live") is True]
    safe_pos = (_j(STATE / "current-position-safe.json") or {}).get("status")
    bold_pos = (_j(STATE / "current-position-bold.json") or {}).get("status")
    flat = (not safe_pos) and (not bold_pos)
    return [
        f"  arms configured: {len(arms)}   live=true: {len(live)} {live or ''}",
        f"  controls flat?  : safe={'FLAT' if not safe_pos else safe_pos}  bold={'FLAT' if not bold_pos else bold_pos}"
        + ("   [GREEN]" if flat else "   [RED]"),
    ]


def build() -> str:
    now = et_now()
    hm = now.strftime("%H:%M")
    rth = ("09:30" <= hm <= "15:55") and now.weekday() < 5
    out: list[str] = []
    out.append("=" * 72)
    out.append(f" GAMMA GLANCE  {now.strftime('%Y-%m-%d %H:%M ET %a')}   MARKET {'OPEN' if rth else 'CLOSED'}")
    out.append("=" * 72)

    # self-check verdict
    sc = _j(STATE / "self-check-last.json") or {}
    v = sc.get("verdict", "?")
    sc_tag = GREEN if v == "GREEN" else (RED if v in ("BROKEN", "DEGRADED") else GRAY)
    out.append(f"\nSELF-CHECK  {sc_tag} {v}  (@ {sc.get('ts_et', '?')})")
    for p in (sc.get("problems") or [])[:4]:
        out.append(f"        - {p[:96]}")

    eng_tag, eng_lines = _engine_today(now)
    out.append("\nENGINE TODAY")
    out.extend(eng_lines)

    fill_tag, fill_lines = _funnel_today(now)
    out.append("\nFUNNEL")
    out.extend(fill_lines)

    lvl_tag, lvl_lines = _levels()
    out.append("\nLEVELS")
    out.extend(lvl_lines)

    pm_tag, pm_lines = _premarket(now)
    out.append("\nPREMARKET")
    out.extend(pm_lines)

    out.append("\nARMS")
    out.extend(_arms())

    out.append("\nEXIT MODE")
    out.extend(_structure_stop())

    # one-line bottom verdict: RED if any RED block
    any_red = RED in (sc_tag, eng_tag, fill_tag, lvl_tag, pm_tag)
    out.append("\n" + "-" * 72)
    out.append(f" OVERALL: {RED + ' attention needed' if any_red else GREEN + ' nothing screaming'}")
    out.append("=" * 72)
    return "\n".join(out)


def main() -> int:
    print(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
