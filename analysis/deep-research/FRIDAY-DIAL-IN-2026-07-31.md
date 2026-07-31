# FRIDAY DIAL-IN — 2026-07-31

**The most actionable finding: `block_elite_bull` refused +$867 of post-fix replay profit (n=5, drop-best +$177) while the ungated fleet banked +$1,242 real fills on the SAME blocked signals — the gate's entire 0%-WR/−$885 evidence base predates the levels-v2 fix. LIFT-GATE TRIAL ships this weekend on bold-2 at min size with a hard re-block bar.**

> Synthesized 2026-07-31 17:28 ET (`et_clock` verified, market closed). Four lanes, each independently adversarially reviewed (review verdicts: 3× MINOR_GAPS, 1× SOLID, 0 refuted). All numbers below are the reviewer-confirmed values; where a lane's own headline was found sloppy, the corrected number is used and the correction is named. No lane touched live params; nothing here is applied yet.

---

## 1. Lane verdicts — what ships vs what needs J

### Lane 1 — REQUALIFY `block_elite_bull` on post-fix data · **SHIP_CANDIDATE**

**Honest number:** post-fix replay of the blocked cohort (safe sequential-hold, qty 3, real OPRA, entry+1, live CONTROL exit shape): **n=5, +$867.00, WR 40%, drop-best +$177.40** — the exact drop-best bar the old-era evidence failed at (−$1,421). Fleet REAL fills mapped to the blocked clusters: **+$1,242.00 / 7 trades, losers included**.

