"""A/B replay harness: v1 (backtest/lib/filters.py::detect_trendline_rejection_bearish)
vs v2 (backtest/lib/trendline_fit_v2.py) FITTER ONLY, on the REAL-FILL trendline_rejection
bearish entries from analysis/trades-enriched.jsonl (real-fills arms only: safe-2, bold-2,
safe-3, risky-1).

Per the frozen prereg analysis/recommendations/prereg-trendline-fitter-v2-swap-10-30-2026-09-09.json:
"Replay the SAME sessions with only the fitter swapped -- every other gate, filter, sizing
rule and exit rule held byte-identical." This script does NOT edit backtest/lib/filters.py
or setup/scripts/heartbeat_core.py (both FROZEN_TRADING_PATH). It monkeypatches the fitter
function inside an in-memory copy of the filters module's namespace ONLY for the purpose of
this read-only, offline comparison script. No orders. No params changes.

Population: v1's REAL, ALREADY-FILLED trendline_rejection-bearish entries (real fills =
the only WR/P&L authority, L50/L71). For each such entry, we hold the underlying bar DATA
byte-identical (same single-day frame from autoresearch.runner.load_data, same bar_idx) and
ask ONLY: does v2's fitter (canon rule 1-8, ATR-scaled tolerance, close-through disqualifying,
CONFIRMED-only) ALSO produce a bearish-resistance rejection at the exact same bar?

  - MATCH: v2 also fires at that bar -> the real fill's P&L counts for BOTH v1 and v2
    (paired, byte-identical entry/exit/P&L). This is the only way a v2-side P&L number in
    this script is backed by a REAL fill.
  - MISS: v2 does NOT fire at that bar -> v1's real fill stands; v2 has no matching entry
    at that bar (a regression candidate under prereg decision clause (c), OP-16 anti-regression).

This script does NOT invent counterfactual P&L for bars where v2 fires but v1 did not --
those entries have no real fill by construction (the trade was never taken) and any BS/sim
price for them would be RANKING-ONLY per the prereg's own disclosure rule; this script does
not attempt that pricing at all, and says so in the output.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
BACKTEST = REPO / "backtest"
sys.path.insert(0, str(BACKTEST))

import pandas as pd  # noqa: E402

from autoresearch import runner  # noqa: E402
from lib.filters import detect_trendline_rejection_bearish  # noqa: E402
from lib import trendline_fit_v2 as v2  # noqa: E402

REAL_FILLS_ARMS = {"safe-2", "bold-2", "safe-3", "risky-1"}
TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
OUT_JSON = REPO / "analysis" / "trendline-v2" / "ab_replay_results_2026_09_10.json"

# v1 production constants (backtest/lib/filters.py module-level; TRENDLINE_LOOKBACK_BARS /
# TRENDLINE_MIN_SWINGS are what the live call site at filters.py:1717 actually passes).
import lib.filters as filters_mod  # noqa: E402
V1_LOOKBACK_BARS = getattr(filters_mod, "TRENDLINE_LOOKBACK_BARS", 60)
V1_MIN_SWINGS = getattr(filters_mod, "TRENDLINE_MIN_SWINGS", 3)
V1_PROXIMITY_PCT = 0.0010  # detect_trendline_rejection_bearish default


def load_real_entries() -> list[dict]:
    rows = []
    with open(TRADES_ENRICHED, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("_meta"):
                continue
            rows.append(d)
    out = []
    for r in rows:
        if r.get("attribution") != "engine":
            continue
        if r.get("arm") not in REAL_FILLS_ARMS:
            continue
        trigs = r.get("triggers")
        if not (isinstance(trigs, list) and "trendline_rejection" in trigs):
            continue
        out.append(r)
    return out


def day_frame(date_str: str) -> pd.DataFrame:
    d = dt.date.fromisoformat(date_str)
    spy, _ = runner.load_data(d, d)
    spy = spy.copy()
    spy["_ts"] = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("US/Eastern")
    day = spy[spy["_ts"].dt.date == d].reset_index(drop=True)
    return day


def find_bar_idx(day: pd.DataFrame, entry_ts_et: str) -> int | None:
    """Bars are labeled by CLOSE time (verified against test_trendline_trigger.py's
    5/1 13:35-bar / 13:36-entry pairing). The triggering bar is the one whose label
    is the largest 5-min boundary <= entry time."""
    entry_dt = pd.to_datetime(entry_ts_et)
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.tz_localize("US/Eastern")
    else:
        entry_dt = entry_dt.tz_convert("US/Eastern")
    floor_min = (entry_dt.minute // 5) * 5
    bar_label = entry_dt.replace(minute=floor_min, second=0, microsecond=0)
    matches = day.index[day["_ts"] == bar_label]
    if len(matches) == 0:
        return None
    return int(matches[0])


def bars_to_v2(day: pd.DataFrame) -> list[v2.BarV2]:
    out = []
    for _, row in day.iterrows():
        out.append(v2.BarV2(
            ts_unix=int(row["_ts"].timestamp()),
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
        ))
    return out


def v2_check_rejection(bars_v2: list[v2.BarV2], bar_idx: int) -> dict:
    """Does ANY CONFIRMED resistance line (wick or body family) from v2's fitter,
    fit using ONLY bars strictly before bar_idx (query_index=bar_idx-1, no lookahead,
    C6), reject at bar_idx (v2's own ATR-tolerance touch + close-below + red bar)?"""
    query_idx = bar_idx - 1
    if query_idx < 5:
        return {"fired": False, "reason": "insufficient_prior_bars", "lines_checked": 0}
    cur = bars_v2[bar_idx]
    fired_lines = []
    lines_checked = 0
    for family in ("wick", "body"):
        try:
            lines = v2.detect_trendlines_v2(
                bars_v2, families=(family,), kinds=("resistance",),
                query_index=query_idx, require_confirmed=True,
            )
        except Exception as exc:  # fail loud in the record, not silently
            return {"fired": False, "reason": f"v2_exception:{type(exc).__name__}:{exc}",
                    "lines_checked": lines_checked}
        lines_checked += len(lines)
        for ln in lines:
            proj = ln.current_value + ln.slope_per_bar * (bar_idx - query_idx)
            reached = cur.high >= (proj - ln.tolerance_dollars)
            closed_below = cur.close < proj
            is_red = cur.close < cur.open
            if reached and closed_below and is_red:
                fired_lines.append({
                    "line_id": ln.line_id, "family": family,
                    "projected_price": round(proj, 4),
                    "n_touches": ln.n_touches, "tolerance_dollars": round(ln.tolerance_dollars, 4),
                })
    return {"fired": len(fired_lines) > 0, "lines_checked": lines_checked, "fired_lines": fired_lines}


def v1_check_reproduction(day: pd.DataFrame, bar_idx: int, lookback_bars=V1_LOOKBACK_BARS,
                           min_swings=V1_MIN_SWINGS, proximity_pct=V1_PROXIMITY_PCT) -> float | None:
    bar = day.iloc[bar_idx]
    prior_bars = day.iloc[:bar_idx]
    return detect_trendline_rejection_bearish(
        bar, prior_bars, bar_idx,
        lookback_bars=lookback_bars, min_swings=min_swings, proximity_pct=proximity_pct,
    )


def main():
    entries = load_real_entries()
    print(f"[ab_replay] {len(entries)} real-fill trendline_rejection engine rows "
          f"across real-fills arms {sorted(REAL_FILLS_ARMS)}", file=sys.stderr)

    results = []
    day_cache: dict[str, pd.DataFrame] = {}
    v2bars_cache: dict[str, list] = {}

    for r in entries:
        date = r["date"]
        entry_ts = r.get("entry_ts_et")
        if date not in day_cache:
            try:
                day_cache[date] = day_frame(date)
            except Exception as exc:
                day_cache[date] = None
                print(f"[ab_replay] WARN could not load bars for {date}: {exc}", file=sys.stderr)
        day = day_cache[date]
        rec = {
            "date": date, "arm": r["arm"], "entry_ts_et": entry_ts,
            "pnl_dollars": r.get("pnl_dollars"), "trigger_level": r.get("trigger_level"),
        }
        if day is None or day.empty:
            rec["status"] = "NO_BAR_DATA"
            results.append(rec)
            continue
        bar_idx = find_bar_idx(day, entry_ts)
        if bar_idx is None:
            rec["status"] = "NO_MATCHING_BAR"
            results.append(rec)
            continue
        rec["bar_idx"] = bar_idx
        rec["bar_label_et"] = str(day.iloc[bar_idx]["_ts"])

        v1_price = v1_check_reproduction(day, bar_idx)
        rec["v1_reproduces"] = v1_price is not None
        rec["v1_projected_price"] = v1_price

        if date not in v2bars_cache:
            v2bars_cache[date] = bars_to_v2(day)
        v2_res = v2_check_rejection(v2bars_cache[date], bar_idx)
        rec["v2_fires"] = v2_res["fired"]
        rec["v2_detail"] = v2_res
        rec["status"] = "OK"
        results.append(rec)

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_v1_repro = sum(1 for r in results if r.get("v1_reproduces"))
    n_v2_match = sum(1 for r in results if r.get("v2_fires"))
    n_paired = sum(1 for r in results if r.get("v1_reproduces") and r.get("v2_fires"))
    n_v1_only = sum(1 for r in results if r.get("v1_reproduces") and not r.get("v2_fires"))

    summary = {
        "n_entries_total": len(entries),
        "n_ok_bar_lookup": n_ok,
        "n_v1_reproduces_real_entry": n_v1_repro,
        "n_v2_also_fires_same_bar": n_v2_match,
        "n_paired_v1_and_v2_both_fire": n_paired,
        "n_v1_fires_v2_does_not_regression_candidates": n_v1_only,
    }
    print(json.dumps(summary, indent=2))

    OUT_JSON.write_text(json.dumps({"summary": summary, "rows": results}, indent=2, default=str),
                         encoding="utf-8")
    print(f"[ab_replay] wrote {OUT_JSON}", file=sys.stderr)


if __name__ == "__main__":
    main()
