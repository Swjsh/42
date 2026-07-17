"""zone_rejection_band_study.py -- ZONE-REJECTION-BAND (2026-07-17).

J directive, 2026-07-17 10:40 ET (verbatim): "it was within cents!! the engine needs to
trade this. fix it. levels are not ever exact to the penny! its zones!!"

INCIDENT: 10:15 ET, SPY bounced to 747.27 and rejected -- 61c shy of PDL 747.88, $1.15
shy of the engine's nearest MEMORY_RES level (748.42). backtest/lib/filters.py#
detect_level_rejection requires bar.high > level (exact pierce) -- zero triggers fired on
EITHER account (automation/state/core-decisions.jsonl 2026-07-17T10:15:0[34], triggers_
fired=[] on both) despite full ribbon+HTF bear alignment. Prior art: detect_wick_rejection_
bearish (2026-05-10, J's 4/29 fix) already tolerates the PIERCE side; the APPROACH side
(never reaches the level at all) has no trigger of any kind. This studies and, if it
clears, ships the missing mirror.

Frozen pre-registration: analysis/recommendations/prereg-zone-rejection-band-2026-07-17.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift).

METHOD (full detail in the frozen prereg -- summarized here):
  * SIGNAL MINING reuses lib.orchestrator.run_backtest -- the SAME full historical bar-walk
    engine backtest/tools/_signal_cache.py uses to build the canonical ribbon_ride cohort
    (ribbon/HTF/VIX + evaluate_bearish_setup/evaluate_bullish_setup + the FULL gate stack,
    including block_level_rejection -- gates.py's GATE_ORDER table cross-references these
    exact orchestrator.py line numbers, confirming this is the SAME logic, not a parallel
    implementation). Unlike _signal_cache.py's L2_PATCH (loosened gates for unrelated
    purposes), this study feeds each account's REAL, UNMODIFIED live params.json so control
    and candidate both reflect what the actual engine does today.
  * CONTROL = the unmodified, currently-shipped detect_level_rejection (exact pierce).
  * CANDIDATE = an IN-PROCESS monkeypatch of filters.detect_level_rejection for the
    duration of one run (never touches the checked-in file) that (a) returns the ORIGINAL
    pierce result unchanged whenever it fires (guarantees byte-identical behavior on every
    already-covered bar) and (b) falls through to a proximity-band check -- bar.high within
    an UMBRELLA Z of a level from below, red close, level never reached -- when the pierce
    trigger is silent. Umbrella Z = max($1.00, 0.3xATR14-5m-at-bar), a per-bar dynamic value
    guaranteed to be a superset of every one of the 8 frozen Z grid cells; each cell is then
    a POST-FILTER of the one umbrella fire-log by the fire's own recorded proximity/ATR.
  * EPISODE ATTRIBUTION (frozen prereg's own definition, reusing WF-GATE-METHODOLOGY-
    2026-07-16.md's matched-episode delta_i): per (date, direction) ordinal slot --
    unchanged (identical entry_ts both sides) -> delta_i=0, not replayed; new (candidate-
    only slot) -> delta_i = pnl_candidate - 0; shifted (both sides, different entry_ts) ->
    delta_i = pnl_candidate - pnl_control, BOTH replayed through the IDENTICAL SS-B lineage
    (never orchestrator's own legacy internal P&L).
  * REPLAY reuses structure_stop_study.SS_B_SHAPE / replay_structure_aware /
    structure_stop_signal_time and ribbon_ride_strike_exit_ab.fetch_entry_and_bars (real
    OPRA local-cache bars only, C7 -- unrecoverable episodes are dropped and counted, never
    imputed), exactly the SS-B lineage every study this week used.
  * BOTH ACCOUNTS tested independently (C29) -- Safe (ATM tier, block_level_rejection=True
    already armed -- disclosed interaction in the prereg) and Bold (OTM-3 tier,
    block_level_rejection=False).
  * GATES: the frozen ab_delta_per_trade_v2026_07_16 WF form (WF-GATE-METHODOLOGY-2026-07-
    16.md) + BH-FDR (autoresearch.ribbon_rejection_wick_battery.bh_fdr, alpha=0.10) across
    all 16 (8 cells x 2 accounts) test statistics this run.

ANALYSIS ONLY. No params/config/trading-path/filters.py file touched. No orders placed.
Any SHIP (adding the validated branch to filters.py) is a SEPARATE, later, clock-gated step
(no engine edit before 16:00 ET, per CLAUDE.md mid-session-edit doctrine) -- never inside
this script.

Run: backtest/.venv/Scripts/python.exe backtest/tools/zone_rejection_band_study.py [--smoke]
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
from lib.orchestrator import run_backtest                                 # noqa: E402
from autoresearch.runner import load_data                                 # noqa: E402
import autoresearch.strategy_space_grind as g                             # noqa: E402
import structure_stop_study as sss                                        # noqa: E402
import ribbon_ride_strike_exit_ab as rrse                                 # noqa: E402
from autoresearch.null_baseline import random_entry_null                  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402
import strike_selection as ssel                                           # noqa: E402

SMOKE = "--smoke" in sys.argv

PREREG = REPO / "analysis" / "recommendations" / "prereg-zone-rejection-band-2026-07-17.json"
EXPECTED_PREREG_SHA16 = "0f799f46e5dc7ab3"
EXPECTED_PREREG_VERSION = 1

OUT_JSON = REPO / "analysis" / "recommendations" / ("zone-rejection-band-2026-07-17-SMOKE.json" if SMOKE
                                                     else "zone-rejection-band-2026-07-17.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("zone-rejection-band-2026-07-17-SMOKE.md" if SMOKE
                                                   else "zone-rejection-band-2026-07-17.md")

IS_START = dt.date(2025, 1, 1)
OOS_BOUNDARY = dt.date(2026, 1, 1)
# Latest exact-match full-history master on disk this session (see runner.load_data's
# candidate-file convention -- an exact (start,end) filename match is required for the
# 2025-01-01-rooted window; the newer rolling append files only start 2026-05-19). SPY has
# a 2026-07-14 master but VIX's matching master stops at 2026-07-08 -- both files must
# exist for load_data to pick the pair, so 2026-07-08 is the true latest usable end date.
DATA_END = dt.date(2026, 7, 8)

FIXED_Z = [0.15, 0.30, 0.50, 0.75, 1.00]
ATR_MULT_Z = [0.1, 0.2, 0.3]
Z_UMBRELLA_FIXED = max(FIXED_Z)     # 1.00
Z_UMBRELLA_ATR_MULT = max(ATR_MULT_Z)  # 0.3
MIN_ENTRY_PREMIUM = 0.30
NULL_SEEDS = 3 if SMOKE else 20

_ORIGINAL_DETECT_LEVEL_REJECTION = filters_mod.detect_level_rejection

ACCOUNTS = {
    "safe": {
        "params_path": REPO / "automation" / "state" / "params.json",
        "tiers": ssel.V15_SAFE_TIERS,
        "qty": 3,
    },
    "bold": {
        "params_path": REPO / "automation" / "state" / "aggressive" / "params.json",
        "tiers": ssel.V15_BOLD_TIERS,
        "qty": 5,
    },
}

# Live-verified this session (mcp__alpaca__get_account_info / mcp__alpaca_aggressive__get_account_info)
LIVE_EQUITY = {"safe": 1485.31, "bold": 1963.04}


def log(msg: str) -> None:
    print(f"[zone-rejection-band] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT -- never run a drifted spec
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
# ATR(14, 5m) -- precomputed once, looked up by bar timestamp inside the candidate detector
# ---------------------------------------------------------------------------------------------
def compute_atr14_5m(spy_df: pd.DataFrame) -> dict:
    df = spy_df.sort_values("timestamp_et").reset_index(drop=True)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    ts = df["timestamp_et"]
    if hasattr(ts, "dt") and ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    return {pd.Timestamp(t): (float(a) if pd.notna(a) else None) for t, a in zip(ts, atr)}


def _norm_ts(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


# ---------------------------------------------------------------------------------------------
# CANDIDATE DETECTOR -- pierce-preserving umbrella zone-approach widening
# ---------------------------------------------------------------------------------------------
def make_candidate_detector(atr_by_ts: dict, fire_log: dict):
    def _candidate(bar, levels_active):
        pierced = _ORIGINAL_DETECT_LEVEL_REJECTION(bar, levels_active)
        if pierced is not None:
            return pierced
        if not levels_active:
            return None
        high = float(bar["high"])
        openp = float(bar["open"])
        close = float(bar["close"])
        if close >= openp:
            return None  # red-close requirement (rejection intent), frozen grid rule
        ts_key = pd.Timestamp(_norm_ts(bar["timestamp_et"]))
        atr = atr_by_ts.get(ts_key)
        z_umbrella = Z_UMBRELLA_FIXED
        if atr is not None:
            z_umbrella = max(z_umbrella, Z_UMBRELLA_ATR_MULT * atr)
        candidates = [(lvl, lvl - high) for lvl in levels_active if lvl > high and (lvl - high) <= z_umbrella]
        if not candidates:
            return None
        lvl, gap = min(candidates, key=lambda x: x[1])
        fire_log[ts_key] = {"level": float(lvl), "proximity_cents": float(round(gap, 4)),
                            "atr_at_fire": atr}
        return float(round(lvl, 2))
    return _candidate


def _nearest_fire(fire_log: dict, entry_ts: dt.datetime, tolerance_minutes: int = 10):
    key = pd.Timestamp(entry_ts)
    if key in fire_log:
        return fire_log[key]
    best, best_dist = None, None
    tol = dt.timedelta(minutes=tolerance_minutes)
    for k, v in fire_log.items():
        d = abs(k.to_pydatetime() - entry_ts) if hasattr(k, "to_pydatetime") else abs(k - entry_ts)
        if d <= tol and (best_dist is None or d < best_dist):
            best, best_dist = v, d
    return best


# ---------------------------------------------------------------------------------------------
# MINING -- one control + one umbrella-candidate run per account
# ---------------------------------------------------------------------------------------------
def _bear_trades(trades):
    return [t for t in trades if t.side == "P" and "BS_FALLBACK" not in str(t.setup)]


def tier_for_equity(tiers, equity: float):
    for t in tiers:
        if t.equity_min <= equity < t.equity_max:
            return t.strike_offset, t.label
    last = tiers[-1]
    return last.strike_offset, last.label


def mine_account(label: str, cfg: dict, spy_full: pd.DataFrame, vix_full: pd.DataFrame,
                 atr_by_ts: dict, start_date: dt.date, end_date: dt.date) -> dict:
    raw_params = json.loads(cfg["params_path"].read_text(encoding="utf-8-sig"))
    p = g._strip_strike_keys(raw_params)
    p["use_real_fills"] = True
    equity = LIVE_EQUITY[label]
    strike_offset, tier_label = tier_for_equity(cfg["tiers"], equity)
    time_stop_et = dt.datetime.strptime(raw_params.get("time_stop_et", "15:50"), "%H:%M").time()

    common_kwargs = dict(
        start_date=start_date, end_date=end_date, use_real_fills=True, params_overrides=p,
        enable_bullish=True, initial_equity=equity, strike_offset=strike_offset,
        premium_stop_pct=-0.50, premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,
    )

    t0 = _time_mod.time()
    ctrl_res = run_backtest(spy_full, vix_full, **common_kwargs)
    control_trades = _bear_trades(ctrl_res.trades)
    log(f"[{label}] control (tier={tier_label} so={strike_offset}): {len(control_trades)} bear trades "
        f"({round(_time_mod.time()-t0,1)}s)")

    fire_log: dict = {}
    candidate_fn = make_candidate_detector(atr_by_ts, fire_log)
    filters_mod.detect_level_rejection = candidate_fn
    try:
        t0 = _time_mod.time()
        cand_res = run_backtest(spy_full, vix_full, **common_kwargs)
    finally:
        filters_mod.detect_level_rejection = _ORIGINAL_DETECT_LEVEL_REJECTION
    candidate_trades = _bear_trades(cand_res.trades)
    log(f"[{label}] candidate: {len(candidate_trades)} bear trades, {len(fire_log)} zone-branch fires "
        f"({round(_time_mod.time()-t0,1)}s)")

    return {
        "control_trades": control_trades, "candidate_trades": candidate_trades, "fire_log": fire_log,
        "strike_offset": strike_offset, "tier_label": tier_label, "equity": equity,
        "time_stop_et": time_stop_et, "qty": cfg["qty"], "params": p,
    }


# ---------------------------------------------------------------------------------------------
# EPISODE ATTRIBUTION -- per the frozen prereg's ordinal (date,direction) matching
# ---------------------------------------------------------------------------------------------
def attribute_episodes(control_trades, candidate_trades) -> dict:
    def by_date(trades):
        d: dict = {}
        for t in sorted(trades, key=lambda x: _norm_ts(x.entry_time_et)):
            dd = _norm_ts(t.entry_time_et).date()
            d.setdefault(dd, []).append(t)
        return d

    c_by_date = by_date(control_trades)
    k_by_date = by_date(candidate_trades)
    all_dates = sorted(set(c_by_date) | set(k_by_date))
    unchanged_n = 0
    new_eps: list = []
    shifted_eps: list = []
    control_only_excess = 0  # diagnostic only -- out of the frozen prereg's scope, disclosed not gated

    for d in all_dates:
        c_list = c_by_date.get(d, [])
        k_list = k_by_date.get(d, [])
        n = max(len(c_list), len(k_list))
        for i in range(n):
            c_t = c_list[i] if i < len(c_list) else None
            k_t = k_list[i] if i < len(k_list) else None
            if c_t is not None and k_t is not None:
                if _norm_ts(c_t.entry_time_et) == _norm_ts(k_t.entry_time_et):
                    unchanged_n += 1
                else:
                    shifted_eps.append((d, i, c_t, k_t))
            elif k_t is not None and c_t is None:
                new_eps.append((d, i, k_t))
            elif c_t is not None and k_t is None:
                control_only_excess += 1

    return {"unchanged_n": unchanged_n, "new": new_eps, "shifted": shifted_eps,
           "control_only_excess": control_only_excess}


# ---------------------------------------------------------------------------------------------
# REPLAY -- SS-B lineage, identical for control and candidate sides of a shifted episode
# ---------------------------------------------------------------------------------------------
def replay_trade(trade, so: int, qty: int, time_stop_et: dt.time, spy_by_date: dict):
    entry_ts = _norm_ts(trade.entry_time_et)
    date = entry_ts.date()
    fetched = rrse.fetch_entry_and_bars(float(trade.entry_spot), trade.side, date, entry_ts, so,
                                        old_semantics=False)
    if fetched is None:
        return None, "no_local_bars"
    entry_premium, walk_bars = fetched
    if entry_premium < MIN_ENTRY_PREMIUM:
        return None, "floor_skip"
    if not walk_bars:
        return None, "no_local_bars"
    ss_time = None
    if trade.rejection_level is not None:
        day_bars = spy_by_date.get(date)
        if day_bars is not None:
            sub = day_bars[day_bars["timestamp_et"] >= entry_ts]
            ss_time = sss.structure_stop_signal_time(sub, trade.side, float(trade.rejection_level),
                                                      sss.STRUCTURE_BUFFER["SS-B"])
    r = sss.replay_structure_aware(entry_premium, trade.side, qty, walk_bars, ss_time, sss.SS_B_SHAPE,
                                   time_stop_et)
    return r["pnl"], None


def build_delta_population(mined: dict, fire_log: dict, spy_by_date: dict) -> list[dict]:
    """Replays every new/shifted episode ONCE (not per Z cell) and records its raw
    proximity_cents/atr_at_fire so each of the 8 grid cells can post-filter membership."""
    episodes = attribute_episodes(mined["control_trades"], mined["candidate_trades"])
    so, qty, time_stop_et = mined["strike_offset"], mined["qty"], mined["time_stop_et"]
    pop: list[dict] = []
    n_dropped = {"no_local_bars": 0, "floor_skip": 0}

    for date, ordinal, k_t in episodes["new"]:
        pnl_c, err = replay_trade(k_t, so, qty, time_stop_et, spy_by_date)
        if pnl_c is None:
            n_dropped[err] += 1
            continue
        fire = _nearest_fire(fire_log, _norm_ts(k_t.entry_time_et))
        pop.append({"kind": "new", "date": str(date), "entry_ts": str(_norm_ts(k_t.entry_time_et)),
                   "delta": round(pnl_c, 2), "proximity_cents": fire["proximity_cents"] if fire else None,
                   "atr_at_fire": fire["atr_at_fire"] if fire else None})

    for date, ordinal, c_t, k_t in episodes["shifted"]:
        pnl_c, err_c = replay_trade(k_t, so, qty, time_stop_et, spy_by_date)
        pnl_x, err_x = replay_trade(c_t, so, qty, time_stop_et, spy_by_date)
        if pnl_c is None or pnl_x is None:
            n_dropped[err_c or err_x] += 1
            continue
        fire = _nearest_fire(fire_log, _norm_ts(k_t.entry_time_et))
        pop.append({"kind": "shifted", "date": str(date), "entry_ts": str(_norm_ts(k_t.entry_time_et)),
                   "delta": round(pnl_c - pnl_x, 2), "proximity_cents": fire["proximity_cents"] if fire else None,
                   "atr_at_fire": fire["atr_at_fire"] if fire else None})

    log(f"delta population: {len(pop)} episodes ({sum(1 for e in pop if e['kind']=='new')} new, "
        f"{sum(1 for e in pop if e['kind']=='shifted')} shifted), dropped={n_dropped}, "
        f"unchanged={episodes['unchanged_n']}, control_only_excess={episodes['control_only_excess']}")
    return pop, episodes["unchanged_n"], episodes["control_only_excess"], n_dropped


# ---------------------------------------------------------------------------------------------
# PER-CELL METRICS (frozen ab_delta_per_trade_v2026_07_16 WF form) + BH-FDR + null sanity
# ---------------------------------------------------------------------------------------------
def cell_membership(pop: list[dict], label: str, z_value: float, is_atr: bool) -> list[dict]:
    out = []
    for e in pop:
        if e["proximity_cents"] is None:
            continue
        if is_atr:
            atr = e["atr_at_fire"]
            if atr is None or e["proximity_cents"] > z_value * atr:
                continue
        else:
            if e["proximity_cents"] > z_value:
                continue
        out.append(e)
    return out


def cell_metrics(members: list[dict]) -> dict:
    n = len(members)
    if n == 0:
        return {"n": 0, "total_delta": 0.0, "is_delta_mean": None, "oos_delta_mean": None,
               "n_is": 0, "n_oos": 0, "wf_delta": None, "is_delta_positive": None,
               "oos_positive": False, "wf_ge_070": False, "sub_window_stable": False,
               "verdict_ladder": "NO_EPISODES"}
    is_vals = [e["delta"] for e in members if dt.date.fromisoformat(e["date"]) < OOS_BOUNDARY]
    oos_vals = [e["delta"] for e in members if dt.date.fromisoformat(e["date"]) >= OOS_BOUNDARY]
    n_is, n_oos = len(is_vals), len(oos_vals)
    is_mean = (sum(is_vals) / n_is) if n_is else None
    oos_mean = (sum(oos_vals) / n_oos) if n_oos else None
    is_delta_positive = (is_mean is not None and is_mean > 0)
    wf = None
    if is_delta_positive and oos_mean is not None:
        wf = round(oos_mean / is_mean, 4)
    oos_sorted = sorted([e for e in members if dt.date.fromisoformat(e["date"]) >= OOS_BOUNDARY],
                        key=lambda e: e["date"])
    mid = len(oos_sorted) // 2
    sw1 = oos_sorted[:mid]
    sw2 = oos_sorted[mid:]
    sw1_total = sum(e["delta"] for e in sw1)
    sw2_total = sum(e["delta"] for e in sw2)
    n_negative_halves = sum(1 for tot in (sw1_total, sw2_total) if tot < 0)
    oos_delta_positive = bool(oos_mean is not None and oos_mean > 0)
    if is_delta_positive and wf is not None and wf >= 0.70:
        ladder = "PASS"
    elif is_delta_positive and (wf is None or wf < 0.70):
        ladder = "FAIL_WF_BELOW_BAR"
    elif (not is_delta_positive) and not oos_delta_positive:
        ladder = "FAIL_NO_IMPROVEMENT"
    else:  # not is_delta_positive and oos_delta_positive
        ladder = "INSUFFICIENT_REGIME_SHIFT"
    return {
        "n": n, "total_delta": round(sum(e["delta"] for e in members), 2),
        "is_delta_mean": round(is_mean, 2) if is_mean is not None else None,
        "oos_delta_mean": round(oos_mean, 2) if oos_mean is not None else None,
        "n_is": n_is, "n_oos": n_oos, "wf_delta": wf, "is_delta_positive": is_delta_positive,
        "oos_positive": bool(oos_mean is not None and oos_mean * n_oos > 0),
        "wf_ge_070": bool(wf is not None and wf >= 0.70),
        "sub_window_stable": bool(len(oos_sorted) > 0 and n_negative_halves <= 1),
        "verdict_ladder": ladder,
    }


def anchor_no_regression(pop: list[dict], j_anchor_dates: set) -> bool:
    """PASS unless a new/shifted episode lands on one of the 7 J-anchor trade dates
    (pierce-preservation guarantees the candidate cannot alter an anchor's OWN entry
    unless that SAME day also independently produces a new/shifted zone episode)."""
    return not any(e["date"] in j_anchor_dates for e in pop)


def make_null_sim_fn(so: int, fixed_qty: int, time_stop_et: dt.time, spy_by_date: dict):
    def _sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level, triggers_fired,
             side, qty, setup, premium_stop_pct, strike_offset):
        entry_ts = _norm_ts(entry_bar["timestamp_et"])
        date = entry_ts.date()
        entry_spot = float(entry_bar["close"])
        fetched = rrse.fetch_entry_and_bars(entry_spot, side, date, entry_ts, so, old_semantics=False)
        if fetched is None:
            return None
        entry_premium_raw, norm_bars = fetched
        if entry_premium_raw < MIN_ENTRY_PREMIUM:
            return None
        ss_time = None
        if rejection_level is not None:
            day_bars = spy_by_date.get(date)
            if day_bars is not None:
                sub = day_bars[day_bars["timestamp_et"] >= entry_ts]
                ss_time = sss.structure_stop_signal_time(sub, side, float(rejection_level),
                                                          sss.STRUCTURE_BUFFER["SS-B"])
        r = sss.replay_structure_aware(entry_premium_raw, side, fixed_qty, norm_bars, ss_time,
                                       sss.SS_B_SHAPE, time_stop_et)
        return SimpleNamespace(dollar_pnl=r["pnl"])
    return _sim


def empirical_p_null(real_per_trade, null_by_seed: list[float]) -> float:
    if real_per_trade is None or not null_by_seed:
        return 1.0
    ge = sum(1 for v in null_by_seed if v >= real_per_trade)
    return round((1 + ge) / (1 + len(null_by_seed)), 4)


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
J_ANCHOR_DATES = {"2026-04-29", "2026-05-01", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"}

CELLS = [(f"fixed_{z}", z, False) for z in FIXED_Z] + [(f"atr_{m}x", m, True) for m in ATR_MULT_Z]


def main() -> int:
    t_start = _time_mod.time()
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        log("PREREG HASH/VERSION MISMATCH -- refusing to run a drifted spec. Aborting.")
        return 1

    if SMOKE:
        load_start, start_date, end_date = dt.date(2026, 5, 19), dt.date(2026, 6, 1), dt.date(2026, 6, 20)
    else:
        load_start, start_date, end_date = IS_START, IS_START, DATA_END
    log(f"loading SPY/VIX data {load_start}..{DATA_END} ...")
    spy_full, vix_full = load_data(load_start, DATA_END)
    # spy_full/vix_full are passed into run_backtest BELOW EXACTLY as returned by load_data
    # (raw timestamp_et strings) -- orchestrator.py does its OWN pd.to_datetime(..., utc=True)
    # parse internally (orchestrator.py:233), which correctly interprets the embedded UTC
    # offset. A SEPARATE, naive-normalized copy is used for every lookup structure THIS
    # script owns (ATR, spy_by_date, rth-for-null, fire-log keys, entry_ts matching) -- never
    # feeding a tz-stripped frame into run_backtest itself (that would silently mis-localize
    # naive-ET as UTC inside orchestrator's own utc=True parse -- a 4-5h shift bug).
    spy_naive = spy_full.copy()
    spy_naive["timestamp_et"] = pd.to_datetime(spy_naive["timestamp_et"])
    if spy_naive["timestamp_et"].dt.tz is not None:
        spy_naive["timestamp_et"] = spy_naive["timestamp_et"].dt.tz_localize(None)
    spy_naive["date"] = spy_naive["timestamp_et"].dt.date
    spy_by_date = {d: gdf.reset_index(drop=True) for d, gdf in spy_naive.groupby("date")}
    log(f"computing ATR(14,5m) over {len(spy_naive)} bars ...")
    atr_by_ts = compute_atr14_5m(spy_naive)

    accounts_out: dict = {}
    for label, cfg in ACCOUNTS.items():
        mined = mine_account(label, cfg, spy_full, vix_full, atr_by_ts, start_date, end_date)
        pop, unchanged_n, control_only_excess, n_dropped = build_delta_population(
            mined, mined["fire_log"], spy_by_date)

        cells_out: dict = {}
        bh_input: list[dict] = []
        null_cache: dict = {}
        for cell_label, z_value, is_atr in CELLS:
            members = cell_membership(pop, cell_label, z_value, is_atr)
            metrics = cell_metrics(members)
            metrics["anchor_no_regression"] = anchor_no_regression(members, J_ANCHOR_DATES)

            per_trade_mean = (metrics["total_delta"] / metrics["n"]) if metrics["n"] else None
            null_key = min(metrics["n"], 40)  # cap draw-count growth; disclosed simplification
            if null_key not in null_cache and null_key > 0:
                sim_fn = make_null_sim_fn(mined["strike_offset"], mined["qty"], mined["time_stop_et"],
                                          spy_by_date)
                rth = spy_naive[(spy_naive["timestamp_et"].dt.time >= dt.time(9, 30)) &
                               (spy_naive["timestamp_et"].dt.time <= dt.time(16, 0))].reset_index(drop=True)
                null_res = random_entry_null(
                    rth=rth, n_signals=null_key, n_call=0, n_put=null_key,
                    strike_offset=mined["strike_offset"], premium_stop_pct=sss.SS_B_SHAPE["premium_stop_pct"],
                    qty=mined["qty"], entry_gate=(dt.time(9, 35), mined["time_stop_et"]), seeds=NULL_SEEDS,
                    setup="ZONE_REJECTION_NULL", sim_fn=sim_fn,
                )
                null_cache[null_key] = null_res.get("per_trade_by_seed", [])
            p_null = empirical_p_null(per_trade_mean, null_cache.get(null_key, []))
            metrics["p_null"] = p_null
            metrics["per_trade_mean"] = round(per_trade_mean, 2) if per_trade_mean is not None else None
            cells_out[cell_label] = metrics
            bh_input.append({"p_null": p_null})

        bh_fdr(bh_input, alpha=FDR_ALPHA)
        for (cell_label, _z, _atr), b in zip(CELLS, bh_input):
            cells_out[cell_label]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
            cells_out[cell_label]["bh_rank"] = b["bh_rank"]

        gates: dict = {}
        decisions: dict = {}
        for cell_label, _z, _atr in CELLS:
            c = cells_out[cell_label]
            g_ = {
                "oos_positive": bool(c["oos_positive"]),
                "wf_ge_070": bool(c["wf_ge_070"]),
                "sub_window_stable": bool(c["sub_window_stable"]),
                "anchor_no_regression": bool(c["anchor_no_regression"]),
                "bh_fdr_survivor": bool(c["bh_fdr_survivor"]),
            }
            g_["all_5_pass"] = all(g_.values())
            gates[cell_label] = g_
            fails = [k for k, v in g_.items() if k != "all_5_pass" and not v]
            decisions[cell_label] = {"ship_ready": g_["all_5_pass"] and c["n"] > 0, "fails": fails,
                                     "n": c["n"], "evidence_thin": c["n"] < 15}

        ship_ready_cells = [lbl for lbl, _z, _atr in CELLS if decisions[lbl]["ship_ready"]]
        winner = None
        if ship_ready_cells:
            winner = max(ship_ready_cells, key=lambda lbl: (cells_out[lbl]["oos_delta_mean"] or -1e18,
                                                            cells_out[lbl]["n"]))

        # Honest "closest cell" for the KILL writeup: most gates passed, tie-break by n.
        n_gates_passed = {lbl: sum(1 for k, v in gates[lbl].items() if k != "all_5_pass" and v)
                          for lbl, _z, _atr in CELLS}
        closest_cell = max((lbl for lbl, _z, _atr in CELLS),
                           key=lambda lbl: (n_gates_passed[lbl], cells_out[lbl]["n"]))

        accounts_out[label] = {
            "mined_summary": {"n_control_bear_trades": len(mined["control_trades"]),
                              "n_candidate_bear_trades": len(mined["candidate_trades"]),
                              "n_zone_branch_fires_umbrella": len(mined["fire_log"]),
                              "strike_tier": mined["tier_label"], "strike_offset": mined["strike_offset"],
                              "equity_live_verified": mined["equity"], "qty": mined["qty"],
                              "time_stop_et": str(mined["time_stop_et"])},
            "episode_attribution": {"unchanged_n": unchanged_n, "n_new": sum(1 for e in pop if e["kind"] == "new"),
                                    "n_shifted": sum(1 for e in pop if e["kind"] == "shifted"),
                                    "control_only_excess_diagnostic": control_only_excess,
                                    "n_dropped": n_dropped},
            "cells": cells_out, "gates": gates, "decisions": decisions,
            "verdict": {"any_ship_ready": bool(ship_ready_cells), "ship_ready_cells": ship_ready_cells,
                       "winner": winner, "closest_cell": closest_cell,
                       "closest_cell_gates_passed": n_gates_passed[closest_cell],
                       "closest_cell_fails": decisions[closest_cell]["fails"],
                       "closest_cell_verdict_ladder": cells_out[closest_cell]["verdict_ladder"]},
        }
        log(f"[{label}] VERDICT any_ship_ready={bool(ship_ready_cells)} winner={winner} "
            f"cells={ship_ready_cells}")

    elapsed_total = round(_time_mod.time() - t_start, 1)
    any_ship_ready_overall = any(accounts_out[a]["verdict"]["any_ship_ready"] for a in accounts_out)

    out = {
        "_doc": "ZONE-REJECTION-BAND -- proximity-band bearish level-rejection trigger study, "
               "2026-07-17 J-directed miss. ANALYSIS ONLY. Source: backtest/tools/zone_rejection_band_study.py.",
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "preflight": pf,
        "prereg_path": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "motivating_incident": "2026-07-17 10:15 ET, SPY 747.27 vs PDL 747.88 (61c shy), zero triggers "
                               "both accounts (core-decisions.jsonl confirmed).",
        "z_grid": {"fixed_dollars": FIXED_Z, "atr_relative_multiples": ATR_MULT_Z},
        "accounts": accounts_out,
        "verdict": {"any_ship_ready_overall": any_ship_ready_overall,
                   "safe_ship_ready": accounts_out["safe"]["verdict"]["any_ship_ready"],
                   "bold_ship_ready": accounts_out["bold"]["verdict"]["any_ship_ready"]},
        "disclosures": [
            "MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this "
            "candidate trigger, which does not exist in production.",
            "Umbrella single-pass mining (not 8 separate per-cell orchestrator runs) -- smaller Z cells "
            "are exact post-filters on recorded proximity_cents/atr_at_fire; a disclosed path-dependence "
            "caveat applies to SAME-DAY SEQUENCING after a wide-Z entry (see prereg mining_method_umbrella).",
            "Episode attribution is ordinal (date,direction) matching, not a full state-machine replay "
            "isolated per Z cell -- disclosed simplification, per the frozen prereg.",
            "control_only_excess (ordinal slots where control had MORE same-day bear entries than "
            "candidate) is a diagnostic OUTSIDE the frozen prereg's delta definition -- reported, not "
            "gated, per the frozen document's own scope (new/shifted/unchanged only).",
            "Safe's live block_level_rejection=true gate is threaded through orchestrator.run_backtest's "
            "own params_overrides -- the mined control/candidate populations already reflect its "
            "suppression of single-trigger LEVEL-tier entries; not re-derived separately.",
            "Null-sanity draw count is capped at 40 per cell (n_signals=min(cell_n,40)) and cached by "
            "that capped count across cells sharing it -- disclosed efficiency simplification, not a "
            "per-cell-exact null.",
            "min_entry_premium floor (0.30, both accounts) applied IN-SIM against the raw entry-bar OPEN "
            "premium; a signal below floor is dropped and counted, never imputed (C7).",
            "ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local; matches the "
            "6-8-worker-ceiling / OPRA-cache-deadlock lesson by staying at 1 worker for this cache-bound "
            "workload (same convention every SS-B-lineage study this week used).",
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
    L.append("# Zone-rejection-band study -- ZONE-REJECTION-BAND-2026-07-17")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/zone_rejection_band_study.py`. "
             f"Pre-reg: `{out['prereg_path']}`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE RUN -- reduced date range/seeds, pipeline verification only, "
                 "NOT a decision-grade result.**")
    L.append("")
    L.append(f"**Motivating incident:** {out['motivating_incident']}")
    L.append("")
    for label in ("safe", "bold"):
        a = out["accounts"][label]
        L.append(f"## {label.upper()}")
        L.append("")
        ms = a["mined_summary"]
        L.append(f"Tier **{ms['strike_tier']}** (so={ms['strike_offset']}), equity=${ms['equity_live_verified']}, "
                 f"qty={ms['qty']}, time_stop={ms['time_stop_et']}. Control bear trades: "
                 f"{ms['n_control_bear_trades']}. Candidate bear trades: {ms['n_candidate_bear_trades']}. "
                 f"Umbrella zone-branch fires: {ms['n_zone_branch_fires_umbrella']}.")
        L.append("")
        ea = a["episode_attribution"]
        L.append(f"Episodes: unchanged={ea['unchanged_n']}, new={ea['n_new']}, shifted={ea['n_shifted']}, "
                 f"control_only_excess(diagnostic)={ea['control_only_excess_diagnostic']}, "
                 f"dropped={ea['n_dropped']}.")
        L.append("")
        L.append("| Z cell | n | n_is/n_oos | IS delta/tr | OOS delta/tr | WF | verdict_ladder | anchor_ok | bh_survivor | ship_ready |")
        L.append("|---|--:|--:|--:|--:|--:|---|:--:|:--:|:--:|")
        for cell_label, c in a["cells"].items():
            d = a["decisions"][cell_label]
            L.append(f"| {cell_label} | {c['n']} | {c['n_is']}/{c['n_oos']} | ${c['is_delta_mean']} | "
                     f"${c['oos_delta_mean']} | {c['wf_delta']} | {c['verdict_ladder']} | "
                     f"{c['anchor_no_regression']} | {c['bh_fdr_survivor']} | {d['ship_ready']} |")
        L.append("")
        v = a["verdict"]
        if v["any_ship_ready"]:
            L.append(f"**{label.upper()} SHIP-READY: {v['ship_ready_cells']}. Winner: {v['winner']}.**")
        else:
            cc = v["closest_cell"]
            ccm = a["cells"][cc]
            L.append(f"**{label.upper()}: NULL RESULT (KILL).** Closest cell: `{cc}` "
                     f"({v['closest_cell_gates_passed']}/5 gates passed, verdict_ladder="
                     f"{v['closest_cell_verdict_ladder']}, n={ccm['n']}, IS=${ccm['is_delta_mean']}, "
                     f"OOS=${ccm['oos_delta_mean']}) -- fails: {v['closest_cell_fails']}.")
        L.append("")
    L.append("## Overall verdict")
    L.append("")
    ov = out["verdict"]
    L.append(f"any_ship_ready_overall={ov['any_ship_ready_overall']} "
             f"(safe={ov['safe_ship_ready']}, bold={ov['bold_ship_ready']})")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
