#!/usr/bin/env python
"""conviction_c4_sidecar.py -- F4 CONVICTION C4 POLARITY SIDECAR + FLEET COVERAGE
(2026-09-03, descends from analysis/deep-research/2026-09-03-money/range-extreme-dead.md
and backtest/tools/money_range_extreme_probe.py, queue item TP1... no -- F4 in
analysis/deep-research/2026-09-03-money/SYNTHESIS.md section 3).

WHY THIS EXISTS. H2 proved conviction.py's C4 `range_extreme` is a DEAD KNOB: 0/482 (now
0/528+) post-fix hit rate, not from a coding bug but a POLARITY mismatch -- C4 was
calibrated on a mean-reversion exhibit ("puts want the TOP of the envelope, calls the
BOTTOM"), but the two live triggers (BULLISH_RECLAIM_RIDE_THE_RIBBON /
BEARISH_REJECTION_RIDE_THE_RIBBON) are CONTINUATION setups that fire near the session
extreme IN THEIR OWN TRADE DIRECTION -- the mirror-opposite shape. `conviction.py` itself
is FROZEN (config freeze through 2026-10-30) -- this sidecar re-scores the SAME rows with
the polarity flipped, entirely off to the side, so the question "would a continuation-shaped
C4 actually help" gets its own forward evidence base without touching the live component.

H2 ALSO found the conviction shadow has ZERO coverage on the four fleet arms
(risky-1/risky-3/safe-1/safe-3): `_conviction_shadow()` is called only on the core
(safe-2/bold-2) tick path (heartbeat_core.py) -- the fleet executor
(build_shared_signal.py / fleet_executor.py) never calls it, and fleet PLACED rows carry no
`conviction` block at all. This sidecar closes that gap for JUST the C4 component (the only
one computable from a fleet PLACED row's own fields): it recomputes `range_position` from
the cached SPY 1-minute tape, using the SAME session-envelope-through-the-trigger-bar
convention `heartbeat_core.py` uses for the core path (`_sess = win.iloc[:trig_idx+1]`,
"no look-ahead").

TWO DIFFERENT COVERAGE LEVELS -- NEVER FABRICATED, ALWAYS LABELED (`coverage` field on every
ledger row):
  "full_conviction" (core rows only) -- the row already carries ALL 7 components + a real
      floor (`floor_effective`) + a real `would_block` (total < floor). This sidecar
      RE-DERIVES `total` from the STORED components (total_live - orig_C4 + flipped_C4) --
      it does NOT re-invoke `score_conviction()`, because that requires level_records /
      level_states / structure_side / confluence_zones that a decision-ledger row does not
      retain. Equivalence between "sum stored components via conviction._SCORING_KEYS" and
      the row's own stored `total` is PROVEN on real rows in
      backtest/tests/test_conviction_c4_sidecar_2026_09_03.py (>= 20 rows), which is what
      licenses treating "stored components + flipped C4" as a faithful stand-in for calling
      score_conviction() again.
  "c4_component_only" (the four fleet arms) -- there is no C1/C2/C3/C5/C6/C7 to sum for a
      fleet PLACED row (no level_records, no memory, no structure read at placement time),
      so there is NO real floor and NO real `would_block` for these rows. The
      `would_block_*_c4proxy` fields name exactly what they are: "did the C4 component alone
      fail to score" -- a genuinely computable, non-fabricated quantity -- NEVER blended
      with core's real floor-based `would_block` without the `coverage` label making the
      difference explicit at every read site (ledger row AND summary cell).

THRESHOLDS (frozen here as constants, mirrors conviction.py's live rule and its exact
mirror-image -- see money_range_extreme_probe.py Part 4, same numbers):
  LIVE polarity          (conviction.py, unchanged): calls want pos <= 0.30, puts >= 0.70
  CONTINUATION polarity  (this sidecar's candidate):  calls want pos >= 0.70, puts <= 0.30

SHADOW ONLY. Never imports/writes anything on the trading path. `conviction.py` is read
ONLY for its RANGE_EXTREME_PCT constant and `_SCORING_KEYS` tuple (both read-only, never
mutated, never monkeypatched). Gates nothing -- there is no SKIP_LOW_CONVICTION branch
today and this sidecar does not add one. Decision rule frozen in
analysis/recommendations/prereg-conviction-c4-continuation-polarity-2026-09-03.md.

Outputs:
  analysis/recommendations/conviction-c4-sidecar-ledger.jsonl    append-only, dedup on
                                                                  (arm, account, ts_et)
  analysis/recommendations/conviction-c4-sidecar-summary.json    per-arm + book rollup

Run:
    python setup/scripts/conviction_c4_sidecar.py
Cost: $0 -- local JSONL/JSON reads only, no network, no broker, no LLM.
Guard: backtest/tests/test_conviction_c4_sidecar_2026_09_03.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FLEET_DIR = STATE / "fleet"
BACKTEST = REPO / "backtest"
for _p in (str(REPO), str(FLEET_DIR), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import conviction as cv  # noqa: E402  -- FROZEN, read-only import (constants + key tuple)
import conviction_shadow_report as csr  # noqa: E402  -- FIX_BOUNDARY_ET, read-only

CORE_DECISIONS = STATE / "core-decisions.jsonl"
SIP_1M_DIR = BACKTEST / "data" / "spy_sip_cache"

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "conviction-c4-sidecar-ledger.jsonl"
SUMMARY = OUT_DIR / "conviction-c4-sidecar-summary.json"
PREREG_REL = "analysis/recommendations/prereg-conviction-c4-continuation-polarity-2026-09-03.md"

FLEET_ARMS = ("risky-1", "risky-3", "safe-1", "safe-3")
_CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
_JOIN_WINDOW_S = 120

# --- C4 POLARITY THRESHOLDS (constants, per task spec) -------------------------------------
# LIVE mirrors conviction.py's own rule exactly (read off its RANGE_EXTREME_PCT, not
# retyped, so a future recalibration of that constant propagates here automatically).
LIVE_CALL_MAX_POS = cv.RANGE_EXTREME_PCT              # 0.30 -- live: calls want pos <= 0.30
LIVE_PUT_MIN_POS = 1.0 - cv.RANGE_EXTREME_PCT          # 0.70 -- live: puts  want pos >= 0.70
# CONTINUATION is the mirror image -- the polarity the live trigger family (RIDE_THE_RIBBON,
# 100% continuation setups per H2) actually produces.
CONTINUATION_CALL_MIN_POS = 1.0 - cv.RANGE_EXTREME_PCT  # 0.70 -- calls reward pos >= 0.70
CONTINUATION_PUT_MAX_POS = cv.RANGE_EXTREME_PCT          # 0.30 -- puts  reward pos <= 0.30

# The four named big winning days (SYNTHESIS.md sec.1, money_retest_entry_variant.py's own
# BIG_WINNER_DAYS -- same four dates, re-declared here rather than importing that module
# because it pulls pandas + the full backtest stack for one constant this stdlib-only
# nightly script must not depend on).
BIG_WINNER_DAYS = frozenset({"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"})

# DECISION-BEARING bar (prereg section 5, core-only per the 2026-09-03 amendment): both
# required before decision_rule may be read as a verdict.
BAR_MIN_SESSIONS = 20
BAR_MIN_CORE_ROWS = 60
# DISCLOSURE-ONLY threshold -- reported every night alongside fleet_rows_scored_disclosure_only,
# never part of bar_met (fleet has no real floor/would_block; see fleet_c4proxy_outcome_join).
BAR_MIN_FLEET_ROWS = 60


# ---------------------------------------------------------------------------------------
# C4 scoring, both polarities -- pure, side-effect-free
# ---------------------------------------------------------------------------------------
def c4_live_score(side: Optional[str], pos: Optional[float]) -> Optional[int]:
    if pos is None or side not in ("C", "P"):
        return None
    if side == "P":
        return 1 if pos >= LIVE_PUT_MIN_POS else 0
    return 1 if pos <= LIVE_CALL_MAX_POS else 0


def c4_continuation_score(side: Optional[str], pos: Optional[float]) -> Optional[int]:
    if pos is None or side not in ("C", "P"):
        return None
    if side == "C":
        return 1 if pos >= CONTINUATION_CALL_MIN_POS else 0
    return 1 if pos <= CONTINUATION_PUT_MAX_POS else 0


# ---------------------------------------------------------------------------------------
# CORE population (core-decisions.jsonl, post-fix, carries a real conviction block)
# ---------------------------------------------------------------------------------------
def _iter_core_rows():
    if not CORE_DECISIONS.exists():
        return
    with CORE_DECISIONS.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "conviction" not in line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            c = row.get("conviction")
            if not isinstance(c, dict):
                continue
            ts = row.get("ts_et")
            if not isinstance(ts, str) or ts < csr.FIX_BOUNDARY_ET:
                continue  # pre-fix rows scored with C4/C5 degraded by construction -- excluded
            yield row


def score_core_row(row: dict) -> dict:
    """RE-DERIVES `total` from the STORED components (does not re-invoke score_conviction()
    -- see module docstring for why, and the equivalence test for the proof)."""
    c = row["conviction"]
    comp = c.get("components") or {}
    degraded = list(c.get("degraded_components") or [])
    side = row.get("side")
    ts = row.get("ts_et")
    total_live = c.get("total")
    floor_eff = c.get("floor_effective")
    out: dict = {
        "arm": "core",
        "coverage": "full_conviction",
        "account": row.get("account"),
        "ts_et": ts,
        "date": ts[:10] if isinstance(ts, str) else None,
        "side": side,
        "setup": row.get("setup"),
        "k": c.get("k"),
        "range_position": comp.get("range_position"),
        "range_position_source": "stored_component",
        "orig_range_extreme": comp.get("range_extreme"),
        "degraded_range_extreme": "range_extreme" in degraded,
        "total_live": total_live,
        "floor_effective": floor_eff,
        "would_block_live": c.get("would_block"),
    }
    pos = comp.get("range_position")
    applicable = (
        pos is not None and "range_extreme" not in degraded and side in ("C", "P")
        and total_live is not None and floor_eff is not None
    )
    if not applicable:
        out.update({"not_applicable": True, "skip_reason": "degraded_or_missing_input",
                    "c4_live": None, "c4_continuation": None, "c4_flip": None,
                    "total_continuation": None, "would_block_continuation": None,
                    "would_block_flip": None})
        return out
    c4l = c4_live_score(side, pos)
    c4c = c4_continuation_score(side, pos)
    orig_c4 = int(comp.get("range_extreme") or 0)
    total_continuation = int(total_live) - orig_c4 + c4c
    would_block_continuation = bool(total_continuation < floor_eff)
    out.update({
        "not_applicable": False,
        "c4_live": c4l,
        "c4_continuation": c4c,
        "c4_flip": bool(c4c == 1 and c4l == 0),
        "total_continuation": total_continuation,
        "would_block_continuation": would_block_continuation,
        "would_block_flip": bool(bool(c.get("would_block")) and not would_block_continuation),
    })
    return out


# ---------------------------------------------------------------------------------------
# FLEET population (4 ledgers, PLACED rows only, no conviction block -- the coverage gap)
# ---------------------------------------------------------------------------------------
def _iter_fleet_rows(arm: str):
    path = FLEET_DIR / arm / "decisions.jsonl"
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            placement = row.get("placement") or {}
            if not placement.get("placed"):
                continue  # PLACED rows only -- the real-order-committing subset
            yield row


_SPY_1M_CACHE: dict[str, Optional[list]] = {}


def _load_spy_1m_rth(date_str: str) -> Optional[list]:
    """RTH (09:30-16:00 ET) 1-min bars for one date from the cached SIP tape, sorted by
    timestamp. Cache-miss (no file for the date -- e.g. today's live session) returns None,
    never fabricated. Same source money_retest_entry_variant.py reads
    (backtest/data/spy_sip_cache/spy_1m_<date>.json)."""
    if date_str in _SPY_1M_CACHE:
        return _SPY_1M_CACHE[date_str]
    path = SIP_1M_DIR / f"spy_1m_{date_str}.json"
    if not path.exists():
        _SPY_1M_CACHE[date_str] = None
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _SPY_1M_CACHE[date_str] = None
        return None
    out = []
    for b in raw.get("bars", []):
        t = b.get("t")
        if not isinstance(t, str) or len(t) < 19:
            continue
        hhmmss = t[11:19]
        if "09:30:00" <= hhmmss < "16:00:00":
            try:
                out.append({"t": t, "hhmmss": hhmmss, "h": float(b["h"]), "l": float(b["l"]),
                            "c": float(b["c"])})
            except (KeyError, TypeError, ValueError):
                continue
    out.sort(key=lambda b: b["t"])
    _SPY_1M_CACHE[date_str] = out
    return out


def _hhmmss(ts: Optional[str]) -> Optional[str]:
    """ET wall-clock HH:MM:SS from either a naive core ts_et or an offset-aware fleet
    ts_et (e.g. '...-04:00' EDT) -- fromisoformat resolves the offset, .time() reads the
    ET wall clock regardless of which format was on disk."""
    if not isinstance(ts, str):
        return None
    try:
        return dt.datetime.fromisoformat(ts).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return None


def _floor_to_minute(hhmmss: str) -> str:
    """Truncate an 'HH:MM:SS' wall-clock string to its minute floor 'HH:MM:00'."""
    return hhmmss[:5] + ":00"


def range_position_from_tape(date_str: str, hhmmss: str):
    """Session hi/lo through the LAST FULLY-CLOSED bar off the cached 1-min tape.

    CONVENTION (fixed 2026-09-03 -- see FINDING-1 below): bars in spy_1m_<date>.json use
    START-OF-BAR timestamps -- a bar dated 'HH:MM:00' spans HH:MM:00..HH:(MM+1):00 and its
    h/l/c are not final until the NEXT minute begins. A bar therefore only qualifies once its
    OWN start time is STRICTLY EARLIER than the trigger tick's minute floor
    (`b['t'] < floor_to_minute(tick)`), i.e. only bars that have actually CLOSED by the tick.
    This mirrors heartbeat_core.py's own anti-look-ahead pattern (`trig_idx = n - 2`,
    setup/scripts/heartbeat_core.py ~lines 917/947 -- the most-recently-fetched bar is always
    excluded as still-forming/confirmation-only), one bar resolution finer (1-min vs 5-min).

    FINDING-1 (confirmed on real data, 2026-09-03 review): fleet decision ticks fire ~3-6s
    AFTER the minute mark, so the OLD `b['hhmmss'] <= hhmmss` filter included the bar still
    forming at tick time (e.g. a tick at 14:49:03 included the 14:49:00-14:50:00 bar), leaking
    up to ~59s of future high/low/close into range_position. Fixed by requiring the bar's
    start to be strictly before the tick's minute floor instead of `<=` the raw tick time.

    Returns (pos, trigger_close, skip_reason)."""
    bars = _load_spy_1m_rth(date_str)
    if not bars:
        return None, None, "no_cached_spy_tape_for_date"
    floor = _floor_to_minute(hhmmss)
    prefix = [b for b in bars if b["hhmmss"] < floor]
    if not prefix:
        return None, None, "trigger_before_first_cached_rth_bar"
    hi = max(b["h"] for b in prefix)
    lo = min(b["l"] for b in prefix)
    close = prefix[-1]["c"]
    if hi <= lo:
        return None, None, "degenerate_envelope_hi_le_lo"
    return round((close - lo) / (hi - lo), 4), close, None


def score_fleet_row(row: dict, arm: str) -> dict:
    ts = row.get("ts_et")
    side = row.get("side")
    date_str = ts[:10] if isinstance(ts, str) else None
    out: dict = {
        "arm": arm,
        "coverage": "c4_component_only",
        "account": None,
        "ts_et": ts,
        "date": date_str,
        "side": side,
        "setup": row.get("setup_name"),
        "range_position_source": "spy_tape_prefix",
    }
    hhmmss = _hhmmss(ts)
    if side not in ("C", "P") or not date_str or not hhmmss:
        out.update({"not_applicable": True, "skip_reason": "missing_side_or_ts_et",
                    "range_position": None, "c4_live": None, "c4_continuation": None,
                    "c4_flip": None, "would_block_live_c4proxy": None,
                    "would_block_continuation_c4proxy": None})
        return out
    pos, close, reason = range_position_from_tape(date_str, hhmmss)
    if pos is None:
        out.update({"not_applicable": True, "skip_reason": reason,
                    "range_position": None, "c4_live": None, "c4_continuation": None,
                    "c4_flip": None, "would_block_live_c4proxy": None,
                    "would_block_continuation_c4proxy": None})
        return out
    c4l = c4_live_score(side, pos)
    c4c = c4_continuation_score(side, pos)
    out.update({
        "not_applicable": False,
        "range_position": pos,
        "trigger_close": close,
        "c4_live": c4l,
        "c4_continuation": c4c,
        "c4_flip": bool(c4c == 1 and c4l == 0),
        # C4-COMPONENT-ONLY PROXY -- there is no floor for a fleet row (no C1/C2/C3/C5/C6/C7
        # available at this row shape). "would_block" here means exactly one thing: the C4
        # point alone failed to score under that polarity. NEVER pooled with core's real
        # floor-based would_block without the `coverage` label carrying the distinction.
        "would_block_live_c4proxy": (c4l == 0),
        "would_block_continuation_c4proxy": (c4c == 0),
    })
    return out


# ---------------------------------------------------------------------------------------
# ledger I/O -- idempotent append, dedup on (arm, account, ts_et)
# ---------------------------------------------------------------------------------------
def _row_id(r: dict) -> str:
    return f"{r.get('arm')}|{r.get('account') or ''}|{r.get('ts_et')}"


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
            continue  # a torn last line must never kill the accrual
    return rows


# ---------------------------------------------------------------------------------------
# outcome join -- real fills, greedy one-to-one, day-scoped, +/-120s window (mirrors
# conviction_shadow_report._attach_outcomes exactly, generalized over core AND fleet arms)
# ---------------------------------------------------------------------------------------
def _resolved_fills_arm(row: dict) -> Optional[str]:
    if row.get("arm") == "core":
        return _CORE_ACCOUNT_TO_ARM.get(str(row.get("account")))
    return row.get("arm")


def _parse_ts(ts: Optional[str]):
    if not isinstance(ts, str) or len(ts) < 19:
        return None
    try:
        return dt.datetime.fromisoformat(ts[:19])
    except ValueError:
        return None


def attach_outcomes(rows: list[dict]) -> int:
    """Joins each ledger row to its REAL round trip via fills_fifo.mine_real_arm_fills.
    Additive and never raises -- an unmatched row keeps real_pnl absent and is excluded from
    outcome cells rather than guessed at."""
    try:
        from fills_fifo import mine_real_arm_fills  # noqa: PLC0415
    except Exception:  # noqa: BLE001 -- the join is additive; never break the sidecar
        return 0

    needed = {a for a in (_resolved_fills_arm(r) for r in rows) if a}
    by_arm: dict[str, list[dict]] = {}
    for a in needed:
        try:
            by_arm[a] = mine_real_arm_fills(a)
        except Exception:  # noqa: BLE001
            by_arm[a] = []

    candidates = []
    for idx, row in enumerate(rows):
        arm = _resolved_fills_arm(row)
        t = _parse_ts(row.get("ts_et"))
        if not arm or t is None:
            continue
        for rid, rt in enumerate(by_arm.get(arm, [])):
            if rt.get("date") != row.get("date"):
                continue
            et = _parse_ts(rt.get("entry_ts_et"))
            if et is None:
                continue
            gap = abs((et - t).total_seconds())
            if gap <= _JOIN_WINDOW_S:
                candidates.append((gap, idx, arm, rid))
    candidates.sort(key=lambda c: c[0])
    used_rows: set = set()
    used_rts: set = set()
    joined = 0
    for gap, idx, arm, rid in candidates:
        if idx in used_rows or (arm, rid) in used_rts:
            continue
        rt = by_arm[arm][rid]
        rows[idx]["real_pnl"] = rt["real_pnl"]
        rows[idx]["match_gap_s"] = round(gap, 1)
        used_rows.add(idx)
        used_rts.add((arm, rid))
        joined += 1
    return joined


# ---------------------------------------------------------------------------------------
# summary statistics -- day-clustered bootstrap CI (same methodology as
# tp1_r50_forward_shadow.py's _bootstrap_day_clustered_mean / go_live_gate.bootstrap_pf_ci),
# top-3 concentration (magnitude-based, sign-agnostic)
# ---------------------------------------------------------------------------------------
def _bootstrap_day_clustered_mean(rows: list[dict], n_boot: int = 2000,
                                   seed: int = 20260903) -> Optional[dict]:
    by_day: dict[str, list[float]] = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r["real_pnl"])
    days = sorted(by_day)
    n_days = len(days)
    if n_days < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample_days = [days[rng.randrange(n_days)] for _ in range(n_days)]
        vals = [v for d in sample_days for v in by_day[d]]
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return {"n_boot": n_boot, "n_days_clustered": n_days,
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def _cell(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    vals = [r["real_pnl"] for r in rows]
    n = len(vals)
    total = sum(vals)
    wins = sum(1 for v in vals if v > 0)
    return {"n": n, "total_pnl": round(total, 2), "mean_pnl": round(total / n, 4),
            "win_rate_pct": round(100.0 * wins / n, 1),
            "session_clustered_ci": _bootstrap_day_clustered_mean(rows)}


def _would_block(row: dict, polarity: str) -> Optional[bool]:
    key = (f"would_block_{polarity}" if row["coverage"] == "full_conviction"
           else f"would_block_{polarity}_c4proxy")
    return row.get(key)


def _outcome_join(rows: list[dict]) -> dict:
    joined = [r for r in rows if r.get("real_pnl") is not None]
    out: dict = {"n_joined": len(joined), "n_unjoined": len(rows) - len(joined)}
    for polarity in ("live", "continuation"):
        allow = [r for r in joined if _would_block(r, polarity) is False]
        block = [r for r in joined if _would_block(r, polarity) is True]
        out[polarity] = {"WOULD_ALLOW": _cell(allow), "WOULD_BLOCK": _cell(block)}
    return out


def _top3_concentration_share(rows: list[dict]) -> float:
    vals = [r["real_pnl"] for r in rows if r.get("real_pnl") is not None]
    total_abs = sum(abs(v) for v in vals)
    if total_abs <= 1e-9:
        return 0.0
    top3 = sum(sorted((abs(v) for v in vals), reverse=True)[:3])
    return round(top3 / total_abs, 4)


def _arm_summary(rows: list[dict]) -> dict:
    n = len(rows)
    applicable = [r for r in rows if not r.get("not_applicable")]
    n_app = len(applicable)
    sessions = sorted({r["date"] for r in rows if r.get("date")})
    coverage = rows[0]["coverage"] if rows else None
    live_key = "would_block_live" if coverage == "full_conviction" else "would_block_live_c4proxy"
    cont_key = ("would_block_continuation" if coverage == "full_conviction"
                else "would_block_continuation_c4proxy")
    n_block_live = sum(1 for r in applicable if r.get(live_key))
    n_block_cont = sum(1 for r in applicable if r.get(cont_key))
    return {
        "n": n,
        "n_applicable": n_app,
        "n_not_applicable": n - n_app,
        "coverage": coverage,
        "sessions": len(sessions),
        "date_span": f"{sessions[0]}..{sessions[-1]}" if sessions else None,
        "would_block_rate_live_pct": (round(100.0 * n_block_live / n_app, 1)
                                       if n_app else None),
        "would_block_rate_continuation_pct": (round(100.0 * n_block_cont / n_app, 1)
                                               if n_app else None),
        "flips_c4": sum(1 for r in applicable if r.get("c4_flip")),
        "flips_would_block": (sum(1 for r in applicable if r.get("would_block_flip"))
                               if coverage == "full_conviction" else None),
        "outcome_join": _outcome_join(rows),
        "top3_concentration_share": _top3_concentration_share(rows),
    }


def _big_days_check(rows: list[dict]) -> dict:
    big = [r for r in rows if r.get("date") in BIG_WINNER_DAYS and not r.get("not_applicable")]
    would_block = []
    for r in big:
        key = ("would_block_continuation" if r["coverage"] == "full_conviction"
               else "would_block_continuation_c4proxy")
        if r.get(key):
            would_block.append({"arm": r["arm"], "ts_et": r["ts_et"], "date": r["date"]})
    return {"n_entries_on_big_days": len(big), "n_would_block_under_continuation": len(would_block),
            "all_would_allow_continuation": (len(big) > 0 and len(would_block) == 0),
            "blocked_rows": would_block}


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


# ---------------------------------------------------------------------------------------
def run() -> dict:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen = {_row_id(r) for r in existing}

        new_rows = []
        for raw in _iter_core_rows():
            r = score_core_row(raw)
            if _row_id(r) not in seen:
                new_rows.append(r)
        for arm in FLEET_ARMS:
            for raw in _iter_fleet_rows(arm):
                r = score_fleet_row(raw, arm)
                if _row_id(r) not in seen:
                    new_rows.append(r)

        if new_rows:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, default=str) + "\n")

        all_rows = existing + new_rows
        attach_outcomes(all_rows)  # additive, mutates in place, never raises

        by_arm = {}
        for arm in ("core",) + FLEET_ARMS:
            arm_rows = [r for r in all_rows if r.get("arm") == arm]
            if arm_rows:
                by_arm[arm] = _arm_summary(arm_rows)

        # FINDING-2 FIX (2026-09-03): the PRIMARY decision statistic is CORE ROWS ONLY
        # (coverage=="full_conviction", real stored conviction block + real floor-based
        # would_block). Fleet C4-proxy rows are DISCLOSURE ONLY under their own key
        # (fleet_c4proxy_outcome_join) and are NEVER pooled with core into one outcome-join
        # cell -- prereg section 7's "do_not: pool fleet c4proxy would_block with core's real
        # floor-based would_block under one key" previously conflicted with section 5 reading
        # a pooled `book_outcome_join`; both the code and the prereg are now core-only for
        # the decision rule (prereg section 5/7, 2026-09-03 amendment).
        core_rows_all = [r for r in all_rows if r["arm"] == "core"]
        fleet_rows_all = [r for r in all_rows if r["arm"] in FLEET_ARMS]
        core_applicable = sum(1 for r in core_rows_all if not r.get("not_applicable"))
        fleet_applicable = sum(1 for r in fleet_rows_all if not r.get("not_applicable"))
        core_sessions = sorted({r["date"] for r in core_rows_all
                                 if r.get("date") and not r.get("not_applicable")})
        fleet_sessions = sorted({r["date"] for r in fleet_rows_all
                                  if r.get("date") and not r.get("not_applicable")})
        # Bar is CORE-ONLY (prereg section 5): >=20 forward sessions AND >=60 forward core
        # rows. Fleet coverage is still measured and reported every night (bar_met never
        # depends on it -- it is disclosure, never decision-bearing).
        bar_met = (len(core_sessions) >= BAR_MIN_SESSIONS and core_applicable >= BAR_MIN_CORE_ROWS)

        core_outcome = _outcome_join(core_rows_all)
        fleet_c4proxy_outcome = _outcome_join(fleet_rows_all)
        big_days = _big_days_check(all_rows)

        ci_block_cont = (core_outcome.get("continuation", {}).get("WOULD_BLOCK", {})
                         .get("session_clustered_ci"))
        blocks_losers = bool(ci_block_cont and ci_block_cont.get("ci_upper_97.5", 0) < 0)
        decision_met = bool(bar_met and blocks_losers and big_days["all_would_allow_continuation"])

        summary = {
            "_meta": {
                "generated_at_et": _stamp_now_et(),
                "builder": "setup/scripts/conviction_c4_sidecar.py",
                "armed": False,
                "shadow_only": ("[DISARMED] SHADOW ONLY -- conviction.py is unmodified and "
                                "FROZEN; this sidecar re-scores a COPY of each row with C4's "
                                "polarity flipped. Gates nothing."),
                "fix_boundary_et": csr.FIX_BOUNDARY_ET,
                "live_thresholds": {"call_max_pos": LIVE_CALL_MAX_POS, "put_min_pos": LIVE_PUT_MIN_POS},
                "continuation_thresholds": {"call_min_pos": CONTINUATION_CALL_MIN_POS,
                                             "put_max_pos": CONTINUATION_PUT_MAX_POS},
                "prereg": PREREG_REL,
                "new_rows_this_run": len(new_rows),
            },
            "by_arm": by_arm,
            "core_outcome_join": core_outcome,
            "fleet_c4proxy_outcome_join": fleet_c4proxy_outcome,
            "big_winner_days": sorted(BIG_WINNER_DAYS),
            "big_days_check": big_days,
            "bar": {"min_sessions": BAR_MIN_SESSIONS, "min_core_rows": BAR_MIN_CORE_ROWS,
                    "min_fleet_rows_disclosure_only": BAR_MIN_FLEET_ROWS,
                    "sessions_accrued": len(core_sessions),
                    "core_rows_scored": core_applicable,
                    "fleet_rows_scored_disclosure_only": fleet_applicable,
                    "fleet_sessions_disclosure_only": len(fleet_sessions),
                    "bar_met": bar_met},
            "decision_rule": {
                "would_block_ci_upper_lt_zero": blocks_losers,
                "big_days_all_would_allow": big_days["all_would_allow_continuation"],
                "all_conditions_met": decision_met,
                "note": ("Both conditions are read ONLY once bar_met is True (see prereg "
                         f"{PREREG_REL}) -- values are still computed and reported below the "
                         "bar for visibility, never as a verdict. Decision statistic is CORE "
                         "ROWS ONLY (core_outcome_join, coverage=full_conviction); fleet "
                         "C4-proxy rows (fleet_c4proxy_outcome_join) are disclosure-only and "
                         "never pooled into this statistic (prereg section 7)."),
            },
            "status": ("BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING"),
        }
        SUMMARY.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- a nightly instrument must fail open, not crash
        return {"error": f"{type(e).__name__}: {e}"[:400], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
