# STOPPED-THEN-PAID — the deferred stop-noise study, finally run (2026-08-04 cohort)

**Written:** 2026-08-06, market open (`et_clock.py` -> `13:53:05 Thursday EDT`, `market_hours=True`).
Strictly read-only: no file under `automation/state/`, `setup/scripts/`, `backtest/lib/`, or any
`params*.json` was touched. New tools live under `backtest/tools/` (listed at the bottom).

---

## J's question, verbatim, asked twice, unanswered until this file

> *"the trades were labeled as stopped out and then paid... We were right. We just got stopped
> out early. Did that get the full audit and backtest? I wanted us to get into those same trades
> and then fine tune them into the point that we actually stayed in them and then profited. Did
> that occur?"*

**It had not occurred.** The hypothesis (`stop_inside_noise_floor`) auto-emitted on 07-08,
07-16, 07-21, 07-29 and 08-04 with zero converted study. This file is that study.

---

## VERDICT — one sentence

> ### Widening the stop turns 08-04's cohort from **−$1,111 into +$2,097** — a real, mechanistically-verified effect — but the IDENTICAL mechanism, on the IDENTICAL strategy, one trading day later on a reversal day, never turns profitable at any width tested (best case still **−$613**), and the 391-day population's own matching archetype (30× the sample) is monotonically worse at every width. **No single static width survives both days. The regime that decides which day you're in is not detectable at entry time — this repo already tested that classifier and it failed.** Verdict: **(b) regime-conditional, not shippable. Mark the recurring hypothesis SETTLED.**

