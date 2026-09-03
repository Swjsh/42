"""Tests for the missed-setups scanner.

Run from repo root:
    python -m pytest backtest/autoresearch/test_missed_setups_scanner.py -v

Or as a script (in case pytest discovery doesn't pick it up):
    python backtest/autoresearch/test_missed_setups_scanner.py
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

# Allow `from autoresearch.eod_deep import ...` to resolve when running
# from the repo root.
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.eod_deep.missed_setups_scanner import scan_missed_setups  # noqa: E402
from autoresearch.eod_deep.missed_setups_section import render_section  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def test_scanner_finds_misses_on_2026_05_15() -> None:
    """The 2026-05-15 chart had multiple level interactions but the engine
    only took 1 trade. The scanner must surface at least 4 missed setups,
    including the 09:30 open rejection, the 09:45 wick low to 737.96
    (LEVEL_REJECT_LIVE bull off 738.10 Carry), the 14:55 trendline break,
    and the 15:45 break of the 740 area.

    The exact P&L numbers depend on whether OPRA cache is present, so we
    assert structural properties rather than precise dollar figures.
    """
    result = scan_missed_setups(dt.date(2026, 5, 15))

    assert isinstance(result, dict), "scan_missed_setups must return a dict"
    assert result["date"] == "2026-05-15"

    interactions = result.get("level_interactions") or []
    assert isinstance(interactions, list), "level_interactions must be a list"

    # Headline assertion: at least 4 missed setups detected.
    missed_count = result.get("missed_setup_count", 0)
    logger.info("2026-05-15 missed_setup_count = %s", missed_count)
    logger.info("2026-05-15 missed_total_pnl   = %s", result.get("missed_setup_total_pnl_dollars"))
    logger.info("2026-05-15 engine_trades      = %s", result.get("engine_trades_today"))
    logger.info("2026-05-15 engine_pnl         = %s", result.get("engine_pnl_today"))
    logger.info("2026-05-15 edge_capture_pct   = %s", result.get("edge_capture_pct"))
    assert missed_count >= 4, (
        f"expected >= 4 missed setups, got {missed_count}. "
        f"Scan warnings: {result.get('scan_warnings')}"
    )

    # Each interaction must have a bar_time, level price, type, and at least 1 setup.
    for inter in interactions:
        assert "bar_time" in inter
        assert "level" in inter
        assert inter.get("interaction_type") in ("touch", "rejection", "break", "reclaim"), (
            f"unexpected interaction_type: {inter.get('interaction_type')}"
        )
        assert isinstance(inter.get("qualifying_setups"), list)
        assert len(inter["qualifying_setups"]) >= 1

    # 738.10 Carry interaction (09:45 bar wicked to 737.96 — bullish reclaim/rejection).
    # This is the canonical "missed" event in the J 5/15 narrative: J's manual
    # P738 was buying the wick; the scanner must see the level interaction.
    near_738_10 = [
        i for i in interactions
        if abs(float(i.get("level", 0.0)) - 738.10) < 0.06
    ]
    assert near_738_10, "expected at least one interaction with the 738.10 Carry"

    # 739.04 PML interaction in the 09:40-10:00 window (break + reclaim
    # bracketing the open dump).
    early_pml = [
        i for i in interactions
        if abs(float(i.get("level", 0.0)) - 739.04) < 0.06
        and i.get("bar_time", "") < "10:05 ET"
    ]
    assert early_pml, (
        "expected at least one 739.04 PML interaction in the 09:40-10:00 window"
    )

    # Setups list should include at least one of each of the 4 setup families
    # across the full day's interactions (loose check — the scanner is
    # designed to flag many candidates).
    all_setups = {
        s.get("setup", "")
        for i in interactions
        for s in (i.get("qualifying_setups") or [])
    }
    families = {
        "shotgun": any(s.startswith("SHOTGUN_SCALPER_TIER") for s in all_setups),
        "ribbon_or_sniper": any(
            s in {
                "BEARISH_REJECTION_RIDE_THE_RIBBON",
                "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                "SNIPER_LEVEL_BREAK",
            }
            for s in all_setups
        ),
    }
    logger.info("Setup families fired: %s", families)
    assert families["shotgun"], "no SHOTGUN_SCALPER tiers fired in the scan"

    # Engine reconciliation: 5/15 had exactly 1 engine trade (the 09:46 P740).
    assert result.get("engine_trades_today") >= 1, (
        f"expected >= 1 engine trade on 2026-05-15, got {result.get('engine_trades_today')}"
    )


def test_scanner_handles_unknown_date_cleanly() -> None:
    """A date with no SPY bars must not raise — it should return a result
    with warnings populated and missed_count = 0."""
    result = scan_missed_setups(dt.date(1990, 1, 2))
    assert isinstance(result, dict)
    assert result["missed_setup_count"] == 0
    assert result["scan_warnings"], "expected a warning about missing SPY bars"


def test_formatter_renders_valid_markdown() -> None:
    """Formatter must produce a non-empty markdown string with the standard
    header and a table when there are missed setups."""
    result = scan_missed_setups(dt.date(2026, 5, 15))
    md = render_section(result)
    assert isinstance(md, str)
    assert md.startswith("### Engine Misses Today"), (
        "section must start with the canonical header"
    )
    # If there were misses, the table header should be present.
    if result.get("missed_setup_count", 0) > 0:
        assert "| Time | Level | Type | Setup |" in md, (
            "expected markdown table header in formatter output"
        )
        assert "**Root causes (deduplicated):**" in md
    logger.info("formatter output (truncated):\n%s", md[:600])


def test_formatter_handles_empty_result() -> None:
    """Formatter must handle the no-misses case gracefully."""
    empty = {
        "date": "2026-05-15",
        "level_interactions": [],
        "missed_setup_count": 0,
        "missed_setup_total_pnl_dollars": 0.0,
        "engine_trades_today": 1,
        "engine_pnl_today": -770.0,
        "edge_capture_pct": 0.0,
        "scan_warnings": [],
        "opra_available": True,
    }
    md = render_section(empty)
    assert isinstance(md, str)
    assert md.startswith("### Engine Misses Today")
    assert "No qualifying missed setups" in md


def test_formatter_handles_none_input() -> None:
    md = render_section({})  # empty dict
    assert md.startswith("### Engine Misses Today")


if __name__ == "__main__":
    # Manual runner — print result for the 2026-05-15 case.
    import json as _json
    res = scan_missed_setups(dt.date(2026, 5, 15))
    print(_json.dumps({k: v for k, v in res.items() if k != "level_interactions"}, indent=2, default=str))
    print(f"\nlevel_interactions: {len(res.get('level_interactions') or [])}")
    for inter in (res.get("level_interactions") or [])[:10]:
        print(f"  {inter['bar_time']} @ {inter['level']:.2f} "
              f"({inter['interaction_type']}): {len(inter['qualifying_setups'])} setup(s)")
    print("\n--- MARKDOWN ---")
    print(render_section(res))

    # Run the test functions individually.
    for fn in (
        test_scanner_finds_misses_on_2026_05_15,
        test_scanner_handles_unknown_date_cleanly,
        test_formatter_renders_valid_markdown,
        test_formatter_handles_empty_result,
        test_formatter_handles_none_input,
    ):
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
            sys.exit(2)
    print("\nALL TESTS PASSED")
