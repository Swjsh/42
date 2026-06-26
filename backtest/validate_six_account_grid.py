"""validate_six_account_grid.py -- the NIGHT-MANDATE per-account readiness gate (READ-ONLY).

ONE table for ALL 6 SPY grid arms (safe-1/2/3, risky-1, bold-2, risky-3) off the ONE
deterministic brain. For each arm it reports:

  (a) ENTRY fidelity -- the arm, driven by the brain signal + its gate x sizing + every
      strategy, enters faithfully vs its OWN backtest (matched / extra / missed), the same
      5/5-style gate the committed harnesses use for safe-2/bold-2 and the 4 fleet_rest arms.
  (b) EXIT-shape correctness -- the bracket/scale-out each fired strategy WOULD place (via
      fleet_executor.plan_all -> EntryPlan.exit_shape) byte-matches the validated ExitShape
      in the strategy REGISTRY (stop / TP1 partial fraction / runner profit_lock / target /
      trail). This is the live exit_manager's input contract, so a match here + the green
      exit_manager/exit_actuator unit suites == the placed scale-out is the validated shape.

REUSE, DO NOT BREAK: imports the committed replay_fleet_arms.py + replay_heartbeat_core.py
helpers verbatim (no edits to those files). Adds the missing piece -- a DISTINCT bold-2
entry-fidelity check (bold-2 is mcp_heartbeat/base-gate; the committed fleet-arms harness
only tables the 4 fleet_rest arms, and the heartbeat_core harness only tables the SAFE
verdict). Here bold-2 is validated as "risky x base" reading the BOLD verdict with NO gate.

ARMS NOTHING, ENABLES NOTHING, PLACES NOTHING. Pure offline replay. $0.
Run: backtest/.venv/Scripts/python.exe backtest/validate_six_account_grid.py
"""
from __future__ import annotations

import json
import sys
from datetime import time as dtime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
for p in ("backtest", "setup/scripts", "automation/state/fleet"):
    sys.path.insert(0, str(REPO / p))

# Reuse the committed fleet-arms harness internals verbatim (zero edits to that file).
import replay_fleet_arms as rfa  # noqa: E402
import fleet_executor as fx  # noqa: E402
import strategies as strat_mod  # noqa: E402

SPY_CSV = rfa.SPY_CSV
VIX_CSV = rfa.VIX_CSV
N_DAYS = rfa.N_DAYS
ACCOUNTS = rfa.ACCOUNTS

# All 6 SPY grid arms, in grid order (sizing x gate). bold-2 is added to the 4 fleet_rest
# arms the committed harness tables, plus safe-2 (the SAFE control) for a complete picture.
SIX_ARMS = ("safe-3", "safe-2", "safe-1", "risky-1", "bold-2", "risky-3")


def _arm(arm_id):
    for a in ACCOUNTS["arms"]:
        if a.get("id") == arm_id:
            return a
    raise KeyError(arm_id)


# --- EXIT-SHAPE CORRECTNESS ------------------------------------------------------------
def _exit_shapes_for_arm(arm: dict) -> dict:
    """Run plan_all on a signal where BOTH registered strategies fire, then capture the
    exit_shape each ENTER plan carries. The arm only gates+sizes -- the exit must equal the
    strategy's REGISTRY ExitShape regardless of account. Returns {strategy: (placed, expected)}.
    A LOOSE signal (min triggers, ELITE-classified) is used so gates don't bench the plan, so
    we exercise the exit-shape path for every arm even the tight ones (the exit shape is gate-
    independent by construction; entry SELECTIVITY is checked separately in part (a))."""
    sig = {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["level_rejection", "ribbon_flip", "confluence"], "quality": "ELITE",
         "est_premium": 1.20, "spot": 600.0},
        {"name": "vwap_continuation", "side": "C", "setup": "VWAP_CONTINUATION",
         "triggers": ["sequence_reclaim", "VWAP_CONTINUATION_BREAKOUT"], "quality": "ELITE",
         "est_premium": 1.20, "spot": 600.0},
    ]}
    params = fx._params_for(arm)
    equity = float(arm.get("starting_equity") or 2000.0)
    plans = fx.plan_all(arm, sig, equity, params)
    out: dict = {}
    for p in plans:
        if p.action == "ENTER" and p.strategy and p.exit_shape:
            expected = strat_mod.by_name(p.strategy).exit.to_dict()
            out[p.strategy] = (dict(p.exit_shape), expected)
    return out


