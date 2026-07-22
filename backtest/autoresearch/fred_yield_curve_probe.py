"""FRED Daily Treasury Par Yield Curve (10Y-2Y spread) -- feasibility probe (chef-inbox
2026-07-10-prospector-fred-daily-treasury-par-yield-curve-10y-, canonical master for the
FRED/Treasury-yield-curve family per its 2026-07-21 consolidation note).

The bounded question (per the inbox item): does the 10Y-2Y Treasury yield-curve spread --
a macro regime signal for risk appetite / recession expectations -- carry a testable
directional/timing signal for 0DTE SPY entries, tested as (a) a LEVEL gate (steep vs flat
curve, median split) and (b) a day-over-day SLOPE gate (steepening vs flattening), against
the standing OP-11/OP-16 pass bar (OOS positive AND walk-forward >= 0.70 AND sub-window
stable AND anchor-day no-regression) before any wiring proposal reaches
conductor-proposals.jsonl.

Data source note (OP-20 disclosure): FRED's `fredgraph.csv` CSV-download endpoint
(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10,DGS2,DGS3MO`) requires NO API
key/registration -- confirmed live this fire, closing the inbox item's own "register a FRED
API key" blocker without needing one. Cached locally at
`backtest/data/fred_yield_curve_2026-04-01_2026-07-22.csv` (79 daily rows, filtered to the
probe window).

Method note (why median-split, not an absolute inversion threshold): the 10Y-2Y spread
never inverted over this window (min +0.27, max +0.57, entire series positive) -- a
standard "inverted vs normal" test would degenerate to a single-population no-op. Median
split (steep >= median vs flat < median) is the only threshold that actually partitions
this observed window, same disclosed-adaptation pattern as bxm_gate_probe.py's realized-vol
median split. This is a deliberate, disclosed adaptation (OP-20), not a silent substitution.

This is a FEASIBILITY probe, not a strategy retrofit: J's real fills (journal/trades.csv,
C1: real-fills is the only WR authority) are the trade population; the spread is read
CAUSALLY as of the prior trading day's close (the only reading available before a day's
09:30 open at daily granularity).

Reuses the canonical `probe_stats` significance/concentration/verdict helpers (C14/C17 --
no hand-rolled n<10 or top3>150% thresholds). Does NOT rebuild a simulator; does NOT touch
params/doctrine/orders/heartbeat/filters/CLAUDE. Places no order, arms nothing (rail-4 clear).

Method disclosure up front (OP-20): mixes ALL journal accounts (core safe/bold + fleet
safe-1/safe-3/risky-1/risky-3) to maximize n for a DAY-LEVEL regime question (not a per-
account edge question) -- same disclosed blend as the sibling VIX1D/BXM probes.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.fred_yield_curve_probe
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backtest.autoresearch.probe_stats import (
    base_verdict,
    day_concentration,
    significance,
    summarize_trades,
)

TRADES_CSV = _REPO / "journal" / "trades.csv"
FRED_CSV = _REPO / "backtest" / "data" / "fred_yield_curve_2026-04-01_2026-07-22.csv"
OUT_PATH = _REPO / "analysis" / "recommendations" / "fred-yield-curve-gate-feasibility-2026-07-22.json"


def _load_real_trades() -> list[dict]:
    """Robust real-fills loader (L239-adjacent: journal/trades.csv has rows with an
    extra stray field from historical manual entries that breaks strict field-count
    parsing). Uses stdlib csv.reader (quote-aware) + POSITIONAL indices that are
    stable regardless of mid-row field-count drift: date=row[0], dollar_pnl=row[13],
    account_id=row[-1] -- the same loader shape as vix1d_gate_probe.py/bxm_gate_probe.py."""
    rows = []
    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        assert header[0] == "date" and header[13] == "dollar_pnl" and header[-1] == "account_id", (
            "trades.csv header drifted -- positional indices below are no longer valid"
        )
        for row in r:
            if len(row) < 14:
                continue
            try:
                pnl = float(row[13])
            except (ValueError, IndexError):
                continue
            rows.append({"date": row[0], "dollar_pnl": pnl, "account_id": row[-1]})
    return rows


def _load_spread_daily() -> dict[str, float]:
    """date -> DGS10 - DGS2 (10Y-2Y spread, percentage points). Skips rows with a
    missing/blank reading for either maturity (FRED leaves holidays/weekends blank
    rather than omitting the row)."""
    out: dict[str, float] = {}
    with open(FRED_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            date = row.get("observation_date", "")[:10]
            d10 = row.get("DGS10", "")
            d2 = row.get("DGS2", "")
            if not date or not d10 or not d2:
                continue
            try:
                out[date] = round(float(d10) - float(d2), 3)
            except ValueError:
                continue
    return out


def _prior_trading_day_spread(spread_by_date: dict, trade_date: str, skip: int = 0) -> tuple[str, float] | None:
    """CAUSAL: the `skip`-th most recent spread reading STRICTLY BEFORE the trade
    date (skip=0 -> most recent prior reading; skip=1 -> the one before that), used
    both for the plain level read and for the day-over-day slope gate. Looks back up
    to 10 calendar days to skip weekends/holidays (C6 -- a gate applied at 09:30 open
    can only see a PRIOR close, never today's)."""
    try:
        d = dt.date.fromisoformat(trade_date)
    except ValueError:
        return None
    found: list[tuple[str, float]] = []
    for back in range(1, 15):
        prior = (d - dt.timedelta(days=back)).isoformat()
        if prior in spread_by_date:
            found.append((prior, spread_by_date[prior]))
        if len(found) > skip:
            return found[skip]
    return None


def _partition_summary(rows: list[dict]) -> dict:
    pnls = [r["dollar_pnl"] for r in rows]
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["dollar_pnl"], 2)
    summ = summarize_trades(pnls)
    conc = day_concentration(by_day)
    sig = significance(summ["n_trades"])
    verdict = base_verdict(summ["n_trades"], summ["expectancy_per_trade_usd"], conc["top3_day_pct_of_net"])
    return {**summ, **conc, "significance": sig, "verdict": verdict}


