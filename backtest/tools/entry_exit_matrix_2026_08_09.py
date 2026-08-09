"""entry_exit_matrix_2026_08_09.py -- J's /goal 2026-08-09: "dynamic entries and exit testing
across our trades, map it into a multi column/row matrix table and figure out what is
profitable." ENTRY variants (rows) x EXIT variants (columns), every cell scored on the SAME
real data, sequential one-position-at-a-time per (row,col) cell, on BOTH the 391-day replay
population and the ~25-trading-day real-fill book.

Frozen pre-registration (committed BEFORE this file, git-provable):
    analysis/recommendations/prereg-entry-exit-matrix-2026-08-09.json (commit edc595af)

NOT a re-run of analysis/recommendations/entry-exit-matrix-2026-07-09.md -- that pass's 5
verdicts (exit-A FAIL, exit-B FAIL, entry-1 FAIL, entry-1+exit-A FAIL, exit-C+entry-2
INCONCLUSIVE_NO_ANCHOR) are CITED in the output doc, never re-tested expecting a different
answer.

MECHANICS -- reuses existing, validated machinery wherever it exists (nothing rebuilt that
already works):
  * Population A (391-day replay): backtest/tools/score_ladder_replay_2026_08_07.py's OWN
    run_backtest_with_full_capture + SAFE_BASE_LIVE_NOW config, extended one trading day via
    the freshest cached SPY/VIX tail (spy_5m_2026-05-19_2026-08-07.csv). Gives r.trades
    (CONTROL's own binary entries) + bear_by_idx/bull_by_idx (full per-bar score/blockers/
    level/vix log used to build the other 7 entry rows).
  * Population B (~25-day real-fill book): analysis/entry-quality/entry-quality-ledger.json's
    OWN `events` array, REUSED verbatim -- 244 real engine-attributed option-BUY fills, 27
    trading days 2026-06-26..2026-08-07, broker truth (not a backtest re-simulation).
  * Exit engine (BOTH populations, ALL 12 columns): backtest/lib/exit_manager_walk.py
    #walk_exit_manager -> automation/state/fleet/exit_manager.py#plan_exit_actions -- the LIVE
    decision core. NEVER simulator_real (closes the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar).
  * Sequential, one-position-at-a-time (NOT_FLAT) walk PER (row, col, population) cell -- a
    later signal inside a still-open position's holding window is suppressed, not stacked;
    re-derived independently per cell so a wider stop's suppression effect on later re-entries
    is MEASURED, never assumed (score_ladder_replay.py#walk_lane's own discipline).

File ownership: analysis-only. Never touches backtest/lib/trendline_detector.py,
automation/state/fleet/exit_manager.py, params.json/aggressive/params.json/accounts.json,
backtest/futures/**, or TradingView chart code. Reads production code, writes to analysis/
and this one new file under backtest/tools/.

Run: backtest/.venv/Scripts/python.exe backtest/tools/entry_exit_matrix_2026_08_09.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent                                        # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
SCRIPTS_DIR = ROOT / "setup" / "scripts"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import score_ladder_replay_2026_08_07 as sl                # noqa: E402  -- reused machinery
import engine_fullhist_replay as efr                          # noqa: E402
import strategies as fleet_strategies                            # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from crypto.lib.market_structure import analyze_structure              # noqa: E402
from crypto.lib.bar import Bar                                          # noqa: E402

ET_ZONE = ZoneInfo("America/New_York")   # a real tzinfo (et_frame.ET_TZ is a bare tz-name STRING,
                                          # fine for pandas .tz_convert but not datetime.replace())

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-entry-exit-matrix-2026-08-09.json"
OUT_DIR = ROOT / "analysis" / "deep-research"
OUT_JSON = OUT_DIR / "ENTRY-EXIT-MATRIX-2026-08-09.json"
OUT_MD = OUT_DIR / "ENTRY-EXIT-MATRIX-2026-08-09.md"
SCORECARD_JSON = ROOT / "analysis" / "recommendations" / "entry-exit-matrix-2026-08-09-scorecard.json"
LEDGER_PATH = ROOT / "analysis" / "entry-quality" / "entry-quality-ledger.json"

DATA = REPO / "data"
OLD_SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-08-07.csv"   # freshest cached tail (extends sl's 08-06)
NEW_VIX_FILE = DATA / "vix_5m_2026-05-19_2026-08-07.csv"
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 8, 7)
OLD_WINDOW_END = dt.date(2026, 7, 22)

TUESDAY_GATE = "2026-08-04"
ZONE_BAND = 0.15
MIN_CONTRACTS_STUDY = sl.MIN_CONTRACTS_STUDY  # 3, matches the ladder study convention


def log(msg: str) -> None:
    print(f"[eem] {msg}", flush=True)


# =================================================================== data load (extends sl's)

def load_extended_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy_old = pd.read_csv(OLD_SPY_FILE)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY_FILE)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy = pd.concat([spy_old, spy_tail], ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    vix_old = pd.read_csv(OLD_VIX_FILE)
    vix_old["timestamp_et"] = pd.to_datetime(vix_old["timestamp_et"])
    vix_new = pd.read_csv(NEW_VIX_FILE)
    vix_new["timestamp_et"] = pd.to_datetime(vix_new["timestamp_et"])
    vix_tail = vix_new[vix_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    vix = pd.concat([vix_old, vix_tail], ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    return spy, vix


# =================================================================== EXIT COLUMNS (12)

BASE_EXIT = fleet_strategies.by_name("ribbon_ride").exit.to_dict()


def _shape(**overrides) -> dict:
    d = dict(BASE_EXIT)
    d.update(overrides)
    return d


def _static_col(shape: dict):
    def fn(position: dict, opt_df) -> dict:
        return shape
    return fn


def _atr_stop_col(position: dict, opt_df) -> dict:
    """ATR_STOP: premium-mode, PER-POSITION premium_stop_pct derived from the option's own
    realized bar range in the first 6 bars after entry (an option-premium ATR proxy -- no
    delta/Greeks exist in the historical cache, same disclosed gap T4 omitted entirely).
    multiplier 2.0x, clipped to [-0.15,-0.60]. Falls back to CONTROL's -0.20 if <2 bars."""
    entry_premium = position["entry_premium"]
    sample = opt_df[:6] if len(opt_df) >= 2 else opt_df
    if len(sample) < 2 or entry_premium <= 0:
        pct = -0.20
    else:
        ranges = [float(b["high"]) - float(b["low"]) for b in sample]
        atr = sum(ranges) / len(ranges)
        pct = -min(0.60, max(0.15, (2.0 * atr) / entry_premium))
    return {"premium_stop_pct": round(pct, 4), "tp1_premium_pct": BASE_EXIT["tp1_premium_pct"],
            "tp1_qty_fraction": BASE_EXIT["tp1_qty_fraction"], "profit_lock_mode": "trailing",
            "runner_target_pct": BASE_EXIT["runner_target_pct"], "trail_pct": BASE_EXIT["trail_pct"],
            "profit_lock_arm_pct": BASE_EXIT["profit_lock_arm_pct"], "stop_mode": "premium",
            "catastrophe_stop_pct": BASE_EXIT["catastrophe_stop_pct"]}


