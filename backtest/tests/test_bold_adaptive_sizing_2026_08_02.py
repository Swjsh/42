"""Guards for the BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3 study (prereg:
analysis/recommendations/prereg-bold-adaptive-sizing-2026-08-02.json; scorecard:
analysis/recommendations/bold-adaptive-sizing-2026-08-02.{json,md}).

VERDICT OF THE STUDY: NULL. The exploratory recombination from MIN-CONTRACTS-BOLD-2026-08-02
($+10,528.60, n=286) was computed by UNION-ing two separate backtest runs and is NOT a valid
replay of what a live, one-position-at-a-time engine would actually do. A TRUE sequential
walk (this study's own contribution: `_sequential_admit` in bold_adaptive_sizing_2026_08_02.py,
adapted from elite_bull_postfix_requal_2026_07_31.py's sequential_hold()) reproduces the
unsequenced union almost exactly in AGGREGATE dollar terms ($+10,473.20 sequential vs
$+10,528.60 derived, a mere $55.40/0.5% gap -- pre-emption is NOT the dominant story here,
unlike the filter5_ribbon_fate_2026_07_31.py precedent that was 86% pre-emption) -- BUT that
small aggregate gap conceals a REAL, disqualifying regression in Bold's own protected runner
cohort: 2 of the 32 runner-cohort trades ($14,539.40 CONTROL) are individually PRE-EMPTED by
an earlier qty=3 fallback trade occupying the position slot, dropping the cohort to $13,493.00
-- a zero-tolerance FAIL per the frozen prereg's G5, regardless of the healthy-looking
aggregate. Separately and independently, G2 (day-majority, a novel term defined fresh in the
prereg) also fails: 119 losing days vs 82 winning days in the adaptive-sequential population --
disclosed as informational-only context, that same few-big-winners/many-small-losers shape is
ALSO present in CONTROL_SEQUENTIAL (checked, see the scorecard's control_day_majority block),
so this is a pre-existing feature of the ribbon_ride population, not something the adaptive
rule introduces -- but it is a REQUIRED gate under the frozen prereg regardless, and it fails.

These guards pin: (1) the adaptive qty resolver is a genuine, non-dead, three-way branch
(qty=5 / qty=3 / deny) -- C14 vary-and-assert; (2) the qty=3 AND qty=5 leg splits are sane
under THIS study's own code path (re-verified fresh, not cited from the parent NULL study);
(3) kill-switch and Rule-6/risk-cap independence at both tiers; (4) the new qty_mode
parameter defaults to 'fixed', byte-identical to every pre-existing bold_fullhist_replay.py
call site; (5) the sequential-admission (one-position-at-a-time) mechanism itself, proven on
synthetic fixture rows independent of any historical outcome; (6) that
automation/state/aggressive/params.json and setup/scripts/heartbeat_core.py were NOT
changed by this NULL result (nothing shipped to the live path).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bold_adaptive_sizing_2026_08_02.py -v
"""
from __future__ import annotations

import datetime as dt
import inspect
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
import bold_adaptive_sizing_2026_08_02 as study  # noqa: E402
from lib import risk_gate as rg  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from exit_manager import ExitState  # noqa: E402

AGGRESSIVE_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
HEARTBEAT_CORE = REPO / "setup" / "scripts" / "heartbeat_core.py"
RULE_6_ABSOLUTE_MIN_CONTRACTS = 3  # CLAUDE.md Rule 6: "Min 3 contracts (2 TP + 1 runner)"


def _agg_params() -> dict:
    return json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# 1. LEG-SPLIT SANITY, re-verified FRESH under this study's own code path (task step 4:
