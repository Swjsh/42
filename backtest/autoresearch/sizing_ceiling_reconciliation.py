"""SIZING-CEILING RECONCILIATION (Item 2, B6 row) — 2026-06-20.

THE CONTRADICTION (surfaced by the D1/B1-feasibility batch):
  - The sizing-study (markdown/research/SIZING-STUDY-2026-06-19.md) recommends a
    ~6% premium ceiling (~$120 on $2K). That number was derived from J's CHEAP
    OTM-3 SPX/SPY style: mean entry premium ~$1.94, tabled only $0.30-0.50 contracts,
    half-Kelly = 3.9% of equity. min-3 at $0.40 = $120 = 6%.
  - But SPY 0DTE puts on a ~$600 underlying cost ~$2-3 ATM. min-3 = $550-840 =
    27-42% of $2K. So the 6% ceiling FORBIDS the structurally-required min-3 at any
    strike that has a validated edge. This BLOCKS trading any edge on $2K.

WHAT THIS SCRIPT DOES (ANALYSIS + PROPOSE only — risk doctrine is J's call):
  1. Reads REAL OPRA 0DTE SPY put entry premiums (next-bar-open ASK = bar.open +
     $0.02 slippage, identical to simulator_real) at ATM / OTM-1 / OTM-2 for the
     09:35 ET entry on EVERY cached trading day (not just gap days — the contradiction
     is structural to a $600 underlying, so we want the full premium distribution).
  2. Computes min-3 cost ($ and % of $2K) at each strike + the distribution.
  3. Maps against the account's risk rails: Rule 6 per-trade cap (Safe 30% = $600),
     the -30% daily kill-switch ($600), the min-3 structural requirement, and the
     LIVE params ceiling (v15_max_premium_pct_of_account[$0-2K] = 40% = $800).
  4. Reframes the prudent bound as $-AT-RISK-to-the-chart-stop (not gross premium):
     with chart-stops (the live exit), $-at-risk = premium x stop-distance, not the
     full premium. This is the reconciliation lever.
  5. Proposes a RECONCILED $2K sizing rule (numbers only; flagged for J's risk
     sign-off). Changes NOTHING live.

Pure Python, $0 cost. Reads the OPRA cache + params.json. Writes a JSON scorecard.
NEVER edits params / risk_gate / heartbeat.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO / "backtest"))

from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after, _CONTRACT_BAR_CACHE,
)
from lib.simulator_real import _strike_from_spot, DEFAULT_ENTRY_SLIPPAGE  # noqa: E402

PARAMS_PATH = REPO / "automation" / "state" / "params.json"
OUT_PATH = REPO / "analysis" / "recommendations" / "sizing-ceiling-reconciliation.json"

# Account + doctrine constants
ACCOUNT_EQUITY = 2000.0
MIN_CONTRACTS = 3
SIZING_STUDY_CEILING_PCT = 0.06        # the disputed sizing-study recommendation (~$120)
RULE6_SAFE_CAP_PCT = 0.30              # Rule 6 per-trade cap, Safe account (30% = $600)
KILL_SWITCH_PCT = 0.30                 # -30% of SoD equity daily kill-switch ($600)
HALF_KELLY_PCT = 0.039                 # sizing-study half-Kelly on J's realized-payoff basis (~$78)

# Entry timing: the 09:35 ET fill = the SECOND 5-min bar of the session. The CSVs carry
# a -04:00 offset on ET wall time; first bar = "...10:30:00-04:00" (= 09:30 ET bar).
# Entry fills on the NEXT bar after the 09:30 trigger bar => the "...10:35:00-04:00" bar.
# We reuse bar_at_or_after with the option's own timestamps, exactly like simulate_trade_real.
ENTRY_BAR_WALLCLOCK = "10:35:00-04:00"   # 09:35 ET in the cache's wall-clock convention

# Strikes to price (puts). offset is subtracted from ATM for puts (simulator convention):
#   ATM  : strike = round(spot)
#   OTM-1: strike = round(spot) - 1  (further OTM for a put = lower strike)
#   OTM-2: strike = round(spot) - 2
STRIKE_LABELS = {"ATM": 0, "OTM-1": 1, "OTM-2": 2}


def _load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))


def _live_ceiling_pct(params: dict) -> float:
    """Pull the actual $0-2K tier premium ceiling from params.json (the binding live gate)."""
    tiers = params.get("v15_max_premium_pct_of_account", [])
    for t in tiers:
        # tiers look like {"max_equity": 2000, "pct": 0.40} or similar — be tolerant.
        lo = t.get("min_equity", t.get("min", 0))
        hi = t.get("max_equity", t.get("max", 10**12))
        if lo <= ACCOUNT_EQUITY <= hi:
            return float(t.get("pct", t.get("max_pct", t.get("value", 0.40))))
    return 0.40  # documented $0-2K default


def _spy_open_at_entry(spy_df: pd.DataFrame, day: dt.date) -> float | None:
    """SPY open on the 09:35-ET entry bar (the bar we fill on), per the cache convention."""
    sub = spy_df[spy_df["timestamp_et"].astype(str).str.startswith(day.isoformat())]
    if sub.empty:
        return None
    # entry bar = the one ending ...10:35:00-04:00 (the bar AFTER the 09:30 trigger bar)
    entry = sub[sub["timestamp_et"].astype(str).str.contains(ENTRY_BAR_WALLCLOCK)]
    if entry.empty:
        return None
    return float(entry.iloc[0]["open"])


def _entry_premium(day: dt.date, spot: float, offset: int) -> tuple[float, int] | None:
    """Real ASK-side put entry premium at strike = round(spot)-offset on `day`.

    Mirrors simulator_real.simulate_trade_real: entry = next-bar open + slippage at the
    EXACT strike (no nearest-strike fallback — true moneyness cost). Returns
    (premium, true_offset) or None if that contract isn't cached.
    """
    atm = _strike_from_spot(spot)
    strike = atm - offset  # puts: OTM = lower strike
    sym = option_symbol(day, strike, "P")
    df = load_contract_bars(sym)
    if df is None or df.empty:
        return None
    # The option CSV uses the same wall-clock; find the 09:35-ET entry bar.
    df = df.copy()
    ts = df["timestamp_et"].astype(str)
    row = df[ts.str.contains(ENTRY_BAR_WALLCLOCK)]
    if row.empty:
        return None
    open_px = float(row.iloc[0]["open"])
    if open_px <= 0:
        return None
    return open_px + DEFAULT_ENTRY_SLIPPAGE, int(atm - strike)


def _pct_stats(arr: list[float]) -> dict:
    a = np.array(arr, dtype=float)
    return {
        "n": int(a.size),
        "median": round(float(np.median(a)), 3),
        "mean": round(float(np.mean(a)), 3),
        "p10": round(float(np.percentile(a, 10)), 3),
        "p90": round(float(np.percentile(a, 90)), 3),
        "min": round(float(a.min()), 3),
        "max": round(float(a.max()), 3),
    }


def main() -> int:
    print("=" * 92)
    print("SIZING-CEILING RECONCILIATION (Item 2) — real min-3 SPY 0DTE put cost on $2K")
    print("=" * 92)

    params = _load_params()
    live_ceiling_pct = _live_ceiling_pct(params)
    live_ceiling_usd = ACCOUNT_EQUITY * live_ceiling_pct
    sizing_ceiling_usd = ACCOUNT_EQUITY * SIZING_STUDY_CEILING_PCT
    rule6_cap_usd = ACCOUNT_EQUITY * RULE6_SAFE_CAP_PCT
    kill_switch_usd = ACCOUNT_EQUITY * KILL_SWITCH_PCT
    print(f"  $2K rails: 6% sizing-study ceiling=${sizing_ceiling_usd:.0f} | "
          f"live params ceiling={live_ceiling_pct*100:.0f}%=${live_ceiling_usd:.0f} | "
          f"Rule6 cap=30%=${rule6_cap_usd:.0f} | kill-switch=${kill_switch_usd:.0f}")

    # Load SPY 5m (broadest cached window that overlaps OPRA coverage ~through 2026-05-29).
    spy_path = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
    spy_df = pd.read_csv(spy_path)
    # Restrict to the OPRA-covered window.
    spy_df = spy_df[(spy_df["timestamp_et"].astype(str) >= "2025-01-02")
                    & (spy_df["timestamp_et"].astype(str) <= "2026-05-29T23:59")].reset_index(drop=True)
    all_days = sorted({pd.Timestamp(t).date() for t in spy_df["timestamp_et"]})
    print(f"  Scanning {len(all_days)} trading days (2025-01-02 .. 2026-05-29) for real put premiums ...")

    # Per-day real premiums at each strike.
    per_strike: dict[str, list[dict]] = {k: [] for k in STRIKE_LABELS}
    spot_samples: list[float] = []
    for day in all_days:
        spot = _spy_open_at_entry(spy_df, day)
        if spot is None or spot <= 0:
            continue
        spot_samples.append(spot)
        for label, off in STRIKE_LABELS.items():
            pr = _entry_premium(day, spot, off)
            if pr is None:
                continue
            prem, true_off = pr
            if true_off != off:
                continue  # exact strike not found at requested moneyness
            per_strike[label].append({"date": day.isoformat(), "spot": round(spot, 2),
                                      "premium": round(prem, 3),
                                      "cost_min3": round(prem * MIN_CONTRACTS * 100.0, 2)})
        # Keep the in-memory OPRA cache from ballooning across 350 days x many strikes.
        if len(_CONTRACT_BAR_CACHE) > 4000:
            _CONTRACT_BAR_CACHE.clear()

    print(f"  SPY underlying over window: median=${np.median(spot_samples):.0f} "
          f"range ${min(spot_samples):.0f}-${max(spot_samples):.0f}")

    # Build the cost table per strike.
    strike_table: dict[str, dict] = {}
    for label in STRIKE_LABELS:
        recs = per_strike[label]
        if not recs:
            continue
        prems = [r["premium"] for r in recs]
        costs = np.array([r["cost_min3"] for r in recs], dtype=float)
        prem_stats = _pct_stats(prems)
        cost_stats = _pct_stats([float(c) for c in costs])
        fits_6pct = int((costs <= sizing_ceiling_usd).sum())
        fits_live = int((costs <= live_ceiling_usd).sum())
        fits_rule6 = int((costs <= rule6_cap_usd).sum())
        n = len(costs)
        strike_table[label] = {
            "n_days_priced": n,
            "premium": prem_stats,
            "min3_cost": cost_stats,
            "min3_cost_pct_of_2k_median": round(100.0 * float(np.median(costs)) / ACCOUNT_EQUITY, 1),
            "min3_cost_pct_of_2k_p90": round(100.0 * float(np.percentile(costs, 90)) / ACCOUNT_EQUITY, 1),
            "days_min3_fits_6pct_ceiling": fits_6pct,
            "pct_days_fits_6pct": round(100.0 * fits_6pct / n, 1),
            "days_min3_fits_live_40pct": fits_live,
            "pct_days_fits_live_40pct": round(100.0 * fits_live / n, 1),
            "days_min3_fits_rule6_30pct": fits_rule6,
            "pct_days_fits_rule6_30pct": round(100.0 * fits_rule6 / n, 1),
        }

    print("\n  Real min-3 0DTE SPY put cost (median) + ceiling-fit rates:")
    print(f"  {'Strike':>7} {'n':>4} {'prem_med':>9} {'min3_$med':>10} {'%2K':>6} "
          f"{'fit6%':>7} {'fit30%':>7} {'fit40%':>7}")
    for label in STRIKE_LABELS:
        t = strike_table.get(label)
        if not t:
            continue
        print(f"  {label:>7} {t['n_days_priced']:>4} "
              f"{t['premium']['median']:>9.2f} ${t['min3_cost']['median']:>9.0f} "
              f"{t['min3_cost_pct_of_2k_median']:>5.0f}% "
              f"{t['pct_days_fits_6pct']:>6.0f}% {t['pct_days_fits_rule6_30pct']:>6.0f}% "
              f"{t['pct_days_fits_live_40pct']:>6.0f}%")

    # ---- The reconciliation: reframe the prudent bound as $-at-risk, not gross premium ----
    # With chart-stops (the LIVE exit), the realistic $-at-risk per trade is NOT the gross
    # premium. It is premium x typical stop-distance. Two reference stop-distances:
    #   - chart/ribbon stop (the binding live stop): historically the median LOSS on the
    #     everyday book is ~25-35% of premium before the chart/ribbon/profit-lock exit fires.
    #   - the -50% catastrophe cap (the wide backstop, premium_stop_pct_bear): worst case.
    # half-Kelly (3.9% of equity ~ $78) is a $-AT-RISK budget, not a gross-premium budget.
    # So the coherent rule is: size min-3 at a strike whose (gross premium) fits the
    # per-trade NOTIONAL cap (Rule 6, 30%), AND whose $-at-risk-to-chart-stop fits half-Kelly.
    atm = strike_table.get("ATM", {})
    otm1 = strike_table.get("OTM-1", {})
    otm2 = strike_table.get("OTM-2", {})

    def _risk_at_stop(cost_median: float, stop_frac: float) -> float:
        return round(cost_median * stop_frac, 2)

    reconciliation = {
        "the_contradiction": {
            "sizing_study_ceiling_pct": SIZING_STUDY_CEILING_PCT,
            "sizing_study_ceiling_usd": sizing_ceiling_usd,
            "derivation": ("6% was derived from J's CHEAP OTM-3 SPX/SPY style: mean entry "
                           "premium ~$1.94, half-Kelly=3.9% of equity, min-3 at $0.40=$120=6%. "
                           "It is a $-RISK budget expressed as a gross-premium % for a $0.40 contract."),
            "why_infeasible_on_spy_0dte": ("SPY 0DTE puts on a ~$600 underlying cost ~$2-3 ATM, so "
                                           "min-3 = $550-840 = 27-42% of $2K. The 6% ceiling ($120) "
                                           "implies max ~$0.40/contract for min-3 — unreachable at any "
                                           "strike with a validated gap-and-go / book edge."),
            "real_min3_cost_atm_median": atm.get("min3_cost", {}).get("median"),
            "real_min3_cost_atm_pct_of_2k": atm.get("min3_cost_pct_of_2k_median"),
        },
        "risk_rails_map": {
            "min_contracts_structural": MIN_CONTRACTS,
            "rule6_safe_per_trade_cap_pct": RULE6_SAFE_CAP_PCT,
            "rule6_safe_per_trade_cap_usd": rule6_cap_usd,
            "kill_switch_pct": KILL_SWITCH_PCT,
            "kill_switch_usd": kill_switch_usd,
            "live_params_ceiling_pct": live_ceiling_pct,
            "live_params_ceiling_usd": live_ceiling_usd,
            "half_kelly_pct": HALF_KELLY_PCT,
            "half_kelly_usd": round(ACCOUNT_EQUITY * HALF_KELLY_PCT, 2),
        },
        "dollar_at_risk_reframe": {
            "insight": ("The 6% number conflates GROSS PREMIUM with $-AT-RISK. With chart-stops "
                        "(the live primary exit), the realistic loss per trade is premium x stop-"
                        "distance, NOT the whole premium. half-Kelly (~$78) is a $-at-risk budget."),
            "atm_min3_gross_cost_median": atm.get("min3_cost", {}).get("median"),
            "atm_risk_at_chart_stop_30pct": _risk_at_stop(atm.get("min3_cost", {}).get("median", 0.0), 0.30),
            "atm_risk_at_catastrophe_cap_50pct": _risk_at_stop(atm.get("min3_cost", {}).get("median", 0.0), 0.50),
            "note": ("ATM min-3 GROSS is ~30-40% of $2K, but its $-at-risk-to-the-chart-stop "
                     "(~30% premium move before the chart/ribbon/profit-lock exit) is ~$200, and a "
                     "catastrophe -50% stop caps it ~$340 — both well inside the -30% kill-switch "
                     "($600) and the Rule-6 per-trade cap ($600). The gross premium is the NOTIONAL "
                     "deployed, not the loss exposure."),
        },
    }

    # ---- Proposed reconciled $2K sizing rule (numbers; flagged for J's risk sign-off) ----
    proposed_rule = {
        "headline": ("Replace the 6% GROSS-PREMIUM ceiling for SPY 0DTE with a TWO-PART rule that "
                     "lets min-3 fit at a feasible strike while respecting the real risk rails."),
        "part_1_notional_cap": {
            "rule": "Per-trade GROSS premium (min-3 cost) <= Rule-6 per-trade cap (Safe 30% of equity).",
            "at_2k": f"${rule6_cap_usd:.0f}",
            "rationale": ("This is the EXISTING Rule 6 cap — it already bounds notional. It is the "
                          "correct binding gate, not a new 6% premium ceiling. The live params 40% "
                          "tier is LOOSER than Rule 6; tighten the $0-2K params tier to 30% to MATCH "
                          "Rule 6 (removes the 40%-vs-30% inconsistency)."),
        },
        "part_2_dollar_at_risk_cap": {
            "rule": ("Per-trade $-AT-RISK-to-the-chart-stop <= half-Kelly band (~4% of equity). "
                     "$-at-risk = min3_gross_cost x stop_distance_fraction (use the chart/ribbon "
                     "stop distance, ~0.30; cap the catastrophe stop so worst-case stays < kill-switch)."),
            "at_2k_half_kelly": f"${ACCOUNT_EQUITY * HALF_KELLY_PCT:.0f}",
            "rationale": ("This restores the sizing-study's ACTUAL intent (half-Kelly $-at-risk) "
                          "without the OTM-3-specific gross-premium proxy. ATM min-3's $-at-risk to "
                          "the chart stop (~$200) is above strict half-Kelly ($78); accept it as the "
                          "structural floor (min-3 is mandatory) OR step OTM to reduce gross + $-risk."),
        },
        "feasible_optimal_strike_2k": {
            "primary": "ATM",
            "fallback_high_premium_open": "OTM-1",
            "do_not_use_blanket": "ITM-1 (busts the live ceiling >half the days; reserve for $10k+ tier)",
            "rationale": ("Matches the D1/B1 finding: ATM has the best verified edge on the days it "
                          "fits and already-LIVE scorecard; OTM-1 is the 100%-fit fallback on high-IV "
                          "opens; ITM-1's +42% edge is a $10k+ lever, infeasible as a $2K default."),
        },
        "core_insight_preserved": ("J's 1-2-lot lesson (L168) was about ADDING / scaling-UP and "
                                   "post-loss revenge-sizing, NOT the base trade. min-3 as a FLAT, "
                                   "atomic, chart-stopped bracket is structurally different. Keep "
                                   "min-3 + the no-add rule + the post-loss throttle; the base-trade "
                                   "notional is bounded by Rule 6, not by a 6% premium proxy."),
        "J_DECISION_REQUIRED": ("RISK DOCTRINE — J's call. This proposes: (a) DROP the 6% gross-premium "
                                "ceiling for SPY 0DTE (it is an SPX-OTM3 artifact, infeasible on $600 "
                                "SPY); (b) bind per-trade size by the EXISTING Rule-6 30% notional cap + "
                                "a $-at-risk-to-stop half-Kelly check; (c) tighten the live params $0-2K "
                                "tier 40%->30% to match Rule 6. NOTHING changed live. Needs J sign-off."),
    }

    scorecard = {
        "title": "Sizing-ceiling reconciliation — real min-3 SPY 0DTE cost on $2K vs the 6% ceiling",
        "item": "Item 2 / master-plan B6",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "status": "ANALYSIS + PROPOSE-ONLY (Rule 9 / risk doctrine = J's call). NOTHING live changed.",
        "method": ("Real OPRA 0DTE SPY put entry premiums (next-bar-open ASK = bar.open + $0.02 "
                   "slippage, identical to simulator_real) at ATM/OTM-1/OTM-2 for the 09:35 ET entry "
                   "on every cached trading day 2025-01-02..2026-05-29. Exact strike, no nearest-"
                   "strike fallback. Mapped against the $2K risk rails + the sizing-study 6% ceiling."),
        "account_equity": ACCOUNT_EQUITY,
        "underlying_window": {
            "spy_median": round(float(np.median(spot_samples)), 2),
            "spy_min": round(float(min(spot_samples)), 2),
            "spy_max": round(float(max(spot_samples)), 2),
            "n_days": len(spot_samples),
        },
        "real_min3_cost_by_strike": strike_table,
        "reconciliation": reconciliation,
        "proposed_reconciled_rule": proposed_rule,
        "source_docs": [
            "markdown/research/SIZING-STUDY-2026-06-19.md (the 6% derivation)",
            "markdown/0dte/J-DAILY-TRADING-BOOK.md (B1 feasibility; the 27-40% finding)",
            "automation/state/params.json (live ceilings + Rule 6 cap)",
        ],
        "caveats": [
            "Real OPRA cache ends ~2026-05-29 (coverage bound).",
            "Exact-strike pricing (no nearest-strike fallback) => a few cache-missing days drop out per strike.",
            "Premiums are the 09:35 ET entry fill (next bar after 09:30); intraday entries on rejection "
            "setups can be cheaper or pricier — this is the open-fill reference distribution.",
            "$-at-risk-to-chart-stop uses a ~30% premium-move proxy for the chart/ribbon stop distance; "
            "the exact per-trade stop distance varies (the catastrophe -50% cap is the worst case).",
            "PROPOSE-ONLY: risk doctrine (min_contracts, premium caps, the ceiling) is J's sign-off.",
        ],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    print(f"\nScorecard: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
