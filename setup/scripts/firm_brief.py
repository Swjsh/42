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

    # Gamma's own read of its trades (trade_autopsy.py, Gamma_TradeAutopsy 16:15 ET) -- the
    # hypothesis organ J asked for 2026-07-08 ("why doesn't Gamma think 'maybe we're stopping
    # out too early'"). One line; full report in analysis/autopsies/. Fail-open.
    autopsy = load_json(STATE / "trade-autopsy-last.json")
    lines.append("## Gamma's read (trade autopsy)")
    if not autopsy:
        lines.append("- no autopsy yet (Gamma_TradeAutopsy fires 16:15 ET).")
    elif autopsy.get("error"):
        lines.append(f"- {autopsy.get('date', '?')}: autopsy FAILED ({autopsy['error'][:100]}) -- fix me.")
    else:
        hyp = autopsy.get("new_hypotheses") or []
        hyp_s = f"; NEW hypotheses: {', '.join(hyp)}" if hyp else "; no new hypotheses"
        lines.append(f"- {autopsy.get('date', '?')}: {autopsy.get('n_positions', 0)} engine positions, "
                     f"net {_fmt_money(float(autopsy.get('net_pnl', 0)))}, "
                     f"{autopsy.get('n_stopped_then_paid', 0)} stopped-then-paid{hyp_s} "
                     f"({autopsy.get('md', 'analysis/autopsies/')})")
    lines.append("")

    lines.append("---")
    lines.append(f"Sources: pnl-statement.json (T1 broker-truth) | self-check-last.json | {HANDOFF_NAME}")
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
