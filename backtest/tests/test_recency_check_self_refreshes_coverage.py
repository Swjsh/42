"""Guard: recency_check.py must SELF-REFRESH the data-coverage manifest, never
trust a stale on-disk `data-coverage.json` for its OPRA cache-last date.

WHY THIS GUARD EXISTS (conductor 2026-07-18, F3-RED-BOOK-STILL-ARMED audit)
-----------------------------------------------------------------------------
`data-coverage.json` (`backtest/tools/data_coverage_manifest.py`) is a MANUALLY-run
tool with NO scheduled task keeping it current. Found stuck reporting
`option_chain_realfills.last=2026-07-08` (the manifest file itself last regenerated
2026-07-14) while the REAL on-disk option-chain cache
(`backtest/data/options/SPY*.csv`) had already extended to 2026-07-17 -- a silent
~9-trading-day undercount. `recency_check.read_cache_last_date()` blindly trusted
that stale manifest, so the CONFIRM-BEFORE-CAPITAL gate's "recent window" was
truncated by ~9 days on every nightly `Gamma_LicenseMonitor --run` fire -- the exact
silent-degradation foot-gun `data_coverage_manifest.py`'s own docstring says it
exists to prevent (the guard itself needed a guard, C7).

Fix: `read_cache_last_date()` now calls `data_coverage_manifest.build_manifest()`
(a live rescan of the real files on disk) and rewrites `data-coverage.json` BEFORE
reading it, falling back to the existing (possibly stale) file only if that refresh
raises (fail-open -- a stale-but-readable window beats crashing the gate).

These tests pin:
  * a stale on-disk manifest gets OVERWRITTEN with the true current last-date
    (live rescan of the real `backtest/data/options/` directory -- no mocking of
    the underlying data, only of the manifest PATH so the live cache is untouched);
  * the manifest file on disk is actually rewritten (not just read past), so every
    OTHER consumer of `data-coverage.json` (task_scorer's recency gate,
    license_monitor, self_check) benefits too, not just this one call site;
  * fail-open: an exception during self-refresh falls back to the existing stale
    JSON rather than crashing;
  * a non-vacuous BITE (neutering the refresh call reproduces the stale-read
    behaviour) proves the self-refresh is what changes the outcome.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autoresearch import recency_check as rc

_ROOT = Path(__file__).resolve().parents[2]
_REAL_OPTIONS_DIR = _ROOT / "backtest" / "data" / "options"


def _true_option_cache_last() -> str:
    """Independently derive the real last-covered date from the live options dir
    (same regex convention as data_coverage_manifest._option_cache_span, re-derived
    here rather than imported, so this test does not just re-check the module
    against itself)."""
    import re

    pat = re.compile(r"SPY(\d{2})(\d{2})(\d{2})[CP]\d+", re.IGNORECASE)
    import datetime as dt

    days = set()
    for p in _REAL_OPTIONS_DIR.glob("SPY*.csv"):
        m = pat.match(p.name)
        if not m:
            continue
        yy, mm, dd = (int(g) for g in m.groups())
        days.add(dt.date(2000 + yy, mm, dd))
    assert days, "live options cache is empty -- fixture precondition failed"
    return max(days).isoformat()


@pytest.fixture(autouse=True)
def _redirect_coverage_path(tmp_path, monkeypatch):
    """Point DATA_COVERAGE at a throwaway file so this test never mutates the
    real `automation/state/data-coverage.json`, while build_manifest() itself
    still scans the REAL on-disk options dir (untouched -- read-only rescan)."""
    stale = tmp_path / "data-coverage.json"
    stale.write_text(json.dumps({
        "classes": {"option_chain_realfills": {"first": "2025-01-02", "last": "2026-07-08", "n_days": 1}}
    }), encoding="utf-8")
    monkeypatch.setattr(rc, "DATA_COVERAGE", stale)
    yield stale


def test_stale_manifest_self_refreshes_to_true_last_date(_redirect_coverage_path):
    true_last = _true_option_cache_last()
    got = rc.read_cache_last_date()
    assert got.isoformat() == true_last
    # And it must NOT equal the stale seed value we planted (proves it actually refreshed).
    assert got.isoformat() != "2026-07-08" or true_last == "2026-07-08"


def test_stale_manifest_file_is_overwritten_on_disk(_redirect_coverage_path):
    before = json.loads(_redirect_coverage_path.read_text(encoding="utf-8"))
    assert before["classes"]["option_chain_realfills"]["last"] == "2026-07-08"
    rc.read_cache_last_date()
    after = json.loads(_redirect_coverage_path.read_text(encoding="utf-8"))
    true_last = _true_option_cache_last()
    assert after["classes"]["option_chain_realfills"]["last"] == true_last
    assert after["generated_by"] == "backtest/tools/data_coverage_manifest.py"


def test_refresh_failure_falls_back_to_existing_stale_json(_redirect_coverage_path, monkeypatch):
    """If the live rescan raises for any reason, the gate must not crash -- it
    falls back to whatever is already on disk (fail-open for the gate's caller)."""

    def _boom():
        raise RuntimeError("simulated manifest-refresh failure")

    # Patch the imported name at its SOURCE module so recency_check's inline
    # `from tools.data_coverage_manifest import build_manifest` picks up the stub.
    import tools.data_coverage_manifest as dcm

    monkeypatch.setattr(dcm, "build_manifest", _boom)
    got = rc.read_cache_last_date()
    assert got.isoformat() == "2026-07-08"  # the stale seed value, not a crash


def test_bite_without_self_refresh_the_stale_date_would_have_leaked(_redirect_coverage_path, monkeypatch):
    """Neuter the self-refresh entirely (simulate the pre-fix code path) and prove
    the stale seed value DOES leak through -- demonstrates the fix is load-bearing,
    not a no-op."""
    import tools.data_coverage_manifest as dcm

    def _boom():
        raise RuntimeError("no self-refresh -- old behaviour")

    monkeypatch.setattr(dcm, "build_manifest", _boom)
    got = rc.read_cache_last_date()
    true_last = _true_option_cache_last()
    assert got.isoformat() == "2026-07-08"
    # Sanity: the live cache has actually moved past the stale seed (else this
    # bite would be vacuous -- both fixtures would coincidentally agree).
    assert true_last > "2026-07-08"