#    "re-confirm under YOUR code path", not just cite the parent study's already-shipped
#    result).
# --------------------------------------------------------------------------------------
class TestLegSplitFreshUnderThisStudy:
    def _shape(self) -> dict:
        return fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    def test_qty3_fallback_splits_2_1_neither_leg_zero(self):
        st = ExitState.from_entry(
            symbol="SPY260802C00745000", side="C", entry_premium=1.60, qty=3,
            exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
            structure_stop_enabled=True,
        )
        assert st.tp1_qty == 2
        assert st.runner_qty == 1
        assert st.tp1_qty > 0 and st.runner_qty > 0

    def test_qty5_preferred_splits_3_2_neither_leg_zero(self):
        st = ExitState.from_entry(
            symbol="SPY260802C00745000", side="C", entry_premium=1.10, qty=5,
            exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
            structure_stop_enabled=True,
        )
        assert st.tp1_qty == 3
        assert st.runner_qty == 2
        assert st.tp1_qty > 0 and st.runner_qty > 0

    def test_neither_tier_of_the_adaptive_rule_ever_produces_a_zero_leg(self):
        for qty in (bfr.BOLD_MIN_CONTRACTS_FALLBACK, bfr.BOLD_MIN_CONTRACTS_PREFERRED):
            st = ExitState.from_entry(
                symbol="SPY260802C00745000", side="C", entry_premium=1.50, qty=qty,
                exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
                structure_stop_enabled=True,
            )
            assert st.tp1_qty > 0, f"qty={qty} produced a ZERO-size TP1 leg"
            assert st.runner_qty > 0, f"qty={qty} produced a ZERO-size runner leg"
            assert st.tp1_qty + st.runner_qty == qty


# --------------------------------------------------------------------------------------
# 2. ADAPTIVE RESOLVER IS A GENUINE THREE-WAY BRANCH, NOT A DEAD KNOB (C14 RED-proof: it
#    must pick 5 below the floor-5 ceiling, 3 in the unlocked band, None above the
#    floor-3 ceiling -- three outcomes, not two).
# --------------------------------------------------------------------------------------
class TestAdaptiveResolverNotDeadKnob:
    def test_below_floor5_ceiling_picks_preferred_qty5(self):
        assert bfr.resolve_bold_qty_adaptive(1.10) == 5

    @pytest.mark.parametrize("premium", [1.30, 1.50, 1.75, 1.99])
    def test_in_the_unlocked_band_falls_back_to_qty3(self, premium):
        assert bfr.resolve_bold_qty_adaptive(premium) == 3

    def test_above_floor3_ceiling_denies_both_tiers(self):
        assert bfr.resolve_bold_qty_adaptive(2.50) is None

    def test_matches_resolve_bold_qty_at_each_tier_directly(self):
        """The adaptive resolver must not silently diverge from the primitives it composes."""
        for premium in (0.50, 1.10, 1.30, 1.75, 1.99, 2.50, 3.00):
            expect5 = bfr.resolve_bold_qty(premium, min_contracts=5)
            expect3 = bfr.resolve_bold_qty(premium, min_contracts=3)
            got = bfr.resolve_bold_qty_adaptive(premium)
            if expect5 is not None:
                assert got == 5, f"premium={premium}: floor5 affordable, adaptive should prefer 5"
            elif expect3 is not None:
                assert got == 3, f"premium={premium}: floor5 denied but floor3 affordable, adaptive should fall back to 3"
            else:
                assert got is None, f"premium={premium}: both tiers should deny"

    def test_check_order_agrees_deny5_allow3_in_the_unlocked_band(self):
        """Direct risk_gate.check_order calls (not resolve_bold_qty*), mirroring the parent
        study's own RED-proof pattern, confirming the adaptive rule's fallback branch is
        exercising a REAL risk_gate-visible affordability gap, not a private re-derivation
        that happens to agree with itself."""
        p5 = dict(_agg_params()); p5["min_contracts"] = 5
        p3 = dict(_agg_params()); p3["min_contracts"] = 3
        for premium in (1.30, 1.50, 1.75, 1.99):
            deny5 = rg.check_order(
                "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=5,
                premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
                current_position_status="flat", day_trades_used_5d=0,
                kill_switch_tripped=False, prior_stops_today=[], params=p5,
            )
            allow3 = rg.check_order(
                "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=3,
                premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
                current_position_status="flat", day_trades_used_5d=0,
                kill_switch_tripped=False, prior_stops_today=[], params=p3,
            )
            assert deny5.allowed is False and deny5.code == rg.CODE_RISK_CAP
            assert allow3.allowed is True


