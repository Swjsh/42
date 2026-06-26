"""Smoke-test the local Ollama floor through swarm_client's real call path.

Proves the Plan B "never goes dark" guarantee: a request routed to the local
lane actually returns. Usage:
    python setup/scripts/smoke_local_lane.py [model]   # default: qwen3:14b
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm_client as sc  # noqa: E402

model = sys.argv[1] if len(sys.argv) > 1 else "qwen3:14b"
roster = sc.load_roster()
lane = {"provider": "ollama", "model": model}
env = sc._call_lane(
    lane, "Reply with exactly one word: pong. /no_think",
    system="You are terse. Output one word.",
    max_tokens=200, temperature=0.0, timeout=120, task_id="smoke.local", roster=roster,
)
print("ok:", env.get("ok"), "| lane:", env.get("lane"), "| elapsed_s:", env.get("elapsed_s"))
print("error:", env.get("error"))
print("content:", repr((env.get("content") or "")[:400]))
sys.exit(0 if env.get("ok") and (env.get("content") or "").strip() else 1)
