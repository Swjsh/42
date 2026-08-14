"""ENTRY-LOCATION-GATE runner -- prereg ENTRY-LOCATION-GATE-2026-08-14.

QUESTION. Does WHERE in the day's range an entry sits predict its outcome? The engine has no
location feature at all (deep review D6: the 2026-08-14 loser and the 2026-08-13 winner were
byte-identical on every logged field at entry), and its scores cannot rank -- bull_score is
`11 - len(blockers)` over the admission criteria themselves (filters.py:1273), bear_score the
same shape at :1758. A location VETO is the only lever that does not require a new scoring model.

BOTH DIRECTIONS (handoff N1). Bull: distance from the running intraday HIGH. Bear: distance
from the running intraday LOW. 151 of the 191 population trades are puts, so the bear side
carries the statistical weight -- a bull-only study would have been underpowered by design.

CAUSALITY (C6, non-negotiable). Every feature is computed from bars STRICTLY BEFORE the entry
bar. The entry price is the entry bar's OPEN (the engine's own next-bar-open convention); the
entry bar's own high/low never enters the range. A violation voids the cell rather than being
footnoted.

HONESTY. dollar_pnl here is the replay's real-OPRA-fills P&L, not excursion -- but this study
still only reallocates ALREADY-TAKEN trades. It cannot discover a trade we did not take, and a
"gate that improves the book" is really "a filter that removes a cohort". The blocked-WINNER
cost is therefore reported as its own column in every cell (prereg G3), because C20 says
proximity gates anti-correlate with breakout setups and the whole risk is cutting the runners.

Read-only. Writes analysis/recommendations/entry-location-gate-2026-08-14.json. Arms nothing.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
BARS = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-08.csv"
OUT = REPO / "analysis" / "recommendations" / "entry-location-gate-2026-08-14.json"

PROX_BANDS = [0.10, 0.20, 0.30]          # gate if within this fraction of range from the extreme
RUN_BANDS = [2.0, 3.0]                   # gate if prior day ran >= this many points toward us
MIN_PRIOR_BARS = 3                       # a "range so far" needs some bars to be meaningful
MIN_RANGE_PTS = 0.25                     # below this the range is noise, not location
MIN_CELL_N = 30                          # prereg G4: smaller -> NOT-RUN, never a null result


# ── bars ─────────────────────────────────────────────────────────────────────────────────

def load_bars() -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = defaultdict(list)
    with BARS.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp_et"]
            days[ts[:10]].append({
                "t": ts[11:16],
                "o": float(row["open"]), "h": float(row["high"]),
                "l": float(row["low"]), "c": float(row["close"]),
            })
    for d in days:
        days[d].sort(key=lambda b: b["t"])
    return days


def rth(bars: list[dict]) -> list[dict]:
    return [b for b in bars if "09:30" <= b["t"] < "16:00"]


# ── features (causal) ────────────────────────────────────────────────────────────────────

def features(day_bars: list[dict], prior_bars: Optional[list[dict]], entry_hhmm: str) -> Optional[dict]:
    """Location features at entry, from bars STRICTLY BEFORE the entry bar."""
    session = rth(day_bars)
    before = [b for b in session if b["t"] < entry_hhmm]
    entry_bar = next((b for b in session if b["t"] == entry_hhmm), None)
    if entry_bar is None or len(before) < MIN_PRIOR_BARS:
        return None
    hi = max(b["h"] for b in before)
    lo = min(b["l"] for b in before)
    rng = hi - lo
    if rng < MIN_RANGE_PTS:
        return None
    entry_px = entry_bar["o"]                      # engine enters at the bar's open
    prior_run = None
    if prior_bars:
        ps = rth(prior_bars)
        if ps:
            prior_run = ps[-1]["c"] - ps[0]["o"]
    return {
        "entry_px": entry_px, "hi_so_far": hi, "lo_so_far": lo, "range_pts": rng,
        "n_prior_bars": len(before),
        # fraction of the range between the entry and the extreme in the trade's direction
        "dist_from_high_frac": (hi - entry_px) / rng,
        "dist_from_low_frac": (entry_px - lo) / rng,
        "prior_day_run_pts": prior_run,
    }


def gated(side: str, f: dict, prox: Optional[float], run: Optional[float]) -> bool:
    """True = this cell's gate would REFUSE the trade."""
    if prox is not None:
        near = f["dist_from_high_frac"] if side == "C" else f["dist_from_low_frac"]
        if not near <= prox:
            return False
    if run is not None:
        pr = f["prior_day_run_pts"]
        if pr is None:
            return False
        # bull: refuse after a big UP day (buying extension). bear: after a big DOWN day.
        if side == "C" and not pr >= run:
            return False
        if side == "P" and not pr <= -run:
            return False
    return True