# --------------------------------------------------------------------------------------
# 3. RULE 6 FLOOR IS NON-NEGOTIABLE: resolve_bold_qty_adaptive must refuse to be
#    constructed with a floor below 3, and the module constants must reflect (5, 3).
# --------------------------------------------------------------------------------------
class TestRule6FloorNeverBelow3:
    def test_module_constants_are_5_and_3(self):
        assert bfr.BOLD_MIN_CONTRACTS_PREFERRED == 5
        assert bfr.BOLD_MIN_CONTRACTS_FALLBACK == 3
        assert bfr.BOLD_MIN_CONTRACTS_FALLBACK >= RULE_6_ABSOLUTE_MIN_CONTRACTS

    def test_resolver_raises_if_floor_argument_pushed_below_3(self):
        with pytest.raises(ValueError):
            bfr.resolve_bold_qty_adaptive(1.50, min_contracts_floor=2)

    def test_resolver_raises_at_floor_1_too(self):
        with pytest.raises(ValueError):
            bfr.resolve_bold_qty_adaptive(1.50, min_contracts_floor=1)


# --------------------------------------------------------------------------------------
# 4. KILL-SWITCH AND RISK-CAP STILL BIND AT BOTH TIERS (prereg G7).
# --------------------------------------------------------------------------------------
class TestKillSwitchAndRiskCapIndependence:
    def test_kill_switch_denies_regardless_of_which_tier_would_otherwise_resolve(self):
        for mc, qty in ((5, 5), (3, 3)):
            p = dict(_agg_params()); p["min_contracts"] = mc
            d = rg.check_order(
                "bold-2", equity=500.0, start_of_day_equity=1197.52, proposed_qty=qty,
                premium=1.00, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
                current_position_status="flat", day_trades_used_5d=0,
                kill_switch_tripped=False, prior_stops_today=[], params=p,
            )
            # equity $500 <= kill floor (1197.52 * (1-0.50) = $598.76) -> KILL_SWITCH.
            assert d.allowed is False
            assert d.code == rg.CODE_KILL_SWITCH

    def test_risk_cap_still_binds_at_the_fallback_tier_for_an_oversized_proposal(self):
        p = dict(_agg_params()); p["min_contracts"] = 3
        d = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=20,
            premium=1.50, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=p,
        )
        assert d.allowed is False
        assert d.code == rg.CODE_RISK_CAP

    def test_risk_cap_re_derives_notional_against_the_ACTUAL_resolved_qty_not_a_stale_one(self):
        """A premium in the unlocked band resolves qty=3 adaptively; check_order at qty=5
        for the SAME premium must still deny -- proves nothing smuggles a stale/wrong qty
        past RISK_CAP."""
        premium = 1.60
        adaptive_qty = bfr.resolve_bold_qty_adaptive(premium)
        assert adaptive_qty == 3
        p5 = dict(_agg_params()); p5["min_contracts"] = 5
        d5 = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=5,
            premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=p5,
        )
        assert d5.allowed is False and d5.code == rg.CODE_RISK_CAP
        p3 = dict(_agg_params()); p3["min_contracts"] = 3
        d3 = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=adaptive_qty,
            premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=p3,
        )
        assert d3.allowed is True


# --------------------------------------------------------------------------------------
# 5. TOOL-EXTENSION PARITY: replay_population's new qty_mode/min_contracts_preferred/
#    min_contracts_floor parameters are byte-identical to every pre-existing call site
#    (including the parent MIN-CONTRACTS-BOLD-2026-08-02 study's own two calls) when
#    omitted.
# --------------------------------------------------------------------------------------
class TestToolExtensionParity:
    def test_qty_mode_defaults_to_fixed(self):
        sig = inspect.signature(bfr.replay_population)
        assert sig.parameters["qty_mode"].default == "fixed"

    def test_min_contracts_default_unchanged_by_this_change(self):
        sig = inspect.signature(bfr.replay_population)
        assert sig.parameters["min_contracts"].default == bfr.BOLD_MIN_CONTRACTS == 5

    def test_new_preferred_and_floor_defaults_match_module_constants(self):
        sig = inspect.signature(bfr.replay_population)
        assert sig.parameters["min_contracts_preferred"].default == bfr.BOLD_MIN_CONTRACTS_PREFERRED
        assert sig.parameters["min_contracts_floor"].default == bfr.BOLD_MIN_CONTRACTS_FALLBACK

    def test_replay_population_rejects_unknown_qty_mode(self):
        with pytest.raises(ValueError):
            bfr.replay_population(None, None, None, block_elite_bull=True, qty_mode="bogus")

    def test_resolve_bold_qty_adaptive_default_equity_and_cap_match_bold_constants(self):
        sig = inspect.signature(bfr.resolve_bold_qty_adaptive)
        assert sig.parameters["equity"].default == bfr.BOLD_LIVE_EQUITY
        assert sig.parameters["per_trade_risk_cap_pct"].default == bfr.BOLD_PER_TRADE_RISK_CAP_PCT


