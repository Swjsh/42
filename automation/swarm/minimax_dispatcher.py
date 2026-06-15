"""MiniMax dispatcher for swarm agents (Stages 2-4).

Routes Stages 2-3 (technical, macro, level_thesis, internals, validator) and
Stage 4 (synthesis / CIO) off the Claude `--print` path onto OpenRouter / MiniMax
M2 via run_minimax.py.

Stage 1 (data_fetcher) stays on Claude — it needs TV+Alpaca MCP.

Synthesis moved to MiniMax 2026-05-20: Claude Sonnet was consistently timing out
at 120s (reads 6 JSON files + complex 9-step formula). MiniMax handles in <90s at
~5x lower cost. Per J: "fix this and run swarm with those models."

PER CLAUDE.md OP-25 ENGINE-BENEFIT AUTONOMY: this is observer/infrastructure
work. Ships without weekend ratification. Synthesis stays Claude → swarm output
quality unchanged. Specialists move to M2 → ~5x cheaper per agent.

PER CLAUDE.md OP-28: swarm is advisory-only. Output schema unchanged.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow this module to be imported both as `automation.swarm.minimax_dispatcher`
# and run directly from the swarm dir (Pool spawn workers may pick either).
_THIS_DIR = Path(__file__).resolve().parent
_REPO = _THIS_DIR.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Direct import path (sibling to setup/)
sys.path.insert(0, str(_REPO / "setup" / "scripts"))
from run_minimax import call_minimax, DEFAULT_MODEL as MINIMAX_DEFAULT_MODEL  # noqa: E402

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

WORK_DIR = _REPO
SWARM_DIR = WORK_DIR / "automation" / "swarm"
STATE_DIR = SWARM_DIR / "state"
GLOBAL_STATE_DIR = WORK_DIR / "automation" / "state"
PROMPTS_DIR = SWARM_DIR / "prompts"

# ────────────────────────────────────────────────────────────────────────────
# Per-agent input file map (Stages 2-4; data_fetcher excluded — needs MCP)
# ────────────────────────────────────────────────────────────────────────────

AGENT_INPUTS: dict[str, list[Path]] = {
    # Stage 2 — original 4 specialists
    "technical":          [STATE_DIR / "raw_data.json",
                           GLOBAL_STATE_DIR / "key-levels.json"],
    "macro":              [STATE_DIR / "raw_data.json",
                           GLOBAL_STATE_DIR / "macro-calendar.json"],
    "level_thesis":       [STATE_DIR / "raw_data.json",
                           GLOBAL_STATE_DIR / "key-levels.json"],
    "internals":          [STATE_DIR / "raw_data.json"],
    # Stage 2 — 9 new specialists (added 2026-05-20 expansion, wired to AGENT_INPUTS 2026-05-21)
    "volume_analyst":     [STATE_DIR / "raw_data.json"],
    "momentum_analyst":   [STATE_DIR / "raw_data.json"],
    "regime_classifier":  [STATE_DIR / "raw_data.json"],
    "premarket_analyst":  [STATE_DIR / "raw_data.json",
                           GLOBAL_STATE_DIR / "key-levels.json"],
    "pattern_scout":      [STATE_DIR / "raw_data.json",
                           GLOBAL_STATE_DIR / "key-levels.json"],
    "catalyst_analyst":   [GLOBAL_STATE_DIR / "macro-calendar.json"],
    "sentiment_analyst":  [STATE_DIR / "raw_data.json"],
    "correlation_analyst":[STATE_DIR / "raw_data.json"],
    "session_timer":      [STATE_DIR / "raw_data.json"],
    # Stage 3 — validator + risk_assessor read all available specialist outputs
    "validator":          [STATE_DIR / "technical_output.json",
                           STATE_DIR / "macro_output.json",
                           STATE_DIR / "level_thesis_output.json",
                           STATE_DIR / "internals_output.json",
                           STATE_DIR / "volume_analyst_output.json",
                           STATE_DIR / "momentum_analyst_output.json",
                           STATE_DIR / "regime_classifier_output.json",
                           STATE_DIR / "premarket_analyst_output.json",
                           STATE_DIR / "pattern_scout_output.json",
                           STATE_DIR / "catalyst_analyst_output.json",
                           STATE_DIR / "sentiment_analyst_output.json",
                           STATE_DIR / "correlation_analyst_output.json",
                           STATE_DIR / "session_timer_output.json"],
    "risk_assessor":      [STATE_DIR / "technical_output.json",
                           STATE_DIR / "macro_output.json",
                           STATE_DIR / "level_thesis_output.json",
                           STATE_DIR / "internals_output.json",
                           STATE_DIR / "volume_analyst_output.json",
                           STATE_DIR / "momentum_analyst_output.json",
                           STATE_DIR / "regime_classifier_output.json",
                           STATE_DIR / "premarket_analyst_output.json",
                           STATE_DIR / "pattern_scout_output.json",
                           STATE_DIR / "catalyst_analyst_output.json",
                           STATE_DIR / "sentiment_analyst_output.json",
                           STATE_DIR / "correlation_analyst_output.json",
                           STATE_DIR / "session_timer_output.json"],
    # Stage 4 — synthesis CIO reads ALL available specialist + validator + risk outputs
    "synthesis":          [STATE_DIR / "technical_output.json",
                           STATE_DIR / "macro_output.json",
                           STATE_DIR / "level_thesis_output.json",
                           STATE_DIR / "internals_output.json",
                           STATE_DIR / "volume_analyst_output.json",
                           STATE_DIR / "momentum_analyst_output.json",
                           STATE_DIR / "regime_classifier_output.json",
                           STATE_DIR / "premarket_analyst_output.json",
                           STATE_DIR / "pattern_scout_output.json",
                           STATE_DIR / "catalyst_analyst_output.json",
                           STATE_DIR / "sentiment_analyst_output.json",
                           STATE_DIR / "correlation_analyst_output.json",
                           STATE_DIR / "session_timer_output.json",
                           STATE_DIR / "validator_output.json",
                           GLOBAL_STATE_DIR / "key-levels.json"],
}

AGENT_OUTPUTS: dict[str, Path] = {
    # Stage 2 — original 4 specialists
    "technical":          STATE_DIR / "technical_output.json",
    "macro":              STATE_DIR / "macro_output.json",
    "level_thesis":       STATE_DIR / "level_thesis_output.json",
    "internals":          STATE_DIR / "internals_output.json",
    # Stage 2 — 9 new specialists (wired 2026-05-21)
    "volume_analyst":     STATE_DIR / "volume_analyst_output.json",
    "momentum_analyst":   STATE_DIR / "momentum_analyst_output.json",
    "regime_classifier":  STATE_DIR / "regime_classifier_output.json",
    "premarket_analyst":  STATE_DIR / "premarket_analyst_output.json",
    "pattern_scout":      STATE_DIR / "pattern_scout_output.json",
    "catalyst_analyst":   STATE_DIR / "catalyst_analyst_output.json",
    "sentiment_analyst":  STATE_DIR / "sentiment_analyst_output.json",
    "correlation_analyst":STATE_DIR / "correlation_analyst_output.json",
    "session_timer":      STATE_DIR / "session_timer_output.json",
    # Stage 3
    "validator":          STATE_DIR / "validator_output.json",
    "risk_assessor":      STATE_DIR / "risk_assessor_output.json",
    # Stage 4 — synthesis writes the canonical swarm output
    "synthesis":          STATE_DIR / "swarm_output.json",
}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.MULTILINE)


def _et_now_str() -> str:
    """ISO local-ish ET (best-effort) — for runtime header parity with run_claude_agent."""
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo("America/New_York")
        return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        # UTC fallback
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _runtime_header(agent_name: str) -> str:
    """Same header shape as runner.py _runtime_header — keeps parity for graders."""
    return (
        "# RUNTIME CONTEXT (injected by swarm minimax_dispatcher)\n"
        f"- Current ET time: {_et_now_str()}\n"
        f"- Today's date (ET): {_et_now_str()[:10]}\n"
        f"- Agent: {agent_name}\n"
        f"- Working directory: {WORK_DIR}\n"
        f"- Execution engine: minimax (via OpenRouter)\n"
        "\n---\n\n"
    )


def _read_input_files(agent_name: str) -> tuple[str, list[str]]:
    """Inline all input files as fenced blocks for the agent prompt.

    Returns (context_block, missing_files). Missing files don't raise — the
    agent prompts handle missing levels gracefully ("data_quality: minimal").
    """
    inputs = AGENT_INPUTS.get(agent_name, [])
    if not inputs:
        return "", []

    blocks: list[str] = []
    missing: list[str] = []
    for path in inputs:
        rel = path.relative_to(WORK_DIR) if path.is_absolute() and path.is_relative_to(WORK_DIR) else path
        if not path.exists():
            missing.append(str(rel))
            blocks.append(
                f"### `{rel}`\n\n"
                "FILE MISSING — proceed with `data_quality: minimal` "
                "and fields filled per the prompt's missing-data rules.\n"
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            missing.append(str(rel))
            blocks.append(f"### `{rel}`\n\nFILE UNREADABLE: {exc}\n")
            continue
        blocks.append(f"### `{rel}`\n\n```json\n{text}\n```\n")

    return "\n".join(blocks), missing


def _extract_json(text: str) -> Optional[dict]:
    """Robustly extract the first top-level JSON object from model output.

    Handles:
      - Bare JSON object (most common)
      - ```json fenced block (markdown wrapped)
      - Preamble + JSON (strip until first '{')
    """
    if not text or not text.strip():
        return None
    s = text.strip()

    # Strip markdown fence if present
    s = _JSON_FENCE_RE.sub("", s).strip()

    # First attempt: parse as-is
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Locate first '{' and last '}', take the slice, retry
    first = s.find("{")
    last = s.rfind("}")
    if first >= 0 and last > first:
        slice_ = s[first:last + 1]
        try:
            return json.loads(slice_)
        except json.JSONDecodeError:
            return None
    return None


def _build_agent_prompt(agent_name: str, prompt_path: Path) -> str:
    """Compose the full user prompt: runtime header + inlined inputs + agent instructions + output rule."""
    try:
        raw_prompt = prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(f"agent prompt missing: {prompt_path}")

    context_block, _missing = _read_input_files(agent_name)

    output_file_name = AGENT_OUTPUTS[agent_name].name
    output_rule = (
        "## OUTPUT RULE (CRITICAL)\n\n"
        f"You will NOT write files. The dispatcher writes `{output_file_name}` for you.\n"
        "Respond with EXACTLY the JSON object specified by your prompt. "
        "NO preamble, NO explanation, NO markdown code fences, NO trailing text. "
        "Output starts with `{` and ends with `}`. Nothing else.\n"
    )

    return (
        _runtime_header(agent_name)
        + "# FILES YOU CAN READ (already inlined — do NOT try to read them via tools)\n\n"
        + context_block
        + "\n---\n\n# YOUR INSTRUCTIONS\n\n"
        + raw_prompt
        + "\n\n---\n\n"
        + output_rule
    )


# ────────────────────────────────────────────────────────────────────────────
# Main entry — module-level (Pool-pickle safe)
# ────────────────────────────────────────────────────────────────────────────


def run_minimax_agent(args: tuple) -> dict:
    """Pool-safe MiniMax invocation. Same signature as runner.run_claude_agent.

    Args:
        args: (agent_name: str, prompt_path: Path, cfg: dict)
            cfg recognized keys:
              - timeout: int seconds (default 120)
              - minimax_model: str (default "minimax/minimax-m2")
              - max_tokens: int (default 4000)

    Returns:
        Same dict shape as run_claude_agent:
          {"agent": str, "ok": bool, "returncode": int, "elapsed_s": float,
           "stderr_snippet": str}
        Plus extras: cost_usd, input_tokens, output_tokens, provider="minimax".
    """
    agent_name, prompt_path, cfg = args
    start = time.monotonic()

    if agent_name not in AGENT_INPUTS:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -10,
            "elapsed_s": 0.0,
            "stderr_snippet": f"agent {agent_name!r} not in AGENT_INPUTS map "
                              f"(known: {sorted(AGENT_INPUTS)})",
            "provider": "minimax",
        }

    try:
        prompt_path = Path(prompt_path)
        full_prompt = _build_agent_prompt(agent_name, prompt_path)
    except Exception as exc:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -11,
            "elapsed_s": round(time.monotonic() - start, 2),
            "stderr_snippet": f"prompt build failed: {exc}",
            "provider": "minimax",
        }

    result = call_minimax(
        prompt=full_prompt,
        model=cfg.get("minimax_model", MINIMAX_DEFAULT_MODEL),
        system="You are a focused analytical agent. Respond with ONLY raw JSON. "
               "No preamble, no markdown fences, no commentary. Strict JSON only.",
        max_tokens=cfg.get("max_tokens", 4000),
        temperature=0.3,
        timeout=cfg.get("timeout", 120),
        task_id=f"swarm.{agent_name}",
        # stream=False (default) — minimax-m2 completes synthesis in ~21s non-streaming;
        # streaming is available in call_minimax() for future use but not needed here.
    )

    elapsed = round(time.monotonic() - start, 2)

    if not result["ok"]:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -12,
            "elapsed_s": elapsed,
            "stderr_snippet": f"minimax call failed: {result.get('error')}",
            "cost_usd": result.get("cost_usd", 0.0),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "provider": "minimax",
        }

    parsed = _extract_json(result["content"])
    if parsed is None:
        # Persist the raw content for forensic inspection
        raw_path = STATE_DIR / f"{agent_name}_minimax_raw.txt"
        try:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(result["content"] or "", encoding="utf-8")
        except Exception:
            pass
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -13,
            "elapsed_s": elapsed,
            "stderr_snippet": "json parse failed (raw saved to "
                              f"{raw_path.name}); content head: "
                              f"{(result['content'] or '')[:200]!r}",
            "cost_usd": result.get("cost_usd", 0.0),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "provider": "minimax",
        }

    # Write output file (atomic via tmp + replace)
    out_path = AGENT_OUTPUTS[agent_name]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(out_path)
    except Exception as exc:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -14,
            "elapsed_s": elapsed,
            "stderr_snippet": f"output file write failed: {exc}",
            "cost_usd": result.get("cost_usd", 0.0),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "provider": "minimax",
        }

    return {
        "agent": agent_name,
        "ok": True,
        "returncode": 0,
        "elapsed_s": elapsed,
        "stderr_snippet": "",
        "cost_usd": result.get("cost_usd", 0.0),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "provider": "minimax",
    }


if __name__ == "__main__":
    # Quick manual smoke from CLI: dispatch one agent against current swarm state
    # Example: python minimax_dispatcher.py synthesis --timeout 180
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("agent", choices=sorted(AGENT_INPUTS.keys()))
    p.add_argument("--model", default=MINIMAX_DEFAULT_MODEL)
    p.add_argument("--max-tokens", type=int, default=8000)
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()

    prompt_paths = {
        "technical":    PROMPTS_DIR / "technical_agent.md",
        "macro":        PROMPTS_DIR / "macro_agent.md",
        "level_thesis": PROMPTS_DIR / "level_thesis_agent.md",
        "internals":    PROMPTS_DIR / "internals_agent.md",
        "validator":    PROMPTS_DIR / "validator_agent.md",
        "synthesis":    PROMPTS_DIR / "synthesis_agent.md",
    }

    # Synthesis reads 6 files + writes swarm_output.json — allow more tokens
    max_tokens = args.max_tokens if args.agent != "synthesis" else max(args.max_tokens, 8000)
    out = run_minimax_agent((args.agent, prompt_paths[args.agent], {
        "minimax_model": args.model,
        "max_tokens": max_tokens,
        "timeout": args.timeout,
    }))
    print(json.dumps(out, indent=2))
    sys.exit(0 if out["ok"] else 1)
