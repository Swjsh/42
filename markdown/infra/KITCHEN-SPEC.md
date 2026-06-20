# The Kitchen — full spec (archived from CLAUDE.md OP-31)

> Moved out of CLAUDE.md on 2026-06-17 (Tier 0 lean pass). Verbatim.
> The load-bearing contract + guardrails remain summarized in CLAUDE.md OP-31; this is the full detail.
> Scheduled-task registry: [`automation/state/SCHEDULED-TASKS.md`](../automation/state/SCHEDULED-TASKS.md).

31. **The Kitchen -- 24/7 autonomous free-tier R&D loop (ratified 2026-05-21 by J).** J directive verbatim: *"I need twenty four seven free model cooking ... we need to figure out what makes money, how the engine can utilize it to make money ... Claude is the driver ... I am not any part of this at all. It is pure autonomy."*

    **The system (three coupled scheduled tasks):**

    | Task | Cadence | Role |
    |---|---|---|
    | `Gamma_KitchenDaemonKeepalive` | every 5 min, 24/7 | Restarts `kitchen_daemon.py` if dead. Daemon is a long-running pythonw that polls `cook-queue.jsonl`, picks pending tasks by priority+age, runs each through the OpenRouter free-tier ladder, writes DRAFT candidates to `strategy/candidates/`. PID at `automation/state/kitchen-daemon.pid`. |
    | `Gamma_KitchenSeeder` | hourly @ :20 ET, 24/7 | Reads leaderboard + lessons + journal + mistakes.md + recent decisions.jsonl, asks Nemotron to brainstorm 5 fresh cook tasks, enqueues them. Skipped if pending backlog >= 25. Filters forbidden-surface task descriptions. |
    | `Gamma_KitchenReviewer` | every 2h @ :45 ET, 24/7 | Triages recent cook outputs into PROMOTE / VALIDATE / DUPLICATE / LOW_QUALITY. Queues specific follow-up cook tasks. Writes digest to `analysis/kitchen-review/{date-time}-review.md` + `strategy/candidates/_review-log.jsonl`. |

    **Files:**
    - `setup/scripts/kitchen_daemon.py` -- the cook worker
    - `setup/scripts/kitchen_seeder.py` -- the task generator
    - `setup/scripts/kitchen_reviewer.py` -- the output triager
    - `setup/scripts/run-kitchen-{daemon-keepalive,seeder,reviewer}.ps1` -- wrappers
    - `setup/install-kitchen.ps1` -- one-shot installer
    - `automation/state/cook-queue.jsonl` -- append-only event log (create / claim / complete / fail / requeue)
    - `automation/state/kitchen-status.json` -- snapshot of current state (read this when you wake)
    - `strategy/candidates/_chef-log.jsonl` -- per-cook telemetry
    - `strategy/candidates/_review-log.jsonl` -- per-review-decision log

    **CLAUDE-WHEN-AWAKE PROTOCOL (the "Claude is the driver" contract):**

    Whenever Claude wakes up (interactive session OR scheduled wake fire), the FIRST thing to do related to R&D is read kitchen status and steer:

    1. **Read** `automation/state/kitchen-status.json` -- shows daemon liveness, queue depth, current task, recent completions, today's cost.
    2. **Read** recent `analysis/kitchen-review/*-review.md` for the latest reviewer triage.
    3. **Read** the last 10 entries in `strategy/candidates/_chef-log.jsonl` to see what cooks ran.
    4. **Steer** by enqueueing high-value tasks Claude has uniquely positioned to design (architecture-shaped questions, anchor-day deep dives, cross-cutting refactors of the watcher fleet) via:
       ```
       python setup/scripts/kitchen_daemon.py enqueue --task "<imperative>" --priority high --source claude
       ```
    5. **Promote** -- when a cook output is genuinely PROMOTE-worthy per reviewer triage, Claude appends a row to `strategy/candidates/_LEADERBOARD.md` (Claude is the only writer to the leaderboard markdown -- daemon and reviewer only WRITE to candidates dir + review log).
    6. **Prune** -- if pending backlog has stale tasks (`source=manual-seed` > 48h, priority=low, not picked yet), Claude may emit a `requeue` event with reason=archived to clear them (rare).

    **HARD GUARDRAILS (enforced in code, not just convention):**
    - Daemon NEVER modifies `automation/prompts/heartbeat*.md`, `automation/state/params*.json`, `CLAUDE.md` -- Rule 9.
    - Daemon NEVER places orders (no MCP available; CHEF_SYSTEM_PROMPT explicitly forbids).
    - Seeder filters task descriptions for forbidden patterns (heartbeat.md, params*.json, "place order", etc.) before enqueueing.
    - Paid tier (MiniMax M2.5 paid) has a daily cap of **$3/day** enforced in `kitchen_daemon._today_paid_spend()`. Once breached, the daemon refuses tier-3 calls for the rest of the day; only free tiers run.
    - All three tasks are read-mostly on production state. Writes are confined to `strategy/candidates/` + `analysis/kitchen-review/` + `automation/state/{cook-queue.jsonl,kitchen-status.json,kitchen-daemon.pid}` + JSONL logs.

    **Cost discipline:**
    - **Primary path:** Nemotron 3 Super 120B-MoE / 12B active, $0.
    - **Fallback chain:** DeepSeek V4 Flash :free -> MiniMax M2.5 :free -> MiniMax M2.5 paid ($0.003-$0.006/call).
    - Daily throughput target: ~50-100 cooks/day at near-$0. Hard cap on paid burn: $3/day.

    **Anti-patterns this OP forbids:**
    - Running interactive Claude sessions to "cook strategies" instead of enqueueing to the Kitchen.
    - Bypassing the model ladder by hard-coding paid MiniMax in new cook scripts.
    - Writing to `_LEADERBOARD.md` from the daemon/seeder/reviewer (only Claude curates it per the protocol above).
    - Adding fourth scheduled task without registry entry in `automation/state/SCHEDULED-TASKS.md` (audit script catches this).
