---
name: pulse
description: One-screen Gamma autonomy pulse — shows scheduled tasks state, live grinder, validator trend, drift health, persona files, background Claude agents, and latest digest. Use when you want to confirm "is everything running" in 10 seconds.
allowed-tools: Bash
---

# Gamma Pulse

Run the comprehensive one-screen autonomy check:

!`powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\jackw\Desktop\42\setup\scripts\gamma-pulse.ps1"`

The output above is the live snapshot of:
1. **Scheduled tasks** — which are firing, when, with what result
2. **Live grinder** — PID + iteration count + last write
3. **Validators** — last 6 cron-fired runs, PASS/FAIL trend
4. **Drift health** — foot-gun catch rate, parity drift, alerts
5. **Task audit** — registry-vs-reality match
6. **Personas** — Coach + Chef file presence
7. **Background agents** — anything visible in `claude agents`
8. **Daily digest** — today's auto-generated summary
9. **Quick commands** — copy-paste reference

If anything looks wrong, the next action is in the relevant section above.
