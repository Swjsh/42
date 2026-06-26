"""
RE-VALIDATION (2026-06-26): VIX_BULL_HARD_CAP (filter 9) under the CURRENT engine.

The old scorecard (analysis/recommendations/vix-bull-hard-cap-01.json, ratified
2026-06-17) validated this block on the OLD engine: premium_stop_pct_bear=-0.10,
premium_stop_pct_bull=-0.08 (wide premium-stop bracket). That is STALE.

The CURRENT Safe engine (chart-stops-ab-2026-06-18.json B2 SHIP) is:
  premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50 (catastrophe cap),
  chart-stop-primary + ribbon-flip-back + chandelier profit-lock + time-stop,
  tp1 0.50 @ 0.667, runner 2.50, real OPRA fills, per-tier strike, Safe $2K cap.

A gate that correctly blocked a LOSING OTM+wide-stop bull config may now block a
WINNER under the -50% cap + managed exits (the bull stop sweep in the chart-stops
scorecard showed bull WR 0.333 @ -8% -> 0.778 @ -50%: the wide cap RIDES bull winners).

This script re-runs the A/B on the CURRENT engine via the params-driven path
(autoresearch.runner.run_with_params, the SAME path the chart-stops scorecard used),
with cap-admission at Safe-2 ($2,000). BASE = current params.json (all live gates).
CANDIDATE = BASE but vix_bull_max raised 18.0 -> 22.0 (UNBLOCK the 18-22 VIX band).
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.autoresearch.runner import run_with_params, load_data

# Real OPRA option coverage bounds (per chart-stops scorecard full_history_note).
FULL_START = dt.date(2025, 1, 1)
FULL_END   = dt.date(2026, 5, 29)
# OOS slice (recent) — mirror the chart-stops oos_subwindow.
OOS_START  = dt.date(2026, 3, 1)
OOS_END    = dt.date(2026, 5, 29)

IS_SUB_WINDOWS = [
    ("W1-2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2-2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3-Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4-Apr-May",dt.date(2026, 4, 1),  dt.date(2026, 5, 29)),
]

# J source-of-truth (OP-16). Winners engine MUST take; losers MUST skip/lose-less.
J_WINNERS = {dt.date(2026, 4, 29): 342, dt.date(2026, 5, 1): 470, dt.date(2026, 5, 4): 730}
J_LOSERS  = {dt.date(2026, 5, 5): -260, dt.date(2026, 5, 6): -300, dt.date(2026, 5, 7): -165}

# CURRENT production Safe engine config (params.json + chart-stops B2 SHIP).
# This is the byte-current live engine, NOT the old -10/-8 bracket.
BASE = dict(
    use_real_fills=True,
    # chart-stop-primary -50% catastrophe cap BOTH sides (B2 SHIP):
    premium_stop_pct_bear=-0.50,
    premium_stop_pct_bull=-0.50,
    # managed exits (params.json):
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    level_stop_buffer_dollars=0.50,
    ribbon_flip_back_min_spread_cents=30.0,
    time_stop_minutes_before_close=20,
    # chandelier profit-lock (Safe; WP-6 trail 0.125):
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.05,
    # entry gates / sizing (all live TRUE in params.json):
    midday_trendline_gate=True,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    entry_bar_body_pct_min=0.20,
    block_bull_1100_1200=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=0.0,
    block_elite_bull_vix_high=25.0,
    vix_bear_hard_cap=23.0,
    # asymmetric triggers (bear 1, bull 2):
    min_triggers_bear=1,
    min_triggers_bull=2,
    # The block under test — LIVE value is 18.0:
    vix_bull_max=18.0,
)

# Cap-admission at Safe-2 ($2,000) — the realizable book the live order gate permits.
CAP_ACCOUNT = "safe"
CAP_EQUITY  = 2000.0


def edate(t):
    et = t.entry_time_et
    return et.date() if hasattr(et, "date") else dt.date.fromisoformat(str(et)[:10])


def pnl_window(trades, s, e):
    return sum(t.dollar_pnl for t in trades if s <= edate(t) <= e)


def pnl_on_date(trades, d):
    return sum(t.dollar_pnl for t in trades if edate(t) == d)


def is_bull(t):
    # Calls = bull. TradeFill carries direction/option_type; check robustly.
    for attr in ("direction", "side", "option_type", "right"):
        v = getattr(t, attr, None)
        if v is None:
            continue
        s = str(v).upper()
        if s in ("BULL", "C", "CALL", "LONG"):
            return True
        if s in ("BEAR", "P", "PUT", "SHORT"):
            return False
    return None


def edge_capture(trades):
    """OP-16 edge_capture on the J source-of-truth days."""
    ec = 0.0
    for d, _ in J_WINNERS.items():
        ec += pnl_on_date(trades, d)
    for d, _ in J_LOSERS.items():
        loss = pnl_on_date(trades, d)
        ec -= max(0.0, -loss)  # subtract engine loss on J losing days
    return ec


def run(label, vix_bull_max, spy, vix):
    p = dict(BASE)
    p["vix_bull_max"] = vix_bull_max
    res_full, _ = run_with_params(p, FULL_START, FULL_END, spy, vix,
                                  cap_account=CAP_ACCOUNT, cap_equity=CAP_EQUITY)
    res_oos, _  = run_with_params(p, OOS_START, OOS_END, spy, vix,
                                  cap_account=CAP_ACCOUNT, cap_equity=CAP_EQUITY)
    return res_full, res_oos


def summarize(res):
    trades = res.trades
    bulls = [t for t in trades if is_bull(t) is True]
    bears = [t for t in trades if is_bull(t) is False]
    return {
        "n": len(trades),
        "pnl": sum(t.dollar_pnl for t in trades),
        "n_bull": len(bulls),
        "bull_pnl": sum(t.dollar_pnl for t in bulls),
        "n_bear": len(bears),
        "bear_pnl": sum(t.dollar_pnl for t in bears),
        "ec": edge_capture(trades),
        "trades": trades,
    }


def main():
    print("Loading real-OPRA data (Jan 2025 - May 2026)...")
    spy, vix = load_data(FULL_START, FULL_END)

    print("Running BASE (vix_bull_max=18.0, LIVE block ON)...")
    b_full, b_oos = run("BASE", 18.0, spy, vix)
    print("Running CANDIDATE (vix_bull_max=22.0, UNBLOCK 18-22 band)...")
    c_full, c_oos = run("CAND", 22.0, spy, vix)

    bf, bo = summarize(b_full), summarize(b_oos)
    cf, co = summarize(c_full), summarize(c_oos)

    print("\n" + "=" * 78)
    print("VIX_BULL_HARD_CAP re-validation — CURRENT engine (real fills, -50% cap, Safe $2K)")
    print("=" * 78)
    print("  BASE = block ON  (vix_bull_max=18.0, blocks CALL when VIX>=18)")
    print("  CAND = block OFF (vix_bull_max=22.0, allows CALL in VIX 18-22 band)")
    print()
    print(f"  FULL [{FULL_START}..{FULL_END}]:")
    print(f"    BASE n={bf['n']:>3} pnl={bf['pnl']:+9,.0f}  bull(n={bf['n_bull']} ${bf['bull_pnl']:+,.0f})  bear(n={bf['n_bear']} ${bf['bear_pnl']:+,.0f})  EC={bf['ec']:+.0f}")
    print(f"    CAND n={cf['n']:>3} pnl={cf['pnl']:+9,.0f}  bull(n={cf['n_bull']} ${cf['bull_pnl']:+,.0f})  bear(n={cf['n_bear']} ${cf['bear_pnl']:+,.0f})  EC={cf['ec']:+.0f}")
    is_delta = cf['pnl'] - bf['pnl']
    blocked_full = cf['n'] - bf['n']
    print(f"    --> UNBLOCK delta = {is_delta:+,.0f}  (CAND adds {blocked_full} trade(s) = the 18-22 band bulls)")
    print()
    print(f"  OOS [{OOS_START}..{OOS_END}]:")
    print(f"    BASE n={bo['n']:>3} pnl={bo['pnl']:+9,.0f}  bull(n={bo['n_bull']} ${bo['bull_pnl']:+,.0f})")
    print(f"    CAND n={co['n']:>3} pnl={co['pnl']:+9,.0f}  bull(n={co['n_bull']} ${co['bull_pnl']:+,.0f})")
    oos_delta = co['pnl'] - bo['pnl']
    blocked_oos = co['n'] - bo['n']
    print(f"    --> UNBLOCK delta = {oos_delta:+,.0f}  (CAND adds {blocked_oos} trade(s))")

    # Identify the actual trades the gate blocks (in CAND, not in BASE).
    base_keys = {(str(edate(t)), round(float(t.entry_premium), 2)) for t in bf['trades']}
    added = [t for t in cf['trades'] if (str(edate(t)), round(float(t.entry_premium), 2)) not in base_keys]
    print(f"\n  Trades the gate BLOCKS (present in CAND/unblocked, absent in BASE) — full history:")
    if not added:
        print("    (none — gate blocks ZERO trades under the current engine config)")
    for t in sorted(added, key=lambda x: str(edate(x))):
        d = edate(t)
        print(f"    {d}  bull={is_bull(t)}  premium=${float(t.entry_premium):.2f}  pnl={t.dollar_pnl:+,.0f}")

    # Sub-window stability of the UNBLOCK.
    print(f"\n  IS sub-windows (UNBLOCK delta per window):")
    sw_hurt = 0  # for the UNBLOCK: 'hurt' = unblock LOSES money in that window (block helped)
    for name, s, e in IS_SUB_WINDOWS:
        bp = pnl_window(bf['trades'], s, e)
        cp = pnl_window(cf['trades'], s, e)
        d = cp - bp
        flag = "UNBLOCK-WINS" if d > 50 else ("UNBLOCK-LOSES(block helps)" if d < -50 else "FLAT")
        if d < -50:
            sw_hurt += 1
        print(f"    {name:<12s}  base={bp:+8,.0f}  unblocked={cp:+8,.0f}  delta={d:+7,.0f}  {flag}")

    # Anchor no-regression (bearish source-of-truth).
    print(f"\n  Anchor no-regression (J winners must NOT regress on UNBLOCK):")
    anchor_ok = True
    for d in sorted(set(J_WINNERS) | set(J_LOSERS)):
        bp = pnl_on_date(bf['trades'], d)
        cp = pnl_on_date(cf['trades'], d)
        delta = cp - bp
        kind = "WIN" if d in J_WINNERS else "LOSS"
        flag = "OK"
        if d in J_WINNERS and delta < -50:
            anchor_ok = False; flag = "REGRESS"
        if d in J_LOSERS and delta < -50:
            anchor_ok = False; flag = "WORSE-LOSS"
        print(f"    {d} ({kind})  base={bp:+7,.0f}  unblocked={cp:+7,.0f}  delta={delta:+7,.0f}  {flag}")
    print(f"    EC: BASE={bf['ec']:+.0f}  UNBLOCKED={cf['ec']:+.0f}  (delta={cf['ec']-bf['ec']:+.0f})")

    # Verdict (block earns its keep iff UNBLOCK delta < 0).
    print("\n" + "=" * 78)
    print("VERDICT (does the BLOCK still earn its keep under the current engine?)")
    print("=" * 78)
    block_help_full = -is_delta   # block's contribution = -(unblock delta)
    block_help_oos  = -oos_delta
    print(f"  Full-history: block contributes {block_help_full:+,.0f} (block HELPS if >0)")
    print(f"  OOS:          block contributes {block_help_oos:+,.0f} (block HELPS if >0)")
    print(f"  Anchor no-regression on unblock: {'OK' if anchor_ok else 'REGRESSION'}")
    print(f"  EC unchanged by unblock:         {'OK' if abs(cf['ec']-bf['ec'])<1 else 'CHANGED'}")
    if block_help_full <= 0 and block_help_oos <= 0:
        print("\n  >>> UNBLOCK: the block no longer earns its keep on the current engine.")
    elif block_help_full > 0 and block_help_oos > 0:
        print("\n  >>> KEEP: the block still produces a positive delta on the current engine.")
    else:
        print("\n  >>> MIXED / INCONCLUSIVE: block helps in one window, hurts in the other.")
    print("=" * 78)


if __name__ == "__main__":
    main()
