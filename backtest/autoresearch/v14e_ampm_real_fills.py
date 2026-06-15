"""V14E bear AM-vs-PM real-fills validation.

Validates whether the AM/PM time-of-day pattern observed in SPY-proxy WR
(V14E #17 WATCH-ONLY candidate) holds in actual option P&L.

Gate for leaderboard #17 advancement:
  "Real-fills pending (10+ obs per time bucket)"

Design:
  1. Load ALL deduped high-conf v14e bear observations (watcher_name=v14_enhanced_watcher,
     confidence=high) from watcher-observations.jsonl
  2. Bucket by hour (09:xx, 10:xx, 11:xx, 12:xx, 13:xx, 14:xx, 15:xx)
  3. Run simulate_trade_real with:
       - PRODUCTION config: premium_stop_pct=-0.08, strike_offset=2 (OTM-2)
       - CHART-STOP config: premium_stop_pct=-0.99, strike_offset=2
  4. Report WR + P&L per bucket, AM (09-11:xx) vs PM (12-14:xx) split
  5. Compare to SPY-proxy numbers from _v14e_ampm_oos.py

Key reference:
  IS: PM exp=+$12.02, AM exp=-$3.05 (SPY-proxy)
  OOS: PM exp=+$12.69, AM exp=-$1.44 (SPY-proxy)

Output: analysis/recommendations/v14e_ampm_real_fills.json
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner
from lib.ribbon import compute_ribbon
from lib.simulator_real import simulate_trade_real

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
    encoding="utf-8",
)
log = logging.getLogger(__name__)

OBS_LOG = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "v14e_ampm_real_fills.json"

# AM = chop zone (first session — lowest historical WR)
# PM = money zone (afternoon session — highest historical WR)
AM_HOURS = {9, 10, 11}
PM_HOURS = {12, 13, 14}

# Strike offset per v14e default (OTM-2 puts)
V14E_STRIKE_OFFSET = 2


def load_v14e_highconf_bear_observations() -> list[dict]:
    """Load and deduplicate high-conf v14e bear observations."""
    rows = []
    for line in OBS_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "v14_enhanced_watcher":
            continue
        if r.get("confidence") != "high":
            continue
        # Bear signals only (direction=short, setup_name contains BEARISH)
        direction = r.get("direction", "")
        setup = r.get("setup_name", "")
        if direction != "short" and "BEAR" not in setup.upper():
            continue
        rows.append(r)

    # Dedup by bar_timestamp_et[:16]
    seen: set = set()
    deduped = []
    for r in rows:
        key = (r.get("bar_timestamp_et") or "")[:16]
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return sorted(deduped, key=lambda r: (r.get("bar_timestamp_et") or ""))


def run_signal(obs: dict, premium_stop_pct: float = -0.08) -> dict:
    """Run one observation through the real-fills engine."""
    ts_raw = obs.get("bar_timestamp_et", "")
    ts_date = ts_raw[:10]  # YYYY-MM-DD
    entry_price = obs.get("entry_price", 0.0)
    meta = obs.get("metadata") or {}
    rejection_level = meta.get("rejection_or_reclaim_level", entry_price + 0.40)
    strike_offset = meta.get("strike_offset", V14E_STRIKE_OFFSET)
    watcher_pnl = obs.get("would_be_pnl_dollars")
    watcher_outcome = obs.get("would_be_outcome")
    hour = int(ts_raw[11:13]) if len(ts_raw) >= 13 else 0
    bucket = "AM" if hour in AM_HOURS else ("PM" if hour in PM_HOURS else "other")

    result = {
        "date": ts_date,
        "bar_timestamp_et": ts_raw[:16],
        "hour": hour,
        "bucket": bucket,
        "entry_price": entry_price,
        "rejection_level": rejection_level,
        "premium_stop_pct": premium_stop_pct,
        "watcher_outcome": watcher_outcome,
        "watcher_pnl": watcher_pnl,
        "real_fills_pnl": None,
        "real_fills_outcome": None,
        "error": None,
    }

    d = dt.date.fromisoformat(ts_date)
    d_start = d - dt.timedelta(days=5)
    try:
        spy_full, _ = ar_runner.load_data(d_start, d)
    except Exception as e:
        try:
            spy_full, _ = ar_runner.load_data(d, d)
        except Exception as e2:
            result["error"] = f"load_data failed: {e2}"
            log.warning("  load_data failed for %s: %s", ts_date, e2)
            return result

    # Normalize timestamps (L31)
    ts_col = pd.to_datetime(spy_full["timestamp_et"])
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("America/New_York").dt.tz_localize(None)
    spy_full = spy_full.copy()
    spy_full["timestamp_et"] = ts_col

    target_date = d
    day_mask = spy_full["timestamp_et"].dt.date == target_date
    spy_day = spy_full[day_mask & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))].copy()
    if spy_day.empty:
        result["error"] = f"no day bars for {ts_date}"
        return result

    first_day_ts = spy_day["timestamp_et"].iloc[0]
    prior_bars = spy_full[spy_full["timestamp_et"] < first_day_ts].tail(40).copy()
    combined = pd.concat([prior_bars, spy_day], ignore_index=True)

    try:
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)
    except Exception as e:
        result["error"] = f"ribbon failed: {e}"
        return result

    entry_ts = pd.to_datetime(ts_raw[:16])
    if entry_ts.tz is not None:
        entry_ts = entry_ts.tz_localize(None)

    matches = combined[combined["timestamp_et"] == entry_ts]
    if matches.empty:
        diff = (combined["timestamp_et"] - entry_ts).dt.total_seconds().abs()
        if diff.min() <= 600:
            closest = int(diff.idxmin())
            matches = combined.iloc[[closest]]

    if matches.empty:
        result["error"] = f"entry bar not found for {ts_raw[:16]}"
        return result

    entry_bar_idx = int(matches.index[0])
    entry_bar = combined.iloc[entry_bar_idx]

    try:
        fill = simulate_trade_real(
            entry_bar_idx=entry_bar_idx,
            entry_bar=entry_bar,
            spy_df=combined,
            ribbon_df=ribbon_df,
            rejection_level=float(rejection_level),
            triggers_fired=obs.get("triggers_fired") or ["level_rejection"],
            side="P",   # bearish = puts
            qty=3,
            setup="BEARISH_REJECTION_v14e",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
    except Exception as e:
        result["error"] = f"simulate failed: {e}"
        log.warning("  simulate failed for %s: %s", ts_raw[:16], e)
        return result

    if fill is None:
        result["error"] = "no OPRA data"
        return result

    pnl = fill.dollar_pnl or 0
    result["real_fills_pnl"] = round(pnl, 2)
    result["real_fills_outcome"] = fill.exit_reason
    result["entry_premium"] = round(fill.entry_premium or 0, 4)
    log.info(
        "  %s [%s] stop=%.2f  real=$%+.0f  watcher=$%s  exit=%s",
        ts_raw[:16], bucket, premium_stop_pct, pnl,
        f"+{watcher_pnl:.0f}" if (watcher_pnl or 0) > 0 else str(watcher_pnl or 0),
        fill.exit_reason,
    )
    return result


def compute_bucket_stats(results: list[dict]) -> dict:
    """Compute per-hour and AM/PM statistics."""
    by_hour: dict[int, list] = defaultdict(list)
    for r in results:
        if r.get("real_fills_pnl") is not None:
            by_hour[r.get("hour", -1)].append(r)

    hour_stats = {}
    for h in sorted(by_hour):
        graded = by_hour[h]
        wins = [r for r in graded if (r.get("real_fills_pnl") or 0) > 0]
        total_pnl = sum(r.get("real_fills_pnl") or 0 for r in graded)
        wr = len(wins) / len(graded) if graded else 0
        exp = total_pnl / len(graded) if graded else 0
        hour_stats[f"{h:02d}xx"] = {
            "n_graded": len(graded),
            "wins": len(wins),
            "win_rate": round(wr, 4),
            "total_pnl": round(total_pnl, 2),
            "expectancy": round(exp, 2),
        }

    # AM vs PM
    am_graded = [r for r in results if r.get("real_fills_pnl") is not None
                 and r.get("hour", -1) in AM_HOURS]
    pm_graded = [r for r in results if r.get("real_fills_pnl") is not None
                 and r.get("hour", -1) in PM_HOURS]

    def _stats(subset):
        if not subset:
            return {"n_graded": 0, "win_rate": 0.0, "total_pnl": 0.0, "expectancy": 0.0}
        wins = [r for r in subset if (r.get("real_fills_pnl") or 0) > 0]
        pnl = sum(r.get("real_fills_pnl") or 0 for r in subset)
        return {
            "n_graded": len(subset),
            "wins": len(wins),
            "win_rate": round(len(wins) / len(subset), 4),
            "total_pnl": round(pnl, 2),
            "expectancy": round(pnl / len(subset), 2),
        }

    return {
        "by_hour": hour_stats,
        "AM": _stats(am_graded),
        "PM": _stats(pm_graded),
        "pm_over_am_exp_delta": round(
            _stats(pm_graded)["expectancy"] - _stats(am_graded)["expectancy"], 2
        ),
    }


def main() -> None:
    observations = load_v14e_highconf_bear_observations()
    log.info("Loaded %d high-conf v14e bear observations", len(observations))

    for stop_label, stop_pct in [("PROD (-0.08)", -0.08), ("CHART_STOP (-0.99)", -0.99)]:
        log.info("\n=== %s ===", stop_label)
        results = []
        for obs in observations:
            ts = (obs.get("bar_timestamp_et") or "")[:16]
            hour = int(ts[11:13]) if len(ts) >= 13 else 0
            log.info("  [%s] Signal %s", f"{hour:02d}xx", ts)
            r = run_signal(obs, premium_stop_pct=stop_pct)
            r["stop_label"] = stop_label
            results.append(r)

        graded = [r for r in results if r.get("real_fills_pnl") is not None]
        no_data = [r for r in results if r.get("error")]
        wins = [r for r in graded if (r.get("real_fills_pnl") or 0) > 0]
        total_pnl = sum(r.get("real_fills_pnl") or 0 for r in graded)
        wr = len(wins) / len(graded) if graded else 0

        stats = compute_bucket_stats(results)

        log.info("\nSUMMARY [%s]: total=%d graded=%d no_data=%d WR=%.1f%% P&L=$%+.0f",
                 stop_label, len(results), len(graded), len(no_data), wr * 100, total_pnl)
        log.info("AM: n=%d WR=%.1f%% exp=$%+.1f | PM: n=%d WR=%.1f%% exp=$%+.1f | PM-AM delta=$%+.1f",
                 stats["AM"]["n_graded"], stats["AM"]["win_rate"] * 100, stats["AM"]["expectancy"],
                 stats["PM"]["n_graded"], stats["PM"]["win_rate"] * 100, stats["PM"]["expectancy"],
                 stats["pm_over_am_exp_delta"])
        log.info("By hour: %s", {k: f'n={v["n_graded"]} WR={v["win_rate"]*100:.0f}% exp=${v["expectancy"]:+.1f}'
                                  for k, v in stats["by_hour"].items()})

        # Print per-stop results dict to a variable for final combined output
        if stop_label.startswith("PROD"):
            prod_results = results
            prod_stats = stats
        else:
            chart_results = results
            chart_stats = stats

    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "description": "V14E bear AM-vs-PM real-fills validation",
        "n_observations": len(observations),
        "spy_proxy_reference": {
            "IS": {"PM_exp": 12.02, "AM_exp": -3.05},
            "OOS": {"PM_exp": 12.69, "AM_exp": -1.44},
        },
        "production_stop": {
            "stop_pct": -0.08,
            "stats": prod_stats,
            "signals": prod_results,
        },
        "chart_stop": {
            "stop_pct": -0.99,
            "stats": chart_stats,
            "signals": chart_results,
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\nOutput: %s", OUT_JSON)


if __name__ == "__main__":
    main()
