"""EOD pipeline analytics -- runs on free-tier models (primary) or Claude (backup).

EVOLUTION (2026-05-22): originally a "fallback" path that only ran when Claude
was rate-limited. Now the PRIMARY path for all analytical scheduled tasks
(analyst, manager, eod-summary) per J directive: "we need to figure out how to
use the free or super cheap models for one of them. im not paying for more
anthropic api calls."

PRIMARY PATH (--primary, default for PS1 wrappers):
  Model ladder: Nemotron-3-Super-120B (free, 1M ctx) → DeepSeek-V4-Flash (free)
  → MiniMax-M2.5 (free) → MiniMax-M2.5 (paid, $3/day cap).
  Output tagged "FREE-TIER ROUTE" so J knows the production path.

FALLBACK PATH (no --primary, called by Invoke-ClaudeWithRetry):
  Same ladder but tagged "FALLBACK ROUTE" indicating Claude failed first.

CONTRACT:
  * Outputs land at the same canonical paths Claude would write to
  * Tool-dependent features (e.g., Analyst's `_chef-inbox/` routing,
    Manager's MCP Alpaca status pings) are SKIPPED -- documented in output
  * If all tiers fail, exit non-zero so the wrapper logs CRITICAL

Supported tasks: analyst | manager | eod-summary  (3 safe ones per J 2026-05-20).
Daily-review NOT supported -- its key-levels.json output is consumed by the
next morning's premarket and structured-JSON degradation is too risky.

Usage:
    python eod_fallback.py --task analyst [--primary]
    python eod_fallback.py --task manager [--primary]
    python eod_fallback.py --task eod-summary [--primary]
    python eod_fallback.py --task analyst --date 2026-05-20 --dry-run

Per CLAUDE.md OP-3 (cost discipline) + OP-30 free-tier-first + OP-27 L41.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from run_minimax import call_minimax  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ── Free-tier model ladder (OP-30: free-tier-first for autonomous analytics) ──
# Try each tier in order; advance on 429 / rate-limit errors.
# Nemotron first: 120B MoE reasoning model, 1M ctx, $0.
# Last tier is paid MiniMax M2.5 (~$0.003/call) — only fires if all free tiers 429.
_LADDER_FREE_1 = "nvidia/nemotron-3-super-120b-a12b:free"
_LADDER_FREE_2 = "deepseek/deepseek-v4-flash:free"
_LADDER_FREE_3 = "minimax/minimax-m2.5:free"
_LADDER_PAID   = "minimax/minimax-m2.5"
_MODEL_LADDER  = [_LADDER_FREE_1, _LADDER_FREE_2, _LADDER_FREE_3, _LADDER_PAID]


def _call_with_ladder(
    system: str,
    prompt: str,
    max_tokens: int,
    task_id: str,
    timeout: int,
) -> dict:
    """Try free-tier models first; fall back through the ladder on 429/failure.

    Returns the result dict from the first tier that succeeds (ok=True), or the
    last tier's result if all tiers fail.
    """
    last_result: dict = {"ok": False, "error": "no_tiers_tried", "cost_usd": 0.0, "model": "none"}
    for model in _MODEL_LADDER:
        result = call_minimax(
            prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            task_id=task_id,
            timeout=timeout,
        )
        last_result = result
        if result.get("ok"):
            return result
        err = str(result.get("error", "")).lower()
        # Hard failures (auth/permission): no point trying further models
        if any(kw in err for kw in ("auth", "permission", "invalid_key", "unauthorized")):
            print(f"[eod-analytics] {model}: hard failure ({err[:100]}) -- aborting ladder",
                  file=sys.stderr)
            break
        # Rate-limit / timeout / transient: try next tier
        print(f"[eod-analytics] {model}: soft failure ({err[:80]}) -- trying next tier",
              file=sys.stderr)
    return last_result


# DST-aware ET helper (no tzdata dependency).
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


# Headless launch redirect
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"eod-fallback-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"eod-fallback-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


MAX_INLINE_BYTES = 60_000  # cap per input file to keep prompt budget sane


def _read_file_safe(path: Path, max_bytes: int = MAX_INLINE_BYTES) -> str:
    """Read a file as text, returning '' on missing/error. Truncates with a marker
    above max_bytes."""
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[... truncated {len(data) - max_bytes:,} bytes ...]"
        return data
    except OSError as exc:
        return f"[read error: {exc}]"


def _read_csv_today_only(path: Path, today: str) -> str:
    """Read trades.csv but filter to today's rows (avoid sending full ledger)."""
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return ""
        header = lines[0]
        # Find date column by name (defensive)
        cols = [c.strip().lower() for c in header.split(",")]
        date_idx = next((i for i, c in enumerate(cols) if "date" in c or c == "ts" or "timestamp" in c), 0)
        kept = [header]
        for ln in lines[1:]:
            fields = ln.split(",")
            if date_idx < len(fields) and fields[date_idx].startswith(today):
                kept.append(ln)
        return "\n".join(kept) if len(kept) > 1 else f"{header}\n[no trades today]"
    except OSError as exc:
        return f"[read error: {exc}]"


