# Playbook — Project Gamma

> Named setups with explicit context, trigger, entry, stop, and target. Every entry here is earned from real evidence, not theorized.
>
> **Numeric values (premium stop, TP1 multiplier, vol multiplier, time gates, qty tiers) are NOT canonical here — they live in [`automation/state/params.json`](../automation/state/params.json).** When you change a value in this file, change params.json in the same edit. Drift between this file and params.json is detected at premarket Step 1a (rule-version pin check) and creates a kill-switch.

**Version:** 1.0 setup library (BEARISH_REJECTION CONFIRMED, BULLISH_RECLAIM PAPER-ELIGIBLE)
**Rule version:** v14 — see [`automation/state/params.json#rule_version`](../automation/state/params.json) for canonical
**Last updated:** 2026-05-08

---

## How a setup gets into this playbook

1. J describes a real trade with the pattern.
2. Setup written using the Setup Template, status **draft**.
3. Setup needs **at least 3 confirming real-trade examples** with the same trigger before status moves to **confirmed**.
4. Setup needs **20 paper trades clearing thresholds in `risk-rules.md`** before status moves to **live-eligible**.
5. Setups that fail thresholds get retired, not loosened.

---

## Setups

### Setup name: BEARISH_REJECTION_RIDE_THE_RIBBON (PUTS)

**Status:** **CONFIRMED (3 of 3 examples successful) → paper-testing phase**

**Origin / sample:**
| Date | Contract | Entry | Exit (avg) | P&L | % return | Management quality |
|---|---|---|---|---|---|---|
| 2026-04-29 | SPY 710P 0DTE | $1.67 | $2.24 | +$342 | +34% | Compromised (working) |
| 2026-05-01 | SPY 721P 0DTE | $0.325 (avg of 2 legs) | $0.56 | +$470 | +72% | Mixed (anticipation entry on leg 1) |
| 2026-05-04 | SPY 721P 0DTE | $0.85 | $1.58 | +$730 | +86% | Clean (full ribbon ride) |

**Total sample:** 3 winners. Floor return +34%, ceiling +86%. The variance is explained almost entirely by management discipline (ribbon-ride vs. compromised exits).

**Hypothesis:** When SPY tests a defined resistance level and rejects it, AND the EMA ribbon flips bearish at the rejection, the next leg lower can be ridden via the EMA ribbon as a dynamic trailing stop. The trade compounds gamma during the leg — the deeper the move, the faster the premium gain on 0DTE puts.

### Context filters (all must be true)
- Time of day: 09:35 ET or later (premarket levels defined; full chart context available).
- SPY structure: bearish — multi-day downtrend in play, OR clear intraday lower-highs forming a descending trendline ≥2 touches, OR premarket level acting as defined resistance.
- EMA ribbon on the trade timeframe (3-min default): bearish-colored at trigger time. **Price wick below ribbon does NOT qualify — the EMA lines themselves must be reordered (Fast < Pivot < Slow).**
- No major scheduled news in next 30 min (FOMC, CPI, NFP, mega-cap earnings).
- Daily loss budget remaining > planned $-risk.
- **Ribbon spread ≥ 30 cents (Fast EMA to Slow EMA).** A compressed ribbon (< 30 cents) means the market is in equilibrium/chop. Do not enter directional plays in a compressed ribbon.
- **No volume divergence on the breakdown bar.** If a breakdown bar is followed within 1–2 bars by a recovery bar with equal or higher volume, the breakdown has failed — do not enter.
- **VIX confirmation (added 2026-05-05):** For puts, VIX should be rising OR already above 20 at time of entry. A flat or falling VIX as SPY tests resistance = options market is not pricing fear = weaker setup. VIX rising toward / above 20 as SPY rejects a level = strong bearish confirmation. VIX below 15 = do not enter puts (market too complacent, premiums too thin, moves fizzle). Pull VIX quote on every entry evaluation.
- **J can watch the chart for the next 1–2 hours.** If J knows he can't watch, downgrade management to a hard premium target (see "Reduced-attention variant" below).

### Trigger (must have ≥ 2 of 3 firing simultaneously)
1. **Level rejection.** SPY tests a defined level (premarket high, descending trendline, prior horizontal resistance) and prints a rejection candle — close back below the level after touching. On 3-min timeframe: a single confirmed rejection candle (often paired with a yellow sell-triangle indicator print).
2. **EMA ribbon flip.** Ribbon transitions from bullish-stack (cyan/blue) to bearish-stack (red/yellow). The "break" through the ribbon is J's preferred entry timing.
3. **Confluence with multi-day or premarket structure.** Multi-day descending trendline, premarket high, or prior day high all aligning at the same level.

