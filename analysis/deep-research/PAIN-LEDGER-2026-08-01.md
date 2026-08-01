# PAIN LEDGER — MAE/MFE over every closed engine trade (2026-08-01)

> # ⛔ DESCRIPTIVE ONLY — this ledger VALIDATES NO STOP CHANGE. MAE knowledge is hindsight by definition (C6): a live stop cannot condition on a trade's eventual maximum heat. Any stop-placement change is its own future pre-registered A/B that may cite this ledger only as its evidence base.
>
> Nothing in this file is a pass/fail verdict, a knob proposal, or evidence sufficient for one. It answers ONE question: *what did our filled trades actually live through?*

_Generated 2026-08-01T15:18:39.467327 ET · prereg `analysis/pain-ledger/PREREG-2026-08-01.md` (committed before the builder existed) · real OPRA 1-min bars · entry+1 holding-window · $0._

## Population + provenance

- **160 of 161** closed engine option positions scored (21 winners / 128 losers / 11 scratch), arms: bold-2, risky-1, risky-3, safe-1, safe-2, safe-3, 22 ET dates 2026-06-26 → 2026-07-31.
- Excluded AND counted: 0 no-OPRA-bars, 1 no-exit-eligible-window, 0 bad-entry (symbols in `mae-mfe.json` `_meta.population`). Synthetic rows: **0 by construction** (no synthetic path exists in this machinery).
- P&L = broker fills; excursions = real Alpaca OPRA 1-min bar lows/highs.
- Recency split: most recent 25 distinct ET dates (from 2026-06-26) vs older.
- Verification: one loser row's MAE/MFE independently recomputed from a fresh OPRA fetch
  outside the builder's code path — exact match (`SPY260706C00755000`, min_low 0.01 /
  max_high 0.03). Winner-side capture rate re-derived same run at 101.9%, matching the
  registered `Gamma_WinnerAutopsy` first-fire number.
- **stop_mode recovery (2026-08-01 update):** 16 of the original 123 `premium_unverified`
  rows recovered a verified `stop_mode` from the engine's own `exit_pass` tick history
  (`pain_ledger.recover_stop_mode_from_exit_trace` — direct tick-logged value where every
  non-null tick agreed, or an unambiguous `structure_stop` action stage). 107 remain
  unrecoverable (dated 2026-06-26..2026-07-09, before the tick-level `stop_mode` field
  existed) and stay labelled `premium_unverified`, honestly — no date heuristic, no guess.
  Cut 5's table below reflects the recovered rows; cuts 1-4 are numerically UNCHANGED (MAE/
  MFE/timing never depended on stop_basis).

## Findings at a glance (DESCRIPTIVE — restating the banner: none of this validates a stop change)

- **Real winners take real heat, but bounded:** median winner |MAE| **12.2%**, p75 19.2%,
  p90 26.2%. 5/21 winners went deeper than −20% before winning; **0/21 went past −50%**;
  only 3/21 never ticked below entry at all. A winner cohort that mostly survives a
  10–25% drawdown before paying is what these entries actually look like on real bars.
- **Zero winners ever traded through their configured premium-stop level** (0/21
  `stop_inside_mae`) vs **82/128 losers** that did. UNCHANGED by the stop_mode recovery
  above (this count was always basis-independent — see cut 5's note). Definitionally
  entangled with the exit policy that produced the cohorts (see limitations) — descriptive,
  not causal.
- **The separation lives in MFE, not MAE overlap:** winners' median MFE **+115%** (p90
  +285%) vs losers' **+9.6%** (p90 +44%). 30/128 losers did touch ≥+30% favorable at some
  point before dying — recorded here as the evidence base any future exit study must cite.
- **Timing shape:** winners hit max heat early (median t→MAE **2m** after entry) and pay
  later (median t→MFE 14m, median hold 24m). Losers die fast: median hold **4m**, t→MAE 3m.
- **Setup families differ:** `BEARISH_REJECTION` winners carry median 13.8% |MAE| with
  median t→MAE 10m (slow heat, then +150% median MFE); `BULLISH_RECLAIM` winners run
  hotter (19.1% median |MAE|) and its losers are 76 of the 128. The `(unattributed)`
  cohort (25 rows) is dominated by sub-$0.20-premium fills where % stats are tick noise.
- **Recency cut is degenerate today** — only 22 distinct dates exist, so the older cohort
  is empty; kept as frozen, informative as dates accrue.

## 1 · How much heat? |MAE| distribution by outcome (premium %, whole population)

| Cohort | n | mean | p25 | p50 | p75 | p90 |
|---|---:|---:|---:|---:|---:|---:|
| **winners** | 21 | 12.9% | 8.0% | 12.2% | 19.2% | 26.2% |
| **losers** | 128 | 32.4% | 22.3% | 28.6% | 42.3% | 51.9% |
| **scratches** | 11 | 21.9% | 6.5% | 24.0% | 25.0% | 54.5% |

_|MAE| shown as positive magnitude (a p50 of 20% means half the cohort never traded more than 20% below entry during the holding window)._

## 2 · By setup family (winners vs losers; every family shown, small-n flagged)

