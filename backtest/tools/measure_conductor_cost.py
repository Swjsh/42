"""measure_conductor_cost.py -- independent re-derivation of the conductor
SELF_REPORT_CORRECTION factor (CONDUCTOR-BUDGET-ARITHMETIC, queue item, 2026-08-08).

WHY THIS EXISTS:
conductor_budget.py multiplies every conductor fire's SELF-reported `cost_usd`
(a number the LLM itself types into `conductor_outcome.py record --cost X` --
NOT parsed from any CLI/billing telemetry) by a constant SELF_REPORT_CORRECTION
= 2.2 before comparing to the $30/day cap. That constant traces to a single
2026-07-25 census (automation/state/spend-2026-07-25.json, $423.39/day across
ALL Claude sessions that day -- opus/sonnet/haiku, not conductor-specific) and
has never been re-derived since. This script re-derives it PER FIRE by matching
each conductor-family outcome row to its own Claude Code session transcript
(~/.claude/projects/C--Users-jackw-Desktop-42/*.jsonl) and computing a real
token-based cost from that transcript using Anthropic's published per-token
pricing -- the same methodology already used by setup/scripts/spend_summary.py
and setup/scripts/token_forensics.py, just applied per-fire instead of per-day.

MATCHING METHODOLOGY:
  1. A session file is "conductor family" iff it contains the literal string
     "rail-0 budget gate" -- this text is part of automation/prompts/conductor.md
     STAGE 0 (present in every AFTERHOURS/WEEKEND fire's injected prompt; NOT
     present in the disabled conductor-rth STAGE 0-RTH branch, so this also
     naturally excludes the (already-disabled-since-07-25) RTH_LIGHT fires).
  2. For each automation/state/conductor-outcomes.jsonl row (fired_at, cost_usd),
     find the conductor-family session whose transcript activity window
     [first_ts, last_ts] best explains that fired_at: last_ts <= fired_at +
     MATCH_TOLERANCE_SEC and (fired_at - last_ts) minimized. One session matches
     at most one outcome row (greedy nearest-first assignment) -- a session
     re-used across multiple rows would double count real spend.
  3. real_cost_usd for the matched session = sum over every assistant-role
     message in that transcript of tokens x published per-tier price (same
     PRICING_PER_M table as token_forensics.py). This is a lower bound if the
     conductor's Agent()-tool fan-out ever spawns subagent turns that are NOT
     recorded inside the parent transcript (isSidechain flag was checked: 0
     occurrences found anywhere in the 605-file corpus scanned 2026-08-08, i.e.
     no evidence one way or the other from that flag -- flagged as a caveat,
     not resolved).
  4. ratio = self_reported_cost_usd / real_cost_usd for each matched pair with
     self_reported_cost_usd >= MIN_SELF_REPORT (near-zero self-reports make the
     ratio numerically unstable/meaningless -- a $0.01 self-report against a
     $0.15 real cost is a 15x ratio driven by rounding, not a signal).
     NOTE the constant's own definition: SELF_REPORT_CORRECTION is meant to be
     multiplied INTO the self-report to approximate the real cost, i.e.
     corrected = self_report * FACTOR ~= real, so FACTOR ~= real / self_report
     = 1 / ratio_as_defined_above. This script reports BOTH directions
     explicitly to avoid an inversion bug -- see `real_over_self` (this is the
     one that should be compared to 2.2) vs `self_over_real`.

OUTPUT: prints a JSON summary to stdout; --write also saves it to the given path.
Pure stdlib. Never raises past main() -- a match failure just yields n=0, which
the caller (or a human) must then treat as UNDERPOWERED, never silently as 0
evidence of no drift.

CLI:
  python backtest/tools/measure_conductor_cost.py
  python backtest/tools/measure_conductor_cost.py --write analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.json
  python backtest/tools/measure_conductor_cost.py --min-self-report 0.25 --tolerance-sec 900
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
OUTCOMES_PATH = REPO / "automation" / "state" / "conductor-outcomes.jsonl"
SESSIONS_DIR = Path.home() / ".claude" / "projects" / "C--Users-jackw-Desktop-42"

CONDUCTOR_MARKER = "rail-0 budget gate"

# Same table as token_forensics.py / spend_summary.py (Anthropic public rates,
# USD per 1M tokens). Kept duplicated rather than imported: this tool must stay
# runnable standalone (no repo-internal import chain that could break it).
PRICING_PER_M = {
    "haiku": {"input": 1.00, "output": 5.00, "cache_creation": 1.25, "cache_read": 0.10},
    "sonnet": {"input": 3.00, "output": 15.00, "cache_creation": 3.75, "cache_read": 0.30},
    "opus": {"input": 15.00, "output": 75.00, "cache_creation": 18.75, "cache_read": 1.50},
}

DEFAULT_MATCH_TOLERANCE_SEC = 900  # 15 min: session must END within this of fired_at
DEFAULT_MIN_SELF_REPORT = 0.25     # ignore near-zero self-reports (ratio noise)


def _price_for_model(model: str) -> dict:
    m = (model or "").lower()
    if "opus" in m:
        return PRICING_PER_M["opus"]
    if "haiku" in m:
        return PRICING_PER_M["haiku"]
    return PRICING_PER_M["sonnet"]  # sonnet default (also covers unknown -- conservative-ish)


def _compute_msg_cost(model: str, usage: dict) -> float:
    if not usage:
        return 0.0
    p = _price_for_model(model)
    inp = float(usage.get("input_tokens", 0) or 0)
    out = float(usage.get("output_tokens", 0) or 0)
    cwrite = float(usage.get("cache_creation_input_tokens", 0) or 0)
    cread = float(usage.get("cache_read_input_tokens", 0) or 0)
    return (inp * p["input"] + out * p["output"] + cwrite * p["cache_creation"]
            + cread * p["cache_read"]) / 1_000_000.0


@dataclass
class SessionInfo:
    session_id: str
    path: Path
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    real_cost_usd: float = 0.0
    is_conductor: bool = False
    n_assistant_msgs: int = 0
    models_seen: set = field(default_factory=set)


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def scan_sessions(sessions_dir: Path = SESSIONS_DIR) -> list[SessionInfo]:
    """Parse every session transcript once: real cost, activity window, and
    whether it's a conductor-family fire (marker string present anywhere)."""
    out: list[SessionInfo] = []
    if not sessions_dir.exists():
        return out
    for jsonl in sessions_dir.glob("*.jsonl"):
        info = SessionInfo(session_id=jsonl.stem, path=jsonl)
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if CONDUCTOR_MARKER in text:
            info.is_conductor = True
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(d.get("timestamp", ""))
            if ts is not None:
                if info.first_ts is None or ts < info.first_ts:
                    info.first_ts = ts
                if info.last_ts is None or ts > info.last_ts:
                    info.last_ts = ts
            if d.get("type") == "assistant":
                msg = d.get("message") or {}
                model = msg.get("model") or ""
                usage = msg.get("usage") or {}
                if usage:
                    info.real_cost_usd += _compute_msg_cost(model, usage)
                    info.n_assistant_msgs += 1
                    if model:
                        info.models_seen.add(model)
        out.append(info)
    return out


