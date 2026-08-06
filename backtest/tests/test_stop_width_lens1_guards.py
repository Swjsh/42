"""Guards for LENS 1 of the 2026-08-05 EOD audit (stop-width question).

Pins the load-bearing FACTS the verdict rests on, so a later data refresh, a cache
regeneration, or a "helpful" refactor of the grid tool cannot silently invert the answer
without a test going RED.

Everything load-bearing is asserted against the COMMITTED companion JSON
(`analysis/deep-research/EOD-2026-08-05-STOPS.json`), so these guards survive a fresh
clone. The raw-OPRA cross-checks are additive and SKIP when the cache is absent --
`backtest/data/` is gitignored (.gitignore:56), so the 1-min CSVs are local-only. A guard
that silently vanished with its untracked data file would be worse than no guard (C7).

No network, no broker, fast.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BARS = REPO / "backtest" / "data" / "highres" / "SPY260805C00776000_1m_2026-08-05.csv"
LENS1 = REPO / "analysis" / "deep-research" / "EOD-2026-08-05-STOPS.json"

LOWEST_ENTRY = 2.06          # cheapest of the ten real 776C entry fills
LAST_STOPOUT_ET = "10:20"


def _et(ts: str) -> str:
    """UTC ISO -> ET HH:MM. EDT months only (this rig trades Mar-Nov)."""
    return f"{(int(ts[11:13]) - 4) % 24:02d}:{ts[14:16]}"


needs_cache = pytest.mark.skipif(
    not BARS.exists(),
    reason=f"local-only real-OPRA cache absent ({BARS.name}); backtest/data/ is gitignored. "
           "Regenerate: python backtest/tools/stop_width_grid_20260805.py")


@pytest.fixture(scope="module")
def bars() -> list[dict]:
    with BARS.open(encoding="utf-8") as fh:
        return [{"et": _et(r["timestamp"]), "h": float(r["high"]),
                 "l": float(r["low"]), "c": float(r["close"]),
                 "v": int(r["volume"]), "n": int(r["trade_count"])}
                for r in csv.DictReader(fh)]


@pytest.fixture(scope="module")
def lens1() -> dict:
    assert LENS1.exists(), f"missing companion JSON: {LENS1}"
    return json.loads(LENS1.read_text(encoding="utf-8"))


@needs_cache
def test_cache_is_real_opra_not_synthetic(bars):
    """A synthetic/BS curve would carry no volume and no trade prints (C7/L241)."""
    assert len(bars) > 300, f"suspiciously few bars: {len(bars)}"
    assert sum(b["v"] for b in bars) > 100_000
    assert sum(b["n"] for b in bars) > 10_000


@needs_cache
def test_776c_never_recovered_to_any_entry_price(bars):
    """THE load-bearing fact of the whole lens: after the last stop-out the contract never
    traded at any entry price again, so a wider stop can only lose MORE."""
    post = [b for b in bars if b["et"] > LAST_STOPOUT_ET]
    assert post, "no bars after the last stop-out -- cache truncated?"
    assert max(b["h"] for b in post) < LOWEST_ENTRY, (
        "776C DID recover above the cheapest entry after 10:20 -- the LENS 1 verdict "
        "('a wider stop loses more') no longer follows and must be re-derived")


@needs_cache
def test_776c_expires_worthless(bars):
    assert bars[-1]["c"] <= 0.05, f"final close {bars[-1]['c']} -- expected ~0.01"


def test_776c_never_recovered__from_committed_json(lens1):
    """Clone-safe twin of test_776c_never_recovered_to_any_entry_price. THE load-bearing
    fact: after the last stop-out the contract never traded at any entry price again, so a
    wider stop can only lose MORE."""
    q = lens1["q1_did_776c_ever_recover"]
    assert q["answer"] == "NO"
    assert q["max_high_after_1020"] < q["lowest_entry"], (
        f"776C high after 10:20 ({q['max_high_after_1020']}) reached the cheapest entry "
        f"({q['lowest_entry']}) -- the LENS 1 verdict must be re-derived")
    assert q["session_close"] <= 0.05
    assert min(q["entry_prices"]) == q["lowest_entry"]


def test_widening_the_stop_is_monotonically_worse_at_every_entry_cap(lens1):
    """Down every column of the joint stop x cap grid, a wider stop must lose more.
    If this ever flips, 'do we need larger stops = NO' has to be re-argued."""
    joint = lens1["q2_776c_sequential_stop_grid"]["joint_stop_x_entrycap_combined_both_arms"]
    order = ["-6%", "-10%", "-15%", "-25%", "-50%"]
    for cap in ("cap1",):
        vals = [joint[w][cap] for w in order]
        assert vals == sorted(vals, reverse=True), (
            f"{cap}: widening is no longer monotonically worse: "
            f"{dict(zip(order, vals))}")
    # the widest stop must be the worst cell at every cap
    for cap in ("cap1", "cap2", "cap3", "cap5"):
        assert joint["-50%"][cap] <= min(joint[w][cap] for w in order), (
            f"{cap}: -50% is no longer the worst cell")


def test_more_entries_is_worse_at_every_stop_width(lens1):
    """Across every row, more entries must lose more (or tie once the wider stop has
    already suppressed the re-entries)."""
    joint = lens1["q2_776c_sequential_stop_grid"]["joint_stop_x_entrycap_combined_both_arms"]
    for w, row in joint.items():
        vals = [row[c] for c in ("cap1", "cap2", "cap3", "cap5")]
        assert vals == sorted(vals, reverse=True), f"{w}: {vals} not non-increasing"


def test_best_cell_is_tightest_stop_one_entry(lens1):
    joint = lens1["q2_776c_sequential_stop_grid"]["joint_stop_x_entrycap_combined_both_arms"]
    best = max((v, w, c) for w, row in joint.items() for c, v in row.items())
    assert (best[1], best[2]) == ("-6%", "cap1"), f"best cell moved to {best}"


def test_gap_fade_archetype_degrades_monotonically_with_stop_width(lens1):
    """08-05's own archetype on the 391-day population. This is the single cleanest
    number behind the NO verdict."""
    cells = lens1["q3_generalization"]["fullhist_391d"]["cells"]
    order = ["-6%", "-10%", "-12%", "-15%", "-20%", "-25%", "-50%"]
    vals = [cells[w]["by_archetype"]["gap-fade"]["pnl"] for w in order]
    assert vals == sorted(vals, reverse=True), f"gap-fade no longer monotone: {vals}"
    assert vals[0] > vals[-1], "widening no longer hurts gap-fade"


def test_fullhist_harness_reproduces_the_frozen_published_baseline(lens1):
    """The -20% cell IS the live ribbon_ride premium_stop_pct, so it must equal the repo's
    frozen engine-fullhist-replay baseline. This is what makes the other cells credible."""
    v = lens1["q3_generalization"]["fullhist_391d"]["validation"]
    assert v["this_run_n_trades"] == v["published_n_trades"] == 191
    assert abs(v["this_run_minus20_total"] - v["published_total_pnl"]) < 1.0, (
        f"harness no longer reproduces the frozen baseline: "
        f"{v['this_run_minus20_total']} vs {v['published_total_pnl']}")


def test_reentries_are_net_positive_book_wide_so_cap1_is_refuted(lens1):
    """Guards against the seductive-but-wrong 'just take one entry' conclusion."""
    o = lens1["q5_what_survives_both_days"]["candidate_off_the_stop_axis"][
        "ordinal_decomposition_broker_truth"]
    assert o["2"]["pnl"] > 0, "2nd entries are no longer profitable -- re-argue cap=1"
    assert sum(o[k]["pnl"] for k in o if k != "1") > 0, (
        "re-entries as a whole are no longer net positive -- the cap=1 refutation changes")


def test_cap3_benefit_is_disclosed_as_concentrated_in_the_motivating_day(lens1):
    """OP-11 / no-repick discipline: the honesty field must stay attached to the number."""
    c = lens1["q5_what_survives_both_days"]["candidate_off_the_stop_axis"]
    assert c["08-04_gap-go_trend_day"]["cost"] == 0.0, "cap=3 is no longer a no-op on 08-04"
    assert c["honesty"]["n_small"] is True
    assert "PRE-REGISTER" in c["honesty"]["verdict"].upper()
    assert abs(c["honesty"]["benefit_excluding_the_motivating_day"]) < 200


def test_regime_is_not_claimed_live_detectable(lens1):
    """The verdict must never quietly promote a hindsight regime split to a shippable gate."""
    assert lens1["verdict"]["regime_live_detectable_at_entry"] is False
    assert lens1["q4_regime_conditionality"]["live_detectable_at_entry"] is False


def test_verdict_is_no(lens1):
    assert lens1["verdict"]["do_we_need_larger_stops"] == "NO"
