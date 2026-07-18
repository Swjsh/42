"""exit_manager_replay.py -- EXIT-MANAGER-REPLAY-HARNESS (GOAL-REPLAY-TODAY-GREEN iteration 6).

WHY (the FRAME AUDIT, GOAL-REPLAY-TODAY-GREEN.md 2026-07-17 ~20:30 ET): iterations 2-3 proved
`simulate_trade_real`'s exit model is KNOWN-DIVERGENT from the live exit_manager -- live ran
core_safe's 13:01 746P to +$241; the sim breakeven-zeroed it in 2 minutes. This module abandons
simulate_trade_real for exit-fidelity purposes and instead drives the ACTUAL production exit
code (`automation/state/fleet/exit_manager.py plan_exit_actions`, via
`backtest/lib/exit_manager_walk.py`) tick-by-tick over today's REAL 1-minute OPRA option bars
(backtest/data/highres/, fetched iteration 3) for the 6 engine-fireable core round trips
(5 core_safe + 1 core_bold; the 12:04 J-called 746C stays OUT OF SCOPE -- no engine rule fires
it, confirmed again via journal/trades.csv j_override='Y', consistent with every prior
iteration).

SECOND ROOT CAUSE FOUND BUILDING THIS (not previously documented): the sim-based harness was
not merely using a coarser/divergent EXIT MECHANISM -- it was reading the WRONG EXIT NUMBERS.
`simulate_trade_real` callers (replay_today_eval.py iterations 2-3 included) source exit knobs
from automation/state/params.json's top-level keys (tp1_premium_pct=0.5, v15_profit_lock_mode=
"fixed", runner_max_premium_pct=2.5). But heartbeat_core.py:1471-1477's REAL exit_manager
registration for ribbon_ride entries (BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON -- 5 of today's 6 entries) reads
`automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()` instead: tp1_premium_pct=1.0,
profit_lock_mode="trailing" (chandelier, arm +5%/trail 15%), runner_target_pct=99.0 (rides via
trail/structure/time-stop, not a fixed target), stop_mode="structure" (chart-level primary,
-50% catastrophe cap demoted). params.json's structure_stop_enabled=true (both accounts,
confirmed) resolves 5/6 of today's real entries to STRUCTURE mode at from_entry -- exactly the
mechanism the sim never modeled. Only the isolated bollinger_squeeze entry (14:03) genuinely
uses params.json's j_bollinger_squeeze_* keys (that mapping WAS correct in the prior harness).

Entry data: read verbatim from automation/state/core-decisions.jsonl (SIGNAL/DECISION layer,
iteration-2-faithful, unchanged) -- symbol/side/strike/qty/setup/stop_mode/trigger_level, and
critically entry_premium = the REAL BROKER FILL PRICE (fill.filled_avg_price), not a re-derived
approximation. This deliberately ISOLATES the exit-mechanism fidelity question (this iteration's
job) from the entry-fill-price question (iteration 3 already closed that to $0.00-$0.08).

Run: backtest/.venv/Scripts/python.exe backtest/tools/exit_manager_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402 -- automation/state/fleet/strategies.py
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import replay_today_eval as rte  # noqa: E402 -- reuse iteration-2/3's faithful SIGNAL layer

DATE_STR = "2026-07-17"
TRADE_DATE = dt.date(2026, 7, 17)
CORE_SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
CORE_BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
JOURNAL_TRADES_PATH = REPO / "journal" / "trades.csv"
OUT_JSON = REPO / "analysis" / "recommendations" / "exit-manager-replay-2026-07-17.json"

# Faithfulness tolerance -- same standard as iterations 2-3 (max($40, 15% of |live|)), so this
# result is directly comparable to the sim-based baseline it supersedes.
TOL_ABS = 40.0
TOL_PCT = 0.15

ACCOUNT_ARM = {"safe": "core_safe", "bold": "core_bold"}


def log(msg: str) -> None:
    print(f"[exit-mgr-replay] {msg}", flush=True)


def exit_shape_for(setup: str, account_params: dict) -> dict:
    """The REAL exit_shape heartbeat_core.py would register with exit_manager for this setup
    -- byte-identical to _execute's construction (heartbeat_core.py:1453-1481)."""
    if setup == "bollinger_squeeze":
        shape = {
            "premium_stop_pct": account_params["j_bollinger_squeeze_premium_stop_pct"],
            "tp1_premium_pct": account_params["j_bollinger_squeeze_tp1_pct"],
            "tp1_qty_fraction": account_params["j_bollinger_squeeze_tp1_qty_fraction"],
            "profit_lock_mode": account_params["j_bollinger_squeeze_profit_lock_mode"],
            "trail_pct": account_params["j_bollinger_squeeze_profit_lock_trail_pct"],
        }
        return shape
    # ribbon_ride (BEARISH_REJECTION_RIDE_THE_RIBBON / BULLISH_RECLAIM_RIDE_THE_RIBBON) --
    # the strategies.py-shipped shape, NOT params.json's top-level knobs (see module docstring).
    strat = fleet_strategies.by_name("ribbon_ride")
    return strat.exit.to_dict()


