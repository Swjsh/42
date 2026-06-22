"""B9-CAP — re-score the 3-edge VWAP portfolio through cap_admission (the realizable book).

WHY (the cap-defect cycle): simulator_real has NO per-trade notional/min_contracts cap, so
EVERY cap-blind B9 headline (Safe ATM @qty3 ; Bold ITM-2 @qty5) counts fills the LIVE
engine (risk_gate.check_order, the single authority) would BLOCK. This harness re-runs the
byte-for-byte B9 detectors on real 0DTE OPRA fills, at the PER-ACCOUNT qty (Safe 3 / Bold 5),
then applies lib.cap_admission.admit_book per account at current equity (Safe $2,000/$600 cap ;
Bold $1,648/$824 cap), enforce_cap=True (default). A blocked fill -> $0 realizable (never
qty-reduced; qty<min = hard DENY).

It answers:
  1. The AFFORDABLE tier per account: the richest strike tier (OTM-2/OTM-1/ATM/ITM-2 @ 0DTE)
     whose median order (median entry premium x qty x 100) FITS the cap.
  2. The TRUE realizable portfolio P&L + Sharpe + maxDD per account at the affordable tier,
     vs the cap-blind headline.
  3. Standalone realizable OOS exp/tr per edge per affordable tier.
  4. Whether the diversification (daily-P&L correlation) survives the cap.

Reuses _b9_portfolio's detectors + metrics; the ONLY new behaviour is (a) qty is a parameter
(re-run at the account's real qty, since _compute_pnl floors tp1_qty = int(qty*frac) and is
NOT perfectly linear in qty), (b) each TradeRow now carries entry_premium so cap_admission can
gate it, (c) admit_book per account/qty/equity before aggregation.

Pure Python / numpy, $0, no live orders, no params/heartbeat edits. Markets closed. PASTE REAL.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b9_cap_aware_rescore.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts, _nearest_cached_strike, _strike_from_spot, Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix, detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median, vix_slope, detect_opt_signals as detect_vix_regime_dayside,
    VIX_MEDIAN_BARS, VIX_SLOPE_BARS, _swing_stop,
)
from autoresearch._b9_portfolio import (  # noqa: E402
    PREMIUM_STOP_PCT, MAX_STRIKE_STEPS, OOS_YEAR, TRADING_DAYS_PER_YEAR,
    portfolio_aggregate, by_day, daily_series_for_days, jaccard, load_vix_regime_config,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.cap_admission import admit_book, params_for, decide  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "B9-CAP-AWARE-RESCORE.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "B9-CAP-AWARE-RESCORE.md"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# Strike tiers tested (0DTE). offset is added/subtracted to the ATM strike per the B9
# convention: for a CALL, strike = atm + offset; for a PUT, strike = atm - offset.
#   ATM offset 0 ; ITM-2 offset -2 ; OTM-1 offset +1 ; OTM-2 offset +2.
TIERS = {"OTM-2": +2, "OTM-1": +1, "ATM": 0, "ITM-2": -2}

# Per-account sizing (the cap is measured against current equity).
ACCOUNTS = {
    "Safe-2": {"acct": "safe", "equity": 2_000.0, "qty": 3, "edges": ("e1", "e2", "e4")},
    "Bold":   {"acct": "bold", "equity": 1_648.0, "qty": 5, "edges": ("e1", "e2")},
}


@dataclass
class TradeRow:
    date: str
    side: str
    strike: int
    pnl: float            # dollar P&L at THIS row's qty
    pct: float
    entry_premium: float  # per-contract entry premium (cap gate reads this)
    exit_reason: str


def simulate_set(signals, spy, ribbon, vix, *, strike_offset, qty, setup="B9CAP",
                 premium_stop_pct=PREMIUM_STOP_PCT):
    """Run every signal at one strike tier on real OPRA fills, at the given qty.
    Identical to _b9_portfolio.simulate_set except qty is a parameter and we keep
    entry_premium per fill."""
    rows = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=qty, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, strike=int(strike),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            entry_premium=round(float(fill.entry_premium), 4),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def edge_metrics_capaware(admitted, blocked):
    """Per-trade standalone metrics over the CAP-ADMITTED rows (realizable book)."""
    rows = list(admitted)
    if not rows:
        return {"n": 0, "n_blocked": len(blocked)}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    bd = by_day(rows)
    prems = sorted(r.entry_premium for r in rows)
    med = prems[len(prems) // 2] if len(prems) % 2 == 1 else 0.5 * (prems[len(prems)//2-1] + prems[len(prems)//2])
    return {
        "n": n, "n_blocked": len(blocked), "days": len(bd),
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "oos_n": len(oos_rows),
        "oos_exp": round(float(np.mean([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "oos_total": round(float(np.sum([r.pnl for r in oos_rows])), 2) if oos_rows else 0.0,
        "median_entry_premium": round(med, 3),
    }


def corr_matrix(edge_rows):
    """Daily-P&L Pearson on union of fire-days (0 where one didn't fire) + Jaccard."""
    names = list(edge_rows)
    fire = {nm: set(by_day(r)) for nm, r in edge_rows.items()}
    out_corr, out_jac = {}, {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            key = f"{a}__{b}"
            out_jac[key] = jaccard(fire[a], fire[b])
            union = sorted(fire[a] | fire[b])
            if len(union) >= 3:
                va = daily_series_for_days(edge_rows[a], union)
                vb = daily_series_for_days(edge_rows[b], union)
                out_corr[key] = (round(float(np.corrcoef(va, vb)[0, 1]), 3)
                                 if va.std() > 0 and vb.std() > 0 else None)
            else:
                out_corr[key] = None
    return {"jaccard": out_jac, "daily_pnl_corr": out_corr,
            "fire_day_counts": {nm: len(s) for nm, s in fire.items()}}


def main() -> int:
    print(f"[b9cap] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_trading_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()
    print(f"[b9cap] trading_days={n_trading_days}  edge#4 vix-cfg={vix_cfg}", flush=True)

    # Detect each edge's signals ONCE (byte-for-byte the B9 detectors).
    sig = {}
    sig["e1"] = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig["e2"] = detect_reclaim_failed_break(days)
    s4 = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                   vix_cfg["low_margin"], vix_cfg["slope_rule"])
    sig["e4"] = [Signal(bar_idx=s.gidx, side=s.side,
                        stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                        note="vix_regime_dayside") for s in s4]
    print(f"[b9cap] signals: e1={len(sig['e1'])} e2={len(sig['e2'])} e4={len(sig['e4'])}", flush=True)

    setup_name = {"e1": "VWAPCONT", "e2": "RECLAIM", "e4": "VIXREGIME"}

    results = {}   # account -> tier -> {...}
    for acct, cfg in ACCOUNTS.items():
        equity, qty, edges = cfg["equity"], cfg["qty"], cfg["edges"]
        acct_key = cfg["acct"]
        p = params_for(acct_key)
        # cap context
        risk_cap = p["per_trade_risk_cap_pct"] * equity
        tier_pct = next(t["max_pct"] for t in p["v15_max_premium_pct_of_account"]
                        if t["equity_min"] <= equity < t["equity_max"])
        eff_cap = min(risk_cap, tier_pct * equity)
        max_prem_per_contract = eff_cap / (qty * 100.0)
        print(f"\n[b9cap] === {acct}: equity=${equity:.0f} qty={qty} "
              f"risk_cap=${risk_cap:.0f} tier_cap=${tier_pct*equity:.0f} "
              f"EFFECTIVE_CAP=${eff_cap:.0f}  max_prem/contract=${max_prem_per_contract:.3f} "
              f"(min_contracts={p['min_contracts']})", flush=True)

        results[acct] = {
            "equity": equity, "qty": qty, "min_contracts": p["min_contracts"],
            "risk_cap_dollar": round(risk_cap, 2),
            "tier_cap_dollar": round(tier_pct * equity, 2),
            "effective_cap_dollar": round(eff_cap, 2),
            "max_premium_per_contract": round(max_prem_per_contract, 4),
            "tiers": {},
        }

        for tname, off in TIERS.items():
            edge_capaware = {}
            edge_blind = {}
            edge_admit_rows = {}
            for e in edges:
                rows, cov = simulate_set(sig[e], spy, ribbon, vix,
                                         strike_offset=off, qty=qty, setup=setup_name[e])
                # cap-blind book (every fill) for the headline comparison
                edge_blind[e] = edge_metrics_capaware(rows, [])
                # cap-aware admission at this account's qty/equity
                adm = admit_book(rows, acct_key, equity, qty, enforce_cap=True,
                                 premium_getter=lambda r: r.entry_premium)
                edge_capaware[e] = {
                    **edge_metrics_capaware(adm.admitted, adm.blocked),
                    "block_rate": adm.block_rate,
                    "block_codes": {str(k): v for k, v in adm.block_codes.items()},
                }
                edge_admit_rows[e] = list(adm.admitted)

            # median entry premium across ALL edges at this tier (affordability summary)
            all_prem = sorted(r.entry_premium for e in edges for r in
                              simulate_set(sig[e], spy, ribbon, vix, strike_offset=off,
                                           qty=qty, setup=setup_name[e])[0])
            med_all = (all_prem[len(all_prem)//2] if all_prem and len(all_prem) % 2 == 1
                       else (0.5*(all_prem[len(all_prem)//2-1]+all_prem[len(all_prem)//2])
                             if all_prem else 0.0))
            median_order_notional = med_all * qty * 100.0
            median_fits = median_order_notional <= eff_cap and qty >= p["min_contracts"]

            # ---- cap-BLIND portfolio (headline reproduction) ----
            def combine(rowsrc):
                comb = defaultdict(float)
                for e in edges:
                    for d, v in by_day(rowsrc(e)).items():
                        comb[d] += v
                return dict(comb)

            blind_rows = {}
            for e in edges:
                blind_rows[e], _ = simulate_set(sig[e], spy, ribbon, vix,
                                                strike_offset=off, qty=qty, setup=setup_name[e])
            blind_combined = combine(lambda e: blind_rows[e])
            blind_agg = portfolio_aggregate(blind_combined, n_trading_days)

            # ---- cap-AWARE (realizable) portfolio ----
            aware_combined = combine(lambda e: edge_admit_rows[e])
            aware_agg = portfolio_aggregate(aware_combined, n_trading_days)

            corr_blind = corr_matrix({e: blind_rows[e] for e in edges})
            corr_aware = corr_matrix({e: edge_admit_rows[e] for e in edges})

            results[acct]["tiers"][tname] = {
                "strike_offset": off,
                "median_entry_premium_all_edges": round(med_all, 3),
                "median_order_notional": round(median_order_notional, 2),
                "median_order_fits_cap": bool(median_fits),
                "standalone_capblind": edge_blind,
                "standalone_capaware": edge_capaware,
                "portfolio_capblind": blind_agg,
                "portfolio_capaware": aware_agg,
                "corr_capblind": corr_blind,
                "corr_capaware": corr_aware,
            }
            print(f"[b9cap]   {acct} {tname:5s} off={off:+d}: med_prem=${med_all:.3f} "
                  f"med_notional=${median_order_notional:.0f} fits={median_fits} "
                  f"| blind=${blind_agg['total_dollar']} -> aware=${aware_agg['total_dollar']} "
                  f"(Sharpe {blind_agg['annualized_sharpe']}->{aware_agg['annualized_sharpe']}, "
                  f"maxDD ${blind_agg['max_drawdown']}->${aware_agg['max_drawdown']})", flush=True)

        # affordable tier = richest tier whose median order fits (ITM-2 > ATM > OTM-1 > OTM-2)
        richness = ["ITM-2", "ATM", "OTM-1", "OTM-2"]
        affordable = next((t for t in richness
                           if results[acct]["tiers"][t]["median_order_fits_cap"]), None)
        results[acct]["affordable_tier"] = affordable
        print(f"[b9cap] {acct} AFFORDABLE TIER (richest that fits) = {affordable}", flush=True)

    summary = {
        "campaign": "B9-CAP — cap-aware re-score of the 3-edge VWAP portfolio (realizable book)",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}", "trading_days": n_trading_days,
        "fills_authority": "real OPRA via lib.simulator_real (C1); cap via lib.cap_admission (risk_gate.check_order)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "config": {"premium_stop_pct": PREMIUM_STOP_PCT, "exits": "v15 default",
                   "vix_regime_config": vix_cfg, "tiers_tested": TIERS,
                   "accounts": {a: {"equity": c["equity"], "qty": c["qty"],
                                    "edges": list(c["edges"])} for a, c in ACCOUNTS.items()}},
        # DERIVED from THIS run's own cap-blind books at the ACTUAL per-account qty
        # (Safe-2 qty3 / Bold qty5) — never hardcode a literal here. The prior `18784` was the
        # qty=3 Bold ITM-2 figure, but Bold runs qty=5 (cap-blind ITM-2 ~$33,013), so a "haircut"
        # read off the literal compared qty3-blind vs qty5-aware and OVERSTATED it (B9 flag #1,
        # fixed 2026-06-22). Deriving makes the baseline qty-consistent by construction.
        "capblind_headlines_being_rescored": {
            "Safe-2_ATM_1+2+4": results["Safe-2"]["tiers"]["ATM"]["portfolio_capblind"]["total_dollar"],
            "Bold_ITM-2_1+2": results["Bold"]["tiers"]["ITM-2"]["portfolio_capblind"]["total_dollar"],
            "diversification_daily_corr_e2_e4": 0.076},
        "results": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b9cap] wrote {OUT_JSON}", flush=True)

    # ---- console verdict ----
    print("\n=== B9 CAP-AWARE VERDICT ===")
    for acct in ACCOUNTS:
        r = results[acct]
        aff = r["affordable_tier"]
        print(f"\n{acct}: equity=${r['equity']:.0f} qty={r['qty']} "
              f"effective_cap=${r['effective_cap_dollar']:.0f} "
              f"max_prem/contract=${r['max_premium_per_contract']:.3f}")
        for t in ("OTM-2", "OTM-1", "ATM", "ITM-2"):
            td = r["tiers"][t]
            mark = " <== AFFORDABLE" if t == aff else ""
            print(f"  {t:6s} med_prem=${td['median_entry_premium_all_edges']:.3f} "
                  f"med_notional=${td['median_order_notional']:.0f} "
                  f"fits={td['median_order_fits_cap']}  "
                  f"blind=${td['portfolio_capblind']['total_dollar']} "
                  f"aware=${td['portfolio_capaware']['total_dollar']} "
                  f"(Sh {td['portfolio_capblind']['annualized_sharpe']}->"
                  f"{td['portfolio_capaware']['annualized_sharpe']}, "
                  f"DD ${td['portfolio_capaware']['max_drawdown']}){mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
