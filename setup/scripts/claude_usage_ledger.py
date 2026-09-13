#!/usr/bin/env python3
"""claude_usage_ledger.py -- $0 pure-Python read of Claude Code's local transcripts.

WHY (J 2026-09-13, GOAL-EARN-YOUR-KEEP item 5's "tokens spent per day"): J's complaint is
"it's too expensive and not producing enough outcome" -- but nobody has a number. This is the
instrument. It reads ~/.claude/projects/**/*.jsonl (every Claude Code session transcript on
this box, across all projects -- interactive desktop, headless/scheduled fires, and subagent
sidechains all land in the same tree) and answers: what did Claude cost per day, by who spent
it, over the last 14 days.

SCHEMA (verified against real transcripts 2026-09-13, not assumed):
  Each JSONL line is one event. An assistant message with token usage looks like:
    {"type": "assistant", "sessionId": "...", "isSidechain": false, "entrypoint": "claude-desktop",
     "cwd": "...", "timestamp": "2026-09-07T04:04:46.791Z",
     "message": {"model": "claude-fable-5-1", "usage": {
         "input_tokens": 2, "output_tokens": 710,
         "cache_creation_input_tokens": 69893, "cache_read_input_tokens": 45041, ...}}}
  Token fields live under message.usage: input_tokens / output_tokens /
  cache_creation_input_tokens / cache_read_input_tokens. model lives under message.model.

KIND RULE (derived from the real tree, not guessed):
  - subagent:  isSidechain == True.  Subagent/Task-tool transcripts are written as sidechain
    events interleaved into the SAME session file as their parent -- confirmed by grepping
    2,612 real transcript files: isSidechain True co-occurs with an `agentId` field, isSidechain
    False never carries one.
  - interactive: isSidechain == False AND entrypoint == "claude-desktop" (the desktop/CLI
    interactive app -- 12,566 of ~13,857 non-sidechain-eligible lines sampled).
  - headless/scheduled: isSidechain == False AND entrypoint in {"sdk-cli", "sdk-ts", "cli"} --
    programmatic / `claude -p` / SDK-driven launches, which is how this repo's scheduled tasks
    and conductor fires invoke Claude (grep of automation/setup scripts confirms subprocess
    launches, not the desktop app).
  - unknown: entrypoint missing or an unrecognized value. Never guessed into one of the above.

DOLLAR EQUIVALENT: this is an API-RATE EQUIVALENT for CONSUMPTION under a subscription plan
(Claude Max), NOT a bill -- the user does not pay per-token on Max. Rates ($/M tokens):
  Opus-class / Fable: $15 in / $75 out   Sonnet: $3 in / $15 out   Haiku: $1 in / $5 out
  cache read = 10% of that model's input rate; cache write (cache_creation) = 125% of it.
Model family is matched by substring on the model id ("opus"/"fable" > "sonnet" > "haiku");
anything unmatched is priced at Sonnet rates and flagged, never silently dropped.

FAILS OPEN: a single unparseable line or unreadable file is skipped and counted, never raises
(C7) -- this is a reporting script, it must never be the thing that breaks a session.
Pure stdlib. $0. Reads only, never writes into ~/.claude.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
CONDUCTOR_OUTCOMES = REPO / "automation" / "state" / "conductor-outcomes.jsonl"
CONDUCTOR_BUDGET = REPO / "automation" / "state" / "conductor-budget.json"
CONDUCTOR_SELF_REPORT_CORRECTION = 2.2  # conductor-budget.json's documented under-report factor

OUT_DIR = REPO / "analysis" / "usage"
OUT_JSON = OUT_DIR / "claude-usage-14d.json"
OUT_MD = OUT_DIR / "claude-usage-14d.md"

MAX_PLAN_PER_DAY_USD = 6.67  # $200/mo Max 20x, per CLAUDE.md

# Rates: $ per 1M tokens (input, output). Matched by substring on the model id, checked in
# this order (most specific first) so "claude-3-5-haiku" doesn't match a looser "sonnet" rule.
RATE_TABLE = [
    ("opus", 15.0, 75.0),
    ("fable", 15.0, 75.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 1.0, 5.0),
]
DEFAULT_RATE = ("sonnet-default(unmatched)", 3.0, 15.0)
CACHE_READ_FACTOR = 0.10
CACHE_WRITE_FACTOR = 1.25

KNOWN_HEADLESS_ENTRYPOINTS = {"sdk-cli", "sdk-ts", "cli"}
KNOWN_INTERACTIVE_ENTRYPOINTS = {"claude-desktop"}


def rate_for_model(model: str | None) -> tuple[str, float, float]:
    """Return (label, in_rate, out_rate) per 1M tokens for a model id, substring-matched."""
    m = (model or "").lower()
    for key, rin, rout in RATE_TABLE:
        if key in m:
            return (key, rin, rout)
    return DEFAULT_RATE


def classify_kind(is_sidechain: Any, entrypoint: Any) -> str:
    if is_sidechain is True:
        return "subagent"
    if is_sidechain is False:
        if entrypoint in KNOWN_INTERACTIVE_ENTRYPOINTS:
            return "interactive"
        if entrypoint in KNOWN_HEADLESS_ENTRYPOINTS:
            return "scheduled"
    return "unknown"


def usd_for_usage(usage: dict, model: str | None) -> tuple[float, str]:
    """Dollar API-rate equivalent for one assistant message's usage block."""
    label, rin, rout = rate_for_model(model)
    inp = float(usage.get("input_tokens") or 0)
    out = float(usage.get("output_tokens") or 0)
    cread = float(usage.get("cache_read_input_tokens") or 0)
    cwrite = float(usage.get("cache_creation_input_tokens") or 0)
    usd = (
        inp * rin / 1e6
        + out * rout / 1e6
        + cread * (rin * CACHE_READ_FACTOR) / 1e6
        + cwrite * (rin * CACHE_WRITE_FACTOR) / 1e6
    )
    return usd, label


