# Unvalidated-constants register (2026-08-12) — what the engine BELIEVES that nobody checked

> J: *"We never looked at the options contracts to know this information, so we didn't know one
> of our other tools needed sharpening. What other tools could fall under the same scenario?"*
>
> Sibling of [CAPABILITY-AUDIT](CAPABILITY-AUDIT-2026-08-12.md). That one asked **what can the
> engine not SAY?** This one asks **what does it BELIEVE that was never measured?**
>
> ⚠️ PROVENANCE. The dispatched parent agent returned a status placeholder and zero artifacts
> (190k tokens) — but its THREE sub-agents each delivered real sweeps, which arrived separately
> and are merged here. Everything in "MEASURED THIS SESSION" I ran myself and quote from a live
> command. Sub-agent findings are marked [SWEEP] and were spot-verified where load-bearing.

## The failure shape (from the exemplar)

`simulator_real.py:104-108` read: *"half-spread ~= 0.02-0.05… defensible for OPRA-feed
liquidity at common strikes."* A plausible, well-reasoned, **never-measured** guess, written
once and inherited by 255 call sites. Measured 2026-08-12: SPY 0DTE trades at the **penny
floor**, half-spread **$0.0104** — the default was **2x reality**.

**A constant justified by a comment rather than a measurement produces no error, no RED, no
anomaly — just quietly wrong numbers, forever.**

## MEASURED THIS SESSION

### 🚨 1. FEES ARE NOT MODELLED ON THE DIRECTIONAL PATH — and they are the same order as spread

| | |
|---|---|
| `simulator_credit.py` | ✅ models commission (`DEFAULT_COMMISSION`, $0.65/contract default, `:416`) |
| **`simulator_real.py`** (the directional 0DTE path we actually trade) | ❌ **no fee/commission term anywhere** |
| **Real fees charged** | **$40.44 over 313 fee rows / ~1,332 contract-sides = $0.0304/contract-side** (OCC Clearing Fee) |

**A 3-contract round trip pays ~$0.182 in fees.** Measured spread on the same trip is ~$0.06.
**Fees are ~3x the spread cost and are modelled as zero.** Every `simulator_real` P&L is GROSS,
not net. Note this cuts the OPPOSITE way from the slippage finding (which was 2x pessimistic):
the two partially cancel, and nobody has ever netted them against each other.
→ **Work order: add a fee term to `simulator_real`, and re-baseline slippage and fees TOGETHER
in one prereg'd commit.** Doing slippage alone would swing the numbers optimistic.

### 🚨 2. LATENCY — I WAS WRONG: it IS measured, and the number is alarming

I claimed "never measured." **False** — `analysis/pain-ledger/latency.json` has measured it
since 2026-08-01, n=30 fills on 08-12, and its own docstring says
*"INSTRUMENT ONLY -- descriptive, never load-bearing for any trading/gate decision."*
So it was measured, written down, and **nothing reads it.** That is worse than unmeasured.

**The measured pipeline (n=30, 2026-08-12):**

| hop | median | p90 |
|---|---:|---:|
| **bar close -> core verdict** | **424 s (7.1 min)** | **604 s (10.1 min)** |
| core verdict -> signal written | 117 s | 178 s |
| signal -> plan | 6.0 s | 7.9 s |
| plan -> submit | 0.50 s | 0.74 s |
| submit -> broker ack | 0.087 s | 0.092 s |
| broker ack -> fill | 0.133 s | 0.203 s |
| **TOTAL bar close -> fill** | **578 s (9.6 min)** | **727 s (12.1 min)** |

**Execution is not the problem — it is 0.7 s from plan to filled.** The problem is entirely
upstream: the engine takes a MEDIAN OF 9.6 MINUTES to act on a bar close, on a strategy whose
whole edge is 30-minute 0DTE moves and whose bars are 5 minutes long. **We are routinely acting
on a signal two bars stale.**

Why this matters beyond fidelity:
- It plausibly explains a chunk of J's "why didn't we get in at 09:50" — the engine's 09:35 bar
  produced a verdict at 09:45 and a fill at 09:46.
- Every replay assumes an instantaneous fill at the trigger bar, so **the harness models an
  entry we never actually get.** This is a systematic entry-price bias no calibration has ever
  accounted for, and it is in the OPTIMISTIC direction.
- The conviction score's C4 (range extreme) is computed at a price we are ~10 minutes late to.

### ✅ ROOT-CAUSED SAME NIGHT — the 424 s was mostly a MEASUREMENT ARTIFACT

**`bar_close_ts` is not a bar close. It is the bar's OPEN.** `fill_latency.py:138` maps it to
`trigger_bar_et`, and the engine writes that as the bar's opening timestamp. Proved three ways
on 2026-08-12: the engine logged `trigger_bar_et=09:45, spy=773.54`, and the 5-min bar
*labelled* 09:45 (spanning 09:45-09:50) closes at exactly **773.54**; same match for
09:35→772.88 and 09:40→772.81.

