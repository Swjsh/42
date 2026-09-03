"""Guards for BOLD-SELECTIVE-FALLBACK-2026-08-02 (iteration 3 of the bold-2 sizing lane).

Prereg: analysis/recommendations/prereg-bold-selective-fallback-2026-08-02.json
Scorecard: analysis/recommendations/bold-selective-fallback-2026-08-02.{json,md}

VERDICT OF THE STUDY: NULL on all 3 cells. Every cell still fails G5 (runner-cohort
zero-tolerance) -- the SAME 2 of Bold's own 32 runner-cohort trades ($14,539.40 -> $13,493.00,
missing 05-18 SPY P736 +$514.40 and 06-08 SPY P741 +$532.00) survive BOTH the tier bar (cell A:
tier in {SUPER, ELITE}) and the level-anchored filter (cell C: >=1 level-tied trigger) --
because those two specific pre-empting fallback trades are THEMSELVES high-quality,
level-anchored setups. This is the load-bearing finding of this iteration: pre-emption is a
TIMING/duration collision (which slot is occupied when), not a setup-quality problem, so
quality-based selectivity (A, C) cannot discriminate against the trades that cause it. Cell B
(time-of-day >= noon) is the only one of the three that is mechanistically aligned with the
actual failure mode -- it excludes the 05-18 trade entirely (it fired before noon) and
HALVES the cohort damage (missing=1, cohort $14,539.40 -> $14,007.40, a $532 loss instead of
$1,046.40) -- but the 06-08 blocking trade itself fires at/after noon and still gets through,
so even cell B does not reach ZERO and still fails G5's zero-tolerance bar. NOTHING SHIPS.

These guards pin: (1) this study's _sequential_admit is the SAME object as iteration 2's, not
a re-implementation (the task's explicit "reuse, don't rebuild" instruction, made
mechanically verifiable, not just claimed); (2) each of the 3 predicates is a genuine
two-way branch on representative fixtures; (3) preferred-tier (qty=5) rows are NEVER
filtered by any predicate, only fallback-tier (qty=3) rows are; (4) the G5 runner-cohort
check function correctly fails on a missing member and on a winner-to-loser flip, and
passes on a clean case, all via synthetic fixtures independent of the real historical
data; (5) the frozen constants (noon cutoff, 15-fire floor, level-tied-trigger vocabulary)
match the prereg exactly; (6) nothing was shipped to the live path by this NULL.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bold_selective_fallback_2026_08_02.py -v
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR, CRYPTO_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bold_fullhist_replay as bfr  # noqa: E402
import bold_adaptive_sizing_2026_08_02 as study2  # noqa: E402
import bold_selective_fallback_2026_08_02 as study3  # noqa: E402

AGGRESSIVE_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
HEARTBEAT_CORE = REPO / "setup" / "scripts" / "heartbeat_core.py"
PREREG = REPO / "analysis" / "recommendations" / "prereg-bold-selective-fallback-2026-08-02.json"
SCORECARD = REPO / "analysis" / "recommendations" / "bold-selective-fallback-2026-08-02.json"


def _agg_params() -> dict:
    return json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))


def _row(entry_time: str, qty: int, tier: str = "BASE", triggers: list[str] | None = None,
         pnl: float = 0.0, symbol: str = "X", exit_time: str | None = None) -> dict:
    return {
        "entry_time_et": entry_time, "exit_time_et": exit_time, "qty": qty, "tier": tier,
        "triggers": triggers or [], "dollar_pnl": pnl, "symbol": symbol,
        "date": entry_time[:10], "entry_premium": 1.0, "side": "C",
    }


# --------------------------------------------------------------------------------------
# 1. REUSE, NOT REBUILD: _sequential_admit must be the literal same object as iteration
#    2's, not a re-implementation that happens to behave similarly.
# --------------------------------------------------------------------------------------
class TestReusesIteration2MechanismNotRebuilt:
    def test_sequential_admit_is_the_same_object_as_iter2(self):
        assert study3.study2._sequential_admit is study2._sequential_admit

    def test_stats_day_majority_key_decompose_runner_cohort_all_reused_from_iter2(self):
        assert study3.study2._stats is study2._stats
        assert study3.study2._day_majority is study2._day_majority
        assert study3.study2._key is study2._key
        assert study3.study2.decompose is study2.decompose
        assert study3.study2._runner_cohort is study2._runner_cohort

    def test_replay_population_reused_unmodified_from_bold_fullhist_replay(self):
        assert study3.bfr.replay_population is bfr.replay_population
        assert study3.bfr.resolve_bold_qty_adaptive is bfr.resolve_bold_qty_adaptive

    def test_evaluate_cell_actually_calls_through_to_the_shared_sequential_admit(self, monkeypatch):
        """Stronger than the identity check above: proves evaluate_cell's RUNTIME behavior
        is driven by bold_adaptive_sizing_2026_08_02's own _sequential_admit, not a private
        copy that happens to satisfy the `is` check. Monkeypatches the shared function to a
        stub that always returns empty and confirms evaluate_cell's output changes
        accordingly -- if bold_selective_fallback_2026_08_02 ever grew its own private
        re-implementation instead of calling through, this test would stop being sensitive
        to the patch and silently keep passing with nonzero output, which is exactly the
        failure mode this test exists to catch."""
        control_rows = [_row("2026-08-02T09:35:00", 5, pnl=50.0, symbol="CTRL",
                              exit_time="2026-08-02T09:50:00")]
        runner_rows: list[dict] = []
        adaptive_rows = [
            _row("2026-08-02T09:35:00", 5, pnl=50.0, symbol="CTRL", exit_time="2026-08-02T09:50:00"),
            _row("2026-08-02T10:00:00", 3, tier="SUPER", pnl=10.0, symbol="FB",
                 exit_time="2026-08-02T10:15:00"),
        ]
        control_sequential = study2._sequential_admit(control_rows)
        control_keys = {study2._key(r) for r in control_rows}

        monkeypatch.setattr(study2, "_sequential_admit", lambda rows: [])
        out = study3.evaluate_cell(
            "A_tier_bar", study3.rule_a_tier_bar, adaptive_rows, control_sequential,
            control_keys, control_sequential_total=50.0, runner_rows=runner_rows)
        assert out["selective_sequential_stats"]["n"] == 0, (
            "evaluate_cell did not react to the monkeypatched shared _sequential_admit -- "
            "it is not actually calling through to the reused function")


# --------------------------------------------------------------------------------------
# 2. EACH PREDICATE IS A GENUINE TWO-WAY BRANCH (G8 vary-and-assert), on representative
#    fixtures -- not silently always-True or always-False.
# --------------------------------------------------------------------------------------
class TestPredicatesAreGenuineBranches:
    def test_rule_a_tier_bar_passes_super_and_elite_fails_level_trendline_base(self):
        assert study3.rule_a_tier_bar(_row("2026-08-02T10:00:00", 3, tier="SUPER")) is True
        assert study3.rule_a_tier_bar(_row("2026-08-02T10:00:00", 3, tier="ELITE")) is True
        assert study3.rule_a_tier_bar(_row("2026-08-02T10:00:00", 3, tier="LEVEL")) is False
        assert study3.rule_a_tier_bar(_row("2026-08-02T10:00:00", 3, tier="TRENDLINE")) is False
        assert study3.rule_a_tier_bar(_row("2026-08-02T10:00:00", 3, tier="BASE")) is False

    def test_rule_b_time_cutoff_passes_at_and_after_noon_fails_before(self):
        assert study3.rule_b_time_cutoff(_row("2026-08-02T11:59:59", 3)) is False
        assert study3.rule_b_time_cutoff(_row("2026-08-02T12:00:00", 3)) is True
        assert study3.rule_b_time_cutoff(_row("2026-08-02T14:30:00", 3)) is True
        assert study3.rule_b_time_cutoff(_row("2026-08-02T09:35:00", 3)) is False

    def test_rule_c_level_anchored_passes_with_level_trigger_fails_trendline_only(self):
        assert study3.rule_c_level_anchored(
            _row("2026-08-02T10:00:00", 3, triggers=["level_rejection"])) is True
        assert study3.rule_c_level_anchored(
            _row("2026-08-02T10:00:00", 3, triggers=["confluence"])) is True
        assert study3.rule_c_level_anchored(
            _row("2026-08-02T10:00:00", 3, triggers=["sequence_reclaim"])) is True
        assert study3.rule_c_level_anchored(
            _row("2026-08-02T10:00:00", 3, triggers=["trendline_rejection"])) is False
        assert study3.rule_c_level_anchored(_row("2026-08-02T10:00:00", 3, triggers=[])) is False

    def test_level_tied_triggers_vocabulary_matches_pnl_attribution_source_exactly(self):
        assert study3.LEVEL_TIED_TRIGGERS == frozenset(
            {"confluence", "level_reclaim", "level_rejection", "sequence_reclaim", "sequence_rejection"})


# --------------------------------------------------------------------------------------
# 3. SELECTION MECHANICS: preferred-tier (qty=5) rows are NEVER filtered by any
#    predicate; fallback-tier (qty=3) rows ARE filtered.
# --------------------------------------------------------------------------------------
class TestSelectionMechanicsPreferredTierNeverFiltered:
    def test_qty5_rows_always_kept_even_when_predicate_would_reject_them(self):
        rows = [_row("2026-08-02T09:35:00", 5, tier="BASE", triggers=[])]
        always_false = lambda r: False  # noqa: E731
        out = study3.build_selective_candidates(rows, always_false)
        assert len(out) == 1, "a qty=5 preferred-tier row must survive regardless of predicate"

    def test_qty3_rows_dropped_when_predicate_rejects_kept_when_predicate_accepts(self):
        rows = [
            _row("2026-08-02T09:35:00", 3, tier="SUPER", symbol="PASS"),
            _row("2026-08-02T09:40:00", 3, tier="BASE", symbol="FAIL"),
        ]
        out = study3.build_selective_candidates(rows, study3.rule_a_tier_bar)
        symbols = {r["symbol"] for r in out}
        assert symbols == {"PASS"}

    @pytest.mark.parametrize("cell_name,cfg", list(study3.CELLS.items()))
    def test_every_cell_predicate_is_callable_and_returns_bool(self, cell_name, cfg):
        r3 = _row("2026-08-02T13:00:00", 3, tier="ELITE", triggers=["confluence"])
        assert isinstance(cfg["predicate"](r3), bool)


# --------------------------------------------------------------------------------------
# 4. G5 RUNNER-COHORT CHECK, proven on synthetic fixtures independent of the real walk.
# --------------------------------------------------------------------------------------
class TestRunnerCohortG5CheckMechanism:
    def test_clean_case_all_present_no_flips_passes(self):
        runner_rows = [_row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A")]
        selective = [_row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A")]
        out = study3.check_runner_cohort_g5(runner_rows, selective)
        assert out["pass"] is True and out["n_missing"] == 0 and out["n_flips"] == 0

    def test_missing_cohort_member_fails(self):
        runner_rows = [_row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A")]
        selective: list[dict] = []  # A got pre-empted, absent entirely
        out = study3.check_runner_cohort_g5(runner_rows, selective)
        assert out["pass"] is False and out["n_missing"] == 1

    def test_winner_to_loser_flip_fails_even_if_present(self):
        runner_rows = [_row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A")]
        # same key present but somehow now a loser (should not happen in practice since
        # the row is byte-identical, but the check must still catch it defensively)
        selective = [_row("2026-08-02T09:35:00", 5, pnl=-5.0, symbol="A")]
        out = study3.check_runner_cohort_g5(runner_rows, selective)
        assert out["pass"] is False and out["n_flips"] == 1

    def test_aggregate_below_control_sum_fails_even_with_zero_missing_and_zero_flips(self):
        runner_rows = [
            _row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A"),
            _row("2026-08-02T11:00:00", 5, pnl=100.0, symbol="B"),
        ]
        # both present, both still winners, but B's pnl silently dropped -- must still fail
        selective = [
            _row("2026-08-02T09:35:00", 5, pnl=100.0, symbol="A"),
            _row("2026-08-02T11:00:00", 5, pnl=10.0, symbol="B"),
        ]
        out = study3.check_runner_cohort_g5(runner_rows, selective)
        assert out["pass"] is False
        assert out["n_missing"] == 0 and out["n_flips"] == 0  # neither trip, only the aggregate does
        assert out["selective_sum"] < out["control_sum"]


# --------------------------------------------------------------------------------------
# 5. FROZEN CONSTANTS match the prereg exactly (provenance, not silently drifted).
# --------------------------------------------------------------------------------------
class TestFrozenConstantsMatchPrereg:
    def test_noon_cutoff(self):
        assert study3.MIDNIGHT_CUTOFF_ET == dt.time(12, 0, 0)

    def test_min_fallback_fires_floor_is_15(self):
        assert study3.MIN_FALLBACK_FIRES_FLOOR == 15

    def test_three_cells_exactly_no_more_no_fewer(self):
        assert list(study3.CELLS.keys()) == ["A_tier_bar", "B_time_of_day_cutoff", "C_level_anchored"]

    def test_prereg_frozen_before_scorecard(self):
        assert PREREG.exists(), "prereg must exist"
        prereg = json.loads(PREREG.read_text(encoding="utf-8"))
        # 2026-09-03: prereg_hygiene status write-back moves a prereg to a terminal
        # RUN_COMPLETE* status once its result file exists (commit a07ae7e3). The
        # frozen-before-scorecard property is the pinned rule set below, not the label.
        assert prereg["status"] == "PRE-REGISTERED" or prereg["status"].startswith("RUN_COMPLETE"), prereg["status"]
        assert set(prereg["candidate_rules"].keys()) == {"_doc", "A_tier_bar", "B_time_of_day_cutoff", "C_level_anchored"}
        assert "G10_material_fallback_fires_NEW" in prereg["pre_registered_ship_conditions"]


# --------------------------------------------------------------------------------------
# 6. SCORECARD / NULL-RESULT PINS: the produced JSON matches what this study actually
#    found, and nothing was shipped to the live path.
# --------------------------------------------------------------------------------------
class TestScorecardAndNullResultPins:
    def test_scorecard_exists_and_verdict_is_null(self):
        assert SCORECARD.exists(), "run backtest/tools/bold_selective_fallback_2026_08_02.py first"
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        assert out["verdict"] == "NULL"
        assert out["ship_cells"] == []

    def test_all_three_cells_fail_g5_zero_tolerance(self):
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        for name, c in out["cells"].items():
            assert c["gates"]["G5_runner_cohort_ZERO_TOLERANCE"] is False, (
                f"cell {name} now passes G5 -- the underlying data changed, this whole "
                "scorecard needs a fresh look, not a silent pin update")

    def test_all_three_cells_clear_g10_material_fires(self):
        """The floor was designed to be clearable by a real mechanism -- confirm it was
        NOT the reason any cell failed (the disqualifying gate is G5, not G10)."""
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        for name, c in out["cells"].items():
            assert c["gates"]["G10_material_fallback_fires_NEW"] is True, (
                f"cell {name} failed the material-fires floor -- re-examine before "
                "concluding G5 is the binding constraint")

    def test_parity_guards_all_held(self):
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        pg = out["parity_guards"]
        assert pg["unsequenced_union_vs_iter2"]["ok"] is True
        assert pg["control_sequential_vs_iter2"]["ok"] is True
        assert pg["runner_cohort_crosscheck"]["ok"] is True

    def test_cell_a_and_cell_c_lose_the_identical_two_runner_trades(self):
        """Load-bearing finding of this iteration: the tier bar and the level-anchored
        filter fail to protect the SAME 2 runner-cohort trades, because the trades that
        cause the pre-emption are themselves high-quality/level-anchored -- pre-emption is
        a timing collision, not a quality gap. If this ever diverges, the finding's
        headline claim needs re-examination, not a silent pin update."""
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        a = out["cells"]["A_tier_bar"]["runner_cohort_g5"]
        c = out["cells"]["C_level_anchored"]["runner_cohort_g5"]
        assert a["n_missing"] == c["n_missing"] == 2
        assert a["selective_sum"] == c["selective_sum"]

    def test_cell_b_halves_but_does_not_zero_the_cohort_damage(self):
        out = json.loads(SCORECARD.read_text(encoding="utf-8"))
        b = out["cells"]["B_time_of_day_cutoff"]["runner_cohort_g5"]
        assert b["n_missing"] == 1, "time-cutoff cell expected to save exactly 1 of the 2 lost runner trades"
        assert b["n_missing"] > 0, "even the best-performing cell must not reach zero here (that would flip G5 to PASS and change the verdict)"

    def test_aggressive_params_min_contracts_still_5_unchanged_by_this_null(self):
        params = _agg_params()
        assert params.get("min_contracts") == 5, (
            "aggressive/params.json min_contracts changed since the BOLD-SELECTIVE-"
            "FALLBACK-2026-08-02 NULL -- if this is an intentional, freshly-evidenced "
            "re-ship, update this pin in the same commit; if accidental drift, revert to 5."
        )

    def test_heartbeat_core_has_no_selective_fallback_formula_yet(self):
        src = HEARTBEAT_CORE.read_text(encoding="utf-8")
        assert "min_contracts_preferred" not in src, (
            "heartbeat_core.py appears to carry an adaptive/selective two-tier sizing "
            "formula, but BOLD-SELECTIVE-FALLBACK-2026-08-02 NULLED (every cell failed "
            "G5 runner-cohort zero-tolerance) -- if shipped on fresh evidence since, "
            "update/remove this pin in the same commit; if accidental, revert."
        )
