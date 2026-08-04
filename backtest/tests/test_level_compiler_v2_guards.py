"""GUARDS for the Premarket Level-Compiler v2 (WS1, 2026-07-27, J live-flagged incident).

THE INCIDENT: today's engine premarket-high was 744.90 -- a SINGLE 80-share IEX print
(o=h=l=c=744.9, n=1, v=80). J's real level, 745.40, is confirmed all over the SIP tape and
is the 07-08 daily close, part of a 3-week 744.2-745.8 shelf broken down on 07-23. Today
(07-27) gapped up +0.81% from Friday's 738.93 close straight INTO that shelf (open 744.91,
high 745.53) -- a backside retest -- then faded the entire gap. The engine had no shelf/
gap/degeneracy awareness. This file pins the 5 required guards, each with a BITE
(non-vacuous proof: neutralize the fix inline and show the SAME assertion would fail
without it -- the standing RED-proof pattern this suite already uses, see
test_refresh_levels_intraday.py::test_bite_pre_normalize_contradiction_is_real).

Pure-Python, $0, no network -- daily-series fixtures below are the REAL 2026-07-27 SIP
daily bars (fetched live once during this build for calibration, hardcoded here so the
guard never depends on network availability or a moving "today").
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rli = _load("refresh_levels_intraday", "setup/scripts/refresh_levels_intraday.py")
dctx = _load("daily_context", "setup/scripts/daily_context.py")
hc = _load("heartbeat_core", "setup/scripts/heartbeat_core.py")


# =====================================================================================
# Fixture: REAL 2026-06-22 .. 2026-07-27 SPY daily SIP bars (fetched live 2026-07-27
# for calibration -- see WS1 build notes). Hardcoded so shelf/gap guards never depend on
# network or a moving "today".
# =====================================================================================
_REAL_DAILY_BARS = [
    {"date": "2026-06-22", "o": 747.70, "h": 750.18, "l": 743.13, "c": 744.39, "v": 46731169},
    {"date": "2026-06-23", "o": 733.81, "h": 739.63, "l": 732.30, "c": 733.58, "v": 66917430},
    {"date": "2026-06-24", "o": 735.17, "h": 739.945, "l": 730.84, "c": 733.24, "v": 57507627},
    {"date": "2026-06-25", "o": 738.91, "h": 739.37, "l": 729.60, "c": 734.30, "v": 54195404},
    {"date": "2026-06-26", "o": 728.945, "h": 736.53, "l": 716.58, "c": 728.99, "v": 71104306},
    {"date": "2026-06-29", "o": 736.525, "h": 741.56, "l": 732.09, "c": 741.00, "v": 58501605},
    {"date": "2026-06-30", "o": 741.29, "h": 748.02, "l": 740.89, "c": 746.77, "v": 55693737},
    {"date": "2026-07-01", "o": 745.00, "h": 749.435, "l": 742.375, "c": 745.76, "v": 47175555},
    {"date": "2026-07-02", "o": 747.40, "h": 751.31, "l": 740.03, "c": 744.78, "v": 57575794},
    {"date": "2026-07-06", "o": 748.74, "h": 752.41, "l": 747.41, "c": 751.28, "v": 50768534},
    {"date": "2026-07-07", "o": 750.22, "h": 750.96, "l": 745.21, "c": 747.71, "v": 43789259},
    {"date": "2026-07-08", "o": 743.16, "h": 746.15, "l": 739.51, "c": 745.40, "v": 43833354},
    {"date": "2026-07-09", "o": 747.35, "h": 751.97, "l": 745.59, "c": 751.71, "v": 41503216},
    {"date": "2026-07-10", "o": 752.05, "h": 755.42, "l": 748.10, "c": 754.95, "v": 42260129},
    {"date": "2026-07-13", "o": 752.47, "h": 753.9105, "l": 748.00, "c": 749.17, "v": 44096964},
    {"date": "2026-07-14", "o": 750.91, "h": 753.34, "l": 748.66, "c": 751.83, "v": 35205607},
    {"date": "2026-07-15", "o": 754.24, "h": 755.58, "l": 750.20, "c": 754.81, "v": 43913069},
    {"date": "2026-07-16", "o": 752.76, "h": 754.57, "l": 747.88, "c": 750.72, "v": 46475759},
    {"date": "2026-07-17", "o": 742.08, "h": 747.29, "l": 740.80, "c": 743.29, "v": 62723008},
    {"date": "2026-07-20", "o": 747.06, "h": 748.73, "l": 741.5103, "c": 742.09, "v": 50500548},
    {"date": "2026-07-21", "o": 746.29, "h": 749.04, "l": 744.18, "c": 748.28, "v": 34385946},
    {"date": "2026-07-22", "o": 746.62, "h": 750.02, "l": 746.37, "c": 747.41, "v": 32896257},
    {"date": "2026-07-23", "o": 739.37, "h": 742.56, "l": 735.21, "c": 738.18, "v": 55502098},
    {"date": "2026-07-24", "o": 738.51, "h": 743.72, "l": 737.29, "c": 738.93, "v": 44843800},
    {"date": "2026-07-27", "o": 744.91, "h": 745.53, "l": 735.87, "c": 739.09, "v": 41536534},
]
_TODAY_ET = datetime(2026, 7, 27, 21, 15, 0)


# =====================================================================================
# GUARD 1 -- SIP feed (refresh_levels_intraday's OWN fetch; heartbeat_core untouched)
# =====================================================================================

def test_refresh_levels_intraday_uses_sip_feed():
    """Updated 2026-08-03 (LANE-4 IEX-tail fix): the frame's SPINE stays SIP (the 07-27
    consolidated-tape fix), but a REAL-TIME IEX *tail* is now allowed — bars strictly newer
    than the delayed SIP tip, per-bar volume-floored (TAIL_MIN_BAR_VOLUME) so the 07-27
    single-print class still cannot set a level. The old blanket 'no feed=iex anywhere'
    assertion is superseded by shape-pinning both fetches: SIP = 7-day spine, IEX = 1-day
    tail-only supplement. Behavior guard: test_level_refresh_iex_tail_2026_08_03.py."""
    src = Path(REPO / "setup" / "scripts" / "refresh_levels_intraday.py").read_text(encoding="utf-8")
    assert '_fetch_bars_rest(feed="sip", days_back=7, limit=1500)' in src, \
        "the frame's spine must remain the 7-day SIP consolidated tape"
    assert '_fetch_bars_rest(feed="iex", days_back=1, limit=IEX_TAIL_LIMIT)' in src, \
        "the real-time IEX supplement must stay a 1-day TAIL fetch, never the spine"
    assert "TAIL_MIN_BAR_VOLUME" in src and "_merge_iex_tail" in src, \
        "the IEX tail must flow through the volume-floored merge (07-27 wound stays closed)"


def test_heartbeat_core_live_tick_fetch_untouched_iex():
    """Explicit scope guard: heartbeat_core.py's OWN bar fetch (the hot-path live tick)
    stays IEX -- this WS1 change only touches the level FILE producer, never the engine's
    own read. If this ever flips it means someone touched the wrong file."""
    src = Path(REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert "feed=iex" in src


# =====================================================================================
# GUARD 2 -- degeneracy refusal: the EXACT 07-27 incident (80-share single IEX print)
# =====================================================================================

def _rth_bars_ok():
    """Realistic, non-degenerate RTH bars (clears both bar-count and volume floors)."""
    return [
        ("09:35", 745.0, 744.0, 744.5, 500_000),
        ("09:45", 745.5, 744.2, 745.0, 400_000),
        ("09:55", 745.2, 744.0, 744.3, 350_000),
        ("10:05", 744.8, 743.8, 744.0, 300_000),
    ]


def _make_df(rth_bars, pre_bars=()):
    today = rli.et_now().strftime("%Y-%m-%d")
    rows = []
    for hm, hi, lo, cl, vol in list(pre_bars) + list(rth_bars):
        rows.append({"date": today, "hm": hm, "high": hi, "low": lo, "close": cl, "volume": vol})
    return pd.DataFrame(rows)


@pytest.fixture
def _state(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"key_levels": {}}), encoding="utf-8")
    monkeypatch.setattr(rli, "KEY_LEVELS", kl)
    monkeypatch.setattr(rli, "TODAY_BIAS", bias)
    monkeypatch.setattr(rli, "daily_context", None)  # isolate this guard from the shelf wire
    # isolate from the REAL project's params.json / key-levels-memory.json -- without this,
    # _memory_merge_enabled() reads the live repo state and can inject real level_memory
    # entries near the test's prices, contaminating the degeneracy assertions below.
    monkeypatch.setattr(rli, "PARAMS", tmp_path / "no-params.json")
    monkeypatch.setattr(rli, "MEMORY_MAP", tmp_path / "no-memory-map.json")
    return kl, bias


def test_degenerate_80_share_single_print_pmh_refused(_state):
    """THE incident, reproduced exactly: ONE premarket bar, o=h=l=c=744.9, v=80 (n=1<3
    bars AND 80<10,000 shares -- fails BOTH degeneracy checks). Must NOT be written as a
    level, and the refusal must be LOUD in the file's provenance_notes (C7/L241)."""
    kl, _ = _state
    pre_degenerate = [("08:30", 744.9, 744.9, 744.9, 80)]
    out = rli.refresh(df=_make_df(_rth_bars_ok(), pre_degenerate))
    assert out["ok"] is True
    data = json.loads(kl.read_text())
    labels = {lv["label"] for lv in data["levels"]}
    assert not any(lbl.startswith("INTRADAY_PMH") for lbl in labels)
    assert not any(lbl.startswith("INTRADAY_PML") for lbl in labels)
    assert any(abs(lv["price"] - 744.9) < 0.01 for lv in data["levels"]) is False
    notes = data["provenance_notes"]
    assert len(notes) >= 1
    pmh_notes = [n for n in notes if n["label"].startswith("INTRADAY_PMH")]
    assert pmh_notes, f"expected a PMH refusal note, got {notes}"
    assert "bar" in pmh_notes[0]["reason"].lower()  # refused on the n<3-bars check first


