"""trendline_timeframe_matrix_2026_08_09.py -- data-driven answer to J's literal question:
"what time frame do we draw them on for which markets."

Uses `backtest/lib/trendline_detector.py` (the new pivot-anchored detector) to measure, per
drawing timeframe, whether the tape actually RESPECTS lines drawn there: touch-respect rate
(does price bounce away after testing a line, vs. break through) and forward-return
conditional on a touch (favorable direction = away from the line).

SCOPE: SPY intraday only (this project's live instrument). MES/futures swing timeframes are
explicitly out of this agent's lane (sibling doing MES swing validation) -- noted, not tested.

DATA HONESTY (disclosed up front, not discovered after a disappointing result):
  - 5m/15m/30m/1h columns run over the FULL population (`autoresearch.recency_check.
    load_merged_spy_vix()`, 399 trading days 2025-01-02..2026-08-07 as of this run). 15m/30m/1h
    are RESAMPLED from the native 5m bars (lossless downsampling -- a real, cached 15m/30m/1h
    bar is not a materially different object from a same-window OHLC aggregate of 5m bars).
  - 1m has NO cached population file in this repo (`backtest/data/` holds 5m-native SPY only).
    Rather than skip the column, this script pulls a BOUNDED REAL sample (most recent 25
    trading days -- matches `autoresearch/recency_check.py`'s own RECENCY_LOOKBACK_TRADING_DAYS
    convention) via direct Alpaca IEX REST (same un-blockable, already-wired, $0 credential
    path `trendline_engine.fetch_spy_5m` uses, generalized to timeframe=1Min). This column is
    SAMPLE-sized (n~25 days), not population-sized -- reported as such, never blended into the
    other columns' totals.

EVALUATION CADENCE (compute-bounded, disclosed): evaluating every native bar at 5m over the
full 399-day population is ~31k detector calls; at ~0.02-0.05s/call that is tens of minutes.
This script evaluates on a ~15-MINUTE WALL-CLOCK cadence (5m: every 3rd bar, 15m/30m/1h: every
native bar) so every timeframe column gets a comparable NUMBER of evaluation points rather than
a cadence that favors finer timeframes by construction. Lookback per timeframe is held at a
constant ~3-TRADING-DAY WALL-CLOCK span (not a constant bar count) so "how far back do we look
to draw a line" is the actual, comparable question being answered.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/trendline_timeframe_matrix_2026_08_09.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "autoresearch"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from recency_check import load_merged_spy_vix  # noqa: E402
from _edgehunt_vwap_continuation import _normalize_spy  # noqa: E402
from lib import trendline_detector as td  # noqa: E402

OUT_JSON = REPO / "analysis" / "deep-research" / "trendline-timeframe-matrix-2026-08-09.json"

RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)

# ~3 trading days of RTH lookback, held constant in WALL-CLOCK terms across timeframes (not
# bar count) -- 78 RTH 5m bars/day * 3 = 234.
LOOKBACK_TRADING_DAYS = 3
BARS_PER_RTH_DAY_5M = 78

TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "1m": 1}

# Forward-return window held at ~60 minutes of wall-clock time across every timeframe.
FORWARD_MINUTES = 60

MIN_TOUCHES = 3
MIN_BARS_BETWEEN_TOUCHES_MIN = 30   # ~30 minutes between touches, translated to bars per TF
MIN_SPAN_MIN = 60                    # ~60 minutes minimum anchor-pair span, translated per TF
TOUCH_TOLERANCE_DOLLARS = 0.20       # backtest/lib/trendlines.py precedent, see detector module

RECENT_SAMPLE_TRADING_DAYS = 25      # matches recency_check.py's RECENCY_LOOKBACK_TRADING_DAYS


def log(m: str) -> None:
    print(f"[tf-matrix] {m}", flush=True)


# --------------------------------------------------------------------------- resampling
def _resample_rth(spy_5m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """RTH-only OHLC resample, grouped BY CALENDAR DAY first so a bucket never spans an
    overnight gap (matches the per-day-groupby philosophy already used elsewhere in this
    codebase, e.g. orchestrator.py's _compute_htf_15m_stack)."""
    if minutes == 5:
        return spy_5m.copy()
    frames = []
    for _, day_df in spy_5m.groupby("date", sort=True):
        d = day_df.set_index("timestamp_et").sort_index()
        agg = d.resample(f"{minutes}min", label="left", closed="left", origin="start_day").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["open"])
        agg = agg.reset_index()
        agg["date"] = agg["timestamp_et"].dt.date
        frames.append(agg)
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- native 1m sample
def _fetch_spy_1m_sample(trading_days: list, n_days: int) -> Optional[pd.DataFrame]:
    """Bounded REAL 1-minute SPY sample via direct Alpaca IEX REST -- same credential/endpoint
    path as `trendline_engine.fetch_spy_5m`, generalized to timeframe=1Min. Returns None (never
    raises) on any failure -- this column is a bonus, its absence must not crash the matrix."""
    try:
        import urllib.request

        creds_path = REPO / ".mcp.json"
        env = json.loads(creds_path.read_text(encoding="utf-8"))["mcpServers"]["alpaca"]["env"]
        key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    except Exception as exc:  # noqa: BLE001
        log(f"1m sample: could not load Alpaca creds ({exc}) -- skipping 1m column")
        return None

    recent_days = sorted(trading_days)[-n_days:]
    start = dt.datetime.combine(recent_days[0], dt.time(0, 0)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (dt.datetime.combine(recent_days[-1], dt.time(0, 0)) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min"
            f"&start={start}&end={end}&feed=iex&sort=asc&limit=10000&adjustment=raw")
    bars: list[dict] = []
    url = base
    try:
        for _ in range(60):
            req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.loads(r.read())
            bars.extend(payload.get("bars", []))
            token = payload.get("next_page_token")
            if not token:
                break
            url = base + f"&page_token={token}"
    except Exception as exc:  # noqa: BLE001
        log(f"1m sample: REST fetch failed ({exc}) -- skipping 1m column")
        return None

    if not bars:
        log("1m sample: 0 bars returned -- skipping 1m column")
        return None
    df = pd.DataFrame(bars).rename(columns={"t": "timestamp_et", "o": "open", "h": "high",
                                             "l": "low", "c": "close", "v": "volume"})
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    rth = (df["t"] >= RTH_START) & (df["t"] < RTH_END)
    df = df.loc[rth].sort_values("timestamp_et").reset_index(drop=True)
    log(f"1m sample: {len(df)} RTH bars across {df['date'].nunique()} trading days "
        f"({df['date'].min()}..{df['date'].max()})")
    return df


# --------------------------------------------------------------------------- evaluation
def evaluate_timeframe(df: pd.DataFrame, timeframe: str, *, cadence_bars: int) -> dict:
    tf_minutes = TIMEFRAME_MINUTES[timeframe]
    bars = td.bars_from_dataframe(df)
    n = len(bars)
    lookback_bars = max(20, (LOOKBACK_TRADING_DAYS * BARS_PER_RTH_DAY_5M * 5) // tf_minutes)
    forward_bars = max(1, FORWARD_MINUTES // tf_minutes)
    min_span_bars = max(3, MIN_SPAN_MIN // tf_minutes)
    min_bars_between = max(2, MIN_BARS_BETWEEN_TOUCHES_MIN // tf_minutes)
    warmup = lookback_bars + 2

    touches: list[dict] = []
    n_evals = 0
    t0 = time.time()
    idx = warmup
    while idx < n - forward_bars:
        n_evals += 1
        window_start = max(0, idx - lookback_bars)
        window = bars[window_start: idx + 1]
        lines = td.detect_trendlines(
            window, kinds=("resistance", "support"), anchor_mode="wick",
            min_touches=MIN_TOUCHES, min_bars_between_touches=min_bars_between,
            min_span_bars=min_span_bars, touch_tolerance_dollars=TOUCH_TOLERANCE_DOLLARS,
            max_lines_per_kind=1, symbol="SPY", timeframe=timeframe,
        )
        for ln in lines:
            if ln.status != "testing":
                continue
            fwd_idx = idx + forward_bars
            if fwd_idx >= n:
                continue
            touch_close = bars[idx].close
            fwd_close = bars[fwd_idx].close
            favorable = (fwd_close - touch_close) if ln.kind == "support" else (touch_close - fwd_close)
            touches.append({
                "bar_index": idx, "kind": ln.kind, "line_id": ln.line_id,
                "touch_count_at_detection": ln.touch_count,
                "forward_return_favorable": round(favorable, 4),
                "respected": bool(favorable > 0),
            })
        idx += cadence_bars
    elapsed = time.time() - t0

    n_touches = len(touches)
    n_respected = sum(1 for t_ in touches if t_["respected"])
    mean_fwd = (sum(t_["forward_return_favorable"] for t_ in touches) / n_touches) if n_touches else None
    return {
        "timeframe": timeframe, "n_bars": n, "n_evaluations": n_evals,
        "lookback_bars": lookback_bars, "forward_bars": forward_bars,
        "min_span_bars": min_span_bars, "min_bars_between_touches": min_bars_between,
        "cadence_bars": cadence_bars, "elapsed_sec": round(elapsed, 1),
        "n_touches": n_touches,
        "touch_respect_rate": round(n_respected / n_touches, 4) if n_touches else None,
        "mean_forward_return_favorable": round(mean_fwd, 4) if mean_fwd is not None else None,
        "n_resistance_touches": sum(1 for t_ in touches if t_["kind"] == "resistance"),
        "n_support_touches": sum(1 for t_ in touches if t_["kind"] == "support"),
    }


def main() -> int:
    t_start = time.time()
    log("loading population ...")
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    rth = (spy["t"] >= RTH_START) & (spy["t"] < RTH_END)
    spy = spy.loc[rth].reset_index(drop=True)
    trading_days = sorted(spy["date"].unique())
    log(f"population: {len(spy)} RTH 5m rows, {len(trading_days)} trading days, "
        f"{trading_days[0]}..{trading_days[-1]}")

    results: dict[str, dict] = {}

    for tf, cadence in (("5m", 3), ("15m", 1), ("30m", 1), ("1h", 1)):
        log(f"=== {tf} (full {len(trading_days)}-day population) ===")
        df_tf = _resample_rth(spy, TIMEFRAME_MINUTES[tf])
        res = evaluate_timeframe(df_tf, tf, cadence_bars=cadence)
        log(f"  n_evals={res['n_evaluations']} n_touches={res['n_touches']} "
            f"respect_rate={res['touch_respect_rate']} mean_fwd_favorable={res['mean_forward_return_favorable']} "
            f"({res['elapsed_sec']}s)")
        res["population"] = "full"
        res["n_trading_days"] = len(trading_days)
        results[tf] = res

    log("=== 1m (bounded recent sample) ===")
    df_1m = _fetch_spy_1m_sample(trading_days, RECENT_SAMPLE_TRADING_DAYS)
    if df_1m is not None and len(df_1m) > 0:
        res = evaluate_timeframe(df_1m, "1m", cadence_bars=5)
        log(f"  n_evals={res['n_evaluations']} n_touches={res['n_touches']} "
            f"respect_rate={res['touch_respect_rate']} mean_fwd_favorable={res['mean_forward_return_favorable']} "
            f"({res['elapsed_sec']}s)")
        res["population"] = "sample"
        res["n_trading_days"] = df_1m["date"].nunique()
        results["1m"] = res
    else:
        results["1m"] = {"timeframe": "1m", "population": "unavailable",
                          "note": "no cached 1m population; live REST fetch failed or returned 0 bars"}

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "population_window": f"{trading_days[0]}..{trading_days[-1]}",
        "n_trading_days_full_population": len(trading_days),
        "instrument": "SPY (0DTE intraday) -- MES/futures swing timeframes out of this agent's "
                       "lane, not tested here",
        "method": {
            "lookback": f"~{LOOKBACK_TRADING_DAYS} trading days wall-clock, translated to bars per timeframe",
            "forward_window_minutes": FORWARD_MINUTES,
            "min_touches": MIN_TOUCHES,
            "touch_tolerance_dollars": TOUCH_TOLERANCE_DOLLARS,
            "anchor_mode": "wick",
            "evaluation_cadence": "~15 minutes wall-clock (5m: every 3rd bar; 15m/30m/1h: every native bar)",
            "respected_definition": "forward_return_favorable > 0 -- price moved AWAY from the "
                                     "line (up off support / down off resistance) over the next "
                                     "~60 minutes after a 'testing' touch",
        },
        "results": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"TOTAL elapsed: {round(time.time() - t_start, 1)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
