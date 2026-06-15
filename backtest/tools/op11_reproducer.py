"""OP-11 in-process reproducer — prove the Karpathy shadow loop closes.

Runs the full loop offline (no market days, no LLM) and prints a human-readable
trace of every hop:

    stage candidate -> per-bar dual evaluation (prod vs shadow) -> metric diff
    -> auto-ratify gate -> scorecard verdict -> STAGED params bump (REVOKE model)
    -> rollback (production params.json proven byte-identical).

Usage:
    cd backtest
    python tools/op11_reproducer.py                       # default candidate, BS sim
    python tools/op11_reproducer.py --real-fills          # real OPRA fills
    python tools/op11_reproducer.py --start 2026-02-01 --end 2026-05-07 \
        --candidate '{"min_ribbon_momentum_cents": 3.0}'

The shadow is read-only by construction: this script NEVER writes production
state. Scorecards go to a temp dir; the "ratify" step only STAGES a one-line diff
to a CHANGES-PENDING file for a human to apply or REVOKE.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib import shadow  # noqa: E402
from lib.shadow import run_shadow_backtest, write_shadow_scorecard  # noqa: E402

DATA = BACKTEST / "data"
PARAMS = REPO / "automation" / "state" / "params.json"


def _load(start: str, end: str, master: str) -> tuple[pd.DataFrame, pd.DataFrame, Path, Path]:
    sp = DATA / f"spy_5m_{master}.csv"
    vp = DATA / f"vix_5m_{master}.csv"
    spy = pd.read_csv(sp)
    vix = pd.read_csv(vp)
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    return spy, vix, sp, vp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-02-01")
    ap.add_argument("--end", default="2026-05-07")
    ap.add_argument("--master", default="2025-01-01_2026-05-22", help="master CSV window suffix")
    ap.add_argument("--candidate", default='{"min_ribbon_momentum_cents": 3.0}',
                    help="JSON params.json-shaped override dict to test as the shadow")
    ap.add_argument("--real-fills", action="store_true")
    args = ap.parse_args()

    overrides = json.loads(args.candidate)
    spy, vix, sp, vp = _load(args.start, args.end, args.master)

    # Route scorecards to a temp dir — never touch analysis/recommendations.
    tmp = Path(tempfile.mkdtemp(prefix="op11_"))
    shadow.RECOMMENDATIONS_DIR = tmp

    before = hashlib.sha256(PARAMS.read_bytes()).hexdigest()

    print("=" * 70)
    print(f"OP-11 LOOP TRACE  window={args.start}..{args.end}  fills={'real' if args.real_fills else 'BS'}")
    print(f"candidate overrides: {overrides}")
    print("=" * 70)
    print("[1] staging candidate into a shadow overlay (in-memory, prod untouched)")

    res = run_shadow_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(args.start),
        end_date=dt.date.fromisoformat(args.end),
        shadow_overrides=overrides,
        rule_id="REPRO_CANDIDATE",
        title="op11 reproducer candidate",
        spy_path=sp, vix_path=vp,
        use_real_fills=args.real_fills,
        check_sub_window=True,
    )

    pm, sm = res.prod_metrics, res.shadow_metrics
    print("[2] per-bar dual evaluation complete")
    print(f"    PROD (v15.3): n={pm.n_trades:>3}  pnl=${pm.total_pnl:>9.2f}  wr={pm.hit_rate}  thr={pm.thresholds_passed}/4")
    print(f"    SHADOW      : n={sm.n_trades:>3}  pnl=${sm.total_pnl:>9.2f}  wr={sm.hit_rate}  thr={sm.thresholds_passed}/4")
    ab_real = (pm.n_trades, pm.total_pnl) != (sm.n_trades, sm.total_pnl)
    print(f"[3] A/B is REAL (prod != shadow): {ab_real}   regressed={res.regressed_metrics}")
    print(f"[4] auto-ratify gate -> dominates={res.dominates}  eligible={res.auto_ratify_eligible}")

    path = write_shadow_scorecard(res)
    verdict = json.loads(path.read_text())["verdict"]
    print(f"[5] scorecard verdict: {verdict}   ({path})")

    print("[6] STAGED bump (REVOKE model):")
    if res.auto_ratify_eligible:
        pending = tmp / "CHANGES-PENDING.md"
        pending.write_text(
            f"# PENDING param change (auto-ratify) — REVOKE within 24h to cancel\n"
            f"candidate: {json.dumps(overrides)}\n"
            f"verdict: {verdict}\nscorecard: {path}\n"
            f"revoke by: delete this file OR set shadow-version.json enabled=false\n"
        )
        print(f"    candidate DOMINATES -> staged to {pending} (human applies/REVOKEs)")
    else:
        print(f"    not eligible ({verdict}) -> nothing staged. Loop correctly withheld a non-dominating candidate.")

    after = hashlib.sha256(PARAMS.read_bytes()).hexdigest()
    print(f"[7] ROLLBACK / read-only invariant: production params.json byte-identical = {before == after}")
    print("=" * 70)
    print("LOOP CLOSED." if before == after else "ERROR: production state mutated!")
    return 0 if before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
