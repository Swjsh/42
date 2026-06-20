"""Chef R&D via NVIDIA Nemotron 3 Super (free tier on OpenRouter).

CLOSES THE LOOP J FLAGGED 2026-05-20: a single Claude Code interactive cooking
session burned ~$430 in metered token value (4.5M output, 597M cache reads on
Sonnet effort=max), which then drained the shared rate-limit pool and knocked
out heartbeat + EOD pipeline. This script runs the same R&D work on Nemotron
3 Super 120B-MoE / 12B-active for $0.

Nemotron 3 Super characteristics (free tier verified 2026-05-20):
  * 1M token context (vs ~200K on Sonnet via stream-json)
  * Reasoning-tuned (chain-of-thought)
  * Agentic-capable
  * Rate-limited (not $-capped)

Falls back to MiniMax M2.5 paid tier ($0.003/call) if Nemotron 429s.
Per CLAUDE.md OP-25 engine-benefit autonomy + OP-3 cost discipline + OP-22
"don't stop cooking" / "build chef around free models" (J directive 2026-05-21).

USAGE
  python chef_nemotron.py --task "rank top-5 sniper variants by edge_capture"
  python chef_nemotron.py --auto                       # auto-pick from _chef-inbox/
  python chef_nemotron.py --brainstorm                 # propose 3 candidates from lessons + recent trades
  python chef_nemotron.py --rank                       # re-rank existing leaderboard
  python chef_nemotron.py --task "..." --dry-run       # build prompt + show token estimate; no API call

OUTPUT
  Writes a DRAFT candidate spec to strategy/candidates/{YYYY-MM-DD}-{slug}.md
    or a ranking/analysis doc to strategy/candidates/_analysis/{YYYY-MM-DD}-{slug}.md
  Appends a JSONL row to strategy/candidates/_chef-log.jsonl
  Emits a one-line summary to stdout

NEVER touches:
  * automation/prompts/heartbeat*.md      (Rule 9)
  * automation/state/params*.json         (Rule 9)
  * Live order placement                  (No MCP available anyway)
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
CANDIDATES_DIR = REPO / "strategy" / "candidates"
ANALYSIS_DIR = CANDIDATES_DIR / "_analysis"
CHEF_INBOX = CANDIDATES_DIR / "_chef-inbox"
CHEF_LOG = CANDIDATES_DIR / "_chef-log.jsonl"
STATE_DIR = REPO / "automation" / "state"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from run_minimax import call_minimax  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Tier preference: try Nemotron first (free + 1M ctx + reasoning), fallback to MiniMax
# free, last-resort paid MiniMax M2.5. Any 429 on a free tier triggers next-tier fallback.
PRIMARY_FREE = "nvidia/nemotron-3-super-120b-a12b:free"
FALLBACK_FREE_1 = "deepseek/deepseek-v4-flash:free"
FALLBACK_FREE_2 = "minimax/minimax-m2.5:free"
LAST_RESORT_PAID = "minimax/minimax-m2.5"  # ~$0.003/call

MODEL_LADDER = [PRIMARY_FREE, FALLBACK_FREE_1, FALLBACK_FREE_2, LAST_RESORT_PAID]


# DST-aware ET helper (no tzdata dep)
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
    sys.stdout = open(_log_dir / f"chef-nemotron-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"chef-nemotron-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# Input gathering helpers
# ────────────────────────────────────────────────────────────────────────────


MAX_INLINE_BYTES = 80_000  # Nemotron has 1M ctx so we can afford bigger inlines


def _read_file_safe(path: Path, max_bytes: int = MAX_INLINE_BYTES) -> str:
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[... truncated {len(data) - max_bytes:,} bytes ...]"
        return data
    except OSError as exc:
        return f"[read error: {exc}]"


def _block(label: str, content: str) -> str:
    if not content:
        return f"### {label}\n(empty / not present)\n"
    return f"### {label}\n```\n{content}\n```\n"


def _slugify(s: str) -> str:
    out = []
    for c in s.lower():
        if c.isalnum():
            out.append(c)
        elif c in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:60] or "untitled"


# ────────────────────────────────────────────────────────────────────────────
# System prompt: condensed Chef persona (from .claude/agents/chef.md)
# ────────────────────────────────────────────────────────────────────────────


CHEF_SYSTEM_PROMPT = """You are Chef -- the strategy R&D scientist for Project Gamma 0DTE SPY trading.

You are running on a FREE reasoning model. Your job is to analyze inputs and propose
strategy candidates as DRAFT markdown specs.