def _exit_correct(arm: dict) -> tuple[bool, str]:
    """Both registered strategies' placed exit shapes == their REGISTRY ExitShape on this arm."""
    shapes = _exit_shapes_for_arm(arm)
    if set(shapes) != {"ribbon_ride", "vwap_continuation"}:
        return False, f"only planned {sorted(shapes)} (expected both strategies)"
    for name, (placed, expected) in shapes.items():
        if placed != expected:
            return False, f"{name} exit mismatch: {placed} != {expected}"
    rr = shapes["ribbon_ride"][0]
    vw = shapes["vwap_continuation"][0]
    desc = (f"ribbon[stop{rr['premium_stop_pct']}/tp{rr['tp1_premium_pct']}/f{rr['tp1_qty_fraction']}/"
            f"{rr['profit_lock_mode']}/rt{rr['runner_target_pct']}/tr{rr['trail_pct']}] "
            f"vwap[stop{vw['premium_stop_pct']}/tp{vw['tp1_premium_pct']}/f{vw['tp1_qty_fraction']}/"
            f"{vw['profit_lock_mode']}]")
    return True, desc


# --- ENTRY FIDELITY (per arm) ----------------------------------------------------------
def _entry_fidelity_for_arm(arm_id, safe_pack, bold_pack, spy, vix, start, end):
    """Reuse the committed harness's GT + signal-synth + fidelity for ALL 6 arms (including
    bold-2, which the committed harness's ARMS_UNDER_TEST excludes). bold-2 = base gate ({}),
    bold params -> reads the BOLD verdict with no selectivity override, exactly a 'risky x base'
    cell. The committed _ground_truth_trades + _entry_fidelity already handle an empty
    gate_override (no post-filter), so bold-2 flows through the same path with no new logic."""
    arm = _arm(arm_id)
    pack = safe_pack if arm_id.startswith("safe") else bold_pack
    verdict_by_bar, payload_by_bar = pack[2], pack[3]
    gtres, gt_trades, notes, benched = rfa._ground_truth_trades(arm, spy, vix, start, end)
    fid = rfa._entry_fidelity(arm, gt_trades, verdict_by_bar, payload_by_bar, gtres.decisions, spy)
    gt_n = len(fid["gt_by_bar"])
    matched, extra, missed = len(fid["matched"]), len(fid["extra"]), len(fid["missed"])
    faithful = (extra == 0 and missed == 0 and matched == gt_n)
    return {"arm": arm_id, "gt_n": gt_n, "matched": matched, "extra": extra, "missed": missed,
            "faithful": faithful, "benched": benched, "notes": notes, "fid": fid}


