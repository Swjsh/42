"""v27_stale_cache_detection — regression gate for stale SPY price cache reads.

Background:
  On 2026-05-19 ticks 111 (15:03 ET) and 126 (15:48 ET) the heartbeat reported
  claimed_spy=736.72 while the actual last-closed bar closes were 734.45 and 733.86
  — divergences of +$2.27 and +$2.86 (MISALIGNED-CRITICAL in the tick-audit CSV).
  The pattern is consistent with a stale cache in loop-state.json: the heartbeat
  stopped fetching fresh TV MCP data (likely due to rate-limit exhaustion) and
  returned the last successful fetch from ~14:10-14:15 ET as the current price.

  The R1 closed-bar fix (heartbeat v15.1) prevents in-progress bar reads
  (`bar_close_et = bar.time + 5min ≤ now_et` filter). This validator catches the
  different failure mode where the entire TV MCP fetch is stale — returning a
  legitimately-closed bar from 20-30+ minutes ago.

Modes:
  offline  Synthetic tick DataFrame: one normal tick (divergence $0.05) + one
           stale-cache tick (divergence $2.27, MISALIGNED-CRITICAL). Asserts
           detect_stale_cache_ticks() finds exactly 1 stale tick.
  live     Reads automation/state/heartbeat-tick-audit-{today}.csv. Counts rows
           where divergence_dollars > 1.00 AND classification == MISALIGNED-CRITICAL.
           GREEN = 0, YELLOW = 1-2, RED = >2. pass=True (audit mode).

Offline coverage:
  - Normal tick: divergence=0.05 - not flagged
  - Stale tick: divergence=2.27, classification=MISALIGNED-CRITICAL - flagged
  - Sub-threshold tick: divergence=0.80 (< 1.00 cutoff) - not flagged
  - MISALIGNED-CRITICAL with divergence=0.92 (< 1.00) - not flagged
  - Large divergence but classification=ALIGNED - not flagged

Live coverage:
  2026-05-19 audit CSV shows 6 MISALIGNED-CRITICAL rows; 3 with divergence_dollars > 1.00
  (ticks 3, 111, 126). Expected verdict RED (>2). pass=True in audit mode.

Exit code:
  0  all offline tests pass
  1  any offline test fails
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_AUDIT_DIR = _ROOT / "automation" / "state"
_STALE_THRESHOLD_USD = 1.00
_STALE_CLASSIFICATION = "MISALIGNED-CRITICAL"


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def detect_stale_cache_ticks(ticks: list[dict]) -> list[dict]:
    """Return ticks classified as stale-cache reads.

    A tick is flagged as a stale-cache read if:
      - abs(divergence_dollars) > _STALE_THRESHOLD_USD (default $1.00)
      - classification == "MISALIGNED-CRITICAL"

    Args:
        ticks: list of dicts with keys: tick_id, fire_at, divergence_dollars,
               classification (and optionally claimed_spy, decision, notes).

    Returns:
        Subset of ticks meeting both conditions.
    """
    stale = []
    for tick in ticks:
        try:
            divergence = float(tick.get("divergence_dollars", 0))
        except (TypeError, ValueError):
            continue
        classification = tick.get("classification", "")
        if abs(divergence) > _STALE_THRESHOLD_USD and classification == _STALE_CLASSIFICATION:
            stale.append(tick)
    return stale


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Offline: stale-cache detection on synthetic fixture.

    Evidence basis: 2026-05-19 tick-audit CSV shows claimed_spy=736.72 at
    ticks 111 (15:03 ET, divergence=+2.27) and 126 (15:48 ET, divergence=+2.86).
    Both are MISALIGNED-CRITICAL. The stale price matches the ~14:10 bar close,
    suggesting the TV MCP cache froze at that time.
    """
    results: list[tuple[str, bool, str]] = []

    # --- Test fixtures ---
    normal_tick = {
        "tick_id": "10",
        "fire_at": "14:00:02",
        "decision": "HOLD",
        "claimed_spy": "735.40",
        "divergence_dollars": "0.05",
        "classification": "ALIGNED",
    }
    stale_tick = {
        "tick_id": "111",
        "fire_at": "15:03:02",
        "decision": "HOLD",
        "claimed_spy": "736.72",
        "divergence_dollars": "2.27",
        "classification": "MISALIGNED-CRITICAL",
        "notes": "Stale cache at 14:10 bar price; actual close=734.45",
    }
    sub_threshold_tick = {
        "tick_id": "5",
        "fire_at": "10:00:02",
        "decision": "HOLD",
        "claimed_spy": "735.10",
        "divergence_dollars": "0.80",
        "classification": "MISALIGNED-CRITICAL",
    }
    early_misaligned_no_stale = {
        "tick_id": "3",
        "fire_at": "09:39:02",
        "decision": "HOLD",
        "claimed_spy": "735.62",
        "divergence_dollars": "0.92",
        "classification": "MISALIGNED-CRITICAL",
        "notes": "In-progress bar read (R1 regression), not stale-cache",
    }
    large_div_aligned = {
        "tick_id": "50",
        "fire_at": "11:00:02",
        "decision": "HOLD",
        "claimed_spy": "737.00",
        "divergence_dollars": "1.50",
        "classification": "ALIGNED",
        "notes": "Large divergence but classification=ALIGNED — not a stale-cache flag",
    }

    all_ticks = [normal_tick, stale_tick, sub_threshold_tick,
                 early_misaligned_no_stale, large_div_aligned]
    stale = detect_stale_cache_ticks(all_ticks)

    # T1: exactly 1 stale-cache tick in the full fixture
    t1 = len(stale) == 1
    results.append(("T1_stale_count_is_1", t1, f"stale={len(stale)} expected=1"))

    # T2: the stale tick is tick 111
    stale_ids = [s["tick_id"] for s in stale]
    t2 = "111" in stale_ids
    results.append(("T2_stale_tick_is_111", t2, f"stale_ids={stale_ids}"))

    # T3: normal tick (0.05 divergence) is not stale
    normal_in_stale = [s for s in stale if s["tick_id"] == "10"]
    t3 = len(normal_in_stale) == 0
    results.append(("T3_normal_tick_not_stale", t3,
                    f"normal in stale={len(normal_in_stale)} (must be 0)"))

    # T4: sub-threshold tick (0.80 < 1.00) is not stale
    sub_in_stale = [s for s in stale if s["tick_id"] == "5"]
    t4 = len(sub_in_stale) == 0
    results.append(("T4_sub_threshold_not_stale", t4,
                    f"sub-threshold in stale={len(sub_in_stale)} (must be 0)"))

    # T5: 0.92 divergence with MISALIGNED-CRITICAL is NOT stale (< $1.00 threshold)
    early_in_stale = [s for s in stale if s["tick_id"] == "3"]
    t5 = len(early_in_stale) == 0
    results.append(("T5_below_threshold_misaligned_not_stale", t5,
                    f"early_misaligned in stale={len(early_in_stale)} (must be 0)"))

    # T6: large divergence with ALIGNED classification is not flagged
    aligned_in_stale = [s for s in stale if s["tick_id"] == "50"]
    t6 = len(aligned_in_stale) == 0
    results.append(("T6_aligned_with_large_div_not_stale", t6,
                    f"ALIGNED large-div in stale={len(aligned_in_stale)} (must be 0)"))

    # T7: single stale-tick fixture
    stale_single = detect_stale_cache_ticks([stale_tick])
    t7 = len(stale_single) == 1
    results.append(("T7_single_stale_fixture", t7, f"single fixture stale={len(stale_single)}"))

    # T8: empty input yields no stale ticks
    t8 = detect_stale_cache_ticks([]) == []
    results.append(("T8_empty_input_no_stale", t8, "empty list yields []"))

    # T9: negative large divergence (claimed lower than actual) also flagged
    neg_stale = {
        "tick_id": "99",
        "fire_at": "13:00:02",
        "claimed_spy": "732.00",
        "divergence_dollars": "-1.50",
        "classification": "MISALIGNED-CRITICAL",
    }
    neg_result = detect_stale_cache_ticks([neg_stale])
    t9 = len(neg_result) == 1
    results.append(("T9_negative_large_div_also_stale", t9,
                    f"neg-large stale={len(neg_result)} (abs > 1.00 = flagged)"))

    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note} for n, p, note in results],
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Live: scan today's heartbeat-tick-audit CSV for stale-cache ticks.

    Reads automation/state/heartbeat-tick-audit-{today}.csv. Flags rows
    where divergence_dollars > 1.00 AND classification == MISALIGNED-CRITICAL.
    Returns GREEN/YELLOW/RED but always pass=True (audit mode).
    """
    today = dt.date.today().strftime("%Y-%m-%d")
    csv_path = _AUDIT_DIR / f"heartbeat-tick-audit-{today}.csv"

    if not csv_path.exists():
        # Fall back to most recent available audit file
        candidates = sorted(_AUDIT_DIR.glob("heartbeat-tick-audit-*.csv"))
        if candidates:
            csv_path = candidates[-1]
            note_prefix = f"Today's audit not found; using {csv_path.name}"
        else:
            return {
                "mode": "live",
                "pass": True,
                "verdict": "GREEN",
                "note": f"No heartbeat-tick-audit CSV found under {_AUDIT_DIR}",
                "stale_count": 0,
                "total_rows": 0,
                "audit_file": None,
            }
    else:
        note_prefix = f"Audit file: {csv_path.name}"

    ticks: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticks.append(row)

    stale = detect_stale_cache_ticks(ticks)

    if len(stale) == 0:
        verdict = "GREEN"
    elif len(stale) <= 2:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    stale_summary = [
        {
            "tick_id": s.get("tick_id"),
            "fire_at": s.get("fire_at"),
            "claimed_spy": s.get("claimed_spy"),
            "divergence_dollars": s.get("divergence_dollars"),
            "classification": s.get("classification"),
        }
        for s in stale
    ]

    return {
        "mode": "live",
        "pass": True,   # audit mode — stale-cache events are evidence, not a gym block
        "verdict": verdict,
        "audit_file": csv_path.name,
        "total_rows": len(ticks),
        "stale_count": len(stale),
        "stale_ticks": stale_summary,
        "note": (
            f"{note_prefix}. Scanned {len(ticks)} ticks. "
            f"Stale-cache ticks (|divergence|>$1.00 + MISALIGNED-CRITICAL): {len(stale)} "
            f"(verdict={verdict}). "
            "pass=True in audit mode."
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc: dict = {}
    exit_code = 0

    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        r = sc["offline"]
        print(f"=== OFFLINE === {r['passed']}/{r['total']} pass  all_pass={r['all_pass']}")
        for t in r["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:<52} {t['note']}")
        if not r["all_pass"]:
            exit_code = 1

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        r = sc["live"]
        print(f"\n=== LIVE === verdict={r['verdict']}  stale_count={r['stale_count']}  "
              f"total_rows={r['total_rows']}  pass={r['pass']}")
        if r.get("stale_ticks"):
            for s in r["stale_ticks"]:
                print(f"  STALE  tick={s['tick_id']}  fire_at={s['fire_at']}  "
                      f"claimed_spy={s['claimed_spy']}  divergence=${s['divergence_dollars']}")
        print(f"  {r['note']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
