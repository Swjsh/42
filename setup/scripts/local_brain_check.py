#!/usr/bin/env python3
"""local_brain_check.py -- one command that answers "is the local LLM real, and is it working?"

WHY (J asked twice, 2026-09-15): the Ollama models named `claude-*` are LOCAL QWEN models
aliased so the Claude Code CLI accepts the id (setup/ollama/nothink_proxy.py rewrites them).
The names lie; the digests do not. Answering that ad-hoc each time is a missing instrument
(OP-33e), so this is the standing surface: identity, placement, a LIVE inference, and which
brain the automation fires are actually routed to.

Run:  python setup/scripts/local_brain_check.py [--json]

Every line is measured this run -- nothing is read from a cache or a doc. Any check that
cannot be performed prints UNKNOWN with the reason rather than a guess.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLLAMA = "http://localhost:11434"
SMOKE_PROMPT = "Reply with exactly: LOCAL_OK"
# Aliases whose NAME claims a vendor model. Any of these is by definition local weights:
# Claude is never distributed, so a `claude-*` tag in Ollama is always something else.
VENDOR_NAME_PREFIXES = ("claude-", "gpt-", "gemini-")


def _get(path: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(OLLAMA + path, timeout=timeout) as r:
            return json.loads(r.read()), None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
        return None, str(e)


def _post(path: str, body: dict, timeout: int = 300):
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
        return None, str(e)


def collect_models() -> tuple[list[dict], str | None]:
    """Installed models with their digest. Models sharing a digest are ONE model under N names."""
    data, err = _get("/api/tags")
    if err:
        return [], err
    models = []
    for m in data.get("models", []):
        models.append({
            "name": m.get("name", ""),
            "digest": (m.get("digest") or "")[:12],
            "size_gb": round((m.get("size") or 0) / 1e9, 1),
            "family": ((m.get("details") or {}).get("family") or "?"),
            "param_size": ((m.get("details") or {}).get("parameter_size") or "?"),
        })
    by_digest: dict[str, list[str]] = {}
    for m in models:
        by_digest.setdefault(m["digest"], []).append(m["name"])
    for m in models:
        siblings = [n for n in by_digest[m["digest"]] if n != m["name"]]
        m["same_weights_as"] = siblings
        m["vendor_named"] = m["name"].startswith(VENDOR_NAME_PREFIXES)
    return models, None


def smoke(model: str) -> dict:
    """A REAL generation, timed. think:false -- thinking-native Qwen otherwise spends the
    whole token budget in the thinking channel and returns an empty response (the exact
    behaviour nothink_proxy.py exists to normalise)."""
    t0 = time.time()
    out, err = _post("/api/generate", {
        "model": model, "prompt": SMOKE_PROMPT, "stream": False,
        "think": False, "options": {"num_predict": 40}})
    wall = round(time.time() - t0, 2)
    if err:
        return {"ok": False, "model": model, "error": err, "wall_s": wall}
    ev, ed = out.get("eval_count") or 0, out.get("eval_duration") or 0
    return {
        "ok": bool((out.get("response") or "").strip()),
        "model": out.get("model", model),
        "response": (out.get("response") or "").strip()[:120],
        "tok_per_s": round(ev / (ed / 1e9), 1) if ed else None,
        "load_s": round((out.get("load_duration") or 0) / 1e9, 1),
        "wall_s": wall,
    }


def loaded() -> list[dict]:
    data, err = _get("/api/ps")
    if err:
        return []
    out = []
    for m in data.get("models", []):
        total, gpu = m.get("size") or 0, m.get("size_vram") or 0
        out.append({"name": m.get("name"), "processor":
                    f"{round(100 * gpu / total)}% GPU" if total else "?"})
    return out


def brain_route() -> dict:
    """Which brain the opted-in automation fires (run-conductor / -weekend / analyst-eod /
    treasurer-weekly) actually use. mode=local -> the local models below; anything else -> Anthropic."""
    p = REPO / "automation" / "state" / "brain-mode.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        return {"mode": "UNKNOWN", "reason": f"{type(e).__name__}: {e}", "map": {}}
    return {"mode": d.get("mode", "UNKNOWN"), "map": d.get("map") or {},
            "changed_et": d.get("changed_et"), "changed_by": d.get("changed_by")}


def store() -> dict:
    """Where the weights physically live, and how much disk they occupy."""
    try:
        root = subprocess.run(["powershell", "-NoProfile", "-Command", "$env:OLLAMA_MODELS"],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return {"path": "UNKNOWN", "reason": str(e)}
    if not root:
        return {"path": "default (~/.ollama/models)", "size_gb": None}
    blobs = Path(root) / "blobs"
    if not blobs.is_dir():
        return {"path": root, "size_gb": None, "reason": "blobs dir not found"}
    total = sum(f.stat().st_size for f in blobs.iterdir() if f.is_file())
    return {"path": root, "size_gb": round(total / 1e9, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--model", default=None, help="model to smoke-test (default: the routed sonnet-tier model)")
    args = ap.parse_args()

    models, tags_err = collect_models()
    route = brain_route()
    target = args.model or route.get("map", {}).get("sonnet") or (models[0]["name"] if models else None)
    result = {
        "ollama_up": tags_err is None,
        "ollama_error": tags_err,
        "store": store(),
        "models": models,
        "loaded": loaded(),
        "brain_route": route,
        "smoke": smoke(target) if (tags_err is None and target) else None,
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["ollama_up"] and (result["smoke"] or {}).get("ok") else 1

    print(f"ollama: {'UP' if result['ollama_up'] else 'DOWN -- ' + str(tags_err)}  @ {OLLAMA}")
    st = result["store"]
    print(f"weights: {st.get('path')}" + (f"  ({st['size_gb']} GB on disk)" if st.get("size_gb") else ""))
    print("\nINSTALLED MODELS  (a name is not an identity -- the digest is)")
    for m in models:
        flag = "  <-- LOCAL WEIGHTS, vendor-styled NAME" if m["vendor_named"] else ""
        alias = f"  [same weights as: {', '.join(m['same_weights_as'])}]" if m["same_weights_as"] else ""
        print(f"  {m['name']:<28} {m['digest']}  {m['size_gb']:>5} GB  {m['family']}/{m['param_size']}{alias}{flag}")
    if result["loaded"]:
        print("\nLOADED NOW: " + ", ".join(f"{m['name']} ({m['processor']})" for m in result["loaded"]))
    s = result["smoke"]
    if s:
        print(f"\nLIVE INFERENCE  {s['model']}")
        if s["ok"]:
            print(f"  response={s['response']!r}  {s['tok_per_s']} tok/s  load {s['load_s']}s  wall {s['wall_s']}s  -> WORKING")
        else:
            print(f"  FAILED: {s.get('error') or 'empty response'}  (wall {s['wall_s']}s)")
    r = result["brain_route"]
    where = "LOCAL Ollama models" if r["mode"] == "local" else "Anthropic (real Claude)"
    print(f"\nAUTOMATION ROUTING: brain-mode={r['mode']} -> {where}")
    if r["mode"] == "local":
        print(f"  tier map: {r['map']}  (affects run-conductor, -weekend, analyst-eod, treasurer-weekly)")
    return 0 if result["ollama_up"] and (s or {}).get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
