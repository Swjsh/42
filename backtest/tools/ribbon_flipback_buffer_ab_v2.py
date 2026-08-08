#!/usr/bin/env python
"""ribbon_flipback_buffer_ab_v2.py -- PRE-REGISTERED v2 ribbon-flip-back DECISIVENESS A/B.

Executes analysis/recommendations/prereg-ribbon-flipback-buffer-v2-2026-08-08.json (frozen
2026-08-08 ~06:00 ET, BEFORE this runner existed). v2 supersedes the v1 prereg, whose
`stop_rule` correctly fired: the v1 frozen candidate ("SPY $ beyond the flip boundary") has
NO live code surface (heartbeat_core._ribbon_flip_fn / exit_manager_walk both derive the
ribbon-flip-back boolean from a bare categorical stack equality -- no SPY-dollar boundary is
ever computed or compared). v2 re-freezes on the two surfaces that ARE code-grounded:

  1. spread_cents  -- backtest/lib/ribbon.py `compute_ribbon`'s EMA-internal spread (in
     cents), produced by the SAME pure function call that yields the categorical 'stack'
     column exit_manager_walk.ribbon_stack_at reads. A flip-back only counts as invalidation
     when spread_cents at that closed read is >= a frozen percentile threshold (decisiveness
     filter: a thin, indecisive EMA fan is not treated as a real stack reversal).
  2. confirm-closes -- the categorical stack sequence must show N (1 or 2) CONSECUTIVE closed
     opposing reads before the flip counts, using the run-length of opposing-stack closed
     reads (matching the v1 script's proven `_run_length` mechanism, reused verbatim below).

MECHANISM (identical discipline to v1, restated): variants change ONLY the caller-side
derivation of the ribbon_flip_back boolean fed into `exit_manager.plan_exit_actions`.
`exit_manager_walk.py` and `automation/state/fleet/exit_manager.py` are READ, NEVER WRITTEN.
The CONTROL replay passes the raw, unmodified `aligned[['stack']]` column straight through --
byte-identical to the live derivation (a bare single-tick categorical equality, per
exit_manager.py's 2026-08-08 in-code correction of the old "spread+buffer" comment).

CONTROL SEMANTICS (quoted verbatim, per the prereg's discipline):
  As literally implemented by backtest/lib/exit_manager_walk.py (`ribbon_stack_at` +
  the walk loop's `flip = (stack=='BULL') if side=='P' else (stack=='BEAR')`): a RAW
  single-closed-bar categorical stack read -- NO price buffer, NO confirming-close count,
  NO spread_cents gate. Every candidate here narrows (never widens) the set of ticks where
  that raw equality is allowed to register as `ribbon_flip_back=True`.

CONTROL PARITY STOP-RULE (mandatory, run BEFORE any candidate replay -- see
`run_control_parity_check`): 8 sampled positions (mixed outcome/account/setup), CONTROL
replayed via the shipped-shape chain (`winner_autopsy.resolve_shipped_shape` off the as-
placed `placement`/`exec` decision-row block -- the SAME live-resolution chain the nightly
Gamma_WinnerAutopsy fire uses, not a strategy-name guess), reconciled against the real
broker-fill `actual_exit_pnl` within max($40, 15%). >=6/8 (proportionally, `ceil(0.75*n)`
for a smaller smoke sample) must reconcile or this run STOPS and reports the divergence --
no candidate ever runs on top of an unreconciled reconstruction.

PERCENTILE PINNING (`collect_opposing_flip_reads` + `pin_percentiles`): spread_cents is
measured across every DISTINCT opposing-stack closed 5m read that occurred inside each
position's CONTROL-managed tick window (from entry+1 through CONTROL's own resolution/last
tick -- i.e. exactly the ticks CONTROL's ribbon-flip check was live for), deduplicated back
to the underlying 5m closed-read cadence (never inflated by 1-min-cadence repetition of the
same 5m read). Percentiles are pinned ONCE, before any candidate is built, from this corpus.

POPULATION: mae-mfe.json's 219 frozen scored engine positions (2026-06-26..2026-08-07),
matched onto exit_shape_parity_study.reconstruct_positions the same way the frozen v1 script
did. Bars: exit_shape_parity_study.fetch_option_bars (real OPRA 1-min), fetched ONCE per
(symbol, date) into a session cache (backtest/data/ribbon_flipback_ab_cache/) -- REUSED here
from the v1 attempt's already-fetched cache where present, never re-fetched per shape.

REPLAY: backtest/lib/exit_manager_walk.walk_exit_manager driving the production
automation/state/fleet/exit_manager.plan_exit_actions. Never a BS-sim (2026-07-09 scar).

Run (full 219, the RUNNER's job -- NOT run by the builder):
    backtest/.venv/Scripts/python.exe backtest/tools/ribbon_flipback_buffer_ab_v2.py
Run (fast smoke, real fetches, capped population -- what the BUILDER runs to prove the
pipeline works end-to-end):
    backtest/.venv/Scripts/python.exe backtest/tools/ribbon_flipback_buffer_ab_v2.py --limit 5
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import exit_shape_parity_study as esp  # noqa: E402
import winner_autopsy as wa  # noqa: E402
import trade_autopsy as ta  # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402
from ribbon import compute_ribbon  # noqa: E402
from exit_manager import TIME_STOP_ET  # noqa: E402

STATE = REPO / "automation" / "state"
FLEET = STATE / "fleet"
CACHE_DIR = REPO / "backtest" / "data" / "ribbon_flipback_ab_cache"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-07.csv"
ARCH = REPO / "analysis" / "regime-library" / "day-archetypes.json"
MAE_MFE = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
PREREG = REPO / "analysis" / "recommendations" / "prereg-ribbon-flipback-buffer-v2-2026-08-08.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "ribbon-flipback-buffer-ab-v2-2026-08-08.json"
OUT_MD = REPO / "analysis" / "recommendations" / "ribbon-flipback-buffer-ab-v2-2026-08-08.md"

FLEET_REST_ARMS = ta.FLEET_REST_ARMS               # ("safe-1","safe-3","risky-1","risky-3")
CORE_ARMS = tuple(ta.CORE_ARM_ACCOUNT)              # ("safe-2","bold-2")
ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS
SAFE_ARMS = {"safe-1", "safe-2", "safe-3"}
BOLD_ARMS = {"bold-2", "risky-1", "risky-3"}
TIME_STOP = TIME_STOP_ET

TREND_LIKE = {"trend-up", "trend-down", "gap-go"}
CHOP_LIKE = {"range-chop", "pin-day", "gap-fade", "V-reversal", "inverted-V"}

CONTROL_PARITY_N_SAMPLE = 8
CONTROL_PARITY_MIN_PASS_FRACTION = 0.75  # 6/8 at full sample size
CONTROL_PARITY_TOL_ABS = 40.0
CONTROL_PARITY_TOL_PCT = 0.15

BH_Q = 0.10
POWER_FLOOR_N = 15
N_BOOTSTRAP = 4000
_RNG_SEED = 20260808  # frozen seed -- reproducible bootstrap, not re-picked after seeing results


# ==============================================================================================
# TIME HELPERS
# ==============================================================================================
def _naive_et(ts: str) -> dt.datetime:
    s = ts.strip()
    if s.endswith("Z"):
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        d = dt.datetime.fromisoformat(s)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
    return d


# ==============================================================================================
# POPULATION -- mae-mfe.json is the frozen SET; esp.* is the frozen RECONSTRUCTION MACHINERY
# ==============================================================================================
def load_frozen_population() -> tuple[list[dict], dict]:
    ledger = json.loads(MAE_MFE.read_text(encoding="utf-8"))
    trades = ledger["trades"]
    target_keys = {(t["date"], t["arm"], t["symbol"], t["entry_ts_utc"]) for t in trades}
    outcome_by_key = {(t["date"], t["arm"], t["symbol"], t["entry_ts_utc"]): t["outcome"]
                      for t in trades}
    stop_meta_by_key = {(t["date"], t["arm"], t["symbol"], t["entry_ts_utc"]): t["stop"]
                        for t in trades}

    fills = esp.load_fleet_engine_fills(arms=ALL_LIVE_ARMS)
    all_positions = esp.reconstruct_positions(fills)
    ts_et_by = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}

    matched = []
    for p in all_positions:
        key = (p["date_et"], p["arm"], p["symbol"], p["entry_ts_utc"])
        if key not in target_keys:
            continue
        p = dict(p)
        p["entry_ts_et"] = ts_et_by.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
        p["mae_mfe_outcome"] = outcome_by_key[key]
        p["mae_mfe_stop_meta"] = stop_meta_by_key[key]
        matched.append(p)
    matched = [p for p in matched if p["entry_ts_et"] and int(round(p["entry_qty"])) >= 1]

    meta = {
        "n_frozen_target": len(target_keys), "n_reconstructed_total": len(all_positions),
        "n_matched": len(matched), "n_unmatched_target_keys": len(target_keys) - len(matched),
    }
    return sorted(matched, key=lambda x: (x["date_et"], x["entry_ts_et"], x["arm"], x["symbol"])), meta


def option_side_from_symbol(symbol: str) -> str:
    s = symbol[9]
    assert s in ("C", "P"), f"unexpected side char {s!r} in symbol {symbol!r}"
    return s


# ==============================================================================================
# BAR CACHE -- fetch ONCE per unique (symbol, date), session-local, replay CONTROL + 7
# candidates from RAM. REUSES backtest/data/ribbon_flipback_ab_cache/ left by the v1 attempt.
# ==============================================================================================
def load_opt_bars_cached(symbol: str, date_et: str) -> Optional[pd.DataFrame]:
    import time as _time_mod
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{symbol}_{date_et}.json"
    if cache_path.exists():
        bars = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        bars = esp.fetch_option_bars(symbol, date_et)
        cache_path.write_text(json.dumps(bars), encoding="utf-8")
        _time_mod.sleep(0.15)  # be polite to the data API on cache misses only
    if not bars:
        return None
    rows = []
    for b in bars:
        ts = pd.Timestamp(b["t"])
        if ts.tzinfo is not None:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        rows.append({"timestamp_et": ts, "open": float(b["o"]), "high": float(b["h"]),
                     "low": float(b["l"]), "close": float(b["c"])})
    if not rows:
        return None
    return pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)


# ==============================================================================================
# RIBBON RECONSTRUCTION -- caller-side ONLY (zero production edits). PRODUCTION compute_ribbon
# (backtest/lib/ribbon.py), unmodified, over the cached SPY 5m closes. RTH-only continuous EMA
# warmup (matches engine_fullhist_replay.build_ribbon_lookup's documented "byte-identical
# inputs to what orchestrator.run_backtest computes internally" convention, reused verbatim
# from the v1 attempt -- same mechanism, proven by that script's own passing test suite).
# NO-LOOKAHEAD join: closes_at = timestamp_et + 5min, merge_asof(direction="backward") --
# the SAME convention exit_manager_walk.last_closed_bar_close_at uses for its own scalar
# lookups (C6: every 1-min row carries the most recent CLOSED 5m read, never the forming bar).
# ==============================================================================================
def _run_length(mask: pd.Series) -> pd.Series:
    grp = (mask != mask.shift(fill_value=False)).cumsum()
    run = mask.groupby(grp).cumcount() + 1
    return run.where(mask, 0)


def build_ribbon_lookup_full(spy_df: pd.DataFrame) -> pd.DataFrame:
    rth_mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
                & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_df.loc[rth_mask].reset_index(drop=True)
    ribbon = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["close"] = spy_rth["close"].values
    out["stack"] = ribbon["stack"].values
    out["spread_cents"] = ribbon["spread_cents"].values
    is_bull = out["stack"] == "BULL"
    is_bear = out["stack"] == "BEAR"
    out["bull_run"] = _run_length(is_bull)
    out["bear_run"] = _run_length(is_bear)
    out["closes_at"] = out["timestamp_et"] + pd.Timedelta(minutes=5)
    out = out.sort_values("closes_at", kind="stable").reset_index(drop=True)
    out["lookup_idx"] = out.index  # stable row identity, survives the merge_asof join below
    return out


def ribbon_tick_df_for_full(opt_df: pd.DataFrame, lookup_full: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy().sort_values("timestamp_et", kind="stable")
    right = lookup_full.drop(columns=["timestamp_et"])
    merged = pd.merge_asof(left, right, left_on="timestamp_et", right_on="closes_at",
                           direction="backward")
    assert len(merged) == len(opt_df), "merge_asof row count drifted from opt_df"
    return merged.reset_index(drop=True)


# ==============================================================================================
# CANDIDATE CONSTRUCTION -- the v2 axis: spread_cents decisiveness gate x confirm-closes.
# CONTROL is `aligned[['stack']]` UNCHANGED (raw derivation, passed straight to
# walk_exit_manager -- zero suppression). A candidate overrides 'stack' to a neutral value
# ('MIXED') at any tick where {spread_cents >= min_spread_cents} AND {run-length of
# consecutive opposing closed reads >= confirm_closes} does NOT both hold, so
# exit_manager_walk's own UNMODIFIED flip test (stack=='BULL'/'BEAR') naturally yields the
# gated boolean. Both conditions are re-evaluated FRESH at every tick (no persisted "once
# confirmed always confirmed" state) -- this mirrors production's own statelessness: every
# real tick recomputes `ribbon_flip_back` from scratch (heartbeat_core._ribbon_flip_fn /
# exit_manager_walk's walk loop), never carries a flag forward.
# NaN spread_cents (WARMUP bars) fails CLOSED via pandas' NaN>=x -> False -- a warmup read can
# never satisfy the decisiveness gate, matching C7 (no silent pass-through of missing data).
# ==============================================================================================
def candidate_ribbon_tick_df(aligned: pd.DataFrame, side: str, min_spread_cents: float,
                             confirm_closes: int) -> pd.DataFrame:
    opposite = "BULL" if side == "P" else "BEAR"
    run_col = aligned["bull_run"] if side == "P" else aligned["bear_run"]
    confirm_ok = run_col >= confirm_closes
    spread_ok = aligned["spread_cents"] >= min_spread_cents
    raw_flip = aligned["stack"] == opposite
    suppressed = raw_flip & ~(confirm_ok & spread_ok)
    stack = aligned["stack"].where(~suppressed, other="MIXED")
    return pd.DataFrame({"stack": stack})


# ==============================================================================================
# SHAPE RESOLUTION -- "live-resolved shapes via the resolve_shipped_shape chain" (task spec).
# Uses the SAME machinery the nightly Gamma_WinnerAutopsy fire uses: the as-PLACED
# `placement`/`exec` block off the arm's own decision ledger row (winner_autopsy.
# find_entry_decision), layered with the arm's accounts.json exit_patch
# (winner_autopsy.resolve_shipped_shape) -- NOT a strategy-name guess. `stop_mode` is
# deliberately never carried to "structure" by resolve_shipped_shape (its own documented
# choice: this replay never supplies last_closed_5m_close, so structure mode would silently
# degrade to a no-op stop) -- structure_stop_enabled is held False / trigger_level None
# UNIFORMLY across CONTROL and every candidate here, isolating the ribbon_flip_back axis this
# study is actually about (structure-stop width/reference is a separate, already-adjudicated
# axis -- structure-stop-reference-level-2026-07-20.json, NO-SHIP, untouched by this study).
# ==============================================================================================
_ARM_ROWS_CACHE: dict[tuple, list] = {}


def _arm_rows_cached(arm: str, date_et: str) -> list:
    key = (arm, date_et)
    if key not in _ARM_ROWS_CACHE:
        _ARM_ROWS_CACHE[key] = wa.load_arm_rows(arm, date_et)
    return _ARM_ROWS_CACHE[key]


def resolve_position_shape(p: dict, arm_patches: dict) -> dict:
    arm_rows = _arm_rows_cached(p["arm"], p["date_et"])
    entry_row = wa.find_entry_decision(arm_rows, p["symbol"])
    placement = None
    setup_name = None
    if entry_row:
        placement = entry_row.get("placement") or entry_row.get("exec")
        setup_name = entry_row.get("setup_name") or entry_row.get("setup")
    shape = wa.resolve_shipped_shape(placement, arm_patches.get(p["arm"]))
    p["setup"] = setup_name or "(unattributed)"
    p["entry_row_found"] = entry_row is not None
    return shape


# ==============================================================================================
# REPLAY CONTEXT -- ONE opt_df fetch + ONE ribbon alignment + ONE shape resolution + ONE
# CONTROL walk per position, shared by the control-parity check, the percentile corpus, the
# whipsaw stat, and the A/B harness's control_rows (never re-fetched/re-walked per consumer).
# ==============================================================================================
def replay_control(p: dict, shape: dict, opt_df: pd.DataFrame, aligned: pd.DataFrame,
                   spy_full: pd.DataFrame, entry_dt: dt.datetime):
    control_ribbon_df = aligned[["stack"]]
    return walk_exit_manager(
        symbol=p["symbol"], side=p["side"], entry_time_et=entry_dt,
        entry_premium=float(p["entry_price"]), qty=int(round(p["entry_qty"])),
        exit_shape=shape, structure_stop_enabled=False, trigger_level=None,
        strategy="ribbon_flipback_ab_v2", time_stop_et=TIME_STOP,
        opt_df=opt_df, ribbon_tick_df=control_ribbon_df, five_min_spy_df=spy_full,
        opt_df_resolution="1min", frame="et-v2")


def build_replay_contexts(positions: list[dict], arm_patches: dict, ribbon_lookup: pd.DataFrame,
                          spy_full: pd.DataFrame) -> tuple[list[dict], dict]:
    ctx = []
    n_no_bars = []
    n_no_spy = []
    for p in positions:
        opt_df = load_opt_bars_cached(p["symbol"], p["date_et"])
        if opt_df is None or opt_df.empty:
            n_no_bars.append({"date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                              "actual_pnl": round(p["actual_exit_pnl"], 2)})
            continue
        aligned = ribbon_tick_df_for_full(opt_df, ribbon_lookup)
        if aligned["stack"].isna().all():
            n_no_spy.append({"date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"]})
            continue
        entry_dt = _naive_et(p["entry_ts_et"])
        shape = resolve_position_shape(p, arm_patches)
        ctl_res = replay_control(p, shape, opt_df, aligned, spy_full, entry_dt)
        if ctl_res.exit_reason == "no_bars_after_entry":
            n_no_bars.append({"date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                              "actual_pnl": round(p["actual_exit_pnl"], 2)})
            continue
        ctx.append({"p": p, "opt_df": opt_df, "aligned": aligned, "entry_dt": entry_dt,
                    "shape": shape, "ctl_res": ctl_res})
    return ctx, {"n_no_bars": n_no_bars, "n_no_spy_ribbon_coverage": n_no_spy}


# ==============================================================================================
# CONTROL PARITY STOP-RULE (prereg `ribbon_reconstruction.control_parity_stop_rule`)
# ==============================================================================================
def sample_control_parity_positions(positions: list[dict], n: int = CONTROL_PARITY_N_SAMPLE
                                    ) -> list[dict]:
    """Deterministic stratified sample across (outcome, safe/bold-account-family) buckets --
    NO randomness, reproducible/auditable. Round-robins non-empty buckets in sorted-key order,
    taking each bucket's earliest-by-date position per pass, until `n` positions are picked
    (or the population is exhausted). 'Mixed outcome/account/setup' per the prereg's wording."""
    buckets: dict[tuple, list] = defaultdict(list)
    for p in positions:
        fam = "safe" if p["arm"] in SAFE_ARMS else "bold"
        buckets[(p.get("mae_mfe_outcome", "?"), fam)].append(p)
    for lst in buckets.values():
        lst.sort(key=lambda p: (p["date_et"], p["entry_ts_et"]))
    order = sorted(buckets.keys())
    idxs = {k: 0 for k in order}
    sample = []
    while len(sample) < n and any(idxs[k] < len(buckets[k]) for k in order):
        progressed = False
        for k in order:
            if len(sample) >= n:
                break
            if idxs[k] < len(buckets[k]):
                sample.append(buckets[k][idxs[k]])
                idxs[k] += 1
                progressed = True
        if not progressed:
            break
    return sample[:n]


