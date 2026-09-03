"""Daily spend summary -- aggregates Claude Code + MiniMax + Groq token costs per day.

Closes the OP-3 cost-effectiveness loop: see actual burn velocity instead of
inferring spend only when rate-limits fire.

Reads:
  * ~/.claude/projects/C--Users-jackw-Desktop-42/*.jsonl (Claude Code session logs)
      - Each `message.usage` block is summed by model.
  * automation/state/minimax-calls.jsonl (MiniMax-via-OpenRouter telemetry)
      - Each call's cost_usd is summed by task_id.
  * automation/state/swarm-calls.jsonl (swarm_client.py lane telemetry)
      - Groq lanes priced from raw input_tokens/output_tokens (2026-07-06 Groq-bill
        audit: swarm_client.py logs tokens but NEVER computed cost -- the roster
        treated Groq as a $0 free-tier lane while the account was actually on
        Groq's paid on-demand tier, so ~$9.50 of real usage went unmetered for
        12 days until an external invoice surfaced it. Priced here instead of at
        the source so this stays a zero-risk, offline-only reporting change).
        Cerebras/OpenRouter lanes in this file are left at $0 (Cerebras's free
        tier is unverified-paid; OpenRouter lanes are tracked via minimax-calls
        already) -- only re-price a provider here once there's the same kind of
        hard evidence (sustained volume with zero rate-limit errors) as Groq had.

Writes:
  * automation/state/spend-{YYYY-MM-DD}.json      -- snapshot for today
  * automation/state/spend-daily.jsonl             -- one row per day (history)
  * automation/state/spend-summary-alert-state.json -- last known breach state (for
    transition-only alerting, see ALERTING below)
  * STATUS.md '## Known broken' SPEND_ marker (de-duplicating upsert via
    status_known_broken.py) -- written only on a WARN transition, cleared only on
    a CLEAR transition. Never a blind per-fire append (see ALERTING).
  * automation/state/discord-outbox.jsonl      -- one terse ping ONLY on a breach
    transition (WARN going in, CLEAR coming out) -- see ALERTING.

ALERTING (recalibrated 2026-09-03, SPEND-SUMMARY-CHRONIC-RED-ALERT-FATIGUE):
  The threshold used to be a hardcoded --warn-threshold 30 (set by
  run-spend-summary.ps1) against a script default of $50 -- both frozen numbers,
  never revisited after the Max plan moved from $100/mo flat to $200/mo 20x
  (2026-06-24). Against REAL history (automation/state/spend-daily.jsonl,
  20 real-session days 2026-08-10..2026-09-02) the $30 number was breached on
  100% of sampled days (low $43.15, high $2,697.10) -- an alarm that has never
  once gone green is not discriminating signal from noise (same "alarm that
  cannot clear" class as the 2026-08-17 check_llm_auth_outage fix). Two
  independent changes fix this:
    1. THRESHOLD is now auto-derived every run (see _derive_warn_threshold):
       the 75th percentile of the trailing WARN_WINDOW_DAYS days' totals
       STRICTLY BEFORE today (today can never raise its own bar), floored at
       WARN_FLOOR so a quiet historical stretch can't collapse the bar to
       near-zero. Falls back to the floor when fewer than WARN_MIN_HISTORY_DAYS
       prior days exist. This self-corrects as usage shifts (recency > a frozen
       number, per J 2026-07-31) instead of needing manual recalibration again.
       Pass --warn-threshold explicitly to force a fixed value instead (kept for
       back-compat / ad-hoc checks).
    2. ALERTS ARE TRANSITION-ONLY: a WARN Discord ping + STATUS.md marker fire
       only when today's breach state DIFFERS from the last recorded state
       (loaded from spend-summary-alert-state.json) -- not-breached -> breached
       sends ONE WARN, breached -> not-breached sends ONE CLEAR, and a day that
       stays on the same side of the line as the day before is SILENT. This is
       the same convention self_check.py's _problem_set_signature / gate_expiry_check
       / guard_runner_slow._flag_status_md already use for "don't re-ping an
       unchanged condition every fire."
  conductor_budget.py ALSO has a $30/day cap, but it scopes only to the
  conductor-family fires' self-reported (2.16x-corrected) cost -- a materially
  smaller population than this script's whole-day ALL-Claude-Code-session scan.
  Reusing that number here would silently change what's being measured, so a
  fresh threshold is derived for this script's own (much larger) population
  instead of importing conductor_budget's.

CLI:
  python spend_summary.py                    -- today's summary, write files
  python spend_summary.py --days 7           -- last 7 days
  python spend_summary.py --check-only       -- print to stdout, no writes
  python spend_summary.py --date 2026-05-19  -- a specific date
  python spend_summary.py --warn-threshold 100  -- force a fixed threshold (skips auto-derive)

Cost model (Anthropic public rates -- update when tiers change):
  Sonnet 4.6:  $3/M input,  $15/M output,  $3.75/M cache_5m write, $0.30/M cache_read
  Opus 4.7:    $15/M input, $75/M output,  $18.75/M cache_5m write, $1.50/M cache_read
  Haiku 4.5:   $1/M input,  $5/M output,   $1.25/M cache_5m write, $0.10/M cache_read

The Max plan covers spend up to the rate-limit budget; this report is the
METER that tells us how close we are. A high $-day doesn't bill J extra dollars
directly (the plan is a flat $200/mo 20x subscription, corrected 2026-09-03 --
was stale here since the 2026-06-24 upgrade from $100/mo), but every dollar
here is a client-side Anthropic-list-price ESTIMATE of token burn, not a real
invoice line -- it predicts rate-limit pressure, it is not a bill.

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
SWARM_CALLS_TELEMETRY = STATE_DIR / "swarm-calls.jsonl"
SPEND_DAILY_HISTORY = STATE_DIR / "spend-daily.jsonl"
DISCORD_OUTBOX = STATE_DIR / "discord-outbox.jsonl"
ALERT_STATE_FILE = STATE_DIR / "spend-summary-alert-state.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_known_broken as skb  # noqa: E402  -- de-duplicating STATUS.md '## Known broken' writer

STATUS_MARKER = "SPEND_"

# Threshold auto-derivation (SPEND-SUMMARY-CHRONIC-RED-ALERT-FATIGUE, 2026-09-03) -- see
# module docstring ALERTING section for the full rationale.
WARN_FLOOR = 50.0
WARN_PERCENTILE = 75.0
WARN_MIN_HISTORY_DAYS = 5
WARN_WINDOW_DAYS = 30

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


# Groq on-demand per-token rates ($/M from groq.com/pricing, confirmed 2026-07-06).
# Only priced for models actually seen in the roster -- an unrecognized Groq model
# returns None (see _groq_cost) rather than silently reporting $0, so a NEW model
# showing up here can't repeat the "assumed free" mistake unnoticed.
GROQ_PRICING: dict[str, dict[str, float]] = {
    "llama-3.1-8b-instant": {"input": 0.05 / 1_000_000, "output": 0.08 / 1_000_000},
    "llama-3.3-70b-versatile": {"input": 0.59 / 1_000_000, "output": 0.79 / 1_000_000},
    "openai/gpt-oss-120b": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


def _groq_cost(model: str, in_tok: int, out_tok: int) -> Optional[float]:
    """Real on-demand cost for a Groq call, or None if the model has no known rate."""
    rates = GROQ_PRICING.get(model)
    if not rates:
        return None
    return in_tok * rates["input"] + out_tok * rates["output"]


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
    groq_cost: float = 0.0
    groq_calls: int = 0
    groq_by_model: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    groq_unpriced_models: set = field(default_factory=set)

    @property
    def claude_total_cost(self) -> float:
        return round(sum(agg.cost_usd(tier) for tier, agg in self.claude_by_tier.items()), 4)

    @property
    def total_cost(self) -> float:
        return round(self.claude_total_cost + self.minimax_cost + self.groq_cost, 4)

    def to_dict(self) -> dict:
        return {
            "date_et": self.date_et,
            "total_cost_usd": self.total_cost,
            "claude_cost_usd": self.claude_total_cost,
            "minimax_cost_usd": round(self.minimax_cost, 4),
            "groq_cost_usd": round(self.groq_cost, 4),
            "claude_sessions": self.claude_sessions,
            "claude_by_tier": {tier: agg.to_dict(tier) for tier, agg in self.claude_by_tier.items()},
            "minimax_calls": self.minimax_calls,
            "minimax_by_task": dict(sorted(self.minimax_by_task.items(), key=lambda kv: -kv[1])),
            "groq_calls": self.groq_calls,
            "groq_by_model": dict(sorted(self.groq_by_model.items(), key=lambda kv: -kv[1])),
            "groq_unpriced_models": sorted(self.groq_unpriced_models),
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


def _scan_swarm_calls(reports: dict[str, DayReport]) -> None:
    """Walk swarm-calls.jsonl (swarm_client.py telemetry), price Groq lanes for
    real, add to the matching ET-date report. Cerebras/local/OpenRouter lanes
    stay at $0 here (unverified-paid / tracked elsewhere -- see module docstring)."""
    if not SWARM_CALLS_TELEMETRY.exists():
        return
    target = set(reports.keys())
    try:
        with open(SWARM_CALLS_TELEMETRY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lane = entry.get("lane") or ""
                if not lane.startswith("groq::"):
                    continue
                ts = entry.get("ts") or ""
                et_date = _et_date(ts) if ts else ""
                if et_date not in target:
                    continue
                model = lane.split("::", 1)[1]
                in_tok = int(entry.get("input_tokens") or 0)
                out_tok = int(entry.get("output_tokens") or 0)
                cost = _groq_cost(model, in_tok, out_tok)
                report = reports[et_date]
                report.groq_calls += 1
                if cost is None:
                    report.groq_unpriced_models.add(model)
                    continue
                report.groq_cost += cost
                report.groq_by_model[model] += cost
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
    lines.append(f"  Groq:         ${report.groq_cost:>8.2f}  (calls={report.groq_calls})")
    for model, cost in report.groq_by_model.items():
        lines.append(f"    {model:30s}  ${cost:>7.4f}")
    if report.groq_unpriced_models:
        lines.append(f"    UNPRICED MODEL(S) SEEN: {sorted(report.groq_unpriced_models)} "
                      f"-- add rates to GROQ_PRICING, cost NOT included above")
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
        "groq_cost_usd": round(report.groq_cost, 4),
        "claude_sessions": report.claude_sessions,
        "minimax_calls": report.minimax_calls,
        "groq_calls": report.groq_calls,
    })
    existing.sort(key=lambda r: r.get("date_et", ""))
    try:
        with open(SPEND_DAILY_HISTORY, "w", encoding="utf-8") as f:
            for row in existing:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[spend-summary] WARN history write failed: {exc}", file=sys.stderr)


def _percentile(values: "list[float]", pct: float) -> float:
    """Linear-interpolation percentile (numpy-default method), 0 <= pct <= 100."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    k = (n - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def _load_spend_history_rows() -> "list[dict]":
    """Every row currently in spend-daily.jsonl (best-effort, skips malformed lines)."""
    rows: "list[dict]" = []
    if not SPEND_DAILY_HISTORY.exists():
        return rows
    try:
        with open(SPEND_DAILY_HISTORY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def _derive_warn_threshold(
    history_rows: "list[dict]",
    target_date: str,
    floor: float = WARN_FLOOR,
    pct: float = WARN_PERCENTILE,
    min_days: int = WARN_MIN_HISTORY_DAYS,
    window_days: int = WARN_WINDOW_DAYS,
) -> float:
    """Auto-derived WARN threshold: the `pct`-th percentile of the trailing
    `window_days` days' totals STRICTLY BEFORE `target_date` (today can never
    raise its own bar), floored at `floor`. Falls back to `floor` outright when
    fewer than `min_days` prior days of history exist -- not enough evidence to
    derive a meaningful percentile yet, and a floor default is safer than a
    percentile computed from 1-2 points. Pure function of its inputs (no I/O)
    so it's directly unit-testable against a fixture series.

    See module docstring ALERTING section for the 2026-09-03 rationale (the old
    static $30 threshold was breached on 20/20 sampled real-session days)."""
    prior = sorted(
        (r for r in history_rows if str(r.get("date_et", "")) < target_date),
        key=lambda r: r["date_et"],
    )
    window = prior[-window_days:] if window_days else prior
    if len(window) < min_days:
        return floor
    totals = [float(r.get("total_cost_usd", 0.0) or 0.0) for r in window]
    return round(max(floor, _percentile(totals, pct)), 2)


def _load_alert_state() -> dict:
    """Last recorded breach state, for transition-only alerting. Missing/corrupt
    file reads as {} (treated as 'not previously breached' by the caller) --
    fail-open, never blocks a run (C7)."""
    if not ALERT_STATE_FILE.exists():
        return {}
    try:
        return json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_alert_state(date_et: str, breached: bool, threshold: float, total_usd: float) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        ALERT_STATE_FILE.write_text(
            json.dumps({
                "date_et": date_et,
                "breached": breached,
                "threshold_usd": threshold,
                "total_usd": total_usd,
            }, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[spend-summary] WARN alert_state write failed: {exc}", file=sys.stderr)


def _status_known_broken_line(report: DayReport, threshold: float) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"- [{ts}] {STATUS_MARKER}WARN: {report.date_et} total ${report.total_cost:.2f} "
        f">= threshold ${threshold:.2f} (claude ${report.claude_total_cost:.2f} across "
        f"{report.claude_sessions} sessions, minimax ${report.minimax_cost:.2f}, groq "
        f"${report.groq_cost:.2f}) -- Anthropic list-price PROXY for Max-plan rate-limit "
        f"pressure, not a real bill (flat $200/mo 20x plan)."
    )


def _append_status_warn(report: DayReport, threshold: float) -> None:
    """De-duplicating STATUS.md '## Known broken' writer (status_known_broken.py) --
    inserts the SPEND_ marker line, replacing any prior SPEND_ reading. Caller is
    responsible for only invoking this on a genuine breach TRANSITION (see main()) --
    this function itself is unconditional given a breach, matching the pre-2026-09-03
    contract callers/tests already rely on."""
    skb.upsert(STATUS_MARKER, _status_known_broken_line(report, threshold), status_path=STATUS_FILE)


def _clear_status_warn() -> None:
    """Clears the SPEND_ marker on a breach -> not-breached transition (a
    green/recovered reading) -- same upsert(marker, None) convention every other
    status_known_broken caller uses."""
    skb.upsert(STATUS_MARKER, None, status_path=STATUS_FILE)


def _alert_discord(report: DayReport, threshold: float) -> None:
    """Terse Discord ping on threshold breach only -- GREEN=silent, matches
    self_check.py / github_audit.py so J sees a burn spike the same day it
    happens instead of finding it later in STATUS.md (turns the reactive
    '$52 planning burn' incidents into caught-before-they-compound ones).
    Caller is responsible for only invoking this on a breach TRANSITION (see
    main()) -- this function itself is unconditional given a breach, matching
    the pre-2026-09-03 contract test_spend_summary_discord_alert.py pins."""
    if report.total_cost < threshold:
        return
    if not DISCORD_OUTBOX.parent.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        msg = (f"SPEND WARN {report.date_et}: ${report.total_cost:.2f} "
               f"(threshold ${threshold:.2f}) — claude ${report.claude_total_cost:.2f} "
               f"across {report.claude_sessions} session(s), minimax ${report.minimax_cost:.2f}, "
               f"groq ${report.groq_cost:.2f}")
        with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "channel": "gamma-ops",
                                "source": "spend_summary", "message": msg[:500]}) + "\n")
    except OSError as exc:
        print(f"[spend-summary] WARN discord_outbox write failed: {exc}", file=sys.stderr)


