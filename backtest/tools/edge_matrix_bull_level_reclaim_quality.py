"""edge_matrix_bull_level_reclaim_quality.py -- EDGE-MATRIX 2026-07-23 grid runner.

Family: bull-level-reclaim-quality. LEVEL RECLAIM (bull calls) with NOT-extended quality
conditioning (RSI cap / RSI-reset / distance-from-session-low cap -- J's 2026-07-21 dojo
ruling). Question: does conditioning rescue reclaim from the fires-at-tops lottery profile
(live blocked cohort n=24 WR 0%)?

Frozen pre-reg (written BEFORE this ran):
    analysis/edge-matrix/prereg-bull-level-reclaim-quality-2026-07-23.json

Reuse map (never re-derived):
  - Levels: backtest/lib/watchers/level_memory.py LevelMemory (live perception layer).
  - RSI: backtest/autoresearch/rsi_extension_block_probe._wilder_rsi.
  - Ribbon: backtest/lib/ribbon.compute_ribbon.
  - Fills: backtest/lib/option_pricing_real (real OPRA cache only -- NO BS-synthetic).
  - Exits: backtest/lib/exit_manager_walk.walk_exit_manager (REAL production decision core),
    RIBBON_RIDE shape via setup/scripts/dojo/sim_executor's live merge.
  - Strike/qty: sim_executor._strike_for (ATM live Safe tier) + risk_gate.max_affordable_qty.

Timestamp frames: et-v2 on BOTH SPY and OPRA sides (per-row offset -> UTC -> ET, DST-correct,
frame-consistent joins per backtest/lib/et_frame.py). Population comes from the day
inventory's own per-day source_file choices -- never from an independent cache pick.

CAUSALITY (C6): bar i uses only bars <= i. Level set/roles are frozen at bar i-1
(LevelMemory.levels_at(i-1)); the trigger is bar i's own close. Assert-checked at runtime by
a truncation spot-check on a sample of emitted signals (_assert_causal_spotcheck).

Rail-4 CLEAR: research tool + JSON outputs only. No broker import, no live wiring, no git ops.

USAGE:
    backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_bull_level_reclaim_quality.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from itertools import product
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from lib.watchers.level_memory import LevelMemory  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402
from autoresearch.rsi_extension_block_probe import _wilder_rsi  # noqa: E402
from dojo import sim_executor as se  # noqa: E402
import fleet_executor as fx  # noqa: E402

PREREG_PATH = _ROOT / "analysis" / "edge-matrix" / "prereg-bull-level-reclaim-quality-2026-07-23.json"
INVENTORY_PATH = _ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
EPISODES_PATH = _ROOT / "analysis" / "edge-matrix" / "bull-level-reclaim-quality-episodes.json"
RESULTS_PATH = _ROOT / "analysis" / "edge-matrix" / "bull-level-reclaim-quality-results-2026-07-23.json"
DATA_DIR = _ROOT / "backtest" / "data"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"

# ---- fixed detector constants (frozen in the pre-reg; never grid axes) -----------------
MIN_MEMORY = 20.0          # producer's MIN_MEMORY selection floor (level_memory.py T7 note)
LOOKBACK_DAYS = 5          # LevelMemory DEFAULT_LOOKBACK_DAYS (live default)
COOLDOWN_BARS = 6          # 30 min per-level re-fire dedupe
ENTRY_FIRST = dtime(9, 35)   # live 09:35 entry gate (trigger-bar START)
ENTRY_LAST = dtime(15, 30)   # last eligible trigger-bar START
RSI_RESET_LEVEL = 55.0     # J 07-21: reset to 50.8 preceded the good 11:15 entry
RSI_RESET_WINDOW = 12      # bars (60 min)
MIN_BAND = 0.15            # smallest grid band -- used only as a cheap candidate prefilter
ARM_ID = "safe"            # dojo alias -> accounts.json "safe-2" (CORE-SAFE, ATM tier)
STRATEGY_NAME = "ribbon_ride"
STRUCTURE_STOP_ENABLED = True  # fixed per pre-reg
SPOTCHECK_N = 25
SPOTCHECK_SEED = 20260723


@dataclass(frozen=True)
class Cell:
    band: float
    rsi_cap: Optional[float]
    rsi_reset_required: bool
    dist_cap: Optional[float]

    def cell_id(self) -> str:
        b = f"band{int(round(self.band * 100)):02d}"
        c = "capnone" if self.rsi_cap is None else f"cap{int(self.rsi_cap)}"
        r = "reseton" if self.rsi_reset_required else "resetoff"
        d = "distnone" if self.dist_cap is None else f"dist{int(round(self.dist_cap * 100))}"
        return f"{b}_{c}_{r}_{d}"

    def params(self) -> dict:
        return {"zone_band_dollars": self.band, "rsi_cap": self.rsi_cap,
                "rsi_reset_required": self.rsi_reset_required,
                "dist_from_session_low_cap_dollars": self.dist_cap}


def build_grid(prereg: dict) -> list[Cell]:
    ax = prereg["grid"]["axes"]
    cells = [Cell(band=float(b), rsi_cap=(None if c is None else float(c)),
                  rsi_reset_required=bool(r),
                  dist_cap=(None if d is None else float(d)))
             for b, c, r, d in product(ax["zone_band_dollars"], ax["rsi_cap"],
                                        ax["rsi_reset_required"],
                                        ax["dist_from_session_low_cap_dollars"])]
    assert len(cells) == prereg["grid"]["cell_count"], "grid drifted from pre-reg"
    return cells


# =====================================================================================
# Data loading -- inventory-pinned per-day source files, et-v2 frame on both sides.
# =====================================================================================
_SOURCE_CACHE: dict[str, pd.DataFrame] = {}


def _load_source_file(fname: str) -> pd.DataFrame:
    if fname not in _SOURCE_CACHE:
        df = pd.read_csv(DATA_DIR / fname)
        # format="ISO8601": some caches mix "YYYY-MM-DD HH:MM:SS-04:00" and
        # "YYYY-MM-DDTHH:MM:SS-04:00" rows (appended by different writers); both are ISO8601.
        ts = pd.to_datetime(df["timestamp_et"], utc=True,
                            format="ISO8601").dt.tz_convert("America/New_York")
        df["timestamp_et"] = ts.dt.tz_localize(None)  # et-v2: true ET wall time, naive
        _SOURCE_CACHE[fname] = df
    return _SOURCE_CACHE[fname]


def load_day_frames(inventory: dict) -> dict[str, pd.DataFrame]:
    """{date_str: RTH 5m frame (naive true-ET)} for every covered day, using the
    inventory's OWN per-day source_file (honors its dedupe rule exactly)."""
    frames: dict[str, pd.DataFrame] = {}
    for row in inventory["days"]:
        d = row["date"]
        src = _load_source_file(row["source_file"])
        day = date.fromisoformat(d)
        m = src["timestamp_et"].dt.date == day
        day_df = src.loc[m]
        rth = day_df.loc[(day_df["timestamp_et"].dt.time >= dtime(9, 30))
                          & (day_df["timestamp_et"].dt.time < dtime(16, 0))]
        rth = (rth.drop_duplicates(subset="timestamp_et")
                   .sort_values("timestamp_et").reset_index(drop=True))
        if len(rth) >= 30:
            frames[d] = rth[["timestamp_et", "open", "high", "low", "close", "volume"]].copy()
    return frames