def test_degeneracy_bite_neutralized_guard_lets_garbage_through(_state, monkeypatch):
    """BITE (non-vacuous): fully neutralize the guard function (all 3 of its checks --
    bar count, volume, AND zero-range) and show the SAME degenerate 80-share print WOULD
    have been written as a level -- proving the refusal above is the guard doing real
    work, not an accident of the fixture."""
    kl, _ = _state
    monkeypatch.setattr(rli, "_degeneracy_reason", lambda sub: None)
    pre_degenerate = [("08:30", 744.9, 744.9, 744.9, 80)]
    rli.refresh(df=_make_df(_rth_bars_ok(), pre_degenerate))
    data = json.loads(kl.read_text())
    labels = {lv["label"].split("_2026")[0] for lv in data["levels"]}
    assert "INTRADAY_PMH" in labels, "with the guard neutralized, the degenerate print IS written (bite proven)"


def test_degeneracy_zero_range_refused(_state):
    """PMH==PML (high==low across the whole subset) is refused even with enough bars/volume
    -- a dead/flat tape is still not a trustworthy level."""
    kl, _ = _state
    pre_flat = [("08:00", 744.90, 744.90, 744.90, 20_000),
                ("08:15", 744.90, 744.90, 744.90, 15_000),
                ("08:30", 744.90, 744.90, 744.90, 18_000)]
    rli.refresh(df=_make_df(_rth_bars_ok(), pre_flat))
    data = json.loads(kl.read_text())
    labels = {lv["label"].split("_2026")[0] for lv in data["levels"]}
    assert "INTRADAY_PMH" not in labels and "INTRADAY_PML" not in labels
    notes = data["provenance_notes"]
    assert any("range" in n["reason"].lower() or "==" in n["reason"] for n in notes)


