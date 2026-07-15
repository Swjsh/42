"""firm_brief.py -- T9 (HANDOFF-2026-07-09-TRUTH-AND-EXITS, WS4 SHRINK): ONE page = the firm.

J's complaint: "the project is so big I can't grasp it." This writes ONE glanceable daily
brief -- automation/state/firm-brief.md -- so "how's the firm" is answerable top-to-bottom
in under 30 seconds. Four sections, each sourced from an existing keystone instrument (no
new computation, no decision-ledger reads per ground rule 2):

  1. Engine P&L for the last 2 trading days present in T1's pnl-statement.json
     (automation/state/pnl-statement.json, broker-truth -- broker_fills.py).
  2. One line per CONSOLIDATED engine trade for the most recent of those days. Fleet arms
     place the SAME signal across up to 4 accounts within the same second (confirmed 07-08:
     safe-1/safe-3/risky-1/risky-3 all filled 741P ~$0.97 at 09:52) -- FIFO round-trips are
     keyed per (arm, symbol), so one fleet-wide trade event produces up to 4 near-duplicate
     rows in pnl-statement.json's `round_trips`. This groups by (symbol, entry-minute) so
     each brief line is one trade EVENT, matching how a human (and the HANDOFF itself) talks
     about "the 09:52 741P trade" -- not one broker fill-pair per account. Capped at 12 lines.
  3. Max 3 items blocked on J: a curated top-3 (by $/risk impact) from the HANDOFF's
     J-DECISIONS list (6 total; the other 3 are noted, not dropped), PLUS a live grep of
     automation/overnight/queue.md for any "J:" / "[J:" marker (so a future ask surfaces
     automatically instead of going stale in a hardcoded list).
  4. One system-health word (GREEN/YELLOW/RED). DESIGN CHOICE: reads the CACHED verdict at
     automation/state/self-check-last.json (written every ~30 min by Gamma_SelfCheck) rather
     than importing and calling self_check.run() directly -- run() makes live Alpaca account
     pings, reads several state files, writes STATUS.md, and can queue its own Discord alert;
     none of that is "lightest-weight" or appropriate to trigger from a brief-writer. Reading
     the cached JSON is a single stat+read with zero side effects and reflects the same
     verdict self_check already maintains. Mapping: GREEN->GREEN, DEGRADED->YELLOW,
     BROKEN->RED, missing/unreadable->YELLOW (unknown is never treated as green).

Also appends ONE Discord ping (with J's <@id> mention token -- the T3 fix this session found:
pings without the mention never push to phone) pointing at the brief. Fail-open per section:
a missing/unreadable source degrades that section's text, never crashes the whole brief.
$0, pure stdlib, no network.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "firm-brief.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "firm-brief.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from et_clock import et_now  # noqa: E402
from trade_today_watcher import _load_user_mention  # noqa: E402  (T3 mention-token pattern, reused not re-implemented)

STATE = REPO / "automation" / "state"
STATEMENT = STATE / "pnl-statement.json"
SELF_CHECK_LAST = STATE / "self-check-last.json"
QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"
OUTBOX = STATE / "discord-outbox.jsonl"
BRIEF_MD = STATE / "firm-brief.md"
HANDOFF_NAME = "markdown/planning/HANDOFF-2026-07-09-TRUTH-AND-EXITS.md"

MAX_TRADE_LINES = 12

# Curated top-3 of the HANDOFF's 6 J-DECISIONS, ranked by $/risk impact (editorial call made
# at authoring time per T9's instructions -- not re-derived at runtime). The other 3
# (D5 min-1-contract Rule-6 amendment, D6 EOD-flatten backstop activation, "which Discord
# channel does J watch" for T3) are named in the "+N more" note below, not dropped.
J_DECISIONS_TOP3 = [
    "Account split -- J's manual safe-2 trading burns the core's PDT budget (blocked its only "
    "valid 07-08 entry) + contaminates engine-vs-manual measurement. [J: yes/no + which account]",
    "D-SIP $99/mo Algo Trader Plus -- unlocks REAL volume (free IEX undercounts ~28x; J's "
    "volume-shelf reads need this). [J: yes/no]",
    "D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: yes, strengthened).",
]
J_DECISIONS_MORE_NOTE = f"+3 more in {HANDOFF_NAME} (D5 min-1-contract Rule-6 amendment, D6 EOD-flatten backstop activation, which Discord channel J watches)"


def load_json(path: Path) -> dict:
    """Fail-open JSON load -- missing/corrupt source degrades that section, never raises."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def pick_last_days(per_day: dict, n: int = 2) -> list:
    """Last n date_et keys present in per_day, oldest-first. ISO date strings sort correctly."""
    return sorted(per_day.keys())[-n:]


