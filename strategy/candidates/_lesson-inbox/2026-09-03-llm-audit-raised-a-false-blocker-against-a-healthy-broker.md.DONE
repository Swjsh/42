# Lesson candidate: an LLM-run safety audit that can raise a false BLOCKER is worse than no audit

**Class:** C7 (audit outputs, not exit codes) + C14 (dead/mis-wired instrument) + "deterministic > LLM on hot paths".

**Observed (2026-09-03 00:03 ET):** `Gamma_McpDailyAudit` (LLM prompt `automation/prompts/mcp-weekly-audit.md`) wrote
`MCP_AUDIT_RED: Alpaca Safe and Bold both 401 Unauthorized ... BLOCKER: Live trading requires valid Alpaca auth` into
STATUS.md `## Known broken`. The same morning (07:48 ET) it had written `MCP_AUDIT_YELLOW ... 404 (credential/account
mismatch possible)`. A direct REST `GET /v2/account` with the `.mcp.json` keys at 01:20 ET returned 200 for BOTH accounts
(PA3POKNV46VG $5,653.87 ACTIVE; PA3WEBXJU67N $5,593.52 ACTIVE), and the live engine had traded all day on those keys.

**Root cause (one sentence):** the audit probes the broker THROUGH the MCP server inside an LLM session (a process whose
environment, session and cold-start state are all different from the engine's REST path), then narrates whatever it saw
as a verdict about the broker — so a stale MCP session reads as "credentials rejected" with a BLOCKER label, and nothing
cross-checks it against the path that actually trades.

**Compounding factor:** the audit was being re-fired every 5 minutes by the phantom-hold catch-up storm (sibling lesson
`2026-09-03-tests-planted-phantom-holds-in-a-production-log.md`), so a $0.10 LLM probe ran ~12×/hour and stacked four
contradictory verdict lines in the section (06:23 YELLOW, 06:27 YELLOW, 07:48 YELLOW, 23:50 "all healthy" YELLOW, 00:03 RED).

**Fixed:** verdict line cleared via the new `status_known_broken.upsert` (commit `9b3e8825`); a $0 deterministic REST probe
(`setup/scripts/mcp_daily_audit.py`, RED only on two consecutive auth failures 30 s apart, GREEN clears the marker) replaces
the LLM fire — in build the same night.

**Generalisation worth a rule:** a monitor whose RED can block trading must probe the SAME path the engine uses (REST +
`.mcp.json` keys), be deterministic, require two consecutive failures before RED, and self-clear on GREEN. An LLM may
summarise a probe's output; it must never BE the probe.
