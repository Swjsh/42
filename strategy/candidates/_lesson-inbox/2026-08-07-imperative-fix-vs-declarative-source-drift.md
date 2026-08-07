## Imperative live-state fix vs declarative source-of-truth drift (2026-08-07, conductor AFTERHOURS)

**Symptom:** `Gamma_CryptoTwin` was migrated onto the `run_cmd_hidden.py` exit-code-visibility
relay on 2026-07-14 (`fix-venv-pythonw-console-leak.ps1`, commit `306e5075`) -- but that fix
was applied IMPERATIVELY (`Set-ScheduledTask -Action ...` against live Task Scheduler state
only). `install-crypto-twin.ps1`, the task's own DECLARATIVE install script (which owns
re-registration whenever anyone legitimately tunes a trigger/cadence/setting), was never
updated to match. Its 2026-08-01 cadence-tune commit (`af849657`, an unrelated 5min->1min
timing change) re-ran that stale template and silently reverted the relay fix -- zero error,
zero log line, zero visible symptom. Confirmed live 2026-08-07: `Get-ScheduledTask` showed
bare venv-pythonw direct invocation again, 3+ weeks after the "fix" shipped.

**Generalization check found 13 MORE instances of the identical bug** (source templates
still emit the old direct wiring; live state currently correct by luck only, because nothing
has legitimately re-run those particular install scripts since the 2026-07-14 imperative
patch): `Gamma_BrokerFills, Confluence, DressRehearsal, EmaSnapshot, FirmBrief,
FreeModelAudit, FuturesMirror, LevelMemory, Prospector, TradeAutopsy, TradeToday, Trendlines,
TwinSentinel`. All 14 (13 + CryptoTwin) fixed this fire.

**Root cause (the general pattern, not the specific bug):** this repo has TWO parallel
descriptions of "what a scheduled task's action should be" -- live Task Scheduler state (what
actually runs) and the install-*.ps1 script (the declarative template that regenerates that
state on any legitimate future edit). A fix applied to ONLY the first is invisible and
temporary: it silently expires the next time anyone touches the second for an unrelated
reason. This is the exact producer/consumer-drift shape C14 already names ("dead/
translated-but-unapplied knobs") but manifesting through TWO writers of the same live state
rather than a config knob nobody reads.

**Fix shipped:** all 14 install-script templates now emit the relay wiring directly, so any
future legitimate re-run cannot regress it. Guard: `backtest/tests/test_install_script_relay_
wiring_drift.py` -- STATIC (no live Task Scheduler calls), asserts each of 15 "should be on
the relay" task's OWN install script contains the relay reference in CODE. Caught its own
false-positive during RED-proofing: a naive `"run_cmd_hidden.py" in text` substring check
was fooled by install-crypto-twin.ps1's PRE-FIX docstring literally saying "no run_cmd_
hidden.py hop needed" in prose -- fixed by stripping PowerShell comments/docstrings before
the check, so only executable code counts.

**Suggested graduation (if this pattern recurs anywhere else in the repo):** ANY time a fix
is applied imperatively against live state that has its own regenerating declarative source
(scheduled tasks, but also e.g. `accounts.json`/`params.json` if a script ever rewrites them
wholesale from a template), the fix must land in BOTH places in the SAME commit, or a static
drift guard (this pattern: parse the declarative source, assert it matches what the live-state
fix intended) must exist before the imperative-only fix is considered "shipped."

**Filed by:** conductor AFTERHOURS fire, 2026-08-07 ~05:30-06:35 ET, commit (pending, this
fire's own).