def day_engine_pnl(statement: dict, date: str) -> float:
    """Sum engine_pnl across every arm's per_day entry for `date`. Source = T1 per_day, per
    T9's instructions -- the section-2 trade list independently derives the same total from
    round_trips, so the two numbers cross-check by construction (build_statement() writes both
    from the same fifo_round_trips() pass)."""
    day = (statement.get("per_day") or {}).get(date, {})
    return round(sum(float(a.get("engine_pnl", 0.0)) for a in day.values()), 2)


def short_symbol(occ: str) -> str:
    """OCC option symbol -> compact 'STRIKE+RIGHT' (SPY260708P00741000 -> '741P'). Any
    non-OCC symbol (shouldn't occur for attribution=='engine' -- crypto is always manual
    per broker_fills.py) falls back to the raw string, never raises."""
    try:
        right = occ[-9]
        strike = int(occ[-8:]) / 1000.0
        if right not in ("C", "P"):
            raise ValueError
        strike_s = f"{strike:.0f}" if strike == int(strike) else f"{strike:g}"
        return f"{strike_s}{right}"
    except Exception:  # noqa: BLE001
        return occ


def group_engine_trades(round_trips: list, date: str) -> list:
    """PURE: consolidate engine round-trips for `date` by (symbol, entry-minute) into one
    trade-event per group -- see module docstring point 2 for why (fleet arms fill the same
    signal near-simultaneously across up to 4 accounts). qty-weighted avg entry/exit price,
    summed qty + pnl, sorted by entry time."""
    groups: dict = {}
    for rt in round_trips:
        if rt.get("date_et") != date or rt.get("attribution") != "engine":
            continue
        entry_ts = rt.get("entry_ts_et", "")
        exit_ts = rt.get("exit_ts_et", "")
        key = (rt.get("symbol"), entry_ts[:16])  # minute precision
        qty = float(rt.get("qty") or 0)
        g = groups.setdefault(key, {
            "symbol": rt.get("symbol"), "entry_ts": entry_ts, "exit_ts": exit_ts,
            "qty": 0.0, "pnl": 0.0, "w_entry": 0.0, "w_exit": 0.0, "arms": set(),
        })
        g["qty"] += qty
        g["pnl"] += float(rt.get("pnl") or 0)
        g["w_entry"] += float(rt.get("entry_price") or 0) * qty
        g["w_exit"] += float(rt.get("exit_price") or 0) * qty
        if rt.get("arm"):
            g["arms"].add(rt["arm"])
        if entry_ts and entry_ts < g["entry_ts"]:
            g["entry_ts"] = entry_ts
        if exit_ts and exit_ts > g["exit_ts"]:
            g["exit_ts"] = exit_ts

    out = []
    for g in groups.values():
        qty = g["qty"]
        entry_avg = (g["w_entry"] / qty) if qty else 0.0
        exit_avg = (g["w_exit"] / qty) if qty else 0.0
        out.append({
            "symbol": g["symbol"], "entry_ts": g["entry_ts"], "exit_ts": g["exit_ts"],
            "qty": qty, "pnl": round(g["pnl"], 2),
            "entry_price": round(entry_avg, 4), "exit_price": round(exit_avg, 4),
            "n_arms": len(g["arms"]),
        })
    out.sort(key=lambda x: x["entry_ts"])
    return out


def verdict_label(trade: dict) -> str:
    """Heuristic WIN/LOSS/FLAT + a rough 'why' bucket from % premium move. NOT a substitute
    for T5/T6's real shape-provenance study -- this is a one-glance label only."""
    entry, exit_, pnl = trade["entry_price"], trade["exit_price"], trade["pnl"]
    pct = ((exit_ - entry) / entry * 100.0) if entry else 0.0
    if pnl > 0:
        verdict, why = "WIN", ("runner/trail" if pct >= 50 else "TP hit")
    elif pnl < 0:
        verdict, why = "LOSS", ("catastrophe stop" if pct <= -45 else "stopped early")
    else:
        verdict, why = "FLAT", "scratch"
    return f"{verdict} ({why}, {pct:+.0f}%)"


def _fmt_qty(q: float) -> str:
    return f"{q:.0f}" if float(q).is_integer() else f"{q:g}"


def _fmt_money(x: float) -> str:
    """+$150.00 / -$382.00 -- sign BEFORE the dollar sign (not Python's default '$-382.00')."""
    return f"{'+' if x >= 0 else '-'}${abs(x):.2f}"


