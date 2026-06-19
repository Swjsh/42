"""SNIPER stage-2 real-fills validation — top combo from stage2 neighborhood search.

Stage-2 top combo: off=2, vol=1.1, stop=-0.06, tp1=0.4, runner=3.0, frac=0.667
BS-sim (current code): wide_pnl=$27,813, n=231, 6/6 quarters positive, dd=$249

This script re-runs the sniper_real_fills.py validation flow but with the
stage2 combo parameters (stop=-0.06 vs -0.10 in the original winner combo).

CRITICAL SECURITY CONSTRAINTS:
- NEVER import or call any Alpaca tool or order function.
- Free-tier OpenRouter only. This script calls no LLMs.
- Read-only on production state.
- Cost ceiling: $0.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

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

# Stage-2 top combo (neighborhood search around stage-1 best)
STAGE2_COMBO_DICT = {
    "vol_mult": 1.1,
    "body_min_cents": 0.05,
    "min_stars": 2,
    "strike_offset": 2,
    "premium_stop_pct": -0.06,
    "tp1_premium_pct": 0.40,
    "runner_target_pct": 3.0,
    "profit_lock_threshold_pct": 0.0,
    "profit_lock_stop_offset_pct": 0.05,
    "tp1_qty_fraction": 0.667,
    "qty": 10,
    "proximity_dollars": 1.5,
    "require_break_above_open": True,
}

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)

OPRA_DIR = REPO / "data" / "options"
OUT_JSON = REPO.parent / "analysis" / "recommendations" / "sniper-stage2-realfills.json"


def _opra_available(date_et: dt.date, strike: int, side: str) -> bool:
    sym = option_symbol(date_et, strike, side)
    return (OPRA_DIR / f"{sym}.csv").exists()


def _compute_bs_per_day_pnl(
    combo: SniperCombo,
    spy_full: pd.DataFrame,
    vix_full: pd.DataFrame,
) -> dict[dt.date, dict[str, Any]]:
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

    ribbon_df = compute_ribbon(combined["close"]).reset_index(drop=True)

    real_trades: list[dict[str, Any]] = []
    total_real_pnl = 0.0
    notes: list[str] = []

    for i in range(len(day_bars)):
        bar_idx = day_offset + i
        bar = combined.iloc[bar_idx]
        signal = detect_sniper_break(bar, bar_idx, combined, levels, params)
        if signal is None:
            continue

        side = "P" if signal.direction == "short" else "C"
        entry_spot = float(signal.entry_price)
        if side == "P":
            strike = round(entry_spot) + combo.strike_offset
        else:
            strike = round(entry_spot) - combo.strike_offset

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
            break

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
                "note": "simulate_trade_real returned None",
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
        break  # max_trades_per_day=1

    return {
        "date": date_et.isoformat(),
        "real_pnl": round(total_real_pnl, 2),
        "trades": real_trades,
        "notes": notes,
    }


def main() -> int:
    combo = SniperCombo(**{k: STAGE2_COMBO_DICT[k] for k in STAGE2_COMBO_DICT
                            if k in SniperCombo.__dataclass_fields__})

    log.info("Stage-2 combo: stop=%.2f runner=%.1f tp1=%.2f vol=%.1f",
             combo.premium_stop_pct, combo.runner_target_pct,
             combo.tp1_premium_pct, combo.vol_mult)

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

    log.info("Running BS sim per-day ...")
    bs_by_day = _compute_bs_per_day_pnl(combo, spy_full, vix_full)
    total_bs = sum(v["pnl"] for v in bs_by_day.values())
    n_trades = sum(len(v["trades"]) for v in bs_by_day.values())
    log.info("BS sim complete: %d days with trades, total_pnl=%.2f, n_trades=%d",
             len(bs_by_day), total_bs, n_trades)

    ranked = sorted(bs_by_day.items(), key=lambda kv: kv[1]["pnl"], reverse=True)
    top3 = ranked[:3]
    log.info("Top-3 BS days: %s", [(d.isoformat(), v["pnl"]) for d, v in top3])

    # Find top-3 days WITH OPRA coverage
    top_with_opra: list[tuple[dt.date, dict[str, Any]]] = []
    for d, v in ranked:
        if len(top_with_opra) >= 3:
            break
        if not v["trades"]:
            continue
        t0 = v["trades"][0]
        if _opra_available(d, t0["strike"], t0["side"]):
            top_with_opra.append((d, v))
    log.info("Top-3 with OPRA: %s", [(d.isoformat(), v["pnl"]) for d, v in top_with_opra])

    opra_status: list[dict[str, Any]] = []
    for d, v in top3:
        if not v["trades"]:
            opra_status.append({"date": d.isoformat(), "opra_available": False, "reason": "no trades"})
            continue
        t0 = v["trades"][0]
        avail = _opra_available(d, t0["strike"], t0["side"])
        opra_status.append({
            "date": d.isoformat(),
            "strike": t0["strike"],
            "side": t0["side"],
            "symbol": option_symbol(d, t0["strike"], t0["side"]),
            "opra_available": avail,
            "bs_pnl": v["pnl"],
        })

    available_count = sum(1 for s in opra_status if s.get("opra_available"))
    log.info("OPRA availability top-3: %d/3", available_count)

    run_list = top3 if available_count > 0 else top_with_opra

    # Run real-fills
    real_results: list[dict[str, Any]] = []
    for d, v in run_list:
        if not v["trades"]:
            continue
        t0 = v["trades"][0]
        if not _opra_available(d, t0["strike"], t0["side"]):
            real_results.append({
                "date": d.isoformat(),
                "bs_pnl": v["pnl"],
                "real_pnl": None,
                "verdict": "BLOCKED",
                "reason": f"OPRA missing: {option_symbol(d, t0['strike'], t0['side'])}",
            })
            continue

        log.info("Running real-fills for %s ...", d.isoformat())
        rf = _run_real_fills_for_day(d, spy_full, combo)
        bs_pnl = v["pnl"]
        real_pnl = rf["real_pnl"]
        if bs_pnl != 0:
            diff_pct = (real_pnl - bs_pnl) / abs(bs_pnl) * 100
        else:
            diff_pct = 0.0

        verdict = "PASS" if abs(diff_pct) < 20.0 else "CAVEAT"
        if rf["real_pnl"] == 0.0 and not rf["trades"]:
            verdict = "BLOCKED"

        real_results.append({
            "date": d.isoformat(),
            "bs_pnl": bs_pnl,
            "real_pnl": real_pnl,
            "diff_pct": round(diff_pct, 1),
            "verdict": verdict,
            "trades": rf["trades"],
            "notes": rf.get("notes", []),
        })
        log.info("  %s: BS=%.2f REAL=%.2f diff=%.1f%% => %s",
                 d, bs_pnl, real_pnl, diff_pct, verdict)

    # Overall verdict
    verdicts = [r["verdict"] for r in real_results]
    if all(v == "PASS" for v in verdicts):
        overall = "PASS"
    elif any(v == "CAVEAT" for v in verdicts):
        overall = "CAVEAT"
    elif all(v == "BLOCKED" for v in verdicts):
        overall = "BLOCKED"
    else:
        overall = "PARTIAL"

    report = {
        "strategy": "SNIPER_LEVEL_BREAK",
        "stage": 2,
        "generated_at": dt.datetime.now().isoformat(),
        "combo": STAGE2_COMBO_DICT,
        "wide_window": {"start": WIDE_START.isoformat(), "end": WIDE_END.isoformat()},
        "bs_sim_summary": {
            "total_pnl": round(total_bs, 2),
            "n_trades": n_trades,
            "n_days": len(bs_by_day),
        },
        "top3_bs": [(d.isoformat(), v["pnl"]) for d, v in top3],
        "opra_status": opra_status,
        "real_fills": real_results,
        "overall_verdict": overall,
        "verdict_rule": "PASS if all available days |diff|<20%; CAVEAT if any day |diff|>=20%; BLOCKED if no OPRA data",
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2))
    log.info("Report written to %s", OUT_JSON)
    log.info("OVERALL VERDICT: %s", overall)

    return 0 if overall in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
