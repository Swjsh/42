"""GATE-FREQUENCY AUDIT — leave-one-out on the LIVE config, scored on TOTAL P&L.

MISSION (frequency is the constraint, not edge quality):
    The live engine trades ~1.5x/month. For a $2K account total growth =
    expectancy x frequency x size, so a gate that lifts per-trade expectancy
    but slashes trade count can LOWER total P&L. This audit finds the FEW gates
    (if any) that are OVER-RESTRICTIVE: the trades they remove are net-positive
    or net-neutral, so relaxing them RAISES (or holds) total P&L while adding
    frequency. Most gates are expected to EARN their keep (remove net-losers) —
    that is a fine, honest result.

METHOD:
    1. Baseline = full live engine (params.json, real OPRA fills, 2025-01..2026-05-29).
    2. For each relaxable BEAR-path gate, re-run with THAT gate relaxed/removed,
       holding everything else live. Record:
         - extra trades admitted (delta vs baseline, BEAR side)
         - the TOTAL P&L of the admitted population
         - new total P&L / WR / exp / monthly rate
    3. Classify EARNS_KEEP (removed pop net-negative) vs OVER_RESTRICTIVE
       (removed pop net-positive-or-neutral AND total P&L rises/holds).
    4. OOS-validate every OVER_RESTRICTIVE candidate (chronological split,
       sign-stable, WF>=0.70, not driven by 2-3 outliers).

DISCIPLINE:
    - Total P&L (account growth) is the metric, NOT per-trade exp / edge_capture.
    - But a loosening that tanks per-trade exp into the red is still bad even if
      count rises: require the admitted population net-positive-or-neutral.
    - Causality preserved (we relax gates; we never add look-ahead).
    - Audit SAFE; flag (don't assume) Bold transfer (C29).
    - Real fills. Pure Python. $0. Propose-only; does NOT edit live params.

OUTPUT:
    analysis/recommendations/gate-frequency-audit.json (baseline + per-gate deltas
    + verdicts) and a printed ranked table.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch import runner  # noqa: E402

PARAMS_PATH = REPO / "automation" / "state" / "params.json"
OUT_PATH = REPO / "analysis" / "recommendations" / "gate-frequency-audit.json"

# Full real-OPRA window. Option bars only exist through ~2026-05-29 (honest limit).
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 5, 29)
# Chronological OOS split: train (IS) = 2025 calendar year; test (OOS) = 2026 YTD.
IS_START, IS_END = dt.date(2025, 1, 2), dt.date(2025, 12, 31)
OOS_START, OOS_END = dt.date(2026, 1, 1), dt.date(2026, 5, 29)

MONTHS_FULL = (FULL_END.year - FULL_START.year) * 12 + (FULL_END.month - FULL_START.month) + 1


def _load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))


def _live() -> dict:
    p = _load_params()
    p["use_real_fills"] = True
    return p


def _trade_key(t) -> tuple:
    """A stable identity for a taken trade so we can diff populations."""
    et = t.entry_time_et
    # normalise tz for hashing
    if hasattr(et, "tz_localize") and getattr(et, "tz", None) is not None:
        et = et.tz_localize(None)
    elif hasattr(et, "tzinfo") and et.tzinfo is not None:
        et = et.replace(tzinfo=None)
    return (et.isoformat(), t.strike, "C" if "BULLISH" in t.setup else "P")


def _run(params: dict, spy, vix, start, end) -> dict:
    result, _ = runner.run_with_params(params, start, end, spy, vix)
    trades = list(result.trades)
    rows = {}
    for t in trades:
        rows[_trade_key(t)] = float(getattr(t, "dollar_pnl", 0.0))
    pnls = list(rows.values())
    n = len(pnls)
    n_win = sum(1 for x in pnls if x > 0)
    total = sum(pnls)
    bear = [t for t in trades if "BULLISH" not in t.setup]
    return {
        "n": n,
        "n_bear": len(bear),
        "wr": round(n_win / n, 4) if n else 0.0,
        "total": round(total, 2),
        "exp": round(total / n, 2) if n else 0.0,
        "rows": rows,           # key -> pnl, for population diff
        "trades": trades,
    }


def _admitted_population(base_rows: dict, relaxed_rows: dict) -> dict:
    """Population the relaxed gate ADMITS that the baseline blocked.

    A relaxed gate can also SHIFT downstream selection (quality lock, V_PULLBACK,
    re-entry) — so we report BOTH: the strict set difference (keys present only
    when relaxed) and the net total-P&L delta (the headline). The set-difference
    P&L is the 'removed population' the gate was costing/saving.
    """
    added_keys = [k for k in relaxed_rows if k not in base_rows]
    dropped_keys = [k for k in base_rows if k not in relaxed_rows]  # rare: selection shift
    added_pnl = sum(relaxed_rows[k] for k in added_keys)
    dropped_pnl = sum(base_rows[k] for k in dropped_keys)
    added_win = sum(1 for k in added_keys if relaxed_rows[k] > 0)
    return {
        "n_added": len(added_keys),
        "n_dropped": len(dropped_keys),
        "added_pnl": round(added_pnl, 2),
        "dropped_pnl": round(dropped_pnl, 2),
        "added_wr": round(added_win / len(added_keys), 4) if added_keys else None,
        "net_population_pnl": round(added_pnl - dropped_pnl, 2),  # what the gate's removal nets
        "added_pnls": [round(relaxed_rows[k], 2) for k in added_keys],
        "added_keys": [list(k) for k in added_keys],
    }


# ── Gate definitions: each maps to a single-variable relaxation of the live config ──
# `mut` receives a deep copy of the live params and relaxes ONE gate.
def _g_momentum_off(p):  # ribbon momentum gate (currently armed at 0 via is-not-None bug)
    p["min_ribbon_momentum_cents"] = None

def _g_midday_trendline_off(p):
    p["midday_trendline_gate"] = False

def _g_vix_bear_cap_off(p):
    p["vix_bear_hard_cap"] = None

def _g_vix_bear_cap_30(p):  # loosen panic cap 23 -> 30 (only blocks true extremes)
    p["vix_bear_hard_cap"] = 30.0

def _g_entry_after_1530(p):  # extend entry window 15:00 -> 15:30 ET
    p["entry_no_trade_after_et"] = "15:30"

def _g_entry_before_0930(p):  # open the 09:30-09:35 window
    p["entry_no_trade_before_et"] = "09:30"

def _g_level_rejection_off(p):  # un-block BEAR LEVEL-tier level_rejection
    p["block_level_rejection"] = False

def _g_body_gate_off(p):  # doji/wick entry-bar gate off (bear)
    p["entry_bar_body_pct_min"] = 0.0

def _g_body_gate_10(p):  # loosen doji gate 0.20 -> 0.10
    p["entry_bar_body_pct_min"] = 0.10

def _g_f9_vol_05(p):  # loosen breakdown-bar volume mult 0.7 -> 0.5
    p["filter_9_vol_multiplier"] = 0.5

def _g_f9_vol_00(p):  # remove the volume requirement on the breakdown bar
    p["filter_9_vol_multiplier"] = 0.0

def _g_spread_20(p):  # loosen ribbon spread floor 30c -> 20c
    p["ribbon_min_spread_cents"] = 20

def _g_spread_25(p):
    p["ribbon_min_spread_cents"] = 25


GATES = [
    # (id, human, mutator, note)
    ("ribbon_momentum", "RIBBON_MOMENTUM_GATE (->off)", _g_momentum_off,
     "min_ribbon_momentum_cents 0->None. NOTE: at 0 it is ARMED (0 is-not-None), "
     "despite params doc claiming DISABLED. Relaxation = truly off."),
    ("midday_trendline", "MIDDAY_TRENDLINE_GATE (->off)", _g_midday_trendline_off,
     "block 1-trig trendline_rejection 11:30-14:00 ET -> allow."),
    ("vix_bear_cap_off", "VIX_BEAR_HARD_CAP (->off)", _g_vix_bear_cap_off,
     "vix_bear_hard_cap 23->None (allow bears at any VIX)."),
    ("vix_bear_cap_30", "VIX_BEAR_HARD_CAP (23->30)", _g_vix_bear_cap_30,
     "loosen panic cap to 30 (block only true fear extremes)."),
    ("entry_after_1530", "ENTRY_WINDOW (after 15:00->15:30)", _g_entry_after_1530,
     "extend bear entry cutoff 15:00->15:30 ET (theta risk past 3pm)."),
    ("entry_before_0930", "ENTRY_WINDOW (before 09:35->09:30)", _g_entry_before_0930,
     "open the 09:30-09:35 window."),
    ("level_rejection", "LEVEL_REJECTION_GATE (->off)", _g_level_rejection_off,
     "un-block BEAR LEVEL-tier level_rejection entries."),
    ("body_gate_off", "ENTRY_BAR_BODY_PCT (0.20->off)", _g_body_gate_off,
     "doji/wick-dominant entry-bar gate off (bear)."),
    ("body_gate_10", "ENTRY_BAR_BODY_PCT (0.20->0.10)", _g_body_gate_10,
     "loosen doji gate to 0.10 body."),
    ("f9_vol_05", "FILTER_9_VOL_MULT (0.7->0.5)", _g_f9_vol_05,
     "loosen breakdown-bar volume requirement 0.7->0.5x."),
    ("f9_vol_00", "FILTER_9_VOL_MULT (0.7->0.0)", _g_f9_vol_00,
     "remove the volume requirement on the breakdown bar."),
    ("spread_25", "RIBBON_SPREAD_MIN (30c->25c)", _g_spread_25,
     "loosen ribbon spread floor 30c->25c."),
    ("spread_20", "RIBBON_SPREAD_MIN (30c->20c)", _g_spread_20,
     "loosen ribbon spread floor 30c->20c."),
]


def _wf_norm(is_delta: float, oos_delta: float, is_months: float, oos_months: float) -> float:
    """Per-month-normalised walk-forward ratio of the LOOSENING's P&L delta.

    >=0.70 = OOS sustains at least 70% of the IS per-month improvement rate.
    Only meaningful when is_delta > 0 (the loosening helps IS). When is_delta<=0
    the loosening isn't even an IS win -> WF is N/A (return 0).
    """
    if is_delta <= 0:
        return 0.0
    is_rate = is_delta / is_months
    oos_rate = oos_delta / oos_months
    if is_rate == 0:
        return 0.0
    return round(oos_rate / is_rate, 3)


def main() -> int:
    print("=" * 100)
    print("GATE-FREQUENCY AUDIT — leave-one-out on LIVE config (real fills), metric = TOTAL P&L")
    print("=" * 100)
    print(f"Loading data {FULL_START}..{FULL_END} ...")
    spy, vix = runner.load_data(FULL_START, FULL_END)

    live = _live()
    print("Running BASELINE (full live engine, real fills)...")
    base_full = _run(live, spy, vix, FULL_START, FULL_END)
    base_is = _run(live, spy, vix, IS_START, IS_END)
    base_oos = _run(live, spy, vix, OOS_START, OOS_END)

    is_months = 12.0
    oos_months = (OOS_END.year - OOS_START.year) * 12 + (OOS_END.month - OOS_START.month) + 1

    print(f"\nBASELINE full : n={base_full['n']} (bear={base_full['n_bear']}) "
          f"WR={base_full['wr']*100:.0f}% total=${base_full['total']:+.0f} "
          f"exp=${base_full['exp']:+.0f} rate={base_full['n']/MONTHS_FULL:.2f}/mo")
    print(f"BASELINE IS   : n={base_is['n']} total=${base_is['total']:+.0f}")
    print(f"BASELINE OOS  : n={base_oos['n']} total=${base_oos['total']:+.0f}")

    results = []
    for gid, human, mut, note in GATES:
        p = copy.deepcopy(live)
        mut(p)
        full = _run(p, spy, vix, FULL_START, FULL_END)
        is_ = _run(p, spy, vix, IS_START, IS_END)
        oos = _run(p, spy, vix, OOS_START, OOS_END)

        pop = _admitted_population(base_full["rows"], full["rows"])
        total_delta = round(full["total"] - base_full["total"], 2)
        trade_delta = full["n"] - base_full["n"]
        is_delta = round(is_["total"] - base_is["total"], 2)
        oos_delta = round(oos["total"] - base_oos["total"], 2)

        # outlier robustness: largest single admitted trade as % of admitted P&L
        added = pop["added_pnls"]
        if added and pop["added_pnl"] != 0:
            top1 = max(added, key=abs)
            top1_share = round(abs(top1) / abs(sum(added)), 3) if sum(added) != 0 else None
        else:
            top1, top1_share = None, None

        wf = _wf_norm(is_delta, oos_delta, is_months, oos_months)

        # CLASSIFY (total-P&L metric):
        #   EARNS_KEEP        — removed population net-negative (relaxing LOWERS total P&L).
        #   OVER_RESTRICTIVE  — relaxing RAISES or holds total P&L AND adds frequency,
        #                       AND the admitted population is net positive-or-neutral.
        admits_freq = trade_delta > 0
        pop_net = pop["net_population_pnl"]
        # "neutral" band: within $200 absolute on full-window total
        holds_or_raises = total_delta >= -200.0
        admitted_not_negative = pop_net >= -200.0
        if admits_freq and total_delta > 200.0 and admitted_not_negative:
            verdict = "OVER_RESTRICTIVE"
        elif admits_freq and holds_or_raises and admitted_not_negative and total_delta >= 0:
            verdict = "OVER_RESTRICTIVE_MARGINAL"
        else:
            verdict = "EARNS_KEEP"

        # OOS gate for loosening candidates:
        oos_ok = (
            verdict.startswith("OVER_RESTRICTIVE")
            and is_delta > 0 and oos_delta > 0 and wf >= 0.70
            and (top1_share is None or top1_share <= 0.60)
        )

        row = {
            "gate_id": gid,
            "gate": human,
            "note": note,
            "trade_delta": trade_delta,
            "n_full": full["n"],
            "removed_population_n": pop["n_added"],
            "removed_population_pnl": pop["added_pnl"],
            "removed_population_wr": pop["added_wr"],
            "n_dropped_by_selection_shift": pop["n_dropped"],
            "net_population_pnl": pop_net,
            "total_pnl_full": full["total"],
            "total_pnl_delta": total_delta,
            "wr_full": full["wr"],
            "exp_full": full["exp"],
            "rate_per_month": round(full["n"] / MONTHS_FULL, 2),
            "is_delta": is_delta,
            "oos_delta": oos_delta,
            "wf_norm": wf,
            "top1_admitted_pnl": round(top1, 2) if top1 is not None else None,
            "top1_share_of_admitted": top1_share,
            "verdict": verdict,
            "oos_validated_loosen": bool(oos_ok),
        }
        results.append(row)

    # Sort: over-restrictive (by total_pnl_delta desc) first, then earns-keep (most protective first)
    def _sort_key(r):
        prio = 0 if r["verdict"].startswith("OVER_RESTRICTIVE") else 1
        return (prio, -r["total_pnl_delta"])
    results.sort(key=_sort_key)

    print("\n" + "=" * 100)
    print("RANKED GATE AUDIT (relaxing each, holding all else live)")
    print("=" * 100)
    hdr = f"{'gate':<34} {'dTrades':>7} {'removedP&L':>11} {'totalDelta':>11} {'IS_d':>7} {'OOS_d':>7} {'WF':>5} {'verdict':<26} OOS?"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(f"{r['gate']:<34} {r['trade_delta']:>+7d} "
              f"${r['removed_population_pnl']:>+9.0f} ${r['total_pnl_delta']:>+9.0f} "
              f"${r['is_delta']:>+5.0f} ${r['oos_delta']:>+5.0f} {r['wf_norm']:>5.2f} "
              f"{r['verdict']:<26} {'YES' if r['oos_validated_loosen'] else 'no'}")

    over = [r for r in results if r["verdict"].startswith("OVER_RESTRICTIVE")]
    shippable = [r for r in results if r["oos_validated_loosen"]]
    print("\n" + "=" * 100)
    print(f"HEADLINE: {len(over)} gate(s) flagged OVER_RESTRICTIVE; "
          f"{len(shippable)} pass the full OOS bar to loosen.")
    if shippable:
        for r in shippable:
            print(f"  -> LOOSEN {r['gate']}: total +${r['total_pnl_delta']:.0f}, "
                  f"+{r['trade_delta']} trades, IS +${r['is_delta']:.0f} OOS +${r['oos_delta']:.0f} WF {r['wf_norm']}")
    else:
        print("  -> No gate cleanly meets the bar. Most gates EARN their keep (remove net-losers).")
    print("=" * 100)

    scorecard = {
        "audit": "gate-frequency-audit",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "account": "SAFE (Gamma-Safe-2)",
        "metric": "TOTAL P&L (account growth) — NOT per-trade expectancy or edge_capture",
        "config": "live params.json, chart-stop primary, real OPRA fills",
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                   "note": "real OPRA option bars end ~2026-05-29"},
        "oos_split": {"is": [IS_START.isoformat(), IS_END.isoformat()],
                      "oos": [OOS_START.isoformat(), OOS_END.isoformat()],
                      "is_months": is_months, "oos_months": oos_months},
        "baseline": {
            "full": {k: base_full[k] for k in ("n", "n_bear", "wr", "total", "exp")},
            "is": {k: base_is[k] for k in ("n", "total")},
            "oos": {k: base_oos[k] for k in ("n", "total")},
            "trades_per_month": round(base_full["n"] / MONTHS_FULL, 2),
        },
        "classification_rule": {
            "EARNS_KEEP": "removed population net-negative -> relaxing LOWERS total P&L (keep gate).",
            "OVER_RESTRICTIVE": "relaxing RAISES total P&L >$200 AND adds trades AND admitted pop net>=-$200.",
            "OVER_RESTRICTIVE_MARGINAL": "relaxing holds/raises total P&L within neutral band + adds trades.",
            "oos_validated_loosen": "verdict OVER_RESTRICTIVE AND is_delta>0 AND oos_delta>0 AND WF>=0.70 AND top1_share<=0.60",
        },
        "gates": results,
        "headline": {
            "n_over_restrictive": len(over),
            "n_shippable_loosen": len(shippable),
            "shippable": [r["gate_id"] for r in shippable],
        },
        "discipline_notes": [
            "Total P&L is the metric; admitted population required net positive-or-neutral so frequency is not bought with negative-EV trades.",
            "Causality preserved: only gate thresholds were relaxed; no look-ahead added.",
            "Dual-account: this audit is SAFE. Bold runs different params (ITM-2, 50% risk, no chandelier); any finding requires a fresh Bold A/B (C29) — do NOT assume transfer.",
            "Propose-only: live params.json NOT edited.",
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print(f"\nScorecard -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
