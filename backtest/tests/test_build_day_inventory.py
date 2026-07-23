"""Guard tests for backtest/tools/build_day_inventory.py (EDGE-MATRIX-NIGHTLY-RERUN Step 1).

Covers the two things that matter for a script whose whole job is "add new days without ever
touching frozen history": (1) zero-pending-days is a byte-identical copy-through no-op, and
(2) a genuine new day is added with correctly-computed has_opra/gap_pct/n_rth_bars/partial,
while heldout_days stays frozen. Also covers the pure classification helpers directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_day_inventory as bdi  # noqa: E402


def _mk_spy_csv(path: Path, day: str, bars: list[tuple[int, int, float, float, float, float, int]]) -> None:
    rows = []
    for hh, mm, o, h, l, c, v in bars:
        ts = f"{day}T{hh:02d}:{mm:02d}:00-04:00"
        rows.append({"timestamp_et": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
    pd.DataFrame(rows).to_csv(path, index=False)


def _rth_bars(n: int, o: float, h: float, l: float, c: float) -> list[tuple[int, int, float, float, float, float, int]]:
    out = []
    for i in range(n):
        minute = 30 + 5 * i
        out.append((9 + minute // 60, minute % 60, o, h, l, c, 1000))
    return out


def _base_original(last_day: str, source_file: str) -> dict:
    return {
        "built": "2026-07-22", "built_for": "edge-matrix 2026-07-23",
        "method": {"rth": "09:30<=t<16:00 TRUE ET"}, "counts": {},
        "days": [{
            "date": last_day, "has_opra": True, "n_opra_files": 24, "gap_pct": 0.1,
            "day_type": "chop", "vix_band": "mid", "day_vix": 16.9, "rth_range": 1.0,
            "range_ratio": 0.5, "body_frac": 0.2, "n_rth_bars": 78, "partial": False,
            "source_file": source_file,
        }],
        "opra_days": [last_day], "heldout_days": [last_day],
        "excluded_fragments": [], "manual_amendments": [],
    }


@pytest.fixture()
def patched_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    options_dir = data_dir / "options"
    options_dir.mkdir(parents=True)
    monkeypatch.setattr(bdi, "DATA_DIR", data_dir)
    monkeypatch.setattr(bdi, "OPTIONS_DIR", options_dir)
    return data_dir, options_dir


def test_zero_pending_days_is_byte_identical_copy_through(patched_dirs):
    data_dir, _ = patched_dirs
    src = data_dir / "spy_5m_2026-07-01_2026-07-22.csv"
    _mk_spy_csv(src, "2026-07-22", _rth_bars(78, 500, 500.5, 499.5, 500))
    original = _base_original("2026-07-22", src.name)

    ext = bdi._extend_new_days(original)

    assert ext["forward_days"] == []
    assert ext["days"] == original["days"]
    assert ext["opra_days"] == original["opra_days"]
    assert ext["heldout_days"] == original["heldout_days"]
    assert ext["excluded_fragments"] == original["excluded_fragments"]
    assert ext["counts"]["forward_days_added"] == 0


def test_extend_adds_one_new_day_with_correct_fields(patched_dirs):
    data_dir, options_dir = patched_dirs
    last_src = data_dir / "spy_5m_2026-07-01_2026-07-22.csv"
    _mk_spy_csv(last_src, "2026-07-22", _rth_bars(78, 500, 500.5, 499.5, 500))
    new_src = data_dir / "spy_5m_2026-07-01_2026-07-23.csv"
    _mk_spy_csv(new_src, "2026-07-23", _rth_bars(78, 505, 506, 504, 505))
    (options_dir / "SPY260723C00500000.csv").write_text("t,o\n1,2\n", encoding="utf-8")
    (options_dir / "SPY260723P00500000.csv").write_text("t,o\n1,2\n", encoding="utf-8")

    original = _base_original("2026-07-22", last_src.name)
    ext = bdi._extend_new_days(original)

    assert ext["forward_days"] == ["2026-07-23"]
    assert len(ext["days"]) == 2
    row = ext["days"][-1]
    assert row["date"] == "2026-07-23"
    assert row["has_opra"] is True
    assert row["n_opra_files"] == 2
    assert row["n_rth_bars"] == 78
    assert row["partial"] is False
    assert row["gap_pct"] == pytest.approx(1.0, abs=0.01)  # (505-500)/500*100
    assert "2026-07-23" in ext["opra_days"]
    # FROZEN: heldout_days must never gain the new day
    assert ext["heldout_days"] == ["2026-07-22"]
    assert "2026-07-23" not in ext["heldout_days"]
    # original row untouched
    assert ext["days"][0] == original["days"][0]


def test_extend_excludes_short_fragment_day(patched_dirs):
    data_dir, _ = patched_dirs
    last_src = data_dir / "spy_5m_2026-07-01_2026-07-22.csv"
    _mk_spy_csv(last_src, "2026-07-22", _rth_bars(78, 500, 500.5, 499.5, 500))
    frag_src = data_dir / "spy_5m_2026-07-01_2026-07-23.csv"
    _mk_spy_csv(frag_src, "2026-07-23", _rth_bars(12, 505, 506, 504, 505))  # < 30 bars

    original = _base_original("2026-07-22", last_src.name)
    ext = bdi._extend_new_days(original)

    assert ext["forward_days"] == []
    assert len(ext["days"]) == 1  # fragment day NOT added to days[]
    assert {"date": "2026-07-23", "n_rth_bars": 12} in ext["excluded_fragments"]


def test_extend_marks_partial_day(patched_dirs):
    data_dir, _ = patched_dirs
    last_src = data_dir / "spy_5m_2026-07-01_2026-07-22.csv"
    _mk_spy_csv(last_src, "2026-07-22", _rth_bars(78, 500, 500.5, 499.5, 500))
    partial_src = data_dir / "spy_5m_2026-07-01_2026-07-23.csv"
    _mk_spy_csv(partial_src, "2026-07-23", _rth_bars(50, 505, 506, 504, 505))  # 30<=n<70

    original = _base_original("2026-07-22", last_src.name)
    ext = bdi._extend_new_days(original)

    assert ext["forward_days"] == ["2026-07-23"]
    assert ext["days"][-1]["partial"] is True


@pytest.mark.parametrize("day_vix,expected", [
    (14.9, "low"), (15.0, "mid"), (19.9, "mid"), (20.0, "elevated"),
    (24.9, "elevated"), (25.0, "high"), (None, None),
])
def test_vix_band_boundaries(day_vix, expected):
    assert bdi._vix_band(day_vix) == expected


@pytest.mark.parametrize("range_ratio,body_frac,expected", [
    (None, None, "unclassified"),
    (1.2, 0.6, "trend"),
    (0.5, 0.9, "chop"),
    (0.9, 0.3, "range"),
    (1.0, 0.5, "trend"),  # boundary: both >= thresholds
])
def test_classify_day_type(range_ratio, body_frac, expected):
    assert bdi._classify_day_type(range_ratio, body_frac) == expected


def test_atr20_needs_min_5_samples():
    assert bdi._atr20([1.0, 2.0]) is None
    assert bdi._atr20([1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(3.0)
    # only last 20 count
    assert bdi._atr20(list(range(1, 31))) == pytest.approx(sum(range(11, 31)) / 20)
