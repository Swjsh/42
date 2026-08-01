"""g2_trendline_bypass_ab_2026_08_01 -- G2-TRENDLINE-BYPASS-INVERTS-PRIORITY (queue.md, filed
2026-07-27, CRITICAL/engine-edge): resolve whether the 2026-05-09 TRENDLINE-CHOP-ZONE relaxation
(filters 5/8/9 -> demerit, scoped to trendline-ONLY bear setups) should be EXTENDED to all
level-tied triggers, REMOVED outright, or left as-is.

Frozen pre-reg: analysis/recommendations/prereg-g2-trendline-bypass-2026-08-01.json.

METHOD (reuses filter5_ribbon_fate_2026_07_31.py's scaffold verbatim -- same population, same
dual-patch capture technique, same real-exit walk, same gate shapes):
  CONTROL     run_backtest(**SAFE_BASE_LIVE) -- trendline_bypass_scope='trendline_only' (default).
  ARM_EXTEND  CONTROL + trendline_bypass_scope='all_level_tied'.
  ARM_REMOVE  CONTROL + trendline_bypass_scope='none'.

BEAR SIDE ONLY: the flag is a parameter of evaluate_bearish_setup exclusively.

EXITS: every entry in every arm is re-walked through the REAL live exit core
(automation/state/fleet/exit_manager.plan_exit_actions via lib/exit_manager_walk) with the
RIBBON_RIDE registry exit shape. Each arm's own run_backtest dollar_pnl is DISCARDED --
simulate_trade_real is known-divergent from the live exit manager (2026-07-09 sim-parity scar).

P&L: real cached OPRA contracts ONLY. Contracts with no cached CSV are excluded and COUNTED
per arm; nothing is Black-Scholes-synthesized into a total.

Run: backtest/.venv/Scripts/python.exe backtest/tools/g2_trendline_bypass_ab_2026_08_01.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- SAFE_BASE_LIVE, ribbon lookup, TIME_STOP_ET
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- entry_date, classify_tier
import lib.orchestrator as orch_mod  # noqa: E402
import lib.engine.score as score_mod  # noqa: E402 -- holds its OWN by-name bindings (score.py:66)
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import CACHE_DIR, load_contract_bars, option_symbol  # noqa: E402
from strategies import by_name as fleet_strategy_by_name  # noqa: E402

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
NEW_VIX = DATA / "vix_5m_2026-05-19_2026-07-31.csv"
OLD_WINDOW_END = dt.date(2026, 7, 22)
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-g2-trendline-bypass-2026-08-01.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "g2-trendline-bypass-2026-08-01.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "g2-trendline-bypass-2026-08-01.md"

RECENT_TRADING_DAYS = 25
RUNNER_NO_REGRESSION_FLOOR = 0.95
ARMS = ("ARM_EXTEND", "ARM_REMOVE")
SCOPE_FOR_ARM = {"ARM_EXTEND": "all_level_tied", "ARM_REMOVE": "none"}


def log(msg: str) -> None:
    print(f"[g2-trendline-bypass] {msg}", flush=True)


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


def load_extended_data():
    spy_old = pd.read_csv(OLD_SPY)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX)
    vix_new = pd.read_csv(NEW_VIX)
    _vix_new_dates = pd.to_datetime(vix_new["timestamp_et"]).dt.date
    vix_tail = vix_new[_vix_new_dates > OLD_WINDOW_END].reset_index(drop=True)
    vix_df = pd.concat([vix_old, vix_tail], ignore_index=True)
    return spy_df, vix_df


def recent_window_dates(spy_df: pd.DataFrame, n: int = RECENT_TRADING_DAYS) -> set:
    days = sorted({d for d in spy_df["timestamp_et"].dt.date if d <= FULL_END})
    return set(days[-n:])


def run_arm(label: str, spy_df, vix_df, *, trendline_bypass_scope: str = "trendline_only"):
    """Dual-patch pass-through (mirrors filter5_ribbon_fate_2026_07_31.py::run_arm exactly --
    both lib.orchestrator and lib.engine.score hold independent by-name bindings of
    evaluate_bearish_setup, and run_backtest's own _ENGINE_SCORE_ASSERT parity cross-check
    drives every bar through both; patching only one makes that assert fire mid-run)."""
    orig_bear = orch_mod.evaluate_bearish_setup
    assert score_mod.evaluate_bearish_setup is orig_bear, (
        "lib.engine.score no longer shares filters.evaluate_bearish_setup with lib.orchestrator "
        "-- the dual patch below would be scoring two different functions"
    )

    def _bear(ctx, **kw):
        kw = dict(kw, trendline_bypass_scope=trendline_bypass_scope)
        return orig_bear(ctx, **kw)

    kwargs = dict(efr.SAFE_BASE_LIVE)
    orch_mod.evaluate_bearish_setup = _bear
    score_mod.evaluate_bearish_setup = _bear
    t0 = time.time()
    try:
        r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        score_mod.evaluate_bearish_setup = orig_bear
    log(f"  {label}: {len(r.trades)} raw entries in {time.time() - t0:.1f}s "
        f"(scope={trendline_bypass_scope})")
    return r


def derive_rows(label: str, r, spy_df: pd.DataFrame, ribbon_lookup, exit_shape: dict):
    """Re-walk every BEAR entry through the REAL exit manager. Byte-identical machinery to
    engine_fullhist_replay.py's own loop (and filter5_ribbon_fate_2026_07_31.py::derive_rows)."""
    rows, skipped, excluded = [], {"no_opra": 0, "no_spy_day": 0}, []

    def _excluded(edate, symbol, t, reason):
        return {"arm": label, "date": edate.isoformat(),
                "entry_time_et": naive_dt(t.entry_time_et).isoformat(),
                "side": t.side, "symbol": symbol, "reason": reason,
                "setup": t.setup, "triggers": list(t.triggers_fired),
                "level": float(t.rejection_level) if t.rejection_level else None}

    bear_trades = [t for t in r.trades if t.side == "P"]
    for t in bear_trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            skipped["no_opra"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_opra"))
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            skipped["no_spy_day"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_spy_day"))
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        rows.append({
            "arm": label, "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "side": t.side, "setup": t.setup, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": list(t.triggers_fired), "level": trigger_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
        })
    log(f"  {label}: {len(rows)} real-OPRA bear walks "
        f"(excluded: no_opra={skipped['no_opra']} no_spy_day={skipped['no_spy_day']})")
    return rows, skipped, excluded


def _key(row) -> tuple:
    return (row["date"], row["entry_time_et"], row["symbol"], row["side"])


def cohort_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "total": 0.0, "wr": None, "per_trade": None,
                "total_ex_best": None, "n_days": 0}
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(rows), "total": total, "wr": round(wins / len(rows), 4),
        "per_trade": round(total / len(rows), 2),
        "total_ex_best": round(total - max(pnls), 2), "n_days": len({r["date"] for r in rows}),
    }


