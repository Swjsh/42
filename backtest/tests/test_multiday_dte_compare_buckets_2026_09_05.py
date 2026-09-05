"""RED-proof guard: multiday_dte_compare must actually run the 3/4-DTE buckets that
were backfilled 2026-07-07 (options_3dte_4dte_backfill_manifest.json, ok=2958/2961) and
must never silently report a result for a bucket whose option cache is missing.

Context: strategy/candidates/2026-07-07-193737-weekly-dte-not-0dte.md's
## ADJUDICATION 2026-09-05 found the backfill landed but DTE_BUCKETS stopped at [0,1,2]
and _dte_expansion_sim.DTE_DIRS had no 3/4 entries -- so ~50 Nemotron _analysis files
claiming a 3/4-DTE rescore were all fabricated (the runner could not have produced them).

This test is RED against the pre-2026-09-05 code (DTE_BUCKETS=[0,1,2], DTE_DIRS missing
3/4) and GREEN after the fix in multiday_dte_compare.py / _dte_expansion_sim.py.

  backtest/.venv/Scripts/python.exe -m pytest tests/test_multiday_dte_compare_buckets_2026_09_05.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]      # backtest/
ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

from autoresearch import multiday_dte_compare as C  # noqa: E402
from autoresearch import _dte_expansion_sim as X  # noqa: E402


def test_dte_buckets_includes_3_and_4():
    """The bucket list the runner actually iterates must include the backfilled DTEs."""
    assert 3 in C.DTE_BUCKETS, "3-DTE bucket missing -- backfilled cache never wired in"
    assert 4 in C.DTE_BUCKETS, "4-DTE bucket missing -- backfilled cache never wired in"
    assert C.DTE_BUCKETS == [0, 1, 2, 3, 4]


def test_dte_dirs_maps_3_and_4_to_the_backfilled_cache_dirs():
    """_dte_expansion_sim.DTE_DIRS (the actual cache loader map) must point 3/4 at the
    real backfilled directories, same convention as 1/2."""
    assert 3 in X.DTE_DIRS and 4 in X.DTE_DIRS
    assert X.DTE_DIRS[3].name == "options_3dte"
    assert X.DTE_DIRS[4].name == "options_4dte"
    assert X.DTE_DIRS[3].exists(), "options_3dte cache dir does not exist on disk"
    assert X.DTE_DIRS[4].exists(), "options_4dte cache dir does not exist on disk"
    assert any(X.DTE_DIRS[3].glob("*.csv")), "options_3dte cache dir is empty"
    assert any(X.DTE_DIRS[4].glob("*.csv")), "options_4dte cache dir is empty"


def test_missing_cache_raises_not_silently_skips():
    """A bucket with zero fills (cache entirely absent for every signal date) must
    raise BucketCacheMissingError, never return a silent 0-trade 'result'."""
    cov_all_missing = {
        "signals": 10, "filled": 0, "cache_miss": 0,
        "no_expiry_listed": 10, "sim_none": 0, "fill_rate": 0.0,
    }
    with pytest.raises(C.BucketCacheMissingError):
        C.check_bucket_coverage(99, cov_all_missing)


def test_missing_cache_reports_coverage_counts_when_healthy(capsys):
    """A healthy bucket must not raise, and must print the coverage counts (never
    silent) so a partial-fill bucket is visible in the run log."""
    cov_healthy = {
        "signals": 50, "filled": 45, "cache_miss": 3,
        "no_expiry_listed": 2, "sim_none": 0, "fill_rate": 0.9,
    }
    C.check_bucket_coverage(3, cov_healthy)
    out = capsys.readouterr().out
    assert "DTE=3" in out
    assert "filled=45" in out
    assert "no_expiry_listed=2" in out


def test_zero_signals_bucket_does_not_raise():
    """No signals generated at all is a signal-generation fact (e.g. family produced
    0 triggers), not a cache-coverage fact -- must not be conflated with a missing cache."""
    C.check_bucket_coverage(4, {"signals": 0, "filled": 0, "cache_miss": 0,
                                "no_expiry_listed": 0, "sim_none": 0, "fill_rate": 0.0})
