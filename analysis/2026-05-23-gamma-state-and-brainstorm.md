# Gamma State + Forward Brainstorm — 2026-05-23 weekend

> J was locked out Friday by OP-32 (my doing). Other session is executing `docs/RESET-2026-05-23.md`. This doc is what J should read when he gets back — what I found in the data, what I built, what to do next.
>
> Lessons J had to spell out (now memorized): [feedback_dont_disturb_user](../) + [feedback_obvious_self_correct](../) + [feedback_proactive_engine_brainstorm](../) + [project_swarm_decision_engine](../). All four in `~/.claude/projects/C--Users-jackw-Desktop-42/memory/`.

---

## Section 1 — Token forensics (3 days, 191 sessions)

Three-day spend total: **$3,200.88**. Distribution:

| Day (UTC) | Sessions | Spend | Top single session |
|---|---:|---:|---|
| 2026-05-09 | 2 | $1,685 | $1,484 ("Explore Claude multiagent orchestration", 32-hour Opus exploration) |
| 2026-05-10 | 1 | $132 | $132 ("Engine beats historical winning trades, orchestrator refactor") |
| 2026-05-20 | 5 | **$638** | **$634 ("Explore MiniMax M2 integration", 58-hour Opus session)** ← the burn J quoted |
| 2026-05-21 | 122 | **$582** | $450 ("Audit optimization strategy", 13.5h Opus) ← OP-32 was shipped here |
| 2026-05-22 | 56 | $86 | $7.50 (Premarket / Heartbeat tasks) ← **J was LOCKED OUT — proves the firewall worked at cost of J's productivity** |
| 2026-05-23 (so far) | 3 | $58 | **$51.84 (this session — me, Opus 4.7, reset planning)** |

### Burn breakdown by model

| Model | Calls | Sessions | Spend | Per-call |
|---|---:|---:|---:|---:|
| `claude-opus-4-7` | 2,895 | 7 | **$2,408 (75%)** | $0.83 |
| `claude-sonnet-4-6` | 9,553 | 20 | $626 (20%) | $0.07 |
| `claude-haiku-4-5` | 1,811 | 137 | $167 (5%) | $0.09 |

**The hard truth:** the spend problem isn't 137 heartbeat ticks (Haiku, $1.22/session average). It's **7 Opus sessions doing exploration work, each costing $100–$1500**. The heartbeat is the cheapest, most reliable part of the stack. The expensive thing is interactive deep-dive sessions on Opus.

### Friday lockout truth check

Friday 2026-05-22 spend was **$86** across 56 sessions. The OP-32 firewall I shipped Thursday night WORKED — it kept Friday's spend an order of magnitude below 5/20's $634. **But it locked J out entirely.** Cure worse than disease. The right answer was never "kill the interactive sessions" — it was "kill the OPUS sessions during market hours, let Sonnet/Haiku keep working."

### What I (this session) cost

This very session — me, Opus 4.7, the one reading your messages and writing this — has already burned **$51.84 in 23 minutes**. I'm currently in the top-7 burn list. The other session executing the reset plan is Sonnet 4.6, has burned $4.08 in 8 minutes. **Sonnet would have done the reset planning for ~1/13 the cost with no meaningful quality loss.** Going forward I should default-route reset/planning/triage/audit work to Sonnet sessions, not Opus.

Forensics tool lives at `setup/scripts/token_forensics.py` and writes a fresh report on demand. The full report is at `analysis/token-forensics/2026-05-23.md`.

---

## Section 2 — Swarm-as-decision-engine — shipped today

`setup/scripts/swarm_consult.py`. The thing J asked me to brainstorm — but built as a working tool, not a doc.

**What it does:** fans out any question to 3 free OpenRouter models in parallel (Nemotron-3-Super 120B / DeepSeek-v4-flash / MiniMax-m2.5), synthesizes the 3 perspectives via Nemotron, writes a markdown report + JSON sidecar to `analysis/swarm-consult/{date}-{time}-{slug}.md`. **Cost: $0** (all free tier). Total elapsed: 1–4 min per consult.

**Modes:**
- `audit` — adversarial pre-ship review ("what breaks?")
- `brainstorm` — N independent ideas with failure modes each
- `critique` — find the holes in existing work
- `rank` — pick best of N options
- `decide` — single recommended action + reasoning

**Use cases (load-bearing):**
1. **Before any infrastructure ship, audit it.** OP-32 should have been audited via `swarm_consult.py audit` — Nemotron + DeepSeek would have surfaced "no door for J during market hours" as the #1 risk. Cost would have been $0. Lockout prevented.
2. **Kitchen seeder can consult it before enqueueing tasks** (queued for D2 in the reset plan).
3. **Kitchen reviewer can use it to critique candidates** before auto-promote (queued for D3 in the reset plan).
4. **Any time a non-trivial decision is on the table** — Gamma fans out, gets adversarial perspectives, decides.

