# THE FABLE HANDOFF — judgment transplant for every model that comes after

> Written by Claude Fable 5, 2026-07-02 evening, at J's direction, with limited usage remaining.
> Purpose: everything irreplaceable from the 2026-06-30 → 07-02 sessions, installed as standing doctrine
> so a Sonnet-driven Gamma (conductor, agents, evening sessions) executes at Fable quality.
> This document is LOAD-BEARING. Read it at the start of any substantive Gamma session.

---

## 1. THE DIAGNOSTIC TOOLKIT (how to think, not what to do)

**T1 — Motion vs Function.** A green check that measures *activity* (file fresh, process ticking, exit 0, order "placed") proves nothing. Only *function* counts: an order that FILLS, an entry that's REACHABLE, a signal that's CONSUMED. Before saying "works/solid/ready": quote the end-to-end evidence from THIS run. The fill funnel is the canonical instrument; extend it, never bypass it.

**T2 — Burden of proof is on the GATE, not the trade.** (J's law, 2026-07-02.) Every rule/gate/lock/veto between signal and order must carry: provenance (J-ratified with citation, or Claude-invented), evidence (a real A/B scorecard, or nothing), and ledger impact (what it blocked, counted). Claude-invented + no evidence + blocks trades = kill or A/B it. The re-entry lock died this way after costing a day's best trade. When J calls out a missed trade, investigate the gate first.

**T3 — Null controls or it didn't happen.** Every positive result must beat (a) random-entry null with the same exit shape, and (b) the opposite-direction null on the same entries. The opposite-direction null is the regime detector: when it EARNS, your signal is a coin whose era ended (this killed the E2-context port). Pre-register designs (commit DESIGN.md BEFORE grinding), split train/test BEFORE ranking, evaluate the test set ONCE, BH-FDR across whatever you compared. Burned holdouts stay burned.

**T4 — Hunt the stale clock.** This rig's recurring bug family: time handled wrong. Wall-clock vs bar-time (the 09:30 stale-signal escape), tz-aware vs naive (Bold's crash), fixed offsets stored year-round (the CSV winter clip), local-Mountain vs ET (never Bash TZ; use et_clock). Any datetime comparison in new code needs a guard test with both aware/naive and both sessions' bars.

**T5 — Dead-knob audit (C14, generalized).** A config value proves nothing until varied-and-asserted: change it, watch behavior change. The engine silently ignored dozens of ratified keys for a week. The params↔consumer reconciliation ratchet now guards this — keep it green, extend it to every new key.

**T6 — Same-day fixes.** What's seen during RTH gets diagnosed during RTH (read-only), staged as a git-apply-checked patch + skip-until-applied guards, applied at 16:00, live before the next open. The staging pattern is in markdown/audits/ENTRY-FLOOR-FIX-PLAN / TZ-QUALITY-LOCK-FIX-PLAN — copy it.

**T7 — The kill is a product.** An honest negative (with the specific nail named: slippage / concentration / OOS-flip / regime-null) prevents future waste and often reveals the real vein (RRW died as an entry → lives as a veto candidate). Never soften a kill; never re-run a killed hypothesis without a genuinely new feature.

**T8 — J's reads are seed corpus.** When J calls a live setup ("wicked into the ribbon at 10:30"), capture the exact timestamps + mechanics, build the detector to fire on HIS bars first (anchor test, ≤5 fires/day = tight), then battery it. His direction-sense is real (59.2%, null-controlled); the machine's job is expressing it with mechanical hands.

## 2. MODEL ECONOMY (J is quota-limited — this is doctrine)

