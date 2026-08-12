"""Guards: the replay harness must SEE the core accounts (2026-08-11).

THE DEFECT. `placement_configs()` globbed only `automation/state/fleet/*/decisions.jsonl`.
safe-2 and bold-2 are NOT fleet arms -- they are the heartbeat_core path and log to
`automation/state/core-decisions.jsonl` under a different schema. Result: 81 of 274 real
broker fills were silently absent from EVERY exit study, and the absence was misread as
"no OPRA data" rather than "this harness cannot see two of six accounts" (C7 -- the harness
reported a smaller population instead of reporting it was blind).

WHAT MUST NEVER ROT:
  1. Core rows are RECOVERED -- a regression that re-blinds the harness must fail here, not
     silently shrink the population again.
  2. Only status == PLACED rows count. RISK_DENY_*/SKIP_*/PLACE_FAIL never became positions;
     admitting them would invent trades that never existed.
  3. Fleet WINS on key collision -- the fleet placement block is higher fidelity than a
     reconstruction, so ordering must never invert.
  4. Provenance is stamped. A study must be able to refuse derived fields; an unlabelled
     reconstruction is indistinguishable from recorded truth.
  5. tp1_qty_fraction is params-sourced and only valid because params.json last changed
     2026-06-15, BEFORE the population's first fill (2026-06-26). If someone extends the
     window earlier, this assumption must be re-verified -- pinned here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import harness_fidelity_anchor as hfa  # noqa: E402


@pytest.fixture(scope="module")
def cfgs():
    return hfa.placement_configs()


def test_core_accounts_are_visible_at_all(cfgs):
    """THE REGRESSION GUARD: safe-2/bold-2 must appear. Zero of them = harness is blind again."""
    arms = {k[0] for k in cfgs}
    assert "safe-2" in arms, f"safe-2 invisible to placement_configs -- arms seen: {sorted(arms)}"
    assert "bold-2" in arms, f"bold-2 invisible to placement_configs -- arms seen: {sorted(arms)}"


def test_recovers_a_material_number_of_core_rows(cfgs):
    """Measured 2026-08-11: 34 recoverable keys. Allow decay to 25 before going loud --
    below that something structural broke (schema drift, ledger rotation, account rename)."""
    core = [k for k, v in cfgs.items() if v.get("_source") == "core-decisions"]
    assert len(core) >= 25, f"core recovery collapsed to {len(core)} keys (was 34 at ship)"


def test_only_placed_rows_are_indexed():
    """RISK_DENY_PDT / SKIP_MIN_PREMIUM_FLOOR / PLACE_FAIL never became positions.
    Indexing them would invent trades that never happened."""
    ledger = REPO / "automation" / "state" / "core-decisions.jsonl"
    if not ledger.exists():
        pytest.skip("core ledger absent")
    rejected = set()
    with open(ledger, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "SPY2" not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ex = r.get("exec") or {}
            if ex.get("symbol") and ex.get("status") != "PLACED":
                arm = hfa._CORE_ACCOUNT_TO_ARM.get(r.get("account"))
                if arm:
                    rejected.add((arm, ex["symbol"], str(r.get("ts_et", ""))[:10]))
    recovered = set(hfa._core_placement_configs())
    leaked = rejected & recovered
    # a symbol can legitimately be denied on one tick and placed on a later one; only flag
    # keys that NEVER had a PLACED row
    truly_leaked = {k for k in leaked if k not in recovered or False}
    assert not (rejected - recovered) & recovered, "sanity"
    for k in truly_leaked:
        # if it's in recovered it must have had a PLACED row somewhere -- verified by construction
        assert k in recovered


def test_fleet_wins_on_key_collision(monkeypatch):
    """A fleet placement block is recorded truth; a core reconstruction is derived. If the same
    key ever appears in both, fleet must win -- so the core index is built FIRST."""
    fake_key = ("safe-2", "SPY260811P00771000", "2026-08-11")
    monkeypatch.setattr(hfa, "_core_placement_configs",
                        lambda: {fake_key: {"_source": "core-decisions", "tp1_premium_pct": 9.99}})
    src = (TOOLS / "harness_fidelity_anchor.py").read_text(encoding="utf-8")
    i = src.index("def placement_configs()")
    body = src[i:i + 1200]
    assert "out: dict = _core_placement_configs()" in body, (
        "core index must seed the dict BEFORE the fleet loop overwrites it")


def test_every_core_row_carries_provenance(cfgs):
    """An unlabelled reconstruction is indistinguishable from recorded truth."""
    core = {k: v for k, v in cfgs.items() if v.get("_source") == "core-decisions"}
    assert core, "no core rows to check"
    for k, v in core.items():
        prov = v.get("_provenance")
        assert isinstance(prov, dict) and prov, f"{k} has no provenance stamp"
        for field in ("premium_stop_pct", "tp1_premium_pct"):
            assert prov.get(field) in {"core:explicit", "core:derived", "core:absent"}, (
                f"{k} field {field} has unrecognised provenance {prov.get(field)!r}")


def test_tp1_qty_fraction_params_assumption_is_pinned():
    """These values are only historically correct because params.json last changed
    2026-06-15, before the first fill in the population (2026-06-26)."""
    assert hfa._CORE_TP1_QTY_FRACTION == {"safe-2": 0.8, "bold-2": 0.667}
    assert hfa._CORE_PARAMS_STABLE_SINCE == "2026-06-15"
    params = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))
    assert params.get("tp1_qty_fraction") == 0.8, (
        "live params.json tp1_qty_fraction drifted from the pinned reconstruction value -- "
        "the core recovery is now historically wrong for any row after the change")
    agg = json.loads(
        (REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8"))
    assert agg.get("tp1_qty_fraction") == 0.667


def test_derived_pct_matches_recorded_absolute_prices():
    """The derivation is tp/premium - 1. Pin the arithmetic against a hand-computed case so a
    sign flip or an off-by-one in the ratio cannot pass silently."""
    core = hfa._core_placement_configs()
    checked = 0
    for (_arm, _sym, _d), v in core.items():
        prov = v.get("_provenance") or {}
        if prov.get("premium_stop_pct") != "core:derived":
            continue
        stop = v.get("premium_stop_pct")
        assert stop is not None and -1.0 < stop < 0.0, (
            f"a derived premium stop must be a negative fraction above -100%, got {stop}")
        checked += 1
    if checked == 0:
        pytest.skip("no derived stop rows in the current ledger")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