def _diagnose_divergence(row: dict) -> str:
    if row["control_exit_reason"] == "data_exhausted_force_close":
        return "no cached OPRA bars covered the actual resolution window (data/coverage gap)"
    if row["actual_n_exit_legs"] > 1 and row["control_exit_reason"] not in ("tp1",):
        return ("actual position exited in multiple legs (TP1 + runner); the replayed "
                "shipped_shape or ribbon reconstruction diverged before the runner leg")
    if not row.get("entry_row_found", True):
        return "no matching entry decision row found -- shipped_shape fell back to defaults"
    return ("shape/ribbon reconstruction diverges from the live tick sequence (e.g. a "
            "structure_stop or manual override this premium-only replay does not model)")


def run_control_parity_check(sample: list[dict], arm_patches: dict, ribbon_lookup: pd.DataFrame,
                             spy_full: pd.DataFrame) -> dict:
    rows = []
    for p in sample:
        opt_df = load_opt_bars_cached(p["symbol"], p["date_et"])
        if opt_df is None or opt_df.empty:
            rows.append({"date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                        "outcome": p.get("mae_mfe_outcome"), "actual_pnl": round(p["actual_exit_pnl"], 2),
                        "control_replay_pnl": None, "diff": None, "tolerance": None,
                        "reconciled": False, "control_exit_reason": "no_bars",
                        "actual_n_exit_legs": len(p["exit_fills"]), "entry_row_found": False})
            continue
        aligned = ribbon_tick_df_for_full(opt_df, ribbon_lookup)
        entry_dt = _naive_et(p["entry_ts_et"])
        shape = resolve_position_shape(p, arm_patches)
        res = replay_control(p, shape, opt_df, aligned, spy_full, entry_dt)
        tol = max(CONTROL_PARITY_TOL_ABS, CONTROL_PARITY_TOL_PCT * abs(p["actual_exit_pnl"]))
        diff = round(res.dollar_pnl - p["actual_exit_pnl"], 2)
        reconciled = abs(diff) <= tol
        rows.append({
            "date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
            "outcome": p.get("mae_mfe_outcome"), "setup": p.get("setup"),
            "actual_pnl": round(p["actual_exit_pnl"], 2), "control_replay_pnl": res.dollar_pnl,
            "diff": diff, "tolerance": round(tol, 2), "reconciled": reconciled,
            "control_exit_reason": res.exit_reason, "actual_n_exit_legs": len(p["exit_fills"]),
            "entry_row_found": p.get("entry_row_found", False), "shipped_shape": shape,
        })
    n = len(rows)
    n_reconciled = sum(1 for r in rows if r["reconciled"])
    required = math.ceil(CONTROL_PARITY_MIN_PASS_FRACTION * n) if n else 0
    passed = n_reconciled >= required
    divergences = [r for r in rows if not r["reconciled"]]
    return {
        "n_sampled": n, "n_reconciled": n_reconciled, "required": required, "passed": passed,
        "rows": rows,
        "diagnosis": [
            {"symbol": r["symbol"], "date_et": r["date_et"], "diff": r["diff"],
             "tolerance": r["tolerance"], "control_exit_reason": r["control_exit_reason"],
             "likely_cause": _diagnose_divergence(r)}
            for r in divergences
        ],
    }