**Anticipation entries are forbidden.** The events listed above must have just printed.

### Contract selection
- DTE: 0
- Strike: ATM or 1st OTM put.
- Premium target: $0.50–$2.00 entry zone.
- Order type: limit at mid; reassess in 30s if not filled. Don't chase if SPY has moved against entry > 0.10.

### Stop
- **Premium stop:** **v14 ratified `-8%` (entry × 0.92).** Source of truth: [`automation/state/params.json#premium_stop_pct`](../automation/state/params.json). Was -50% in v1, tightened through v9 (-33%) → v10 (-10%) → v14 (-8%) by backtest sweep. The -8% level was chosen because it strictly dominates -10% on all user criteria simultaneously (total $4,731 vs $4,375, W/L 2.93x vs 2.57x, max DD smaller, same WR). **Drift check: premarket Step 1a verifies prompt + params.json match.**
- **Chart stop:** SPY closes a 3-min candle **above** the rejected level + $0.50 buffer (params.json#chart_stop_buffer_dollars). Ribbon condition removed in v11 (tested worse). Setup is dead.
- **Time stop:** Out by 15:50 ET. No 0DTE held into the close.

### Target / exit — RIDE THE RIBBON (primary management)

Locked at TP1 = +30% premium (params.json#tp1_premium_pct) based on `strategy/scale-out-math.md` analysis. Banks meaningful profit; doesn't clip the natural runner; +30% is reachable on every trade in the n=3 confirmed sample. **TP1 fallback to chart-level (next Active/Carry tier level past entry, $1.50 min distance, no round numbers) per v11 ratification — whichever fires first.**

**TP1 (sell 2 of 3 contracts):** when **either** of these fires first —
- Premium ≥ entry premium × 1.30 (i.e., +30% gain), OR
- SPY reaches first major intraday support level from `today-bias.json`.

**After TP1 fires:**
- Move runner stop to **breakeven** (premium = entry premium).
- Runner now risk-free; rides the ribbon for the home-run leg.

**Runner exit (any of these → market sell remaining ⅓):**
- 3-min candle closes back **into** the EMA ribbon (yellow band).
- Bounce signature: long lower wick + green follow-through candle.
- Premium ≥ entry × 3.0 (massive runner — take it).
- Time stop 15:50 ET.

**Fallback rule (the small-trade catcher):**
- If a runner-exit signal fires **before** TP1 has been hit → **exit ALL 3 contracts** at the signal price.
- This is the path for small-magnitude trades (like 5/1 where premium maxed at +22%) that never reach +30% TP1 but still produce a positive ribbon-exit.
- Without this rule, small trades get stranded on the way to a stop. With it, every trade either pays at TP1 or pays at signal exit.

### Reduced-attention variant (if J can't watch)

If J knows in advance he won't be able to watch the chart in real time, **downgrade the management rule** rather than violate the ribbon-trail by accident:

- Set a **premium-take-profit GTC order at +50% of entry premium for ⅔ of the position** (mechanical TP).
- Set a **premium-stop at -50% for the full position** (mechanical stop).
- Runner: trail via a hard premium target at +100% if hit, otherwise time-exit by 15:30 ET.
- Acknowledge in the journal pre-trade: *"reduced-attention mode active — ribbon trail not in effect."*

This caps both the upside and the downside, but it removes the "I was working and missed the move" failure mode that ate into the 4/29 result.

### Position sizing (per `risk-rules.md`)

| Account size | Contracts | Structure | Approx % deployed at $1.00 entry |
|---|---|---|---|
| $1K – $2K | **3** | 2 TP + 1 runner | 30% |
| $2K – $5K | **4** | 2 TP + 2 runners | 25% |
| $5K – $10K | **6** | 4 TP + 2 runners | 18% |
| $10K – $25K | **10** | 6 TP + 4 runners | 12% |
| $25K+ | **15+** | 10 TP + 5 runners | 10% |

- **As account grows: contract count up, % deployed down.** Survival rules (50% per-trade cap, -50% premium stop) hold at every size.
- 50% per-trade $-risk cap is the ceiling, not the target. Target deployment is the % column above.
- Gamma computes exact $-risk and % of account before every entry; trade rejected if over.

### Stats (filled in over time)

**Real-money sample (pre-rules, n=3):**
- Trades: 3
- Winners: 3 (100%)
- Avg %-return on capital deployed: +64%
- Floor: +34% (compromised management)
- Ceiling: +86% (clean ribbon ride)

**Paper sample (rules applied, target n=20):**
- Trades: 0
- Win rate: TBD
- Avg R: TBD
- Notes: TBD

---

### Setup name: BULLISH_RECLAIM_RIDE_THE_RIBBON (CALLS)

**Status:** **PAPER-ELIGIBLE (J override 2026-05-06) — paper trades enabled despite < 3 confirmed real-trade examples. Mirror logic to bearish setup is sound enough to test on paper. Observation count still tracks toward live-deployment threshold.**

**Origin / sample:**
| Date | Time | Setup | Result | Notes |
|---|---|---|---|---|
| 2026-05-05 | 10:20 ET | SPY 0DTE call setup at 721.49–722.00 reclaim | **Not traded** (no playbook entry yet) | Open 722.13, low 722.01 (after 10:15 bar tested 721.79), close 723.19, vol 82,407 (4× morning avg). Full reversal candle. Launched the entire bullish day to 725.04. Paper-validated example #1. |

**Total sample:** 1 paper-validated observation. Need 2 more before status moves to `confirmed → paper-testing`.

**Hypothesis:** Direct mirror of `BEARISH_REJECTION_RIDE_THE_RIBBON`. When SPY tests a defined support level and reclaims it, AND the EMA ribbon flips bullish at the reclaim, the next leg higher can be ridden via the EMA ribbon as a dynamic trailing stop. The trade compounds gamma during the leg — the deeper the move, the faster the premium gain on 0DTE calls.

### Context filters (all must be true)
- Time of day: 09:35 ET or later (premarket levels defined; full chart context available).
- SPY structure: bullish — multi-day uptrend in play, OR clear intraday higher-lows forming an ascending trendline ≥2 touches, OR premarket level acting as defined support, OR oversold reversal off a multi-day swing low.
- EMA ribbon on the trade timeframe (3-min default, 5-min current): bullish-stacked at trigger time. **Price wick above ribbon does NOT qualify — the EMA lines themselves must be reordered (Fast > Pivot > Slow).**
- No major scheduled news in next 30 min (FOMC, CPI, NFP, mega-cap earnings).
- Daily loss budget remaining > planned $-risk.
- **Ribbon spread ≥ 30 cents (Fast EMA to Slow EMA).** Compressed ribbon (< 30 cents) = chop, no entry.
- **No volume divergence on the reclaim bar.** If a reclaim/breakout bar is followed within 1–2 bars by a sell bar with equal or higher volume, the reclaim has failed — do not enter.
- **VIX confirmation (mirror of bearish setup):** For calls, VIX should be **FALLING** OR already below 17.20 baseline at time of entry. A flat or rising VIX as SPY tests support = options market pricing fear = weaker setup. VIX falling toward / below 15 as SPY reclaims a level = strong bullish confirmation. **VIX above 22 = do not enter calls** (market too fearful, breakouts get sold). Pull VIX quote on every entry evaluation.
- **J can watch the chart for the next 1–2 hours.** Reduced-attention variant: switch to mechanical TP/SL targets.

### Trigger (must have ≥ 2 of 3 firing simultaneously)
1. **Level reclaim.** SPY tests a defined support (premarket low, ascending trendline, prior horizontal support, multi-day swing low) and prints a reversal candle — close back above the level after touching/wicking through. On the trade timeframe: a single reversal candle with **wide range, opens low, closes near high, volume ≥ 1.5× recent average**. Today's 10:20 AM bar is the canonical example: open 722.13, low 722.01, close 723.19, vol 82K vs ~25K avg.
2. **EMA ribbon flip.** Ribbon transitions from bearish-stack (red/yellow) to bullish-stack (cyan/blue). The "break" through the ribbon is the preferred entry timing.
3. **Confluence with multi-day or premarket structure.** Multi-day ascending trendline, premarket low, prior day low, or multi-day swing low all aligning at the same level.

**Anticipation entries are forbidden.** The events listed above must have just printed.

### Contract selection
- DTE: 0
- Strike: ATM or 1st OTM call.
- Premium target: $0.50–$2.00 entry zone.
- Order type: limit at mid; reassess in 30s if not filled. Don't chase if SPY has moved 0.10 against entry.

### Stop
- **Premium stop:** **v14 ratified `-8%` (entry × 0.92).** Source of truth: [`automation/state/params.json#premium_stop_pct`](../automation/state/params.json). Mirror of bearish stop — same value, same backtest provenance. **Drift check: premarket Step 1a verifies prompt + params.json match.**
- **Chart stop:** SPY closes a 3-min candle **below** the reclaimed level + $0.50 buffer (params.json#chart_stop_buffer_dollars). Ribbon-flip-back exit requires opposite-stack + 30c spread (params.json#ribbon_flip_back_*) — not just MIXED transition (chop = no real bias).
- **Time stop:** Out by 15:50 ET. No 0DTE held into the close.

### Target / exit — RIDE THE RIBBON (primary management)

Same math as bearish version (`scale-out-math.md` analysis applies symmetrically).

**TP1 (sell 2 of 3 contracts):** when **either** of these fires first —
- Premium ≥ entry premium × 1.30 (i.e., +30% gain), OR
- SPY reaches first major intraday resistance level from `today-bias.json`.

**After TP1 fires:**
- Move runner stop to **breakeven** (premium = entry premium).
- Runner now risk-free; rides the ribbon for the home-run leg.

**Runner exit (any of these → market sell remaining ⅓):**
- 3-min candle closes back **into** the EMA ribbon (yellow band).
- Rejection signature: long upper wick + red follow-through candle.
- Premium ≥ entry × 3.0 (massive runner — take it).
- Time stop 15:50 ET.

**Fallback rule:**
- If a runner-exit signal fires **before** TP1 has been hit → **exit ALL 3 contracts** at the signal price.

### Reduced-attention variant (if J can't watch)

Same as bearish version — set a +50% GTC TP for ⅔ position, -50% premium stop full position, runner trails at +100% target or 15:30 ET time-exit.

### Position sizing

Same as bearish version (per `risk-rules.md`). 50% per-trade $-risk cap, 3 contracts at $1K-$2K, scaling table applies.

### Why DRAFT and not CONFIRMED

Per playbook policy (line 14): "Setup needs at least 3 confirming real-trade examples with the same trigger before status moves to confirmed." J has not provided real winning trades on the bullish side yet. The 5/5 10:20 AM example is paper-validated (we observed the setup fire and watched it work) but not real-traded.

**Path to confirmation:**
1. Need 2 more paper-validated observations of this exact pattern firing AND working (price moves favorable from entry trigger).
2. Each observation gets logged like the bearish 3-trade reconstruction was — a row above with date, level, result, notes.
3. After 3 paper-validated wins, status promotes to `confirmed → paper-testing` (parallel to bearish setup's current state).
4. After 20 paper trades clearing thresholds, promotes to `live-eligible`.

**During DRAFT phase:**
- Setup is **eligible for autonomous paper trading** by Gamma — same rules, same filters, same sizing.
- Each paper trade outcome is logged toward the 20-trade live threshold.
- Mistakes file gets red-flag entry if filters aren't followed strictly.

### Stats (filled in over time)

**Paper sample (rules applied, target n=20):**
- Trades: 0
- Win rate: TBD
- Avg R: TBD

**Paper-validated observations (toward 3-example confirmation):**
- 1 (2026-05-05 10:20 AM) — 721.49–722.00 reclaim, vol 82K (4× avg), launched full bullish day to 725.04
- 2 (2026-05-11 ~10:05 AM) — 738.10 bull flag break during MCP outage window. Flagpole = opening V-launch. Flag = tight consolidation. Break = 738.10 reclaim with volume. Price ran to 739.59. Would have been a winner on +30% TP1 within 2-3 bars. (DRAFT setup, not auto-traded — observed via journal reconstruction)

---

## Setup ideas / candidates (NOT YET TRADABLE)

### CANDIDATE — `ORB_RETEST_LONG` (CALLS) — watch-only, OP-21 gate 0/3 live wins

**Status:** WATCH-ONLY 2026-05-21 — watcher running live, accumulating observations. NOT YET TRADABLE until 3+ J live wins confirmed (OP-21 gate).

**Evidence:** 16-month deduped (N=32): WR=81.2%, P&L=+$976, 5/6 quarters positive. Walk-forward OOS/IS Sharpe ratio=0.667 (PASS). Real-fills N=22 OPRA cases WR=81.8% with chart-stop-only (L64). See leaderboard #4.

**Pattern:** SPY breaks above the 30-min opening range high (ORH), pulls back to within $0.20 of ORH from above, closes above ORH on a green bar → entry. State machine: BREAKOUT → WAITING_RETEST → RETEST_HELD (entry signal).

**Quality gates (wired in watcher, no heartbeat feature needed):**
- OR range < $2.00 (MAX_OR_RANGE=2.00; wide ORBs return None internally)
- Direction: LONG ONLY (ORB_DIRECTION_FILTER="long"; shorts suppressed)
- Confidence: medium only (high=$-198/9 fires — consensus trap; medium=$+589/86 fires — +EV)
- Entry window: 10:00–12:30 ET (MAX_BARS_AWAIT_RETEST=8 after breakout bar)

**Exit rules (non-standard vs BEARISH_REJECTION):**
- Stop = chart stop at ORH (SPY close < ORH − $0.05). Premium stop = −0.99 (chart-stop-only per L64)
- TP1 = ORH + 50% × or_range (0.5R projection). qty_fraction = 0.50
- Runner = ORH + 100% × or_range (1.0R projection). BE stop after TP1
- NO ribbon-flip exit (ribbon may be MIXED during retest; chart stop is the invalidation)
- Profit-lock chandelier v15 applies. Time stop 15:50 ET

**Promotion path:**
1. 3+ J live wins on ORB_RETEST_LONG
2. Move this block to the live `### Setup name:` section above
3. Uncomment heartbeat.md execution block (see `strategy/candidates/_analysis/2026-05-24-orb-heartbeat-integration-spec.md`)
4. J weekend ratification (Rule 9)

---

### CANDIDATE — `STAIRSTEP_CONTINUATION` (PUTS or CALLS)

**Status:** OBSERVED 2026-05-07 — pattern named after the missed 735.40 sequence. n=1 paper observation, 0 real-money. NOT YET TRADABLE.

**Origin / sample:**
| Date | Pattern | Result | Notes |
|---|---|---|---|
| 2026-05-07 | LH-LH-LH at broken 735.40 (736.12 → 735.61 → 735.41) → SPY -$5.65 to 729.75 | Not traded | System bought calls at 12:30 instead of puts (counter-trend trap). J's eye saw the pattern; system didn't. |

**Hypothesis:** When a key level breaks AND each subsequent retest from the broken side prints a progressively lower high (or higher low for support flip), the level has rotated from defending to capping. Once 3+ rejections form a strict sequence, continuation in the broken direction is the high-edge trade.

**Trigger conditions (need ≥ 2 of 3):**
1. **Sequence count:** `bounce_history.length ≥ 3` at a level with `role: "broken_to_resistance"` (or `_to_support`).
2. **Strict monotonic highs:** all `high_reached` values are strictly decreasing (or low_reached strictly increasing for support flip).
3. **Confirming bar:** last closed 5m bar's close is on the broken side AND red (for bear) / green (for bull).

**Why this matters:** This is the pattern J's intuitive eye reads. The codified rules track it now via `bounce_history[]` in `key-levels.json` and the `sequence_rejection` / `sequence_reclaim` triggers in heartbeat filter 10. Once 3+ paper observations confirm, promote to CONFIRMED setup.

**Path to confirmation:** Need 3 paper-validated observations of this exact pattern firing AND working. Each gets logged like the 4/29-5/1-5/4 reconstruction.

---

### CANDIDATE — `LEVEL_SWEEP_SNIPE` (CALLS on support sweep / PUTS on resistance sweep)

**Status:** OBSERVED 2026-05-11 — n=1 live observation. NOT YET TRADABLE. WATCH-ONLY.

**Origin / sample:**
| Date | Time | Direction | Level | Sweep bar | Recovery | Notes |
|---|---|---|---|---|---|---|
| 2026-05-11 | 10:30 ET | BULL (calls) | 737.60 (bull flag — 9:35 bar close) | O 738.44 H 738.69 **L 737.59** C 738.42 Vol **154K (~10× avg)** | +83¢ within single candle | Price flushed BELOW 737.60, absorbed sellers, closed back above. Next bars: 738.61→739.18. ATH would have been target. |

**Hypothesis:** When SPY sweeps BELOW (or above) a pre-identified key level on a single 5m bar with extremely high volume (≥3× avg), then CLOSES BACK ABOVE (or below) the level on the SAME bar, the sweep was a liquidity grab — stops below the level got cleared, institutional buyers absorbed the supply. The wick low IS the hard stop. The entry is the close of the sweep bar (or next bar open). Reward/risk is asymmetric: stop is the exact wick low (known), target is the next major level.

**What makes this different from SUPPORT_UNDERSHOOT_REVERSAL:**
- Happens within a SINGLE BAR (no 1-2 bar sequence needed)
- Volume threshold much higher: ≥3× avg (today: 10×) vs 1.3× for undershoot
- Entry is the sweep bar's CLOSE or next bar open — not waiting for subsequent bar confirmation
- Stop is mechanical: wick low − $0.05 (exact sweep point). Tight and defined.

**What makes this different from BULLISH_RECLAIM:**
- BULLISH_RECLAIM waits for ribbon to fully flip + ≥2 of 3 triggers
- LEVEL_SWEEP_SNIPE fires on VOLUME ALONE at a pre-identified level — ribbon is context, not gate
- Entry is earlier (sweep bar close) with a tighter stop (wick low vs. level − $0.50)
- Higher conviction required on the LEVEL itself — must be premarket-identified or multi-touch

**Context filters (all must be true):**
- Level is pre-identified in `today-bias.json` or drawn by J before the bar fires. Round numbers do NOT qualify.
- Sweep bar volume ≥ 3× 20-bar average on the 5m chart.
- Bar CLOSES back on the entry side of the level (close above level for calls; below for puts). A wick-only touch that closes ON the wrong side = NOT a sweep snipe, wait for next bar.
- Time gate: ≥ 10:00 ET (standard entry gate).
- No active position already open.

**Trigger (single bar, ALL 3 required):**
1. Bar wicks THROUGH a pre-identified key level by ≥ $0.20 (meaningful sweep, not a tick).
2. Bar closes BACK on the correct side of the level.
3. Volume ≥ 3× 20-bar avg on that bar (absorption, not just noise).

**Entry / stop / target:**
- Entry: next bar open (safest) or sweep bar close if it's clearly recovering
- Stop: wick extreme − $0.05 (for calls: wick LOW − $0.05; for puts: wick HIGH + $0.05)
- TP1: +30% premium OR next major chart level above entry (whichever first)
- Runner: ribbon trail per BULLISH/BEARISH_RECLAIM rules

**Path to confirmation:**
- Need 3 paper-validated observations (current: 1)
- Backtest: add `sweep_snipe` trigger to `backtest/lib/filters.py`, test against 16-month window
- Must clear: total P&L > 0, WR ≥ 45%, W/L ≥ 1.5×

**J note (2026-05-11):** "that wick on the 10:30 candle is such a snipe. I want us watching those." — added to watch list. Heartbeat should log anytime this fires for watcher replay grading.

---

### CANDIDATE — `NAMED_LEVEL_SECOND_TEST` (CALLS on support / PUTS on resistance)

**Status:** WATCH-ONLY 2026-06-18 — Case study #1 confirmed live. NOT YET TRADABLE until 3+ observations with tracked outcomes.

**Origin / sample:**
| Date | Time | Dir | Level | Test #1 | Test #2 low | Result | Notes |
|---|---|---|---|---|---|---|---|
| 2026-06-18 | 11:45 ET | BULL | PML 743.35 | 09:45: L:743.86, bounced $1.34 | 11:45: L:744.36 (+$0.50 higher low) | 11:50: H:746.40, +$2.04 move | Bold BULLISH_RECLAIM stopped out 11:04 — this was a SEPARATE setup, independent lock |

**Hypothesis:** When SPY tests a named ★★+ support (PML, PDL, Carry, Active) and bounces, then re-tests the same level forming a **higher low** (second wick > first wick by ≥ $0.30), the second test is institutional absorption — dark pool buy wall absorbed two waves of selling. A green reversal bar on the second test + volume spike on the next bar = entry.

**What makes this DISTINCT from BULLISH_RECLAIM:**
- No ribbon flip required (ribbon may be BEAR/MIXED)
- No multiple-trigger requirement (level + higher low is the complete thesis)
- Entry is the second test's reversal bar close, not a ribbon transition
- Stop is tight and mechanical: second wick low − $0.10

**Trigger conditions (ALL 3 required):**
1. A named ★★+ support was tested earlier today — SPY wicked to within $0.75 of the level and bounced ≥ $0.50 (first test confirmed)
2. Second test reaches within $0.75 of the level AND the wick low is ≥ $0.30 above the first test's low (higher low = structure holds)
3. Second test bar closes green (close > open) AND volume on the NEXT bar exceeds the surrounding 5-bar average by ≥ 20%

**Entry / stop / target:**
- Entry: second test bar close or next bar open
- Stop: second test wick low − $0.10 (mechanical, tight — typically $0.20–$0.50 SPY risk)
- TP1: $0.70 SPY above entry OR next named resistance level (whichever is closer)
- Runner: PMH / next major resistance if TP1 hit first

**Critical distinction from first_entry_lock:**
This setup carries the name `NAMED_LEVEL_SECOND_TEST` — entirely separate from `BULLISH_RECLAIM_RIDE_THE_RIBBON`. A BULLISH_RECLAIM stop-out does NOT block this setup. The heartbeat's isolation guarantee (see heartbeat.md First-entry-after-stop section) ensures per-setup-name independence. These are distinct risk hypotheses: ribbon-flip trend-following vs. level-accumulation mean-reversion.

**Watcher link:** `backtest/lib/watchers/floor_hold_bounce_watcher.py` (WATCH_ONLY) is the existing code that detects this class of setup. Today's 11:45 case study should be logged there as observation #1.

**Path to confirmation:**
- Need 3 paper-validated observations (current: 1 — 2026-06-18)
- Backtest: scan 16-month historical data for "named support tested twice same session, second test forms higher low ≥ $0.30" — check hit rate and P&L
- Must clear: WR ≥ 50%, W/L ≥ 2.0 (tight stop amplifies R:R)
- FLOOR_HOLD_BOUNCE watcher replay backtest = primary validation path

---

### CANDIDATE — `RESISTANCE_OVERSHOOT_REVERSAL` (PUTS) / `SUPPORT_UNDERSHOOT_REVERSAL` (CALLS)

**Status:** OBSERVED 2026-05-07 — bull trap to 736.11 before reversal. n=1, NOT YET TRADABLE.

**Origin / sample:**
| Date | Pattern | Result | Notes |
|---|---|---|---|
| 2026-05-07 | 11:35 break 735.40 to 736.11 on light vol → 11:40 wick 736.12 close 735.84 → 11:50 close back below 735.40 → -$5.65 reversal | Not traded (system offline 11:35-12:04) | First break of multi-touch resistance is often a stop-hunt, not a breakout. The OVERSHOOT signal fires within 1-2 bars when the breakout reverses. |

**Hypothesis:** When SPY breaks above a multi-touch resistance level on LIGHT volume (vol < 1.3× avg) and within 1-2 bars closes back below the level, the breakout was a liquidity grab. Stops above the level get hit, then sellers re-engage. The "trap" has fixed risk (long-side stops cleared) and asymmetric reward (room to fall to next support).

**Trigger conditions (need all 3):**
1. **Breakout-then-reverse:** Bar N high > level, bar N+1 or N+2 close < level.
2. **Light-vol breakout:** Bar N volume < 1.3× 20-bar avg (the breakout itself was thin).
3. **Heavy-vol reversal:** Bar N+1 or N+2 volume ≥ 1.3× 20-bar avg (sellers stepping in).

Mirror for support undershoot: SPY breaks below support on light vol, closes back above within 1-2 bars on heavy vol = stop-hunt below + buyer re-engagement.

**Why this matters:** Today's 11:35-11:50 sequence at 735.40 is the textbook example. System was offline so didn't capture; need 3 more observations before adding to live triggers.

---

### CANDIDATE — `TRENDLINE_BREAK_VOLUME` (PUTS on ascending break / CALLS on descending break)

**Status:** n=2 observations (2026-05-08, 2026-05-11). NOT YET TRADABLE. Pattern splitting from original TRENDLINE_BREAK_RETEST — the "pure volume break" variant is cleaner and doesn't require a horizontal level retest.

**J note (2026-05-11 ~12:40 ET):** "review that trend line break on the chart now look how clean that is. we need to be watching those! volume and trend line break, this is clean." — this is the core signal: VOLUME + TRENDLINE BREAK. No retest required.

**Origin / sample:**

| Date | Time | Direction | Trendline | Break bar | Vol | Result | Notes |
|---|---|---|---|---|---|---|---|
| 2026-05-08 | 14:55 | BEAR (puts) | Ascending, anchors 5/7 15:30 $733.94 → 5/8 15:45 $738.92, slope $0.21/hr, 3+ touches | O 736.58 H 736.73 **L 736.10** C 736.37, vol **51,960** | ~1.3× avg | Not traded (system blind to drawings) | Price bounced 736.11 within 5 min — break was a scalp |
| **2026-05-11** | **12:40** | **BEAR (puts)** | **Ascending from 737.59 (10:30 ET), 9+ higher lows over 2hr, slope ~$0.18/5min** | **O 740.10 H 740.13 L 738.84 C 739.17, vol 134K** | **~3× avg** | **Outcome TBD (MCP down at close)** | **CLEAN setup per J — volume confirmed, no ambiguity on the break** |

**Hypothesis:** When SPY breaks an ascending (or descending) trendline that has been respected for ≥ 3 bar-touches, AND the break bar has volume ≥ 2× 20-bar average, the structural bias has shifted. The break itself — not a subsequent retest — is the entry signal. High volume on the break bar confirms institutional participation, not noise. The previous sub-variant (break + horizontal level retest) was a refinement; the core pattern is simply: **trendline touched 3+ times → close through it on elevated volume → enter direction of break.**

**Why this is cleaner than the retest variant:** The 5/8 example required waiting for a horizontal level retest, which introduces ambiguity (does the level hold or fail?). Today's 12:40 bar needed no retest — the 129¢ flush on 3× volume IS the signal. Waiting for retest on a strong break means missing the initial move.

**Context filters (all must be true):**
- Trendline drawn by J OR auto-detected with ≥ 3 confirmed swing-point touches.
- Trendline respected for ≥ 30 minutes of RTH bars (not a 1-bar construction).
- Break bar volume ≥ 2× 20-bar average. (Today: 3×. 5/8: 1.3× — borderline.)
- 5m bar CLOSES through the trendline by ≥ $0.10 (not just a wick — today: 740.10 open, 739.17 close, ~$0.90 break).
- All standard time gates (no entry < 10:00 ET, no entry 14:00–15:00 ET).
- Ribbon context: ribbon does NOT need to have flipped — the break bar often precedes the ribbon flip. Watch ribbon for confirmation but don't wait for it.

**Trigger — ALL 3 required:**
1. **Trendline close-through:** 5m bar closes on the broken side by ≥ $0.10.
2. **Volume ≥ 2× 20-bar avg** on the break bar.
3. **Trendline had ≥ 3 prior touches** (so it was a real, tested line — not an arbitrary line through 2 points).

**Entry / stop / target:**
- Entry: break bar close (aggressive) or next bar open (conservative)
- Stop: above the break bar HIGH + $0.10 (for puts) / below bar LOW − $0.10 (for calls)
- TP1: +30% premium OR next major support level from `today-bias.json`
- Runner: ribbon trail per BEARISH_REJECTION doctrine once ribbon confirms flip

**Today's 12:40 example sizing:**
- Break bar close: 739.17. Stop: above 740.13 + $0.10 = 740.23. Risk: ~$1.06 on SPY.
- Target: 738.71 (SMA50, already partially hit at 738.84 wick). Next: 737.60, then 736.13.
- Entry on puts at break bar close → even if just targeting SMA50, that's $0.46 SPY move = meaningful premium gain on 0DTE.

**Path to confirmation:**
- Need 3 observations with tracked outcomes (current: n=2, outcome #2 TBD)
- Backtest: add `trendline_break_volume` trigger to `backtest/lib/filters.py`
- Must clear: total P&L > 0, WR ≥ 45%, W/L ≥ 1.5×
- Trendline detection via `backtest/lib/trendlines.py` must agree with J's drawn lines on replay

**Awareness-only until confirmed.** Heartbeat logs when pattern fires. J tracks outcome manually until 3 observations with outcomes are in the table.

---

### CANDIDATE — `PRE_FOMC_DERISK_DRIFT` (CONTEXT, NOT A SETUP)

**Status:** PATTERN MEMO — informs `macro_pre_event_bias` filter, not a standalone setup.

**Origin / sample:**
| Date | Pattern | Result |
|---|---|---|
| 2026-05-07 | FOMC 14:00 — SPY drifted 735.40 → 729.75 (-$5.65) over 11:35-13:30 | Hard veto would have prevented 12:30 BULL counter-trend trade |

**Hypothesis:** On days with high-severity macro events (FOMC, CPI, NFP, PCE), institutional unwinding starts 90-180 min before the print. The 4 hours pre-event are dominated by de-risking, not directional thesis. Counter-trend setups (bull setups when bias bearish, OR vice versa) have terrible expectancy in this window.

**Mechanism (ALREADY ACTIVE in heartbeat.md as of 2026-05-07 v2):** Macro Bias Inheritance with HARD VETO tier (event ≤ 120 min) blocks counter-trend entries. SOFT MODIFIER tier (120-240 min) raises the score threshold by 1.

**Why this matters:** Today's 12:30 -$45 BULL trade is the canonical example. Under the v2 rule it would emit `SKIP_MACRO` instead of ENTER_BULL.

---

## Retired setups

- *(empty)*
