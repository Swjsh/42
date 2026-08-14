"""Guard: conviction C4 (range_extreme) and C5 (structure_agreement) are actually WIRED.

WHAT WENT WRONG (found 2026-08-14, handoff workplan step 3 "root-cause C4 FIRST").

`heartbeat_core._conviction_shadow` read the bar history off `bc.get("bars_prior")`. The
producer writes it under **`"prior_bars"`** (`_build_payload`, and it is the key the whole
engine contract uses -- `engine_cli._require(d, "prior_bars", ...)`). The key was TRANSPOSED,
so `bars` was always `[]`, `hi`/`lo` were always `None`, and C4 hit its degrade branch on every
tick since the component was born.

PROOF IT NEVER ONCE SCORED (measured on disk before the fix, not inferred):

    102 conviction rows across all arms' decision ledgers
    102/102  degraded_components contains "range_extreme"
      0/102  components contains "range_position"   <- written ONLY on the non-degraded branch
    102/102  would_block = True
    observed total distribution: {0: 34, 3: 26, 4: 42}   <- ceiling 4, floor 5

The instrument was not a weak scorer. It was a CONSTANT: it blocked 100% of sided verdicts,
unanimously, because its reachable ceiling sat below its own floor. C5 was hardcoded `None`
("not yet threaded off engine_cli") which cost the other missing point.

SECOND DEFECT, fixed in the same pass and pinned separately below: simply correcting the key
would have handed C4 a **~1.9-session** envelope, because the payload window is 150 x 5m bars
(~12.5 RTH hours) and `prior_bars` carries no timestamps to slice by. C4's stated meaning is
INTRADAY location ("puts want the TOP of the envelope, calls the BOTTOM" -- the component that
distinguishes a long at the range LOW from a long at the range TOP). A multi-day envelope
scores a different concept under the same name, which is the failure mode that is invisible
once the component starts returning non-degraded rows. The producer now emits a session-scoped
`session_high` / `session_low` computed causally from timestamps it actually has.

WHY THIS CLASS KEEPS RECURRING HERE: this is the SECOND dead branch in conviction's short life
(the first was `source.startswith("shelf")` vs the producer's `daily_context_shelf`, fixed
2026-08-12). Both were invisible to any test asserting only that a conviction row EXISTS. Both
are C14 "dead knob" -- so these tests assert the component SCORED, never that it ran.

SCOPE: conviction is DISARMED (shadow-only; nothing branches on `would_block`). These fixes
move telemetry, not orders. C2 `multi_day_memory` is 0/102 as well, but that one is NOT a bug:
every level conviction matched was an intraday/prior-day reference (INTRADAY_RTH_HIGH,
PRIOR_DAY_CLOSE, INTRADAY_SWING_*), never a MEMORY_* shelf -- unexercised, not dead.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_conviction_c4_c5_wiring_2026_08_14.py -q
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_MOD = ROOT / "setup" / "scripts" / "heartbeat_core.py"
_spec = importlib.util.spec_from_file_location("heartbeat_core", _MOD)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

import conviction as cv  # noqa: E402

SAFE_PARAMS = json.loads((ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

# Per-day amplitude is deliberately SMALL relative to the multi-day drift, so a window-wide
# envelope and a session envelope are numerically far apart. That gap is what RED-proofs the
# session-scoping half of the fix.
_DAY_AMPLITUDE = 0.6
_DAY_DRIFT = 6.0


def _synth_multiday(n_days: int = 4) -> pd.DataFrame:
    """RTH 5m bars: a gentle intraday wiggle riding a large day-over-day drift."""
    rows = []
    base = 600.0
    for d in range(n_days):
        day = pd.Timestamp(f"2026-06-0{d + 1} 00:00", tz="America/New_York")
        t = day + pd.Timedelta(hours=9, minutes=30)
        end = day + pd.Timedelta(hours=16)
        i = 0
        prev = base
        while t < end:
            # small deterministic intraday oscillation around the day's base
            px = round(base + _DAY_AMPLITUDE * ((i % 8) / 8.0), 2)
            rows.append({"timestamp": t, "open": prev, "high": max(prev, px) + 0.01,
                         "low": min(prev, px) - 0.01, "close": px, "volume": 1_000_000})
            prev = px
            t += pd.Timedelta(minutes=5)
            i += 1
        base += _DAY_DRIFT
    return pd.DataFrame(rows)


def _payload():
    p = hc._build_payload(_synth_multiday(), SAFE_PARAMS, vix=(17.0, 17.2),
                          levels=([], []), vix_ma=(17.0, 17.0))
    assert p is not None, "fixture failed to produce a payload -- fix the fixture, not the guard"
    return p


# ---------------------------------------------------------------------------
# 1. THE TRANSPOSED KEY. Positive marker (trap #1: a claim and its retraction look
#    identical to grep, so assert on the AST of the function that must read it).
# ---------------------------------------------------------------------------
def _fn_ast(name: str) -> ast.FunctionDef:
    tree = ast.parse(_MOD.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in heartbeat_core.py")


def test_conviction_shadow_reads_session_envelope_keys():
    """The envelope must come from session_high/session_low -- never a bars list max/min."""
    src = ast.unparse(_fn_ast("_conviction_shadow"))
    assert "session_high" in src and "session_low" in src, (
        "C4's envelope inputs are gone from _conviction_shadow -- range_extreme will degrade "
        "on every tick again (it did, 102/102, until 2026-08-14)")


def test_no_code_anywhere_reads_the_transposed_key():
    """`bars_prior` is not a key this repo's producer ever writes. Reading it is the bug."""
    tree = ast.parse(_MOD.read_text(encoding="utf-8"))
    offenders = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and n.value == "bars_prior"]
    assert not offenders, (
        "heartbeat_core references the string 'bars_prior'; the producer writes 'prior_bars'. "
        "This exact transposition silently disabled conviction C4 from birth.")


