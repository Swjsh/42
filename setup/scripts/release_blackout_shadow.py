#!/usr/bin/env python
"""release_blackout_shadow.py -- FORWARD ACCRUAL for the scheduled-release blackout candidates
R1/R2/R3 (queue: B2 SCHEDULED-RELEASE-BLACKOUT, filed 2026-09-03, stamp 12:40 ET), per the
PRE-REGISTERED bar + decision rule in
`analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md`.

BACKGROUND. `backtest/tools/release_gap_study.py`'s historical read (44 cached trading days
2026-06-26..2026-09-02 + today's real fills, see `analysis/deep-research/2026-09-03-money/
release-gap-study.md`) found NONE of R1/R2/R3 clears "net >= 0 after drop-best-day" with real
(multi-day) evidence: R1 and R3 pass only via a single trading day's worth of correlated legs
(degenerate, not evidence); R2 (a comparison arm only, never itself ship-eligible) fails
outright once its one positive day is dropped. Per the prereg's own DO-NOT, that verdict is
not re-litigated on the same (already-seen) data -- the only clean path is a forward shadow
scored on release days nobody has seen yet, exactly the same two-DO-NOT contract
`tp1_r50_forward_shadow.py`'s own docstring states for its sibling instrument.

WHAT IT MEASURES, PER ISM RELEASE DAY (never touches non-ISM days -- R2 is a comparison arm
only per the prereg and is logged for transparency but is never ship-eligible)
-------------------------------------------------------------------------------------------
For every ISM (tier-1, `severity="high"`) release day on/after `ACCRUAL_START_DATE` whose
session is COMPLETE (strictly before "today", or today at/after 16:00 ET):
  1. **Moves** (informational only, logged separately from rule application -- see the
     NO-LOOK-AHEAD section below): the SPY $ and per-contract option % move across
     10:00->10:01 ET, sourced from whichever cache has the data THAT NIGHT --
     `backtest/data/highres/<OCC>_1m_<date>.csv` + `backtest/data/spy_sip_cache/spy_1m_<date>.
     json` once archived (preferred, same metrics as `release_gap_study.py`'s historical
     study -- EXTEND, DON'T FORK, imported not re-derived), else `analysis/quote-tape/<date>.
     jsonl` (bid/ask ticks, ~20s polling cadence -- the largest single-poll-to-poll drop in a
     padded [09:55,10:05) ET window, since a strict minute-bucket comparison can straddle-miss
     a gap between two polls; see `_quote_tape_option_moves`'s own docstring for the concrete
     case this was caught on. Option side only -- quote-tape carries no SPY underlying quote)
     for a date still within its ~3-day retention window, else `move_source="no_data"` --
     reported honestly, never guessed.
  2. **Rule application** to that day's REAL fills (`automation/state/fills-ledger.jsonl` via
     `release_gap_study.build_scored_positions`): which positions R1 (entries [09:45,10:05))
     and R2 (entries [09:35,10:05), comparison-only) would have removed, and which positions
     R3 (R1 + flatten open-at-09:58) would have flattened, with the SAME per-trade dollar
     accounting `release_gap_study.py` uses (imported `r3_delta_for_position`, not
     re-derived).

⛔ NO LOOK-AHEAD, STRUCTURALLY ENFORCED (guarded by `test_release_blackout_shadow_2026_09_03.
py::test_rule_reads_calendar_never_realized_move`): `_apply_rules_for_date()` -- the function
that decides which trades R1/R2/R3 touch -- takes ONLY `(date, day_positions)`; its signature
carries no move/gap parameter at all, so it CANNOT read the release's realized size even by
accident. It uses only `scheduled_releases(date)` (the calendar, known premarket) and each
position's own `entry_ts_et` (already known at order-placement time). `_load_moves_for_date()`
is called completely separately and its result is merged into the row only AFTER rule
application returns -- moves are informational evidence for the prereg's 15%-adverse-move bar,
never an input to which trades the rule removes.

NO BACKFILL. `ACCRUAL_START_DATE` is pinned to this build's own date (2026-09-03) -- today
is itself an ISM day, so the very first scheduled run already contributes real forward
evidence, exactly the situation `tp1_r50_forward_shadow.py`'s docstring describes as the
"clock starts at the first scheduled run."

EXTEND, DON'T FORK -- everything below is imported, not re-typed:
  setup/scripts/macro_calendar.py#scheduled_releases      B1's release calendar
  backtest/tools/release_gap_study.py                     build_scored_positions, option/spy
                                                            bar loaders + gap metrics, R3's
                                                            per-position delta math, the
                                                            day-clustered bootstrap CI /
                                                            top-3-concentration / drop-best-day
                                                            helpers, BIG_WIN_DAYS

COST: $0. Pure local computation over already-cached files -- zero network calls, zero LLM
calls, zero broker calls (same contract as `tp1_r50_forward_shadow.py`).

Outputs:
  analysis/recommendations/release-blackout-shadow-ledger.jsonl   append-only, dedup on date_et
  analysis/recommendations/release-blackout-shadow-summary.json   running totals + bar/gate status
"""
from __future__ import annotations

