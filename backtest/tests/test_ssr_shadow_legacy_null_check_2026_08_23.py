"""test_ssr_shadow_legacy_null_check_2026_08_23.py -- guard against the data-loss defect
introduced by commit 77442e70 (the ssr-v2 respec): `compute_progress`'s `legacy_evidence`
block retained v1's `n_round_trips`/`total_pnl_usd` (the flattering half of the evidence
pair) but silently DROPPED v1's `null_check` (the half that made SSR's exits interesting --
v1 had n=17, +$27,335.69 absolute, but FAILED beats_null: an unmanaged hold to the same
closing bar returned +$30,828.09, ~$3,492 MORE). That un-sourced a figure already cited in
analysis/deep-research/PROFITABILITY-ORDER-2026-08-23.md and automation/overnight/queue.md.

THE GENERAL RULE this guards: a quarantine that preserves the flattering half of retired
evidence (P&L) and drops the unflattering half (the null it failed) is WORSE than deleting
both -- it leaves a citable number with its refutation removed. A respec must preserve the
WHOLE legacy evidence record or none of it, never split the pair.

REDs on regression if a future edit:
  (a) drops `legacy_evidence.null_check` again (the exact defect this file was written for),
  (b) lets `legacy_evidence.null_check` report evaluated=False while real legacy round trips
      with resolvable entry/close/direction/config exist (i.e. computes the P&L half but
      silently skips the null half),
  (c) loses the "ssr-v1 / HISTORICAL / NOT counted toward v2 arming_bar" label so a reader
      could mistake the legacy null for current-spec evidence,
  (d) lets legacy evidence (P&L OR null) leak into the v2 `arming_bar`'s three-condition AND
      (n>=20 AND positive_expectancy AND beats_null) -- that gate must stay computed
      exclusively from ssr-v2-tagged round trips.

No network calls -- compute_progress is exercised with hand-built ledger rows and a fake
instrument lookup (same isolation pattern as test_ssr_shadow.py / test_ssr_shadow_v2_respec.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import ssr_shadow  # noqa: E402

ET = "America/New_York"


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Same isolation pattern as the rest of the ssr_shadow suite -- never touches the real
    automation/state/futures/ssr-shadow-* files."""
    monkeypatch.setattr(ssr_shadow, "STATE_FILE", tmp_path / "ssr-shadow-state.json")
    monkeypatch.setattr(ssr_shadow, "LEDGER_FILE", tmp_path / "ssr-shadow-would-be.jsonl")
    monkeypatch.setattr(ssr_shadow, "PROGRESS_FILE", tmp_path / "ssr-shadow-progress.json")
    monkeypatch.setattr(ssr_shadow, "LOCK_FILE", tmp_path / "ssr-shadow.lock")
    monkeypatch.setattr(ssr_shadow, "LOG_DIR", tmp_path / "logs")
    return tmp_path


class _FakeInstrument:
    def __init__(self, point_value: float = 20.0, round_turn_usd: float = 4.0):
        self.point_value = point_value
        self.round_turn_usd = round_turn_usd


def _fake_lookup(_cfg):
    return _FakeInstrument(point_value=20.0, round_turn_usd=4.0)