def test_degeneracy_healthy_subset_not_refused(_state):
    """Non-vacuous the OTHER direction: a normal, well-volumed premarket subset (the
    real 07-27 SIP shape -- dozens of bars, tens of thousands of shares) is NOT refused."""
    kl, _ = _state
    pre_healthy = [("08:00", 745.0, 744.5, 744.8, 20_000),
                   ("08:15", 745.3, 744.8, 745.0, 18_000),
                   ("08:30", 745.6, 745.0, 745.4, 22_000)]
    rli.refresh(df=_make_df(_rth_bars_ok(), pre_healthy))
    data = json.loads(kl.read_text())
    labels = {lv["label"].split("_2026")[0] for lv in data["levels"]}
    assert "INTRADAY_PMH" in labels and "INTRADAY_PML" in labels
    assert data["provenance_notes"] == []


# =====================================================================================
# GUARD 3 -- directional balance: a session-high scenario must yield BOTH sides
# =====================================================================================

def _old_nearest_n_overall(picks, cap):
    """Foil: the PRE-fix algorithm ('N nearest to spot, regardless of side')."""
    ranked = sorted(picks, key=lambda t: (t[0], -t[2]))
    return ranked[:cap]


def test_directional_balance_session_high_yields_both_sides(tmp_path, monkeypatch):
    """THE session-high scenario (today's real shape): spot sits at a fresh high, so
    every NEARBY memory candidate is resistance (overhead is close, the floor is far
    below where price came from). Old nearest-6-overall would have picked ALL resistance
    and ZERO support -- exactly today's incident. New 3-per-side balance must surface at
    least one support even though it is farther away than several resistance candidates."""
    spot = 745.50  # a fresh session high
    cand = (
        [{"price": p, "role": "resistance", "type": "resistance", "label": f"R{p}",
          "memory_score": 90.0, "tier": "Active"}
         for p in (745.60, 745.70, 745.90, 746.10, 746.40, 746.60)]  # 6 -- fills the OLD cap alone
        + [{"price": p, "role": "support", "type": "support", "label": f"S{p}",
            "memory_score": 90.0, "tier": "Active"} for p in (742.00, 740.50)]
    )
    mem = tmp_path / "key-levels-memory.json"
    mem.write_text(json.dumps({"levels": cand}), encoding="utf-8")
    monkeypatch.setattr(rli, "MEMORY_MAP", mem)
    out = rli._merge_memory_levels([], spot=spot, now_iso="2026-07-27T09:35:00-04:00")
    mem_out = [lv for lv in out if lv["source"] == "level_memory"]
    roles = {lv["role"] for lv in mem_out}
    assert "resistance" in roles and "support" in roles, \
        f"expected BOTH sides represented, got roles={roles} from {[lv['price'] for lv in mem_out]}"
    assert any(lv["price"] == 742.00 for lv in mem_out)  # nearest support makes the cut