def window_slice(rows: list[dict], dates: Optional[set]) -> list[dict]:
    if dates is None:
        return rows
    return [r for r in rows if dt.date.fromisoformat(r["date"]) in dates]


def runner_cohort(rows: list[dict]) -> dict:
    sel = [r for r in rows
           if "runner" in (r["exit_reason"] or "").lower() or "trail" in (r["exit_reason"] or "").lower()]
    return {"n": len(sel), "total": round(sum(r["dollar_pnl"] for r in sel), 2)}


def score_arm(label: str, control_rows: list[dict], arm_rows: list[dict], recent_dates: set) -> dict:
    ctrl_by_key = {_key(r): r for r in control_rows}
    arm_by_key = {_key(r): r for r in arm_rows}
    added_keys = [k for k in arm_by_key if k not in ctrl_by_key]
    dropped_keys = [k for k in ctrl_by_key if k not in arm_by_key]
    added = [arm_by_key[k] for k in added_keys]
    dropped = [ctrl_by_key[k] for k in dropped_keys]

    out = {"arm": label}
    for wname, wdates in (("full", None), ("recent25", recent_dates)):
        c = window_slice(control_rows, wdates)
        a = window_slice(arm_rows, wdates)
        c_total = round(sum(r["dollar_pnl"] for r in c), 2)
        a_total = round(sum(r["dollar_pnl"] for r in a), 2)
        w_added = window_slice(added, wdates)
        w_dropped = window_slice(dropped, wdates)
        changed_days = sorted({r["date"] for r in w_added} | {r["date"] for r in w_dropped})
        day_deltas = {}
        for d in changed_days:
            cd = sum(r["dollar_pnl"] for r in c if r["date"] == d)
            ad = sum(r["dollar_pnl"] for r in a if r["date"] == d)
            day_deltas[d] = round(ad - cd, 2)
        n_up = sum(1 for v in day_deltas.values() if v > 0)
        n_dn = sum(1 for v in day_deltas.values() if v < 0)
        delta = round(a_total - c_total, 2)
        best_added = max((r["dollar_pnl"] for r in w_added), default=0.0)
        out[wname] = {
            "control": {"n": len(c), "total": c_total}, "arm": {"n": len(a), "total": a_total},
            "delta_total": delta, "n_added": len(w_added), "n_dropped": len(w_dropped),
            "added_stats": cohort_stats(w_added), "dropped_stats": cohort_stats(w_dropped),
            "n_changed_days": len(changed_days), "n_days_improved": n_up, "n_days_worsened": n_dn,
            "day_deltas": day_deltas, "best_added_trade": round(best_added, 2),
            "delta_minus_best_added": round(delta - best_added, 2),
        }
    out["runner_cohort"] = {"control": runner_cohort(control_rows), "arm": runner_cohort(arm_rows)}
    rc, ra = out["runner_cohort"]["control"], out["runner_cohort"]["arm"]
    out["gates"] = {
        "G1_recent_window_positive": {
            "delta_total_recent": out["recent25"]["delta_total"],
            "pass": out["recent25"]["delta_total"] > 0},
        "G2_day_majority_recent": {
            "improved": out["recent25"]["n_days_improved"], "worsened": out["recent25"]["n_days_worsened"],
            "pass": out["recent25"]["n_days_improved"] > out["recent25"]["n_days_worsened"]},
        "G3_survives_drop_best_recent": {
            "delta_minus_best": out["recent25"]["delta_minus_best_added"],
            "pass": out["recent25"]["delta_minus_best_added"] > 0},
        "G4_runner_anchor_no_regression": {
            "control_n": rc["n"], "arm_n": ra["n"], "control_total": rc["total"], "arm_total": ra["total"],
            "pass": (ra["n"] >= rc["n"] * RUNNER_NO_REGRESSION_FLOOR
                     and ra["total"] >= rc["total"] * RUNNER_NO_REGRESSION_FLOOR)},
        "G5_fire_count": {
            "n_changed_full": out["full"]["n_added"] + out["full"]["n_dropped"],
            "n_changed_recent": out["recent25"]["n_added"] + out["recent25"]["n_dropped"],
            "pass": (out["full"]["n_added"] + out["full"]["n_dropped"]) > 0},
    }
    for g in out["gates"].values():
        g["status"] = "PASS" if g["pass"] else "FAIL"
    out["all_gates_pass"] = all(g["pass"] for g in out["gates"].values())
    out["verdict"] = "SHIP_CANDIDATE" if out["all_gates_pass"] else "NULL"
    return out


