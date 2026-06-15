"""V14E bear chart-stop research — L51 analog check.

Research question (per STATUS.md research queue item #3):
  For v14e bear entries (RIDE_THE_RIBBON, OTM-2 puts, default -8% premium
  stop), does the -8% premium stop fire BEFORE the directional bear move
  develops on score=8/9 entries?

L51 precedent: LBFS violent initial bounce invalidated all premium stops.
L55 precedent: NLWB same pattern for calls. Both fixed with chart-stop-only
(-99% premium stop, chart stop = rejection_level + $0.30).

Method:
  1. Load all graded stopped bear v14e obs from watcher-observations.jsonl
  2. Load full SPY 5m DataFrame for ribbon warmup
  3. For each obs, simulate_trade_real with:
     A. PROD: premium_stop_pct=-0.08 (production default)
     B. CHART: premium_stop_pct=-0.99 (chart-stop-only)
  4. Compare exit_reason distribution + P&L delta
  5. Split by score (8/9 vs 10) to see vulnerability gradient

Output: analysis/recommendations/v14e-chart-stop-research.json
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.ribbon import compute_ribbon
from lib.simulator_real import simulate_trade_real
from lib.simulator_real import option_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OBS_LOG = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "v14e-chart-stop-research.json"

# Find the SPY CSV (rolling append pattern)
def _find_spy_csv() -> Optional[Path]:
    data_dir = REPO / "data"
    # Prefer the largest file (most historical coverage)
    candidates = sorted(data_dir.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0] if candidates else None

STRIKE_OFFSET = 2   # OTM-2 puts: for puts, strike = ATM - offset = OTM-2
QTY = 3
PROD_STOP = -0.08
CHART_STOP = -0.99


def load_stopped_bear_obs() -> list[dict]:
    rows = []
    for line in OBS_LOG.read_text().splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if (
            o.get("watcher_name") == "v14_enhanced_watcher"
            and o.get("direction") == "short"
            and o.get("would_be_outcome") == "stopped"
        ):
            rows.append(o)
    return rows


def load_spy_full(spy_path: Path) -> pd.DataFrame:
    log.info("Loading SPY 5m from %s ...", spy_path.name)
    df = pd.read_csv(spy_path)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    log.info("  %d bars, %s → %s", len(df), df["timestamp_et"].iloc[0].date(),
             df["timestamp_et"].iloc[-1].date())
    return df


def _simulate_one(obs: dict, spy_full: pd.DataFrame, premium_stop_pct: float) -> Optional[dict]:
    """Run simulate_trade_real for one obs with a given premium stop.

    Returns dict with exit_reason/pnl, or None if OPRA missing.
    """
    ts_raw = obs["bar_timestamp_et"]
    ts = pd.Timestamp(ts_raw)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    target_date = ts.date()

    # Day bars (RTH only) + 40 prior bars for ribbon warmup
    day_mask = spy_full["timestamp_et"].dt.date == target_date
    day_bars = spy_full[day_mask & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))].copy()
    if day_bars.empty:
        return None
    first_day_ts = day_bars["timestamp_et"].iloc[0]
    prior_bars = spy_full[spy_full["timestamp_et"] < first_day_ts].tail(40).copy()
    combined = pd.concat([prior_bars, day_bars], ignore_index=True)

    # Compute ribbon
    ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

    # Find entry bar index in combined
    matches = combined[combined["timestamp_et"] == ts]
    if matches.empty:
        diff = (combined["timestamp_et"] - ts).dt.total_seconds().abs()
        idx_min = diff.idxmin()
        if diff[idx_min] > 120:  # >2 min tolerance
            return None
        entry_bar_idx = idx_min
    else:
        entry_bar_idx = matches.index[0]

    entry_bar = combined.iloc[entry_bar_idx]
    rejection_level = obs.get("metadata", {}).get("rejection_or_reclaim_level") or 0.0
    triggers_fired = obs.get("triggers_fired") or []

    try:
        fill = simulate_trade_real(
            entry_bar_idx=entry_bar_idx,
            entry_bar=entry_bar,
            spy_df=combined,
            ribbon_df=ribbon_df,
            rejection_level=rejection_level,
            triggers_fired=triggers_fired,
            side="P",
            qty=QTY,
            setup="BEARISH_REJECTION_v14e",
            premium_stop_pct=premium_stop_pct,
            strike_offset=STRIKE_OFFSET,
        )
    except Exception as e:
        log.debug("simulate_trade_real error for %s: %s", ts, e)
        return None

    if fill is None:
        return None

    exit_reason_str = (
        fill.exit_reason.value
        if hasattr(fill.exit_reason, "value")
        else str(fill.exit_reason)
    )
    return {
        "exit_reason": exit_reason_str,
        "pnl": fill.dollar_pnl,
        "entry_premium": fill.entry_premium,
    }


def main() -> int:
    spy_path = _find_spy_csv()
    if spy_path is None:
        log.error("No SPY CSV found in backtest/data/")
        return 1

    spy_full = load_spy_full(spy_path)
    stopped = load_stopped_bear_obs()
    log.info("Stopped bear v14e obs: %d", len(stopped))

    results = []
    for i, obs in enumerate(stopped):
        score = obs.get("metadata", {}).get("score")
        ts = obs["bar_timestamp_et"]
        if i % 10 == 0:
            log.info("  Processing obs %d/%d ...", i + 1, len(stopped))

        prod = _simulate_one(obs, spy_full, PROD_STOP)
        chart = _simulate_one(obs, spy_full, CHART_STOP)

        results.append({
            "ts": ts,
            "score": score,
            "grader_pnl": obs.get("would_be_pnl_dollars"),
            "prod_exit": prod["exit_reason"] if prod else "OPRA_MISS",
            "prod_pnl": prod["pnl"] if prod else None,
            "prod_entry_premium": prod["entry_premium"] if prod else None,
            "chart_exit": chart["exit_reason"] if chart else "OPRA_MISS",
            "chart_pnl": chart["pnl"] if chart else None,
        })

    # ── Analysis ──────────────────────────────────────────────────────────────
    covered = [r for r in results if r["prod_exit"] != "OPRA_MISS"]
    opra_miss_count = len(results) - len(covered)
    log.info("OPRA coverage: %d/%d (%.1f%%)", len(covered), len(results),
             len(covered) / max(len(results), 1) * 100)

    prod_exits = Counter(r["prod_exit"] for r in covered)
    premium_stop_obs = [r for r in covered if "PREMIUM_STOP" in r["prod_exit"]]
    chart_stop_obs = [r for r in covered if "LEVEL_STOP" in r["prod_exit"] or
                      "CHART_STOP" in r["prod_exit"]]
    other_obs = [r for r in covered
                 if r not in premium_stop_obs and r not in chart_stop_obs]

    print("\n=== V14E BEAR CHART-STOP RESEARCH — L51 ANALOG CHECK ===")
    print(f"Stopped bear obs: {len(stopped)} total | {len(covered)} OPRA-covered | {opra_miss_count} OPRA-miss")
    print(f"\nProduction (-8% stop) exit breakdown (N={len(covered)}):")
    for reason, cnt in prod_exits.most_common():
        print(f"  {reason}: {cnt}")
    print(f"\nPREMIUM_STOP fires: {len(premium_stop_obs)} ({len(premium_stop_obs)/max(len(covered),1)*100:.1f}%)")
    print(f"CHART/LEVEL_STOP fires: {len(chart_stop_obs)} ({len(chart_stop_obs)/max(len(covered),1)*100:.1f}%)")
    print(f"Other (time stop, runner, etc): {len(other_obs)}")

    # Per-score breakdown
    print("\nPer-score premium-stop rate:")
    per_score = {}
    for sv in [6, 7, 8, 9, 10]:
        sv_obs = [r for r in covered if r["score"] == sv]
        sv_prem = [r for r in sv_obs if "PREMIUM_STOP" in r["prod_exit"]]
        sv_entry_premiums = [r["prod_entry_premium"] for r in sv_prem if r.get("prod_entry_premium")]
        avg_premium = sum(sv_entry_premiums) / len(sv_entry_premiums) if sv_entry_premiums else 0
        per_score[sv] = {
            "n": len(sv_obs),
            "premium_stops": len(sv_prem),
            "pct": round(len(sv_prem) / max(len(sv_obs), 1) * 100, 1),
            "avg_entry_premium_at_prem_stop": round(avg_premium, 3),
        }
        if sv_obs:
            print(f"  score={sv}: N={len(sv_obs)}, premium_stops={len(sv_prem)} "
                  f"({per_score[sv]['pct']}%), avg_entry_premium={avg_premium:.2f}")

    # P&L delta: production vs chart-stop-only
    both = [r for r in covered if r["chart_exit"] != "OPRA_MISS" and r["chart_pnl"] is not None]
    prod_total = sum(r["prod_pnl"] or 0 for r in both)
    chart_total = sum(r["chart_pnl"] or 0 for r in both)
    delta = chart_total - prod_total

    print(f"\nP&L comparison on {len(both)} doubly-covered stopped obs:")
    print(f"  Production (-8% stop):   ${prod_total:,.2f}")
    print(f"  Chart-stop-only (-99%):  ${chart_total:,.2f}")
    direction_label = "chart better" if delta > 0 else "prod better"
    print(f"  Delta (chart - prod):    ${delta:,.2f}  ({direction_label})")

    # For premium-stop fires specifically: what did chart-stop give instead?
    prem_fire_both = [r for r in premium_stop_obs
                      if r["chart_exit"] != "OPRA_MISS" and r["chart_pnl"] is not None]
    if prem_fire_both:
        prod_prem_pnl = sum(r["prod_pnl"] or 0 for r in prem_fire_both)
        chart_prem_pnl = sum(r["chart_pnl"] or 0 for r in prem_fire_both)
        chart_exits_on_prem = Counter(r["chart_exit"] for r in prem_fire_both)
        print(f"\nOn {len(prem_fire_both)} premium-stop fires specifically:")
        print(f"  Prod P&L: ${prod_prem_pnl:,.2f} | Chart P&L: ${chart_prem_pnl:,.2f} | Delta: ${chart_prem_pnl-prod_prem_pnl:,.2f}")
        print(f"  What chart-stop-only gave instead: {dict(chart_exits_on_prem)}")

    # Save
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "research_question": "Does -8% premium stop fire before directional bear move on v14e bear stopped entries?",
        "n_stopped_obs": len(stopped),
        "n_opra_covered": len(covered),
        "n_opra_miss": opra_miss_count,
        "prod_exit_distribution": dict(prod_exits),
        "premium_stop_fires": len(premium_stop_obs),
        "premium_stop_pct_of_covered": round(len(premium_stop_obs) / max(len(covered), 1) * 100, 1),
        "pnl_comparison": {
            "n": len(both),
            "prod_pnl": round(prod_total, 2),
            "chart_stop_pnl": round(chart_total, 2),
            "delta": round(delta, 2),
            "direction": "chart_better" if delta > 0 else "prod_better",
        },
        "per_score": per_score,
        "detail": [
            {k: v for k, v in r.items() if v is not None}
            for r in results
        ],
    }
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str))
    log.info("Results → %s", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
