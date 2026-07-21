"""dojo/whisper.py -- the "listen into the engine" surface (pure formatting, no I/O).

Renders a terse, human, multi-arm block from a bar's DojoDecision list so the session agent
can read it aloud to J at every replayed bar (DOJO-REPLAY-TRAINING-SPEC.md item 2 / DOJO-
ARCHITECTURE-DECISION.md's whisper.py contract). This module NEVER computes anything the
engine didn't already decide -- it only formats what is already on each decision object.

FIELD SOURCE (frozen contract, DOJO-ARCHITECTURE-DECISION.md engine_step.py section):
    DojoDecision: arm, side, verdict, bear_score, bull_score, ribbon, htf_15m, vix, triggers,
    setup, trigger_level, would_place, spy, cursor_et, context_bundle.

engine_step.py had not been built yet at the time this module was written (Phase 1, parallel
build). Every field is therefore read defensively via `_get()` (getattr-or-dict-get, never
raises, missing -> the caller's default) rather than assumed present -- this module renders
correctly against the CONTRACT's field list today and degrades gracefully (missing fields show
as "-", never a crash) if the real DojoDecision ships with a slightly different shape.

`context_bundle` is read the same way heartbeat_core.py already tags it onto a decision row
(setup/scripts/heartbeat_core.py's `"context_bundle": bc.get("context_bundle")` /
`_read_context_bundle()`) -- a plain dict (or None) shaped like
setup/scripts/context_bundle_producer.py's `compute_levels_context()` output:
    context_bundle["levels_context"] = {
        "nearest_level_above": {"price": float, "distance": float, "source": str} | None,
        "nearest_level_below": {"price": float, "distance": float, "source": str} | None,
        "n_levels_within_1pct": int | None, "reason": str | None,
    }
That is the "nearest key levels above/below" this module renders per arm.

NEVER fabricates a value: a field that is genuinely absent on the decision object renders as
"-", never a guessed or defaulted number. NEVER raises: `render()` is called live, mid-session,
with J watching -- a formatting bug here must never take down the whisper loop.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

_MISSING = object()


# =============================================================== defensive field access
def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` off a decision-like object -- tolerant of dataclass instances, plain
    dicts, SimpleNamespaces, or any other hand-built test fixture. NEVER raises: any lookup
    failure (missing attribute/key, weird `__getattr__`, wrong type) falls back to `default`.
    This is the single point where "render ONLY fields that exist" + "never fabricate a
    value" are enforced -- a genuinely-absent field always resolves to `default`."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        val = getattr(obj, name, _MISSING)
    except Exception:
        return default
    return default if val is _MISSING else val


def _fmt_val(x: Any) -> str:
    """None -> '-'; anything else -> str(x). Never raises."""
    if x is None:
        return "-"
    try:
        return str(x)
    except Exception:
        return "-"


def _fmt_num(x: Any, nd: int = 2) -> str:
    """None -> '-'; a real number -> fixed-point string; anything non-numeric falls back to
    str(x) rather than raising (a decision field that's a string where a number was expected
    is a data problem worth surfacing verbatim, not a crash)."""
    if x is None:
        return "-"
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return _fmt_val(x)


def _fmt_bar_time(cursor_et: Any) -> str:
    """cursor_et is a tz-aware ET datetime per the render() contract; defensively falls back
    to str() for anything else (e.g. a hand-built test fixture) rather than raising."""
    if cursor_et is None:
        return "-"
    try:
        return f"{cursor_et:%H:%M ET}"
    except (TypeError, ValueError):
        return _fmt_val(cursor_et)


def _fmt_levels(context_bundle: Any) -> str:
    """Nearest active key level above/below, from context_bundle['levels_context'] (see
    module docstring for the exact shape this mirrors -- context_bundle_producer.py's
    compute_levels_context()). Missing/malformed at any layer -> '-', never a raise."""
    lc = _get(context_bundle, "levels_context")
    if not isinstance(lc, dict):
        return "-"
    above = lc.get("nearest_level_above")
    below = lc.get("nearest_level_below")
    parts: list[str] = []
    if isinstance(above, dict) and above.get("price") is not None:
        parts.append(f"above {_fmt_num(above.get('price'))}(+{_fmt_num(above.get('distance'))})")
    if isinstance(below, dict) and below.get("price") is not None:
        parts.append(f"below {_fmt_num(below.get('price'))}(-{_fmt_num(below.get('distance'))})")
    return " / ".join(parts) if parts else "-"


# =============================================================================== rendering
def _render_arm_line(d: Any) -> str:
    """One arm's line. Wrapped in its own try/except so a single malformed decision object
    degrades to a minimal safe line instead of ever taking down render() for the whole bar."""
    try:
        arm = _fmt_val(_get(d, "arm"))
        verdict_raw = _get(d, "verdict")
        verdict = verdict_raw.upper() if isinstance(verdict_raw, str) else _fmt_val(verdict_raw)
        bear = _fmt_num(_get(d, "bear_score"))
        bull = _fmt_num(_get(d, "bull_score"))
        side = _fmt_val(_get(d, "side"))
        setup = _fmt_val(_get(d, "setup"))
        trig = _fmt_num(_get(d, "trigger_level"))
        levels = _fmt_levels(_get(d, "context_bundle"))
        return (
            f"  {arm:<8}: {verdict:<6} bear={bear:<6} bull={bull:<6} "
            f"side={side:<2} setup={setup:<20} trig={trig:<8} levels: {levels}"
        )
    except Exception:  # noqa: BLE001 -- whisper must never crash the live session loop
        return f"  {_fmt_val(_get(d, 'arm', '?'))}: - (render error, decision unavailable)"


def render(decisions: list, cursor_et: datetime) -> str:
    """Terse, human, multi-arm whisper block -- the "listen into the engine" surface the
    session agent reads aloud to J each replayed bar.

    Header line = bar time (from `cursor_et`, NOT any decision's own `cursor_et` field --
    the caller's clock is authoritative for the header) + SPY + ribbon, both read off the
    first decision (they are the shared market-wide read every arm's decision carries this
    tick; if the list is empty both render as '-').

    One line per arm: verdict, bear/bull score, side, setup, trigger_level, and the nearest
    key levels above/below (from that decision's `context_bundle.levels_context`, if
    present). RULES: renders ONLY fields that exist on the decision objects -- never
    fabricates a value, never raises, even when a decision is missing every optional field.
    """
    bar_label = _fmt_bar_time(cursor_et)
    first = decisions[0] if decisions else None
    spy = _fmt_num(_get(first, "spy"))
    ribbon = _fmt_val(_get(first, "ribbon"))
    lines = [f"[{bar_label}] SPY {spy} | ribbon: {ribbon}"]

    if not decisions:
        lines.append("  (no arm decisions this bar)")
        return "\n".join(lines)

    for d in decisions:
        lines.append(_render_arm_line(d))
    return "\n".join(lines)
