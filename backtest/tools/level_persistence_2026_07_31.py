"""level_persistence_2026_07_31.py -- LEVEL PERSISTENCE formalization (J's question 2026-07-31:
"did we draw 20 different levels or validate the same ones?" + his thesis that a level
yesterday's tape rode/flipped/bounced holds MORE weight today).

Outputs: analysis/deep-research/LEVEL-PERSISTENCE-2026-07-31.{md,json}
Guard:   backtest/tests/test_level_persistence_2026_07_31.py (matcher + touch-counter logic)

================================ PRE-REGISTRATION (FROZEN) ================================
Frozen 2026-07-31 16:43:52 ET (et_clock.py, market closed) BEFORE any classification ran.
Written in-session by the level-persistence lane; no cell result was seen before this block
was committed to disk. All cells reported, no cherry-picking.

HYPOTHESES
  H1 (continuity, DESCRIPTIVE -- no gate): a substantial fraction of each v2-compiler
      morning level set (2026-07-28..07-31, n=20/day) resolves to the same zone as a prior
      day's level. Deliverable = the persistence map, not a pass/fail.
  H2 (persistence predicts, PRIMARY): in the 390-day full-history replay population
      (engine-fullhist-replay-2026-07-23.json, 190 real-OPRA trades, 66 level-tied with
      trigger_level != null), trades on PERSISTENT levels outperform trades on FRESH
      levels, and TOUCH-VALIDATED outperform FRESH, on per-trade $ P&L.
      DESCRIPTIVE slicing of EXISTING per-trade records -- no new variants, no engine rerun.

DEFINITIONS (replay side, OHLC-derived -- provenance gap disclosed below)
  Per-day level set S_eod(D) = lib.levels._detect_from_history(all bars <= D 16:00 ET, D)
      .active -- the SAME derivation the replay's entry layer uses, taken at end-of-day D
      (fullest version of day D's set). Round-number levels (price == int(price)) are
      EXCLUDED from prior-day match sets (they are position-relative and recur trivially).
  Match: level L matches prior level P iff |L - P| <= tol.
  FRESH: trade's trigger_level L has NO match in S_eod(D_prev) for any of the `lookback`
      trading days D_prev before the trade date (>=1 prior in-window trading day required,
      else UNKNOWN and excluded, disclosed).
  PERSISTENT: >=1 matched prior day within lookback.
  TOUCH-VALIDATED: PERSISTENT and total touch-interactions >= 2, where interactions =
      count of RTH (09:30-16:00 ET) 5m bars on MATCHED prior days (within lookback) whose
      [low, high] intersects [L - tol, L + tol].
  PRIMARY CELL (frozen): tol = $0.40, lookback = 5 trading days.
  SENSITIVITY GRID (all cells reported): tol in {0.25, 0.40, 0.60} x lookback in {1, 5, 10}.

STATS / MULTIPLICITY
  Per cohort per cell: n, total $, $/trade, WR, drop-best, drop-worst.
  Contrasts per cell: (a) PERSISTENT-or-better vs FRESH, (b) TOUCH-VALIDATED vs FRESH --
      Mann-Whitney U two-sided on per-trade $ P&L. 9 cells x 2 contrasts = 18 p-values,
      Benjamini-Hochberg FDR q = 0.10 across ALL 18. Primary decision reads ONLY the
      primary cell; sensitivity cells are stability context.
  Verdict rule (frozen): "touch-validated levels measurably outperform" requires, in the
      PRIMARY cell: TV $/trade > FRESH $/trade AND TV total > 0 AND contrast (b) BH-significant.
      If TV outperforms directionally but is not BH-significant -> DESCRIPTIVE (spec still
      written per lane step 3, labeled evidence-thin, A/B pre-reg required before any arming).

PART 1 / PART 4 (live v2 snapshots, DESCRIPTIVE)
  Snapshot days available since v2 compiler (7b4aa3f4, shipped 2026-07-27 evening):
      07-28 0930, 07-29 0946, 07-31 0930 (+ 07-31 1550 EOD). 07-30 snapshot MISSING
      (no history dir, file untracked per C34) -- DISCLOSED; 07-31 persistence is matched
      against the 07-29 morning set; 07-30 TAPE (bars) is still used for touch-validation.
  Snapshot match tol: max(zone_width_a, zone_width_b, 0.40) where zone_width is the file's
      half-width field when present (shelves 0.80, intraday ~0.37).
  Touch-validation of a 07-31 level: >=2 RTH 5m bars on 2026-07-30 intersecting
      [price - max(zw, 0.40), price + max(zw, 0.40)] (live cache bars, SIP-appended feed).

DATA + PROVENANCE GAP (OP-20 disclosure)
  Replay levels are OHLC-derived approximations (backtest/lib/levels.py: Globex H/L,
      PMH/PML, premarket rejection buckets, PDH/PDL/PDC, POC, 5-day H/L, session H/L,
      opens, prior week/month closes, aVWAPs, round numbers) -- NOT the curated live
      key-levels.json feed and NOT the v2 shelf compiler. Cohort CONTRASTS are the signal.
      aVWAP levels are dynamic (recomputed daily); a today-vs-yesterday aVWAP match within
      tol counts as persistence of the same dynamic construct -- disclosed limitation.
  Bars: backtest/data/spy_5m_2025-01-01_2026-07-22.csv (replay window; the exact file the
      replay used) + backtest/data/spy_5m_2026-05-19_2026-07-31.csv (live cache, for
      2026-07-30 tape; feed patchwork disclosed in DATA-PROVENANCE.md, appends are SIP).
  P&L: per-trade dollar_pnl from the replay JSON -- real-OPRA-only by construction
      (n_excluded_no_opra_cache=16 already excluded upstream; nothing synthetic here).
==========================================================================================

Run: backtest/.venv/Scripts/python.exe backtest/tools/level_persistence_2026_07_31.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
for _p in (str(ROOT), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.levels import _detect_from_history  # noqa: E402

SPY_FULLHIST = REPO / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
SPY_LIVE = REPO / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
REPLAY_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
HIST_DIR = ROOT / "automation" / "state" / "key-levels-history"
OUT_JSON = ROOT / "analysis" / "deep-research" / "LEVEL-PERSISTENCE-2026-07-31.json"
OUT_MD = ROOT / "analysis" / "deep-research" / "LEVEL-PERSISTENCE-2026-07-31.md"

# ---- frozen prereg constants (see module docstring) ----
PRIMARY_TOL = 0.40
PRIMARY_LOOKBACK = 5
TOL_GRID = (0.25, 0.40, 0.60)
LOOKBACK_GRID = (1, 5, 10)
TOUCH_MIN = 2
BH_Q = 0.10
SNAPSHOT_DEFAULT_TOL = 0.40
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)

# J's called prices today (2026-07-31) -- annotated in the Part 4 table.
J_CALLS = {737.68: "today's exact low (called live)",
           739.72: "bounce target (called live)",
           742.97: "premarket low call"}


# ============================== core matching logic (guarded) ==============================

def zone_match(price_a: float, price_b: float, tol: float) -> bool:
    """True iff two level prices resolve to the same zone: |a - b| <= tol (inclusive)."""
    return abs(float(price_a) - float(price_b)) <= float(tol)


def match_against_set(price: float, level_set: list[float], tol: float) -> bool:
    """True iff `price` matches ANY level in `level_set` within tol."""
    return any(zone_match(price, p, tol) for p in level_set)


def count_zone_touches(bars: pd.DataFrame, price: float, tol: float) -> int:
    """Count RTH 5m bars whose [low, high] range intersects [price - tol, price + tol].

    `bars` must have columns low, high and a `time` column of datetime.time (ET).
    Only bars with RTH_START <= time < RTH_END are counted.
    """
    if bars.empty:
        return 0
    rth = bars[(bars["time"] >= RTH_START) & (bars["time"] < RTH_END)]
    if rth.empty:
        return 0
    lo, hi = float(price) - float(tol), float(price) + float(tol)
    hit = (rth["low"] <= hi) & (rth["high"] >= lo)
    return int(hit.sum())


def classify_level(trigger_level: float,
                   prior_day_sets: list[list[float]],
                   prior_day_bars: list[pd.DataFrame],
                   tol: float,
                   touch_min: int = TOUCH_MIN) -> tuple[str, int, int]:
    """Classify one trade's trigger level.

    prior_day_sets / prior_day_bars: aligned lists, most-recent-first or any order,
    ALREADY restricted to the lookback window (round numbers already excluded from sets).

    Returns (cohort, n_matched_prior_days, total_touches_on_matched_days) where cohort in
    {"UNKNOWN", "FRESH", "PERSISTENT", "TOUCH_VALIDATED"}.
    """
    if not prior_day_sets:
        return ("UNKNOWN", 0, 0)
    matched_idx = [i for i, s in enumerate(prior_day_sets)
                   if match_against_set(trigger_level, s, tol)]
    if not matched_idx:
        return ("FRESH", 0, 0)
    touches = sum(count_zone_touches(prior_day_bars[i], trigger_level, tol)
                  for i in matched_idx)
    if touches >= touch_min:
        return ("TOUCH_VALIDATED", len(matched_idx), touches)
    return ("PERSISTENT", len(matched_idx), touches)


def strip_round_numbers(levels: list[float]) -> list[float]:
    """Drop exact-integer levels (the derivation's psychological round numbers)."""
    return [p for p in levels if float(p) != float(int(p))]


# ============================== stats helpers ==============================

def mannwhitney_p(xs: list[float], ys: list[float]) -> float:
    """Two-sided Mann-Whitney U via normal approximation with tie correction.

    Self-contained (no scipy dependency in the backtest venv guarantee)."""
    import math
    n1, n2 = len(xs), len(ys)
    if n1 == 0 or n2 == 0:
        return float("nan")
    allv = [(v, 0) for v in xs] + [(v, 1) for v in ys]
    allv.sort(key=lambda t: t[0])
    # midranks
    ranks = [0.0] * len(allv)
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = mid
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    # tie correction
    tie_counts = Counter(v for v, _ in allv)
    n = n1 + n2
    tie_term = sum(t ** 3 - t for t in tie_counts.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1))) if n > 1 else 0.0
    if var <= 0:
        return 1.0
    z = (u1 - mu) / math.sqrt(var)
    # two-sided normal
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return min(1.0, p)


