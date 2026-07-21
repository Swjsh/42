"""Guard for the 2026-07-21 root-cause fix in backtest/tools/exit_shape_parity_study.py.

Two invariants pinned here, both load-bearing:

  1. BACKWARD-COMPAT (must never regress): `load_fleet_engine_fills()` called with NO args
     (how every existing study/tool/test calls it) must stay scoped to `FLEET_REST_ARMS` ONLY --
     byte-identical to pre-fix behavior. This is what keeps every frozen historical anchor
     (structure_stop_study's `-757.1` CONTROL pin, T4/T5, ribbon_ride_strike_exit_ab,
     p5_topcell_real_fills_confirm) reproducible. A silent default-arm-scope change here would be
     exactly the "re-pick after seeing results" hazard the no_repick_clause discipline exists to
     prevent.

  2. THE FIX ITSELF: `load_fleet_engine_fills(arms=esp.ALL_LIVE_ARMS)` must include CORE-arm
     (safe-2/bold-2) fills that the fleet-only default cannot see -- this is what unblocks a
     FUTURE, separately-frozen re-run against current-day real trading (root cause of the
     "0/0 exhibit fills recoverable" gap disclosed twice on 2026-07-20 in
     STRUCTURE-STOP-ZONE-BAND / STRUCTURE-STOP-REFERENCE-LEVEL, and of every recurring
     T-AUTOPSY "confirm on fresh OPRA slice" hypothesis coming up empty).

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_exit_shape_parity_study_core_arms.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import exit_shape_parity_study as esp  # noqa: E402

FIXTURE_ROWS = [
    # a fleet-rest fill (must always be seen)
    {"arm": "safe-1", "symbol": "SPY260630C00743000", "side": "buy", "qty": 8.0,
     "price": 0.14, "is_crypto": False, "is_option": True, "ts_utc": "2026-06-30T14:49:06Z",
     "date_et": "2026-06-30", "attribution": "engine"},
    # a CORE arm fill predating structure_stop_study.ANCHOR_END_DATE (2026-07-08) -- exactly
    # the population the default must NOT silently absorb
    {"arm": "safe-2", "symbol": "SPY260701C00745000", "side": "buy", "qty": 3.0,
     "price": 0.50, "is_crypto": False, "is_option": True, "ts_utc": "2026-07-01T14:00:00Z",
     "date_et": "2026-07-01", "attribution": "engine"},
    # a CORE bold-2 fill, today-dated
    {"arm": "bold-2", "symbol": "SPY260721P00748000", "side": "buy", "qty": 3.0,
     "price": 0.33, "is_crypto": False, "is_option": True, "ts_utc": "2026-07-21T18:58:18Z",
     "date_et": "2026-07-21", "attribution": "engine"},
    # non-engine attribution must stay excluded regardless of arms scope
    {"arm": "safe-2", "symbol": "SPY260721C00745000", "side": "buy", "qty": 1.0,
     "price": 0.10, "is_crypto": False, "is_option": True, "ts_utc": "2026-07-21T15:00:00Z",
     "date_et": "2026-07-21", "attribution": "manual"},
]


def _write_fixture_ledger(tmp_path: Path) -> Path:
    p = tmp_path / "fills-ledger-fixture.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in FIXTURE_ROWS) + "\n", encoding="utf-8")
    return p


def test_all_live_arms_is_fleet_plus_core():
    assert esp.CORE_ARMS == ("safe-2", "bold-2")
    assert esp.ALL_LIVE_ARMS == esp.FLEET_REST_ARMS + esp.CORE_ARMS
    assert set(esp.FLEET_REST_ARMS).isdisjoint(esp.CORE_ARMS)


def test_default_scope_is_fleet_only_backward_compat(tmp_path):
    """THE regression this test exists to catch: a future edit accidentally widening the
    DEFAULT would silently shift every frozen anchor built on load_fleet_engine_fills()."""
    ledger = _write_fixture_ledger(tmp_path)
    fills = esp.load_fleet_engine_fills(ledger_path=ledger)
    arms_seen = {f["arm"] for f in fills}
    assert arms_seen == {"safe-1"}, (
        f"default arg must stay FLEET_REST_ARMS-only, saw {arms_seen}")
    assert len(fills) == 1


def test_explicit_all_live_arms_includes_core_fills(tmp_path):
    """THE fix: explicitly requesting ALL_LIVE_ARMS surfaces the core-arm (safe-2/bold-2)
    fills the fleet-only default is structurally blind to."""
    ledger = _write_fixture_ledger(tmp_path)
    fills = esp.load_fleet_engine_fills(ledger_path=ledger, arms=esp.ALL_LIVE_ARMS)
    arms_seen = {f["arm"] for f in fills}
    assert arms_seen == {"safe-1", "safe-2", "bold-2"}
    # non-engine attribution row must still be excluded even under the widened arm scope
    assert len(fills) == 3


def test_manual_attribution_excluded_under_either_scope(tmp_path):
    ledger = _write_fixture_ledger(tmp_path)
    fleet_only = esp.load_fleet_engine_fills(ledger_path=ledger)
    all_live = esp.load_fleet_engine_fills(ledger_path=ledger, arms=esp.ALL_LIVE_ARMS)
    for fills in (fleet_only, all_live):
        assert all(f["attribution"] == "engine" for f in fills)


def test_core_arm_fills_predate_anchor_cutoff_would_change_frozen_pin_if_defaulted(tmp_path):
    """Documents WHY the default must not change: the 2026-07-01 core fill in this fixture
    (standing in for the 127 real safe-2/bold-2 fills confirmed <= 2026-07-08 in production
    fills-ledger.jsonl) predates structure_stop_study.ANCHOR_END_DATE (2026-07-08) -- if
    load_fleet_engine_fills() ever defaulted to ALL_LIVE_ARMS, this fill would silently enter
    the FROZEN anchor population and change test_control_anchor_reproduces_established_baseline_live's
    pinned -757.1."""
    ledger = _write_fixture_ledger(tmp_path)
    fleet_only = esp.load_fleet_engine_fills(ledger_path=ledger)
    all_live = esp.load_fleet_engine_fills(ledger_path=ledger, arms=esp.ALL_LIVE_ARMS)
    pre_anchor_core_fills = [f for f in all_live
                             if f["arm"] in esp.CORE_ARMS and f["date_et"] <= "2026-07-08"]
    assert len(pre_anchor_core_fills) == 1
    assert pre_anchor_core_fills[0] not in fleet_only
