"""test_ssr_shadow_v2_respec.py -- guard suite for the ssr-v2 respec (setup/scripts/
ssr_shadow.py, 2026-08-23): CONFIGS switched from full-size NQ/GC to micro MNQ/MGC (the
fundability fix -- see that module's docstring RESPEC section + the 2026-08-13 fundability
disclosure that flagged full-size sizing as ~326x this book's own equity at qty=3).

REDs on regression if a future edit:
  (a) reverts CONFIGS back to full-size symbols, or drifts a point value away from what the
      live Instrument registry actually says (backtest/futures/instruments.py for MNQ,
      backtest/futures/ssr/ssr_instruments.py for MGC),
  (b) reverts/loses the spec_version bump to "ssr-v2",
  (c) lets a ssr-v1 (pre-respec) round trip leak into the ssr-v2 arming bar's
      n_round_trips/total_pnl_usd -- the "fresh forward clock" is the single most important
      non-obvious property of this respec: it would be very easy to silently rescue a failed
      beats_null by mixing units across spec versions,
  (d) weakens the arming bar's three-condition AND (n>=20 AND positive_expectancy AND
      beats_null) as part of some unrelated future respec,
  (e) orphans a position that was still open under the retired v1 spec at the moment of the
      respec (LEGACY_CONFIG_ALIASES).

No network calls -- CONFIGS/instrument-registry assertions are pure lookups; compute_progress
is exercised with hand-built ledger rows (same isolation pattern as test_ssr_shadow.py).
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
from futures.instruments import MNQ as _MNQ_REGISTRY  # noqa: E402
from futures.instruments import NQ as _NQ_REGISTRY  # noqa: E402
from futures.ssr.detector import SSRSignal  # noqa: E402
from futures.ssr.ssr_instruments import GC as _GC_REGISTRY  # noqa: E402
from futures.ssr.ssr_instruments import MGC as _MGC_REGISTRY  # noqa: E402

ET = "America/New_York"


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Same isolation pattern as test_ssr_shadow.py -- never touches the real
    automation/state/futures/ssr-shadow-* files."""
    monkeypatch.setattr(ssr_shadow, "STATE_FILE", tmp_path / "ssr-shadow-state.json")
    monkeypatch.setattr(ssr_shadow, "LEDGER_FILE", tmp_path / "ssr-shadow-would-be.jsonl")
    monkeypatch.setattr(ssr_shadow, "PROGRESS_FILE", tmp_path / "ssr-shadow-progress.json")
    monkeypatch.setattr(ssr_shadow, "LOCK_FILE", tmp_path / "ssr-shadow.lock")
    monkeypatch.setattr(ssr_shadow, "LOG_DIR", tmp_path / "logs")
    return tmp_path


class _FakeInstrument:
    def __init__(self, point_value: float = 2.0, round_turn_usd: float = 1.24):
        self.point_value = point_value
        self.round_turn_usd = round_turn_usd


# ── (a) CONFIGS use micro symbols with VERIFIED point values ──────────────────────────────
def test_configs_use_micro_symbols_not_full_size():
    assert set(ssr_shadow.CONFIGS) == {"MNQ", "MGC"}, (
        "ssr-v2 CONFIGS must be keyed by the MICRO symbols (MNQ/MGC) -- get_ssr(cfg_name) "
        "must resolve to the account-sized contract, that is the whole point of this respec.")
    assert "NQ" not in ssr_shadow.CONFIGS and "GC" not in ssr_shadow.CONFIGS, (
        "full-size NQ/GC must never be live CONFIGS entries again -- a NEW position must "
        "never open under the retired ssr-v1 sizing.")


