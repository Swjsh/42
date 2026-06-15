"""
Grade a swarm replay output against actual market outcomes — 3 dimensions:
  1. Direction:    swarm consensus_bias vs actual SPY close direction
  2. Battle level: did the predicted battle level get tested? Hold/break?
  3. Predictions:  for each of the 3 falsifiable predictions, was invalidation triggered?

Reads:
  - analysis/swarm-benchmark/replay-{date}-{asof}/swarm_output.json
  - backtest/data/spy_5m_*.csv (for actual outcomes)

Writes:
  - analysis/swarm-benchmark/replay-{date}-{asof}/grade.json
  - analysis/swarm-benchmark/aggregate.json (rebuilt from all grade.json files)

Usage:
  python grader_replay.py --date 2026-05-14 --as-of 06:00
  python grader_replay.py --grade-all                          # grade every replay dir
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
WORK_DIR = Path(__file__).parent.parent.parent.parent.resolve()
BENCHMARK_BASE = WORK_DIR / "analysis" / "swarm-benchmark"
SPY_CSV_DEFAULT = WORK_DIR / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-15.csv"


def _log(msg: str) -> None:
    print(f"[grader] {msg}", flush=True)


@dataclass(frozen=True)
class ActualSession:
    """The day's actual RTH outcome, computed from 5m bars."""
    date: str
    open_price: float
    close_price: float
    high: float
    low: float
    actual_bias: str           # 'bullish' | 'bearish' | 'no_trade'
    move_dollars: float


def _load_spy_5m(path: Path = SPY_CSV_DEFAULT) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp_et"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return df.sort_values("timestamp_et").reset_index(drop=True)


def _rth_bars(spy_df: pd.DataFrame, date_et: str) -> pd.DataFrame:
    return spy_df[
        (spy_df["timestamp_et"].dt.strftime("%Y-%m-%d") == date_et) &
        (spy_df["timestamp_et"].dt.time >= time(9, 30)) &
        (spy_df["timestamp_et"].dt.time < time(16, 0))
    ].copy()


def _actual_outcome(spy_df: pd.DataFrame, date_et: str) -> ActualSession | None:
    rth = _rth_bars(spy_df, date_et)
    if rth.empty:
        return None
    open_p = float(rth.iloc[0]["open"])
    close_p = float(rth.iloc[-1]["close"])
    high_p = float(rth["high"].max())
    low_p = float(rth["low"].min())
    move = close_p - open_p
    if move > 1.0:
        bias = "bullish"
    elif move < -1.0:
        bias = "bearish"
    else:
        bias = "no_trade"
    return ActualSession(
        date=date_et, open_price=round(open_p, 2), close_price=round(close_p, 2),
        high=round(high_p, 2), low=round(low_p, 2),
        actual_bias=bias, move_dollars=round(move, 2),
    )


def _grade_direction(consensus: str, actual: str) -> dict:
    if consensus == actual:
        grade = "CORRECT"
    elif consensus == "no_trade":
        grade = "ABSTAIN"
    elif actual == "no_trade":
        grade = "ABSTAIN_ACTUAL"
    else:
        grade = "WRONG"
    return {"grade": grade, "consensus": consensus, "actual": actual}


def _grade_battle_level(battle_level: dict, rth: pd.DataFrame) -> dict:
    if not battle_level or battle_level.get("price") is None:
        return {"grade": "NO_LEVEL", "reason": "no battle level in swarm output"}
    price = float(battle_level["price"])
    role = battle_level.get("role", "support")
    proximity = 0.25

    touched = ((rth["low"] <= price + proximity) & (rth["high"] >= price - proximity)).any()
    if not touched:
        return {"grade": "UNTESTED", "battle_level": price, "role": role,
                "rth_range": [round(float(rth["low"].min()), 2), round(float(rth["high"].max()), 2)]}

    # Find first touch bar; assess what happened in the next 2 bars
    first_touch_idx = rth[(rth["low"] <= price + proximity) & (rth["high"] >= price - proximity)].index[0]
    next_bars = rth.loc[first_touch_idx:].head(3)
    closed_below = (next_bars["close"] < price - 0.10).any()
    closed_above = (next_bars["close"] > price + 0.10).any()

    if role == "support":
        if closed_below and not closed_above:
            outcome = "BROKE"   # support failed
        elif closed_above and not closed_below:
            outcome = "HELD"    # support held
        else:
            outcome = "TESTED_MIXED"
    else:
        if closed_above and not closed_below:
            outcome = "BROKE"   # resistance failed
        elif closed_below and not closed_above:
            outcome = "HELD"    # resistance held
        else:
            outcome = "TESTED_MIXED"

    return {"grade": outcome, "battle_level": price, "role": role,
            "first_touch_time": next_bars.iloc[0]["timestamp_et"].isoformat()}