def _read_jsonl_today_only(path: Path, today: str, max_rows: int = 200) -> str:
    """Read a JSONL file but filter to today's rows (by ts/timestamp/timestamp_et)."""
    if not path.exists():
        return ""
    try:
        kept: list[str] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    # JSONL may contain bare strings or arrays; keep them if today's
                    # date appears in the raw line (best-effort).
                    if today in line:
                        kept.append(line)
                    continue
                ts = obj.get("ts") or obj.get("timestamp") or obj.get("timestamp_et") or ""
                if isinstance(ts, str) and ts.startswith(today):
                    kept.append(line)
                if len(kept) >= max_rows:
                    kept.append(f'{{"_truncated": "max_rows={max_rows} reached"}}')
                    break
        return "\n".join(kept) if kept else "[no rows for today]"
    except OSError as exc:
        return f"[read error: {exc}]"


def _inline_block(label: str, content: str) -> str:
    """Format a file block for the prompt. Use heredoc-style fences."""
    if not content:
        return f"### {label}\n(empty / not present)\n"
    return f"### {label}\n```\n{content}\n```\n"


def _format_fallback_output(body: str, *, task: str, date_str: str,
                             cost_usd: float, model: str, omitted_features: list[str],
                             primary: bool = False) -> str:
    """Wrap free-tier output with a route header so J can see which path fired."""
    route = "FREE-TIER PRIMARY" if primary else "FALLBACK ROUTE (Claude rate-limited)"
    claude_note = "" if primary else " because Claude was rate-limited"
    header = (
        f"<!-- {route}: this file was generated by a free-tier model{claude_note}. -->\n"
        f"<!-- Task: {task}  Date: {date_str}  Model: {model}  Cost: ${cost_usd:.4f} -->\n"
        f"<!-- Omitted features (tool-dependent, skipped on free-tier path): "
        f"{', '.join(omitted_features) if omitted_features else 'none'} -->\n\n"
    )
    return header + body


def _append_status_warn(task: str, date_str: str, ok: bool, error: Optional[str],
                         cost_usd: float, primary: bool = False) -> None:
    if not STATUS_FILE.parent.exists():
        return
    try:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        severity = "INFO" if (ok and primary) else ("WARN" if ok else "BROKEN")
        route = "free-tier-primary" if primary else "fallback-on-rate-limit"
        lines = [
            "",
            f"### {severity}: eod-analytics {task} used free-tier model ({route})",
            f"- ts: {ts}",
            f"- task: {task}",
            f"- date_et: {date_str}",
            f"- route: {route}",
            f"- ok: {ok}",
            f"- cost_usd: {cost_usd:.4f}",
        ]
        if error:
            lines.append(f"- error: {error}")
        if not primary:
            lines.append("- note: output is reduced quality (no tool calls). Re-run on Claude if quality matters.")
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"[eod-analytics] WARN status_md write failed: {exc}", file=sys.stderr)


# ────────────────────────────────────────────────────────────────────────────
# Task definitions
# ────────────────────────────────────────────────────────────────────────────


