"""swarm_client.py — lane-pool client for the free swarm kitchen (Plan B, Phase 0).

Routes the OpenAI-compatible chat API across MULTIPLE independent free providers
plus a LOCAL Ollama floor, resolved per ROLE from automation/state/model-roster.json.

Why this exists (markdown/planning/FREE-AGENT-PLAN-B-KITCHEN.md sec 7):
  * Never goes dark — every role's lane list ends in the local Ollama floor
    (no quota, no ToS, no rate limit). The kitchen can't be fully blocked.
  * Privacy routing — privacy=sensitive roles never touch a trains_on_input lane
    (Gemini/Mistral free train on inputs); they fall back to no-train lanes or local.
  * Quota-aware — per-lane 429 cooldown (in-memory) skips cooling lanes, like
    kitchen_daemon's per-tier cooldowns; cross-provider failover on error.
  * JSON mode — call_role_json validates against a schema, one repair-retry then
    failover to the next lane.
  * Telemetry — every call appended to automation/state/swarm-calls.jsonl.

HARD CONSTRAINTS (Plan B): never places orders, never touches heartbeat*.md /
params*.json / CLAUDE.md. Observer/infra only — ships without ratification (OP-25).

This module reuses the OpenAI SDK + telemetry pattern from run_minimax.py but
generalizes base_url + api_key per provider (run_minimax hardcodes OpenRouter).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
ROSTER_FILE = REPO / "automation" / "state" / "model-roster.json"
TELEMETRY_FILE = REPO / "automation" / "state" / "swarm-calls.jsonl"

TIER_429_COOLDOWN_S = 300.0   # cool a lane for 5 min after a 429 (matches kitchen_daemon D4)
DEFAULT_TIMEOUT_S = 120
REMOTE_TIMEOUT_S = 45         # cap remote-lane wait so a throttled/hung cloud lane fails over fast to local
DEFAULT_MAX_TOKENS = 4000

# ────────────────────────────────────────────────────────────────────────────
# Lane health (in-memory per-lane cooldown) — mirrors kitchen_daemon._TIER_429
# ────────────────────────────────────────────────────────────────────────────

_LANE_COOLDOWN_UNTIL: dict[str, float] = {}   # lane_key -> monotonic time it recovers
_LANE_LOCK = threading.Lock()


def _lane_key(lane: dict) -> str:
    return f"{lane.get('provider')}::{lane.get('model')}"


def _cool_lane(lane: dict, seconds: float = TIER_429_COOLDOWN_S) -> None:
    with _LANE_LOCK:
        _LANE_COOLDOWN_UNTIL[_lane_key(lane)] = time.monotonic() + seconds


def _lane_is_cooling(lane: dict) -> bool:
    with _LANE_LOCK:
        until = _LANE_COOLDOWN_UNTIL.get(_lane_key(lane), 0.0)
    return until > time.monotonic()


# ────────────────────────────────────────────────────────────────────────────
# Roster + provider config
# ────────────────────────────────────────────────────────────────────────────

_ROSTER_CACHE: Optional[dict] = None


def load_roster(*, force: bool = False) -> dict:
    """Load + cache model-roster.json. Raises FileNotFoundError if missing."""
    global _ROSTER_CACHE
    if _ROSTER_CACHE is not None and not force:
        return _ROSTER_CACHE
    if not ROSTER_FILE.exists():
        raise FileNotFoundError(f"model-roster.json missing at {ROSTER_FILE}")
    _ROSTER_CACHE = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
    return _ROSTER_CACHE


def provider_cfg(provider: str, roster: Optional[dict] = None) -> dict:
    roster = roster or load_roster()
    cfg = (roster.get("providers") or {}).get(provider)
    if not cfg:
        raise KeyError(f"provider {provider!r} not in roster.providers")
    return cfg


def resolve_lanes(role: str, roster: Optional[dict] = None) -> list[dict]:
    """Return the ordered lanes for a role, with the privacy filter applied.

    A privacy=sensitive role drops any lane whose provider trains on input
    (Gemini/Mistral free). The local Ollama floor (trains_on_input=false) always
    survives, so a sensitive role is never left without a lane.
    """
    roster = roster or load_roster()
    role_cfg = (roster.get("roles") or {}).get(role)
    if not role_cfg:
        raise KeyError(f"role {role!r} not in roster.roles")
    lanes = list(role_cfg.get("lanes") or [])
    if role_cfg.get("privacy") == "sensitive":
        kept = []
        for lane in lanes:
            try:
                trains = bool(provider_cfg(lane["provider"], roster).get("trains_on_input"))
            except KeyError:
                trains = True  # unknown provider => treat as unsafe, drop it
            if not trains:
                kept.append(lane)
        lanes = kept
    if not lanes:
        # Safety net: a sensitive role with every lane filtered still gets the floor.
        floor = roster.get("local_floor")
        if floor:
            lanes = [floor]
    return lanes


def effective_lanes(role: str, roster: Optional[dict] = None) -> list[dict]:
    """resolve_lanes minus any lane currently in 429 cooldown (keeps order)."""
    lanes = resolve_lanes(role, roster)
    live = [ln for ln in lanes if not _lane_is_cooling(ln)]
    # Never return empty: if everything is cooling, fall through to the floor anyway
    # (the floor is local + un-rate-limited, so cooling it is almost never right).
    return live or lanes


def _load_key(provider: str, roster: Optional[dict] = None) -> Optional[str]:
    """Read a provider's API key. ollama needs none. Env override per provider."""
    cfg = provider_cfg(provider, roster)
    env_name = f"{provider.upper()}_API_KEY"
    env_key = os.environ.get(env_name, "").strip()
    if env_key:
        return env_key
    key_file = cfg.get("key_file")
    if not key_file:
        return None  # e.g. ollama
    path = REPO / key_file
    if not path.exists():
        return None
    txt = path.read_text(encoding="utf-8").strip()
    return txt.splitlines()[0].strip() if txt else None


