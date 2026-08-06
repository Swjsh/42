"""lever_catcap_2026_08_06.py -- LEVER 3: the catastrophe cap and the per-trade loss tail.

Runs EXACTLY the cells and gates frozen in
`analysis/recommendations/prereg-lever-catcap-2026-08-06.json`
(git commit 089beb50, committed BEFORE this file existed -- verify with
`git merge-base --is-ancestor 089beb50 HEAD`).

FOUR AXES, applied to the `ribbon_ride` shape only, layered OUTERMOST over each arm's
accounts.json exit_patch:
  A CATCAP    catastrophe_stop_pct        {-.20 -.25 -.30 -.35 -.40 [-.50 ctl] -.60 -.70}
  B GIVEBACK  arm_scope=full + trailing, trail_pct {.30 .40 .50 .60}   (pre-TP1 trail WIDTH)
  C BEFLOOR   pre_tp1_be_floor_arm_pct    {.15 .20 .25 .30 .40}
  D TP1       tp1_premium_pct             {.20 .25 .30 .40 [1.0 ctl] .50}

TWO POPULATIONS:
  A  391-day pinned replay (engine-fullhist-replay-2026-07-23.json, n=191, entries FROZEN).
  B  the real broker book for 2026-08-04 / 08-05 / 08-06, all 5 arms, sequential per arm-day.

Exits are re-derived ONLY through backtest/lib/exit_manager_walk.walk_exit_manager, which
drives the REAL production core automation/state/fleet/exit_manager.plan_exit_actions.
NEVER simulator_real.simulate_trade_real (the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar).

ANALYSIS ONLY: writes only to analysis/deep-research/. No trading-path file is touched.

Run: backtest/.venv/Scripts/python.exe backtest/tools/lever_catcap_2026_08_06.py
"""
from __future__ import annotations

import datetime as dt
import json
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

PREREG = REPO / "analysis" / "recommendations" / "prereg-lever-catcap-2026-08-06.json"
SOURCE_REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
SPY_HIST = BACKTEST / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
SPY_WEEK = BACKTEST / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVER-CATCAP-2026-08-06.json"
OUT_MD = REPO / "analysis" / "deep-research" / "LEVER-CATCAP-2026-08-06.md"

# Population A's own convention (SAFE_BASE time_stop_minutes_before_close=20). Using
# em.TIME_STOP_ET (15:50) here would silently re-walk every historical trade against a
# 10-minute-later force-close than the source population used.
TIME_STOP_A = dt.time(15, 40)
TIME_STOP_B = em.TIME_STOP_ET  # 15:50, the true production default for the live fleet

ANCHOR_RUNNER_N = 35
ANCHOR_RUNNER_PNL = 15774.05

ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
WEEK_DATES = ["2026-08-04", "2026-08-05", "2026-08-06"]

# verbatim from automation/state/fleet/strategies.py
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

# ---- CELLS (frozen in the prereg; any edit here without a new prereg is a protocol breach) --
CELLS: list[dict] = [
    # CONTROL = real broker fills / the source population verbatim. Never re-walked.
    {"id": "CONTROL", "axis": "-", "patch": {}},
    # CONTROL_WALK = the UNCHANGED shape pushed through the SAME harness. This is the cell
    # every other cell is differenced against on Population B, so the reported knob effect is
    # isolated from replay divergence (point-sampled 1-min bar OPENs vs a continuous NBBO
    # feed). Population A needs no such cell -- its CONTROL walk reconciles to the source
    # population with zero mismatches -- but it is carried there too as a null check.
    {"id": "CONTROL_WALK", "axis": "-", "patch": {}},
]
for w in (-0.20, -0.25, -0.30, -0.35, -0.40, -0.60, -0.70):
    CELLS.append({"id": f"A_cat{int(round(w*100))}", "axis": "A_CATCAP",
                  "patch": {"catastrophe_stop_pct": w}})
for t in (0.30, 0.40, 0.50, 0.60):
    CELLS.append({"id": f"B_give{int(round(t*100))}", "axis": "B_GIVEBACK",
                  "patch": {"profit_lock_arm_scope": "full", "profit_lock_mode": "trailing",
                            "trail_pct": t}})
