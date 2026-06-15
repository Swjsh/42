"""LBFS expanded real-fills validation — 19 VIX>=20 watcher observations.

Reads all VIX>=20 LBFS signals from watcher-observations.jsonl (N=19 as of 2026-05-24),
runs each through simulate_trade_real with chart-stop-only (premium_stop=-0.99),
and computes actual option P&L vs the grader's SPY-price proxy.

Key difference from lbfs_real_fills_validate.py (the original 4-signal validator):
  - 19 signals spanning 4 distinct market regimes (2025-Q1/Q2, Q2/Q3, Q4/2026-Q1,
    2026-Q1/Q2) — the N>=15 OP-21 gate threshold
  - Uses pure chart-stop mechanism (L51): premium_stop=-0.99 + rejection_level=break_level
  - Tests both ATM (strike_offset=0) and OTM-1 (strike_offset=1) to find the right
    strike class for LBFS entries

Results determine whether the OP-21 real-fills gate passes:
  - Gate: WR >= 50% AND P&L > 0 with chart-stop mechanism
  - If PASS → LBFS VIX>=20 candidate is PROMOTE-READY for leaderboard
  - If FAIL → watch and accumulate more live data (do not promote)

Output: analysis/recommendations/lbfs-expanded-real-fills.json
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner
from lib.ribbon import compute_ribbon
from lib.option_pricing_real import load_contract_bars, option_symbol
from lib.simulator_real import simulate_trade_real

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
    encoding="utf-8",
)
log = logging.getLogger(__name__)

OBS_LOG = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "lbfs-expanded-real-fills.json"


def load_vix20_lbfs_observations() -> list[dict]:
    """Load and deduplicate VIX>=20 LBFS observations from watcher log."""
    rows = []
    for line in OBS_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "level_break_first_strike_watcher":
            continue
        if r.get("confidence") != "high":  # VIX>=20 = "high"
            continue
        rows.append(r)

    # Dedup by (bar_timestamp_et[:16])
    seen: set = set()
    deduped = []
    for r in rows:
        key = (r.get("bar_timestamp_et") or "")[:16]
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return sorted(deduped, key=lambda r: (r.get("bar_timestamp_et") or ""))


def run_signal(obs: dict, strike_offset: int = 0) -> dict:
    """Run one observation through the real-fills engine."""
    ts_raw = obs.get("bar_timestamp_et", "")
    ts_date = ts_raw[:10]  # YYYY-MM-DD
    entry_price = obs.get("entry_price", 0.0)
    stop_price = obs.get("stop_price", entry_price + 0.30)  # break_level + 0.30
    meta = obs.get("metadata") or {}
    break_level = meta.get("break_level", stop_price - 0.30)
    vix_now = meta.get("vix_now", 0.0)
    break_below_cents = meta.get("break_below_cents", 0.0)
    vol_ratio = meta.get("vol_ratio", 0.0)

    result = {
        "date": ts_date,
        "bar_timestamp_et": ts_raw[:16],
        "entry_price": entry_price,
        "break_level": break_level,
        "break_below_cents": break_below_cents,
        "vol_ratio": vol_ratio,
        "vix_now": vix_now,
        "strike_offset": strike_offset,
        "watcher_outcome": obs.get("would_be_outcome"),
        "watcher_pnl": obs.get("would_be_pnl_dollars"),
        "real_fills_pnl": None,
        "real_fills_outcome": None,
        "error": None,
    }

    d = dt.date.fromisoformat(ts_date)
    # Load current day + 3 prior days for ribbon warmup
    d_start = d - dt.timedelta(days=5)
    try:
        spy_full, _ = ar_runner.load_data(d_start, d)
    except Exception as e:
        # Fallback: just load one day
        try:
            spy_full, _ = ar_runner.load_data(d, d)
        except Exception as e2:
            result["error"] = f"load_data failed: {e2}"
            log.warning("  load_data failed for %s: %s", ts_date, e2)
            return result

    # Normalize timestamps (L31 — tz-aware collisions)
    ts_col = pd.to_datetime(spy_full["timestamp_et"])
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("America/New_York").dt.tz_localize(None)
    spy_full = spy_full.copy()
    spy_full["timestamp_et"] = ts_col

    # Filter to same day for simulate_trade_real
    target_date = d
    day_mask = spy_full["timestamp_et"].dt.date == target_date
    spy_day = spy_full[day_mask & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))].copy()
    if spy_day.empty:
        result["error"] = f"no day bars for {ts_date}"
        return result

    # Build combined (prior + day) for ribbon warmup — same pattern as lbfs_real_fills_validate.py
    first_day_ts = spy_day["timestamp_et"].iloc[0]
    prior_bars = spy_full[spy_full["timestamp_et"] < first_day_ts].tail(40).copy()
    combined = pd.concat([prior_bars, spy_day], ignore_index=True)

    # Compute ribbon on close column (NOT the full DataFrame)
    try:
        ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)
    except Exception as e:
        result["error"] = f"ribbon compute failed: {e}"
        return result

    # Find entry bar in combined
    entry_ts = pd.to_datetime(ts_raw[:16])
    if entry_ts.tz is not None:
        entry_ts = entry_ts.tz_localize(None)

    matches = combined[combined["timestamp_et"] == entry_ts]
    if matches.empty:
        # Fuzzy match within 10 min
        diff = (combined["timestamp_et"] - entry_ts).dt.total_seconds().abs()
        if diff.min() <= 600:
            closest = int(diff.idxmin())
            matches = combined.iloc[[closest]]

    if matches.empty:
        result["error"] = f"entry bar not found for {ts_raw[:16]}"
        log.warning("  entry bar not found for %s", ts_raw[:16])
        return result

    entry_bar_idx = int(matches.index[0])
    entry_bar = combined.iloc[entry_bar_idx]

    # Use combined as spy_df (simulate_trade_real reads forward bars from this)
    spy = combined

    # Run real-fills simulation: chart-stop-only (L51 doc)
    try:
        fill = simulate_trade_real(
            entry_bar_idx=entry_bar_idx,
            entry_bar=entry_bar,
            spy_df=spy,
            ribbon_df=ribbon_df,
            rejection_level=float(break_level),
            triggers_fired=["MIXED_RIBBON_LEVEL_BREAK", "VOL_1.5X"],
            side="P",  # bearish
            qty=3,
            setup="LEVEL_BREAK_FIRST_STRIKE",
            premium_stop_pct=-0.99,   # chart stop ONLY (L51 — premium stop incompatible)
            strike_offset=strike_offset,
        )
    except Exception as e:
        result["error"] = f"simulate_trade_real failed: {e}"
        log.warning("  simulate failed for %s: %s", ts_raw[:16], e)
        return result

    if fill is None:
        result["error"] = "simulate_trade_real returned None (no OPRA data?)"
        log.warning("  None fill for %s", ts_raw[:16])
        return result

    pnl = fill.dollar_pnl or 0
    result["real_fills_pnl"] = round(pnl, 2)
    result["real_fills_outcome"] = fill.exit_reason
    result["entry_premium"] = round(fill.entry_premium or 0, 4)
    result["tp1_premium"] = round(fill.tp1_premium or 0, 4) if fill.tp1_premium else None
    result["exit_reason"] = fill.exit_reason
    log.info(
        "  %s  VIX=%.1f  break_below=%.0fc  vol=%.1fx  pnl=$%+.0f  exit=%s",
        ts_raw[:16], vix_now, break_below_cents, vol_ratio, pnl, fill.exit_reason,
    )
    return result


def main() -> None:
    observations = load_vix20_lbfs_observations()
    log.info("Loaded %d VIX>=20 LBFS observations", len(observations))

    # Run for both ATM and OTM-1
    all_results = []
    for strike_offset in [0, 1]:  # 0=ATM, 1=OTM-1 (strike $1 BELOW spot for puts)
        log.info("\n=== strike_offset=%d ===", strike_offset)
        for obs in observations:
            log.info("Signal %s  VIX=%.1f  break=%.0fc",
                     (obs.get("bar_timestamp_et") or "")[:16],
                     (obs.get("metadata") or {}).get("vix_now", 0),
                     (obs.get("metadata") or {}).get("break_below_cents", 0))
            r = run_signal(obs, strike_offset=strike_offset)
            r["strike_offset_label"] = "ATM" if strike_offset == 0 else "OTM-1"
            all_results.append(r)

    # Compute summary per strike_offset
    summary = {}
    for label in ["ATM", "OTM-1"]:
        subset = [r for r in all_results if r.get("strike_offset_label") == label]
        graded = [r for r in subset if r.get("real_fills_pnl") is not None]
        wins = [r for r in graded if (r.get("real_fills_pnl") or 0) > 0]
        total_pnl = sum(r.get("real_fills_pnl") or 0 for r in graded)
        watcher_total = sum(r.get("watcher_pnl") or 0 for r in graded)
        wr = len(wins) / len(graded) if graded else 0

        summary[label] = {
            "n_total": len(subset),
            "n_graded": len(graded),
            "n_no_data": sum(1 for r in subset if r.get("error")),
            "wins": len(wins),
            "losses": len(graded) - len(wins),
            "win_rate": round(wr, 4),
            "real_fills_total_pnl": round(total_pnl, 2),
            "watcher_proxy_pnl": round(watcher_total, 2),
            "op21_gate_pass": wr >= 0.50 and total_pnl > 0,
        }

        log.info(
            "\nSUMMARY [%s]: N=%d graded=%d WR=%.1f%% P&L=$%+.0f "
            "watcher_proxy=$%+.0f  OP21_GATE=%s",
            label, len(subset), len(graded), wr * 100, total_pnl,
            watcher_total, "PASS" if summary[label]["op21_gate_pass"] else "FAIL",
        )

    # Outcome breakdown
    log.info("\n=== Signal details ===")
    for r in all_results:
        if r.get("strike_offset_label") == "ATM":
            flag = "W" if (r.get("real_fills_pnl") or 0) > 0 else ("E" if r.get("error") else "L")
            log.info(
                "  %s  VIX=%.1f break=%.0fc vol=%.1fx  real=$%s  watcher=$%s  [%s]  %s",
                r["bar_timestamp_et"], r.get("vix_now", 0),
                r.get("break_below_cents", 0), r.get("vol_ratio", 0),
                f"+{r['real_fills_pnl']:.0f}" if (r.get("real_fills_pnl") or 0) > 0
                else (str(r.get("error", ""))[:30] if r.get("error") else f"{r.get('real_fills_pnl',0):.0f}"),
                f"+{r['watcher_pnl']:.0f}" if (r.get("watcher_pnl") or 0) > 0
                else str(r.get("watcher_pnl", 0) or 0),
                flag, r.get("exit_reason") or r.get("error", ""),
            )

    output = {
        "generated_at": dt.datetime.now().isoformat(),
        "description": "LBFS expanded real-fills validation — 19 VIX>=20 watcher observations",
        "op21_gate": "WR >= 50% AND P&L > 0 with chart-stop mechanism (premium_stop=-0.99)",
        "n_observations": len(observations),
        "summary": summary,
        "signals": all_results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\nOutput: %s", OUT_JSON)

    # Final verdict
    atm = summary.get("ATM", {})
    log.info("\n=== FINAL VERDICT ===")
    log.info("ATM: WR=%.1f%% P&L=$%+.0f  -> OP21 REAL-FILLS GATE: %s",
             atm.get("win_rate", 0) * 100, atm.get("real_fills_total_pnl", 0),
             "PASS" if atm.get("op21_gate_pass") else "FAIL")


if __name__ == "__main__":
    main()
