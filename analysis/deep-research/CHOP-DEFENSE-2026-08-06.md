# DON'T TRADE CHOP, honestly — per-trade admissibility + the exposure meter

**2026-08-06, after the close.** Clock verified first action this lane:
`python setup/scripts/et_clock.py` → **`2026-08-06 18:46:33 Thursday EDT, market_hours=False`**.
Prereg frozen and committed **before** any runner existed:
`analysis/recommendations/chop-defense-prereg-2026-08-06.json` @ **5737488a**
(provable: `git merge-base --is-ancestor 5737488a a2ce72d0` → true).

> J's directive for next week: *"Small losses, strategic entries, good days where we hold our
> winners and don't trade chop."* The day-level chop classifier is **DEAD** (20.9% vs 39.1%
> baseline) and is NOT resurrected here. This lane asked the only live question: do PER-TRADE,
> INTRA-DAY proxies — computable at entry from closed bars and the arm's own booked outcomes —
> achieve what the day-level classifier could not?

---

## FOR J — 10 LINES

- **"Did we trade chop today" is now a glance:** `Gamma_ChopMeter` (16:08 ET nightly) writes one
  line into firm-brief.md. Tonight's first real line: **4 entries | ord>=4: 0 | against V-d1: 0 |
  zero-structure: 0 | rr<0.70: 1 | fleet realized floor +$0 | BRK600 would-trip: no.**
- **Measurement only.** The meter blocks nothing, touches no params. Revert = one line
  (`Unregister-ScheduledTask Gamma_ChopMeter`).
- **12 fresh admissibility cells, honest score: 1 clean pass, 11 rejects/nulls.**
- 🎯 The one live cell: **B-RR-070 — realized range at entry < 0.70× the 20-day median**
  (compression = chop). +$765 on the 26-day book (0 days harmed, blocked-cohort WR 11.4%) **and
  +$1,645 on the independent 391-day replay (22 days helped / 2 harmed, zero Wednesday in it)** —
  the only fresh cell with cross-population support. **BH q = 0.50 fails the 0.10 bar → PREREG
  with a forward clock, NOT a ship.** The meter counts it nightly from day one.
- ❌ **"No structure yet = chop" is WRONG on this book:** blocking zero-structure entries costs
  Tuesday **−$2,091** (the best gap entries fire before any structure event exists). The meter
  reports the count as CONTEXT, never an alarm.
- ❌ **"Against the last structure event = chop" is DEAD** (−$1,501 Thursday — reclaim winners
  fire against prior bearish breaks by construction). Confirms the structure_shift_confirmation
  graveyard verdict from the entry side.
- **Consecutive-loss halts add nothing beyond CAP-3:** the only passing variant blocks the
  identical Wednesday trades (+$653, same set).
- **The BRK600/CAP-3/CONSEC4 preregs now have their forward-evidence recorders** — the meter logs
  the fleet-POOLED REALIZED floor + would-trip nightly, the surface the live equity-based
  `daily_loss_guard.py` does not have.

---

## 1. Provenance and the trust gate

Population A = the same 208 real broker fills / 26 ET dates (2026-06-26…2026-08-06,
`attribution=="engine"`, SPY options) every KEEP-LOSSES lane used. The runner
(`backtest/tools/chop_admissibility_2026_08_06.py`) refuses to print any cell unless the base
reconciles to broker truth — run fresh this session, **6/6 PASS**:
book +$1,782.01 · 208 positions · 26 dates · Tue +$3,624.00 · Wed −$1,935.00 · Thu +$1,465.00.

Population B = the 391-day engine replay (191 trades / 141 traded days, pinned
`spy_5m_2025-01-01_2026-07-22.csv` lineage). Family A's "structural NO-OP on B" claim was
**verified, not assumed**: max consecutive same-contract losers on B = 2, so the ≥3 cells cannot
fire and the ≥2 cells never see a third entry (0 blocked → NO_OP).

Semantics per prereg: taken-counted sequential walk (blocked contributes $0, never increments
any counter, exits book before entries at equal timestamps) for family A; stateless deletion
arithmetic for families B/C. ABSTAIN never blocks. No exit re-walked, no fill re-priced.
**Verdict cap frozen in the prereg: nothing from this battery may exceed PREREG** (every cell is
a same-week post-Wednesday hypothesis); C-AGAINST was pre-capped at SHADOW (graveyard-adjacent).

## 2. The 12 fresh cells — full table, nothing hidden

Gates = the L4 G1–G8 battery (Tue ≥ −$100 hard / Thu ≥ −$100 hard / Wed > 0 / total > 0 /
ex-Wed ≥ 0 / 0 days harmed / n ≥ 5 / popB ≥ 0 or NO-OP). p = within-day permutation (20k draws,
seed 20260806); q = BH over the 12 cells with the parent-17 base.

