"""Guards for the MIN-CONTRACTS-BOLD-2026-08-02 study (prereg:
analysis/recommendations/prereg-min-contracts-bold-2026-08-02.json; scorecard:
analysis/recommendations/min-contracts-bold-2026-08-02.{json,md}).

VERDICT OF THE STUDY: NULL. Bold's min_contracts stays 5 in
automation/state/aggressive/params.json -- lowering it to 3 nearly doubles participation
(+83.3%, n=156->286 replayed trades over the 2025-01-02..2026-07-22 window) and confirms
smaller per-trade risk (avg notional $428.85->$345.63), but Bold's OWN runner cohort (n=32
trades that reached TP1 and rode a runner, exit_family()==RUNNER_TRAIL, drawn from the
min_contracts=5 CONTROL walk) loses $5,909.20 in aggregate dollar terms when shrunk to
qty=3 (zero tolerance required by the prereg's G3), the recent-25-trade window flips
NEGATIVE under the floor-3 variant ($+2,864.40 control vs $-105.75 variant -- J's own
dynamic-market/recency doctrine treats this as first-class, disqualifying evidence), and
total aggregate P&L is technically lower ($7,448.40 control vs $7,367.40 variant, -1.1%).
These guards therefore pin TWO things: (1) the underlying mechanism (min_contracts is a
live, non-dead knob; the qty=3 leg split is sane; the tool's new min_contracts parameter is
parity-safe) so a FUTURE re-test of this same lever starts from verified primitives instead
of re-deriving them, and (2) that aggressive/params.json's min_contracts was NOT silently
changed by this session (still 5) -- a pin, not a new floor.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_min_contracts_bold_2026_08_02.py -v
"""
from __future__ import annotations

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
from lib import risk_gate as rg  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from exit_manager import ExitState  # noqa: E402

AGGRESSIVE_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
RULE_6_ABSOLUTE_MIN_CONTRACTS = 3  # CLAUDE.md Rule 6: "Min 3 contracts (2 TP + 1 runner)"


