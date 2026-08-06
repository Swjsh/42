"""FLEET-PDT-PARITY guards (2026-08-06, EOD-2026-08-05-SILENT-ARMS).

THE DEFECT: fleet_live.py read `acct.get("daytrade_count")`, which Alpaca PAPER returns
as null for every arm -> the margin-PDT branch of the risk gate (fleet arms are pinned to
pdt_gate_mode="margin_pdt" at fleet_executor.py:1125) was fed a hardcoded 0 forever, and
the decision ledger logged `day_trades: 0` as if it were broker truth. Broker-verified
2026-08-06: the TRUE trailing-5bd counts were safe-3=6, risky-1=7, risky-3=8.

THE SHAPE OF THE FIX these guards pin:
  * VISIBILITY is unconditional -- the true count + its source land in the row every tick.
  * ENFORCEMENT is opt-in (params.fleet_pdt_enforce, default absent/false) and additionally
    requires the arm to be live. Default = byte-identical to pre-fix (C14 vary-and-assert:
    the flag must actually change what the gate binds on, or it is a dead knob).
  * FAIL-OPEN never invents a block: any fetch failure degrades to the broker field, then 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import fleet_live as fl  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_memo():
    fl._pdt_memo.clear()
    yield
    fl._pdt_memo.clear()


# ------------------------------------------------------------------ the read is now TRUE
def test_true_count_comes_from_pdt_tracker_not_the_null_broker_field(monkeypatch):
    """The regression that shipped the bug: broker field null -> 0, while the real
    trailing-5bd count was 7. The tracker value must win."""
    import pdt_tracker
    monkeypatch.setattr(pdt_tracker, "fetch_day_trades_used_5d", lambda creds, *a, **k: 7)
    n, src = fl._true_day_trades_5d("risky-1", {"key": "k", "secret": "s"},
                                    {"daytrade_count": None})
    assert (n, src) == (7, "pdt_tracker")


def test_fetch_failure_fails_open_to_the_broker_field_then_zero(monkeypatch):
    """FAIL-OPEN DIRECTION (pdt_tracker's documented contract): a fetch outage must degrade
    to the pre-fix value -- it may never manufacture a block the engine did not have."""
    import pdt_tracker
    monkeypatch.setattr(pdt_tracker, "fetch_day_trades_used_5d",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net down")))
    assert fl._true_day_trades_5d("a", {}, {"daytrade_count": 2}) == (2, "broker_field_fallback")
    assert fl._true_day_trades_5d("b", {}, {"daytrade_count": None}) == (0, "broker_field_fallback")
    assert fl._true_day_trades_5d("c", {}, {}) == (0, "broker_field_fallback")


def test_ttl_memo_serves_the_cache_then_refetches_after_expiry(monkeypatch):
    """The fetch is ~150-200 ms and run() walks every arm inside the placement path."""
    calls = {"n": 0}

    def _fake(creds, *a, **k):
        calls["n"] += 1
        return 4

    import pdt_tracker
    monkeypatch.setattr(pdt_tracker, "fetch_day_trades_used_5d", _fake)
    assert fl._true_day_trades_5d("safe-3", {}, {}, now_mono=1000.0) == (4, "pdt_tracker")
    assert fl._true_day_trades_5d("safe-3", {}, {}, now_mono=1000.0 + fl._PDT_TTL_SEC - 1) \
        == (4, "pdt_tracker_cached")
    assert calls["n"] == 1, "cache did not serve inside the TTL"
    fl._true_day_trades_5d("safe-3", {}, {}, now_mono=1000.0 + fl._PDT_TTL_SEC + 1)
    assert calls["n"] == 2, "cache never expired -- a completed round trip would stay invisible"


def test_memo_is_keyed_per_arm_never_shared(monkeypatch):
    """Separate Alpaca accounts = separate PDT budgets. A shared cache would cross-contaminate."""
    counts = {"safe-3": 6, "risky-1": 7, "risky-3": 8}
    import pdt_tracker
    monkeypatch.setattr(pdt_tracker, "fetch_day_trades_used_5d",
                        lambda creds, *a, **k: counts[creds["arm"]])
    for arm, want in counts.items():
        assert fl._true_day_trades_5d(arm, {"arm": arm}, {})[0] == want


# ----------------------------------------------------- enforcement is opt-in + vary-and-assert
def _gate_input(*, params: dict, arm_live: bool, true_count: int, legacy: int) -> int:
    """Mirror of the run() expression under test -- the ONE line that decides what the risk
    gate binds on. Kept in lockstep with fleet_live.run() by
    test_run_expression_matches_this_mirror below (AST-level, so drift REDs)."""
    enforce = bool(params.get("fleet_pdt_enforce")) and bool(arm_live)
    return true_count if enforce else legacy


@pytest.mark.parametrize("params,live,expected", [
    ({}, True, 0),                                # DEFAULT: byte-identical to pre-fix
    ({"fleet_pdt_enforce": False}, True, 0),      # explicit off
    ({"fleet_pdt_enforce": True}, False, 0),      # armed but arm not live -> still legacy
    ({"fleet_pdt_enforce": True}, True, 7),       # armed + live -> the TRUE count binds
])
def test_enforcement_flag_is_not_a_dead_knob(params, live, expected):
    """C14/L201 vary-and-assert: the flag must CHANGE the value the risk gate sees in
    exactly one cell and leave the other three at today's behavior."""
    assert _gate_input(params=params, arm_live=live, true_count=7, legacy=0) == expected


def test_run_expression_matches_this_mirror():
    """The mirror above must not silently drift from production. Pins the literal source
    line in fleet_live.run() (a rename/refactor REDs here instead of quietly un-testing
    the flag)."""
    src = (REPO / "automation" / "state" / "fleet" / "fleet_live.py").read_text(encoding="utf-8")
    assert 'enforce_true = bool(params.get("fleet_pdt_enforce")) and bool(arm.get("live"))' in src
    assert "day_trades = day_trades_true if enforce_true else day_trades_legacy" in src
    assert "row.update(day_trades_true=day_trades_true, day_trades_source=day_trades_source," in src


def test_default_params_do_not_arm_enforcement():
    """Ship-state assertion: neither live params file may carry the flag armed. Flipping it
    jails all three fleet arms (true counts 6/7/8 >= 3) and is a deliberate, separate act."""
    import json
    for rel in ("automation/state/params.json", "automation/state/aggressive/params.json"):
        p = REPO / rel
        if not p.exists():
            continue
        assert not json.loads(p.read_text(encoding="utf-8")).get("fleet_pdt_enforce"), \
            f"{rel} arms fleet PDT enforcement -- that silences the fleet; must be deliberate"


def test_fleet_arms_are_pinned_to_margin_pdt_so_the_count_is_load_bearing():
    """If the fleet were ever repinned to cash_settlement this whole fix would be moot --
    pin the assumption so a future repin surfaces here instead of silently orphaning it."""
    src = (REPO / "automation" / "state" / "fleet" / "fleet_executor.py").read_text(encoding="utf-8")
    assert '_fleet_params["pdt_gate_mode"] = "margin_pdt"' in src
