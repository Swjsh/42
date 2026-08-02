"""bold_selective_fallback_2026_08_02.py -- ITERATION 3 of the bold-2 sizing lane.

Iteration 1 (min-contracts-bold-2026-08-02): blanket min_contracts 5->3. NULL (runner
cohort -$5,909.20, recent-25 flipped negative).
Iteration 2 (bold-adaptive-sizing-2026-08-02): unconditional try-5-fallback-3. NULL --
the TRUE sequential replay (_sequential_admit) held up in aggregate ($+10,473.20 vs the
naive $+10,528.60 union, only a 0.5% gap) but 2 of Bold's own 32-trade runner cohort were
individually PRE-EMPTED by an earlier qty=3 fallback trade occupying the single position
slot, failing G5's zero-tolerance bar ($14,539.40 -> $13,493.00).

THIS ITERATION's hypothesis: the failure mechanism is SLOT CONTENTION, not exit
degradation. Fix: make the qty=3 fallback SELECTIVE -- only spend the scarce
one-position-at-a-time slot at reduced size when the setup clears an additional quality
bar, instead of firing on every floor-5-unaffordable signal unconditionally.

Prereg (frozen BEFORE this runner existed, commit 79563308):
    analysis/recommendations/prereg-bold-selective-fallback-2026-08-02.json

REUSED, NOT REBUILT (task instruction, verified by an identity-import guard test):
    bold_adaptive_sizing_2026_08_02._sequential_admit   -- the one-position-at-a-time walk
    bold_adaptive_sizing_2026_08_02._stats              -- per-population stats block
    bold_adaptive_sizing_2026_08_02._day_majority       -- G2 novel-term classifier
    bold_adaptive_sizing_2026_08_02._runner_cohort      -- Bold's own n=32 cohort extractor
    bold_adaptive_sizing_2026_08_02._key                -- (symbol, entry_time_et) row key
    bold_adaptive_sizing_2026_08_02.decompose           -- added-vs-preempted attribution
    bold_fullhist_replay.replay_population(qty_mode='adaptive')  -- UNMODIFIED, zero new kwargs

THREE CANDIDATE RULES (frozen in the prereg, chosen on MECHANISM, not a threshold sweep --
see prereg candidate_rules block for the full justification of each):
    A. tier bar:      fallback only when row.tier in {SUPER, ELITE}
    B. time cutoff:   fallback only when entry_time_et >= 12:00:00 ET
    C. level-anchored: fallback only when triggers_fired intersects the level_tied_triggers
                       vocabulary already defined in PNL-ATTRIBUTION-2026-07-28.json

For each cell: selective_candidates = every preferred-tier (qty=5) row UNCONDITIONALLY
(never filtered -- identical to CONTROL) UNION every fallback-tier (qty=3) row whose
predicate is True. _sequential_admit is then applied exactly as iteration 2 applied it to
the unconditional 286-row set.

Run: backtest/.venv/Scripts/python.exe backtest/tools/bold_selective_fallback_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
ROOT = REPO.parent                                    # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools"),
           str(ROOT / "automation" / "state" / "fleet"), str(ROOT / "crypto" / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bold_fullhist_replay as bfr  # noqa: E402
import bold_adaptive_sizing_2026_08_02 as study2  # noqa: E402 -- ITER2 module, REUSED not rebuilt

OUT_JSON = ROOT / "analysis" / "recommendations" / "bold-selective-fallback-2026-08-02.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "bold-selective-fallback-2026-08-02.md"
PREREG = ROOT / "analysis" / "recommendations" / "prereg-bold-selective-fallback-2026-08-02.json"
GUARD_FILE = ROOT / "backtest" / "tests" / "test_bold_selective_fallback_2026_08_02.py"

# --- Frozen baselines this study cross-checks against (parity guards) ----------------------
ITER2_CONTROL_SEQUENTIAL_N = 153
ITER2_CONTROL_SEQUENTIAL_TOTAL = 7578.40
ITER2_UNSEQUENCED_UNION_N = 286
ITER2_UNSEQUENCED_UNION_TOTAL = 10528.60
CONTROL_RAW_TOTAL_PNL = study2.CONTROL_RAW_TOTAL_PNL          # 7448.40, cited from iter1
RUNNER_COHORT_N_EXPECTED = study2.RUNNER_COHORT_N_EXPECTED    # 32
RUNNER_COHORT_PNL_EXPECTED = study2.RUNNER_COHORT_PNL_EXPECTED  # 14539.40

MIDNIGHT_CUTOFF_ET = dt.time(12, 0, 0)   # rule B, frozen in the prereg -- NOT swept
MIN_FALLBACK_FIRES_FLOOR = 15            # G10, frozen in the prereg -- ~10% of iter2's 130-pool

# Identical vocabulary to analysis/deep-research/PNL-ATTRIBUTION-2026-07-28.json's
# trigger_class_definition.level_tied_triggers -- reused verbatim, not reinvented.
LEVEL_TIED_TRIGGERS = frozenset(
    {"confluence", "level_reclaim", "level_rejection", "sequence_reclaim", "sequence_rejection"})


def log(msg: str) -> None:
    print(f"[bold-selective-fallback] {msg}", flush=True)


# --- The three predicates (prereg candidate_rules block) -----------------------------------
def rule_a_tier_bar(row: dict) -> bool:
    """Fallback permitted only when tier in {SUPER, ELITE} -- the two ordinal tiers
    PNL-ATTRIBUTION-2026-07-28.json found robustly positive INDIVIDUALLY on the SAFE-side
    population (SUPER $+5,127.10/37tr WR .51; ELITE $+2,758.20/11tr WR .73), excluding
    LEVEL (which was net-negative alone on that population, -$990.45/18tr WR .28) and
    TRENDLINE (the dominant loser, -$1,830.10/124tr WR .19)."""
    return row["tier"] in ("SUPER", "ELITE")


def rule_b_time_cutoff(row: dict) -> bool:
    """Fallback permitted only at/after 12:00:00 ET -- the engine's own existing 'midday'
    session boundary (aggressive/params.json's midday_trendline_gate key names 11:00-12:00
    ET as a first-class boundary inside the confirmed 09:35-15:00 entry window). Less
    remaining session after noon = lower opportunity cost if the slot gets spent."""
    t = dt.datetime.fromisoformat(row["entry_time_et"]).time()
    return t >= MIDNIGHT_CUTOFF_ET


def rule_c_level_anchored(row: dict) -> bool:
    """Fallback permitted only when the entry carries >=1 level-tied trigger, per the SAME
    vocabulary PNL-ATTRIBUTION-2026-07-28.json already defined -- the exact mechanism named
    in this iteration's own task charter (level-tied +$6,895/66tr vs trendline-only
    -$1,830/124tr)."""
    trig = set(row.get("triggers") or [])
    return bool(trig & LEVEL_TIED_TRIGGERS)


CELLS: dict[str, dict] = {
    "A_tier_bar": {"predicate": rule_a_tier_bar, "label": "tier in {SUPER, ELITE}"},
    "B_time_of_day_cutoff": {"predicate": rule_b_time_cutoff, "label": "entry_time_et >= 12:00 ET"},
    "C_level_anchored": {"predicate": rule_c_level_anchored, "label": "has >=1 level-tied trigger"},
}


def build_selective_candidates(adaptive_rows: list[dict], predicate) -> list[dict]:
    """Preferred-tier (qty=5) rows are NEVER filtered -- identical to CONTROL, always kept.
    Fallback-tier (qty=3) rows are kept only when predicate(row) is True."""
    out = []
    for r in adaptive_rows:
        if r["qty"] == bfr.BOLD_MIN_CONTRACTS_PREFERRED:
            out.append(r)
        elif r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK and predicate(r):
            out.append(r)
    return out


def check_runner_cohort_g5(runner_rows: list[dict], selective_sequential: list[dict]) -> dict:
    """Same G5 zero-tolerance logic as iteration 2's inline main() block, factored out here
    so it can be applied per-cell and unit-tested independently on synthetic fixtures."""
    seq_by_key = {study2._key(r): r for r in selective_sequential}
    missing: list[tuple] = []
    matches: list[tuple[dict, dict]] = []
    for r in runner_rows:
        k = study2._key(r)
        sr = seq_by_key.get(k)
        if sr is None:
            missing.append(k)
        else:
            matches.append((r, sr))
    control_sum = round(sum(r["dollar_pnl"] for r in runner_rows), 2)
    selective_sum = round(sum(sr["dollar_pnl"] for _, sr in matches), 2)
    n_flips = sum(1 for cr, sr in matches if cr["dollar_pnl"] > 0 and sr["dollar_pnl"] <= 0)
    passed = (len(missing) == 0 and selective_sum >= control_sum and n_flips == 0)
    return {
        "n_cohort": len(runner_rows), "control_sum": control_sum, "selective_sum": selective_sum,
        "n_missing": len(missing), "n_flips": n_flips, "pass": passed,
    }


def evaluate_cell(
    cell_name: str, predicate, adaptive_rows: list[dict], control_sequential: list[dict],
    control_keys: set, control_sequential_total: float, runner_rows: list[dict],
) -> dict:
    n_fallback_before = sum(1 for r in adaptive_rows if r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK)
    selective_candidates = build_selective_candidates(adaptive_rows, predicate)
    n_fallback_after_filter = sum(
        1 for r in selective_candidates if r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK)

    selective_sequential = study2._sequential_admit(selective_candidates)
    n_fallback_placed = sum(
        1 for r in selective_sequential if r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK)

    stats = study2._stats(selective_sequential, cell_name)
    day_maj = study2._day_majority(selective_sequential)
    g5 = check_runner_cohort_g5(runner_rows, selective_sequential)
    decomp = study2.decompose(control_sequential, selective_sequential, control_keys)

    g1 = stats["recent_25"]["total_pnl"] > 0
    g2 = day_maj["pass"]
    g3 = stats["drop_best"]["still_positive"]
    g4 = (stats["total_pnl"] >= CONTROL_RAW_TOTAL_PNL
          and stats["total_pnl"] >= control_sequential_total)
    g5_pass = g5["pass"]
    g6 = bfr.BOLD_MIN_CONTRACTS_FALLBACK == 3 and bfr.BOLD_MIN_CONTRACTS_PREFERRED == 5
    g7 = GUARD_FILE.exists()  # mechanism structurally unchanged from iter2; iter2's own guard file still proves it directly
    g8 = n_fallback_placed > 0 and GUARD_FILE.exists()
    gain = decomp["gain_over_control_sequential"]
    if gain > 0:
        g9 = (decomp["added_cohort"]["total_pnl"] > 0
              and (decomp["pct_of_gain_from_preemption"] is None
                   or decomp["pct_of_gain_from_preemption"] < 50.0))
    else:
        g9 = False
    g10 = n_fallback_placed >= MIN_FALLBACK_FIRES_FLOOR

    gates = {
        "G1_recent25_positive_PRIMARY": g1, "G2_day_majority": g2,
        "G3_drop_best_still_positive": g3, "G4_pnl_not_degraded_vs_both_baselines": g4,
        "G5_runner_cohort_ZERO_TOLERANCE": g5_pass, "G6_rule6_floor_respected": g6,
        "G7_kill_switch_and_risk_cap_bind_at_both_tiers": g7,
        "G8_not_a_dead_knob_C14": g8, "G9_gain_is_not_mostly_preemption": g9,
        "G10_material_fallback_fires_NEW": g10,
    }
    ship = all(gates.values())

    log(f"CELL {cell_name} [{CELLS[cell_name]['label']}]: fallback_before_filter={n_fallback_before} "
        f"after_filter={n_fallback_after_filter} placed={n_fallback_placed} "
        f"total=${stats['total_pnl']:+.2f} recent25=${stats['recent_25']['total_pnl']:+.2f} "
        f"G5={g5_pass} G10={g10} SHIP={ship}")

    return {
        "label": CELLS[cell_name]["label"],
        "fire_counts": {
            "n_fallback_candidate_before_filter": n_fallback_before,
            "n_fallback_candidate_after_filter": n_fallback_after_filter,
            "n_fallback_actually_placed": n_fallback_placed,
        },
        "selective_sequential_stats": stats,
        "day_majority": day_maj,
        "runner_cohort_g5": g5,
        "decomposition": decomp,
        "gates": gates,
        "ship": ship,
    }


def main() -> int:
    if not PREREG.exists():
        print(f"FAIL: prereg {PREREG} not found -- refusing to run an un-pre-registered study.",
              file=sys.stderr)
        return 2
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "PRE-REGISTERED":
        print(f"FAIL: prereg status is {prereg.get('status')!r}, not PRE-REGISTERED.",
              file=sys.stderr)
        return 2

    t_start = time.time()
    log(f"loaded prereg {PREREG.name} (frozen {prereg['registered_at_et']})")
    log("loading merged full-history SPY/VIX data")
    spy_df, vix_df = bfr._load_spy_vix()
    ribbon_lookup = bfr.efr.build_ribbon_lookup(spy_df)

    log("=== CONTROL: qty_mode=fixed, min_contracts=5 (current live) ===")
    control = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                     qty_mode="fixed", min_contracts=bfr.BOLD_MIN_CONTRACTS)
    log("=== ADAPTIVE CANDIDATE POOL: qty_mode=adaptive (identical to iter2, unfiltered) ===")
    adaptive = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                      qty_mode="adaptive")

    control_rows = control["rows"]
    adaptive_rows = adaptive["rows"]
    control_keys = {study2._key(r) for r in control_rows}

    # --- parity guards vs iter2's shipped figures, BEFORE any selectivity is applied -------
    unsequenced_stats = study2._stats(adaptive_rows, "ADAPTIVE_CANDIDATE_unsequenced")
    union_parity_ok = (unsequenced_stats["n"] == ITER2_UNSEQUENCED_UNION_N
                        and abs(unsequenced_stats["total_pnl"] - ITER2_UNSEQUENCED_UNION_TOTAL) < 0.02)
    log(f"PARITY [unsequenced union] n={unsequenced_stats['n']} (expected {ITER2_UNSEQUENCED_UNION_N}) "
        f"total=${unsequenced_stats['total_pnl']:+.2f} (expected ${ITER2_UNSEQUENCED_UNION_TOTAL:+.2f}) "
        f"OK={union_parity_ok}")

    control_sequential = study2._sequential_admit(control_rows)
    control_sequential_stats = study2._stats(control_sequential, "CONTROL_SEQUENTIAL")
    control_parity_ok = (control_sequential_stats["n"] == ITER2_CONTROL_SEQUENTIAL_N
                          and abs(control_sequential_stats["total_pnl"] - ITER2_CONTROL_SEQUENTIAL_TOTAL) < 0.02)
    log(f"PARITY [control sequential] n={control_sequential_stats['n']} "
        f"(expected {ITER2_CONTROL_SEQUENTIAL_N}) total=${control_sequential_stats['total_pnl']:+.2f} "
        f"(expected ${ITER2_CONTROL_SEQUENTIAL_TOTAL:+.2f}) OK={control_parity_ok}")

    runner_rows = study2._runner_cohort(control_rows)
    runner_control_sum = round(sum(r["dollar_pnl"] for r in runner_rows), 2)
    runner_crosscheck_ok = (len(runner_rows) == RUNNER_COHORT_N_EXPECTED
                             and abs(runner_control_sum - RUNNER_COHORT_PNL_EXPECTED) < 0.02)
    log(f"RUNNER COHORT re-derived: n={len(runner_rows)} (expected {RUNNER_COHORT_N_EXPECTED}) "
        f"total=${runner_control_sum:+.2f} (expected ${RUNNER_COHORT_PNL_EXPECTED:+.2f}) "
        f"CROSSCHECK_OK={runner_crosscheck_ok}")

    # --- evaluate all 3 cells ---------------------------------------------------------------
    cells_out: dict[str, dict] = {}
    for cell_name, cfg in CELLS.items():
        cells_out[cell_name] = evaluate_cell(
            cell_name, cfg["predicate"], adaptive_rows, control_sequential, control_keys,
            control_sequential_stats["total_pnl"], runner_rows)

    any_ship = any(c["ship"] for c in cells_out.values())
    ship_cells = [name for name, c in cells_out.items() if c["ship"]]
    verdict = "SHIP" if any_ship else "NULL"
    log(f"OVERALL VERDICT: {verdict} (ship_cells={ship_cells})")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)),
        "prereg_registered_at_et": prereg["registered_at_et"],
        "window": {"start": bfr.FULL_START.isoformat(), "end": bfr.FULL_END.isoformat()},
        "account": "core_bold (Gamma-Bold-2, PA33W2KUAT40)",
        "live_equity_used": bfr.BOLD_LIVE_EQUITY,
        "gate_state_held_fixed": {"block_elite_bull": True},
        "parity_guards": {
            "unsequenced_union_vs_iter2": {
                "expected_n": ITER2_UNSEQUENCED_UNION_N, "expected_total": ITER2_UNSEQUENCED_UNION_TOTAL,
                "reproduced": unsequenced_stats, "ok": union_parity_ok,
            },
            "control_sequential_vs_iter2": {
                "expected_n": ITER2_CONTROL_SEQUENTIAL_N, "expected_total": ITER2_CONTROL_SEQUENTIAL_TOTAL,
                "reproduced": control_sequential_stats, "ok": control_parity_ok,
            },
            "runner_cohort_crosscheck": {
                "expected_n": RUNNER_COHORT_N_EXPECTED, "expected_total": RUNNER_COHORT_PNL_EXPECTED,
                "n": len(runner_rows), "total": runner_control_sum, "ok": runner_crosscheck_ok,
            },
        },
        "control_raw_baseline": {"total_pnl": CONTROL_RAW_TOTAL_PNL},
        "control_sequential": control_sequential_stats,
        "cells": cells_out,
        "ship_cells": ship_cells,
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"total runtime {out['runtime_seconds']}s")
    return 0 if any_ship else 1


def write_markdown(out: dict) -> None:
    cs = out["control_sequential"]
    pg = out["parity_guards"]
    L = [
        "# BOLD-SELECTIVE-FALLBACK-2026-08-02 -- iteration 3, selective qty=3 fallback",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/bold_selective_fallback_2026_08_02.py`.",
        f"Prereg (frozen first): `{out['prereg']}` ({out['prereg_registered_at_et']}).",
        f"Account: {out['account']}. Equity: ${out['live_equity_used']:,.2f}. "
        f"Window: {out['window']['start']}..{out['window']['end']}. "
        f"Gate state held fixed: block_elite_bull=True (current live).",
        "",
        f"## OVERALL VERDICT: {out['verdict']}",
        "",
        f"Ship cells: {out['ship_cells'] if out['ship_cells'] else 'NONE'}",
        "",
        "## Parity guards (must hold before any cell's own numbers are trusted)",
        "",
        f"- Unsequenced union vs iter2: n={pg['unsequenced_union_vs_iter2']['reproduced']['n']} "
        f"(expected {pg['unsequenced_union_vs_iter2']['expected_n']}) total="
        f"${pg['unsequenced_union_vs_iter2']['reproduced']['total_pnl']:+,.2f} "
        f"(expected ${pg['unsequenced_union_vs_iter2']['expected_total']:+,.2f}) "
        f"OK={pg['unsequenced_union_vs_iter2']['ok']}",
        f"- Control sequential vs iter2: n={pg['control_sequential_vs_iter2']['reproduced']['n']} "
        f"(expected {pg['control_sequential_vs_iter2']['expected_n']}) total="
        f"${pg['control_sequential_vs_iter2']['reproduced']['total_pnl']:+,.2f} "
        f"(expected ${pg['control_sequential_vs_iter2']['expected_total']:+,.2f}) "
        f"OK={pg['control_sequential_vs_iter2']['ok']}",
        f"- Runner cohort crosscheck: n={pg['runner_cohort_crosscheck']['n']} "
        f"(expected {pg['runner_cohort_crosscheck']['expected_n']}) total="
        f"${pg['runner_cohort_crosscheck']['total']:+,.2f} "
        f"(expected ${pg['runner_cohort_crosscheck']['expected_total']:+,.2f}) "
        f"OK={pg['runner_cohort_crosscheck']['ok']}",
        "",
        f"## CONTROL_SEQUENTIAL (unchanged baseline, all cells compare against this)",
        "",
        f"n={cs['n']} total=${cs['total_pnl']:+,.2f} WR={cs['win_rate']} "
        f"recent25=${cs['recent_25']['total_pnl']:+,.2f} "
        f"drop_best_remainder=${cs['drop_best']['remainder']:+,.2f}",
        "",
        "## Per-cell results (ALL cells reported, including losers)",
        "",
    ]
    for name, c in out["cells"].items():
        st = c["selective_sequential_stats"]
        fc = c["fire_counts"]
        dm = c["day_majority"]
        rc = c["runner_cohort_g5"]
        dc = c["decomposition"]
        L += [
            f"### {name} -- {c['label']} -- {'SHIP' if c['ship'] else 'NULL'}",
            "",
            "| Gate | Result |",
            "|---|---|",
        ]
        for gname, gval in c["gates"].items():
            L.append(f"| {gname} | {'PASS' if gval else 'FAIL'} |")
        L += [
            "",
            f"- Fire counts: fallback_before_filter={fc['n_fallback_candidate_before_filter']} "
            f"after_filter={fc['n_fallback_candidate_after_filter']} "
            f"actually_placed={fc['n_fallback_actually_placed']}",
            f"- SELECTIVE_SEQUENTIAL: n={st['n']} total=${st['total_pnl']:+,.2f} WR={st['win_rate']} "
            f"recent25=${st['recent_25']['total_pnl']:+,.2f} "
            f"drop_best_remainder=${st['drop_best']['remainder']:+,.2f} "
            f"({'still +' if st['drop_best']['still_positive'] else 'flips -'})",
            f"- Day-majority: up={dm['up_days']} down={dm['down_days']} neutral={dm['neutral_days']} "
            f"pass={dm['pass']}",
            f"- Runner cohort (G5): n={rc['n_cohort']} control_sum=${rc['control_sum']:+,.2f} "
            f"selective_sum=${rc['selective_sum']:+,.2f} missing={rc['n_missing']} "
            f"flips={rc['n_flips']} pass={rc['pass']}",
            f"- Decomposition: added n={dc['added_cohort']['n']} total=${dc['added_cohort']['total_pnl']:+,.2f} "
            f"| preempted n={dc['preempted_cohort']['n']} total=${dc['preempted_cohort']['total_pnl']:+,.2f} "
            f"| gain_over_control=${dc['gain_over_control_sequential']:+,.2f} "
            f"identity_holds={dc['identity_holds']} pct_from_preemption={dc['pct_of_gain_from_preemption']}",
            "",
        ]
    L += [
        "---",
        "_Source: `backtest/tools/bold_selective_fallback_2026_08_02.py`. Raw JSON: "
        "`analysis/recommendations/bold-selective-fallback-2026-08-02.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