def exit_reason_mix(rows: list[dict]) -> dict:
    from collections import Counter
    c = Counter((r["exit_reason"] or "").split(" @")[0] for r in rows)
    n = max(1, len(rows))
    return {k: {"n": v, "pct": round(100.0 * v / n, 1)} for k, v in c.most_common()}


def cached_contracts_per_day(dates) -> dict:
    counts = {d: 0 for d in dates}
    for p in CACHE_DIR.glob("SPY*.csv"):
        stem = p.stem
        if len(stem) < 9 or not stem[3:9].isdigit():
            continue
        try:
            d = dt.date(2000 + int(stem[3:5]), int(stem[5:7]), int(stem[7:9]))
        except ValueError:
            continue
        if d in counts:
            counts[d] += 1
    return counts


def opra_measurability(control_rows, control_excl, arm_rows, arm_excl, recent_dates) -> dict:
    def keyset(rows):
        return {_key(r) for r in rows}

    def in_window(rows):
        return [r for r in rows if dt.date.fromisoformat(r["date"]) in recent_dates]

    ctrl_raw = keyset(control_rows) | keyset(control_excl)
    out = {"windows": {}}
    for wname, rows_c, excl_c, rows_a, excl_a in (
        ("full", control_rows, control_excl, arm_rows, arm_excl),
        ("recent25", in_window(control_rows), in_window(control_excl),
         in_window(arm_rows), in_window(arm_excl)),
    ):
        added_walked = [r for r in rows_a if _key(r) not in ctrl_raw]
        added_excluded = [r for r in excl_a if _key(r) not in ctrl_raw]
        n_unmeas = len(added_excluded)
        n_raw = len(added_walked) + n_unmeas
        out["windows"][wname] = {
            "added_by_arm": {
                "raw_entries": n_raw, "measurable": len(added_walked),
                "unmeasurable_no_opra": n_unmeas,
                "measurable_pct": round(100.0 * len(added_walked) / n_raw, 1) if n_raw else None,
            },
        }
    out["cached_contracts_per_day_recent25"] = {
        d.isoformat(): n for d, n in sorted(cached_contracts_per_day(recent_dates).items())}
    zero_days = [d for d, n in out["cached_contracts_per_day_recent25"].items() if n == 0]
    out["recent25_days_with_zero_opra_coverage"] = {"n": len(zero_days), "days": zero_days}
    return out


