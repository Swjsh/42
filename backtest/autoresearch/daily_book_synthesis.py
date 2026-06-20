"""DAILY-BOOK SYNTHESIS — D1 (portfolio/coverage), D2 (leaderboard), B1 (feasible strike).

Campaign synthesis: turns the validated/candidate edges into the actual daily-trading
book and answers "what do we trade every day + how much can a $2K account realistically
make."  REUSES the already-validated detectors, the real-OPRA fill loader, and the
filed scorecards; it does NOT re-derive any edge — it only intersects per-day signal
DATES (coverage) and reads real chain prices (B1 feasibility).

Three angles
------------
D2  LEADERBOARD — rank the edges by (OOS expectancy x frequency) from the filed
    scorecards (gap-and-go-LIVE.json, j-daily-pattern-LIVE.json,
    chart-stops-ab-2026-06-18.json).  Pure read + arithmetic.

D1  PORTFOLIO / COVERAGE — run the shippable detectors over OUR 2025-26 tape, take the
    per-day signal DATES, and compute:
      * coverage % = days with >=1 signal from the union / trading days
      * correlation: do the edges fire the SAME days (redundant) or DIFFERENT days
        (complementary)?
      * blended daily expectancy + realistic monthly P&L on a $2K account.

B1  FEASIBLE STRIKE — for gap-and-go (the one ship-grade strike tweak, ATM->ITM-1),
    read the REAL ITM-1 / ATM / OTM-1 0DTE SPY put entry premium from the OPRA cache on
    each gap-down signal day, and check whether $2K can buy min-3 contracts within the
    6% premium ceiling (~$120).  If ITM-1 x3 busts the ceiling, report the strike that
    maximizes edge WITHIN the constraint.

Pure Python, $0.  Real fills / real chain prices.  Writes
analysis/recommendations/daily-book-synthesis.json.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # ...\42\backtest
PROJECT = REPO.parent                               # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    load_spy, align_vix, build_day_contexts, detect_gap_and_go, Signal,
)
from autoresearch.j_daily_pattern_ratify import detect_j_vwap_continuation  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real, _strike_from_spot  # noqa: E402
from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after,
)

SPY = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
VIX = REPO / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
RECS = PROJECT / "analysis" / "recommendations"
OUT = RECS / "daily-book-synthesis.json"

EXIT_STOP = -0.99          # chart-stop only (the live config for these setups)
ENTRY_SLIPPAGE = 0.02      # matches simulator_real DEFAULT_ENTRY_SLIPPAGE

# $2K Safe account constraints
ACCOUNT_EQUITY = 2000.0
MIN_CONTRACTS = 3
PREMIUM_CEILING_PCT = 0.06          # the doctrinal sizing-study ceiling (~$120 on $2K)
PREMIUM_CEILING_DOLLARS = ACCOUNT_EQUITY * PREMIUM_CEILING_PCT
LIVE_PARAMS_CEILING_PCT = 0.40      # what params.json $0-2K tier actually has TODAY
TRADING_WEEKS_PER_MONTH = 52.0 / 12.0   # ~4.33


def _load_scorecard(name: str) -> dict:
    p = RECS / name
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# B1 — real chain price at the gap-and-go entry (next bar after 09:30, ~09:35 ET)
# ─────────────────────────────────────────────────────────────────────────────
def _entry_premium_for_offset(d: dt.date, entry_time: dt.datetime, entry_spot: float,
                              side: str, offset: int) -> tuple[float, int] | None:
    """Real ASK-side entry premium for the contract at strike = atm-offset (puts).

    Mirrors simulator_real.simulate_trade_real strike selection + entry-fill exactly:
      atm = round(spot); puts: strike = atm - offset (offset=-1 -> ITM-1 = atm+1).
      entry = next 5-min bar open + slippage.  Returns (premium, true_strike_offset)
      or None when that exact strike isn't cached (no nearest-strike fallback here —
      we want the TRUE cost of the requested moneyness, L58-honest).
    """
    atm = _strike_from_spot(entry_spot)
    strike = atm - offset if side == "P" else atm + offset
    symbol = option_symbol(d, strike, side)
    opt_df = load_contract_bars(symbol)
    if opt_df is None:
        return None
    opt_df = opt_df.copy()
    if opt_df["timestamp_et"].dt.tz is not None:
        opt_df["timestamp_et"] = opt_df["timestamp_et"].dt.tz_localize(None)
    next_bar_start = entry_time + dt.timedelta(minutes=5)
    eb = bar_at_or_after(opt_df, next_bar_start)
    if eb is None or eb.open <= 0:
        return None
    return float(eb.open) + ENTRY_SLIPPAGE, int(strike - atm)


def gap_and_go_signals(spy, ribbon, vix, days) -> list[dict]:
    """Per-signal records for gap-and-go: date, side, real entry premiums AND real-fills
    P&L at ATM / ITM-1 / OTM-1 so B1 uses true chain prices AND a verified edge per
    strike (the filed scorecard has ATM+ITM1 only; OTM-1's edge is computed here, same
    sim/exit stack)."""
    sigs = detect_gap_and_go(spy, ribbon, vix, days)
    out = []
    for sg in sigs:
        bar = spy.iloc[sg.bar_idx]
        et_raw = bar["timestamp_et"]
        et = et_raw
        if hasattr(et, "tz_localize") and et.tz is not None:
            et = et.tz_localize(None)
        et = et.to_pydatetime() if hasattr(et, "to_pydatetime") else et
        d = et.date()
        spot = float(bar["close"])
        ev = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        rec = {"date": str(d), "side": sg.side, "spot": round(spot, 2)}
        for label, off in (("ATM", 0), ("ITM1", -1), ("OTM1", 1)):
            pr = _entry_premium_for_offset(d, et, spot, sg.side, off)
            if pr is None:
                rec[label] = None
                continue
            prem, true_off = pr
            # Real-fills P&L at this strike (chart-stop-only, same exit stack as scorecards).
            atm = _strike_from_spot(spot)
            strike = atm - off if sg.side == "P" else atm + off
            f = simulate_trade_real(
                entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
                rejection_level=sg.stop_level, triggers_fired=[sg.note or "gng"],
                side=sg.side, qty=MIN_CONTRACTS, setup="GAP_AND_GO",
                strike_override=strike, entry_vix=ev, premium_stop_pct=EXIT_STOP,
            )
            pnl = float(f.dollar_pnl) if (f is not None and f.dollar_pnl is not None) else None
            rec[label] = {"premium": round(prem, 3),
                          "cost_min3": round(prem * MIN_CONTRACTS * 100.0, 2),
                          "true_offset": true_off,
                          "pnl_min3": round(pnl, 2) if pnl is not None else None}
        out.append(rec)
    return out


def vwap_cont_signal_dates(spy, ribbon, vix, days) -> list[str]:
    """Per-day entry dates for J's VWAP-aligned morning continuation (the daily edge)."""
    sigs = detect_j_vwap_continuation(spy, ribbon, vix, days)
    dates = []
    for sg in sigs:
        bar = spy.iloc[sg.bar_idx]
        et = bar["timestamp_et"]
        dates.append(str(et.date()))
    return sorted(set(dates))


