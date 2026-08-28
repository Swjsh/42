"""prod_shadow.py -- PROD-1 SHADOW: one production-candidate arm, measured the way real
money would be (TASK C1, built 2026-08-28).

WHAT THIS IS. A measurement instrument, not a new trading account and not a new signal
source. It derives, from ONE real arm's already-realized fills in the canonical ledger
(analysis/trades-enriched.jsonl, built by trades_enriched.py), what a single
production-configured arm would have made every day if it had been sized at a
Kelly-informed fraction of equity instead of the current 30%/50% caps, paid realistic
regulatory fees + exit slippage, and stopped itself for the day after a bounded loss. No
new broker account, no live keys, no orders -- READ analysis/trades-enriched.jsonl and
analysis/recommendations/cost-model.json, WRITE only under analysis/prod-shadow/.

WHY safe-2 IS THE BASE ARM, NOT A 5-ARM BLEND. Session ground truth (TASK A2/adversarial
review, 2026-08-28) established the 5 active arms trade ONE shared signal (r~0.62-0.85
pairwise, effective independent arms ~1.44 of nominal 5) and safe-2 (CORE-SAFE, account
PA3POKNV46VG) is the specific arm A2 identified as the live-eligible core candidate with a
directly-reconciled broker history. Using safe-2 alone sidesteps the multi-arm
double-counting problem by construction -- this IS one arm, not an aggregate presented as
one arm.

WHY THIS DOES NOT CALL backtest/lib/exit_manager_walk.py DIRECTLY, THOUGH THE TASK NAMED IT.
walk_exit_manager exists to RE-DERIVE what the live exit_manager.plan_exit_actions decision
core would do, tick-by-tick over bar data, when you don't already have a realized outcome
(e.g. a counterfactual "what if this gate had passed" scorecard). Here the outcome already
happened for real: safe-2's exit_reason/exit_ts_et/ret_pct_of_premium in trades-enriched.jsonl
IS that module's own authoritative decision core having already run live. Re-walking it from
1-minute option bars would reproduce the SAME exit trigger and timing, because exit_manager's
price-trigger logic (TP1 level, premium stop, structure stop, trailing floor) is evaluated
against the PREMIUM PATH, never against position size -- qty only changes how many contracts
execute at each already-determined trigger, not whether/when it fires. This is verified, not
assumed: exit_manager.ExitState.from_entry stores qty only to size legs
(state.qty / tp1_qty_fraction), never as an input to any trigger condition. Rescaling qty
after the fact and keeping the recorded ret_pct_of_premium (the qty-invariant, partial-exit-
weighted blended return) is therefore equivalent to re-walking the bars for THIS purpose --
cheaper, no OPRA cache dependency, and byte-reproducible from the ledger alone. What this
means we do NOT model: a materially different qty could plausibly move the fill price itself
(see TASK B2's liquidity-depth findings) -- max_contracts (default 20) exists partly to keep
the shadow's qty in the range B2 measured as not yet the binding constraint, and this
limitation is disclosed in summary.json's honesty block, not hidden.

SIZING (the actual production-candidate change under test). risk_fraction_per_trade defaults
to 0.02 (2% of running equity spent on premium per trade) -- inside the 1.86%-3.72% half-to-
full-Kelly band TASK A2/B2 computed from safe-2's own August WR/payoff, chosen as a round,
conservative point estimate given P(PF<=1.0)~0.40 argues for sizing below Kelly, not at it.
Current live caps (30% Safe / 50% Bold) are 8-18x this. max_contracts (default 20) matches
the fleet's own position_sizing_tiers ceiling (TASK B2 finding: the largest order the entire
rig can ever request today). daily_stop_pct (default 0.06, i.e. 3x the per-trade fraction) is
a DISCLOSED ASSUMPTION, not a validated number -- no source in this repo pins a specific
daily-stop multiple for this sizing regime; it is carried explicitly as a knob, not asserted
as correct.

COSTS. Reuses analysis/recommendations/cost-model.json's OWN empirically-sourced rate
schedule (COST-REALISM-2026-08-18.md) rather than re-deriving fresh numbers: OCC/ORF (both
sides), TAF/SEC (exit/sell side only), CAT (once per arm-day with activity), and the
conservative exit-slippage assumption (2c/contract premium, i.e. $2/contract dollar impact).
TASK A1's finding stands and is not re-litigated here: this exit-slippage number is a
MODELING ASSUMPTION, not a measurement -- no bid/ask-at-exit data source exists anywhere in
this repo (see cost-model.json's own spread_evidence_entry_side.conclusion).

DAILY STOP. Trades within a date are walked in entry_ts_et order; once realized net P&L for
the day (after fees+slippage) breaches -daily_stop_pct * day_start_equity, every remaining
signal that day is logged as skipped_daily_stop (never silently dropped -- still one ledger
row each) and no further capital is risked that day.

PDT / SETTLEMENT. Alpaca offers no cash-account product (all margin, per TASK A1's regulatory
research) and CLAUDE.md records the $25K PDT floor as FINRA-repealed 2026-06-04, so a rolling
5-trading-day day-trade-count breach does NOT block anything here. It IS computed and
disclosed per day (pdt_flag_old_regime_nonbinding) as a regime-reversal-risk signal, following
C4's disclosure-not-silence convention, never used to gate simulated trades.

OUTPUTS. analysis/prod-shadow/ledger.jsonl (one row per signal, executed or skipped, full
cost attribution) + analysis/prod-shadow/summary.json (config, daily series with the actual
shadow P&L printed next to the $2,000/day aspiration and the equity that aspiration would
require AT THIS SHADOW'S OWN OBSERVED RETURN DISTRIBUTION, period totals for full-history /
August-2026 / pre-August, the four scorecard_guards structural guards, drawdown, and an
explicit honesty-disclosures block). Rebuilt nightly via daily_brief.py's eod chain
(_rebuild_prod_shadow, fail-open, no new scheduled task) -- see that file's docstring.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
TRADES_ENRICHED_PATH = REPO / "analysis" / "trades-enriched.jsonl"
COST_MODEL_PATH = REPO / "analysis" / "recommendations" / "cost-model.json"
OUT_DIR = REPO / "analysis" / "prod-shadow"
LEDGER_PATH = OUT_DIR / "ledger.jsonl"
SUMMARY_PATH = OUT_DIR / "summary.json"

sys.path.insert(0, str(REPO / "setup" / "scripts" / "lib"))
import scorecard_guards as sg  # noqa: E402

DEFAULT_BASE_ARM = "safe-2"
DEFAULT_STARTING_EQUITY = 5000.0
DEFAULT_RISK_FRACTION = 0.02
DEFAULT_MAX_CONTRACTS = 20
DEFAULT_DAILY_STOP_PCT = 0.06
DAILY_TARGET_DOLLARS = 2000.0
PDT_OLD_REGIME_MAX_5DAY = 3
AUGUST_START = "2026-08-01"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_cost_model_rates(path: Path = COST_MODEL_PATH) -> tuple[dict, Optional[str]]:
    with open(path, "r", encoding="utf-8") as fh:
        cm = json.load(fh)
    return cm["rates"], cm.get("generated_et")


def load_source_trades(arm: str = DEFAULT_BASE_ARM, path: Path = TRADES_ENRICHED_PATH) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("_meta"):
                continue
            if row.get("arm") != arm:
                continue
            rows.append(row)
    rows.sort(key=lambda r: (r["date"], r.get("entry_ts_et") or ""))
    return rows


# --------------------------------------------------------------------------- #
# Sizing + costs (unit-testable in isolation -- see backtest/tests)
# --------------------------------------------------------------------------- #

def size_position(equity: float, risk_fraction: float, entry_px: Optional[float],
                   max_contracts: int) -> tuple[int, float]:
    """Returns (qty, risk_dollars_considered). qty=0 means this real, small account cannot
    afford even 1 contract at the risk_fraction cap -- a genuine constraint, logged as a
    skip, never silently rounded up."""
    if not entry_px or entry_px <= 0:
        return 0, 0.0
    risk_dollars = risk_fraction * equity
    cost_per_contract = entry_px * 100.0
    max_afford = math.floor(risk_dollars / cost_per_contract) if cost_per_contract > 0 else 0
    return max(0, min(max_afford, max_contracts)), risk_dollars


def compute_costs(qty: int, entry_px: float, ret_pct_of_premium: float, rates: dict) -> dict:
    """Fee + exit-slippage model, reusing cost-model.json's rate schedule verbatim.
    exit_price is reconstructed ONLY to compute the SEC fee's sell-proceeds base -- pnl
    itself is derived from ret_pct_of_premium (see module docstring), not from this price."""
    if qty <= 0:
        return {"occ": 0.0, "orf": 0.0, "taf": 0.0, "sec": 0.0,
                "fee_total_ex_cat": 0.0, "slippage_dollars": 0.0, "exit_price_reconstructed": None}
    exit_price = max(0.0, entry_px * (1.0 + ret_pct_of_premium / 100.0))
    sell_proceeds = exit_price * qty * 100.0
    occ = rates["occ_fee_per_contract_both_sides"] * qty * 2.0
    orf = rates["orf_fee_per_contract_both_sides"] * qty * 2.0
    taf = rates["taf_fee_per_contract_sells_only"] * qty
    sec = rates["sec_fee_rate_per_dollar_sells_only"] * sell_proceeds
    slippage = rates["exit_spread_adjustment_conservative_per_contract"] * qty * 100.0
    return {
        "occ": round(occ, 4), "orf": round(orf, 4), "taf": round(taf, 4), "sec": round(sec, 4),
        "fee_total_ex_cat": round(occ + orf + taf + sec, 4),
        "slippage_dollars": round(slippage, 4),
        "exit_price_reconstructed": round(exit_price, 4),
    }


def rolling_window_dates(date_str: str, all_dates: list[str], n: int = 5) -> list[str]:
    """The n most recent TRADING days up to and including date_str, drawn from the observed
    trading-day calendar (never a naive calendar-day subtraction -- would miscount across
    weekends/holidays)."""
    idx = all_dates.index(date_str)
    return all_dates[max(0, idx - n + 1):idx + 1]


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #

def simulate(source_trades: list[dict], rates: dict,
             starting_equity: float = DEFAULT_STARTING_EQUITY,
             risk_fraction: float = DEFAULT_RISK_FRACTION,
             max_contracts: int = DEFAULT_MAX_CONTRACTS,
             daily_stop_pct: float = DEFAULT_DAILY_STOP_PCT) -> tuple[list[dict], dict]:
    """Walk source_trades (one arm's real fills, canonical trip basis -- each row is already
    one flat-to-flat FIFO trip per trades_enriched.py) in chronological order as ONE shadow
    arm. Returns (ledger_rows, daily_summary_by_date)."""
    by_date: dict[str, list[dict]] = {}
    for t in source_trades:
        by_date.setdefault(t["date"], []).append(t)
    all_dates = sorted(by_date.keys())

    equity = starting_equity
    ledger: list[dict] = []
    daily: dict[str, dict] = {}

    for date in all_dates:
        day_trades = by_date[date]
        day_start_equity = equity
        day_pnl_net = 0.0
        stopped = False
        n_executed = 0
        n_skipped_stop = 0
        n_skipped_other = 0

        for t in day_trades:
            entry_px = t.get("entry_px")
            ret_pct = t.get("ret_pct_of_premium")
            row = {
                "date": date, "symbol": t.get("symbol"), "right": t.get("right"),
                "setup": t.get("setup"), "exit_reason": t.get("exit_reason"),
                "entry_ts_et": t.get("entry_ts_et"), "exit_ts_et": t.get("exit_ts_et"),
                "source_arm": t.get("arm"), "source_qty": t.get("qty"),
                "source_pnl_dollars": t.get("pnl_dollars"),
                "entry_px": entry_px, "ret_pct_of_premium": ret_pct,
                "equity_before": round(equity, 2),
            }
            if stopped:
                row.update(status="skipped_daily_stop", qty=0, pnl_net=0.0,
                           equity_after=round(equity, 2))
                ledger.append(row)
                n_skipped_stop += 1
                continue
            if entry_px is None or ret_pct is None:
                row.update(status="skipped_missing_data", qty=0, pnl_net=0.0,
                           equity_after=round(equity, 2))
                ledger.append(row)
                n_skipped_other += 1
                continue
            qty, risk_dollars = size_position(equity, risk_fraction, entry_px, max_contracts)
            if qty < 1:
                row.update(status="skipped_insufficient_capital", qty=0,
                           risk_dollars_available=round(risk_dollars, 2), pnl_net=0.0,
                           equity_after=round(equity, 2))
                ledger.append(row)
                n_skipped_other += 1
                continue

            cost_dollars = qty * 100.0 * entry_px
            pnl_gross = cost_dollars * (ret_pct / 100.0)
            costs = compute_costs(qty, entry_px, ret_pct, rates)
            pnl_net = pnl_gross - costs["fee_total_ex_cat"] - costs["slippage_dollars"]

            equity += pnl_net
            day_pnl_net += pnl_net
            n_executed += 1

            row.update(status="executed", qty=qty, risk_fraction=risk_fraction,
                       risk_dollars_allocated=round(risk_dollars, 2),
                       cost_dollars_premium=round(cost_dollars, 2),
                       pnl_gross=round(pnl_gross, 2), fees=costs, pnl_net=round(pnl_net, 2),
                       equity_after=round(equity, 2))
            ledger.append(row)

            if day_pnl_net <= -daily_stop_pct * day_start_equity:
                stopped = True

        if n_executed > 0:
            cat = rates["cat_fee_per_arm_day"]
            equity -= cat
            day_pnl_net -= cat

        day_pct = (day_pnl_net / day_start_equity * 100.0) if day_start_equity > 0 else None
        daily[date] = {
            "date": date,
            "day_start_equity": round(day_start_equity, 2),
            "day_end_equity": round(equity, 2),
            "day_pnl_net": round(day_pnl_net, 2),
            "day_pnl_pct": round(day_pct, 3) if day_pct is not None else None,
            "n_signals": len(day_trades),
            "n_executed": n_executed,
            "n_skipped_daily_stop": n_skipped_stop,
            "n_skipped_insufficient_capital_or_data": n_skipped_other,
            "daily_stop_triggered": stopped,
            "target_2000_gap_dollars": round(DAILY_TARGET_DOLLARS - day_pnl_net, 2),
            "equity_needed_for_2000_at_this_days_pct":
                (round(DAILY_TARGET_DOLLARS / (day_pct / 100.0), 0) if day_pct and day_pct > 0 else None),
        }
        window = rolling_window_dates(date, all_dates, n=5)
        window_trades = sum(daily[d]["n_executed"] for d in window)
        daily[date]["rolling_5trading_day_trade_count"] = window_trades
        daily[date]["pdt_flag_old_regime_nonbinding"] = window_trades > PDT_OLD_REGIME_MAX_5DAY

    return ledger, daily


# --------------------------------------------------------------------------- #
# Summary / reporting
# --------------------------------------------------------------------------- #

def _max_drawdown(daily_rows: list[dict]) -> dict:
    peak = None
    max_dd = 0.0
    max_dd_pct = 0.0
    trough_date = None
    peak_date = None
    for r in daily_rows:
        eq = r["day_end_equity"]
        if peak is None or eq > peak:
            peak = eq
            peak_date = r["date"]
        dd = (peak - eq) if peak is not None else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100.0) if peak else 0.0
            trough_date = r["date"]
    return {"max_dd_dollars": round(max_dd, 2), "max_dd_pct_of_peak": round(max_dd_pct, 3),
            "peak_equity": round(peak, 2) if peak is not None else None,
            "peak_date": peak_date, "trough_date": trough_date}


def _target_gap(daily_rows: list[dict]) -> dict:
    pcts = sorted(r["day_pnl_pct"] for r in daily_rows if r["day_pnl_pct"] is not None)
    if not pcts:
        return {"n_days": 0}

    def _pctile(p: float) -> float:
        idx = min(len(pcts) - 1, max(0, int(round(p * (len(pcts) - 1)))))
        return pcts[idx]

    median_pct = statistics.median(pcts)
    p90_pct = _pctile(0.90)

    def _equity_for(pct: float) -> Optional[float]:
        if pct is None or pct <= 0:
            return None
        return round(DAILY_TARGET_DOLLARS / (pct / 100.0), 0)

    n_days_hit_2000 = sum(1 for r in daily_rows if r["day_pnl_net"] >= DAILY_TARGET_DOLLARS)
    return {
        "n_days": len(daily_rows),
        "median_day_pct": round(median_pct, 3),
        "p90_day_pct": round(p90_pct, 3),
        "median_day_dollars": round(statistics.median(r["day_pnl_net"] for r in daily_rows), 2),
        "n_days_day_pnl_gte_2000": n_days_hit_2000,
        "equity_needed_for_2000_as_median_day": _equity_for(median_pct),
        "equity_needed_for_2000_as_p90_day": _equity_for(p90_pct),
        "note": ("None means that percentile day is <=0% -- scaling a flat/losing day up "
                 "never produces a $2,000 gain at ANY equity size."),
    }


def build_summary(ledger: list[dict], daily: dict, config: dict, rates_meta: dict,
                   base_arm: str) -> dict:
    all_dates = sorted(daily.keys())
    all_rows = [daily[d] for d in all_dates]
    aug_rows = [daily[d] for d in all_dates if d >= AUGUST_START]
    pre_aug_rows = [daily[d] for d in all_dates if d < AUGUST_START]

    executed = [r for r in ledger if r["status"] == "executed"]
    day_trade_pnls: dict[str, list[float]] = {}
    day_pnls: dict[str, float] = {}
    for d in all_dates:
        day_trade_pnls[d] = [r["pnl_net"] for r in executed if r["date"] == d]
        day_pnls[d] = daily[d]["day_pnl_net"]

    guards = {
        "bootstrap": sg.day_level_bootstrap(day_trade_pnls),
        "ex_best_day": sg.ex_best_day(day_pnls),
        "signal_cluster": sg.signal_cluster_n(executed, symbol_key="symbol"),
    }

    n_signals_total = len(ledger)
    n_skipped_stop = sum(1 for r in ledger if r["status"] == "skipped_daily_stop")
    n_skipped_capital = sum(1 for r in ledger if r["status"] == "skipped_insufficient_capital")
    n_skipped_data = sum(1 for r in ledger if r["status"] == "skipped_missing_data")

    def _period(rows: list[dict]) -> dict:
        if not rows:
            return {"n_days": 0}
        total = round(sum(r["day_pnl_net"] for r in rows), 2)
        return {
            "n_trading_days": len(rows),
            "date_from": rows[0]["date"], "date_to": rows[-1]["date"],
            "total_pnl_net": total,
            "mean_day_pnl": round(total / len(rows), 2),
            "median_day_pnl": round(statistics.median(r["day_pnl_net"] for r in rows), 2),
            "n_positive_days": sum(1 for r in rows if r["day_pnl_net"] > 0),
            "n_zero_days": sum(1 for r in rows if r["n_executed"] == 0),
            "n_daily_stop_days": sum(1 for r in rows if r["daily_stop_triggered"]),
            "starting_equity_for_period": rows[0]["day_start_equity"],
            "ending_equity_for_period": rows[-1]["day_end_equity"],
            "max_drawdown": _max_drawdown(rows),
            "target_gap": _target_gap(rows),
        }

    return {
        "_meta": True,
        "generated_et": datetime.now(timezone.utc).astimezone().isoformat(),
        "purpose": "TASK C1 PROD-1 SHADOW -- one production-candidate arm, measured the way real money would be. See setup/scripts/prod_shadow.py module docstring for full methodology.",
        "base_arm": base_arm,
        "config": config,
        "cost_model_source": {"path": "analysis/recommendations/cost-model.json", "generated_et": rates_meta},
        "n_source_signals": n_signals_total,
        "n_executed": len(executed),
        "n_skipped_daily_stop": n_skipped_stop,
        "n_skipped_insufficient_capital": n_skipped_capital,
        "n_skipped_missing_data": n_skipped_data,
        "full_history": _period(all_rows),
        "august_2026": _period(aug_rows),
        "pre_august_2026": _period(pre_aug_rows),
        "guards": guards,
        "daily_series": all_rows,
        "honesty_disclosures": [
            "This is ONE arm's (safe-2's) real realized exit outcomes RESCALED by a smaller "
            "qty and re-costed -- not a re-simulation from bars. Exit trigger/timing/reason "
            "are IDENTICAL to what really happened (exit_manager's price triggers are "
            "qty-invariant, see module docstring); only position size and cost attribution "
            "differ from the live safe-2 account.",
            "A materially different qty could plausibly move the fill price itself at the "
            "premium buckets where this book makes its money (TASK B2 finding); "
            "max_contracts caps qty at 20 to stay inside the range B2 measured as not yet "
            "the binding liquidity constraint, but this is not independently re-verified here.",
            "Exit-side slippage ($2/contract) is a MODELING ASSUMPTION carried from "
            "cost-model.json, not a measurement -- no bid/ask-at-exit data source exists "
            "anywhere in this repo (TASK A1 finding, unresolved).",
            "daily_stop_pct is a disclosed, UNVALIDATED assumption (3x the per-trade risk "
            "fraction) -- no source in this repo pins a specific multiple for this sizing "
            "regime.",
            "PDT rolling-5-day count is informational only and does not gate any simulated "
            "trade -- Alpaca accounts are margin-only and CLAUDE.md records the $25K PDT "
            "floor as FINRA-repealed 2026-06-04.",
            "Single arm, small n (see guards.bootstrap.n_days) -- every period stat here "
            "inherits the same day-count/concentration caveats TASK A2's adversarial review "
            "raised for the real book; this shadow does not create new statistical power, "
            "it re-costs and re-sizes the power that already exists.",
        ],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def run(base_arm: str = DEFAULT_BASE_ARM, starting_equity: float = DEFAULT_STARTING_EQUITY,
        risk_fraction: float = DEFAULT_RISK_FRACTION, max_contracts: int = DEFAULT_MAX_CONTRACTS,
        daily_stop_pct: float = DEFAULT_DAILY_STOP_PCT, write: bool = True) -> dict:
    rates, rates_meta = load_cost_model_rates()
    source = load_source_trades(arm=base_arm)
    ledger, daily = simulate(source, rates, starting_equity=starting_equity,
                              risk_fraction=risk_fraction, max_contracts=max_contracts,
                              daily_stop_pct=daily_stop_pct)
    config = {
        "base_arm": base_arm, "starting_equity": starting_equity,
        "risk_fraction_per_trade": risk_fraction, "max_contracts": max_contracts,
        "daily_stop_pct": daily_stop_pct, "daily_target_dollars": DAILY_TARGET_DOLLARS,
    }
    summary = build_summary(ledger, daily, config, rates_meta, base_arm)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("w", encoding="utf-8") as fh:
            for row in ledger:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        with SUMMARY_PATH.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
    return {"ledger": ledger, "daily": daily, "summary": summary}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", default=DEFAULT_BASE_ARM)
    ap.add_argument("--starting-equity", type=float, default=DEFAULT_STARTING_EQUITY)
    ap.add_argument("--risk-fraction", type=float, default=DEFAULT_RISK_FRACTION)
    ap.add_argument("--max-contracts", type=int, default=DEFAULT_MAX_CONTRACTS)
    ap.add_argument("--daily-stop-pct", type=float, default=DEFAULT_DAILY_STOP_PCT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    result = run(base_arm=args.arm, starting_equity=args.starting_equity,
                 risk_fraction=args.risk_fraction, max_contracts=args.max_contracts,
                 daily_stop_pct=args.daily_stop_pct)
    summary = result["summary"]
    if not args.quiet:
        fh = summary["full_history"]
        ag = summary["august_2026"]
        print(f"[prod_shadow] base_arm={summary['base_arm']} risk_fraction={args.risk_fraction} "
              f"max_contracts={args.max_contracts} daily_stop_pct={args.daily_stop_pct}")
        print(f"[prod_shadow] wrote {len(result['ledger'])} ledger rows -> "
              f"{LEDGER_PATH.relative_to(REPO)}")
        print(f"[prod_shadow] FULL HISTORY {fh.get('date_from')}..{fh.get('date_to')} "
              f"({fh.get('n_trading_days')} days): net {fh.get('total_pnl_net')} "
              f"(mean/day {fh.get('mean_day_pnl')}, median/day {fh.get('median_day_pnl')})")
        print(f"[prod_shadow] AUGUST 2026 ({ag.get('n_trading_days')} days): net "
              f"{ag.get('total_pnl_net')} (mean/day {ag.get('mean_day_pnl')}, "
              f"median/day {ag.get('median_day_pnl')})")
        print(f"[prod_shadow] max drawdown full-history: {fh.get('max_drawdown')}")
        print(f"[prod_shadow] target gap (full-history): {fh.get('target_gap')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
