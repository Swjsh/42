"""tp1_reachability_2026_08_06.py -- LANE 2: TP1 REACHABILITY, the full grid.

Runs EXACTLY the cells and gates frozen in
`analysis/recommendations/prereg-tp1-reachability-2026-08-06.json` (commit 24c4832d,
committed BEFORE this file existed -- verify with
`git merge-base --is-ancestor 24c4832d <runner commit>`).

GRID: tp1_premium_pct {0.30,0.40,0.50,0.75,1.0} x tp1_qty_fraction {0.5,0.667,0.8}
  - RIBBON PRIMARY: patch applied to ribbon_ride only (15 cells; R_tp100_f667 == live
    registry shape == the null cell, excluded from the BH tested family).
  - VWAP EXPLORATORY: patch applied to vwap_continuation only, WEEK-ONLY, n-small,
    ineligible to ship regardless of gates (frozen in prereg).

TWO POPULATIONS:
  A  391-day pinned replay (engine-fullhist-replay-2026-07-23.json, n=191, entries FROZEN).
  B  the real broker book for the FULL 4-session week 2026-08-03..06, all 5 arms,
     sequential per arm-day. 08-04..06 orders reused verbatim from the catcap-validated
     _week_orders_2026_08_06.json; 08-03 from _week_orders_2026_08_03.json (pulled this
     session, reconciled to the broker-verified +$534 Monday).

Exits are re-derived ONLY through backtest/lib/exit_manager_walk.walk_exit_manager, which
drives the REAL production core automation/state/fleet/exit_manager.plan_exit_actions.
NEVER simulator_real.simulate_trade_real (2026-07-09 SIM-EXIT-SHAPE-PARITY scar).

MECHANICAL DISTINCTION (required by the lane, frozen in prereg): a REACHABLE TP1 banks a
partial and THEN arms the post-TP1 lock (exit_manager.py:483-496 -> :506-516, validated
live machinery). Every cell keeps profit_lock_arm_scope='post_tp1'. This is NOT the
five-times-dead pre-TP1 arm_scope='full' cell (exit_manager.py:389-395), which arms the
trail on the full position before any profit banks.

ANALYSIS ONLY: writes only to analysis/. No trading-path file is touched.

Run: backtest/.venv/Scripts/python.exe backtest/tools/tp1_reachability_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402
from _week_positions_2026_08_06 import build_positions  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-tp1-reachability-2026-08-06.json"
PREREG_COMMIT = "24c4832d"
SOURCE_REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
SPY_HIST = BACKTEST / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
SPY_WEEK = BACKTEST / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
ORDERS_MON = BACKTEST / "data" / "_week_orders_2026_08_03.json"
ORDERS_TUE_THU = BACKTEST / "data" / "_week_orders_2026_08_06.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "TP1-REACHABILITY-2026-08-06.json"
SCORECARD = REPO / "analysis" / "recommendations" / "tp1-reachability-2026-08-06.json"

TIME_STOP_A = dt.time(15, 40)   # source population's own convention
TIME_STOP_B = em.TIME_STOP_ET   # 15:50, production default for the live fleet

ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
WEEK_DATES = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
MONDAY_HEADER_PNL = 534.0

# verbatim from automation/state/fleet/strategies.py (same block lever_catcap used)
REGISTRY_SHAPES = {
    "vwap_continuation": dict(
        premium_stop_pct=-0.06, tp1_premium_pct=0.40, tp1_qty_fraction=0.8,
        profit_lock_mode="fixed", runner_target_pct=2.5, trail_pct=0.125,
        profit_lock_arm_pct=0.05, stop_mode="premium", catastrophe_stop_pct=None,
        profit_lock_arm_scope="post_tp1"),
    "ribbon_ride": dict(
        premium_stop_pct=-0.20, tp1_premium_pct=1.0, tp1_qty_fraction=0.667,
        profit_lock_mode="trailing", runner_target_pct=99.0, trail_pct=0.15,
        profit_lock_arm_pct=0.05, stop_mode="structure", catastrophe_stop_pct=-0.50,
        profit_lock_arm_scope="post_tp1"),
}
# verbatim from automation/state/fleet/accounts.json params_patch.exit_patch
ARM_EXIT_PATCH = {
    "safe-2": {}, "bold-2": {},
    "safe-3": {"stop_mode": "structure", "profit_lock_mode": "trailing"},
    "risky-1": {"tp1_premium_pct": 0.5, "stop_mode": "structure"},
    "risky-3": {"stop_mode": "structure", "profit_lock_mode": "trailing", "trail_pct": 0.20},
}

TP1_LEVELS = (0.30, 0.40, 0.50, 0.75, 1.0)
FRACTIONS = (0.5, 0.667, 0.8)


def _fid(f: float) -> str:
    return {0.5: "50", 0.667: "667", 0.8: "80"}[f]


CELLS: list[dict] = [
    {"id": "CONTROL", "target": None, "patch": {}},
    {"id": "CONTROL_WALK", "target": None, "patch": {}},
]
for tp in TP1_LEVELS:
    for fr in FRACTIONS:
        CELLS.append({"id": f"R_tp{int(round(tp*100))}_f{_fid(fr)}", "target": "ribbon_ride",
                      "patch": {"tp1_premium_pct": tp, "tp1_qty_fraction": fr}})
for tp in TP1_LEVELS:
    for fr in FRACTIONS:
        CELLS.append({"id": f"W_tp{int(round(tp*100))}_f{_fid(fr)}", "target": "vwap_continuation",
                      "patch": {"tp1_premium_pct": tp, "tp1_qty_fraction": fr}})

NULL_CELLS = {"R_tp100_f667", "W_tp40_f80"}  # == live registry shapes; excluded from BH family


def log(m: str) -> None:
    print(f"[tp1-reach] {m}", flush=True)


def shape_for(strategy: str, arm: Optional[str], cell: dict) -> dict:
    """registry -> arm exit_patch -> CELL patch OUTERMOST, applied ONLY to the cell's target
    strategy (per-strategy isolation, frozen in prereg). Same layering as lever_catcap."""
    s = dict(REGISTRY_SHAPES[strategy])
    if arm:
        s.update(ARM_EXIT_PATCH.get(arm, {}))
    if cell["target"] == strategy and cell["patch"]:
        s.update(cell["patch"])
    return s


def build_ribbon_lookup(spy_df: pd.DataFrame) -> pd.DataFrame:
    rth = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
           & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    spy_rth = spy_df.loc[rth].reset_index(drop=True)
    rib = compute_ribbon(spy_rth["close"])
    out = spy_rth[["timestamp_et"]].copy()
    out["stack"] = rib["stack"].values
    return out.sort_values("timestamp_et").reset_index(drop=True)


def ribbon_tick_df_for(opt_df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    left = opt_df[["timestamp_et"]].copy()
    if getattr(left["timestamp_et"].dt, "tz", None) is not None:
        left["timestamp_et"] = left["timestamp_et"].dt.tz_localize(None)
    right = lookup.copy()
    if getattr(right["timestamp_et"].dt, "tz", None) is not None:
        right["timestamp_et"] = right["timestamp_et"].dt.tz_localize(None)
    merged = pd.merge_asof(left.sort_values("timestamp_et", kind="stable"),
                           right.sort_values("timestamp_et", kind="stable"),
                           on="timestamp_et", direction="backward")
    assert len(merged) == len(opt_df), "ribbon merge_asof row count drifted"
    return merged.reset_index(drop=True)[["stack"]]


# ---------------- stats (ported VERBATIM from bull_gate_f5class_requal_2026_08_01.py, itself
# ported from shelf_hold_reclaim_study.py, so p-values/BH remain directly comparable) --------
def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    tstat = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


# ============================ POPULATION A ================================================
_POPA_BARS: dict[str, tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]] = {}


def popa_bars(sym: str, lookup: pd.DataFrame):
    """Memoized (opt_df, ribbon_tick_df) per symbol -- identical across cells since entries
    are frozen and the ribbon lookup is population-fixed."""
    if sym not in _POPA_BARS:
        df = load_contract_bars(sym)
        if df is None or df.empty:
            _POPA_BARS[sym] = (None, None)
        else:
            _POPA_BARS[sym] = (df, ribbon_tick_df_for(df, lookup))
    return _POPA_BARS[sym]


def load_population_a() -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    src = json.loads(SOURCE_REPLAY.read_text(encoding="utf-8"))
    trades = src["trades"]
    spy = pd.read_csv(SPY_HIST)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    return trades, spy, build_ribbon_lookup(spy)


def walk_population_a(trades: list[dict], spy: pd.DataFrame, lookup: pd.DataFrame,
                      cell: dict) -> Optional[list[dict]]:
    if cell["target"] == "vwap_continuation":
        return None  # popA is ribbon-family only; vwap cells are week-only (frozen)
    rows: list[dict] = []
    for t in trades:
        sym = t["symbol"]
        entry_ts = pd.to_datetime(t["entry_time_et"])
        if getattr(entry_ts, "tzinfo", None) is not None:
            entry_ts = entry_ts.tz_localize(None)
        entry_ts = entry_ts.to_pydatetime()
        day = entry_ts.date()
        opt_df, rtd = popa_bars(sym, lookup)
        if opt_df is None:
            continue
        spy_day = spy[spy["timestamp_et"].dt.date == day].reset_index(drop=True)
        if spy_day.empty:
            continue
        shape = shape_for("ribbon_ride", None, cell)
        res = walk_exit_manager(
            symbol=sym, side=t["side"], entry_time_et=entry_ts,
            entry_premium=float(t["entry_premium"]), qty=int(t["qty"]),
            exit_shape=shape, structure_stop_enabled=True,
            trigger_level=t.get("trigger_level"), strategy="ribbon_ride",
            time_stop_et=TIME_STOP_A, opt_df=opt_df, ribbon_tick_df=rtd,
            five_min_spy_df=spy_day)
        tp1_fired = any(l.stage == "tp1" and l.kind == "SELL_PARTIAL" for l in res.legs)
        rows.append({"symbol": sym, "date": str(day), "side": t["side"], "qty": int(t["qty"]),
                     "entry_premium": float(t["entry_premium"]),
                     "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                     "exit_time_et": (res.exit_time_et.isoformat()
                                      if res.exit_time_et else None),
                     "tp1_fired": tp1_fired, "src_pnl": float(t["dollar_pnl"])})
    return rows


def popa_reachability(trades: list[dict], ctl_rows: list[dict]) -> dict:
    """The reachability BRIDGE (frozen in prereg): unconditional post-entry session max
    (bar HIGH, catcap's convention) vs in-trade max under the CONTROL walk (bar OPEN
    point-samples -- the walk's own best_premium analog -- truncated at the CONTROL exit)."""
    ctl_exit = {(r["symbol"], r["date"]): r["exit_time_et"] for r in ctl_rows}
    uncond, intrade = [], []
    for t in trades:
        sym, ep = t["symbol"], float(t["entry_premium"])
        if ep <= 0:
            continue
        df, _ = _POPA_BARS.get(sym, (None, None))
        if df is None:
            df = load_contract_bars(sym)
        if df is None or df.empty:
            continue
        ets = pd.to_datetime(t["entry_time_et"])
        if getattr(ets, "tzinfo", None) is not None:
            ets = ets.tz_localize(None)
        d2 = df.copy()
        d2["timestamp_et"] = pd.to_datetime(d2["timestamp_et"])
        if getattr(d2["timestamp_et"].dt, "tz", None) is not None:
            d2["timestamp_et"] = d2["timestamp_et"].dt.tz_localize(None)
        after = d2[d2["timestamp_et"] > ets]
        if after.empty:
            continue
        uncond.append((float(after["high"].max()) - ep) / ep)
        key = (sym, str(ets.date()))
        xt = ctl_exit.get(key)
        if xt:
            inwin = after[after["timestamp_et"] <= pd.to_datetime(xt)]
            if not inwin.empty:
                intrade.append((float(inwin["open"].max()) - ep) / ep)

    def table(mfes: list[float]) -> dict:
        r = {f"+{int(t*100)}%": round(sum(1 for m in mfes if m >= t) / max(1, len(mfes)), 4)
             for t in (0.30, 0.40, 0.50, 0.75, 1.00)}
        return {"n": len(mfes),
                "median_mfe": round(statistics.median(mfes), 4) if mfes else None,
                "reach_fraction": r}
    return {
        "unconditional_session_max_bar_high": {
            **table(uncond),
            "_measure": "max bar HIGH after entry to session end, ignoring exits -- UPPER "
                        "BOUND (catcap section-4 convention, reproduced)"},
        "in_trade_under_control_walk_bar_open": {
            **table(intrade),
            "_measure": "max bar OPEN point-sample from entry to the CONTROL walk's own exit "
                        "-- the walk-convention analog of the live ledger's best_premium "
                        "measure (EOD-2026-08-05-REENTRY-SIZING section 1a: 14% of 124 live "
                        "ribbon entries reached +100%, median +16.3%)"},
    }


# ============================ POPULATION B ================================================
def attribute_week(pos: dict) -> dict:
    """Ported from lever_catcap_2026_08_06.attribute_week (same convention, cited): the fleet
    arms trade the SAME shared signal, so (date, strike, side) determines the setup; core-lane
    safe-2/bold-2 rows are attributed from the fleet arms' identical-signal rows."""
    sig: dict[tuple, dict] = {}
    for arm in ARMS:
        f = FLEET_DIR / arm / "decisions.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "ENTER" not in str(d.get("action", "")):
                continue
            ts = str(d.get("ts_et", ""))
            date_iso, strike, side = ts[:10], d.get("strike"), d.get("side")
            if not date_iso or strike is None or side is None:
                continue
            setup = str(d.get("setup_name") or "")
            strat = "vwap_continuation" if "VWAP" in setup.upper() else "ribbon_ride"
            key = (date_iso, int(strike), str(side))
            cand = {"strategy": strat, "trigger_level": d.get("trigger_level"),
                    "setup_name": setup, "ts": ts}
            prev = sig.get(key)
            if prev is None or (prev.get("trigger_level") is None
                                and cand.get("trigger_level") is not None):
                sig[key] = cand
    for date_iso, arms in pos.items():
        for arm, plist in arms.items():
            for p in plist:
                strike = int(p["symbol"][-8:]) // 1000
                hit = sig.get((date_iso, strike, p["side"]))
                p["strategy"] = (hit or {}).get("strategy")
                p["trigger_level"] = (hit or {}).get("trigger_level")
                p["setup_name"] = (hit or {}).get("setup_name")
    return pos


def _load_legacy_schema_cache(symbol: str, date_iso: str) -> Optional[pd.DataFrame]:
    """Verbatim from lever_catcap_2026_08_06.py (same defect, same fix): pre-existing
    highres CSVs carry UTC `timestamp`, not ET-naive `timestamp_et`."""
    p = BACKTEST / "data" / "highres" / f"{symbol}_1m_{date_iso}.csv"
    if not p.exists():
        return None
    raw = pd.read_csv(p)
    if "timestamp" not in raw.columns:
        return None
    ts_utc = pd.to_datetime(raw["timestamp"], utc=True)
    ts_et = ts_utc.dt.tz_convert(dt.timezone(dt.timedelta(hours=-4))).dt.tz_localize(None)
    out = pd.DataFrame({"timestamp_et": ts_et, "open": raw["open"], "high": raw["high"],
                        "low": raw["low"], "close": raw["close"], "volume": raw["volume"]})
    return out.sort_values("timestamp_et").reset_index(drop=True)


def load_week_bars(pos: dict) -> dict:
    bars: dict[tuple, pd.DataFrame] = {}
    for date_iso, arms in pos.items():
        syms = {p["symbol"] for plist in arms.values() for p in plist}
        for s in sorted(syms):
            try:
                df, src = fetch_1min_cached(s, date_iso)
            except Exception as e:  # noqa: BLE001
                df = _load_legacy_schema_cache(s, date_iso)
                src = ("legacy_schema_cache_reparsed" if df is not None
                       else f"fetch_failed:{type(e).__name__}")
            if df is not None and not df.empty:
                bars[(date_iso, s)] = df
                log(f"  bars {date_iso} {s}: {len(df)} rows ({src})")
            else:
                log(f"  bars {date_iso} {s}: MISSING ({src})")
    return bars


_WEEK_RTD: dict[tuple, pd.DataFrame] = {}


def week_rtd(date_iso: str, sym: str, opt_df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    key = (date_iso, sym)
    if key not in _WEEK_RTD:
        _WEEK_RTD[key] = ribbon_tick_df_for(opt_df, lookup)
    return _WEEK_RTD[key]


def walk_week(pos: dict, bars: dict, spy_by_day: dict, lookup: pd.DataFrame,
              cell: dict, is_control: bool) -> list[dict]:
    """Sequential, one position at a time, per arm per day (catcap discipline verbatim)."""
    rows: list[dict] = []
    for date_iso in WEEK_DATES:
        spy_day = spy_by_day.get(date_iso)
        for arm in ARMS:
            plist = pos.get(date_iso, {}).get(arm, [])
            cf_flat: Optional[dt.datetime] = None
            for p in plist:
                h, mi, s = (int(x) for x in p["entry_et"].split(":"))
                y, mo, dd = (int(x) for x in date_iso.split("-"))
                entry_ts = dt.datetime(y, mo, dd, h, mi, s)
                base = {"date": date_iso, "arm": arm, "symbol": p["symbol"],
                        "entry_et": p["entry_et"], "strategy": p["strategy"],
                        "side": p["side"], "qty": p["qty"],
                        "entry_premium": p["premium"], "real_pnl": p["realized_pnl"]}
                if is_control:
                    rows.append({**base, "suppressed": False, "tp1_fired": None,
                                 "dollar_pnl": p["realized_pnl"],
                                 "exit_reason": "REAL_BROKER_FILL"})
                    continue
                if cf_flat is not None and entry_ts < cf_flat:
                    rows.append({**base, "suppressed": True, "tp1_fired": None,
                                 "dollar_pnl": 0.0,
                                 "exit_reason": f"suppressed (cf open until {cf_flat.time()})"})
                    continue
                opt_df = bars.get((date_iso, p["symbol"]))
                if opt_df is None or spy_day is None or not p.get("strategy"):
                    why = ("UNATTRIBUTED_HELD_AT_REAL" if not p.get("strategy")
                           else "NO_OPRA_HELD_AT_REAL")
                    rows.append({**base, "suppressed": False, "tp1_fired": None,
                                 "dollar_pnl": p["realized_pnl"], "exit_reason": why})
                    continue
                rtd = week_rtd(date_iso, p["symbol"], opt_df, lookup)
                shape = shape_for(p["strategy"], arm, cell)
                res = walk_exit_manager(
                    symbol=p["symbol"], side=p["side"], entry_time_et=entry_ts,
                    entry_premium=float(p["premium"]), qty=int(p["qty"]),
                    exit_shape=shape, structure_stop_enabled=True,
                    trigger_level=p["trigger_level"], strategy=p["strategy"],
                    time_stop_et=TIME_STOP_B, opt_df=opt_df, ribbon_tick_df=rtd,
                    five_min_spy_df=spy_day)
                cf_flat = res.exit_time_et
                tp1_fired = any(l.stage == "tp1" and l.kind == "SELL_PARTIAL"
                                for l in res.legs)
                rows.append({**base, "suppressed": False, "tp1_fired": tp1_fired,
                             "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason})
    return rows


# ================================== gate scoring ==========================================
SUBWINDOWS = [("2025H1", "2025-01-01", "2025-06-30"),
              ("2025H2", "2025-07-01", "2025-12-31"),
              ("2026Q1", "2026-01-01", "2026-03-31"),
              ("2026Q2p", "2026-04-01", "2026-07-22")]


def score_popa_cell(rows: list[dict], ctl: list[dict], runner_keys: set) -> dict:
    key = lambda r: (r["symbol"], r["date"])  # noqa: E731
    ctl_map = {key(r): r["dollar_pnl"] for r in ctl}
    deltas = {key(r): round(r["dollar_pnl"] - ctl_map.get(key(r), 0.0), 2) for r in rows}
    changed = {k: d for k, d in deltas.items() if abs(d) > 0.005}
    agg = round(sum(deltas.values()), 2)
    best_trade = max((d for d in changed.values() if d > 0), default=0.0)
    # day-level
    day_delta: dict[str, float] = {}
    for (sym, d), v in deltas.items():
        day_delta[d] = round(day_delta.get(d, 0.0) + v, 2)
    best_day = max((v for v in day_delta.values() if v > 0), default=0.0)
    runner_delta = round(sum(v for k, v in deltas.items() if k in runner_keys), 2)
    # sub-windows
    subw = []
    for name, lo, hi in SUBWINDOWS:
        in_w = {k: v for k, v in deltas.items() if lo <= k[1] <= hi}
        ch_w = [v for v in in_w.values() if abs(v) > 0.005]
        subw.append({"window": name, "delta": round(sum(in_w.values()), 2),
                     "n_changed": len(ch_w)})
    # frozen G4 rule, implemented literally: PASS = delta >= -$0.005 in >= 3 of the windows
    # containing >= 5 changed trades; fewer than 2 qualifying windows => FAIL. (With exactly
    # 2 qualifying windows the >=3 requirement is unreachable => FAIL, by construction.)
    qual = [w for w in subw if w["n_changed"] >= 5]
    n_ok = sum(1 for w in qual if w["delta"] >= -0.005)
    subw_pass = len(qual) >= 2 and n_ok >= 3
    # WF months
    months: dict[str, list[float]] = {}
    for (sym, d), v in changed.items():
        months.setdefault(d[:7], []).append(v)
    qual_months = {m: sum(v) for m, v in months.items() if len(v) >= 3}
    wf = (round(sum(1 for t in qual_months.values() if t >= 0) / len(qual_months), 3)
          if qual_months else None)
    wf_pass = (wf is not None and len(qual_months) >= 4 and wf >= 0.70)
    # OOS
    oos_delta = round(sum(v for k, v in deltas.items() if k[1] >= "2026-01-01"), 2)
    p_raw = one_sample_p(list(changed.values())) if changed else 1.0
    return {
        "aggregate_delta": agg, "n_changed": len(changed),
        "ex_best_trade": round(agg - best_trade, 2),
        "drop_best_day": round(agg - best_day, 2),
        "runner_cohort_delta": runner_delta,
        "sub_windows": subw, "sub_window_stable": bool(subw_pass),
        "wf_months_qualifying": len(qual_months), "wf_fraction": wf, "wf_pass": bool(wf_pass),
        "oos_2026_delta": oos_delta,
        "p_value_raw": round(p_raw, 6),
        "tp1_fire_rate": round(sum(1 for r in rows if r.get("tp1_fired")) / max(1, len(rows)), 4),
    }


def main() -> int:
    t0 = time.time()
    assert PREREG.exists(), "frozen prereg missing"
    log(f"prereg: {PREREG.name} (commit {PREREG_COMMIT})")

    # ---------- POPULATION A ----------
    log("POPULATION A: loading pinned 391-day replay ...")
    trades, spy_hist, lookup_hist = load_population_a()
    log(f"  n trades = {len(trades)}")

    a_by_cell: dict[str, Optional[list[dict]]] = {}
    for c in CELLS:
        a_by_cell[c["id"]] = walk_population_a(trades, spy_hist, lookup_hist, c)
        if a_by_cell[c["id"]] is not None:
            tot = sum(r["dollar_pnl"] for r in a_by_cell[c["id"]])
            log(f"  A {c['id']:14s} n={len(a_by_cell[c['id']]):3d} total=${tot:,.2f}")

    ctl_a = a_by_cell["CONTROL"]
    mism = [r for r in ctl_a if abs(r["dollar_pnl"] - r["src_pnl"]) > 0.005]
    log(f"  CONTROL reconciliation vs source replay: {len(mism)} mismatches "
        f"(MUST be 0; nonzero => scorecard VOID)")
    ctl_a_total = round(sum(r["dollar_pnl"] for r in ctl_a), 2)
    runner_keys = {(r["symbol"], r["date"]) for r in ctl_a
                   if r["dollar_pnl"] > 0 and "runner_stop" in str(r["exit_reason"])}
    runner_ctl = round(sum(r["dollar_pnl"] for r in ctl_a
                           if (r["symbol"], r["date"]) in runner_keys), 2)
    log(f"  runner anchor cohort: n={len(runner_keys)} ${runner_ctl:,.2f} "
        f"(catcap: 35 / $15,497.25)")

    reach = popa_reachability(trades, ctl_a)
    log(f"  reachability bridge: uncond={reach['unconditional_session_max_bar_high']['reach_fraction']}"
        f" | in-trade={reach['in_trade_under_control_walk_bar_open']['reach_fraction']}")

    # ---------- POPULATION B ----------
    log("POPULATION B: real broker book, FULL 4-session week 08-03..06 ...")
    orders = json.loads(ORDERS_MON.read_text(encoding="utf-8"))
    orders.update(json.loads(ORDERS_TUE_THU.read_text(encoding="utf-8")))
    pos = attribute_week(build_positions(orders))
    unattributed = [(d, a, p["symbol"]) for d, arms in pos.items()
                    for a, pl in arms.items() for p in pl if not p.get("strategy")]
    log("  positions: " + ", ".join(
        f"{d}={sum(len(v) for v in pos[d].values())}" for d in WEEK_DATES))
    log(f"  unattributed strategy: {len(unattributed)} {unattributed[:6]}")

    spy_week = pd.read_csv(SPY_WEEK)
    spy_week["timestamp_et"] = pd.to_datetime(spy_week["timestamp_et"])
    if getattr(spy_week["timestamp_et"].dt, "tz", None) is not None:
        spy_week["timestamp_et"] = spy_week["timestamp_et"].dt.tz_localize(None)
    lookup_week = build_ribbon_lookup(spy_week)
    spy_by_day = {d: spy_week[spy_week["timestamp_et"].dt.date
                              == dt.date.fromisoformat(d)].reset_index(drop=True)
                  for d in WEEK_DATES}
    for d in WEEK_DATES:
        log(f"  SPY 5m rows {d}: {0 if spy_by_day[d] is None else len(spy_by_day[d])}")
        assert spy_by_day[d] is not None and not spy_by_day[d].empty, f"SPY 5m missing {d}"

    bars = load_week_bars(pos)

    b_by_cell: dict[str, list[dict]] = {}
    for c in CELLS:
        b_by_cell[c["id"]] = walk_week(pos, bars, spy_by_day, lookup_week,
                                       c, c["id"] == "CONTROL")
    ctl_b = b_by_cell["CONTROL"]
    walk_b = b_by_cell["CONTROL_WALK"]
    day_ctl = {d: round(sum(r["dollar_pnl"] for r in ctl_b if r["date"] == d), 2)
               for d in WEEK_DATES}
    day_walk = {d: round(sum(r["dollar_pnl"] for r in walk_b if r["date"] == d), 2)
                for d in WEEK_DATES}
    replay_div = {d: round(day_walk[d] - day_ctl[d], 2) for d in WEEK_DATES}
    log(f"  CONTROL (real fills) day totals: {day_ctl}")
    log(f"  CONTROL_WALK  (harness) totals : {day_walk}")
    log(f"  replay divergence (walk-real)  : {replay_div}  <- NOT a knob effect")
    log(f"  Monday recon: CONTROL {day_ctl['2026-08-03']} vs header {MONDAY_HEADER_PNL} "
        f"(diff {round(day_ctl['2026-08-03'] - MONDAY_HEADER_PNL, 2)})")

    # ---------- score every cell ----------
    keyB = lambda r: (r["date"], r["arm"], r["symbol"], r["entry_et"])  # noqa: E731
    walk_map = {keyB(r): r["dollar_pnl"] for r in walk_b}
    results = []
    for c in CELLS:
        cid = c["id"]
        if cid == "CONTROL":
            continue
        B = b_by_cell[cid]
        day_cell = {d: round(sum(r["dollar_pnl"] for r in B if r["date"] == d), 2)
                    for d in WEEK_DATES}
        day_delta = {d: round(day_cell[d] - day_walk[d], 2) for d in WEEK_DATES}
        week_total_delta = round(sum(day_delta.values()), 2)
        strat_split = {}
        for strat in ("ribbon_ride", "vwap_continuation", None):
            dd = round(sum(r["dollar_pnl"] - walk_map.get(keyB(r), 0.0)
                           for r in B if r["strategy"] == strat and not r["suppressed"]), 2)
            strat_split[str(strat)] = dd
        week_deltas_per_pos = [round(r["dollar_pnl"] - walk_map.get(keyB(r), 0.0), 2)
                               for r in B if not r["suppressed"]]
        week_changed = [d for d in week_deltas_per_pos if abs(d) > 0.005]

        A = a_by_cell[cid]
        if A is not None:
            pa = score_popa_cell(A, ctl_a, runner_keys)
            p_raw = pa["p_value_raw"]
        else:
            pa = None
            p_raw = round(one_sample_p(week_changed), 6) if week_changed else 1.0

        gates = {
            "G1_popA_aggregate": (pa is not None and pa["aggregate_delta"] > 0.005),
            "G2_ex_best_trade": (pa is not None and pa["ex_best_trade"] > 0.005),
            "G3_runner_anchor": (pa is not None and pa["runner_cohort_delta"] >= -0.005),
            "G4_subwindow_stable": (pa is not None and pa["sub_window_stable"]),
            "G5_drop_best_day": (pa is not None and pa["drop_best_day"] > 0.005),
            "G6_week_tuesday_HARD": day_delta["2026-08-04"] >= -0.005,
            "G7_week_total": week_total_delta > 0.005,
            # G8 filled after BH pass below
        }
        bar = {
            "OOS_positive": (pa is not None and pa["oos_2026_delta"] > 0.005
                             and week_total_delta >= -0.005),
            "WF_ge_0.70": (pa is not None and pa["wf_pass"]),
            "sub_window_stable": gates["G4_subwindow_stable"],
            "anchor_no_regression": gates["G3_runner_anchor"],
        }
        results.append({
            "id": cid, "target": c["target"], "patch": c["patch"],
            "is_null_cell": cid in NULL_CELLS,
            "ship_eligible": (c["target"] == "ribbon_ride" and cid not in NULL_CELLS),
            "popA": pa,
            "p_value_raw": p_raw,
            "week_day_total": day_cell, "week_day_delta": day_delta,
            "week_total_delta": week_total_delta,
            "week_strategy_split": strat_split,
            "week_n_changed": len(week_changed),
            "week_suppressed": sum(1 for r in B if r["suppressed"]),
            "week_tp1_fire_rate": round(
                sum(1 for r in B if r.get("tp1_fired")) /
                max(1, sum(1 for r in B if r.get("tp1_fired") is not None)), 4),
            "gates": gates, "auto_ratify_bar": bar,
        })
        pa_s = (f"popA d=${pa['aggregate_delta']:>9,.2f} runner d=${pa['runner_cohort_delta']:>9,.2f}"
                if pa else "popA N/A (week-only)")
        log(f"  {cid:14s} {pa_s} | Mon ${day_delta['2026-08-03']:>7,.2f} "
            f"Tue ${day_delta['2026-08-04']:>8,.2f} Wed ${day_delta['2026-08-05']:>8,.2f} "
            f"Thu ${day_delta['2026-08-06']:>7,.2f}")

    # BH across the tested family (28 cells, null cells excluded -- frozen in prereg)
    tested = [r for r in results if r["id"] not in NULL_CELLS and r["id"] != "CONTROL_WALK"]
    sig = bh_fdr([r["p_value_raw"] for r in tested], q=0.10)
    for r, s in zip(tested, sig):
        r["gates"]["G8_bh_fdr"] = bool(s)
    for r in results:
        r["gates"].setdefault("G8_bh_fdr", None)
        g = r["gates"]
        r["clears_all_gates"] = (all(bool(v) for v in g.values())
                                 if r["id"] not in NULL_CELLS and r["id"] != "CONTROL_WALK"
                                 else None)
        r["clears_full_bar"] = (bool(r["clears_all_gates"])
                                and all(r["auto_ratify_bar"].values())
                                and r["ship_eligible"]) if r["clears_all_gates"] is not None else None
    n_bh = sum(1 for r in tested if r["gates"]["G8_bh_fdr"])
    log(f"BH-FDR q=0.10 across {len(tested)} tested cells: {n_bh} survivors")
    shippable = [r["id"] for r in results if r.get("clears_full_bar")]
    log(f"cells clearing the FULL auto-ratify bar: {shippable if shippable else 'NONE'}")

    out = {
        "_doc": "LANE 2 -- TP1 REACHABILITY full grid. Run per frozen prereg "
                "analysis/recommendations/prereg-tp1-reachability-2026-08-06.json "
                f"(commit {PREREG_COMMIT}).",
        "generated_at_et": dt.datetime.now().isoformat(),
        "runtime_seconds": round(time.time() - t0, 1),
        "prereg_commit": PREREG_COMMIT,
        "populations": {
            "A": {"source": str(SOURCE_REPLAY.relative_to(REPO)), "n": len(ctl_a),
                  "control_total": ctl_a_total,
                  "control_reconciliation_mismatches": len(mism),
                  "runner_cohort_n": len(runner_keys),
                  "runner_cohort_total": runner_ctl},
            "B": {"source": "real broker /v2/orders, 5 arms, FULL 4-session week 2026-08-03..06",
                  "n_positions": {d: sum(len(v) for v in pos[d].values()) for d in WEEK_DATES},
                  "control_day_totals_real_fills": day_ctl,
                  "control_walk_day_totals": day_walk,
                  "replay_divergence_walk_minus_real": replay_div,
                  "monday_recon_vs_header_534": round(day_ctl["2026-08-03"] - MONDAY_HEADER_PNL, 2),
                  "unattributed_strategy": unattributed,
                  "bars_missing": [f"{d}|{s}" for d, arms in pos.items()
                                   for a, pl in arms.items() for p in pl
                                   for s in [p["symbol"]] if (d, s) not in bars]},
        },
        "reachability_bridge": reach,
        "cells": results,
        "week_positions": {d: {a: pos[d][a] for a in ARMS if pos[d].get(a)} for d in WEEK_DATES},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")

    scorecard = {
        "rule_id": "tp1-reachability-2026-08-06",
        "_doc": "A/B scorecard, every cell disclosed. Frozen prereg commit "
                f"{PREREG_COMMIT}. Exits via walk_exit_manager ONLY.",
        "generated_at_et": dt.datetime.now().isoformat(),
        "void": len(mism) > 0,
        "populations_summary": out["populations"],
        "cells": [{k: r[k] for k in ("id", "target", "patch", "is_null_cell", "ship_eligible",
                                     "p_value_raw", "week_day_delta", "week_total_delta",
                                     "week_strategy_split", "gates", "auto_ratify_bar",
                                     "clears_all_gates", "clears_full_bar")}
                  | ({"popA_aggregate_delta": r["popA"]["aggregate_delta"],
                      "popA_runner_cohort_delta": r["popA"]["runner_cohort_delta"],
                      "popA_ex_best_trade": r["popA"]["ex_best_trade"],
                      "popA_drop_best_day": r["popA"]["drop_best_day"],
                      "popA_wf_fraction": r["popA"]["wf_fraction"],
                      "popA_oos_2026_delta": r["popA"]["oos_2026_delta"],
                      "popA_tp1_fire_rate": r["popA"]["tp1_fire_rate"],
                      "popA_sub_windows": r["popA"]["sub_windows"]}
                     if r["popA"] else {"popA": None})
                  for r in results],
        "bh_family_size": len(tested), "bh_q": 0.10, "bh_survivors": n_bh,
        "cells_clearing_full_bar": shippable,
        "verdict": ("SHIP_CANDIDATE" if shippable else "DO_NOT_ARM"),
        "reachability_bridge": reach,
    }
    SCORECARD.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    log(f"wrote {SCORECARD}  ({round(time.time()-t0,1)}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
