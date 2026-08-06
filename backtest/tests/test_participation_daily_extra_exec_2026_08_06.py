"""D6 guards (2026-08-06) -- participation_daily / participation_cascade truth pins.

CLAIM ADJUDICATED: EOD-2026-08-05-SILENT-ARMS.md item 2 said "participation_daily.py is
still extra_exec-blind (no reference to the field)". REFUTED by a live data test this
session: participation_daily consumes participation_cascade's events, and that classifier's
_extra_exec_events lane (shipped 2026-08-04) flows through -- the real 2026-08-06T14:21:03
extra_exec bollinger_squeeze fill counted as FILLED in account_stats (fills=2), and the
2026-08-03T13:21:03 incident row surfaces too. The 08-05 claim was a source-grep of the
WRONG file (the wrapper, not the classifier it delegates to). Test 1 below pins that
counting end-to-end so the claim can never resurface unnoticed.

REAL RESIDUAL DEFECT FOUND IN ITS PLACE: participation_cascade counted SYNTHETIC ledger
rows (armed=false + core_tick_id=null -- the D3 test-leak rows) as real events; the
2026-08-06T04:16:32 synthetic row showed up as a genuine STALE_TRIGGER enter-verdict in
participation_daily's goal-layer counts. fill_funnel quarantines these (commit 3a953a70);
participation_cascade did not. Test 2 pins the new quarantine + its C7 disclosure counter.

Run:  backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_participation_daily_extra_exec_2026_08_06.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "backtest" / "tools"), str(ROOT / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import participation_cascade as pc  # noqa: E402
import participation_daily as pdaily  # noqa: E402

DAY = "2026-08-06"
SYM = "SPY260806C00769000"


def _write_fixture_ledger(tmp_path: Path) -> Path:
    """A minimal real-shaped core-decisions.jsonl: one production HOLD row carrying a
    REAL extra_exec PLACED order (the 14:21 incident shape), one later row whose exit_pass
    proves the symbol filled, and one SYNTHETIC test-leak row (armed=false,
    core_tick_id=null -- the D3 fingerprint)."""
    rows = [
        # production tick: primary path HOLD, secondary path placed a real order
        {"ts_et": f"{DAY}T14:21:03", "account": "safe", "armed": True,
         "core_tick_id": "tick-1421", "verdict": "HOLD", "action": "HOLD",
         "reason": "no setup passed scoring", "side": None, "setup": None,
         "spy": 768.9, "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED",
                                        "exec": {"symbol": SYM, "side": "C", "qty": 3,
                                                 "status": "PLACED"}}]},
        # later production tick: exit_pass shows the symbol open (broker-truth fill signal)
        {"ts_et": f"{DAY}T14:22:03", "account": "safe", "armed": True,
         "core_tick_id": "tick-1422", "verdict": "HOLD", "action": "HOLD",
         "reason": "no setup passed scoring", "side": None, "setup": None,
         "spy": 768.8, "exit_pass": [{"symbol": SYM, "open_qty": 3, "action": "HOLD"}]},
        # SYNTHETIC leak row (D3 shape): must be quarantined, never an event
        {"ts_et": f"{DAY}T04:16:32", "account": "safe", "armed": False,
         "core_tick_id": None, "verdict": "HOLD",
         "action": "SKIP_STALE_TRIGGER", "reason": "stale trigger bar",
         "spy": 751.0, "vix": 16.0},
    ]
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    p = state_dir / "core-decisions.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    (tmp_path / "fleet").mkdir()
    (tmp_path / "data").mkdir()
    return state_dir


def _cascade_day(tmp_path):
    state_dir = _write_fixture_ledger(tmp_path)
    return pc.compute_cascade_day(DAY, core_glob_dir=state_dir,
                                  fleet_dir=tmp_path / "fleet", data_dir=tmp_path / "data")


def test_extra_exec_fill_counts_in_participation_daily(tmp_path):
    """THE REFUTED-CLAIM PIN: an extra_exec PLACED order on an otherwise-HOLD row must
    count as an attempt AND a fill in participation_daily's goal-layer stats."""
    day = _cascade_day(tmp_path)
    extra_events = [e for e in day["events"]
                    if str(e.get("detail") or "").startswith("extra_exec:")]
    assert len(extra_events) == 1 and extra_events[0]["stage"] == "FILLED"
    stats = pdaily.account_stats(day, "safe-2")
    assert stats["fills"] == 1, (
        f"extra_exec fill not counted (fills={stats['fills']}) -- participation_daily has "
        "gone extra_exec-blind (the refuted 08-05 claim would now be TRUE)")
    assert stats["attempts"] == 1
    assert stats["enter_verdicts"] >= 1


def test_synthetic_rows_are_quarantined_with_disclosure(tmp_path):
    """THE D6 FIX PIN: the armed=false + core_tick_id=null test-leak row must produce ZERO
    events AND be disclosed via n_synthetic_core_rows_excluded (C7 -- never silent)."""
    day = _cascade_day(tmp_path)
    synth_ts_events = [e for e in day["events"] if e["ts_start"] == f"{DAY}T04:16:32"]
    assert synth_ts_events == [], (
        f"synthetic row produced events {synth_ts_events} -- the D6 quarantine is gone; "
        "test-leak rows are polluting participation counts again")
    assert day["n_synthetic_core_rows_excluded"] == 1, (
        "quarantine happened without disclosure (C7: quarantined, not silently dropped)")


def test_real_rows_survive_the_quarantine(tmp_path):
    """Other direction (non-vacuous): production rows (armed present / core_tick_id set)
    must NOT be swallowed by the synthetic predicate."""
    day = _cascade_day(tmp_path)
    real_events = [e for e in day["events"] if e["ts_start"].startswith(f"{DAY}T14:")]
    assert real_events, "the quarantine ate real production rows -- predicate too broad"
