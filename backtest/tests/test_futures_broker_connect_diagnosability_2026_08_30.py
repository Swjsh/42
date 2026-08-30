"""Guard for the 2026-08-30 connect()-diagnosability fix.

WHY THIS EXISTS
  self_check.py flagged FUTURES-HEALTH RED on 2026-08-30: the real-fill broker lane
  (Gamma_FuturesBrokerLane, trader-broker/decisions.jsonl) went from a ~5% baseline
  connect-failure rate to 76% over 2026-08-24 -> 2026-08-28, with ZERO recoverable
  reason anywhere on disk. Root cause: TastytradeBroker.connect()'s except blocks called
  only `log.error(...)` -- and nothing in this lane's real deployment (pythonw, no
  console, no logging.Handler ever attached) ever reads Python's `logging` output. The
  exact exception class/message that would explain WHY auth is failing was computed and
  then discarded on every single failed tick (C7: silent success/failure -- audit
  outputs, not exit codes/log calls that go nowhere).

  Fix: connect()'s except blocks now (a) set self.last_failure_detail (the SAME
  mechanism place_bracket_entry already uses and futures_mirror_shadow.py already reads
  on empty order-id lists), and (b) always append one row to broker-transport.jsonl via
  the existing _log_broker_transport helper -- for BOTH the transport-error case (already
  covered before this fix) and the non-transport auth/config case (NOT covered before
  this fix, and exactly the case a repo-wide grep confirms produced zero
  broker-transport.jsonl rows despite 76% of ticks failing to connect on 2026-08-28).
  futures_trader_core.run_tick() then carries connect_failure through into the ledger
  row itself, so the NEXT investigation reads the reason straight off decisions.jsonl
  without needing a live reproduction.

  This is diagnostics-only: connected=False still refuses to act/journal as a BROKER
  lane exactly as before (see test_futures_trader_core.py's existing
  test_broker_not_connected_refuses_to_act_or_journal, unchanged) -- zero decision-logic
  change, purely additive visibility.

RED-PROOF: every test below was confirmed to fail against the pre-fix connect() (which
  never sets last_failure_detail and never logs a non-transport row) before the fix
  landed, then confirmed green after.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from backtest.futures import tastytrade_paper as tp  # noqa: E402
from backtest.futures import futures_trader_core as ftc  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_transport_file(monkeypatch, tmp_path):
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")
    monkeypatch.setattr(tp.time, "sleep", lambda seconds: None)


def _read_transport_rows() -> list[dict]:
    if not tp.BROKER_TRANSPORT_FILE.exists():
        return []
    return [json.loads(line) for line in
            tp.BROKER_TRANSPORT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestMissingEnvVar:
    def test_missing_env_var_sets_last_failure_detail(self, monkeypatch):
        monkeypatch.delenv("TT_SECRET", raising=False)
        monkeypatch.delenv("TT_REFRESH", raising=False)
        b = tp.TastytradeBroker(watch_only=False)
        ok = b.connect()
        assert ok is False
        assert b.last_failure_detail is not None
        assert b.last_failure_detail["outcome"] == "missing_env_var"
        assert b.last_failure_detail["call"] == "connect"

    def test_missing_env_var_lands_a_broker_transport_row(self, monkeypatch):
        # BEFORE this fix: a KeyError from connect() logged via log.error() only --
        # zero rows in broker-transport.jsonl, matching the real repo's empty file.
        monkeypatch.delenv("TT_SECRET", raising=False)
        monkeypatch.delenv("TT_REFRESH", raising=False)
        b = tp.TastytradeBroker(watch_only=False)
        b.connect()
        rows = _read_transport_rows()
        assert len(rows) == 1
        assert rows[0]["call"] == "connect"
        assert rows[0]["outcome"] == "missing_env_var"
        assert rows[0]["error_class"] == "KeyError"


class TestNonTransportConnectFailure:
    """A genuine auth/permissions failure (not a network blip) -- the class of error
    _is_transport_error() deliberately does NOT match, and which the pre-fix code
    therefore never wrote to broker-transport.jsonl at all."""

    def test_non_transport_exception_sets_auth_or_permission_error(self, monkeypatch):
        monkeypatch.setenv("TT_SECRET", "dummy")
        monkeypatch.setenv("TT_REFRESH", "dummy")

        def _boom(fn):
            raise PermissionError("invalid_grant: refresh token revoked")

        monkeypatch.setattr(tp, "_with_retry", _boom)
        b = tp.TastytradeBroker(watch_only=False)
        ok = b.connect()
        assert ok is False
        assert b.last_failure_detail["outcome"] == "auth_or_permission_error"
        assert b.last_failure_detail["error_class"] == "PermissionError"
        assert "refresh token revoked" in b.last_failure_detail["error_repr"]

    def test_non_transport_exception_still_lands_a_broker_transport_row(self, monkeypatch):
        monkeypatch.setenv("TT_SECRET", "dummy")
        monkeypatch.setenv("TT_REFRESH", "dummy")
        monkeypatch.setattr(tp, "_with_retry",
                             lambda fn: (_ for _ in ()).throw(PermissionError("nope")))
        b = tp.TastytradeBroker(watch_only=False)
        b.connect()
        rows = _read_transport_rows()
        assert len(rows) == 1
        assert rows[0]["outcome"] == "auth_or_permission_error"
        assert rows[0]["error_class"] == "PermissionError"


class TestSuccessClearsStaleFailure:
    def test_successful_connect_clears_a_prior_failure_detail(self, monkeypatch):
        monkeypatch.setenv("TT_SECRET", "dummy")
        monkeypatch.setenv("TT_REFRESH", "dummy")
        b = tp.TastytradeBroker(watch_only=False)
        b.last_failure_detail = {"call": "connect", "outcome": "stale_from_last_tick"}

        class _FakeAcct:
            account_number = "TEST123"

        monkeypatch.setattr(tp, "_with_retry", lambda fn: (object(), _FakeAcct()))
        ok = b.connect()
        assert ok is True
        assert b.last_failure_detail is None


class TestLedgerCarriesConnectFailure:
    """futures_trader_core.run_tick() must surface the broker's own last_failure_detail
    on a not-connected BROKER tick -- this is the field the next investigation reads
    instead of re-deriving the root cause from scratch."""

    def test_not_connected_ledger_row_carries_connect_failure(self, monkeypatch, tmp_path):
        class _FakeBroker:
            last_failure_detail = {
                "call": "connect", "outcome": "auth_or_permission_error",
                "error_class": "PermissionError", "error_repr": "invalid_grant",
            }

            def connect(self):
                return False

        monkeypatch.setattr(ftc, "make_broker", lambda backend: _FakeBroker())
        monkeypatch.setattr(ftc, "backend_name", lambda broker: "TastytradeBroker")
        monkeypatch.setattr(ftc, "is_simulated", lambda broker: False)

        rec = ftc.run_tick("MES", backend="tastytrade", state_dir=tmp_path)
        assert rec["action"] == "HOLD"
        assert rec["reason"] == "broker_not_connected"
        assert rec["connect_failure"]["outcome"] == "auth_or_permission_error"
        assert rec["connect_failure"]["error_class"] == "PermissionError"

    def test_no_last_failure_detail_attr_carries_none_not_a_crash(self, monkeypatch, tmp_path):
        class _BareBroker:
            def connect(self):
                return False

        monkeypatch.setattr(ftc, "make_broker", lambda backend: _BareBroker())
        monkeypatch.setattr(ftc, "backend_name", lambda broker: "BareBroker")
        monkeypatch.setattr(ftc, "is_simulated", lambda broker: False)

        rec = ftc.run_tick("MES", backend="tastytrade", state_dir=tmp_path)
        assert rec["action"] == "HOLD"
        assert rec["reason"] == "broker_not_connected"
        assert rec["connect_failure"] is None