# ==============================================================================================
# PERCENTILE PINNING + WHIPSAW BASE RATE (prereg `candidates_frozen.buffer_variable` /
# `disclosures_required.(7)`) -- computed ONCE from CONTROL, before any candidate is built.
# ==============================================================================================
def collect_opposing_flip_reads(ctx: list[dict]) -> tuple[list[dict], dict]:
    """For every replay context, dedupe the closed-5m reads inside the CONTROL-managed tick
    window [start_idx, start_idx + n_ticks_walked) back to their underlying 5m cadence (never
    inflated by 1-min-cadence repetition of the same closed read), and keep every read whose
    stack opposes that position's side. Fails CLOSED (excluded, counted) on NaN spread_cents."""
    reads = []
    n_nan_spread = 0
    n_positions_with_reads = 0
    for c in ctx:
        p, opt_df, aligned, entry_dt, ctl_res = c["p"], c["opt_df"], c["aligned"], c["entry_dt"], c["ctl_res"]
        start_idx_arr = opt_df.index[opt_df["timestamp_et"] > entry_dt]
        if len(start_idx_arr) == 0:
            continue
        start_idx = int(start_idx_arr[0])
        window = aligned.iloc[start_idx: start_idx + ctl_res.n_ticks_walked]
        window = window.drop_duplicates(subset=["closes_at"], keep="first")
        opposite = "BULL" if p["side"] == "P" else "BEAR"
        opp_rows = window[window["stack"] == opposite]
        n_this_position = 0
        for _, row in opp_rows.iterrows():
            sc = row["spread_cents"]
            if pd.isna(sc):
                n_nan_spread += 1
                continue
            reads.append({"date_et": p["date_et"], "symbol": p["symbol"], "side": p["side"],
                          "closes_at": row["closes_at"], "spread_cents": float(sc),
                          "lookup_idx": int(row["lookup_idx"])})
            n_this_position += 1
        if n_this_position:
            n_positions_with_reads += 1
    meta = {"n_flip_reads": len(reads), "n_nan_spread_excluded": n_nan_spread,
            "n_positions_with_flip_reads": n_positions_with_reads,
            "n_positions_considered": len(ctx)}
    return reads, meta