def load_outcomes(path: Path = OUTCOMES_PATH) -> list[dict]:
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def match_fires(
    outcomes: list[dict],
    sessions: list[SessionInfo],
    tolerance_sec: int = DEFAULT_MATCH_TOLERANCE_SEC,
) -> list[dict]:
    """Greedy nearest-match: each outcome row claims at most one session, each
    session claims at most one row. Sessions must be conductor-family (marker
    present) and end at-or-before fired_at (+ small forward slack for clock
    skew between the record() call and the transcript's last event) within
    `tolerance_sec`.

    FORWARD_SLACK_SEC allows the session's last_ts to be a little AFTER
    fired_at too (record() timestamps itself independently of the transcript
    writer; the two can interleave by a few seconds), but candidates where
    last_ts is far after fired_at are rejected -- that would mean the outcome
    row was written mid-session, which should not happen for a well-formed
    fire.
    """
    FORWARD_SLACK_SEC = 30
    candidates = [s for s in sessions if s.is_conductor and s.last_ts is not None]
    used: set[str] = set()
    matches: list[dict] = []
    # Process rows in chronological order so earlier fires claim their nearest
    # session before a later fire's window can steal it.
    ordered = sorted(
        enumerate(outcomes),
        key=lambda kv: str(kv[1].get("fired_at") or ""),
    )
    for idx, row in ordered:
        fired_at = _parse_ts(str(row.get("fired_at") or ""))
        if fired_at is None:
            continue
        best = None
        best_delta = None
        for s in candidates:
            if s.session_id in used:
                continue
            delta = (fired_at - s.last_ts).total_seconds()
            if delta < -FORWARD_SLACK_SEC or delta > tolerance_sec:
                continue
            adelta = abs(delta)
            if best is None or adelta < best_delta:
                best = s
                best_delta = adelta
        if best is not None:
            used.add(best.session_id)
            matches.append({
                "row_index": idx,
                "task_id": row.get("task_id"),
                "fired_at": row.get("fired_at"),
                "self_reported_cost_usd": float(row.get("cost_usd") or 0.0),
                "session_id": best.session_id,
                "session_last_ts": best.last_ts.isoformat(),
                "delta_sec": round((fired_at - best.last_ts).total_seconds(), 1),
                "real_cost_usd": round(best.real_cost_usd, 4),
                "n_assistant_msgs": best.n_assistant_msgs,
                "models_seen": sorted(best.models_seen),
            })
    return matches


