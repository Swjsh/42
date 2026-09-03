"""Guard for the 2026-09-03 `_is_transport_error` fix (conductor AFTERHOURS fire).

WHY THIS EXISTS
  broker-transport.jsonl real evidence (2026-09-01/02, 5 rows) showed a well-formed broker
  answer -- TastytradeError("Couldn't parse response: {'error_code': 'invalid_request',
  'error_description': 'User is not a TastyTrade customer'}") -- misclassified as
  outcome=transport_error via the "couldn't parse response" substring check, same as a raw
  HTML 502 gateway page. That:
    (a) burned ~13s per connect() retrying (1s+3s+9s backoff) a deterministic re-fail, and
    (b) buried a genuine account/entitlement-shaped message inside the generic "flaky
        gateway" bucket, where the original OAuth-race hypothesis
        (FUTURES-BROKER-CONNECT-FAILURE-RATE-ROOT-CAUSE, queue.md 2026-08-30) could never be
        refined against it -- every failure just read "transport_error" regardless of shape.

  The fix narrows "couldn't parse response" transport-classification to bodies that do NOT
  carry a structured `error_code` -- a genuine gateway/HTML/empty-body response has no such
  key; a real (if schema-mismatched) broker answer does.

RED-PROOF: run against the PRE-fix code (`git stash`) -- test_the_live_incident_text_is_now_
  classified_as_non_transport fails (asserts False, gets True); restore -> passes. The other
  three tests pin the invariants the fix must NOT regress.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("", "backtest"):
    _pp = str(REPO / _p) if _p else str(REPO)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from backtest.futures import tastytrade_paper as tp  # noqa: E402


class _FakeSdkError(Exception):
    """Stand-in for tastytrade.utils.TastytradeError -- avoids an SDK import dependency for
    this classification-only test; _is_transport_error only ever inspects repr()/str()."""


def test_the_live_incident_text_is_now_classified_as_non_transport():
    """THE bug: this exact live broker-transport.jsonl row text (2026-09-01T10:45:42 et al,
    5 occurrences) must no longer read as a transport failure."""
    exc = _FakeSdkError(
        "Couldn't parse response: {'error_code': 'invalid_request', "
        "'error_description': 'User is not a TastyTrade customer'}"
    )
    assert tp._is_transport_error(exc) is False


def test_html_502_gateway_page_still_classifies_as_transport():
    """MUST NOT regress -- the original 2026-08-29 fix's own live signature (a raw nginx 502
    page has no error_code key at all)."""
    exc = _FakeSdkError("Couldn't parse response: <html>502 Bad Gateway</html> nginx/1.31.0")
    assert tp._is_transport_error(exc) is True


def test_empty_body_parse_failure_still_classifies_as_transport():
    """No error_code anywhere in an empty/garbled body -- still transport noise."""
    exc = _FakeSdkError("Couldn't parse response: ")
    assert tp._is_transport_error(exc) is True


def test_a_different_structured_error_code_also_classifies_as_non_transport():
    """Not a one-off special case for 'User is not a TastyTrade customer' specifically -- ANY
    structured error_code body is a genuine broker answer, not noise."""
    exc = _FakeSdkError(
        "Couldn't parse response: {'error_code': 'invalid_price_increment', "
        "'error_description': 'Price must be in increments of $0.25 for this order.'}"
    )
    assert tp._is_transport_error(exc) is False


def test_connect_logs_auth_or_permission_error_outcome_for_the_live_incident_text(monkeypatch, tmp_path):
    """End-to-end: connect() must now log outcome=auth_or_permission_error (not
    transport_error) for this exact exception, and must NOT retry it 3x."""
    monkeypatch.setattr(tp, "BROKER_TRANSPORT_FILE", tmp_path / "broker-transport.jsonl")
    monkeypatch.setenv("TT_SECRET", "dummy")
    monkeypatch.setenv("TT_REFRESH", "dummy")

    exc = _FakeSdkError(
        "Couldn't parse response: {'error_code': 'invalid_request', "
        "'error_description': 'User is not a TastyTrade customer'}"
    )
    calls = {"n": 0}

    def _boom(fn, **kw):
        calls["n"] += 1
        raise exc

    monkeypatch.setattr(tp, "_with_retry", _boom)
    b = tp.TastytradeBroker(watch_only=False)
    ok = b.connect()

    assert ok is False
    assert calls["n"] == 1  # _with_retry itself owns internal retry; connect() calls it once
    assert b.last_failure_detail["outcome"] == "auth_or_permission_error"
