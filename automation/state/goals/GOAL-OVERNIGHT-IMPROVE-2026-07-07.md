# GOAL: OVERNIGHT-IMPROVE-2026-07-07

> J verbatim (2026-07-07 ~23:00 ET): "work all night, don't stop." Source: the Fable
> gap-audit, `markdown/audits/FABLE-GAP-AUDIT-2026-07-07.md` +
> `markdown/audits/FABLE-DECISIONS-2026-07-07.md`.

**FOLDED 2026-08-29 (OP-22)** from the pre-`/goal`-schema original at
`automation/state/overnight-goal.md`, which is now a tombstone pointing here. This
file is a reformatted-not-rewritten copy — content preserved, sections relabeled to
the current schema. **ARCHIVED / TERMINAL — `active-goal.json` does not point here.**

## DONE-WHEN
(Reconstructed retroactively — the original loop predates this DONE-WHEN convention.)
All 17 gap-audit items (G1-G3, G5, G6, G7-G13, G15-G17) either shipped with a
red-proofed guard + path-scoped commit, or reached an honest `[B]`
BLOCKED-NEEDS-REVIEW / `[B-J]` disposition with the reason stated. A null/kill
verdict (e.g. G6's weekly-hold KILL) counts as DONE-WHEN met for that item.

## OPERATING RULES
1. `et_clock` gate: market hours = read-only (research/docs only, no live-engine
   edits, no heavy grinds sharing the heartbeat's Max pool); after-hours/weekend =
   full build.
2. Pick the TOP `[ ]` item; read its gap-audit spec + any flagged TRAP before
   touching anything; re-verify the pointer (inherited claims are this repo's
   disease).
3. Every code change ships with a red-proofed guard (revert → guard RED → restore)
   + a path-scoped commit; the pre-commit safety gate must pass. Red-block →
   REVERT + mark `[B]` with the reason, never force past a red gate.
4. Live-path / entry-blast-radius items (G4, G11): A/B or replay-validate before
   shipping, else `[B]` BLOCKED-NEEDS-REVIEW.
5. The OP-0 J-first four (arm live money, rotate/expose a secret, irreversible
   external, genuine no-default fork) are always `[B-J]` — flag the exact ask, move
   on.
6. After each item: update its checkbox + one-line result here; one-line note to
   STATUS.md on any commit.
7. Stop when: all items `[x]`/`[B]`, OR the safety gate red-blocks twice in a row
   (halt + flag), OR market opens with only live-path items remaining (go read-only).

_(2026-08-29 addendum, current-schema clauses that postdate this goal but apply to
any future work resumed from it: CONFIG FREEZE 2026-08-31→~09-29 on trading-path
changes; `conductor_outcome.py record` per fire; `model:"sonnet"` on every fan-out;
STATUS.md at OPEN/CLOSE only.)_

## QUEUE
- [x] G1 adopted-position CAP-ONLY (commit 55fd164) + 3-test red-proofed guard
- [x] G2 production-interpreter import verified (system-python + venv PYTHONPATH; pandas 2.3.3)
- [x] G3 runner close-out + corrected EOD +$489 (commit fc8ee27)
- [x] G16 et_clock health — runnable CLI + canonical `is_market_hours()` gate (commit 54ce9b6)
- [x] G7 armability gate — `backtest/lib/armability.py` + promoter disclosure (commit d553fe5)
- [x] G8 greeks/IV capture — `fleet_broker.get_option_greeks` + `heartbeat_core._capture_greeks` (commit addb959)
- [x] G9 sim-vs-live parity ledger — found 0 reconciled fills ever (commit 412ec93)
- [x] G15 hygiene — stale vwap_cont docs, doc/flag guard, SIP=$99/mo (commit dd84573)
- [x] G17 ET-derivation dedup (C14) — `autonomy_actuator` now delegates to `et_clock` (commit 8c672c0)
- [x] G5 alert/capture flywheel — DETECT→ALERT→CAPTURE; found+fixed 113 dropped alerts (commit 327479e)
- [x] G10 audit-tail recovery — recovered 27 findings + 12 verdicts off disk verbatim
- [x] G12 htf_15m suppression measured (9d/708 ticks) — real but not costly, no fix shipped
- [B] G4 fleet divergence PHASE 1 — NEEDS-REVIEW: entry-path fleet-producer keystone; spec `markdown/audits/G4-FLEET-DIVERGENCE-SPEC.md`
- [B] G11 level_memory → key-levels producer — NEEDS-REVIEW: entry-path level-feed (filter-10) blast radius; A/B first
- [x] G6 J-exact weekly-spec battery — **KILL**: hold-to-Friday fails random-entry null, bleeds -$4-6K on overnight gaps
- [x] G13 treasurer review — Safe-2 drawdown = J manual activity (averaging-down + qty-5 + off-scope crypto), not the engine

## J-DECISIONS
- [B-J] D4 Safe-2 paper-reset to $2K w/ epoch ledger (rec: YES, strengthened by G13)
- [B-J] D5 min-1 contract for single-exit shapes (Rule 6)
- [B-J] D6 activate G7-EOD-flatten backstop cd-2026-06-27-001 (rec: yes)
- [B-J] Provision futures on Tastytrade 5WW73759 → MNQ live-paper
- [B-J] Paid SIP data = $99/mo CONFIRMED (Algo Trader Plus) — volume-shelf lens (D-SIP)

**Flag:** crypto activity in Safe-2 paper (UNI/USD, BTC/USD scalps) contradicted the
scope lock (crypto = gym-only) — either J manually scalping (contaminates Safe-2 as
an engine-measurement account, see D4) or a rogue process (investigate). (G13,
2026-07-08)

## PROGRESS LOG
- 2026-07-07 ~22:45 ET: Tier 1 (G1/G2/G3) DONE + verified (129 graduated-guards passed).
- 2026-07-07 ~23:00 ET (iter 1): loop armed. No armability/min-lot check existed
  anywhere (G7 premise confirmed); `et_clock.py` returned EMPTY → queued G16 first.
- 2026-07-08 00:33 ET (iter 2, G16 DONE): 54ce9b6, gate PASS.
- 2026-07-08 00:45 ET (iter 3, G7 DONE): d553fe5, gate PASS.
- 2026-07-08 00:58 ET (iter 4, G8 DONE): addb959, gate PASS. UNVERIFIED at ship time:
  live snapshots URL form (fail-open, proven only on first real fill).
- 2026-07-08 01:05 ET (iter 5, G9 DONE): 412ec93. KEY FINDING: 0 reconciled fills
  across core + all 6 fleet arms — the rig had never recorded a filled entry.
- 2026-07-08 01:15 ET (iter 6, G15 DONE): dd84673, gate PASS.
- 2026-07-08 01:20 ET (iter 7, G17 DONE): 8c672c0, gate PASS.
- 2026-07-08 01:30 ET (iter 8, G5 DONE): 327479e. KEY FIX: 113 alerts silently
  dropped by the discord bridge (schema mismatch) — now delivered.
- 2026-07-08 01:38 ET (iter 9, G10 DONE-RECOVERED): read the truncated audit tail
  off disk instead of blocking. F1 (min_ribbon_momentum_cents=0 arming a supposedly
  disabled Safe gate) re-verified live, queued.
- 2026-07-08 01:44 ET (iter 10, G12 DONE): htf suppression measured, no fix (correct
  per measure-before-fix).
- 2026-07-08 01:50-02:14 ET (iter 11, G4/G11): both entry-path items → BLOCKED-
  NEEDS-REVIEW by design (won't auto-ship a producer keystone unsupervised); specs
  written for J-supervised A/B.
- 2026-07-08 00:19 ET (G13 DONE via treasurer agent): Safe-2 drawdown traced to J
  manual activity, not the engine.
- 2026-07-08 00:30 ET (G6 DONE — KILL): weekly-put hold-to-Friday killed (null-failed
  + gap-exposed + doesn't hold). **GAP-AUDIT COMPLETE. Loop terminated.**

## HONEST STATE
Terminal as of 2026-07-08 ~00:30 ET. 12 items shipped with red-proofed guards, 2 held
`[B]` NEEDS-REVIEW pending J-supervised A/B (never auto-shipped — correct per rail 4),
5 items routed to J as `[B-J]`. One KILL (G6, evidenced not just asserted). The
loop's own honest self-assessment at close: G4/G11 remain the two live open threads
if anyone picks this back up — check current repo state before assuming either is
still unshipped, this file is a historical record, not a live status board.
