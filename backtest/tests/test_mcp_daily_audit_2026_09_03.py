"""Guard: mcp_daily_audit.py -- the deterministic, $0 replacement for the
LLM-driven `Gamma_McpDailyAudit` fire.

THE INCIDENT (2026-09-03): the free-model `mcp-weekly-audit.md` prompt wrote TWO
false BLOCKERs into STATUS.md `## Known broken` in one night -- a RED at 00:03 ET
("Alpaca Safe and Bold both 401 Unauthorized ... BLOCKER") and a YELLOW at
07:48 ET ("404 (credential/account mismatch)") -- while a direct REST
`GET /v2/account` with the SAME `.mcp.json` keys returned 200/ACTIVE for both
accounts throughout, and the live engine (which trades via direct REST, not MCP)
never lost a tick. This suite pins the deterministic script's classification
rules so it can never repeat that failure mode: a definitive mismatch is RED
immediately (a config fact), but a bare unreachable/401 read is only a CANDIDATE
until it is confirmed by a SECOND probe 30s later -- a single transient miss
recovers to YELLOW, never RED. TradingView and the MCP-server-process checks are
report-only and can never escalate to RED (the live engine does not depend on
either).

All HTTP and WMI calls are injected fakes -- these tests never touch the network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import mcp_daily_audit as mda  # noqa: E402
import status_known_broken as skb  # noqa: E402

KNOWN_BROKEN = "## Known broken"

FAKE_SAFE_ACCT = "ACCT_SAFE_TEST"
FAKE_BOLD_ACCT = "ACCT_BOLD_TEST"
FAKE_SAFE_KEY = "TESTKEY_SAFE_SECRET_VALUE"
FAKE_BOLD_KEY = "TESTKEY_BOLD_SECRET_VALUE"
FAKE_SAFE_SECRET = "TESTSECRET_SAFE_do_not_leak"
FAKE_BOLD_SECRET = "TESTSECRET_BOLD_do_not_leak"


# ---------------------------------------------------------------------------
# Response builders (match _http_get_json's return contract)
# ---------------------------------------------------------------------------

def _ok_account(acct: str, status: str = "ACTIVE") -> dict:
    return {"reachable": True, "status_code": 200,
            "data": {"account_number": acct, "status": status}, "error": None}


def _ok_clock() -> dict:
    return {"reachable": True, "status_code": 200, "data": {"is_open": False}, "error": None}


def _fail_401() -> dict:
    return {"reachable": False, "status_code": 401, "data": None, "error": "HTTP 401"}


def _ok_tv() -> dict:
    return {"reachable": True, "status_code": 200, "data": {"Browser": "Chrome/1.0"}, "error": None}


def _fail_tv() -> dict:
    return {"reachable": False, "status_code": None, "data": None, "error": "Connection refused"}


def _make_fake_http(script: dict):
    """script: {key: [resp, resp, ...]} -- key is '<APCA-API-KEY-ID>:account',
    '<APCA-API-KEY-ID>:clock', or 'tv'. Repeats the last response once the
    script for a key is exhausted. Records call counts on `.calls`."""
    calls: dict = {}

    def fake(url: str, headers: dict, timeout: float = 5.0) -> dict:
        if "9222" in url:
            key = "tv"
        elif "/v2/clock" in url:
            key = f"{headers.get('APCA-API-KEY-ID', '')}:clock"
        else:
            key = f"{headers.get('APCA-API-KEY-ID', '')}:account"
        idx = calls.get(key, 0)
        calls[key] = idx + 1
        responses = script.get(key, [])
        if idx < len(responses):
            return responses[idx]
        return responses[-1] if responses else {"reachable": True, "status_code": 200, "data": {}, "error": None}

    fake.calls = calls
    return fake


class _SleepSpy:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def _fake_creds():
    return {
        "safe": {"ALPACA_API_KEY": FAKE_SAFE_KEY, "ALPACA_SECRET_KEY": FAKE_SAFE_SECRET,
                  "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"},
        "bold": {"ALPACA_API_KEY": FAKE_BOLD_KEY, "ALPACA_SECRET_KEY": FAKE_BOLD_SECRET,
                  "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"},
    }


def _fake_expected():
    return {"safe": FAKE_SAFE_ACCT, "bold": FAKE_BOLD_ACCT}


def _happy_script(**overrides) -> dict:
    base = {
        f"{FAKE_SAFE_KEY}:account": [_ok_account(FAKE_SAFE_ACCT)],
        f"{FAKE_SAFE_KEY}:clock": [_ok_clock()],
        f"{FAKE_BOLD_KEY}:account": [_ok_account(FAKE_BOLD_ACCT)],
        f"{FAKE_BOLD_KEY}:clock": [_ok_clock()],
        "tv": [_ok_tv()],
    }
    base.update(overrides)
    return base


def _run(script: dict, *, ps_count: str = "2", monkeypatch=None):
    assert monkeypatch is not None
    monkeypatch.setattr(mda, "load_mcp_creds", _fake_creds)
    monkeypatch.setattr(mda, "expected_accounts", _fake_expected)
    fake_http = _make_fake_http(script)
    sleep_spy = _SleepSpy()
    result = mda.run_audit(http_get=fake_http, sleep_fn=sleep_spy, ps_runner=lambda ps: ps_count)
    return result, sleep_spy, fake_http


# ---------------------------------------------------------------------------
# 1. 200 + ACTIVE + matching id -> GREEN
# ---------------------------------------------------------------------------

def test_all_healthy_is_green_and_never_sleeps(monkeypatch):
    result, sleep_spy, _ = _run(_happy_script(), monkeypatch=monkeypatch)
    assert result["verdict"] == "GREEN"
    assert result["alpaca_safe"]["verdict"] == "ok"
    assert result["alpaca_bold"]["verdict"] == "ok"
    assert sleep_spy.calls == [], "a healthy first read must never trigger the 30s retry wait"


# ---------------------------------------------------------------------------
# 2. 401 twice -> RED (confirmed transient failure)
# ---------------------------------------------------------------------------

def test_401_confirmed_twice_is_red(monkeypatch):
    script = _happy_script(**{f"{FAKE_SAFE_KEY}:account": [_fail_401(), _fail_401()]})
    result, sleep_spy, _ = _run(script, monkeypatch=monkeypatch)
    assert result["verdict"] == "RED"
    assert result["alpaca_safe"]["verdict"] == "red"
    assert sleep_spy.calls == [mda.RETRY_WAIT_SECONDS], "must retry exactly once, 30s later, before calling RED"


# ---------------------------------------------------------------------------
# 3. 401 once then 200 -> YELLOW (transient, recovered)
# ---------------------------------------------------------------------------

def test_401_once_then_recovered_is_yellow_not_red(monkeypatch):
    script = _happy_script(**{
        f"{FAKE_SAFE_KEY}:account": [_fail_401(), _ok_account(FAKE_SAFE_ACCT)],
    })
    result, sleep_spy, _ = _run(script, monkeypatch=monkeypatch)
    assert result["verdict"] == "YELLOW"
    assert result["alpaca_safe"]["verdict"] == "yellow"
    assert sleep_spy.calls == [mda.RETRY_WAIT_SECONDS]


# ---------------------------------------------------------------------------
# 4. Account id mismatch -> RED immediately, mismatch named, no retry
# ---------------------------------------------------------------------------

def test_account_id_mismatch_is_red_immediately_and_names_the_mismatch(monkeypatch):
    script = _happy_script(**{
        f"{FAKE_BOLD_KEY}:account": [_ok_account("PA_WRONG_ACCOUNT_NUMBER")],
    })
    result, sleep_spy, _ = _run(script, monkeypatch=monkeypatch)
    assert result["verdict"] == "RED"
    assert result["alpaca_bold"]["verdict"] == "red"
    assert "PA_WRONG_ACCOUNT_NUMBER" in result["alpaca_bold"]["note"]
    assert FAKE_BOLD_ACCT in result["alpaca_bold"]["note"], "note must name what was EXPECTED too"
    assert sleep_spy.calls == [], "a definitive mismatch is a config fact -- it must not wait for a retry"


def test_inactive_status_is_also_a_mismatch_red(monkeypatch):
    script = _happy_script(**{
        f"{FAKE_SAFE_KEY}:account": [_ok_account(FAKE_SAFE_ACCT, status="SUSPENDED")],
    })
    result, _, _ = _run(script, monkeypatch=monkeypatch)
    assert result["verdict"] == "RED"
    assert "SUSPENDED" in result["alpaca_safe"]["note"]


# ---------------------------------------------------------------------------
# 5. TradingView down -> YELLOW only, never RED
# ---------------------------------------------------------------------------

def test_tv_down_is_yellow_only(monkeypatch):
    script = _happy_script(tv=[_fail_tv()])
    result, _, _ = _run(script, monkeypatch=monkeypatch)
    assert result["verdict"] == "YELLOW"
    assert result["tradingview"]["ok"] is False
    assert result["alpaca_safe"]["verdict"] == "ok"
    assert result["alpaca_bold"]["verdict"] == "ok"


# ---------------------------------------------------------------------------
# 6. MCP server processes absent -> YELLOW only, never RED
# ---------------------------------------------------------------------------

def test_mcp_processes_absent_is_yellow_only(monkeypatch):
    result, _, _ = _run(_happy_script(), ps_count="0", monkeypatch=monkeypatch)
    assert result["verdict"] == "YELLOW"
    assert result["mcp_processes"]["ok"] is False
    assert result["alpaca_safe"]["verdict"] == "ok"
    assert result["alpaca_bold"]["verdict"] == "ok"


# ---------------------------------------------------------------------------
# 7. Secrets never appear in the serialized output
# ---------------------------------------------------------------------------

def test_secrets_never_appear_in_json_or_status_line(monkeypatch, tmp_path):
    result, _, _ = _run(_happy_script(), monkeypatch=monkeypatch)
    serialized = json.dumps(result)
    for secret in (FAKE_SAFE_KEY, FAKE_BOLD_KEY, FAKE_SAFE_SECRET, FAKE_BOLD_SECRET):
        assert secret not in serialized

    status_path = tmp_path / "STATUS.md"
    status_path.write_text(KNOWN_BROKEN + "\n\n", encoding="utf-8")
    output_path = tmp_path / "mcp-daily-audit.json"
    mda.write_outputs(result, output_path=output_path, status_path=status_path)

    json_text = output_path.read_text(encoding="utf-8")
    status_text = status_path.read_text(encoding="utf-8")
    for secret in (FAKE_SAFE_KEY, FAKE_BOLD_KEY, FAKE_SAFE_SECRET, FAKE_BOLD_SECRET):
        assert secret not in json_text
        assert secret not in status_text


# ---------------------------------------------------------------------------
# write_outputs: GREEN clears the marker, non-GREEN writes exactly one line
# ---------------------------------------------------------------------------

def test_write_outputs_red_writes_one_marker_line(monkeypatch, tmp_path):
    script = _happy_script(**{f"{FAKE_SAFE_KEY}:account": [_fail_401(), _fail_401()]})
    result, _, _ = _run(script, monkeypatch=monkeypatch)
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(KNOWN_BROKEN + "\n\n", encoding="utf-8")
    output_path = tmp_path / "mcp-daily-audit.json"

    mda.write_outputs(result, output_path=output_path, status_path=status_path)
    text = status_path.read_text(encoding="utf-8")
    assert text.count("MCP_AUDIT_RED") == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["verdict"] == "RED"


def test_write_outputs_green_clears_a_prior_red_marker(monkeypatch, tmp_path):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(
        KNOWN_BROKEN + "\n\n- [2026-09-03T00:03:45 ET] MCP_AUDIT_RED: stale false reading\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "mcp-daily-audit.json"
    result, _, _ = _run(_happy_script(), monkeypatch=monkeypatch)

    mda.write_outputs(result, output_path=output_path, status_path=status_path)
    text = status_path.read_text(encoding="utf-8")
    assert "MCP_AUDIT_" not in text
    assert json.loads(output_path.read_text(encoding="utf-8"))["verdict"] == "GREEN"


def test_write_outputs_dedupes_a_stale_red_when_the_new_reading_is_also_red(monkeypatch, tmp_path):
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(
        KNOWN_BROKEN + "\n\n"
        "- [2026-09-03T00:03:45 ET] MCP_AUDIT_RED: stale reading 1\n"
        "- [2026-09-03T07:48:00 ET] MCP_AUDIT_YELLOW: stale reading 2\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "mcp-daily-audit.json"
    script = _happy_script(**{f"{FAKE_SAFE_KEY}:account": [_fail_401(), _fail_401()]})
    result, _, _ = _run(script, monkeypatch=monkeypatch)

    mda.write_outputs(result, output_path=output_path, status_path=status_path)
    text = status_path.read_text(encoding="utf-8")
    assert text.count("MCP_AUDIT_") == 1, "exactly one MCP_AUDIT_ line must survive, never a stack"
    assert "stale reading" not in text


# ---------------------------------------------------------------------------
# expected_accounts(): registry-driven, never hardcoded (2026-08-18 scar class)
# ---------------------------------------------------------------------------

def test_expected_accounts_reads_the_live_fleet_registry():
    expected = mda.expected_accounts()
    assert expected["safe"] == "PA3POKNV46VG"
    assert expected["bold"] == "PA3WEBXJU67N"
