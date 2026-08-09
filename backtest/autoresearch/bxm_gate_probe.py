"""CBOE BuyWrite Index (BXM) — feasibility probe (chef-inbox
2026-07-10-prospector-cboe-buywrite-index-bxm-real-time-levels).

The bounded question (per the inbox item): does the CBOE BuyWrite Index (BXM — a
covered-call-writing benchmark reflecting institutional option-premium collection
pressure) carry a testable directional/timing signal for 0DTE SPY entries, tested
as a same-structure DAILY realized-volatility-of-BXM gate (compressed vs elevated
covered-call-writing activity), against the standing OP-11/OP-16 pass bar (OOS
positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day
no-regression) before any wiring proposal reaches conductor-proposals.jsonl.

Method note (why realized-vol-of-BXM, not raw BXM level): BXM is a PRICE INDEX
(covered-call total-return benchmark), not a vol reading like VIX — its raw level
is non-stationary and trends with SPX, so a level-band gate (as used for VIX1D)
is not the right shape. What the prospector's finding actually claims testable
signal in ("volatility compression or expansion ahead of expiry") is a REALIZED-
VOL-OF-BXM-RETURNS read, which is stationary and analogous in structure to the
VIX1D probe's level-band gate. This is a deliberate, disclosed adaptation of the
inbox ask to a testable form (OP-20), not a silent substitution.

This is a FEASIBILITY probe, not a strategy retrofit: J's real fills
(journal/trades.csv, C1: real-fills is the only WR authority) are the trade
population; BXM 5-day realized vol is read CAUSALLY as of the prior trading day's
close (the only reading available before a day's 09:30 open at daily granularity).

Reuses the canonical `probe_stats` significance/concentration/verdict helpers
(C14/C17 — no hand-rolled n<10 or top3>150% thresholds). Does NOT rebuild a
simulator; does NOT touch params/doctrine/orders/heartbeat/filters/CLAUDE. Places
no order, arms nothing (rail-4 clear).

Method disclosure up front (OP-20): mixes ALL journal accounts (core safe/bold +
fleet safe-1/safe-3/risky-1/risky-3) to maximize n for a DAY-LEVEL regime question
(not a per-account edge question) — a deliberate, disclosed choice (same pattern
as vix1d_gate_probe.py), not an accidental blend.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.bxm_gate_probe
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
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
BXM_CSV = _REPO / "backtest" / "data" / "bxm_daily_2026-04-01_2026-07-21.csv"
OUT_PATH = _REPO / "analysis" / "recommendations" / "bxm-gate-feasibility-2026-07-22.json"

# Pre-registered BEFORE looking at gated results: a 5-trading-day trailing realized
# vol of BXM's daily log returns (annualized, %). Bands are a simple median-split
# of the BXM series' OWN historical realized-vol distribution over the probe window
# (not hand-picked to flatter any candidate) — "compressed" = below-median BXM
# realized vol (calm covered-call regime), "elevated" = above-median (event/roll
# stress). ROLL_WINDOW=5 chosen to match a single trading week, the same horizon
# the inbox item's "ahead of expiry" framing implies for a 0DTE-adjacent read.
ROLL_WINDOW = 5


def _load_real_trades() -> list[dict]:
    """Robust real-fills loader (L239-adjacent: journal/trades.csv has rows with an
    extra stray field from historical manual entries that breaks strict field-count
    parsing). Uses stdlib csv.reader (quote-aware) + POSITIONAL indices for the
    stable leading columns (date=row[0], dollar_pnl=row[13]) but a NAME-based
    lookup for account_id (BXM-PROBE-TRADES-CSV-HEADER-DRIFT-FIX, 2026-08-08: a
    trailing column, theta_at_entry, was appended AFTER account_id on 2026-08-01,
    breaking the old `header[-1] == "account_id"` fixed-position assumption --
    name-lookup is robust to any FUTURE trailing-column append too, not just this
    one). Same loader shape as vix1d_gate_probe.py — fix both when touching either."""
    rows = []
    with open(TRADES_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        assert header[0] == "date" and header[13] == "dollar_pnl" and "account_id" in header, (
            "trades.csv header drifted -- positional indices below are no longer valid"
        )
        account_idx = header.index("account_id")
        for row in r:
            if len(row) < 14 or len(row) <= account_idx:
                continue
            try:
                pnl = float(row[13])
            except (ValueError, IndexError):
                continue
            rows.append({"date": row[0], "dollar_pnl": pnl, "account_id": row[account_idx]})
    return rows


def _load_bxm_realized_vol() -> dict[str, float]:
    """date -> trailing ROLL_WINDOW-day annualized realized vol (%) of BXM log
    returns, keyed to the date the vol reading BECOMES AVAILABLE (that date's own
    close), so a caller doing a "prior trading day" lookback stays causal (C6)."""
    closes: list[tuple[str, float]] = []
    with open(BXM_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            date = row.get("Date", "")[:10]
            close = row.get("Close", "")
            if not date or not close:
                continue
            try:
                closes.append((date, float(close)))
            except ValueError:
                continue
    closes.sort(key=lambda x: x[0])
    log_rets = []
    for i in range(1, len(closes)):
        prev = closes[i - 1][1]
        cur = closes[i][1]
        if prev > 0 and cur > 0:
            log_rets.append((closes[i][0], math.log(cur / prev)))
    out: dict[str, float] = {}
    for i in range(ROLL_WINDOW - 1, len(log_rets)):
        window = [log_rets[j][1] for j in range(i - ROLL_WINDOW + 1, i + 1)]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        ann_vol_pct = math.sqrt(var) * math.sqrt(252) * 100.0
        out[log_rets[i][0]] = round(ann_vol_pct, 3)
    return out


def _prior_trading_day_reading(readings: dict[str, float], trade_date: str) -> float | None:
    """CAUSAL: the most recent BXM realized-vol reading STRICTLY BEFORE the trade
    date (C6 — a gate applied at 09:30 open can only see yesterday's close)."""
    try:
        d = dt.date.fromisoformat(trade_date)
    except ValueError:
        return None
    for back in range(1, 8):
        prior = (d - dt.timedelta(days=back)).isoformat()
        if prior in readings:
            return readings[prior]
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
    readings = _load_bxm_realized_vol()

    all_vals = sorted(readings.values())
    median = all_vals[len(all_vals) // 2] if all_vals else None

    for r in trades:
        r["asof_bxm_rvol"] = _prior_trading_day_reading(readings, r["date"])

    unresolved = [r for r in trades if r["asof_bxm_rvol"] is None]

    result: dict = {
        "probe": "bxm_gate_feasibility",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_inbox_item": (
            "strategy/candidates/_chef-inbox/"
            "2026-07-10-prospector-cboe-buywrite-index-bxm-real-time-levels.md"
        ),
        "trade_population": (
            "journal/trades.csv -- ALL accounts (core safe/bold + fleet "
            "safe-1/safe-3/risky-1/risky-3), real broker fills, disclosed blend "
            "for a day-level regime question (not a per-account edge question)"
        ),
        "n_total_trades_loaded": len(trades),
        "n_unresolved_bxm_asof": len(unresolved),
        "bxm_rvol_median_pct": median,
        "ungated": _partition_summary(trades),
        "candidates": {},
        "method_disclosures": {
            "signal_adaptation": (
                "BXM is a covered-call TOTAL-RETURN price index, not a vol level -- "
                "its raw close is non-stationary and trends with SPX, so (unlike "
                "VIX1D) a level-band gate is the wrong shape. Adapted to a "
                f"{ROLL_WINDOW}-day trailing annualized realized vol of BXM's own "
                "daily log returns (stationary), which is the closest testable form "
                "of the inbox finding's 'volatility compression/expansion' claim. "
                "Disclosed substitution, not silent (OP-20)."
            ),
            "causality": (
                "BXM realized-vol read as the prior trading day's close (up to 7 "
                "calendar days back to skip weekends/holidays) -- the only reading "
                "available before a day's 09:30 open at daily granularity. C6-safe."
            ),
            "scope_limitation": (
                "An INTRADAY BXM read (checked at entry time, not pre-market) is "
                "out of scope -- BXM is a once-daily index, no intraday free feed "
                "exists (same limitation class as vix1d_gate_probe.py)."
            ),
            "fill_model": "Real broker fills only (journal/trades.csv dollar_pnl), no simulation.",
            "yardstick": (
                "per-trade expectancy + concentration-robust day metrics "
                "(probe_stats canonical helpers) -- NOT J edge_capture (this is a "
                "cross-strategy regime gate, not a single directional candidate; L192)."
            ),
            "pre_registration": (
                "Compressed/elevated split is a MEDIAN split of BXM's own realized-"
                "vol distribution over this exact probe window (not a hand-picked "
                "flattering threshold); ROLL_WINDOW=5 fixed before any candidate "
                "was scored."
            ),
        },
    }

    if median is not None:
        compressed_rows = [
            r for r in trades if r["asof_bxm_rvol"] is not None and r["asof_bxm_rvol"] <= median
        ]
        elevated_rows = [
            r for r in trades if r["asof_bxm_rvol"] is not None and r["asof_bxm_rvol"] > median
        ]
        compressed_dates = {r["date"] for r in compressed_rows}
        elevated_dates = {r["date"] for r in elevated_rows}
        result["candidates"]["rvol_gate::compressed_le_median"] = {
            "threshold": {"bxm_rvol_median_pct": median, "window_days": ROLL_WINDOW},
            "kept": _partition_summary(compressed_rows) if compressed_rows else {"n_trades": 0},
            "dropped": _partition_summary(elevated_rows) if elevated_rows else {"n_trades": 0},
            "walk_forward": _walk_forward_check(compressed_dates, trades),
        }
        result["candidates"]["rvol_gate::elevated_gt_median"] = {
            "threshold": {"bxm_rvol_median_pct": median, "window_days": ROLL_WINDOW},
            "kept": _partition_summary(elevated_rows) if elevated_rows else {"n_trades": 0},
            "dropped": _partition_summary(compressed_rows) if compressed_rows else {"n_trades": 0},
            "walk_forward": _walk_forward_check(elevated_dates, trades),
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
             "re-propose without new data"
    )
    return result


def main() -> int:
    result = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"VERDICT={result['overall_verdict']}  n_trades={result['n_total_trades_loaded']}  "
          f"unresolved_bxm={result['n_unresolved_bxm_asof']}")
    for r in result["verdict_reasons"]:
        print(f"  {r}")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
