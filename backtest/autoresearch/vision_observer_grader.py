"""EOD grader for the chart-vision observer layer.

Pairs vision observations from `automation/state/vision-observations.jsonl` with
heartbeat decisions from `automation/state/decisions.jsonl` for the same date and
nearest tick, then grades each pair against next-bar actual SPY close from the
master 5m CSV.

Produces `analysis/vision-vs-heartbeat-{date}.json` with per-tick comparison and
aggregate accuracy. The output drives the 20-day promotion-path decision per
OP-21: if vision accuracy beats heartbeat accuracy in DIVERGED cases by >= 10pp
across 20+ trading days, propose ratification of a vision-veto branch.

Usage:
    python -m autoresearch.vision_observer_grader --date 2026-05-17

Wired into `backtest/autoresearch/eod_deep/main.py` as Stage 4a.6 (alongside the
existing self-heal skills suite).

Hard constraints:
    - Does NOT touch live state files.
    - Pure-Python (no LLM cost).
    - Stream-reads vision-observations.jsonl one line at a time (append-only log
      can grow large; do not slurp).
    - Fail-soft on every record — bad JSON / missing fields go in
      ``ingest_warnings`` and processing continues.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

REPO = Path(__file__).resolve().parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

VISION_JSONL = REPO / "automation" / "state" / "vision-observations.jsonl"
DECISIONS_JSONL = REPO / "automation" / "state" / "decisions.jsonl"
ANALYSIS_DIR = REPO / "analysis"
SPY_CSV_DIR = REPO / "backtest" / "data"

# Direction-call enum (vision side). Heartbeat side maps via _map_heartbeat_action.
VISION_DIRS = {"bull", "bear", "chop", "unclear"}

# Heartbeat -> vision-direction mapping. HOLD / HOLD_DEV / SKIP -> "chop";
# ENTER_BULL -> "bull"; ENTER_BEAR -> "bear"; anything else -> "unclear".
def _map_heartbeat_action(action: str) -> str:
    if not action:
        return "unclear"
    a = action.upper()
    if a == "ENTER_BULL" or a == "ADD_BULL":
        return "bull"
    if a == "ENTER_BEAR" or a == "ADD_BEAR":
        return "bear"
    if a in ("HOLD", "HOLD_DEV", "SKIP", "WAIT", "WATCH", "EXIT_STOP", "EXIT_TP1", "EXIT_RUNNER", "EXIT_TIME"):
        return "chop"
    return "unclear"


# === Data classes ===

@dataclass(frozen=True)
class VisionObservation:
    """One line from vision-observations.jsonl."""
    tick_id: int
    date: str
    time_et: str
    price_now: Optional[float]
    direction_call: str
    confidence: int
    in_progress_pattern: str
    level_interaction: dict
    momentum: str
    horizon_minutes: int
    grounded_against_ohlcv: bool
    raw: dict


@dataclass(frozen=True)
class HeartbeatDecision:
    """One line from decisions.jsonl."""
    tick_id: int
    date: str
    time_et: str
    action: str
    direction_mapped: str
    bull_score: Optional[int]
    bear_score: Optional[int]
    spy: Optional[float]
    reason: str
    raw: dict


@dataclass(frozen=True)
class PairedTick:
    """A vision obs and a heartbeat decision at the same date+tick (or near-tick)."""
    tick_id: int
    date: str
    time_et: str
    vision: Optional[VisionObservation]
    heartbeat: Optional[HeartbeatDecision]
    tag: str  # ALIGNED | DIVERGED | vision_only | heartbeat_only
    next_bar_close: Optional[float]
    next_bar_direction: Optional[str]  # bull | bear | flat (computed from |delta| < 0.05)
    vision_correct: Optional[bool]
    heartbeat_correct: Optional[bool]


@dataclass
class Aggregate:
    """Per-day aggregate scorecard."""
    date: str
    total_paired_ticks: int = 0
    aligned: int = 0
    diverged: int = 0
    vision_only: int = 0
    heartbeat_only: int = 0
    vision_correct_n: int = 0
    vision_graded_n: int = 0
    heartbeat_correct_n: int = 0
    heartbeat_graded_n: int = 0
    diverged_vision_correct: int = 0
    diverged_heartbeat_correct: int = 0
    diverged_graded: int = 0
    ingest_warnings: list = field(default_factory=list)


# === Ingest ===

def _stream_jsonl(path: Path, on_date: str) -> Iterable[dict]:
    """Yield parsed JSON objects from a .jsonl file, filtered to one date.

    Stream-read one line at a time. Bad JSON lines are skipped and a warning
    yielded as a special record `{"_warning": "..."}`.
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                yield {"_warning": f"{path.name}:line{line_no}: invalid JSON ({e})"}
                continue
            if rec.get("date") == on_date:
                yield rec


