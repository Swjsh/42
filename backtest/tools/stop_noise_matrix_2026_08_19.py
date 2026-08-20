#!/usr/bin/env python
"""STOP LEVEL vs THE NOISE FLOOR -- full counterfactual matrix over every closed round trip.

THE QUESTION (J, 2026-08-19 losses lane): is the premium stop set inside the 1-minute noise
band of the contract, and is "percent of premium" even the right UNIT for a stop when the
thing that moves the option is an underlying move?

WHAT THIS IS. A counterfactual replay of all 303 closed real-fills round trips
(analysis/recommendations/trade-matrix.json) against a grid of premium stops, and against a
second grid of NOISE-NORMALISED stops where the stop level is derived per-trade from a fixed
SPY move and the contract's own Black-Scholes delta.

WHAT IS REAL AND WHAT IS MODELLED -- read this before quoting any number:
  * The price PATH is real: full-day 1-minute OPRA bars from backtest/data/opra_1m_cache,
    the same tape the trade-matrix MAE/MFE came from. Nothing is simulated about the prices.
  * Every exit that was NOT a hard entry-referenced premium stop (TP1, structure stop,
    ribbon flip, time stop, and the profit-lock TRAIL rungs that the ledger also labels
    "premium_stop") is REPLAYED AT ITS OBSERVED MINUTE AND PRICE. Only the hard stop is swapped.
  * When a candidate stop is WIDER than the one that actually fired, the trade no longer exits
    there and the continuation is real tape -- but the OTHER exit rules (structure stop, ribbon
    flip, TP1) cannot be re-derived without re-running the engine, so those rows are held to
    the 15:50 ET production time stop and FLAGGED `continuation_modeled`. That flag's share of
    every cell's effect is reported. Missing both the protective and the profit-taking exits
    biases those cells PESSIMISTIC for wide stops -- stated, not hidden.
  * Entry-bar convention: primary results are ENTRY-BAR-EXCLUSIVE (a stop cannot fire on a
    print that may have printed before the fill landed). The inclusive variant ships as a
    sensitivity rather than as an unlabelled default.

COSTS. Fees are recomputed per counterfactual execution from setup/scripts/cost_model.py's
empirical rates (OCC/ORF/TAF/SEC; CAT is per-arm-day and cannot be attributed to a trip, so it
is excluded here exactly as trade-matrix's real_pnl_net excludes it). Exit-side spread realism
(0.129 of the exit minute's traded range, measured by setup/scripts/exit_fill_realism.py) is
applied to BOTH the baseline and every counterfactual so the delta is like-for-like.

$0 -- cache-only, no network. Read-only: places no orders, writes no params, arms nothing.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from backtest.lib.option_iv_solve import solve_greeks, OptionMathError  # noqa: E402

MATRIX = REPO / "analysis" / "recommendations" / "trade-matrix.json"
OPRA_CACHE = REPO / "backtest" / "data" / "opra_1m_cache"
OUT_JSON = REPO / "analysis" / "recommendations" / "losses-stop-level-matrix-2026-08-19.json"

# --- cost rates (setup/scripts/cost_model.py, empirically read off account activity) --------
OCC_PER_CONTRACT = 0.025
ORF_PER_CONTRACT = 0.015
TAF_PER_CONTRACT = 0.00329
SEC_RATE_PER_DOLLAR = 20.60 / 1_000_000.0
# exit_fill_realism.py 2026-08-18: our sells land 0.129 of the minute's traded range ABOVE
# where a genuine bid-hit lands. Debited per share, x100 per contract.
EXIT_SLIP_FRACTION_OF_RANGE = 0.129

EOD_TIME_STOP = dt.time(15, 50)       # exit_manager's production time stop
YEAR_SECONDS = 365.25 * 24 * 60 * 60  # matches backtest/lib/pricing.time_to_expiry_years

# Configured hard premium stop by setup (automation/state/fleet/strategies.py + params.json).
# stop_mode == "structure" overrides to the -50% catastrophe cap (exit_manager.CATASTROPHE_STOP_PCT).
SETUP_HARD_STOP = {
    "BULLISH_RECLAIM_RIDE_THE_RIBBON": -0.20,
    "BEARISH_REJECTION_RIDE_THE_RIBBON": -0.20,
    "VWAP_CONTINUATION": -0.06, "vwap_continuation": -0.06,
    "VWAP_RECLAIM_FAILED_BREAK": -0.08, "vwap_reclaim_failed_break": -0.08,
    "vix_regime_dayside": -0.08,
    "bollinger_squeeze": -0.08,
}
CATASTROPHE = -0.50
# Trail percentages the exit stack can produce (exit_manager DEFAULT_TRAIL_PCT / ExitShape).
TRAIL_PCTS = (0.125, 0.15, 0.20, 0.25)

# Configured TP1 level by setup (strategies.py ExitShape.tp1_premium_pct / params.json). Used
# ONLY to bound the modelled continuation: a row whose hard stop no longer fires would, in
# production, still have met its own take-profit. Letting it ride uncapped to 15:50 credits
# the counterfactual with money the live exit stack would have banked far earlier -- which is
# how a single trend day comes to carry a whole matrix.
SETUP_TP1 = {
    "BULLISH_RECLAIM_RIDE_THE_RIBBON": 1.00,
    "BEARISH_REJECTION_RIDE_THE_RIBBON": 1.00,
    "VWAP_CONTINUATION": 0.40, "vwap_continuation": 0.40,
    "VWAP_RECLAIM_FAILED_BREAK": 0.30, "vwap_reclaim_failed_break": 0.30,
    "vix_regime_dayside": 0.30,
    "bollinger_squeeze": 0.30,
}

STOP_GRID = [-0.08, -0.12, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50, -0.65, -0.80]
SPY_MOVE_GRID = [0.0005, 0.00075, 0.0010, 0.0015, 0.0020, 0.0025, 0.0035, 0.0050]
NOISE_STOP_FLOOR = -0.95  # a stop below -95% of premium can never fire; treated as "no stop"


def _ceil_cents(x: float) -> float:
    return math.ceil(round(x, 10) * 100.0) / 100.0


def exit_fees(qty: int, price: float) -> float:
    """Regulatory fees on ONE sell execution of `qty` contracts at `price`."""
    proceeds = price * qty * 100.0
    return (_ceil_cents(OCC_PER_CONTRACT * qty) + _ceil_cents(ORF_PER_CONTRACT * qty)
            + _ceil_cents(TAF_PER_CONTRACT * qty) + _ceil_cents(SEC_RATE_PER_DOLLAR * proceeds))


def entry_fees_of(row: dict) -> float:
    fb = row.get("fee_breakdown") or {}
    return float(fb.get("occ_entry", 0.0)) + float(fb.get("orf_entry", 0.0))


# ================================================================ bars
def load_bars(symbol: str, date: str) -> Optional[list[dict]]:
    p = OPRA_CACHE / f"{symbol}_{date}.csv"
    if not p.exists():
        return None
    et = dt.timezone(dt.timedelta(hours=-4))  # OPRA store is fixed -04:00 (DST-frame doctrine)
    out: list[dict] = []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                ts = dt.datetime.fromisoformat(str(r["t"]).replace("Z", "+00:00"))
            except (ValueError, KeyError, TypeError):
                continue
            ts = ts.astimezone(et).replace(tzinfo=None)
            try:
                out.append({"ts": ts, "o": float(r["o"]), "h": float(r["h"]),
                            "l": float(r["l"]), "c": float(r["c"])})
            except (TypeError, ValueError, KeyError):
                continue
    out.sort(key=lambda b: b["ts"])
    return out or None


# ================================================================ leg classification
def classify_legs(row: dict, bars: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Split the observed exit legs into (preserved, hard_stop, notes).

    A leg labelled `premium_stop` is a HARD entry-referenced stop only if its stated level is
    at or below the configured hard stop for that row. Anything tighter is a PROFIT-LOCK /
    TRAIL rung (exit_manager writes those with the same `premium_stop` label) and is preserved:
    treating a profit-lock exit as a hard stop would delete the winners from every wide-stop
    cell, which is precisely the artifact this lane is supposed to catch. Trail identity is
    corroborated against the contract's own running high-water mark, and any leg matching
    neither shape is reported as unclassified rather than silently bucketed.
    """
    E = row["entry_premium"]
    hard_pct = (CATASTROPHE if row.get("stop_mode") == "structure"
                else SETUP_HARD_STOP.get(row.get("setup"), -0.20))
    hard_level = E * (1.0 + hard_pct)
    entry_min = dt.datetime.fromisoformat(row["entry_ts_et"]).replace(second=0, microsecond=0)

    preserved: list[dict] = []
    hard: list[dict] = []
    notes: list[str] = []
    for leg in (row.get("exit_legs") or []):
        ts = dt.datetime.fromisoformat(leg["ts_et"]).replace(second=0, microsecond=0)
        item = {"ts": ts, "qty": int(leg["qty"]), "price": float(leg["price"]),
                "stage": leg.get("stage"), "reason": leg.get("reason")}
        if leg.get("stage") != "premium_stop":
            preserved.append(item)
            continue
        reason = leg.get("reason") or ""
        lvl = None
        if "premium_stop @ " in reason:
            try:
                lvl = float(reason.split("premium_stop @ ")[1].split()[0])
            except (ValueError, IndexError):
                lvl = None
        if lvl is None:
            notes.append("premium_stop leg with no parseable level -> preserved")
            preserved.append(item)
            continue
        if lvl <= hard_level + 0.011:          # 1 cent of rounding slack
            item["hard_level"] = lvl
            hard.append(item)
            continue
        hwm = max([b["h"] for b in bars if entry_min <= b["ts"] <= ts] or [E])
        matched = any(abs(lvl - hwm * (1.0 - t)) <= 0.03 for t in TRAIL_PCTS)
        item["trail_level"] = lvl
        item["trail_hwm_corroborated"] = matched
        preserved.append(item)
        if not matched:
            notes.append("premium_stop leg @ %.2f tighter than hard %.2f, no trail match vs "
                         "HWM %.2f -> preserved as non-hard" % (lvl, hard_level, hwm))
    preserved.sort(key=lambda x: x["ts"])
    hard.sort(key=lambda x: x["ts"])
    return preserved, hard, notes


