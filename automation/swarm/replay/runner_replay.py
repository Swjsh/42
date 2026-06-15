"""
Replay orchestrator for the Gamma swarm — runs stages 2-4 of the live swarm
(specialists → validator → synthesis) against synthesized historical data.

Skips Stage 1 (data_fetcher) — that's the only MCP-bound stage. Replaces it
with build_raw_data.py + build_key_levels.py + build_macro_calendar.py.

KEY DESIGN: never touches production state at automation/state/*. All replay
inputs live in automation/swarm/state/replay/{date}_{asof}/, and agents are
instructed via a runtime header to read FROM that overlay directory.

Usage:
  python runner_replay.py --date 2026-05-14 --as-of 06:00
  python runner_replay.py --date 2026-05-14 --as-of 06:00 --skip-build  # reuse cached inputs

Output:
  analysis/swarm-benchmark/replay-{date}-{asof}/
    raw_data.json
    key-levels.json
    macro-calendar.json
    technical_output.json
    macro_output.json
    level_thesis_output.json
    internals_output.json
    validator_output.json
    swarm_output.json    <-- final
    runner_summary.json  <-- meta: timings, costs, agent successes
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPLAY_DIR = Path(__file__).parent.resolve()
SWARM_DIR = REPLAY_DIR.parent
WORK_DIR = SWARM_DIR.parent.parent.resolve()
PROMPTS_DIR = SWARM_DIR / "prompts"
BENCHMARK_BASE = WORK_DIR / "analysis" / "swarm-benchmark"

CLAUDE_EXE = Path(r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")
EMPTY_MCP_CONFIG = Path(__file__).parent / "empty-mcp.json"

AGENT_CONFIG = {
    "technical":     {"model": "haiku",  "budget": 0.15, "timeout": 120, "effort": "medium"},
    "macro":         {"model": "haiku",  "budget": 0.15, "timeout": 120, "effort": "medium"},
    "level_thesis":  {"model": "haiku",  "budget": 0.10, "timeout": 90,  "effort": "low"},
    "internals":     {"model": "haiku",  "budget": 0.10, "timeout": 90,  "effort": "low"},
    "validator":     {"model": "haiku",  "budget": 0.15, "timeout": 120, "effort": "medium"},
    "synthesis":     {"model": "sonnet", "budget": 0.65, "timeout": 240, "effort": "medium"},
}


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[replay {ts}] {msg}", flush=True)


def _replay_dir(date_et: str, as_of_hhmm: str) -> Path:
    safe_asof = as_of_hhmm.replace(":", "")
    return BENCHMARK_BASE / f"replay-{date_et}-{safe_asof}"


def _build_overlay(date_et: str, as_of_hhmm: str, replay_dir: Path) -> None:
    """Stage 1 replacement: synthesize raw_data.json, key-levels.json, macro-calendar.json."""
    sys.path.insert(0, str(REPLAY_DIR))
    from build_raw_data import build_raw_data
    from build_key_levels import build_key_levels
    from build_macro_calendar import build_macro_calendar

    _log(f"building overlay in {replay_dir}")
    replay_dir.mkdir(parents=True, exist_ok=True)
    build_raw_data(date_et, as_of_hhmm, output_path=replay_dir / "raw_data.json")
    build_key_levels(date_et, as_of_hhmm, output_path=replay_dir / "key-levels.json")
    build_macro_calendar(date_et, output_path=replay_dir / "macro-calendar.json")


def _replay_header(agent_name: str, date_et: str, as_of_hhmm: str, replay_dir: Path) -> str:
    """Header injected before each agent prompt - redirects all file reads to the replay overlay."""
    replay_rel = replay_dir.relative_to(WORK_DIR).as_posix()
    if agent_name == "synthesis":
        output_filename = "swarm_output.json"
    else:
        output_filename = f"{agent_name}_output.json"
    return (
        f"# REPLAY-MODE CONTEXT (injected by runner_replay.py)\n"
        f"- This is a HISTORICAL REPLAY of date {date_et} at as-of {as_of_hhmm} ET.\n"
        f"- Replay overlay directory: {replay_rel}\n"
        f"- Current ET time (synthetic): {date_et}T{as_of_hhmm}:00\n"
        f"- Agent: {agent_name}\n"
        f"\n"
        f"# CRITICAL FILE-PATH REDIRECTIONS (override the original prompt's paths):\n"
        f"- `automation/swarm/state/raw_data.json` -> read `{replay_rel}/raw_data.json`\n"
        f"- `automation/state/key-levels.json` -> read `{replay_rel}/key-levels.json`\n"
        f"- `automation/state/macro-calendar.json` -> read `{replay_rel}/macro-calendar.json`\n"
        f"- `automation/swarm/state/technical_output.json` -> read `{replay_rel}/technical_output.json`\n"
        f"- `automation/swarm/state/macro_output.json` -> read `{replay_rel}/macro_output.json`\n"
        f"- `automation/swarm/state/level_thesis_output.json` -> read `{replay_rel}/level_thesis_output.json`\n"
        f"- `automation/swarm/state/internals_output.json` -> read `{replay_rel}/internals_output.json`\n"
        f"- `automation/swarm/state/validator_output.json` -> read `{replay_rel}/validator_output.json`\n"
        f"- `automation/swarm/state/swarm_output.json` -> WRITE to `{replay_rel}/swarm_output.json`\n"
        f"\n"
        f"# YOUR REQUIRED OUTPUT PATH (CRITICAL - the runner will fail if you write elsewhere):\n"
        f"- WRITE your output JSON to: `{replay_rel}/{output_filename}`\n"
        f"- NEVER write to or modify `automation/state/*` or `automation/swarm/state/*` directly.\n"
        f"\n---\n\n"
    )


def _run_claude_agent(args: tuple) -> dict:
    """Pool-safe worker — must be module-level for multiprocessing.Pool pickling."""
    agent_name, prompt_path, cfg, date_et, as_of_hhmm, replay_dir_str = args
    replay_dir = Path(replay_dir_str)
    start = time.monotonic()

    # Idempotency: skip if output already exists from a prior (successful) run
    output_filename_check = "swarm_output.json" if agent_name == "synthesis" else f"{agent_name}_output.json"
    existing_output = replay_dir / output_filename_check
    if existing_output.exists() and existing_output.stat().st_size > 50:
        try:
            json.loads(existing_output.read_text(encoding="utf-8"))
            return {
                "agent": agent_name, "ok": True, "wrote_output": True,
                "returncode": 0, "elapsed_s": 0.0,
                "stderr_snippet": "SKIPPED_ALREADY_EXISTS",
            }
        except Exception:
            pass  # corrupt — fall through and re-run

    try:
        with open(prompt_path, encoding="utf-8") as f:
            prompt_text = f.read()

        full_prompt = _replay_header(agent_name, date_et, as_of_hhmm, replay_dir) + prompt_text

        cmd = [
            str(CLAUDE_EXE),
            "--print",
            "--permission-mode", "bypassPermissions",
            "--model", cfg["model"],
            "--max-budget-usd", str(cfg["budget"]),
            "--effort", cfg["effort"],
            "--output-format", "text",
            # Suppress MCP server spawn — swarm agents read JSON files only, no MCP needed.
            # Prevents orphan alpaca-mcp-server.exe processes with visible console windows.
            "--strict-mcp-config",
            "--mcp-config", str(EMPTY_MCP_CONFIG),
        ]

        # CREATE_NO_WINDOW = 0x08000000 — hides any console window the subprocess opens
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
        output_filename = "swarm_output.json" if agent_name == "synthesis" else f"{agent_name}_output.json"
        wrote_file = (replay_dir / output_filename).exists()

        return {
            "agent": agent_name,
            "ok": proc.returncode == 0,
            "wrote_output": wrote_file,
            "returncode": proc.returncode,
            "elapsed_s": elapsed,
            "stderr_snippet": (proc.stderr or "")[:300],
        }

    except subprocess.TimeoutExpired:
        return {
            "agent": agent_name, "ok": False, "wrote_output": False,
            "returncode": -1, "elapsed_s": cfg["timeout"],
            "stderr_snippet": f"TIMEOUT after {cfg['timeout']}s",
        }
    except Exception as exc:
        return {
            "agent": agent_name, "ok": False, "wrote_output": False,
            "returncode": -2, "elapsed_s": round(time.monotonic() - start, 1),
            "stderr_snippet": str(exc)[:300],
        }


def run_replay(date_et: str, as_of_hhmm: str, skip_build: bool = False) -> dict:
    replay_dir = _replay_dir(date_et, as_of_hhmm)
    run_start = time.monotonic()

    if not skip_build:
        _build_overlay(date_et, as_of_hhmm, replay_dir)
    else:
        _log(f"--skip-build: reusing overlay at {replay_dir}")

    if not (replay_dir / "raw_data.json").exists():
        raise RuntimeError(f"Overlay raw_data.json missing — cannot proceed")

    # Stage 2: parallel specialists (4 agents in Pool(4))
    _log("stage 2: parallel specialists")
    parallel_specs = [
        ("technical",    PROMPTS_DIR / "technical_agent.md",    AGENT_CONFIG["technical"]),
        ("macro",        PROMPTS_DIR / "macro_agent.md",         AGENT_CONFIG["macro"]),
        ("level_thesis", PROMPTS_DIR / "level_thesis_agent.md",  AGENT_CONFIG["level_thesis"]),
        ("internals",    PROMPTS_DIR / "internals_agent.md",     AGENT_CONFIG["internals"]),
    ]
    pool_args = [(name, str(path), cfg, date_et, as_of_hhmm, str(replay_dir))
                 for (name, path, cfg) in parallel_specs]

    with multiprocessing.Pool(4) as pool:
        stage2_results = pool.map(_run_claude_agent, pool_args)

    # Retry any specialist that didn't write an output (1 retry, serial)
    retry_results = []
    for idx, r in enumerate(stage2_results):
        if r["wrote_output"]:
            continue
        _log(f"  retrying {r['agent']} (initial: rc={r['returncode']} {r['elapsed_s']}s)")
        retry_r = _run_claude_agent(pool_args[idx])
        retry_r["retry"] = True
        retry_results.append((idx, retry_r))

    for idx, retry_r in retry_results:
        stage2_results[idx] = retry_r

    n_wrote = 0
    for r in stage2_results:
        prefix = "RETRY " if r.get("retry") else ""
        status = "OK" if r["wrote_output"] else f"NO_OUTPUT(rc={r['returncode']})"
        _log(f"  {prefix}{r['agent']}: {status} {r['elapsed_s']}s")
        if r["wrote_output"]:
            n_wrote += 1
    _log(f"  specialists with output: {n_wrote}/4")

    if n_wrote == 0:
        _log("ERROR: no specialists produced output — aborting")
        return {"status": "failed", "stage_failed": "specialists", "results": stage2_results}

    # Stage 3: validator (sequential)
    _log("stage 3: validator")
    v_result = _run_claude_agent((
        "validator", str(PROMPTS_DIR / "validator_agent.md"),
        AGENT_CONFIG["validator"], date_et, as_of_hhmm, str(replay_dir),
    ))
    status = "OK" if v_result["wrote_output"] else f"NO_OUTPUT(rc={v_result['returncode']})"
    _log(f"  validator: {status} {v_result['elapsed_s']}s")

    # Stage 4: synthesis CIO (sequential, sonnet)
    _log("stage 4: synthesis CIO")
    s_result = _run_claude_agent((
        "synthesis", str(PROMPTS_DIR / "synthesis_agent.md"),
        AGENT_CONFIG["synthesis"], date_et, as_of_hhmm, str(replay_dir),
    ))
    status = "OK" if s_result["wrote_output"] else f"NO_OUTPUT(rc={s_result['returncode']})"
    _log(f"  synthesis: {status} {s_result['elapsed_s']}s")

    # Read final swarm_output.json
    final_path = replay_dir / "swarm_output.json"
    if not final_path.exists():
        _log(f"ERROR: synthesis produced no swarm_output.json at {final_path}")
        return {"status": "failed", "stage_failed": "synthesis"}

    try:
        with open(final_path, encoding="utf-8") as f:
            final = json.load(f)
    except Exception as exc:
        _log(f"ERROR: swarm_output.json invalid JSON: {exc}")
        return {"status": "failed", "stage_failed": "synthesis_json_invalid"}

    total_elapsed = round(time.monotonic() - run_start, 1)
    bias = final.get("consensus_bias", "?")
    confidence = final.get("swarm_confidence", "?")
    strength = final.get("consensus_strength", "?")

    summary = {
        "date": date_et,
        "as_of_et": as_of_hhmm,
        "replay_dir": str(replay_dir.relative_to(WORK_DIR)),
        "total_elapsed_s": total_elapsed,
        "consensus_bias": bias,
        "swarm_confidence": confidence,
        "consensus_strength": strength,
        "specialists_ok": n_wrote,
        "validator_ok": v_result["wrote_output"],
        "synthesis_ok": s_result["wrote_output"],
        "stage2_results": stage2_results,
        "stage3_result": v_result,
        "stage4_result": s_result,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(replay_dir / "runner_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    _log(f"SUCCESS: bias={bias} conf={confidence} strength={strength} total={total_elapsed}s")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the swarm against a historical date")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--as-of", default="06:00", help="As-of HH:MM ET (default 06:00)")
    parser.add_argument("--skip-build", action="store_true",
                        help="Skip Stage 1 overlay build; reuse existing files in replay dir")
    args = parser.parse_args()

    try:
        result = run_replay(args.date, args.as_of, skip_build=args.skip_build)
        return 0 if result.get("status") != "failed" else 1
    except Exception as exc:
        _log(f"FATAL: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