- **Subagents/workflows default to `model: "sonnet"`** (or haiku for mechanical work). NEVER spawn on the session's own model by default — inheritance burned J's Fable quota 2026-07-02.
- Conductor + gamma-drive route to **sonnet** (queue-drain and fix-and-guard work; reserve opus-class for frame audits and architecture only, and only after-hours with J's awareness).
- Research stays FREE-tier (OpenRouter/groq/cerebras/ollama). Compute-heavy work goes in ONE long pure-Python process (venv is reaper-exempt), not many agent round-trips.
- Big-model sessions (when available): spend on JUDGMENT — audits, designs, adjudications, this document's maintenance — never on mechanical execution a spec can carry.

## 3. STATE OF THE WORLD (as of 2026-07-02 ~17:30 ET)

- **The machine trades.** First full honest session 07-02: 16 fills, 16 managed exits, 0 open at EOD, all-accounts net +$240.59. Bold's +$290 leg-2 put was J's own midday call, traded.
- **Armed on Safe paper:** core BEAR/BULL ribbon + vwap_continuation (validated −8%/+30% exit) + vwap_reclaim_failed_break + vix_regime_dayside + double_bottom_base_quiet + bollinger_squeeze (newest, strongest scorecard). Bold: core only. Fleet: ribbon_ride + vwap_continuation, 4 arms.
- **Fixed & guarded this week:** marketable placement, entry ceiling 15:00, entry floor + stale-trigger freshness (staged→applied 07-02 eve), Bold tz crash, ribbon-flip-back exit (core+fleet), GATE_KEYS vix bands, kitchen stage5 poison pill, watcher_grader, honest EOD/funnel/loop-state, promoter contract, OosCheck schedule, dress rehearsal nightly.
- **Killed honestly (do not resurrect without NEW features):** re-entry lock (J order), stage5 shotgun (spread), RRW-as-entry (premium bleed), J-fingerprint E1/E6 (doesn't port), Phase-B exit-family port (chandelier scratches engine entries), futures seed-pile Phase 1 (regime sign-flip), 12%-WR contender (BLOCKED-FINAL), ~64 prior families (see STRATEGY-BACKLOG).
- **Gates:** recency RED = capital frozen (paper trade-to-learn continues, correct). Live money / secrets / irreversible-external = J-only, always.
- **Open J-owed items:** tastytrade PROD token rotation (since 06-22); overnight/weekend futures appetite; SwarmPremarket paid-pin decision.

## 4. THE ROADMAP — execution-ready specs (Sonnet-Gamma runs these; queue.md carries the live copies)

> **2026-08-18 note:** this section is a frozen 2026-07-02 execution-queue snapshot, kept
> verbatim below for provenance — it is NOT the current destination/milestone roadmap despite
> the header. **The current canonical roadmap (destination, gates, RATIFIED/PROPOSED/OPEN
> status) lives at [`markdown/planning/ROADMAP.md`](../planning/ROADMAP.md).** Most items below
> are 47+ days old and should be assumed done/superseded until re-verified against `queue.md`
> or `git log` — do not treat this list as live work.

Priority order; each is one evening-session or conductor-fire sized; every one ships with guard + revert + REVOKE line:

1. **RISKY-ARM GATE TIERS** — implement per-arm gate-strictness from the GATE-PROVENANCE-AUDIT-2026-07-02 design (agent report + markdown/audits/): SAFE=full stack, RISKY=minimum viable (NEVER relax: kill-switch, PDT, flat-verify, entry floor/ceiling, risk caps). Risky arms take the one-gate-away trades; measure per-arm funnels ≥5 days before judging.
2. **COOLDOWN A/B VERDICT** — read analysis/recommendations/reentry-cooldown-ab.json (produced 07-02 eve); ship per its verdict ONLY (T2: no gate without evidence). Addresses the vwap 6-churn/−$196 pathology.
3. **RRW FULL-ANGLE** — (a) veto/exit overlay on bull path (its signal is real, p<0.05); (b) entry under RISKY-profile management; (c) fleet-arm candidate. Battery + nulls each; kill or ship per numbers.
4. **FDR-16 CONFIRM** — top-2 non-redundant groups through lib.simulator_real, canonical battery; expand only if one clears.
5. **BOLLINGER→MES SWING PORT** — the one current-regime candidate for futures Phase 1 retry; flat-by-Friday default; futures Phase 2/3 stay locked until something validates.
6. **SINGLE STRATEGY REGISTRY (M1 first)** — per markdown/specs/STRATEGY-REGISTRY-DESIGN.md; M1 = reconciliation guard, zero behavior change.
7. **EXTRA-EXEC QUALITY VISIBILITY** — the quality-lock deletion (07-02) removed suppression; ensure the funnel + digest surface per-setup churn/expectancy daily so gate decisions stay evidence-fed.
8. **PREMARKET-OPEN LEVEL (INTRADAY_PMO)** — one-liner spec in analysis/recommendations/ribbon-rejection-wick.json; add + guard.

## 5. OPERATING CONTRACT WITH J (hard-learned, non-negotiable)

- **Answer in the MAIN chat, plain text FIRST, tools second.** Never end a turn with only scheduler/tool noise. He asked four times on 07-02; never again.
- Milestones also ping Discord (gamma-ops outbox) — but chat is primary when he's present.
- Lead with the number/verdict; red numbers reported as plainly as green; corrections volunteered before he finds them.
- OP-0/OP-33 stand: act without asking on sanctioned+reversible+paper; verify before claiming; the four J-only categories never move.
- He cannot narrate the whole system to you. Think like the owner: when something is dumb, suspect it's Claude-invented and audit it (T2). "Gamma will fix it" — the machine does the work; J holds the off-switch.

## 6. AFTER FABLE

Fable's edge was never a bigger hammer — it was refusing to trust green paint. Everything above is that refusal, written down. Keep the guards green, keep the instruments honest, keep the burden of proof on the gates, spend big-model tokens on judgment and cheap-model tokens on execution, and Gamma keeps compounding without me. The equity curve is the only reviewer that matters.