CRITICAL OUTPUT RULES (no exceptions):
- Output ONLY markdown candidate/analysis blocks. NO preamble. NO explanation outside
  the markdown. NO "Let me think..." or "We are to..." or "I will produce..." prose.
- If the task implies multiple deliverables, output each as its own block, separated
  by exactly `---` on its own line.
- Each block starts with `# CANDIDATE: <NAME>` or `# ANALYSIS: <NAME>`. Nothing before
  that heading -- not even a blank line of reasoning.
- Internal reasoning STAYS internal. Do not narrate your decision-making process in
  the output.
- Be DECISIVE. If you face ambiguity, pick the most useful interpretation and ship.

HARD GUARDRAILS (you cannot violate these):
1. NEVER propose changes to automation/prompts/heartbeat*.md (Rule 9 -- doctrine).
2. NEVER propose changes to automation/state/params*.json (Rule 9).
3. NEVER suggest placing live orders. You only PROPOSE candidates as DRAFT.
4. EVERY candidate proposal MUST include OP-20 disclosures (see template below).

OP-16 GOAL FUNCTION (the scoring metric):
  edge_capture = sum(engine_pnl_on_J_winners) - sum(max(0, engine_loss_on_J_losers))
  final_score = edge_capture * aggregate_sharpe
  REJECT if edge_capture < 771 (50% of max_possible 1542).

J's source-of-truth trade days (immutable):
  WINNERS (engine MUST take):
    4/29 SPY 710P x 6 -> +$342
    5/01 SPY 721P x 20 -> +$470
    5/04 SPY 721P x 10 -> +$730
  LOSERS (engine MUST skip or lose less):
    5/05 SPY 722P x 20 -> -$260
    5/06 SPY 730P x 10 -> -$300
    5/07 SPY 734C x 3 -> -$45
    5/07 SPY 737C x 10 -> -$120

OP-20 DISCLOSURES (every proposal must include):
  1. Account-size assumption (qty=28 requires $25K+; $1K paper ~= 14% headline)
  2. Sample-bias disclosure (sample size, selection method, overfit risk)
  3. Out-of-sample test result (walk-forward held-out window, or NEEDS-OOS if not done)
  4. Real-fills check on top 3 J days (NEEDS-REAL-FILLS if not done)
  5. Failure-mode enumeration (worst day, max drawdown, blow-up scenario)
  6. Concentration disclosure (if top-5 days = X% of P&L, state X)

CANDIDATE TEMPLATE (output exactly this markdown structure):

```
# CANDIDATE: <name>

**Filed:** <today's date>
**Filer:** chef-nemotron (free-tier autonomous R&D)
**Type:** <new_trigger | filter_change | exit_change | quality_gate | watcher_proposal>
**Status:** DRAFT (NEEDS-RATIFICATION per Rule 9)

## Hypothesis

<2-3 sentences: what edge are we trying to capture, why does it exist>

## Mechanism

<concrete: what bars / indicators / state triggers entry, what's the exit logic>

## Expected impact on OP-16 anchors

| J day | Current engine behavior | Proposed behavior | Delta |
|---|---|---|---|
| 4/29 winner | <if known> | <prediction> | <est> |
| 5/01 winner | ... | ... | ... |
| 5/04 winner | ... | ... | ... |
| 5/05 loser | ... | ... | ... |
| 5/06 loser | ... | ... | ... |
| 5/07 loser 1 | ... | ... | ... |
| 5/07 loser 2 | ... | ... | ... |

(If you don't have data, write `unknown -- requires Stage-1 backtest` and explain.)

## OP-20 disclosures

1. **Account-size assumption:** ...
2. **Sample bias:** ...
3. **Out-of-sample:** NEEDS-OOS (or paste result)
4. **Real-fills:** NEEDS-REAL-FILLS (or paste result)
5. **Failure modes:** ...
6. **Concentration:** ...

## Pre-merge gate

<what tests need to pass: gym validators, walk-forward, real-fills>

## Confidence

X / 10 -- <brief reasoning>

## Pre-existing leaderboard impact

<does this conflict with / complement candidates 1-9 in _LEADERBOARD.md?>
```

Be RIGOROUS about OP-16 anchors. If you don't know, SAY "unknown -- requires Stage-1 backtest"
instead of fabricating numbers. Quality > volume. One good candidate beats five bad ones.