def format_trade_line(t: dict) -> str:
    entry_hm = (t["entry_ts"][11:16] if len(t["entry_ts"]) >= 16 else t["entry_ts"])
    exit_hm = (t["exit_ts"][11:16] if len(t["exit_ts"]) >= 16 else t["exit_ts"])
    sym = short_symbol(t["symbol"])
    arms = f"{t['n_arms']} arms" if t["n_arms"] != 1 else "1 arm"
    return (f"- {entry_hm}->{exit_hm} {sym} x{_fmt_qty(t['qty'])} ({arms}) "
            f"${t['entry_price']:.2f}->${t['exit_price']:.2f}  "
            f"{_fmt_money(t['pnl'])}  {verdict_label(t)}")


def autopsy_staleness_note(autopsy_date: "str | None", now_et) -> "str | None":
    """PURE: a loud one-liner when the last autopsy is OLDER than the most recent weekday
    session that should have one (fire time 16:15 ET, checked with a 16:30 grace). None when
    fresh / before the first expected fire. This is the standing instrument that catches a
    dark Gamma_TradeAutopsy clock-trigger without anyone remembering to check (OP-33b/e)."""
    import datetime as _dt
    if autopsy_date is None:
        return None  # the "no autopsy yet" line below covers the never-ran case
    d = now_et.date()
    # most recent weekday whose 16:30 ET has passed
    if d.weekday() >= 5:                      # Sat/Sun -> Friday
        expected = d - _dt.timedelta(days=d.weekday() - 4)
    elif now_et.time() >= _dt.time(16, 30):
        expected = d
    else:                                     # before today's fire -> previous weekday
        expected = d - _dt.timedelta(days=1)
        while expected.weekday() >= 5:
            expected -= _dt.timedelta(days=1)
    try:
        have = _dt.date.fromisoformat(str(autopsy_date))
    except ValueError:
        return f"- ⚠ STALE: unparseable autopsy date {autopsy_date!r} -- check Gamma_TradeAutopsy."
    if have < expected:
        return (f"- ⚠ STALE: last autopsy is {have} but {expected} should exist by now -- "
                f"Gamma_TradeAutopsy (16:15 ET) may not be firing; check "
                f"Get-ScheduledTaskInfo Gamma_TradeAutopsy.")
    return None


def render_health(self_check: dict) -> "tuple[str, str]":
    """(one-word verdict, one-line detail). Missing/unreadable cache -> YELLOW (never GREEN
    on unknown state)."""
    if not self_check:
        return "YELLOW", "self-check-last.json missing or unreadable -- Gamma_SelfCheck may not be firing."
    raw = str(self_check.get("verdict", "")).upper()
    mapped = {"GREEN": "GREEN", "DEGRADED": "YELLOW", "BROKEN": "RED"}.get(raw, "YELLOW")
    problems = self_check.get("problems") or []
    ts = self_check.get("ts_et", "?")
    if not problems:
        detail = f"self-check {raw or 'UNKNOWN'} @ {ts} -- no problems flagged."
    else:
        first = str(problems[0])
        if len(first) > 160:
            first = first[:157] + "..."
        more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
        detail = f"self-check {raw} @ {ts} -- {first}{more}"
    return mapped, detail


