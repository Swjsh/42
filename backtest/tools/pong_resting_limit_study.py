"""pong_resting_limit_study.py -- PONG-RESTING-LIMIT (2026-07-17).

J-directed brainstorm-to-evidence, 2026-07-17 ~10:55 ET: "price ping-pongs between
levels; set up resting limit BUY orders on the option at prices it will hit when the
underlying reaches our levels, so entries are grabbed by price action." STUDY ONLY --
no live code, no orders, no engine edits.

Frozen pre-registration: analysis/recommendations/prereg-pong-resting-limit-2026-07-17.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift).

MECHANISM (full detail in the frozen prereg -- summarized here):
  * LEVEL SET: backtest.lib.levels._detect_from_history -- the SAME as-of-causal level
    detector orchestrator.run_backtest uses (called with the exact same
    `full_history[timestamp_et <= bar_time]` pattern orchestrator.py:927-931 uses),
    frozen once per day at the day's first RTH bar. A level is SUPPORT (candidate CALL)
    if below the day's open spot, RESISTANCE (candidate PUT) if above.
  * ENTRY ZONE: a level ARMS a resting order on the first bar (09:35 ET+) whose CLOSE
    comes within $0.50 of it, approaching from the correct side, not yet crossed.
  * PRICING: P(L) = observed_option_premium + BS_delta*(L - observed_spot) -
    theta_5min, computed ONCE at the arm bar (BS delta/theta via lib.pricing, VIX-IV
    proxy; option premium is the REAL OPRA close at the arm bar).
  * FILL: first subsequent option bar (real OPRA) whose LOW is strictly below P(L).
    Fill price = P(L) exactly (no queue-position credit -- conservative).
  * CANCEL-WATCHER GRID: {no_cancel, cancel_0.15, cancel_0.30, cancel_0.50} -- cancels
    the resting order if the underlying trades through the level by that threshold
    before the option fills.
  * ONE POSITION AT A TIME: sibling-cancel -- while an order is pending, no other
    level's arm condition is evaluated that day.
  * ADVERSE-SELECTION SPLIT: every FILLED episode is classified bounce (level held for
    3 bars / 15 min after fill) vs slice_through (level broken within that window) --
    reported as separate populations, not just blended.
  * CONTROL = the CURRENT engine's confirmation-entry semantics (detect_level_rejection
    / detect_wick_rejection_bearish for PUT, detect_level_reclaim / detect_wick_reclaim_
    bullish for CALL) scoped to the SAME (date, level) episode -- if/when it fires within
    the same watch window, entered via ribbon_ride_strike_exit_ab.fetch_entry_and_bars
    (byte-identical house convention).
  * EXIT GRID: {tp 30%, tp 50%} x {structure stop through level, -35% premium stop} x
    {12-min, 30-min time stop from fill} = 8 shapes, SS-B-lineage tp1_qty_fraction/
    trailing-lock knobs held fixed.
  * FRICTION: candidate entry side carries NO added slippage (the passive fill IS the
    honest price, avoiding double-counting the SEC-DERA-cited passive-limit benefit);
    control entry side DOES carry the house DEFAULT_ENTRY_SLIPPAGE (marketable entries
    really do cross the spread). BOTH sides carry exit-side slippage + commission
    (lib.simulator_credit DEFAULT_EXIT_SLIPPAGE / DEFAULT_COMMISSION, unchanged).
  * PAIRING: delta_i = pnl_candidate(episode_i) - pnl_control(episode_i) over the union
    of episode_ids either side "traded" (untraded side = pnl 0) -- the simpler form
    WF-GATE-METHODOLOGY-2026-07-16.md itself states and bold_strike_axis_deltawf.py
    already uses, re-implemented locally (not imported) so the raw per-episode delta
    list can additionally feed sub-window-stability, anchor-check, and BH-FDR's null
    comparison.
  * GATES: the frozen ab_delta_per_trade_v2026_07_16 WF form (WF-GATE-METHODOLOGY-2026-
    07-16.md + Amendment 1) + BH-FDR (autoresearch.ribbon_rejection_wick_battery.bh_fdr,
    alpha=0.10) across all 32 (cancel_rule x exit_shape) cells PER ACCOUNT.
  * BOTH ACCOUNTS independently (C29) -- qty=3 fixed for both per the task's explicit
    instruction (a disclosed deviation from each account's own live qty knob).

TIMESTAMP CONVENTION: wall-v1 (parse the stored offset, strip tz, keep wall time) for
SPY and OPRA option bars -- both share the SAME year-round-fixed-offset storage
artifact (lib/et_frame.py), so this keeps SPY-to-option joins internally consistent
(the DEFAULT, guard-tested convention in this codebase; DST-correct et-v2 is not used
here, matching every other SS-B-lineage script's own ad hoc wall-v1-equivalent parse).
VIX is parsed the same way but its OWN stored offsets are genuinely correct per
et_frame.py, so VIX lookups are TRUE ET except for a disclosed <=1h skew in EST months
against the wall-v1 SPY/option clock -- a low-materiality approximation for a coarse
IV proxy, not re-derived here.

ANALYSIS ONLY. No params/config/trading-path/entry_manager.py/filters.py file touched.
No orders placed. If a cell clears, the BUILD SPEC is written as a section of the
scorecard md -- no j_intent_executor/entry_manager.py edit happens in this script.

Run: backtest/.venv/Scripts/python.exe backtest/tools/pong_resting_limit_study.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(REPO / "crypto" / "lib") not in sys.path:
    sys.path.insert(0, str(REPO / "crypto" / "lib"))

import pandas as pd  # noqa: E402

from lib import filters as filters_mod                                    # noqa: E402
from lib.levels import _detect_from_history                               # noqa: E402
from lib.pricing import black_scholes, vix_to_iv, time_to_expiry_years    # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol     # noqa: E402
from lib.simulator_credit import (                                        # noqa: E402
    DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE, DEFAULT_COMMISSION)
from exit_manager import ExitState, plan_exit_actions                     # noqa: E402
from autoresearch.runner import load_data                                 # noqa: E402
from autoresearch.null_baseline import random_entry_null                  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402
import ribbon_ride_strike_exit_ab as rrse                                 # noqa: E402
import structure_stop_study as sss                                        # noqa: E402
import strike_selection as ssel                                           # noqa: E402

SMOKE = "--smoke" in sys.argv

PREREG = REPO / "analysis" / "recommendations" / "prereg-pong-resting-limit-2026-07-17.json"
EXPECTED_PREREG_SHA16 = "0b9f9f813876fa09"
EXPECTED_PREREG_VERSION = 1

OUT_JSON = REPO / "analysis" / "recommendations" / ("pong-resting-limit-2026-07-17-SMOKE.json" if SMOKE
                                                     else "pong-resting-limit-2026-07-17.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("pong-resting-limit-2026-07-17-SMOKE.md" if SMOKE
                                                   else "pong-resting-limit-2026-07-17.md")

IS_START = dt.date(2025, 1, 1)
OOS_BOUNDARY = dt.date(2026, 1, 1)
DATA_END = dt.date(2026, 7, 8)   # latest date with a matching SPY+VIX master on disk this session

ENTRY_ZONE_WIDTH = 0.50           # reused from today's zone-rejection-band prereg's fixed_0.5 cell
MIN_ENTRY_PREMIUM = 0.30          # house floor (C7 convention), both candidate and control
THETA_MINUTES = 5
CLASSIFICATION_WINDOW_BARS = 3    # ~15 min, adverse-selection split
BREAK_MARGIN = 0.10
QTY = 3                           # fixed both accounts, disclosed deviation from live qty knob
NULL_SEEDS = 3 if SMOKE else 10   # reduced vs zone study's 20 -- 4x larger grid, disclosed
WF_GATE_BAR = 0.70

CANCEL_RULES: list[tuple[str, "float | None"]] = [
    ("no_cancel", None), ("cancel_0.15", 0.15), ("cancel_0.30", 0.30), ("cancel_0.50", 0.50),
]
EXIT_SHAPES: list[dict] = []
for _tp in (0.30, 0.50):
    for _stop in ("structure", "premium35"):
        for _tstop in (12, 30):
            _tp_lbl = "tp30" if _tp == 0.30 else "tp50"
            EXIT_SHAPES.append({"label": f"{_tp_lbl}_{_stop}_t{_tstop}", "tp_pct": _tp,
                                "stop_type": _stop, "time_stop_min": _tstop})

J_ANCHOR_DATES = {"2026-04-29", "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"}

_ORIG_LEVEL_REJECTION = filters_mod.detect_level_rejection
_ORIG_WICK_REJECTION_BEAR = filters_mod.detect_wick_rejection_bearish
_ORIG_LEVEL_RECLAIM = filters_mod.detect_level_reclaim
_ORIG_WICK_RECLAIM_BULL = filters_mod.detect_wick_reclaim_bullish

ACCOUNTS = {
    "safe": {"params_path": REPO / "automation" / "state" / "params.json", "tiers": ssel.V15_SAFE_TIERS},
    "bold": {"params_path": REPO / "automation" / "state" / "aggressive" / "params.json", "tiers": ssel.V15_BOLD_TIERS},
}
LIVE_EQUITY = {"safe": 1478.13, "bold": 1963.04}  # live-verified this session (Alpaca MCP get_account_info)


def log(msg: str) -> None:
    print(f"[pong-resting-limit] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT
# ---------------------------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored and preg.get("version") == EXPECTED_PREREG_VERSION)
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
           "expected_sha16": EXPECTED_PREREG_SHA16, "version": preg.get("version"), "status": preg.get("status")}


# ---------------------------------------------------------------------------------------------
# TIMESTAMP HELPERS -- wall-v1 (see module docstring)
# ---------------------------------------------------------------------------------------------
def _wallv1(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    if hasattr(ts, "dt") and ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    return ts


def tier_for_equity(tiers, equity: float):
    for t in tiers:
        if t.equity_min <= equity < t.equity_max:
            return t.strike_offset, t.label
    last = tiers[-1]
    return last.strike_offset, last.label


# ---------------------------------------------------------------------------------------------
# LEVEL SET -- once per day, shared across accounts and cancel_rule variants
# ---------------------------------------------------------------------------------------------
def build_level_by_day(spy_naive: pd.DataFrame) -> dict:
    level_by_day: dict = {}
    dates = sorted(spy_naive["date"].unique())
    for d in dates:
        day_rows = spy_naive[(spy_naive["date"] == d) & (spy_naive["time"] >= dt.time(9, 30))]
        if day_rows.empty:
            continue
        first_ts = day_rows["timestamp_et"].iloc[0]
        history_upto = spy_naive[spy_naive["timestamp_et"] <= first_ts]
        level_by_day[d] = _detect_from_history(history_upto, d)
    return level_by_day


# ---------------------------------------------------------------------------------------------
# VIX lookup -- nearest bar at/before ts (wall-v1 clock; VIX's own offsets are genuinely
# correct, so this is TRUE ET except for the disclosed <=1h SPY/option-side skew in EST months)
# ---------------------------------------------------------------------------------------------
class VixLookup:
    def __init__(self, vix_naive: pd.DataFrame):
        v = vix_naive.sort_values("timestamp_et").reset_index(drop=True)
        self.ts = v["timestamp_et"].values.astype("datetime64[ns]")
        self.close = v["close"].astype(float).values

    def at_or_before(self, ts: dt.datetime) -> "float | None":
        import numpy as np
        key = pd.Timestamp(ts).to_datetime64()
        idx = int(np.searchsorted(self.ts, key, side="right")) - 1
        if idx < 0:
            return None
        return float(self.close[idx])


# ---------------------------------------------------------------------------------------------
# PRICING -- delta-mapped resting-limit target
# ---------------------------------------------------------------------------------------------
def compute_pl(obs_spot: float, obs_premium: float, strike: int, is_call: bool, iv: float,
               arm_ts: dt.datetime, level: float) -> tuple[float, float, float]:
    """Returns (P(L), delta, theta_5min)."""
    tte = time_to_expiry_years(arm_ts)
    tte5 = time_to_expiry_years(arm_ts + dt.timedelta(minutes=THETA_MINUTES))
    price_now, delta = black_scholes(obs_spot, strike, iv, tte, is_call)
    price_5, _ = black_scholes(obs_spot, strike, iv, tte5, is_call)
    theta_5min = price_now - price_5
    p_l = round(max(0.01, obs_premium + delta * (level - obs_spot) - theta_5min), 2)
    return p_l, round(delta, 4), round(theta_5min, 4)


# ---------------------------------------------------------------------------------------------
# MINING -- one (account, cancel_rule) pass -> list of episode-arm records
# ---------------------------------------------------------------------------------------------
def mine_cancel_rule(so: int, time_stop_et: dt.time, spy_naive: pd.DataFrame, level_by_day: dict,
                     vix_lookup: VixLookup, cancel_threshold) -> list[dict]:
    episodes: list[dict] = []
    dates = sorted(level_by_day.keys())
    for d in dates:
        level_set = level_by_day[d]
        levels = level_set.active
        if not levels:
            continue
        day_rth = spy_naive[(spy_naive["date"] == d) & (spy_naive["time"] >= dt.time(9, 30))
                            & (spy_naive["time"] < dt.time(16, 0))].sort_values("timestamp_et").reset_index(drop=True)
        if day_rth.empty:
            continue
        day_open_spot = float(day_rth["open"].iloc[0])
        roles = {L: ("C" if L < day_open_spot else "P") for L in levels}
        levels_sorted = sorted(levels, key=lambda L: abs(L - day_open_spot))

        watch = day_rth[(day_rth["time"] >= dt.time(9, 35)) & (day_rth["time"] < time_stop_et)].reset_index(drop=True)
        if watch.empty:
            continue

        i = 0
        n_watch = len(watch)
        while i < n_watch:
            bar = watch.iloc[i]
            close = float(bar["close"])
            armed = None
            for L in levels_sorted:
                role = roles[L]
                gap = (close - L) if role == "C" else (L - close)
                if 0 < gap <= ENTRY_ZONE_WIDTH:
                    armed = (L, role)
                    break
            if armed is None:
                i += 1
                continue

            L, role = armed
            side = role
            arm_ts = bar["timestamp_et"].to_pydatetime() if hasattr(bar["timestamp_et"], "to_pydatetime") else bar["timestamp_et"]
            arm_spot = close
            episode_id = f"{d.isoformat()}|{role}|{L:.2f}"
            strike = rrse.strike_for(arm_spot, side, so)
            opt_df = load_contract_bars(option_symbol(d, strike, side))
            if opt_df is None or opt_df.empty:
                episodes.append({"episode_id": episode_id, "date": d.isoformat(), "role": role, "level": L,
                                 "arm_ts": str(arm_ts), "outcome": "no_local_bars", "so": so, "strike": strike})
                i += 1
                continue
            opt_ts = _wallv1(opt_df["timestamp_et"])
            opt_df = opt_df.assign(timestamp_et=opt_ts).sort_values("timestamp_et").reset_index(drop=True)
            obs_rows = opt_df[opt_df["timestamp_et"] <= arm_ts]
            if obs_rows.empty:
                episodes.append({"episode_id": episode_id, "date": d.isoformat(), "role": role, "level": L,
                                 "arm_ts": str(arm_ts), "outcome": "no_local_bars", "so": so, "strike": strike})
                i += 1
                continue
            obs_premium = float(obs_rows.iloc[-1]["close"])
            vix_now = vix_lookup.at_or_before(arm_ts)
            if vix_now is None:
                episodes.append({"episode_id": episode_id, "date": d.isoformat(), "role": role, "level": L,
                                 "arm_ts": str(arm_ts), "outcome": "no_vix", "so": so, "strike": strike})
                i += 1
                continue
            iv = vix_to_iv(vix_now)
            p_l, delta, theta_5min = compute_pl(arm_spot, obs_premium, strike, side == "C", iv, arm_ts, L)

            # cancel watch (SPY bars from arm bar forward)
            cancel_ts = None
            cancel_bar_pos = None
            if cancel_threshold is not None:
                for j in range(i, n_watch):
                    wb = watch.iloc[j]
                    breach = (float(wb["low"]) <= L - cancel_threshold) if role == "C" else (float(wb["high"]) >= L + cancel_threshold)
                    if breach:
                        cancel_ts = wb["timestamp_et"].to_pydatetime() if hasattr(wb["timestamp_et"], "to_pydatetime") else wb["timestamp_et"]
                        cancel_bar_pos = j
                        break

            # fill watch (option bars strictly after arm_ts, same date)
            walk_opt = opt_df[(opt_df["timestamp_et"] > arm_ts) & (opt_df["timestamp_et"].dt.date == d)]
            fill_ts = None
            for _, ob in walk_opt.iterrows():
                ob_ts = ob["timestamp_et"].to_pydatetime() if hasattr(ob["timestamp_et"], "to_pydatetime") else ob["timestamp_et"]
                if cancel_ts is not None and ob_ts > cancel_ts:
                    break
                if float(ob["low"]) < p_l:
                    fill_ts = ob_ts
                    break

            rec = {"episode_id": episode_id, "date": d.isoformat(), "role": role, "level": L,
                  "arm_ts": str(arm_ts), "arm_spot": arm_spot, "obs_premium": obs_premium,
                  "delta": delta, "theta_5min": theta_5min, "p_l": p_l, "so": so, "strike": strike,
                  "side": side}

            if cancel_ts is not None and (fill_ts is None or cancel_ts <= fill_ts):
                rec["outcome"] = "canceled"
                rec["fill_price"] = None
                episodes.append(rec)
                # resume scanning after the cancel bar
                i = (cancel_bar_pos + 1) if cancel_bar_pos is not None else n_watch
                continue

            if fill_ts is not None:
                if p_l < MIN_ENTRY_PREMIUM:
                    rec["outcome"] = "floor_skip"
                    rec["fill_price"] = None
                else:
                    rec["outcome"] = "filled"
                    rec["fill_price"] = p_l
                    rec["fill_ts"] = str(fill_ts)
                    # adverse-selection classification: up to 3 SPY 5m bars (15 min) after fill
                    after = day_rth[day_rth["timestamp_et"] > pd.Timestamp(fill_ts)].head(CLASSIFICATION_WINDOW_BARS)
                    broke = False
                    for _, ab in after.iterrows():
                        if role == "C":
                            if float(ab["low"]) <= L - BREAK_MARGIN:
                                broke = True
                                break
                        else:
                            if float(ab["high"]) >= L + BREAK_MARGIN:
                                broke = True
                                break
                    rec["classification"] = "slice_through" if broke else "bounce"
                episodes.append(rec)
                # slot busy through fill decision; resume scanning on the bar AFTER the fill bar
                next_candidates = watch.index[watch["timestamp_et"] > pd.Timestamp(fill_ts)]
                i = int(next_candidates[0]) if len(next_candidates) else n_watch
                continue

            # never resolved this day (no cancel, no fill) -- expires at time stop
            rec["outcome"] = "unfilled_expired"
            rec["fill_price"] = None
            episodes.append(rec)
            i = n_watch  # no more arms today (slot busy until expiry)

    return episodes


# ---------------------------------------------------------------------------------------------
# EXIT REPLAY -- candidate (no entry-side slippage) and control (full house friction)
# ---------------------------------------------------------------------------------------------
def replay_exit(entry_premium_raw: float, side: str, qty: int, walk_bars: list, ss_time, shape_cell: dict,
                fill_dt: dt.datetime, account_time_stop_et: dt.time, *, entry_side_friction: bool) -> float:
    tp_pct = shape_cell["tp_pct"]
    stop_pct = -0.35 if shape_cell["stop_type"] == "premium35" else -0.50
    ss_time_eff = ss_time if shape_cell["stop_type"] == "structure" else None
    ts_clock = min(fill_dt + dt.timedelta(minutes=shape_cell["time_stop_min"]),
                   dt.datetime.combine(fill_dt.date(), account_time_stop_et)).time()

    shape = {"premium_stop_pct": stop_pct, "tp1_premium_pct": tp_pct, "tp1_qty_fraction": 0.667,
            "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}
    entry_eff = entry_premium_raw + (DEFAULT_ENTRY_SLIPPAGE if entry_side_friction else 0.0)
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_eff, qty=qty, exit_shape=shape)
    open_qty = qty
    realized = 0.0
    last_close = entry_eff
    structure_fired = False
    for bar in walk_bars:
        if open_qty <= 0:
            break
        last_close = bar.c
        if ss_time_eff is not None and not structure_fired and bar.dt >= ss_time_eff:
            fp = max(0.01, bar.o - DEFAULT_EXIT_SLIPPAGE)
            realized += (fp - entry_eff) * open_qty * 100.0
            open_qty = 0
            structure_fired = True
            break
        now_et = bar.dt.time()
        dec = plan_exit_actions(state, best_premium=bar.h, worst_premium=bar.l, open_qty=open_qty,
                                now_et=now_et, ribbon_flip_back=False, time_stop_et=ts_clock)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_eff * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_eff * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                fp = entry_eff * (1.0 + state.premium_stop_pct)
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            else:
                fp = bar.c
            fp = max(0.01, fp - DEFAULT_EXIT_SLIPPAGE)
            realized += (fp - entry_eff) * a.qty * 100.0
            open_qty -= a.qty
        state = dec.state
    if open_qty > 0:
        fp = max(0.01, last_close - DEFAULT_EXIT_SLIPPAGE)
        realized += (fp - entry_eff) * open_qty * 100.0
        open_qty = 0
    commission = DEFAULT_COMMISSION * 2 * qty
    realized -= commission
    return round(realized, 2)


def _load_walk_bars(date: dt.date, strike: int, side: str, after_ts: dt.datetime) -> "list | None":
    opt_df = load_contract_bars(option_symbol(date, strike, side))
    if opt_df is None or opt_df.empty:
        return None
    ts = _wallv1(opt_df["timestamp_et"])
    df = opt_df.assign(timestamp_et=ts)
    walk = df[(df["timestamp_et"] > after_ts) & (df["timestamp_et"].dt.date == date)]
    if walk.empty:
        return []
    out = []
    for _, r in walk.iterrows():
        t = r["timestamp_et"].to_pydatetime() if hasattr(r["timestamp_et"], "to_pydatetime") else r["timestamp_et"]
        out.append(sss.NormBar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out


def candidate_pnl(ep: dict, shape_cell: dict, time_stop_et: dt.time, spy_by_date: dict) -> "float | None":
    date = dt.date.fromisoformat(ep["date"])
    fill_dt = dt.datetime.fromisoformat(ep["fill_ts"])
    walk_bars = _load_walk_bars(date, ep["strike"], ep["side"], fill_dt)
    if not walk_bars:
        return None
    ss_time = None
    if shape_cell["stop_type"] == "structure":
        day_bars = spy_by_date.get(date)
        if day_bars is not None:
            sub = day_bars[day_bars["timestamp_et"] >= fill_dt]
            ss_time = sss.structure_stop_signal_time(sub, ep["side"], float(ep["level"]), sss.STRUCTURE_BUFFER["SS-B"])
    return replay_exit(ep["fill_price"], ep["side"], QTY, walk_bars, ss_time, shape_cell, fill_dt, time_stop_et,
                       entry_side_friction=False)


# ---------------------------------------------------------------------------------------------
# CONTROL -- current engine confirmation-entry semantics, scoped to the SAME (date, level)
# ---------------------------------------------------------------------------------------------
def control_outcome(episode_id: str, date_iso: str, role: str, level: float, so: int,
                    time_stop_et: dt.time, spy_naive: pd.DataFrame, spy_by_date: dict) -> dict:
    date = dt.date.fromisoformat(date_iso)
    day_rth = spy_naive[(spy_naive["date"] == date) & (spy_naive["time"] >= dt.time(9, 35))
                        & (spy_naive["time"] < time_stop_et)].sort_values("timestamp_et").reset_index(drop=True)
    if day_rth.empty:
        return {"pnl": 0.0, "date": date, "traded": False}
    trig_ts, trig_bar = None, None
    for _, bar in day_rth.iterrows():
        if role == "P":
            lvl = _ORIG_LEVEL_REJECTION(bar, [level])
            if lvl is None:
                lvl = _ORIG_WICK_REJECTION_BEAR(bar, [level])
        else:
            lvl = _ORIG_LEVEL_RECLAIM(bar, [level])
            if lvl is None:
                lvl = _ORIG_WICK_RECLAIM_BULL(bar, [level])
        if lvl is not None:
            trig_ts = bar["timestamp_et"]
            trig_bar = bar
            break
    if trig_ts is None:
        return {"pnl": 0.0, "date": date, "traded": False}
    trig_dt = trig_ts.to_pydatetime() if hasattr(trig_ts, "to_pydatetime") else trig_ts
    entry_ts = trig_dt + dt.timedelta(minutes=5)
    entry_spot = float(trig_bar["close"])
    fetched = rrse.fetch_entry_and_bars(entry_spot, role, date, entry_ts, so, old_semantics=False)
    if fetched is None:
        return {"pnl": 0.0, "date": date, "traded": False}
    entry_premium_raw, walk_bars = fetched
    if entry_premium_raw < MIN_ENTRY_PREMIUM or not walk_bars:
        return {"pnl": 0.0, "date": date, "traded": False}
    return {"pnl": None, "date": date, "traded": True, "entry_premium_raw": entry_premium_raw,
           "walk_bars": walk_bars, "role": role, "level": level, "entry_ts": entry_ts}


def control_pnl_for_shape(ctrl: dict, shape_cell: dict, time_stop_et: dt.time, spy_by_date: dict) -> float:
    if not ctrl["traded"]:
        return 0.0
    ss_time = None
    if shape_cell["stop_type"] == "structure":
        day_bars = spy_by_date.get(ctrl["date"])
        if day_bars is not None:
            sub = day_bars[day_bars["timestamp_et"] >= ctrl["entry_ts"]]
            ss_time = sss.structure_stop_signal_time(sub, ctrl["role"], float(ctrl["level"]), sss.STRUCTURE_BUFFER["SS-B"])
    return replay_exit(ctrl["entry_premium_raw"], ctrl["role"], QTY, ctrl["walk_bars"], ss_time, shape_cell,
                       ctrl["entry_ts"], time_stop_et, entry_side_friction=True)


# ---------------------------------------------------------------------------------------------
# DELTA-WF (local re-implementation of the frozen ab_delta_per_trade_v2026_07_16 form --
# same math as bold_strike_axis_deltawf.compute_delta_wf/ladder_verdict, additionally
# exposing the raw per-episode delta list)
# ---------------------------------------------------------------------------------------------
def ladder_verdict(is_delta_mean, oos_delta_mean, wf_delta) -> str:
    if is_delta_mean is None or oos_delta_mean is None:
        return "FAIL"
    if is_delta_mean > 0:
        return "PASS" if (wf_delta is not None and wf_delta >= WF_GATE_BAR) else "FAIL"
    return "FAIL" if oos_delta_mean <= 0 else "INSUFFICIENT_REGIME_SHIFT"


def compute_delta_wf(cand: dict, ctrl: dict) -> dict:
    shared = sorted(i for i in cand if cand[i]["traded"] or ctrl[i]["traded"])
    deltas = []
    for i in shared:
        c_pnl = cand[i]["pnl"] if cand[i]["traded"] else 0.0
        x_pnl = ctrl[i]["pnl"] if ctrl[i]["traded"] else 0.0
        deltas.append({"episode_id": i, "date": cand[i]["date"], "delta": round(c_pnl - x_pnl, 2),
                       "cand_traded": cand[i]["traded"], "ctrl_traded": ctrl[i]["traded"]})
    is_d = [d for d in deltas if d["date"] < OOS_BOUNDARY]
    oos_d = [d for d in deltas if d["date"] >= OOS_BOUNDARY]
    n_is, n_oos = len(is_d), len(oos_d)
    is_sum = round(sum(d["delta"] for d in is_d), 2)
    oos_sum = round(sum(d["delta"] for d in oos_d), 2)
    is_mean = round(is_sum / n_is, 4) if n_is else None
    oos_mean = round(oos_sum / n_oos, 4) if n_oos else None
    wf = None
    if is_mean is not None and is_mean > 0 and n_oos > 0:
        wf = round((oos_sum / n_oos) / (is_sum / n_is), 4)
    ladder = ladder_verdict(is_mean, oos_mean, wf)
    sw_stable = True
    if oos_d:
        oos_sorted = sorted(oos_d, key=lambda d: d["date"])
        mid = len(oos_sorted) // 2
        sw1 = sum(d["delta"] for d in oos_sorted[:mid])
        sw2 = sum(d["delta"] for d in oos_sorted[mid:])
        sw_stable = sum(1 for tot in (sw1, sw2) if tot < 0) <= 1
    return {"n_shared": len(shared), "n_is": n_is, "n_oos": n_oos, "is_delta_sum": is_sum, "oos_delta_sum": oos_sum,
           "is_delta_mean": is_mean, "oos_delta_mean": oos_mean, "wf_delta": wf, "ladder_verdict": ladder,
           "n_cand_only": sum(1 for d in deltas if d["cand_traded"] and not d["ctrl_traded"]),
           "n_ctrl_only": sum(1 for d in deltas if d["ctrl_traded"] and not d["cand_traded"]),
           "n_both_traded": sum(1 for d in deltas if d["cand_traded"] and d["ctrl_traded"]),
           "oos_positive": bool(oos_sum > 0), "wf_ge_070": bool(wf is not None and wf >= WF_GATE_BAR),
           "sub_window_stable": sw_stable, "deltas": deltas}


def anchor_no_regression(deltas: list[dict], cand_outcomes: dict) -> bool:
    for d in deltas:
        if d["cand_traded"] and str(d["date"]) in J_ANCHOR_DATES:
            return False
    return True


# ---------------------------------------------------------------------------------------------
# NULL SANITY -- random-entry baseline for BH-FDR, same house pattern as zone-rejection-band
# ---------------------------------------------------------------------------------------------
def make_null_sim_fn(so: int, time_stop_et: dt.time, shape_cell: dict, spy_by_date: dict):
    def _sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level, triggers_fired,
             side, qty, setup, premium_stop_pct, strike_offset):
        entry_ts = entry_bar["timestamp_et"].to_pydatetime() if hasattr(entry_bar["timestamp_et"], "to_pydatetime") else entry_bar["timestamp_et"]
        date = entry_ts.date()
        entry_spot = float(entry_bar["close"])
        fetched = rrse.fetch_entry_and_bars(entry_spot, side, date, entry_ts, so, old_semantics=False)
        if fetched is None:
            return None
        entry_premium_raw, walk_bars = fetched
        if entry_premium_raw < MIN_ENTRY_PREMIUM:
            return None
        ss_time = None
        if shape_cell["stop_type"] == "structure" and rejection_level is not None:
            day_bars = spy_by_date.get(date)
            if day_bars is not None:
                sub = day_bars[day_bars["timestamp_et"] >= entry_ts]
                ss_time = sss.structure_stop_signal_time(sub, side, float(rejection_level), sss.STRUCTURE_BUFFER["SS-B"])
        pnl = replay_exit(entry_premium_raw, side, qty, walk_bars, ss_time, shape_cell, entry_ts, time_stop_et,
                          entry_side_friction=True)
        return SimpleNamespace(dollar_pnl=pnl)
    return _sim


def empirical_p_null(real_per_trade, null_by_seed: list[float]) -> float:
    if real_per_trade is None or not null_by_seed:
        return 1.0
    ge = sum(1 for v in null_by_seed if v >= real_per_trade)
    return round((1 + ge) / (1 + len(null_by_seed)), 4)


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        log("PREREG HASH/VERSION MISMATCH -- refusing to run a drifted spec. Aborting.")
        return 1

    if SMOKE:
        load_start, data_end = dt.date(2026, 5, 19), dt.date(2026, 6, 20)
    else:
        load_start, data_end = IS_START, DATA_END
    log(f"loading SPY/VIX data {load_start}..{data_end} ...")
    spy_full, vix_full = load_data(load_start, data_end)

    spy_naive = spy_full.copy()
    spy_naive["timestamp_et"] = _wallv1(spy_naive["timestamp_et"])
    spy_naive["date"] = spy_naive["timestamp_et"].dt.date
    spy_naive["time"] = spy_naive["timestamp_et"].dt.time
    if not SMOKE:
        spy_naive = spy_naive[spy_naive["date"] >= IS_START]
    spy_naive = spy_naive.sort_values("timestamp_et").reset_index(drop=True)
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_naive.groupby("date")}

    vix_naive = vix_full.copy()
    vix_naive["timestamp_et"] = _wallv1(vix_naive["timestamp_et"])
    vix_lookup = VixLookup(vix_naive)

    log(f"building causal level set per day over {spy_naive['date'].nunique()} days ...")
    level_by_day = build_level_by_day(spy_naive)
    log(f"level_by_day: {len(level_by_day)} days with an active level set")

    accounts_out: dict = {}
    for label, cfg in ACCOUNTS.items():
        raw_params = json.loads(cfg["params_path"].read_text(encoding="utf-8-sig"))
        equity = LIVE_EQUITY[label]
        so, tier_label = tier_for_equity(cfg["tiers"], equity)
        time_stop_et = dt.datetime.strptime(raw_params.get("time_stop_et", "15:40"), "%H:%M").time()
        log(f"[{label}] tier={tier_label} so={so} equity=${equity} time_stop={time_stop_et}")

        # --- mining: 4 cancel_rule passes ---
        mined_by_rule: dict = {}
        for rule_label, threshold in CANCEL_RULES:
            t0 = _time_mod.time()
            eps = mine_cancel_rule(so, time_stop_et, spy_naive, level_by_day, vix_lookup, threshold)
            mined_by_rule[rule_label] = eps
            n_filled = sum(1 for e in eps if e.get("outcome") == "filled")
            n_bounce = sum(1 for e in eps if e.get("classification") == "bounce")
            n_slice = sum(1 for e in eps if e.get("classification") == "slice_through")
            log(f"[{label}][{rule_label}] {len(eps)} arm events, {n_filled} filled "
               f"(bounce={n_bounce} slice={n_slice}) ({round(_time_mod.time()-t0,1)}s)")

        # --- episode universe (union across cancel_rule mining passes) ---
        universe: dict = {}
        for rule_label, eps in mined_by_rule.items():
            for ep in eps:
                universe.setdefault(ep["episode_id"], ep)  # first-seen record for role/level/date

        # --- control (memoized per episode_id, independent of cancel_rule) ---
        control_cache: dict = {}
        for eid, ep in universe.items():
            control_cache[eid] = control_outcome(eid, ep["date"], ep["role"], ep["level"], so, time_stop_et,
                                                 spy_naive, spy_by_date)
        n_control_traded = sum(1 for c in control_cache.values() if c["traded"])
        log(f"[{label}] control: {len(control_cache)} episode_ids, {n_control_traded} confirmation-triggered")

        # --- control pnl per (episode_id, exit_shape) -- independent of cancel_rule, so cache
        # ONCE per shape and reuse across all 4 cancel_rule passes (4x fewer replay walks) ---
        eid_date: dict = {eid: dt.date.fromisoformat(universe[eid]["date"]) for eid in universe}
        ctrl_pnl_cache: dict = {}   # (eid, shape_label) -> pnl
        ctrl_outcomes_by_shape: dict = {}  # shape_label -> {eid: {"pnl","date","traded"}}
        for shape_cell in EXIT_SHAPES:
            shape_label = shape_cell["label"]
            outcomes = {}
            for eid in universe:
                ctrl = control_cache[eid]
                if ctrl["traded"]:
                    key = (eid, shape_label)
                    if key not in ctrl_pnl_cache:
                        ctrl_pnl_cache[key] = control_pnl_for_shape(ctrl, shape_cell, time_stop_et, spy_by_date)
                    pnl = ctrl_pnl_cache[key]
                else:
                    pnl = 0.0
                outcomes[eid] = {"pnl": pnl, "date": eid_date[eid], "traded": ctrl["traded"]}
            ctrl_outcomes_by_shape[shape_label] = outcomes

        # --- control-sanity (candidate-vs-itself, mandatory WF-GATE-METHODOLOGY disclosure) --
        # computed ONCE against a reference shape's control outcomes; self-vs-self degenerates
        # to delta=0 for every episode regardless of which shape's pnl values are used.
        _ref_outcomes = ctrl_outcomes_by_shape[EXIT_SHAPES[0]["label"]]
        self_dwf = compute_delta_wf(_ref_outcomes, _ref_outcomes)
        control_sanity = {"is_delta_mean": self_dwf["is_delta_mean"], "oos_delta_mean": self_dwf["oos_delta_mean"],
                          "wf_delta": self_dwf["wf_delta"], "ladder_verdict": self_dwf["ladder_verdict"]}

        # --- per (cancel_rule, exit_shape) cell ---
        cells_out: dict = {}
        bh_input: list[dict] = []
        null_cache: dict = {}
        cell_order: list[tuple[str, str]] = []
        for rule_label, _thr in CANCEL_RULES:
            eps_by_id = {e["episode_id"]: e for e in mined_by_rule[rule_label]}
            for shape_cell in EXIT_SHAPES:
                shape_label = shape_cell["label"]
                cell_order.append((rule_label, shape_label))

                ctrl_outcomes = ctrl_outcomes_by_shape[shape_label]
                cand_outcomes: dict = {}
                n_bounce_filled = n_slice_filled = 0
                bounce_delta_sum = slice_delta_sum = 0.0
                for eid in universe:
                    ep = eps_by_id.get(eid)
                    if ep is not None and ep.get("outcome") == "filled":
                        c_pnl = candidate_pnl(ep, shape_cell, time_stop_et, spy_by_date)
                        if c_pnl is not None:
                            cand_outcomes[eid] = {"pnl": c_pnl, "date": dt.date.fromisoformat(ep["date"]), "traded": True}
                            if ep.get("classification") == "bounce":
                                n_bounce_filled += 1
                                bounce_delta_sum += (c_pnl - ctrl_outcomes[eid]["pnl"])
                            else:
                                n_slice_filled += 1
                                slice_delta_sum += (c_pnl - ctrl_outcomes[eid]["pnl"])
                            continue
                    cand_outcomes[eid] = {"pnl": 0.0, "date": ctrl_outcomes[eid]["date"], "traded": False}

                dwf = compute_delta_wf(cand_outcomes, ctrl_outcomes)
                anchor_ok = anchor_no_regression(dwf["deltas"], cand_outcomes)
                n = dwf["n_shared"]
                per_trade_mean = round((dwf["is_delta_sum"] + dwf["oos_delta_sum"]) / n, 2) if n else None

                null_key = (shape_label, min(dwf["n_both_traded"] + dwf["n_cand_only"], 40))
                if null_key not in null_cache and null_key[1] > 0:
                    n_signals = null_key[1]
                    n_call = sum(1 for eid in cand_outcomes if cand_outcomes[eid]["traded"]
                                and eps_by_id.get(eid, {}).get("side") == "C")
                    n_call = min(n_call, n_signals)
                    n_put = n_signals - n_call
                    rth = spy_naive[(spy_naive["time"] >= dt.time(9, 30)) & (spy_naive["time"] <= dt.time(16, 0))].reset_index(drop=True)
                    sim_fn = make_null_sim_fn(so, time_stop_et, shape_cell, spy_by_date)
                    null_res = random_entry_null(
                        rth=rth, n_signals=n_signals, n_call=n_call, n_put=n_put, strike_offset=so,
                        premium_stop_pct=(-0.35 if shape_cell["stop_type"] == "premium35" else -0.50), qty=QTY,
                        entry_gate=(dt.time(9, 35), time_stop_et), seeds=NULL_SEEDS,
                        setup="PONG_NULL", sim_fn=sim_fn,
                    )
                    null_cache[null_key] = null_res.get("per_trade_by_seed", [])
                p_null = empirical_p_null(per_trade_mean, null_cache.get(null_key, []))

                cells_out[f"{rule_label}|{shape_label}"] = {
                    "cancel_rule": rule_label, "exit_shape": shape_label, "n": n,
                    "n_is": dwf["n_is"], "n_oos": dwf["n_oos"],
                    "is_delta_mean": dwf["is_delta_mean"], "oos_delta_mean": dwf["oos_delta_mean"],
                    "wf_delta": dwf["wf_delta"], "verdict_ladder": dwf["ladder_verdict"],
                    "oos_positive": dwf["oos_positive"], "wf_ge_070": dwf["wf_ge_070"],
                    "sub_window_stable": dwf["sub_window_stable"], "anchor_no_regression": anchor_ok,
                    "per_trade_mean": per_trade_mean, "p_null": p_null,
                    "n_bounce_filled": n_bounce_filled, "n_slice_filled": n_slice_filled,
                    "bounce_delta_total": round(bounce_delta_sum, 2), "slice_delta_total": round(slice_delta_sum, 2),
                    "bounce_delta_mean": round(bounce_delta_sum / n_bounce_filled, 2) if n_bounce_filled else None,
                    "slice_delta_mean": round(slice_delta_sum / n_slice_filled, 2) if n_slice_filled else None,
                    "n_cand_only": dwf["n_cand_only"], "n_ctrl_only": dwf["n_ctrl_only"], "n_both_traded": dwf["n_both_traded"],
                }
                bh_input.append({"p_null": p_null})

        bh_fdr(bh_input, alpha=FDR_ALPHA)
        for (rule_label, shape_label), b in zip(cell_order, bh_input):
            key = f"{rule_label}|{shape_label}"
            cells_out[key]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
            cells_out[key]["bh_rank"] = b["bh_rank"]

        gates: dict = {}
        decisions: dict = {}
        for key, c in cells_out.items():
            g_ = {"oos_positive": bool(c["oos_positive"]), "wf_ge_070": bool(c["wf_ge_070"]),
                 "sub_window_stable": bool(c["sub_window_stable"]), "anchor_no_regression": bool(c["anchor_no_regression"]),
                 "bh_fdr_survivor": bool(c["bh_fdr_survivor"])}
            g_["all_5_pass"] = all(g_.values())
            gates[key] = g_
            fails = [k for k, v in g_.items() if k != "all_5_pass" and not v]
            decisions[key] = {"ship_ready": g_["all_5_pass"] and c["n"] > 0, "fails": fails, "n": c["n"],
                              "evidence_thin": c["n"] < 15}

        ship_ready = [k for k in cells_out if decisions[k]["ship_ready"]]
        winner = None
        if ship_ready:
            winner = max(ship_ready, key=lambda k: (cells_out[k]["oos_delta_mean"] or -1e18, cells_out[k]["n"]))
        n_gates_passed = {k: sum(1 for kk, v in gates[k].items() if kk != "all_5_pass" and v) for k in cells_out}
        closest = max(cells_out.keys(), key=lambda k: (n_gates_passed[k], cells_out[k]["n"]))

        # --- adverse-selection split, blended across cancel rules (raw, un-cancel-filtered = no_cancel cell family) ---
        raw_bounce_n = sum(1 for e in mined_by_rule["no_cancel"] if e.get("classification") == "bounce")
        raw_slice_n = sum(1 for e in mined_by_rule["no_cancel"] if e.get("classification") == "slice_through")

        accounts_out[label] = {
            "tier_label": tier_label, "strike_offset": so, "equity_live_verified": equity, "qty": QTY,
            "time_stop_et": str(time_stop_et),
            "mining_summary": {rule: {
                "n_arm_events": len(eps), "n_filled": sum(1 for e in eps if e.get("outcome") == "filled"),
                "n_canceled": sum(1 for e in eps if e.get("outcome") == "canceled"),
                "n_unfilled_expired": sum(1 for e in eps if e.get("outcome") == "unfilled_expired"),
                "n_no_local_bars": sum(1 for e in eps if e.get("outcome") == "no_local_bars"),
                "n_floor_skip": sum(1 for e in eps if e.get("outcome") == "floor_skip"),
                "n_bounce": sum(1 for e in eps if e.get("classification") == "bounce"),
                "n_slice_through": sum(1 for e in eps if e.get("classification") == "slice_through"),
            } for rule, eps in mined_by_rule.items()},
            "adverse_selection_split_raw_no_cancel": {
                "n_bounce": raw_bounce_n, "n_slice_through": raw_slice_n,
                "slice_through_share": round(raw_slice_n / (raw_bounce_n + raw_slice_n), 4) if (raw_bounce_n + raw_slice_n) else None,
            },
            "control_confirmation_summary": {"n_episode_ids": len(control_cache), "n_confirmation_triggered": n_control_traded},
            "control_sanity_disclosure": control_sanity,
            "cells": cells_out, "gates": gates, "decisions": decisions,
            "verdict": {"any_ship_ready": bool(ship_ready), "ship_ready_cells": ship_ready, "winner": winner,
                       "closest_cell": closest, "closest_cell_gates_passed": n_gates_passed[closest],
                       "closest_cell_fails": decisions[closest]["fails"],
                       "closest_cell_verdict_ladder": cells_out[closest]["verdict_ladder"]},
        }
        log(f"[{label}] VERDICT any_ship_ready={bool(ship_ready)} winner={winner} n_cells_ship_ready={len(ship_ready)}")

    elapsed_total = round(_time_mod.time() - t_start, 1)
    any_ship_ready_overall = any(accounts_out[a]["verdict"]["any_ship_ready"] for a in accounts_out)

    out = {
        "_doc": "PONG-RESTING-LIMIT -- delta-mapped resting-limit-at-level entry mechanism study, "
               "2026-07-17 J-directed brainstorm-to-evidence. ANALYSIS ONLY. "
               "Source: backtest/tools/pong_resting_limit_study.py.",
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "preflight": pf,
        "prereg_path": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "grid": {"cancel_rules": [c[0] for c in CANCEL_RULES], "exit_shapes": [e["label"] for e in EXIT_SHAPES],
                "entry_zone_width": ENTRY_ZONE_WIDTH, "qty": QTY},
        "accounts": accounts_out,
        "verdict": {"any_ship_ready_overall": any_ship_ready_overall,
                   "safe_ship_ready": accounts_out["safe"]["verdict"]["any_ship_ready"],
                   "bold_ship_ready": accounts_out["bold"]["verdict"]["any_ship_ready"]},
        "disclosures": [
            "MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this "
            "candidate mechanism, which does not exist in production.",
            "wall-v1 timestamp convention throughout (SPY+options share a year-round-fixed-offset "
            "storage artifact, lib/et_frame.py) -- internally consistent SPY-to-option joins, but "
            "winter-month (EST) wall-clock labels can be off by up to 1h vs true ET; VIX lookups "
            "inherit the same skew against the SPY/option clock even though VIX's own storage is "
            "genuinely correct (a coarse IV proxy, low-materiality).",
            "Entry-zone width ($0.50) and level set are FIXED, not swept -- see the prereg's "
            "mechanism_spec.entry_zone.provenance for why (interacts with the one-slot-per-day state "
            "machine, unlike a simple post-filter).",
            "Delta is Black-Scholes-MODELED (lib.pricing.black_scholes, VIX-derived IV) -- OPRA bars "
            "carry no greeks; this is the house standard, no empirical-greeks alternative exists in "
            "the local cache.",
            "one_position_at_a_time is enforced at the ENTRY-ATTEMPT level only (no new arm while a "
            "prior order is pending or a prior fill's own exit is still open is NOT separately "
            "enforced -- exit duration is exit-shape-dependent and evaluated as a post-filter of a "
            "shape-agnostic mining pass) -- a disclosed simplification, not full position-slot realism.",
            "Adverse-selection classification (bounce vs slice_through) uses a 3-bar/15-min window "
            "after fill with a 10c break margin -- a disclosed, un-swept convention (not itself a "
            "grid axis this study adjudicates).",
            "Control (confirmation-entry) is scoped to the SAME (date, level) episode, not a full "
            "independent orchestrator/gate-stack run -- isolates EXECUTION MECHANISM specifically, "
            "per the task's own framing; block_level_rejection and other production gates are a "
            "DIFFERENT, separately-provenanced axis, out of scope here (same carve-out zone-"
            "rejection-band-2026-07-17 used for the same gate).",
            "qty=3 fixed BOTH accounts (a disclosed deviation from each account's own live qty knob, "
            "per the task's explicit instruction for apples-to-apples comparability in this study).",
            "min_entry_premium floor (0.30, both accounts) applied against P(L) (candidate) and the "
            "raw entry-bar OPEN premium (control); a signal below floor is dropped and counted "
            "(floor_skip), never imputed (C7).",
            "Null-sanity draw count capped at 40 per cell and cached by (exit_shape, capped_n) across "
            "cancel_rule cells sharing it; NULL_SEEDS reduced to 10 (vs zone study's 20) given this "
            "study's 4x larger grid -- disclosed efficiency simplification, not a per-cell-exact null.",
            "ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local; matches "
            "the 6-8-worker-ceiling / OPRA-cache-deadlock lesson.",
        ],
        "runtime_seconds": elapsed_total,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({elapsed_total}s total)")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# PONG resting-limit-at-level study -- PONG-RESTING-LIMIT-2026-07-17")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/pong_resting_limit_study.py`. "
             f"Pre-reg: `{out['prereg_path']}`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE RUN -- reduced date range/seeds, pipeline verification only, "
                 "NOT a decision-grade result.**")
    L.append("")
    for label in ("safe", "bold"):
        a = out["accounts"][label]
        L.append(f"## {label.upper()}")
        L.append("")
        L.append(f"Tier **{a['tier_label']}** (so={a['strike_offset']}), equity=${a['equity_live_verified']}, "
                 f"qty={a['qty']}, time_stop={a['time_stop_et']}.")
        L.append("")
        L.append("### Mining summary (per cancel rule)")
        L.append("")
        L.append("| cancel_rule | arm_events | filled | canceled | unfilled_expired | no_local_bars | bounce | slice_through |")
        L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
        for rule, ms in a["mining_summary"].items():
            L.append(f"| {rule} | {ms['n_arm_events']} | {ms['n_filled']} | {ms['n_canceled']} | "
                     f"{ms['n_unfilled_expired']} | {ms['n_no_local_bars']} | {ms['n_bounce']} | {ms['n_slice_through']} |")
        L.append("")
        asr = a["adverse_selection_split_raw_no_cancel"]
        L.append(f"**ADVERSE-SELECTION SPLIT (raw, no_cancel population): bounce n={asr['n_bounce']}, "
                 f"slice_through n={asr['n_slice_through']}, slice_through_share={asr['slice_through_share']}.**")
        L.append("")
        cc = a["control_confirmation_summary"]
        L.append(f"Control: {cc['n_episode_ids']} distinct (date,level) episode_ids examined, "
                 f"{cc['n_confirmation_triggered']} would have confirmation-triggered under current engine semantics.")
        L.append("")
        cs = a["control_sanity_disclosure"]
        L.append(f"Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean={cs['is_delta_mean']}, "
                 f"oos_delta_mean={cs['oos_delta_mean']}, wf_delta={cs['wf_delta']}, ladder={cs['ladder_verdict']}.")
        L.append("")
        L.append("### Per-cell table (cancel_rule x exit_shape)")
        L.append("")
        L.append("| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |")
        L.append("|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|")
        for key, c in a["cells"].items():
            d = a["decisions"][key]
            L.append(f"| {key} | {c['n']} | {c['n_is']}/{c['n_oos']} | ${c['is_delta_mean']} | ${c['oos_delta_mean']} | "
                     f"{c['wf_delta']} | {c['verdict_ladder']} | {c['n_bounce_filled']}/${c['bounce_delta_mean']} | "
                     f"{c['n_slice_filled']}/${c['slice_delta_mean']} | {c['anchor_no_regression']} | "
                     f"{c['bh_fdr_survivor']} | {d['ship_ready']} |")
        L.append("")
        v = a["verdict"]
        if v["any_ship_ready"]:
            L.append(f"**{label.upper()} SHIP-READY: {v['ship_ready_cells']}. Winner: {v['winner']}.**")
        else:
            cc2 = a["cells"][v["closest_cell"]]
            L.append(f"**{label.upper()}: NULL RESULT (KILL).** Closest cell: `{v['closest_cell']}` "
                     f"({v['closest_cell_gates_passed']}/5 gates, verdict_ladder={v['closest_cell_verdict_ladder']}, "
                     f"n={cc2['n']}, IS=${cc2['is_delta_mean']}, OOS=${cc2['oos_delta_mean']}) -- "
                     f"fails: {v['closest_cell_fails']}.")
        L.append("")
    L.append("## Overall verdict")
    L.append("")
    ov = out["verdict"]
    L.append(f"any_ship_ready_overall={ov['any_ship_ready_overall']} (safe={ov['safe_ship_ready']}, bold={ov['bold_ship_ready']})")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
