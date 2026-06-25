"""Contract test for automation/scripts/ribbon_cli.py — the LIVE blindness-recovery CLI.

WHY THIS EXISTS (L164 + producer/consumer-break class, STAGE 4.5 graduation):
Both production heartbeats (automation/prompts/heartbeat.md lines 132-137 and
automation/prompts/aggressive/heartbeat.md) invoke this CLI by subprocess during a
TradingView hang — it is the OPEN-BLINDNESS-TV-HANG Layer-1a fallback that lets the
engine derive price + the Saty ribbon stack from Alpaca bars when TV is dark. The prompt
parses a FIXED set of JSON keys off stdout and branches on the EXIT CODE:

    exit 0  -> stack in {BULL,BEAR,MIXED}; parse stack/price/ema_fast/ema_pivot/
               ema_slow/spread_cents and use them for ALL downstream ribbon checks.
    exit 1  -> UNKNOWN stack or any error; emit SKIP_TV_DATA_STALE, no entry this tick.

Nothing pinned that contract. The library tests (test_ribbon_fallback.py) exercise
compute_ribbon() but NEVER the CLI's exit codes or JSON keys — so a rename of a
RibbonRead field, a change to the exit-code logic, or deleting the (until now UNTRACKED)
script would silently break the live fallback and re-open the exact blindness pain point
with no test going red. This test invokes the REAL CLI as a subprocess, exactly as the
heartbeat does, and asserts the full contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CLI = _REPO / "automation" / "scripts" / "ribbon_cli.py"

# The exact keys the heartbeat parses off stdout on a successful (exit 0) read
# (automation/prompts/heartbeat.md step 135). If any of these stop being emitted,
# the live fallback silently mis-reads the ribbon.
_HEARTBEAT_PARSED_KEYS = ("stack", "price", "ema_fast", "ema_pivot", "ema_slow", "spread_cents")
# Full output schema (everything the CLI promises).
_FULL_KEYS = _HEARTBEAT_PARSED_KEYS + ("sma_50", "bars_used", "source")


def _run(arg: str | None) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI exactly as the heartbeat does: `python ribbon_cli.py '<json>'`."""
    cmd = [sys.executable, str(_CLI)]
    if arg is not None:
        cmd.append(arg)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def _bull_closes() -> str:
    return json.dumps([700.0 + i * 0.5 for i in range(120)])


def _bear_closes() -> str:
    return json.dumps([760.0 - i * 0.5 for i in range(120)])


# --- the file must exist + be tracked (L164) -------------------------------

def test_cli_file_exists():
    assert _CLI.is_file(), f"the live fallback CLI is missing: {_CLI}"


def test_cli_is_git_tracked():
    """L164: a live producer the heartbeat invokes MUST be tracked, or a clean
    checkout/stash makes the blindness-recovery path vanish silently."""
    res = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(_CLI.relative_to(_REPO))],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, (
        "ribbon_cli.py is NOT git-tracked — the live TV-hang fallback would disappear "
        "on a clean checkout/stash and the engine would go blind again (L164)."
    )


# --- exit-code contract (the heartbeat branches on this) -------------------

def test_clean_bull_stack_exit_0_and_all_heartbeat_keys_present():
    res = _run(_bull_closes())
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    for k in _HEARTBEAT_PARSED_KEYS:
        assert k in out, f"heartbeat-parsed key missing from CLI output: {k}"
    assert out["stack"] == "BULL"
    # The 6 parsed values must be real numbers on a usable read (not None).
    for k in _HEARTBEAT_PARSED_KEYS:
        assert out[k] is not None, f"{k} is None on a usable BULL read"
    assert out["source"] == "alpaca_fallback"


def test_clean_bear_stack_exit_0():
    res = _run(_bear_closes())
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["stack"] == "BEAR"


def test_short_input_exit_1_and_unknown_stack():
    """Fewer bars than the slow EMA seed -> UNKNOWN -> exit 1 (heartbeat: SKIP, no entry).
    Critically: stdout is STILL valid JSON so the heartbeat can read price for logging."""
    res = _run("[700.0, 700.5, 701.0]")
    assert res.returncode == 1
    out = json.loads(res.stdout)
    assert out["stack"] == "UNKNOWN"
    assert out["ema_slow"] is None
    assert out["price"] == 701.0  # price still surfaced from the last bar


def test_full_output_schema_is_stable():
    """Every promised key is present (so a downstream consumer can rely on the shape)."""
    res = _run(_bull_closes())
    out = json.loads(res.stdout)
    assert set(out.keys()) == set(_FULL_KEYS), (
        f"CLI output schema drifted: got {sorted(out.keys())}, expected {sorted(_FULL_KEYS)}"
    )


# --- error paths all fail-closed to exit 1 (no entry on a bad feed) ---------

def test_malformed_json_arg_exit_1():
    res = _run("not-json")
    assert res.returncode == 1
    assert res.stdout.strip() == ""  # no bogus JSON object emitted


def test_non_array_json_exit_1():
    res = _run('{"close": 1.0}')
    assert res.returncode == 1


def test_empty_array_exit_1():
    res = _run("[]")
    assert res.returncode == 1


def test_missing_arg_exit_1():
    res = _run(None)
    assert res.returncode == 1
