# ENTRY QUALITY — the signature of entries that PAY vs entries that BLEED (LANE 4, 2026-08-06)

> Clock verified at session start: `python setup/scripts/et_clock.py` → **2026-08-06 18:46:33
> Thursday EDT, market_hours=False**. Paper only. Nothing armed. Prereg
> `analysis/recommendations/entry-quality-admissibility-prereg-2026-08-06.json` committed
> **6d6bf8c8 BEFORE any runner existed** (git-provable). Ship commit **c7d2bf9b**.
> Machine twin: `ENTRY-QUALITY-2026-08-06.json`. Standing ledger:
> `analysis/entry-quality/entry-quality-ledger.json` (rebuilt by
> `setup/scripts/entry_quality_ledger.py`).

---

## VERDICT (four sentences)

1. **The signature is real and simple: entries that PAY are level-tied triggers taken on a tape
   with confirmed 1m structure (+$70.8/entry, 40% WR, median MFE +51%, n=55); entries that BLEED
   are bare confirmations into a structureless tape (−$103.1/entry, **0% WR**, n=16).** Wednesday
   lived in the second cell; Thursday and Tuesday lived in the first.
2. **The lane's named rule — "require ANY structure event within 8 bars" — is DEAD by its own
   pre-committed kill criterion:** Δ −$524, blocks $3,696 of winners, and its worst day is
   **−$1,760 on 08-04** — it would have gutted the record Tuesday. Structure **PRESENCE**
   (recency-uncapped, 1m, abstain-when-blind) is the surviving shape.
3. **Nothing clears the discriminating bar** (all five battery cells BH q=0.37+ vs the 0.10 bar),
   so **zero new rules graduate**: the frozen shadow set stays exactly V-d1 + V-e3, and tonight
   their **forward shadow counter is SHIPPED and proven running inside the real nightly fire**
   (forward session 1/10 logged: 4 entries, 0 blocks — both rules kept winning Thursday).
4. Two standing numbers were **corrected**: the 08-05 study's population dropped a −$237 engine
   entry (true ≤08-05 net **+$80**, not +$317), and V-e3's advertised basis (n=41, p=0.063) does
   not reproduce on verifiably-complete bars (true **n=28, p=0.29**).

---

## 1 · Population — LIVE-ENGINE-REAL-FILLS-v2

**235 engine entry events / 26 days (2026-06-26 → 2026-08-06) / net +$1,545 / WR 19.1%.**
Entries = engine-attributed option buy fills; P&L = FIFO against **all-attribution** exits
(broker truth). FIFO closes clean: 0 unmatched sell qty, 0 leftover. 5 manual buys excluded.

**Correction to v1:** the 08-05 study's n=230/+$317 population silently dropped
06-26 safe-2 `SPY260626P00732000` (engine buy 3×0.98, **manual**-attributed sell 0.19 = −$237)
because it filtered exits by attribution. True ≤08-05 net: **+$80**.

### Prior 5m-structure cuts — reconciled EXACTLY

| bucket | prior (v1, ≤08-05) | v2 (full) | delta explained |
|---|---|---|---|
| AGREES | 120 / +$344 | 122 / +$71 | +732P (−$237) +squeeze (−$36) |
| DISAGREES | 18 / +$559 | 21 / +$2,060 | +3 Thu puts (+$1,501) |
| **NO_EVENT** | **38 / −$1,366** | **38 / −$1,366** | **unchanged — VERIFIED** |
| BLIND | 54 / +$780 | 54 / +$780 | unchanged — VERIFIED |

The Thu A-grade puts read 5m-**DISAGREES** at fill time (last 5m event was a bullish BOS 3 bars
prior) while reading 1m CHoCH-DOWN 5-6 bars prior — the third independent confirmation that
**agreement is the wrong property and 5m is the wrong lens; absence on 1m is the killer.**

---

## 2 · Admissibility battery — all 5 frozen cells, BH-corrected (family = 5, q bar 0.10)

Population v2, within-day permutation (20k draws, seed 20260806, eligible-only draws).