def test_configs_instrument_lookup_resolves_to_verified_micro_point_values():
    """Point values pinned against the SAME live registries the code imports from (never a
    hand-typed number) -- backtest/futures/instruments.py (MNQ) and backtest/futures/ssr/
    ssr_instruments.py (MGC), both read + verified in-repo before this respec shipped."""
    for cfg_name in ("MNQ", "MGC"):
        instrument = ssr_shadow.get_ssr(cfg_name)
        assert instrument.symbol == cfg_name

    mnq = ssr_shadow.get_ssr("MNQ")
    assert mnq.point_value == pytest.approx(2.0), (
        "MNQ (Micro E-mini Nasdaq-100) point_value must be $2.00/index point -- verified "
        "against backtest/futures/instruments.py (NQ=$20.00 -> MNQ=$2.00, exactly 1/10th).")
    assert mnq.point_value == pytest.approx(_MNQ_REGISTRY.point_value)

    mgc = ssr_shadow.get_ssr("MGC")
    assert mgc.point_value == pytest.approx(10.0), (
        "MGC (Micro Gold, 10oz) point_value must be $10.00/point -- verified against "
        "backtest/futures/ssr/ssr_instruments.py (GC=$100.00 -> MGC=$10.00, exactly 1/10th).")
    assert mgc.point_value == pytest.approx(_MGC_REGISTRY.point_value)

    # both micros are exactly 1/10th their full-size sibling.
    assert _NQ_REGISTRY.point_value / mnq.point_value == pytest.approx(10.0)
    assert _GC_REGISTRY.point_value / mgc.point_value == pytest.approx(10.0)

    # the full-size symbols must STILL resolve (LEGACY_CONFIG_ALIASES needs this to settle a
    # position still open under v1 at the moment of the respec) -- just never a live
    # CONFIGS key (pinned above).
    assert ssr_shadow.get_ssr("NQ").point_value == pytest.approx(20.0)
    assert ssr_shadow.get_ssr("GC").point_value == pytest.approx(100.0)


# ── (b) spec_version bumped, and every NEW row self-identifies it ─────────────────────────
def test_spec_version_is_ssr_v2():
    assert ssr_shadow.SPEC_VERSION == "ssr-v2"


def test_new_ledger_rows_are_stamped_with_the_current_spec_version():
    """entry/closed rows must self-identify their spec_version -- this is the mechanism
    compute_round_trips/compute_progress use to tell a fresh ssr-v2 round trip apart from a
    pre-respec ssr-v1 one that never carried this field at all."""
    ts = pd.Timestamp("2026-08-24 10:00:00", tz=ET)
    sig = SSRSignal(ts_et=ts, bar_index=10, direction="short", level_name="PDH",
                    level_price=100.0, sweep_extreme=101.0, stop_price=101.0,
                    entry_ref_close=100.0,
                    state_trace={"swept_at_index": 0, "shifted_at_index": 0, "shift_mode": "bos"})
    inst = ssr_shadow.get_ssr("MNQ")
    pos = ssr_shadow.open_position("MNQ", sig, None, inst)
    entry_row = ssr_shadow._entry_event(pos)
    assert entry_row.get("spec_version") == ssr_shadow.SPEC_VERSION == "ssr-v2"

    bar = {"ts_et": ts + pd.Timedelta(minutes=15), "high": pos["entry"] + 1,
          "low": pos["stop"] + 1.0, "close": pos["entry"]}
    events, _new_pos = ssr_shadow.decide_bar_events(pos, bar, inst)
    # quiet bar hits nothing -> no events; force a stop hit instead to get a real `closed` row
    bar_stop = {"ts_et": ts + pd.Timedelta(minutes=15), "high": pos["stop"] + 1.0,
               "low": pos["tp1"] - 1.0, "close": pos["stop"]}
    events, _new_pos = ssr_shadow.decide_bar_events(pos, bar_stop, inst)
    assert events, "expected a closed event from the forced stop-hit bar"
    assert events[0]["spec_version"] == "ssr-v2"


def test_legacy_position_walked_forward_reports_ssr_v1_not_current_spec_version():
    """A position whose OWN `config` is a retired LEGACY_CONFIG_ALIASES value ("NQ") must
    keep reporting spec_version ssr-v1 on every row it generates while being walked forward
    under CURRENT (ssr-v2) code -- it must never "graduate" to the running code's spec_version
    just because this build is newer."""
    ts = pd.Timestamp("2026-08-21 11:45:00", tz=ET)
    sig = SSRSignal(ts_et=ts, bar_index=10, direction="short", level_name="NY_HIGH",
                    level_price=20000.0, sweep_extreme=20050.0, stop_price=20050.0,
                    entry_ref_close=20000.0,
                    state_trace={"swept_at_index": 0, "shifted_at_index": 0, "shift_mode": "bos"})
    full_nq = ssr_shadow.get_ssr("NQ")
    legacy_pos = ssr_shadow.open_position("NQ", sig, None, full_nq)
    assert legacy_pos["config"] == "NQ"

    entry_row = ssr_shadow._entry_event(legacy_pos)
    assert entry_row["spec_version"] == "ssr-v1"

    bar_stop = {"ts_et": ts + pd.Timedelta(minutes=15), "high": legacy_pos["stop"] + 1.0,
               "low": legacy_pos["tp1"] - 1.0, "close": legacy_pos["stop"]}
    events, new_pos = ssr_shadow.decide_bar_events(legacy_pos, bar_stop, full_nq)
    assert events and events[0]["event"] == "closed"
    assert events[0]["spec_version"] == "ssr-v1", (
        "a legacy (config=NQ) position's closing row must be attributed to ssr-v1 even "
        "though the CODE currently running is ssr-v2.")
    assert new_pos["status"] == "closed"


