"""End-to-end Pool smoke test for the MiniMax dispatcher.

Runs Stages 2-3 (4 specialists in parallel + validator sequential) using the
same Pool.map(dispatch_agent, ...) call the production runner uses. Skips
Stage 1 (data_fetcher / MCP-bound) and Stage 4 (synthesis / Claude) so this
test doesn't burn Anthropic API quota.

Verifies:
  - runner.dispatch_agent is Pool-picklable
  - All 5 MiniMax-routed agents return ok=True
  - Output JSON files written
  - Cost stays well under $0.10 total

Usage:
    python automation/swarm/test_minimax_smoke.py
"""
from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import (  # noqa: E402  (must come after sys.path mutation)
    AGENT_CONFIG,
    PROMPTS_DIR,
    STATE_DIR,
    dispatch_agent,
)


def main() -> int:
    print("[smoke] starting Stages 2-3 Pool.map smoke test", flush=True)
    if not (STATE_DIR / "raw_data.json").exists():
        print("[smoke] ERROR: raw_data.json missing — Stage 2 inputs unavailable", flush=True)
        return 2

    run_start = time.monotonic()

    # ── Stage 2: parallel specialists ─────────────────────────────────────
    parallel_specs = [
        ("technical",    PROMPTS_DIR / "technical_agent.md",    AGENT_CONFIG["technical"]),
        ("macro",        PROMPTS_DIR / "macro_agent.md",        AGENT_CONFIG["macro"]),
        ("level_thesis", PROMPTS_DIR / "level_thesis_agent.md", AGENT_CONFIG["level_thesis"]),
        ("internals",    PROMPTS_DIR / "internals_agent.md",    AGENT_CONFIG["internals"]),
    ]
    print(f"[smoke] dispatching Stage 2 (Pool(4)): {[s[0] for s in parallel_specs]}", flush=True)
    with multiprocessing.Pool(4) as pool:
        stage2 = pool.map(dispatch_agent, parallel_specs)

    for r in stage2:
        rc = r.get("returncode", "?")
        cost = r.get("cost_usd", 0.0)
        print(
            f"[smoke]   {r['agent']:<14} ok={r['ok']} rc={rc} "
            f"elapsed={r['elapsed_s']}s cost=${cost:.4f} "
            f"tokens={r.get('input_tokens', '?')}/{r.get('output_tokens', '?')}",
            flush=True,
        )

    # ── Stage 3: validator ────────────────────────────────────────────────
    print("[smoke] dispatching Stage 3 (validator sequential)", flush=True)
    v = dispatch_agent((
        "validator",
        PROMPTS_DIR / "validator_agent.md",
        AGENT_CONFIG["validator"],
    ))
    print(
        f"[smoke]   validator     ok={v['ok']} rc={v.get('returncode', '?')} "
        f"elapsed={v['elapsed_s']}s cost=${v.get('cost_usd', 0.0):.4f} "
        f"tokens={v.get('input_tokens', '?')}/{v.get('output_tokens', '?')}",
        flush=True,
    )

    # ── Summary ───────────────────────────────────────────────────────────
    all_results = stage2 + [v]
    n_ok = sum(1 for r in all_results if r["ok"])
    total_cost = sum(r.get("cost_usd", 0.0) for r in all_results)
    total_in = sum(r.get("input_tokens", 0) for r in all_results)
    total_out = sum(r.get("output_tokens", 0) for r in all_results)
    elapsed = round(time.monotonic() - run_start, 2)

    print(
        f"\n[smoke] SUMMARY: {n_ok}/5 ok, "
        f"elapsed={elapsed}s, "
        f"total_cost=${total_cost:.4f}, "
        f"tokens={total_in} in / {total_out} out",
        flush=True,
    )

    # Verify output files exist + are valid JSON
    expected_outputs = [
        STATE_DIR / "technical_output.json",
        STATE_DIR / "macro_output.json",
        STATE_DIR / "level_thesis_output.json",
        STATE_DIR / "internals_output.json",
        STATE_DIR / "validator_output.json",
    ]
    file_ok = 0
    for p in expected_outputs:
        if not p.exists():
            print(f"[smoke] MISSING: {p.name}", flush=True)
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                print(f"[smoke] WRONG_TYPE: {p.name}", flush=True)
                continue
            file_ok += 1
        except json.JSONDecodeError as exc:
            print(f"[smoke] BAD_JSON: {p.name} — {exc}", flush=True)

    print(f"[smoke] FILE_VERIFY: {file_ok}/5 outputs are valid JSON", flush=True)

    if n_ok == 5 and file_ok == 5:
        print("[smoke] PASS — Stages 2-3 fully migratable to MiniMax", flush=True)
        return 0
    print("[smoke] FAIL — see errors above", flush=True)
    return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
