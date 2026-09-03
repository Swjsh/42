#!/usr/bin/env python
"""structure_classifier_shadow.py -- EVIDENCE-half of queue item
STRUCTURE-VETO-CLASSIFIER-FIX (the code fix itself is a 2026-10-30 item, per the
CLAUDE.md freeze -- this module ships nothing, flips nothing, only measures).

BACKGROUND. `dissect_structure_veto_misclass.py`
(analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.md) found that
`_classify_sameday_5m` (backtest/lib/engine/engine_cli.py:192-224) calls ONLY
`crypto/lib/market_structure.classify_trend` -- the module's own self-documented
"tentative" fallback -- over `find_swing_points(window=2)` swings, which structurally
cannot confirm the newest two 5m bars (10 minutes) fed to it. The SAME module ships
`walk_structure`, its own self-documented "authoritative" BOS/CHoCH state machine, which
`grep -n "walk_structure" backtest/lib/engine/engine_cli.py setup/scripts/heartbeat_core.py`
finds ZERO live callers of. On 2026-09-03 this produced a `SKIP_STRUCTURE_VETO` "downtrend"
read 11:11-11:35 ET at SPY 770.7-772.9 -- during a continuous 6-point RALLY.

WHAT THIS MODULE DOES. For every core tick (account="safe" -- the ONLY account where
`structure_veto_enabled` is true; `bold` ships an explicit `false` since 2026-08-12 and
NEVER calls the classifier live, confirmed empirically below, zero SKIP_STRUCTURE_VETO
rows for account=bold in the whole ledger) since the veto's own first live fire (found
dynamically from automation/state/core-decisions.jsonl, not hardcoded), for both every
SKIP_STRUCTURE_VETO row AND every ENTER_BULL/ENTER_BEAR row (so the comparison is not
conditioned on vetoes alone):

  1. Rebuilds the SAME-DAY 5m bars available AT THAT TICK -- bars closed strictly before
     the tick, using the tick's own logged `trigger_bar_et` as the inclusive cutoff
     (byte-identical to heartbeat_core.py's own `(date==trig_date) & (ts<=trig_ts)` mask,
     confirmed by direct read, setup/scripts/heartbeat_core.py:993-1004). NO LOOK-AHEAD:
     a synthetic bar placed after the cutoff is proven (test suite) to never change the
     computed label.
       - For dates <= 2026-09-02: REAL continuous-tick 5m bars from the frozen cache
         `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` (verified this build to
         byte-reproduce a live-logged "downtrend" read exactly -- see the module's own
         `_selfcheck()` -- unlike the D7 report's own per-minute-tape proxy, which did NOT
         byte-reproduce it).
       - For dates > 2026-09-02 (today onward -- the cache is a frozen point-in-time
         artifact, never refreshed by this module, no network calls): 5m bars are
         RECONSTRUCTED from the per-minute `spy` tape already logged in
         core-decisions.jsonl, bucketed exactly as `dissect_structure_veto_misclass.py`
         does (open=first sample, close=last, high=max, low=min per 5-min bucket).
         Flagged `bar_source="reconstructed_approx_from_core_decisions"` on every such row
         -- an APPROXIMATION, disclosed, never silently blended with the real-bar rows.
  2. Labels those bars with BOTH classifiers, exactly as production would:
       - `label_live`: the REAL `_classify_sameday_5m` (imported directly from
         `backtest.lib.engine.engine_cli`, never reimplemented -- byte-for-byte fidelity
         by construction, not by promise).
       - `label_walk`: `crypto.lib.market_structure.walk_structure(bars, swings, window=2)`
         -- window=2 is the SAME swing window production already uses for `classify_trend`
         (apples-to-apples on the identical swing set), fed the SAME
         `find_swing_points(window=2, inclusive_right=True)` swings `_classify_sameday_5m`
         itself computes. CONFIRMATION LAG THIS IMPLIES: a swing pivot at bar index i only
         becomes a breakable reference at bar i+window (i+2 => 10 minutes for 5m bars) --
         the identical structural blind spot `classify_trend` has. `walk_structure` ALSO
         requires an actual bar CLOSE beyond that reference to fire a BOS/CHoCH break; if
         price never fully reclaims the pivot, `walk_structure`'s working trend can stay
         `unknown` (or stale) far longer than 10 minutes -- its lag floor is 10 minutes,
         its lag ceiling is unbounded (the rest of the session, if no break ever confirms).
  3. Records the forward SPY move at +30/+60 min in the vetoed/entered side's OWN
     favorable direction (side "C"=bull favorable-up, "P"=bear favorable-down), read from
     the SAME 5m bar source used for the label (never a different tape) -- `None` when
     unavailable (session/data doesn't extend that far forward yet).

OUTPUTS.
  analysis/recommendations/structure-classifier-shadow-ledger.jsonl   append-only,
                                                                       dedup on (account, ts_et)
  analysis/recommendations/structure-classifier-shadow-summary.json  agreement rate,
    favourable-rate splits, bootstrap CIs, today's 11:16/11:21/11:27 rows quoted, the four
    named winning days' walk_structure veto check, forward-window (>=2026-09-03) bar status
    per the FROZEN prereg analysis/recommendations/prereg-structure-classifier-swap-2026-09-03.md

SCOPE / WHAT THIS IS NOT. Read-only on automation/state/**, journal/**,
analysis/quote-tape/**. No network call, no broker call. Never flips
`structure_veto_enabled`, never edits engine_cli.py/params.json/any trading-path file --
only IMPORTS them (explicitly sanctioned: "import them read-only"). This is the EVIDENCE
half of STRUCTURE-VETO-CLASSIFIER-FIX; the classifier swap itself is a separate, later,
2026-10-30 decision gated on this ledger's forward accrual (see the prereg).

COST: $0. Pure local computation over an already-written CSV cache + the existing
core-decisions.jsonl ledger. No pandas/numpy import -- stdlib only (csv, datetime, json).
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --- read-only imports of trading-path / gym modules (CLAUDE.md-sanctioned: "import them
#     read-only") -- never reimplemented, so this module can never silently drift from
#     what production actually runs. --------------------------------------------------
from lib.engine.engine_cli import _classify_sameday_5m, _veto_side  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import walk_structure  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"          # READ-ONLY
SPY_5M_CACHE_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-02.csv"  # READ-ONLY,
                                                                                    # frozen artifact
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "structure-classifier-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "structure-classifier-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-structure-classifier-swap-2026-09-03.md"

ACCOUNT_SCOPE = "safe"          # the ONLY account with structure_veto_enabled=true (fact,
                                 # verified this build: zero SKIP_STRUCTURE_VETO rows exist
                                 # for account="bold" anywhere in the retained ledger)
WINDOW = 2                      # swing window -- matches production's own find_swing_points
                                 # call inside _classify_sameday_5m exactly
WINNER_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
FREEZE_DATE = "2026-09-03"      # this build's own date == the prereg's freeze date; the
                                 # DECISION clock (bar_met/status) only counts ticks dated
                                 # on/after this date -- forward-only, exactly like the
                                 # sibling tp1_r50_forward_shadow.py's ACCRUAL_START_DATE
BAR_FORWARD_SESSIONS = 20       # frozen bar (a): >= 20 forward trading days
BAR_DISAGREEMENT_TICKS = 30     # frozen bar (b): >= 30 forward label_live != label_walk ticks
TODAY_QUOTE_TICKS = ("2026-09-03T11:16:03", "2026-09-03T11:21:03", "2026-09-03T11:27:03")

# All data this module ever touches (2026-07-06 first fire .. forward) sits inside the US
# EDT window (2nd Sun Mar .. 1st Sun Nov 2026) -- confirmed no DST transition is crossed
# before the 2026-10-30 decision date. A single fixed -04:00 offset is used throughout
# rather than a full DST-aware conversion (out of scope for a single-season shadow); this
# assumption is stated once, here, rather than re-derived silently downstream.
_ET_FIXED_TZ = timezone(timedelta(hours=-4))
_TZ_SUFFIX_RE = re.compile(r"[+-]\d{2}:\d{2}$")


def _is_rth(ts: datetime) -> bool:
    """RTH = 09:30 <= t < 16:00 ET (matches heartbeat_core.py:903's own RTH filter)."""
    hm = (ts.hour, ts.minute)
    return (9, 30) <= hm < (16, 0)


# ------------------------------------------------------------------------------------------
# timestamp helpers -- everything internal is a NAIVE ET wall-clock datetime (matches the
# established convention in backtest/tools/dissect_structure_veto_misclass.py, which strips
# offsets rather than reasoning cross-timezone); tz-aware only at the Bar()/payload boundary.
# ------------------------------------------------------------------------------------------
def _parse_et_naive(s: str | None) -> datetime | None:
    if not s:
        return None
    s = _TZ_SUFFIX_RE.sub("", s.strip())
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _iso_with_offset(dt_naive: datetime) -> str:
    return dt_naive.isoformat() + "-04:00"


# ------------------------------------------------------------------------------------------
# ledger I/O (torn-last-line tolerant, same contract as every sibling shadow ledger)
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


# ------------------------------------------------------------------------------------------
# spy_5m CSV cache -- real continuous-tick bars, 2026-05-19..2026-09-02 (frozen, read-only)
# ------------------------------------------------------------------------------------------
def load_spy_5m_cache() -> dict[str, list[dict]]:
    """date_et -> RTH-only (09:30<=t<16:00) bar dicts, sorted ascending, `ts` naive ET."""
    by_date: dict[str, list[dict]] = {}
    if not SPY_5M_CACHE_CSV.exists():
        return by_date
    with SPY_5M_CACHE_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ts = _parse_et_naive(row["timestamp_et"])
            if ts is None or not _is_rth(ts):
                continue
            date_et = ts.strftime("%Y-%m-%d")
            by_date.setdefault(date_et, []).append({
                "ts": ts, "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    for date_et in by_date:
        by_date[date_et].sort(key=lambda b: b["ts"])
    return by_date


def reconstruct_5m_bars_for_date(date_et: str) -> list[dict]:
    """APPROXIMATE: bucket the per-minute `spy` tape logged in core-decisions.jsonl into 5m
    OHLC, identical method to dissect_structure_veto_misclass.py's `bucket_5m` (open=first
    sample, close=last, high=max, low=min per bucket; bucket key = 5-min floor, matching the
    observed bar-label-is-interval-start convention). Used ONLY for dates the frozen CSV
    cache does not cover (2026-09-03 onward) -- never for dates the cache already has.
    """
    buckets: dict[datetime, list[tuple[datetime, float]]] = {}
    if not CORE_DECISIONS.exists():
        return []
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("account") != ACCOUNT_SCOPE:
                continue
            ts_et = d.get("ts_et")
            if not ts_et or not ts_et.startswith(date_et):
                continue
            spy = d.get("spy")
            if spy is None:
                continue
            ts = _parse_et_naive(ts_et)
            if ts is None:
                continue
            floor_min = (ts.minute // 5) * 5
            bkey = ts.replace(minute=floor_min, second=0, microsecond=0)
            buckets.setdefault(bkey, []).append((ts, float(spy)))
    bars = []
    for bkey in sorted(buckets):
        if not _is_rth(bkey):
            continue
        samples = sorted(buckets[bkey], key=lambda x: x[0])
        prices = [p for _, p in samples]
        bars.append({"ts": bkey, "open": prices[0], "high": max(prices), "low": min(prices),
                     "close": prices[-1], "volume": 0.0})
    return bars


def bars_for_date(date_et: str, cache: dict[str, list[dict]],
                   memo: dict[str, tuple[list[dict], str]]) -> tuple[list[dict], str]:
    """Returns (full_day_bars, bar_source). Memoized per run -- each date's bars are built
    at most once even though many ticks share a date."""
    if date_et in memo:
        return memo[date_et]
    if date_et in cache:
        result = (cache[date_et], "csv_cache_real")
    else:
        result = (reconstruct_5m_bars_for_date(date_et), "reconstructed_approx_from_core_decisions")
    memo[date_et] = result
    return result


# ------------------------------------------------------------------------------------------
# classification -- label_live (byte-for-byte production import) + label_walk (authoritative,
# not called anywhere live)
# ------------------------------------------------------------------------------------------
def _to_bar_objects(bars_upto: list[dict]) -> list[Bar]:
    return [Bar(open_time=b["ts"].replace(tzinfo=_ET_FIXED_TZ), open=b["open"], high=b["high"],
                low=b["low"], close=b["close"], volume=b["volume"], granularity_seconds=300,
                source="structure_classifier_shadow") for b in bars_upto]


def classify_both(bars_upto: list[dict]) -> dict:
    """bars_upto MUST already be capped to <= cutoff (no look-ahead) -- caller's job."""
    payload = [{"open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"],
                "volume": b["volume"], "timestamp_iso": _iso_with_offset(b["ts"])}
               for b in bars_upto]
    label_live = _classify_sameday_5m(payload)          # the REAL production function

    bar_objs = _to_bar_objects(bars_upto)
    swings = find_swing_points(bar_objs, window=WINDOW, inclusive_right=True)
    label_walk, events = walk_structure(bar_objs, swings, window=WINDOW)
    return {"label_live": label_live, "label_walk": label_walk,
            "n_bars_fed": len(bars_upto), "n_walk_events": len(events)}


# ------------------------------------------------------------------------------------------
# forward move -- from the SAME 5m bar source, deliberately UNCAPPED (this is the one place
# look-ahead is intentional and required)
# ------------------------------------------------------------------------------------------
def forward_close_at_or_after(bars_full: list[dict], target: datetime) -> float | None:
    for b in bars_full:                       # bars_full is sorted ascending
        if b["ts"] >= target:
            return b["close"]
    return None


def _favorable(side: str | None, move: float | None) -> bool | None:
    if move is None or side not in ("C", "P"):
        return None
    return (move > 0) if side == "C" else (move < 0)


# ------------------------------------------------------------------------------------------
# core-decisions.jsonl scan -- ONE pass collects the scored population + the veto's own
# first live fire date (found, not hardcoded)
# ------------------------------------------------------------------------------------------
SCORED_VERDICTS = frozenset({"SKIP_STRUCTURE_VETO", "ENTER_BULL", "ENTER_BEAR"})


def scan_population() -> tuple[list[dict], str | None]:
    if not CORE_DECISIONS.exists():
        return [], None
    rows: list[dict] = []
    first_fire_ts: str | None = None
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("account") != ACCOUNT_SCOPE:
                continue
            verdict = d.get("verdict")
            if verdict not in SCORED_VERDICTS:
                continue
            ts_et = d.get("ts_et")
            if not ts_et:
                continue
            if verdict == "SKIP_STRUCTURE_VETO" and (first_fire_ts is None or ts_et < first_fire_ts):
                first_fire_ts = ts_et
            # NOTE ON SCHEMA (found this build, not assumed): core-decisions.jsonl's own
            # "action" field is a DOWNSTREAM order-dispatch outcome (NOT_FLAT / PLACED /
            # VETOED_BY_MODELS / RISK_DENY_* / SKIP_LATE_ENTRY / ...), NOT the same thing as
            # "verdict" (SKIP_STRUCTURE_VETO / ENTER_BULL / ENTER_BEAR / HOLD / ...) except by
            # coincidence on SKIP_STRUCTURE_VETO rows (where the two happen to be equal). This
            # ledger's own "action" column is therefore the VERDICT (the classification this
            # whole shadow is about) -- the raw downstream field is kept separately, verbatim,
            # as "execution_action_raw" so nothing is silently dropped.
            rows.append({
                "ts_et": ts_et, "account": d.get("account"),
                "action": verdict, "execution_action_raw": d.get("action"),
                "side": d.get("side"), "spy": d.get("spy"),
                "setup": d.get("setup"),
                "trigger_bar_et": d.get("trigger_bar_et"),
                "structure_reason_logged": ((d.get("conviction") or {}).get("structure_reason")),
            })
    rows.sort(key=lambda r: r["ts_et"])
    return rows, first_fire_ts


# ------------------------------------------------------------------------------------------
# per-tick row builder
# ------------------------------------------------------------------------------------------
def build_row(cand: dict, cache: dict[str, list[dict]], memo: dict) -> dict | None:
    ts_naive = _parse_et_naive(cand["ts_et"])
    if ts_naive is None:
        return None
    date_et = ts_naive.strftime("%Y-%m-%d")
    cutoff = _parse_et_naive(cand.get("trigger_bar_et")) or ts_naive
    bars_full, bar_source = bars_for_date(date_et, cache, memo)
    bars_upto = [b for b in bars_full if b["ts"] <= cutoff]

    cl = classify_both(bars_upto)
    side = cand.get("side")
    entry_spy = cand.get("spy")

    fwd30_close = forward_close_at_or_after(bars_full, cutoff + timedelta(minutes=30))
    fwd60_close = forward_close_at_or_after(bars_full, cutoff + timedelta(minutes=60))
    move30 = (round(fwd30_close - entry_spy, 4)
              if (fwd30_close is not None and entry_spy is not None) else None)
    move60 = (round(fwd60_close - entry_spy, 4)
              if (fwd60_close is not None and entry_spy is not None) else None)

    walk_would_veto = _veto_side(side, cl["label_walk"])
    live_would_veto_now = _veto_side(side, cl["label_live"])

    return {
        "ts_et": cand["ts_et"], "date_et": date_et, "account": cand["account"],
        "action": cand["action"], "execution_action_raw": cand.get("execution_action_raw"),
        "side": side, "spy": entry_spy, "setup": cand.get("setup"),
        "trigger_bar_et": cand.get("trigger_bar_et"),
        "bar_source": bar_source, "n_bars_fed": cl["n_bars_fed"],
        "label_live": cl["label_live"], "label_walk": cl["label_walk"],
        "n_walk_events": cl["n_walk_events"],
        "agree": (cl["label_live"] == cl["label_walk"]),
        "structure_reason_logged": cand.get("structure_reason_logged"),
        "live_label_matches_logged": (
            (cl["label_live"] == cand["structure_reason_logged"])
            if cand.get("structure_reason_logged") else None),
        "live_would_veto_recomputed": live_would_veto_now,
        "walk_would_veto": walk_would_veto,
        "fwd_move_30m": move30, "fwd_move_60m": move60,
        "favorable_30m": _favorable(side, move30),
        "favorable_60m": _favorable(side, move60),
    }


# ------------------------------------------------------------------------------------------
# bootstrap helpers
# ------------------------------------------------------------------------------------------
def _bootstrap_rate_ci(binary: list[float], n_boot: int = 5000, seed: int = 20260903) -> dict | None:
    n = len(binary)
    if n == 0:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        means.append(sum(binary[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[min(int(0.975 * n_boot), n_boot - 1)]
    return {"n": n, "rate": round(sum(binary) / n, 4),
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def _bootstrap_rate_diff_ci(group_a: list[float], group_b: list[float],
                             n_boot: int = 5000, seed: int = 20260903) -> dict | None:
    """CI on rate(group_a) - rate(group_b), independent resampling each group."""
    if not group_a or not group_b:
        return None
    rng = random.Random(seed)
    na, nb = len(group_a), len(group_b)
    diffs = []
    for _ in range(n_boot):
        ra = sum(group_a[rng.randrange(na)] for _ in range(na)) / na
        rb = sum(group_b[rng.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(ra - rb)
    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[min(int(0.975 * n_boot), n_boot - 1)]
    return {"n_a": na, "n_b": nb, "rate_a": round(sum(group_a) / na, 4),
            "rate_b": round(sum(group_b) / nb, 4),
            "diff": round(sum(group_a) / na - sum(group_b) / nb, 4),
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


# ------------------------------------------------------------------------------------------
# summary
# ------------------------------------------------------------------------------------------
def _summarize(rows: list[dict], first_fire_ts: str | None) -> dict:
    n = len(rows)
    if n == 0:
        return {"prereg": PREREG_REL, "generated_at_et": _stamp_now_et(),
                "account_scope": ACCOUNT_SCOPE, "veto_first_fire_et": first_fire_ts,
                "n_ticks": 0, "status": "ACCRUING",
                "note": "No qualifying ticks yet -- core-decisions.jsonl empty or unreadable."}

    n_agree = sum(1 for r in rows if r["agree"])
    by_action: dict[str, dict] = {}
    for action in ("SKIP_STRUCTURE_VETO", "ENTER_BULL", "ENTER_BEAR"):
        subset = [r for r in rows if r["action"] == action]
        by_action[action] = {
            "n": len(subset),
            "agreement_rate": (round(sum(1 for r in subset if r["agree"]) / len(subset), 4)
                                if subset else None),
        }

    # Group A: live actually vetoed. veto_correct = NOT favorable (favorable => veto was wrong).
    group_a = [r for r in rows if r["action"] == "SKIP_STRUCTURE_VETO"]
    group_a_30 = [r for r in group_a if r["favorable_30m"] is not None]
    group_a_60 = [r for r in group_a if r["favorable_60m"] is not None]
    group_a_agree_30 = [r for r in group_a_30 if r["agree"]]
    group_a_disagree_30 = [r for r in group_a_30 if not r["agree"]]
    group_a_agree_60 = [r for r in group_a_60 if r["agree"]]
    group_a_disagree_60 = [r for r in group_a_60 if not r["agree"]]

    # Group B: walk WOULD veto but live did NOT (only walk_structure would have blocked).
    group_b = [r for r in rows if r["action"] in ("ENTER_BULL", "ENTER_BEAR") and r["walk_would_veto"]]
    group_b_30 = [r for r in group_b if r["favorable_30m"] is not None]
    group_b_60 = [r for r in group_b if r["favorable_60m"] is not None]

    def fav_list(subset, key):
        return [1.0 if r[key] else 0.0 for r in subset]

    def correct_list(subset, key):  # veto-correct = NOT favorable to the blocked/entered side
        return [0.0 if r[key] else 1.0 for r in subset]

    live_veto_episodes = {
        "n": len(group_a),
        "favorable_rate_30m": _bootstrap_rate_ci(fav_list(group_a_30, "favorable_30m")),
        "favorable_rate_60m": _bootstrap_rate_ci(fav_list(group_a_60, "favorable_60m")),
        "veto_correct_rate_30m": _bootstrap_rate_ci(correct_list(group_a_30, "favorable_30m")),
        "veto_correct_rate_60m": _bootstrap_rate_ci(correct_list(group_a_60, "favorable_60m")),
        "split_by_walk_agreement": {
            "walk_also_would_veto_favorable_rate_30m": _bootstrap_rate_ci(
                fav_list(group_a_agree_30, "favorable_30m")),
            "walk_disagreed_favorable_rate_30m": _bootstrap_rate_ci(
                fav_list(group_a_disagree_30, "favorable_30m")),
            "favorable_rate_diff_ci_30m_agree_minus_disagree": _bootstrap_rate_diff_ci(
                fav_list(group_a_agree_30, "favorable_30m"),
                fav_list(group_a_disagree_30, "favorable_30m")),
            "walk_also_would_veto_favorable_rate_60m": _bootstrap_rate_ci(
                fav_list(group_a_agree_60, "favorable_60m")),
            "walk_disagreed_favorable_rate_60m": _bootstrap_rate_ci(
                fav_list(group_a_disagree_60, "favorable_60m")),
            "favorable_rate_diff_ci_60m_agree_minus_disagree": _bootstrap_rate_diff_ci(
                fav_list(group_a_agree_60, "favorable_60m"),
                fav_list(group_a_disagree_60, "favorable_60m")),
        },
    }
    walk_only_veto_episodes = {
        "n": len(group_b),
        "note": ("ENTER_* ticks the LIVE classifier did NOT block but walk_structure's label "
                 "on the identical bars would have -- the trade was actually taken; "
                 "favorable_rate here = rate the taken trade would have WON (i.e. a "
                 "walk_structure veto at that tick would have been WRONG to fire)."),
        "favorable_rate_30m": _bootstrap_rate_ci(fav_list(group_b_30, "favorable_30m")),
        "favorable_rate_60m": _bootstrap_rate_ci(fav_list(group_b_60, "favorable_60m")),
        "veto_correct_rate_30m": _bootstrap_rate_ci(correct_list(group_b_30, "favorable_30m")),
        "veto_correct_rate_60m": _bootstrap_rate_ci(correct_list(group_b_60, "favorable_60m")),
    }

    # Reconstruction fidelity -- ONLY rows carrying a logged `conviction.structure_reason`
    # (a heartbeat_core.py._sameday_structure_diag diagnostic, a SEPARATE call into the SAME
    # _classify_sameday_5m -- rolled out ~2026-08-19, absent on older rows) can be
    # cross-checked at all. `structure_reason_logged` carries MORE detail than this ledger's
    # own `label_live` can ever reproduce: `_classify_sameday_5m` itself only ever returns
    # {'uptrend','downtrend','range','unknown'}, but the live diagnostic decomposes 'unknown'
    # into 'unknown:insufficient_bars' / 'unknown:classifier' AND can log 'error:<ExcType>...'
    # when ITS OWN import path fails at runtime (a REAL, now-fixed live scar -- confirmed this
    # build: every 'error:ModuleNotFoundError' logged value falls on 2026-08-19, the exact
    # date heartbeat_core.py's own top-of-file comment documents that import bug). Neither of
    # those two cases is a fair test of THIS module's reconstruction, so they are counted and
    # EXCLUDED from `comparable_match_rate` rather than silently blended into it (OP-33) --
    # `exact_match_rate` (the raw string-equality number) is also kept for full transparency.
    fidelity: dict[str, dict] = {}
    for src in ("csv_cache_real", "reconstructed_approx_from_core_decisions"):
        checkable = [r for r in rows if r["bar_source"] == src and r.get("structure_reason_logged")]
        exact = sum(1 for r in checkable if r.get("live_label_matches_logged"))

        def _is_excluded(r):
            return str(r["structure_reason_logged"]).startswith(("error:", "unknown:"))

        comparable = [r for r in checkable if not _is_excluded(r)]
        excluded = [r for r in checkable if _is_excluded(r)]
        comparable_match = sum(
            1 for r in comparable if r["label_live"] == r["structure_reason_logged"])
        fidelity[src] = {
            "n_with_a_logged_value_to_check": len(checkable),
            "n_exact_byte_match": exact,
            "exact_match_rate": (round(exact / len(checkable), 4) if checkable else None),
            "n_excluded_error_or_unknown_variant": len(excluded),
            "n_comparable": len(comparable),
            "n_comparable_match": comparable_match,
            "comparable_match_rate": (round(comparable_match / len(comparable), 4)
                                       if comparable else None),
        }

    # Today's quoted rows (task-specified exact ticks)
    today_rows = [r for r in rows if r["ts_et"] in TODAY_QUOTE_TICKS]

    # Four named winning days -- would walk_structure have vetoed any entry?
    winner_day_check = {}
    for wd in WINNER_DAYS:
        day_entries = [r for r in rows if r["date_et"] == wd
                       and r["action"] in ("ENTER_BULL", "ENTER_BEAR")]
        vetoed_by_walk = [r for r in day_entries if r["walk_would_veto"]]
        winner_day_check[wd] = {
            "n_entries": len(day_entries),
            "n_would_be_vetoed_by_walk": len(vetoed_by_walk),
            "vetoed_ticks": [r["ts_et"] for r in vetoed_by_walk],
        }
    any_winner_day_vetoed = any(v["n_would_be_vetoed_by_walk"] > 0 for v in winner_day_check.values())

    # ---- FORWARD (>= FREEZE_DATE) decision clock -- the frozen prereg's own population ----
    fwd_rows = [r for r in rows if r["date_et"] >= FREEZE_DATE]
    fwd_days = sorted({r["date_et"] for r in fwd_rows})
    fwd_disagree = [r for r in fwd_rows if not r["agree"]]
    fwd_group_a = [r for r in fwd_rows if r["action"] == "SKIP_STRUCTURE_VETO"]
    fwd_group_b = [r for r in fwd_rows if r["action"] in ("ENTER_BULL", "ENTER_BEAR")
                   and r["walk_would_veto"]]
    fwd_live_correct_30 = correct_list([r for r in fwd_group_a if r["favorable_30m"] is not None],
                                        "favorable_30m")
    fwd_walk_correct_30 = correct_list([r for r in fwd_group_b if r["favorable_30m"] is not None],
                                        "favorable_30m")
    bar_met = (len(fwd_days) >= BAR_FORWARD_SESSIONS) and (len(fwd_disagree) >= BAR_DISAGREEMENT_TICKS)
    forward_clock = {
        "freeze_date": FREEZE_DATE,
        "forward_sessions_accrued": len(fwd_days),
        "forward_sessions_to_bar": max(0, BAR_FORWARD_SESSIONS - len(fwd_days)),
        "forward_disagreement_ticks": len(fwd_disagree),
        "forward_disagreement_ticks_to_bar": max(0, BAR_DISAGREEMENT_TICKS - len(fwd_disagree)),
        "bar_met": bar_met,
        "live_veto_correct_rate_30m": _bootstrap_rate_ci(fwd_live_correct_30),
        "walk_veto_correct_rate_30m": _bootstrap_rate_ci(fwd_walk_correct_30),
        "decision_rule": (
            "Ships (10-30 swap eligible) only if bar_met AND "
            "walk_veto_correct_rate_30m.ci_lower_2.5 > live_veto_correct_rate_30m.ci_lower_2.5 "
            "AND zero winning-day entries vetoed by walk (see winner_day_check) -- see "
            f"{PREREG_REL} for the frozen, non-softenable full rule + falsifier."),
    }

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "account_scope": ACCOUNT_SCOPE,
        "veto_first_fire_et": first_fire_ts,
        "n_ticks": n,
        "n_skip_structure_veto": by_action["SKIP_STRUCTURE_VETO"]["n"],
        "n_enter_bull": by_action["ENTER_BULL"]["n"],
        "n_enter_bear": by_action["ENTER_BEAR"]["n"],
        "agreement_rate_overall": round(n_agree / n, 4),
        "agreement_rate_by_action": by_action,
        "reconstruction_fidelity_by_bar_source": fidelity,
        "live_veto_episodes": live_veto_episodes,
        "walk_only_veto_episodes": walk_only_veto_episodes,
        "today_quoted_rows": today_rows,
        "winner_day_check": winner_day_check,
        "any_winner_day_entry_would_be_vetoed_by_walk": any_winner_day_vetoed,
        "forward_decision_clock": forward_clock,
        "status": "BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING",
    }


# ------------------------------------------------------------------------------------------
# self-check -- proves the CSV-cache reconstruction path byte-reproduces a real logged
# "downtrend" verdict before this module ever trusts it for the ledger (cheap, run every
# invocation; a failure here means the cache/import wiring drifted and MUST be surfaced,
# never silently ignored -- OP-33).
# ------------------------------------------------------------------------------------------
def _selfcheck(cache: dict[str, list[dict]]) -> dict:
    date_et, cutoff_iso, expected = "2026-08-21", "2026-08-21T13:25:00", "downtrend"
    bars_full = cache.get(date_et, [])
    cutoff = _parse_et_naive(cutoff_iso)
    bars_upto = [b for b in bars_full if b["ts"] <= cutoff]
    if not bars_upto:
        return {"ok": False, "reason": f"no cached bars for {date_et} -- cache missing/stale"}
    got = classify_both(bars_upto)["label_live"]
    return {"ok": (got == expected), "expected": expected, "got": got,
            "n_bars": len(bars_upto), "date_et": date_et, "cutoff": cutoff_iso}


# ------------------------------------------------------------------------------------------
def run() -> dict:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        cache = load_spy_5m_cache()
        selfcheck = _selfcheck(cache)
        if not selfcheck["ok"]:
            return {"error": "SELFCHECK_FAILED", "selfcheck": selfcheck, "prereg": PREREG_REL}

        candidates, first_fire_ts = scan_population()
        if first_fire_ts is None:
            return {"error": "NO_SKIP_STRUCTURE_VETO_ROWS_FOUND -- cannot anchor the clock's "
                              "start; core-decisions.jsonl may be empty/rotated",
                     "prereg": PREREG_REL}
        population = [c for c in candidates if c["ts_et"] >= first_fire_ts]

        existing = _read_ledger()
        seen = {(r.get("account"), r.get("ts_et")) for r in existing}
        todo = [c for c in population if (c["account"], c["ts_et"]) not in seen]

        memo: dict[str, tuple[list[dict], str]] = {}
        appended: list[dict] = []
        for cand in todo:
            row = build_row(cand, cache, memo)
            if row is not None:
                appended.append(row)

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        all_rows = existing + appended
        summary = _summarize(all_rows, first_fire_ts)
        summary["new_this_run"] = len(appended)
        summary["selfcheck"] = selfcheck
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal (fail-open)
        return {"error": f"{type(e).__name__}: {e}"[:500], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