def render_pdt_lines(self_check: dict) -> list[str]:
    """PURE: render the per-account PDT/settlement (Rule 7) status line(s) from
    self_check's cached 'pdt' summary (self-check-last.json's "pdt" key, written by
    self_check.check_pdt_status every ~30 min, 2026-07-14). The 2026-07-13 scar (core
    Safe silently PDT-blocked ALL DAY on a day-trade count it INHERITED from an account
    repoint [commit 61cfca0], found by a manual review, not an instrument --
    analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2) is why this exists: a BLOCKED
    account renders LOUD here, it never quietly blends into an otherwise-green brief.

    2026-07-15: check_pdt_status now branches per account on params.pdt_gate_mode --
    "cash_settlement" entries (both core accounts, params.json) carry
    "gate_mode": "cash_settlement" and a settlement-ledger shape (entries_used_today /
    max_same_day_roundtrips / settled_cash_remaining / sod_settled_cash) instead of the
    margin-PDT shape (day_trades_used_5d / limit / remaining / rolloff_date) -- rendered
    distinctly below so a cash account never prints a fabricated "None/None day-trades
    used" line. margin_pdt entries (fleet arms, or a reverted account) render exactly as
    before -- zero change to that branch.

    Missing/empty data (self_check hasn't reported PDT status yet, or the fetch failed
    for an account) renders an honest UNKNOWN line -- NEVER fabricates a count (OP-33).
    Fixed account order (safe then bold), not dict-iteration-order-dependent. Guard:
    test_firm_brief_pdt_section.py."""
    pdt = (self_check or {}).get("pdt") or {}
    if not pdt:
        return ["- UNKNOWN (self-check has not reported PDT status yet -- Gamma_SelfCheck fires ~every 30 min)."]
    lines: list[str] = []
    for label, name in (("safe", "core Safe"), ("bold", "core Bold")):
        a = pdt.get(label)
        if not a:
            lines.append(f"- {name}: UNKNOWN (no PDT reading this cycle).")
            continue
        status = a.get("status")
        if status == "UNKNOWN":
            lines.append(f"- {name}: UNKNOWN ({a.get('reason', 'fetch failed')}).")
            continue
        if a.get("gate_mode") == "cash_settlement":
            entries = a.get("entries_used_today")
            cap = a.get("max_same_day_roundtrips")
            remaining = a.get("settled_cash_remaining")
            sod = a.get("sod_settled_cash")
            remaining_s = f"${remaining:,.2f}" if remaining is not None else "?"
            sod_s = f"${sod:,.2f}" if sod is not None else "?"
            if status == "BLOCKED":
                lines.append(f"- {name}: SETTLEMENT-BLOCKED (cash_settlement) -- {entries}/{cap} "
                             f"same-day entries used, {remaining_s} settled cash remaining of "
                             f"{sod_s} SOD.")
            else:
                lines.append(f"- {name}: {entries}/{cap} same-day entries used (cash_settlement), "
                             f"{remaining_s} settled cash remaining of {sod_s} SOD.")
            continue
        used = a.get("day_trades_used_5d")
        limit = a.get("limit")
        roll = a.get("rolloff_date") or "n/a"
        if status == "NOT_APPLICABLE":
            eq = a.get("equity")
            eq_s = f"${eq:,.2f}" if eq is not None else "?"
            lines.append(f"- {name}: PDT N/A (equity {eq_s} >= $25K threshold).")
        elif status == "BLOCKED":
            lines.append(f"- {name}: BLOCKED -- {used}/{limit} day-trades used (rolling 5bd), "
                         f"0 remaining, rolls off {roll}.")
        else:
            remaining = a.get("remaining")
            roll_s = f", next rolls off {roll}" if used else ""
            lines.append(f"- {name}: {used}/{limit} day-trades used, {remaining} remaining{roll_s}.")
    return lines


def find_queue_j_markers(path: Path) -> list:
    """Live grep of queue.md for explicit 'J:' / '[J:' markers (fail-open -> [])."""
    out = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "J:" in line or "[J:" in line:
                out.append(line.strip()[:160])
    except Exception:  # noqa: BLE001
        pass
    return out


def _format_coverage_suffix(coverage_data: dict, gauntlet_data: Optional[dict]) -> str:
    """PURE: renders the path-coverage scoreboard + last gauntlet result as a
    suffix for the TWIN line -- e.g. "coverage: 5/6 branches green today, 1
    incident(s), gauntlet: PASS 20:41." Fail-open: missing/empty coverage_data
    renders an honest "no path-coverage data yet" note rather than fabricating
    numbers (a scenario scheduler that hasn't shipped yet must never LOOK green).
    Schema (fixed 2026-07-11, three independent crews converged on the same
    finding): automation/state/crypto-twin/path-coverage.json's REAL producer
    (crypto_twin_scenarios.py's BRANCH_REGISTRY + crypto_twin_health.py's
    summarize_path_coverage(), confirmed by twin_sentinel.py's
    parse_path_coverage()) writes {"branches": {NAME: {"status":
    "PENDING"|"IN_PROGRESS"|"NOT_YET_COVERED"|"GREEN"|"INCIDENT", ...}}} --
    NOT the {"paths": {...: {"status": "green"}}} shape this function was
    originally built against (a guess made before the real producer shipped),
    which meant `paths` was always empty and coverage silently never rendered
    even once real data existed."""
    branches = (coverage_data or {}).get("branches") or {}
    if not branches:
        cov_s = "coverage: no path-coverage data yet"
    else:
        total = len(branches)
        green = sum(1 for b in branches.values() if isinstance(b, dict) and b.get("status") == "GREEN")
        incidents = sum(1 for b in branches.values() if isinstance(b, dict) and b.get("status") == "INCIDENT")
        cov_s = f"coverage: {green}/{total} branches green today, {incidents} incident(s)"
    gauntlet_s = ""
    if gauntlet_data:
        overall = gauntlet_data.get("overall", "?")
        ts = str(gauntlet_data.get("ts_et", "?"))
        time_s = ts[11:16] if len(ts) >= 16 else ts   # HH:MM out of an ISO timestamp
        gauntlet_s = f", gauntlet: {overall} {time_s}"
    return f"| {cov_s}{gauntlet_s}."


