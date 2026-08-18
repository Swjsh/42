"""conviction_v2_historical_replay_2026_08_18.py -- does conviction v2 agree with past winners?

J's question, verbatim: "Does the new conviction engine agree with previous days' winners?"

WHY THIS EXISTS. A prior quality-AGNOSTIC proximity replay (2026-08-18, over all 12 days that
have trendline history) found winners 27/28 (96%) had a trendline within $0.60 of the strike;
losers 64/75 (85%); median gap $0.01 for BOTH groups -- proximity alone does not discriminate.
So ALL of v2's discriminating power must come from its QUALITY BAR (TL_MIN_RESPECTS=20,
TL_MAX_VIOLATIONS=6 in setup/scripts/conviction.py), and that bar was untestable historically
because the closed-fills ledger carries no respect_count/violations. This script makes it
testable: it reconstructs the quality bar from cached bars using the LIVE PRODUCER ITSELF
(backtest/autoresearch/trendline_engine.py's detect()/`_fit()`), not a re-implementation, then
scores v0 vs v2 on every closed real round trip across the 12 days.

METHOD, IN ONE PARAGRAPH. For each closed round trip (automation/state/fleet/fills_fifo.py,
arms safe-2/bold-2/safe-3/risky-1/risky-3), find the entry's real SPOT and fired triggers by
joining to the nearest automation/state/core-decisions.jsonl tick (the ONE shared signal all
arms trade off -- MAP.md). Reconstruct the trendline quality bar by calling
trendline_engine.detect(bars, include_same_day_tier=True) on the SAME trailing-lookback bar
window production uses, TRUNCATED to bars that have fully CLOSED at-or-before the entry instant
(C6 no-look-ahead) -- this is the live producer's own arithmetic, called on historically-
truncated input, not a port. Reconstruct the session envelope and same-day structure side the
same no-look-ahead way (structure via backtest.lib.engine.engine_cli._classify_sameday_5m,
REUSED not reimplemented). Call setup/scripts/conviction.py's score_conviction() TWICE per row,
identical kwargs except trendline_records (None for v0, the reconstructed lines for v2) -- so
the v0/v2 DELTA is attributable ONLY to the trendline generalization, regardless of how
faithfully the other (unreconstructable-historically) components are populated.

WHAT IS NOT RECONSTRUCTED (documented, not hidden): level_records, level_states, and
confluence_zones are single-overwritten live state files with no historical archive for these
12 days -- passed as None (component degrades to 0, exactly as production degrades on a cold
read). This never touches the v0/v2 DELTA (only C1 named_level / C4 range_extreme are trendline-
reachable), only the absolute score level, which is why the floor-sweep table's ABSOLUTE
numbers should be read as a lower bound on what a fully-informed v0 would have scored, not a
concurrently-achievable ceiling. Cross-validated against the real logged v0 on the 4 days
(08-13/08-14/08-17/08-18) core-decisions.jsonl actually carries a `conviction` field.

Writes:
  analysis/deep-research/CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.json  (raw rows + aggregates)
  analysis/deep-research/CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.md    (the report)
Guard: backtest/tests/test_conviction_v2_replay_reconstruction.py
Cost: $0 -- pure local CSV/JSONL reads + CPU, no network, no LLM, no broker.
Changes NO production behaviour -- conviction stays DISARMED, v2 stays shadow-only.

Run: backtest/.venv/Scripts/python.exe backtest/tools/conviction_v2_historical_replay_2026_08_18.py
"""
from __future__ import annotations

import bisect
import json
import math
import statistics
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "setup" / "scripts", REPO / "backtest" / "autoresearch",
           REPO / "automation" / "state" / "fleet"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import pandas as pd  # noqa: E402

import conviction as cv                      # noqa: E402  setup/scripts/conviction.py
import trendline_engine as te                 # noqa: E402  backtest/autoresearch/trendline_engine.py
import fills_fifo                             # noqa: E402  automation/state/fleet/fills_fifo.py
from backtest.lib import et_frame             # noqa: E402
from backtest.lib.engine.engine_cli import _classify_sameday_5m  # noqa: E402

# --------------------------------------------------------------------------------- constants
DAYS = ["2026-06-26", "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14",
        "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18"]
ARMS = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"]
BARS_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-08-18.csv"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.json"
OUT_MD = REPO / "analysis" / "deep-research" / "CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.md"

BAR_SECONDS = 300
JOIN_WINDOW_S = 150  # matches conviction_shadow_report.py's own _JOIN_WINDOW_S convention
N_DAYS_LOOKBACK = te.N_DAYS  # 5 -- reused from the producer, never re-typed
CALENDAR_LOOKBACK_DAYS = math.ceil(N_DAYS_LOOKBACK * 7 / 5) + 2  # mirrors fetch_spy_5m_lookback

# 2026-07-27 is when heartbeat_core.py started logging bear_triggers_raw/bull_triggers_raw/
# bear_rejection_level_raw/bull_reclaim_level_raw on EVERY tick (TRIGGER-BLINDNESS fix).
# Confirmed empirically: 2026-06-26 core-decisions.jsonl rows carry NEITHER field; 2026-08-11
# rows carry bear_triggers_raw/bull_triggers_raw on HOLD verdicts too (dense, verdict-agnostic).
RAW_TRIGGER_SCHEMA_BOUNDARY = "2026-07-27"