# ================================================================ simulator
def simulate(row: dict, bars: list[dict], preserved: list[dict], hard: list[dict],
             stop_pct: Optional[float], *, include_entry_bar: bool = False,
             keep_hard_as_observed: bool = False, apply_tp1_cap: bool = False) -> dict:
    """Replay one round trip with the hard premium stop replaced by `stop_pct`.

    keep_hard_as_observed=True reproduces the trade EXACTLY as it happened (the baseline
    self-check). stop_pct=None means no hard stop at all. apply_tp1_cap=True exits the
    remainder at the setup's configured TP1 level once the removed hard stop's original
    minute has passed -- the conservative bound on the modelled continuation.
    """
    E = row["entry_premium"]
    Q = int(row["qty"])
    entry_ts = dt.datetime.fromisoformat(row["entry_ts_et"])
    entry_min = entry_ts.replace(second=0, microsecond=0)
    eod = dt.datetime.combine(entry_ts.date(), EOD_TIME_STOP)
    obs = preserved + hard
    last_actual = max([l["ts"] for l in obs] or [entry_min])
    limit = last_actual if keep_hard_as_observed else max(eod, last_actual)

    sched = sorted(obs, key=lambda x: x["ts"]) if keep_hard_as_observed else list(preserved)
    stop_level = None if (stop_pct is None or keep_hard_as_observed) else E * (1.0 + stop_pct)

    bar_at = {b["ts"]: b for b in bars if entry_min <= b["ts"] <= limit}
    minutes = sorted(set(bar_at) | {l["ts"] for l in sched if l["ts"] <= limit})

    tp1_level = None
    tp1_from = None
    if apply_tp1_cap and hard and not keep_hard_as_observed:
        tp1_pct = SETUP_TP1.get(row.get("setup"))
        if tp1_pct is not None:
            tp1_level = E * (1.0 + tp1_pct)
            tp1_from = hard[0]["ts"]

    remaining = Q
    fills: list[dict] = []
    pending = list(sched)
    collisions = 0

    for t in minutes:
        # 1. observed non-stop exits at this minute fire first (they actually happened; the
        #    within-minute ordering against a stop touch is unresolvable at 1m resolution)
        for leg in [l for l in pending if l["ts"] == t]:
            pending.remove(leg)
            if remaining <= 0:
                continue
            q = min(leg["qty"], remaining)
            fills.append({"ts": t, "qty": q, "price": leg["price"],
                          "kind": leg.get("stage") or "observed"})
            remaining -= q
        if remaining <= 0:
            break
        b = bar_at.get(t)
        if b is None:
            continue
        if t == entry_min and not include_entry_bar:
            continue
        # TP1 bound on the modelled continuation (checked before the stop: a high-side touch
        # in the same minute is unresolvable at 1m, and crediting the stop there would make
        # this bound LESS conservative, not more)
        if tp1_level is not None and t >= tp1_from and b["h"] >= tp1_level:
            fills.append({"ts": t, "qty": remaining, "price": tp1_level, "kind": "cf_tp1"})
            remaining = 0
            break
        if stop_level is None:
            continue
        if b["l"] <= stop_level:
            if any(l["ts"] == t for l in sched):
                collisions += 1
            px = min(stop_level, b["o"])        # gap-through: never better than the open
            fills.append({"ts": t, "qty": remaining, "price": px, "kind": "cf_stop"})
            remaining = 0
            break

    terminal_modeled = False
    if remaining > 0:
        tail = [b for b in bars if entry_min <= b["ts"] <= limit]
        if not tail:
            return {"status": "NO_BARS", "fills": fills, "unfilled": remaining}
        fills.append({"ts": tail[-1]["ts"], "qty": remaining, "price": tail[-1]["c"],
                      "kind": "cf_eod"})
        terminal_modeled = True
        remaining = 0

    gross = sum((f["price"] - E) * f["qty"] * 100.0 for f in fills)
    fees = entry_fees_of(row) + sum(exit_fees(f["qty"], f["price"]) for f in fills)
    slip = 0.0
    for f in fills:
        b = bar_at.get(f["ts"])
        if b is None:
            continue
        slip += EXIT_SLIP_FRACTION_OF_RANGE * (b["h"] - b["l"]) * 100.0 * f["qty"]
    return {
        "status": "OK",
        "arm": row["arm"], "date": row["date"], "symbol": row["symbol"],
        "fills": fills,
        "gross": gross,
        "net": gross - fees,
        "net_slip": gross - fees - slip,
        "fees": fees,
        "slip": slip,
        "stopped": any(f["kind"] == "cf_stop" for f in fills),
        "terminal_modeled": terminal_modeled,
        "collisions": collisions,
        "hold_minutes": round((fills[-1]["ts"] - entry_min).total_seconds() / 60.0, 1),
    }


