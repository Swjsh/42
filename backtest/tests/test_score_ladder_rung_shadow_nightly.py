"""Guard: backtest/tools/score_ladder_rung_shadow_nightly.py -- the $0 forward clock for LANE 1
(SCORE-LADDER-RUNG, single-demerit, bull-only, rungs 7/8, prereg a780122e) after the
2026-08-07 evening HOLD decision (analysis/deep-research/CLOSE-EXECUTION-2026-08-07.md).

Three things this guards:
1. Non-vacuous correctness: running the shadow for 2026-08-07 (a date with real fills +
   real OPRA already cached from the gate-decision run) reproduces the EXACT added_pnl
   (-$945.00) that decided tonight's HOLD -- proving the shadow uses the SAME mechanism,
   not a drifted copy (C14).
2. Zero trading-path effect: the shadow module never imports/references any live-order or
   config-mutation surface (fleet_live, risk_gate placement, accounts.json writes,
   place_bracket/place_option_order) -- grep-based vary-and-assert on its own source text.
3. Fail-open on a no-data date (weekend/holiday): returns 0, writes nothing, never raises.

RED-proof (this session): this test file was written BEFORE
backtest/tools/score_ladder_rung_shadow_nightly.py existed -- first run was a collection
error (ModuleNotFoundError). Quoted in CLOSE-EXECUTION-2026-08-07.md.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

BACKTEST = Path(__file__).resolve().parents[1]
ROOT = BACKTEST.parent
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(BACKTEST), str(BACKTEST / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEDGER_PATH = ROOT / "analysis" / "arm-ladder" / "ladder-rung-shadow-ledger.jsonl"
FORBIDDEN_SUBSTRINGS = (
    "fleet_live", "risk_gate", "place_bracket", "place_option_order",
    "accounts.json", "\"w\"", "'w'",  # no write-mode open on any file other than the ledger append
)


@pytest.fixture(scope="module")
def shadow():
    return importlib.import_module("score_ladder_rung_shadow_nightly")


def test_module_source_never_touches_a_live_order_or_config_surface():
    """Grep-based vary-and-assert: the shadow's own source text must never mention any
    live-placement or config-mutation surface. Import-time proof, not just documentation."""
    src_path = BACKTEST / "tools" / "score_ladder_rung_shadow_nightly.py"
    assert src_path.exists(), f"expected {src_path} to exist"
    src = src_path.read_text(encoding="utf-8")
    for bad in ("fleet_live", "risk_gate", "place_bracket", "place_option_order"):
        assert bad not in src, f"shadow script references live-order surface {bad!r}"
    assert 'open(LEDGER_OUT' in src or "LEDGER_OUT.open" in src or "open(str(LEDGER_OUT" in src, \
        "shadow script should write only through its own LEDGER_OUT path"
    # only append mode ("a") on the ledger file -- never "w" (which would blow away history)
    assert '"a"' in src or "'a'" in src, "ledger write must be append-mode"
    assert '"w")' not in src and "'w')" not in src, "no write-mode (truncating) file opens allowed"


def test_no_data_date_is_a_fail_open_noop(shadow, tmp_path, monkeypatch):
    """A date with zero core-decisions rows (weekend/holiday) must return 0 and write nothing
    -- never raise, never fabricate a row (C7: silent success is failure, but so is a crash
    on an expected gap)."""
    before = LEDGER_PATH.read_text(encoding="utf-8") if LEDGER_PATH.exists() else ""
    rc = shadow.run_for_date("2026-01-03")  # a Saturday -- no RTH ticks
    assert rc == 0
    after = LEDGER_PATH.read_text(encoding="utf-8") if LEDGER_PATH.exists() else ""
    assert after == before, "no-data date must not append anything to the ledger"


def test_2026_08_07_reproduces_the_exact_gate_decision_number(shadow):
    """The non-vacuous proof: replaying the shadow for the SAME day used to decide tonight's
    HOLD must reproduce the SAME added_pnl (-$945.00, rungs 7 and 8, real OPRA, no EST) that
    analysis/arm-ladder/LADDER-RUNG-2026-08-07-friday-final.json already recorded. If this
    ever drifts, the shadow and the ship-gate harness have silently diverged (C14)."""
    rc = shadow.run_for_date("2026-08-07")
    assert rc == 0
    assert LEDGER_PATH.exists()
    rows = [json.loads(line) for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    todays = [r for r in rows if r["date"] == "2026-08-07"]
    assert len(todays) >= 2, "expected one row per LANE-1 arm (risky-3 rung7, risky-1 rung8)"
    by_arm = {r["arm_id"]: r for r in todays[-2:]}
    assert set(by_arm) == {"risky-3", "risky-1"}
    for arm_id, rung in (("risky-3", 7), ("risky-1", 8)):
        row = by_arm[arm_id]
        assert row["rung"] == rung
        assert row["est"] is False, "shadow must always price on real OPRA, never EST"
        assert row["added_pnl"] == pytest.approx(-945.00, abs=0.01), (
            f"{arm_id}: shadow added_pnl {row['added_pnl']} drifted from the "
            "gate-decision run's -$945.00 -- mechanism divergence, investigate before trusting "
            "any future forward tally from this instrument")
        assert row["n_added"] == 57


def test_shadow_reuses_ladder_rung_replay_functions_not_a_second_copy(shadow):
    """C14 guard: the shadow must IMPORT its admission/walk logic from
    ladder_rung_replay_2026_08_07 rather than reimplementing rung_admits/walk_day -- so a
    future edit to the frozen mechanism can never silently drift between the ship-gate
    harness and its own forward clock."""
    import ladder_rung_replay_2026_08_07 as lrr
    assert shadow.rung_admits is lrr.rung_admits
    assert shadow.walk_day is lrr.walk_day
    assert shadow.DayBars is lrr.DayBars
