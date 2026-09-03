#!/usr/bin/env python
"""pullback_hold_shadow.py -- nightly forward scanner for PULLBACK-HOLD-BULL-TRIGGER Lane B.

Pre-registration (frozen BEFORE this script ever wrote a ledger row):
`analysis/recommendations/prereg-pullback-hold-bull-trigger-2026-09-03.md`. Detector:
`backtest/lib/pullback_hold_detector.py` (standalone, SHADOW-ONLY, zero engine wiring).

WHAT THIS SCRIPT DOES
----------------------
For every trading session found in `automation/state/core-decisions.jsonl`, builds a synthetic
5-min SPY OHLC bar series from the live engine's own OWN per-tick spot-price log (account
`safe` only -- `safe`/`bold` tick within ~1 second of each other on an identical `spy` price,
verified 2026-09-03; using both would double-bucket the same market moment), reusing the SAME
`levels_active` and `htf_15m` fields the live engine already computed and logged per tick (no
separate level-feed or ribbon recompute -- Lane A is scored against exactly what the engine saw
that day). Scans for PULLBACK-HOLD fires via `pullback_hold_detector.scan_session`, scores each
fire's forward outcome (FAVOURABLE / ADVERSE / FLAT / UNSCORED_INSUFFICIENT_BARS) against the
frozen medians in the pre-reg, and rewrites the FULL ledger + summary from scratch every run
(same idempotency pattern as `day_throttle_shadow.py`: this is a deterministic function of
`core-decisions.jsonl`, so re-running for the same underlying data reproduces byte-identical
output rather than needing manual append-dedup).

DATA CAVEAT (disclosed, matches the bear-f8 sign-costing doc's own disclosure): the synthetic
bars are built from 1-per-minute tick snapshots, not true continuous OHLC -- a bucket's
high/low is the max/min of the ~5 per-minute ticks it contains, not the true intrabar extreme.
This under-states real intrabar range slightly; it is the best available data without a live
SPY-bar fetch or OPRA (both out of scope for this rail-4 shadow tool).

ZERO ENGINE WIRING: reads `core-decisions.jsonl` (read-only) and writes only to
`analysis/recommendations/`. Never imports `heartbeat_core`, `filters`, `orchestrator`'s live
dispatch, `strategies`, `risk_gate`, `exit_manager`, `fleet_executor`, `fleet_live`, or
`params*.json`. Places no orders.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.pullback_hold_detector import (  # noqa: E402
    PULLBACK_LOOKBACK_BARS,
    PULLBACK_MIN_HOLD_BARS,
    PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
    scan_session,
)

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "pullback-hold-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "pullback-hold-shadow-summary.json"
PREREG = OUT_DIR / "prereg-pullback-hold-bull-trigger-2026-09-03.md"

TICK_ACCOUNT = "safe"          # safe/bold tick within ~1s on an identical spy price
RTH_START = dt.time(9, 30)
RTH_END = dt.time(15, 55)

# Frozen forward-outcome medians -- see the pre-reg's "Forward outcome proxy" section for the
# exact reproduction recipe (n=44 matched core-arm engine BULL trips, full history).
MEDIAN_BULL_HOLD_MIN = 23.9
MEDIAN_BULL_MFE = 0.60
MEDIAN_BULL_MAE = 0.58

# Frozen engine bull baseline (same walk, ENTERED population) -- the bar the forward CI-lower
# must clear per the pre-reg's decision rule. NOT recomputed here; pinned so this script can't
# silently drift the bar it is measuring against.
BULL_BASELINE_FAVOURABLE_RATE = 0.4545
BULL_BASELINE_N = 44

FORWARD_SESSIONS_REQUIRED = 30
FORWARD_FIRES_REQUIRED = 25

# Forward window opens the pre-reg's own filing date -- any session dated before this is
# in-sample reference ONLY (same no-peeking split as day_throttle_shadow.py's
# FORWARD_FIRST_DATE) and can never clear the verdict. Frozen at pre-reg time; do not edit.
FORWARD_FIRST_DATE = "2026-09-03"

BOOTSTRAP_SEED = 1337
BOOTSTRAP_N = 2000


def _load_ticks() -> list[dict]:
    if not CORE_DECISIONS.exists():
        return []
    ticks = []
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("account") != TICK_ACCOUNT:
                continue
            ts_et = d.get("ts_et")
            spy = d.get("spy")
            if not ts_et or spy is None:
                continue
            ticks.append(d)
    return ticks


def _bucket_key(ts: dt.datetime) -> dt.datetime:
    """Floor a timestamp to its 5-min bucket start."""
    minute = (ts.minute // 5) * 5
    return ts.replace(minute=minute, second=0, microsecond=0)


def build_session_bars(ticks_for_day: list[dict]) -> tuple[pd.DataFrame, dict, list]:
    """Build synthetic 5-min OHLC bars + per-bar levels_active + per-bar htf_15m from one
    session's account=='safe' ticks. Returns (bars_df, levels_by_idx, htf_by_idx)."""
    buckets: dict[dt.datetime, list[dict]] = collections.defaultdict(list)
    for t in ticks_for_day:
        ts = dt.datetime.fromisoformat(t["ts_et"])
        if ts.time() < RTH_START or ts.time() > RTH_END:
            continue
        buckets[_bucket_key(ts)].append(t)

    bucket_starts = sorted(buckets.keys())
    rows = []
    levels_by_idx: dict[int, list] = {}
    htf_by_idx: list = []
    for idx, bstart in enumerate(bucket_starts):
        bucket_ticks = sorted(buckets[bstart], key=lambda t: t["ts_et"])
        prices = [float(t["spy"]) for t in bucket_ticks]
        rows.append({
            "timestamp_et": bstart,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
        })
        last_tick = bucket_ticks[-1]
        levels_by_idx[idx] = list(last_tick.get("levels_active") or [])
        htf_by_idx.append(last_tick.get("htf_15m"))

    bars = pd.DataFrame(rows)
    return bars, levels_by_idx, htf_by_idx