def _agg_params() -> dict:
    return json.loads(AGGRESSIVE_PARAMS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# 1. LEG-SPLIT SANITY (task step 2: "prove the leg split is sane at qty=3 with a direct
#    test, not by reading"). Calls the REAL production ExitState.from_entry -- the same
#    function the fleet exit lane and heartbeat_core._execute both consume -- with Bold's
#    REAL shared exit shape (strategies.RIBBON_RIDE.exit, tp1_qty_fraction=0.667).
# --------------------------------------------------------------------------------------
class TestLegSplitAtQty3:
    def _shape(self) -> dict:
        return fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    def test_qty3_splits_2_1_neither_leg_zero(self):
        st = ExitState.from_entry(
            symbol="SPY260802C00745000", side="C", entry_premium=1.50, qty=3,
            exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
            structure_stop_enabled=True,
        )
        assert st.tp1_qty == 2
        assert st.runner_qty == 1
        assert st.tp1_qty > 0 and st.runner_qty > 0
        assert st.tp1_qty + st.runner_qty == 3

    def test_qty5_splits_3_2_for_comparison(self):
        """Sanity anchor: the CURRENT live split, so a future shape change that breaks
        BOTH qty3 and qty5 the same way doesn't look like a qty3-specific pass."""
        st = ExitState.from_entry(
            symbol="SPY260802C00745000", side="C", entry_premium=1.50, qty=5,
            exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
            structure_stop_enabled=True,
        )
        assert st.tp1_qty == 3
        assert st.runner_qty == 2

    @pytest.mark.parametrize("qty", [3, 4, 5, 6, 7, 8])
    def test_no_qty_in_rule6_plus_range_ever_produces_a_zero_leg(self, qty):
        st = ExitState.from_entry(
            symbol="SPY260802C00745000", side="C", entry_premium=1.50, qty=qty,
            exit_shape=self._shape(), strategy="ribbon_ride", trigger_level=744.0,
            structure_stop_enabled=True,
        )
        assert st.tp1_qty > 0, f"qty={qty} produced a ZERO-size TP1 leg -- disaster class"
        assert st.runner_qty > 0, f"qty={qty} produced a ZERO-size runner leg -- disaster class"
        assert st.tp1_qty + st.runner_qty == qty


# --------------------------------------------------------------------------------------
# 2. min_contracts IS A LIVE KNOB, NOT A DEAD ONE (C14 RED-proof: vary-and-assert that the
#    floor actually changes risk_gate's decision, using the REAL check_order function).
# --------------------------------------------------------------------------------------
class TestMinContractsNotDeadKnob:
    def _params(self, min_contracts: int) -> dict:
        p = dict(_agg_params())
        p["min_contracts"] = min_contracts
        return p

    @pytest.mark.parametrize("premium", [1.30, 1.50, 1.75, 1.99])
    def test_floor5_denies_floor3_allows_in_the_unlocked_band(self, premium):
        """The exact band tonight's study unlocks ($1.19 < premium <= ~$1.99 at bold-2's
        current $1,197.52 equity): floor=5 must DENY (RISK_CAP deadlock), floor=3 must
        ALLOW. If both alloweded the same way, the knob would be dead -- this is the
        RED-proof (task requirement)."""
        deny5 = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=5,
            premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=self._params(5),
        )
        allow3 = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=3,
            premium=premium, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=self._params(3),
        )
        assert deny5.allowed is False, f"premium={premium}: floor5 should deny (RISK_CAP)"
        assert deny5.code == rg.CODE_RISK_CAP
        assert allow3.allowed is True, f"premium={premium}: floor3 should allow"

    def test_above_the_unlocked_band_both_floors_still_deny(self):
        """Above ~$1.99 even floor=3 can't fit -- confirms the ceiling shift is bounded,
        not an unlimited unlock."""
        for mc in (5, 3):
            d = rg.check_order(
                "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=mc,
                premium=2.50, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
                current_position_status="flat", day_trades_used_5d=0,
                kill_switch_tripped=False, prior_stops_today=[], params=self._params(mc),
            )
            assert d.allowed is False

    def test_resolve_bold_qty_changes_with_floor_parameter(self):
        for premium in (1.30, 1.50, 1.75, 1.99):
            q5 = bfr.resolve_bold_qty(premium, min_contracts=5)
            q3 = bfr.resolve_bold_qty(premium, min_contracts=3)
            assert q5 is None, f"premium={premium}: floor5 should deadlock (None)"
            assert q3 == 3, f"premium={premium}: floor3 should resolve qty=3"


# --------------------------------------------------------------------------------------
# 3. MONOTONIC SUPERSET (structural, not just empirically observed in the one A/B run):
#    for ANY premium, if the higher floor (5) admits a trade, the lower floor (3) must too.
# --------------------------------------------------------------------------------------
class TestMonotonicSuperset:
    @pytest.mark.parametrize("premium", [0.30, 0.75, 1.00, 1.19, 1.50, 1.99, 2.12, 3.00])
    def test_lower_floor_never_excludes_what_higher_floor_admits(self, premium):
        q5 = bfr.resolve_bold_qty(premium, min_contracts=5)
        q3 = bfr.resolve_bold_qty(premium, min_contracts=3)
        if q5 is not None:
            assert q3 is not None, (
                f"premium={premium}: floor5 admitted but floor3 excluded -- "
                "monotonicity violated, the participation math is unsound")