def bh_flags(pvals: list[float], q: float = BH_Q) -> list[bool]:
    """Benjamini-Hochberg: True where the hypothesis is rejected at FDR q. NaNs -> False."""
    import math
    idx = [i for i, p in enumerate(pvals) if not (p is None or (isinstance(p, float) and math.isnan(p)))]
    m = len(idx)
    flags = [False] * len(pvals)
    if m == 0:
        return flags
    order = sorted(idx, key=lambda i: pvals[i])
    thresh_rank = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            thresh_rank = rank
    for rank, i in enumerate(order, start=1):
        if rank <= thresh_rank:
            flags[i] = True
    return flags


def cohort_stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "total": 0.0, "per_trade": None, "wr": None,
                "drop_best": None, "drop_worst": None}
    pnls = [r["dollar_pnl"] for r in rows]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    return {"n": n,
            "total": round(total, 2),
            "per_trade": round(total / n, 2),
            "wr": round(wins / n, 4),
            "drop_best": round(total - max(pnls), 2),
            "drop_worst": round(total - min(pnls), 2)}


# ============================== data loading ==============================

def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = "timestamp_et" if "timestamp_et" in df.columns else "timestamp"
    ts = pd.to_datetime(df[tcol], utc=True).dt.tz_convert("America/New_York")
    df = df.copy()
    df["timestamp_et"] = ts
    df["date"] = ts.dt.date
    df["time"] = ts.dt.time
    return df