def test_directional_balance_bite_old_algorithm_starves_support_side(tmp_path):
    """BITE (non-vacuous): replay the SAME candidate pool through the OLD 'nearest-6-
    overall' algorithm and show it picks ZERO supports -- the exact failure this change
    fixes, proven by reconstructing the pre-fix logic as a foil."""
    spot = 745.50
    picks = (
        [(abs(p - spot), p, 90.0, None) for p in (745.60, 745.70, 745.90, 746.10, 746.40, 746.60)]
        + [(abs(p - spot), p, 90.0, None) for p in (742.00, 740.50)]
    )
    old_selected = _old_nearest_n_overall(picks, cap=6)
    old_sides = {"resistance" if p >= spot else "support" for _d, p, _s, _m in old_selected}
    assert old_sides == {"resistance"}, "bite: the pre-fix algorithm starves the support side (proven)"


# =====================================================================================
# GUARD 4 -- shelf detection finds the REAL 744.2-745.8 shelf, its 07-23 break, and
# today's (07-27) backside retest, on the real daily series.
# =====================================================================================

def test_shelf_detection_finds_744_745_shelf_broken_and_retested():
    out = dctx.compute_daily_context(bars=list(_REAL_DAILY_BARS), now=_TODAY_ET)
    assert out["ok"] is True
    shelves = out["shelf_zones"]
    hit = [s for s in shelves if s["band_low"] <= 745.40 <= s["band_high"]]
    assert hit, f"no shelf covers J's 745.40 level; shelves={[(s['band_low'], s['band_high']) for s in shelves]}"
    shelf = min(hit, key=lambda s: s["band_high"] - s["band_low"])  # tightest covering band
    assert shelf["band_low"] <= 744.30 and shelf["band_high"] >= 745.70   # ~= the doctrine's 744.2-745.8
    assert shelf["touches"] >= 3
    assert shelf["span_sessions"] >= 10
    assert shelf["broken"] is True
    assert shelf["break"]["direction"] == "down"
    assert shelf["break"]["break_date"] == "2026-07-23"
    assert shelf["backside_retest"]["backside_retest"] is True
    assert shelf["backside_retest"]["from_side"] == "below"


