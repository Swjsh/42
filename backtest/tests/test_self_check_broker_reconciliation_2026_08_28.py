"""Guard: self_check.check_broker_reconciliation -- the standing daily reconciliation
check (TASK B3). Lands a BROKEN/RED problem in STATUS.md's Known-broken section when
any active arm's ledger P&L diverges from real broker equity beyond tolerance; DEGRADED
(not BROKEN) on a live-fetch failure; and only recomputes once per ET calendar day.

No network calls: go_live_gate.reconciliation_criterion is monkeypatched directly, so
these tests are fast and deterministic regardless of live broker state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import self_check as sc  # noqa: E402
import go_live_gate as glg  # noqa: E402


def _fake_result(*, reconciled_map: dict) -> dict:
    per_arm = {}
    all_pass = True
    for arm, reconciled in reconciled_map.items():
        if reconciled is None:
            per_arm[arm] = {"reconciled": None, "note": "live fetch failed: HTTP 500"}
            all_pass = False
            continue
        per_arm[arm] = {
            "reconciled": reconciled,
            "diff_vs_fee_adjusted_ledger": 0.0 if reconciled else -74.27,
            "tolerance": 10.0,
            "window": ["2026-08-03", "2026-08-27"],
            "broker_pnl_sum": 290.0,
            "ledger_pnl_fee_adjusted": 364.27 if not reconciled else 290.0,
        }
        if not reconciled:
            all_pass = False
    return {"per_arm": per_arm, "pass": all_pass}


def test_all_reconciled_produces_no_problems(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    with patch.object(glg, "load_ledger_rows", return_value=[]), \
         patch.object(glg, "reconciliation_criterion",
                       return_value=_fake_result(reconciled_map={"safe-2": True, "safe-3": True})):
        problems = sc.check_broker_reconciliation(_FakeNow("2026-08-28"), force=True)
    assert problems == []
    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert written["checked_date_et"] == "2026-08-28"
    assert written["pass"] is True


def test_a_drifted_arm_produces_a_RED_broken_problem(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    with patch.object(glg, "load_ledger_rows", return_value=[]), \
         patch.object(glg, "reconciliation_criterion",
                       return_value=_fake_result(reconciled_map={"safe-2": True, "safe-3": False})):
        problems = sc.check_broker_reconciliation(_FakeNow("2026-08-28"), force=True)
    assert len(problems) == 1
    assert "safe-3" in problems[0]
    assert "-74.27" in problems[0] or "74.27" in problems[0]
    assert sc._problem_is_broken(problems[0]) is True, (
        "a genuine reconciliation drift must classify as BROKEN (RED), not DEGRADED -- "
        "it undermines trust in the exact ledger a go-live decision rests on"
    )


def test_a_fetch_failure_is_degraded_not_broken(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    with patch.object(glg, "load_ledger_rows", return_value=[]), \
         patch.object(glg, "reconciliation_criterion",
                       return_value=_fake_result(reconciled_map={"risky-1": None})):
        problems = sc.check_broker_reconciliation(_FakeNow("2026-08-28"), force=True)
    assert len(problems) == 1
    assert "risky-1" in problems[0]
    assert sc._problem_is_broken(problems[0]) is False, (
        "a transient fetch failure is not itself proof of a data drift -- DEGRADED, not BROKEN"
    )


def test_second_call_same_day_is_cached_and_skips_recompute(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    calls = {"n": 0}

    def _counting_criterion(rows):
        calls["n"] += 1
        return _fake_result(reconciled_map={"safe-2": True})

    with patch.object(glg, "load_ledger_rows", return_value=[]), \
         patch.object(glg, "reconciliation_criterion", side_effect=_counting_criterion):
        first = sc.check_broker_reconciliation(_FakeNow("2026-08-28"))
        second = sc.check_broker_reconciliation(_FakeNow("2026-08-28"))
    assert first == []
    assert second == []
    assert calls["n"] == 1, "a same-day second call must NOT re-hit the broker/recompute"


def test_a_new_day_forces_a_fresh_recompute(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    calls = {"n": 0}

    def _counting_criterion(rows):
        calls["n"] += 1
        return _fake_result(reconciled_map={"safe-2": True})

    with patch.object(glg, "load_ledger_rows", return_value=[]), \
         patch.object(glg, "reconciliation_criterion", side_effect=_counting_criterion):
        sc.check_broker_reconciliation(_FakeNow("2026-08-28"))
        sc.check_broker_reconciliation(_FakeNow("2026-08-29"))
    assert calls["n"] == 2, "a new ET calendar day must trigger a fresh recompute"


def test_an_unexpected_error_fails_open_never_raises(tmp_path, monkeypatch):
    state_path = tmp_path / "reconciliation-daily.json"
    monkeypatch.setattr(sc, "RECONCILIATION_STATE", state_path)
    with patch.object(glg, "load_ledger_rows", side_effect=RuntimeError("boom")):
        problems = sc.check_broker_reconciliation(_FakeNow("2026-08-28"), force=True)
    assert len(problems) == 1
    assert "RECONCILIATION CHECK ERROR" in problems[0]
    assert sc._problem_is_broken(problems[0]) is False, (
        "the check itself failing to run is not proof of a data drift -- DEGRADED, not BROKEN"
    )


class _FakeNow:
    """Minimal stand-in for et_clock.et_now()'s return value -- only strftime is used."""

    def __init__(self, date_str: str):
        self._date_str = date_str

    def strftime(self, fmt: str) -> str:
        if fmt == "%Y-%m-%d":
            return self._date_str
        return f"{self._date_str}T00:00:00"
