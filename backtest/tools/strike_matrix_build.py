"""strike_matrix_build.py -- PROPOSE-ONLY strike-offset counterfactual study.

J's ask (2026-08-18, in-chat, market closed): "are we putting our winners through a
matrix for ATM, minus one, minus two, plus one, plus two... would we have bought a
different contract today, would it have paid better? And is it a hard code of value
for the accounts to buy?" Explicit: "Don't make any changes on this though."

This script changes NO params, NO strategy file, NO engine code. It only reads real
fills + cached/fetched OPRA option bars and writes two report files (paths given by
the caller / see __main__ defaults):
  analysis/deep-research/STRIKE-MATRIX-2026-08-18.md
  analysis/recommendations/strike-matrix-2026-08-18.json

METHOD
------
Population: every CLOSED round trip (automation/state/fleet/fills_fifo.mine_real_arm_
fills, attribution=='engine' only) for arms {safe-2, bold-2, safe-3, risky-1, risky-3},
dated [START_DATE, today) -- today excluded because Alpaca's option-bars endpoint 403s
on same-day 0DTE contracts (measured 2026-08-17, see fetch_option_data.py's topup
docstring) so today's fills cannot be priced yet.

For each trade: look up SPY spot at the REAL entry_ts_et from the local 1-minute spot
cache (backtest/data/spy_sip_cache/spy_1m_{date}.json -- already-cached ET wall-clock
bars, verified against the 09:30 volume spike, no fetch needed). atm = round(spot).
Build the 5 counterfactual strikes (ITM-2, ITM-1, ATM, OTM-1, OTM-2) using the SAME
sign convention as crypto/lib/strike_selection.py (positive tier offset = ITM):
  calls: strike = atm - offset       puts: strike = atm + offset

Each counterfactual (and the REAL strike, for a matched baseline) is priced with the
SAME model: option_pricing_real.bar_containing() at the real entry_ts_et and at the
real exit_ts_et (the LAST sell leg's timestamp for multi-leg TP1+runner exits), using
each bar's vwap as the fill proxy. This reuses the SAME 5-min OPRA cache + bar-lookup
primitives the rest of the backtest engine already trusts (option_pricing_real.py) --
no new fill model invented here.

WHY A MATCHED MODELED BASELINE, NOT THE BROKER-EXACT real_pnl: real_pnl comes from
live marketable-limit fills (spread-crossing, slippage) that the 5-min-bar vwap model
does not reproduce. Comparing "real broker P&L" against "modeled P&L of a strike we
never traded" would not be apples-to-apples. So this script ALSO models the strike
ACTUALLY traded with the identical bar-vwap method and uses THAT as the "actual"
baseline for every delta -- the broker-exact real_pnl is reported alongside, separately,
for grounding/model-fidelity disclosure, never blended into the delta math.

C29 CAVEAT (this repo's own scar -- exit knobs ratified on one strike tier do not
transfer to another): this script only asks "what would this OTHER contract's premium
have been at the moment the REAL trade's exit already fired" -- it does NOT re-run
exit_manager's stop/TP1/trail logic against the counterfactual contract's OWN premium
path. A different strike has different delta/theta and could have hit a %-based stop
or TP earlier or later than the real exit timestamp. This is disclosed prominently in
the written report; treat every number here as "same clock, different contract," not
"what the validated exit rule would have produced on that contract."

Fetch budget: counterfactual contracts not already cached are fetched via
backtest/tools/fetch_option_data.fetch_contract_bars directly (free tier, ~200 req/min,
sleep_s between calls), capped at --max-fetch (default 150, sizing-pass measured ~37
actually needed as of 2026-08-18).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation" / "state" / "fleet"))
sys.path.insert(0, str(ROOT / "backtest" / "lib"))
sys.path.insert(0, str(ROOT / "backtest" / "tools"))
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

import fills_fifo  # noqa: E402
import option_pricing_real as opr  # noqa: E402
from fetch_option_data import (  # noqa: E402
    already_cached,
    cache_path,
    fetch_contract_bars,
    topup_from_fills_ledger,
    write_cache,
)
from _alpaca_creds import resolve_alpaca_creds  # noqa: E402
from et_clock import et_now, et_today_str  # noqa: E402

ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
START_DATE = "2026-07-20"
MIN_ENTRY_PREMIUM = 0.30  # automation/state/params.json#min_entry_premium

# tier-offset convention: positive = ITM, negative = OTM (matches
# crypto/lib/strike_selection.py's StrikeTier.strike_offset)
OFFSET_LABELS = ["ITM-2", "ITM-1", "ATM", "OTM-1", "OTM-2"]
OFFSET_VALUE = {"ITM-2": 2, "ITM-1": 1, "ATM": 0, "OTM-1": -1, "OTM-2": -2}

SPY_CACHE = ROOT / "backtest" / "data" / "spy_sip_cache"


def counterfactual_strike(atm: int, side: str, label: str) -> int:
    off = OFFSET_VALUE[label]
    return (atm + off) if side == "P" else (atm - off)


def classify_offset(atm: int, strike: int, side: str) -> str:
    """Inverse of counterfactual_strike -- label the REAL strike relative to atm."""
    delta = (strike - atm) if side == "P" else (atm - strike)
    for label, off in OFFSET_VALUE.items():
        if off == delta:
            return label
    return f"other({delta:+d})"


def load_spot_bars(date_str: str) -> Optional[list[dict]]:
    p = SPY_CACHE / f"spy_1m_{date_str}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("bars", [])
    except (OSError, json.JSONDecodeError):
        return None


def spot_at(bars: list[dict], when_et: dt.datetime) -> Optional[float]:
    """Last 1-min bar's open at or before when_et, gap-tolerant to 300s -- the SAME
    tolerance option_pricing_real.bar_containing() uses for option bars, so a stale
    local cache (e.g. 2026-08-07's spot fetch died ~12:01 ET that day, mtime-verified)
    is refused rather than silently priced off a spot that could be >1hr stale."""
    when_s = when_et.strftime("%Y-%m-%dT%H:%M:%S")
    chosen = None
    for b in bars:
        if b["t"] <= when_s:
            chosen = b
        else:
            break
    if chosen is None:
        return None
    gap = (when_et - dt.datetime.fromisoformat(chosen["t"])).total_seconds()
    if gap > 300:
        return None
    return float(chosen["o"])


def price_leg(df, when_et: dt.datetime) -> Optional[float]:
    bar = opr.bar_containing(df, when_et)
    return float(bar.vwap) if bar is not None else None


def gather_trades() -> tuple[list[dict], dict[str, Any]]:
    today = et_today_str()
    meta: dict[str, Any] = {"today_et": today, "start_date": START_DATE, "per_arm": {}}
    all_trades: list[dict] = []
    for arm in ARMS:
        trades = fills_fifo.mine_real_arm_fills(arm)
        in_window = [t for t in trades if START_DATE <= t["date"] < today]
        excluded_today = [t for t in trades if t["date"] >= today]
        meta["per_arm"][arm] = {
            "total_closed_round_trips": len(trades),
            "in_window": len(in_window),
            "excluded_today_403": len(excluded_today),
            "excluded_today_symbols": [t["symbol"] for t in excluded_today],
        }
        for t in in_window:
            t2 = dict(t)
            t2["arm"] = arm
            t2["strike"] = int(t2["symbol"][-8:]) // 1000
            all_trades.append(t2)
    all_trades.sort(key=lambda t: (t["date"], t["entry_ts_et"]))
    return all_trades, meta


def enrich_with_spot(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """Attach atm/counterfactual strikes. Returns (priceable, excluded_no_spot)."""
    priceable, excluded = [], []
    spot_cache: dict[str, Optional[list[dict]]] = {}
    for t in trades:
        if t["date"] not in spot_cache:
            spot_cache[t["date"]] = load_spot_bars(t["date"])
        bars = spot_cache[t["date"]]
        entry_dt = dt.datetime.fromisoformat(t["entry_ts_et"])
        spot = spot_at(bars, entry_dt) if bars else None
        if spot is None:
            excluded.append({
                "arm": t["arm"], "date": t["date"], "symbol": t["symbol"],
                "entry_ts_et": t["entry_ts_et"], "real_pnl": t["real_pnl"],
                "reason": "no local SPY 1-min spot bar at/before entry_ts_et "
                          "(known partial-day cache gap)" if bars else
                          "no local spy_1m cache file for this date",
            })
            continue
        t2 = dict(t)
        t2["spot_at_entry"] = spot
        t2["atm"] = int(round(spot))
        t2["real_offset_label"] = classify_offset(t2["atm"], t["strike"], t["side"])
        t2["counterfactual_strikes"] = {
            lbl: counterfactual_strike(t2["atm"], t["side"], lbl) for lbl in OFFSET_LABELS
        }
        priceable.append(t2)
    return priceable, excluded


def needed_symbols(trades: list[dict]) -> set[str]:
    out: set[str] = set()
    for t in trades:
        trade_date = dt.date.fromisoformat(t["date"])
        out.add(t["symbol"])  # real strike, for the matched baseline
        for lbl, k in t["counterfactual_strikes"].items():
            out.add(opr.option_symbol(trade_date, k, t["side"]))
    return out


def fetch_missing(symbols: set[str], max_fetch: int, sleep_s: float) -> dict[str, Any]:
    missing = sorted(s for s in symbols if not already_cached(s))
    report = {"needed": len(symbols), "already_cached": len(symbols) - len(missing),
              "missing": len(missing), "fetched": 0, "failed": 0,
              "capped_remaining": 0, "failure_reasons": {}, "fetched_symbols": []}
    if not missing:
        return report
    if len(missing) > max_fetch:
        report["capped_remaining"] = len(missing) - max_fetch
        missing = missing[:max_fetch]
    creds = resolve_alpaca_creds()
    for sym in missing:
        trade_date = f"20{sym[3:5]}-{sym[5:7]}-{sym[7:9]}"
        try:
            rows = fetch_contract_bars(sym, trade_date, creds.key, creds.secret)
            if rows:
                write_cache(sym, rows)
                report["fetched"] += 1
                report["fetched_symbols"].append(sym)
            else:
                report["failed"] += 1
                report["failure_reasons"]["empty_response"] = (
                    report["failure_reasons"].get("empty_response", 0) + 1)
        except Exception as e:  # noqa: BLE001 -- one bad contract must not stall the run
            report["failed"] += 1
            key = f"{type(e).__name__}:{str(e)[:60]}"
            report["failure_reasons"][key] = report["failure_reasons"].get(key, 0) + 1
        time.sleep(sleep_s)
    return report


def price_all(trades: list[dict]) -> list[dict]:
    """Attach modeled_actual (real strike, bar model) + modeled per offset to each trade."""
    priced = []
    bar_cache: dict[str, Any] = {}

    def get_bars(sym: str):
        if sym not in bar_cache:
            bar_cache[sym] = opr.load_contract_bars(sym)
        return bar_cache[sym]

    for t in trades:
        row = dict(t)
        entry_dt = dt.datetime.fromisoformat(t["entry_ts_et"])
        exit_dt = dt.datetime.fromisoformat(t["exit_ts_et"])

        df_real = get_bars(t["symbol"])
        if df_real is not None:
            ep = price_leg(df_real, entry_dt)
            xp = price_leg(df_real, exit_dt)
            if ep is not None and xp is not None:
                notional = ep * t["qty"] * 100
                row["modeled_actual_entry"] = ep
                row["modeled_actual_exit"] = xp
                row["modeled_actual_pnl"] = round((xp - ep) * t["qty"] * 100, 2)
                row["modeled_actual_notional"] = round(notional, 2)
                row["modeled_actual_pct_return"] = (
                    round(100.0 * row["modeled_actual_pnl"] / notional, 1) if notional > 0 else None)
            else:
                row["modeled_actual_pnl"] = None
        else:
            row["modeled_actual_pnl"] = None

        offsets_out = {}
        trade_date = dt.date.fromisoformat(t["date"])
        for lbl, k in t["counterfactual_strikes"].items():
            sym = opr.option_symbol(trade_date, k, t["side"])
            df = get_bars(sym)
            cell: dict[str, Any] = {"symbol": sym, "strike": k}
            if df is None:
                cell["status"] = "no_bars_cached"
            else:
                ep = price_leg(df, entry_dt)
                xp = price_leg(df, exit_dt)
                if ep is None or xp is None:
                    cell["status"] = "no_bar_at_entry_or_exit_ts"
                else:
                    notional = ep * t["qty"] * 100
                    cell["entry_price"] = ep
                    cell["exit_price"] = xp
                    cell["pnl"] = round((xp - ep) * t["qty"] * 100, 2)
                    cell["notional"] = round(notional, 2)
                    cell["pct_return"] = round(100.0 * cell["pnl"] / notional, 1) if notional > 0 else None
                    cell["floor_blocked"] = ep < MIN_ENTRY_PREMIUM
                    cell["status"] = "priced"
            offsets_out[lbl] = cell
        row["offsets"] = offsets_out
        priced.append(row)
    return priced


def aggregate(priced: list[dict], winners_only: bool) -> dict[str, Any]:
    pop = [t for t in priced if not winners_only or t["real_pnl"] > 0]
    out: dict[str, Any] = {"n_population": len(pop)}
    for lbl in OFFSET_LABELS:
        matched_actual = []
        matched_actual_notional = []
        matched_actual_pct = []
        cell_pnls = []
        cell_notional = []
        cell_pct = []
        n_floor_blocked = 0
        n_no_data = 0
        for t in pop:
            cell = t["offsets"].get(lbl, {})
            if cell.get("status") != "priced":
                n_no_data += 1
                continue
            if cell.get("floor_blocked"):
                n_floor_blocked += 1
                continue
            if t.get("modeled_actual_pnl") is None:
                n_no_data += 1
                continue
            cell_pnls.append(cell["pnl"])
            cell_notional.append(cell["notional"])
            cell_pct.append(cell["pct_return"])
            matched_actual.append(t["modeled_actual_pnl"])
            matched_actual_notional.append(t["modeled_actual_notional"])
            matched_actual_pct.append(t["modeled_actual_pct_return"])
        n = len(cell_pnls)
        total = round(sum(cell_pnls), 2) if n else None
        mean = round(total / n, 2) if n else None
        wins = sum(1 for p in cell_pnls if p > 0)
        wr = round(100.0 * wins / n, 1) if n else None
        actual_total = round(sum(matched_actual), 2) if n else None
        actual_mean = round(actual_total / n, 2) if n else None
        delta_total = round(total - actual_total, 2) if n else None
        delta_mean = round(mean - actual_mean, 2) if n else None
        mean_notional = round(sum(cell_notional) / n, 2) if n else None
        actual_mean_notional = round(sum(matched_actual_notional) / n, 2) if n else None
        notional_ratio = (round(mean_notional / actual_mean_notional, 2)
                           if n and actual_mean_notional else None)
        mean_pct_return = round(sum(cell_pct) / n, 1) if n else None
        actual_mean_pct_return = round(sum(matched_actual_pct) / n, 1) if n else None
        delta_pct_return = (round(mean_pct_return - actual_mean_pct_return, 1)
                             if n else None)
        out[lbl] = {
            "n_priced": n, "n_floor_blocked": n_floor_blocked, "n_no_data": n_no_data,
            "total_pnl": total, "mean_pnl": mean, "win_rate_pct": wr,
            "matched_actual_total_pnl": actual_total, "matched_actual_mean_pnl": actual_mean,
            "delta_total_vs_actual": delta_total, "delta_mean_vs_actual": delta_mean,
            "mean_notional": mean_notional, "matched_actual_mean_notional": actual_mean_notional,
            "notional_ratio_vs_actual": notional_ratio,
            "mean_pct_return_on_notional": mean_pct_return,
            "matched_actual_mean_pct_return": actual_mean_pct_return,
            "delta_pct_return_vs_actual": delta_pct_return,
        }
    # real (broker-exact) grounding for this population, independent of any offset matching
    real_total = round(sum(t["real_pnl"] for t in pop), 2)
    real_mean = round(real_total / len(pop), 2) if pop else None
    real_wins = sum(1 for t in pop if t["real_pnl"] > 0)
    out["real_broker_exact"] = {
        "n": len(pop), "total_pnl": real_total, "mean_pnl": real_mean,
        "win_rate_pct": round(100.0 * real_wins / len(pop), 1) if pop else None,
    }
    # model fidelity check: real vs modeled-at-real-strike
    diffs = [abs(t["real_pnl"] - t["modeled_actual_pnl"]) for t in pop
             if t.get("modeled_actual_pnl") is not None]
    out["model_fidelity_mean_abs_diff"] = round(sum(diffs) / len(diffs), 2) if diffs else None
    out["model_fidelity_n"] = len(diffs)
    return out


def concentration(priced: list[dict]) -> dict[str, Any]:
    """C4 doctrine (disclose concentration): the 5 arms share ONE signal (MAP.md -- 'all
    four bought the same contract within 15 seconds' on some days), so trade COUNT
    overstates independent evidence. Reports unique (date, real_symbol) combos vs raw n,
    and each offset's top-3-trade P&L share on the winners pool (a single/two-trade
    artifact check, same spirit as C22's day-share diagnostic elsewhere in this repo)."""
    combos = {(t["date"], t["symbol"]) for t in priced}
    per_date = {}
    for t in priced:
        per_date[t["date"]] = per_date.get(t["date"], 0) + 1
    winners = [t for t in priced if t["real_pnl"] > 0]
    top3 = {}
    for lbl in OFFSET_LABELS:
        pnls = sorted(
            (t["offsets"][lbl]["pnl"] for t in winners
             if t["offsets"][lbl].get("status") == "priced" and not t["offsets"][lbl].get("floor_blocked")),
            reverse=True,
        )
        total = sum(pnls)
        top3[lbl] = {
            "n": len(pnls), "total_pnl": round(total, 2),
            "top3_pnl": round(sum(pnls[:3]), 2),
            "top3_share_pct": round(100.0 * sum(pnls[:3]) / total, 1) if total else None,
        }
    return {
        "n_trades": len(priced),
        "n_unique_date_symbol_combos": len(combos),
        "n_unique_dates": len(per_date),
        "max_trades_one_date": max(per_date.values()) if per_date else 0,
        "note": "175 trades is NOT 175 independent bets -- collapses to ~64 unique "
                "(date, contract) signals; every arm trades the SAME shared_signal.py "
                "output, so within a cluster the strike is the only thing that differs.",
        "winners_top3_trade_share_by_offset": top3,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fetch", type=int, default=150)
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--out-json", default=str(ROOT / "analysis" / "recommendations" /
                                               "strike-matrix-2026-08-18.json"))
    ap.add_argument("--out-md", default=str(ROOT / "analysis" / "deep-research" /
                                             "STRIKE-MATRIX-2026-08-18.md"))
    args = ap.parse_args()

    print("[1/6] topup_from_fills_ledger()...")
    topup_report = topup_from_fills_ledger()
    print(f"  {topup_report}")

    print("[2/6] gathering real closed round trips...")
    trades, meta = gather_trades()
    print(f"  {len(trades)} in-window trades across {len(ARMS)} arms")

    print("[3/6] resolving SPY spot at entry (local cache)...")
    priceable, excluded_no_spot = enrich_with_spot(trades)
    print(f"  priceable={len(priceable)} excluded_no_spot={len(excluded_no_spot)}")

    print("[4/6] computing needed contracts + fetching missing (capped)...")
    need = needed_symbols(priceable)
    fetch_report = fetch_missing(need, args.max_fetch, args.sleep)
    print(f"  {fetch_report}")

    print("[5/6] pricing all trades x 5 offsets...")
    priced = price_all(priceable)

    print("[6/6] aggregating...")
    agg_all = aggregate(priced, winners_only=False)
    agg_winners = aggregate(priced, winners_only=True)
    conc = concentration(priced)

    result = {
        "generated_at_et": et_now().isoformat(),
        "propose_only": True,
        "nothing_armed": True,
        "j_ask_2026_08_18": "are we putting our winners through a matrix for ATM/-1/-2/+1/+2 "
                             "-- would a different contract have paid better, and is the "
                             "strike a hardcode? Don't make any changes on this though.",
        "caveats": [
            "C29 (this repo's own scar): every offset's exit price is read at the REAL "
            "trade's exit timestamp, using the SAME 5-min-bar-vwap model for every strike. "
            "This answers 'what would this other contract's premium have been at the moment "
            "the real exit fired' -- it does NOT re-run exit_manager's stop/TP1/trail logic "
            "against that contract's own premium path, which has different delta/theta and "
            "could have stopped out earlier or later than the real trade did.",
            "LEVERAGE ARTIFACT: raw $ P&L holds contract COUNT fixed across offsets, but "
            "ITM strikes cost far more per contract (ITM-2 averaged ~2.3-2.9x the real "
            "trade's notional; see notional_ratio_vs_actual per offset). A same-qty ITM-2 "
            "buy is a materially bigger bet than what Rule 6's per-trade risk cap would "
            "commonly allow at that premium -- raw $ deltas favoring ITM strikes are mostly "
            "a bet-size effect, not a strike-selection edge. mean_pct_return_on_notional / "
            "delta_pct_return_vs_actual is the capital-normalized, fairer comparison.",
            "min_entry_premium FLOOR (params.json, 0.30): counterfactual entries priced "
            "below $0.30 are EXCLUDED from n_priced/totals and counted in n_floor_blocked -- "
            "the live engine would have refused these, so they are not 'available' "
            "alternatives. OTM-1/OTM-2 carry the large majority of floor blocks.",
            "CONCENTRATION (C4): see the `concentration` block -- 175 trades collapse to "
            "~64 unique (date, contract) signals because all 5 arms trade one shared "
            "signal. Read n as ~64 independent bets fanned out 5 ways, not 175.",
            "MODEL FIDELITY: the bar-vwap model applied to the REAL strike (modeled_actual_"
            "pnl) differs from the broker-exact real_pnl by ~$53/trade (all) / ~$86/trade "
            "(winners) on average (mean_abs_diff) -- real fills cross the spread and can "
            "land mid-bar; treat every modeled number here as directional, not exact.",
            "vwap_reclaim_failed_break / OTM-2: strategies.py documents this ONE setup "
            "measured FAILING at OTM-2 (theta/delta). Structurally moot for this population: "
            "fleet_executor.STRATEGY_STRIKE_TIERS force-routes that setup to an ATM-class "
            "table regardless of arm, and the fleet producer is currently OFF "
            "(build_shared_signal.RUN_VWAP_RECLAIM_FB=False); core Safe's copy of the setup "
            "carries its own isolated ATM override (j_vwap_reclaim_fb_strike_offset_safe=0). "
            "No trade in this population could have been routed to the failing cell today.",
        ],
        "meta": meta,
        "topup_report": topup_report,
        "excluded_no_spot": excluded_no_spot,
        "fetch_report": fetch_report,
        "n_trades_priced_pool": len(priced),
        "concentration": conc,
        "aggregate_all_trades": agg_all,
        "aggregate_winners_only": agg_winners,
        "trades": priced,
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
