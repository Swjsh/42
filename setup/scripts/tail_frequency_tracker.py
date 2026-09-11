#!/usr/bin/env python3
"""Score PREREG-TAIL-FREQUENCY-2026-09-10 -- is the engine's right tail repeatable?

WHY THIS EXISTS
---------------
GOAL-WHY-THIS-WEEK-2026-09-10 (W12) established that the engine's entire lifetime
edge is carried by ~5 tail days, all inside one 2026-07-29..2026-08-27 stretch:

    all arms   419 trips / 47 days   net +$349    ex-top-1-day  -$3,275
    active 4   300 trips / 44 days   net +$1,121  ex-top-1-day  -$1,698

At that n you cannot distinguish "a fat tail that fires ~monthly" from "one lucky
regime". A prereg was frozen committing to a decision rule BEFORE the data arrived.
This module scores it. It exists so the 10-30 checkpoint reads a measured number
instead of someone's memory of a prose paragraph (a repeated question is a missing
instrument).

DESIGN NOTES
------------
* Deterministic, pure-Python, $0. No LLM, no network. Safe to schedule daily.
* Population is `analysis/trades-enriched.jsonl` filtered to attribution=='engine'.
  `journal/trades.csv` is NOT a valid source: it spans the pre-engine era
  (2026-04-29..2026-06-26) and inflates any engine claim with J-era manual fills.
* Tail-day counting is DAY-level, so it is immune to the arm-replication trap
  (per-arm agreement on one signal is replication, not confirmation). The per-wave
  diagnostic dedupes on a ~10-minute bucket + contract symbol for that reason.
* FAILS LOUDLY. If the source is missing or unparseable it raises; it never returns
  a plausible-looking zero. A silent zero here would read as "no tail days", i.e.
  as evidence for H0 -- the exact failure this rig calls C7.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # anchor to __file__ (C9)
ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
PREREG = REPO / "analysis" / "preregs" / "prereg-tail-frequency-2026-09-10.json"
OUT = REPO / "analysis" / "recommendations" / "tail-frequency-tracker.json"

ACTIVE_ARMS = {"safe-2", "bold-2", "safe-3", "risky-1"}
TAIL_USD = 500.0
BIG_TAIL_USD = 1000.0
WINDOW_START = "2026-09-11"
WINDOW_END = "2026-10-30"
MIN_DAYS_FOR_VERDICT = 10                            # prereg kill criterion


def _et_now() -> str:
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    from et_clock import et_now                      # noqa: E402 -- never type a timestamp
    return et_now().strftime("%Y-%m-%d %H:%M:%S %Z")


def load_engine_trips(path: Path = ENRICHED) -> list[dict]:
    """Engine-attributed trips. Raises rather than returning [] -- an empty result
    would read as 'no tail days', which is evidence for H0."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- cannot score the tail-frequency prereg. "
            "Refusing to emit a zero that would read as evidence for H0."
        )
    trips, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if r.get("attribution") == "engine" and r.get("date"):
            trips.append(r)
    if not trips:
        raise ValueError(
            f"{path} parsed but yielded 0 engine-attributed trips "
            f"({bad} unparseable lines) -- refusing to report a silent zero."
        )
    return trips


def daily_totals(trips: list[dict], arms: set[str] | None = None) -> dict[str, float]:
    day: dict[str, float] = collections.defaultdict(float)
    for r in trips:
        if arms is not None and r.get("arm") not in arms:
            continue
        day[r["date"]] += float(r.get("pnl_dollars") or 0.0)
    return dict(day)


def tail_days(day: dict[str, float], lo: str, hi: str, thr: float = TAIL_USD) -> list[tuple[str, float]]:
    return sorted((d, v) for d, v in day.items() if lo <= d <= hi and v > thr)


def verdict(n_tail: int, n_days: int) -> tuple[str, str]:
    """The decision rule, frozen in the prereg BEFORE any window data existed."""
    if n_days < MIN_DAYS_FOR_VERDICT:
        return "UNDERPOWERED", (
            f"only {n_days} trading day(s) with engine fills in the window "
            f"(need >= {MIN_DAYS_FOR_VERDICT}); no verdict rather than a weak one"
        )
    if n_tail >= 4:
        return "H1_SUPPORTED", "tail is repeatable -- continue accumulating n toward the gate"
    if n_tail <= 1:
        return "H0_SUPPORTED", (
            "regime-cluster hypothesis wins decisively -- a KILL conversation on the "
            "current signal is warranted at the 10-30 checkpoint"
        )
    return "AMBIGUOUS", "still undersampled -- extend the window, do NOT tune"


def build(window_start: str = WINDOW_START, window_end: str = WINDOW_END) -> dict:
    trips = load_engine_trips()
    now = _et_now()

    scopes = {}
    for label, arms in (("all_arms", None), ("active_4", ACTIVE_ARMS)):
        day = daily_totals(trips, arms)
        win = {d: v for d, v in day.items() if window_start <= d <= window_end}
        tl = tail_days(day, window_start, window_end, TAIL_USD)
        big = tail_days(day, window_start, window_end, BIG_TAIL_USD)
        srt = sorted(day.items(), key=lambda kv: -kv[1])
        total = sum(day.values())
        scopes[label] = {
            "lifetime_trips": sum(1 for r in trips if arms is None or r.get("arm") in arms),
            "lifetime_days": len(day),
            "lifetime_net": round(total, 2),
            "lifetime_net_ex_top_1_day": round(total - (srt[0][1] if srt else 0.0), 2),
            "best_day": srt[0][0] if srt else None,
            "window_days_with_fills": len(win),
            "window_net": round(sum(win.values()), 2),
            "tail_days_gt_500": [{"date": d, "pnl": round(v, 2)} for d, v in tl],
            "n_tail_days": len(tl),
            "n_tail_days_gt_1000": len(big),
        }

    n_tail = scopes["all_arms"]["n_tail_days"]          # primary metric: all-arms, per prereg
    n_days = scopes["all_arms"]["window_days_with_fills"]
    v, why = verdict(n_tail, n_days)

    return {
        "generated_at_et": now,
        "prereg_id": "PREREG-TAIL-FREQUENCY-2026-09-10",
        "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "observation_window": {"start": window_start, "end": window_end},
        "primary_metric": "count of trading days with all-arms engine-attributed book P&L > +$500",
        "n_tail_days": n_tail,
        "n_trading_days_with_fills": n_days,
        "verdict": v,
        "verdict_reason": why,
        "decision_rule_frozen_before_data": True,
        "scopes": scopes,
        "freeze_note": "Measurement only. Authorises no config change. CONFIG FREEZE 2026-08-31 -> 2026-10-30 unaffected.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window-start", default=WINDOW_START)
    ap.add_argument("--window-end", default=WINDOW_END)
    ap.add_argument("--print", action="store_true", help="print the report to stdout")
    args = ap.parse_args()

    rep = build(args.window_start, args.window_end)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")

    print(f"[tail-frequency] {rep['verdict']}: {rep['n_tail_days']} tail day(s) "
          f"over {rep['n_trading_days_with_fills']} day(s) with fills "
          f"({args.window_start}..{args.window_end}) -- {rep['verdict_reason']}")
    print(f"[tail-frequency] -> {OUT}")
    if args.print:
        print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
