"""MiniMax-via-OpenRouter client for Project Gamma.

Library + CLI interface. Routes non-critical autonomous work (swarm specialists,
EOD subagents, wake-fire heavy lifts) to MiniMax M2 at ~1/15 the cost of Sonnet.

PER CLAUDE.md OP-25 ENGINE-BENEFIT AUTONOMY: this is observer/infrastructure
work that does NOT modify live trading doctrine. Ships without ratification.

Hard guarantees enforced by this module:
  1. Daily $5 spend cap (configurable; refuses calls once exceeded).
  2. Every call written to automation/state/minimax-calls.jsonl (telemetry).
  3. Daily cap breach raises a BROKEN flag in automation/overnight/STATUS.md.
  4. NEVER touches heartbeat.md / params*.json / live order paths.
  5. Falls back to Claude path on persistent MiniMax failure (callers decide).

Library usage:
    from setup.scripts.run_minimax import call_minimax
    result = call_minimax(
        prompt="...",
        system="...",
        model="minimax/minimax-m2",
        max_tokens=4000,
        task_id="swarm.technical",
    )
    if result["ok"]:
        text = result["content"]

CLI usage:
    python setup/scripts/run_minimax.py --prompt "..." [--system "..."]
    echo "prompt body" | python setup/scripts/run_minimax.py --stdin
    python setup/scripts/run_minimax.py --prompt "..." --json  # full envelope
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[2]
KEY_FILE = REPO / "automation" / "state" / ".openrouter.key"
TELEMETRY_FILE = REPO / "automation" / "state" / "minimax-calls.jsonl"
STATUS_FILE = REPO / "automation" / "overnight" / "STATUS.md"

# ────────────────────────────────────────────────────────────────────────────
# Policy + model catalog (CLAUDE.md OP-3 cost discipline + OP-20 telemetry)
# ────────────────────────────────────────────────────────────────────────────

DAILY_CAP_USD: float = 5.00
ALERT_THRESHOLD_USD: float = 4.00
DEFAULT_MODEL: str = "minimax/minimax-m2.5"  # confirmed production model for specialists + EOD fallback (38 confirmed calls, all ok 2026-05-21)
TIMEOUT_DEFAULT_S: int = 120

# OpenRouter pricing in USD per token (verified 2026-05-20 via WebFetch).
# Update when OpenRouter publishes new tiers.
#
# FREE-TIER MODELS (cost=0 per OpenRouter Models API 2026-05-20):
#   * nvidia/nemotron-3-super-120b-a12b:free  -- 120B MoE / 12B active, 1M ctx, AGENTIC PRIMARY
#   * minimax/minimax-m2.5:free               -- 204K ctx, MiniMax mid-tier free variant
#   * deepseek/deepseek-v4-flash:free         -- 1M ctx, coding-focused
#   * qwen/qwen3-coder:free                   -- 1M ctx, coding-focused
#   * meta-llama/llama-3.3-70b-instruct:free  -- 131K ctx, general
# Free tier is rate-limited (not $-capped), so callers should fallback gracefully
# on 429. Pricing entries are 0/0; daily $-cap logic does not apply.
PRICING: dict[str, dict[str, float]] = {
    "minimax/minimax-m2":   {"input": 0.255 / 1_000_000, "output": 1.00 / 1_000_000},
    "minimax/minimax-m2.5": {"input": 0.15  / 1_000_000, "output": 1.15 / 1_000_000},
    "minimax/minimax-m2.7": {"input": 0.279 / 1_000_000, "output": 1.20 / 1_000_000},
    "nvidia/nemotron-3-super-120b-a12b:free":   {"input": 0.0, "output": 0.0},
    "nvidia/nemotron-3-nano-30b-a3b:free":      {"input": 0.0, "output": 0.0},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": {"input": 0.0, "output": 0.0},
    "minimax/minimax-m2.5:free":                {"input": 0.0, "output": 0.0},
    "deepseek/deepseek-v4-flash:free":          {"input": 0.0, "output": 0.0},
    "qwen/qwen3-coder:free":                    {"input": 0.0, "output": 0.0},
    "meta-llama/llama-3.3-70b-instruct:free":   {"input": 0.0, "output": 0.0},
}


def _is_free_model(model: str) -> bool:
    """Free-tier models end with ':free' on OpenRouter. Cost=0, rate-limited."""
    return bool(model) and model.lower().endswith(":free")

# ────────────────────────────────────────────────────────────────────────────
# Logging (stderr only — stdout is the call result in CLI mode)
# ────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("run_minimax")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s minimax %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ────────────────────────────────────────────────────────────────────────────
# Result envelope (typed)
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MiniMaxResult:
    ok: bool
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    elapsed_s: float
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "content": self.content,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
        }


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _load_api_key() -> str:
    """Read OpenRouter key from KEY_FILE. Raise FileNotFoundError if missing,
    ValueError if it doesn't look like an OpenRouter key.

    Env var override: OPENROUTER_API_KEY (takes precedence — useful for CI smoke).
    """
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key
    if not KEY_FILE.exists():
        raise FileNotFoundError(
            f"OpenRouter key missing at {KEY_FILE}. "
            "Paste your key (single line, no quotes) into this file. "
            "See markdown/infra/MINIMAX-INTEGRATION.md."
        )
    key = KEY_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    if not key:
        raise ValueError(f"OpenRouter key file at {KEY_FILE} is empty")
    if not key.startswith("sk-or-"):
        raise ValueError(
            f"OpenRouter key at {KEY_FILE} doesn't start with 'sk-or-' — "
            "verify you pasted an OpenRouter key (not an Anthropic/OpenAI/MiniMax-direct one)"
        )
    return key


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _today_spend_usd() -> float:
    """Sum cost_usd for today's telemetry rows (UTC date)."""
    if not TELEMETRY_FILE.exists():
        return 0.0
    today = _today_iso()
    total = 0.0
    try:
        with open(TELEMETRY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("ts", "")
                if isinstance(ts, str) and ts[:10] == today:
                    total += float(entry.get("cost_usd", 0.0) or 0.0)
    except OSError:
        return 0.0
    return round(total, 6)


def _log_call(entry: dict) -> None:
    """Append a single JSONL row to telemetry. Best-effort — never raises."""
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("telemetry write failed: %s", exc)


def _alert_status_md(severity: str, msg: str) -> None:
    """Append a BROKEN or WARN flag to STATUS.md. Best-effort — never raises."""
    try:
        if not STATUS_FILE.parent.exists():
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        flag = "BROKEN" if severity == "BROKEN" else "WARN"
        body = f"\n### {flag}: minimax-{msg}\n- ts: {ts}\n- detail: {msg}\n- source: run_minimax.py\n"
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write(body)
    except Exception as exc:
        logger.warning("status_md write failed: %s", exc)


def _estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    pricing = PRICING.get(model)
    if not pricing:
        # Unknown model: charge as M2 (conservative default). Telemetry flags it.
        pricing = PRICING[DEFAULT_MODEL]
    return round(in_tokens * pricing["input"] + out_tokens * pricing["output"], 6)


# ────────────────────────────────────────────────────────────────────────────
# Main entry
# ────────────────────────────────────────────────────────────────────────────


def call_minimax(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    system: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    timeout: int = TIMEOUT_DEFAULT_S,
    task_id: str = "ad_hoc",
    enforce_cap: bool = True,
    stream: bool = False,
) -> dict:
    """Call MiniMax via OpenRouter. Returns a dict envelope (see MiniMaxResult).

    Never raises. On any failure, returns ok=False with `error` populated.

    Args:
        prompt: user-turn content (required, non-empty)
        model: full OpenRouter slug, e.g. "minimax/minimax-m2"
        system: optional system message
        max_tokens: hard upper bound on response tokens
        temperature: 0.0-2.0
        timeout: seconds before SDK aborts the request
        task_id: free-form tag stored in telemetry (e.g. "swarm.technical")
        enforce_cap: if True, refuses calls once today's spend ≥ DAILY_CAP_USD
        stream: if True, use SSE streaming to avoid OpenRouter's ~120s non-streaming
                server-side timeout on large completions (e.g. synthesis with 2500+ tokens).
                Streaming keeps the connection alive between chunks instead of waiting for
                the full response body.
    """
    start = time.monotonic()

    if not prompt or not prompt.strip():
        return MiniMaxResult(
            ok=False, content="", model=model, input_tokens=0, output_tokens=0,
            cost_usd=0.0, elapsed_s=0.0, error="empty_prompt",
        ).to_dict()

    # Lazy import so smoke tests of cap logic don't require the SDK.
    try:
        from openai import OpenAI
    except ImportError as exc:
        return MiniMaxResult(
            ok=False, content="", model=model, input_tokens=0, output_tokens=0,
            cost_usd=0.0, elapsed_s=round(time.monotonic() - start, 3),
            error=f"openai_sdk_missing: {exc}",
        ).to_dict()

    # Daily cap check -- skip entirely for free-tier models (rate-limited, not $-capped)
    if enforce_cap and not _is_free_model(model):
        spent = _today_spend_usd()
        if spent >= DAILY_CAP_USD:
            _alert_status_md("BROKEN", f"daily-cap-exhausted ${spent:.2f} >= ${DAILY_CAP_USD:.2f}")
            return MiniMaxResult(
                ok=False, content="", model=model, input_tokens=0, output_tokens=0,
                cost_usd=0.0, elapsed_s=round(time.monotonic() - start, 3),
                error=f"daily_cap_exhausted: ${spent:.2f} >= ${DAILY_CAP_USD:.2f}",
            ).to_dict()

    # Auth
    try:
        api_key = _load_api_key()
    except (FileNotFoundError, ValueError) as exc:
        _alert_status_md("BROKEN", f"auth-failed: {exc}")
        return MiniMaxResult(
            ok=False, content="", model=model, input_tokens=0, output_tokens=0,
            cost_usd=0.0, elapsed_s=round(time.monotonic() - start, 3), error=str(exc),
        ).to_dict()

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/jackwatergun/project-gamma",
            "X-Title": "Project Gamma",
        },
        timeout=float(timeout),
    )

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if stream:
        # ── Streaming path: accumulate SSE chunks ──────────────────────────────
        # Avoids OpenRouter's ~120s non-streaming server-side timeout.  Each chunk
        # resets the per-chunk idle timer; total generation time is not bounded.
        content_parts: list[str] = []
        in_tokens = 0
        out_tokens = 0
        finish_reason_val: Optional[str] = None

        try:
            with client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            ) as stream_resp:
                for chunk in stream_resp:
                    if chunk.choices:
                        delta_content = chunk.choices[0].delta.content
                        if delta_content:
                            content_parts.append(delta_content)
                        if chunk.choices[0].finish_reason:
                            finish_reason_val = chunk.choices[0].finish_reason
                    # Usage reported in last chunk (OpenRouter includes it)
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                        out_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        except Exception as exc:
            elapsed = round(time.monotonic() - start, 3)
            err = f"{type(exc).__name__}: {str(exc)[:300]}"
            _log_call({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "task_id": task_id, "model": model, "ok": False,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "elapsed_s": elapsed, "error": err,
            })
            return MiniMaxResult(
                ok=False, content="", model=model, input_tokens=0, output_tokens=0,
                cost_usd=0.0, elapsed_s=elapsed, error=err,
            ).to_dict()

        elapsed = round(time.monotonic() - start, 3)
        content = "".join(content_parts)
        # If usage wasn't reported in streaming chunks, estimate from content length
        if out_tokens == 0:
            out_tokens = max(1, len(content) // 4)
        cost = _estimate_cost(model, in_tokens, out_tokens)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task_id": task_id, "model": model,
            "input_tokens": in_tokens, "output_tokens": out_tokens,
            "cost_usd": cost, "elapsed_s": elapsed,
            "ok": True, "finish_reason": finish_reason_val, "streamed": True,
        }
        _log_call(entry)
        if enforce_cap:
            prior = _today_spend_usd() - cost
            if prior < ALERT_THRESHOLD_USD <= prior + cost:
                _alert_status_md("WARN", f"approaching-daily-cap ${prior + cost:.2f} of ${DAILY_CAP_USD:.2f}")
        return MiniMaxResult(
            ok=True, content=content, model=model,
            input_tokens=in_tokens, output_tokens=out_tokens,
            cost_usd=cost, elapsed_s=elapsed, error=None,
        ).to_dict()

    # ── Non-streaming path (default) ───────────────────────────────────────────
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        err = f"{type(exc).__name__}: {str(exc)[:300]}"
        _log_call({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task_id": task_id, "model": model, "ok": False,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "elapsed_s": elapsed, "error": err,
        })
        return MiniMaxResult(
            ok=False, content="", model=model, input_tokens=0, output_tokens=0,
            cost_usd=0.0, elapsed_s=elapsed, error=err,
        ).to_dict()

    elapsed = round(time.monotonic() - start, 3)
    content = (resp.choices[0].message.content or "") if resp.choices else ""
    usage = getattr(resp, "usage", None)
    in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    out_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    cost = _estimate_cost(model, in_tokens, out_tokens)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_id": task_id,
        "model": model,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": cost,
        "elapsed_s": elapsed,
        "ok": True,
        "finish_reason": getattr(resp.choices[0], "finish_reason", None) if resp.choices else None,
    }
    _log_call(entry)

    # Cap alerting (only on the crossing, not every call past threshold)
    if enforce_cap:
        prior = _today_spend_usd() - cost  # already includes this call
        if prior < ALERT_THRESHOLD_USD <= prior + cost:
            _alert_status_md("WARN", f"approaching-daily-cap ${prior + cost:.2f} of ${DAILY_CAP_USD:.2f}")

    return MiniMaxResult(
        ok=True, content=content, model=model,
        input_tokens=in_tokens, output_tokens=out_tokens,
        cost_usd=cost, elapsed_s=elapsed, error=None,
    ).to_dict()


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description="MiniMax-via-OpenRouter client for Project Gamma.")
    p.add_argument("--prompt", help="Prompt text (mutually exclusive with --stdin)")
    p.add_argument("--prompt-file", help="Path to prompt text file (mutually exclusive with --prompt / --stdin)")
    p.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    p.add_argument("--system", default=None, help="Optional system message")
    p.add_argument("--system-file", default=None, help="Path to file containing system message")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter slug (default: {DEFAULT_MODEL})")
    p.add_argument("--max-tokens", type=int, default=4000)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--timeout", type=int, default=TIMEOUT_DEFAULT_S)
    p.add_argument("--task-id", default="cli")
    p.add_argument("--json", action="store_true", help="Output full JSON envelope (default: bare content)")
    p.add_argument("--no-cap", action="store_true", help="Disable daily cap (debug only)")
    p.add_argument("--check-status", action="store_true", help="Print today's spend + cap and exit")
    args = p.parse_args()

    if args.check_status:
        spent = _today_spend_usd()
        print(json.dumps({
            "date_utc": _today_iso(),
            "spent_usd": spent,
            "cap_usd": DAILY_CAP_USD,
            "remaining_usd": round(DAILY_CAP_USD - spent, 4),
            "alert_threshold_usd": ALERT_THRESHOLD_USD,
            "telemetry_file": str(TELEMETRY_FILE),
        }, indent=2))
        return 0

    # Resolve prompt source
    inputs_chosen = sum(bool(x) for x in (args.prompt, args.stdin, args.prompt_file))
    if inputs_chosen != 1:
        print("ERROR: exactly one of --prompt / --prompt-file / --stdin required", file=sys.stderr)
        return 2

    if args.stdin:
        prompt = sys.stdin.read()
    elif args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = args.prompt

    system: Optional[str] = args.system
    if args.system_file:
        system = Path(args.system_file).read_text(encoding="utf-8")

    result = call_minimax(
        prompt=prompt,
        model=args.model,
        system=system,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        timeout=args.timeout,
        task_id=args.task_id,
        enforce_cap=not args.no_cap,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["ok"]:
            print(result["content"])
        else:
            print(f"ERROR: {result['error']}", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())
