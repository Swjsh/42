"""Guards for setup/scripts/context_levels.py (WS-E, work order #9.5 row E,
markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md, corrected per #9.13 A).

All pure/offline -- no TradingView, no network, no MCP. Must pass with TradingView
Desktop CLOSED.

Four guards, matching the work order's deliverable list 1:1:
  1. THE FREEZE GUARD (headline): heartbeat_core._read_levels / _read_level_records
     output is byte-identical with a populated context-levels.json present vs absent --
     proven by construction (context_levels.py never writes to key-levels.json, and
     heartbeat_core never reads context-levels.json). A "bite" companion proves the
     guard is not vacuous: MERGING context-level rows straight into key-levels.json
     (the original, rejected row-E design) DOES change the gate's output -- which is
     exactly the defect #9.13 A found and this file's separate-file design avoids.
  2. Initial balance / opening-range / VWAP-band values are correct on a synthetic
     session, cross-checked against an independently hand-derived formula (not a call
     into the same cumsum/opening_range code under test).
  3. Every emitted context level carries BOTH zone_width and zone_width_provenance.
  4. Companion: existing guards this work must not regress (run separately, see the
     WS-E report for their quoted summary lines).
"""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO / "backtest"))


def _load(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cl = _load("context_levels", "setup/scripts/context_levels.py")
hc = _load("heartbeat_core", "setup/scripts/heartbeat_core.py")


# =====================================================================================
# Synthetic session fixture -- ALL bars carry equal volume (100 shares) so VWAP reduces
# to a plain arithmetic mean of typical price, letting the "hand-computed" expectation
# below be derived independently of compute_vwap()'s cumsum/cumv implementation.
# =====================================================================================

SESSION_DATE = "2026-01-02"
PRIOR_DATE = "2026-01-01"
ET = "America/New_York"

# (HH:MM, high, low, close) -- 12 bars, 09:30..10:25 (60 minutes, satisfies
# opening_range()'s len>=minutes//5 floor for minutes=60/15/5 all at once).
_SESSION_BARS = [
    ("09:30", 101, 99, 100),
    ("09:35", 102, 100, 101),
    ("09:40", 103, 98, 100),
    ("09:45", 104, 100, 102),
    ("09:50", 100, 97, 98),
    ("09:55", 99, 96, 97),
    ("10:00", 98, 95, 96),
    ("10:05", 97, 94, 95),
    ("10:10", 96, 93, 94),
    ("10:15", 95, 92, 93),
    ("10:20", 94, 91, 92),
    ("10:25", 93, 90, 91),
]

_PRIOR_BARS = [
    ("09:30", 200, 198, 199),
    ("09:35", 202, 200, 201),
]


def _frame(session_date: str, bars: list[tuple[str, float, float, float]], volume: float = 100.0) -> pd.DataFrame:
    rows = []
    for hm, h, l, c in bars:
        ts = pd.Timestamp(f"{session_date} {hm}:00", tz=ET)
        rows.append({"ts": ts, "date": session_date, "high": float(h), "low": float(l),
                     "close": float(c), "volume": volume})
    return pd.DataFrame(rows)


def _full_frame() -> pd.DataFrame:
    return pd.concat([_frame(PRIOR_DATE, _PRIOR_BARS), _frame(SESSION_DATE, _SESSION_BARS)],
                      ignore_index=True)


def _rth(session_date: str = SESSION_DATE) -> pd.DataFrame:
    return cl._rth_bars(_full_frame(), session_date)


# =====================================================================================
# GUARD 2 -- IB / opening-range / VWAP values correct on the synthetic session,
# independently hand-derived (not by calling the code under test a second time).
# =====================================================================================

def test_initial_balance_matches_hand_computed_high_low():
    rth = _rth()
    ib = cl.compute_initial_balance(rth, SESSION_DATE)
    assert ib is not None
    # Hand-computed from the 12-bar table above: max(highs)=104 @09:45, min(lows)=90 @10:25.
    assert ib["high"] == pytest.approx(104.0)
    assert ib["low"] == pytest.approx(90.0)
    assert ib["zone_width"] == pytest.approx((104.0 - 90.0) / 2)
    assert ib["zone_width_provenance"] == "ib_or_range_observed"


def test_opening_range_5m_matches_hand_computed_high_low():
    rth = _rth()
    orr = cl.compute_opening_range(rth, 5, SESSION_DATE)
    assert orr is not None
    # First 5 minutes = only the 09:30 bar: high=101, low=99.
    assert orr["high"] == pytest.approx(101.0)
    assert orr["low"] == pytest.approx(99.0)
    assert orr["zone_width"] == pytest.approx(1.0)


def test_opening_range_15m_matches_hand_computed_high_low():
    rth = _rth()
    orr = cl.compute_opening_range(rth, 15, SESSION_DATE)
    assert orr is not None
    # First 15 minutes = bars 09:30/09:35/09:40: high=max(101,102,103)=103, low=min(99,100,98)=98.
    assert orr["high"] == pytest.approx(103.0)
    assert orr["low"] == pytest.approx(98.0)
    assert orr["zone_width"] == pytest.approx(2.5)


def _independent_vwap_expectation(bars):
    """Deliberately NOT compute_vwap()'s cumsum/cumv formula -- a plain population-
    variance derivation, valid here because every synthetic bar carries equal volume
    (so volume-weighting reduces to an unweighted mean)."""
    typicals = [(h + l + c) / 3.0 for _, h, l, c in bars]
    vwap = statistics.mean(typicals)
    variance = statistics.mean([(t - vwap) ** 2 for t in typicals])  # population variance
    stdev = math.sqrt(variance)
    return vwap, stdev


def test_session_vwap_bands_match_independently_derived_expectation():
    rth = _rth()
    levels = cl.compute_vwap_bands(rth, SESSION_DATE)
    assert len(levels) == 5
    by_type = {lv["type"]: lv for lv in levels}

    exp_vwap, exp_stdev = _independent_vwap_expectation(_SESSION_BARS)
    assert exp_vwap == pytest.approx(96.833333, abs=1e-5)  # hand-computed: 1162/12

    assert by_type["session_vwap"]["price"] == pytest.approx(exp_vwap, abs=1e-2)
    assert by_type["vwap_upper_1sigma"]["price"] == pytest.approx(exp_vwap + exp_stdev, abs=1e-2)
    assert by_type["vwap_lower_1sigma"]["price"] == pytest.approx(exp_vwap - exp_stdev, abs=1e-2)
    assert by_type["vwap_upper_2sigma"]["price"] == pytest.approx(exp_vwap + 2 * exp_stdev, abs=1e-2)
    assert by_type["vwap_lower_2sigma"]["price"] == pytest.approx(exp_vwap - 2 * exp_stdev, abs=1e-2)

    # zone_width on every VWAP-family level == the observed sigma, not a hand-picked default.
    for lv in levels:
        assert lv["zone_width"] == pytest.approx(exp_stdev, abs=1e-2)
        assert lv["zone_width_provenance"] == "vwap_sigma_observed"


def test_prior_day_vwap_matches_independently_derived_expectation():
    spy_full = _full_frame()
    pdv = cl.compute_prior_day_vwap(spy_full, SESSION_DATE)
    assert pdv is not None
    exp_vwap, exp_stdev = _independent_vwap_expectation(_PRIOR_BARS)
    assert exp_vwap == pytest.approx(200.0)   # hand-computed: mean(199, 201)
    assert exp_stdev == pytest.approx(1.0)    # hand-computed: sqrt(mean((-1)^2,(1)^2)) = 1
    assert pdv["price"] == pytest.approx(exp_vwap, abs=1e-6)
    assert pdv["zone_width"] == pytest.approx(exp_stdev, abs=1e-6)
    assert pdv["zone_width_provenance"] == "vwap_sigma_observed"


# =====================================================================================
# GUARD 3 -- every emitted level carries BOTH zone_width and zone_width_provenance.
# =====================================================================================

def test_every_emitted_level_carries_zone_width_and_provenance(monkeypatch, tmp_path):
    # No banked CBOE archive in this offline run -> gamma_walls emits nothing (verified
    # separately below); every OTHER family must still be present with the required
    # fields on every record.
    monkeypatch.setattr(cl, "GEX_ARCHIVE_DIR", tmp_path / "no-such-dir")
    out = cl.build_context_levels(_full_frame(), SESSION_DATE)
    assert len(out["levels"]) >= 8  # IB + OR5 + OR15 + 5 VWAP bands + prior-day VWAP
    for lv in out["levels"]:
        assert "zone_width" in lv, lv
        assert "zone_width_provenance" in lv, lv
        assert isinstance(lv["zone_width"], float)
        assert lv["zone_width"] > 0
        assert isinstance(lv["zone_width_provenance"], str) and lv["zone_width_provenance"]
    assert "gamma_walls" not in out["families_emitted"]
    assert "gamma_walls" in out["families_skipped"]


def test_gamma_walls_emit_nothing_when_no_archive_present(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "GEX_ARCHIVE_DIR", tmp_path / "empty")
    assert cl.compute_gamma_walls(SESSION_DATE) == []


def test_gamma_walls_reuses_gex_regime_math_on_a_synthetic_cboe_archive(tmp_path, monkeypatch):
    """Pure/offline: a hand-built CBOE-shaped archive (same fields cboe_oi_bank.py
    already writes) proves compute_gamma_walls() adapts the wire shape and calls the
    EXISTING gex_regime.compute_gex_regime -- it does not reimplement the GEX math."""
    archive_dir = tmp_path / "gex-archive"
    archive_dir.mkdir()
    doc = {
        "by_symbol": {
            "SPY": {
                "spot": 100.0,
                "contracts": [
                    {"strike": 100.0, "right": "C", "gamma": 0.05, "open_interest": 1000.0},
                    {"strike": 100.0, "right": "P", "gamma": 0.05, "open_interest": 10.0},
                    {"strike": 105.0, "right": "C", "gamma": 0.02, "open_interest": 10.0},
                    {"strike": 95.0, "right": "P", "gamma": 0.05, "open_interest": 900.0},
                ],
            }
        }
    }
    (archive_dir / f"{SESSION_DATE}-cboe.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(cl, "GEX_ARCHIVE_DIR", archive_dir)

    walls = cl.compute_gamma_walls(SESSION_DATE)
    assert len(walls) == 2
    by_type = {w["type"]: w for w in walls}
    # Dominant call-gamma strike (highest OI*gamma among calls) = 100.0; dominant put = 95.0.
    assert by_type["call_wall"]["price"] == pytest.approx(100.0)
    assert by_type["put_wall"]["price"] == pytest.approx(95.0)
    for w in walls:
        assert w["zone_width_provenance"] == "default_pre_ab"  # a strike has no observed spread
        assert w["stale"] is False
        assert "gex_notional" in w


# =====================================================================================
# GUARD 1 -- THE FREEZE GUARD (headline). heartbeat_core._read_levels /
# _read_level_records output is byte-identical with a populated context-levels.json
# present vs absent. Companion bite proves it is not vacuous.
# =====================================================================================

_KEY_LEVELS_FIXTURE = {
    "schema_version": 3,
    "levels": [
        {"price": 745.40, "role": "resistance", "type": "resistance", "label": "PMH_2026-01-02",
         "tier": "Active", "source": "premarket_high", "expires_at": "2099-12-31T16:00:00-04:00"},
        {"price": 738.20, "role": "support", "type": "support", "label": "PML_2026-01-02",
         "tier": "Active", "source": "premarket_low", "expires_at": "2099-12-31T16:00:00-04:00"},
    ],
}

# A representative populated context-levels.json (schema this file's producer writes).
# Deliberately includes a price WITHIN the $12 gate band around the test spot (740.00)
# so the bite test below has something to actually smuggle into key-levels.json.
_CONTEXT_LEVELS_FIXTURE = {
    "schema_version": 1,
    "generated_at": "2026-01-02T09:31:00",
    "session_date": "2026-01-02",
    "levels": [
        {"family": "vwap", "type": "session_vwap", "session_date": "2026-01-02",
         "role": "pivot", "label": "SESSION VWAP", "source": "test fixture",
         "zone_width": 0.5, "zone_width_provenance": "vwap_sigma_observed", "price": 739.80},
        {"family": "initial_balance", "type": "initial_balance", "session_date": "2026-01-02",
         "role": "range", "label": "INITIAL BALANCE", "source": "test fixture",
         "zone_width": 1.2, "zone_width_provenance": "ib_or_range_observed",
         "high": 742.00, "low": 737.00},
    ],
    "families_known": list(cl.FAMILIES),
    "families_emitted": ["vwap_bands", "initial_balance"],
    "families_skipped": {},
}

SPOT = 740.00


def _read_both(state_dir, monkeypatch):
    monkeypatch.setattr(hc, "STATE", state_dir)
    return hc._read_levels(SPOT), hc._read_level_records(SPOT)


def test_read_levels_byte_identical_with_and_without_context_levels_file(tmp_path, monkeypatch):
    without_dir = tmp_path / "without"
    with_dir = tmp_path / "with"
    without_dir.mkdir()
    with_dir.mkdir()

    (without_dir / "key-levels.json").write_text(json.dumps(_KEY_LEVELS_FIXTURE), encoding="utf-8")
    (with_dir / "key-levels.json").write_text(json.dumps(_KEY_LEVELS_FIXTURE), encoding="utf-8")
    # The ONLY difference between the two directories: a populated context-levels.json.
    (with_dir / "context-levels.json").write_text(json.dumps(_CONTEXT_LEVELS_FIXTURE), encoding="utf-8")

    out_without = _read_both(without_dir, monkeypatch)
    out_with = _read_both(with_dir, monkeypatch)

    assert out_without == out_with, (
        f"heartbeat_core output changed merely because context-levels.json exists: "
        f"{out_without} != {out_with}"
    )
    assert out_without[0] != []  # non-vacuous: there IS output to compare


def test_bite_merging_context_rows_into_key_levels_json_DOES_change_gate_output(tmp_path, monkeypatch):
    """Non-vacuity proof for guard 1. This reproduces the ORIGINAL row-E design
    (#9.13 A): dropping a context-level dict straight into key-levels.json's `levels`
    array. It MUST change _read_levels' output -- if it did not, guard 1 above would be
    passing for the trivial reason that nothing in this test setup is capable of
    affecting heartbeat_core at all, not because the separate-file design is doing its
    job. The two assertions together are the actual proof: separate file = no effect
    (guard 1), merged file = real effect (this test)."""
    baseline_dir = tmp_path / "baseline"
    merged_dir = tmp_path / "merged"
    baseline_dir.mkdir()
    merged_dir.mkdir()

    (baseline_dir / "key-levels.json").write_text(json.dumps(_KEY_LEVELS_FIXTURE), encoding="utf-8")

    # Simulate the REJECTED design: context levels (with role: "context") appended
    # directly into key-levels.json's own `levels` array.
    smuggled = {
        "price": 739.80, "role": "context", "type": "context", "label": "SESSION VWAP",
        "tier": "Context", "source": "test fixture", "expires_at": "2099-12-31T16:00:00-04:00",
    }
    merged_levels = {**_KEY_LEVELS_FIXTURE, "levels": _KEY_LEVELS_FIXTURE["levels"] + [smuggled]}
    (merged_dir / "key-levels.json").write_text(json.dumps(merged_levels), encoding="utf-8")

    baseline_active, baseline_multi = _read_both(baseline_dir, monkeypatch)[0]
    merged_active, merged_multi = _read_both(merged_dir, monkeypatch)[0]

    assert 739.80 not in baseline_active
    assert 739.80 in merged_active, (
        "the role:'context' row did not reach the gate's active list -- if this ever "
        "fails, _read_level_records/_read_levels gained a role filter and the freeze "
        "guard above should be re-examined against the new source"
    )
    assert baseline_active != merged_active

# ----------------------------------------------------------------- staleness cap (Opus review)

def test_gamma_walls_dropped_when_archive_is_older_than_the_cap(tmp_path, monkeypatch):
    """_latest_cboe_archive() takes the newest archive AT OR BEFORE the session date with no
    lower bound -- so without a cap an arbitrarily old file is still DRAWN (flagged stale, but
    drawn). Gamma walls are a fast-decaying OI-positioning read; a two-week-old wall is a wrong
    line on J's chart, and work-order sec 9 exists precisely because J cannot tell decoration from
    decision.

    NOT hypothetical: journal/gex-archive/ has no file for 2026-09-05 or 2026-09-09 and
    known-gaps.json records neither -- the banker misses days silently.

    RED-PROOF: before MAX_ARCHIVE_STALENESS_DAYS, this emitted two walls instead of zero.
    """
    import context_levels as cl
    arch = tmp_path / "gex-archive"
    arch.mkdir()
    contracts = [
        {"strike": 760.0, "right": "P", "gamma": 0.05, "open_interest": 9000},
        {"strike": 775.0, "right": "C", "gamma": 0.05, "open_interest": 9000},
    ]
    (arch / "2026-08-01-cboe.json").write_text(
        json.dumps({"by_symbol": {"SPY": {"spot": 767.0, "contracts": contracts}}}), encoding="utf-8")
    monkeypatch.setattr(cl, "GEX_ARCHIVE_DIR", arch)

    # 39 days stale -> nothing, silently-wrong walls are worse than no walls
    assert cl.compute_gamma_walls("2026-09-09") == []

    # inside the cap -> still emitted, and honestly stamped
    (arch / "2026-09-08-cboe.json").write_text(
        json.dumps({"by_symbol": {"SPY": {"spot": 767.0, "contracts": contracts}}}), encoding="utf-8")
    walls = cl.compute_gamma_walls("2026-09-09")
    assert walls, "a 1-day-old archive is legitimate context (the banker fires after the close)"
    for w in walls:
        assert w["archive_date"] == "2026-09-08"
        assert w["stale"] is True
        assert w["staleness_days"] == 1, "staleness must be a NUMBER, not just a bool"