def relabel_g1_measurability(scored: dict, meas: dict) -> dict:
    """UNDETERMINED counts as NOT PASS (frozen pre-reg, known_data_gap_disclosed_before_running:
    'If G1 comes back UNDETERMINED, the ship rule below treats it as a non-PASS ... it does not
    silently default to PASS.'). Mutates g1['pass'] to False on UNDETERMINED, then the caller
    MUST recompute all_gates_pass/verdict from the (now-corrected) gates dict -- see
    `_recompute_verdict` below. A prior version of this function only changed the status LABEL
    and left the boolean the sign-test measured, silently shipping an UNDETERMINED-gated arm on
    its first run (2026-08-01 ~04:35 ET) -- caught before the scorecard was finalized, fixed
    same session, RE-DERIVED from the already-computed per-trade JSON rather than re-running the
    ~3.5min backtest (the correction is postprocessing-only, not a re-measurement)."""
    g1 = scored["gates"]["G1_recent_window_positive"]
    add = meas["windows"]["recent25"]["added_by_arm"]
    n_missing = add["unmeasurable_no_opra"]
    delta = g1["delta_total_recent"]
    if n_missing <= 0:
        g1["status"] = "PASS" if g1["pass"] else "FAIL"
        return scored
    g1["status"] = "UNDETERMINED"
    g1["pass"] = False  # frozen pre-reg rule: UNDETERMINED is NOT a pass
    g1["undetermined_because"] = (
        f"{n_missing} of {add['raw_entries']} raw entries this arm's recent-window book differs "
        f"by could not be priced (no cached OPRA contract). Measured delta ${delta:+,.2f} covers "
        f"only the priceable subset. G1 is a strict sign test -- UNDETERMINED, not measured, and "
        f"per the frozen pre-reg counts as NOT PASS."
    )
    return scored