def build_eod_level_sets(spy: pd.DataFrame) -> dict:
    """S_eod(D) for every trading day D: production _detect_from_history at day close,
    round numbers stripped for match purposes (kept count disclosed)."""
    days = sorted(spy["date"].unique())
    out = {}
    for d in days:
        hist = spy[spy["date"] <= d]
        ls = _detect_from_history(hist, d)
        out[d] = strip_round_numbers(ls.active)
    return out


# ============================== Part 2: replay classification ==============================

def classify_replay(trades: list[dict], spy: pd.DataFrame) -> dict:
    eod_sets = build_eod_level_sets(spy)
    trading_days = sorted(eod_sets.keys())
    day_pos = {d: i for i, d in enumerate(trading_days)}
    bars_by_day = {d: g for d, g in spy.groupby("date")}

    level_trades = [t for t in trades if t.get("trigger_level") is not None]
    grid = {}
    per_trade_primary = []
    for tol in TOL_GRID:
        for lb in LOOKBACK_GRID:
            cohorts = {"FRESH": [], "PERSISTENT": [], "TOUCH_VALIDATED": [], "UNKNOWN": []}
            for t in level_trades:
                d = dt.date.fromisoformat(t["date"])
                pos = day_pos.get(d)
                if pos is None or pos == 0:
                    cohorts["UNKNOWN"].append(t)
                    continue
                prior_days = trading_days[max(0, pos - lb):pos]
                sets_ = [eod_sets[pd_] for pd_ in prior_days]
                bars_ = [bars_by_day[pd_] for pd_ in prior_days]
                cohort, nmatch, touches = classify_level(
                    t["trigger_level"], sets_, bars_, tol)
                cohorts[cohort].append(t)
                if tol == PRIMARY_TOL and lb == PRIMARY_LOOKBACK:
                    per_trade_primary.append({
                        "date": t["date"], "entry": t["entry_time_et"][11:16],
                        "tier": t["tier"], "side": t["side"],
                        "triggers": t["triggers"],
                        "trigger_level": t["trigger_level"],
                        "cohort": cohort, "matched_prior_days": nmatch,
                        "touches": touches, "dollar_pnl": t["dollar_pnl"]})
            fresh_pnl = [x["dollar_pnl"] for x in cohorts["FRESH"]]
            pers_plus = [x["dollar_pnl"] for x in cohorts["PERSISTENT"] + cohorts["TOUCH_VALIDATED"]]
            tv_pnl = [x["dollar_pnl"] for x in cohorts["TOUCH_VALIDATED"]]
            grid[f"tol{tol}_lb{lb}"] = {
                "tol": tol, "lookback": lb,
                "cohorts": {k: cohort_stats(v) for k, v in cohorts.items()},
                "p_persistent_vs_fresh": mannwhitney_p(pers_plus, fresh_pnl),
                "p_touchvalidated_vs_fresh": mannwhitney_p(tv_pnl, fresh_pnl),
            }
    # BH across all 18 reported p-values (frozen policy)
    keys = sorted(grid.keys())
    plist, ptags = [], []
    for k in keys:
        plist.append(grid[k]["p_persistent_vs_fresh"]); ptags.append((k, "persistent_vs_fresh"))
        plist.append(grid[k]["p_touchvalidated_vs_fresh"]); ptags.append((k, "touchvalidated_vs_fresh"))
    flags = bh_flags(plist, BH_Q)
    for (k, tag), fl in zip(ptags, flags):
        grid[k][f"bh_sig_{tag}"] = bool(fl)
    return {"grid": grid, "per_trade_primary": per_trade_primary,
            "n_level_tied": len(level_trades)}


