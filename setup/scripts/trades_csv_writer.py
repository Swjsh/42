"""
trades_csv_writer.py -- the ONE sanctioned way to append a row to journal/trades.csv
(or journal/trades-aggressive.csv). Rule 8 (journal every trade).

FIXES B8 (2026-09-01): 25/556 historical rows in journal/trades.csv overflowed the
44-column header because archetype_match_json (and a few RECONCILE_FILL rows) were
built as raw comma-joined / hand-escaped text instead of run through csv.writer with
QUOTE_MINIMAL -- embedded commas and backslash-escaped quotes inside the JSON payload
split a row across extra columns and broke pandas.read_csv (flagged 2026-07-18,
LESSONS-LEARNED.md, never fixed until now). Repair of the 25 already-corrupted rows is
a one-off (see backtest/tests/test_trades_csv_integrity_2026_09_01.py); this module is
the fix for every row written FROM HERE ON.

Any code OR prose-instructed manual append (automation/prompts/*/eod-flatten.md, the
`log-trade` skill) must go through append_trade_row() / make_archetype_json() below --
never hand-splice a comma-joined row string, and never wrap JSON text in your own quote
characters. csv.DictWriter with quoting=csv.QUOTE_MINIMAL handles ALL of that correctly
by construction: any value containing a comma, a quote, or a newline gets doubled-quote
CSV escaping automatically, so the archetype JSON's internal commas/quotes can never
split the row again.

Schema mirrors setup/scripts/fleet_journal_bridge.py's SCHEMA byte-for-byte (that
module already writes safely via csv.writer -- this module exists so every OTHER
producer of trades.csv rows gets the same safety for free, without importing the
bridge's broker-fills-specific machinery).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TRADES_CSV = REPO / "journal" / "trades.csv"
TRADES_CSV_AGGRESSIVE = REPO / "journal" / "trades-aggressive.csv"

# Canonical 44-column schema -- must match the live header of journal/trades.csv and
# fleet_journal_bridge.SCHEMA. Verified against the live header by
# backtest/tests/test_trades_csv_integrity_2026_09_01.py.
SCHEMA: list[str] = [
    "date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
    "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
    "dollar_pnl", "r_multiple", "stop_px", "target_px", "dollar_risk",
    "pct_risk_of_acct", "account_equity_pre", "followed_rules", "setup_quality",
    "fill_quality", "gamma_recommended", "j_override", "hold_minutes",
    "trade_grade", "trade_grade_score", "delta_at_entry", "iv_at_entry",
    "iv_regime", "slippage_cents", "exit_slippage_cents", "tod_bucket",
    "bars_after_trigger", "entry_relative_to_bar", "hold_quality_pct",
    "cf_time_stop_pnl", "cf_high_water_pnl", "archetype_match_json",
    "tape_assistance", "notes_short", "account_id", "theta_at_entry",
]


def make_archetype_json(closest: str, similarity: float) -> str:
    """Build a properly-serialized archetype_match_json value.

    Never hand-write JSON text (`'{"closest":"' + closest + '"...'`) for this column --
    that string-building pattern is exactly what produced the B8 corruption when the
    `closest` value or a following field ever needed a comma or quote.
    """
    return json.dumps({"closest": closest, "similarity": similarity})


def append_trade_row(row: dict[str, Any], csv_path: Path = TRADES_CSV) -> None:
    """Append one row via csv.DictWriter(quoting=QUOTE_MINIMAL) -- the only sanctioned
    append path. Any string value containing a comma/quote/newline (e.g. a JSON blob
    from make_archetype_json, or a notes_short sentence with a comma in it) is quoted
    correctly and automatically; nothing here can ever split a row into extra columns.

    Fails loudly (raises) on an unknown column name rather than silently dropping or
    misplacing data -- per OP judgment guards, no silent fallback.
    """
    unknown = set(row) - set(SCHEMA)
    if unknown:
        raise ValueError(f"append_trade_row: unknown column(s) {sorted(unknown)} not in SCHEMA")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SCHEMA, quoting=csv.QUOTE_MINIMAL, restval="")
        if needs_header:
            w.writeheader()
        w.writerow(row)
