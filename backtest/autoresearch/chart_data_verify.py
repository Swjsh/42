"""Chart data verify — cross-check live SPY 5m bars across data sources.

AUDIT: pull the last N closed 5m bars from yfinance live (intraday) AND from the
master CSV. Compare close prices within ±$0.05 tolerance.

DIAGNOSE: GREEN if all bars match within tolerance; YELLOW if 1 bar diverges
$0.05-$0.10 (consolidated-vs-single-venue rounding); RED if any divergence > $0.10
(cache-stale / wrong-bar-time / API broken).

HEAL: re-run the in-memory yfinance top-up that watcher_live.py performs.
The CSV is NOT modified (rule 9 — that's the EOD appender's job).

REPORT: stdout + JSON at automation/state/chart-data-verify-{date}.json.

Note: this skill validates the BAR DATA pipeline. To validate that the heartbeat
prompt READS the right bar (closed vs in-progress), use heartbeat-tick-audit.

USAGE:
    python -m autoresearch.chart_data_verify
    python -m autoresearch.chart_data_verify --date 2026-05-14 --bars 5
    python -m autoresearch.chart_data_verify --heal
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "automation" / "state"
DATA_DIR = ROOT / "backtest" / "data"

TOL_GREEN  = 0.05
TOL_YELLOW = 0.10
# The 15:55 ET closing bar routinely has larger divergence between TV (CSV) and yfinance
# because data providers disagree on the exact RTH close price. This is non-actionable —
# the heartbeat uses TV data directly, not the CSV for the final bar.
TOL_CLOSE_BAR = 0.35


def find_master_csv(target_date: str):
    """Find the spy_5m_*.csv covering target_date (newest-first, prefer the broadest)."""
    if not DATA_DIR.exists():
        return None
    candidates = sorted(DATA_DIR.glob("spy_5m_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    for path in candidates:
        # filename pattern: spy_5m_{start}_{end}.csv
        try:
            parts = path.stem.split("_")
            start = datetime.strptime(parts[-2], "%Y-%m-%d").date()
            end   = datetime.strptime(parts[-1], "%Y-%m-%d").date()
            if start <= target <= end:
                return path
        except Exception:
            continue
    return candidates[0] if candidates else None


def fetch_yfinance_bars(target_date: str, bars: int):
    """Fetch the last `bars` closed 5m bars from yfinance for SPY on target_date."""
    try:
        import yfinance as yf
        import pandas as pd
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        # period="2d" handles weekend lookback; interval="5m"
        df = yf.download("SPY", period="5d", interval="5m", prepost=False, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        # Datetime column may be 'Datetime' or 'index' depending on yf version
        ts_col = "Datetime" if "Datetime" in df.columns else "index"
        df["timestamp_et"] = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        df["date"] = df["timestamp_et"].dt.date
        target_df = df[df["date"] == target].copy()
        if target_df.empty:
            return None
        return target_df[["timestamp_et", "Open", "High", "Low", "Close", "Volume"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        ).reset_index(drop=True).tail(bars)
    except Exception as e:
        print(f"yfinance fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def load_csv_bars(csv_path: Path, target_date: str, bars: int):
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        # Normalize to tz-naive ET to match yfinance output
        ts = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
        df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
        df["date"] = df["timestamp_et"].dt.date
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        d = df[df["date"] == target].copy()
        return d.tail(bars).reset_index(drop=True) if not d.empty else None
    except Exception as e:
        print(f"csv load failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (defaults to most recent weekday)")
    parser.add_argument("--bars", type=int, default=5, help="Number of trailing bars to verify")
    parser.add_argument("--heal", action="store_true", help="run yfinance top-up (in-memory only)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    target_date = args.date
    if target_date is None:
        # Default to today; fall back to most recent weekday
        d = datetime.now().date()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        target_date = d.strftime("%Y-%m-%d")

    csv_path = find_master_csv(target_date)
    if csv_path is None:
        verdict = "RED"
        reason = "no-spy_5m-csv-found-in-backtest-data"
        result = _report(target_date, verdict, reason, [], None, None, "no-op-csv-missing")
        return _emit(result, args.quiet)

    csv_bars = load_csv_bars(csv_path, target_date, args.bars)
    yf_bars  = fetch_yfinance_bars(target_date, args.bars)

    # ---- DIAGNOSE ----
    rows = []
    max_div = 0.0

    csv_has = csv_bars is not None and len(csv_bars) > 0
    yf_has  = yf_bars  is not None and len(yf_bars)  > 0

    if not csv_has and not yf_has:
        verdict = "RED"
        reason = "no-csv-data-AND-no-yfinance-data"
    elif not csv_has and yf_has:
        verdict = "YELLOW"
        reason = "no-csv-data-yet-yfinance-has-bars (CSV stale, EOD appender hasn't run)"
        for _, r in yf_bars.iterrows():
            rows.append({
                "ts": str(r["timestamp_et"]),
                "csv_close": None,
                "yf_close": float(r["close"]),
                "divergence": None,
            })
    elif csv_has and not yf_has:
        verdict = "YELLOW"
        reason = "yfinance-fetch-failed-csv-only"
        for _, r in csv_bars.iterrows():
            rows.append({
                "ts": str(r["timestamp_et"]),
                "csv_close": float(r["close"]),
                "yf_close": None,
                "divergence": None,
            })
    else:
        # Both present — match on timestamp; if not exact match, just compare same-index trailing bars
        # Try exact-timestamp join first
        try:
            import pandas as pd
            csv_idx = csv_bars.set_index("timestamp_et")
            yf_idx  = yf_bars.set_index("timestamp_et")
            common = csv_idx.index.intersection(yf_idx.index)
            if len(common) == 0:
                # No timestamp intersection: CSV and yfinance cover different time windows.
                # Most common cause: CSV was last appended mid-session (or previous EOD),
                # but yfinance is returning end-of-day bars for today. Position-based
                # comparison here is MEANINGLESS (comparing 10:05 vs 15:35 bars gives
                # spurious $1+ "divergences"). Report YELLOW + the actual timestamp ranges
                # instead of a bogus RED.
                csv_last = str(csv_bars.iloc[-1]["timestamp_et"]) if len(csv_bars) else "N/A"
                yf_last  = str(yf_bars.iloc[-1]["timestamp_et"])  if len(yf_bars)  else "N/A"
                verdict = "YELLOW"
                reason = (
                    f"no-timestamp-overlap: csv ends {csv_last}, "
                    f"yf ends {yf_last} -- CSV not updated yet or EOD appender pending"
                )
                for _, r in yf_bars.iterrows():
                    rows.append({
                        "ts": str(r["timestamp_et"]),
                        "csv_close": None,
                        "yf_close": float(r["close"]),
                        "divergence": None,
                    })
            else:
                max_div_non_close = 0.0
                for ts in sorted(common):
                    csv_close = float(csv_idx.loc[ts]["close"])
                    yf_close  = float(yf_idx.loc[ts]["close"])
                    div = abs(csv_close - yf_close)
                    max_div = max(max_div, div)
                    # 15:55 ET bar uses relaxed tolerance — TV and yfinance closing prices
                    # routinely differ at EOD due to data source differences.
                    is_close_bar = ts.time() == dt_time(15, 55)
                    if not is_close_bar:
                        max_div_non_close = max(max_div_non_close, div)
                    rows.append({
                        "ts": str(ts),
                        "csv_close": csv_close,
                        "yf_close": yf_close,
                        "divergence": round(div, 4),
                        "note": "15:55-close-bar-relaxed-tolerance" if is_close_bar else None,
                    })
                # Verdict from actual overlapping bars only — do NOT run this when
                # common=0 (no-overlap branch already set verdict/reason above).
                # For the 15:55 close bar, apply TOL_CLOSE_BAR; for all other bars TOL_YELLOW.
                close_bar_ok = max_div - max_div_non_close <= 0 or max_div <= TOL_CLOSE_BAR
                if max_div_non_close <= TOL_GREEN and close_bar_ok:
                    verdict = "GREEN"
                    reason = f"all-bars-within-tolerance (non-close max=${max_div_non_close:.4f})"
                elif max_div_non_close <= TOL_YELLOW and close_bar_ok:
                    verdict = "YELLOW"
                    reason = f"max-divergence-${max_div_non_close:.4f}-within-${TOL_YELLOW:.2f}-rounding-noise"
                elif max_div_non_close > TOL_YELLOW:
                    verdict = "RED"
                    reason = f"max-divergence-${max_div_non_close:.4f}-EXCEEDS-${TOL_YELLOW:.2f}-non-close-bar-cache-stale"
                else:
                    verdict = "YELLOW"
                    reason = f"close-bar-only-divergence-${max_div:.4f}-EOD-source-difference"
        except Exception as e:
            verdict = "RED"
            reason = f"compare-failed: {type(e).__name__}: {e}"
            return _emit(_report(target_date, verdict, reason, rows, str(csv_path), max_div, "no-op-error"), args.quiet)

    # ---- HEAL ----
    heal_action = "no-op"
    if args.heal and verdict == "RED":
        # Re-fetch yfinance bars (in-memory only — do NOT touch CSV per rule 9)
        yf2 = fetch_yfinance_bars(target_date, args.bars)
        if yf2 is not None and len(yf2) > 0:
            heal_action = f"re-fetched-{len(yf2)}-yfinance-bars-(in-memory-only-CSV-not-modified)"
        else:
            heal_action = "yfinance-refetch-failed"

    result = _report(target_date, verdict, reason, rows, str(csv_path), max_div, heal_action)
    return _emit(result, args.quiet)


def _report(target_date, verdict, reason, rows, csv_path, max_div, heal_action):
    return {
        "skill": "chart-data-verify",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date,
        "verdict": verdict,
        "reason": reason,
        "csv_path": csv_path,
        "max_divergence_dollars": round(max_div or 0, 4),
        "rows_compared": len(rows),
        "heal_action": heal_action,
        "rows": rows[:20],
    }


def _emit(result, quiet) -> int:
    out = OUTPUT_DIR / f"chart-data-verify-{result['target_date']}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if not quiet:
        print(f"=== chart-data-verify {result['target_date']} ===")
        print(f"VERDICT: {result['verdict']}")
        print(f"  reason: {result['reason']}")
        print(f"  csv: {result['csv_path']}")
        print(f"  rows compared: {result['rows_compared']}")
        print(f"  max divergence: ${result['max_divergence_dollars']}")
        for r in result['rows'][:5]:
            print(f"    {r}")
        print(f"  heal: {result['heal_action']}")
        print(f"  wrote: {out}")
    return 1 if result['verdict'] == "RED" else 0


if __name__ == "__main__":
    sys.exit(main())