**Every hop measured from `bar_close_ts` is therefore inflated by one full bar period (300 s).**

| | reported | TRUE (−300 s) |
|---|---:|---:|
| bar close → core verdict | 424 s | **~124 s** |
| bar close → fill (fleet) | 578 s | **~278 s** |

**The tick-by-tick proves the engine is not slow.** Ticks 09:41-09:45 saw the 09:35 bar (bull 6,
no setup); 09:46-09:50 saw the 09:40 bar (bull 6, no setup); at **09:51:04** the 09:45 bar
became available, **bull jumped 6→10**, and the setup fired on the FIRST tick it could.
**The setup genuinely did not exist until that bar closed.** J's sniper entries are real and
earned, not luck.

What the true ~124 s actually decomposes into, and both parts are addressable:
1. **~64 s to pick up a bar that has already closed** (bar closes 09:50:00, first tick using it
   is 09:51:04). Polling/availability lag — worth a look, but a 1-min heartbeat can't do much
   better than ~60 s without a faster cadence or a push feed.
2. **~60 s lost to the FREE-MODEL VETO.** 09:51:04 fired `ENTER_BULL` → `VETOED_BY_MODELS`;
   09:52:04 fired the identical verdict → `PLACED`. **The veto layer cost a full minute of
   entry timing on this trade, then let the same trade through anyway.** This is a NEW cost of
   the veto lane, separate from its 31.2% accuracy problem — it delays entries it does not
   ultimately block. Fold into the veto kill/keep decision.

→ **Work orders:** (a) FIX THE INSTRUMENT — rename to `trigger_bar_open_ts` and add a derived
`bar_close_ts = open + bar_period`, so nobody re-reads a 300 s offset as engine lag (I did,
and reported 9.6 min to J before catching it); (b) quantify the veto's timing cost across the
population and add it to the veto ledger; (c) the entry-bias concern is much smaller than
stated — median trigger-bar-close→fill drift is $0.18, with a fast-move tail to $1.22.

### 3. `min_entry_premium = $0.30` — VALIDATED ✅ (the good case)
Backed by `analysis/recommendations/min-entry-premium-2026-07-31.json` **and** a
blocked-replay counterfactual. This is what a validated constant looks like, and it is the
comparison class for everything else here.

### 4. The `$12` level window (`heartbeat_core.py:436`) — UNVALIDATED
`abs(p - spy) <= 12` decides which levels the engine can even see. No scorecard. At SPY ~772
that is ±1.6%, which on a 0DTE horizon admits levels price cannot reach — diluting the level
set the new conviction score reads. Cheap to sweep now that conviction gives an objective.

## KNOWN FROM EARLIER WORK (carried in so the register is one list)

- **Paper fills charge no spread** — measured slip −$1.98 with a 90% CI of −$531..+$499 (268x
  the point estimate). "We pay no spread" is a property of Alpaca's simulator, not a
  measurement. Every paper P&L embeds this.
- **Ribbon 13/20/48 on 5-min = a 4-HOUR slow lookback** gating trades held ~30 min. The
  indicator is correct (34.4% BEAR over a month, right on real down days); the **timeframe
  match to our holding period was never validated**.
- **Harness runs 5-min bars; 1-min bars are FREE and entitled.** Residual replay error is
  dominated by intra-bar path ambiguity — this is the largest known fidelity gain available
  at $0.
- **VIX `entry_thresholds`** — documented VESTIGIAL, on no live path (verified twice
  2026-07-14). Dead constants that still read as live config.

## NOT SWEPT (named, not omitted)
Time gates (09:35 floor / 15:00 ceiling / 15:50 stop) · strike-tier offsets · warmup periods ·
level match tolerances + touch/proximity bands (J's zones-not-prices point — band width should
be a pre-registered A/B, never hand-picked) · `tp1_qty_fraction` · kill-switch fractions ·
`CONTEXT_BUNDLE_STALE_MIN` and the staleness windows generally.

## Ranked next actions

| # | action | why | effort |
|---|---|---|---|
| 1 | **Add fees to `simulator_real` + re-baseline fees AND slippage together** | fees are 3x spread and modelled as $0; fixing slippage alone swings optimistic | small |
| 2 | **Root-cause the 424 s bar_close->verdict hop** (latency is ALREADY measured — nothing reads it) | we act ~2 bars stale on a 5-min-bar strategy; replays model an entry we never get | small |
| 3 | **Move the harness to 1-min bars** | biggest known fidelity gain, $0, already entitled | medium |
| 4 | Sweep the `$12` level window | dilutes the conviction score's input set | small |
| 5 | Validate the ribbon timeframe against our real ~30-min holding period | a 4h gauge may simply be the wrong tool for the horizon | medium |

## [SWEEP] MERGED FROM THE THREE SUB-AGENT SWEEPS