| Setup family | outcome | n | mean |MAE| | p50 |MAE| | p75 |MAE| | p50 MFE | med t→MAE | med t→MFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `(unattributed)` | winner | 5 | 4.9% | 3.7% | 8.0% | 11.1% | 1m | 1m |
| `(unattributed)` | loser | 20 | 17.5% | 15.4% | 21.1% | 7.5% | 1m | 1m |
| `BEARISH_REJECTION_RIDE_THE_RIBBON` | winner | 10 | 14.0% | 13.8% | 20.2% | 149.8% | 10m | 36m |
| `BEARISH_REJECTION_RIDE_THE_RIBBON` | loser | 32 | 34.3% | 30.0% | 44.2% | 13.2% | 7m | 3m |
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | winner | 6 | 17.9% | 19.1% | 19.8% | 213.3% | 2m | 20m |
| `BULLISH_RECLAIM_RIDE_THE_RIBBON` | loser | 76 | 35.5% | 32.2% | 44.9% | 10.1% | 3m | 2m |

## 3 · Recent-25-dates vs older (recency > aggregate)

| Window | outcome | n | mean |MAE| | p50 |MAE| | p75 |MAE| | p50 MFE |
|---|---|---:|---:|---:|---:|---:|
| recent25 | winner | 21 | 12.9% | 12.2% | 19.2% | 115.1% |
| recent25 | loser | 128 | 32.4% | 28.6% | 42.3% | 9.6% |
| recent25 | scratch | 11 | 21.9% | 24.0% | 25.0% | 25.0% |
| older | winner | 0 | n/a | n/a | n/a | n/a |
| older | loser | 0 | n/a | n/a | n/a | n/a |
| older | scratch | 0 | n/a | n/a | n/a | n/a |

_⚠ The **older cohort is EMPTY today**: the population spans only 22 distinct ET dates (≤ 25), so every trade falls inside the frozen recent-25 window. The split is kept AS FROZEN (not re-tuned post-hoc) and becomes informative as dates accrue._

## 4 · MFE + timing (medians)

| Cohort | n | p50 MFE | p90 MFE | med t→MAE | med t→MFE | med hold |
|---|---:|---:|---:|---:|---:|---:|
| winners | 21 | 115.1% | 284.5% | 2m | 14m | 24m |
| losers | 128 | 9.6% | 43.9% | 3m | 2m | 4m |
| scratches | 11 | 25.0% | 112.1% | 6m | 4m | 6m |

## 5 · Configured stop vs MAE (`stop_inside_mae` = level traded through, NOT 'live would have fired')

| Cohort | stop basis | n | stop inside MAE | stop outside MAE | unknown |
|---|---|---:|---:|---:|---:|
| winners | `premium` | 2 | 0 | 2 | 0 |
| winners | `premium_unverified` | 7 | 0 | 7 | 0 |
| winners | `structure_catastrophe_cap` | 12 | 0 | 12 | 0 |
| losers | `premium` | 15 | 2 | 13 | 0 |
| losers | `premium_unverified` | 94 | 72 | 22 | 0 |
| losers | `structure_catastrophe_cap` | 19 | 8 | 11 | 0 |
| scratches | `premium_unverified` | 6 | 2 | 4 | 0 |
| scratches | `structure_catastrophe_cap` | 5 | 2 | 3 | 0 |

_`structure_catastrophe_cap` rows: the operative stop was a CHART level; the premium number tested here is only the −50% catastrophe cap. `premium_unverified`: stop_mode was not recoverable from the decision ledger OR the engine's own exit_pass tick history — no date-based heuristic or majority-vote guess is ever used to shrink this bucket (16 rows WERE recovered this way vs the original 123; see the population note above)._

---

## Method / disclosed limitations (frozen in the prereg — read before quoting)

- **Bar-low basis:** 1-min bar lows see every intra-minute print; the live actuator samples ~one NBBO snapshot per minute. `stop_inside_mae` overcounts touches relative to live behavior — by design, and labelled.
- **entry+1:** heat inside the entry bar's own minute is excluded (the live exit pass cannot act there); nothing after the final exit bar counts.
- **$ figures at full entry qty** — `*_before_first_exit` flags mark when an extreme postdates a partial exit (the $ figure is hypothetical there).
- **Sub-$0.20-premium entries quantize the % stats:** on a $0.02 entry, one $0.01 tick is ±50% of premium, so MAE/MFE percentages in that cohort are tick-noise multiples (the noise-floor lesson). The $0.30 min-entry-premium floor (KEEP, real provenance) removes these going forward; historical rows keep them, labelled by their `entry_price`.
- **No significance tests anywhere** — these are distributions, not claims. A future study slicing this ledger to hunt an effect owes its own prereg + FDR.
- **Winners took their heat and lived; losers' MAE is bounded below by their exits** (a stopped trade cannot show heat past its stop). Comparing the two cohorts' MAE is conditioned on the exit policy that produced them — one more reason this ledger cannot validate a stop by itself.

_Ledger: `analysis/pain-ledger/mae-mfe.json` · builder `setup/scripts/pain_ledger.py` · refreshed nightly by the existing `Gamma_WinnerAutopsy` 16:25 ET fire (no new task)._