def _classify_outcome(entry_close: float, trigger_idx: int, bars: pd.DataFrame) -> str:
    """Walk forward on the SAME session's bars from `trigger_idx` for up to
    MEDIAN_BULL_HOLD_MIN minutes, classify FAVOURABLE/ADVERSE/FLAT/UNSCORED_INSUFFICIENT_BARS."""
    trigger_ts = bars.iloc[trigger_idx]["timestamp_et"]
    window_end = trigger_ts + dt.timedelta(minutes=MEDIAN_BULL_HOLD_MIN)
    fav_price = entry_close + MEDIAN_BULL_MFE
    adv_price = entry_close - MEDIAN_BULL_MAE

    forward = bars.iloc[trigger_idx:]
    forward = forward[forward["timestamp_et"] <= window_end]
    if forward.empty:
        return "UNSCORED_INSUFFICIENT_BARS"

    last_ts_in_session = bars.iloc[-1]["timestamp_et"]
    reached_full_window = last_ts_in_session >= window_end

    for _, bar in forward.iterrows():
        hit_fav = bar["high"] >= fav_price
        hit_adv = bar["low"] <= adv_price
        if hit_fav and hit_adv:
            return "ADVERSE"  # tie-break, conservative, pre-registered
        if hit_fav:
            return "FAVOURABLE"
        if hit_adv:
            return "ADVERSE"

    if not reached_full_window:
        return "UNSCORED_INSUFFICIENT_BARS"  # session ended before the hold window closed
    return "FLAT"


def scan_all_sessions() -> tuple[list[dict], list[str]]:
    """Returns (ledger_rows, scanned_dates)."""
    ticks = _load_ticks()
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    for t in ticks:
        date = t["ts_et"][:10]
        by_date[date].append(t)

    ledger_rows: list[dict] = []
    scanned_dates: list[str] = []

    for date in sorted(by_date.keys()):
        bars, levels_by_idx, htf_by_idx = build_session_bars(by_date[date])
        if bars.empty or len(bars) < PULLBACK_MIN_HOLD_BARS + 1:
            continue
        scanned_dates.append(date)

        fires = scan_session(
            bars,
            levels_by_idx,
            htf_stacks=htf_by_idx,
            zone_band_dollars=PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
            min_hold_bars=PULLBACK_MIN_HOLD_BARS,
            lookback_bars=PULLBACK_LOOKBACK_BARS,
            rth_only=True,
        )
        if not fires:
            continue

        # Map each fire's ts back to its bar index for the forward walk.
        ts_to_idx = {str(row["timestamp_et"]): i for i, row in bars.iterrows()}
        for fire in fires:
            idx = ts_to_idx.get(fire.ts)
            if idx is None:
                continue
            outcome = _classify_outcome(fire.trigger_close, idx, bars)
            ledger_rows.append({
                "date": date,
                **fire.as_dict(),
                "outcome": outcome,
                "median_hold_min": MEDIAN_BULL_HOLD_MIN,
                "median_mfe": MEDIAN_BULL_MFE,
                "median_mae": MEDIAN_BULL_MAE,
                "in_sample": date < FORWARD_FIRST_DATE,
            })

    return ledger_rows, scanned_dates


