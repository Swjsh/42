"""Re-validate block_elite_bull under the CURRENT engine (real fills + managed exits).

A/B: production params with block ON vs OFF, real OPRA fills, over full option-data
history (2025-01-02 .. 2026-06-18). Isolates the ELITE+level_reclaim trades the gate
targets and reports the per-trade real-fill delta. Anchor-no-regression checked on the
bear source-of-truth dates.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_revalidate_block_elite_bull.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

from autoresearch import runner  # noqa: E402

START = dt.date(2025, 1, 2)
END = dt.date(2026, 6, 18)  # option-cache coverage end

PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
prod = json.loads(PARAMS_PATH.read_text())

# Force real fills for the WR authority (C1).
prod["use_real_fills"] = True

# Load SPY/VIX master that covers the window.
spy_path = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-18.csv"
vix_path = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-18.csv"
if not vix_path.exists():
    # fall back to whatever vix master pairs with the spy master
    cands = sorted((ROOT / "backtest" / "data").glob("vix_5m_2025-01-01_*.csv"))
    vix_path = cands[-1] if cands else vix_path
print(f"SPY: {spy_path.name}  VIX: {vix_path.name}")
spy = pd.read_csv(spy_path)
vix = pd.read_csv(vix_path)
spy = spy[(spy["timestamp_et"] >= str(START)) & (spy["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
vix = vix[(vix["timestamp_et"] >= str(START)) & (vix["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
print(f"SPY bars: {len(spy):,}  VIX bars: {len(vix):,}")


def run(block: bool):
    p = dict(prod)
    p["block_elite_bull"] = block
    if block:
        p["block_elite_bull_vix_low"] = 0.0
        p["block_elite_bull_vix_high"] = 25.0
    res, m = runner.run_with_params(p, START, END, spy, vix, enforce_cap=False)
    return res, m


def trade_key(t):
    et = t.entry_time_et
    if hasattr(et, "tz_localize") and getattr(et, "tz", None) is not None:
        et = et.tz_localize(None)
    return (str(et), getattr(t, "strike", None), getattr(t, "side", None))


def is_gate_target(t):
    """Trades the gate predicate can fire on: bull (C) + level_reclaim trigger.

    The gate also requires tier==ELITE, but ELITE is a function of the trigger set
    (confluence OR sequence rec/rej). TradeFill carries side + triggers_fired, not
    the tier label; the decisions log (below) is the authoritative SKIP-action proof.
    Any C-side trade carrying level_reclaim that the gate suppresses IS the target.
    """
    side = getattr(t, "side", "") or ""
    trigs = getattr(t, "triggers_fired", None) or []
    if isinstance(trigs, str):
        trigs = [x.strip() for x in trigs.split(",")]
    return str(side).upper() == "C" and "level_reclaim" in trigs


print("\n=== Running block ON (production) ===")
res_on, m_on = run(True)
print("=== Running block OFF (unblocked) ===")
res_off, m_off = run(False)

on_trades = list(res_on.trades)
off_trades = list(res_off.trades)
on_keys = {trade_key(t) for t in on_trades}
off_keys = {trade_key(t) for t in off_trades}

# Trades that appear ONLY when unblocked = the ones the gate currently suppresses.
unblocked_only = [t for t in off_trades if trade_key(t) not in on_keys]
# Trades that appear ONLY when blocked = quality-slot cascade unblocking something else.
blocked_only = [t for t in on_trades if trade_key(t) not in off_keys]

print("\n" + "=" * 60)
print(f"BLOCK ON  : {len(on_trades)} trades, total ${sum(t.dollar_pnl for t in on_trades):.0f}")
print(f"BLOCK OFF : {len(off_trades)} trades, total ${sum(t.dollar_pnl for t in off_trades):.0f}")
print(f"AGG DELTA (OFF - ON): ${sum(t.dollar_pnl for t in off_trades) - sum(t.dollar_pnl for t in on_trades):.0f}")

print("\n--- Trades the gate SUPPRESSES (in OFF only) ---")
elite_suppressed = [t for t in unblocked_only if is_gate_target(t)]
other_suppressed = [t for t in unblocked_only if not is_gate_target(t)]
sup_pnl = sum(t.dollar_pnl for t in unblocked_only)
elite_pnl = sum(t.dollar_pnl for t in elite_suppressed)
print(f"  Total suppressed: {len(unblocked_only)} trades, ${sup_pnl:.0f}")
print(f"  ...of which ELITE+level_reclaim bull (gate target): {len(elite_suppressed)} trades, ${elite_pnl:.0f}")
print(f"  ...other (cascade): {len(other_suppressed)} trades, ${sum(t.dollar_pnl for t in other_suppressed):.0f}")
if elite_suppressed:
    n_w = sum(1 for t in elite_suppressed if t.dollar_pnl > 0)
    print(f"  ELITE target WR: {n_w}/{len(elite_suppressed)} = {100*n_w/len(elite_suppressed):.0f}%")
    print(f"  ELITE target per-trade: ${elite_pnl/len(elite_suppressed):.1f}")
    for t in sorted(elite_suppressed, key=lambda x: str(x.entry_time_et)):
        print(f"    {str(t.entry_time_et)[:16]}  {getattr(t,'contract_symbol','?')}  pnl=${t.dollar_pnl:.0f}")

print("\n--- Trades present ONLY when blocked (cascade re-fills) ---")
print(f"  {len(blocked_only)} trades, ${sum(t.dollar_pnl for t in blocked_only):.0f}")

# Anchor-no-regression: bear source-of-truth dates must be unchanged.
ANCHOR_DATES = {"2025-04-29", "2025-05-01", "2025-05-04", "2025-05-05", "2025-05-06", "2025-05-07"}
# NOTE: anchors are 2026 dates in OP-16? They are 4/29..5/07 — check both years present in data window.
def anchor_pnl(trades):
    out = {}
    for t in trades:
        d = str(t.entry_time_et)[:10]
        if d in ANCHOR_DATES or d.replace("2025", "2026") in ANCHOR_DATES or d[5:] in {"04-29", "05-01", "05-04", "05-05", "05-06", "05-07"}:
            out.setdefault(d, 0.0)
            out[d] += t.dollar_pnl
    return out

print("\n--- ANCHOR no-regression (bear source-of-truth) ---")
a_on = anchor_pnl(on_trades)
a_off = anchor_pnl(off_trades)
all_anchor_days = sorted(set(a_on) | set(a_off))
regression = False
for d in all_anchor_days:
    v_on = a_on.get(d, 0.0)
    v_off = a_off.get(d, 0.0)
    flag = "" if abs(v_on - v_off) < 0.01 else "  <-- CHANGED"
    if abs(v_on - v_off) >= 0.01:
        regression = True
    print(f"  {d}: ON=${v_on:.0f}  OFF=${v_off:.0f}{flag}")
if not all_anchor_days:
    print("  (no anchor-date trades in this window — anchors are bear/PUT, gate only touches bull)")
print(f"\nANCHOR REGRESSION: {'YES' if regression else 'NO'}")
