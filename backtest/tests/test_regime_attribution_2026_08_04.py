"""Guards for setup/scripts/regime_attribution.py (LENS 4 nightly instrument, 2026-08-04).

Every test here pins a property that, if it broke, would make the instrument LIE in the
specific way a P&L-attribution instrument is most likely to lie: grading a day against a bar
it helped set, fabricating a 0.0 where there is no evidence, or reporting a concentration
ratio that flips sign or exceeds 1 on a losing day.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import regime_attribution as ra  # noqa: E402


LIB = {
    "2026-01-05": {"archetype": "gap-go"},
    "2026-01-06": {"archetype": "gap-go"},
    "2026-01-07": {"archetype": "range-chop"},
    "2026-01-08": {"archetype": "gap-go"},
    "2026-01-09": {"archetype": "data-incomplete"},
}
PNL = {"2026-01-05": 100.0, "2026-01-06": -40.0, "2026-01-07": 10.0, "2026-01-08": 3000.0}


# --- archetype_share -------------------------------------------------------
def test_share_excludes_data_incomplete_from_the_denominator():
    # 3 gap-go of 4 ASSIGNABLE days (the data-incomplete session is not a day)
    assert ra.archetype_share(LIB, "gap-go") == 0.75
    assert ra.archetype_share(LIB, "range-chop") == 0.25


def test_share_of_never_seen_archetype_is_zero_not_none():
    assert ra.archetype_share(LIB, "pin-day") == 0.0


def test_share_of_empty_library_is_none_not_a_divide_by_zero():
    assert ra.archetype_share({}, "gap-go") is None


# --- prior_mean: the look-ahead guard --------------------------------------
def test_prior_mean_is_strictly_before_the_graded_day():
    """THE load-bearing property. If the graded day is included in its own baseline, a
    headline day silently sets the bar it is measured against and regime_lift collapses."""
    mean, n = ra.prior_mean(PNL, LIB, "gap-go", "2026-01-08")
    assert n == 2 and mean == 30.0            # (100 + -40)/2 -- 3000 excluded
    incl = (100.0 - 40.0 + 3000.0) / 3
    assert mean != pytest.approx(incl)


def test_prior_mean_returns_none_not_zero_when_no_prior_day_exists():
    """A fabricated 0.0 would report a first-of-its-kind day as 'exactly average'."""
    mean, n = ra.prior_mean(PNL, LIB, "range-chop", "2026-01-07")
    assert mean is None and n == 0


def test_prior_mean_ignores_other_archetypes():
    mean, n = ra.prior_mean(PNL, LIB, "range-chop", "2026-01-08")
    assert n == 1 and mean == 10.0


# --- mix_ev ----------------------------------------------------------------
def test_mix_ev_weights_by_population_share_not_by_days_traded():
    """gap-go is 75% of the population but only 3 of 4 traded days here; the point of mix_ev
    is that it must follow the POPULATION mix, so a rare-archetype windfall cannot dominate."""
    ev = ra.mix_ev(PNL, LIB)
    gap_mean = (100.0 - 40.0 + 3000.0) / 3
    assert ev == pytest.approx(0.75 * gap_mean + 0.25 * 10.0, abs=0.02)


def test_mix_ev_coverage_reports_untraded_population_mass():
    lib = dict(LIB, **{"2026-02-02": {"archetype": "pin-day"}})
    cov = ra.mix_ev_coverage(PNL, lib)
    assert 0.0 < cov < 1.0                     # pin-day never traded -> not fully covered
    assert ra.mix_ev_coverage(PNL, LIB) == pytest.approx(1.0)


def test_mix_ev_is_none_with_no_traded_days():
    assert ra.mix_ev({}, LIB) is None


# --- concentration ---------------------------------------------------------
def _rts(*pnls):
    return [{"real_pnl": p} for p in pnls]


def test_concentration_denominator_is_gross_positive_so_shares_stay_in_range():
    """A NET denominator produces a nonsense >100% (or negative) share whenever the day's
    losers are large relative to its net -- which is every interesting day."""
    c = ra.concentration(_rts(500.0, 400.0, -800.0, 50.0))
    assert c["gross_positive"] == 950.0 and c["gross_negative"] == -800.0
    assert 0 < c["top1_share"] <= 1 and 0 < c["top2_share"] <= 1
    assert c["top2_share"] == pytest.approx(900.0 / 950.0, abs=1e-4)   # stored rounded to 4dp


def test_concentration_on_an_all_losing_day_reports_none_not_a_sign_flip():
    c = ra.concentration(_rts(-10.0, -20.0))
    assert c["top1_share"] is None and c["top2_share"] is None
    assert c["gross_positive"] == 0.0 and c["n_roundtrips"] == 2


def test_concentration_of_no_trades_is_empty_not_an_exception():
    c = ra.concentration([])
    assert c["n_roundtrips"] == 0 and c["top1_share"] is None


# --- verdict ---------------------------------------------------------------
def test_verdict_says_n_equals_1_when_there_is_no_prior_day():
    v = ra.verdict(3000.0, None, 0.05, ra.concentration(_rts(3000.0)))
    assert "NO PRIOR" in v and "n=1" in v


def test_verdict_flags_a_two_trade_day_as_concentrated():
    v = ra.verdict(900.0, 10.0, 0.2, ra.concentration(_rts(500.0, 400.0, -50.0, 10.0)))
    assert "CONCENTRATED" in v


def test_verdict_on_no_trades_is_explicit():
    assert "NO TRADES" in ra.verdict(0.0, None, 0.2, ra.concentration([]))


# --- fail-open contract ----------------------------------------------------
def test_build_report_fails_open_on_a_missing_library(monkeypatch):
    monkeypatch.setattr(ra, "load_library", lambda: {})
    rep = ra.build_report("2026-08-04")
    assert rep["status"] == "NO_LIBRARY" and "reason" in rep


def test_build_report_marks_an_untagged_date_loudly(monkeypatch):
    monkeypatch.setattr(ra, "load_library", lambda: LIB)
    monkeypatch.setattr(ra, "day_pnl_map", lambda: ({"2029-12-31": 5.0}, {"2029-12-31": []}))
    rep = ra.build_report()
    assert rep["status"] == "UNTAGGED" and rep["date_et"] == "2029-12-31"


def test_render_never_raises_on_a_non_ok_report():
    assert "REGIME-ATTRIBUTION" in ra.render({"status": "NO_FILLS", "reason": "x"})


# --- history upsert --------------------------------------------------------
def test_history_upsert_is_idempotent_by_date(tmp_path, monkeypatch):
    hist = tmp_path / "attribution-history.jsonl"
    monkeypatch.setattr(ra, "HISTORY", hist)
    rep = {"status": "OK", "date_et": "2026-08-04", "archetype": "gap-go", "day_pnl": 1.0}
    ra.upsert_history(rep)
    ra.upsert_history(dict(rep, day_pnl=2.0))
    rows = [json.loads(x) for x in hist.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1 and rows[0]["day_pnl"] == 2.0


def test_history_upsert_skips_non_ok_reports(tmp_path, monkeypatch):
    hist = tmp_path / "h.jsonl"
    monkeypatch.setattr(ra, "HISTORY", hist)
    ra.upsert_history({"status": "UNTAGGED", "date_et": "2026-08-04"})
    assert not hist.exists()


# --- live wiring -----------------------------------------------------------
def test_live_report_reproduces_the_broker_day_for_2026_08_04():
    """Anchors the instrument to the broker-verified 2026-08-04 total. If the ledger join or
    the FIFO miner drifts, this fails instead of silently reporting a different day."""
    rep = ra.build_report("2026-08-04")
    if rep.get("status") != "OK":
        pytest.skip(f"library/ledger not present in this tree: {rep.get('status')}")
    assert rep["archetype"] == "gap-go"
    assert rep["day_pnl"] == pytest.approx(3624.0, abs=0.01)
    assert set(rep["per_arm"]) == set(ra.ARMS)
    assert rep["concentration"]["n_roundtrips"] == 25
    # today must NOT be inside its own baseline
    assert rep["archetype_mean_prior"] is not None
    assert rep["archetype_mean_prior"] < 0
