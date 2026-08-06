"""Guards for automation/scripts/compute_trendlines.py (2026-08-06 audit).

TWO defects pinned here, both of the "silent success" family (C7/C14):

  1. LEXICOGRAPHIC LATEST-FILE PICK. `sorted(glob("spy_5m_*.csv"))[-1]` returned
     `spy_5m_2026-07-23_supplement.csv` (5KB, one session) instead of
     `spy_5m_2026-05-19_2026-08-06.csv` (594KB, current), because "2026-07" sorts
     after "2026-05". The script then reported success while fitting every trendline
     to a stale single session. Same family as the beacon asc+limit truncation.

  2. NO STALENESS FILTER ON MANUAL LINES. Auto-detected lines had a +/-$5 proximity
     filter; hand-drawn ones had none, so May anchors were extrapolated months forward
     and published as current -- the audit found projected_price_now values of
     $2,825.07 and -$1,117.96 against a $770 spot.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "automation" / "scripts"))

import compute_trendlines as ct  # noqa: E402


# ------------------------------------------------------- latest-CSV selection

def _touch(dirpath: Path, name: str, size: int = 100) -> Path:
    p = dirpath / name
    p.write_bytes(b"x" * size)
    return p


def test_supplement_file_does_not_beat_current_range_file(tmp_path, monkeypatch):
    """THE incident: a July supplement must not outrank an August range file."""
    _touch(tmp_path, "spy_5m_2026-05-19_2026-08-06.csv", size=594_913)
    _touch(tmp_path, "spy_5m_2026-07-23_supplement.csv", size=5_026)
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    assert ct._latest_spy_csv().name == "spy_5m_2026-05-19_2026-08-06.csv"


def test_newest_end_date_wins_over_lexicographic_order(tmp_path, monkeypatch):
    _touch(tmp_path, "spy_5m_2026-05-19_2026-08-06.csv")
    _touch(tmp_path, "spy_5m_2026-09-01_2026-09-02.csv")
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    assert ct._latest_spy_csv().name == "spy_5m_2026-09-01_2026-09-02.csv"


def test_same_end_date_prefers_the_bigger_file(tmp_path, monkeypatch):
    _touch(tmp_path, "spy_5m_2026-08-06_2026-08-06.csv", size=5_000)
    _touch(tmp_path, "spy_5m_2026-05-19_2026-08-06.csv", size=600_000)
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    assert ct._latest_spy_csv().name == "spy_5m_2026-05-19_2026-08-06.csv"


def test_undated_file_never_wins(tmp_path, monkeypatch):
    _touch(tmp_path, "spy_5m_2026-05-19_2026-08-06.csv", size=100)
    _touch(tmp_path, "spy_5m_zzz_backup.csv", size=999_999)
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    assert ct._latest_spy_csv().name == "spy_5m_2026-05-19_2026-08-06.csv"


def test_empty_data_dir_raises_rather_than_returning_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    try:
        ct._latest_spy_csv()
    except FileNotFoundError:
        return
    raise AssertionError("must raise FileNotFoundError, not silently return a bad path")


# ------------------------------------------------------- staleness thresholds

def test_manual_staleness_bounds_are_pinned():
    """Loosening these is what let $2,825 projections reach the artifact."""
    assert ct.MANUAL_MAX_AGE_DAYS <= 10.0
    assert ct.MANUAL_MAX_DISTANCE <= 15.0


def test_real_repo_pick_is_a_current_range_file():
    """Against the real data dir, the pick must not be a supplement/patch file."""
    picked = ct._latest_spy_csv()
    assert "supplement" not in picked.name, f"picked a supplement patch: {picked.name}"
    dates = []
    for tok in picked.stem.split("_"):
        try:
            dates.append(dt.date.fromisoformat(tok))
        except ValueError:
            continue
    assert dates, f"picked an undated file: {picked.name}"
    assert max(dates) >= dt.date(2026, 8, 1), f"picked a stale file: {picked.name}"


# ------------------------------------------------------- honesty of the artifact

def test_docstring_does_not_claim_the_heartbeat_reads_this_file():
    """The old docstring said the heartbeat reads the cached file. It never did --
    trendline_rejection computes its own line from prior_bars."""
    doc = ct.__doc__ or ""
    assert "heartbeat reads the cached file" not in doc
    assert "ZERO downstream consumers" in doc, "the SHADOW/no-consumer status must stay stated"
