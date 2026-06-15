"""Forensic analysis of Claude Code session JSONL transcripts.

Answers: where did the token burn go? Which sessions cost the most? Were they
interactive (J) or autonomous (scheduled tasks)?

USAGE
  python token_forensics.py                        # last 3 days, all stats
  python token_forensics.py --days 7               # last week
  python token_forensics.py --date 2026-05-22      # one specific UTC date
  python token_forensics.py --top 20               # show top-N sessions by cost
  python token_forensics.py --json                 # JSON instead of markdown

OUTPUT
  Markdown report to stdout + analysis/token-forensics/{YYYY-MM-DD}.md if --write

PRICING (Anthropic public, USD per 1M tokens, verified Q2 2026)
  claude-haiku-4-5         : $1.00 in / $5.00 out / $1.25 cwrite / $0.10 cread
  claude-sonnet-4-6        : $3.00 in / $15.00 out / $3.75 cwrite / $0.30 cread
  claude-opus-4-7          : $15.00 in / $75.00 out / $18.75 cwrite / $1.50 cread
  claude-opus-4-5          : $15.00 in / $75.00 out / $18.75 cwrite / $1.50 cread
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
SESSIONS_DIR = Path.home() / ".claude" / "projects" / "C--Users-jackw-Desktop-42"


# USD per 1M tokens. Pattern-matched on model id.
PRICING_PER_M = {
    "haiku": {"input": 1.00, "output": 5.00, "cache_creation": 1.25, "cache_read": 0.10},
    "sonnet": {"input": 3.00, "output": 15.00, "cache_creation": 3.75, "cache_read": 0.30},
    "opus": {"input": 15.00, "output": 75.00, "cache_creation": 18.75, "cache_read": 1.50},
}


def _price_for_model(model: str) -> dict[str, float]:
    m = (model or "").lower()
    if "opus" in m:
        return PRICING_PER_M["opus"]
    if "sonnet" in m:
        return PRICING_PER_M["sonnet"]
    if "haiku" in m:
        return PRICING_PER_M["haiku"]
    # Unknown -> charge as sonnet (conservative)
    return PRICING_PER_M["sonnet"]


def _compute_cost(model: str, usage: dict) -> float:
    if not usage:
        return 0.0
    p = _price_for_model(model)
    inp = float(usage.get("input_tokens", 0) or 0)
    out = float(usage.get("output_tokens", 0) or 0)
    cwrite = float(usage.get("cache_creation_input_tokens", 0) or 0)
    cread = float(usage.get("cache_read_input_tokens", 0) or 0)
    return (
        inp * p["input"]
        + out * p["output"]
        + cwrite * p["cache_creation"]
        + cread * p["cache_read"]
    ) / 1_000_000.0


@dataclass
class SessionStats:
    session_id: str
    file_path: Path
    file_mtime_utc: datetime
    file_bytes: int
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    entrypoint: str = ""
    cwd: str = ""
    git_branch: str = ""
    permission_mode: str = ""
    ai_title: str = ""
    n_user_turns: int = 0
    n_assistant_turns: int = 0
    n_tool_uses: int = 0
    models_used: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_input: int = 0
    total_output: int = 0
    total_cache_creation: int = 0
    total_cache_read: int = 0
    total_cost_usd: float = 0.0
    per_model_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def is_scheduled_task(self) -> bool:
        """Best-effort: scheduled tasks invoke via `--print` flag, captured in
        entrypoint or detectable by absence of interactive turns + short duration."""
        ep = (self.entrypoint or "").lower()
        if "--print" in ep or "print" in ep:
            return True
        # Heuristic: 1-2 user turns + many assistant turns with single short user prompt
        # is typical of one-shot --print invocation
        return False  # default: assume interactive

    @property
    def duration_minutes(self) -> Optional[float]:
        if not (self.first_ts and self.last_ts):
            return None
        try:
            t1 = datetime.fromisoformat(self.first_ts.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(self.last_ts.replace("Z", "+00:00"))
            return round((t2 - t1).total_seconds() / 60.0, 1)
        except Exception:
            return None


def _parse_session(path: Path) -> SessionStats:
    stats = SessionStats(
        session_id=path.stem,
        file_path=path,
        file_mtime_utc=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
        file_bytes=path.stat().st_size,
    )
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = d.get("type", "")
                ts = d.get("timestamp", "")
                if ts:
                    if not stats.first_ts:
                        stats.first_ts = ts
                    stats.last_ts = ts
                # Metadata from any event that carries it
                if d.get("entrypoint") and not stats.entrypoint:
                    stats.entrypoint = str(d.get("entrypoint"))[:200]
                if d.get("cwd") and not stats.cwd:
                    stats.cwd = str(d.get("cwd"))[:200]
                if d.get("gitBranch") and not stats.git_branch:
                    stats.git_branch = str(d.get("gitBranch"))[:80]
                if d.get("permissionMode") and not stats.permission_mode:
                    stats.permission_mode = str(d.get("permissionMode"))[:30]
                if t == "ai-title" and d.get("aiTitle") and not stats.ai_title:
                    stats.ai_title = str(d.get("aiTitle"))[:120]
                if t == "user":
                    stats.n_user_turns += 1
                if t == "assistant":
                    stats.n_assistant_turns += 1
                    msg = d.get("message", {})
                    model = msg.get("model", "")
                    usage = msg.get("usage", {})
                    if model:
                        stats.models_used[model] += 1
                    if usage:
                        stats.total_input += int(usage.get("input_tokens", 0) or 0)
                        stats.total_output += int(usage.get("output_tokens", 0) or 0)
                        stats.total_cache_creation += int(usage.get("cache_creation_input_tokens", 0) or 0)
                        stats.total_cache_read += int(usage.get("cache_read_input_tokens", 0) or 0)
                        cost = _compute_cost(model, usage)
                        stats.total_cost_usd += cost
                        stats.per_model_cost[model] += cost
                if t == "tool_use" or (t == "assistant" and isinstance(d.get("message", {}).get("content"), list)):
                    stats.n_tool_uses += 1
    except OSError as exc:
        print(f"[token-forensics] WARN failed to read {path.name}: {exc}", file=sys.stderr)
    return stats


def _filter_sessions(days: Optional[int], date_str: Optional[str]) -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    all_files = list(SESSIONS_DIR.glob("*.jsonl"))
    if date_str:
        # Filter to files whose first event ts starts with date_str
        # Cheaper: filter by mtime within +/- 36h of date_str
        try:
            d = datetime.fromisoformat(date_str)
        except ValueError:
            print(f"[token-forensics] bad date format: {date_str}", file=sys.stderr)
            return []
        d_start = d.replace(tzinfo=timezone.utc) - timedelta(hours=6)
        d_end = d.replace(tzinfo=timezone.utc) + timedelta(hours=42)
        return [f for f in all_files
                if d_start <= datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) <= d_end]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days or 3)
    return [f for f in all_files
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) >= cutoff]


def _format_md(sessions: list[SessionStats], top_n: int, label: str) -> str:
    lines = [
        f"# Token forensics — {label}",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC_",
        "",
        f"**Sessions analyzed:** {len(sessions)}",
        "",
    ]

    total_cost = sum(s.total_cost_usd for s in sessions)
    total_input = sum(s.total_input for s in sessions)
    total_output = sum(s.total_output for s in sessions)
    total_cread = sum(s.total_cache_read for s in sessions)
    total_cwrite = sum(s.total_cache_creation for s in sessions)

    lines.extend([
        "## Aggregate totals",
        "",
        f"- **Total cost:** ${total_cost:.2f}",
        f"- **Input tokens:** {total_input:,}",
        f"- **Output tokens:** {total_output:,}",
        f"- **Cache writes:** {total_cwrite:,}",
        f"- **Cache reads:** {total_cread:,}  (cache reads dominate cost when context is reused)",
        "",
    ])

    # By model
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "calls": 0, "sessions": set()})
    for s in sessions:
        for m, n in s.models_used.items():
            by_model[m]["calls"] += n
            by_model[m]["sessions"].add(s.session_id)
        for m, c in s.per_model_cost.items():
            by_model[m]["cost"] += c
    lines.extend([
        "## By model",
        "",
        "| Model | Calls | Sessions | Cost USD |",
        "|---|---:|---:|---:|",
    ])
    for m, info in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]):
        lines.append(f"| `{m}` | {int(info['calls'])} | {len(info['sessions'])} | ${info['cost']:.2f} |")
    lines.append("")

    # Top sessions by cost
    top = sorted(sessions, key=lambda s: -s.total_cost_usd)[:top_n]
    lines.extend([
        f"## Top {top_n} sessions by cost",
        "",
        "| # | First ts (UTC) | Duration min | Cost USD | Output tok | Cache read tok | Models | Title / Entrypoint |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ])
    for i, s in enumerate(top, 1):
        models = ", ".join(sorted(s.models_used.keys())) or "?"
        title = s.ai_title[:60] if s.ai_title else (s.entrypoint[:60] or "?")
        first = (s.first_ts or "?")[:19]
        dur = f"{s.duration_minutes:.1f}" if s.duration_minutes else "?"
        lines.append(
            f"| {i} | {first} | {dur} | ${s.total_cost_usd:.2f} | "
            f"{s.total_output:,} | {s.total_cache_read:,} | "
            f"{models[:40]} | {title} |"
        )
    lines.append("")

    # By UTC date breakdown
    by_date: dict[str, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "sessions": 0, "input": 0, "output": 0, "cache_read": 0})
    for s in sessions:
        d = (s.first_ts or s.file_mtime_utc.isoformat())[:10]
        by_date[d]["cost"] += s.total_cost_usd
        by_date[d]["sessions"] += 1
        by_date[d]["input"] += s.total_input
        by_date[d]["output"] += s.total_output
        by_date[d]["cache_read"] += s.total_cache_read
    lines.extend([
        "## By UTC date",
        "",
        "| Date | Sessions | Cost USD | Output tok | Cache read tok |",
        "|---|---:|---:|---:|---:|",
    ])
    for d in sorted(by_date.keys()):
        info = by_date[d]
        lines.append(
            f"| {d} | {info['sessions']} | ${info['cost']:.2f} | "
            f"{int(info['output']):,} | {int(info['cache_read']):,} |"
        )
    lines.append("")

    return "\n".join(lines)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, help="Look back N days (default 3)")
    g.add_argument("--date", help="Specific UTC date YYYY-MM-DD")
    parser.add_argument("--top", type=int, default=15, help="Top N sessions by cost in detail table")
    parser.add_argument("--write", help="Also write markdown report to this path")
    parser.add_argument("--json", action="store_true", help="JSON output instead of markdown")
    args = parser.parse_args()

    files = _filter_sessions(args.days, args.date)
    if not files:
        print("no session files found in window", file=sys.stderr)
        return 1

    label = args.date if args.date else f"last {args.days or 3} day(s)"
    print(f"[token-forensics] parsing {len(files)} session file(s) for {label}...", file=sys.stderr)

    sessions = [_parse_session(f) for f in files]
    # Drop sessions with zero cost AND zero turns (empty placeholder files)
    sessions = [s for s in sessions if s.total_cost_usd > 0 or s.n_assistant_turns > 0]

    if args.json:
        out = {
            "label": label,
            "total_sessions": len(sessions),
            "total_cost_usd": round(sum(s.total_cost_usd for s in sessions), 4),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "first_ts": s.first_ts,
                    "last_ts": s.last_ts,
                    "duration_min": s.duration_minutes,
                    "ai_title": s.ai_title,
                    "models": dict(s.models_used),
                    "total_cost_usd": round(s.total_cost_usd, 4),
                    "input_tokens": s.total_input,
                    "output_tokens": s.total_output,
                    "cache_read": s.total_cache_read,
                    "cache_creation": s.total_cache_creation,
                    "user_turns": s.n_user_turns,
                    "assistant_turns": s.n_assistant_turns,
                    "entrypoint": s.entrypoint[:120],
                    "permission_mode": s.permission_mode,
                }
                for s in sorted(sessions, key=lambda x: -x.total_cost_usd)[:args.top]
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        md = _format_md(sessions, args.top, label)
        print(md)
        if args.write:
            out_path = Path(args.write)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")
            print(f"\n[token-forensics] wrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(_main())
