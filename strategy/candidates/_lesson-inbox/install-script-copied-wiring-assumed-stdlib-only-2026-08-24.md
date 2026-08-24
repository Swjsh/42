# Lesson candidate: an install script copied from a sibling inherits the sibling's interpreter choice, not its dependency list

**Filed:** 2026-08-24 01:xx ET (conductor AFTERHOURS)
**Class:** C7 (silent success is failure) + C9-adjacent (install-script wiring drift)

## Symptom

`Gamma_EarningsCalendar` (registered 2026-08-21) crashed on every single scheduled fire
(07:50 ET, 08-21 through 08-23) with `FATAL earnings_calendar.py: No module named
'yfinance'` — invisible to Task Scheduler (`LastTaskResult=0` throughout, the
fire-and-forget wscript hop masks the child's real exit code) and invisible to a casual
glance at `self_check.py`'s output, which correctly flagged `EARNINGS-CALENDAR STALE`
but gave no hint that the underlying cause was "crashing every time," not "never ran."

## Root cause

`install-earnings-calendar.ps1` was built by copying `install-macro-calendar.ps1`'s
wiring verbatim (both installers even said so in their own doc comments — "mirrors
Gamma_MacroCalendar's exact wiring"). `macro_calendar.py` is genuinely stdlib-only, so
system Python313's `pythonw.exe` is correct for it. `earnings_calendar.py` does
`import yfinance`, which only exists in `backtest\.venv` — the copy-paste carried over
the WRONG interpreter choice along with the wiring shape, and nobody re-checked the new
target script's own import list before shipping.

## Generalizable rule

Before wiring any new install-*.ps1 by copying a sibling's Action string: grep the
TARGET script's own `import`/`from` lines for anything outside the stdlib, and if found,
route the INNER hop through `backtest\.venv\Scripts\pythonw.exe` (the proven
split-interpreter pattern in `install-ledger-archive.ps1`), never system Python313's
pythonw — even if the sibling installer being copied used system pythonw correctly for
ITS OWN (different) target script.

## Suggested guard (not built this fire, scope was the one concrete instance)

A repo-wide static check: for every `install-*.ps1` under `setup/scripts/`, extract the
target `.py` script's import list; if it imports anything outside stdlib AND the
install script's inner hop uses system Python313 pythonw (not backtest-venv pythonw),
flag it. Would have caught this bug at authoring time instead of 3 days into silent
production failures. `test_install_script_relay_wiring_drift.py` is the closest
existing precedent (same "static source-parse, no live Task Scheduler query" style) but
checks relay PRESENCE, not interpreter CORRECTNESS for a given script's deps — a
different, adjacent bug class.

## Fix landed this fire (narrow, not the generalized guard)

`install-earnings-calendar.ps1` fixed + guard test
`backtest/tests/test_earnings_calendar_install_wiring_2026_08_24.py` pins the specific
wiring so THIS task can't regress. First occurrence of this exact pattern (not a
re-violation of an existing lesson) — the generalized cross-repo scanner is a candidate
for a future fire if this class resurfaces on a different task.
