"""CAP-AWARE re-validation overlay for the DTE x STOP-CONSTRUCTION matrix.

THE DEFECT (confirmed at code level — premise of this overlay):
  risk_gate.check_order enforces RISK_CAP against NOTIONAL = premium*qty*100, capped at the
  TIGHTER of per_trade_risk_cap_pct (Safe 0.30 / Bold 0.50) and the v15 per-tier max_pct table.
    * Safe-2 equity $2,000 -> effective cap = $600 (40% tier @ 0-2k binds the 30% risk cap? no:
      0.30*2000=600 vs 0.40*2000=800 -> RISK CAP 600 binds). MIN_CONTRACTS Safe = 3.
    * Bold equity ~$1,648 -> 0.50*1648 = $824 cap. MIN_CONTRACTS Bold = 5.
  simulator_real / the DTE harness have NO notional/buying-power cap -> the validated
  +$57.59/+$73.91 OOS exp ASSUMED qty-3 always fills. At the median 1DTE day the deployed cell
  is BLOCKED (qty3 1DTE notional > cap), so the live engine takes FEWER trades than the sim
  scored. QUANTIFY already confirmed: Safe block-rate 72.29%, cap-aware OOS exp 103.09 (on the
  trades that DO fit) vs the validated 57.59 (which counted blocked trades as if they filled).

THIS OVERLAY (the RE-VALIDATION):
  Sweep, PER ACCOUNT, the matrix
      strike tier {OTM-2 (+2), OTM-1 (+1), ATM (0), ITM-2 (-2)}
    x DTE {0, 1}
    x stop {dollar-anchored (re-derived per tier, C29), -8% percent}
    qty = 3 (Safe) / 5 (Bold, its min)
  ENFORCING the per-account notional cap + min_contracts PER TRADE exactly as live
  (risk_gate.check_order via pre_order_gate.check): a BLOCKED trade is EXCLUDED ($0), never
  auto-reduced (min_contracts denies, it does not shrink). Then run the FULL canonical bar on
  the cap-enforced trade set:
      gates 1-6,9 structural (_dte_stop_construction.clears_bar == _dte_expansion_sim.clears_bar)
      gate 7  DTE-aware random-entry null, ALSO cap-enforced (beat null MAX + drop-top5 > null MEAN)
      gate 8  no-truncation: same-tier chart-stop-only cap-enforced cell sign (is_truncation_artifact)
  -> the FULL 11-gate bar (per L172/L173/L171 + the structural 7).

GOAL (the question this answers): does a CHEAPER 1DTE strike (OTM-2 / OTM-1 1DTE) keep the
  theta-room doubling WHILE fitting qty-3 notional inside the $600 cap (1DTE premium <= $2.00/sh
  for Safe; <= $1.65/sh for Bold @ qty5)? Report best_safe_cell (affordable cell with highest
  OOS exp that CLEARS the 11-gate bar), its OOS exp, and whether it beats the ATM/0DTE/-8%
  affordable baseline (+$25/tr OOS). Same for Bold. HONEST: if NOTHING affordable clears + beats
  the baseline, say so -> the answer is stay at the 0DTE baseline.

REUSE (Sunday SAFE-research guard — NO watcher/params/risk_gate/orchestrator/heartbeat/
simulator_real edits, NO orders, NO commit; RESEARCH SIM ONLY):
  - run_cell / simulate_dte_trade_stop / calibrate / _book_metrics from _dte_stop_construction
    (real per-DTE OPRA fills, the #1 detector byte-for-byte, the pluggable stop construction).
  - metrics / clears_bar / OOS_YEAR / QTY / _strike_from_spot / _nearest_cached_strike_dte /
    simulate_dte_trade / Signal from _dte_expansion_sim (the validated DTE machinery).
  - dte_null (DTE-aware random-entry null) from _dte_library_survey, ADAPTED to take an explicit
    qty + the cap predicate so the null is cap-enforced apples-to-apples with the signal cell.
  - is_truncation_artifact from lib.truncation_guard (gate 8).
  - check_order (the LIVE cap) via pre_order_gate._params_for + lib.risk_gate.check_order — the
    SINGLE source of truth the live heartbeat calls. We call it; we never re-type the caps here.

Pure Python, $0. No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_dte_stop_cap_aware.py [--validate]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from autoresearch import _dte_expansion_sim as sim  # noqa: E402
from autoresearch._dte_expansion_sim import (  # noqa: E402
    OOS_YEAR,
    metrics as dte_metrics,
    clears_bar,
    simulate_dte_trade,
    Signal,
)
from autoresearch import _dte_stop_construction as dsc  # noqa: E402
from autoresearch._dte_stop_construction import (  # noqa: E402
    run_cell,
    calibrate,
    _book_metrics,
    FAMILIES_EXT,
)
from autoresearch.infinite_ammo_discovery import build_day_contexts, _strike_from_spot  # noqa: E402
from lib.truncation_guard import is_truncation_artifact  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
import pandas as pd  # noqa: E402

# The LIVE cap — the single source of truth. This overlay now FOLDS its cap logic into
# lib.cap_admission (the graduated order-ADMISSION layer), which calls risk_gate.check_order
# with the EXACT params the heartbeat uses — so cap-aware == live-risk by construction and
# there is ONE cap implementation (no re-typed literals). The old local _cap_allows /
# _enforce_cap are thin shims over the lib so the rest of this overlay is unchanged.
from lib.cap_admission import cap_allows as _lib_cap_allows, admit_book  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "dte-stop-cap-aware.json"

# Matrix axes (the task's grid).
TIERS = {"OTM-2": 2, "OTM-1": 1, "ATM": 0, "ITM-2": -2}   # strike_offset: pos=OTM, neg=ITM
DTES = (0, 1)
STOPS = ("dollar", "percent")          # dollar-anchored (re-derived per tier) + -8% percent
BASELINE_PCT = -0.08

# Per-account live config (qty = the account's min_contracts floor; equity from CLAUDE.md).
ACCOUNTS = {
    "safe": {"qty": 3, "equity": 2000.0},
    "bold": {"qty": 5, "equity": 1648.0},
}
NULL_SEEDS = 40
ENTRY_GATE = (dt.time(9, 35), dt.time(15, 50))

# The affordable baseline the best cell must beat (+$25/tr OOS over it): ATM / 0DTE / -8%.
BASELINE_CELL = {"tier": "ATM", "dte": 0, "stop": "percent"}
BEAT_MARGIN = 25.0


# ─────────────────────────────────────────────────────────────────────────────
# CAP PREDICATE — the live gate, per account. A trade fills iff check_order ALLOWS
# (qty @ entry_premium @ equity within the per-account notional cap + min_contracts).
# ─────────────────────────────────────────────────────────────────────────────
def _cap_allows(account: str, equity: float, qty: int, premium: float) -> bool:
    """True iff the LIVE risk_gate would ALLOW this (qty, premium) at this equity.

    Thin shim over lib.cap_admission.cap_allows (the single source of truth, which calls
    risk_gate.check_order with the heartbeat's sizing params). A denial here is the SAME
    denial the live engine would issue at order-build."""
    return _lib_cap_allows(account, equity, qty, premium)


def _enforce_cap(rows, account: str, equity: float, qty: int):
    """Filter a cell's DteFill rows to the trades the LIVE cap would actually FILL.

    Folded into lib.cap_admission.admit_book (the shared order-ADMISSION layer): a BLOCKED
    trade is EXCLUDED entirely ($0), exactly as live (min_contracts DENIES, never shrinks).
    Returns (kept_rows, block_rate, n_total) — the legacy tuple shape this overlay consumes."""
    res = admit_book(rows, account, equity, qty, enforce_cap=True)
    return list(res.admitted), res.block_rate, res.n_total


# ─────────────────────────────────────────────────────────────────────────────
# GATE 7 — DTE-aware random-entry null, CAP-ENFORCED. Adapted from _dte_library_survey.dte_null:
# draw random RTH bars on the cell's SAME entry days + SAME side mix, run the cell's
# strike/stop/DTE through simulate_dte_trade, then enforce the SAME per-account cap per drawn
# trade (a blocked random entry is excluded too — apples-to-apples with the signal cell).
# ─────────────────────────────────────────────────────────────────────────────
def _rth_idxs_for_day(spy, day: dt.date) -> list[int]:
    sub = spy[(spy["date"] == day) & (spy["t"] >= ENTRY_GATE[0]) & (spy["t"] <= ENTRY_GATE[1])]
    return [int(i) for i in sub.index.tolist()]


def cap_null(cell_rows, spy, day_open_close, dte, strike_offset, premium_stop_pct,
             account, equity, qty, seeds=NULL_SEEDS) -> dict:
    if not cell_rows:
        return {"per_trade_mean": 0.0, "per_trade_max": 0.0, "n_drawn": 0}
    days = sorted({dt.date.fromisoformat(r.date) for r in cell_rows})
    n_call = sum(1 for r in cell_rows if r.side == "C")
    n_put = sum(1 for r in cell_rows if r.side == "P")
    n_sig = len(cell_rows)
    day_idxs = {d: _rth_idxs_for_day(spy, d) for d in days}
    day_idxs = {d: ix for d, ix in day_idxs.items() if ix}
    elig_days = list(day_idxs)
    if not elig_days:
        return {"per_trade_mean": 0.0, "per_trade_max": 0.0, "n_drawn": 0}

    per_trades: list[float] = []
    for seed in range(seeds):
        rng = random.Random(seed)
        sides = ["C"] * n_call + ["P"] * n_put
        if len(sides) < n_sig:
            sides += ["C" if n_call >= n_put else "P"] * (n_sig - len(sides))
        rng.shuffle(sides)
        draw_days = [rng.choice(elig_days) for _ in range(n_sig)]
        pnl = 0.0
        nn = 0
        for k in range(n_sig):
            d = draw_days[k]
            side = sides[k]
            bidx = rng.choice(day_idxs[d])
            bar = spy.iloc[bidx]
            spot = float(bar["close"])
            atm = _strike_from_spot(spot)
            target = atm - strike_offset if side == "P" else atm + strike_offset
            res = sim._nearest_cached_strike_dte(d, target, side, dte)
            if res is None:
                continue
            strike, expiry = res
            stop_level = float(bar["low"]) if side == "C" else float(bar["high"])
            sg = Signal(bar_idx=bidx, side=side, stop_level=stop_level, note="cap_null")
            fill = simulate_dte_trade(sg, spy, {}, day_open_close, dte,
                                      strike=strike, expiry=expiry, side=side,
                                      qty=sim.QTY, premium_stop_pct=premium_stop_pct)
            if fill is None:
                continue
            # CAP-ENFORCE the random entry too (same gate as the signal cell).
            if not _cap_allows(account, equity, qty, fill.entry_premium):
                continue
            pnl += fill.dollar_pnl
            nn += 1
        per_trades.append(pnl / nn if nn else 0.0)
    return {
        "seeds": seeds,
        "per_trade_mean": round(float(np.mean(per_trades)), 2),
        "per_trade_max": round(float(max(per_trades)), 2),
        "per_trade_min": round(float(min(per_trades)), 2),
        "n_drawn": n_sig,
    }


def _drop_top5_full_rows(rows) -> Optional[float]:
    """Per-trade after dropping the 5 best P&L DAYS — full sample (gate 5 / null gate input)."""
    if not rows:
        return None
    by_day = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r.dollar_pnl)
    if len(by_day) <= 5:
        return None
    day_tot = sorted(by_day.items(), key=lambda kv: sum(kv[1]), reverse=True)
    kept = [p for _, pnls in day_tot[5:] for p in pnls]
    return round(sum(kept) / len(kept), 2) if kept else None


# ─────────────────────────────────────────────────────────────────────────────
# ONE CAP-ENFORCED CELL — run the cell, enforce the cap, compute metrics + structural bar.
# (gate 7 null + gate 8 truncation are applied in the driver, which needs the chart cell.)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CapCell:
    account: str
    tier: str
    tier_offset: int
    dte: int
    stop: str
    stop_param: float
    n_raw: int
    n_capped: int
    block_rate: float
    median_entry_premium: float
    metrics: dict
    book: dict
    oos_exp: Optional[float]
    structural_pass: bool
    structural_fails: list
    capped_rows: list   # DteFill rows that the cap KEEPS (for null + truncation)


def run_capped_cell(signals, spy, day_open_close, account, equity, qty, tier, tier_off,
                    dte, stop, stop_param) -> CapCell:
    cell = run_cell(signals, spy, day_open_close, dte,
                    strike_offset=tier_off, construction=stop, stop_param=stop_param)
    kept, block_rate, n_raw = _enforce_cap(cell.rows, account, equity, qty)
    # Re-scale each KEPT fill's dollar P&L to the ACCOUNT qty (run_cell used sim.QTY=3; Bold qty=5).
    if qty != sim.QTY and kept:
        kept = [_rescale_qty(r, qty) for r in kept]
    m = dte_metrics(kept)
    structural_pass, structural_fails = clears_bar(m)
    book = _book_metrics(kept)
    med_prem = round(float(np.median([r.entry_premium for r in cell.rows])), 4) if cell.rows else 0.0
    return CapCell(
        account=account, tier=tier, tier_offset=tier_off, dte=dte, stop=stop,
        stop_param=round(stop_param, 4), n_raw=n_raw, n_capped=len(kept), block_rate=block_rate,
        median_entry_premium=med_prem, metrics=m, book=book,
        oos_exp=m.get("oos_exp"), structural_pass=structural_pass,
        structural_fails=structural_fails, capped_rows=kept,
    )


def _rescale_qty(r, qty: int):
    """Return a copy of DteFill with dollar_pnl re-scaled from sim.QTY to `qty` contracts.
    Per-share economics (entry/exit premium, pct_return) are qty-invariant; only the dollar
    P&L and the dollar stop floor scale. The dollar-stop FLOOR was computed at sim.QTY inside
    simulate_dte_trade_stop, so for the dollar construction at qty != 3 the realized loss cap
    scales proportionally — which is exactly the live behaviour (a $thresh cap is per-position,
    so a 5-lot Bold position caps at 5/3 the 3-lot dollar threshold). pct_return is the
    construction-invariant authority, so we re-derive dollars from it."""
    from dataclasses import replace
    new_dollar = round(r.pct_return * (r.entry_premium * qty * 100.0), 2)
    return replace(r, dollar_pnl=new_dollar)


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────────
def _affordable(cell: CapCell) -> bool:
    """A cell is AFFORDABLE iff at least a material fraction of its signals actually fill under
    the cap AND it clears the minimum n bar (BAR_N). A cell blocked into n<20 is unusable."""
    return cell.n_capped >= sim.BAR_N


def run_account(account, signals, spy, day_open_close):
    cfg = ACCOUNTS[account]
    qty, equity = cfg["qty"], cfg["equity"]
    print(f"\n========== ACCOUNT={account.upper()} qty={qty} equity=${equity:.0f} ==========", flush=True)

    # Per-tier calibration (C29: the dollar threshold is re-derived per tier from that tier's
    # 0DTE -8% run — NOT shared across tiers). calibrate() runs at sim.QTY=3; for Bold qty=5 the
    # dollar threshold scales 5/3 (per-position cap), applied below.
    cells: list[CapCell] = []
    chart_pt_by = {}   # (tier,dte) -> chart-stop-only cap-enforced per-trade (gate 8 reference)
    for tier, off in TIERS.items():
        calib = calibrate(signals, spy, day_open_close, off)
        dollar_thresh = calib["dollar_thresh"] * (qty / sim.QTY)
        # gate-8 reference: same-tier chart-stop-only cap-enforced cell, per DTE.
        for dte in DTES:
            chart_cell = run_capped_cell(signals, spy, day_open_close, account, equity, qty,
                                         tier, off, dte, "chart", 0.0)
            chart_pt_by[(tier, dte)] = chart_cell.metrics.get("exp_dollar")
        for dte in DTES:
            for stop in STOPS:
                sp = dollar_thresh if stop == "dollar" else BASELINE_PCT
                c = run_capped_cell(signals, spy, day_open_close, account, equity, qty,
                                    tier, off, dte, stop, sp)
                cells.append(c)
                print(f"  {tier:>5} DTE={dte} {stop:>7} | medPrem=${c.median_entry_premium:<6} "
                      f"n_raw={c.n_raw:>3} n_cap={c.n_capped:>3} block={c.block_rate*100:>5.1f}% "
                      f"oos_exp=${str(c.oos_exp):>7} struct={'P' if c.structural_pass else 'F'} "
                      f"afford={'Y' if _affordable(c) else 'n'}", flush=True)

    # Baseline = affordable ATM/0DTE/-8% (the cell the answer must beat by +$25/tr OOS).
    base = next((c for c in cells if c.tier == BASELINE_CELL["tier"] and c.dte == BASELINE_CELL["dte"]
                 and c.stop == BASELINE_CELL["stop"]), None)
    base_oos = base.oos_exp if (base and _affordable(base)) else None

    # FULL 11-gate evaluation on every AFFORDABLE cell.
    evaluated = []
    for c in cells:
        afford = _affordable(c)
        full_pass = None
        null = None
        null_pass = None
        trunc_artifact = None
        if afford and c.structural_pass and (c.oos_exp or -1) > 0:
            null = cap_null(c.capped_rows, spy, day_open_close, c.dte, c.tier_offset,
                            c.stop_param if c.stop == "percent" else -0.99,
                            c.account, ACCOUNTS[account]["equity"], ACCOUNTS[account]["qty"])
            exp = c.metrics.get("exp_dollar")
            dt5_full = _drop_top5_full_rows(c.capped_rows)
            beats_max = exp is not None and exp > null["per_trade_max"]
            drop_beats_mean = dt5_full is not None and dt5_full > null["per_trade_mean"]
            null_pass = bool(beats_max and drop_beats_mean)
            chart_pt = chart_pt_by.get((c.tier, c.dte))
            trunc_artifact = is_truncation_artifact(
                best_per_trade=exp, chart_stop_only_per_trade=chart_pt,
                best_premium_stop_pct=(c.stop_param if c.stop == "percent" else None),
            )
            full_pass = bool(c.structural_pass and null_pass and (not trunc_artifact))
        else:
            full_pass = False
        evaluated.append({
            "account": account, "tier": c.tier, "tier_offset": c.tier_offset, "dte": c.dte,
            "stop": c.stop, "stop_param": c.stop_param, "median_entry_premium": c.median_entry_premium,
            "n_raw": c.n_raw, "n_capped": c.n_capped, "block_rate": c.block_rate,
            "affordable": afford, "oos_exp": c.oos_exp,
            "metrics_exp": c.metrics.get("exp_dollar"), "wr_pct": c.metrics.get("wr_pct"),
            "positive_quarters": c.metrics.get("positive_quarters"),
            "oos_drop_top5": c.metrics.get("oos_drop_top5"),
            "top5_day_pct": c.metrics.get("top5_day_pct"),
            "book_maxDD": c.book.get("book_maxDD"), "book_worst_day": c.book.get("book_worst_day"),
            "structural_pass": c.structural_pass, "structural_fails": c.structural_fails,
            "gate7_null": null, "gate7_null_pass": null_pass,
            "gate8_truncation_artifact": trunc_artifact,
            "FULL_11GATE_PASS": full_pass,
        })

    # Best affordable cell that CLEARS the full bar, ranked by OOS exp.
    clearing = [e for e in evaluated if e["FULL_11GATE_PASS"]]
    clearing.sort(key=lambda e: (e["oos_exp"] or -1e9), reverse=True)
    best = clearing[0] if clearing else None

    beats_baseline = None
    if best is not None and base_oos is not None:
        beats_baseline = bool((best["oos_exp"] or -1e9) > base_oos + BEAT_MARGIN)

    return {
        "account": account, "qty": qty, "equity": equity,
        "affordability_rule": f"premium*qty*100 <= cap; cap from check_order (Safe $600 / Bold $824); min_contracts {qty}",
        "baseline_cell": {**BASELINE_CELL, "oos_exp": base_oos,
                          "affordable": bool(base and _affordable(base)),
                          "structural_pass": (base.structural_pass if base else None)},
        "beat_margin_required": BEAT_MARGIN,
        "cells": evaluated,
        "best_affordable_11gate_cell": best,
        "best_beats_baseline_by_margin": beats_baseline,
        "n_affordable": sum(1 for e in evaluated if e["affordable"]),
        "n_clearing_full_bar": len(clearing),
    }


def validate() -> int:
    """Deterministic self-tests for the cap predicate + qty rescale (no OPRA needed)."""
    # Safe $600 cap @ qty3: premium 2.00 -> 600 == cap -> ALLOW; 2.01 -> 603 > 600 -> BLOCK.
    assert _cap_allows("safe", 2000.0, 3, 2.00) is True, "safe 2.00 should fit ($600 cap)"
    assert _cap_allows("safe", 2000.0, 3, 2.01) is False, "safe 2.01 should block (>$600)"
    # min_contracts: qty 2 < Safe min 3 -> BLOCK even at tiny premium.
    assert _cap_allows("safe", 2000.0, 2, 0.50) is False, "safe qty2 < min3 should block"
    # Bold $824 cap @ qty5: premium 1.648 -> 824 == cap -> ALLOW; 1.66 -> 830 -> BLOCK.
    assert _cap_allows("bold", 1648.0, 5, 1.648) is True, "bold 1.648 should fit ($824 cap)"
    assert _cap_allows("bold", 1648.0, 5, 1.70) is False, "bold 1.70 should block (>$824)"
    assert _cap_allows("bold", 1648.0, 4, 0.50) is False, "bold qty4 < min5 should block"
    # qty rescale: pct_return invariant -> dollars scale with qty*entry*100.
    from autoresearch._dte_expansion_sim import DteFill
    r = DteFill(date="2025-01-02", side="C", strike=600, atm=600, strike_off=0, expiry="2025-01-02",
                dte=0, entry_premium=1.00, exit_premium=1.30, dollar_pnl=90.0, pct_return=0.30,
                exit_reason="TP1_PREMIUM", held_overnight=False, gap_pts=0.0, note="t")
    r5 = _rescale_qty(r, 5)
    assert abs(r5.dollar_pnl - 150.0) < 1e-6, r5.dollar_pnl   # 0.30 * 1.00 * 5 * 100 = 150
    print("  OK cap predicate: Safe $600/qty3 boundary, Bold $824/qty5 boundary, min_contracts deny")
    print("  OK qty rescale: pct_return-invariant; qty3 $90 -> qty5 $150")
    print("VALIDATION PASSED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--family", default="vwap_continuation", choices=list(FAMILIES_EXT))
    args = ap.parse_args()

    if args.validate:
        return validate()

    print("[cap-aware] loading SPY+VIX ...", flush=True)
    spy, vix = sim._load_spy_vix()
    day_open_close = sim._spy_day_open_close(spy)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    for d in DTES:
        if d:
            sim._build_expiry_index(d)
    detect = FAMILIES_EXT[args.family]
    signals = detect(days, vix, spy, ribbon)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    print(f"[cap-aware] family={args.family} signals={len(signals)} on {sig_days} days "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}", flush=True)

    out = {
        "campaign": "CAP-AWARE re-validation of the DTE x STOP matrix — best AFFORDABLE config per account",
        "run_date": dt.date.today().isoformat(),
        "family": args.family,
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "n_signals": len(signals),
        "matrix_axes": {"tiers": list(TIERS), "dte": list(DTES), "stops": list(STOPS)},
        "cap_source": "lib.cap_admission (folds the cap) -> lib.risk_gate.check_order (the LIVE sizing gate)",
        "full_bar": "structural 1-6,9 (clears_bar) + gate7 DTE-aware cap-enforced random-null + gate8 no-truncation",
        "accounts": {},
    }
    for account in ("safe", "bold"):
        out["accounts"][account] = run_account(account, signals, spy, day_open_close)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[cap-aware] wrote {OUT}", flush=True)

    print("\n=== CAP-AWARE VERDICT ===")
    for account in ("safe", "bold"):
        a = out["accounts"][account]
        b = a["best_affordable_11gate_cell"]
        base = a["baseline_cell"]
        print(f"\n[{account.upper()}] baseline {base['tier']}/{base['dte']}DTE/{base['stop']} "
              f"oos_exp=${base['oos_exp']} (affordable={base['affordable']})")
        if b:
            print(f"  BEST affordable 11-gate cell: {b['tier']}/{b['dte']}DTE/{b['stop']} "
                  f"oos_exp=${b['oos_exp']} n_cap={b['n_capped']} block={b['block_rate']*100:.1f}% "
                  f"(medPrem=${b['median_entry_premium']})")
            print(f"  beats baseline by +${BEAT_MARGIN}/tr OOS? {a['best_beats_baseline_by_margin']}")
        else:
            print(f"  NO affordable cell clears the full 11-gate bar "
                  f"({a['n_affordable']} affordable, {a['n_clearing_full_bar']} clear) "
                  f"-> STAY at the 0DTE baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