def _bootstrap_ci_lower(rows: list[dict]) -> float | None:
    """Session-clustered bootstrap CI-lower (2.5th percentile) on the FAVOURABLE rate.
    Resamples TRADING DAYS with replacement (fires within a day are correlated market moments,
    not independent draws) -- same convention as bear-f8-vix-floor-sign-costing-2026-09-03.md.
    `rows` must already be pre-filtered to the population being scored (forward-only)."""
    scored = [r for r in rows if r["outcome"] in ("FAVOURABLE", "ADVERSE", "FLAT")]
    if not scored:
        return None
    by_day: dict[str, list[dict]] = collections.defaultdict(list)
    for r in scored:
        by_day[r["date"]].append(r)
    days = sorted(by_day.keys())
    if not days:
        return None

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    rates = []
    for _ in range(BOOTSTRAP_N):
        sample_days = rng.choice(days, size=len(days), replace=True)
        pooled = []
        for d in sample_days:
            pooled.extend(by_day[d])
        if not pooled:
            continue
        fav = sum(1 for r in pooled if r["outcome"] == "FAVOURABLE")
        rates.append(fav / len(pooled))
    if not rates:
        return None
    return float(np.percentile(rates, 2.5))


def _score_block(rows: list[dict], dates: list[str]) -> dict:
    scored = [r for r in rows if r["outcome"] in ("FAVOURABLE", "ADVERSE", "FLAT")]
    fav = sum(1 for r in scored if r["outcome"] == "FAVOURABLE")
    adv = sum(1 for r in scored if r["outcome"] == "ADVERSE")
    flat = sum(1 for r in scored if r["outcome"] == "FLAT")
    unscored = sum(1 for r in rows if r["outcome"] == "UNSCORED_INSUFFICIENT_BARS")
    n_scored = len(scored)
    ci_lower = _bootstrap_ci_lower(rows)
    return {
        "sessions": len(dates),
        "n_fires_total": len(rows),
        "n_scored": n_scored,
        "favourable": fav,
        "adverse": adv,
        "flat": flat,
        "unscored_insufficient_bars": unscored,
        "favourable_rate": (fav / n_scored) if n_scored else None,
        "ci_lower_2p5_bootstrap": ci_lower,
    }


