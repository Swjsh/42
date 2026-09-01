"""Guard: a dead credential must fall through to the next arm, never to "no data".

SCAR (2026-09-01). `fetch_bars` took `next(iter(fleet_broker.load_creds().values()))` --
the FIRST arm in secrets.json. That file still lists retired arms, and `safe-1`'s key
returns HTTP 401. Dict order is insertion order, so the fetch picked a dead key and every
single contract failed with 401 while six other arms would have answered instantly.

The dangerous part was not the 401. It was that the ledger then reported those episodes as
`scored: false` -- which reads identically to "no tape exists for this contract". A broken
credential and a genuinely unpriceable refusal produced the same output, so the failure
would have looked like an honest null forever.

Two properties pinned here:
  1. FALL THROUGH -- an HTTP failure on one arm must not end the attempt.
  2. ACTIVE FIRST -- known-active arms are tried before retired ones.
"""
from __future__ import annotations

import importlib
import sys
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

rsl = importlib.import_module("refused_setup_ledger")

ACTIVE = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")


def test_active_arms_are_ordered_before_retired_ones(monkeypatch):
    fake = {"safe-1": {"key": "dead", "secret": "x"},
            "safe-2": {"key": "live", "secret": "y"}}
    mod = type(sys)("fleet_broker")
    mod.load_creds = lambda: fake            # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fleet_broker", mod)
    monkeypatch.setattr(rsl, "REPO", REPO)

    labels = [lbl for lbl, _ in rsl._data_creds()]
    assert "fleet:safe-2" in labels and "fleet:safe-1" in labels
    assert labels.index("fleet:safe-2") < labels.index("fleet:safe-1"), (
        "retired arm ordered ahead of an active one -- the 2026-09-01 scar")


def test_fetch_falls_through_a_401_to_the_next_arm(monkeypatch, tmp_path):
    """The exact failure: arm #1 401s, arm #2 has the bars."""
    monkeypatch.setattr(rsl, "HIGHRES", tmp_path)
    monkeypatch.setattr(rsl, "_data_creds", lambda: [
        ("fleet:dead", {"key": "d", "secret": "d"}),
        ("fleet:live", {"key": "l", "secret": "l"}),
    ])

    calls: list[str] = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return (b'{"bars":{"SPY260831P00766000":[{"t":"2026-08-31T13:30:00Z",'
                    b'"o":1.0,"h":1.2,"l":0.9,"c":1.1,"v":10}]}}')

    def fake_open(req, timeout=0):
        key = req.headers.get("Apca-api-key-id") or req.headers.get("APCA-API-KEY-ID")
        calls.append(key)
        if key == "d":
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return _Resp()

    import urllib.request as ur
    monkeypatch.setattr(ur, "urlopen", fake_open)

    assert rsl.fetch_bars("SPY260831P00766000", "2026-08-31") is True
    assert calls == ["d", "l"], f"did not fall through: {calls}"
    assert (tmp_path / "SPY260831P00766000_1m_2026-08-31.csv").exists()


def test_no_bars_is_an_honest_false_not_a_crash(monkeypatch, tmp_path):
    """A contract with genuinely no tape stays unscored -- and never fabricates a price."""
    monkeypatch.setattr(rsl, "HIGHRES", tmp_path)
    monkeypatch.setattr(rsl, "_data_creds", lambda: [("x", {"key": "k", "secret": "s"})])

    class _Empty:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"bars":{}}'

    import urllib.request as ur
    monkeypatch.setattr(ur, "urlopen", lambda *a, **k: _Empty())

    assert rsl.fetch_bars("SPY260831P00999000", "2026-08-31") is False
    assert not list(tmp_path.glob("*.csv")), "wrote a cache file for a contract with no bars"


def test_every_arm_failing_reports_false(monkeypatch, tmp_path):
    monkeypatch.setattr(rsl, "HIGHRES", tmp_path)
    monkeypatch.setattr(rsl, "_data_creds", lambda: [
        ("a", {"key": "a", "secret": "a"}), ("b", {"key": "b", "secret": "b"})])

    import urllib.request as ur

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(ur, "urlopen", boom)
    assert rsl.fetch_bars("SPY260831P00766000", "2026-08-31") is False


def test_existing_cache_short_circuits(monkeypatch, tmp_path):
    """Never re-fetch what the cache already holds."""
    monkeypatch.setattr(rsl, "HIGHRES", tmp_path)
    (tmp_path / "SPY260831P00766000_1m_2026-08-31.csv").write_text("x", encoding="utf-8")
    monkeypatch.setattr(rsl, "_data_creds",
                        lambda: pytest.fail("hit the network despite a cache hit"))
    assert rsl.fetch_bars("SPY260831P00766000", "2026-08-31") is True
