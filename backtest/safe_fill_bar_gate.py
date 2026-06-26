"""A/B test: require_bearish_fill_bar=True for SAFE bears.

Canonical SAFE baseline matches CONTEXT-92 methodology:
  - IS: 2025-01-02 to 2026-05-07   (n=98, total=+23722 in CONTEXT-92)
  - OOS: 2026-05-08 to 2026-06-15  (full OOS through data end, n~20)
  - initial_equity=2000.0  (actual SAFE account -> OTM-2 via v15_strike_offset_per_tier)
  - params_overrides = full SAFE params.json content

OP-22 auto-ratify gates:
  G1: IS_delta >= 0
  G2: OOS_delta > 0
  G3: WF_per_trade = (oos_delta/n_oos_removed) / (is_delta/n_is_removed) >= 0.70
  G4: sub-window hurt <= 1/3
  G5: anchor no regression
"""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

# Note: full params.json overrides require crypto.lib import (sys.path="backtest" only).
# Instead pass strike_offset=2 (OTM-2 for puts, matching SAFE $2K tier) directly.

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 15)

SW_BOUNDS = [
    (dt.date(2025,  1,  2), dt.date(2025,  5, 30)),
    (dt.date(2025,  6,  2), dt.date(2025, 10, 31)),
    (dt.date(2025, 11,  3), dt.date(2026,  5,  7)),
]

ANCHOR_DATES = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

COMMON = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    midday_trendline_gate=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20,
    vix_bear_hard_cap=23.0,
    min_triggers_bear=1,
    min_triggers_bull=2,
    profit_lock_threshold_pct=0.05,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
    initial_equity=2000.0,   # SAFE account -- $600 cap/trade, qty capped to 3-7
    strike_offset=2,          # OTM-2 for puts (positive = OTM in orchestrator convention)
)

BASELINE  = dict(COMMON, require_bearish_fill_bar=False)
CANDIDATE = dict(COMMON, require_bearish_fill_bar=True)


def run_period(kwargs, start, end):
    r = run_backtest(spy, vix, start_date=start, end_date=end, **kwargs)
    trades = r.trades
    n     = len(trades)
    total = sum(t.dollar_pnl for t in trades)
    wins  = sum(1 for t in trades if t.dollar_pnl > 0)
    bears = [t for t in trades if t.side == "P"]
    bulls = [t for t in trades if t.side == "C"]
    wr    = wins / n if n else 0.0
    return {"n": n, "total": total, "wr": wr,
            "n_bears": len(bears), "n_bulls": len(bulls),
            "bear_total": sum(t.dollar_pnl for t in bears),
            "bull_total": sum(t.dollar_pnl for t in bulls),
            "trades": trades}


def stats_line(label, s):
    return (f"{label}: n={s['n']:3d}({s['n_bears']}B+{s['n_bulls']}C) "
            f"total={s['total']:+.0f}  WR={s['wr']:.1%}  "
            f"bear={s['bear_total']:+.0f}  bull={s['bull_total']:+.0f}")


print("Running baseline IS ...")
bas_is  = run_period(BASELINE,  IS_S,  IS_E)
print("Running candidate IS ...")
cnd_is  = run_period(CANDIDATE, IS_S,  IS_E)
print("Running baseline OOS ...")
bas_oos = run_period(BASELINE,  OOS_S, OOS_E)
print("Running candidate OOS ...")
cnd_oos = run_period(CANDIDATE, OOS_S, OOS_E)

print()
print("=" * 75)
print("SAFE FILL-BAR DIRECTION GATE A/B TEST")
print("Gate: require_bearish_fill_bar (block bear if fill bar closes BULLISH)")
print("=" * 75)
print()
print(stats_line("BASELINE IS ", bas_is))
print(stats_line("CANDIDATE IS", cnd_is))
print()
print(stats_line("BASELINE OOS ", bas_oos))
print(stats_line("CANDIDATE OOS", cnd_oos))

