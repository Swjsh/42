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


# ────────────────────────────────────────────────────────────────────────────
# Multi-provider routing — a perspective model is a "provider:model" spec.
# Bare slugs (no prefix) default to OpenRouter (back-compat). Non-OpenRouter
# providers (cerebras/groq) are called directly via the OpenAI-compatible SDK so
# the swarm can pull GLM (Cerebras), etc. ALL providers here are NO-TRAIN (safe
# for sensitive engine internals); Gemini/Mistral train on input and are excluded.
# ────────────────────────────────────────────────────────────────────────────
_PROVIDERS: dict[str, dict] = {
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",  "key_file": STATE_DIR / ".openrouter.key", "trains": False},
    "cerebras":   {"base_url": "https://api.cerebras.ai/v1",     "key_file": STATE_DIR / ".cerebras.key",   "trains": False},
    "groq":       {"base_url": "https://api.groq.com/openai/v1", "key_file": STATE_DIR / ".groq.key",       "trains": False},
}


def _split_spec(spec: str) -> tuple[str, str]:
    """'cerebras:zai-glm-4.7' -> ('cerebras','zai-glm-4.7'); bare slug -> ('openrouter', slug).

    OpenRouter slugs contain '/' (vendor/model) so the FIRST ':' only counts as a
    provider prefix when the prefix is a known provider — avoids mis-splitting a
    rare ':free' suffix or a slug with a colon.
    """
    if ":" in spec:
        head = spec.split(":", 1)[0]
        if head in _PROVIDERS:
            return head, spec.split(":", 1)[1]
    return "openrouter", spec