import collections
import datetime as dt
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts"), str(REPO / "backtest" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import macro_calendar as mc              # noqa: E402  -- B1 deliverable
import release_gap_study as rgs          # noqa: E402  -- EXTEND, DON'T FORK

QUOTE_TAPE_DIR = REPO / "analysis" / "quote-tape"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "release-blackout-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "release-blackout-shadow-summary.json"
PREREG_REL = "analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md"

ACCRUAL_START_DATE = "2026-09-03"        # this build's own date -- no backfill
BAR_MIN_ISM_DAYS = 3
BAR_MIN_DAYS_GE15PCT = 2
ADVERSE_THRESHOLD_PCT = -15.0


# ============================================================================================
# ledger I/O (same tolerant-of-a-torn-last-line contract as tp1_r50_forward_shadow._read_ledger)
# ============================================================================================
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
            continue          # a torn last line must never kill the accrual
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


def _today_et() -> dt.date:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().date()
    except Exception:  # noqa: BLE001
        return dt.date.today()


def _now_time_et() -> dt.time:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().time()
    except Exception:  # noqa: BLE001
        return dt.time(0, 0)


# ============================================================================================
# candidate date selection -- forward-only, ISM-only, session-complete only
# ============================================================================================
def _date_is_complete(date_str: str, today: dt.date, now_time: dt.time) -> bool:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    if d < today:
        return True
    if d == today:
        return now_time >= dt.time(16, 0)     # after the 15:55 flatten + a safety margin
    return False


def candidate_dates(today: Optional[dt.date] = None, now_time: Optional[dt.time] = None) -> list[str]:
    """Every ISM day in [ACCRUAL_START_DATE, today], session-complete, weekday only. Whether
    it is an actual trading day (vs an unscheduled holiday `scheduled_releases`'s own NYSE-
    holiday table doesn't know about) is irrelevant to correctness here -- a date with no
    engine fills simply yields zero R1/R2/R3-affected positions, logged honestly as such."""
    today = today or _today_et()
    now_time = now_time if now_time is not None else _now_time_et()
    start = dt.datetime.strptime(ACCRUAL_START_DATE, "%Y-%m-%d").date()
    out = []
    d = start
    while d <= today:
        if d.weekday() < 5:
            date_str = d.isoformat()
            if mc.scheduled_releases(date_str) and _is_ism_date(date_str) and _date_is_complete(date_str, today, now_time):
                out.append(date_str)
        d += dt.timedelta(days=1)
    return out


def _is_ism_date(date_str: str) -> bool:
    events = mc.scheduled_releases(date_str)
    return any(e.get("time_et") == "10:00" and e.get("type", "").startswith("ism_") for e in events)


# ============================================================================================
# moves (informational only -- NEVER read by _apply_rules_for_date)
# ============================================================================================
def _load_quote_tape_ticks(date_str: str) -> list[dict]:
    f = QUOTE_TAPE_DIR / f"{date_str}.jsonl"
    if not f.exists():
        return []
    ticks = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ticks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return ticks


