"""Guard: an engine that was dark during RTH must OBSERVE before it may buy.

THE INCIDENT (2026-08-14). The box slept 04:27-09:46 ET (one 5h19m hole in the launcher log).
On wake, the engine's FIRST look at the day -- key levels 322 minutes stale, no premarket, no
warmup ticks -- was a bull entry 10 seconds into its first tick: the first core-decisions row
of the day is 09:46:12 action=PLACED. It bought the top of a 1.1-point range, into
INTRADAY_RTH_HIGH, after a +3.14 prior day. All five arms followed the shared signal: -$1,569.

THE GUARD. At entry-attempt time, if this account's newest PRIOR core-decisions row is more
than COLD_OPEN_GAP_MIN old, the entry is refused (SKIP_COLD_OPEN) and a warmup marker holds
entries closed for COLD_OPEN_WARMUP_MIN while normal ticks re-populate the ledger.

WHY NORMAL DAYS NEVER TRIP IT (the design's load-bearing property): during RTH the engine
writes a row EVERY ~60s tick, and entries are only legal from 09:35 -- by which time rows exist
from 09:30 onward. The overnight/weekend gap is invisible because the newest PRIOR row at any
legal entry time is ~1 minute old. Only a genuine RTH dark gap (sleep, crash, block) trips it.

Entry path only: exits, the kill-switch, and the EOD flatten run in run_account BEFORE any
verdict reaches _execute, so this guard structurally cannot touch them.
KILL: params cold_open_guard_enabled=false (single key).
"""

from __future__ import annotations

import datetime as dtm
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HC = REPO / "setup" / "scripts" / "heartbeat_core.py"

NOW = dtm.datetime(2026, 8, 14, 9, 46, 12)
ON = {"cold_open_guard_enabled": True}


def _row(ts: str, acct: str = "safe") -> str:
    return json.dumps({"account": acct, "ts_et": ts, "action": "HOLD"})


@pytest.fixture()
def hc(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("_hc_cold_probe", HC)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_hc_cold_probe"] = m
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "LEDGER", tmp_path / "core-decisions.jsonl")
    return m


def test_the_incident_is_blocked(hc, tmp_path):
    """THE REGRESSION: newest prior row = yesterday 15:55, entry attempt 09:46:12."""
    (tmp_path / "core-decisions.jsonl").write_text(_row("2026-08-13T15:55:04") + "\n", encoding="utf-8")
    reason = hc._cold_open_block("safe", "safe-2", NOW, ON)
    assert reason is not None, (
        "the exact 2026-08-14 wake-storm state is not blocked -- the engine can again buy the "
        "top of the range 10 seconds after waking from a 5-hour sleep")
    assert "dark" in reason


def test_warmup_marker_holds_then_releases(hc, tmp_path):
    led = tmp_path / "core-decisions.jsonl"
    led.write_text(_row("2026-08-13T15:55:04") + "\n", encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", NOW, ON) is not None          # trips + writes marker
    assert hc._cold_open_block("safe", "safe-2", NOW + dtm.timedelta(seconds=90), ON) is not None
    # after expiry, ticks have refreshed the ledger -> allowed
    led.write_text(_row("2026-08-13T15:55:04") + "\n" + _row("2026-08-14T09:48:30") + "\n",
                   encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", NOW + dtm.timedelta(minutes=4), ON) is None


def test_normal_day_and_monday_open_are_NEVER_blocked(hc, tmp_path):
    """The load-bearing false-positive check: a weekend gap is invisible because today's rows
    exist from 09:30 before any entry is legal. If this fails, the guard blocks every open."""
    lines = [_row("2026-08-11T15:55:04")] + [_row(f"2026-08-14T09:{m:02d}:05") for m in range(30, 51)]
    (tmp_path / "core-decisions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", dtm.datetime(2026, 8, 14, 9, 51, 10), ON) is None


def test_accounts_are_scoped_independently(hc, tmp_path):
    """bold ticking + safe dark -> only safe is blocked."""
    lines = [_row("2026-08-13T15:55:04", "safe")] + \
            [_row(f"2026-08-14T09:{m:02d}:05", "bold") for m in range(30, 46)]
    (tmp_path / "core-decisions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", NOW, ON) is not None
    assert hc._cold_open_block("bold", "bold-2", NOW, ON) is None


def test_single_key_kill_switch(hc, tmp_path):
    (tmp_path / "core-decisions.jsonl").write_text(_row("2026-08-13T15:55:04") + "\n", encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", NOW, {"cold_open_guard_enabled": False}) is None


def test_fail_open_on_missing_or_empty_ledger(hc, tmp_path, monkeypatch):
    """A fresh install / corrupt ledger must not brick entries -- the guard is an extra safety,
    not the authority."""
    monkeypatch.setattr(hc, "LEDGER", tmp_path / "absent.jsonl")
    assert hc._cold_open_block("safe", "safe-2", NOW, ON) is None
    (tmp_path / "absent.jsonl").write_text("not json\n\n", encoding="utf-8")
    assert hc._cold_open_block("safe", "safe-2", NOW, ON) is None


def test_wired_into_execute_before_the_claim():
    """The refusal must exist on the entry path with its own SKIP status, BEFORE the claim gate
    so a cold-open refusal never consumes the 180s claim window."""
    code = "\n".join(l for l in HC.read_text(encoding="utf-8").splitlines()
                     if not l.strip().startswith("#"))
    assert "SKIP_COLD_OPEN" in code, "_execute lost the SKIP_COLD_OPEN refusal"
    # EXACT-LINE assert, not a substring: mutation testing showed
    # `_cold_reason = None and _cold_open_block(...)` slips past a loose contains-check while
    # disabling the guard entirely (fifth instance of claim-vs-retraction this week).
    assert "    _cold_reason = _cold_open_block(account, arm, _now_exec, params)" in code, (
        "the guard call in _execute is no longer the exact live pattern -- it may have been "
        "disabled in place (e.g. `None and _cold_open_block(...)`)")
    i_cold = code.index("_cold_reason = _cold_open_block")
    i_use = code.index("if _cold_reason:")
    i_claim = code.index("if _claim_active(arm, symbol")
    assert i_cold < i_use < i_claim, "cold-open check no longer precedes the claim gate"


def test_thresholds_are_sane():
    """Gap threshold must exceed several tick intervals (no jitter trips) and warmup must be
    short enough not to sit out a real setup for long."""
    spec = importlib.util.spec_from_file_location("_hc_cold_c", HC)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_hc_cold_c"] = m
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    assert 5.0 <= m.COLD_OPEN_GAP_MIN <= 30.0
    assert 1.0 <= m.COLD_OPEN_WARMUP_MIN <= 10.0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