| cell | n blk | Δ full | Δ drop-top2 | win$ blk | lose$ blk | blk WR | worst day | p | **BH q** | gates | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| R-PRES-5m | 38 | +1366 | **−159** | 830 | 2196 | 10.5% | −627 | .276 | .366 | 12--5-- | WATCH |
| **R-S8-5m** | 80 | **−524** | −2049 | **3696** | 3172 | 17.5% | **−1760 (08-04)** | .859 | .859 | ----5-- | **REJECT → GRAVEYARD** |
| **R-PRES-1m** (=V-e3) | 28 | **+2211** | **+565** | **0** | 2211 | **0.0%** | **+27** | .290 | .366 | 123456- | FWD-SHADOW (G7 fails) |
| R-S40-1m | 28 | +2211 | +565 | 0 | 2211 | 0.0% | +27 | .293 | .366 | 123456- | ≡ R-PRES-1m (cap never binds) |
| V-d1-rescore | 33 | +1242 | +726 | 15 | 1257 | 3.0% | −15 | .108 | .366 | 123456- | FWD-SHADOW (per its prereg) |

- **R-S8-5m is the pre-registered kill executed:** requiring *recent* structure blocks the early
  trend-day entries whose structure is stale-but-present — $3,696 of winners, −$1,760 on the
  record Tuesday alone. The idea "structure must be fresh" is now graveyard material with numbers.
- **R-PRES-1m blocks $0 of winners** — its blocked cohort is 28 straight losers (WR 0.0%), worst
  day +$27. It still fails the only test that separates "picked the bad entry" from "sat out a bad
  day" (q=0.37). It stays **SHADOW**; it is already frozen as V-e3 — no new prereg needed.
- **Graduation outcome (pre-committed selection rule): ZERO new preregs.** The at-most-two frozen
  admissibility rules remain **V-d1 + V-e3**.
- In-sample union V-d1 ∪ V-e3: 53 entries, overlap only 8 (nearly orthogonal), removed P&L
  −$3,068, union-blocked WR **1.9%** vs population 19.1%. IN-SAMPLE; the forward window decides.

### Cross-lane reconciliation (so J never reads a contradiction)