def render_twin_lines(health_data: dict, coverage_data: Optional[dict] = None,
                      gauntlet_data: Optional[dict] = None) -> list[str]:
    """PURE: render the Crypto Twin (24/7 mechanism-validation training ground, J
    requirement 2026-07-10) section body from its last-tick snapshot
    (automation/state/twin-health.json, written every ~5 min by Gamma_CryptoTwin /
    crypto_twin_health.py). Mirrors render_prospector_lines' fail-open shape
    immediately below it in build_brief() -- a missing/never-fired source degrades
    this section's text only, never the rest of the brief. Deliberately does NOT
    report the twin's P&L (markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md's kill
    criteria: "never appears in any edge scorecard" -- this is a MECHANISM-HEALTH
    glance, not a trading result). Guard: test_firm_brief_twin_section.py.

    B2c EXTENSION: `coverage_data` (path-coverage.json) and `gauntlet_data`
    (gauntlet-last.json) are OPTIONAL, additive, and both default to None so
    every pre-existing single-argument call site/test is byte-for-byte
    unaffected (None means "don't touch the line" -- build_brief() always
    passes an actual dict, possibly {} on a missing file, once wired below).
    When provided, they extend the SAME "- TWIN: ..." line with a path-coverage
    scoreboard, e.g. "...orders=3 lifetime. | coverage: 5/6 branches green
    today, 1 incident(s), gauntlet: PASS 20:41." -- fail-open per field."""
    if not health_data:
        return ["- no tick yet (Gamma_CryptoTwin fires every 5 min, 24/7)."]
    last_tick = health_data.get("last_tick_et", "?")
    ticks_today = health_data.get("ticks_today", 0)
    last_action = health_data.get("last_action") or "?"
    breaker = health_data.get("breaker_tripped")
    breaker_s = "TRIPPED" if breaker else ("OK" if breaker is not None else "?")
    account = health_data.get("account_status", "?")
    n_orders = health_data.get("n_orders_lifetime", 0)
    line = (f"- TWIN: last tick {last_tick} ({ticks_today} today), "
           f"last_action={last_action}, breaker={breaker_s}, account={account}, "
           f"orders={n_orders} lifetime.")
    if coverage_data is not None:
        line += " " + _format_coverage_suffix(coverage_data, gauntlet_data)
    err = health_data.get("last_error")
    if err:
        line += f" ⚠ LAST ERROR: {str(err)[:160]}"
    return [line]


def render_autopsy_lines(data: dict) -> list[str]:
    """PURE: render the "Gamma's read (trade autopsy)" section body from its last-run
    snapshot (automation/state/trade-autopsy-last.json). Mirrors render_prospector_lines'
    fail-open shape.

    THE 2026-07-14 HONESTY FIX: Monday 07-13 lost a real -$25 on risky-3, but bars were
    unavailable for that position (OPRA indexing lag), so `trade-autopsy-last.json` had
    0 replayed rows and this line used to print "0 engine positions, net +$0.00" --
    indistinguishable from a genuinely flat day (C7 silent-wrong; the .md itself already
    said INCOMPLETE, but nobody reads the .md from a one-line brief). Never again: this
    renders `P&L_UNVERIFIED/NO_BARS` -- no dollar figure claimed as the day's true P&L --
    whenever `pnl_status` says the data is incomplete. `pnl_status` is read defensively:
    pre-2026-07-14 last.json files predate the key entirely, so it's inferred from the
    same `n_no_bars`/`n_positions_found` fields that schema already had (never crashes on
    an old file). Guard: test_firm_brief_autopsy_pnl_status.py."""
    if not data:
        return ["- no autopsy yet (Gamma_TradeAutopsy fires 16:15 ET)."]
    if data.get("error"):
        return [f"- {data.get('date', '?')}: autopsy FAILED ({str(data['error'])[:100]}) -- fix me."]
    status = data.get("pnl_status")
    if status is None:  # legacy file written before the pnl_status key existed
        if data.get("n_no_bars", 0) > 0:
            status = "unverified_no_bars"
        elif not data.get("n_positions_found"):
            status = "flat"
        else:
            status = "verified"
    md_path = data.get("md", "analysis/autopsies/")
    if status == "unverified_no_bars":
        n_found = data.get("n_positions_found", 0)
        n_no_bars = data.get("n_no_bars", 0)
        partial = data.get("net_pnl_known_partial")
        partial_s = (f"; {_fmt_money(float(partial))} known from {data.get('n_positions', 0)} "
                     f"replayed" if partial is not None else "")
        return [f"- {data.get('date', '?')}: P&L_UNVERIFIED/NO_BARS -- {n_found} closed engine "
                f"position(s) found, bars unavailable for {n_no_bars}{partial_s} "
                f"(NOT a flat day -- re-run trade_autopsy.py --date {data.get('date', '?')}) "
                f"({md_path})"]
    hyp = data.get("new_hypotheses") or []
    hyp_s = f"; NEW hypotheses: {', '.join(hyp)}" if hyp else "; no new hypotheses"
    net_pnl = data.get("net_pnl")
    net_pnl = 0.0 if net_pnl is None else float(net_pnl)  # legacy-file belt-and-suspenders
    return [f"- {data.get('date', '?')}: {data.get('n_positions', 0)} engine positions, "
            f"net {_fmt_money(net_pnl)}, "
            f"{data.get('n_stopped_then_paid', 0)} stopped-then-paid{hyp_s} ({md_path})"]


