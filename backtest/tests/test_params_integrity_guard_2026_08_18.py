"""Guard: setup/scripts/params_integrity_guard.py — the RULE-9 mid-session params-mutation
DETECTOR (RULE-ENGINE-ALIGNMENT-2026-08-18.md finding #1: params.json is read fresh from
disk every heartbeat_core tick with nothing detecting or reporting a same-day edit).

RED-PROOF NOTE: tests 1-8 exercise params_integrity_guard.py directly (hermetic — every
constant the module touches is monkeypatched to a tmp_path, so NOTHING here reads or writes
real automation/state files). test_wiring_heartbeat_core_calls_check_every_tick is the one
that RED-proofs the INTEGRATION: written and run BEFORE heartbeat_core.py was edited to call
params_integrity_guard.check(...), it failed with an AssertionError (no such call present in
main()'s source) — proving the test exercises something real, not a tautology. After wiring
the one try/except call into main(), the same test passes. See the session report for the
exact before/after pytest lines.

Run:  cd backtest && .venv/Scripts/python.exe -m pytest tests/test_params_integrity_guard_2026_08_18.py -q
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import params_integrity_guard as pig  # noqa: E402

HEARTBEAT_CORE = SCRIPTS / "heartbeat_core.py"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect every module-level path constant to an isolated tmp_path tree so no test
    ever touches real automation/state/*.json or STATUS.md. Returns the dict of
    {name: Path} it wired as WATCHED_FILES for convenience."""
    state = tmp_path / "state"
    state.mkdir()
    watched = {
        "core_safe": state / "params.json",
        "core_bold": state / "aggressive" / "params.json",
        "fleet_accounts": state / "fleet" / "accounts.json",
    }
    for p in watched.values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"tp1_premium_pct": 0.5, "premium_stop_pct": -0.5}), encoding="utf-8")

    status_md = tmp_path / "STATUS.md"
    status_md.write_text("", encoding="utf-8")
    outbox = state / "discord-outbox.jsonl"
    snapshot = state / "params-integrity.json"

    monkeypatch.setattr(pig, "WATCHED_FILES", watched)
    monkeypatch.setattr(pig, "SNAPSHOT_PATH", snapshot)
    monkeypatch.setattr(pig, "STATUS_MD", status_md)
    monkeypatch.setattr(pig, "DISCORD_OUTBOX", outbox)
    return {"watched": watched, "status_md": status_md, "outbox": outbox, "snapshot": snapshot}


def _et(hour: int, minute: int, day: int = 18) -> datetime:
    return datetime(2026, 8, day, hour, minute, 0)


# --- 1. first tick of the session: snapshot, no alert ------------------------------------
def test_first_tick_takes_snapshot_no_alert(sandbox):
    result = pig.check(_et(9, 30))
    assert result["status"] == "SNAPSHOT_TAKEN"
    assert result["changed"] == []
    assert sandbox["snapshot"].exists()
    snap = json.loads(sandbox["snapshot"].read_text(encoding="utf-8"))
    assert snap["date"] == "2026-08-18"
    assert set(snap["hashes"]) == set(sandbox["watched"])
    # No alert on the very first tick — there is nothing yet to compare against.
    assert sandbox["status_md"].read_text(encoding="utf-8") == ""
    assert not sandbox["outbox"].exists()


# --- 2. unchanged files on a later tick: cheap, no parse, no alert ------------------------
def test_unchanged_files_same_session_is_ok_and_cheap(sandbox, monkeypatch):
    pig.check(_et(9, 30))  # baseline

    parse_calls = {"n": 0}
    real_load = pig._load_json

    def _counting_load(path):
        parse_calls["n"] += 1
        return real_load(path)

    monkeypatch.setattr(pig, "_load_json", _counting_load)

    result = pig.check(_et(9, 31))
    assert result == {"status": "OK", "changed": []}
    # THE hot-path claim, proven directly: a same-content tick must not parse ANY watched
    # file's JSON — only hash+compare. "Hash, don't deep-diff, on the hot path."
    assert parse_calls["n"] == 0
    assert sandbox["status_md"].read_text(encoding="utf-8") == ""
    assert not sandbox["outbox"].exists()