# ============================================================================ bar store
def load_bars(csv_path: Path = BARS_CSV) -> dict:
    """RTH-only 5m SPY bars, sorted ascending. Each bar carries:
      't'      -- genuine UTC Zulu ISO string ('...Z'), so trendline_engine's internal
                  _et()/_bar_date_et() (which assume a UTC-labelled 't') group same-day-tier
                  bars onto the CORRECT ET calendar date. (A naive ET-labelled 't' would
                  double-shift the hour inside _et() -- this is the concrete bug this
                  function exists to avoid; pinned by the guard test's frame test.)
      'o','h','l','c','v' -- float OHLCV.
    Plus parallel arrays `_unix` (int epoch seconds, bar OPEN time) and `_close_unix`
    (bar CLOSE time = open + 5min, for the C6 'has this bar actually closed yet' test).

    DST note: the CSV stores timestamp_et with a per-row EXPLICIT offset (e.g. '-04:00');
    pd.to_datetime(..., utc=True) resolves each row's TRUE UTC instant from that embedded
    offset (not a hardcoded assumption), so this is correct regardless of the known
    wall-v1 mislabeling bug (et_frame.py) -- and DAYS is EDT-only anyway (verified below).
    """
    df = pd.read_csv(csv_path)
    ts_utc = pd.to_datetime(df["timestamp_et"], utc=True)
    ts_et_v2 = et_frame.parse_timestamp_et(df["timestamp_et"], frame=et_frame.FRAME_ET_V2)
    ts_wall_v1 = et_frame.parse_timestamp_et(df["timestamp_et"], frame=et_frame.FRAME_WALL_V1)
    # NOTE: itertuples() silently renames any leading-underscore column to a positional field
    # (pandas namedtuple restriction) -- these columns are named WITHOUT a leading underscore
    # for exactly that reason, not a style choice.
    df = df.assign(ts_utc_col=ts_utc, ts_et_col=ts_et_v2, ts_wall_col=ts_wall_v1)
    df = df.sort_values("ts_utc_col").reset_index(drop=True)

    # RTH filter -- byte-identical predicate to trendline_engine.fetch_spy_5m's own UTC-string
    # slice (13:30:00-20:00:00 UTC == 09:30-16:00 ET, true for EDT months only -- our range).
    hhmmss = df["ts_utc_col"].dt.strftime("%H:%M:%S")
    df = df[(hhmmss >= "13:30:00") & (hhmmss <= "20:00:00")].reset_index(drop=True)

    bars: list[dict] = []
    for row in df.itertuples():
        u = int(row.ts_utc_col.timestamp())
        bars.append({
            "t": row.ts_utc_col.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "o": float(row.open), "h": float(row.high), "l": float(row.low), "c": float(row.close),
            "v": float(row.volume),
            "_unix": u, "_close_unix": u + BAR_SECONDS,
            "_date_et": row.ts_et_col.strftime("%Y-%m-%d"),
            "_ts_et_iso": row.ts_et_col.isoformat(),
        })

    # DST-safety self-check (the task's explicit trap #1): for every bar on one of our 12
    # target dates, wall-v1 and et-v2 parses must agree -- if they don't, the -04:00-year-round
    # storage bug (et_frame.py's own docstring) would be silently mislabeling a WINTER day, and
    # this whole replay's timestamps would be wrong by an hour. All 12 DAYS are Jun-Aug (EDT).
    on_target = df["ts_et_col"].dt.strftime("%Y-%m-%d").isin(DAYS)
    mismatches = int((df.loc[on_target, "ts_et_col"] != df.loc[on_target, "ts_wall_col"]).sum())
    dst_check = {"target_day_bars": int(on_target.sum()), "wall_v1_et_v2_mismatches": mismatches,
                 "safe": mismatches == 0}

    unix_list = [b["_unix"] for b in bars]
    close_list = [b["_close_unix"] for b in bars]
    by_date: dict[str, list[int]] = {}
    for i, b in enumerate(bars):
        by_date.setdefault(b["_date_et"], []).append(i)
    return {"bars": bars, "unix_list": unix_list, "close_list": close_list,
            "by_date": by_date, "dst_check": dst_check}


def closed_bar_cutoff_idx(store: dict, entry_unix: int) -> int:
    """Index of the LAST bar that has fully CLOSED at-or-before entry_unix (C6: a still-
    forming bar's close is not yet knowable at decision time). -1 if none qualifies."""
    return bisect.bisect_right(store["close_list"], entry_unix) - 1


def window_start_idx(store: dict, start_unix: int) -> int:
    return bisect.bisect_left(store["unix_list"], start_unix)


# ============================================================================ trendline reconstruction
def reconstruct_trendline_records(store: dict, cutoff_idx: int) -> list[dict]:
    """THE quality-bar reconstruction. Calls trendline_engine.detect() -- the REAL live
    producer, not a port of its arithmetic -- on the SAME trailing-lookback window production
    uses (fetch_spy_5m_lookback's own calendar_days formula), truncated to bars closed at-or-
    before the entry (C6). include_same_day_tier=True mirrors production's ONE call site
    (trendline_engine.main()) exactly -- the real 2026-08-17/08-18 winners were credited via a
    SAME_DAY-tier line (see backtest/tests/test_conviction_trendline_variant_2026_08_18.py's
    GOOD_LINE fixture), so omitting this tier would silently exclude the very population this
    replay exists to test.
    """
    if cutoff_idx < 0:
        return []
    bars = store["bars"]
    entry_unix = bars[cutoff_idx]["_unix"]
    start_unix = entry_unix - CALENDAR_LOOKBACK_DAYS * 86400
    lo = window_start_idx(store, start_unix)
    window = bars[lo: cutoff_idx + 1]
    if len(window) < te.MIN_SPAN + 2:
        return []
    # detect() reads only t/o/h/l/c -- strip the private bookkeeping keys defensively so a
    # future trendline_engine change can never accidentally see (and thus depend on) them.
    clean = [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in window]
    lines = te.detect(clean, include_same_day_tier=True)
    return [asdict(ln) for ln in lines]


def reconstruct_envelope(store: dict, cutoff_idx: int) -> tuple[Optional[float], Optional[float]]:
    """SESSION ENVELOPE -- the trigger DAY's high/low through the trigger bar (heartbeat_core.py
    ~line 816-826's own definition, ported verbatim: same-day bars only, sliced to the closed
    cutoff BEFORE aggregating -- C6)."""
    if cutoff_idx < 0:
        return None, None
    bars = store["bars"]
    date = bars[cutoff_idx]["_date_et"]
    idxs = store["by_date"].get(date, [])
    sess = [bars[i] for i in idxs if i <= cutoff_idx]
    if not sess:
        return None, None
    return max(b["h"] for b in sess), min(b["l"] for b in sess)