def render_prospector_lines(data: dict) -> list[str]:
    """PURE: render the Prospector (exogenous-idea organ, J 2026-07-09: "gamma
    hasn't introduced a single new idea like this at all yet") section body
    from its last-run snapshot (automation/state/prospector-last.json). Mirrors
    the trade-autopsy section's fail-open shape immediately below it in
    build_brief() -- a missing/errored/never-run source degrades this section's
    text only, never the rest of the brief. Guard: test_firm_brief_prospector_section.py."""
    if not data:
        return ["- no scan yet (Gamma_Prospector fires 21:30 ET nightly)."]
    if data.get("error"):
        return [f"- {data.get('date', '?')}: scan FAILED ({str(data['error'])[:100]}) -- fix me."]
    beat = data.get("beat", "?")
    n_new = data.get("n_new_ideas", 0)
    n_total = data.get("n_total_ideas", 0)
    promo = data.get("promoted_idea")
    promo_s = f"; promoted `{promo}` -> _chef-inbox" if promo else ""
    lane_s = "" if data.get("scan_ok", True) else " (no free lane up that night -- skip-with-log)"
    return [f"- {data.get('date', '?')} (beat `{beat}`): {n_new} new idea(s), "
            f"{n_total} total in ledger{promo_s}{lane_s} "
            f"(analysis/prospector/ideas-ledger.jsonl)."]


def render_futures_shadow_lines(data: dict) -> list[str]:
    """PURE: render the FUTURES-MIRROR-SHADOW (7th-arm forward-evidence lane, 2026-07-14 J
    directive 'make sure you trade futures today too') section body from its last-computed
    snapshot (automation/state/futures/shadow-progress.json, written by
    setup/scripts/futures_shadow_progress.py -- piggybacks on Gamma_FuturesMirror's existing
    5-min-RTH + 16:05-sweep poll, no new scheduled task). Mirrors render_prospector_lines'
    fail-open shape immediately above it in build_brief() -- a missing/never-fired source
    degrades this section's text only, never the rest of the brief. Places no order, arms
    nothing -- this is a progress GLANCE, matching render_twin_lines' P&L-free posture for the
    same reason (a shadow lane's job is mechanism/evidence, not a tradeable result yet).
    Guard: test_firm_brief_futures_shadow_section.py."""
    if not data:
        return ["- no shadow-progress.json yet (Gamma_FuturesMirror fires every 5 min, "
                "09:30-16:05 ET weekdays -- first poll of the day writes it)."]
    n = data.get("n_round_trips", 0)
    total = data.get("total_pnl_usd", 0.0)
    bar = data.get("arming_bar") or {}
    needed = bar.get("round_trips_needed", 20)
    armable = bar.get("armable")
    updated = data.get("updated_et", "?")
    if n < needed:
        bar_s = f"{n}/{needed} round trips toward the arming bar"
    else:
        exp_s = "positive" if bar.get("expectancy_positive") else "negative"
        null_s = {True: "beats", False: "does NOT beat", None: "null unevaluated vs"}[bar.get("beats_null")]
        bar_s = (f"{n}/{needed} round trips, expectancy {exp_s}, {null_s} buy-hold null "
                f"-- armable={armable}")
    return [f"- FUTURES SHADOW (MES mirror): {bar_s}, total {_fmt_money(float(total))} "
           f"@ {updated}."]