# ============================== Part 1 + 4: live snapshot continuity ==============================

SNAP_FILES = [("2026-07-28", "0930.json"),
              ("2026-07-29", "0946.json"),
              ("2026-07-31", "0930.json")]


def load_snapshot(day: str, fname: str) -> list[dict]:
    d = json.load(open(HIST_DIR / day / fname, encoding="utf-8"))
    return d["levels"]


def snap_tol(a: dict, b: dict | None = None) -> float:
    zw_a = a.get("zone_width") or 0.0
    zw_b = (b or {}).get("zone_width") or 0.0
    return max(float(zw_a), float(zw_b), SNAPSHOT_DEFAULT_TOL)


def continuity_map() -> dict:
    snaps = {day: load_snapshot(day, f) for day, f in SNAP_FILES}
    days = [d for d, _ in SNAP_FILES]
    out = {"days": days, "missing_snapshot_days": ["2026-07-30"], "per_day": {}}
    for i, day in enumerate(days):
        levels = snaps[day]
        rec = {"n": len(levels), "levels": []}
        prior_day = days[i - 1] if i > 0 else None
        for L in levels:
            entry = {"price": L["price"], "label": L.get("label"),
                     "source": L.get("source"), "weight": L.get("weight"),
                     "zone_width": L.get("zone_width")}
            if prior_day:
                matches = [P for P in snaps[prior_day]
                           if zone_match(L["price"], P["price"], snap_tol(L, P))]
                entry["persisted_from"] = prior_day if matches else None
                entry["matched_labels"] = [m.get("label") for m in matches][:3]
            rec["levels"].append(entry)
        if prior_day:
            n_pers = sum(1 for e in rec["levels"] if e.get("persisted_from"))
            rec["n_persisted_from_prior_snapshot"] = n_pers
            rec["n_new"] = rec["n"] - n_pers
        out["per_day"][day] = rec
    # 3-day chains: 07-31 levels that match 07-29 AND (via 07-29 partner) 07-28
    chains = 0
    for e in out["per_day"]["2026-07-31"]["levels"]:
        if not e.get("persisted_from"):
            continue
        l29 = [P for P in snaps["2026-07-29"]
               if zone_match(e["price"], P["price"], snap_tol(e, P))]
        if any(any(zone_match(P["price"], Q["price"], snap_tol(P, Q))
                   for Q in snaps["2026-07-28"]) for P in l29):
            chains += 1
    out["n_full_chain_0728_to_0731"] = chains
    return out