QUOTE_TAPE_WINDOW_START = "09:55:00"     # padded window around 10:00 -- see note below
QUOTE_TAPE_WINDOW_END = "10:05:00"


def _quote_tape_option_moves(date_str: str) -> list[dict]:
    """Quote-tape polls roughly every ~20s (sight-beacon cadence), NOT a fixed 1-min grid --
    a strict minute-bucket comparison (close-of-09:59-bucket vs close-of-10:00-bucket, the
    `highres`-cache convention `release_gap_study.py` uses) can miss a gap that straddles a
    bucket boundary between two polls. Confirmed on today's own 770C tape: the 0.735->0.495
    drop (the exact gap `dissect-wave-autopsy.md` documents) happened between the poll at
    10:00:48 and the poll at 10:01:10 -- a strict "close(10:00 bucket) vs close(09:59 bucket)"
    comparison would have caught only a -6.4% move (both ends still pre-drop) and silently
    understated the real -32.7% single-poll-to-poll gap. So for THIS source only, the metric
    is the LARGEST single-poll-to-poll drop between consecutive ticks anywhere inside a padded
    [09:55, 10:05) ET window -- a deliberately different, coarser methodology than the
    highres-cache path, labeled `source="quote_tape_adjacent_tick"` (never silently conflated
    with the bar-close methodology)."""
    ticks = _load_quote_tape_ticks(date_str)
    if not ticks:
        return []
    by_symbol: dict[str, list[dict]] = collections.defaultdict(list)
    for t in ticks:
        sym = t.get("symbol")
        te = t.get("ts_et", "")
        if sym and len(te) >= 19 and QUOTE_TAPE_WINDOW_START <= te[11:19] < QUOTE_TAPE_WINDOW_END:
            by_symbol[sym].append(t)
    out = []
    for sym, tks in by_symbol.items():
        tks.sort(key=lambda t: t.get("ts_et", ""))
        mids = [t.get("mid") for t in tks if t.get("mid") is not None]
        worst_pct = None
        for prev, cur in zip(mids, mids[1:]):
            if prev and prev > 0:
                pct = (cur - prev) / prev * 100
                if worst_pct is None or pct < worst_pct:
                    worst_pct = pct
        if worst_pct is not None:
            out.append({"symbol": sym, "move_1000_1001_pct": round(worst_pct, 3),
                        "source": "quote_tape_adjacent_tick",
                        "window": f"{QUOTE_TAPE_WINDOW_START}-{QUOTE_TAPE_WINDOW_END}"})
    return out


def _load_moves_for_date(date_str: str) -> dict:
    """Informational-only move measurement, sourced highres-cache first, quote-tape fallback,
    else honestly reported as unavailable. NEVER consulted by `_apply_rules_for_date`."""
    opt_files = rgs.option_files_for_date(date_str)
    spy_bars = rgs.load_spy_bars(date_str)
    if opt_files:
        contract_moves = []
        for f in opt_files:
            m = rgs.OPT_FILE_RE.match(f.name)
            occ = m.group(1) if m else f.stem
            gm = rgs.option_gap_metrics(rgs.load_option_bars(f))
            if gm:
                gm["symbol"] = occ
                contract_moves.append(gm)
        spy_m = rgs.spy_gap_metrics(spy_bars) if spy_bars else None
        worst = min((c["move_1000_1001_pct"] for c in contract_moves), default=None)
        return {
            "move_source": "highres_cache",
            "spy_move_1000_1001_dollars": (spy_m["move_1000_1001_dollars"] if spy_m else None),
            "option_moves": contract_moves,
            "worst_adverse_1000_1001_pct": (round(worst, 3) if worst is not None else None),
        }
    qt_moves = _quote_tape_option_moves(date_str)
    if qt_moves:
        worst = min(c["move_1000_1001_pct"] for c in qt_moves)
        return {
            "move_source": "quote_tape",
            "spy_move_1000_1001_dollars": None,      # quote-tape carries no SPY underlying quote
            "option_moves": qt_moves,
            "worst_adverse_1000_1001_pct": round(worst, 3),
        }
    return {"move_source": "no_data", "spy_move_1000_1001_dollars": None,
            "option_moves": [], "worst_adverse_1000_1001_pct": None}


