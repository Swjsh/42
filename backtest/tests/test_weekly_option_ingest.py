"""Guards for backtest/tools/fetch_weekly_option_data.py (weekly-lane option-bar ingestion).

The headline guard is `test_bar_window_starts_before_expiry_window`, which pins a REAL bug
caught on the first live ingest (2026-08-18): the expiry-selection window and the bar-fetch
window were passed the same start date, so any contract expiring near the window start had its
entire price path excluded and arrived carrying only its expiry-day bar. It looked healthy --
the manifest reported 99% "coverage" -- because coverage counted contracts that returned ANY
bar. 275 of 11,551 contracts (2.4%) were silently truncated. A multi-day backtest reading those
would have modeled a week-long hold against a single pathological expiry-day print.

Fixed by fetching bars from expiry_window_start - BAR_LOOKBACK_DAYS. Post-fix: truncated
contracts 275 -> 53 (the remainder genuinely traded on only one day), usable >=5-bar paths
9,466 -> 10,309.

No network in any test here: the API-touching seams are monkeypatched.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "backtest" / "tools" / "fetch_weekly_option_data.py"


def _load():
    spec = importlib.util.spec_from_file_location("fetch_weekly_option_data", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load()


def _contract(symbol="QQQ260601C00700000", expiry="2026-06-01", oi="5000"):
    return {
        "symbol": symbol,
        "root_symbol": "QQQ",
        "expiration_date": expiry,
        "strike_price": "700",
        "type": "call",
        "open_interest": oi,
    }


def test_bar_window_starts_before_expiry_window(monkeypatch):
    """REGRESSION: bars must be fetched from BEFORE the earliest expiry, not from it.

    This is the guard for the 2026-08-18 truncation bug. If the bar-fetch start ever equals
    the expiry-window start again, every contract expiring in the first days of the window
    loses its price path while still counting as 'covered'.
    """
    seen: dict[str, dt.date] = {}

    def fake_iter_contracts(root, start, end, key, secret):
        yield _contract()

    def fake_fetch_bars(symbols, start, end, key, secret):
        seen["bars_start"] = start
        seen["bars_end"] = end
        return {symbols[0]: [{"t": "2026-05-28T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2,
                              "v": 10, "n": 3, "vw": 1.5}]}

    monkeypatch.setattr(MOD, "iter_contracts", fake_iter_contracts)
    monkeypatch.setattr(MOD, "fetch_bars", fake_fetch_bars)
    monkeypatch.setattr(MOD, "write_contract_csv", lambda root, sym, rows: Path("/dev/null"))

    expiry_start = dt.date(2026, 6, 1)
    summary = MOD.ingest_root("QQQ", expiry_start, dt.date(2026, 8, 14), "k", "s", min_oi=250)

    assert seen["bars_start"] < expiry_start, (
        f"bar-fetch start {seen['bars_start']} is not before the expiry-window start "
        f"{expiry_start} -- contracts expiring early in the window will be truncated to "
        f"their expiry-day bar (the 2026-08-18 bug)."
    )
    assert seen["bars_start"] == expiry_start - dt.timedelta(days=MOD.BAR_LOOKBACK_DAYS)
    assert summary["bars_window_start"] < summary["expiry_window_start"], (
        "the manifest must record BOTH windows so a future reader can tell whether a thin "
        "contract was genuinely thin or merely truncated by the fetch window"
    )


def test_screen_drops_illiquid_contracts():
    """Coverage is volume-gated: fetching bars for OI~1 contracts yields phantom 2-bar series."""
    contracts = [
        _contract(symbol="A", oi="5000"),
        _contract(symbol="B", oi="1"),
        _contract(symbol="C", oi=None),
        _contract(symbol="D", oi=""),
        _contract(symbol="E", oi="250"),
    ]
    kept = {c["symbol"] for c in MOD.screen(contracts, min_oi=250)}
    assert kept == {"A", "E"}, f"screen kept {kept}; expected only the OI>=250 contracts"


def test_empty_screen_fails_loud_instead_of_writing_empty_cache(monkeypatch):
    """Silent success is this shop's #1 documented failure. An empty screen must raise."""
    monkeypatch.setattr(MOD, "iter_contracts", lambda *a, **k: iter([_contract(oi="1")]))
    with pytest.raises(MOD.IngestError, match="zero contracts cleared"):
        MOD.ingest_root("QQQ", dt.date(2026, 6, 1), dt.date(2026, 8, 14), "k", "s", min_oi=250)


def test_screened_but_no_bars_fails_loud(monkeypatch):
    """Contracts that screen fine but return no bars = API/credential problem, not empty market."""
    monkeypatch.setattr(MOD, "iter_contracts", lambda *a, **k: iter([_contract()]))
    monkeypatch.setattr(MOD, "fetch_bars", lambda *a, **k: {})
    with pytest.raises(MOD.IngestError, match="NONE returned bars"):
        MOD.ingest_root("QQQ", dt.date(2026, 6, 1), dt.date(2026, 8, 14), "k", "s", min_oi=250)


def test_expiry_day_bars_are_flagged_not_dropped():
    """Expiry-day prints are pathological (observed: low 0.07 on 381k volume) -- flag, keep."""
    c = _contract(expiry="2026-06-01")
    bars = [
        {"t": "2026-05-29T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 5, "n": 2, "vw": 1.5},
        {"t": "2026-06-01T04:00:00Z", "o": 2, "h": 3, "l": 0.07, "c": 1, "v": 99, "n": 9, "vw": 1},
    ]
    rows = MOD.rows_for(c, bars)
    assert len(rows) == 2, "expiry-day bar must be retained, not dropped"
    assert [r["is_expiry_day"] for r in rows] == [0, 1]


@pytest.mark.parametrize(
    "bar_utc,expected",
    [
        # EDT (UTC-4): 04:00Z is midnight ET the SAME calendar day.
        ("2026-06-01T04:00:00Z", dt.date(2026, 6, 1)),
        # EST (UTC-5): 05:00Z is midnight ET the same day.
        ("2026-01-15T05:00:00Z", dt.date(2026, 1, 15)),
        # The DST trap: 04:00Z in JANUARY is 23:00 ET on the PREVIOUS day. A hardcoded -04:00
        # offset (the repo's documented DST-frame scar) would wrongly report Jan 15.
        ("2026-01-15T04:00:00Z", dt.date(2026, 1, 14)),
    ],
)
def test_bar_date_et_is_dst_correct(bar_utc, expected):
    assert MOD._bar_date_et(bar_utc) == expected
