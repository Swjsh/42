# journal/trades.csv: unescaped literal `"` inside `archetype_match_json` notes text corrupts LATE columns for that row

**Found:** 2026-07-18, conductor (AFTERHOURS), while building TRADE-TO-LEARN-CUMULATIVE-DIGEST.

**Symptom:** the two 2026-07-16 `VWAP_CONTINUATION` backfilled rows in `journal/trades.csv` have
their `archetype_match_json` field's embedded notes text containing a literal `"` character that
was never CSV-doubled (`""`) to escape it inside the quoted field. `csv.DictReader` treats that
raw `"` as the end of the quoted field, so everything after it in the row (the rest of
`archetype_match_json`, `tape_assistance`, `notes_short`, `account_id`) gets shifted/garbled —
`row["account_id"]` for those 2 rows returns a fragment of the notes text, not `"safe"`.

**Root cause:** whatever wrote those 2 rows (per the notes: `fleet_journal_bridge.py` /
a manual backfill, 2026-07-16 per the notes) serialized `archetype_match_json` with
`json.dumps(...)` but then embedded it into the CSV row WITHOUT going through `csv.writer`'s
own quote-escaping (which doubles `"` -> `""` inside a quoted field) — likely a raw f-string /
manual quote-wrap instead of `csv.writer.writerow(...)`.

**Impact (bounded, not fixed this fire):** any consumer that reads COLUMNS AFTER
`archetype_match_json` (account_id, notes_short) is UNRELIABLE for these 2 rows specifically.
Consumers reading only EARLY columns (date/time/setup/dollar_pnl/etc, before the corruption
point) are unaffected — verified directly: `dollar_pnl` parses correctly for all 179 rows in
the file including these 2 (`trade_to_learn_digest.load_real_fills` only reads early columns
and is provably unaffected, guarded by
`test_trade_to_learn_digest.py::test_real_csv_malformed_quoting_rows_still_parse_early_columns`).

**Fix (not done this fire — scope discipline; the digest doesn't need the corrupted columns):**
whatever writer path produced these 2 rows should route `archetype_match_json` through
`csv.writer` (or `csv.DictWriter`) instead of manual string concatenation, so Python's own
CSV module handles quote-doubling. A follow-up sweep of `journal/trades.csv` for OTHER rows
with the same defect (any row where a downstream column reads garbled) would be worth a quick
`csv.Sniffer`-style pass before trusting `account_id`/`notes_short` broadly.

**Generalizable lesson:** any pipeline that builds a CSV row by hand-embedding a JSON string
(rather than through `csv.writer`) is one un-doubled internal quote away from silently
corrupting every column after it in that row — and because `csv.DictReader` doesn't error on
this (it just mis-assigns fields), the corruption is SILENT (C7 class: silent success is
failure). Prefer `csv.writer`/`csv.DictWriter` for any row containing embedded JSON, never
raw string formatting into a `.csv`.
