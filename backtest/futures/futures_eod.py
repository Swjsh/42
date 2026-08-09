"""futures_eod.py -- the futures session review. Closes the learn loop.

WHY (the other half of journaling). Recording trades is not reviewing them. The SPY side
has an EOD digest that grades the day against the rules and feeds the next research pass;
the futures lane had a journal and no reviewer, which is how a lane accumulates rows nobody
reads and drifts without anyone noticing.

WHAT IT GRADES, and why each one is here rather than "nice to have":

  TICK COVERAGE -- did the lane actually fire every tick it was scheduled to? This is the
    headline number, deliberately. Every other metric on this page is conditional on the
    engine having been awake, and a lane that quietly stops ticking produces a PERFECT
    -looking digest: zero trades, zero errors, zero rule breaks. "No trades today" and "the
    engine was dead today" must never render identically (C7 -- audit outputs, not exit
    codes; and the crypto twin's four dark days).

  FUNNEL -- signals seen -> qualified -> entered, with the RAIL that rejected each drop.
    A lane that sees 57 signals and takes 0 is either correctly disciplined or silently
    broken, and only the rejection breakdown distinguishes those.

  ROUND TRIPS -- closed trades from the ledger, filtered to ONE fill class. Never mixed.

  RULE ADHERENCE -- every entry is checked against the rails AFTER the fact, independently
    of the pre-trade gate. A gate that is bypassed or mis-wired shows up as a post-hoc
    violation, which a pre-trade-only check can never reveal.

DISCLOSURE: the digest states its fill class on every P&L line. Simulated fills are
mechanism evidence, never edge evidence.

Read-only over state and the journal. Writes only its own digest + state file. Never
places, cancels, or modifies anything.

CLI:
    python -m futures.futures_eod                 # today's session
    python -m futures.futures_eod --date 2026-08-07
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures.futures_session import et_now, is_holiday  # noqa: E402
from futures import futures_journal as fj  # noqa: E402

STATE_DIR = REPO / "automation" / "state" / "futures" / "trader"
LEDGER = STATE_DIR / "decisions.jsonl"
DIGEST_DIR = REPO / "analysis" / "futures-eod"
STATE_OUT = REPO / "automation" / "state" / "futures" / "eod-summary.json"

# Gamma_FuturesTrader fires every 5 min across the 6.5h RTH window.
TICK_INTERVAL_MIN = 5
EXPECTED_TICKS = int(6.5 * 60 / TICK_INTERVAL_MIN)   # 78
# Below this fraction of expected ticks the lane was not meaningfully awake.
COVERAGE_RED = 0.70
COVERAGE_YELLOW = 0.90


def _read_ledger(date: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("ts_et", "")).startswith(date):
                rows.append(r)
    except OSError:
        pass
    return rows


def tick_coverage(rows: list[dict], date: str) -> dict:
    """Did the engine actually run? The metric every other metric depends on."""
    ticks = len(rows)
    pct = ticks / EXPECTED_TICKS if EXPECTED_TICKS else 0.0
    if is_holiday(dt.datetime.fromisoformat(date)):
        verdict, note = "HOLIDAY", "market holiday -- no ticks expected"
    elif dt.datetime.fromisoformat(date).weekday() > 4:
        verdict, note = "WEEKEND", "weekend -- no ticks expected"
    elif pct >= COVERAGE_YELLOW:
        verdict, note = "GREEN", "lane was awake"
    elif pct >= COVERAGE_RED:
        verdict, note = "YELLOW", "gaps in the tick record -- check the scheduler"
    elif ticks > 0:
        verdict, note = "RED", "lane was mostly dark; today's other numbers are not trustworthy"
    else:
        verdict, note = "DARK", "NO ticks at all -- the lane did not run; zero trades means nothing"
    return {"ticks": ticks, "expected": EXPECTED_TICKS, "pct": round(pct, 3),
            "verdict": verdict, "note": note}


def funnel(rows: list[dict]) -> dict:
    """signals seen -> qualified -> entered, plus WHY each drop happened."""
    seen = sum(int(r.get("n_signals") or 0) for r in rows)
    entries = [r for r in rows if r.get("action") == "ENTER"]
    rejections: Counter = Counter()
    for r in rows:
        for rej in r.get("rejected") or []:
            rejections[rej.get("rail", "?")] += 1
    actions = Counter(r.get("action", "?") for r in rows)
    feeds = Counter(r.get("freshness", "?") for r in rows)
    return {
        "signals_seen": seen,
        "entries": len(entries),
        "rejections_by_rail": dict(rejections),
        "actions": dict(actions),
        "feed_verdicts": dict(feeds),
        "exit_events": sum(len(r.get("exit_events") or []) for r in rows),
        "errors": [r.get("see_error") or r.get("exit_error")
                   for r in rows if r.get("see_error") or r.get("exit_error")],
    }


def round_trips(date: str, fills: str = "SIMULATED") -> dict:
    """Closed trades for the date, from ONE fill class only. Never mixed."""
    rows = [r for r in fj.read_trades(fills=fills) if r.get("date") == date]
    pnls = []
    for r in rows:
        try:
            pnls.append(float(r.get("dollar_pnl") or 0.0))
        except (TypeError, ValueError):
            continue
    wins = [p for p in pnls if p > 0]
    return {
        "fills": fills,
        "n": len(rows),
        "total_pnl": round(sum(pnls), 2),
        "win_rate": round(len(wins) / len(pnls), 3) if pnls else None,
        "best": round(max(pnls), 2) if pnls else None,
        "worst": round(min(pnls), 2) if pnls else None,
        "by_setup": dict(Counter(r.get("setup", "?") for r in rows)),
        "by_exit": dict(Counter(r.get("exit_reason", "?") for r in rows)),
        "rows": rows,
    }


def rule_audit(rows: list[dict], trades: dict) -> list[dict]:
    """Post-hoc rule check on every entry, INDEPENDENT of the pre-trade gate.

    Checking only at entry time cannot catch a gate that was bypassed or mis-wired --
    the same reason a winning trade that broke a rule still gets red-flagged on the SPY
    side. Process over P&L.
    """
    from futures.futures_risk_rails import FuturesRiskRails  # noqa: PLC0415

    rails = FuturesRiskRails()
    breaks: list[dict] = []
    for r in rows:
        if r.get("action") != "ENTER":
            continue
        e = r.get("entry") or {}
        qty = int(e.get("qty") or 0)
        risk = float(e.get("risk_usd") or 0.0)
        if qty > rails.max_contracts:
            breaks.append({"ts": r.get("ts_et"), "rule": "contract_cap",
                           "detail": f"qty {qty} > cap {rails.max_contracts}"})
        if risk > rails.per_trade_risk_cap:
            breaks.append({"ts": r.get("ts_et"), "rule": "per_trade_risk",
                           "detail": f"${risk:.2f} > cap ${rails.per_trade_risk_cap:.2f}"})
        if not e.get("stop"):
            breaks.append({"ts": r.get("ts_et"), "rule": "defined_stop",
                           "detail": "entry recorded with no stop -- Rule 3"})
        if r.get("freshness") != "GREEN":
            breaks.append({"ts": r.get("ts_et"), "rule": "data_freshness",
                           "detail": f"entered on a {r.get('freshness')} feed"})
    day_pnl = trades.get("total_pnl") or 0.0
    if -day_pnl >= rails.session_loss_cap:
        breaks.append({"ts": "session", "rule": "session_loss_cap",
                       "detail": f"session P&L ${day_pnl:.2f} reached the "
                                 f"${rails.session_loss_cap:.2f} cap"})
    return breaks


def build(date: Optional[str] = None, fills: str = "SIMULATED") -> dict:
    date = date or et_now().strftime("%Y-%m-%d")
    rows = _read_ledger(date)
    cov = tick_coverage(rows, date)
    fun = funnel(rows)
    trades = round_trips(date, fills)
    breaks = rule_audit(rows, trades)

    # The digest verdict leads with coverage on purpose: if the lane was dark, a clean
    # trade record is an artifact of silence, not evidence of discipline.
    if cov["verdict"] in ("DARK", "RED"):
        verdict = "RED"
    elif breaks:
        verdict = "RULE_BREAK"
    elif cov["verdict"] == "YELLOW":
        verdict = "YELLOW"
    elif cov["verdict"] in ("WEEKEND", "HOLIDAY"):
        verdict = "NO_SESSION"
    else:
        verdict = "GREEN"

    return {"date": date, "generated_at_et": et_now().isoformat(timespec="seconds"),
            "verdict": verdict, "coverage": cov, "funnel": fun, "trades": trades,
            "rule_breaks": breaks, "fill_class": fills}


def render(d: dict) -> str:
    cov, fun, tr = d["coverage"], d["funnel"], d["trades"]
    L = [f"# Futures EOD — {d['date']}", "",
         f"> Generated `{d['generated_at_et']}` · verdict **{d['verdict']}**",
         f"> Fill class **{d['fill_class']}**"
         + (" — simulated fills are mechanism evidence, **never edge evidence**."
            if d["fill_class"] == "SIMULATED" else ""), ""]

    L += ["## Was the lane awake?", "",
          f"**{cov['verdict']}** — {cov['ticks']}/{cov['expected']} ticks "
          f"({cov['pct']:.0%}). {cov['note']}", ""]
    if cov["verdict"] in ("DARK", "RED"):
        L += ["> ⚠️ Everything below is conditional on the engine having run. It mostly "
              "did not, so read the numbers as *unknown*, not as *zero*.", ""]

    L += ["## Funnel", "",
          f"- **{fun['signals_seen']}** signals seen → **{fun['entries']}** entries "
          f"→ {fun['exit_events']} exit events"]
    if fun["rejections_by_rail"]:
        L.append("- rejected by rail: " + " · ".join(
            f"`{k}` {v}" for k, v in sorted(fun["rejections_by_rail"].items(),
                                            key=lambda kv: -kv[1])))
    if fun["actions"]:
        L.append("- actions: " + " · ".join(f"`{k}` {v}" for k, v in fun["actions"].items()))
    if fun["feed_verdicts"]:
        L.append("- feed: " + " · ".join(f"`{k}` {v}" for k, v in fun["feed_verdicts"].items()))
    if fun["errors"]:
        L.append(f"- ⚠️ **{len(fun['errors'])} errors** — {fun['errors'][:3]}")
    L.append("")

    L += [f"## Round trips ({tr['fills']})", ""]
    if tr["n"]:
        L += [f"- **{tr['n']}** closed · **${tr['total_pnl']:,.2f}** · "
              f"WR {tr['win_rate']:.0%} · best ${tr['best']:,.2f} / worst ${tr['worst']:,.2f}",
              "- by setup: " + " · ".join(f"`{k}` {v}" for k, v in tr["by_setup"].items()),
              "- by exit: " + " · ".join(f"`{k}` {v}" for k, v in tr["by_exit"].items())]
    else:
        L.append("- none closed today")
    L.append("")

    L += ["## Rule audit", ""]
    if d["rule_breaks"]:
        L.append(f"🚨 **{len(d['rule_breaks'])} break(s)** — process over P&L, a winning "
                 "trade that broke a rule still counts:")
        for b in d["rule_breaks"]:
            L.append(f"- `{b['ts']}` **{b['rule']}** — {b['detail']}")
    else:
        L.append("✅ no rule breaks detected (post-hoc check, independent of the entry gate)")
    L.append("")
    return "\n".join(L)


def write(d: dict) -> Path:
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGEST_DIR / f"{d['date']}.md"
    path.write_text(render(d), encoding="utf-8")
    try:
        STATE_OUT.parent.mkdir(parents=True, exist_ok=True)
        slim = {k: v for k, v in d.items() if k != "trades"}
        slim["trades"] = {k: v for k, v in d["trades"].items() if k != "rows"}
        tmp = STATE_OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, STATE_OUT)
    except Exception:  # noqa: BLE001 -- digest write is the deliverable; state is a bonus
        pass
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures EOD session review")
    ap.add_argument("--date", default=None)
    ap.add_argument("--fills", default="SIMULATED",
                    choices=["SIMULATED", "BROKER", "UNKNOWN"])
    ap.add_argument("--print", action="store_true", help="print the digest to stdout")
    args = ap.parse_args(argv)

    d = build(args.date, args.fills)
    path = write(d)
    if args.print:
        # The digest is UTF-8 (arrows, check marks); a Windows console defaults to cp1252
        # and would raise UnicodeEncodeError mid-print, turning a successful review into a
        # traceback. The FILE is always written correctly regardless -- only stdout needs
        # persuading.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
        print(render(d))
    else:
        print(json.dumps({"date": d["date"], "verdict": d["verdict"],
                          "coverage": d["coverage"]["verdict"],
                          "ticks": d["coverage"]["ticks"],
                          "entries": d["funnel"]["entries"],
                          "closed": d["trades"]["n"],
                          "pnl": d["trades"]["total_pnl"],
                          "rule_breaks": len(d["rule_breaks"]),
                          "digest": str(path.relative_to(REPO))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