- **Why the gate's evidence is void:** all 24 real bull fills behind `block_elite_bull` (0% WR, −$885) were gathered under the OLD broken level feed (IEX premarket, fabricated PMH, stale levels). Levels compiler v2 (SIP + shelves + weights, commit `7b4aa3f4`) shipped 2026-07-27 evening; the gate's own written condition was "re-eval at n≥20 under corrected feed." Post-fix days 07-28..07-31 are that re-eval's first evidence — and they point the other way.
- **Reviewer corrections folded in (cite these, not the lane's raw lines):**
  - The "111 blocks on 07-31 = 15 safe + 11 bold" line was garbled. Correct: 111 is the verdict-string count on 07-31 (action-filtered 101 rows: 50 safe + 51 bold); the 4-day window dedupes to **13 safe + 11 bold events = 11 distinct cross-account setups**. Artifacts carry the right numbers; the finding text didn't.
  - The fleet +$1,242 cell is **concentrated**: 3 correlated arms took the same 2026-07-29 14:31 signal (+$1,154 = 93% of the cell). Cluster-mean dedup ≈ **+$472**; dropping the whole 07-29 cluster leaves **+$88**. Both still >0, so the frozen 3-branch verdict rule fires branch (a) either way — but 7 trades ≠ 7 independent observations.
  - Concentration in the PRIMARY too: the 07-29 winner (+$689.60) is 79% of the +$867. Drop-best stays positive (+$177.40) — that is the load-bearing check.
- **Disclosed loser:** the one real post-fix core fill on this cohort (bold-2, 07-28, gate not binding) was **−$295**. Bold's own blocked cohort in its VIX[15,18) band replays flat (−$2.60/5tr, drop-best −$321) — that is exactly why the trial's kill bar is tight and why a negative trial read kills the bold band question, not necessarily Safe's gate.
- **This is a TRIAL, not a ratified edge.** n=5 over 4 sessions. The trial IS the instrument that builds n≥20 under the corrected feed.

**Ships this weekend (paper autonomy, no J needed):** conductor applies the one-key flip verbatim from the rec — `automation/state/aggressive/params.json` `block_elite_bull: false`, bold-2 only, min size, `revert=true` — and arms the kill-criterion tracker (**n≥10 elite-bull fills OR 10 sessions; net<0 → re-block**). Logged to the REVOKE surface; J's lever is revoke, not pre-approval.

**NEEDS J (explicit, no hidden ask):**
- **Alpaca OPRA data agreement re-sign.** The `/options/bars` endpoint began 403ing "OPRA agreement is not signed" MID-STUDY on both keys (worked 07-23). This is a click in J's Alpaca dashboard — Gamma can't sign agreements on his account. Until then, backfills run on the disclosed fallback (trade-print aggregation + TradingView OPRA cross-validated 3/3 vs real fills — zero synthetic in this study). Repair chip already spawned (`task_69c6e734`).
- Safe's [0,25) gate re-eval trigger stays forward-scheduled: 20 tradeable post-fix events or 2026-08-08, whichever first. Nothing for J to do — just visibility.

Artifacts: `analysis/recommendations/elite-bull-requal-2026-07-31.{md,json}` + prereg + tool + 15 RED-proofed guards, commit `53446011` (not pushed).

---

### Lane 2 — J-called-entries replay · **DESCRIPTIVE**

**Honest number:** J's four called entries all pay in real-OPRA replay: **+$2,009 CORE / +$2,269 ZONE-RIDE, qty 3, n=4 ANECDOTE**. Tape-verified **to pennies on 3 of 4 anchors** (the lane's own headline said 4/4 — reviewer flagged the compression; e3's premarket-low read was 18 cents off, the only deviation found across two days of calls). The engine SAW every one and captured none on the cores.

- Entry timing for e1/e2/e4 is hindsight narration — this is what J's stated entries pay, **not a validated policy**. e3 is the exception: the engine passed 11/11 LIVE and a fleet arm took it for real money.
- Reviewer flagged the e2 ZONE-RIDE cell (+$914) as convention-sensitive: under 1-min/touch sampling it lands ~+$390 (ZONE total ~+$1,745). Directional conclusion unaffected — all four profitable under any convention (MFE 221–434%, worst MAE −22.6%).
- One mechanism explains all four misses: **defended touch of a persistent w5 shelf, entered on the defense instead of the late close-cross.** The `shelf_hold_reclaim` spec is written and handed off — w5-anchor scope, 3 admission geometries (2 already built shadow-only and LIVE-fired at J's exact moments), F5/F8/F10 demoted to pre-reg axes, CONTROL-vs-ZONE-RIDE exit A/B. Not implemented in-lane, per charter.

**Ships this weekend:** nothing armed (n=4 anecdote). The pre-registered full-population `shelf_hold_reclaim` study goes on the weekend grind (item 4 below). **NEEDS J:** nothing.

Artifacts: `analysis/deep-research/J-CALLED-ENTRIES-2026-07-31.{md,json}` + replay tool, commit `1888ccfd` (not pushed).

---

### Lane 3 — Formalize level persistence · **DESCRIPTIVE**

**Honest number:** **17/20 of today's levels chain back through 07-29 to 07-28**; in the 390-day replay the level-tied money concentrates on touch-validated zones — **$108/trade WR 0.50 (n=54) vs $25/trade WR 0.29 fresh (n=7)**; static structural levels $198/trade WR 0.62 (n=37, POST-HOC). Sums to the PNL-ATTRIBUTION level-tied +$6,894.85 to the cent. **No cell is BH-significant** (18 tests, q=0.10; min p 0.178) — directional confirmation of J's "same levels" thesis, not proof.

- The tiny FRESH cohort is itself the finding: genuinely fresh levels barely exist among level-tied entries. But reviewer named two confounds the doc under-stated, carry them forward: (1) round numbers are stripped from prior-day match sets but not from trade triggers, tilting integer-level trades toward FRESH — the contrast partly measures level TYPE, not persistence; (2) Part-1 continuity has no null baseline — v2 shelves come from overlapping trailing windows, so day-over-day self-match is substantially mechanical.
- The lived validation stands anyway: J's 737.68 call = our `SHELF_737.05_738.65` (27 touch-bars on Thursday's tape); his 739.72 = our SHELF 739.73 (1 cent, 35 touch-bars). The dynamic aVWAP-style cohort is the drag (−$981.65/18tr) and the v2 compiler doesn't emit it.
- Weight-upgrade spec written but **NOT armed** per the frozen rule — needs its own pre-registered A/B first.

**Ships this weekend (paper autonomy):** the pre-registered touch-validation A/B (item 3), the SHADOW weight column in the v2 compiler (item 5), and the key-levels-history snapshot gap fix (07-30 missing; item 6). **NEEDS J:** nothing.

Artifacts: `analysis/deep-research/LEVEL-PERSISTENCE-2026-07-31.{md,json}` + tool + 10 guards, commit `4a281a31` (not pushed).

---

### Lane 4 — Wick-entry lane (risky arms, "get in off the wick") · **NULL**

**Honest number:** closed-bar wick-hold at persistent shelves is real as a DETECTOR (captures both of J's called incidents, guard-fixtured) but dead as a lane: **bull −$4,058.80 / 689 trades (WR 39.6%), bear −$9,286.40 / 613 trades** over 390 days, real OPRA, ZONE-RIDE exits — **every P&L gate fails**, held-out negative both directions, drop-best negative. Nothing armed. Review: SOLID, every number re-derived exactly.

- **Killer mechanism (recorded as future-prereg hypothesis only):** the entry is structurally counter-ribbon — 461/689 bull trades exit `ribbon_flip_back` at ≤5-min hold for −$7,500. Raw density 4.3 fires/day vs J's ~1/day reads: the frozen closed-bar predicate admits hover-wicks the human excludes.
- The closed-bar null does NOT kill the intra-bar shape: entry-price advantage of the live-tick variant is unmeasurable offline. Per the frozen `if_null` clause, `shelf_wick_hold_live_tick_v1` goes to **forward shadow only**.

**Ships this weekend:** $0 forward-shadow logger build (item 7). **NEEDS J:** nothing.

Artifacts: `analysis/recommendations/wick-lane-2026-07-31.{md,json}` + prereg + tools + 15 RED-proofed guards, commit `e804ed76` (not pushed).

---

## 2. J vs engine — the grade table (07-30/07-31, all tape-verified)

| # | When | J's call | Tape verdict | J | Engine saw it? | Engine did | Engine | Replay qty 3 (CORE) |
|---|---|---|---|---|---|---|---|---|
| e1 | 07-31 10:15 | Buy the 737.68 wick low | **EXACT RTH low** — our `SHELF_737.05_738.65` (w5) | **A+** | Yes — shadow `wick_reclaim` fired 10:21–10:35 | Refused: blockers {F5,F8,F10}, peak score 9–10 vs binary 11/11 bar | **F** | +$550.75 |
| e2 | 07-31 11:30 | Buy the 739.72 bounce | Low 739.81 vs our SHELF 739.73 — **8 cents** | **A** | Partially — shadow `pullback_hold` 11:41–11:45 | No trigger class exists (`level_reclaim` needs low<level<close cross; this never crossed) | **F** | +$605.85 (ZONE-RIDE +$914, convention-sensitive to ~+$390) |
| e3 | 07-31 12:16 | 743.25 reclaim (his 742.97 premarket-low read; SIP 742.79, **−18c — the only miss**) | Level was our `MEMORY_RES 742.90` / SHELF 743.25 | **A−** | **Yes — passed 11/11 LIVE** | Refused ×111 that day by `block_elite_bull` (stale old-feed evidence). Ungated fleet took it: risky-3 **+$126 real**, safe-3 **+$75 real** | **D** | +$330.40 |
| e4 | 07-30 (blind day) | Four beats, all verified | All four confirmed on SIP | **A** | No — `levels_active` empty 776/796 rows | Wrong-way ENTER_BEAR near the low, **−$275 broker-true** (root cause repaired: BLIND-ENGINE-REPAIR-2026-07-30) | **F** | +$522.45 |
| | | | **Totals** | **4/4 paid** | | Core capture: **0/4**. Fleet caught e3 — the week's first green day (+$120.48 real) | | **+$2,009 / +$2,269** |

**The pattern:** J isn't beating our levels — he's trading them. Every call landed ON the file to within pennies. The gap is 100% on the trigger/gate side: one score bar (e1), one missing trigger class (e2), one stale-evidence gate (e3), one blind day already repaired (e4). e3's fix ships this weekend; e1+e2's fix is the `shelf_hold_reclaim` study.

---

## 3. Graveyard additions

One lane nulled — add to the do-NOT-retest list:

- **Shelf wick-hold, closed-bar predicate, under ribbon-clause exits (ZONE-RIDE/`ribbon_flip_back`)** — NULL both directions over 390 days (bull −$4,059/689tr, bear −$9,286/613tr, all gates fail, held-out negative). Frozen production wick constants, zero tunables, zero sweeps — this is the mechanism's honest read, not a bad parameterization. Escape hatches, BOTH requiring a NEW frozen prereg before any run: (a) `shelf_wick_hold_live_tick_v1` forward shadow only (offline untestable); (b) displacement-qualified wicks + zone-referenced non-ribbon exit — noting (b) is exit-graveyard-adjacent and gets extra scrutiny at prereg.

No other lane produced a graveyard entry (lane 1 lifts a gate at the live CONTROL exit shape — not an exit retest; lanes 2/3 are descriptive).

---

## 4. Weekend plan — Saturday/Sunday, in order

**Standing process gate on ALL items (adopted from lanes 1/3/4 review findings): the frozen prereg commits BEFORE the runner exists — freeze-ordering must be git-provable, not self-attested. All timestamps via `et_clock`, ET-explicit.**

| # | Item | What runs | Gate |
|---|---|---|---|
| 1 | **Elite-bull LIFT-GATE TRIAL flip** (Sat, first) | Conductor applies `block_elite_bull: false` on bold-2 verbatim from `elite-bull-requal-2026-07-31.json` (min size, `revert=true`), arms kill tracker, logs to REVOKE surface | Rec JSON + 15/15 guards already green; kill bar frozen: n≥10 fills OR 10 sessions, net<0 → re-block. Effective Monday open |
| 2 | **Reporting-hygiene fix** (Sat, small) | Correct the garbled 111-blocks line in lane-1 finding surfaces; add fleet-concentration disclosure (+$472 dedup / +$88 ex-07-29) beside the +$1,242 cell | Numbers must match the committed JSON artifacts |
| 3 | **Level-persistence A/B** (Sat) | Fullhist entry-layer variant: require touch-validated trigger levels for level-tied entries vs baseline (spec already written, lane 3) | Prereg committed first; 4 gates + sub-window stability; all cells reported; round-number confound named in prereg (reviewer finding) |
| 4 | **`shelf_hold_reclaim` pre-reg + full-population levels-v2-retro study** (Sat night/Sun — the big one) | Lane 2's delivered spec: w5-anchor scope, 3 admission geometries, F5/F8/F10 as pre-reg axes, structure stop at zone floor, CONTROL-vs-ZONE-RIDE exit A/B | Prereg committed first; real-OPRA only, entry+1, graveyard exclusions respected; NO wiring regardless of result — study only |
| 5 | **v2 compiler SHADOW weight column** (Sun) | Wire prior-day touches/flips/bounces into the compiler weight field as a shadow column so forward days accumulate live evidence | Shadow-only — zero change to existing weights (diff-proven); guard RED-proofed |
| 6 | **key-levels-history snapshot gap fix** (Sun) | Repair the 07-30 hole + guard so morning snapshots can't silently skip a day | Guard test; C34 check that the file is tracked |
| 7 | **`shelf_wick_hold_live_tick_v1` shadow logger** (Sun, if time) | $0 tick-path shadow logger on risky-3 per the frozen `if_null` clause | Shadow-only, no order path, fail-open, C8 spawn pattern |
| 8 | **OPRA-agreement repair chip** (`task_69c6e734`) | Blocked on J's dashboard click — chase Monday if unsigned | **NEEDS J** — the only item on this list that does |

Nothing on this list touches live money. Items 1 and 5 are the only production-adjacent edits; both are revertible one-liners with logged REVOKE entries.

---

## 5. Morning brief — 6 lines, spoken, as Gamma

1. First green day of the week — plus $120 real — and it came from the exact signal class my core accounts refused a hundred and eleven times while the loose fleet arms just took it.
2. The bull gate doing the refusing was built on 24 losing fills that ALL predate the levels fix; the post-fix replay says plus $867 on five trades, so I'm lifting it on bold-two at minimum size this weekend — paper only, tight auto-re-block if it reads negative, and your lever is revoke.
3. Your four calls this week all paid — three verified to the penny on the tape — and every one landed on a level already in my file; my failures were triggers and gates, not levels.
4. That's the weekend's real work: a pre-registered study of entering on the defended touch of a persistent shelf, the way you actually trade it, instead of waiting for a late close-cross.
5. The wick-entry idea you asked about tested honestly dead offline — minus four thousand bull-side over 390 days — so it goes to the graveyard, and only a live-tick shadow version gets a forward look.
6. One thing needs your hands: Alpaca wants the OPRA data agreement re-signed on the dashboard — two of my data pulls are running on fallbacks until you click it.

---

*Synthesist note: all four lane reviews confirmed the load-bearing numbers by independent re-derivation; zero refutations. Lane commits `53446011`, `1888ccfd`, `4a281a31`, `e804ed76` — all pathspec-scoped on main, none pushed, per push discipline.*