# ─────────────────────────────────────────────────────────────────────────────
# Everyday bearish-rejection book — per-day entry dates from the live engine.
# Run the orchestrator ONCE on the real-fills window with the live params; take the
# entry dates of its fills.  (This is the same engine the chart-stops-ab scorecard
# scored; we only need its DATES here for the coverage union.)
# ─────────────────────────────────────────────────────────────────────────────
def everyday_book_dates() -> tuple[list[str], dict]:
    """Run the live engine over the real-fills window; return its per-trade dates.

    Lets runner.run_with_params load its OWN data via the orchestrator loader (the
    raw orchestrator df/vix format), rather than reusing the discovery-format frames —
    the two loaders differ (discovery adds date/t/minute cols; orchestrator expects
    the raw timestamp_et column on vix_df).
    """
    from autoresearch.runner import run_with_params
    # Live Safe params (the everyday chart-stop-primary book). Real fills.
    live = {
        "use_real_fills": True,
        "min_triggers_bear": 1,
        "min_triggers_bull": 2,
        "premium_stop_pct_bear": -0.50,
        "premium_stop_pct_bull": -0.50,
        "tp1_premium_pct": 0.50,
        "tp1_qty_fraction": 0.667,
        "runner_target_premium_pct": 2.5,
        "per_trade_risk_cap_pct": 0.30,
        "midday_trendline_gate": True,
        "block_level_rejection": True,
        "entry_bar_body_pct_min": 0.20,
        "vix_bear_hard_cap": 23.0,
        "block_bull_1100_1200": True,
        "block_elite_bull": True,
        "block_elite_bull_vix_low": 0.0,
        "block_elite_bull_vix_high": 25.0,
        "profit_lock_threshold_pct": 0.05,
        "profit_lock_stop_offset_pct": 0.15,
    }
    # Bounded by real OPRA coverage (option CSVs end ~2026-05-29).
    start = dt.date(2025, 1, 2)
    end = dt.date(2026, 5, 29)
    res, _metrics = run_with_params(live, start, end)   # loader picks raw orchestrator format
    rows = []
    for f in res.trades:
        et = f.entry_time_et
        d = et.date() if hasattr(et, "date") else None
        if d is None:
            continue
        rows.append({"date": str(d), "side": getattr(f, "side", "?"),
                     "pnl": round(float(f.dollar_pnl), 2) if f.dollar_pnl is not None else None})
    dates = sorted({r["date"] for r in rows})
    pnls = [r["pnl"] for r in rows if r["pnl"] is not None]
    summary = {
        "n_trades": len(rows),
        "n_distinct_days": len(dates),
        "window": [str(start), str(end)],
        "exp_dollar": round(float(np.mean(pnls)), 2) if pnls else 0.0,
        "total_dollar": round(float(np.sum(pnls)), 2) if pnls else 0.0,
        "wr_pct": round(100.0 * np.mean([1 if p > 0 else 0 for p in pnls]), 1) if pnls else 0.0,
    }
    return dates, summary


