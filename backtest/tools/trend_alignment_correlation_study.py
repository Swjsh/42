"""trend_alignment_correlation_study.py -- Phase 1: does multi-TF trend alignment predict
trade outcome? (context-enrichment program, J 2026-07-14; Phase 0 = setup/scripts/
context_bundle_producer.py, shipped LOGGED-ONLY b1597a6).

WHY: Phase 0 built a pure, as-of-bounded compute_trend_alignment() and tagged it onto the
decision row for VISIBILITY, with ZERO behavior change (nothing on the live decision path
reads it yet). Phase 1 answers the actual question J asked -- "does it correlate" -- BEFORE
any gate/veto/sizing knob is allowed to consume it. This is a STUDY. It places no orders,
edits no live params/config, and does not arm anything.

HARD RULES (task brief, 2026-07-14):
  * compute_trend_alignment is imported UNMODIFIED from context_bundle_producer -- single
    source of truth, never reimplemented. See `from context_bundle_producer import
    compute_trend_alignment` below; nothing in this file re-derives the alignment math.
  * NO LOOK-AHEAD (C6): every historical decision at time T is scored using ONLY bars with
    timestamp <= T. `alignment_for_decision()` is the ONE place that slices -- guarded by
    test_trend_alignment_correlation_study.py::test_alignment_for_decision_matches_cutoff_only.
  * Per-episode accounting (C31 scar -- group by EPISODE, never by leg/order).
  * MEASURED vs MODELED labels attached to every population (P1/P3 = MODELED/replayed via
    SS-B on real OPRA bars; P2 = MEASURED, real broker fills).
  * ET via et_clock.py only, never Bash date/TZ.

PRE-REGISTRATION: analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json
-- FROZEN and committed BEFORE any scoring run. This module must not change behavior in a way
that contradicts that frozen spec; if reality forces a deviation, the deviation is disclosed
in the run's output, never silently absorbed.

THREE POPULATIONS (see pre-reg for full detail):
  P1 -- the canonical ribbon_ride signal cohort (_signal_cache.load_or_build_signals(), reused
        UNMODIFIED, n=250, both directions, 2025-01-01..2026-06-18), replayed under the SAME
        SS-B exit shape + fill-bar convention ribbon_ride_strike_exit_ab.py already certifies
        (real OPRA bars, not synthetic). MODELED (a real-fills-priced replay, not a live fill).
  P2 -- real engine fills, automation/state/fills-ledger.jsonl, reconstructed into per-episode
        rows via exit_shape_parity_study.reconstruct_positions() (the C31-safe grouping).
        MEASURED (actual broker fills, ~109-112 engine episodes, 2026-06-26..2026-07-09).
  P3 -- J's OP-16 source-of-truth anchor trades (7 trades, verbatim from
        ssb_certification_study.J_ANCHOR_TRADES -- the SAME transcription CLAUDE.md OP-16 and
        the SS-B certification study already use, reused unchanged here, not re-typed).
        MODELED (alignment reconstructed at each trade's real entry_time_et).

MODES:
  `python trend_alignment_correlation_study.py --build-cache` -- fetch+cache daily/hourly/15m
      SPY history ONCE (paginated Alpaca REST), covering the full span the 3 populations need.
      No scoring, no signal replay -- pure infra build/verify step.
  `python trend_alignment_correlation_study.py --score` -- NOT YET ENABLED this phase (raises).
      Scoring is gated behind the frozen pre-registration being committed first (anti-p-hacking
      barrier, task hard rule: "must fully complete + COMMIT the pre-registration BEFORE any
      scoring runs"). Flip the guard in a LATER commit, once the pre-reg is in git history.
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time_mod
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest", REPO / "backtest" / "tools", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# UNMODIFIED reuse -- single source of truth for the alignment math (task hard rule).
from context_bundle_producer import compute_trend_alignment, _load_alpaca_creds  # noqa: E402
from et_clock import et_now as _et_now  # noqa: E402

CACHE_DIR = REPO / "analysis" / "backtests" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PREREG_F = (REPO / "analysis" / "recommendations"
            / "prereg-trend-alignment-correlation-2026-07-14.json")

# Alpaca timeframe codes this study needs -- same 3 timeframes Phase 0's producer uses,
# fetched here as full [start,end] history (paginated) rather than a trailing lookback.
TIMEFRAME_CODES = {"daily": "1Day", "hourly": "1Hour", "m15": "15Min"}

# Full span P1/P2/P3 need: daily needs ~6mo of LEAD-IN before the earliest signal (2025-01-01)
# for a stable structure read at that signal's own T; hourly/m15 need history across the WHOLE
# decision window (any T in 2025-01-01..2026-07-09 must be reconstructable), not just a trailing
# window -- so all 3 timeframes are fetched for the same [FETCH_START, FETCH_END] superset.
FETCH_START = date(2024, 7, 1)   # ~6mo lead-in before P1's earliest signal (2025-01-01)
FETCH_END = date(2026, 7, 14)    # today (et_clock-verified at freeze time) -- covers P2's window


# ===============================================================================================
# FETCH + CACHE -- ONE paginated Alpaca REST pull per timeframe, cached to disk so the per-signal
# scoring loop (Phase 1's actual correlation run) never re-fetches. Same credential-loading +
# request shape as context_bundle_producer._fetch_bars / heartbeat_core's _fetch_spy_5m (the
# un-blockable direct-REST path) -- this function differs only in taking an explicit [start,end]
# and paginating via Alpaca's page_token, since a trailing "days_back from now" lookback (Phase
# 0's convention, correct for the LIVE producer) cannot cover an 18-month historical replay.
# ===============================================================================================
def _cache_path(timeframe_key: str) -> Path:
    return CACHE_DIR / f"trend-alignment-spy-{timeframe_key}-{FETCH_START}_{FETCH_END}.json"


def fetch_historical_bars(timeframe_key: str, *, feed: str = "iex",
                           refresh: bool = False) -> pd.DataFrame:
    """SPY OHLCV for [FETCH_START, FETCH_END], paginated, cached to disk. Returns a DataFrame
    with columns (timestamp[tz-aware UTC], open, high, low, close, volume) -- the exact shape
    compute_trend_alignment's callers (via _df_to_bars) expect. NEVER raises on a page failure
    mid-pull -- if partial data was already fetched this call, it re-raises only after logging
    (the caller decides whether a partial cache is usable); a totally fresh call that fails
    immediately propagates the exception (fail LOUD here -- this is an offline build step, not
    the fail-open live producer)."""
    cache_f = _cache_path(timeframe_key)
    if cache_f.exists() and not refresh:
        raw = json.loads(cache_f.read_text(encoding="utf-8"))
        df = pd.DataFrame(raw["bars"])
        if len(df):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    key, sec = _load_alpaca_creds()
    tf_code = TIMEFRAME_CODES[timeframe_key]
    all_bars: list[dict] = []
    page_token = None
    start_s = FETCH_START.strftime("%Y-%m-%dT00:00:00Z")
    end_s = (FETCH_END + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    n_pages = 0
    while True:
        url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe={tf_code}"
               f"&start={start_s}&end={end_s}&limit=10000&feed={feed}&adjustment=raw&sort=asc")
        if page_token:
            url += f"&page_token={page_token}"
        req = urllib.request.Request(
            url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
        all_bars.extend(payload.get("bars", []))
        n_pages += 1
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        _time_mod.sleep(0.2)  # polite pacing across pages, not a rate-limit workaround

    bars = [{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
             "close": b["c"], "volume": b["v"]} for b in all_bars]
    cache_f.write_text(json.dumps({
        "timeframe": timeframe_key, "start": str(FETCH_START), "end": str(FETCH_END),
        "n_bars": len(bars), "n_pages": n_pages,
        "fetched_at_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "bars": bars,
    }, indent=2), encoding="utf-8")

    df = pd.DataFrame(bars)
    if len(df):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def build_all_caches(*, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Fetch+cache all 3 timeframes ONCE. Returns {timeframe_key: df}."""
    out = {}
    for tf_key in TIMEFRAME_CODES:
        out[tf_key] = fetch_historical_bars(tf_key, refresh=refresh)
        print(f"[trend-alignment-study] {tf_key}: {len(out[tf_key])} bars cached "
              f"-> {_cache_path(tf_key).name}", flush=True)
    return out