def test_producer_still_emits_the_canonical_prior_bars_key():
    """Guard the other direction: the engine contract requires 'prior_bars'."""
    p = _payload()
    assert isinstance(p["bar_ctx"].get("prior_bars"), list) and p["bar_ctx"]["prior_bars"], (
        "bar_ctx lost 'prior_bars' -- engine_cli._require would fail closed on every tick")


# ---------------------------------------------------------------------------
# 2. SESSION SCOPING. The half of the fix that is invisible once C4 stops degrading.
# ---------------------------------------------------------------------------
def test_session_envelope_is_emitted_and_populated():
    bc = _payload()["bar_ctx"]
    assert bc.get("session_high") is not None and bc.get("session_low") is not None, (
        "session envelope absent -> C4 degrades exactly as it did before the fix")
    assert bc["session_high"] > bc["session_low"]


def test_session_envelope_is_ONE_session_not_the_whole_window():
    """RED-proof for the subtle half: a window-wide max/min spans ~1.9 sessions here."""
    bc = _payload()["bar_ctx"]
    sess_range = bc["session_high"] - bc["session_low"]
    prior = bc["prior_bars"]
    window_range = max(b["high"] for b in prior) - min(b["low"] for b in prior)
    assert sess_range < window_range / 2, (
        f"session envelope ({sess_range:.2f}) is not meaningfully narrower than the whole "
        f"150-bar window ({window_range:.2f}) -- C4 is scoring a MULTI-DAY range while its "
        "docstring claims intraday location")
    assert sess_range <= _DAY_AMPLITUDE + 0.2, (
        f"session envelope {sess_range:.2f} exceeds one synthetic day's amplitude "
        f"({_DAY_AMPLITUDE}) -- bars from a prior session leaked in")


def test_session_envelope_is_causal_no_look_ahead():
    """C6: the envelope may never see past the trigger bar (2nd-to-last bar of the window)."""
    df = _synth_multiday()
    bc = hc._build_payload(df, SAFE_PARAMS, vix=(17.0, 17.2), levels=([], []),
                           vix_ma=(17.0, 17.0))["bar_ctx"]
    # The final bar is the forward-confirmation bar; inflate it and the envelope must NOT move.
    df2 = df.copy()
    df2.loc[df2.index[-1], "high"] = float(df2["high"].max()) + 50.0
    df2.loc[df2.index[-1], "low"] = float(df2["low"].min()) - 50.0
    bc2 = hc._build_payload(df2, SAFE_PARAMS, vix=(17.0, 17.2), levels=([], []),
                            vix_ma=(17.0, 17.0))["bar_ctx"]
    assert (bc2["session_high"], bc2["session_low"]) == (bc["session_high"], bc["session_low"]), (
        "the post-trigger confirmation bar moved the envelope -- look-ahead (C6)")


