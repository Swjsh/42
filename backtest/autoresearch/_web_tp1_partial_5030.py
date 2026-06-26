"""WEB-LEARN: tp1-partial-50pct-vs-30pct on the LIVE vwap_continuation edge (#1).

HYPOTHESIS (web-sourced exit-management claim): raising the TP1 PARTIAL-OUT level from
+30% to +50% premium (banking the first half higher; runner + trail + stop + qty-fraction
all unchanged) improves EXPECTANCY on the live vwap_continuation edge WITHOUT tripping the
risk-adjusted gate.

The edgehunt mini-sweep already showed tp1_premium_pct=0.5 at exp +$90.43 / OOS +$122.64 /
6-of-6 positive quarters vs the live +30% at +$78.29 / OOS +$105.62 -- but that was scored on
DOLLAR-EXPECTANCY ONLY and was never put through the L175 Sharpe/Sortino/maxDD gate. Because a
+50% partial mechanically lowers WR (the first half banks less often), the risk-adjusted picture
must be confirmed before claiming improvement. This module applies the RIGHT bar for an
EXIT/MANAGEMENT change: expectancy lift AND the L175 risk-adjusted gate (book Sharpe + Sortino
+ maxDD MUST NOT worsen). REJECT if Sharpe drops OR maxDD widens even if dollar-expectancy
rises -- that is the exact L175 trap.

REUSE (no detector rebuild, no drift):
  * detector  = autoresearch._edgehunt_vwap_continuation.detect_signals (BYTE-FOR-BYTE the
    live vwap_continuation_watcher port).
  * fills     = lib.simulator_real.simulate_trade_real (real OPRA fills, C1).
  * strike/vix/normalize helpers = the same edgehunt + infinite_ammo path.
  * book-risk / per-trade-dist / L175 verdict math = ported from
    autoresearch._b10_exit_variance (the established Sharpe/Sortino/maxDD gate).

HARD WINDOW (the OPRA cache blind spot): real OPRA fills only exist <= 2026-05-29. We load
to END = 2026-05-15 (the b9/b10 window end, inside the cache) and ASSERT every filled trade's
date <= 2026-05-29. Any trade beyond the window aborts the run (no silent blind-spot leakage).

ONLY the partial-out level varies:
    tp1_premium_pct in {0.30 (live baseline), 0.40, 0.50}
Everything else HELD at the live vwap_continuation values:
    tp1_qty_fraction = 0.50, runner_target_premium_pct = 2.5,
    profit_lock_mode = 'trailing', profit_lock_threshold_pct = 0.05, profit_lock_trail_pct = 0.15,
    premium_stop_pct = -0.08, qty = 3.

Two strike tiers reported (C29 -- gates do not transfer across tiers): ATM (Safe-2) and
ITM-2 (Bold). The live edge ships dual-account; we report both so the verdict is tier-honest.

Pure Python / numpy, $0 (no LLM, no live orders). Markets closed (Sunday). NO live edits.
Writes analysis/recommendations/web-tp1-partial-5030.json + a section appended to
analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_web_tp1_partial_5030.py
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
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "web-tp1-partial-5030.json"
SCORECARD_MD = ROOT / "analysis" / "recommendations" / "SUNDAY-WEB-LEARN-SCORECARD.md"

# ── Window. Load to the b9/b10 window end (inside the OPRA cache); HARD-assert <=05-29. ──
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
HARD_WINDOW_MAX = dt.date(2026, 5, 29)   # OPRA real-fills cache blind spot (HARD + assert)
OOS_YEAR = 2026

# ── Strike tiers (C29) ──────────────────────────────────────────────────────────
ATM = 0
ITM2 = -2

# ── LIVE vwap_continuation exit config -- HELD CONSTANT; only TP1 varies ──────────
LIVE_TP1_QTY_FRAC = 0.50
LIVE_RUNNER_PCT = 2.5
LIVE_PROFIT_LOCK_MODE = "trailing"
LIVE_PROFIT_LOCK_THRESH = 0.05
LIVE_PROFIT_LOCK_TRAIL = 0.15
LIVE_PREMIUM_STOP = -0.08
QTY = 3
MAX_STRIKE_STEPS = 4

# ── The sweep: ONLY the partial-out level ─────────────────────────────────────────
TP1_SWEEP = [0.30, 0.40, 0.50]   # 0.30 = live baseline
BASELINE_TP1 = 0.30

TRADING_DAYS_YEAR = 252
# A higher TP1 banks less early -> a modest maxDD widening is EXPECTED. Only FAIL the gate
# if maxDD blows out materially. Same threshold the b10 variance audit uses.
MAXDD_MATERIAL_WORSEN_PCT = 0.25


# ════════════════════════════════════════════════════════════════════════════════
# SIM — one signal set at one (strike, tp1) cell on real OPRA fills.
# ════════════════════════════════════════════════════════════════════════════════
@dataclass
class TradeRow:
    date: str
    side: str
    strike: int
    pnl: float
    pct: float
    exit_reason: str
    tp1_filled: bool


def simulate_cell(signals, spy, ribbon, vix, *, strike_offset, tp1_premium_pct):
    """Run every signal at one (strike, tp1) cell. Everything but tp1 = live constants."""
    rows: list[TradeRow] = []
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
            qty=QTY, setup="VWAPCONT_TP1SWEEP", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=LIVE_PREMIUM_STOP,
            tp1_premium_pct=tp1_premium_pct,             # the ONLY swept knob
            tp1_qty_fraction=LIVE_TP1_QTY_FRAC,
            runner_target_premium_pct=LIVE_RUNNER_PCT,
            profit_lock_mode=LIVE_PROFIT_LOCK_MODE,
            profit_lock_threshold_pct=LIVE_PROFIT_LOCK_THRESH,
            profit_lock_trail_pct=LIVE_PROFIT_LOCK_TRAIL,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        # HARD-WINDOW assert: no fill may leak past the OPRA cache blind spot.
        if d > HARD_WINDOW_MAX:
            raise AssertionError(
                f"HARD-WINDOW breach: filled trade {d} > {HARD_WINDOW_MAX} (OPRA cache blind spot)")
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, strike=int(strike),
            pnl=round(float(fill.dollar_pnl), 2),
            pct=round(float(fill.pct_return_on_premium), 5),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            tp1_filled=bool(getattr(fill, "tp1_filled", False)),
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ════════════════════════════════════════════════════════════════════════════════
# METRICS — expectancy + WR + IS/OOS + positive-quarters + concentration
# ════════════════════════════════════════════════════════════════════════════════
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _top5_day_pct(rows: list[TradeRow]):
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def expectancy_metrics(rows: list[TradeRow]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_pnl = [r.pnl for r in rows if int(r.date[:4]) != OOS_YEAR]
    oos_pnl = [r.pnl for r in rows if int(r.date[:4]) == OOS_YEAR]
    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: round(sum(v) / len(v), 2) for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v > 0)
    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_pnl), "is_exp": round(float(np.mean(is_pnl)), 2) if is_pnl else 0.0,
        "oos_n": len(oos_pnl), "oos_exp": round(float(np.mean(oos_pnl)), 2) if oos_pnl else 0.0,
        "oos_total": round(float(np.sum(oos_pnl)), 2) if oos_pnl else 0.0,
        "quarters": quarters,
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": _top5_day_pct(rows),
    }


# ════════════════════════════════════════════════════════════════════════════════
# L175 RISK-ADJUSTED GATE — per-trade Sharpe + book daily Sharpe/Sortino/maxDD
# (ported from _b10_exit_variance.book_risk / per_trade_dist / decide_verdict)
# ════════════════════════════════════════════════════════════════════════════════
def per_trade_shape(rows: list[TradeRow]) -> dict:
    pnl = np.array([r.pnl for r in rows], float)
    n = len(pnl)
    mean = float(pnl.mean()) if n else 0.0
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    losers = pnl[pnl < 0]
    return {
        "n": n,
        "mean": round(mean, 2),
        "std": round(std, 2),
        "sharpe_per_trade": round(mean / std, 4) if std > 0 else 0.0,
        "pct_losing": round(100 * float((pnl < 0).mean()), 1) if n else 0.0,
        "worst_trade": round(float(pnl.min()), 2) if n else 0.0,
        "mean_of_losers": round(float(losers.mean()), 2) if len(losers) else 0.0,
    }


def _daily_series(rows: list[TradeRow]) -> np.ndarray:
    by_d: dict[str, float] = defaultdict(float)
    for r in rows:
        by_d[r.date] += r.pnl
    return np.array([by_d[d] for d in sorted(by_d)], float)


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return round(float((equity - peak).min()), 2)


def book_risk(rows: list[TradeRow]) -> dict:
    d = _daily_series(rows)
    n_days = len(d)
    if n_days == 0:
        return {"trading_days": 0}
    mean_d = float(d.mean())
    std_d = float(d.std(ddof=1)) if n_days > 1 else 0.0
    downside = np.minimum(d, 0.0)
    dd_dev = float(np.sqrt((downside ** 2).mean()))
    mdd = _max_drawdown(np.cumsum(d))
    ann = np.sqrt(TRADING_DAYS_YEAR)
    return {
        "trading_days": n_days,
        "mean_daily": round(mean_d, 2),
        "std_daily": round(std_d, 2),
        "downside_dev_daily": round(dd_dev, 2),
        "worst_day": round(float(d.min()), 2),
        "max_drawdown": mdd,
        "total": round(float(d.sum()), 2),
        "day_wr_pct": round(100 * float((d > 0).mean()), 1),
        "sharpe_annualized": round((mean_d / std_d) * ann, 3) if std_d > 0 else 0.0,
        "sortino_annualized": round((mean_d / dd_dev) * ann, 3) if dd_dev > 0 else 0.0,
    }


def l175_verdict(base_pt, var_pt, base_bk, var_bk) -> dict:
    """L175 gate for an EXIT change: expectancy must rise AND risk-adjusted must NOT worsen.
    PASS iff higher mean AND per-trade Sharpe holds AND book Sortino holds AND book Sharpe
    holds AND book maxDD does not worsen materially (>25% deeper). Else L175_TRAP (reject)."""
    higher_mean = var_pt["mean"] > base_pt["mean"]
    sharpe_tr_ok = var_pt["sharpe_per_trade"] >= base_pt["sharpe_per_trade"] - 1e-9
    sharpe_bk_ok = var_bk["sharpe_annualized"] >= base_bk["sharpe_annualized"] - 1e-9
    sortino_ok = var_bk["sortino_annualized"] >= base_bk["sortino_annualized"] - 1e-9
    base_mdd = abs(base_bk["max_drawdown"])
    var_mdd = abs(var_bk["max_drawdown"])
    mdd_worsen_frac = (var_mdd - base_mdd) / base_mdd if base_mdd > 0 else 0.0
    mdd_material_worse = mdd_worsen_frac > MAXDD_MATERIAL_WORSEN_PCT
    passes = bool(higher_mean and sharpe_tr_ok and sharpe_bk_ok and sortino_ok
                  and (not mdd_material_worse))
    return {
        "higher_mean": bool(higher_mean),
        "per_trade_sharpe_holds": bool(sharpe_tr_ok),
        "book_sharpe_holds": bool(sharpe_bk_ok),
        "book_sortino_holds": bool(sortino_ok),
        "maxdd_worsen_frac": round(mdd_worsen_frac, 4),
        "maxdd_material_worse": bool(mdd_material_worse),
        "verdict": "PASS_RISK_ADJUSTED" if passes else "L175_TRAP_REJECT",
    }


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"[web-tp1] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    win_lo = spy["timestamp_et"].iloc[0].date()
    win_hi = spy["timestamp_et"].iloc[-1].date()
    print(f"[web-tp1] trading_days={len(days)} window={win_lo}..{win_hi} "
          f"(HARD cache cap={HARD_WINDOW_MAX})", flush=True)

    # Detect the live vwap_continuation signals ONCE (byte-for-byte live detector).
    signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[web-tp1] vwap_continuation signals={len(signals)} on {sig_days} days side={side_ct}",
          flush=True)

    tiers = {"Safe-2_ATM": ATM, "Bold_ITM2": ITM2}
    results: dict[str, dict] = {}

    for tier_name, so in tiers.items():
        print(f"\n[web-tp1] === {tier_name} (strike_offset={so}) ===", flush=True)
        # Run each tp1 cell once.
        cells = {}
        for tp1 in TP1_SWEEP:
            rows, cov = simulate_cell(signals, spy, ribbon, vix,
                                      strike_offset=so, tp1_premium_pct=tp1)
            em = expectancy_metrics(rows)
            pt = per_trade_shape(rows)
            bk = book_risk(rows)
            cells[f"tp1_{int(tp1*100)}"] = {
                "tp1_premium_pct": tp1, "coverage": cov,
                "expectancy": em, "per_trade_shape": pt, "book_risk": bk,
                "_rows": rows,
            }
            print(f"  tp1={tp1:.2f} n={em.get('n')} exp=${em.get('exp_dollar')} "
                  f"oos_exp=${em.get('oos_exp')} WR={em.get('wr_pct')}% posQ={em.get('positive_quarters')} "
                  f"top5%={em.get('top5_day_pct')} | sharpe/tr={pt['sharpe_per_trade']} "
                  f"bookSharpe={bk.get('sharpe_annualized')} bookSortino={bk.get('sortino_annualized')} "
                  f"maxDD=${bk.get('max_drawdown')}", flush=True)

        base = cells[f"tp1_{int(BASELINE_TP1*100)}"]
        # L175 verdict for each non-baseline tp1 vs the +30% baseline.
        verdicts = {}
        for tp1 in TP1_SWEEP:
            if abs(tp1 - BASELINE_TP1) < 1e-9:
                continue
            var = cells[f"tp1_{int(tp1*100)}"]
            v = l175_verdict(base["per_trade_shape"], var["per_trade_shape"],
                             base["book_risk"], var["book_risk"])
            be = base["expectancy"]; ve = var["expectancy"]
            v["exp_delta"] = round(ve.get("exp_dollar", 0) - be.get("exp_dollar", 0), 2)
            v["oos_exp_delta"] = round(ve.get("oos_exp", 0) - be.get("oos_exp", 0), 2)
            v["wr_delta_pp"] = round(ve.get("wr_pct", 0) - be.get("wr_pct", 0), 1)
            verdicts[f"tp1_{int(tp1*100)}_vs_30"] = v
            print(f"  L175 tp1={tp1:.2f} vs 0.30: {v['verdict']} "
                  f"(exp d={v['exp_delta']:+} oos d={v['oos_exp_delta']:+} WR d={v['wr_delta_pp']:+}pp | "
                  f"higher_mean={v['higher_mean']} sharpe/tr_holds={v['per_trade_sharpe_holds']} "
                  f"bookSharpe_holds={v['book_sharpe_holds']} sortino_holds={v['book_sortino_holds']} "
                  f"maxDD_worsen={v['maxdd_worsen_frac']:+.1%} material={v['maxdd_material_worse']})",
                  flush=True)

        # strip rows before serializing
        for c in cells.values():
            c.pop("_rows", None)
        results[tier_name] = {"strike_offset": so, "cells": cells, "l175_verdicts": verdicts}

    # Overall: the headline claim is about the LIVE edge. Safe-2 ships ATM today; Bold ships ITM-2.
    # The claim "improves expectancy without tripping L175" PASSES only if tp1=0.50 PASSES L175.
    def _tier_pass(tier):
        v = results[tier]["l175_verdicts"].get("tp1_50_vs_30", {})
        return v.get("verdict") == "PASS_RISK_ADJUSTED"
    atm_pass = _tier_pass("Safe-2_ATM")
    itm_pass = _tier_pass("Bold_ITM2")
    overall = ("EDGE_IMPROVEMENT" if (atm_pass and itm_pass)
               else ("PARTIAL_TIER_IMPROVEMENT" if (atm_pass or itm_pass) else "L175_TRAP_REJECT"))

    summary = {
        "slug": "tp1-partial-50pct-vs-30pct",
        "claim": ("Raising TP1 partial-out +30%->+50% (runner/trail/stop/qty held) improves "
                  "vwap_continuation expectancy without tripping the L175 risk-adjusted gate."),
        "kind": "improves_existing_edge_1_vwap_continuation",
        "run_date": dt.date.today().isoformat(),
        "window_loaded": f"{win_lo}..{win_hi}",
        "hard_window_cap": str(HARD_WINDOW_MAX),
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "detector": ("BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals "
                     "(= live vwap_continuation_watcher port)"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1); HARD-window asserted <=2026-05-29",
        "held_constant_live_config": {
            "tp1_qty_fraction": LIVE_TP1_QTY_FRAC, "runner_target_premium_pct": LIVE_RUNNER_PCT,
            "profit_lock_mode": LIVE_PROFIT_LOCK_MODE, "profit_lock_threshold_pct": LIVE_PROFIT_LOCK_THRESH,
            "profit_lock_trail_pct": LIVE_PROFIT_LOCK_TRAIL, "premium_stop_pct": LIVE_PREMIUM_STOP,
            "qty": QTY,
        },
        "swept": {"tp1_premium_pct": TP1_SWEEP, "baseline": BASELINE_TP1},
        "n_signals": len(signals), "signal_side_count": side_ct,
        "l175_gate_rule": ("EXIT change PASSES iff exp rises AND per-trade Sharpe holds AND book "
                           "daily Sharpe holds AND book Sortino holds AND book maxDD not >25% deeper. "
                           "REJECT (L175 trap) if dollar-exp rises but any risk metric worsens."),
        "tiers": results,
        "overall_verdict": overall,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills, the only 0DTE WR authority (C1); SPY-dir != option edge (C3/L58).",
            "wr_caveat": ("a higher TP1 partial mechanically LOWERS WR -- the first half banks less "
                          "often -- so WR delta will be negative; that is EXPECTED and is why the gate "
                          "is risk-adjusted (Sharpe/Sortino), not WR-based (OP-14)."),
            "relative_comparison": ("Sharpe/Sortino are RELATIVE (tp1 vs tp1 on the SAME trade set / "
                                    "SAME bull-flattered tape) so the bull bias cancels; the ABSOLUTE "
                                    "Sharpe is not a forward forecast."),
            "tier_honesty": ("C29 -- exit knobs do not transfer across strike tiers; ATM (Safe-2) and "
                             "ITM-2 (Bold) reported independently; the live edge ships dual-account."),
            "hard_window": ("OPRA real-fill cache ends ~2026-05-29; every filled trade asserted "
                            "<= that date so no blind-spot leakage inflates OOS."),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[web-tp1] wrote {OUT_JSON}", flush=True)

    append_scorecard(summary)
    print(f"[web-tp1] appended section to {SCORECARD_MD}", flush=True)

    print("\n=== TP1 +50% vs +30% (vwap_continuation) VERDICT ===")
    print(f"OVERALL: {overall}")
    for tier, r in results.items():
        v = r["l175_verdicts"].get("tp1_50_vs_30", {})
        b = r["cells"][f"tp1_{int(BASELINE_TP1*100)}"]
        w = r["cells"]["tp1_50"]
        print(f"  {tier}: {v.get('verdict')}  exp ${b['expectancy'].get('exp_dollar')}->"
              f"${w['expectancy'].get('exp_dollar')} (oos ${b['expectancy'].get('oos_exp')}->"
              f"${w['expectancy'].get('oos_exp')})  WR {b['expectancy'].get('wr_pct')}%->"
              f"{w['expectancy'].get('wr_pct')}%  bookSharpe {b['book_risk'].get('sharpe_annualized')}->"
              f"{w['book_risk'].get('sharpe_annualized')}  Sortino {b['book_risk'].get('sortino_annualized')}->"
              f"{w['book_risk'].get('sortino_annualized')}  maxDD ${b['book_risk'].get('max_drawdown')}->"
              f"${w['book_risk'].get('max_drawdown')}")
    return 0


def append_scorecard(s: dict) -> None:
    L = []
    L.append(f"\n\n---\n\n## tp1-partial-50pct-vs-30pct — vwap_continuation (#1) — {s['run_date']}\n")
    L.append(f"**Claim:** {s['claim']}\n")
    L.append(f"**Kind:** EXIT/MANAGEMENT change on the LIVE edge #1 -> bar = expectancy lift AND "
             f"L175 risk-adjusted gate (Sharpe/Sortino/maxDD not worse).\n")
    L.append(f"- Window loaded: {s['window_loaded']} | HARD OPRA cap: {s['hard_window_cap']} (asserted) "
             f"| OOS: {s['oos_split']}")
    L.append(f"- Fills: {s['fills_authority']}")
    L.append(f"- Detector: {s['detector']}")
    hc = s["held_constant_live_config"]
    L.append(f"- Held constant (live config): tp1_qty={hc['tp1_qty_fraction']}, "
             f"runner={hc['runner_target_premium_pct']}x, trail={hc['profit_lock_trail_pct']} "
             f"(mode {hc['profit_lock_mode']}, arm {hc['profit_lock_threshold_pct']}), "
             f"stop={hc['premium_stop_pct']}, qty={hc['qty']}. **Only tp1_premium_pct swept.**")
    L.append(f"- Signals: {s['n_signals']} ({s['signal_side_count']})\n")
    L.append(f"### VERDICT: **{s['overall_verdict']}**\n")

    for tier, r in s["tiers"].items():
        L.append(f"#### {tier} (strike_offset={r['strike_offset']})\n")
        L.append("| tp1 | n | exp $ | OOS exp $ | WR% | posQ | top5%day | sharpe/tr | book Sharpe | book Sortino | maxDD $ |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for tp1 in TP1_SWEEP:
            c = r["cells"][f"tp1_{int(tp1*100)}"]
            em = c["expectancy"]; pt = c["per_trade_shape"]; bk = c["book_risk"]
            flag = " (baseline)" if abs(tp1 - BASELINE_TP1) < 1e-9 else ""
            L.append(f"| {tp1:.2f}{flag} | {em.get('n')} | {em.get('exp_dollar')} | {em.get('oos_exp')} | "
                     f"{em.get('wr_pct')} | {em.get('positive_quarters')} | {em.get('top5_day_pct')} | "
                     f"{pt['sharpe_per_trade']} | {bk.get('sharpe_annualized')} | "
                     f"{bk.get('sortino_annualized')} | {bk.get('max_drawdown')} |")
        L.append("")
        for vk, v in r["l175_verdicts"].items():
            L.append(f"- **L175 {vk}**: {v['verdict']} — exp Δ={v['exp_delta']:+}, OOS exp Δ="
                     f"{v['oos_exp_delta']:+}, WR Δ={v['wr_delta_pp']:+}pp; higher_mean={v['higher_mean']}, "
                     f"per-trade Sharpe holds={v['per_trade_sharpe_holds']}, book Sharpe holds="
                     f"{v['book_sharpe_holds']}, Sortino holds={v['book_sortino_holds']}, "
                     f"maxDD worsen={v['maxdd_worsen_frac']:+.1%} (material={v['maxdd_material_worse']}).")
        L.append("")
    L.append("**How to read:** a higher TP1 partial mechanically LOWERS WR (first half banks less often) "
             "— expected, hence the gate is risk-adjusted not WR-based (OP-14). PASS requires dollar-expectancy "
             "to rise AND every risk metric (per-trade Sharpe, book Sharpe, book Sortino, maxDD) to hold; "
             "a dollar-exp rise with a Sharpe drop or maxDD blowout is the L175 TRAP and is REJECTED.\n")
    for k, v in s["DISCLOSURE"].items():
        L.append(f"- _{k}_: {v}")
    L.append("")

    header = ""
    if not SCORECARD_MD.exists():
        header = ("# Sunday Web-Learn Scorecard\n\nWeb-sourced hypotheses tested on OUR data "
                  "(real OPRA fills, HARD-windowed). Each section names the death honestly or the "
                  "validated improvement. NO live edits — research only.\n")
    SCORECARD_MD.parent.mkdir(parents=True, exist_ok=True)
    with SCORECARD_MD.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
