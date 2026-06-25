#!/usr/bin/env python3
"""Self-test for self_correction.py -- verifies BEHAVIOR and SAFETY.

Stdlib only. No pytest needed:  python test_self_correction.py
Uses a throwaway temp store via CLAUDE_CORRECTIONS_FILE; never touches your real file.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.gettempdir()) / "sc_selftest_store.md"
os.environ["CLAUDE_CORRECTIONS_FILE"] = str(TMP)
TMP.write_text("", encoding="utf-8")

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sc", HERE / "self_correction.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def hook(prompt: str) -> str:
    sys.stdin = io.StringIO(json.dumps({"prompt": prompt}))
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        sc.main()
    finally:
        sys.stdout = old
    return buf.getvalue()


def store() -> str:
    return TMP.read_text(encoding="utf-8") if TMP.exists() else ""


def n_rules() -> int:
    return len([ln for ln in store().splitlines() if ln.startswith("- ")])


fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


TMP.write_text("", encoding="utf-8")

# --- BEHAVIOR ---
hook("no, don't use tabs, use spaces")
check("short correction auto-captured", "tabs" in store())

hook("rule: " + "always run the full test suite before you say you are done and never skip it " * 3)
check("marker rule captured even when long", "run the full test suite" in store())

snap = store()
hook("Let's discuss this: you sometimes don't do that thing I wanted, and I want to talk "
     "through the whole philosophy of how corrections ought to work, in detail, right now. " * 2)
check("long meta-message NOT auto-captured (false-positive guard)", store() == snap)

snap = store()
hook("move my stop loss to 720")
check("trading jargon excluded", store() == snap)

hook("no, don't use tabs, use spaces")
check("dedupe (same rule once)", store().count("don't use tabs") == 1)

out = hook("hello there")
check("recall prints standing block", "STANDING USER CORRECTIONS" in out and "tabs" in out)

before = n_rules()
hook("forget rule 1")
check("forget rule N removes one", n_rules() == before - 1)

hook("clear all corrections")
check("clear all empties the list", n_rules() == 0)

# --- SAFETY (the work-environment audit, automated) ---
src = (HERE / "self_correction.py").read_text(encoding="utf-8")
for bad in ("subprocess.", "os.system(", "os.popen(", "eval(", "exec(",
            "__import__(", "import socket", "import requests", "urllib.request"):
    check(f"safety: source has no '{bad}'", bad not in src)

TMP.write_text("", encoding="utf-8")
print("\nRESULT: " + ("ALL PASS" if not fails else f"{len(fails)} FAILED -> {fails}"))
sys.exit(0 if not fails else 1)