for a in (0.15, 0.20, 0.25, 0.30, 0.40):
    CELLS.append({"id": f"C_be{int(round(a*100))}", "axis": "C_BEFLOOR",
                  "patch": {"pre_tp1_be_floor_arm_pct": a}})
for p in (0.20, 0.25, 0.30, 0.40, 0.50):
    CELLS.append({"id": f"D_tp1_{int(round(p*100))}", "axis": "D_TP1",
                  "patch": {"tp1_premium_pct": p}})


def log(m: str) -> None:
    print(f"[lever-catcap] {m}", flush=True)


def shape_for(strategy: str, arm: Optional[str], patch: dict) -> dict:
    """registry -> arm exit_patch -> CELL patch (outermost). The cell patch applies to
    ribbon_ride ONLY: vwap_continuation keeps its registry shape in every cell, so the axis
    is isolated to the family the lane targets."""
    s = dict(REGISTRY_SHAPES[strategy])
    if arm:
        s.update(ARM_EXIT_PATCH.get(arm, {}))
    if strategy == "ribbon_ride" and patch:
        s.update(patch)
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


# ============================ POPULATION A : 391-day pinned ================================
def load_population_a() -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    src = json.loads(SOURCE_REPLAY.read_text(encoding="utf-8"))
    trades = src["trades"]
    spy = pd.read_csv(SPY_HIST)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    return trades, spy, build_ribbon_lookup(spy)


def walk_population_a(trades: list[dict], spy: pd.DataFrame, lookup: pd.DataFrame,
                      patch: dict) -> list[dict]:
    rows: list[dict] = []
    for t in trades:
        sym = t["symbol"]
        entry_ts = pd.to_datetime(t["entry_time_et"])
        if getattr(entry_ts, "tzinfo", None) is not None:
            entry_ts = entry_ts.tz_localize(None)
        entry_ts = entry_ts.to_pydatetime()
        day = entry_ts.date()
        opt_df = load_contract_bars(sym)
        if opt_df is None or opt_df.empty:
            continue
        spy_day = spy[spy["timestamp_et"].dt.date == day].reset_index(drop=True)
        if spy_day.empty:
            continue
        rtd = ribbon_tick_df_for(opt_df, lookup)
        shape = shape_for("ribbon_ride", None, patch)
        res = walk_exit_manager(
            symbol=sym, side=t["side"], entry_time_et=entry_ts,
            entry_premium=float(t["entry_premium"]), qty=int(t["qty"]),
            exit_shape=shape, structure_stop_enabled=True,
            trigger_level=t.get("trigger_level"), strategy="ribbon_ride",
            time_stop_et=TIME_STOP_A, opt_df=opt_df, ribbon_tick_df=rtd,
            five_min_spy_df=spy_day)
        rows.append({"symbol": sym, "date": str(day), "side": t["side"],
                     "entry_premium": float(t["entry_premium"]), "qty": int(t["qty"]),
                     "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                     "stage": getattr(res, "exit_stage", None),
                     "src_pnl": float(t["dollar_pnl"])})
    return rows


# ============================ POPULATION B : the week book ================================
def attribute_week(pos: dict) -> dict:
    """Attach strategy + trigger_level. Source = the fleet arms' OWN decisions.jsonl ENTER
    rows (they all trade the SAME shared signal, so (date, strike, side) determines the
    setup); safe-2/bold-2 log through the CORE ledger, whose PLACED rows carry no
    setup_name/strike -- they are attributed from the fleet arms' identical-signal rows,
    exactly as stopped_then_paid_2026_08_04.py did, and every attribution is asserted
    non-null below."""
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
            # keep the FIRST-seen signal for the (date,strike,side); prefer one with a
            # populated trigger_level (ribbon needs it; vwap is legitimately None).
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
    """Reader for the pre-existing backtest/data/highres/*.csv files written by
    stop_width_grid_20260805.py's own loader: SAME naming convention (`{sym}_1m_{date}.csv`)
    but a DIFFERENT schema -- UTC `timestamp` instead of ET-naive `timestamp_et`. Confirmed by
    inspection of the 2026-08-05 files, not assumed. Read-only reparse; the file is never
    rewritten. Copied verbatim from stopped_then_paid_2026_08_04.py (same defect, same fix)."""
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