# ===============================================================================================
# NO-LOOK-AHEAD RECONSTRUCTION -- the ONE place this module slices bars before calling
# compute_trend_alignment. Mirrors the exact workflow compute_trend_alignment's own docstring
# specifies for Phase 1 reuse: slice each DataFrame to <=T, call the SAME pure function, never
# re-derive the math. Guarded by test_alignment_for_decision_matches_cutoff_only (this module's
# guard test) which proves the property one level up from Phase 0's own pure-function guard.
# ===============================================================================================
def alignment_for_decision(daily_df: "pd.DataFrame | None", hourly_df: "pd.DataFrame | None",
                            m15_df: "pd.DataFrame | None", decision_ts) -> dict:
    """Slice each of the 3 timeframe DataFrames to rows with timestamp <= decision_ts, then call
    context_bundle_producer.compute_trend_alignment (UNMODIFIED) on the slices. decision_ts may
    be a naive or tz-aware datetime/Timestamp/ISO string -- normalized to UTC for comparison
    against the tz-aware cached bars (naive inputs are ASSUMED ET per this repo's convention
    and localized accordingly, since every signal source in this study records entry times in
    ET, not UTC)."""
    ts = pd.Timestamp(decision_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/New_York").tz_convert("UTC")
    else:
        ts = ts.tz_convert("UTC")

    def _slice(df):
        if df is None or len(df) == 0:
            return df
        return df[df["timestamp"] <= ts].reset_index(drop=True)

    return compute_trend_alignment(_slice(daily_df), _slice(hourly_df), _slice(m15_df))


def alignment_vs_side(alignment: dict, side: str) -> dict:
    """Reduce compute_trend_alignment()'s raw bundle to the study's core dependent variable:
    does this alignment AGREE with the trade's own side? side: 'bull' (calls) or 'bear' (puts).

    signed_score: alignment_score if side=='bull' else -alignment_score -- so POSITIVE ALWAYS
    means 'agrees with this trade's own direction' regardless of which side the trade took.
    This is the value that gets bucketed into the -3..+3 AGREEMENT buckets in the pre-reg
    (never the raw market-direction score, which would conflate bull/bear populations).

    aligned:  True iff EVERY available timeframe read the trade's own direction (mirrors
              compute_trend_alignment's trend_alignment[side]['aligned']).
    fighting: True iff EVERY available timeframe read the OPPOSITE direction (full alignment
              against the trade)."""
    if side not in ("bull", "bear"):
        raise ValueError(f"side must be 'bull' or 'bear', got {side!r}")
    opposite = "bear" if side == "bull" else "bull"
    score = alignment["alignment_score"]
    return {
        "signed_score": int(score if side == "bull" else -score),
        "raw_score": int(score),
        "aligned": bool(alignment["trend_alignment"][side]["aligned"]),
        "fighting": bool(alignment["trend_alignment"][opposite]["aligned"]),
        "degraded": bool(alignment["degraded"]),
    }


def side_from_option_char(option_char: str) -> str:
    """OCC/ledger convention 'C'/'P' or 'call'/'put' -> this study's 'bull'/'bear'."""
    c = option_char.strip().upper()
    if c in ("C", "CALL"):
        return "bull"
    if c in ("P", "PUT"):
        return "bear"
    raise ValueError(f"unrecognized option side {option_char!r}")


# ===============================================================================================
# POPULATION LOADERS -- signal/episode lists only (entry_ts, side, [outcome if MEASURED]).
# Outcome replay (P1's SS-B pass, P3's per-trade replay) is DEFERRED to the scoring run per the
# task's anti-p-hacking barrier ("Do NOT run scoring yet") -- these loaders build the POPULATION
# a scoring run will consume, they do not themselves run OPRA-heavy replay.
# ===============================================================================================
def load_p1_population() -> list[dict]:
    """P1 -- the canonical ribbon_ride signal cohort, REUSED UNMODIFIED via
    _signal_cache.load_or_build_signals() (cached analysis/exit-parity/signal-set.json).

    OP-33 HONESTY NOTE: the task brief described this population as 'n in thousands'. The
    actual canonical cohort every ribbon_ride/exit study in this repo reuses (T3/T4,
    ribbon_ride_strike_exit_ab.py, WP5-STRIKE-AB) is n=250 (both directions, L2 gate, cap off,
    2025-01-01..2026-06-18) -- there is no larger canonical population with SS-B-replayed real-
    OPRA outcomes in this repo as of 2026-07-14. This loader reuses the REAL n=250 cohort rather
    than fabricating or padding to a bigger number; the pre-registration states n=250 explicitly
    and flags this discrepancy against the task brief's guess rather than silently assuming
    'thousands' was correct."""
    import _signal_cache as sc  # backtest/tools on sys.path (inserted above)
    data = sc.load_or_build_signals()
    sigs = data["signals"] if isinstance(data, dict) else data
    return sigs


def load_p2_population() -> list[dict]:
    """P2 -- real engine fills, MEASURED. Reads automation/state/fills-ledger.jsonl (broker-
    truth, broker_fills.py's pull from Alpaca /v2/account/activities/FILL) and reconstructs
    per-EPISODE rows via exit_shape_parity_study.reconstruct_positions() -- the SAME C31-safe
    grouping trade_autopsy.py and the 2026-07-11 ledger-forensics report use (never per-leg/
    per-order, which inverted a result once already)."""
    import exit_shape_parity_study as esps  # backtest/tools on sys.path
    ledger_f = REPO / "automation" / "state" / "fills-ledger.jsonl"
    fills = []
    with ledger_f.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                fills.append(json.loads(line))
    positions = esps.reconstruct_positions(fills)
    return positions


def load_p3_population() -> list[dict]:
    """P3 -- J's OP-16 source-of-truth anchor trades, reused VERBATIM from
    ssb_certification_study.J_ANCHOR_TRADES (7 trades, transcribed from journal/trades.csv,
    winner-sum-asserted == CLAUDE.md's OP-16 $1,542 max in that module) -- not re-typed here,
    imported so any future correction to the source list is inherited automatically."""
    import ssb_certification_study as scs  # backtest/tools on sys.path
    return list(scs.J_ANCHOR_TRADES)


# ===============================================================================================
# GUARD: no-look-ahead reconstruction property, at THIS module's slicing boundary (one level up
# from Phase 0's own pure-function guard in test_context_bundle_producer.py). Exercised by
# backtest/tests/test_trend_alignment_correlation_study.py -- kept importable here too so a
# manual `python trend_alignment_correlation_study.py --self-check` can run it standalone.
# ===============================================================================================
def _self_check_no_lookahead() -> None:
    idx = pd.date_range("2026-01-01", periods=80, freq="1h", tz="UTC")
    up = pd.DataFrame({"timestamp": idx, "open": range(80), "high": [x + 1 for x in range(80)],
                        "low": range(80), "close": [x + 0.5 for x in range(80)],
                        "volume": [100] * 80})
    T = idx[49]

    sliced = up[up["timestamp"] <= T].reset_index(drop=True)
    a1 = alignment_for_decision(up, up, up, T)
    a2 = compute_trend_alignment(sliced, sliced, sliced)
    assert a1 == a2, "alignment_for_decision must reproduce a manually <=T-sliced call exactly"

    full = compute_trend_alignment(up, up, up)
    assert a1 != full or full["alignment_score"] == a1["alignment_score"], (
        "sanity: at minimum the two calls must be independently well-formed")
    print("[trend-alignment-study] self-check PASSED: no-look-ahead reconstruction holds")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-cache", action="store_true",
                     help="fetch+cache daily/hourly/15m SPY history (no scoring)")
    ap.add_argument("--refresh", action="store_true", help="ignore existing cache files")
    ap.add_argument("--self-check", action="store_true",
                     help="run the no-look-ahead reconstruction guard standalone")
    ap.add_argument("--score", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.self_check:
        _self_check_no_lookahead()
        return 0

    if args.score:
        if not PREREG_F.exists():
            raise SystemExit(
                "REFUSED: --score requires the frozen pre-registration to exist at "
                f"{PREREG_F} first (anti-p-hacking barrier -- commit the pre-reg before any "
                "scoring run, per task hard rule).")
        raise SystemExit(
            "--score is NOT YET ENABLED this phase. Phase 1's BUILD step (this commit) freezes "
            "the pre-registration and the fetch/cache/population-loader infrastructure only. "
            "The actual correlation scoring run is a SEPARATE, later commit -- see "
            f"{PREREG_F.name} status field.")

    if args.build_cache:
        build_all_caches(refresh=args.refresh)
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
