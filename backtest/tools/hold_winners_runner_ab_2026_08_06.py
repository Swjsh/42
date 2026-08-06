#!/usr/bin/env python
"""hold_winners_runner_ab_2026_08_06.py -- LANE 3: HOLD OUR WINNERS (the runner-shape A/B).

Executes PREREG-RUNNER-BE-FLOOR-2026-08-06 (analysis/recommendations/
prereg-runner-be-floor-2026-08-06.json, committed 61bc6507 BEFORE this file existed --
git-provable). Every methodological choice below is the frozen prereg's; nothing here was
picked after seeing results.

THE QUESTION (J, verbatim directive for next week: "good days where we hold our winners"):
post-TP1 runner managed by a fixed BE floor (profit_lock_mode="fixed") vs the chandelier
trail (profit_lock_mode="trailing"), full real-fills population INCLUDING losers,
stratified by day archetype.

SCOPE GUARD (stated per prereg): POST-TP1 only. profit_lock_arm_scope stays "post_tp1" in
every cell -- exit_manager.plan_exit_actions consults profit_lock_mode only in its post-TP1
branch under that scope (exit_manager.py:514). This is mechanically disjoint from the
five-times-dead PRE-TP1 arm_scope="full" graveyard cell.

MECHANISM: exits via backtest/lib/exit_manager_walk.walk_exit_manager ->
automation/state/fleet/exit_manager.plan_exit_actions (the REAL live decision core).
NEVER simulator_real. Sequential one-position walks per (arm, date, symbol) wave; a cell
still holding at the next observed real entry SUPPRESSES that re-entry (disclosed, counted).
Structure stops ARE modeled (five_min_spy_df + per-entry trigger_level from the arm's own
ledger row) -- a fidelity upgrade over prior population replays. Ribbon flips are NOT
modeled (ribbon_tick_df=None) -- identical omission in all cells, disclosed.

Run: backtest/.venv/Scripts/python.exe backtest/tools/hold_winners_runner_ab_2026_08_06.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "backtest" / "lib",
           REPO / "automation" / "state" / "fleet", REPO / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402
import strategies as strat_registry  # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402

STATE = REPO / "automation" / "state"
FLEET = STATE / "fleet"
CACHE = REPO / "backtest" / "data" / "opra_1m_cache"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-06.csv"
ARCH = REPO / "analysis" / "regime-library" / "day-archetypes.json"
OUT_JSON = REPO / "analysis" / "deep-research" / "HOLD-WINNERS-2026-08-06.json"

ALL_ARMS = ("safe-1", "safe-2", "safe-3", "risky-1", "risky-3", "bold-2")
FLEET_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
CORE_ARMS = {"safe-2": "safe", "bold-2": "bold"}
TIME_STOP = dt.time(15, 40)          # live params.json time_stop_et, both core + fleet paths
JOIN_TOL_MIN = 5.0                   # frozen: nearest entry row within 5 minutes

TREND_LIKE = {"trend-up", "trend-down", "gap-go"}
CHOP_LIKE = {"range-chop", "pin-day", "gap-fade", "V-reversal", "inverted-V"}

# accounts.json params_patch.exit_patch, read live (frozen recipe -- overlay onto registry)
def _arm_exit_patches() -> dict:
    grid = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
    out = {}
    for arm in grid.get("arms", []):
        patch = ((arm.get("params_patch") or {}).get("exit_patch")) or {}
        out[arm.get("id")] = dict(patch)
    return out


# core isolated exit overrides (heartbeat_core._SETUP_EXIT_OVERRIDES params keys)
_CORE_XOV = {
    "vwap_continuation": {"stop": "j_vwap_cont_premium_stop_pct", "tp1": "j_vwap_cont_tp1_pct"},
    "vwap_reclaim_failed_break": {"stop": "j_vwap_reclaim_fb_premium_stop_pct",
                                  "tp1": "j_vwap_reclaim_fb_tp1_pct"},
    "vix_regime_dayside": {"stop": "j_vix_dayside_premium_stop_pct", "tp1": "j_vix_dayside_tp1_pct"},
    "double_bottom_base_quiet": {"stop": "j_db_base_quiet_premium_stop_pct",
                                 "tp1": "j_db_base_quiet_tp1_pct",
                                 "runner": "j_db_base_quiet_runner_target_pct"},
    "bollinger_squeeze": {"stop": "j_bollinger_squeeze_premium_stop_pct",
                          "tp1": "j_bollinger_squeeze_tp1_pct",
                          "tq": "j_bollinger_squeeze_tp1_qty_fraction",
                          "plmode": "j_bollinger_squeeze_profit_lock_mode",
                          "trail": "j_bollinger_squeeze_profit_lock_trail_pct"},
    "gap_and_go": {"stop": "j_gap_and_go_premium_stop_pct", "tp1": "j_gap_and_go_tp1_pct",
                   "stop_mode": "structure"},
}


def _load_params(account: str) -> dict:
    p = STATE / ("params.json" if account == "safe" else "aggressive/params.json")
    return json.loads(p.read_text(encoding="utf-8"))


def _naive_et(ts: str) -> dt.datetime:
    """Ledger ts strings -> naive true-ET datetime. Handles naive ('...T14:26:04.600900'),
    offset-aware ('...-04:00'), and UTC 'Z' forms. Whole population is EDT (UTC-4)."""
    s = ts.strip()
    if s.endswith("Z"):
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        d = dt.datetime.fromisoformat(s)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
    return d


# ---------------------------------------------------------------- entry-row attribution
def _fleet_entry_rows() -> list[dict]:
    rows = []
    for arm in FLEET_ARMS:
        p = FLEET / arm / "decisions.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or '"ENTER' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not str(r.get("action", "")).startswith("ENTER"):
                continue
            pl = r.get("placement") or {}
            sym = pl.get("symbol") or r.get("symbol")
            ts = r.get("ts_et") or r.get("signal_written_at") or ""
            if not sym or not ts:
                continue
            rows.append({
                "arm": r.get("arm_id") or arm, "symbol": sym, "ts": _naive_et(ts),
                "setup": str(r.get("setup_name") or pl.get("strategy") or ""),
                "trigger_level": r.get("trigger_level", pl.get("trigger_level")),
                "stop_mode": str(pl.get("stop_mode") or ""),
            })
    return rows


def _core_entry_rows() -> list[dict]:
    rows = []
    p = STATE / "core-decisions.jsonl"
    arm_of = {v: k for k, v in CORE_ARMS.items()}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or '"PLACED"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("action")) != "PLACED":
            continue
        ex = r.get("exec") or {}
        pl = ex if isinstance(ex, dict) else {}
        sym = pl.get("symbol") or r.get("symbol")
        acct = str(r.get("account") or "")
        ts = r.get("ts_et") or ""
        if not sym or acct not in arm_of or not ts:
            continue
        rows.append({
            "arm": arm_of[acct], "symbol": sym, "ts": _naive_et(ts),
            "setup": str(r.get("setup") or ""),
            "trigger_level": (r.get("trigger_level")
                              or pl.get("trigger_level")
                              or r.get("bear_rejection_level_raw")
                              or r.get("bull_reclaim_level_raw")),
            "stop_mode": str(pl.get("stop_mode") or ""),
        })
    return rows


def join_attribution(positions: list[dict]) -> None:
    """Attach setup/trigger_level/stop_mode from the arm's own entry row (nearest within
    JOIN_TOL_MIN minutes on the same symbol). Mutates position dicts in place (study-local
    records, not shared state)."""
    idx = defaultdict(list)
    for row in _fleet_entry_rows() + _core_entry_rows():
        idx[(row["arm"], row["symbol"])].append(row)
    for lst in idx.values():
        lst.sort(key=lambda r: r["ts"])
    for p in positions:
        ts = _naive_et(p["entry_ts_et"])
        cands = idx.get((p["arm"], p["symbol"]), [])
        best, best_d = None, None
        for r in cands:
            d = abs((r["ts"] - ts).total_seconds()) / 60.0
            if d <= JOIN_TOL_MIN and (best_d is None or d < best_d):
                best, best_d = r, d
        if best:
            p["setup"] = best["setup"]
            p["trigger_level"] = best["trigger_level"]
            p["row_stop_mode"] = best["stop_mode"]
            p["attribution"] = "ledger_row"
        else:
            p["setup"] = ""
            p["trigger_level"] = None
            p["row_stop_mode"] = ""
            p["attribution"] = "fallback_ribbon_ride"


# ---------------------------------------------------------------- shape resolution
def resolve_shape(p: dict, patches: dict) -> dict:
    """Frozen recipe: registry-by-setup + arm exit_patch overlay + core isolated overrides.
    Ledger row placement tp fields are NOT trusted for core arms (D4)."""
    setup = (p.get("setup") or "").strip()
    setup_l = setup.lower()
    if "ride_the_ribbon" in setup_l or p["attribution"] == "fallback_ribbon_ride" or not setup:
        shape = strat_registry.RIBBON_RIDE.exit.to_dict()
        p["strategy"] = "ribbon_ride"
    elif setup_l in ("vwap_continuation",):
        shape = strat_registry.VWAP_CONTINUATION.exit.to_dict()
        p["strategy"] = "vwap_continuation"
    elif setup_l in ("vwap_reclaim_failed_break",):
        shape = strat_registry.VWAP_RECLAIM_FAILED_BREAK.exit.to_dict()
        p["strategy"] = "vwap_reclaim_failed_break"
    elif p["arm"] in CORE_ARMS and setup_l in _CORE_XOV:
        params = _load_params(CORE_ARMS[p["arm"]])
        xov = _CORE_XOV[setup_l]
        shape = {
            "premium_stop_pct": float(params.get(xov.get("stop", ""), -0.50) or -0.50),
            "tp1_premium_pct": float(params.get(xov.get("tp1", ""), 0.30) or 0.30),
            "tp1_qty_fraction": float(params.get(xov["tq"], params.get("tp1_qty_fraction", 0.8))
                                      if "tq" in xov else params.get("tp1_qty_fraction", 0.8)),
            "profit_lock_mode": str(params.get(xov["plmode"], "fixed") if "plmode" in xov else "fixed"),
        }
        if "trail" in xov:
            shape["trail_pct"] = float(params.get(xov["trail"], 0.125))
        if "runner" in xov:
            shape["runner_target_pct"] = float(params.get(xov["runner"], 2.5))
        if xov.get("stop_mode"):
            shape["stop_mode"] = xov["stop_mode"]
        p["strategy"] = setup_l
    else:
        # unknown setup on a fleet arm -> ribbon_ride family naming variants land above;
        # anything else is disclosed and gets the ribbon_ride shape (frozen fallback)
        shape = strat_registry.RIBBON_RIDE.exit.to_dict()
        p["strategy"] = f"fallback({setup_l or 'none'})"
        p["attribution"] = "fallback_ribbon_ride"
    patch = patches.get(p["arm"]) or {}
    shape = dict(shape)
    shape.update(patch)                       # arm exit_patch overlay (fleet arms only carry one)
    shape["profit_lock_arm_scope"] = "post_tp1"   # scope guard -- frozen, every cell
    return shape


# ---------------------------------------------------------------- bars
_OPT_CACHE: dict = {}


def load_opt_df(symbol: str, date: str) -> pd.DataFrame | None:
    key = (symbol, date)
    if key in _OPT_CACHE:
        return _OPT_CACHE[key]
    p = CACHE / f"{symbol}_{date}.csv"
    if not p.exists():
        _OPT_CACHE[key] = None
        return None
    rows = []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ts = pd.Timestamp(r["t"])
            if ts.tzinfo is not None:
                ts = ts.tz_convert("America/New_York").tz_localize(None)
            rows.append({"timestamp_et": ts, "open": float(r["o"]), "high": float(r["h"]),
                         "low": float(r["l"]), "close": float(r["c"])})
    df = pd.DataFrame(rows).sort_values("timestamp_et").reset_index(drop=True) if rows else None
    _OPT_CACHE[key] = df
    return df


def load_spy5m(dates: set[str]) -> pd.DataFrame:
    df = pd.read_csv(SPY5M)
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed")
    ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.assign(timestamp_et=ts)
    df = df[df["timestamp_et"].dt.strftime("%Y-%m-%d").isin(dates)]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- the replay
CELLS = ("CONTROL", "B_BE_FLOOR", "C_BE_FLOOR_TGT25")


def cell_shape(base: dict, cell: str) -> dict:
    s = dict(base)
    if cell == "B_BE_FLOOR":
        s["profit_lock_mode"] = "fixed"
    elif cell == "C_BE_FLOOR_TGT25":
        s["profit_lock_mode"] = "fixed"
        if float(s.get("runner_target_pct", 2.5)) >= 99.0:
            s["runner_target_pct"] = 2.5
    return s


def run() -> dict:
    fills = esp.load_fleet_engine_fills(arms=ALL_ARMS)
    positions = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    ts_et_by = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    for p in positions:
        p["entry_ts_et"] = ts_et_by.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "")
    positions = [p for p in positions if p["entry_ts_et"] and int(p["entry_qty"]) >= 1]
    join_attribution(positions)
    patches = _arm_exit_patches()
    for p in positions:
        p["base_shape"] = resolve_shape(p, patches)

    spy5 = load_spy5m({p["date_et"] for p in positions})
    arch = json.loads(ARCH.read_text(encoding="utf-8"))["days"]

    waves = defaultdict(list)
    for p in positions:
        waves[(p["arm"], p["date_et"], p["symbol"])].append(p)
    for w in waves.values():
        w.sort(key=lambda p: p["entry_ts_et"])

    per_pos: list[dict] = []
    suppressed = Counter()
    no_bars: list[dict] = []          # cache file missing/empty -- data gap, disclosed
    suppressed_all: list[dict] = []   # suppressed in EVERY cell (sequential convention)

    for wkey, wave in sorted(waves.items()):
        opt_df = load_opt_df(wkey[2], wkey[1])
        if opt_df is None or opt_df.empty:
            no_bars.extend(wave)
            continue
        flat_after = {c: None for c in CELLS}
        for p in wave:
            entry_dt = _naive_et(p["entry_ts_et"])
            side = p["symbol"][9]
            rec = {"arm": p["arm"], "date": p["date_et"], "symbol": p["symbol"],
                   "entry_ts": p["entry_ts_et"], "entry_premium": p["entry_price"],
                   "qty": int(p["entry_qty"]), "strategy": p["strategy"],
                   "attribution": p["attribution"], "actual_pnl": round(p["actual_exit_pnl"], 2),
                   "cells": {}}
            structure_ok = (str(p["base_shape"].get("stop_mode")) == "structure"
                            and p.get("trigger_level") is not None)
            any_valid = False
            for c in CELLS:
                fa = flat_after[c]
                if fa is not None and entry_dt < fa:
                    suppressed[c] += 1
                    rec["cells"][c] = {"suppressed": True, "pnl": 0.0}
                    continue
                res = walk_exit_manager(
                    symbol=p["symbol"], side=side, entry_time_et=entry_dt,
                    entry_premium=float(p["entry_price"]), qty=int(p["entry_qty"]),
                    exit_shape=cell_shape(p["base_shape"], c),
                    structure_stop_enabled=structure_ok,
                    trigger_level=(float(p["trigger_level"]) if structure_ok else None),
                    strategy=p["strategy"], time_stop_et=TIME_STOP,
                    opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=spy5,
                    opt_df_resolution="1min", frame="et-v2")
                if res.exit_reason == "no_bars_after_entry":
                    rec["cells"][c] = {"invalid": True, "pnl": 0.0}
                    continue
                any_valid = True
                flat_after[c] = res.exit_time_et
                rec["cells"][c] = {
                    "pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
                    "exit_ts": res.exit_time_et.isoformat() if res.exit_time_et else None,
                    "reached_tp1": any(leg.stage == "tp1" for leg in res.legs),
                    "stages": [leg.stage for leg in res.legs],
                }
            if not any_valid:
                # every cell either suppressed this entry (sequential one-position
                # convention: the prior wave position was still open at this entry time in
                # EVERY cell -- pre-TP1 exits are cell-identical, so this is the common
                # case) or had no bars. Disclosed, never silently dropped (C7).
                if all(rec["cells"].get(c, {}).get("suppressed") for c in CELLS):
                    suppressed_all.append({"arm": p["arm"], "date": p["date_et"],
                                           "symbol": p["symbol"], "entry_ts": p["entry_ts_et"],
                                           "actual_pnl": round(p["actual_exit_pnl"], 2)})
                else:
                    no_bars.append(p)
                continue
            per_pos.append(rec)

    # --------------------------------------------------------- aggregation (frozen slices)
    def cell_pnls(rows, c):
        return [r["cells"][c]["pnl"] for r in rows
                if c in r["cells"] and not r["cells"][c].get("suppressed")
                and not r["cells"][c].get("invalid")]

    def block(rows):
        out = {}
        for c in CELLS:
            vals = cell_pnls(rows, c)
            out[c] = {"n": len(vals), "total": round(sum(vals), 2)}
        out["delta_B_minus_CONTROL"] = round(out["B_BE_FLOOR"]["total"] - out["CONTROL"]["total"], 2)
        out["delta_C_minus_CONTROL"] = round(out["C_BE_FLOOR_TGT25"]["total"] - out["CONTROL"]["total"], 2)
        return out

    overall = block(per_pos)
    overall["actual_broker_total_walked_subset"] = round(sum(r["actual_pnl"] for r in per_pos), 2)
    overall["actual_broker_total_full_population"] = round(
        sum(r["actual_pnl"] for r in per_pos)
        + sum(s["actual_pnl"] for s in suppressed_all)
        + sum(p["actual_exit_pnl"] for p in no_bars), 2)
    overall["n_positions_walked"] = len(per_pos)
    overall["n_no_bars"] = len(no_bars)
    overall["n_suppressed_all_cells"] = len(suppressed_all)
    overall["suppressed_all_cells_actual_pnl"] = round(
        sum(s["actual_pnl"] for s in suppressed_all), 2)
    overall["suppressed_all_cells_rows"] = suppressed_all
    overall["suppressed_per_cell"] = dict(suppressed)
    overall["n_reached_tp1"] = {
        c: sum(1 for r in per_pos if r["cells"].get(c, {}).get("reached_tp1")) for c in CELLS}
    overall["attribution_fallback_n"] = sum(1 for r in per_pos if r["attribution"] != "ledger_row")
    overall["attribution_fallback_rows"] = [
        {"arm": r["arm"], "date": r["date"], "symbol": r["symbol"], "entry_ts": r["entry_ts"]}
        for r in per_pos if r["attribution"] != "ledger_row"]

    by_day = {}
    for d in sorted({r["date"] for r in per_pos}):
        rows = [r for r in per_pos if r["date"] == d]
        b = block(rows)
        b["archetype"] = (arch.get(d) or {}).get("archetype", "UNTAGGED")
        by_day[d] = b

    def rollup(dates):
        return block([r for r in per_pos if r["date"] in dates])

    arch_of = {d: (arch.get(d) or {}).get("archetype", "UNTAGGED") for d in by_day}
    by_arch = {}
    for a in sorted(set(arch_of.values())):
        by_arch[a] = rollup({d for d, aa in arch_of.items() if aa == a})
    trend_days = {d for d, a in arch_of.items() if a in TREND_LIKE}
    chop_days = {d for d, a in arch_of.items() if a in CHOP_LIKE}
    other_days = {d for d, a in arch_of.items() if a not in TREND_LIKE | CHOP_LIKE}

    by_arm = {arm: block([r for r in per_pos if r["arm"] == arm])
              for arm in sorted({r["arm"] for r in per_pos})}
    winners = block([r for r in per_pos if r["actual_pnl"] > 0])
    losers = block([r for r in per_pos if r["actual_pnl"] <= 0])

    dates_sorted = sorted(by_day)
    third = max(1, len(dates_sorted) // 3)
    thirds = [set(dates_sorted[:third]), set(dates_sorted[third:2 * third]),
              set(dates_sorted[2 * third:])]
    subwindows = [rollup(t) for t in thirds]

    # gates (frozen)
    deltas_by_day = {d: by_day[d]["delta_B_minus_CONTROL"] for d in by_day}
    best_day = max(deltas_by_day, key=lambda d: deltas_by_day[d])
    g1 = overall["delta_B_minus_CONTROL"] > 0
    chop_block = rollup(chop_days)
    g2 = chop_block["delta_B_minus_CONTROL"] >= 0
    g3 = (overall["delta_B_minus_CONTROL"] - deltas_by_day[best_day]) > 0
    sw = [s["delta_B_minus_CONTROL"] for s in subwindows]
    g4 = sum(1 for v in sw if v >= 0) >= 2 and all(v > -250 for v in sw)
    gates = {"G1_overall_positive": g1, "G2_chop_survival": g2,
             "G3_ex_best_day_positive": g3, "G4_subwindow_stability": g4,
             "best_delta_day": best_day, "best_delta_value": deltas_by_day[best_day],
             "subwindow_deltas": sw}
    if all([g1, g2, g3, g4]):
        verdict = "ARM_ELIGIBLE"
    elif g1 and not g2:
        verdict = "REGIME_CONDITIONAL_TREND__DO_NOT_ARM"
    else:
        verdict = "DO_NOT_ARM"

    # exit-mechanism distribution shift (descriptive)
    mech = {c: dict(Counter(r["cells"][c].get("exit_reason", "?") for r in per_pos
                            if not r["cells"].get(c, {}).get("suppressed")
                            and not r["cells"].get(c, {}).get("invalid"))) for c in CELLS}

    return {
        "prereg": "PREREG-RUNNER-BE-FLOOR-2026-08-06 (commit 61bc6507, frozen before this runner)",
        "generated_et": dt.datetime.now().isoformat(timespec="seconds"),
        "overall": overall,
        "gates": gates, "verdict": verdict,
        "rollups": {"trend_like": rollup(trend_days), "chop_like": chop_block,
                    "other_untagged": rollup(other_days),
                    "trend_days": sorted(trend_days), "chop_days": sorted(chop_days),
                    "other_days": sorted(other_days)},
        "by_archetype": by_arch, "by_day": by_day, "by_arm": by_arm,
        "winners_cohort_actual": winners, "losers_cohort_actual": losers,
        "subwindows": subwindows,
        "exit_mechanisms": mech,
        "per_position": per_pos,
    }


def main() -> int:
    out = run()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    o = out["overall"]
    print(f"walked {o['n_positions_walked']} positions | no_bars {o['n_no_bars']} | "
          f"suppressed_all_cells {o['n_suppressed_all_cells']} "
          f"(actual {o['suppressed_all_cells_actual_pnl']})")
    print(f"actual broker: walked subset {o['actual_broker_total_walked_subset']} | "
          f"full population {o['actual_broker_total_full_population']}")
    for c in CELLS:
        print(f"  {c}: n={o[c]['n']} total={o[c]['total']}")
    print(f"delta B-CONTROL: {o['delta_B_minus_CONTROL']} | delta C-CONTROL: {o['delta_C_minus_CONTROL']}")
    print("gates:", json.dumps(out["gates"], default=str))
    print("VERDICT:", out["verdict"])
    print("trend_like:", json.dumps(out["rollups"]["trend_like"]))
    print("chop_like:", json.dumps(out["rollups"]["chop_like"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
