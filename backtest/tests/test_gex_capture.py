"""Tests for automation/scripts/gex_capture.py — the daily GEX capture + regime tag.

NO live Alpaca: the chain fetch is monkeypatched with a synthetic snapshot, and all
writes are redirected to a tmp_path. Asserts:
  * a valid RAW chain snapshot is archived (per-contract strike/right/gamma/OI),
  * a well-formed regime TAG is written (all expected keys, status "ok"),
  * the tag's regime label MATCHES gex_regime.compute_gex_regime on the same chain
    (proving the job REUSES the engine, not a divergent reimplementation),
  * the fail-safe path writes a "not_computed" tag (and never raises) when the chain
    is empty / unavailable,
  * idempotency: a second run skips when the dated archive already exists.

Run:  cd backtest && python -m pytest tests/test_gex_capture.py -q
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.gex_regime import (  # noqa: E402
    GammaContract,
    compute_gex_regime,
    from_alpaca_snapshot,
)

# Load the capture module by path (automation/ is not an importable package).
_CAP_PATH = REPO / "automation" / "scripts" / "gex_capture.py"
_spec = importlib.util.spec_from_file_location("gex_capture", _CAP_PATH)
gex_capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gex_capture)  # type: ignore[union-attr]


# ── synthetic chain (puts dominate -> short-gamma trend regime) ────────────────
def _synthetic_snapshot() -> dict:
    """Alpaca-shaped snapshot: symbol -> {greeks:{gamma}, openInterest}. Puts carry more
    OI than calls so the net dealer GEX is negative -> short_gamma_trend."""
    return {
        "snapshots": {
            "SPY260619C00600000": {"greeks": {"gamma": 0.05}, "openInterest": 1000},
            "SPY260619C00610000": {"greeks": {"gamma": 0.04}, "openInterest": 1500},
            "SPY260619P00600000": {"greeks": {"gamma": 0.05}, "openInterest": 6000},
            "SPY260619P00590000": {"greeks": {"gamma": 0.06}, "openInterest": 8000},
            # a junk row with no gamma — must be archived but ignored by the computer
            "SPY260619C00999000": {"greeks": {}, "openInterest": 10},
        }
    }


SPOT = 600.0


@pytest.fixture()
def patched(tmp_path, monkeypatch):
    """Redirect archive + tag paths into tmp and stub the network fetchers."""
    archive_dir = tmp_path / "journal" / "gex-archive"
    tag_path = tmp_path / "automation" / "state" / "gex-regime.json"
    monkeypatch.setattr(gex_capture, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(gex_capture, "REGIME_TAG", tag_path)
    monkeypatch.setattr(gex_capture, "fetch_spot", lambda: SPOT)
    return archive_dir, tag_path


def test_capture_writes_snapshot_and_wellformed_tag(patched, monkeypatch):
    archive_dir, tag_path = patched
    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", _synthetic_snapshot)

    now = dt.datetime(2026, 6, 19, 9, 15, 0)
    tag = gex_capture.capture(now=now)

    # ── RAW snapshot archived with the per-contract schema ────────────────────
    archive_file = archive_dir / "2026-06-19.json"
    assert archive_file.exists(), "raw chain archive not written"
    raw = json.loads(archive_file.read_text(encoding="utf-8"))
    assert raw["underlying"] == "SPY"
    assert raw["session_date"] == "2026-06-19"
    assert raw["spot"] == SPOT
    assert raw["n_contracts"] == 5  # all rows archived, including the junk one
    sample = raw["contracts"][0]
    for k in ("symbol", "strike", "right", "gamma", "open_interest"):
        assert k in sample
    # OCC parse landed: at least one put and one call with a numeric strike
    rights = {c["right"] for c in raw["contracts"] if c["right"]}
    assert "call" in rights and "put" in rights

    # ── well-formed regime TAG ────────────────────────────────────────────────
    assert tag_path.exists(), "regime tag not written"
    on_disk = json.loads(tag_path.read_text(encoding="utf-8"))
    assert on_disk == tag  # returned dict == file contents
    for k in ("status", "underlying", "session_date", "captured_at", "regime",
              "net_gex_sign", "zero_gamma_flip", "call_wall", "put_wall", "spot",
              "n_contracts", "source", "raw_archive"):
        assert k in on_disk, f"missing key in tag: {k}"
    assert on_disk["status"] == "ok"
    assert on_disk["raw_archive"] == str(archive_file)


def test_tag_regime_matches_gex_regime_engine(patched, monkeypatch):
    """The capture job's label must equal the engine's own output on the same chain."""
    _, tag_path = patched
    snap = _synthetic_snapshot()
    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", lambda: snap)

    tag = gex_capture.capture(now=dt.datetime(2026, 6, 19, 9, 15, 0))

    # Recompute independently via the engine and compare the load-bearing fields.
    expected = compute_gex_regime(from_alpaca_snapshot(snap), SPOT)
    assert tag["regime"] == expected.regime == "short_gamma_trend"
    assert tag["net_gex_sign"] == expected.net_gex_sign == "short"
    assert tag["net_gex"] == pytest.approx(expected.net_gex)
    assert tag["n_contracts"] == expected.n_contracts  # junk row dropped by computer
    assert tag["zero_gamma_flip"] == expected.zero_gamma_flip


def test_failsafe_on_empty_chain_writes_not_computed(patched, monkeypatch):
    archive_dir, tag_path = patched
    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", lambda: {"snapshots": {}})

    tag = gex_capture.capture(now=dt.datetime(2026, 6, 19, 9, 15, 0))

    assert tag["status"] == "not_computed"
    assert tag["regime"] is None
    assert "reason" in tag and tag["reason"]
    assert tag_path.exists()
    # No raw archive should be written for an empty chain.
    assert not (archive_dir / "2026-06-19.json").exists()


def test_failsafe_on_fetch_exception_never_raises(patched, monkeypatch):
    _, tag_path = patched

    def _boom():
        raise OSError("simulated network down")

    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", _boom)
    tag = gex_capture.capture(now=dt.datetime(2026, 6, 19, 9, 15, 0))
    assert tag["status"] == "not_computed"
    assert "simulated network down" in tag["reason"]
    assert json.loads(tag_path.read_text(encoding="utf-8"))["status"] == "not_computed"


def test_idempotent_skips_when_archive_exists(patched, monkeypatch):
    archive_dir, tag_path = patched
    snap = _synthetic_snapshot()
    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", lambda: snap)

    now = dt.datetime(2026, 6, 19, 9, 15, 0)
    gex_capture.capture(now=now)  # first run writes the archive + tag
    assert (archive_dir / "2026-06-19.json").exists()

    # Second run: fetch must NOT be called again.
    def _should_not_call():
        raise AssertionError("fetch_option_snapshots called on idempotent re-run")

    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", _should_not_call)
    tag2 = gex_capture.capture(now=now)
    # Echoes the existing ok tag (status preserved), without re-pulling.
    assert tag2["status"] in ("ok", "skip_exists")


def test_main_returns_zero_on_failsafe(patched, monkeypatch):
    monkeypatch.setattr(gex_capture, "fetch_option_snapshots", lambda: {"snapshots": {}})
    assert gex_capture.main() == 0