_LEVEL_PRICE_RE = re.compile(r"\b(7\d{2}|6\d{2})\.(\d{1,2})\b")


def _grade_level_prediction(prediction: dict, rth: pd.DataFrame) -> dict:
    """Pragmatic grader for level predictions: extract first price + time from claim/invalidation,
    check whether the price was touched in the time window. Predictions without parseable
    price+time get tagged review_needed."""
    claim = prediction.get("claim", "")
    invalidation = prediction.get("invalidation", "")

    prices = _LEVEL_PRICE_RE.findall(claim + " " + invalidation)
    if not prices:
        return {"grade": "REVIEW_NEEDED", "reason": "no parseable price in claim/invalidation"}

    target_price = float(f"{prices[0][0]}.{prices[0][1]}")
    touched = ((rth["low"] <= target_price + 0.10) & (rth["high"] >= target_price - 0.10)).any()

    # Check for time hint (e.g., "by 10:00 ET", "within first 30 min")
    time_match = re.search(r"\b(\d{1,2}):(\d{2})\s*ET\b", claim + " " + invalidation)
    if time_match:
        cutoff = time(int(time_match.group(1)), int(time_match.group(2)))
        early_window = rth[rth["timestamp_et"].dt.time < cutoff]
        touched_in_window = (
            (early_window["low"] <= target_price + 0.10) &
            (early_window["high"] >= target_price - 0.10)
        ).any() if not early_window.empty else False
    else:
        touched_in_window = touched

    return {
        "grade": "TOUCHED_IN_WINDOW" if touched_in_window else "MISSED",
        "target_price": target_price,
        "touched_any_time": bool(touched),
        "touched_in_specified_window": bool(touched_in_window),
        "claim": claim[:100],
    }


def _grade_predictions(predictions: list, rth: pd.DataFrame) -> list:
    out = []
    for p in predictions:
        domain = p.get("domain", "")
        if domain == "level":
            out.append({**_grade_level_prediction(p, rth), "domain": domain})
        else:
            out.append({"grade": "REVIEW_NEEDED", "domain": domain,
                        "reason": f"narrative grading needed for {domain} prediction",
                        "claim": p.get("claim", "")[:120],
                        "invalidation": p.get("invalidation", "")[:120]})
    return out


def grade_replay(date_et: str, as_of_hhmm: str,
                 spy_csv: Path = SPY_CSV_DEFAULT) -> dict:
    safe_asof = as_of_hhmm.replace(":", "")
    replay_dir = BENCHMARK_BASE / f"replay-{date_et}-{safe_asof}"
    swarm_path = replay_dir / "swarm_output.json"
    if not swarm_path.exists():
        return {"date": date_et, "status": "missing_swarm_output"}

    with open(swarm_path, encoding="utf-8") as f:
        swarm = json.load(f)

    spy_df = _load_spy_5m(spy_csv)
    rth = _rth_bars(spy_df, date_et)
    if rth.empty:
        return {"date": date_et, "status": "no_rth_bars",
                "swarm_consensus": swarm.get("consensus_bias")}

    actual = _actual_outcome(spy_df, date_et)
    direction_grade = _grade_direction(swarm.get("consensus_bias", "no_trade"), actual.actual_bias)
    battle_grade = _grade_battle_level(swarm.get("battle_level", {}), rth)
    pred_grades = _grade_predictions(swarm.get("swarm_predictions", []), rth)

    grade = {
        "date": date_et,
        "as_of_et": as_of_hhmm,
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "actual": {
            "open": actual.open_price, "close": actual.close_price,
            "high": actual.high, "low": actual.low,
            "move_dollars": actual.move_dollars,
            "actual_bias": actual.actual_bias,
        },
        "swarm": {
            "consensus_bias": swarm.get("consensus_bias"),
            "swarm_confidence": swarm.get("swarm_confidence"),
            "consensus_strength": swarm.get("consensus_strength"),
            "battle_level": swarm.get("battle_level", {}),
            "dissent_active": swarm.get("dissent_flag", {}).get("active", False),
        },
        "grades": {
            "direction": direction_grade,
            "battle_level": battle_grade,
            "predictions": pred_grades,
        },
        "narrative": swarm.get("synthesis_narrative", "")[:300],
    }

    with open(replay_dir / "grade.json", "w", encoding="utf-8") as f:
        json.dump(grade, f, indent=2)
    _log(f"{date_et}: direction={direction_grade['grade']} "
         f"battle={battle_grade['grade']} preds={[p['grade'] for p in pred_grades]}")
    return grade