# --------------------------------------------------------------------------------------
# 6. SEQUENTIAL-ADMISSION MECHANISM, proven on SYNTHETIC fixture rows -- independent of
#    any particular historical outcome (task requirement: the mechanism itself must be
#    pinned, not just observed once in the real data walk).
# --------------------------------------------------------------------------------------
class TestSequentialAdmitMechanism:
    def _row(self, entry: str, exit_: str | None, pnl: float, symbol: str = "X", qty: int = 5) -> dict:
        return {"entry_time_et": entry, "exit_time_et": exit_, "dollar_pnl": pnl,
                "symbol": symbol, "date": entry[:10], "qty": qty, "entry_premium": 1.0}

    def test_non_overlapping_trades_all_survive(self):
        rows = [
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 100.0),
            self._row("2026-08-02T10:00:00", "2026-08-02T10:15:00", -50.0),
        ]
        kept = study._sequential_admit(rows)
        assert len(kept) == 2

    def test_a_later_entry_inside_an_earlier_open_position_is_dropped(self):
        """THE core mechanism this whole study exists to verify: a signal that arrives
        while an earlier admitted trade's position is still open is pre-empted, dropped
        entirely -- never independently counted, regardless of how profitable it would
        have been in isolation."""
        rows = [
            self._row("2026-08-02T09:35:00", "2026-08-02T10:30:00", -20.0, symbol="A"),
            self._row("2026-08-02T09:40:00", "2026-08-02T09:55:00", 999.0, symbol="B"),  # inside A's open window
        ]
        kept = study._sequential_admit(rows)
        assert len(kept) == 1
        assert kept[0]["symbol"] == "A", "the FIRST (earlier-entering) trade wins the slot, not the more profitable one"

    def test_entry_exactly_at_the_prior_exit_instant_is_pre_empted_not_admitted(self):
        """Boundary condition: entry <= previous exit (not strictly <) counts as still-open --
        matches elite_bull_postfix_requal_2026_07_31.py's sequential_hold() convention
        exactly ('entry ts is <= the previous kept replay's exit time')."""
        rows = [
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 10.0, symbol="A"),
            self._row("2026-08-02T09:50:00", "2026-08-02T10:00:00", 10.0, symbol="B"),
        ]
        kept = study._sequential_admit(rows)
        assert len(kept) == 1
        assert kept[0]["symbol"] == "A"

    def test_entry_one_second_after_prior_exit_is_admitted(self):
        rows = [
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 10.0, symbol="A"),
            self._row("2026-08-02T09:50:01", "2026-08-02T10:00:00", 10.0, symbol="B"),
        ]
        kept = study._sequential_admit(rows)
        assert len(kept) == 2

    def test_unresolved_trade_blocks_the_rest_of_its_own_day_only(self):
        rows = [
            self._row("2026-08-02T09:35:00", None, 0.0, symbol="A"),  # never resolved
            self._row("2026-08-02T14:00:00", "2026-08-02T14:10:00", 50.0, symbol="B"),  # same day -- blocked
            self._row("2026-08-03T09:35:00", "2026-08-03T09:50:00", 25.0, symbol="C"),  # next day -- free
        ]
        kept = study._sequential_admit(rows)
        symbols = {r["symbol"] for r in kept}
        assert symbols == {"A", "C"}, "unresolved trade occupies its own day, never bleeds into the next"

    def test_ordering_is_by_entry_time_not_input_order(self):
        rows = [
            self._row("2026-08-02T10:00:00", "2026-08-02T10:15:00", 1.0, symbol="LATER"),
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 2.0, symbol="EARLIER"),
        ]
        kept = study._sequential_admit(rows)
        assert [r["symbol"] for r in kept] == ["EARLIER", "LATER"]


