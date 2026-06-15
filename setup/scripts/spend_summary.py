"""Daily spend summary -- aggregates Claude Code + MiniMax token costs per day.

Closes the OP-3 cost-effectiveness loop: see actual burn velocity instead of
inferring spend only when rate-limits fire.

Reads:
  * ~/.claude/projects/C--Users-jackw-Desktop-42/*.jsonl (Claude Code session logs)
      - Each `message.usage` block is summed by model.
  * automation/state/minimax-calls.jsonl (MiniMax-via-OpenRouter telemetry)
      - Each call's cost_usd is summed by task_id.

Writes:
  * automation/state/spend-{YYYY-MM-DD}.json  -- snapshot for today
  * automation/state/spend-daily.jsonl         -- one row per day (history)
  * STATUS.md WARN if today's total > --warn-threshold (default $50)

CLI:
  python spend_summary.py                    -- today's summary, write files
  python spend_summary.py --days 7           -- last 7 days
  python spend_summary.py --check-only       -- print to stdout, no writes
  python spend_summary.py --date 2026-05-19  -- a specific date

Cost model (Anthropic public rates -- update when tiers change):
  Sonnet 4.6:  $3/M input,  $15/M output,  $3.75/M cache_5m write, $0.30/M cache_read
  Opus 4.7:    $15/M input, $75/M output,  $18.75/M cache_5m write, $1.50/M cache_read
  Haiku 4.5:   $1/M input,  $5/M output,   $1.25/M cache_5m write, $0.10/M cache_read

The Max plan covers spend up to the rate-limit budget; this report is the
METER that tells us how close we are. A high $-day doesn't cost J extra
(Max is flat $100/mo), but it predicts the next rate-limit hit.

Per OP-25 engine-benefit autonomy + OP-3 cost discipline + OP-27 L41 spawn rules.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"
CC_PROJECT_DIR = Path.home() / ".claude" / "projects" / "C--Users-jackw-Desktop-42"
MINIMAX_TELEMETRY = STATE_DIR / "minimax-calls.jsonl"
SPEND_DAILY_HISTORY = STATE_DIR / "spend-daily.jsonl"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# DST-aware ET (no tzdata dependency) -- shared pattern with session_guard.py.
def _et_offset_hours(dt_utc: datetime) -> int:
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start_utc = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end_utc = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start_utc <= dt_utc < dst_end_utc) else -5


def _et_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)


def _et_date(s: str) -> str:
    """Convert a UTC ISO string to ET date (YYYY-MM-DD)."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        dt_et = dt_utc + timedelta(hours=_et_offset_hours(dt_utc))
        return dt_et.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return "unknown"


# Pricing: $ per token (rates in $/M divided by 1M). Update when Anthropic publishes new tiers.
# Key matching is case-insensitive substring match on the model field from session logs.
PRICING: dict[str, dict[str, float]] = {
    "opus": {
        "input": 15.0 / 1_000_000,
        "output": 75.0 / 1_000_000,
        "cache_creation": 18.75 / 1_000_000,
        "cache_read": 1.50 / 1_000_000,
    },
    "sonnet": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_creation": 3.75 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    },
    "haiku": {
        "input": 1.0 / 1_000_000,
        "output": 5.0 / 1_000_000,
        "cache_creation": 1.25 / 1_000_000,
        "cache_read": 0.10 / 1_000_000,
    },
}


def _model_tier(model: str) -> str:
    """Map a model string to its pricing tier. Defaults to sonnet (conservative)."""
    m = (model or "").lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"


@dataclass
class TokenAgg:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    message_count: int = 0

    def add(self, usage: dict) -> None:
        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage.get("output_tokens", 0) or 0)
        self.cache_creation_input_tokens += int(usage.get("cache_creation_input_tokens", 0) or 0)
        self.cache_read_input_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
        self.message_count += 1

    def cost_usd(self, tier: str) -> float:
        p = PRICING[tier]
        return round(
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_creation_input_tokens * p["cache_creation"]
            + self.cache_read_input_tokens * p["cache_read"],
            4,
        )

    def to_dict(self, tier: str) -> dict:
        return {
            "tier": tier,
            "messages": self.message_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "estimated_cost_usd": self.cost_usd(tier),
        }


