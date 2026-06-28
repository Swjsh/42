"""contender_oos_check.py — single-combo OOS validation for the promote_keeper pipeline.

Runs the TOP contender from the newest contender-rank-*.json file through the
strategy_space_grind harness and emits a structured A/B scorecard JSON at
analysis/recommendations/{proposal_id}-scorecard.json.

GATES CHECKED (OP-11 auto-ship bar):
  1. oos_positive     -- OOS total PnL > 0 (OOS = 2026-01-01..END)
  2. wf_ge_0.70       -- OOS/IS per-trade expectancy ratio >= 0.70
  3. sub_window_stable -- fraction of quarters with positive expectancy >= 0.60
  4. anchor_no_regression -- edge_capture >= 771 (50% of J-edge max, OP-16)

If ALL gates pass -> prints EVAL_BAR_CLEARED=TRUE
If ANY gate fails -> prints EVAL_BAR_CLEARED=FALSE with which gate failed.

Output written to: analysis/recommendations/<proposal_id>-scorecard.json

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/contender_oos_check.py
  backtest/.venv/Scripts/python.exe backtest/autoresearch/contender_oos_check.py --proposal-id pk-2026-06-28-001
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent  # backtest/
_ROOT = _REPO.parent                            # repo root
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import autoresearch.strategy_space_grind as ssg  # noqa: E402
from autoresearch.runner import load_data         # noqa: E402

RECS_DIR = _ROOT / "analysis" / "recommendations"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"


def _find_newest_contender() -> Path:
    files = sorted(RECS_DIR.glob("contender-rank-*.json"))
    if not files:
        raise SystemExit("No contender-rank-*.json files found.")
    return files[-1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-id", default=None,
                        help="Proposal ID for the scorecard filename (e.g. pk-2026-06-28-001)")
    args = parser.parse_args()

    # 1. Load the top contender.
    cfile = _find_newest_contender()
    cdata = _load_json(cfile)
    top = cdata["top"][0]
    label = top["label"]
    combo = top["combo"]
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    ranked_at = cdata.get("ranked_at_et", "unknown")

    print(f"Contender file: {cfile.name}")
    print(f"Label:          {label}")
    print(f"Ranked at:      {ranked_at}")
    print(f"IS metrics:     edge={top['edge_capture']:.2f}  wf={top['wf']:.3f}  n={top['n']}")
    print()

    # 2. Load base params + data.
    print("Loading params and market data (SPY+VIX bars)...")
    base_params = _load_json(PARAMS_PATH)
    spy, vix = load_data(ssg.START, ssg.END)
    print("Data loaded.")
    print()

    # 3. Build the gate patch identical to mass_grind._run().
    patch = dict(ssg.L2_PATCH)
    patch["block_level_rejection"] = bool(blr)
    patch["min_triggers_bear"] = int(mt)
    patch["min_triggers_bull"] = int(mt)
    patch["tp1_premium_pct"] = float(tp)
    patch["tp1_qty_fraction"] = float(tq)
    patch["profit_lock_mode"] = str(lk)

    print(f"Applying combo params:")
    print(f"  strike_offset={so}  stop_pct={sv}  tp1={tp:.0%}  qty_frac={tq:.3f}  lock={lk}")
    print(f"  block_lr={blr}  min_triggers={mt}")
    print()

    # 4. Run the real-fills backtest.
    print("Running backtest (real OPRA fills)...")
    trades = ssg.run_cell(spy, vix, base_params,
                          strike_offset=int(so),
                          gate_patch=patch,
                          stop_pct=float(sv))
    print(f"  {len(trades)} trades loaded.")
    print()

    # 5. Compute metrics.
    m = ssg.metrics_for(trades)
    val = m["_validation"]

    # Gate checks.
    oos_pos = bool(val["gate"]["oos_positive"])
    wf_pass = bool(val["gate"]["wf_ge_0.70"])
    sw_pass = bool(val["gate"]["sub_window_stable"])
    anchor_pass = m["edge_capture"] >= ssg.EDGE_CAPTURE_REJECT_BELOW

    all_pass = oos_pos and wf_pass and sw_pass and anchor_pass

    # 6. Build scorecard.
    proposal_id = args.proposal_id or f"pk-{cfile.stem.replace('contender-rank-', '')}-001"
    scorecard = {
        "proposal_id": proposal_id,
        "scored_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "contender_file": cfile.name,
        "contender_label": label,
        "contender_ranked_at": ranked_at,
        "combo": combo,
        "is_metrics": {
            "edge_capture": top["edge_capture"],
            "wf": top["wf"],
            "n": top["n"],
            "expectancy": top["expectancy"],
            "wr": top["wr"],
            "max_dd": top["max_dd"],
        },
        "full_window": {
            "n": m["n"],
            "edge_capture": m["edge_capture"],
            "expectancy": m["expectancy"],
            "wr": m["wr"],
            "max_dd": m["max_dd"],
            "total_dollar": m["total"],
            "trading_days": m["trading_days"],
            "wf_per_trade": m["wf"],
        },
        "oos_split": {
            "IS": f"<{ssg.OOS_BOUNDARY}",
            "OOS": f">={ssg.OOS_BOUNDARY}",
            "IS_n": val["IS"]["n"],
            "IS_exp": val["IS"]["exp"],
            "IS_total": val["IS"]["total"],
            "OOS_n": val["OOS"]["n"],
            "OOS_exp": val["OOS"]["exp"],
            "OOS_total": val["OOS"]["total"],
            "wf_ratio": val["wf_per_trade"],
        },
        "quarterly": val["quarters"],
        "quarter_positive_fraction": val["quarter_positive_fraction"],
        "gates": {
            "oos_positive": oos_pos,
            "wf_ge_0.70": wf_pass,
            "sub_window_stable_ge_0.60": sw_pass,
            "anchor_no_regression": anchor_pass,
            "ALL_PASS": all_pass,
        },
        "eval_bar_cleared": all_pass,
        "verdict": "CLEARED" if all_pass else "BLOCKED",
        "failed_gates": [
            g for g, v in [
                ("oos_positive", oos_pos),
                ("wf_ge_0.70", wf_pass),
                ("sub_window_stable", sw_pass),
                ("anchor_no_regression", anchor_pass),
            ] if not v
        ],
    }

    # 7. Write scorecard.
    scorecard_path = RECS_DIR / f"{proposal_id}-scorecard.json"
    scorecard_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print(f"Scorecard written: {scorecard_path.name}")
    print()

    # 8. Report.
    print("=" * 60)
    print(f"OOS VALIDATION: {label}")
    print("=" * 60)
    print(f"  Full n={m['n']}  edge_capture={m['edge_capture']:.2f}  exp={m['expectancy']:.2f}")
    print(f"  WF={m['wf']:.3f}  (IS exp={val['IS']['exp']:.2f}  OOS exp={val['OOS']['exp']:.2f})")
    print(f"  Quarterly positive fraction: {val['quarter_positive_fraction']:.2f}")
    print()
    print("GATES:")
    print(f"  oos_positive:        {'PASS' if oos_pos else 'FAIL'}")
    print(f"  wf_ge_0.70:          {'PASS' if wf_pass else 'FAIL'}  ({m['wf']:.3f})")
    print(f"  sub_window_stable:   {'PASS' if sw_pass else 'FAIL'}  ({val['quarter_positive_fraction']:.2f} >= 0.60)")
    print(f"  anchor_no_regression:{'PASS' if anchor_pass else 'FAIL'}  ({m['edge_capture']:.2f} >= 771)")
    print()
    print(f"VERDICT: {'EVAL_BAR_CLEARED=TRUE' if all_pass else 'EVAL_BAR_CLEARED=FALSE'}")
    if not all_pass:
        print(f"  Failed gates: {scorecard['failed_gates']}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
