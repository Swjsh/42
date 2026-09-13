"""station_brain_quiz.py -- "is the local brain smart, and how fast?" in one $0 run.

Three graded questions, each verifiable by a string check (no LLM grading): a repo-rule read that
needs the *isolation* nuance, a sizing calculation that needs arithmetic + rounding down, and a
look-ahead bug hunt in a small Python function. Speeds come straight from Ollama's own timing
fields (eval_count / eval_duration), never a stopwatch around HTTP. Writes
automation/state/station/brain-quiz.json (latest run; the /station page renders it) and prints a
one-line verdict per question. Stdlib only. Instrument for J's repeated question "show me it's
working / is it dumb?" (GAMMA-STATION 2026-09-13).

Usage:
  python setup/scripts/station_brain_quiz.py                          # planner from station config
  python setup/scripts/station_brain_quiz.py --model qwen3:14b --also  # extra model, kept under "others"
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
OUT = ROOT / "automation" / "state" / "station" / "brain-quiz.json"
CONFIG = ROOT / "automation" / "state" / "station" / "config.json"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
SYSTEM = ("You are Gamma's local planner. Answer precisely and briefly. Follow the requested answer "
          "format exactly; no preamble.")

BUGGY_FUNC = '''def breakout_at(bars, i):
    """True when bar i CLOSES above the highest HIGH of the 20 bars before it (no look-ahead)."""
    window = bars[i - 20:i + 1]
    prior_high = max(b["high"] for b in window)
    return bars[i]["close"] > prior_high
'''


def et_now() -> str:
    try:
        out = subprocess.run([sys.executable, str(ROOT / "setup/scripts/et_clock.py")],
                             capture_output=True, text=True, timeout=20).stdout
        return out.strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"et_clock failed: {exc}"


def rules_excerpt() -> str:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8", errors="replace")
    start = text.find("## The 10 rules")
    end = text.find("## Tech stack")
    return text[start:end] if start >= 0 and end > start else text[:6000]


def questions() -> list[dict]:
    return [
        {
            "id": "rule5_isolation",
            "label": "Repo rule read (needs the isolation nuance)",
            "prompt": (rules_excerpt() + "\n\nQUESTION: Gamma-Safe just hit -30% of start-of-day equity. "
                       "Does Gamma-Bold have to stop trading for the day too? Reply exactly as "
                       "'VERDICT: YES' or 'VERDICT: NO', then one sentence naming the rule number."),
            "expected": "VERDICT: NO -- Rule 5 kill switches are isolated per account",
            "check": lambda a: bool(re.search(r"VERDICT:\s*\**\s*NO\b", a, re.I)) and bool(re.search(r"\b5\b", a)),
            "num_predict": 120,
        },
        {
            "id": "sizing_math",
            "label": "Sizing arithmetic (Rule 6, round down)",
            "prompt": ("Gamma-Safe equity is $5,266.38. Rule 6 caps per-trade risk at 30% of account equity. "
                       "An at-the-money SPY 0DTE call is quoted at $2.10 per share and one contract is 100 shares. "
                       "What is the maximum WHOLE number of contracts Gamma-Safe may buy? Show the math in one "
                       "line, then finish with 'ANSWER: <integer>'."),
            "expected": "5,266.38 x 0.30 = 1,579.91; / 210 = 7.52 -> ANSWER: 7",
            "check": lambda a: bool(re.search(r"ANSWER:\s*\**\s*7\b", a)),
            "num_predict": 200,
        },
        {
            "id": "lookahead_bug",
            "label": "Code bug hunt (look-ahead / self-inclusion)",
            "prompt": ("Find the bug in this Python function and fix it.\n\n```python\n" + BUGGY_FUNC + "```\n\n"
                       "Reply as two lines: 'BUG: <one sentence>' and 'FIX: <the corrected slice expression>'."),
            "expected": "window includes bar i itself (close can never beat its own high) -> bars[i - 20:i]",
            "check": lambda a: bool(re.search(r"20\s*\)?\s*:\s*i\s*\]", a)),
            "num_predict": 200,
        },
    ]


def chat(model: str, prompt: str, num_predict: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 8192, "num_predict": num_predict, "temperature": 0.2},
    }
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_split() -> str:
    try:
        ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"(\d+%/\d+% CPU/GPU|100% GPU|100% CPU)", ps)
        return m.group(1) if m else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def run_model(model: str) -> dict:
    rows = []
    for q in questions():
        t0 = time.time()
        try:
            r = chat(model, q["prompt"], q["num_predict"])
        except Exception as exc:  # noqa: BLE001 -- a failed question is a wrong answer, not a crash
            rows.append({"id": q["id"], "label": q["label"], "expected": q["expected"],
                         "answer": f"ERROR {exc!r}"[:600], "correct": False, "gen_tok_per_s": None,
                         "prompt_tok_per_s": None, "wall_s": round(time.time() - t0, 1)})
            continue
        wall = time.time() - t0
        ans = ((r.get("message") or {}).get("content") or "").strip()
        ev_n, ev_d = r.get("eval_count", 0), r.get("eval_duration", 0)
        pe_n, pe_d = r.get("prompt_eval_count", 0), r.get("prompt_eval_duration", 0)
        rows.append({
            "id": q["id"], "label": q["label"], "expected": q["expected"], "answer": ans[:600],
            "correct": bool(q["check"](ans)),
            "gen_tokens": ev_n,
            "gen_tok_per_s": round(ev_n / (ev_d / 1e9), 1) if ev_d else None,
            "prompt_tokens": pe_n,
            "prompt_tok_per_s": round(pe_n / (pe_d / 1e9), 1) if pe_d else None,
            "load_s": round(r.get("load_duration", 0) / 1e9, 1),
            "wall_s": round(wall, 1),
        })
        print(f"[quiz] {model} {q['id']}: {'PASS' if rows[-1]['correct'] else 'FAIL'} "
              f"gen {rows[-1]['gen_tok_per_s']} tok/s, wall {rows[-1]['wall_s']}s", flush=True)
    speeds = [x["gen_tok_per_s"] for x in rows if x.get("gen_tok_per_s")]
    return {
        "model": model,
        "score": f"{sum(1 for x in rows if x['correct'])}/{len(rows)}",
        "gen_tok_per_s": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "processor_split": ollama_split(),
        "questions": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="default: automation/state/station/config.json 'model'")
    ap.add_argument("--also", action="store_true", help="store this run under 'others' instead of replacing the headline")
    args = ap.parse_args()
    model = args.model
    if not model:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig")) if CONFIG.exists() else {}
        model = cfg.get("model", "gamma-planner-fast")

    result = run_model(model)
    result["ts_et"] = et_now()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(OUT.read_text(encoding="utf-8-sig")) if OUT.exists() else {}
    if args.also and prev.get("model"):
        others = [o for o in prev.get("others", []) if o.get("model") != model]
        others.append({k: result[k] for k in ("model", "score", "gen_tok_per_s", "processor_split", "ts_et", "questions")})
        prev["others"] = others
        record = prev
    else:
        record = dict(result, others=[o for o in prev.get("others", []) if o.get("model") != model])
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[quiz] {model}: score {result['score']}, avg gen {result['gen_tok_per_s']} tok/s, "
          f"split {result['processor_split']} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
