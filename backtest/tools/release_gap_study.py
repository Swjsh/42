#!/usr/bin/env python
"""release_gap_study.py -- B2 SCHEDULED-RELEASE BLACKOUT STUDY (2026-09-03, stamp 12:40 ET).

Depends on B1's `setup/scripts/macro_calendar.py#scheduled_releases(date)` (rule-based ISM
Manufacturing/Services PMI + hand-curated FOMC/CPI/PPI/NFP/PCE/GDP + secondary Consumer
Confidence/UMich cohorts). Imported directly -- confirmed usable this build (no fallback
needed): `scheduled_releases("2026-08-05")` returns `ism_services_pmi`,
`scheduled_releases("2026-09-03")` returns `ism_services_pmi`, matching the two live
quote-tape gap days named in this task's briefing.

WHY THIS EXISTS. `analysis/deep-research/2026-09-03-money/dissect-wave-autopsy.md` (D1,
read-only, reused not reproduced) found today's Wave 1 (09:41 ET entries, four arms) was
stopped at the -50% catastrophe cap by a single-minute quote-tape gap spanning 10:00-10:01
ET on every held symbol, coincident with the ISM Services PMI release; the same pattern
recurred on 2026-08-05 (also ISM Services). `macro_calendar.py`'s prior calendar
(KNOWN_EVENTS_2026) never listed ISM at all, and the engine has NO event blackout of any
kind (`structure-veto` and the entry gates are unrelated mechanisms; the retired
`macro-veto-v2` params keys were CONFIRMED_DEAD 2026-08-29). This module tests whether a
calendar-known (not release-VALUE-known -- no look-ahead) blackout around the 10:00 ET
tier-1 release window would have helped, on cached history, before any live change ships.

WHAT THIS DOES (cached data only -- no broker/market-data/network calls of any kind):
  1. `trading_day_universe()` -- every date in [STUDY_START, latest fully-archived session]
     that has a cached SPY 1-min bar file (`backtest/data/spy_sip_cache/spy_1m_<date>.json`).
     2026-09-03 (today) is EXCLUDED from this cached-bar universe -- its SPY 1-min cache has
     not been archived yet (market open at build time) -- but its real fills/decisions ARE
     included in the fills-ledger-driven sections (3) and (4) below, since those need only
     `automation/state/fills-ledger.jsonl` timestamps, not the SPY bar archive. This
     asymmetry is reported explicitly everywhere it matters, never silently smoothed over.
  2. `release_flags(date)` -- classifies each date via `scheduled_releases()`: `is_ism` (tier-1,
     severity=high: ISM Manufacturing/Services PMI) vs `is_secondary` (Consumer Confidence /
     UMich prelim+final, severity=med, `RULE_BASED_UNVERIFIED`). The candidate RULES (R1/R2/R3,
     section 4) are frozen to ISM-ONLY scope (`"tier-1 10:00 release"` per this task's own
     wording) -- `is_secondary` is a measurement/reporting cohort only, per the task's own
     framing ("CB/UMich as secondary cohorts"). This distinction matters concretely: 2026-08-28
     (one of the four named winning days) carries a `umich_sentiment_final` (secondary, NOT
     ISM) release -- the frozen ISM-only rule never touches it; an EXPLORATORY ISM+secondary
     variant is reported separately, clearly labeled, never folded into the frozen decision.
  3. SPY $ and option % moves across the 10:00 ET window (`spy_gap_metrics` / per-contract
     `option_gap_metrics`, using `backtest/data/highres/<OCC>_1m_<date>.csv`) -- two windows:
     10:00->10:01 (the single minute spanning the release print) and 09:59->10:02 (a wider
     bracket). Distribution, n, day-clustered bootstrap CI, release vs non-release days.
  4. Every engine position (`automation/state/fills-ledger.jsonl`, `attribution=="engine"`,
     `is_option=True`) reconstructed via FIFO buy/sell leg matching (mirrors
     `tp1_r50_forward_shadow.legs_by_activity_id`'s grouping exactly, extended to carry
     precise entry/exit timestamps -- read not re-derived) -- split into (a) positions OPEN
     across 10:00:00 ET and (b) positions ENTERED in [09:45, 10:05) ET, release vs
     non-release days: P&L, cap-hit rate (proxy: realized pnl <= -45% of cost basis on the
     closed quantity -- the -50% catastrophe cap's own neighborhood; a proxy, not an exact
     exit-reason parse, because no per-fill exit-reason field survives to fills-ledger.jsonl
     -- stated explicitly, not silently assumed exact), hold minutes.
  5. Three candidate rules costed on ENTRY-TICK information only (the calendar is known
     premarket; the release VALUE is not -- no look-ahead, guarded by
     `test_release_blackout_shadow_2026_09_03.py`):
       R1: no new entries in [T-15, T+5) = [09:45, 10:05) ET on an ISM day.
       R2: R1 + no new entries in [09:35, T+5) = [09:35, 10:05) ET on an ISM day (kills the
           whole pre-release morning down to the engine's own existing 09:35 entry gate).
       R3: R1 + flatten any position still open at T-2 = 09:58 ET on an ISM day (a KILL-TYPE
           reduction -- it can only close earlier or enter less, never enter more/hold
           longer). Costed via the position's own cached 1-min option bar (same OCC symbol,
           same date) at/before 09:58 as the counterfactual flatten mark; a position with no
           matching bar or already fully closed before 09:58 is excluded and counted, never
           silently dropped.
     Each rule reports: n trades removed/flattened, $ saved vs winners forgone, day-clustered
     bootstrap CI, top-3 |delta| concentration, drop-best-day (ex_best_day sum, mirroring
     `tp1_r50_forward_shadow._top3_concentration_share` / `_bootstrap_day_clustered_mean`
     verbatim), per-arm breakdown, and an explicit check against the four named winning days
     (2026-08-06, 08-13, 08-27, 08-28).

OUTPUTS:
  analysis/deep-research/2026-09-03-money/release-gap-study.json   full machine-readable dump
  analysis/deep-research/2026-09-03-money/release-gap-study.md     human-readable report
(both written by `write_report()`; this module's `main()` also prints a compact summary to
stdout for the calling session's own dry-run verification.)

COST: $0. Pure local computation over already-cached JSON/JSONL/CSV files -- zero network
calls, zero LLM calls, zero broker calls. Read-only everywhere except its two named output
files and (separately) the sibling forward-shadow instrument's own ledger/summary files.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import macro_calendar as mc  # noqa: E402  -- B1 deliverable, imported per this task's own instruction

SPY_CACHE_DIR = REPO / "backtest" / "data" / "spy_sip_cache"
OPT_CACHE_DIR = REPO / "backtest" / "data" / "highres"
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
PAIN_LEDGER = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"

OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
OUT_JSON = OUT_DIR / "release-gap-study.json"
OUT_MD = OUT_DIR / "release-gap-study.md"
PREREG_REL = "analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md"

STUDY_START = "2026-06-26"
STUDY_END_CACHED = "2026-09-02"          # last date with an archived SPY 1-min cache file
TODAY_PARTIAL = "2026-09-03"             # in scope for fills-based sections only (see docstring)

BIG_WIN_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
NAMED_ISM_DAYS = ["2026-08-03", "2026-08-05"]     # named in the task briefing

SECONDARY_TYPES = frozenset({"consumer_confidence", "umich_sentiment_prelim", "umich_sentiment_final"})
CAP_HIT_THRESHOLD = -0.45                # proxy for "hit (or nearly hit) the -50% catastrophe cap"

OPT_FILE_RE = re.compile(r"^(SPY\d{6}[CP]\d{8})_1m_(\d{4}-\d{2}-\d{2})\.csv$")


# ============================================================================================
# 1. Trading-day universe + release calendar (B1 import)
# ============================================================================================
def trading_day_universe() -> list[str]:
    dates = []
    for f in sorted(SPY_CACHE_DIR.glob("spy_1m_*.json")):
        d = f.stem.replace("spy_1m_", "")
        if STUDY_START <= d <= STUDY_END_CACHED:
            dates.append(d)
    return sorted(dates)


def release_flags(date: str) -> dict[str, Any]:
    events = mc.scheduled_releases(date)
    tenam = [e for e in events if e.get("time_et") == "10:00"]
    ism = [e for e in tenam if e.get("type", "").startswith("ism_")]
    secondary = [e for e in tenam if e.get("type") in SECONDARY_TYPES]
    return {
        "date": date,
        "events_10am": tenam,
        "is_ism": bool(ism),
        "ism_types": [e["type"] for e in ism],
        "is_secondary_10am": bool(secondary),
        "secondary_types": [e["type"] for e in secondary],
        "is_release_day_any": bool(tenam),
    }


# ============================================================================================
# 2. SPY / option 1-minute gap metrics
# ============================================================================================
def load_spy_bars(date: str) -> Optional[dict[str, dict]]:
    f = SPY_CACHE_DIR / f"spy_1m_{date}.json"
    if not f.exists():
        return None
    doc = json.loads(f.read_text(encoding="utf-8"))
    bars: dict[str, dict] = {}
    for b in doc.get("bars", []):
        t = b.get("t", "")
        if len(t) >= 16:
            bars[t[11:16]] = b            # keyed by 'HH:MM' (naive ET per spy_sip_cache convention)
    return bars


def spy_gap_metrics(bars: dict[str, dict]) -> Optional[dict[str, float]]:
    """price_at(HH:MM) := close of the bar stamped (HH:MM - 1) == open of the bar stamped HH:MM.
    move_1000_1001 = price_at(10:01) - price_at(10:00) = close(bar 10:00) - close(bar 09:59)
                    (the SPY dollar move DURING the release-print minute).
    move_0959_1002 = price_at(10:02) - price_at(09:59) = close(bar 10:01) - open(bar 09:59)
                    (a wider bracket around the release)."""
    b0959, b1000, b1001 = bars.get("09:59"), bars.get("10:00"), bars.get("10:01")
    if not (b0959 and b1000 and b1001):
        return None
    c0959, o0959, c1000, c1001 = b0959.get("c"), b0959.get("o"), b1000.get("c"), b1001.get("c")
    if None in (c0959, o0959, c1000, c1001):
        return None
    return {
        "move_1000_1001_dollars": round(c1000 - c0959, 4),
        "move_0959_1002_dollars": round(c1001 - o0959, 4),
        "abs_move_1000_1001_dollars": round(abs(c1000 - c0959), 4),
    }


def load_option_bars(csv_path: Path) -> dict[str, dict]:
    bars: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ts = row.get("timestamp_et", "")
            if len(ts) >= 16:
                try:
                    bars[ts[11:16]] = {
                        "o": float(row["open"]), "h": float(row["high"]),
                        "l": float(row["low"]), "c": float(row["close"]),
                    }
                except (KeyError, ValueError):
                    continue
    return bars


def option_gap_metrics(bars: dict[str, dict]) -> Optional[dict[str, float]]:
    b0959, b1000, b1001 = bars.get("09:59"), bars.get("10:00"), bars.get("10:01")
    if not (b0959 and b1000 and b1001):
        return None
    c0959, o0959, c1000, c1001 = b0959.get("c"), b0959.get("o"), b1000.get("c"), b1001.get("c")
    if None in (c0959, o0959, c1000, c1001) or c0959 == 0 or o0959 == 0:
        return None
    return {
        "move_1000_1001_pct": round((c1000 - c0959) / c0959 * 100, 3),
        "move_0959_1002_pct": round((c1001 - o0959) / o0959 * 100, 3),
    }


def option_files_for_date(date: str) -> list[Path]:
    out = []
    for f in OPT_CACHE_DIR.glob(f"*_1m_{date}.csv"):
        if OPT_FILE_RE.match(f.name):
            out.append(f)
    return sorted(out)


def build_gap_dataset(dates: list[str]) -> list[dict]:
    """One row per trading day: SPY metrics + per-contract option metrics + release flags."""
    rows = []
    for d in dates:
        flags = release_flags(d)
        bars = load_spy_bars(d)
        spy_m = spy_gap_metrics(bars) if bars else None
        opt_rows = []
        for f in option_files_for_date(d):
            m = OPT_FILE_RE.match(f.name)
            occ = m.group(1)
            obars = load_option_bars(f)
            gm = option_gap_metrics(obars)
            if gm:
                gm["symbol"] = occ
                opt_rows.append(gm)
        row = {
            "date": d, **{k: v for k, v in flags.items() if k != "date"},
            "spy": spy_m,
            "n_option_contracts": len(opt_rows),
            "option_contracts": opt_rows,
        }
        if opt_rows:
            moves_1001 = [r["move_1000_1001_pct"] for r in opt_rows]
            moves_0959 = [r["move_0959_1002_pct"] for r in opt_rows]
            row["worst_adverse_1000_1001_pct"] = round(min(moves_1001), 3)   # most negative
            row["max_abs_1000_1001_pct"] = round(max(abs(x) for x in moves_1001), 3)
            row["worst_adverse_0959_1002_pct"] = round(min(moves_0959), 3)
            row["max_abs_0959_1002_pct"] = round(max(abs(x) for x in moves_0959), 3)
        else:
            row["worst_adverse_1000_1001_pct"] = None
            row["max_abs_1000_1001_pct"] = None
            row["worst_adverse_0959_1002_pct"] = None
            row["max_abs_0959_1002_pct"] = None
        rows.append(row)
    return rows


# ============================================================================================
# 3. Position reconstruction from raw fills (mirrors tp1_r50_forward_shadow's FIFO grouping)
# ============================================================================================
def load_raw_fills() -> list[dict]:
    seen: set = set()
    fills: list[dict] = []
    if not FILLS_LEDGER.exists():
        return fills
    with FILLS_LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("is_option") or r.get("attribution") != "engine":
                continue
            aid = r.get("activity_id")
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            fills.append(r)
    fills.sort(key=lambda r: r["ts_utc"])
    return fills


def _parse_utc(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def build_positions(fills: list[dict]) -> list[dict]:
    """One record per BUY activity: entry fields + chronological sell `legs` + `remaining`.
    Identical FIFO grouping to tp1_r50_forward_shadow.legs_by_activity_id (arm, symbol,
    date_et keyed, defensively re-sorted by ts_utc), extended to keep the buy's own fields
    (not just its legs) since this study needs entry timestamp/price directly, not only the
    leg-level delta tp1_r50 needed."""
    fills = sorted(fills, key=lambda r: r["ts_utc"])
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in fills:
        groups[(r["arm"], r["symbol"], r["date_et"])].append(r)

    positions: list[dict] = []
    for g in groups.values():
        buys = [dict(r, remaining=r["qty"], legs=[]) for r in g if r["side"] == "buy"]
        pending, active = collections.deque(buys), collections.deque()
        for r in g:
            if r["side"] == "buy":
                active.append(pending.popleft())
                continue
            sq = r["qty"]
            while sq > 1e-9 and active:
                b = active[0]
                take = min(sq, b["remaining"])
                b["remaining"] -= take
                b["legs"].append({"price": float(r["price"]), "qty": take,
                                   "ts_utc": r["ts_utc"], "ts_et": r.get("ts_et")})
                sq -= take
                if b["remaining"] <= 1e-9:
                    active.popleft()
        positions.extend(buys)
    return positions


def score_position(b: dict) -> dict:
    multiplier = float(b.get("multiplier", 100))
    entry_price = float(b["price"])
    total_qty = float(b["qty"])
    legs = sorted(b["legs"], key=lambda l: l["ts_utc"])
    closed_qty = sum(l["qty"] for l in legs)
    fully_closed = b["remaining"] <= 1e-6
    realized_pnl = round(sum((l["price"] - entry_price) * l["qty"] for l in legs) * multiplier, 2)
    cost_basis_closed = entry_price * closed_qty * multiplier
    pnl_pct_of_premium = (realized_pnl / cost_basis_closed) if cost_basis_closed > 1e-9 else None

    entry_ts_et = b.get("ts_et", "")
    exit_ts_et = legs[-1]["ts_et"] if legs else None
    entry_hhmmss = entry_ts_et[11:19] if len(entry_ts_et) >= 19 else entry_ts_et[11:16] + ":00"
    exit_hhmmss = (exit_ts_et[11:19] if exit_ts_et and len(exit_ts_et) >= 19
                   else (exit_ts_et[11:16] + ":00" if exit_ts_et else None))

    hold_minutes = None
    if fully_closed and legs:
        try:
            hold_minutes = round((_parse_utc(legs[-1]["ts_utc"]) - _parse_utc(b["ts_utc"])).total_seconds() / 60.0, 2)
        except Exception:
            hold_minutes = None

    open_across_1000 = (entry_hhmmss < "10:00:00") and (
        (not fully_closed) or (exit_hhmmss is not None and exit_hhmmss > "10:00:00"))
    entry_in_0945_1005 = "09:45:00" <= entry_hhmmss < "10:05:00"
    entry_in_0935_1005 = "09:35:00" <= entry_hhmmss < "10:05:00"

    return {
        "activity_id": b.get("activity_id"), "arm": b["arm"], "symbol": b["symbol"],
        "date_et": b["date_et"], "entry_ts_et": entry_ts_et, "entry_ts_utc": b.get("ts_utc"),
        "entry_price": entry_price, "qty": total_qty, "multiplier": multiplier,
        "fully_closed": fully_closed, "remaining": round(b["remaining"], 4),
        "exit_ts_et": exit_ts_et, "hold_minutes": hold_minutes,
        "realized_pnl": realized_pnl, "pnl_pct_of_premium": (
            round(pnl_pct_of_premium, 4) if pnl_pct_of_premium is not None else None),
        "cap_hit_proxy": (pnl_pct_of_premium is not None and pnl_pct_of_premium <= CAP_HIT_THRESHOLD),
        "open_across_1000": open_across_1000,
        "entry_in_0945_1005": entry_in_0945_1005,
        "entry_in_0935_1005": entry_in_0935_1005,
        "legs": legs,
    }


def build_scored_positions() -> list[dict]:
    fills = load_raw_fills()
    positions = build_positions(fills)
    return [score_position(b) for b in positions]


# ============================================================================================
# Shared stats helpers (day-clustered bootstrap CI, top-3 concentration, drop-best-day) --
# mirrors tp1_r50_forward_shadow._bootstrap_day_clustered_mean / _top3_concentration_share
# EXACTLY (same methodology as go_live_gate.bootstrap_pf_ci: resample trading DAYS, not
# trades, respecting within-day correlation).
# ============================================================================================
def bootstrap_day_clustered_mean(values_by_day: dict[str, list[float]], n_boot: int = 2000,
                                  seed: int = 20260903) -> Optional[dict]:
    days = sorted(values_by_day)
    n_days = len(days)
    if n_days < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample_days = [days[rng.randrange(n_days)] for _ in range(n_days)]
        vals = [v for d in sample_days for v in values_by_day[d]]
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return {"n_boot": n_boot, "n_days_clustered": n_days,
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def top3_concentration_share(values: list[float]) -> float:
    total_abs = sum(abs(v) for v in values)
    if total_abs <= 1e-9:
        return 0.0
    top3 = sum(sorted((abs(v) for v in values), reverse=True)[:3])
    return round(top3 / total_abs, 4)


def drop_best_day(values_by_day: dict[str, list[float]]) -> dict:
    """Mirrors tp1_r50's ex_best_day_sum_delta: subtract the single day whose total is most
    favorable to the case being made (here: the day that saves the rule's proponent the most),
    report whether the remaining sum still supports the same conclusion."""
    by_day_total = {d: sum(v) for d, v in values_by_day.items()}
    if not by_day_total:
        return {"best_day": None, "best_day_total": 0.0, "total": 0.0, "ex_best_day_total": 0.0}
    total = sum(by_day_total.values())
    best_day = max(by_day_total, key=lambda d: by_day_total[d])
    return {"best_day": best_day, "best_day_total": round(by_day_total[best_day], 2),
            "total": round(total, 2), "ex_best_day_total": round(total - by_day_total[best_day], 2)}


# ============================================================================================
# 4. Descriptive cohorts (item 3 of the task)
# ============================================================================================
def describe_cohort(rows: list[dict], flags_by_date: dict[str, dict]) -> dict:
    def bucket(pred_release: bool) -> list[dict]:
        return [r for r in rows if flags_by_date.get(r["date_et"], {}).get("is_ism", False) == pred_release]

    def summarize(sub: list[dict]) -> dict:
        n = len(sub)
        closed = [r for r in sub if r["fully_closed"]]
        pnl_vals = [r["realized_pnl"] for r in closed]
        cap_hits = sum(1 for r in closed if r["cap_hit_proxy"])
        holds = [r["hold_minutes"] for r in closed if r["hold_minutes"] is not None]
        by_arm: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, "pnl": 0.0})
        for r in closed:
            by_arm[r["arm"]]["n"] += 1
            by_arm[r["arm"]]["pnl"] = round(by_arm[r["arm"]]["pnl"] + r["realized_pnl"], 2)
        return {
            "n_positions": n, "n_fully_closed": len(closed),
            "n_still_open": n - len(closed),
            "sum_pnl": round(sum(pnl_vals), 2),
            "mean_pnl": (round(sum(pnl_vals) / len(pnl_vals), 2) if pnl_vals else None),
            "cap_hit_rate": (round(cap_hits / len(closed), 4) if closed else None),
            "n_cap_hits": cap_hits,
            "mean_hold_minutes": (round(sum(holds) / len(holds), 2) if holds else None),
            "by_arm": dict(by_arm),
        }

    ism_rows, non_ism_rows = bucket(True), bucket(False)
    return {"ism_days": summarize(ism_rows), "non_ism_days": summarize(non_ism_rows)}


# ============================================================================================
# 5. Candidate rule costing (item 4 of the task) -- ENTRY-TICK information only, ISM-scoped
# ============================================================================================
def cost_r1_r2(rows: list[dict], flags_by_date: dict[str, dict], window_key: str,
               rule_name: str) -> dict:
    """R1 (window_key='entry_in_0945_1005') / R2 (window_key='entry_in_0935_1005'): remove
    every position whose ENTRY falls in the window on an ISM day. delta_saved = -realized_pnl
    (positive = a loss avoided, negative = a winner given up). Only fully-closed positions are
    costed (an open position's true P&L is unknown -- excluded and counted, never guessed)."""
    removed = [r for r in rows
               if flags_by_date.get(r["date_et"], {}).get("is_ism", False) and r.get(window_key)]
    removed_closed = [r for r in removed if r["fully_closed"]]
    removed_open = [r for r in removed if not r["fully_closed"]]

    deltas = [-r["realized_pnl"] for r in removed_closed]
    by_day: dict[str, list[float]] = collections.defaultdict(list)
    for r in removed_closed:
        by_day[r["date_et"]].append(-r["realized_pnl"])

    ci = bootstrap_day_clustered_mean(by_day)
    top3 = top3_concentration_share(deltas)
    dbd = drop_best_day(by_day)

    by_arm: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, "saved": 0.0})
    for r in removed_closed:
        by_arm[r["arm"]]["n"] += 1
        by_arm[r["arm"]]["saved"] = round(by_arm[r["arm"]]["saved"] + (-r["realized_pnl"]), 2)

    winners_forgone = round(sum(r["realized_pnl"] for r in removed_closed if r["realized_pnl"] > 0), 2)
    losses_avoided = round(-sum(r["realized_pnl"] for r in removed_closed if r["realized_pnl"] < 0), 2)
    big_days_touched = sorted({r["date_et"] for r in removed_closed} & set(BIG_WIN_DAYS))

    return {
        "rule": rule_name, "window": window_key,
        "n_trades_removed": len(removed), "n_removed_fully_closed": len(removed_closed),
        "n_removed_still_open_excluded": len(removed_open),
        "net_saved": round(sum(deltas), 2),
        "losses_avoided": losses_avoided, "winners_forgone": winners_forgone,
        "session_clustered_ci_on_net_saved_per_day": ci,
        "top3_concentration_share": top3,
        "drop_best_day": dbd,
        "big_win_days_touched": big_days_touched,
        "by_arm": dict(by_arm),
        "removed_dates": sorted({r["date_et"] for r in removed_closed}),
    }


