# Macro calendar hand list goes stale silently (found 2026-09-08 new-week readiness check)

**Symptom:** `setup/scripts/macro_calendar.py#KNOWN_EVENTS_2026` carried no CPI/PPI/NFP after July
(last hand entry NFP 2026-08-07, then FOMC 09-16). Fri 09-04 NFP, Thu 09-10 PPI and Fri 09-11 CPI
were invisible; premarket's today-bias would have said "no macro events today" on CPI day.
`Gamma_MacroCalendar` fired daily rc=0 and news.json read `stale: false` -- freshness measured the
FILE, not the COVERAGE.

**Root cause:** BLS returns HTTP 403 to this host, so the only source is a hand-curated list that
nothing refreshes and nothing audits for forward coverage. C7 shape (silent success): a fresh stamp
on an empty window.

**Fix shipped:** PPI 09-10 + CPI 09-11 added (web-verified). Live tick path unaffected
(heartbeat_core reads no_trade_window only from params.json).

**Guard to graduate:** a coverage assertion, not a mtime check -- fail RED (STATUS Known broken)
when the next 45 calendar days contain no `cpi_release` OR no `nfp_release` entry, since both
recur monthly without exception. Plus a monthly instrument that pulls the BLS schedule via a
host that is not 403'd (or a mirrored source) and diffs against the hand list.

**Theme:** C7 (silent success), C4 (disclose coverage).
