"""trendline_study_sight-check -- T4 SIGHT CHECK, 2026-09-03.

READ-ONLY study script. Imports backtest/lib/filters.py (LIVE trigger code) and
backtest/lib/trendline_detector.py (general/shadow-capable detector) as libraries --
never modifies them, places no orders, makes no network calls. All bars come from the
already-cached backtest/data/spy_sip_cache/spy_5m_<date>.json files.

QUESTION: would the LIVE engine (heartbeat_core.py) have seen J's rising-support line at
the 10:55 ET candle today? This script:

  1. Reconstructs EXACTLY the 5m bar window heartbeat_core._build_payload() would have
     built for a tick where the 10:55 candle is the trigger bar (trig_idx = n-2), using
     the SAME RTH-only filter (>=09:30 ET, <16:00 ET) applied BEFORE windowing, and the
     SAME W=150 bounded window, spanning back across prior sessions as needed (today's
     RTH bars alone, 09:30-10:55, are only 17 bars -- nowhere near the 62 bars
     detect_trendline_reclaim_bullish requires (lookback_bars=60 + 2), so prior-session
     RTH bars are concatenated exactly as the live multi-day fetch would supply them).
  2. Runs backtest.lib.filters.detect_trendline_reclaim_bullish -- the actual, live,
     shadow-only bull trendline function -- against that exact window, bar-for-bar, and
     quotes the return value plus every intermediate quantity (pivot search result,
     slope sign, reached/closed-above/green checks).
  3. Cross-checks against the RTH-only 09:30-16:00 slice actually used by the LIVE code
     (the multi-day df IS RTH-only before AND after the window, per heartbeat_core.py
     line 902-903) to show explicitly that premarket bars never enter this function's
     input at all -- independent of whether they'd matter to the geometry.

AGGREGATION / LABEL CONVENTION: bar label T = open-of-interval [T, T+5min). Matches the
existing spy_5m_<date>.json cache directly (verified: no re-aggregation from 1m needed --
the 5m cache already exists for every date used here with the same T3/T2-study-verified
convention).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backtest"))

from backtest.lib.filters import (  # noqa: E402
    detect_trendline_reclaim_bullish,
    detect_trendline_rejection_bearish,
    TRENDLINE_LOOKBACK_BARS,
    TRENDLINE_MIN_SWINGS,
)
from crypto.lib.bar import Bar  # noqa: E402
from backtest.lib.trendline_detector import detect_trendlines  # noqa: E402

CACHE_DIR = REPO_ROOT / "backtest" / "data" / "spy_sip_cache"
OUT_DIR = REPO_ROOT / "analysis" / "deep-research" / "2026-09-03-money"
OUT_JSON = OUT_DIR / "trendline-sight-check.json"
OUT_MD = OUT_DIR / "trendline-sight-check.md"

RTH_START = "09:30:00"
RTH_END = "16:00:00"  # exclusive, matches heartbeat_core.py's dt.time(16,0) exclusive bound
W = 150


def load_5m_cache(date: str) -> pd.DataFrame:
    f = CACHE_DIR / f"spy_5m_{date}.json"
    raw = json.loads(f.read_text(encoding="utf-8"))["bars"]
    df = pd.DataFrame(raw).rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def rth_only(df: pd.DataFrame) -> pd.DataFrame:
    """Byte-identical to heartbeat_core.py _build_payload lines 902-903 (naive local
    ET timestamps here, so no tz_convert needed -- the cache is already ET-local per
    T2/T3 study verification)."""
    t = df["timestamp"].dt.time
    import datetime as dt
    mask = (t >= dt.time(9, 30)) & (t < dt.time(16, 0))
    return df[mask].reset_index(drop=True)


def main() -> dict:
    # Multi-day RTH-only concatenation, exactly what heartbeat_core.py's multi-day
    # _fetch_spy_5m() + the RTH filter would hand to the W=150 window slice. Using
    # 3 prior sessions is generous headroom over the 62-bar minimum
    # detect_trendline_reclaim_bullish needs (60 lookback + 2); Sept 1 alone (78 RTH
    # bars) + today's 17 bars-through-10:55 = 95, already comfortably above 62.
    dates = ["2026-09-01", "2026-09-02", "2026-09-03"]
    frames = []
    per_day_rth_counts = {}
    for d in dates:
        raw = load_5m_cache(d)
        rth = rth_only(raw)
        per_day_rth_counts[d] = int(len(rth))
        frames.append(rth)
    full_df = pd.concat(frames, ignore_index=True)

    # Truncate TODAY's frame to bars up to and including the 10:55 candle (the trigger
    # bar we're testing), THEN append the 11:00 bar as the forward-confirmation slot --
    # this is exactly the shape heartbeat_core.py's `win` has when trig_idx points at
    # the 10:55 bar (trig_idx = n-2, last bar n-1 = forward-confirmation bar).
    today_mask = full_df["timestamp"].dt.date.astype(str) == "2026-09-03"
    today_idx = full_df[today_mask].index
    bar_1055_positions = full_df.index[full_df["timestamp"] == pd.Timestamp("2026-09-03 10:55:00")]
    bar_1100_positions = full_df.index[full_df["timestamp"] == pd.Timestamp("2026-09-03 11:00:00")]
    assert len(bar_1055_positions) == 1, f"expected exactly one 10:55 bar, got {len(bar_1055_positions)}"
    assert len(bar_1100_positions) == 1, f"expected exactly one 11:00 bar, got {len(bar_1100_positions)}"
    idx_1055 = int(bar_1055_positions[0])
    idx_1100 = int(bar_1100_positions[0])

    df_upto_1100 = full_df.iloc[: idx_1100 + 1].reset_index(drop=True)

    # W=150 window slice, byte-identical to heartbeat_core.py line 906-907.
    win = df_upto_1100.iloc[-W:].reset_index(drop=True)
    n = len(win)
    trig_idx = n - 2  # heartbeat_core.py line 917
    trig_bar = win.iloc[trig_idx]
    forward_bar = win.iloc[n - 1]

    assert trig_bar["timestamp"] == pd.Timestamp("2026-09-03 10:55:00"), \
        f"trig bar mismatch: {trig_bar['timestamp']}"
    assert forward_bar["timestamp"] == pd.Timestamp("2026-09-03 11:00:00"), \
        f"forward bar mismatch: {forward_bar['timestamp']}"

    prior_bars = win.iloc[: trig_idx + 1][["open", "high", "low", "close", "volume"]].astype(float).reset_index(drop=True)
    bar_series = win.iloc[trig_idx]

    result = {
        "meta": {
            "stamp_et": "2026-09-03T17:40",
            "question": "would heartbeat_core.py have seen J's 10:55 rising-support line via the LIVE trigger machinery",
            "rth_filter": ">=09:30:00 ET and <16:00:00 ET, applied to the FULL multi-day df BEFORE the W=150 window slice (heartbeat_core.py lines 902-903, 906-907) -- premarket bars (04:00-09:29:59) are excluded from `df` itself, never reach `win`, `prior_bars`, or any detector call",
            "per_day_rth_bar_counts": per_day_rth_counts,
            "window_len_n": n,
            "trig_idx": trig_idx,
            "trig_bar_timestamp": str(trig_bar["timestamp"]),
            "forward_confirmation_bar_timestamp": str(forward_bar["timestamp"]),
            "trig_bar_ohlc": {"o": float(trig_bar["open"]), "h": float(trig_bar["high"]),
                               "l": float(trig_bar["low"]), "c": float(trig_bar["close"])},
            "TRENDLINE_LOOKBACK_BARS": TRENDLINE_LOOKBACK_BARS,
            "TRENDLINE_MIN_SWINGS": TRENDLINE_MIN_SWINGS,
            "min_bar_idx_required": TRENDLINE_LOOKBACK_BARS + 2,
            "bar_idx_sufficient": trig_idx >= (TRENDLINE_LOOKBACK_BARS + 2),
        },
    }

    # ---- 1. THE LIVE FUNCTION, byte-identical call shape to evaluate_bullish_setup's
    # invocation (filters.py ~1464-1467): ctx.bar, ctx.prior_bars, ctx.bar_idx,
    # lookback_bars=TRENDLINE_LOOKBACK_BARS, min_swings=TRENDLINE_MIN_SWINGS
    # (proximity_pct / require_decreasing left at function defaults, same as the live call).
    live_reclaim_result = detect_trendline_reclaim_bullish(
        bar_series, prior_bars, trig_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS,
        min_swings=TRENDLINE_MIN_SWINGS,
    )
    live_rejection_result = detect_trendline_rejection_bearish(
        bar_series, prior_bars, trig_idx,
        lookback_bars=TRENDLINE_LOOKBACK_BARS,
        min_swings=TRENDLINE_MIN_SWINGS,
    )
    result["live_function_calls"] = {
        "detect_trendline_reclaim_bullish": live_reclaim_result,
        "detect_trendline_rejection_bearish": live_rejection_result,
        "note": "Both search ONLY descending HIGH pivots (window['high'].values, "
                "require_decreasing pivot check) -- the reclaim function is the byte-"
                "identical pivot search to the rejection function, terminal check flipped "
                "(closes ABOVE + green vs closes BELOW + red). Neither has any code path "
                "that fits a line through LOWS. J's line is a rising SUPPORT line (through "
                "LOWS) -- a geometry class this function cannot represent, independent of "
                "whether the specific numeric fit would have matched.",
    }

    # ---- 2. Manually replay the SAME sequential-descending-peaks search the live
    # function runs, to show WHY it returns None: quote the actual pivot search outcome
    # (do the last min_swings highs even form a candidate descending line at all).
    MIN_BAR_SEPARATION = 10
    lookback = TRENDLINE_LOOKBACK_BARS
    start = max(0, trig_idx - lookback)
    window = prior_bars.iloc[start:trig_idx]
    highs = window["high"].values
    pivots = []
    search_start = 0
    decreasing_ok = True
    for _ in range(TRENDLINE_MIN_SWINGS):
        if search_start >= len(highs):
            break
        sub = highs[search_start:]
        if len(sub) == 0:
            break
        rel_pos = int(sub.argmax())
        pos = search_start + rel_pos
        val = float(highs[pos])
        if pivots and val >= pivots[-1][1]:
            decreasing_ok = False
        pivots.append((int(window.index[pos]) if hasattr(window, "index") else pos, val))
        search_start = pos + MIN_BAR_SEPARATION
    result["pivot_search_replay"] = {
        "lookback_window_len": int(len(window)),
        "pivots_found_highs": pivots,
        "n_pivots": len(pivots),
        "min_swings_required": TRENDLINE_MIN_SWINGS,
        "sequential_pivots_strictly_decreasing": decreasing_ok if len(pivots) >= 2 else None,
        "conclusion": (
            "insufficient pivots" if len(pivots) < TRENDLINE_MIN_SWINGS
            else ("pivots found but NOT strictly decreasing -- today's structure into "
                  "10:55 is a rising market (higher highs), so the mandatory "
                  "require_decreasing check on HIGH pivots fails by construction; a "
                  "descending-resistance line cannot be fit through an uptrend's highs"
                  if not decreasing_ok else "descending line fit successfully (see live_function_calls for terminal outcome)")
        ),
    }

    # ---- 3. The GENERAL/shadow-capable detector (trendline_detector.py -- has a real
    # support/rising-line code path, unlike the two live functions above) run over the
    # EXACT SAME RTH-only, multi-day, no-premarket window the live engine would have had
    # available at this tick (win, ending at trig_idx = the 10:55 bar). This isolates the
    # PREMARKET-EXCLUSION question from the SUPPORT-KIND-NOT-SEARCHED question: if this
    # also finds nothing, the RTH-only window itself (not just the live function's
    # resistance-only geometry) is insufficient to reconstruct J's specific line.
    def _to_bars(frame: pd.DataFrame) -> tuple:
        import datetime as _dt
        out = []
        for _, r in frame.iterrows():
            # Cache timestamps are naive ET-local strings; attach UTC tzinfo only to
            # satisfy Bar's tz-aware invariant -- detect_trendlines here is used purely
            # for bar-INDEX-relative pivot/slope geometry, never real wall-clock math, so
            # the (incorrect) absolute offset does not affect any value this script reads.
            ts = r["timestamp"].to_pydatetime().replace(tzinfo=_dt.timezone.utc)
            out.append(Bar(open_time=ts, open=float(r["open"]), high=float(r["high"]),
                            low=float(r["low"]), close=float(r["close"]),
                            volume=float(r["volume"]), granularity_seconds=300, source="spy_sip_cache_5m"))
        return tuple(out)

    rth_only_bars = _to_bars(win.iloc[: trig_idx + 1])  # RTH-only, multi-day, thru 10:55, no look-ahead
    general_rth_only = detect_trendlines(
        rth_only_bars, kinds=("support",), anchor_mode="wick", require_slope="rising",
        symbol="SPY", timeframe="5m",
    )

    # Premarket-INCLUSIVE contrast run: same general detector, same as-of point (10:55),
    # but with today's premarket bars (04:00-09:29:59) included -- this is the bar set the
    # live engine's RTH filter (heartbeat_core.py:902-903) structurally never builds.
    today_full = load_5m_cache("2026-09-03")
    today_full_upto_1055 = today_full[today_full["timestamp"] <= pd.Timestamp("2026-09-03 10:55:00")].reset_index(drop=True)
    premkt_bars = _to_bars(today_full_upto_1055)
    general_with_premarket = detect_trendlines(
        premkt_bars, kinds=("support",), anchor_mode="wick", require_slope="rising",
        symbol="SPY", timeframe="5m",
    )

    def _line_to_dict(ln) -> dict:
        return {
            "kind": ln.kind, "anchor_mode": ln.anchor_mode,
            "anchors": [{"bar_index": a.bar_index, "price": a.price, "structure_label": a.structure_label}
                        for a in ln.anchors],
            "touch_count": ln.touch_count, "slope_per_bar": ln.slope_per_bar,
            "current_value": ln.current_value, "status": ln.status,
        }

    result["general_detector_support_rising_search"] = {
        "note": "backtest/lib/trendline_detector.py::detect_trendlines(kinds=('support',), "
                "anchor_mode='wick', require_slope='rising') -- the general library that DOES "
                "have a support/rising-line code path (unlike the two live functions above). "
                "Zero consumers on the entry OR shadow-ledger path today (only chart-drawing / "
                "research scripts import it) -- included here purely to isolate whether the "
                "premarket exclusion, independent of the live function's resistance-only "
                "geometry, is itself sufficient to make J's specific line unreconstructable.",
        "rth_only_multiday_no_premarket": {
            "n_bars_fed": len(rth_only_bars),
            "n_lines_found": len(general_rth_only),
            "lines": [_line_to_dict(x) for x in general_rth_only],
        },
        "premarket_inclusive_today_only": {
            "n_bars_fed": len(premkt_bars),
            "n_lines_found": len(general_with_premarket),
            "lines": [_line_to_dict(x) for x in general_with_premarket],
        },
    }

    return result


if __name__ == "__main__":
    import datetime as _dt
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = main()
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