# ============================================================================================
# rule application -- NO move-data parameter, structurally cannot look ahead (see docstring)
# ============================================================================================
def _apply_rules_for_date(date_str: str, day_positions: list[dict]) -> dict:
    """Decides which trades R1/R2/R3 touch using ONLY the calendar date (already-ISM by
    construction -- caller filters) and each position's own entry_ts_et / leg timestamps.
    Signature deliberately excludes any move/gap value -- see module docstring and
    `test_rule_reads_calendar_never_realized_move`."""
    r1_trades = [p for p in day_positions if p.get("entry_in_0945_1005") and p["fully_closed"]]
    r2_trades = [p for p in day_positions if p.get("entry_in_0935_1005") and p["fully_closed"]]

    bar_cache: dict[tuple, dict] = {}
    r3_included, r3_excluded = [], collections.defaultdict(int)
    for p in day_positions:
        res = rgs.r3_delta_for_position(p, bar_cache)
        if res["included"]:
            r3_included.append(res)
        else:
            r3_excluded[res["exclude_reason"]] += 1

    return {
        "r1": {"n_removed": len(r1_trades), "net_saved": round(sum(-p["realized_pnl"] for p in r1_trades), 2),
               "trades": [{"activity_id": p["activity_id"], "arm": p["arm"], "symbol": p["symbol"],
                           "realized_pnl": p["realized_pnl"]} for p in r1_trades]},
        "r2": {"n_removed": len(r2_trades), "net_saved": round(sum(-p["realized_pnl"] for p in r2_trades), 2),
               "trades": [{"activity_id": p["activity_id"], "arm": p["arm"], "symbol": p["symbol"],
                           "realized_pnl": p["realized_pnl"]} for p in r2_trades]},
        "r3": {"n_flattened": len(r3_included), "net_delta": round(sum(r["delta"] for r in r3_included), 2),
               "trades": r3_included, "exclusions": dict(r3_excluded)},
    }


assert "move" not in {p.lower() for p in inspect.signature(_apply_rules_for_date).parameters}, (
    "_apply_rules_for_date must never accept a move/gap parameter -- no-look-ahead contract")


# ============================================================================================
# per-day row + summary
# ============================================================================================
def build_row(date_str: str, all_positions: list[dict]) -> dict:
    day_positions = [p for p in all_positions if p["date_et"] == date_str]
    rules = _apply_rules_for_date(date_str, day_positions)      # calendar + fills ONLY
    moves = _load_moves_for_date(date_str)                       # separate, informational
    meets_threshold = (moves["worst_adverse_1000_1001_pct"] is not None
                       and moves["worst_adverse_1000_1001_pct"] <= ADVERSE_THRESHOLD_PCT)
    return {
        "date_et": date_str,
        "logged_at_et": _stamp_now_et(),
        "n_positions_that_day": len(day_positions),
        **moves,
        "meets_15pct_adverse_threshold": meets_threshold,
        "r1": rules["r1"], "r2": rules["r2"], "r3": rules["r3"],
        "no_look_ahead_note": ("rule membership computed from scheduled_releases(date) + each "
                               "position's own entry_ts_et only -- never from the move measured "
                               "in this same row (see _apply_rules_for_date signature guard)"),
    }


