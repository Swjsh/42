"""Free-tier swarm consultation for Gamma-side decisions.

Born 2026-05-23 after J's directive: *"can we turn our free swarm engines into
something gamma uses to pick the best foot forward? brainstorm this."*

The premise: single-model decisions create single failure modes. OP-32 was a
single-perspective Sonnet decision that locked J out Friday. If the same
proposal had been audited by Nemotron + DeepSeek + MiniMax with "what's the
worst this could do to J?" the "no door for J" failure mode would have surfaced
immediately. Multi-model swarm with cheap free tier = adversarial review for $0.

This is a Gamma-SIDE reasoning primitive — NOT a trading primitive. The swarm
audits/critiques/brainstorms decisions ABOUT the engine, not trade entries.
Live orders still go through Pilot per Rule 9.

MODES
  audit       — adversarial pre-ship review of a proposed change
  brainstorm  — generate N independent ideas, synthesize ranked list
  critique    — find the holes in existing work / candidate
  rank        — pick the best of N options + reasoning
  decide      — recommend one action with reasoning

USAGE
  python swarm_consult.py audit --question "..." [--context "..." | --context-file PATH]
  python swarm_consult.py brainstorm --question "..." --n 3
  python swarm_consult.py decide --question "..."

DEFAULT MODELS (parallel fan-out, $0 each)
  nvidia/nemotron-3-super-120b-a12b:free   (primary reasoner, 1M ctx)
  deepseek/deepseek-v4-flash:free          (coding-focused, 1M ctx)
  minimax/minimax-m2.5:free                (general, 204K ctx)
Synthesizer: Nemotron.

OUTPUT
  analysis/swarm-consult/{YYYY-MM-DD}-{HHMMSS}-{slug}.md  — human-readable report
  analysis/swarm-consult/{YYYY-MM-DD}-{HHMMSS}-{slug}.json — machine-readable
  analysis/swarm-consult/_log.jsonl  — append-only telemetry

NEVER touches:
  * automation/prompts/heartbeat*.md      (Rule 9)
  * automation/state/params*.json         (Rule 9)
  * Live order placement                  (no MCP)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "swarm-consult"
LOG_FILE = OUT_DIR / "_log.jsonl"
STATE_DIR = REPO / "automation" / "state"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from run_minimax import call_minimax  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# Default fan-out: 3 independent free-tier perspectives.
DEFAULT_PERSPECTIVE_MODELS: tuple[str, ...] = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "deepseek/deepseek-v4-flash:free",
    "minimax/minimax-m2.5:free",
)
DEFAULT_SYNTHESIZER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# Generous timeouts — free tier can be slow under load. Total worst case per call ~5min.
PERSPECTIVE_TIMEOUT_S = 240
SYNTHESIS_TIMEOUT_S = 300


# ────────────────────────────────────────────────────────────────────────────
# DST-aware ET helper (no tzdata dep — same pattern as chef_nemotron)
# ────────────────────────────────────────────────────────────────────────────


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


# Headless launch redirect — never let pythonw spawn a visible window
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"swarm-consult-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"swarm-consult-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# System prompts (one per mode)
# ────────────────────────────────────────────────────────────────────────────


_SHARED_PREAMBLE = """You are a free-tier reasoning model consulted by Project Gamma -- an autonomous 0DTE SPY options trading system. You are NOT placing trades. You are NOT modifying live doctrine. You are providing an INDEPENDENT perspective on a proposed change or question, which will be synthesized with perspectives from other models.

Project Gamma's core principles (so you can spot violations):
  * Rule 9: NO mid-session rule changes. heartbeat.md / params*.json are frozen unless J ratifies on weekends.
  * Rule 10: If anything violates rules, the trade does not happen.
  * Self-healing > delayed J-flag. Do not disturb the user (no popup windows, no Claude lockouts during market hours, no Discord pings unless asked).
  * J's edge = source of truth. Anchor days: winners 4/29 + 5/01 + 5/04, losers 5/05 + 5/06 + 5/07.
  * Cost discipline: free-tier first. Anthropic Claude reserved for live trading (Haiku heartbeat) and unique tool-use cases.

Be DIRECT, SPECIFIC, RIGOROUS. No filler. No "as an AI". No restating the question. Get to the substance.
"""


_MODE_INSTRUCTIONS = {
    "audit": """MODE: AUDIT (adversarial pre-ship review)

