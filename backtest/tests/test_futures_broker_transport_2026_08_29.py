"""Guards for the 2026-08-29 transport-diagnosability fix.

WHY THIS EXISTS
  The MES mirror lane (armed 2026-08-20) has placed 8 order attempts, 0 placed. 7 of 8 rows
  in mirror-broker-orders.jsonl read {"order_ids": [], "placed": false} with NO reason field.
  automation/state/logs/futures-mirror-shadow.stderr.log shows the root cause is
  transport-layer sandbox flakiness (502 gateway pages, ReadTimeouts, connect failures) --
  and a SEPARATE bug (broker-probe.jsonl rows 20-21) shows a bare `except: H1_PERMISSIONS`
  mislabeled a network ReadTimeout as a permissions rejection, misleading three weeks of
  investigation.

  This file pins three independent fixes, entirely via monkeypatch/fakes -- NO network calls:
    1. backtest/futures/tastytrade_paper.py -- place_bracket legs and connect/get_positions/
       get_account_equity now retry transport-class failures (deterministic backoff) and
       ALWAYS journal a structured row to automation/state/futures/broker-transport.jsonl
       (bypassing the handler-less `log` object entirely) on any non-success outcome.
    2. setup/scripts/futures_broker_probe.py -- the verdict taxonomy now has a distinct
       H3_TRANSPORT bucket so a network timeout is never again reported as H1_PERMISSIONS.
    3. setup/scripts/futures_mirror_shadow.py -- a non-placement row now always carries a
       `failure_detail` field (sourced from the broker, or an explicit fallback string).

RED-PROOF: every test below was run against the PRE-fix code first (via `git stash`) and
  confirmed to fail for the reason its docstring states, then confirmed green after the fix.
  See the orchestrating session's report for the exact before/after pytest counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from backtest.futures import tastytrade_paper as tp  # noqa: E402

import futures_broker_probe as fbp  # noqa: E402
import futures_mirror_shadow as fms  # noqa: E402


# ═══════════════════════ shared fakes (self-contained -- this file owns its own
#                          copies, matching this repo's own stated convention: see
#                          futures_mirror_shadow.py's "REUSE DECISION" docstring) ═════════════
class _FakeOrder:
    def __init__(self, order_id):
        self.id = order_id


class _FakeResponse:
    """Mimics the tastytrade SDK's place_order() response shape."""
    def __init__(self, order=None, errors=None, warnings=None):
        self.order = order
        self.errors = errors
        self.warnings = warnings


class _FakeContract:
    """Builds a REAL tastytrade.order.Leg (not a bare dict) -- NewOrder validates its legs via
    pydantic, so a stand-in dict fails leg construction itself and masks the actual behavior
    under test. Matches test_tastytrade_paper_leg_failure_logging_2026_08_21.py's own fixture."""
    symbol = "MESZ9"

    def build_leg(self, qty, action):
        from tastytrade.instruments import InstrumentType
        from tastytrade.order import Leg
        return Leg(instrument_type=InstrumentType.FUTURE, symbol=self.symbol,
                   action=action, quantity=qty)


def _broker() -> tp.TastytradeBroker:
    b = tp.TastytradeBroker(watch_only=False)
    b._connected = True
    b._session = object()
    b._account = mock.Mock()
    b._front_month = lambda instrument: _FakeContract()
    return b


@pytest.fixture(autouse=True)
def _isolate_transport_file(monkeypatch, tmp_path):
    """Every test in this file must write into a tmp broker-transport.jsonl, never the real
    automation/state/futures/ tree -- BROKER_TRANSPORT_FILE is a module attribute computed
    once at import time, so patching STATE_DIR alone would not retarget it (same lesson
    test_futures_mirror_shadow.py's own _isolate_state fixture documents)."""
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")
    monkeypatch.setattr(tp.time, "sleep", lambda seconds: None)  # keep retries instant