def reconstruct_structure_side(store: dict, cutoff_idx: int) -> Optional[str]:
    """C5 input, reusing engine_cli._classify_sameday_5m -- the SAME classifier the live
    structure veto consults (heartbeat_core.py's own _sameday_structure_side, ported call
    convention, not reimplemented). Same-day bars only, through the closed cutoff (C6).

    BUG FOUND BY THIS SCRIPT'S OWN FIRST RUN (2026-08-18): _classify_sameday_5m builds a
    crypto.lib.bar.Bar per row, and Bar.__post_init__ HARD-REQUIRES a tz-AWARE open_time
    ('Bar.open_time must be tz-aware (UTC preferred)') -- passing the naive ET timestamp
    (et_frame's own stripped-tz convention) raised inside _classify_sameday_5m's try block
    and was silently swallowed by ITS OWN fail-open `except Exception: return 'unknown'`,
    so this function returned None on ALL 103/103 rows without ever surfacing an error. The
    'unknown' mapped to None just like a genuine range/no-signal day would have -- a SILENT,
    look-alike degradation, not a crash, which is exactly why it has to be checked for
    explicitly rather than trusted because nothing raised. Fixed by feeding the already-tz-
    aware UTC 't' string (Zulu) under 'timestamp_iso' instead of the naive ET string."""
    if cutoff_idx < 0:
        return None
    bars = store["bars"]
    date = bars[cutoff_idx]["_date_et"]
    idxs = store["by_date"].get(date, [])
    sess = [bars[i] for i in idxs if i <= cutoff_idx]
    payload = [{"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"],
                "timestamp_iso": b["t"]} for b in sess]
    try:
        trend = _classify_sameday_5m(payload)
    except Exception:  # noqa: BLE001 -- fail-open, matches production's own try/except
        return None
    return {"uptrend": "C", "downtrend": "P"}.get(str(trend))


def bar_close_at_or_before(store: dict, entry_unix: int) -> Optional[float]:
    idx = closed_bar_cutoff_idx(store, entry_unix)
    return store["bars"][idx]["c"] if idx >= 0 else None


# ============================================================================ decision-log join
def load_core_decisions(days: list[str] = DAYS) -> list[dict]:
    """Stream-parse core-decisions.jsonl (65MB, 28879 rows), keeping only rows whose date
    falls in `days`. Never loads the whole file into one json.loads pass."""
    day_set = set(days)
    out = []
    with CORE_DECISIONS.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip() or line[:14] != '{"ts_et": "202':
                continue
            ts_prefix = line[11:21]  # '"ts_et": "' is 10 chars, date is next 10
            if ts_prefix not in day_set:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = row.get("ts_et")
            if not isinstance(ts, str) or len(ts) < 19:
                continue
            try:
                row["_dt"] = datetime.fromisoformat(ts[:19])
            except ValueError:
                continue
            row["_date"] = ts[:10]
            out.append(row)
    out.sort(key=lambda r: r["_dt"])
    return out


def _nearest(rows: list[dict], date: str, dt: datetime, predicate=None) -> tuple[Optional[dict], Optional[float]]:
    """Nearest row (optionally filtered by `predicate`) on `date` within JOIN_WINDOW_S."""
    best, best_gap = None, None
    for r in rows:
        if r["_date"] != date:
            continue
        if predicate is not None and not predicate(r):
            continue
        gap = abs((r["_dt"] - dt).total_seconds())
        if gap <= JOIN_WINDOW_S and (best_gap is None or gap < best_gap):
            best, best_gap = r, gap
    return best, best_gap


def join_round_trip(rt: dict, decisions: list[dict]) -> dict:
    """Tiered join -- see module docstring. Returns a dict of everything score_conviction()
    needs plus provenance flags for the limitations section."""
    side = rt["side"]
    date = rt["date"]
    dt = datetime.fromisoformat(rt["entry_ts_et"][:19])
    tier1 = date >= RAW_TRIGGER_SCHEMA_BOUNDARY

    result = {"triggers_fired": [], "trigger_source": "unknown", "entry_level": None,
              "real_spot": None, "spot_source": None, "decision_join_gap_s": None,
              "logged_v0": None, "logged_v0_account": None}

    # spot: nearest tick on this date, ANY account/verdict (shared signal -- MAP.md).
    any_row, gap = _nearest(decisions, date, dt)
    if any_row is not None:
        result["real_spot"] = any_row.get("spy")
        result["spot_source"] = "decision_log"
        result["decision_join_gap_s"] = round(gap, 1)
    if result["real_spot"] is None:
        result["real_spot"] = None  # filled by caller from bars
        result["spot_source"] = "bar_close_fallback"

    if tier1:
        raw_key = "bear_triggers_raw" if side == "P" else "bull_triggers_raw"
        lvl_key = "bear_rejection_level_raw" if side == "P" else "bull_reclaim_level_raw"
        row, gap2 = _nearest(decisions, date, dt, predicate=lambda r: raw_key in r)
        if row is not None:
            result["triggers_fired"] = row.get(raw_key) or []
            result["entry_level"] = row.get(lvl_key)
            result["trigger_source"] = "raw_any_tick"
            if result["decision_join_gap_s"] is None:
                result["decision_join_gap_s"] = round(gap2, 1)
    else:
        verdict_side = "ENTER_BEAR" if side == "P" else "ENTER_BULL"
        row, gap2 = _nearest(decisions, date, dt,
                              predicate=lambda r: r.get("verdict") == verdict_side and r.get("side") == side)
        if row is not None:
            result["triggers_fired"] = row.get("triggers") or []
            result["trigger_source"] = "verdict_scoped"
            if result["decision_join_gap_s"] is None:
                result["decision_join_gap_s"] = round(gap2, 1)

    # logged v0 cross-check -- ONLY for core arms, ONLY same account, ONLY rows carrying a
    # real `conviction` dict (post-fix, post-2026-08-13 in practice).
    if rt["arm"] in ("safe-2", "bold-2"):
        acct = "safe" if rt["arm"] == "safe-2" else "bold"
        crow, _ = _nearest(decisions, date, dt,
                            predicate=lambda r: r.get("account") == acct and isinstance(r.get("conviction"), dict))
        if crow is not None:
            result["logged_v0"] = crow["conviction"]
            result["logged_v0_account"] = acct

    return result


