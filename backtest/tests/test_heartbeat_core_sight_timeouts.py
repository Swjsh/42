"""Never-blind guard — every network read in the LIVE engine sight path is bounded.

The 2026-06-25 architecture migration retired the LLM heartbeats (Gamma_Heartbeat/
_Aggressive, now Disabled) in favor of Gamma_HeartbeatCore = setup/scripts/heartbeat_core.py,
which reads NO TradingView / no MCP / no CDP — it pulls SPY 5m bars + ribbon + VIX + the
broker account/activities directly over the network. That eliminated the original
OPEN-BLINDNESS-TV-HANG root cause (a TV chart reload at the bell hung the 09:35 tick until a
280s tree-kill), but it MOVED the never-blind guarantee onto these direct network calls.

The foot-gun this pins: ``urllib.request.urlopen`` defaults to ``timeout=None`` = BLOCK
FOREVER, and a future refactor could add a new broker/data call (or drop an explicit
``timeout=``) and silently re-introduce an indefinite-hang blindness that no exception
handler catches (a hang is not an exception -> the fail-open ``except`` never fires; the tick
just stalls). yfinance's ``download`` currently defaults to ``timeout=10`` but that default
DIFFERS across installed versions on this rig (0.2.66 vs 1.0) -> relying on it is fragile.

So: assert STATICALLY (AST, no import, no network, $0) that EVERY ``urlopen(...)`` and every
``yf.download(...)`` in heartbeat_core.py passes an explicit, bounded ``timeout=`` literal.
This is the never-blind property as a code assertion (OP-25 graduate-concern-to-guard),
replacing the now-stale OPEN-BLINDNESS-TV-HANG prose. RED if any network call goes unbounded.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HEARTBEAT_CORE = ROOT / "setup" / "scripts" / "heartbeat_core.py"

# Reasonable ceiling for a hot-path (3-min tick) network read: a stall longer than this
# should fail the call, not the tick. Generous so a legit slow read isn't flagged.
MAX_TIMEOUT_SECONDS = 60


def _tree() -> ast.AST:
    assert HEARTBEAT_CORE.exists(), f"missing live engine: {HEARTBEAT_CORE}"
    return ast.parse(HEARTBEAT_CORE.read_text(encoding="utf-8"), filename=str(HEARTBEAT_CORE))


def _call_name(node: ast.Call) -> str | None:
    """Return a dotted-ish name for the called function, or None."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _network_calls() -> list[ast.Call]:
    """All urlopen(...) and yf.download(...) / download(...) Call nodes in the live engine."""
    out: list[ast.Call] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("urlopen", "download"):
                out.append(node)
    return out


def _timeout_kw(call: ast.Call) -> ast.keyword | None:
    for kw in call.keywords:
        if kw.arg == "timeout":
            return kw
    return None


def test_there_are_network_calls_to_guard() -> None:
    """Non-vacuous: the live engine genuinely makes network reads (else the guard is empty)."""
    calls = _network_calls()
    assert len(calls) >= 4, (
        f"expected the live engine to make >=4 network reads (SPY 5m + 3x VIX + 2x broker); "
        f"found {len(calls)} -- if the sight path was refactored, update this guard."
    )


def test_every_network_call_has_a_timeout_kwarg() -> None:
    """The core invariant: no unbounded (timeout=None / blocks-forever) network read."""
    offenders = []
    for call in _network_calls():
        if _timeout_kw(call) is None:
            offenders.append((_call_name(call), call.lineno))
    assert not offenders, (
        "UNBOUNDED network call(s) in heartbeat_core.py -- a hang here stalls the live tick "
        "indefinitely (urlopen default timeout=None = block forever; a hang is not an "
        f"exception so the fail-open except never fires). Add an explicit timeout=. {offenders}"
    )


def test_every_timeout_is_a_bounded_positive_literal() -> None:
    """A timeout= must be a concrete positive number <= the ceiling, not None / a name / huge."""
    bad = []
    for call in _network_calls():
        kw = _timeout_kw(call)
        if kw is None:
            continue  # covered by the previous test
        v = kw.value
        if not (isinstance(v, ast.Constant) and isinstance(v.value, (int, float))):
            bad.append((_call_name(call), call.lineno, "non-literal timeout"))
            continue
        if not (0 < float(v.value) <= MAX_TIMEOUT_SECONDS):
            bad.append((_call_name(call), call.lineno, f"timeout={v.value} out of (0, {MAX_TIMEOUT_SECONDS}]"))
    assert not bad, f"unbounded / non-literal network timeouts: {bad}"


def test_critical_spy_fetch_is_bounded() -> None:
    """Belt-and-suspenders on the single most important read: the SPY 5m bars feed the
    price + ribbon (the never-blind core). It must have a bounded timeout no matter what."""
    src = HEARTBEAT_CORE.read_text(encoding="utf-8")
    assert "data.alpaca.markets/v2/stocks/SPY/bars" in src, "SPY 5m REST URL moved -- re-pin this guard"
    # the urlopen for the SPY fetch lives in _fetch_spy_5m; assert that function's urlopen is bounded
    tree = _tree()
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_fetch_spy_5m"), None)
    assert fn is not None, "_fetch_spy_5m renamed/removed -- the price+ribbon sight path moved"
    urlopens = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) == "urlopen"]
    assert urlopens, "_fetch_spy_5m no longer calls urlopen -- re-verify the sight source"
    for c in urlopens:
        assert _timeout_kw(c) is not None, "_fetch_spy_5m urlopen lost its timeout -- never-blind regression"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
