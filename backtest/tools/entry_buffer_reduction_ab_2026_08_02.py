#!/usr/bin/env python
"""entry_buffer_reduction_ab_2026_08_02.py -- candidate entry_cross_buffer reduction A/B.

Pre-registered BEFORE this file existed: analysis/recommendations/
entry-buffer-reduction-prereg-2026-08-02.json (commit 78979314). Read that file for the full
hypothesis/method/gates -- this module implements exactly what it describes and nothing more.

WHY THIS IS SAFE TO TEST WITHOUT AN exit_manager REPLAY: TP1/stop are computed off `mid`
(heartbeat_core.py ~line 2004-2005: `tp = round(mid * (1 + tp1_pct), 2)`; fleet_live.py
~line 449-455, same shape), NOT off `entry_px`. A buffer change therefore cannot alter which
trades are taken, their qty (also `mid`-based, via risk_gate.max_affordable_qty), or their
exit rules -- it can ONLY shift the entry cost basis of trades that still cross. This makes
the effect of a smaller buffer on an ALREADY-REAL, ALREADY-EXITED trade a closed-form
per-contract $ shift, not something that needs re-walking through the exit engine.

METHOD (real data only, no synthetic backfill):
  STILL-FILLS: fill_price <= ask_decision + candidate_buffer. DISCLOSED ASSUMPTION: realized
    execution price is buffer-independent as long as the tighter limit still clears it (the
    limit is a ceiling on what we could pay, not a target the exchange fills TO) -- NOT
    independently verified against Alpaca's specific price-improvement/routing internals.
  FILLED rows: delta_pnl = (CROSS_BUFFER - candidate_buffer) * qty * 100, applied identically
    to every trades.csv leg sharing that entry's order_id (TP1 + runner legs share one cost
    basis, so they shift by the same per-contract amount).
  MISSED rows: delta_pnl = -(sum of that entry's real realized dollar_pnl across all legs) --
    the entire trade is foregone. A limit that never crosses is a missed trade, not a free
    option (explicit mission instruction) -- modeled exactly that way, no exceptions.

Run:
    backtest/.venv/Scripts/python.exe backtest/tools/entry_buffer_reduction_ab_2026_08_02.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import entry_execution_cost_2026_08_02 as eec  # noqa: E402

PRICED_JSON = REPO / "analysis" / "recommendations" / "entry-execution-cost-2026-08-02.json"
TRADES_CSV = REPO / "journal" / "trades.csv"
PREREG_JSON = REPO / "analysis" / "recommendations" / "entry-buffer-reduction-prereg-2026-08-02.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "entry-buffer-reduction-results-2026-08-02.json"

CANDIDATES = (0.01, 0.015, 0.02)
BASELINE_BUFFER = eec.CROSS_BUFFER  # 0.03
RUNNER_STAGES = {"trail", "runner_target"}


# =============================================================================
# Pure helpers
# =============================================================================

def still_fills(fill_price: float, ask_decision: float, candidate_buffer: float) -> bool:
    """PURE. See module docstring STILL-FILLS. A tiny epsilon absorbs float/round noise from
    the source data's own 2-decimal rounding (entry_px, ask_decision are cent-rounded)."""
    return fill_price <= round(ask_decision + candidate_buffer, 2) + 1e-9


def filled_delta_pnl(qty: float, candidate_buffer: float,
                     baseline_buffer: float = BASELINE_BUFFER) -> float:
    """PURE. Per-entry $ delta when the trade STILL fills at the candidate buffer -- a pure
    cost-basis shift, identical for every leg of this entry (see module docstring)."""
    return round((baseline_buffer - candidate_buffer) * qty * 100, 2)


# =============================================================================
# I/O
# =============================================================================

def load_priced_rows() -> list[dict]:
    payload = json.loads(PRICED_JSON.read_text(encoding="utf-8"))
    return payload["rows"]