### 🚨 A LIVE INCONSISTENCY, not merely unvalidated — three different trail values
`exit_manager.py:69 DEFAULT_TRAIL_PCT = 0.125` · `heartbeat_core.py:2333` per-setup fallback
**0.15** · CLAUDE.md prose says *"trails 15% off HWM"*. **Three values for one knob on one
path.** Which one binds depends on whether the strategy registry lookup succeeds. This is a
C14-class defect with a concrete blast radius — resolve it before any exit study is trusted.

### 🚨 `entry_cross_buffer = 0.03` — we cross 3x the measured spread
`heartbeat_core.py:2104` / `fleet_broker.py:250`: every live entry places a marketable limit
**3 cents** above the ask. Measured half-spread is **1.04 cents**. Bare constant, no
justification for 3c. It may cost nothing when we fill at the ask — but nobody has checked the
realized fill-vs-ask distribution, and at 3-5 contracts a systematic 2c overpay is real money
at our edge size. **Cheap to measure from fills we already own.**

### 🚨 An ADMITTED placeholder running live
`refresh_levels_intraday.py:134 ZONE_WIDTH_PCT = 0.0005` — the comment self-flags:
*"DEFAULT pending a pre-registered A/B study (never hand-picked)."* The study was never run;
the placeholder has been setting every level's reaction-zone width since. Directly relevant to
J's zones-not-prices doctrine.

### My own conviction score inherits an unvalidated threshold — flagging against myself
`conviction.py` C2 uses `memory_score >= 40`. **Production's level-memory merge uses
`MEMORY_MERGE_MIN_SCORE = 60.0`** (`refresh_levels_intraday.py:103`, itself bare). I picked 40
with no basis and it disagrees with the live producer. Worse: the whole level-memory wire was
graded **NEGATIVE_INSUFFICIENT_N** (n=3 changed trades, −$489.50) and stayed ON only because n
was below the 15-trade floor — so C2 rests on a mechanism that has never shown positive
evidence. Must be resolved before conviction weights are frozen.

### Other never-measured guesses worth ranking
- `pricing.py:55-58` **`iv = vix/100`** — the module docstring itself admits real ATM 0DTE IV is
  *"0.5-1.5x VIX depending on regime"*. The BS model discloses its own inaccuracy and was never
  calibrated against actual OPRA IV.
- `build_shared_signal.py:711-712` **`BULL_PEAK_THRESHOLD=9` / `BEAR_PEAK_THRESHOLD=8`** — round
  numbers deciding whether loose/bold arms trade a gate-blocked signal. No backtest cited.
- **Five staleness windows, none derived from a latency measurement**: `max_age_s=180`,
  `stale_min=6`, `STALE_AFTER_S=180`, `CONVICTION_ZONES_STALE_MIN=240`,
  `CONTEXT_BUNDLE_STALE_MIN=20`. **We now HAVE the latency distribution** (median 578 s
  bar->fill) — these should be derived from it rather than guessed.
- `filters.py:53-55` wick geometry — hand-fit to ONE anchor trade (J's 4/29). Only
  `wick_min_pct_of_range=0.50` was later swept and confirmed; the dollar tolerances were not.
- **Theta-decay curve** (`markdown/trading-knowledge/dte-iv-volatility.md:64`) — sourced to
  external blogs, never measured against our own OPRA fills, despite us owning the data.
- `option_pricing_real.py:259` **300 s bar-gap tolerance** — bare, no empirical basis.
- `max_distance = 2.0` for structure-stop anchoring — bare, duplicated across two independent
  implementations (`exit_manager.py:101`, `build_shared_signal.py:328`).

### MORE DEAD CONFIG (zero code consumers — reads as armed, is not)
**Liquidity-gate bundle** (6 keys: OI>=300, delta band, spread caps) and the **macro-veto
bundle** (4 keys) are both CONFIRMED DEAD per the `KNOWN_DEAD` registry — joining the already
known-vestigial VIX `entry_thresholds`. `vix_bear_hard_cap=23` is STALE_UNVERIFIED (0 fires all
summer). `vix_dir_deadband=0.05` appears in no study anywhere.

### The best-evidenced constants (the standard to hold others to)
`SIGHT_STALENESS_MAX_DIVERGENCE_USD=$1.00` (n=3,860 rows) · `ENTRY_CLAIM_TTL_SEC=180` ·
`HYSTERESIS_MISS_N=5` · the T+1 settlement model · the **V15 strike tier tables** (every
boundary cites a named prereg) · ribbon EMA 13/20/48 (fingerprinted against TradingView).
These prove the bar is reachable — most of the register simply never had it applied.

## The standing rule this produces

**Every numeric constant on a decision or simulation path needs a provenance tag: either a
scorecard path, or the literal word UNVALIDATED.** A code comment explaining the reasoning is
not evidence — the exemplar's comment was expert-sounding and 2x wrong. Re-run this register
whenever a new constant is introduced, and at every posture change (paper→live especially:
fees and spread are $0 in paper and real in life).
