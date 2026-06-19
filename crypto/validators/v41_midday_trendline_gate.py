"""v41_midday_trendline_gate — MIDDAY_TRENDLINE_GATE logic correctness tests.

Background:
  2026-06-16: MIDDAY_TRENDLINE_GATE added to leaderboard rank 21 (RATIFICATION_READY).
  A vs B scorecard complete (analysis/recommendations/midday_trendline_gate_ab_scorecard.json):
    Option A surgical gate: +1,562/c total vs baseline +1,169/c (+393/c delta, keeps 71% of trades).

  Gate logic (implemented in heartbeat.md natural language directive, tested here):
    Block a bear entry if ALL three conditions hold:
      1. bar time is in [11:30, 14:00) ET  (11:30 inclusive, 14:00 exclusive)
      2. exactly 1 trigger fired
      3. the sole trigger is "trendline_rejection"

  Foot-gun it prevents:
    Autopsy of 2026-02-20..2026-05-20: 24 of 32 midday losers were single-trigger
    trendline_rejection entries → EXIT_ALL_PREMIUM_STOP.
    "Midday trendline entries need more conviction than a single trigger." — J's intuition.

  Note: gate function defined inline (no production Python dependency — logic lives in
  heartbeat.md as a natural language directive; this validator provides regression coverage
  for the day the gate is ported to Python).

Modes:
  offline  10 deterministic boundary tests. All 10 must PASS.
  live     Audit automation/state/aggressive/decisions.jsonl for ENTER_BEAR ticks
           in the 11:30-14:00 window with trendline_rejection. Informational — pass=True always.
  both     Run offline then live.

Offline coverage:
  T1:  12:00 ET, ["trendline_rejection"]                    → BLOCKED
  T2:  12:00 ET, ["trendline_rejection", "level_rejection"] → NOT BLOCKED (2 triggers)
  T3:  12:00 ET, ["level_rejection"]                        → NOT BLOCKED (not trendline)
  T4:  10:00 ET, ["trendline_rejection"]                    → NOT BLOCKED (before 11:30)
  T5:  14:00 ET, ["trendline_rejection"]                    → NOT BLOCKED (exclusive boundary)
  T6:  13:59 ET, ["trendline_rejection"]                    → BLOCKED (last minute of window)
  T7:  11:30 ET, ["trendline_rejection"]                    → BLOCKED (inclusive boundary)
  T8:  09:40 ET, ["trendline_rejection"]                    → NOT BLOCKED (morning)
  T9:  15:00 ET, ["trendline_rejection"]                    → NOT BLOCKED (EOD, after window)
  T10: 12:30 ET, []                                         → NOT BLOCKED (zero triggers)

Live coverage:
  Count of aggressive ENTER_BEAR ticks in [11:30, 14:00) where trigger contains
  "trendline_rejection". Report count + % of all bear entries. pass=True always.

Exit code:
  0 — all offline tests PASS (or live-only run)
  1 — any offline test FAIL
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Gate function (inline — no production dependency)
# ---------------------------------------------------------------------------

def is_midday_trendline_only(
    time_et: datetime.time,
    triggers_fired: list[str],
) -> bool:
    """Returns True if the midday single-trigger trendline gate should BLOCK this entry.

    Conditions (all three must hold):
      1. time_et in [11:30, 14:00) ET
      2. len(triggers_fired) == 1
      3. "trendline_rejection" in triggers_fired
    """
    is_midday = datetime.time(11, 30) <= time_et < datetime.time(14, 0)
    is_trendline_only = (
        len(triggers_fired) == 1 and "trendline_rejection" in triggers_fired
    )
    return is_midday and is_trendline_only


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run 10 deterministic boundary tests for is_midday_trendline_only."""
    results: list[dict] = []

    def t(label: str, time_et: datetime.time, triggers: list[str], expect_blocked: bool) -> None:
        got = is_midday_trendline_only(time_et, triggers)
        passed = got == expect_blocked
        results.append({
            "label": label,
            "time_et": str(time_et),
            "triggers": triggers,
            "expect_blocked": expect_blocked,
            "got_blocked": got,
            "passed": passed,
        })
        status = "PASS" if passed else "FAIL"
        block_str = "BLOCKED    " if got else "NOT BLOCKED"
        expected_str = "BLOCKED    " if expect_blocked else "NOT BLOCKED"
        print(f"  [{status}] {label:5s}  {str(time_et):8s}  {str(triggers):45s}"
              f"  got={block_str}  expect={expected_str}")

    # T1: midday, single trendline trigger → BLOCKED
    t("T1", datetime.time(12, 0), ["trendline_rejection"], True)

    # T2: midday, two triggers (trendline + level) → NOT BLOCKED (len != 1)
    t("T2", datetime.time(12, 0), ["trendline_rejection", "level_rejection"], False)

    # T3: midday, single trigger but NOT trendline_rejection → NOT BLOCKED
    t("T3", datetime.time(12, 0), ["level_rejection"], False)

    # T4: 10:00 ET, before window opens → NOT BLOCKED
    t("T4", datetime.time(10, 0), ["trendline_rejection"], False)

    # T5: 14:00 ET, exclusive upper boundary → NOT BLOCKED
    t("T5", datetime.time(14, 0), ["trendline_rejection"], False)

    # T6: 13:59 ET, last minute inside window → BLOCKED
    t("T6", datetime.time(13, 59), ["trendline_rejection"], True)

    # T7: 11:30 ET, inclusive lower boundary → BLOCKED
    t("T7", datetime.time(11, 30), ["trendline_rejection"], True)

    # T8: 09:40 ET, opening-bell morning window → NOT BLOCKED
    t("T8", datetime.time(9, 40), ["trendline_rejection"], False)

    # T9: 15:00 ET, after window — EOD entries allowed → NOT BLOCKED
    t("T9", datetime.time(15, 0), ["trendline_rejection"], False)

    # T10: 12:30 ET (midday), zero triggers → NOT BLOCKED (other gates handle empty)
    t("T10", datetime.time(12, 30), [], False)

    passed_n = sum(1 for r in results if r["passed"])
    total_n = len(results)

    return {
        "mode": "offline",
        "tests": results,
        "passed": passed_n,
        "total": total_n,
        "all_pass": passed_n == total_n,
    }


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Scan aggressive/decisions.jsonl for ENTER_BEAR ticks in [11:30, 14:00) ET
    where trigger contains 'trendline_rejection'. Informational — pass=True always."""
    dec_path = _ROOT / "automation" / "state" / "aggressive" / "decisions.jsonl"
    if not dec_path.exists():
        print("  [SKIP] aggressive/decisions.jsonl not found")
        return {
            "mode": "live",
            "all_pass": True,
            "total_bear_entries": 0,
            "midday_trendline_only_count": 0,
            "note": "decisions.jsonl not found",
        }

    total_bear = 0
    midday_tl_only = 0
    midday_tl_examples: list[dict] = []

    _window_start = datetime.time(11, 30)
    _window_end = datetime.time(14, 0)

    with dec_path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue

            action = row.get("action", "")
            if action not in ("ENTER_BEAR", "enter_bear"):
                # Also check legacy aggressive format
                direction = row.get("direction", "")
                setup = row.get("setup_name", "")
                if not (direction == "BEAR" and "enter" in action.lower()):
                    # Try broader pattern
                    if "BEAR" not in action.upper() or "ENTER" not in action.upper():
                        continue

            total_bear += 1

            # Extract trigger
            trigger_raw = row.get("trigger", row.get("triggers_fired", ""))
            if isinstance(trigger_raw, list):
                triggers = trigger_raw
            elif isinstance(trigger_raw, str) and trigger_raw:
                triggers = [trigger_raw]
            else:
                triggers = []

            # Parse time_et from the tick
            time_et_str = row.get("time_et", row.get("ts", ""))
            if not time_et_str:
                continue

            # Handle ISO timestamp (ts field) or HH:MM string
            try:
                if "T" in time_et_str or "-" in time_et_str[:8]:
                    # ISO format like "2026-05-20T09:48:03-04:00"
                    parsed_dt = datetime.datetime.fromisoformat(time_et_str)
                    # Convert to ET (subtract 4h from UTC as EDT approximation)
                    if parsed_dt.tzinfo is not None:
                        import zoneinfo
                        et_tz = zoneinfo.ZoneInfo("America/New_York")
                        parsed_dt = parsed_dt.astimezone(et_tz)
                    bar_time = parsed_dt.time()
                else:
                    # "HH:MM" string
                    bar_time = datetime.time.fromisoformat(time_et_str[:5])
            except Exception:
                continue

            if not (_window_start <= bar_time < _window_end):
                continue

            # Check if would be blocked by gate
            if is_midday_trendline_only(bar_time, triggers):
                midday_tl_only += 1
                if len(midday_tl_examples) < 5:
                    midday_tl_examples.append({
                        "date": row.get("date", row.get("ts", "")[:10]),
                        "time_et": str(bar_time),
                        "triggers": triggers,
                        "action": action,
                    })

    pct = midday_tl_only / total_bear * 100 if total_bear > 0 else 0.0
    print(f"  [AUDIT] aggressive bear entries: total={total_bear}")
    print(f"          midday [11:30-14:00) trendline-only (would-block): "
          f"N={midday_tl_only} ({pct:.1f}% of all bear entries)")
    if midday_tl_examples:
        print(f"          examples:")
        for ex in midday_tl_examples:
            print(f"            {ex['date']} {ex['time_et']} triggers={ex['triggers']}")
    else:
        print(f"          no matching entries found in decisions.jsonl")

    return {
        "mode": "live",
        "all_pass": True,
        "total_bear_entries": total_bear,
        "midday_trendline_only_count": midday_tl_only,
        "pct_of_all_bear": round(pct, 1),
        "examples": midday_tl_examples,
        "note": "informational audit — pass=True always",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "both"],
        default="offline",
        help="offline=deterministic gate tests; live=decisions.jsonl audit; both=all",
    )
    args = parser.parse_args(argv)

    print(f"\n[v41] MIDDAY_TRENDLINE_GATE — mode={args.mode}")
    print(f"      window=[11:30, 14:00) ET  condition=single 'trendline_rejection' trigger")

    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if not result["all_pass"]:
            rc = 1

    if args.mode in ("live", "both"):
        run_live()

    return rc


if __name__ == "__main__":
    sys.exit(main())
