# Money-leak audit — SYNTHESIS (2026-09-03, Fable judgment over a 10-hypothesis Sonnet fleet)

> Trigger: J, 11:00 ET, after four losing sessions (09-01..09-03 book −$2,367 incl. today's −$1,045):
> "why are we absolutely failing these past few trading days … find test and resolve these issues."
> Method: 10 independent investigators (one hypothesis each, cached data only, read-only on live state,
> no broker calls), 3 skeptic lenses per SUPPORTED finding, synthesis by the main session.
> Reports: one `<slug>.md` + `<slug>.json` per hypothesis in this directory; scripts `backtest/tools/money_*.py`.
> Population unless stated: the 394 OPRA-scored engine round trips in `analysis/pain-ledger/mae-mfe.json`
> (all arms, real fills), cross-joined to the decision ledgers.

## 1. Root cause — what the evidence actually supports

**There is no single broken knob.** Every entry-tick rule tested trades winners for losers at roughly 1:1,
and the sign of every candidate flips with one day removed. What the data says instead, in one sentence:

> The engine's P&L is a function of DAY TYPE, not of any feature known at the entry tick: the same
> breakout entry at the session extreme that pays +$1,500–3,000 on a fast one-directional day
> (08-13, 08-27, 08-28) is stopped at −50% or by a 4-cent structure breach on a chop/reversal day
> (09-01, 09-02, 09-03), and no filter we can compute at entry separates the two day types yet.

Supporting facts (each from a different investigator, each independently reproduced where it mattered):

- **The book is not yet distinguishable from breakeven.** Current-cap cohort n=239: WR 32.6% (break-even
  29.3%), PF 1.23 CI [0.84, 1.74], total +$3,532 CI [−2,639, +9,825]. (H8) The last four sessions are inside
  that distribution. This is the honest headline, not "failing".
- **Entry location is directional but not actionable.** Chase-extreme (calls ≥0.75 / puts ≤0.25 of the
  session range) n=103: +$2.12/trade, PF 1.03 vs rest n=83: +$18.90/trade, PF 1.34; diff CI [−73, +39];
  the sign flips at the 0.90/0.10 threshold; a global refuse-extreme rule flips 08-13 from +$1,748 to −$147
  because every winner that day was a breakout at range_position 1.0. Within BULLISH_RECLAIM only: chase
  PF 0.99 vs rest PF 1.67 (CI still crosses zero). (H1)
- **The loss mechanism is the "orphan band".** 45.5% of all 279 losers (127 trades) had ≥+10% favorable
  excursion before ending at the cap; 27 of them had ≥+20% MFE and still hit −50%. (H4)
- **Arming the profit-lock before TP1 rescues that band and kills the big days.** `profit_lock_arm_scope='full'`
  on the one walker-trusted arm (safe-2, n=88): +$2,578 total, per-trade CI [+$0.59, +$55.86], WR 29.5→36.4%,
  PF 0.73→1.40 — BUT the most recent quarter (08-18..09-02) is −$327 and three of the four big days lose
  a combined −$881, with two winners cut to exactly $0. Do not ship as tested. (H4)
- **Structure stops are whipsaw-prone and buffers do not fix it.** Of 79 real structure-stop exits, SPY
  reclaimed the trigger within 15/30/60 min in 56% / 71% / 79% of cases. Five buffer variants ($0.15, $0.25,
  0.5×ATR, two closes, 1-bar grace) all flip negative when their single best day is removed; the two with
  positive headlines owe 97%/117% of their total to 3 of 79 positions. (H5) Today's 10:36 exit was a
  4-cent breach (5m close 767.96 vs trigger 768.00) followed by a reclaim to 769+.
- **"Wait for the retest" works or fails depending on the zone width.** Retest variant on 103 signals:
  $0.30 zone −$2,850 (misses 17 winners worth +$5,952, 08-28 flips to a loss); $0.50 zone +$955
  (WR 39.8→45.8%, PF 1.46→1.73), CI crosses zero both ways. It helps in VIX 15–17 (+$1,167) and hurts on
  fast VIX<15 days. Unresolvable until the zone width actually in force per decision row is persisted. (H10)
- **VIX band is the one split that repeats across studies.** Whole book: VIX<15 n=84 −$601, 15–17 n=247
  +$2,639, >17 n=63 −$1,503 (H3); the chase-extreme penalty lives in VIX<15 (chase PF 0.85 vs rest 1.58) and
  vanishes in 15–17 (H1); retest helps in 15–17 and hurts in <15 (H10). But the two biggest winning days
  sit on the 15.0 boundary (08-27 VIX 15.04, 08-28 14.59), so a level cut is not a rule — per C5 it is VIX
  *character* that needs the pre-registered classifier H8's settled hypothesis already asked for.
- **Refuted outright** (no live change licensed): tighter catastrophe cap (monotonically worse at −30/−35/−40%,
  kills 11 winners incl. every 08-28 winner; H8); bold-2 min-premium floor or tier shift (its <$0.40 bucket
  is its BEST, PF 6.07; the bleed is the $0.80–1.50 bucket, n=16, −$1,130; tier shift already failed live
  07-18..08-20; H3); bear-requires-level (opposite sign; kills 08-06's +$1,501; H6); any later entry gate
  (09:45 removes a +$991 cohort, 10:00 flips 08-13 to a loser; H7).
- **Instrument defects found:** conviction component C4 `range_extreme` has a 0/482 hit rate because its
  polarity was calibrated on a mean-reversion exhibit while both live triggers are continuation setups
  (calls print range_position 0.34–1.00, mean 0.81; puts 0.00–0.45, mean 0.14) — mechanically proven,
  three skeptics failed to refute; and the conviction shadow has ZERO coverage on the four fleet arms. (H2)
  Fleet skipped-exit-check cost: real but $32 total, hygiene. (H9)

## 2. What this means for "start making money"

1. **Nothing found today clears the bar for the 09-29 safety bundle.** Every candidate fails at least one of:
   CI crosses zero, drop-best-day flips sign, kills a named winning day. Shipping any of them would be
   result-shopping on seen data.
2. **The lever is a day-type discriminator known at entry time**, not a stop or a gate. Three independent
   studies point at the same thing from different angles (H1 VIX split, H10 regime split, H4 winner-kill).
   Until it exists, the engine will keep paying the chop-day tax to stay in the trend-day trades that carry
   the whole book. That is the right-tail shape the 08-29 review named; the September window is the test of
   whether the tail pays for the tax.
3. **The orphan band is the largest recoverable pool** (127 losers with real favorable excursion) and the
   +5%-arm / 15%-trail cell is now SEEN data. The next candidate must be pre-registered on unseen (forward)
   data with an arming condition that cannot trigger on noise: arm only after MFE ≥ +20% AND ≥ 10 minutes
   in trade, trail 15% off HWM, and it must leave the 08-04 C769 runner and all four big days untouched.

## 3. Forward instruments to build tonight ($0, shadow-only, none on the trading path)

| # | Instrument | Prereg bar | Files |
|---|---|---|---|
| F1 | **Profit-lock v2 forward shadow** — nightly walker replay of every closed fill under {arm ≥+20% MFE AND ≥10 min, trail 15%} vs control; safe-2 dollars trusted, other arms sign-only | ≥20 sessions AND ≥25 scored fills; per-trade Δ CI-lower > 0; recent-quarter ≥ 0; 4 big days Δ ≥ 0 | `setup/scripts/profit_lock_v2_shadow.py`, prereg |
| F2 | **Entry-location × trend-quality shadow ledger** — promote `money_entry_location*.py` to a nightly ledger; add entry-time trend-quality co-signals (minutes since ribbon flip, HTF stack age, opening-range extension) | re-test BULLISH_RECLAIM chase vs rest at n_chase ≥ 150 with the co-signal pre-registered | `setup/scripts/entry_location_trend_shadow.py`, prereg |
| F3 | **Retest zone-width grid** — persist the zone width in force per trigger (from the archived key-levels snapshots) and pre-register the grid {0.20, 0.30, 0.40, 0.50, 0.75} with the decision rule fixed before reading | forward ≥20 sessions; the grid is read once | prereg + `setup/scripts/retest_zone_shadow.py` |
| F4 | **Conviction C4 polarity recalibration (shadow sidecar)** — re-score decision rows nightly with continuation-polarity C4; extend the shadow to fleet ledgers via the sidecar, not the engine | shadow only; feeds the conviction ratchet | `setup/scripts/conviction_shadow_report.py` variant |
| F5 | **Day-type classifier prereg** — the P1 free swarm grinds entry-time-known day-type features against the 44-day real-fills population with the decision rule frozen; forward-scored | OOS positive, WF ≥ 0.70, sub-window stable, 4 big days kept | Kitchen item + prereg |

Everything above is additive, reversible (`git revert`), and outside the frozen trading path.

## 4. What we still do not know

- Whether the edge is real at all: PF CI [0.84, 1.74] at n=239. The go-live gate's 20 scored days is the
  smallest measurement that settles it; we are 2 scored days in.
- Whether the day-type tax is separable at entry time. F2 + F5 are the smallest tests.
- The true zone width in force on past triggers (F3 prerequisite).
- Walker dollars off safe-2 remain SIGN-ONLY (fidelity anchor of 2026-09-03).

## 5. Verdict for J

**Not failing — running a thin, unproven right-tail edge through its normal chop-day drawdown, and no knob
found today fixes that without killing the days that pay.** The lever is telling trend days from chop days
at entry time, which we do not have yet; five forward instruments go up tonight to build it without touching
the frozen path. The September window is the test of the edge itself, and the honest current read of that
edge is a coin flip with upside (PF 1.23, CI 0.84–1.74).
