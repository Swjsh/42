"""Re-validate block_bull_1100_1200 under the CURRENT engine (real-fills + ITM/managed exits).

A/B: run_backtest with block_bull_1100_1200 ON (production) vs OFF (unblocked), with
use_real_fills=True and the FULL production Safe params armed. The diff between the two
trade sets == exactly the bull (C) trades fired in the 11:00-12:00 ET window, scored under
real OPRA fills + the managed exit_manager (partial TP1 + runner + chandelier + -50% cap).

Decision: does blocking STILL produce a POSITIVE edge_delta under real fills, or does the
new exit structure turn those blocked bulls into winners (=> UNBLOCK)?

Also confirms anchor-no-regression (the bear source-of-truth trades are untouched by a
bull-only gate; we verify the bear trade set is byte-identical between the two runs).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))
sys.path.insert(0, str(ROOT))  # repo root for crypto.lib.strike_selection
from lib.orchestrator import run_backtest  # noqa: E402

DATA = ROOT / "backtest" / "data"
SPY = DATA / "spy_5m_2025-01-01_2026-06-18.csv"
VIX = DATA / "vix_5m_2025-01-01_2026-06-18.csv"
PARAMS = ROOT / "automation" / "state" / "params.json"

# IS/OOS split from the original scorecard.
IS_END = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)

START = dt.date(2025, 1, 2)
END = dt.date(2026, 6, 18)


def load_params() -> dict:
    p = json.loads(PARAMS.read_text())
    # Strip _doc / comment keys (start with "_") — they are prose, not knobs.
    return {k: v for k, v in p.items() if not k.startswith("_")}


def run(block: bool, params: dict):
    spy = pd.read_csv(SPY)
    vix = pd.read_csv(VIX)
    spy = spy[(spy["timestamp_et"] >= str(START)) & (spy["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= str(START)) & (vix["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    ov = dict(params)
    ov["block_bull_1100_1200"] = block
    res = run_backtest(
        spy, vix,
        start_date=START, end_date=END,
        use_real_fills=True,
        initial_equity=2000.0,            # Safe-2 account
        per_trade_risk_cap_pct=0.30,      # Safe Rule 6
        params_overrides=ov,
    )
    return res


def trade_key(t) -> tuple:
    et = t.entry_time_et
    if hasattr(et, "tz") and getattr(et, "tz", None) is not None:
        et = et.tz_localize(None)
    return (str(et), getattr(t, "contract_symbol", getattr(t, "strike", "")), t.side if hasattr(t, "side") else "")


def naive(ts):
    if hasattr(ts, "tz_localize") and getattr(ts, "tz", None) is not None:
        return ts.tz_localize(None)
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        return ts.replace(tzinfo=None)
    return ts


def main():
    params = load_params()
    print(f"Loaded {len(params)} production param knobs. Running A/B (real fills, Safe $2K)...")

    res_blocked = run(True, params)   # production
    res_unblocked = run(False, params)

    tb = res_blocked.trades
    tu = res_unblocked.trades
    print(f"\nBLOCKED   (production): {len(tb)} trades, total ${sum(t.dollar_pnl for t in tb):,.0f}")
    print(f"UNBLOCKED            : {len(tu)} trades, total ${sum(t.dollar_pnl for t in tu):,.0f}")

    # The UNBLOCKED-only trades = the bull 11-12 trades the gate suppresses.
    kb = {trade_key(t) for t in tb}
    extra = [t for t in tu if trade_key(t) not in kb]

    # Sanity: every extra trade should be a CALL in 11:00-12:00 ET.
    print(f"\n=== UNBLOCKED-ONLY TRADES (the gate's victims), n={len(extra)} ===")
    rows = []
    for t in sorted(extra, key=lambda t: naive(t.entry_time_et)):
        et = naive(t.entry_time_et)
        side = getattr(t, "side", "?")
        is_is = et.date() <= IS_END
        rows.append((et, side, t.dollar_pnl, "IS" if is_is else "OOS",
                     getattr(t, "exit_reason", ""), getattr(t, "strike", "")))
        intw = dt.time(11, 0) <= et.time() < dt.time(12, 0)
        flag = "" if (side == "C" and intw) else "  <-- UNEXPECTED (not C/11-12)"
        print(f"  {et}  {side}  ${t.dollar_pnl:+8.1f}  {'IS' if is_is else 'OOS':3}  {getattr(t,'exit_reason','')}{flag}")

    is_extra = [r for r in rows if r[3] == "IS"]
    oos_extra = [r for r in rows if r[3] == "OOS"]
    is_pnl = sum(r[2] for r in is_extra)
    oos_pnl = sum(r[2] for r in oos_extra)
    all_pnl = is_pnl + oos_pnl
    is_wr = sum(1 for r in is_extra if r[2] > 0) / max(1, len(is_extra))
    oos_wr = sum(1 for r in oos_extra if r[2] > 0) / max(1, len(oos_extra))

    print(f"\n=== EDGE DELTA (block REMOVES these trades) ===")
    print(f"  IS  blocked: n={len(is_extra)}  WR={is_wr:.1%}  P&L=${is_pnl:+.1f}  -> IS_delta(block)=${-is_pnl:+.1f}")
    print(f"  OOS blocked: n={len(oos_extra)}  WR={oos_wr:.1%}  P&L=${oos_pnl:+.1f}  -> OOS_delta(block)=${-oos_pnl:+.1f}")
    print(f"  ALL blocked: n={len(rows)}  P&L=${all_pnl:+.1f}  -> total_delta(block)=${-all_pnl:+.1f}")
    print(f"\n  block JUSTIFIED if total P&L of blocked trades < 0 (i.e. they are net losers under real fills)")
    print(f"  block STALE     if total P&L of blocked trades > 0 (gate suppresses WINNERS under real fills)")

    # Anchor / bear no-regression: bear trade set must be byte-identical (bull-only gate).
    bear_b = sorted([(str(naive(t.entry_time_et)), round(t.dollar_pnl, 2)) for t in tb if getattr(t, "side", "") == "P"])
    bear_u = sorted([(str(naive(t.entry_time_et)), round(t.dollar_pnl, 2)) for t in tu if getattr(t, "side", "") == "P"])
    print(f"\n=== ANCHOR / BEAR NO-REGRESSION ===")
    print(f"  bear trades blocked-run: n={len(bear_b)}  total ${sum(p for _,p in bear_b):,.0f}")
    print(f"  bear trades unblock-run: n={len(bear_u)}  total ${sum(p for _,p in bear_u):,.0f}")
    print(f"  bear sets IDENTICAL: {bear_b == bear_u}")

    # Aggregate effect on the whole engine (real fills).
    print(f"\n=== AGGREGATE (whole engine, real fills) ===")
    tot_b = sum(t.dollar_pnl for t in tb)
    tot_u = sum(t.dollar_pnl for t in tu)
    print(f"  BLOCKED total ${tot_b:,.1f}  (n={len(tb)})")
    print(f"  UNBLOCK total ${tot_u:,.1f}  (n={len(tu)})")
    print(f"  unblocking changes aggregate by ${tot_u - tot_b:+,.1f}")


if __name__ == "__main__":
    main()
