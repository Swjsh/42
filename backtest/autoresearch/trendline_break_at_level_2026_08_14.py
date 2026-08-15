"""TRENDLINE-BREAK-AT-LEVEL runner -- prereg `TRENDLINE-BREAK-AT-LEVEL-2026-08-13`.

J, 2026-08-13 ~14:15 ET, unprompted, with a same-day rising support sitting 0.03 from the
close: *"should we be drawing or theorizing on this trend line break as we approach the key
level"*. The existing break dataset is UNCONDITIONAL -- it answers "do trendline breaks pay?"
(no) and has never been sliced on whether the break happened AT a level. This runs that slice.

The prereg was frozen 2026-08-13 and its runner was never written. This is that runner, built
to the frozen spec: 6 pre-registered bands x 4 family-kind combos x 3 horizons = 72 cells, ALL
reported, BH-FDR q=0.10 across the family, date-shuffle null, NOT-RUN below n=30.

HONESTY CLAUSE (the prereg's own words, restated because it governs how the output may be
read): MFE/MAE is EXCURSION, not P&L. No stop, no target, no theta, no spread. A favourable
excursion ratio is NECESSARY but nowhere near SUFFICIENT to trade -- this repo has been burned
by SPY-price edge that did not survive option economics (C3). No cell here may be called
profitable. The maximum possible output is "a cohort worth pricing on real OPRA, separately".

G0 -- THE BAR-INDEX JOIN, VERIFIED NOT ASSUMED. The break dataset's `break_bar_idx` is an
ordinal into the day's RTH bars, but the bar cache is stored on a FIXED -04:00 frame, so RTH
bar 0 carries the label 10:30 in winter and 09:30 in summer (the documented DST frame
artifact). Guessing that offset would silently mis-join every winter date. Instead each date's
anchor is DERIVED by testing both candidates against that date's own `close_at_break` values
and requiring >=99% agreement; a date that cannot be resolved is DROPPED and disclosed, never
joined on a guess.

Read-only. Arms nothing. Streams the 67MB JSONL once (well inside the 5-minute reaper window).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BREAKS = REPO / "analysis" / "trendlines" / "break-dataset.jsonl"
SUMMARY = REPO / "analysis" / "trendlines" / "break-dataset-summary.json"
CACHE = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-08.csv"
OUT = REPO / "analysis" / "recommendations" / "trendline-break-at-level-2026-08-14.json"

BANDS = [0.10, 0.20, 0.35, 0.50, 0.75, 1.00]      # frozen sweep -- all six reported
HORIZONS = [30, 60, 90]
MIN_CELL_N = 30
N_PERM = 1000
RTH_ANCHORS = ("09:30", "10:30")
MAX_RTH_BARS = 96
LEVEL_NAMES = ["PRIOR_DAY_HIGH", "PRIOR_DAY_LOW", "PRIOR_DAY_CLOSE",
               "OVERNIGHT_HIGH", "OVERNIGHT_LOW",
               "INTRADAY_RTH_HIGH_SO_FAR", "INTRADAY_RTH_LOW_SO_FAR"]


# ----------------------------------------------------------------------------- bars + levels
def load_days() -> dict[str, pd.DataFrame]:
    df = pd.read_csv(CACHE)
    ts = pd.to_datetime(df["timestamp_et"])
    df["d"] = ts.dt.strftime("%Y-%m-%d")
    df["t"] = ts.dt.strftime("%H:%M")
    return {d: g.reset_index(drop=True) for d, g in df.groupby("d")}


def resolve_anchor(day: pd.DataFrame, closes_at_break: list[tuple[int, float]]) -> Optional[int]:
    """G0: derive the date's RTH bar-0 row index by REPRODUCING its own break closes."""
    best, best_rate = None, 0.0
    for label in RTH_ANCHORS:
        idx = day.index[day["t"] == label]
        if len(idx) == 0:
            continue
        start = int(idx[0])
        hit = tot = 0
        for bi, cb in closes_at_break:
            j = start + bi
            if j < len(day):
                tot += 1
                hit += abs(float(day["close"].iloc[j]) - cb) < 0.011
        rate = hit / tot if tot else 0.0
        if rate > best_rate:
            best, best_rate = start, rate
    return best if best_rate >= 0.99 else None