| cell | blocked | Δtotal | ΔTue | ΔWed | ΔThu | Δex-Wed | harmed | popB | p | q | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A-CONSEC-CONTRACT-2 | 25 | +598 | **−524** | +913 | 0 | −315 | 2 | NO_OP | 0.72 | 1.0 | REJECT |
| **A-CONSEC-CONTRACT-3** | 8 | +676 | 0 | +653 | 0 | +23 | 0 | NO_OP | 0.36 | 1.0 | PREREG (CAP-3-redundant) |
| A-CONSEC-SETUP-2 | 53 | −978 | **−2,108** | +913 | 0 | −1,891 | 2 | NO_OP | 0.87 | 1.0 | REJECT |
| A-CONSEC-SETUP-3 | 21 | +345 | −444 | +653 | 0 | −308 | 1 | NO_OP | 0.55 | 1.0 | REJECT |
| B-RR-050 | 9 | +103 | 0 | 0 | 0 | +103 | 0 | +152 | 0.13 | 0.54 | NULL (Wed untouched) |
| B-RR-060 | 28 | +217 | 0 | 0 | 0 | +217 | 0 | +714 | 1.0 | 1.0 | NULL |
| **B-RR-070** | 35 | **+765** | **0** | **+451** | **+36** | **+314** | **0** | **+1,645** | **0.088** | **0.50** | **PREREG — 8/8 gates, both populations** |
| B-RR-080 | 63 | +546 | 0 | +1,142 | **−1,465** | −596 | 1 | −634 | 0.46 | 1.0 | REJECT (kills Thursday) |
| C-NOEVT | 75 | +647 | **−2,091** | +1,363 | 0 | −716 | 3 | −1,711 | 0.31 | 1.0 | REJECT |
| C-TSSE-30 | 36 | +1,032 | +545 | 0 | 0 | +1,032 | 1 | −1,429 | 0.026 | 0.24 | NULL (Wed untouched; popB negative) |
| C-TSSE-60 | 11 | +497 | +361 | 0 | 0 | +497 | 0 | −100 | 0.029 | 0.24 | NULL |
| C-AGAINST | 20 | −1,000 | 0 | 0 | **−1,501** | −1,000 | 2 | −774 | 0.97 | 1.0 | REJECT (capped SHADOW anyway) |

Three readings that matter:

1. **B-RR-070 is the only fresh cell with a real cross-population shape.** On A it blocks a
   cohort with WR 11.4% ($32 of winners vs $797 of losers, including Wednesday's two 10:18
   ord-5 776C entries and tonight's −$36 14:21 squeeze); on B it deletes a WR-7.7% cohort for
   +$1,645 spread across 22 helped days with zero share from any single day. **And the threshold
   is razor-adjacent to disaster: B-RR-080 blocks Thursday's entire +$1,465.** That knife-edge
   is exactly why q=0.50 means forward clock, not arming.
2. **Structure timing does not discriminate Wednesday.** Wednesday's 09:58–10:18 churn fired
   AFTER fresh structure events (C-NOEVT/TSSE leave Wed untouched at $0 or block Tuesday
   winners). The chop that hurt this book is *repeat entries into the same falling contract* —
   already covered by same-bar + CAP-3 + the breaker — not "entries without structure."
3. **Loss-conditional halts converge to CAP-3.** A-CONSEC-CONTRACT-3's Wednesday block set is
   identical to CAP-3's (+$653, same four 10:14/10:18 entries) with less ex-Wed money (+$23 vs
   +$67). Carry ONE lever (CAP-3, already preregged); a second overlapping lever adds attribution
   confusion and zero dollars (KEEP-LOSSES §2: levers never add).

Feature census (context for the meter): 75/208 A-entries (36%) fire with zero structure events;
median minutes-since-structure at entry 14.1; rr quartiles 0.75/0.89/1.21 (A) vs 0.81/1.16/1.63
(B) — the live book already trades noticeably more compressed tape than the replay population.

## 3. Inherited — cited, not re-run (KEEP-LOSSES-SMALL-2026-08-06.md)

Per the lane brief, lever (d) numbers are inherited verbatim and were NOT remeasured:
same-bar cooldown Tue +$144 / Wed +$202 / 0 of 26 days harmed (S2 ships it in the Fix+Ship
lane); CAP-3 +$720 (91% single-day); CONSEC4 +$974 (4 dates total evidence); fleet −$600
realized breaker +$1,225 (LODO 100%, margin $73, safe band $800 wide); recommended package
floor Wed −$710, 0 harmed. The ordinal ladder stands: 4th −$257 (n=9), 5th+ −$463 (n=3, WR 0%).

## 4. The CHOP EXPOSURE METER — shipped

`setup/scripts/chop_exposure_meter.py` → `automation/state/chop-exposure-{date}.json` +
`-last.json`; `firm_brief.render_chop_lines` renders the line (additive, fail-open — a missing
artifact renders "meter has not run yet", never an exception). Registered `Gamma_ChopMeter`
16:08 ET daily, deliberately between `Gamma_BrokerFills` (16:05, refreshes the fills ledger) and
`Gamma_FirmBrief` (16:10, renders the line).

