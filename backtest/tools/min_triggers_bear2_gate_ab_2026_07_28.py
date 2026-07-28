"""min_triggers_bear2_gate_ab_2026_07_28.py -- PRE-REGISTERED gate-add A/B:
filter_10_min_triggers_bear 1 -> 2 (kills single-trigger bear entries, which in the
full-history population are exactly the trendline-only class: 120 of 124 TL_only trades
have exactly 1 trigger; the other 4 are trendline+ribbon_flip 2-trigger and survive).

WHY A RERUN, NOT COHORT ARITHMETIC: run_backtest manages one position at a time, so
removing an entry can unlock later signals that the baseline suppressed. Cohort
subtraction is therefore only an estimate; this script re-runs the REAL entry cascade
(backtest/lib/orchestrator.py#run_backtest) with the knob flipped, then re-derives every
exit through the REAL live exit core (exit_manager_walk.walk_exit_manager), identically
to backtest/tools/engine_fullhist_replay.py (whose machinery it imports).

PRE-REGISTRATION (fixed in this file BEFORE the variant run; the script also writes the
prereg block to the output JSON and flushes it to disk BEFORE computing the variant):
see PREREG dict below. All four gates must pass for a SHIP verdict; every gate's number
is reported either way. A FAIL/NULL is a valid, valuable answer.

Run: backtest/.venv/Scripts/python.exe backtest/tools/min_triggers_bear2_gate_ab_2026_07_28.py
Outputs: analysis/deep-research/min-triggers-bear2-ab-2026-07-28.json
         + appends a results section to analysis/deep-research/PNL-ATTRIBUTION-2026-07-28.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

import engine_fullhist_replay as efr  # noqa: E402 -- machinery reuse (import runs no replay)
import elite_bear_level_reject_gate_ab as eb  # noqa: E402
import pandas as pd  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

import strategies as fleet_strategies  # noqa: E402

OUT_JSON = ROOT / "analysis" / "deep-research" / "min-triggers-bear2-ab-2026-07-28.json"
ATTRIB_MD = ROOT / "analysis" / "deep-research" / "PNL-ATTRIBUTION-2026-07-28.md"
BASELINE_SCORECARD = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
DAY_INV = ROOT / "analysis" / "edge-matrix" / "day-inventory-extended.json"

PREREG = {
    "rule_id": "min_triggers_bear_2_gate_add",
    "registered_at": None,  # stamped at write time, BEFORE the variant run
    "hypothesis": (
        "Bear-side single-trigger entries (in practice the trendline-only class: 124/190 "
        "replay trades, all bear, full-window -$1,830.10 at WR 0.194 per "
        "PNL-ATTRIBUTION-2026-07-28) are a net P&L drain. Raising the EXISTING production "
        "knob filter_10_min_triggers_bear from 1 to 2 (params.json; orchestrator kwarg "
        "min_triggers_bear) improves full-history engine P&L."
    ),
    "mechanism": (
        "Existing engine knob, full cascade re-run baseline-vs-variant -- NOT cohort "
        "subtraction -- so one-position-at-a-time replacement entries are modeled."
    ),
    "pass_bar_all_four_required": {
        "gate_1_positive_aggregate": "variant_total - baseline_total > 0 (full window)",
        "gate_2_day_majority": "strictly more improved days than worsened days among days where |delta| > $0.005",
        "gate_3_survives_drop_best": "delta_total minus the single most-improved day still > 0",
        "gate_4_heldout_positive": "delta restricted to day-inventory-extended.json heldout_days (last 25% by date) > 0",
    },
    "baseline_anchor": (
        "baseline rerun must reproduce the stored 2026-07-23 scorecard: n_trades==190 and "
        "|total - 5064.75| <= 1.00, else ABORT (fail closed, no gate eval)"
    ),
    "contamination_disclosure": (
        "Full-window descriptive cohort stats INCLUDING held-out dates were computed tonight "
        "BEFORE this A/B (PNL-ATTRIBUTION-2026-07-28.json). Naive cohort arithmetic predicts "
        "gate 4 FAILS (TL_only heldout cohort is +$68.45, so removing it should cost the "
        "heldout window about that much, modulo replacement trades). The hypothesis itself "
        "predates tonight -- the 2026-07-23 scorecard's public per-tier table already showed "
        "TRENDLINE -$1,830.10 full-window. This A/B settles it under real re-entry dynamics; "
        "ALL gate outcomes are reported, pass or fail."
    ),
    "config_delta": {"min_triggers_bear": {"baseline": 1, "variant": 2}},
}


def replay_entries(trades, spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame,
                   correct_shape: dict) -> tuple[list[dict], int, int]:
    """Identical exit re-derivation loop to engine_fullhist_replay.main (same fields)."""
    rows: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    for t in trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=correct_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=rtd,
            five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty), "entry_premium": round(float(t.entry_premium), 4),
            "triggers": t.triggers_fired, "dollar_pnl": res.dollar_pnl,
            "exit_reason": res.exit_reason,
        })
    return rows, n_no_opra, n_no_spy_day


def day_series(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        out[r["date"]] += float(r["dollar_pnl"])
    return dict(out)


def evaluate_gates(base_days: dict[str, float], var_days: dict[str, float],
                   heldout: set[str], eps: float = 0.005) -> dict:
    """The four pre-registered gates. Pure function -- guard-tested in
    backtest/tests/test_pnl_attribution_2026_07_28.py."""
    all_dates = sorted(set(base_days) | set(var_days))
    delta = {d: round(var_days.get(d, 0.0) - base_days.get(d, 0.0), 2) for d in all_dates}
    changed = {d: v for d, v in delta.items() if abs(v) > eps}
    n_improved = sum(1 for v in changed.values() if v > 0)
    n_worsened = sum(1 for v in changed.values() if v < 0)
    delta_total = round(sum(delta.values()), 2)
    best_day_gain = max(changed.values(), default=0.0)
    heldout_delta = round(sum(v for d, v in delta.items() if d in heldout), 2)
    gates = {
        "gate_1_positive_aggregate": {"delta_total": delta_total, "pass": delta_total > 0},
        "gate_2_day_majority": {"n_changed_days": len(changed), "n_improved": n_improved,
                                 "n_worsened": n_worsened, "pass": n_improved > n_worsened},
        "gate_3_survives_drop_best": {"best_day_gain": round(best_day_gain, 2),
                                       "delta_minus_best_day": round(delta_total - best_day_gain, 2),
                                       "pass": (delta_total - best_day_gain) > 0},
        "gate_4_heldout_positive": {"heldout_delta": heldout_delta, "n_heldout_days": len(heldout),
                                     "pass": heldout_delta > 0},
    }
    gates["all_pass"] = all(g["pass"] for g in gates.values() if isinstance(g, dict))
    gates["changed_days"] = dict(sorted(changed.items()))
    return gates


def trade_key(r: dict) -> tuple:
    return (r["date"], r["entry_time_et"], r["symbol"])


def main() -> int:
    t0 = time.time()
    PREREG["registered_at"] = dt.datetime.now().isoformat()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    # flush prereg to disk BEFORE any run (mtime documents the ordering)
    OUT_JSON.write_text(json.dumps({"prereg": PREREG, "status": "REGISTERED_RUNNING"},
                                     indent=2), encoding="utf-8")
    print(f"[ab] prereg flushed to {OUT_JSON}")

    inv = json.loads(DAY_INV.read_text(encoding="utf-8"))
    heldout = set(inv["heldout_days"])
    stored = json.loads(BASELINE_SCORECARD.read_text(encoding="utf-8"))
    stored_total = stored["headline"]["total_pnl"]
    stored_n = stored["headline"]["n_trades"]

    spy_df = pd.read_csv(efr.SPY_FILE)
    vix_df = pd.read_csv(efr.VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    results = {}
    for label, overrides in (("baseline", {}), ("variant", {"min_triggers_bear": 2})):
        cfg = dict(efr.SAFE_BASE_LIVE, **overrides)
        t1 = time.time()
        r = run_backtest(spy_df, vix_df, start_date=efr.FULL_START, end_date=efr.FULL_END, **cfg)
        rows, n_no_opra, n_no_spy = replay_entries(r.trades, spy_df, ribbon_lookup, correct_shape)
        total = round(sum(x["dollar_pnl"] for x in rows), 2)
        results[label] = {"rows": rows, "total": total, "n": len(rows),
                          "n_raw_entries": len(r.trades), "n_no_opra": n_no_opra,
                          "n_no_spy_day": n_no_spy, "elapsed_s": round(time.time() - t1, 1)}
        print(f"[ab] {label}: n={len(rows)} total={total:+.2f} "
              f"(raw={len(r.trades)}, no_opra={n_no_opra}) in {results[label]['elapsed_s']}s")

    base, var = results["baseline"], results["variant"]
    anchor_ok = (base["n"] == stored_n) and (abs(base["total"] - stored_total) <= 1.00)
    if not anchor_ok:
        out = {"prereg": PREREG, "status": "ABORT_BASELINE_ANCHOR_FAIL",
               "baseline": {"n": base["n"], "total": base["total"]},
               "stored_scorecard": {"n": stored_n, "total": stored_total}}
        OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("[ab] ABORT: baseline rerun does not reproduce the stored scorecard")
        return 1

    gates = evaluate_gates(day_series(base["rows"]), day_series(var["rows"]), heldout)

    bkeys = {trade_key(r) for r in base["rows"]}
    vkeys = {trade_key(r) for r in var["rows"]}
    removed = [r for r in base["rows"] if trade_key(r) not in vkeys]
    added = [r for r in var["rows"] if trade_key(r) not in bkeys]
    removed_pnl = round(sum(r["dollar_pnl"] for r in removed), 2)
    added_pnl = round(sum(r["dollar_pnl"] for r in added), 2)

    verdict = "SHIP_CANDIDATE" if gates["all_pass"] else "FAIL_DO_NOT_SHIP"
    out = {
        "prereg": PREREG,
        "status": "COMPLETE",
        "verdict": verdict,
        "baseline_anchor": {"pass": True, "n": base["n"], "total": base["total"],
                             "stored_n": stored_n, "stored_total": stored_total},
        "headline": {
            "baseline_total": base["total"], "variant_total": var["total"],
            "delta_total": round(var["total"] - base["total"], 2),
            "baseline_n": base["n"], "variant_n": var["n"],
            "n_removed_trades": len(removed), "removed_trades_pnl": removed_pnl,
            "n_added_trades": len(added), "added_trades_pnl": added_pnl,
        },
        "gates": gates,
        "removed_trades": removed,
        "added_trades": added,
        "runtime_s": round(time.time() - t0, 1),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[ab] wrote {OUT_JSON}")

    g = gates
    md = [
        "", "---", "",
        "## PRE-REGISTERED GATE-ADD A/B: min_triggers_bear 1 -> 2 "
        f"({dt.date.today().isoformat()})",
        "",
        f"Tool: `backtest/tools/min_triggers_bear2_gate_ab_2026_07_28.py`; full result: "
        f"`analysis/deep-research/min-triggers-bear2-ab-2026-07-28.json`. Prereg written to "
        "disk before the variant ran; contamination disclosed there (descriptive full-window "
        "slices, including held-out dates, were seen first -- and already predicted gate 4's "
        "direction).",
        "",
        f"**VERDICT: {verdict}**",
        "",
        "| Gate | Number | Pass |",
        "|---|---|---|",
        f"| baseline anchor (must reproduce stored scorecard) | n={base['n']} total=${base['total']:+,.2f} "
        f"vs stored n={stored_n} ${stored_total:+,.2f} | True |",
        f"| 1 positive aggregate | delta ${g['gate_1_positive_aggregate']['delta_total']:+,.2f} "
        f"(${base['total']:+,.2f} -> ${var['total']:+,.2f}) | {g['gate_1_positive_aggregate']['pass']} |",
        f"| 2 day-majority | {g['gate_2_day_majority']['n_improved']} improved / "
        f"{g['gate_2_day_majority']['n_worsened']} worsened of {g['gate_2_day_majority']['n_changed_days']} "
        f"changed days | {g['gate_2_day_majority']['pass']} |",
        f"| 3 survives drop-best | ${g['gate_3_survives_drop_best']['delta_minus_best_day']:+,.2f} "
        f"after dropping best day (+${g['gate_3_survives_drop_best']['best_day_gain']:,.2f}) "
        f"| {g['gate_3_survives_drop_best']['pass']} |",
        f"| 4 held-out positive | ${g['gate_4_heldout_positive']['heldout_delta']:+,.2f} over "
        f"{g['gate_4_heldout_positive']['n_heldout_days']} held-out days | "
        f"{g['gate_4_heldout_positive']['pass']} |",
        "",
        f"Trade diff: {len(removed)} removed (sum ${removed_pnl:+,.2f}), {len(added)} added "
        f"(sum ${added_pnl:+,.2f}) -- added trades are replacement entries the baseline's "
        "open position had suppressed.",
        "",
    ]
    with open(ATTRIB_MD, "a", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"[ab] appended results section to {ATTRIB_MD}")
    print(f"[ab] VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
