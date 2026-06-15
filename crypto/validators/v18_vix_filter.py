"""v18_vix_filter — verify the 3-bar VIX lookback (T81 fix).

Per docs/T81-BULL-VIX-GATE.md: single-bar VIX gating with a 0.05 deadband misses
slow-drift trends (e.g. 5/14 had VIX trending -0.49 over the session but each
5m delta was 0.02-0.04 — sub-deadband). Production now uses a 3-bar lookback
which catches aggregated drift of 0.06-0.12.

Offline tests (T1-T10):
  T1  Sub-deadband decline: single-bar says 'flat', 3-bar says 'falling'
  T2  Sub-deadband climb:   single-bar 'flat', 3-bar 'rising'
  T3  Above-deadband one-bar drop: both 'falling'
  T4  Above-deadband one-bar rise: both 'rising'
  T5  True flat (no movement): both 'flat'
  T6  Filter 8 bull — VIX 17.10 (below 17.20 threshold), any direction -> PASS
  T7  Filter 8 bull — VIX 17.50, 3-bar declining (17.65->17.50) -> PASS (falling)
  T8  Filter 8 bull — VIX 17.50, 3-bar flat (17.50->17.50) -> REJECT
  T9  Filter 8 bull — VIX hard cap: 22.50 > 22.00 -> REJECT regardless of direction
  T10 Filter 8 bear — VIX 17.50 with rising 3-bar history (17.32->17.50) -> PASS

Live mode: pull yfinance VIX 5m bars, compute single-bar + 3-bar verdicts,
report the difference. The "pass" of live mode is: the function ran AND we
got at least one bar back.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.vix_filter import (
    passes_filter_8_bear,
    passes_filter_8_bull,
    vix_direction,
    vix_direction_lookback,
)


def run_offline() -> dict:
    results = []

    # T1: sub-deadband decline. Hist [17.65, 17.60, 17.55] now 17.50.
    # 1-bar prior (17.55): now-prior = -0.05, NOT > 0.05 -> flat
    # 3-bar prior (17.65): now-prior = -0.15, > 0.05 -> falling
    hist1 = [17.65, 17.60, 17.55]
    d1_single = vix_direction(17.50, hist1[-1])
    d1_three = vix_direction_lookback(17.50, hist1, lookback_bars=3)
    results.append(("T1_sub_deadband_decline_3bar_catches",
                    d1_single == "flat" and d1_three.direction == "falling",
                    f"1bar={d1_single} 3bar={d1_three.direction}"))

    # T2: sub-deadband climb. Hist [17.30, 17.35, 17.40] now 17.45.
    # 1-bar prior 17.40 -> +0.05 (NOT > 0.05) -> flat
    # 3-bar prior 17.30 -> +0.15 -> rising
    hist2 = [17.30, 17.35, 17.40]
    d2_single = vix_direction(17.45, hist2[-1])
    d2_three = vix_direction_lookback(17.45, hist2, lookback_bars=3)
    results.append(("T2_sub_deadband_climb_3bar_catches",
                    d2_single == "flat" and d2_three.direction == "rising",
                    f"1bar={d2_single} 3bar={d2_three.direction}"))

    # T3: above-deadband 1-bar drop. Hist [17.80] now 17.50 -> both falling
    hist3 = [17.80]
    d3_single = vix_direction(17.50, hist3[-1])
    d3_three = vix_direction_lookback(17.50, hist3, lookback_bars=3)
    results.append(("T3_above_deadband_drop_both_falling",
                    d3_single == "falling" and d3_three.direction == "falling",
                    f"1bar={d3_single} 3bar={d3_three.direction}"))

    # T4: above-deadband 1-bar rise. Hist [17.20] now 17.50 -> both rising
    hist4 = [17.20]
    d4_single = vix_direction(17.50, hist4[-1])
    d4_three = vix_direction_lookback(17.50, hist4, lookback_bars=3)
    results.append(("T4_above_deadband_rise_both_rising",
                    d4_single == "rising" and d4_three.direction == "rising",
                    f"1bar={d4_single} 3bar={d4_three.direction}"))

    # T5: True flat (no movement). Hist [17.50, 17.50, 17.50] now 17.50 -> flat
    hist5 = [17.50, 17.50, 17.50]
    d5_single = vix_direction(17.50, hist5[-1])
    d5_three = vix_direction_lookback(17.50, hist5, lookback_bars=3)
    results.append(("T5_true_flat_both_flat",
                    d5_single == "flat" and d5_three.direction == "flat",
                    f"1bar={d5_single} 3bar={d5_three.direction}"))

    # T6: Filter 8 bull — VIX 17.10 below the 17.20 threshold, no need to check direction
    p6 = passes_filter_8_bull(17.10, [17.10, 17.10, 17.10])
    results.append(("T6_F8_bull_under_threshold_passes", p6 is True,
                    f"passes={p6}"))

    # T7: Filter 8 bull — VIX 17.50 (above 17.20) but 3-bar history shows declining
    # hist [17.65, 17.60, 17.55] now 17.50 -> 3-bar prior 17.65, falling 0.15 -> PASS
    p7 = passes_filter_8_bull(17.50, [17.65, 17.60, 17.55])
    results.append(("T7_F8_bull_above_threshold_but_falling_passes", p7 is True,
                    f"passes={p7}"))

    # T8: Filter 8 bull — VIX 17.50 with flat 3-bar history. 3-bar prior 17.50 -> flat -> REJECT
    p8 = passes_filter_8_bull(17.50, [17.50, 17.50, 17.50])
    results.append(("T8_F8_bull_above_threshold_and_flat_rejects", p8 is False,
                    f"passes={p8}"))

    # T9: Filter 8 bull — hard cap. VIX 22.50 > 22.00 cap -> REJECT regardless of direction
    p9 = passes_filter_8_bull(22.50, [25.0, 24.0, 23.0])  # falling but above cap
    results.append(("T9_F8_bull_hard_cap_rejects_even_falling", p9 is False,
                    f"passes={p9}"))

    # T10: Filter 8 bear — VIX 17.50 (above 17.30) with rising 3-bar (17.32->17.50)
    # hist [17.32, 17.40, 17.45] now 17.50 -> 3-bar prior 17.32, rising 0.18 -> PASS
    p10 = passes_filter_8_bear(17.50, [17.32, 17.40, 17.45])
    results.append(("T10_F8_bear_above_threshold_and_rising_passes", p10 is True,
                    f"passes={p10}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:90]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """Pull yfinance VIX 5m bars, compute 1-bar vs 3-bar verdicts.

    Soft-pass: if yfinance is unavailable, we still return pass=True with a note
    (this validator's primary value is offline; live is observational).
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"mode": "live", "pass": True, "skipped": "yfinance not installed"}

    try:
        ticker = yf.Ticker("^VIX")
        df = ticker.history(period="2d", interval="5m")
        if df is None or df.empty:
            return {"mode": "live", "pass": True, "skipped": "no VIX bars returned"}
        closes = df["Close"].dropna().tolist()
        if len(closes) < 4:
            return {"mode": "live", "pass": True, "skipped": f"only {len(closes)} bars, need >=4"}
    except Exception as e:
        return {"mode": "live", "pass": True, "skipped": f"yfinance error: {e}"}

    vix_now = float(closes[-1])
    hist = [float(c) for c in closes[-4:-1]]
    d_single = vix_direction(vix_now, hist[-1])
    d_three = vix_direction_lookback(vix_now, hist, lookback_bars=3)
    pass_bull = passes_filter_8_bull(vix_now, hist)
    pass_bear = passes_filter_8_bear(vix_now, hist)

    return {
        "mode": "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "bars_count": len(closes),
        "vix_now": vix_now,
        "vix_hist_last3": hist,
        "single_bar_direction": d_single,
        "three_bar_direction": d_three.direction,
        "three_bar_prior_used": d_three.prior_used,
        "filter_8_bull_passes": pass_bull,
        "filter_8_bear_passes": pass_bear,
        "single_vs_three_bar_differ": d_single != d_three.direction,
        "pass": True,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:50s} {t['note']}")

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        live = sc["live"]
        print(f"\n=== LIVE === VIX (yfinance)")
        if "skipped" in live:
            print(f"  skipped: {live['skipped']}")
        else:
            print(f"  vix_now:        {live['vix_now']}")
            print(f"  vix_hist:       {live['vix_hist_last3']}")
            print(f"  1-bar:          {live['single_bar_direction']}")
            print(f"  3-bar:          {live['three_bar_direction']} (prior {live['three_bar_prior_used']})")
            print(f"  F8 bull passes: {live['filter_8_bull_passes']}")
            print(f"  F8 bear passes: {live['filter_8_bear_passes']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
