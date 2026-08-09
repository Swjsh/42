"""Guards for setup/scripts/stop_mode_shadow_ledger.py (forward stop_mode clock, 2026-08-09).

THE BUG THESE EXIST TO PREVENT (found by this module's own smoke test before it ever shipped):
the first cut sourced its events from `entry_quality_ledger.build_population()`, which returns
RAW broker fills with NO `trigger_level` key at all (verified 249/249 missing -- that field is
attached later in the ledger pipeline). `walk_exit_manager` with `trigger_level=None` has no
chart level to invalidate against, so the structure stop can never fire, the CONTROL arm
silently collapses to premium-only, and BOTH arms return byte-identical P&L. The clock would
have accrued exactly $0.00 forever while reporting itself perfectly healthy -- an instrument
that looks alive and measures nothing.

That failure is invisible to any test that only checks "does it run without raising", so the
guards below assert the two properties that actually distinguish a working clock from a dead
one: the CONTROL arm must really differ from the PREMIUM arm, and the two arms must not be
accidentally identical by construction.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "stop_mode_shadow_ledger.py"
LEDGER_JSON = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"


def _load():
    spec = importlib.util.spec_from_file_location("stop_mode_shadow_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["stop_mode_shadow_ledger"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_script_exists():
    assert SCRIPT.exists(), f"missing {SCRIPT}"


def test_arms_differ_in_exactly_one_field():
    """PREMIUM must be CONTROL with stop_mode flipped and NOTHING else -- a second differing
    field would silently turn a one-variable A/B into a bundle (the exact defect the parent
    matrix's ATR_STOP column had)."""
    m = _load()
    ctl, prem = m._shapes()
    diff = {k for k in set(ctl) | set(prem) if ctl.get(k) != prem.get(k)}
    assert diff == {"stop_mode"}, f"arms differ in more than stop_mode: {diff}"
    assert ctl["stop_mode"] == "structure"
    assert prem["stop_mode"] == "premium"


def test_control_arm_is_read_from_shipped_strategy_not_retyped():
    """If someone hardcodes the control shape, this clock stops tracking the live exit."""
    m = _load()
    sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
    import strategies as fleet_strategies
    ctl, _ = m._shapes()
    assert ctl == dict(fleet_strategies.by_name("ribbon_ride").exit.to_dict())


def test_accrual_start_is_after_the_retrospective_cutoff():
    """Forward clock: seeding it with the same window the retrospective study already scored
    would double-count and destroy its out-of-sample property."""
    m = _load()
    assert m.ACCRUAL_START_DATE > "2026-08-07"


@pytest.mark.skipif(not LEDGER_JSON.exists(), reason="enriched ledger not present")
def test_enriched_ledger_carries_trigger_level():
    """THE regression guard. build_population() lacks trigger_level; the enriched JSON has it.
    If the source ever regresses to the raw one, structure stops stop firing and every delta
    silently becomes 0.00."""
    events = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))["events"]
    assert events, "enriched ledger has no events"
    n_with = sum(1 for e in events if e.get("trigger_level") is not None)
    assert any("trigger_level" in e for e in events), (
        "enriched ledger lost its trigger_level field -- the structure stop cannot fire "
        "without it and this clock would accrue meaningless zeros")
    assert n_with > 0, "no event carries a non-null trigger_level"


@pytest.mark.skipif(not LEDGER_JSON.exists(), reason="enriched ledger not present")
def test_run_reads_enriched_ledger_not_build_population():
    """Source-level guard: the module must not call build_population() for its event set."""
    src = SCRIPT.read_text(encoding="utf-8")
    # Strip comments: a comment explaining why we do NOT call build_population is correct
    # documentation and must not trip this guard -- only a real call should.
    body = "\n".join(ln.split("#", 1)[0] for ln in src.split("def run(")[1].splitlines())
    assert "build_population()" not in body, (
        "run() calls build_population() -- that source has no trigger_level and silently "
        "zeroes every delta")
    assert "entry-quality-ledger.json" in body


def test_input_health_flags_a_stale_feed():
    """A clock whose input stops updating must SAY so, not read as 'no fills today'."""
    m = _load()
    fresh = m._input_health([{"date_et": "2099-01-01"}])
    assert fresh["input_stale"] is False
    stale = m._input_health([{"date_et": "2020-01-01"}])
    assert stale["input_stale"] is True
    assert "STALE" in stale["input_note"]


def test_summary_never_claims_a_ship():
    """Descriptive-only contract: reaching the bar is permission to TEST, never to ship."""
    m = _load()
    s = m._summarize([])
    assert s["status"] == "ARMED_AWAITING_FILLS"
    s2 = m._summarize([{
        "date_et": "2026-08-10", "delta_pnl": 5.0,
        "control": {"pnl": -1.0}, "premium": {"pnl": 4.0}}])
    assert "NEVER changes stop_mode by itself" in s2["decision_rule"]
    assert s2["status"] in ("ACCRUING", "BAR_MET_AWAITING_PREREG_AB")


def test_mechanism_signature_requires_wr_to_fall():
    """The pre-registered gate is expectancy UP *and* win rate DOWN. A version that fires on
    dollars alone would have reported the retrospective real-fills result as a confirmation
    when it actually failed its own mechanism test."""
    m = _load()
    up_wr_up = m._summarize([
        {"date_et": "2026-08-10", "delta_pnl": 10.0,
         "control": {"pnl": -5.0}, "premium": {"pnl": 5.0}}])
    assert up_wr_up["mean_delta_per_trade"] > 0
    assert up_wr_up["delta_wr"] > 0
    assert up_wr_up["mechanism_signature_holds"] is False, (
        "signature must NOT hold when win rate rises, however good the dollars look")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