EXIT_COLUMNS: dict[str, Callable] = {
    "CONTROL": _static_col(_shape()),
    "TP1_30": _static_col(_shape(tp1_premium_pct=0.30)),
    "TP1_40": _static_col(_shape(tp1_premium_pct=0.40)),
    "TP1_50": _static_col(_shape(tp1_premium_pct=0.50)),
    "TP1_75": _static_col(_shape(tp1_premium_pct=0.75)),
    "MFE_TRAIL": _static_col(_shape(profit_lock_arm_pct=0.03, trail_pct=0.10)),
    "ATR_STOP": _atr_stop_col,
    "CATCAP_25": _static_col(_shape(catastrophe_stop_pct=-0.25)),
    "CATCAP_30": _static_col(_shape(catastrophe_stop_pct=-0.30)),
    "CATCAP_40": _static_col(_shape(catastrophe_stop_pct=-0.40)),
    "CATCAP_60": _static_col(_shape(catastrophe_stop_pct=-0.60)),
    "STRUCT_ONLY": _static_col(_shape(catastrophe_stop_pct=-0.95)),
}
COL_ORDER = list(EXIT_COLUMNS.keys())


# =================================================================== ENTRY ROWS (8)

DEMOTABLE_BULL = {5, 7, 8, 10}
DEMOTABLE_BEAR = {5, 7, 8, 9}
VIX_HARD_CAP_BEAR = 23.0
ROW_ORDER = ["CONTROL", "STRUCT8", "VD1", "LADDER7", "LADDER8", "LADDER9", "MAX3", "ZONE"]


def side_admission_single_demerit(side: str, score: int, blockers: list, level, vix) -> Optional[dict]:
    """LANE 1 (single-demerit) semantics per CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md:
    the logged score already IS the adjusted score (filters.py:1273 bull_score=11-len(blockers)),
    demotable blockers no longer veto. Distinct from score_ladder_replay's OWN side_admission
    (double-demerit, LANE 2) -- this file implements LANE 1 deliberately (matches this task's
    prereg + the brief's explicit "demotable filters subtract demerits" wording)."""
    demotable = DEMOTABLE_BULL if side == "C" else DEMOTABLE_BEAR
    active = list(blockers or [])
    if not active:
        return None
    if any(b not in demotable for b in active):
        return None
    if side == "P" and 8 in active and vix is not None and vix > VIX_HARD_CAP_BEAR:
        return None
    if level is None or not isinstance(level, (int, float)):
        return None
    return {"adjusted": int(score)}