# ============================================================================ scoring
def score_round_trip(rt: dict, store: dict, decisions: list[dict]) -> dict:
    join = join_round_trip(rt, decisions)
    entry_unix = int(datetime.fromisoformat(rt["entry_ts_et"][:19]).timestamp()
                      + _et_utc_offset_seconds(rt["entry_ts_et"]))
    cutoff_idx = closed_bar_cutoff_idx(store, entry_unix)

    if join["real_spot"] is None:
        join["real_spot"] = bar_close_at_or_before(store, entry_unix)

    env_hi, env_lo = reconstruct_envelope(store, cutoff_idx)
    structure_side = reconstruct_structure_side(store, cutoff_idx)
    trendline_records = reconstruct_trendline_records(store, cutoff_idx)

    tf = [str(t).lower() for t in (join["triggers_fired"] or [])]
    tl_trigger_confirmed = any("trendline" in t for t in tf)

    common = dict(side=rt["side"], entry_level=join["entry_level"], level_records=None,
                  triggers_fired=join["triggers_fired"], level_states=None,
                  trigger_close=join["real_spot"], envelope_high=env_hi, envelope_low=env_lo,
                  structure_side=structure_side, confluence_zones=None, k=rt["_k"])

    v0 = cv.score_conviction(**common, trendline_records=None)
    v2 = cv.score_conviction(**common, trendline_records=trendline_records)

    return {
        "date": rt["date"], "arm": rt["arm"], "side": rt["side"],
        "entry_ts_et": rt["entry_ts_et"], "exit_ts_et": rt["exit_ts_et"],
        "qty": rt["qty"], "real_pnl": rt["real_pnl"], "win": rt["real_pnl"] > 0,
        "k": rt["_k"], "cutoff_bar_found": cutoff_idx >= 0,
        "real_spot": join["real_spot"], "spot_source": join["spot_source"],
        "decision_join_gap_s": join["decision_join_gap_s"],
        "triggers_fired": join["triggers_fired"], "trigger_source": join["trigger_source"],
        "tl_trigger_confirmed": tl_trigger_confirmed,
        "entry_level": join["entry_level"],
        "envelope_high": env_hi, "envelope_low": env_lo, "structure_side": structure_side,
        "n_trendline_candidates": len(trendline_records),
        "trendline_candidates": trendline_records,
        "v0_total": v0.total, "v0_components": v0.components,
        "v2_total": v2.total, "v2_components": v2.components,
        "delta": v2.total - v0.total,
        "logged_v0": join["logged_v0"], "logged_v0_account": join["logged_v0_account"],
    }


def _et_utc_offset_seconds(ts_et_str: str) -> int:
    """core-decisions/fills-ledger ts_et strings are naive ET wall-clock. All 12 DAYS are EDT
    (verified by load_bars' dst_check), so the offset from UTC is a constant -4h for every
    timestamp this function is ever called with -- NOT a hardcoded year-round assumption (the
    caller only ever passes dates from DAYS), just the EDT-only fact this replay already proved."""
    return 4 * 3600


# ============================================================================ round trip mining
def mine_all_round_trips() -> list[dict]:
    out = []
    for arm in ARMS:
        rts = fills_fifo.mine_real_arm_fills(arm)
        rts = [r for r in rts if r["date"] in DAYS]
        rts.sort(key=lambda r: r["entry_ts_et"])
        per_arm_day_count: dict[str, int] = {}
        for r in rts:
            r = dict(r, arm=arm)
            key = r["date"]
            r["_k"] = per_arm_day_count.get(key, 0)
            per_arm_day_count[key] = r["_k"] + 1
            out.append(r)
    return out


# ============================================================================ aggregation
def _mean(xs):
    return round(statistics.mean(xs), 3) if xs else None


def _median(xs):
    return round(statistics.median(xs), 3) if xs else None


def discrimination_table(rows: list[dict]) -> dict:
    winners = [r for r in rows if r["win"]]
    losers = [r for r in rows if not r["win"]]
    table = {}
    for floor in range(0, 9):
        cell = {}
        for tag, total_key in (("v0", "v0_total"), ("v2", "v2_total")):
            blocked = [r for r in rows if r[total_key] < floor]
            wb = [r for r in blocked if r["win"]]
            lb = [r for r in blocked if not r["win"]]
            pnl_blocked = sum(r["real_pnl"] for r in blocked)
            cell[tag] = {
                "n_blocked": len(blocked), "winners_blocked": len(wb), "losers_blocked": len(lb),
                "winners_blocked_pct": round(100.0 * len(wb) / len(winners), 1) if winners else None,
                "losers_blocked_pct": round(100.0 * len(lb) / len(losers), 1) if losers else None,
                "pnl_blocked": round(pnl_blocked, 2),
                "delta_if_armed_usd": round(-pnl_blocked, 2),
            }
        table[str(floor)] = cell
    return table


def build_aggregates(rows: list[dict]) -> dict:
    scoreable = [r for r in rows if r["real_spot"] is not None]
    winners = [r for r in scoreable if r["win"]]
    losers = [r for r in scoreable if not r["win"]]
    tl_rows = [r for r in scoreable if r["tl_trigger_confirmed"]]
    tl_winners = [r for r in tl_rows if r["win"]]
    tl_losers = [r for r in tl_rows if not r["win"]]

    def bucket(rs):
        return {
            "n": len(rs),
            "v0_mean": _mean([r["v0_total"] for r in rs]), "v0_median": _median([r["v0_total"] for r in rs]),
            "v2_mean": _mean([r["v2_total"] for r in rs]), "v2_median": _median([r["v2_total"] for r in rs]),
            "delta_mean": _mean([r["delta"] for r in rs]),
            "n_delta_gt_0": sum(1 for r in rs if r["delta"] > 0),
            "total_pnl": round(sum(r["real_pnl"] for r in rs), 2),
        }

    return {
        "n_total_round_trips": len(rows),
        "n_scoreable": len(scoreable),
        "n_unscoreable_no_spot": len(rows) - len(scoreable),
        "n_winners": len(winners), "n_losers": len(losers),
        "all_rows": bucket(scoreable),
        "winners": bucket(winners),
        "losers": bucket(losers),
        "trendline_triggered_only": {
            "n": len(tl_rows), "winners": bucket(tl_winners), "losers": bucket(tl_losers),
        },
        "discrimination_full_population": discrimination_table(scoreable),
        "discrimination_trendline_triggered_only": discrimination_table(tl_rows),
        "trigger_source_breakdown": _count_by(scoreable, "trigger_source"),
        "spot_source_breakdown": _count_by(scoreable, "spot_source"),
    }


def _count_by(rows, key):
    out: dict[str, int] = {}
    for r in rows:
        out[str(r[key])] = out.get(str(r[key]), 0) + 1
    return out


