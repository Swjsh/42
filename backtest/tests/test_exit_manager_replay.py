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

# Pinned baseline. See analysis/recommendations/exit-manager-replay-2026-07-17.json.
#
# RE-PINNED 2026-08-15, with the drift EXPLAINED rather than absorbed.
#
# This harness reads LIVE automation/state/params.json + fleet/strategies.py, so its numbers
# move whenever exit config ships. Between the original pin (2026-07-17) and now, four
# J-directed exit changes landed -- the PRE-TP1 PROFIT RATCHET (1a9b1409), J's LADDER
# (af6cf286), the trail arm moved +40% -> +75% (658ecc79), and the ribbon confirmation buffer
# (20a9e792, implemented NOT armed). The pin was never moved with them, so it sat RED and
# detected nothing thereafter.
#
# WHAT THE DRIFT ACTUALLY IS -- the one number worth a human's attention:
#   ("bold", "13:51:21")  177.4 -> 114.0, and it is now the ONE unfaithful trade (5/6).
#   Its replay exit is `premium_stop @ 0.61`, while the LIVE trade made $191.
#   Today's exit config would have cut that real winner by ~40%.
# That is the pre-TP1 ratchet's INTENDED shape (lock profit earlier, cap the runner), so it is
# a trade-off, not self-evidently a bug -- but it is n=1 and it has never been measured across
# a population. Filed in STATUS.md; the question "does the ratchet cost more than it saves"
# needs its own pre-registered study, NOT an adjudication on one trade.
#
# HOW TO MAINTAIN THIS PIN: re-derive it whenever exit config ships, in the SAME commit, and
# state what moved and why -- as here. Do not silently re-pin: the delta IS the signal, and a
# pin quietly dragged to today's numbers is how a real exit regression would slip through.
PINNED_PER_TRADE_PNL = {
    ("safe", "11:06:03"): -46.0,
    ("safe", "11:40:04"): -102.0,
    ("safe", "13:01:03"): 246.3,
    ("bold", "13:51:21"): 114.0,   # was 177.4 -- pre-TP1 ratchet, premium_stop @ 0.61
    ("safe", "14:03:03"): 112.15,
    ("safe", "14:49:03"): -63.0,
}
PINNED_N_FAITHFUL = 5              # was 6 -- the bold trade above is the unfaithful one
PINNED_N_SCORED = 6
PINNED_ALL_FAITHFUL = False        # was True, for the same single trade
PINNED_TOTAL_DELTA = -80.55        # was -17.15; the -63.4 move is that trade


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
