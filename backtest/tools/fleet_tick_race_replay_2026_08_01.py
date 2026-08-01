"""fleet_tick_race_replay_2026_08_01.py -- WEEKEND-TWELVE Next-Twelve #4, task A.4.

DRY-RUN REPLAY, NO ORDERS. Replays 2026-07-31 12:15-12:20 ET (the WINNER-AUTOPSY-
2026-07-31-1219.md incident window) through the REAL, SHIPPED build_shared_signal.build()
function -- not a re-implementation of its logic -- against RECONSTRUCTED point-in-time
snapshots of core-decisions.jsonl (+ the tick-complete marker where applicable), to show
exactly what a fleet read would have observed at a grid of candidate tick instants, under:

  OLD  = pre-fix: no marker concept, two independent last-row-per-account scans
         (core_tick_id ignored -- byte-identical to git HEAD before this session's fix).
  NEW  = post-fix: build() resolves the last-COMPLETE-tick marker once and pins every
         block to it (this session's shipped change).

...at TWO fleet-executor cadences:
  3-MIN = the REAL live cadence (Gamma_FleetExecutor, confirmed via
          Get-ScheduledTask -> Interval PT3M). Ticks placed at the historically-documented
          real instants: 12:16:02.508 (WEEKEND-TWELVE task prompt) and 12:19:01.000
          (WINNER-AUTOPSY doc section 1: "build_shared_signal.py wrote the signal at
          12:19:01").
  1-MIN  = the CANDIDATE cadence task B.3 evaluates (Gamma_HeartbeatCore's own PT1M).
           Ticks placed at the SAME ~2.5s-past-the-minute offset the real 12:16 tick used,
           once per minute, 12:16 through 12:19.

DATA PROVENANCE: every row byte is copied VERBATIM from the real, on-disk
automation/state/core-decisions.jsonl (2026-07-31 12:15:03 through 12:19:03, all 10 rows,
both accounts) -- nothing synthesized. The ONE reconstruction this script performs is
`core_tick_id`: that field did not exist in production on 2026-07-31 (this session adds it),
so each row is assigned a core_tick_id via its OWN minute-floor (heartbeat_core.main() fires
at most once per minute during RTH, so minute-floor is a safe, unique-enough grouping key
for two rows written ~1s apart by the SAME invocation -- exactly what core_tick_id means in
production). The tick-complete marker for each "as-of-T" snapshot is derived mechanically:
whichever tick has the LATEST core_tick_id with BOTH accounts' rows at timestamp <= T.

Writes NOTHING to any production path. shared-signal.json is redirected to a scratch tmp
file per call. RAIL-4 CLEAR.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/fleet_tick_race_replay_2026_08_01.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_shared_signal as bss  # noqa: E402

ET = timezone(timedelta(hours=-4))
REAL_LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
TODAY = "2026-07-31"


def _load_real_window() -> list[dict]:
    """Every real row in the incident window, verbatim off disk."""
    rows = []
    with REAL_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            ts = r.get("ts_et", "")
            if ts[:16] >= f"{TODAY}T12:15" and ts[:16] <= f"{TODAY}T12:19":
                rows.append(r)
    if len(rows) != 10:
        raise SystemExit(f"expected 10 real rows (5 minutes x 2 accounts), got {len(rows)} "
                         "-- automation/state/core-decisions.jsonl has drifted since this "
                         "replay was authored; re-derive the window before trusting output.")
    return rows


def _with_core_tick_id(rows: list[dict]) -> list[dict]:
    """RECONSTRUCTION (disclosed in the module docstring): assign core_tick_id = the row's
    own minute-floor. The only invented field in this entire replay."""
    out = []
    for r in rows:
        minute = r["ts_et"][:16]  # "YYYY-MM-DDTHH:MM"
        out.append({**r, "core_tick_id": f"TICK-{minute}"})
    return out


def _last_complete_tick_as_of(rows: list[dict], as_of: datetime) -> str | None:
    """Mechanical derivation of what heartbeat_core's REAL marker would say at instant
    `as_of`: the core_tick_id of the latest tick where BOTH safe+bold rows have
    ts_et <= as_of. None if no tick is yet complete."""
    as_of_str = as_of.strftime("%Y-%m-%dT%H:%M:%S")
    by_tick: dict[str, set[str]] = {}
    for r in rows:
        if r["ts_et"] <= as_of_str:
            by_tick.setdefault(r["core_tick_id"], set()).add(r["account"])
    complete = [t for t, accts in by_tick.items() if {"safe", "bold"} <= accts]
    return max(complete) if complete else None  # tick ids sort lexicographically == chronologically


def _snapshot_ledger(rows: list[dict], as_of: datetime, out_path: Path) -> None:
    as_of_str = as_of.strftime("%Y-%m-%dT%H:%M:%S")
    visible = [r for r in rows if r["ts_et"] <= as_of_str]
    out_path.write_text("\n".join(json.dumps(r) for r in visible) + ("\n" if visible else ""),
                        encoding="utf-8")


def _snapshot_marker(rows: list[dict], as_of: datetime, out_path: Path) -> None:
    tick_id = _last_complete_tick_as_of(rows, as_of)
    if tick_id is None:
        if out_path.exists():
            out_path.unlink()
        return
    out_path.write_text(json.dumps({"core_tick_id": tick_id, "date": TODAY,
                                    "ts_et": f"{TODAY}T00:00:00", "accounts": ["bold", "safe"]}),
                        encoding="utf-8")


def _read_at(rows: list[dict], as_of: datetime, *, use_marker: bool, tmp_dir: Path) -> dict:
    """One fleet read at instant `as_of`, calling the REAL bss.build(). `use_marker=False`
    reproduces the OLD (pre-fix) world by simply never writing the marker file (build()'s
    own fail-open path then runs the exact pre-fix two-independent-scans logic -- this IS
    the old code, not a simulation of it)."""
    core_path = tmp_dir / f"core-{as_of.strftime('%H%M%S%f')}-{use_marker}.jsonl"
    marker_path = tmp_dir / f"marker-{as_of.strftime('%H%M%S%f')}-{use_marker}.json"
    out_path = tmp_dir / f"sig-{as_of.strftime('%H%M%S%f')}-{use_marker}.json"
    _snapshot_ledger(rows, as_of, core_path)
    if use_marker:
        _snapshot_marker(rows, as_of, marker_path)
    bss.CORE_DECISIONS = core_path
    bss.TICK_MARKER = marker_path
    bss.OUT = out_path
    bss.BEACON = tmp_dir / "no-beacon.json"
    sig = bss.build(now=as_of, scoring_peak=True, emit_strategies=False, run_vwap=False)
    return sig


def _fmt(as_of: datetime) -> str:
    return as_of.strftime("%H:%M:%S.%f")[:-3]


def main() -> int:
    rows = _with_core_tick_id(_load_real_window())
    tmp_dir = Path(tempfile.mkdtemp(prefix="fleet_race_replay_"))

    print("=" * 100)
    print("FLEET TICK-PAIRING RACE REPLAY -- 2026-07-31 12:15-12:20 ET -- DRY-RUN, NO ORDERS")
    print("=" * 100)
    print(f"Data: {REAL_LEDGER} (10 real rows, verbatim). Scratch dir: {tmp_dir}")
    print()
    print("BAR CLOSE -> CORE ROWS timeline (ground truth, both accounts, real ledger):")
    for r in rows:
        flag = " <-- A+ setup (bull=11, block_elite_bull) first COMPLETE at 12:16:03" \
            if r["ts_et"] == f"{TODAY}T12:16:03" else \
            (" <-- setup DECAYED (raw detector no longer firing)"
             if r["ts_et"] == f"{TODAY}T12:19:02" else "")
        print(f"  {r['ts_et']}  {r['account']:4}  verdict={r['verdict']:28} "
              f"bull_score={r['bull_score']:2}  trigger_bar={r.get('trigger_bar_et', '')[:16]}{flag}")
    print()

    # -------------------------------------------------------------------
    # Scenario 1: REAL 3-min cadence, historically-documented tick instants.
    # -------------------------------------------------------------------
    real_ticks = [
        datetime(2026, 7, 31, 12, 16, 2, 508000, tzinfo=ET),  # WEEKEND-TWELVE task prompt
        datetime(2026, 7, 31, 12, 19, 1, 0, tzinfo=ET),       # WINNER-AUTOPSY doc section 1
    ]
    print("-" * 100)
    print("SCENARIO 1 -- REAL 3-min fleet cadence (Gamma_FleetExecutor, Interval PT3M, live-verified)")
    print("-" * 100)
    for label, use_marker in (("OLD (pre-fix, no marker)", False), ("NEW (this session's fix)", True)):
        print(f"\n  {label}:")
        first_enter = None
        for t in real_ticks:
            sig = _read_at(rows, t, use_marker=use_marker, tmp_dir=tmp_dir)
            bold_bull = sig.get("bold", {}).get("bull", {})
            passed = bold_bull.get("passed")
            src_tick = sig.get("time_et")
            print(f"    fleet read @ {_fmt(t)}  ->  sig['bold']['bull'].passed={passed!s:5}  "
                  f"(top-level tick={src_tick}, top-level bull_score={sig['bull']['score']}, "
                  f"bold-perception bull_score={bold_bull.get('score')})")
            if passed and first_enter is None:
                first_enter = t
        if first_enter:
            hole_s = (first_enter - datetime(2026, 7, 31, 12, 16, 3, tzinfo=ET)).total_seconds()
            print(f"    => first ENTER-eligible fleet read: {_fmt(first_enter)} "
                  f"(hole since setup-complete-at-12:16:03 = {hole_s:.1f}s)")
        else:
            print("    => never ENTER-eligible in this window")

    # -------------------------------------------------------------------
    # Scenario 2: CANDIDATE 1-min cadence (task B.3), same ~2.5s intra-minute offset.
    # -------------------------------------------------------------------
    sim_ticks = [datetime(2026, 7, 31, 12, m, 2, 508000, tzinfo=ET) for m in (16, 17, 18, 19)]
    print()
    print("-" * 100)
    print("SCENARIO 2 -- CANDIDATE 1-min fleet cadence (task B.3; Gamma_HeartbeatCore's own PT1M)")
    print("-" * 100)
    for label, use_marker in (("OLD (pre-fix, no marker)", False), ("NEW (this session's fix)", True)):
        print(f"\n  {label}:")
        first_enter = None
        for t in sim_ticks:
            sig = _read_at(rows, t, use_marker=use_marker, tmp_dir=tmp_dir)
            bold_bull = sig.get("bold", {}).get("bull", {})
            passed = bold_bull.get("passed")
            src_tick = sig.get("time_et")
            print(f"    fleet read @ {_fmt(t)}  ->  sig['bold']['bull'].passed={passed!s:5}  "
                  f"(top-level tick={src_tick}, top-level bull_score={sig['bull']['score']}, "
                  f"bold-perception bull_score={bold_bull.get('score')})")
            if passed and first_enter is None:
                first_enter = t
        if first_enter:
            hole_s = (first_enter - datetime(2026, 7, 31, 12, 16, 3, tzinfo=ET)).total_seconds()
            print(f"    => first ENTER-eligible fleet read: {_fmt(first_enter)} "
                  f"(hole since setup-complete-at-12:16:03 = {hole_s:.1f}s)")
        else:
            print("    => never ENTER-eligible in this window")

    print()
    print("=" * 100)
    print("No orders placed. No production file written (all reads/writes scoped to scratch tmp_dir).")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
