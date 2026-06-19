"""SNIPER real-fills RE-RUN with PROFIT-LOCK variants — T42.

Hypothesis: after T41 added profit-lock to simulator_real.py, SNIPER might
also be rescued like v14_enhanced was (3/3 PASS, real wide_pnl exceeded BS).

This runs the SAME days as T35 (sniper_real_fills.py) but with the winner
combo's profit_lock_threshold_pct overridden across a small grid:
  - 0.00 (control — should match T35's CAVEAT result)
  - 0.05 (lock at +5% favor)
  - 0.10 (lock at +10% favor)
  - 0.15

profit_lock_stop_offset_pct held at 0.05 (lock stop to entry +5%).

Output: `analysis/recommendations/sniper-v1-realfills-pl-variants.json`
        `docs/SNIPER-PL-VARIANTS-2026-05-13.md`
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from copy import copy
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from autoresearch import runner as _runner  # noqa: E402
from autoresearch.sniper_evaluator import SniperCombo, run_sniper_day  # noqa: E402
from autoresearch.sniper_real_fills import (  # noqa: E402
    WINNER_COMBO_DICT,
    _run_real_fills_for_day,
    _compute_bs_per_day_pnl,
    WIDE_START,
    WIDE_END,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PL_VARIANTS = [
    (0.00, 0.05, "control_pl_off"),
    (0.05, 0.05, "pl_05_off05"),
    (0.05, 0.08, "pl_05_off08"),
    (0.10, 0.05, "pl_10_off05"),
    (0.10, 0.08, "pl_10_off08"),
]

# Days to test (mirror T35 — top-3 abs + J anchors with OPRA)
TARGET_DAYS = [
    dt.date(2025, 4, 7),
    dt.date(2026, 4, 29),
    dt.date(2026, 5, 4),
    dt.date(2026, 5, 5),
]

OUT_JSON = REPO.parent / "analysis" / "recommendations" / "sniper-v1-realfills-pl-variants.json"
OUT_DOC = REPO.parent / "docs" / "SNIPER-PL-VARIANTS-2026-05-13.md"


def build_combo(threshold: float, offset: float) -> SniperCombo:
    d = copy(WINNER_COMBO_DICT)
    d["profit_lock_threshold_pct"] = threshold
    d["profit_lock_stop_offset_pct"] = offset
    return SniperCombo(**{k: d[k] for k in d if k in SniperCombo.__dataclass_fields__})


def main() -> int:
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
    log.info("Loaded: SPY %d, VIX %d bars", len(spy_full), len(vix_full))

    # First compute BS P&L for the target days (so we have BS reference)
    log.info("Computing BS sim per day (for reference) ...")
    bs_by_day = _compute_bs_per_day_pnl(
        build_combo(0.0, 0.05), spy_full, vix_full
    )
    bs_lookup = {d: v["pnl"] for d, v in bs_by_day.items()}

    results = []
    for threshold, offset, label in PL_VARIANTS:
        log.info("=" * 60)
        log.info("VARIANT %s: profit_lock_threshold=%.2f, offset=%.2f", label, threshold, offset)
        combo = build_combo(threshold, offset)

        day_results = []
        for d in TARGET_DAYS:
            try:
                res = _run_real_fills_for_day(d, spy_full, combo)
            except Exception as exc:
                res = {"date": d.isoformat(), "error": repr(exc)}
            res["bs_pnl"] = bs_lookup.get(d, 0.0)
            if "real_pnl" in res and res.get("trades") and not any(t.get("missing_opra") for t in res["trades"]):
                bs = res["bs_pnl"]
                real = res["real_pnl"]
                res["diff_pct"] = round((real - bs) / abs(bs) * 100.0, 1) if bs else None
                res["status"] = "MEASURED"
            else:
                res["status"] = "BLOCKED_OR_NO_SIGNAL"
            day_results.append(res)
            log.info(
                "  %s BS=$%+.0f real=$%+.0f (status=%s, trades=%d)",
                d.isoformat(), res["bs_pnl"], res.get("real_pnl", 0.0),
                res["status"], len(res.get("trades", []))
            )

        total_bs = sum(r["bs_pnl"] for r in day_results)
        total_real = sum(r.get("real_pnl", 0.0) for r in day_results if r.get("status") == "MEASURED")
        measured = [r for r in day_results if r["status"] == "MEASURED"]
        n_pass = sum(1 for r in measured if abs(r.get("diff_pct") or 999) < 20.0)

        # Verdict: PASS if 4/29 J anchor turns positive AND total real >= total BS
        anchor_4_29 = next((r for r in day_results if r["date"] == "2026-04-29"), None)
        anchor_4_29_real = anchor_4_29.get("real_pnl", 0.0) if anchor_4_29 else 0.0
        rescued = anchor_4_29_real > 0
        verdict = "RESCUED" if rescued and total_real > 0 else "STILL_FAILS"

        log.info(
            "  → %s: total BS=$%+.0f real=$%+.0f (rescued 4/29=$%+.0f, %d/%d within ±20%%)",
            verdict, total_bs, total_real, anchor_4_29_real, n_pass, len(measured)
        )

        results.append({
            "variant": label,
            "profit_lock_threshold_pct": threshold,
            "profit_lock_stop_offset_pct": offset,
            "verdict": verdict,
            "total_bs_pnl": round(total_bs, 2),
            "total_real_pnl": round(total_real, 2),
            "anchor_4_29_real": round(anchor_4_29_real, 2),
            "days": day_results,
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "generated_at": dt.datetime.now().isoformat(),
        "winner_combo_base": WINNER_COMBO_DICT,
        "variants": results,
        "target_days": [d.isoformat() for d in TARGET_DAYS],
    }, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    # Markdown report
    OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    md = [
        "# SNIPER Real-Fills — Profit-Lock Variants — T42",
        "",
        f"Generated: {dt.datetime.now().isoformat()}",
        "",
        "## Hypothesis",
        "",
        "T35 verdict was CAVEAT (4/4 measured days flipped from BS-winners to real-losses).",
        "After T41 added profit-lock to `simulator_real.py`, hypothesis: profit-lock RESCUES",
        "SNIPER the same way it rescued v14_enhanced (T44b verdict: 3/3 PASS).",
        "",
        "## Results",
        "",
        "| Variant | profit_lock_threshold / offset | total BS | total real | 4/29 J real | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        md.append(
            f"| {r['variant']} | {r['profit_lock_threshold_pct']:.2f} / {r['profit_lock_stop_offset_pct']:.2f} "
            f"| ${r['total_bs_pnl']:+.0f} | ${r['total_real_pnl']:+.0f} | ${r['anchor_4_29_real']:+.0f} "
            f"| **{r['verdict']}** |"
        )
    md.append("")
    md.append("## Per-day detail (each variant)")
    md.append("")
    for r in results:
        md.append(f"### {r['variant']} (threshold={r['profit_lock_threshold_pct']:.2f}, offset={r['profit_lock_stop_offset_pct']:.2f})")
        md.append("")
        md.append("| Date | BS | Real | Diff% | Status |")
        md.append("|---|---:|---:|---:|---|")
        for d in r["days"]:
            md.append(
                f"| {d['date']} | ${d['bs_pnl']:+.0f} | ${d.get('real_pnl', 0):+.0f} "
                f"| {d.get('diff_pct', 'n/a')}% | {d['status']} |"
            )
        md.append("")
    OUT_DOC.write_text("\n".join(md), encoding="utf-8")
    log.info("Wrote %s", OUT_DOC)

    # Pick winner
    rescued = [r for r in results if r["verdict"] == "RESCUED"]
    if rescued:
        winner = max(rescued, key=lambda r: r["total_real_pnl"])
        log.info("=" * 60)
        log.info("BEST VARIANT: %s with total real $%+.0f, 4/29 $%+.0f",
                 winner["variant"], winner["total_real_pnl"], winner["anchor_4_29_real"])
    else:
        log.info("=" * 60)
        log.info("NO VARIANT RESCUED SNIPER — BS sim is fundamentally diverging beyond profit-lock")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
