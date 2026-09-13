"""Guard for GOAL-SUBTRACTION-2026-09-11 item (c): the 'Engine Misses Today' journal section
must never report a negative (or zero) dollar figure as "missed edge" / "P&L left on the
table". Live scar: journal/2026-09-10.md printed "54 missed setups, -$839 ... left on the
table" -- setups that would have NET LOST money are not missed edge; sitting them out was
correct. See missed_setups_section.py's inline comment for the full fix rationale.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MODPATH = REPO / "backtest" / "autoresearch" / "eod_deep" / "missed_setups_section.py"
_spec = importlib.util.spec_from_file_location("missed_setups_section_g", _MODPATH)
mss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mss)  # type: ignore[union-attr]


def _setup(pnl: float, setup: str = "SHOTGUN_SCALPER_TIER_1", why: str = "engine did not fire") -> dict:
    return {
        "setup": setup,
        "direction": "CALL" if pnl >= 0 else "PUT",
        "strike": "ATM",
        "would_be_pnl_dollars": pnl,
        "would_be_hold_minutes": 12,
        "why_missed": why,
    }


def _interaction(bar_time: str, level: float, setups: list) -> dict:
    return {
        "bar_time": bar_time,
        "level": level,
        "interaction_type": "rejection",
        "qualifying_setups": setups,
    }


def _base_scan_result(interactions: list, *, total_pnl: float, engine_trades: int = 0,
                       engine_pnl: float = 0.0) -> dict:
    missed_count = sum(len(i["qualifying_setups"]) for i in interactions)
    return {
        "missed_setup_count": missed_count,
        "missed_setup_total_pnl_dollars": total_pnl,
        "edge_capture_pct": 0.0,
        "engine_trades_today": engine_trades,
        "engine_pnl_today": engine_pnl,
        "level_interactions": interactions,
        "scan_warnings": [],
        "opra_available": True,
    }


# --------------------------------------------------------------------------------------- #
# 1. RED-PROOF TARGET: the 2026-09-10 shape -- net-negative aggregate, some winners exist
#    but losers outweigh them -- headline must show the POSITIVE-only sum, never the raw
#    net negative figure as "left on the table".
# --------------------------------------------------------------------------------------- #
def test_net_negative_day_headline_never_shows_a_negative_dollar_figure() -> None:
    interactions = [
        _interaction("09:35", 741.84, [_setup(150.0), _setup(-300.0)]),
        _interaction("10:05", 738.20, [_setup(-250.0), _setup(-339.0)]),
    ]
    scan = _base_scan_result(interactions, total_pnl=150.0 - 300.0 - 250.0 - 339.0,
                              engine_trades=5, engine_pnl=-790.0)
    assert scan["missed_setup_total_pnl_dollars"] == -739.0  # sanity on the fixture itself

    md = mss.render_section(scan)
    headline = md.splitlines()[2]
    assert "-$" not in headline, f"headline must never carry a negative $ figure: {headline!r}"
    assert "+$150" in headline, "the one winner's $150 must be the headline figure, not the net -$739"
    assert "left on the table" in headline
    assert "loser" in headline.lower()


# --------------------------------------------------------------------------------------- #
# 2. All-loser day (no winners at all) -- must print "no positive missed edge", never a
#    dollar figure.
# --------------------------------------------------------------------------------------- #
def test_all_losers_prints_no_positive_missed_edge() -> None:
    interactions = [_interaction("09:35", 741.84, [_setup(-100.0), _setup(-50.0)])]
    scan = _base_scan_result(interactions, total_pnl=-150.0, engine_trades=0, engine_pnl=0.0)

    md = mss.render_section(scan)
    headline = md.splitlines()[2]
    assert "no positive missed edge" in headline
    assert "left on the table" not in headline, (
        "the DONE-WHEN-forbidden framing -- a net loss must never be presented as "
        "'P&L left on the table'"
    )
    # the net figure MAY still appear as CONTEXT (why sitting it out was correct), it is
    # just never framed as missed edge / left on the table.
    assert "-$150" in headline


# --------------------------------------------------------------------------------------- #
# 3. Net-positive day (winners dominate) -- unaffected, still shows the (now positive-only,
#    which here equals a smaller number than the old net-of-everything total) headline.
# --------------------------------------------------------------------------------------- #
def test_net_positive_day_shows_positive_only_sum_with_loser_note() -> None:
    interactions = [_interaction("09:35", 741.84, [_setup(1000.0), _setup(-100.0)])]
    scan = _base_scan_result(interactions, total_pnl=900.0, engine_trades=1, engine_pnl=200.0)

    md = mss.render_section(scan)
    headline = md.splitlines()[2]
    assert "+$1,000" in headline, f"headline should show the winners-only sum: {headline!r}"
    assert "1 would-be loser" in headline


# --------------------------------------------------------------------------------------- #
# 4. All-winners day -- no loser_note clause, no spurious "(before 0 ...)" text.
# --------------------------------------------------------------------------------------- #
def test_all_winners_day_has_no_loser_note() -> None:
    interactions = [_interaction("09:35", 741.84, [_setup(500.0)])]
    scan = _base_scan_result(interactions, total_pnl=500.0, engine_trades=0, engine_pnl=0.0)

    md = mss.render_section(scan)
    headline = md.splitlines()[2]
    assert "+$500" in headline
    assert "before" not in headline


# --------------------------------------------------------------------------------------- #
# 5. Zero missed setups -- unaffected pre-existing branch (regression pin).
# --------------------------------------------------------------------------------------- #
def test_zero_missed_setups_unaffected() -> None:
    scan = _base_scan_result([], total_pnl=0.0, engine_trades=3, engine_pnl=120.0)
    md = mss.render_section(scan)
    assert "No qualifying missed setups detected" in md


# --------------------------------------------------------------------------------------- #
# 6. Live replay: reproduce the ACTUAL 2026-09-10 journal shape (54 setups, -$839 net) and
#    assert the regenerated section never carries "-$839" as a headline dollar figure.
# --------------------------------------------------------------------------------------- #
def test_2026_09_10_shape_replay_no_negative_headline() -> None:
    # 3 winners summing +$300, enough losers to net -$839 overall (matches the real day's
    # reported total_pnl of -$839 and count of 54 -- exact per-setup breakdown is not
    # reconstructable from the journal alone, so this uses a representative distribution).
    winners = [_setup(100.0), _setup(100.0), _setup(100.0)]
    losers = [_setup(-1139.0 / 51)] * 51  # 51 losers summing to -1139, net with +300 = -839
    interactions = [_interaction("09:35", 741.84, winners + losers)]
    scan = _base_scan_result(interactions, total_pnl=300.0 - 1139.0, engine_trades=5,
                              engine_pnl=-790.0)

    md = mss.render_section(scan)
    headline = md.splitlines()[2]
    assert "-$839" not in headline, f"the exact live-scar figure must not reappear: {headline!r}"
    assert "+$300" in headline
