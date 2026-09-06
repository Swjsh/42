"""test_wave_day_conditions_2026_09_05.py -- GOAL-WAVE-DAY-CONDITIONS-2026-09-05 W4.

Guards `setup/scripts/wave_day_conditions.py`:

1. FAIL-OPEN ON MISSING INPUTS (C7): a date with no cached SPY/VIX bars, no
   right-tail CAPTURE file, and no journal entry must still produce a full row
   with every field present, every unavailable field null + a `reason`
   string -- and MUST NOT raise. This is the literal DONE-WHEN text: "the
   script runs on a day with missing inputs and writes a row with nulls
   (never crashes)".

2. LEDGER JOIN CORRECTNESS: a known August wave day (2026-08-04, doctrine's
   own worked example -- edge-master-doctrine.md "August 2026 big-day
   anatomy") must join to `wave: True` via the real
   `analysis/right-tail/CAPTURE-2026-08-04.json` on disk, proving the
   wave_label() -> CAPTURE-<date>.json join actually reads the real ledger
   artifact this goal's DONE-WHEN names, not a stub.

RED-PROOF: both tests fail on the pre-fix code path -- test 1 would raise
(KeyError/FileNotFoundError propagating out of an un-guarded field
calculator) before the fail-open wrapping in each `_..._` helper; test 2
would read `wave: None` if `wave_label()` looked at the wrong file / wrong
key (`n_waves_meeting_threshold` vs `n_waves_all`, the exact bug class this
goal's sibling `right_tail_waves.py` module docstring documents at length
for the underlying wave detector).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import wave_day_conditions as w  # noqa: E402

FAR_FUTURE_DATE = "2099-01-04"  # a Sunday; guaranteed no cache/ledger/journal coverage
KNOWN_WAVE_DATE = "2026-08-04"  # doctrine's own worked example, real CAPTURE file on disk


def test_missing_inputs_never_crashes_and_nulls_every_unavailable_field():
    """A date with zero cached coverage anywhere (SPY, VIX, key-levels, journal,
    right-tail CAPTURE) must not raise, and every field that cannot be computed
    must be null with a `reason` string attached -- never a fabricated number."""
    row = w.build_row(FAR_FUTURE_DATE)  # must not raise

    assert row["date"] == FAR_FUTURE_DATE
    assert row["day_of_week"] == "Sunday"

    assert row["wave"]["wave"] is None
    assert isinstance(row["wave"].get("reason"), str) and row["wave"]["reason"]

    assert row["overnight_gap_pct"]["value"] is None
    assert isinstance(row["overnight_gap_pct"].get("reason"), str) and row["overnight_gap_pct"]["reason"]

    assert row["first15_range_over_atr20"]["first_15min_range"] is None
    assert row["first15_range_over_atr20"]["atr20"] is None
    assert row["first15_range_over_atr20"]["ratio"] is None
    assert isinstance(row["first15_range_over_atr20"].get("reason"), str)

    assert row["vix"]["opening_vs_prior_close"]["value"] is None
    assert isinstance(row["vix"]["opening_vs_prior_close"].get("reason"), str)
    assert row["vix"]["vix_5day_slope"]["value"] is None
    assert isinstance(row["vix"]["vix_5day_slope"].get("reason"), str)

    assert row["prior_day_close_vs_vwap_pct"]["value"] is None
    assert isinstance(row["prior_day_close_vs_vwap_pct"].get("reason"), str)

    assert row["distance_to_nearest_zone"]["value"] is None
    assert isinstance(row["distance_to_nearest_zone"].get("reason"), str)

    assert row["premarket_bias"]["classified"] is None
    assert isinstance(row["premarket_bias"].get("reason"), str)

    assert row["bias_called_direction"]["value"] is None
    assert isinstance(row["bias_called_direction"].get("reason"), str)

    # atr20_definition is a static disclosure string, always present regardless of data
    assert row["atr20_definition"]


def test_append_row_on_missing_inputs_writes_valid_jsonl_line(tmp_path):
    """The append path (what the scheduled task actually calls) must also
    survive a missing-inputs date end-to-end: one valid JSON line written,
    no exception."""
    import json
    out = tmp_path / "wave-day-conditions-test.jsonl"
    row = w.append_row(FAR_FUTURE_DATE, path=out)
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["date"] == FAR_FUTURE_DATE
    assert parsed["wave"]["wave"] is None
    assert row["generated_at_et"]  # stamped from et_clock, never left blank


def test_known_august_wave_day_joins_to_wave_true():
    """2026-08-04 (doctrine's own worked example, edge-master-doctrine.md
    'August 2026 big-day anatomy') must resolve wave=True via the real
    analysis/right-tail/CAPTURE-2026-08-04.json on disk -- proves the join
    reads n_waves_meeting_threshold (the >=1.3x-priced waves), not merely
    n_waves_all (raw ENTER ticks before pricing/threshold filtering)."""
    capture_path = REPO / "analysis" / "right-tail" / f"CAPTURE-{KNOWN_WAVE_DATE}.json"
    assert capture_path.exists(), (
        f"fixture precondition missing: {capture_path} must exist on disk for this "
        "guard to prove a real join (not a stub) -- if right_tail_capture.py's output "
        "layout changed, update this test's fixture path, don't skip the assertion."
    )

    info = w.wave_label(KNOWN_WAVE_DATE)
    assert info["wave"] is True
    assert info["n_waves_meeting_threshold"] is not None and info["n_waves_meeting_threshold"] >= 1
    # n_waves_all must be >= n_waves_meeting_threshold -- catches a swapped-field bug
    # where the join reads the wrong count.
    assert info["n_waves_all"] >= info["n_waves_meeting_threshold"]

    row = w.build_row(KNOWN_WAVE_DATE)
    assert row["wave"]["wave"] is True


def test_known_no_wave_day_joins_to_wave_false():
    """2026-08-26 has a real CAPTURE file with n_waves_all==2 but
    n_waves_meeting_threshold==0 (2 raw ENTER ticks, neither priced >=1.3x) --
    the sharper discriminator: a naive n_waves_all>=1 join would wrongly read
    this as a wave day. Must join to wave=False, not None or True."""
    no_wave_date = "2026-08-26"
    capture_path = REPO / "analysis" / "right-tail" / f"CAPTURE-{no_wave_date}.json"
    assert capture_path.exists(), f"fixture precondition missing: {capture_path}"

    info = w.wave_label(no_wave_date)
    assert info["n_waves_meeting_threshold"] == 0
    assert info["wave"] is False


# GOAL-WAVE-DAY-CONDITIONS-2026-09-05 W5: second, narrower outcome label (big_day,
# >=2.0x priced peak_multiple) -- RED-PROOF: pre-fix `wave_label()` had no `big_day`
# key at all, so `info["big_day"]` would raise KeyError on every one of these.

def test_known_august_2x_anchor_day_labels_big_day_true():
    """2026-08-04 (doctrine's own worked example) has waves priced at 5.44x/5.90x/
    3.01x peak_multiple in the real CAPTURE-2026-08-04.json on disk -- all comfortably
    clear BIG_DAY_THRESHOLD=2.0. Must label big_day=True with a positive count, not
    merely truthy via n_waves_meeting_threshold (a 1.3x-only day must NOT satisfy
    this by accident -- see the next test)."""
    capture_path = REPO / "analysis" / "right-tail" / f"CAPTURE-{KNOWN_WAVE_DATE}.json"
    assert capture_path.exists(), f"fixture precondition missing: {capture_path}"

    info = w.wave_label(KNOWN_WAVE_DATE)
    assert info["big_day"] is True
    assert info["n_waves_meeting_big_day_threshold"] >= 1
    assert info["big_day_threshold"] == w.BIG_DAY_THRESHOLD
    # the anchor day's own peak_multiples (from the real capture file) must include
    # at least one value >= threshold -- proves the filter actually ran over real numbers.
    import json as _json
    raw = _json.loads(capture_path.read_text(encoding="utf-8"))
    real_peaks = [wv.get("peak_multiple") for wv in raw.get("waves", []) if wv.get("computed")]
    assert any(p is not None and p >= w.BIG_DAY_THRESHOLD for p in real_peaks)

    row = w.build_row(KNOWN_WAVE_DATE)
    assert row["wave"]["big_day"] is True


def test_1p3x_only_day_does_not_satisfy_big_day():
    """2026-08-06 is a real doctrine top-5 dollar day (edge-master-doctrine.md) whose
    single wave peaked at 1.85x -- clears the 1.3x wave gate (wave=True) but must NOT
    satisfy the narrower 2.0x big_day gate. Discriminates against a bug where big_day
    is computed from n_waves_meeting_threshold (the 1.3x set) instead of its own
    peak_multiple >= 2.0 filter -- the exact mismatch this goal's W5 item exists to
    surface (doctrine's dollar-outlier days are not identical to any-wave->=2x-peak
    days)."""
    date_1p3x_only = "2026-08-06"
    capture_path = REPO / "analysis" / "right-tail" / f"CAPTURE-{date_1p3x_only}.json"
    assert capture_path.exists(), f"fixture precondition missing: {capture_path}"

    info = w.wave_label(date_1p3x_only)
    assert info["wave"] is True  # clears the 1.3x gate
    assert info["big_day"] is False  # does NOT clear the 2.0x gate
    assert info["n_waves_meeting_big_day_threshold"] == 0


def test_missing_capture_file_degrades_big_day_to_null_with_reason():
    """The far-future / no-coverage date must null out big_day alongside wave --
    never crash, never silently default to False (which would be indistinguishable
    from a real 'checked and no wave reached 2x' verdict)."""
    info = w.wave_label(FAR_FUTURE_DATE)
    assert info["big_day"] is None
    assert info["n_waves_meeting_big_day_threshold"] is None
    assert info["big_day_threshold"] == w.BIG_DAY_THRESHOLD
    assert isinstance(info.get("reason"), str) and info["reason"]