def _read_transport_rows() -> list[dict]:
    if not tp.BROKER_TRANSPORT_FILE.exists():
        return []
    return [json.loads(line) for line in
           tp.BROKER_TRANSPORT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


# ═══════════════════════ 1. ReadTimeout during a leg -> transport_error row ═══════════════════
class TestLegTransportFailureLogged:
    def test_readtimeout_during_a_leg_lands_a_transport_error_row_with_real_error_class(self):
        """Live incident: str(exc) is EMPTY for httpx.ReadTimeout ('ReadTimeout: ' with
        nothing after the colon) -- the row's `error_class` must still carry the real type
        name, never an empty string, and `outcome` must be transport_error (not silently
        dropped, not misclassified as a leg rejection)."""
        broker = _broker()
        broker._account.place_order = mock.AsyncMock(side_effect=httpx.ReadTimeout(""))
        broker._account.get_live_orders = mock.AsyncMock(return_value=[])
        broker._account.get_positions = mock.AsyncMock(return_value=[])

        ids = broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

        assert ids == []
        rows = _read_transport_rows()
        entry_rows = [r for r in rows if r["call"] == "place_bracket_entry"]
        assert len(entry_rows) == 1, rows
        row = entry_rows[0]
        assert row["outcome"] == "transport_error"
        assert row["error_class"] == "ReadTimeout"
        assert row["error_class"] != ""
        assert row["ts_et"]   # non-empty ET timestamp

    def test_exhausted_transport_retry_makes_three_total_attempts(self):
        """Proves the retry loop actually retried (not just logged on the first failure) --
        3 total attempts to place_order for the leg, confirm-check called between them."""
        broker = _broker()
        broker._account.place_order = mock.AsyncMock(side_effect=httpx.ReadTimeout(""))
        broker._account.get_live_orders = mock.AsyncMock(return_value=[])
        broker._account.get_positions = mock.AsyncMock(return_value=[])

        broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

        # 3 legs (entry/tp1/stop, no runner) x 3 attempts each = 9 total place_order calls.
        assert broker._account.place_order.call_count == 9


# ═══════════════════════ 2. clean broker rejection -> leg_rejected, NOT retried ════════════════
class TestCleanRejectionNotRetried:
    def test_clean_rejection_logs_leg_rejected_and_is_never_retried(self):
        """A response that came BACK from the broker (no exception) carrying `errors` is a
        real answer, not a transport failure -- must be logged once as leg_rejected and MUST
        NOT trigger the retry loop at all (place_order called exactly once per leg)."""
        broker = _broker()
        broker._account.place_order = mock.AsyncMock(
            return_value=_FakeResponse(order=None, errors=["insufficient_buying_power"]))

        ids = broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

        assert ids == []
        # entry + tp1 + stop = 3 calls total, none retried (a clean, non-exception response
        # never enters the transport-retry branch at all).
        assert broker._account.place_order.call_count == 3

        rows = _read_transport_rows()
        entry_rows = [r for r in rows if r["call"] == "place_bracket_entry"]
        assert len(entry_rows) == 1, rows
        row = entry_rows[0]
        assert row["outcome"] == "leg_rejected"
        assert "insufficient_buying_power" in (row["detail"] or "")
        assert row["error_class"] is None    # no exception was ever raised for this outcome


# ═══════════════════════ 3 & 4. probe verdict taxonomy ═════════════════════════════════════════
class TestProbeVerdictTaxonomy:
    def test_readtimeout_maps_to_h3_transport_not_h1_permissions(self):
        """THE bug this fixes: broker-probe.jsonl rows 20-21 read "error": "ReadTimeout: "
        labelled H1_PERMISSIONS by the old bare `else`. A network timeout must now map to
        H3_TRANSPORT."""
        exc = httpx.ReadTimeout("")   # empty message -- matches the live incident exactly
        assert str(exc) == ""
        verdict = fbp._classify_probe_verdict(exc)
        assert verdict == "H3_TRANSPORT"
        assert verdict != "H1_PERMISSIONS"

    def test_gateway_502_html_body_maps_to_h3_transport(self):
        """The OTHER live transport signature: a raw nginx 502 HTML page fails JSON parsing
        inside tastytrade.utils.validate_response and gets wrapped in a generic
        TastytradeError -- must still classify as transport, not fall through to H1."""
        from tastytrade.utils import TastytradeError
        exc = TastytradeError("Couldn't parse response: <html>502 Bad Gateway</html> nginx/1.31.0")
        assert fbp._classify_probe_verdict(exc) == "H3_TRANSPORT"

    def test_genuine_permissions_error_still_maps_to_h1_permissions(self):
        """A REAL broker-answered rejection (TastytradeError carrying an actual code/message,
        no transport markers, not the session-not-active message) must still classify as
        H1_PERMISSIONS -- the fix narrows the bucket, it doesn't empty it."""
        from tastytrade.utils import TastytradeError
        exc = TastytradeError("forbidden: account is not approved for futures trading")
        assert fbp._classify_probe_verdict(exc) == "H1_PERMISSIONS"

    def test_session_not_active_behavior_is_preserved_exactly(self):
        """MUST NOT regress -- verified working live 2026-08-xx (a Sunday CME-closed probe)."""
        exc = RuntimeError("tif.futures_session_not_active: The Futures trading session is "
                          "not currently active.")
        verdict = fbp._classify_probe_verdict(exc)
        assert verdict == "SESSION_NOT_ACTIVE (inconclusive -- re-run while CME is open)"

    def test_totally_unrelated_exception_is_h4_unknown_not_h1(self):
        """Anything genuinely unclassifiable must never silently default to H1_PERMISSIONS --
        that bare-`else` behavior is exactly the bug this whole fix removes."""
        exc = AttributeError("'NoneType' object has no attribute 'front_month'")
        assert fbp._classify_probe_verdict(exc) == "H4_UNKNOWN"


# ═══════════════════════ 5. mirror non-placement row carries failure_detail ═══════════════════
class _FakeBrokerNoDetailAttr:
    """Simulates a broker returning an EMPTY id list with NO last_failure_detail attribute at
    all (the shape before this fix, or any duck-typed backend that never grew the field) --
    proves the mirror's own explicit fallback string fires rather than a KeyError."""
    def connect(self):
        return True

    def is_flat(self, instrument):
        return True

    def get_account_equity(self):
        return 2000.0

    def place_bracket(self, *a, **kw):
        return []


class _FakeBrokerWithDetail:
    """Simulates the NEW tastytrade_paper.py behavior: last_failure_detail is populated after
    a failed place_bracket call."""
    def __init__(self, detail):
        self.last_failure_detail = None
        self._detail = detail

    def connect(self):
        return True

    def is_flat(self, instrument):
        return True

    def get_account_equity(self):
        return 2000.0

    def place_bracket(self, *a, **kw):
        self.last_failure_detail = self._detail
        return []


class TestMirrorFailureDetail:
    @pytest.fixture(autouse=True)
    def _isolate_mirror_state(self, monkeypatch, tmp_path):
        state_dir = tmp_path / "futures"
        monkeypatch.setattr(fms, "STATE_DIR", state_dir)
        monkeypatch.setattr(fms, "BROKER_ORDERS_FILE", state_dir / "mirror-broker-orders.jsonl")
        monkeypatch.setenv("MIRROR_ARMED", "1")

    def _sig_and_pos(self, now_et):
        # 2026-08-20 is a Thursday (a real CME session window) -- a weekend date pre-emptively
        # rejects via the risk rails' session_window check before place_bracket is ever
        # reached, which would silently defeat these tests (matches the existing armed-
        # execution test fixture in test_futures_mirror_shadow.py's TestArmedExecution).
        sig = {"signal_ref": "long|2026-08-20T10:00", "direction": "long",
              "source_arms": ["safe-1"], "setup_name": "TEST"}
        pos = fms.open_mirror_position(sig, entry_price=6000.0, atr=5.0, now_et=now_et)
        return sig, pos

    def test_no_last_failure_detail_attr_falls_back_to_explicit_unknown_string(self, monkeypatch):
        fake = _FakeBrokerNoDetailAttr()
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        now_et = __import__("datetime").datetime(2026, 8, 20, 10, 0, 0)
        sig, pos = self._sig_and_pos(now_et)
        result = fms._broker_execute_entry(sig, pos, now_et)

        assert result["placed"] is False
        assert result["failure_detail"] == "unknown_no_detail_from_broker"
        rows = [json.loads(l) for l in
               fms.BROKER_ORDERS_FILE.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["failure_detail"] == "unknown_no_detail_from_broker"

    def test_broker_supplied_failure_detail_is_carried_through_verbatim(self, monkeypatch):
        detail = {"instrument": "MES", "placed_ids": [], "leg_failures": ["place_bracket_entry"]}
        fake = _FakeBrokerWithDetail(detail)
        import futures.futures_trader_core as ftc
        monkeypatch.setattr(ftc, "make_broker", lambda backend: fake)

        now_et = __import__("datetime").datetime(2026, 8, 20, 10, 0, 0)
        sig, pos = self._sig_and_pos(now_et)
        result = fms._broker_execute_entry(sig, pos, now_et)

        assert result["placed"] is False
        assert result["failure_detail"] == detail
        assert result["failure_detail"] != ""
        assert result["failure_detail"] is not None


# ═══════════════════════ 6. entry-leg duplicate-order safety ═══════════════════════════════════
class TestEntryLegDuplicateOrderSafety:
    def test_entry_leg_retry_does_not_fire_when_landed_state_cannot_be_confirmed(self):
        """CRITICAL SAFETY: a transport failure means the RESPONSE was lost, not necessarily
        the REQUEST -- the order may already be resting/filled at the broker. If the
        confirm-before-retry query itself fails (broker unreachable again), the entry leg
        must be ABANDONED, never retried -- a duplicate live order is worse than one missed
        diagnostic retry. place_order for the entry leg must be called exactly ONCE."""
        broker = _broker()
        responses = [
            httpx.ReadTimeout(""),                       # entry leg: transport failure
            _FakeResponse(order=_FakeOrder("tp1-1")),     # tp1 leg: succeeds normally
            _FakeResponse(order=_FakeOrder("stop-1")),    # stop leg: succeeds normally
        ]
        broker._account.place_order = mock.AsyncMock(side_effect=responses)
        # The confirmation query itself is UNREACHABLE (same broker outage) -> ambiguous.
        broker._account.get_live_orders = mock.AsyncMock(
            side_effect=RuntimeError("cannot reach broker to confirm"))
        broker._account.get_positions = mock.AsyncMock(
            side_effect=RuntimeError("cannot reach broker to confirm"))

        ids = broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

        assert broker._account.place_order.call_count == 3   # entry(1) + tp1(1) + stop(1)
        assert ids == ["tp1-1", "stop-1"]                      # entry missing, others fine

        rows = _read_transport_rows()
        entry_rows = [r for r in rows if r["call"] == "place_bracket_entry"]
        assert len(entry_rows) == 1, rows
        assert entry_rows[0]["outcome"] == "transport_error_not_retried_ambiguous"
        assert entry_rows[0]["detail"] == "confirmation_query_itself_failed"

    def test_entry_leg_retries_normally_when_confirm_check_proves_it_did_not_land(self):
        """Sanity counterpart: when the confirm-check CAN positively prove the order did not
        land (empty live orders, empty positions), the entry leg is safe to retry -- this is
        NOT the ambiguous path, so it must exhaust all 3 attempts, not abandon after 1."""
        broker = _broker()
        broker._account.place_order = mock.AsyncMock(side_effect=httpx.ReadTimeout(""))
        broker._account.get_live_orders = mock.AsyncMock(return_value=[])
        broker._account.get_positions = mock.AsyncMock(return_value=[])

        broker.place_bracket("MES", "BUY", 2, 6000.0, 6010.0, 5990.0)

        entry_calls_expected = 3   # confirmed-not-landed -> retries all the way to exhaustion
        assert broker._account.place_order.call_count == entry_calls_expected * 3  # 3 legs

        rows = _read_transport_rows()
        entry_rows = [r for r in rows if r["call"] == "place_bracket_entry"]
        assert entry_rows[0]["outcome"] == "transport_error"   # exhausted, not ambiguous