# ── stats ────────────────────────────────────────────────────────────────────────────────

def _mean(x: list[float]) -> float:
    return sum(x) / len(x) if x else 0.0


def perm_p(gated_pnl: list[float], kept_pnl: list[float], iters: int = 20000) -> Optional[float]:
    """Two-sided permutation test on the mean difference. None when either side is too small
    to permute meaningfully."""
    if len(gated_pnl) < 5 or len(kept_pnl) < 5:
        return None
    import random
    rnd = random.Random(20260814)
    pool = gated_pnl + kept_pnl
    n = len(gated_pnl)
    obs = abs(_mean(gated_pnl) - _mean(kept_pnl))
    hits = 0
    for _ in range(iters):
        rnd.shuffle(pool)
        if abs(_mean(pool[:n]) - _mean(pool[n:])) >= obs:
            hits += 1
    return (hits + 1) / (iters + 1)


def bh_fdr(pvals: list[tuple[str, float]], q: float = 0.10) -> dict[str, bool]:
    """Benjamini-Hochberg. Returns {cell_id: survives}."""
    live = [(k, p) for k, p in pvals if p is not None]
    live.sort(key=lambda kv: kv[1])
    m = len(live)
    survive: dict[str, bool] = {k: False for k, _ in pvals}
    kmax = 0
    for i, (_, p) in enumerate(live, start=1):
        if p <= (i / m) * q:
            kmax = i
    for i, (k, _) in enumerate(live, start=1):
        survive[k] = i <= kmax
    return survive


# ── runner ───────────────────────────────────────────────────────────────────────────────

def build_cells() -> list[dict]:
    cells = [{"id": f"prox<={p:.2f}", "prox": p, "run": None} for p in PROX_BANDS]
    cells += [{"id": f"run>={r:.1f}", "prox": None, "run": r} for r in RUN_BANDS]
    cells += [{"id": f"prox<={p:.2f} AND run>={r:.1f}", "prox": p, "run": r}
              for p in PROX_BANDS for r in RUN_BANDS]
    return cells