def _system_analyst() -> str:
    return (
        "You are Analyst -- the EOD digest writer for Project Gamma. You are running in FALLBACK MODE: "
        "Claude was rate-limited, so you are MiniMax M2 producing a degraded but useful EOD digest. "
        "You CANNOT call tools; you only read inputs inlined in the prompt and emit markdown. "
        "Do NOT propose strategy candidates (that's Chef's job and the inbox-routing tools are not available). "
        "Do NOT modify any state files; only emit the digest text."
    )


def _prompt_analyst(date_str: str) -> tuple[str, list[str]]:
    """Build the analyst-mode prompt. Returns (prompt, omitted_features)."""
    today = date_str
    today_dt = _et_now()  # for runtime header only
    weekday = datetime.strptime(today, "%Y-%m-%d").strftime("%A")

    sections = [
        _inline_block(f"trades.csv (today only)",
                      _read_csv_today_only(REPO / "journal" / "trades.csv", today)),
        _inline_block(f"decisions.jsonl (today only, cap 200 rows)",
                      _read_jsonl_today_only(STATE_DIR / "decisions.jsonl", today)),
        _inline_block(f"journal/{today}.md",
                      _read_file_safe(REPO / "journal" / f"{today}.md")),
        _inline_block("today-bias.json",
                      _read_file_safe(STATE_DIR / "today-bias.json", 20_000)),
        _inline_block("loop-state.json",
                      _read_file_safe(STATE_DIR / "loop-state.json", 20_000)),
        _inline_block("current-position.json",
                      _read_file_safe(STATE_DIR / "current-position.json", 5_000)),
        _inline_block("scout_output.json",
                      _read_file_safe(REPO / "automation" / "scout" / "state" / "scout_output.json", 20_000)),
        _inline_block("swarm_output.json",
                      _read_file_safe(REPO / "automation" / "swarm" / "state" / "swarm_output.json", 30_000)),
        _inline_block("gym scorecard (latest)",
                      _read_file_safe(REPO / "crypto" / "data" / "scorecards" / "latest.json", 20_000)),
    ]
    body = (
        f"# EOD Digest -- {today} ({weekday}) -- FALLBACK ROUTE\n\n"
        f"Wall-clock at write: {today_dt.strftime('%Y-%m-%dT%H:%M:%S')} ET\n\n"
        "## Inputs (inlined)\n\n" + "\n".join(sections) + "\n\n"
        "## Required output (markdown)\n\n"
        "Write a clean EOD digest. Required sections:\n"
        "1. **One-line headline** -- P&L (Safe + Bold if both data present), # trades, # rule breaks (if any).\n"
        "2. **Per-trade audit** -- for each trade in trades.csv today: ticker/strike, entry/exit, P&L, "
        "rule compliance (any of 10 rules broken? specify which), what worked, what didn't.\n"
        "3. **Decisions journal** -- summarize from decisions.jsonl: how many ENTER signals fired, "
        "how many were taken, how many skipped + why. Flag any ghost-entry patterns (ENTER logged "
        "without matching trade).\n"
        "4. **Pattern observations** -- 1-3 patterns you saw in today's tape (e.g., morning chop, "
        "afternoon trend, ribbon flips). Tie back to the morning bias if there's a match/miss.\n"
        "5. **One thing to fix tomorrow** -- ONE concrete observation. Not a strategy proposal.\n\n"
        "Keep it under 800 words. Use bullet points liberally. No emojis. No tool calls. "
        "Do NOT propose strategy changes -- this is observation only."
    )
    omitted = [
        "_chef-inbox routing (no Write tool)",
        "mistakes.md append (no Write tool)",
        "_analyst-log.jsonl entry (no Write tool)",
        "patterns/{slug}.md updates (no Write tool)",
    ]
    return body, omitted


def _system_manager() -> str:
    return (
        "You are Gamma in Manager mode -- the conductor verifying the daily loop ran. You are in "
        "FALLBACK MODE on MiniMax M2 because Claude was rate-limited. You CANNOT call tools or MCP; "
        "you only read inputs inlined in the prompt and emit markdown. Be concise and verification-focused."
    )


