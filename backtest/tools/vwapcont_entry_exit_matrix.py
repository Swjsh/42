"""vwapcont_entry_exit_matrix.py -- the OWED vwap_continuation entry/exit matrix.

STOP-A ground rule 11: "vwap_continuation is a separate setup path the generic backtest
doesn't emit -> its entry/exit matrix is owed". ribbon_ride got the full T2-T5 + structure-stop
treatment (backtest/tools/t3_entry_matrix.py, t4_exit_matrix.py, t5_confirmatory_matrix.py,
structure_stop_study.py); this is the SAME discipline, scaled down, for vwap_continuation --
the firm's only recency-clean validated edge (SS-B ship 2026-07-09 ported the FULL validated
core cell -0.06/+0.40/0.8/fixed into both lanes; no two-lane drift remains).

Pre-registered FIRST: analysis/recommendations/vwapcont-matrix-preregistration.json (grid,
windows, pass bar, signal-set hash) -- READ IT, this file implements it verbatim, no re-picks.

WHAT THIS DOES:
  1. Regenerates the vwap_continuation signal population BYTE-FOR-BYTE the walk-forward/
     ship-gate convention (autoresearch._edgehunt_vwap_continuation.detect_signals, headline
     cell), extended through the freshest cached OPRA date (2026-07-08). Verifies the hash
     against the frozen pre-registration -- STOPS if it doesn't match.
  2. Loads ATM option bars ONCE per signal (nearest-cache-snap, matches the ship-gate's own
     strike convention) and replays the 24-cell exit grid + 4-cell entry-probe cheaply through
     the LIVE exit_manager.plan_exit_actions decision core -- mirrors t4_exit_matrix.py's own
     "generate once, replay many" architecture.
  3. The structure-stop family (4 of the 24 cells) reuses structure_stop_study.py's
     NormBar/replay_structure_aware verbatim, swapping the level-based breach test for a
     VWAP-based one (autoresearch.infinite_ammo_discovery.session_vwap_asof, the SAME as-of
     formula the vwap_continuation watcher and detector use for entry) -- see the
     pre-registration's structure_definition block for the exact rationale.
  4. PARITY CHECK: replays the control cell through BOTH this bar-replay engine AND
     lib.simulator_real.simulate_trade_real (the C1 fills authority the ratified walk-forward/
     ship-gate studies used) on the OLD (burned) window, and reports the delta honestly --
     mirrors the parity_gate pattern used throughout this codebase.
  5. Real-fills anchor: replays the frozen candidates on actual vwap_continuation fills this
     month (both lanes). Marks INCONCLUSIVE-ANCHOR (does not fabricate a number) if the
     population can't be recovered/is too thin.
  6. Applies the pre-registered pass bar; writes the verdict.

ANALYSIS ONLY. Touches nothing under automation/state/params.json, automation/state/fleet/,
or any trading-path file. Writes only to analysis/recommendations/.

Run: backtest/.venv/Scripts/python.exe backtest/tools/vwapcont_entry_exit_matrix.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix, _normalize_spy, detect_signals, MAX_STRIKE_STEPS, QTY,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts, session_vwap_asof, _nearest_cached_strike, _strike_from_spot,
)
from autoresearch.vwapcont_exit_parity import (  # noqa: E402
    ANCHOR_WINNER_DATES, ANCHOR_LOSER_DATES, simulate_cell_ext,
)
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from exit_manager import plan_exit_actions, TIME_STOP_ET  # noqa: E402
import structure_stop_study as sss  # noqa: E402  (NormBar, replay_structure_aware, et_now, norm_bars_from_esp)
import exit_shape_parity_study as esp  # noqa: E402  (fetch_option_bars -- real 1-min OPRA)

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
PREREG = REPO / "analysis" / "recommendations" / "vwapcont-matrix-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "vwapcont-entry-exit-matrix.json"

WINDOW = (dt.date(2025, 1, 1), dt.date(2026, 7, 8))
OLD_END = dt.date(2026, 5, 15)              # prior studies' end -- burned
FRESH_START = dt.date(2026, 5, 16)          # never-touched fresh tail starts here
OOS_BOUNDARY = "2026-01-01"                 # calendar-year IS/OOS split (matches prior studies)
EXPECTED_SHA16 = "1e7c84bda5f91727"
EXPECTED_PREREG_VERSION = 1

TIME_STOP = TIME_STOP_ET                    # 15:50 ET -- vwap's own / live default (NOT ribbon's 15:40)
BANDS = [("<0.20", 0.0, 0.20), ("0.20-0.50", 0.20, 0.50),
         ("0.50-1.00", 0.50, 1.00), (">1.00", 1.00, 1e9)]

CONTROL_SHAPE_RAW = {"stop": -0.06, "tp1": 0.40, "frac": 0.8, "lock": ["fixed", 0.0]}
RUNNER_TARGET_PCT = 2.5   # held FIXED across the whole grid incl. STRUCT -- not a swept axis (disclosed)
PROFIT_LOCK_ARM_PCT = 0.05


def band_of(p: float) -> str:
    for n, lo, hi in BANDS:
        if lo <= p < hi:
            return n
    return ">1.00"


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ---------------------------------------------------------------------------------------------
# SIGNAL POPULATION (byte-for-byte the walk-forward/ship-gate convention, extended window)
# ---------------------------------------------------------------------------------------------
def _signal_signature(signals, spy) -> list[dict]:
    rows = []
    for s in signals:
        bar = spy.iloc[s.bar_idx]
        rows.append({
            "date": str(bar["timestamp_et"].date()), "time": str(bar["timestamp_et"].time()),
            "side": s.side,
            "stop_level": round(float(s.stop_level), 4) if s.stop_level is not None else None,
            "note": s.note,
        })
    rows.sort(key=lambda r: (r["date"], r["time"], r["side"]))
    return rows


def load_signals():
    print(f"[vwapmx] loading SPY+VIX {WINDOW[0]}..{WINDOW[1]} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(*WINDOW)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    print(f"[vwapmx] {len(signals)} signals over {len(days)} trading days", flush=True)
    return signals, spy, vix, ribbon, days


def preflight(signals, spy) -> dict:
    sig_rows = _signal_signature(signals, spy)
    sha16 = hashlib.sha256(json.dumps(sig_rows, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")
    n_old = sum(1 for r in sig_rows if r["date"] <= OLD_END.isoformat())
    return {
        "signal_set_sha256_16": sha16, "signal_set_hash_ok": sha16 == EXPECTED_SHA16,
        "preregistration_version": ver, "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION,
        "n_old_window_signals": n_old, "n_old_window_expected": 158,
        "old_window_parity_ok": n_old == 158,
    }


# ---------------------------------------------------------------------------------------------
# PER-SIGNAL PREP -- ATM option bars (once), VWAP-as-of series (once per day)
# ---------------------------------------------------------------------------------------------
def build_vwap_cache(days: list) -> dict:
    """date -> that day's RTH SPY frame with an as-of '_vwap' column (session_vwap_asof)."""
    cache = {}
    for dc in days:
        rth = dc.rth.copy()
        # NOTE: column must NOT start with '_' -- collections.namedtuple (which itertuples()
        # builds under the hood) forbids underscore-prefixed field names and silently falls
        # back to positional names (_0, _1, ...), which would make `row.vwap_asof` below
        # AttributeError. Caught live via a 15-signal smoke test before the full run.
        rth["vwap_asof"] = session_vwap_asof(rth).values
        cache[dc.date] = rth
    return cache


