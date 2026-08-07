"""Guard: SSR battery exhibit-date (2026-08-07) narrative must be grounded in a
computed per-symbol breakdown, not a hand tally over the (symbol, direction,
combo) cell table.

Round-1 fixer finding (2026-08-07, BLOCKING): a prior narrative claimed "NQ=F
and ES=F DID fire signals+trades on 2026-08-07 (8 NQ/ES trades total, all
losers or marginal)" -- undercounting the true 20 trades by 60% (missed all
12 ES=F rows) and mischaracterizing the 4 ES=F long winners (+$2144.17 each,
~median win size for the family) as "marginal".

Root cause: no persisted, machine-computed per-symbol exhibit-date breakdown
existed, so the count was hand-tallied off a 24-row grid table and drifted.

Fix under test: `run_ssr_battery._headline_by_symbol_exhibit` computes and
persists that breakdown; these tests pin (a) its reconciliation with the
existing family-level headline total on synthetic fixtures (pure-logic,
deterministic, no I/O), and (b) the real numbers in the currently-persisted
futures-ssr-smoke.json, so a re-introduced undercount or mischaracterization
REDs immediately.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_BACKTEST_DIR = _REPO / "backtest"
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))

from futures.ssr.run_ssr_battery import (  # noqa: E402
    EXHIBIT_DATE,
    _headline_by_symbol_exhibit,
    _headline_with_without_exhibit,
)

SMOKE_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-smoke.json"


def _fake_cell(symbol: str, dates_nets: list[tuple[dt.date, float]]) -> dict:
    return {"symbol": symbol,
            "trades": [{"date": d, "net": n} for d, n in dates_nets]}


def _synthetic_cells() -> list[dict]:
    """Mirrors the real shape: multiple symbols, multiple cells per symbol
    (as multiple direction/combo grid cells would produce), some exhibit-date
    trades winning and some losing, plus non-exhibit-date trades that must be
    excluded from the breakdown entirely."""
    other_day = EXHIBIT_DATE - dt.timedelta(days=3)
    return [
        _fake_cell("NQ=F", [(EXHIBIT_DATE, -4423.23), (other_day, 100.0)]),
        _fake_cell("NQ=F", [(EXHIBIT_DATE, -9407.03)]),
        _fake_cell("ES=F", [(EXHIBIT_DATE, 2144.17), (EXHIBIT_DATE, 2144.17)]),
        _fake_cell("ES=F", [(EXHIBIT_DATE, -2074.03), (EXHIBIT_DATE, -2037.00)]),
    ]


def test_by_symbol_breakdown_reconciles_with_family_headline_total():
    cells = _synthetic_cells()
    headline = _headline_with_without_exhibit(cells)
    by_symbol = _headline_by_symbol_exhibit(cells)

    n_from_breakdown = sum(b["n"] for b in by_symbol.values())
    assert n_from_breakdown == headline["n_trades_on_2026_08_07"]
    assert n_from_breakdown == 6  # 2 NQ + 4 ES on the exhibit date; the 5th NQ trade is a different day

    net_from_breakdown = sum(b["total_net"] for b in by_symbol.values())
    exhibit_net_from_headline = round(headline["with_2026_08_07"] - headline["without_2026_08_07"], 2)
    assert abs(net_from_breakdown - exhibit_net_from_headline) < 0.01


def test_by_symbol_breakdown_excludes_non_exhibit_dates():
    cells = _synthetic_cells()
    by_symbol = _headline_by_symbol_exhibit(cells)
    assert by_symbol["NQ=F"]["n"] == 2  # NOT 3 -- the other_day trade must not leak in


def test_by_symbol_breakdown_separates_winners_from_losers():
    cells = _synthetic_cells()
    by_symbol = _headline_by_symbol_exhibit(cells)
    assert by_symbol["NQ=F"]["n_winners"] == 0
    assert by_symbol["NQ=F"]["n_losers"] == 2
    assert by_symbol["ES=F"]["n_winners"] == 2
    assert by_symbol["ES=F"]["n_losers"] == 2


def _load_smoke_json() -> dict:
    if not SMOKE_JSON.exists():
        import pytest
        pytest.skip(f"{SMOKE_JSON} not present -- run run_ssr_battery.py --family A first")
    return json.loads(SMOKE_JSON.read_text(encoding="utf-8"))


def test_persisted_smoke_json_exhibit_total_is_20_not_8():
    """Pins the true family-A exhibit-date trade count. The finding's wrong
    narrative said 8; the real number (also independently corroborated by the
    JSON's own headline field) is 20."""
    payload = _load_smoke_json()
    headline = payload["headline_with_without_exhibit_2026_08_07"]
    assert headline["n_trades_on_2026_08_07"] == 20


def test_persisted_smoke_json_by_symbol_breakdown_is_present_and_reconciles():
    payload = _load_smoke_json()
    by_symbol = payload.get("exhibit_day_breakdown_by_symbol")
    assert by_symbol, "exhibit_day_breakdown_by_symbol must be persisted for family A"
    total_n = sum(b["n"] for b in by_symbol.values())
    assert total_n == payload["headline_with_without_exhibit_2026_08_07"]["n_trades_on_2026_08_07"]


def test_persisted_smoke_json_es_exhibit_trades_are_not_all_losers():
    """Guards the second half of the finding: ES=F's exhibit-date trades were
    mischaracterized as 'all losers or marginal'. ES=F must show at least one
    winner on 2026-08-07 (its 4 LONDON_LOW long fills)."""
    payload = _load_smoke_json()
    by_symbol = payload.get("exhibit_day_breakdown_by_symbol") or {}
    es = by_symbol.get("ES=F")
    assert es is not None, "ES=F must have fired on the exhibit date"
    assert es["n_winners"] > 0, "ES=F's exhibit-date trades were mischaracterized as all losers"