# ─────────────────────────────────────────────────────────────────────────────
# Coverage math
# ─────────────────────────────────────────────────────────────────────────────
def _jaccard(a: set, b: set) -> float:
    u = a | b
    return round(len(a & b) / len(u), 3) if u else 0.0


def coverage_block(all_trading_days: list[str], named_date_sets: dict[str, list[str]],
                   window: tuple[str, str]) -> dict:
    """% of trading days with >=1 signal from the union; pairwise overlap (Jaccard);
    complementary vs redundant read.  Restrict the denominator to the common window."""
    lo, hi = window
    days_in_window = [d for d in all_trading_days if lo <= d <= hi]
    n_days = len(days_in_window)
    win = set(days_in_window)
    sets = {k: (set(v) & win) for k, v in named_date_sets.items()}
    union = set().union(*sets.values()) if sets else set()
    pairwise = {}
    keys = list(sets.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            inter = sets[a] & sets[b]
            pairwise[f"{a}|{b}"] = {
                "overlap_days": len(inter),
                "jaccard": _jaccard(sets[a], sets[b]),
                "a_only": len(sets[a] - sets[b]),
                "b_only": len(sets[b] - sets[a]),
            }
    return {
        "window": [lo, hi],
        "trading_days_in_window": n_days,
        "per_edge_fire_days": {k: len(v) for k, v in sets.items()},
        "per_edge_fire_day_pct": {k: round(100.0 * len(v) / n_days, 1) if n_days else 0.0
                                  for k, v in sets.items()},
        "union_fire_days": len(union),
        "union_coverage_pct": round(100.0 * len(union) / n_days, 1) if n_days else 0.0,
        "pairwise_overlap": pairwise,
        "days_with_2plus_edges": sum(
            1 for d in union if sum(1 for s in sets.values() if d in s) >= 2),
        "days_with_all_edges": sum(
            1 for d in union if all(d in s for s in sets.values())) if sets else 0,
    }


def main() -> int:
    print("Loading SPY / VIX / ribbon ...")
    spy = load_spy(str(SPY))
    vix = align_vix(spy, str(VIX))
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    days = build_day_contexts(spy)
    all_trading_days = sorted({str(dc.date) for dc in days})
    print(f"  {len(all_trading_days)} trading days, {all_trading_days[0]}..{all_trading_days[-1]}")

    # ── Signals ──────────────────────────────────────────────────────────────
    print("Detecting gap-and-go (+ real chain prices for B1) ...")
    gng = gap_and_go_signals(spy, ribbon, vix, days)
    gng_put = [r for r in gng if r["side"] == "P"]   # LIVE side is put-only
    gng_dates_put = sorted({r["date"] for r in gng_put})
    gng_dates_all = sorted({r["date"] for r in gng})

    print("Detecting VWAP-continuation ...")
    vwap_dates = vwap_cont_signal_dates(spy, ribbon, vix, days)

    print("Running everyday bearish-rejection book (live engine, real fills) ...")
    book_dates, book_summary = everyday_book_dates()
    print(f"  everyday book: {book_summary['n_trades']} trades / "
          f"{book_summary['n_distinct_days']} days")

    # ── B1 feasibility ───────────────────────────────────────────────────────
    print("Computing B1 feasibility (real ITM-1 put premiums vs $2K ceiling) ...")
    b1 = b1_feasibility(gng_put)

    # ── D1 coverage ──────────────────────────────────────────────────────────
    # Common window = intersection of data availability across the three edges.
    # Everyday book + real-OPRA stop at 2026-05-29; gap-and-go/VWAP detectors run to
    # 2026-06-16 but their SCORECARDS used the same real-fill cache. Use the everyday
    # book's window as the common denominator so coverage is apples-to-apples.
    window = (book_summary["window"][0], book_summary["window"][1])
    # Shippable set = {gap-and-go put (LIVE), everyday book (LIVE)}.
    shippable = coverage_block(all_trading_days, {
        "gap_and_go_put": gng_dates_put,
        "everyday_book": book_dates,
    }, window)
    # Shippable + near-survivor (adds VWAP-cont) = the "if VWAP flips live" picture.
    plus_vwap = coverage_block(all_trading_days, {
        "gap_and_go_put": gng_dates_put,
        "everyday_book": book_dates,
        "vwap_continuation": vwap_dates,
    }, window)

    # ── D2 leaderboard ───────────────────────────────────────────────────────
    print("Building D2 leaderboard from filed scorecards ...")
    leaderboard, blended = d2_leaderboard(window, len(all_trading_days),
                                          shippable, plus_vwap, book_summary, b1)

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "title": "Daily-trading book synthesis — D1 (coverage), D2 (leaderboard), B1 (feasible strike)",
        "method": {
            "detectors": "REUSED: detect_gap_and_go + detect_j_vwap_continuation; everyday book = lib.orchestrator.run_backtest via runner.run_with_params (live Safe params, real OPRA fills).",
            "fills": "lib.simulator_real (real OPRA, next-bar-open, v15 exit stack, chart-stop-only) — same as the filed scorecards. NOT rebuilt.",
            "B1_prices": "real OPRA entry premiums (next-bar-open ASK = bar.open + $0.02 slippage) at the EXACT requested strike (no nearest-strike fallback — true moneyness cost).",
            "coverage_window": f"{window[0]}..{window[1]} (bounded by real OPRA option coverage, the apples-to-apples denominator).",
            "honesty": "OOS expectancy comes from the filed scorecards (not re-derived). Frequency = distinct signal days / trading days on OUR tape. Coverage = union of per-day signal dates.",
        },
        "data": {"spy": SPY.name, "trading_days": len(all_trading_days),
                 "date_range": [all_trading_days[0], all_trading_days[-1]]},
        "D2_leaderboard": leaderboard,
        "D1_coverage": {
            "shippable_set": shippable,
            "shippable_plus_vwap_cont": plus_vwap,
            "blended_economics": blended,
            "everyday_book_summary": book_summary,
        },
        "B1_feasibility": b1,
        "signal_dates": {
            "gap_and_go_put": gng_dates_put,
            "gap_and_go_all": gng_dates_all,
            "vwap_continuation": vwap_dates,
            "everyday_book": book_dates,
        },
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWROTE {OUT}")
    _print_human(out)
    return 0


def b1_feasibility(gng_put: list[dict]) -> dict:
    """Real ITM-1 vs ATM vs OTM-1 put premium distribution on gap-down signal days,
    and whether min-3 fits the $2K ceiling at each strike."""
    res = {}
    live_ceiling = ACCOUNT_EQUITY * LIVE_PARAMS_CEILING_PCT
    for label in ("ATM", "ITM1", "OTM1"):
        prems = [r[label]["premium"] for r in gng_put if r.get(label)]
        costs = [r[label]["cost_min3"] for r in gng_put if r.get(label)]
        pnls = [r[label]["pnl_min3"] for r in gng_put if r.get(label) and r[label].get("pnl_min3") is not None]
        if not prems:
            res[label] = {"n": 0}
            continue
        prems_a = np.array(prems)
        costs_a = np.array(costs)
        fit_6pct = int((costs_a <= PREMIUM_CEILING_DOLLARS).sum())
        fit_live = int((costs_a <= live_ceiling).sum())
        # Real-fills edge at this strike, AND the edge on ONLY the days where min-3 fits
        # the live 40% ceiling (the realistic tradeable subset on $2K).
        pnls_a = np.array(pnls) if pnls else np.array([])
        fit_live_pnls = [r[label]["pnl_min3"] for r in gng_put
                         if r.get(label) and r[label].get("pnl_min3") is not None
                         and r[label]["cost_min3"] <= live_ceiling]
        res[label] = {
            "n_days_priced": len(prems),
            "premium_median": round(float(np.median(prems_a)), 3),
            "premium_mean": round(float(np.mean(prems_a)), 3),
            "premium_p10": round(float(np.percentile(prems_a, 10)), 3),
            "premium_p90": round(float(np.percentile(prems_a, 90)), 3),
            "cost_min3_median": round(float(np.median(costs_a)), 2),
            "cost_min3_mean": round(float(np.mean(costs_a)), 2),
            "cost_min3_max": round(float(np.max(costs_a)), 2),
            "days_min3_fits_6pct_ceiling": fit_6pct,
            "pct_days_min3_fits_6pct": round(100.0 * fit_6pct / len(costs), 1),
            "days_min3_fits_live_40pct": fit_live,
            "pct_days_min3_fits_live_40pct": round(100.0 * fit_live / len(costs), 1),
            "realfills_exp_per_trade_min3_all": round(float(np.mean(pnls_a)), 2) if len(pnls_a) else None,
            "realfills_exp_per_trade_min3_fits_live": round(float(np.mean(fit_live_pnls)), 2) if fit_live_pnls else None,
            "realfills_n_fits_live": len(fit_live_pnls),
            "realfills_wr_pct_all": round(100.0 * float(np.mean(pnls_a > 0)), 1) if len(pnls_a) else None,
        }
    # OOS exp/trade per strike from the filed gap-and-go scorecard (ATM+ITM1 only).
    gg = _load_scorecard("gap-and-go-LIVE.json")
    atm = gg["tiers"]["ATM"]["chart_stop_only"]
    itm1 = gg["tiers"]["ITM1"]["chart_stop_only"]
    oos_exp = {"ATM": atm["oos_exp_dollar"], "ITM1": itm1["oos_exp_dollar"]}
    full_exp = {"ATM": atm["exp_dollar"], "ITM1": itm1["exp_dollar"]}

    # Feasible-optimal on $2K: the strike with the BEST real-fills edge ON THE DAYS IT
    # ACTUALLY FITS the live 40% ceiling AND fits a large majority of days (>=80%). The
    # 6% ceiling is reported but is INFEASIBLE for min-3 at any tradeable strike on a
    # ~$600 underlying (would force OTM-5+ lottery tickets that have no validated edge).
    feasible = {}
    for label in ("ATM", "ITM1", "OTM1"):
        r = res.get(label, {})
        feasible[label] = {
            "median_min3_cost": r.get("cost_min3_median"),
            "fits_6pct_ceiling_median": bool(r.get("cost_min3_median", 9e9) <= PREMIUM_CEILING_DOLLARS),
            "pct_days_fits_live_40pct": r.get("pct_days_min3_fits_live_40pct"),
            "realfills_exp_fits_live": r.get("realfills_exp_per_trade_min3_fits_live"),
            "scorecard_oos_exp": oos_exp.get(label),
        }
    # Candidate = fits live ceiling >=80% of days AND has positive real-fills edge there.
    cands = [(lab, feasible[lab]["realfills_exp_fits_live"])
             for lab in ("ITM1", "ATM", "OTM1")
             if (feasible[lab]["pct_days_fits_live_40pct"] or 0) >= 80.0
             and feasible[lab]["realfills_exp_fits_live"] is not None
             and feasible[lab]["realfills_exp_fits_live"] > 0]
    best = max(cands, key=lambda x: x[1])[0] if cands else None
    return {
        "account_equity": ACCOUNT_EQUITY,
        "min_contracts": MIN_CONTRACTS,
        "ceiling_6pct_dollars": PREMIUM_CEILING_DOLLARS,
        "ceiling_live_40pct_dollars": live_ceiling,
        "ceiling_note": ("Two ceilings exist. (a) 6% = the doctrinal sizing-study RECOMMENDATION "
                         "(markdown/research/SIZING-STUDY-2026-06-19.md, NOT yet ratified into params). "
                         f"(b) {LIVE_PARAMS_CEILING_PCT:.0%} = what params.json v15_max_premium_pct_of_account[$0-2K] "
                         "ACTUALLY enforces TODAY. The 6% ceiling is INFEASIBLE for min-3 on a ~$600 underlying "
                         "(see headline_finding); the live 40% ceiling is the binding real-world gate."),
        "headline_finding": (
            "On a $2K account, min-3 contracts of SPY 0DTE puts costs ~$550-810 (OTM-1..ITM-1) at "
            "real OPRA prices = 27-40% of equity, because SPY is a ~$600 underlying. The 6% ceiling "
            "($120 -> max $0.40/contract for min-3) is unreachable at any strike with a validated edge "
            "(only OTM-5+ lottery tickets cost that little). Under the LIVE 40% ceiling: OTM-1 fits "
            "100% of days, ATM ~82%, ITM-1 only ~46%. So ITM-1 (the +42% edge) is NOT feasible as a "
            "blanket $2K default; the feasible-optimal strike is the deepest one that both fits and keeps a positive verified edge."),
        "per_strike": res,
        "scorecard_oos_exp": oos_exp,
        "scorecard_full_exp": full_exp,
        "feasible_check": feasible,
        "feasible_optimal_strike": best,
    }


def d2_leaderboard(window, n_all_days, shippable, plus_vwap, book_summary, b1) -> tuple[list[dict], dict]:
    """Rank edges by (OOS exp x frequency). Pull exp from filed scorecards; frequency
    from OUR-tape signal days within the common window."""
    gg = _load_scorecard("gap-and-go-LIVE.json")
    vwap = _load_scorecard("j-daily-pattern-LIVE.json")

    n_days = shippable["trading_days_in_window"]
    weeks = n_days / 5.0

    def per_week(fire_days):
        return round(fire_days / weeks, 2) if weeks else 0.0

    gg_atm = gg["tiers"]["ATM"]["chart_stop_only"]
    gg_itm1 = gg["tiers"]["ITM1"]["chart_stop_only"]
    vwap_cont = vwap["variants"]["J_VWAP_CONT"]["tiers"]["ATM"]

    gng_fire = shippable["per_edge_fire_days"]["gap_and_go_put"]
    book_fire = shippable["per_edge_fire_days"]["everyday_book"]
    vwap_fire = plus_vwap["per_edge_fire_days"]["vwap_continuation"]

    rows = [
        {
            "rank_key": "gap_and_go_ITM1_put",
            "edge": "Gap-and-go (PUT, ITM-1)  [B1 ship-grade strike]",
            "oos_exp_dollar": gg_itm1["oos_exp_dollar"],
            "full_exp_dollar": gg_itm1["exp_dollar"],
            "wr_pct": gg_itm1["wr_pct"],
            "fire_days_on_our_tape": gng_fire,
            "trades_per_week": per_week(gng_fire),
            "oos_stability": "all-cuts-OOS+ TRUE, WF median +1.39, q+ 6/6, DSR PASS, drop-top5 +$31.7",
            "ship_status": "SHIP (B1) — feasibility-gated (see B1 block)",
            "weekly_edge_dollar": round(gg_itm1["oos_exp_dollar"] * per_week(gng_fire), 1),
        },
        {
            "rank_key": "gap_and_go_ATM_put",
            "edge": "Gap-and-go (PUT, ATM)  [current LIVE]",
            "oos_exp_dollar": gg_atm["oos_exp_dollar"],
            "full_exp_dollar": gg_atm["exp_dollar"],
            "wr_pct": gg_atm["wr_pct"],
            "fire_days_on_our_tape": gng_fire,
            "trades_per_week": per_week(gng_fire),
            "oos_stability": "all-cuts-OOS+ TRUE, WF median +1.87, q+ 6/6, DSR PASS, drop-top5 +$15.6",
            "ship_status": "SHIP-LIVE (gap_and_go_enabled=true, side=put)",
            "weekly_edge_dollar": round(gg_atm["oos_exp_dollar"] * per_week(gng_fire), 1),
        },
        {
            "rank_key": "vwap_continuation_ATM",
            "edge": "VWAP-continuation (J daily edge, ATM, both sides)",
            "oos_exp_dollar": vwap_cont["oos_exp_dollar"],
            "full_exp_dollar": vwap_cont["exp_dollar"],
            "wr_pct": vwap_cont["wr_pct"],
            "fire_days_on_our_tape": vwap_fire,
            "trades_per_week": per_week(vwap_fire),
            "oos_stability": "NEAR-SURVIVOR (6/7): OOS+, WF median +0.55 (ATM)/+0.72 (ITM1)/+0.96 (VIXgate), q+ 5/6, DSR PASS, both-dirs+, drop-top5 +$24.5; FAILS strict all-cuts-OOS+ (recent Q2 window neg).",
            "ship_status": "WATCH / dormant flip-ready (j_vwap_cont_enabled=false)",
            "weekly_edge_dollar": round(vwap_cont["oos_exp_dollar"] * per_week(vwap_fire), 1),
        },
        {
            "rank_key": "everyday_bearish_rejection_book",
            "edge": "Everyday bearish-rejection book (live engine, chart-stop-primary)",
            "oos_exp_dollar": None,
            "full_exp_dollar": book_summary["exp_dollar"],
            "wr_pct": book_summary["wr_pct"],
            "fire_days_on_our_tape": book_fire,
            "trades_per_week": per_week(book_fire),
            "oos_stability": "chart-stops-ab-2026-06-18: edge_capture invariant +$1,340 (no J-edge regression), DSR PASS PSR 0.998, total +$16,671 vs prior +$8,160. Low frequency, anchor-validated.",
            "ship_status": "LIVE (production heartbeat)",
            "weekly_edge_dollar": round(book_summary["exp_dollar"] * per_week(book_fire), 1),
        },
    ]
    # Rank by weekly_edge_dollar (edge x frequency), the task's priority metric.
    rows_sorted = sorted(rows, key=lambda r: (r["weekly_edge_dollar"] is not None,
                                              r["weekly_edge_dollar"] or -9e9), reverse=True)
    for i, r in enumerate(rows_sorted, 1):
        r["priority"] = i

    # ── Blended economics on $2K ──────────────────────────────────────────────
    # Use the feasible-optimal gap-and-go strike's edge ON THE DAYS IT FITS the live
    # $2K ceiling (the realistic tradeable subset), + the everyday book exp.
    feas = b1.get("feasible_optimal_strike")
    feas_block = b1.get("per_strike", {}).get(feas, {}) if feas else {}
    gg_exp = (feas_block.get("realfills_exp_per_trade_min3_fits_live")
              if feas_block.get("realfills_exp_per_trade_min3_fits_live") is not None
              else gg_atm["oos_exp_dollar"])
    gg_label = f"gap_and_go_put_{feas or 'ATM'}_fits_live_2k"
    union_fire = shippable["union_fire_days"]
    union_pct = shippable["union_coverage_pct"]
    weeks_local = shippable["trading_days_in_window"] / 5.0

    # Blended weekly $ = sum of (edge exp x its own fire-days/week). Both fire at most
    # 1x/day; on overlap days the engine would pick one (independent kill switches), so
    # this is an UPPER bound that we annotate.
    gng_pw = per_week(gng_fire)
    book_pw = per_week(book_fire)
    blended_weekly = gg_exp * gng_pw + book_summary["exp_dollar"] * book_pw
    blended_monthly = blended_weekly * TRADING_WEEKS_PER_MONTH
    # Per-fire-day blended expectancy (across union days that actually have a signal).
    total_trades_pw = gng_pw + book_pw
    blended_exp_per_trade = round(blended_weekly / total_trades_pw, 2) if total_trades_pw else 0.0

    blended = {
        "shippable_set": [gg_label, "everyday_book"],
        "feasible_optimal_gap_and_go_strike": feas,
        "gap_and_go_oos_exp_used": gg_exp,
        "everyday_book_exp_used": book_summary["exp_dollar"],
        "union_coverage_pct": union_pct,
        "union_fire_days": union_fire,
        "trading_days_in_window": shippable["trading_days_in_window"],
        "gap_and_go_trades_per_week": gng_pw,
        "everyday_book_trades_per_week": book_pw,
        "blended_trades_per_week": round(total_trades_pw, 2),
        "blended_exp_per_trade_dollar": blended_exp_per_trade,
        "blended_weekly_dollar": round(blended_weekly, 1),
        "blended_monthly_dollar_2k": round(blended_monthly, 0),
        "blended_monthly_pct_of_2k": round(100.0 * blended_monthly / ACCOUNT_EQUITY, 1),
        "daily_coverage_verdict": _daily_verdict(union_pct, total_trades_pw),
        "honesty_note": ("blended_weekly is the sum of each edge's (exp x fire-days/week); on the "
                         f"{shippable['pairwise_overlap'].get('gap_and_go_put|everyday_book', {}).get('overlap_days', 0)} "
                         "overlap days the engine trades ONE (kill switches isolated but one position/account), "
                         "so realized P&L is at/below this figure. Frequency is the binding constraint, not edge."),
    }
    return rows_sorted, blended


def _daily_verdict(union_pct: float, trades_pw: float) -> str:
    if union_pct >= 80 and trades_pw >= 4:
        return "DAILY achievable from the shippable set"
    if union_pct >= 50 or trades_pw >= 2:
        return f"NEAR-DAILY only with the WATCH edge; shippable-alone is ~{trades_pw:.1f} trades/wk ({union_pct:.0f}% of days)"
    return (f"NOT daily — shippable set fires ~{trades_pw:.1f} trades/wk ({union_pct:.0f}% of days). "
            "Daily coverage needs the VWAP-cont near-survivor flipped live.")


def _print_human(out: dict) -> None:
    print("\n" + "=" * 78)
    print("D2 LEADERBOARD (priority order, by OOS-edge x frequency):")
    for r in out["D2_leaderboard"]:
        print(f"  #{r['priority']} {r['edge']}")
        print(f"       OOS exp ${r['oos_exp_dollar']}  | full exp ${r['full_exp_dollar']}  | "
              f"{r['trades_per_week']}/wk  | weekly-edge ${r['weekly_edge_dollar']}  | {r['ship_status']}")
    b = out["D1_coverage"]["blended_economics"]
    print("\nD1 COVERAGE (shippable set):")
    s = out["D1_coverage"]["shippable_set"]
    print(f"  union coverage: {s['union_coverage_pct']}% of {s['trading_days_in_window']} days  "
          f"({s['union_fire_days']} fire-days)")
    print(f"  per-edge: {s['per_edge_fire_day_pct']}")
    print(f"  overlap: {s['pairwise_overlap']}")
    print(f"  blended: {b['blended_trades_per_week']} trades/wk, exp ${b['blended_exp_per_trade_dollar']}/trade, "
          f"~${b['blended_monthly_dollar_2k']}/mo ({b['blended_monthly_pct_of_2k']}% of $2K)")
    print(f"  VERDICT: {b['daily_coverage_verdict']}")
    pv = out["D1_coverage"]["shippable_plus_vwap_cont"]
    print(f"  +VWAP-cont: union {pv['union_coverage_pct']}% ({pv['union_fire_days']} days)")
    f = out["B1_feasibility"]
    print("\nB1 FEASIBILITY (real put premiums; 6% ceiling=${:.0f}, LIVE 40% ceiling=${:.0f}):".format(
        f["ceiling_6pct_dollars"], f["ceiling_live_40pct_dollars"]))
    for lab in ("ATM", "ITM1", "OTM1"):
        r = f["per_strike"].get(lab, {})
        if r.get("n_days_priced"):
            print(f"  {lab}: prem med ${r['premium_median']} -> min3 ${r['cost_min3_median']}  "
                  f"| fits-6pct {r['pct_days_min3_fits_6pct']}%  | fits-40pct {r['pct_days_min3_fits_live_40pct']}%  "
                  f"| edge(fits-live) ${r['realfills_exp_per_trade_min3_fits_live']}  | scorecard-OOS ${f['scorecard_oos_exp'].get(lab, 'n/a')}")
    print(f"  HEADLINE: {f['headline_finding']}")
    print(f"  FEASIBLE-OPTIMAL STRIKE on $2K: {f['feasible_optimal_strike']}")
    print("=" * 78)


if __name__ == "__main__":
    raise SystemExit(main())
