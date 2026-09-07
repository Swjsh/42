# Lesson inbox: subagents abandon in-flight background runs and end their turn "waiting"

**Date:** 2026-09-07 (Sunday), microstructure/SIP-tape research session (Fable orchestrating, Sonnet workers)

**Symptom:** Three separate Sonnet research agents (H3 latency, edge-capture tape, J-real replay) each launched a 15–50 minute Python run in the background, then ENDED THEIR TURN with "I'll wait for the completion notification." No notification ever reaches a finished subagent. Twice the run was lost or had to be relaunched by the orchestrator; once the orchestrator's `TaskStop` on the idle agent appears to have killed the child process (43 windows fetched, then dead). Each idle agent also re-woke 3–4 times reporting "still waiting", burning ~10k tokens per wake for nothing.

**Root cause (one sentence):** a subagent has no durable wait primitive — once it ends its turn, its background children are orphaned or reaped and nothing wakes it — so "launch in background then wait" is structurally impossible inside a worker agent.

**Confounders that cost time:** (1) the first H3 traceback was a CAUGHT per-trade failure being logged, misread as fatal → orchestrator launched a duplicate → two runs raced the same cache files (WinError 32 on `.tmp` replace); (2) empty log files from Python stdout buffering made "dead" and "slow" indistinguishable until `-u` was used.

**Fix (rule for orchestrators):** long-running compute is launched and watched by the ORCHESTRATOR, never by a worker: worker builds + smoke-tests the script synchronously (bounded run, e.g. 2 days), returns; orchestrator runs `nohup python -u … > log 2>&1 &` itself and polls with a `run_in_background` shell loop on the output file. If a worker must run something long, it runs it in the FOREGROUND under a Bash timeout (≤10 min) — never `&`. Always `-u` for observable logs. Never `TaskStop` an agent that may own a live child you still want.

**Guard candidate:** add the rule to `~/.claude/CLAUDE.md` §1 (model routing) and to the agent prompt template used by research fan-outs.
