# PowerShell Compatibility (relocated from CLAUDE.md 2026-06-28)

- Target PowerShell 5.1 syntax — no em-dashes, no PS 7+ only features — in all scripts and one-liners.
- Before running any resilience/cleanup script, dry-run trace every process it would kill and every file it would delete. Confirm none belong to the active Claude session, dev server (port 3000), or build artifacts (`.next`, `node_modules`).

## Scheduled-task trigger permission envelope (found 2026-08-26)

A conductor session's process token can **create/modify CALENDAR-based triggers** (`-Daily`,
`-Once`, `/SC DAILY`, `/SC ONCE`) freely via `Register-ScheduledTask`, `Set-ScheduledTask`
(on an existing task), and `schtasks /Create` — but is **`Access Denied` for EVENT-based
triggers** (`-AtLogOn`, `-AtStartup`, `/SC ONLOGON`, `/SC ONSTART`), on both brand-new tasks
and when adding one to an existing task's trigger set. `Enable-ScheduledTask` (toggling an
already-registered task) is unaffected. Reproduced via disposable dummy-task A/B probes
(`/SC ONCE`/`/SC DAILY` succeeded, `/SC ONLOGON`/`/SC ONSTART` denied, same shell, same
moment) — this is a token/privilege boundary, not a per-task ACL quirk.

**Practical implication:** if a fix design calls for an at-boot/at-logon recovery trigger
(e.g. to catch a missed evening run after a reboot), do NOT spend a fire probing
`Register-ScheduledTask`/`schtasks /Create ONLOGON` — it will fail. Default instead to
**adding extra DAILY trigger slots to the existing task** (`Set-ScheduledTask` with an
appended `-Daily` trigger list), paired with an idempotent skip-if-already-ran-today guard
in the target script so the extra slots are safe no-ops after the first real run of the day.
Full incident + the dress-rehearsal fix that used this pattern:
`strategy/candidates/_lesson-inbox/2026-08-26-scheduled-task-permission-envelope.md`.
