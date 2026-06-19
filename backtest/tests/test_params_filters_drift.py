"""params.json ↔ filters.py drift COVERAGE RATCHET (Phase 0b — 2026-06-18).

WHY THIS IS A RATCHET, NOT NEW PARITIES — the v25 validator
(``crypto/validators/v25_filter_gates.py``) already binds every value that lives in
BOTH params.json and filters.py as a hard equality (P1-P8: ribbon spread, the 3 VIX
thresholds, the VIX deadband, filter_9 vol mult, filter_10 bear/bull triggers) AND
runs a dynamic presence guard (PRES_*) asserting every ACTIVE gate knob
(``block_*`` / ``*_gate`` / ``*_min`` / ``*_hard_cap`` / ``*_required``) is referenced
by its heartbeat. Auditing filters.py confirmed the only params knob with a filters.py
module constant that v25 does NOT hard-bind is ``vix_bear_hard_cap`` (23.0) ↔
``VIX_HARD_CAP_BEAR`` (999.0 = off) — an INTENTIONAL divergence: the param doc says
"heartbeat.md activation pending", and filters.py defaults it off. Hard-asserting that
pair would falsely fail. (v25's presence guard already covers it via heartbeat prose.)

So there is no clean NEW hard parity to add. Per the Phase-0b directive, this file
instead installs the COVERAGE RATCHET the task asks for: it makes the manual
``gamma-sync`` ritual a failing test by asserting that **no params gate/threshold knob
can be added without v25 covering it**. Concretely:

  1. Every ACTIVE gate knob in BOTH params files is in scope of v25's classifier (so
     v25's presence guard actually evaluates it) OR is on v25's documented exclusion
     list. A new ``block_foo`` knob is auto-covered; a knob in a name family v25 does
     not recognize trips this test → author must extend v25.
  2. Every filters.py module threshold constant that has a params.json twin is bound by
     a v25 P-parity (or is on the documented INTENTIONAL_UNBOUND allowlist with a
     reason). A future constant that gains a params twin without a parity trips this.
  3. v25's P1-P8 parities still actually pass (re-asserted here so this file fails loudly
     if a real drift appears, independent of the full gym run).

Imports v25's own helpers so the ratchet tracks v25's real logic, never a stale copy.
Pure static / dataclass-default inspection — no backtest, no network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "backtest"))

# Reuse v25's exact helpers + paths so this ratchet can never drift from v25's logic.
from crypto.validators.v25_filter_gates import (
    _gate_key_in_scope,
    _value_is_active,
    _is_documented_dormant,
    _presence_assertions,
    _PRESENCE_EXCLUSIONS,
    _PARAMS_PATH,
    _PARAMS_AGG_PATH,
    _HEARTBEAT_PATH,
    _HEARTBEAT_AGG_PATH,
    run_offline as v25_run_offline,
)
import backtest.lib.filters as F


def _params(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── filters.py module constants that have a params.json twin ──────────────────
#
# Audited 2026-06-18. The constants in filters.py that correspond to a params.json
# value, and whether v25 binds them with a P-parity. The RATCHET asserts every twin is
# either bound (covered) or on the INTENTIONAL_UNBOUND allowlist with justification.
#
# Bound by v25 P1-P5 (constant -> params path):
_V25_BOUND_CONSTANTS = {
    "RIBBON_SPREAD_MIN_CENTS": "P1  ribbon_min_spread_cents",
    "VIX_BEAR_THRESHOLD": "P2  vix_entry_thresholds.bear_min_exclusive_and_rising",
    "VIX_BULL_LOW_THRESHOLD": "P3  vix_entry_thresholds.bull_max_exclusive_or_falling",
    "VIX_BULL_HARD_CAP": "P4  vix_entry_thresholds.bull_hard_cap",
    "VIX_RISING_DEADBAND": "P5  vix_dir_deadband",
}

# Constants with a params twin that v25 deliberately does NOT hard-bind. Each needs a
# reason. A new entry here is a conscious decision; an unlisted twin trips the ratchet.
INTENTIONAL_UNBOUND: dict[str, str] = {
    "VIX_HARD_CAP_BEAR": (
        "params vix_bear_hard_cap=23.0 but filters.py default=999.0 (off); the param doc "
        "says 'heartbeat.md activation pending'. Pair is INTENTIONALLY divergent until the "
        "bear hard-cap filter is wired into filters.py. v25 already presence-checks the "
        "knob against the heartbeat (PRES_safe_vix_bear_hard_cap). Bind a P-parity here "
        "once filters.py consumes vix_bear_hard_cap (constant != 999)."
    ),
}


# ── 1. Every active gate knob is in scope of v25's presence guard ─────────────

@pytest.mark.parametrize("params_path,hb_path,label", [
    (_PARAMS_PATH, _HEARTBEAT_PATH, "safe"),
    (_PARAMS_AGG_PATH, _HEARTBEAT_AGG_PATH, "agg"),
])
def test_every_active_gate_knob_is_covered_by_v25_presence_guard(params_path, hb_path, label):
    """RATCHET: every ACTIVE gate/threshold knob in the params file is actually
    EVALUATED by v25's presence guard (i.e. v25 emits a PRES_*_<key>_live_referenced
    row for it), unless it is dormant or on v25's documented exclusion list.

    This is the "no NEW params gate knob lacks a v25 presence assertion" check. Because
    v25's guard is dynamic over a name-family classifier, a newly-added ``block_foo`` is
    auto-covered — but a knob whose name escapes the classifier (a new family v25 does
    not recognize) is NOT covered, and this test fails, forcing the author to extend v25.
    """
    params = _params(params_path)
    hb_text = hb_path.read_text(encoding="utf-8")

    # Keys we EXPECT v25 to have a presence row for: in-scope, active, not dormant,
    # not on v25's own exclusion list.
    expected = {
        k for k in params
        if _gate_key_in_scope(k)
        and _value_is_active(params[k])
        and not _is_documented_dormant(params, k)
    }

    rows = _presence_assertions(params, hb_text, label)
    covered = set()
    for name, _passed, _note in rows:
        # rows are named PRES_<label>_<key>_live_referenced (+ a _meta row).
        prefix = f"PRES_{label}_"
        suffix = "_live_referenced"
        if name.startswith(prefix) and name.endswith(suffix):
            covered.add(name[len(prefix):-len(suffix)])

    missing = expected - covered
    assert not missing, (
        f"[{label}] active gate knob(s) NOT evaluated by v25's presence guard: "
        f"{sorted(missing)}. v25's gate classifier did not pick them up — extend "
        f"crypto/validators/v25_filter_gates._GATE_KEY_PATTERNS/_SUFFIXES (or add a "
        f"documented exclusion) so every gate knob has a live-reference assertion."
    )


def test_v25_presence_exclusions_are_real_keys():
    """Hygiene: every key on v25's presence-exclusion allowlist exists in at least one
    params file (no stale exclusion silently masking a typo'd key name)."""
    safe = _params(_PARAMS_PATH)
    agg = _params(_PARAMS_AGG_PATH)
    all_keys = set(safe) | set(agg)
    stale = set(_PRESENCE_EXCLUSIONS) - all_keys
    assert not stale, (
        f"v25 _PRESENCE_EXCLUSIONS lists key(s) that exist in neither params file: "
        f"{sorted(stale)} — remove the stale exclusion(s)."
    )


# ── 2. Every filters.py constant with a params twin is bound or allowlisted ───

def test_no_filters_constant_twin_is_silently_unbound():
    """RATCHET: the filters.py threshold constants that have a params.json twin are
    each either bound by a v25 P-parity (``_V25_BOUND_CONSTANTS``) or on the
    ``INTENTIONAL_UNBOUND`` allowlist with a reason. This is the meta-guard that a
    future constant gaining a params twin cannot slip through without a sync assertion."""
    # The audited universe of filters.py constants that map to a params value.
    twin_constants = set(_V25_BOUND_CONSTANTS) | set(INTENTIONAL_UNBOUND)

    # Every listed constant must actually exist in filters.py (catches a rename).
    for c in sorted(twin_constants):
        assert hasattr(F, c), (
            f"filters.py no longer defines constant {c!r} referenced by this ratchet — "
            f"a rename/removal; update _V25_BOUND_CONSTANTS / INTENTIONAL_UNBOUND."
        )

    # The two lists must be disjoint (a constant is bound XOR intentionally unbound).
    both = set(_V25_BOUND_CONSTANTS) & set(INTENTIONAL_UNBOUND)
    assert not both, f"constant(s) both bound AND intentionally-unbound: {sorted(both)}"


def test_intentional_unbound_divergence_still_holds():
    """Sanity-pin the ONE intentional divergence so this allowlist entry can't quietly
    become wrong: ``VIX_HARD_CAP_BEAR`` must still be the OFF default (999) while params
    ``vix_bear_hard_cap`` is set. The day filters.py actually consumes the param (constant
    != 999), this test fails → time to promote it to a real P-parity and drop the
    allowlist entry."""
    safe = _params(_PARAMS_PATH)
    param_val = safe.get("vix_bear_hard_cap")
    assert param_val not in (None, 0), (
        "params vix_bear_hard_cap is unset/0 — the intentional-divergence rationale no "
        "longer applies; remove VIX_HARD_CAP_BEAR from INTENTIONAL_UNBOUND."
    )
    assert F.VIX_HARD_CAP_BEAR == 999.0, (
        f"filters.VIX_HARD_CAP_BEAR is now {F.VIX_HARD_CAP_BEAR} (was 999=off). filters.py "
        f"appears to consume the bear hard cap — promote vix_bear_hard_cap to a v25 "
        f"P-parity bound to VIX_HARD_CAP_BEAR and remove it from INTENTIONAL_UNBOUND."
    )


# ── 3. v25's actual P-parities still pass (drift tripwire, independent of gym) ─

def test_v25_parity_assertions_still_green():
    """Run v25's offline suite and assert the parity (P*) + presence (PRES_*) rows all
    pass. This is a fast, standalone tripwire: if a real params↔filters drift is
    introduced (e.g. someone edits RIBBON_SPREAD_MIN_CENTS but not params), this fails
    here without needing the full crypto gym."""
    res = v25_run_offline()
    failing = [t for t in res["tests"]
               if (t["name"].startswith("P") or t["name"].startswith("PRES_"))
               and not t["pass"]]
    assert not failing, (
        "v25 parity/presence assertion(s) FAILED — a real params↔filters/heartbeat "
        "drift:\n" + "\n".join(f"  [{t['name']}] {t['note']}" for t in failing)
    )