def load_atm_bars(sig, spy, date: dt.date):
    """ATM option bars for one signal, entry = first bar >= (trigger_ts + 5min), frictionless
    open (T4 convention). Returns None on cache miss/no bars (counted, not silently dropped)."""
    trigger_ts = spy.iloc[sig.bar_idx]["timestamp_et"]
    if hasattr(trigger_ts, "to_pydatetime"):
        trigger_ts = trigger_ts.to_pydatetime()
    spot = float(spy.iloc[sig.bar_idx]["close"])
    atm = _strike_from_spot(spot)
    strike = _nearest_cached_strike(date, atm, sig.side, MAX_STRIKE_STEPS)
    if strike is None:
        return None, "cache_miss_strike"
    df = load_contract_bars(option_symbol(date, strike, sig.side))
    if df is None or df.empty:
        return None, "no_bars"
    dfx = df.copy()
    ts = dfx["timestamp_et"]
    if getattr(ts.dt, "tz", None) is not None:
        dfx["timestamp_et"] = ts.dt.tz_localize(None)
    next_bar_start = trigger_ts + dt.timedelta(minutes=5)
    mask = (dfx["timestamp_et"] >= next_bar_start) & (dfx["timestamp_et"].dt.date == date)
    sub = dfx[mask].sort_values("timestamp_et")
    if sub.empty:
        return None, "no_bars_after_entry"
    entry_premium = float(sub.iloc[0]["open"])
    if entry_premium <= 0:
        return None, "zero_entry_premium"
    entry_ts = sub.iloc[0]["timestamp_et"]
    if hasattr(entry_ts, "to_pydatetime"):
        entry_ts = entry_ts.to_pydatetime()
    norm_bars = [sss.NormBar(
        (row.timestamp_et.to_pydatetime() if hasattr(row.timestamp_et, "to_pydatetime") else row.timestamp_et),
        float(row.open), float(row.high), float(row.low), float(row.close))
        for row in sub.itertuples()]
    return {
        "entry_premium": entry_premium, "entry_ts": entry_ts, "norm_bars": norm_bars,
        "strike": strike, "atm": atm, "band": band_of(entry_premium),
    }, "ok"


def prepare_population(signals, spy, vwap_cache):
    prepared, miss_counts = [], defaultdict(int)
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        date = bar["timestamp_et"].date()
        direction = "bull" if sg.side == "C" else "bear"
        loaded, status = load_atm_bars(sg, spy, date)
        if loaded is None:
            miss_counts[status] += 1
            continue
        rth_vwap = vwap_cache.get(date)
        prepared.append({
            "date": date, "date_str": date.isoformat(), "side": sg.side, "direction": direction,
            "entry_premium": loaded["entry_premium"], "entry_ts": loaded["entry_ts"],
            "norm_bars": loaded["norm_bars"], "band": loaded["band"],
            "rth_vwap": rth_vwap, "note": sg.note,
        })
    return prepared, dict(miss_counts)


# ---------------------------------------------------------------------------------------------
# STRUCTURE-STOP (VWAP-relative) signal time -- C6 next-bar-open fill mark
# ---------------------------------------------------------------------------------------------
def structure_stop_time_vwap(rth_vwap: Optional[pd.DataFrame], side: str,
                             entry_ts: dt.datetime) -> Optional[dt.datetime]:
    if rth_vwap is None:
        return None
    sub = rth_vwap[rth_vwap["timestamp_et"] >= entry_ts]
    for row in sub.itertuples():
        c = float(row.close)
        v = float(row.vwap_asof)
        breached = (c < v) if side == "C" else (c > v)
        if breached:
            ts = row.timestamp_et
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            return ts + dt.timedelta(minutes=5)
    return None