def build_ladder_candidates(bear_by_idx: dict, bull_by_idx: dict, spy_rth: pd.DataFrame) -> list[dict]:
    out = []
    for idx in sorted(set(bear_by_idx) | set(bull_by_idx)):
        bear, bull = bear_by_idx.get(idx), bull_by_idx.get(idx)
        if (bear and bear["passed"]) or (bull and bull["passed"]):
            continue
        opts = []
        for side, blk in (("P", bear), ("C", bull)):
            if not blk:
                continue
            a = side_admission_single_demerit(side, blk["score"], blk["blockers"], blk["level"], blk["vix"])
            if a:
                opts.append((side, blk, a))
        if not opts:
            continue
        if len(opts) == 2:
            if opts[0][2]["adjusted"] == opts[1][2]["adjusted"]:
                continue
            opts.sort(key=lambda o: -o[2]["adjusted"])
        side, blk, adm = opts[0]
        bar = spy_rth.iloc[idx]
        out.append({"bar_idx": int(idx), "side": side, "timestamp_et": bar["timestamp_et"],
                    "date": bar["timestamp_et"].date().isoformat(), "score": blk["score"],
                    "blockers": blk["blockers"], "triggers": blk["triggers"], "level": float(blk["level"]),
                    "vix": blk["vix"], "spot": blk["spot"], "adjusted": adm["adjusted"]})
    return out


def build_zone_candidates(bear_by_idx: dict, bull_by_idx: dict, spy_rth: pd.DataFrame) -> list[dict]:
    """ZONE: level-proximity BAND admission ($0.15), ignores score entirely -- a genuinely
    DIFFERENT admission axis than the score ladder (widens the trigger's precision requirement
    rather than forgiving scoring blockers). 'adjusted'=0 lets this reuse sl.walk_lane's rung
    mechanism at rung=0 (always admits)."""
    out = []
    for idx in sorted(set(bear_by_idx) | set(bull_by_idx)):
        bear, bull = bear_by_idx.get(idx), bull_by_idx.get(idx)
        if (bear and bear["passed"]) or (bull and bull["passed"]):
            continue
        opts = []
        for side, blk in (("P", bear), ("C", bull)):
            if not blk:
                continue
            level, spot = blk.get("level"), blk.get("spot")
            if level is None or not isinstance(level, (int, float)) or spot is None:
                continue
            if abs(float(spot) - float(level)) <= ZONE_BAND:
                opts.append((side, blk))
        if not opts or len(opts) == 2:
            continue   # empty, or ambiguous same-bar dual-zone touch -> skip (disclosed)
        side, blk = opts[0]
        bar = spy_rth.iloc[idx]
        out.append({"bar_idx": int(idx), "side": side, "timestamp_et": bar["timestamp_et"],
                    "date": bar["timestamp_et"].date().isoformat(), "score": blk["score"],
                    "blockers": blk["blockers"], "triggers": blk["triggers"], "level": float(blk["level"]),
                    "vix": blk["vix"], "spot": blk["spot"], "adjusted": 0})
    return out


def _closed_bars_before(spy_rth: pd.DataFrame, entry_time_et: dt.datetime, lookback: int = 80) -> pd.DataFrame:
    """entry_time_et is always naive (post efr.naive_dt); spy_rth['timestamp_et'] may be
    tz-aware (the OPRA cache's fixed -04:00 convention) -- strip tz before comparing, same
    guard exit_manager_walk.py's _reframe_series applies (never a bare unconditional strip
    that would corrupt an already-naive series, per that module's own documented scar)."""
    ts = spy_rth["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    as_of = pd.Timestamp(entry_time_et)
    if as_of.tzinfo is not None:
        as_of = as_of.tz_localize(None)
    closes_at = ts + pd.Timedelta(minutes=5)
    eligible = spy_rth.loc[(closes_at <= as_of).values]
    if eligible.empty:
        return eligible
    return eligible.tail(lookback)


def structure_within_8(spy_rth: pd.DataFrame, entry_time_et: dt.datetime) -> bool:
    """R-S8-5m semantics (entry_quality_ledger.py's OWN definition, reproduced against the
    backtest's 5m frame instead of the live-fills SIP cache): a BOS/CHoCH event within the
    last 8 CLOSED 5m bars, direction-agnostic (matches a_structure_5m_within8's EVENT<=8bars
    bucket -- NOT the direction-aware a_structure_5m_bucket)."""
    closed = _closed_bars_before(spy_rth, entry_time_et)
    if len(closed) < 8:
        return False
    bars = [Bar(open_time=row["timestamp_et"].to_pydatetime().replace(tzinfo=ET_ZONE),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), volume=float(row["volume"]) if "volume" in closed.columns else 0.0,
                granularity_seconds=300, source="eem_backtest_5m")
            for _, row in closed.iterrows()]
    rd = analyze_structure(bars, window=3)
    if not rd.events:
        return False
    ev = rd.events[-1]
    bars_ago = (len(bars) - 1 - ev.break_index)
    return bars_ago <= 8


