"""Shared Windows process-table reader (GOAL fix, 2026-09-09).

WHY THIS EXISTS. Windows 11 24H2+ REMOVED `wmic.exe` from the OS. Every keepalive/watchdog
module in this repo that shelled out to `wmic` for a liveness check got WinError 2 on every
call, silently read an EMPTY process table (or a per-pid lookup as "not found"), and
concluded its target was dead -- causing a relaunch storm (126 discord-bridge starts in one
day, 6 concurrent bridges spamming J's Discord; see supervisor_keepalive.py's own
2026-09-09 docstring for the root-cause narrative and commit b1578290 for its fix).

This module is the ONE shared, importable replacement so every sibling keepalive/watchdog
stops re-deriving its own wmic call: PowerShell CIM (Get-CimInstance Win32_Process) via
CREATE_NO_WINDOW (this rig must never flash a console window -- standing user requirement),
emitting the exact `/FORMAT:LIST`-shaped blank-line-delimited `Key=Value` record text every
existing parser in this repo already expects, so callers can swap their subprocess call for
an import without touching their own parsing/decision logic.

Reference implementation: supervisor_keepalive.py's `live_process_table_text()` /
`parse_process_table()` (fixed in commit b1578290, left untouched deliberately -- this
module mirrors that pattern rather than replacing it, since other modules and tests already
import supervisor_keepalive's own copies).

Exposes:
    process_table_text() -> str                       full-table PowerShell CIM read
    parse_process_table(text) -> dict[int, str]        PURE: text -> {pid: cmdline}
    process_cmdline(pid) -> str | None                 single-pid CIM lookup
"""
from __future__ import annotations

import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Embedded newlines in a CommandLine are flattened so they cannot split a record; built with
# [char] codes (not backslash escapes) to stay quoting-safe across the -Command boundary.
_PS_NL = "[string][char]10"
_PS_CR = "[string][char]13"

_PS_PROCESS_TABLE = (
    "Get-CimInstance Win32_Process | ForEach-Object { "
    "$c = $_.CommandLine; if ($null -eq $c) { $c = '' }; "
    "$c = $c.Replace(" + _PS_CR + ",' ').Replace(" + _PS_NL + ",' '); "
    "'CommandLine=' + $c + " + _PS_NL + " + 'ProcessId=' + $_.ProcessId + " + _PS_NL + " }"
)


def process_table_text() -> str:
    """Real full process-table read via PowerShell CIM (CREATE_NO_WINDOW, no console
    flash). Isolated into its own function so every caller's pure parsing/decision logic
    never needs a real subprocess call to be unit tested."""
    return subprocess.check_output(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_PROCESS_TABLE],
        stderr=subprocess.DEVNULL, timeout=30, creationflags=_CREATE_NO_WINDOW,
    ).decode("utf-8", errors="ignore")


def parse_process_table(text: str) -> "dict[int, str]":
    """PURE: parse a '/FORMAT:LIST'-shaped CommandLine+ProcessId dump (blank-line-delimited
    records, and the last record sometimes has no trailing blank line) into {pid: cmdline}.
    Copied verbatim from supervisor_keepalive.py's proven parser (commit b1578290) -- keeps
    every pid rather than stopping at the first match, so callers can look up an ARBITRARY
    pid, not just find one marker."""
    table: "dict[int, str]" = {}
    current: "dict[str, str]" = {}

    def _flush(rec: "dict[str, str]") -> None:
        try:
            pid = int(rec.get("ProcessId", ""))
        except ValueError:
            return
        table[pid] = rec.get("CommandLine", "")

    # The LIST shape ends every line with \r\r\n; str.splitlines() treats the lone \r as a line
    # break and splits every record before ProcessId (2026-09-05 runaway: 34 twin loops).
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if current:
                _flush(current)
            current = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()
    if current:
        _flush(current)
    return table


def process_cmdline(pid: int) -> "str | None":
    """Single-pid lookup: the CommandLine of a live process, or None if no process with
    that pid currently exists (or it exists with an empty/unset CommandLine). Replaces every
    sibling module's own `wmic process where ProcessId=<pid> get CommandLine` call with an
    equivalent single-process PowerShell CIM query (cheaper than a full-table read + filter
    when a caller only ever needs one pid).

    Deliberately does NOT swallow subprocess-level failures (a PowerShell launch failure, a
    timeout) -- those propagate as exceptions so each caller can apply its OWN fail-open vs
    fail-closed policy on a tooling hiccup, exactly as each caller's original wmic-based
    implementation did (some callers fail-open on a read error, others fail-closed and
    relaunch) -- this module must not silently pick one policy for everyone."""
    ps_cmd = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\"; "
        "if ($null -ne $p) { "
        "$c = $p.CommandLine; if ($null -eq $c) { $c = '' }; "
        "$c = $c.Replace(" + _PS_CR + ",' ').Replace(" + _PS_NL + ",' '); "
        "Write-Output $c }"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        stderr=subprocess.DEVNULL, timeout=10, creationflags=_CREATE_NO_WINDOW,
    ).decode("utf-8", errors="ignore")
    text = out.strip("\r\n")
    return text if text else None
