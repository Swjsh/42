"""fleet_exit_parity_per_arm.py -- PROFIT-P1-FLEET-EXIT-PARITY (2026-07-11).

Per-arm exit_manager replay of SS-B vs each fleet arm's CURRENT (observed, historical) exit
shape, on THAT ARM'S OWN real fills only (C29: exit knobs never transfer across arms/tiers
without independent per-arm verification -- LESSONS-LEARNED C29). This is the per-arm
breakdown the pooled structure_stop_study.py (layer b) never produced -- that study answers
"does SS-B beat CONTROL across all 4 fleet_rest arms pooled"; this answers "does SS-B beat
CONTROL on safe-1's own fills / safe-3's own fills / risky-1's own fills / risky-3's own fills,
independently" (arms differ by gate selectivity + sizing tier -- C29 says a result on one
cannot be assumed on another).

REUSES, does not reinvent (OP-22):
  * exit_shape_parity_study.py  -- load_fleet_engine_fills, reconstruct_positions (broker-truth
                                    fill ledger -> episode reconstruction, the same grouping
                                    algorithm trade_autopsy.py uses -- C31-safe), fetch_option_bars
                                    (real 1-min Alpaca OPRA bars).
  * structure_stop_study.py     -- CONTROL_SHAPE (the actual shipped -20%/+150%/sell80/fixed
                                    shape -- confirmed against ledger-forensics' own empirical
                                    -20.0% median premium-stop pct-move finding, so this IS what
                                    produced these real fills, not a guess), SS_B_SHAPE (the
                                    certified structure-stop cell: -50% cat cap / +100% TP1
                                    sell66 / trailing-15% runner / structure-primary), the SAME
                                    certified replay engine (replay_structure_aware -- structure
                                    check first, then the LIVE exit_manager.plan_exit_actions
                                    core for catastrophe/TP1/trail/time-stop),
                                    recover_trigger_level_real_position (disclosed backward-scan
                                    heuristic -- real fills carry no entry_spot label),
                                    structure_stop_signal_time, option_side_from_symbol,
                                    norm_bars_from_esp, STRUCTURE_BUFFER, TIME_STOP_LAYER_B.
  * tw8_level_context.py        -- load_spy_full (CACHED LOCAL SPY 5m data -- zero network
                                    calls; backtest/data/spy_5m_2026-05-19_2026-07-10.csv already
                                    covers every fill date in scope with room for level lookback).
  * exit_manager.py             -- via structure_stop_study, the live decision core (unmodified).
  * t4_exit_matrix.py           -- the drop-top-3 concentration-check convention (same formula).

ONE deliberate NON-reuse, disclosed: structure_stop_study.prepare_positions()'s bar fetcher
special-cases `date_et == TODAY.isoformat()` where TODAY is HARDCODED to `dt.date(2026, 7, 9)`
(that module's own one-off run day) and switches to a wall-clock-capped fetch window for that
date only. Today is no longer 2026-07-09 (this study runs later), so blindly reusing that
function would silently truncate 2026-07-09's option bars to whatever hour this script happens
to run at -- a live correctness bug for any rerun after 07-09, not a hypothetical. Every date in
THIS study's scope is now a fully-elapsed historical day, so `prepare_positions_historical`
below is a small adaptation that always uses the plain historical `esp.fetch_option_bars` (never
the today-safe variant) -- everything else is byte-for-byte the same logic.

SCOPE (task CONSTRAINTS): read-only. Touches no params/engine/fleet config -- migrates nothing,
places no orders. Network calls are ONLY the bounded per-episode 1-min OPTION bar fetch (Alpaca
OPRA, via esp.fetch_option_bars) -- at most one call per unique (symbol, date) across all 4 arms
(roughly a few dozen total for ~109 episodes), explicitly sanctioned by the task ("own-fill
episodes + per-episode option bars (small, bounded queries), which is acceptable"). SPY 5m data
is 100% local cache -- zero network calls for that leg. No OPRA grid/grind/battery-scale scan.

ARMS: safe-1, safe-3, risky-1, risky-3 (the 4 fleet_rest arms). safe-2/bold-2 are core
(mcp_heartbeat-executed) and out of this study's scope -- SS-B's core certification already
shipped as ssb-certification-2026-07-09.json / structure-stop-2026-07-09.json.

OUTPUT: analysis/recommendations/fleet-exit-parity-{arm}.json per arm -- per-episode detail +
aggregate (actual / CONTROL-replay / SS-B-replay totals + win rates) + robustness (drop-top-3,
both-halves chronological split) + an explicit n-honesty verdict. n < MIN_N_FOR_VERDICT ->
INSUFFICIENT_N, never a guess (per-arm fill volume this window is small by construction: the
9-day window had 109 episodes across 6 accounts).

Run: backtest/.venv/Scripts/python.exe backtest/tools/fleet_exit_parity_per_arm.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp    # noqa: E402
import structure_stop_study as sss       # noqa: E402
import tw8_level_context as lc           # noqa: E402

OUT_DIR = REPO / "analysis" / "recommendations"
FLEET_REST_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")

# Local cache covers every fill date in scope (2026-06-26..2026-07-09) with room for level
# lookback and zero network calls -- confirmed on disk before use, not assumed.
SPY_CACHE_START = dt.date(2026, 5, 19)
SPY_CACHE_END = dt.date(2026, 7, 10)

MIN_N_FOR_VERDICT = 10


# ---------------------------------------------------------------------------------------------
# Adapted position-prep (see module docstring for why this isn't a direct sss.prepare_positions
# call): identical logic, minus the hardcoded-TODAY bar-fetch branch.
# ---------------------------------------------------------------------------------------------
def prepare_positions_historical(positions: list[dict], spy_full, level_cache: dict,
                                 bar_cache: dict) -> tuple[list[dict], dict]:
    prepared = []
    recovery_status_counts: dict = {}
    n_no_bars = 0
    for p in positions:
        side = sss.option_side_from_symbol(p["symbol"])
        date = dt.date.fromisoformat(p["date_et"])
        entry_ts_utc = dt.datetime.fromisoformat(p["entry_ts_utc"].replace("Z", "+00:00"))
        entry_ts_et = sss.et_now(entry_ts_utc)
        trigger_level, status = sss.recover_trigger_level_real_position(
            spy_full, level_cache, date, entry_ts_et, side)
        recovery_status_counts[status] = recovery_status_counts.get(status, 0) + 1

        key = (p["symbol"], p["date_et"])
        if key not in bar_cache:
            bar_cache[key] = esp.fetch_option_bars(p["symbol"], p["date_et"])
            _time_mod.sleep(0.12)
        opt_bars = bar_cache[key]
        if not opt_bars:
            n_no_bars += 1
            continue
        norm_bars = sss.norm_bars_from_esp(opt_bars, entry_ts_utc=p["entry_ts_utc"])
        if not norm_bars:
            n_no_bars += 1
            continue
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts_et)]
        qty = int(p["entry_qty"])
        if qty < 1:
            continue
        prepared.append({
            "arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"], "side": side,
            "entry_premium": p["entry_price"], "qty": qty, "actual_exit_pnl": p.get("actual_exit_pnl"),
            "entry_ts_utc": p["entry_ts_utc"],
            "trigger_level": trigger_level, "recovery_status": status,
            "norm_bars": norm_bars, "spy_lifetime": spy_lifetime,
        })
    n_recoverable = sum(1 for p in prepared if p["trigger_level"] is not None)
    stats = {"n_positions_total": len(positions), "n_positions_with_bars": len(prepared),
             "n_no_option_bars": n_no_bars,
             "n_recoverable_trigger_level": n_recoverable,
             "n_fallback": len(prepared) - n_recoverable,
             "recovery_status_counts": recovery_status_counts}
    return prepared, stats


# ---------------------------------------------------------------------------------------------
# Robustness helpers
# ---------------------------------------------------------------------------------------------
def _drop_top3(pnls: list[float]) -> dict:
    """SAME convention as t4_exit_matrix.battery's drop-top-3 (ground rule 8): drop the 3
    highest pnls, recompute the total -- does the edge ride on 3 big winners?"""
    n = len(pnls)
    kept = sorted(pnls)[:-3] if n > 3 else []
    return {"n_kept": len(kept), "total_after_drop": round(sum(kept), 2) if kept else None,
           "mean_after_drop": round(sum(kept) / len(kept), 2) if kept else None}


def _both_halves(rows: list[dict], pnl_key: str) -> dict:
    """Chronological first-half / second-half split (stable sort by date then symbol) -- does
    the shape's edge (if any) hold across time, or is it a single-window artifact?"""
    ordered = sorted(rows, key=lambda r: (r["date_et"], r["symbol"]))
    n = len(ordered)
    mid = n // 2
    first, second = ordered[:mid], ordered[mid:]
    return {
        "first_half": {"n": len(first), "total": round(sum(r[pnl_key] for r in first), 2)},
        "second_half": {"n": len(second), "total": round(sum(r[pnl_key] for r in second), 2)},
    }