def pin_percentiles(reads: list[dict]) -> dict:
    vals = sorted(r["spread_cents"] for r in reads)
    if not vals:
        return {"n": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None}
    s = pd.Series(vals)
    return {
        "n": len(vals),
        "p25": round(float(s.quantile(0.25)), 4),
        "p50": round(float(s.quantile(0.50)), 4),
        "p75": round(float(s.quantile(0.75)), 4),
        "min": round(vals[0], 4), "max": round(vals[-1], 4),
    }


def whipsaw_base_rate(reads: list[dict], ribbon_lookup: pd.DataFrame) -> dict:
    """How often a flip un-flips within 1-2 closed reads under CONTROL (a market-behavior
    statistic on the ribbon itself, not bounded by any position's own management window --
    CONTROL exits on the FIRST opposing tick, so there is nothing to observe post-exit inside
    a position's own walk; this measures the underlying ribbon's persistence)."""
    n = len(reads)
    n_unflip_1 = 0
    n_unflip_within_2 = 0
    n_exhausted = 0
    stacks = ribbon_lookup["stack"]
    L = len(ribbon_lookup)
    for r in reads:
        idx = r["lookup_idx"]
        opposite = "BULL" if r["side"] == "P" else "BEAR"
        if idx + 1 >= L:
            n_exhausted += 1
            continue
        nxt1 = stacks.iloc[idx + 1]
        un1 = nxt1 != opposite
        if idx + 2 < L:
            nxt2 = stacks.iloc[idx + 2]
            un2 = un1 or (nxt2 != opposite)
        else:
            un2 = un1
        if un1:
            n_unflip_1 += 1
        if un2:
            n_unflip_within_2 += 1
    denom = n - n_exhausted
    return {
        "n_flip_reads": n, "n_lookup_exhausted": n_exhausted,
        "n_unflip_within_1_read": n_unflip_1, "n_unflip_within_2_reads": n_unflip_within_2,
        "whipsaw_rate_1_read": round(n_unflip_1 / denom, 4) if denom else None,
        "whipsaw_rate_within_2_reads": round(n_unflip_within_2 / denom, 4) if denom else None,
    }


