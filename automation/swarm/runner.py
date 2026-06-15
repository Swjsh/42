"""
Gamma Swarm Pre-Market Hypothesis Engine — orchestrator.

Fires at 06:00 ET weekdays via Gamma_SwarmPremarket scheduled task.
Produces automation/swarm/state/swarm_output.json by ~06:10 ET.
Consumed by premarket.md Step 1c at 08:30 ET as advisory context.

Architecture:
  Stage 1: data_fetcher (sequential, claude --print, needs TV+Alpaca MCP)
  Stage 2: technical + macro + level_thesis + internals (Pool(4), claude --print)
  Stage 3: validator (sequential, reads stage-2 outputs)
  Stage 4: synthesis (sequential, reads all 5 outputs, writes swarm_output.json)
"""

import multiprocessing
import subprocess
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure sibling module `minimax_dispatcher` is importable both when run as a
# script AND when spawned by multiprocessing.Pool workers on Windows.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from minimax_dispatcher import run_minimax_agent  # noqa: E402


WORK_DIR = Path(__file__).parent.parent.parent.resolve()
SWARM_DIR = Path(__file__).parent.resolve()
STATE_DIR = SWARM_DIR / "state"
PROMPTS_DIR = SWARM_DIR / "prompts"

CLAUDE_EXE = Path(r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")
EMPTY_MCP_CONFIG = Path(__file__).parent / "replay" / "empty-mcp.json"

# MCP-free stages: only data_fetcher needs TV+Alpaca MCP. Specialists + validator + synthesis
# read JSON files only. Suppressing MCP spawn for them prevents orphan alpaca-mcp-server.exe
# processes with visible console windows (4+ spawned per swarm fire = window spam).
_MCP_FREE_AGENTS = {
    "technical", "macro", "level_thesis", "internals",
    # 8 new Stage-2 specialists (all read JSON files only — no MCP needed)
    "volume_analyst", "momentum_analyst", "regime_classifier",
    "premarket_analyst", "pattern_scout", "catalyst_analyst",
    "sentiment_analyst", "correlation_analyst", "session_timer",
    # Stage-3 agents
    "validator", "risk_assessor",
    # Stage-4
    "synthesis",
}

# Per-agent budgets + provider routing.
#
# Stage 2 expanded from Pool(4) → Pool(12) per J's 2026-05-20 directive:
# "why only 4/6 swarm? why not 20 if using minimax? if we are using cheap
# model we should do a LOT of testing and theorizing with swarms."
# MiniMax M2.5 is ~5x cheaper than haiku — running 13 parallel specialists
# costs only ~3x more than 4 while tripling the hypothesis diversity.
# Stage 2 agents: 4 original (technical/macro/level_thesis/internals) +
#   8 supplemental (volume/momentum/regime/premarket/pattern/catalyst/sentiment/correlation) +
#   1 support (session_timer) = 13 total.
#
# Stage 3 expanded from sequential validator → Pool(2): validator + risk_assessor.
# This gives the CIO synthesis both a devil's advocate (validator) and an explicit
# risk assessment (risk_assessor) to weigh before writing swarm_output.json.
#
# Ratified 2026-05-20 by J: "stick to the 3" (M2 default, $5/day cap, swarm
# stages 2-5 + EOD subagents). Pool(13) stays within budget at ~$0.25/fire.
#
# NOTE: data_fetcher (Stage 1, Claude+MCP) may time out at 120s when TV MCP
# responds slowly (Claude CLI internal MCP timeout = 120s, independent of our
# subprocess timeout=180s). Fallback: uses raw_data.json from prior run (stale
# but within-session). Structural fix: move swarm from 08:10 → 08:15 ET to give
# TV more warmup time after LaunchTV at 08:00 ET. Or add pre-flight MCP health
# check in data_fetcher.md before issuing chart reads.
_MINIMAX_TESTING_MODEL = "minimax/minimax-m2.5"   # confirmed production model for specialists
# 38 confirmed calls as of 2026-05-21, all ok. Synthesis pinned to m2 (AGENT_CONFIG line below).
# Specialists stay on m2.5: cheaper ($0.15/M vs $0.255/M) + quality confirmed over 5+ swarm fires.

_MINIMAX_DEFAULT = {"provider": "minimax", "minimax_model": _MINIMAX_TESTING_MODEL, "max_tokens": 4000, "timeout": 180}

AGENT_CONFIG = {
    # Stage 1 — data fetcher (Claude, needs MCP)
    "data_fetcher":       {"provider": "claude", "model": "haiku", "budget": 0.50, "timeout": 180, "effort": "medium"},
    # Stage 2 — original 4 specialists
    "technical":          _MINIMAX_DEFAULT,
    "macro":              _MINIMAX_DEFAULT,
    "level_thesis":       _MINIMAX_DEFAULT,
    "internals":          _MINIMAX_DEFAULT,
    # Stage 2 — 8 new specialists
    "volume_analyst":     _MINIMAX_DEFAULT,
    "momentum_analyst":   _MINIMAX_DEFAULT,
    "regime_classifier":  _MINIMAX_DEFAULT,
    "premarket_analyst":  _MINIMAX_DEFAULT,
    "pattern_scout":      _MINIMAX_DEFAULT,
    "catalyst_analyst":   _MINIMAX_DEFAULT,
    "sentiment_analyst":  _MINIMAX_DEFAULT,
    "correlation_analyst": _MINIMAX_DEFAULT,
    "session_timer":      _MINIMAX_DEFAULT,
    # Stage 3 — validator (devil's advocate) + risk_assessor (parallel)
    "validator":          _MINIMAX_DEFAULT,
    "risk_assessor":      {**_MINIMAX_DEFAULT, "max_tokens": 5000},
    # Stage 4 — synthesis CIO (reads all 12 + 2 outputs)
    # Pinned to m2 (stable): completed in 21s vs m2.5 timeout. -J approved.
    "synthesis":          {"provider": "minimax", "minimax_model": "minimax/minimax-m2", "max_tokens": 8000, "timeout": 180},
}


def dispatch_agent(args: tuple) -> dict:
    """Pool-pickle-safe agent dispatcher: routes to Claude or MiniMax by `provider`.

    Each result dict has the same shape regardless of provider (agent, ok,
    returncode, elapsed_s, stderr_snippet). MiniMax results additionally carry
    cost_usd, input_tokens, output_tokens, provider="minimax".
    """
    _agent_name, _prompt_path, cfg = args
    provider = (cfg or {}).get("provider", "claude")
    if provider == "minimax":
        return run_minimax_agent(args)
    return run_claude_agent(args)


def _et_now() -> datetime:
    """Current time in US Eastern (handles EDT/EST)."""
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo("America/New_York")
        return datetime.now(tz)
    except Exception:
        # Fallback: UTC-4 (EDT approximate)
        return datetime.now(timezone.utc) - timedelta(hours=4)


def _runtime_header(agent_name: str) -> str:
    """Context header injected before each agent's prompt — mirrors _shared.ps1 pattern."""
    now_et = _et_now()
    return (
        f"# RUNTIME CONTEXT (injected by swarm runner)\n"
        f"- Current ET time: {now_et.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        f"- Today's date (ET): {now_et.strftime('%Y-%m-%d')}\n"
        f"- Weekday: {now_et.strftime('%A')}\n"
        f"- Agent: {agent_name}\n"
        f"- Working directory: {WORK_DIR}\n"
        f"\n---\n\n"
    )


def run_claude_agent(args: tuple) -> dict:
    """
    Pool-safe worker: invoke one swarm agent via claude --print.

    Must be a module-level function (not a closure) for multiprocessing.Pool
    pickling to work correctly. See OP-15: always use Pool, never ThreadPoolExecutor.
    """
    agent_name, prompt_path, cfg = args
    start = time.monotonic()

    try:
        with open(prompt_path, encoding="utf-8") as f:
            prompt_text = f.read()

        full_prompt = _runtime_header(agent_name) + prompt_text

        cmd = [
            str(CLAUDE_EXE),
            "--print",
            "--permission-mode", "bypassPermissions",
            "--model", cfg["model"],
            "--max-budget-usd", str(cfg["budget"]),
            "--effort", cfg["effort"],
            "--output-format", "text",
        ]

        # Suppress MCP servers for agents that don't need them (no more orphan windows).
        if agent_name in _MCP_FREE_AGENTS:
            cmd.extend(["--strict-mcp-config", "--mcp-config", str(EMPTY_MCP_CONFIG)])

        # CREATE_NO_WINDOW = 0x08000000 — hide any console window the subprocess might open
        creationflags = 0x08000000 if sys.platform == "win32" else 0

        proc = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=cfg["timeout"],
            cwd=str(WORK_DIR),
            creationflags=creationflags,
        )

        elapsed = round(time.monotonic() - start, 1)
        return {
            "agent": agent_name,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "elapsed_s": elapsed,
            "stderr_snippet": (proc.stderr or "")[:300],
        }

    except subprocess.TimeoutExpired:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -1,
            "elapsed_s": cfg["timeout"],
            "stderr_snippet": f"TIMEOUT after {cfg['timeout']}s",
        }
    except Exception as exc:
        return {
            "agent": agent_name,
            "ok": False,
            "returncode": -2,
            "elapsed_s": round(time.monotonic() - start, 1),
            "stderr_snippet": str(exc)[:300],
        }