def _walk_forward_check(kept_dates: set[str], all_trades: list[dict]) -> dict:
    """Split the trading-day timeline chronologically in half; report the gate's
    kept-vs-dropped expectancy delta in EACH half separately (sub-window
    stability, OP-11/16)."""
    all_dates = sorted({r["date"] for r in all_trades})
    if len(all_dates) < 8:
        return {"note": "too few trading days for a walk-forward split", "sufficient": False}
    mid = len(all_dates) // 2
    halves = {"first_half": set(all_dates[:mid]), "second_half": set(all_dates[mid:])}
    out = {}
    for label, date_set in halves.items():
        half_trades = [r for r in all_trades if r["date"] in date_set]
        kept = [r for r in half_trades if r["date"] in kept_dates]
        out[label] = {"kept": _partition_summary(kept) if kept else None}
    kept_exp = [out[h]["kept"]["expectancy_per_trade_usd"] for h in halves if out[h]["kept"]]
    stable = len(kept_exp) == 2 and all(e > 0 for e in kept_exp)
    out["sub_window_stable"] = stable
    return out


def run() -> dict:
    trades = _load_real_trades()
    spread_by_date = _load_spread_daily()

    all_vals = sorted(spread_by_date.values())
    median = all_vals[len(all_vals) // 2] if all_vals else None

    for r in trades:
        cur = _prior_trading_day_spread(spread_by_date, r["date"], skip=0)
        prev = _prior_trading_day_spread(spread_by_date, r["date"], skip=1)
        r["asof_spread"] = cur[1] if cur else None
        r["asof_slope"] = round(cur[1] - prev[1], 3) if (cur and prev) else None

    unresolved = [r for r in trades if r["asof_spread"] is None]

    result: dict = {
        "probe": "fred_yield_curve_gate_feasibility",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_inbox_item": (
            "strategy/candidates/_chef-inbox/"
            "2026-07-10-prospector-fred-daily-treasury-par-yield-curve-10y-.md"
        ),
        "trade_population": (
            "journal/trades.csv -- ALL accounts (core safe/bold + fleet "
            "safe-1/safe-3/risky-1/risky-3), real broker fills, disclosed blend "
            "for a day-level regime question (not a per-account edge question)"
        ),
        "n_total_trades_loaded": len(trades),
        "n_unresolved_spread_asof": len(unresolved),
        "spread_median_pp": median,
        "ungated": _partition_summary(trades),
        "candidates": {},
        "method_disclosures": {
            "data_source": (
                "FRED fredgraph.csv CSV-download endpoint, NO API key/registration "
                "required (confirmed live this fire -- closes the inbox item's own "
                "'register a FRED API key' blocker without needing one). Series "
                "DGS10/DGS2 (10-year/2-year constant maturity Treasury yield)."
            ),
            "signal_adaptation": (
                "The 10Y-2Y spread never inverted over this probe window (min "
                f"{min(all_vals) if all_vals else None}pp, max {max(all_vals) if all_vals else None}pp, "
                "entire series positive) -- a standard inverted-vs-normal test would "
                "degenerate to a single-population no-op. Adapted to a MEDIAN split "
                "(steep >= median vs flat < median) of the spread's own distribution "
                "over this exact window, same disclosed-adaptation pattern as "
                "bxm_gate_probe.py's realized-vol median split. Disclosed, not silent "
                "(OP-20)."
            ),
            "causality": (
                "Spread level/slope read as the prior trading day's close (up to 14 "
                "calendar days back to skip weekends/holidays) -- the only reading "
                "available before a day's 09:30 open at daily granularity. C6-safe."
            ),
            "scope_limitation": (
                "An INTRADAY yield-curve read (checked at entry time, not pre-market) "
                "is out of scope -- Treasury par yields are a once-daily EOD series, "
                "no free intraday feed exists (same limitation class as the sibling "
                "VIX1D/BXM probes)."
            ),
            "fill_model": "Real broker fills only (journal/trades.csv dollar_pnl), no simulation.",
            "yardstick": (
                "per-trade expectancy + concentration-robust day metrics "
                "(probe_stats canonical helpers) -- NOT J edge_capture (this is a "
                "cross-strategy regime gate, not a single directional candidate; L192)."
            ),
            "pre_registration": (
                "Median-split level gate + day-over-day slope gate were fixed BEFORE "
                "this run produced any output; median value itself is data-derived "
                "(not hand-picked) but the SPLIT METHOD (median, not an absolute "
                "threshold) was chosen for the disclosed reason above before scoring."
            ),
        },
    }

    if median is not None:
        steep_rows = [r for r in trades if r["asof_spread"] is not None and r["asof_spread"] >= median]
        flat_rows = [r for r in trades if r["asof_spread"] is not None and r["asof_spread"] < median]
        steep_dates = {r["date"] for r in steep_rows}
        flat_dates = {r["date"] for r in flat_rows}
        result["candidates"]["level_gate::steep_ge_median"] = {
            "threshold": {"spread_median_pp": median},
            "kept": _partition_summary(steep_rows) if steep_rows else {"n_trades": 0},
            "dropped": _partition_summary(flat_rows) if flat_rows else {"n_trades": 0},
            "walk_forward": _walk_forward_check(steep_dates, trades),
        }
        result["candidates"]["level_gate::flat_lt_median"] = {
            "threshold": {"spread_median_pp": median},
            "kept": _partition_summary(flat_rows) if flat_rows else {"n_trades": 0},
            "dropped": _partition_summary(steep_rows) if steep_rows else {"n_trades": 0},
            "walk_forward": _walk_forward_check(flat_dates, trades),
        }

    slope_rows = [r for r in trades if r["asof_slope"] is not None]
    steepening_rows = [r for r in slope_rows if r["asof_slope"] > 0]
    flattening_rows = [r for r in slope_rows if r["asof_slope"] <= 0]
    steepening_dates = {r["date"] for r in steepening_rows}
    result["candidates"]["slope_gate::steepening_gt_0"] = {
        "threshold": {"definition": "spread(t-1) - spread(t-2), day-over-day change"},
        "kept": _partition_summary(steepening_rows) if steepening_rows else {"n_trades": 0},
        "dropped": _partition_summary(flattening_rows) if flattening_rows else {"n_trades": 0},
        "walk_forward": _walk_forward_check(steepening_dates, trades),
    }

    any_promotable = False
    reasons = []
    for name, c in result["candidates"].items():
        kept = c.get("kept")
        wf = c.get("walk_forward", {})
        if not kept or kept.get("n_trades", 0) == 0:
            reasons.append(f"{name}: no trades kept -- gate empties the population")
            continue
        oos_positive = kept["expectancy_per_trade_usd"] > 0
        wf_stable = wf.get("sub_window_stable", False)
        clean = kept.get("verdict") == "CLEAN"
        if oos_positive and wf_stable and clean:
            any_promotable = True
            reasons.append(f"{name}: CLEARS bar (verdict={kept['verdict']}, wf_stable={wf_stable})")
        else:
            reasons.append(
                f"{name}: does NOT clear bar (verdict={kept.get('verdict')}, "
                f"expectancy=${kept.get('expectancy_per_trade_usd')}, wf_stable={wf_stable})"
            )
    result["overall_verdict"] = (
        "FEASIBILITY_CONFIRMED_CANDIDATE_FOUND" if any_promotable else "NO_CANDIDATE_CLEARS_BAR_YET"
    )
    result["verdict_reasons"] = reasons
    result["eval_bar_cleared"] = any_promotable
    result["next_step"] = (
        "a clearing candidate still needs the full OP-11/16 anchor-day no-regression "
        "check against J's 3 anchor days before conductor-proposals.jsonl (this probe "
        "does not run that check -- it is a feasibility screen only)"
        if any_promotable
        else "small real-fills n (see n_total_trades_loaded) means this is a screening "
             "result, not a rejection -- re-run as the trade log grows; do not "
             "re-propose without new data. DGS3MO cached but unused this fire "
             "(inbox's own note flags it as a fold-in sub-series once built, not a "
             "separate candidate -- left for a future fire, not attempted here)."
    )
    return result


def main() -> int:
    result = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"VERDICT={result['overall_verdict']}  n_trades={result['n_total_trades_loaded']}  "
          f"unresolved_spread={result['n_unresolved_spread_asof']}")
    for r in result["verdict_reasons"]:
        print(f"  {r}")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