def _alert_clear_discord(report: DayReport, threshold: float) -> None:
    """Symmetric CLEAR ping for a breached -> not-breached transition -- the other
    half of transition-only alerting (see module docstring ALERTING section).
    Unconditional given the caller decided a transition happened; no threshold
    gate here (mirrors _alert_discord's shape but for the opposite direction)."""
    if not DISCORD_OUTBOX.parent.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        msg = (f"SPEND CLEAR {report.date_et}: ${report.total_cost:.2f} "
               f"back under threshold ${threshold:.2f} — claude ${report.claude_total_cost:.2f} "
               f"across {report.claude_sessions} session(s)")
        with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "channel": "gamma-ops",
                                "source": "spend_summary", "message": msg[:500]}) + "\n")
    except OSError as exc:
        print(f"[spend-summary] WARN discord_outbox write failed: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="Specific ET date YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of trailing days to report (default 1 = today only)")
    parser.add_argument("--check-only", action="store_true",
                        help="Print summary to stdout; don't write files or STATUS.md")
    parser.add_argument("--warn-threshold", type=float, default=None,
                        help="Force a fixed total $/day WARN threshold, skipping auto-derivation. "
                             "Default (omitted): auto-derived every run as the "
                             f"{WARN_PERCENTILE:.0f}th percentile of the trailing {WARN_WINDOW_DAYS} "
                             f"days' totals (floored at ${WARN_FLOOR:.0f}) -- see _derive_warn_threshold "
                             "and the module docstring ALERTING section.")
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
    _scan_swarm_calls(reports)

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
            # Only alert on TODAY's breach (not retrospective backfills)
            today_et = _et_now().strftime("%Y-%m-%d")
            if d == today_et:
                _run_daily_alert(report, today_et, args.warn_threshold)

    return 0


def _run_daily_alert(report: DayReport, today_et: str, forced_threshold: "Optional[float]") -> dict:
    """Resolve today's WARN threshold (auto-derived unless `forced_threshold` is
    given), then fire transition-only alerts: a WARN only on not-breached ->
    breached, a CLEAR only on breached -> not-breached, SILENT otherwise (see
    module docstring ALERTING section). Always persists the new state so the
    NEXT run has something to compare against. Split out of main() so the
    decision logic is directly unit-testable without running the full
    session-scan pipeline. Returns a dict describing what happened (for tests)."""
    threshold = forced_threshold
    if threshold is None:
        threshold = _derive_warn_threshold(_load_spend_history_rows(), today_et)
    breached = report.total_cost >= threshold
    prev_state = _load_alert_state()
    prev_breached = bool(prev_state.get("breached", False))

    action = "silent"
    if breached and not prev_breached:
        _append_status_warn(report, threshold)
        _alert_discord(report, threshold)
        action = "warn"
    elif prev_breached and not breached:
        _clear_status_warn()
        _alert_clear_discord(report, threshold)
        action = "clear"
    _save_alert_state(today_et, breached, threshold, report.total_cost)
    return {"action": action, "threshold": threshold, "breached": breached, "prev_breached": prev_breached}


if __name__ == "__main__":
    sys.exit(main())