def load_entries() -> list[dict]:
    core_today = rte.rows_for_today(rte.load_jsonl(rte.CORE_DECISIONS_PATH))
    entries = rte.extract_core_entries(core_today)  # verbatim recorded exec blocks, both channels
    # Restrict to core_safe / core_bold engine-fireable round trips only (this harness's scope).
    return [e for e in entries if e["arm"] in ("core_safe", "core_bold")]


def ground_truth_by_entry() -> dict[tuple, float]:
    """(account_id, time_entry HH:MM:SS) -> summed real dollar_pnl across all legs (broker-
    verified, journal/trades.csv). Cross-validation only, never fed into the walk itself."""
    rows = rte.load_trades_csv_today()
    gt = {}
    for r in rows:
        if r.get("j_override") == "Y":
            continue
        key = (r["account_id"], r["time_entry"])
        gt[key] = gt.get(key, 0.0) + float(r["dollar_pnl"])
    return gt


def match_ground_truth(gt: dict, account_id: str, entry_ts: dt.datetime) -> float | None:
    best, best_gap = None, None
    for (acct, t_entry), pnl in gt.items():
        if acct != account_id:
            continue
        try:
            gt_t = dt.datetime.combine(TRADE_DATE, dt.datetime.strptime(t_entry, "%H:%M:%S").time())
        except ValueError:
            continue
        gap = abs((gt_t - entry_ts).total_seconds())
        if gap <= 600 and (best_gap is None or gap < best_gap):
            best, best_gap = pnl, gap
    return best


