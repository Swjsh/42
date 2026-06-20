#!/usr/bin/env python
"""overnight_swarm.py - nightly backtest swarm -> ranked morning shortlist.

The /insights report (2026-06-18) flagged that 80+ sweep scripts exist but there
is no nightly orchestrator that ranks their output into a single shortlist J can
read each morning. This is that orchestrator.

What it does (pure-Python, $0, read-only on broker):
  1. (optionally) re-run the one-call real-fills backtest matrix (tools/run_all_sniper.py)
     so the candidate pool is fresh; otherwise consume the existing results JSON.
  2. Score every candidate per OP-16: final ~ edge-proxy x daily-Sharpe.
  3. Regression-gate each variant vs its same-strike V0_baseline (compare.py's
     $50/day threshold): a variant is RATIFY-READY only if it is flat-or-better on
     EVERY day AND its total is positive (never declare improvement on a single
     good day - LESSONS C4).
  4. Write a ranked shortlist to analysis/overnight-shortlist-{date}.{md,json} and
     append a one-line pointer to automation/overnight/STATUS.md (signal, not silence).

Per OP-16 the shortlist is J's REVOKE surface, not an auto-deploy: nothing here
touches params.json / heartbeat.md / live orders.

Usage:
    python -m autoresearch.overnight_swarm                 # consume latest results
    python -m autoresearch.overnight_swarm --run           # re-run the matrix first
    python -m autoresearch.overnight_swarm --top 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
PROJECT = REPO.parent                                # 42/
ABT = PROJECT / "analysis" / "backtests"
RESULTS = ABT / "_sniper_results.json"
OUT_DIR = PROJECT / "analysis"
STATUS = PROJECT / "automation" / "overnight" / "STATUS.md"
REGRESSION_THRESHOLD = 50.0  # dollars/day, matches tools/compare.py


def _sharpe(per_day: dict[str, float]) -> float:
    """Daily Sharpe, annualised (mean/std * sqrt(252)). 0 if <2 days or no spread."""
    vals = [float(v) for v in per_day.values()]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(252)


def _split_key(key: str) -> tuple[str, str]:
    """'ATM stop-8%||V_mom_gate' -> ('ATM stop-8%', 'V_mom_gate')."""
    if "||" in key:
        grp, variant = key.split("||", 1)
        return grp.strip(), variant.strip()
    return "(ungrouped)", key.strip()


def _regression_verdict(per_day: dict[str, float],
                        baseline: dict[str, float] | None) -> tuple[str, list[str]]:
    """RATIFY-READY only if flat-or-better every shared day AND positive total."""
    total = sum(per_day.values())
    if baseline is None:
        return ("NO_BASELINE", [])
    regressed = []
    for day, base_pnl in baseline.items():
        cand_pnl = per_day.get(day)
        if cand_pnl is None:
            continue
        if cand_pnl < base_pnl - REGRESSION_THRESHOLD:
            regressed.append(f"{day}: {cand_pnl:+.0f} vs base {base_pnl:+.0f}")
    if regressed:
        return ("REGRESSED", regressed)
    if total <= 0:
        return ("FLAT_BUT_UNPROFITABLE", [])
    return ("RATIFY_READY", [])


def build_shortlist(results: dict, top: int) -> dict:
    # index baselines per strike group
    baselines: dict[str, dict[str, float]] = {}
    for key, val in results.items():
        grp, variant = _split_key(key)
        if variant.upper().startswith("V0_BASELINE") or variant.upper() == "V0_BASELINE":
            baselines[grp] = {k: float(v) for k, v in (val.get("per_day") or {}).items()}

    rows = []
    for key, val in results.items():
        grp, variant = _split_key(key)
        per_day = {k: float(v) for k, v in (val.get("per_day") or {}).items()}
        total = float(val.get("total", sum(per_day.values())))
        sharpe = _sharpe(per_day)
        # OP-16 ranking: edge-proxy (total P&L) x daily Sharpe. Negative totals rank last.
        score = total * sharpe if total > 0 else total
        is_baseline = variant.upper().startswith("V0_BASELINE")
        if is_baseline:
            # the baseline IS the current strategy, not a proposed change - never
            # "ratify-ready" (it would trivially pass against itself).
            verdict, detail = "BASELINE", []
        else:
            verdict, detail = _regression_verdict(per_day, baselines.get(grp))
        rows.append({
            "key": key, "group": grp, "variant": variant,
            "total": round(total, 2), "sharpe": round(sharpe, 3),
            "score": round(score, 2), "days_plus": val.get("days_plus"),
            "n_trades": val.get("n"), "gate": verdict, "gate_detail": detail,
            "per_day": {k: round(v, 2) for k, v in per_day.items()},
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    ratify = [r for r in rows if r["gate"] == "RATIFY_READY"]
    return {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(RESULTS.relative_to(PROJECT)),
        "candidate_count": len(rows),
        "ratify_ready_count": len(ratify),
        "ranking_metric": "total_pnl x daily_sharpe (OP-16 edge x sharpe)",
        "regression_threshold_usd": REGRESSION_THRESHOLD,
        "top": rows[:top],
        "ratify_ready": ratify[:top],
    }


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        f"# Overnight Swarm Shortlist - {report['generated_at'][:10]}",
        "",
        f"_Generated {report['generated_at']} from `{report['source']}`._  ",
        f"_{report['candidate_count']} candidates scored; "
        f"**{report['ratify_ready_count']} RATIFY-READY** "
        f"(flat-or-better every day + positive total)._  ",
        f"_Ranking: {report['ranking_metric']}. This is J's REVOKE surface - "
        "nothing here is auto-deployed (OP-16)._",
        "",
        "## Top candidates",
        "",
        "| # | group | variant | total $ | sharpe | score | days+ | gate |",
        "|---|-------|---------|---------|--------|-------|-------|------|",
    ]
    for i, r in enumerate(report["top"], 1):
        lines.append(
            f"| {i} | {r['group']} | {r['variant']} | {r['total']:+.0f} | "
            f"{r['sharpe']:.2f} | {r['score']:.0f} | {r['days_plus']} | {r['gate']} |"
        )
    if report["ratify_ready"]:
        lines += ["", "## RATIFY-READY (beats-or-flat every day, positive total)", ""]
        for r in report["ratify_ready"]:
            lines.append(f"- **{r['key']}** - total {r['total']:+.0f}, "
                         f"sharpe {r['sharpe']:.2f}, score {r['score']:.0f}")
    else:
        lines += ["", "_No RATIFY-READY candidates this run (all either regressed a "
                  "day or netted <=0). No-op is the correct outcome - LESSONS C4._"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_status(report: dict) -> None:
    if not STATUS.exists():
        return
    stamp = report["generated_at"]
    line = (f"\n- {stamp[:16]} overnight-swarm: {report['candidate_count']} scored, "
            f"**{report['ratify_ready_count']} ratify-ready** "
            f"-> `analysis/overnight-shortlist-{stamp[:10]}.md`")
    with STATUS.open("a", encoding="utf-8") as fh:
        fh.write(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true",
                    help="re-run tools/run_all_sniper.py first to refresh the pool")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    if args.run:
        try:
            subprocess.run([sys.executable, "tools/run_all_sniper.py"],
                           cwd=str(REPO), timeout=1800, check=False,
                           creationflags=(0x08000000 if sys.platform == "win32" else 0))
        except Exception as exc:  # never crash the orchestrator on a sub-run failure
            print(f"WARN: matrix re-run failed ({exc}); using existing results", file=sys.stderr)

    if not RESULTS.exists():
        print(f"ERROR: no results at {RESULTS} - run with --run or fire the sniper matrix first",
              file=sys.stderr)
        return 1

    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    report = build_shortlist(results, args.top)

    date = report["generated_at"][:10]
    (OUT_DIR / f"overnight-shortlist-{date}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, OUT_DIR / f"overnight-shortlist-{date}.md")
    append_status(report)

    print(f"overnight-swarm: {report['candidate_count']} candidates, "
          f"{report['ratify_ready_count']} ratify-ready -> "
          f"analysis/overnight-shortlist-{date}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