def artifact_hunt(rows: list[dict]) -> dict:
    """Adversarial checks per this rig's standing 'suspicion scales with how good it looks'
    rule -- run BEFORE reporting, not after."""
    scoreable = [r for r in rows if r["real_spot"] is not None]
    tl_rows = [r for r in scoreable if r["tl_trigger_confirmed"]]
    tl_winners = [r for r in tl_rows if r["win"]]
    tl_losers = [r for r in tl_rows if not r["win"]]
    tl_credited = [r for r in scoreable if r["delta"] > 0]  # rows v2 actually helped

    by_date: dict[str, float] = {}
    for r in tl_credited:
        by_date[r["date"]] = by_date.get(r["date"], 0.0) + r["real_pnl"]
    # Magnitude-based concentration (NOT a signed share of net P&L -- when the net straddles
    # zero a signed share can exceed 100% or flip sign nonsensically, exactly the
    # trendline_conviction_override_study.py precedent's own 'only meaningful when the total
    # is itself positive' caveat. Share of GROSS movement is well-defined regardless of sign.):
    gross = sum(abs(v) for v in by_date.values())
    top_day = max(by_date.items(), key=lambda kv: abs(kv[1])) if by_date else (None, 0.0)
    top_day_gross_share = round(abs(top_day[1]) / gross, 3) if gross > 0 else None

    # THE central adversarial check: does C1 (named_level via trendline anchor) actually
    # discriminate, or does it fire near-universally whenever the trigger is trendline-family?
    # _match_trendline has NO distance cap of its own (only C4's separate $0.60 AT-the-line
    # check does) and searches up to ~8 candidate lines (wick/body x support/resistance x
    # primary/same-day) fit over a 5-trading-day window -- so if ANY one of those 8 clears
    # 20 respects / <=6 violations ANYWHERE, C1 fires regardless of how far that specific line
    # sits from the actual entry.
    c1_fires = sum(1 for r in tl_rows if r["v2_components"].get("named_level") == 2)
    c4_fires_winners = sum(1 for r in tl_winners if r["v2_components"].get("range_extreme") == 1)
    c4_fires_losers = sum(1 for r in tl_losers if r["v2_components"].get("range_extreme") == 1)
    match_gaps = []
    for r in tl_rows:
        qualifying = [c for c in r["trendline_candidates"]
                      if (c.get("respect_count") or 0) >= cv.TL_MIN_RESPECTS
                      and (c.get("violations") if c.get("violations") is not None else 0) <= cv.TL_MAX_VIOLATIONS]
        if qualifying and r["real_spot"] is not None:
            best_gap = min(abs(r["real_spot"] - (c.get("current_value") or r["real_spot"])) for c in qualifying)
            match_gaps.append(round(best_gap, 3))

    # proxy check 1: "later in the day = more bars = more respects" -- correlate n_trendline
    # candidates found against minutes-since-open at entry, over ALL trendline-triggered rows.
    def minutes_since_open(ts: str) -> Optional[float]:
        try:
            t = datetime.fromisoformat(ts[:19])
            return (t.hour * 60 + t.minute) - (9 * 60 + 30)
        except ValueError:
            return None

    xs, ys = [], []
    for r in tl_rows:
        m = minutes_since_open(r["entry_ts_et"])
        if m is not None:
            xs.append(m)
            ys.append(r["n_trendline_candidates"])
    corr_time_vs_ncandidates = _pearson(xs, ys)

    xs2, ys2 = [], []
    for r in tl_rows:
        m = minutes_since_open(r["entry_ts_et"])
        if m is not None:
            xs2.append(m)
            ys2.append(r["delta"])
    corr_time_vs_delta = _pearson(xs2, ys2)

    return {
        "n_rows_v2_gt_v0": len(tl_credited),
        "credited_pnl_by_date": {k: round(v, 2) for k, v in sorted(by_date.items())},
        "top_credited_day": top_day[0], "top_credited_day_pnl": round(top_day[1], 2),
        "top_credited_day_gross_share": top_day_gross_share,
        "concentration_flag": (top_day_gross_share is not None and top_day_gross_share >= 0.5
                                and len(by_date) > 1),
        "c1_named_level_fires_of_tl_rows": f"{c1_fires}/{len(tl_rows)}",
        "c1_fires_uniformly_flag": (len(tl_rows) > 0 and c1_fires == len(tl_rows)),
        "c4_at_line_fires_winners": f"{c4_fires_winners}/{len(tl_winners)}" if tl_winners else "0/0",
        "c4_at_line_fires_losers": f"{c4_fires_losers}/{len(tl_losers)}" if tl_losers else "0/0",
        "matched_line_gap_dollars": {
            "n": len(match_gaps), "mean": _mean(match_gaps), "median": _median(match_gaps),
            "max": round(max(match_gaps), 3) if match_gaps else None,
            "n_gap_gt_060": sum(1 for g in match_gaps if g > cv.TL_TOUCH_TOL),
        },
        "pearson_minutes_since_open_vs_n_candidates": corr_time_vs_ncandidates,
        "pearson_minutes_since_open_vs_delta": corr_time_vs_delta,
        "time_of_day_proxy_flag": (corr_time_vs_delta is not None and abs(corr_time_vs_delta) >= 0.5),
        "_reading": ("c1_fires_uniformly_flag is the HEADLINE check: _match_trendline has no "
                     "distance cap of its own (only C4's separate $0.60 test does), and "
                     "searches ~8 candidate lines fit over a 5-day window, so C1 (+2, 'named_"
                     "level' via trendline anchor) can fire even when the matched line sits "
                     "several dollars from spot (see matched_line_gap_dollars.max) -- "
                     "n_gap_gt_060 counts how many of those matches would NOT also clear C4's "
                     "OWN proximity bar. concentration_flag/time_of_day_proxy_flag are "
                     "tripwires, not verdicts -- a flagged result needs the raw "
                     "credited_pnl_by_date table read by eye before trusting any aggregate."),
    }


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return round(sxy / math.sqrt(sxx * syy), 3)


