> **Provenance.** 36-agent workflow (`gamma-day-deep-review-2026-08-13`), 7 independent angles,
> every finding adversarially verified by a separate reviewer before inclusion.
> **16 findings survived, 12 were killed.** 4.93M subagent tokens, 770 tool calls, 37 minutes.
> Read-only: nothing was armed, changed, or ordered.
>
> This SUPERSEDES the headline of the solo review in `FULL-TRADE-REVIEW-2026-08-13.md`, which is
> retained for its per-trade forensics. See "THE FRAMING CORRECTION" below.

# FULL TRADE REVIEW — 2026-08-13
### Seven-angle synthesis, adversarially verified. Read-only. Nothing was armed, changed, or ordered.

---

## THE FINDING

**Five arms run five different entry-gate sets, and no inventory exists of which gate is armed where. Uninventoried gate coverage moved $942 today — 29% of the day's $3,286 gross — in two opposite directions, neither of them intended.**

| Gate | Armed on | Fired at | Effect today |
|---|---|---|---|
| `block_bull_1100_1200` | **safe-2 only** (`params.json`, ratified 2026-06-18) | 11:41 ET — safe-2 logged `SKIP_BULL_1100_1200` | bold-2, safe-3, risky-1, risky-3 lacked it and took the signal: **−$410** (53% of the day's total losses) |
| `block_conf_lvl_rec_afternoon` | **bold-2 only** (`aggressive/params.json`) | 14:36 ET — bold-2 logged `SKIP_CONF_LVL_REC_AFTERNOON` on trig 777.17, bull_score 11, tier ELITE | blocked bold-2 out of the day's **+$532** winning event. Its own provenance doc reads *"KEPT but DEAD (0 impact in all contexts): $0 delta in all 6 WF folds and 4-way A/B."* It was not dead today. |

**Do not promote either gate on this evidence.** Run BOTH already-ratified time-of-day gates across all five arms and the day is `+410 − 532 = −$122` **worse** than what actually happened. Picking the gate that landed on today's loser and ignoring the one that landed on today's winner is post-hoc gate *selection*, and it voids the "already ratified, therefore legitimate" argument entirely.

**The action is the inventory, not the promotion.** Tonight's deliverable is a gate × arm coverage matrix — which named entry gate is armed on which of the five arms, with each one's provenance and last-retest date. That question was asked implicitly four times across seven analyst angles today; it is a missing instrument, not a query.

---

## THE FRAMING CORRECTION THAT GOVERNS EVERYTHING BELOW

**There were not 15 trades. There were 5 signal EVENTS, mechanically fanned across arms.**

| Event | ET | Trigger | Arms | P&L |
|---|---|---|---|---|
| A | 09:51–09:52 | 776.85 | 5 | **+$1,985** |
| B | 10:27 | 778.96 | 1 | −$90 |
| C | 11:41–11:42 | 775.73 | 4 | −$410 |
| D | 12:41 | BEAR trendline | 2 | −$269 |
| E | 14:36–14:37 | 777.17 | 3 | **+$532** |

Sums to +$1,748 exactly. All five events are sign-homogeneous, so **8W/7L IS 2W/3L.**

Proof it is mechanical, not five decisions: all three fleet arms entering at 09:52:04 carry `core_tick_id = 2026-08-13T09:51:02.924807` — the same core tick that fired at 09:51:03.

Three numbers that must travel with every conclusion from this day:

- **Event A alone is +$1,985 = 114% of the day's net.** Ex-A, 2026-08-13 is a **−$237 losing day.**
- The brief's headline separation ("all 8 winners hit +25%, zero overlap") is Fisher **p = 0.000155 at n=15** and **p = 0.100 at n=5.** Not significant at α=0.05.
- The winner half of that separation is near-tautological: minimum winner *realized* return is **+46.77%**, and realized ≤ MFE by construction. The only empirical content is the loser side (max loser MFE **+23.71%**, bold-2 in event C), which comes from **3 events.**

**n = 1 day. Everything below is a hypothesis. Nothing here is a validated edge, and no cell in this review was profitable — every counterfactual is a price path with no spread, no queue, and no partial-fill model. Excursion is not P&L.** That is stated once; it applies to every line.

---

## RANKED FINDINGS
*(dollars today × confidence × cheapness to test)*

### 1. Gate coverage is uninventoried — build the matrix
**$942 touched · high confidence · free tonight**

Verified above. Supporting forward evidence for `block_bull_1100_1200`, correctly attributed:

- Fired on 3 days since 07-01 (07-10 ×6 ticks, 08-04 ×6, 08-13 ×3), **safe account only**, representing **5 bar-level episodes.**
- On the 2 days where ungated arms placed anyway, **16 fills across 3 episodes all lost: −$964** (08-04 −$554, 08-13 −$410). 07-10's 2 episodes produced no fills — unmeasured.
- **The "19 fills, 19 losers, −$1,292" framing is wrong twice.** 07-28's −$328 belongs to a *different* gate (`block_elite_bull`, verdict `SKIP_ELITE_BULL_LEVEL_RECLAIM`); `block_bull_1100_1200` never fired that day. And the fills are the same 4 bars multiplied by arm count and consecutive 1-min ticks at a frozen SPY price (767.745 / 768.64 / 775.99).
- Correct unit: **3 losing episodes of 3 measured, p = 0.125** under a coin-flip null. Directionally supportive. Not significant.
- Gate provenance is thin: IS n=11 totalling **−$89**, OOS n=1, filed caveat *"signal is IS-dominant."* Last formal retest, commit `04199b32` (2026-07-22): **RETEST-INSUFFICIENT-N.** The −$964 is ~11x the entire IS effect and is a sizing artifact of 5–10-lot arms at $5,501 equity, not a stronger signal (C31 axis).
- The 11:00–12:00 boundary is **not discriminated** from midday chop or Nth-signal-of-day: the window catches only 4 of 7 losers; the 10:27 and 12:41 losers fall outside it; the 14:36 re-entries won.

### 2. The five-arm book is ONE bet — stop counting it as five samples
**Not P&L; a risk and evidence-weight finding · high confidence · free tonight**

- Grouping the 15 trades by entry minute explains **95.3%** of realized-return variance (η² = 0.9532 on `cap`). Compare: AM/PM η² = 0.0046, call/put η² = 0.2645. Permutation p = 0.00005 over 20,000 shuffles.
- **ICC(1) = 0.95** [95% CI 0.786–0.994]. All 20 co-traded arm pairs shared P&L sign.
- **Arm identity explains nothing.** η²(ARM) = 0.100, *below* the 0.286 a random 5-way split produces by chance. The "safe vs bold vs risky" distinction — the entire premise of the 5-arm grid — is empirically empty on this day.
- Robust: leave-one-trade-out 0.949–0.980; leave-one-cluster-out 0.927–0.978. `cap` is realized return off actual fills, not excursion.
- **Correction to the risk number:** "$5,342 deployed, 1.95x stacking" sums five time-separated windows as if simultaneous. **Peak concurrent notional was $2,041** (38% of that), and inside the actual overlap window the stacking factor was **2.18x**, not 1.95x. A book-level concurrent-notional cap cannot be sized off a non-concurrent aggregate — re-derive it against peak overlap before proposing any number.
- **This is not new.** `markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md` §3.1 established "one bet sized three ways" a month earlier on a multi-day window, and already logged tighter book-level cuts as an open fork for J. **Fold this day in as confirming evidence; do not open a parallel doc.**

### 3. The fleet CAN enter where production refuses — the docstring is false
**−$325 today · high confidence · free tonight**

- `build_shared_signal.py` docstring: *"an arm can only filter production's signal further, never enter when production held."* **This is a stale v1 note, contradicted 750 lines lower in the same file.**
- `passed_scoring_peak` (line 771) sets passed=True when score ≥ `BULL_PEAK_THRESHOLD = 9` with a fired trigger **regardless of production's verdict**. `SCORING_PEAK_LIVE = True` since 2026-06-25. Exactly ONE verdict hard-blocks (`SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`). Three further producer-side rescue lanes are live (probe, full_send, score-ladder).
- The file's own comment states the intent: *"a genuinely-looser arm is NOT representable downstream and must be a producer-side lane."*
- **Proved today:** at 11:41–11:43 safe returned `SKIP_BULL_1100_1200` and took nothing; safe-3, risky-1 and risky-3 all entered at 11:42:05 for **−$325** = 42% of the day's losses.
- Consequence: fleet risk is **not** bounded by production's gate perimeter. Any reasoning that assumes it is, is wrong.

### 4. `conviction.py` is unsatisfiable in production — DO NOT ARM, and repair the instrument
**$0 realized; −$693 to −$1,748 attached to the arm decision · high confidence · cheap**

- `would_block = True` on **41 of 41** core ENTER rows. Totals distribution `{0:6, 3:14, 4:21}` — max 4 — against `effective_floor(k) = 5 + k`.
- **The gate is mathematically unsatisfiable.** Only 3 of 7 components ever scored: named_level (2 pts) + fresh_test (1) + elite_trigger (1) = ceiling **4 < base floor 5**. `degraded_components = ["range_extreme","structure"]` on 41/41. C5 is degraded by design (`structure_side=None`, "not yet threaded off engine_cli"); C4's degradation is unexplained and kills the component the module's own docstring calls the discriminator.
- **The ordinal ratchet is therefore untested, not tested.** Sweeping `DEFAULT_RATCHET_STEP` from 0 to 99 leaves 41/41 blocked. The step term could be deleted and zero decisions change. **Record 2026-08-13 as a non-observation for ordinal escalation** — neither support nor refutation.
- **Arming at shipped defaults blocks all 6 core trips**: +$1,047 winners vs −$354 losers = **−$693**, the core arms' entire net. And since fleet signals derive from core, a core `SKIP_LOW_CONVICTION` emits no shared signal — plausibly **−$1,748**, the whole day.
- **Three defects, all cheap:**
  - **k mis-keyed.** `heartbeat_core.py:510-511` hardcodes `STATE/"settlement-ledger.json"` for both accounts, while the live risk gate at `:2093` already uses `_sl.ledger_path(STATE, account)`. `_conviction_shadow(verdict, bc, account)` **already receives `account` and never uses it** — one-line fix. Today bold logged k=1 at 09:51:06 on its own first entry, reading safe's counter.
  - **Fleet coverage zero.** safe-3 / risky-1 / risky-3 logged 384 rows each with the `conviction` key absent entirely — **0 of 1,152.** 9 of 15 trips and $1,055 of the day's P&L are uninstrumented.
  - **Four dead components**, especially C4 `range_extreme`.
- Ordinal signal itself was null on the 6 instrumented trips: winners at k = 0,1,2; losers at k = 1,1,2. safe-2's own sequence (+332 / −69 / +181) contradicts "later = worse"; bold-2's (+534 / −85 / −200) supports it.

### 5. Strike cannot be ranked without pinning the exit's NUMERIC parameters
**$265 verdict spread on one signal pair · medium-high confidence · free (a prereg rule)**

- At fixed R=$500 on the 09:52 pair (777C ATM E=1.03 Q=4 vs 779C OTM E=0.36 Q=13): hold-to-10:42 gives **OTM +$231**; a cost-recovery ladder gives **ATM +$34**. Both reproduce exactly.
- **The mechanism is NOT "strike × exit rule."** The ladder's recovery target `r` is a deterministic function of Q via `ceil(Q/(1+r))`, and Q is a deterministic function of strike at fixed dollar risk. The rule silently applied **r=34% to the 4-lot ATM cell and r=20% to the 13-lot OTM cell.** Harmonize r over the legal common domain [34%, 50%] and **OTM wins 17 of 17.** At r=35% both cells: ATM +$232 vs OTM +$295.
- This is a recovery-target-height effect surfacing through **integer quantization at small Q** — not a property of strike.
- **The prereg gate that follows:** any future strike A/B must pin recovery target, runner fraction and exit clock **identically across strike cells**, and must report the runner fraction *actually achieved after integer rounding*. A strike × exit CROSS does **not** fix this — it reproduces the same confound.

### 6. risky-3's arm P&L must never be read as a strike result — and the confound flatters it
**Removes a number · high confidence · free**

- risky-3 is the only arm on a hard premium stop: `accounts.json` arms[5] `exit_patch = {stop_mode: premium}`, resolved to −20% by `strategies.py:131`, and posted per-trade in its own ledger (`"stop_display":"0.30 (-20%)"`). All four siblings post `stop_mode=structure`.
- **The confound runs opposite to intuition.** Held to the siblings' exit rule, risky-3 does *worse*: trade 9's siblings exited at 15:56–15:57 when 778C printed 0.19 vs risky-3's 0.24 fill (10 lots, −$130 vs −$80 — the stop **saved $50**). Trade 6's 781C never printed above 0.26 after 14:41, so no later exit could beat the 0.27 fill. De-confounded, risky-3 falls from **+$196/18.85%** to **+$146/14.04%** or **+$36/3.46%**.
- Four confounds, not three: different stop mode, different signal mix (missed the 14:36 winner, took a solo 10:27 loser), different qty rule (`cheap_contract_qty_boost` → q=10), and **n=3 with a single +$366 winner = 187% of its net.**
- "Lowest ret/$ of 5 arms" is decided by **16 basis points** over bold-2 (18.85% vs 19.01%) on n=3. Noise scale.

**Arm totals — an accounting fact, never a ranking:** safe-2 +$444/$696 (63.79%) · safe-3 +$457/$861 (53.08%) · risky-1 +$402/$1,435 (28.01%) · bold-2 +$249/$1,310 (19.01%) · risky-3 +$196/$1,040 (18.85%).

### 7. %-gate semantics vary with contract PRICE — measured, but nothing to act on
**$0 attributable · medium confidence · pre-register only**

- Median intra-minute (hi−lo)/last, 09:52–10:42, 51 minutes each: 776C **5.65%**, 777C 7.38%, 778C 9.50%, 779C 11.11%, 781C **15.38%**.
- **It is a price effect, not a strike-distance effect.** Pooling 24 (strike × window) cells: log(noise) vs log(price), **r = −0.887**, slope −0.315. Cells at similar price match across strikes (776C @0.92 → 10.43% vs 779C @0.82 → 11.11%).
- **Unstable within the same day**, 1.9–3.3x: 776C 5.46%→10.43%, 781C 15.38%→50.00%. Same-strike time variation ≥ the 2.72x cross-strike spread. A calibration fit in one window is wrong by ~2x in another window of the same session.
- **No gate is shown to have misfired.** The chandelier arms **post-TP1 only** (`exit_manager.py:182/:453/:621`, `arm_scope` default post_tp1). All 7 losers exited in a single full-size fill with no TP1 partial → **the chandelier armed on zero losers and cost $0 of the −$769.** The "0.97 noise-widths at 781C" figure is void: it compares a post-TP1 gate to noise measured at the pre-TP1 price (at TP1=0.72 implied noise is ~11%, i.e. ~1.4 widths).
- Residue: already repo doctrine (C29; "sub-$0.20 premiums = %-stops reading spread"). This session supplies a first measured elasticity. Nothing more.

---

## KILLED — do not resurrect

| Killed claim | Why |
|---|---|
| **"Promote `block_bull_1100_1200` fleet-wide — this is the prize"** | Post-hoc gate *selection*. The fleet's other ratified TOD gate (`block_conf_lvl_rec_afternoon`) blocked a **winner** today; both universal = **−$122 vs actual**. Nothing pre-fill distinguishes the 11:41 loser from the two winners except the clock (all three: score 11, ELITE, ribbon BULL, htf BULL, VIX 14.4–14.7). |
| **"76% of the exit-grid gain is a SIZING effect"** | There is **no sizing change at all**: 78 contracts and $5,342 entry debit in both worlds. Isolating the split with times frozen caps at **+$90** across the whole fraction axis — the claim's +$978 is ~3x its own mechanism's ceiling. The runner sweep silently restarted the clock at TP1 instead of entry and booked the difference as size. |
| **"Prior 250-signal study refutes tight stops"** | Misquotes the source (STOP-A actually says *"the cheap <$0.20 band wants a MODERATE −25/−30% stop, not none"*), argues against a **retired** −20% baseline (live is −50% since 2026-06-18), and this repo has a **ratified tightening that won** (`tighter-stop-01.json`, OOS delta 1801.7, WF 3.37, IMPLEMENTED). Six of its eight winner-drawdown figures were wrong, all understated. |
| **"Confirmation-gated adding: losses EXACTLY unchanged, drawdown invariant"** | Trade 7 missed confirming by **1.25 cents** on a $0.01-tick contract. One tick better on entry and it confirms: −$85 → −$880, worst-arm DD 5.7% → 21.7%, and the "invariant across the ladder" claim is false at every rung. Separation is decided by entry-fill luck (bold-2 filled 0.97 vs safe-3/risky-1 at 1.13/1.14 on the same contract). |
| **"Probe-then-commit — scale 4x with the loser bucket pinned"** | Arithmetic error: the add leg was scaled as `k×q` instead of `k×(q−1)`, double-counting the probe contract. True slope is $1,202/k, not $1,585/k — headline uplift **33% too large**. Also triggers and fills on the same minute's `hi` (look-ahead); honest next-poll fill drops the add leg 16%. |
| **"Staggering arms is a NULL for P&L"** | Not a null — a **zero-power test**. No scenario at any k was negative on this tape, so P(day<0)=0.0% ranks nothing; the worst k=1 case clears zero by $39 (2.2%). The round-robin leg is an identity: the five offsets sum to exactly $1,748 by construction. **Drop event A and the sign inverts** (k=1 −$149.7 vs k=all −$237.0 — staggering would have *helped* by $87). The conclusion "don't build rotation" stands; the evidence does not. |
| **"Don't buy an option trading below where it was 15 min ago"** | Not zero-parameter (plateau is N=15–21; at N≥22 the lookback precedes the open and the entire morning winner cluster is *undefined*, not passing). Contains zero option-specific information — sign matches SPY 15-min momentum on 15 of 15. Theta does the separating on 0.005–0.023% underlying moves. **The engine already killed this gate class**: `min_ribbon_momentum_cents = null`, disabled 2026-07-08 because *"the residual gate removed a NET +585 cohort... big down-day puts matching J edge signature"* — precisely today's event D. And on its own day it is beaten by "skip 10:00–13:00 ET" ($2,517 vs $2,427). |
| **"Reclaim re-entry loses money robustly"** | The sweep never varied the knob that sets the sign. Remove the +25%/6-min confirmation gate — a strictly simpler rule using strictly less information — and every cell flips positive on the same data. What was shown negative is the *gate*, not the reclaim. **File as NON-RESULT, not NEGATIVE RESULT** — otherwise the next session tests the obvious variant, gets the opposite answer, and builds the thing. |
| **"Scout-and-follower staggering loses at every lag"** | Followers charged the minute **HIGH** (100th percentile); the 15 real fills sat at median 0.75 of their own minute range. Change only the fill to LAST and −$157 → −$31; enter on the scout's actual confirmation minute and the sign goes **positive**. At L=4 and L=5 no follower ever enters, so the dramatised "−$1,479" is a never-follow cell, not an entry-price cell. |
| **"ATM-beats-OTM by $47.96/tr is a hidden per-contract artifact"** | The live book does **not** size by dollars — `heartbeat_core.py:2176` is literally `qty = int(params.get("min_contracts", 3))`, and today every arm held contract count constant across a 3.5x premium range. The deflator was cherry-picked below P25 of its own file (median 4.64 flips the sign). The convention is **disclosed** in `disclosures[8]`, not hidden. And the claim's own $480 baseline commits the exact unit error it alleges, inflated ~11x. |
| **"No arm generated an independent signal today"** | Counts entries only. **Six independent declines while flat** exist, none capacity-blocked, fencing off **−$679 of the day's −$769** (88%) — versus the −$90 the claim generalized from. Also misidentifies the 10:27 signal as a stale re-fire (different trigger bar, level advanced $2.11) and calls it a fade (SPY made its high-of-day 13 minutes *after* entry — the real mechanism is C3). |
| **"Arming conviction would have cost −$693"** | Scope error worth $1,055: fleet signals derive from core ENTER ticks via `core_tick_id`, so a core block kills the fleet trips too — the figure is **−$1,748**, the whole day. Also 125% of the −$693 is one 2-second, one-contract cluster; remove it and the gate *saves* $173 on the other four. (**The action — keep it disarmed — is still right**, for the reasons in Finding 4.) |

---

## WHAT TO DO TONIGHT
*Cheap, read-only, pre-registerable. This review changed nothing; each item below is a filing or a spec.*

1. **Build the gate × arm coverage matrix.** Every named entry gate × 5 arms, with provenance file, ratification date, last retest verdict, and current armed state. Sources: `params.json`, `aggressive/params.json`, `fleet/accounts.json` `params_patch`. This is the #1 finding's deliverable and it is a pure read.
2. **Correct the false guarantee in `build_shared_signal.py`'s docstring** — file the correction; the code (`passed_scoring_peak`, `SCORING_PEAK_LIVE=True`, probe/full_send lanes) has contradicted it since 2026-06-25 and it is actively misleading risk reasoning.
3. **Stamp `evidence_n = 5` on every scorecard touching 2026-08-13** — labelled as realized-outcome clusters, not signal events. Where only the loser side is load-bearing, state **n = 3**. Reporting n = 15 is a C4 disclosure failure.
4. **Annotate `FULL-TRADE-REVIEW-2026-08-13.md` §5c**: "worst-case ordering DD" is not an observed drawdown — it is `sum(losses)/equity` under a reordering that did not happen, i.e. a deterministic function of total losses. On n=1 with known outcomes it is indistinguishable from fitting to which trades lost.
5. **Pre-register the strike-A/B pinning rule** (Finding 5) as a gate on the next strike prereg: exit numeric parameters pinned identically across cells; report achieved runner fraction after integer rounding.
6. **Write the conviction repair spec** — per-account `k` via `_sl.ledger_path(STATE, account)` (the param is already in the signature), C4/C5 threading, fleet instrumentation — and record explicitly: **DO NOT ARM.** Any future "Nth trade of day" prereg cites `conviction.py#effective_floor` as prior art *and* records 2026-08-13 as a non-observation.
7. **File the exit-axis kills** so nobody re-runs them: trailing null, fixed-stop-only destructive, time-stop disqualified, reclaim = NON-result.

---

## WHAT NEEDS MORE DAYS

- **Does `block_bull_1100_1200` belong on the other four arms?** n=3 episodes, p=0.125, ratified on IS n=11 totalling −$89, last retest INSUFFICIENT-N. Needs a per-arm A/B on each arm's own real-fills history, and needs the 11:00–12:00 boundary discriminated from midday chop and from Nth-signal-of-day.
- **Is `block_conf_lvl_rec_afternoon` actually dead?** Its doc claims $0 delta in all 6 WF folds and a 4-way A/B. It blocked a live winner today. A knob mis-labelled dead is C14 in its purest form.
- **Is the +25% / 4–6 minute confirmation separator real?** p=0.100 at event level; the winner half is tautological; the loser side is n=3. It is also partly measuring **entry slippage**, not signal quality — event C is one price path peaking at 1.20 entered at 0.97 / 1.13 / 1.14, giving MFE +23.7% / +6.2% / +5.3% purely from a 17.5% entry-price spread.
- **Is confirmation-gated adding safe?** Zero observations of confirm-then-reverse. Trade 7 missed confirming by 1.25 cents. The measured add multipliers are 4.0x–7.7x base size — squarely C31 territory.
- **Does the ordinal ratchet do anything?** Unanswerable until the instrument is satisfiable and covers all five arms.
- **What is the right book-level concurrent-notional cap?** Peak concurrent today was $2,041 at 2.18x stacking, but Rule 6's per-account caps (30% Safe / 50% Bold) do not compose into a book cap at ρ≈0.95. Needs peak-overlap measured across many days, and it re-opens a fork already logged for J.

---

## NULLS — checked, found nothing. Do not re-run these.

**Entry anatomy — the engine's own quality fields separate NOTHING**
- `bull_score`: **11 on all four bull events**, winners and losers alike. Hard-capped at 11 (max across all 24,049 core rows since 07-01); ENTER_BULL takes only {10, 11}, 250/300 = 83.3% at 11. Of 22 ENTER_BULL placements since 07-01, 18 were at 11 and all 4 at 10 fall on one day. **Cannot be re-thresholded — there is no headroom.**
- `quality`/tier: **ELITE on 903 of 903** fleet BULLISH_RECLAIM_RIDE_THE_RIBBON rows since 07-01. A literal constant with zero variance ever recorded.
- `reason` string: byte-identical across winning and losing core bull placements.
- `risk_code = ALLOW` on all placements — **tautological**, ALLOW is a precondition for a fill. Population-wide it varies (152 ALLOW of 903).
- `htf_15m = BULL` on all 15 fills including the two puts taken against it.
- `conviction.total`: 4(W) 4(L) 3(L) 0(L) 3(W). Overlaps completely; only ==0 isolates anything, and that is redundant with `matched_level_label == null`.
- EMA ribbon width, NBBO spread (0.00–0.12, uncorrelated), `sight_check` (all fresh), `free_eval` (disabled 2026-08-12 — no model veto existed today, cannot be credited or blamed), equity at entry, entry premium, matched-level source type, intraday re-trigger count: **all null.**

**Exit grid — every mandated axis**
- **Trailing stops (axis c): NULL.** 15/25/35% = $769 / $1,763 / $1,233 vs actual $1,748. Best cell **+$15** at slip 0.02. The 20–30% band is a genuine plateau ($1,648–$1,796) and **the live chandelier already sits inside it.**
- **Fixed premium stops standalone (axis a): NULL and destructive.** −20/−30/−40/−50% = −$468 / −$930 / −$639 / +$165. All four lose $1,583–$2,678 vs actual. With no target and no clock they ride winners from the 10:32 peak all the way down.
- **Time stops standalone (axis b): no usable signal.** The full curve is not monotone and not a plateau: 10m 1,125 → 15m 895 → 20m 1,347 → 25m 1,145 → 30m 2,203 → 35m 2,214 → 40m 2,661 → 45m 2,740 → 50m 2,163 → 55m 1,174 → 60m 596. **±$1,000 on 5-minute steps.**
- **The "best cell" (stop-20 + time-45m, +$1,295) is a fitted point, four ways.** 777C peaked at 2.70 at 14:32 UTC — **41 minutes after entry**; the argmax clock IS the time-to-peak of the one contract supplying the gain. 82.3% of the delta is event A (ex-A residual −$74). Moving 45m→55m inverts the sign (+$992 → −$574, 158% of the gain). Slip: +$1,295 @ $0.02, +$671 @ $0.10, **−$109 @ $0.20**. And paths truncate at 15:13 ET, so trips 13–15 never reach the clock and every hold-to-end terminates ~42 min before the real 15:55 flatten.
- **Time stops HARM the losers at every N from 15 to 60** (actual −$769; N=45 −$902; N=35 −$1,262). They cut no losses here — 100% of apparent value sits on the winner side.
- **Runner management: NULL for every stop and trailing variant.** Trail 10/15/20/25/35% all underperform actual (−$74 to −$184); stop-on-runner catastrophic (−$938 to −$1,170). **The existing scalp-plus-trail shape was close to the best available management of the runner leg on this day.**
- **Stop level as winner protection: not binding.** Paired with any ≤30-min clock, stops at −15/−20/−25/−30/−50% leave the 8 winners at exactly $3,316 and bind on **zero** of them. Worst winner excursion was −13.89% in the first 60 minutes.
- **Leave-one-episode-out: no cell survives.** Excluding event A, the top cell falls +$3,043 → −$8 and actual falls to −$237.

**Sizing**
- **VIX-scaled sizing: dead knob.** Full-day VIX range 14.41–14.74 (2.3%). Inverse-VIX returns $8,664 vs $8,688 flat = −0.3%.
- **Inverse-volatility sizing: strictly worse than doing nothing.** Inverse premium-vol $7,548, inverse SPY-30m-vol $1,490 vs $8,688 flat. The latter also breaches bold-2's 50% kill switch (−59.0%) uncapped.
- **Direct-vol sizing as a RISK dial: refuted, not merely null.** A trivial clock constant (w=1.0 before 10:00 ET, 0.35 after, **no volatility input at all**) beats it on drawdown for all five arms *and* on return. Leave-one-out of event A zeroes the DD improvement on 3 of 5 arms exactly. And the DD reduction is bought by under-sizing a winner — the 14:36 event had the session's **lowest** SPY 30-min realized vol.
- **The $19,983 headline: artifact.** One cluster contributes 104% of it and it requires 64–81% of arm equity in a single trade.
- **Time-of-day as a generalisable sizing curve: contradicted by the only n>1 data available.** J's 667-trade ledger has the 09:30 bucket at −$30.87/PF 0.66 (n=164, his *worst*) and the 11:00 bucket at +$28.79/PF 1.45 (n=63, one of his best) — the exact inverse of today's shape.
- **Liquidity feasibility of large confirmation adds: UNVERIFIED.** `_today_bars.json` is empty for all six contracts (options bars endpoint returns 403, OPRA agreement unsigned). Stated as unknown, not as acceptable.

**Correlation / structure**
- **No natural hedge exists to measure.** 0 of 140 open-position minutes had any arm holding the opposite direction. The "arms partially offset" hypothesis is **refuted**, not merely unsupported.
- **Different strikes are not different bets.** Minute log-return correlations: 0.972 (777/776), 0.905 (777/778), 0.890 (776/778), 0.767–0.785 (779 vs rest). The only decorrelated contract (781C at 0.18–0.26) is decorrelated because it is thin, not because it expresses a different view.
- **Intra-signal dispersion is exit timing, not selection.** No arm ever differentiated itself by picking a different signal.
- **Decline skill unmeasurable at n=6.** Every decline traced to a mechanical gate (clock window, trigger count, premium floor, late-entry ceiling) — not one was an assessment of the signal.

**Timing / ordinal**
- **Book-wide signal ordinal: null.** Sequence W L L L W — the *last* signal of the day was a winner, so "take only the first N" has no stable cutoff (first-1 +$237, first-2 +$147, first-3 −$263, first-4 −$532 vs actual).
- **Monotone per-arm ordinal: refuted.** Ordinal-3 (3/5 wins, +$252) beat ordinal-2 (0/5 wins, −$489). "Block ordinal ≥3" would have been −$252 worse than nothing.
- **Same-bar cooldown: null**, reproducing the 2026-08-06 DO_NOT_ARM. All successive entries carried strictly advancing `trigger_bar_et`. Note: safe and bold both entered on the same 09:45 bar — a cross-arm version would have blocked one of the two biggest winners.
- **Clock cooldown ≤30 min: mostly null.** Only 1 of 5 ordinal-2 entries (23.0 min, −$90) falls inside the tested grid; the others sat 59.0, 60.0, 60.5 and 119.0 minutes out.
- **Ordinal as an increment over time-of-day: zero.** The clock cut is a perfect separator today, so ordinal adds nothing it doesn't already capture, and costs the +$532 afternoon cluster.

**Strike**
- **Stop-survival race: no signal.** From the 09:52 entry all five call strikes reached +30% before touching −25% or −50%; 776C at 10:00, every other strike at 09:58.
- **Chandelier simulation: instrument invalid, not a result.** Minute-low replay exits every strike 09:54–09:56 including 777C at +4.0%, yet 777C demonstrably held live until 10:42. Minute-low print data is strictly more adverse than what the live exit_manager samples. **No strike ordering can be read off it, and I am not claiming the chandelier would have cut the winner.**
- **Per-contract dollar P&L by strike: pure artifact.** "+$45.52/contract ATM vs +$6.53 far-OTM" is the 2.9–3.5x premium ratio restated.
- **"Bought near the contract's own running high": points the wrong way.** Morning winners at 0.90–0.97x, 11:42 losers at 0.17–0.32x — it separates by time of day, not outcome. Every one of the 15 entries was below its contract's prior HOD, so "buy the new high" was never available.
- **%-gate timing advantage for OTM: null where it matters.** First-touch times are identical or 1 min *worse* for 779C vs 777C at +20/+25/+30/+40/+50%. OTM only led at +100%.
- **Execution-dispersion penalty for cheap strikes: n=4. Would not defend it.**
- **C31 not testable today.** No averaging-down, no add-after-loss, no size increase following a loss anywhere in the 15 trades. risky-3's 10 lots are a pre-registered single-entry rule, not discretionary size-up. Found no evidence for or against.
- **Running boosted-fill tally vs the n≥10 kill threshold: could not be computed.** No per-arm boosted-fill ledger exists. Open gap, not estimated.

**Outside-the-box**
- **Cross-strike gamma leadership: structurally dead.** 781C traded 0.02–0.05 all session; its per-minute `last` is unchanged across 13 of 15 entry windows.
- **Intra-minute range as a liquidity filter: no separation.** Winners 7.9–17.6%, losers 10.4–21.2%. Both tails contain both outcomes.
- **Confirmation speed as a predictor of move size: spurious.** r = +0.818 looks strong but lag takes only three values (4, 5, 6 min) perfectly confounded with cluster — all four lag-6 trades ARE event A. **Effective n = 3.** Do not derive an exit level from it.
- **Synthetic SPY from put-call parity: builds cleanly, adds nothing.** 344 contiguous minutes, ET 09:30–15:13, range 774.37–779.30, tracks the narrative correctly — and produces the exact same partition as the plain contract price. **Reported so nobody builds the parity machinery.**
- **Simultaneous-stop cluster as a regime flag: real but not incremental.** The day's only qualifying event (11:56/11:57, three arms within 60s) blocks the identical cluster two other proposals already block.
- **STACKING THE POSITIVE FINDINGS: not additive.** Multiple findings all resolve to blocking the same 11:41 and 12:41 clusters. Their dollar values **MUST NOT be summed.** Any future A/B must pick one gate per cluster-decision or it will double-count a single day's two decisions.

---

## THE THREE QUESTIONS ONE DAY CANNOT ANSWER

**1. What happens when a +25% confirmation reverses?**
Zero observations. All 8 confirmations came from 2 events and all 8 held. The entire risk of the confirmation-add family — the only sizing idea on this desk with a plausible mechanism — lives in a tail with **n = 0**, at measured multipliers of 4.0x–7.7x base size. And the separation that makes it look clean is one tick wide: trade 7 missed confirming by **1.25 cents** on a contract that ticks in pennies. We need days that contain a confirmed-then-reversed trade before any of this is knowable.

**2. Is time-of-day a real regime effect, or is it this day's shape?**
Time-of-day did suspicious amounts of work across four independent angles: it is the only feature separating the losing bull cluster from both winning ones; a bare clock constant beat volatility-scaling on all five arms for drawdown *and* return; "skip 10:00–13:00 ET" beat the best proposed novel gate on its own derivation day ($2,517 vs $2,427); and the exit grid's optimum is one contract's rally duration. On a single session, "the 11:00–12:00 window is bad" and "the midday pullback chopped and the trend resumed after lunch" are observationally identical. **J's own 667-trade ledger says the opposite** (09:30 his worst bucket, 11:00 among his best). One of those two datasets is measuring a regime and one is measuring an artifact, and one day cannot say which.

**3. What does the book's real worst case look like when five arms are one bet?**
Every event today was sign-homogeneous, peak concurrent notional was $2,041, and the day was net positive — so the correlation cost nothing and we have never observed the loss it implies. Rule 5's kill switches are per-account and do not compose at ρ≈0.95: each arm passed its own cap while the book held a single undiversified position. "Worst-case ordering DD" is not an answer — it is a reordering that did not happen, and on n=1 with known outcomes it is a function of which trades lost. **We need days where the shared signal is wrong at peak concurrency before any book-level cap can be sized honestly.**