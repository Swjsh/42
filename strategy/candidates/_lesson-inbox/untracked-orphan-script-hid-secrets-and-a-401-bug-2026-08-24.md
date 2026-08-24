---
filed: 2026-08-24
filed_by: conductor fire (AFTERHOURS, no-console-popups guard RED investigation)
kind: lesson
status: pending
---

# An untracked, never-wired script can carry a live secret + a silent auth bug for days — nobody is watching it

## Symptom

`backtest/tests/test_window_leak_compliance.py::test_no_py_subprocess_missing_creationflags`
went RED (`incident_fix_status.py --alert`: `no-console-popups` RED). Root cause was 3
`subprocess.run()` calls in `setup/scripts/mcp_audit_probe.py` missing
`creationflags=CREATE_NO_WINDOW`. Investigating that one file surfaced two much more
consequential, completely unrelated bugs sitting in the same file:

1. Two Alpaca account key/secret pairs hardcoded in plaintext (`ALPACA_API_KEY` +
   `ALPACA_SECRET_KEY` for both Safe-2 and Bold-2, verbatim, in a `.py` file).
2. `probe_alpaca()` accepted a `secret` parameter and never put it in the request
   headers — every single probe call 401'd regardless of real account health. This was
   the exact, sole root cause of a live `## Known broken` STATUS.md entry
   (`MCP_AUDIT_RED: Alpaca Safe/Bold MCP servers offline or unreachable`, filed
   2026-08-23T22:30:35Z) that had been sitting un-diagnosed, reading as a real outage.

`git ls-files setup/scripts/mcp_audit_probe.py` returned nothing — the file had **never
been committed**. `conductor-outcomes.jsonl` shows a prior fire built it, but no fire ever
finished wiring it to a scheduled task or committing it. It sat on disk, executable,
carrying live secrets, silently 401-ing every run, for at least 1 day (the MCP_AUDIT_RED
timestamp) — found only because an *unrelated* compliance regex (`no-console-popups`)
happened to scan every `.py` file in `setup/scripts/` including this one.

## Root cause

The repo's automated hygiene checks (`self_check.py`'s `CANDIDATES-UNTRACKED`,
`auto_commit_candidates.py`) only watch `strategy/candidates/` for untracked-file drift.
Nothing watches `setup/scripts/` (or any other code directory) for a script that got
built, left uncommitted, and never wired to anything. Such a file is invisible to every
producer/consumer contract, every scheduled-task registry check, and every git-tracked
secrets scan — it exists in a blind spot between "built" and "shipped" (the C35 class:
"built+tested+RED-proofed != shipped until committed") except *worse*, because this file
was never even proposed for shipping — it was abandoned mid-build.

## Why this is a CLASS, not a one-off

Any autonomous fire that builds a script and doesn't finish the full loop (build → test →
commit → wire-to-a-caller-or-delete) leaves exactly this shape of landmine: a live,
executable, secret-bearing file with zero producer/consumer visibility. The specific
instance here (hardcoded creds + a masked 401 that looked like a real outage) is a
worst-case combination, but the general pattern — "a fire built X, moved on, X was never
committed or wired" — will recur for ANY future half-finished build unless something
periodically sweeps for it.

## The fix (this fire)

Fixed the 3 immediate bugs in place: `creationflags` added to all subprocess.run calls;
secrets replaced with a `.mcp.json` runtime loader (matching `fast_path_executor.py`'s
established pattern); the missing `APCA-API-SECRET-KEY` header added. Committed clean
(`2d703a27`) — the file is no longer untracked, no longer carries a secret, and its own
`## Known broken` false-alarm was annotated RESOLVED, not deleted.

## Open follow-up (not this fire's scope)

`mcp_audit_probe.py` is STILL not wired to any `Gamma_*` scheduled task — it exists,
is correct, and is invoked by nothing except its own test/audit files. A future fire
should either wire it into a real weekly-MCP-audit cadence or explicitly mark it
dead/superseded (it may duplicate `engine-health.json`'s existing MCP-adjacent checks —
not verified this fire).

**Generalizable guard worth building:** a periodic sweep (e.g. inside `self_check.py`)
for `.py` files under `setup/scripts/`, `automation/`, or `backtest/` that are untracked
AND older than some threshold (mirroring `CANDIDATES-UNTRACKED`'s existing shape, just
widened beyond `strategy/candidates/`) — and, separately, a lightweight static secrets
grep (`APCA-API-KEY-ID\s*[:=]\s*["']PK`, `ALPACA_SECRET_KEY\s*[:=]\s*["'][A-Za-z0-9]{30,}`
etc.) run against untracked `.py` files specifically, since those are the files most
likely to carry a copy-pasted credential that was never meant to persist. Not built this
fire — filing as the lesson so a future fire (or `lesson-author` grading this) can decide
whether it clears the bar to graduate to code.