# --------------------------------------------------------------------------------------
# 7. DECOMPOSITION ACCOUNTING IDENTITY (task step 3): gain_over_control ==
#    added_total - preempted_total, proven on a synthetic fixture where the answer is
#    known by construction.
# --------------------------------------------------------------------------------------
class TestDecomposeAccountingIdentity:
    def _row(self, entry: str, exit_: str, pnl: float, symbol: str, qty: int = 5) -> dict:
        return {"entry_time_et": entry, "exit_time_et": exit_, "dollar_pnl": pnl,
                "symbol": symbol, "date": entry[:10], "qty": qty, "entry_premium": 1.0,
                "side": "C"}

    def test_identity_holds_on_a_known_synthetic_case(self):
        # CONTROL takes A (qty5) and C (qty5), sequentially (no overlap).
        control_sequential = [
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 100.0, "A"),
            self._row("2026-08-02T11:00:00", "2026-08-02T11:15:00", 50.0, "C"),
        ]
        control_candidate_keys = {("A", "2026-08-02T09:35:00"), ("C", "2026-08-02T11:00:00")}
        # ADAPTIVE: A survives unchanged (qty5, same entry), a NEW fallback trade B (qty3)
        # is inserted right after A and BEFORE C, occupying the slot so C is pre-empted.
        adaptive_sequential = [
            self._row("2026-08-02T09:35:00", "2026-08-02T09:50:00", 100.0, "A"),
            self._row("2026-08-02T10:55:00", "2026-08-02T11:20:00", 30.0, "B", qty=3),  # overlaps C's entry
        ]
        out = study.decompose(control_sequential, adaptive_sequential, control_candidate_keys)
        assert out["added_cohort"]["n"] == 1 and out["added_cohort"]["total_pnl"] == 30.0
        assert out["preempted_cohort"]["n"] == 1 and out["preempted_cohort"]["total_pnl"] == 50.0
        assert out["gain_over_control_sequential"] == pytest.approx(30.0 - 50.0)
        assert out["identity_holds"] is True


# --------------------------------------------------------------------------------------
# 8. NULL-RESULT PIN: nothing shipped. aggressive/params.json unchanged, heartbeat_core.py
#    carries no two-tier adaptive-sizing formula. A future session re-testing this lever
#    should read the scorecard first, not silently assume the finding.
# --------------------------------------------------------------------------------------
def test_aggressive_params_min_contracts_still_5_unchanged_by_this_null():
    params = _agg_params()
    assert params.get("min_contracts") == 5, (
        "aggressive/params.json min_contracts changed since the BOLD-ADAPTIVE-SIZING-"
        "TRY5-FALLBACK3 NULL verdict (analysis/recommendations/bold-adaptive-sizing-"
        "2026-08-02.md) -- if this is an intentional, freshly-evidenced re-ship, update "
        "this pin in the same commit; if it's accidental drift, revert to 5."
    )


def test_heartbeat_core_has_no_adaptive_two_tier_formula_yet():
    src = HEARTBEAT_CORE.read_text(encoding="utf-8")
    assert "min_contracts_preferred" not in src, (
        "heartbeat_core.py appears to carry an adaptive two-tier sizing formula, but "
        "BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3 NULLED (G2 day-majority + G5 runner-cohort "
        "zero-tolerance both failed) -- if this was shipped on fresh evidence since, "
        "update/remove this pin in the same commit; if accidental, revert."
    )


def test_scorecard_verdict_is_null():
    scorecard = REPO / "analysis" / "recommendations" / "bold-adaptive-sizing-2026-08-02.json"
    assert scorecard.exists(), "run backtest/tools/bold_adaptive_sizing_2026_08_02.py first"
    out = json.loads(scorecard.read_text(encoding="utf-8"))
    assert out["verdict"] == "NULL"
    assert out["gates"]["G5_runner_cohort_ZERO_TOLERANCE"] is False, (
        "the runner-cohort zero-tolerance gate is expected to be the (or a) disqualifying "
        "reason -- if it now passes, the underlying data changed and this whole scorecard "
        "needs a fresh look, not a silent pin update")
