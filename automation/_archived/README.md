# automation/_archived/

> Frozen documents superseded by current implementations. Kept for forensics and to preserve design rationale for decisions made early in the project.
>
> **Do not edit these files.** If a fix is needed in the live system, edit the live document. If a historical document is genuinely wrong, flag it in [CHANGELOG.md](../../CHANGELOG.md) but leave the archived file alone — its value is preserving what we believed at the time.

| Archived file | Superseded by | Why archived |
|---|---|---|
| [heartbeat.md](heartbeat.md) | [`automation/prompts/heartbeat.md`](../prompts/heartbeat.md) | 2026-05-04 design doc was a 15+ file read on every tick; rewrote 2026-05-06 (token-economy v3) as ~89-line lean prompt reading 5 state files. v11/v12/v14 ratifications updated all numeric values. |
| [premarket.md](premarket.md) | [`automation/prompts/premarket.md`](../prompts/premarket.md) | 2026-05-04 high-level outline; live prompt has 7 numbered steps + sub-steps for trendlines/levels/macro/dark-pool. Original missed the catalyst layer (2026-05-07), trendline awareness (2026-05-08), and key-levels v3 schema (2026-05-08). |
| [eod.md](eod.md) | [`automation/prompts/eod-flatten.md`](../prompts/eod-flatten.md) + [`automation/prompts/eod-summary.md`](../prompts/eod-summary.md) + [`automation/prompts/daily-review.md`](../prompts/daily-review.md) + [`automation/prompts/weekly-review.md`](../prompts/weekly-review.md) | 2026-05-04 spec described one 16:30 task; live system splits into 4 distinct prompts at 15:55 / 16:00 / 16:30 / Sunday-18:00. Original missed the 2026-05-07 catalyst & liquidity additions, daily backtest sync, hypothesis grading, and counterfactual exit P&L. |
| [webhooks.md](webhooks.md) | None — deferred indefinitely | Tier 2 webhook acceleration was never built. Polling cadence (HOT/BASE/COOL) made it cost-ineffective. Reconsider only after live deployment passes the 4-of-4 threshold AND J observes morning-entry latency is still problematic. |
| [cron.md](cron.md) | [`automation/morning-kickoff.md`](../morning-kickoff.md) + `setup/install-tasks.ps1` | Linux/macOS crontab design from 2026-05-04. Live system runs on Windows Task Scheduler (deployed 2026-05-05). Six tasks registered with WakeToRun, StartWhenAvailable, ExecutionTimeLimit per-task. |

## When to read an archived file

- **Forensic debugging.** "Why did we choose -50% premium stop in v1?" → read archived `heartbeat.md` original section.
- **Onboarding context.** Reading the original design helps understand the *direction* of the project's evolution, not just the current state.
- **Reverting a regret.** If a recent change turns out worse than an earlier design, the archive is the source for the prior approach.

## When NOT to read an archived file

- **Implementing today's behavior.** Live code follows live prompts. Numeric values follow [`params.json`](../state/params.json). The archived files are wrong about today's rules by construction (e.g., -50% premium stop in archived heartbeat is the OLD value; v14 is -8%).
- **Quoting in J-facing communication.** Always quote live files. Archived files are for project memory.
