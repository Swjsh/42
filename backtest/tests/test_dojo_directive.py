"""Guard + acceptance tests for setup/scripts/dojo/directive.py (DOJO Phase 1 build,
DOJO-ARCHITECTURE-DECISION.md's directive.py contract).

Proves: a well-formed directive parses into a DojoDirective; an unknown arm id RAISES
(RED-proof); an unknown exit_patch key RAISES (RED-proof); `to_ledger_row` produces a dict
that round-trips through `json.dumps`/`json.loads` byte-for-byte; and a handful of the other
fail-loud paths the contract requires (missing field, bad side, malformed trigger, dojo=False
refusal, id auto-generation) so the "fail LOUD, never silently no-op" rule is actually proven,
not just asserted in a docstring.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_directive.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import directive as dd  # noqa: E402

# A well-formed raw directive, matching a real active-arm roster + a real trigger vocabulary.
VALID_RAW = {
    "issued_et": "2026-07-17T09:41:00",
    "cursor_et": "2026-07-17T09:40:00",
    "arms": ["safe", "bold", "safe-3"],
    "side": "C",
    "trigger": {
        "type": "level_reclaim_confirmed_close",
        "tag_level": 600.0,
        "confirm_close_above": 600.5,
    },
    "invalidation": {"close_below": 599.0},
    "exits": {"stop_mode": "structure", "trail_pct": 0.15},
    "sizing": {"qty": 3},
    "note": "J: ride the reclaim on safe+bold+safe-3, tight trail",
}


def _raw(**overrides) -> dict:
    """A fresh copy of VALID_RAW with the given keys overridden -- never mutate the shared
    module-level fixture (coding-style immutability rule)."""
    out = json.loads(json.dumps(VALID_RAW))  # deep copy via round-trip; the fixture is JSON-safe
    out.update(overrides)
    return out


# ============================================================================ 1. valid parses
def test_valid_directive_parses():
    d = dd.parse_and_validate(_raw())
    assert isinstance(d, dd.DojoDirective)
    assert d.arms == ["safe", "bold", "safe-3"]
    assert d.side == "C"
    assert d.dojo is True
    assert d.trigger["type"] == "level_reclaim_confirmed_close"
    assert d.exits == {"stop_mode": "structure", "trail_pct": 0.15}
    assert d.sizing == {"qty": 3}
    assert d.note.startswith("J: ride the reclaim")
    # issued_et/cursor_et parsed to tz-aware ET datetimes (package-wide convention)
    assert d.issued_et.tzinfo is not None
    assert d.cursor_et.tzinfo is not None
    assert d.issued_et.year == 2026 and d.issued_et.month == 7 and d.issued_et.day == 17


# ==================================================================== 2. unknown arm id RAISES
def test_unknown_arm_id_raises():
    with pytest.raises(ValueError, match="unknown arm id"):
        dd.parse_and_validate(_raw(arms=["safe", "not-a-real-arm"]))


def test_retired_arm_id_raises():
    """safe-1 is status='retired' in the real accounts.json -- retired is NOT active, so it
    must be rejected exactly like a made-up id (proves the roster load filters on status,
    not just id presence)."""
    with pytest.raises(ValueError, match="unknown arm id"):
        dd.parse_and_validate(_raw(arms=["safe-1"]))


# ============================================================ 3. unknown exit_patch key RAISES
def test_unknown_exit_patch_key_raises():
    with pytest.raises(ValueError, match="unknown exit_patch key"):
        dd.parse_and_validate(_raw(exits={"totally_made_up_knob": 1}))


def test_known_exit_patch_keys_all_accepted():
    """Every key fleet_executor actually validates against must round-trip through dojo's
    directive parser untouched -- proves the two schemas are genuinely the same set, not two
    independently-hand-typed lists that can silently drift (C14/L201)."""
    import fleet_executor  # already on sys.path via directive's own bootstrap

    full_patch = {
        "premium_stop_pct": -0.2,
        "tp1_premium_pct": 1.5,
        "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "trailing",
        "runner_target_pct": 2.5,
        "trail_pct": 0.125,
        "profit_lock_arm_pct": 0.05,
        "stop_mode": "structure",
        "catastrophe_stop_pct": -0.5,
        "profit_lock_arm_scope": "post_tp1",
    }
    assert set(full_patch) == fleet_executor.EXIT_PATCH_ALLOWED_KEYS
    d = dd.parse_and_validate(_raw(exits=full_patch))
    assert d.exits == full_patch


# ==================================================================== 4. to_ledger_row round-trip
def test_to_ledger_row_round_trips_through_json_dumps():
    d = dd.parse_and_validate(_raw())
    row = dd.to_ledger_row(d)
    dumped = json.dumps(row)
    reloaded = json.loads(dumped)
    assert reloaded == row
    assert reloaded["id"] == d.id
    assert reloaded["arms"] == d.arms
    assert reloaded["issued_et"] == d.issued_et.isoformat()
    assert reloaded["cursor_et"] == d.cursor_et.isoformat()
    assert reloaded["dojo"] is True
    # every value must be a plain JSON-safe type -- no datetimes/sets/dataclasses leaked through
    for v in row.values():
        assert isinstance(v, (str, int, float, bool, list, dict, type(None)))


# =========================================================================== other fail-loud paths
@pytest.mark.parametrize("missing", list(dd.REQUIRED_RAW_FIELDS))
def test_missing_required_field_raises(missing):
    raw = _raw()
    del raw[missing]
    with pytest.raises(ValueError, match=f"missing required field {missing!r}"):
        dd.parse_and_validate(raw)


def test_bad_side_raises():
    with pytest.raises(ValueError):
        dd.parse_and_validate(_raw(side="X"))


def test_malformed_trigger_type_raises():
    with pytest.raises(ValueError):
        dd.parse_and_validate(_raw(trigger={"type": "not_a_real_trigger_type"}))


def test_non_dict_directive_raises():
    with pytest.raises(ValueError, match="must be a JSON object"):
        dd.parse_and_validate(["not", "a", "dict"])  # type: ignore[arg-type]


def test_dojo_false_refused():
    with pytest.raises(ValueError, match="dojo=True"):
        dd.parse_and_validate(_raw(dojo=False))


def test_bare_time_of_day_timestamp_rejected():
    """j_intent_logic.parse_et's 'HH:MM' sentinel-year (1900) escape hatch must never leak
    into a dojo directive -- a directive always needs a real calendar date."""
    with pytest.raises(ValueError, match="full timestamp"):
        dd.parse_and_validate(_raw(issued_et="09:41"))


def test_id_auto_generated_when_absent():
    d = dd.parse_and_validate(_raw())
    assert d.id.startswith("dojo-20260717-094100-c")


def test_explicit_id_preserved():
    d = dd.parse_and_validate(_raw(id="dojo-custom-001"))
    assert d.id == "dojo-custom-001"


def test_session_py_reads_id_and_arms():
    """session.cmd_directive reads `d.id` / `getattr(d, 'arms', None)` off the return value --
    prove both are present and of the expected shape without importing session.py itself
    (session.py is owned by another builder / frozen for this task)."""
    d = dd.parse_and_validate(_raw())
    assert isinstance(d.id, str) and d.id
    assert isinstance(d.arms, list) and all(isinstance(a, str) for a in d.arms)