def test_shelf_detection_bite_thin_series_finds_nothing():
    """BITE: strip the series down to too few sessions/touches and confirm no shelf is
    detected -- proving the touch/span thresholds are load-bearing, not decorative."""
    thin = list(_REAL_DAILY_BARS)[-4:]  # 4 sessions -- below SHELF_MIN_SPAN_SESSIONS=10
    out = dctx.compute_daily_context(bars=thin, now=_TODAY_ET)
    hit = [s for s in out["shelf_zones"] if s["band_low"] <= 745.40 <= s["band_high"]]
    assert hit == [], "bite: too few sessions must yield no shelf (span threshold proven load-bearing)"


# =====================================================================================
# GUARD 5 -- gap math correct on 07-27: 738.93 -> 744.91 open
# =====================================================================================

def test_gap_math_correct_2026_07_27():
    out = dctx.compute_daily_context(bars=list(_REAL_DAILY_BARS), now=_TODAY_ET)
    gap = out["gap_state"]
    assert gap["available"] is True
    assert gap["prior_close"] == 738.93
    assert gap["prior_session"] == "2026-07-24"
    assert gap["today_open"] == 744.91
    assert gap["direction"] == "up"
    assert abs(gap["gap_dollars"] - 5.98) < 0.01
    assert abs(gap["gap_pct"] - 0.81) < 0.05          # ~+0.81%, doctrine's stated figure
    assert gap["gap_filled"] is True                   # today's low (735.87) round-tripped the whole gap
    prior = out["prior_day"]
    assert prior == {"date": "2026-07-24", "high": 743.72, "low": 737.29, "close": 738.93}


def test_gap_math_bite_wrong_prior_close_changes_the_answer():
    """BITE: corrupt the prior session's close and confirm the computed gap actually
    changes -- proving the assertions above pin real arithmetic, not a tautology."""
    corrupted = [dict(b) for b in _REAL_DAILY_BARS]
    corrupted[-2] = {**corrupted[-2], "c": 700.00}   # was 738.93
    out = dctx.compute_daily_context(bars=corrupted, now=_TODAY_ET)
    gap = out["gap_state"]
    assert gap["prior_close"] == 700.00
    assert abs(gap["gap_dollars"] - (744.91 - 700.00)) < 0.01
    assert abs(gap["gap_dollars"] - 5.98) > 1.0  # materially different from the real answer


# =====================================================================================
# GUARD 6 -- heartbeat_core._read_levels output BYTE-IDENTICAL before/after (proves the
# live decide path is untouched by the new optional fields).
# =====================================================================================

