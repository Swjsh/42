"""fill_latency TZ guard (2026-08-03 EOD process audit, Lens 4).

DEFECT PINNED: _parse_iso claimed 'naive == ET' but fed naive datetimes to .timestamp()
bare, which resolves them in the BOX's local zone (this rig runs Mountain, ET-2 -- the
et_clock scar). First live-population day (2026-08-03) produced hop values off by exactly
the 2h zone gap: bar_close->core_verdict = 7563.0s and core_verdict->signal = -7141.0s,
because bar_close/signal_written are tz-aware while core-decisions' ts_et is naive.

These tests RED on the pre-fix code ON THIS BOX (local != ET) and pin the fixed behavior:
naive stamps get ET_TZ attached before epoch conversion, so mixed naive/aware hops are
exact. Pure-function tests only -- no I/O, no network, no monkeypatching.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import fill_latency as flat  # noqa: E402


def test_naive_stage_is_treated_as_et_not_box_local():
    """The live 2026-08-03 exhibit: aware bar_close 09:35:00-04:00 -> naive verdict
    09:41:03 must be 363s, not 7563s (naive-as-Mountain) and not -6837s (naive-as-UTC)."""
    aware = flat._parse_iso("2026-08-03T09:35:00-04:00")
    naive = flat._parse_iso("2026-08-03T09:41:03")
    assert aware is not None and naive is not None
    assert naive - aware == 363.0


def test_naive_et_equals_same_instant_utc_z():
    """09:42:04.755794 naive (ET by producer convention) == 13:42:04.755794Z exactly."""
    naive_et = flat._parse_iso("2026-08-03T09:42:04.755794")
    aware_utc = flat._parse_iso("2026-08-03T13:42:04.755794Z")
    assert naive_et == aware_utc


def test_aware_pair_unaffected_by_fix():
    """Two aware stamps never touch the naive branch -- pre-fix behavior preserved."""
    a = flat._parse_iso("2026-08-03T09:42:02-0400")
    b = flat._parse_iso("2026-08-03T09:42:04.033570-04:00")
    assert round(b - a, 3) == 2.034


def test_stage_deltas_on_live_exhibit_row_is_sane():
    """End-to-end through stage_deltas with the REAL safe-3 2026-08-03 stage stamps:
    every hop non-negative, bar_close->verdict 363s, total == bar_close->fill 424.756s."""
    stages = {
        "bar_close_ts": "2026-08-03T09:35:00-04:00",
        "core_verdict_ts": "2026-08-03T09:41:03",
        "signal_written_ts": "2026-08-03T09:42:02-0400",
        "plan_ts": "2026-08-03T09:42:04.033570-04:00",
        "submit_ts": "2026-08-03T09:42:04.555666-04:00",
        "broker_submitted_ts": "2026-08-03T13:42:04.638997838Z",
        "fill_ts": "2026-08-03T13:42:04.755794Z",
    }
    d = flat.stage_deltas(stages)
    assert d["n_resolvable_stages"] == 7
    assert d["bar_close_ts_to_core_verdict_ts_s"] == 363.0
    assert d["core_verdict_ts_to_signal_written_ts_s"] == 59.0
    hop_keys = [k for k in d if k.endswith("_s") and k != "total_s"]
    assert all(d[k] is not None and d[k] >= 0 for k in hop_keys), d
    assert d["total_s"] == 424.756