OUTPUT FORMAT: respond with ONLY the markdown candidate (or analysis), no preamble, no
explanation outside the markdown. No code fences around the whole response. Begin directly
with `# CANDIDATE:` or `# ANALYSIS:`.
"""


# ────────────────────────────────────────────────────────────────────────────
# Task builders
# ────────────────────────────────────────────────────────────────────────────


def _gather_common_inputs() -> str:
    """The standard input set every chef task needs."""
    sections = [
        _block("strategy/candidates/_LEADERBOARD.md",
               _read_file_safe(CANDIDATES_DIR / "_LEADERBOARD.md", 50_000)),
        _block("markdown/doctrine/LESSONS-LEARNED.md (head 30K bytes)",
               _read_file_safe(REPO / "markdown" / "doctrine" / "LESSONS-LEARNED.md", 30_000)),
        _block("markdown/0dte/playbook.md",
               _read_file_safe(REPO / "markdown" / "0dte" / "playbook.md", 25_000)),
        _block("markdown/0dte/risk-rules.md",
               _read_file_safe(REPO / "markdown" / "0dte" / "risk-rules.md", 15_000)),
        _block("CLAUDE.md OP-16 (J edge) -- excerpt",
               _read_excerpt(REPO / "CLAUDE.md",
                             start_marker="16. **J's edge is the source",
                             max_lines=30)),
    ]
    return "\n".join(sections)


def _read_excerpt(path: Path, start_marker: str, max_lines: int) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if start_marker in line:
                return "\n".join(lines[i:i + max_lines])
        return ""
    except OSError:
        return ""


def _build_task_prompt(task_desc: str) -> tuple[str, str]:
    """Free-form task. Returns (prompt, suggested_slug)."""
    common = _gather_common_inputs()
    prompt = (
        f"# Task\n\n{task_desc}\n\n"
        "## Inputs (inlined)\n\n"
        f"{common}\n\n"
        "## Your output\n\n"
        "Produce one DRAFT candidate (or ranked analysis if the task is comparative) "
        "per the CANDIDATE TEMPLATE in the system prompt. Be concrete. Be honest about "
        "unknowns. No filler."
    )
    return prompt, _slugify(task_desc)[:50]


def _build_auto_prompt() -> tuple[str, str]:
    """Auto-pick the oldest item from _chef-inbox/."""
    if not CHEF_INBOX.exists():
        return _build_brainstorm_prompt()
    items = sorted([p for p in CHEF_INBOX.glob("*.md")
                    if p.name not in ("README.md",) and ".STALE." not in p.name],
                   key=lambda p: p.stat().st_mtime)
    if not items:
        return _build_brainstorm_prompt()
    top = items[0]
    inbox_content = _read_file_safe(top, 80_000)
    common = _gather_common_inputs()
    prompt = (
        f"# Auto-pick from _chef-inbox/\n\n"
        f"## Inbox item: {top.name}\n\n```\n{inbox_content}\n```\n\n"
        "## Inputs (inlined)\n\n"
        f"{common}\n\n"
        "## Your output\n\n"
        "Convert the inbox item into a DRAFT candidate spec per the CANDIDATE TEMPLATE. "
        "Address everything the inbox item raised. If the item is an analysis (not a "
        "proposal), produce a candidate that operationalizes the analysis's findings."
    )
    return prompt, _slugify(top.stem)[:50]


def _build_brainstorm_prompt() -> tuple[str, str]:
    common = _gather_common_inputs()
    prompt = (
        "# Brainstorm 3 strategy candidates\n\n"
        "Mine the lessons-learned + playbook + recent leaderboard for 3 fresh candidate "
        "ideas that pass the OP-16 edge_capture floor. Diversify across: new trigger "
        "primitive / filter refinement / exit-logic change. Output 3 separate candidate "
        "specs back-to-back, each per the CANDIDATE TEMPLATE, separated by `---`.\n\n"
        "## Inputs (inlined)\n\n" + common
    )
    return prompt, "brainstorm-3"


def _build_rank_prompt() -> tuple[str, str]:
    common = _gather_common_inputs()
    prompt = (
        "# Re-rank the leaderboard\n\n"
        "Review every candidate listed in `_LEADERBOARD.md`. Score each on:\n"
        "  1. OP-16 edge_capture (current best estimate)\n"
        "  2. Implementation complexity (1=trivial, 5=hard)\n"
        "  3. Failure-mode severity (1=local, 5=catastrophic)\n"
        "  4. OOS / real-fills readiness\n"
        "  5. Confidence level\n\n"
        "Produce a single markdown ANALYSIS doc with:\n"
        "  * Updated ranked table (highest priority first)\n"
        "  * Top-2 candidate recommendations for next ratification window\n"
        "  * Any candidate that should be DROPPED (stale, failed, dominated)\n"
        "Output format: begin with `# ANALYSIS: Leaderboard re-rank YYYY-MM-DD`.\n\n"
        "## Inputs (inlined)\n\n" + common
    )
    return prompt, "leaderboard-rerank"


# ────────────────────────────────────────────────────────────────────────────
# Model-ladder caller
# ────────────────────────────────────────────────────────────────────────────


def _call_with_ladder(prompt: str, max_tokens: int = 6000, task_id: str = "chef.adhoc") -> dict:
    """Try Nemotron -> Deepseek-free -> MiniMax-free -> MiniMax-paid until one succeeds.
    Returns the run_minimax result dict plus a 'ladder_used' key."""
    last_result = None
    for tier_idx, model in enumerate(MODEL_LADDER):
        print(f"[chef-nemotron] attempt tier={tier_idx} model={model}", file=sys.stderr)
        result = call_minimax(
            prompt,
            system=CHEF_SYSTEM_PROMPT,
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
            timeout=300,
            task_id=f"{task_id}.tier{tier_idx}",
        )
        result["ladder_used"] = tier_idx
        result["model_attempted"] = model
        if result.get("ok") and (result.get("content") or "").strip():
            return result
        last_result = result
        err = result.get("error", "unknown")
        # Don't burn the ladder on auth errors -- those won't be fixed by switching model
        if "auth-failed" in str(err) or "openrouter key" in str(err).lower():
            break
        print(f"[chef-nemotron] tier {tier_idx} failed: {err}", file=sys.stderr)
    return last_result or {"ok": False, "error": "all_tiers_failed", "ladder_used": -1}


# ────────────────────────────────────────────────────────────────────────────
# Output writers
# ────────────────────────────────────────────────────────────────────────────


_BLOCK_HEADING_RE = None  # initialized lazily

def _extract_blocks(content: str) -> list[tuple[str, str]]:
    """Split a model response into discrete (kind, body) blocks where kind is
    'CANDIDATE' or 'ANALYSIS'. Reasoning preamble/interlude text is discarded.

    Each block starts at a `# CANDIDATE: ...` or `# ANALYSIS: ...` heading
    (optionally inside a code fence) and ends at the next such heading or EOF.
    Trailing code fences are stripped.
    """
    import re
    global _BLOCK_HEADING_RE
    if _BLOCK_HEADING_RE is None:
        _BLOCK_HEADING_RE = re.compile(r"^\s*#\s+(CANDIDATE|ANALYSIS)\s*:\s*(.+?)\s*$", re.MULTILINE)

    matches = list(_BLOCK_HEADING_RE.finditer(content))
    if not matches:
        return []

    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].rstrip()
        # Strip trailing code-fence wrapper if present
        if body.endswith("```"):
            body = body.rsplit("```", 1)[0].rstrip()
        kind = m.group(1).upper()
        blocks.append((kind, body))
    return blocks


def _slugify_from_heading(heading_line: str, fallback: str) -> str:
    """Extract a slug from a `# CANDIDATE: NAME` line."""
    import re
    m = re.match(r"^\s*#\s+(?:CANDIDATE|ANALYSIS)\s*:\s*(.+?)\s*$", heading_line)
    if not m:
        return fallback
    return _slugify(m.group(1))[:60] or fallback


def _write_candidate(content: str, slug: str, *, model: str, cost_usd: float, ladder_used: int) -> Path:
    """Write the model output. If the response contains multiple
    `# CANDIDATE:` / `# ANALYSIS:` blocks, write each to its own file and return
    the primary one (first block). Reasoning noise outside these blocks is
    discarded.
    """
    today = _et_now().strftime("%Y-%m-%d")
    blocks = _extract_blocks(content)

    header_template = (
        "<!-- CHEF-NEMOTRON: this DRAFT was generated by {model} (free tier) at $-cost {cost_usd:.4f}. -->\n"
        "<!-- Model-ladder tier used: {ladder} (0=Nemotron, 1=DeepSeek-free, 2=MiniMax-free, 3=MiniMax-paid). -->\n"
        "<!-- Per CLAUDE.md OP-22 + OP-25 + OP-30 (effort/concurrency discipline). -->\n"
        "<!-- NOT YET RATIFIED -- J review required per Rule 9 before any production change. -->\n\n"
    )

    # No structured blocks detected -- fall back to writing the raw content under a
    # single chef-nemo-{slug}.md file so it isn't lost.
    if not blocks:
        target = CANDIDATES_DIR / f"{today}-chef-nemo-{slug}.md"
        target.write_text(
            header_template.format(model=model, cost_usd=cost_usd, ladder=ladder_used) + content,
            encoding="utf-8",
        )
        return target

    primary_path: Optional[Path] = None
    written: list[Path] = []
    for idx, (kind, body) in enumerate(blocks):
        heading_line = body.split("\n", 1)[0] if body else ""
        block_slug = _slugify_from_heading(heading_line, fallback=f"{slug}-block{idx + 1}")
        if kind == "ANALYSIS":
            target_dir = ANALYSIS_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{today}-{block_slug}.md"
        else:
            target = CANDIDATES_DIR / f"{today}-chef-nemo-{block_slug}.md"
        target.write_text(
            header_template.format(model=model, cost_usd=cost_usd, ladder=ladder_used) + body + "\n",
            encoding="utf-8",
        )
        written.append(target)
        if primary_path is None:
            primary_path = target
    print(f"[chef-nemotron] wrote {len(written)} block(s): {[str(p.relative_to(REPO)) for p in written]}")
    return primary_path  # type: ignore[return-value]


def _append_log(entry: dict) -> None:
    try:
        CHEF_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHEF_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"[chef-nemotron] WARN log write failed: {exc}", file=sys.stderr)


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--task", help="Free-form task description")
    g.add_argument("--auto", action="store_true", help="Auto-pick from _chef-inbox/")
    g.add_argument("--brainstorm", action="store_true", help="Propose 3 fresh candidates")
    g.add_argument("--rank", action="store_true", help="Re-rank leaderboard")
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--model", help="Override the primary model (default ladder: Nemotron->DeepSeek->MiniMax-free->MiniMax-paid)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.task:
        prompt, slug = _build_task_prompt(args.task)
        task_id_base = "chef.task"
    elif args.auto:
        prompt, slug = _build_auto_prompt()
        task_id_base = "chef.auto"
    elif args.brainstorm:
        prompt, slug = _build_brainstorm_prompt()
        task_id_base = "chef.brainstorm"
    elif args.rank:
        prompt, slug = _build_rank_prompt()
        task_id_base = "chef.rank"
    else:
        parser.error("must pick a mode")
        return 2

    if args.dry_run:
        approx = (len(prompt) + len(CHEF_SYSTEM_PROMPT)) // 4
        print(f"[chef-nemotron] dry-run slug={slug} approx_input_tokens={approx:,}")
        print(prompt[:2000] + ("..." if len(prompt) > 2000 else ""))
        return 0

    # Single-model mode if user overrode
    if args.model:
        global MODEL_LADDER
        MODEL_LADDER = [args.model]

    result = _call_with_ladder(prompt, max_tokens=args.max_tokens, task_id=task_id_base)
    cost = float(result.get("cost_usd", 0.0) or 0.0)
    model_used = result.get("model", result.get("model_attempted", "unknown"))
    ladder = int(result.get("ladder_used", -1))

    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "task" if args.task else ("auto" if args.auto else ("brainstorm" if args.brainstorm else "rank")),
        "slug": slug,
        "model_used": model_used,
        "ladder_used": ladder,
        "cost_usd": cost,
        "ok": result.get("ok", False),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "elapsed_s": result.get("elapsed_s", 0.0),
    }

    if not result.get("ok"):
        err = result.get("error", "unknown")
        print(f"[chef-nemotron] FAIL slug={slug} error={err}", file=sys.stderr)
        log_entry["error"] = err
        _append_log(log_entry)
        return 1

    content = (result.get("content") or "").strip()
    if not content:
        print(f"[chef-nemotron] FAIL slug={slug} empty content", file=sys.stderr)
        log_entry["error"] = "empty_content"
        _append_log(log_entry)
        return 1

    # Strip leading/trailing code fences if model wrapped output
    if content.startswith("```"):
        first_nl = content.find("\n")
        if first_nl > 0:
            content = content[first_nl + 1:]
        if content.rstrip().endswith("```"):
            content = content.rsplit("```", 1)[0].rstrip()

    target = _write_candidate(content, slug, model=model_used, cost_usd=cost, ladder_used=ladder)
    log_entry["output_path"] = str(target.relative_to(REPO))
    _append_log(log_entry)

    print(f"[chef-nemotron] OK slug={slug} wrote={target.relative_to(REPO)} cost=${cost:.4f} model={model_used} tier={ladder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
