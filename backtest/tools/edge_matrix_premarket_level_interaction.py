"""edge_matrix_premarket_level_interaction.py -- EDGE-MATRIX family runner:
PREMARKET-LEVEL-INTERACTION (frozen pre-reg:
analysis/edge-matrix/prereg-premarket-level-interaction-2026-07-23.json -- read that file
for the full frozen grid/population/gate definitions; this module is the runner, not a
second copy of the spec).

FAMILY: levels formed by premarket structure (04:00-09:30 ET highs/lows + premarket
S/R-flip levels; J exhibits 745.94 on 07-21, the 04:15/05:30/07:20 flip level on 07-17)
traded on FIRST RTH touch, rejection (fade) vs reclaim (break) direction rules, zone
bands from the LIVE LevelMemory constants (TOUCH_TOL=0.20 / CLUSTER_TOL=0.35).

RECONCILIATION with the KILLED PREMARKET-TOUCH-CREDIT study (2026-07-20, p~0.21): that
study asked whether premarket touch COUNTS segment the EXISTING RTH-trigger population.
This study asks whether the premarket level ITSELF is a viable entry anchor (a brand-new
signal population). The kill does not pre-decide this; if this also nulls, the premarket
idea is dead from both directions.

DATA PROVENANCE SEAM (measured before the pre-reg froze): full 04:00+ premarket coverage
(>=50 bars/day) starts 2026-03-16 -- ENTIRELY inside the held-out window. Tuning-side days
(2025-01-02..2026-02-24) carry a thin premarket feed (median ~3 bars/day; 77/285 days with
>=6). Tuning-side premarket levels are a degraded proxy and every verdict carries that
confound. Coverage floor: >= 6 premarket bars or the day is excluded (counted).

TIMESTAMP FRAME: wall-v1 (backtest/lib/et_frame.py convention) -- the SPY master + OPRA
caches store a FIXED -04:00 offset year-round; strip the tz label, keep the wall-clock
numbers, NEVER tz_convert. Matches exit_manager_walk.py and every existing scorecard.

Exits: the LIVE RIBBON_RIDE ExitShape (automation/state/fleet/strategies.py) walked
tick-by-tick through the REAL exit_manager via backtest/lib/exit_manager_walk.py, with
structure_stop_enabled=True (live params.json value, verified 2026-07-22) and
trigger_level = the premarket level (trigger-exact, buffer 0.00 -- live behavior).

Dollars: real OPRA fills ONLY (backtest/data/options/ via lib/option_pricing_real.py).
No-fill signals counted + disclosed, excluded from gate math. Zero BS-synthetic episodes.

ANALYSIS ONLY: writes only analysis/edge-matrix/premarket-level-interaction-episodes.json.
NO live wiring, NO git commits, NO broker imports.

Run: backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_premarket_level_interaction.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
_FLEET = REPO / "automation" / "state" / "fleet"
if str(_FLEET) not in sys.path:
    sys.path.insert(0, str(_FLEET))

import pandas as pd  # noqa: E402

from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.watchers.level_memory import BREAK_MARGIN, LevelMemory  # noqa: E402
import strategies as fleet_strategies  # noqa: E402  (automation/state/fleet/strategies.py)

INVENTORY = REPO / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
PREREG = REPO / "analysis" / "edge-matrix" / "prereg-premarket-level-interaction-2026-07-23.json"
EPISODES_OUT = REPO / "analysis" / "edge-matrix" / "premarket-level-interaction-episodes.json"
DATA_DIR = REPO / "backtest" / "data"

RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
PM_START = dt.time(4, 0)
ENTRY_CUTOFF = dt.time(15, 45)
TIME_STOP = dt.time(15, 50)
MIN_PM_BARS = 6
QTY = 3
PERM_DRAWS = 10_000
PERM_SEED = 20260723

# Frozen grid (pre-reg: 4 knobs, 16 cells)
LEVEL_DEFS = ("pm_hl", "pm_flip")
BANDS = (0.20, 0.35)
RULES = ("reject", "reclaim")
CONFIRMS = ("none", "next_bar")

_OFFSET_RE = re.compile(r"[+-]\d{2}:?\d{2}$")


def wall_naive(series: pd.Series) -> pd.Series:
    """wall-v1: strip any trailing tz offset from the timestamp STRING, keep wall-clock."""
    stripped = series.astype(str).str.replace(_OFFSET_RE, "", regex=True).str.replace("T", " ", regex=False)
    return pd.to_datetime(stripped, format="mixed")


def load_source_file(fname: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / fname)
    df = df.assign(timestamp_et=wall_naive(df["timestamp_et"]))
    df = df.drop_duplicates(subset="timestamp_et", keep="last").sort_values("timestamp_et")
    df = df.reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["time"] = df["timestamp_et"].dt.time
    return df


def rth_ribbon_stack_map(src_df: pd.DataFrame) -> dict:
    """Ribbon stack per wall timestamp, computed over the source file's RTH-ONLY
    concatenated frame (orchestrator's frame convention -- EMA warms across days)."""
    rth = src_df[(src_df["time"] >= RTH_START) & (src_df["time"] < RTH_END)].reset_index(drop=True)
    if rth.empty:
        return {}
    rib = compute_ribbon(rth["close"])
    return dict(zip(rth["timestamp_et"], rib["stack"]))


@dataclass(frozen=True)
class PmLevel:
    price: float
    kind: str        # "pm_high" | "pm_low" | "pm_flip"
    meta: str = ""


def premarket_levels(pm_bars: pd.DataFrame, level_def: str) -> list[PmLevel]:
    """Levels frozen at 09:30 from premarket bars ONLY. CAUSALITY GUARD: every input bar
    must be timestamped strictly before 09:30 on the same day (C6)."""
    assert len(pm_bars) >= MIN_PM_BARS
    assert (pm_bars["time"] < RTH_START).all(), "look-ahead: non-premarket bar fed to level builder"
    assert pm_bars["date"].nunique() == 1, "look-ahead: multi-day frame fed to premarket level builder"

    if level_def == "pm_hl":
        hi = float(pm_bars["high"].max())
        lo = float(pm_bars["low"].min())
        out = [PmLevel(price=round(hi, 2), kind="pm_high")]
        if abs(hi - lo) > 1e-9:
            out.append(PmLevel(price=round(lo, 2), kind="pm_low"))
        return out

    if level_def == "pm_flip":
        frame = pm_bars[["timestamp_et", "open", "high", "low", "close"]].copy()
        # LevelMemory tz-normalizes via utc=True; localize the wall clock to ET first so
        # the wall-clock numbers survive the round-trip unchanged (no DST ambiguity at
        # 04:00-09:25).
        frame["timestamp_et"] = frame["timestamp_et"].dt.tz_localize("America/New_York")
        lm = LevelMemory(frame)
        levels = lm.levels_at(len(frame) - 1, lookback_days=5)
        flips = [lv for lv in levels if lv.role_flips >= 1]
        if not flips:
            return []
        best = max(flips, key=lambda lv: lv.memory_score)
        return [PmLevel(price=round(best.price, 2), kind="pm_flip",
                        meta=f"role={best.role} flips={best.role_flips} mem={best.memory_score:.0f}")]

    raise ValueError(level_def)


@dataclass(frozen=True)
class Signal:
    date: str
    level: PmLevel
    band: float
    rule: str
    confirm: str
    signal_idx: int          # index into the day's RTH frame
    signal_ts: pd.Timestamp  # signal bar's OPEN timestamp
    entry_ts: pd.Timestamp   # signal bar close time (= entry evaluation instant)
    side: str                # "C" | "P"
    spot_at_signal: float


def first_touch_signal(rth: pd.DataFrame, prev_close_before_rth: float, level: PmLevel,
                       band: float, rule: str, confirm: str, date_str: str) -> Optional[Signal]:
    """First RTH touch of the zone [level-band, level+band]; direction + confirm rules per
    the frozen pre-reg. CAUSAL: the decision at bar t reads only bars <= t (+ optional
    confirm bar t+1, with entry strictly after it)."""
    lows = rth["low"].values
    highs = rth["high"].values
    closes = rth["close"].values
    lp = level.price

    touch_idx = None
    for i in range(len(rth)):
        if lows[i] <= lp + band and highs[i] >= lp - band:
            touch_idx = i
            break
    if touch_idx is None:
        return None

    t = touch_idx
    approach_close = closes[t - 1] if t > 0 else prev_close_before_rth
    approach_above = approach_close >= lp

    side: Optional[str] = None
    if rule == "reject":
        if approach_above and closes[t] > lp:
            side = "C"
        elif (not approach_above) and closes[t] < lp:
            side = "P"
    elif rule == "reclaim":
        if (not approach_above) and closes[t] >= lp + BREAK_MARGIN:
            side = "C"
        elif approach_above and closes[t] <= lp - BREAK_MARGIN:
            side = "P"
    if side is None:
        return None

    sig_idx = t
    if confirm == "next_bar":
        if t + 1 >= len(rth):
            return None
        nxt = closes[t + 1]
        ok = (nxt > closes[t]) if side == "C" else (nxt < closes[t])
        if not ok:
            return None
        sig_idx = t + 1

    sig_ts = rth["timestamp_et"].iloc[sig_idx]
    entry_ts = sig_ts + pd.Timedelta(minutes=5)
    # CAUSALITY GUARDS (C6): entry strictly after every bar the decision read.
    assert entry_ts > rth["timestamp_et"].iloc[t], "entry not strictly after touch bar"
    assert entry_ts > sig_ts, "entry not strictly after signal bar"
    if entry_ts.time() > ENTRY_CUTOFF:
        return None
    return Signal(date=date_str, level=level, band=band, rule=rule, confirm=confirm,
                  signal_idx=sig_idx, signal_ts=sig_ts, entry_ts=entry_ts, side=side,
                  spot_at_signal=float(closes[sig_idx]))


def opt_frame(symbol: str) -> Optional[pd.DataFrame]:
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return None
    out = df.copy()
    ts = out["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)  # drops the offset label, keeps wall clock
    out["timestamp_et"] = ts
    return out.sort_values("timestamp_et").reset_index(drop=True)


def run() -> dict:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["version"] == 1 and prereg["n_cells"] == 16
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    heldout = set(inv["heldout_days"])
    day_rows = [d for d in inv["days"] if d["has_opra"]]

    exit_shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()

    src_cache: dict[str, pd.DataFrame] = {}
    ribbon_cache: dict[str, dict] = {}

    episodes: list[dict] = []
    excluded_days = {"below_pm_floor": 0, "no_spy_bars": 0}
    day_meta: dict[str, dict] = {}

    for drow in day_rows:
        date_str = drow["date"]
        fname = drow["source_file"]
        if fname not in src_cache:
            src_cache[fname] = load_source_file(fname)
            ribbon_cache[fname] = rth_ribbon_stack_map(src_cache[fname])
        src = src_cache[fname]
        date_obj = dt.date.fromisoformat(date_str)
        day = src[src["date"] == date_obj]
        if day.empty:
            excluded_days["no_spy_bars"] += 1
            continue
        pm = day[(day["time"] >= PM_START) & (day["time"] < RTH_START)].reset_index(drop=True)
        rth = day[(day["time"] >= RTH_START) & (day["time"] < RTH_END)].reset_index(drop=True)
        if len(pm) < MIN_PM_BARS or rth.empty:
            excluded_days["below_pm_floor"] += 1
            continue
        prev_close = float(pm["close"].iloc[-1])
        day_meta[date_str] = {"n_pm_bars": int(len(pm)), "heldout": date_str in heldout}

        levels_by_def = {ld: premarket_levels(pm, ld) for ld in LEVEL_DEFS}
        spy_walk_df = day[["timestamp_et", "close"]].reset_index(drop=True)
        stack_map = ribbon_cache[fname]

        for ld, band, rule, confirm in product(LEVEL_DEFS, BANDS, RULES, CONFIRMS):
            cell_id = f"pmli-{ld}-b{int(band*100)}-{rule}-{confirm}"
            for level in levels_by_def[ld]:
                sig = first_touch_signal(rth, prev_close, level, band, rule, confirm, date_str)
                if sig is None:
                    continue
                ep = {
                    "cell_id": cell_id, "date": date_str, "heldout": date_str in heldout,
                    "level_def": ld, "level_kind": level.kind, "level_price": level.price,
                    "level_meta": level.meta, "band": band, "rule": rule, "confirm": confirm,
                    "signal_ts": str(sig.signal_ts), "entry_ts": str(sig.entry_ts),
                    "side": sig.side, "spot_at_signal": sig.spot_at_signal,
                    "n_pm_bars": int(len(pm)),
                }
                strike = int(sig.spot_at_signal + 0.5)  # ATM (V15_SAFE_TIERS offset 0)
                sym = option_symbol(date_obj, strike, sig.side)
                ep["strike"] = strike
                ep["symbol"] = sym
                odf = opt_frame(sym)
                fill_bar = None
                if odf is not None:
                    m = odf[odf["timestamp_et"] >= sig.entry_ts]
                    if not m.empty:
                        fill_bar = m.iloc[0]
                if fill_bar is None or float(fill_bar.get("vwap", 0) or 0) <= 0:
                    ep["fill_status"] = "no_fill"
                    episodes.append(ep)
                    continue
                entry_premium = float(fill_bar["vwap"])
                fill_ts = fill_bar["timestamp_et"]
                if fill_ts.time() > ENTRY_CUTOFF:
                    ep["fill_status"] = "no_fill_late"
                    episodes.append(ep)
                    continue
                walk_opt = odf[odf["timestamp_et"].dt.date == date_obj].reset_index(drop=True)
                rib_df = pd.DataFrame({
                    "timestamp_et": walk_opt["timestamp_et"],
                    "stack": [stack_map.get(t, float("nan")) for t in walk_opt["timestamp_et"]],
                })
                res = walk_exit_manager(
                    symbol=sym, side=sig.side, entry_time_et=fill_ts.to_pydatetime(),
                    entry_premium=entry_premium, qty=QTY, exit_shape=exit_shape,
                    structure_stop_enabled=True, trigger_level=level.price,
                    strategy="ribbon_ride", time_stop_et=TIME_STOP,
                    opt_df=walk_opt, ribbon_tick_df=rib_df, five_min_spy_df=spy_walk_df)
                ep.update({
                    "fill_status": "real_fill", "fill_ts": str(fill_ts),
                    "entry_premium": round(entry_premium, 4), "qty": QTY,
                    "pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                    "exit_ts": str(res.exit_time_et), "hold_minutes": res.hold_minutes,
                    "legs": [{"stage": l.stage, "qty": l.qty, "px": l.fill_price,
                              "pnl": l.leg_pnl} for l in res.legs],
                })
                episodes.append(ep)

    return {"episodes": episodes, "excluded_days": excluded_days, "day_meta": day_meta,
            "exit_shape": exit_shape}


def perm_p(pnls: list[float], draws: int, seed: int) -> float:
    """One-sided sign-flip permutation p for total > 0."""
    if len(pnls) < 5:
        return 1.0
    obs = sum(pnls)
    rng = random.Random(seed)
    ge = 0
    for _ in range(draws):
        tot = sum(x if rng.random() < 0.5 else -x for x in pnls)
        if tot >= obs:
            ge += 1
    return ge / draws


def summarize(run_out: dict) -> list[dict]:
    episodes = run_out["episodes"]
    cells = []
    for ld, band, rule, confirm in product(LEVEL_DEFS, BANDS, RULES, CONFIRMS):
        cell_id = f"pmli-{ld}-b{int(band*100)}-{rule}-{confirm}"
        eps = [e for e in episodes if e["cell_id"] == cell_id]
        tune = [e for e in eps if not e["heldout"]]
        held = [e for e in eps if e["heldout"]]
        tune_fills = [e for e in tune if e["fill_status"] == "real_fill"]
        held_fills = [e for e in held if e["fill_status"] == "real_fill"]
        pnls = [e["pnl"] for e in tune_fills]
        total = round(sum(pnls), 2)
        n = len(pnls)
        expectancy = round(total / n, 2) if n else 0.0
        by_day: dict[str, float] = {}
        for e in tune_fills:
            by_day[e["date"]] = by_day.get(e["date"], 0.0) + e["pnl"]
        n_days = len(by_day)
        day_wr = round(sum(1 for v in by_day.values() if v > 0) / n_days, 3) if n_days else 0.0
        top = sorted(pnls, reverse=True)
        ex_top3 = round(total - sum(top[:3]), 2)
        ex_top1 = round(total - (top[0] if top else 0.0), 2)
        held_total = round(sum(e["pnl"] for e in held_fills), 2)
        p = perm_p(pnls, PERM_DRAWS, PERM_SEED)
        gates = int(total > 0) + int(day_wr > 0.5) + int(ex_top1 > 0) + int(held_total > 0)
        cells.append({
            "cell_id": cell_id,
            "params": {"level_def": ld, "band": band, "rule": rule, "confirm": confirm,
                       "n_tuning_days_active": n_days, "ex_top1_total": ex_top1,
                       "held_out_fills": len(held_fills),
                       "n_signals_heldout": len(held),
                       "no_fill_tuning": len(tune) - len(tune_fills)},
            "n_signals": len(tune),
            "n_real_fills": n,
            "expectancy": expectancy,
            "total_pnl": total,
            "day_wr": day_wr,
            "ex_top3_total": ex_top3,
            "held_out_total": held_total,
            "p_raw": round(p, 4),
            "gates_passed": gates,
        })
    return cells


def main() -> None:
    run_out = run()
    cells = summarize(run_out)
    payload = {
        "family": "premarket-level-interaction",
        "prereg": str(PREREG.relative_to(REPO)),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "grid": {"level_def": LEVEL_DEFS, "band": BANDS, "rule": RULES, "confirm": CONFIRMS},
        "exit_shape": run_out["exit_shape"],
        "qty": QTY,
        "perm": {"draws": PERM_DRAWS, "seed": PERM_SEED},
        "excluded_days": run_out["excluded_days"],
        "n_days_covered": len(run_out["day_meta"]),
        "n_days_covered_tuning": sum(1 for v in run_out["day_meta"].values() if not v["heldout"]),
        "n_days_covered_heldout": sum(1 for v in run_out["day_meta"].values() if v["heldout"]),
        "cells": cells,
        "episodes": run_out["episodes"],
    }
    EPISODES_OUT.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"cells": cells, "excluded_days": run_out["excluded_days"],
                      "n_days_covered": payload["n_days_covered"],
                      "tuning_days": payload["n_days_covered_tuning"],
                      "heldout_days": payload["n_days_covered_heldout"],
                      "episodes_written": len(run_out["episodes"]),
                      "out": str(EPISODES_OUT)}, indent=1))


if __name__ == "__main__":
    main()