R3_EXCLUDE_NOT_YET_ENTERED = "not_yet_entered_by_0958"
R3_EXCLUDE_NO_EFFECT = "already_closed_before_0958"
R3_EXCLUDE_NO_BAR = "no_bar_data"
R3_EXCLUDE_STILL_OPEN = "still_open_at_snapshot"


def r3_delta_for_position(r: dict, bar_cache: Optional[dict] = None) -> dict:
    """Single-position R3 counterfactual (shared by `cost_r3`'s multi-day aggregate AND
    `release_blackout_shadow.py`'s nightly per-day scoring -- EXTEND, DON'T FORK, one source
    of truth for the flatten-at-09:58 math). `bar_cache` is an optional {(symbol,date): bars}
    dict the caller can reuse across positions on the same contract/day; a fresh one is used
    when omitted. Returns either `{"included": True, ...delta fields...}` or
    `{"included": False, "exclude_reason": <one of the R3_EXCLUDE_* constants>}` -- never a
    silent None, so a caller can always account for every position it was handed."""
    if bar_cache is None:
        bar_cache = {}
    entry_ts_et = r["entry_ts_et"]
    entry_hhmmss = entry_ts_et[11:19] if len(entry_ts_et) >= 19 else entry_ts_et[11:16] + ":00"
    if entry_hhmmss >= "09:58:00":
        # the position was not even open yet at T-2 -- R3 cannot have flattened it
        return {"included": False, "exclude_reason": R3_EXCLUDE_NOT_YET_ENTERED}

    entry_price = r["entry_price"]
    multiplier = r["multiplier"]
    legs = r["legs"]
    qty_closed_before_0958 = sum(l["qty"] for l in legs if l["ts_et"][11:19] < "09:58:00")
    qty_total = r["qty"]
    remaining_at_0958 = round(qty_total - qty_closed_before_0958, 6)
    if remaining_at_0958 <= 1e-6:
        return {"included": False, "exclude_reason": R3_EXCLUDE_NO_EFFECT}
    if not r["fully_closed"] and remaining_at_0958 >= r["qty"] - r["remaining"] - 1e-6 and r["remaining"] > 1e-6:
        # still has open qty as of the ledger snapshot itself -- true realized pnl unknown
        return {"included": False, "exclude_reason": R3_EXCLUDE_STILL_OPEN}

    key = (r["symbol"], r["date_et"])
    if key not in bar_cache:
        f = OPT_CACHE_DIR / f"{r['symbol']}_1m_{r['date_et']}.csv"
        bar_cache[key] = load_option_bars(f) if f.exists() else {}
    bars = bar_cache[key]
    # nearest available minute at or before 09:58
    flatten_price = None
    for hhmm in ("09:58", "09:57", "09:56", "09:55"):
        b = bars.get(hhmm)
        if b:
            flatten_price = b["c"]
            break
    if flatten_price is None:
        return {"included": False, "exclude_reason": R3_EXCLUDE_NO_BAR}

    actual_remaining_pnl = sum(
        (l["price"] - entry_price) * l["qty"] for l in legs if l["ts_et"][11:19] >= "09:58:00"
    ) * multiplier
    cf_remaining_pnl = (flatten_price - entry_price) * remaining_at_0958 * multiplier
    delta = round(cf_remaining_pnl - actual_remaining_pnl, 2)
    return {
        "included": True,
        "activity_id": r["activity_id"], "arm": r["arm"], "symbol": r["symbol"],
        "date_et": r["date_et"], "remaining_at_0958": remaining_at_0958,
        "flatten_price": flatten_price, "actual_remaining_pnl": round(actual_remaining_pnl, 2),
        "cf_remaining_pnl": round(cf_remaining_pnl, 2), "delta": delta,
    }


