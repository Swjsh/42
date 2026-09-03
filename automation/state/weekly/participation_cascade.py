"""participation_cascade.py -- weekly-lane JOINT GATE CASCADE instrument. THE LOAD-BEARING
GUARD for the weekly-options program (arm weekly-1).

WHY (integrator build task, 2026-08-18; mirrors backtest/tools/participation_cascade.py's own
C15 doctrine -- "gates interact multiplicatively -- trace session cascades"). Both critics who
reviewed this program named an unmeasured joint gate-cascade as the single biggest risk:
weekly_core.py stacks SIX hard AND-gates (liquidity, min-dte, earnings-blackout,
expiry-availability, concurrency, correlation) on top of a strict zone+trigger requirement --
exactly the mechanism (L199) that already produced "6 arms, 700 signals, 0 trades" on the SPY
side before anyone measured the joint funnel. This instrument answers "of everything we looked
at, how many survived each gate, and where does the funnel die" purely from the ACTUAL LOGGED
FIELDS setup/scripts/weekly_core.py already writes to
automation/state/weekly/shadow-ledger.jsonl -- it never re-runs the engine, exactly like its
SPY-side counterpart.

CONSISTENCY WITH THE SPY-SIDE INSTRUMENT (backtest/tools/participation_cascade.py -- read in
full before writing this one, per the build task's own instruction to search for and mirror an
existing funnel instrument if one exists): that instrument reconstructs a funnel from
MULTIPLE heterogeneous per-TICK ledger sources (core-decisions.jsonl + 4 fleet arms'
decisions.jsonl) with a run-length-encoding dedup step, because the SPY engine logs one row
per 1-MINUTE TICK and the same signal can repeat across many consecutive ticks.
weekly_core.py's shadow ledger is structurally simpler: ONE row per SYMBOL per RUN (the
lane's cadence is not yet fixed -- program doc Sec7 step 5), and every row is ALREADY a
TERMINAL, single-stage classification (weekly_core.py's own `stage` field -- the STAGE_*
constants duplicated below verbatim, in weekly_core's own pipeline order). No dedup/RLE step
is needed as a result -- a documented, deliberate simplification, not an oversight: if a
future cadence starts producing multiple rows per symbol per day, this module's per-day
aggregation already treats every row as its own event (nothing here assumes at-most-one-row-
per-symbol-per-day), so it degrades gracefully rather than silently double-counting anything
misleading -- re-adding SPY-side-style dedup would be a non-breaking follow-up, not a redesign.

FUNNEL PIPELINE (== weekly_core.py's STAGE constants, in weekly_core's own execution order --
the task's requested checkpoint names in parens):
  symbols evaluated -> (zone present) -> (trigger fired) -> (liquidity pass) ->
  (min-DTE pass) -> (earnings-blackout pass) -> (expiry-available) ->
  (concurrency pass / correlation pass) -> (would-place)
STAGE_NO_DATA rows (bars/contracts/earnings-feed unreadable) are EXCLUDED from the funnel's
ranked pipeline (a data failure is a pre-condition problem, not a scored gate outcome -- the
same "non-scoring" treatment the SPY-side instrument gives NO_DATA/NO_SIGNAL) but are counted
and disclosed on every result (`n_data_errors_excluded_from_funnel`, never silently dropped,
matching the SPY sibling's `n_synthetic_core_rows_excluded` OP-33 precedent).

Each row's `stage` is TERMINAL by construction (weekly_core.py's `_row` builder returns
exactly one stage per row), so "how far did this row get" reduces to a simple RANK lookup --
see `_RANK` / `CHECKPOINT_LABELS`. `compute_cascade_day` derives every checkpoint's
CUMULATIVE pass count (how many rows got AT LEAST that far) directly from those ranks: no
re-implementation of weekly_core's own gate logic lives here, only the classification the
ledger rows already carry.

OUTPUT: automation/state/weekly/participation-cascade.jsonl -- APPEND-ONLY (never
overwritten; a day computed twice appends twice, matching this repo's append-only jsonl
convention everywhere else -- a reader wanting the freshest read for a date takes the LAST
matching line). `summarize_range` is the "why zero signals, in one command" entry point: pass
any [start, end] ISO-date window and get funnel totals + the ranked blocker leaderboard back,
no forensic ledger-grepping required.

CLI:  backtest/.venv/Scripts/python.exe automation/state/weekly/participation_cascade.py
      [--date YYYY-MM-DD] [--sessions N] [--start YYYY-MM-DD --end YYYY-MM-DD] [--write]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# automation/state/weekly/participation_cascade.py -> weekly -> state -> automation -> 42/
REPO = Path(__file__).resolve().parents[3]
WEEKLY_STATE = Path(__file__).resolve().parent
LEDGER_PATH = WEEKLY_STATE / "shadow-ledger.jsonl"
CASCADE_JSONL_PATH = WEEKLY_STATE / "participation-cascade.jsonl"
ARM = "weekly-1"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001 -- fail-open, mirrors the SPY-side instrument's own precedent
    def et_now() -> dt.datetime:
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

# Must equal setup/scripts/weekly_core.py's STAGE_* constants. Duplicated as PLAIN STRINGS
# (not imported from weekly_core.py) so this instrument reads the LEDGER'S OWN WRITTEN
# VALUES rather than coupling to weekly_core's live Python module -- exactly the
# "reconstructs from LOGGED fields, never re-runs the engine" contract this docstring opens
# with (mirrors the SPY-side instrument's own independence from heartbeat_core.py's source).
STAGE_NO_DATA = "NO_DATA"
STAGE_NO_ZONE = "NO_ZONE"
STAGE_NO_TRIGGER = "NO_TRIGGER"
STAGE_LIQUIDITY_BLOCK = "LIQUIDITY_BLOCK"
STAGE_MIN_DTE_BLOCK = "MIN_DTE_BLOCK"
STAGE_EARNINGS_BLACKOUT_BLOCK = "EARNINGS_BLACKOUT_BLOCK"
STAGE_EXPIRY_UNAVAILABLE_BLOCK = "EXPIRY_UNAVAILABLE_BLOCK"
STAGE_CONCURRENCY_BLOCK = "CONCURRENCY_BLOCK"
STAGE_CORRELATION_BLOCK = "CORRELATION_BLOCK"
STAGE_WOULD_PLACE = "WOULD_PLACE"

# Ordered pipeline (NO_DATA excluded -- see module docstring). Index i == "the terminal
# failure/success stage a row stopped at, at pipeline position i".
ORDERED_STAGES = (
    STAGE_NO_ZONE, STAGE_NO_TRIGGER, STAGE_LIQUIDITY_BLOCK, STAGE_MIN_DTE_BLOCK,
    STAGE_EARNINGS_BLACKOUT_BLOCK, STAGE_EXPIRY_UNAVAILABLE_BLOCK, STAGE_CONCURRENCY_BLOCK,
    STAGE_CORRELATION_BLOCK, STAGE_WOULD_PLACE,
)
# CHECKPOINT_LABELS[i] = "did the row get PAST ORDERED_STAGES[i]'s own failure mode" for
# i < len-1, and "did the row land exactly on WOULD_PLACE" for the last one. See
# compute_cascade_day's funnel-building loop for the exact pass-count semantics.
CHECKPOINT_LABELS = (
    "zone_present", "trigger_fired", "liquidity_pass", "min_dte_pass",
    "earnings_blackout_pass", "expiry_available_pass", "concurrency_pass",
    "correlation_pass", "would_place",
)
_RANK = {s: i for i, s in enumerate(ORDERED_STAGES)}
_RANK[STAGE_NO_DATA] = -1  # excluded from the ranked pipeline -- see module docstring

_BLOCKED_STAGES = (
    STAGE_LIQUIDITY_BLOCK, STAGE_MIN_DTE_BLOCK, STAGE_EARNINGS_BLACKOUT_BLOCK,
    STAGE_EXPIRY_UNAVAILABLE_BLOCK, STAGE_CONCURRENCY_BLOCK, STAGE_CORRELATION_BLOCK,
)


# ---------------------------------------------------------------------------
# ledger reading (fail-open -- a missing/corrupt file yields [], never a crash)
# ---------------------------------------------------------------------------

def _iter_jsonl(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(o, dict):
            yield o


def _read_rows_for_day(day: str, ledger_path: Path) -> list[dict]:
    return [
        r for r in _iter_jsonl(ledger_path)
        if str(r.get("ts_et") or "").startswith(day) and r.get("arm") == ARM
    ]


def discover_sessions(n: int, *, ledger_path: Path = LEDGER_PATH) -> list[str]:
    """Every ET calendar date that appears in the shadow ledger, ascending, last N (0 = all)."""
    days: set[str] = set()
    for r in _iter_jsonl(ledger_path):
        if r.get("arm") != ARM:
            continue
        ts = str(r.get("ts_et") or "")
        if len(ts) >= 10:
            days.add(ts[:10])
    return sorted(days)[-n:] if n else sorted(days)


def _date_range(start_day: str, end_day: str) -> list[str]:
    start = dt.date.fromisoformat(start_day)
    end = dt.date.fromisoformat(end_day)
    if end < start:
        raise ValueError(f"end_day {end_day} is before start_day {start_day}")
    out: list[str] = []
    d = start
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# per-day cascade
# ---------------------------------------------------------------------------

def compute_cascade_day(day: str, *, ledger_path: Path = LEDGER_PATH) -> dict:
    """Full joint cascade for one ET session day, reconstructed from the shadow ledger's
    OWN `stage` field. Fail-open throughout (a day with zero rows yields an all-zero,
    fully-visible funnel, never a crash or a silently skipped day)."""
    rows = _read_rows_for_day(day, ledger_path)
    ranks = [_RANK.get(r.get("stage"), -1) for r in rows]
    n_data_errors = sum(1 for rk in ranks if rk == -1)

    funnel: dict[str, int] = {}
    for j, label in enumerate(CHECKPOINT_LABELS):
        # "passed checkpoint j" == the row's terminal stage sits STRICTLY PAST stage
        # ORDERED_STAGES[j] in the pipeline (rank > j). For the LAST checkpoint
        # (would_place, j == len-1) nothing can be "strictly past" it, so this correctly
        # yields 0 via the plain rank>j formula UNLESS handled -- would_place is instead
        # "landed exactly on rank j" (the terminal success state itself).
        if label == "would_place":
            funnel[label] = sum(1 for rk in ranks if rk == j)
        else:
            funnel[label] = sum(1 for rk in ranks if rk > j)

    trigger_fired = funnel["trigger_fired"]
    would_place = funnel["would_place"]
    joint_pass_rate = round(100.0 * would_place / trigger_fired, 1) if trigger_fired else None

    blocker_counts: Counter = Counter(
        (r.get("stage"), r.get("gate")) for r in rows if r.get("stage") in _BLOCKED_STAGES
    )
    top_blockers = [
        {"stage": s, "gate": g, "count": n} for (s, g), n in blocker_counts.most_common()
    ]

    if not rows:
        verdict = "NO_DATA_FOR_DAY"
    elif would_place > 0:
        verdict = "WOULD_PLACE_OCCURRED"
    elif trigger_fired == 0:
        verdict = "NO_TRIGGERS"
    else:
        verdict = "GATED_OUT"

    return {
        "date": day,
        "symbols_evaluated": len(rows),
        "n_data_errors_excluded_from_funnel": n_data_errors,
        "funnel": funnel,
        "joint_pass_rate_pct_of_triggered": joint_pass_rate,
        "top_blockers": top_blockers,
        "verdict": verdict,
        "rows": rows,  # full detail -- dropped by _compact_for_jsonl before persisting
    }


def compute_cascade_sessions(n: int = 10, *, ledger_path: Path = LEDGER_PATH) -> list[dict]:
    days = discover_sessions(n, ledger_path=ledger_path)
    return [compute_cascade_day(d, ledger_path=ledger_path) for d in days]


def summarize_range(start_day: str, end_day: str, *, ledger_path: Path = LEDGER_PATH) -> dict:
    """THE 'why zero signals, in one command' entry point -- callable standalone against any
    date range, no forensic ledger-grepping required. Every day in [start_day, end_day]
    (inclusive) is aggregated whether or not the ledger has rows for that specific date (a
    day with zero rows contributes symbols_evaluated=0, visibly, never silently skipped --
    OP-33). This is the module's exposed summary function returning the joint pass rate."""
    days = _date_range(start_day, end_day)
    day_results = [compute_cascade_day(d, ledger_path=ledger_path) for d in days]
    total_evaluated = sum(d["symbols_evaluated"] for d in day_results)
    total_data_errors = sum(d["n_data_errors_excluded_from_funnel"] for d in day_results)
    total_triggered = sum(d["funnel"]["trigger_fired"] for d in day_results)
    total_would_place = sum(d["funnel"]["would_place"] for d in day_results)
    joint_pass_rate = (
        round(100.0 * total_would_place / total_triggered, 1) if total_triggered else None
    )
    blocker_totals: Counter = Counter()
    for d in day_results:
        for b in d["top_blockers"]:
            blocker_totals[(b["stage"], b["gate"])] += b["count"]
    return {
        "start_date": start_day, "end_date": end_day, "n_days": len(days),
        "symbols_evaluated": total_evaluated,
        "n_data_errors_excluded_from_funnel": total_data_errors,
        "trigger_fired": total_triggered, "would_place": total_would_place,
        "joint_pass_rate_pct_of_triggered": joint_pass_rate,
        "top_blockers": [
            {"stage": s, "gate": g, "count": n} for (s, g), n in blocker_totals.most_common()
        ],
        "daily": [
            {"date": d["date"], "symbols_evaluated": d["symbols_evaluated"],
             "trigger_fired": d["funnel"]["trigger_fired"], "would_place": d["funnel"]["would_place"],
             "verdict": d["verdict"]}
            for d in day_results
        ],
    }