def grade_all() -> dict:
    """Grade every replay dir, rebuild aggregate scorecard."""
    grades = []
    for d in sorted(BENCHMARK_BASE.glob("replay-*")):
        m = re.match(r"replay-(\d{4}-\d{2}-\d{2})-(\d{4})", d.name)
        if not m:
            continue
        date_et = m.group(1)
        as_of_raw = m.group(2)
        as_of_hhmm = f"{as_of_raw[:2]}:{as_of_raw[2:]}"
        g = grade_replay(date_et, as_of_hhmm)
        if g.get("status") in ("missing_swarm_output", "no_rth_bars"):
            continue
        grades.append(g)

    if not grades:
        return {"n_graded": 0}

    n = len(grades)
    direction_grades = [g["grades"]["direction"]["grade"] for g in grades]
    n_correct = sum(1 for x in direction_grades if x == "CORRECT")
    n_wrong = sum(1 for x in direction_grades if x == "WRONG")
    n_abstain = sum(1 for x in direction_grades if x in ("ABSTAIN", "ABSTAIN_ACTUAL"))

    battle_grades = [g["grades"]["battle_level"]["grade"] for g in grades]
    n_battle_tested = sum(1 for x in battle_grades if x in ("HELD", "BROKE", "TESTED_MIXED"))
    n_battle_untested = sum(1 for x in battle_grades if x == "UNTESTED")

    high_conf = [g for g in grades if (g["swarm"].get("swarm_confidence") or 0) >= 70]
    high_conf_correct = sum(1 for g in high_conf if g["grades"]["direction"]["grade"] == "CORRECT")

    agg = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "n_days_graded": n,
        "direction": {
            "n_correct": n_correct, "n_wrong": n_wrong, "n_abstain": n_abstain,
            "accuracy_pct": round(n_correct / (n_correct + n_wrong) * 100, 1) if (n_correct + n_wrong) else None,
        },
        "battle_level": {
            "n_tested": n_battle_tested, "n_untested": n_battle_untested,
            "tested_rate_pct": round(n_battle_tested / n * 100, 1),
        },
        "confidence_calibration": {
            "high_conf_days": len(high_conf),
            "high_conf_correct_pct": round(high_conf_correct / len(high_conf) * 100, 1) if high_conf else None,
        },
        "per_day": [
            {
                "date": g["date"],
                "swarm_bias": g["swarm"]["consensus_bias"],
                "swarm_conf": g["swarm"]["swarm_confidence"],
                "actual_bias": g["actual"]["actual_bias"],
                "actual_move": g["actual"]["move_dollars"],
                "direction_grade": g["grades"]["direction"]["grade"],
                "battle_level": g["swarm"]["battle_level"].get("price"),
                "battle_grade": g["grades"]["battle_level"]["grade"],
            }
            for g in grades
        ],
    }
    out = BENCHMARK_BASE / "aggregate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)
    _log(f"aggregate scorecard: {n} days, direction accuracy={agg['direction']['accuracy_pct']}%")
    return agg


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade swarm replay outputs against actuals")
    parser.add_argument("--date", help="Single date YYYY-MM-DD")
    parser.add_argument("--as-of", default="06:00")
    parser.add_argument("--grade-all", action="store_true", help="Grade every replay dir")
    args = parser.parse_args()

    if args.grade_all:
        grade_all()
        return 0
    if args.date:
        grade_replay(args.date, args.as_of)
        return 0
    parser.error("Specify --date or --grade-all")
    return 1


if __name__ == "__main__":
    sys.exit(main())