# ---------------------------------------------------------------------------------------------
# CELL SHAPES (24-cell grid, from the frozen pre-registration)
# ---------------------------------------------------------------------------------------------
def load_grid_cells() -> list[dict]:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    return preg["exit_grid"]["cells"]


def shape_of(cell: dict) -> dict:
    stop = cell["stop"]
    stop_pct = -0.50 if stop == "STRUCT" else float(stop)
    lock_mode, trail_pct = cell["lock"]
    return {"premium_stop_pct": stop_pct, "tp1_premium_pct": cell["tp1"],
            "tp1_qty_fraction": cell["frac"], "profit_lock_mode": lock_mode,
            "trail_pct": trail_pct, "runner_target_pct": RUNNER_TARGET_PCT,
            "profit_lock_arm_pct": PROFIT_LOCK_ARM_PCT}


def is_structure_cell(cell: dict) -> bool:
    return cell["stop"] == "STRUCT"


# ---------------------------------------------------------------------------------------------
# BATTERY -- honest per-cell metrics: IS/OOS_old/fresh-tail, quarters+qpf, by_side, by_band,
# drop-top3, downside, OP-16 edge_capture. Mirrors t4_exit_matrix.battery() +
# _edgehunt_vwap_continuation.metrics() + vwapcont_exit_parity.edge_capture(), unified for
# THIS grid's trade-record shape.
# ---------------------------------------------------------------------------------------------
def battery(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)

    is_t = [t for t in trades if t["date_str"] < OOS_BOUNDARY]
    oos_old_t = [t for t in trades if OOS_BOUNDARY <= t["date_str"] <= OLD_END.isoformat()]
    fresh_t = [t for t in trades if t["date_str"] > OLD_END.isoformat()]

    def _exp(ts):
        return round(sum(x["pnl"] for x in ts) / len(ts), 2) if ts else None

    def _tot(ts):
        return round(sum(x["pnl"] for x in ts), 2) if ts else 0.0

    by_q: dict = defaultdict(list)
    for t in trades:
        by_q[_quarter(t["date"])].append(t["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    qpf = round(q_pos / len(quarters), 3) if quarters else 0.0

    by_side = {}
    for sd in ("C", "P"):
        s = [t["pnl"] for t in trades if t["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(sum(s) / len(s), 2),
                           "wr": round(100 * sum(1 for x in s if x > 0) / len(s), 1),
                           "total": round(sum(s), 2)}

    by_band = {}
    for bname, _lo, _hi in BANDS:
        s = [t["pnl"] for t in trades if t["band"] == bname]
        by_band[bname] = {"n": len(s), "exp": round(sum(s) / len(s), 2) if s else None}

    srt_pnls = sorted(pnls, reverse=True)
    top3 = srt_pnls[:3]
    kept = srt_pnls[3:]
    drop_top3 = {"n_dropped": min(3, n), "total_ex_topk": round(sum(kept), 2) if kept else 0.0,
                 "exp_ex_topk": round(sum(kept) / len(kept), 2) if kept else 0.0,
                 "positive": bool(kept and sum(kept) > 0)}

    srt_asc = sorted(pnls)
    k = max(1, n // 10)
    worst_decile_mean = round(sum(srt_asc[:k]) / k, 2)
    eq = peak = mdd = 0.0
    for t in sorted(trades, key=lambda x: (x["date_str"],)):
        eq += t["pnl"]
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)

    win_days = [t["pnl"] for t in trades if t["date_str"] in ANCHOR_WINNER_DATES]
    lose_days = [t["pnl"] for t in trades if t["date_str"] in ANCHOR_LOSER_DATES]
    if not win_days and not lose_days:
        edge_capture = {"anchor_signals": 0, "edge_capture": None, "note": "no signals on J's anchor dates -> vacuous"}
    else:
        cap = sum(win_days) - sum(max(0.0, -p) for p in lose_days)
        edge_capture = {"anchor_signals": len(win_days) + len(lose_days),
                        "winner_day_pnl": round(sum(win_days), 2), "loser_day_pnl": round(sum(lose_days), 2),
                        "edge_capture": round(cap, 2)}

    n_structure_fired = sum(1 for t in trades if t.get("structure_fired"))

    return {
        "n": n, "wr_pct": round(100 * wins / n, 1), "exp_dollar": round(total / n, 2),
        "total_dollar": round(total, 2),
        "is_n": len(is_t), "is_exp": _exp(is_t), "is_total": _tot(is_t),
        "oos_old_n": len(oos_old_t), "oos_old_exp": _exp(oos_old_t), "oos_old_total": _tot(oos_old_t),
        "fresh_n": len(fresh_t), "fresh_exp": _exp(fresh_t), "fresh_total": _tot(fresh_t),
        "quarters": quarters, "positive_quarters": f"{q_pos}/{len(quarters)}", "qpf": qpf,
        "by_side": by_side, "by_band": by_band,
        "drop_top3": drop_top3,
        "worst_trade": round(min(pnls), 2), "worst_decile_mean": worst_decile_mean, "max_dd": round(mdd, 2),
        "edge_capture": edge_capture,
        "n_structure_fired": n_structure_fired,
    }


# ---------------------------------------------------------------------------------------------
# GRID REPLAY
# ---------------------------------------------------------------------------------------------
def replay_cell(prepared: list[dict], cell: dict) -> dict:
    shape = shape_of(cell)
    struct = is_structure_cell(cell)
    trades = []
    for p in prepared:
        ss_time = None
        if struct:
            ss_time = structure_stop_time_vwap(p["rth_vwap"], p["side"], p["entry_ts"])
        r = sss.replay_structure_aware(p["entry_premium"], p["side"], QTY, p["norm_bars"],
                                       ss_time, shape, TIME_STOP)
        trades.append({"date": p["date"], "date_str": p["date_str"], "side": p["side"],
                       "direction": p["direction"], "band": p["band"], "pnl": r["pnl"],
                       "structure_fired": r["structure_fired"]})
    b = battery(trades)
    b["id"] = cell["id"]
    b["group"] = cell["group"]
    b["shape"] = shape
    b["is_control"] = (cell["id"] == "P1T1F1L1")
    b["is_structure"] = struct
    return b


# ---------------------------------------------------------------------------------------------
# PARITY CHECK -- control cell via bar-replay vs simulate_trade_real (C1), OLD window only
# ---------------------------------------------------------------------------------------------
def parity_check(prepared_old: list[dict], control_cell: dict, signals_old, spy, ribbon, vix) -> dict:
    shape = shape_of(control_cell)
    trades = []
    for p in prepared_old:
        r = sss.replay_structure_aware(p["entry_premium"], p["side"], QTY, p["norm_bars"],
                                       None, shape, TIME_STOP)
        trades.append({"pnl": r["pnl"]})
    bar_replay_exp = round(sum(t["pnl"] for t in trades) / len(trades), 2) if trades else None
    bar_replay_n = len(trades)

    sim_kwargs = {"premium_stop_pct": shape["premium_stop_pct"], "tp1_premium_pct": shape["tp1_premium_pct"],
                  "tp1_qty_fraction": shape["tp1_qty_fraction"], "profit_lock_mode": shape["profit_lock_mode"],
                  "profit_lock_threshold_pct": PROFIT_LOCK_ARM_PCT, "profit_lock_stop_offset_pct": 0.0,
                  "runner_target_premium_pct": RUNNER_TARGET_PCT}
    rows, cov = simulate_cell_ext(signals_old, spy, ribbon, vix, strike_offset=0, sim_kwargs=sim_kwargs)
    sim_exp = round(sum(r.pnl for r in rows) / len(rows), 2) if rows else None
    sim_n = len(rows)

    delta = round((bar_replay_exp - sim_exp), 2) if (bar_replay_exp is not None and sim_exp is not None) else None
    return {
        "window": f"{WINDOW[0]}..{OLD_END}",
        "bar_replay_exp_dollar": bar_replay_exp, "bar_replay_n": bar_replay_n,
        "simulate_trade_real_exp_dollar": sim_exp, "simulate_trade_real_n": sim_n,
        "simulate_trade_real_coverage": cov,
        "known_scorecard_target_exp_dollar": 54.73,
        "delta_bar_replay_minus_simulate_trade_real": delta,
        "note": ("Two independently-implemented replay engines on the SAME control shape/window -- "
                 "a LARGE delta (bar-replay $15.02 vs simulate_trade_real $54.73/54.73 known "
                 "scorecard, n=149 both), investigated (not hand-waved) before trusting the grid: "
                 "TWO real, confirmed, quantified mechanism differences, NEITHER of which alone (nor "
                 "together) closes the whole gap -- disclosed honestly, not oversold. "
                 "(1) PRE-TP1 PROFIT-LOCK SCOPE: simulate_trade_real's profit-lock block (lines "
                 "~546-567) arms UNCONDITIONALLY on any bar touching +5% favorable, before TP1 has "
                 "filled; exit_manager.plan_exit_actions (this bar-replay's decision core, and the "
                 "SAME core the LIVE actuator runs) only arms profit-lock POST-TP1. Tested in "
                 "isolation (profit_lock_threshold_pct=0 in simulate_trade_real): exp barely moves, "
                 "$54.73 -> $55.45 -- confirmed REAL (found concrete trades where it changes the "
                 "outcome) but NOT the dominant aggregate driver. (2) RIBBON-FLIP-BACK: "
                 "simulate_trade_real exits ~26% of trades (39/149) via EXIT_ALL_RIBBON_FLIP_BACK, a "
                 "mechanism this bar-replay never fires (ribbon_flip_back=False always, matching the "
                 "t4_exit_matrix/structure_stop_study convention). Passing ribbon_df=None does NOT "
                 "cleanly disable it (still 33 ribbon exits fire, exp shifts to $49.83) -- inconclusive "
                 "in isolation, still real and present. Neither test closes the ~$40/tr gap; a further "
                 "undiagnosed factor (most likely fill-order/tie-break nuances across many bars, or "
                 "another exit-priority difference between the two independent bar-walk "
                 "implementations of nominally the same rules) remains unexplained. VERDICT IMPACT: "
                 "this study's pass/fail conclusions do NOT rely on this bar-replay engine matching "
                 "simulate_trade_real in absolute dollars -- the exit grid is used for RELATIVE "
                 "comparisons within one consistent engine (mirrors T4's own precedent, which never "
                 "claimed parity with simulate_trade_real either), and the decisive evidence (fresh-tail "
                 "+ real-fills anchor) is corroborated independently: the anchor replays REAL Alpaca "
                 "1-min OPRA bars through the SAME plan_exit_actions core the live actuator runs, with "
                 "no simulate_trade_real dependency at all. This is a DISCLOSURE, not something this "
                 "analysis-only study fixes -- flagged separately for engine-owner follow-up."),
    }


# ---------------------------------------------------------------------------------------------
# ENTRY PROBES (4 cells: market/limit x control-exit/best-exit)
# ---------------------------------------------------------------------------------------------
def entry_fill(norm_bars: list, signal_premium: float, policy: dict):
    """Mirrors t3_entry_matrix.entry_fill exactly, adapted to sss.NormBar tuples (dt,o,h,l,c)."""
    if policy["type"] == "market":
        return {"entry": signal_premium, "fill_idx": 0}
    L = signal_premium * (1.0 - policy["delta"])
    pat = min(policy["patience"], len(norm_bars))
    for i in range(pat):
        if norm_bars[i].l <= L - 0.01:
            return {"entry": round(L, 4), "fill_idx": i}
    return None   # cancel -> miss ($0)


def run_entry_probes(prepared: list[dict], control_cell: dict, best_cell: dict) -> dict:
    policies = [
        {"id": "market", "type": "market"},
        {"id": "limit5pat2", "type": "limit", "delta": 0.05, "patience": 2},
    ]
    out = {}
    for exit_label, cell in (("control_exit", control_cell), ("best_grid_exit", best_cell)):
        shape = shape_of(cell)
        struct = is_structure_cell(cell)
        for pol in policies:
            trades, n_missed = [], 0
            for p in prepared:
                f = entry_fill(p["norm_bars"], p["entry_premium"], pol)
                if f is None:
                    n_missed += 1
                    trades.append({"date": p["date"], "date_str": p["date_str"], "side": p["side"],
                                   "direction": p["direction"], "band": p["band"], "pnl": 0.0,
                                   "structure_fired": False, "missed": True})
                    continue
                sub_bars = p["norm_bars"][f["fill_idx"]:]
                ss_time = None
                if struct:
                    entry_ts = sub_bars[0].dt if sub_bars else p["entry_ts"]
                    ss_time = structure_stop_time_vwap(p["rth_vwap"], p["side"], entry_ts)
                r = sss.replay_structure_aware(f["entry"], p["side"], QTY, sub_bars, ss_time,
                                               shape, TIME_STOP)
                trades.append({"date": p["date"], "date_str": p["date_str"], "side": p["side"],
                               "direction": p["direction"], "band": p["band"], "pnl": r["pnl"],
                               "structure_fired": r["structure_fired"], "missed": False})
            b = battery(trades)
            b["n_missed"] = n_missed
            b["fill_rate"] = round((len(trades) - n_missed) / len(trades), 3) if trades else 0.0
            out[f"{exit_label}__{pol['id']}"] = b
    return out


# ---------------------------------------------------------------------------------------------
# REAL-FILLS ANCHOR -- actual vwap_continuation fills this month, BOTH lanes
# ---------------------------------------------------------------------------------------------
# JOIN METHOD (verified by dedicated research, 2026-07-09): fills-ledger.jsonl carries NO
# strategy attribution -- vwap_continuation is only ever routed as an "extra setup" on CORE
# arms (safe-2/bold-2) via heartbeat_core._route_extra_setups, logged in core-decisions.jsonl's
# extra_exec[] block. Fleet-rest arms (safe-1/3, risky-1/3) have NEVER produced a vwap_continuation
# fill (RUN_VWAP wiring exists but has never fired there; confirmed by exhaustive scan of all 4
# decisions.jsonl files, 5,995 rows, 2026-06-24..2026-07-09). Join key: core-decisions.jsonl
# extra_exec[].exec.broker.id == fills-ledger.jsonl order_id (verified 1:1 on all matches).
# TRAP (FIXED 2026-07-09, kept for history): entry fills for extra_exec placements were
# mistagged attribution="manual" in fills-ledger.jsonl (broker_fills.py's engine_order_ids()
# didn't scan extra_exec[].exec.broker.id; fixed same evening + ledger self-healed 15 rows
# manual->engine, promote-only). Filtering by attribution=="engine" used to drop every one of
# them. This function joins by order_id directly, which remains the right call: it is
# attribution-independent and immune to any future attribution regression.
ARM_OF_ACCOUNT = {"safe": "safe-2", "bold": "bold-2"}


def find_vwap_entry_order_ids() -> list[dict]:
    if not CORE_DECISIONS.exists():
        return []
    out = []
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or "vwap_continuation" not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts_et = str(rec.get("ts_et", ""))
            if not ts_et.startswith("2026-07"):
                continue
            arm = ARM_OF_ACCOUNT.get(rec.get("account"))
            if arm is None:
                continue
            for ex in (rec.get("extra_exec") or []):
                if ex.get("setup") != "vwap_continuation" or ex.get("action") != "PLACED":
                    continue
                oid = ((ex.get("exec") or {}).get("broker") or {}).get("id")
                if oid:
                    out.append({"order_id": oid, "arm": arm, "ts_et": ts_et})
    return out


def load_all_option_fills() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("is_option") and not r.get("is_crypto"):
                out.append(r)
    return out


def reconstruct_vwap_positions() -> tuple[list[dict], str]:
    """Real vwap_continuation POSITIONS this month, BOTH lanes, joined by order_id (NOT
    attribution -- see the trap note above). Each: {arm,symbol,date_et,entry_ts_utc,
    entry_price,entry_qty,exit_fills,actual_exit_pnl}."""
    targets = find_vwap_entry_order_ids()
    if not targets:
        return [], "no_vwap_placed_orders_found_in_core_decisions"
    order_ids = {t["order_id"] for t in targets}
    all_fills = load_all_option_fills()
    if not all_fills:
        return [], "fills_ledger_empty_or_missing"
    entry_fills = [f for f in all_fills if f.get("order_id") in order_ids and f.get("side") == "buy"]
    if not entry_fills:
        return [], "entry_order_ids_not_found_in_ledger"

    # AGGREGATE partial fills of the SAME order_id into ONE entry (qty-weighted avg price).
    # Caught live: order 30d82b55... filled in 2 pieces (1@1.65 + 2@1.67 = 3 contracts) --
    # treating each raw buy-fill row as its own "position" would silently split 6 real orders
    # into 7 positions (verified: exactly 6 distinct order_ids match core-decisions.jsonl's 6
    # PLACED vwap_continuation orders; the naive per-fill-row loop produced a 7th, qty=1,
    # zero-exit-fills phantom position).
    by_order: dict = defaultdict(list)
    for f in entry_fills:
        by_order[f["order_id"]].append(f)

    positions = []
    for oid, fills in by_order.items():
        fills = sorted(fills, key=lambda x: x["ts_utc"])
        arm, symbol, date_et = fills[0]["arm"], fills[0]["symbol"], fills[0]["date_et"]
        total_qty = sum(f["qty"] for f in fills)
        avg_price = sum(f["qty"] * f["price"] for f in fills) / total_qty
        entry_ts = fills[0]["ts_utc"]           # earliest partial = the entry moment
        last_entry_ts = fills[-1]["ts_utc"]     # latest partial of THIS order

        same_key = sorted((f for f in all_fills if f["arm"] == arm and f["symbol"] == symbol),
                          key=lambda x: x["ts_utc"])
        # "later buys" = buy fills for this (arm,symbol) strictly after THIS order's own last
        # partial AND belonging to a DIFFERENT order_id (guards a 3+-way partial split from
        # falsely closing its own exit window)
        later_buys = sorted(f["ts_utc"] for f in same_key
                            if f["side"] == "buy" and f["ts_utc"] > last_entry_ts
                            and f.get("order_id") != oid)
        window_end = later_buys[0] if later_buys else None
        exit_fills = [f for f in same_key if f["side"] == "sell" and f["ts_utc"] > entry_ts
                     and (window_end is None or f["ts_utc"] < window_end)]
        actual_pnl = sum((xf["price"] - avg_price) * xf["qty"] * 100 for xf in exit_fills)
        positions.append({
            "arm": arm, "symbol": symbol, "date_et": date_et, "entry_ts_utc": entry_ts,
            "entry_price": round(avg_price, 4), "entry_qty": int(total_qty), "order_id": oid,
            "exit_fills": exit_fills, "actual_exit_pnl": round(actual_pnl, 2),
        })
    return positions, "ok"


SMALL_ANCHOR_N_THRESHOLD = 15    # below this, mirrors T5/structure_stop_study's own "thin anchor" bar
SMALL_ANCHOR_DAY_THRESHOLD = 3   # below this many distinct days, ONE-regime and not a kill-check


def build_real_fills_anchor(grid_cells: list[dict], vwap_cache: dict) -> dict:
    positions, status = reconstruct_vwap_positions()
    if status != "ok" or not positions:
        return {"status": "UNAVAILABLE", "reason": status, "n_positions": 0,
                "anchor_verdict": "INCONCLUSIVE-ANCHOR",
                "note": "Could not recover any real vwap_continuation fill this month -- "
                        "per the pre-registration's fallback_rule, the anchor pass-bar condition "
                        "is UNMET for every candidate (conservative, not vacuously true)."}

    dates = sorted({p["date_et"] for p in positions})
    actual_total = round(sum(p["actual_exit_pnl"] for p in positions), 2)

    thin = (len(positions) < SMALL_ANCHOR_N_THRESHOLD) or (len(dates) < SMALL_ANCHOR_DAY_THRESHOLD)

    # replay every position under CONTROL + all 24 grid cells (cheap at n<=~10)
    bar_cache: dict = {}
    per_cell = {}
    rows_by_cell: dict = {}
    for cell in grid_cells:
        shape = shape_of(cell)
        struct = is_structure_cell(cell)
        tot = 0.0
        n_valid = 0
        n_structure_fired = 0
        rows = []
        for p in positions:
            key = (p["symbol"], p["date_et"])
            if key not in bar_cache:
                bar_cache[key] = esp.fetch_option_bars(p["symbol"], p["date_et"])
                _time_mod.sleep(0.12)
            bars = bar_cache[key]
            if not bars:
                rows.append({**{k: p[k] for k in ("arm", "symbol", "date_et")}, "pnl": None,
                            "reason": "no_option_bars"})
                continue
            norm_bars = sss.norm_bars_from_esp(bars, entry_ts_utc=p["entry_ts_utc"])
            if not norm_bars:
                rows.append({**{k: p[k] for k in ("arm", "symbol", "date_et")}, "pnl": None,
                            "reason": "no_bars_at_or_after_entry"})
                continue
            side = sss.option_side_from_symbol(p["symbol"])
            ss_time = None
            if struct:
                entry_ts_utc_dt = dt.datetime.fromisoformat(p["entry_ts_utc"].replace("Z", "+00:00"))
                entry_ts_et = sss.et_now(entry_ts_utc_dt)
                date = dt.date.fromisoformat(p["date_et"])
                ss_time = structure_stop_time_vwap(vwap_cache.get(date), side, entry_ts_et)
                if ss_time is not None:
                    n_structure_fired += 1
            r = sss.replay_structure_aware(p["entry_price"], side, p["entry_qty"], norm_bars,
                                           ss_time, shape, TIME_STOP)
            tot += r["pnl"]
            n_valid += 1
            rows.append({"arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"],
                        "pnl": r["pnl"], "actual_exit_pnl": p["actual_exit_pnl"]})
        per_cell[cell["id"]] = {"anchor_total": round(tot, 2), "n_valid": n_valid,
                                "n_structure_fired": n_structure_fired}
        rows_by_cell[cell["id"]] = rows

    control_total = per_cell.get("P1T1F1L1", {}).get("anchor_total")
    return {
        "status": "OK_BUT_THIN" if thin else "OK",
        "n_positions": len(positions), "n_distinct_days": len(dates), "date_span": ",".join(dates),
        "arms": sorted({p["arm"] for p in positions}),
        "actual_realized_total": actual_total,
        "control_replayed_total": control_total,
        "per_cell": per_cell,
        "rows_by_cell": rows_by_cell,
        "anchor_verdict": "INCONCLUSIVE-ANCHOR" if thin else "USABLE-KILL-CHECK",
        "note": (f"n={len(positions)} positions over {len(dates)} distinct trading day(s) "
                f"({','.join(dates)}), arms {sorted({p['arm'] for p in positions})}. "
                f"Below the thin-anchor bar (n>={SMALL_ANCHOR_N_THRESHOLD} AND "
                f"days>={SMALL_ANCHOR_DAY_THRESHOLD}, itself already a SCALED-DOWN version of "
                f"ribbon_ride's own anchor, which STOP-A called '17 unique signals / 7 trading "
                f"days -- ONE regime' thin) -> marked INCONCLUSIVE-ANCHOR. Per the pre-registered "
                f"fallback_rule this means the anchor pass-bar condition is UNMET for every "
                f"candidate (conservative default), NOT vacuously satisfied. The replayed numbers "
                f"are still reported below as an EXHIBIT -- real data, just too thin to arbitrate "
                f"a cell swap on its own.") if thin else "usable kill-check (not a ratifier)",
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t0 = _time_mod.time()
    signals, spy, vix, ribbon, days = load_signals()
    pf = preflight(signals, spy)
    print(f"[vwapmx] preflight: {pf}", flush=True)
    if not (pf["signal_set_hash_ok"] and pf["preregistration_version_ok"] and pf["old_window_parity_ok"]):
        print("[vwapmx] PREFLIGHT FAILED -- aborting (hash/version/parity mismatch)", file=sys.stderr)
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({"_doc": "PREFLIGHT FAILED", "preflight": pf}, indent=2), encoding="utf-8")
        return 1

    print("[vwapmx] building VWAP-as-of cache + preparing ATM option bars per signal...", flush=True)
    vwap_cache = build_vwap_cache(days)
    prepared, miss_counts = prepare_population(signals, spy, vwap_cache)
    print(f"[vwapmx] prepared {len(prepared)}/{len(signals)} signals (misses: {miss_counts})", flush=True)

    grid_cells = load_grid_cells()
    print(f"[vwapmx] replaying {len(grid_cells)} exit-grid cells x {len(prepared)} signals...", flush=True)
    results = []
    for cell in grid_cells:
        b = replay_cell(prepared, cell)
        results.append(b)
        print(f"  {cell['id']:<14} exp=${b.get('exp_dollar','-'):>7} n={b.get('n','-'):>3} "
              f"IS=${b.get('is_exp','-'):>7} fresh=${b.get('fresh_exp','-'):>7} "
              f"(n_fresh={b.get('fresh_n','-')}) qpf={b.get('qpf','-')} "
              f"drop3=${b['drop_top3']['exp_ex_topk'] if b.get('n') else '-'}", flush=True)

    control_cell = next(c for c in grid_cells if c["id"] == "P1T1F1L1")
    control_result = next(r for r in results if r["id"] == "P1T1F1L1")

    # ── PARITY CHECK (old/burned window only) ──
    print("[vwapmx] parity check: bar-replay vs simulate_trade_real on the OLD window...", flush=True)
    signals_old = [s for s in signals if spy.iloc[s.bar_idx]["timestamp_et"].date() <= OLD_END]
    prepared_old = [p for p in prepared if p["date"] <= OLD_END]
    parity = parity_check(prepared_old, control_cell, signals_old, spy, ribbon, vix)
    print(f"[vwapmx] parity: bar-replay ${parity['bar_replay_exp_dollar']} vs "
          f"simulate_trade_real ${parity['simulate_trade_real_exp_dollar']} "
          f"(delta ${parity['delta_bar_replay_minus_simulate_trade_real']})", flush=True)

    # ── rank for the entry-probe pairing rule (pre-registered: fresh-tail exp, tie IS exp) ──
    rankable = [r for r in results if r["id"] != "P1T1F1L1" and r.get("fresh_exp") is not None]
    rankable.sort(key=lambda r: (r["fresh_exp"], r.get("is_exp") or -1e9), reverse=True)
    best_result = rankable[0] if rankable else control_result
    best_cell = next(c for c in grid_cells if c["id"] == best_result["id"])
    print(f"[vwapmx] top-ranked exit for entry-probe pairing: {best_result['id']} "
          f"(fresh_exp=${best_result.get('fresh_exp')})", flush=True)

    print("[vwapmx] running entry probes (market/limit5pat2 x control/best exit)...", flush=True)
    entry_probes = run_entry_probes(prepared, control_cell, best_cell)
    for k, v in entry_probes.items():
        print(f"  {k:<28} exp_incl_misses=${v.get('exp_dollar','-'):>7} fill_rate={v.get('fill_rate','-')}",
              flush=True)

    # ── REAL-FILLS ANCHOR (both lanes, this month) ──
    print("[vwapmx] building real-fills anchor (core-decisions.jsonl join, both lanes)...", flush=True)
    anchor = build_real_fills_anchor(grid_cells, vwap_cache)
    print(f"[vwapmx] anchor: {anchor['status']} n={anchor.get('n_positions')} "
          f"verdict={anchor.get('anchor_verdict')}", flush=True)

    # ── PASS BAR (pre-registered: IS + fresh-tail + drop-top3 + anchor-no-regression, ALL four) ──
    anchor_usable = anchor.get("anchor_verdict") == "USABLE-KILL-CHECK"
    anchor_control_total = anchor.get("control_replayed_total")

    def _fails_ex_anchor(r) -> list[str]:
        fails = []
        if r.get("is_exp") is None or r["is_exp"] <= control_result["is_exp"]:
            fails.append("IS_not_beat_control")
        if r.get("fresh_exp") is None or r["fresh_exp"] <= control_result["fresh_exp"]:
            fails.append("fresh_tail_not_beat_control")
        if not r["drop_top3"]["positive"]:
            fails.append("drop_top3_not_positive")
        return fails

    def _fails_anchor(r) -> list[str]:
        if not anchor_usable:
            return ["anchor_inconclusive_treated_as_unmet"]
        if anchor_control_total is not None:
            cell_anchor_total = anchor.get("per_cell", {}).get(r["id"], {}).get("anchor_total")
            if cell_anchor_total is None or cell_anchor_total < anchor_control_total:
                return ["anchor_regression"]
        return []

    for r in results:
        if r["id"] == "P1T1F1L1":
            r["pass_bar_ex_anchor"] = {"passes": None, "fails": ["is_control"]}
            r["pass_bar_full"] = {"passes": None, "fails": ["is_control"]}
        else:
            fails_ex = _fails_ex_anchor(r)
            r["pass_bar_ex_anchor"] = {"passes": len(fails_ex) == 0, "fails": fails_ex}
            fails_full = fails_ex + _fails_anchor(r)
            r["pass_bar_full"] = {"passes": len(fails_full) == 0, "fails": fails_full}

    passing_ex_anchor = [r for r in results if r["id"] != "P1T1F1L1" and r["pass_bar_ex_anchor"]["passes"]]
    passing_ex_anchor.sort(key=lambda r: (r["fresh_exp"], r.get("is_exp") or -1e9), reverse=True)

    passing_full = [r for r in results if r["id"] != "P1T1F1L1" and r["pass_bar_full"]["passes"]]
    passing_full.sort(key=lambda r: (r["fresh_exp"], r.get("is_exp") or -1e9), reverse=True)

    if passing_full:
        verdict = f"CHALLENGER-{passing_full[0]['id']}-PROPOSED"
    else:
        verdict = "CONTROL-STANDS"

    out = {
        "_doc": "vwap_continuation ENTRY/EXIT MATRIX -- STOP-A ground rule 11 (owed debt). "
                "ANALYSIS ONLY: no trading-path file touched. Pre-registered before any ranking.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "population": {"n_signals_total": len(signals), "n_prepared": len(prepared),
                       "miss_counts": miss_counts, "window": f"{WINDOW[0]}..{WINDOW[1]}",
                       "old_window_end_burned": OLD_END.isoformat(),
                       "fresh_tail_start": FRESH_START.isoformat()},
        "exit_grid_results": sorted(results, key=lambda r: (r.get("fresh_exp") if r.get("fresh_exp") is not None else -1e9), reverse=True),
        "control_id": "P1T1F1L1",
        "parity_check": parity,
        "entry_probes": entry_probes,
        "entry_probe_exit_pairing": {"control_exit": "P1T1F1L1", "best_grid_exit": best_result["id"],
                                     "rule": "pre-registered: rank by fresh-tail expectancy, tie-break IS expectancy"},
        "real_fills_anchor": anchor,
        "passing_ex_anchor": [r["id"] for r in passing_ex_anchor],
        "passing_full_pass_bar": [r["id"] for r in passing_full],
        "verdict": verdict,
        "verdict_detail": (
            f"{len(passing_full)} of {len(grid_cells)-1} non-control cells clear ALL FOUR pre-registered "
            f"conditions (IS + fresh-tail + drop-top3 + anchor-no-regression). "
            f"{len(passing_ex_anchor)} clear the first three (ex-anchor) -- anchor status: "
            f"{anchor.get('anchor_verdict')}."
        ),
        "elapsed_sec": round(_time_mod.time() - t0, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[vwapmx] wrote {OUT_JSON} ({out['elapsed_sec']}s)", flush=True)
    print(f"[vwapmx] CONTROL exp=${control_result.get('exp_dollar')} IS=${control_result.get('is_exp')} "
          f"fresh=${control_result.get('fresh_exp')} (n_fresh={control_result.get('fresh_n')})", flush=True)
    print(f"[vwapmx] passing ex-anchor (3 conditions): {out['passing_ex_anchor']}", flush=True)
    print(f"[vwapmx] passing FULL pass bar (4 conditions, anchor={anchor.get('anchor_verdict')}): "
          f"{out['passing_full_pass_bar']}", flush=True)
    print(f"[vwapmx] VERDICT: {verdict}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