def build_brief(statement: dict, self_check: dict, queue_j_items: list, now_et) -> str:
    per_day = statement.get("per_day") or {}
    round_trips = statement.get("round_trips") or []
    last_days = pick_last_days(per_day, 2)

    lines = [f"# Firm Brief -- {now_et.strftime('%Y-%m-%d')} (generated {now_et.strftime('%Y-%m-%d %H:%M ET')})", ""]

    lines.append("## Engine P&L (broker-truth, T1 pnl-statement.json)")
    if not last_days:
        lines.append("- no trading days found in pnl-statement.json yet.")
    else:
        for i, d in enumerate(last_days):
            pnl = day_engine_pnl(statement, d)
            trades = group_engine_trades(round_trips, d)
            wins = sum(1 for t in trades if t["pnl"] > 0)
            losses = sum(1 for t in trades if t["pnl"] < 0)
            tag = "latest" if i == len(last_days) - 1 else ""
            tag_s = f" ({tag})" if tag else ""
            lines.append(f"- {d}{tag_s}: {_fmt_money(pnl)} across "
                         f"{len(trades)} trade(s) ({wins}W / {losses}L)")
    lines.append("")

    latest = last_days[-1] if last_days else None
    lines.append(f"## Today's engine trades ({latest})" if latest else "## Today's engine trades")
    if latest:
        trades = group_engine_trades(round_trips, latest)
        if not trades:
            lines.append("- no engine round trips closed yet today.")
        else:
            shown = trades[:MAX_TRADE_LINES]
            for t in shown:
                lines.append(format_trade_line(t))
            if len(trades) > MAX_TRADE_LINES:
                lines.append(f"- ... +{len(trades) - MAX_TRADE_LINES} more (see pnl-statement.json round_trips)")
    else:
        lines.append("- no data yet.")
    lines.append("")

    lines.append(f"## Blocked on J (top 3; {J_DECISIONS_MORE_NOTE})")
    for i, item in enumerate(J_DECISIONS_TOP3, 1):
        lines.append(f"{i}. {item}")
    if queue_j_items:
        lines.append(f"- queue.md J-flagged: {'; '.join(queue_j_items[:3])}" +
                     (f" (+{len(queue_j_items) - 3} more)" if len(queue_j_items) > 3 else ""))
    else:
        lines.append("- queue.md: no additional J: markers found.")
    lines.append("")

    health_word, health_detail = render_health(self_check)
    lines.append(f"## System health: {health_word}")
    lines.append(f"- {health_detail}")
    lines.append("")

    # PDT (Rule 7) per-account visibility -- the 2026-07-13 scar: core Safe was silently
    # PDT-blocked all day on an INHERITED day-trade count from an account repoint, and
    # nobody knew until a manual review found it. Sourced from self_check's cached
    # 'pdt' summary (self-check-last.json, written by check_pdt_status ~every 30 min) --
    # same no-live-network-call design as render_health above.
    lines.append("## PDT status (Rule 7 -- per-account day-trades used)")
    lines.extend(render_pdt_lines(self_check))
    lines.append("")

    # Gamma's own read of its trades (trade_autopsy.py, Gamma_TradeAutopsy 16:15 ET) -- the
    # hypothesis organ J asked for 2026-07-08 ("why doesn't Gamma think 'maybe we're stopping
    # out too early'"). One line; full report in analysis/autopsies/. Fail-open. A MISSED FIRE
    # is rendered LOUDLY (OP-33b: registered != firing; the clock trigger is only provable by
    # its own fires, so the brief -- not anyone's memory -- carries the staleness tell).
    autopsy = load_json(STATE / "trade-autopsy-last.json")
    lines.append("## Gamma's read (trade autopsy)")
    stale_note = autopsy_staleness_note(autopsy.get("date"), now_et)
    if stale_note:
        lines.append(stale_note)
    lines.extend(render_autopsy_lines(autopsy))
    lines.append("")

    # Prospector -- the exogenous-idea organ (J 2026-07-09: "gamma hasn't introduced a single
    # new idea like this at all yet"). One line; full ledger in
    # analysis/prospector/ideas-ledger.jsonl, promotions land in strategy/candidates/_chef-inbox/.
    # Fail-open, same shape as the trade-autopsy section above.
    prospector = load_json(STATE / "prospector-last.json")
    lines.append("## Prospector (exogenous ideas)")
    lines.extend(render_prospector_lines(prospector))
    lines.append("")

    # Crypto Twin -- the 24/7 mechanism-validation training ground (J requirement
    # 2026-07-10, markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md). One line; full
    # ledger in automation/state/crypto-twin/decisions.jsonl. Fail-open, same shape
    # as the trade-autopsy/prospector sections above. B2c: the line is extended with
    # the twin_gauntlet.py path-coverage scoreboard (path-coverage.json) + the last
    # gauntlet run's result (gauntlet-last.json) -- both fail-open ({} on missing file).
    twin_health = load_json(STATE / "twin-health.json")
    twin_coverage = load_json(STATE / "crypto-twin" / "path-coverage.json")
    twin_gauntlet = load_json(STATE / "crypto-twin" / "gauntlet-last.json")
    lines.append("## Crypto Twin (24/7 mechanism validation)")
    lines.extend(render_twin_lines(twin_health, twin_coverage, twin_gauntlet))
    lines.append("")

    # Futures Shadow -- the MES 7th-arm forward-evidence mirror (2026-07-14 J directive "make
    # sure you trade futures today too"; queue.md FUTURES-MIRROR-SHADOW). One line; full
    # ledger in automation/state/futures/mirror-would-be.jsonl. Fail-open, same shape as the
    # prospector/twin sections above.
    futures_shadow = load_json(STATE / "futures" / "shadow-progress.json")
    lines.append("## Futures Shadow (MES mirror, 7th-arm forward evidence)")
    lines.extend(render_futures_shadow_lines(futures_shadow))
    lines.append("")

    lines.append("---")
    lines.append(f"Sources: pnl-statement.json (T1 broker-truth) | self-check-last.json | "
                 f"prospector-last.json | twin-health.json | crypto-twin/path-coverage.json | "
                 f"crypto-twin/gauntlet-last.json | futures/shadow-progress.json | "
                 f"{HANDOFF_NAME}")
    return "\n".join(lines) + "\n"


