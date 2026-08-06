"""CHARACTERIZATION TEST -- the vwap_continuation "once per day" flag is PROCESS-scoped,
not DAY-scoped, and the live fleet producer runs in a fresh process every minute.

WHY THIS FILE EXISTS (2026-08-05 EOD, LENS 2 / entries):
  vwap_continuation_watcher.detect_vwap_continuation_setup documents
  "Fires at most ONCE per day ... Per-day state (trend side, fired flag, VIX history)
  resets on date change" and enforces it with the MODULE-GLOBAL `_fired_today`.

  The live fleet path is:
      setup/scripts/run-fleet-executor.ps1   (Windows task, every 1 min 09:30-15:55 ET)
        -> Invoke-PythonHidden automation/state/fleet/build_shared_signal.py   <-- NEW PROCESS
             -> fleet_market.vwap_strategy_block()
                  -> detect_vwap_continuation_setup()

  A new process means a new module import means `_fired_today = False` again. The
  once-per-day contract therefore does NOT hold on the live fleet path. Unlike the CORE
  path (heartbeat_core._route_extra_setups -> exit_actuator.same_bar_cooldown_active,
  backed by the on-disk automation/state/fleet/<arm>/extra-setup-cooldown.json), the fleet
  path persists NO cooldown of any kind.

OBSERVED CONSEQUENCE -- 2026-08-05, broker-verified fills:
  risky-1 and risky-3 each entered SPY260805C00776000 FIVE times between 09:58 and 10:18 ET
  and were stopped out all five (-$485 / -$794). The validated cell
  (analysis/recommendations/j-daily-pattern-LIVE.json, n=153, +$38.3/trade) was measured at
  ONE entry per day. Entries 2-5 are outside the validated population.

CLASS: C12 (stateful detectors need persisted state) + C14 (a knob that is unconditional in
the study but optional/void in production).

TO WHOEVER SHIPS THE FIX (persist `fired` per arm+setup+date on disk, mirroring
exit_actuator.record_entry_bar): INVERT the second test below -- after the fix, a fresh
process on the same day must NOT re-fire. Flipping it is the point; deleting it is not.
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))

from lib.filters import BarContext  # noqa: E402

CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-05.csv"
DAY = "2026-08-05"


def _rth_frame() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df = df[df["timestamp_et"].astype(str).str.startswith(DAY)].copy()
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    t = df["timestamp_et"].dt.time
    df = df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))]
    return df.reset_index(drop=True)


def _ctx(frame: pd.DataFrame, i: int) -> BarContext:
    sub = frame.iloc[: i + 1]
    last = sub.iloc[-1]
    return BarContext(
        bar_idx=i, timestamp_et=last["timestamp_et"].to_pydatetime(), bar=last,
        prior_bars=sub, ribbon_now=None, ribbon_history=[], vix_now=17.4, vix_prior=17.4,
        vol_baseline_20=0.0, range_baseline_20=0.0, levels_active=[], multi_day_levels=[],
        htf_15m_stack=None,
    )


def _replay(reload_every_bar: bool) -> list[str]:
    import lib.watchers.vwap_continuation_watcher as w
    importlib.reload(w)  # clean slate for this replay
    frame = _rth_frame()
    fires: list[str] = []
    for i in range(len(frame)):
        if reload_every_bar:
            importlib.reload(w)  # <-- stands in for "the scheduler started a new process"
        sig = w.detect_vwap_continuation_setup(_ctx(frame, i))
        if sig is not None:
            fires.append(frame.iloc[i]["timestamp_et"].strftime("%H:%M"))
    return fires


@pytest.mark.skipif(not CSV.exists(), reason="pinned 5m lineage cache not present")
def test_same_process_honours_once_per_day() -> None:
    """The documented contract HOLDS inside a single long-lived process."""
    fires = _replay(reload_every_bar=False)
    assert fires == ["09:55"], f"expected exactly one fire, got {fires}"


@pytest.mark.skipif(not CSV.exists(), reason="pinned 5m lineage cache not present")
def test_fresh_process_each_tick_breaks_once_per_day() -> None:
    """CURRENT (DEFECTIVE) LIVE BEHAVIOUR -- a new process per tick re-fires the same day.

    INVERT THIS ASSERTION when the persisted-cooldown fix lands: the fixed path must
    produce exactly ['09:55'] here too.
    """
    fires = _replay(reload_every_bar=True)
    assert len(fires) > 1, (
        "fresh-process replay produced a single fire -- if this is because the "
        "once-per-day flag is now PERSISTED, invert this test (see module docstring); "
        "if it is because the fixture changed, fix the fixture."
    )
    assert fires[0] == "09:55"


def test_fleet_path_has_no_persisted_cooldown_while_core_does() -> None:
    """Parity check: the CORE lane persists a same-bar cooldown, the FLEET lane does not.

    This is the wiring half of the defect. It is asserted on SOURCE TEXT (not behaviour)
    so it stays true regardless of market data availability.
    """
    core = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert "same_bar_cooldown_active" in core, "core lane lost its persisted cooldown"
    assert "record_entry_bar" in core, "core lane lost its cooldown writer"

    fleet_srcs = "\n".join(
        (REPO / "automation" / "state" / "fleet" / f).read_text(encoding="utf-8")
        for f in ("fleet_live.py", "fleet_executor.py", "fleet_market.py")
    )
    # Strip comments/docstring prose so a mention in a comment does not fake a wiring.
    code_only = "\n".join(
        ln for ln in fleet_srcs.splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert "same_bar_cooldown_active(" not in code_only, (
        "the fleet lane now CALLS the persisted cooldown -- good; update this test to "
        "assert the new parity instead of the gap"
    )