Your job: identify everything that could go WRONG with the proposed change. Be the harshest reviewer who would have caught the OP-32 lockout BEFORE it shipped.

Produce these sections in order:
1. **Most likely failure mode** (one concrete, specific scenario — what breaks, in what order, who notices)
2. **Worst-case impact on J's environment** (window popups? lockouts? mid-day pings? game interruption?)
3. **Worst-case impact on Pilot/Heartbeat** (trade missed? wrong direction? overfit?)
4. **Rule 9 / Rule 10 / OP violations** (cite specific rule or OP number if any)
5. **Hidden second-order effects** (what depends on this? what does this break downstream?)
6. **Risk score** (1-10, single integer, with one-sentence justification)
7. **Single most-important question the human reviewer should ask before shipping**

If the proposal is solid, say so plainly — don't manufacture risk.
""",
    "brainstorm": """MODE: BRAINSTORM (generate N independent ideas)

Your job: propose N candidate ideas that address the question. Each idea should be specific enough that someone could implement it without ambiguity.

For EACH idea:
1. **Name** (3-6 words, imperative)
2. **What it does** (1 sentence)
3. **Why it works** (1 sentence — what edge/insight it exploits)
4. **Concrete mechanism** (2-4 sentences — what code/data/process)
5. **Failure mode** (1 sentence — most likely way it underdelivers)
6. **First test** (1 sentence — smallest experiment to validate)

Diversify across categories: don't propose 3 variants of the same idea. Aim for orthogonal approaches.
""",
    "critique": """MODE: CRITIQUE (find the holes)

Your job: rigorously critique the proposed work. Find what's overfitting, what's not yet validated, what's cherry-picked, what's missing.

Produce these sections:
1. **Strongest claim** (the load-bearing assertion the work depends on)
2. **Weakest evidence** (the place where the claim outruns the data)
3. **Cherry-pick risk** (selection effects, regime concentration, anchor-day fitting)
4. **Missing disclosures** (per OP-20: account size, sample bias, OOS, real-fills, failure mode, concentration)
5. **What would change my mind** (specific test/data that would validate or kill it)
6. **Verdict** (HOLD / PROMOTE / NEEDS-MORE / REJECT — one word + one-sentence reasoning)
""",
    "rank": """MODE: RANK (pick the best of N options)

Your job: given a set of options, rank them by quality against the criteria.