def spy_5m_for_date(date_iso: str) -> Optional[pd.DataFrame]:
    """Build a 5-minute SPY frame for a date the historical CSV does not cover (2026-08-06)
    by resampling real 1-minute SPY bars from the same disk-cached Alpaca REST source."""
    try:
        df, src = fetch_1min_cached("SPY", date_iso)
    except Exception:  # noqa: BLE001
        df, src = _load_legacy_schema_cache("SPY", date_iso), "legacy_schema_cache_reparsed"
    if df is None or df.empty:
        return None
    d = df.copy()
    d["timestamp_et"] = pd.to_datetime(d["timestamp_et"])
    if getattr(d["timestamp_et"].dt, "tz", None) is not None:
        d["timestamp_et"] = d["timestamp_et"].dt.tz_localize(None)
    r = (d.set_index("timestamp_et")
           .resample("5min")
           .agg({"open": "first", "high": "max", "low": "min", "close": "last",
                 "volume": "sum"})
           .dropna(subset=["close"])
           .reset_index())
    log(f"  SPY 5m {date_iso}: resampled {len(d)} 1-min -> {len(r)} 5-min bars ({src})")
    return r


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


def walk_week(pos: dict, bars: dict, spy_by_day: dict, lookup: pd.DataFrame,
              patch: dict, is_control: bool) -> list[dict]:
    """Sequential, one position at a time, per arm per day. A counterfactual position still
    open at a later REAL entry timestamp SUPPRESSES that entry."""
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
                    # reproduce history EXACTLY BY CONSTRUCTION -- never an approximate re-walk
                    cf_flat = dt.datetime(y, mo, dd,
                                          *(int(x) for x in p["exit_legs"][-1][0].split(":"))) \
                        if p["exit_legs"] else None
                    rows.append({**base, "suppressed": False,
                                 "dollar_pnl": p["realized_pnl"],
                                 "exit_reason": "REAL_BROKER_FILL"})
                    continue
                if cf_flat is not None and entry_ts < cf_flat:
                    rows.append({**base, "suppressed": True, "dollar_pnl": 0.0,
                                 "exit_reason": f"suppressed (cf open until {cf_flat.time()})"})
                    continue
                opt_df = bars.get((date_iso, p["symbol"]))
                if opt_df is None or spy_day is None or not p.get("strategy"):
                    # UNATTRIBUTED or unpriceable -> HELD AT ITS REAL P&L in EVERY cell,
                    # so it is arithmetically incapable of moving any reported delta.
                    # Never guessed at, never silently dropped (dropping it would change the
                    # day total and make the CONTROL_WALK baseline dishonest).
                    why = ("UNATTRIBUTED_HELD_AT_REAL" if not p.get("strategy")
                           else "NO_OPRA_HELD_AT_REAL")
                    rows.append({**base, "suppressed": False,
                                 "dollar_pnl": p["realized_pnl"], "exit_reason": why})
                    continue
                rtd = ribbon_tick_df_for(opt_df, lookup)
                shape = shape_for(p["strategy"], arm, patch)
                res = walk_exit_manager(
                    symbol=p["symbol"], side=p["side"], entry_time_et=entry_ts,
                    entry_premium=float(p["premium"]), qty=int(p["qty"]),
                    exit_shape=shape, structure_stop_enabled=True,
                    trigger_level=p["trigger_level"], strategy=p["strategy"],
                    time_stop_et=TIME_STOP_B, opt_df=opt_df, ribbon_tick_df=rtd,
                    five_min_spy_df=spy_day)
                cf_flat = res.exit_time_et
                rows.append({**base, "suppressed": False, "dollar_pnl": res.dollar_pnl,
                             "exit_reason": res.exit_reason})
    return rows


