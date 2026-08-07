# SCORE-LADDER-V2 REPLAY — 2026-08-07 (J's 4th ask, demerit semantics)

> Prereg frozen + committed BEFORE any run: `analysis/recommendations/prereg-score-ladder-v2-2026-08-07.json`
> (commit `c2ec28f3`, 12:35 ET — git-provably precedes the runner). Clock verified at start:
> `2026-08-07 12:07 EDT market_hours=True`. All runners in `backtest/tools/score_ladder_*.py`.
> Machine mirrors: `SCORE-LADDER-REPLAY-2026-08-07.json` (population) ·
> `SCORE-LADDER-GATES-2026-08-07.json` (gates/battery) · `SCORE-LADDER-SIDE-LANES-2026-08-07.json`
> (bull/bear-only) · `SCORE-LADDER-WEEK-LIVE-2026-08-07.json` (live-tape week, real OPRA) ·
> `SCORE-LADDER-TODAY-EST-2026-08-07.json` (today, EST).

## VERDICT FIRST

**DO NOT SHIP TONIGHT — PREREG + forward shadow clock instead.** The frozen gates fail, by
their own pre-stated numbers:

| Frozen gate | rung 7 (risky-3, J's spec) | rung 8 (risky-1) |
|---|---|---|
| G_week (ladder week net > binary AND > 0) | **FAIL** — live-instrument week extras **−$59.60** | **FAIL on frozen instrument**; live instrument **+$972.40** but week *net* (incl. the real book's negative Fri) ≤ 0 |
| G_tuesday (no material degrade) | PASS — Tuesday **improved +$1,243.90** | PASS (same) |
| G_wednesday (≥ binary − $300, no spiral) | **FAIL** — Wed extras **−$1,143** (11 entries) | **FAIL by $105** — Wed extras **−$405** (5 entries, re-opens a mild 777C/776C chase) |
| G_population_net (≥ binary − 10%) | PASS (+$9,970 vs +$5,777) | PASS (+$11,485) |
| G_population_tail (worst day not >25% worse) | PASS (−$1,983 vs −$2,142) | PASS |
| BH q=0.10 across all cells | **NOTHING SURVIVES** (best cell p=0.066) | same |

Per the prereg's verdict rule (ALL gates must pass): **PREREG-ONLY**, failing cells named:
`G_wednesday` (both rungs, live instrument), `G_week` (rung 7 live; all rungs on the frozen
orchestrator instrument), BH-null everywhere. The pre-registered **BULL-ONLY** subsidiary
cell is the one live candidate (below) — it fails the same Wednesday/week gates tonight and
goes on a **frozen forward clock** (shadow ledger, arm bar pre-stated) instead of shipping.

**Bear-side demotion is DEAD ON ARRIVAL — do not arm on any rung.** Population bear extras:
rung 7 **−$4,564/315tr**, rung 8 **−$6,360/280tr** (bear-only lanes confirm: −$4,947 / −$6,311).
This is the same shape as the 2026-07-27 disarmed raw-floor lane (−$10.9K at floor 9) — the
demerit tightening softens but does not cure it.

## J's question, answered literally

> "Why are we sitting out of anything that's a ten out of eleven?"

**The ladder takes it.** The 10:15 tick (bull_score 10/11, sole blocker filter 10,
level_reclaim+confluence at 770.46): adjusted score 9 ≥ rung 7 → risky-3 IN, ≥ 8 → risky-1 IN
(guard-pinned: `backtest/tests/test_score_ladder_v2_admission_2026_08_07.py`, 11/11 green,
RED-proofed). Walked mechanically on today's tape (EST pricing), the 10:14–10:24 window is
messier than the eyeball: first entry 770C structure-stopped **−$109 EST** on the 10:20
pullback, re-entry at 10:24 caught the run **+$288 EST** (runner_stop @ 1.83). The window
nets ≈ **+$172 EST** at qty 3 — real, but not the clean +30% ride the refusal log implies.

**And this week it takes J's misses:** Mon 09:46 752C sole-f10 refusal → **+$738** real-OPRA
runner to the 15:40 time stop; Tue 09:41 + 10:36 sole-f10 refusals → **+$459.50 / +$784.40**.
Those three are exactly the trades J has been pointing at. The cost side: Wednesday's fade
chase (−$405 at rung 8) and Thursday's VIX-demoted puts (−$481.50) give most of it back.

## Today (2026-08-07) — EST-labeled (same-day OPRA 403 until ~16:21)

EST = Black-Scholes from the engine's own per-tick spy/vix, calibrated k=1.0293 against 47
REAL NBBO anchors from today's ledger (IQR 0.96–1.09). Scoring authority = the live engine's
own logged scores/blockers (no re-scoring). *Numbers below refreshed at the last pre-close run.*

- Refused-tick admissions today (rung ≥6 shape): 132 of 306 HOLD rows; 74 ELITE (score ≥10)
  in the 10:15–11:45 window, sole blockers f10 (54), f7 (10), f11 (10 — **correctly refused
  on every rung**: level-tied/trigger-count gate is non-demotable).
- **Study lane (qty 3, ATM, extras only):** rung 7 **+$66.72 EST** (7 trades) · rung 8
  **+$156.03 EST** (6 trades) — as of 12:32 ET; final table in the JSON after the close run.
- **Arm cells (real fills + EST extras, real hold windows occupy the lane):**
  risky-3 rung 7: real **−$420.00** + extras **+$184.60 EST**;
  risky-1 rung 8: real **−$400.00** + extras **+$394.62 EST**.
- Honest morning cell: no earlier/bigger morning loser is admitted for the ARM lanes — the
  arms were genuinely holding the real 09:46–10:02 loser, so the ladder adds nothing worse
  pre-10:14. (The unoccupied study lane does take a 09:51 −$89 EST loser at rung 7.)

## The week — LIVE-TAPE instrument (engine's own ticks, REAL OPRA, qty 3 ATM extras)

| Day | rung 6 | rung 7 | rung 8 | rung 9 | color |
|---|---|---|---|---|---|
| Mon 08-03 | +738.00 | +738.00 | +738.00 | +738.00 | one sole-f10 refusal = the day's runner |
| Tue 08-04 | +1,243.90 | +1,243.90 | +1,243.90 | +1,243.90 | Tuesday NOT degraded — **added** two winners |
| Wed 08-05 | −1,143.00 | −1,143.00 | −405.00 | −405.00 | the adversarial day: rung 7 takes 11 chase entries (777C×2, 776C, 775C, 773C, 772C×2 + 2 puts); rung 8's stricter admission caps it at 5 |
| Thu 08-06 | −877.90 | −898.50 | −604.50 | −324.00 | f8-demoted puts (−289.50, −192) + late ribbon-demoted call |
| **Week** | **−39.00** | **−59.60** | **+972.40** | **+1,252.90** | rung 7 negative, rung 8 positive |

Spiral check (frozen): no 3+ same-contract re-entries at rung 8 (777C ×2 max) — the *count*
gate passes; the *dollar* allowance (−$300) fails by $105. Same-bar cooldown was DISARMED in
live config (as replayed); if it were armed per its shipped consult contract it would have
suppressed at most the 10:00/10:02 777C re-entry (−$117) — noted, not armed, per its own
day-0 DO_NOT_ARM prereg.

Why two week instruments: the frozen prereg's orchestrator replay barely trades this week
(offline OHLC-derived levels ≠ the live TV/memory level feed — the documented entry-layer
divergence), so its week cells (rung 8: −$330 vs binary −$100) measure replay divergence more
than ladder quality. The live-tape instrument above is the faithful one; the frozen gate is
still reported as frozen. Both fail the Wednesday allowance.

## Population — 398 RTH days (2025-01-02..2026-08-06), occupancy-applied lanes

Baseline = binary engine (both directions, current live config incl. `block_elite_bull=false`),
same walk mechanics. 253 missing leading-edge OPRA contracts (07-23..08-06) were backfilled
first — the initial run's week cells were structurally empty (all candidates `no_opra_cache`)
and were re-run; that defect and fix are part of this record.

| Lane | n | total | extras n / $ | bull extras | bear extras | displaced binary n / baseline $ | worst day |
|---|---|---|---|---|---|---|---|
| binary | 296 | +$5,777.10 | — | — | — | — | −$2,142 |
| rung 6 | 1,202 | +$2,157.45 | 1,018 / **−$9,577** | +$3,109 | **−$12,687** | 115 / −$6,600 | −$2,217 |
| rung 7 | 987 | +$9,969.85 | 794 / −$2,095 | +$2,469 | −$4,564 | 106 / −$6,930 | −$1,983 |
| rung 8 | 829 | +$11,485.10 | 623 / −$1,109 | +$5,251 | −$6,360 | 91 / −$6,829 | −$1,983 |
| rung 9 | 545 | +$13,254.00 | 297 / **+$3,350** | +$3,350 | 0 (rung 9 bear = binary) | 52 / −$4,139 | −$2,142 |

**⚠️ The lane uplift is mostly DISPLACEMENT, not extras.** At rung 8, the +$5,708 delta =
extras (−$1,109) + not-taking 91 binary trades that lost −$6,829 in the baseline (the ladder
is already in a position when they'd have fired, occupying earlier on a demoted tick of the
same setup). That is real one-position-at-a-time mechanics, but it is a fragile, luck-shaped
mechanism — daily-delta bootstrap p=0.21 (rung 8), and NOTHING clears BH q=0.10 (best cell:
rung 9 daily delta p=0.066). Treat the population "pass" as *non-catastrophic*, not as edge.

**Pre-registered side cells** (full lanes re-walked, not sliced):

| Cell | lane total | extras | week (live instr.) | verdict |
|---|---|---|---|---|
| BULL-only rung 7 | +$13,110.75 | 553 / +$2,576 (**ex-top5 −$1,817** — concentration junk) | — | fails G3-style robustness |
| **BULL-only rung 8** | **+$16,108.35** | 381 / **+$6,126** (+$16.1/tr, WR 34%; ex-top5 +$1,825; thirds +$2,165/−$1,348/+$5,309 — T2 negative) | Wed −$405 / week +$972 | **the one live candidate** — sub-window unstable, BH ns (p=0.107) → forward clock, not a ship |
| BEAR-only rung 7 | +$664.05 | 345 / −$4,947 | — | dead |
| BEAR-only rung 8 | +$1,789.95 | 295 / −$6,311 | — | dead — echoes the 2026-07-27 graveyard |

Battery (rung 8, full lane): G1 +$11,485 (delta +$5,708) · G3 ex-best-trade +$9,273 ·
G4 runner cohort n=150/+$99.5K (gross of stops; see JSON) · sub-window thirds delta
−$1,851 / +$1,869 / +$5,690 (T1 negative) · archetype delta: trend **+$4,205**, range +$1,361,
chop **−$21** (rung 7 chop: −$1,033 — rung 8 does not bleed chop worse than binary; rung 7
does) · worst day −$1,983. 93 extras excluded no-OPRA (spread across months, disclosed).

## Provenance + graveyard (what this is NOT)

- Harness audit: `arm_score_ladder_replay.py` (10-anchor table) and `ladder_fullhist_replay.py`
  (raw-floor fullhist — the DISARM evidence: floor 7/8/9 → −$31K/−$16.6K/−$10.9K) both found
  and reused for conventions; live `_ladder_plan`/`_ladder_block`/`_apply_score_ladder`
  machinery confirmed intact + inert (disarmed 2026-07-27, `score_ladder_floor` keys absent).
- This is NOT filter deletion, NOT filter-8 relax, NOT the raw-floor ladder: non-demotable
  absolutes retained (window/spread/VIX-hard/level-tied/risk_gate), double-demerit arithmetic
  (pinned by J's own 10:15 example: score 10, demerit 1 → adjusted 9), both sides tested,
  safe arms stay binary as the control — that IS the top rung.
- Re-arming the OLD `score_ladder_floor` key would resurrect the DEAD raw-floor semantics,
  not this design. The demerit ladder needs its own small producer/consumer change — spec
  staged in the close addendum, deliberately NOT built into the live path today (Rule 9 +
  failed gates).

## Disclosures (all of them)

1. **EST labeling**: every hypothetical today-number is BS-calibrated EST (k=1.0293, 47 real
   anchors); the week + population are REAL OPRA. Study-lane EST tracks are point-sample
   1-min bars (open=high=low=close) — intra-minute extremes invisible.
2. **Displacement dominance** in the population lanes (above) — the honest mechanism split
   is printed per lane in the gates JSON.
3. **5-min OPRA walk**: intra-bar stop/TP touches under-detected (documented
   OPTION-BAR-RESOLUTION-BIAS) — affects baseline and ladder lanes identically.
4. **Replay-vs-live entry divergence**: the orchestrator instrument's binary lane took ~0
   trades this trading week; its week cells are weak. The live-tape instrument closes that
   gap for the week; the population necessarily runs on the offline instrument.
5. **First run was defective** (week cells empty on a stale OPRA leading edge) — root-caused
   (`no_opra_cache` exclusions), 253 contracts backfilled via the established
   `expand_opra_cache` path, re-run. Both runs preserved in the log trail.
6. Today's arm-cell "real" P&L = broker FILL sells−buys ×100 (closed round-trips only).
7. `bold-2` was PDT-blocked live today (RISK_DENY_PDT logged 12:06) — the risky-arm cells
   here are unaffected (risky arms are PDT LOG-ONLY per FLEET-PDT-PARITY).

## Cross-lane note (discovered at addendum time)

A parallel workstream (LANE 1 in the close addendum) independently built a SINGLE-demerit
ladder (logged score ≥ rung, bull-only, demotable-only blockers) with weaker frozen gates
(added-P&L > 0; avg/added-trade > −$5) and reached **SHIP bull-only** with a dormant patch.
The two lanes' NUMBERS reconcile once conventions align (bull-only week positive in both;
bear dead in both; chop-day bleed scales with admission width in both); the VERDICTS differ
on demerit arithmetic and gate strictness. Full reconciliation + merge guidance:
[CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md](CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md)
§LANE 2. This lane's verdict under its own frozen prereg is unchanged: PREREG + shadow.

## Forward plan (what ships tonight instead of the arm)

- **Shadow nightly** `backtest/tools/score_ladder_shadow_nightly.py` (run ~16:40 ET: fetches
  the day's own OPRA post-16:21, walks all 4 rungs on the live tick ledger, appends
  `analysis/arm-ladder/ladder-v2-shadow-ledger.jsonl`). Task registration staged in the
  close addendum ($0, no trading-path surface).
- **Frozen arm bar** (stated before any forward data): consider arming BULL-ONLY rung 8 on
  risky-1 only after ≥10 shadow sessions with extras net > 0, no session < −$500 (qty-3
  basis), and negative-extras sessions averaging ≥ −$300. Bear side: off the table on
  current evidence.
- **J-override path** (his call, one ask away): the addendum carries the exact minimal spec.
  What the evidence supports if J overrides tonight: bull-only, rung 8, risky-1 only,
  min-size — NOT rung 7, NOT bear, NOT risky-3's 12-lot sizing.
