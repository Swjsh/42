"""heartbeat.md ``(currently `X`)`` param-annotation drift RATCHET (2026-06-24).

WHY THIS GUARD EXISTS — the foot-gun it graduates to code.
-----------------------------------------------------------
The live decision surface is an LLM-executed prompt (``automation/prompts/heartbeat.md``
+ ``.../aggressive/heartbeat.md``). Each param-gated gate is documented there as::

    Read ``params.json#block_bull_morning_agg`` (currently ``true``).

The GATING LOGIC reads the live flag at runtime (``If `true` AND ...``), so a flipped
param is *logically* honoured. But the parenthetical ``(currently `true`)`` is a frozen
human annotation — when J flips a param **mid-session** (a Rule-9 author override, e.g.
2026-06-24 disabling ``block_bull_morning_agg`` after it vetoed an 11/11 A+ reclaim) the
annotation goes STALE and nothing catches it. An executing LLM can anchor on the stale
``(currently `true`)`` and skip re-reading the real flag → silent live-behaviour risk.
This is the params↔prompt drift class (sibling to ``test_params_filters_drift.py``'s
params↔filters ratchet); the prose got re-violated, so it graduates to an assertion
(OP-25 STAGE 4.5).

WHAT THIS RATCHET ASSERTS
-------------------------
  1. Every ``#<param>` (currently `<value>`)`` annotation in BOTH heartbeats matches the
     live value in the correct params.json — EXCEPT entries on ``KNOWN_STALE`` (a drift
     pending a rail-4 heartbeat.md edit J must apply; the conductor cannot edit
     heartbeat.md). A NEW drift (an un-allowlisted mismatch) FAILS LOUD.
  2. Every ``KNOWN_STALE`` entry is STILL genuinely stale. Once J applies the proposal
     and the annotation is corrected, the entry is dead → the test fails until it is
     removed. The allowlist is therefore shrinks-only (a ratchet toward zero), never a
     place fixed drift can hide forever.

Pure static text/JSON inspection — no backtest, no network, $0.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "backtest"))

# Reuse v25's canonical path constants so this ratchet never drifts from the real files.
from crypto.validators.v25_filter_gates import (  # noqa: E402
    _PARAMS_PATH,
    _PARAMS_AGG_PATH,
    _HEARTBEAT_PATH,
    _HEARTBEAT_AGG_PATH,
)

# ── KNOWN_STALE allowlist (RATCHET — shrinks only) ────────────────────────────
#
# An annotation that is intentionally/temporarily out of sync with the live param,
# pending a rail-4 heartbeat.md edit that only J can apply. Each entry MUST still be
# genuinely stale (the ratchet asserts it) — remove it the moment J applies the fix.
#
# key = (heartbeat label, param name); value = the proposal / rationale ref.
KNOWN_STALE: dict[tuple[str, str], str] = {
    # gp-2026-06-24-001 applied 2026-06-24 (interactive session): annotation updated to `false`
}

# ``Read `...#<param>` (currently `<value>`)`` — capture the param key and annotated value.
_ANNOTATION_RE = re.compile(r"#([A-Za-z0-9_.]+)`\s*\(currently\s*`([^`]+)`\)")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(params: dict, dotted_key: str):
    """Traverse a (possibly dotted) param path; raise KeyError if absent."""
    node = params
    for part in dotted_key.split("."):
        node = node[part]
    return node


def _annotation_matches(annotated: str, actual) -> bool:
    a = annotated.strip().strip("`").lower()
    if isinstance(actual, bool):
        return a == ("true" if actual else "false")
    if isinstance(actual, (int, float)):
        try:
            return abs(float(a) - float(actual)) < 1e-9
        except ValueError:
            return False
    if actual is None:
        return a in ("null", "none")
    return a == str(actual).lower()


def _annotations(hb_path: Path):
    """Yield (param_key, annotated_value) for every annotation in a heartbeat file."""
    text = hb_path.read_text(encoding="utf-8")
    for m in _ANNOTATION_RE.finditer(text):
        yield m.group(1), m.group(2)


# (label, heartbeat path, params path)
_SURFACES = [
    ("safe", _HEARTBEAT_PATH, _PARAMS_PATH),
    ("aggressive", _HEARTBEAT_AGG_PATH, _PARAMS_AGG_PATH),
]


def test_every_param_annotation_matches_live_value():
    """A `(currently `X`)` annotation that disagrees with the live param FAILS LOUD —
    unless it is on KNOWN_STALE (a rail-4 fix pending J)."""
    drifts: list[str] = []
    seen_any = False
    for label, hb_path, params_path in _SURFACES:
        params = _load(params_path)
        for key, annotated in _annotations(hb_path):
            seen_any = True
            try:
                actual = _resolve(params, key)
            except KeyError:
                drifts.append(
                    f"[{label}] annotation references `{key}` which is ABSENT from "
                    f"{params_path.name} — broken Read reference."
                )
                continue
            if _annotation_matches(annotated, actual):
                continue
            if (label, key) in KNOWN_STALE:
                continue  # documented + ratcheted below
            drifts.append(
                f"[{label}] `{key}` annotation reads `{annotated}` but live value is "
                f"`{actual}` ({params_path.name}). Correct the heartbeat annotation "
                f"(rail-4: DRAFT + ping J) or add to KNOWN_STALE with a proposal ref."
            )
    assert seen_any, "parsed ZERO annotations — the regex or heartbeat format changed."
    assert not drifts, "params<->prompt annotation drift:\n" + "\n".join(drifts)


def test_known_stale_entries_are_still_stale():
    """Ratchet (shrinks-only): every KNOWN_STALE entry must STILL be genuinely stale.
    Once J applies the fix and the annotation is corrected, the entry is dead → this
    fails until it is removed, so fixed drift can never hide in the allowlist forever."""
    fixed: list[str] = []
    for label, hb_path, params_path in _SURFACES:
        params = _load(params_path)
        annotated_by_key = dict(_annotations(hb_path))
        for (l, key), ref in KNOWN_STALE.items():
            if l != label:
                continue
            if key not in annotated_by_key:
                fixed.append(
                    f"KNOWN_STALE[({l},{key})] — annotation no longer present in "
                    f"{hb_path.name}; remove the dead allowlist entry. ({ref})"
                )
                continue
            actual = _resolve(params, key)
            if _annotation_matches(annotated_by_key[key], actual):
                fixed.append(
                    f"KNOWN_STALE[({l},{key})] — annotation now MATCHES the live value "
                    f"(`{actual}`); the drift is fixed. Remove this allowlist entry so "
                    f"the ratchet tightens. ({ref})"
                )
    assert not fixed, "KNOWN_STALE has FIXED (dead) entries — tighten the ratchet:\n" + "\n".join(fixed)


def test_the_known_morning_block_drift_is_fixed():
    """Verifies gp-2026-06-24-001 was applied: annotation updated `true`→`false` 2026-06-24.
    Drift between params (false) and annotation (true) existed until the interactive
    session resolved it; this test now confirms the annotation matches params."""
    params = _load(_PARAMS_AGG_PATH)
    assert params["block_bull_morning_agg"] is False, (
        "block_bull_morning_agg is no longer false — J's mid-session disable was reverted; "
        "re-evaluate this guard's fixture."
    )
    annotated = dict(_annotations(_HEARTBEAT_AGG_PATH)).get("block_bull_morning_agg")
    assert annotated is not None, "the morning-block annotation vanished from the Bold heartbeat."
    assert annotated.strip().strip("`").lower() == "false", (
        f"annotation reads {annotated!r} but params is False — drift re-introduced; "
        "re-add to KNOWN_STALE or apply the fix."
    )
