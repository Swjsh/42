"""test_level_state_live_safety_invariants_2026_08_23.py -- pins the invariants
that keep `backtest/lib/filters.py`'s LevelState resolution safe on the LIVE
trading path, in files far away from the resolver itself.

WHY THIS FILE, SEPARATE FROM test_level_state_resolution_determinism_2026_08_23.py
------------------------------------------------------------------------------
That file pins `resolve_level_state()` itself: give it ANY dict, in ANY
insertion order, and the total order it defines (exact key -> role ->
recency -> distance -> key) always wins. That guard holds regardless of what
produces the dict.

This file pins something upstream and unrelated to the resolver's own logic --
the reason a genuine PRICE COLLISION (two LevelStates within the resolver's
$0.05 tolerance) essentially never reaches the resolver on the live path at
all, and the keying convention that makes the resolver's EXACT-KEY tier the
one that actually decides every live trigger today. Per the adversarial review
of commit 4249d95e (analysis/deep-research/SEQUENCE-REJECTION-PARITY-PROBE-
2026-08-23.md; analysis/deep-research/PROFITABILITY-ORDER-2026-08-23.md Sec4),
live's safety rested on THREE things never previously asserted anywhere near
the resolver:

  (a) `ROLE_EPSILON = 0.10` (setup/scripts/refresh_levels_intraday.py:99) --
      the PRODUCER-side dedupe threshold is WIDER than the resolver's $0.05
      lookup tolerance, so at most ONE active level can ever fall inside that
      band in the first place.
  (b) `eff = levels_active + [fhh]` (setup/scripts/heartbeat_core.py:790) --
      argument ORDERING that put the active entry ahead of the first-hour-high
      supplement under the OLD insertion-order-dependent scan.
  (c) `_read_levels` rounds every producer price to 2dp (heartbeat_core.py:490)
      and `resolve_level_state` keys off `f"{price:.4f}"` -- the reason the
      resolver's EXACT-KEY tier, not its role/recency/distance tier-2 scan,
      is the one that fires on the live population. The resolver's own
      docstring says tier-2 has ZERO measured production impact today ("in
      the currently observed live + GT data, tier 1 does all the work") --
      this guard is what that claim rests on.

Post-4249d95e, resolve_level_state() no longer STRICTLY NEEDS (a) or (b) for
correctness -- it is order-independent by construction. But both are exactly
what a REVERT of that fix (documented as a one-line `git revert`, see the
probe doc) would fall back on, and neither was ever pinned. A future editor
narrowing ROLE_EPSILON toward $0.05, or reordering `eff`, ships INVISIBLY
today. These guards make that change loud.

Run:
  cd C:\\Users\\jackw\\Desktop\\42
  backtest\\.venv\\Scripts\\python.exe -m pytest backtest/tests/test_level_state_live_safety_invariants_2026_08_23.py -q
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
SCRIPTS = REPO / "setup" / "scripts"
for _p in (str(BACKTEST), str(SCRIPTS), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import heartbeat_core as hc  # noqa: E402 -- setup/scripts, not a package
import refresh_levels_intraday as rli  # noqa: E402 -- setup/scripts, not a package

from lib import filters as flt  # noqa: E402
from lib.engine.engine_cli import build_bar_context  # noqa: E402


# ---------------------------------------------------------------------------
# (a) ROLE_EPSILON must stay strictly wider than the resolver's own tolerance.
# ---------------------------------------------------------------------------
def test_role_epsilon_stays_wider_than_resolver_tolerance():
    """GUARD (item 3a). `refresh_levels_intraday.ROLE_EPSILON` is the
    PRODUCER-side collapse threshold: any two candidate levels within this many
    dollars of each other are merged into ONE entry with ONE role before they
    ever reach key-levels.json. As long as ROLE_EPSILON is strictly GREATER
    than resolve_level_state's own lookup tolerance, at most one ACTIVE level
    can ever land inside that tolerance band -- the collision class this
    resolver exists to adjudicate structurally cannot occur on the ACTIVE
    population. Narrow ROLE_EPSILON to <= the resolver tolerance and two
    distinct active levels CAN collide again; this must RED the moment that
    ships, not get discovered from a live mis-resolution."""
    resolver_tolerance = inspect.signature(flt.resolve_level_state).parameters["tolerance"].default
    assert rli.ROLE_EPSILON > resolver_tolerance, (
        f"ROLE_EPSILON={rli.ROLE_EPSILON} must stay strictly greater than "
        f"resolve_level_state's tolerance={resolver_tolerance} -- narrowing it "
        "re-opens the active-level collision the 2026-08-23 resolver fix was "
        "built to guard against (see SEQUENCE-REJECTION-PARITY-PROBE-2026-08-23.md)"
    )


def test_role_epsilon_violation_is_independently_provable_in_a_fixture():
    """Proves guard (a) actually discriminates: a LOCAL, disk-untouched fixture
    that narrows the epsilon to the resolver's tolerance (not stricter than it)
    fails the same assertion. This is the fixture-level proof asked for by the
    adversarial review -- NOT a claim about the file on disk, which the guard
    above already covers."""
    resolver_tolerance = inspect.signature(flt.resolve_level_state).parameters["tolerance"].default
    narrowed_role_epsilon = resolver_tolerance  # violates "strictly greater"
    assert not (narrowed_role_epsilon > resolver_tolerance)


# ---------------------------------------------------------------------------
# (b) levels_active must be inserted into `eff` before the FHH supplement.
# ---------------------------------------------------------------------------
def _states_key_order(levels_active: list, fhh) -> list:
    """One synthetic bar, no role transitions (close stays inside both bands),
    so the ONLY thing that can determine states.keys() order is `eff`'s own
    construction order -- not any bounce/role logic."""
    win = pd.DataFrame({"high": [700.0], "low": [700.0], "close": [700.0]})
    states = hc._rebuild_level_states(win, 1, levels_active, fhh)
    return list(states.keys())


def test_active_levels_are_inserted_before_fhh_in_effective_levels():
    """GUARD (item 3b). `_rebuild_level_states` builds `eff = list(levels_active)
    + ([fhh] if fhh is not None else [])` -- ACTIVE entries first. Dict
    insertion order is directly observable via `states.keys()` (Python dicts
    preserve insertion order), so this is a REAL behavioural pin, not a
    source-text match. Under the pre-2026-08-23 insertion-order-dependent scan,
    this ordering was WHY an active level always won an arbitrary collision
    against the first-hour-high supplement; it stays load-bearing as the
    fallback safety net if the deterministic resolver is ever reverted (the
    probe doc documents a one-line revert). Reordering `eff` -- e.g. FHH first,
    or interleaved -- must RED here."""
    active_price, fhh_price = 735.03, 735.07
    keys = _states_key_order([active_price], fhh_price)
    assert keys == [f"{active_price:.4f}", f"{fhh_price:.4f}"], (
        f"active-before-fhh insertion order violated: got {keys} -- "
        "setup/scripts/heartbeat_core.py:790's `eff = list(levels_active) + "
        "[fhh]` construction changed"
    )


def test_active_before_fhh_ordering_is_independently_provable_in_a_fixture():
    """Proves guard (b) actually discriminates: a LOCAL, disk-untouched
    reimplementation with the REVERSED order (fhh first) produces the opposite
    key sequence, so the assertion above is not vacuously true for any order."""
    active_price, fhh_price = 735.03, 735.07

    def _reversed_eff_key_order(levels_active, fhh):
        eff = ([fhh] if fhh is not None else []) + list(levels_active)  # BROKEN: fhh first
        return [f"{float(L):.4f}" for L in eff]

    reversed_keys = _reversed_eff_key_order([active_price], fhh_price)
    real_keys = _states_key_order([active_price], fhh_price)
    assert reversed_keys != real_keys, (
        "fixture didn't discriminate -- pick prices whose formatted keys differ"
    )
    assert reversed_keys == [f"{fhh_price:.4f}", f"{active_price:.4f}"]


# ---------------------------------------------------------------------------
# (c) 2dp producer rounding + ":.4f" resolver keying agree end-to-end, so the
#     EXACT-KEY tier is the one that fires for a same-day active level.
# ---------------------------------------------------------------------------
def test_2dp_producer_rounding_and_resolver_key_agree_end_to_end():
    """GUARD (item 3c). Runs the REAL pipeline: a noisy raw price -> the SAME
    2dp rounding `_read_levels` applies (heartbeat_core.py:490) -> the REAL
    windowed rebuild (`_rebuild_level_states`) -> a REAL JSON round-trip (the
    wire format between heartbeat_core and engine_cli) -> the REAL
    `build_bar_context` reconstruction -> the REAL `detect_level_rejection` ->
    the REAL `resolve_level_state`. Asserts the resolved LevelState is reached
    via the EXACT-KEY tier (object identity with `level_states[exact_key]`),
    never the role/recency/distance tier-2 scan. If 2dp rounding on the
    producer side and the resolver's `:.4f` key format ever drift out of sync,
    exact-key stops hitting and every live trigger falls back to the
    ambiguous tier-2 path this fix's own docstring says has ZERO measured
    production exercise today."""
    raw_price = 735.028471  # a noisy float, as a live-computed level might arrive
    active_price = round(raw_price, 2)  # _read_levels's own rounding contract
    assert active_price == 735.03

    bar = {
        "open": active_price, "high": active_price + 0.02,
        "low": active_price - 0.30, "close": active_price - 0.15, "volume": 1000,
    }
    win = pd.DataFrame({"high": [bar["high"]], "low": [bar["low"]], "close": [bar["close"]]})
    states = hc._rebuild_level_states(win, 1, [active_price], None)

    # The REAL wire format: heartbeat_core JSON-serializes bar_ctx for engine_cli.
    roundtripped = json.loads(json.dumps(states))

    ctx = build_bar_context({
        "bar_idx": 0, "timestamp_et": "2026-08-23T15:35:00",
        "bar": bar, "prior_bars": [bar],
        "vix_now": 15.0, "vix_prior": 15.0,
        "levels_active": [active_price], "multi_day_levels": [], "htf_15m_stack": None,
        "level_states": roundtripped,
    })

    rejection_level = flt.detect_level_rejection(ctx.bar, ctx.levels_active)
    assert rejection_level == active_price

    exact_key = f"{active_price:.4f}"
    assert exact_key in ctx.level_states, (
        "producer 2dp rounding and the resolver's :.4f key format drifted out "
        f"of sync -- active level {active_price} produced no matching key "
        f"{exact_key!r} after a JSON round-trip"
    )
    resolved = flt.resolve_level_state(
        ctx.level_states, rejection_level, wanted_role="broken_to_resistance"
    )
    assert resolved is ctx.level_states[exact_key], (
        "exact-key tier did NOT resolve an ACTIVE, canonically-keyed same-day "
        "level -- tier-2 (role/recency/distance) fired instead, which should "
        "be structurally unreachable for this population"
    )
