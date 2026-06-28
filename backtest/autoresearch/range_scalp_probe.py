"""RANGE-SCALP first-slice real-fills probe.

Bounded question (ONE combo, ONE regime window):
    Does the shotgun_scalper **Tier-2 LEVEL_REJECT_LIVE** signal (a named-level
    mean-reversion fade) show **positive per-trade expectancy** under **real OPRA
    fills** over the recent range-bound regime (2026-05-21 .. 2026-06-26)?

Why this probe exists (conductor 2026-06-28):
    - The regime-diagnosis (analysis/self-audit/recency-regime-diagnosis-2026-06-28.md)
      confirmed a REGIME SHIFT to flat-ribbon / compressed-VIX grind. The
      regime-appropriate edge is mean-reversion level fade, NOT directional
      continuation.
    - That mechanism is ALREADY implemented as shotgun_scalper Tier-2
      LEVEL_REJECT_LIVE — so we REUSE the existing real-OPRA-fills machinery
      (run_shotgun_day / _simulate_trade_real / _build_auto_levels) rather than
      build a duplicate simulator.
    - EVALUATION YARDSTICK: per-trade expectancy / WR / total P&L. We deliberately
      do NOT use J `edge_capture` here: that metric is anchored on directional
      trend days (5/14 +$1208, 5/15 +$1400) and structurally auto-rejects any
      range/mean-reversion strategy (which cannot win on trend days). A
      regime-specific strategy needs a regime-matched yardstick.

Scope discipline (these are LATER slices, NOT this probe):
    - multi-combo sweep
    - explicit flat-ribbon/VIX regime gate (the WINDOW already IS the range
      regime per the diagnosis, so running Tier-2 on it approximates "Tier-2 in
      the range regime"; an explicit ribbon/VIX gate is a refinement)
    - IS / OOS / walk-forward

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_probe --smoke
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_probe
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

from autoresearch import runner as _runner
from autoresearch.shotgun_scalper_grinder import ShotgunCombo, run_shotgun_day

# Recent range regime window (per recency-regime-diagnosis-2026-06-28).
WINDOW_START = dt.date(2026, 5, 21)
WINDOW_END = dt.date(2026, 6, 26)

TIER_LEVEL_REJECT = 2  # shotgun_scalper detector Tier-2 LEVEL_REJECT_LIVE

# Range-scalp exit config (per the chef candidate: ITM strike, tight target/stop,
# single exit / no runner). ONE combo for this first probe.
RANGE_SCALP_COMBO = ShotgunCombo(
    vol_ratio_threshold=1.5,   # Tier-2 already requires >=1.5 internally
    strike_offset=1,           # ITM-1 (candidate: lower theta, better reversion capture)
    tp_premium_pct=0.30,       # tight near-term mean-reversion target
    stop_premium_pct=-0.20,    # tight stop (fill bar must show reversal)
    time_stop_min=15,
    chandelier_arm_pct=0.25,
    qty=3,
    tp1_qty_fraction=1.0,      # single exit
)

OUT_PATH = _REPO / "analysis" / "recommendations" / "range-scalp-probe-2026-06-28.json"


# The grinder's _runner.load_data master only covers through ~2026-05-22; the recent
# range window lives in a dedicated recent csv (same one recency_check concats).
RECENT_SPY_CSV = _REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-06-26.csv"


def _load_spy(start: dt.date, end: dt.date):
    import pandas as pd

    spy = pd.read_csv(RECENT_SPY_CSV)
    spy["timestamp_et"] = (
        pd.to_datetime(spy["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return spy


def _trading_days(spy, start: dt.date, end: dt.date) -> list[dt.date]:
    days = sorted(set(spy["timestamp_et"].dt.date.unique()))
    return [d for d in days if start <= d <= end]


def run_probe(start: dt.date, end: dt.date, combo: ShotgunCombo) -> dict:
    spy = _load_spy(start - dt.timedelta(days=5), end)  # pad for prior-day levels / pre-bars
    days = _trading_days(spy, start, end)

    opra_cache: dict = {}
    trades = []
    by_day: dict[str, float] = {}
    for d in days:
        day_trades = run_shotgun_day(d, spy, combo, opra_cache, tier_filter=TIER_LEVEL_REJECT)
        trades.extend(day_trades)
        by_day[d.isoformat()] = round(sum(t.dollar_pnl for t in day_trades), 2)

    pnls = [t.dollar_pnl for t in trades]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    total = round(sum(pnls), 2)
    expectancy = round(total / n, 2) if n else 0.0
    wr = round(wins / n, 3) if n else 0.0

    # Concentration check (OP-20 disclosure 6 / C4): a positive net driven by a
    # handful of days is fragile, not an edge.
    nz_days = {k: v for k, v in by_day.items() if v != 0.0}
    n_active_days = len(nz_days)
    n_losing_days = sum(1 for v in nz_days.values() if v < 0)
    top3 = sorted(nz_days.values(), reverse=True)[:3]
    top3_pct_of_net = round(100.0 * sum(top3) / total, 1) if total else None

    if n < 10:
        verdict = "INCONCLUSIVE"
    elif expectancy <= 0:
        verdict = "DRY"
    elif top3_pct_of_net is not None and top3_pct_of_net > 150.0:
        # net positive but concentration-fragile: worth the next (regime-gated) slice,
        # NOT a deploy-ready edge.
        verdict = "VEIN_CONCENTRATED"
    else:
        verdict = "VEIN"

    days_with_data = [d.isoformat() for d in days]
    return {
        "probe": "range_scalp_tier2_level_reject",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "dates_run": days_with_data,
        "n_dates": len(days_with_data),
        "combo": {
            "tier_filter": TIER_LEVEL_REJECT,
            "vol_ratio_threshold": combo.vol_ratio_threshold,
            "strike_offset": combo.strike_offset,
            "tp_premium_pct": combo.tp_premium_pct,
            "stop_premium_pct": combo.stop_premium_pct,
            "time_stop_min": combo.time_stop_min,
            "chandelier_arm_pct": combo.chandelier_arm_pct,
            "qty": combo.qty,
        },
        "results": {
            "n_trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": wr,
            "expectancy_per_trade_usd": expectancy,
            "total_pnl_usd": total,
            "mean_trade_usd": round(statistics.mean(pnls), 2) if n else 0.0,
            "median_trade_usd": round(statistics.median(pnls), 2) if n else 0.0,
            "worst_trade_usd": round(min(pnls), 2) if n else 0.0,
            "best_trade_usd": round(max(pnls), 2) if n else 0.0,
            "n_active_days": n_active_days,
            "n_losing_days": n_losing_days,
            "top3_day_pct_of_net": top3_pct_of_net,
            "by_day_pnl": by_day,
        },
        "method_disclosures": {
            "tiers_included": "Tier-2 LEVEL_REJECT_LIVE only (tier_filter=2)",
            "regime_gate_applied": "NO — first probe relies on the WINDOW already being the "
                                   "range regime (per recency-regime-diagnosis-2026-06-28). "
                                   "Explicit flat-ribbon/VIX gate is a later refinement.",
            "fill_model": "Real OPRA bars via _simulate_trade_real (NO Black-Scholes). "
                          "Slippage/half-spread NOT applied (Stage-5-class refinement).",
            "yardstick": "per-trade expectancy / WR / total P&L. J edge_capture deliberately "
                         "NOT used (anchored on directional trend days; auto-rejects range edges).",
            "ribbon": "run_shotgun_day uses a NaN ribbon_stub; Tier-2 LEVEL_REJECT does not "
                      "depend on the ribbon, so this does not bias Tier-2 detection.",
            "limitations": "ONE combo, no sweep, no IS/OOS. A VEIN verdict justifies building "
                           "the regime-gated multi-combo + IS/OOS slice next; a DRY verdict means "
                           "level-fade-via-Tier-2 is also dry in this regime.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="run a single day (first in window)")
    args = ap.parse_args()

    if args.smoke:
        spy = _load_spy(WINDOW_START - dt.timedelta(days=5), WINDOW_END)
        days = _trading_days(spy, WINDOW_START, WINDOW_END)
        if not days:
            print("SMOKE: no trading days with data in window")
            return 1
        d = days[0]
        opra_cache: dict = {}
        trades = run_shotgun_day(d, spy, RANGE_SCALP_COMBO, opra_cache, tier_filter=TIER_LEVEL_REJECT)
        print(f"SMOKE {d}: {len(trades)} Tier-2 trades, pnl={sum(t.dollar_pnl for t in trades):.2f}")
        return 0

    result = run_probe(WINDOW_START, WINDOW_END, RANGE_SCALP_COMBO)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    r = result["results"]
    print(f"VERDICT={result['verdict']} dates={result['n_dates']} "
          f"n={r['n_trades']} wr={r['win_rate']} "
          f"exp/tr=${r['expectancy_per_trade_usd']} total=${r['total_pnl_usd']}")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