def load_legs_by_entry_order_id() -> dict[str, list[dict]]:
    """{entry_order_id: [{stage, dollar_pnl, date}, ...]} -- every trades.csv leg, not just
    the priced-105 subset, so runner-cohort membership can be checked against ALL legs of a
    priced entry even if this loader is reused elsewhere."""
    out: dict[str, list[dict]] = {}
    if not TRADES_CSV.exists():
        return out
    with TRADES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                meta = json.loads(row.get("archetype_match_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            eoid = meta.get("entry_order_id")
            if not eoid:
                continue
            stage_match = re.search(r"stage=(\w+)", row.get("notes_short") or "")
            try:
                pnl = float(row.get("dollar_pnl") or 0)
            except ValueError:
                pnl = 0.0
            out.setdefault(eoid, []).append({
                "stage": stage_match.group(1) if stage_match else None,
                "dollar_pnl": pnl, "date": row.get("date"),
            })
    return out


# =============================================================================
# Orchestration
# =============================================================================

def run_candidate(candidate: float, priced_rows: list[dict], legs_by_eoid: dict) -> dict:
    per_day_delta: dict[str, float] = {}
    misses: list[dict] = []
    runner_misses: list[dict] = []
    n_filled = 0
    n_missed = 0

    for r in priced_rows:
        oid = r["order_id"]
        legs = legs_by_eoid.get(oid, [])
        real_total_pnl = round(sum(leg["dollar_pnl"] for leg in legs), 2) if legs else None
        stages = {leg["stage"] for leg in legs}
        is_runner_cohort = bool(stages & RUNNER_STAGES)
        date = r["date_et"]

        if still_fills(r["fill_price"], r["ask_decision"], candidate):
            n_filled += 1
            delta = filled_delta_pnl(r["qty"], candidate)
        else:
            n_missed += 1
            delta = -(real_total_pnl if real_total_pnl is not None else 0.0)
            miss_row = {"order_id": oid, "arm": r["arm"], "symbol": r["symbol"], "date_et": date,
                       "fill_price": r["fill_price"], "ask_decision": r["ask_decision"],
                       "candidate_limit": round(r["ask_decision"] + candidate, 2),
                       "real_pnl_foregone": real_total_pnl}
            misses.append(miss_row)
            if is_runner_cohort:
                runner_misses.append(miss_row)

        per_day_delta[date] = round(per_day_delta.get(date, 0.0) + delta, 2)

    total_delta = round(sum(per_day_delta.values()), 2)
    days_sorted = sorted(per_day_delta.items())
    n_days = len(days_sorted)
    n_days_nonneg = sum(1 for _, v in days_sorted if v >= 0)

    drop_best_day, drop_best_val = (max(days_sorted, key=lambda kv: kv[1])
                                    if days_sorted else (None, 0.0))
    total_drop_best = round(total_delta - drop_best_val, 2)

    n_runner_in_pop = sum(1 for r in priced_rows
                          if bool({leg["stage"] for leg in legs_by_eoid.get(r["order_id"], [])}
                                  & RUNNER_STAGES))

    gates = {
        "primary_aggregate_positive": total_delta > 0,
        "day_majority": n_days_nonneg >= (n_days // 2 + 1) if n_days else False,
        "drop_best_still_positive": total_drop_best > 0,
        "runner_cohort_zero_tolerance": len(runner_misses) == 0,
    }
    all_gates_pass = all(gates.values())

    return {
        "candidate_buffer": candidate,
        "n_priced": len(priced_rows), "n_filled": n_filled, "n_missed": n_missed,
        "fill_rate_pct": round(100 * n_filled / len(priced_rows), 1) if priced_rows else None,
        "total_delta_pnl": total_delta,
        "n_trading_days": n_days, "n_days_nonneg_delta": n_days_nonneg,
        "day_majority_threshold": (n_days // 2 + 1) if n_days else None,
        "drop_best_day": drop_best_day, "drop_best_day_delta": drop_best_val,
        "total_delta_pnl_drop_best": total_drop_best,
        "n_runner_cohort_in_population": n_runner_in_pop,
        "n_runner_cohort_missed": len(runner_misses),
        "runner_cohort_misses": runner_misses,
        "all_misses": misses,
        "gates": gates,
        "verdict": "PASS_ALL_GATES" if all_gates_pass else "FAIL",
        "per_day_delta": dict(days_sorted),
    }


def main() -> int:
    priced_rows = load_priced_rows()
    legs_by_eoid = load_legs_by_entry_order_id()

    results = [run_candidate(c, priced_rows, legs_by_eoid) for c in CANDIDATES]
    any_pass = any(r["verdict"] == "PASS_ALL_GATES" for r in results)

    summary = {
        "generated_at_note": "run via setup/scripts/et_clock.py at report time, see markdown artifact",
        "baseline_buffer": BASELINE_BUFFER,
        "n_priced_entries": len(priced_rows),
        "candidates": results,
        "any_candidate_passes_all_gates": any_pass,
        "disposition": ("SHIP the smallest candidate that passes every gate"
                        if any_pass else
                        "NULL -- entry_cross_buffer stays 0.03, no candidate cleared every gate"),
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # fold a compact results pointer into the pre-registration file (append-only, never
    # rewrites the pre_registration block itself)
    prereg = json.loads(PREREG_JSON.read_text(encoding="utf-8"))
    prereg["results"] = {
        "ran_after_prereg_commit": "78979314",
        "full_output": "analysis/recommendations/entry-buffer-reduction-results-2026-08-02.json",
        "any_candidate_passes_all_gates": any_pass,
        "disposition": summary["disposition"],
        "per_candidate_headline": [
            {"candidate": r["candidate_buffer"], "verdict": r["verdict"],
             "total_delta_pnl": r["total_delta_pnl"], "fill_rate_pct": r["fill_rate_pct"],
             "n_missed": r["n_missed"], "n_runner_cohort_missed": r["n_runner_cohort_missed"],
             "gates": r["gates"]}
            for r in results
        ],
    }
    PREREG_JSON.write_text(json.dumps(prereg, indent=2, default=str), encoding="utf-8")

    print(json.dumps({k: v for k, v in summary.items() if k != "candidates"}, indent=2))
    for r in results:
        print(f"\n--- candidate {r['candidate_buffer']} ---")
        print(json.dumps({k: v for k, v in r.items()
                          if k not in ("all_misses", "per_day_delta")}, indent=2))
    print(f"\nwrote -> {OUT_JSON.relative_to(REPO)}")
    print(f"folded results pointer -> {PREREG_JSON.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
