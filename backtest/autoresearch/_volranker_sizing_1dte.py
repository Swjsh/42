"""VOLRANKER SIZING OVERLAY on the WP-8 1DTE/DOLLAR-STOP #1 stream (the DEPLOYED config).

slug = overnight-vol-sizing-overlay-1dte  |  kind = sizing_overlay (NOT a gate, NOT a new signal)

THE STRUCTURAL FIX this tests. The overnight-vol tercile SIZING overlay (`_volranker_sizing.py`)
on the 0DTE #1 vwap_continuation stream came back MARGINAL: a clean OOS-verified RISK tool at
$2K (sizes DOWN on low-vol days) but INERT at $10K+ because the min-3-contract floor pins flat-3
at exactly 3 contracts (3 lots ~= 4% of $10K, far below quarter-Kelly) -> NO down-sizing room ->
the overlay cannot move the book at scale.

THE DEPLOYED config is WP-8's 1DTE / DOLLAR-STOP (Safe-2 ATM/$35.88, Bold ITM-2/$67.68), whose
1DTE contracts carry HIGHER premium (~1.5x the 0DTE: ATM ~$2.34 vs 0DTE ~$1.38; ITM-2 ~$3.06 vs
0DTE ~$2.55) -> 3 contracts is a BIGGER % of equity -> the min-3 floor binds LESS -> the ranker
gets REAL down-sizing room at $10K+, where it could become a genuine COMPOUNDING lever instead of
a $2K-only risk-tool. THE KEY QUESTION: does the higher 1DTE premium give the floor enough room
that the overlay now improves risk-adjusted return at $10K/$25K (the compounding case the 0DTE
stream structurally blocked)?

WHAT THIS REUSES BYTE-FOR-BYTE (Sunday SAFE-research guard -- NO watcher/params/risk_gate/
orchestrator/heartbeat/simulator_real edits, NO orders, NO commit; RESEARCH SIM ONLY):
  - the OVERLAY logic, byte-for-byte: `_volranker_sizing.{causal_terciles, overlay_contracts,
    flat_contracts, run_cell, _improvement_verdict, _trade_dollar, ACCOUNTS, TERCILE_MULT,
    OOS_YEAR, MIN_WARMUP, TRAIL_WIN, _split_is_oos}`. NOT re-implemented -- imported and called.
  - the overnight-vol tercile feature, byte-for-byte: `_deploytiming_overnight_vol.
    overnight_vol_by_day` + `OPRA_CACHE_LAST` (the EXACT W-track def: sum|MES 1m logret| over
    18:00->09:30 ET, causal).
  - the Rule-6 cap-clamp, byte-for-byte: `_b10_sizing.contracts_from_fraction` (via the overlay).
  - the 1DTE/DOLLAR-STOP trade stream, byte-for-byte: `_dte_stop_construction.{run_cell as
    dte_run_cell, calibrate, simulate_dte_trade_stop}` + the validated `_dte_expansion_sim`
    machinery (per-DTE OPRA loader, expiry index, overnight gap, expiry settlement). The dollar
    threshold is the SAME calibrated $/tier the WP-8 ship-spec uses (re-derived from the 0DTE -8%
    run at this tier -- NOT refit here).

THE ONLY NEW CODE: the bridge that (1) builds the 1DTE/dollar-stop DteFill stream per tier,
(2) converts each DteFill -> the volranker `T` shape (pct=pct_return qty-invariant, pnl3=
dollar_pnl at the base qty-3, entry_premium=entry_premium), (3) feeds it through the IDENTICAL
overlay run_cell at $2K/$10K/$25K. NO overlay arithmetic is duplicated -- the swap is the stream.

THE BAR (same as `_volranker_sizing.py`): SIZING_IMPROVEMENT if the overlay
  (1) IMPROVES risk-adjusted return (per-trade Sharpe OR per-day Sharpe/Sortino UP, OR maxDD
      DOWN at equal-or-better total) vs FLAT-3 on the SAME 1DTE/dollar-stop stream,
  (2) RESPECTS the Rule-6 caps (per-trade cap + min-3; verified 0 breaches),
  (3) NEVER zeroes a takeable day (L174-safe: bottom-tercile reduced, not removed),
  (4) OOS-honest (IS/OOS split; OOS-2026 must ALSO improve risk-adjusted, not just IS lever-up).
The COMPOUNDING-CASE question is specifically the $10K/$25K cells (the 0DTE stream blocked these).

Pure Python, $0. No live orders. Markets closed (Sunday). Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_volranker_sizing_1dte.py [--smoke]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# ── Overlay logic — byte-for-byte from _volranker_sizing (imported, NOT re-implemented).
from autoresearch._volranker_sizing import (  # noqa: E402
    T, causal_terciles, run_cell, _improvement_verdict, _split_is_oos,
    TERCILE_MULT, OOS_YEAR, MIN_WARMUP, TRAIL_WIN,
)
from autoresearch._volranker_sizing import ACCOUNTS as VR_ACCOUNTS  # noqa: E402
# ── Overnight-vol tercile feature — byte-for-byte from the W-track.
from autoresearch._deploytiming_overnight_vol import (  # noqa: E402
    overnight_vol_by_day, OPRA_CACHE_LAST,
)
# ── 1DTE / dollar-stop trade stream — byte-for-byte from the DTE-stop campaign machinery.
from autoresearch._dte_stop_construction import (  # noqa: E402
    run_cell as dte_run_cell, calibrate, FAMILIES_EXT, TIERS, LIVE_TIER,
    _load_spy_vix, BASELINE_PCT,
)
from autoresearch._dte_expansion_sim import (  # noqa: E402
    _spy_day_open_close, _build_expiry_index,
)
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "volranker-sizing-1dte.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "VOLRANKER-SIZING-1DTE-SCORECARD.md"

DTE = 1                                   # the WP-8 deployed config is 1DTE
EQUITY_LEVELS = (2000.0, 10000.0, 25000.0)   # prompt: $2K, $10K, $25K

# Per-account tier for the 1DTE/dollar-stop stream (CLAUDE.md account context, == WP-8 ship-spec):
#   Safe-2 -> ATM (offset 0), dollar-stop calibrated $35.88
#   Bold   -> ITM-2 (offset -2), dollar-stop calibrated $67.68
# The cap/min/kill come byte-for-byte from the volranker ACCOUNTS (Rule 5/6).
ACCT_TIER = {"Safe-2": "ATM", "Bold": "ITM-2"}


# ─────────────────────────────────────────────────────────────────────────────
# BRIDGE — build the 1DTE/dollar-stop stream per tier, convert DteFill -> volranker T.
# This is the ONLY new arithmetic; the overlay run_cell consumes T exactly as on the 0DTE stream.
# ─────────────────────────────────────────────────────────────────────────────
def build_1dte_dollarstop_T(signals, spy, day_open_close, *, tier_offset,
                            dollar_thresh, edge_tag) -> tuple[list[T], dict, float]:
    """Run the 1DTE/dollar-stop cell (real per-DTE OPRA fills + overnight gap + expiry
    settlement) and convert each DteFill -> the volranker T shape.

    T.pct = DteFill.pct_return (qty-invariant return-on-premium, the unit the overlay scales by);
    T.pnl3 = DteFill.dollar_pnl (at the base qty-3 the DTE sim uses -- the FLAT-3 reference $);
    T.entry_premium = DteFill.entry_premium (capital-deployed per contract -- drives the floor).
    """
    cell = dte_run_cell(signals, spy, day_open_close, DTE, strike_offset=tier_offset,
                        construction="dollar", stop_param=dollar_thresh)
    rows: list[T] = []
    for f in cell.rows:
        if f.entry_premium <= 0:
            continue
        rows.append(T(
            date=f.date, side=f.side, edge=edge_tag,
            entry_premium=round(float(f.entry_premium), 4),
            pct=round(float(f.pct_return), 6),
            pnl3=round(float(f.dollar_pnl), 2),
            exit_reason=f.exit_reason))
    return rows, cell.cov, dollar_thresh


def _prem_stats(trades: list[T]) -> dict:
    if not trades:
        return {"n": 0}
    p = np.array([t.entry_premium for t in trades], float)
    return {"n": len(p), "median_premium": round(float(np.median(p)), 4),
            "mean_premium": round(float(np.mean(p)), 4),
            "min_premium": round(float(p.min()), 4), "max_premium": round(float(p.max()), 4)}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="build streams + print floor-room diagnostics, no full scorecard write")
    args = ap.parse_args()

    print("[vr-1dte] loading SPY+VIX + #1 detector + MES overnight ...", flush=True)
    spy, vix = _load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    _build_expiry_index(DTE)   # 1DTE expiry index

    # #1 vwap_continuation detector — byte-for-byte (the DTE-stop family registry holds it).
    detect = FAMILIES_EXT["vwap_continuation"]
    signals = detect(days, vix, spy, ribbon)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[vr-1dte] vwap_continuation signals={len(signals)} on {sig_days} days "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    # Overnight-vol terciles — byte-for-byte (W-track def + causal tercile mechanism).
    onv = overnight_vol_by_day()
    mes_last = onv.index.max()
    join_cutoff = min(OPRA_CACHE_LAST, mes_last)
    terciles = causal_terciles(onv, join_cutoff=join_cutoff)
    tc = defaultdict(int)
    for v in terciles.values():
        tc[v] += 1
    print(f"[vr-1dte] overnight-vol days={len(onv)} join_cutoff={join_cutoff} "
          f"terciles={dict(tc)}", flush=True)

    # Calibrate the dollar threshold per tier (re-derived from the 0DTE -8% run at that tier,
    # frozen and applied at 1DTE -- the SAME calibration the WP-8 ship-spec uses; NOT refit).
    results = {}
    for acct_name, acct in VR_ACCOUNTS.items():
        tier = ACCT_TIER[acct_name]
        tier_offset = TIERS[tier]
        calib = calibrate(signals, spy, day_open_close, tier_offset)
        dollar_thresh = calib["dollar_thresh"]
        trades, cov, _ = build_1dte_dollarstop_T(
            signals, spy, day_open_close, tier_offset=tier_offset,
            dollar_thresh=dollar_thresh, edge_tag="e1")
        trades_cls = [t for t in trades if dt.date.fromisoformat(t.date) in terciles]
        n_drop = len(trades) - len(trades_cls)
        is_t, oos_t = _split_is_oos(trades_cls)
        pstats = _prem_stats(trades_cls)
        print(f"\n[vr-1dte] === {acct_name} (tier={tier} off={tier_offset:+d} "
              f"dollar_stop=${dollar_thresh}) === 1DTE trades={len(trades)} "
              f"classifiable={len(trades_cls)} (dropped {n_drop} post-MES-cutoff) | "
              f"IS={len(is_t)} OOS={len(oos_t)} | median_prem=${pstats.get('median_premium')}",
              flush=True)

        if args.smoke:
            # Floor-room diagnostic: at each equity, how big is FLAT-3 as % of equity (median prem)?
            # This is the structural lever -- larger % = more down-sizing room for the overlay.
            mp = pstats.get("median_premium", 0.0)
            cap = acct["per_trade_cap_frac"]
            for eq in EQUITY_LEVELS:
                cost3 = 3 * mp * 100.0
                frac3 = cost3 / eq
                print(f"    @ ${int(eq):>6}: FLAT-3 cost=${cost3:.0f} = {100*frac3:.1f}% of equity "
                      f"(cap {int(cap*100)}%); floor-room {'YES' if frac3 > 0.06 else 'tight'} "
                      f"(>6% => bot-tercile can size <3)", flush=True)
            continue

        per_equity = {}
        for eq in EQUITY_LEVELS:
            full_cell = run_cell(trades_cls, terciles, account=acct, equity=eq)
            is_cell = run_cell(is_t, terciles, account=acct, equity=eq)
            oos_cell = run_cell(oos_t, terciles, account=acct, equity=eq)
            full_v = _improvement_verdict(full_cell)
            oos_v = _improvement_verdict(oos_cell)
            # OOS honesty: full must improve AND OOS must also improve risk-adjusted (not IS lever-up)
            clean = bool(full_v["IMPROVES"] and oos_v["risk_adjusted_up"] and oos_v["respects_caps"])
            per_equity[str(int(eq))] = {
                "full": {"cell": full_cell, "verdict": full_v},
                "IS_2025": {"cell": is_cell, "verdict": _improvement_verdict(is_cell)},
                "OOS_2026": {"cell": oos_cell, "verdict": oos_v},
                "OOS_HONEST_CLEAN": clean,
            }
            fp, op = full_cell["flat3"], full_cell["overlay"]
            print(f"  ${int(eq):>6} | FLAT tot=${fp['per_day']['total']:>10} "
                  f"shTr={fp['per_trade'].get('sharpe')} shDay={fp['per_day'].get('sharpe_day')} "
                  f"sortDay={fp['per_day'].get('sortino_day')} maxDD={fp['compounding']['max_dd_frac']} "
                  f"grow={fp['compounding']['growth_mult']}x", flush=True)
            print(f"  ${int(eq):>6} |  OV  tot=${op['per_day']['total']:>10} "
                  f"shTr={op['per_trade'].get('sharpe')} shDay={op['per_day'].get('sharpe_day')} "
                  f"sortDay={op['per_day'].get('sortino_day')} maxDD={op['compounding']['max_dd_frac']} "
                  f"grow={op['compounding']['growth_mult']}x | caps_ok="
                  f"{full_cell['cap_respect']['RESPECTS_CAPS']} IMPROVES={full_v['IMPROVES']} "
                  f"OOS_clean={clean} | avgQty_by_terc={op['avg_qty_by_tercile']}", flush=True)

        results[acct_name] = {
            "tier": tier, "strike_offset": tier_offset, "dollar_stop_thresh": dollar_thresh,
            "calibration": calib, "premium_stats": pstats,
            "n_trades": len(trades), "n_classifiable": len(trades_cls),
            "n_dropped_post_mes": n_drop, "n_IS": len(is_t), "n_OOS": len(oos_t),
            "coverage": cov, "per_equity": per_equity,
        }

    if args.smoke:
        print("\n[vr-1dte] smoke done (floor-room diagnostics only).")
        return 0

    # ── VERDICT roll-up ──────────────────────────────────────────────────────
    def _imp(a, eq):
        return results[a]["per_equity"][str(int(eq))]["full"]["verdict"]["IMPROVES"]

    def _clean(a, eq):
        return results[a]["per_equity"][str(int(eq))]["OOS_HONEST_CLEAN"]

    improves_10k = any(_imp(a, 10000.0) for a in results)
    clean_10k = any(_clean(a, 10000.0) for a in results)
    improves_25k = any(_imp(a, 25000.0) for a in results)
    clean_25k = any(_clean(a, 25000.0) for a in results)
    improves_2k = any(_imp(a, 2000.0) for a in results)
    caps_ok = all(results[a]["per_equity"][str(int(eq))]["full"]["cell"]["cap_respect"]["RESPECTS_CAPS"]
                  for a in results for eq in EQUITY_LEVELS)
    # zero-day audit (L174) across all cells
    zeroes = sum(results[a]["per_equity"][str(int(eq))]["full"]["cell"]["cap_respect"]
                 ["overlay_zeroed_flat_takeable"]
                 for a in results for eq in EQUITY_LEVELS)

    # The COMPOUNDING case is the $10K/$25K cells. SIZING_IMPROVEMENT requires OOS-clean at scale.
    compounding_clean = clean_10k or clean_25k
    if compounding_clean:
        verdict = "SIZING_IMPROVEMENT"
    elif improves_10k or improves_25k or improves_2k:
        verdict = "MARGINAL"
    elif caps_ok and zeroes == 0:
        verdict = "NO_IMPROVEMENT"
    else:
        verdict = "DEAD"

    summary = {
        "slug": "overnight-vol-sizing-overlay-1dte",
        "kind": "sizing_overlay on the WP-8 1DTE/dollar-stop DEPLOYED config (NOT a gate; L174-safe)",
        "run_date": dt.date.today().isoformat(),
        "the_question": ("does the higher 1DTE premium give the min-3 floor enough room that the "
                         "overnight-vol sizing overlay now improves risk-adjusted return at "
                         "$10K/$25K -- the compounding case the 0DTE stream structurally blocked?"),
        "edge": "vwap_continuation (LIVE #1), CALL+PUT, real per-DTE OPRA fills (C1)",
        "deployed_config": ("WP-8 1DTE / DOLLAR-STOP: Safe-2 ATM/$35.88, Bold ITM-2/$67.68 "
                            "(dollar threshold = median 0DTE -8% loss at that tier, frozen at 1DTE)"),
        "overnight_feature": "sum(|MES 1m logret|) over 18:00->09:30 ET (W-track def, byte-for-byte)",
        "tercile_mechanism": (f"causal: day's overnight_rv vs PRIOR {TRAIL_WIN}d window (shift-1); "
                              f"cuts = 1/3 & 2/3 quantiles; <{MIN_WARMUP} priors -> BASE (no guess)"),
        "tercile_multipliers": TERCILE_MULT,
        "join_cutoff": str(join_cutoff),
        "mes_overnight_last": str(mes_last),
        "tercile_counts": dict(tc),
        "the_bar": ("sizing overlay must (1) improve risk-adjusted return (per-trade Sharpe OR "
                    "per-day Sharpe/Sortino UP, OR maxDD DOWN at eq-or-better return) vs FLAT-3 on "
                    "the SAME 1DTE/dollar-stop stream, (2) RESPECT Rule-6 caps (per-trade cap + "
                    "min-3; 0 breaches), (3) NEVER zero a takeable day (L174; 0 zero-days), "
                    "(4) OOS-honest (OOS-2026 also improves risk-adjusted, not just IS lever-up). "
                    "The COMPOUNDING case is the $10K/$25K cells."),
        "equity_levels": list(EQUITY_LEVELS),
        "accounts": results,
        "verdict": verdict,
        "verdict_rollup": {
            "improves_2k": improves_2k,
            "improves_10k": improves_10k, "oos_clean_10k": clean_10k,
            "improves_25k": improves_25k, "oos_clean_25k": clean_25k,
            "compounding_case_clean_at_scale": compounding_clean,
            "caps_respected_all_cells": caps_ok,
            "overlay_zeroed_takeable_days_total": zeroes,
        },
        "verdict_legend": {
            "SIZING_IMPROVEMENT": "OOS-honest risk-adjusted lift at $10K OR $25K (the compounding case)",
            "MARGINAL": "helps somewhere (often $2K risk-tool) but NOT OOS-clean at $10K/$25K scale",
            "NO_IMPROVEMENT": "caps respected, no zero days, but no risk-adjusted lift (inert)",
            "DEAD": "breaches caps or zeroes takeable days (broken overlay)",
        },
        "DISCLOSURE": {
            "overlay_logic": "BYTE-FOR-BYTE _volranker_sizing.{run_cell, overlay_contracts, "
                             "_improvement_verdict, causal_terciles}; only the trade stream swapped",
            "stream": ("1DTE/dollar-stop via _dte_stop_construction.run_cell(construction='dollar') -> "
                       "real per-DTE OPRA day-T bars + honest overnight gap + expiry intrinsic "
                       "settlement (inherited byte-for-byte from _dte_expansion_sim); converted to "
                       "the volranker T (pct=pct_return qty-invariant, pnl3=dollar_pnl@qty-3)"),
            "caps": "Rule-6 clamp = _b10_sizing.contracts_from_fraction (via overlay); audited 0 breaches",
            "never_zero": "overlay floors at >=1 where the cap fits; bottom-tercile reduced not removed (L174)",
            "calibration_note": ("dollar threshold re-derived from the 0DTE -8% run at each tier "
                                 "(Safe-2 $35.88, Bold $67.68), frozen and applied at 1DTE -- the SAME "
                                 "calibration the WP-8 ship-spec uses, NOT refit on the 1DTE stream"),
            "join_caveat": (f"classifiable days bounded by MES 1m (ends {mes_last}); 1DTE trades after "
                            f"that have no overnight tercile (dropped, disclosed) -- OPRA to {OPRA_CACHE_LAST}"),
            "fixed_equity_note": ("per-trade/per-day risk metrics at FIXED equity (so $ comparable, not "
                                  "confounded by the compounding path); growth/maxDD-frac from the replay"),
            "research_only": "Sunday money-path guard: no watcher/params/risk_gate/heartbeat edit, no orders, no commit",
            "spy_vs_option": "C3/L58 -- overnight-FLOW ranker validated on the OPTION P&L, not SPY/futures range",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[vr-1dte] wrote {OUT_JSON}", flush=True)
    print("\n=== VOLRANKER SIZING 1DTE VERDICT ===")
    print(f"VERDICT: {verdict}")
    print(f"  $10K improves={improves_10k} OOS-clean={clean_10k} | "
          f"$25K improves={improves_25k} OOS-clean={clean_25k} | "
          f"$2K improves={improves_2k} | caps_ok={caps_ok} zero_days={zeroes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