def level_grid(days: dict, anchors: dict) -> tuple[np.ndarray, list[str]]:
    """L[date, bar, 7] of level PRICES, causal at each bar. NaN where undefined.

    INTRADAY_* use bars strictly BEFORE the bar index (G2): the running extreme at bar i is
    taken over bars [0, i), so the break bar can never define the level it is breaking into.
    """
    dates = sorted(anchors)
    L = np.full((len(dates), MAX_RTH_BARS, len(LEVEL_NAMES)), np.nan, dtype=float)
    prev_rth: Optional[pd.DataFrame] = None
    prev_end_pos: Optional[int] = None
    prev_date: Optional[str] = None
    for di, d in enumerate(dates):
        day, start = days[d], anchors[d]
        rth = day.iloc[start:start + MAX_RTH_BARS]
        if prev_rth is not None:
            L[di, :, 0] = float(prev_rth["high"].max())
            L[di, :, 1] = float(prev_rth["low"].min())
            L[di, :, 2] = float(prev_rth["close"].iloc[-1])
            # overnight = bars after the PRIOR session's last RTH bar, through this session's
            # open -- i.e. the prior day's post-RTH tail plus this day's pre-RTH bars.
            tail = days[prev_date].iloc[prev_end_pos:]
            pre = day.iloc[:start]
            on = pd.concat([tail, pre]) if len(tail) or len(pre) else None
            if on is not None and len(on):
                L[di, :, 3] = float(on["high"].max())
                L[di, :, 4] = float(on["low"].min())
        highs = rth["high"].to_numpy(dtype=float)
        lows = rth["low"].to_numpy(dtype=float)
        n = len(highs)
        if n:
            run_hi = np.maximum.accumulate(highs)
            run_lo = np.minimum.accumulate(lows)
            # STRICTLY BEFORE: bar i sees [0, i) -> shift by one, bar 0 sees nothing.
            L[di, 1:n, 5] = run_hi[: n - 1]
            L[di, 1:n, 6] = run_lo[: n - 1]
        prev_rth, prev_end_pos, prev_date = rth, start + len(rth), d
    return L, dates


# ----------------------------------------------------------------------------- stats
def bh_fdr(pairs: list[tuple[str, float]], q: float = 0.10) -> dict[str, bool]:
    valid = [(k, p) for k, p in pairs if p is not None]
    if not valid:
        return {}
    valid.sort(key=lambda kp: kp[1])
    m, cut = len(valid), 0
    for i, (_, p) in enumerate(valid, 1):
        if p <= q * i / m:
            cut = i
    return {k: (i <= cut) for i, (k, _) in enumerate(valid, 1)}


def ratio(mfe: np.ndarray, mae: np.ndarray) -> Optional[float]:
    """Aggregate MFE/MAE. Returns None -- never NaN -- when undefined.

    THE FIRST RUN OF THIS STUDY REPORTED 72/72 CELLS SURVIVING BH-FDR AT p=0.001. That is
    impossible on a null hypothesis this repo's own prereg expected to hold, and it was an
    artifact, caught before anything was written up (/fable-too-good: suspicion scales with
    how good it looks). Mechanism: 2,333 of 52,833 breaks occur too close to the close to have
    forward bars, so their mfe/mae are null -> NaN -> every sum NaN -> every ratio NaN. The
    permutation counter then compared `abs(nan) >= abs(nan)`, which is False EVERY time, so no
    permutation ever counted as a hit and every p collapsed to the floor 1/(K+1).
    A NaN that silently becomes "significant" is the most dangerous shape a bug can take here,
    so the null rows are now excluded explicitly and this function refuses to return NaN."""
    s, t = float(mae.sum()), float(mfe.sum())
    if not np.isfinite(s) or not np.isfinite(t) or s <= 0:
        return None
    return t / s