# Default fan-out: 5 independent free perspectives across 4 distinct VENDORS + 2
# providers (J 2026-06-28: "get 5 in the swarm" incl. GLM + DeepSeek). GLM via
# Cerebras (free, no-train). DeepSeek is PAID on every reachable host right now
# (OpenRouter paid; Groq decommissioned the free distills) — excluded under the
# free-only rule; swap in when a free host returns. LIVE-VERIFIED 2026-06-28.
# Lesson: NEVER hand-pick slugs from memory — catalogs rotate; probe live (--audit-roster).
DEFAULT_PERSPECTIVE_MODELS: tuple[str, ...] = (
    "cerebras:zai-glm-4.7",                      # GLM 4.7 — Cerebras free, no-train, strong reasoner
    "nvidia/nemotron-3-super-120b-a12b:free",   # NVIDIA 120B — 1M ctx
    "openai/gpt-oss-120b:free",                  # OpenAI open 120B — distinct lineage
    "google/gemma-4-31b-it:free",                # Google 31B — 262K ctx
    "qwen/qwen3-next-80b-a3b-instruct:free",     # Qwen 80B — fifth vendor
)
# Rotation pool: when a primary 429s/404s, _call_one_perspective falls through to
# the next live model so we still get a full set. 429 = transient (rotate), 404 = dead (skip).
PERSPECTIVE_FALLBACK_POOL: tuple[str, ...] = (
    "cerebras:gpt-oss-120b",                     # Cerebras gpt-oss — GLM-lane fallback (no-train)
    "openai/gpt-oss-20b:free",                   # OpenAI 20B — fast
    "meta-llama/llama-3.3-70b-instruct:free",    # Meta 70B
    "nousresearch/hermes-3-llama-3.1-405b:free", # Nous 405B
    "qwen/qwen3-coder:free",                      # Qwen coder 1M ctx
    "nvidia/nemotron-3-ultra-550b-a55b:free",    # NVIDIA 550B — heavy
)
# Errors worth rotating to a different model (transient capacity / de-tagged slug).
_ROTATABLE_ERR_MARKERS = ("429", "RateLimit", "404", "NotFound", "unavailable", "Timeout", "timed out", "503", "502")
DEFAULT_SYNTHESIZER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def _provider_call(spec: str, *, prompt: str, system: Optional[str], max_tokens: int,
                   temperature: float, timeout: int, task_id: str) -> dict:
    """Call a perspective model on its provider. Returns the same envelope shape as
    call_minimax (ok/content/model/input_tokens/output_tokens/cost_usd/elapsed_s/error).

    OpenRouter specs delegate to call_minimax (keeps its telemetry + cap logic).
    Cerebras/Groq are called directly. Reasoning models (GLM, gpt-oss) often put the
    answer in `.reasoning` when `.content` is empty under a tight budget — we fall
    back to reasoning so a thinking model never reads as an empty failure.
    """
    provider, model = _split_spec(spec)
    if provider == "openrouter":
        return call_minimax(prompt=prompt, model=model, system=system, max_tokens=max_tokens,
                            temperature=temperature, timeout=timeout, task_id=task_id)

    import time as _t
    start = _t.monotonic()
    cfg = _PROVIDERS.get(provider)
    if not cfg:
        return {"ok": False, "content": "", "model": spec, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "elapsed_s": 0.0, "error": f"unknown_provider:{provider}"}
    try:
        key = cfg["key_file"].read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "content": "", "model": spec, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "elapsed_s": round(_t.monotonic() - start, 3),
                "error": f"key_load_failed:{provider}:{exc}"}
    try:
        from openai import OpenAI
        client = OpenAI(base_url=cfg["base_url"], api_key=key, timeout=float(timeout))
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(model=model, messages=messages,
                                              max_tokens=max_tokens, temperature=temperature)
        choice = resp.choices[0] if resp.choices else None
        msg = choice.message if choice else None
        content = (getattr(msg, "content", None) or "") if msg else ""
        if not content.strip() and msg is not None:
            content = getattr(msg, "reasoning", "") or ""  # thinking model fallback
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        elapsed = round(_t.monotonic() - start, 3)
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task_id": task_id,
                 "model": spec, "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": 0.0,
                 "elapsed_s": elapsed, "ok": bool(content.strip()), "provider": provider}
        try:
            with open(STATE_DIR / "swarm-calls.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
        return {"ok": bool(content.strip()), "content": content, "model": spec, "input_tokens": in_tok,
                "output_tokens": out_tok, "cost_usd": 0.0, "elapsed_s": elapsed,
                "error": None if content.strip() else "empty_content"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "content": "", "model": spec, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "elapsed_s": round(_t.monotonic() - start, 3),
                "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

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


def _is_rotatable_error(err: Optional[str]) -> bool:
    """True if the error is transient/capacity/de-tag — worth trying another model."""
    if not err:
        return False
    return any(marker.lower() in err.lower() for marker in _ROTATABLE_ERR_MARKERS)


def _call_one_perspective(
    *,
    model: str,
    prompt: str,
    system: str,
    max_tokens: int,
    task_id: str,
    fallbacks: tuple[str, ...] = (),
    claimed: Optional[set] = None,
    claim_lock=None,
) -> Perspective:
    """Single perspective. Tries `model` first, then rotates through `fallbacks`
    on transient errors (429/404/timeout) so the swarm still returns a full set
    of perspectives instead of collapsing to 1.

    `claimed` + `claim_lock` (optional) keep parallel lanes on DISTINCT models so
    3 perspectives don't all land on the same fallback. Always returns a
    Perspective (never raises).
    """
    def _claim(m: str) -> bool:
        if claimed is None or claim_lock is None:
            return True
        with claim_lock:
            if m in claimed:
                return False
            claimed.add(m)
            return True

    candidates = [model, *[m for m in fallbacks if m != model]]
    last_err: Optional[str] = None
    attempts: list[str] = []

    for cand in candidates:
        if not _claim(cand):
            continue  # another lane owns this model — keep diversity
        attempts.append(cand)
        result = _provider_call(
            cand,
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=0.4,
            timeout=PERSPECTIVE_TIMEOUT_S,
            task_id=task_id,
        )
        ok = bool(result.get("ok")) and (result.get("content", "") or "").strip()
        if ok:
            return Perspective(
                model=cand,
                ok=True,
                content=result.get("content", "") or "",
                input_tokens=int(result.get("input_tokens", 0) or 0),
                output_tokens=int(result.get("output_tokens", 0) or 0),
                cost_usd=float(result.get("cost_usd", 0.0) or 0.0),
                elapsed_s=float(result.get("elapsed_s", 0.0) or 0.0),
                error=None,
            )
        last_err = result.get("error") or "empty_content"
        # Release the claim on a dead/transient model so a later lane could retry it.
        if claimed is not None and claim_lock is not None:
            with claim_lock:
                claimed.discard(cand)
        if not _is_rotatable_error(last_err):
            break  # hard error (bad prompt, auth) — rotating won't help

    return Perspective(
        model=model, ok=False, content="",
        input_tokens=0, output_tokens=0, cost_usd=0.0, elapsed_s=0.0,
        error=f"all_lanes_failed (tried {attempts}): {last_err}",
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
    import threading
    swarm_start = time.monotonic()

    # Shared claim-set keeps the 3 lanes on DISTINCT models when they rotate
    # through the shared fallback pool (preserves perspective diversity).
    claimed: set = set()
    claim_lock = threading.Lock()

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
                fallbacks=PERSPECTIVE_FALLBACK_POOL,
                claimed=claimed,
                claim_lock=claim_lock,
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
        synth_result = _provider_call(
            synthesizer,
            prompt=synth_prompt,
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
# Roster self-heal — query the LIVE OpenRouter catalog (the only source of truth)
# ────────────────────────────────────────────────────────────────────────────


def audit_roster(verify_calls: bool = True) -> dict:
    """Probe OpenRouter's live /models catalog + (optionally) test each configured
    perspective model with a tiny call. Returns a report dict and prints it.

    This is the self-heal that prevents the "all models 404" rot: the free catalog
    rotates constantly, so we re-derive truth from the API instead of trusting
    hand-picked slugs. Run from a scheduled task or by hand after a swarm comes
    back with <3 perspectives.
    """
    import urllib.request

    try:
        key = _load_api_key_for_audit()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"key load failed: {exc}"}

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        catalog = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"catalog fetch failed: {exc}"}

    free_ids = set()
    for m in catalog.get("data", []):
        pr = m.get("pricing", {})
        try:
            if float(pr.get("prompt", "1") or "1") == 0.0 and float(pr.get("completion", "1") or "1") == 0.0:
                free_ids.add(m["id"])
        except (TypeError, ValueError):
            continue

    configured = list(DEFAULT_PERSPECTIVE_MODELS) + list(PERSPECTIVE_FALLBACK_POOL)
    # Catalog-check applies only to OpenRouter specs (cerebras/groq have their own
    # catalogs we don't list-probe; their live-call result below is the proof).
    or_specs = [m for m in configured if _split_spec(m)[0] == "openrouter"]
    report = {
        "ok": True,
        "checked_at_et": _et_now().isoformat(timespec="seconds"),
        "free_catalog_count": len(free_ids),
        "in_catalog": [m for m in or_specs if m in free_ids],
        "DROPPED_FROM_FREE": [m for m in or_specs if m not in free_ids],
        "non_openrouter": [m for m in configured if _split_spec(m)[0] != "openrouter"],
        "live_call_ok": [],
        "live_call_fail": [],
    }

    if verify_calls:
        # Cerebras reasoning models need a bigger budget or content comes back empty.
        for m in DEFAULT_PERSPECTIVE_MODELS:
            r = _provider_call(m, prompt="Reply with exactly: OK", system=None, max_tokens=300,
                               timeout=40, task_id="roster_audit", temperature=0)
            (report["live_call_ok"] if r.get("ok") else report["live_call_fail"]).append(
                m if r.get("ok") else f"{m} :: {(r.get('error') or '')[:60]}"
            )

    print(json.dumps(report, indent=2))
    if report["DROPPED_FROM_FREE"]:
        print(
            f"\n[audit-roster] WARNING: {len(report['DROPPED_FROM_FREE'])} configured model(s) "
            f"no longer free. Replace them from this free catalog:",
            file=sys.stderr,
        )
        for mid in sorted(free_ids):
            print(f"  {mid}", file=sys.stderr)
    return report


def _load_api_key_for_audit() -> str:
    """Reuse run_minimax's key resolution without importing private names."""
    from run_minimax import _load_api_key  # noqa: PLC0415
    return _load_api_key()


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _main() -> int:
    # Standalone self-heal command — bypasses the positional-mode parser.
    if "--audit-roster" in sys.argv:
        rep = audit_roster(verify_calls="--no-verify" not in sys.argv)
        return 0 if rep.get("ok") and not rep.get("DROPPED_FROM_FREE") else 1

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