def vd1_agrees(spy_rth: pd.DataFrame, entry_time_et: dt.datetime, side: str) -> bool:
    """V-d1 semantics (entry_quality_ledger.py's OWN last5_direction, reproduced): the LAST
    fully closed 5m bar's own open->close direction must agree with the trade side."""
    closed = _closed_bars_before(spy_rth, entry_time_et)
    if closed.empty:
        return False
    last = closed.iloc[-1]
    direction = "up" if last["close"] > last["open"] else ("down" if last["close"] < last["open"] else "flat")
    want = "up" if side == "C" else "down"
    return direction == want


def apply_max3(trades: list) -> list:
    """Cap same (date, side) entries at 3/day. 'arm' collapses to one simulated lane
    (disclosed simplification of the brief's (arm,date,contract) key)."""
    counts: dict[tuple, int] = {}
    keep = []
    for t in sorted(trades, key=lambda x: efr.naive_dt(x.entry_time_et)):
        edate = t.entry_time_et
        edate = edate.date() if hasattr(edate, "date") else pd.Timestamp(edate).date()
        key = (edate.isoformat(), t.side)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= 3:
            keep.append(t)
    return keep


def apply_max3_events(events: list) -> list:
    counts: dict[tuple, int] = {}
    keep = []
    for e in sorted(events, key=lambda x: x["ts_et"]):
        key = (e["date_et"], e["opt_side"])
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= 3:
            keep.append(e)
    return keep


def build_rows_pop_a(r_trades: list, bear_by_idx: dict, bull_by_idx: dict, spy_rth: pd.DataFrame) -> dict:
    """Returns {row_id: {'binary': trades_subset, 'candidates': extras, 'rung': int|None}}."""
    struct8 = [t for t in r_trades if structure_within_8(spy_rth, efr.naive_dt(t.entry_time_et))]
    vd1 = [t for t in r_trades if vd1_agrees(spy_rth, efr.naive_dt(t.entry_time_et), t.side)]
    max3 = apply_max3(r_trades)
    ladder_cands = build_ladder_candidates(bear_by_idx, bull_by_idx, spy_rth)
    zone_cands = build_zone_candidates(bear_by_idx, bull_by_idx, spy_rth)
    return {
        "CONTROL": {"binary": r_trades, "candidates": [], "rung": None},
        "STRUCT8": {"binary": struct8, "candidates": [], "rung": None},
        "VD1": {"binary": vd1, "candidates": [], "rung": None},
        "LADDER7": {"binary": r_trades, "candidates": ladder_cands, "rung": 7},
        "LADDER8": {"binary": r_trades, "candidates": ladder_cands, "rung": 8},
        "LADDER9": {"binary": r_trades, "candidates": ladder_cands, "rung": 9},
        "MAX3": {"binary": max3, "candidates": [], "rung": None},
        "ZONE": {"binary": r_trades, "candidates": zone_cands, "rung": 0},
    }


# =================================================================== battery + stats

def _quarter_half_split(dates: list[str]) -> tuple[set, set]:
    uniq = sorted(set(dates))
    half = len(uniq) // 2
    return set(uniq[:half]), set(uniq[half:])


def battery(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "total": 0.0, "expectancy": None, "wr": None}
    df = pd.DataFrame(trades)
    n = len(df)
    total = float(df["dollar_pnl"].sum())
    exp = round(total / n, 2)
    wr = round(float((df["dollar_pnl"] > 0).mean()), 4)
    per_day = df.groupby("date")["dollar_pnl"].sum()
    best_day = float(per_day.max()) if len(per_day) else 0.0
    n_ex_best = n - int((df["date"] == per_day.idxmax()).sum()) if len(per_day) else n
    drop_best_day_exp = round((total - best_day) / n_ex_best, 2) if n_ex_best > 0 else None
    runner_trades = df[df.get("reached_tp1", False) == True] if "reached_tp1" in df.columns else df.iloc[0:0]
    runner_exp = round(float(runner_trades["dollar_pnl"].mean()), 2) if len(runner_trades) else None
    d1, d2 = _quarter_half_split(list(df["date"]))
    h1 = df[df["date"].isin(d1)]["dollar_pnl"]
    h2 = df[df["date"].isin(d2)]["dollar_pnl"]
    h1_exp = round(float(h1.mean()), 2) if len(h1) else None
    h2_exp = round(float(h2.mean()), 2) if len(h2) else None
    sub_window_stable = bool(h1_exp is not None and h2_exp is not None
                              and ((h1_exp > 0) == (h2_exp > 0) == (exp > 0)))
    tue = df[df["date"] == TUESDAY_GATE]["dollar_pnl"]
    tue_total = round(float(tue.sum()), 2) if len(tue) else None
    p_boot = sl.bootstrap_p_mean_gt0(list(df["dollar_pnl"]), n_boot=10000, seed=7)
    return {
        "n": n, "total": round(total, 2), "expectancy": exp, "wr": wr,
        "drop_best_day_expectancy": drop_best_day_exp, "best_day": round(best_day, 2),
        "runner_cohort_n": int(len(runner_trades)), "runner_cohort_expectancy": runner_exp,
        "first_half_exp": h1_exp, "second_half_exp": h2_exp, "sub_window_stable": sub_window_stable,
        "tuesday_0804_total": tue_total, "tuesday_0804_n": int(len(tue)),
        "bootstrap_p_mean_gt0": p_boot,
        "trading_days": int(df["date"].nunique()),
    }