# ================================== scoring helpers =======================================
def tail_stats(pnls: list[float]) -> dict:
    losses = sorted(-p for p in pnls if p < 0)
    if not losses:
        return {"n_losers": 0}
    def pct(q: float) -> float:
        i = min(len(losses) - 1, max(0, int(round(q * (len(losses) - 1)))))
        return round(losses[i], 2)
    return {"n_losers": len(losses), "median": pct(0.50), "p75": pct(0.75),
            "p90": pct(0.90), "p95": pct(0.95), "max": round(losses[-1], 2),
            "total_loss": round(sum(losses), 2)}


def split_delta(cell_rows: list[dict], ctl_rows: list[dict], key) -> dict:
    ctl = {key(r): r["dollar_pnl"] for r in ctl_rows}
    loss_side = win_side = 0.0
    n_worse = n_better = 0
    for r in cell_rows:
        k = key(r)
        if k not in ctl:
            continue
        d = round(r["dollar_pnl"] - ctl[k], 2)
        if d > 0.005:
            n_better += 1
        elif d < -0.005:
            n_worse += 1
        if ctl[k] < 0:
            loss_side += d
        else:
            win_side += d
    return {"loss_side_delta": round(loss_side, 2), "win_side_delta": round(win_side, 2),
            "n_better": n_better, "n_worse": n_worse}


