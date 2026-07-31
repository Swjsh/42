"""full_send_arm_ab.py -- pre-registered A/B for the FULL-SEND learning arm (2026-07-31).

PRE-REGISTRATION: analysis/recommendations/prereg-full-send-arm-2026-07-31.json
(frozen 2026-07-31T17:35:46-04:00 ET, BEFORE this script was run).

QUESTION: if one paper arm stops inheriting the COHORT-LEVEL vetoes (block_elite_bull,
block_bull_1100_1200, block_conf_lvl_rec_afternoon, block_level_rejection,
require_bearish_fill_bar) and hard-clamps to minimum size, how many more fills does it take
(the LEARNING RATE, the primary metric) and what does that cost in real-OPRA P&L (the
secondary, expected-negative metric)?

DESIGN: BASELINE and FULL_SEND run at IDENTICAL sizing/exits, so the delta isolates
SELECTION. The live arm additionally hard-clamps qty to min_contracts; because 0DTE option
exits here are per-contract percentages, per-trade P&L scales ~linearly with qty, so the
min-size figure is reported as a disclosed scaling alongside the raw one.

MIN-SIZE ESTIMATOR CORRECTION (2026-07-31 evening, adversarial verifier):
the original implementation computed `scale_factor = MIN_CONTRACTS / mean_qty` and applied
that ONE scalar to the SUM of P&L. That is a BIASED RATIO ESTIMATOR: over a qty range of
3-22 it weights each trade by its own lot size, so large-lot outcomes dominate a figure that
is supposed to describe a uniform 5-lot book. Both headlines INVERTED when corrected
(full population +$1,951 -> negative; recent +$63 -> negative). The correct estimator is
per-trade: MIN_CONTRACTS * SUM(pnl_i / qty_i). See `_minsize()`. Any future edit that
reintroduces a single scale_factor over a sum is the same defect returning.

REAL OPRA FILLS ONLY (use_real_fills=True). Entry+1 convention is the orchestrator's own.
$0, offline. Run: python backtest/full_send_arm_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backtest"))
from lib.orchestrator import run_backtest  # noqa: E402

SPY_CSV = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_CSV = REPO / "backtest" / "data" / "vix_5m_2025-01-01_2026-07-22.csv"
OUT_JSON = REPO / "analysis" / "recommendations" / "full-send-arm-2026-07-31.json"

# Windows, both reported -- no cherry-picking (pre-reg commitment).
FULL_S, FULL_E = dt.date(2025, 1, 2), dt.date(2026, 7, 22)   # full population
RECENT_S, RECENT_E = dt.date(2026, 5, 8), dt.date(2026, 7, 22)  # recent window

# Sizing/exit shape held IDENTICAL across both arms so the delta is pure SELECTION.
# Values mirror the BOLD (risky) live lane the full-send arm would run on.
SHARED = dict(
    use_real_fills=True,
    enable_bullish=True,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    premium_stop_pct=-0.50, premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,
    tp1_premium_pct=1.00, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.15,
    initial_equity=2000.0, strike_offset=2,
    min_triggers_bear=1, min_triggers_bull=2,
    midday_trendline_gate=False,
    entry_bar_body_pct_min=0.20,
    vix_bear_hard_cap=23.0,
)

# The 5 COHORT vetoes under test. BASELINE = as shipped (ON). FULL_SEND = not inherited (OFF).
COHORT_GATES_ON = dict(
    block_elite_bull=True, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0,
    block_bull_1100_1200=True,
    block_conf_lvl_rec_afternoon=True,
    block_level_rejection=True,
    require_bearish_fill_bar=True,
)
COHORT_GATES_OFF = dict(
    block_elite_bull=False, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0,
    block_bull_1100_1200=False,
    block_conf_lvl_rec_afternoon=False,
    block_level_rejection=False,
    require_bearish_fill_bar=False,
)

BASELINE = {**SHARED, **COHORT_GATES_ON}
FULL_SEND = {**SHARED, **COHORT_GATES_OFF}
# The LIVE full-send arm additionally prices the nearer ATM-class contract (fleet_executor
# _tiers_for_arm -> PROBE_STRIKE_TIERS), because its far-OTM bold table priced 15 of its 16
# named-setup ticks on 2026-07-31 under the UNTOUCHED $0.30 min_entry_premium floor. That is a
# REAL P&L-relevant deviation from the OTM-2 cells above, so it is MEASURED here, not assumed.
FULL_SEND_ATM = {**SHARED, **COHORT_GATES_OFF, "strike_offset": 0}

MIN_CONTRACTS = 5  # bold params.json min_contracts (the live full-send clamp)


def _tdate(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.date()


def summarize(res, label: str) -> dict:
    trades = list(res.trades)
    pnl = [float(t.dollar_pnl) for t in trades]
    total = sum(pnl)
    by_day = defaultdict(float)
    qtys = []
    # Per-CONTRACT P&L (pnl_i / qty_i) -- the basis of the unbiased min-size estimator.
    per_contract: list[float] = []
    pc_by_day = defaultdict(float)
    n_missing_qty = 0
    for t in trades:
        by_day[_tdate(t)] += float(t.dollar_pnl)
        q = getattr(t, "contracts", None) or getattr(t, "qty", None)
        if q:
            qtys.append(int(q))
            pc = float(t.dollar_pnl) / int(q)
            per_contract.append(pc)
            pc_by_day[_tdate(t)] += pc
        else:
            n_missing_qty += 1
    days_traded = len(by_day)
    wins = [p for p in pnl if p > 0]
    return {
        "label": label,
        "n_trades": len(trades),
        "days_with_a_trade": days_traded,
        "total_pnl": round(total, 2),
        "per_trade_expectancy": round(total / len(trades), 2) if trades else 0.0,
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "worst_trade": round(min(pnl), 2) if pnl else 0.0,
        "best_trade": round(max(pnl), 2) if pnl else 0.0,
        "worst_day": round(min(by_day.values()), 2) if by_day else 0.0,
        "best_day": round(max(by_day.values()), 2) if by_day else 0.0,
        "mean_qty": round(sum(qtys) / len(qtys), 2) if qtys else None,
        "min_qty": min(qtys) if qtys else None,
        "max_qty": max(qtys) if qtys else None,
        # Unbiased per-contract aggregates (see module docstring + _minsize).
        "_pc_sum": round(sum(per_contract), 6) if per_contract else None,
        "_pc_worst_trade": round(min(per_contract), 6) if per_contract else None,
        "_pc_worst_day": round(min(pc_by_day.values()), 6) if pc_by_day else None,
        "_n_trades_with_qty": len(per_contract),
        "_n_trades_missing_qty": n_missing_qty,
        "_by_day": {str(k): round(v, 2) for k, v in sorted(by_day.items())},
        "_setups": dict(Counter(str(getattr(t, "setup_name", "?")) for t in trades)),
    }


def _minsize(s: dict) -> dict | None:
    """UNBIASED min-size projection: MIN_CONTRACTS * SUM(pnl_i / qty_i).

    NOT `(MIN_CONTRACTS / mean_qty) * SUM(pnl_i)` -- that biased ratio estimator was the
    original implementation and it INVERTED both headline signs (see module docstring).
    Every field here is a per-trade recomputation, never a scalar rescale of an aggregate."""
    if not s.get("_n_trades_with_qty"):
        return None
    return {
        "method": "MIN_CONTRACTS * sum(pnl_i / qty_i)  [per-trade, unbiased]",
        "min_contracts": MIN_CONTRACTS,
        "total_pnl_minsize": round(MIN_CONTRACTS * s["_pc_sum"], 2),
        "worst_trade_minsize": round(MIN_CONTRACTS * s["_pc_worst_trade"], 2),
        "worst_day_minsize": round(MIN_CONTRACTS * s["_pc_worst_day"], 2),
        "n_trades_scaled": s["_n_trades_with_qty"],
        "n_trades_missing_qty": s["_n_trades_missing_qty"],
        "observed_qty_range": [s.get("min_qty"), s.get("max_qty")],
        "_disclosure": (
            "Per-trade rescale to a uniform MIN_CONTRACTS lot. Exits are per-contract "
            "percentages, so pnl_i/qty_i is the per-contract outcome of trade i and the sum "
            "is the min-size book. NOT exact: the per-trade risk cap and the min_entry_premium "
            "floor could have admitted or refused a DIFFERENT trade set at a 5-lot, and this "
            "reweights the SAME trades rather than re-running selection at min size. "
            "SUPERSEDES the original scale_factor=MIN_CONTRACTS/mean_qty applied to a SUM, "
            "which was a biased ratio estimator over qty 3-22 and inverted both headline signs."
        ),
    }


def run_window(s: dt.date, e: dt.date, n_sessions: int, tag: str) -> dict:
    print(f"\n=== {tag}: {s} .. {e} ===", flush=True)
    print("  running BASELINE (cohort gates ON) ...", flush=True)
    base = summarize(run_backtest(SPY, VIX, start_date=s, end_date=e, **BASELINE), "BASELINE")
    print("  running FULL_SEND (cohort gates OFF, OTM-2) ...", flush=True)
    full = summarize(run_backtest(SPY, VIX, start_date=s, end_date=e, **FULL_SEND), "FULL_SEND")
    print("  running FULL_SEND_ATM (cohort gates OFF, ATM -- the LIVE arm's strike) ...", flush=True)
    full_atm = summarize(run_backtest(SPY, VIX, start_date=s, end_date=e, **FULL_SEND_ATM),
                         "FULL_SEND_ATM")
    full_atm["fills_per_session"] = (round(full_atm["n_trades"] / n_sessions, 4)
                                     if n_sessions else 0.0)

    base["fills_per_session"] = round(base["n_trades"] / n_sessions, 4) if n_sessions else 0.0
    full["fills_per_session"] = round(full["n_trades"] / n_sessions, 4) if n_sessions else 0.0
    uplift = (full["n_trades"] / base["n_trades"]) if base["n_trades"] else float("inf")

    # Min-size projection: the live arm clamps every entry to MIN_CONTRACTS. Both arms above
    # ran at the same equity-derived qty, so restate FULL_SEND's book at a uniform min lot --
    # PER TRADE (see _minsize), never as one scale factor over the sum.
    full_minsize = _minsize(full)

    # --- pre-registered failure checks -------------------------------------
    kill_threshold = -0.50 * SHARED["initial_equity"]
    worst_day_ms = (full_minsize or {}).get("worst_day_minsize", full["worst_day"])
    worst_trade_ms = (full_minsize or {}).get("worst_trade_minsize", full["worst_trade"])
    checks = {
        "F1_kill_switch_breach": {
            "threshold": kill_threshold,
            "observed_worst_day_minsize": worst_day_ms,
            "FAIL": bool(worst_day_ms <= kill_threshold),
        },
        "F2_per_trade_bound": {
            "baseline_worst_trade": base["worst_trade"],
            "fullsend_worst_trade_minsize": worst_trade_ms,
            "FAIL": bool(worst_trade_ms < base["worst_trade"]),
        },
        "F4_no_learning_uplift": {
            "required_uplift_x": 2.0,
            "observed_uplift_x": round(uplift, 3),
            "FAIL": bool(uplift < 2.0),
        },
    }
    # ATM cell -- the LIVE arm's actual strike. Restated at min size the same (unbiased) way.
    atm_minsize = _minsize(full_atm)
    if atm_minsize is not None:
        checks["F1_kill_switch_breach_ATM"] = {
            "threshold": kill_threshold,
            "observed_worst_day_minsize": atm_minsize["worst_day_minsize"],
            "FAIL": bool(atm_minsize["worst_day_minsize"] <= kill_threshold),
        }
        checks["F2_per_trade_bound_ATM"] = {
            "baseline_worst_trade": base["worst_trade"],
            "fullsend_worst_trade_minsize": atm_minsize["worst_trade_minsize"],
            "FAIL": bool(atm_minsize["worst_trade_minsize"] < base["worst_trade"]),
        }
    return {"window": {"start": str(s), "end": str(e), "sessions": n_sessions},
            "baseline": base, "full_send": full, "full_send_minsize": full_minsize,
            "full_send_atm": full_atm, "full_send_atm_minsize": atm_minsize,
            "trade_uplift_x": round(uplift, 3),
            "pnl_delta_raw": round(full["total_pnl"] - base["total_pnl"], 2),
            "prereg_checks": checks}


if __name__ == "__main__":
    print("loading bars ...", flush=True)
    SPY = pd.read_csv(SPY_CSV)
    VIX = pd.read_csv(VIX_CSV)
    _ts = pd.to_datetime(SPY["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    _d = _ts.dt.date
    sess_full = len({d for d in _d if FULL_S <= d <= FULL_E})
    sess_recent = len({d for d in _d if RECENT_S <= d <= RECENT_E})
    print(f"sessions: full={sess_full} recent={sess_recent}", flush=True)

    out = {
        "rule_id": "full-send-arm-2026-07-31",
        "prereg": "analysis/recommendations/prereg-full-send-arm-2026-07-31.json",
        "generated_at_et": "2026-07-31 (after-hours build window)",
        "corrected_at_et": "2026-07-31 evening (min-size estimator correction, see _corrections)",
        "_corrections": [
            {
                "id": "minsize-biased-ratio-estimator",
                "found_by": "adversarial verifier, 2026-07-31 evening",
                "defect": ("min-size P&L used scale_factor = MIN_CONTRACTS / mean_qty applied to "
                           "the SUM of P&L -- a biased ratio estimator over an observed qty range "
                           "of 3-22, which weights each trade by its own lot size."),
                "correct_estimator": "MIN_CONTRACTS * sum(pnl_i / qty_i)  [per-trade]",
                "superseded_values": {"full_population_minsize": 1951.0, "recent_minsize": 63.0},
                "effect": "BOTH headline signs INVERT to negative. See windows.*.full_send_minsize.",
                "also_removed": ("the _disclosure claim that the scaling 'is exact' -- an "
                                 "affirmatively false statement of method."),
            },
            {
                "id": "atm-strike-not-reverted-on-the-shipped-path",
                "found_by": "adversarial verifier, 2026-07-31 evening",
                "defect": ("this scorecard and commit e28d210c said the ATM strike override was "
                           "REVERTED. It was reverted in fleet_executor._tiers_for_arm ONLY, and "
                           "the shipped full-send lane (_full_send_plan) never calls that -- it "
                           "prices PROBE_STRIKE_TIERS, offset 0 (ATM) at $2K equity."),
                "resolution": ("KEEP ATM (it is what clears the $0.30 min_entry_premium floor "
                               "that refused risky-1 all of 2026-07-31 -- the point of the arm) "
                               "and label every surface ATM + UNMEASURED-AT-THIS-STRIKE."),
                "measurement_status": ("the headline full_send cell was measured at "
                                       "strike_offset=2 (OTM-2); production trades offset=0. "
                                       "That cell DOES NOT APPLY to the shipped lane -- OP-16 "
                                       "sim-accuracy. The incremental trades this arm adds have "
                                       "NO valid measurement at their actual strike."),
            },
        ],
        "fidelity": "REAL OPRA FILLS (use_real_fills=True). No synthetic pricing anywhere.",
        "design": ("BASELINE vs FULL_SEND at IDENTICAL sizing/exits so the delta isolates "
                   "SELECTION. FULL_SEND = the 5 cohort vetoes not inherited."),
        "cohort_gates_dropped": sorted(COHORT_GATES_OFF),
        "windows": {},
    }
    out["windows"]["full_population"] = run_window(FULL_S, FULL_E, sess_full, "FULL POPULATION")
    out["windows"]["recent"] = run_window(RECENT_S, RECENT_E, sess_recent, "RECENT")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    for wname, w in out["windows"].items():
        b, f = w["baseline"], w["full_send"]
        print(f"\n[{wname}] sessions={w['window']['sessions']}")
        print(f"  BASELINE : n={b['n_trades']:4d}  {b['fills_per_session']:.3f}/sess  "
              f"total=${b['total_pnl']:>10,.2f}  exp=${b['per_trade_expectancy']:>7.2f}  "
              f"WR={b['win_rate']:.1%}  worstday=${b['worst_day']:,.2f}")
        print(f"  FULL_SEND: n={f['n_trades']:4d}  {f['fills_per_session']:.3f}/sess  "
              f"total=${f['total_pnl']:>10,.2f}  exp=${f['per_trade_expectancy']:>7.2f}  "
              f"WR={f['win_rate']:.1%}  worstday=${f['worst_day']:,.2f}")
        print(f"  uplift={w['trade_uplift_x']}x   pnl_delta_raw=${w['pnl_delta_raw']:,.2f}")
        a = w["full_send_atm"]
        print(f"  FS_ATM   : n={a['n_trades']:4d}  {a['fills_per_session']:.3f}/sess  "
              f"total=${a['total_pnl']:>10,.2f}  exp=${a['per_trade_expectancy']:>7.2f}  "
              f"WR={a['win_rate']:.1%}  worstday=${a['worst_day']:,.2f}")
        if w["full_send_atm_minsize"]:
            m = w["full_send_atm_minsize"]
            print(f"  FS_ATM @min-size(5*sum(pnl/qty)): total=${m['total_pnl_minsize']:,.2f}"
                  f"  worstday=${m['worst_day_minsize']:,.2f}  worsttrade=${m['worst_trade_minsize']:,.2f}")
        if w["full_send_minsize"]:
            m = w["full_send_minsize"]
            print(f"  FULL_SEND @min-size(5*sum(pnl/qty)): total=${m['total_pnl_minsize']:,.2f}"
                  f"  worstday=${m['worst_day_minsize']:,.2f}  worsttrade=${m['worst_trade_minsize']:,.2f}"
                  f"  n_scaled={m['n_trades_scaled']} qty_range={m['observed_qty_range']}")
        for k, v in w["prereg_checks"].items():
            print(f"    {k}: {'FAIL' if v['FAIL'] else 'pass'}  {v}")
