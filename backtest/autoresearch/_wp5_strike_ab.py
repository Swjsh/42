"""WP-5: vwap_continuation STRIKE A/B on real OPRA fills — quantify the live money leak.

CONTEXT (the live-edge money leak). B1's smoke test
(``analysis/recommendations/B1-VWAP-SMOKETEST.md``) found that the ONE live edge,
``vwap_continuation`` (``j_vwap_cont_enabled=true`` on Safe-2), fires the GENERIC v15
OTM-2 strike tier on the $2K Safe-2 account — NOT its VALIDATED cell. The edge-hunt
validated the SAME signal set at ATM (OOS +$59.81/tr) and ITM-2 (OOS +$105.62/tr) with
the strike gradient ITM > ATM > OTM (OTM = the weak end). The three recent in-cache
live-strike fills (2026-05-22 / -28 / -29) all LOST money. So the live edge is likely
running where its validated edge is eroded by OTM theta/delta (C3/C29). This A/B
quantifies the leak so J can fix it in daylight.

WHAT THIS DOES. Reuse the VALIDATED ``_edgehunt_vwap_continuation.detect_signals``
detector (byte-for-byte the live ``vwap_continuation_watcher`` port) + the real-OPRA
``lib.simulator_real.simulate_trade_real`` (C1) + the existing 11-gate machinery
(``autoresearch.fraud_gates.verify_candidate`` for the two GRADUATED fraud gates +
the deterministic mandatory gates in-script). Detect signals ONCE, then re-simulate the
SAME signal set at four strike cells, holding the −8% stop and v15 exits constant:

  * OTM-2  (sim strike_offset = +2)  — the CURRENT LIVE Safe-2 tier (the leak source)
  * ATM    (sim strike_offset =  0)  — the VALIDATED Safe-2 cell
  * ITM-1  (sim strike_offset = −1)
  * ITM-2  (sim strike_offset = −2)  — the VALIDATED Bold cell

STRIKE-OFFSET CONVENTION (the load-bearing crosswalk; mis-stating it invalidated a
whole weekend once — sim-accuracy gate, OP-16). TWO conventions exist and they are
INVERSE of each other:
  * simulator_real.py  (L357-364): puts strike = atm − offset, calls = atm + offset
                       => NEGATIVE offset = ITM, POSITIVE = OTM (BOTH sides).
  * live heartbeat / params.json ``v15_strike_offset_per_tier``: OTM-2 has
                       strike_offset = −2, ITM-2 = +2  => NEGATIVE = OTM (INVERSE).
This script passes the SIMULATOR convention to simulate_trade_real. The live Safe-2
OTM-2 tier therefore maps to SIM offset +2 (verified vs B1: Safe-2 heartbeat strike =
OTM-2). Every cell is labelled with BOTH conventions in the output so there is no
ambiguity.

HARD WINDOW (C7 assert). Signals + fills are hard-windowed to the OPRA cache edge
(<= 2026-05-29). The output ASSERTS the last realized fill date <= 2026-05-29; if a
fill lands after that the run FAILS LOUD (never silently report past-cache fills).

THE LEAK. Reported in $/trade and annualized $ at the live signal frequency:
  * (ATM exp/tr) − (OTM-2 exp/tr)            — the Safe-2 mis-strike cost
  * (validated cell) − (live cell)           — same thing, named by the brief
Annualized = leak_per_trade × signals_per_year (signal_days / trading_days × 252).

GATES per cell (the standing 11-gate bar): full-sample + OOS expectancy, n, WR,
positive-quarters >= 4/6, top5-day < 200%, drop-top5 > 0, OOS-alone drop-top5 (L173),
the random-entry-null (L172) and no-truncation (L171) graduated fraud gates.

Pure Python, $0 (no LLM in the sim loop). No live orders. Markets closed (Sunday).
Writes analysis/recommendations/wp5-strike-ab.json (consumed by
WP5-STRIKE-AB-SCORECARD.md). RESEARCH ONLY — touches NO live watcher / params.json /
heartbeat / risk_gate / orchestrator.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_wp5_strike_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # backtest/
ROOT = REPO.parent                            # repo root (42/)
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
    detect_signals,
)
from autoresearch.fraud_gates import CandidateSignal, oos_drop_top5_gate, verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
    build_day_contexts,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402

SLUG = "wp5-strike-ab"
OUT = ROOT / "analysis" / "recommendations" / "wp5-strike-ab.json"

# ── Held-constant survivor structure (only strike varies across cells) ──────────
PREMIUM_STOP_PCT = -0.08      # v15 asymmetric tight stop (held constant)
QTY = 3                       # 2 TP + 1 runner
MAX_STRIKE_STEPS = 4          # nearest-cached snap radius (matches the edge-hunt path)
SETUP = "WP5_VWAP_CONTINUATION"
OOS_YEAR = 2026
NULL_SEEDS = 20

# Hard window: the OPRA cache edge. ASSERT no realized fill lands after this.
CACHE_EDGE = dt.date(2026, 5, 29)

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 29)    # hard-windowed to the cache edge

# ── The four strike cells (SIM convention; see module docstring crosswalk) ──────
# (label, sim_offset, live_params_offset, role)
CELLS = [
    ("OTM-2", 2, -2, "LIVE Safe-2 tier (leak source)"),
    ("ATM", 0, 0, "VALIDATED Safe-2 cell"),
    ("ITM-1", -1, 1, "intermediate"),
    ("ITM-2", -2, 2, "VALIDATED Bold cell"),
]
LIVE_LABEL = "OTM-2"          # the cell currently trading on Safe-2
SAFE_VALID_LABEL = "ATM"      # the validated Safe-2 cell
BOLD_VALID_LABEL = "ITM-2"    # the validated Bold cell

# ── Mandatory gate bars (the standing 11-gate bar) ──────────────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0

TRADING_DAYS_PER_YEAR = 252


def _quarter(day: str) -> str:
    y, m, _ = day.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _per_trade(rows) -> Optional[float]:
    return round(float(np.mean([r["pnl"] for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows) -> Optional[float]:
    """Per-trade after removing the 5 best P&L DAYS (concentration robustness)."""
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    if not by_day:
        return None
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(float(np.mean(kept)), 2) if kept else None


def _oos_drop_top5_per_trade(rows) -> Optional[float]:
    """OOS-only per-trade after removing the 5 best OOS observations (L173)."""
    oos = sorted((r["pnl"] for r in rows if int(r["date"][:4]) == OOS_YEAR), reverse=True)
    trimmed = oos[5:]
    return round(float(np.mean(trimmed)), 2) if trimmed else None


def _top5_day_pct(rows) -> Optional[float]:
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def _simulate_cell(signals, spy, vix, *, sim_offset: int) -> tuple[list[dict], dict]:
    """Re-run the SAME signal set at ONE strike cell on real OPRA fills.

    Holds PREMIUM_STOP_PCT + v15 exits constant; only the strike offset varies.
    Returns (rows, coverage). ASSERTS no fill lands after the cache edge (C7).
    """
    rows: list[dict] = []
    n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        # SIM convention: puts strike = atm - offset, calls = atm + offset.
        target = atm - sim_offset if sg.side == "P" else atm + sim_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=None,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "vwap_cont"],
            side=sg.side, qty=QTY, setup=SETUP, strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        # C7 HARD-WINDOW ASSERT: no realized fill past the OPRA cache edge.
        assert d <= CACHE_EDGE, f"fill date {d} > cache edge {CACHE_EDGE} (look-ahead/cache bleed)"
        rows.append({
            "date": str(d), "side": sg.side, "strike": int(strike), "atm": int(atm),
            "strike_off_sim": int(strike - atm),
            "pnl": round(float(fill.dollar_pnl), 2),
            "exit": fill.exit_reason.name if fill.exit_reason else "NONE",
        })
    cov = {"signals": len(signals), "filled": len(rows),
           "cache_miss": n_cache_miss, "sim_none": n_sim_none,
           "fill_rate": round(len(rows) / len(signals), 3) if signals else 0.0}
    return rows, cov


def _cell_metrics_and_gates(rows, cand_signals, rth, *, sim_offset: int) -> dict:
    """Full metric block + the standing 11-gate bar for one strike cell."""
    n = len(rows)
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]

    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "per_trade": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    pos_q = sum(1 for v in quarters.values() if v["per_trade"] > 0)

    overall_pt = _per_trade(rows)
    is_pt = _per_trade(is_rows)
    oos_pt = _per_trade(oos_rows)
    drop_top5_pt = _drop_top5_per_trade(rows)
    oos_drop_top5_pt = _oos_drop_top5_per_trade(rows)
    top5 = _top5_day_pct(rows)
    wr = round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None
    last_fill = max((r["date"] for r in rows), default=None)

    # ── graduated fraud gates (re-sim chosen + chart-stop-only + 20-seed null) ──
    fraud = verify_candidate(
        cand_signals, rth, strike_offset=sim_offset, premium_stop_pct=PREMIUM_STOP_PCT,
        qty=QTY, setup=f"{SETUP}_{sim_offset}", seeds=NULL_SEEDS)

    # ── L173 OOS-alone drop-top5 gate ──
    oos_dt5 = oos_drop_top5_gate(oos_drop_top5_per_trade=oos_drop_top5_pt, oos_n=len(oos_rows))

    gates = {
        "GATE_n_ge20": bool(n >= BAR_N),
        "GATE_OOS_pt_gt0": bool(oos_pt is not None and oos_pt > 0),
        "GATE_IS_pt_gt0": bool(is_pt is not None and is_pt > 0),
        "GATE_full_pt_gt0": bool(overall_pt is not None and overall_pt > 0),
        "GATE_pos_quarters_ge4of6": bool(pos_q >= BAR_POS_Q and len(quarters) >= 6),
        "GATE_top5_day_lt200": bool(top5 is not None and top5 < BAR_TOP5),
        "GATE_drop_top5_pt_gt0": bool(drop_top5_pt is not None and drop_top5_pt > 0),
        "GATE_oos_drop_top5_gt0": bool(oos_dt5.get("oos_drop_top5_pass")),
        "GATE_beats_random_null": bool(fraud.null_pass),
        "GATE_no_truncation": bool(fraud.no_truncation_pass),
        "GATE_wr_reported": bool(wr is not None),  # disclosure gate (WR shown, not gating)
    }
    fails = [k for k, v in gates.items() if not v]

    return {
        "n": n, "wr_pct": wr,
        "overall_per_trade": overall_pt,
        "is_n": len(is_rows), "is_per_trade": is_pt,
        "oos_n": len(oos_rows), "oos_per_trade": oos_pt,
        "drop_top5_per_trade": drop_top5_pt,
        "oos_drop_top5_per_trade": oos_drop_top5_pt,
        "oos_drop_top5_gate": oos_dt5,
        "top5_day_pct": top5,
        "positive_quarters": f"{pos_q}/{len(quarters)}",
        "quarters": quarters,
        "last_fill_date": last_fill,
        "exit_hist": {k: sum(1 for r in rows if r["exit"] == k)
                      for k in sorted({r["exit"] for r in rows})},
        "fraud_gates": fraud.as_dict(),
        "gates": gates,
        "fails": fails,
        "clears_11_gate_bar": len(fails) == 0,
    }


def main() -> int:
    print(f"[wp5] loading SPY+VIX {START}..{END} (hard-windowed to cache edge) ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)

    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)

    # Detect the validated vwap_continuation signal set ONCE (full pattern).
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals})
    fire_day_pct = round(100 * sig_days / n_days, 1)
    sigs_per_year = round(sig_days / n_days * TRADING_DAYS_PER_YEAR, 1)
    print(f"[wp5] vwap_continuation signals={len(signals)} on {sig_days} days "
          f"({fire_day_pct}% of {n_days}) side={side_ct}  ~{sigs_per_year} signals/yr", flush=True)

    # Build the CandidateSignal list ONCE (indexes into rth) for the fraud gates.
    cand_signals = [
        CandidateSignal(
            bar_idx=int(rth.index[rth["timestamp_et"] == spy.iloc[s.bar_idx]["timestamp_et"]][0]),
            side=s.side, rejection_level=float(s.stop_level), note=s.note or "vwap_cont")
        for s in signals
        if (rth["timestamp_et"] == spy.iloc[s.bar_idx]["timestamp_et"]).any()
    ]

    # ── Run all four strike cells on real OPRA fills ───────────────────────────
    cells = []
    for label, sim_off, live_off, role in CELLS:
        print(f"[wp5] cell {label} (sim_off={sim_off:+d} / live_params_off={live_off:+d}) ...",
              flush=True)
        rows, cov = _simulate_cell(signals, spy, vix, sim_offset=sim_off)
        m = _cell_metrics_and_gates(rows, cand_signals, rth, sim_offset=sim_off)
        cells.append({
            "label": label, "role": role,
            "sim_strike_offset": sim_off, "live_params_strike_offset": live_off,
            "coverage": cov, "metrics": m,
        })
        print(f"    n={m['n']} WR={m['wr_pct']}% full=${m['overall_per_trade']} "
              f"IS=${m['is_per_trade']} OOS=${m['oos_per_trade']} posQ={m['positive_quarters']} "
              f"top5%={m['top5_day_pct']} null_pass={m['fraud_gates']['null_pass']} "
              f"no_trunc={m['fraud_gates']['no_truncation_pass']} "
              f"clears={m['clears_11_gate_bar']} fails={m['fails']}", flush=True)

    by_label = {c["label"]: c for c in cells}

    def _full(lbl):  # full-sample per-trade
        return by_label[lbl]["metrics"]["overall_per_trade"]

    def _oos(lbl):
        return by_label[lbl]["metrics"]["oos_per_trade"]

    # ── THE LEAK ───────────────────────────────────────────────────────────────
    def _leak(better_lbl, worse_lbl):
        out = {}
        for tag, fn in (("full_sample", _full), ("oos", _oos)):
            b, w = fn(better_lbl), fn(worse_lbl)
            per_tr = round(b - w, 2) if (b is not None and w is not None) else None
            out[tag] = {
                "better_per_trade": b, "worse_per_trade": w,
                "leak_per_trade": per_tr,
                "leak_per_year": (round(per_tr * sigs_per_year, 0) if per_tr is not None else None),
            }
        return out

    leak_atm_vs_otm2 = _leak(SAFE_VALID_LABEL, LIVE_LABEL)         # Safe mis-strike
    leak_itm2_vs_otm2 = _leak(BOLD_VALID_LABEL, LIVE_LABEL)        # Bold validated vs live tier
    leak_itm1_vs_otm2 = _leak("ITM-1", LIVE_LABEL)

    live_cell = by_label[LIVE_LABEL]["metrics"]
    otm2_full = live_cell["overall_per_trade"]
    otm2_oos = live_cell["oos_per_trade"]
    otm2_positive = bool((otm2_full is not None and otm2_full > 0)
                         and (otm2_oos is not None and otm2_oos > 0))
    otm2_clears = by_label[LIVE_LABEL]["metrics"]["clears_11_gate_bar"]

    # decisive-beat check: validated cell positive AND clears + leak materially > 0
    atm_clears = by_label[SAFE_VALID_LABEL]["metrics"]["clears_11_gate_bar"]
    itm2_clears = by_label[BOLD_VALID_LABEL]["metrics"]["clears_11_gate_bar"]
    atm_beats_decisively = bool(
        atm_clears and not otm2_clears
        and leak_atm_vs_otm2["oos"]["leak_per_trade"] is not None
        and leak_atm_vs_otm2["oos"]["leak_per_trade"] > 0)
    itm2_beats_decisively = bool(
        itm2_clears and leak_itm2_vs_otm2["oos"]["leak_per_trade"] is not None
        and leak_itm2_vs_otm2["oos"]["leak_per_trade"] > 0)

    # last fill across ALL cells must respect the cache edge (C7 belt-and-suspenders).
    all_last_fills = [c["metrics"]["last_fill_date"] for c in cells if c["metrics"]["last_fill_date"]]
    last_fill_overall = max(all_last_fills) if all_last_fills else None
    assert last_fill_overall is None or last_fill_overall <= str(CACHE_EDGE), (
        f"last fill {last_fill_overall} > cache edge {CACHE_EDGE}")

    verdict_bits = []
    if otm2_positive and otm2_clears:
        verdict_bits.append(f"OTM-2 (live Safe-2) IS a positive edge (full=${otm2_full}/tr "
                            f"OOS=${otm2_oos}/tr, clears the 11-gate bar)")
    elif otm2_positive:
        verdict_bits.append(f"OTM-2 (live Safe-2) is positive but does NOT clear the full "
                            f"11-gate bar (full=${otm2_full}/tr OOS=${otm2_oos}/tr; "
                            f"fails {by_label[LIVE_LABEL]['metrics']['fails']})")
    else:
        verdict_bits.append(f"OTM-2 (live Safe-2) is NOT a positive edge "
                            f"(full=${otm2_full}/tr OOS=${otm2_oos}/tr) — the live tier is "
                            f"breakeven/negative")
    if atm_beats_decisively or (_oos(SAFE_VALID_LABEL) or -9e9) > (otm2_oos or -9e9):
        verdict_bits.append(f"ATM (validated Safe-2) beats it: OOS leak +"
                            f"${leak_atm_vs_otm2['oos']['leak_per_trade']}/tr "
                            f"(~${leak_atm_vs_otm2['oos']['leak_per_year']}/yr)")
    if itm2_beats_decisively or (_oos(BOLD_VALID_LABEL) or -9e9) > (otm2_oos or -9e9):
        verdict_bits.append(f"ITM-2 (validated Bold) beats it: OOS leak +"
                            f"${leak_itm2_vs_otm2['oos']['leak_per_trade']}/tr "
                            f"(~${leak_itm2_vs_otm2['oos']['leak_per_year']}/yr)")

    summary = {
        "slug": SLUG,
        "work_package": "WP-5",
        "title": "vwap_continuation STRIKE A/B — the live-edge OTM-2 mis-strike leak",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "cache_edge": str(CACHE_EDGE),
        "last_fill_date_overall": last_fill_overall,
        "last_fill_within_cache_edge": bool(last_fill_overall is None
                                            or last_fill_overall <= str(CACHE_EDGE)),
        "trading_days": n_days,
        "detector": ("VALIDATED _edgehunt_vwap_continuation.detect_signals (byte-for-byte "
                     "the live vwap_continuation_watcher port); signals detected ONCE then "
                     "re-simulated at each strike cell — only the strike offset varies"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "held_constant": {"premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY, "exits": "v15",
                          "snap_radius": MAX_STRIKE_STEPS},
        "strike_offset_convention": {
            "simulator_real": "NEGATIVE=ITM, POSITIVE=OTM (puts strike=atm-off, calls=atm+off; L357-364)",
            "live_params_v15_tier": "NEGATIVE=OTM, POSITIVE=ITM (INVERSE of the simulator)",
            "note": ("each cell carries BOTH offsets; OTM-2 = sim +2 = live_params -2 (the live "
                     "Safe-2 $2K tier per v15_strike_offset_per_tier[2000..10000])"),
        },
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "signals": {"n": len(signals), "on_days": sig_days, "fire_day_pct": fire_day_pct,
                    "side": side_ct, "signals_per_year_est": sigs_per_year},
        "cells": cells,
        "leak": {
            "ATM_minus_OTM2__safe_mis_strike": leak_atm_vs_otm2,
            "ITM2_minus_OTM2__bold_validated_vs_live_tier": leak_itm2_vs_otm2,
            "ITM1_minus_OTM2": leak_itm1_vs_otm2,
            "annualization": (f"leak_per_trade x signals_per_year ({sigs_per_year}/yr = "
                              f"{sig_days}/{n_days} fire-day rate x {TRADING_DAYS_PER_YEAR})"),
        },
        "live_cell_otm2": {
            "full_per_trade": otm2_full, "oos_per_trade": otm2_oos,
            "is_positive_edge": otm2_positive, "clears_11_gate_bar": otm2_clears,
        },
        "decisive": {
            "atm_beats_otm2_decisively": atm_beats_decisively,
            "itm2_beats_otm2_decisively": itm2_beats_decisively,
        },
        "recommended_live_strike": {
            "safe_2": SAFE_VALID_LABEL, "bold": BOLD_VALID_LABEL,
            "current_live_safe_2": LIVE_LABEL,
        },
        "verdict": " | ".join(verdict_bits),
        "DISCLOSURE": {
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "is_oos": "IS=2025 AND OOS=2026 both shown per cell (single-regime artifact guard)",
            "concentration": "top5_day_pct + drop-top5 + OOS-alone drop-top5 (C4/L173)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/C29/L58)",
            "fraud_gates": "random-entry-null (L172) + no-truncation (L171) graduated gates per cell",
            "per_setup_fix": ("C29: the fix is PER-SETUP (vwap_continuation -> its validated "
                              "strike), NOT a blanket v15 tier change — exits/strikes ratified on "
                              "one tier do not transfer to another"),
            "concentration_caveat_L174": ("the same-side sub-pool concern (edge #2/#4 are #1 "
                                          "re-cuts) is about ADDING setups; this A/B re-strikes "
                                          "the EXISTING live edge, so it is not affected"),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[wp5] wrote {OUT}", flush=True)

    print("\n=== WP-5 STRIKE A/B VERDICT (vwap_continuation) ===")
    print(f"signals={len(signals)} on {sig_days} days ({fire_day_pct}%)  ~{sigs_per_year}/yr  "
          f"last_fill={last_fill_overall} (<= {CACHE_EDGE} OK)")
    hdr = f"{'cell':<7}{'n':>4}{'WR%':>6}{'full$':>9}{'IS$':>9}{'OOS$':>9}{'posQ':>6}{'clears':>8}"
    print(hdr)
    for c in cells:
        m = c["metrics"]
        print(f"{c['label']:<7}{m['n']:>4}{str(m['wr_pct']):>6}"
              f"{str(m['overall_per_trade']):>9}{str(m['is_per_trade']):>9}"
              f"{str(m['oos_per_trade']):>9}{m['positive_quarters']:>6}"
              f"{str(m['clears_11_gate_bar']):>8}")
    print(f"\nLEAK (ATM - OTM2): full ${leak_atm_vs_otm2['full_sample']['leak_per_trade']}/tr "
          f"(${leak_atm_vs_otm2['full_sample']['leak_per_year']}/yr)  |  "
          f"OOS ${leak_atm_vs_otm2['oos']['leak_per_trade']}/tr "
          f"(${leak_atm_vs_otm2['oos']['leak_per_year']}/yr)")
    print(f"LEAK (ITM2 - OTM2): full ${leak_itm2_vs_otm2['full_sample']['leak_per_trade']}/tr "
          f"(${leak_itm2_vs_otm2['full_sample']['leak_per_year']}/yr)  |  "
          f"OOS ${leak_itm2_vs_otm2['oos']['leak_per_trade']}/tr "
          f"(${leak_itm2_vs_otm2['oos']['leak_per_year']}/yr)")
    print(f"OTM-2 positive edge? {otm2_positive}  (clears 11-gate bar: {otm2_clears})")
    print(f"VERDICT: {summary['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
