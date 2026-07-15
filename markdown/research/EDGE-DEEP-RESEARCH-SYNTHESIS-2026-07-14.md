# WHAT'S MISSING FOR OUR EDGE — deep-research synthesis (Fable, 2026-07-14)

> 91/103 research agents completed (synthesis step hit the weekly usage limit; this doc is the
> human synthesis from the 93 extracted claims — load-bearing claims were 3-0/2-1 adversarially
> verified before the limit; claims whose verification was cut short are marked UNVERIFIED).
> Sources: SSRN 4404704 (Beckmeyer et al., retail 0DTE), SEC DERA 0DTE working paper,
> SSRN 4692190 (0DTE returns), CBOE 0DTE analyses, the GEX-vs-VIX-controls study, the MNQ
> falsification battery (our own repo's futures Phase-1), QuantConnect ORB-credit study, et al.

## The brutal convergence — we trade the statistically losing SHAPE

The strongest, multiply-verified finding: retail 0DTE loses ~$350K/day in aggregate, and the
LOSING COHORT'S EXACT PROFILE is: **single-leg (72.2% of orders), ATM/slightly-OTM, upfront-debit
(long premium), short holds, put-heavy** — with **>70% of the losses coming from TRANSACTION
COSTS, not bad direction.** That profile is *us*, line for line. Our 12/12 signal kills were not
bad luck: an independent falsification battery (14 OHLCV signal families, 947 days) also found
ZERO bar-pattern signals clear friction at this timescale — and the post-news-drift and
volume-magnitude nulls were precise, not underpowered.

Second structural truth: the debit we pay IS the seller's compensation (VIX1D systematically
overestimates next-day realized vol = a positive variance risk premium at the 0DTE horizon).
Buying single-leg premium means paying that premium every trade, then paying the spread twice.

## What the documented EXCEPTIONS share (this is the edge map)

1. **Longer holds + regime classification, not better entries.** The only two signals that
   cleared the falsification battery's own bar worked via regime classification + 60-75 minute
   holds. J's OP-16 anchor winners are all multi-hour ribbon rides. The engine's losing cohort
   was 3-minute noise-stop deaths (now partially fixed by SS-B). The exceptions don't out-read
   the next bar — they hold through it.
2. **Multi-leg / defined-risk structures.** In the SAME dataset where single-leg loses, multi-leg
   trades are "significantly MORE profitable." A vertical DEBIT spread sells back part of the
   overpriced premium (the short leg collects VRP), cuts theta bleed, and defines risk — and
   debit spreads are viable in a CASH account (pay the debit in full, no margin). Credit
   spreads/naked selling are NOT accessible: margin account required + $2K minimum equity + SPY's
   physical settlement makes partially-ITM assignment a real tail risk (~$55.8K to carry 100
   shares).
3. **Execution: non-marketable limit orders HALVE the dominant cost** (SEC DERA: ~$0.021-0.028
   all-in vs $0.05 marketable; 0DTE spreads are tick-wide most of the time; retail-size limit
   orders fill well). Our entry_manager (T-W5) already implements passive-limit entries —
   sim-shadow only, TWIN-B3 queued to graduate it. This attacks the #1 measured loss driver with
   already-built machinery.
4. **The genuinely +EV documented 0DTE strategy found** (reproducible QuantConnect source,
   Sharpe 2.26 with day-of-week exclusions): SELLS credit spreads on the 60-min opening-range
   breakout. Not accessible at $1.7K cash — this is the North Star for when equity reaches
   ~$5K+/margin, not a v1 play. UNVERIFIED-tier (single practitioner source, self-reported).

## Formally KILLED by this research (stop spending on these)

- **GEX/dealer-gamma as alpha** — no incremental lift after VIX+ATM-IV controls (1,972-day SPY
  study), no edge in the high-VIX quintile, can't sign dealer positioning from OI, CBOE:
  0DTE MM gamma flow ≈ 0.2% of liquidity, customer flow balanced. Multiple independent strikes +
  our own internal study. Keep the free CBOE banking (cheap) strictly as a calm-regime
  descriptor; never as a signal build.
- **Order-flow imbalance at our timescale** — properly-lagged OFI: OOS R² ~3%, Sharpe ~0.12,
  decays away from HFT horizons. The one promising options-imbalance study is weekly-horizon,
  another market, needs participant-signed data we don't have.
