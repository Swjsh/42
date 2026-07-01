"""BULL-UNBLOCK-STRUCTURAL — WIDEN THE DATA WINDOW (the FALSE-WALL carry-forward).

The frame-audit that made this possible (conductor 2026-07-01, commit c2bfe39):
    The range-scalp thread declared its edge "DATA-BLOCKED at n=8" on a 25-day
    window -- but the full master SPY/VIX 5m (2025-01-01..2026-06-18, 533 days) and
    OPRA real-fills (370 0DTE days) existed all along; the probe just hardcoded a
    25-day recent CSV on a stale comment. That fire's explicit CARRY-FORWARD:

        "the bull-frontier '25-day OPRA wall' (BULL-UNBLOCK-REPLAY-PROBE) was the
         SAME misread -- re-run those probes over the FULL 370-day OPRA history
         before accepting 'bull data-gated.'"

    This probe does exactly that for the ONE bull-unblock lever that was blocked
    ONLY by insufficient-n (not by a decisive net-negative):

      SLICE 2 (bull_unblock_structural_probe.py, commit 946530f) on the 25-day
      window: relaxing filter_10_min_triggers_bull 2->1 added n=8 bulls,
      net +$76 GROSS but INCONCLUSIVE (n<10) + 493% day-concentrated + FRAGILE
      (breakeven 1.6c) -> UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE = NOT proposable.

    The elite lever (SLICE 1) was already decisively net-NEGATIVE (-$241,
    DRY_AT_ZERO), so widening it would only re-confirm KEEP; the structural lever
    is the only one whose verdict could genuinely FLIP with more data. The n<10
    wall is the exact "data-blocked" frame the range-scalp fire proved false.

The decisive bounded question (mirrors the range-scalp widewindow ladder):
    Run the SAME min_triggers_bull 2-vs-1 A/B (block_elite_bull held FIXED at
    production True to isolate the structural lever) via the REAL engine over the
    FULL 2025-01-02..2026-06-18 history with use_real_fills=True. Score the ADDED
    bull cohort pooled + IS(2025)/OOS(2026). Does the cohort:
      (a) reach statistical significance pooled (n >= 10)?
      (b) hold positive expectancy IN-SAMPLE **and** OUT-OF-SAMPLE?
      (c) survive realistic slippage (breakeven half-spread >= 0.05)?
      (d) de-concentrate (top-3 days no longer dominate net)?
    Only if all four hold does relaxing the 2-trigger requirement become a
    proposable bull-unblock (DRAFT + ping J, rail-4 -- NEVER a hot edit); any
    other verdict is the HONEST full-history answer the 25-day window could not
    give, and closes the bull frontier for the RIGHT (data-rich) reason.

REUSE, don't rebuild (L17/L36): _bull_cfg / classify_verdict / _key / _date /
ANCHOR_DATES from the SLICE-1/2 probes; probe_stats for significance/concentration/
slippage. Both original probes stay byte-identical (no regression risk).

Rail-4 CLEAR: a research probe + results JSON. Touches NO params/doctrine/orders/
heartbeat/filters/CLAUDE; places NO order; arms NOTHING. $0 (cached OPRA fills).

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.bull_unblock_structural_widewindow_probe --smoke
    backtest/.venv/Scripts/python.exe -m autoresearch.bull_unblock_structural_widewindow_probe
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BT = _REPO / "backtest"
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

import pandas as pd
from lib.orchestrator import run_backtest
from autoresearch.probe_stats import (
    significance, day_concentration, concentration_flag, slippage_sweep,
    summarize_trades,
)
# Reuse the SLICE-1/2 config + verdict ladder + trade-key helpers (compound, don't duplicate).
from autoresearch.bull_unblock_structural_probe import _bull_cfg
from autoresearch.bull_unblock_replay_probe import _key, _date, ANCHOR_DATES

# --- full-history data (verified present 2026-07-01, same masters range-scalp used) ---
FULL_SPY_CSV = _BT / "data" / "spy_5m_2025-01-01_2026-06-18.csv"
FULL_VIX_CSV = _BT / "data" / "vix_5m_2025-01-01_2026-06-18.csv"

WINDOW_START = dt.date(2025, 1, 2)    # first OPRA 0DTE day
WINDOW_END = dt.date(2026, 6, 18)     # SPY master last day (a trade needs the 5m bar)
OOS_START = dt.date(2026, 1, 1)       # temporal walk-forward split: train 2025, test 2026

OUT_PATH = _REPO / "analysis" / "recommendations" / "bull-unblock-structural-widewindow-2026-07-01.json"


def classify_wide_verdict(
    *,
    pooled_sufficient: bool,
    pooled_net_positive: bool,
    both_splits_sufficient: bool,
    both_splits_positive: bool,
    slippage_survives_realistic: bool,
    concentrated: bool,
) -> str:
    """Pure full-history verdict ladder for the added-bull cohort (extracted for bite-testing).

    Precedence encodes the disqualification order (mirrors range-scalp widewindow):
      1. not enough added trades even pooled     -> STILL_INCONCLUSIVE_AFTER_WIDENING
      2. pooled cohort net <= 0                   -> BLOCK_CORRECTLY_REMOVES_LOSERS_ON_FULL_HISTORY
      3. a split too thin to walk-forward         -> POOLED_POSITIVE_SPLIT_TOO_THIN
      4. IS/OOS disagree in sign                  -> FAILS_WALK_FORWARD_SIGN_FLIP
      5. gross edge dies under realistic slippage -> DIES_ON_SLIPPAGE
      6. positive+robust but day-concentrated     -> POSITIVE_BUT_CONCENTRATED
      7. all clear -> relaxing min_triggers ADDS a real bull edge, propose to J
                                                  -> UNBLOCK_ADDS_EDGE_PROPOSE_ON_WIDE_HISTORY
    """
    if not pooled_sufficient:
        return "STILL_INCONCLUSIVE_AFTER_WIDENING"
    if not pooled_net_positive:
        return "BLOCK_CORRECTLY_REMOVES_LOSERS_ON_FULL_HISTORY"
    if not both_splits_sufficient:
        return "POOLED_POSITIVE_SPLIT_TOO_THIN"
    if not both_splits_positive:
        return "FAILS_WALK_FORWARD_SIGN_FLIP"
    if not slippage_survives_realistic:
        return "DIES_ON_SLIPPAGE"
    if concentrated:
        return "POSITIVE_BUT_CONCENTRATED"
    return "UNBLOCK_ADDS_EDGE_PROPOSE_ON_WIDE_HISTORY"


def _score_cohort(bulls: list) -> dict:
    """Score a list of added-bull trades with the canonical probe_stats helpers."""
    pnls = [t.dollar_pnl for t in bulls]
    rows = [{"dollar_pnl": t.dollar_pnl, "qty": getattr(t, "qty", 1) or 1} for t in bulls]
    summ = summarize_trades(pnls) if bulls else {}
    by_day: dict = {}
    for t in bulls:
        by_day[str(_date(t))] = by_day.get(str(_date(t)), 0.0) + t.dollar_pnl
    conc = day_concentration(by_day) if bulls else {}
    top3 = conc.get("top3_day_pct_of_net") if conc else None
    return {
        "n": len(bulls),
        "net_pnl": round(sum(pnls), 2),
        "summary": summ,
        "significance": significance(len(bulls)),
        "day_concentration": {k: v for k, v in conc.items() if k != "by_day_pnl"} if conc else {},
        "concentration_flag": concentration_flag(top3) if bulls else {},
        "slippage": slippage_sweep(rows) if bulls else {},
    }


def run_wide_probe(start: dt.date, end: dt.date) -> dict:
    spy = pd.read_csv(FULL_SPY_CSV)
    vix = pd.read_csv(FULL_VIX_CSV)

    r_base = run_backtest(spy, vix, start_date=start, end_date=end, **_bull_cfg(2))
    r_unbl = run_backtest(spy, vix, start_date=start, end_date=end, **_bull_cfg(1))

    base_keys = {_key(t) for t in r_base.trades}
    added = [t for t in r_unbl.trades if _key(t) not in base_keys]
    added_bulls = [t for t in added if t.side == "C"]

    is_bulls = [t for t in added_bulls if _date(t) < OOS_START]
    oos_bulls = [t for t in added_bulls if _date(t) >= OOS_START]

    pooled = _score_cohort(added_bulls)
    is_blk = _score_cohort(is_bulls)
    oos_blk = _score_cohort(oos_bulls)

    is_exp = is_blk["summary"].get("expectancy_per_trade_usd", 0.0) if is_bulls else 0.0
    oos_exp = oos_blk["summary"].get("expectancy_per_trade_usd", 0.0) if oos_bulls else 0.0
    pooled_net_positive = pooled["net_pnl"] > 0
    both_sufficient = is_blk["significance"]["sufficient"] and oos_blk["significance"]["sufficient"]
    both_positive = is_exp > 0 and oos_exp > 0
    slip_ok = isinstance(pooled["slippage"], dict) and pooled["slippage"].get("verdict") == "SURVIVES_REALISTIC"
    conc_flag = pooled["concentration_flag"].get("concentrated", False) if pooled["concentration_flag"] else False

    # No bull anchors exist (J's source-of-truth are all PUTS) -> the added cohort
    # must never touch an anchor day; assert it (mirrors SLICE-1/2).
    anchor_added = [t for t in added_bulls if _date(t) in ANCHOR_DATES]
    anchor_ok = not anchor_added

    verdict = classify_wide_verdict(
        pooled_sufficient=pooled["significance"]["sufficient"],
        pooled_net_positive=pooled_net_positive,
        both_splits_sufficient=both_sufficient,
        both_splits_positive=both_positive,
        slippage_survives_realistic=slip_ok,
        concentrated=conc_flag,
    )

    return {
        "probe": "bull_unblock_structural_widewindow_probe",
        "lever": "filter_10_min_triggers_bull (2 -> 1)",
        "block_elite_bull": "True (production, held FIXED to isolate the structural lever)",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "oos_start": OOS_START.isoformat()},
        "real_fills": True,
        "frame_audit": (
            "SLICE-2 (946530f) declared the structural bull lever NOT proposable at n=8 on a "
            "25-day OPRA window. The 2026-07-01 range-scalp frame-audit proved the master SPY/VIX "
            "5m (2025-01-01..2026-06-18) + OPRA real-fills (370 0DTE days) cover the full history; "
            "the 25-day window was a hardcoded-CSV misread, cited as a SHARED bull wall. This re-runs "
            "the SAME min_triggers 2->1 A/B over the full history for the honest, n-sufficient answer."
        ),
        "base": {"n": len(r_base.trades), "pnl": round(sum(t.dollar_pnl for t in r_base.trades), 2), "min_triggers_bull": 2},
        "unblock": {"n": len(r_unbl.trades), "pnl": round(sum(t.dollar_pnl for t in r_unbl.trades), 2), "min_triggers_bull": 1},
        "added_bull_cohort_pooled": pooled,
        "added_bull_cohort_in_sample_2025": is_blk,
        "added_bull_cohort_out_of_sample_2026": oos_blk,
        "walk_forward": {
            "is_expectancy_usd": round(is_exp, 2),
            "oos_expectancy_usd": round(oos_exp, 2),
            "both_sufficient_n": both_sufficient,
            "both_positive": both_positive,
            "slippage_survives_realistic": slip_ok,
            "not_concentrated": not conc_flag,
            "anchor_no_regression": anchor_ok,
        },
        "added_trades": [
            {"date": str(_date(t)), "strike": float(t.strike), "pnl": round(t.dollar_pnl, 2)}
            for t in sorted(added_bulls, key=_date)
        ],
        "method_disclosures": {
            "reuse": "_bull_cfg / _key / _date / ANCHOR_DATES from SLICE-1/2 probes + probe_stats; "
                     "both original probes byte-identical (no regression risk).",
            "isolation": "block_elite_bull held at production True across BOTH runs so the added cohort "
                         "is EXACTLY what the 2-trigger requirement removes, not a re-test of the elite block.",
            "fill_model": "Real OPRA bars via run_backtest(use_real_fills=True). NO Black-Scholes.",
            "yardstick": "added-cohort net + IS/OOS sign agreement + probe_stats significance/concentration/"
                         "slippage. J edge_capture NOT used (auto-rejects; and no bull anchors exist).",
            "limitations": "ONE lever (min_triggers 2->1), production strike/risk held constant. A PROPOSE "
                           "verdict is DRAFT+ping-J (rail-4), NEVER a hot edit; any other verdict is the honest "
                           "full-history answer the 25-day window could not give.",
        },
    }


def _print(result: dict) -> None:
    p = result["added_bull_cohort_pooled"]
    isb = result["added_bull_cohort_in_sample_2025"]
    oosb = result["added_bull_cohort_out_of_sample_2026"]
    slip = p["slippage"] if isinstance(p["slippage"], dict) else {}
    print(f"VERDICT={result['verdict']}")
    print(f"  BASE (min_triggers=2): n={result['base']['n']} pnl={result['base']['pnl']:+.0f}")
    print(f"  UNBL (min_triggers=1): n={result['unblock']['n']} pnl={result['unblock']['pnl']:+.0f}")
    print(f"  ADDED pooled : n={p['n']} net=${p['net_pnl']} "
          f"exp=${p['summary'].get('expectancy_per_trade_usd') if p['summary'] else 'NA'} "
          f"sufficient={p['significance']['sufficient']}")
    print(f"  ADDED IS 2025: n={isb['n']} net=${isb['net_pnl']} "
          f"exp=${isb['summary'].get('expectancy_per_trade_usd') if isb['summary'] else 'NA'}")
    print(f"  ADDED OOS2026: n={oosb['n']} net=${oosb['net_pnl']} "
          f"exp=${oosb['summary'].get('expectancy_per_trade_usd') if oosb['summary'] else 'NA'}")
    print(f"  slippage: {slip.get('verdict', 'NA')} breakeven={slip.get('breakeven_half_spread', 'NA')}")
    print(f"  concentration top3%={p['day_concentration'].get('top3_day_pct_of_net') if p['day_concentration'] else 'NA'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="run a ~3-month slice (2025-01..2025-03)")
    args = ap.parse_args()

    if args.smoke:
        result = run_wide_probe(dt.date(2025, 1, 2), dt.date(2025, 3, 31))
        _print(result)
        return 0

    result = run_wide_probe(WINDOW_START, WINDOW_END)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print(result)
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