def main() -> int:
    t0 = time.time()
    assert PREREG.exists(), "frozen prereg missing"
    log(f"prereg: {PREREG.name}")

    # ---------- POPULATION A ----------
    log("POPULATION A: loading pinned 391-day replay ...")
    trades, spy_hist, lookup_hist = load_population_a()
    log(f"  n trades = {len(trades)}")

    a_by_cell: dict[str, list[dict]] = {}
    for c in CELLS:
        a_by_cell[c["id"]] = walk_population_a(trades, spy_hist, lookup_hist, c["patch"])
        log(f"  A {c['id']:12s} n={len(a_by_cell[c['id']]):3d} "
            f"total=${sum(r['dollar_pnl'] for r in a_by_cell[c['id']]):,.2f}")

    ctl_a = a_by_cell["CONTROL"]
    mism = [r for r in ctl_a if abs(r["dollar_pnl"] - r["src_pnl"]) > 0.005]
    log(f"  CONTROL reconciliation vs source replay: {len(mism)} mismatches "
        f"(MUST be 0; nonzero => scorecard VOID)")
    ctl_a_total = round(sum(r["dollar_pnl"] for r in ctl_a), 2)

    # runner anchor cohort: the 35 trades whose CONTROL exit rode the trail to a win
    runner_keys = {(r["symbol"], r["date"]) for r in ctl_a
                   if r["dollar_pnl"] > 0 and "runner_stop" in str(r["exit_reason"])}
    runner_ctl = round(sum(r["dollar_pnl"] for r in ctl_a
                           if (r["symbol"], r["date"]) in runner_keys), 2)
    log(f"  runner anchor cohort: n={len(runner_keys)} (expected {ANCHOR_RUNNER_N}) "
        f"${runner_ctl:,.2f} (expected ${ANCHOR_RUNNER_PNL:,.2f})")

    # ---------- POPULATION B ----------
    log("POPULATION B: real broker book 08-04/05/06 ...")
    pos = attribute_week(build_positions())
    unattributed = [(d, a, p["symbol"]) for d, arms in pos.items()
                    for a, pl in arms.items() for p in pl if not p.get("strategy")]
    log(f"  positions: " + ", ".join(
        f"{d}={sum(len(v) for v in pos[d].values())}" for d in WEEK_DATES))
    log(f"  unattributed strategy: {len(unattributed)} {unattributed[:5]}")

    spy_week = pd.read_csv(SPY_WEEK)
    spy_week["timestamp_et"] = pd.to_datetime(spy_week["timestamp_et"])
    if getattr(spy_week["timestamp_et"].dt, "tz", None) is not None:
        spy_week["timestamp_et"] = spy_week["timestamp_et"].dt.tz_localize(None)
    lookup_week = build_ribbon_lookup(spy_week)
    spy_by_day = {d: spy_week[spy_week["timestamp_et"].dt.date
                              == dt.date.fromisoformat(d)].reset_index(drop=True)
                  for d in WEEK_DATES}
    for d in WEEK_DATES:
        if spy_by_day[d].empty:
            # the historical CSV stops at 2026-08-05; build 08-06 from real 1-min SPY bars
            spy_by_day[d] = spy_5m_for_date(d)
        log(f"  SPY 5m rows {d}: "
            f"{0 if spy_by_day[d] is None else len(spy_by_day[d])}")
    # Re-warm the ribbon over the FULL week including any resampled day, so 08-06's ribbon
    # stack is not cold-started (compute_ribbon needs prior bars).
    extra = [spy_by_day[d] for d in WEEK_DATES
             if spy_by_day[d] is not None
             and not (spy_week["timestamp_et"].dt.date == dt.date.fromisoformat(d)).any()]
    if extra:
        spy_all = pd.concat([spy_week] + extra, ignore_index=True)
        spy_all = spy_all.sort_values("timestamp_et").reset_index(drop=True)
        lookup_week = build_ribbon_lookup(spy_all)
        log(f"  ribbon re-warmed over {len(spy_all)} SPY 5m bars (week + resampled days)")

    bars = load_week_bars(pos)

    b_by_cell: dict[str, list[dict]] = {}
    for c in CELLS:
        b_by_cell[c["id"]] = walk_week(pos, bars, spy_by_day, lookup_week,
                                       c["patch"], c["id"] == "CONTROL")
    ctl_b = b_by_cell["CONTROL"]              # real broker fills
    walk_b = b_by_cell["CONTROL_WALK"]        # unchanged shape through the SAME harness
    day_ctl = {d: round(sum(r["dollar_pnl"] for r in ctl_b if r["date"] == d), 2)
               for d in WEEK_DATES}
    day_walk = {d: round(sum(r["dollar_pnl"] for r in walk_b if r["date"] == d), 2)
                for d in WEEK_DATES}
    replay_divergence = {d: round(day_walk[d] - day_ctl[d], 2) for d in WEEK_DATES}
    log(f"  CONTROL (real fills) day totals: {day_ctl}")
    log(f"  CONTROL_WALK  (harness) totals : {day_walk}")
    log(f"  replay divergence (walk-real)  : {replay_divergence}  <- NOT a knob effect")

    # ---------- score every cell ----------
    keyA = lambda r: (r["symbol"], r["date"])            # noqa: E731
    keyB = lambda r: (r["date"], r["arm"], r["symbol"], r["entry_et"])  # noqa: E731

    results = []
    for c in CELLS:
        cid = c["id"]
        A = a_by_cell[cid]
        B = b_by_cell[cid]
        a_tot = round(sum(r["dollar_pnl"] for r in A), 2)
        a_delta = round(a_tot - ctl_a_total, 2)
        ctl_map = {keyA(r): r["dollar_pnl"] for r in ctl_a}
        per = [(keyA(r), round(r["dollar_pnl"] - ctl_map.get(keyA(r), 0.0), 2)) for r in A]
        changed = [d for _, d in per if abs(d) > 0.005]
        best = max(changed) if changed else 0.0
        run_cell = round(sum(r["dollar_pnl"] for r in A
                             if (r["symbol"], r["date"]) in runner_keys), 2)
        day_cell = {d: round(sum(r["dollar_pnl"] for r in B if r["date"] == d), 2)
                    for d in WEEK_DATES}
        # PRIMARY (gated) delta = vs CONTROL_WALK -> the ISOLATED knob effect, free of replay
        # divergence. Also reported: delta vs the real broker book, for transparency.
        base = day_ctl if cid == "CONTROL" else day_walk
        day_delta = {d: round(day_cell[d] - base[d], 2) for d in WEEK_DATES}
        day_delta_vs_real = {d: round(day_cell[d] - day_ctl[d], 2) for d in WEEK_DATES}
        gates = {
            "HG_TUE": day_delta["2026-08-04"] >= -0.005,
            "G1_popA_aggregate": a_delta > 0.005,
            "G2_runner_anchor": round(run_cell - runner_ctl, 2) >= -0.005,
            "G3_wednesday": day_delta["2026-08-05"] > 0.005,
            "G4_thursday": day_delta["2026-08-06"] >= -0.005,
            "G5_drop_best": round(a_delta - best, 2) > 0.005,
        }
        results.append({
            "id": cid, "axis": c["axis"], "patch": c["patch"],
            "popA_total": a_tot, "popA_delta": a_delta,
            "popA_drop_best": round(a_delta - best, 2),
            "popA_n_changed": len(changed),
            "popA_split": split_delta(A, ctl_a, keyA),
            "popA_tail": tail_stats([r["dollar_pnl"] for r in A]),
            "runner_cohort_total": run_cell,
            "runner_cohort_delta": round(run_cell - runner_ctl, 2),
            "week_day_total": day_cell, "week_day_delta": day_delta,
            "week_day_delta_vs_real_book": day_delta_vs_real,
            "week_total_delta": round(sum(day_delta.values()), 2),
            "week_split": split_delta([r for r in B if not r["suppressed"]],
                                      walk_b if cid != "CONTROL" else ctl_b, keyB),
            "week_suppressed": sum(1 for r in B if r["suppressed"]),
            "gates": gates,
            "clears_all": all(gates.values()) if cid != "CONTROL" else None,
        })
        log(f"  {cid:12s} popA d=${a_delta:>9,.2f} runner d=${run_cell-runner_ctl:>9,.2f} "
            f"| Tue ${day_delta['2026-08-04']:>8,.2f} Wed ${day_delta['2026-08-05']:>8,.2f} "
            f"Thu ${day_delta['2026-08-06']:>7,.2f}")

    # ---------- TP1 reachability (descriptive) ----------
    reach = {}
    mfes = []
    for t in trades:
        sym, ep = t["symbol"], float(t["entry_premium"])
        df = load_contract_bars(sym)
        if df is None or df.empty or ep <= 0:
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
        mfes.append((float(after["high"].max()) - ep) / ep)
    for thr in (0.20, 0.25, 0.30, 0.40, 0.50, 1.00):
        reach[f"+{int(thr*100)}%"] = round(sum(1 for m in mfes if m >= thr) / max(1, len(mfes)), 4)
    tp1_desc = {"n": len(mfes),
                "median_mfe": round(statistics.median(mfes), 4) if mfes else None,
                "reach_fraction": reach}
    log(f"  TP1 reachability n={len(mfes)} median MFE="
        f"{tp1_desc['median_mfe']} reach={reach}")

    out = {
        "_doc": "LEVER 3 -- catastrophe cap + per-trade loss tail. Run per frozen prereg "
                "analysis/recommendations/prereg-lever-catcap-2026-08-06.json (commit 089beb50).",
        "generated_at_et": dt.datetime.now().isoformat(),
        "runtime_seconds": round(time.time() - t0, 1),
        "prereg_commit": "089beb50",
        "populations": {
            "A": {"source": str(SOURCE_REPLAY.relative_to(REPO)), "n": len(ctl_a),
                  "control_total": ctl_a_total,
                  "control_reconciliation_mismatches": len(mism),
                  "runner_cohort_n": len(runner_keys), "runner_cohort_total": runner_ctl,
                  "runner_anchor_expected_n": ANCHOR_RUNNER_N,
                  "runner_anchor_expected_pnl": ANCHOR_RUNNER_PNL},
            "B": {"source": "real broker /v2/orders, 5 arms, 2026-08-04..06",
                  "n_positions": {d: sum(len(v) for v in pos[d].values()) for d in WEEK_DATES},
                  "control_day_totals_real_fills": day_ctl,
                  "control_walk_day_totals": day_walk,
                  "replay_divergence_walk_minus_real": replay_divergence,
                  "unattributed_strategy": unattributed,
                  "bars_missing": [f"{d}|{s}" for d, arms in pos.items()
                                   for a, pl in arms.items() for p in pl
                                   for s in [p["symbol"]] if (d, s) not in bars]},
        },
        "tp1_reachability": tp1_desc,
        "cells": results,
        "week_positions": {d: {a: pos[d][a] for a in ARMS if pos[d].get(a)} for d in WEEK_DATES},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}  ({round(time.time()-t0,1)}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