# ── (c) v1 ledger is quarantined from v2's arming n (the "fresh forward clock") ──────────
def _legacy_v1_row_pair(signal_ref="NQ|short|PDH|2026-08-03T09:45", pnl_usd=27335.69):
    """Rows shaped EXACTLY like the real pre-respec ledger: no `spec_version` key at all
    (that field did not exist before this respec) and `config` still the retired full-size
    literal ("NQ") -- this is what every row in the LIVE ledger looked like before this
    commit. Never hand-add spec_version="ssr-v1" here -- the whole point is that ABSENCE of
    the field is itself how a real legacy row is recognized."""
    return [
        {"ts_et": "2026-08-03T10:00:00-04:00", "config": "NQ", "signal_ref": signal_ref,
        "direction": "short", "event": "entry", "entry": 15000.0, "fill_price": 15000.0,
        "bar_close": 15000.0, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0},
        {"ts_et": "2026-08-03T11:00:00-04:00", "config": "NQ", "signal_ref": signal_ref,
        "direction": "short", "event": "closed", "reason": "runner", "entry": 15000.0,
        "fill_price": 14900.0, "bar_close": 14900.0, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": pnl_usd},
    ]


def _v2_row_pair(signal_ref, pnl_usd):
    """Rows shaped like a POST-respec fill: config="MNQ" (a live CONFIGS key) and
    spec_version stamped, exactly what _entry_event/_row now write."""
    return [
        {"ts_et": "2026-08-24T10:00:00-04:00", "config": "MNQ", "signal_ref": signal_ref,
        "direction": "short", "event": "entry", "entry": 20000.0, "fill_price": 20000.0,
        "bar_close": 20000.0, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0,
        "spec_version": "ssr-v2"},
        {"ts_et": "2026-08-24T11:00:00-04:00", "config": "MNQ", "signal_ref": signal_ref,
        "direction": "short", "event": "closed", "reason": "runner", "entry": 20000.0,
        "fill_price": 19900.0, "bar_close": 19900.0, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": pnl_usd, "spec_version": "ssr-v2"},
    ]


def test_legacy_v1_round_trips_excluded_from_v2_round_trip_count():
    rows = _legacy_v1_row_pair()
    trips = ssr_shadow.compute_round_trips(rows)
    assert len(trips) == 1
    assert trips[0]["spec_version"] == "ssr-v1", (
        "a row with no spec_version field (the real shape of every pre-respec ledger row) "
        "must be attributed to ssr-v1, never silently treated as current-spec evidence.")

    progress = ssr_shadow.compute_progress(rows, now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 0, (
        "the ssr-v1 round trip must NOT count toward the ssr-v2 arming bar's n_round_trips "
        "-- this is the 'fresh forward clock' the respec requires.")
    assert progress["total_pnl_usd"] == 0.0
    assert progress["positive_expectancy"] is False
    assert progress["arming_bar"]["armable"] is False
    assert progress["legacy_evidence"]["n_round_trips"] == 1
    assert progress["legacy_evidence"]["total_pnl_usd"] == pytest.approx(27335.69)
    assert "ssr-v1" in progress["legacy_evidence"]["spec_versions"]


def test_v1_and_v2_evidence_never_mixed_in_the_arming_aggregate():
    """A ledger with BOTH a legacy v1 trip and a fresh v2 trip: the arming bar must reflect
    ONLY the v2 trip, and the legacy trip's dollar figure must never leak into
    total_pnl_usd/n_round_trips above -- the exact failure mode the respec task forbids
    ('do not let a reader mistake v1's +$27k for v2 evidence')."""
    rows = _legacy_v1_row_pair(pnl_usd=27335.69) + _v2_row_pair(
        "MNQ|short|PDH|2026-08-24T09:45", pnl_usd=150.0)
    progress = ssr_shadow.compute_progress(rows, now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 1
    assert progress["total_pnl_usd"] == pytest.approx(150.0), (
        "v1's +$27,335.69 must not be summed into the v2 total_pnl_usd.")
    assert progress["legacy_evidence"]["n_round_trips"] == 1
    assert progress["legacy_evidence"]["total_pnl_usd"] == pytest.approx(27335.69)


def test_live_progress_shape_matches_the_real_current_ledger_state():
    """Sanity pin against the ACTUAL live ledger's shape at the moment of this respec: 17
    pre-respec round trips, net +$27,335.69, all lacking spec_version. Constructed by hand
    here (never read from the real file -- this test must stay isolated), but with the SAME
    cardinality/sign as the real ssr-shadow-progress.json this task's context block quoted,
    so a reviewer can cross-check this test against that snapshot."""
    rows: list[dict] = []
    total = 0.0
    per_trip = 27335.69 / 17
    for i in range(17):
        pnl = round(per_trip, 2)
        total += pnl
        rows += _legacy_v1_row_pair(signal_ref=f"NQ|short|PDH|2026-08-{i + 1:02d}T09:45",
                                    pnl_usd=pnl)
    progress = ssr_shadow.compute_progress(rows, now_et=pd.Timestamp("2026-08-24T12:00:00", tz=ET))
    assert progress["n_round_trips"] == 0
    assert progress["arming_bar"]["armable"] is False
    assert progress["legacy_evidence"]["n_round_trips"] == 17
    assert progress["legacy_evidence"]["total_pnl_usd"] == pytest.approx(total, abs=0.5)


# ── (d) arming bar's three-condition AND is untouched by the respec ─────────────────────
def _v2_trip_rows(i, *, bar_close, pnl_usd, entry=20000.0, day="24"):
    ref = f"MNQ|short|PDH|2026-08-{day}T{i:02d}:00"
    ts_prefix = f"2026-08-{day}T{i:02d}"
    return [
        {"ts_et": f"{ts_prefix}:00:00-04:00", "config": "MNQ", "signal_ref": ref,
        "direction": "short", "event": "entry", "entry": entry, "fill_price": entry,
        "bar_close": entry, "exit_qty": 0, "qty_open_after": 3, "pnl_usd": 0.0,
        "spec_version": "ssr-v2"},
        {"ts_et": f"{ts_prefix}:30:00-04:00", "config": "MNQ", "signal_ref": ref,
        "direction": "short", "event": "closed", "reason": "runner", "entry": entry,
        "fill_price": bar_close, "bar_close": bar_close, "exit_qty": 3, "qty_open_after": 0,
        "pnl_usd": pnl_usd, "spec_version": "ssr-v2"},
    ]


def _fake_lookup(_cfg):
    return _FakeInstrument(point_value=2.0, round_turn_usd=1.24)


def test_arming_bar_still_requires_all_three_conditions():
    """Pins the exact gate: n>=20 AND positive_expectancy AND beats_null. Four v2-tagged
    ledgers, three each satisfying exactly two of the three (armable must stay False), one
    satisfying all three (armable must be True) -- guards against a future respec 'helpfully'
    loosening this AND into an OR, or dropping a condition, while touching the same code
    path this respec touched."""
    now = pd.Timestamp("2026-08-24T12:00:00", tz=ET)

    # (1) n>=20, but NOT positive_expectancy (net negative) -> not armable regardless of null.
    rows_neg_ev = []
    for i in range(20):
        rows_neg_ev += _v2_trip_rows(i, bar_close=20050.0, pnl_usd=-10.0)
    p1 = ssr_shadow.compute_progress(rows_neg_ev, instrument_lookup=_fake_lookup, now_et=now)
    assert p1["n_round_trips"] == 20
    assert p1["positive_expectancy"] is False
    assert p1["arming_bar"]["armable"] is False

    # (2) n>=20 AND positive_expectancy, but the null (unmanaged hold to the SAME bar_close)
    # beats the small realized gain -> beats_null False -> still not armable.
    rows_fails_null = []
    for i in range(20):
        rows_fails_null += _v2_trip_rows(i, bar_close=19500.0, pnl_usd=30.0, day="25")
    p2 = ssr_shadow.compute_progress(rows_fails_null, instrument_lookup=_fake_lookup, now_et=now)
    assert p2["n_round_trips"] == 20
    assert p2["positive_expectancy"] is True
    assert p2["arming_bar"]["beats_null"] is False
    assert p2["arming_bar"]["armable"] is False

    # (3) positive_expectancy AND beats_null (adverse bar_close -> null is negative, realized
    # exit protected the gain), but n<20 -> still not armable.
    rows_too_few = []
    for i in range(19):
        rows_too_few += _v2_trip_rows(i, bar_close=20100.0, pnl_usd=500.0, day="26")
    p3 = ssr_shadow.compute_progress(rows_too_few, instrument_lookup=_fake_lookup, now_et=now)
    assert p3["n_round_trips"] == 19
    assert p3["positive_expectancy"] is True
    assert p3["arming_bar"]["armable"] is False, "n<20 must block arming regardless of quality"

    # (4) sanity: all three satisfied together -> armable True. Same construction as (3) plus
    # one more trip to cross n=20.
    rows_all_good = []
    for i in range(20):
        rows_all_good += _v2_trip_rows(i, bar_close=20100.0, pnl_usd=500.0, day="27")
    p4 = ssr_shadow.compute_progress(rows_all_good, instrument_lookup=_fake_lookup, now_et=now)
    assert p4["n_round_trips"] == 20
    assert p4["positive_expectancy"] is True
    assert p4["arming_bar"]["beats_null"] is True
    assert p4["arming_bar"]["armable"] is True, (
        "sanity check: all three conditions true together must still produce armable=True "
        "-- this respec must not have accidentally made arming permanently unreachable.")


# ── (e) a v1 position still open at the moment of the respec is never orphaned ───────────
def test_legacy_open_position_still_walked_forward_after_configs_key_rename(monkeypatch):
    """The exact scenario this respec created in the LIVE state file: one position open
    under config="NQ" (a key that no longer exists in CONFIGS after the rename). Without
    LEGACY_CONFIG_ALIASES, `_run_once_unlocked`'s per-config walk loop (which now iterates
    CONFIGS' MNQ/MGC keys) would never touch it again -- silently orphaned forever. This
    pins that it keeps being walked and can still close via the normal exit machinery."""
    monkeypatch.setattr(ssr_shadow, "CONFIGS", {"MNQ": ssr_shadow.CONFIGS["MNQ"]})

    entry_ts = pd.Timestamp("2026-08-21 11:45:00", tz=ET)
    sig = SSRSignal(ts_et=entry_ts, bar_index=5, direction="short", level_name="NY_HIGH",
                    level_price=20000.0, sweep_extreme=20050.0, stop_price=20050.0,
                    entry_ref_close=20000.0,
                    state_trace={"swept_at_index": 0, "shifted_at_index": 0, "shift_mode": "bos"})
    full_nq = ssr_shadow.get_ssr("NQ")
    legacy_pos = ssr_shadow.open_position("NQ", sig, None, full_nq)
    assert legacy_pos["config"] == "NQ"

    # Seed state: a real MNQ watermark (so MNQ is not cold-starting) + the one open legacy
    # position, exactly mirroring the live ssr-shadow-state.json this respec inherited.
    idx = pd.date_range(entry_ts + pd.Timedelta(minutes=15), periods=40, freq="15min")
    bars = pd.DataFrame({
        "timestamp_et": idx,
        "open": [20000.0] * 40, "high": [20001.0] * 40, "low": [19999.0] * 40,
        "close": [20000.0] * 40, "volume": [100] * 40,
    })
    # force a clean stop-hit a few bars in so the position actually closes.
    bars.loc[3, "high"] = legacy_pos["stop"] + 1.0
    bars.loc[3, "close"] = legacy_pos["stop"]

    ssr_shadow._atomic_write_json(ssr_shadow.STATE_FILE, {
        "configs": {"MNQ": {"watermark_bar_ts_et": idx[0].isoformat()}},
        "positions": {legacy_pos["signal_ref"]: legacy_pos},
    })

    def fetcher(symbol, interval, period):
        return bars.copy()

    def signal_fn(bars_, snapshots, atr, params):
        return []  # no new signals this poll -- only the legacy walk matters here

    now = idx[-1]
    summary = ssr_shadow.run_once(now_et=now, bar_fetcher=fetcher, signal_fn=signal_fn)
    assert summary["events"] >= 1, "the legacy NQ position must have been walked and closed"

    state = ssr_shadow.load_state()
    settled = state["positions"][legacy_pos["signal_ref"]]
    assert settled["status"] == "closed", "legacy position must not be orphaned by the respec"

    rows = ssr_shadow.load_ledger_rows()
    closing_rows = [r for r in rows if r.get("signal_ref") == legacy_pos["signal_ref"]
                   and r.get("event") == "closed"]
    assert closing_rows, "expected a closed row for the legacy position"
    assert closing_rows[0]["spec_version"] == "ssr-v1", (
        "the legacy position's own closing row must be attributed to ssr-v1, even though "
        "CONFIGS/SPEC_VERSION are now ssr-v2.")
