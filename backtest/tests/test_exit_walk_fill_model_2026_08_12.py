"""Guard: the walk harness's exit fill model is OPTIMISTIC vs live -- pinned until fixed.

THE FACT. backtest/lib/exit_manager_walk.py fills 6 of 9 exit stages (tp1, runner_target,
premium_stop, profit_lock_floor, trail, be_stop) at the EXACT triggered premium with ZERO
slippage. Only the 3 in _MARKET_STAGES (time_stop, ribbon_flip, structure_stop) pay
DEFAULT_EXIT_SLIPPAGE.

ITS JUSTIFICATION WAS FALSE. The docstring called the zero-slippage stages "a resting-order fill
model". No resting-order exit lane exists anywhere in this system:
    fleet_broker.market_sell -> {"type": "market", ...}, no limit_price key, ever
    exit_actuator.py:658     -> the SOLE market_sell call site
    heartbeat_core.py:1038/1044 -> core arms route through it; fleet_live does too
Every live exit at every stage is an unconditional market order and pays the spread. TP1 included.

So the 6 zero-slippage stages are ALWAYS optimistic vs live, never conservative -- TP1 and
runner_target overstate wins, the stops understate losses. (Stated precisely because this repo
already had to retract an "errs conservative" claim about the sibling simulator.)

WHY THIS IS A PIN AND NOT A FIX. walk_exit_manager has ~95 calling files and NO slippage kwarg --
DEFAULT_EXIT_SLIPPAGE is a module constant, so a fix needs new plumbing and moves every historical
cell at once. It belongs in the same pre-registered commit as the 2c->1c re-baseline and the fee
model. Fixing it unattended would launder a large number of published verdicts.

WHY A GUARD AT ALL: this exact mechanism was already documented correctly on 2026-07-23 in
automation/overnight/queue.md:2846 -- "every twin exit is a MARKET order (no exit-side
passive-limit lane exists) ... never its 'TP1/stop fills exactly at the bracket level' limit-exit
assumption -- flagged as a TWIN-B6b follow-up, not built" -- and sat unacted-on for three weeks
while studies kept consuming the harness. A note in a queue file is not a guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WALK = REPO / "backtest" / "lib" / "exit_manager_walk.py"
BROKER = REPO / "automation" / "state" / "fleet" / "fleet_broker.py"
ACTUATOR = REPO / "automation" / "state" / "fleet" / "exit_actuator.py"


def _code(p: Path) -> str:
    return "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                     if not ln.strip().startswith("#"))


# ------------------------------------------------------------------ the live mechanism


def test_live_exits_are_unconditional_market_orders():
    """THE PREMISE. If live ever gains a passive-limit exit lane, the harness's zero-slippage
    stages stop being wrong and this whole finding needs re-deriving rather than deleting."""
    code = _code(BROKER)
    m = re.search(r"def market_sell\(.*?\n(.*?)\ndef ", code, re.S)
    body = m.group(1) if m else code
    assert '"type": "market"' in body, "market_sell no longer sends a market order"
    assert "limit_price" not in body, (
        "market_sell gained a limit_price -- a passive-limit exit lane may now exist, which would "
        "change whether the walk harness's exact-fill stages are actually wrong")


def test_both_engines_exit_through_the_same_single_call_site():
    """The bias applies to core AND fleet because they share one actuator. If a second exit path
    appears, this finding's scope changes."""
    assert "market_sell" in _code(ACTUATOR)
    hb = _code(REPO / "setup" / "scripts" / "heartbeat_core.py")
    assert "exit_actuator" in hb, "core no longer routes exits through exit_actuator"


# ------------------------------------------------------------------ the harness convention


def test_only_three_stages_pay_slippage():
    """Pins the actual asymmetry. If _MARKET_STAGES grows to cover all stages, the bug is FIXED --
    delete this test in that commit rather than loosening it."""
    code = _code(WALK)
    m = re.search(r"_MARKET_STAGES\s*=\s*frozenset\(\{(.*?)\}\)", code, re.S)
    assert m, "_MARKET_STAGES not found -- the fill model was restructured; re-derive this guard"
    stages = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert stages == {"time_stop", "ribbon_flip", "structure_stop"}, (
        f"_MARKET_STAGES changed to {sorted(stages)}. If stages were ADDED, the optimism gap is "
        "being closed -- that is a fill-model change that moves every historical cell and needs "
        "its own prereg + re-baseline, not a silent edit.")


