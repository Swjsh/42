"""Guard tests for the trigger_level data-fidelity fix in trades_enriched.py (2026-09-01).

ROOT CAUSE this pins: trigger_level was read from the wrong stage. The SIGNAL stage
(trigger_level_exact) is null whenever the trigger was a sloped trendline (see
conviction.py:64) -- categorically true for every BEARISH_REJECTION put, since a trendline
has no single horizontal price. The PLACEMENT stage (core: exec.trigger_level, fleet:
placement.trigger_level) is the level exit_manager.py ACTUALLY armed its structure stop
with, and is populated whenever a structure stop was armed at all.

THE INVARIANT (proof, not a heuristic): automation/state/fleet/exit_manager.py:268-269 --
    resolved_structure = (shape_mode == "structure" and bool(structure_stop_enabled)
                          and trigger_level is not None)
-- stop_mode can only resolve to "structure" when trigger_level was not None at entry. So
any row this repo's ledgers ever recorded with stop_mode=="structure" PROVES a real
trigger_level existed. If trades_enriched.py's own output ever has a structure-mode row
with a null trigger_level, that is proof the join is reading the wrong field again.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name):
    path = os.path.join(ROOT, "setup", "scripts", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


te = _load("trades_enriched")


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _mk_repo(tmp_path):
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True)
    fleet = state / "fleet"
    fleet.mkdir()
    (tmp_path / "analysis").mkdir()
    return tmp_path, state, fleet


REAL_REPO_ROOT = ROOT
_real_fills = os.path.join(REAL_REPO_ROOT, "automation", "state", "fills-ledger.jsonl")


# --------------------------------------------------------------------------- #
# Synthetic-fixture tests: pin the join mechanics in isolation.
# --------------------------------------------------------------------------- #

def test_core_path_prefers_placement_trigger_level_over_signal_stage(tmp_path):
    """The bug's PRIMARY case: a trendline-triggered (BEARISH_REJECTION put) entry has
    trigger_level_exact == null at the SIGNAL stage (no single horizontal price on a sloped
    trendline) but exit_manager.py still armed a real structure stop, so exec.trigger_level
    (PLACEMENT stage) carries the real number. The join must use the placement value, not
    fall through to the null signal-stage field."""
    repo, state, fleet = _mk_repo(tmp_path)

    fills = [
        {"arm": "safe-2", "symbol": "SPY260827P00772000", "side": "buy", "qty": 3,
         "price": 0.45, "multiplier": 100, "order_id": "OID-PUT1", "is_option": True,
         "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-2", "symbol": "SPY260827P00772000", "side": "sell", "qty": 3,
         "price": 0.30, "multiplier": 100, "order_id": "OID-PUT2", "is_option": True,
         "ts_utc": "2026-08-27T14:10:00Z", "ts_et": "2026-08-27T10:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-08-27T09:59:00", "account": "safe", "verdict": "ENTER_BEAR",
         "setup": "BEARISH_REJECTION", "reason": "tier ELITE",
         "trigger_level_exact": None,  # trendline trigger -- signal stage has no level
         "exec": {"symbol": "SPY260827P00772000", "stop_mode": "structure",
                   "trigger_level": 772.26, "broker": {"id": "OID-PUT1"}}},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    row = rows[0]
    assert row["stop_mode"] == "structure"
    assert row["trigger_level"] == 772.26, (
        f"placement-stage exec.trigger_level must win over null signal-stage "
        f"trigger_level_exact, got {row['trigger_level']!r}"
    )
    assert row["right"] == "P"


def test_core_path_falls_back_to_signal_stage_when_placement_missing(tmp_path):
    """When placement never recorded a level (e.g. exec.trigger_level absent -- an older
    row shape, or a non-structure entry), the join must still fall back to the signal-stage
    trigger_level_exact rather than losing the value entirely."""
    repo, state, fleet = _mk_repo(tmp_path)

    fills = [
        {"arm": "bold-2", "symbol": "SPY260827C00768000", "side": "buy", "qty": 2,
         "price": 0.55, "multiplier": 100, "order_id": "OID-C1", "is_option": True,
         "ts_utc": "2026-08-27T15:00:00Z", "ts_et": "2026-08-27T11:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "bold-2", "symbol": "SPY260827C00768000", "side": "sell", "qty": 2,
         "price": 0.75, "multiplier": 100, "order_id": "OID-C2", "is_option": True,
         "ts_utc": "2026-08-27T15:10:00Z", "ts_et": "2026-08-27T11:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-08-27T10:59:00", "account": "bold", "verdict": "ENTER_BULL",
         "setup": "LEVEL_RECLAIM", "reason": "tier BASE",
         "trigger_level_exact": 768.0,  # horizontal level, no trendline involved
         "exec": {"symbol": "SPY260827C00768000", "stop_mode": "premium",
                   "broker": {"id": "OID-C1"}}},  # no exec.trigger_level key at all
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    assert rows[0]["trigger_level"] == 768.0


def test_fleet_path_reads_placement_trigger_level_not_hardcoded_none(tmp_path):
    """The fleet-path bug: trigger_level was a HARDCODED None, discarding the level for
    every fleet arm (safe-3/risky-1/risky-3/etc), including safe-3, the go-live gate's
    prod-shadow arm. Must now read placement.trigger_level."""
    repo, state, fleet = _mk_repo(tmp_path)
    arm_dir = fleet / "safe-3"
    arm_dir.mkdir()

    fills = [
        {"arm": "safe-3", "symbol": "SPY260827C00773000", "side": "buy", "qty": 3,
         "price": 0.60, "multiplier": 100, "order_id": "OID-F1", "is_option": True,
         "ts_utc": "2026-08-27T16:00:00Z", "ts_et": "2026-08-27T12:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-3", "symbol": "SPY260827C00773000", "side": "sell", "qty": 3,
         "price": 0.80, "multiplier": 100, "order_id": "OID-F2", "is_option": True,
         "ts_utc": "2026-08-27T16:10:00Z", "ts_et": "2026-08-27T12:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    decisions = [
        {"ts_et": "2026-08-27T11:59:00", "action": "ENTER_BULL",
         "setup_name": "ribbon_ride", "quality": "ELITE",
         "placement": {"symbol": "SPY260827C00773000", "stop_mode": "structure",
                        "trigger_level": 773.03, "broker": {"id": "OID-F1"}}},
    ]
    _write_jsonl(arm_dir / "decisions.jsonl", decisions)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 1
    row = rows[0]
    assert row["arm"] == "safe-3"
    assert row["stop_mode"] == "structure"
    assert row["trigger_level"] == 773.03, (
        f"fleet path must read placement.trigger_level, not hardcode None -- "
        f"got {row['trigger_level']!r}"
    )


def test_fleet_path_multiple_arms_each_carry_own_structure_level(tmp_path):
    """risky-1 and risky-3 (the other fleet arms named in the diagnosis) must each carry
    their own placement-stage level too -- not just safe-3."""
    repo, state, fleet = _mk_repo(tmp_path)
    fills = []
    decisions_by_arm = {}
    for arm, symbol, order_id, level in (
        ("risky-1", "SPY260827C00774000", "OID-R1", 774.5),
        ("risky-3", "SPY260827P00771000", "OID-R3", 771.1),
    ):
        fills.append({"arm": arm, "symbol": symbol, "side": "buy", "qty": 2,
                       "price": 0.40, "multiplier": 100, "order_id": order_id, "is_option": True,
                       "ts_utc": "2026-08-27T17:00:00Z", "ts_et": "2026-08-27T13:00:00",
                       "date_et": "2026-08-27", "attribution": "engine"})
        fills.append({"arm": arm, "symbol": symbol, "side": "sell", "qty": 2,
                       "price": 0.55, "multiplier": 100, "order_id": order_id + "-X", "is_option": True,
                       "ts_utc": "2026-08-27T17:10:00Z", "ts_et": "2026-08-27T13:10:00",
                       "date_et": "2026-08-27", "attribution": "engine"})
        decisions_by_arm[arm] = [
            {"ts_et": "2026-08-27T12:59:00", "action": "ENTER_BULL",
             "setup_name": "vwap_continuation", "quality": "BASE",
             "placement": {"symbol": symbol, "stop_mode": "structure",
                            "trigger_level": level, "broker": {"id": order_id}}},
        ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    for arm, decisions in decisions_by_arm.items():
        arm_dir = fleet / arm
        arm_dir.mkdir()
        _write_jsonl(arm_dir / "decisions.jsonl", decisions)

    result = te.rebuild(repo)
    rows = {r["arm"]: r for r in result["rows"] if not r.get("_meta")}
    assert rows["risky-1"]["trigger_level"] == 774.5
    assert rows["risky-3"]["trigger_level"] == 771.1


def test_structure_stop_invariant_synthetic_no_violation(tmp_path):
    """Direct pin of the exit_manager.py:268 invariant on a small mixed synthetic ledger:
    every row this rebuild produces with stop_mode=='structure' has a non-null numeric
    trigger_level; a row with stop_mode=='premium' is allowed to be null."""
    repo, state, fleet = _mk_repo(tmp_path)
    fleet_arm = fleet / "safe-3"
    fleet_arm.mkdir()

    fills = [
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "buy", "qty": 3,
         "price": 0.50, "multiplier": 100, "order_id": "OID-S1", "is_option": True,
         "ts_utc": "2026-08-27T14:00:00Z", "ts_et": "2026-08-27T10:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-2", "symbol": "SPY260827C00768000", "side": "sell", "qty": 3,
         "price": 0.70, "multiplier": 100, "order_id": "OID-S2", "is_option": True,
         "ts_utc": "2026-08-27T14:10:00Z", "ts_et": "2026-08-27T10:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-3", "symbol": "SPY260827P00770000", "side": "buy", "qty": 2,
         "price": 0.35, "multiplier": 100, "order_id": "OID-S3", "is_option": True,
         "ts_utc": "2026-08-27T15:00:00Z", "ts_et": "2026-08-27T11:00:00",
         "date_et": "2026-08-27", "attribution": "engine"},
        {"arm": "safe-3", "symbol": "SPY260827P00770000", "side": "sell", "qty": 2,
         "price": 0.20, "multiplier": 100, "order_id": "OID-S4", "is_option": True,
         "ts_utc": "2026-08-27T15:10:00Z", "ts_et": "2026-08-27T11:10:00",
         "date_et": "2026-08-27", "attribution": "engine"},
    ]
    _write_jsonl(state / "fills-ledger.jsonl", fills)
    core_rows = [
        {"ts_et": "2026-08-27T09:59:00", "account": "safe", "verdict": "ENTER_BULL",
         "setup": "PREMIUM_MODE_ROW", "reason": "tier BASE",
         "trigger_level_exact": None,
         "exec": {"symbol": "SPY260827C00768000", "stop_mode": "premium",
                   "broker": {"id": "OID-S1"}}},
    ]
    _write_jsonl(state / "core-decisions.jsonl", core_rows)
    fleet_decisions = [
        {"ts_et": "2026-08-27T10:59:00", "action": "ENTER_BEAR",
         "setup_name": "BEARISH_REJECTION", "quality": "ELITE",
         "placement": {"symbol": "SPY260827P00770000", "stop_mode": "structure",
                        "trigger_level": 770.4, "broker": {"id": "OID-S3"}}},
    ]
    _write_jsonl(fleet_arm / "decisions.jsonl", fleet_decisions)

    result = te.rebuild(repo)
    rows = [r for r in result["rows"] if not r.get("_meta")]
    assert len(rows) == 2

    structure_rows = [r for r in rows if r["stop_mode"] == "structure"]
    assert structure_rows, "fixture must include at least one structure-mode row"
    for r in structure_rows:
        assert isinstance(r["trigger_level"], (int, float)), (
            f"stop_mode=='structure' row must carry a numeric trigger_level "
            f"(exit_manager.py:268 proves one existed at entry) -- row {r['symbol']} "
            f"got {r['trigger_level']!r}"
        )

    premium_row = next(r for r in rows if r["stop_mode"] == "premium")
    assert premium_row["trigger_level"] is None  # allowed -- premium mode needs no level


# --------------------------------------------------------------------------- #
# Real-tape checks: pin the invariant + the disclosed puts-were-categorically-null bug
# against the actual repo ledgers, for post-2026-08-11 engine rows (the window the
# whole-engine null study replays).
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_structure_stop_invariant_holds():
    """The core invariant, proved by exit_manager.py:268 (resolved_structure requires
    trigger_level is not None): NO row in the real, freshly-rebuilt ledger may have
    stop_mode=='structure' with a null trigger_level. This is the exact guard the task
    brief specifies."""
    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    rows = result["rows"]

    violations = [
        (r["date"], r["arm"], r["symbol"])
        for r in rows
        if r.get("stop_mode") == "structure" and r.get("trigger_level") is None
    ]
    assert not violations, (
        f"{len(violations)} row(s) have stop_mode=='structure' but null trigger_level -- "
        f"this violates the exit_manager.py:268 invariant (a structure stop can only "
        f"resolve when trigger_level is not None at entry): {violations[:10]}"
    )


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_fleet_structure_rows_carry_trigger_level():
    """Fleet-specific slice of the invariant: safe-3/risky-1/risky-3 rows with
    stop_mode=='structure' must carry a non-null numeric trigger_level. Pre-fix, the fleet
    path hardcoded None for every row regardless of stop_mode, so this would have failed
    for all 3 arms."""
    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    fleet_arms = {"safe-3", "risky-1", "risky-3"}
    fleet_structure_rows = [
        r for r in result["rows"]
        if r.get("arm") in fleet_arms and r.get("stop_mode") == "structure"
    ]
    assert fleet_structure_rows, "expected at least one fleet structure-mode row in the real ledger"
    for r in fleet_structure_rows:
        assert isinstance(r["trigger_level"], (int, float)), (
            f"fleet arm {r['arm']} row {r['symbol']} on {r['date']} has stop_mode=='structure' "
            f"but trigger_level={r['trigger_level']!r}"
        )


@pytest.mark.skipif(not os.path.exists(_real_fills), reason="real fills-ledger.jsonl not present")
def test_real_tape_puts_are_no_longer_categorically_null():
    """Pre-fix, EVERY put row (right=='P') in the post-2026-08-11 window had
    trigger_level==None, because BEARISH_REJECTION's trendline trigger always nulls the
    SIGNAL-stage trigger_level_exact -- this is exactly the sign-agreement-killing gap the
    whole-engine null study hit. Post-fix, puts whose stop_mode resolved to 'structure' must
    show real placement-stage levels."""
    result = te.rebuild(Path(REAL_REPO_ROOT), write=False)
    post_puts = [
        r for r in result["rows"]
        if r.get("right") == "P" and r.get("date", "") > "2026-08-11"
        and r.get("stop_mode") == "structure"
    ]
    assert post_puts, "expected at least one post-2026-08-11 structure-mode put row"
    non_null_puts = [r for r in post_puts if r.get("trigger_level") is not None]
    assert len(non_null_puts) == len(post_puts), (
        f"{len(post_puts) - len(non_null_puts)} of {len(post_puts)} post-2026-08-11 "
        f"structure-mode put rows still have a null trigger_level -- the bear side is "
        f"still categorically null"
    )