def _to_vision_obs(rec: dict) -> Optional[VisionObservation]:
    try:
        return VisionObservation(
            tick_id=int(rec["tick_id"]),
            date=str(rec["date"]),
            time_et=str(rec["time_et"]),
            price_now=_try_float(rec.get("price_now")),
            direction_call=str(rec.get("q5_direction_call", "unclear")).lower(),
            confidence=int(rec.get("q6_confidence_1_10", 0) or 0),
            in_progress_pattern=str(rec.get("q2_in_progress_pattern", "none")),
            level_interaction=rec.get("q3_level_interaction") or {},
            momentum=str(rec.get("q4_momentum", "")),
            horizon_minutes=int(rec.get("q5_horizon_minutes", 10) or 10),
            grounded_against_ohlcv=bool(rec.get("grounded_against_ohlcv", False)),
            raw=rec,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _to_heartbeat_decision(rec: dict) -> Optional[HeartbeatDecision]:
    try:
        action = str(rec.get("action", ""))
        return HeartbeatDecision(
            tick_id=int(rec["tick_id"]),
            date=str(rec["date"]),
            time_et=str(rec.get("time_et", "")),
            action=action,
            direction_mapped=_map_heartbeat_action(action),
            bull_score=_try_int(rec.get("bull_score")),
            bear_score=_try_int(rec.get("bear_score")),
            spy=_try_float(rec.get("spy")),
            reason=str(rec.get("reason", "")),
            raw=rec,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _try_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _try_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# === SPY 5m CSV lookup (for next-bar close grading) ===

def _find_spy_csv() -> Optional[Path]:
    """Pick the most recent `spy_5m_*.csv` in backtest/data/."""
    if not SPY_CSV_DIR.exists():
        return None
    candidates = sorted(
        SPY_CSV_DIR.glob("spy_5m_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_spy_bars_for_date(date_str: str) -> dict:
    """Return mapping ``"HH:MM" -> close_float`` for RTH 5m bars on the date.

    SPY CSV format: ``timestamp_et,open,high,low,close,volume`` where timestamp_et is
    e.g. ``"2025-01-02 10:30:00-04:00"``. Bar timestamp is the OPENING time of the
    5m bar; close is at +5min from that label.
    """
    csv_path = _find_spy_csv()
    if not csv_path:
        return {}
    bars: dict = {}
    try:
        with csv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = row.get("timestamp_et", "")
                if not ts.startswith(date_str):
                    continue
                # "2025-01-02 10:30:00-04:00" -> "10:30"
                hh_mm = ts[11:16]
                close = _try_float(row.get("close"))
                if close is not None:
                    bars[hh_mm] = close
    except OSError:
        return {}
    return bars


def _next_bar_close_after(time_et: str, bars: dict) -> Optional[float]:
    """Find the close of the bar that opens >= time_et + 5 min.

    `time_et` may be "HH:MM" or "HH:MM:SS". A tick at 09:42:30 wants the 09:45
    bar's close (which represents the 09:45-09:50 interval and closes at 09:50
    by the bar-OPEN-labels convention used in our master CSV).
    """
    try:
        if len(time_et) >= 5:
            hh = int(time_et[0:2])
            mm = int(time_et[3:5])
        else:
            return None
    except ValueError:
        return None
    # Next 5m bar OPEN time = round-up to next multiple of 5, then +5 min step.
    next_open_min = ((mm // 5) + 1) * 5
    if next_open_min >= 60:
        hh += 1
        next_open_min -= 60
    if hh > 15 or (hh == 15 and next_open_min > 55):
        return None
    key = f"{hh:02d}:{next_open_min:02d}"
    return bars.get(key)


def _direction_from_delta(price_now: Optional[float],
                          next_close: Optional[float],
                          threshold_dollars: float = 0.05) -> Optional[str]:
    if price_now is None or next_close is None:
        return None
    delta = next_close - price_now
    if abs(delta) < threshold_dollars:
        return "flat"
    return "bull" if delta > 0 else "bear"


# === Pairing ===

def _pair_observations(visions: list, decisions: list) -> list:
    """Pair vision obs and heartbeat decisions by tick_id within the same date.

    Vision and heartbeat fire on the same 3-min cadence so tick_id should match.
    If a tick has both: pair them. If only one: emit a vision_only / heartbeat_only
    pair so the aggregate counts everything.
    """
    by_v = {v.tick_id: v for v in visions}
    by_h = {h.tick_id: h for h in decisions}
    all_ticks = sorted(set(by_v) | set(by_h))
    pairs = []
    for tid in all_ticks:
        v = by_v.get(tid)
        h = by_h.get(tid)
        if v and h:
            tag = "ALIGNED" if v.direction_call == h.direction_mapped else "DIVERGED"
            time_et = v.time_et
            date = v.date
        elif v and not h:
            tag = "vision_only"
            time_et = v.time_et
            date = v.date
        elif h and not v:
            tag = "heartbeat_only"
            time_et = h.time_et
            date = h.date
        else:
            continue  # not reachable
        pairs.append((tid, date, time_et, v, h, tag))
    return pairs


# === Grading ===

def _grade_pair(pair_tup: tuple, bars: dict) -> PairedTick:
    tid, date, time_et, v, h, tag = pair_tup
    # Use vision's price_now if available, else heartbeat's spy
    price_now = (v.price_now if v else None) or (h.spy if h else None)
    next_close = _next_bar_close_after(time_et, bars)
    truth = _direction_from_delta(price_now, next_close)

    def _grade(dir_call: Optional[str]) -> Optional[bool]:
        if dir_call is None or dir_call in ("unclear", "chop"):
            return None
        if truth in (None, "flat"):
            return None
        return dir_call == truth

    return PairedTick(
        tick_id=tid,
        date=date,
        time_et=time_et,
        vision=v,
        heartbeat=h,
        tag=tag,
        next_bar_close=next_close,
        next_bar_direction=truth,
        vision_correct=_grade(v.direction_call if v else None),
        heartbeat_correct=_grade(h.direction_mapped if h else None),
    )


# === Public entry point ===

def run_grader(date_str: str, write_output: bool = True) -> dict:
    """Run the grader for a single date. Returns the JSON-serializable result dict."""
    visions: list = []
    decisions: list = []
    warnings: list = []

    for rec in _stream_jsonl(VISION_JSONL, date_str):
        if "_warning" in rec:
            warnings.append(rec["_warning"])
            continue
        obs = _to_vision_obs(rec)
        if obs is None:
            warnings.append(f"vision-observations: skipped malformed record tick_id={rec.get('tick_id')}")
            continue
        visions.append(obs)

    for rec in _stream_jsonl(DECISIONS_JSONL, date_str):
        if "_warning" in rec:
            warnings.append(rec["_warning"])
            continue
        dec = _to_heartbeat_decision(rec)
        if dec is None:
            warnings.append(f"decisions: skipped malformed record tick_id={rec.get('tick_id')}")
            continue
        decisions.append(dec)

    bars = _load_spy_bars_for_date(date_str)
    if not bars:
        warnings.append(f"spy 5m bars for {date_str} not found in {SPY_CSV_DIR} — next-bar grading disabled")

    pair_tuples = _pair_observations(visions, decisions)
    pairs = [_grade_pair(pt, bars) for pt in pair_tuples]

    # Aggregate
    agg = Aggregate(date=date_str)
    agg.ingest_warnings = warnings
    for p in pairs:
        agg.total_paired_ticks += 1
        if p.tag == "ALIGNED":
            agg.aligned += 1
        elif p.tag == "DIVERGED":
            agg.diverged += 1
        elif p.tag == "vision_only":
            agg.vision_only += 1
        elif p.tag == "heartbeat_only":
            agg.heartbeat_only += 1
        if p.vision_correct is not None:
            agg.vision_graded_n += 1
            if p.vision_correct:
                agg.vision_correct_n += 1
        if p.heartbeat_correct is not None:
            agg.heartbeat_graded_n += 1
            if p.heartbeat_correct:
                agg.heartbeat_correct_n += 1
        if p.tag == "DIVERGED":
            if p.vision_correct is not None or p.heartbeat_correct is not None:
                agg.diverged_graded += 1
            if p.vision_correct:
                agg.diverged_vision_correct += 1
            if p.heartbeat_correct:
                agg.diverged_heartbeat_correct += 1

    vision_acc = _pct(agg.vision_correct_n, agg.vision_graded_n)
    heartbeat_acc = _pct(agg.heartbeat_correct_n, agg.heartbeat_graded_n)
    diverged_vision_acc = _pct(agg.diverged_vision_correct, agg.diverged_graded)
    diverged_heartbeat_acc = _pct(agg.diverged_heartbeat_correct, agg.diverged_graded)

    out = {
        "schema_version": "1.0.0",
        "date": date_str,
        "generated_at_et": dt.datetime.now().isoformat(timespec="seconds"),
        "aggregate": {
            "total_paired_ticks": agg.total_paired_ticks,
            "aligned": agg.aligned,
            "diverged": agg.diverged,
            "vision_only": agg.vision_only,
            "heartbeat_only": agg.heartbeat_only,
            "vision_accuracy_pct": vision_acc,
            "vision_graded_n": agg.vision_graded_n,
            "heartbeat_accuracy_pct": heartbeat_acc,
            "heartbeat_graded_n": agg.heartbeat_graded_n,
            "diverged_vision_accuracy_pct": diverged_vision_acc,
            "diverged_heartbeat_accuracy_pct": diverged_heartbeat_acc,
            "diverged_graded_n": agg.diverged_graded,
            "vision_minus_heartbeat_diverged_pp": _round_or_none(diverged_vision_acc, diverged_heartbeat_acc),
        },
        "per_tick": [_pair_to_dict(p) for p in pairs],
        "ingest_warnings": warnings,
        "verdict": _compute_verdict(agg, vision_acc, heartbeat_acc, diverged_vision_acc, diverged_heartbeat_acc),
    }

    if write_output:
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ANALYSIS_DIR / f"vision-vs-heartbeat-{date_str}.json"
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    return out


def _pair_to_dict(p: PairedTick) -> dict:
    return {
        "tick_id": p.tick_id,
        "date": p.date,
        "time_et": p.time_et,
        "tag": p.tag,
        "vision_direction": p.vision.direction_call if p.vision else None,
        "vision_confidence": p.vision.confidence if p.vision else None,
        "vision_pattern": p.vision.in_progress_pattern if p.vision else None,
        "vision_momentum": p.vision.momentum if p.vision else None,
        "vision_grounded": p.vision.grounded_against_ohlcv if p.vision else None,
        "heartbeat_action": p.heartbeat.action if p.heartbeat else None,
        "heartbeat_direction": p.heartbeat.direction_mapped if p.heartbeat else None,
        "heartbeat_bull_score": p.heartbeat.bull_score if p.heartbeat else None,
        "heartbeat_bear_score": p.heartbeat.bear_score if p.heartbeat else None,
        "heartbeat_reason": p.heartbeat.reason[:140] if p.heartbeat else None,
        "next_bar_close": p.next_bar_close,
        "next_bar_direction": p.next_bar_direction,
        "vision_correct": p.vision_correct,
        "heartbeat_correct": p.heartbeat_correct,
    }


def _pct(n: int, d: int) -> Optional[float]:
    if d == 0:
        return None
    return round(100 * n / d, 2)


def _round_or_none(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _compute_verdict(agg: Aggregate,
                     vision_acc: Optional[float],
                     heartbeat_acc: Optional[float],
                     diverged_vision_acc: Optional[float],
                     diverged_heartbeat_acc: Optional[float]) -> dict:
    """One-day verdict — N=1 day is never sufficient for promotion, just signal."""
    notes = []
    if agg.total_paired_ticks == 0:
        return {"verdict": "NO_DATA", "narrative": "no vision observations or heartbeat decisions for this date"}
    if vision_acc is None or heartbeat_acc is None:
        notes.append("insufficient_graded_ticks_for_one_or_both_layers")
    if agg.diverged_graded < 3:
        notes.append("too_few_diverged_ticks_for_signal")
    note_text = "; ".join(notes) if notes else "single-day sample (N=1); 20+ days required for promotion-path decision per OP-21"
    return {
        "verdict": "INFORMATIONAL",
        "vision_outperforms_heartbeat_today": (
            vision_acc is not None and heartbeat_acc is not None and vision_acc > heartbeat_acc
        ),
        "diverged_vision_outperforms": (
            diverged_vision_acc is not None and diverged_heartbeat_acc is not None
            and diverged_vision_acc > diverged_heartbeat_acc
        ),
        "narrative": note_text,
    }


def main_cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    out = run_grader(args.date)
    if not args.quiet:
        print(f"=== VISION vs HEARTBEAT for {args.date} ===")
        agg = out["aggregate"]
        print(f"  paired ticks: {agg['total_paired_ticks']} "
              f"(aligned={agg['aligned']} diverged={agg['diverged']} "
              f"vision_only={agg['vision_only']} heartbeat_only={agg['heartbeat_only']})")
        print(f"  vision acc:    {agg['vision_accuracy_pct']}% (n={agg['vision_graded_n']})")
        print(f"  heartbeat acc: {agg['heartbeat_accuracy_pct']}% (n={agg['heartbeat_graded_n']})")
        if agg.get('diverged_graded_n', 0) > 0:
            print(f"  DIVERGED-only: vision={agg['diverged_vision_accuracy_pct']}% vs "
                  f"heartbeat={agg['diverged_heartbeat_accuracy_pct']}% "
                  f"(margin={agg['vision_minus_heartbeat_diverged_pp']}pp, n={agg['diverged_graded_n']})")
        print(f"  verdict: {out['verdict']['verdict']}")
        print(f"  output:  {ANALYSIS_DIR / f'vision-vs-heartbeat-{args.date}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