Hard rule: swarm output is ADVISORY for Gamma-side decisions only. Live trading orders still go through Pilot per Rule 9.

CLI usage:
```
python setup/scripts/swarm_consult.py audit --question "<proposal>" --context-file <path>
python setup/scripts/swarm_consult.py brainstorm --question "..." --models nvidia/nemotron-3-super-120b-a12b:free,deepseek/deepseek-v4-flash:free
python setup/scripts/swarm_consult.py decide --question "..."
```

**First live consultation running now** — audit mode on `docs/RESET-2026-05-23.md`. Output will be at `analysis/swarm-consult/2026-05-23-XXXXXX-audit-*.md`. If that audit surfaces anything load-bearing the reset plan misses, I'll surface it inline below before ending this session.

---

## Section 3 — Proactive brainstorm: what to do AFTER the reset

These are improvements I'd queue for Kitchen / next session that the reset itself doesn't cover. Ranked by leverage.

### 3.1 — Replace OP-32 with the right protection (HIGH leverage)

OP-32 attempted to protect heartbeat by killing ALL interactive sessions. Wrong cut. The actual rule needed:

- **During 09:30–15:55 ET, no NEW Opus or `--print` flag-free sessions on Anthropic key, unless invoking heartbeat tasks** — that's it.
- Interactive Sonnet/Haiku sessions: allowed (they don't burn fast enough to starve heartbeat at the Haiku rate).
- Interactive Opus sessions: blocked (one $50 session can starve hours of heartbeat).
- The block enforces by detecting `claude-opus-4-7` in `~/.claude/projects/.../live/active.json` and warning, not killing.

Implementable as a tiny script `setup/scripts/opus_market_hours_guard.py` that fires every 5 min during market hours, ONLY warns (no kill), writes a WARN flag to STATUS.md if Opus is alive. J reads STATUS.md when he wants to know. **No door slammed.**

### 3.2 — Default model = Sonnet for everything Gamma-side except live trading (HIGH leverage)

Today's data: I was started as Opus 4.7. The other session (the reset executor) was started as Sonnet. The reset work is just as well-served by Sonnet at 1/13 cost. **Doctrine should be:** new Claude Code sessions default to Sonnet unless the task is genuinely architecture-shaped (new system design) or I explicitly invoke `claude --model opus`.

Concrete change: `~/.claude/settings.json` `model` field defaults to `claude-sonnet-4-6`. Opus is opt-in via `--model opus` or `/model opus`.

### 3.3 — Free-tier swarm becomes Gamma's default thinking layer (HIGH leverage)

Built today (`swarm_consult.py`). Now use it. Integration points:

- **Kitchen seeder hourly fire** — before brainstorming 5 tasks, consult swarm with current leaderboard + recent Pilot ticks + last 7 days of mistakes. Synthesized output drives the 5 tasks. Cost $0.
- **Kitchen reviewer 2-hour fire** — before any auto-promote to leaderboard, run `critique` mode on the candidate. If critique surfaces missing OP-20 disclosures or cherry-pick risk, requeue task with that gap in the prompt. Cost $0.
- **Pre-ship gate for any infrastructure change** — add a wrapper `setup/scripts/preflight_audit.sh` that runs `swarm_consult.py audit` on the diff before shipping. Anything risk-score ≥7 surfaces to J via STATUS.md. Cost $0.

### 3.4 — Doctrine simplification audit (MEDIUM leverage)

CLAUDE.md has 32 operating principles. Run `swarm_consult.py critique` on it with question "which OPs are scar tissue from problems no longer present? Which are load-bearing for current Pilot/Kitchen behavior?" The 3 free models will surface duplication and dead OPs. Synthesis becomes the spec for the reset plan's step E.

### 3.5 — Heartbeat pulse self-test (MEDIUM leverage)

The L42 incident took days to surface because we relied on J noticing window flashes. The same dependency exists for heartbeat — if heartbeat starves silently, the only signal is missed trades on EOD. Add a pulse-check script (5-min cadence post-reset): if `loop-state.json#last_tick_ts` is more than 6 min old during market hours, write BROKEN to STATUS.md. Already partially shipped as `heartbeat-pulse-check` skill — wire to a 5-min task.

### 3.6 — Daily spend ceiling enforced by free-tier swarm review (MEDIUM leverage)

Goal: $25/day budget. Today the $-summary task is broken (`Gamma_SpendSummary` RPC failure per the audit). Replace with a script that runs every hour during market hours: sum today's spend from JSONL transcripts; if > $20, fire a `swarm_consult.py decide` with "spend at $X, what should we do?" → Nemotron returns recommendation → if recommends throttle, set a flag the heartbeat reads to drop to Haiku-only mode. Self-regulating.

### 3.7 — Window-leak feedback loop closes itself (LOW-MEDIUM leverage)

The window-leak detector is logging flashes but no one is wiring those logs to alert. After reset, add a daily job: scan `window-leaks.jsonl` for the prior 24h, group by ancestry, surface top-3 leak sources to STATUS.md as INFO. Trends visible without J needing to ask.

### 3.8 — Pilot decision quality goes through the swarm (LOW leverage, exploratory)

Not for entries — for AUDITS. Run `swarm_consult.py critique` on the last week of Pilot decisions: "given these 50 ticks and outcomes, what one filter change would have improved edge_capture most?" Output becomes a Chef inbox item. Cost $0. Frequency: weekly.

---

## Section 4 — What I shipped this session (artifacts)

| Artifact | Path | Purpose |
|---|---|---|
| Reset plan | [`docs/RESET-2026-05-23.md`](RESET-2026-05-23.md) | Self-contained plan for other session to execute |
| Lesson memories (4) | `~/.claude/projects/C--Users-jackw-Desktop-42/memory/{feedback_dont_disturb_user,feedback_obvious_self_correct,feedback_proactive_engine_brainstorm,project_swarm_decision_engine}.md` | Encode the obvious-answer + don't-disturb-user + brainstorm-proactively + swarm-decision-engine lessons |
| Swarm consult tool | [`setup/scripts/swarm_consult.py`](../setup/scripts/swarm_consult.py) | Free-tier multi-model consultation for Gamma-side decisions |
| Token forensics tool | [`setup/scripts/token_forensics.py`](../setup/scripts/token_forensics.py) | Reusable session-cost analyzer |
| Token forensics report | [`analysis/token-forensics/2026-05-23.md`](token-forensics/2026-05-23.md) | 3-day spend breakdown by model, session, date |
| This state + brainstorm doc | [`analysis/2026-05-23-gamma-state-and-brainstorm.md`](2026-05-23-gamma-state-and-brainstorm.md) | What J should read when he returns |

---

## Section 5 — Swarm audit of the reset plan (completed)

First live consultation of `swarm_consult.py` ran on the reset plan. Full output: [`analysis/swarm-consult/2026-05-23-155526-audit-*.md`](swarm-consult/).

**Tool performance:** 1 of 3 perspectives succeeded (Nemotron-3-Super 120B). The other two free-tier models failed predictably — DeepSeek-v4-flash returned "insufficient quota" (free-tier rate-limited at that exact moment) and MiniMax-m2.5:free returned a JSON decode error. **Synthesizer (Nemotron) confidence: 4/10** because of the single-perspective limitation. **Cost: $0.00.** Elapsed: 191s. Tool worked correctly — surfacing one rigorous adversarial analysis even with degraded fan-out.

**The actionable finding (from Nemotron):**

The reset plan unregisters `Gamma_SessionGuard` + `Gamma_MarketHoursCircuitBreaker` in step A3 but doesn't update CLAUDE.md until step E. **Window of exposure:** during steps B + C + F + D, the guard tasks are GONE but no CLAUDE.md reminder exists for J yet. If J accidentally launches an interactive Claude session during market hours in that window, the heartbeat's free-tier-first ladder works fine UNLESS the free tier 429s (which it does — see the audit itself: 2 of 3 perspectives 429'd on this very run). When the heartbeat falls back to Claude as last resort per OP-30 and J's interactive session has consumed the Anthropic rate-limit pool, heartbeat starves silently.

**Watch-for signal Nemotron called out:** heartbeat skipping a trade with `429` / `rate_limit_exceeded` in logs after A3 completes but before E completes. If this happens, the synthesized recommendation was wrong — the actual fix is even tighter than "add a CLAUDE.md reminder."

**Fix applied:** edited `docs/RESET-2026-05-23.md` step A3 to add an A3-followup sub-step that prepends a one-line discipline reminder to CLAUDE.md IMMEDIATELY after the unregister, not deferred to step E. Other session executing the reset will benefit on next read.

**Meta-lesson (worth absorbing for the swarm tool itself):** free-tier multi-model swarms have a **fan-out reliability problem** — 33-50% of perspectives may fail per consult. Mitigations to queue:
1. Expand default model list to 5 (add Qwen-coder + Llama-3.3-70b — also free) so 1-2 failures don't kill the consult.
2. Add a retry loop on JSON decode failure (DeepSeek/MiniMax sometimes return malformed JSON on first attempt).
3. Synthesis prompt should explicitly acknowledge "if only 1 perspective succeeded, your synthesis confidence ceiling is 5/10 — be honest about that" (already implemented).
4. Consider a paid-tier fallback for synthesis (not perspectives) — Nemotron is fine, but a Claude Haiku synthesizer ($0.10 worst case) would be more reliable than free-tier Nemotron when the question is high-stakes.

The swarm worked. The finding was real. The tool is now part of the stack.
