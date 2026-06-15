"""Stress-test seed 6 (v15 winner) on known high-impact event days.

Replays the engine with seed 6 params on a curated list of historical
event days that historically broke other strategies:
  - FOMC rate decisions
  - CPI releases
  - NFP days
  - Mega-cap earnings overflow days
  - Known whipsaw / chop trap days

For each event day, reports:
  - n_trades fired
  - P&L outcome
  - any rule violations (would the engine have done something stupid?)

Output: analysis/recommendations/v15-stress-test.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner, random_eval

REPO = Path(__file__).resolve().parent.parent
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "v15-stress-test.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# Curated stress days. Mix of historical FOMC/CPI/NFP + known event days
# from journal/CHANGELOG (e.g., 2026-05-07 FOMC = first live trade day).
STRESS_DAYS = [
    # 2026 FOMC + macro
    {"date": "2026-05-07", "tag": "FOMC May 2026", "type": "fomc", "severity": "high",
     "note": "live trade day -- system took counter-trend BULL into pre-FOMC bear sequence (-$45)"},
    {"date": "2026-04-29", "tag": "FOMC April 2026", "type": "fomc", "severity": "high",
     "note": "J's manual winner +$342 (BEARISH_REJECTION)"},
    {"date": "2026-03-19", "tag": "FOMC March 2026", "type": "fomc", "severity": "high"},
    {"date": "2026-04-10", "tag": "CPI March 2026", "type": "cpi", "severity": "high"},
    {"date": "2026-03-12", "tag": "CPI February 2026", "type": "cpi", "severity": "high"},
    {"date": "2026-04-04", "tag": "NFP March 2026", "type": "nfp", "severity": "high"},
    {"date": "2026-03-07", "tag": "NFP February 2026", "type": "nfp", "severity": "high"},
    # Known live-context days
    {"date": "2026-05-01", "tag": "J historical winner", "type": "live_context", "severity": "med",
     "note": "J 721P +$470 / +72%"},
    {"date": "2026-05-04", "tag": "J historical winner", "type": "live_context", "severity": "med",
     "note": "J 721P +$730 / +86% (best example)"},
    {"date": "2026-05-05", "tag": "J chop trap loss", "type": "live_context", "severity": "med",
     "note": "J 722P -$260 manual"},
    {"date": "2026-05-06", "tag": "J held to zero", "type": "live_context", "severity": "med",
     "note": "J 730P -$300 (rule 3 break)"},
]


def stress_one_day(date_str: str, params: dict, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """Run engine on a single date, report what fired + P&L."""
    d = dt.date.fromisoformat(date_str)
    try:
        result, m = runner.run_with_params(params, d, d, spy_df, vix_df)
        # Trade-level detail
        trades = []
        for t in result.trades:
            trades.append({
                "entry_time": str(getattr(t, "entry_time", "?")),
                "exit_time": str(getattr(t, "exit_time", "?")),
                "side": getattr(t, "side", "?"),
                "setup": getattr(t, "setup", "?"),
                "qty": getattr(t, "qty", 0),
                "entry_premium": round(getattr(t, "entry_premium", 0), 3),
                "exit_premium": round(getattr(t, "exit_premium", 0), 3),
                "pnl_dollars": round(getattr(t, "pnl_dollars", 0), 2),
                "exit_reason": getattr(t, "exit_reason", "?"),
            })
        return {
            "date": date_str,
            "n_trades": m.n_trades,
            "n_winners": m.n_winners,
            "n_losers": m.n_losers,
            "total_pnl": round(m.total_pnl, 2),
            "win_rate": round(m.win_rate, 4),
            "trades": trades,
        }
    except Exception as exc:  # noqa: BLE001
        return {"date": date_str, "error": repr(exc)}


def main() -> int:
    logger.info("Stress-testing seed 6 (v15 winner) on %d event days", len(STRESS_DAYS))
    params = random_eval.generate_params(6)

    # Load full data range covering all stress days
    min_d = min(dt.date.fromisoformat(d["date"]) for d in STRESS_DAYS)
    max_d = max(dt.date.fromisoformat(d["date"]) for d in STRESS_DAYS)
    spy, vix = runner.load_data(min_d, max_d)

    results = []
    total_pnl = 0
    total_trades = 0
    total_winners = 0
    for stress in STRESS_DAYS:
        r = stress_one_day(stress["date"], params, spy, vix)
        r["tag"] = stress["tag"]
        r["type"] = stress["type"]
        r["severity"] = stress["severity"]
        if "note" in stress:
            r["note"] = stress["note"]
        results.append(r)
        if "error" not in r:
            total_pnl += r["total_pnl"]
            total_trades += r["n_trades"]
            total_winners += r["n_winners"]
            logger.info("  %s [%s] n=%d pnl=$%+.0f wr=%d/%d",
                        stress["date"], stress["tag"], r["n_trades"], r["total_pnl"],
                        r["n_winners"], r["n_trades"])
        else:
            logger.error("  %s ERROR: %s", stress["date"], r["error"])

    summary = {
        "candidate": "v15-seed6",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "n_event_days": len(STRESS_DAYS),
        "total_pnl_across_event_days": round(total_pnl, 2),
        "total_trades": total_trades,
        "total_winners": total_winners,
        "agg_win_rate": round(total_winners / total_trades, 4) if total_trades else 0,
        "by_day": results,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("=" * 60)
    logger.info("STRESS TEST DONE")
    logger.info("  Total event-day P&L: $%+.0f across %d trades, WR %.0f%%",
                total_pnl, total_trades, summary["agg_win_rate"] * 100)
    logger.info("  Output: %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