def main() -> int:
    log("Loading entries (SIGNAL layer, verbatim recorded exec blocks)")
    entries = load_entries()
    log(f"  {len(entries)} core engine-fireable entries: "
        f"{', '.join(e['ts_et'][11:19] + '/' + e['arm'] for e in entries)}")

    core_safe_params = json.loads(CORE_SAFE_PARAMS_PATH.read_text(encoding="utf-8"))
    core_bold_params = json.loads(CORE_BOLD_PARAMS_PATH.read_text(encoding="utf-8"))
    account_params = {"core_safe": core_safe_params, "core_bold": core_bold_params}

    log("Loading 1-min SPY + 5-min SPY (for last_closed_5m_close) + ribbon")
    spy_5m_rth, ribbon_5m = rte.load_spy_ribbon()
    spy_1m_rth = rte.load_spy_1min_rth()
    if spy_1m_rth is None:
        log("FATAL: no 1-min SPY data -- run backtest/tools/fetch_today_1min.py first")
        return 1
    ribbon_1m = rte.build_ribbon_1min(spy_1m_rth, spy_5m_rth, ribbon_5m)

    gt = ground_truth_by_entry()

    results = []
    for e in entries:
        arm = e["arm"]
        account_id = {"core_safe": "safe", "core_bold": "bold"}[arm]
        params = account_params[arm]
        symbol = rte.option_symbol(TRADE_DATE, e["strike"], e["side"])
        opt_1m = rte.load_opt_1min(symbol)
        if opt_1m is None:
            log(f"  SKIP {e['ts_et']} {symbol}: no 1-min OPRA cache")
            continue

        entry_time_et = rte._parse_et_naive(e["ts_et"])
        entry_premium = float(e["live_entry_px"])
        setup = e.get("setup") or "BEARISH_REJECTION_RIDE_THE_RIBBON"
        shape = exit_shape_for(setup, params)
        structure_enabled = bool(params.get("structure_stop_enabled", False))
        trigger_level = e.get("rejection_level")
        time_stop_et = rte._parse_hhmm(params["time_stop_et"])

        res = walk_exit_manager(
            symbol=symbol, side=e["side"], entry_time_et=entry_time_et,
            entry_premium=entry_premium, qty=int(e["qty"]), exit_shape=shape,
            structure_stop_enabled=structure_enabled, trigger_level=trigger_level,
            strategy=setup, time_stop_et=time_stop_et,
            opt_df=opt_1m, ribbon_tick_df=ribbon_1m, five_min_spy_df=spy_5m_rth,
        )

        live_pnl = match_ground_truth(gt, account_id, entry_time_et)
        delta = None if live_pnl is None else round(res.dollar_pnl - live_pnl, 2)
        tol = None if live_pnl is None else max(TOL_ABS, abs(live_pnl) * TOL_PCT)
        faithful = None if live_pnl is None else bool(abs(delta) <= tol)

        row = {
            "arm": arm, "account_id": account_id, "setup": setup,
            "entry_time_et": entry_time_et.isoformat(), "symbol": symbol, "side": e["side"],
            "qty": int(e["qty"]), "entry_premium": entry_premium,
            "resolved_stop_mode": res.stop_mode, "trigger_level": res.trigger_level,
            "exit_reason": res.exit_reason, "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
            "hold_minutes": res.hold_minutes, "n_ticks_walked": res.n_ticks_walked,
            "legs": [{"kind": lg.kind, "qty": lg.qty, "fill_price": lg.fill_price,
                      "reason": lg.reason, "stage": lg.stage, "ts_et": lg.ts_et.isoformat(),
                      "leg_pnl": lg.leg_pnl} for lg in res.legs],
            "replay_dollar_pnl": res.dollar_pnl,
            "live_dollar_pnl": live_pnl,
            "delta": delta, "tolerance": tol, "faithful": faithful,
        }
        results.append(row)
        log(f"  {e['ts_et'][11:19]} {arm:10s} {symbol} qty={e['qty']} entry=${entry_premium:.2f} "
            f"stop_mode={res.stop_mode} -> replay=${res.dollar_pnl:+.2f} live=${live_pnl:+.2f} "
            f"delta=${delta:+.2f} faithful={faithful} exit={res.exit_reason}")

    n_faithful = sum(1 for r in results if r["faithful"])
    n_scored = sum(1 for r in results if r["faithful"] is not None)
    replay_total = round(sum(r["replay_dollar_pnl"] for r in results), 2)
    live_total = round(sum(r["live_dollar_pnl"] for r in results if r["live_dollar_pnl"] is not None), 2)

    per_arm = {}
    for arm in ("core_safe", "core_bold"):
        arm_rows = [r for r in results if r["arm"] == arm]
        per_arm[arm] = {
            "n_trades": len(arm_rows),
            "replay_pnl": round(sum(r["replay_dollar_pnl"] for r in arm_rows), 2),
            "live_pnl": round(sum(r["live_dollar_pnl"] for r in arm_rows if r["live_dollar_pnl"] is not None), 2),
        }
        per_arm[arm]["delta"] = round(per_arm[arm]["replay_pnl"] - per_arm[arm]["live_pnl"], 2)

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "trade_date": DATE_STR,
        "n_entries": len(results),
        "n_faithful": n_faithful,
        "n_scored": n_scored,
        "all_faithful": n_faithful == n_scored and n_scored > 0,
        "faithfulness_tolerance": {"abs_dollars": TOL_ABS, "pct_of_live": TOL_PCT},
        "replay_total_pnl": replay_total,
        "live_total_pnl": live_total,
        "total_delta": round(replay_total - live_total, 2),
        "per_arm": per_arm,
        "trades": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"FAITHFULNESS: {n_faithful}/{n_scored} trades within tolerance. "
        f"replay_total=${replay_total:+.2f} live_total=${live_total:+.2f} delta=${out['total_delta']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
