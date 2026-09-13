"""station_planner_bench.py -- measure a local Ollama model the way the Station will use it.

For each (num_ctx, prompt_tokens) pair: one /api/generate call with a real repo document as the
prompt body and a question that can only be answered by reading it. Records prompt-eval and
generation tok/s straight from Ollama's own timing fields (never a stopwatch around the HTTP
call), the load time, the CPU/GPU split reported by `ollama ps`, and whether the answer named
the expected fact. Writes automation/state/station/planner-bench.json (append-only history list)
and prints one summary line per run. Stdlib only, $0.

Usage:
  python setup/scripts/station_planner_bench.py --model gamma-planner
  python setup/scripts/station_planner_bench.py --model gamma-planner --pairs 16384:2000,32768:14000
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "automation" / "state" / "station" / "planner-bench.json"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
DOC = ROOT / "CLAUDE.md"
QUESTION = ("\n\nQUESTION: Using only the document above, what are the two daily loss kill-switch percentages "
            "(Rule 5) for Gamma-Safe and Gamma-Bold? Answer in one short line.")
EXPECT = ("30", "50")


def et_now() -> str:
    try:
        out = subprocess.run([sys.executable, str(ROOT / "setup/scripts/et_clock.py")],
                             capture_output=True, text=True, timeout=20).stdout
        return out.strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"et_clock failed: {exc}"


def build_prompt(target_tokens: int) -> str:
    text = DOC.read_text(encoding="utf-8", errors="replace")
    # ~4 chars per token is the usual English/markdown ratio; pad by repeating the doc with a marker
    body = text
    while len(body) < target_tokens * 4:
        body += "\n\n<!-- repeated for benchmark padding -->\n\n" + text
    return body[: target_tokens * 4] + QUESTION


def ollama_ps() -> str:
    try:
        return subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"ollama ps failed: {exc}"


def generate(model: str, prompt: str, num_ctx: int, num_predict: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0.2},
    }
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_pair(model: str, num_ctx: int, prompt_tokens: int, num_predict: int) -> dict:
    prompt = build_prompt(prompt_tokens)
    t0 = time.time()
    r = generate(model, prompt, num_ctx, num_predict)
    wall = time.time() - t0
    pe_n, pe_d = r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 0)
    ev_n, ev_d = r.get("eval_count", 0), r.get("eval_duration", 0)
    answer = (r.get("response") or "").strip()
    ps = ollama_ps()
    split = re.search(r"(\d+%/\d+% CPU/GPU|100% GPU|100% CPU)", ps)
    size = re.search(r"\s(\d+(?:\.\d+)?\s?GB)\s", ps)
    return {
        "num_ctx": num_ctx,
        "prompt_tokens_target": prompt_tokens,
        "prompt_tokens_actual": pe_n,
        "prompt_tok_per_s": round(pe_n / (pe_d / 1e9), 1) if pe_d else None,
        "gen_tokens": ev_n,
        "gen_tok_per_s": round(ev_n / (ev_d / 1e9), 1) if ev_d else None,
        "load_s": round(r.get("load_duration", 0) / 1e9, 1),
        "wall_s": round(wall, 1),
        "processor_split": split.group(1) if split else ps[-120:],
        "resident_size": size.group(1) if size else None,
        "answer": answer[:300],
        "answer_correct": all(x in answer for x in EXPECT),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs", default="16384:2000,16384:12000,32768:2000,32768:26000",
                    help="comma list of num_ctx:prompt_tokens")
    ap.add_argument("--num-predict", type=int, default=120)
    args = ap.parse_args()
    pairs = [tuple(int(x) for x in p.split(":")) for p in args.pairs.split(",")]

    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    ver = subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout.strip()
    runs = []
    for num_ctx, ptoks in pairs:
        try:
            res = run_pair(args.model, num_ctx, ptoks, args.num_predict)
        except Exception as exc:  # noqa: BLE001 -- a failed pair is a result, not a crash
            res = {"num_ctx": num_ctx, "prompt_tokens_target": ptoks, "error": repr(exc)[:300]}
        runs.append(res)
        print(f"[bench] {args.model} ctx={num_ctx} prompt~{ptoks}: "
              + (f"prefill {res.get('prompt_tok_per_s')} tok/s, gen {res.get('gen_tok_per_s')} tok/s, "
                 f"load {res.get('load_s')}s, split {res.get('processor_split')}, correct={res.get('answer_correct')}"
                 if "error" not in res else f"ERROR {res['error']}"), flush=True)

    record = {"ts_et": et_now(), "model": args.model, "gpu": gpu, "ollama": ver, "runs": runs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    history.append(record)
    OUT.write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(f"[bench] wrote {OUT} ({len(history)} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