def summarize(matches: list[dict], min_self_report: float = DEFAULT_MIN_SELF_REPORT) -> dict:
    usable = [m for m in matches
              if m["self_reported_cost_usd"] >= min_self_report and m["real_cost_usd"] > 0]
    real_over_self = [m["real_cost_usd"] / m["self_reported_cost_usd"] for m in usable]
    self_over_real = [m["self_reported_cost_usd"] / m["real_cost_usd"] for m in usable]
    n = len(usable)
    summary = {
        "n_total_matched": len(matches),
        "n_usable_for_ratio": n,
        "min_self_report_filter_usd": min_self_report,
    }
    if n > 0:
        summary["real_over_self"] = {
            "note": "real_cost / self_reported_cost -- THIS is the number comparable to SELF_REPORT_CORRECTION=2.2",
            "n": n,
            "median": round(median(real_over_self), 3),
            "mean": round(mean(real_over_self), 3),
            "min": round(min(real_over_self), 3),
            "max": round(max(real_over_self), 3),
        }
        summary["self_over_real"] = {
            "note": "self_reported_cost / real_cost (inverse direction, sanity cross-check)",
            "n": n,
            "median": round(median(self_over_real), 3),
            "mean": round(mean(self_over_real), 3),
            "min": round(min(self_over_real), 3),
            "max": round(max(self_over_real), 3),
        }
        summary["self_reported_total_usd"] = round(sum(m["self_reported_cost_usd"] for m in usable), 2)
        summary["real_total_usd"] = round(sum(m["real_cost_usd"] for m in usable), 2)
        summary["aggregate_ratio_real_over_self"] = (
            round(summary["real_total_usd"] / summary["self_reported_total_usd"], 3)
            if summary["self_reported_total_usd"] > 0 else None
        )
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tolerance-sec", type=int, default=DEFAULT_MATCH_TOLERANCE_SEC)
    ap.add_argument("--min-self-report", type=float, default=DEFAULT_MIN_SELF_REPORT)
    ap.add_argument("--write", default=None, help="Path to also write the JSON output to")
    ap.add_argument("--show-matches", action="store_true", help="Include the per-fire match list in output")
    args = ap.parse_args(argv)

    outcomes = load_outcomes()
    sessions = scan_sessions()
    n_conductor_sessions = sum(1 for s in sessions if s.is_conductor)
    matches = match_fires(outcomes, sessions, tolerance_sec=args.tolerance_sec)
    summary = summarize(matches, min_self_report=args.min_self_report)

    payload = {
        "computed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcomes_rows_total": len(outcomes),
        "conductor_family_sessions_found": n_conductor_sessions,
        "sessions_scanned_total": len(sessions),
        **summary,
    }
    if args.show_matches:
        payload["matches"] = matches

    print(json.dumps(payload, indent=2))
    if args.write:
        out_path = Path(args.write)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full_payload = dict(payload)
        full_payload["matches"] = matches  # always persist full match list to the file
        out_path.write_text(json.dumps(full_payload, indent=2), encoding="utf-8")
        print(f"\n[measure-conductor-cost] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