def build_candidate_defs(pcts: dict) -> dict:
    """{0, p25, p50, p75} x {1, 2 confirm closes} minus (0,1)=CONTROL -- prereg's frozen grid.
    Percentiles that are None (empty corpus, e.g. a tiny smoke sample) are simply omitted --
    disclosed via the resulting candidate count, never a fabricated fallback value."""
    thresholds = {"P0": 0.0}
    for name, key in (("P25", "p25"), ("P50", "p50"), ("P75", "p75")):
        if pcts.get(key) is not None:
            thresholds[name] = pcts[key]
    defs = {}
    for tname, tval in thresholds.items():
        for confirm in (1, 2):
            if tname == "P0" and confirm == 1:
                continue  # == CONTROL (min_spread_cents=0, confirm=1) -- excluded per grid
            defs[f"{tname}-C{confirm}"] = {"min_spread_cents": tval, "confirm_closes": confirm,
                                           "threshold_label": tname}
    return defs


# ==============================================================================================
# STATS -- one-sided bootstrap p (paired-delta mean > 0) + BH-FDR. Reused verbatim from the
# v1 attempt's proven mechanism (same shape of problem: n candidates vs one CONTROL anchor).
# ==============================================================================================
def one_sided_bootstrap_p(xs: list[float], n_boot: int, rng: random.Random) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    count_le_zero = 0
    for _ in range(n_boot):
        resample_mean = sum(xs[rng.randrange(n)] for _ in range(n)) / n
        if resample_mean <= 0:
            count_le_zero += 1
    return round(count_le_zero / n_boot, 5)


def bh_fdr(p_by_cid: dict, q: float = BH_Q) -> dict:
    items = [(cid, p) for cid, p in p_by_cid.items() if p is not None]
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    thresholds = {}
    largest_k_significant = -1
    for k, (cid, p) in enumerate(items, start=1):
        thr = (k / m) * q if m else q
        thresholds[cid] = round(thr, 6)
        if p <= thr:
            largest_k_significant = k
    significant_cids = {cid for k, (cid, p) in enumerate(items, start=1)
                        if k <= largest_k_significant}
    return {cid: {"p": p_by_cid.get(cid), "bh_threshold": thresholds.get(cid),
                  "significant": cid in significant_cids}
            for cid in p_by_cid}


