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
        "6. **Chef R&D queue (MACHINE-READABLE)** -- After the prose above, emit 1 to 3 lines that "
        "each begin with the literal token `COOK:` (uppercase, followed by a colon and a space). Each "
        "`COOK:` line is a SINGLE concrete, self-contained R&D / investigation task for the Chef R&D "
        "loop to act on cold (it has no memory of today). Derive them from what you observed: a knob to "
        "sweep, a hypothesis to backtest, a recurring miss to investigate, the 'fix tomorrow' item "
        "rephrased as an actionable research task. Write the FULL task on ONE physical line (no internal "
        "newlines), 15-40 words, naming the relevant file/pattern/level where you can. Example:\n"
        "COOK: Backtest whether requiring a 2nd confirming trigger before BULLISH_RECLAIM_RIDE_THE_RIBBON "
        "entries improves real-fills expectancy vs single-trigger entries; use the level-family harness.\n"
        "If you genuinely have nothing worth cooking, emit exactly one line `COOK: none`.\n\n"
        "Keep the prose sections under 800 words. Use bullet points liberally. No emojis. No tool calls. "
        "Do NOT propose strategy changes in prose -- observation only; the `COOK:` lines are the ONLY "
        "place you queue forward work."
    )
    # Chef routing is now WIRED on the free-tier path via a deterministic Python
    # append to cook-queue.jsonl (see _route_analyst_cook_tasks). The remaining
    # items below still require a Write tool and stay skipped on this path.
    omitted = [
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
# Analyst -> Chef R&D routing (deterministic Python append; no Write tool)
#
# THE BUG THIS FIXES: on the free-tier ladder the analyst has no Write tool, so
# _chef-inbox routing was hard-skipped -- reflection never reached R&D. Even the
# Claude path wrote to _chef-inbox/ which kitchen_daemon.py never reads (it only
# polls cook-queue.jsonl). Here we parse the digest the model just produced and
# append proper `create` rows to cook-queue.jsonl -- the SAME format + file the
# daemon consumes via kitchen_daemon._load_queue(). Plain file append: works on
# every path, no model tool-calling required.
# ────────────────────────────────────────────────────────────────────────────


COOK_QUEUE_FILE = STATE_DIR / "cook-queue.jsonl"
_MAX_COOK_TASKS_PER_RUN = 3          # cap: never flood the queue from one digest
_MIN_COOK_TASK_CHARS = 25            # below this a "task" is too thin to be useful
_MAX_COOK_TASK_CHARS = 600          # clamp pathological model output


def _sanitize_task_text(text: str) -> str:
    """Collapse whitespace and strip to a clean single-line, JSONL/daemon-safe string.

    The daemon's _load_queue() reads cook-queue.jsonl as strict UTF-8 with NO
    errors= fallback, so a single stray cp1252 byte (e.g. a Word em-dash 0x97)
    aborts the whole read. We normalise smart punctuation to ASCII and drop any
    remaining non-printable/non-ASCII bytes so a row we write can never be the
    thing that bricks the consumer.
    """
    if not text:
        return ""
    # Normalise the common cp1252 / unicode punctuation the free-tier models emit.
    replacements = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "--", "−": "-", "…": "...",
        " ": " ", "→": "->", "•": "-", "·": "-",
        "‑": "-", "‒": "-", "―": "--",  # nbhyphen / figure-dash / horizontal-bar
        "\x97": "--", "\x96": "-", "\x91": "'", "\x92": "'",
        "\x93": '"', "\x94": '"', "\x85": "...",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Strip markdown emphasis markers that add noise to a task description.
    text = text.replace("**", "").replace("`", "")
    # Collapse all whitespace (including newlines) to single spaces.
    text = " ".join(text.split())
    # Drop any remaining non-ASCII byte so the row is pure-ASCII UTF-8.
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.strip()


def _slugify_task(text: str, max_len: int = 60) -> str:
    """Stable slug from task text: lowercase alnum, hyphen-separated, length-capped.

    Deterministic for a given input so re-running the same digest yields the same
    task_id (-> dedupe works across runs)."""
    out_chars = []
    prev_hyphen = False
    for ch in text.lower():
        if ch.isalnum():
            out_chars.append(ch)
            prev_hyphen = False
        elif not prev_hyphen:
            out_chars.append("-")
            prev_hyphen = True
    slug = "".join(out_chars).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "analyst-cook"


def _extract_cook_tasks(digest: str) -> tuple[list[str], str]:
    """Parse the analyst digest for forward R&D tasks.

    Returns (tasks, source_label). Primary source: explicit `COOK:` marker lines
    (machine-readable, requested by the prompt). Fallback: the prose
    "One thing to fix tomorrow" section, turned into a single task -- this keeps
    routing alive even if a model ignores the COOK: instruction.
    """
    if not digest:
        return [], "empty_digest"

    # ── Primary: COOK: marker lines ──────────────────────────────────────────
    cook_tasks: list[str] = []
    for raw_line in digest.splitlines():
        line = raw_line.strip()
        # Tolerate leading markdown bullets / emphasis: "- **COOK:** ...", "* COOK: ..."
        probe = line.lstrip("-*> ").lstrip()
        if probe.upper().startswith("COOK:"):
            payload = probe[len("COOK:"):].strip()
            payload = _sanitize_task_text(payload)
            if payload and payload.lower() != "none":
                cook_tasks.append(payload)
    if cook_tasks:
        return cook_tasks, "cook_marker"

    # ── Fallback: "One thing to fix tomorrow" prose section ──────────────────
    # Find a header line that contains the phrase, then take the following
    # non-empty prose up to the next header / horizontal rule.
    lines = digest.splitlines()
    fix_idx = None
    for i, line in enumerate(lines):
        norm = line.lower()
        if line.lstrip().startswith("#") and "fix tomorrow" in norm:
            fix_idx = i
            break
        # also tolerate a bold inline header like "**One thing to fix tomorrow**"
        if "fix tomorrow" in norm and ("**" in line or line.strip().endswith(":")):
            fix_idx = i
            break
    if fix_idx is not None:
        collected: list[str] = []
        for line in lines[fix_idx + 1:]:
            s = line.strip()
            if not s:
                if collected:
                    break          # blank line ends the section once we have text
                continue
            if s.startswith("#") or set(s) <= {"-", "*", "_"} and len(s) >= 3:
                break              # next header or horizontal rule
            collected.append(s)
        prose = _sanitize_task_text(" ".join(collected))
        # Strip a leading "**One thing...**" echo if the model repeated the header.
        if prose:
            task = f"Analyst EOD fix-it: {prose}"
            return [task], "fix_tomorrow_section"

    return [], "no_recommendation_found"


def _repair_queue_encoding_if_needed() -> Optional[str]:
    """Idempotently repair a non-UTF-8 byte in cook-queue.jsonl, in place.

    The daemon's _load_queue() reads the queue as strict UTF-8 (no errors=), so a
    single stray cp1252 byte anywhere in the file aborts the read and the daemon
    never reaches rows appended at EOF -- which would silently defeat this whole
    fix. We only touch the file when a decode actually fails, re-decoding the
    bytes with a cp1252 fallback (lossless for the real content) and re-writing
    pure UTF-8. Returns a short note if a repair happened, else None.

    This is data hygiene on a JSONL state file (a plain append target), not a
    change to the read-only daemon code.
    """
    try:
        raw = COOK_QUEUE_FILE.read_bytes()
    except OSError:
        return None
    try:
        raw.decode("utf-8")
        return None  # already clean -- no-op
    except UnicodeDecodeError as exc:
        bad_pos = exc.start
    # Re-decode tolerantly: utf-8 where valid, cp1252 for stray legacy bytes.
    try:
        text = raw.decode("utf-8", errors="replace")
        # Replace U+FFFD (the replacement char) back to ASCII '--' so we don't
        # leave non-ASCII in the file; cp1252 0x97/0x96 were almost always dashes.
        text = text.replace("�", "--")
        backup = COOK_QUEUE_FILE.with_suffix(".jsonl.precp1252.bak")
        try:
            if not backup.exists():
                backup.write_bytes(raw)
        except OSError:
            pass
        tmp = COOK_QUEUE_FILE.with_suffix(".jsonl.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(COOK_QUEUE_FILE)
        return f"repaired non-utf8 byte at pos {bad_pos} (backup .precp1252.bak)"
    except OSError as exc:
        return f"WARN repair failed: {exc}"


def _load_existing_task_ids() -> set[str]:
    """Read all `create` task_ids already in the queue (defensive read for dedupe)."""
    ids: set[str] = set()
    if not COOK_QUEUE_FILE.exists():
        return ids
    try:
        # errors="replace": never crash on a legacy byte while reading for dedupe.
        with open(COOK_QUEUE_FILE, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict) and ev.get("event") == "create":
                    tid = ev.get("task_id")
                    if tid:
                        ids.add(str(tid))
    except OSError as exc:
        print(f"[eod-analytics] WARN dedupe read failed: {exc}", file=sys.stderr)
    return ids


def _route_analyst_cook_tasks(digest: str, date_str: str) -> dict:
    """Parse the analyst digest and append deduped R&D tasks to cook-queue.jsonl.

    Returns a summary dict: {parsed, source, appended:[task_id...], skipped_dupe, note}.
    Never raises -- routing failure must not fail the analyst run.
    """
    summary = {
        "parsed": 0,
        "source": None,
        "appended": [],
        "skipped_dupe": 0,
        "note": "",
    }
    try:
        tasks, source = _extract_cook_tasks(digest)
        summary["source"] = source
        # Filter to substantive tasks and clamp length.
        clean: list[str] = []
        for t in tasks:
            t = _sanitize_task_text(t)
            if len(t) < _MIN_COOK_TASK_CHARS:
                continue
            if len(t) > _MAX_COOK_TASK_CHARS:
                t = t[:_MAX_COOK_TASK_CHARS].rstrip()
            clean.append(t)
        # De-dupe within this run (by slug) and cap.
        seen_slugs: set[str] = set()
        deduped: list[str] = []
        for t in clean:
            slug = _slugify_task(t)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            deduped.append(t)
        deduped = deduped[:_MAX_COOK_TASKS_PER_RUN]
        summary["parsed"] = len(deduped)

        if not deduped:
            summary["note"] = (
                f"no cook tasks extracted (source={source}); appended nothing. "
                "Digest had no COOK: lines and no parseable fix-it section."
            )
            print(f"[eod-analytics] analyst-cook-routing: {summary['note']}",
                  file=sys.stderr)
            return summary

        # Repair the queue's encoding first so the daemon can actually read what
        # we append (a stray cp1252 byte aborts its strict-UTF-8 read at EOF).
        repair_note = _repair_queue_encoding_if_needed()
        if repair_note:
            print(f"[eod-analytics] analyst-cook-routing: {repair_note}", file=sys.stderr)

        existing_ids = _load_existing_task_ids()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows_to_write: list[str] = []
        for t in deduped:
            task_id = f"{_slugify_task(t)}-{date_str}"
            if task_id in existing_ids:
                summary["skipped_dupe"] += 1
                continue
            existing_ids.add(task_id)  # guard against intra-run id collisions too
            row = {
                "event": "create",
                "task_id": task_id,
                "task": t,
                "priority": "medium",
                "source": "analyst-eod-auto",
                "ts": ts,
            }
            rows_to_write.append(json.dumps(row, separators=(",", ":")))
            summary["appended"].append(task_id)

        if rows_to_write:
            try:
                COOK_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(COOK_QUEUE_FILE, "a", encoding="utf-8") as f:
                    f.write("\n".join(rows_to_write) + "\n")
            except OSError as exc:
                summary["note"] = f"WARN append failed: {exc}"
                print(f"[eod-analytics] analyst-cook-routing: {summary['note']}",
                      file=sys.stderr)
                return summary

        summary["note"] = (
            f"routed {len(summary['appended'])} cook task(s) (source={source}, "
            f"{summary['skipped_dupe']} dupe-skipped)"
        )
        print(f"[eod-analytics] analyst-cook-routing: {summary['note']} "
              f"ids={summary['appended']}")
    except Exception as exc:  # noqa: BLE001 -- routing must never fail the run
        summary["note"] = f"WARN routing exception: {type(exc).__name__}: {exc}"
        print(f"[eod-analytics] analyst-cook-routing: {summary['note']}", file=sys.stderr)
    return summary


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

    # Analyst -> Chef R&D routing: parse the digest we just wrote and append
    # deduped tasks to cook-queue.jsonl so reflection actually reaches the
    # Kitchen R&D loop (works on the free-tier path -- plain file append, no
    # Write tool / model tool-calling needed).
    if args.task == "analyst":
        _route_analyst_cook_tasks(content, date_str)

    _append_status_warn(args.task, date_str, ok=True, error=None, cost_usd=cost_usd,
                        primary=args.primary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
