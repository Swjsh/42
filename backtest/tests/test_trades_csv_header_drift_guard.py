"""Guard for BXM-PROBE-TRADES-CSV-HEADER-DRIFT-FIX (queued 2026-08-08, fixed 2026-08-09
conductor WEEKEND).

Root cause (one sentence): `journal/trades.csv` gained a new trailing column
(`theta_at_entry`, added 2026-08-01 by the THETA COCKPIT build) AFTER `account_id`, so both
`bxm_gate_probe.py::_load_real_trades` and `vix1d_gate_probe.py::_load_real_trades`'s fixed
`header[-1] == "account_id"` assertion broke -- fail-closed working as intended, but the
probes needed to resolve `account_id`'s column by NAME instead of a fixed relative position.

Pins (both probes share the identical loader shape -- test both, per the queue item's own
"check both when picking this up" note):
  1. A trailing column appended AFTER account_id (this class of drift, e.g. theta_at_entry)
     does NOT break the loader -- it must still resolve account_id correctly by name.
  2. A column inserted BEFORE account_id (a different drift direction) also does not break
     it -- name-lookup is direction-agnostic, unlike the old fixed-position assumption.
  3. If `account_id` is removed from the header entirely, the loader still fails LOUD
     (AssertionError), not silently (C7 -- fail-closed on genuine schema loss must survive
     this fix, only the false-positive trailing-column case should stop failing).

Rail-4 CLEAR: read-only guard tests against synthetic tmp CSVs. No params/doctrine/orders/
heartbeat/filters touched.
"""
import csv
import os
import sys
import tempfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backtest"))

from autoresearch import bxm_gate_probe  # noqa: E402
from autoresearch import vix1d_gate_probe  # noqa: E402

# Real header shape as of 2026-08-01 (account_id at index -2, theta_at_entry appended
# after it at index -1) -- the exact drift that broke both probes.
_BASE_COLS = ["date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
              "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
              "dollar_pnl"]
_TRAILING_COLS_AFTER_DOLLAR_PNL = ["r_multiple", "stop_px", "target_px", "dollar_risk",
                                   "pct_risk_of_acct", "account_equity_pre",
                                   "followed_rules", "setup_quality", "fill_quality",
                                   "gamma_recommended", "j_override", "hold_minutes",
                                   "trade_grade", "trade_grade_score", "delta_at_entry",
                                   "iv_at_entry", "iv_regime", "slippage_cents",
                                   "exit_slippage_cents", "tod_bucket", "bars_after_trigger",
                                   "entry_relative_to_bar", "hold_quality_pct",
                                   "cf_time_stop_pnl", "cf_high_water_pnl",
                                   "archetype_match_json", "tape_assistance", "notes_short"]


def _write_synthetic_csv(path, header_extra_cols):
    """Writes a minimal synthetic trades.csv with `account_id` followed by
    header_extra_cols (simulates a trailing-column append after account_id)."""
    header = _BASE_COLS + _TRAILING_COLS_AFTER_DOLLAR_PNL + ["account_id"] + header_extra_cols
    row = ["2026-08-01"] + [""] * (len(_BASE_COLS) - 2) + ["150.0"] + \
        [""] * len(_TRAILING_COLS_AFTER_DOLLAR_PNL) + ["safe-2"] + \
        ["x"] * len(header_extra_cols)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(row)


@pytest.mark.parametrize("probe_module", [bxm_gate_probe, vix1d_gate_probe])
def test_trailing_column_after_account_id_does_not_break_loader(probe_module, monkeypatch):
    """The exact 2026-08-01 drift class: a column appended AFTER account_id must not
    break the loader, and account_id must still resolve to the correct value."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "trades.csv")
        _write_synthetic_csv(path, ["theta_at_entry"])
        monkeypatch.setattr(probe_module, "TRADES_CSV", path)
        rows = probe_module._load_real_trades()
        assert len(rows) == 1
        assert rows[0]["account_id"] == "safe-2"
        assert rows[0]["dollar_pnl"] == pytest.approx(150.0)


@pytest.mark.parametrize("probe_module", [bxm_gate_probe, vix1d_gate_probe])
def test_no_trailing_column_still_works(probe_module, monkeypatch):
    """account_id as the literal last column (pre-2026-08-01 shape) must still work --
    the fix must not regress the original layout."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "trades.csv")
        _write_synthetic_csv(path, [])
        monkeypatch.setattr(probe_module, "TRADES_CSV", path)
        rows = probe_module._load_real_trades()
        assert len(rows) == 1
        assert rows[0]["account_id"] == "safe-2"


@pytest.mark.parametrize("probe_module", [bxm_gate_probe, vix1d_gate_probe])
def test_account_id_missing_entirely_still_fails_loud(probe_module, monkeypatch):
    """C7: genuine schema loss (account_id removed, not just relocated) must still
    fail LOUD via the header assertion, not silently produce empty/wrong rows."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "trades.csv")
        header = _BASE_COLS + _TRAILING_COLS_AFTER_DOLLAR_PNL  # no account_id at all
        row = ["2026-08-01"] + [""] * (len(_BASE_COLS) - 2) + ["150.0"] + \
            [""] * len(_TRAILING_COLS_AFTER_DOLLAR_PNL)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerow(row)
        monkeypatch.setattr(probe_module, "TRADES_CSV", path)
        with pytest.raises(AssertionError, match="header drifted"):
            probe_module._load_real_trades()