def _prompt_manager(date_str: str) -> tuple[str, list[str]]:
    today = date_str
    today_dt = _et_now()
    weekday = datetime.strptime(today, "%Y-%m-%d").strftime("%A")

    sections = [
        _inline_block("today-bias.json",
                      _read_file_safe(STATE_DIR / "today-bias.json", 15_000)),
        _inline_block("loop-state.json",
                      _read_file_safe(STATE_DIR / "loop-state.json", 15_000)),
        _inline_block("current-position.json",
                      _read_file_safe(STATE_DIR / "current-position.json", 5_000)),
        _inline_block("current-position-bold.json",
                      _read_file_safe(STATE_DIR / "current-position-bold.json", 5_000)),
        _inline_block("decisions.jsonl (today, cap 100 rows)",
                      _read_jsonl_today_only(STATE_DIR / "decisions.jsonl", today, max_rows=100)),
        _inline_block(f"journal/{today}.md",
                      _read_file_safe(REPO / "journal" / f"{today}.md", 40_000)),
        _inline_block(f"analysis/eod/{today}.md (if analyst already ran)",
                      _read_file_safe(REPO / "analysis" / "eod" / f"{today}.md", 30_000)),
        _inline_block("scout_output.json",
                      _read_file_safe(REPO / "automation" / "scout" / "state" / "scout_output.json", 15_000)),
        _inline_block("swarm_output.json",
                      _read_file_safe(REPO / "automation" / "swarm" / "state" / "swarm_output.json", 20_000)),
        _inline_block("STATUS.md tail (last 60 lines for known-broken section)",
                      _tail_text(STATUS_FILE, 60)),
        _inline_block("key-levels.json",
                      _read_file_safe(STATE_DIR / "key-levels.json", 15_000)),
        _inline_block("news.json",
                      _read_file_safe(STATE_DIR / "news.json", 20_000)),
    ]
    body = (
        f"# Daily Brief -- {today} ({weekday}) -- FALLBACK ROUTE\n\n"
        f"Wall-clock at write: {today_dt.strftime('%Y-%m-%dT%H:%M:%S')} ET\n\n"
        "## Inputs (inlined)\n\n" + "\n".join(sections) + "\n\n"
        "## Required output (markdown)\n\n"
        "Write a single-screen daily brief for J. Required sections:\n"
        "1. **TLDR** -- 1-3 sentences. Was today flat, winning, losing? Anything unusual?\n"
        "2. **What ran / what didn't** -- list each scheduled phase and whether its expected "
        "deliverable is present in the inputs above. Specifically check: scout, swarm, premarket "
        "(today-bias.json populated), heartbeat (decisions.jsonl >=10 rows), EOD flatten (position null), "
        "analyst (analysis/eod/{today}.md present).\n"
        "3. **P&L snapshot** -- if loop-state or position files show numbers, surface them. Both accounts "
        "if both present.\n"
        "4. **Known-broken** -- pull RED/BROKEN/WARN entries from STATUS.md tail. List with one-line context.\n"
        "5. **Tomorrow's setup** -- from scout + swarm + key-levels + news: what's the macro context, "
        "what levels matter, what to watch.\n\n"
        "Keep under 600 words. Verification-focused, not narrative. No emojis. No tool calls."
    )
    omitted = [
        "MCP Alpaca account-info ping (no MCP)",
        "daily-loop-status-{date}.json structured write (no Write tool)",
        "manager-log.jsonl append (no Write tool)",
    ]
    return body, omitted


def _system_eod_summary() -> str:
    return (
        "You are the EOD-Summary writer for Project Gamma. You are in FALLBACK MODE on MiniMax M2 "
        "because Claude was rate-limited. You CANNOT call tools; you only read inputs inlined in the "
        "prompt and emit markdown. Append-style journal section -- you do NOT rewrite the journal."
    )


