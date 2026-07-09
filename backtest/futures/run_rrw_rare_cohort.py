"""run_rrw_rare_cohort.py -- JOB 2: re-test the RRW "rare/high-quality" cohort (vol_mult_min
>= 2.5) through TODAY's canonical harness (battery.py + swing_sim.py).

WHY THIS EXISTS: the 2026-07-02 PHASE1-swing-battery killed the MES swing seed pile
(analysis/PHASE1-swing-battery/RESULTS.md: DOES_NOT_TRANSFER, 0/12 BH-FDR survivors) but
explicitly did NOT disprove one cohort -- quoting RESULTS.md's "What this does NOT kill"
section verbatim: "(a) the RRW vol>=2.5 rare cohort -- direction-consistent both periods,
opposite-direction loses, but unpowered at 45 events/18mo; it would need years of data or a
relaxed-but-validated gate to power a test -- parked, not disproven ... Any follow-up must be
a NEW pre-registered battery -- no knob-turning on this one." This script is that follow-up:
a NEW, independent pass at the SAME cohort definition, through the CURRENT canonical harness
(backtest/futures/battery.py + backtest/futures/swing_sim.py, imported verbatim -- neither is
modified), not a rerun of the old ad-hoc analysis/PHASE1-swing-battery/swing_battery.py script.

COHORT DEFINITION (read from DESIGN.md sec 2 "Seed A -- RRW-short" + RESULTS.md's funnel
table -- the EXACT vol>=2.5 half of Seed A's 8-combo grid, reproduced here verbatim, not
reinterpreted):
  Detector: backtest/lib/watchers/ribbon_rejection_wick_detector.detect() (bear direction
    only -- "the short cohort was the direction-real side", DESIGN.md sec 2 Seed A).
  Grid (4 of the original 8 combos -- the vol_mult_min=2.5 half):
    wick_frac_min in {0.35, 0.5} x break_lookback_bars in {6, 12}, vol_mult_min FIXED at 2.5,
    stack_filter FIXED at "any" (require_stack_not_flipped=False -- DESIGN.md: "Config family
    = the 8 BH-FDR survivors ... stack=any", not gridded).
  Fixed (disclosed, MES-point-scaled from the SPY battery, DESIGN.md sec 2):
    close_margin_dollars=0.10 pt, min_bar_range_dollars=1.00 pt.
  above_lookback_bars / vol_median_min_bars: RRWParams class defaults (36 / 3) -- the
    original superset scan never overrode these either (verified against
    analysis/PHASE1-swing-battery/swing_battery.py::scan_rrw, which is READ for the exact
    param values but its ExitEngine/battery machinery is NOT imported or reused here -- only
    battery.py/swing_sim.py are the harness, per the task's explicit constraint).
  Eligible signal-bar window: RTH 5-minute bars, 09:35-15:30 ET inclusive, index >= 48 bars
    into the frame (Saty ribbon warmup) -- identical to the original scan_rrw()'s window,
    reproduced here for cohort fidelity, not imported (that script's machinery is untouched).

REUSE DECISION (why signal detection runs on 5-MINUTE bars while battery.py's ATR + fill
mechanics run on DAILY bars -- documented per the task's "your call, document it" invitation):
  vol_mult_min (break-bar volume vs today's PRIOR RTH bars) is the entire reason this cohort
  is "rare" and the entire thing under test -- it has NO meaning at daily granularity (there
  is exactly one bar per day, so "prior bars today" is always empty; see
  backtest/futures/seeds/rrw_seed.py's own disclosure, which is why the ALREADY-EXECUTED
  2026-07-09 daily-bar Seed A pass at analysis/recommendations/futures-swing-rrw_short.json
  fixes vol_mult_min=0.0 for every combo and could never express this cohort at all).
  battery.py's score_seed()/run_cell(), by construction, compute `wilder_atr(bars)` and walk
  simulate_swing() on the SAME `bars` frame passed in -- there is no way to feed it a
  different timeframe for signals vs mechanics without editing it (forbidden). The fix used
  here: detect signals on RTH 5-MINUTE bars (the only place vol_mult_min is meaningful), then
  translate each signal to "the daily bar for that signal's calendar date" and pass DAILY
  bars into battery.py as `bars` -- so ATR14 and the entry/stop/target walk are computed
  exactly the way the ALREADY-EXECUTED 2026-07-09 daily Seed A pass does (same `bars` shape,
  same DAILY_HORIZONS, same battery.py defaults: stop_mult=1.5xATR14, target_mult=3.0xATR14),
  while the SIGNAL ITSELF stays faithful to the true vol>=2.5 definition. Multiple 5m signals
  on the same calendar day collapse to the FIRST one per (combo, day) -- otherwise they would
  all map to the identical daily_idx and manufacture duplicate trades.
  Consequence (disclosed, not hidden): entry/exit prices and trade counts will differ from
  the original 2026-07-02 5m-signal/ETH-5m-fill-walk battery's numbers for this same cohort
  (RESULTS.md's train n=15-16 / test n=3-4 per shape) -- this is a genuinely different (and
  coarser) execution mechanic, not a byte-for-byte replication. That is the intended scope:
  "re-run JUST that cohort through TODAY's harness."

Direction: SHORT only (the historically "direction-real" side). battery.py's score_seed()
  still computes a "long" pass over the same signal grid regardless (it always evaluates both
  directions) -- those cells will show n=0 by construction (no long signals were generated)
  and are excluded from the BH-FDR family; reported, not hidden.

VERDICT OVERLAY (battery.py itself only emits a per-CELL `clears` boolean and an aggregate
  seed-level PASS/KILL; the INCONCLUSIVE_SMALL_N rung is this script's addition, computed
  from battery.py's own output, never by editing battery.py):
    PASS               : >=1 cell clears (battery.py's own gate: oos_n_sufficient AND
                          oos_mean>0 AND bh_fdr_survivor(alpha=0.05) AND beats_buy_and_hold).
    INCONCLUSIVE_SMALL_N: zero cells ever reached MIN_OOS_N=5 (n_bh_fdr_eligible==0) -- the
                          cohort fired too rarely to even ENTER the FDR family; the task's
                          explicit instruction is to say this plainly rather than KILL.
    KILL               : >=1 cell reached the FDR family but none cleared all gates.

Run: backtest/.venv/Scripts/python.exe backtest/futures/run_rrw_rare_cohort.py
Writes: analysis/recommendations/futures-swing-rrw_rare.json
        + a provenance row to analysis/backtests/data-versions.jsonl
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "futures"))

from futures.data import load_continuous_csv, resample_5m, resample_daily, fetch_vix_daily, fetch_es_daily_gap  # noqa: E402
from futures.instruments import MES  # noqa: E402
from futures import battery  # noqa: E402  (score_seed/run_cell -- the canonical harness, NOT modified)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.watchers.ribbon_rejection_wick_detector import detect, RRWParams  # noqa: E402

MES_CSV = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
REC_DIR = REPO / "analysis" / "recommendations"
DATA_VERSIONS = REPO / "analysis" / "backtests" / "data-versions.jsonl"
OUT_PATH = REC_DIR / "futures-swing-rrw_rare.json"

# ── frozen cohort definition (DESIGN.md sec 2 Seed A, the vol>=2.5 half) ──────────
RARE_VOL_MULT_MIN = 2.5
WICK_FRAC_MIN = (0.35, 0.5)
BREAK_LOOKBACK_BARS = (6, 12)
CLOSE_MARGIN_PTS = 0.10          # MES points (DESIGN.md-disclosed scaling from SPY cents)
MIN_BAR_RANGE_PTS = 1.00         # MES points
DIRECTION = "bear"               # the historically direction-real side; -> "short" in battery.py

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
SIG_MIN = dt.time(9, 35)         # matches the original scan_rrw()'s eligible-signal window
SIG_MAX = dt.time(15, 30)
WARMUP_BARS = 48                 # Saty ribbon warmup (fast=13/pivot=20/slow=48)

OOS_CUT = dt.date(2026, 1, 1)                        # task-specified split, verbatim
DAILY_HORIZONS = [(1, "1d"), (3, "3d"), (5, "5d")]    # matches the already-executed 2026-07-09
                                                       # daily-bar Seed A pass (run_swing_battery.py)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_combos() -> list[dict]:
    combos = []
    for wf in WICK_FRAC_MIN:
        for lb in BREAK_LOOKBACK_BARS:
            combos.append({
                "combo_id": f"A_rrw_w{wf}_lb{lb}_v{RARE_VOL_MULT_MIN}",
                "wick_frac_min": wf, "break_lookback_bars": lb,
                "vol_mult_min": RARE_VOL_MULT_MIN, "stack_filter": "any",
            })
    assert len(combos) == 4
    return combos


def _params_for(combo: dict) -> RRWParams:
    return RRWParams(
        wick_frac_min=combo["wick_frac_min"], break_lookback_bars=combo["break_lookback_bars"],
        vol_mult_min=combo["vol_mult_min"], require_stack_not_flipped=False,
        close_margin_dollars=CLOSE_MARGIN_PTS, min_bar_range_dollars=MIN_BAR_RANGE_PTS,
        # above_lookback_bars / vol_median_min_bars: class defaults (36 / 3) -- never
        # overridden by the original superset scan either.
    )


def load_frames() -> dict:
    """RTH 5-minute bars (the ONLY granularity where vol_mult_min is meaningful -- signal
    detection) + daily RTH bars (battery.py's ATR + fill-mechanics frame, matching the
    already-executed 2026-07-09 daily Seed A pass's own convention)."""
    t0 = time.time()
    raw = load_continuous_csv(str(MES_CSV))
    span = (str(raw["timestamp_et"].min()), str(raw["timestamp_et"].max()))
    log(f"loaded {len(raw)} 1m bars, span {span}")

    rth5 = resample_5m(raw)
    rth5["date"] = rth5["timestamp_et"].dt.date
    daily = resample_daily(raw)
    log(f"resampled: rth5m={len(rth5)} bars, daily={len(daily)} bars, in {time.time()-t0:.1f}s")

    # Extend the daily series past the cache's native end (2026-06-12) via a yfinance ES=F
    # daily gap-fill (disclosed lower-fidelity, matches run_swing_battery.py's established
    # 2026-07-09 convention) -- gives a late-cache-window trade room to resolve on TIME
    # rather than DATA_END, and grows the (already small) OOS sample for a rare cohort where
    # every extra trading day matters. Best-effort: a fetch failure degrades to the native
    # cached window only, never fatal.
    cache_end = daily["date"].max()
    today = dt.date.today()
    daily_ext = daily
    gap_rows = 0
    try:
        gap = fetch_es_daily_gap(str(cache_end), str(today + dt.timedelta(days=1)))
        gap = gap[gap["date"] > cache_end].reset_index(drop=True)
        if not gap.empty:
            daily_ext = pd.concat(
                [daily, gap[["timestamp_et", "date", "open", "high", "low", "close", "volume"]]],
                ignore_index=True)
            gap_rows = len(gap)
            log(f"yfinance ES=F daily gap-fill: +{gap_rows} rows through {gap['date'].max()}")
    except Exception as e:  # noqa: BLE001 -- best-effort extension, never fatal
        log(f"yfinance gap-fill FAILED ({e!r}) -- proceeding with cache-only daily series")

    vix_by_date = {}
    try:
        vix_df = fetch_vix_daily("2025-01-01", str(today + dt.timedelta(days=1)))
        vix_by_date = dict(zip(vix_df["date"], vix_df["vix_close"]))
        log(f"VIX daily rows: {len(vix_df)}")
    except Exception as e:  # noqa: BLE001 -- regime split is descriptive, never fatal
        log(f"VIX fetch FAILED ({e!r}) -- regime_split will be empty")

    return {"raw": raw, "rth5": rth5, "daily": daily_ext, "daily_native_end": cache_end,
            "vix_by_date": vix_by_date, "md5": md5_of(MES_CSV), "span_et": list(span),
            "rows_1m": len(raw), "gap_rows": gap_rows}


def scan_rare_cohort(rth5: pd.DataFrame) -> dict:
    """Scans the 4 rare-cohort combos on RTH 5m bars (bear direction only). Returns
    {combo_id: DataFrame[ts, date, wick_frac, bars_since_break, vol_break_ratio]} -- the raw
    (undeduped) fires, for funnel reporting BEFORE the daily-index collapse."""
    bars = rth5[["timestamp_et", "open", "high", "low", "close", "volume"]].copy()
    ribbon = compute_ribbon(bars["close"])
    tt = rth5["timestamp_et"].dt.time
    eligible = np.flatnonzero((tt >= SIG_MIN) & (tt <= SIG_MAX))
    eligible = eligible[eligible >= WARMUP_BARS]

    out = {}
    for combo in build_combos():
        params = _params_for(combo)
        rows = []
        for i in eligible:
            sig = detect(bars, int(i), params, direction=DIRECTION, ribbon_df=ribbon)
            if sig is None:
                continue
            rows.append({
                "ts_et": rth5["timestamp_et"].iloc[i], "date": rth5["date"].iloc[i],
                "wick_frac": sig["wick_frac"], "bars_since_break": sig["bars_since_break"],
                "vol_break_ratio": sig["vol_break_ratio"],
            })
        out[combo["combo_id"]] = pd.DataFrame(rows)
        log(f"  {combo['combo_id']}: {len(rows)} raw 5m fires "
           f"(wf={combo['wick_frac_min']} lb={combo['break_lookback_bars']} "
           f"vol>={combo['vol_mult_min']})")
    return out


def signals_to_daily_index(fires_by_combo: dict, daily: pd.DataFrame) -> pd.DataFrame:
    """Collapses each combo's 5m fires to (>=1) one signal per calendar day -- the FIRST fire
    of the day (chronological) becomes that combo's daily_idx+1 entry signal; later same-day
    fires are dropped (they would otherwise map to the identical signal_bar_idx and
    manufacture duplicate trades, since battery.py's mechanics run on DAILY bars)."""
    date_to_idx = {d: i for i, d in enumerate(daily["date"])}
    rows = []
    for combo_id, fires in fires_by_combo.items():
        if fires.empty:
            continue
        first_per_day = fires.sort_values("ts_et").drop_duplicates(subset="date", keep="first")
        for r in first_per_day.itertuples():
            idx = date_to_idx.get(r.date)
            if idx is None:
                continue
            rows.append({"combo_id": combo_id, "signal_bar_idx": idx, "direction": "short",
                        "signal_date": str(r.date), "wick_frac": r.wick_frac,
                        "vol_break_ratio": r.vol_break_ratio})
    cols = ["combo_id", "signal_bar_idx", "direction", "signal_date", "wick_frac", "vol_break_ratio"]
    return pd.DataFrame(rows, columns=cols)


def compute_verdict(scorecard: dict) -> tuple[str, str]:
    """Overlay on top of battery.py's own per-cell `clears`/aggregate PASS-KILL output (never
    edits battery.py -- this is pure post-processing of its returned dict). Returns
    (verdict, rationale)."""
    n_clear = scorecard["n_clearing_cells"]
    n_eligible = scorecard["n_bh_fdr_eligible"]
    if n_clear > 0:
        return "PASS", f"{n_clear}/{scorecard['n_cells_tested']} cells clear every battery.py gate."
    if n_eligible == 0:
        n_short_signals = sum(1 for c in scorecard["cells"] if c["direction"] == "short")
        return ("INCONCLUSIVE_SMALL_N",
               f"0/{scorecard['n_cells_tested']} cells ever reached MIN_OOS_N="
               f"{battery.MIN_OOS_N} OOS trades (n_bh_fdr_eligible=0) -- the rare cohort fired "
               "too rarely to enter the BH-FDR family at all; this is NOT evidence against the "
               "cohort, it is an underpowered test (matches RESULTS.md's 2026-07-02 finding: "
               "'unpowered at 45 events/18mo ... parked, not disproven'). Per task instruction: "
               "reported as INCONCLUSIVE_SMALL_N, not KILL.")
    return ("KILL",
           f"{n_eligible} cell(s) reached the BH-FDR family (OOS n>=5) but 0 cleared every "
           "gate (oos_mean>0 AND bh_fdr_survivor(alpha=0.05) AND beats_buy_and_hold).")


def main() -> None:
    t0 = time.time()
    frames = load_frames()
    rth5, daily, vix_by_date = frames["rth5"], frames["daily"], frames["vix_by_date"]

    log("scanning the 4 rare-cohort (vol>=2.5) combos on RTH 5m bars, bear direction only ...")
    fires_by_combo = scan_rare_cohort(rth5)
    total_raw_fires = sum(len(v) for v in fires_by_combo.values())

    signals = signals_to_daily_index(fires_by_combo, daily)
    log(f"funnel: {total_raw_fires} raw 5m fires -> {len(signals)} deduped daily-bar signals "
       f"(first-per-day-per-combo)")
    for combo in build_combos():
        n = int((signals["combo_id"] == combo["combo_id"]).sum()) if len(signals) else 0
        log(f"  {combo['combo_id']}: {n} daily signals")

    grid = [{"combo_id": c["combo_id"]} for c in build_combos()]
    scorecard = battery.score_seed("rrw_rare", grid, signals, daily, MES, DAILY_HORIZONS,
                                    OOS_CUT, vix_by_date)
    log(f"battery.score_seed: {scorecard['n_cells_tested']} cells tested, "
       f"{scorecard['n_bh_fdr_eligible']} BH-FDR eligible, "
       f"{scorecard['n_clearing_cells']} clear -> raw verdict={scorecard['verdict']}")

    verdict, rationale = compute_verdict(scorecard)
    log(f"FINAL VERDICT (this script's overlay): {verdict} -- {rationale}")

    payload = {
        "rule_id": "futures-swing-rrw_rare", "phase": "1-followup",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "spec_origin": ("JOB 2, 2026-07-09 work order: re-test the RRW rare/high-quality "
                       "cohort DESIGN.md/RESULTS.md explicitly parked as 'not-disproven'."),
        "prior_art": {
            "path": "backtest/futures/analysis/PHASE1-swing-battery/RESULTS.md",
            "run_date": "2026-07-02", "verdict": "DOES_NOT_TRANSFER (whole battery)",
            "parked_quote": (
                "the RRW vol>=2.5 rare cohort -- direction-consistent both periods, "
                "opposite-direction loses, but unpowered at 45 events/18mo; it would need "
                "years of data or a relaxed-but-validated gate to power a test -- parked, "
                "not disproven"),
            "original_cohort_numbers": {
                "note": "original 5m-signal/ETH-5m-fill-walk mechanics, NOT this script's "
                        "daily-bar mechanics -- not directly comparable, reported for context",
                "vol_ge_2_5_event_count_18mo": "32-45 (4 combos)",
                "train_n_per_shape": "15-16", "test_n_per_shape": "3-4",
            },
        },
        "cohort_definition": {
            "detector": "backtest/lib/watchers/ribbon_rejection_wick_detector.detect",
            "direction": "bear (short) only -- the direction-real side per DESIGN.md",
            "grid": build_combos(),
            "close_margin_dollars_pts": CLOSE_MARGIN_PTS, "min_bar_range_dollars_pts": MIN_BAR_RANGE_PTS,
            "above_lookback_bars_default": 36, "vol_median_min_bars_default": 3,
            "signal_bar_timeframe": "RTH 5-minute", "signal_window_et": ["09:35", "15:30"],
            "warmup_bars": WARMUP_BARS,
        },
        "harness": {
            "module": "backtest/futures/battery.py (score_seed/run_cell) + "
                      "backtest/futures/swing_sim.py (wilder_atr/simulate_swing) -- "
                      "imported verbatim, not modified",
            "mechanics_bar_timeframe": "daily RTH (ATR14 + entry/stop/target walk)",
            "reuse_decision_note": ("signal detection runs on 5m bars (the only granularity "
                                    "vol_mult_min has meaning); each 5m signal is translated "
                                    "to its calendar date's DAILY bar index before entering "
                                    "battery.py, deduped first-per-day-per-combo. See module "
                                    "docstring REUSE DECISION section for full rationale."),
            "oos_cut": str(OOS_CUT), "horizons": DAILY_HORIZONS,
            "stop_mult": battery.DEFAULT_STOP_MULT, "target_mult": battery.DEFAULT_TARGET_MULT,
            "cost_per_side_usd": battery.DEFAULT_COST_PER_SIDE_USD, "min_oos_n": battery.MIN_OOS_N,
            "alpha": 0.05,
        },
        "data": {
            "source": str(MES_CSV), "md5": frames["md5"], "rows_1m": frames["rows_1m"],
            "span_et": frames["span_et"], "daily_native_end": str(frames["daily_native_end"]),
            "daily_extended_via_yfinance_es_gap_fill": frames["gap_rows"] > 0,
            "yfinance_gap_fill_rows": frames["gap_rows"],
        },
        "funnel": {
            "raw_5m_fires_by_combo": {cid: int(len(v)) for cid, v in fires_by_combo.items()},
            "raw_5m_fires_total": total_raw_fires,
            "deduped_daily_signals_total": int(len(signals)),
            "deduped_daily_signals_by_combo": (
                {cid: int((signals["combo_id"] == cid).sum()) for cid in fires_by_combo}
                if len(signals) else {cid: 0 for cid in fires_by_combo}),
        },
        "verdict": verdict, "verdict_rationale": rationale,
        "battery_raw_verdict": scorecard["verdict"],
        "n_cells_tested": scorecard["n_cells_tested"],
        "n_bh_fdr_eligible": scorecard["n_bh_fdr_eligible"],
        "n_clearing_cells": scorecard["n_clearing_cells"],
        "cells": scorecard["cells"],
        "runtime_sec": round(time.time() - t0, 1),
    }

    REC_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    log(f"scorecard written: {OUT_PATH}")

    DATA_VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    with DATA_VERSIONS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ran_at": dt.datetime.now().isoformat(timespec="seconds"), "symbol": "mes_futures",
            "as_of": str(dt.date.today()), "status": "ok",
            "action": "rrw_rare_cohort_followup_2026_07_09",
            "source": str(MES_CSV), "md5": frames["md5"], "rows_1m": frames["rows_1m"],
            "span_et": frames["span_et"],
            "note": ("JOB 2 follow-up to the 2026-07-02 PHASE1-swing-battery's parked "
                     "vol>=2.5 RRW-short rare cohort. Verdict: " + verdict + ". "
                     "Scorecard: analysis/recommendations/futures-swing-rrw_rare.json"),
        }) + "\n")
    log(f"data-versions.jsonl provenance row appended")
    log(f"TOTAL runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
