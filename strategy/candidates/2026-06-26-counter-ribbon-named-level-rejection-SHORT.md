# Strategy candidate: COUNTER_RIBBON_NAMED_LEVEL_REJECTION (SHORT side)

> DRAFT — Chef proposal 2026-06-26. J ratifies. **VERDICT: HOLD / REJECT.**

## Hypothesis
Enter PUTS on a confirmed rejection candle off a named Active/Carry **resistance** level,
**counter-ribbon ALLOWED** (do not require EMA ribbon = BEAR), ITM strikes + tight target
(anti-theta, the vwap_continuation winning profile), outer-band only (~$0.30), hard cap
2–3/session. Directional claim: relaxing the ribbon gate captures the 2026-06-24 ~09:40 ET
PMH 737.11 first-candle rejection the engine missed for ribbon-lag.

## Verdict up front (brutal honesty)
**This setup does NOT clear the null and should NOT be promoted.** Counter-trend 0DTE
bounce/fade scalps are the most-attempted, most-failed family, and the SHORT side of THIS
exact primitive has already been independently killed three times in our own corpus. I am
calling **HOLD** per the task's own instruction ("if it does not clearly beat the null, say
HOLD"). I did not have to re-run a grind to know this — we already paid for the answer.

## Why this could not be freshly real-fills-validated (data gap — disclosed, not hidden)
- **OPRA option-bar cache stops at 2026-06-18** (`backtest/data/options/` last contract =
  `SPY260618*`). The two motivating anchors (06-24 SHORT, 06-26 LONG) have **no cached 0DTE
  contracts**, and 06-26 has no SPY 5m bars yet either. So `simulator_real.py` **cannot fill
  either anchor.** A grind today validates only the population through 06-18, NOT the anchors.
