"""Guard: loop_state_refresh heals a ribbon dict-of-nulls, not just a fully-null ribbon.

Scar (2026-08-28, full-suite RED --
test_state_contracts.py::test_live_json_file_validates[automation/state/loop-state.json]):
`_heal_nulls_from_beacon`'s ribbon-healing check was `ls.get("ribbon") is None`, written
against the ORIGINAL orphaned shape (ribbon key entirely absent/None). The CORE loop-state
file's actual shape is `ribbon: {"fast": null, ..., "stack": null}` -- a PRESENT dict whose
leaves are null -- which the `is None` check never matched, so `ribbon.stack`
(LoopStateModel's one non-Optional ribbon field) stayed null forever even with a fresh,
populated sight-beacon.json sitting right there.

This pins both shapes so neither can silently regress: a fully-null ribbon key, and a
present ribbon dict whose stack is null/falsy. Also pins that an already-healthy ribbon
(real stack value) is left untouched -- the healer must never overwrite live data with
beacon data, only fill a genuine gap.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import loop_state_refresh as lsr  # noqa: E402

_BEACON = {
    "ribbon_stack": "BEAR",
    "ema_fast": 769.3094,
    "ema_pivot": 769.3179,
    "ema_slow": 769.7255,
    "spread_cents": 41.6,
    "spy": 769.28,
}


def _write_beacon(tmp_path) -> None:
    (tmp_path / "sight-beacon.json").write_text(json.dumps(_BEACON), encoding="utf-8")


def test_heals_fully_null_ribbon_key(tmp_path):
    """The ORIGINAL scarred shape (ribbon key entirely None) still heals."""
    _write_beacon(tmp_path)
    ls = {"ribbon": None, "spy": {"last": None}}
    changed = lsr._heal_nulls_from_beacon(ls, tmp_path)
    assert changed is True
    assert ls["ribbon"]["stack"] == "BEAR"
    assert ls["ribbon"]["fast"] == _BEACON["ema_fast"]
    assert ls["spy"]["last"] == _BEACON["spy"]


def test_heals_ribbon_dict_of_nulls(tmp_path):
    """The 2026-08-28 recurrence: ribbon is a PRESENT dict, but stack (and siblings)
    are null -- this is the actual shape the live core loop-state.json carried."""
    _write_beacon(tmp_path)
    ls = {
        "ribbon": {"fast": None, "pivot": None, "slow": None, "spread_cents": None, "stack": None},
        "spy": {"last": None},
    }
    changed = lsr._heal_nulls_from_beacon(ls, tmp_path)
    assert changed is True, "a present-dict ribbon with a null stack must still be healed"
    assert ls["ribbon"]["stack"] == "BEAR"
    assert ls["ribbon"]["spread_cents"] == _BEACON["spread_cents"]


def test_does_not_overwrite_a_healthy_ribbon(tmp_path):
    """A ribbon that already carries a real stack value must never be clobbered by beacon
    data -- the healer fills gaps, it does not become a second writer of live fields."""
    _write_beacon(tmp_path)
    ls = {
        "ribbon": {"fast": 1.0, "pivot": 2.0, "slow": 3.0, "spread_cents": 4.0, "stack": "BULL"},
        "spy": {"last": 100.0},
    }
    changed = lsr._heal_nulls_from_beacon(ls, tmp_path)
    assert changed is False
    assert ls["ribbon"]["stack"] == "BULL"
    assert ls["spy"]["last"] == 100.0


def test_no_heal_when_beacon_itself_has_no_ribbon_stack(tmp_path):
    """Fail-open: a null ribbon with a beacon that also has no ribbon_stack stays null
    rather than writing a fabricated value."""
    (tmp_path / "sight-beacon.json").write_text(json.dumps({"spy": 100.0}), encoding="utf-8")
    ls = {"ribbon": {"fast": None, "pivot": None, "slow": None, "spread_cents": None, "stack": None}}
    changed = lsr._heal_nulls_from_beacon(ls, tmp_path)
    assert changed is False
    assert ls["ribbon"]["stack"] is None
