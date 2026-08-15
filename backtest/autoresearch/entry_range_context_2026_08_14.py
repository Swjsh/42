"""ENTRY-RANGE-CONTEXT runner -- prereg ENTRY-RANGE-CONTEXT-2026-08-14 (frozen 327661f3).

Tests the hypothesis the LOCATION study's anchors generated after refuting location: that an
entry taken while the session's established range is small has worse expectancy, because a
small range means no directional information has been produced yet and 0DTE premium pays theta
+ spread while the underlying does nothing.

THE CONFOUND IS THE POINT. Range is mechanically small early in the session, so a range gate is
partly an open-avoidance gate. Every cell is therefore also run on the >=10:30 ET subset, where
session age no longer explains a small range. Per prereg G4, if the effect dies there the
verdict is CONFOUNDED-WITH-TIME and no gate is proposed.

Population, bar loading and the causal feature function are IMPORTED from the location runner
so the two studies cannot drift. Read-only; arms nothing.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

from entry_location_gate_2026_08_14 import (  # noqa: E402
    MIN_CELL_N, REPLAY, _mean, bh_fdr, features, load_bars, perm_p,
)

OUT = REPO / "analysis" / "recommendations" / "entry-range-context-2026-08-14.json"
THRESHOLDS = [0.75, 1.00, 1.50, 2.00]
LATE_CUTOFF = "10:30"


def evaluate(trades: list[dict], subset: str) -> list[dict]:
    by_side: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_side[t["side"]].append(t)
    cells = []
    for side, rows in by_side.items():
        for th in THRESHOLDS:
            g = [r for r in rows if r["feat"]["range_pts"] < th]
            k = [r for r in rows if r["feat"]["range_pts"] >= th]
            gp = [r["dollar_pnl"] for r in g]
            kp = [r["dollar_pnl"] for r in k]
            rec: dict[str, Any] = {
                "cell": f"{side}|range<{th:.2f}|{subset}", "side": side, "threshold": th,
                "subset": subset, "n_gated": len(g), "n_kept": len(k),
                "gated_total": round(sum(gp), 2), "kept_total": round(sum(kp), 2),
                "gated_mean": round(_mean(gp), 2) if gp else None,
                "kept_mean": round(_mean(kp), 2) if kp else None,
                "blocked_winners_n": sum(1 for p in gp if p > 0),
                "blocked_winner_dollars": round(sum(p for p in gp if p > 0), 2),
                "book_delta_if_gated": round(-sum(gp), 2),
            }
            if len(g) < MIN_CELL_N:
                rec.update(verdict="NOT-RUN", perm_p=None,
                           why=f"n_gated {len(g)} < {MIN_CELL_N}")
            else:
                p = perm_p(gp, kp)
                rec.update(verdict="MEASURED", perm_p=None if p is None else round(p, 5))
            cells.append(rec)
    return cells


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # DATASET INTEGRITY (2026-08-15). This study published its population size off a file
    # that had been mutated out-of-band -- engine-fullhist-replay went 190 -> 191 rows via an
    # unrelated regime-threshold commit, and this runner read the mutated version. Fail here,
    # before computing, rather than publishing a number under a frozen prereg's authority.
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    from dataset_integrity import assert_intact
    assert_intact("analysis/recommendations/engine-fullhist-replay-2026-07-23.json")
    days = load_bars()
    ordered = sorted(days)
    prior_of = {d: (ordered[i - 1] if i else None) for i, d in enumerate(ordered)}
    raw = json.load(REPLAY.open(encoding="utf-8"))["trades"]
    trades = []
    for t in raw:
        d = t["date"]
        if d not in days:
            continue
        f = features(days[d], days.get(prior_of[d]) if prior_of[d] else None,
                     t["entry_time_et"][11:16])
        if f is None:
            continue
        trades.append({"date": d, "side": t["side"], "dollar_pnl": t["dollar_pnl"],
                       "entry_hhmm": t["entry_time_et"][11:16], "feat": f})

    late = [t for t in trades if t["entry_hhmm"] >= LATE_CUTOFF]
    cells = evaluate(trades, "all") + evaluate(late, f">={LATE_CUTOFF}")
    surv = bh_fdr([(c["cell"], c["perm_p"]) for c in cells if c["verdict"] == "MEASURED"], q=0.10)
    for c in cells:
        c["survives_bh_fdr_q10"] = surv.get(c["cell"], False)

    # G3 anchors (outside this window -- reported from the shadow ledger for completeness)
    anchors = {"2026-08-14 09:46 loser": {"range_pts": 0.81},
               "2026-08-13 09:51 winner": {"range_pts": 2.74}}
    for name, a in anchors.items():
        a["gated_by"] = [f"range<{th:.2f}" for th in THRESHOLDS if a["range_pts"] < th]

    rep = {"_doc": __doc__.strip().splitlines()[0],
           "prereg_id": "ENTRY-RANGE-CONTEXT-2026-08-14",
           "n_trades": len(trades), "n_late": len(late),
           "thresholds": THRESHOLDS, "late_cutoff_et": LATE_CUTOFF,
           "G3_anchors": anchors, "cells": cells}
    # G2 monotonicity
    for side in ("C", "P"):
        sizes = [c["n_gated"] for c in cells if c["side"] == side and c["subset"] == "all"]
        rep.setdefault("G2_monotonic", {})[side] = {
            "gated_n_by_threshold": sizes,
            "monotonic_nondecreasing": all(a <= b for a, b in zip(sizes, sizes[1:]))}
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"ENTRY-RANGE-CONTEXT  n={len(trades)}  n(>={LATE_CUTOFF})={len(late)}")
    print(f"  G2 monotonic: { {k: v['monotonic_nondecreasing'] for k, v in rep['G2_monotonic'].items()} }")
    print(f"  G3 anchors: " + "; ".join(f"{k} (range {v['range_pts']}) gated_by={v['gated_by'] or 'NONE'}"
                                        for k, v in anchors.items()))
    for c in cells:
        if c["verdict"] == "NOT-RUN":
            print(f"    [NOT-RUN] {c['cell']:<28} n_gated={c['n_gated']}")
        else:
            star = "*" if c["survives_bh_fdr_q10"] else " "
            print(f"    [{star}] {c['cell']:<28} gated n={c['n_gated']:>3} mean=${c['gated_mean']:>8} "
                  f"vs kept=${c['kept_mean']:>8}  p={c['perm_p']}  "
                  f"blocked_winners={c['blocked_winners_n']} (${c['blocked_winner_dollars']})")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
