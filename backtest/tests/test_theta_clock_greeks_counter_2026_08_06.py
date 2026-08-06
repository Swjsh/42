"""D7 guard -- theta_clock's empty-greeks disclosure is a LIVE counter, not prose.

THE DEFECT: the per-row `greeks_source` string hardcoded "empty on 29/29 real entries to
date" -- a figure grepped once at build time and frozen into the source (theta_clock.py
~L320-322). Every session after the build it drifted further from truth while still
claiming "to date".

THE FIX PINNED HERE: greeks_source_label() renders from a persisted probe counter
(theta-clock/greeks-probe-stats.json) that run_once updates on EVERY greeks probe; the
literal "29/29" render is gone.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_theta_clock_greeks_counter_2026_08_06.py
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "setup" / "scripts"), str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture()
def tc():
    return importlib.import_module("theta_clock")


def test_label_renders_live_counter(tc):
    label = tc.greeks_source_label({}, {"empty": 41, "nonempty": 1})
    assert "41/42" in label and "live counter" in label
    assert "29/29" not in label


def test_label_without_stats_has_no_fabricated_number(tc):
    label = tc.greeks_source_label(None, None)
    assert "unavailable" in label
    assert "29/29" not in label and "/" not in label.split("(")[-1].split()[0]


def test_label_with_real_greeks_is_broker_snapshot(tc):
    assert tc.greeks_source_label({"theta": -0.5}, {"empty": 10, "nonempty": 2}) == "broker_snapshot"


def test_row_render_carries_no_hardcoded_29_29(tc):
    """The compute_row output itself must never carry the frozen figure again."""
    row = tc.compute_row(arm="safe-2",
                          position={"symbol": "SPY260806P00770000", "qty": "3",
                                    "avg_entry_price": "1.00", "current_price": "0.95"},
                          quote={"bid": 0.9, "ask": 1.0, "mid": 0.95}, greeks=None,
                          entry_snap={"entry_premium": 1.00, "entry_spot": 770.0,
                                      "mins_to_close_at_entry": 120.0},
                          spot_now=769.5, now_et=datetime(2026, 8, 6, 14, 30),
                          greeks_probe_stats={"empty": 3, "nonempty": 0})
    assert "29/29" not in row["greeks_source"]
    assert "3/3" in row["greeks_source"]


def test_run_once_persists_the_probe_counter(tc, tmp_path):
    """Integration: one tick with an empty-greeks probe increments + persists the counter,
    and the appended row's greeks_source cites it."""
    theta_dir = tmp_path / "theta-clock"
    summary = tc.run_once(
        now_et=datetime(2026, 8, 6, 14, 30),
        creds_by_arm={"safe-2": {"key": "k", "secret": "s"}},
        active_arms=["safe-2"],
        positions_fn=lambda arm, creds: [{"symbol": "SPY260806P00770000", "qty": "3",
                                           "avg_entry_price": "1.00", "current_price": "0.95"}],
        greeks_fn=lambda creds, symbol: {},          # the empirically-common empty probe
        quote_fn=lambda creds, symbol: {"bid": 0.9, "ask": 1.0, "mid": 0.95},
        spot_fn=lambda: (770.0, "test"),
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=theta_dir,
        status_md_path=tmp_path / "STATUS.md",
    )
    assert summary["n_positions"] == 1
    stats = json.loads((theta_dir / "greeks-probe-stats.json").read_text(encoding="utf-8"))
    assert stats["empty"] == 1 and stats["nonempty"] == 0
    assert "1/1" in summary["positions"][0]["greeks_source"]
    # second tick accumulates
    tc.run_once(
        now_et=datetime(2026, 8, 6, 14, 31),
        creds_by_arm={"safe-2": {"key": "k", "secret": "s"}},
        active_arms=["safe-2"],
        positions_fn=lambda arm, creds: [{"symbol": "SPY260806P00770000", "qty": "3",
                                           "avg_entry_price": "1.00", "current_price": "0.95"}],
        greeks_fn=lambda creds, symbol: {"theta": -0.4},   # a real probe result counts too
        quote_fn=lambda creds, symbol: {"bid": 0.9, "ask": 1.0, "mid": 0.95},
        spot_fn=lambda: (770.0, "test"),
        state_path=tmp_path / "position-state.json",
        snapshot_path=tmp_path / "theta-clock.json",
        theta_dir=theta_dir,
        status_md_path=tmp_path / "STATUS.md",
    )
    stats2 = json.loads((theta_dir / "greeks-probe-stats.json").read_text(encoding="utf-8"))
    assert stats2["empty"] == 1 and stats2["nonempty"] == 1


def test_source_has_no_hardcoded_render(tc):
    """Static pin: the greeks_source assignment must route through greeks_source_label --
    re-hardcoding a prose figure REDs here."""
    src = (ROOT / "setup" / "scripts" / "theta_clock.py").read_text(encoding="utf-8")
    render_zone = src[src.index("def compute_row"):src.index("def check_stall_alert")]
    assert "greeks_source_label(" in render_zone
    assert "29/29 real entries to date" not in render_zone
