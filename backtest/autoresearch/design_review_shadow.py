"""design_review_shadow.py — keep Gamma's eyes on the "smart" free reviewer.

J 2026-06-29: "even though you found a model with a brain, you still need eyes on this.
Don't rely on the smart model's table until it proves >=85% agreement with what YOU produce.
For the first week, score it over multiple angles + edge cases so we know it gives real answers."

TWO MECHANISMS:
  1. LABELED EDGE-CASE SUITE (the upfront proof): a battery of designs with GROUND-TRUTH
     verdicts = Gamma's expert judgment (encoded from the 7-check rubric). Run the smart
     model on each; the smart model must match >=85% before it is trusted to gate alone.
     Covers the failure modes: WR-only, no-OOS, overfit, absurd-stop, look-ahead-y, and
     the legit cases it MUST approve. Cheap, repeatable, runnable any time.
  2. PRODUCTION SHADOW LEDGER (ongoing): every real review by the smart model is logged
     next to Gamma's verdict; rolling agreement is tracked. The smart model only graduates
     to autonomous gating once rolling agreement >=85% over the trailing window.

Until graduation: the smart model SCORES, Gamma DECIDES (human-in-the-loop). This file is
the test that earns the model its autonomy — process > blind trust.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch")); sys.path.insert(0, str(REPO / "setup" / "scripts")); sys.path.insert(0, str(REPO))
import backtest_design_swarm as bds  # noqa: E402

OUT = REPO / "analysis" / "design-swarm"
LEDGER = OUT / "review-shadow-ledger.jsonl"
SCORECARD = OUT / "review-shadow-scorecard.json"
GRAD_THRESHOLD = 0.85


def _D(name, **kw):
    return bds.Design(name=name, **kw)


# GROUND TRUTH = Gamma's judgment. (design, expected_recommended, why)
LABELED_CASES = [
    # --- MUST REJECT (the traps) ---
    (_D("WR-only full split (the trap that fooled us)", side="P", disable_filters=[5], stop_sweep=[-0.50], metric="wr", split="full"),
     False, "judged on win-rate alone, no expectancy, no OOS"),
    (_D("expectancy but NO OOS, claims edge", side="P", disable_filters=[5], stop_sweep=[-0.20], metric="expectancy", split="full"),
     False, "no out-of-sample split while claiming edge"),
    (_D("absurd positive stop", side="P", disable_filters=[5], stop_sweep=[0.20], metric="expectancy", split="oos"),
     False, "stop is positive (nonsense)"),
    (_D("drawdown-only, no edge metric", side="P", disable_filters=[5], stop_sweep=[-0.50], metric="drawdown", split="full"),
     False, "risk metric only, no expectancy/edge metric, no OOS"),
    (_D("overfit: 1 filter combo, no OOS, single stop, full", side="P", disable_filters=[5, 9, 6, 7], stop_sweep=[-0.50], metric="wr", split="full"),
     False, "WR-only + no OOS + many filters disabled (loose+unvalidated)"),
    # --- MUST ACCEPT (legit) ---
    (_D("expectancy + OOS + tight-stop sweep", side="P", disable_filters=[5], stop_sweep=[-0.50, -0.20, -0.08], metric="expectancy", split="oos"),
     True, "proper metric + OOS + stop sweep"),
    (_D("payoff ratio + OOS", side="P", disable_filters=[5], stop_sweep=[-0.30, -0.15], metric="payoff", split="oos"),
     True, "asymmetry metric + OOS"),
    (_D("VIX-regime stratified expectancy", side="P", disable_filters=[5], stop_sweep=[-0.20], metric="expectancy", split="full", strata="vix"),
     True, "stratified expectancy surfaces regime-dependence (the OOS truth)"),
    (_D("bull side expectancy + OOS", side="C", disable_filters=[], stop_sweep=[-0.30, -0.15], metric="expectancy", split="oos", enable_bullish=True),
     True, "legit bull-side expectancy + OOS"),
    (_D("expectancy OOS, minimal but sound", side="P", disable_filters=[5], stop_sweep=[-0.20], metric="expectancy", split="oos"),
     True, "expectancy + OOS present — minimal but legitimate"),
]


def run_labeled(model: str = "nvidia/nemotron-3-super-120b-a12b:free") -> dict:
    rows, hits = [], 0
    for d, expected, why in LABELED_CASES:
        v = bds.smart_review_design(d, model=model)
        agree = (v["recommended"] == expected)
        hits += int(agree)
        rows.append({"design": d.name, "expected": expected, "smart": v["recommended"],
                     "score": v["score"], "agree": agree, "flags": v["flags"][:3], "gamma_why": why})
    acc = hits / len(LABELED_CASES)
    out = {"model": model, "n": len(LABELED_CASES), "agreement": round(acc, 3),
           "threshold": GRAD_THRESHOLD, "graduated": acc >= GRAD_THRESHOLD,
           "verdict": ("TRUSTED — matches Gamma >=85%" if acc >= GRAD_THRESHOLD
                       else "NOT TRUSTED — Gamma stays in the loop"),
           "cases": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    SCORECARD.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def log_production_review(design: "bds.Design", smart_verdict: dict, gamma_verdict: dict | None) -> None:
    """Append a real review to the shadow ledger (smart vs Gamma). gamma_verdict=None when
    Gamma hasn't weighed in yet (it gets backfilled on review)."""
    OUT.mkdir(parents=True, exist_ok=True)
    row = {"design": asdict(design), "smart": smart_verdict, "gamma": gamma_verdict,
           "agree": (None if gamma_verdict is None else smart_verdict.get("recommended") == gamma_verdict.get("recommended"))}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def rolling_agreement() -> dict:
    if not LEDGER.exists():
        return {"n": 0, "agreement": None, "note": "no production reviews logged yet"}
    pairs = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
    scored = [p for p in pairs if p.get("agree") is not None]
    if not scored:
        return {"n": len(pairs), "agreement": None, "note": "no Gamma verdicts logged yet"}
    agree = sum(1 for p in scored if p["agree"]) / len(scored)
    return {"n": len(scored), "agreement": round(agree, 3), "graduated": agree >= GRAD_THRESHOLD}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="nvidia/nemotron-3-super-120b-a12b:free")
    args = ap.parse_args()
    res = run_labeled(args.model)
    print(f"\n=== SMART-REVIEWER SHADOW SCORECARD ({res['model'].split('/')[-1]}) ===")
    for c in res["cases"]:
        mark = "OK " if c["agree"] else "XX "
        print(f"  {mark} {c['design'][:44]:46} expected={str(c['expected']):5} smart={str(c['smart']):5} (score {c['score']})")
    print(f"\n  AGREEMENT vs Gamma ground truth: {res['agreement']:.0%}  (gate {GRAD_THRESHOLD:.0%})")
    print(f"  VERDICT: {res['verdict']}")
