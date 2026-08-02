"""level_target_exit_study.py -- EXECUTION of the FROZEN level-target-exit prereg
(analysis/recommendations/level-target-exit-prereg-2026-07-31.json), overnight 2026-08-02
runner-leg investigation, sub-problem B.

FROZEN PROTOCOL. 144 declared cells (target_rule x max_reach x band x trigger_form x action),
gates G1-G8, BH-FDR q=0.10, IS/OOS walk-forward >=0.70, runner-cohort no-regression at ZERO
tolerance. Nothing here adds, drops, or widens a cell or gate. Where the frozen text is
genuinely ambiguous (one case: step_4's band_source note vs the explicit 4-value band sweep --
see BAND_INTERPRETATION_NOTE below), the literal, structurally-binding `cells.axes` spec is
followed and the ambiguity is disclosed in the output rather than silently resolved.

PATH A ADMISSIBILITY (the prereg's own blocker) is PROVEN by backtest/lib/
reconstruct_levels_asof.py (backtest/tests/test_reconstruct_levels_asof.py, 6/6 green,
causality vary-and-assert RED-proofed, real-data ground truth against the 2026-07-31 anchor
trade). This script is its consumer -- the actual population-scale run. See that module's
docstring for the full admissibility argument and its disclosed scope (shelf + intraday
levels only; level_memory + premarket-curated levels NOT reconstructed).

ENGINE: backtest/lib/exit_manager_walk / automation/state/fleet/exit_manager.plan_exit_actions
drives the INCUMBENT control -- the REAL production decision core, never re-implemented. The
level-target OVERLAY mirrors backtest/tools/exit_grid_n1_20260731_746c.py's walk_level_target
pattern exactly (production core checked FIRST each tick, level check second, additive) --
generalized from that script's one fixed target to a per-position reconstructed level universe.

RESOLUTION DISCLOSURE: the population-wide option-bar cache (backtest/data/options/*.csv,
14,344 files) is 5-MINUTE bars, not the 1-minute cache exit_grid_n1 had for its single anchor
trade. This is the SAME established convention exit_manager_walk.py's own docstring names
("5-minute for historical backtests where only 5-min OPRA is cached") -- not invented here.
It widens the harness-vs-live parity gap (G8) beyond the single-trade study's own +17.3%
figure; the parity check below re-measures it fresh on this population, at this resolution.

POPULATION: automation/state/fills-ledger.jsonl, ALL_LIVE_ARMS (all 6 arms), FIFO-paired via
exit_shape_parity_study.reconstruct_positions (imported, not reimplemented). Every exclusion
is counted, never silently dropped (C7/L241).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts",
           REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_manager as em                                   # noqa: E402
import strategies as strat_mod                               # noqa: E402
import fleet_executor as fx                                  # noqa: E402
from exit_manager_walk import (                              # noqa: E402
    walk_exit_manager, last_closed_bar_close_at, DEFAULT_EXIT_SLIPPAGE,
)
import reconstruct_levels_asof as rla                        # noqa: E402
import exit_shape_parity_study as esp                        # noqa: E402

STATE = REPO / "automation" / "state"
OPT_DIR = REPO / "backtest" / "data" / "options"
DAILY_CACHE = REPO / "backtest" / "data" / "spy_daily_bars_real_2024-10-01_2026-08-01.json"
FIVEMIN_CACHE = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
PREREG_PATH = REPO / "analysis" / "recommendations" / "level-target-exit-prereg-2026-07-31.json"
SAMPLING_GAP_PATH = REPO / "analysis" / "pain-ledger" / "sampling-gap.json"   # runner-trail cohort source
OUT_PATH = REPO / "analysis" / "recommendations" / "level-target-exit-2026-08-02.json"

ACCOUNTS = json.loads((STATE / "fleet" / "accounts.json").read_text(encoding="utf-8"))
ARM_BY_ID = {a["id"]: a for a in ACCOUNTS["arms"]}

_SYM_RE = re.compile(r"^SPY\d{6}([CP])\d{8}$")

BAND_INTERPRETATION_NOTE = (
    "step_4_levels_are_ZONES_not_prices.band_source says 'Where level.zone_width is present, "
    "BAND = zone_width/2... Where absent, BAND = the swept default.' Every level this study "
    "reconstructs carries its own zone_width (as does every level the live system writes), "
    "which read literally would make the swept band axis inoperative for 100% of cells -- "
    "collapsing all 4 band cells to an identical threshold and contradicting cells.axes.band's "
    "explicit 4-value sweep and total_cells=144 (which the BH-FDR correction is keyed to). "
    "Resolution taken (disclosed, not silently picked): BAND = the swept axis value directly "
    "for all 4 band cells, per the cells.axes specification, which is the more structurally "
    "binding part of the frozen document. Flagged for adjudication, not improvised past."
)


# ============================================================================================
# 1. POPULATION -- real-fills positions, FIFO-paired, joined to their own fired exit shape
# ============================================================================================

def _side_of_symbol(symbol: str) -> Optional[str]:
    m = _SYM_RE.match(symbol)
    return m.group(1) if m else None


def _strategy_for_setup(setup_name: Optional[str]):
    if not setup_name:
        return None
    su = str(setup_name).strip().upper()
    for strat in strat_mod.REGISTRY:
        if any(su == s.upper() for s in strat.entry_setups):
            return strat
    return None


def _normalize_fleet_row(d: dict) -> Optional[dict]:
    """Fleet arms (automation/state/fleet/{arm}/decisions.jsonl): ENTER_* rows carry a rich
    `placement` dict -- tp1_premium_pct/premium_stop_pct/tp1_qty_fraction/profit_lock_mode/
    stop_mode/trigger_level/entry_px are all logged directly (the ACTUAL fired values)."""
    pl = d.get("placement") or {}
    if not (str(d.get("action", "")).startswith("ENTER") and pl.get("placed") and pl.get("symbol")):
        return None
    return {
        "symbol": pl["symbol"], "setup_name": d.get("setup_name"),
        "tp1_premium_pct": pl.get("tp1_premium_pct"), "premium_stop_pct": pl.get("premium_stop_pct"),
        "tp1_qty_fraction": pl.get("tp1_qty_fraction"), "profit_lock_mode": pl.get("profit_lock_mode"),
        "stop_mode": pl.get("stop_mode"), "trigger_level": pl.get("trigger_level"),
        "entry_px": pl.get("entry_px"),
    }


def _normalize_core_row(d: dict) -> Optional[dict]:
    """Core arms (automation/state/core-decisions.jsonl, heartbeat_core.py's OWN schema --
    DIFFERENT from the fleet's, confirmed by direct read this session): the entry lives under
    `exec` with action=='PLACED' (not 'ENTER_*'), and does NOT log tp1_premium_pct/
    premium_stop_pct/stop_mode/trigger_level/profit_lock_mode at all -- only symbol/setup/
    premium/tp/stop (absolute prices, not pcts) and exit_managed. DISCLOSED FIDELITY GAP: this
    means core positions always resolve stop_mode via the registry default with
    trigger_level=None (ExitState.from_entry's documented fail-safe -> 'premium' mode even if
    the live position actually ran in structure mode) -- never a guess, always the same
    documented fail-safe path the production code itself uses on missing data."""
    ex = d.get("exec") or {}
    if not (d.get("action") == "PLACED" and ex.get("status") == "PLACED" and ex.get("symbol")):
        return None
    return {
        "symbol": ex["symbol"], "setup_name": ex.get("setup") or d.get("setup"),
        "tp1_premium_pct": None, "premium_stop_pct": None, "tp1_qty_fraction": None,
        "profit_lock_mode": None, "stop_mode": None, "trigger_level": None,
        "entry_px": ex.get("premium"),
    }


class _DecisionIndex:
    """Lazy per-arm index of normalized ENTER rows, keyed by symbol -> list[(ts_et_dt, row)].
    Fleet and core arms use DIFFERENT log schemas (see the two normalizers above); this class
    hides that behind one .find() interface returning the common normalized shape."""
    _CORE_ACCOUNT_OF_ARM = {"safe-2": "safe", "bold-2": "bold"}

    def __init__(self):
        self._by_arm: dict = {}

    def _load_fleet(self, arm: str) -> dict:
        p = STATE / "fleet" / arm / "decisions.jsonl"
        idx = defaultdict(list)
        if not p.exists():
            return idx
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                norm = _normalize_fleet_row(d)
                if norm is None:
                    continue
                try:
                    ts = dt.datetime.fromisoformat(d["ts_et"])
                except (KeyError, ValueError):
                    continue
                idx[norm["symbol"]].append((ts, norm))
        return idx

    def _load_core(self, account: str) -> dict:
        p = STATE / "core-decisions.jsonl"
        idx = defaultdict(list)
        if not p.exists():
            return idx
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("account") != account:
                    continue
                norm = _normalize_core_row(d)
                if norm is None:
                    continue
                try:
                    ts = dt.datetime.fromisoformat(d["ts_et"])
                except (KeyError, ValueError):
                    continue
                idx[norm["symbol"]].append((ts, norm))
        return idx

    def find(self, arm: str, symbol: str, entry_ts_utc: str, tol_s: float = 300.0):
        if arm not in self._by_arm:
            acct = self._CORE_ACCOUNT_OF_ARM.get(arm)
            self._by_arm[arm] = self._load_core(acct) if acct else self._load_fleet(arm)
        cands = self._by_arm[arm].get(symbol) or []
        if not cands:
            return None
        entry_dt_utc = dt.datetime.fromisoformat(entry_ts_utc.replace("Z", "+00:00"))
        entry_et = entry_dt_utc.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
        best, best_gap = None, None
        for ts, row in cands:
            ts_naive = ts.replace(tzinfo=None)
            gap = abs((ts_naive - entry_et).total_seconds())
            if gap <= tol_s and (best_gap is None or gap < best_gap):
                best, best_gap = row, gap
        return best


def build_population() -> tuple[list[dict], dict]:
    """Every real-fills round-trip position, joined to the ENTER decision that fired it.
    Returns (positions, exclusion_counts). Nothing imputed -- every exclusion is counted."""
    fills = esp.load_fleet_engine_fills(arms=esp.ALL_LIVE_ARMS)
    raw_positions = esp.reconstruct_positions(fills)
    di = _DecisionIndex()

    excluded = {"bad_symbol": 0, "qty_lt_1": 0, "no_entry_decision_match": 0,
               "no_strategy_resolved": 0}
    out = []
    for p in raw_positions:
        side = _side_of_symbol(p["symbol"])
        qty = int(p["entry_qty"])
        if side is None:
            excluded["bad_symbol"] += 1
            continue
        if qty < 1:
            excluded["qty_lt_1"] += 1
            continue
        decision = di.find(p["arm"], p["symbol"], p["entry_ts_utc"])
        if decision is None:
            excluded["no_entry_decision_match"] += 1
            continue
        setup_name = decision.get("setup_name")
        strat_obj = _strategy_for_setup(setup_name)
        if strat_obj is None:
            excluded["no_strategy_resolved"] += 1
            continue
        base_shape = fx._exit_shape_dict(strat_obj, ARM_BY_ID.get(p["arm"]))
        shape = dict(base_shape)
        for k in ("tp1_premium_pct", "premium_stop_pct", "tp1_qty_fraction",
                  "profit_lock_mode", "stop_mode"):
            if decision.get(k) is not None:
                shape[k] = decision[k]
        trigger_level = decision.get("trigger_level")
        entry_registered = decision.get("entry_px")
        if entry_registered is None:
            entry_registered = p["entry_price"]
        structure_stop_enabled = (str(shape.get("stop_mode")) == "structure"
                                  and trigger_level is not None)
        out.append({
            "arm": p["arm"], "symbol": p["symbol"], "side": side,
            "entry_ts_utc": p["entry_ts_utc"], "date_et": p["date_et"],
            "entry_price_fill": p["entry_price"], "entry_price_registered": float(entry_registered),
            "qty": qty, "exit_shape": shape, "trigger_level": trigger_level,
            "structure_stop_enabled": structure_stop_enabled, "strategy": strat_obj.name,
            "actual_exit_pnl": round(p["actual_exit_pnl"], 2),
            "is_core_arm": p["arm"] in ("safe-2", "bold-2"),
        })
    return out, excluded


# ============================================================================================
# 2. DATA -- option bars (cached, 5-min) + SPY 5m/daily bars for level reconstruction
# ============================================================================================

_OPT_BAR_CACHE: dict = {}   # in-process memo -- symbol -> (df, resolution)


def load_option_bars(symbol: str, date_et: Optional[str] = None,
                     prefer_1min: bool = True) -> "tuple[Optional[pd.DataFrame], str]":
    """RESOLUTION FIX (found + fixed this session): backtest/data/options/*.csv is 5-MINUTE
    bars. A 5-min bar's point-sampled OPEN frequently misses an intra-bar dip/spike a real
    engine tick (fleet: 3-min, core: 1-min, both reading the LIVE NBBO) would have caught --
    verified exactly on SPY260709C00750000/risky-3: the real position stopped out on a dip to
    $0.40 inside a 5-min bar whose own open was $0.52, so the 5-min-bar walk rode straight
    through the stop and posted a large phantom gain. This is a materially BIGGER effect than
    exit_grid_n1's single-trade 1-minute-cache study saw (that study had true 1-min option
    data for its one anchor date). Fix: fetch 1-MINUTE option bars (the SAME real-OPRA REST
    path exit_shape_parity_study.fetch_option_bars already uses elsewhere in this codebase --
    not a new network path) for every position, matching the engine's own tick-level fidelity.
    SPY bars deliberately STAY 5-minute (structure_stop is 5-min-NATIVE by v15.3 design, not
    an approximation -- see exit_manager_walk.last_closed_bar_close_at's docstring).
    Falls back to the cached 5-min CSV, resolution disclosed, only if the 1-min fetch fails.
    Returns (df_or_None, resolution_str) so the caller can report exactly what each position
    actually ran on."""
    if symbol in _OPT_BAR_CACHE:
        return _OPT_BAR_CACHE[symbol]
    result = (None, "none")
    if date_et:
        bars = esp.fetch_option_bars(symbol, date_et)
        if bars:
            rows = []
            for b in bars:
                ts = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                ts_et = ts.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
                rows.append({"timestamp_et": ts_et, "open": b["o"], "high": b["h"],
                            "low": b["l"], "close": b["c"], "volume": b.get("v", 0)})
            if rows:
                df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True)
                result = (df, "1min_rest")
    if result[0] is None:
        p = OPT_DIR / f"{symbol}.csv"
        if p.exists():
            df = pd.read_csv(p)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
            result = (df.sort_values("timestamp_et").reset_index(drop=True), "5min_cache_fallback")
    _OPT_BAR_CACHE[symbol] = result
    return result


def load_spy_bars():
    daily_bars = json.loads(DAILY_CACHE.read_text(encoding="utf-8"))
    five_min = pd.read_csv(FIVEMIN_CACHE)
    five_min["timestamp_et"] = pd.to_datetime(five_min["timestamp_et"]).dt.tz_localize(None)
    return daily_bars, five_min


def spot_at(five_min: pd.DataFrame, as_of_et: dt.datetime) -> Optional[float]:
    sub = five_min.loc[five_min["timestamp_et"] <= as_of_et]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["close"])


# ============================================================================================
# 3. ELIGIBLE-LEVEL SELECTION (frozen detector_specification)
# ============================================================================================

MAX_REACH_SWEEP = (1.5, 3.0, 5.0)
MIN_REACH = 0.25
BAND_SWEEP = (0.0, 0.15, 0.25, 0.40)
TARGET_RULES = ("RULE_A_NEAREST", "RULE_B_SECOND", "RULE_C_STRONGEST")
TRIGGER_FORMS = ("ARM_T_touch", "ARM_C_close5")
ACTIONS = ("ARM_FULL", "ARM_RUNNER_ONLY")


def eligible_levels(levels: list[dict], side: str, spot: float, trigger_level,
                    max_reach: float) -> list[dict]:
    out = []
    for lv in levels:
        price = lv.get("price")
        if price is None or str(lv.get("tier")) != "Active":
            continue
        if side == "C" and not (price > spot):
            continue
        if side == "P" and not (price < spot):
            continue
        if trigger_level is not None and abs(price - float(trigger_level)) < 0.06:
            continue  # exclude the position's own stop-reference level
        dist = abs(price - spot)
        if dist > max_reach or dist < MIN_REACH:
            continue
        out.append(lv)
    return out


def pick_target(elig: list[dict], spot: float, rule: str) -> Optional[dict]:
    if not elig:
        return None
    by_dist = sorted(elig, key=lambda lv: abs(lv["price"] - spot))
    if rule == "RULE_A_NEAREST":
        return by_dist[0]
    if rule == "RULE_B_SECOND":
        return by_dist[1] if len(by_dist) >= 2 else None
    if rule == "RULE_C_STRONGEST":
        return sorted(elig, key=lambda lv: (-lv.get("weight", 0), abs(lv["price"] - spot)))[0]
    raise ValueError(rule)


# ============================================================================================
# 4. THE WALK -- production core FIRST, level overlay SECOND (mirrors exit_grid_n1 exactly)
# ============================================================================================

def walk_position_incumbent(pos: dict, opt_df: pd.DataFrame, spy5: pd.DataFrame) -> dict:
    """The INCUMBENT control -- byte-identical machinery to exit_manager_walk.walk_exit_manager,
    used both as the G1-G8 comparison baseline and as the harness-vs-live parity check (G8)."""
    r = walk_exit_manager(
        symbol=pos["symbol"], side=pos["side"], entry_time_et=pos["_entry_ts_et_naive"],
        entry_premium=pos["entry_price_registered"], qty=pos["qty"], exit_shape=pos["exit_shape"],
        structure_stop_enabled=pos["structure_stop_enabled"], trigger_level=pos["trigger_level"],
        strategy=pos["strategy"], time_stop_et=dt.time(15, 40), opt_df=opt_df,
        ribbon_tick_df=None, five_min_spy_df=spy5)
    pnl = sum((leg.fill_price - pos["entry_price_fill"]) * leg.qty * 100.0 for leg in r.legs)
    return {"pnl": round(pnl, 2), "legs": r.legs, "exit_reason": r.exit_reason,
           "resolved": r.resolved}


def walk_position_level_target(pos: dict, opt_df: pd.DataFrame, spy5: pd.DataFrame,
                               target_price: float, band: float, trigger_form: str,
                               action: str) -> dict:
    """Production core checked FIRST every tick (structure/catastrophe/time/tp1/ribbon/trail),
    THEN the level-target overlay -- additive, mirrors exit_grid_n1_20260731_746c.py's
    walk_level_target verbatim. action=ARM_FULL zeroes tp1_qty_fraction so the level is the
    ONLY take-profit (the incumbent's stop/time-stop machinery still guards the position);
    ARM_RUNNER_ONLY leaves TP1 armed and the level only ever sees the RUNNER's open_qty."""
    shape = dict(pos["exit_shape"])
    if action == "ARM_FULL":
        shape["tp1_qty_fraction"] = 0.0
    state = em.ExitState.from_entry(
        symbol=pos["symbol"], side=pos["side"], entry_premium=pos["entry_price_registered"],
        qty=pos["qty"], exit_shape=shape, strategy=pos["strategy"],
        trigger_level=pos["trigger_level"], structure_stop_enabled=pos["structure_stop_enabled"])

    opt_df = opt_df.reset_index(drop=True)
    entry_ts = pos["_entry_ts_et_naive"]
    after = opt_df.index[opt_df["timestamp_et"] > entry_ts]
    if len(after) == 0:
        return {"pnl": 0.0, "legs": [], "exit_reason": "no_bars_after_entry", "level_fired": False}
    start_idx = int(after[0])
    open_qty = pos["qty"]
    legs = []
    level_fired = False
    is_call = pos["side"] == "C"
    armed = (target_price - band) if is_call else (target_price + band)

    for idx in range(start_idx, len(opt_df)):
        bar = opt_df.iloc[idx]
        ts = bar["timestamp_et"]
        best = worst = float(bar["open"])
        now_et = ts.time()
        closed5 = last_closed_bar_close_at(spy5, ts)

        dec = em.plan_exit_actions(state, best_premium=best, worst_premium=worst,
                                   open_qty=open_qty, now_et=now_et, ribbon_flip_back=False,
                                   time_stop_et=dt.time(15, 40), last_closed_5m_close=closed5)
        state_in, state = state, dec.state
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                px = pos["entry_price_registered"] * (1.0 + state_in.tp1_premium_pct)
            elif a.stage == "runner_target":
                px = pos["entry_price_registered"] * (1.0 + state_in.runner_target_pct)
            elif a.stage in ("trail", "be_stop"):
                px = state.runner_stop_premium
            elif a.stage in ("premium_stop", "profit_lock_floor"):
                px = state_in.runner_stop_premium
            else:  # time_stop / ribbon_flip / structure_stop -- market-style
                px = max(0.01, float(bar["close"]) - DEFAULT_EXIT_SLIPPAGE)
            legs.append({"ts_et": ts, "qty": a.qty, "price": round(px, 4), "stage": a.stage,
                        "reason": a.reason})
            open_qty -= a.qty
        if dec.closes_position or open_qty <= 0:
            break

        hit = False
        spy_row = spy5.loc[spy5["timestamp_et"] == ts]
        if trigger_form == "ARM_T_touch" and not spy_row.empty:
            h, low = float(spy_row.iloc[0]["high"]), float(spy_row.iloc[0]["low"])
            hit = (h >= armed) if is_call else (low <= armed)
        elif trigger_form == "ARM_C_close5" and closed5 is not None:
            hit = (closed5 >= armed) if is_call else (closed5 <= armed)
        if hit:
            px = max(0.01, float(bar["close"]) - DEFAULT_EXIT_SLIPPAGE)
            legs.append({"ts_et": ts, "qty": open_qty, "price": round(px, 4),
                        "stage": "level_target", "reason": f"level_target {target_price} ({trigger_form})"})
            level_fired = True
            open_qty = 0
            break

    if open_qty > 0:
        last = opt_df.iloc[-1]
        legs.append({"ts_et": last["timestamp_et"], "qty": open_qty,
                    "price": round(max(0.01, float(last["close"]) - DEFAULT_EXIT_SLIPPAGE), 4),
                    "stage": "force_close", "reason": "data_exhausted"})

    pnl = sum((leg["price"] - pos["entry_price_fill"]) * leg["qty"] * 100.0 for leg in legs)
    return {"pnl": round(pnl, 2), "legs": legs, "level_fired": level_fired,
           "exit_reason": legs[-1]["reason"] if legs else "n/a"}


if __name__ == "__main__":
    print("module import OK -- run via run_level_target_study.py")