| | 2026-08-04 (cohort's own day) | 2026-08-05 (cross-check, same mechanism) | 391-day population (gap-fade slice, n=30) |
|---|---:|---:|---:|
| live | **−$1,111.00** (cohort) / +$3,624 (whole day) | **−$1,279.00** | **−$120.10** |
| best tested width | **+$2,096.70** at −15%…−50% (cohort) / +$5,135.80 (whole day) | **−$613.00** at −20% | never — monotone worse, −$2,703.80 at −50% |
| turns profitable? | **YES** | **NO** | **NO** |

---

## 1. The cohort, RE-DERIVED from the broker (not trusted from the autopsy table)

Pulled live this session via `fleet_broker.load_creds()` + `GET /v2/orders`, all 5 arms, every
order touching strikes 762/763/765/768/769/771/772 on 2026-08-04
(`backtest/tools/_pull_08_04_broker_fills.py`, read-only). Confirmed complete: every arm's
entire day of engine activity sits inside those 7 strikes (checked with no strike filter).

**15 stopped_then_paid legs, two strategy families, real fills:**

| family | legs | contracts | actual P&L | stop mechanism |
|---|---:|---|---:|---|
| `vwap_continuation` | 5 | 762C (risky-1, risky-3), 763C ×2 (risky-3), 765C (risky-3) | **−$443.00** | premium, −6% (trigger_level is always `None` for this setup — confirmed, on every arm, regardless of exit_patch) |
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | 10 | 768C (bold-2, safe-3, risky-1, risky-3), 769C gen-1 (same 4), 772C (safe-3, safe-2) | **−$668.00** | structure (trigger_level populated — cross-verified byte-identical across 3 independent arms' own `decisions.jsonl`), catastrophe cap −50% |
| **total** | **15** | | **−$1,111.00** | |

Every one of these 15 numbers reconciles to the *cent* against `analysis/autopsies/2026-08-04.md`
(see §2 — reconciliation is exact, by construction, not approximate).

---

## 2. Method — and a bug this session caught in itself before reporting

Per the brief: exits are re-derived **only** through `exit_manager.plan_exit_actions` via
`backtest/lib/exit_manager_walk.walk_exit_manager` — never `simulator_real.simulate_trade_real`
(the 2026-07-09 SIM-EXIT-SHAPE-PARITY scar). Pattern copied from
`backtest/tools/exit_armscope_ab_2026_07_28.py`. Real 1-min OPRA throughout (not 5-min —
OPTION-BAR-RESOLUTION-BIAS-2026-08-02 under-detects intra-bar touches).

**Sequential, per arm, whole day, never recombined.** Each arm holds one position at a time
(verified empirically — zero overlapping positions across all 5 arms' real fills). Every arm's
**entire** real 2026-08-04 entry sequence (not just the 15 cohort legs) is walked as one queue.
Candidate re-entry instants are the arm's own **real** entry timestamps — LENS 5's proven
argument from the 08-05 audit, reused verbatim: a wider stop can only *delay* an exit, never
*advance* one, so the counterfactual's flat windows are a strict subset of the real ones. A
position still open at a later real entry's timestamp **suppresses** that entry — exactly the
mechanism the task brief named (risky-3's 3rd 763C entry, +$524, must not be silently destroyed).

**The self-caught bug.** An early draft re-walked the *unchanged* ("live") shape through the
harness too, instead of reading real fills directly. Point-sampled 1-min bars (bar **open**, not
a continuous NBBO feed — the documented `walk_exit_manager` convention) don't always land on the
exact historical stop-touch minute. That mismatch spuriously extended one position's modeled
life just long enough to swallow the next *real* entry — silently destroying the risky-3 +$524
winner even in the cell that was supposed to change nothing. **Caught by the reconciliation
check before anything was reported**, fixed by reading the "live" cell directly from real broker
fills (a cell that changes nothing from history must reconcile to $0.00 delta by construction,
never by approximation). After the fix:

| | n legs | max abs delta | sum actual | sum harness |
|---|---:|---:|---:|---:|
| 2026-08-04 cohort | 15 | **$0.00** | −$1,111.00 | −$1,111.00 |
| 2026-08-04 whole day, all 5 arms | 25 | — | **+$3,624.00** (known truth) | **+$3,624.00** |
| 2026-08-05 cross-check wave | 10 | **$0.00** | −$1,279.00 | −$1,279.00 |

Two independent known totals (whole-day +$3,624.00, and the WINNERS.md losers-only −$1,111.00)
both reproduce exactly. The harness is trusted from here.

---

## 3. THE CORE GRID — 2026-08-04

**Read `all_legs` as the primary number.** `cohort_legs_only` is reported too because the brief
asked for it, but it is **outcome-conditioned by construction** (these 15 legs were selected
*because* they lost) — reading it alone repeats, on the losers' side, the exact winners-only
conditioning trap `EOD-2026-08-04-WINNERS.md` already named and fixed on the winners' side.

| stop width | all_legs (25 positions, whole day) | cohort_legs_only (15 legs) | suppressed |
|---|---:|---:|---:|
| **live** | **+$3,624.00** | **−$1,111.00** | 0 |
| −10% | +$4,648.50 | +$983.90 | 8 |
| −12% | +$4,542.68 | +$878.08 | 8 |
| −15% | **+$5,151.35** | **+$2,112.25** | 11 |
| −20% | +$5,135.80 | +$2,096.70 | 11 |
| −25% | +$5,135.80 | +$2,096.70 | 11 |
| −30% | +$5,135.80 | +$2,096.70 | 11 |
| −50% catastrophe-only | +$5,135.80 | +$2,096.70 | 11 |

**Every tested width beats live. Plateau from −15% onward — the mechanism is decisive, not a
tuning knob (see §4).**

### 3a. It is not one uniform effect — decompose by family

| family | live | best width | delta |
|---|---:|---:|---:|
| `vwap_continuation` (5 legs, driven by 762/763/765C) | +$721.00 | **+$2,450.70** (from −15%) | **+$1,729.70** |
| `ribbon_ride` (14 legs incl. winners, 768/769/772C) | +$2,903.00 | +$2,685.10 (from −20%) | **−$217.90** |

**Almost 100% of the whole-day improvement is `vwap_continuation`.** `ribbon_ride` is a small
*drag* under every tested width, once winners are correctly included — its own winners lose
about $532 more than its own losers save (winners_only: $3,571 live -> $3,039 at any tested
tighter catastrophe cap). Looking at the ribbon cohort's losers alone (−$668 -> −$300 to −$354)
would say "tighten the catastrophe cap" — looking at the whole family says the opposite. **The
all-legs discipline matters, and it flips the ribbon-side reading.**

---

## 4. THE SEQUENTIAL CAVEAT — exactly what the brief warned about, plus one layer deeper

**risky-3's 763C sub-wave, real fills:** entry #1 09:50 @1.46 → stopped 09:52 (−$40) → entry #2
09:54 @1.52 → stopped 09:56 (−$144) → entry #3 09:57 @1.40 → rides to **+$524** via TP1+trail,
10:23.

**At −10% and wider: entry #1 is never stopped.** It rides the *same* move entry #3 caught in
reality, exiting via `runner_stop @2.35` at 10:23 for **+$528.80** — matching the real winner's
economics almost exactly, minus the two intervening stop-outs. Entries #2 and #3 are correctly
**suppressed** (the arm never goes flat) — the real +$524 winner does not vanish; its outcome is
captured by entry #1 instead.

**A second, deeper layer the brief didn't anticipate: at −15% and wider, an even EARLIER
position takes over.** risky-3's 09:46 762C entry (real: −$104, stopped in 1 minute) now rides
the **entire morning trend** to **+$670.00** via `runner_stop @3.00` at 10:25 — which suppresses
the *whole* 763C sub-wave (all 3 entries, winner included) *and* the 765C re-entry. This is why
every cell from −15% through −50% is numerically identical: once the stop is wide enough that the
FIRST touch of a real trend survives to the runner, widening further changes nothing — the % stop
stops being the binding constraint at all.

**The honest reading:** on a genuine one-way trend day, a tight stop does not protect against a
bad idea — it forces the SAME good idea to be re-bought several times, each time a little worse,
paying the spread/slippage tax repeatedly. A wide-enough stop lets the *first* touch of the move
be the only vehicle needed. This is real, it is not an artifact, and it is fully mechanistic —
not a coincidence of one lucky fill (contrast with LENS 1's self-flagged "−25% knife edge" on
08-05, which *was* a one-cent coincidence; this is a 39-minute survival into a documented trend).

---

## 5. THE DECISIVE CROSS-CHECK — 2026-08-05, same strategy, same harness, one day later

risky-1 + risky-3, `SPY260805C00776000`, the direct `vwap_continuation` analog of 08-04's
cohort. Re-derived independently this session (not copied from the prior hand-rolled studies —
see box below) through the *identical* harness at the *identical* widths.

| stop width | all_legs | suppressed |
|---|---:|---:|
| **live** | **−$1,279.00** | 0 |
| −10% | −$877.20 | 4 |
| −12% | −$1,046.16 | 4 |
| −15% | −$902.40 | 6 |
| **−20% (best)** | **−$613.00** | 8 |
| −25% | −$766.25 | 8 |
| −30% | −$919.50 | 8 |
| −50% catastrophe-only (worst) | −$1,532.50 | 8 |

> ### At NO tested width does 776C cross into profit. Best case is still a $613 loss.

**Same mechanism as 08-04, opposite outcome.** At −20%, entry #1 (09:58 @2.37) survives 22
minutes before finally stopping at 10:20 — suppressing all 4 later re-entries (which in reality
bled another −$400/−$658 combined). That IS the suppression benefit working exactly as it did on
08-04. The difference is what the surviving position does next: **776C never recovered**
(post-10:20 high $2.00 at 10:25 — six cents *under* the cheapest of the five real entries, $2.06;
then 0.88 → 0.35 → 0.07 → settled $0.01). Fewer, larger losses beat five smaller ones up to a
point (−20%), then the single surviving position's own loss outgrows the suppression benefit and
by −50% it is worse than live.

**A correction to the prior published finding, made honestly.** `EOD-2026-08-05-STOPS.md`'s
headline said *"a wider stop does not save these trades — it loses more, in every cell"* — a
claim that document's own adversarial review had already flagged as overstated ("monotonicity
holds at cap1 only"). This session's independent re-derivation — using the real production exit
core with full TP1/runner mechanics, which that prior study's hand-rolled `simulate()` did not
have at all — confirms the shape is genuinely non-monotonic, with a real minimum near −20%, not
a pricing-noise artifact. **The correction does not change the ship decision.** No cell is ever
profitable; the substantive verdict (do not widen this stop) is upheld and now rests on a cleaner
mechanism than before.

<details>
<summary>Why this was re-derived instead of just cited (methodology note)</summary>

`stop_width_grid_20260805.py`'s own `simulate()` function is a hand-rolled stop-or-EOD check —
it never calls `plan_exit_actions`, has no TP1, no profit-lock, no runner. LENS 1's own
adversarial review of that file flagged: *"the headline joint grid has no generating code in any
committed tool — a clean clone cannot regenerate it."* Re-deriving the 776C wave through
`walk_exit_manager` closes that gap for the vwap family specifically, and gives this study a true
apples-to-apples comparison against 08-04 (same harness, same core, same width labels).
</details>

---

## 6. THE POPULATION CROSS-CHECK — 391 days, and one honest scoping gap

`backtest/tools/stop_width_fullhist_sweep.py` (ribbon_ride, 2025-01-02 → 2026-07-22, 191 trades /
141 days) re-run this session with one added cell, −30%, via a thin wrapper
(`backtest/tools/_pop_sweep_with_30.py`) that monkeypatches the existing tool's width list at
runtime rather than editing it. Reproduces the frozen −20% baseline exactly (+$4,809 on 191
trades, matching `engine-fullhist-replay-2026-07-23.json` to the cent).

| stop | total | trend-like | chop-like | **gap-fade (08-05's archetype, n=30)** | gap-go (08-04's archetype, n=37) |
|---|---:|---:|---:|---:|---:|
| −6% | +8,036 | +3,466 | +4,504 | **−120.1** | +2,870.6 |
| −10% | +6,948 | +3,423 | +3,459 | **−367.2** | +3,082.2 |
| −12% | +6,107 | +3,201 | +2,840 | **−423.1** | +2,965.7 |
| −15% | +6,153 | +4,001 | +2,087 | **−596.1** | +2,790.8 |
| −20% (live ribbon fallback) | +4,809 | +3,903 | +840 | **−884.4** | +2,911.1 |
| −25% | +4,060 | +3,444 | +550 | **−1,172.6** | +2,670.3 |
| **−30% (NEW this session)** | +4,521 | +4,012 | +443 | **−1,460.8** | +2,777.7 |
| −50% | +2,176 | +4,534 | −2,423 | **−2,703.8** | +3,686.0 |

**The gap-fade column is the load-bearing one, and it is cleanly monotone — −120 → −2,704 across
the whole grid, no exceptions.** The new −30% cell (−1,460.8) sits exactly where a straight
interpolation between −25% and −50% would put it. On the archetype 08-05 actually was, 30 trades
say the same thing the one 776C wave says: never widen.

**Honest scoping gap, disclosed rather than papered over.** This population sweep varies
`premium_stop_pct` only — it never touches `catastrophe_stop_pct`, so the 67-of-191 structure-mode
trades sit at a constant −50% cap through every cell shown above. That means this table is a
valid, large-N cross-check for the **premium-stop axis** (relevant to `vwap_continuation`, §3–5)
but provides **zero** population evidence on the **catastrophe-cap axis** this study also probed
on 08-04's ribbon legs (§3a). That is a real, currently-unfilled gap — named in the verdict, not
silently generalized past.

---

## 7. RECONCILING THE APPARENT CONTRADICTION — the single most valuable output of this file

**Both are true, from real data, and here is why.**

- The autopsy's claim: *"the live stop exits losers that then pay the thesis — the stop is
  harvesting winners, not cutting losers"* (15/15 in this cohort).
- The 08-05 audit's claim: *"the stop is not the problem... the five stop-outs were the only
  thing limiting the damage."*

The `stopped_then_paid` **tag** (`trade_autopsy.py#classify_position`) only requires the
contract's high **at any point after** the stop-out to reach back to entry price. It says
nothing about whether that recovery was sustained, tradeable, or capturable by any live rule —
and it says nothing at all about what happens to a position that is *not* stopped.

- **On 2026-08-04 (gap-go):** the underlying trend genuinely continued. Every stop-out was a
  re-buy of the *same still-live move*. Widening captured that move more efficiently — fewer
  round-trips, equal-or-better outcome, verified leg-by-leg in §4. The tag was diagnostic of a
  real defect.
- **On 2026-08-05 (gap-fade):** the underlying move genuinely reversed and never came back
  (776C's post-10:20 high sat six cents under even the *cheapest* of the five real entries).
  Every stop-out correctly refused to keep buying a dead trade. Widening only ever meant paying
  for more of a decline that had already happened — concentrated into one bigger loss instead of
  spread across several smaller ones. The stop was doing its job.

**It is the same stop, the same re-entry architecture, and the same shape of statistic on both
days.** What differs is whether the move that justified the *original* entry was still true by
the time of the re-entry — a fact that is only knowable in hindsight.

**Is that distinction knowable live, at entry time? No — and this repo already built and tested
the exact instrument that would need to know it.** The pre-registered early regime classifier
(`REGIME-EARLY-CLASSIFIER-2026-08-02.md`) failed every gate: 8-way accuracy 20.9% against a 39.1%
majority baseline; of the days it flagged gap-fade at 09:45 ET, 18 were truly gap-go against 16
truly gap-fade — worse than a coin flip on precisely the question this reconciliation turns on.
**Tuesday 08-04 and Wednesday 08-05 are exactly the pair that classifier cannot tell apart**, and
the 776C entries (09:58–10:19) sit squarely inside its documented blind window.

---

## 8. GRAVEYARD CHECK

| entry | status | this study's relationship to it |
|---|---|---|
| `hold_to_time_stop` / `trail_only_no_tp1` | **DEAD**, book-wide, −$451.50 over n=21 winners (`git show HEAD:analysis/winner-autopsies/all.md`) | **Not the same lever.** `hold_to_time` disables TP1 entirely (`tp1_premium_pct=999.0`) and drops the stop to −95% — "no risk management except a near-wipeout cap." This study's grid never touches TP1/profit-lock/trail at any cell; even the widest cell (−50% catastrophe-only) runs full TP1 + trailing-runner management. Scored all-legs (not winners-only), unlike the graveyard entry's original (pre-fix) number. It rhymes with the same intuition and it still fails the SAME cross-day test the graveyard entry would fail — an independent kill, not a revival. |
| pre-TP1 profit-lock `arm_scope=full` | **DEAD, 5th time** — cell E1, `exit-armscope-tp1-ab-2026-07-28.json`: G1 aggregate −$482.10, G4 runner cohort −$7,758.85 (22 worse / 0 better), n=190 real OPRA | Different axis (when the trail arms, not stop width) — not retested here, cited only to confirm no silent re-derivation occurred. |

**This study's result is not either graveyard entry wearing a new name.**

---

## 9. `hold_to_time` counterfactual trustworthiness — the task's specific ask, answered

**Not trustworthy as a general "money left on the table" measure — confirmed, and this is itself
a reportable finding, not just a caveat.**

`hold_to_time` (`trade_autopsy.py#COUNTERFACTUALS`) sets `tp1_premium_pct=999.0`,
`runner_target_pct=999.0`, `profit_lock_mode="fixed"`, `trail_pct=0.0`, `premium_stop_pct=-0.95`
— every exit disabled except a near-total wipeout, priced at whatever the contract is worth at
the 15:50 time-stop. On a 0DTE contract that number is dominated by full delta/intrinsic exposure
to the *entire remaining session's move*, not by theta — its own name ("does pure theta-ride beat
what we did") mischaracterizes what it actually measures.

The **$6,976** quoted on risky-3's −$104 762C trade is real-OPRA-derived, not fabricated — but it
is a full-exposure, uncapped-both-directions readout of *one trending day*, and this session
independently confirms it is dangerous exactly the way `EOD-2026-08-04-WINNERS.md` already said
("pure 0DTE expiry mechanics on a one-directional day... the single most dangerous shape on the
menu on a reversal day"): **the analogous "let it ride with minimal stop" cell in this study's own
08-05 grid (−50% catastrophe-only) is the WORST cell in the entire grid**, −$1,532.50, worse than
doing nothing.

**Systemic bias worth fixing (flagged, not fixed here — out of read-only scope):**
`classify_position()` always names the *highest*-P&L counterfactual as `best_counterfactual`, and
`hold_to_time` has the only unbounded upside in the menu — it will win that comparison on every
trend day **by construction**, and it is never symmetrically punished with a comparable MINUS
figure on a reversal day (a reversal day just shows as an ordinary loss, not a flagged blowup).
**The autopsy's own "Δ vs best" column is structurally biased toward flagging `exit_shape_cost` on
trend days, independent of whether a real, live-executable improvement exists.** Worth a future
fix: exclude `hold_to_time` from `best_counterfactual` selection, or add its own worst-case /
capped-downside twin as a counterweight.

---

## 10. VERDICT

> **(b) Regime-conditional, and the regime is not detectable live at entry time.** Record the
> null. Mark `H-2026-08-0{4,8,16,21,29}-stop-noise` (`stop_inside_noise_floor`) **SETTLED** —
> it should stop re-emitting weekly; the mechanism is now fully understood and the blocker is
> live-detectability, not missing data.

- **Do not ship** any `vwap_continuation` stop-width change, in either direction, on this
  evidence. 08-04 alone would say ship wide; 08-05 alone (and the 391-day gap-fade population)
  says don't; the discriminator isn't knowable at the time a trade is placed.
- **Worth a narrow, separate, future pre-registration** (not this study, not shippable today):
  the `ribbon_ride` catastrophe-cap axis is pinned at −50% for every structure-mode trade and has
  **never** been tested at any other width in the 391-day population (that sweep only varies
  `premium_stop_pct`). 08-04's own all-legs data argues, if anything, to *leave it alone*
  (tightening costs ~$532 more on winners than it saves on losers) — the opposite direction from
  what a naive read of the losers-only cohort would suggest. Named as a genuine open question,
  not answered here.
- **What would change this verdict:** a live, pre-tick regime signal that clears the same gates
  the 2026-08-02 classifier failed (>39.1% majority-baseline accuracy; precision materially above
  the observed 26.8–26.9%). Until one exists, any stop-width change is a bet on which regime
  today is, placed with a coin this repo already showed is not fair.

---

## Sources / new artifacts (all read-only w.r.t. the live trading path)

- `backtest/tools/stopped_then_paid_2026_08_04.py` — the main sequential replay harness (this
  study's core deliverable; re-runnable, produces the raw grid JSON).
- `backtest/tools/_pull_08_04_broker_fills.py` — read-only broker order puller (GET only).
- `backtest/tools/_pop_sweep_with_30.py` — thin wrapper adding one cell to the existing,
  already-verified `stop_width_fullhist_sweep.py` without editing it.
- `analysis/autopsies/2026-08-04.md` — cohort definition + the recurring hypothesis.
- `analysis/deep-research/EOD-2026-08-04-{FULL-REVIEW,WINNERS,REENTRY}.md` — same-day context,
  cross-verified against, not re-litigated.
- `analysis/deep-research/EOD-2026-08-05-{FULL-REVIEW,STOPS}.md` — the cross-check day's
  already-adversarially-reviewed findings, cited directly for the put/population/PDT material
  this study did not re-derive; the 776C wave itself **was** independently re-derived (§5).
- `analysis/recommendations/exit-armscope-tp1-ab-2026-07-28.json`,
  `git show HEAD:analysis/winner-autopsies/all.md` — graveyard citations (§8).

**Nothing armed. Nothing needs J.** This is a settle-the-hypothesis finding, not a ship decision.