# ---------------------------------------------------------------------------
# artifact writer (append-only jsonl)
# ---------------------------------------------------------------------------

def _compact_for_jsonl(f: dict) -> dict:
    """Drop the full per-row detail before persisting -- mirrors the SPY-side instrument's
    `_compact_for_state` (the funnel counts + top_blockers already carry everything a glance
    needs; full row detail stays in shadow-ledger.jsonl itself, re-readable any time)."""
    return {k: v for k, v in f.items() if k != "rows"}


def append_cascade_row(
    day_result: dict, *, path: Path = CASCADE_JSONL_PATH, now_et: Optional[dt.datetime] = None,
) -> Path:
    """APPEND one compact JSON line for this day's cascade to the standing jsonl ledger --
    never overwritten (see module docstring). Fail-loud: propagates any OSError rather than
    silently swallowing a write failure (this is a state producer, not a best-effort probe)."""
    now_et = now_et or et_now()
    row = {**_compact_for_jsonl(day_result), "generated_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S")}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return path


# ---------------------------------------------------------------------------
# renderer
# ---------------------------------------------------------------------------

def render_day_text(f: dict) -> str:
    jp = f["joint_pass_rate_pct_of_triggered"]
    jp_str = "n/a" if jp is None else f"{jp:.1f}%"
    out = [
        f"CASCADE {f['date']}  [{f['verdict']}]  evaluated={f['symbols_evaluated']} "
        f"data_errors={f['n_data_errors_excluded_from_funnel']} "
        f"joint_pass_rate_of_triggered={jp_str}"
    ]
    for label in CHECKPOINT_LABELS:
        out.append(f"  {label:<24}{f['funnel'][label]}")
    if f["top_blockers"]:
        out.append("  blockers (triggered symbols killed, ranked):")
        for b in f["top_blockers"]:
            out.append(f"    {b['count']:>3}x [{b['stage']}] gate={b['gate']}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="weekly-1 participation cascade -- joint gate funnel (C15 mirror), THE load-bearing guard"
    )
    ap.add_argument("--date", default=None, help="single ET date YYYY-MM-DD (default: latest session in the ledger)")
    ap.add_argument("--start", default=None, help="range start YYYY-MM-DD (pair with --end)")
    ap.add_argument("--end", default=None, help="range end YYYY-MM-DD (pair with --start)")
    ap.add_argument("--sessions", type=int, default=10, help="how many trailing sessions (default 10)")
    ap.add_argument("--write", action="store_true",
                     help="append to automation/state/weekly/participation-cascade.jsonl")
    args = ap.parse_args()

    if args.start and args.end:
        summary = summarize_range(args.start, args.end)
        print(json.dumps(summary, indent=1))
        return 0

    if args.date:
        days = [args.date]
    else:
        days = discover_sessions(args.sessions)
        if not days:
            print("[participation_cascade] no weekly-1 rows found in the shadow ledger yet.")
            return 0

    for day in days:
        f = compute_cascade_day(day)
        print(render_day_text(f))
        print()
        if args.write:
            p = append_cascade_row(f)
            print(f"[participation_cascade] appended {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
