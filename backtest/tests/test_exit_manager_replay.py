"""Guard for backtest/tools/exit_manager_replay.py (GOAL-REPLAY-TODAY-GREEN iteration 6,
EXIT-MANAGER-REPLAY-HARNESS). Load-bearing invariants:

  1. FAITHFULNESS WIN PIN: this is the first harness in the goal's history to drive the REAL
     exit_manager.plan_exit_actions (not simulate_trade_real) over today's real 1-min OPRA
     bars. Pinned result: 6/6 core engine-fireable entries within tolerance (iteration 2 was
     0/5, iteration 3 was 2/5 trivial-only). If a future edit regresses this silently, that is
     exactly the "silent success is failure" failure mode (C7) this pin exists to catch.
  2. STRUCTURE-STOP IS EXERCISED: at least one entry must resolve stop_mode="structure" and
     exit via a "structure_stop"-stage leg -- proves last_closed_5m_close is actually wired
     end-to-end, not silently None on every tick (which would make structure mode inert and
     collapse to the catastrophe cap, the exact gap hold_posture_ab_study.py disclosed and
     this harness exists to close).
  3. POINT-SAMPLE FIDELITY FIX PIN: backtest/lib/exit_manager_walk.py samples bar OPEN (not
     bar high/low) as the per-tick best/worst premium -- found + tested this build
     (fleet_broker.get_option_quote_hilo is a single NBBO snapshot, not a range-swept value).
     Pinned via the 14:03 bollinger_squeeze trade's exit reason, which flips from a false
     premium_stop (bar-low artifact) to its real runner-stop-driven winning exit under the
     point-sample convention.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_exit_manager_replay.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "tools", FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

HIRES_DIR = REPO / "backtest" / "data" / "highres"
_DATA_AVAILABLE = (HIRES_DIR / "SPY_1m_2026-07-17.csv").exists()

pytestmark = pytest.mark.skipif(
    not _DATA_AVAILABLE,
    reason="today's 1-min OPRA cache (backtest/data/highres/) not present in this checkout")

# Pinned baseline (iteration 6, 2026-07-17 after-hours). See
# analysis/recommendations/exit-manager-replay-2026-07-17.json for the full record.
PINNED_PER_TRADE_PNL = {
    ("safe", "11:06:03"): -46.0,
    ("safe", "11:40:04"): -102.0,
    ("safe", "13:01:03"): 246.3,
    ("bold", "13:51:21"): 177.4,
    ("safe", "14:03:03"): 112.15,
    ("safe", "14:49:03"): -63.0,
}
PINNED_N_FAITHFUL = 6
PINNED_N_SCORED = 6
PINNED_ALL_FAITHFUL = True
PINNED_TOTAL_DELTA = -17.15


def _run():
    import exit_manager_replay as emr
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = emr.main()
    assert rc == 0
    import json
    return json.loads(emr.OUT_JSON.read_text(encoding="utf-8"))


def test_faithfulness_pin():
    out = _run()
    assert out["n_faithful"] == PINNED_N_FAITHFUL
    assert out["n_scored"] == PINNED_N_SCORED
    assert out["all_faithful"] == PINNED_ALL_FAITHFUL
    assert out["total_delta"] == pytest.approx(PINNED_TOTAL_DELTA, abs=0.01)


def test_per_trade_pnl_pin():
    out = _run()
    seen = {(t["account_id"], t["entry_time_et"][11:19]): t["replay_dollar_pnl"] for t in out["trades"]}
    for key, expected in PINNED_PER_TRADE_PNL.items():
        assert key in seen, f"missing pinned trade {key}"
        assert seen[key] == pytest.approx(expected, abs=0.01), f"{key} drifted from pinned {expected}"


def test_structure_stop_actually_exercised():
    out = _run()
    structure_trades = [t for t in out["trades"] if t["resolved_stop_mode"] == "structure"]
    assert len(structure_trades) >= 4, "expected the majority of today's ribbon_ride entries to resolve structure mode"
    structure_exits = [t for t in structure_trades if "structure_stop" in (t["exit_reason"] or "")]
    assert len(structure_exits) >= 1, (
        "no trade actually EXITED via structure_stop -- last_closed_5m_close may be silently "
        "None every tick, collapsing structure mode to the catastrophe cap")


def test_point_sample_fixes_bollinger_trade():
    out = _run()
    boll = next(t for t in out["trades"] if t["entry_time_et"][11:19] == "14:03:03")
    assert boll["replay_dollar_pnl"] > 0, (
        "bollinger_squeeze trade should be a real winner under point-sample premiums; a "
        "negative value suggests the bar-high/low over-triggering artifact regressed")
    assert "premium_stop" not in (boll["exit_reason"] or "")