is_delta  = cnd_is["total"]  - bas_is["total"]
oos_delta = cnd_oos["total"] - bas_oos["total"]
n_is_removed  = bas_is["n_bears"]  - cnd_is["n_bears"]
n_oos_removed = bas_oos["n_bears"] - cnd_oos["n_bears"]

print()
print(f"IS_delta  = {is_delta:+.0f}  (removed {n_is_removed} IS bears)")
print(f"OOS_delta = {oos_delta:+.0f}  (removed {n_oos_removed} OOS bears)")

print()
print("--- Sub-window analysis ---")
sw_hurts = 0
for i, (sw_s, sw_e) in enumerate(SW_BOUNDS, 1):
    sb = run_period(BASELINE,  sw_s, sw_e)
    sc = run_period(CANDIDATE, sw_s, sw_e)
    delta = sc["total"] - sb["total"]
    hurt  = delta < -100
    sw_hurts += int(hurt)
    tag = "HURT" if hurt else "OK"
    print(f"  SW{i} {sw_s}..{sw_e}: baseline={sb['total']:+.0f}"
          f"  cand={sc['total']:+.0f}  delta={delta:+.0f}  [{tag}]")

print()
print("--- Anchor check ---")
base_anchor = [t for t in bas_is["trades"] if t.entry_time_et.date() in ANCHOR_DATES]
cand_anchor = [t for t in cnd_is["trades"] if t.entry_time_et.date() in ANCHOR_DATES]
base_anc_pnl = sum(t.dollar_pnl for t in base_anchor)
cand_anc_pnl = sum(t.dollar_pnl for t in cand_anchor)
anchor_delta = cand_anc_pnl - base_anc_pnl
print(f"  Baseline anchor: n={len(base_anchor)} total={base_anc_pnl:+.0f}")
print(f"  Candidate anchor: n={len(cand_anchor)} total={cand_anc_pnl:+.0f}")
print(f"  Anchor delta: {anchor_delta:+.0f}")
g5_pass = anchor_delta >= -200

if n_is_removed > 0 and is_delta != 0:
    per_is  = is_delta  / n_is_removed
    per_oos = (oos_delta / n_oos_removed) if n_oos_removed > 0 else float("nan")
    wf = per_oos / per_is if (per_is != 0 and n_oos_removed > 0) else float("nan")
else:
    per_is = per_oos = wf = float("nan")

g1_pass = is_delta  >= 0
g2_pass = oos_delta >  0
g3_pass = (wf == wf) and wf >= 0.70
g4_pass = sw_hurts  <= 1

print()
print("=" * 75)
print("OP-22 GATE RESULTS")
print("=" * 75)
print(f"  [{'PASS' if g1_pass else 'FAIL'}] G1 IS_delta:     {is_delta:+.0f}  (>= 0)")
print(f"  [{'PASS' if g2_pass else 'FAIL'}] G2 OOS_delta:    {oos_delta:+.0f}  (> 0)")
wf_str = f"{wf:.3f}" if wf == wf else "n/a"
print(f"  [{'PASS' if g3_pass else 'FAIL'}] G3 WF_per_trade: {wf_str}  (>= 0.70)")
print(f"         per_is={per_is:.1f}/trade  per_oos={per_oos:.1f}/trade"
      f"  n_is_removed={n_is_removed}  n_oos_removed={n_oos_removed}")
print(f"  [{'PASS' if g4_pass else 'FAIL'}] G4 SW_hurt:      {sw_hurts}/3  (<= 1/3)")
print(f"  [{'PASS' if g5_pass else 'FAIL'}] G5 anchor:       {anchor_delta:+.0f}")

all_pass = g1_pass and g2_pass and g3_pass and g4_pass and g5_pass
verdict = "RATIFY" if all_pass else "REJECT"
print()
print(f"VERDICT: {verdict}")