def write_summary(rows: list[dict], scanned_dates: list[str]) -> dict:
    from et_clock import et_now  # noqa: E402 -- deferred, matches day_throttle_shadow.py's idiom

    forward_dates = [d for d in scanned_dates if d >= FORWARD_FIRST_DATE]
    forward_rows = [r for r in rows if not r["in_sample"]]
    in_sample_dates = [d for d in scanned_dates if d < FORWARD_FIRST_DATE]
    in_sample_rows = [r for r in rows if r["in_sample"]]

    forward = _score_block(forward_rows, forward_dates)
    in_sample = _score_block(in_sample_rows, in_sample_dates)

    sessions_elapsed = len(forward_dates)
    fires_elapsed = forward["n_scored"]
    verdict_ready = (sessions_elapsed >= FORWARD_SESSIONS_REQUIRED
                      and fires_elapsed >= FORWARD_FIRES_REQUIRED)

    verdict = None
    ci_lower = forward["ci_lower_2p5_bootstrap"]
    if verdict_ready and ci_lower is not None:
        verdict = "CLEARS_BASELINE" if ci_lower > BULL_BASELINE_FAVOURABLE_RATE else "NO_CLEAR"

    summary = {
        "_meta": {
            "generated_at_et": et_now().isoformat(),
            "builder": "setup/scripts/pullback_hold_shadow.py",
            "detector": "backtest/lib/pullback_hold_detector.py",
            "prereg": str(PREREG.relative_to(REPO)).replace("\\", "/"),
            "shadow_only": "MEASUREMENT ONLY -- zero engine wiring, no live/backtest gate reads "
                            "this ledger.",
            "constants": {
                "zone_band_dollars_default": PULLBACK_ZONE_BAND_DOLLARS_DEFAULT,
                "min_hold_bars_k": PULLBACK_MIN_HOLD_BARS,
                "lookback_bars": PULLBACK_LOOKBACK_BARS,
                "median_bull_hold_min": MEDIAN_BULL_HOLD_MIN,
                "median_bull_mfe": MEDIAN_BULL_MFE,
                "median_bull_mae": MEDIAN_BULL_MAE,
            },
            "bull_baseline_favourable_rate": BULL_BASELINE_FAVOURABLE_RATE,
            "bull_baseline_n": BULL_BASELINE_N,
        },
        "forward_window": {
            "first_date": FORWARD_FIRST_DATE,
            "sessions_scanned": sessions_elapsed,
            "sessions_required": FORWARD_SESSIONS_REQUIRED,
            "fires_scored": fires_elapsed,
            "fires_required": FORWARD_FIRES_REQUIRED,
            "verdict_ready": verdict_ready,
            "scanned_dates": forward_dates,
        },
        "forward": {**forward, "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_n": BOOTSTRAP_N},
        "in_sample_reference": in_sample,
        "verdict": verdict,
        "_reading_note": "`forward` (dated >= "
                          f"{FORWARD_FIRST_DATE}) is the ONLY block that can adjudicate the "
                          "pre-reg's decision rule -- verdict is null until BOTH forward_window "
                          "floors clear (30 sessions AND 25 scored fires); a null verdict means "
                          "MEASURING, not NO_EDGE. `in_sample_reference` covers everything "
                          "core-decisions.jsonl logged BEFORE the pre-reg's freeze date and is "
                          "printed for drift-checking only -- it can NEVER clear the verdict "
                          "(no-peeking, same split day_throttle_shadow.py uses).",
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(args=argv if argv is not None else sys.argv[1:])
    # no flags defined yet; placeholder for a future --date override, and lets callers (tests)
    # invoke main() as a library function without inheriting the host process's own argv.

    if not PREREG.exists():
        print(f"pullback_hold_shadow: pre-registration missing at {PREREG} -- refusing to "
              "produce a ledger with no frozen spec behind it", file=sys.stderr)
        return 1

    rows, scanned_dates = scan_all_sessions()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    tmp.replace(LEDGER)

    summary = write_summary(rows, scanned_dates)
    tmp_s = SUMMARY.with_suffix(".json.tmp")
    tmp_s.write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    tmp_s.replace(SUMMARY)

    fw = summary["forward_window"]
    fwd = summary["forward"]
    ins = summary["in_sample_reference"]
    print(f"pullback_hold_shadow: {len(scanned_dates)} sessions in core-decisions.jsonl "
          f"({ins['sessions']} in-sample pre-{FORWARD_FIRST_DATE}, {fw['sessions_scanned']} "
          f"forward) -- {len(rows)} fires total")
    print(f"  in-sample reference (NOT verdict-eligible): {ins['n_scored']} scored, "
          f"FAV={ins['favourable']} ADV={ins['adverse']} FLAT={ins['flat']} "
          f"rate={ins['favourable_rate']}")
    print(f"  forward window {fw['fires_scored']}/{fw['fires_required']} fires, "
          f"{fw['sessions_scanned']}/{fw['sessions_required']} sessions"
          f"{' -- VERDICT READY' if fw['verdict_ready'] else ' (measuring, no verdict yet)'}")
    if fwd["ci_lower_2p5_bootstrap"] is not None:
        print(f"  forward favourable_rate={fwd['favourable_rate']:.3f} "
              f"ci_lower={fwd['ci_lower_2p5_bootstrap']:.3f} "
              f"vs baseline={BULL_BASELINE_FAVOURABLE_RATE:.4f} verdict={summary['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
