"""
AGGRESSIVE_MIDDAY_GATE_DESIGN (9b619cd2)

Safe account has midday_trendline_gate=True. Aggressive has midday_trendline_gate=False.
Question: with block_level_rejection=True already active, does adding midday_trendline_gate=True
to Aggressive provide incremental value, or is the effect redundant/zero?

Mechanism: midday_trendline_gate blocks TRENDLINE-ONLY entries in 11:30-14:00 ET.
With block_level_rejection=True, all level_rejection entries are already blocked.
So midday gate would only affect trendline-only entries in the midday window.
If Aggressive's trendline-only midday entries are already filtered by block_level_rejection
being broader OR if those midday entries are actually profitable for Aggressive → gate should stay OFF.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

# Aggressive production params (post-Rank35, midday_gate=False is baseline)
AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    tp1_premium_pct=0.75,                # C14 fix: must match production (default is 0.30)
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_max": 30.0},
)

# Pop params_overrides to avoid double-kwarg conflict
AGG_BASE_KW = {k: v for k, v in AGG_BASE_KWARGS.items() if k != "params_overrides"}
AGG_OVERRIDES = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}

# Candidate: same but midday_trendline_gate=True
AGG_CAND_KW = dict(AGG_BASE_KW)
AGG_CAND_KW["midday_trendline_gate"] = True


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _anchor_ok(cand_bd, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = cand_bd.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _time_bucket(t):
    et = t.entry_time_et
    if getattr(et, "tzinfo", None):
        et = et.replace(tzinfo=None)
    h, m = et.hour, et.minute
    minutes = h * 60 + m
    if minutes < 11 * 60 + 30:
        return "OPEN/AM (09:35-11:30)"
    if minutes < 14 * 60:
        return "MIDDAY (11:30-14:00)"
    return "AFTERNOON (14:00+)"


def _is_tl_only(t):
    triggers = getattr(t, "triggers_fired", [])
    if isinstance(triggers, str):
        import json
        try:
            triggers = json.loads(triggers)
        except Exception:
            triggers = [triggers]
    return triggers == ["trendline_rejection"] or triggers == ["trendline_rejection".strip()]


if __name__ == "__main__":
    print("=" * 90)
    print("AGGRESSIVE_MIDDAY_GATE_DESIGN (9b619cd2)")
    print("Baseline: midday_trendline_gate=False  |  Candidate: midday_trendline_gate=True")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Baseline composition first: understand what fires in midday
    print("\n[BASELINE IS COMPOSITION — MIDDAY WINDOW BREAKDOWN]")
    is_base = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, params_overrides=AGG_OVERRIDES, **AGG_BASE_KW)
    is_bp   = _pnl(is_base.trades)
    is_bd   = _by_date(is_base.trades)
    print(f"  IS trades: n={len(is_base.trades)} pnl={is_bp:+.0f}")

    midday_tl_only = [t for t in is_base.trades if _time_bucket(t) == "MIDDAY (11:30-14:00)" and _is_tl_only(t)]
    midday_other   = [t for t in is_base.trades if _time_bucket(t) == "MIDDAY (11:30-14:00)" and not _is_tl_only(t)]
    am_trades      = [t for t in is_base.trades if _time_bucket(t) == "OPEN/AM (09:35-11:30)"]
    pm_trades      = [t for t in is_base.trades if _time_bucket(t) == "AFTERNOON (14:00+)"]

    print(f"\n  Time bucket breakdown:")
    print(f"    AM (09:35-11:30):  n={len(am_trades):3}  pnl={_pnl(am_trades):+.0f}")
    print(f"    MIDDAY TL-only:    n={len(midday_tl_only):3}  pnl={_pnl(midday_tl_only):+.0f}  <-- gate would block these")
    print(f"    MIDDAY non-TL:     n={len(midday_other):3}  pnl={_pnl(midday_other):+.0f}  <-- gate would keep these")
    print(f"    PM (14:00+):       n={len(pm_trades):3}  pnl={_pnl(pm_trades):+.0f}")

    if midday_tl_only:
        avg = _pnl(midday_tl_only) / len(midday_tl_only)
        wr = sum(1 for t in midday_tl_only if t.dollar_pnl > 0) / len(midday_tl_only)
        print(f"\n  MIDDAY TL-only trades (gate would block):")
        print(f"    WR={wr:.1%}  avg={avg:+.0f}/trade")
        for t in midday_tl_only:
            d = _date(t)
            print(f"    {t.entry_time_et}  pnl={t.dollar_pnl:+.0f}  date={d}")
    else:
        print(f"\n  MIDDAY TL-only trades: ZERO (block_level_rejection may already prevent these)")
        print(f"  -> midday_trendline_gate would have NO EFFECT if n=0")

    # Full IS/OOS comparison
    print("\n[FULL IS COMPARISON]")
    is_cand = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, params_overrides=AGG_OVERRIDES, **AGG_CAND_KW)
    is_cp   = _pnl(is_cand.trades)
    is_cd   = _by_date(is_cand.trades)
    is_delta = is_cp - is_bp
    print(f"  BASELINE: n={len(is_base.trades)} pnl={is_bp:+.0f}")
    print(f"  CANDIDATE: n={len(is_cand.trades)} pnl={is_cp:+.0f} delta={is_delta:+.0f}")
    anchor_is = _anchor_ok(is_cd, is_bd)
    print(f"  Anchor check: {'OK' if anchor_is else 'FAIL'}")

    print("\n[OOS COMPARISON]")
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=AGG_OVERRIDES, **AGG_BASE_KW)
    oos_cand = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, params_overrides=AGG_OVERRIDES, **AGG_CAND_KW)
    oos_bp = _pnl(oos_base.trades)
    oos_cp = _pnl(oos_cand.trades)
    oos_delta = oos_cp - oos_bp
    n_is  = len(is_base.trades)
    n_oos = len(oos_base.trades)
    wf = (oos_delta / n_oos) / (is_delta / n_is) if is_delta != 0 and n_oos > 0 else 0.0
    print(f"  BASELINE: n={n_oos} pnl={oos_bp:+.0f}")
    print(f"  CANDIDATE: n={len(oos_cand.trades)} pnl={oos_cp:+.0f} delta={oos_delta:+.0f}")
    print(f"  WF_norm: {wf:.3f}")
    oos_positive = oos_delta > 0

    # OOS blocked trades
    print("\n[BLOCKED OOS TRADES (what would be removed by adding the gate)]")
    oos_base_et = [(t.entry_time_et, t.dollar_pnl, getattr(t, "entry_vix", 0)) for t in oos_base.trades]
    oos_cand_et = set(t.entry_time_et for t in oos_cand.trades)
    oos_blocked = [(et, pnl, vix) for et, pnl, vix in oos_base_et if et not in oos_cand_et]
    if not oos_blocked:
        print("  ZERO blocked OOS trades — gate has no effect on Aggressive OOS")
    for et, pnl, vix in oos_blocked:
        print(f"  {et}  VIX={vix:.1f}  pnl={pnl:+.0f}")

    # Sub-window stability
    print("\n[IS SUB-WINDOW STABILITY]")
    print(f"  {'Window':20}  {'BASE_n':>6}  {'CAND_n':>6}  {'BASE_pnl':>9}  {'CAND_pnl':>9}  {'delta':>7}  {'verdict':>8}")
    print("  " + "-" * 80)
    sub_hurts = 0
    sub_helps = 0
    sub_neutral = 0
    for label, s, e in IS_SUBWINDOWS:
        b = run_backtest(spy_df, vix_df, start_date=s, end_date=e, params_overrides=AGG_OVERRIDES, **AGG_BASE_KW)
        c = run_backtest(spy_df, vix_df, start_date=s, end_date=e, params_overrides=AGG_OVERRIDES, **AGG_CAND_KW)
        bp = _pnl(b.trades)
        cp = _pnl(c.trades)
        d = cp - bp
        verdict = "HURT" if d < -100 else ("HELP" if d > 100 else "NEUTRAL")
        if verdict == "HURT":
            sub_hurts += 1
        elif verdict == "HELP":
            sub_helps += 1
        else:
            sub_neutral += 1
        print(f"  {label:20}  {len(b.trades):>6}  {len(c.trades):>6}  {bp:>+9.0f}  {cp:>+9.0f}  {d:>+7.0f}  {verdict:>8}")
    print(f"\n  HURT={sub_hurts} HELP={sub_helps} NEUTRAL={sub_neutral}")
    sub_stable = sub_hurts == 0

    # Final verdict
    print("\n" + "=" * 90)
    print("FINAL VERDICT")
    print("=" * 90)
    wf_pass = wf >= 0.70
    print(f"\n  OOS positive: {oos_positive} (delta={oos_delta:+.0f})")
    print(f"  WF >= 0.70:   {wf_pass} (WF={wf:.3f})")
    print(f"  Anchor OK:    {anchor_is}")
    print(f"  Sub-window stable: {sub_stable}")
    all_pass = oos_positive and wf_pass and anchor_is and sub_stable
    print(f"\n  CANDIDATE STATUS: {'PASS - file A/B scorecard' if all_pass else 'FAIL/NO-EFFECT - gate stays OFF'}")
    if not oos_blocked and is_delta == 0:
        print(f"\n  CONCLUSION: block_level_rejection=True already removes all trendline-only midday entries")
        print(f"  in Aggressive. midday_trendline_gate=True has ZERO incremental effect.")
        print(f"  -> Aggressive midday gate stays OFF (confirmed redundant).")
    elif all_pass:
        print(f"\n  RECOMMENDATION: Add midday_trendline_gate=True to Aggressive params")
    else:
        print(f"\n  RECOMMENDATION: Keep midday_trendline_gate=False for Aggressive (gate hurts or no-effect)")

    print("\nANALYSIS COMPLETE.")
