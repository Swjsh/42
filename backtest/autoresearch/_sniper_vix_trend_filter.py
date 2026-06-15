"""SNIPER VIX-trend regime filter diagnostic.

MOTIVATION (L73):
  The VIX>=18 grinder passed full-window gates but FAILED OOS walk-forward
  (IS=$4,130 vs OOS=-$833, WF ratio=-0.224). Root cause: VIX level (>=18)
  alone is insufficient — VIX CHARACTER (trending vs spike-and-revert) is
  the true discriminator.

  The IS window (Jan-Oct 2025) was dominated by trending high-VIX.
  OOS F1+F2 (Nov 2025 - Feb 2026) = spike-and-revert high-VIX = -$1,713.
  OOS F3 (Mar-Apr 2026, tariff crash) = trending high-VIX = +$911.

HYPOTHESIS:
  Adding `prior_day_VIX > prior_5d_avg_VIX` (VIX is above its 5-day avg,
  indicating escalating rather than just elevated) eliminates most of the
  F1+F2 damage while preserving IS and F3 performance.

WHAT THIS SCRIPT DOES:
  1. Runs primary candidate on full window (2025-01..2026-05-22)
  2. For each trade, tags it: VIX_ESCALATING (above 5d avg) vs VIX_DECLINING
  3. Reports WR/P&L split between the two regimes
  4. Simulates "joint filter" result: VIX>=18 AND VIX_above_5d_avg
  5. Runs IS/OOS split with joint filter to check WF improvement

OUTPUT:
  Console table + autoresearch/_state/sniper_vix_trend_results.json

CLI:
  python autoresearch/_sniper_vix_trend_filter.py
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)
IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 10, 31)
OOS_START = dt.date(2025, 11, 1)
OOS_END = dt.date(2026, 5, 22)

OUT_JSON = REPO / "autoresearch" / "_state" / "sniper_vix_trend_results.json"

VIX_LOWER = 18
VIX_TREND_WINDOW = 5  # rolling days for VIX average

PRIMARY_COMBO = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "strike_offset": 1,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.30,
    "tp1_qty_fraction": 0.5,
    "runner_target_pct": 2.0,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.08,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}


def _build_vix_maps(vix_df: pd.DataFrame, trade_dates: list[dt.date]) -> tuple[dict, dict]:
    """Return (prior_close_map, prior_5d_avg_map) for each trade date."""
    vix_by_date = (
        vix_df.groupby(vix_df["timestamp_et"].dt.date)["close"]
        .last()
        .to_dict()
    )
    sorted_vix_days = sorted(vix_by_date.keys())
    vix_sorted_vals = [vix_by_date[d] for d in sorted_vix_days]

    prior_close: dict[dt.date, float] = {}
    prior_5d_avg: dict[dt.date, float] = {}

    for trade_date in trade_dates:
        idx = bisect.bisect_left(sorted_vix_days, trade_date) - 1
        if idx < 0:
            prior_close[trade_date] = 15.0
            prior_5d_avg[trade_date] = 15.0
            continue
        prior_close[trade_date] = float(vix_sorted_vals[idx])
        # 5-day average: average of up to 5 prior VIX closes
        start_idx = max(0, idx - VIX_TREND_WINDOW + 1)
        window_vals = vix_sorted_vals[start_idx:idx + 1]
        prior_5d_avg[trade_date] = float(mean(window_vals)) if window_vals else 15.0

    return prior_close, prior_5d_avg


def _sharpe(day_pnl_map: dict) -> float:
    vals = list(day_pnl_map.values())
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    variance = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    std = math.sqrt(variance)
    return (m / std) * math.sqrt(252) if std > 0 else 0.0


def _run_with_vix_trend(
    spy_full: pd.DataFrame,
    prior_close_map: dict,
    prior_5d_avg_map: dict,
    trade_dates: list[dt.date],
    combo_dict: dict,
    window_start: dt.date,
    window_end: dt.date,
    require_vix_escalating: bool,
) -> dict:
    """Run SNIPER with VIX>=18 and optionally VIX_above_5d_avg filter."""
    from autoresearch.sniper_evaluator import SniperCombo
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    from lib.sniper_detector import SniperParams, compute_levels, detect_sniper_break

    combo = SniperCombo(**{k: v for k, v in combo_dict.items() if k in SniperCombo.__dataclass_fields__})
    params = SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )

    all_trades: list[dict] = []
    day_pnl_map: dict[dt.date, float] = {}
    skipped_low = skipped_trend = 0

    for date_et in trade_dates:
        if date_et < window_start or date_et > window_end:
            continue

        vix_prev = prior_close_map.get(date_et, 15.0)
        vix_5d = prior_5d_avg_map.get(date_et, 15.0)

        if vix_prev < VIX_LOWER:
            skipped_low += 1
            continue

        if require_vix_escalating and vix_prev < vix_5d:
            skipped_trend += 1
            continue

        day_bars = spy_full[
            (spy_full["timestamp_et"].dt.date == date_et)
            & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
        ].reset_index(drop=True)
        if day_bars.empty:
            continue

        first_ts = day_bars["timestamp_et"].iloc[0]
        levels = compute_levels(spy_full, first_ts, params)
        if not levels:
            day_pnl_map[date_et] = 0.0
            continue

        pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
        combined = pd.concat([pre_bars, day_bars], ignore_index=True)
        day_offset = len(pre_bars)
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

        day_pnl = 0.0
        for i in range(len(day_bars)):
            bar_idx = day_offset + i
            bar = combined.iloc[bar_idx]
            signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
            if signal is None or signal.direction != "short":
                continue
            entry_spot = float(signal.entry_price)
            strike = round(entry_spot) + combo.strike_offset
            fill = simulate_trade_real(
                entry_bar_idx=bar_idx, entry_bar=bar, spy_df=combined, ribbon_df=ribbon_df,
                rejection_level=signal.level.price, triggers_fired=["sniper_level_break"],
                side="P", qty=combo.qty, setup="SNIPER_LEVEL_BREAK",
                levels_active=[L.price for L in levels if L.tier == "Active"],
                levels_carry=[L.price for L in levels if L.tier == "Carry"],
                use_tiered_exits=True, strike_override=int(strike),
                premium_stop_pct=combo.premium_stop_pct,
                profit_lock_threshold_pct=combo.profit_lock_threshold_pct,
                profit_lock_stop_offset_pct=combo.profit_lock_stop_offset_pct,
            )
            if fill is None:
                break
            trade_pnl = float(fill.dollar_pnl or 0.0)
            all_trades.append({
                "date": date_et.isoformat(),
                "dollar_pnl": trade_pnl,
                "vix_prev": round(vix_prev, 2),
                "vix_5d_avg": round(vix_5d, 2),
                "vix_escalating": vix_prev >= vix_5d,
            })
            day_pnl = trade_pnl
            break

        day_pnl_map[date_et] = day_pnl

    wide_pnl = round(sum(t["dollar_pnl"] for t in all_trades), 2)
    n = len(all_trades)
    wr = round(sum(1 for t in all_trades if t["dollar_pnl"] > 0) / n, 3) if n else 0.0
    sharpe = _sharpe(day_pnl_map)

    q_map: dict[str, float] = defaultdict(float)
    for t in all_trades:
        d = dt.date.fromisoformat(t["date"])
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        q_map[q] += t["dollar_pnl"]
    pos_q = sum(1 for v in q_map.values() if v > 0)

    return {
        "wide_pnl": wide_pnl, "n": n, "wr": wr, "sharpe": round(sharpe, 3),
        "pos_q": pos_q, "q_count": len(q_map),
        "skipped_low": skipped_low, "skipped_trend": skipped_trend,
        "quarter_pnl": {k: round(v, 2) for k, v in sorted(q_map.items())},
        "trades": all_trades,
    }


def main() -> None:
    from autoresearch import runner as _runner
    import pytz

    print("=" * 70)
    print("SNIPER VIX-Trend Regime Filter Diagnostic")
    print("=" * 70)
    print(f"Primary candidate: off=1, stp=-10%, tp1=30%, run=2.0, lk=5%/8%")
    print(f"Test: VIX>=18 vs VIX>=18 AND VIX>5d_avg (escalating regime)")
    print()

    print("Loading SPY + VIX data...", end=" ", flush=True)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    for df in (spy_full, vix_full):
        df["timestamp_et"] = (
            pd.to_datetime(df["timestamp_et"], utc=True)
            .dt.tz_convert(pytz.timezone("US/Eastern"))
            .dt.tz_localize(None)
        )
    print("done")

    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    trade_dates = [d for d in all_dates if WIDE_START <= d <= WIDE_END]
    prior_close_map, prior_5d_avg_map = _build_vix_maps(vix_full, trade_dates)
    print(f"Trade dates: {len(trade_dates)}")
    print()

    # ── Step 1: Run baseline (VIX>=18 only) over full window ──
    print("Step 1: Baseline VIX>=18 (full window)...", end=" ", flush=True)
    base = _run_with_vix_trend(
        spy_full, prior_close_map, prior_5d_avg_map, trade_dates,
        PRIMARY_COMBO, WIDE_START, WIDE_END, require_vix_escalating=False)
    print(f"done  n={base['n']}  pnl=${base['wide_pnl']:,.0f}  wr={base['wr']:.1%}")

    # ── Step 2: Regime stratification on baseline trades ──
    print()
    print("Step 2: Regime stratification (VIX escalating vs declining):")
    esc = [t for t in base["trades"] if t["vix_escalating"]]
    dec = [t for t in base["trades"] if not t["vix_escalating"]]

    esc_pnl = sum(t["dollar_pnl"] for t in esc)
    dec_pnl = sum(t["dollar_pnl"] for t in dec)
    esc_wr = sum(1 for t in esc if t["dollar_pnl"] > 0) / len(esc) if esc else 0
    dec_wr = sum(1 for t in dec if t["dollar_pnl"] > 0) / len(dec) if dec else 0

    print(f"  VIX escalating (VIX > 5d avg):  n={len(esc):>3}  pnl=${esc_pnl:>8,.0f}  wr={esc_wr:.1%}")
    print(f"  VIX declining  (VIX <= 5d avg): n={len(dec):>3}  pnl=${dec_pnl:>8,.0f}  wr={dec_wr:.1%}")
    print()

    # Show the 10 worst declining trades for diagnosis
    dec_losers = sorted(dec, key=lambda t: t["dollar_pnl"])[:10]
    if dec_losers:
        print("  10 worst VIX-DECLINING trades:")
        for t in dec_losers:
            print(f"    {t['date']}  pnl=${t['dollar_pnl']:>8,.0f}  "
                  f"vix={t['vix_prev']:.1f}  5d_avg={t['vix_5d_avg']:.1f}  "
                  f"delta={t['vix_prev']-t['vix_5d_avg']:+.1f}")
    print()

    # ── Step 3: Joint filter (VIX>=18 AND escalating) full window ──
    print("Step 3: Joint filter VIX>=18 AND VIX>5d_avg (full window)...", end=" ", flush=True)
    joint = _run_with_vix_trend(
        spy_full, prior_close_map, prior_5d_avg_map, trade_dates,
        PRIMARY_COMBO, WIDE_START, WIDE_END, require_vix_escalating=True)
    print(f"done  n={joint['n']}  pnl=${joint['wide_pnl']:,.0f}  wr={joint['wr']:.1%}")
    print()

    # ── Step 4: IS/OOS split with joint filter ──
    print("Step 4: IS/OOS walk-forward with joint filter...")
    is_joint = _run_with_vix_trend(
        spy_full, prior_close_map, prior_5d_avg_map, trade_dates,
        PRIMARY_COMBO, IS_START, IS_END, require_vix_escalating=True)
    oos_joint = _run_with_vix_trend(
        spy_full, prior_close_map, prior_5d_avg_map, trade_dates,
        PRIMARY_COMBO, OOS_START, OOS_END, require_vix_escalating=True)

    wf_ratio = (oos_joint["sharpe"] / is_joint["sharpe"]
                if is_joint["sharpe"] != 0 else 0.0)
    wf_pass = wf_ratio >= 0.50

    print()

    # ── Summary comparison table ──
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  {'Filter':<30} {'n':>5}  {'pnl':>9}  {'wr':>6}  {'sharpe':>8}  {'+q':>5}")
    print("  " + "-" * 65)

    rows = [
        ("Baseline VIX>=18 (full)", base),
        ("Joint VIX>=18+escalating (full)", joint),
        ("Joint IS (2025-01..2025-10)", is_joint),
        ("Joint OOS (2025-11..2026-05)", oos_joint),
    ]
    for label, r in rows:
        print(f"  {label:<30} {r['n']:>5}  ${r['wide_pnl']:>8,.0f}  "
              f"{r['wr']:>6.1%}  {r['sharpe']:>8.3f}  "
              f"{r['pos_q']:>2}/{r['q_count']:<2}")

    print()
    print("Walk-forward gate (OOS_Sharpe / IS_Sharpe >= 0.50):")
    print(f"  IS  Sharpe: {is_joint['sharpe']:.3f}")
    print(f"  OOS Sharpe: {oos_joint['sharpe']:.3f}")
    print(f"  WF ratio:   {wf_ratio:.3f}  ->  {'PASS' if wf_pass else 'FAIL'}")
    print()

    # Hypothesis verdict
    print("Hypothesis verdict:")
    if esc_wr >= 0.55 and dec_wr < 0.45 and abs(dec_pnl) > 0.5 * abs(esc_pnl):
        print("  CONFIRMED — VIX escalating vs declining is a significant discriminator.")
        print(f"  Escalating: WR={esc_wr:.1%}, P&L=${esc_pnl:,.0f}")
        print(f"  Declining:  WR={dec_wr:.1%}, P&L=${dec_pnl:,.0f}")
    elif esc_wr > dec_wr + 0.05:
        print("  PARTIAL — Some signal. Escalating WR > Declining WR but modest gap.")
    else:
        print("  NOT CONFIRMED — Escalating vs declining not a clear discriminator at this threshold.")

    print()
    print("Quarter breakdown (joint filter, full window):")
    for q, v in sorted(joint["quarter_pnl"].items()):
        print(f"  {q}: {'+' if v >= 0 else ''}{v:,.0f}  [{'PASS' if v >= 0 else 'FAIL'}]")

    # ── Save ──
    payload = {
        "run_at": dt.datetime.now().isoformat(),
        "combo": PRIMARY_COMBO,
        "vix_lower": VIX_LOWER,
        "vix_trend_window": VIX_TREND_WINDOW,
        "window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
        "baseline_vix18": {k: v for k, v in base.items() if k != "trades"},
        "regime_split": {
            "escalating": {"n": len(esc), "pnl": round(esc_pnl, 2), "wr": round(esc_wr, 3)},
            "declining": {"n": len(dec), "pnl": round(dec_pnl, 2), "wr": round(dec_wr, 3)},
        },
        "joint_filter": {k: v for k, v in joint.items() if k != "trades"},
        "is_joint": {k: v for k, v in is_joint.items() if k != "trades"},
        "oos_joint": {k: v for k, v in oos_joint.items() if k != "trades"},
        "wf_ratio": round(wf_ratio, 3),
        "wf_pass": wf_pass,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved to {OUT_JSON}")


if __name__ == "__main__":
    main()