# =================================================================== POPULATION A runner

def run_population_a() -> dict:
    log(f"loading extended SPY/VIX {FULL_START}..{FULL_END}")
    spy_raw, vix_df = load_extended_data()
    spy_rth = sl.build_rth_frame(spy_raw)
    log(f"  raw={len(spy_raw)} rows, rth={len(spy_rth)} rows, days={spy_rth['timestamp_et'].dt.date.nunique()}")

    t0 = _time.time()
    log("run_backtest(**SAFE_BASE_LIVE_NOW) with BOTH-side capture (reused from score_ladder_replay)")
    r, bear_by_idx, bull_by_idx = sl.run_backtest_with_full_capture(
        spy_raw, vix_df, start_date=FULL_START, end_date=FULL_END, **sl.SAFE_BASE_LIVE_NOW)
    log(f"  done {_time.time()-t0:.1f}s -- {len(r.trades)} CONTROL binary trades, "
        f"{len(bear_by_idx)} bear rows, {len(bull_by_idx)} bull rows")

    ribbon_lookup = efr.build_ribbon_lookup(spy_raw)
    rows = build_rows_pop_a(r.trades, bear_by_idx, bull_by_idx, spy_rth)
    for rid, blk in rows.items():
        log(f"  row {rid}: binary={len(blk['binary'])} candidates={len(blk['candidates'])} rung={blk['rung']}")

    results: dict[str, dict] = {}
    cell_trades: dict[str, list] = {}
    t1 = _time.time()
    for rid in ROW_ORDER:
        blk = rows[rid]
        for cid in COL_ORDER:
            col_fn = EXIT_COLUMNS[cid]
            shape = col_fn({"entry_premium": 0.0}, [])  # static cols ignore args; ATR handled per-position below
            if cid == "ATR_STOP":
                lane = walk_lane_dynamic_shape(blk["rung"], blk["candidates"], blk["binary"],
                                               spy_rth, ribbon_lookup, col_fn)
            else:
                lane = sl.walk_lane(blk["rung"], blk["candidates"], blk["binary"], spy_rth,
                                    ribbon_lookup, shape)
            key = f"{rid}__{cid}"
            cell_trades[key] = lane["trades"]
            results[key] = battery(lane["trades"])
            results[key]["n_excluded"] = len(lane["excluded"])
            results[key]["suppressed_binary"] = lane["suppressed_binary"]
    log(f"  {len(ROW_ORDER)}x{len(COL_ORDER)}={len(ROW_ORDER)*len(COL_ORDER)} cells walked in {_time.time()-t1:.1f}s")
    return {"cells": results, "trades": cell_trades, "n_control_binary": len(r.trades),
            "n_bear_rows": len(bear_by_idx), "n_bull_rows": len(bull_by_idx),
            "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                        "n_rth_days": int(spy_rth["timestamp_et"].dt.date.nunique())},
            "spy_rth": spy_rth, "ribbon_lookup": ribbon_lookup}


