"""TBR_HIGH_VOL trailing realized-vol regime filter.

Tests whether TBR_HIGH_VOL edge is concentrated in HIGH-RV regimes
(persistent multi-week elevated realized vol) vs flat/calm periods.

Key finding from leaderboard #16:
  'Day-level VIX filter cannot fix multi-quarter concentration — TBR edge
   is driven by persistent multi-week trendline structure, not day-level
   VIX character. The correct future test is a trailing 60d realized-vol
   regime detector, not a VIX gate.'

Method:
  1. Aggregate 5m SPY bars to daily close (last bar of each RTH session)
  2. Compute trailing N-day annualized realized vol for windows 20, 40, 60
     RV_N = sqrt(252) × std(last N log daily returns)
  3. Compute IS percentile thresholds (p25, p50, p75) — IS calibration only
  4. Tag each TBR trade: LOW (<p25), MED (p25–p75), HIGH (>p75)
  5. Compare WR + expectancy per tier in IS and OOS
  6. Walk-forward: does IS HIGH-RV WR / exp carry to OOS HIGH-RV?

Hypothesis:
  IS Q2-2025 (April tariff shock) and OOS Q1-2026 (Jan-Mar tariff crash)
  are both persistent high-realized-vol regimes.  If TBR edge is
  regime-gated, HIGH-RV WF ratio should ≥ 0.50 and the concentration
  should be EXPLAINED (not removed) by the regime flag.

CLI::

    python -m autoresearch.tbr_rv_regime_filter
    python -m autoresearch.tbr_rv_regime_filter --window 60
    python -m autoresearch.tbr_rv_regime_filter --sweep        # test all 3 windows
    python -m autoresearch.tbr_rv_regime_filter --out analysis/recommendations/tbr_rv_regime.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from autoresearch.runner import load_data
from autoresearch.tbr_hv_real_fills_val import (
    DEFAULT_COMBO,
    _report,
    _run_tbr_hv_real_fills,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
    encoding="utf-8",
)
log = logging.getLogger(__name__)

IS_START = dt.date(2025, 1, 1)
IS_END = dt.date(2025, 9, 30)
OOS_START = dt.date(2025, 10, 1)
OOS_END = dt.date(2026, 5, 22)

# Best ITM-2 / stop=-35% combo from WF analysis (leaderboard #16)
BEST_COMBO = replace(DEFAULT_COMBO, strike_offset=-2, stop_premium_pct=-0.35)

# RV windows in trading days to sweep
RV_WINDOWS = [20, 40, 60]

# Annualisation factor
SQRT_252 = math.sqrt(252)


# ---------------------------------------------------------------------------
# Step 1 — build daily-close series from 5m bars
# ---------------------------------------------------------------------------

def _build_daily_closes(spy_df: pd.DataFrame) -> pd.Series:
    """Return last-bar-of-day close for each RTH session, indexed by date.

    Only considers bars at or after 09:30 ET to avoid pre-market outliers.
    """
    spy = spy_df.copy()
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], utc=False)
    try:
        if spy["timestamp_et"].dt.tz is not None:
            spy["timestamp_et"] = (
                spy["timestamp_et"]
                .dt.tz_convert("America/New_York")
                .dt.tz_localize(None)
            )
    except Exception:
        pass

    rth = spy[spy["timestamp_et"].dt.time >= dt.time(9, 30)].copy()
    rth["date"] = rth["timestamp_et"].dt.date
    daily = rth.groupby("date")["close"].last()
    return daily


# ---------------------------------------------------------------------------
# Step 2 — compute trailing realized vol
# ---------------------------------------------------------------------------

def _compute_rv_series(daily_close: pd.Series, window: int) -> pd.Series:
    """Return trailing-N-day annualized realized vol, indexed by date.

    RV = sqrt(252) × std(last N log daily returns).
    Requires window+1 prior closes; returns NaN where insufficient history.
    """
    log_returns = daily_close.apply(math.log).diff()  # ln(Ct/Ct-1)
    rv = log_returns.rolling(window=window, min_periods=window).std() * SQRT_252
    return rv


# ---------------------------------------------------------------------------
# Step 3 — compute IS percentile thresholds (no look-ahead)
# ---------------------------------------------------------------------------

def _compute_is_percentiles(
    rv_series: pd.Series,
    is_start: dt.date,
    is_end: dt.date,
) -> tuple[float, float, float]:
    """Compute (p25, p50, p75) of RV within IS window.  NaN rows excluded."""
    is_mask = (rv_series.index >= is_start) & (rv_series.index <= is_end)
    is_rv = rv_series[is_mask].dropna()
    if is_rv.empty:
        return (0.0, 0.0, 0.0)
    vals = sorted(is_rv.values)
    n = len(vals)
    p25 = vals[int(0.25 * n)]
    p50 = vals[int(0.50 * n)]
    p75 = vals[int(0.75 * n)]
    return (p25, p50, p75)


# ---------------------------------------------------------------------------
# Step 4 — tag each trade date with RV tier
# ---------------------------------------------------------------------------

def _tag_trades_by_rv(
    trades: list[dict],
    rv_by_date: dict[dt.date, float],
    p25: float,
    p75: float,
) -> list[dict]:
    """Return a copy of trades with 'rv_tier' added: 'HIGH' / 'MED' / 'LOW' / 'NA'."""
    tagged = []
    for t in trades:
        t = dict(t)
        date = dt.date.fromisoformat(t["date"])
        rv = rv_by_date.get(date)
        if rv is None or math.isnan(rv):
            t["rv_tier"] = "NA"
        elif rv > p75:
            t["rv_tier"] = "HIGH"
        elif rv >= p25:
            t["rv_tier"] = "MED"
        else:
            t["rv_tier"] = "LOW"
        t["rv_value"] = round(rv, 6) if (rv is not None and not math.isnan(rv)) else None
        tagged.append(t)
    return tagged


# ---------------------------------------------------------------------------
# Step 5 — per-tier stats + concentration
# ---------------------------------------------------------------------------

def _stats_subset(trades: list[dict]) -> dict:
    """Compute n, wr, exp, total_pnl, passes for a trade subset."""
    if not trades:
        return {"n": 0, "wr": 0.0, "exp": 0.0, "total_pnl": 0.0, "passes": False}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    total = sum(pnls)
    wr = len(wins) / len(pnls)
    exp = total / len(pnls)
    passes = len(trades) >= 10 and wr >= 0.55
    return {
        "n": len(trades),
        "wr": round(wr, 4),
        "exp": round(exp, 2),
        "total_pnl": round(total, 2),
        "passes": passes,
    }


def _concentration(trades: list[dict], total_pnl: float) -> dict:
    """Return per-quarter P&L and max-concentration fraction."""
    qpnl: dict[str, float] = defaultdict(float)
    qn: dict[str, int] = defaultdict(int)
    for t in trades:
        d = dt.date.fromisoformat(t["date"])
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        qpnl[q] += t["pnl"]
        qn[q] += 1
    if total_pnl == 0.0:
        max_q = ""
        max_pct = 0.0
    else:
        max_q = max(qpnl, key=lambda q: abs(qpnl[q]))
        max_pct = qpnl[max_q] / total_pnl * 100
    return {
        "by_quarter": {q: round(qpnl[q], 2) for q in sorted(qpnl)},
        "by_quarter_n": {q: qn[q] for q in sorted(qn)},
        "max_quarter": max_q,
        "max_pct": round(max_pct, 1),
    }


def _report_by_tier(
    trades_tagged: list[dict],
    window: int,
    thresholds: tuple[float, float, float],
    label: str,
) -> dict:
    """Print tier breakdown table and return summary dict."""
    p25, p50, p75 = thresholds
    by_tier = {"HIGH": [], "MED": [], "LOW": [], "NA": []}
    for t in trades_tagged:
        tier = t.get("rv_tier", "NA")
        by_tier.setdefault(tier, []).append(t)

    total_pnl = sum(t["pnl"] for t in trades_tagged)

    print(f"\n  {'-'*56}")
    print(f"  {label}  |  window={window}d  thresholds: p25={p25:.2%} p75={p75:.2%}")
    print(f"  {'-'*56}")
    print(f"  {'Tier':<8} {'N':>5} {'WR':>7} {'Exp':>8} {'Total':>10} {'%share':>8}")
    print(f"  {'-'*56}")

    tier_summaries: dict[str, dict] = {}
    for tier in ("HIGH", "MED", "LOW", "NA"):
        subset = by_tier[tier]
        s = _stats_subset(subset)
        tier_summaries[tier] = s
        tier_total = s["total_pnl"]
        share = (tier_total / total_pnl * 100) if total_pnl != 0.0 else 0.0
        pass_mark = "P" if s["passes"] else " "
        print(
            f"  {tier:<8} {s['n']:>5}  {s['wr']:>6.1%}  ${s['exp']:>7.2f}  ${tier_total:>9.2f}  {share:>7.1f}%  {pass_mark}"
        )

    all_s = _stats_subset(trades_tagged)
    print(f"  {'ALL':<8} {all_s['n']:>5}  {all_s['wr']:>6.1%}  ${all_s['exp']:>7.2f}  ${all_s['total_pnl']:>9.2f}  {'100.0%':>8}")

    # Concentration for HIGH tier
    if by_tier["HIGH"]:
        high_conc = _concentration(by_tier["HIGH"], tier_summaries["HIGH"]["total_pnl"])
        print(f"\n  HIGH-tier concentration: max quarter = {high_conc['max_quarter']} "
              f"({high_conc['max_pct']:.1f}% of HIGH-tier P&L)")
        print(f"  HIGH-tier by quarter: {high_conc['by_quarter']}")

    return {
        "all": all_s,
        "tiers": tier_summaries,
        "concentration": {
            tier: _concentration(by_tier[tier], tier_summaries[tier]["total_pnl"])
            for tier in ("HIGH", "MED", "LOW")
            if by_tier[tier]
        },
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_rv_regime_analysis(
    windows: list[int] | None = None,
    out_path: Path | None = None,
) -> dict:
    if windows is None:
        windows = RV_WINDOWS

    print("=" * 70)
    print("TBR_HIGH_VOL  Trailing Realized-Vol Regime Filter Analysis")
    print(f"IS : {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print(f"Combo: ITM-2, stop=-35%  (best from WF analysis)")
    print(f"Windows: {windows} trading days")
    print("=" * 70)

    # Load SPY bars for the full window (need extra lookback for RV warmup)
    warmup_start = dt.date(2024, 6, 1)  # extra 6 months before IS start for 60d warmup
    log.info("Loading SPY bars %s to %s for RV computation...", warmup_start, OOS_END)
    spy_full, _vix = load_data(IS_START, OOS_END)  # use existing IS_START; first 60d will be NaN (warm-up)

    daily_close = _build_daily_closes(spy_full)
    log.info("Daily closes computed: %d days (%s to %s)",
             len(daily_close), daily_close.index[0], daily_close.index[-1])

    # Compute RV series for each window
    rv_series: dict[int, pd.Series] = {}
    rv_by_date: dict[int, dict[dt.date, float]] = {}
    for w in windows:
        rv_series[w] = _compute_rv_series(daily_close, w)
        rv_by_date[w] = {d: float(v) for d, v in rv_series[w].items() if not math.isnan(float(v))}
        valid = sum(1 for v in rv_by_date[w].values() if not math.isnan(v))
        log.info("RV(%dd) computed: %d valid dates", w, valid)

    # Load IS and OOS trades (run once, reuse across window sweep)
    log.info("Running IS trades (%s to %s)...", IS_START, IS_END)
    is_trades = _run_tbr_hv_real_fills(IS_START, IS_END, combo=BEST_COMBO)
    log.info("Running OOS trades (%s to %s)...", OOS_START, OOS_END)
    oos_trades = _run_tbr_hv_real_fills(OOS_START, OOS_END, combo=BEST_COMBO)

    log.info("IS trades: %d  OOS trades: %d", len(is_trades), len(oos_trades))

    # Per-window analysis
    results: dict[int, dict] = {}

    for w in windows:
        print(f"\n{'='*70}")
        print(f"WINDOW = {w} TRADING DAYS")

        p25, p50, p75 = _compute_is_percentiles(rv_series[w], IS_START, IS_END)
        print(f"  IS RV percentiles: p25={p25:.2%} p50={p50:.2%} p75={p75:.2%}")

        is_tagged = _tag_trades_by_rv(is_trades, rv_by_date[w], p25, p75)
        oos_tagged = _tag_trades_by_rv(oos_trades, rv_by_date[w], p25, p75)

        is_na = sum(1 for t in is_tagged if t["rv_tier"] == "NA")
        oos_na = sum(1 for t in oos_tagged if t["rv_tier"] == "NA")
        if is_na or oos_na:
            log.warning("Trades with no RV data (warmup): IS=%d OOS=%d", is_na, oos_na)

        print(f"\n  IS breakdown ({IS_START} to {IS_END})")
        is_summary = _report_by_tier(is_tagged, w, (p25, p50, p75), "IS")

        print(f"\n  OOS breakdown ({OOS_START} to {OOS_END})")
        oos_summary = _report_by_tier(oos_tagged, w, (p25, p50, p75), "OOS")

        # Walk-forward per tier
        print(f"\n  {'-'*56}")
        print(f"  WALK-FORWARD (OOS_exp / IS_exp per tier, gate >= 0.50)")
        print(f"  {'-'*56}")
        wf_results: dict[str, dict] = {}
        for tier in ("HIGH", "MED", "LOW", "ALL"):
            is_s = is_summary["tiers"].get(tier) if tier != "ALL" else is_summary["all"]
            oos_s = oos_summary["tiers"].get(tier) if tier != "ALL" else oos_summary["all"]
            if is_s is None or oos_s is None:
                continue
            is_exp = is_s.get("exp", 0.0)
            oos_exp = oos_s.get("exp", 0.0)
            if is_exp == 0.0:
                wf_ratio = float("inf") if oos_exp > 0 else 0.0
            else:
                wf_ratio = oos_exp / is_exp
            wf_pass = wf_ratio >= 0.50 and oos_s.get("passes", False)
            print(
                f"  {tier:<5}  IS_exp={is_exp:+.2f}  OOS_exp={oos_exp:+.2f}  "
                f"ratio={wf_ratio:+.3f}  {'PASS' if wf_pass else 'FAIL'}"
            )
            wf_results[tier] = {
                "is_exp": is_exp,
                "oos_exp": oos_exp,
                "wf_ratio": round(wf_ratio, 4) if wf_ratio != float("inf") else None,
                "wf_pass": wf_pass,
                "is_n": is_s.get("n", 0),
                "oos_n": oos_s.get("n", 0),
            }

        # Verdict
        high_wf = wf_results.get("HIGH", {})
        high_pass = high_wf.get("wf_pass", False)
        high_ratio = high_wf.get("wf_ratio", 0.0) or 0.0
        high_is_wr = (is_summary["tiers"].get("HIGH") or {}).get("wr", 0.0)
        high_oos_wr = (oos_summary["tiers"].get("HIGH") or {}).get("wr", 0.0)

        print(f"\n  HIGH-RV({w}d) verdict: ", end="")
        if high_pass:
            print(f"WF PASS  ratio={high_ratio:.3f}  IS_WR={high_is_wr:.1%}  OOS_WR={high_oos_wr:.1%}")
        else:
            print(f"WF FAIL  ratio={high_ratio:.3f}  IS_WR={high_is_wr:.1%}  OOS_WR={high_oos_wr:.1%}")

        results[w] = {
            "window": w,
            "is_percentiles": {"p25": round(p25, 6), "p50": round(p50, 6), "p75": round(p75, 6)},
            "is_summary": is_summary,
            "oos_summary": oos_summary,
            "wf": wf_results,
        }

    # Final cross-window verdict
    print(f"\n{'='*70}")
    print("CROSS-WINDOW SUMMARY")
    print(f"  {'Window':<10} {'HIGH WF ratio':>14} {'HIGH IS WR':>11} {'HIGH OOS WR':>12} {'Gate'}")
    best_window = None
    best_ratio = -999.0
    for w in windows:
        r = results[w]
        wf_h = r["wf"].get("HIGH", {})
        ratio = wf_h.get("wf_ratio") or 0.0
        is_wr = (r["is_summary"]["tiers"].get("HIGH") or {}).get("wr", 0.0)
        oos_wr = (r["oos_summary"]["tiers"].get("HIGH") or {}).get("wr", 0.0)
        gate = "PASS" if wf_h.get("wf_pass", False) else "FAIL"
        print(f"  {w}d{'':<7} {ratio:>+13.3f}  {is_wr:>10.1%}  {oos_wr:>11.1%}  {gate}")
        if ratio > best_ratio:
            best_ratio = ratio
            best_window = w

    print(f"\n  Best performing window: {best_window}d  (HIGH WF ratio = {best_ratio:.3f})")

    # Concentration explainability check
    print(f"\n{'='*70}")
    print("CONCENTRATION EXPLAINABILITY  (does HIGH-RV explain the concentrated quarters?)")
    for w in windows:
        r = results[w]
        is_h_conc = (r["is_summary"].get("concentration") or {}).get("HIGH", {})
        oos_h_conc = (r["oos_summary"].get("concentration") or {}).get("HIGH", {})
        all_is_conc = _concentration(is_trades, sum(t["pnl"] for t in is_trades))
        all_oos_conc = _concentration(oos_trades, sum(t["pnl"] for t in oos_trades))

        is_conc_pct = (r["is_summary"]["tiers"].get("HIGH") or {}).get("total_pnl", 0.0)
        is_total = (r["is_summary"]["all"] or {}).get("total_pnl", 0.0)
        oos_conc_pct_high = (r["oos_summary"]["tiers"].get("HIGH") or {}).get("total_pnl", 0.0)
        oos_total = (r["oos_summary"]["all"] or {}).get("total_pnl", 0.0)

        print(f"\n  Window={w}d:")
        print(f"    ALL IS:  max_q={all_is_conc['max_quarter']} ({all_is_conc['max_pct']:.1f}%)")
        print(f"    HIGH IS: max_q={is_h_conc.get('max_quarter','')} ({is_h_conc.get('max_pct',0.0):.1f}%)  "
              f"HIGH captures {is_conc_pct/is_total*100:.1f}% of IS P&L" if is_total != 0.0
              else f"    HIGH IS: (no data)")
        print(f"    ALL OOS: max_q={all_oos_conc['max_quarter']} ({all_oos_conc['max_pct']:.1f}%)")
        print(f"    HIGH OOS: max_q={oos_h_conc.get('max_quarter','')} ({oos_h_conc.get('max_pct',0.0):.1f}%)  "
              f"HIGH captures {oos_conc_pct_high/oos_total*100:.1f}% of OOS P&L" if oos_total != 0.0
              else f"    HIGH OOS: (no data)")

    # Save
    output = {
        "run_date": dt.date.today().isoformat(),
        "description": "TBR_HIGH_VOL trailing realized-vol regime filter analysis",
        "combo": {"strike_offset": -2, "stop_pct": -0.35},
        "is_period": {"start": str(IS_START), "end": str(IS_END)},
        "oos_period": {"start": str(OOS_START), "end": str(OOS_END)},
        "n_trades": {"is": len(is_trades), "oos": len(oos_trades)},
        "windows_tested": windows,
        "results": {str(w): results[w] for w in windows},
        "best_window": best_window,
        "best_high_rv_wf_ratio": round(best_ratio, 4),
    }

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        log.info("Results written to %s", out_path)

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TBR_HIGH_VOL trailing realized-vol regime filter analysis"
    )
    parser.add_argument(
        "--window", type=int, default=None,
        help="Single RV window in trading days (default: run all three: 20, 40, 60)",
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="Run all windows [20, 40, 60] (default when no --window given)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Write JSON results to this path",
    )
    args = parser.parse_args()

    windows = RV_WINDOWS if (args.sweep or args.window is None) else [args.window]
    out_path = Path(args.out) if args.out else None

    result = run_rv_regime_analysis(windows=windows, out_path=out_path)

    # Return 0 if at least one window passes the HIGH-RV WF gate
    any_pass = any(
        result["results"][str(w)]["wf"].get("HIGH", {}).get("wf_pass", False)
        for w in windows
    )
    return 0 if any_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