- **There is no historical per-day named-level store.** `level_source.py` reads ONLY the
  single LIVE `automation/state/key-levels.json` snapshot (today's levels). The historical
  backtest infra (`build_day_contexts`) carries `prior_close` + RTH session only — it has **no
  record of what the Active/Carry named levels were on each past day.** Any historical
  "named-level rejection" backtest is therefore a **PROXY** (PDH/PDL/intraday-extreme), not the
  real J-curated levels. This is a structural limit of the data, not a tuning choice.

So the honest path is to lean on the THREE prior results that already measured this exact
primitive with real fills and a proper null — rather than fabricate a fresh number on a proxy.

## Backtest evidence (from existing, paid-for results — convergent)

### 1. `level-rejection-gate-01` (RATIFIED 2026-06-17, real-fills engine backtest)
This is the SHORT side of this setup, measured directly. `level_rejection` =
"counter-trend fade of a resistance touch." Finding:
- **IS subset n=22, avg −$584/trade, −$13,389 total.** Systematically unprofitable.
- Production decision was to **BLOCK** it: `block_level_rejection=true` shipped to params.json.
- Blocking it improved IS pnl by **+$13,181** (−$5,118 → +$8,063) and OOS by +$682; WF=0.842.
- i.e. our own ratified production gate exists specifically to **stop taking this trade.**
  Proposing it as a new candidate is proposing to re-enable a gate J already ratified OFF.

### 2. `level-quality-benchmark` (220 days, 3,202 real levels, 3 null shuffles)
Named levels have a PLACEMENT edge but **NO reaction edge** — the gate that matters here:
- touch_rate 0.529 real vs 0.219 random vs **0.513 distance-matched null** → levels get
  touched only because of WHERE they sit, not because they predict a turn (DM-null ≈ real).
- `respect_rate_of_touched` **0.250 real vs 0.276 random vs 0.255 DM-null** → a random level
  at the same distance is respected **as often or MORE.** No lift.
- `median_reaction_respected` **1.798 real vs 1.807 DM-null** → reaction size is null-identical.
- This is the textbook C3/L143/L183 signature: **a level edge a random-entry null reproduces
  is an exit artifact, not signal alpha.** The SHORT fade has no edge over a coin-flip entry.

### 3. `gate_sweep_patterns_levels` (Chef, 2026-06-17, C-category level-proximity sweep)
All 11 ribbon/level-proximity gate-relaxations REJECTED. Relevant to counter-ribbon:
- `vol_ratio = 0.0` on **all** J winner entry bars → the vol≥1.2–1.5x confirmation this
  setup mandates **anti-correlates** with J's actual edge bars (they fire on LOW vol).
- 5/01 (the one BULL-ribbon-all-day anchor) is structurally uncapturable by any bear gate.

## Theta sanity note (the ITM + tight requirement)
The anti-theta framing (ITM + tight target) is correct in spirit — it is the only profile
that survived our edge hunt (`vwap_continuation`, ITM-2/−8%). BUT: vwap_continuation is a
**WITH-trend continuation** edge. The thing that makes ITM+tight work there is that price
keeps going your way. Here the structure is **counter-ribbon fade** — you are betting on a
reversal against momentum. ITM+tight does not rescue a no-edge ENTRY: a tight target on a
trade with ~50% (null-level) hit-rate just realizes the loss faster. From the benchmark,
breakeven SPY move after 6 bars of theta is ITM-1 ≈ 0.24 / ATM ≈ 0.31 / OTM-2 ≈ 0.45 pts —
ITM helps the theta math, but the entry has to actually predict a ≥0.24pt drop better than
random, and the null benchmark says it does not.

## Regime stratification (range vs trend, NOT averaged — L-stratify)
From the level benchmark `by_vix_regime_real` (the closest available range/trend proxy):
- **low VIX (calm/range, n=299):** respect_of_touched 0.288, **median reaction only 1.165 pts**
  → in range days the bounce is too SHALLOW to beat ITM theta + tight target.
- **mid VIX (n=2399):** respect 0.248, reaction 1.720.
- **high VIX (trend/volatile, n=504):** respect 0.240 (LOWEST), reaction 3.170 → bigger moves
  but the level is LEAST respected (break-through regime) → the fade is run over.
- Net: there is **no regime where the SHORT fade is both respected AND deep enough** — calm
  days respect but don't move; volatile days move but don't respect. The averaged number hides
  this; stratified, both tails are unfavorable for a counter-ribbon resistance fade.

## Beats-the-null check (the critical gate)
**NO.** The level benchmark distance-matched null reproduces real levels' respect rate
(0.250 real vs 0.255 DM-null) and reaction size (1.798 vs 1.807). A random-entry null at the
same level distance/time performs as well or better. Per C3/L58/L183, this is the disqualifier.

## Disclosures (per OP-20)
1. **Account-size assumption:** N/A — not promoted; no fill math run. Had it run, Safe-2 $2K /
   qty 5, ITM-2 (L180 cap-realizability applies).
2. **Sample-bias disclosure:** the level benchmark is 220 days (2025-08 → 2026-06-16); the
   ratified gate's IS subset is only n=22 — small, but the direction is corroborated by the
   independent 3,202-level null benchmark, so it is not a single-sample artifact.
3. **Out-of-sample test result:** `level-rejection-gate-01` OOS = blocking the fade ADDED
   +$682 (the fade LOST money OOS too). The benchmark's null comparison is itself an OOS-style
   robustness test (random levels at matched distance). Both OOS-style checks fail the setup.
4. **Real-fills check:** NOT runnable on the two anchors (OPRA cache stops 06-18; no historical
   named-level store). The `level-rejection-gate-01` evidence IS real-fills (engine backtest,
   `use_real_fills=True`). So the real-fills authority we DO have says: skip this trade.
5. **Failure-mode enumeration:** (a) no reaction edge vs DM-null (exit artifact); (b) vol-gate
   anti-correlates with edge bars; (c) calm-day reaction too shallow for ITM theta; (d)
   volatile-day level least-respected (fade run over); (e) it re-enables a gate J ratified OFF;
   (f) 5/01-class BULL-ribbon-all-day anchors uncapturable even with the relaxation; (g) the
   06-24/06-26 anchors are un-fillable today, so any "it would have caught them" claim is
   un-evidenced.
6. **Concentration:** top5_pct = N/A (no trade set generated). Prior sweep flagged the closest
   analog (A3 bear-7) as 5/04-concentrated — concentration risk is the norm for this family.

## Knob changes proposed
**NONE.** Do not add `counter_ribbon_level_rejection`. Do not set `block_level_rejection=false`.
The existing production gate `block_level_rejection=true` should REMAIN ON.

## Pre-merge gate
`python crypto/validators/runner.py` → **97/98 PASS, overall_pass=True** (1 known-flaky live
source excluded). Green before and after this work item (read-only analysis; no code changed).

## My confidence (1-10) and why
**Confidence this should NOT ship: 9/10.** Three independent results — a ratified production
gate, a 3,202-level null benchmark, and a Chef gate-sweep — all say the SHORT counter-ribbon
named-level rejection has no edge over a distance-matched null and loses money on real fills.
The 1 point of doubt: the two NEW anchors (06-24/06-26) are genuinely un-fillable right now,
so I cannot *disprove* that the relaxation helps on those specific bars. The right next step is
not to promote — it is to **fetch OPRA + SPY bars for 06-24/06-26 and re-fill the two anchors**
to either confirm or kill the relaxation on the motivating cases. Until then: **HOLD.**

## Recommended next step (closes the data gap, not the search)
Queue an OPRA + SPY-bar fetch for 2026-06-19 → 2026-06-26 so the two ribbon-lag anchors become
fillable. THEN run a proxy-named-level real-fills check on ONLY those two days. If the
relaxation does not clearly beat the null on the two anchors with real fills, this primitive is
closed (it already failed the population test three ways).
