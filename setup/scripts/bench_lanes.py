"""bench_lanes.py — empirical benchmark of the live free lanes. $0 (free providers).

Measures, per lane: structured-JSON reliability, a reasoning sample, and latency
for each — so we can assign the right free model to each kitchen role and stop
spending Claude on work a free model does fine.

    python setup/scripts/bench_lanes.py
Writes automation/state/lane-bench.json + prints a table.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import swarm_client as sc  # noqa: E402

LANES = [
    {"provider": "groq", "model": "llama-3.1-8b-instant"},
    {"provider": "cerebras", "model": "gpt-oss-120b"},
    {"provider": "cerebras", "model": "zai-glm-4.7"},
    {"provider": "google_aistudio", "model": "gemini-flash-lite-latest"},
    {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free"},
    {"provider": "ollama", "model": "qwen3:14b"},
]

JSON_TASK = (
    'Classify this market note. Output ONLY JSON: '
    '{"bias":"bull|bear|neutral","confidence":0.0-1.0,"reason":"<=8 words"}. '
    'Note: "SPY reclaimed the VWAP on rising volume after a morning flush."'
)
JSON_SCHEMA = {"type": "object", "required": ["bias", "confidence", "reason"],
               "properties": {"bias": {"type": "string"},
                              "confidence": {"type": "number"},
                              "reason": {"type": "string"}}}
REASON_TASK = (
    "In ONE sentence: why can a 0DTE SPY call with LOW delta still lose money "
    "even when SPY moves up in your favor?"
)


def _strip(t: str) -> str:
    t = (t or "").strip()
    if "</think>" in t:
        t = t.split("</think>")[-1].strip()
    return " ".join(t.split())


def run():
    roster = sc.load_roster()
    rows = []
    for lane in LANES:
        key = sc._lane_key(lane)
        t = time.monotonic()
        e = sc._call_lane(lane, JSON_TASK,
                          system="You are a terse market classifier. Output only JSON.",
                          max_tokens=500, temperature=0.0, timeout=90,
                          task_id="bench.json", roster=roster)
        jl = round(time.monotonic() - t, 1)
        parsed = sc.extract_json(e.get("content", "")) if e.get("ok") else None
        jok = sc.validate_json(parsed, JSON_SCHEMA)[0] if parsed is not None else False

        t = time.monotonic()
        e2 = sc._call_lane(lane, REASON_TASK,
                           system="You are a 0DTE options expert. Answer in one sentence.",
                           max_tokens=600, temperature=0.2, timeout=90,
                           task_id="bench.reason", roster=roster)
        rl = round(time.monotonic() - t, 1)
        reason = _strip(e2.get("content", "")) if e2.get("ok") else f"ERR {e2.get('error','')[:60]}"

        rows.append({"lane": key, "json_ok": jok, "json_latency_s": jl,
                     "reason_latency_s": rl, "reason_sample": reason[:260]})
        print(f"{key:46}  json_ok={str(jok):5}  jL={jl:>5}s  rL={rl:>5}s")
        print(f"    reason: {reason[:200]}")
    (sc.REPO / "automation" / "state" / "lane-bench.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8")
    fast = sorted([r for r in rows if r["json_ok"]], key=lambda r: r["json_latency_s"])
    print(f"\nJSON-reliable lanes, fastest first: {[r['lane'] for r in fast]}")
    return rows


if __name__ == "__main__":
    run()