- **More OHLCV bar-pattern mining** — two independent falsification batteries (ours + external)
  say the same thing. The gross-edge ceiling on public bar patterns is structural (UNVERIFIED
  wording, but consistent with everything measured).
- **Post-news drift; volume-magnitude signals** — precise nulls.

## THE RANKED ANSWER: what's missing

| # | Missing piece | Evidence grade | Effort | Action |
|---|---|---|---|---|
| 1 | **Passive-limit execution** (halve the dominant cost) | SEC DERA, 3-0 | LOW — entry_manager built, TWIN-B3 queued | Graduate on twin → SPY A/B |
| 2 | **Debit-spread structure** (sell back the VRP, defined risk) | SSRN multi-leg finding, 3-0 + mleg supported | MED — execution machinery + pre-reg A/B | Pre-registered A/B: same signals, spread vs naked; kill criterion = anchor regression (never cap J's +86% runners without evidence) |
| 3 | **Longer-hold, regime-classified posture** (the exceptions' profile; J's own anchors match) | Falsification battery positive controls + our anchor evidence | LOW-MED | Pre-reg: hold-time floor / trail-first posture on A-tier signals under SS-B |
| 4 | VIX1D risk-premium-adjusted regime gate | Academic, promising but our P5 killed cousins | LOW | Park unless #1-3 create a base to filter |
| 5 | Sell-side/credit structures (the actual house side) | Strong but inaccessible at $1.7K cash | — | Revisit at ~$5K/margin; the ORB-credit study is the template |

**The single highest-leverage next experiment: the debit-spread A/B (#2)** — it attacks both
verified loss mechanisms simultaneously (the overpriced single-leg debit AND friction as % of
premium), it's the one structural change the losing-cohort data directly indicts us on, and it's
executable in a cash account today. #1 runs in parallel because it's already built.

## Honesty rails

- Nothing here claims a signal edge exists. The evidence says: stop paying the full risk premium
  (structure), stop paying double friction (execution), hold like the winners hold (posture) —
  then re-measure whether our validated setups clear zero. That's the honest path from -EV
  toward viability; alpha beyond that remains unproven.
- Several late verification votes died on the usage limit; anything not 3-0/2-1 verified is
  labeled UNVERIFIED above and gets re-verified before it gates any build.
- The falsification battery cited as external is partly OUR OWN repo's futures Phase-1 work —
  independent of tonight's web sweep, but not independent of us. Disclosed.

## Queue (dispatched — status as of 2026-07-14 hygiene pass)

- EDGE-1-PASSIVE-LIMIT-GRADUATION (HIGH): TWIN-B3 execution → twin live measurement → SPY A/B.
  **STATUS: queued** (`automation/overnight/queue.md`, pending).
- EDGE-2-DEBIT-SPREAD-AB (HIGH): mleg execution lane + frozen pre-reg (spread vs naked on the
  same signal cohort, exit_manager replay + real fills, anchor-regression kill criterion).
  **STATUS: queued** (pending).
- EDGE-3-HOLD-POSTURE-PREREG (MED): hold-floor/trail-first posture study under SS-B.
  **STATUS: queued** (pending).
- EDGE-KILL-LEDGER: GEX-as-alpha, OFI-intraday, OHLCV-mining formally closed in the
  strategy-space registry (do not re-open without new non-OHLCV data).
  **STATUS: DONE 2026-07-14** — 5 DEAD closure rows appended to
  `analysis/backtests/STRATEGY-SPACE-REGISTRY.jsonl` (`gex_dealer_gamma_alpha_family`,
  `orderflow_imbalance_intraday_family`, `ohlcv_bar_pattern_mining_family`,
  `post_news_drift_family`, `volume_magnitude_signal_family`), each carrying
  what / why-killed / evidence-artifact / reopen-condition ("new NON-OHLCV data only").
  Queue fallout folded the same pass: FUTURES-PHASE1-BATTERY closed as done-kill (stale
  checkbox — ran 2026-07-09, KILL all seeds), FUTURES-FILLSIM-ARM folded (dependency killed;
  arming path = mirror-shadow forward evidence), BOLLINGER-MES-SWING-PORT-SPEC
  closed-superseded (new OHLCV battery on futures = the closed class). FUTURES-MIRROR-SHADOW
  verified NO-contradiction and stays: it is forward paper evidence of the real engine's
  decisions (round-trips + expectancy + buy-hold null bar), not bar-pattern mining.
  TWIN-B7-FREE-MODEL-BENCH untouched (stays).