# ================================================================ aggregation
def aggregate(per_trade: list[dict], baseline: list[dict], label: str,
              extra: Optional[dict] = None) -> dict:
    n = len(per_trade)
    gross = sum(t["gross"] for t in per_trade)
    net = sum(t["net"] for t in per_trade)
    net_slip = sum(t["net_slip"] for t in per_trade)
    wins = [t for t in per_trade if t["net"] > 0]
    losses = [t for t in per_trade if t["net"] < 0]

    by_day: dict = defaultdict(float)
    delta_by_day: dict = defaultdict(float)
    deltas = []
    became_loser = 0
    winner_dollars_lost = 0.0
    loser_dollars_saved = 0.0
    for cf, bl in zip(per_trade, baseline):
        by_day[cf["date"]] += cf["net"]
        dd = cf["net"] - bl["net"]
        delta_by_day[cf["date"]] += dd
        deltas.append((abs(dd), dd, cf["date"], cf["arm"], cf["symbol"]))
        if bl["net"] > 0 and cf["net"] <= 0:
            became_loser += 1
        if bl["net"] > 0:
            winner_dollars_lost += min(0.0, dd)
        else:
            loser_dollars_saved += max(0.0, dd)

    peak = cum = 0.0
    mdd = 0.0
    for day in sorted(by_day):
        cum += by_day[day]
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)

    total_delta = net - sum(b["net"] for b in baseline)
    top_day_share = top_trade_share = None
    top_day_name = top_trade_name = None
    ranked_days = sorted(delta_by_day.items(), key=lambda kv: -abs(kv[1]))
    if abs(total_delta) > 1e-9 and delta_by_day:
        top_day_share = round(ranked_days[0][1] / total_delta, 4)
        top_day_name = ranked_days[0][0]
        deltas.sort(reverse=True)
        top_trade_share = round(deltas[0][1] / total_delta, 4)
        top_trade_name = "%s %s %s" % (deltas[0][2], deltas[0][3], deltas[0][4])
    # ROBUSTNESS: an effect one day can erase is not an effect. Days are dropped by |delta|,
    # and 2026-08-04 is named explicitly because it is the book's one +1.4% SPY trend day.
    drop1 = total_delta - (ranked_days[0][1] if ranked_days else 0.0)
    drop3 = total_delta - sum(v for _, v in ranked_days[:3])
    drop_0804 = total_delta - delta_by_day.get("2026-08-04", 0.0)
    n_days_moved = sum(1 for v in delta_by_day.values() if abs(v) > 0.005)
    # DAY-LEVEL SIGN TEST -- the one robustness statistic a single trend day cannot buy.
    days_up = sum(1 for v in delta_by_day.values() if v > 0.005)
    days_dn = sum(1 for v in delta_by_day.values() if v < -0.005)
    changed_days = [v for v in delta_by_day.values() if abs(v) > 0.005]
    median_changed_day = round(statistics.median(changed_days), 2) if changed_days else None
    n_clusters = len({(cf["date"], cf["symbol"]) for cf, bl in zip(per_trade, baseline)
                      if abs(cf["net"] - bl["net"]) > 0.005})
    n_trades_moved = sum(1 for cf, bl in zip(per_trade, baseline)
                         if abs(cf["net"] - bl["net"]) > 0.005)

    out = {
        "cell": label,
        "n": n,
        "net_pnl_gross": round(gross, 2),
        "net_pnl_after_fees": round(net, 2),
        "net_pnl_after_fees_and_exit_slippage": round(net_slip, 2),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "n_wins": len(wins),
        "avg_loss": round(statistics.mean([t["net"] for t in losses]), 2) if losses else None,
        "worst_loss": round(min([t["net"] for t in losses]), 2) if losses else None,
        "avg_win": round(statistics.mean([t["net"] for t in wins]), 2) if wins else None,
        "best_win": round(max([t["net"] for t in wins]), 2) if wins else None,
        "max_drawdown_book": round(mdd, 2),
        "n_stopped_by_candidate": sum(1 for t in per_trade if t["stopped"]),
        "n_terminal_modeled": sum(1 for t in per_trade if t["terminal_modeled"]),
        "n_minute_collisions": sum(t["collisions"] for t in per_trade),
        "delta_vs_production_gross": round(gross - sum(b["gross"] for b in baseline), 2),
        "delta_vs_production_net": round(total_delta, 2),
        "delta_vs_production_net_slip": round(net_slip - sum(b["net_slip"] for b in baseline), 2),
        "concentration_top_day_share_of_delta": top_day_share,
        "concentration_top_day": top_day_name,
        "concentration_top_trade_share_of_delta": top_trade_share,
        "concentration_top_trade": top_trade_name,
        "delta_drop_top_day": round(drop1, 2),
        "delta_drop_top_3_days": round(drop3, 2),
        "delta_excluding_2026_08_04": round(drop_0804, 2),
        "n_days_with_any_change": n_days_moved,
        "days_improved": days_up,
        "days_worsened": days_dn,
        "median_changed_day_delta": median_changed_day,
        "n_date_symbol_clusters_changed": n_clusters,
        "n_trades_changed": n_trades_moved,
        "winners_turned_into_losers": became_loser,
        "dollars_lost_on_baseline_winners": round(winner_dollars_lost, 2),
        "dollars_saved_on_baseline_losers": round(loser_dollars_saved, 2),
    }
    if extra:
        out.update(extra)
    return out