def load_opt_df(symbol: str) -> Optional[pd.DataFrame]:
    """Real OPRA contract bars in the et-v2 naive frame, or None. NO synthetic fallback."""
    raw = load_contract_bars(symbol)
    if raw is None or raw.empty:
        return None
    df = raw.copy()
    ts = df["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return df.sort_values("timestamp_et").reset_index(drop=True)


# =====================================================================================
# Detector -- base reclaim events (shared across cells), causal by construction.
# =====================================================================================
@dataclass
class BaseEvent:
    day: str
    bar_idx: int              # day-local index of the trigger bar
    ts: str                   # trigger-bar START (naive true-ET iso)
    level_price: float
    memory_score: float
    role_flips: int
    prev_close: float
    close: float
    rsi: Optional[float]
    dist_from_low: float
    rsi_reset_ok: bool
    band_pass: dict           # {"0.15": bool, "0.25": bool}


def _detect_day(day: str, day_df: pd.DataFrame, window_df: pd.DataFrame,
                day_offset_in_window: int, rsi_day: list, reset_ok_day: list,
                bands: list[float]) -> list[BaseEvent]:
    """Base reclaim events for one day. window_df = prior <=4 covered days + this day
    (RTH, continuous); day bars start at day_offset_in_window inside it. Level set for
    trigger bar i comes from LevelMemory.levels_at(window-index of i-1) -- bars <= i-1 only."""
    lm = LevelMemory(window_df)
    closes = day_df["close"].values
    lows = day_df["low"].values
    times = day_df["timestamp_et"]
    events: list[BaseEvent] = []
    session_low = math.inf
    for i in range(len(day_df)):
        session_low = min(session_low, float(lows[i]))
        if i < 1:
            continue
        t = times.iloc[i].time()
        if not (ENTRY_FIRST <= t <= ENTRY_LAST):
            continue
        close_i = float(closes[i])
        prev_close = float(closes[i - 1])
        # cheap prefilter: a reclaim needs close_i > level + MIN_BAND >= prev_close + MIN_BAND
        if close_i - prev_close <= MIN_BAND:
            continue
        win_prev = day_offset_in_window + i - 1
        levels = lm.levels_at(win_prev, LOOKBACK_DAYS)
        for lvl in levels:
            if lvl.memory_score < MIN_MEMORY or lvl.role != "resistance":
                continue
            if prev_close > lvl.price:
                continue
            if close_i <= lvl.price + MIN_BAND:
                continue
            bp = {f"{b:.2f}": bool(close_i > lvl.price + b) for b in bands}
            if not any(bp.values()):
                continue
            events.append(BaseEvent(
                day=day, bar_idx=i, ts=times.iloc[i].isoformat(),
                level_price=float(lvl.price), memory_score=float(lvl.memory_score),
                role_flips=int(lvl.role_flips), prev_close=prev_close, close=close_i,
                rsi=rsi_day[i], dist_from_low=round(close_i - session_low, 4),
                rsi_reset_ok=bool(reset_ok_day[i]), band_pass=bp))
    return events


def cell_signals(events: list[BaseEvent], cell: Cell) -> list[BaseEvent]:
    """Apply the cell's band + quality gates, then the per-level cooldown."""
    picked: list[BaseEvent] = []
    last_fire: dict[tuple[str, float], int] = {}
    bkey = f"{cell.band:.2f}"
    for ev in events:  # events are in (day, bar_idx) order
        if not ev.band_pass[bkey]:
            continue
        if cell.rsi_cap is not None and (ev.rsi is None or ev.rsi >= cell.rsi_cap):
            continue
        if cell.rsi_reset_required and not ev.rsi_reset_ok:
            continue
        if cell.dist_cap is not None and ev.dist_from_low > cell.dist_cap:
            continue
        key = (ev.day, ev.level_price)
        prev = last_fire.get(key)
        if prev is not None and ev.bar_idx - prev < COOLDOWN_BARS:
            continue
        last_fire[key] = ev.bar_idx
        picked.append(ev)
    return picked


# =====================================================================================
# Execution -- real OPRA fill + REAL exit_manager walk. Cached per unique (signal, band).
# =====================================================================================
_WALK_CACHE: dict[tuple, dict] = {}
_RIBBON_CACHE: dict[tuple, Optional[pd.DataFrame]] = {}
_OPT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def _opt(symbol: str) -> Optional[pd.DataFrame]:
    if symbol not in _OPT_CACHE:
        _OPT_CACHE[symbol] = load_opt_df(symbol)
    return _OPT_CACHE[symbol]


def execute_signal(ev: BaseEvent, band: float, day_frames_stack: dict[str, pd.DataFrame],
                    safe_arm_cfg: dict, safe_params: dict, exit_shape: dict,
                    time_stop: dtime) -> dict:
    key = (ev.day, ev.bar_idx, ev.level_price, band)
    if key in _WALK_CACHE:
        return _WALK_CACHE[key]
    out = _execute_uncached(ev, band, day_frames_stack, safe_arm_cfg, safe_params,
                             exit_shape, time_stop)
    _WALK_CACHE[key] = out
    return out


def _execute_uncached(ev: BaseEvent, band: float, day_frames_stack: dict[str, pd.DataFrame],
                       safe_arm_cfg: dict, safe_params: dict, exit_shape: dict,
                       time_stop: dtime) -> dict:
    trade_date = date.fromisoformat(ev.day)
    spy_day = day_frames_stack[ev.day]  # carries 'stack'
    entry_spot = ev.close
    strike = se._strike_for(safe_arm_cfg, entry_spot, "C")
    symbol = option_symbol(trade_date, strike, "C")
    opt_df = _opt(symbol)
    base = {"day": ev.day, "trigger_ts": ev.ts, "level_price": ev.level_price,
            "memory_score": ev.memory_score, "band": band, "rsi": ev.rsi,
            "dist_from_low": ev.dist_from_low, "rsi_reset_ok": ev.rsi_reset_ok,
            "strike": strike, "symbol": symbol}
    if opt_df is None:
        return {**base, "status": "NO_OPTION_DATA"}
    entry_ts = pd.Timestamp(ev.ts) + pd.Timedelta(minutes=5)  # trigger bar CLOSE time
    fill = bar_at_or_after(opt_df, entry_ts)
    if fill is None or not (fill.vwap and fill.vwap > 0):
        return {**base, "status": "NO_FILL"}
    entry_premium = round(float(fill.vwap), 4)
    afford = fx.risk_gate.max_affordable_qty(equity=float(safe_arm_cfg.get("starting_equity", 2000.0)),
                                              premium=entry_premium, params=safe_params)
    qty = min(int(safe_params.get("min_contracts", 3)), afford) if afford else 0
    if qty < 1:
        return {**base, "status": "UNAFFORDABLE", "entry_premium": entry_premium}
    rkey = (ev.day, symbol)
    if rkey not in _RIBBON_CACHE:
        _RIBBON_CACHE[rkey] = se._ribbon_aligned_to(spy_day, opt_df)
    result = walk_exit_manager(
        symbol=symbol, side="C", entry_time_et=fill.timestamp_et,
        entry_premium=entry_premium, qty=qty, exit_shape=exit_shape,
        structure_stop_enabled=STRUCTURE_STOP_ENABLED,
        trigger_level=round(ev.level_price - band, 4), strategy=STRATEGY_NAME,
        time_stop_et=time_stop, opt_df=opt_df, ribbon_tick_df=_RIBBON_CACHE[rkey],
        five_min_spy_df=spy_day[["timestamp_et", "open", "high", "low", "close"]],
    )
    return {**base, "status": "FILLED", "qty": qty, "entry_premium": entry_premium,
            "entry_fill_ts": fill.timestamp_et.isoformat(), "pnl": result.dollar_pnl,
            "exit_reason": result.exit_reason,
            "exit_ts": (result.exit_time_et.isoformat() if result.exit_time_et else None),
            "hold_minutes": result.hold_minutes}


def run_cell(signals: list[BaseEvent], cell: Cell, day_frames_stack, safe_arm_cfg,
             safe_params, exit_shape, time_stop) -> list[dict]:
    """Sequential one-position-at-a-time execution. Returns per-episode rows."""
    episodes: list[dict] = []
    open_until: dict[str, Optional[pd.Timestamp]] = {}
    for ev in signals:
        busy_until = open_until.get(ev.day)
        trig = pd.Timestamp(ev.ts)
        if busy_until is not None and trig < busy_until:
            episodes.append({"day": ev.day, "trigger_ts": ev.ts, "level_price": ev.level_price,
                             "band": cell.band, "status": "SKIPPED_POSITION_OPEN"})
            continue
        row = execute_signal(ev, cell.band, day_frames_stack, safe_arm_cfg, safe_params,
                              exit_shape, time_stop)
        episodes.append(row)
        if row["status"] == "FILLED" and row.get("exit_ts"):
            open_until[ev.day] = pd.Timestamp(row["exit_ts"])
    return episodes


# =====================================================================================
# Statistics + gates (pre-reg conventions).
# =====================================================================================
def _one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se_ = (var / n) ** 0.5
    if se_ == 0:
        return 1.0
    t = mean / se_
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))
    return max(0.0, min(1.0, p))