# ---------------------------------------------------------------------------------------------
# Per-arm replay
# ---------------------------------------------------------------------------------------------
def replay_arm(arm: str, positions: list[dict], spy_full, level_cache: dict, bar_cache: dict) -> dict:
    prepared, stats = prepare_positions_historical(positions, spy_full, level_cache, bar_cache)
    rows = []
    for p in prepared:
        ss_time = sss.structure_stop_signal_time(p["spy_lifetime"], p["side"], p["trigger_level"],
                                                  sss.STRUCTURE_BUFFER["SS-B"])
        r_control = sss.replay_structure_aware(p["entry_premium"], p["side"], p["qty"],
                                               p["norm_bars"], None, sss.CONTROL_SHAPE,
                                               sss.TIME_STOP_LAYER_B)
        r_ssb = sss.replay_structure_aware(p["entry_premium"], p["side"], p["qty"],
                                           p["norm_bars"], ss_time, sss.SS_B_SHAPE,
                                           sss.TIME_STOP_LAYER_B)
        rows.append({
            "arm": arm, "symbol": p["symbol"], "date_et": p["date_et"], "side": p["side"],
            "entry_premium": p["entry_premium"], "qty": p["qty"],
            "trigger_level": p["trigger_level"], "recovery_status": p["recovery_status"],
            "actual_pnl": p.get("actual_exit_pnl"),
            "control_pnl": r_control["pnl"], "ssb_pnl": r_ssb["pnl"],
            "ssb_structure_fired": r_ssb["structure_fired"],
            "control_exits": r_control["exits"], "ssb_exits": r_ssb["exits"],
        })

    n = len(rows)
    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    ssb_total = round(sum(r["ssb_pnl"] for r in rows), 2)
    actual_total = round(sum((r["actual_pnl"] or 0.0) for r in rows), 2)
    control_wr = round(sum(1 for r in rows if r["control_pnl"] > 0) / n, 3) if n else None
    ssb_wr = round(sum(1 for r in rows if r["ssb_pnl"] > 0) / n, 3) if n else None
    n_structure_fired = sum(1 for r in rows if r["ssb_structure_fired"])

    drop3_control = _drop_top3([r["control_pnl"] for r in rows])
    drop3_ssb = _drop_top3([r["ssb_pnl"] for r in rows])
    halves_control = _both_halves(rows, "control_pnl")
    halves_ssb = _both_halves(rows, "ssb_pnl")

    if n < MIN_N_FOR_VERDICT:
        verdict = "INSUFFICIENT_N"
        verdict_reason = (f"n={n} episodes < {MIN_N_FOR_VERDICT} floor -- data reported, no "
                          f"migrate/keep call made (n-honesty, not a guess).")
    else:
        ssb_beats_control = ssb_total > control_total
        drop3_holds = (drop3_ssb["total_after_drop"] is not None
                      and drop3_control["total_after_drop"] is not None
                      and drop3_ssb["total_after_drop"] > drop3_control["total_after_drop"])
        halves_ssb_wins = sum(1 for h in ("first_half", "second_half")
                              if halves_ssb[h]["total"] > halves_control[h]["total"])
        if ssb_beats_control and drop3_holds and halves_ssb_wins == 2:
            verdict = "SS_B_CLEARLY_BETTER"
        elif ssb_beats_control:
            verdict = "SS_B_BETTER_BUT_FRAGILE"
        else:
            verdict = "KEEP_CURRENT_SHAPE"
        verdict_reason = (f"ssb_total ${ssb_total} vs control_total ${control_total} "
                          f"({'beats' if ssb_beats_control else 'does NOT beat'} control); "
                          f"drop-top3 {'holds' if drop3_holds else 'does not hold'}; "
                          f"both-halves SS-B wins {halves_ssb_wins}/2.")

    return {
        "_doc": (f"PROFIT-P1-FLEET-EXIT-PARITY -- {arm} exit_manager replay, SS-B vs the "
                f"CURRENT observed exit shape, on {arm}'s OWN real fills only (C29: no "
                f"cross-arm transfer assumed). Read-only research artifact -- migrates nothing, "
                f"places no orders."),
        "generated_at": dt.datetime.now().isoformat(),
        "arm": arm,
        "n_episodes": n,
        "n_positions_total_ledger": stats["n_positions_total"],
        "n_positions_with_bars": stats["n_positions_with_bars"],
        "n_no_option_bars": stats["n_no_option_bars"],
        "n_recoverable_trigger_level": stats["n_recoverable_trigger_level"],
        "n_fallback_trigger_level": stats["n_fallback"],
        "recovery_status_counts": stats["recovery_status_counts"],
        "n_structure_fired_ssb": n_structure_fired,
        "aggregate": {
            "actual_total_pnl": actual_total,
            "control_total_pnl": control_total, "control_win_rate": control_wr,
            "ssb_total_pnl": ssb_total, "ssb_win_rate": ssb_wr,
            "ssb_minus_control": round(ssb_total - control_total, 2),
        },
        "robustness": {
            "drop_top3": {"control": drop3_control, "ssb": drop3_ssb},
            "both_halves": {"control": halves_control, "ssb": halves_ssb},
        },
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "shapes_used": {"control": sss.CONTROL_SHAPE, "ss_b": sss.SS_B_SHAPE,
                        "ss_b_structure_buffer_usd": sss.STRUCTURE_BUFFER["SS-B"]},
        "episodes": rows,
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    print(f"[fleet-exit-parity] {len(positions)} reconstructed positions across "
          f"{len(FLEET_REST_ARMS)} fleet_rest arms", flush=True)

    print(f"[fleet-exit-parity] loading cached SPY 5m bars {SPY_CACHE_START}..{SPY_CACHE_END} "
          f"(local file, zero network calls)...", flush=True)
    spy_full = lc.load_spy_full(SPY_CACHE_START, SPY_CACHE_END)
    print(f"[fleet-exit-parity] spy_full: {len(spy_full)} rows, "
          f"{spy_full['date'].min()}..{spy_full['date'].max()}", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    level_cache: dict = {}
    bar_cache: dict = {}
    summary = {}
    for arm in FLEET_REST_ARMS:
        arm_positions = [p for p in positions if p["arm"] == arm]
        print(f"[fleet-exit-parity] {arm}: {len(arm_positions)} positions, replaying...", flush=True)
        result = replay_arm(arm, arm_positions, spy_full, level_cache, bar_cache)
        out_path = OUT_DIR / f"fleet-exit-parity-{arm}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"[fleet-exit-parity] {arm}: n={result['n_episodes']} verdict={result['verdict']} "
              f"ssb-control=${result['aggregate']['ssb_minus_control']} -> wrote {out_path}",
              flush=True)
        summary[arm] = {"n": result["n_episodes"], "verdict": result["verdict"],
                        "ssb_minus_control": result["aggregate"]["ssb_minus_control"],
                        "control_total": result["aggregate"]["control_total_pnl"],
                        "ssb_total": result["aggregate"]["ssb_total_pnl"],
                        "actual_total": result["aggregate"]["actual_total_pnl"]}

    print("\n[fleet-exit-parity] SUMMARY:", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
