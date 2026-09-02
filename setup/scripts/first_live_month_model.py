"""first_live_month_model.py -- what does month ONE actually look like, in dollars?

WHY. The go-live gate answers "is the edge real?" (criterion 1, currently FAIL on every arm
at CI-lower 0.333-0.412 against a 1.0 bar). It does NOT answer the question a person
actually asks before turning on real money: *if I run this for a month, what is the chance
I end down, how bad is a bad month, and how deep does it get along the way?* The 2026-09-01
audit computed that for safe-2 -- P(month<0)=0.55, p5 -$1,895, maxDD p95 -$2,225 pre-cap;
0.21 / -$941 / -$1,586 post-ladder -- and noted "nobody had modeled this". safe-3 is the
DESIGNATED PROD-SHADOW ARM, the one the whole 2026-10-30 decision rests on, and its model
was never computed. This is that.

METHOD, inherited deliberately rather than invented. Day-level bootstrap with replacement
over trading DAYS (not trades), because trades within a day are correlated -- resampling
trades would understate the variance that matters. Same fee model as
analysis/recommendations/_scratch_a1_bootstrap.py (OCC/ORF/TAF/SEC per contract plus a
per-arm-day CAT share, allocated across that arm-day's trades so per-trade adjusted P&L
still sums correctly), same percentile-bootstrap convention.

WHAT IS NEW HERE vs that script: it bootstrapped PROFIT FACTOR, a ratio. A dollar model
needs the PATH, because max drawdown is a path statistic -- the order of days inside the
month changes how deep it gets even when the total is identical. So each resample draws an
ORDERED 20-day sequence and the drawdown is measured along it.

HONEST LIMITS, stated because a dollar figure invites more trust than a ratio does:
  * A bootstrap resamples the days it was given. It cannot produce a day worse than the
    worst day observed. Every arm's history here is calm-regime (the gate discloses zero
    days with VIX>20 and zero days down more than 1%), so the tails below are LOWER BOUNDS
    on a stressed month, not forecasts of one.
  * Resampling days i.i.d. discards autocorrelation. If bad days cluster, real drawdowns
    are deeper than modelled.
  * The -$400/day realized-loss cap is applied as a FLOOR on each resampled day's P&L. That
    is the cap's intent, not a tick-level simulation of it: a real day would stop trading
    on breach, so the modelled floor is if anything generous about what follows.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
TRADES = REPO / "analysis" / "trades-enriched.jsonl"
OUT = REPO / "analysis" / "first-live-month"

# Same rates as _scratch_a1_bootstrap.py -- duplicated there from the cost rebuild, kept
# identical here so the two studies are comparable rather than merely similar.
RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}

TRADING_DAYS_PER_MONTH = 20
DAILY_LOSS_CAP = -400.0   # automation/state/params.json daily_loss_kill_switch_dollars


def ceil_cents(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100.0


def fee_ex_cat(qty: float, exit_px: float) -> float:
    sell_proceeds = exit_px * qty * 100.0
    occ = 2 * ceil_cents(RATES["occ_per_contract"] * qty)
    orf = 2 * ceil_cents(RATES["orf_per_contract"] * qty)
    taf = ceil_cents(RATES["taf_per_contract_sell"] * qty)
    sec = ceil_cents(RATES["sec_rate_per_dollar_sell"] * sell_proceeds)
    return occ + orf + taf + sec


def load_rows(path: Path = TRADES) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("_meta"):
            continue
        rows.append(r)
    return rows


def daily_pnl(rows: list[dict], arm: str, slip_cents: float = 2.0,
              apply_cap: bool = False) -> dict[str, float]:
    """Cost-adjusted P&L per trading day for one arm.

    slip_cents defaults to 2 -- the middle rung of the A1 study's cost ladder, and the one
    that study treats as the realistic case rather than the optimistic (0c) or pessimistic
    (5c) bound.
    """
    arm_rows = [r for r in rows if r.get("arm") == arm]
    counts: dict[tuple, int] = defaultdict(int)
    for r in arm_rows:
        counts[(r["arm"], r["date"])] += 1

    by_day: dict[str, float] = defaultdict(float)
    for r in arm_rows:
        qty = float(r.get("qty") or 0)
        exit_px = float(r.get("exit_px_avg") or 0)
        fee = fee_ex_cat(qty, exit_px)
        cat = RATES["cat_per_arm_day"] / counts[(r["arm"], r["date"])]
        slip = (slip_cents / 100.0) * qty
        by_day[r["date"]] += float(r.get("pnl_dollars") or 0) - fee - cat - slip

    if apply_cap:
        return {d: max(v, DAILY_LOSS_CAP) for d, v in by_day.items()}
    return dict(by_day)


def max_drawdown(path_pnls: list[float]) -> float:
    """Deepest peak-to-trough of the CUMULATIVE curve. Returns <= 0."""
    cum = 0.0
    peak = 0.0
    worst = 0.0
    for v in path_pnls:
        cum += v
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return worst


def bootstrap_month(day_values: list[float], n_boot: int = 20000, seed: int = 42,
                    days: int = TRADING_DAYS_PER_MONTH) -> Optional[dict]:
    """Ordered 20-day resample. The ORDER matters: max drawdown is a path statistic, so
    two months with the same total differ in how deep they go."""
    if not day_values:
        return None
    rng = random.Random(seed)
    n = len(day_values)
    totals: list[float] = []
    dds: list[float] = []
    for _ in range(n_boot):
        path = [day_values[rng.randrange(n)] for _ in range(days)]
        totals.append(sum(path))
        dds.append(max_drawdown(path))
    totals.sort()
    dds.sort()

    def pct(sorted_vals: list[float], q: float) -> float:
        return round(sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))], 2)

    return {
        "n_observed_days": n,
        "observed_day_mean": round(statistics.fmean(day_values), 2),
        "observed_day_worst": round(min(day_values), 2),
        "observed_day_best": round(max(day_values), 2),
        "n_boot": n_boot,
        "P(month<0)": round(sum(1 for t in totals if t < 0) / len(totals), 3),
        "month_p5": pct(totals, 0.05),
        "month_median": pct(totals, 0.50),
        "month_p95": pct(totals, 0.95),
        "month_mean": round(statistics.fmean(totals), 2),
        "maxDD_p50": pct(dds, 0.50),
        "maxDD_p95": pct(dds, 0.05),   # p95 DEPTH = 5th percentile of a negative series
        "maxDD_worst": round(dds[0], 2),
    }


def build(arm: str = "safe-3", rows: Optional[list[dict]] = None,
          slip_cents: float = 2.0) -> dict:
    rows = rows if rows is not None else load_rows()
    out: dict = {"arm": arm, "slip_cents": slip_cents,
                 "trading_days_per_month": TRADING_DAYS_PER_MONTH,
                 "daily_loss_cap": DAILY_LOSS_CAP, "scenarios": {}}
    for label, cap in (("uncapped", False), ("with_400_daily_cap", True)):
        by_day = daily_pnl(rows, arm, slip_cents=slip_cents, apply_cap=cap)
        res = bootstrap_month(list(by_day.values()))
        if res is None:
            out["scenarios"][label] = {"error": f"no trades on disk for arm {arm!r}"}
            continue
        res["observed_total"] = round(sum(by_day.values()), 2)
        res["window"] = [min(by_day), max(by_day)] if by_day else None
        out["scenarios"][label] = res
    out["limits"] = [
        "A bootstrap cannot produce a day worse than the worst day observed. This arm's "
        "history is calm-regime -- the go-live gate discloses zero days with VIX>20 and "
        "zero days down more than 1% -- so these tails are LOWER BOUNDS on a stressed "
        "month, not forecasts of one.",
        "Days are resampled i.i.d., discarding autocorrelation. If bad days cluster, real "
        "drawdowns are deeper than modelled.",
        "The -$400 cap is applied as a floor on each resampled day, which is the cap's "
        "intent rather than a tick-level simulation of it.",
    ]
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arm", default="safe-3")
    ap.add_argument("--all-arms", action="store_true")
    ap.add_argument("--slip-cents", type=float, default=2.0)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    rows = load_rows()
    arms = sorted({r.get("arm") for r in rows if r.get("arm")}) if args.all_arms else [args.arm]

    reports = {}
    for arm in arms:
        rep = build(arm, rows=rows, slip_cents=args.slip_cents)
        reports[arm] = rep
        for label, s in rep["scenarios"].items():
            if "error" in s:
                print(f"{arm:<9} {label:<20} {s['error']}")
                continue
            print(f"{arm:<9} {label:<20} n_days={s['n_observed_days']:<3} "
                  f"P(month<0)={s['P(month<0)']:<6} p5=${s['month_p5']:<10} "
                  f"median=${s['month_median']:<10} maxDD_p95=${s['maxDD_p95']}")

    if not args.no_write:
        OUT.mkdir(parents=True, exist_ok=True)
        for arm, rep in reports.items():
            p = OUT / f"{arm}.json"
            body = json.dumps(rep, indent=2)
            body.encode("utf-8")
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(p)
        print(f"wrote {len(reports)} report(s) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
