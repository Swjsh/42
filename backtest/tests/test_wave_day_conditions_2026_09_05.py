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
