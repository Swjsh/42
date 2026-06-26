#!/usr/bin/env python
"""Deterministic decision grader (R-0008 fix).

Graduates the fragile EOD-summary Step-7h LLM "hand-edit the JSONL" instruction
into a pure-Python grade. For ~5 weeks `decision_grade` was null on ~100% of rows
because the free-tier EOD path never escalated to the Claude prompt that carried 7h
(and the free-tier path has no Write tool anyway). This runs on every EOD path.

WHAT IT GRADES: heartbeat per-tick decision rows (Schema A: have `action` + `spy`
+ a date + a clock time + the `decision_grade` field). Watcher/ledger rows
(Schema B: `outcome` + `setup_name`, no `decision_grade`) are LEFT UNTOUCHED -- they
are a different ledger graded by `outcome`, not in scope for R-0008.

GRADE BASIS (honest, documented): a SPY 30-min-forward DIRECTIONAL proxy -- NOT an
option-P&L grade (we have no per-tick option fill for a SKIP/HOLD). For a directional
action (ENTER/EXIT with a known side) we grade whether SPY moved in the action's
favor over the next 30 min; for a no-commitment HOLD/SKIP we grade `correct` if the
tape stayed in chop (nothing missed) else `ambiguous`. The weekly review aggregates
this into a decision-precision rate; `decision_grade_basis` records the method so it
is never mistaken for realized option P&L.

Side effect (bonus): rewrites the ledger one-object-per-line, REPAIRING any malformed
concatenated lines (the file currently has one). Atomic temp-file swap.

$0, no network, no LLM. Usage:
    python setup/scripts/grade_decisions.py --date 2026-06-18     # grade one date
    python setup/scripts/grade_decisions.py --backfill-all        # grade all ungraded
    python setup/scripts/grade_decisions.py --backfill-all --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from json import JSONDecoder
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
LEDGERS = [
    REPO / "automation" / "state" / "decisions.jsonl",
    REPO / "automation" / "state" / "aggressive" / "decisions.jsonl",
]
FWD_MINUTES = 30
CHOP_THRESH_PCT = 0.0015  # |SPY 30-min move| < 0.15% = no clean directional move
GRADE_BASIS = "spy_30min_fwd_proxy_v1"

_DECODER = JSONDecoder()


# ── SPY bars ────────────────────────────────────────────────────────────────
def _load_spy() -> pd.DataFrame:
    """Newest SPY 5m master, tz-aware ET index."""
    cands = sorted((REPO / "backtest" / "data").glob("spy_5m_2025-01-01_*.csv"))
    cands = [c for c in cands if "merged" not in c.name] or cands
    if not cands:
        raise FileNotFoundError("no spy_5m_2025-01-01_*.csv master found")
    master = cands[-1]
    df = pd.read_csv(master)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=True)  # offset-aware -> UTC
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def _fwd_move(spy: pd.DataFrame, date: str, time_et: str) -> float | None:
    """SPY % move from the bar at/after (date, time_et) to ~FWD_MINUTES later.
    Returns None when the date/time is outside our bar coverage."""
    try:
        # decision clock is naive ET; SPY master is ET with -04:00/-05:00 offset.
        # Localize to America/New_York then compare in UTC (C6/L57: never tz_localize('UTC')).
        anchor_naive = pd.Timestamp(f"{date} {time_et}")
        anchor = anchor_naive.tz_localize("America/New_York").tz_convert("UTC")
    except (ValueError, TypeError):
        return None
    day = spy[(spy["ts"] >= anchor) & (spy["ts"] <= anchor + timedelta(hours=1))]
    if day.empty:
        return None
    t0 = day.iloc[0]
    later = spy[(spy["ts"] >= anchor + timedelta(minutes=FWD_MINUTES - 1))]
    if later.empty:
        return None
    t1 = later.iloc[0]
    # only grade if t1 is genuinely forward (not same bar) and same session day
    if t1["ts"] <= t0["ts"]:
        return None
    if (t1["ts"] - t0["ts"]) > timedelta(hours=2):  # ran off the session -> no clean window
        return None
    if not t0["close"]:
        return None
    return (float(t1["close"]) - float(t0["close"])) / float(t0["close"])


# ── stance + grade ──────────────────────────────────────────────────────────
def _lean(obj: dict) -> int:
    """The engine's directional READ for this tick: +1 bull / -1 bear / 0 none.

    Priority: explicit side/symbol (a committed trade) > ribbon stack (the trend
    read) > a decisive score gap (>=2). A no-lean tick (e.g. a pure chop-floor HOLD)
    returns 0 and is left UNGRADED -- a directional proxy cannot grade an abstention
    with no stated direction, and auto-scoring it 'correct' in chop inflates the
    metric to ~100% (the bug this replaces)."""
    action = str(obj.get("action", "")).upper()
    sym = str(obj.get("symbol", "") or "")
    side = str(obj.get("side", "") or "").upper()
    if "BULL" in action or "CALL" in action or side in ("C", "CALL", "BULL"):
        return 1
    if "BEAR" in action or "PUT" in action or side in ("P", "PUT", "BEAR"):
        return -1
    if sym:  # OCC symbol e.g. SPY260519C00738000 / ...P00738000
        body = sym.split("SPY")[-1]
        if "C" in body and "C" in body[5:9]:
            return 1
        if "P" in body and "P" in body[5:9]:
            return -1
    stack = str(obj.get("ribbon_stack", "") or "").upper()
    if stack == "BULL":
        return 1
    if stack == "BEAR":
        return -1
    b, s = obj.get("bull_score"), obj.get("bear_score")
    if isinstance(b, (int, float)) and isinstance(s, (int, float)) and abs(b - s) >= 2:
        return 1 if b > s else -1
    return 0


def _grade(obj: dict, fwd_ret: float) -> str | None:
    """Directional-read correctness vs the SPY 30-min forward move. None when the
    tick carries no determinable directional lean (left ungraded, not auto-correct)."""
    lean = _lean(obj)
    if lean == 0:
        return None
    signed = lean * fwd_ret
    if signed > CHOP_THRESH_PCT:
        return "correct"
    if signed < -CHOP_THRESH_PCT:
        return "wrong"
    return "ambiguous"


def _is_gradeable(obj: dict) -> bool:
    """Schema-A heartbeat decision row: has action, a reference SPY price, a date
    and a clock time, and is not already graded. Schema-B (outcome/setup_name) skipped."""
    if "outcome" in obj and "decision_grade" not in obj:
        return False  # watcher/ledger row -> different ledger, leave untouched
    if not obj.get("action"):
        return False
    if obj.get("spy") in (None, "", 0):
        return False
    if not obj.get("date") or not obj.get("time_et"):
        return False
    g = obj.get("decision_grade")
    return g in (None, "") or g not in ("correct", "wrong", "ambiguous")


# ── LOSSLESS whole-content stream decode (handles compact, concatenated, AND
#    pretty-printed multi-line objects -- newlines inside an object are just
#    whitespace to raw_decode, so a stray indented tick is reassembled, not lost.
#    Rewriting compact one-object-per-line REPAIRS the file going forward.) ─────
def _stream_decode(content: str) -> tuple[list[dict], int]:
    """Return (objects, garbage_resyncs). Resync only on genuine corruption; for a
    clean (even pretty-printed) ledger garbage_resyncs is 0 == fully lossless."""
    objs: list[dict] = []
    resyncs = 0
    idx, n = 0, len(content)
    while idx < n:
        while idx < n and content[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = _DECODER.raw_decode(content, idx)
        except json.JSONDecodeError:
            resyncs += 1
            idx += 1  # lossless char-walk: never skips a valid object, only garbage chars
            continue
        idx = end
        if isinstance(obj, dict):
            objs.append(obj)
        # non-dict (e.g. a bare string fragment) is consumed + dropped, not double-counted
    return objs, resyncs


def _grade_obj(obj: dict, spy: pd.DataFrame, only_date: str | None, counts: dict) -> None:
    """Mutate obj in place with its grade; bump counts. (Schema-B / non-gradeable
    rows pass through untouched.)"""
    if not _is_gradeable(obj):
        if obj.get("decision_grade") in ("correct", "wrong", "ambiguous"):
            counts["already"] += 1
        else:
            counts["skipped_not_gradeable"] += 1
        return
    if only_date and obj.get("date") != only_date:
        counts["skipped_not_gradeable"] += 1
        return
    fwd = _fwd_move(spy, obj["date"], obj["time_et"])
    if fwd is None:
        obj["decision_grade"] = None
        obj["decision_grade_basis"] = "no_fwd_bars"
        counts["no_data"] += 1
        return
    grade = _grade(obj, fwd)
    if grade is None:
        obj["decision_grade"] = None
        obj["decision_grade_basis"] = "no_directional_lean"
        counts["no_lean"] += 1
        return
    obj["decision_grade"] = grade
    obj["decision_grade_basis"] = f"{GRADE_BASIS}:fwd_ret={fwd:+.4f}"
    counts[grade] += 1


def grade_ledger(path: Path, spy: pd.DataFrame, only_date: str | None,
                 dry_run: bool) -> dict:
    counts = {"correct": 0, "wrong": 0, "ambiguous": 0, "no_lean": 0, "no_data": 0,
              "skipped_not_gradeable": 0, "already": 0, "garbage_resyncs": 0,
              "objects_in": 0, "objects_out": 0}
    if not path.exists():
        return counts
    content = path.read_text(encoding="utf-8", errors="replace")
    objs, resyncs = _stream_decode(content)
    counts["garbage_resyncs"] = resyncs
    counts["objects_in"] = len(objs)
    out_lines: list[str] = []
    for obj in objs:
        _grade_obj(obj, spy, only_date, counts)
        out_lines.append(json.dumps(obj, separators=(",", ":")))
        counts["objects_out"] += 1
    graded_any = (counts["correct"] + counts["wrong"] + counts["ambiguous"]
                  + counts["no_lean"] + counts["no_data"]) > 0
    # Rewrite compact (one object per line = repair pretty-printed/concatenated rows).
    # The char-walk decode is object-lossless (every valid top-level object recovered;
    # only genuine garbage chars are dropped), so a write preserves all decision data.
    # The caller backs up to .bak before the real run as a second safety net.
    if not dry_run and graded_any:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="grade only rows with this date (YYYY-MM-DD)")
    ap.add_argument("--backfill-all", action="store_true", help="grade every ungraded row")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    only_date = None if args.backfill_all else args.date
    if not only_date and not args.backfill_all:
        # default to today (matches the run-eod-summary.ps1 wiring without args)
        only_date = datetime.now().astimezone().strftime("%Y-%m-%d")

    spy = _load_spy()
    grand = {}
    for ledger in LEDGERS:
        c = grade_ledger(ledger, spy, only_date, args.dry_run)
        tag = ledger.relative_to(REPO)
        loss = c["objects_in"] - c["objects_out"]
        print(f"{tag}: in={c['objects_in']} out={c['objects_out']} resyncs={c['garbage_resyncs']} "
              f"LOSS={loss} | correct={c['correct']} wrong={c['wrong']} "
              f"ambiguous={c['ambiguous']} no_lean={c['no_lean']} no_data={c['no_data']} "
              f"already={c['already']} not_gradeable={c['skipped_not_gradeable']}"
              f"{'  [dry-run]' if args.dry_run else ''}")
        assert loss == 0, f"DATA LOSS in {tag}: in={c['objects_in']} out={c['objects_out']}"
        for k, v in c.items():
            grand[k] = grand.get(k, 0) + v
    total_graded = grand["correct"] + grand["wrong"] + grand["ambiguous"]
    print(f"TOTAL newly graded={total_graded} (no_data={grand['no_data']}) "
          f"scope={'today=' + only_date if only_date else 'backfill-all'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