Produce:
1. **Ranked table** (option name | score 1-10 | one-sentence why)
2. **Top pick + reasoning** (3-5 sentences explaining why #1 beats #2)
3. **Dominated options** (any option strictly worse than another — call out)
4. **What's missing from all options** (1-2 sentences — the option none of them contain)
""",
    "decide": """MODE: DECIDE (single recommended action)

Your job: given the question + context, recommend ONE action.

Produce:
1. **Recommended action** (1 sentence — specific, concrete, executable)
2. **Reasoning** (3-5 sentences — why this beats alternatives)
3. **Confidence** (1-10, single integer)
4. **Required follow-up** (1 sentence — what to watch for after acting)
5. **If I were wrong, the signal would be** (1 sentence — what would tell us to reverse)
""",
}


# ────────────────────────────────────────────────────────────────────────────
# Result envelopes
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Perspective:
    model: str
    ok: bool
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    elapsed_s: float
    error: Optional[str]


@dataclass
class SwarmResult:
    mode: str
    question: str
    context: str
    perspectives: list[Perspective] = field(default_factory=list)
    synthesis: Optional[Perspective] = None
    total_cost_usd: float = 0.0
    total_elapsed_s: float = 0.0
    slug: str = ""
    ts_et: str = ""


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _slugify(s: str, max_len: int = 60) -> str:
    out = []
    for c in s.lower():
        if c.isalnum():
            out.append(c)
        elif c in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:max_len] or "untitled"


def _read_context_file(path: str, max_bytes: int = 200_000) -> str:
    p = Path(path)
    if not p.exists():
        return f"[context file not found: {path}]"
    try:
        data = p.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[... truncated {len(data) - max_bytes:,} bytes ...]"
        return data
    except OSError as exc:
        return f"[context read error: {exc}]"


def _build_perspective_prompt(mode: str, question: str, context: str) -> str:
    instructions = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["decide"])
    sections = [f"# Question\n\n{question}\n"]
    if context.strip():
        sections.append(f"## Context\n\n```\n{context}\n```\n")
    sections.append(f"## Your task\n\n{instructions}")
    return "\n".join(sections)


def _build_synthesis_prompt(
    mode: str,
    question: str,
    context: str,
    perspectives: list[Perspective],
) -> str:
    perspectives_block = []
    for i, p in enumerate(perspectives, 1):
        if not p.ok:
            perspectives_block.append(
                f"### Perspective {i} ({p.model}) -- FAILED\n\nError: {p.error}\n"
            )
        else:
            perspectives_block.append(
                f"### Perspective {i} ({p.model})\n\n{p.content.strip()}\n"
            )

    # Truncate context for synthesis pass to save tokens
    ctx_for_synth = context if len(context) < 5000 else (context[:5000] + "\n[truncated for synthesis]")

    mode_label = mode.upper()

    sections = [
        f"# Synthesis task ({mode_label})\n",
        f"## Original question\n\n{question}\n",
    ]
    if ctx_for_synth.strip():
        sections.append(f"## Context (truncated)\n\n```\n{ctx_for_synth}\n```\n")
    sections.append(f"## Perspectives ({len([p for p in perspectives if p.ok])} of {len(perspectives)} succeeded)\n")
    sections.extend(perspectives_block)
    sections.append(
        "## Your synthesis task\n\n"
        f"You are synthesizing the {len(perspectives)} perspectives above into a SINGLE actionable output for Project Gamma.\n\n"
        "Produce:\n"
        "1. **Consensus points** — what all perspectives agree on (bullet list)\n"
        "2. **Key disagreements** — where perspectives split, and which is most rigorous (with reasoning)\n"
        "3. **Synthesized recommendation** — one paragraph distilling the best of the above\n"
        "4. **Confidence in synthesis** (1-10) — based on perspective convergence + evidence quality\n"
        "5. **Single most-important next action** — concrete, specific, executable today\n"
        "6. **Watch-for signal** — what observation would invalidate the synthesis\n\n"
        "Be DECISIVE. The point of multi-model swarm is convergence, not a hung jury. If 2 of 3 perspectives agree, say so and pick the 2-side; if they all diverge, pick the most rigorous and say why.\n"
    )
    return "\n".join(sections)


# ────────────────────────────────────────────────────────────────────────────
# Core fan-out + synthesis
# ────────────────────────────────────────────────────────────────────────────


def _call_one_perspective(
    *,
    model: str,
    prompt: str,
    system: str,
    max_tokens: int,
    task_id: str,
) -> Perspective:
    """Single model call. Always returns a Perspective (never raises)."""
    result = call_minimax(
        prompt=prompt,
        model=model,
        system=system,
        max_tokens=max_tokens,
        temperature=0.4,
        timeout=PERSPECTIVE_TIMEOUT_S,
        task_id=task_id,
    )
    return Perspective(
        model=model,
        ok=bool(result.get("ok")),
        content=result.get("content", "") or "",
        input_tokens=int(result.get("input_tokens", 0) or 0),
        output_tokens=int(result.get("output_tokens", 0) or 0),
        cost_usd=float(result.get("cost_usd", 0.0) or 0.0),
        elapsed_s=float(result.get("elapsed_s", 0.0) or 0.0),
        error=result.get("error"),
    )


def consult(
    *,
    mode: str,
    question: str,
    context: str = "",
    models: tuple[str, ...] = DEFAULT_PERSPECTIVE_MODELS,
    synthesizer: str = DEFAULT_SYNTHESIZER_MODEL,
    max_tokens_per_perspective: int = 2500,
    max_tokens_synthesis: int = 3000,
    skip_synthesis: bool = False,
) -> SwarmResult:
    """Run a swarm consultation. Returns a populated SwarmResult.

    Always returns even if some perspectives fail — caller checks .perspectives[i].ok
    to see which succeeded.
    """
    if mode not in _MODE_INSTRUCTIONS:
        raise ValueError(f"unknown mode: {mode}. Must be one of {sorted(_MODE_INSTRUCTIONS)}")

    if not question.strip():
        raise ValueError("question is empty")

    ts_et = _et_now()
    slug = _slugify(question, max_len=50)
    system = _SHARED_PREAMBLE
    prompt = _build_perspective_prompt(mode, question, context)

    result = SwarmResult(
        mode=mode,
        question=question,
        context=context,
        slug=slug,
        ts_et=ts_et.isoformat(timespec="seconds"),
    )

    import time
    swarm_start = time.monotonic()

    # Fan out in parallel
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(
                _call_one_perspective,
                model=m,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens_per_perspective,
                task_id=f"swarm.{mode}.{slug[:20]}.{i}",
            ): (i, m)
            for i, m in enumerate(models)
        }
        perspectives_by_index: dict[int, Perspective] = {}
        for fut in as_completed(futures):
            i, m = futures[fut]
            try:
                perspectives_by_index[i] = fut.result()
            except Exception as exc:  # defensive — shouldn't happen, _call_one_perspective never raises
                perspectives_by_index[i] = Perspective(
                    model=m, ok=False, content="", input_tokens=0, output_tokens=0,
                    cost_usd=0.0, elapsed_s=0.0,
                    error=f"future_exception: {type(exc).__name__}: {exc}",
                )
    # Preserve input order
    result.perspectives = [perspectives_by_index[i] for i in range(len(models))]

    succeeded = [p for p in result.perspectives if p.ok and p.content.strip()]

    # Synthesize if at least 1 perspective came back
    if succeeded and not skip_synthesis:
        synth_prompt = _build_synthesis_prompt(mode, question, context, result.perspectives)
        synth_result = call_minimax(
            prompt=synth_prompt,
            model=synthesizer,
            system=_SHARED_PREAMBLE,
            max_tokens=max_tokens_synthesis,
            temperature=0.3,
            timeout=SYNTHESIS_TIMEOUT_S,
            task_id=f"swarm.{mode}.{slug[:20]}.synth",
        )
        result.synthesis = Perspective(
            model=synthesizer,
            ok=bool(synth_result.get("ok")),
            content=synth_result.get("content", "") or "",
            input_tokens=int(synth_result.get("input_tokens", 0) or 0),
            output_tokens=int(synth_result.get("output_tokens", 0) or 0),
            cost_usd=float(synth_result.get("cost_usd", 0.0) or 0.0),
            elapsed_s=float(synth_result.get("elapsed_s", 0.0) or 0.0),
            error=synth_result.get("error"),
        )

    result.total_elapsed_s = round(time.monotonic() - swarm_start, 3)
    result.total_cost_usd = round(
        sum(p.cost_usd for p in result.perspectives) + (result.synthesis.cost_usd if result.synthesis else 0.0),
        6,
    )
    return result


# ────────────────────────────────────────────────────────────────────────────
# Output writers
# ────────────────────────────────────────────────────────────────────────────


def _write_outputs(result: SwarmResult) -> tuple[Path, Path]:
    """Write the markdown report + JSON sidecar. Returns (md_path, json_path)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ts_str = result.ts_et.replace(":", "").replace("-", "")[:15]  # YYYYMMDDTHHMMSS
    today = result.ts_et[:10]
    stem = f"{today}-{ts_str[-6:]}-{result.mode}-{result.slug}"

    md_path = OUT_DIR / f"{stem}.md"
    json_path = OUT_DIR / f"{stem}.json"

    # Markdown report
    md_lines = [
        f"# SWARM CONSULT: {result.mode.upper()} -- {result.question[:80]}",
        "",
        f"**Filed:** {result.ts_et} ET",
        f"**Mode:** `{result.mode}`",
        f"**Cost:** ${result.total_cost_usd:.4f}",
        f"**Elapsed:** {result.total_elapsed_s:.1f}s",
        f"**Perspectives:** {sum(1 for p in result.perspectives if p.ok)} / {len(result.perspectives)} succeeded",
        "",
        "## Question",
        "",
        result.question,
        "",
    ]
    if result.context.strip():
        md_lines.extend([
            "## Context (provided)",
            "",
            "```",
            result.context if len(result.context) < 10_000 else (result.context[:10_000] + "\n[truncated]"),
            "```",
            "",
        ])

    # Synthesis first (the actionable output)
    if result.synthesis and result.synthesis.ok:
        md_lines.extend([
            "## Synthesis (actionable)",
            "",
            f"_Model: `{result.synthesis.model}`, elapsed {result.synthesis.elapsed_s:.1f}s, cost ${result.synthesis.cost_usd:.4f}_",
            "",
            result.synthesis.content.strip(),
            "",
        ])
    elif result.synthesis:
        md_lines.extend([
            "## Synthesis -- FAILED",
            "",
            f"Error: `{result.synthesis.error}`",
            "",
        ])
    else:
        md_lines.extend([
            "## Synthesis -- SKIPPED",
            "",
            "(no successful perspectives, or synthesis skipped by caller)",
            "",
        ])

    md_lines.append("## Individual perspectives")
    md_lines.append("")
    for i, p in enumerate(result.perspectives, 1):
        md_lines.append(f"### Perspective {i}: `{p.model}`")
        md_lines.append("")
        if p.ok:
            md_lines.append(f"_Elapsed {p.elapsed_s:.1f}s, {p.input_tokens} in / {p.output_tokens} out, cost ${p.cost_usd:.4f}_")
            md_lines.append("")
            md_lines.append(p.content.strip())
        else:
            md_lines.append(f"**FAILED** -- `{p.error}`")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # JSON sidecar
    json_data = {
        "ts_et": result.ts_et,
        "mode": result.mode,
        "question": result.question,
        "context": result.context,
        "slug": result.slug,
        "total_cost_usd": result.total_cost_usd,
        "total_elapsed_s": result.total_elapsed_s,
        "perspectives": [asdict(p) for p in result.perspectives],
        "synthesis": asdict(result.synthesis) if result.synthesis else None,
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append log entry
    log_entry = {
        "ts_et": result.ts_et,
        "mode": result.mode,
        "slug": result.slug,
        "question_head": result.question[:120],
        "perspectives_ok": sum(1 for p in result.perspectives if p.ok),
        "perspectives_total": len(result.perspectives),
        "synthesis_ok": bool(result.synthesis and result.synthesis.ok),
        "total_cost_usd": result.total_cost_usd,
        "total_elapsed_s": result.total_elapsed_s,
        "md_path": str(md_path.relative_to(REPO)),
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, separators=(",", ":"), ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[swarm-consult] WARN log write failed: {exc}", file=sys.stderr)

    return md_path, json_path


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        choices=sorted(_MODE_INSTRUCTIONS.keys()),
        help="audit | brainstorm | critique | rank | decide",
    )
    parser.add_argument("--question", required=True, help="The question / proposal / topic")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--context", help="Inline context block")
    g.add_argument("--context-file", help="Path to a file containing context")
    parser.add_argument(
        "--models",
        help="Comma-separated OpenRouter slugs to use as perspectives (default: 3 free-tier)",
    )
    parser.add_argument(
        "--synthesizer",
        default=DEFAULT_SYNTHESIZER_MODEL,
        help=f"Synthesizer model (default: {DEFAULT_SYNTHESIZER_MODEL})",
    )
    parser.add_argument("--max-tokens-per-perspective", type=int, default=2500)
    parser.add_argument("--max-tokens-synthesis", type=int, default=3000)
    parser.add_argument("--skip-synthesis", action="store_true", help="Just collect perspectives, no synthesis")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout banner; only print paths")
    args = parser.parse_args()

    if args.models:
        models = tuple(m.strip() for m in args.models.split(",") if m.strip())
    else:
        models = DEFAULT_PERSPECTIVE_MODELS

    context = ""
    if args.context:
        context = args.context
    elif args.context_file:
        context = _read_context_file(args.context_file)

    if not args.quiet:
        print(
            f"[swarm-consult] mode={args.mode} models={len(models)} synth={args.synthesizer.split('/')[-1]} starting fan-out...",
            file=sys.stderr,
        )

    result = consult(
        mode=args.mode,
        question=args.question,
        context=context,
        models=models,
        synthesizer=args.synthesizer,
        max_tokens_per_perspective=args.max_tokens_per_perspective,
        max_tokens_synthesis=args.max_tokens_synthesis,
        skip_synthesis=args.skip_synthesis,
    )

    md_path, json_path = _write_outputs(result)

    succeeded = sum(1 for p in result.perspectives if p.ok)
    if not args.quiet:
        print(
            f"[swarm-consult] DONE perspectives_ok={succeeded}/{len(result.perspectives)} "
            f"synth_ok={bool(result.synthesis and result.synthesis.ok)} "
            f"cost=${result.total_cost_usd:.4f} elapsed={result.total_elapsed_s:.1f}s",
            file=sys.stderr,
        )
    print(str(md_path))
    print(str(json_path))
    return 0 if succeeded > 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
