"""STRATEGY-SPACE GRIND — sweep STRIKE x GATE x STOP on real OPRA fills.

A standalone search driver (does NOT touch gate_frequency_frontier.py). For each
cell in the STRIKE x GATE x STOP grid it runs the real-fills backtest over the
full OPRA window and returns the canonical metric bundle:

    {edge_capture (OP-16), expectancy, wr, trades_per_day, max_dd, wf, n}

Machinery (run_cfg / _summ / validate / _wf / edge_capture_block / the J anchor
set + EDGE_CAPTURE_MAX/REJECT) is cloned from
backtest/autoresearch/fleet_gate_sweetspot.py so this driver agrees byte-for-byte
with the established OP-16 verdict ladder. Real OPRA fills ONLY (C1), risk-gate
assert ON (GAMMA_RISK_GATE_ASSERT defaults to 1 — backtest-risk == live-risk).

AXES
----
STRIKES (run_backtest `strike_offset` kwarg, SIMULATOR convention where
NEGATIVE = ITM, 0 = ATM, POSITIVE = OTM — confirmed against
orchestrator._params_to_kwargs L363-382 / the strike_offset kwarg default -2 at
L497 / the bear/bull resolution L770-771):
    OTM-3 = +3, OTM-2 = +2, OTM-1 = +1, ATM = 0, ITM-1 = -1, ITM-2 = -2
  To make this axis bind, the per-tier table (v15_strike_offset_per_tier) and the
  legacy strike_offset_itm are STRIPPED from the params dict (otherwise the
  $2K-equity tier lookup forces OTM-2 and ignores the swept value — C14 dead-knob
  trap). strike_offset is then passed as a direct run_backtest kwarg.

GATES:
    control = no patch (the swept-strike production config)
    L2      = the validated sweet-spot patch:
              {block_level_rejection:false, midday_trendline_gate:false,
               entry_bar_body_pct_min:0.0, filter_9_vol_multiplier:0.4,
               ribbon_spread_min_cents:20}
              (ribbon_spread_min_cents is the orchestrator-recognised key; the
               params.json field ribbon_min_spread_cents is a silent dead knob —
               C14/L70, verified in fleet_gate_sweetspot.py.)

STOPS:
    chart_level  = chart/level stop PRIMARY: premium_stop_pct = -0.50 (the live
                   catastrophe cap; the chart-level / ribbon-flip / profit-lock
                   exits bind first). This is what the live engine trades.
    pct_-8       = premium-% stop at -8%  (premium_stop_pct = -0.08)
    pct_-50      = premium-% stop at -50% (premium_stop_pct = -0.50, == the
                   live catastrophe cap; reported separately for completeness)
  All three are applied to BOTH bear AND bull via premium_stop_pct_bear/bull so
  the params.json per-side -0.50 caps cannot override the swept value.

GAPS (not fabricated):
  - DOLLAR-ANCHORED STOP is NOT expressible for the generic
    BEARISH_REJECTION_RIDE_THE_RIBBON path. simulator_real.simulate_trade_real
    exposes only premium_stop_pct + the level/chart stop; the dollar-anchored
    stop (j_vwap_cont_dollar_stop_safe) lives ONLY in the per-setup
    live_order_resolver / vwap_continuation WP-8 path, not in run_backtest's
    generic order path (grep-confirmed: no dollar_stop / abs_stop knob in
    simulator_real.py or orchestrator.py). It is therefore OMITTED here rather
    than faked. pct_-50 and chart_level coincide numerically (both -0.50): the
    cell is kept for axis completeness and labelled.

PROPOSE-ONLY: writes analysis/recommendations/strategy-space-grind.json; does NOT
edit params.json.

Run:  backtest/.venv/Scripts/python.exe -m autoresearch.strategy_space_grind
  Single cell (smoke):
      backtest/.venv/Scripts/python.exe -m autoresearch.strategy_space_grind --cell ITM-2:L2:pct_-8
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parent.parent     # backtest/
_ROOT = _REPO.parent                               # repo root
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reproducibility / parity: keep the live-risk assertion ON unless the caller
# explicitly opts out. The driver never silently disables it.
os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "1")

from lib.orchestrator import run_backtest            # noqa: E402
from autoresearch.runner import load_data            # noqa: E402

PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
OUT_PATH = _ROOT / "analysis" / "recommendations" / "strategy-space-grind.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 18)            # OPRA real-fill coverage cap (matches fleet_gate_sweetspot)
OOS_BOUNDARY = dt.date(2026, 1, 1)   # 2025 IS / 2026 OOS (calendar-year chronological split)

SAFE_EQUITY = 2000.0                  # live Safe account size

# --- OP-16 J source-of-truth anchors (cloned from fleet_gate_sweetspot.py) ---
J_WINNERS = [
    (dt.date(2026, 4, 29), "P", 342.0),   # SPY 710P x6
    (dt.date(2026, 5, 1), "P", 470.0),    # SPY 721P x20
    (dt.date(2026, 5, 4), "P", 730.0),    # SPY 721P x10
]
J_LOSERS = [
    (dt.date(2026, 5, 5), "P", -260.0),   # SPY 722P x20
    (dt.date(2026, 5, 6), "P", -300.0),   # SPY 730P x10
    (dt.date(2026, 5, 7), "C", -45.0),    # SPY 734C x3
]
EDGE_CAPTURE_MAX = 1542.0
EDGE_CAPTURE_REJECT_BELOW = 771.0     # < 50% of max => REJECT (OP-16)

# ---------------- AXES ----------------
# strike_offset is SIMULATOR convention: negative = ITM, 0 = ATM, positive = OTM.
STRIKES: dict[str, int] = {
    "OTM-3": 3,
    "OTM-2": 2,
    "OTM-1": 1,
    "ATM": 0,
    "ITM-1": -1,
    "ITM-2": -2,
}

# The validated sweet-spot gate patch (L2). control = no patch.
L2_PATCH: dict = {
    "block_level_rejection": False,
    "midday_trendline_gate": False,
    "entry_bar_body_pct_min": 0.0,
    "filter_9_vol_multiplier": 0.4,
    "ribbon_spread_min_cents": 20,
}
GATES: dict[str, dict] = {
    "control": {},
    "L2": L2_PATCH,
}

# Premium-stop value per stop label. None is never used here (all express a
# premium_stop_pct); the dollar-anchored stop is intentionally absent (see GAPS).
STOPS: dict[str, float] = {
    "chart_level": -0.50,   # chart/level stop primary (live catastrophe cap)
    "pct_-8": -0.08,
    "pct_-50": -0.50,
}


# ---------- trade helpers (cloned) ----------
def _tdate(t) -> dt.date:
    ts = t.entry_time_et
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts.date()


def _days(trades) -> int:
    return len(set(_tdate(t) for t in trades))


def _summ(trades, lo: Optional[dt.date] = None, hi: Optional[dt.date] = None) -> dict:
    sub = [t for t in trades
           if (lo is None or _tdate(t) >= lo) and (hi is None or _tdate(t) <= hi)]
    if not sub:
        return {"n": 0, "total": 0.0, "wr": 0.0, "exp": 0.0, "tr_per_day": 0.0,
                "trading_days": 0, "max_dd": 0.0, "bear_n": 0, "bear_pnl": 0.0,
                "bull_n": 0, "bull_pnl": 0.0}
    pnls = [float(t.dollar_pnl) for t in sub]
    wins = [p for p in pnls if p > 0]
    bears = [t for t in sub if "BULLISH" not in str(t.setup)]
    bulls = [t for t in sub if "BULLISH" in str(t.setup)]
    nd = _days(sub)

    def _sort_key(t):
        ts = t.entry_time_et
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.replace(tzinfo=None)
        return ts
    ordered = sorted(sub, key=_sort_key)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in ordered:
        eq += float(t.dollar_pnl)
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {
        "n": len(sub), "total": round(sum(pnls), 2),
        "wr": round(len(wins) / len(sub), 4), "exp": round(sum(pnls) / len(sub), 2),
        "trading_days": nd,
        "tr_per_day": round(len(sub) / nd, 3) if nd else 0.0,
        "max_dd": round(mdd, 2),
        "bear_n": len(bears), "bear_pnl": round(sum(t.dollar_pnl for t in bears), 2),
        "bull_n": len(bulls), "bull_pnl": round(sum(t.dollar_pnl for t in bulls), 2),
    }


# ---------- OP-16 edge_capture (sliced from the SAME full-window run) ----------
def edge_capture_block(full_trades) -> dict:
    per_day: dict[str, dict] = {}

    def _day_pnl(d: dt.date) -> tuple[float, int]:
        day_t = [t for t in full_trades if _tdate(t) == d]
        return round(sum(float(t.dollar_pnl) for t in day_t), 2), len(day_t)

    winner_sum = 0.0
    for d, _dir, real in J_WINNERS:
        pnl, n = _day_pnl(d)
        winner_sum += pnl
        per_day[str(d)] = {"role": "WINNER", "j_real_pnl": real, "engine_pnl": pnl, "engine_n": n}

    loser_penalty = 0.0
    for d, _dir, real in J_LOSERS:
        pnl, n = _day_pnl(d)
        penalty = max(0.0, -pnl)
        loser_penalty += penalty
        per_day[str(d)] = {"role": "LOSER", "j_real_pnl": real, "engine_pnl": pnl,
                           "engine_n": n, "loss_penalty": round(penalty, 2)}

    edge_capture = round(winner_sum - loser_penalty, 2)
    return {
        "edge_capture": edge_capture,
        "winner_day_pnl_sum": round(winner_sum, 2),
        "loser_day_loss_penalty": round(loser_penalty, 2),
        "edge_capture_max": EDGE_CAPTURE_MAX,
        "edge_capture_pct_of_max": round(edge_capture / EDGE_CAPTURE_MAX, 3),
        "reject_below": EDGE_CAPTURE_REJECT_BELOW,
        "rejected_by_op16": bool(edge_capture < EDGE_CAPTURE_REJECT_BELOW),
        "per_anchor_day": per_day,
    }


# ---------- walk-forward / OOS validation (cloned) ----------
def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _wf(is_total, n_is, oos_total, n_oos) -> float:
    if n_is == 0 or n_oos == 0 or is_total == 0:
        return 0.0
    return (oos_total / n_oos) / (is_total / n_is)


def validate(trades, label: str) -> dict:
    is_t = [t for t in trades if _tdate(t) < OOS_BOUNDARY]
    oos_t = [t for t in trades if _tdate(t) >= OOS_BOUNDARY]
    is_s, oos_s = _summ(is_t), _summ(oos_t)
    wf = _wf(is_s["total"], is_s["n"], oos_s["total"], oos_s["n"])
    by_q: dict[str, list] = {}
    for t in trades:
        by_q.setdefault(_quarter(_tdate(t)), []).append(float(t.dollar_pnl))
    quarters = {q: {"n": len(v), "total": round(sum(v), 2), "exp": round(sum(v) / len(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)
    q_frac = round(q_pos / len(quarters), 3) if quarters else 0.0
    return {
        "label": label, "IS": is_s, "OOS": oos_s, "wf_per_trade": round(wf, 3),
        "quarters": quarters, "quarter_positive_fraction": q_frac,
        "gate": {"oos_positive": oos_s["total"] > 0, "wf_ge_0.70": wf >= 0.70,
                 "sub_window_stable": q_frac >= 0.60,
                 "PASS": bool(oos_s["total"] > 0 and wf >= 0.70 and q_frac >= 0.60)},
    }


# ---------- config builder: strip the per-tier table so strike_offset binds ----------
def _strip_strike_keys(params: dict) -> dict:
    """Remove the per-tier strike table + legacy ITM key so the swept strike_offset
    kwarg is the SOLE strike authority (C14 dead-knob avoidance)."""
    p = copy.deepcopy(params)
    p.pop("v15_strike_offset_per_tier", None)
    p.pop("strike_offset_itm", None)
    return p


def run_cell(spy, vix, base_params: dict, strike_offset: int, gate_patch: dict,
             stop_pct: float, equity: float = SAFE_EQUITY):
    """Run the real-fills backtest for ONE (strike, gate, stop) cell.

    Returns the trade list. strike_offset is SIMULATOR convention
    (negative=ITM, 0=ATM, positive=OTM). The premium stop is applied to BOTH
    bear and bull so the params.json per-side caps cannot override it.
    """
    p = _strip_strike_keys(base_params)
    p.update(copy.deepcopy(gate_patch))
    p["use_real_fills"] = True
    # Force the premium stop on both sides through params_overrides (these are
    # translated by _params_to_kwargs and applied in run_backtest).
    p["premium_stop_pct"] = stop_pct
    p["premium_stop_pct_bear"] = stop_pct
    p["premium_stop_pct_bull"] = stop_pct
    res = run_backtest(
        spy, vix, start_date=START, end_date=END,
        use_real_fills=True, params_overrides=p, initial_equity=equity,
        # Direct kwarg = the sole strike authority now that the tier table is stripped.
        strike_offset=int(strike_offset),
        # Mirror the per-side premium stop at the kwarg level too (belt-and-suspenders;
        # the params_overrides path also sets these, but a direct kwarg removes any
        # default-guard ambiguity in run_backtest).
        premium_stop_pct=float(stop_pct),
        premium_stop_pct_bear=float(stop_pct),
        premium_stop_pct_bull=float(stop_pct),
    )
    return res.trades


def metrics_for(trades) -> dict:
    """The required bundle: edge_capture, expectancy, wr, trades_per_day, max_dd, wf, n."""
    s = _summ(trades)
    ec = edge_capture_block(trades)
    val = validate(trades, "cell")
    return {
        "n": s["n"],
        "edge_capture": ec["edge_capture"],
        "edge_capture_pct_of_max": ec["edge_capture_pct_of_max"],
        "rejected_by_op16": ec["rejected_by_op16"],
        "expectancy": s["exp"],
        "wr": s["wr"],
        "trades_per_day": s["tr_per_day"],
        "max_dd": s["max_dd"],
        "wf": val["wf_per_trade"],
        "total": s["total"],
        "trading_days": s["trading_days"],
        "oos_positive": val["gate"]["oos_positive"],
        "validation_pass": val["gate"]["PASS"],
        "_edge_capture_detail": ec,
        "_validation": val,
    }


def _cell_id(strike_label: str, gate_label: str, stop_label: str) -> str:
    return f"{strike_label}:{gate_label}:{stop_label}"


def run_single_cell(spy, vix, params, strike_label, gate_label, stop_label) -> dict:
    trades = run_cell(spy, vix, params, STRIKES[strike_label],
                      GATES[gate_label], STOPS[stop_label])
    m = metrics_for(trades)
    m["cell"] = _cell_id(strike_label, gate_label, stop_label)
    m["strike_offset_simulator"] = STRIKES[strike_label]
    m["gate_patch"] = GATES[gate_label]
    m["stop_premium_pct"] = STOPS[stop_label]
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", default=None,
                    help="Run ONE cell only, e.g. ITM-2:L2:pct_-8 (smoke test).")
    args = ap.parse_args()

    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    spy, vix = load_data(START, END)
    print(f"data spy={len(spy)} vix={len(vix)}; window {START}..{END} "
          f"(real OPRA fills; GAMMA_RISK_GATE_ASSERT={os.environ.get('GAMMA_RISK_GATE_ASSERT')})")

    if args.cell:
        try:
            sl, gl, stl = args.cell.split(":")
        except ValueError:
            print(f"bad --cell '{args.cell}'; want STRIKE:GATE:STOP "
                  f"(strikes {list(STRIKES)}, gates {list(GATES)}, stops {list(STOPS)})")
            return 2
        if sl not in STRIKES or gl not in GATES or stl not in STOPS:
            print(f"unknown axis value in '{args.cell}'. strikes={list(STRIKES)} "
                  f"gates={list(GATES)} stops={list(STOPS)}")
            return 2
        m = run_single_cell(spy, vix, params, sl, gl, stl)
        print(f"\nCELL {m['cell']}: n={m['n']} EC=${m['edge_capture']:+.0f} "
              f"({m['edge_capture_pct_of_max']:.0%} of max, op16_reject={m['rejected_by_op16']}) "
              f"exp=${m['expectancy']:+.0f} WR={m['wr']:.0%} {m['trades_per_day']}/day "
              f"maxDD=${m['max_dd']:+.0f} wf={m['wf']} total=${m['total']:+.0f}")
        print(json.dumps({k: v for k, v in m.items() if not k.startswith("_")}, indent=2))
        return 0

    grid: list[dict] = []
    for sl in STRIKES:
        for gl in GATES:
            for stl in STOPS:
                m = run_single_cell(spy, vix, params, sl, gl, stl)
                grid.append(m)
                print(f"  {m['cell']:24s} n={m['n']:3d} EC=${m['edge_capture']:+7.0f} "
                      f"exp=${m['expectancy']:+6.0f} WR={m['wr']:.0%} "
                      f"{m['trades_per_day']}/day dd=${m['max_dd']:+7.0f} wf={m['wf']:+.2f} "
                      f"-> {'OP16-REJECT' if m['rejected_by_op16'] else 'op16-ok'}")

    grid.sort(key=lambda r: r["edge_capture"], reverse=True)
    out: dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": ("STRATEGY-SPACE GRIND: STRIKE x GATE x STOP sweep on real OPRA fills, "
                    "OP-16 edge_capture + expectancy/wr/freq/maxDD/wf/n per cell. PROPOSE-ONLY."),
        "window": f"{START}..{END} (OPRA coverage cap)",
        "oos_split": {"IS": f"<{OOS_BOUNDARY}", "OOS": f">={OOS_BOUNDARY}"},
        "equity": SAFE_EQUITY,
        "risk_gate_assert": os.environ.get("GAMMA_RISK_GATE_ASSERT"),
        "axes": {
            "STRIKES_simulator_convention_neg_is_ITM": STRIKES,
            "GATES": GATES,
            "STOPS_premium_pct": STOPS,
        },
        "gaps": [
            ("DOLLAR-ANCHORED STOP not expressible for the generic "
             "BEARISH_REJECTION_RIDE_THE_RIBBON path: simulator_real.simulate_trade_real "
             "exposes only premium_stop_pct + the level/chart stop; the dollar-anchored "
             "stop (j_vwap_cont_dollar_stop_safe) lives only in the per-setup "
             "live_order_resolver / vwap_continuation WP-8 path. Omitted, not faked."),
            ("pct_-50 and chart_level both set premium_stop_pct=-0.50; chart_level is the "
             "live config name (chart/ribbon/profit-lock bind first), pct_-50 is the "
             "explicit premium-stop label. Kept distinct for axis completeness."),
        ],
        "grid_sorted_by_edge_capture": grid,
        "discipline_notes": [
            "Real OPRA fills only (C1). GAMMA_RISK_GATE_ASSERT on (backtest-risk==live-risk).",
            "strike_offset SIMULATOR convention (neg=ITM); per-tier table stripped so the swept value binds.",
            "edge_capture sliced from the SAME full-window run (engine is stateful; 1-day runs starve warmup).",
            "Propose-only: params.json NOT edited.",
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}  ({len(grid)} cells)")
    top = grid[0]
    print(f"TOP by edge_capture: {top['cell']} EC=${top['edge_capture']:+.0f} "
          f"exp=${top['expectancy']:+.0f} wf={top['wf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