# --- 3. a real mid-session mutation: detected, per-key diff, both surfaces written --------
def test_mismatch_detected_with_per_key_diff_and_both_surfaces(sandbox):
    pig.check(_et(9, 30))  # baseline: {"tp1_premium_pct": 0.5, "premium_stop_pct": -0.5}

    # Simulate exactly the audited scenario: someone edits core_safe params.json mid-session.
    sandbox["watched"]["core_safe"].write_text(
        json.dumps({"tp1_premium_pct": 0.75, "new_knob": True}), encoding="utf-8")

    events = []
    result = pig.check(_et(11, 15), log_fn=events.append)

    assert result["status"] == "CHANGED"
    assert result["changed"] == ["core_safe"]
    diff = result["diff"]["core_safe"]
    assert diff["changed"] == {"tp1_premium_pct": {"old": 0.5, "new": 0.75}}
    assert diff["added"] == {"new_knob": True}
    assert diff["removed"] == {"premium_stop_pct": -0.5}

    # Ledger event: loud + distinctly typed (greppable, not a normal tick row).
    assert len(events) == 1
    assert events[0]["event"] == "RULE9_PARAMS_CHANGED_MID_SESSION"
    assert events[0]["files"] == ["core_safe"]

    # STATUS.md: per-key diff present, not just "something changed".
    status_text = sandbox["status_md"].read_text(encoding="utf-8")
    assert "RULE9 PARAMS CHANGED MID-SESSION" in status_text
    assert "tp1_premium_pct" in status_text and "0.5" in status_text and "0.75" in status_text
    assert "new_knob" in status_text
    assert "premium_stop_pct" in status_text

    # discord-outbox.jsonl: one new line, same schema self_check.py already writes.
    outbox_lines = sandbox["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(outbox_lines) == 1
    row = json.loads(outbox_lines[0])
    assert row["source"] == "params_integrity_guard"
    assert "RULE9" in row["message"]


# --- 4. repeat identical state (post-alert baseline) never re-alerts ---------------------
def test_repeat_identical_state_does_not_re_alert(sandbox):
    pig.check(_et(9, 30))
    sandbox["watched"]["core_safe"].write_text(json.dumps({"tp1_premium_pct": 0.75}), encoding="utf-8")
    pig.check(_et(11, 15))  # alerts once, rolls baseline forward
    lines_after_first_alert = sandbox["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines_after_first_alert) == 1

    # Same (now-current) content on every later tick this session — must NOT re-alert.
    for hh, mm in ((11, 16), (12, 0), (15, 55)):
        result = pig.check(_et(hh, mm))
        assert result == {"status": "OK", "changed": []}

    lines_final = sandbox["outbox"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines_final) == 1  # unchanged — no spam


# --- 5. a NEW session date is a fresh snapshot, never a false "mid-session" mismatch -----
def test_new_session_date_resnapshots_not_a_false_mismatch(sandbox):
    pig.check(_et(9, 30, day=18))  # Tuesday baseline

    # A legitimate WEEKEND edit changes the file before the next session even opens.
    sandbox["watched"]["core_safe"].write_text(json.dumps({"tp1_premium_pct": 0.9}), encoding="utf-8")

    result = pig.check(_et(9, 30, day=19))  # Wednesday, first tick of a NEW session
    assert result["status"] == "SNAPSHOT_TAKEN"  # not CHANGED — never alerted
    assert sandbox["status_md"].read_text(encoding="utf-8") == ""
    assert not sandbox["outbox"].exists()
    snap = json.loads(sandbox["snapshot"].read_text(encoding="utf-8"))
    assert snap["date"] == "2026-08-19"


# --- 6. change_events accumulates the day's full mutation history ------------------------
def test_change_events_accumulate_across_the_session(sandbox):
    pig.check(_et(9, 30))
    sandbox["watched"]["core_safe"].write_text(json.dumps({"tp1_premium_pct": 0.6}), encoding="utf-8")
    pig.check(_et(10, 0))
    sandbox["watched"]["core_bold"].write_text(json.dumps({"x": 1}), encoding="utf-8")
    pig.check(_et(13, 0))

    snap = json.loads(sandbox["snapshot"].read_text(encoding="utf-8"))
    assert len(snap["change_events"]) == 2
    assert snap["change_events"][0]["files"] == ["core_safe"]
    assert snap["change_events"][1]["files"] == ["core_bold"]


# --- 7. never raises: a malformed watched file fails open, never crashes the tick --------
def test_malformed_json_fails_open_never_raises(sandbox):
    pig.check(_et(9, 30))
    sandbox["watched"]["core_safe"].write_text("{not valid json", encoding="utf-8")
    result = pig.check(_et(9, 31))  # must not raise
    assert result["status"] in ("CHANGED", "OK", "ERROR")  # any well-formed result, no exception


# --- 8. never blocks: check() never returns anything a caller could mistake for a deny ---
def test_result_shape_has_no_deny_or_block_field(sandbox):
    """Codifies the "detect, never block" design decision: the return contract carries no
    allowed/denied/block-style field a future careless caller could wire into the trade
    gate by accident."""
    pig.check(_et(9, 30))
    sandbox["watched"]["core_safe"].write_text(json.dumps({"tp1_premium_pct": 0.6}), encoding="utf-8")
    result = pig.check(_et(9, 31))
    for banned_key in ("allowed", "denied", "block", "veto", "deny"):
        assert banned_key not in result


# --- 9. hermeticity: state_dir=... fully redirects every path, touches nothing else ------
def test_state_dir_param_redirects_every_path_no_module_global_touched(tmp_path, monkeypatch):
    """RED-PROOF FOR A REAL REGRESSION (2026-08-18): the first wiring pass called
    heartbeat_core.main() -> params_integrity_guard.check(et, log_fn=_log) with NO state
    awareness at all. Every test that drives hc.main() (which monkeypatches hc.STATE to a
    tmp_path for hermeticity, the established idiom in this test suite) silently did REAL
    file I/O against production automation/state/params.json and
    automation/overnight/STATUS.md — caught by test_fleet_tick_pairing_race_2026_08_01.py
    going RED. This test pins the fix directly: passing state_dir=<tmp> must touch ONLY
    paths under that tmp tree, never the module's own real-repo globals."""
    other_root = tmp_path / "isolated_state"
    other_root.mkdir()
    (other_root / "params.json").write_text(json.dumps({"k": 1}), encoding="utf-8")
    (other_root / "aggressive").mkdir()
    (other_root / "aggressive" / "params.json").write_text(json.dumps({"k": 1}), encoding="utf-8")
    (other_root / "fleet").mkdir()
    (other_root / "fleet" / "accounts.json").write_text(json.dumps({"k": 1}), encoding="utf-8")

    # Sabotage the REAL module globals with a probe that raises if ever touched — proves
    # state_dir fully bypasses them rather than merely shadowing part of the path set.
    poison = Path("Z:/should-never-be-touched/params.json")
    monkeypatch.setattr(pig, "WATCHED_FILES", {"core_safe": poison})
    monkeypatch.setattr(pig, "SNAPSHOT_PATH", poison)
    monkeypatch.setattr(pig, "STATUS_MD", poison)
    monkeypatch.setattr(pig, "DISCORD_OUTBOX", poison)

    result = pig.check(_et(9, 30), state_dir=other_root)
    assert result["status"] == "SNAPSHOT_TAKEN"
    assert (other_root / "params-integrity.json").exists()
    assert not poison.parent.exists()  # never even attempted the poisoned drive path

    # Force a real mismatch + alert, confirm STATUS.md/discord land ONLY under other_root.
    (other_root / "params.json").write_text(json.dumps({"k": 2}), encoding="utf-8")
    result2 = pig.check(_et(10, 0), state_dir=other_root)
    assert result2["status"] == "CHANGED"
    assert (other_root / "discord-outbox.jsonl").exists()
    # STATUS.md lives at state_dir.parent/"overnight"/STATUS.md, mirroring the real
    # automation/state + automation/overnight sibling layout.
    assert (other_root.parent / "overnight" / "STATUS.md").exists()


# --- 10. wiring: heartbeat_core.main() actually calls this every tick --------------------
def test_wiring_heartbeat_core_calls_check_every_tick():
    """RED before the wiring line existed in heartbeat_core.py's main() (AssertionError:
    'params_integrity_guard.check(' not found in main()'s source) — GREEN after. Pure AST
    source-text check (no heavy heartbeat_core import needed — mirrors
    test_heartbeat_core_no_trade_window.py / test_heartbeat_core_sight_timeouts.py's
    existing lightweight-inspection style for this same file)."""
    assert HEARTBEAT_CORE.exists(), f"missing live engine: {HEARTBEAT_CORE}"
    source = HEARTBEAT_CORE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(HEARTBEAT_CORE))
    main_fn = next((n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    assert main_fn is not None, "heartbeat_core.py has no main() — engine entry point missing"
    main_src = ast.get_source_segment(source, main_fn) or ""
    assert "params_integrity_guard" in main_src, (
        "heartbeat_core.main() must call params_integrity_guard.check(...) once per tick "
        "(RULE9 detector wiring) — import found in module but not called from main().")
    assert "params_integrity_guard.check(" in main_src, (
        "params_integrity_guard is referenced in main() but .check(...) is never called.")
    assert "state_dir=" in main_src, (
        "the call must pass state_dir=STATE -- omitting it reproduces the real 2026-08-18 "
        "test-leak regression (see test_state_dir_param_redirects_every_path_no_module_"
        "global_touched): any test that monkeypatches heartbeat_core.STATE for hermeticity "
        "would silently NOT redirect this detector, which would then touch real production "
        "automation/state/*.json and automation/overnight/STATUS.md during a test run.")

    # The call must be defensively wrapped — a visibility instrument raising must never
    # abort a live trading tick. A bare unguarded call at module scope of main() (no
    # surrounding try) would be a real regression risk; assert a `try` node encloses it.
    has_try_wrapped_call = any(
        isinstance(n, ast.Try) and "params_integrity_guard.check(" in (ast.get_source_segment(source, n) or "")
        for n in ast.walk(main_fn)
    )
    assert has_try_wrapped_call, (
        "params_integrity_guard.check(...) call in main() must be wrapped in try/except — "
        "a visibility instrument must fail open, never raise into the live tick.")
