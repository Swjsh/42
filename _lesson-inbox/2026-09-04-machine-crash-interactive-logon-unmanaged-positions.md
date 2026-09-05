---
date: 2026-09-04
source: Fable end-of-day audit 2026-09-05 00:02 ET
kind: lesson
---

# A machine crash left two live paper positions unmanaged for 55 minutes -- and no instrument noticed

**Symptom:** core-decisions.jsonl has no rows 09:51:03 -> 10:46:15 ET (664 ticks vs ~770 expected). Both cores (safe-2 3x P772 @1.29, bold-2 5x P770 @0.62, entered 09:46) were open the whole time. Exits at 10:46:06/07 carry broker `source: null` (Alpaca web dashboard) -- J closed them by hand the minute he got back. The intervention counter correctly logged 2 `engine_entered_manual_exit` round trips (+$338); they were RESCUES, not discretionary cuts, and should be tagged as such in the September clean-window accounting.

**Root cause, one sentence:** Windows logged an unexpected shutdown at 07:51:05 local (Kernel-Power 41 + EventLog 6008, no minidump -> hard hang/power, not a BSOD), rebooted 08:01:13 local (10:01 ET), and EVERY Gamma_* task (186/186) is registered `LogonType=Interactive`, so nothing relaunched until the user logon at 08:45:55 local (10:45 ET) -- the hidden-launcher chain's first post-crash launch is 08:46:01 local in both run-ps1-hidden and run-cmd-hidden logs.

**Why it is worse than one bad hour:** Alpaca rejects option brackets, so `exit_manager` is the ONLY stop. Machine death = naked position until a human returns. The `dead_mans_switch_open_position_on_process_death` guard covers process death on a live box, not box death.

**Instruments that stayed GREEN through it (C7):** engine-health.json GREEN 18:02 ET; monday_verify WS7 GREEN with 347/405 fires; STATUS.md had no entry for the outage; gym/pulse silent. A 55-minute hole in the 1-minute engine during RTH with positions open must be a RED line, not a footnote.

**Fixes (ordered):**
1. J-only (system settings): Windows auto sign-in after reboot (netplwiz) + BIOS "restore on AC power loss" -- turns 55 min into ~10.
2. Off-box dead-man: a $0 external worker (GitHub Actions cron / free tier) that reads a heartbeat stamp the engine pushes each tick and, if stale >5 min during RTH with open positions, flattens via Alpaca REST. Alert-only first; flatten arming is a kill-type risk REDUCTION for the 09-29 checkpoint.
3. Outage detector: engine_health.py / monday_verify count 1-minute gaps >3 min inside 09:30-15:55 ET in core-decisions.jsonl and RED them to STATUS `## Known broken` -- guard test with today's ledger as the fixture.
4. Intervention counter: a manual exit that lands within 5 min of a detected engine gap is `rescue_exit`, not `engine_entered_manual_exit` -- keeps the Sept ZERO target honest.