def _legacy_v1_row_pair(signal_ref, *, entry, close, pnl_usd, direction="short"):
    """Rows shaped EXACTLY like the real pre-respec ledger: no `spec_version` key at all
    (that field did not exist before this respec) and `config` still the retired full-size
    literal ("NQ") -- absence of spec_version is itself how a legacy row is recognized."""
    return [
        {"ts_et": "2026-08-03T10:00:00-04:00", "config": "NQ", "signal_ref": signal_ref,
        "direction": direction, "event": "entry", "entry": entry, "fill_price": entry,
        "bar_close": entry, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0},
        {"ts_et": "2026-08-03T11:00:00-04:00", "config": "NQ", "signal_ref": signal_ref,
        "direction": direction, "event": "closed", "reason": "runner", "entry": entry,
        "fill_price": close, "bar_close": close, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": pnl_usd},
    ]


def _v2_row_pair(signal_ref, *, pnl_usd, entry=20000.0, bar_close, day="24", hour=9):
    """Rows shaped like a post-respec fill: config="MNQ" (a live CONFIGS key) and
    spec_version stamped, exactly what _entry_event/_row now write."""
    ts = f"2026-08-{day}T{hour:02d}"
    return [
        {"ts_et": f"{ts}:00:00-04:00", "config": "MNQ", "signal_ref": signal_ref,
        "direction": "short", "event": "entry", "entry": entry, "fill_price": entry,
        "bar_close": entry, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0,
        "spec_version": "ssr-v2"},
        {"ts_et": f"{ts}:30:00-04:00", "config": "MNQ", "signal_ref": signal_ref,
        "direction": "short", "event": "closed", "reason": "runner", "entry": entry,
        "fill_price": bar_close, "bar_close": bar_close, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": pnl_usd, "spec_version": "ssr-v2"},
    ]


# ── (a) THE PRIMARY REGRESSION GUARD: legacy_evidence must carry ALL THREE fields ──────────
def test_legacy_evidence_never_drops_the_null_half_of_the_evidence_pair():
    """One legacy round trip: entry 15000 -> close 14900, short, qty 3, managed pnl 500.
    Same-direction unmanaged hold = (15000-14900)*20*3 - 4*3 = 5988; managed 500 does NOT
    beat that -> beats_null False. This is the exact shape of the real v1 failure (managed
    exits subtract value vs an unmanaged hold), just with small round numbers so the expected
    null figure can be hand-verified instead of trusted."""
    rows = _legacy_v1_row_pair("NQ|short|PDH|2026-08-03T09:45", entry=15000.0, close=14900.0,
                               pnl_usd=500.0)
    progress = ssr_shadow.compute_progress(rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))

    legacy = progress["legacy_evidence"]
    # THE P&L HALF (already correctly preserved pre-fix -- must stay correct)
    assert legacy["n_round_trips"] == 1
    assert legacy["total_pnl_usd"] == pytest.approx(500.0)
    # THE NULL HALF (this is what commit 77442e70 dropped -- the regression this file guards)
    assert "null_check" in legacy, "legacy_evidence lost its null_check block entirely"
    nc = legacy["null_check"]
    assert nc["evaluated"] is True, (
        "legacy_evidence computed the P&L half but silently skipped the null half -- "
        "exactly the defect this guard exists for.")
    assert nc["null_total_pnl_usd"] == pytest.approx(5988.0)
    assert nc["beats_null"] is False
    assert nc["coverage"] == "1/1"
    assert nc["unavailable"] == 0


def test_legacy_null_check_labeled_ssr_v1_historical_not_arming():
    """The restored null_check must be unmistakably labeled as retired/non-arming -- matching
    the existing quarantine discipline already applied to n_round_trips/total_pnl_usd (the
    `status`/`note` fields), so a reader can never mistake it for current-spec (v2) evidence."""
    rows = _legacy_v1_row_pair("NQ|short|PDH|2026-08-03T09:45", entry=15000.0, close=14900.0,
                               pnl_usd=500.0)
    progress = ssr_shadow.compute_progress(rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    label = progress["legacy_evidence"]["null_check"].get("label", "")
    assert "ssr-v1" in label
    assert "HISTORICAL" in label.upper() or "NOT counted" in label
    assert "v2" in label.lower() or "arming" in label.lower()


def test_legacy_null_check_reproduces_the_real_pre_respec_figures():
    """Pin against the ACTUAL pre-respec ledger state at the moment of the 2026-08-23 respec
    (n=17, +$27,335.69 managed, +$30,828.09 unmanaged null, beats_null False) -- the exact
    figures the downstream citation (analysis/deep-research/PROFITABILITY-ORDER-2026-08-23.md)
    lost its source for. Built by hand here (isolated, no real-file reads) with 17 identical
    per-trip rows summing to the cited totals, using the SAME entry/close/qty shape as the
    other pre-respec pin (test_ssr_shadow_v2_respec.py::test_live_progress_shape_matches_the_
    real_current_ledger_state) so a reviewer can cross-check both against the same snapshot."""
    per_trip_pnl = round(27335.69 / 17, 2)
    per_trip_null = round(30828.09 / 17, 2)
    # solve entry/close pair per-trip that reproduces both pnl and null under _fake_lookup
    # (point_value=20, round_turn_usd=4, qty=3): pnl = qty*pv*d_managed - rt*qty (managed exit
    # at a worse price than the bar close); null = qty*pv*d_full - rt*qty (unmanaged hold to
    # the SAME bar close). Choose bar_close/entry directly rather than back-solving a fill.
    rows: list[dict] = []
    for i in range(17):
        entry = 15000.0
        close = entry - (per_trip_null + 4.0 * 3) / (20.0 * 3)  # unmanaged hold pts
        fill = entry - (per_trip_pnl + 4.0 * 3) / (20.0 * 3)    # managed exit pts (worse price)
        rows += _legacy_v1_row_pair(f"NQ|short|PDH|2026-08-{i + 1:02d}T09:45", entry=entry,
                                    close=close, pnl_usd=per_trip_pnl)
        rows[-1]["fill_price"] = fill  # managed exit fills worse than the bar close (the gap)

    progress = ssr_shadow.compute_progress(rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    legacy = progress["legacy_evidence"]
    assert legacy["n_round_trips"] == 17
    assert legacy["total_pnl_usd"] == pytest.approx(27335.69, abs=0.5)
    assert legacy["null_check"]["evaluated"] is True
    assert legacy["null_check"]["null_total_pnl_usd"] == pytest.approx(30828.09, abs=0.5)
    assert legacy["null_check"]["beats_null"] is False


# ── (b) v2 arming bar stays computed EXCLUSIVELY from v2-tagged evidence ───────────────────
def test_v2_arming_bar_unaffected_by_legacy_evidence_either_direction():
    """Legacy evidence (P&L and now null) must never leak into the v2 arming_bar in EITHER
    direction: a legacy population that FAILS beats_null must not drag down a v2 population
    that PASSES, and (checked separately below) a legacy population that would pass must
    never rescue a v2 population that fails. The arming bar's three-condition AND must be
    computed exclusively from ssr-v2-tagged round trips."""
    legacy_rows = _legacy_v1_row_pair("NQ|short|PDH|2026-08-03T09:45", entry=15000.0,
                                      close=14900.0, pnl_usd=500.0)  # legacy FAILS beats_null

    v2_rows: list[dict] = []
    for i in range(20):
        v2_rows += _v2_row_pair(f"MNQ|short|PDH|2026-08-{24}T{i:02d}:00", pnl_usd=100.0,
                                bar_close=19999.0, hour=i % 24)
    progress = ssr_shadow.compute_progress(legacy_rows + v2_rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-25T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 20
    assert progress["positive_expectancy"] is True
    assert progress["arming_bar"]["beats_null"] is True, (
        "a small unmanaged-hold delta (entry 20000 -> bar_close 19999) beaten by a $100/trip "
        "managed exit must evaluate True on v2's OWN evidence, regardless of the legacy "
        "population's own (failing) beats_null.")
    assert progress["arming_bar"]["armable"] is True
    # the legacy population's failure is fully isolated in legacy_evidence, never in arming_bar
    assert progress["legacy_evidence"]["null_check"]["beats_null"] is False


def test_v2_arming_bar_still_requires_all_three_conditions_with_legacy_present():
    """Even with a full legacy_evidence null_check present, armable must still require ALL
    THREE v2-only conditions (n>=20 AND positive_expectancy AND beats_null) -- restoring the
    legacy null field must not weaken or bypass this gate."""
    legacy_rows = _legacy_v1_row_pair("NQ|short|PDH|2026-08-03T09:45", entry=15000.0,
                                      close=14900.0, pnl_usd=27335.69)  # legacy PASSES pnl>0

    # v2 population meets n>=20 and positive_expectancy but FAILS beats_null (managed exit
    # worse than an unmanaged hold to the same bar_close) -- armable must stay False.
    v2_rows: list[dict] = []
    for i in range(20):
        v2_rows += _v2_row_pair(f"MNQ|short|PDH|2026-08-{24}T{i:02d}:00", pnl_usd=10.0,
                                bar_close=19900.0, hour=i % 24)
    progress = ssr_shadow.compute_progress(legacy_rows + v2_rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-25T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 20
    assert progress["positive_expectancy"] is True
    assert progress["arming_bar"]["beats_null"] is False, (
        "v2's own null_check must fail here regardless of the legacy population's positive "
        "P&L -- a respec must never let legacy evidence rescue a failing v2 arming bar.")
    assert progress["arming_bar"]["armable"] is False


def test_fresh_v2_clock_reads_zero_and_not_evaluated_with_only_legacy_rows():
    """With ONLY legacy (pre-respec) rows in the ledger, the v2 clock must read n=0 and its
    own top-level null_check must be not-evaluated -- the 'fresh forward clock' invariant --
    while legacy_evidence.null_check is fully evaluated alongside it."""
    rows = _legacy_v1_row_pair("NQ|short|PDH|2026-08-03T09:45", entry=15000.0, close=14900.0,
                               pnl_usd=500.0)
    progress = ssr_shadow.compute_progress(rows, instrument_lookup=_fake_lookup,
                                           now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 0
    assert progress["null_check"]["evaluated"] is False
    assert progress["arming_bar"]["beats_null"] is None
    assert progress["arming_bar"]["armable"] is False
    assert progress["legacy_evidence"]["null_check"]["evaluated"] is True
