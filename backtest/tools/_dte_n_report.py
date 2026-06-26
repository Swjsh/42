"""Report achievable n per family per DTE on the REAL fetched cache, by running the
sim's exact fill path. Reuses _dte_expansion_sim. For each family x DTE x the v15-default
strike/stop cell band, counts filled trades + OOS n + held-overnight stats. The gate:
adequate_n = vwap_continuation reaches n>=20 at 1DTE in at least one strike cell.

Pure python, $0. Run: backtest/.venv/Scripts/python.exe backtest/tools/_dte_n_report.py
"""
from __future__ import annotations
import datetime as dt, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]; ROOT = REPO.parent
for p in (str(REPO), str(ROOT)):
    if p not in sys.path: sys.path.insert(0, p)
from autoresearch import _dte_expansion_sim as S

spy, vix = S._load_spy_vix()
day_oc = S._spy_day_open_close(spy)
days = S.build_day_contexts(spy)

REPORT = {}
for fam in ("vwap_continuation", "orb_continuation"):
    detect = S.FAMILIES[fam]
    sigs = detect(days, vix, spy)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in sigs})
    REPORT[fam] = {"n_signals": len(sigs), "signal_days": sig_days, "by_dte": {}}
    print(f"\n=== {fam}: {len(sigs)} signals / {sig_days} days ===")
    for dte in (0, 1, 2):
        if dte: S._build_expiry_index(dte)
        best_n = best_oos = 0; best_cell = None; cells = []
        for so in S.STRIKE_OFFSETS:
            for ps in S.PREMIUM_STOPS:
                rows, cov = S.run_cell(sigs, spy, day_oc, dte, strike_offset=so, premium_stop_pct=ps)
                m = S.metrics(rows)
                n = m.get("n", 0); oos = m.get("oos_n", 0)
                held = m.get("overnight", {}).get("held_overnight_pct", 0) if dte else 0
                cells.append({"off": so, "stop": ps, "n": n, "oos_n": oos,
                              "fill_rate": cov["fill_rate"], "held_overnight_pct": held})
                if n > best_n: best_n = n; best_cell = (so, ps)
                if oos > best_oos: best_oos = oos
        REPORT[fam]["by_dte"][str(dte)] = {"max_n": best_n, "max_oos_n": best_oos,
                                           "best_cell_off_stop": best_cell, "cells": cells}
        print(f"  DTE={dte}: max_n={best_n} max_oos_n={best_oos} best_cell={best_cell}")

vwap1 = REPORT["vwap_continuation"]["by_dte"]["1"]
adequate = vwap1["max_n"] >= 20 and vwap1["max_oos_n"] >= 20
REPORT["adequate_n"] = adequate
REPORT["adequate_n_basis"] = f"vwap_continuation 1DTE max_n={vwap1['max_n']} max_oos_n={vwap1['max_oos_n']} (need >=20 OOS)"
out = ROOT / "analysis" / "recommendations" / "dte-n-report.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(REPORT, indent=2, default=str))
print(f"\nadequate_n={adequate}  ({REPORT['adequate_n_basis']})")
print(f"wrote {out}")