# ────────────────────────────────────────────────────────────────────────────
# Telemetry
# ────────────────────────────────────────────────────────────────────────────


def _log_call(entry: dict) -> None:
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
    except OSError:
        pass


# ────────────────────────────────────────────────────────────────────────────
# JSON helpers (no external dependency — lightweight validator)
# ────────────────────────────────────────────────────────────────────────────


def extract_json(text: str) -> Optional[Any]:
    """Pull the first JSON value out of a model response.

    Strips ```fences and <think>...</think> reasoning blocks first, then parses
    the largest brace/bracket span. Returns the parsed object or None.
    """
    if not text:
        return None
    s = text
    # Drop reasoning traces (DeepSeek-R1 etc.)
    end = s.rfind("</think>")
    if end != -1:
        s = s[end + len("</think>"):]
    s = s.strip()
    # Strip a leading code fence
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Fall back to the widest {...} or [...] span
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = s.find(open_c), s.rfind(close_c)
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


_TYPE_MAP = {
    "string": str, "number": (int, float), "integer": int,
    "boolean": bool, "object": dict, "array": list,
}


def validate_json(obj: Any, schema: dict) -> tuple[bool, list[str]]:
    """Minimal JSON-Schema check: top-level type + required keys + property types.

    Deliberately dependency-free (no jsonschema). Good enough to gate a model's
    structured output and decide repair-or-failover; not a full validator.
    """
    errors: list[str] = []
    stype = schema.get("type")
    if stype and stype in _TYPE_MAP and not isinstance(obj, _TYPE_MAP[stype]):
        # bool is an int subclass — guard the common integer/number case
        if not (stype in ("number", "integer") and isinstance(obj, bool)):
            return False, [f"top-level type != {stype}"]
    if isinstance(obj, dict):
        for key in schema.get("required", []):
            if key not in obj:
                errors.append(f"missing required key: {key}")
        props = schema.get("properties", {})
        for key, spec in props.items():
            if key in obj and obj[key] is not None:
                t = spec.get("type")
                if t in _TYPE_MAP and not isinstance(obj[key], _TYPE_MAP[t]):
                    if not (t in ("number", "integer") and isinstance(obj[key], bool) is False
                            and isinstance(obj[key], (int, float))):
                        errors.append(f"key {key}: expected {t}")
    return (len(errors) == 0), errors


# ────────────────────────────────────────────────────────────────────────────
# The call path
# ────────────────────────────────────────────────────────────────────────────


