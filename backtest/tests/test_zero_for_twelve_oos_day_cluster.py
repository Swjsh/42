"""Golden-file guard for zero_for_twelve_oos_day_cluster_2026_08_02.py.

Prevents silent drift on the ZERO-FOR-TWELVE-POSTMORTEM historical-OOS
day-cluster finding (queue.md item, closed the "STILL NOT DONE" historical
half 2026-08-02): re-running the tool must reproduce the same subset_fraction
and pooled-distinct counts on the frozen data window, and the output must be
non-vacuous (real numbers, not an empty/zero result -- C7).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.zero_for_twelve_oos_day_cluster_2026_08_02 import main, OUT  # noqa: E402


def test_runs_and_writes_output():
    rc = main()
    assert rc == 0
    assert OUT.exists()


def test_output_is_non_vacuous_and_matches_frozen_window():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    a = data["vwap_continuation"]
    b = data["vix_regime_dayside"]
    overlap = data["overlap_2026_oos"]

    # Non-vacuous: real signal counts, not zero (C7 -- a check passing on
    # nothing happening is not GREEN).
    assert a["n_oos_signals"] > 0
    assert b["n_oos_signals"] > 0
    assert overlap["shared_day_side_n"] > 0

    # Frozen-window golden values (data window 2025-01-01..2026-07-22, the
    # rolling-append master available at the time this guard was written).
    # If these drift, either the data window advanced (expected -- update the
    # golden values with a note) or the detector logic changed (investigate).
    assert a["n_oos_signals"] == 61
    assert b["n_oos_signals"] == 34
    assert overlap["vix_regime_dayside_oos_day_side_n"] == 34
    assert overlap["shared_day_side_n"] == 32
    assert (
        overlap["vix_regime_dayside_subset_fraction_of_itself_found_in_vwap_continuation"]
        >= 0.90
    ), "the near-total-subset finding (L174, quantified) must not silently regress"


def test_l174_caveat_is_recorded_verbatim():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert "NOT INDEPENDENT" in data["l174_caveat_on_record"]
    assert "vix_regime_dayside" in data["l174_caveat_on_record"] or "subset" in data["l174_caveat_on_record"]