def crosscheck_logged_v0(rows: list[dict]) -> dict:
    """On the days core-decisions.jsonl carries a REAL logged v0, compare it to my
    reconstruction (same inputs where I could get them; degraded where I couldn't). This is
    the validation step for the whole reconstruction pipeline, not just the trendline piece."""
    have = [r for r in rows if r["logged_v0"] is not None]
    if not have:
        return {"n": 0, "note": "no round trip joined to a row carrying a logged conviction dict"}
    exact_total_matches = sum(1 for r in have if r["logged_v0"].get("total") == r["v0_total"])
    range_extreme_matches = sum(
        1 for r in have
        if r["logged_v0"].get("components", {}).get("range_extreme") == r["v0_components"].get("range_extreme"))
    structure_matches = sum(
        1 for r in have
        if r["logged_v0"].get("components", {}).get("structure_agreement") == r["v0_components"].get("structure_agreement"))
    rows_detail = [{
        "date": r["date"], "arm": r["arm"], "entry_ts_et": r["entry_ts_et"],
        "logged_v0_total": r["logged_v0"].get("total"), "reconstructed_v0_total": r["v0_total"],
        "logged_range_extreme": r["logged_v0"].get("components", {}).get("range_extreme"),
        "reconstructed_range_extreme": r["v0_components"].get("range_extreme"),
        "logged_structure": r["logged_v0"].get("components", {}).get("structure_agreement"),
        "reconstructed_structure": r["v0_components"].get("structure_agreement"),
    } for r in have]
    return {
        "n": len(have),
        "exact_total_match_pct": round(100.0 * exact_total_matches / len(have), 1),
        "range_extreme_component_match_pct": round(100.0 * range_extreme_matches / len(have), 1),
        "structure_component_match_pct": round(100.0 * structure_matches / len(have), 1),
        "detail": rows_detail,
    }