def score_cell(cell: Cell, n_signals: int, episodes: list[dict], heldout: set[str]) -> dict:
    filled = [e for e in episodes if e.get("status") == "FILLED"]
    pnls = [float(e["pnl"]) for e in filled]
    n = len(pnls)
    total = round(sum(pnls), 2)
    by_day: dict[str, float] = {}
    for e in filled:
        by_day[e["day"]] = by_day.get(e["day"], 0.0) + float(e["pnl"])
    n_days = len(by_day)
    day_wins = sum(1 for v in by_day.values() if v > 0)
    top_sorted = sorted(pnls, reverse=True)
    ex_top1 = round(total - (top_sorted[0] if top_sorted else 0.0), 2)
    ex_top3 = round(total - sum(top_sorted[:3]), 2)
    held_days = [d for d in by_day if d in heldout]
    held_total = round(sum(by_day[d] for d in held_days), 2)
    g1 = total > 0
    g2 = n_days > 0 and day_wins > n_days / 2.0
    g3 = n > 0 and ex_top1 > 0
    g4 = bool(held_days) and held_total > 0
    return {
        "cell_id": cell.cell_id(), "params": cell.params(),
        "n_signals": n_signals, "n_real_fills": n,
        "n_no_option_data": sum(1 for e in episodes if e.get("status") == "NO_OPTION_DATA"),
        "n_no_fill": sum(1 for e in episodes if e.get("status") == "NO_FILL"),
        "n_unaffordable": sum(1 for e in episodes if e.get("status") == "UNAFFORDABLE"),
        "n_skipped_position_open": sum(1 for e in episodes if e.get("status") == "SKIPPED_POSITION_OPEN"),
        "total_pnl": total, "expectancy": (round(total / n, 2) if n else 0.0),
        "win_rate": (round(sum(1 for x in pnls if x > 0) / n, 3) if n else None),
        "n_days_with_fills": n_days, "day_wins": day_wins,
        "day_wr": (round(day_wins / n_days, 3) if n_days else 0.0),
        "ex_top1_total": ex_top1, "ex_top3_total": ex_top3,
        "held_out_days_with_fills": len(held_days), "held_out_total": held_total,
        "p_raw": round(_one_sample_p(pnls), 4),
        "gate_1_positive_aggregate": g1, "gate_2_day_majority": g2,
        "gate_3_survives_ex_top1": g3, "gate_4_held_out_positive": g4,
        "gates_passed": int(g1) + int(g2) + int(g3) + int(g4),
    }