LANE 5's battery REJECTED its "C-NOEVT: block zero-structure entries" at **−$2,091 on Tuesday**;
this lane's R-PRES-1m shows **+$2,211 with $0 Tuesday impact**. Both are right: the deciding
choice is **quorum handling**. R-PRES-1m **abstains** below 20 closed 1m bars (early entries
stand); blocking-when-blind variants (the V-e2 shape, and LANE 5's cell under its definition)
gut Tuesday's early reclaims. *Absence-of-structure only survives when blindness abstains.*

---

## 3 · The factor crossings (descriptive — no significance claims)

Full tables live in the standing ledger JSON (`crossings{}`). Highlights:

| factor | PAY side | BLEED side |
|---|---|---|
| (a) 1m structure | AGREES n=162 +$3,549 (WR 23.5%) | **NO_EVENT n=28 −$2,211 (WR 0.0%)** |
| (b) trigger class | **tied n=61 +$4,170 (+$68/entry, WR 41%, medMFE +51%)** | bare n=132 −$1,911 (WR 9.8%, medMFE +9%) |
| (d) last-5m-bar | agree n=198 +$3,038 | against n=33 −$1,242 (WR 3.0%) |
| (e) time-of-day | 12:00-13:29 n=44 +$1,989 | **11:00-11:59 n=36 −$1,481 (WR 11.1%)** |
| (f) VWAP side | below n=57 +$36 (WR 29.8%) | above n=177 +$1,575 (WR 15.8%) — not a discriminator |
| setup | reclaims n=115 +$2,757 | VWAP_CONTINUATION n=17 −$558 (WR 11.8%) — extends the 08-05 watch item |

**Factor (b) confound check (important):** core rows under-log trigger levels — the *same
physical* Thu 10:31 put is `bare` on safe-2's core row and `tied @771.5` on the fleet rows. The
honest apples-to-apples read is **fleet-only: tied n=45 +$4,240 (+$94.2/entry, WR 46.7%) vs bare
n=88 −$1,801 (−$20.5/entry, WR 3.4%)** — the split survives, and hardens.

**Factor (c)** (distance to the owned session extreme): only 8 days of `levels_active` coverage,
191/235 abstain, every cell n-small — hug(0-0.5) n=3 −$151 / near n=19 −$247 / far n=9 +$1,301 /
beyond n=13 +$2,355. **Logged for accrual, no conclusions.**

### THE SIGNATURE (post-hoc 2×2 — prereg fodder, ships nothing)

| 1m structure × trigger | n | P&L | per entry | WR | med MFE |
|---|---:|---:|---:|---:|---:|
| **present + level-tied → PAYS** | 55 | **+$3,896** | **+$70.8** | **40.0%** | **+51%** |
| present + bare | 106 | +$350 | +$3.3 | 12.3% | +10% |
| absent + tied (n-small) | 3 | −$192 | −$64 | 0% | — |
| **absent + bare → BLEEDS** | 16 | **−$1,649** | **−$103.1** | **0.0%** | +11% |

Exemplars land exactly where the week said they would: **Thu 10:31** (1m CHoCH-DOWN 5-6 bars
prior, tied 771.5, below VWAP) = the PAY cell, +$1,501. **Wed 09:58-10:19** (zero structure,
`trigger_level=None`, buying a 19-39-min-old session high) = the BLEED cell. **Tue** reclaims: 1m
events present throughout — R-PRES-1m blocked ZERO Tuesday entries; the killed R-S8 would have
cost −$1,760 there.

---

## 4 · SHIPPED — the V-d1/V-e3 forward shadow counter ($0 trading-path impact)

| item | detail |
|---|---|
| **Counter** | `setup/scripts/entry_shadow_counter.py` — per-entry `would_block` booleans for V-d1 + V-e3 (semantics single-sourced from `entry_quality_ledger.blocked_by` — one implementation, L251), idempotent per activity_id |
| **Artifacts** | `analysis/entry-quality/shadow-tally.jsonl` (per-entry) + `shadow-summary.json` (running F-gate scorecard vs the frozen forward prereg) |
| **Nightly** | folded into the existing `Gamma_WinnerAutopsy` 16:25 ET fire — same fail-open contract as pain_ledger; **no new scheduled task** |
| **Proof in situ** | full `winner_autopsy.py` fire ran tonight: `[entry-shadow] 4 tally rows (0 new, 4 refreshed) across 1 forward session(s); vd1 blocks 0, ve3 blocks 0` |
| **Guards** | `backtest/tests/test_entry_shadow_counter.py` **14/14 green**; RED-proofed twice (V-d1 comparison inverted → 6 RED; V-e3 quorum 20→0 → 1 RED); both restored **byte-identical** (sha256 `225f2a0d…` verified) and re-proven green |
| **Revert** | one line: delete the `entry_shadow` try-block in `winner_autopsy.py` `main()` |
| **Forward window** | session **1/10** logged (08-06): 4 entries, 0 blocks either rule — the instrument's first datapoint is "both rules kept the whole winning Thursday" |

V-d1 carry-forward context (from the standing instruments lane): **+$918 ex-week, BH q=0.75** —
exactly why it is SHADOW and not armed. The counter makes the 10-session forward verdict
mechanical instead of a human re-derivation.

---

## CAVEATS (read before quoting)

- **n=235 / 26 days is small; 08-04 is +$3,624 of the +$1,545 net.** Every battery cell carries
  drop-top2 and per-day columns for exactly this reason.
- **Nothing clears BH q≤0.10.** Every in-sample dollar above is still consistent with "sat out a
  bad day" until the forward window says otherwise. J's paper bias (take the trade) stands.
- The 2×2 signature and the crossings are **post-hoc descriptive**; they ship nothing and may
  only seed a future prereg.
- Factor (b) at all-arms grain is partly a **logging artifact** (core under-logs trigger levels);
  fleet-only is the honest read. Factor (c) has 8 days of coverage — n-small everywhere.
- MFE joins from the pain ledger at position grain; adds carry `mfe=null`, counted, never
  zero-filled. Permutation draws among **eligible** (non-abstain) entries per day — disclosed.
- Bar data verified complete before trusting any structure read: 26/26 days × 390 RTH 1m + 78
  5m SIP bars.

## ARTIFACTS

| path | what |
|---|---|
| `analysis/recommendations/entry-quality-admissibility-prereg-2026-08-06.json` | frozen prereg, commit **6d6bf8c8**, before the runner |
| `setup/scripts/entry_quality_ledger.py` | standing ledger builder + frozen battery (`--battery`) |
| `analysis/entry-quality/entry-quality-ledger.json` | the standing scorecard (events + crossings) |
| `analysis/entry-quality/admissibility-battery.json` | all 5 cells, all cuts, BH q |
| `setup/scripts/entry_shadow_counter.py` + `analysis/entry-quality/shadow-*.json*` | the shipped shadow instrument |
| `backtest/tests/test_entry_shadow_counter.py` | 14 guards, RED-proofed ×2 |
| `analysis/deep-research/ENTRY-QUALITY-2026-08-06.json` | machine-readable twin of this report |