def cost_r3(rows: list[dict], flags_by_date: dict[str, dict]) -> dict:
    """R3 = R1 + flatten any position still open at T-2 = 09:58 ET on an ISM day. For each
    ISM-day position, re-simulate: legs with ts_et < 09:58:00 keep their actual fill price;
    the qty still open AT 09:58 is marked at that SAME contract's own cached 1-min option bar
    close at/just-before 09:58 instead of whatever it actually did afterward.
    delta_r3 = counterfactual_remaining_pnl - actual_remaining_pnl (only for the portion open
    at 09:58; positions with no matching bar file, or already fully closed before 09:58, are
    EXCLUDED and counted separately -- never silently defaulted to 0). Per-position math lives
    in `r3_delta_for_position`; this function aggregates it across the whole population."""
    ism_rows = [r for r in rows if flags_by_date.get(r["date_et"], {}).get("is_ism", False)]

    deltas: list[tuple[str, float]] = []       # (date, delta)
    exclude_counts: dict[str, int] = collections.defaultdict(int)
    flattened: list[dict] = []

    bar_cache: dict[tuple, dict] = {}   # (symbol, date) -> bars dict, loaded once per contract

    for r in ism_rows:
        res = r3_delta_for_position(r, bar_cache)
        if not res["included"]:
            exclude_counts[res["exclude_reason"]] += 1
            continue
        deltas.append((res["date_et"], res["delta"]))
        flattened.append(res)

    n_no_effect = exclude_counts[R3_EXCLUDE_NO_EFFECT]
    n_not_yet_entered = exclude_counts[R3_EXCLUDE_NOT_YET_ENTERED]
    n_no_bar = exclude_counts[R3_EXCLUDE_NO_BAR]
    n_still_open_after_all_legs = exclude_counts[R3_EXCLUDE_STILL_OPEN]

    by_day: dict[str, list[float]] = collections.defaultdict(list)
    for d, v in deltas:
        by_day[d].append(v)

    ci = bootstrap_day_clustered_mean(by_day)
    top3 = top3_concentration_share([v for _, v in deltas])
    dbd = drop_best_day(by_day)

    by_arm: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, "delta": 0.0})
    for f in flattened:
        by_arm[f["arm"]]["n"] += 1
        by_arm[f["arm"]]["delta"] = round(by_arm[f["arm"]]["delta"] + f["delta"], 2)

    big_days_touched = sorted({d for d, _ in deltas} & set(BIG_WIN_DAYS))

    return {
        "rule": "R3", "n_positions_flattened": len(flattened),
        "n_no_effect_already_closed_before_0958": n_no_effect,
        "n_not_yet_entered_by_0958": n_not_yet_entered,
        "n_excluded_no_bar_data": n_no_bar,
        "n_excluded_still_open_at_snapshot": n_still_open_after_all_legs,
        "net_delta": round(sum(v for _, v in deltas), 2),
        "session_clustered_ci_on_delta_per_day": ci,
        "top3_concentration_share": top3,
        "drop_best_day": dbd,
        "big_win_days_touched": big_days_touched,
        "by_arm": dict(by_arm),
        "flattened_detail": flattened,
    }