# =====================================================================================
# Causality spot-check -- re-derive a sample of signals on truncated frames (C6 guard).
# =====================================================================================
def _assert_causal_spotcheck(base_events: list[BaseEvent], day_frames: dict[str, pd.DataFrame],
                              day_order: list[str], global_frame: pd.DataFrame,
                              rsi_full: pd.Series, bands: list[float]) -> int:
    if not base_events:
        return 0
    rng = random.Random(SPOTCHECK_SEED)
    sample = rng.sample(base_events, min(SPOTCHECK_N, len(base_events)))
    checked = 0
    for ev in sample:
        di = day_order.index(ev.day)
        prior = day_order[max(0, di - (LOOKBACK_DAYS - 1)):di]
        # TRUNCATED window: prior days + this day's bars STRICTLY <= trigger bar
        day_df = day_frames[ev.day]
        trunc_day = day_df.iloc[: ev.bar_idx + 1]
        window = pd.concat([day_frames[d] for d in prior] + [trunc_day], ignore_index=True)
        offset = len(window) - len(trunc_day)
        lm = LevelMemory(window)
        levels = lm.levels_at(offset + ev.bar_idx - 1, LOOKBACK_DAYS)
        match = [lv for lv in levels
                 if abs(lv.price - ev.level_price) < 1e-9 and lv.role == "resistance"
                 and lv.memory_score >= MIN_MEMORY]
        assert match, (f"CAUSALITY VIOLATION: signal {ev.day} bar {ev.bar_idx} level "
                       f"{ev.level_price} not reproducible on a frame truncated at the "
                       f"trigger bar -- the level set must depend only on bars <= i-1")
        assert abs(match[0].memory_score - ev.memory_score) < 1e-6, (
            f"CAUSALITY VIOLATION: memory_score drifted under truncation for {ev.day} "
            f"bar {ev.bar_idx} ({match[0].memory_score} vs {ev.memory_score})")
        # RSI: recompute on the truncated continuous series -- must match (ewm is causal)
        if ev.rsi is not None:
            gpos = global_frame.index[(global_frame["day"] == ev.day)
                                       & (global_frame["day_idx"] == ev.bar_idx)][0]
            rsi_trunc = _wilder_rsi(global_frame["close"].iloc[: gpos + 1].reset_index(drop=True))
            assert abs(float(rsi_trunc.iloc[-1]) - ev.rsi) < 1e-6, (
                f"CAUSALITY VIOLATION: RSI at {ev.day} bar {ev.bar_idx} changed under "
                f"truncation ({float(rsi_trunc.iloc[-1])} vs {ev.rsi})")
        checked += 1
    return checked


