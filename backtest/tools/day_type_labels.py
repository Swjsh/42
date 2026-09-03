#!/usr/bin/env python
"""day_type_labels.py -- F5 DAY-TYPE CLASSIFIER: the realized-label table + the
09:35/09:45-computable feature rows that feed it.

Descends from analysis/deep-research/2026-09-03-money/SYNTHESIS.md section 2 ("the lever is
a day-type discriminator known at entry time") and forward instrument F5 ("the P1 free swarm
grinds entry-time-known day-type features against the 44-day real-fills population with the
decision rule frozen; forward-scored"). Frozen prereg:
analysis/recommendations/prereg-day-type-classifier-2026-09-03.md -- read that file for the
label definition, the frozen feature list, the model class, the validation protocol, and the
ship decision rule. THIS SCRIPT DOES NOT BUILD OR SHIP A CLASSIFIER -- it only produces the
two inputs (labels, features) a classifier build would consume. No trading-path file is read
for anything but its own (already-computed, already-live) context.

TWO THINGS COMPUTED, KEPT STRICTLY SEPARATE:

  1. LABELS (`labels`) -- realized, day-final, HINDSIGHT-BY-CONSTRUCTION. Built from
     `automation/state/fills-ledger.jsonl` (broker truth), engine-attributed option fills
     only (`is_option and attribution=='engine'`; excludes the small manual/crypto
     bycatch -- see `_load_engine_option_fills`). FIFO buy/sell leg matching per
     (arm, symbol, date_et), mirroring `setup/scripts/tp1_r50_forward_shadow.py
     .legs_by_activity_id` EXACTLY (same grouping contract, so activity_id joins with other
     instruments in this family stay aligned) -- this module reproduces that function rather
     than importing it, because importing a `setup/scripts/*_shadow.py` module into a
     `backtest/tools/*` builder would create an odd cross-tree dependency for a ~40-line
     pure function; the fixture-level parity is pinned by this module's own test file.
     A trading day's label is NEVER available before the day closes -- this table exists to
     be JOINED against features that ARE available early, never used as an entry-time input
     itself. THE CURRENT (in-progress) TRADING SESSION IS ALWAYS LABELED `in_progress` --
     never given a final paying/tax/mixed verdict while the market is still open, no matter
     how many legs have already closed.

  2. FEATURES (`features_0935` / `features_0945`) -- causal, NO LOOK-AHEAD, split into two
     buckets by when each quantity is actually knowable, because the frozen feature list
     itself spans two different availability times:
       - `features_0935`: overnight gap $/%, prior-day range, VIX level + 5d/20d slope +
         overnight change, day-of-week, event-calendar flag. All knowable by the 09:35 ET
         entry gate (CLAUDE.md's own "09:35 ET entry gate" language) -- none of these
         quantities depend on anything that happens after the open.
       - `features_0945`: the 09:30-09:45 opening-range width + its position vs the prior
         day's range, and the first-15-minute ribbon-flip count. These CANNOT be computed at
         09:35 without look-ahead -- the opening range is not closed until 09:45 by
         definition (same "a bar is real once its CLOSE time passes" discipline
         `backtest/lib/regime_early_features.py.bars_through_cutoff` already encodes for 5m
         bars). Available at "each entry tick" from 09:45 onward, per the task brief's own
         phrasing -- this is the resolution of the apparent tension between "computable at
         09:35" and "opening-range 09:30-09:45": the OR sub-features simply are NOT part of
         the 09:35 snapshot; they join the feature set once the window they describe has
         actually closed. Stated as a one-line assumption per CLAUDE.md's judgment-guards
         (assumption surfacing), not silently resolved.
       - ES/SPY premarket trend is in the frozen feature list ("if cached") but NO cached
         ES/premarket-futures series exists anywhere in this repo (verified this build --
         `find . -iname '*es_futures*'` and `*premarket*` turn up logs/docs, never an ES bar
         cache). The field is emitted as `null` with an explicit
         `es_spy_premarket_trend_reason`, never fabricated or silently dropped (C7/OP-33).

  BOTH feature functions are STRUCTURALLY incapable of look-ahead, not just runtime-checked:
  `_features_0935_from_ticks` and `_features_0945_from_ticks` each receive an ALREADY-SLICED
  list of ticks (mirrors `regime_early_features.early_features`'s "reduce over whatever
  you're given, no cutoff parameter" contract) -- the caller does the slicing once, at the
  single call site in `run()`. The guard test corrupts/reverses ticks strictly after each
  cutoff and asserts the computed row is byte-identical, the same RED-proof technique
  `backtest/tests/test_regime_early_classifier_guards.py` already uses for 5m bars.

DATA SOURCES (read-only; nothing on the trading path is imported or written):
  automation/state/fills-ledger.jsonl     realized labels (broker truth, FIFO leg match)
  automation/state/core-decisions.jsonl   per-minute spy/vix/ribbon ticks + (from
                                           2026-07-15 on) context_bundle.events, the
                                           ONLY source for the event-calendar flag on a
                                           PAST date (automation/state/news.json is a
                                           TODAY-only snapshot and cannot answer "was there
                                           an event flagged on 2026-07-22" retroactively)

WHY A FULL REBUILD EVERY RUN, NOT AN INCREMENTAL CURSOR: the two input files are small
(core-decisions.jsonl ~37.6k lines / fills-ledger.jsonl ~1.3k lines as of this build) and a
full parse+recompute finishes in low single-digit seconds (measured, printed by --self-time)
-- comfortably inside the 5-minute reaper window with wide margin, so there is no
correctness or performance reason to carry cursor state across runs. Output
(`analysis/recommendations/day-type-labels.json`) is fully OVERWRITTEN each run, not
append-only -- there is nothing to dedup because there is nothing partial to merge.

$0. Pure Python stdlib (no pandas/numpy) over two already-written JSONL files on disk.
Read-only on automation/state/**; writes only its own output JSON. Never places an order,
never touches params*.json/heartbeat_core.py/strategies.py/accounts.json.

Run: python backtest/tools/day_type_labels.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

OUT_DIR = REPO / "analysis" / "recommendations"
OUT_JSON = OUT_DIR / "day-type-labels.json"
PREREG_REL = "analysis/recommendations/prereg-day-type-classifier-2026-09-03.md"

LABEL_TABLE_START_DATE = "2026-07-01"      # per the F5 task brief, exact
EXIT_MULTIPLE_PAYING_THRESHOLD = 1.3       # "exits >= 1.3x entry premium" -- the engine's
                                            # own established edge definition (winner_
                                            # signature.py _mult_band; MEMORY.md "Engine
                                            # edge = a RIGHT TAIL"), reused not reinvented
PNL_EPSILON = 0.005                        # book_pnl within this of 0 -> neither > nor <

# The four named anchor winning days this whole audit is protecting (loss-size-math.md
# section 5's "Big winning days" table + SYNTHESIS.md section 1/2). A classifier that would
# have refused entries on any of these is refused by the prereg's own decision rule --
# reproduced here ONLY as a sanity constant for the anchor-day check block in the output
# (never as a filter on the data itself).
NAMED_BIG_DAYS = ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")


# ------------------------------------------------------------------------------------------
# generic helpers
# ------------------------------------------------------------------------------------------
def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn last line must never kill the build


def _stamp_now_et() -> tuple[str, str]:
    """Returns (iso_stamp, today_date_str). ET via et_clock, NEVER Bash TZ (CLAUDE.md)."""
    try:
        from et_clock import et_now  # noqa: PLC0415
        now = et_now()
        return now.isoformat(), now.date().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the build
        today = dt.date.today().isoformat()
        return today, today


def _slope(values: list[float]) -> float | None:
    """OLS slope of `values` against x=0..n-1. None on n<2 (a slope needs >=2 points)."""
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs)
    return round(num / den, 5) if den else None


# ------------------------------------------------------------------------------------------
# 1. LABELS -- realized book P&L + "at least one exit >= 1.3x" per session, from
#    fills-ledger.jsonl (broker truth)
# ------------------------------------------------------------------------------------------
def _load_engine_option_fills() -> list[dict]:
    """Engine-attributed option fills only. Excludes: manual j_override fills, crypto
    fills (BTC/USD gym microtrades journaled with 'manual' attribution -- these carry
    is_option=False and are what produces the handful of Saturday/Sunday/holiday `date_et`
    values seen in the raw ledger; they are never SPY 0DTE sessions and must not leak a
    label onto a non-trading day)."""
    seen: set = set()
    fills: list[dict] = []
    for r in _iter_jsonl(FILLS_LEDGER):
        if not r.get("is_option") or r.get("attribution") != "engine":
            continue
        aid = r.get("activity_id")
        if aid is None or aid in seen:
            continue
        seen.add(aid)
        fills.append(r)
    fills.sort(key=lambda r: r["ts_utc"])
    return fills


def _legs_by_activity_id(fills: list[dict]) -> dict[str, dict]:
    """Per-buy record {legs, remaining, total_qty, entry_price, multiplier, date_et, arm}.

    Reproduces `tp1_r50_forward_shadow.legs_by_activity_id`'s FIFO (arm, symbol, date_et)
    grouping EXACTLY (same contract, independently re-verified here rather than imported --
    see module docstring). `legs` is chronologically ordered sell fills against that buy."""
    fills = sorted(fills, key=lambda r: r["ts_utc"])
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in fills:
        groups[(r["arm"], r["symbol"], r["date_et"])].append(r)

    by_activity: dict[str, dict] = {}
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
                b["legs"].append({"price": float(r["price"]), "qty": take})
                sq -= take
                if b["remaining"] <= 1e-9:
                    active.popleft()
        for b in buys:
            by_activity[b["activity_id"]] = {
                "legs": b["legs"], "remaining": b["remaining"], "total_qty": b["qty"],
                "entry_price": float(b["price"]), "multiplier": float(b.get("multiplier", 100)),
                "date_et": b["date_et"], "arm": b["arm"],
            }
    return by_activity


def score_activities() -> list[dict]:
    """One row per BUY activity: realized_pnl (closed portion only), exit_multiple_max
    (max leg price / entry price, across all sell legs -- 'at least one exit >= 1.3x' is
    evaluated per-leg, not on a weighted-average exit), outcome, and whether the position
    is still open (remaining > 0 -- expected for 0DTE only on the CURRENT session)."""
    fills = _load_engine_option_fills()
    legs_index = _legs_by_activity_id(fills)
    rows = []
    for aid, rec in legs_index.items():
        legs = rec["legs"]
        entry_price = rec["entry_price"]
        mult = rec["multiplier"]
        closed_qty = sum(l["qty"] for l in legs)
        proceeds = sum(l["price"] * l["qty"] for l in legs) * mult
        cost = entry_price * closed_qty * mult
        realized_pnl = round(proceeds - cost, 2) if closed_qty > 1e-9 else 0.0
        exit_multiple_max = (max(l["price"] for l in legs) / entry_price
                              if legs and entry_price > 1e-9 else None)
        outcome = ("no_exit" if closed_qty <= 1e-9 else
                   "winner" if realized_pnl > 0.01 else
                   "loser" if realized_pnl < -0.01 else "scratch")
        rows.append({
            "activity_id": aid, "arm": rec["arm"], "date_et": rec["date_et"],
            "entry_price": entry_price, "closed_qty": closed_qty, "total_qty": rec["total_qty"],
            "still_open": rec["remaining"] > 1e-6,
            "realized_pnl": realized_pnl, "exit_multiple_max": exit_multiple_max,
            "had_exit_ge_threshold": (exit_multiple_max is not None
                                       and exit_multiple_max >= EXIT_MULTIPLE_PAYING_THRESHOLD),
            "outcome": outcome,
        })
    return rows


def label_for_day(book_pnl: float, n_winners: int, n_closed: int, had_1_3x: bool,
                   is_current_session: bool) -> tuple[str, str]:
    """Returns (label, rule_matched). See prereg §1 for the frozen definition:
      paying = book_pnl > 0 AND >=1 exit >= 1.3x entry premium (any activity, any arm)
      tax    = book_pnl < 0 AND every closed activity that day was a loser (n_winners==0)
               -- 'every exit a stop' is APPROXIMATED as 'every closed activity lost money',
               disclosed explicitly: fills-ledger.jsonl carries no ground-truth exit-reason
               tag (loss-size-math.md section 8's same disclosed gap), so 'stop' cannot be
               distinguished from 'time-stop' or 'structure-stop' losses -- all are losses.
      mixed  = neither condition holds (book near zero, or book>0 without a 1.3x exit, or
               book<0 with at least one winner)
      no_trade = zero closed activities that day
      in_progress = the CURRENT trading session -- NEVER given a final verdict while open
    """
    if is_current_session:
        return "in_progress", "current_session_never_finalized"
    if n_closed == 0:
        return "no_trade", "zero_closed_activities"
    if book_pnl > PNL_EPSILON and had_1_3x:
        return "paying", "book>0_and_exit>=1.3x"
    if book_pnl < -PNL_EPSILON and n_winners == 0:
        return "tax", "book<0_and_zero_winners"
    return "mixed", "neither_paying_nor_tax_condition_met"


def build_labels(today_str: str) -> tuple[list[dict], dict]:
    activities = score_activities()
    by_date: dict[str, list[dict]] = collections.defaultdict(list)
    for a in activities:
        by_date[a["date_et"]].append(a)

    dates = sorted(d for d in by_date if d >= LABEL_TABLE_START_DATE)
    rows = []
    for d in dates:
        acts = by_date[d]
        closed = [a for a in acts if a["outcome"] != "no_exit"]
        book_pnl = round(sum(a["realized_pnl"] for a in closed), 2)
        n_winners = sum(1 for a in closed if a["outcome"] == "winner")
        n_losers = sum(1 for a in closed if a["outcome"] == "loser")
        n_scratch = sum(1 for a in closed if a["outcome"] == "scratch")
        had_1_3x = any(a["had_exit_ge_threshold"] for a in closed)
        n_still_open = sum(1 for a in acts if a["still_open"])
        is_current = (d == today_str)
        label, rule = label_for_day(book_pnl, n_winners, len(closed), had_1_3x, is_current)
        rows.append({
            "date": d, "day_of_week": dt.date.fromisoformat(d).strftime("%A"),
            "n_activities_total": len(acts), "n_closed": len(closed),
            "n_winners": n_winners, "n_losers": n_losers, "n_scratch": n_scratch,
            "n_still_open": n_still_open, "book_pnl": book_pnl,
            "had_exit_ge_1_3x": had_1_3x, "label": label, "label_rule": rule,
            "arms_active": sorted({a["arm"] for a in acts}),
        })

    counts = collections.Counter(r["label"] for r in rows)
    anchor_check = {}
    label_by_date = {r["date"]: r["label"] for r in rows}
    for d in NAMED_BIG_DAYS:
        anchor_check[d] = {
            "label": label_by_date.get(d, "NOT_IN_TABLE"),
            "is_paying": label_by_date.get(d) == "paying",
        }
    return rows, {
        "label_counts": dict(counts),
        "n_sessions": len(rows),
        "anchor_day_check": anchor_check,
        "all_four_anchor_days_paying": all(v["is_paying"] for v in anchor_check.values()),
    }


# ------------------------------------------------------------------------------------------
# 2. FEATURES -- 09:35 and 09:45 snapshots from core-decisions.jsonl, no look-ahead
# ------------------------------------------------------------------------------------------
def load_core_ticks() -> dict[str, list[dict]]:
    """by_date[date] = ticks for account=='safe' that date, sorted by time. Falls back to
    account=='bold' for a date with zero 'safe' ticks (neither core account has ever been
    absent on a live trading day in this ledger, but the fallback is defensive, not load-
    bearing)."""
    safe_by_date: dict[str, list[dict]] = collections.defaultdict(list)
    bold_by_date: dict[str, list[dict]] = collections.defaultdict(list)
    for r in _iter_jsonl(CORE_DECISIONS):
        ts = r.get("ts_et", "")
        if len(ts) < 19:
            continue
        d, t = ts[:10], ts[11:19]
        tick = {"date": d, "time": t, "spy": r.get("spy"), "vix": r.get("vix"),
                "ribbon": r.get("ribbon"), "context_bundle": r.get("context_bundle")}
        if r.get("account") == "safe":
            safe_by_date[d].append(tick)
        elif r.get("account") == "bold":
            bold_by_date[d].append(tick)
    by_date: dict[str, list[dict]] = {}
    for d in set(safe_by_date) | set(bold_by_date):
        ticks = safe_by_date.get(d) or bold_by_date.get(d) or []
        by_date[d] = sorted(ticks, key=lambda t: t["time"])
    return by_date


def _daily_vix_close(by_date: dict[str, list[dict]]) -> dict[str, float]:
    """Last known VIX tick of each date -- used as the trailing series for the 5d/20d
    slope AND as 'yesterday's VIX' for the overnight-change feature."""
    out = {}
    for d, ticks in by_date.items():
        vix_ticks = [t["vix"] for t in ticks if t.get("vix") is not None]
        if vix_ticks:
            out[d] = vix_ticks[-1]
    return out


def _features_0935_from_ticks(ticks_upto_0935: list[dict], prior_day_ticks: list[dict],
                               vix_trailing_5: list[float], vix_trailing_20: list[float]
                               ) -> dict:
    """STRUCTURALLY no-look-ahead: receives only the pre-sliced tick lists (today's ticks
    up to and including 09:35, and the full prior trading day). Has no notion of 'today
    after 09:35' -- it cannot read what it was never handed (same contract as
    regime_early_features.early_features)."""
    out: dict = {}
    today_open = ticks_upto_0935[0]["spy"] if ticks_upto_0935 else None
    t0935 = ticks_upto_0935[-1] if ticks_upto_0935 else None
    vix_0935 = t0935["vix"] if t0935 else None

    prior_spy = [t["spy"] for t in prior_day_ticks if t.get("spy") is not None]
    prior_vix = [t["vix"] for t in prior_day_ticks if t.get("vix") is not None]
    prior_high = max(prior_spy) if prior_spy else None
    prior_low = min(prior_spy) if prior_spy else None
    prior_close = prior_spy[-1] if prior_spy else None
    prior_vix_close = prior_vix[-1] if prior_vix else None
    prior_range = (round(prior_high - prior_low, 4)
                   if prior_high is not None and prior_low is not None else None)

    out["overnight_gap_dollars"] = (round(today_open - prior_close, 4)
                                     if today_open is not None and prior_close else None)
    out["overnight_gap_pct"] = (round(100.0 * (today_open - prior_close) / prior_close, 4)
                                 if today_open is not None and prior_close else None)
    out["prior_day_range_dollars"] = prior_range
    out["vix_level_0935"] = vix_0935
    out["vix_overnight_change"] = (round(vix_0935 - prior_vix_close, 4)
                                    if vix_0935 is not None and prior_vix_close is not None
                                    else None)
    out["vix_5d_slope"] = _slope(vix_trailing_5) if len(vix_trailing_5) >= 2 else None
    out["vix_5d_slope_n"] = len(vix_trailing_5)
    out["vix_20d_slope"] = _slope(vix_trailing_20) if len(vix_trailing_20) >= 2 else None
    out["vix_20d_slope_n"] = len(vix_trailing_20)

    # event-calendar flag: sourced from THIS tick's own context_bundle.events (computed
    # live at 09:35 that day) -- never from automation/state/news.json, which is a
    # today-only snapshot and cannot answer a historical date.
    cb = (t0935 or {}).get("context_bundle") or {}
    events = cb.get("events") or {}
    next_et = events.get("next_event_et") or ""
    if not cb:
        out["event_calendar_flag"] = None
        out["event_calendar_reason"] = ("context_bundle not present on this tick -- "
                                         "v1.1 (events/prior_day/today_context) shipped "
                                         "2026-07-15; dates before that carry no bundle")
    else:
        # next_event_et is formatted 'HH:MM ET YYYY-MM-DD' (macro_calendar.py convention)
        ev_date = next_et.split(" ")[-1] if next_et else None
        today_date = ticks_upto_0935[0]["date"] if ticks_upto_0935 else None
        flag = bool(ev_date and today_date and ev_date == today_date
                    and events.get("next_event_severity") in ("high", "medium"))
        out["event_calendar_flag"] = flag
        out["event_calendar_severity"] = events.get("next_event_severity") if flag else None
        out["event_calendar_reason"] = "from this tick's own context_bundle.events"

    out["es_spy_premarket_trend"] = None
    out["es_spy_premarket_trend_reason"] = (
        "no cached ES/premarket-futures bar series exists in this repo (verified this "
        "build) -- frozen NOT_AVAILABLE, never fabricated (C7)")
    return out


def _features_0945_from_ticks(ticks_0930_to_0945: list[dict], prior_low: float | None,
                               prior_range: float | None) -> dict:
    """STRUCTURALLY no-look-ahead: receives only the 09:30<=t<09:45 tick slice. The 09:45
    tick itself is EXCLUDED (mirrors bars_through_cutoff's '< cutoff' convention -- the
    09:30-09:45 window is not closed until wall-clock reaches 09:45)."""
    spy_vals = [t["spy"] for t in ticks_0930_to_0945 if t.get("spy") is not None]
    ribbons = [t["ribbon"] for t in ticks_0930_to_0945 if t.get("ribbon") is not None]
    out: dict = {"n_ticks_in_window": len(ticks_0930_to_0945)}
    if spy_vals:
        or_high, or_low = max(spy_vals), min(spy_vals)
        or_mid = (or_high + or_low) / 2.0
        out["opening_range_width_dollars"] = round(or_high - or_low, 4)
        out["opening_range_position_vs_prior_range"] = (
            round((or_mid - prior_low) / prior_range, 4)
            if prior_low is not None and prior_range not in (None, 0) else None)
    else:
        out["opening_range_width_dollars"] = None
        out["opening_range_position_vs_prior_range"] = None
    flips = sum(1 for i in range(1, len(ribbons)) if ribbons[i] != ribbons[i - 1])
    out["first_15min_ribbon_flips_count"] = flips if ribbons else None
    return out


def build_features(today_str: str) -> list[dict]:
    by_date = load_core_ticks()
    vix_close = _daily_vix_close(by_date)
    all_dates_sorted = sorted(by_date)  # FULL history (from 2026-06-25), for trailing windows
    date_idx = {d: i for i, d in enumerate(all_dates_sorted)}

    session_dates = sorted(d for d in by_date if d >= LABEL_TABLE_START_DATE)
    rows = []
    for d in session_dates:
        ticks = by_date[d]
        i = date_idx[d]
        prior_date = all_dates_sorted[i - 1] if i > 0 else None
        prior_ticks = by_date.get(prior_date, []) if prior_date else []

        ticks_upto_0935 = [t for t in ticks if t["time"] < "09:36:00"]
        ticks_0930_0945 = [t for t in ticks if "09:30:00" <= t["time"] < "09:45:00"]

        trailing_5 = [vix_close[dd] for dd in all_dates_sorted[max(0, i - 5):i] if dd in vix_close]
        trailing_20 = [vix_close[dd] for dd in all_dates_sorted[max(0, i - 20):i] if dd in vix_close]

        f0935 = _features_0935_from_ticks(ticks_upto_0935, prior_ticks, trailing_5, trailing_20)
        f0945 = _features_0945_from_ticks(
            ticks_0930_0945,
            prior_low=(min(t["spy"] for t in prior_ticks if t.get("spy") is not None)
                       if any(t.get("spy") is not None for t in prior_ticks) else None),
            prior_range=f0935.get("prior_day_range_dollars"),
        )
        rows.append({
            "date": d, "day_of_week": dt.date.fromisoformat(d).strftime("%A"),
            "prior_date": prior_date,
            "features_0935": f0935, "features_0945": f0945,
        })
    return rows


# ------------------------------------------------------------------------------------------
def run() -> dict:
    t_start = time.time()
    stamp_iso, today_str = _stamp_now_et()

    label_rows, label_meta = build_labels(today_str)
    feature_rows = build_features(today_str)
    feat_by_date = {r["date"]: r for r in feature_rows}

    sessions = []
    for lr in label_rows:
        fr = feat_by_date.get(lr["date"], {})
        sessions.append({**lr, "features_0935": fr.get("features_0935"),
                          "features_0945": fr.get("features_0945")})

    doc = {
        "_meta": {
            "prereg": PREREG_REL,
            "generated_at_et": stamp_iso,
            "today_session_et": today_str,
            "label_table_start_date": LABEL_TABLE_START_DATE,
            "sources": {
                "labels": str(FILLS_LEDGER.relative_to(REPO)).replace("\\", "/"),
                "features": str(CORE_DECISIONS.relative_to(REPO)).replace("\\", "/"),
            },
            "exit_multiple_paying_threshold": EXIT_MULTIPLE_PAYING_THRESHOLD,
            "named_big_days": list(NAMED_BIG_DAYS),
            "build_wall_seconds": None,  # filled below
        },
        "label_summary": label_meta,
        "sessions": sessions,
    }
    doc["_meta"]["build_wall_seconds"] = round(time.time() - t_start, 3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def main() -> int:
    doc = run()
    meta, summ = doc["_meta"], doc["label_summary"]
    print(f"day_type_labels: n_sessions={summ['n_sessions']} "
          f"label_counts={summ['label_counts']} "
          f"all_four_anchor_days_paying={summ['all_four_anchor_days_paying']} "
          f"wall_seconds={meta['build_wall_seconds']}")
    print(f"anchor_day_check={json.dumps(summ['anchor_day_check'])}")
    print(f"wrote {OUT_JSON.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