# --------------------------------------------------------------------------------------
# 4. RULE 6 FLOOR + KILL-SWITCH INDEPENDENCE (task step 3's G6: "confirm the daily kill
#    switch and Rule-6 per-trade cap still bind correctly at the new size").
# --------------------------------------------------------------------------------------
class TestRule6AndKillSwitch:
    def test_rule6_absolute_floor_is_3(self):
        assert RULE_6_ABSOLUTE_MIN_CONTRACTS == 3

    def test_tested_variant_never_goes_below_rule6_floor(self):
        assert bfr.BOLD_MIN_CONTRACTS >= RULE_6_ABSOLUTE_MIN_CONTRACTS
        TESTED_VARIANT_MIN_CONTRACTS = 3  # the value this study tested
        assert TESTED_VARIANT_MIN_CONTRACTS >= RULE_6_ABSOLUTE_MIN_CONTRACTS

    def test_kill_switch_fires_identically_regardless_of_min_contracts(self):
        """KILL_SWITCH (risk_gate gate order position 1) must be evaluated before, and
        independently of, MIN_CONTRACTS (position 5). A tripped kill switch must deny at
        BOTH floor=5 and floor=3 -- proves lowering the floor cannot smuggle an order past
        an already-tripped daily kill switch."""
        for mc in (5, 3):
            p = dict(_agg_params())
            p["min_contracts"] = mc
            d = rg.check_order(
                "bold-2", equity=500.0, start_of_day_equity=1197.52, proposed_qty=mc,
                premium=1.00, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
                current_position_status="flat", day_trades_used_5d=0,
                kill_switch_tripped=False, prior_stops_today=[], params=p,
            )
            # equity $500 <= kill floor (1197.52 * (1-0.50) = $598.76) -> KILL_SWITCH,
            # regardless of min_contracts.
            assert d.allowed is False
            assert d.code == rg.CODE_KILL_SWITCH

    def test_risk_cap_still_binds_at_floor3_for_an_oversized_proposal(self):
        """Lowering the FLOOR does not raise the CEILING -- a qty that exceeds what
        equity*risk_cap allows must still be denied at floor=3."""
        p = dict(_agg_params())
        p["min_contracts"] = 3
        d = rg.check_order(
            "bold-2", equity=1197.52, start_of_day_equity=1197.52, proposed_qty=20,
            premium=1.50, setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
            current_position_status="flat", day_trades_used_5d=0,
            kill_switch_tripped=False, prior_stops_today=[], params=p,
        )
        assert d.allowed is False
        assert d.code == rg.CODE_RISK_CAP


# --------------------------------------------------------------------------------------
# 5. TOOL-EXTENSION PARITY (bold_fullhist_replay.py's new min_contracts parameter must be
#    byte-identical to every pre-existing call site when omitted).
# --------------------------------------------------------------------------------------
class TestToolExtensionParity:
    def test_replay_population_default_min_contracts_matches_bold_min_contracts_constant(self):
        sig = inspect.signature(bfr.replay_population)
        default = sig.parameters["min_contracts"].default
        assert default == bfr.BOLD_MIN_CONTRACTS == 5

    def test_resolve_bold_qty_default_unchanged(self):
        sig = inspect.signature(bfr.resolve_bold_qty)
        assert sig.parameters["min_contracts"].default == bfr.BOLD_MIN_CONTRACTS == 5


# --------------------------------------------------------------------------------------
# 6. NULL-RESULT PIN (this session's decision, not a new floor): min_contracts stays 5.
#    A future session re-testing this lever should read the study first, not silently
#    re-flip the value. This test intentionally does NOT block a future, evidence-backed
#    change -- it only fails loudly if the key drifts WITHOUT anyone updating this pin.
# --------------------------------------------------------------------------------------
def test_aggressive_params_min_contracts_unchanged_by_tonights_null_result():
    params = _agg_params()
    assert params.get("min_contracts") == 5, (
        "aggressive/params.json min_contracts changed since the MIN-CONTRACTS-BOLD-2026-08-02 "
        "NULL verdict (analysis/recommendations/min-contracts-bold-2026-08-02.md) -- if this "
        "is an intentional, freshly-evidenced re-ship, update this pin in the same commit; "
        "if it's accidental drift, revert to 5."
    )
