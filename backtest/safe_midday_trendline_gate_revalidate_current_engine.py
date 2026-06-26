"""RE-VALIDATE midday_trendline_gate under the CURRENT LIVE Safe engine (2026-06-26).

The gate (gates.py #10): blocks entries whose ONLY trigger is `trendline_rejection`
in the window 11:30-14:00 ET (start_minutes=690). Direction-NEUTRAL (fires on C and P).
Safe=true. The block was ratified on the OLD engine (OTM + premium_stop -0.08/-0.10,
NO chandelier). This re-runs the A/B on the CURRENT LIVE config:
  - real OPRA fills (use_real_fills=True)
  - chart-stop-primary: premium_stop -0.50 catastrophe cap (both sides)
  - managed exits: tp1 0.50 @ 0.667 qty, runner 2.5x, chandelier trailing 0.125 off HWM
  - Safe sizing: OTM-2 tier at $2,000 equity (v15_strike_offset_per_tier), 30% risk cap
  - min_triggers bear=1 / bull=2, block_elite_bull, block_level_rejection ON (live)

A/B = gate ON (blocked, baseline=live) vs gate OFF (unblocked). DELTA = blocked - unblocked.
If DELTA > 0, the block still earns its keep. If DELTA <= 0, it suppresses winners now.

Anchor-no-regression: the gate is trendline-only; J anchors are level/conf trades, so
they should be untouched. We confirm the bearish source-of-truth PNL is identical.

Security: read-only, no Alpaca, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA = ROOT / "backtest" / "data"
SPY = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
VIX = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
# Recent OOS extension (post-06-16) — separate file, merge for the recent window
SPY_REC = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-25.csv")
VIX_REC = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-25.csv")

IS_S, IS_E = dt.date(2025, 1, 2), dt.date(2026, 5, 7)
OOS_S, OOS_E = dt.date(2026, 5, 8), dt.date(2026, 6, 16)
REC_S, REC_E = dt.date(2026, 5, 19), dt.date(2026, 6, 25)

SW = [
    ("W1 2025 H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("W2 2025 H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ("W3 2026 Q1", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
    ("W4 2026 Apr-May", dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
]

J_WIN = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSS = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}

# CURRENT LIVE Safe config (mirrors automation/state/params.json + reconfirm scorecard).
LIVE = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    premium_stop_pct=-0.50,
    premium_stop_pct_bear=-0.50,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    level_stop_buffer_dollars=0.50,
    time_stop_minutes_before_close=20,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.125,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    min_triggers_bear=1,
    min_triggers_bull=2,
    initial_equity=2000.0,
    params_overrides={"v15_strike_offset_per_tier": json.load(
        open(ROOT / "automation" / "state" / "params.json"))["v15_strike_offset_per_tier"]},
)

GATE_LO, GATE_HI = dt.time(11, 30), dt.time(14, 0)


def _date(t):
    et = t.entry_time_et
    ts = pd.Timestamp(et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.date()


def _time(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.time()


def _pnl(tr):
    return sum(t.dollar_pnl for t in tr)


def _is_tl_only(t):
    tg = set(t.triggers_fired)
    return len(tg) == 1 and "trendline_rejection" in tg


def _in_window(t):
    return GATE_LO <= _time(t) < GATE_HI


def run(spy, vix, s, e, gate):
    kw = dict(LIVE)
    kw["midday_trendline_gate"] = gate
    return run_backtest(spy, vix, start_date=s, end_date=e, **kw)


def block_delta(spy, vix, s, e, label):
    """DELTA = pnl(gate ON) - pnl(gate OFF). Positive => block helps."""
    on = run(spy, vix, s, e, True)
    off = run(spy, vix, s, e, False)
    p_on, p_off = _pnl(on.trades), _pnl(off.trades)
    # The trades the gate removes = those in OFF that are tl-only + in window
    removed = [t for t in off.trades if _is_tl_only(t) and _in_window(t)]
    n_rem = len(removed)
    rem_pnl = _pnl(removed)
    delta = p_on - p_off
    print(f"\n=== {label} ===")
    print(f"  gate OFF (unblocked): n={len(off.trades)} pnl={p_off:+.0f}")
    print(f"  gate ON  (blocked):   n={len(on.trades)} pnl={p_on:+.0f}")
    print(f"  removed trades (tl-only, 11:30-14:00): n={n_rem} pnl={rem_pnl:+.0f}")
    print(f"  BLOCK_DELTA (ON-OFF) = {delta:+.0f}  ({'block helps' if delta > 0 else 'block hurts/neutral'})")
    if removed:
        wins = sum(1 for t in removed if t.dollar_pnl > 0)
        for t in sorted(removed, key=_date):
            sd = "C" if t.side == "C" else "P"
            print(f"      {_date(t)} {_time(t)} {sd}  pnl={t.dollar_pnl:+.0f}  {'WIN' if t.dollar_pnl>0 else 'LOSS'}")
        print(f"      removed WR={wins}/{n_rem}={wins/n_rem:.0%}")
    return delta, p_on, p_off, n_rem, rem_pnl, on, off


if __name__ == "__main__":
    is_d, is_on, is_off, is_n, is_rp, is_ron, is_roff = block_delta(SPY, VIX, IS_S, IS_E, "IS 2025-01-02..2026-05-07")
    oos_d, oos_on, oos_off, oos_n, oos_rp, oos_ron, oos_roff = block_delta(SPY, VIX, OOS_S, OOS_E, "OOS 2026-05-08..2026-06-16")
    rec_d, rec_on, rec_off, rec_n, rec_rp, _, _ = block_delta(SPY_REC, VIX_REC, REC_S, REC_E, "RECENT 2026-05-19..2026-06-25")

    # Anchor no-regression: J source-of-truth days PNL must be unchanged by the gate.
    print("\n=== ANCHOR NO-REGRESSION (J source-of-truth, gate ON vs OFF) ===")
    on_by = {}
    off_by = {}
    for t in is_ron.trades + oos_ron.trades:
        on_by.setdefault(_date(t), 0.0)
        on_by[_date(t)] += t.dollar_pnl
    for t in is_roff.trades + oos_roff.trades:
        off_by.setdefault(_date(t), 0.0)
        off_by[_date(t)] += t.dollar_pnl
    anchor_ok = True
    for d in sorted(J_WIN | J_LOSS):
        po = on_by.get(d, 0.0)
        pf = off_by.get(d, 0.0)
        tag = "WIN" if d in J_WIN else "LOSS"
        flag = ""
        if abs(po - pf) > 1.0:
            flag = " <-- CHANGED BY GATE"
            anchor_ok = False
        print(f"  {d} ({tag}): gate_ON={po:+.0f}  gate_OFF={pf:+.0f}{flag}")
    print(f"  ANCHOR: {'PASS (gate does not touch anchors)' if anchor_ok else 'FAIL'}")

    # Sub-window stability of the BLOCK (delta per window)
    print("\n=== SUB-WINDOW BLOCK DELTA (ON-OFF per window) ===")
    sw_help = sw_hurt = 0
    for lbl, s, e in SW:
        on = _pnl(run(SPY, VIX, s, e, True).trades)
        off = _pnl(run(SPY, VIX, s, e, False).trades)
        d = on - off
        if d > 0:
            sw_help += 1
        elif d < 0:
            sw_hurt += 1
        print(f"  {lbl}: delta={d:+.0f} ({'help' if d>0 else 'hurt' if d<0 else 'neutral'})")

    print("\n" + "=" * 60)
    print("=== VERDICT: does the block STILL earn its keep? ===")
    print(f"  IS    block_delta = {is_d:+.0f} (removed n={is_n}, pnl={is_rp:+.0f})")
    print(f"  OOS   block_delta = {oos_d:+.0f} (removed n={oos_n}, pnl={oos_rp:+.0f})")
    print(f"  REC   block_delta = {rec_d:+.0f} (removed n={rec_n}, pnl={rec_rp:+.0f})")
    print(f"  SW: help={sw_help} hurt={sw_hurt}")
    print(f"  Anchor: {'PASS' if anchor_ok else 'FAIL'}")
    keep = is_d > 0 and oos_d >= 0
    print(f"\n  -> {'KEEP (block still helps)' if keep else 'UNBLOCK candidate (block no longer helps / now neutral-or-hurts)'}")