def _load_agent_output(name: str, min_mtime: float | None = None) -> dict | None:
    """Read an agent's output JSON if it exists, is valid JSON, and is fresh.

    Args:
        name: agent name (e.g. "technical") — file is STATE_DIR/{name}_output.json
        min_mtime: if provided, reject the file if its modification time (seconds
                   since epoch) is OLDER than this value. Prevents stale files from
                   a prior run masking a fresh failure.
    """
    path = STATE_DIR / f"{name}_output.json"
    if not path.exists():
        return None
    if min_mtime is not None:
        try:
            if path.stat().st_mtime < min_mtime:
                return None  # stale — written before this run started
        except OSError:
            return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_failure_output(reason: str) -> None:
    """Write a minimal failure swarm_output.json so premarket.md Step 1c skips gracefully."""
    failure = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "swarm_version": "v1",
        "status": "failed",
        "failure_reason": reason,
        "consensus_bias": "no_trade",
        "swarm_confidence": 0,
        "dissent_flag": {"active": False, "dissenting_agents": [], "dissent_reason": None},
    }
    out_path = STATE_DIR / "swarm_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(failure, f, indent=2)
    print(f"[swarm] failure output written: {reason}")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[swarm {ts}] {msg}", flush=True)


def main() -> int:
    _log(f"runner.py start WORK_DIR={WORK_DIR}")
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    run_start = time.monotonic()
    run_start_wall = time.time()  # wall-clock for freshness checks vs file mtime

    # ── Stage 1: Data fetcher (sequential — needs TV+Alpaca MCP) ──────────────
    _log("stage 1: data_fetcher (TV + Alpaca) [provider=claude]")
    fetch_result = dispatch_agent((
        "data_fetcher",
        PROMPTS_DIR / "data_fetcher.md",
        AGENT_CONFIG["data_fetcher"],
    ))
    status_str = "OK" if fetch_result["ok"] else f"FAIL(rc={fetch_result['returncode']})"
    _log(f"  data_fetcher: {status_str} {fetch_result['elapsed_s']}s")
    if not fetch_result["ok"]:
        stderr_snip = fetch_result.get("stderr_snippet", "")
        if stderr_snip:
            _log(f"  data_fetcher stderr: {stderr_snip[:500]}")
        else:
            _log("  data_fetcher stderr: (empty — check if claude --print returned silent rc=1)")

    raw_data_path = STATE_DIR / "raw_data.json"
    if not raw_data_path.exists():
        _log("ERROR: raw_data.json not produced — aborting swarm run")
        _write_failure_output("data_fetcher_produced_no_raw_data")
        return 1
    if not fetch_result["ok"]:
        import time as _time
        stale_age_min = round((_time.time() - raw_data_path.stat().st_mtime) / 60, 1)
        _log(f"  WARNING: data_fetcher failed — proceeding with stale raw_data.json ({stale_age_min}min old)")

    # ── Stage 2: Parallel specialist agents (Pool 13) ─────────────────────────
    # Expanded from 4 → 13 per J's 2026-05-20 directive: MiniMax is cheap enough
    # to run many parallel hypotheses; diversity improves CIO synthesis quality.
    _STAGE2_AGENTS = [
        # Original 4
        ("technical",          PROMPTS_DIR / "technical_agent.md"),
        ("macro",              PROMPTS_DIR / "macro_agent.md"),
        ("level_thesis",       PROMPTS_DIR / "level_thesis_agent.md"),
        ("internals",          PROMPTS_DIR / "internals_agent.md"),
        # New 8
        ("volume_analyst",     PROMPTS_DIR / "volume_analyst.md"),
        ("momentum_analyst",   PROMPTS_DIR / "momentum_analyst.md"),
        ("regime_classifier",  PROMPTS_DIR / "regime_classifier.md"),
        ("premarket_analyst",  PROMPTS_DIR / "premarket_analyst.md"),
        ("pattern_scout",      PROMPTS_DIR / "pattern_scout.md"),
        ("catalyst_analyst",   PROMPTS_DIR / "catalyst_analyst.md"),
        ("sentiment_analyst",  PROMPTS_DIR / "sentiment_analyst.md"),
        ("correlation_analyst", PROMPTS_DIR / "correlation_analyst.md"),
        ("session_timer",      PROMPTS_DIR / "session_timer.md"),
    ]
    _log(f"stage 2: {len(_STAGE2_AGENTS)} parallel specialists [provider=minimax, Pool({len(_STAGE2_AGENTS)})]")
    parallel_specs = [(name, path, AGENT_CONFIG[name]) for name, path in _STAGE2_AGENTS]

    with multiprocessing.Pool(len(_STAGE2_AGENTS)) as pool:
        stage2_results = pool.map(dispatch_agent, parallel_specs)

    for r in stage2_results:
        status = "OK" if r["ok"] else f"FAIL(rc={r['returncode']})"
        cost_str = f" ${r.get('cost_usd', 0):.4f}" if "cost_usd" in r else ""
        _log(f"  {r['agent']}: {status} {r['elapsed_s']}s{cost_str}")

    # Check how many specialist agents produced FRESH output files this run.
    # Pass run_start_wall so stale files from prior runs don't mask failures.
    stage2_names = [name for name, _ in _STAGE2_AGENTS]
    specialist_outputs = [_load_agent_output(n, min_mtime=run_start_wall) for n in stage2_names]
    n_available = sum(1 for o in specialist_outputs if o is not None)
    _log(f"  specialists available: {n_available}/{len(stage2_names)}")

    if n_available == 0:
        _log("ERROR: no specialist agents produced output — aborting")
        _write_failure_output("all_specialist_agents_failed")
        return 1

    # ── Stage 3: Validator + Risk Assessor (parallel — both read stage-2 outputs) ──
    _log("stage 3: validator + risk_assessor [provider=minimax, Pool(2)]")
    stage3_specs = [
        ("validator",     PROMPTS_DIR / "validator_agent.md",    AGENT_CONFIG["validator"]),
        ("risk_assessor", PROMPTS_DIR / "risk_assessor.md",       AGENT_CONFIG["risk_assessor"]),
    ]
    with multiprocessing.Pool(2) as pool:
        stage3_results = pool.map(dispatch_agent, stage3_specs)

    v_result = next((r for r in stage3_results if r["agent"] == "validator"), stage3_results[0])
    ra_result = next((r for r in stage3_results if r["agent"] == "risk_assessor"), None)
    for r in stage3_results:
        status = "OK" if r["ok"] else f"FAIL(rc={r['returncode']})"
        _log(f"  {r['agent']}: {status} {r['elapsed_s']}s")

    # ── Stage 4: Synthesis (sequential — reads all 5 outputs) ─────────────────
    _log("stage 4: synthesis (CIO) [provider=minimax]")
    s_result = dispatch_agent((
        "synthesis",
        PROMPTS_DIR / "synthesis_agent.md",
        AGENT_CONFIG["synthesis"],
    ))
    status = "OK" if s_result["ok"] else f"FAIL(rc={s_result['returncode']})"
    _log(f"  synthesis: {status} {s_result['elapsed_s']}s")

    # ── Validate final output ──────────────────────────────────────────────────
    out_path = STATE_DIR / "swarm_output.json"
    # First check: synthesis agent must have reported ok=True (avoids stale-file false pass)
    if not s_result.get("ok"):
        _log(f"ERROR: synthesis agent failed (rc={s_result.get('returncode')}) — writing failure stub")
        _write_failure_output(f"synthesis_failed_rc_{s_result.get('returncode')}")
        return 1
    # Second check: file must exist and be fresh (written after this run started)
    if not out_path.exists():
        _log("ERROR: synthesis did not produce swarm_output.json — writing failure stub")
        _write_failure_output("synthesis_produced_no_output")
        return 1
    try:
        if out_path.stat().st_mtime < run_start_wall:
            _log("ERROR: swarm_output.json is stale (mtime < run_start) — synthesis did not update it")
            _write_failure_output("synthesis_produced_stale_output")
            return 1
    except OSError:
        pass

    try:
        with open(out_path, encoding="utf-8") as f:
            final = json.load(f)
        elapsed_total = round(time.monotonic() - run_start, 1)
        bias = final.get("consensus_bias", "?")
        confidence = final.get("swarm_confidence", "?")
        strength = final.get("consensus_strength", "?")
        _log(f"SUCCESS: bias={bias} confidence={confidence} strength={strength} total={elapsed_total}s")
    except Exception as exc:
        _log(f"ERROR: swarm_output.json exists but invalid JSON: {exc}")
        _write_failure_output(f"synthesis_output_invalid_json: {exc}")
        return 1

    _log("runner.py complete")
    return 0


if __name__ == "__main__":
    # Required for multiprocessing on Windows (spawn start method)
    multiprocessing.freeze_support()
    sys.exit(main())