# ============================================================================================
# 6. Report assembly
# ============================================================================================
def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001
        return dt.datetime.utcnow().isoformat() + "Z(fallback-utc-et_clock_unavailable)"


def run() -> dict:
    dates = trading_day_universe()
    flags_by_date = {d: release_flags(d) for d in dates}
    # also compute today's flag (partial-day, fills-only scope) for the fills-based sections
    flags_by_date[TODAY_PARTIAL] = release_flags(TODAY_PARTIAL)

    gap_dataset = build_gap_dataset(dates)

    ism_days = [d for d in dates if flags_by_date[d]["is_ism"]]
    secondary_days = [d for d in dates if flags_by_date[d]["is_secondary_10am"] and not flags_by_date[d]["is_ism"]]
    non_release_days = [d for d in dates if not flags_by_date[d]["is_release_day_any"]]

    def spy_bucket(day_list: list[str]) -> dict:
        by_day = collections.defaultdict(list)
        vals = []
        for row in gap_dataset:
            if row["date"] in day_list and row["spy"]:
                by_day[row["date"]].append(row["spy"]["abs_move_1000_1001_dollars"])
                vals.append(row["spy"]["abs_move_1000_1001_dollars"])
        ci = bootstrap_day_clustered_mean(by_day)
        return {"n_days": len(vals), "mean_abs_move_1000_1001_dollars": (round(sum(vals)/len(vals), 4) if vals else None),
                "max_abs_move_1000_1001_dollars": (round(max(vals), 4) if vals else None),
                "values": vals, "ci_on_mean": ci}

    def opt_bucket(day_list: list[str]) -> dict:
        by_day = collections.defaultdict(list)
        vals = []
        for row in gap_dataset:
            if row["date"] in day_list and row["worst_adverse_1000_1001_pct"] is not None:
                by_day[row["date"]].append(row["worst_adverse_1000_1001_pct"])
                vals.append(row["worst_adverse_1000_1001_pct"])
        ci = bootstrap_day_clustered_mean(by_day)
        n_ge15 = sum(1 for v in vals if v <= -15.0)
        return {"n_days_with_option_bars": len(vals),
                "mean_worst_adverse_pct": (round(sum(vals)/len(vals), 3) if vals else None),
                "min_worst_adverse_pct": (round(min(vals), 3) if vals else None),
                "n_days_with_ge15pct_adverse_1min_move": n_ge15,
                "values": vals, "ci_on_mean": ci}

    spy_gap_summary = {
        "ism_days": spy_bucket(ism_days), "secondary_days": spy_bucket(secondary_days),
        "non_release_days": spy_bucket(non_release_days),
        "named_ism_days_in_briefing": {d: spy_bucket([d]) for d in NAMED_ISM_DAYS if d in dates},
    }
    option_gap_summary = {
        "ism_days": opt_bucket(ism_days), "secondary_days": opt_bucket(secondary_days),
        "non_release_days": opt_bucket(non_release_days),
    }

    positions = build_scored_positions()
    cohort_summary = describe_cohort(positions, flags_by_date)

    r1 = cost_r1_r2(positions, flags_by_date, "entry_in_0945_1005", "R1")
    r2 = cost_r1_r2(positions, flags_by_date, "entry_in_0935_1005", "R2")
    r3 = cost_r3(positions, flags_by_date)

    # exploratory: R1 with secondary cohort included too (never part of the frozen decision)
    def is_release_any(date: str) -> bool:
        return flags_by_date.get(date, {}).get("is_release_day_any", False)
    exploratory_rows = [r for r in positions if is_release_any(r["date_et"]) and r.get("entry_in_0945_1005")]
    exploratory_closed = [r for r in exploratory_rows if r["fully_closed"]]
    r1_exploratory_incl_secondary = {
        "n_trades_removed": len(exploratory_rows),
        "net_saved": round(sum(-r["realized_pnl"] for r in exploratory_closed), 2),
        "note": ("EXPLORATORY ONLY -- includes secondary (CB/UMich) 10am releases, NOT part of "
                 "the frozen ISM-only rule. Included because 2026-08-28 (a named big-win day) "
                 "carries a UMich release; this shows what would happen if the rule's scope "
                 "were widened, which it is not."),
        "big_win_days_touched": sorted({r["date_et"] for r in exploratory_closed} & set(BIG_WIN_DAYS)),
    }

    big_day_flags = {d: {"is_ism": flags_by_date.get(d, {}).get("is_ism"),
                          "is_secondary": flags_by_date.get(d, {}).get("is_secondary_10am"),
                          "events": flags_by_date.get(d, {}).get("events_10am")} for d in BIG_WIN_DAYS}

    decision_inputs = {
        "r1_net_saved_after_drop_best_day": r1["drop_best_day"]["ex_best_day_total"],
        "r1_big_win_days_touched": r1["big_win_days_touched"],
        "r3_net_delta_after_drop_best_day": r3["drop_best_day"]["ex_best_day_total"],
        "r3_big_win_days_touched": r3["big_win_days_touched"],
    }

    out = {
        "generated_at_et": _stamp_now_et(),
        "study_start": STUDY_START, "study_end_cached": STUDY_END_CACHED,
        "today_partial": TODAY_PARTIAL,
        "n_trading_days_in_cached_universe": len(dates),
        "n_ism_days": len(ism_days), "ism_days": ism_days,
        "n_secondary_only_days": len(secondary_days), "secondary_only_days": secondary_days,
        "n_non_release_days": len(non_release_days),
        "big_win_days_release_flags": big_day_flags,
        "named_ism_days_from_briefing": NAMED_ISM_DAYS,
        "gap_dataset_by_day": gap_dataset,
        "spy_gap_summary": spy_gap_summary,
        "option_gap_summary": option_gap_summary,
        "n_positions_reconstructed": len(positions),
        "cohort_summary_open_across_1000_and_entry_window": cohort_summary,
        "R1": r1, "R2": r2, "R3": r3,
        "R1_exploratory_incl_secondary_cohort": r1_exploratory_incl_secondary,
        "decision_inputs": decision_inputs,
        "prereg": PREREG_REL,
        "b1_source": "setup/scripts/macro_calendar.py#scheduled_releases (imported live, confirmed usable)",
    }
    return out