# =====================================================================================
# main
# =====================================================================================
def main() -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    opra_days = [d for d in inventory["opra_days"]]
    heldout = set(inventory["heldout_days"])
    grid = build_grid(prereg)
    bands = [float(b) for b in prereg["grid"]["axes"]["zone_band_dollars"]]

    print("[load] day frames from inventory-pinned sources ...", file=sys.stderr)
    day_frames = load_day_frames(inventory)
    day_order = sorted(day_frames.keys())
    missing = [d for d in opra_days if d not in day_frames]
    if missing:
        print(f"[warn] {len(missing)} opra days missing SPY frames: {missing[:5]}", file=sys.stderr)
    opra_days = [d for d in opra_days if d in day_frames]

    print("[indicators] continuous RSI + ribbon over all covered days ...", file=sys.stderr)
    parts = []
    for d in day_order:
        f = day_frames[d].copy()
        f["day"] = d
        f["day_idx"] = range(len(f))
        parts.append(f)
    global_frame = pd.concat(parts, ignore_index=True)
    rsi_full = _wilder_rsi(global_frame["close"])
    ribbon = compute_ribbon(global_frame["close"])
    global_frame["stack"] = ribbon["stack"].values
    # rolling min RSI over the reset window (causal: window ends at current bar)
    rsi_roll_min = rsi_full.rolling(RSI_RESET_WINDOW + 1, min_periods=1).min()

    # per-day views
    rsi_by_day: dict[str, list] = {}
    reset_by_day: dict[str, list] = {}
    stack_frames: dict[str, pd.DataFrame] = {}
    for d in day_order:
        m = global_frame["day"] == d
        rvals = rsi_full[m]
        rsi_by_day[d] = [None if pd.isna(v) else float(v) for v in rvals]
        reset_by_day[d] = [bool(v <= RSI_RESET_LEVEL) if not pd.isna(v) else False
                            for v in rsi_roll_min[m]]
        sf = day_frames[d].copy()
        sf["stack"] = global_frame.loc[m, "stack"].values
        stack_frames[d] = sf

    print(f"[detector] base reclaim events over {len(opra_days)} OPRA days ...", file=sys.stderr)
    base_events: list[BaseEvent] = []
    for n_done, d in enumerate(opra_days):
        di = day_order.index(d)
        prior = day_order[max(0, di - (LOOKBACK_DAYS - 1)):di]
        window = pd.concat([day_frames[p] for p in prior] + [day_frames[d]], ignore_index=True)
        offset = len(window) - len(day_frames[d])
        base_events.extend(_detect_day(d, day_frames[d], window, offset,
                                        rsi_by_day[d], reset_by_day[d], bands))
        if (n_done + 1) % 50 == 0:
            print(f"  ... {n_done + 1}/{len(opra_days)} days, {len(base_events)} events",
                  file=sys.stderr)
    print(f"[detector] {len(base_events)} base events", file=sys.stderr)

    checked = _assert_causal_spotcheck(base_events, day_frames, day_order, global_frame,
                                        rsi_full, bands)
    print(f"[causality] truncation spot-check PASSED on {checked} sampled signals", file=sys.stderr)

    safe_arm_cfg, _canonical = se._resolve_arm_cfg(ARM_ID)
    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    exit_shape = se._resolve_exit_shape(safe_arm_cfg, STRATEGY_NAME, None)
    time_stop = se._parse_hhmm(se._time_stop_et_for(safe_arm_cfg))
    print(f"[exec] exit_shape={exit_shape} time_stop={time_stop}", file=sys.stderr)

    cell_rows = []
    episodes_out: dict[str, list[dict]] = {}
    for cell in grid:
        sigs = cell_signals(base_events, cell)
        eps = run_cell(sigs, cell, stack_frames, safe_arm_cfg, safe_params, exit_shape,
                        time_stop)
        episodes_out[cell.cell_id()] = eps
        row = score_cell(cell, len(sigs), eps, heldout)
        cell_rows.append(row)
        print(f"  {row['cell_id']:38s} sig={row['n_signals']:5d} fills={row['n_real_fills']:5d} "
              f"total=${row['total_pnl']:>10.2f} exp=${row['expectancy']:>7.2f} "
              f"dayWR={row['day_wr']:.2f} held=${row['held_out_total']:>9.2f} "
              f"gates={row['gates_passed']}/4", file=sys.stderr)

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(_ROOT)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    results = {
        "generated_at": datetime.now().isoformat(),
        "family": prereg["family"],
        "prereg_file": _rel(PREREG_PATH),
        "inventory_file": _rel(INVENTORY_PATH),
        "n_opra_days_used": len(opra_days),
        "n_heldout_days": len(heldout),
        "n_base_events": len(base_events),
        "causality_spotcheck_passed_n": checked,
        "exit_shape_used": exit_shape,
        "time_stop_et": str(time_stop),
        "cells": cell_rows,
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    EPISODES_PATH.write_text(json.dumps({
        "_doc": ("Per-episode detail for verifier recompute -- edge-matrix 2026-07-23, "
                  "family bull-level-reclaim-quality. status=FILLED rows are real OPRA "
                  "fills walked through the production exit_manager; every other status "
                  "is disclosed and excluded from gate math. NO BS-synthetic anywhere."),
        "prereg_file": _rel(PREREG_PATH),
        "episodes_by_cell": episodes_out,
    }, indent=0, default=str), encoding="utf-8")
    print(f"[written] {RESULTS_PATH}")
    print(f"[written] {EPISODES_PATH}")
    return results


if __name__ == "__main__":
    main()
