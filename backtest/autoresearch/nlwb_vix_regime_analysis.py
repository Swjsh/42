"""NLWB VIX-regime rescue analysis.

Reads `analysis/recommendations/nlwb_full_real_fills.json` (already produced by
nlwb_full_real_fills_validate.py) and tests three VIX-gated sub-scenarios to
determine if removing the VIX 17-20 drag bucket rescues the OP-21 real-fills gate.

Context (from nlwb_full_real_fills_validate.py, 2026-05-20):
  Full window (ribbon=MIXED/BULL, N=23 completed): WR=47.8%, PnL=-$1,294 — FAIL
  VIX breakdown:
    <15:   N=1,  WR=100.0%
    15-17: N=7,  WR=57.1%
    17-20: N=5,  WR=20.0%  <- primary drag
    20-25: N=5,  WR=60.0%
    >=25:  N=5,  WR=40.0%

OP-21 real-fills gate (from OP-21 promotion criteria):
  WR >= 50% AND PnL > 0 AND N meaningful (>=15 preferred across >=2 regimes)

Scenarios tested:
  A. VIX<17 only      — removes the 17-20 drag bucket
  B. VIX>=20 only     — higher-vol only
  C. VIX<17 or VIX>=25 — removes the 17-20 drag; keeps >=25 (40% WR marginal)
  D. VIX<17 or VIX>=20 (excluding 17-20 only)

Output: analysis/recommendations/nlwb_vix_regime_analysis.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

IN_JSON  = ROOT / "analysis" / "recommendations" / "nlwb_full_real_fills.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "nlwb_vix_regime_analysis.json"


def _classify_scenario(vix_bucket: str, scenario: str) -> bool:
    """Return True if this vix_bucket is included in the named scenario."""
    if scenario == "A_vix_lt17":
        return vix_bucket in ("<15", "15-17")
    if scenario == "B_vix_ge20":
        return vix_bucket in ("20-25", ">=25")
    if scenario == "C_vix_lt17_or_ge25":
        return vix_bucket in ("<15", "15-17", ">=25")
    if scenario == "D_exclude_17_20":
        return vix_bucket in ("<15", "15-17", "20-25", ">=25")
    return False


SCENARIOS = {
    "A_vix_lt17": "VIX < 17 only",
    "B_vix_ge20": "VIX >= 20 only",
    "C_vix_lt17_or_ge25": "VIX < 17 OR VIX >= 25 (skip 17-25 band)",
    "D_exclude_17_20": "All except VIX 17-20 (skip only drag bucket)",
}


def analyse() -> dict:
    if not IN_JSON.exists():
        print(f"ERROR: {IN_JSON} not found. Run nlwb_full_real_fills_validate.py first.")
        sys.exit(1)

    full = json.loads(IN_JSON.read_text(encoding="utf-8"))

    # Keep only COMPLETE results (have outcome + dollar_pnl)
    completed = [r for r in full["results"] if r.get("status") == "COMPLETE"]
    print(f"Full window: {len(completed)} completed trades")
    print(f"Full window: WR={full['wr_real']*100:.1f}%  PnL=${full['total_dollar_pnl']:.0f}")
    print()

    scenario_results: dict = {}
    for key, label in SCENARIOS.items():
        trades = [r for r in completed if _classify_scenario(r.get("vix_bucket", ""), key)]
        wins   = sum(1 for t in trades if t.get("outcome") == "WIN")
        losses = sum(1 for t in trades if t.get("outcome") == "LOSS")
        n      = len(trades)
        wr     = wins / n if n > 0 else 0.0
        pnl    = sum(t.get("dollar_pnl", 0.0) for t in trades)

        op21_pass = wr >= 0.50 and pnl > 0
        n_adequate = n >= 15

        # VIX bucket sub-breakdown within this scenario
        sub: dict[str, dict] = {}
        for bucket in ("<15", "15-17", "17-20", "20-25", ">=25"):
            bt = [t for t in trades if t.get("vix_bucket") == bucket]
            if bt:
                bw = sum(1 for t in bt if t.get("outcome") == "WIN")
                sub[bucket] = {
                    "n": len(bt),
                    "wins": bw,
                    "wr_pct": round(bw / len(bt) * 100, 1),
                    "pnl": round(sum(t.get("dollar_pnl", 0) for t in bt), 2),
                }

        scenario_results[key] = {
            "label": label,
            "n": n,
            "wins": wins,
            "losses": losses,
            "wr_pct": round(wr * 100, 1),
            "total_pnl": round(pnl, 2),
            "avg_pnl_per_trade": round(pnl / n, 2) if n > 0 else 0.0,
            "op21_wr_gate": "PASS" if wr >= 0.50 else "FAIL",
            "op21_pnl_gate": "PASS" if pnl > 0 else "FAIL",
            "op21_n_adequate": "YES" if n_adequate else f"NO (N={n}, need N>=15)",
            "op21_real_fills_gate": "PASS" if (op21_pass and n_adequate) else (
                "MARGINAL" if op21_pass else "FAIL"
            ),
            "by_vix_bucket": sub,
        }

        gate_str = scenario_results[key]["op21_real_fills_gate"]
        print(f"[{key}] {label}")
        print(f"  N={n}  WR={wr*100:.1f}%  PnL=${pnl:.0f}  Gate: {gate_str}")
        for bucket, bs in sub.items():
            print(f"    {bucket}: N={bs['n']}  WR={bs['wr_pct']}%  PnL=${bs['pnl']:.0f}")
        print()

    # Summary verdict
    any_full_pass = any(
        s["op21_real_fills_gate"] == "PASS" for s in scenario_results.values()
    )
    any_marginal = any(
        s["op21_real_fills_gate"] == "MARGINAL" for s in scenario_results.values()
    )

    if any_full_pass:
        verdict = "RESCUE_FOUND — at least one VIX-gated variant passes OP-21 real-fills gate with N>=15"
    elif any_marginal:
        verdict = (
            "MARGINAL — WR>=50% and PnL>0 in at least one scenario BUT N<15 (insufficient sample). "
            "Needs accumulation of live observations before formal OP-21 gate test."
        )
    else:
        verdict = "NO_RESCUE — no VIX-gated variant achieves WR>=50% AND positive PnL across N>=15 signals"

    print(f"=== RESCUE VERDICT: {verdict} ===")

    output = {
        "run_date": dt.date.today().isoformat(),
        "source_file": str(IN_JSON),
        "full_window_summary": {
            "n_completed": len(completed),
            "wr_pct": round(full["wr_real"] * 100, 1),
            "total_pnl": full["total_dollar_pnl"],
            "op21_gate": full["op21_real_fills_gate"],
        },
        "scenarios": scenario_results,
        "rescue_verdict": verdict,
        "recommendation": (
            "If MARGINAL scenario found: add VIX gate to watcher confidence tier. "
            "Route VIX-in-drag-bucket signals to confidence='low' (observe but lower weight). "
            "Accumulate live observations in qualifying VIX regime; revisit real-fills gate "
            "when N>=15 live signals in target regime. "
            "If NO_RESCUE: NLWB has no viable VIX-gated path to OP-21 promotion. "
            "Consider archiving as WATCH_FRAGILE-INACTIVE or removing from watcher fleet."
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {OUT_JSON}")
    return output


if __name__ == "__main__":
    analyse()