# expires_at is intentionally a FAR-FUTURE constant, not the day this fixture was authored
# (2026-07-27) -- heartbeat_core._level_expired() compares expires_at's date against the REAL
# current ET date (_et_now(), unmocked here), so a same-day-authored date silently rots the
# moment wall-clock time crosses it: both tests below went RED from 2026-07-28 onward with
# ZERO code change (_read_levels(740.00) returned ([], []) for both old- and new-style input,
# making the "byte-identical" assertion vacuously true and the explicit non-vacuous bite fail).
# First observed red 2026-08-01 (conductor-weekend); root cause confirmed via
# heartbeat_core._level_expired -> today's real date > 2026-07-27 -> every fixture level
# expired -> both active/multi lists empty. Far-future date sidesteps this permanently.
_OLD_STYLE_LEVELS = [
    {"price": 745.40, "role": "resistance", "type": "resistance", "label": "PMH_2026-07-27",
     "tier": "Active", "source": "premarket_high",
     "expires_at": "2099-12-31T16:00:00-04:00"},
    {"price": 738.20, "role": "support", "type": "support", "label": "PML_2026-07-27",
     "tier": "Active", "source": "premarket_low",
     "expires_at": "2099-12-31T16:00:00-04:00"},
    {"price": 744.10, "role": "resistance", "type": "resistance", "label": "SHELF_744_2026-07-27",
     "tier": "Active", "source": "daily_context_shelf",
     "expires_at": "2099-12-31T16:00:00-04:00"},
]

_NEW_STYLE_LEVELS = [
    {**_OLD_STYLE_LEVELS[0], "source_feed": "sip", "n_bars": 66, "volume": 744663.0,
     "weight": 2, "zone_width": 0.3727, "zone_width_provenance": "default_pre_ab"},
    {**_OLD_STYLE_LEVELS[1], "source_feed": "sip", "n_bars": 79, "volume": 37715507.0,
     "weight": 2, "zone_width": 0.3691, "zone_width_provenance": "default_pre_ab"},
    {**_OLD_STYLE_LEVELS[2], "weight": 5, "zone_width": 0.8, "zone_width_provenance": "shelf_band_observed",
     "touches": 10, "span_sessions": 33, "shelf_broken": True,
     "shelf_break": {"direction": "down", "break_date": "2026-07-23"},
     "backside_retest": {"backside_retest": True, "from_side": "below"}},
]


def _read_levels_for(levels, spot, tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    kl.write_text(json.dumps({"schema_version": 3, "levels": levels}), encoding="utf-8")
    monkeypatch.setattr(hc, "STATE", tmp_path)
    return hc._read_levels(spot)


def test_read_levels_byte_identical_old_vs_new_schema(tmp_path, monkeypatch):
    spot = 740.00
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    old_out = _read_levels_for(_OLD_STYLE_LEVELS, spot, tmp_path / "old", monkeypatch)
    new_out = _read_levels_for(_NEW_STYLE_LEVELS, spot, tmp_path / "new", monkeypatch)
    assert old_out == new_out, f"heartbeat_core._read_levels output changed: {old_out} != {new_out}"
    assert old_out[0] != []  # non-vacuous: there IS output to compare


def test_read_levels_bite_a_real_price_change_is_NOT_byte_identical(tmp_path, monkeypatch):
    """BITE: prove the comparison above actually discriminates -- change a PRICE (not just
    add fields) and confirm _read_levels output DOES differ, so 'byte-identical' isn't a
    vacuously-true comparison of two empty/degenerate outputs."""
    spot = 740.00
    (tmp_path / "old").mkdir()
    (tmp_path / "changed").mkdir()
    old_out = _read_levels_for(_OLD_STYLE_LEVELS, spot, tmp_path / "old", monkeypatch)
    changed = [{**lv, "price": lv["price"] + 5.0} for lv in _OLD_STYLE_LEVELS]
    changed_out = _read_levels_for(changed, spot, tmp_path / "changed", monkeypatch)
    assert old_out != changed_out, "bite: a genuine price change must be visible to _read_levels"
