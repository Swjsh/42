"""Guard: regime_stamp.py's file writes must be atomic + retry-resilient.

Root cause (2026-08-04): a direct in-place ``Path.write_bytes`` hit a one-off
``OSError: [Errno 22] Invalid argument`` at 08:22 ET on this OneDrive-synced
repo, leaving regime-stamp.json frozen on the PRIOR day's content for 24h+
while Task Scheduler still reported LastTaskResult=0 (the fire-and-forget
``run_exe_hidden.vbs`` launcher never propagates the child's real exit code).
self_check's REGIME-STAMP DRIFT check caught the *consequence* same morning;
this guard pins the *cause*-side fix: writes must go through a temp-file +
os.replace atomic swap with a few retries on transient OSError, never a bare
in-place ``write_bytes`` that can be caught mid-write by a competing lock.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "automation" / "scripts" / "regime_stamp.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("regime_stamp_under_test", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def rs():
    return _load_module()


def test_source_never_calls_write_bytes_directly_on_target_paths(rs):
    """The two live-state targets must go through the atomic-retry helper,
    never a bare Path.write_bytes on STAMP_PATH/BIAS_PATH (the exact call
    shape that raised the uncaught OSError this fire root-caused)."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "STAMP_PATH.write_bytes(" not in src, (
        "STAMP_PATH must be written via _atomic_write_bytes_with_retry, not a "
        "direct write_bytes call (that call shape is what raised the uncaught "
        "OSError on 2026-08-04)")
    assert "BIAS_PATH.write_bytes(" not in src, (
        "BIAS_PATH must be written via _atomic_write_bytes_with_retry, not a "
        "direct write_bytes call")
    assert src.count("_atomic_write_bytes_with_retry(") >= 3, (
        "expected the helper definition + 2 call sites (stamp + bias patch)")


def test_atomic_write_creates_target_with_exact_bytes(rs, tmp_path):
    target = tmp_path / "out.json"
    payload = b'{"a": 1}\n'
    rs._atomic_write_bytes_with_retry(target, payload)
    assert target.read_bytes() == payload


def test_atomic_write_leaves_no_temp_file_behind_on_success(rs, tmp_path):
    target = tmp_path / "out.json"
    rs._atomic_write_bytes_with_retry(target, b"{}")
    leftovers = list(tmp_path.glob(f".{target.name}.*.tmp"))
    assert leftovers == [], f"temp file(s) not cleaned up: {leftovers}"


def test_atomic_write_retries_past_a_transient_failure(rs, tmp_path, monkeypatch):
    target = tmp_path / "out.json"
    calls = {"n": 0}
    real_replace = rs.os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(22, "Invalid argument")  # exact errno from the incident
        return real_replace(src, dst)

    monkeypatch.setattr(rs.os, "replace", flaky_replace)
    monkeypatch.setattr(rs.time, "sleep", lambda *_a, **_k: None)  # keep test fast

    rs._atomic_write_bytes_with_retry(target, b"payload")
    assert target.read_bytes() == b"payload"
    assert calls["n"] == 2, "expected exactly one retry after the injected failure"


def test_atomic_write_raises_the_real_error_after_exhausting_retries(rs, tmp_path, monkeypatch):
    target = tmp_path / "out.json"

    def always_fails(src, dst):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(rs.os, "replace", always_fails)
    monkeypatch.setattr(rs.time, "sleep", lambda *_a, **_k: None)

    with pytest.raises(OSError) as exc_info:
        rs._atomic_write_bytes_with_retry(target, b"payload", attempts=3)
    assert exc_info.value.errno == 22
    assert not target.exists()


def test_main_writes_todays_date_not_a_stale_date(rs, tmp_path, monkeypatch):
    """End-to-end: main() must stamp the CURRENT ET date, proving the write
    path (atomic helper) actually lands fresh content -- this is the exact
    symptom from the incident (file frozen on the prior trading day)."""
    import datetime as dt

    fake_state_dir = tmp_path / "state"
    fake_stamp = fake_state_dir / "regime-stamp.json"
    fake_bias = fake_state_dir / "today-bias.json"
    fake_state_dir.mkdir(parents=True)
    fake_bias.write_text(json.dumps({"date": "placeholder"}), encoding="utf-8")

    monkeypatch.setattr(rs, "STATE_DIR", fake_state_dir)
    monkeypatch.setattr(rs, "STAMP_PATH", fake_stamp)
    monkeypatch.setattr(rs, "BIAS_PATH", fake_bias)
    monkeypatch.setattr(rs, "rebuild_artifact", lambda: True)

    fake_artifact = {
        "spec_version": "1.0.0",
        "distribution": {"full_pct": {"range-chop": 40.0}, "n_assignable": 100},
        "days": {
            "2026-08-01": {"archetype": "gap-go", "dow": "Sat", "range_pct": 1.0,
                            "gap_pct": 0.1, "close_loc": 0.5, "vix_open": 15.0,
                            "vix_close": 15.5, "session": "full"},
        },
    }
    monkeypatch.setattr(rs, "ART_PATH", tmp_path / "artifact.json")
    (tmp_path / "artifact.json").write_text(json.dumps(fake_artifact), encoding="utf-8")

    today_et = dt.datetime.now(tz=rs.ET).date()
    rc = rs.main()
    assert rc == 0
    written = json.loads(fake_stamp.read_text(encoding="utf-8"))
    assert written["date"] == today_et.isoformat(), (
        "regime-stamp.json must be stamped with TODAY's ET date, not stale content")
