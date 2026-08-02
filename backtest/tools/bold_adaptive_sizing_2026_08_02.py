"""bold_adaptive_sizing_2026_08_02.py -- TRUE SEQUENTIAL replay of the BOLD-ADAPTIVE-SIZING-
TRY5-FALLBACK3 rule: try min_contracts=5 first, fall back to min_contracts=3 ONLY when 5 is
itself RISK_CAP-unaffordable at the current premium/equity.

Prereg (frozen BEFORE this runner executed):
    analysis/recommendations/prereg-bold-adaptive-sizing-2026-08-02.json

WHY THIS TOOL EXISTS, NOT JUST A RE-READ OF min-contracts-bold-2026-08-02.json's
`exploratory_adaptive_not_shipped` BLOCK: that number ($+10,528.60) was computed
"exact-by-construction" by UNION-ing two separately-run backtests: control_rows (floor=5,
unchanged) plus the variant-only rows floor=3 newly unlocks. That union is exact for
PER-ROW P&L (proven: exit timing/reason is a pure function of (entry, qty), independent of
which OTHER trades exist -- see method note below) but is NOT exact for the ADMISSION SET,
because this engine holds exactly ONE position at a time (broker-verified-flat-before-entry,
C11) and the union silently assumes every admitted row actually gets taken, ignoring that a
newly-unlocked qty=3 fallback trade can OCCUPY the position slot and pre-empt a LATER signal
the floor-5-only engine would have taken at qty=5. That mechanism is invisible to a
recombination and only surfaces in a real, entry-time-ordered, exit-time-gated walk -- this
tool builds exactly that walk and reports the honest number next to the derived one.

PRECEDENT THIS ARTIFACT ALREADY BURNED (why this isn't paranoia): backtest/tools/
filter5_ribbon_fate_2026_07_31.py's attribution_block() found a headline +$738.60 "from
deleting filter 5" was 86% position-sequencing/pre-emption -- the gate's own added cohort
was worth ~$4.93/trade. That helper exists "so this can never be silently omitted again."
This tool reproduces the same decomposition (added vs pre-empted cohort) for the
adaptive-sizing case.

METHOD (see prereg's `method` block for the full rationale):
  1. replay_population(qty_mode='fixed', min_contracts=5) -> CONTROL_ROWS (the current live
     engine's own candidate set, floor-5-only, now carrying exit_time_et -- previously
     computed by walk_exit_manager but discarded before this tool existed).
  2. replay_population(qty_mode='adaptive') -> ADAPTIVE_CANDIDATE_ROWS: ONE direct pass
     that resolves EVERY one of the 334 raw signals via resolve_bold_qty_adaptive (try 5,
     fall back to 3), walking the exit at whichever qty it resolves. This is NOT a
     recombination of two runs -- it is the adaptive rule's own first-class code path,
     structurally guaranteed to produce the identical per-row P&L as the union would have
     (same deterministic (entry, qty) -> exit function), verified below as a parity
     cross-check against the already-shipped $10,528.60 figure before any sequential
     filtering is applied.
  3. A NEW sequential-admission pass (`_sequential_admit`, adapted from
     elite_bull_postfix_requal_2026_07_31.py's `sequential_hold()` -- same "one position at
     a time, an entry <= the previous KEPT trade's exit is pre-empted" concept, re-implemented
     against this tool's own row schema) applied INDEPENDENTLY to CONTROL_ROWS and
     ADAPTIVE_CANDIDATE_ROWS, producing CONTROL_SEQUENTIAL and ADAPTIVE_SEQUENTIAL -- the
     TRUE replayed populations, apples-to-apples (identical methodology both arms).
  4. Decomposition: ADDED cohort (ADAPTIVE_SEQUENTIAL rows never in CONTROL_ROWS at all --
     only possible because of the qty=3 fallback) vs PRE-EMPTED cohort (CONTROL_SEQUENTIAL
     rows absent from ADAPTIVE_SEQUENTIAL -- displaced by an earlier adaptive-only trade).

Run: backtest/.venv/Scripts/python.exe backtest/tools/bold_adaptive_sizing_2026_08_02.py
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
from exit_leak_decompose import exit_family  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "bold-adaptive-sizing-2026-08-02.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "bold-adaptive-sizing-2026-08-02.md"
PREREG = ROOT / "analysis" / "recommendations" / "prereg-bold-adaptive-sizing-2026-08-02.json"
GUARD_FILE = ROOT / "backtest" / "tests" / "test_bold_adaptive_sizing_2026_08_02.py"

CONTROL_MIN_CONTRACTS = 5   # current live automation/state/aggressive/params.json value
RECENT_N = 25               # "recent-25" per J's dynamic-market/recency doctrine

# Already-shipped baselines this study compares against (min-contracts-bold-2026-08-02.json,
# commit ba51e5fb) -- hardcoded WITH provenance citation, matching this repo's established
# anchor-constant convention (e.g. bold_fullhist_replay.py's own SAFE_ANCHOR_RUNNER_N/PNL).
CONTROL_RAW_TOTAL_PNL = 7448.40   # min-contracts-bold-2026-08-02.json .control.total_pnl
DERIVED_UNION_TOTAL_PNL = 10528.60  # .exploratory_adaptive_not_shipped.total_pnl (the naive, unsequenced union this tool re-derives directly and then sequences)
DERIVED_UNION_N = 286
DERIVED_UNION_RECENT25_PNL = 470.25
RUNNER_COHORT_N_EXPECTED = 32           # Bold's OWN runner cohort (NOT the SAFE 35/$15,774 anchor)
RUNNER_COHORT_PNL_EXPECTED = 14539.40   # .bold_own_runner_cohort.control_pnl_sum


def log(msg: str) -> None:
    print(f"[bold-adaptive-sizing] {msg}", flush=True)


def _key(row: dict) -> tuple:
    return (row["symbol"], row["entry_time_et"])


def _sequential_admit(rows: list[dict]) -> list[dict]:
    """PRIMARY mechanism of this study: the core holds ONE position at a time. An entry
    whose entry_time_et is <= the previous KEPT row's exit_time_et is consumed by the
    still-open position -> dropped (pre-empted), never independently counted.

    Adapted from backtest/tools/elite_bull_postfix_requal_2026_07_31.py's sequential_hold()
    (identical concept -- re-implemented against this tool's own entry_time_et/exit_time_et
    row-key schema rather than cross-imported, matching this repo's established per-tool
    hand-built-primitive convention; see bold_fullhist_replay.py's own "WHY A SEPARATE TOOL"
    docstring section for the precedent this follows).

    UNRESOLVED-TRADE CONVENTION (disclosed, not silently assumed): every trade in this
    0DTE population is either resolved (exit_time_et set, always same trading day -- the
    ribbon_ride exit shape's time_stop fires by 15:40 ET at the latest) or, in the rare case
    the option's own cached bar series ends before an exit condition fires, unresolved
    (exit_time_et is None). An unresolved trade's SLOT is treated as occupied through
    16:00 ET of its own entry day (0DTE options are worthless/expired by then regardless),
    never carried into a later day and never treated as instantly free -- the conservative
    direction (a missing exit_time_et could otherwise wrongly free the slot for a
    same-day trade that could not really have been taken)."""
    kept: list[dict] = []
    current_exit: dt.datetime | None = None
    for r in sorted(rows, key=lambda x: x["entry_time_et"]):
        entry = dt.datetime.fromisoformat(r["entry_time_et"])
        if current_exit is not None and entry <= current_exit:
            continue
        kept.append(r)
        exit_s = r.get("exit_time_et")
        if exit_s:
            current_exit = dt.datetime.fromisoformat(exit_s)
        else:
            entry_date = dt.datetime.fromisoformat(r["entry_time_et"]).date()
            current_exit = dt.datetime.combine(entry_date, dt.time(16, 0))
    return kept


def _stats(rows: list[dict], label: str) -> dict:
    n = len(rows)
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = [p for p in pnls if p > 0]
    wr = round(len(wins) / n, 4) if n else None
    avg = round(total / n, 2) if n else None

    if pnls:
        best = max(pnls)
        remainder = round(total - best, 2)
    else:
        best, remainder = 0.0, 0.0

    ordered = sorted(rows, key=lambda r: r["entry_time_et"])
    recent = ordered[-RECENT_N:] if ordered else []
    recent_pnls = [r["dollar_pnl"] for r in recent]
    recent_total = round(sum(recent_pnls), 2)
    recent_wr = round(sum(1 for p in recent_pnls if p > 0) / len(recent_pnls), 4) if recent_pnls else None

    notionals = [r["entry_premium"] * r["qty"] * 100.0 for r in rows]

    return {
        "label": label, "n": n, "total_pnl": total, "win_rate": wr, "avg_pnl_per_trade": avg,
        "drop_best": {"best_trade_pnl": round(best, 2), "remainder": remainder,
                      "still_positive": remainder > 0},
        "recent_25": {"n": len(recent), "total_pnl": recent_total, "win_rate": recent_wr,
                      "start_date": recent[0]["date"] if recent else None,
                      "end_date": recent[-1]["date"] if recent else None},
        "notional": {
            "avg": round(sum(notionals) / len(notionals), 2) if notionals else None,
            "max": round(max(notionals), 2) if notionals else None,
            "min": round(min(notionals), 2) if notionals else None,
        },
    }


def _day_majority(rows: list[dict]) -> dict:
    """NOVEL TERM (frozen definition, prereg G2): group by entry calendar date, sum P&L per
    day, classify up (>0) / down (<0) / neutral (==0, excluded from the ratio). PASS iff
    up_days > down_days (strict majority among decided days)."""
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["dollar_pnl"], 2)
    up = sum(1 for v in by_day.values() if v > 0)
    down = sum(1 for v in by_day.values() if v < 0)
    neutral = sum(1 for v in by_day.values() if v == 0)
    return {"n_days": len(by_day), "up_days": up, "down_days": down, "neutral_days": neutral,
            "pass": up > down, "by_day_pnl": by_day}


def _runner_cohort(control_rows: list[dict]) -> list[dict]:
    """Bold's OWN runner cohort, re-derived fresh (not hardcoded) via the SAME
    exit_family()==RUNNER_TRAIL classification the parent min-contracts study used --
    cross-checked below against the already-shipped n=32/$14,539.40 figure."""
    return [r for r in control_rows if exit_family(r["exit_reason"], r["resolved_stop_mode"]) == "RUNNER_TRAIL"]


def decompose(control_sequential: list[dict], adaptive_sequential: list[dict],
              control_candidate_keys: set) -> dict:
    """Task-mandated decomposition, mirrors filter5_ribbon_fate_2026_07_31.py's
    attribution_block(): ADDED cohort (adaptive-sequential rows whose key never appears in
    the floor-5-only CONTROL CANDIDATE set at all -- only possible via the qty=3 fallback)
    vs PRE-EMPTED cohort (control-sequential rows -- i.e. what the CURRENT engine's own true
    sequential walk actually takes -- absent from adaptive-sequential, displaced by an
    earlier adaptive-only trade occupying the slot)."""
    adaptive_keys = {_key(r) for r in adaptive_sequential}
    added = [r for r in adaptive_sequential if _key(r) not in control_candidate_keys]
    preempted = [r for r in control_sequential if _key(r) not in adaptive_keys]
    added_total = round(sum(r["dollar_pnl"] for r in added), 2)
    preempted_total = round(sum(r["dollar_pnl"] for r in preempted), 2)
    adaptive_total = round(sum(r["dollar_pnl"] for r in adaptive_sequential), 2)
    control_total = round(sum(r["dollar_pnl"] for r in control_sequential), 2)
    gain_over_control = round(adaptive_total - control_total, 2)
    identity_check = round(added_total - preempted_total, 2)
    pct_of_gain_from_preemption = (
        round(100.0 * (-preempted_total) / gain_over_control, 1)
        if gain_over_control > 0 else None)
    return {
        "_doc": "delta_over_control == added_total - preempted_total (accounting identity, verified below).",
        "added_cohort": {"n": len(added), "total_pnl": added_total,
                          "trades": [{"date": r["date"], "symbol": r["symbol"], "side": r["side"],
                                      "qty": r["qty"], "dollar_pnl": r["dollar_pnl"]} for r in added]},
        "preempted_cohort": {"n": len(preempted), "total_pnl": preempted_total,
                              "trades": [{"date": r["date"], "symbol": r["symbol"], "side": r["side"],
                                          "qty": r["qty"], "dollar_pnl": r["dollar_pnl"]} for r in preempted]},
        "gain_over_control_sequential": gain_over_control,
        "identity_check_added_minus_preempted": identity_check,
        "identity_holds": abs(gain_over_control - identity_check) < 0.02,
        "pct_of_gain_from_preemption": pct_of_gain_from_preemption,
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
                                     qty_mode="fixed", min_contracts=CONTROL_MIN_CONTRACTS)
    log("=== ADAPTIVE: qty_mode=adaptive (try 5, fallback 3) -- ONE direct pass, not a union ===")
    adaptive = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                      qty_mode="adaptive")

    control_rows = control["rows"]
    adaptive_candidate_rows = adaptive["rows"]
    control_keys = {_key(r) for r in control_rows}

    # --- parity cross-check vs the already-shipped naive-union figures (task ask: report
    # the derived number NEXT TO the replayed one) -----------------------------------------
    unsequenced_stats = _stats(adaptive_candidate_rows, "ADAPTIVE_CANDIDATE_unsequenced")
    parity_ok = (unsequenced_stats["n"] == DERIVED_UNION_N
                 and abs(unsequenced_stats["total_pnl"] - DERIVED_UNION_TOTAL_PNL) < 0.02)
    log(f"PARITY CHECK vs shipped exploratory union: n={unsequenced_stats['n']} "
        f"(expected {DERIVED_UNION_N}) total=${unsequenced_stats['total_pnl']:+.2f} "
        f"(expected ${DERIVED_UNION_TOTAL_PNL:+.2f}) PARITY_OK={parity_ok}")

    # --- fire/participation counts (L243 discipline) ---------------------------------------
    n_preferred_tier = sum(1 for r in adaptive_candidate_rows if r["qty"] == bfr.BOLD_MIN_CONTRACTS_PREFERRED)
    n_fallback_tier = sum(1 for r in adaptive_candidate_rows if r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK)
    participation = {
        "n_raw_signals": control["n_raw_entries"],
        "n_excluded_no_opra_cache": control["n_excluded_no_opra_cache"],
        "n_excluded_no_spy_day": control["n_excluded_no_spy_day"],
        "control_n_excluded_risk_cap_deadlock": control["n_excluded_risk_cap_deadlock"],
        "adaptive_n_excluded_risk_cap_deadlock_both_tiers": adaptive["n_excluded_risk_cap_deadlock"],
        "control_n_candidate": len(control_rows),
        "adaptive_n_candidate": len(adaptive_candidate_rows),
        "adaptive_n_candidate_preferred_tier_qty5": n_preferred_tier,
        "adaptive_n_candidate_fallback_tier_qty3": n_fallback_tier,
    }
    log(f"FIRE COUNTS: raw={participation['n_raw_signals']} "
        f"control_candidate={participation['control_n_candidate']} "
        f"adaptive_candidate={participation['adaptive_n_candidate']} "
        f"(preferred_qty5={n_preferred_tier} fallback_qty3={n_fallback_tier})")

    # --- THE REAL WORK: sequential admission, apples-to-apples both arms ------------------
    control_sequential = _sequential_admit(control_rows)
    adaptive_sequential = _sequential_admit(adaptive_candidate_rows)
    n_preempted_control_only = len(control_rows) - len(control_sequential)
    n_preempted_adaptive = len(adaptive_candidate_rows) - len(adaptive_sequential)
    log(f"SEQUENTIAL ADMISSION: control {len(control_rows)}->{len(control_sequential)} "
        f"(self-pre-emption: {n_preempted_control_only}); adaptive "
        f"{len(adaptive_candidate_rows)}->{len(adaptive_sequential)} "
        f"(pre-emption: {n_preempted_adaptive})")

    control_sequential_stats = _stats(control_sequential, "CONTROL_SEQUENTIAL")
    adaptive_sequential_stats = _stats(adaptive_sequential, "ADAPTIVE_SEQUENTIAL")
    n_fallback_placed = sum(1 for r in adaptive_sequential if r["qty"] == bfr.BOLD_MIN_CONTRACTS_FALLBACK)
    participation["adaptive_n_actually_placed_post_sequential"] = len(adaptive_sequential)
    participation["adaptive_n_fallback_actually_placed"] = n_fallback_placed

    log(f"HONEST REPLAYED (sequential): CONTROL n={control_sequential_stats['n']} "
        f"total=${control_sequential_stats['total_pnl']:+.2f} | ADAPTIVE n="
        f"{adaptive_sequential_stats['n']} total=${adaptive_sequential_stats['total_pnl']:+.2f} "
        f"(derived-unsequenced was ${unsequenced_stats['total_pnl']:+.2f}, "
        f"gap=${unsequenced_stats['total_pnl'] - adaptive_sequential_stats['total_pnl']:+.2f})")

    day_maj = _day_majority(adaptive_sequential)
    control_day_maj = _day_majority(control_sequential)  # informational only, not gated -- context for whether a losing day-majority is specific to the adaptive rule or a pre-existing shape of this trade population
    log(f"DAY-MAJORITY (informational, control for context): up={control_day_maj['up_days']} "
        f"down={control_day_maj['down_days']} pass={control_day_maj['pass']} | "
        f"ADAPTIVE (gated): up={day_maj['up_days']} down={day_maj['down_days']} pass={day_maj['pass']}")

    # --- runner cohort, re-derived fresh + cross-checked --------------------------------
    runner_rows = _runner_cohort(control_rows)
    runner_control_sum = round(sum(r["dollar_pnl"] for r in runner_rows), 2)
    runner_crosscheck_ok = (len(runner_rows) == RUNNER_COHORT_N_EXPECTED
                             and abs(runner_control_sum - RUNNER_COHORT_PNL_EXPECTED) < 0.02)
    log(f"RUNNER COHORT re-derived: n={len(runner_rows)} (expected {RUNNER_COHORT_N_EXPECTED}) "
        f"total=${runner_control_sum:+.2f} (expected ${RUNNER_COHORT_PNL_EXPECTED:+.2f}) "
        f"CROSSCHECK_OK={runner_crosscheck_ok}")

    adaptive_seq_by_key = {_key(r): r for r in adaptive_sequential}
    runner_missing = []
    runner_matches = []
    for r in runner_rows:
        k = _key(r)
        ar = adaptive_seq_by_key.get(k)
        if ar is None:
            runner_missing.append(k)
        else:
            runner_matches.append((r, ar))
    runner_adaptive_sum = round(sum(ar["dollar_pnl"] for _, ar in runner_matches), 2)
    n_flips = sum(1 for cr, ar in runner_matches if cr["dollar_pnl"] > 0 and ar["dollar_pnl"] <= 0)
    g5_pass = (len(runner_missing) == 0 and runner_adaptive_sum >= runner_control_sum
               and n_flips == 0)
    log(f"G5 RUNNER COHORT vs ADAPTIVE_SEQUENTIAL: missing={len(runner_missing)} "
        f"adaptive_sum=${runner_adaptive_sum:+.2f} (control=${runner_control_sum:+.2f}) "
        f"flips={n_flips} G5_PASS={g5_pass}")

    # --- decomposition (task step 3) -------------------------------------------------------
    decomp = decompose(control_sequential, adaptive_sequential, control_keys)
    log(f"DECOMPOSITION: added n={decomp['added_cohort']['n']} total="
        f"${decomp['added_cohort']['total_pnl']:+.2f} | preempted n="
        f"{decomp['preempted_cohort']['n']} total=${decomp['preempted_cohort']['total_pnl']:+.2f} "
        f"| identity_holds={decomp['identity_holds']} | pct_from_preemption="
        f"{decomp['pct_of_gain_from_preemption']}")

    # --- gates (frozen in the prereg BEFORE this run) --------------------------------------
    g1 = adaptive_sequential_stats["recent_25"]["total_pnl"] > 0
    g2 = day_maj["pass"]
    g3 = adaptive_sequential_stats["drop_best"]["still_positive"]
    g4 = (adaptive_sequential_stats["total_pnl"] >= CONTROL_RAW_TOTAL_PNL
          and adaptive_sequential_stats["total_pnl"] >= control_sequential_stats["total_pnl"])
    g5 = g5_pass
    g6 = bfr.BOLD_MIN_CONTRACTS_FALLBACK == 3 and bfr.BOLD_MIN_CONTRACTS_PREFERRED == 5
    g7 = GUARD_FILE.exists()  # structural proof lives in the guard file, not silently asserted here
    g8 = n_fallback_placed > 0 and GUARD_FILE.exists()
    gain = decomp["gain_over_control_sequential"]
    if gain > 0:
        g9 = (decomp["added_cohort"]["total_pnl"] > 0
              and (decomp["pct_of_gain_from_preemption"] is None
                   or decomp["pct_of_gain_from_preemption"] < 50.0))
    else:
        g9 = False  # vacuous per prereg -- G4 already fails when gain <= 0, so this can't ship anyway

    all_gates = {
        "G1_recent25_positive_PRIMARY": g1, "G2_day_majority": g2,
        "G3_drop_best_still_positive": g3, "G4_pnl_not_degraded_vs_both_baselines": g4,
        "G5_runner_cohort_ZERO_TOLERANCE": g5, "G6_rule6_floor_respected": g6,
        "G7_kill_switch_and_risk_cap_guard_present": g7, "G8_not_a_dead_knob_C14": g8,
        "G9_gain_is_not_mostly_preemption": g9,
    }
    ship = all(all_gates.values())
    verdict = "SHIP" if ship else "NULL"
    log(f"GATES: {all_gates}")
    log(f"VERDICT: {verdict}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)),
        "prereg_registered_at_et": prereg["registered_at_et"],
        "window": {"start": bfr.FULL_START.isoformat(), "end": bfr.FULL_END.isoformat()},
        "account": "core_bold (Gamma-Bold-2, PA33W2KUAT40)",
        "live_equity_used": bfr.BOLD_LIVE_EQUITY,
        "gate_state_held_fixed": {"block_elite_bull": True},
        "derived_union_figure_being_replayed": {
            "_doc": "The naive, un-sequenced exact-by-construction recombination from "
                    "min-contracts-bold-2026-08-02.json's exploratory_adaptive_not_shipped "
                    "block -- the ZERO-SEQUENCING-LOSS CEILING, reported here for "
                    "comparison, never gated on.",
            "n": DERIVED_UNION_N, "total_pnl": DERIVED_UNION_TOTAL_PNL,
            "recent_25_total_pnl": DERIVED_UNION_RECENT25_PNL,
            "reproduced_this_session_unsequenced": unsequenced_stats,
            "parity_with_shipped_figure_ok": parity_ok,
        },
        "control_raw_baseline": {
            "_doc": "The already-shipped 'current engine' figure (min-contracts-bold-2026-08-02.json .control), unchanged, not re-litigated.",
            "total_pnl": CONTROL_RAW_TOTAL_PNL,
        },
        "control_sequential": control_sequential_stats,
        "adaptive_sequential": adaptive_sequential_stats,
        "gap_explained": {
            "derived_unsequenced_total": unsequenced_stats["total_pnl"],
            "honest_sequential_total": adaptive_sequential_stats["total_pnl"],
            "gap_dollars": round(unsequenced_stats["total_pnl"] - adaptive_sequential_stats["total_pnl"], 2),
            "gap_pct_of_derived": (
                round(100.0 * (unsequenced_stats["total_pnl"] - adaptive_sequential_stats["total_pnl"])
                      / unsequenced_stats["total_pnl"], 1) if unsequenced_stats["total_pnl"] else None),
            "n_candidates_lost_to_sequencing": n_preempted_adaptive,
            "mechanism": "trades pre-empted because an earlier adaptive-only (fallback qty=3) "
                        "trade's exit_time_et had not yet passed when this signal arrived -- "
                        "the position slot was occupied.",
        },
        "day_majority": day_maj,
        "control_day_majority_informational_not_gated": control_day_maj,
        "participation": participation,
        "bold_own_runner_cohort": {
            "n": len(runner_rows), "control_pnl_sum": runner_control_sum,
            "expected_n": RUNNER_COHORT_N_EXPECTED, "expected_pnl": RUNNER_COHORT_PNL_EXPECTED,
            "crosscheck_vs_shipped_figure_ok": runner_crosscheck_ok,
            "adaptive_sequential_pnl_sum": runner_adaptive_sum,
            "n_missing_in_adaptive_sequential": len(runner_missing),
            "n_winner_to_loser_flips": n_flips,
            "pass": g5_pass,
        },
        "decomposition": decomp,
        "gates": all_gates,
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"total runtime {out['runtime_seconds']}s")
    return 0 if ship else 1


def write_markdown(out: dict) -> None:
    cs, as_ = out["control_sequential"], out["adaptive_sequential"]
    du = out["derived_union_figure_being_replayed"]
    ge = out["gap_explained"]
    dm = out["day_majority"]
    rc = out["bold_own_runner_cohort"]
    dc = out["decomposition"]
    L = [
        "# BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3 -- TRUE sequential replay, 2026-08-02",
        "",
        f"Generated {out['generated_at']}. Runner: "
        "`backtest/tools/bold_adaptive_sizing_2026_08_02.py`.",
        f"Prereg (frozen first): `{out['prereg']}` ({out['prereg_registered_at_et']}).",
        f"Account: {out['account']}. Equity: ${out['live_equity_used']:,.2f}. "
        f"Window: {out['window']['start']}..{out['window']['end']}. "
        f"Gate state held fixed: block_elite_bull=True (current live).",
        "",
        f"## VERDICT: {out['verdict']}",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for k, val in out["gates"].items():
        L.append(f"| {k} | {'PASS' if val else 'FAIL'} |")
    L += [
        "",
        "## Derived (naive union) vs honest replayed -- THE GAP",
        "",
        f"- Derived, exact-by-construction union (shipped in min-contracts-bold-2026-08-02.json, "
        f"NOT sequential): n={du['n']} total=${du['total_pnl']:+,.2f} recent25="
        f"${du['recent_25_total_pnl']:+,.2f}",
        f"- Reproduced fresh this session (parity check, one direct adaptive-mode pass, "
        f"pre-sequential): {du['reproduced_this_session_unsequenced']['n']} total="
        f"${du['reproduced_this_session_unsequenced']['total_pnl']:+,.2f} -- "
        f"PARITY_OK={du['parity_with_shipped_figure_ok']}",
        f"- **HONEST, sequentially-replayed (one position at a time)**: n={as_['n']} "
        f"total=${as_['total_pnl']:+,.2f}",
        f"- **GAP**: ${ge['gap_dollars']:+,.2f} ({ge['gap_pct_of_derived']}% of the derived "
        f"figure), {ge['n_candidates_lost_to_sequencing']} candidate trade(s) pre-empted. "
        f"Mechanism: {ge['mechanism']}",
        "",
        "## Control, also re-walked sequentially (apples-to-apples)",
        "",
        "| | CONTROL_SEQUENTIAL (floor=5 only) | ADAPTIVE_SEQUENTIAL (try5/fallback3) |",
        "|---|---|---|",
        f"| n | {cs['n']} | {as_['n']} |",
        f"| Total P&L | ${cs['total_pnl']:+,.2f} | ${as_['total_pnl']:+,.2f} |",
        f"| vs shipped CONTROL_RAW ${out['control_raw_baseline']['total_pnl']:+,.2f} | -- | "
        f"{'>=' if as_['total_pnl'] >= out['control_raw_baseline']['total_pnl'] else '<'} |",
        f"| Win rate | {cs['win_rate']} | {as_['win_rate']} |",
        f"| Avg $/trade | ${cs['avg_pnl_per_trade']:+.2f} | ${as_['avg_pnl_per_trade']:+.2f} |",
        f"| Drop-best remainder | ${cs['drop_best']['remainder']:+,.2f} "
        f"({'still +' if cs['drop_best']['still_positive'] else 'flips -'}) | "
        f"${as_['drop_best']['remainder']:+,.2f} "
        f"({'still +' if as_['drop_best']['still_positive'] else 'flips -'}) |",
        f"| Recent-{RECENT_N} total (PRIMARY gate) | ${cs['recent_25']['total_pnl']:+,.2f} | "
        f"${as_['recent_25']['total_pnl']:+,.2f} |",
        "",
        f"## Day-majority (G2, novel term, defined fresh in the prereg)",
        "",
        f"up_days={dm['up_days']} down_days={dm['down_days']} neutral_days={dm['neutral_days']} "
        f"of n_days={dm['n_days']} -- **PASS={dm['pass']}**",
        "",
        f"(informational, NOT gated -- context for whether this is adaptive-specific or a "
        f"pre-existing shape of the trade population) CONTROL_SEQUENTIAL day-majority: "
        f"up={out['control_day_majority_informational_not_gated']['up_days']} "
        f"down={out['control_day_majority_informational_not_gated']['down_days']} "
        f"pass={out['control_day_majority_informational_not_gated']['pass']} -- "
        f"{'same shape as adaptive (few big winners, many small losing days -- a baseline strategy feature, not something the adaptive rule introduced)' if out['control_day_majority_informational_not_gated']['pass'] == dm['pass'] else 'DIFFERS from adaptive -- the adaptive rule changes the day-majority shape, investigate further'}",
        "",
        "## Bold's OWN runner cohort (G5, zero-tolerance)",
        "",
        f"n={rc['n']} (expected {rc['expected_n']}, crosscheck_ok={rc['crosscheck_vs_shipped_figure_ok']}) "
        f"CONTROL total=${rc['control_pnl_sum']:+,.2f} (expected ${rc['expected_pnl']:+,.2f}) "
        f"ADAPTIVE_SEQUENTIAL total=${rc['adaptive_sequential_pnl_sum']:+,.2f} "
        f"missing={rc['n_missing_in_adaptive_sequential']} flips={rc['n_winner_to_loser_flips']} "
        f"-- **PASS={rc['pass']}**",
        "",
        "## Decomposition: added vs pre-empted (task step 3)",
        "",
        f"- ADDED cohort (only possible via the qty=3 fallback): n={dc['added_cohort']['n']} "
        f"total=${dc['added_cohort']['total_pnl']:+,.2f}",
        f"- PRE-EMPTED cohort (current engine's own sequential trades displaced by an "
        f"earlier fallback trade): n={dc['preempted_cohort']['n']} "
        f"total=${dc['preempted_cohort']['total_pnl']:+,.2f}",
        f"- gain_over_control_sequential=${dc['gain_over_control_sequential']:+,.2f}, "
        f"identity_holds={dc['identity_holds']}, "
        f"pct_of_gain_from_preemption={dc['pct_of_gain_from_preemption']}",
        "",
        "## Participation / fire counts (L243 discipline)",
        "",
        f"```\n{json.dumps(out['participation'], indent=2)}\n```",
        "",
        "---",
        "_Source: `backtest/tools/bold_adaptive_sizing_2026_08_02.py`. Raw JSON: "
        "`analysis/recommendations/bold-adaptive-sizing-2026-08-02.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