def walk_lane_dynamic_shape(rung, candidates, binary_trades, spy_rth, ribbon_lookup, shape_fn) -> dict:
    """Twin of sl.walk_lane, but calls shape_fn(position, opt_df) per position instead of
    threading one static exit_shape -- needed for ATR_STOP's per-position dynamic stop.
    Duplicated (not monkeypatched) deliberately: sl.walk_lane is validated/tested code from a
    prior fire and this file does not modify it, per file-ownership discipline."""
    import elite_bear_level_reject_gate_ab as eb
    events = [("binary", efr.naive_dt(t.entry_time_et), t) for t in binary_trades]
    if rung is not None:
        for c in candidates:
            if c["adjusted"] >= rung:
                events.append(("extra", efr.naive_dt(c["timestamp_et"]) + dt.timedelta(minutes=5), c))
    events.sort(key=lambda e: e[1])

    trades, excluded = [], []
    suppressed_binary = 0
    flat_until: Optional[dt.datetime] = None

    for kind, decision_ts, payload in events:
        if flat_until is not None and decision_ts <= flat_until:
            if kind == "binary":
                suppressed_binary += 1
            continue
        if kind == "binary":
            t = payload
            edate = eb.entry_date(t)
            symbol = option_symbol(edate, int(t.strike), t.side)
            opt_df = sl.cached_contract_bars(symbol)
            if opt_df is None:
                excluded.append({"kind": "binary", "date": edate.isoformat(), "reason": "no_opra_cache"})
                continue
            day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == edate].reset_index(drop=True)
            if day_spy.empty:
                excluded.append({"kind": "binary", "date": edate.isoformat(), "reason": "no_spy_day"})
                continue
            entry_time = efr.naive_dt(t.entry_time_et)
            rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
            bars_from_entry = _opt_bars_from(opt_df, entry_time)
            # opt_df/entry_time are passed so a shape_fn can derive its parameters from
            # PRE-entry bars. Existing columns ignore these keys; behaviour is unchanged.
            shape = shape_fn({"entry_premium": float(t.entry_premium), "opt_df": opt_df,
                              "entry_time_et": entry_time}, bars_from_entry)
            res = walk_exit_manager(symbol=symbol, side=t.side, entry_time_et=entry_time,
                                    entry_premium=float(t.entry_premium), qty=int(t.qty),
                                    exit_shape=shape, structure_stop_enabled=(shape.get("stop_mode") == "structure"),
                                    trigger_level=(float(t.rejection_level) if t.rejection_level else None),
                                    strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
                                    opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy)
            exit_ts = res.exit_time_et if res.exit_time_et is not None else entry_time
            flat_until = exit_ts
            trades.append({"kind": "binary", "date": edate.isoformat(), "entry_time_et": entry_time.isoformat(),
                           "side": t.side, "symbol": symbol, "qty": int(t.qty),
                           "entry_premium": round(float(t.entry_premium), 4), "dollar_pnl": res.dollar_pnl,
                           "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
                           "reached_tp1": any(leg.stage == "tp1" for leg in res.legs)})
        else:
            c = payload
            rr = sl.resolve_extra_entry(spy_rth, c)
            if not rr.get("ok"):
                excluded.append({"kind": "extra", "date": c["date"], "reason": rr.get("reason")})
                continue
            day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == pd.Timestamp(c["timestamp_et"]).date()].reset_index(drop=True)
            rtd = efr.ribbon_tick_df_for(rr["opt_df"], ribbon_lookup)
            bars_from_entry = _opt_bars_from(rr["opt_df"], rr["entry_time_et"])
            shape = shape_fn({"entry_premium": rr["entry_premium"], "opt_df": rr["opt_df"],
                              "entry_time_et": rr["entry_time_et"]}, bars_from_entry)
            res = walk_exit_manager(symbol=rr["symbol"], side=c["side"], entry_time_et=rr["entry_time_et"],
                                    entry_premium=rr["entry_premium"], qty=MIN_CONTRACTS_STUDY, exit_shape=shape,
                                    structure_stop_enabled=(shape.get("stop_mode") == "structure"),
                                    trigger_level=float(c["level"]), strategy="ribbon_ride",
                                    time_stop_et=efr.TIME_STOP_ET, opt_df=rr["opt_df"], ribbon_tick_df=rtd,
                                    five_min_spy_df=day_spy)
            exit_ts = res.exit_time_et if res.exit_time_et is not None else rr["entry_time_et"]
            flat_until = exit_ts
            trades.append({"kind": "extra", "date": c["date"], "entry_time_et": rr["entry_time_et"].isoformat(),
                           "side": c["side"], "symbol": rr["symbol"], "qty": MIN_CONTRACTS_STUDY,
                           "entry_premium": round(rr["entry_premium"], 4), "dollar_pnl": res.dollar_pnl,
                           "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
                           "reached_tp1": any(leg.stage == "tp1" for leg in res.legs)})
    return {"trades": trades, "excluded": excluded, "suppressed_binary": suppressed_binary}


