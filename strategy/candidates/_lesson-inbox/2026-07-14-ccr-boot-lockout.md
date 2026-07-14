# Lesson candidate: a shared automation gateway silently captured J's interactive tools, locking him out for a full workday

**Date:** 2026-07-14
**Fire:** direct J directive (interactive session), root-caused + fixed same session
**Class:** NEW candidate — "shared-gateway-under-interactive-tools = lockout risk" (adjacent to C7
silent-success-is-failure and C11 broker-is-source-of-truth, but distinct: those guard verifying
your OWN state; this is about a dependency an OPTIONAL automation convenience must never be allowed
to impose on a REQUIRED interactive surface). Also touches OP-25's own fail-open mandate ("no
automated process may kill or block J's interactive Claude session" — the 2026-05-22 OP-32 scar)
which this incident violated in a new shape: not a hard lockout, a silent-degradation one.

## Symptom
J's Claude Desktop app was silently served local Ollama instead of real Claude after a Monday PC
restart. No error, no crash, no refused connection — the Desktop app just worked with a much
weaker model and J didn't immediately realize why responses felt wrong. He was at work, couldn't
debug it, and lost a full workday of usable Claude access.

## Root cause
On 2026-07-08 the "brain sovereignty" initiative wired `claude-code-router` (CCR) under "every
claude fire" by writing `apiKeyHelper` + an `env` block (`ANTHROPIC_BASE_URL` /
`ANTHROPIC_API_BASE_URL` / `CLAUDE_AGENT_API_BASE_URL` → `http://127.0.0.1:3456`) into
**`~/.claude/settings.json`** — the GLOBAL, user-level settings file every `claude` entrypoint reads
by default, with no per-project override. That one file is shared by TWO fundamentally different
consumer classes that were never distinguished:
1. **Automation lanes** (conductor, overnight grinder, kitchen) — for whom routing through cheap/
   local models is a legitimate cost-saving design (BRAIN-SOVEREIGNTY.md Tier 2/1).
2. **J's interactive surfaces** (Desktop app, bare terminal `claude`) — for whom ANY dependency on
   a local Node.js gateway process being not just "alive" but *correctly configured* is an
   unacceptable single point of failure, because these are the tools J needs to work at all.

Separately, CCR's own static fallback router (`~/.claude-code-router/config.json` `Router.default`)
was configured with `"ollama,qwen3.6:35b"` and **zero Anthropic provider entry** — so on any cold
boot where CCR's fuller gateway/profile stack (a second sub-process, `@the-next-ai/ai-gateway` on
port 3457) wasn't yet live, the main router (port 3456) still accepted connections and silently
resolved default-routed traffic — including J's — to local Ollama. This is the C7-class trap in a
new shape: the existing keepalive's health check (`ccr-keepalive.json`) only TCP-probes port 3456
("is something listening") — it cannot distinguish "listening and serving real Claude" from
"listening and serving Ollama." Both look identical to a bare socket connect. The keepalive reported
`port_up: true, consecutive_failures: 0` the entire time J was locked out.

**Confirmed live, not just theorized (2026-07-14):** after fixing this, killing CCR and restarting
it via the exact command the keepalive uses caused CCR's OWN `start` sequence to **re-inject the
identical `apiKeyHelper`/`env` hijack back into `~/.claude/settings.json`** — proving this isn't a
rare misconfiguration, it is CCR's normal, repeatable restart behavior. Every future CCR restart
(which happens automatically and often, per its own history of dying overnight) would have
re-created Monday's exact lockout condition were it not for the new guard.

## Fix (shipped this session)
1. **Structural separation, not a one-time patch.** Removed `apiKeyHelper` + `env` entirely from
   `~/.claude/settings.json` — J's Desktop app and bare `claude` CLI now hit `api.anthropic.com`
   directly, unconditionally, regardless of CCR's state. Backup at
   `~/.claude/settings.json.pre-ccr-fix-2026-07-14.bak`.
2. **Audited every automation consumer before touching the global default** (`setup/scripts/
   run-conductor.ps1`, `run-overnight-grinder.ps1`, `kitchen_daemon.py`, `manager_overseer.py`, and
   everything else in the repo that shells out to `claude`) — none currently sets a per-fire CCR
   override; all either avoid the LLM/claude path for safety-critical work, call models directly
   via REST bypassing `claude-code`+CCR entirely (kitchen → `model-roster.json` → Ollama :11434
   direct), or explicitly request real Anthropic models (`--model sonnet`) intending Max-subscription
   billing. So removing the global default broke nothing live — and incidentally fixed a SEPARATE
   silent bug where conductor/overnight-grinder would have silently executed on Ollama instead of
   the Sonnet their own cost logs claimed, any time CCR's fallback triggered.
3. **Self-healing guard, not a one-shot fix.** `setup/scripts/ccr_keepalive.py` gained
   `_check_and_fix_interactive_settings()`, called every 5-minute fire independent of the TCP probe:
   re-scans `~/.claude/settings.json` for the router-pointing keys, auto-strips them, writes a
   same-day forensic backup, and pings J via the Discord outbox. Verified live: the fire 5 minutes
   after the CCR-triggered re-hijack caught it, fixed it, and pinged — fully unattended.
4. New guard suite `backtest/tests/test_ccr_interactive_isolation.py` (14/14): RED-proofed detector
   against synthetic fixtures, a live acceptance check against the real `~/.claude/settings.json`,
   and a repo-wide scan asserting the CCR port string appears ONLY in an explicit allowlist of
   automation/narrative files — a future PR that reintroduces a global pointer anywhere else fails
   the suite.

## Generalizable rule
**Any shared gateway, proxy, or router that automation opts into must be wired at the automation's
OWN launch point (per-fire env vars, `CLAUDE_CONFIG_DIR` override, etc.), NEVER at a global/user-level
default that interactive tools also inherit.** If a global default is the only mechanism available,
the correct target for that default is "what J's interactive tools need" (direct, always-on,
zero extra dependencies) — automation lanes should have to opt IN to the exotic path, not opt OUT of
it. Corollary: a liveness probe that only checks "is the process listening" is not equivalent to "is
the process correct" — for anything that silently changes BEHAVIOR (not just uptime) on
misconfiguration, the guard must assert the actual consumer-facing contract (here: which model gets
served), not a proxy for it (here: is a socket open). And: when a keepalive's OWN restart action can
itself re-introduce the exact fault it exists to prevent, the guard must check AFTER every restart,
not just before — self-healing has to close the loop it participates in creating.
