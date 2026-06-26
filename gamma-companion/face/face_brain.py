"""Gamma companion FACE brain -- the cheap, always-on conversational layer.

Reads a JSON request on stdin:  {"message": str, "history": str, "state": str}
Calls a FREE OpenRouter model (reusing the battle-tested run_minimax client) with
a lean Gamma persona, then prints ONE JSON line on stdout:

    {"ok": bool, "reply": str, "escalate": bool, "model": "opus"|"sonnet",
     "task": str, "source_model": str}

The face NEVER trades and NEVER edits doctrine. It chats, narrates live state,
and DECIDES when a request needs Claude's muscle -- emitting an escalation that
the Node backend runs as a headless `claude -p` fire.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Force UTF-8 stdio. When the Node server spawns us on Windows the default
# console encoding is cp1252, and printing the em-dashes / middots in the state
# summary raises UnicodeEncodeError (works in Git Bash, crashes via the server).
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from run_minimax import call_minimax  # reuse the existing OpenRouter client
except Exception as exc:  # pragma: no cover - import guard
    print(json.dumps({"ok": False, "reply": f"(face offline: {exc})", "escalate": False}))
    sys.exit(0)

# Free-tier ladder -- try in order, fall through on failure / rate-limit.
FACE_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m2.5:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
)

_SYSTEM_FALLBACK = """You are Gamma -- the voice of an autonomous 0DTE SPY options trading system that J built. You are the always-on FACE: warm, sharp, and brief. Short plain sentences (J is often on mobile or voice). You ARE Gamma, not a generic chatbot.

You can SEE the system's live state (provided each turn). Use it to answer status questions directly -- positions, P&L, engine health, the kitchen R&D loop, what each part is doing right now.

You are the cheap, fast layer. For anything that needs real WORK -- research, writing or changing code, deep market analysis, improving the engine, running a backtest, reviewing a candidate, or managing a trade -- you do NOT do it yourself. You hand it to Claude (the powerful model) by ESCALATING.

HARD LIMITS: never place trades, never edit live doctrine/params, never claim work is done that you did not verify. When unsure whether you can answer, escalate.

HOW TO REPLY:
- Chat / status / anything answerable from the state above: reply in plain text, 2-4 sentences max. No escalation block.
- When the request needs Claude's muscle, append a fenced escalation block EXACTLY in this form (and keep any human-facing sentence before it short):
```escalate
{"model": "opus", "task": "<precise, self-contained instruction for Claude, including file paths and context>"}
```
  Use "opus" for deep reasoning / strategy / analysis; "sonnet" for coding, edits, and routine work.
- Only escalate when J EXPLICITLY asks you to build, change, fix, run, write, or analyze something. For questions, status, opinions, and what-should-I-do -- ANSWER directly and fast from the state above; do not escalate.
- Be PROACTIVE: end most replies with one short suggestion for a useful next step (e.g. "Want me to pull the chart?").
- Keep replies tight -- one or two sentences is ideal, especially for voice."""


# Load the ONE canonical Gamma soul (shared with the realtime voice + Discord +
# the conductor). Fall back to the inline persona if the file is ever missing.
def _load_soul() -> str:
    try:
        soul = (REPO / "automation" / "presence" / "GAMMA-VOICE.md").read_text(encoding="utf-8")
        if soul.strip():
            return soul
    except Exception:
        pass
    return _SYSTEM_FALLBACK


# The machine-readable RUNTIME bits the brain needs on top of the persona (the
# escalation FORMAT parse_escalation() depends on) -- not persona, stays in code.
_BRAIN_RUNTIME_CONTRACT = """

---
RUNTIME CONTRACT (output format -- this is mechanics, not persona):
- You are given the live system state each turn. Answer status / question / opinion turns directly from it.
- REPLY SHAPE -- J reads on his phone, so keep it SHORT and SCANNABLE. Lead with the answer (no preamble, no filler, no "As an AI", no walls of text). FACTUAL only.
  - TYPED replies (the default, text face): default to <= 3-4 tight bullets OR <= 2 short sentences. Use markdown the phone renders -- **bold** the key term or a short bold mini-header, "- " bullets for lists, and `inline code` (backticks) for paths / values / numbers. Then ONE proactive next step.
  - SPOKEN replies (voice/fast turns): even shorter -- ONE or TWO plain sentences, NO markdown at all (no bold, no bullets, no backticks -- they get read aloud as noise). Same facts, just spoken.
