"""Guard suite for setup/scripts/winner_signature.py -- the "what does our money look like" organ.

Covers the PURE layer (no ledger, no network): the conventions the headline rests on. The
rails these guards protect are the ones whose failure would be SILENT and would mislead J
into shipping a survivorship artifact as an edge:

  1. THE WAVE CONVENTION. Up to 6 arms enter ONE impulse within seconds. If `wavify` ever
     stops collapsing them, every bucket in the report silently gains ~4x the apparent
     evidence and a 5-session anecdote starts reading as a 400-trade study.
  2. NO LOOK-AHEAD IN THE DAY-STOP COUNTERFACTUAL. The stop may only see P&L from trades
     that had ALREADY EXITED at the moment of the next entry. Letting a still-open (or
     later-exiting) trade's result into that sum turns the whole §4 table into an oracle.
  3. FAIL LOUDLY ON AN EMPTY POPULATION. An empty journal must raise, never write a
     confident-looking report over zero fills (C7: silent success is failure).
  4. EXIT-MULTIPLE BANDING. The band boundaries are the spine of §1; an off-by-one at 1.0x
     would move losers into the winner column.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import winner_signature as ws  # noqa: E402


def _rec(date="2026-08-04", sec=34200, pnl=0.0, xsec=None, arm="safe", **kw):
    base = dict(date=date, arm=arm, side="C", setup="X", pnl=pnl, qty=1.0, entry=1.0,
                exitp=1.0, mult=1.0, hold=10.0, sec=sec, xsec=xsec, hr=sec // 3600,
                vix=15.0, ribbon_width=50.0, ribbon="BULL", htf="BULL", quality="BASE",
                triggers=None, has_ctx=True)
    base.update(kw)
    return base


# ---------------------------------------------------------------------------------
# 1. THE WAVE CONVENTION -- correlated arms must collapse to ONE unit of evidence
# ---------------------------------------------------------------------------------
def test_simultaneous_arms_collapse_into_one_wave():
    """Six arms entering the same impulse seconds apart is ONE piece of evidence."""
    recs = [_rec(arm=a, sec=34200 + i, pnl=100.0) for i, a in enumerate(
        ["safe", "bold", "safe-1", "safe-3", "risky-1", "risky-3"])]
    waves = ws.wavify(recs)
    assert len(waves) == 1, "correlated arm entries must not each count as independent evidence"
    assert waves[0]["pnl"] == pytest.approx(600.0)


def test_gap_longer_than_window_starts_a_new_wave():
    recs = [_rec(sec=34200), _rec(sec=34200 + ws.WAVE_GAP_S + 1)]
    assert len(ws.wavify(recs)) == 2


def test_gap_exactly_at_window_stays_one_wave():
    """Boundary is inclusive -- pinned so a refactor cannot quietly widen the denominator."""
    recs = [_rec(sec=34200), _rec(sec=34200 + ws.WAVE_GAP_S)]
    assert len(ws.wavify(recs)) == 1


def test_waves_do_not_span_days():
    recs = [_rec(date="2026-08-04", sec=57000), _rec(date="2026-08-05", sec=34200)]
    assert len(ws.wavify(recs)) == 2


def test_wave_nth_is_per_day_and_one_indexed():
    recs = [_rec(date="2026-08-04", sec=34200),
            _rec(date="2026-08-04", sec=34200 + ws.WAVE_GAP_S + 1),
            _rec(date="2026-08-05", sec=34200)]
    waves = ws.wavify(recs)
    assert [w["nth"] for w in waves] == [1, 2, 1]
    assert [r["wave_nth"] for r in recs] == [1, 2, 1]


# ---------------------------------------------------------------------------------
# 2. NO LOOK-AHEAD -- the stop may only see ALREADY-EXITED trades
# ---------------------------------------------------------------------------------
def _day_stop_kept(rows, threshold):
    """Mirror of the §4 counterfactual, isolated so the rule itself is testable."""
    kept = []
    for r in sorted(rows, key=lambda x: x["sec"]):
        realized = sum(q["pnl"] for q in rows if q["xsec"] is not None and q["xsec"] <= r["sec"])
        if realized <= -threshold:
            continue
        kept.append(r)
    return kept


def test_day_stop_ignores_a_trade_that_has_not_exited_yet():
    """A big loser still OPEN at the next entry must NOT arm the stop -- we could not have
    known it yet. This is the difference between a counterfactual and an oracle."""
    still_open = _rec(sec=34200, pnl=-500.0, xsec=50000)   # exits long after the 2nd entry
    later = _rec(sec=36000, pnl=+300.0, xsec=40000)
    kept = _day_stop_kept([still_open, later], threshold=100)
    assert later in kept, "an unexited loss must not retroactively block the next entry"


def test_day_stop_arms_on_an_already_exited_loss():
    closed = _rec(sec=34200, pnl=-500.0, xsec=35000)
    later = _rec(sec=36000, pnl=+300.0, xsec=40000)
    kept = _day_stop_kept([closed, later], threshold=100)
    assert later not in kept
    assert kept == [closed], "the losing trade itself is taken; only what FOLLOWS is blocked"


def test_day_stop_never_blocks_the_first_trade_of_the_day():
    only = _rec(sec=34200, pnl=-900.0, xsec=35000)
    assert _day_stop_kept([only], threshold=50) == [only]


# ---------------------------------------------------------------------------------
# 3. FAIL LOUDLY -- never write a confident report over an empty population
# ---------------------------------------------------------------------------------
def test_main_raises_rather_than_writing_an_empty_report(monkeypatch, tmp_path):
    """Redirect the outputs into tmp so a regression cannot clobber the real report, then
    assert BOTH that it raised and that it left nothing behind."""
    md, js = tmp_path / "SIGNATURE.md", tmp_path / "signature.json"
    monkeypatch.setattr(ws, "OUT_MD", md)
    monkeypatch.setattr(ws, "OUT_JSON", js)
    monkeypatch.setattr(ws, "load_trades", lambda: [])
    with pytest.raises(SystemExit):
        ws.main()
    assert not md.exists() and not js.exists(), "wrote a report over an empty population"


# ---------------------------------------------------------------------------------
# 4. EXIT-MULTIPLE BANDING -- the spine of section 1
# ---------------------------------------------------------------------------------
@pytest.mark.parametrize("mult,band", [
    (3.92, "≥2.0×"), (2.0, "≥2.0×"), (1.999, "1.3–2.0×"), (1.3, "1.3–2.0×"),
    (1.299, "1.0–1.3×"), (1.0, "1.0–1.3×"), (0.999, "0.7–1.0×"), (0.7, "0.7–1.0×"),
    (0.699, "<0.7×"), (0.0, "<0.7×"), (None, None),
])
def test_exit_multiple_bands_are_pinned(mult, band):
    assert ws._mult_band(mult) == band


# ---------------------------------------------------------------------------------
# 5. PARSING -- a malformed journal row must be skipped, never coerced
# ---------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("$1,234.50", 1234.5), ("-63", -63.0), ("", None), ("N/A", None), (None, None),
])
def test_num_is_strict(raw, expected):
    assert ws._num(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("09:46:04", 35164), ("09:46", 35160), ("", None), ("abc", None), (None, None),
])
def test_secs_is_strict(raw, expected):
    assert ws._secs(raw) == expected


def test_known_arms_matches_fleet_arms_plus_core():
    """The arm allowlist is what keeps malformed CSV rows (embedded newlines in
    notes_short land the note text in account_id) out of the P&L totals."""
    assert set(ws.FLEET_ARMS) < ws.KNOWN_ARMS
    assert {"safe", "bold"} < ws.KNOWN_ARMS