def _prompt_eod_summary(date_str: str) -> tuple[str, list[str]]:
    today = date_str
    today_dt = _et_now()
    weekday = datetime.strptime(today, "%Y-%m-%d").strftime("%A")

    sections = [
        _inline_block(f"trades.csv (today only)",
                      _read_csv_today_only(REPO / "journal" / "trades.csv", today)),
        _inline_block(f"decisions.jsonl (today only, cap 150 rows)",
                      _read_jsonl_today_only(STATE_DIR / "decisions.jsonl", today, max_rows=150)),
        _inline_block("today-bias.json",
                      _read_file_safe(STATE_DIR / "today-bias.json", 15_000)),
        _inline_block("loop-state.json",
                      _read_file_safe(STATE_DIR / "loop-state.json", 15_000)),
        _inline_block(f"journal/{today}.md current content",
                      _read_file_safe(REPO / "journal" / f"{today}.md", 50_000)),
        _inline_block("hypothesis-grades.jsonl (today only)",
                      _read_jsonl_today_only(STATE_DIR / "hypothesis-grades.jsonl", today, max_rows=50)),
    ]
    body = (
        f"# EOD Reflection Section to append to journal/{today}.md\n\n"
        f"Wall-clock at write: {today_dt.strftime('%Y-%m-%dT%H:%M:%S')} ET\n\n"
        "## Inputs (inlined)\n\n" + "\n".join(sections) + "\n\n"
        "## Required output\n\n"
        "Produce a markdown SECTION (header level 2) titled `## EOD Reflection` that:\n"
        "1. Counts trades taken vs ENTER signals (taken/skipped ratio).\n"
        "2. Notes any rule breaks observed.\n"
        "3. Grades the morning bias call (matched / partial / wrong) against decisions.jsonl tape.\n"
        "4. Lists 1-3 observations about today's regime (chop / trend / news-driven).\n"
        "5. One concrete thing to verify in pre-market tomorrow.\n\n"
        "Output ONLY the new section to be appended. Do not rewrite or quote existing journal content. "
        "Under 400 words. No emojis."
    )
    omitted = [
        "Dark-pool aggregation step",
        "Auto-merge with existing journal file (output is appended verbatim by wrapper)",
        "Shadow diff scorecard step",
    ]
    return body, omitted


def _tail_text(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(data[-lines:])
    except OSError:
        return ""


# ────────────────────────────────────────────────────────────────────────────
# Output writers
# ────────────────────────────────────────────────────────────────────────────


def _write_analyst(content: str, date_str: str, *, model: str, cost_usd: float,
                    omitted: list[str], primary: bool = False) -> Path:
    target = REPO / "analysis" / "eod" / f"{date_str}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    wrapped = _format_fallback_output(content, task="analyst", date_str=date_str,
                                      cost_usd=cost_usd, model=model,
                                      omitted_features=omitted, primary=primary)
    target.write_text(wrapped, encoding="utf-8")
    return target


