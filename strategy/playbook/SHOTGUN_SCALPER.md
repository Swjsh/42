# Setup: SHOTGUN_SCALPER (PUTS or CALLS)

> **Status: DRAFT — WATCH-ONLY** (created 2026-05-15 from J's 09:41:51 ET P738 trade)
>
> Numeric values (premium stop, profit-lock ladder, time stop, qty tiers) are NOT canonical in this doc — they will live in [`automation/state/params.json`](../../automation/state/params.json) once promotion begins. This file defines the SETUP. params.json defines the KNOBS. Drift between the two is a kill-switch event per OP 4.

**Rule version target:** v15.x (post-ratification)
**Authoring date:** 2026-05-15 (evening, after live observation)
**Last validated:** 2026-05-16 morning — 3 detector bugs fixed, full historical replay graded.
**Parent doctrine:** [`strategy/playbook.md`](../playbook.md), [`doctrine/seed10095-exit-doctrine.md`](../../doctrine/seed10095-exit-doctrine.md)
**Operating principles invoked:** OP 14, 16, 17, 20, 21, 22

---

## 2026-05-16 morning validation update — read first

After Stage 1 grinder surfaced 0 keepers across 939 combos, three architectural detector bugs were found and fixed:

1. **Tier 3 bullish bias.** Original detector iterated `for kind in ("low", "high"): if best: break` — returned on the first kind that produced a candidate, locking in bearish bias (29 short / 0 long in 16 weeks of historical replay despite an uptrend). Fix: collect candidates across BOTH kinds, score by `touches × 10 + span_bars`, return best.

2. **Tier 2 sparse-levels gap.** Tier 2 requires named levels to fire and was fed only the 4 levels from `key-levels.json`. Historical replay produced 0 Tier 2 fires. Fix: opt-in `auto_derive_intraday_levels=True` (used by the watcher adapter) adds SESSION_HIGH/LOW, RTH_OPEN_PRICE, ROLLING_30/60MIN_HIGH/LOW so Tier 2 has anchors.

3. **Tier 1 over-firing.** Original detector fired Tier 1 OPEN_REJECTION on EVERY bar after 09:30 that closed below the open — produced 214 Tier 1 fires per session over the 16-week window. Fix: once-per-session gate (no prior bar already triggered) + 30-min decay window (must fire within first 6 bars).

**Historical replay after all 3 fixes (Apr 15 – May 15, 1,794 RTH bars, single-exit doctrine, default exit knobs):**

| Tier_Direction | n fires | Total P&L | Exp/fire | Verdict |
|---|---|---|---|---|
| T1_short | 9 | −$67 | −$7.45 | slight neg (rare) |
| T2_long | 86 | −$200 | −$2.33 | slight neg |
| T2_short | 36 | −$88 | −$2.43 | slight neg |
| T3_long | 191 | −$581 | −$3.04 | NEGATIVE |
| **T3_short** | **168** | **+$418** | **+$2.49** | **POSITIVE — only +EV slice** |
| **Combined** | **490** | **−$518** | **−$1.06** | overall neg |

**Filtered to T3_short-only would yield +$418 / +$2.49 expectancy.** Filtered to T1_short + T3_short = **+$351 / +$1.98 expectancy across 177 fires.** Bullish setups across all tiers are net negative historically — they may be cherry-picking by the chop-leaning market in this window.

**Implication for live promotion (per OP 21):**
- Tier 1 + Tier 3 BEARISH ONLY may be promotion-ready after walk-forward validation.
- Bullish setups (T2_long, T3_long) need their own iteration before promotion.
- Stage 2 grinder is currently testing whether knob extensions + relaxed gates can change this picture.

---

## One-line summary

**Fast, single-exit, live-trigger 0DTE scalp on the FIRST clean rejection at a named level — entered on the live cross (not closed-bar), held minutes-not-hours, profit-locked via chandelier ladder, dead by 12 minutes.**

---

## Concept narrative — why this strategy exists

### The gap

On 2026-05-15, three things happened that exposed a structural blind spot in the existing playbook:

1. **09:41:51 ET — J's live trade.** J manually bought P738 @ $1.51 mid-dump bar. SPY was actively rejecting from a 740.x area down toward the 738.10 Carry. By 09:46 ET J was up **+93%**, premium ~$2.92, SPY wicked to **737.96** (touching the Carry tag). J held looking for more; SPY bounced to 739.83 by 09:55 ET. The +93% peak round-tripped to break-even.

2. **09:46:38 ET — engine's trade (same direction, same idea).** Heartbeat tick fired on the CLOSED 09:45 bar. Bought P740 @ $3.14 — **5 minutes late, $1.63 worse on entry premium, OTM-2 strike picked from the deeper-equity rule.** SPY had already tagged the 738.10 Carry and reversed. Trade stopped at -20% premium, net **-$770**.

3. **14:55 ET — clean Tier-3 setup, totally missed.** Intraday ascending trendline broke at the 741.77 multi-touch level, retest of 741.77 from below, ribbon already flipped bearish. 55-minute dump from 741.62 → 737.44. Engine took zero. The closed-bar gate held it back; ribbon-spread filter was OK but no live trigger fired on the retest tick.

The common theme: **the existing playbook scores LEVEL INTERACTIONS at closed-bar resolution, then sizes them as full ribbon-ride trades.** That's the right call when J is going to hold for a multi-hour leg. It's the wrong call when the trade is a quick rejection scalp where the entire profit window lives in 6-10 minutes between the rejection touch and the first counter-bounce.

### What SHOTGUN_SCALPER fills

SHOTGUN_SCALPER is the answer to "J just took a fast scalp at a level — formalize it." It is deliberately **narrow** in scope and **fast** in lifecycle:

- **Live trigger, not closed-bar.** The trigger is the price interaction itself — wicking into a level, breaking a trendline live, opening-bar rejection. The current 5m closed-bar discipline (per L34 lesson) is correct for RIBBON-RIDE trades. It is wrong for SCALPS. SHOTGUN_SCALPER runs on the live tick.
- **Single exit, no runner.** Closes 100% on the first hit of a profit-lock or hard target. J's actual failure mode on 5/15 was holding for more; the doctrine codifies "take the whole thing, move on."
- **12-minute time stop.** Either it works fast or it doesn't work. No second-half-of-the-hour drag.
- **OTM-1 only.** Cheap enough to lever the move, close enough to ATM that gamma actually fires.
- **No confluence requirement.** This is the OPPOSITE design from BEARISH_REJECTION_RIDE_THE_RIBBON. The named level alone is the thesis. Adding ribbon + trendline + HTF requirements turns this back into a ride-the-ribbon trade.

### What it is NOT (anti-mission)

It is not a replacement for ride-the-ribbon trades. It is a **separate signal class** that fires at different times, on different sizing, with different exit doctrine. The two can coexist on the same chart on the same day. They should never compete for the same fill — SHOTGUN_SCALPER closes inside 12 minutes; if a real ribbon-ride trend develops, the heartbeat takes that next.

---

## The three trigger tiers

SHOTGUN_SCALPER has exactly three triggers. No fourth tier sneaks in. Adding a fourth is a doctrine change, not a tweak.

### Tier 1 — `OPEN_REJECTION`

**Definition:** The first 5m RTH bar (09:30–09:35 ET) prints a rejection candle at a named overnight or premarket level, AND price has crossed back through the level intra-bar.

**Mathematical trigger (evaluated continuously inside the 09:30–09:35 window on the LIVE tick stream):**

```
let L = nearest named level in [Active, Carry, PMH, PML, PDH, PDL, ONH, ONL]
        within distance_filter <= $1.50 from current_price
let direction = "PUT"  if price tagged L from below and rolled back below
                "CALL" if price tagged L from above and reclaimed above
let rejection_distance = abs(bar_high_or_low - L)   # extreme wick distance from level
let body_recovery     = abs(current_price - extreme) # how far back from the wick we are

TRIGGER fires when:
    rejection_distance >= $0.20    # meaningful wick, not a tick
    AND body_recovery >= $0.15      # already reversing, not still at extreme
    AND L is a NAMED level (not a round number, OP 5)
    AND L has been touched >= 1 prior session OR is auto-tagged PMH/PML/PDH/PDL/ONH/ONL
    AND time_now in [09:30:30, 09:34:55]  # not at the very edges
```

**What counts as "rejection":** The level was touched (within $0.05 of price) on this bar, and the live tick is now ≥ $0.15 back away from the extreme on the correct side. The bar does NOT need to be closed.

**False-positive avoidance:**
- Round numbers (738.00, 740.00, 750.00) are **disqualified** as the named level (OP 5). They are awareness-only.
- If the price re-tags the extreme within 60 seconds of the trigger firing, the trigger is **cancelled** (extreme not respected — wait for next bar).
- If VIX is moving in the WRONG direction during the rejection (VIX flat/down on a put rejection; VIX up on a call rejection), trigger is **suppressed** for this bar.

### Tier 2 — `LEVEL_REJECT_LIVE`

**Definition:** Any time during RTH, any named level in `today-bias.json` is tagged on the live tick, AND price wicks through and recovers on the SAME live tick stream, AND a prior multi-touch defense of this level exists in `bounce_history`.

**Mathematical trigger (evaluated continuously, 09:35:00 → 15:00:00 ET):**

```
let L = any named level in today-bias.json with role in
        ["Active", "Carry", "PMH", "PML", "PDH", "PDL", "ONH", "ONL", "trendline_anchor"]
let touches_today = count of bounce_history entries on L this session
let recent_extreme = min/max(price over last 90 seconds)
let recovery = abs(current_price - recent_extreme)

TRIGGER fires when:
    abs(recent_extreme - L) <= $0.10     # genuine tag, not a near-miss
    AND recovery >= $0.20                 # already $0.20 back from the wick
    AND touches_today >= 1                # this isn't the level's first appearance
       OR L.role in ["Active", "Carry"]   # auto-qualified by tier
    AND VIX_delta_15m supports direction  # rising VIX for PUTs, falling for CALLs
    AND time_now NOT in macro_blackout    # see filter checklist
```

**What counts as "rejection":** Within a rolling 90-second window, the high (for puts) or low (for calls) tagged the level within $0.10, and the live tick is now at least $0.20 back from that extreme on the correct side. This is the **live equivalent** of a wick-rejection candle, evaluated continuously, not at bar close.

**False-positive avoidance:**
- Trendlines: only "anchor" trendlines with ≥ 3 prior chart-touches qualify. Freshly-drawn 2-point lines do NOT (per OP 5 spirit — needs proof of respect).
- If price has crossed L in the prior 5 minutes more than twice, the level is **chopping** and is disqualified for the next 10 minutes (no scalps in active battlegrounds).
- If a prior SHOTGUN_SCALPER on the SAME level already stopped out today, the level is dead for SCALPER triggers (rule 4 — no re-entry on a stopped-out setup).

### Tier 3 — `TRENDLINE_BREAK_RETEST`

**Definition:** An intraday trendline with ≥ 3 prior touches breaks on volume (≥ 1.5× 20-bar avg), price extends away $0.20–$0.60, then RETESTS the trendline from the broken side on a fresh tick AND rejects.

**Mathematical trigger (live, evaluated on the tick stream):**

```
let TL = ascending or descending trendline in chart-state with touches >= 3
let break_bar = first 5m bar that closed across TL by >= $0.10
let break_vol = volume on break_bar
let extension_low_high = min(price) for desc-break / max(price) for asc-break since break_bar
let retest_distance = abs(current_price - TL_at_now)

TRIGGER fires when:
    break_bar was within last 30 minutes
    AND break_vol >= 1.5 * 20-bar avg
    AND extension_distance >= $0.20  # the break extended; this isn't a fakeout
    AND retest_distance <= $0.15      # we're back at the line
    AND live tick shows rejection AWAY from TL by >= $0.10
    AND direction matches break direction
       (ascending TL broken down -> PUT; descending TL broken up -> CALL)
```

**What counts as the trigger event:** The retest tick. Not the break bar. The break establishes the bias; the retest tick gives the entry with a defined stop (above/below the trendline by a small buffer).

**False-positive avoidance:**
- If the retest tick has already exceeded the break-bar extreme on the wrong side, the trade is **dead** (level has flipped back, not held as new resistance/support).
- "Trendline" here means a line J or the auto-detector drew that has been respected — not an ad-hoc line through any two pivots.
- Maximum 1 SHOTGUN_SCALPER Tier-3 entry per trendline per session. After it fires, that trendline is consumed.

---

## Entry rules

| Component | Rule |
|---|---|
| **Instrument** | SPY 0DTE only |
| **Strike** | OTM-1 (one strike out-of-the-money from current SPY at trigger). No ATM, no OTM-2, no ITM. The OTM-1 selection is what makes this a scalp, not a directional bet. |
| **Quantity (Safe)** | **3 contracts**, no exceptions, single leg. |
| **Quantity (Bold)** | **5 contracts**, no exceptions, single leg. |
| **Order type** | Marketable limit at the live ask + $0.02 (immediate-or-cancel if available; reassess in 15 seconds if not filled, do NOT chase past +$0.05 of original ask). |
| **Entry timing** | The instant the trigger fires on the live tick stream. No "wait for bar close." No "wait for confirmation." This is the entire point of the setup. |
| **Re-entry** | If the trigger fires again on a DIFFERENT named level (Tier 2) or a DIFFERENT trendline (Tier 3) later in the session, that is a new trade. Same level / same trendline / already stopped = DEAD per rule 4. |
| **Live tick definition** | Mid-point of bid/ask on SPY underlying, sampled at heartbeat frequency. |
| **Pre-entry sizing math** | Mandatory: $-risk, % of equity, premium %. Logged to journal BEFORE order is submitted. |

---

## Exit rules

The exit doctrine is **deliberately different** from BEARISH_REJECTION_RIDE_THE_RIBBON / BULLISH_RECLAIM_RIDE_THE_RIBBON. This is the most important section of the doc.

### Target identification

The PRIMARY target is the **next named level past the entry point in the direction of the trade**, capped at $1.50 distance from entry on SPY. Examples:

- PUT entry at SPY 740.20 after rejection at 740.50 → primary target is the next Carry/Active/PML below 740.20, up to 738.70 (1.50 cap).
- CALL entry at SPY 736.80 after reclaim of 736.50 → primary target is the next Active/Carry/PDH above, up to 738.30.

If no named level exists within $1.50 of entry on the correct side, the target falls back to **+50% premium gain** as the hard cap. That's the SHOTGUN ceiling — beyond +50% gain, the gravity of the next named level isn't pulling us anymore and we're guessing.

### Profit-lock ladder (chandelier ratchets)

Single exit at primary target. UNTIL the primary target is hit, the position is managed by a chandelier ratchet on the premium:

| Premium gain reached | Stop floor moves to |
|---|---|
| +25% | Entry (break-even — no losing winners) |
| +50% | Entry × 1.20 (+20% locked) |
| +75% | Entry × 1.40 (+40% locked) |
| **Primary target hit** | **Market sell 100% — close the trade** |

The ladder is **one-way**. Once a rung is achieved, the floor never moves back down. If price retraces from +75% back through +50%, the floor stays at +40% — it does not drop back to +20%.

**Why one-shot exit, no runner:** J's 5/15 failure mode was the runner mentality on a setup that should have been a scalp. Encoding "no runner" prevents the +93% → 0% round-trip. The data on the existing ribbon-ride setups already covers the runner case (seed 10095 exit doctrine). SHOTGUN_SCALPER explicitly does NOT replicate it.

### Hard stops

| Stop | Trigger |
|---|---|
| **Premium stop** | Entry × 0.80 (premium drops -20%). Mechanical. Set on order submit. |
| **Chart stop** | SPY moves $0.20 beyond the level on the wrong side on a sustained live tick (≥ 30 seconds). Setup is invalidated — exit immediately. |
| **Time stop** | **12 minutes from fill**, no exceptions. The whole thesis is fast. After 12 minutes, either the move worked or it didn't. Close the trade. |
| **EOD stop** | 15:50 ET hard, but in practice every SHOTGUN_SCALPER is done well before. |

If a chandelier rung has already locked in profit and the time stop fires, exit at the locked rung price (market) — that's a winner, log it as such.

---

## Filter checklist (ALL must hold at trigger time)

| Filter | Requirement | Why |
|---|---|---|
| **Time of day** | 09:30:00 ≤ now ≤ 15:00:00 ET (continuous window per v15.1) | Theta murders after 15:00 ET on 0DTE; pre-09:30 is no-trade |
| **Ribbon spread** | ≥ $0.30 (Fast EMA to Slow EMA, 5m) | Compressed ribbon = chop; SCALPER needs directional energy to develop |
| **Ribbon direction** | Does NOT need to be flipped yet | Scalpers FRONT-RUN ribbon flips — this is the design |
| **VIX direction (PUTs)** | VIX flat or rising over last 15 min | Fear pricing supports the trade |
| **VIX direction (CALLs)** | VIX flat or falling over last 15 min | Complacency supports calls |
| **VIX absolute (PUTs)** | VIX > 15 | Below 15 = no fear premium, scalp won't pay |
| **VIX absolute (CALLs)** | VIX < 22 | Above 22 = chop city, calls die |
| **Macro blackout** | NO macro event within ± 30 min (FOMC, CPI, NFP, mega-cap earnings) | Per playbook standard |
| **Daily kill-switch** | Account not halted (Safe -30% / Bold -50% rule 5) | Hard veto |
| **Daily SHOTGUN cap** | < 3 SHOTGUN_SCALPER fills already today in this direction | Prevents revenge / over-firing |
| **Account-specific (Safe)** | Trigger MUST be in `[OPEN_REJECTION, LEVEL_REJECT_LIVE]` only | Tier 3 (trendline retest) reserved for Bold initially |
| **Account-specific (Bold)** | All 3 tiers eligible | More aggressive book takes the broader signal set |
| **Existing position** | No open SPY 0DTE position of any kind | One trade at a time, rule 6 spirit |
| **Already-fired-and-stopped** | This named level / trendline has NOT already stopped out a SHOTGUN_SCALPER today | Rule 4 — no re-entry |
| **Chart data freshness** | Live tick within last 5 seconds; TV `data_get_ohlcv` validated against quote_get for skew | Per L34 |

---

## Anti-patterns (what SHOTGUN_SCALPER is NOT)

- **Not a trending trade.** If SPY is in a clean 2-hour leg with the ribbon stacked and HTF aligned, that's a ride-the-ribbon trade, not a SCALPER. Trade the right book.
- **Not a confluence trade.** SHOTGUN_SCALPER does NOT require ribbon flip + trendline + HTF alignment. Adding those gates kills the setup — confluence trades have different exit math (see `BEARISH_REJECTION_RIDE_THE_RIBBON`).
- **Not for chop days.** Ribbon < $0.30 spread, or 2+ level chops in the prior 5 min, → no SCALPER trades. Save it for the next directional impulse.
- **Not for distant levels.** If the nearest named level is > $1.50 from current price, there's no target structure within range. Skip.
- **Not for round numbers.** Per OP 5, round-number levels are awareness-only. They do NOT qualify as SHOTGUN_SCALPER trigger levels until they have 3+ confirmed chart-defenses.
- **Not for re-entries on the same level.** Stopped on 738.10 puts at 10:14? 738.10 is dead for SCALPER puts the rest of today.
- **Not a runner setup.** Every SHOTGUN_SCALPER closes 100% at primary target or chandelier rung. There is no runner. Adding one re-creates the 5/15 failure mode.

---

## Sizing & risk

### Premium % of equity (Safe account, $1K equity baseline)

| Strike entry premium | Qty | Total premium | % of $1K equity | % of $25K equity |
|---|---|---|---|---|
| $0.80 | 3 | $240 | 24% | 1.0% |
| $1.20 | 3 | $360 | 36% | 1.4% |
| $1.50 | 3 | $450 | 45% | 1.8% |
| $2.00 | 3 | $600 | 60% — **over cap** | 2.4% |

**Safe account hard cap:** trigger does NOT fire if entry premium × 3 > 30% of current equity. SHOTGUN_SCALPER inherits rule 6's per-trade cap.

### Premium % of equity (Bold account, $1K equity baseline)

| Strike entry premium | Qty | Total premium | % of $1K equity | % of $25K equity |
|---|---|---|---|---|
| $0.80 | 5 | $400 | 40% | 1.6% |
| $1.20 | 5 | $600 | 60% — **over cap** | 2.4% |
| $1.50 | 5 | $750 | 75% — **over cap** | 3.0% |

**Bold account hard cap:** trigger does NOT fire if entry premium × 5 > 50% of current equity.

### Daily kill-switch interaction

- SHOTGUN_SCALPER P&L counts toward the daily loss budget (Safe -30% / Bold -50%).
- A stopped-out SCALPER counts as 1 day-trade against PDT limits (rule 7).
- Maximum **3 SHOTGUN_SCALPER fills per direction per account per day**. After 3, that direction is closed for SCALPER for the day even if more triggers fire. Use the slots wisely.

### Per-setup cap rationale

3-per-direction (not 5, not 10) is the empirical guess pending backtest. The reasoning: in a typical RTH session there are ~3 high-quality named-level interactions per side. Allowing 10 would invite spam-firing on borderline triggers. Allowing 1 leaves too much on the table on multi-rejection days. 3 is the placeholder; the grinder (see backtest plan) will validate.

---

## Backtest plan

### What the grinder must test

A dedicated SHOTGUN_SCALPER grinder is required before any promotion (per OP 21). It cannot be inferred from existing BEARISH_REJECTION grinder results — the exit math is fundamentally different.

**Pipeline:** `backtest/autoresearch/shotgun_scalper_overnight_grinder.py` (Stage 1) → `shotgun_scalper_stage2_grinder.py` (refine) → `shotgun_scalper_stages345.py` (regime-robustness + sub-window stability + ratification). Orchestrator: `shotgun_scalper_pipeline.py`. Mirrors the SNIPER pipeline pattern (OP 23).

### Dimensions to sweep (Stage 1)

| Dimension | Range to sweep | Default |
|---|---|---|
| Rejection distance min (Tier 1) | $0.10, $0.15, **$0.20**, $0.25, $0.30 | $0.20 |
| Body recovery min (Tier 1) | $0.10, **$0.15**, $0.20, $0.25 | $0.15 |
| Tier 2 wick tolerance | $0.05, **$0.10**, $0.15 | $0.10 |
| Tier 2 recovery min | $0.15, **$0.20**, $0.25, $0.30 | $0.20 |
| Tier 3 volume mult | 1.3×, **1.5×**, 1.75×, 2.0× | 1.5× |
| Tier 3 extension min | $0.15, **$0.20**, $0.30, $0.45 | $0.20 |
| Premium stop | -15%, **-20%**, -25% | -20% |
| Chandelier rung 1 trigger | +20%, **+25%**, +30% | +25% |
| Chandelier rung 1 floor | entry, **entry** (BE) | BE |
| Chandelier rung 2 trigger | +40%, **+50%**, +60% | +50% |
| Chandelier rung 2 floor | +15%, **+20%**, +25% | +20% |
| Chandelier rung 3 trigger | +65%, **+75%**, +85% | +75% |
| Chandelier rung 3 floor | +35%, **+40%**, +45% | +40% |
| Time stop (minutes) | 8, 10, **12**, 15, 20 | 12 |
| Target distance cap | $1.00, **$1.50**, $2.00 | $1.50 |
| Fallback premium target | +40%, **+50%**, +60% | +50% |
| Daily fills per direction | 1, 2, **3**, 5 | 3 |
| Strike offset | ATM, **OTM-1**, OTM-2 | OTM-1 |

Total combinations (sparse grid): ~1500–3000. Pipeline matches SNIPER cadence.

### J-edge gates (per OP 16)

The 6 source-of-truth winning days and 4 losing days enumerated in CLAUDE.md OP 16 apply. SHOTGUN_SCALPER candidates must satisfy:

- `edge_capture = sum(scalper_pnl on 4/29 + 5/01 + 5/04) − sum(max(0, scalper_loss on 5/05 + 5/06 + 5/07_734C + 5/07_737C))`
- `final_score = edge_capture × aggregate_sharpe`
- `edge_capture ≥ 0.5 × max_possible` or candidate rejected
- 5/15 (today's data) explicitly added as a J-anchor day once journal is closed: **must net positive** on the scalper book.

### Validation requirements (per OP 20)

Before any "ready" claim:

1. Account-size assumption stated (qty=3 Safe / qty=5 Bold are the only assumptions; no scaling math fuzz).
2. Sample-bias disclosure: SHOTGUN_SCALPER is fitted to 5/15's signature pattern; OOS test is mandatory.
3. Walk-forward: train on ≤ 2025-Q4, test on 2026 YTD. Walk_forward_validate.py adapted with `--mode shotgun_scalper`.
4. Real-fills check on top-3 J anchor days using `simulator_real.py` — no BS sim allowed per L29.
5. Failure-mode enumeration: what does the WORST SHOTGUN_SCALPER day look like? Document.
6. Concentration disclosure: if top-N days drive X% of P&L, state X. SCALPER is by design many-small-trades-many-days; concentration > 50% means it's NOT scalping, it's something else.

### Sim accuracy gate (per L29)

SHOTGUN_SCALPER backtest MUST use `simulator_real.py` with OPRA fills. The setup trades OTM-1 strikes for 6-12 minutes — BS pricing error is catastrophic at these horizons. **No grinder result is publishable until OPRA-fills are confirmed for the trigger days.**

---

## Watch-only promotion path (per OP 21)

### Default knobs (DRAFT — watcher only, not live)

| Knob | Value |
|---|---|
| `qty_safe` | 3 |
| `qty_bold` | 5 |
| `strike_offset` | -1 (OTM-1) |
| `premium_stop_pct` | -0.20 |
| `chandelier_rung1` | (+0.25, breakeven) |
| `chandelier_rung2` | (+0.50, +0.20) |
| `chandelier_rung3` | (+0.75, +0.40) |
| `time_stop_minutes` | 12 |
| `primary_target_cap_dollars` | 1.50 |
| `fallback_premium_target_pct` | 0.50 |
| `tier1_rejection_distance_min` | 0.20 |
| `tier1_body_recovery_min` | 0.15 |
| `tier2_wick_tolerance` | 0.10 |
| `tier2_recovery_min` | 0.20 |
| `tier3_volume_mult` | 1.5 |
| `tier3_extension_min` | 0.20 |
| `max_fills_per_direction_per_day` | 3 |

### Observation file

`automation/state/watcher-observations.jsonl` gains records of type:

```json
{
  "watcher": "shotgun_scalper",
  "tier": "OPEN_REJECTION" | "LEVEL_REJECT_LIVE" | "TRENDLINE_BREAK_RETEST",
  "direction": "PUT" | "CALL",
  "level_name": "738.10_Carry",
  "trigger_time_et": "2026-05-15T09:41:47-04:00",
  "spy_at_trigger": 740.21,
  "rejection_distance": 0.32,
  "body_recovery": 0.18,
  "vix_at_trigger": 19.4,
  "vix_delta_15m": +0.6,
  "ribbon_spread": 0.41,
  "would_be_strike": 740,
  "would_be_qty_safe": 3,
  "would_be_qty_bold": 5,
  "would_be_entry_premium": 1.51,
  "outcome_pending": true
}
```

The replay grader (`automation/grading/watcher_grader.py`) walks the post-trigger bars and computes the outcome under the default knobs.

### Ratification gates (ALL required, per OP 21)

Promotion from WATCH-ONLY → PAPER-ELIGIBLE → CONFIRMED → LIVE-ELIGIBLE requires:

1. **3+ historical observations** that grade as wins under default knobs (replay over 2025+2026 backfill).
2. **3+ live observations** that J confirms as clean fires (no flag for "trigger was wrong" or "level was junk").
3. **Positive expectancy** on the 16-month full backfill.
4. **Per-tier expectancy positive** — Tier 1 / Tier 2 / Tier 3 each must clear independently, not just in aggregate.
5. **Per-quality scorecard** showing SHOTGUN_SCALPER COMPLEMENTS (not cancels) the existing ribbon-ride book. If the two strategies fire on the same day, the SCALPER must add positive P&L, not eat into the ribbon-ride's edge.
6. **Walk-forward validate** passes with held-out window.
7. **Real-fills** check passes on top-3 J anchor days.
8. **J explicit ratification** with signed-off rule version bump.

Each gate failure = back to grinder. No loosening defaults to make a fail-case pass (per OP 20).

---

## Worked examples (2026-05-15)

### Example 1 — OPEN_REJECTION (Tier 1) — J's actual trade

**Setup:** 09:30 RTH open ~740.5 area; price drove down toward 738.10 Carry.

**Trigger fire (would have, on live tick stream):** ~09:41:30 ET. Tier 1 OPEN_REJECTION pushed past its 09:35 cutoff, so this technically falls into Tier 2 (LEVEL_REJECT_LIVE) in the formal definition. Tier 2 trigger at 09:41:30:

- `recent_extreme` = ~$737.96 (the wick low touching 738.10 area later — actually still building)
- At 09:41:30 SPY ~$740.20 still dropping toward 738.10
- Tier 2 needs the wick to ALREADY have touched 738.10 within $0.10. At 09:41:30 that hasn't happened yet.

**Corrected example — what SHOTGUN_SCALPER would have done (counterfactual):** J's manual entry at $1.51 / 09:41:51 was an ANTICIPATION entry — he was buying the dump before the level was tagged. SHOTGUN_SCALPER explicitly does not do that. SHOTGUN would have waited for the actual wick at 09:46–09:50 (the 737.96 print touching the 738.10 Carry zone within $0.10) AND a $0.20 recovery away from the extreme on the live tick stream.

**Hypothetical fire at ~09:50 ET:**
- Trigger: Tier 2 LEVEL_REJECT_LIVE at 738.10 Carry
- SPY at trigger: ~738.30 (rebounded $0.34 from 737.96 wick low — clears `recovery >= $0.20`)
- Direction: PUT? **NO — this is a SUPPORT bounce, direction is CALL.**
- Strike: 738C (OTM-1 from 738.30)
- Entry premium est: ~$1.20–$1.50
- Safe qty: 3, Bold qty: 5
- Target: next named level above — 740.x ON resistance. Cap at $1.50 → 739.80.
- Time stop: 12 min from fill, ~10:02 ET.

**Actual outcome (counterfactual replay):** SPY bounced to 739.83 by 09:55 ET — that's a **+$1.50 SPY move** in 5 minutes. 738C OTM-1 would have ~doubled. SHOTGUN would have hit the +75% chandelier rung at ~$2.10 premium and likely the primary target at 739.80. **Estimated SCALPER P&L: +$200–$300 per contract** (Safe: +$600–$900; Bold: +$1,000–$1,500). One-shot exit. Done.

**Contrast with what actually happened:** J entered PUTS at 09:41:51 (anticipation), peaked +93%, gave it back. Engine entered PUTS at 09:46:38 closed-bar (5 min after the wick already happened), bought near the local low, stopped -20%. **Both real trades were on the WRONG side of the rejection event.** SHOTGUN's design (wait for the wick + recovery + correct direction) flips the result.

### Example 2 — TRENDLINE_BREAK_RETEST (Tier 3) — the 14:55 missed setup

**Setup:** Intraday ascending trendline anchored at the 09:50 low and 12:15 higher-low, 4 touches by 14:50. 741.77 multi-touch horizontal resistance overhead. Ribbon already stacked bearish on the 5m by 14:30.

**Break bar:** 14:50 5m bar closes through the ascending trendline by $0.18, volume 1.6× 20-bar avg. Bar low extends $0.22 below the line.

**Trigger fire:** 14:54:30 ET. Price retests the broken trendline from below, tags it within $0.12, ticks reject by $0.14.

- SPY at trigger: ~741.55 (just under retest of 741.62 trendline)
- Direction: PUT (asc TL broken DOWN → puts)
- Strike: 741P (OTM-1)
- Entry premium est: ~$1.10–$1.30
- Safe qty: 3, Bold qty: 5
- Target: next named support below — 740.50 Active. Cap at $1.50 → 740.05.
- Time stop: 12 min from fill, ~15:07 ET.

**Counterfactual outcome:** SPY dumped 741.62 → 737.44 over the next 55 min. By 15:07 (time stop hit at 12 min), SPY ~740.20-ish. 741P OTM-1 likely +60–80% premium. Chandelier rung 2 (+50% floor at +20%) had already locked. Primary target at 740.05 likely hit just before time stop. **Estimated SCALPER P&L: +$150–$250 per contract.**

**Note on Tier 3 scope:** Tier 3 is BOLD-ONLY in the initial promotion path. Safe takes Tier 1 + Tier 2 only until Tier 3 clears its independent expectancy gate per OP 21 promotion rule 4.

### Example 3 — LEVEL_REJECT_LIVE (Tier 2 chain) — the 15:45 break sequence

**Setup:** 15:45 ET 5m bar opens 740.25, drops to 738.94, breaks below 740 psych round-number (awareness only — NOT the trigger level). The REAL trigger level is 738.10 Carry, defended multiple times today.

**Trigger fire #1:** ~15:46:20 ET. SPY ticks 738.05 (touched 738.10 within $0.10), recovers to 738.30.

- Direction: CALL (support tag + recovery = bullish)
- BUT — VIX is rising aggressively at 15:46, V-spike on the dump
- **Filter check: VIX direction (CALLs) requires VIX flat or falling. FAIL.**
- **Trigger SUPPRESSED.** No entry.

**Trigger fire #2:** ~15:48 ET. SPY breaks 738.10 cleanly to the downside (738.10 stops defending). Price now at 737.85, falling further.

- Direction check: is this still a SHOTGUN trigger? **NO.** Once 738.10 has been broken cleanly (close 5m below by ≥ $0.10), it FLIPS roles. New SHOTGUN_SCALPER setups on this level would require it to be reclassified as resistance with a fresh sequence of touches. Not eligible in this same 30 min window.

**Trigger fire #3:** ~15:50 ET. SPY tags 737.44 — next named Carry below.

- Time-of-day check: now ≥ 15:00 → **DISQUALIFIED**. SHOTGUN_SCALPER window closed at 15:00 ET per filter table.
- No entry.

**Net SCALPER trades from this sequence: ZERO.** This is the correct outcome. The 15:45-15:55 window is a multi-level cascade in a thin late-day book — exactly the regime SHOTGUN_SCALPER should NOT trade. The filters correctly prevented engagement.

---

## Comparison vs. existing strategies

| Dimension | SHOTGUN_SCALPER | BEARISH_REJECTION_RIDE_THE_RIBBON | BULLISH_RECLAIM_RIDE_THE_RIBBON | SNIPER_LEVEL_BREAK |
|---|---|---|---|---|
| **Trigger type** | Live tick at named level | Closed 5m bar + ribbon flip | Closed 5m bar + ribbon flip | 5m bar close break of ★★+ level |
| **Trigger latency** | ~Live (seconds) | 5 min (closed bar) | 5 min (closed bar) | 5 min (closed bar) |
| **Confluence required** | NO (level alone) | YES (≥ 2 of 3 triggers) | YES (≥ 2 of 3 triggers) | NO (level break is sufficient) |
| **Ribbon requirement** | Spread ≥ $0.30 (any direction OK) | Stack flipped bearish | Stack flipped bullish | Bypasses ribbon gate |
| **Strike** | OTM-1 (fixed) | ATM or OTM-1 (param) | ATM or OTM-1 (param) | ATM or ITM-2 (param) |
| **Qty Safe** | 3 fixed | Tier-scaled | Tier-scaled | Tier-scaled |
| **Qty Bold** | 5 fixed | Tier-scaled | Tier-scaled | Tier-scaled |
| **Exit style** | Single-exit at target / chandelier ratchet | Tiered: TP1 (50%) + runner (50%) | Tiered: TP1 (50%) + runner (50%) | Profit-lock floor (entry × (1+offset)) |
| **Runner** | NO | YES (50% to 2× target) | YES (50% to 2× target) | YES |
| **Premium stop** | -20% | -20% (seed 10095) | -8% (v14) | Asymmetric per direction |
| **Time stop** | 12 minutes | 15:50 ET | 15:50 ET | 15:50 ET |
| **Time window (entry)** | 09:30 – 15:00 ET | 09:35 – 14:00 / 15:00 ET (v15.1) | 09:35 – 14:00 / 15:00 ET (v15.1) | 09:35 – 15:00 ET (v15.1) |
| **Daily cap** | 3 per direction | None (rule 5 still binds) | None | None |
| **Status** | DRAFT — watch only | CONFIRMED | PAPER-ELIGIBLE | DRAFT — watch only |

### Where SHOTGUN_SCALPER and RIBBON-RIDE setups overlap

Both fire on level rejections. The difference is **what happens AFTER the trigger**:

- RIBBON-RIDE expects a multi-hour leg. Exits are runner-friendly. Premium stop tolerates wobble.
- SHOTGUN_SCALPER expects a 6-12 minute scalp. Exits are single-shot. Time stop kills slow trades fast.

A given chart event can fire BOTH. When it does:

1. SHOTGUN_SCALPER fires first (live tick).
2. RIBBON-RIDE fires 5 min later (closed bar) IF the bar confirms.
3. SHOTGUN_SCALPER is **already closed** (12 min cap) before the RIBBON-RIDE develops.
4. They do not compete for the same fill. They are sequential, not parallel.

### Where SHOTGUN_SCALPER and SNIPER_LEVEL_BREAK overlap

Both bypass standard ribbon gates and let the level interaction BE the trigger. The difference:

- SNIPER trades BREAKS (the level fails). SHOTGUN trades REJECTIONS (the level holds).
- SNIPER allows ITM-2 strikes for richer deltas; SHOTGUN locks OTM-1 for cheaper scalps.
- SNIPER has a runner. SHOTGUN does not.

They are complementary: SNIPER catches the regime CHANGE, SHOTGUN catches the regime DEFENSE.

---

## Open questions (track and resolve before promotion)

1. **Anticipation vs. confirmation entries.** J's 5/15 entry was 5 min BEFORE the level got tagged. Should there be a Tier 0 "Anticipation" tier with separate stop/sizing? Currently: NO, anticipation is forbidden per rule 2. SHOTGUN waits for the wick + recovery. Grinder will validate whether J's anticipation edge is real or survivorship-biased.
2. **Tier 3 in Safe.** Reserved for Bold initially. If Tier 1+2 expectancy is strong, lifting Tier 3 to Safe is a v-bump decision per OP 21.
3. **Chandelier rung calibration.** +25/+50/+75 are educated guesses from the 5/15 chart movement. The grinder may produce +20/+45/+65 or +30/+60/+85 as the optimum. Pin to params.json once grinder ratifies.
4. **Time stop tightening.** 12 min is the placeholder. If 9 of 10 winners hit primary target inside 8 min, tighten to 10. If half the winners need the full 12, leave at 12.
5. **Volume confirmation on Tier 2.** Currently Tier 2 does NOT require a volume threshold on the rejection wick. Tier 1 and Tier 3 do (implicitly via VIX direction / break-bar volume). Grinder should sweep `tier2_volume_mult` ∈ {none, 1.2×, 1.5×} as a dimension.

---

## Audit trail

- **2026-05-15 ET evening** — Doc created from J's 09:41 P738 trade + engine's 09:46 P740 fail + 14:55 trendline miss. DRAFT status. Watch-only.
- **Next:** scaffold `lib/watchers/shotgun_scalper_watcher.py` mirroring `pinfade_watcher` pattern (single-fire detector, default knobs above, writes to `watcher-observations.jsonl`). Then `backtest/autoresearch/shotgun_scalper_overnight_grinder.py` for Stage 1. Both queued for after-4pm work block per OP 22.

---

## Cross-references

- [`strategy/playbook.md`](../playbook.md) — parent playbook, setup template, all existing setups
- [`doctrine/seed10095-exit-doctrine.md`](../../doctrine/seed10095-exit-doctrine.md) — exit knob lock for ride-the-ribbon (this setup uses DIFFERENT exits — do not conflate)
- [`automation/prompts/heartbeat.md`](../../automation/prompts/heartbeat.md) — current heartbeat filter logic (will need SHOTGUN_SCALPER branch added in v15.x)
- [`automation/state/params.json`](../../automation/state/params.json) — canonical knobs (SHOTGUN section to be added post-grinder)
- CLAUDE.md OP 14 (WR is not primary), OP 16 (J-edge gates), OP 17 (3-of-3 standard), OP 20 (non-theatre validation), OP 21 (watch-first promotion), OP 22 (don't stop cooking)
- L34 (closed-bar misalignment lesson — informs WHY SHOTGUN runs on live tick) — `docs/LESSONS-LEARNED.md`
