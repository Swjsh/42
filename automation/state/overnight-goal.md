# OVERNIGHT GOAL — improve the system per the Fable gap-audit (J: "work all night, don't stop")

**Started:** 2026-07-07 ~23:00 ET (Opus, J directive). **Source of truth:**
`markdown/audits/FABLE-GAP-AUDIT-2026-07-07.md` + `markdown/audits/FABLE-DECISIONS-2026-07-07.md`.
This file is the DURABLE state: each loop wake reads it, does the top todo item, updates it. Survives compaction.

## OPERATING RULES (obey EVERY iteration — read before touching anything)
1. **Check `et_clock` first.** MARKET HOURS (09:30–15:55 ET, Mon–Fri): READ-ONLY only — research/analysis/docs, NO live-engine edits, NO heavy grinds (the heartbeat shares the Max pool). AFTER-HOURS/weekend: full build allowed.
2. Pick the TOP `[ ]` item. Read its gap-audit spec + any flagged **TRAP** BEFORE editing. Re-verify the pointer (this repo's disease is inherited claims).
3. Every code change ships with a **red-proofed guard** (revert change → guard RED → restore) + a **path-scoped commit**. The pre-commit curated safety gate MUST pass. If it RED-blocks: **REVERT the change, mark the item `[B]` BLOCKED with the reason — never force past a red gate.**
4. **Live-path / entry-blast-radius items (G4, G11):** A/B or replay-validate BEFORE shipping. If not cleanly validated → mark `[B]` BLOCKED-NEEDS-REVIEW (don't ship tired/unsupervised).
5. **Never** do the OP-0 J-first four: arm live money, rotate/expose a secret, irreversible-external, or a genuine no-default fork. Those are `[B-J]` — flag the exact ask, move on.
6. After each item: update its checkbox + a one-line result here; append a one-line note to `STATUS.md` on any commit.
7. **STOP** the loop when: all items `[x]`/`[B]`, OR the safety gate red-blocks twice in a row (halt + flag `## HALTED`), OR market opens and only live-path items remain (go read-only / idle-tick).

## QUEUE (ordered; `[ ]`todo `[~]`wip `[x]`done `[B]`blocked)
- [x] G1 adopted-position CAP-ONLY (commit 55fd164) + 3-test red-proofed guard
- [x] G2 production-interpreter import verified (system-python + venv PYTHONPATH; pandas 2.3.3)
- [x] G3 runner close-out + corrected EOD +$489 (commit fc8ee27)
- [x] G16 et_clock health — added runnable CLI (`python et_clock.py` -> ET + `market_hours` bool) + canonical `is_market_hours()` gate (Mon-Fri 09:30<=ET<15:55). Root: it was a pure library w/ no `__main__` (empty output = by-design, not a bug). 2 red-proofed guards; safety gate PASS. (commit 54ce9b6)
- [x] G7 armability gate — `backtest/lib/armability.py` primitive + `pipeline_promoter` emits an `armability` disclosure per promoted cell (per-acct budget + break-even premium + transparent sweep; disclose-only). Safe-2 floor affordable <=$2.00/contract, Bold <=$2.78 -> ITM-2 ~$3 flagged unaffordable. Playbook 5.8 doc. 9 red-proofed tests. (commit d553fe5)
- [ ] G8 greeks/IV capture — FIRST investigate whether the engine fetches greeks on the entry path. If yes: add them to the decision/entry log row. If no: add a LOG-ONLY snapshot fetch at entry (zero behavior change; must fail-open, never block/slow a fill). Guard: the log row carries delta/theta/IV.
- [ ] G9 sim-vs-live parity ledger — nightly script diffing each live fill (`filled_avg_price`, FIX3) vs the sim-assumed next-5m-bar fill for the same signal bar → per-setup slippage/latency. New file, no live-path.
- [ ] G15 hygiene — fix stale `_j_vwap_cont_doc` (says DORMANT while `j_vwap_cont_enabled=true`); web-verify Alpaca SIP price → hand J the number (D-SIP); one OP-22 consolidation pass on `queue.md`.
- [ ] G17 ET-derivation dedup (C14) — `autonomy_actuator.py:_et_now`/`_market_is_open` hand-roll a VERBATIM copy of et_clock's DST logic + the 09:30-15:55 window; `test_et_clock` layer-3 doesn't even track it. Migrate to `from et_clock import et_now, is_market_hours` + add it to `_INLINE_DST_FILES`. Small, safe, same-dir import (et_clock is pure-stdlib, no tzdata needed).
- [ ] G5 alert/capture flywheel — `level_memory` fires a Discord-outbox ping on a high-memory-level rejection (regime context) + define `analysis/j-calls/anchors.jsonl` capture schema. LOG/NOTIFY-only, no trading path → ships without ratification. Guard: a detected rejection writes an outbox row.
- [ ] G10 audit-tail recovery — try `Workflow({scriptPath:.../unknown-unknown-audit..., resumeFromRunId:"wf_a6e5356c-0e7"})`; resume is SAME-SESSION-ONLY so this likely fails cross-session → then mark `[B]` (the 6 unread findings were MED/LOW; re-running the full audit is not worth the tokens tonight).
- [ ] G12 htf_15m suppression measurement — log-analysis on `core-decisions.jsonl` history: how often does 09:30–11:00 `htf_15m` contradict the realized session trend AND was an ENTER suppressed. $0, no code change. If real+costly → design a fix (don't fix before measuring).
- [ ] G4 fleet divergence PHASE 1 — per-arm gate-strictness on the SHARED perception. **TRAP: `test_fleet_producer_keystone::test_scoring_peak_off_reverts_fleet_to_inert_BITE` PINS the inert design — frame-fix it in the SAME commit (L197).** Validate via `replay_fleet_arms.py` before ship. Uncertain → `[B]` BLOCKED-NEEDS-REVIEW.
- [ ] G11 level_memory → `key-levels.json` producer. **TRAP: entry-path blast radius (filter-10) — A/B via the feed harness FIRST.** Not cleanly validated → `[B]` BLOCKED-NEEDS-REVIEW.
- [ ] G6 J-exact weekly-spec battery — OTM weekly put + UNDERLYING-level stop (e.g. "750.20") + hold-to-Friday, on the 3-4DTE cache. One PRE-REGISTERED battery. Honest prior: modest / gap-exposed. Report verdict either way.
- [ ] G13 treasurer trajectory review (Safe-2 doom-loop, down ~32%/3wk) — analysis + options doc only; the equity reset itself is D4 `[B-J]`.

## J-DECISIONS (loop does NOT execute — flag + wait)
- [B-J] D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: yes)
- [B-J] D5 min-1 contract for single-exit shapes (his Rule 6)
- [B-J] D6 activate G7-EOD-flatten backstop cd-2026-06-27-001 (rec: yes)
- [B-J] Provision futures on Tastytrade 5WW73759 → MNQ live-paper
- [B-J] Paid SIP data (~$99/mo, verify) → volume-shelf lens

## PROGRESS LOG (append one line per iteration)
- 2026-07-07 ~22:45 ET: Tier 1 (G1/G2/G3) DONE + verified (129 graduated-guards passed). Loop armed for Tier 2–4.
- 2026-07-07 ~23:00 ET (loop armed, iter 1): goal file + self-paced /loop set up. Pre-findings: NO armability/min-lot check exists anywhere (G7 premise confirmed); `et_clock.py` returns EMPTY -> added G16 (verify FIRST). After-hours confirmed (build-safe). Real items (G16->G7->...) fire on the loop wakes with fresh context.
- 2026-07-08 00:33 ET (iter 2, G16 DONE): et_clock CLI + is_market_hours shipped 54ce9b6; gate PASS (5 suites/31). Found autonomy_actuator ET dup -> queued G17. Next: G7 armability.
- 2026-07-08 00:45 ET (iter 3, G7 DONE): armability primitive + promoter disclosure + playbook 5.8; d553fe5, gate PASS. Verified: no $ premium persisted in ratification artifacts -> disclosure sweeps, exact capture deferred to G8/G9. Next: G8 greeks/IV capture.