# ================================================================ greeks + noise floor
def delta_of(row: dict) -> Optional[float]:
    ts = dt.datetime.fromisoformat(row["entry_ts_et"])
    exp = ts.replace(hour=16, minute=0, second=0, microsecond=0)
    t_years = max(60.0, (exp - ts).total_seconds()) / YEAR_SECONDS
    try:
        g = solve_greeks(row["entry_premium"], row["spy_at_entry"], row["strike"],
                         t_years, row["side"])
    except OptionMathError:
        return None
    return abs(g.delta)


def noise_stop_for(row: dict, delta: float, spy_move_frac: float) -> float:
    """Premium-% stop equivalent to a `spy_move_frac` adverse move in SPY, via BS delta."""
    dollar = delta * spy_move_frac * row["spy_at_entry"]
    return -(dollar / row["entry_premium"])


# ================================================================ noise-floor diagnostics
def noise_floor_panel(prepped: list[dict]) -> dict:
    """No counterfactual, no management model -- just what the tape says about 1-minute noise.

    `band_pct` = the median 1-minute traded range over the held window, expressed as a
    fraction of the entry premium. A stop tighter than this is inside a single minute's
    ordinary print-to-print noise on that contract.
    """
    bands: list[float] = []
    band_by_money: dict = defaultdict(list)
    spy_equiv: list[float] = []
    recovered = {"n_hard_stopped": 0, "back_to_entry_before_1550": 0,
                 "back_to_plus30pct_before_1550": 0, "median_post_stop_peak_pct": None}
    peaks: list[float] = []
    for p in prepped:
        row, bars = p["row"], p["bars"]
        entry_min = dt.datetime.fromisoformat(row["entry_ts_et"]).replace(second=0, microsecond=0)
        exit_min = dt.datetime.fromisoformat(row["exit_ts_et"]).replace(second=0, microsecond=0)
        held = [b for b in bars if entry_min <= b["ts"] <= exit_min]
        if held:
            rng = statistics.median([b["h"] - b["l"] for b in held])
            band = rng / row["entry_premium"]
            bands.append(band)
            band_by_money[row["moneyness"]].append(band)
            if p["delta"]:
                spy_equiv.append(rng / (p["delta"] * row["spy_at_entry"]))
        if p["hard"]:
            recovered["n_hard_stopped"] += 1
            stop_min = p["hard"][0]["ts"]
            eod = dt.datetime.combine(entry_min.date(), EOD_TIME_STOP)
            after = [b for b in bars if stop_min < b["ts"] <= eod]
            if after:
                peak = max(b["h"] for b in after)
                peaks.append(peak / row["entry_premium"] - 1.0)
                if peak >= row["entry_premium"]:
                    recovered["back_to_entry_before_1550"] += 1
                if peak >= row["entry_premium"] * 1.30:
                    recovered["back_to_plus30pct_before_1550"] += 1
    if peaks:
        recovered["median_post_stop_peak_pct"] = round(statistics.median(peaks), 4)
    bands.sort()
    spy_equiv.sort()

    def q(seq: list, f: float):
        return round(seq[int(f * (len(seq) - 1))], 5) if seq else None

    return {
        "_doc": "Median 1-minute traded range of the contract, as a fraction of entry premium. "
                "A premium stop tighter than this sits INSIDE one minute of ordinary noise.",
        "n": len(bands),
        "median_1min_range_pct_of_premium": q(bands, 0.5),
        "deciles_1min_range_pct_of_premium": {str(f): q(bands, f)
                                              for f in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "by_moneyness": {m: {"n": len(v),
                             "median_1min_range_pct_of_premium": round(statistics.median(v), 4)}
                         for m, v in sorted(band_by_money.items())},
        "one_minute_noise_expressed_as_spy_move_pct": {
            "_doc": "median 1-min option range / (delta * SPY) = the SPY move that one minute "
                    "of this contract own noise is worth",
            "median": q(spy_equiv, 0.5),
            "deciles": {str(f): q(spy_equiv, f) for f in (0.1, 0.25, 0.5, 0.75, 0.9)},
        },
        "hard_stopped_recovery": recovered,
    }


def unit_dispersion_panel(prepped: list[dict]) -> dict:
    """How much does one premium-% number MEAN across this book, in SPY terms?

    If a -20% premium stop corresponds to wildly different SPY moves trade by trade, then
    percent-of-premium is the wrong UNIT: the same nominal stop is a hair trigger on one
    contract and a catastrophe cap on another.
    """
    out = {}
    for pct in (-0.08, -0.20, -0.50):
        moves = []
        for p in prepped:
            if not p["delta"]:
                continue
            row = p["row"]
            moves.append(abs(pct) * row["entry_premium"] / (p["delta"] * row["spy_at_entry"]))
        moves.sort()
        lo = moves[int(0.10 * (len(moves) - 1))]
        md = moves[int(0.50 * (len(moves) - 1))]
        hi = moves[int(0.90 * (len(moves) - 1))]
        out["%d%%" % round(pct * 100)] = {
            "n": len(moves),
            "spy_move_pct_p10": round(lo * 100, 4),
            "spy_move_pct_median": round(md * 100, 4),
            "spy_move_pct_p90": round(hi * 100, 4),
            "p90_over_p10_ratio": round(hi / max(lo, 1e-9), 2),
        }
    return out


# ================================================================ driver
def main() -> int:
    data = json.load(MATRIX.open(encoding="utf-8"))
    rows = data["rows"]

    prepped: list[dict] = []
    skipped: list[dict] = []
    all_notes: list[str] = []
    for row in rows:
        bars = load_bars(row["symbol"], row["date"])
        if not bars:
            skipped.append({"arm": row["arm"], "date": row["date"], "symbol": row["symbol"],
                            "why": "no cached OPRA bars"})
            continue
        preserved, hard, notes = classify_legs(row, bars)
        all_notes.extend(notes)
        prepped.append({"row": row, "bars": bars, "preserved": preserved, "hard": hard,
                        "delta": delta_of(row)})

    # ---- baseline self-check: replay every leg exactly as observed -------------------------
    baseline = [simulate(p["row"], p["bars"], p["preserved"], p["hard"], None,
                         keep_hard_as_observed=True) for p in prepped]
    bad = [(p["row"]["arm"], p["row"]["date"], p["row"]["symbol"],
            round(b.get("gross", float("nan")), 2), p["row"]["real_pnl_gross"])
           for p, b in zip(prepped, baseline)
           if b["status"] != "OK" or abs(b["gross"] - p["row"]["real_pnl_gross"]) > 0.51]
    if bad:
        print("[FATAL] baseline replay does not reproduce the ledger on %d rows" % len(bad),
              file=sys.stderr)
        for x in bad[:10]:
            print("   ", x, file=sys.stderr)
        return 2

    base_agg = aggregate(baseline, baseline, "PRODUCTION (as traded)")

    # ---- Panel A: EXACT -- no continuation is ever modelled anywhere -----------------------
    # Where the candidate stop is touched, the outcome is exact tape. Where it is never
    # touched (because it is wider than the stop that actually fired), the row KEEPS its
    # observed outcome rather than being credited a modelled hold. So this panel measures
    # tightening honestly and is silent -- not optimistic -- about loosening.
    panel_a = []
    for s in STOP_GRID:
        cells = []
        modeled = 0
        for p, b in zip(prepped, baseline):
            cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"], s)
            if cf["status"] != "OK":
                cf = b
            elif cf["terminal_modeled"]:
                modeled += 1
                cf = b
            cells.append(cf)
        panel_a.append(aggregate(cells, baseline,
                                 "premium stop %d%% (exact, no continuation model)" % round(s * 100),
                                 {"rows_left_at_actual_untouched_by_candidate": modeled}))

    # ---- Panel B: FULL matrix, continuation held to the 15:50 time stop --------------------
    panel_b = []
    for s in STOP_GRID:
        cells = []
        for p, b in zip(prepped, baseline):
            cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"], s)
            cells.append(cf if cf["status"] == "OK" else b)
        panel_b.append(aggregate(cells, baseline,
                                 "premium stop %d%% (full)" % round(s * 100)))
    cells = []
    for p, b in zip(prepped, baseline):
        cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"], None)
        cells.append(cf if cf["status"] == "OK" else b)
    panel_b.append(aggregate(cells, baseline, "NO hard premium stop (full)"))

    # ---- Panel B2: same, but the modelled continuation is capped at production TP1 ---------
    panel_b2 = []
    for s in STOP_GRID:
        cells = []
        for p, b in zip(prepped, baseline):
            cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"], s,
                          apply_tp1_cap=True)
            cells.append(cf if cf["status"] == "OK" else b)
        panel_b2.append(aggregate(cells, baseline,
                                  "premium stop %d%% (TP1-capped)" % round(s * 100)))

    # ---- Panel C: noise-normalised stops (fixed SPY move via BS delta) ---------------------
    def _panel_c(tp1_cap: bool) -> list[dict]:
        out = []
        for m in SPY_MOVE_GRID:
            cells = []
            no_delta = capped = 0
            implied: list[float] = []
            for p, b in zip(prepped, baseline):
                if not p["delta"]:
                    no_delta += 1
                    cells.append(b)
                    continue
                s = noise_stop_for(p["row"], p["delta"], m)
                implied.append(s)
                cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"],
                              None if s < NOISE_STOP_FLOOR else s, apply_tp1_cap=tp1_cap)
                if s < NOISE_STOP_FLOOR:
                    capped += 1
                cells.append(cf if cf["status"] == "OK" else b)
            implied.sort()
            out.append(aggregate(
                cells, baseline,
                "SPY move %.3f%%%s" % (m * 100, " (TP1-capped)" if tp1_cap else ""),
                {"rows_without_delta_left_at_actual": no_delta,
                 "rows_where_implied_stop_unreachable": capped,
                 "implied_premium_stop_pct_p10":
                     round(implied[int(0.1 * (len(implied) - 1))], 4),
                 "implied_premium_stop_pct_median":
                     round(implied[int(0.5 * (len(implied) - 1))], 4),
                 "implied_premium_stop_pct_p90":
                     round(implied[int(0.9 * (len(implied) - 1))], 4)}))
        return out

    panel_c = _panel_c(False)
    panel_c2 = _panel_c(True)

    # ---- sensitivity: entry-bar-INCLUSIVE -------------------------------------------------
    sens = []
    for s in (-0.20, -0.50):
        cells = []
        for p, b in zip(prepped, baseline):
            cf = simulate(p["row"], p["bars"], p["preserved"], p["hard"], s,
                          include_entry_bar=True)
            cells.append(cf if cf["status"] == "OK" else b)
        sens.append(aggregate(cells, baseline,
                              "premium stop %d%% (full, ENTRY BAR INCLUSIVE)" % round(s * 100)))

    hard_legs = sum(len(p["hard"]) for p in prepped)
    trail_legs = sum(1 for p in prepped for l in p["preserved"] if "trail_level" in l)
    trail_ok = sum(1 for p in prepped for l in p["preserved"]
                   if l.get("trail_hwm_corroborated") is True)

    report = {
        "_doc": (__doc__ or "").strip(),
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "source_matrix": "analysis/recommendations/trade-matrix.json",
        "source_matrix_generated_at_et": data.get("generated_at_et"),
        "independence_warning": data.get("_independence_warning"),
        "rows_in_matrix": len(rows),
        "rows_simulated": len(prepped),
        "rows_skipped": skipped,
        "leg_classification": {
            "hard_premium_stop_legs": hard_legs,
            "profit_lock_trail_legs_preserved": trail_legs,
            "trail_legs_corroborated_by_hwm": trail_ok,
            "unclassified_notes": all_notes[:20],
            "unclassified_note_count": len(all_notes),
        },
        "production_baseline": base_agg,
        "noise_floor": noise_floor_panel(prepped),
        "unit_dispersion": unit_dispersion_panel(prepped),
        "panel_a_exact_no_continuation_model": panel_a,
        "panel_b_full_matrix_modelled_continuation": panel_b,
        "panel_b2_full_matrix_tp1_capped_continuation": panel_b2,
        "panel_c_noise_normalised_spy_move": panel_c,
        "panel_c2_noise_normalised_tp1_capped": panel_c2,
        "sensitivity_entry_bar_inclusive": sens,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=1), encoding="utf-8")
    ledger_net = sum(p["row"]["real_pnl_net"] for p in prepped)
    print("wrote", OUT_JSON)
    print("baseline net after fees: $%.2f   ledger real_pnl_net: $%.2f"
          % (base_agg["net_pnl_after_fees"], ledger_net))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