# ==============================================================================================
# GATES -- G1-G7 IDENTICAL in spirit to v1's (prereg: "IDENTICAL to v1 prereg verbatim");
# G8 = BH-FDR significance, folded into the verdict ladder below main().
# ==============================================================================================
def evaluate_candidate(rows: list[dict], arch_of: dict) -> dict:
    deltas = [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in rows]
    changed = [r for r, d in zip(rows, deltas) if abs(d) > 1e-6]
    n_changed = len(changed)

    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    agg_delta = round(candidate_total - control_total, 2)
    g1 = agg_delta > 0

    chop_rows = [r for r in rows if arch_of.get(r["date_et"], "UNTAGGED") in CHOP_LIKE]
    chop_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in chop_rows), 2)
    g2 = chop_delta >= 0

    runner_rows = [r for r in rows if r.get("control_reached_tp1")]
    runner_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in runner_rows), 2)
    g3_runner_ok = runner_delta >= 0
    anchor_rows = [r for r in rows if r.get("is_anchor")]
    anchor_regressions = [r for r in anchor_rows
                          if (r["candidate_pnl"] - r["control_pnl"]) < -10.0]
    g3_anchor_ok = len(anchor_regressions) == 0
    g3 = g3_runner_ok and g3_anchor_ok

    ordered = sorted(rows, key=lambda r: (r["date_et"], r["entry_ts_et"]))
    n = len(ordered)
    qsize = max(1, n // 4)
    quartiles = [ordered[i * qsize: (i + 1) * qsize] for i in range(3)]
    quartiles.append(ordered[3 * qsize:])
    quartiles = [q for q in quartiles if q]
    subwindow_report = []
    g4 = True
    for i, q in enumerate(quartiles):
        d = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in q), 2)
        nch = sum(1 for r in q if abs(r["candidate_pnl"] - r["control_pnl"]) > 1e-6)
        ok = d >= 0 and nch >= 5
        subwindow_report.append({"window": i + 1, "n": len(q), "n_changed": nch, "delta": d, "ok": ok})
        if not ok:
            g4 = False

    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date_et"]].append(r)
    day_deltas = {d: round(sum(r["candidate_pnl"] - r["control_pnl"] for r in rs), 2)
                  for d, rs in by_day.items()}
    best_day = max(day_deltas, key=lambda d: day_deltas[d]) if day_deltas else None
    delta_ex_best_day = round(agg_delta - day_deltas.get(best_day, 0.0), 2) if best_day else agg_delta
    g5 = delta_ex_best_day > 0

    day_control_totals = {d: round(sum(r["control_pnl"] for r in rs), 2) for d, rs in by_day.items()}
    worst_day = min(day_control_totals, key=lambda d: day_control_totals[d]) if day_control_totals else None
    worst_day_delta = day_deltas.get(worst_day, 0.0) if worst_day else 0.0
    g6 = worst_day_delta >= -100.0

    safe_rows = [r for r in rows if r["arm"] in SAFE_ARMS]
    bold_rows = [r for r in rows if r["arm"] in BOLD_ARMS]
    safe_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in safe_rows), 2)
    bold_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in bold_rows), 2)
    g7 = (safe_delta >= 0) and (bold_delta >= 0)

    power_ok = n_changed >= POWER_FLOOR_N

    return {
        "n": len(rows), "n_changed": n_changed, "power_floor_ok": power_ok,
        "control_total": control_total, "candidate_total": candidate_total,
        "aggregate_delta": agg_delta,
        "changed_deltas": [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in changed],
        "gates": {
            "G1_aggregate_positive": g1,
            "G2_chop_cohort": {"result": g2, "n": len(chop_rows), "delta": chop_delta},
            "G3_runner_and_anchor": {"result": g3, "runner_ok": g3_runner_ok,
                                     "runner_n": len(runner_rows), "runner_delta": runner_delta,
                                     "anchor_ok": g3_anchor_ok, "n_anchor": len(anchor_rows),
                                     "n_anchor_regressed": len(anchor_regressions)},
            "G4_subwindow_stability": {"result": g4, "windows": subwindow_report},
            "G5_drop_best_day": {"result": g5, "best_day": best_day,
                                 "best_day_delta": day_deltas.get(best_day),
                                 "delta_ex_best_day": delta_ex_best_day},
            "G6_worst_hard_day_not_worsened": {"result": g6, "worst_control_day": worst_day,
                                               "worst_day_control_total": day_control_totals.get(worst_day),
                                               "worst_day_delta": worst_day_delta},
            "G7_per_account_stratification": {"result": g7, "safe_n": len(safe_rows),
                                              "safe_delta": safe_delta, "bold_n": len(bold_rows),
                                              "bold_delta": bold_delta},
        },
        "by_day_delta": day_deltas,
    }


