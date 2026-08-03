"""Data-creds liveness guard for exit_shape_parity_study.fetch_option_bars
(2026-08-03 EOD process audit, Lens 4).

DEFECT PINNED (L234 shape): the OPRA bar fetcher hardcoded `creds_all.get("safe-1")` --
"any account's key works for market data" was true only while safe-1 existed. The
2026-08-02 full account rebuild retired safe-1; its key started 401-ing, the fail-open
fetcher surfaced that only as '0 bars', and the nightly Gamma_WinnerAutopsy fire
(winner_autopsy -> pain_ledger -> fill_latency fold) hung in its 20/40/80s retry ladder
and wrote NOTHING for the 2026-08-03 cycle (two pythonw processes found still alive 20+
minutes after the 16:25 fire; Task Scheduler showed Result 0 -- the wscript shim's exit
code, C8).

Pins: (1) no hardcoded arm pick survives in the source; (2) _live_data_creds probes and
returns the first LIVE arm, skipping dead keys; (3) the probe result is cached (one probe
per process); (4) all-dead and no-secrets degrade to None (fetch stays fail-open).
RED-proof: on the pre-fix module, _live_data_creds does not exist -> import-time AttributeError.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_TOOLS = _REPO / "backtest" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import exit_shape_parity_study as esp  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    esp._DATA_CREDS_CACHE = None
    yield
    esp._DATA_CREDS_CACHE = None


def test_no_hardcoded_safe1_pick_in_source():
    src = (_TOOLS / "exit_shape_parity_study.py").read_text(encoding="utf-8")
    assert 'creds_all.get("safe-1")' not in src


def test_live_creds_skips_dead_arm(monkeypatch):
    dead = {"key": "K_DEAD", "secret": "S", "base_url": "https://x"}
    live = {"key": "K_LIVE", "secret": "S", "base_url": "https://x"}
    probes = []

    monkeypatch.setattr(esp.fb, "load_creds", lambda: {"a-dead": dead, "b-live": live})

    def fake_get_account(c):
        probes.append(c["key"])
        if c["key"] == "K_DEAD":
            return {"_error": "HTTP Error 401: Unauthorized", "_status": 401}
        return {"status": "ACTIVE", "account_number": "PAXXXX"}

    monkeypatch.setattr(esp.fb, "get_account", fake_get_account)
    got = esp._live_data_creds()
    assert got is not None and got["key"] == "K_LIVE"
    assert probes == ["K_DEAD", "K_LIVE"]  # sorted order, dead skipped after probe


def test_probe_result_is_cached_one_probe_per_process(monkeypatch):
    live = {"key": "K_LIVE", "secret": "S", "base_url": "https://x"}
    calls = {"n": 0}

    def fake_load():
        calls["n"] += 1
        return {"only": live}

    monkeypatch.setattr(esp.fb, "load_creds", fake_load)
    monkeypatch.setattr(esp.fb, "get_account", lambda c: {"status": "ACTIVE"})
    first = esp._live_data_creds()
    second = esp._live_data_creds()
    assert first is second or first == second
    assert calls["n"] == 1


def test_all_dead_returns_none_and_caches(monkeypatch):
    dead = {"key": "K1", "secret": "S", "base_url": "https://x"}
    monkeypatch.setattr(esp.fb, "load_creds", lambda: {"a": dead})
    n = {"probes": 0}

    def fake_get_account(c):
        n["probes"] += 1
        return {"_error": "HTTP Error 401", "_status": 401}

    monkeypatch.setattr(esp.fb, "get_account", fake_get_account)
    assert esp._live_data_creds() is None
    assert esp._live_data_creds() is None
    assert n["probes"] == 1  # negative result cached too -- no per-fetch re-hammering


def test_missing_secrets_file_degrades_to_none(monkeypatch):
    def boom():
        raise FileNotFoundError("secrets.json not found")

    monkeypatch.setattr(esp.fb, "load_creds", boom)
    assert esp._live_data_creds() is None