def _write_manager(content: str, date_str: str, *, model: str, cost_usd: float,
                    omitted: list[str], primary: bool = False) -> Path:
    target = REPO / "analysis" / "daily-brief" / f"{date_str}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    wrapped = _format_fallback_output(content, task="manager", date_str=date_str,
                                      cost_usd=cost_usd, model=model,
                                      omitted_features=omitted, primary=primary)
    target.write_text(wrapped, encoding="utf-8")

    # Also write a minimal daily-loop-status JSON so downstream consumers see a file.
    route = "free-tier-primary" if primary else "fallback-minimax"
    status = STATE_DIR / f"daily-loop-status-{date_str}.json"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(json.dumps({
        "date_et": date_str,
        "verification_route": route,
        "model": model,
        "cost_usd": cost_usd,
        "phases_verified": "see daily-brief markdown (no MCP -- tool-dependent checks skipped)",
        "omitted_features": omitted,
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")
    return target


def _write_eod_summary(content: str, date_str: str, *, model: str, cost_usd: float,
                        omitted: list[str], primary: bool = False) -> Path:
    """Append the EOD reflection section to journal/{date}.md."""
    target = REPO / "journal" / f"{date_str}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else f"# Trading Journal -- {date_str}\n\n"
    wrapped = _format_fallback_output(content, task="eod-summary", date_str=date_str,
                                      cost_usd=cost_usd, model=model,
                                      omitted_features=omitted, primary=primary)
    # Append idempotently -- replace the section if already present
    # Handles both old "(fallback)" label and new plain "## EOD Reflection" label
    for marker in ("## EOD Reflection (fallback)", "## EOD Reflection"):
        if marker in existing:
            new_content = existing.split(marker)[0].rstrip() + "\n\n" + wrapped + "\n"
            break
    else:
        new_content = existing.rstrip() + "\n\n" + wrapped + "\n"
    target.write_text(new_content, encoding="utf-8")
    return target


# ────────────────────────────────────────────────────────────────────────────
# Main dispatcher
# ────────────────────────────────────────────────────────────────────────────


TASK_HANDLERS = {
    "analyst": (_system_analyst, _prompt_analyst, _write_analyst),
    "manager": (_system_manager, _prompt_manager, _write_manager),
    "eod-summary": (_system_eod_summary, _prompt_eod_summary, _write_eod_summary),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True, choices=list(TASK_HANDLERS.keys()),
                        help="EOD task to run via free-tier model ladder")
    parser.add_argument("--date", default=None,
                        help="ET date YYYY-MM-DD (default: today)")
    parser.add_argument("--primary", action="store_true",
                        help="Called as PRIMARY path (not fallback); output tagged FREE-TIER ROUTE")
    parser.add_argument("--model", default=None,
                        help="Force a specific model slug (skips ladder; for debugging)")
    parser.add_argument("--max-tokens", type=int, default=4000,
                        help="Model response cap (default 4000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the prompt and print token estimate; don't call any model")
    args = parser.parse_args()

    date_str = args.date or _et_now().strftime("%Y-%m-%d")
    sys_fn, prompt_fn, write_fn = TASK_HANDLERS[args.task]

    system = sys_fn()
    prompt, omitted = prompt_fn(date_str)

    if args.dry_run:
        approx_tokens = (len(prompt) + len(system)) // 4
        route = "primary (free-tier)" if args.primary else "fallback (free-tier)"
        print(f"[eod-analytics] dry-run task={args.task} date={date_str} route={route}")
        print(f"[eod-analytics] approx prompt tokens: {approx_tokens:,}")
        print(f"[eod-analytics] ladder: {_MODEL_LADDER}")
        print(f"[eod-analytics] omitted features: {omitted}")
        return 0

    # If a specific model was forced (--model), use it directly.
    # Otherwise run the full free-tier ladder (Nemotron → DeepSeek → MiniMax-free → paid).
    if args.model:
        result = call_minimax(
            prompt,
            system=system,
            model=args.model,
            max_tokens=args.max_tokens,
            task_id=f"eod_analytics.{args.task}",
            timeout=240,
        )
    else:
        result = _call_with_ladder(
            system=system,
            prompt=prompt,
            max_tokens=args.max_tokens,
            task_id=f"eod_analytics.{args.task}",
            timeout=240,
        )

    cost_usd = float(result.get("cost_usd", 0.0) or 0.0)
    model_used = result.get("model", "unknown")
    tag = "primary" if args.primary else "fallback"

    if not result.get("ok"):
        err = result.get("error", "unknown")
        print(f"[eod-analytics] FAIL task={args.task} route={tag} error={err} cost=${cost_usd:.4f}",
              file=sys.stderr)
        _append_status_warn(args.task, date_str, ok=False, error=err, cost_usd=cost_usd,
                            primary=args.primary)
        return 1

    content = result.get("content", "").strip()
    if not content:
        print(f"[eod-analytics] FAIL task={args.task} route={tag} empty content model={model_used}",
              file=sys.stderr)
        _append_status_warn(args.task, date_str, ok=False, error="empty_content", cost_usd=cost_usd,
                            primary=args.primary)
        return 1

    target = write_fn(content, date_str, model=model_used, cost_usd=cost_usd,
                      omitted=omitted, primary=args.primary)
    print(f"[eod-analytics] OK task={args.task} route={tag} wrote={target} "
          f"cost=${cost_usd:.4f} model={model_used}")
    _append_status_warn(args.task, date_str, ok=True, error=None, cost_usd=cost_usd,
                        primary=args.primary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
