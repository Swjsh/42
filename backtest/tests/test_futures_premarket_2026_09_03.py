"""Guard suite for backtest/futures/futures_premarket.py (queue item
FUTURES-PREMARKET-PRODUCER-MISSING, 2026-09-03).

Covers: output schema fields present on both files, the DATA_MISSING path never
fabricates a numeric level, computed levels sit in the MES sanity band, `for_session`
equals the next RTH session date computed from ET, and the whole pipeline is
deterministic (two runs on identical input produce identical output apart from
`as_of`).

Bar data is always injected via `bars=`/`bars_by_instrument=` -- no network call, no
touching the real live-cache CSVs or automation/state/futures/*.json.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from futures import futures_premarket as fp  # noqa: E402

TZ = "America/New_York"


# ── helpers ──────────────────────────────────────────────────────────────────

def _bar(ts_str: str, o: float, h: float, l: float, c: float, v: float = 100.0) -> dict:
    return {
        "timestamp_et": pd.Timestamp(ts_str, tz=TZ),
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def _mes_bars_normal() -> pd.DataFrame:
    """One prior RTH session (2026-09-02, Wed) + a few overnight GLOBEX bars leading
    into premarket on 2026-09-03 (Thu). All prices sit inside the MES 3000-9000 band."""
    rows = [
        # prior RTH session 09:30-16:00 ET on 2026-09-02
        _bar("2026-09-02 09:30", 5500.0, 5510.0, 5495.0, 5505.0),
        _bar("2026-09-02 12:00", 5505.0, 5520.0, 5500.0, 5515.0),
        _bar("2026-09-02 15:55", 5515.0, 5525.0, 5510.0, 5520.0),  # PDH=5525 PDL=5495 PDC=5520
        # overnight GLOBEX bars after the 16:00 ET close, before 08:35 ET premarket next day
        _bar("2026-09-02 18:00", 5520.0, 5522.0, 5518.0, 5521.0),
        _bar("2026-09-03 03:00", 5521.0, 5560.0, 5519.0, 5555.0),  # ONH=5560
        _bar("2026-09-03 08:00", 5555.0, 5556.0, 5540.0, 5545.0),  # ONL among overnight=5518 (from 18:00 bar)
    ]
    return pd.DataFrame(rows)


NOW_ET = dt.datetime(2026, 9, 3, 8, 35, 0)  # Thursday, before RTH open


# ── schema fields present ───────────────────────────────────────────────────

def test_top_level_schema_fields_present_both_files():
    key_levels_doc, today_bias_doc = fp.build(
        ["MES"], NOW_ET, offline=True, bars_by_instrument={"MES": _mes_bars_normal()},
    )
    for doc in (key_levels_doc, today_bias_doc):
        for field in ("schema_version", "as_of", "for_session", "computed_from"):
            assert field in doc, f"missing top-level field {field!r} in {doc}"
    assert "instruments" in key_levels_doc
    assert "instruments" in today_bias_doc


def test_normal_case_status_ok_and_levels_populated():
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=_mes_bars_normal())
    assert lv["status"] == "OK"
    assert lv["prior_high"] == pytest.approx(5525.0)
    assert lv["prior_low"] == pytest.approx(5495.0)
    assert lv["prior_close"] == pytest.approx(5520.0)
    assert len(lv["levels"]) >= 3  # PDH, PDL, PDC at minimum

    bias = fp.compute_bias(lv)
    assert bias["status"] == "OK"
    assert bias["bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= bias["confidence"] <= 1.0
    assert "method" in bias and "range_frac" in bias["method"]
    # NO narrative prose: method is a formula string, and there is no "reasoning"/"note"
    # narrative key on the bias doc.
    assert "bias_note" not in bias
    assert "reasoning" not in bias


# ── DATA_MISSING never fabricates ───────────────────────────────────────────

def test_empty_bars_yields_data_missing_no_fabrication():
    empty = pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=empty)
    assert lv["status"] == "DATA_MISSING"
    assert "reason" in lv and lv["reason"]
    for forbidden in ("levels", "prior_close", "prior_high", "prior_low",
                      "overnight_high", "overnight_low", "prior_rth_vwap"):
        assert forbidden not in lv, f"DATA_MISSING block fabricated field {forbidden!r}"

    bias = fp.compute_bias(lv)
    assert bias["status"] == "DATA_MISSING"
    for forbidden in ("bias", "confidence", "overnight_change_pts", "falsifiable_predictions"):
        assert forbidden not in bias, f"DATA_MISSING bias block fabricated field {forbidden!r}"


def test_no_prior_session_bars_yields_data_missing():
    """Bars exist but none fall in the prior RTH session window -- e.g. cache only
    holds today's premarket bars, nothing from yesterday's RTH."""
    rows = [_bar("2026-09-03 08:00", 5555.0, 5556.0, 5540.0, 5545.0)]
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=pd.DataFrame(rows))
    assert lv["status"] == "DATA_MISSING"
    assert "prior session" in lv["reason"]


def test_no_overnight_bar_yet_yields_data_missing_bias_only():
    """Levels compute fine (prior RTH session present) but nothing overnight yet --
    bias must refuse rather than guess a direction from no data."""
    rows = [
        _bar("2026-09-02 09:30", 5500.0, 5510.0, 5495.0, 5505.0),
        _bar("2026-09-02 15:55", 5515.0, 5525.0, 5510.0, 5520.0),
    ]
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=pd.DataFrame(rows))
    assert lv["status"] == "OK"
    bias = fp.compute_bias(lv)
    assert bias["status"] == "DATA_MISSING"
    assert "overnight" in bias["reason"]


# ── MES sanity band ──────────────────────────────────────────────────────────

def test_mes_levels_are_mes_scale_when_present():
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=_mes_bars_normal())
    assert lv["status"] == "OK"
    low, high = fp.SANITY_BANDS["MES"]
    for level in lv["levels"]:
        assert low <= level["price"] <= high, f"level {level} outside MES sanity band {low}-{high}"
    assert low <= lv["prior_close"] <= high


def test_garbled_out_of_band_price_refuses_publication():
    """A prior-session bar with an obviously wrong (SPY-scale, not MES-scale) price
    must never be published as a level."""
    rows = [
        _bar("2026-09-02 09:30", 700.0, 705.0, 698.0, 702.0),   # SPY-scale, not MES-scale
        _bar("2026-09-02 15:55", 702.0, 706.0, 700.0, 703.0),
        _bar("2026-09-03 08:00", 703.0, 704.0, 701.0, 702.5),
    ]
    lv = fp.compute_instrument("MES", NOW_ET, offline=True, bars=pd.DataFrame(rows))
    assert lv["status"] == "DATA_MISSING"
    assert "sanity band" in lv["reason"]


# ── for_session == next RTH session date computed from ET ──────────────────

def test_for_session_same_day_when_before_rth_close_on_a_weekday(monkeypatch):
    monkeypatch.setattr(fp, "is_holiday", lambda _dt: False)
    now = dt.datetime(2026, 9, 3, 8, 35, 0)  # Thursday, before 09:30
    assert fp.next_rth_session_date(now) == dt.date(2026, 9, 3)


def test_for_session_rolls_to_next_weekday_after_rth_close(monkeypatch):
    monkeypatch.setattr(fp, "is_holiday", lambda _dt: False)
    now = dt.datetime(2026, 9, 3, 17, 0, 0)  # Thursday, after 16:00 RTH close
    assert fp.next_rth_session_date(now) == dt.date(2026, 9, 4)  # Friday


def test_for_session_rolls_past_weekend(monkeypatch):
    monkeypatch.setattr(fp, "is_holiday", lambda _dt: False)
    now = dt.datetime(2026, 9, 5, 8, 0, 0)  # Saturday morning (before RTH_END, so the
    # weekday gate is the ONLY thing preventing "today" from being treated as valid)
    assert fp.next_rth_session_date(now) == dt.date(2026, 9, 7)  # Monday


def test_prior_rth_session_date_skips_weekend():
    assert fp.prior_rth_session_date(dt.date(2026, 9, 7)) == dt.date(2026, 9, 4)  # Mon -> Fri


# ── determinism ──────────────────────────────────────────────────────────────

def test_build_is_deterministic_apart_from_as_of():
    bars = {"MES": _mes_bars_normal()}
    kl1, tb1 = fp.build(["MES"], NOW_ET, offline=True, bars_by_instrument=bars)
    kl2, tb2 = fp.build(["MES"], NOW_ET, offline=True, bars_by_instrument=bars)

    kl1_c, kl2_c = dict(kl1), dict(kl2)
    tb1_c, tb2_c = dict(tb1), dict(tb2)
    for d in (kl1_c, kl2_c, tb1_c, tb2_c):
        d.pop("as_of", None)
    assert kl1_c == kl2_c
    assert tb1_c == tb2_c


def test_main_writes_files_deterministically(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "KEY_LEVELS_OUT", tmp_path / "key-levels.json")
    monkeypatch.setattr(fp, "TODAY_BIAS_OUT", tmp_path / "today-bias.json")

    def fake_load_bars(root, offline):
        return _mes_bars_normal() if root == "MES" else pd.DataFrame(
            columns=["timestamp_et", "open", "high", "low", "close", "volume"])

    monkeypatch.setattr(fp, "_load_bars", fake_load_bars)

    rc = fp.main(["--instruments", "MES,MNQ", "--offline", "--now", "2026-09-03T08:35:00"])
    assert rc == 0
    assert (tmp_path / "key-levels.json").exists()
    assert (tmp_path / "today-bias.json").exists()

    import json
    kl = json.loads((tmp_path / "key-levels.json").read_text(encoding="utf-8"))
    assert kl["instruments"]["MES"]["status"] == "OK"
    assert kl["instruments"]["MNQ"]["status"] == "DATA_MISSING"  # empty bars injected for MNQ


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
