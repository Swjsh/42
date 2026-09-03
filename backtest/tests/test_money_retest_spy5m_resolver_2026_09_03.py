"""Guard suite for backtest/tools/money_retest_entry_variant.py's SPY 5m cache resolver.

ROOT CAUSE (RETEST-ZONE-SCORING-KEYERROR, 2026-09-03): SPY_5M_PATH was a hardcoded,
date-stamped filename (spy_5m_2026-05-19_2026-09-02.csv) that goes stale the session
backtest/tools/fetch_data.py writes the next day's file -- it never overwrites, it appends
a new spy_5m_2026-05-19_<end-date>.csv per run and leaves prior files on disk. The nightly
forward consumer (setup/scripts/retest_zone_shadow.py, 17:05 ET, imports this module by
reuse) skipped every entry dated after the pinned constant's end date forever
(skip_no_spy_5m_for_ribbon on all 16 rows for 2026-09-03).

Fix: resolve_spy_5m_path() picks the freshest spy_5m_2026-05-19_*.csv on disk BY FILENAME
END-DATE, called at CALL time (not just once at import) so a long-running process still
picks up a file written after it started. SPY_5M_PATH stays a module attribute (resolved
once at import) for backward compatibility with any code that reads it directly.

Guards below:
  1. Resolver picks the file with the LATEST end date among several synthetic candidates.
  2. Resolver ignores filenames that don't match the exact producer pattern (different
     start date, `_merged`/`_supplement` suffixes, wrong extension).
  3. Resolver raises FileNotFoundError loudly when no matching file exists -- never a
     silent stale fallback.
  4. load_spy_5m_and_ribbon() (the ribbon loader retest_zone_shadow.py actually calls) sees
     a file created AFTER the module was imported -- proving the resolution happens at call
     time, not import time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import money_retest_entry_variant as mrev  # noqa: E402


def _write_spy5m_csv(path: Path) -> None:
    """Minimal frame satisfying load_spy_5m_and_ribbon()'s read + RTH filter + compute_ribbon
    -- one RTH bar is enough for compute_ribbon (causal EMAs) to run without error."""
    pd.DataFrame({
        "timestamp_et": ["2026-05-19 09:30:00"],
        "open": [500.0], "high": [500.5], "low": [499.5], "close": [500.0], "volume": [1000],
    }).to_csv(path, index=False)


# ---------------------------------------------------------------------------------
# 1. latest end date wins
# ---------------------------------------------------------------------------------
def test_resolver_picks_latest_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(mrev, "SPY_5M_DIR", tmp_path)
    for name in ("spy_5m_2026-05-19_2026-09-01.csv",
                 "spy_5m_2026-05-19_2026-09-03.csv",
                 "spy_5m_2026-05-19_2026-09-02.csv"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    resolved = mrev.resolve_spy_5m_path()

    assert resolved.name == "spy_5m_2026-05-19_2026-09-03.csv"


# ---------------------------------------------------------------------------------
# 2. non-matching names never become candidates
# ---------------------------------------------------------------------------------
def test_resolver_ignores_non_matching_names(tmp_path, monkeypatch):
    monkeypatch.setattr(mrev, "SPY_5M_DIR", tmp_path)
    # the one real match -- must win despite being written first / alphabetically mid-pack
    (tmp_path / "spy_5m_2026-05-19_2026-08-01.csv").write_text("x", encoding="utf-8")
    # decoys that must NOT be picked: different start date, merged/supplement variants,
    # a different symbol series, wrong extension
    for decoy in (
        "spy_5m_2025-01-01_2026-09-05.csv",           # different master series start
        "spy_5m_2026-05-19_2026-09-05_merged.csv",     # suffix breaks the exact pattern
        "spy_5m_2026-07-23_supplement.csv",            # no end-date group at all
        "vix_5m_2026-05-19_2026-09-05.csv",            # wrong symbol prefix
        "spy_5m_2026-05-19_2026-09-05.json",           # wrong extension
    ):
        (tmp_path / decoy).write_text("x", encoding="utf-8")

    resolved = mrev.resolve_spy_5m_path()

    assert resolved.name == "spy_5m_2026-05-19_2026-08-01.csv"


# ---------------------------------------------------------------------------------
# 3. raises loudly, never a silent stale fallback
# ---------------------------------------------------------------------------------
def test_resolver_raises_when_none_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(mrev, "SPY_5M_DIR", tmp_path)
    # directory exists but is empty (and/or has only non-matching files)
    (tmp_path / "spy_5m_2025-01-01_2026-09-05.csv").write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        mrev.resolve_spy_5m_path()


# ---------------------------------------------------------------------------------
# 4. the ribbon loader picks up a file created AFTER import -- proves call-time resolution
# ---------------------------------------------------------------------------------
def test_ribbon_loader_sees_file_created_after_import(tmp_path, monkeypatch):
    monkeypatch.setattr(mrev, "SPY_5M_DIR", tmp_path)
    _write_spy5m_csv(tmp_path / "spy_5m_2026-05-19_2026-09-01.csv")

    first = mrev.resolve_spy_5m_path()
    assert first.name == "spy_5m_2026-05-19_2026-09-01.csv"

    # simulate fetch_data.py's next scheduled run writing a fresher file, well after this
    # module (and this test process) were already imported/running
    _write_spy5m_csv(tmp_path / "spy_5m_2026-05-19_2026-09-03.csv")

    spy_rth, ribbon = mrev.load_spy_5m_and_ribbon()

    assert mrev.resolve_spy_5m_path().name == "spy_5m_2026-05-19_2026-09-03.csv"
    assert not spy_rth.empty
    assert len(ribbon) == len(spy_rth)