# ---------------------------------------------------------------------------
# 3. C4 ACTUALLY SCORES. The assertion the old tests never made.
# ---------------------------------------------------------------------------
def test_range_extreme_no_longer_degrades_on_a_real_payload():
    res = hc._conviction_shadow({"side": "C"}, _payload(), "safe")
    assert res is not None and "error" not in res, f"conviction shadow errored: {res}"
    assert "range_extreme" not in (res.get("degraded_components") or ()), (
        "C4 still degrades on a real payload -- the 102/102 bug is back")
    assert "range_position" in (res.get("components") or {}), (
        "range_position is written ONLY on the non-degraded branch; its absence is the exact "
        "signature that proved C4 had never scored once")


def test_range_position_is_a_fraction():
    res = hc._conviction_shadow({"side": "C"}, _payload(), "safe")
    pos = res["components"]["range_position"]
    assert 0.0 <= pos <= 1.0, f"range_position {pos} is not a position within the envelope"


def test_hold_verdicts_still_skip_conviction_entirely():
    """Laziness guard: no sided verdict -> no work, no row (keeps the hot path cheap)."""
    assert hc._conviction_shadow({"side": None}, _payload(), "safe") is None
    assert hc._conviction_shadow({}, _payload(), "safe") is None


# ---------------------------------------------------------------------------
# 4. C5 THREADED. Was the literal `None`.
# ---------------------------------------------------------------------------
def test_structure_side_is_not_hardcoded_none():
    """Exact-node assert: the kwarg must not be a literal None (it was, since birth)."""
    fn = _fn_ast("_conviction_shadow")
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "structure_side":
                    assert not (isinstance(kw.value, ast.Constant) and kw.value.value is None), (
                        "structure_side is hardcoded None again -- C5 degrades on every tick "
                        "and the conviction ceiling drops back below its own floor")
                    return
    raise AssertionError("no structure_side kwarg found in _conviction_shadow")


def _mk_bars(closes: list[float]) -> list[dict]:
    """Same-day 5m bars in the producer's exact shape.

    TZ-AWARE `timestamp_iso` IS LOAD-BEARING, and this cost a false alarm during authorship:
    `crypto.lib.bar.Bar.__post_init__` raises on a naive datetime, `_classify_sameday_5m`
    swallows every exception and returns 'unknown', so naive fixtures make the classifier look
    permanently broken. It is not -- the live producer emits `2026-08-14T09:30:00-04:00` and
    the same call returned 'downtrend' on today's real bars. A fixture that is wrong in the
    direction of "everything is disabled" is the most expensive kind.
    """
    tz = dt.timezone(dt.timedelta(hours=-4))
    t0 = dt.datetime(2026, 6, 1, 9, 30, tzinfo=tz)
    return [{"open": px, "high": px + 0.4, "low": px - 0.4, "close": px, "volume": 1.0,
             "timestamp_iso": (t0 + dt.timedelta(minutes=5 * i)).isoformat()}
            for i, px in enumerate(closes)]