def _recompute_verdict(scored: dict) -> dict:
    """Re-derive all_gates_pass/verdict from the (possibly UNDETERMINED-corrected) gates dict.
    Must run AFTER relabel_g1_measurability, since score_arm's own all_gates_pass was computed
    before the G1 boolean could be corrected."""
    scored["all_gates_pass"] = all(g["pass"] for g in scored["gates"].values())
    scored["verdict"] = "SHIP_CANDIDATE" if scored["all_gates_pass"] else "NULL"
    return scored


def main() -> int:
    preg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"pre-reg {preg['prereg_id']} frozen {preg['frozen_at_et']}")

    log("loading extended SPY/VIX data...")
    spy_df, vix_df = load_extended_data()
    recent_dates = recent_window_dates(spy_df)
    log(f"recent25 window: {min(recent_dates)}..{max(recent_dates)} ({len(recent_dates)} days)")
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategy_by_name("ribbon_ride").exit.to_dict()

    log("running CONTROL (trendline_bypass_scope='trendline_only')...")
    r_control = run_arm("CONTROL", spy_df, vix_df, trendline_bypass_scope="trendline_only")
    control_rows, control_skip, control_excl = derive_rows("CONTROL", r_control, spy_df, ribbon_lookup, exit_shape)

    arm_results = {}
    arm_rows_map = {}
    arm_excl_map = {}
    for arm in ARMS:
        scope = SCOPE_FOR_ARM[arm]
        log(f"running {arm} (trendline_bypass_scope='{scope}')...")
        r_arm = run_arm(arm, spy_df, vix_df, trendline_bypass_scope=scope)
        rows, skip, excl = derive_rows(arm, r_arm, spy_df, ribbon_lookup, exit_shape)
        arm_rows_map[arm] = rows
        arm_excl_map[arm] = excl

        scored = score_arm(arm, control_rows, rows, recent_dates)
        meas = opra_measurability(control_rows, control_excl, rows, excl, recent_dates)
        scored = relabel_g1_measurability(scored, meas)
        scored = _recompute_verdict(scored)
        scored["opra_measurability"] = meas
        added_keys_ctrl = {_key(r) for r in control_rows}
        added = [r for r in rows if _key(r) not in added_keys_ctrl]
        added_keys_arm = {_key(r) for r in rows}
        dropped = [r for r in control_rows if _key(r) not in added_keys_arm]
        scored["added_exit_reason_mix"] = exit_reason_mix(added)
        scored["dropped_exit_reason_mix"] = exit_reason_mix(dropped)
        scored["control_exit_reason_mix"] = exit_reason_mix(control_rows)
        arm_results[arm] = scored
        log(f"{arm}: {scored['verdict']} full_delta=${scored['full']['delta_total']:+.2f} "
            f"recent_delta=${scored['recent25']['delta_total']:+.2f} "
            f"gates=[{scored['gates']['G1_recent_window_positive']['status']},"
            f"{scored['gates']['G2_day_majority_recent']['status']},"
            f"{scored['gates']['G3_survives_drop_best_recent']['status']},"
            f"{scored['gates']['G4_runner_anchor_no_regression']['status']},"
            f"{scored['gates']['G5_fire_count']['status']}]")

    ships = [a for a in ARMS if arm_results[a]["all_gates_pass"]]
    if not ships:
        final_verdict = "NEITHER_SHIPS_STAYS_TRENDLINE_ONLY"
        winner = None
    elif len(ships) == 1:
        final_verdict = f"{ships[0]}_SHIPS"
        winner = ships[0]
    else:
        winner = max(ships, key=lambda a: arm_results[a]["recent25"]["delta_total"])
        final_verdict = f"{winner}_SHIPS_HIGHER_RECENT_DELTA"

    out = {
        "_doc": "G2-TRENDLINE-BYPASS-INVERTS-PRIORITY -- frozen pre-registered, real OPRA fills "
                "via exit_manager_walk, full-history (2025-01-02..2026-07-31) bear population. "
                "ANALYSIS run against a NEW filters.py flag (trendline_bypass_scope), default "
                "value untouched, guarded by test_g2_trendline_bypass_scope.py.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "control_raw_entries": len(r_control.trades),
        "control_bear_entries": len([t for t in r_control.trades if t.side == "P"]),
        "control_walked": len(control_rows),
        "control_total_full": round(sum(r["dollar_pnl"] for r in control_rows), 2),
        "recent_window_dates": sorted(d.isoformat() for d in recent_dates),
        "arms": arm_results,
        "final_verdict": final_verdict,
        "winner": winner,
        "reconciliation_with_filter5_ribbon_2026_07_31": (
            "Disjoint mechanism/question from filter5-ribbon-2026-07-31.json (that study asks "
            "whether filter 5 itself should exist at all, both directions; this study asks "
            "whether the EXISTING bear-side trendline-only relaxation of filters 5/8/9 should "
            "be extended or removed). Same population/harness/OPRA-coverage gap inherited."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"FINAL VERDICT: {final_verdict}")
    return 0


def write_markdown(out: dict) -> None:
    L = [
        "# G2-TRENDLINE-BYPASS-INVERTS-PRIORITY -- A/B (2026-08-01)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. "
        f"Pre-reg: `{out['preregistration_file']}`.",
        "",
        f"CONTROL: {out['control_raw_entries']} raw entries ({out['control_bear_entries']} bear), "
        f"{out['control_walked']} real-OPRA bear walks, total ${out['control_total_full']:+,.2f}.",
        f"Recent window: {out['recent_window_dates'][0]}..{out['recent_window_dates'][-1]} "
        f"({len(out['recent_window_dates'])} days).",
        "",
        "## Arms",
        "",
        "| arm | scope | full delta | recent delta | G1 | G2 | G3 | G4 | G5 | verdict |",
        "|---|---|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for arm in ARMS:
        a = out["arms"][arm]
        g = a["gates"]
        L.append(
            f"| {arm} | {SCOPE_FOR_ARM[arm]} | ${a['full']['delta_total']:+,.2f} | "
            f"${a['recent25']['delta_total']:+,.2f} | {g['G1_recent_window_positive']['status']} | "
            f"{g['G2_day_majority_recent']['status']} | {g['G3_survives_drop_best_recent']['status']} | "
            f"{g['G4_runner_anchor_no_regression']['status']} | {g['G5_fire_count']['status']} | "
            f"**{a['verdict']}** |")
    L += ["", f"## FINAL VERDICT: **{out['final_verdict']}**", ""]
    if out["winner"]:
        L.append(f"Ship `{out['winner']}` (`trendline_bypass_scope='{SCOPE_FOR_ARM[out['winner']]}'`).")
    else:
        L.append("Neither arm clears all 5 gates. `trendline_bypass_scope` stays at the CONTROL "
                  "default (`'trendline_only'`) -- the G2 finding is CONFIRMED as a real asymmetry "
                  "but NOT acted on without evidence clearing the bar.")
    for arm in ARMS:
        a = out["arms"][arm]
        L += [
            "", f"### {arm} detail",
            "",
            f"Full: n_added={a['full']['n_added']} n_dropped={a['full']['n_dropped']} "
            f"added_stats={a['full']['added_stats']}",
            f"Recent25: n_added={a['recent25']['n_added']} n_dropped={a['recent25']['n_dropped']} "
            f"days_improved={a['recent25']['n_days_improved']} days_worsened={a['recent25']['n_days_worsened']}",
            f"Runner-cohort anchor: control={a['runner_cohort']['control']} arm={a['runner_cohort']['arm']}",
            f"Added exit-reason mix: {a['added_exit_reason_mix']}",
            f"OPRA recent25 zero-coverage days: {a['opra_measurability']['recent25_days_with_zero_opra_coverage']}",
        ]
    L += [
        "",
        "## Reconciliation",
        "",
        out["reconciliation_with_filter5_ribbon_2026_07_31"],
        "",
        "---",
        "_Source: `backtest/tools/g2_trendline_bypass_ab_2026_08_01.py`. Full per-trade detail in "
        "the companion `.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