def main() -> int:
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
    spy = spy[(spy["timestamp_et"].dt.time >= dtime(9, 30))
              & (spy["timestamp_et"].dt.time < dtime(16, 0))].reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    days = sorted(spy["date"].unique())[-N_DAYS:]
    start, end = days[0], days[-1]
    print(f"6-ACCOUNT GRID VALIDATION -- replaying {len(days)} days: {start} .. {end} "
          f"(spy rows={len(spy)})")

    # Dual-perception replay (SAME as the committed fleet-arms harness): SAFE arms read the
    # safe-params verdict, BOLD/RISKY arms read the bold-params verdict.
    safe_pack = rfa._replay_verdicts(spy, vix, days, start, end, rfa.PARAMS_SAFE)
    bold_pack = rfa._replay_verdicts(spy, vix, days, start, end, rfa.PARAMS_BOLD)
    score_pct = safe_pack[4]
    print(f"deterministic verdicts: safe@{safe_pack[5]} bars / bold@{bold_pack[5]} bars | "
          f"score parity (bear exact) = {score_pct:.1%}")

    rows = []
    for arm_id in SIX_ARMS:
        ent = _entry_fidelity_for_arm(arm_id, safe_pack, bold_pack, spy, vix, start, end)
        exit_ok, exit_desc = _exit_correct(_arm(arm_id))
        ent["exit_ok"] = exit_ok
        ent["exit_desc"] = exit_desc
        # ARM-READY: entry faithful (or benched-by-design with 0 extra) AND exit shape correct
        # AND score parity >= 95%. The MISSED-only producer-perception gap (risky-3 trendline)
        # is reported explicitly -- it is NOT an arm/exit defect (extra==0 => no over-trade/
        # no wrong placement), but it does fail strict entry fidelity, so ARM-READY=NO with a
        # PRODUCER-GAP tag rather than an arm defect.
        entry_ok = ent["faithful"] or (ent["benched"] and ent["gt_n"] == 0 and ent["extra"] == 0)
        ent["arm_ready"] = bool(entry_ok and exit_ok and score_pct >= 0.95)
        rows.append(ent)

    print("\n" + "=" * 104)
    print("PER-ACCOUNT READINESS (entry fidelity + exit-shape correctness, all off the ONE brain)")
    print("=" * 104)
    print(f"{'account':9} {'bt':>3} {'matched':>7} {'extra':>5} {'missed':>6} "
          f"{'entry':>6} {'exit':>5} {'ARM-READY'}")
    print("-" * 104)
    for r in rows:
        entry_tag = ("OK" if r["faithful"] else
                     ("benched" if (r["benched"] and r["gt_n"] == 0 and r["extra"] == 0) else
                      ("EXTRA" if r["extra"] else "MISSED")))
        ready = "YES" if r["arm_ready"] else "NO"
        if not r["arm_ready"] and r["extra"] == 0 and r["missed"] > 0:
            ready = "NO (producer-gap)"
        print(f"{r['arm']:9} {r['gt_n']:>3} {r['matched']:>7} {r['extra']:>5} {r['missed']:>6} "
              f"{entry_tag:>6} {('OK' if r['exit_ok'] else 'BAD'):>5} {ready}")

    print(f"\nscore parity (bear exact) >= 95%: {'PASS' if score_pct >= 0.95 else 'FAIL'} "
          f"({score_pct:.1%})")
    print("\nEXIT-SHAPE DETAIL (placed scale-out == REGISTRY ExitShape, per arm):")
    for r in rows:
        print(f"  {r['arm']:9} exit={'OK' if r['exit_ok'] else 'BAD'}  {r['exit_desc']}")

    print("\nMISSED / PRODUCER-GAP DETAIL:")
    for r in rows:
        if r["missed"] or r["extra"]:
            print(f"  {r['arm']:9} extra={r['fid']['extra']} missed={r['fid']['missed']}")
            for nstr in r["notes"]:
                print(f"            GT post-filter: {nstr}")

    n_ready = sum(1 for r in rows if r["arm_ready"])
    print(f"\nARM-READY: {n_ready}/6 accounts")
    print("NOTE: this harness ARMS NOTHING and PLACES NOTHING. Arm/enable is J's call.")
    # Exit code: 0 if every arm's EXIT shape is correct AND no arm OVER-trades (extra==0).
    # A pure MISSED (producer-gap) does not fail the run -- it's a flagged producer fix, not
    # an arm/exit defect -- but it IS surfaced. Over-trade (extra>0) or a bad exit shape fails.
    any_extra = any(r["extra"] for r in rows)
    any_bad_exit = any(not r["exit_ok"] for r in rows)
    return 1 if (any_extra or any_bad_exit) else 0


if __name__ == "__main__":
    raise SystemExit(main())
