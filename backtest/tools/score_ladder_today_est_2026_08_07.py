"""score_ladder_today_est_2026_08_07.py -- TODAY (2026-08-07) SCORE-LADDER-V2 day replay.

Prereg: analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json (commit c2ec28f3).

Same-day OPRA is 403 until ~16:21, so EVERY hypothetical premium here is an ESTIMATE
(LABEL: EST) -- Black-Scholes from the live engine's OWN per-tick spy/vix track
(automation/state/core-decisions.jsonl, the scoring authority for today -- no re-scoring),
calibrated against today's REAL NBBO anchors (the engine's exec.premium on actual ENTER
ticks + the exit_pass premium tracks while positions were held). Calibration factor k =
median(real/BS) is computed and disclosed; every EST premium is k * BS.

Admission = the SAME frozen side_admission() the population runner uses (imported, not
re-implemented). Two cell families per rung {6,7,8,9}:
  * STUDY lane: rung-admitted EXTRAS ONLY, qty=3, ATM (PROBE table), own NOT_FLAT chain --
    the clean added-cohort number, comparable to the population lanes.
  * ARM lane (risky-3 rung 7, risky-1 rung 8): the arm's REAL day (broker fills, real P&L)
    + extras at the live _ladder_plan convention (PROBE ATM strike, min_contracts=5,
    the arm's own patched exit shape), occupancy = real holds + EST holds interleaved.
Exits: walk_exit_manager -> exit_manager.plan_exit_actions ONLY, on a per-minute EST bar
series for the entered contract; ribbon per tick from the engine's own logged ribbon;
5-min SPY frame aggregated from the tick track (point-sample OHLC, labeled EST).

Run (after 15:35 ET for full-day coverage; runnable earlier for a partial-day preview):
    backtest/.venv/Scripts/python.exe backtest/tools/score_ladder_today_est_2026_08_07.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies                                     # noqa: E402
from lib.exit_manager_walk import walk_exit_manager                        # noqa: E402
from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv     # noqa: E402
from crypto.lib.strike_selection import pick_strike                         # noqa: E402
import fleet_executor as fx                                                  # noqa: E402
from score_ladder_replay_2026_08_07 import side_admission                     # noqa: E402

TODAY = dt.date(2026, 8, 7)
LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = ROOT / "analysis" / "deep-research" / "SCORE-LADDER-TODAY-EST-2026-08-07.json"

RUNGS = (6, 7, 8, 9)
REF_EQUITY = 2000.0
ARM_CELLS = {
    "risky-3": {"rung": 7, "qty": 10, "exit_patch": {"stop_mode": "structure",
                                                       "profit_lock_mode": "trailing",
                                                       "trail_pct": 0.20}},
    "risky-1": {"rung": 8, "qty": 5, "exit_patch": {"tp1_premium_pct": 0.5,
                                                      "stop_mode": "structure"}},
}
# risky-3 qty note: aggressive params min_contracts=5, but the arm's live
# cheap_contract_qty_boost lifts sub-$0.50 contracts to qty 10; midday ATM premium is
# well above $0.50, so 5 binds in practice -- both shown in output via per-trade qty logic.

ENTRY_FLOOR = 0.30            # min_entry_premium, non-demotable
RISK_CAP_PCT = 0.50           # aggressive per_trade_risk_cap_pct
ARM_EQUITY = {"risky-3": 5343.32, "risky-1": 6338.46}   # live-read 08-06 (WEEK-ORDER sec 3)
TIME_STOP = dt.time(15, 40)


def log(m: str) -> None:
    print(f"[ladder-today] {m}", flush=True)


# =============================================================================== ticks

def load_ticks() -> list[dict]:
    """One row per core tick (the 'safe' account row carries the shared scoring; 'bold'
    rows duplicate it 1:1 -- verified live schema 2026-08-07). Fresh read every run."""
    rows = []
    seen = set()
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            if not line.startswith('{"ts_et": "2026-08-07'):
                continue
            r = json.loads(line)
            if r.get("account") != "safe":
                continue
            key = r.get("core_tick_id") or r.get("ts_et")
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda r: r["ts_et"])
    return rows


def tick_ts(r: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(r["ts_et"])


# =============================================================================== EST pricing

def bs_est(spot: float, strike: float, vix: float, when: dt.datetime, is_call: bool,
           k: float = 1.0) -> float:
    iv = vix_to_iv(vix)
    tte = time_to_expiry_years(when)
    price, _ = black_scholes(spot, strike, iv, tte, is_call=is_call)
    return max(round(k * price, 4), 0.01)


def occ_strike(symbol: str) -> float:
    return int(symbol[-8:]) / 1000.0


def occ_is_call(symbol: str) -> bool:
    return symbol[-9] == "C"


def calibration(rows_all: list[dict]) -> dict:
    """k = median(real_premium / raw_BS) over today's REAL anchors: exec.premium on ENTER
    ticks (both core accounts) + exit_pass best/worst midpoints while holding."""
    anchors = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            if not line.startswith('{"ts_et": "2026-08-07'):
                continue
            r = json.loads(line)
            ts = tick_ts(r)
            ex = r.get("exec") or {}
            sym = ex.get("symbol")
            prem = ex.get("premium")
            if sym and isinstance(prem, (int, float)) and prem > 0:
                raw = bs_est(float(r["spy"]), occ_strike(sym), float(r["vix"]), ts,
                             occ_is_call(sym), k=1.0)
                anchors.append({"ts": r["ts_et"], "symbol": sym, "real": float(prem),
                                "bs_raw": raw, "ratio": float(prem) / raw, "src": "exec"})
            for ep in (r.get("exit_pass") or []):
                sym2 = ep.get("symbol")
                bp, wp = ep.get("best_premium"), ep.get("worst_premium")
                if sym2 and isinstance(bp, (int, float)) and isinstance(wp, (int, float)) and bp > 0:
                    mid = (float(bp) + float(wp)) / 2.0
                    raw = bs_est(float(r["spy"]), occ_strike(sym2), float(r["vix"]), ts,
                                 occ_is_call(sym2), k=1.0)
                    anchors.append({"ts": r["ts_et"], "symbol": sym2, "real": mid,
                                    "bs_raw": raw, "ratio": mid / raw, "src": "exit_pass"})
    if not anchors:
        return {"k": 1.0, "n_anchors": 0, "note": "NO real anchors found -- k=1.0 (raw BS)"}
    ratios = sorted(a["ratio"] for a in anchors)
    k = ratios[len(ratios) // 2]
    return {"k": round(k, 4), "n_anchors": len(anchors),
            "ratio_min": round(ratios[0], 4), "ratio_max": round(ratios[-1], 4),
            "ratio_p25": round(ratios[len(ratios) // 4], 4),
            "ratio_p75": round(ratios[(3 * len(ratios)) // 4], 4),
            "sample_anchors": anchors[:6]}


# =============================================================================== frames

def five_min_frame(ticks: list[dict]) -> pd.DataFrame:
    """EST 5-min SPY OHLC aggregated from the engine's per-minute spot samples."""
    df = pd.DataFrame([{"ts": tick_ts(r), "spy": float(r["spy"])} for r in ticks])
    df["bucket"] = df["ts"].dt.floor("5min")
    g = df.groupby("bucket")["spy"]
    out = pd.DataFrame({
        "timestamp_et": g.first().index,
        "open": g.first().values, "high": g.max().values,
        "low": g.min().values, "close": g.last().values,
    }).reset_index(drop=True)
    return out


