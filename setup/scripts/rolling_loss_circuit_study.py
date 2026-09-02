#!/usr/bin/env python3
"""rolling_loss_circuit_study.py -- calibration + counterfactual for a MULTI-DAY realized-loss
circuit on the CORE arms (queue.md WEEKLY-CIRCUIT-BREAKER-CORE, work order 2026-09 §2d).

THE GAP THIS MEASURES. Rule 5's kill switch is per-DAY: -30% of start-of-day equity (Safe) /
-50% (Bold). The 2026-08-18 day-throttle pre-registration already established that it has
never been reachable -- across 105 arm-days the worst day was -24.4%, p10 -10.1%. Nothing in
the core path looks ACROSS days, so a run of ordinary losing days compounds without any
control ever being consulted. weekly/lib/kill_switch.py has a multi-day circuit; the core
arms have none.

WHAT THIS SCRIPT IS, AND IS NOT. It is a measurement instrument: it reads the real-fills
ledger, reports the actual distribution of rolling W-day realized P&L per arm, and runs a
counterfactual over a threshold grid. It is NOT a validation, and running it does not arm
anything. The trip parameters are frozen in a pre-registration BEFORE the evaluation window;
this script produces the numbers that pre-registration is calibrated against, and the same
script re-run after the window produces the out-of-sample answer.

THREE DISCLOSURES THAT BOUND EVERY NUMBER BELOW (C4 -- state them, never bury them):

  1. THE WINDOWS OVERLAP. A 3-day rolling window over 32 trading days yields 30 windows, and
     adjacent ones share 2/3 of their data. They are NOT 30 independent observations. A "p05"
     over them is a description of one bad stretch, not a tail probability. Worst-case is a
     single event; do not read it as a return period.
  2. THE SAMPLE IS ~20-32 DAYS PER ARM. Any threshold chosen to look good here is fitted to
     one regime, in-sample. That is why this ships as a pre-registration evaluated forward,
     not as a ratified rule.
  3. "DAYS" MEANS TRADING DAYS WITH FILLS, not calendar days. A three-day stretch may span a
     week if the engine sat out. Sitting out is a valid day (J 2026-08-12) and a no-fill day
     carries no realized P&L, so including it would dilute the window with zeros and make the
     circuit LESS sensitive exactly when the engine has gone quiet. Stated because it is a
     modelling choice a reader could reasonably make the other way.

SEMANTICS ARE FIXED, NOT A PARAMETER: BLOCK NEW ENTRIES ONLY, NEVER FORCE-CLOSE -- the same
posture weekly/lib/kill_switch.py argues for at length. Force-closing on a multi-day drawdown
would liquidate positions the strategy is designed to manage on its own terms; that is a
risk-control-SHAPED strategy change, not a safety measure. This module contains no order
path of any kind (guard: test_rolling_loss_circuit_2026_09_02.py).
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
from typing import Iterable

REPO = pathlib.Path(__file__).resolve().parents[2]
TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"

# The five arms trading real fills. safe-1 is dormant (live:false) and excluded.
CORE_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")


def load_arm_days(path: pathlib.Path | None = None,
                  arms: Iterable[str] = CORE_ARMS) -> dict:
    """-> {arm: [(date, realized_pnl_dollars), ...]} ordered oldest-first.

    Sums every fill on a date into that arm's day. Rows with a non-numeric pnl are SKIPPED
    and counted, never coerced to 0.0 -- a missing P&L is not a flat day (OP-25: no silent
    fallbacks, no fabricated values).
    """
    p = path or TRADES_ENRICHED
    arms = tuple(arms)
    acc: dict = {a: collections.defaultdict(float) for a in arms}
    skipped = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        a, d, v = r.get("arm"), r.get("date"), r.get("pnl_dollars")
        if a not in acc or not d:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            skipped += 1
            continue
        acc[a][d] += float(v)
    out = {a: sorted(acc[a].items()) for a in arms}
    out["_skipped_rows"] = skipped
    return out


def rolling_sums(pnls: list[float], window: int) -> list[float]:
    """Every consecutive `window`-length sum. Empty if the series is shorter."""
    if window <= 0:
        raise ValueError("window must be >= 1")
    return [sum(pnls[i:i + window]) for i in range(len(pnls) - window + 1)]


def counterfactual(days: list[tuple[str, float]], window: int, threshold: float) -> dict:
    """Replay the circuit over one arm's real day series.

    Rule, evaluated at the START of each day: sum the realized P&L of the previous `window`
    days that were actually TRADED. If that sum <= -threshold, this day is BLOCKED (no new
    entries) and contributes 0 to the counterfactual.

    THE BLOCKED DAY STILL COUNTS AS A DAY in the trailing window, carrying its counterfactual
    0 -- not its actual P&L. This is the honest version and it matters: a circuit that peeks
    at the P&L of a day it prevented is using a number that would not exist. It also makes
    the circuit self-releasing, because zeros age into the window and lift the trailing sum
    back above the threshold without any separate reset rule.

    `threshold` is a POSITIVE dollar magnitude; the comparison is against its negation.
    """
    if threshold <= 0:
        raise ValueError("threshold must be a positive dollar magnitude")
    trailing: list[float] = []
    blocked_days: list[str] = []
    trips = 0
    was_blocked = False
    cf_total = 0.0
    for date, pnl in days:
        recent = trailing[-window:]
        # Only judge once the window is full: a 2-day-old arm has not had the chance to
        # breach a 3-day limit, and treating a short history as a breach would block every
        # arm on its first days.
        blocked = len(recent) >= window and sum(recent) <= -threshold
        if blocked:
            blocked_days.append(date)
            if not was_blocked:
                trips += 1
            trailing.append(0.0)
        else:
            cf_total += pnl
            trailing.append(pnl)
        was_blocked = blocked
    actual = sum(p for _, p in days)
    return {
        "n_days": len(days),
        "actual_pnl": round(actual, 2),
        "counterfactual_pnl": round(cf_total, 2),
        "delta": round(cf_total - actual, 2),
        "max_dd_actual": round(max_drawdown([p for _, p in days]), 2),
        # `trailing` IS the counterfactual path, in order, with blocked days as 0.0.
        "max_dd_counterfactual": round(max_drawdown(trailing), 2),
        # POSITIVE = the circuit made the worst drawdown SHALLOWER, which is the only thing
        # a circuit breaker is actually for.
        "dd_improvement": round(max_drawdown(trailing) - max_drawdown([p for _, p in days]), 2),
        "trips": trips,
        "days_blocked": len(blocked_days),
        "blocked_dates": blocked_days,
    }


def max_drawdown(path_pnls: list[float]) -> float:
    """Deepest peak-to-trough of the CUMULATIVE curve. Returns <= 0.

    THE METRIC A SAFETY DEVICE MUST BE JUDGED ON. Mean P&L is the wrong yardstick for a
    circuit breaker: a control that costs a little expectancy while truncating the left tail
    can still be worth having, and one that improves expectancy while deepening the tail is
    not a safety device at all. Drawdown is a PATH statistic -- it depends on the order of
    the days, so it cannot be recovered from a total or an average.
    """
    cum = peak = worst = 0.0
    for v in path_pnls:
        cum += v
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return worst


def describe(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)

    def q(f: float) -> float:
        return s[max(0, min(len(s) - 1, int(f * len(s)) - 1))]

    return {"n": len(s), "worst": round(s[0], 2), "p05": round(q(0.05), 2),
            "p10": round(q(0.10), 2), "median": round(statistics.median(s), 2),
            "best": round(s[-1], 2)}


def run(windows=(3, 5), thresholds=(400.0, 600.0, 800.0, 1000.0),
        path: pathlib.Path | None = None, arms: Iterable[str] = CORE_ARMS) -> dict:
    data = load_arm_days(path, arms)
    skipped = data.pop("_skipped_rows", 0)
    report: dict = {"skipped_rows": skipped, "arms": {}, "grid": []}

    for arm, days in data.items():
        pnls = [p for _, p in days]
        report["arms"][arm] = {
            "n_days": len(days),
            "first": days[0][0] if days else None,
            "last": days[-1][0] if days else None,
            "total_pnl": round(sum(pnls), 2),
            "day": describe(pnls),
            "rolling": {str(w): describe(rolling_sums(pnls, w)) for w in windows},
        }

    for w in windows:
        for t in thresholds:
            cells = {}
            for arm, days in data.items():
                if len(days) >= w:
                    cells[arm] = counterfactual(days, w, t)
            book_delta = sum(c["delta"] for c in cells.values())
            report["grid"].append({
                "window": w, "threshold": t,
                "book_delta": round(book_delta, 2),
                # Summed per-arm drawdown improvement -- NOT the book's own drawdown. The
                # arms hold separate accounts with isolated kill switches (Rule 5), so a
                # book-level curve would net one arm's drawdown against another's gain and
                # describe a portfolio nobody trades.
                "book_dd_improvement": round(
                    sum(c["dd_improvement"] for c in cells.values()), 2),
                "n_arms_dd_improved": sum(
                    1 for c in cells.values() if c["dd_improvement"] > 0),
                "n_arms_dd_worsened": sum(
                    1 for c in cells.values() if c["dd_improvement"] < 0),
                "total_trips": sum(c["trips"] for c in cells.values()),
                "total_days_blocked": sum(c["days_blocked"] for c in cells.values()),
                "per_arm": cells,
            })
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--windows", default="3,5")
    ap.add_argument("--thresholds", default="400,600,800,1000")
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    ap.add_argument("--out", help="write the JSON report here as well")
    args = ap.parse_args(argv)

    windows = tuple(int(x) for x in args.windows.split(",") if x.strip())
    thresholds = tuple(float(x) for x in args.thresholds.split(",") if x.strip())
    rep = run(windows, thresholds)

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0

    print("PER-ARM REALIZED P&L BY TRADING DAY WITH FILLS")
    print(f"{'arm':9} {'days':>5} {'total':>9} {'worst':>9} {'p10':>8} {'median':>8}")
    print("-" * 52)
    for arm, a in rep["arms"].items():
        d = a["day"]
        if not d.get("n"):
            continue
        print(f"{arm:9} {a['n_days']:>5} {a['total_pnl']:>9.0f} {d['worst']:>9.0f} "
              f"{d['p10']:>8.0f} {d['median']:>8.0f}")

    print("\nCOUNTERFACTUAL: block new entries while the trailing W-day realized sum <= -T")
    print("(windows OVERLAP and n is ~20-32 days/arm -- in-sample, one regime; see module docstring)")
    print(f"\n{'W':>3} {'T':>7} {'book delta':>11} {'dd shallower':>13} {'arms +/-':>9} "
          f"{'trips':>6} {'blocked':>8}")
    print("-" * 66)
    for cell in rep["grid"]:
        arms_pm = f"{cell['n_arms_dd_improved']}/{cell['n_arms_dd_worsened']}"
        print(f"{cell['window']:>3} {cell['threshold']:>7.0f} {cell['book_delta']:>+11.0f} "
              f"{cell['book_dd_improvement']:>+13.0f} {arms_pm:>9} "
              f"{cell['total_trips']:>6} {cell['total_days_blocked']:>8}")
    print("\n'dd shallower' > 0 means the circuit reduced the worst peak-to-trough, summed "
          "per arm.\nA circuit may cost P&L and still be right IF that column is clearly "
          "positive -- read both.")
    if rep["skipped_rows"]:
        print(f"\nNOTE: {rep['skipped_rows']} ledger row(s) skipped for a missing/non-numeric "
              f"pnl_dollars -- NOT counted as flat days.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