@dataclass
class DayReport:
    date_et: str
    claude_by_tier: dict[str, TokenAgg] = field(default_factory=lambda: defaultdict(TokenAgg))
    claude_sessions: int = 0
    minimax_cost: float = 0.0
    minimax_calls: int = 0
    minimax_by_task: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def claude_total_cost(self) -> float:
        return round(sum(agg.cost_usd(tier) for tier, agg in self.claude_by_tier.items()), 4)

    @property
    def total_cost(self) -> float:
        return round(self.claude_total_cost + self.minimax_cost, 4)

    def to_dict(self) -> dict:
        return {
            "date_et": self.date_et,
            "total_cost_usd": self.total_cost,
            "claude_cost_usd": self.claude_total_cost,
            "minimax_cost_usd": round(self.minimax_cost, 4),
            "claude_sessions": self.claude_sessions,
            "claude_by_tier": {tier: agg.to_dict(tier) for tier, agg in self.claude_by_tier.items()},
            "minimax_calls": self.minimax_calls,
            "minimax_by_task": dict(sorted(self.minimax_by_task.items(), key=lambda kv: -kv[1])),
        }


def _scan_claude_sessions(target_dates: set[str]) -> dict[str, DayReport]:
    """Walk Claude Code session JSONL files, aggregate usage by ET date.
    Returns a dict keyed by ET date string."""
    reports: dict[str, DayReport] = {d: DayReport(date_et=d) for d in target_dates}
    if not CC_PROJECT_DIR.exists():
        return reports

    # Count sessions touched today (by file mtime in ET)
    seen_sessions: dict[str, set[str]] = {d: set() for d in target_dates}

    for jsonl in CC_PROJECT_DIR.glob("*.jsonl"):
        # Quick skip: if file's mtime is before earliest target date, skip
        mtime_dt = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
        mtime_date = _et_date(mtime_dt.isoformat())
        # Always scan all files for the target window -- some files span multiple days
        try:
            with open(jsonl, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    msg = obj.get("message") or {}
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    ts = obj.get("timestamp") or ""
                    et_date = _et_date(ts) if ts else mtime_date
                    if et_date not in target_dates:
                        continue
                    model = msg.get("model") or ""
                    tier = _model_tier(model)
                    reports[et_date].claude_by_tier[tier].add(usage)
                    sid = obj.get("sessionId") or jsonl.stem
                    seen_sessions[et_date].add(sid)
        except OSError:
            continue

    for d in target_dates:
        reports[d].claude_sessions = len(seen_sessions[d])
    return reports


def _scan_minimax(reports: dict[str, DayReport]) -> None:
    """Walk minimax-calls.jsonl, add cost_usd to the matching ET-date report."""
    if not MINIMAX_TELEMETRY.exists():
        return
    target = set(reports.keys())
    try:
        with open(MINIMAX_TELEMETRY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("ts") or ""
                et_date = _et_date(ts) if ts else ""
                if et_date not in target:
                    continue
                cost = float(entry.get("cost_usd", 0.0) or 0.0)
                if cost <= 0:
                    continue
                reports[et_date].minimax_cost += cost
                reports[et_date].minimax_calls += 1
                task = entry.get("task_id", "ad_hoc")
                reports[et_date].minimax_by_task[task] += cost
    except OSError:
        return


def _format_summary(report: DayReport) -> str:
    """Human-readable one-screen summary."""
    lines = [
        f"==== SPEND SUMMARY  date={report.date_et}  total=${report.total_cost:.2f} ====",
        f"  Claude Code:  ${report.claude_total_cost:>8.2f}  (sessions={report.claude_sessions})",
    ]
    for tier in ("opus", "sonnet", "haiku"):
        if tier in report.claude_by_tier:
            agg = report.claude_by_tier[tier]
            lines.append(
                f"    {tier:7s}  ${agg.cost_usd(tier):>7.2f}  msgs={agg.message_count}  "
                f"in={agg.input_tokens:>8,}  out={agg.output_tokens:>8,}  "
                f"cw={agg.cache_creation_input_tokens:>8,}  cr={agg.cache_read_input_tokens:>10,}"
            )
    lines.append(f"  MiniMax:      ${report.minimax_cost:>8.2f}  (calls={report.minimax_calls})")
    if report.minimax_by_task:
        top5 = list(report.minimax_by_task.items())[:5]
        for task, cost in top5:
            lines.append(f"    {task:30s}  ${cost:>7.4f}")
    return "\n".join(lines)


def _append_jsonl_history(report: DayReport) -> None:
    """Append a one-line daily history row to spend-daily.jsonl. Idempotent --
    if today's row already exists, replace it; otherwise append."""
    target_date = report.date_et
    existing = []
    if SPEND_DAILY_HISTORY.exists():
        try:
            with open(SPEND_DAILY_HISTORY, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if row.get("date_et") != target_date:
                            existing.append(row)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
    existing.append({
        "date_et": target_date,
        "total_cost_usd": report.total_cost,
        "claude_cost_usd": report.claude_total_cost,
        "minimax_cost_usd": round(report.minimax_cost, 4),
        "claude_sessions": report.claude_sessions,
        "minimax_calls": report.minimax_calls,
    })
    existing.sort(key=lambda r: r.get("date_et", ""))
    try:
        with open(SPEND_DAILY_HISTORY, "w", encoding="utf-8") as f:
            for row in existing:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[spend-summary] WARN history write failed: {exc}", file=sys.stderr)


def _append_status_warn(report: DayReport, threshold: float) -> None:
    if report.total_cost < threshold:
        return
    if not STATUS_FILE.parent.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [
            "",
            "### WARN: spend-summary threshold breach",
            f"- ts: {ts}",
            f"- date_et: {report.date_et}",
            f"- total: ${report.total_cost:.2f} (threshold ${threshold:.2f})",
            f"- claude: ${report.claude_total_cost:.2f}  minimax: ${report.minimax_cost:.2f}",
            f"- claude_sessions: {report.claude_sessions}",
        ]
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"[spend-summary] WARN status_md write failed: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="Specific ET date YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of trailing days to report (default 1 = today only)")
    parser.add_argument("--check-only", action="store_true",
                        help="Print summary to stdout; don't write files or STATUS.md")
    parser.add_argument("--warn-threshold", type=float, default=50.0,
                        help="Total $/day above which a STATUS.md WARN is appended (default $50)")
    args = parser.parse_args()

    # Build target date set
    if args.date:
        try:
            anchor = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"[spend-summary] ERROR invalid --date {args.date}; expect YYYY-MM-DD", file=sys.stderr)
            return 2
    else:
        anchor = _et_now()
    target_dates: set[str] = set()
    for delta in range(args.days):
        d = (anchor - timedelta(days=delta)).strftime("%Y-%m-%d")
        target_dates.add(d)

    # Scan
    reports = _scan_claude_sessions(target_dates)
    _scan_minimax(reports)

    # Print each day
    for d in sorted(target_dates):
        print(_format_summary(reports[d]))
        print()

    # Persist if not check-only
    if not args.check_only:
        for d in sorted(target_dates):
            report = reports[d]
            snapshot_path = STATE_DIR / f"spend-{d}.json"
            try:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                snapshot_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
            except OSError as exc:
                print(f"[spend-summary] WARN snapshot write failed for {d}: {exc}", file=sys.stderr)
                continue
            _append_jsonl_history(report)
            # Only WARN on TODAY's breach (not retrospective backfills)
            today_et = _et_now().strftime("%Y-%m-%d")
            if d == today_et:
                _append_status_warn(report, args.warn_threshold)

    return 0


if __name__ == "__main__":
    sys.exit(main())