def iter_transcript_lines(root: Path):
    """Yield (file_path, parsed_dict) for every parseable JSONL line under root. Skips
    unreadable files/lines rather than raising (C7)."""
    if not root.exists():
        return
    for fp in root.glob("**/*.jsonl"):
        try:
            with fp.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    yield fp, d
        except OSError:
            continue


def day_of(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.date().isoformat()


def build_ledger(days: int = 14, now: datetime | None = None,
                  root: Path = CLAUDE_PROJECTS) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days - 1)).date()

    # per-day accumulators
    per_day: dict[str, dict] = {}
    # top sessions: file -> {tokens, usd, first_user_msg, day}
    sessions: dict[str, dict] = {}

    unmatched_models: set[str] = set()

    for fp, d in iter_transcript_lines(root):
        dtype = d.get("type")
        ts = d.get("timestamp")
        date_str = day_of(ts)

        # Track first user message per session (for top-5 report), regardless of date filter,
        # so a session that started earlier still gets a recognizable label if it has spend
        # inside the window.
        sess_key = str(fp)
        if dtype == "user" and sess_key not in sessions:
            msg = d.get("message") or {}
            content = msg.get("content")
            text = None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        break
            if text:
                sessions.setdefault(sess_key, {})["first_user_msg"] = text[:100]

        if dtype != "assistant":
            continue
        msg = d.get("message") or {}
        usage = msg.get("usage")
        if not usage:
            continue
        if date_str is None or date_str < cutoff_date.isoformat():
            continue

        model = msg.get("model")
        kind = classify_kind(d.get("isSidechain"), d.get("entrypoint"))
        usd, rate_label = usd_for_usage(usage, model)
        if rate_label == DEFAULT_RATE[0] and model:
            unmatched_models.add(model)

        inp = float(usage.get("input_tokens") or 0)
        out = float(usage.get("output_tokens") or 0)
        cread = float(usage.get("cache_read_input_tokens") or 0)
        cwrite = float(usage.get("cache_creation_input_tokens") or 0)

        day_bucket = per_day.setdefault(date_str, {
            "tokens": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
            "usd_total": 0.0,
            "by_kind": defaultdict(lambda: {"usd": 0.0, "tokens": 0.0}),
            "by_model": defaultdict(lambda: {"usd": 0.0, "tokens": 0.0}),
        })
        day_bucket["tokens"]["input"] += inp
        day_bucket["tokens"]["output"] += out
        day_bucket["tokens"]["cache_read"] += cread
        day_bucket["tokens"]["cache_write"] += cwrite
        day_bucket["usd_total"] += usd
        day_bucket["by_kind"][kind]["usd"] += usd
        day_bucket["by_kind"][kind]["tokens"] += inp + out + cread + cwrite
        model_key = model or "unknown"
        day_bucket["by_model"][model_key]["usd"] += usd
        day_bucket["by_model"][model_key]["tokens"] += inp + out + cread + cwrite

        sess = sessions.setdefault(sess_key, {})
        sess["usd_total"] = sess.get("usd_total", 0.0) + usd
        sess["tokens_total"] = sess.get("tokens_total", 0.0) + inp + out + cread + cwrite
        sess["day"] = date_str

    # finalize per_day (convert defaultdicts to plain dicts, round)
    days_out = {}
    for date_str, bucket in sorted(per_day.items()):
        by_kind = {k: {"usd": round(v["usd"], 4), "tokens": v["tokens"]}
                   for k, v in bucket["by_kind"].items()}
        kind_usd_total = sum(v["usd"] for v in by_kind.values()) or 1e-9
        by_kind_pct = {k: round(100.0 * v["usd"] / kind_usd_total, 1) for k, v in by_kind.items()}
        by_model = {k: {"usd": round(v["usd"], 4), "tokens": v["tokens"]}
                    for k, v in bucket["by_model"].items()}
        days_out[date_str] = {
            "tokens": bucket["tokens"],
            "usd_total": round(bucket["usd_total"], 4),
            "by_kind": by_kind,
            "by_kind_pct": by_kind_pct,
            "by_model": by_model,
        }

    top_sessions = sorted(
        (
            {"file": k, **v}
            for k, v in sessions.items()
            if v.get("usd_total")
        ),
        key=lambda s: -s["usd_total"],
    )[:5]
    for s in top_sessions:
        s["usd_total"] = round(s["usd_total"], 4)

    total_usd = sum(v["usd_total"] for v in days_out.values())
    n_days_with_data = len(days_out) or 1
    avg_per_day = total_usd / n_days_with_data

    # conductor family self-reported cost, corrected, joined alongside (not merged into)
    conductor_total_raw = 0.0
    conductor_total_corrected = 0.0
    conductor_rows_in_window = 0
    if CONDUCTOR_OUTCOMES.exists():
        try:
            with CONDUCTOR_OUTCOMES.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    fired_at = row.get("fired_at")
                    d = day_of(fired_at)
                    if d is None or d < cutoff_date.isoformat():
                        continue
                    conductor_rows_in_window += 1
                    c = float(row.get("cost_usd") or 0.0)
                    conductor_total_raw += c
                    conductor_total_corrected += c * CONDUCTOR_SELF_REPORT_CORRECTION
        except OSError:
            pass

    overall_by_kind = defaultdict(float)
    for bucket in days_out.values():
        for k, v in bucket["by_kind"].items():
            overall_by_kind[k] += v["usd"]
    overall_kind_total = sum(overall_by_kind.values()) or 1e-9
    overall_by_kind_pct = {k: round(100.0 * v / overall_kind_total, 1)
                            for k, v in overall_by_kind.items()}

    return {
        "generated_at_utc": now.isoformat(),
        "window_days": days,
        "note": ("API-rate equivalent for CONSUMPTION under a subscription plan (Claude Max), "
                 "NOT a bill -- Max is not billed per token."),
        "max_plan_per_day_usd": MAX_PLAN_PER_DAY_USD,
        "days": days_out,
        "totals": {
            "usd_total": round(total_usd, 4),
            "avg_usd_per_day": round(avg_per_day, 4),
            "by_kind_pct": overall_by_kind_pct,
        },
        "top_5_sessions": top_sessions,
        "conductor_family": {
            "rows_in_window": conductor_rows_in_window,
            "self_reported_usd": round(conductor_total_raw, 4),
            "corrected_usd": round(conductor_total_corrected, 4),
            "correction_factor": CONDUCTOR_SELF_REPORT_CORRECTION,
            "source": str(CONDUCTOR_OUTCOMES.relative_to(REPO)) if CONDUCTOR_OUTCOMES.exists() else None,
        },
        "unmatched_model_ids": sorted(unmatched_models),
    }