- VOICE: talk cool, not corporate -- a bit of swagger, partner-to-partner. Add ONE fitting emoji where it actually lands (📈 green/market read, 🔧 building/fixing, 👀 watching, ✅ done/shipped, ⚡ fast, 🟢/🔴 health, ⚠️ warning, 🧠 handing to Claude, 🍳 kitchen). Keep it to one, and use NONE on serious lines -- a loss, a risk warning, a veto, or refusing to invent a number stay clean and flat. The emoji is a wink, never a replacement for the fact or the next step.
- WHERE THINGS ARE WRITTEN (one cohesive Gamma -- every face/worker uses the SAME places): human docs -> under markdown/ in the matching subfolder (never repo root, never a code dir); runtime state + logs -> automation/state/ and automation/state/logs/; the shared activity ledger -> automation/state/gamma-activity.jsonl; the shared voice/chat conversation log -> automation/state/companion-conversation.jsonl.
- ESCALATE only when J explicitly asks to build, change, fix, run, write, or analyze something. To escalate, append a fenced block EXACTLY like this (keep any human sentence before it short):
```escalate
{"model": "opus", "task": "<precise, self-contained instruction for Claude, including file paths and context>"}
```
  Use "opus" for deep reasoning / strategy / analysis; "sonnet" for coding, edits, and routine work.
- Never invent a number you cannot read from the state. Never claim unverified work is done."""


SYSTEM = _load_soul() + _BRAIN_RUNTIME_CONTRACT


def build_prompt(message: str, history: str, state_summary: str) -> str:
    parts = [f"# Live system state\n```\n{state_summary}\n```\n"]
    if history.strip():
        parts.append(f"# Recent conversation\n{history}\n")
    parts.append(f"# J just said\n{message}\n")
    parts.append("Reply as Gamma. Escalate only if real work is needed.")
    return "\n".join(parts)


def parse_escalation(text: str):
    """Return (escalation_dict_or_None, visible_reply)."""
    m = re.search(r"```escalate\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None, text
    try:
        obj = json.loads(m.group(1))
    except Exception:
        return None, text
    model = str(obj.get("model") or "sonnet").lower()
    if model not in ("opus", "sonnet"):
        model = "sonnet"
    task = str(obj.get("task") or "").strip()
    if not task:
        return None, text
    reply = (text[: m.start()] + text[m.end():]).strip()
    if not reply:
        reply = f"On it -- handing this to Claude {model.title()}. I'll narrate when it's back."
    return {"model": model, "task": task}, reply


def main() -> None:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except Exception:
        req = {}

    message = str(req.get("message") or "").strip()
    history = str(req.get("history") or "")
    state_summary = str(req.get("state") or "(no state)")

    if not message:
        print(json.dumps({"ok": False, "reply": "(say something and I'll answer)", "escalate": False}))
        return

    fast = bool(req.get("voice") or req.get("fast"))
    # Voice path: smallest/fastest free models first, proven nemotron-super as the
    # guaranteed fallback (the loop skips any model that is 404 / rate-limited).
    models = (
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "minimax/minimax-m2.5:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ) if fast else FACE_MODELS
    # Non-fast cap raised 420 -> 800: a rich self-contained escalation task plus the
    # short human sentence could exceed 420 and TRUNCATE the ```escalate JSON, so
    # parse_escalation's json.loads failed -> (None, text) -> no session. 800 gives
    # the fence room to close. (Voice stays small/fast for latency.)
    max_tokens = 200 if fast else 800
    timeout = 13 if fast else 22

    prompt = build_prompt(message, history, state_summary)
    last_err = None
    for model in models:
        res = call_minimax(
            prompt=prompt,
            model=model,
            system=SYSTEM,
            max_tokens=max_tokens,
            temperature=0.5,
            timeout=timeout,
            task_id="companion.face.voice" if fast else "companion.face",
        )
        content = (res.get("content") or "").strip()
        if res.get("ok") and content:
            esc, reply = parse_escalation(content)
            out = {"ok": True, "reply": reply, "source_model": model, "escalate": bool(esc)}
            if esc:
                out["model"] = esc["model"]
                out["task"] = esc["task"]
            print(json.dumps(out, ensure_ascii=False))
            return
        last_err = res.get("error")

    print(json.dumps({"ok": False, "reply": f"(all free models busy -- try again in a moment)", "escalate": False, "error": last_err}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never emit non-JSON to stdout -- the server parses our last line
        print(json.dumps({"ok": False, "reply": "(face error -- try again)", "escalate": False, "error": str(exc)[:200]}))