def today_table(live_bars: pd.DataFrame) -> dict:
    """Part 4: J's literal question for 2026-07-31's morning 20."""
    snaps = {day: load_snapshot(day, f) for day, f in SNAP_FILES}
    today = snaps["2026-07-31"]
    d0730 = dt.date(2026, 7, 30)
    bars_0730 = live_bars[live_bars["date"] == d0730]
    rows = []
    for L in today:
        tol = snap_tol(L)
        matches29 = [P for P in snaps["2026-07-29"]
                     if zone_match(L["price"], P["price"], snap_tol(L, P))]
        touches = count_zone_touches(bars_0730, L["price"], tol)
        if matches29 and touches >= TOUCH_MIN:
            klass = "TOUCH_VALIDATED"
        elif matches29:
            klass = "PERSISTED"
        else:
            klass = "NEW"
        j_note = ""
        for jp, note in J_CALLS.items():
            if zone_match(L["price"], jp, tol):
                j_note = f"J called {jp} -- {note}"
        rows.append({"price": L["price"], "label": L.get("label"),
                     "source": L.get("source"), "weight": L.get("weight"),
                     "class": klass,
                     "matched_0729": [m.get("label") for m in matches29][:2],
                     "touches_0730_tape": touches,
                     "j_call": j_note})
    counts = Counter(r["class"] for r in rows)
    return {"n": len(rows), "counts": dict(counts), "rows": rows,
            "note": ("PERSISTED matched vs the 07-29 morning snapshot (07-30 snapshot "
                     "missing, disclosed); touch-validation uses the 07-30 SIP tape.")}


# ============================== report ==============================

