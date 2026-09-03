# D4 — Hold counterfactual: wave 1 (770C/772C) and wave 2 (768C/770C), 2026-09-03

> Stamp: 2026-09-03T11:40 ET. Read-only on `automation/state/**`, `analysis/quote-tape/**`, `journal/**`.
> No network calls — cached ledger data only (fills-ledger, core-decisions, fleet decisions,
> quote-tape, key-levels). Script: `backtest/tools/dissect_hold-counterfactual.py`.
> Data window: 09:30–11:39 ET (the stamp's last fully-observed minute). Everything after 11:39 is
> unknown as of this analysis and is reported as PENDING, never fabricated.

## 0. Answer to the mechanics question first (FACT, no proxy needed)

**Wave 1's −50% cap fired at 10:01–10:03 while SPY was 769.54 — 0.98 points ABOVE the 769.36
trigger's zone floor (768.56), not below it.** Verified directly from two independent account rows
(`safe` and `bold`) at `ts_et` 10:01:03/10:01:05, 10:02:03/10:02:05, 10:03:03/10:03:05 — both read
`spy: 769.54` at all three ticks. (Note: the task brief's premise that SPY was "~767.8–768.2" at that
moment does not match the ledger — that SPY level (767.78) wasn't reached until 10:11–10:15, roughly
8–12 minutes *after* the cap had already closed all four wave-1 legs.)

- **Did the 5m structure stop ever fire on wave 1 before the cap did? No.** The engine's own
  `last_closed_5m_close` (read directly from `exit_pass` on both `safe` and `bold` rows, cross-verified
  against a formula derived independently from the raw per-minute SPY tape — 0 mismatches across 47
  ground-truth points, see §1) never dropped below 768.56 during the entire wave-1 holding window:
  769.735 (09:41) → 769.79 (09:46) → 769.64 (09:51) → 769.59 (09:56) → 769.54 (10:01), i.e. always
  ≥0.98 above the zone floor. The nearest the 5m structure stop ever got to firing on wave 1 was three
  minutes *after* the cap had already closed the position: the first 5m close below 768.56 was 768.16
  at 10:06.
- **Was the cap the binding stop? Yes, unambiguously.** For all four wave-1 legs, the −50% premium
  cap was the sole and only stop that was anywhere close to firing. The loss was pure 0DTE theta bleed
  on a chopping, essentially-flat underlying (SPY moved −0.20 net, 769.735→769.54, over the 22-minute
  hold) against a strike that had gone slightly OTM (770/772 vs spot ~769.5) — not a structural
  breakdown. The option cratered −48% to −52% while SPY barely moved, which is what a fast-decaying
  near-the-money 0DTE contract does when the anticipated continuation doesn't show up in the first 20
  minutes.

## 1. Premium reconstruction — sources and verified methodology

Three tiers, all disclosed per-tick in the script output:

1. **FACT — real fills.** `automation/state/fills-ledger.jsonl`, 31 today rows, `attribution: engine`.
2. **FACT — real NBBO.** `analysis/quote-tape/2026-09-03.jsonl`, 648 rows, ~20s cadence while ANY arm
   holds the symbol. Covers 770C 09:41:40–10:02:54 (wave 1) + 10:16:24–10:35:55 (bold wave 2, same
   strike) + 11:06:39–11:39 (wave 3+); 768C 10:16:45–10:36:58 (wave 2, the whole real hold, no gap);
   772C 09:42:22–09:57:59 (wave 1) + 11:06:39–11:39 (wave 3).
3. **APPROXIMATE — Black-Scholes proxy**, only where real quotes don't exist. r=0, T = (minutes to
   16:00 ET)/(390×252) years, sigma solved by implied-vol inversion against the nearest real quote(s):
   - **Two-point calibration (bounded gaps — used wherever a real quote exists on BOTH sides of the
     gap):** implied vol solved at the quote immediately before the gap AND the quote immediately
     after; sigma linearly time-interpolated between the two. Exact at both boundaries by construction.
     Used for 770C 10:03–10:15 and 10:36–11:06, and 772C 09:58–11:05.
   - **Single-point extrapolation (open-ended gaps — no later real quote exists in the 09:30–11:39
     window):** sigma = k·VIX(t)/100 where k is fit once from the last real quote and held forward.
     Used for 768C 10:37→cutoff (all wave-2 "hold" outcomes past the real 10:36/10:37 exits ride this
     proxy) and for the tail of 770C/772C past 11:22/11:35.
   - **Measured calibration error of the naive single-point method** (diagnostic, run on the bounded
     gaps for comparison even though the two-point method is what's actually used for pricing):
     **−81.8%** for 770C at the 10:03→10:16 gap, **−70.3%** for 772C at 09:58→11:06, **−5.2%** for
     770C at 10:36→11:07. The first two are large: a flat constant-implied-vol decay model badly
     underprices a moderately-OTM 0DTE contract once spot round-trips through a dip mid-gap (SPY did:
     769.54→767.78→768.37 inside the first 770C gap). This is exactly why the two-point method (exact
     at both known boundaries) is what prices every leg below, not the single-point one — and it is
     also why the 768C **wave-2 hold-past-10:37 numbers carry the largest disclosed uncertainty**: that
     gap is still open at the data cutoff, so there is no second anchor to bound it, and the true
     calibration error for that segment is **UNMEASURED**.
   - Deep-ITM segments (770C/768C after SPY's rally through 772+, T still hours from close, low VIX)
     are the most reliable part of the proxy — extrinsic value is small relative to intrinsic there, so
     model risk is lowest exactly where the "hold" scenarios end up mattering most.
4. **5-minute close series** used for the structure-stop / zone-break rule: derived from the raw
   per-minute SPY tape via `last_closed_5m_close(t) = spy_tape[floor((t-1)/5)*5 + 1]`, a formula reverse
   -engineered from the engine's own reported values and verified against **47 ground-truth points**
   across three separate windows (09:41–10:03, 10:16–10:36, 11:07–11:34) with **0 mismatches** — this
   series is FACT-grade, not a proxy, for the entire session (it never depends on any option quote).

Zone floors (from `key-levels.json`, `zone_width` field, rule = `5m close < level − zone_width`):
- 769.36 (`SHELF_768.56_770.16`, wave 1 trigger): zone_width 0.80 → **floor 768.56**.
- 768.00 (`INTRADAY_PMH`, wave 2 trigger): zone_width 0.384 → **floor 767.616**.

## 2. Per-leg pricing under the five hold rules

Prices are the achievable **bid** at the decision tick (matches how the real premium_stop and
structure_stop actually execute — off `worst_premium`, not `best_premium`). MAE = max drawdown from
entry along the path the rule actually holds through (to its exit, or to the 11:39 cutoff if
unresolved). `equity` is each arm's stated start-of-day equity.

| Leg | Real exit ($) | Zone-edge-break | Cap −50% | Cap −70% | TP1(+100%)+runner | Hold-to-15:20 (PENDING) |
|---|---:|---:|---:|---:|---:|---:|
| safe-2 w1 770C (3x@0.98) | **−144** | −228 (10:06, APPROX) | −147 (10:01, FACT) | −228 (10:06, APPROX) | +351 (TP1 fired 11:15, runner open) | +565 mtm@11:39 |
| safe-3 w1 770C (5x@1.11) | **−270** | −444 (10:06, APPROX) | −310 (10:01, FACT) | −444 (10:06, APPROX) | +627 (TP1 fired 11:17, runner open) | +877 mtm@11:39 |
| risky-1 w1 770C (5x@1.08) | **−280** | −429 (10:06, APPROX) | −295 (10:02, FACT) | −429 (10:06, APPROX) | +664 (TP1 fired 11:17, runner open) | +892 mtm@11:39 |
| bold-2 w1 772C (5x@0.37) | **−85** | −163 (10:06, APPROX) | −100 (09:58, FACT) | −163 (10:06, APPROX) | +327 (TP1 fired 11:16, runner open) | +562 mtm@11:39 |
| safe-2 w2 768C (3x@1.40) | **−66** | +1,051 mtm (never breached) | +1,051 mtm (never touched) | +1,051 mtm (never touched) | +597 (TP1 fired 11:11, runner open) | +1,051 mtm@11:39 |
| safe-3 w2 768C (5x@1.31) | **−65** | +1,796 mtm (never breached) | +1,796 mtm (never touched) | +1,796 mtm (never touched) | +951 (TP1 fired 11:07, runner open) | +1,796 mtm@11:39 |
| risky-1 w2 768C (5x@1.31) | **−65** | +1,796 mtm (never breached) | +1,796 mtm (never touched) | +1,796 mtm (never touched) | +1,092 (TP1 fired 11:07, runner open) | +1,796 mtm@11:39 |
| bold-2 w2 770C (5x@0.48) | **−70** | +1,192 mtm (never breached) | −132 (10:36, APPROX) | +1,192 mtm (never touched) | +618 (TP1 fired 11:07, runner open) | +1,192 mtm@11:39 |

**Maximum adverse excursion each rule sat through** (dollars / % of that arm's start-of-day equity):

| Leg | Zone-edge-break | Cap −50 | Cap −70 | TP1+runner | Hold-to-15:20 |
|---|---:|---:|---:|---:|---:|
| safe-2 w1 | $228 / 4.03% | $147 / 2.60% | $228 / 4.03% | $229 / 4.06% | $229 / 4.06% |
| safe-3 w1 | $444 / 7.88% | $310 / 5.50% | $444 / 7.88% | $447 / 7.93% | $447 / 7.93% |
| risky-1 w1 | $429 / 6.98% | $295 / 4.80% | $429 / 6.98% | $432 / 7.03% | $432 / 7.03% |
| bold-2 w1 | $163 / 2.92% | $100 / 1.79% | $163 / 2.92% | $171 / 3.06% | $171 / 3.06% |
| safe-2 w2 | $114 / 2.02% (FACT) | $114 / 2.02% (FACT) | $114 / 2.02% (FACT) | $114 / 2.02% (FACT) | $114 / 2.02% (FACT) |
| safe-3 w2 | $145 / 2.57% (FACT) | $145 / 2.57% (FACT) | $145 / 2.57% (FACT) | $145 / 2.57% (FACT) | $145 / 2.57% (FACT) |
| risky-1 w2 | $145 / 2.36% (FACT) | $145 / 2.36% (FACT) | $145 / 2.36% (FACT) | $145 / 2.36% (FACT) | $145 / 2.36% (FACT) |
| bold-2 w2 | $132 / 2.36% (mostly FACT) | $132 / 2.36% (mostly FACT) | $132 / 2.36% (mostly FACT) | $132 / 2.36% (mostly FACT) | $132 / 2.36% (mostly FACT) |

Wave-2 MAE is FACT-grade (occurred inside the real quote-tape window — the 768C low of $1.02 bid at
10:34:51, cross-checked directly against the quote-tape rows, reproduces exactly). Wave-1 MAE for the
non-cap rules is APPROXIMATE (occurs inside a BS-proxy gap).

## 3. Per-arm and book totals under each rule (8 legs)

| Rule | safe-2 | safe-3 | risky-1 | bold-2 | Book (8 legs) |
|---|---:|---:|---:|---:|---:|
| **Real (what happened)** | −$210 | −$335 | −$345 | −$155 | **−$1,045** |
| Zone-edge-break | +$823 | +$1,352 | +$1,367 | +$1,029 | +$4,570 |
| Cap −50% only | +$904 | +$1,486 | +$1,501 | −$232 | +$3,659 |
| Cap −70% only | +$823 | +$1,352 | +$1,367 | +$1,029 | +$4,570 |
| TP1(+100%)+runner | +$948 | +$1,579 | +$1,756 | +$946 | +$5,228 |
| Hold-to-15:20 (PENDING, mtm@11:39) | +$1,616 | +$2,673 | +$2,688 | +$1,754 | +$8,730 |

Every rule that removed or widened the stop shows a large paper gain **as of the 11:39 data cutoff**,
because SPY rallied from 767.8 to 772.9+ within the analysis window. This is a single session's
realized path, not a distribution — see §5.

## 4. Wave 1 vs wave 2 — two different mechanisms, two different answers

- **Wave 1 (770C/772C): the cap was correct in the near term.** SPY did not merely chop after the cap
  fired — it kept falling to 767.78 by 10:11–10:15, a genuine breach of the 768.56 zone floor. A
  zone-respecting structure stop (which never had the chance to fire under the real premium-cap exit)
  would have fired at 10:06 anyway, at a **worse** price than the cap achieved (−$228/−$444/−$429/−$163
  vs the cap's realized −$147/−$310/−$295/−$100). The only way any of these four legs profits is
  holding through that second leg down with **no stop of any kind**, all the way into the later rally —
  i.e. betting the whole loss budget on an unknowable subsequent recovery. The −70% cap and the
  zone-edge-break rule land on the *same* worse exit for three of four legs, because the same 10:06 SPY
  drop crosses both thresholds at once.
- **Wave 2 (768C/770C): the real stop was a whipsaw, not a structural break.** The real structure stop
  used the raw trigger level (768.00) and fired on a 4-cent breach (5m close 767.96 < 768.00) at 10:36.
  But the **zone-adjusted floor for that same level is 767.616** — and the 5m close never went below
  767.96 in the whole observed session, so a zone-respecting version of the same rule would **never
  have fired**, matching the SYNTHESIS.md H5 finding (structure stops whipsaw-prone; today's 10:36 exit
  named there as the example) with a concrete number: the point-vs-zone gap on this trigger is 34.4
  cents of SPY, and SPY's post-stop low (767.96, i.e. the stop-triggering print itself) never
  approached the zone floor at all. Bold-2's wave-2 leg (770C, cheaper premium, wider % swings) is the
  one exception where the −50% cap *would* have fired anyway shortly after 10:36 in the APPROX region —
  everything else on wave 2 rides untouched to the cutoff.

## 5. Why this is not a rule-change recommendation

- **n=1 session, two waves, eight legs.** No confidence interval, no OOS split, no drop-best-day test
  is possible on a single day's hindsight reconstruction. SYNTHESIS.md (this morning, same audit)
  already found that every entry-tick rule tested trades winners for losers at roughly 1:1 and flips
  sign with one day removed — this analysis cannot and does not overturn that with one more day.
- **Survivorship bias is the whole mechanism here.** Every "hold" scenario above wins *because* SPY
  happened to rally hard after 10:36 today. SYNTHESIS.md's H4/H5 findings (the "orphan band," 79 real
  structure-stop exits where SPY reclaimed the trigger 56–79% of the time within 15–60 min, and the
  profit-lock-arm test that went **negative** in the most recent quarter, 08-18..09-02, −$327) already
  quantify how often the opposite happens: the stop fires and price does NOT come back. Removing or
  loosening these stops on the strength of one good afternoon is exactly the "result-shopping on seen
  data" pattern the standing audit explicitly refuses.
- **The wave-2 point-vs-zone finding is real and additive evidence for F3** (the already-queued
  "persist the zone width in force per trigger, pre-register the grid" forward instrument in
  SYNTHESIS.md §3), not a new proposal. It sharpens F3's prereg with a live number (34.4 cents on this
  trigger) rather than licensing an immediate live change — config is frozen until 2026-10-30 in any
  case, and this session is read-only on the trading path by its own charter.

## 6. Caveats

- Data window ends 09:30–11:39 ET. Hold-to-15:20 is reported as **PENDING**, the running
  mark-to-market as of 11:39, not a realized outcome — the actual 15:20 price is unknown and not
  guessed at.
- Runner-rule modeling is a disclosed simplification: TP1 fraction 0.8 for Safe-type arms (safe-2,
  safe-3 by analogy) / 0.667 for Bold-type arms (bold-2, risky-1 by analogy) per `params.json` /
  `aggressive/params.json`; after TP1, Safe arms trail 15% off the running high (chandelier, arms
  immediately since price is already >>+5%), Bold/risky arms move to a flat breakeven stop at entry
  (no trail — `aggressive/params.json` carries no `profit_lock` key, confirming "Bold runs no
  chandelier"). This is the task's own named counterfactual rule (+100% TP1), not the live config's
  actual TP1 threshold (which is +50%/+75% per `params.json`/`aggressive/params.json` — read but not
  used here since the task specifies +100%).
- BS-proxy minutes have 1-minute price/timing granularity (matches the underlying SPY tape's own
  resolution) — a threshold crossing inside a proxy gap is reported at the first per-minute tick where
  the modeled price is at/below threshold, which can overshoot the exact crossing price by up to one
  minute's move. Real-quote-tape segments (FACT) do not have this limitation (~20s native cadence).
- All P&L figures use the achievable bid at the decision tick, consistent with how `premium_stop` and
  `structure_stop` actually execute (off `worst_premium`); no separate slippage/spread model is applied
  on top of that for the BS-proxy segments (a single theoretical fair value stands in for both bid and
  ask there).
- Fleet-arm risk profile mapping (safe-3→"Safe" TP1 fraction/chandelier, risky-1→"Bold" TP1
  fraction/breakeven) is an assumption by naming convention, not verified against each arm's own
  exit-manager config (fleet `exit-state.json` for both arms is currently `{}`, flat, no in-force
  runner state to read).