def _stairstep_up() -> list[float]:
    """Higher highs AND higher lows -- what classify_trend actually requires (a monotone
    ramp has no swing points at all and classifies 'unknown')."""
    out, px = [], 100.0
    for i in range(40):
        px += 2.5 if (i // 3) % 2 == 0 else -1.0
        out.append(round(px, 2))
    return out


def test_structure_side_maps_trend_to_the_agreeing_side():
    up = _stairstep_up()
    down = [round(200.0 - (p - 100.0), 2) for p in up]
    assert hc._sameday_structure_side({"sameday_5m_bars": _mk_bars(up)}) == "C"
    assert hc._sameday_structure_side({"sameday_5m_bars": _mk_bars(down)}) == "P"


def test_structure_side_degrades_rather_than_guessing():
    """range/unknown/missing -> None. 'No opinion' must never masquerade as agreement."""
    assert hc._sameday_structure_side({}) is None
    assert hc._sameday_structure_side({"sameday_5m_bars": []}) is None
    assert hc._sameday_structure_side({"sameday_5m_bars": [{"bad": 1}]}) is None


def test_structure_side_matches_the_live_veto_classifier():
    """One classifier, not two -- the shadow must never disagree with the gate that blocks."""
    from backtest.lib.engine.engine_cli import _classify_sameday_5m, _veto_side
    for closes in (_stairstep_up(), [round(200.0 - (p - 100.0), 2) for p in _stairstep_up()]):
        bars = _mk_bars(closes)
        side = hc._sameday_structure_side({"sameday_5m_bars": bars})
        assert side is not None
        assert not _veto_side(side, _classify_sameday_5m(bars)), (
            "the side C5 calls 'agreeing' is a side the live structure veto would BLOCK")
        other = "P" if side == "C" else "C"
        assert _veto_side(other, _classify_sameday_5m(bars)), (
            "vacuity check: the OPPOSITE side should be vetoed here, so this fixture actually "
            "exercises a confirmed trend rather than a fail-open 'unknown'")


# ---------------------------------------------------------------------------
# 5. C13 REACHABILITY. The finding that made this repair worth doing at all.
# ---------------------------------------------------------------------------
def test_observed_pre_fix_ceiling_reconstructs_from_the_weights():
    """The ONLY components ever observed scoring were named_level, fresh_test, elite_trigger
    (zone_stack scored on 10/102 rows but never co-occurred into a higher total). 2+1+1 = 4,
    and the on-disk total distribution was exactly {0: 34, 3: 26, 4: 42}: nothing above 4."""
    observed_max = cv.W_NAMED_LEVEL + cv.W_FRESH_TEST + cv.W_ELITE_TRIGGER
    assert observed_max == 4
    assert cv.effective_floor(0) == 5
    assert observed_max < cv.effective_floor(0), (
        "the pre-fix arithmetic no longer reproduces: conviction blocked 102/102 rows because "
        "its reachable total could not reach its own floor")


def test_conviction_is_satisfiable_with_c4_and_c5_live():
    """C13: a tier nothing can reach is not a filter, it is an off switch."""
    reachable = (cv.W_NAMED_LEVEL + cv.W_FRESH_TEST + cv.W_ELITE_TRIGGER
                 + cv.W_RANGE_EXTREME + cv.W_STRUCTURE)
    assert reachable > cv.effective_floor(0), (
        f"reachable ceiling {reachable} does not clear floor {cv.effective_floor(0)} -- "
        "conviction would still block 100% of verdicts, as it did on 102/102 rows")


def _code_string_constants() -> set:
    """Every string literal in the module EXCEPT docstrings.

    TRAP #3 (this week's own ledger, and I walked straight into it while writing this file):
    `"SKIP_LOW_CONVICTION" not in src` fails on the docstring that says *there is no
    SKIP_LOW_CONVICTION branch*. A mention is not an implementation, and a substring scan
    cannot tell a claim from its retraction. AST, always.
    """
    tree = ast.parse(_MOD.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings}


def test_conviction_still_disarmed_no_skip_branch_exists():
    """Non-negotiable ordering (handoff step 8): nothing may branch on would_block yet."""
    assert "SKIP_LOW_CONVICTION" not in _code_string_constants(), (
        "a conviction blocking branch appeared in CODE (not just prose); it ships only after "
        "the frozen F1-F4 gates clear, and this repair explicitly does NOT arm it")


def test_the_disarmed_check_is_not_vacuous():
    """Prove the AST scan can still see a real literal -- otherwise the guard above is a no-op
    that would stay green even if conviction were armed tomorrow."""
    consts = _code_string_constants()
    assert "SKIP_COLD_OPEN" in consts, (
        "the AST scan found no known live verdict literal, so it is not actually reading code")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
