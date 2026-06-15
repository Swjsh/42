"""Walk-forward validation for the SNIPER_LEVEL_BREAK winner combo.

Splits the historical window into:
  TRAIN: 2025-01-01 to 2025-12-31 (1 year — optimizer saw this)
  TEST:  2026-01-01 to 2026-05-12 (4.4 months — TRULY out of sample
         for the wide-window metric, though J-anchors in this window
         were used for floor protection)

Runs the SNIPER Stage 5 winner combo (from
analysis/recommendations/sniper-v1.json) on BOTH windows day-by-day,
then compares per-month normalized P&L.

Per CLAUDE.md OP 20 the strategy is "Monday ready" only if:
  - TEST P&L > 0 (positive OOS dollars)
  - test_pnl_per_month >= 0.5 * train_pnl_per_month (no major regime
    decay between train and test)

Writes:
  analysis/recommendations/sniper-v1-walkforward.json
  docs/WALK-FORWARD-SNIPER-2026-05-13.md
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner  # noqa: E402
from autoresearch.sniper_evaluator import SniperCombo, run_sniper_day  # noqa: E402

logger = logging.getLogger(__name__)

WINNER_JSON = ROOT / "analysis" / "recommendations" / "sniper-v1.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "sniper-v1-walkforward.json"
OUT_MD = ROOT / "docs" / "WALK-FORWARD-SNIPER-2026-05-13.md"

TRAIN_START = dt.date(2025, 1, 1)
TRAIN_END = dt.date(2025, 12, 31)
TEST_START = dt.date(2026, 1, 1)
TEST_END = dt.date(2026, 5, 12)


def _load_winner_combo() -> dict:
    """Read the Stage 5 winner combo from sniper-v1.json."""
    payload = json.loads(WINNER_JSON.read_text(encoding="utf-8"))
    if "winner_combo" not in payload:
        raise SystemExit(f"No winner_combo key in {WINNER_JSON}")
    return payload["winner_combo"]


def _evaluate_window(
    combo: SniperCombo,
    start: dt.date,
    end: dt.date,
    label: str,
) -> dict:
    """Run SNIPER day-by-day over [start, end]. Return aggregate metrics."""
    spy, vix = runner.load_data(start, end)
    # Normalize timestamps to ET-naive (matches sniper_evaluator convention)
    spy["timestamp_et"] = (
        pd.to_datetime(spy["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    vix["timestamp_et"] = (
        pd.to_datetime(vix["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )

    all_dates = sorted(set(spy["timestamp_et"].dt.date.unique()))
    day_pnl_map: dict[dt.date, float] = defaultdict(float)
    quarter_pnl_map: dict[str, float] = defaultdict(float)
    all_trades = []

    for d in all_dates:
        if d < start or d > end:
            continue
        day_trades = run_sniper_day(d, spy, vix, combo)
        if not day_trades:
            continue
        all_trades.extend(day_trades)
        day_total = sum(t.dollar_pnl for t in day_trades)
        day_pnl_map[d] += day_total
        q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        quarter_pnl_map[q] += day_total

    n_trades = len(all_trades)
    n_winners = sum(1 for t in all_trades if t.dollar_pnl > 0)
    total_pnl = sum(t.dollar_pnl for t in all_trades)
    win_rate = round(n_winners / n_trades, 3) if n_trades else 0.0

    sorted_days = sorted(day_pnl_map.values(), reverse=True)
    top5_sum = sum(sorted_days[:5])
    top5_pct = round(top5_sum / total_pnl, 3) if total_pnl > 0 else 0.0

    # Sequential drawdown
    cum = peak = max_dd = 0.0
    for d in sorted(day_pnl_map.keys()):
        cum += day_pnl_map[d]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    positive_quarters = sum(1 for v in quarter_pnl_map.values() if v > 0)
    quarter_count = len(quarter_pnl_map)

    logger.info(
        "%s: %d trades / $%.0f / wr=%.1f%% / %d days",
        label,
        n_trades,
        total_pnl,
        win_rate * 100,
        len(day_pnl_map),
    )

    return {
        "window_start": str(start),
        "window_end": str(end),
        "total_pnl": round(total_pnl, 2),
        "n_trades": n_trades,
        "n_winners": n_winners,
        "win_rate": win_rate,
        "trading_days": len(day_pnl_map),
        "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl_map.items()},
        "positive_quarters": positive_quarters,
        "quarter_count": quarter_count,
        "max_drawdown": round(max_dd, 2),
        "top5_pct": top5_pct,
    }


def _months_in_window(start: dt.date, end: dt.date) -> float:
    """Approximate months between two dates (fractional)."""
    days = (end - start).days + 1
    return days / 30.4375  # average month length


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    print(f"Loading SNIPER winner combo from {WINNER_JSON.name}...")
    combo_dict = _load_winner_combo()

    # Build a SniperCombo from the JSON keys (filter to declared fields)
    combo_kwargs = {
        k: v
        for k, v in combo_dict.items()
        if k in SniperCombo.__dataclass_fields__
    }
    combo = SniperCombo(**combo_kwargs)

    print(f"  combo: {combo_dict}")
    print(f"TRAIN window: {TRAIN_START} to {TRAIN_END}")
    print(f"TEST  window: {TEST_START} to {TEST_END}")
    print()

    print("Evaluating TRAIN window...")
    train = _evaluate_window(combo, TRAIN_START, TRAIN_END, "TRAIN")
    print(
        f"  TRAIN: pnl=${train['total_pnl']:.0f} / "
        f"trades={train['n_trades']} / wr={train['win_rate'] * 100:.1f}%"
    )

    print("Evaluating TEST window...")
    test = _evaluate_window(combo, TEST_START, TEST_END, "TEST")
    print(
        f"  TEST:  pnl=${test['total_pnl']:.0f} / "
        f"trades={test['n_trades']} / wr={test['win_rate'] * 100:.1f}%"
    )

    # Per-month normalized — the honest comparison
    train_months = _months_in_window(TRAIN_START, TRAIN_END)
    test_months = _months_in_window(TEST_START, TEST_END)
    train_per_mo = train["total_pnl"] / train_months if train_months else 0.0
    test_per_mo = test["total_pnl"] / test_months if test_months else 0.0
    ratio = (test_per_mo / train_per_mo) if train_per_mo > 0 else 0.0

    # Verdict per OP 20: TEST positive AND test_per_month >= 0.5x train
    test_positive = test["total_pnl"] > 0
    ratio_ok = ratio >= 0.5
    monday_ready = test_positive and ratio_ok
    verdict = "PASS" if monday_ready else "FAIL"

    if not test_positive:
        verdict_reason = "TEST P&L negative — strategy fails OOS"
    elif not ratio_ok:
        verdict_reason = (
            f"test_per_month ${test_per_mo:.0f} < 0.5 * train_per_month "
            f"${train_per_mo:.0f} (ratio {ratio:.2f}x) — serious regime decay"
        )
    else:
        verdict_reason = (
            f"TEST positive AND test_per_month {test_per_mo:.0f}/mo is "
            f"{ratio:.2f}x train_per_month {train_per_mo:.0f}/mo (>= 0.5x floor)"
        )

    payload = {
        "rule_id": "sniper-v1",
        "generated_at": dt.datetime.now().isoformat(),
        "winner_combo": combo_dict,
        "train_window": f"{TRAIN_START} to {TRAIN_END}",
        "train_months": round(train_months, 2),
        "test_window": f"{TEST_START} to {TEST_END}",
        "test_months": round(test_months, 2),
        "train_pnl": train["total_pnl"],
        "test_pnl": test["total_pnl"],
        "train_n_trades": train["n_trades"],
        "test_n_trades": test["n_trades"],
        "train_wr": train["win_rate"],
        "test_wr": test["win_rate"],
        "train_pnl_per_month": round(train_per_mo, 2),
        "test_pnl_per_month": round(test_per_mo, 2),
        "ratio": round(ratio, 3),
        "train_full": train,
        "test_full": test,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "monday_ready": monday_ready,
        "thresholds": {
            "test_positive_required": True,
            "test_per_month_min_ratio": 0.5,
            "policy_reference": "CLAUDE.md OP 20 walk-forward gate",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    # ---- Markdown summary ----
    verdict_icon = "PASS" if monday_ready else "FAIL"
    md = []
    md.append("# Walk-forward validation — SNIPER_LEVEL_BREAK")
    md.append("")
    md.append(f"_Generated: {dt.datetime.now().isoformat()}_")
    md.append("")
    md.append(f"**Verdict: {verdict_icon}**")
    md.append("")
    md.append(f"_{verdict_reason}_")
    md.append("")
    md.append("## Windows")
    md.append("")
    md.append(
        f"- **TRAIN:** {TRAIN_START} to {TRAIN_END}  "
        f"({train_months:.1f} months — optimizer saw this)"
    )
    md.append(
        f"- **TEST:**  {TEST_START} to {TEST_END}  "
        f"({test_months:.1f} months — held out from wide-window optimizer; "
        f"J-anchors used only for floor protection)"
    )
    md.append("")
    md.append("## Headline numbers")
    md.append("")
    md.append("| Metric | TRAIN | TEST |")
    md.append("|---|---|---|")
    md.append(
        f"| Total P&L | ${train['total_pnl']:.0f} | "
        f"${test['total_pnl']:.0f} |"
    )
    md.append(
        f"| Trades | {train['n_trades']} | {test['n_trades']} |"
    )
    md.append(
        f"| Win rate | {train['win_rate'] * 100:.1f}% | "
        f"{test['win_rate'] * 100:.1f}% |"
    )
    md.append(
        f"| Per-month P&L | ${train_per_mo:.0f} | ${test_per_mo:.0f} |"
    )
    md.append(
        f"| Max drawdown | ${train['max_drawdown']:.0f} | "
        f"${test['max_drawdown']:.0f} |"
    )
    md.append(
        f"| Top-5 day concentration | "
        f"{train['top5_pct'] * 100:.1f}% | "
        f"{test['top5_pct'] * 100:.1f}% |"
    )
    md.append(
        f"| Positive quarters | {train['positive_quarters']} / "
        f"{train['quarter_count']} | {test['positive_quarters']} / "
        f"{test['quarter_count']} |"
    )
    md.append("")
    md.append(
        f"**Per-month ratio (test / train): {ratio:.2f}x**"
    )
    md.append("")
    md.append("## Quarter breakdown")
    md.append("")
    md.append("| Quarter | P&L |")
    md.append("|---|---|")
    all_quarters = sorted(
        set(train["quarter_pnl"].keys()) | set(test["quarter_pnl"].keys())
    )
    for q in all_quarters:
        train_q = train["quarter_pnl"].get(q, 0.0)
        test_q = test["quarter_pnl"].get(q, 0.0)
        total_q = train_q + test_q
        md.append(f"| {q} | ${total_q:+.0f} |")
    md.append("")
    md.append("## Interpretation (per CLAUDE.md OP 20)")
    md.append("")
    md.append("- **Per-month ratio > 0.7x** = strategy generalizes well to OOS")
    md.append("- **Per-month ratio 0.5–0.7x** = mild overfit, still trade-worthy")
    md.append("- **Per-month ratio < 0.5x** = serious overfit (DO NOT trade)")
    md.append("- **Test P&L < 0** = strategy fails out-of-sample (DO NOT trade)")
    md.append("")
    md.append("## Winner combo (the params tested)")
    md.append("")
    md.append("```json")
    md.append(json.dumps(combo_dict, indent=2))
    md.append("```")
    md.append("")
    md.append("## Caveats")
    md.append("")
    md.append(
        "- TEST window is 2026-01-01..2026-05-12 (~4.4 months). Wide-window "
        "metric (wide_pnl) of the optimizer was 2025-01-01..2026-05-07, so "
        "TEST overlaps with the very last 5 days of the optimizer's window. "
        "J-anchor days (4/29..5/07) sit inside TEST AND were used for "
        "floor protection in the optimizer. This is selection bias and is "
        "called out per OP 20 disclosure 2 (sample bias)."
    )
    md.append(
        "- Real-fills (OPRA) validation NOT done here. Required separately "
        "per scorecard's `next_actions[1]`."
    )
    md.append(
        "- Per-month normalized is the honest metric because TRAIN is 12 "
        "months and TEST is ~4.4 months — naive dollar ratios mislead."
    )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print()
    print(f"VERDICT: {verdict_icon}")
    print(f"  reason: {verdict_reason}")
    print(f"Written: {OUT_JSON}")
    print(f"Written: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