def queue_discord_ping(brief_text: str, health_word: str, latest_day: Optional[str], latest_pnl: Optional[float]) -> None:
    mention = _load_user_mention()
    pnl_s = _fmt_money(latest_pnl) if latest_pnl is not None else "n/a"
    day_s = latest_day or "n/a"
    msg = (f"{mention}[BRIEF] Firm status {day_s}: engine P&L {pnl_s}, health {health_word}. "
           f"Full brief: automation/state/firm-brief.md")
    row = {"content": msg, "source": "firm_brief", "queued_at": et_now().isoformat()}
    try:
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as e:
        print(f"[firm_brief] WARN: could not queue Discord ping: {e}", file=sys.stderr)


def regenerate_engine_contract() -> None:
    """Fold T1's engine-contract card regeneration into the firm-brief fire (no new task).
    Fail-open: a broken card generator degrades to a warning, never crashes the brief."""
    try:
        import engine_contract  # same dir (setup/scripts), pure stdlib
        path = engine_contract.write_engine_contract()
        print(f"[firm_brief] regenerated engine-contract card: {path}")
    except Exception as e:  # noqa: BLE001
        print(f"[firm_brief] WARN: engine-contract regeneration failed: {e}", file=sys.stderr)


def main() -> int:
    now_et = et_now()
    regenerate_engine_contract()
    # Rule 8: catch trades.csv up from broker-truth BEFORE rendering the brief, so the
    # journal J reads is never behind the cockpit (fleet_journal_bridge is idempotent;
    # fail-open -- a journaling error must never block the brief).
    try:
        from fleet_journal_bridge import run_bridge
        run_bridge()
    except Exception as e:  # noqa: BLE001
        print(f"[firm_brief] WARN: fleet journal bridge failed: {e}", file=sys.stderr)
    statement = load_json(STATEMENT)
    self_check = load_json(SELF_CHECK_LAST)
    queue_j_items = find_queue_j_markers(QUEUE_MD)

    brief_text = build_brief(statement, self_check, queue_j_items, now_et)
    BRIEF_MD.write_text(brief_text, encoding="utf-8")

    per_day = statement.get("per_day") or {}
    last_days = pick_last_days(per_day, 2)
    latest_day = last_days[-1] if last_days else None
    latest_pnl = day_engine_pnl(statement, latest_day) if latest_day else None
    health_word, _ = render_health(self_check)
    queue_discord_ping(brief_text, health_word, latest_day, latest_pnl)

    print(f"[firm_brief] wrote {BRIEF_MD} ({len(brief_text.splitlines())} lines); "
          f"health={health_word}; latest_day={latest_day} pnl={latest_pnl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
