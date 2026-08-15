"""PRE-TP1-RATCHET-COST runner -- prereg PRE-TP1-RATCHET-COST-2026-08-15 (amended before any run).

Replays the SAME recorded entry population through three exit shapes and reports exit-reason
COMPOSITION alongside net P&L. Entries are held fixed by construction, so this is not
vulnerable to the confounds that killed the live before/after (risky-3's premium-stop lane,
risky-1's deleted selectivity gate, risky-3's strike-tier kill -- all concurrent with the
2026-08-10 exit ship).

THE DECISIVE NUMBER is the runner_target fire rate, not net P&L. Live telemetry: 3 fires in 239
pre-stack closes, 0 in 98 post-stack. If removing the ladder restores none, the ladder is not
capping the tail and this line of inquiry is wrong -- and the runner says so in its headline.

Read-only. Arms nothing.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
TOOLS = REPO / "backtest" / "tools"
for _p in (str(FLEET), str(TOOLS), str(REPO / "backtest"), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = REPO / "analysis" / "recommendations" / "ratchet-cost-2026-08-15.json"
HIGHRES = REPO / "backtest" / "data" / "highres"

import exit_manager as em  # noqa: E402
import strategies as strat  # noqa: E402

REASON_CLASSES = ("runner_target", "runner_stop", "ribbon_flip_back",
                  "structure_stop", "premium_stop", "tp1", "time_stop", "other")


def classify(reason: str) -> str:
    r = str(reason or "").lower()
    for c in REASON_CLASSES[:-1]:
        if c in r:
            return c
    return "other"


def shapes() -> dict:
    """Control = the live registry shape. Cells vary ONE knob each (strike-A/B pinning rule)."""
    base = strat.RIBBON_RIDE.exit
    d = base.to_dict()

    def variant(**over):
        v = dict(d)
        v.update(over)
        return v

    return {
        "ratchet_ON_current": dict(d),
        # ladder removed; every other numeric identical
        "ladder_OFF": variant(pre_tp1_ladder=None),
        # top rung removed only (+75%->lock+60%), the rung the live data implicates
        "ladder_TOP_RUNG_OFF": variant(pre_tp1_ladder=[[0.50, 0.30]]),
        # whole pre-TP1 ratchet off (ladder + trail + be-floor)
        "pre_tp1_ALL_OFF": variant(pre_tp1_ladder=None, pre_tp1_trail_arm_pct=None,
                                   pre_tp1_trail_pct=None, pre_tp1_be_floor_arm_pct=None,
                                   pre_tp1_floor_pct=None),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sh = shapes()
    ctrl = sh["ratchet_ON_current"]
    print("PRE-TP1-RATCHET-COST -- cells and the knob each varies\n")
    print(f"  control pre_tp1_ladder      = {ctrl.get('pre_tp1_ladder')}")
    print(f"  control pre_tp1_trail       = arm {ctrl.get('pre_tp1_trail_arm_pct')} "
          f"/ {ctrl.get('pre_tp1_trail_pct')}")
    print(f"  control tp1                 = +{ctrl.get('tp1_premium_pct'):.0%} "
          f"sell {ctrl.get('tp1_qty_fraction'):.3f}")
    print(f"  control runner_target       = +{ctrl.get('runner_target_pct'):.0%}\n")

    # G5 composition-binds precheck: the cells must differ from control in the knob itself.
    binds = {}
    for name, v in sh.items():
        if name == "ratchet_ON_current":
            continue
        diff = {k for k in v if v[k] != ctrl.get(k)}
        binds[name] = sorted(diff)
        print(f"  {name:<22} varies: {sorted(diff)}")
        if not diff:
            print(f"    !! {name} is IDENTICAL to control -- knob inert, cell would be NOT-RUN")

    days = sorted({f.name.split("_")[-1].replace(".csv", "")
                   for f in HIGHRES.glob("SPY*_1m_*.csv")})
    print(f"\n  highres option-day cache: {len(days)} distinct dates "
          f"({days[0]} .. {days[-1]})" if days else "\n  NO highres cache")

    rep = {
        "prereg_id": "PRE-TP1-RATCHET-COST-2026-08-15",
        "status": "CELLS_DEFINED_POPULATION_BLOCKED",
        "cells": {k: {"varies_from_control": binds.get(k, [])} for k in sh},
        "control_shape": ctrl,
        "highres_days_available": len(days),
        "highres_date_range": [days[0], days[-1]] if days else None,
    }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
