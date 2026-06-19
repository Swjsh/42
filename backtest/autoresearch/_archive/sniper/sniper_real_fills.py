"""SNIPER real-fills (OPRA) validation — top-3 P&L days.

Per CLAUDE.md OP 20 disclosure 4: a backtest result is not "ready" until
real-fills validation runs on the top-P&L days. BS sim approximates premium
via vix_to_iv + Black-Scholes; real fills capture bid/ask spread, jumps,
illiquid contracts.

This script:
  1. Re-runs the SNIPER winner combo across the full backtest window
     (2025-01-01 .. 2026-05-12) using BS sim — same as sniper_evaluator.
  2. Ranks days by BS P&L, picks the top-3.
  3. For each top-3 day, checks whether the OPRA contract file exists.
  4. Runs the SNIPER detector + simulator_real on the day to get the
     real-fills P&L (or marks BLOCKED if OPRA missing for that
     date/strike combination).
  5. Computes diff% = (real - bs) / bs * 100.
  6. Writes a JSON report.

Verdict: PASS if all 3 days have |diff| < 20%. CAVEAT otherwise.
BLOCKED if OPRA data is missing for all 3 (real-fills can't run).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner  # noqa: E402
from autoresearch.sniper_evaluator import (  # noqa: E402
    SniperCombo,
    run_sniper_day,
)
from lib.option_pricing_real import (  # noqa: E402
    load_contract_bars,
    option_symbol,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.sniper_detector import (  # noqa: E402
    SniperParams,
    compute_levels,
    detect_sniper_break,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Winner combo from sniper-v1 walk-forward
WINNER_COMBO_DICT = {
    "vol_mult": 1.1,
    "body_min_cents": 0.02,
    "min_stars": 2,
    "strike_offset": 2,
    "premium_stop_pct": -0.10,
    "tp1_premium_pct": 0.40,
    "runner_target_pct": 1.25,
    "profit_lock_threshold_pct": 0.0,
    "profit_lock_stop_offset_pct": 0.08,
    "tp1_qty_fraction": 0.667,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22

OPRA_DIR = REPO / "data" / "options"

OUT_JSON = REPO.parent / "analysis" / "recommendations" / "sniper-v1-realfills.json"
OUT_DOC = REPO.parent / "docs" / "REAL-FILLS-SNIPER-2026-05-13.md"


def _opra_available(date_et: dt.date, strike: int, side: str) -> bool:
    sym = option_symbol(date_et, strike, side)
    return (OPRA_DIR / f"{sym}.csv").exists()


def _compute_bs_per_day_pnl(
    combo: SniperCombo,
    spy_full: pd.DataFrame,
    vix_full: pd.DataFrame,
) -> dict[dt.date, dict[str, Any]]:
    """Run SNIPER BS sim per day across [WIDE_START, WIDE_END].

    Returns dict[date] -> {pnl, trades: [list of SniperTrade dicts]}.
    """
    all_dates = sorted(set(spy_full["timestamp_et"].dt.date.unique()))
    out: dict[dt.date, dict[str, Any]] = {}
    for d in all_dates:
        if d < WIDE_START or d > WIDE_END:
            continue
        trades = run_sniper_day(d, spy_full, vix_full, combo)
        if not trades:
            continue
        out[d] = {
            "pnl": round(sum(t.dollar_pnl for t in trades), 2),
            "trades": [
                {
                    "entry_time_et": t.entry_time_et.isoformat(),
                    "direction": t.direction,
                    "entry_spot": t.entry_spot,
                    "strike": t.strike,
                    "side": "P" if t.direction == "short" else "C",
                    "entry_premium": t.entry_premium,
                    "qty": t.qty,
                    "level_label": t.level_label,
                    "level_price": t.level_price,
                    "vol_ratio": t.vol_ratio,
                    "body_dollars": t.body_dollars,
                    "exit_reason": t.exit_reason,
                    "dollar_pnl": t.dollar_pnl,
                }
                for t in trades
            ],
        }
    return out


def _signal_to_params(combo: SniperCombo) -> SniperParams:
    return SniperParams(
        vol_mult=combo.vol_mult,
        body_min_cents=combo.body_min_cents,
        min_stars=combo.min_stars,
        proximity_dollars=combo.proximity_dollars,
        no_trade_before=dt.time(9, 30),
        no_trade_after=dt.time(15, 50),
        require_break_above_open=combo.require_break_above_open,
    )


def _run_real_fills_for_day(
    date_et: dt.date,
    spy_full: pd.DataFrame,
    combo: SniperCombo,
) -> dict[str, Any]:
    """Find SNIPER signals on date_et, simulate via real OPRA fills."""
    params = _signal_to_params(combo)

    day_bars = spy_full[
        (spy_full["timestamp_et"].dt.date == date_et)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    if day_bars.empty:
        return {"date": date_et.isoformat(), "real_pnl": 0.0, "trades": [],
                "notes": "no bars for date"}

    first_ts = day_bars["timestamp_et"].iloc[0]
    levels = compute_levels(spy_full, first_ts, params)
    if not levels:
        return {"date": date_et.isoformat(), "real_pnl": 0.0, "trades": [],
                "notes": "no historical levels"}

    pre_bars = spy_full[spy_full["timestamp_et"] < first_ts].tail(40).reset_index(drop=True)
    combined = pd.concat([pre_bars, day_bars], ignore_index=True)
    day_offset = len(pre_bars)

    # Build ribbon for combined window (needed by simulator_real)
    ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

    real_trades: list[dict[str, Any]] = []
    total_real_pnl = 0.0
    found_signal = False
    notes: list[str] = []

    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
        if signal is None:
            continue
        found_signal = True

        # Map SNIPER direction to side
        side = "P" if signal.direction == "short" else "C"
        entry_spot = float(signal.entry_price)
        # SNIPER combo offset: strike_offset=2 → puts: strike = round(spot)+2
        # simulator_real strike_offset for puts: strike = atm - strike_offset (default -2 → atm+2)
        # So we need to flip the sign: SNIPER offset=2 == simulator_real offset=-2 for puts
        if side == "P":
            sim_strike_offset = -combo.strike_offset
        else:
            sim_strike_offset = -combo.strike_offset

        # Compute strike same way as evaluator (for symbol lookup)
        if side == "P":
            strike = round(entry_spot) + combo.strike_offset
        else:
            strike = round(entry_spot) - combo.strike_offset

        # Check OPRA availability
        if not _opra_available(date_et, strike, side):
            real_trades.append({
                "entry_time_et": signal.bar_timestamp_et.isoformat(),
                "side": side,
                "strike": int(strike),
                "entry_spot": entry_spot,
                "missing_opra": True,
                "symbol": option_symbol(date_et, strike, side),
            })
            notes.append(f"OPRA missing for {option_symbol(date_et, strike, side)}")
            break  # only 1 trade per day per evaluator policy

        # Run real-fills simulator
        # NEW 2026-05-13 T42: pass profit_lock kwargs from combo so the
        # profit-lock added to simulator_real.py (T41) actually takes effect.
        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=bar,
            spy_df=combined,
            ribbon_df=ribbon_df,
            rejection_level=signal.level.price,
            triggers_fired=["sniper_level_break"],
            side=side,
            qty=combo.qty,
            setup="SNIPER_LEVEL_BREAK",
            levels_active=[L.price for L in levels if L.tier == "Active"],
            levels_carry=[L.price for L in levels if L.tier == "Carry"],
            use_tiered_exits=True,
            strike_override=int(strike),
            premium_stop_pct=combo.premium_stop_pct,
            profit_lock_threshold_pct=combo.profit_lock_threshold_pct,
            profit_lock_stop_offset_pct=combo.profit_lock_stop_offset_pct,
        )
        if fill is None:
            real_trades.append({
                "entry_time_et": signal.bar_timestamp_et.isoformat(),
                "side": side,
                "strike": int(strike),
                "entry_spot": entry_spot,
                "missing_opra": True,
                "symbol": option_symbol(date_et, strike, side),
                "note": "simulate_trade_real returned None (likely no entry bar in OPRA)",
            })
            notes.append(f"simulate_trade_real None for {option_symbol(date_et, strike, side)}")
            break

        total_real_pnl += float(fill.dollar_pnl or 0.0)
        real_trades.append({
            "entry_time_et": signal.bar_timestamp_et.isoformat(),
            "side": side,
            "strike": int(strike),
            "entry_spot": entry_spot,
            "entry_premium": fill.entry_premium,
            "tp1_premium": fill.tp1_premium,
            "runner_exit_premium": fill.runner_exit_premium,
            "exit_reason": str(fill.exit_reason),
            "dollar_pnl": round(fill.dollar_pnl, 2),
            "symbol": option_symbol(date_et, strike, side),
        })
        break  # max_trades_per_day=1 matches BS evaluator default

    return {
        "date": date_et.isoformat(),
        "real_pnl": round(total_real_pnl, 2),
        "trades": real_trades,
        "found_signal": found_signal,
        "notes": notes,
    }


def main() -> int:
    combo = SniperCombo(**{k: WINNER_COMBO_DICT[k] for k in WINNER_COMBO_DICT
                            if k in SniperCombo.__dataclass_fields__})

    log.info("Loading wide window data %s .. %s", WIDE_START, WIDE_END)
    spy_full, vix_full = _runner.load_data(WIDE_START, WIDE_END)
    spy_full["timestamp_et"] = (
        pd.to_datetime(spy_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    vix_full["timestamp_et"] = (
        pd.to_datetime(vix_full["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York").dt.tz_localize(None)
    )

    log.info("Running BS sim per-day across wide window …")
    bs_by_day = _compute_bs_per_day_pnl(combo, spy_full, vix_full)
    log.info("BS per-day complete: %d trading days with trades", len(bs_by_day))

    # Top-3 by BS P&L
    ranked = sorted(bs_by_day.items(), key=lambda kv: kv[1]["pnl"], reverse=True)
    top3 = ranked[:3]
    log.info("Top-3 BS P&L days: %s",
             [(d.isoformat(), v["pnl"]) for d, v in top3])

    # Walk down the ranked list to find the top-3 days WITH OPRA coverage,
    # so we can still produce real-fills evidence on the next-best winners
    # if the absolute top-3 is missing data.
    top_with_opra: list[tuple[dt.date, dict[str, Any]]] = []
    for d, v in ranked:
        if len(top_with_opra) >= 3:
            break
        if not v["trades"]:
            continue
        first_trade = v["trades"][0]
        if _opra_available(d, first_trade["strike"], first_trade["side"]):
            top_with_opra.append((d, v))
    log.info("Top-3 BS days WITH OPRA coverage: %s",
             [(d.isoformat(), v["pnl"]) for d, v in top_with_opra])

    # Pre-scan: which of top-3 has OPRA data for the right strike?
    opra_status: list[dict[str, Any]] = []
    for d, v in top3:
        # Use the first trade's strike (matches per-day evaluator policy)
        if not v["trades"]:
            opra_status.append({"date": d.isoformat(), "opra_available": False,
                                "reason": "no trades on day"})
            continue
        first_trade = v["trades"][0]
        strike = first_trade["strike"]
        side = first_trade["side"]
        avail = _opra_available(d, strike, side)
        opra_status.append({
            "date": d.isoformat(),
            "strike": strike,
            "side": side,
            "symbol": option_symbol(d, strike, side),
            "opra_available": avail,
        })

    available_count = sum(1 for s in opra_status if s.get("opra_available"))
    log.info("OPRA availability for top-3: %d / 3", available_count)

    # Pick the run list: prefer absolute top-3, but if none has OPRA, run on
    # top-with-OPRA (next-best fallback).
    if available_count > 0:
        run_list = top3
    else:
        run_list = top_with_opra
        log.info("No OPRA for absolute top-3; falling back to top-3 days that DO have OPRA.")

    # Also try the J anchor days where SNIPER fires AND OPRA exists — these are
    # the trades J actually took, so the BS-vs-real comparison there is the most
    # decision-relevant evidence.
    j_anchor_dates = [
        dt.date(2026, 4, 29),
        dt.date(2026, 5, 4),
        dt.date(2026, 5, 5),
        dt.date(2026, 5, 6),
        dt.date(2026, 5, 7),
    ]
    j_anchor_with_opra: list[tuple[dt.date, dict[str, Any]]] = []
    for d in j_anchor_dates:
        if d in bs_by_day:
            v = bs_by_day[d]
            if v["trades"]:
                t = v["trades"][0]
                if _opra_available(d, t["strike"], t["side"]):
                    j_anchor_with_opra.append((d, v))
    log.info("J anchor days WITH OPRA: %s",
             [(d.isoformat(), v["pnl"]) for d, v in j_anchor_with_opra])

    # Run real-fills only on dates with OPRA data
    real_results: list[dict[str, Any]] = []
    for d, v in run_list:
        log.info("Running real-fills sim for %s …", d.isoformat())
        try:
            res = _run_real_fills_for_day(d, spy_full, combo)
        except Exception as exc:
            res = {"date": d.isoformat(), "error": repr(exc),
                   "trace": traceback.format_exc()}
        res["bs_pnl"] = v["pnl"]
        # Compute diff%
        bs = v["pnl"]
        real = res.get("real_pnl", 0.0)
        if any(t.get("missing_opra") for t in res.get("trades", [])):
            res["diff_pct"] = None
            res["status"] = "BLOCKED_OPRA"
        elif bs == 0:
            res["diff_pct"] = None
            res["status"] = "BS_ZERO"
        else:
            res["diff_pct"] = round((real - bs) / abs(bs) * 100.0, 1)
            res["status"] = "MEASURED"
        real_results.append(res)

    # Determine verdict
    measured = [r for r in real_results if r["status"] == "MEASURED"]
    blocked = [r for r in real_results if r["status"] == "BLOCKED_OPRA"]
    on_top3 = (available_count > 0)

    if not measured:
        verdict = "BLOCKED"
        verdict_reason = (
            f"OPRA data missing for all {len(blocked)} target days. "
            "Real-fills validation cannot run until OPRA ingest completes. "
            f"Absolute top-3 BS P&L days had {available_count}/3 OPRA coverage; "
            f"top-3 with-OPRA fallback had {len(top_with_opra)} eligible days."
        )
    else:
        max_abs_diff = max(abs(r["diff_pct"]) for r in measured)
        all_under_20 = all(abs(r["diff_pct"]) < 20.0 for r in measured)
        cohort = "top-3 by BS P&L" if on_top3 else "top-3 by BS P&L WITH OPRA coverage (fallback)"
        if all_under_20 and not blocked:
            verdict = "PASS" if on_top3 else "PASS_FALLBACK"
            verdict_reason = (
                f"All {len(measured)} measured days ({cohort}) have |diff| < 20%. "
                f"Max diff: {max_abs_diff:.1f}%."
            )
            if not on_top3:
                verdict_reason += (
                    " NOTE: absolute top-3 BS P&L days had no OPRA coverage; "
                    "ran on next-best with-OPRA days as fallback evidence."
                )
        elif all_under_20 and blocked:
            verdict = "PARTIAL_PASS"
            verdict_reason = (
                f"{len(measured)} of {len(measured)+len(blocked)} measured ({cohort}) — "
                f"all under 20% diff. {len(blocked)} day(s) BLOCKED on missing OPRA data."
            )
        else:
            verdict = "CAVEAT"
            verdict_reason = (
                f"Max |diff| = {max_abs_diff:.1f}% on measured days ({cohort}) "
                f"exceeds 20% threshold. BS sim may not match real fills on those days."
            )

    # Also run on J anchor days (most decision-relevant evidence)
    j_anchor_results: list[dict[str, Any]] = []
    for d, v in j_anchor_with_opra:
        log.info("Running J anchor real-fills sim for %s …", d.isoformat())
        try:
            res = _run_real_fills_for_day(d, spy_full, combo)
        except Exception as exc:
            res = {"date": d.isoformat(), "error": repr(exc),
                   "trace": traceback.format_exc()}
        res["bs_pnl"] = v["pnl"]
        bs = v["pnl"]
        real = res.get("real_pnl", 0.0)
        if any(t.get("missing_opra") for t in res.get("trades", [])):
            res["diff_pct"] = None
            res["status"] = "BLOCKED_OPRA"
        elif bs == 0:
            res["diff_pct"] = None
            res["status"] = "BS_ZERO"
        else:
            res["diff_pct"] = round((real - bs) / abs(bs) * 100.0, 1)
            res["status"] = "MEASURED"
        j_anchor_results.append(res)

    report = {
        "rule_id": "sniper-v1",
        "generated_at": dt.datetime.now().isoformat(),
        "winner_combo": WINNER_COMBO_DICT,
        "wide_window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
        "n_days_with_trades": len(bs_by_day),
        "top3_bs_pnl_days": [
            {"date": d.isoformat(), "bs_pnl": v["pnl"], "n_trades": len(v["trades"])}
            for d, v in top3
        ],
        "top3_with_opra_coverage": [
            {"date": d.isoformat(), "bs_pnl": v["pnl"], "n_trades": len(v["trades"])}
            for d, v in top_with_opra
        ],
        "j_anchor_with_opra": [
            {"date": d.isoformat(), "bs_pnl": v["pnl"], "n_trades": len(v["trades"])}
            for d, v in j_anchor_with_opra
        ],
        "opra_status": opra_status,
        "real_fills_results": real_results,
        "j_anchor_real_fills_results": j_anchor_results,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "thresholds": {
            "diff_pct_threshold": 20.0,
            "policy_reference": "CLAUDE.md OP 20 real-fills gate",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))
    log.info("Wrote %s", OUT_JSON)

    return 0


if __name__ == "__main__":
    sys.exit(main())
