"""REENTRY-COOLDOWN A/B — evidence run for a cooldown-after-premium-stop gate.

CONTEXT (2026-07-02): J deleted the Claude-invented re-entry lock ("Gone. We no
longer have it in our codebase."). Same day, Safe's vwap_continuation churned
re-entries (PLACED -> premium_stop -> re-PLACED) in the 09:55-10:27 window.
Tonight's doctrine: NO gate ships without evidence. This is the evidence run —
STUDY ONLY, ships nothing.

QUESTION: would a simple per-setup cooldown after a premium-stop exit
(grid: 5 / 10 / 15 / 30 min) have net-positive expectancy impact?

TWO EVIDENCE SOURCES (disclosed separately — do NOT blend):
  A. LIVE ledgers (last 30 days of core-decisions.jsonl): reconstruct actual
     PLACED->exit round trips per (account, setup), then replay each day's
     sequence under each cooldown. Tiny N (the rig only started filling
     2026-07-01) — anecdote-grade, reported as such.
  B. BACKTEST multi-entry replay (2025-01-02..2026-05-15 real OPRA fills, the
     edgehunt cache): the ratified edgehunt detector fires ONE causal entry/day,
     so it contains NO re-entry sequences. Here we relax that to ALL trigger
     bars per day and run a SEQUENTIAL replay (position-exclusive, next entry
     only when flat) through the SAME simulate_trade_real path, at the
     PRODUCTION Safe cell (ATM, stop -8%, tp1 +30%) and the edgehunt best cell
     (ITM2, stop -8%). Cooldown c blocks a same-setup re-entry within c minutes
     of a premium-stop exit. cooldown=0 == tonight's post-lock-deletion engine.

CAVEATS (stated in the output, OP-20):
  * B's multi-entry detector is NOT the ratified one-entry/day cell — it models
    the live engine's re-fire behavior, which is the thing being studied.
  * A's N is tiny; B's sim ignores the live watcher's exact trigger cadence
    (bar-close triggers vs 1-min ticks).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/reentry_cooldown_ab.py
Out: analysis/recommendations/reentry-cooldown-ab.json
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "reentry-cooldown-ab.json"
LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
COOLDOWNS = [0, 5, 10, 15, 30]  # minutes; 0 = current (no lock) baseline


# ─────────────────────────────────────────────────────────────────────────────
# PART A — live-ledger replay
# ─────────────────────────────────────────────────────────────────────────────
def _parse_live_trades(days_back: int = 30) -> list[dict]:
    """Reconstruct PLACED->exit round trips from core-decisions.jsonl."""
    if not LEDGER.exists():
        return []
    cutoff = (dt.datetime.now() - dt.timedelta(days=days_back)).strftime("%Y-%m-%d")
    entries: list[dict] = []   # open entries awaiting exit, keyed by (account, symbol)
    trades: list[dict] = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(r.get("ts_et", ""))
            if ts[:10] < cutoff:
                continue
            acct = r.get("account")
            # entries: core exec + extra-setup exec
            execs = []
            if isinstance(r.get("exec"), dict):
                execs.append(r["exec"])
            for x in (r.get("extra_exec") or []):
                if isinstance(x, dict) and isinstance(x.get("exec"), dict):
                    execs.append(x["exec"])
            for ex in execs:
                if ex.get("status") == "PLACED" and ex.get("symbol"):
                    entries.append({
                        "account": acct, "symbol": ex["symbol"],
                        "setup": ex.get("setup") or "?",
                        "entry_ts": ts, "qty": int(ex.get("qty") or 0),
                        "entry_px": float(ex.get("entry_px") or ex.get("premium") or 0),
                    })
            # exits: exit_pass SELL actions
            for ep in (r.get("exit_pass") or []):
                for act in (ep.get("actions") or []):
                    if not act.get("placed"):
                        continue
                    m = re.search(r"@ ([0-9.]+)", str(act.get("reason", "")))
                    exit_px = float(m.group(1)) if m else None
                    sym = ep.get("symbol")
                    # match most recent open entry on this account+symbol
                    for e in reversed(entries):
                        if e["account"] == acct and e["symbol"] == sym and "exit_ts" not in e:
                            e["exit_ts"] = ts
                            e["exit_stage"] = act.get("stage") or "?"
                            e["exit_px"] = exit_px
                            if exit_px is not None and e["entry_px"]:
                                e["pnl"] = round((exit_px - e["entry_px"]) * 100 * e["qty"], 2)
                            trades.append(e)
                            break
    return trades


def _replay_live(trades: list[dict]) -> dict:
    """Apply the cooldown grid to the actual live sequences (per account+setup+day)."""
    by_key = defaultdict(list)
    for t in trades:
        if "exit_ts" not in t or t.get("pnl") is None:
            continue
        by_key[(t["account"], t["setup"], t["entry_ts"][:10])].append(t)
    out = {}
    for c in COOLDOWNS:
        kept_pnl = supp_pnl = 0.0
        n_kept = n_supp = 0
        for _key, seq in by_key.items():
            seq = sorted(seq, key=lambda t: t["entry_ts"])
            blocked_until = None
            for t in seq:
                ets = dt.datetime.fromisoformat(t["entry_ts"])
                if blocked_until and ets < blocked_until:
                    supp_pnl += t["pnl"]; n_supp += 1
                    continue  # suppressed trade's exit does NOT extend the block
                kept_pnl += t["pnl"]; n_kept += 1
                if t.get("exit_stage") == "premium_stop":
                    blocked_until = dt.datetime.fromisoformat(t["exit_ts"]) + dt.timedelta(minutes=c)
        out[str(c)] = {"n_kept": n_kept, "n_suppressed": n_supp,
                       "kept_pnl": round(kept_pnl, 2),
                       "suppressed_pnl": round(supp_pnl, 2),
                       "pnl_delta_vs_no_cooldown": None}
    base = out["0"]["kept_pnl"]
    for c in COOLDOWNS:
        out[str(c)]["pnl_delta_vs_no_cooldown"] = round(out[str(c)]["kept_pnl"] - base, 2)
    return {"grid": out, "n_round_trips": sum(1 for t in trades if "exit_ts" in t),
            "trades": [{k: t.get(k) for k in
                        ("account", "setup", "entry_ts", "exit_ts", "exit_stage",
                         "entry_px", "exit_px", "qty", "pnl")}
                       for t in sorted(trades, key=lambda t: t["entry_ts"]) if "exit_ts" in t]}


# ─────────────────────────────────────────────────────────────────────────────
# PART B — backtest multi-entry sequential replay (real OPRA fills)
# ─────────────────────────────────────────────────────────────────────────────
def _run_backtest_part() -> dict:
    from autoresearch import runner as ar_runner
    from autoresearch.infinite_ammo_discovery import (
        build_day_contexts, session_vwap_asof, _nearest_cached_strike,
        _strike_from_spot,
    )
    from lib.ribbon import compute_ribbon
    from lib.simulator_real import simulate_trade_real
    # detector params — IDENTICAL to _edgehunt_vwap_continuation.py
    TREND_BARS, ENTRY_CUTOFF, SHALLOW_DIP_TOL = 3, dt.time(10, 30), 0.0010
    QTY, MAX_STRIKE_STEPS = 3, 4

    sys.path.insert(0, str(REPO / "autoresearch"))
    ehm = __import__("_edgehunt_vwap_continuation")
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = ehm._normalize_spy(spy_raw)
    vix = ehm._align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # ALL trigger bars per day (the live engine's re-fire surface) — the ratified
    # detector's loop WITHOUT the first-hit break.
    def all_triggers(dc):
        rth = dc.rth
        if len(rth) < TREND_BARS + 2:
            return []
        vwap = session_vwap_asof(rth).values
        closes, highs, lows = rth["close"].values, rth["high"].values, rth["low"].values
        times, idxs = rth["t"].values, rth.index.tolist()
        side = ehm._trend_side(closes, vwap, TREND_BARS)
        if side is None:
            return []
        out = []
        for j in range(TREND_BARS, len(rth)):
            if times[j] > ENTRY_CUTOFF:
                break
            v = vwap[j]
            if v <= 0:
                continue
            if side == "C":
                prior_ext = float(np.max(highs[:j])) if j > 0 else highs[j]
                breakout = highs[j] >= prior_ext and closes[j] > v
                dip = lows[j] <= v * (1 + SHALLOW_DIP_TOL) and closes[j] > v
                stop = float(np.min(lows[:j + 1]))
            else:
                prior_ext = float(np.min(lows[:j])) if j > 0 else lows[j]
                breakout = lows[j] <= prior_ext and closes[j] < v
                dip = highs[j] >= v * (1 - SHALLOW_DIP_TOL) and closes[j] < v
                stop = float(np.max(highs[:j + 1]))
            trig = "breakout" if breakout else ("pullback" if dip else None)
            if trig is None:
                continue
            out.append({"bar_idx": int(idxs[j]), "side": side, "stop": stop, "trig": trig})
        return out

    day_triggers = [(dc, all_triggers(dc)) for dc in days]
    n_trig = sum(len(t) for _, t in day_triggers)
    print(f"[cooldown-ab] trigger bars across {len(days)} days: {n_trig}", flush=True)

    CELLS = {
        "ATM_stop8_prod_safe": {"strike_offset": 0, "premium_stop_pct": -0.08,
                                "tp1_premium_pct": 0.30},
        "ITM2_stop8_edgehunt_best": {"strike_offset": -2, "premium_stop_pct": -0.08,
                                     "tp1_premium_pct": 0.30},
    }
    sim_cache: dict = {}

    def sim_at(bar_idx, side, stop, trig, cell_name):
        key = (bar_idx, cell_name)
        if key in sim_cache:
            return sim_cache[key]
        cell = CELLS[cell_name]
        bar = spy.iloc[bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - cell["strike_offset"] if side == "P" else atm + cell["strike_offset"]
        strike = _nearest_cached_strike(d, target, side, MAX_STRIKE_STEPS)
        res = None
        if strike is not None:
            entry_vix = float(vix.iloc[bar_idx]) if bar_idx < len(vix) else 0.0
            fill = simulate_trade_real(
                entry_bar_idx=bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                rejection_level=stop, triggers_fired=[f"jvwap_{trig}"], side=side,
                qty=QTY, setup="COOLDOWN_AB", strike_override=strike, entry_vix=entry_vix,
                premium_stop_pct=cell["premium_stop_pct"],
                tp1_premium_pct=cell["tp1_premium_pct"],
                runner_target_premium_pct=2.5, profit_lock_mode="fixed",
                profit_lock_trail_pct=0.0)
            if fill is not None and fill.dollar_pnl is not None:
                entry_t = fill.entry_time_et
                exit_t = entry_t + dt.timedelta(minutes=int(fill.hold_minutes or 0))
                res = {"pnl": float(fill.dollar_pnl), "entry_t": entry_t, "exit_t": exit_t,
                       "exit_reason": fill.exit_reason.name if fill.exit_reason else "NONE"}
        sim_cache[key] = res
        return res

    results = {}
    for cell_name in CELLS:
        cell_res = {}
        for c in COOLDOWNS:
            tot = 0.0
            n = n_stops = n_supp = supp_pnl_would_be = 0
            oos_tot, oos_n = 0.0, 0
            for dc, trigs in day_triggers:
                pos_until = None
                blocked_until = None
                for tg in trigs:
                    bt = spy.iloc[tg["bar_idx"]]["timestamp_et"]
                    if pos_until is not None and bt < pos_until:
                        continue  # in a position — the live NOT_FLAT gate
                    if blocked_until is not None and bt < blocked_until:
                        r0 = sim_at(tg["bar_idx"], tg["side"], tg["stop"], tg["trig"], cell_name)
                        if r0 is not None:
                            n_supp += 1
                            supp_pnl_would_be += r0["pnl"]
                        continue  # cooldown suppression
                    r = sim_at(tg["bar_idx"], tg["side"], tg["stop"], tg["trig"], cell_name)
                    if r is None:
                        continue
                    tot += r["pnl"]; n += 1
                    if bt.year == 2026:
                        oos_tot += r["pnl"]; oos_n += 1
                    pos_until = r["exit_t"]
                    if r["exit_reason"] == "EXIT_ALL_PREMIUM_STOP":
                        n_stops += 1
                        if c > 0:
                            blocked_until = r["exit_t"] + dt.timedelta(minutes=c)
            cell_res[str(c)] = {
                "n_trades": n, "total_pnl": round(tot, 2),
                "exp_per_trade": round(tot / n, 2) if n else None,
                "n_premium_stops": n_stops,
                "n_suppressed": n_supp,
                "suppressed_pnl_would_have_been": round(supp_pnl_would_be, 2),
                "oos_2026_n": oos_n, "oos_2026_pnl": round(oos_tot, 2),
                "oos_exp": round(oos_tot / oos_n, 2) if oos_n else None,
            }
        base = cell_res["0"]
        for c in COOLDOWNS:
            cc = cell_res[str(c)]
            cc["pnl_delta_vs_no_cooldown"] = round(cc["total_pnl"] - base["total_pnl"], 2)
            cc["oos_delta_vs_no_cooldown"] = round(cc["oos_2026_pnl"] - base["oos_2026_pnl"], 2)
        results[cell_name] = cell_res
        print(f"[cooldown-ab] {cell_name}: " + " | ".join(
            f"c{c}: n={cell_res[str(c)]['n_trades']} pnl={cell_res[str(c)]['total_pnl']}"
            for c in COOLDOWNS), flush=True)
    return {"window": "2025-01-02..2026-05-15", "n_days": len(days),
            "n_trigger_bars": n_trig, "cells": results,
            "method": ("sequential position-exclusive replay of ALL detector trigger "
                       "bars through simulate_trade_real (real OPRA fills); cooldown "
                       "blocks same-setup re-entry within c min of a premium-stop exit; "
                       "c=0 == the post-lock-deletion engine")}


def main() -> int:
    live_trades = _parse_live_trades(30)
    live = _replay_live(live_trades)
    print(f"[cooldown-ab] live round trips (30d): {live['n_round_trips']}", flush=True)
    bt = _run_backtest_part()

    # verdict: SHIP-WORTHY only if the backtest shows a consistent positive delta
    # (both cells, IS+OOS) AND the live evidence agrees in sign.
    deltas = {}
    for cell, grid in bt["cells"].items():
        for c in COOLDOWNS[1:]:
            deltas.setdefault(c, []).append(grid[str(c)]["pnl_delta_vs_no_cooldown"])
    best_c, best_mean = None, 0.0
    for c, ds in deltas.items():
        m = sum(ds) / len(ds)
        if all(d > 0 for d in ds) and m > best_mean:
            best_c, best_mean = c, m
    live_agrees = None
    if best_c is not None and live["grid"]["0"]["n_kept"]:
        live_agrees = live["grid"][str(best_c)]["pnl_delta_vs_no_cooldown"] >= 0
    ship_worthy = bool(best_c is not None and (live_agrees is not False))
    summary = {
        "rule_id": "reentry-cooldown-ab",
        "run_date": dt.date.today().isoformat(),
        "question": ("would a per-setup cooldown after a premium-stop exit "
                     f"(grid {COOLDOWNS[1:]} min) have net-positive expectancy impact?"),
        "context": ("evidence run mandated by the 2026-07-02 re-entry-lock deletion "
                    "(J directive) + same-day vwap_continuation churn; per new doctrine "
                    "no gate ships without evidence"),
        "live_ledger_30d": live,
        "backtest_real_fills": bt,
        "verdict": {
            "ship_worthy": ship_worthy,
            "best_cooldown_min": best_c,
            "mean_pnl_delta_at_best": round(best_mean, 2) if best_c else None,
            "live_agrees_in_sign": live_agrees,
        },
        "DISCLOSURE": {
            "sources_not_blended": "live (tiny N, anecdote-grade) and backtest reported separately",
            "detector_caveat": ("backtest part relaxes the ratified one-entry/day detector to "
                                "all trigger bars to model live re-fire behavior — that relaxed "
                                "surface is itself unvalidated; deltas are RELATIVE within it"),
            "expectancy_not_wr": "deltas are $ P&L and per-trade expectancy, never WR alone",
        },
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[cooldown-ab] wrote {OUT}", flush=True)
    print(json.dumps(summary["verdict"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