def _opt_bars_from(opt_df: pd.DataFrame, entry_time_et) -> list[dict]:
    ts = opt_df["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    mask = ts >= pd.Timestamp(entry_time_et)
    sub = opt_df.loc[mask.values]
    return [{"open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]}
            for _, r in sub.iterrows()]


# =================================================================== POPULATION B (real fills)

def load_ledger_events() -> list[dict]:
    d = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return d["events"], d["_meta"]


def walk_event(e: dict, shape_fn: Callable, spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> Optional[dict]:
    symbol = e["symbol"]
    opt_df = load_contract_bars(symbol)
    if opt_df is None or opt_df.empty:
        return None
    entry_time = dt.datetime.fromisoformat(e["ts_et"])
    day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == entry_time.date()].reset_index(drop=True)
    if day_spy.empty:
        return None
    rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
    bars_from_entry = _opt_bars_from(opt_df, entry_time)
    entry_premium = float(e["price"])
    shape = shape_fn({"entry_premium": entry_premium}, bars_from_entry)
    trigger_level = e.get("trigger_level")
    res = walk_exit_manager(symbol=symbol, side=e["opt_side"], entry_time_et=entry_time,
                            entry_premium=entry_premium, qty=int(e["qty"]), exit_shape=shape,
                            structure_stop_enabled=(shape.get("stop_mode") == "structure"),
                            trigger_level=(float(trigger_level) if trigger_level is not None else None),
                            strategy=str(e.get("setup") or "ribbon_ride"), time_stop_et=efr.TIME_STOP_ET,
                            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
                            opt_df_resolution="5min", allow_5min=True)
    exit_ts = res.exit_time_et if res.exit_time_et is not None else entry_time
    return {"date": e["date_et"], "entry_time_et": entry_time.isoformat(), "side": e["opt_side"],
            "symbol": symbol, "qty": int(e["qty"]), "entry_premium": round(entry_premium, 4),
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
            "reached_tp1": any(leg.stage == "tp1" for leg in res.legs), "exit_ts": exit_ts}


def walk_events_sequential(events: list[dict], shape_fn: Callable, spy_rth, ribbon_lookup) -> dict:
    """Sequential NOT_FLAT walk over REAL fill events, mirroring sl.walk_lane's discipline --
    these are broker-truth entries, but the EXIT is re-derived per column, so suppression from
    a wider stop must be re-applied here too (a later real fill inside a still-open re-walked
    position's window is suppressed for THIS cell, exactly like population A)."""
    ordered = sorted(events, key=lambda e: e["ts_et"])
    trades, excluded = [], []
    suppressed = 0
    flat_until: Optional[dt.datetime] = None
    for e in ordered:
        decision_ts = dt.datetime.fromisoformat(e["ts_et"])
        if flat_until is not None and decision_ts <= flat_until:
            suppressed += 1
            continue
        t = walk_event(e, shape_fn, spy_rth, ribbon_lookup)
        if t is None:
            excluded.append({"date": e["date_et"], "symbol": e["symbol"], "reason": "no_opra_cache_or_no_spy_day"})
            continue
        flat_until = t.pop("exit_ts")
        trades.append(t)
    return {"trades": trades, "excluded": excluded, "suppressed_binary": suppressed}


def build_rows_pop_b(events: list[dict]) -> dict:
    struct8 = [e for e in events if e.get("s5_bucket") in ("EVENT<=8bars",) or
              (e.get("s5_kind") is not None and e.get("s5_bars_ago") is not None and e["s5_bars_ago"] <= 8)]
    vd1 = [e for e in events if e.get("d_last5_dir") is not None
          and e["d_last5_dir"] == ("up" if e["opt_side"] == "C" else "down")]
    max3 = apply_max3_events(events)
    return {"CONTROL": events, "STRUCT8": struct8, "VD1": vd1, "MAX3": max3}


def run_population_b(spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> dict:
    events, meta = load_ledger_events()
    log(f"population B: {len(events)} real engine-fill events, {meta['population']['n_days']} trading days "
        f"({meta['population']['days'][0]}..{meta['population']['days'][-1]})")
    rows_applicable = ["CONTROL", "STRUCT8", "VD1", "MAX3"]   # LADDER*/ZONE are N/A (prereg)
    rows = build_rows_pop_b(events)
    for rid in rows_applicable:
        log(f"  row {rid}: n={len(rows[rid])}")

    results: dict[str, dict] = {}
    cell_trades: dict[str, list] = {}
    t0 = _time.time()
    for rid in rows_applicable:
        row_events = rows[rid]
        for cid in COL_ORDER:
            col_fn = EXIT_COLUMNS[cid]
            lane = walk_events_sequential(row_events, col_fn, spy_rth, ribbon_lookup)
            key = f"{rid}__{cid}"
            cell_trades[key] = lane["trades"]
            results[key] = battery(lane["trades"])
            results[key]["n_excluded"] = len(lane["excluded"])
            results[key]["suppressed_binary"] = lane["suppressed_binary"]
    log(f"  {len(rows_applicable)}x{len(COL_ORDER)}={len(rows_applicable)*len(COL_ORDER)} cells walked "
        f"in {_time.time()-t0:.1f}s")
    return {"cells": results, "trades": cell_trades, "rows_applicable": rows_applicable,
            "n_events": len(events), "n_days": meta["population"]["n_days"],
            "date_span": f"{meta['population']['days'][0]}..{meta['population']['days'][-1]}"}


# =================================================================== interaction + BH

def interaction_effects(cells: dict, rows: list[str], cols: list[str]) -> dict:
    out = {}
    ctl_ctl = cells.get("CONTROL__CONTROL", {}).get("expectancy")
    if ctl_ctl is None:
        return out
    for rid in rows:
        if rid == "CONTROL":
            continue
        row_ctl = cells.get(f"{rid}__CONTROL", {}).get("expectancy")
        for cid in cols:
            if cid == "CONTROL":
                continue
            ctl_col = cells.get(f"CONTROL__{cid}", {}).get("expectancy")
            actual = cells.get(f"{rid}__{cid}", {}).get("expectancy")
            if row_ctl is None or ctl_col is None or actual is None:
                continue
            predicted = row_ctl + ctl_col - ctl_ctl
            out[f"{rid}__{cid}"] = {"actual": actual, "predicted_additive": round(predicted, 2),
                                    "interaction": round(actual - predicted, 2)}
    return out


def bh_correct(cells: dict) -> dict:
    pvals = {k: v.get("bootstrap_p_mean_gt0") for k, v in cells.items() if v.get("n", 0) >= 5}
    passed = sl.benjamini_hochberg(pvals, q=0.10)
    return passed


def bh_effective_threshold(cells: dict, q: float = 0.10) -> dict:
    """The ACTUAL corrected p-value cutoff BH applied (not just the nominal q), per this
    repo's own benjamini_hochberg mechanics: rank ascending, find the largest i with
    p_i <= q*i/m, effective threshold = p_i at that rank (0 cells survive -> threshold=None)."""
    pvals = {k: v.get("bootstrap_p_mean_gt0") for k, v in cells.items() if v.get("n", 0) >= 5}
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda kv: kv[1])
    m = len(items)
    max_i, thresh = 0, None
    for i, (_k, p) in enumerate(items, start=1):
        if p <= q * i / m:
            max_i, thresh = i, p
    return {"q": q, "m_tested": m, "n_survive": max_i, "effective_p_threshold": thresh,
            "nominal_q": q}


# =================================================================== main

def main() -> int:
    t_start = _time.time()
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"prereg loaded: {PREREG_PATH.name}")

    pop_a = run_population_a()
    pop_b = run_population_b(pop_a["spy_rth"], pop_a["ribbon_lookup"])

    inter_a = interaction_effects(pop_a["cells"], ROW_ORDER, COL_ORDER)
    inter_b = interaction_effects(pop_b["cells"], pop_b["rows_applicable"], COL_ORDER)
    bh_a = bh_correct(pop_a["cells"])
    bh_b = bh_correct(pop_b["cells"])
    bh_thresh_a = bh_effective_threshold(pop_a["cells"])
    bh_thresh_b = bh_effective_threshold(pop_b["cells"])
    log(f"BH q=0.10: pop A {bh_thresh_a['n_survive']}/{bh_thresh_a['m_tested']} survive "
        f"(eff. p<= {bh_thresh_a['effective_p_threshold']}); pop B {bh_thresh_b['n_survive']}/"
        f"{bh_thresh_b['m_tested']} survive (eff. p<= {bh_thresh_b['effective_p_threshold']})")

    out = {
        "_doc": __doc__,
        "prereg_path": str(PREREG_PATH.relative_to(ROOT)),
        "generated_at_et": dt.datetime.now().isoformat(),
        "row_order": ROW_ORDER, "col_order": COL_ORDER,
        "population_a": {"window": pop_a["window"], "n_control_binary": pop_a["n_control_binary"],
                          "n_bear_rows": pop_a["n_bear_rows"], "n_bull_rows": pop_a["n_bull_rows"],
                          "cells": pop_a["cells"], "interaction": inter_a, "bh_pass_q010": bh_a,
                          "bh_effective_threshold": bh_thresh_a},
        "population_b": {"n_events": pop_b["n_events"], "n_days": pop_b["n_days"],
                          "date_span": pop_b["date_span"], "rows_applicable": pop_b["rows_applicable"],
                          "cells": pop_b["cells"], "interaction": inter_b, "bh_pass_q010": bh_b,
                          "bh_effective_threshold": bh_thresh_b},
        "runtime_seconds": round(_time.time() - t_start, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON} ({_time.time()-t_start:.1f}s total)")

    # trades detail written separately (large) for audit trail, not embedded in the main JSON
    trades_path = OUT_DIR / "ENTRY-EXIT-MATRIX-2026-08-09-trades.json"
    trades_path.write_text(json.dumps({"population_a": pop_a["trades"], "population_b": pop_b["trades"]},
                                      indent=0, default=str), encoding="utf-8")
    log(f"wrote {trades_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