def main() -> None:
    print("Loading replay ...")
    replay = json.load(open(REPLAY_JSON, encoding="utf-8"))
    trades = replay["trades"]
    print("Loading bars ...")
    spy = load_bars(SPY_FULLHIST)
    live = load_bars(SPY_LIVE)

    print("Part 1: continuity map ...")
    part1 = continuity_map()
    print("Part 4: today's table ...")
    part4 = today_table(live)
    print("Part 2: replay classification (9 cells) ...")
    part2 = classify_replay(trades, spy)

    primary = part2["grid"][f"tol{PRIMARY_TOL}_lb{PRIMARY_LOOKBACK}"]
    c = primary["cohorts"]
    tv, fresh = c["TOUCH_VALIDATED"], c["FRESH"]
    tv_outperforms = (tv["n"] > 0 and fresh["n"] > 0
                      and tv["per_trade"] is not None and fresh["per_trade"] is not None
                      and tv["per_trade"] > fresh["per_trade"] and tv["total"] > 0)
    bh_sig = primary.get("bh_sig_touchvalidated_vs_fresh", False)
    if tv_outperforms and bh_sig:
        verdict = "TV_OUTPERFORMS_BH_SIGNIFICANT"
    elif tv_outperforms:
        verdict = "TV_OUTPERFORMS_DESCRIPTIVE_ONLY"
    else:
        verdict = "TV_DOES_NOT_OUTPERFORM"

    out = {
        "_doc": "Level persistence formalization. Prereg frozen 2026-07-31 16:43:52 ET in "
                "backtest/tools/level_persistence_2026_07_31.py module docstring BEFORE any run.",
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": {"primary_tol": PRIMARY_TOL, "primary_lookback": PRIMARY_LOOKBACK,
                   "touch_min": TOUCH_MIN, "tol_grid": list(TOL_GRID),
                   "lookback_grid": list(LOOKBACK_GRID), "bh_q": BH_Q,
                   "frozen_at_et": "2026-07-31 16:43:52"},
        "verdict": verdict,
        "part1_continuity": part1,
        "part2_replay": part2,
        "part4_today": part4,
        "provenance": {
            "replay_source": str(REPLAY_JSON.name),
            "replay_levels": "OHLC-derived (lib/levels.py), NOT the live v2 compiler feed",
            "bars_fullhist": SPY_FULLHIST.name,
            "bars_live": SPY_LIVE.name,
            "missing_snapshot_days": ["2026-07-30"],
            "pnl": "real-OPRA-only per-trade dollar_pnl from the replay JSON",
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    write_md(out)
    print(f"Wrote {OUT_MD}")
    print("VERDICT:", verdict)


def write_md(out: dict) -> None:
    L = []
    L.append("# LEVEL PERSISTENCE -- did we draw 20 different levels, or validate the same ones?")
    L.append("")
    L.append(f"Generated {out['generated_at']}. Tool: `backtest/tools/level_persistence_2026_07_31.py` "
             f"(prereg frozen {out['prereg']['frozen_at_et']} ET in its docstring, BEFORE any run). "
             f"Machine-readable: `analysis/deep-research/LEVEL-PERSISTENCE-2026-07-31.json`.")
    L.append("")
    L.append(f"## Verdict: **{out['verdict']}**")
    L.append("")

    # Part 1
    p1 = out["part1_continuity"]
    L.append("## Part 1 -- v2 snapshot continuity (2026-07-28..07-31; 07-30 snapshot MISSING, disclosed)")
    L.append("")
    L.append("| Day | n levels | persisted from prior snapshot | new |")
    L.append("|---|--:|--:|--:|")
    for day in p1["days"]:
        r = p1["per_day"][day]
        pers = r.get("n_persisted_from_prior_snapshot", "--")
        new = r.get("n_new", "--")
        L.append(f"| {day} | {r['n']} | {pers} | {new} |")
    L.append("")
    L.append(f"Full 07-28 -> 07-29 -> 07-31 chains: **{p1['n_full_chain_0728_to_0731']}** of "
             f"{p1['per_day']['2026-07-31']['n']} today-levels.")
    L.append("")

    # Part 2
    p2 = out["part2_replay"]
    prim = p2["grid"][f"tol{PRIMARY_TOL}_lb{PRIMARY_LOOKBACK}"]
    L.append(f"## Part 2 -- does persistence predict? ({p2['n_level_tied']} level-tied real-OPRA "
             f"replay trades; OHLC-derived levels, provenance gap disclosed)")
    L.append("")
    L.append(f"### PRIMARY CELL (frozen): tol ${PRIMARY_TOL}, lookback {PRIMARY_LOOKBACK} trading days")
    L.append("")
    L.append("| Cohort | n | Total | $/trade | WR | drop-best | drop-worst |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for k in ("FRESH", "PERSISTENT", "TOUCH_VALIDATED", "UNKNOWN"):
        s = prim["cohorts"][k]
        if s["n"] == 0:
            L.append(f"| {k} | 0 | -- | -- | -- | -- | -- |")
        else:
            L.append(f"| {k} | {s['n']} | ${s['total']:+,.2f} | ${s['per_trade']:+,.2f} | "
                     f"{s['wr']:.2f} | ${s['drop_best']:+,.2f} | ${s['drop_worst']:+,.2f} |")
    L.append("")
    L.append(f"- p (PERSISTENT-or-better vs FRESH) = {prim['p_persistent_vs_fresh']:.4f} "
             f"(BH-sig at q={BH_Q}: {prim.get('bh_sig_persistent_vs_fresh')})")
    L.append(f"- p (TOUCH_VALIDATED vs FRESH) = {prim['p_touchvalidated_vs_fresh']:.4f} "
             f"(BH-sig at q={BH_Q}: {prim.get('bh_sig_touchvalidated_vs_fresh')})")
    L.append("")
    L.append("### All 9 sensitivity cells (frozen grid, ALL reported)")
    L.append("")
    L.append("| Cell | FRESH n/$-tot/$-tr | PERSISTENT n/$-tot/$-tr | TOUCH_VAL n/$-tot/$-tr | p(TV vs F) | BH |")
    L.append("|---|---|---|---|--:|:--:|")
    for k in sorted(p2["grid"].keys()):
        g = p2["grid"][k]
        def _fmt(s):
            if s["n"] == 0:
                return "0 / -- / --"
            return f"{s['n']} / ${s['total']:+,.0f} / ${s['per_trade']:+,.0f}"
        L.append(f"| {k} | {_fmt(g['cohorts']['FRESH'])} | {_fmt(g['cohorts']['PERSISTENT'])} | "
                 f"{_fmt(g['cohorts']['TOUCH_VALIDATED'])} | {g['p_touchvalidated_vs_fresh']:.3f} | "
                 f"{'Y' if g.get('bh_sig_touchvalidated_vs_fresh') else 'n'} |")
    L.append("")

    # Primary-cell per-trade table
    L.append("<details><summary>Primary-cell per-trade classification (66 rows)</summary>")
    L.append("")
    L.append("| Date | Entry | Tier | Side | Level | Cohort | prior-day matches | touches | P&L |")
    L.append("|---|---|---|---|--:|---|--:|--:|--:|")
    for r in out["part2_replay"]["per_trade_primary"]:
        L.append(f"| {r['date']} | {r['entry']} | {r['tier']} | {r['side']} | {r['trigger_level']} | "
                 f"{r['cohort']} | {r['matched_prior_days']} | {r['touches']} | ${r['dollar_pnl']:+,.2f} |")
    L.append("")
    L.append("</details>")
    L.append("")

    # Part 4
    p4 = out["part4_today"]
    L.append(f"## Part 4 -- J's literal question: today's {p4['n']} morning levels")
    L.append("")
    L.append(f"Counts: {p4['counts']}. {p4['note']}")
    L.append("")
    L.append("| Price | Label | Class | matched 07-29 | touches on 07-30 tape | J call |")
    L.append("|--:|---|---|---|--:|---|")
    for r in p4["rows"]:
        m = ", ".join(x for x in r["matched_0729"] if x) or "--"
        L.append(f"| {r['price']} | {r['label']} | **{r['class']}** | {m} | "
                 f"{r['touches_0730_tape']} | {r['j_call']} |")
    L.append("")
    L.append("## Provenance / disclosures")
    L.append("")
    for k, v in out["provenance"].items():
        L.append(f"- **{k}**: {v}")
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