# ==============================================================================================
# MAIN
# ==============================================================================================
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="SMOKE MODE: cap the population to the first N matched positions "
                         "(fast, real fetches). Omit for the frozen full-219 run.")
    args = ap.parse_args(argv)
    smoke_mode = args.limit is not None

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    print(f"[ribbon-flipback-ab-v2] prereg loaded: {PREREG.name}", flush=True)

    positions, pop_meta = load_frozen_population()
    print(f"[ribbon-flipback-ab-v2] population: {pop_meta}", flush=True)
    if smoke_mode:
        positions = positions[:args.limit]
        print(f"[ribbon-flipback-ab-v2] SMOKE MODE: limited to {len(positions)} positions "
              f"(NOT the frozen 219 -- pipeline verification only)", flush=True)

    for p in positions:
        p["side"] = option_side_from_symbol(p["symbol"])

    arm_patches = wa.load_arm_exit_patches()

    print("[ribbon-flipback-ab-v2] loading SPY 5m + building continuous RTH ribbon lookup "
          "via PRODUCTION compute_ribbon...", flush=True)
    spy_raw = pd.read_csv(SPY5M)
    spy_ts = pd.to_datetime(spy_raw["timestamp_et"], utc=True, format="mixed")
    spy_ts = spy_ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    spy_full = spy_raw.assign(timestamp_et=spy_ts).sort_values("timestamp_et").reset_index(drop=True)
    ribbon_lookup = build_ribbon_lookup_full(spy_full)
    print(f"[ribbon-flipback-ab-v2] ribbon_lookup: {len(ribbon_lookup)} closed 5m RTH reads, "
          f"{spy_full['timestamp_et'].min()}..{spy_full['timestamp_et'].max()}", flush=True)

    # ---- STEP 2: CONTROL PARITY STOP-RULE (must pass BEFORE any candidate replay) ----------
    sample = sample_control_parity_positions(positions, n=min(CONTROL_PARITY_N_SAMPLE, len(positions)))
    parity = run_control_parity_check(sample, arm_patches, ribbon_lookup, spy_full)
    print(f"[ribbon-flipback-ab-v2] CONTROL PARITY: {parity['n_reconciled']}/{parity['n_sampled']} "
          f"reconciled (required {parity['required']}) -> "
          f"{'PASS' if parity['passed'] else 'STOP'}", flush=True)
    for d in parity["diagnosis"]:
        print(f"[ribbon-flipback-ab-v2]   DIVERGE {d['symbol']} {d['date_et']}: "
              f"diff=${d['diff']} (tol=${d['tolerance']}) reason={d['control_exit_reason']} "
              f"-- {d['likely_cause']}", flush=True)

    if not parity["passed"]:
        out = {
            "_doc": ("RIBBON-FLIP-BACK DECISIVENESS A/B v2 -- CONTROL PARITY STOP-RULE FIRED. "
                    "No candidate was replayed. This is the pre-registered discipline working, "
                    "not a failure to report around."),
            "generated_at": dt.datetime.now().isoformat(),
            "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
            "smoke_mode": smoke_mode, "smoke_limit": args.limit,
            "population": pop_meta,
            "control_parity_result": parity,
            "verdict": "STOP_CONTROL_PARITY_FAILED",
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"[ribbon-flipback-ab-v2] wrote {OUT_JSON}", flush=True)
        print("[ribbon-flipback-ab-v2] STOP RULE TRIGGERED -- aborting before any candidate "
              "replay (prereg discipline).", file=sys.stderr, flush=True)
        return 1

    # ---- STEP 1 (shared context) + STEP 3: PERCENTILE PINNING + WHIPSAW BASE RATE ----------
    ctx, excl = build_replay_contexts(positions, arm_patches, ribbon_lookup, spy_full)
    print(f"[ribbon-flipback-ab-v2] replay contexts built: {len(ctx)} "
          f"({len(excl['n_no_bars'])} no-bars, {len(excl['n_no_spy_ribbon_coverage'])} "
          f"no-SPY-ribbon-coverage)", flush=True)

    reads, reads_meta = collect_opposing_flip_reads(ctx)
    pcts = pin_percentiles(reads)
    whipsaw = whipsaw_base_rate(reads, ribbon_lookup)
    print(f"[ribbon-flipback-ab-v2] flip-read corpus: {reads_meta}", flush=True)
    print(f"[ribbon-flipback-ab-v2] pinned percentiles (spread_cents): {pcts}", flush=True)
    print(f"[ribbon-flipback-ab-v2] whipsaw base rate: {whipsaw}", flush=True)

    candidate_defs = build_candidate_defs(pcts)
    candidate_ids = tuple(candidate_defs.keys())
    print(f"[ribbon-flipback-ab-v2] {len(candidate_ids)} candidates: {candidate_defs}", flush=True)

    # ---- STEP 4: THE A/B HARNESS ------------------------------------------------------------
    arch = json.loads(ARCH.read_text(encoding="utf-8"))["days"]
    arch_of = {d: (arch.get(d) or {}).get("archetype", "UNTAGGED") for d in {c["p"]["date_et"] for c in ctx}}

    control_rows = []
    rows_by_candidate: dict = {cid: [] for cid in candidate_ids}

    for c in ctx:
        p, aligned, shape, ctl_res = c["p"], c["aligned"], c["shape"], c["ctl_res"]
        ctl_reached_tp1 = any(leg.stage == "tp1" for leg in ctl_res.legs)
        ctl_flip_fired = ctl_res.exit_reason in ("ribbon_flip_back", "ribbon_flip_back (runner)")
        control_rows.append({
            "date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
            "entry_ts_et": p["entry_ts_et"], "control_pnl": ctl_res.dollar_pnl,
            "control_exit_reason": ctl_res.exit_reason, "reached_tp1": ctl_reached_tp1,
            "ribbon_flip_fired": ctl_flip_fired, "actual_pnl": round(p["actual_exit_pnl"], 2),
            "setup": p.get("setup") or "(unattributed)",
            "outcome": p.get("mae_mfe_outcome"),
        })
        for cid in candidate_ids:
            cdef = candidate_defs[cid]
            cand_df = candidate_ribbon_tick_df(aligned, p["side"], cdef["min_spread_cents"],
                                               cdef["confirm_closes"])
            cand_res = walk_exit_manager(
                symbol=p["symbol"], side=p["side"], entry_time_et=c["entry_dt"],
                entry_premium=float(p["entry_price"]), qty=int(round(p["entry_qty"])),
                exit_shape=shape, structure_stop_enabled=False, trigger_level=None,
                strategy="ribbon_flipback_ab_v2", time_stop_et=TIME_STOP,
                opt_df=c["opt_df"], ribbon_tick_df=cand_df, five_min_spy_df=spy_full,
                opt_df_resolution="1min", frame="et-v2")
            rows_by_candidate[cid].append({
                "date_et": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                "entry_ts_et": p["entry_ts_et"], "control_pnl": ctl_res.dollar_pnl,
                "candidate_pnl": cand_res.dollar_pnl,
                "control_exit_reason": ctl_res.exit_reason,
                "candidate_exit_reason": cand_res.exit_reason,
                "control_reached_tp1": ctl_reached_tp1, "is_anchor": False,
            })

    control_total = round(sum(r["control_pnl"] for r in control_rows), 2)
    n_control_flip_fired = sum(1 for r in control_rows if r["ribbon_flip_fired"])
    print(f"[ribbon-flipback-ab-v2] CONTROL total=${control_total:+.2f} n={len(control_rows)} "
          f"ribbon_flip_back fired on {n_control_flip_fired} control replays", flush=True)

    rng = random.Random(_RNG_SEED)
    p_by_cid = {}
    eval_by_cid = {}
    for cid in candidate_ids:
        rows = rows_by_candidate[cid]
        ev = evaluate_candidate(rows, arch_of)
        changed_deltas = ev.pop("changed_deltas")
        p_val = (one_sided_bootstrap_p(changed_deltas, N_BOOTSTRAP, rng)
                if ev["power_floor_ok"] else None)
        p_by_cid[cid] = p_val
        eval_by_cid[cid] = ev
        print(f"[ribbon-flipback-ab-v2] {cid}: n_changed={ev['n_changed']} "
              f"agg_delta=${ev['aggregate_delta']:+.2f} power_floor={ev['power_floor_ok']}",
              flush=True)

    bh = bh_fdr(p_by_cid)

    verdicts = {}
    for cid in candidate_ids:
        ev = eval_by_cid[cid]
        if not ev["power_floor_ok"]:
            verdicts[cid] = "UNDERPOWERED"
            continue
        gate_results = [
            ev["gates"]["G1_aggregate_positive"], ev["gates"]["G2_chop_cohort"]["result"],
            ev["gates"]["G3_runner_and_anchor"]["result"], ev["gates"]["G4_subwindow_stability"]["result"],
            ev["gates"]["G5_drop_best_day"]["result"], ev["gates"]["G6_worst_hard_day_not_worsened"]["result"],
            ev["gates"]["G7_per_account_stratification"]["result"], bh[cid]["significant"],
        ]
        n_fail = sum(1 for g in gate_results if not g)
        verdicts[cid] = "SHIP" if n_fail == 0 else ("FREEZE+CLOCK" if n_fail == 1 else "CONTROL_HOLDS")
        print(f"[ribbon-flipback-ab-v2] {cid}: verdict={verdicts[cid]} (gate fails={n_fail}) "
              f"bh_p={bh[cid]['p']} bh_sig={bh[cid]['significant']}", flush=True)

    if any(v == "SHIP" for v in verdicts.values()):
        overall_verdict = "SHIP"
    elif any(v == "FREEZE+CLOCK" for v in verdicts.values()):
        overall_verdict = "FREEZE+CLOCK"
    elif candidate_ids and all(v == "UNDERPOWERED" for v in verdicts.values()):
        overall_verdict = "UNDERPOWERED"
    else:
        overall_verdict = "CONTROL_HOLDS"
    if smoke_mode:
        overall_verdict = f"SMOKE_MODE_NOT_ADJUDICABLE ({overall_verdict} at n={len(ctx)})"

    n_winners = sum(1 for r in control_rows if r["actual_pnl"] > 0)
    n_losers = sum(1 for r in control_rows if r["actual_pnl"] < 0)
    n_scratch = sum(1 for r in control_rows if r["actual_pnl"] == 0)

    out = {
        "_doc": ("RIBBON-FLIP-BACK DECISIVENESS A/B v2 (spread_cents threshold x confirm-"
                "closes) -- real-fills pain-ledger anchor, pre-registered, frozen before any "
                "candidate replay. Supersedes the v1 buffer prereg (stop_rule correctly fired: "
                "no SPY-dollar boundary surface exists). ANALYSIS ONLY: no trading-path file "
                "touched by this run."),
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preregistration_doc": preg.get("_doc"),
        "smoke_mode": smoke_mode, "smoke_limit": args.limit,
        "control_semantics_quoted_verbatim": (
            "As literally implemented by backtest/lib/exit_manager_walk.py's walk loop + "
            "ribbon_stack_at: flip = (stack=='BULL') if side=='P' else (stack=='BEAR'), where "
            "'stack' is the aligned ribbon_tick_df's categorical column at this tick. RAW "
            "single-closed-bar test: NO price buffer, NO confirming-close count, NO "
            "spread_cents gate. Confirmed 2026-08-08 in exit_manager.py's own in-code note: "
            "both real callers (heartbeat_core._ribbon_flip_fn live; exit_manager_walk "
            "replay) pass a bare single-tick categorical equality -- no caller-side buffer "
            "exists today. This study's CONTROL reproduces that raw derivation exactly."
        ),
        "population": {**pop_meta, "n_replayed": len(control_rows),
                      "n_no_bars": len(excl["n_no_bars"]),
                      "n_no_spy_ribbon_coverage": len(excl["n_no_spy_ribbon_coverage"]),
                      "n_winners": n_winners, "n_losers": n_losers, "n_scratch": n_scratch,
                      "arms": sorted(ALL_LIVE_ARMS),
                      "date_span": (f"{min(r['date_et'] for r in control_rows)}.."
                                   f"{max(r['date_et'] for r in control_rows)}") if control_rows else None},
        "control_parity_result": parity,
        "flip_read_corpus": reads_meta,
        "pinned_thresholds": {"metric": "spread_cents", "percentiles": pcts,
                              "measured_on": "CONTROL-managed-window opposing-stack closed "
                                             "reads, deduplicated to 5m cadence, computed "
                                             "ONCE before any candidate replay"},
        "whipsaw_base_rate": whipsaw,
        "candidate_defs": candidate_defs,
        "control_total_pnl": control_total,
        "control_n_ribbon_flip_fired": n_control_flip_fired,
        "gates_table": {cid: eval_by_cid[cid]["gates"] for cid in candidate_ids},
        "bh_fdr": {"q": BH_Q, "n_bootstrap": N_BOOTSTRAP, "results": bh},
        "candidate_summary": {
            cid: {"n": eval_by_cid[cid]["n"], "n_changed": eval_by_cid[cid]["n_changed"],
                 "power_floor_ok": eval_by_cid[cid]["power_floor_ok"],
                 "control_total": eval_by_cid[cid]["control_total"],
                 "candidate_total": eval_by_cid[cid]["candidate_total"],
                 "aggregate_delta": eval_by_cid[cid]["aggregate_delta"], "verdict": verdicts[cid]}
            for cid in candidate_ids
        },
        "verdict": overall_verdict,
        "verdicts_by_candidate": verdicts,
        "disclosures": [
            f"population loser-skew ({n_losers}L/{n_winners}W/{n_scratch}S) + single-regime "
            f"window -- IS/OOS-style sub-window labels overstate independence (one continuous "
            f"live period).",
            "shape resolved via winner_autopsy.resolve_shipped_shape off the as-placed "
            "placement/exec decision-row block (the SAME chain the nightly Gamma_WinnerAutopsy "
            "fire uses) -- NOT a strategy-name guess. structure_stop is held OFF uniformly "
            "(resolve_shipped_shape never resolves 'structure' mode by its own design) so this "
            "study isolates the ribbon_flip_back axis cleanly from the separately-adjudicated "
            "structure-stop-reference axis (NO-SHIP 2026-07-20, untouched here).",
            "(5) ribbon is RECONSTRUCTED (production compute_ribbon over cached SPY 5m closes), "
            "not the live engine's recorded ribbon state -- reconstruction-vs-live drift is "
            "possible if live compute inputs ever diverged from this SPY 5m cache.",
            f"(6) pinned percentile thresholds (spread_cents): {pcts} -- measured on "
            f"{reads_meta['n_flip_reads']} distinct opposing-stack closed reads across "
            f"{reads_meta['n_positions_with_flip_reads']} positions "
            f"({reads_meta['n_nan_spread_excluded']} WARMUP/NaN-spread reads excluded, C7).",
            f"(7) whipsaw base rate under CONTROL: {whipsaw}.",
            "C6 fill-mark convention (exit_manager_walk.py): market-style stages (ribbon_flip/"
            "structure_stop/time_stop) fill at that bar's CLOSE minus $0.02 slippage; "
            "limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the "
            "triggered premium level. 1-min OPRA point-sample convention (bar OPEN as both "
            "best/worst, OPTION-BAR-RESOLUTION-BIAS-2026-08-02).",
            "No J-anchor / is_anchor set is applied in v2 (G3's anchor leg is therefore a "
            "no-op check, n_anchor=0 always) -- v1's ANCHOR_FILLS list was a disclosed "
            "interpretive choice, not a prereg-named set; not re-asserted here without a "
            "named source.",
        ],
        "control_position_detail": control_rows,
        "position_detail": rows_by_candidate,
        "no_bars_excluded": excl["n_no_bars"],
        "no_spy_ribbon_coverage_excluded": excl["n_no_spy_ribbon_coverage"],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ribbon-flipback-ab-v2] wrote {OUT_JSON}", flush=True)
    print(f"[ribbon-flipback-ab-v2] OVERALL VERDICT: {overall_verdict}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