def _summarize(rows: list[dict]) -> dict:
    n_days = len(rows)
    n_ge15 = sum(1 for r in rows if r["meets_15pct_adverse_threshold"])
    bar_met = (n_days >= BAR_MIN_ISM_DAYS) and (n_ge15 >= BAR_MIN_DAYS_GE15PCT)

    def rule_summary(key: str) -> dict:
        by_day: dict[str, list[float]] = collections.defaultdict(list)
        for r in rows:
            trades = r[key]["trades"]
            if key == "r3":
                vals = [t["delta"] for t in trades]
            else:
                vals = [-t["realized_pnl"] for t in trades]
            if vals:
                by_day[r["date_et"]].extend(vals)
        total_field = "net_delta" if key == "r3" else "net_saved"
        total = round(sum(r[key][total_field] for r in rows), 2)
        ci = rgs.bootstrap_day_clustered_mean(by_day) if by_day else None
        dbd = rgs.drop_best_day(by_day) if by_day else {"best_day": None, "best_day_total": 0.0,
                                                          "total": total, "ex_best_day_total": total}
        big_days_touched = sorted(set(by_day.keys()) & set(rgs.BIG_WIN_DAYS))
        return {"total": total, "n_days_with_effect": len(by_day),
                "session_clustered_ci": ci, "drop_best_day": dbd,
                "big_win_days_touched": big_days_touched}

    r1_sum, r2_sum, r3_sum = rule_summary("r1"), rule_summary("r2"), rule_summary("r3")

    def ship_verdict(rule_sum: dict) -> str:
        if not bar_met:
            return "BAR_NOT_MET"
        ok = (rule_sum["drop_best_day"]["ex_best_day_total"] >= 0
              and not rule_sum["big_win_days_touched"])
        return "CLEARS_BAR_SHIP_CANDIDATE" if ok else "BAR_MET_BUT_FAILS_DECISION_RULE"

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "accrual_start": ACCRUAL_START_DATE,
        "n_ism_release_days_accrued": n_days,
        "n_days_meeting_15pct_adverse_threshold": n_ge15,
        "bar": {"min_ism_days": BAR_MIN_ISM_DAYS, "min_days_ge15pct": BAR_MIN_DAYS_GE15PCT},
        "bar_met": bar_met,
        "status": "BAR_MET_AWAITING_VERDICT" if bar_met else "ACCRUING",
        "R1": {**r1_sum, "ship_verdict": ship_verdict(r1_sum), "note": "ship candidate"},
        "R2": {**r2_sum, "ship_verdict": "NEVER_SHIP_ELIGIBLE",
               "note": "comparison arm only per the prereg -- never ships regardless of numbers"},
        "R3": {**r3_sum, "ship_verdict": ship_verdict(r3_sum),
               "note": "ship candidate, KILL_TYPE_REDUCTION (bundle-eligible 2026-09-29 if it clears)"},
        "decision_rule": (
            "Neither R1 nor R3 may ship until bar_met=True AND that rule's drop_best_day."
            "ex_best_day_total >= 0 AND big_win_days_touched is empty AND (per the prereg's "
            "falsifier) at least 2 of the first 5 forward ISM days show a >=15% adverse move. "
            f"See {PREREG_REL} -- not softened here."),
    }


def _input_health(all_positions: list[dict]) -> dict:
    newest = max((p.get("date_et", "") for p in all_positions), default="")
    today = _today_et()
    back = 1 if today.weekday() != 0 else 3
    prev_session = today - dt.timedelta(days=back)
    while prev_session.weekday() >= 5:
        prev_session -= dt.timedelta(days=1)
    stale = bool(newest) and newest < prev_session.isoformat()
    return {"input_fills_ledger_newest_date": newest or None,
            "input_expected_through": prev_session.isoformat(),
            "input_stale": stale,
            "input_note": ("STALE -- fills-ledger.jsonl has not advanced to the last completed "
                           "session; this clock is not being fed." if stale else "fed")}


# ============================================================================================
def run() -> dict:
    """Nightly entry point. Fail-open by contract, own scheduled task (never folded into
    another producer's try-block), same shape as tp1_r50_forward_shadow.run()."""
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen_dates = {r.get("date_et") for r in existing}

        all_positions = rgs.build_scored_positions()
        candidates = [d for d in candidate_dates() if d not in seen_dates]

        appended = []
        for d in candidates:
            appended.append(build_row(d, all_positions))

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for row in appended:
                    fh.write(json.dumps(row) + "\n")

        all_rows = existing + appended
        summary = _summarize(all_rows)
        summary["new_this_run"] = len(appended)
        summary["new_dates_this_run"] = [r["date_et"] for r in appended]
        summary.update(_input_health(all_positions))
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:300], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