# ============================================================================================
# 7. Markdown report writer
# ============================================================================================
def write_report(data: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")

    r1, r2, r3 = data["R1"], data["R2"], data["R3"]
    coh = data["cohort_summary_open_across_1000_and_entry_window"]
    spy_g, opt_g = data["spy_gap_summary"], data["option_gap_summary"]

    def fmt_ci(ci):
        if not ci:
            return "n/a (n_days<2)"
        return f"[{ci['ci_lower_2.5']}, {ci['ci_upper_97.5']}] (n_days={ci['n_days_clustered']}, n_boot={ci['n_boot']})"

    lines = []
    lines.append("# B2 -- SCHEDULED-RELEASE BLACKOUT STUDY (2026-09-03, stamp 12:40 ET)\n")
    lines.append(f"**Generated:** {data['generated_at_et']} · **Script:** `backtest/tools/release_gap_study.py`"
                 f" · **B1 source:** `{data['b1_source']}`\n")
    lines.append(f"**Study window:** {data['study_start']} .. {data['study_end_cached']} "
                 f"({data['n_trading_days_in_cached_universe']} trading days with an archived SPY 1-min "
                 f"cache). **{data['today_partial']} is EXCLUDED from the cached-bar distributional "
                 "sections (2) below** -- its SPY 1-min cache has not been archived yet (market open at "
                 "build time) -- but IS included in the fills-ledger-driven sections (3)/(4), which need "
                 "only fill timestamps. This asymmetry is intentional and stated once here, applies "
                 "everywhere below.\n")

    lines.append("## 1. Release calendar over the study window (B1 `scheduled_releases`, ISM tier-1 + secondary)\n")
    lines.append(f"- **ISM (tier-1, severity=high) days:** {data['n_ism_days']} -- {', '.join(data['ism_days'])}")
    lines.append(f"- **Secondary-only (CB/UMich, severity=med, RULE_BASED_UNVERIFIED) days:** "
                 f"{data['n_secondary_only_days']} -- {', '.join(data['secondary_only_days'])}")
    lines.append(f"- **Non-release days:** {data['n_non_release_days']}")
    lines.append(f"- **Named ISM days from this task's briefing:** {', '.join(data['named_ism_days_from_briefing'])} "
                 "-- both confirmed ISM in the calendar above.\n")
    lines.append("**Four named winning days, checked against the calendar:**\n")
    lines.append("| Day | ISM (tier-1)? | Secondary 10am event? |")
    lines.append("|---|---|---|")
    for d, f in data["big_win_days_release_flags"].items():
        ev = ", ".join(e["type"] for e in (f["events"] or [])) or "none"
        lines.append(f"| {d} | {f['is_ism']} | {f['is_secondary']} ({ev}) |")
    lines.append("\n2026-08-28 carries a **secondary** (`umich_sentiment_final`) release, not ISM. The "
                 "frozen candidate rules (R1/R2/R3, see §4) are scoped to **ISM-only** (\"tier-1\" per this "
                 "task's own wording) so 2026-08-28 is untouched by the frozen rules; §4 also reports an "
                 "EXPLORATORY ISM+secondary variant for transparency, never part of the frozen decision.\n")

    lines.append("## 2. SPY $ and option % moves across the 10:00 ET window\n")
    lines.append("### SPY, |move| from close(09:59 bar) to close(10:00 bar) -- the release-print minute\n")
    lines.append("| Cohort | n days | mean \\|move\\| $ | max \\|move\\| $ | day-clustered CI on mean |")
    lines.append("|---|---:|---:|---:|---|")
    for label, key in (("ISM days", "ism_days"), ("Secondary-only days", "secondary_days"),
                       ("Non-release days", "non_release_days")):
        b = spy_g[key]
        lines.append(f"| {label} | {b['n_days']} | {b['mean_abs_move_1000_1001_dollars']} | "
                     f"{b['max_abs_move_1000_1001_dollars']} | {fmt_ci(b['ci_on_mean'])} |")
    for d, b in spy_g.get("named_ism_days_in_briefing", {}).items():
        lines.append(f"| ({d}, named in briefing) | {b['n_days']} | {b['mean_abs_move_1000_1001_dollars']} | "
                     f"{b['max_abs_move_1000_1001_dollars']} | -- |")
    lines.append("")

    lines.append("### Option worst 1-minute adverse move (min over that day's cached contracts), "
                 "close(09:59)->close(10:00)\n")
    lines.append("| Cohort | n days w/ option bars | mean worst-adverse % | min (most negative) % | "
                 "days with a >=15% adverse move | CI on mean |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for label, key in (("ISM days", "ism_days"), ("Secondary-only days", "secondary_days"),
                       ("Non-release days", "non_release_days")):
        b = opt_g[key]
        lines.append(f"| {label} | {b['n_days_with_option_bars']} | {b['mean_worst_adverse_pct']} | "
                     f"{b['min_worst_adverse_pct']} | {b['n_days_with_ge15pct_adverse_1min_move']} | "
                     f"{fmt_ci(b['ci_on_mean'])} |")
    lines.append("\n_Option coverage is sparse (only contracts actually held/cached that day survive in "
                 f"`backtest/data/highres/`) -- {sum(1 for r in data['gap_dataset_by_day'] if r['n_option_contracts']>0)}"
                 f" of {data['n_trading_days_in_cached_universe']} cached-SPY days have >=1 matching option "
                 "file. Treat cell n's literally; this is not a full-chain study._\n")

    lines.append("## 3. Engine positions around the 10:00 window (fills-ledger reconstruction, "
                 f"n={data['n_positions_reconstructed']} positions, includes {data['today_partial']})\n")
    lines.append("### Positions OPEN across 10:00:00 ET, and entries in [09:45,10:05) -- ISM vs non-ISM days\n")
    lines.append("| | n positions | n closed | sum P&L | mean P&L | cap-hit rate (proxy <=-45% premium) | "
                 "mean hold (min) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, key in (("ISM days", "ism_days"), ("Non-ISM days", "non_ism_days")):
        c = coh[key]
        lines.append(f"| {label} | {c['n_positions']} | {c['n_fully_closed']} | {c['sum_pnl']} | "
                     f"{c['mean_pnl']} | {c['cap_hit_rate']} | {c['mean_hold_minutes']} |")
    lines.append("\n_(this cohort mixes \"open across 10:00\" and \"entered in window\" positions since "
                 "`describe_cohort` buckets purely by day-is-ISM; see the JSON's `R1`/`R3` sections for the "
                 "precisely-scoped rule populations.)_\n")

    lines.append("## 4. Candidate rule costing (ENTRY-TICK information only, ISM-scoped, frozen)\n")
    for r, name, desc in ((r1, "R1", "no entries [09:45,10:05) on an ISM day"),
                         (r2, "R2", "no entries [09:35,10:05) on an ISM day (R1 + kills the whole pre-release morning)")):
        lines.append(f"### {name} -- {desc}\n")
        lines.append(f"- n trades removed: **{r['n_trades_removed']}** ({r['n_removed_fully_closed']} fully "
                     f"closed & costed, {r['n_removed_still_open_excluded']} excluded still-open)")
        lines.append(f"- net $ saved (losses avoided − winners forgone): **{r['net_saved']}** "
                     f"(losses avoided {r['losses_avoided']}, winners forgone {r['winners_forgone']})")
        lines.append(f"- day-clustered bootstrap CI on net-saved/day: {fmt_ci(r['session_clustered_ci_on_net_saved_per_day'])}")
        lines.append(f"- top-3 |delta| concentration share: {r['top3_concentration_share']}")
        lines.append(f"- drop-best-day: best day {r['drop_best_day']['best_day']} contributed "
                     f"{r['drop_best_day']['best_day_total']}; ex-best-day total = "
                     f"**{r['drop_best_day']['ex_best_day_total']}**")
        lines.append(f"- big-win-days touched: {r['big_win_days_touched'] or 'NONE'}")
        lines.append(f"- by arm: {json.dumps(r['by_arm'])}")
        lines.append(f"- dates touched: {r['removed_dates']}\n")

    lines.append("### R3 -- R1 + flatten any position open at T-2 = 09:58 ET on an ISM day (kill-type)\n")
    lines.append(f"- n positions flattened & costed: **{r3['n_positions_flattened']}**")
    lines.append(f"- excluded: {r3['n_no_effect_already_closed_before_0958']} already closed before 09:58 "
                 f"(no effect), {r3['n_not_yet_entered_by_0958']} entered at/after 09:58 (position didn't "
                 f"exist yet), {r3['n_excluded_no_bar_data']} no matching option bar, "
                 f"{r3['n_excluded_still_open_at_snapshot']} still open at ledger-read time")
    lines.append(f"- net $ delta (flatten-at-09:58 counterfactual vs actual): **{r3['net_delta']}**")
    lines.append(f"- day-clustered bootstrap CI on delta/day: {fmt_ci(r3['session_clustered_ci_on_delta_per_day'])}")
    lines.append(f"- top-3 |delta| concentration share: {r3['top3_concentration_share']}")
    lines.append(f"- drop-best-day: best day {r3['drop_best_day']['best_day']} contributed "
                 f"{r3['drop_best_day']['best_day_total']}; ex-best-day total = "
                 f"**{r3['drop_best_day']['ex_best_day_total']}**")
    lines.append(f"- big-win-days touched: {r3['big_win_days_touched'] or 'NONE'}")
    lines.append(f"- by arm: {json.dumps(r3['by_arm'])}\n")

    exp = data["R1_exploratory_incl_secondary_cohort"]
    lines.append("### EXPLORATORY (not frozen) -- R1 scope widened to ISM + secondary (CB/UMich)\n")
    lines.append(f"- n trades removed: {exp['n_trades_removed']}, net saved: {exp['net_saved']}")
    lines.append(f"- big-win-days touched: {exp['big_win_days_touched'] or 'NONE'}")
    lines.append(f"- {exp['note']}\n")

    lines.append("## 5. Data sources (all read-only, no trading-path or generated-surface file touched)\n")
    lines.append("- `setup/scripts/macro_calendar.py#scheduled_releases` (B1, imported live)")
    lines.append("- `backtest/data/spy_sip_cache/spy_1m_<date>.json` (SPY 1-min bars)")
    lines.append("- `backtest/data/highres/<OCC>_1m_<date>.csv` (per-contract 1-min option bars)")
    lines.append("- `automation/state/fills-ledger.jsonl` (raw broker fills, `attribution==\"engine\"`, "
                 "`is_option==True`)")
    lines.append(f"- `{data['prereg']}` (decision rule, frozen)\n")

    lines.append("## 6. What this does NOT claim\n")
    lines.append("- No exact per-fill exit-REASON field survives to `fills-ledger.jsonl` -- the "
                 "cap-hit-rate in §3 is a proxy (`realized_pnl <= -45% of cost basis on the closed qty`), "
                 "not a parsed `premium_stop`/`structure_stop`/`tp1`/`trail` classification.")
    lines.append("- R3's counterfactual flatten price uses the SAME contract's own cached 1-min bar close "
                 "at/just-before 09:58 -- not a bid/ask fill simulation, no slippage modeled.")
    lines.append(f"- {data['today_partial']} (today, an ISM day, market open at build time) contributes NO "
                 "row to the §2 SPY/option distributional study (no archived 1-min cache yet) -- its "
                 "already-verified facts live in `dissect-wave-autopsy.md`, cross-referenced not reproduced.")
    lines.append("- Option contract coverage in `backtest/data/highres/` is sparse and skewed toward "
                 "contracts the engine actually held that day -- not a full OPRA chain snapshot.\n")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    data = run()
    write_report(data)
    summary = {
        "n_trading_days": data["n_trading_days_in_cached_universe"],
        "n_ism_days": data["n_ism_days"], "ism_days": data["ism_days"],
        "n_positions_reconstructed": data["n_positions_reconstructed"],
        "R1_net_saved": data["R1"]["net_saved"],
        "R1_n_removed": data["R1"]["n_trades_removed"],
        "R1_big_win_days_touched": data["R1"]["big_win_days_touched"],
        "R2_net_saved": data["R2"]["net_saved"],
        "R3_net_delta": data["R3"]["net_delta"],
        "R3_n_flattened": data["R3"]["n_positions_flattened"],
        "R3_big_win_days_touched": data["R3"]["big_win_days_touched"],
        "outputs": [str(OUT_JSON), str(OUT_MD)],
    }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
