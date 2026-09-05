"""Guard: keepalive process-table parsers survive wmic's real `\\r\\r\\n` line endings.

Incident (2026-09-05 14:44-17:30 ET): crypto_twin_keepalive.find_loop_pid and
proc_trace_keepalive.find_tracer_pid parsed `wmic ... /FORMAT:LIST` with str.splitlines().
Real wmic output ends every line with `\\r\\r\\n`; splitlines() treats the lone `\\r` as a line
break, inserting a blank line between the CommandLine and ProcessId fields, so every record
was split before its ProcessId was read and the parser returned None. Each 5-minute fire
then declared the loop dead and spawned another: 34 crypto-twin loops and 12 tracers were
running when caught, CPU at 53%, and decisions.jsonl got up to 34 rows per minute.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

ctk = importlib.import_module("crypto_twin_keepalive")
ptk = importlib.import_module("proc_trace_keepalive")

TWIN = (r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe "
        r"C:\Users\jackw\Desktop\42\setup\scripts\crypto_twin_health.py --live --loop --duration-sec 86400")
TRACER = (r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe "
          r"C:\Users\jackw\Desktop\42\setup\scripts\proc_trace.py")


def _wmic_list(cmd: str, pid: int, eol: str) -> str:
    # wmic LIST shape: fields, then a blank record separator; real eol is \r\r\n
    return f"{eol}{eol}CommandLine={cmd}{eol}ProcessId={pid}{eol}{eol}{eol}"


@pytest.mark.parametrize("eol", ["\r\r\n", "\r\n", "\n"])
def test_twin_parser_finds_the_loop_under_every_line_ending(eol):
    assert ctk.find_loop_pid(_wmic_list(TWIN, 4242, eol)) == 4242


@pytest.mark.parametrize("eol", ["\r\r\n", "\r\n", "\n"])
def test_tracer_parser_finds_the_tracer_under_every_line_ending(eol):
    assert ptk.find_tracer_pid(_wmic_list(TRACER, 777, eol)) == 777


def test_splitlines_would_have_missed_it():
    # Discriminating half: the pre-fix parse (splitlines) splits the record at the lone \r.
    text = _wmic_list(TWIN, 4242, "\r\r\n")
    assert "" in [ln.strip() for ln in text.splitlines()][1:4]  # a spurious blank between fields
    assert ctk.find_loop_pid(text) == 4242  # the fixed parser still wins


def test_parsers_return_none_when_absent():
    assert ctk.find_loop_pid(_wmic_list(TRACER, 1, "\r\r\n")) is None
    assert ptk.find_tracer_pid(_wmic_list(TWIN, 1, "\r\r\n")) is None