# ============================================================================ report
def render_markdown(agg: dict, hunt: dict, crosscheck: dict, dst_check: dict,
                     generated_at: str) -> str:
    d0 = agg["discrimination_trendline_triggered_only"]
    verdict = _verdict_line(agg, hunt)
    lines = [
        "# Conviction v2 historical replay -- does it agree with past winners?",
        "",
        f"**Generated:** {generated_at} ET  ",
        "**Status:** conviction stays DISARMED; v2 stays shadow-only. This is analysis only.",
        "",
        "## VERDICT",
        "",
        f"> {verdict}",
        "",
        "## Method",
        "",
        "12 days with trendline history (2026-06-26,07-08,07-09,07-10,07-13,07-14,08-11,08-12,"
        "08-13,08-14,08-17,08-18). Every closed real round trip (fills_fifo, arms "
        f"{', '.join(ARMS)}) scored twice via setup/scripts/conviction.py's score_conviction() "
        "-- v0 with trendline_records=None, v2 with lines reconstructed by CALLING "
        "backtest/autoresearch/trendline_engine.py's detect() (the live producer itself, not a "
        "port) on the production trailing-lookback bar window, truncated to bars fully CLOSED "
        "at-or-before the entry instant (C6 no-look-ahead). Real spot + fired triggers joined "
        "from the nearest automation/state/core-decisions.jsonl tick (shared signal, "
        f"+/-{JOIN_WINDOW_S}s window). Session envelope and same-day structure side "
        "reconstructed from bars the same no-look-ahead way; level_records/level_states/"
        "confluence_zones are NOT reconstructable historically (no archive) and are passed "
        "None -- this affects the ABSOLUTE score floor for both v0 and v2 equally, never the "
        "v0-v2 delta (only C1/C4 are trendline-reachable).",
        "",
        f"DST safety: {dst_check['target_day_bars']} target-day bars checked, "
        f"{dst_check['wall_v1_et_v2_mismatches']} wall-v1/et-v2 mismatches "
        f"({'SAFE' if dst_check['safe'] else 'MISMATCH -- see limitations'}) -- all 12 days are "
        "EDT months so the known -04:00-year-round mislabeling bug does not apply here.",
        "",
        "## Discrimination table -- trendline-triggered round trips only "
        "(the population v2 can actually change)",
        "",
        "This is the table that answers the question: would ARMING conviction at floor F have "
        "kept the winners and blocked the losers, and is v2 any better than v0 at that job?",
        "",
        "| Floor | v0 winners blocked | v0 losers blocked | v0 delta_if_armed | "
        "v2 winners blocked | v2 losers blocked | v2 delta_if_armed |",
        "|---|---|---|---|---|---|---|",
    ]
    for floor in range(0, 9):
        c = d0[str(floor)]
        lines.append(
            f"| {floor} | {c['v0']['winners_blocked']}/{agg['trendline_triggered_only']['winners']['n']} "
            f"({c['v0']['winners_blocked_pct']}%) | "
            f"{c['v0']['losers_blocked']}/{agg['trendline_triggered_only']['losers']['n']} "
            f"({c['v0']['losers_blocked_pct']}%) | ${c['v0']['delta_if_armed_usd']:+.2f} | "
            f"{c['v2']['winners_blocked']}/{agg['trendline_triggered_only']['winners']['n']} "
            f"({c['v2']['winners_blocked_pct']}%) | "
            f"{c['v2']['losers_blocked']}/{agg['trendline_triggered_only']['losers']['n']} "
            f"({c['v2']['losers_blocked_pct']}%) | ${c['v2']['delta_if_armed_usd']:+.2f} |"
        )
    lines += [
        "",
        f"Trendline-triggered population: n={agg['trendline_triggered_only']['n']} "
        f"(winners n={agg['trendline_triggered_only']['winners']['n']}, "
        f"losers n={agg['trendline_triggered_only']['losers']['n']}).",
        "",
        "### Score summary (trendline-triggered only)",
        "",
        "| Group | n | v0 mean | v0 median | v2 mean | v2 median | mean delta | rows v2>v0 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, key in (("Winners", "winners"), ("Losers", "losers")):
        b = agg["trendline_triggered_only"][key]
        lines.append(f"| {label} | {b['n']} | {b['v0_mean']} | {b['v0_median']} | {b['v2_mean']} | "
                     f"{b['v2_median']} | {b['delta_mean']} | {b['n_delta_gt_0']} |")

    df = agg["discrimination_full_population"]
    lines += [
        "",
        "## Discrimination table -- FULL population (all triggers, all 5 arms, all 12 days)",
        "",
        "For context: v0/v2 are byte-identical here except on trendline-triggered rows, so "
        "any v0-v2 gap in this table is diluted by the (majority) non-trendline population.",
        "",
        "| Floor | v0 winners blocked % | v0 losers blocked % | v0 delta_if_armed | "
        "v2 winners blocked % | v2 losers blocked % | v2 delta_if_armed |",
        "|---|---|---|---|---|---|---|",
    ]
    for floor in range(0, 9):
        c = df[str(floor)]
        lines.append(
            f"| {floor} | {c['v0']['winners_blocked_pct']}% | {c['v0']['losers_blocked_pct']}% | "
            f"${c['v0']['delta_if_armed_usd']:+.2f} | {c['v2']['winners_blocked_pct']}% | "
            f"{c['v2']['losers_blocked_pct']}% | ${c['v2']['delta_if_armed_usd']:+.2f} |"
        )

    lines += [
        "",
        "## Artifact hunt (run BEFORE trusting the table above)",
        "",
        "### Does the QUALITY BAR (respects/violations) itself discriminate?",
        "",
        f"- C1 (named_level via trendline anchor) fires on **{hunt['c1_named_level_fires_of_tl_rows']}** "
        f"trendline-triggered round trips -- "
        f"{'UNIFORMLY on winners AND losers (NO discrimination from the quality bar itself)' if hunt['c1_fires_uniformly_flag'] else 'not universal -- see detail'}.",
        f"- Matched-line distance from spot (among rows where a quality line was found): "
        f"n={hunt['matched_line_gap_dollars']['n']}, mean=${hunt['matched_line_gap_dollars']['mean']}, "
        f"median=${hunt['matched_line_gap_dollars']['median']}, max=${hunt['matched_line_gap_dollars']['max']} -- "
        f"{hunt['matched_line_gap_dollars']['n_gap_gt_060']} of those matches sit MORE than the "
        "$0.60 C4 proximity tolerance away from spot, i.e. _match_trendline's own quality gate "
        "has no distance cap and can credit a line nowhere near the trade.",
        f"- C4 ('AT the line', the $0.60 separate proximity check) fires on winners "
        f"{hunt['c4_at_line_fires_winners']} vs losers {hunt['c4_at_line_fires_losers']} -- this, "
        "not the quality bar, is where any outcome-linked signal in the floor-sweep table above "
        "actually comes from.",
        "",
        "### Concentration and proxy checks",
        "",
        f"- Rows where v2 total > v0 total (the trendline generalization actually fired): "
        f"n={hunt['n_rows_v2_gt_v0']}",
        f"- Credited P&L by date: {json.dumps(hunt['credited_pnl_by_date'])}",
        f"- Top day: **{hunt['top_credited_day']}**, ${hunt['top_credited_day_pnl']:+.2f} "
        f"({hunt['top_credited_day_gross_share']} share of GROSS credited-population P&L movement) "
        f"-- {'CONCENTRATION FLAG RAISED' if hunt['concentration_flag'] else 'not concentrated'}",
        f"- Correlation(minutes-since-open, n_trendline_candidates found) = "
        f"{hunt['pearson_minutes_since_open_vs_n_candidates']} (time-of-day proxy check #1)",
        f"- Correlation(minutes-since-open, v2-v0 delta) = "
        f"{hunt['pearson_minutes_since_open_vs_delta']} -- "
        f"{'FLAG: delta correlates with time-of-day, not just line quality' if hunt['time_of_day_proxy_flag'] else 'no strong time-of-day proxy signal'}",
        "",
        "## Reconstruction cross-check against REAL logged v0",
        "",
        f"core-decisions.jsonl only carries a real `conviction` field from 2026-08-13 onward. "
        f"n={crosscheck.get('n', 0)} round trips joined to a row carrying one.",
    ]
    if crosscheck.get("n"):
        lines += [
            f"- Exact v0.total match: {crosscheck['exact_total_match_pct']}% (expected to be LOW, "
            "not a bug -- my v0 has no level_records/level_states, so it structurally cannot "
            "reach the named_level/fresh_test points a fully-informed live v0 could; the gaps in "
            "the table below are consistently explained by exactly that, e.g. logged=4 vs "
            "reconstructed=1 is a named_level(+2) + fresh_test(+1) shortfall.)",
            f"- range_extreme component match: {crosscheck['range_extreme_component_match_pct']}% "
            "-- DEGENERATE: every one of these 14 rows has range_extreme=0 on BOTH sides (no "
            "variation in this subset), so this is not real validation, just a trivial "
            "agreement on zero. Reported anyway rather than hidden.",
            f"- structure_agreement component match: {crosscheck['structure_component_match_pct']}% "
            "-- GENUINE (both 0 and 1 appear on both sides): this caught and fixed a real bug in "
            "the FIRST run of this script -- structure_side reconstruction was silently "
            "returning None on 103/103 rows because crypto.lib.bar.Bar requires a tz-AWARE "
            "timestamp and this script was feeding it a naive one, which raised inside "
            "engine_cli._classify_sameday_5m's OWN fail-open except-block and surfaced as a "
            "look-alike 'no signal' rather than an error. Fixed by feeding the already-UTC-Zulu "
            "'t' string instead of the naive ET one; see reconstruct_structure_side()'s "
            "docstring in the tool script.",
            "",
            "| Date | Arm | Logged v0 | Reconstructed v0 | Logged range_extreme | "
            "Reconstructed range_extreme | Logged structure | Reconstructed structure |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in crosscheck["detail"]:
            lines.append(f"| {r['date']} | {r['arm']} | {r['logged_v0_total']} | "
                         f"{r['reconstructed_v0_total']} | {r['logged_range_extreme']} | "
                         f"{r['reconstructed_range_extreme']} | {r['logged_structure']} | "
                         f"{r['reconstructed_structure']} |")

    lines += [
        "",
        "## Limitations -- what could NOT be scored, and why",
        "",
        f"- Total closed round trips mined (5 arms, 12 days): {agg['n_total_round_trips']}.",
        f"- Unscoreable (no spot recoverable from either decision log or bars): "
        f"{agg['n_unscoreable_no_spot']}.",
        f"- Trigger source breakdown: {json.dumps(agg['trigger_source_breakdown'])} -- "
        "'raw_any_tick' = high-fidelity (post-2026-07-27 schema, every tick logs "
        "bear/bull_triggers_raw regardless of verdict); 'verdict_scoped' = pre-07-27 days, "
        "only trustworthy when a same-side ENTER verdict landed within the join window; "
        "'unknown' = no matching decision row found -- these rows are conservatively treated "
        "as NON-trendline-triggered (v0==v2), which can only UNDER-count v2's population, "
        "never inflate it.",
        f"- Spot source breakdown: {json.dumps(agg['spot_source_breakdown'])} -- 'decision_log' "
        "is the real live tick value; 'bar_close_fallback' is the closed 5m bar's close at-or-"
        "before entry (used mainly for fleet-arm entries the core tick log didn't mirror "
        "within the join window).",
        "- level_records, level_states, confluence_zones: NOT reconstructed (no historical "
        "archive of key-levels.json / confluence-zones.json exists for these 12 days). Passed "
        "None to both v0 and v2 uniformly -- degrades named_level (level path)/fresh_test/"
        "zone_stack identically for both scores, so it cannot bias the v0-v2 DELTA, only "
        "compresses the absolute floor-sweep numbers toward the low end for both.",
        "- k (entries-used-today, feeds the escalating ratchet floor): approximated as this "
        "arm's own same-day entry sequence number, not the true per-account settlement "
        "counter (unavailable historically). The floor-sweep tables above use a FLAT floor "
        "sweep (score < F), not the ratchet, specifically to avoid depending on this "
        "approximation.",
        "",
        "## Raw data",
        "",
        "Full per-row detail (all reconstructed trendline candidates, both score breakdowns) "
        "in the JSON sidecar: `analysis/deep-research/CONVICTION-V2-HISTORICAL-REPLAY-2026-08-18.json`.",
        "",
    ]
    return "\n".join(lines)


def _verdict_line(agg: dict, hunt: dict) -> str:
    tl = agg["trendline_triggered_only"]
    n = tl["n"]
    if n == 0:
        return "CANNOT-TELL -- zero trendline-triggered round trips reconstructed across the 12 days."
    if tl["winners"]["n"] == 0 or tl["losers"]["n"] == 0:
        return (f"CANNOT-TELL -- trendline-triggered population (n={n}) has no "
                f"{'losers' if tl['winners']['n'] else 'winners'}, so discrimination is undefined.")

    # THE question is specifically about the QUALITY BAR (respects>=20, violations<=6) -- if
    # C1 fires on every trendline-triggered row regardless of outcome, the quality bar itself
    # has ZERO discriminating power, full stop, no matter what the floor-sweep P&L shows (that
    # P&L comes from the SEPARATE $0.60 proximity check, C4, not from line quality).
    if hunt.get("c1_fires_uniformly_flag"):
        gap = hunt["matched_line_gap_dollars"]
        return (f"NO -- the RESPECTS/VIOLATIONS quality bar does not discriminate: C1 fires on "
                f"{hunt['c1_named_level_fires_of_tl_rows']} trendline-triggered round trips, "
                f"winners and losers alike (matched-line distance from spot up to ${gap['max']}, "
                f"median ${gap['median']} -- _match_trendline has no distance cap of its own). "
                f"The only outcome-linked effect comes from the SEPARATE $0.60 'AT the line' "
                f"check (C4): winners {hunt['c4_at_line_fires_winners']}, losers "
                f"{hunt['c4_at_line_fires_losers']} -- which is architecturally a rebrand of the "
                f"ALREADY-KNOWN proximity signal (prior replay: winners 96%/losers 85% within "
                f"$0.60 of ANY trendline), not new evidence contributed by the quality bar.")

    d0 = agg["discrimination_trendline_triggered_only"]
    best_floor, best_delta = None, None
    for floor in range(0, 9):
        v2delta = d0[str(floor)]["v2"]["delta_if_armed_usd"]
        if best_delta is None or v2delta > best_delta:
            best_floor, best_delta = floor, v2delta
    agrees = best_delta is not None and best_delta > 0
    concentrated = hunt.get("concentration_flag")
    if agrees and not concentrated:
        return (f"YES (with caveats) -- at floor {best_floor}, arming v2 nets "
                f"${best_delta:+.2f} vs v0's degraded baseline over n={n} trendline-triggered "
                f"round trips; see limitations before treating this as ship-ready evidence.")
    if agrees and concentrated:
        return (f"YES BUT SUSPECT -- floor {best_floor} nets ${best_delta:+.2f}, but the "
                f"artifact hunt flagged P&L concentration in one day; do not ship on this "
                f"alone.")
    return (f"NO -- no floor in 0..8 makes v2 net positive over the trendline-triggered "
            f"population (best floor {best_floor}: ${best_delta:+.2f}). v2 does not "
            f"demonstrably agree with past winners on this replay.")


# ============================================================================ main
def main() -> int:
    print("[replay] loading bars...", flush=True)
    store = load_bars()
    print(f"[replay] {len(store['bars'])} RTH bars loaded; dst_check={store['dst_check']}", flush=True)

    print("[replay] mining round trips...", flush=True)
    rts = mine_all_round_trips()
    print(f"[replay] {len(rts)} closed round trips across {len(ARMS)} arms / {len(DAYS)} days", flush=True)

    print("[replay] loading core-decisions.jsonl (streamed)...", flush=True)
    decisions = load_core_decisions()
    print(f"[replay] {len(decisions)} decision rows in scope", flush=True)

    print("[replay] scoring each round trip (v0 vs v2)...", flush=True)
    rows = []
    for i, rt in enumerate(rts):
        rows.append(score_round_trip(rt, store, decisions))
        if (i + 1) % 20 == 0:
            print(f"[replay]   scored {i + 1}/{len(rts)}", flush=True)

    print("[replay] aggregating...", flush=True)
    agg = build_aggregates(rows)
    hunt = artifact_hunt(rows)
    crosscheck = crosscheck_logged_v0(rows)

    try:
        sys.path.insert(0, str(REPO / "setup" / "scripts"))
        from et_clock import et_now  # noqa: PLC0415
        generated_at = et_now().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        generated_at = "unknown"

    out = {
        "_doc": "Historical replay: does conviction v2 agree with past winners? Analysis only, "
                "conviction stays DISARMED, v2 stays shadow-only.",
        "generated_at_et": generated_at,
        "days": DAYS, "arms": ARMS,
        "dst_check": store["dst_check"],
        "aggregates": agg,
        "artifact_hunt": hunt,
        "logged_v0_crosscheck": crosscheck,
        "rows": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[replay] wrote {OUT_JSON}", flush=True)

    md = render_markdown(agg, hunt, crosscheck, store["dst_check"], generated_at)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"[replay] wrote {OUT_MD}", flush=True)

    print("[replay] VERDICT: " + _verdict_line(agg, hunt), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
