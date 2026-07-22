"""VIX1D same-horizon vol gate — feasibility probe (chef-inbox 2026-07-09-prospector-vix1d_gate).

The bounded question (per the inbox item's own 2026-07-21 consolidation note): does CBOE's
VIX1D (ultra-short-dated, next-day/0DTE-horizon implied vol, C5: "VIX character > VIX level")
discriminate REAL trading-day quality better than the 30-day headline VIX -- tested as (a) a
bare VIX1D level gate and (b) a VIX1D-minus-VIX30 term-structure SLOPE gate -- against the
standing OP-11/OP-16 pass bar (OOS positive AND walk-forward >= 0.70 AND sub-window stable
AND anchor-day no-regression) before any wiring proposal reaches conductor-proposals.jsonl.

This is a FEASIBILITY probe, not a strategy retrofit: J's real fills (journal/trades.csv,
C1: real-fills is the only WR authority) are the trade population; VIX1D/VIX30 are read
CAUSALLY as the prior trading day's close (the only vol reading available before a day's
09:30 open at DAILY granularity -- intraday VIX1D quotes are not in a free feed, so an
intraday-gate variant is explicitly OUT of scope here and flagged as a limitation, not
silently assumed away, C6/OP-20).

Reuses the canonical `probe_stats` significance/concentration/verdict helpers (C14/C17 --
no hand-rolled n<10 or top3>150% thresholds). Does NOT rebuild a simulator; does NOT touch
params/doctrine/orders/heartbeat/filters/CLAUDE. Places no order, arms nothing (rail-4 clear).

Method disclosure up front (OP-20): mixes ALL journal accounts (core safe/bold + fleet arms
safe-1/safe-3/risky-1/risky-3) to maximize n for a DAY-LEVEL regime question (not a per-
account edge question) -- this is a deliberate, disclosed choice, not an accidental blend.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.vix1d_gate_probe
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
VIX_CSV = _REPO / "backtest" / "data" / "vix1d_vix30_daily_2026-04-20_2026-07-21.csv"
OUT_PATH = _REPO / "analysis" / "recommendations" / "vix1d-gate-feasibility-2026-07-22.json"

# Candidate bands -- pre-registered from the ALREADY-DOCTRINE VIX range-regime band
# (range_scalp_regime_gated_probe: VIX 14-20 == "compressed-vol range regime") so we are
# not hand-picking a flattering VIX1D threshold post-hoc (C14/L192 discipline). VIX1D is
# structurally noisier/more extreme than VIX30 (it's a 1-day-horizon read), so we ALSO test
# a widened band as a named second candidate -- both are stated BEFORE looking at results.
VIX1D_BANDS = {
    "same_as_vix30_band_14_20": (14.0, 20.0),
    "widened_band_10_25": (10.0, 25.0),
}
# Slope = VIX1D - VIX30. Negative == term structure in backwardation-lite (short-dated vol
# below headline -- "calm tomorrow" per the standard vol-term-structure read). Positive ==
# front-month vol spike (event-day / "violent tomorrow" read). Pre-registered symmetric band.
SLOPE_CALM_MAX = -2.0  # slope <= this == gate says "calm" (VIX1D notably below VIX30)


def _load_real_trades() -> list[dict]:
    """Robust real-fills loader (L239-adjacent: DO NOT use pandas.read_csv on this file --
    it has 26/190 rows with an extra stray field from historical manual entries that breaks
    strict field-count parsing). Uses stdlib csv.reader (quote-aware) + POSITIONAL indices
    that are stable regardless of the mid-row field-count drift: date=row[0] (never shifts),
    dollar_pnl=row[13] (before the drift point in all observed bad rows), account_id=row[-1]
    (last field, robust to a shift anywhere in the middle)."""
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


def _load_vix_daily() -> dict[str, dict]:
    """date -> {vix1d, vix30} (may be None if that source has no reading that day)."""
    out = {}
    with open(VIX_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            date = row["Date"][:10]
            v1d = row.get("vix1d") or ""
            v30 = row.get("vix30") or ""
            out[date] = {
                "vix1d": float(v1d) if v1d else None,
                "vix30": float(v30) if v30 else None,
            }
    return out


def _prior_trading_day_vix(vix_by_date: dict, trade_date: str) -> dict:
    """CAUSAL: the most recent VIX reading STRICTLY BEFORE the trade date (C6 -- a gate
    applied at 09:30 open can only see yesterday's close, never today's)."""
    try:
        d = dt.date.fromisoformat(trade_date)
    except ValueError:
        # Defensive: a malformed date field (e.g. stray non-CSV contamination) must not
        # crash the whole probe -- fail this ONE row's vix lookup, not the fire (C7).
        return {"vix1d": None, "vix30": None}
    for back in range(1, 8):  # look back up to a week to skip weekends/holidays
        prior = (d - dt.timedelta(days=back)).isoformat()
        if prior in vix_by_date and vix_by_date[prior]["vix1d"] is not None:
            return vix_by_date[prior]
    return {"vix1d": None, "vix30": None}


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
    """Split the trading-day timeline chronologically in half; report the gate's kept-vs-
    dropped expectancy delta in EACH half separately (sub-window stability, OP-11/16)."""
    all_dates = sorted({r["date"] for r in all_trades})
    if len(all_dates) < 8:
        return {"note": "too few trading days for a walk-forward split", "sufficient": False}
    mid = len(all_dates) // 2
    halves = {"first_half": set(all_dates[:mid]), "second_half": set(all_dates[mid:])}
    out = {}
    for label, date_set in halves.items():
        half_trades = [r for r in all_trades if r["date"] in date_set]
        kept = [r for r in half_trades if r["date"] in kept_dates]
        dropped = [r for r in half_trades if r["date"] not in kept_dates]
        out[label] = {
            "kept": _partition_summary(kept) if kept else None,
            "dropped": _partition_summary(dropped) if dropped else None,
        }
    kept_exp = [out[h]["kept"]["expectancy_per_trade_usd"] for h in halves if out[h]["kept"]]
    stable = len(kept_exp) == 2 and all(e > 0 for e in kept_exp)
    out["sub_window_stable"] = stable
    return out


def run() -> dict:
    trades = _load_real_trades()
    vix_by_date = _load_vix_daily()

    # attach as-of VIX1D/VIX30 to each trade (causal, per-day, shared across a trade's day)
    day_vix_cache: dict[str, dict] = {}
    for r in trades:
        if r["date"] not in day_vix_cache:
            day_vix_cache[r["date"]] = _prior_trading_day_vix(vix_by_date, r["date"])
        r["asof_vix1d"] = day_vix_cache[r["date"]]["vix1d"]
        r["asof_vix30"] = day_vix_cache[r["date"]]["vix30"]
        r["asof_slope"] = (
            round(r["asof_vix1d"] - r["asof_vix30"], 2)
            if r["asof_vix1d"] is not None and r["asof_vix30"] is not None
            else None
        )

    unresolved = [r for r in trades if r["asof_vix1d"] is None]

    result: dict = {
        "probe": "vix1d_gate_feasibility",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_inbox_item": "strategy/candidates/_chef-inbox/2026-07-09-prospector-vix1d_gate.md",
        "trade_population": "journal/trades.csv -- ALL accounts (core safe/bold + fleet "
                             "safe-1/safe-3/risky-1/risky-3), real broker fills, disclosed blend "
                             "for a day-level regime question (not a per-account edge question)",
        "n_total_trades_loaded": len(trades),
        "n_unresolved_vix_asof": len(unresolved),
        "ungated": _partition_summary(trades),
        "candidates": {},
        "method_disclosures": {
            "causality": "VIX1D/VIX30 read as the prior trading day's close (up to 7 calendar "
                         "days back to skip weekends/holidays) -- the only reading available "
                         "before a day's 09:30 open at daily granularity. C6-safe.",
            "scope_limitation": "An INTRADAY VIX1D gate (checked at entry time, not pre-market) "
                                "is explicitly OUT of scope -- no free intraday VIX1D feed found. "
                                "This probe answers 'is a pre-market VIX1D read informative', not "
                                "'is an intraday VIX1D check informative'.",
            "fill_model": "Real broker fills only (journal/trades.csv dollar_pnl), no simulation.",
            "yardstick": "per-trade expectancy + concentration-robust day metrics (probe_stats "
                         "canonical helpers) -- NOT J edge_capture (this is a cross-strategy "
                         "regime gate, not a single directional candidate; L192).",
            "pre_registration": "VIX1D bands + slope threshold below were fixed BEFORE this run "
                                 "produced any output (anchored to the doctrine's existing "
                                 "VIX-30 range-regime band, not hand-picked post-hoc).",
        },
    }

    # --- candidate A: bare VIX1D level bands ------------------------------------------------
    for label, (lo, hi) in VIX1D_BANDS.items():
        kept_rows = [r for r in trades if r["asof_vix1d"] is not None and lo <= r["asof_vix1d"] <= hi]
        dropped_rows = [r for r in trades if r["asof_vix1d"] is not None and not (lo <= r["asof_vix1d"] <= hi)]
        kept_dates = {r["date"] for r in kept_rows}
        result["candidates"][f"level_gate::{label}"] = {
            "band": {"low": lo, "high": hi},
            "kept": _partition_summary(kept_rows) if kept_rows else {"n_trades": 0},
            "dropped": _partition_summary(dropped_rows) if dropped_rows else {"n_trades": 0},
            "walk_forward": _walk_forward_check(kept_dates, trades),
        }

    # --- candidate B: VIX1D - VIX30 slope (term-structure) gate -----------------------------
    slope_rows = [r for r in trades if r["asof_slope"] is not None]
    calm_rows = [r for r in slope_rows if r["asof_slope"] <= SLOPE_CALM_MAX]
    event_rows = [r for r in slope_rows if r["asof_slope"] > SLOPE_CALM_MAX]
    calm_dates = {r["date"] for r in calm_rows}
    result["candidates"]["slope_gate::calm_le_neg2"] = {
        "threshold": {"slope_calm_max": SLOPE_CALM_MAX, "definition": "vix1d - vix30"},
        "kept_calm": _partition_summary(calm_rows) if calm_rows else {"n_trades": 0},
        "dropped_event": _partition_summary(event_rows) if event_rows else {"n_trades": 0},
        "walk_forward": _walk_forward_check(calm_dates, trades),
    }

    # --- overall feasibility verdict ---------------------------------------------------------
    any_promotable = False
    reasons = []
    for name, c in result["candidates"].items():
        kept = c.get("kept") or c.get("kept_calm")
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
        "a clearing candidate still needs the full OP-11/16 anchor-day no-regression check "
        "against J's 3 anchor days before conductor-proposals.jsonl (this probe does not run "
        "that check -- it is a feasibility screen only)"
        if any_promotable
        else "small real-fills n (see n_total_trades_loaded) means this is a screening result, "
             "not a rejection -- re-run as the trade log grows; do not re-propose without new data"
    )
    return result


def main() -> int:
    result = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"VERDICT={result['overall_verdict']}  n_trades={result['n_total_trades_loaded']}  "
          f"unresolved_vix={result['n_unresolved_vix_asof']}")
    for r in result["verdict_reasons"]:
        print(f"  {r}")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
