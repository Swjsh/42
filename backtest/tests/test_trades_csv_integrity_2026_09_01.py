"""Guard for B8-trades-csv-writer (fixed 2026-09-01).

Root cause (one sentence): journal/trades.csv rows were built by hand-splicing
comma-joined text for archetype_match_json (and, separately, a manual EOD-flatten
RECONCILE_FILL append) instead of going through csv.writer/DictWriter with
QUOTE_MINIMAL, so the JSON payload's embedded commas and backslash-escaped quotes
split 25/556 rows across extra columns and broke pandas.read_csv at line 13
(flagged 2026-07-18 in LESSONS-LEARNED.md, never fixed until this commit).

Pins:
  1. The LIVE journal/trades.csv parses cleanly with pandas at exactly the current
     44-column header width, with zero rows overflowing it -- the concrete symptom
     that was broken before the 2026-09-01 repair.
  2. setup/scripts/trades_csv_writer.py:append_trade_row() -- the sanctioned writer
     for every future append -- round-trips a payload containing a comma AND a
     double-quote inside archetype_match_json (built via make_archetype_json) and
     inside notes_short, without ever producing a row wider than the header.
  3. RED-PROOF: reverting append_trade_row() to naive comma-joined string writing
     (the exact anti-pattern this fix removes) reproduces the corruption -- the
     round-trip row overflows the header -- confirming the test actually exercises
     the mechanism, not just its own scaffolding.

Rail-4 CLEAR: read-only against the live journal/trades.csv (pin 1) plus a
synthetic tmp CSV (pins 2-3). No params/doctrine/orders/heartbeat/filters touched.
"""
import csv
import json
import os
import sys
import tempfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "setup", "scripts"))

import trades_csv_writer as w  # noqa: E402

TRADES_CSV = os.path.join(REPO, "journal", "trades.csv")


def _read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    return header, rows


def test_live_trades_csv_parses_with_no_overflow_rows():
    """The concrete B8 symptom: pandas.read_csv must succeed and every row must fit
    the live 44-column header (no row wider than the header)."""
    pd = pytest.importorskip("pandas")
    header, rows = _read_rows(TRADES_CSV)
    ncols = len(header)
    assert ncols == 44, f"live header is {ncols} cols -- SCHEMA/tests need updating if this is intentional"
    overflow = [i + 2 for i, row in enumerate(rows) if len(row) > ncols]
    assert overflow == [], f"rows still overflow the {ncols}-col header: line(s) {overflow}"

    df = pd.read_csv(TRADES_CSV)
    assert len(df.columns) == ncols
    assert len(df) == len(rows)


def test_append_trade_row_survives_commas_and_quotes_in_json_and_notes():
    """A payload engineered to contain exactly what corrupted the 25 historical rows
    (a comma AND a double-quote inside archetype_match_json, plus a comma inside
    notes_short) must round-trip to a single, correctly-shaped row."""
    with tempfile.TemporaryDirectory() as d:
        path = w.Path(d) / "trades.csv"
        archetype = w.make_archetype_json('bull, "tricky" reclaim', 0.83)
        row = {
            "date": "2026-09-01",
            "time_entry": "09:31:00",
            "time_exit": "09:40:00",
            "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "contract": "SPY 2026-09-01 700C",
            "dollar_pnl": "42",
            "archetype_match_json": archetype,
            "notes_short": 'note with a comma, and a "quoted" phrase',
            "account_id": "safe",
        }
        w.append_trade_row(row, csv_path=path)

        header, rows = _read_rows(str(path))
        assert header == w.SCHEMA
        assert len(rows) == 1
        assert len(rows[0]) == len(w.SCHEMA), (
            f"round-tripped row has {len(rows[0])} fields, expected {len(w.SCHEMA)} "
            "-- the comma/quote payload split the row"
        )

        parsed = dict(zip(header, rows[0]))
        assert json.loads(parsed["archetype_match_json"]) == {
            "closest": 'bull, "tricky" reclaim',
            "similarity": 0.83,
        }
        assert parsed["notes_short"] == 'note with a comma, and a "quoted" phrase'
        assert parsed["account_id"] == "safe"

        # A second append must not disturb the header or the first row.
        w.append_trade_row({"date": "2026-09-02", "account_id": "bold"}, csv_path=path)
        header2, rows2 = _read_rows(str(path))
        assert header2 == w.SCHEMA
        assert len(rows2) == 2
        assert len(rows2[1]) == len(w.SCHEMA)


def test_append_trade_row_rejects_unknown_column():
    """Fail loud (OP judgment guards) on a typo'd column name rather than silently
    dropping it or writing it into the wrong slot."""
    with tempfile.TemporaryDirectory() as d:
        path = w.Path(d) / "trades.csv"
        with pytest.raises(ValueError, match="unknown column"):
            w.append_trade_row({"date": "2026-09-01", "not_a_real_column": "x"}, csv_path=path)


def test_RED_PROOF_naive_comma_join_reproduces_the_corruption():
    """RED-PROOF: writing the SAME payload the old, broken way (hand-joined comma
    string, JSON quoted with a bare '"' wrapper -- the exact anti-pattern B8 removed)
    must overflow the header, confirming this test suite actually catches the
    mechanism and isn't just checking its own scaffolding."""
    with tempfile.TemporaryDirectory() as d:
        path = w.Path(d) / "trades.csv"
        archetype_naive = '"' + json.dumps({"closest": 'bull, "tricky" reclaim', "similarity": 0.83}) + '"'
        values = [""] * len(w.SCHEMA)
        values[w.SCHEMA.index("date")] = "2026-09-01"
        values[w.SCHEMA.index("archetype_match_json")] = archetype_naive
        values[w.SCHEMA.index("notes_short")] = 'note with a comma, and a "quoted" phrase'
        values[w.SCHEMA.index("account_id")] = "safe"
        naive_line = ",".join(values)  # <-- the exact B8 anti-pattern: no CSV quoting at all
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(",".join(w.SCHEMA) + "\n")
            fh.write(naive_line + "\n")

        header, rows = _read_rows(str(path))
        assert len(rows) == 1
        assert len(rows[0]) > len(w.SCHEMA), (
            "expected the naive comma-join to overflow the header (reproducing B8) -- "
            "if this now passes, the RED-PROOF payload no longer exercises the bug"
        )
