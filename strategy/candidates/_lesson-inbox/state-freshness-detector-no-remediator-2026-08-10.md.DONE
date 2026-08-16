---
filed: 2026-08-10
filed_by: conductor (AFTERHOURS fire, ~21:42-22:00 ET)
kind: lesson
status: pending
---

# `state_freshness_audit.py` correctly detects silent producer death but nothing auto-remediates it — 5 producers sat stale for weeks with zero self-heal

## Symptom

`engine-health.json` flagged `state_freshness` RED at fire start: 7/21 live-path state
files STALE. Drilling into the actual internal content stamps (not file mtime, which was
misleadingly recent because a PRIOR fire's `git rm --cached` untrack-fix touched mtime
without touching content): `context-bundle.json` frozen at `2026-07-15`, `confluence-
zones.json` at `2026-07-14`, `trade-today.json`/`ema-snapshot.json`/`news.json` similarly
weeks stale, `premarket-readiness.json` at `2026-07-27`.

## Root cause

Two independent facts, both verified live this fire:

1. **The scheduled tasks fired all day, every day, with `LastTaskResult=0`.**
   `Gamma_ContextBundle` and `Gamma_Confluence` both show clean 5-10min-cadence firings
   in `run-cmd-hidden-<date>.log` for 2026-08-10 (and, by the staleness gap, every day
   since 07-14/07-15) with no captured non-zero exit (`self_check.py`'s own
   `check_run_cmd_hidden_masked_exit` — which specifically hunts non-zero exits — found
   NOTHING wrong with these two).
2. **Manually re-running the exact same producer scripts, via the exact same invocation
   chain (`wscript -> vbs -> system-pythonw -> run_cmd_hidden.py -> venv-pythonw
   <producer>.py`), works instantly and writes fresh content within seconds.** All 5
   stale producers (`context_bundle_producer.py`, `confluence_producer.py`,
   `trade_today_watcher.py`, `premarket_readiness.py`, `macro_calendar.py`,
   `automation/scripts/compute_ema_snapshot.py`) were re-run this fire and immediately
   cleared `state_freshness` from 7/21 stale to 1/21 (the 1 remaining —
   `futures/data-freshness.json` — is a DIFFERENT, already-fixed-in-code issue from
   tonight's earlier 18:45 fire that just hasn't had a live tick since the fix landed;
   expected-quiet until tomorrow's RTH).

**The precise mechanism for WHY the scheduled fires silently no-op'd (exit 0, zero
content change) was investigated but NOT conclusively root-caused this fire** — a
tangential finding surfaced along the way: `automation/overnight/queue.md` and
`STATUS-archive-2026-08.md` both reference an `exit=0 (off-desktop)` annotation from a
PAST VBS-WRAPPER-EXIT-CODE-BLIND-SPOT investigation, but the CURRENT
`setup/scripts/run_cmd_hidden.py` (byte-identical to its HEAD commit `306e5075`,
2026-07-14, confirmed via `git diff HEAD`) contains NO such annotation logic anywhere in
its source OR its `git log -S` history — meaning whatever wrote that string in past logs
either came from a since-reverted/never-committed local edit, or a mechanism this fire
did not find. All 9 checked scheduled tasks (`Gamma_ContextBundle`, `Gamma_Confluence`,
`Gamma_HeartbeatCore`, `Gamma_CryptoTwin`, `Gamma_LedgerArchive`, etc.) share the IDENTICAL
`Principal.LogonType=Interactive` / `UserId=jackw` — ruling out a logon-type
differentiator between "works fine off-desktop" and "silently no-ops" tasks. **This
specific mechanism (why an off-desktop/locked-session firing of these particular
producers apparently completes with exit 0 but never reaches the file-write) is flagged
for a dedicated future fire, not chased further here** (rail-3 bounded; the immediate
remediation did not require knowing the mechanism).

## Generalizable rule

**A detector without an automatic remediator re-violates on its own schedule (L252's own
rule, now proven true for a SECOND detector).** `state_freshness_audit.py` was purpose-built
2026-07-30 specifically to catch this exact failure shape ("a data PRODUCER stopped
writing while every CONSUMER carried on happily") — and it worked, correctly flagging RED
every time `engine_health.py` ran. But nothing ever re-invoked the flagged producer
automatically; the file could only get fresh again when a human/conductor fire happened
to notice the RED and manually re-ran the script, which is exactly why 5 producers sat
stale for 3-4 weeks (07-14/07-15 through 08-10) despite the monitor firing correctly
the entire time.

## Suggested next step (bounded, Sonnet-appropriate)

Build `setup/scripts/state_freshness_remediate.py`: read `state_freshness_audit.audit()`'s
`entries`, and for every entry whose ONLY problem is "STALE BY SESSION" (not MISSING, not
UNKNOWN — those need a human), look up its `writer` field and re-invoke that producer
script directly (mirrors `auto_commit_candidates.py`'s remediator pattern from L252).
Wire it into a cheap, frequent cadence (e.g. piggyback on the existing self-check 30-min
cadence, or a new lightweight scheduled task) so a stale producer self-heals within
minutes of being detected instead of waiting for a human to notice weeks later. Guard:
vary-and-assert — a genuinely-stale file gets remediated (mock the writer, confirm it's
invoked), a genuinely-missing file does NOT get remediated (that needs a human/deeper
fix, not a silent auto-write of a placeholder).

## Suggested L# slot

Fold into C7 (Silent success is failure — audit outputs, not exit codes) alongside L252
directly — this is the SAME "detector without a remediator re-violates" pattern, just a
second detector (`state_freshness_audit.py`, not `auto_commit_candidates.py`'s tracked-file
class) hitting it independently. Cross-reference C34 (git ops reverting live state) since
the misleadingly-recent file mtimes (from a PRIOR fire's `git rm --cached`) were the red
herring that made this look, at first glance, like ANOTHER git-reversion incident before
the internal content stamps proved otherwise.