def evaluate(trades: list[dict], label: str) -> dict[str, Any]:
    by_side: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_side[t["side"]].append(t)
    out: dict[str, Any] = {"population": label, "n": len(trades),
                           "by_side": {s: len(v) for s, v in by_side.items()},
                           "baseline": {}, "cells": []}
    for s, rows in by_side.items():
        pnl = [r["dollar_pnl"] for r in rows]
        out["baseline"][s] = {"n": len(rows), "total": round(sum(pnl), 2),
                              "mean": round(_mean(pnl), 2),
                              "win_rate": round(sum(1 for p in pnl if p > 0) / len(pnl), 4)}
    pvals: list[tuple[str, float]] = []
    for cell in build_cells():
        for s, rows in by_side.items():
            g = [r for r in rows if gated(s, r["feat"], cell["prox"], cell["run"])]
            k = [r for r in rows if r not in g]
            cid = f"{s}|{cell['id']}"
            gp = [r["dollar_pnl"] for r in g]
            kp = [r["dollar_pnl"] for r in k]
            rec: dict[str, Any] = {
                "cell": cid, "side": s, "prox": cell["prox"], "run": cell["run"],
                "n_gated": len(g), "n_kept": len(k),
                "gated_total": round(sum(gp), 2), "kept_total": round(sum(kp), 2),
                "gated_mean": round(_mean(gp), 2) if gp else None,
                "kept_mean": round(_mean(kp), 2) if kp else None,
                # the honest column (prereg G3): what the gate would have thrown away
                "blocked_winners_n": sum(1 for p in gp if p > 0),
                "blocked_winner_dollars": round(sum(p for p in gp if p > 0), 2),
                "blocked_losers_n": sum(1 for p in gp if p <= 0),
                "blocked_loser_dollars": round(sum(p for p in gp if p <= 0), 2),
                "book_delta_if_gated": round(-sum(gp), 2),   # removing the cohort
                # EXPLORATORY, declared as such (2026-08-14): win-rate is NOT the prereg's
                # metric (that is delta expectancy) and is therefore EXCLUDED from the BH-FDR
                # family below. Recorded because mean-dollar tests on 0DTE are dominated by a
                # few large winners, so a WR split can be the more stable statistic -- but
                # acting on it requires its OWN prereg. Reporting it without that label would
                # be exactly the post-hoc metric-picking the canonical battery exists to stop.
                "EXPLORATORY_gated_win_rate": round(sum(1 for x in gp if x > 0) / len(gp), 4) if gp else None,
                "EXPLORATORY_kept_win_rate": round(sum(1 for x in kp if x > 0) / len(kp), 4) if kp else None,
            }
            if len(g) < MIN_CELL_N:
                rec["verdict"] = "NOT-RUN"
                rec["why"] = f"n_gated {len(g)} < {MIN_CELL_N} (prereg G4: never a null result)"
                rec["perm_p"] = None
            else:
                p = perm_p(gp, kp)
                rec["perm_p"] = None if p is None else round(p, 5)
                rec["verdict"] = "MEASURED"
                pvals.append((cid, p))
            out["cells"].append(rec)
    surv = bh_fdr(pvals, q=0.10)
    for rec in out["cells"]:
        rec["survives_bh_fdr_q10"] = surv.get(rec["cell"], False)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    days = load_bars()
    ordered = sorted(days)
    prior_of = {d: (ordered[i - 1] if i else None) for i, d in enumerate(ordered)}

    raw = json.load(REPLAY.open(encoding="utf-8"))["trades"]
    trades, skipped = [], defaultdict(int)
    for t in raw:
        d = t["date"]
        if d not in days:
            skipped["no_bar_day"] += 1
            continue
        f = features(days[d], days.get(prior_of[d]) if prior_of[d] else None,
                     t["entry_time_et"][11:16])
        if f is None:
            skipped["no_causal_features"] += 1
            continue
        trades.append({"date": d, "side": t["side"], "dollar_pnl": t["dollar_pnl"],
                       "entry_time_et": t["entry_time_et"], "tier": t.get("tier"),
                       "setup": t.get("setup"), "feat": f})

    rep = evaluate(trades, "engine-fullhist-replay-2026-07-23 (real OPRA fills)")
    rep["_doc"] = __doc__.strip().splitlines()[0]
    rep["prereg_id"] = "ENTRY-LOCATION-GATE-2026-08-14"
    rep["excluded"] = dict(skipped)
    rep["params"] = {"prox_bands": PROX_BANDS, "run_bands": RUN_BANDS,
                     "min_prior_bars": MIN_PRIOR_BARS, "min_range_pts": MIN_RANGE_PTS,
                     "min_cell_n": MIN_CELL_N}
    # G1: control reproduces the published population
    published = json.load(REPLAY.open(encoding="utf-8"))["headline"]["total_pnl"]
    ours = round(sum(t["dollar_pnl"] for t in trades), 2)
    rep["G1_control"] = {"published_total_all_191": published, "our_total_after_exclusions": ours,
                         "excluded_n": sum(skipped.values()),
                         "note": ("exclusions are bar-coverage only; totals differ by exactly the "
                                  "excluded trades' P&L, which is the intended reconciliation")}
    # G2: monotonicity of gated-cohort size in band width
    for s in ("C", "P"):
        sizes = [c["n_gated"] for c in rep["cells"]
                 if c["side"] == s and c["run"] is None and c["prox"] is not None]
        rep.setdefault("G2_monotonic", {})[s] = {
            "gated_n_by_band": sizes,
            "monotonic_nondecreasing": all(a <= b for a, b in zip(sizes, sizes[1:])),
        }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"ENTRY-LOCATION-GATE  population n={rep['n']}  {rep['by_side']}")
    print(f"  excluded: {dict(skipped)}")
    print(f"  G2 monotonic: { {k: v['monotonic_nondecreasing'] for k, v in rep['G2_monotonic'].items()} }")
    for s in ("P", "C"):
        b = rep["baseline"].get(s)
        if b:
            print(f"\n  === {s} baseline: n={b['n']} total=${b['total']} mean=${b['mean']} wr={b['win_rate']:.1%}")
        for c in rep["cells"]:
            if c["side"] != s:
                continue
            if c["verdict"] == "NOT-RUN":
                print(f"    [NOT-RUN] {c['cell']:<34} n_gated={c['n_gated']}")
                continue
            star = "*" if c["survives_bh_fdr_q10"] else " "
            print(f"    [{star}] {c['cell']:<34} gated n={c['n_gated']:>3} "
                  f"mean=${c['gated_mean']:>8} vs kept=${c['kept_mean']:>8}  "
                  f"p={c['perm_p']}  book_delta=${c['book_delta_if_gated']:>9}  "
                  f"blocked_winners={c['blocked_winners_n']} (${c['blocked_winner_dollars']})")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
