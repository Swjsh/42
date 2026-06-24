"""VOLRANKER SIZING overlay on the 1DTE/dollar-stop #1 stream — QUARTER-KELLY BASE variant.

THE QUESTION (the VOLRANKER-SIZING-1DTE-SCORECARD's primary NEXT DIRECTION #1, verbatim):
  "re-run this overlay with base = quarter-Kelly contracts (B10's contracts_from_fraction(
   f_quarter_kelly, ...)) instead of base = min-3 ... so that bot x0.6 lands at a count
   strictly above 3 and top x1.5 lands higher still — a true two-sided modulation around a
   >3 base, with the min-3 floor as a never-violated backstop rather than the operating point."

WHY this is the precise fix. On the 1DTE stream the overnight-vol tercile overlay came back
MARGINAL: a clean $2K cap-bound RISK tool, but at $10K/$25K it collapsed to UP-ONLY because the
overlay multiplied the *min-3 implied* equity fraction (~7.5% of $10K) and bot x0.6 of that still
rounded ABOVE the min-3 floor -> no down-sizing arm -> a variance trade, not a risk-adjusted lift.
The structural blocker was located precisely: the min-3 floor is the operating point at scale.
This harness swaps the BASE off the min-3 floor and onto quarter-Kelly, the one change that could
give the overlay real TWO-SIDED room at $10K+.

WHAT THIS REUSES BYTE-FOR-BYTE (research-only, $0; NO watcher/params/risk_gate/heartbeat/
simulator_real edit, NO orders, NO commit):
  - the 1DTE/dollar-stop trade stream: _volranker_sizing_1dte.build_1dte_dollarstop_T (which itself
    reuses _dte_stop_construction + _dte_expansion_sim byte-for-byte: real per-DTE OPRA fills +
    honest overnight gap + expiry settlement).
  - the overlay run_cell / metrics / improvement verdict / causal terciles: _volranker_sizing.*
    (NOT re-implemented — imported and called; the overlay arithmetic is untouched).
  - the overnight-vol tercile feature: _deploytiming_overnight_vol.overnight_vol_by_day.
  - the quarter-Kelly fraction: _b10_sizing.{trade_return_stats, kelly_fraction} (continuous m/v
    capped at the discrete two-outcome Kelly, then /4 — the SAME fraction B10's ship-spec uses).
  - the Rule-6 clamp: _b10_sizing.contracts_from_fraction (per-trade cap + min-3 floor).

THE ONLY CHANGE vs _volranker_sizing_1dte: the overlay/flat BASE FRACTION is swapped from the
min-3-implied fraction to f_quarter_kelly. Implemented by REBINDING two module globals on
_volranker_sizing for the duration of each account's run — _base_fraction (the overlay's base) and
flat_contracts (the FLAT baseline) — to quarter-Kelly versions. This is the SAME module-global
rebind pattern the production module already uses for its --sweep TERCILE_MULT; run_cell,
overlay_contracts, _geometric_growth and _improvement_verdict are reused entirely unchanged, so no
overlay/metric arithmetic is duplicated (C14: one source of truth).

OOS-HONESTY: f_quarter_kelly is computed on the IS (2025) slice ONLY and applied frozen to the
full + OOS books (the "what you would have set going in" fraction — no OOS leak into the size).
The tercile cuts are already causal (trailing-60d window, shift-1). The comparison is overlay
(QK base x terciles) vs FLAT (QK base, no terciles) — isolating whether the overnight-vol tercile
MODULATION adds risk-adjusted value once freed from the min-3-floor confound. The COMPOUNDING case
is the $10K/$25K cells; OOS-2026 must ALSO improve risk-adjusted (not just IS lever-up).

Pure Python, $0. No live orders. Markets closed. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_volranker_sizing_qk.py
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

# Overlay logic + metrics + verdict + terciles — byte-for-byte (imported, NOT re-implemented).
import autoresearch._volranker_sizing as VR  # noqa: E402  (we rebind two globals on this module)
from autoresearch._volranker_sizing import (  # noqa: E402
    causal_terciles, run_cell, _improvement_verdict, _split_is_oos,
    TERCILE_MULT, OOS_YEAR, MIN_WARMUP, TRAIL_WIN,
)
from autoresearch._volranker_sizing import ACCOUNTS as VR_ACCOUNTS  # noqa: E402
# 1DTE/dollar-stop stream builder — byte-for-byte.
from autoresearch._volranker_sizing_1dte import (  # noqa: E402
    build_1dte_dollarstop_T, _prem_stats, DTE, EQUITY_LEVELS, ACCT_TIER,
)
# Overnight-vol tercile feature — byte-for-byte.
from autoresearch._deploytiming_overnight_vol import (  # noqa: E402
    overnight_vol_by_day, OPRA_CACHE_LAST,
)
# Quarter-Kelly fraction + the Rule-6 clamp — byte-for-byte from B10.
from autoresearch._b10_sizing import (  # noqa: E402
    trade_return_stats, kelly_fraction, contracts_from_fraction as b10_cff,
)
# Stream machinery (same as _volranker_sizing_1dte).
from autoresearch._dte_stop_construction import (  # noqa: E402
    calibrate, FAMILIES_EXT, TIERS, _load_spy_vix,
)
from autoresearch._dte_expansion_sim import (  # noqa: E402
    _spy_day_open_close, _build_expiry_index,
)
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "volranker-sizing-qk.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "VOLRANKER-SIZING-QK-SCORECARD.md"


# ─────────────────────────────────────────────────────────────────────────────
# QUARTER-KELLY BASE rebind — the ONLY change vs the min-3 harness.
# ─────────────────────────────────────────────────────────────────────────────
def _make_base_qk(f_qk: float):
    """Overlay base fraction = f_quarter_kelly (constant). overlay_contracts then does
    target_frac = f_qk * TERCILE_MULT[tercile], clamped through the SAME Rule-6 clamp
    (per-trade cap + min-3 floor + never-zero). Signature matches VR._base_fraction."""
    def _base(equity, premium, *, per_trade_cap_frac, min_contracts):
        return f_qk
    return _base


def _make_flat_qk(f_qk: float):
    """FLAT baseline contract count at the quarter-Kelly fraction (mult 1.0), clamped to
    Rule-6. Returns 0 when even min-3 breaches the per-trade cap (the SAME shared skip the
    overlay applies). Signature matches VR.flat_contracts (returns int)."""
    def _flat(equity, premium, *, per_trade_cap_frac, min_contracts):
        if premium <= 0:
            return 0
        r = b10_cff(f_qk, equity, premium, per_trade_cap_frac=per_trade_cap_frac,
                    min_contracts=min_contracts)
        return int(r.get("contracts", 0))
    return _flat


def _qk_fraction_is(trades_cls, terciles) -> tuple[float, dict, dict]:
    """Compute quarter-Kelly on the IS (2025) slice ONLY (no OOS leak into the size).
    Returns (f_qk, kelly_dict, is_trade_return_stats)."""
    is_t, _ = _split_is_oos(trades_cls)
    stats = trade_return_stats(is_t)         # reads .pct + .entry_premium (volranker T has both)
    kelly = kelly_fraction(stats)
    return float(kelly["f_quarter_kelly"]), kelly, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="build streams + print f_qk + floor-room diagnostics, no scorecard write")
    args = ap.parse_args()

    print("[vr-qk] loading SPY+VIX + #1 detector + MES overnight ...", flush=True)
    spy, vix = _load_spy_vix()
    day_open_close = _spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    _build_expiry_index(DTE)

    detect = FAMILIES_EXT["vwap_continuation"]
    signals = detect(days, vix, spy, ribbon)
    print(f"[vr-qk] vwap_continuation signals={len(signals)}", flush=True)

    onv = overnight_vol_by_day()
    mes_last = onv.index.max()
    join_cutoff = min(OPRA_CACHE_LAST, mes_last)
    terciles = causal_terciles(onv, join_cutoff=join_cutoff)
    tc = defaultdict(int)
    for v in terciles.values():
        tc[v] += 1
    print(f"[vr-qk] overnight-vol days={len(onv)} join_cutoff={join_cutoff} "
          f"terciles={dict(tc)}", flush=True)

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
        is_t, oos_t = _split_is_oos(trades_cls)
        pstats = _prem_stats(trades_cls)
        f_qk, kelly, is_ret_stats = _qk_fraction_is(trades_cls, terciles)
        cap = acct["per_trade_cap_frac"]
        print(f"\n[vr-qk] === {acct_name} (tier={tier} off={tier_offset:+d} "
              f"dollar_stop=${dollar_thresh}) === 1DTE trades={len(trades)} "
              f"classifiable={len(trades_cls)} | IS={len(is_t)} OOS={len(oos_t)} | "
              f"median_prem=${pstats.get('median_premium')} | f_qk={f_qk} "
              f"(full={kelly['f_full_kelly']}, IS WR={is_ret_stats.get('win_rate')})", flush=True)

        if args.smoke:
            mp = pstats.get("median_premium", 0.0)
            for eq in EQUITY_LEVELS:
                # QK-base contract count at median premium, and the bot/top modulated counts.
                base_c = b10_cff(f_qk, eq, mp, per_trade_cap_frac=cap, min_contracts=3)["contracts"]
                bot_c = b10_cff(f_qk * TERCILE_MULT["bot"], eq, mp, per_trade_cap_frac=cap,
                                min_contracts=3)["contracts"]
                top_c = b10_cff(f_qk * TERCILE_MULT["top"], eq, mp, per_trade_cap_frac=cap,
                                min_contracts=3)["contracts"]
                two_sided = bot_c < base_c < top_c
                print(f"    @ ${int(eq):>6}: QK base={base_c}c  bot={bot_c}c  top={top_c}c  "
                      f"two_sided_room={'YES' if two_sided else 'NO'} "
                      f"(cap {int(cap*100)}%, min-3 floor)", flush=True)
            continue

        per_equity = {}
        # Rebind the base + flat to the quarter-Kelly versions for THIS account, run, then restore.
        orig_base, orig_flat = VR._base_fraction, VR.flat_contracts
        VR._base_fraction = _make_base_qk(f_qk)
        VR.flat_contracts = _make_flat_qk(f_qk)
        try:
            for eq in EQUITY_LEVELS:
                full_cell = run_cell(trades_cls, terciles, account=acct, equity=eq)
                is_cell = run_cell(is_t, terciles, account=acct, equity=eq)
                oos_cell = run_cell(oos_t, terciles, account=acct, equity=eq)
                full_v = _improvement_verdict(full_cell)
                oos_v = _improvement_verdict(oos_cell)
                clean = bool(full_v["IMPROVES"] and oos_v["risk_adjusted_up"]
                             and oos_v["respects_caps"])
                per_equity[str(int(eq))] = {
                    "full": {"cell": full_cell, "verdict": full_v},
                    "IS_2025": {"cell": is_cell, "verdict": _improvement_verdict(is_cell)},
                    "OOS_2026": {"cell": oos_cell, "verdict": oos_v},
                    "OOS_HONEST_CLEAN": clean,
                }
                fp, op = full_cell["flat3"], full_cell["overlay"]
                print(f"  ${int(eq):>6} | FLAT(QK) tot=${fp['per_day']['total']:>10} "
                      f"shTr={fp['per_trade'].get('sharpe')} sortDay={fp['per_day'].get('sortino_day')} "
                      f"maxDD={fp['compounding']['max_dd_frac']}", flush=True)
                print(f"  ${int(eq):>6} |  OV(QK)  tot=${op['per_day']['total']:>10} "
                      f"shTr={op['per_trade'].get('sharpe')} sortDay={op['per_day'].get('sortino_day')} "
                      f"maxDD={op['compounding']['max_dd_frac']} | caps_ok="
                      f"{full_cell['cap_respect']['RESPECTS_CAPS']} IMPROVES={full_v['IMPROVES']} "
                      f"OOS_clean={clean} | avgQty_by_terc={op['avg_qty_by_tercile']} "
                      f"qty_hist={op['qty_hist'].get('overlay')}", flush=True)
        finally:
            VR._base_fraction, VR.flat_contracts = orig_base, orig_flat

        results[acct_name] = {
            "tier": tier, "strike_offset": tier_offset, "dollar_stop_thresh": dollar_thresh,
            "premium_stats": pstats, "f_quarter_kelly_IS": f_qk, "kelly_IS": kelly,
            "is_return_stats": is_ret_stats,
            "n_trades": len(trades), "n_classifiable": len(trades_cls),
            "n_IS": len(is_t), "n_OOS": len(oos_t), "coverage": cov, "per_equity": per_equity,
        }

    if args.smoke:
        print("\n[vr-qk] smoke done (f_qk + floor-room diagnostics only).")
        return 0

    # ── VERDICT roll-up (same bar as the min-3 harness) ──────────────────────
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
    zeroes = sum(results[a]["per_equity"][str(int(eq))]["full"]["cell"]["cap_respect"]
                 ["overlay_zeroed_flat_takeable"]
                 for a in results for eq in EQUITY_LEVELS)

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
        "slug": "overnight-vol-sizing-overlay-1dte-QUARTER-KELLY-BASE",
        "kind": "sizing_overlay (NOT a gate; L174-safe) — QUARTER-KELLY base instead of min-3 base",
        "run_date": dt.date.today().isoformat(),
        "the_question": ("does swapping the overlay BASE from min-3 to quarter-Kelly give the "
                         "overnight-vol tercile overlay genuine TWO-SIDED room (down-size bot days "
                         "AND headroom on top days) at $10K/$25K, so it becomes a COMPOUNDING lever "
                         "rather than the min-3-floor-bound UP-ONLY variance trade the 1DTE min-3 "
                         "harness found? (VOLRANKER-SIZING-1DTE-SCORECARD NEXT DIRECTION #1.)"),
        "edge": "vwap_continuation (LIVE #1), CALL+PUT, real per-DTE OPRA fills (C1)",
        "stream": "WP-8 1DTE / DOLLAR-STOP (Safe-2 ATM/$35.88, Bold ITM-2/$67.68) — byte-for-byte",
        "base_change": ("BASE fraction swapped min-3 -> f_quarter_kelly (B10 continuous-Kelly capped "
                        "at discrete, /4), computed on the IS-2025 slice only and frozen for OOS"),
        "overnight_feature": "sum(|MES 1m logret|) over 18:00->09:30 ET (W-track def, byte-for-byte)",
        "tercile_multipliers": TERCILE_MULT,
        "tercile_mechanism": (f"causal: day's overnight_rv vs PRIOR {TRAIL_WIN}d window (shift-1); "
                              f"cuts = 1/3 & 2/3 quantiles; <{MIN_WARMUP} priors -> BASE (no guess)"),
        "join_cutoff": str(join_cutoff), "tercile_counts": dict(tc),
        "equity_levels": list(EQUITY_LEVELS),
        "the_bar": ("overlay must (1) improve risk-adjusted return (per-trade Sharpe OR per-day "
                    "Sharpe/Sortino UP, OR maxDD DOWN at eq-or-better total) vs FLAT-QK on the SAME "
                    "stream, (2) RESPECT Rule-6 caps (0 breaches), (3) NEVER zero a takeable day "
                    "(L174; 0 zero-days), (4) OOS-honest (OOS-2026 also improves risk-adjusted). "
                    "COMPOUNDING case = $10K/$25K."),
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
            "MARGINAL": "helps somewhere but NOT OOS-clean at $10K/$25K scale",
            "NO_IMPROVEMENT": "caps respected, no zero days, but no risk-adjusted lift (inert)",
            "DEAD": "breaches caps or zeroes takeable days (broken overlay)",
        },
        "DISCLOSURE": {
            "overlay_logic": "BYTE-FOR-BYTE _volranker_sizing.{run_cell, overlay_contracts, "
                             "_improvement_verdict, causal_terciles}; only the BASE fraction rebound",
            "base_rebind": ("VR._base_fraction + VR.flat_contracts rebound to quarter-Kelly per "
                            "account (the established module-global rebind pattern, cf. --sweep "
                            "TERCILE_MULT); restored after each account"),
            "kelly": "f_quarter_kelly = _b10_sizing.kelly_fraction(trade_return_stats(IS_trades)); "
                     "continuous m/v capped at discrete two-outcome, /4 — conservative",
            "oos_honesty": "f_qk computed on IS-2025 ONLY, frozen for OOS; FLAT baseline is QK-flat "
                           "(mult 1.0), so the verdict isolates the TERCILE modulation, not the "
                           "Kelly level (B10 already covered the level)",
            "caps": "Rule-6 clamp = _b10_sizing.contracts_from_fraction; audited 0 breaches; never-zero",
            "research_only": "no watcher/params/risk_gate/heartbeat edit, no orders, no commit",
            "spy_vs_option": "C3/L58 — overnight-FLOW ranker validated on the OPTION P&L",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _write_md(summary)
    print(f"\n[vr-qk] wrote {OUT_JSON}\n[vr-qk] wrote {OUT_MD}", flush=True)
    print("\n=== VOLRANKER SIZING QUARTER-KELLY-BASE VERDICT ===")
    print(f"VERDICT: {verdict}")
    print(f"  $10K improves={improves_10k} OOS-clean={clean_10k} | "
          f"$25K improves={improves_25k} OOS-clean={clean_25k} | "
          f"$2K improves={improves_2k} | caps_ok={caps_ok} zero_days={zeroes}")
    return 0


def _write_md(s: dict) -> None:
    L = []
    L.append("# VOLRANKER SIZING overlay — QUARTER-KELLY BASE (the 1DTE NEXT-DIRECTION #1 test)\n")
    L.append(f"**Run:** {s['run_date']} (after-hours research, $0, no live edit)")
    L.append(f"**Slug:** `{s['slug']}`")
    L.append(f"**Harness:** `backtest/autoresearch/_volranker_sizing_qk.py`")
    L.append(f"**Output JSON:** `analysis/recommendations/volranker-sizing-qk.json`\n")
    L.append(f"## VERDICT: **{s['verdict']}**\n")
    L.append(f"> {s['the_question']}\n")
    L.append(f"- **Base change:** {s['base_change']}")
    L.append(f"- **Stream:** {s['stream']}")
    L.append(f"- **Tercile multipliers:** {s['tercile_multipliers']}")
    rr = s["verdict_rollup"]
    L.append(f"- **Roll-up:** improves $2K={rr['improves_2k']} | $10K improves={rr['improves_10k']} "
             f"OOS-clean={rr['oos_clean_10k']} | $25K improves={rr['improves_25k']} "
             f"OOS-clean={rr['oos_clean_25k']} | caps_ok={rr['caps_respected_all_cells']} "
             f"zero_days={rr['overlay_zeroed_takeable_days_total']}\n")
    for acct_name, b in s["accounts"].items():
        L.append(f"## {acct_name} — {b['tier']} (off {b['strike_offset']:+d}, "
                 f"$-stop ${b['dollar_stop_thresh']})\n")
        k = b["kelly_IS"]
        L.append(f"- **f_quarter_kelly (IS-2025):** {b['f_quarter_kelly_IS']} "
                 f"(full={k['f_full_kelly']}, continuous={k['f_continuous']}, discrete={k['f_discrete']})")
        L.append(f"- **stream:** {b['n_classifiable']} classifiable 1DTE trades "
                 f"(IS={b['n_IS']} / OOS={b['n_OOS']}), median premium "
                 f"${b['premium_stats'].get('median_premium')}\n")
        L.append("| equity | FLAT(QK) total | OV(QK) total | FLAT shTr | OV shTr | FLAT sortDay | "
                 "OV sortDay | FLAT maxDD | OV maxDD | IMPROVES | OOS-clean | overlay qty hist |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for eq in s["equity_levels"]:
            pe = b["per_equity"][str(int(eq))]
            fc, oc = pe["full"]["cell"]["flat3"], pe["full"]["cell"]["overlay"]
            v = pe["full"]["verdict"]
            L.append(f"| ${int(eq)} | {fc['per_day']['total']} | {oc['per_day']['total']} | "
                     f"{fc['per_trade'].get('sharpe')} | {oc['per_trade'].get('sharpe')} | "
                     f"{fc['per_day'].get('sortino_day')} | {oc['per_day'].get('sortino_day')} | "
                     f"{fc['compounding']['max_dd_frac']} | {oc['compounding']['max_dd_frac']} | "
                     f"{v['IMPROVES']} | {pe['OOS_HONEST_CLEAN']} | "
                     f"{oc['qty_hist'].get('overlay')} |")
        L.append("")
    L.append("## Disclosure\n")
    for kk, vv in s["DISCLOSURE"].items():
        L.append(f"- **{kk}:** {vv}")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
