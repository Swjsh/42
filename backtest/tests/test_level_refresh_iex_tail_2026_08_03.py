"""LANE-4 guard — the level feed's eye must not be 15 minutes behind the tape.

THE INCIDENT (2026-08-03): SPY dumped 09:25-09:29 into 749.33 — the final premarket low,
the bias-file support, respected to the cent — and 749.33 entered the engine's
levels_active only at 09:44:03. Root cause (log-proven three ways, see
refresh_levels_intraday.py module docstring): the script's SIP bars pull is served
~15 MINUTES DELAYED on this key's data plan. The 09:33:36 and 09:38:36 fires still wrote
INTRADAY_PML=749.65; each fire's `spot` matched a ~15-min-old bar close; the 09:48:36
fire saw exactly ONE RTH bar 18 minutes into the session.

THE FIX under guard: _merge_iex_tail — a REAL-TIME IEX tail (bars strictly newer than the
last SIP bar) appended to the delayed-SIP spine, volume-floored per bar at
TAIL_MIN_BAR_VOLUME (derived from the ratified degeneracy constants) so the 2026-07-27
80-share single-print wound (bogus PMH 744.90) stays closed.

RED-PROOFS:
  * test_thin_tail_bar_never_sets_a_level — neutering the volume floor (the exact
    pre-07-27 behavior) lets an 80-share print set PMH; with the floor it cannot.
  * test_iex_tail_recovers_the_749_33_case — remove the tail merge (SIP-only frame) and
    the premarket low stays 749.65; with the tail it is 749.33 by the 09:33-fire frame.

$0, pure-Python, no network. All state writes go to tmp_path (never live files).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"

_spec = importlib.util.spec_from_file_location("refresh_levels_intraday", MOD_PATH)
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)

TODAY = rli.et_now().strftime("%Y-%m-%d")


def _utc(hhmm_et: str) -> str:
    """ET premarket/RTH clock time -> the UTC ISO stamp Alpaca bars carry (EDT = UTC-4)."""
    h, m = int(hhmm_et[:2]), int(hhmm_et[3:])
    return f"{TODAY}T{h + 4:02d}:{m:02d}:00Z"


def _frame(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    """rows: (hhmm_et, open, high, low, close, volume) -> the raw fetched-frame shape."""
    df = pd.DataFrame([{"t": _utc(hm), "open": o, "high": h, "low": lo, "close": c,
                        "volume": v} for hm, o, h, lo, c, v in rows])
    return rli._decorate_frame(df)


def _sip_premarket(last_hm: str = "09:15") -> pd.DataFrame:
    """A healthy delayed-SIP premarket spine: 04:00..last_hm, min low 749.65, max high
    751.55, 20k shares/bar (clears the subset degeneracy guard many times over)."""
    rows = []
    hh, mm = 4, 0
    while (hh, mm) <= (int(last_hm[:2]), int(last_hm[3:])):
        hm = f"{hh:02d}:{mm:02d}"
        rows.append((hm, 750.50, 751.55 if hm == "08:30" else 751.20,
                     749.65 if hm == "09:00" else 750.10, 750.60, 20_000.0))
        mm += 5
        if mm == 60:
            mm, hh = 0, hh + 1
    return _frame(rows)


# ---------------------------------------------------------------------------------------
# The 2026-08-03 case: the real-time tail must deliver the final premarket low
# ---------------------------------------------------------------------------------------

class TestIexTailRecoversTheMiss:
    def test_iex_tail_recovers_the_749_33_case(self):
        """The 09:33-fire frame: SIP spine ends 09:15 (delay), IEX tail carries the
        09:20/09:25 dump bars. Tail-merged premarket min low == 749.33; the SIP-only
        (pre-fix) frame stays 749.65 — that difference IS the 15-minute violin gap."""
        sip = _sip_premarket()
        iex = _frame([("09:20", 750.40, 750.60, 749.80, 749.95, 6_000.0),
                      ("09:25", 749.95, 750.10, 749.33, 749.39, 9_000.0)])
        merged, meta = rli._merge_iex_tail(sip, iex)
        pre = merged[merged["hm"] < "09:30"]
        assert float(pre["low"].min()) == pytest.approx(749.33)
        assert meta["tail_used"] == 2 and meta["tail_dropped_thin"] == 0
        # RED-proof half: the pre-fix (SIP-only) frame does NOT know 749.33
        pre_old = sip[sip["hm"] < "09:30"]
        assert float(pre_old["low"].min()) == pytest.approx(749.65)

    def test_full_refresh_writes_tail_pml_with_provenance(self, tmp_path, monkeypatch):
        """End-to-end refresh() on the tail-merged frame (all state writes -> tmp_path):
        INTRADAY_PML lands at 749.33 with source_feed 'sip+iex_tail' — the upgrade is
        visible in the FILE (C7), not just in the frame."""
        monkeypatch.setattr(rli, "KEY_LEVELS", tmp_path / "key-levels.json")
        monkeypatch.setattr(rli, "TODAY_BIAS", tmp_path / "today-bias.json")
        monkeypatch.setattr(rli, "PARAMS", tmp_path / "params.json")  # absent -> memory wire OFF
        monkeypatch.setattr(rli, "MEMORY_MAP", tmp_path / "key-levels-memory.json")
        monkeypatch.setattr(rli, "daily_context", None)  # fail-open path: no shelf derivation
        sip = _sip_premarket()
        iex = _frame([("09:20", 750.40, 750.60, 749.80, 749.95, 6_000.0),
                      ("09:25", 749.95, 750.10, 749.33, 749.39, 9_000.0)])
        merged, _ = rli._merge_iex_tail(sip, iex)
        out = rli.refresh(df=merged)
        assert out["ok"], out
        kl = json.loads((tmp_path / "key-levels.json").read_text(encoding="utf-8"))
        pml = [lv for lv in kl["levels"] if str(lv.get("label", "")).startswith("INTRADAY_PML")]
        assert len(pml) == 1
        assert pml[0]["price"] == pytest.approx(749.33)
        assert pml[0]["source_feed"] == "sip+iex_tail"
        # spot comes from the newest (tail) bar — the frame's eye is current, not 15m old
        assert out["spot"] == pytest.approx(749.39)


# ---------------------------------------------------------------------------------------
# The 2026-07-27 wound stays closed: no single thin print may set a level via the tail
# ---------------------------------------------------------------------------------------

class TestThinTailGuard:
    def test_thin_tail_bar_never_sets_a_level(self):
        """An 80-share IEX print (the exact 07-27 poison class) above the SIP PMH must be
        DROPPED by the volume floor. RED-proof: with the floor neutered to 0 (pre-07-27
        behavior) the same print DOES set the new high — proving the floor is the
        load-bearing guard, not a decoration."""
        sip = _sip_premarket()
        poison = _frame([("09:20", 751.98, 751.99, 751.97, 751.99, 80.0)])
        merged, meta = rli._merge_iex_tail(sip, poison)
        assert float(merged["high"].max()) == pytest.approx(751.55)  # SIP PMH holds
        assert meta["tail_used"] == 0 and meta["tail_dropped_thin"] == 1
        # RED-proof: neuter the floor -> the poison print wins (must NEVER ship this way)
        try:
            rli.TAIL_MIN_BAR_VOLUME = 0.0
            merged_neutered, _ = rli._merge_iex_tail(sip, poison)
            assert float(merged_neutered["high"].max()) == pytest.approx(751.99)
        finally:
            rli.TAIL_MIN_BAR_VOLUME = rli.DEGENERACY_MIN_VOLUME / rli.DEGENERACY_MIN_BARS

    def test_floor_is_derived_not_hand_picked(self):
        assert rli.TAIL_MIN_BAR_VOLUME == pytest.approx(
            rli.DEGENERACY_MIN_VOLUME / rli.DEGENERACY_MIN_BARS)


# ---------------------------------------------------------------------------------------
# Conservatism: no-op / passthrough / fail-open behaviors
# ---------------------------------------------------------------------------------------

class TestMergeConservatism:
    def test_no_newer_iex_is_a_noop(self):
        """IEX bars at/behind the SIP tip change NOTHING (on a real-time-SIP plan the
        merge vanishes). Prices, extremes, and row count are identical to SIP-only."""
        sip = _sip_premarket()
        stale_iex = _frame([("09:00", 750.4, 750.6, 749.9, 750.0, 50_000.0),
                            ("09:15", 750.4, 750.6, 749.9, 750.0, 50_000.0)])
        merged, meta = rli._merge_iex_tail(sip, stale_iex)
        assert len(merged) == len(sip)
        assert float(merged["low"].min()) == pytest.approx(float(sip["low"].min()))
        assert meta["tail_used"] == 0
        assert not bool(merged["iex_tail"].any())

    def test_empty_iex_is_a_noop(self):
        sip = _sip_premarket()
        merged, meta = rli._merge_iex_tail(sip, pd.DataFrame())
        assert len(merged) == len(sip) and meta["tail_used"] == 0

    def test_empty_sip_passes_through(self):
        """A SIP outage must stay LOUD (refresh's existing 'no bars' failure), never be
        silently papered over with sparse IEX-only data."""
        merged, meta = rli._merge_iex_tail(pd.DataFrame(), _sip_premarket())
        assert len(merged) == 0 and meta["tail_used"] == 0

    def test_tail_is_additive_and_ordered(self):
        """No SIP row is replaced; merged frame stays ascending; tail rows are flagged."""
        sip = _sip_premarket()
        iex = _frame([("09:20", 750.4, 750.6, 749.8, 749.9, 6_000.0)])
        merged, _ = rli._merge_iex_tail(sip, iex)
        assert len(merged) == len(sip) + 1
        assert list(merged["ts"]) == sorted(merged["ts"])
        assert bool(merged.iloc[-1]["iex_tail"]) is True
        assert not bool(merged.iloc[:-1]["iex_tail"].any())

    def test_fetch_failure_fails_open_to_sip_only(self, monkeypatch):
        """The IEX leg raising must yield the SIP frame untouched + a loud meta error."""
        sip = _sip_premarket()

        def _fake_fetch(feed: str, days_back: int, limit: int) -> pd.DataFrame:
            if feed == "sip":
                return sip
            raise OSError("iex fetch down")

        monkeypatch.setattr(rli, "_fetch_bars_rest", _fake_fetch)
        df, meta = rli._spy_bars_with_meta()
        assert len(df) == len(sip)
        assert "tail_error" in meta and "iex fetch down" in meta["tail_error"]

    def test_injected_frames_without_tail_column_read_as_sip(self):
        """Back-compat: replay/test frames that predate the tail column keep provenance
        'sip' (the _subset_feed helper inside refresh handles the absent column)."""
        sip = _sip_premarket()
        assert "iex_tail" not in sip.columns  # the raw fetch shape has no flag
        merged, _ = rli._merge_iex_tail(sip, pd.DataFrame())
        assert "iex_tail" in merged.columns  # the merge always stamps it
