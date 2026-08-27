# Lesson candidate: this session's scheduler token can CREATE (DAILY/ONCE) and ENABLE/MODIFY-EXISTING tasks, but NOT register ONLOGON/ONSTART triggers

> Queued by conductor 2026-08-26 (after-hours fire). Class C8 (headless Windows spawn / scheduler mechanics) + a new sub-pattern worth its own note.

## Symptom
Self-check flagged `DRESS-REHEARSAL STALE (RED)`: `Gamma_DressRehearsal` (a daily 20:45 ET
trigger) had not run since 2026-08-23 — 3 consecutive missed nights. `Get-ScheduledTaskInfo`
showed `NumberOfMissedRuns=3`. Investigation (Kernel-Power event log) found the box reboots
most evenings in the 18:00-22:00 MT window, landing directly in the single daily trigger's
window; `StartWhenAvailable=True` was already set but Task Scheduler's catch-up does not
reliably recover more than one missed occurrence in a row. The SAME evening-window pattern
was visible across ~15 other `Gamma_*` tasks (`Get-ScheduledTaskInfo … | Where Missed -gt 0`),
not just DressRehearsal — self_check just doesn't happen to assert freshness on the others.

## Root cause (the part worth encoding — a permission boundary, not the reboot itself)
The planned fix was a backup **at-startup / at-logon** trigger to catch the task up shortly
after any reboot. `Register-ScheduledTask` (COM) returned `Access Denied` creating ANY new
task. `schtasks /Create` succeeded for a throwaway `/SC ONCE` and `/SC DAILY` task, but
returned `Access Denied` specifically for `/SC ONLOGON` and `/SC ONSTART` — isolated via
direct A/B probes (`ZZTestProbeDaily` succeeded, `ZZTestProbeOnLogon`/`ZZTestProbeOnStart`
both denied, same shell, same moment). `Set-ScheduledTask` on the EXISTING task also denied
when the new trigger set included an `AtLogOn` trigger, but **succeeded** when the added
triggers were both `-Daily`. `Enable-ScheduledTask` (a no-op on an already-Ready task)
succeeded throughout.

**The pattern: this Claude session's process token can register/modify CALENDAR-based
triggers (Daily/Once) freely, but is denied registering EVENT-based triggers (OnLogon/
OnStart) — on brand-new tasks AND on modifying an existing task's trigger set.** This is
very likely a Windows privilege distinction (event-driven triggers commonly require rights
tied to an elevated/interactive session token this Bash-tool shell doesn't carry), not a
per-task ACL quirk — it reproduced identically on a disposable dummy task name.

## Fix (shipped this fire)
Redesigned around the constraint instead of fighting it: `dress_rehearsal.py` now skips real
work by default whenever today's ET-date artifact already exists (`--force` overrides), and
**two extra DAILY trigger slots** (19:00 MT, 23:15 MT — both permitted) were added to the
EXISTING `Gamma_DressRehearsal` task via `Set-ScheduledTask`, alongside the unchanged 21:44
MT primary. Three chances per evening for an idempotent, self-skipping script to land while
the box happens to be up, instead of one. Verified live: manual run did real work (today was
genuinely stale) and GREENed; a second immediate run correctly no-op'd; self_check's RED
cleared. Commit `12f4a907`.

## Proposed guard / process change (graduate-to-doc candidate)
1. **Doc it as a standing constraint** for future conductor fires: when a fix design calls
   for an at-boot/at-logon recovery trigger, **default to "extra DAILY/hourly trigger slots
   on the existing task via `Set-ScheduledTask`" instead of attempting `Register-ScheduledTask`
   /`schtasks /Create` with `ONLOGON`/`ONSTART`** — the latter will cost a fire's worth of
   probing before failing. This note IS that documentation; fold into
   `markdown/infra/POWERSHELL-COMPAT.md` or a new `SCHEDULED-TASKS.md` "known constraints"
   section (not code-graduable — it's an environment fact, not a bug the repo can fix) so a
   future fire that hits the same access-denied doesn't re-derive it from scratch.
2. **Optional follow-up (not this fire's scope):** the SAME evening-reboot pattern likely
   affects the ~15 other `Gamma_*` tasks flagged with `NumberOfMissedRuns>0` in this fire's
   `Get-ScheduledTaskInfo` sweep. Most are non-critical (research/kitchen/visibility tasks);
   worth a future fire checking whether any of them are self_check-critical the way
   DressRehearsal was, using the same "extra daily slots + idempotent skip" pattern.

## Related
C8 (headless Windows spawn discipline), C11 (broker/OS is the source of truth — verify
live, don't assume a cmdlet "should" work), the `run_exe_hidden.vbs` + `run_cmd_hidden.py`
hidden-launch chain (unaffected by this — the constraint is trigger TYPE, not the launch
mechanism). `automation/state/SCHEDULED-TASKS.md` (registry J reads).
