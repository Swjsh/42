---
source: conductor-weekend
filed: 2026-08-09T00:xx ET
status: pending
---

# Copy-pasted fixed-position CSV loader broke 3 sibling probes identically

**Queue item closed this fire:** `BXM-PROBE-TRADES-CSV-HEADER-DRIFT-FIX` (filed 2026-08-08,
fixed 2026-08-09 conductor WEEKEND, commits `7dfa8059` + `e26140c2`).

**What happened:** `journal/trades.csv` gained a new trailing column (`theta_at_entry`,
added 2026-08-01 by the THETA COCKPIT build) AFTER the existing `account_id` column. Three
independent research probes -- `bxm_gate_probe.py`, `vix1d_gate_probe.py`, and
`fred_yield_curve_probe.py` -- each had their OWN copy of an identical `_load_real_trades()`
helper (same docstring boilerplate, same `header[-1] == "account_id"` assertion, same
`row[-1]` read) and all three broke on the exact same day, the exact same way. The bug was
filed once (against `bxm_gate_probe.py`, which happened to be the one caught by a routine
safety-gate run), and the sibling in the SAME docstring (`vix1d_gate_probe.py`, explicitly
named in the original filer's own text) was fixed alongside it -- but a THIRD sibling
(`fred_yield_curve_probe.py`) was only found by grepping `header[-1]|row[-1]` across the
whole repo AFTER fixing the first two, not from the original bug report.

**Root cause (one sentence):** copy-paste propagates fragility identically -- three files
sharing one brittle assumption (`account_id` is always the LAST column) will always break on
the SAME calendar day, because the shared assumption breaks on the shared trigger (a new
trailing column landing in the shared source file), not on three independent occasions.

**Fix applied:** all three loaders now resolve `account_id` via `header.index("account_id")`
(name-based) instead of a fixed relative position, robust to any FUTURE trailing-column
append; the header assertion still fails LOUD (C7) if `account_id` is genuinely removed
rather than relocated. One guard test file, parametrized across all 3 probe modules
(`backtest/tests/test_trades_csv_header_drift_guard.py`), so a 4th sibling probe added later
that copies the SAME loader shape would need to opt INTO the parametrize list to get covered
-- it will not be auto-discovered.

**Proposed graduation (OP-25):** when a bug is found in one file via a docstring/comment
that explicitly names a "sibling" or "same loader shape as X" file, the fix pass should
ALWAYS grep the whole repo for the specific fragile pattern (here: `header[-1]` /
`row[-1]` used against a growing CSV) rather than trusting the docstring's own list of named
siblings -- the docstring itself can be stale/incomplete, as it was here (2 named siblings,
3 actual siblings). A standing lint/grep-based guard (e.g. a repo-wide pytest that asserts NO
`.py` file under `backtest/` reads a stably-named CSV column via a fixed negative or absolute
numeric index once that CSV is known to grow columns over time) would catch a 4th
recurrence automatically instead of requiring another manual "oh, one more turned up" pass.
