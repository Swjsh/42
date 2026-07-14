"""context_bundle_producer.py -- multi-timeframe TREND-ALIGNMENT context bundle (Phase 0).

WHY THIS EXISTS (J, 2026-07-14: "how are we properly reviewing previous day levels and
correlating them into our 'eyes' of the day and trends... do we cross-correlate any
information before acting on signals? maybe it should be calculated beforehand and tagged
onto the signal"). The audit (markdown plan, 2026-07-14) proved the live engine
cross-correlates prior-day LEVELS (key-levels.json, via heartbeat_core._read_levels) but
NEVER factors the multi-timeframe trend into whether/how strongly it acts -- the intraday
structure_veto only looks at TODAY's 5m bars (engine_cli._classify_sameday_5m). This
producer closes the "does daily/hourly/15m agree with the signal" gap J named, pre-computed
OFF the hot path (heavy multi-day correlation has no business running inline on a 1-min
heartbeat tick) and written to disk for heartbeat_core to read + TAG onto the decision row.

v1 SCOPE (J's explicit call, 2026-07-14): TREND ALIGNMENT ONLY. Macro/event proximity,
confluence-zone strength, and hard context-gating are pre-approved fast-follows, NOT this
phase -- start lean, prove the mechanism first (Phase 1 correlation study), before adding
more dimensions to the bundle.

PHASE 0 IS LOGGED-ONLY / ZERO-BEHAVIOR-CHANGE: heartbeat_core.py tags this bundle onto
bar_ctx + the decision row for VISIBILITY only. Nothing on the decision path (score_bar,
evaluate_gates, _derive_tier) reads it this phase. See heartbeat_core._read_context_bundle
+ the "context_bundle" keys in _build_payload / run_account, and the RED-proof guard test
backtest/tests/test_context_bundle_tag_no_behavior_change.py.

STRUCTURE PRIMITIVE: reuses crypto/lib/market_structure.py::analyze_structure -- the SAME
swing-sequence structure read the LIVE structure_veto gate already runs on today's 5m bars
via engine_cli._classify_sameday_5m (backtest/lib/engine/engine_cli.py:173-205). This module
mirrors that exact bars-list-of-dicts -> crypto.lib.bar.Bar -> analyze_structure conversion,
just across 3 higher timeframes instead of one intraday one.

PHASE 1 REUSE (amendment, 2026-07-14): `compute_trend_alignment` is AS-OF-BOUNDED and pure
by construction -- it has no notion of "now", only of whatever rows the caller's DataFrames
contain. Phase 1's walk-forward correlation study will fetch daily/hourly/15m history ONCE
and call this SAME function per historical decision timestamp T on bars sliced to <=T, with
zero look-ahead (C6) and zero re-derivation of the math. See compute_trend_alignment's own
docstring for the full contract + the guard test that proves it.

MODES:
  `python context_bundle_producer.py`         -- write automation/state/context-bundle.json,
                                                   print a one-line summary (scheduled-task
                                                   cadence: Gamma_ContextBundle, every 5 min RTH).
  `python context_bundle_producer.py --once`  -- same write, PLUS the full bundle JSON printed
                                                   to stdout (manual verification / --once fires).

FAIL-OPEN: any timeframe fetch failure degrades that timeframe to unavailable (never crashes,
never fabricates a trend) and sets the bundle's top-level `degraded: true` + `degraded_reason`.
$0, pure Python + pandas, no LLM, no TradingView MCP -- direct Alpaca REST (same un-blockable
path as heartbeat_core._fetch_spy_5m / sight_beacon.py).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "context-bundle-producer.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "context-bundle-producer.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
# so `crypto.lib.*` (PEP-420 namespace package, no crypto/__init__.py) resolves,
# and `et_clock` (bare module in this same directory) resolves whether this file is
# run directly or loaded by path via importlib (heartbeat_core.py's own convention).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from et_clock import et_now as _et_now  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import DEFAULT_WINDOW, analyze_structure  # noqa: E402

STATE = REPO / "automation" / "state"
OUT_F = STATE / "context-bundle.json"

MIN_BARS = 10   # below this, a timeframe's structure read is noise, not signal -- unavailable
VOTE = {"uptrend": 1, "downtrend": -1, "range": 0, "unknown": 0}


# ----- pure math: the single source of truth Phase 1's scorer will import -----------------
def _df_to_bars(df: "pd.DataFrame | None", granularity_seconds: int, source: str) -> list[Bar]:
    """DataFrame(timestamp, open, high, low, close, volume) -> list[Bar], oldest first.

    PURE (no I/O). Skips any row that fails to convert (NaN OHLC, bad timestamp, high<low)
    rather than raising -- callers treat a short/empty result as 'insufficient data'."""
    out: list[Bar] = []
    if df is None or len(df) == 0:
        return out
    for _, row in df.iterrows():
        try:
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            v = float(row["volume"]) if row.get("volume") == row.get("volume") else 0.0
            if any(x != x for x in (o, h, l, c)):  # NaN check (x != x is True only for NaN)
                continue
            out.append(Bar(open_time=ts, open=o, high=h, low=l, close=c, volume=v,
                            granularity_seconds=granularity_seconds, source=source))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda b: b.open_time)
    return out


def _tf_state(df: "pd.DataFrame | None", *, source: str, granularity_seconds: int,
              window: int, min_bars: int) -> dict:
    """PURE: one timeframe's df -> a JSON-serializable trend-state dict. Never raises --
    any conversion/structure-read failure degrades to trend='unknown', available=False."""
    bars = _df_to_bars(df, granularity_seconds, source)
    if len(bars) < min_bars:
        return {"trend": "unknown", "confidence": 0.0, "trend_basis": "insufficient",
                "available": False, "n_bars": len(bars), "reason": "insufficient_bars"}
    try:
        read = analyze_structure(bars, window=window)
    except Exception as e:  # noqa: BLE001 -- a structure-read bug must degrade, never crash the bundle
        return {"trend": "unknown", "confidence": 0.0, "trend_basis": "insufficient",
                "available": False, "n_bars": len(bars),
                "reason": f"analyze_structure_error: {type(e).__name__}"}
    return {"trend": read.trend, "confidence": round(float(read.confidence), 4),
            "trend_basis": read.trend_basis, "available": True, "n_bars": len(bars), "reason": None}


def compute_trend_alignment(daily_df: "pd.DataFrame | None", hourly_df: "pd.DataFrame | None",
                             m15_df: "pd.DataFrame | None", *, window: int = DEFAULT_WINDOW,
                             min_bars: int = MIN_BARS) -> dict:
    """PURE, side-effect-free, single source of truth for the trend-alignment math -- Phase 1's
    correlation scorer imports this SAME function so the walk-forward replay and the live
    producer can never drift apart. Does NO I/O; every input is a plain OHLCV DataFrame
    (columns: timestamp, open, high, low, close, volume) the caller already fetched.

    Runs crypto.lib.market_structure.analyze_structure on each of the 3 timeframes -- the
    SAME structure primitive the live structure_veto gate already runs on today's 5m bars
    (engine_cli._classify_sameday_5m) -- to get an up/down/range/unknown trend + a heuristic
    confidence per timeframe.

    SCORING CONVENTION (documented here because it's the one thing every consumer must agree
    on): each timeframe casts a vote -- +1 if its trend is 'uptrend', -1 if 'downtrend', 0 if
    'range'/'unknown'/unavailable (no data, insufficient bars, or a fetch that never arrived).
    `alignment_score` = sum of the 3 votes, an integer in [-3, +3].
      SIGN      = net directional lean: positive = net-bullish stack, negative = net-bearish
                  stack, zero = no net lean (either all-range/unknown, or the up/down votes
                  cancel).
      MAGNITUDE = strength of STACKED agreement: +/-3 means all 3 available timeframes agree
                  in the same direction (full alignment); +/-1 is ambiguous by construction --
                  it can mean "only 1 TF has a directional read" OR "2-vs-1 mixed" (e.g. daily
                  up + hourly down + 15m up nets to +1, which is NOT full alignment). Use
                  `trend_alignment` below for the strict per-direction read, not the score alone.

    `trend_alignment.bull.aligned` is True iff EVERY available timeframe read 'uptrend' (and
    at least one timeframe was available) -- the literal answer to J's question "do
    daily/hourly/15m agree with a bull signal?" `trend_alignment.bear` mirrors it for
    'downtrend'. A timeframe that's unavailable (no data) is excluded from the agree/disagree
    count on EITHER side -- it never manufactures false alignment.

    Returns a dict: {per_tf: {daily, hourly, m15}, alignment_score, trend_alignment,
    degraded, degraded_reasons}. `degraded` here means >=1 timeframe was unavailable to THIS
    function (insufficient/malformed data it was handed) -- distinct from main()'s top-level
    `degraded`, which also folds in upstream FETCH failures (network/auth) the pure function
    never sees.

    AS-OF-BOUNDED / NO-LOOK-AHEAD CONTRACT (load-bearing for Phase 1, added 2026-07-14): this
    function has NO notion of "now" or "latest" anywhere in its body or call chain (_tf_state,
    _df_to_bars, crypto.lib.market_structure.analyze_structure, classify_trend,
    find_swing_points are all pure over whatever rows the caller hands them). The result for a
    given set of input DataFrames depends ONLY on the rows those DataFrames contain -- it is
    a pure function of its arguments, full stop. Concretely: if the caller truncates
    daily_df/hourly_df/m15_df to rows with timestamp <= T before calling this function, the
    returned alignment is EXACTLY what would have been computed live at T -- appending more
    rows (bars from AFTER T) to any of the 3 DataFrames and re-calling with the truncated
    (<=T) slice again reproduces the identical result, byte for byte. This is what makes the
    function directly reusable, unmodified, for Phase 1's walk-forward historical replay
    (`backtest/tools/trend_alignment_correlation_study.py`, not yet built): fetch daily/
    hourly/15m history ONCE, then for each historical decision timestamp T, slice each
    DataFrame to `df[df.timestamp <= T]` and call this same function -- never re-derive the
    math, never let a live-only shortcut creep in. `main()` below is the ONLY place that
    reaches for "now" (via `_et_now()`/`datetime.now()`, purely for the fetch window and the
    `computed_at_et` timestamp) -- that code never executes inside this function. Guard:
    test_context_bundle_producer.py::test_compute_trend_alignment_is_as_of_bounded_no_lookahead.
    """
    per_tf = {
        "daily": _tf_state(daily_df, source="spy_daily", granularity_seconds=86400,
                            window=window, min_bars=min_bars),
        "hourly": _tf_state(hourly_df, source="spy_hourly", granularity_seconds=3600,
                             window=window, min_bars=min_bars),
        "m15": _tf_state(m15_df, source="spy_15m", granularity_seconds=900,
                          window=window, min_bars=min_bars),
    }
    votes = {tf: (VOTE.get(st["trend"], 0) if st["available"] else 0) for tf, st in per_tf.items()}
    alignment_score = int(sum(votes.values()))

    available_tfs = [tf for tf, st in per_tf.items() if st["available"]]
    bull_agree = [tf for tf in available_tfs if per_tf[tf]["trend"] == "uptrend"]
    bear_agree = [tf for tf in available_tfs if per_tf[tf]["trend"] == "downtrend"]
    trend_alignment = {
        "bull": {"agreeing_timeframes": bull_agree, "agree_count": len(bull_agree),
                 "available_count": len(available_tfs),
                 "aligned": bool(available_tfs) and len(bull_agree) == len(available_tfs)},
        "bear": {"agreeing_timeframes": bear_agree, "agree_count": len(bear_agree),
                 "available_count": len(available_tfs),
                 "aligned": bool(available_tfs) and len(bear_agree) == len(available_tfs)},
    }
    degraded_reasons = [f"{tf}: {st['reason']}" for tf, st in per_tf.items() if not st["available"]]
    return {
        "per_tf": per_tf,
        "alignment_score": alignment_score,
        "trend_alignment": trend_alignment,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


# ----- I/O: fetch + write (kept OUT of the pure function above) ---------------------------
def _load_alpaca_creds() -> tuple[str, str]:
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def _fetch_bars(timeframe: str, *, days_back: int, limit: int) -> tuple[pd.DataFrame, "str | None"]:
    """SPY OHLCV via direct Alpaca REST -- same un-blockable path as heartbeat_core's
    _fetch_spy_5m / sight_beacon.py (never TradingView MCP; off the hot path here, but the
    credential + request shape is identical so a stale key fails the same way everywhere).
    Returns (df, error). df is empty and error is a short string on ANY failure -- NEVER
    raises, so a single bad timeframe degrades that timeframe only (see main())."""
    try:
        import urllib.request
        key, sec = _load_alpaca_creds()
        start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe={timeframe}&start={start}"
               f"&limit={limit}&feed=iex&adjustment=raw&sort=asc")
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=15) as r:
            bars = json.loads(r.read()).get("bars", [])
        if not bars:
            return pd.DataFrame(), f"{timeframe}: empty bars response"
        df = pd.DataFrame([{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                           "close": b["c"], "volume": b["v"]} for b in bars])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.reset_index(drop=True), None
    except Exception as e:  # noqa: BLE001 -- fetch failure must degrade, never crash the producer
        return pd.DataFrame(), f"{timeframe}: {type(e).__name__}: {e}"


def main() -> int:
    """Fetch daily(~6mo)/hourly(~3wk)/15m(~5d) SPY bars, compute the trend-alignment bundle,
    write automation/state/context-bundle.json. Always returns 0 (fail-open) -- a failed
    fetch degrades that timeframe (and the bundle's top-level `degraded`), it never aborts
    the write; heartbeat_core must always find a bundle (possibly degraded) to read."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                     help="single run (the only mode this script has); also prints the full "
                          "bundle JSON to stdout for manual verification")
    args = ap.parse_args()

    try:
        daily_df, daily_err = _fetch_bars("1Day", days_back=190, limit=200)
        hourly_df, hourly_err = _fetch_bars("1Hour", days_back=25, limit=500)
        m15_df, m15_err = _fetch_bars("15Min", days_back=7, limit=500)

        result = compute_trend_alignment(daily_df, hourly_df, m15_df)
        fetch_errors = [e for e in (daily_err, hourly_err, m15_err) if e]
        reasons = fetch_errors + result["degraded_reasons"]
        degraded = bool(reasons)

        bundle = {
            "schema_version": 1,
            "computed_at_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
            "per_tf": result["per_tf"],
            "trend_alignment": result["trend_alignment"],
            "alignment_score": result["alignment_score"],
            "degraded": degraded,
            "degraded_reason": "; ".join(reasons) if reasons else None,
            "note": "TREND ALIGNMENT ONLY (v1 scope, J 2026-07-14 -- macro/confluence deferred). "
                    "LOGGED ONLY: not consumed by score/gates/_derive_tier this phase -- see "
                    "heartbeat_core._read_context_bundle + rec['context_bundle'].",
        }
    except Exception as e:  # noqa: BLE001 -- a scheduled fire must never break the chain
        bundle = {
            "schema_version": 1,
            "computed_at_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
            "per_tf": {}, "trend_alignment": {}, "alignment_score": 0,
            "degraded": True, "degraded_reason": f"producer crash: {type(e).__name__}: {e}",
            "note": "context_bundle_producer main() failed -- see degraded_reason. Fail-open: "
                    "this bundle is intentionally written so heartbeat_core's stale/absent "
                    "check has something concrete to age out.",
        }

    OUT_F.parent.mkdir(parents=True, exist_ok=True)
    OUT_F.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    if args.once:
        print(json.dumps(bundle, indent=2))
    else:
        pt = bundle.get("per_tf", {})
        print(f"[context_bundle_producer] alignment_score={bundle.get('alignment_score')} "
              f"degraded={bundle.get('degraded')} "
              f"daily={pt.get('daily', {}).get('trend')} "
              f"hourly={pt.get('hourly', {}).get('trend')} "
              f"m15={pt.get('m15', {}).get('trend')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