**Line columns** (per-entry detail in the JSON): entries · **ord>=4** (the entries CAP-3 would
block — its forward-clock recorder) · **against V-d1** (last closed 5m bar disagrees; flat =
disagree, c6 parity) · **zero-structure** (context only — see §2.2) · **rr<0.70** (B-RR-070's
forward clock, disclosed as a post-battery additive column) · **worst consec-loss run** (CONSEC4
recorder) · **fleet-pooled REALIZED floor + BRK600 would-trip** (the surface the live per-account
equity-based `daily_loss_guard.py` does not have; realized basis per the prereg's build spec).

**Verification quoted fresh:** guard suite `backtest/tests/test_chop_exposure_meter.py` → 8/8
green; RED-proofed by TWO source mutations (meter `ORD_ALARM` 4→5 → 4 guards RED; firm_brief
section removal → 1 guard RED), both restored **byte-identical** (sha256 `e70c1c30…` and
`3a3a5f9c…` match pre-mutation) and re-proven green. Task fired through the REAL
wscript→pythonw chain: `LastTaskResult=0`, artifact rewritten 17:08:52 MT. Meter Thursday
reconciles broker truth to the dollar (4 entries, +$1,465) and its rr<0.70 count (1) matches the
battery's blocked detail for the same day (the 14:21:55 −$36 squeeze).

**Reverts (one line each):** `Unregister-ScheduledTask Gamma_ChopMeter -Confirm:$false` ·
git revert `7aac35e6`.

## 5. Preregs now standing (frozen @ 5737488a)

| lever | status | forward clock | kill |
|---|---|---|---|
| **BRK600** fleet REALIZED breaker | PREREG — build spec written, enforcing surface NOT built (per ladder #2) | ≥10 sessions of meter-recorded floor/would-trip | would-trip on any day that ends green |
| **CAP-3** | PREREG | ≥10 sessions AND ≥8 recorded ord≥4 events | a blocked 4th+ entry worth > +$300 |
| **CONSEC4** | PREREG (optional leg) | same window via per-arm run column | halts before a green session, twice |
| **B-RR-070** | PREREG (new tonight) | meter rr column; judge at ≥10 sessions with ≥8 rr<0.70 entries | rr-blocked cohort turns net-winner, or the Thursday-shape repeat (a compressed morning that pays) |

The breaker build spec (realized basis, latching, blocks-new-entries-only, partial-read →
non-actionable, `fleet_breaker_enabled:false` flag must pre-exist the logic, threshold −$600
frozen on the margin argument) is in the prereg file — **the enforcing breaker is deliberately
NOT built tonight.**

## 6. What this lane did NOT do + open reconciliations

1. **Nothing was armed.** Zero trading-path changes; every shipped byte is measurement.
2. **B-RR-070 is in-sample-selected on A** (4 thresholds swept); its credibility rests on the
   B-side +$1,645 and the forward clock, never the A-side ranking.
3. **Structure walk is 5m/window-2 per-day only** — other granularities/windows untested (and
   not preregged; adding them requires a fresh prereg).
4. **PARALLEL-LANE OVERLAP (open for the orchestrator):** another lane tonight froze a
   *structure-presence admissibility* prereg and is shipping a *V-d1 shadow counter* (tasks
   L4-B/L4-D). My C-family cells and the meter's V-d1 column overlap those surfaces. Both lanes'
   definitions should be reconciled before either V-d1 instrument is cited as THE counter —
   flagged, not resolved here.
5. **The meter's 5m fetch depends on one live arm key** (probed per L234, never hardcoded); a
   full-broker outage degrades bar columns to n/a (disclosed in-line) — by design.

## Artifacts

| path | what |
|---|---|
| `analysis/recommendations/chop-defense-prereg-2026-08-06.json` | frozen prereg (5737488a) |
| `backtest/tools/chop_admissibility_2026_08_06.py` | battery runner (a2ce72d0) |
| `analysis/deep-research/CHOP-DEFENSE-2026-08-06.json` | all 12 cells, censuses, popB detail |
| `setup/scripts/chop_exposure_meter.py` + `install-chop-meter.ps1` | the meter (7aac35e6) |
| `backtest/tests/test_chop_exposure_meter.py` | 8 guards, RED-proofed ×2 |
| `automation/state/chop-exposure-2026-08-06.json` | first real nightly artifact |

**Checks run fresh this session:** et_clock 18:46:33 EDT market_hours=False · trust gate 6/6 ·
popB family-A NO-OP verified (max run 2) · guards 8/8 → RED ×2 → byte-identical restore → 8/8 ·
Gamma_ChopMeter real-chain fire LastTaskResult=0 · meter-vs-battery Thursday reconciliation
exact · prereg-before-runner ancestry proven.