def render_md(ledger: dict) -> str:
    L = []
    L.append("# Claude usage ledger -- last 14 days")
    L.append("")
    L.append(f"> Generated `{ledger['generated_at_utc']}` by "
             "`setup/scripts/claude_usage_ledger.py`. Reads local transcripts under "
             "`~/.claude/projects/**/*.jsonl` -- $0, read-only, no network.")
    L.append(f"> **{ledger['note']}**")
    L.append("")
    t = ledger["totals"]
    L.append(f"## 14-day totals")
    L.append("")
    L.append(f"- **$-equivalent total:** ${t['usd_total']:.2f}")
    L.append(f"- **$-equivalent per day:** ${t['avg_usd_per_day']:.2f} "
             f"vs the $200/mo Max plan (= ${ledger['max_plan_per_day_usd']:.2f}/day)")
    pct = t["by_kind_pct"]
    L.append(f"- **share by kind:** " + " · ".join(
        f"{k} {v}%" for k, v in sorted(pct.items(), key=lambda kv: -kv[1])))
    L.append("")

    cf = ledger["conductor_family"]
    L.append("## Conductor family (self-reported, joined not merged)")
    L.append("")
    L.append(f"- {cf['rows_in_window']} outcome rows in window")
    L.append(f"- self-reported: ${cf['self_reported_usd']:.2f} · "
             f"corrected (x{cf['correction_factor']}): ${cf['corrected_usd']:.2f}")
    L.append("")

    L.append("## Per day")
    L.append("")
    L.append("| Date | $-equiv | interactive % | scheduled % | subagent % | unknown % |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for date_str, bucket in sorted(ledger["days"].items()):
        p = bucket["by_kind_pct"]
        L.append(f"| {date_str} | ${bucket['usd_total']:.2f} | "
                 f"{p.get('interactive', 0)}% | {p.get('scheduled', 0)}% | "
                 f"{p.get('subagent', 0)}% | {p.get('unknown', 0)}% |")
    L.append("")

    L.append("## Top 5 most expensive sessions")
    L.append("")
    if ledger["top_5_sessions"]:
        for s in ledger["top_5_sessions"]:
            msg = (s.get("first_user_msg") or "(no user message captured)").replace("\n", " ")
            L.append(f"- `${s['usd_total']:.2f}` — `{s['file']}` — \"{msg}\"")
    else:
        L.append("- none")
    L.append("")

    if ledger["unmatched_model_ids"]:
        L.append("## Model ids priced at Sonnet default (unmatched by rate table)")
        L.append("")
        for m in ledger["unmatched_model_ids"]:
            L.append(f"- `{m}`")
        L.append("")

    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--root", default=None, help="override transcript root (for tests)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else CLAUDE_PROJECTS
    ledger = build_ledger(days=args.days, root=root)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_md(ledger), encoding="utf-8")

    print(f"[usage-ledger] wrote {OUT_JSON.relative_to(REPO)}")
    print(f"[usage-ledger] wrote {OUT_MD.relative_to(REPO)}")
    print(f"[usage-ledger] {ledger['totals']['usd_total']:.2f} total over "
          f"{len(ledger['days'])} days with data, avg "
          f"${ledger['totals']['avg_usd_per_day']:.2f}/day")
    return 0


if __name__ == "__main__":
    sys.exit(main())