def test_the_false_resting_order_justification_is_gone():
    """THE DOCUMENTATION LIE. The docstring told study authors the zero-slippage stages modelled
    'a resting-order fill model'. They believed it; at least one live-relevant A/B
    (stop-mode-structure-vs-premium-2026-08-09) is confounded by exactly this asymmetry."""
    doc = WALK.read_text(encoding="utf-8")
    # POSITIVE MARKERS, not an absence check. My first cut asserted the phrase
    # "a resting-order fill" was ABSENT -- but the corrected docstring QUOTES that phrase in order
    # to label it false, so the test failed on its own fix. Fifth instance this session of
    # can't-tell-a-claim-from-its-retraction (params ratchet, DEAD labels, fast-path callers,
    # the allowlist filter). Absence checks cannot express "must not be ASSERTED"; a required
    # correction marker can.
    assert "ITS STATED JUSTIFICATION IS FALSE" in doc, (
        "the docstring no longer labels the resting-order justification as false. If the fill "
        "model was actually FIXED, delete this test in that commit; if the correction was merely "
        "removed, restore it -- fleet_broker.market_sell still sends a market order with no "
        "limit_price for every exit stage.")
    # Short marker on purpose: the full sentence wraps a line in the docstring, so a longer
    # substring would fail on the line break rather than on the thing being tested.
    assert "ALWAYS optimistic" in doc, (
        "the corrected direction-of-bias statement was removed from the docstring")
    assert "THERE IS NO RESTING-ORDER EXIT LANE" in doc, (
        "the live-mechanism refutation was removed -- that sentence is what makes the correction "
        "checkable rather than an opinion")


def test_the_plumbing_landed_and_its_defaults_are_inert():
    """RETIRED-AND-REPLACED 2026-08-13, per this test's own prior instruction.

    It used to assert walk_exit_manager had NO slippage kwarg, with the message: "the plumbing
    objection is gone, so the fill-model fix is now cheap. Do it under a prereg and delete this
    test." The prereg (FILL-MODEL-UNIFICATION-2026-08-13) was frozen and the plumbing landed, so
    that assertion fired exactly as designed.

    Replaced rather than deleted: what still matters is that the plumbing did NOT quietly change
    the default. Value-level pins for all 9 stages live in
    test_exit_walk_fill_plumbing_2026_08_13.py; this keeps the pointer so the two files are not
    read in isolation.
    """
    code = _code(WALK)
    m = re.search(r"def walk_exit_manager\((.*?)\)\s*->", code, re.S)
    assert m, "walk_exit_manager signature not found"
    sig = m.group(1)
    assert "exit_slippage" in sig and "all_exits_market" in sig, (
        "the STEP-1 plumbing was removed -- neither prereg arm can be run without it")
    assert "all_exits_market: bool = False" in sig, (
        "all_exits_market no longer defaults to False. Flipping it moves every one of ~95 calling "
        "files' historical cells; that belongs in the prereg'd commit with the re-baseline and "
        "fees, in the mandated order.")


def test_the_queue_entry_that_called_this_three_weeks_early_still_exists():
    """Provenance. This was written down correctly on 2026-07-23 and not acted on for three weeks.
    Keeping the pointer stops the next reader re-discovering it a fourth time."""
    q = REPO / "automation" / "overnight" / "queue.md"
    if not q.exists():
        pytest.skip("queue.md absent")
    text = q.read_text(encoding="utf-8", errors="replace")
    assert "TWIN-B6-SIM-FRICTION-CALIBRATION" in text
    assert "no exit-side passive-limit lane exists" in text, (
        "the 2026-07-23 entry that first identified this was edited away -- it is the provenance "
        "for the whole finding")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