def _call_lane(
    lane: dict,
    prompt: str,
    *,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
    timeout: int,
    task_id: str,
    roster: dict,
    remote_timeout: float = REMOTE_TIMEOUT_S,
) -> dict:
    """One lane attempt. Returns an envelope: ok/content/lane/error/elapsed_s."""
    provider = lane["provider"]
    model = lane["model"]
    start = time.monotonic()
    base_url = lane.get("base_url") or provider_cfg(provider, roster).get("base_url")
    api_key = _load_key(provider, roster) or "x-no-key"  # ollama accepts any

    try:
        from openai import OpenAI
    except ImportError as exc:
        return {"ok": False, "lane": _lane_key(lane), "content": "",
                "error": f"openai_sdk_missing: {exc}", "elapsed_s": 0.0}

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        # Cap remote lanes at REMOTE_TIMEOUT_S so a throttled/hung cloud lane fails
        # over fast to the local floor; keep the caller's longer budget for ollama.
        # max_retries=0: swarm_client owns all retry/failover — no hidden SDK backoff.
        eff_timeout = float(timeout) if provider == "ollama" else min(float(timeout), remote_timeout)
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=eff_timeout, max_retries=0)
        resp = client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        elapsed = round(time.monotonic() - start, 3)
        env = {"ok": True, "lane": _lane_key(lane), "provider": provider,
               "model": model, "content": content, "input_tokens": in_tok,
               "output_tokens": out_tok, "elapsed_s": elapsed, "error": None}
    except Exception as exc:  # noqa: BLE001 — never raise; envelope carries the error
        elapsed = round(time.monotonic() - start, 3)
        err = f"{type(exc).__name__}: {str(exc)[:300]}"
        if "429" in err or "rate" in err.lower() or "quota" in err.lower():
            _cool_lane(lane)
        env = {"ok": False, "lane": _lane_key(lane), "provider": provider,
               "model": model, "content": "", "elapsed_s": elapsed, "error": err}

    _log_call({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "task_id": task_id, **{k: env.get(k) for k in
               ("lane", "ok", "input_tokens", "output_tokens", "elapsed_s", "error")}})
    return env


def call_role(
    role: str,
    prompt: str,
    *,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.3,
    timeout: int = DEFAULT_TIMEOUT_S,
    task_id: str = "swarm.adhoc",
    remote_timeout: float = REMOTE_TIMEOUT_S,
) -> dict:
    """Try each effective lane for the role in order; first success wins.

    Always ends at the local floor, so a return with ok=False means even local
    failed (e.g. Ollama not running) — that is the only true "dark" condition.

    remote_timeout caps how long a cloud lane may take before failover; raise it
    for long generations (e.g. kitchen cooks), keep it low for quick calls.
    """
    roster = load_roster()
    lanes = effective_lanes(role, roster)
    last = {"ok": False, "error": "no_lanes_resolved", "lane": None, "content": ""}
    for lane in lanes:
        env = _call_lane(lane, prompt, system=system, max_tokens=max_tokens,
                         temperature=temperature, timeout=timeout,
                         task_id=f"{task_id}.{role}", roster=roster,
                         remote_timeout=remote_timeout)
        if env.get("ok") and (env.get("content") or "").strip():
            return env
        last = env
    return last


def call_role_json(
    role: str,
    prompt: str,
    schema: dict,
    *,
    system: Optional[str] = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.2,
    timeout: int = DEFAULT_TIMEOUT_S,
    task_id: str = "swarm.json",
) -> tuple[dict, Optional[Any]]:
    """call_role + JSON extraction + schema validation, with one repair-retry.

    Returns (envelope, parsed_obj_or_None). On a parse/validation miss, retries
    the SAME lane once with a terse repair instruction; still failing, the outer
    call_role loop would already have moved on. Caller checks parsed is not None.
    """
    sys_json = (system or "") + (
        "\n\nOUTPUT: a single valid JSON value matching the requested schema. "
        "No prose, no markdown fences, no reasoning outside the JSON."
    )
    env = call_role(role, prompt, system=sys_json, max_tokens=max_tokens,
                    temperature=temperature, timeout=timeout, task_id=task_id)
    parsed = extract_json(env.get("content", "")) if env.get("ok") else None
    ok, errs = validate_json(parsed, schema) if parsed is not None else (False, ["no JSON"])
    if not ok:
        repair = (
            f"{prompt}\n\nYour previous output did not satisfy the schema "
            f"({'; '.join(errs)[:200]}). Return ONLY corrected JSON."
        )
        env = call_role(role, repair, system=sys_json, max_tokens=max_tokens,
                        temperature=temperature, timeout=timeout,
                        task_id=f"{task_id}.repair")
        parsed = extract_json(env.get("content", "")) if env.get("ok") else None
        ok, _ = validate_json(parsed, schema) if parsed is not None else (False, [])
    return env, (parsed if ok else None)


# ────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ────────────────────────────────────────────────────────────────────────────


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Lane-pool swarm client smoke test")
    p.add_argument("--role", default="coordinator")
    p.add_argument("--prompt", default="Reply with the single word: pong")
    p.add_argument("--lanes", action="store_true", help="Print resolved lanes for the role and exit")
    args = p.parse_args()

    if args.lanes:
        for i, ln in enumerate(resolve_lanes(args.role)):
            cooling = " (cooling)" if _lane_is_cooling(ln) else ""
            print(f"  {i}. {_lane_key(ln)}{cooling}")
        return 0

    env = call_role(args.role, args.prompt, task_id="cli.smoke")
    print(json.dumps({k: env.get(k) for k in ("ok", "lane", "elapsed_s", "error")}, indent=2))
    if env.get("ok"):
        print("---\n" + (env.get("content") or "")[:500])
    return 0 if env.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