# ----------------------------------------------------------------------------- main
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    days = load_days()

    # pass 1 -- stream, collect rows, gather per-date (bar_idx, close) for anchor resolution
    raw: list[dict] = []
    probe: dict[str, list] = defaultdict(list)
    with BREAKS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            b = r.get("break")
            if not b:
                continue
            raw.append(r)
            if len(probe[r["date_et"]]) < 40:
                probe[r["date_et"]].append((b["break_bar_idx"], b["close_at_break"]))
    print(f"break rows with a break: {len(raw):,}  dates: {len(probe)}")

    anchors, unresolved = {}, []
    for d, cb in probe.items():
        if d not in days:
            unresolved.append((d, "date_not_in_cache"))
            continue
        a = resolve_anchor(days[d], cb)
        if a is None:
            unresolved.append((d, "anchor_unresolved"))
        else:
            anchors[d] = a
    print(f"G0 anchors resolved: {len(anchors)}/{len(probe)} dates "
          f"({len(unresolved)} dropped)")

    L, dates = level_grid(days, anchors)
    dpos = {d: i for i, d in enumerate(dates)}

    # EXCLUDE breaks with no forward bars (too close to the close to have an excursion at
    # ALL horizons). 2,333 of 52,833. They are not zeros; they are undefined -- see ratio().
    def _has_exc(r: dict) -> bool:
        return all(r["break"].get(f"mfe_{h}min") is not None
                   and r["break"].get(f"mae_{h}min") is not None for h in HORIZONS)

    n_null_exc = sum(1 for r in raw if not _has_exc(r))
    keep = [r for r in raw if r["date_et"] in dpos
            and r["break"]["break_bar_idx"] < MAX_RTH_BARS and _has_exc(r)]
    dropped_rows = len(raw) - len(keep)

    di = np.array([dpos[r["date_et"]] for r in keep])
    bi = np.array([r["break"]["break_bar_idx"] for r in keep])
    line = np.array([r["break"]["line_value_at_break"] for r in keep], dtype=float)
    fam = np.array([f'{r["anchor_family"]}_{r["kind"]}' for r in keep])
    mfe = {h: np.array([r["break"][f"mfe_{h}min"] for r in keep], dtype=float) for h in HORIZONS}
    mae = {h: np.array([r["break"][f"mae_{h}min"] for r in keep], dtype=float) for h in HORIZONS}

    lv = L[di, bi, :]                                   # (N, 7)
    dist = np.abs(lv - line[:, None])
    with np.errstate(invalid="ignore"):
        min_dist = np.nanmin(dist, axis=1)
    n_no_level = int(np.isnan(min_dist).sum())

    # G1 -- reproduce the published unconditional baseline. Computed over ALL raw break rows
    # with defined excursions, NOT over the joined subset: G1 asks "do break-dataset.jsonl and
    # break-dataset-summary.json agree with each other", which is a property of the source
    # files and must not be contaminated by this study's own date-coverage join.
    pub = json.loads(SUMMARY.read_text(encoding="utf-8"))["by_family_direction"]
    g1 = {}
    raw_by_fk: dict[str, list] = defaultdict(list)
    for r in raw:
        if _has_exc(r):
            raw_by_fk[f'{r["anchor_family"]}_{r["kind"]}'].append(r["break"])
    for fk, brs in sorted(raw_by_fk.items()):
        got = {}
        for h in HORIZONS:
            got[f"mean_mfe_{h}min"] = round(float(np.mean([b[f"mfe_{h}min"] for b in brs])), 4)
            got[f"mean_mae_{h}min"] = round(float(np.mean([b[f"mae_{h}min"] for b in brs])), 4)
        exp = {k: pub.get(fk, {}).get(k) for k in got}
        g1[fk] = {"n_with_excursions": len(brs), "reproduced": got, "published": exp,
                  "matches": all(exp[k] is None or abs(got[k] - exp[k]) <= 0.006 for k in got)}

    # cells
    cells = []
    for band in BANDS:
        at = (min_dist <= band) & ~np.isnan(min_dist)
        for fk in sorted(set(fam)):
            m = fam == fk
            a, b_ = m & at, m & ~at & ~np.isnan(min_dist)
            for h in HORIZONS:
                rec: dict[str, Any] = {
                    "cell": f"{fk}|band<={band:.2f}|H{h}", "family_kind": fk,
                    "band": band, "horizon_min": h,
                    "n_at": int(a.sum()), "n_not_at": int(b_.sum()),
                    "ratio_at": None, "ratio_not_at": None, "perm_p": None,
                }
                ra = ratio(mfe[h][a], mae[h][a]) if a.sum() else None
                rb = ratio(mfe[h][b_], mae[h][b_]) if b_.sum() else None
                if a.sum() < MIN_CELL_N or b_.sum() < MIN_CELL_N or ra is None or rb is None:
                    rec["verdict"] = "NOT-RUN"
                    rec["why"] = (f"n_at={int(a.sum())} n_not_at={int(b_.sum())} "
                                  f"floor={MIN_CELL_N} ratio_defined={ra is not None and rb is not None}")
                else:
                    rec["ratio_at"], rec["ratio_not_at"] = round(ra, 4), round(rb, 4)
                    rec["delta"] = round(ra - rb, 4)
                    rec["verdict"] = "MEASURED"
                cells.append(rec)

    # date-shuffle null (the prereg's own null): reassign each date's LEVEL VECTOR to another
    # date, keeping level count + intraday spacing intact. A "confluence" effect that survives
    # date-shuffling is a distance artifact, not confluence.
    rng = np.random.default_rng(20260814)
    measured = [c for c in cells if c["verdict"] == "MEASURED"]
    if measured:
        obs = {c["cell"]: c["delta"] for c in measured}
        hits = {k: 0 for k in obs}
        for _ in range(N_PERM):
            perm = rng.permutation(len(dates))
            lvp = L[perm[di], bi, :]
            with np.errstate(invalid="ignore"):
                mdp = np.nanmin(np.abs(lvp - line[:, None]), axis=1)
            for c in measured:
                band, fk, h = c["band"], c["family_kind"], c["horizon_min"]
                m = fam == fk
                atp = (mdp <= band) & ~np.isnan(mdp)
                a, b_ = m & atp, m & ~atp & ~np.isnan(mdp)
                if a.sum() < MIN_CELL_N or b_.sum() < MIN_CELL_N:
                    continue
                ra, rb = ratio(mfe[h][a], mae[h][a]), ratio(mfe[h][b_], mae[h][b_])
                if ra is not None and rb is not None and abs(ra - rb) >= abs(obs[c["cell"]]):
                    hits[c["cell"]] += 1
        for c in measured:
            c["perm_p"] = round((hits[c["cell"]] + 1) / (N_PERM + 1), 5)

    surv = bh_fdr([(c["cell"], c["perm_p"]) for c in measured], q=0.10)
    for c in cells:
        c["survives_bh_fdr_q10"] = surv.get(c["cell"], False)

    # TOO-GOOD TRIPWIRE (/fable-too-good, added after the NaN incident above). The prereg's
    # own declared expectation is NO effect. A near-total sweep is far more likely to be a
    # bug than a discovery, so it is flagged IN THE ARTIFACT rather than left for a reader to
    # notice -- the first run reported 72/72 at the p-floor and looked like a triumph.
    n_meas = len(measured)
    n_surv = sum(1 for c in cells if c["survives_bh_fdr_q10"])
    at_p_floor = sum(1 for c in measured if c["perm_p"] == round(1 / (N_PERM + 1), 5))
    too_good = {
        "surviving_fraction": round(n_surv / n_meas, 4) if n_meas else None,
        "cells_at_permutation_p_floor": at_p_floor,
        "TRIPPED": bool(n_meas and (n_surv / n_meas > 0.5 or at_p_floor > n_meas * 0.5)),
        "meaning": ("TRIPPED means treat every number in this file as an artifact until the "
                    "mechanism is explained. It does NOT mean a real effect is impossible."),
    }

    # G3 -- vary-and-assert: cohort size must move with band width
    g3 = {}
    for fk in sorted(set(fam)):
        sizes = [c["n_at"] for c in cells if c["family_kind"] == fk and c["horizon_min"] == 30]
        g3[fk] = {"n_at_by_band": sizes,
                  "monotonic_nondecreasing": all(x <= y for x, y in zip(sizes, sizes[1:])),
                  "binds": len(set(sizes)) > 1}

    import subprocess
    # CREATE_NO_WINDOW (OP-27/L41): a bare subprocess.run on win32 flashes a conhost window.
    # Added 2026-08-14 -- I introduced this call tonight WITHOUT the flag and
    # test_window_leak_compliance caught it. That guard exists because console popups were a
    # named, shouted-about defect; shipping a new one inside a research runner is exactly how
    # they come back.
    _NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                          capture_output=True, text=True,
                          creationflags=_NO_WINDOW).stdout.strip()
    rep = {
        "prereg_id": "TRENDLINE-BREAK-AT-LEVEL-2026-08-13",
        "runner": "backtest/autoresearch/trendline_break_at_level_2026_08_14.py",
        "produced_at_git_head": head,
        "honesty_clause": ("MFE/MAE is EXCURSION, not P&L -- no stop, target, theta or spread. "
                           "No cell here may be described as profitable (C3)."),
        "n_break_rows": len(raw), "n_joined": len(keep), "n_dropped_rows": dropped_rows,
        "n_dropped_no_forward_bars": n_null_exc,
        "n_rows_without_any_level": n_no_level,
        "TOO_GOOD_TRIPWIRE": too_good,
        "dates_resolved": len(anchors), "dates_dropped": unresolved[:20],
        "bands": BANDS, "horizons": HORIZONS, "n_permutations": N_PERM,
        "levels": LEVEL_NAMES,
        "G0_join_verified_against_close_at_break": True,
        "G1_baseline_reproduces": g1,
        "G3_patch_binds": g3,
        "cells": cells,
    }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"\njoined {len(keep):,} rows ({dropped_rows:,} dropped); "
          f"{n_no_level:,} had no derivable level")
    print("G1 baseline reproduces:", {k: v["matches"] for k, v in g1.items()})
    print("G3 binds:", {k: v["binds"] for k, v in g3.items()})
    if too_good["TRIPPED"]:
        print(f"  !! TOO-GOOD TRIPWIRE: {n_surv}/{n_meas} survive, "
              f"{at_p_floor} at the p-floor -- treat as artifact until explained")
    print(f"cells: {len(cells)} total, {n_meas} MEASURED, {len(cells) - n_meas} NOT-RUN, "
          f"{n_surv} survive BH-FDR q=0.10")
    for c in cells:
        if c["verdict"] != "MEASURED":
            continue
        star = "*" if c["survives_bh_fdr_q10"] else " "
        print(f"  [{star}] {c['cell']:<40} at={c['ratio_at']:<7} not_at={c['ratio_not_at']:<7} "
              f"delta={c['delta']:>8}  p={c['perm_p']}  (n {c['n_at']}/{c['n_not_at']})")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
