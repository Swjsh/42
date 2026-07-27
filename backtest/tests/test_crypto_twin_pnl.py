"""Guards for crypto_twin_pnl -- the twin's first realized-P&L surface.

THE REGRESSION THIS FILE EXISTS FOR: the first cut of this module treated "no scenario tag" as
organic, and reported **10 real decisions when the true count was zero**. Absence of evidence
got printed as evidence, on the one number J actually reads. Untagged must always quarantine to
UNKNOWN, never inflate ORGANIC.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import crypto_twin_pnl as p  # noqa: E402


def _journal(tmp_path: Path, rows: list[dict]) -> Path:
    f = tmp_path / "journal.jsonl"
    with open(f, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return f


def _pair(ts_e: str, ts_x: str, entry: float, exit_: float, scenario=None, **exit_extra):
    return [
        {"event": "ENTRY_QUALITY", "ts_utc": ts_e, "fill_price": entry, "scenario": scenario},
        {"event": "EXIT_FILLED", "ts_utc": ts_x, "fill_price": exit_, "scenario": scenario,
         "reason": "structure_stop @ 100", **exit_extra},
    ]


# ------------------------------------------------------------------ THE bug, pinned
def test_untagged_scenario_is_UNKNOWN_never_organic(tmp_path):
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=None))
    trips = p.reconstruct_trips(f)
    assert len(trips) == 1
    assert trips[0]["bucket"] == "UNKNOWN", "untagged must never be counted as a real decision"


def test_report_states_zero_organic_when_only_untagged_exist(tmp_path):
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=None))
    txt = p.report(f)
    assert "ZERO organic round trips" in txt
    assert "never made a trade of its own" in txt


def test_explicit_organic_signal_counts(tmp_path):
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=p.ORGANIC))
    assert p.reconstruct_trips(f)[0]["bucket"] == "ORGANIC"


def test_known_battery_scenario_is_forced(tmp_path):
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario="ENTRY_CAT_CAP"))
    assert p.reconstruct_trips(f)[0]["bucket"] == "FORCED"


def test_unrecognised_scenario_string_also_quarantines(tmp_path):
    """A NEW scenario tag nobody taught this module about must not default to organic."""
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario="SOME_FUTURE_TAG"))
    assert p.reconstruct_trips(f)[0]["bucket"] == "UNKNOWN"


# ------------------------------------------------------------------ P&L math + provenance
def test_reconstructed_pct_math(tmp_path):
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=p.ORGANIC))
    t = p.reconstruct_trips(f)[0]
    assert abs(t["pct"] - 1.0) < 1e-9
    assert t["source"] == "reconstructed"


def test_wired_realized_pct_wins_over_reconstruction(tmp_path):
    """When the exit row carries a wired number, trust it over our own pairing arithmetic."""
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=p.ORGANIC,
                                 realized_pct=0.42, realized_usd=1.23, btc_qty=0.0024))
    t = p.reconstruct_trips(f)[0]
    assert t["pct"] == 0.42 and t["usd"] == 1.23
    assert t["source"] == "wired"


def test_no_dollar_data_reports_none_not_zero(tmp_path):
    """'$0.00' and 'we have no dollar data' must never look the same."""
    f = _journal(tmp_path, _pair("t1", "t2", 100.0, 101.0, scenario=p.ORGANIC))
    s = p.summarize(p.reconstruct_trips(f))
    assert s["total_usd"] is None and s["n_with_usd"] == 0
    assert "$ n/a" in p.report(f)


def test_win_rate_and_totals(tmp_path):
    rows = (_pair("a1", "a2", 100.0, 102.0, scenario=p.ORGANIC)
            + _pair("b1", "b2", 100.0, 99.0, scenario=p.ORGANIC))
    s = p.summarize(p.reconstruct_trips(_journal(tmp_path, rows)))
    assert s["n"] == 2 and s["wins"] == 1 and s["win_rate"] == 50.0
    assert abs(s["total_pct"] - 1.0) < 1e-6


# ------------------------------------------------------------------ robustness
def test_unpaired_open_entry_is_not_counted(tmp_path):
    """An entry with no exit yet is an OPEN position, not a zero-P&L round trip."""
    f = _journal(tmp_path, [{"event": "ENTRY_QUALITY", "ts_utc": "t1", "fill_price": 100.0}])
    assert p.reconstruct_trips(f) == []


def test_malformed_and_missing_files_never_raise(tmp_path):
    bad = tmp_path / "journal.jsonl"
    bad.write_text("{not json\nnull\n[]\n", encoding="utf-8")
    assert p.reconstruct_trips(bad) == []
    assert p.reconstruct_trips(tmp_path / "absent.jsonl") == []
    assert "Crypto twin" in p.report(tmp_path / "absent.jsonl")


def test_report_is_cp1252_encodable(tmp_path):
    """It runs headless on a Windows console -- a stray emoji killed an earlier run."""
    rows = (_pair("a1", "a2", 100.0, 102.0, scenario=p.ORGANIC)
            + _pair("b1", "b2", 100.0, 99.0, scenario="ENTRY_CAT_CAP")
            + _pair("c1", "c2", 100.0, 99.0, scenario=None))
    p.report(_journal(tmp_path, rows)).encode("cp1252")
