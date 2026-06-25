#!/usr/bin/env python3
"""self_correction.py -- a Claude Code UserPromptSubmit hook that makes user
corrections ("no, don't do that") PERSIST and be honored on every turn.

TWO JOBS, every prompt:
  1. CAPTURE -- if your message is a short, clear correction, OR is tagged with a
     'rule:' / 'never:' / 'always:' / 'remember:' marker, store it as a standing rule.
  2. RECALL  -- print the standing-rules list to stdout. Claude Code feeds hook
     stdout into the model's context for this turn, so Claude re-reads every rule on
     every prompt (same session or a brand-new one) and stops repeating the mistake.

SAFETY (written to be reviewed in a work environment):
  - Standard library ONLY (json, re, sys, os, datetime, pathlib). No third-party deps.
  - No network calls. No process spawning, no shell, no eval/exec of input.
  - Writes exactly ONE file (the standing-rules markdown). Reads only that file plus
    the hook payload on stdin. Never deletes, never touches any other path.
  - Your prompt is treated as DATA (regex matching only); it is never executed.
  - Fail-open: any error exits 0 with no output and can never block your prompt.
  - Bounded: at most MAX_RULES rules, MAX_LEN chars each; no unbounded growth.

PRIVACY: stored rules are short snippets of your OWN messages, kept in a LOCAL
plaintext file you control (default ~/.claude/standing-corrections.md). Nothing is
transmitted anywhere. Don't phrase a rule with a secret in it. Clear anytime by
deleting the file or sending 'clear all corrections'.

CONFIG (optional env vars):
  CLAUDE_CORRECTIONS_FILE        -- path to the rules file
  CLAUDE_CORRECTIONS_MAXLEN_AUTO -- max message length to AUTO-capture (default 240)
"""
from __future__ import annotations

import datetime as dt  # noqa: F401  (kept for callers who want to stamp rules)
import json
import os
import re
import sys
from pathlib import Path

_envp = os.environ.get("CLAUDE_CORRECTIONS_FILE", "").strip()
STORE = Path(_envp) if _envp else (Path.home() / ".claude" / "standing-corrections.md")
AUTO_MAXLEN = int(os.environ.get("CLAUDE_CORRECTIONS_MAXLEN_AUTO", "240"))
MAX_RULES = 200
MAX_LEN = 240

# Explicit markers -> ALWAYS capture (any length). The reliable way to add a hard rule.
MARKER_RE = re.compile(r"\b(rule|never|always|remember)\s*:\s*(.+)", re.I)
# Management commands.
FORGET_RE = re.compile(r"\b(?:forget|drop|remove)\s+rule\s+(\d+)\b", re.I)
CLEAR_RE = re.compile(r"\b(?:forget all rules|clear all corrections|clear standing corrections)\b", re.I)
# Jargon that looks corrective but isn't ("stop loss", "stopped out").
JARGON_RE = re.compile(r"stop[\s\-]?loss|stop(?:ped)?\s+out", re.I)
# Best-effort correction phrases (only auto-captured on SHORT messages).
CORRECTION_RE = [re.compile(p, re.I) for p in (
    r"\bno,?\s+(?:please\s+)?don'?t\b", r"\bdon'?t do that\b", r"\bdon'?t ever\b",
    r"\bstop doing\b", r"\bstop trying to\b", r"\bquit doing\b", r"\bplease stop\b",
    r"\bnever do that\b", r"\byou always\b", r"\byou keep\b", r"\bi (?:told|asked) you\b",
    r"\bdo it this way\b", r"\bdo this instead\b", r"\binstead of (?:doing|that)\b",
    r"\byou got (?:that|it) wrong\b", r"\bthat'?s not what i (?:asked|wanted|said)\b",
    r"\bstop being\b",
)]


def _read_prompt() -> str:
    try:
        raw = sys.stdin.read()
    except Exception:
        return ""
    try:
        return str(json.loads(raw).get("prompt", "")).strip()
    except Exception:
        return raw.strip()


def _load() -> list[str]:
    if not STORE.exists():
        return []
    return [s[2:].strip() for s in STORE.read_text(encoding="utf-8").splitlines()
            if s.strip().startswith("- ")]


def _save(rules: list[str]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    head = ["# Standing corrections", "",
            "> Auto-captured + manual rules. Edit freely -- delete a line to drop a rule.",
            "> Claude re-reads these every turn and must honor them.", ""]
    STORE.write_text("\n".join(head + [f"- {r}" for r in rules]) + "\n", encoding="utf-8")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _extract_rule(text: str) -> str | None:
    """Return a clean rule to store, or None if this message isn't a rule."""
    m = MARKER_RE.search(text)
    if m:
        verb, body = m.group(1).lower(), re.sub(r"\s+", " ", m.group(2).strip().rstrip("."))
        body = body[:MAX_LEN]
        return f"{verb.capitalize()} {body}" if verb in ("never", "always") else body
    if len(text) > AUTO_MAXLEN:          # long messages are usually discussion, not a terse correction
        return None
    scan = JARGON_RE.sub("", text)
    if any(rx.search(scan) for rx in CORRECTION_RE):
        for part in re.split(r"(?<=[.!?])\s+|\n+", text):   # store the matched sentence
            if any(rx.search(JARGON_RE.sub("", part)) for rx in CORRECTION_RE):
                return re.sub(r"\s+", " ", part.strip())[:MAX_LEN]
        return re.sub(r"\s+", " ", text.strip())[:MAX_LEN]
    return None


def main() -> int:
    text = _read_prompt()
    if text:
        if CLEAR_RE.search(text):
            _save([])
        elif (mf := FORGET_RE.search(text)):
            rules = _load()
            i = int(mf.group(1)) - 1
            if 0 <= i < len(rules):
                del rules[i]
                _save(rules)
        else:
            rule = _extract_rule(text)
            if rule:
                rules = _load()
                if _norm(rule) not in {_norm(r) for r in rules}:
                    rules.append(rule)
                    _save(rules[-MAX_RULES:])

    rules = _load()
    if rules:
        print("=== STANDING USER CORRECTIONS -- persistent rules; honor EVERY one, every turn ===")
        for i, r in enumerate(rules, 1):
            print(f"{i}. {r}")
        print("=== end (drop one with 'forget rule N', or edit the file) ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # fail-open: never block the user's prompt