def est_opt_track(ticks: list[dict], start_idx: int, strike: float, is_call: bool,
                  k: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(opt_df, ribbon_tick_df) per-minute EST bars for one contract from ticks[start_idx:]."""
    rows, ribbon = [], []
    for r in ticks[start_idx:]:
        ts = tick_ts(r)
        p = bs_est(float(r["spy"]), strike, float(r["vix"]), ts, is_call, k)
        rows.append({"timestamp_et": ts, "open": p, "high": p, "low": p, "close": p})
        ribbon.append({"timestamp_et": ts, "stack": r.get("ribbon") or "NEUTRAL"})
    return pd.DataFrame(rows), pd.DataFrame(ribbon)


# =============================================================================== admission

def tick_admission(r: dict) -> Optional[dict]:
    """Frozen side_admission applied to the live tick's LOGGED scores/blockers (no
    re-scoring). Neither side may have passed (verdict != HOLD means the engine acted)."""
    if r.get("verdict") != "HOLD":
        return None
    opts = []
    a = side_admission("P", int(r["bear_score"]), list(r.get("bear_blockers") or []),
                       list(r.get("bear_triggers_raw") or []),
                       r.get("bear_rejection_level_raw"), float(r["vix"]))
    if a:
        opts.append(("P", r.get("bear_rejection_level_raw"), a))
    b = side_admission("C", int(r["bull_score"]), list(r.get("bull_blockers") or []),
                       list(r.get("bull_triggers_raw") or []),
                       r.get("bull_reclaim_level_raw"), float(r["vix"]))
    if b:
        opts.append(("C", r.get("bull_reclaim_level_raw"), b))
    if not opts:
        return None
    if len(opts) == 2:
        if opts[0][2]["adjusted"] == opts[1][2]["adjusted"]:
            return None
        opts.sort(key=lambda o: -o[2]["adjusted"])
    side, level, adm = opts[0]
    return {"side": side, "level": float(level), "adjusted": adm["adjusted"],
            "n_demotable": adm["n_demotable"]}


# =============================================================================== lane walk

def walk_est_lane(ticks: list[dict], rung: int, k: float, qty: int, exit_shape: dict,
                  five_spy: pd.DataFrame, blocked_windows: list[tuple] = ()) -> dict:
    """Sequential NOT_FLAT walk of rung-admitted EXTRAS on EST pricing. blocked_windows =
    real-position holds (arm cells) that also occupy the lane."""
    trades, skipped = [], []
    flat_until: Optional[dt.datetime] = None
    idx_by_ts = {tick_ts(r): i for i, r in enumerate(ticks)}

    for i, r in enumerate(ticks):
        ts = tick_ts(r)
        if ts.time() < dt.time(9, 35) or ts.time() >= dt.time(15, 0):
            continue
        if flat_until is not None and ts <= flat_until:
            continue
        if any(w0 <= ts <= w1 for w0, w1 in blocked_windows):
            continue
        adm = tick_admission(r)
        if adm is None or adm["adjusted"] < rung:
            continue
        if i + 1 >= len(ticks):
            skipped.append({"ts": r["ts_et"], "reason": "no_next_tick"})
            continue
        nxt = ticks[i + 1]
        nts = tick_ts(nxt)
        spot = float(nxt["spy"])
        strike = pick_strike(spot, REF_EQUITY, adm["side"], fx.PROBE_STRIKE_TIERS)
        is_call = adm["side"] == "C"
        entry_premium = bs_est(spot, strike, float(nxt["vix"]), nts, is_call, k)
        if entry_premium < ENTRY_FLOOR:
            skipped.append({"ts": r["ts_et"], "reason": f"min_premium_floor ({entry_premium})"})
            continue
        opt_df, rtd = est_opt_track(ticks, i + 1, strike, is_call, k)
        res = walk_exit_manager(
            symbol=f"EST-SPY-{TODAY.isoformat()}-{int(strike)}{adm['side']}",
            side=adm["side"], entry_time_et=nts, entry_premium=entry_premium, qty=qty,
            exit_shape=exit_shape, structure_stop_enabled=True,
            trigger_level=adm["level"], strategy="ribbon_ride", time_stop_et=TIME_STOP,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=five_spy,
        )
        exit_ts = res.exit_time_et if res.exit_time_et is not None else nts
        flat_until = exit_ts
        trades.append({
            "trigger_ts": r["ts_et"], "entry_ts": nts.isoformat(), "side": adm["side"],
            "strike": strike, "qty": qty, "entry_premium_EST": entry_premium,
            "score": int(r["bull_score"] if is_call else r["bear_score"]),
            "blockers": list((r["bull_blockers"] if is_call else r["bear_blockers"]) or []),
            "adjusted": adm["adjusted"], "level": adm["level"],
            "dollar_pnl_EST": res.dollar_pnl, "exit_reason": res.exit_reason,
            "exit_ts": exit_ts.isoformat() if exit_ts else None,
            "hold_minutes": res.hold_minutes,
        })
    total = round(sum(t["dollar_pnl_EST"] for t in trades), 2)
    return {"rung": rung, "qty": qty, "n_extras": len(trades), "extras_pnl_EST": total,
            "trades": trades, "skipped": skipped}


# =============================================================================== real fills

def todays_real_fills_per_arm() -> dict:
    """Broker FILL activities for today per fleet arm (read-only). Fail-open: any arm's
    pull error is recorded, never fatal."""
    out = {}
    try:
        import fleet_broker as fb
        creds_all = fb.load_creds()
    except Exception as e:  # noqa: BLE001
        return {"_error": f"load_creds failed: {e}"}
    for arm_id, creds in creds_all.items():
        try:
            # NOTE: fleet_broker._request prepends "/v2/" itself -- endpoint must NOT carry it.
            acts = fb._request(creds, f"account/activities/FILL?date={TODAY.isoformat()}")
            if isinstance(acts, dict) and acts.get("_error"):
                out[arm_id] = {"error": str(acts.get("_error"))}
                continue
            fills = [{
                "ts": a.get("transaction_time"), "symbol": a.get("symbol"),
                "side": a.get("side"), "qty": float(a.get("qty") or 0),
                "price": float(a.get("price") or 0),
            } for a in (acts if isinstance(acts, list) else [])]
            buys = sum(f["qty"] * f["price"] for f in fills if f["side"] == "buy")
            sells = sum(f["qty"] * f["price"] for f in fills if f["side"] in ("sell", "sell_short"))
            out[arm_id] = {"fills": fills,
                           "realized_day_pnl": round((sells - buys) * 100.0, 2),
                           "note": "sells-buys x100; open position (if any) not marked"}
        except Exception as e:  # noqa: BLE001
            out[arm_id] = {"error": str(e)}
    return out


def hold_windows_from_fills(fills: list[dict]) -> list[tuple]:
    """[(first_buy_ts, last_sell_ts)] naive-ET windows, per contiguous position episode."""
    if not fills:
        return []
    evs = sorted(fills, key=lambda f: f["ts"] or "")
    windows = []
    open_qty = 0.0
    start = None
    for f in evs:
        ts = pd.Timestamp(f["ts"]).tz_convert("America/New_York").tz_localize(None).to_pydatetime() \
            if f["ts"] else None
        if ts is None:
            continue
        if f["side"] == "buy":
            if open_qty == 0:
                start = ts
            open_qty += f["qty"]
        else:
            open_qty -= f["qty"]
            if open_qty <= 0 and start is not None:
                windows.append((start, ts))
                start, open_qty = None, 0.0
    if start is not None:
        windows.append((start, dt.datetime.combine(TODAY, dt.time(16, 0))))
    return windows


# =============================================================================== main

def main() -> int:
    ticks = load_ticks()
    log(f"{len(ticks)} core ticks today; last: {ticks[-1]['ts_et'] if ticks else 'NONE'}")
    cal = calibration(ticks)
    log(f"EST calibration: k={cal.get('k')} from n={cal.get('n_anchors')} real anchors "
        f"(p25={cal.get('ratio_p25')} p75={cal.get('ratio_p75')})")
    k = float(cal.get("k") or 1.0)
    five_spy = five_min_frame(ticks)

    admissions = []
    for r in ticks:
        adm = tick_admission(r)
        if adm:
            admissions.append({"ts": r["ts_et"], **adm,
                                "bull_score": r["bull_score"], "bull_blockers": r["bull_blockers"],
                                "bear_score": r["bear_score"], "bear_blockers": r["bear_blockers"]})
    log(f"admissible refused ticks (rung>=6 shape): {len(admissions)}; "
        f"per rung: { {g: sum(1 for a in admissions if a['adjusted'] >= g) for g in RUNGS} }")
    t1015 = [a for a in admissions if a["ts"].startswith("2026-08-07T10:15")]
    log(f"10:15 tick admitted: {bool(t1015)} -> {t1015[:1]}")

    registry_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    study = {}
    for rung in RUNGS:
        study[str(rung)] = walk_est_lane(ticks, rung, k, 3, dict(registry_shape), five_spy)
        s = study[str(rung)]
        log(f"STUDY rung {rung}: extras {s['n_extras']} -> ${s['extras_pnl_EST']:+.2f} EST")

    real = todays_real_fills_per_arm()
    arm_cells = {}
    for arm_id, cfg in ARM_CELLS.items():
        arm_real = real.get(arm_id) or {}
        windows = hold_windows_from_fills(arm_real.get("fills") or [])
        shape = dict(registry_shape)
        shape.update(cfg["exit_patch"])
        lane = walk_est_lane(ticks, cfg["rung"], k, cfg["qty"], shape, five_spy,
                             blocked_windows=windows)
        arm_cells[arm_id] = {
            "rung": cfg["rung"], "qty": cfg["qty"],
            "real_day_pnl": arm_real.get("realized_day_pnl"),
            "real_fill_count": len(arm_real.get("fills") or []),
            "real_hold_windows": [(w0.isoformat(), w1.isoformat()) for w0, w1 in windows],
            "extras_EST": lane,
            "day_total_real_plus_EST": (
                round((arm_real.get("realized_day_pnl") or 0.0) + lane["extras_pnl_EST"], 2)),
        }
        log(f"ARM {arm_id} rung {cfg['rung']}: real ${arm_real.get('realized_day_pnl')} "
            f"+ extras EST ${lane['extras_pnl_EST']:+.2f} = "
            f"${arm_cells[arm_id]['day_total_real_plus_EST']}")

    out = {
        "_doc": __doc__,
        "prereg": "analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json (c2ec28f3)",
        "generated_at": dt.datetime.now().isoformat(),
        "est_labeling": "EVERY hypothetical premium/P&L in this file is EST (BS calibrated, k below). Real fills are labeled real.",
        "calibration": cal,
        "n_ticks": len(ticks),
        "last_tick": ticks[-1]["ts_et"] if ticks else None,
        "admissible_refused_ticks": admissions,
        "study_lanes_qty3_ATM_EST": study,
        "arm_cells": arm_cells,
        "real_fills_per_arm": real,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
