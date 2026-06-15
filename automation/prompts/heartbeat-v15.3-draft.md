# heartbeat v15.3 — DRAFT change proposal

> **Status: DRAFT — not deployed. J ratifies on weekend per rule 9 + OP-24.**
>
> This draft proposes a NEW narrow trigger branch in `automation/prompts/heartbeat.md` that fixes
> the foot-gun behind Friday 2026-05-15's −$770 loss on a structurally-valid
> BEARISH_REJECTION_RIDE_THE_RIBBON: the v15.1 closed-bar rule (R1 fix 2026-05-14) systematically
> lags fast-V reversals at the RTH open by one full 5m bar, entering into developed bounce
> momentum.
>
> The fix specced in the Friday journal's `Next priority #1`:
>
> > Live-price trigger for RTH open-drive level breaks — add a branch in heartbeat for named ★★+
> > level crosses in the 09:35–09:45 window that uses live bid (Gamma-Bold style) rather than
> > waiting for bar close. Scope: PML/PMH/Carry levels only (high-conviction named levels).
>
> **What this draft DOES (the load-bearing change):**
> - Adds a NEW conditional trigger path: `live_price_first_bar_level_break` (BEAR) and
>   `live_price_first_bar_level_reclaim` (BULL). Scoped narrowly to:
>   - **Window:** 09:35 ET ≤ now_et < 09:45 ET (first 2 RTH 5m bars only)
>   - **Level types:** only `tier ∈ {Carry, Active}` levels with `stars ≥ 2` AND
>     `source` matching `/PMH|PML|premarket high|premarket low|Carry/i`. PML/PMH/Carry only.
>   - **Direction:** bilateral — level break (BEAR) or level reclaim (BULL)
>   - **Source of price:** live bid via `mcp__tradingview__quote_get` OR the in-progress 5m bar's
>     current price (allowed in THIS branch because it's a level-cross detector, not a candlestick
>     scorer — the close-back-margin check is unnecessary for level-cross firing)
>
> **What this draft does NOT change (everything else stays v15.1):**
> - All 10 BEARISH filters except they may now be evaluated against a live-price tick instead of the
>   last closed bar IF AND ONLY IF the live-price-first-bar trigger fired
> - All 11 BULLISH filters with the same conditional substitution
> - VIX gates (filter 8), ribbon/spread gates (5, 6), HTF score-modifier (10), volume gate (9 —
>   uses the most recent 20-bar avg from the last closed bar)
> - Sizing tiers, strike per-tier, exit doctrine, profit-lock chandelier, time stop 15:50 ET
> - Closed-bar rule (R1 v15.1 fix) — STILL APPLIES to every trigger outside the first-bar window
>   AND to every trigger except `live_price_*` inside the window
> - Source of truth for params (still `params.json`)
> - Setup names (BEARISH_REJECTION_RIDE_THE_RIBBON and BULLISH_RECLAIM_RIDE_THE_RIBBON only —
>   no new playbook entry)
>
> **The branch IS NOT a relaxation of v15.1.** It is a NEW trigger path that adds ONE specific
> firing condition (named-level cross on live price) in a 10-minute window at the RTH open. Every
> other filter and every other gate from v15.1 still has to pass. The branch can only fire entries
> that v15.1 would also have eventually fired — earlier by ~5 minutes — when the level cross is
> the real bearish/bullish impulse and the bar that confirms it is the same bar where the
> reversal completes.

---

## Production line-number citations (from `automation/prompts/heartbeat.md` as of 2026-05-17)

The current production heartbeat has the following load-bearing structure around triggers:

- Line 214: closed-bar filter on the 3-bar SPY 5m read (R1 v15.1 fix)
- Line 226-228: re-states the closed-bar rule for the score-time read
- Line 311: opens the Entry branch (`if current-position.status == null`)
- Line 313: opens "First-entry-after-stop check" gate sequence
- Line 328-330: opens "Scoring" block
- Line 332-342: 10 BEARISH filters (filter 1 = time gate; filter 10 = `≥1 of 4 triggers`)
- Line 344-349: TRIGGER DEFINITIONS (the 4 BEAR triggers: level_reject / ribbon_flip /
  multi_day_confluence / sequence_rejection)
- Line 351: parenthetical mirror for BULL triggers (sequence_reclaim definition)
- Line 353-364: 11 BULLISH filters (filter 1 = time gate; filter 11 = `≥2 of 4 triggers`)
- Line 392: the decision: `both pass + triggers → side with more triggers (tied = neither, log conflict)`
- Line 426-440: `Pre-execution gate sequence` table (G5/G7/G1/G2/G10/first_entry/G6/G6b)

The proposed v15.3 edits are localized to:
- A new subsection under TRIGGER DEFINITIONS (line ~351 — after `sequence_reclaim` parenthetical)
- A new clause inside the SPY 5m read block (line ~226-228) to also pull a live quote during the
  first-bar window
- A new line in BEARISH filter 10 (line ~342) and BULLISH filter 11 (line ~364) that lists
  `live_price_first_bar_level_break` / `_reclaim` as a 5th trigger AVAILABLE ONLY during the
  09:35-09:45 ET window
- A new gate G2b (after existing G2 at line 434) that asserts: if the firing trigger is
  `live_price_first_bar_*`, then `09:35:00 ≤ now_et < 09:45:00` AND the firing level matches the
  PML/PMH/Carry filter

No changes to lines 1-225, no changes to the score thresholds, no changes to filter 1's
`time IN [09:35 ET, 15:00 ET)` range.

---

## Change A — extend SPY 5m read to also capture a live quote during the first-bar window

**Current (heartbeat.md line 226-228):**

```
`data_get_ohlcv(count=3, summary=true)` on BATS:SPY 5m. **CRITICAL (R1 v15.1 closed-bar fix
2026-05-14):** TV returns bars labeled by OPEN time and the LAST element [-1] is the LIVE
IN-PROGRESS bar (not yet closed). Apply close-time filter: compute `bar_close_et = bar.time + 5min`
for each bar; filter to `bar_close_et <= now_et`. After filter, `Latest = filtered[-1]` (the
actually-closed-most-recent bar) and `Prior = filtered[-2]`. The unfiltered raw bar[-1]
(in-progress) MUST NOT be used for any scoring decision.
```

**Proposed addition (insert immediately after line 228):**

```
**v15.3 first-bar live-price addendum (NEW — RTH open-drive level-break window only):**

IF `09:35:00 ET ≤ now_et < 09:45:00 ET` AND `current-position.status == null`: ALSO call
`mcp__tradingview__quote_get("BATS:SPY")` once this tick. Store `live_spy_bid = quote.bid`,
`live_spy_last = quote.last`, `live_spy_fetched_at_et = now_et`. These two values are ONLY used by
the v15.3 first-bar level-break trigger (Change B below) — NEVER for filter 9 (volume), filter 5/6
(ribbon/spread), filter 8 (VIX), or any other scoring filter.

OUTSIDE the 09:35-09:45 ET window, the closed-bar filter (R1 v15.1) is still the EXCLUSIVE
source of price for every decision in this tick. The live-quote read is suppressed entirely.

If the quote call fails: skip the v15.3 trigger this tick (do not infer level cross from the
in-progress bar's OHLC — the live-bid path needs a fresh quote). Continue scoring with closed-bar
values only.
```

---

## Change B — define the new triggers + insert into TRIGGER DEFINITIONS block

**Current (heartbeat.md line 344-351):**

```
**TRIGGER DEFINITIONS (used by filter 10):**

- **level_reject** (single-bar): `bar.high > level AND bar.close < level` on last closed bar. ...
- **ribbon_flip** (multi-bar): 5m ribbon stack transitioned to BEAR within last 1-3 closed bars ...
- **multi_day_confluence**: rejected level (from level_reject above) coincides within ±$0.30 of a
  Carry- or Reference-tier level in `key-levels.json` ...
- **sequence_rejection** (NEW 2026-05-07 ...): a level ... has a `bounce_history[]` array with ≥3
  entries where `high_reached` values are strictly decreasing AND the most recent bar closed
  below the level. ...

(For BULLISH, mirror these: sequence_reclaim = `bounce_history` with strictly INcreasing
low_reached values at a broken_to_support level, with last close above level.)
```

**Proposed addition (insert AFTER line 351 sequence_reclaim parenthetical, BEFORE the BULLISH filters):**

```
**v15.3 first-bar live-price triggers (NEW — narrow scope, RTH-open-only):**

These triggers are AVAILABLE ONLY when `09:35:00 ET ≤ now_et < 09:45:00 ET` AND
`current-position.status == null`. Outside this window, they are NOT in the trigger set and
score as 0.

- **live_price_first_bar_level_break** (BEAR trigger): A named level L in `key-levels.json`
  qualifies if ALL of:
    1. `L.tier ∈ {"Carry", "Active"}`
    2. `L.strength.stars ≥ 2`
    3. `L.source` matches case-insensitive `/PMH|PML|premarket high|premarket low|Carry|carry/`
    4. `L.type ∈ {"support", "psychological", "transition"}` (BEAR side breaks support-class levels)

  Fires iff:
    (a) live_spy_bid < L.price - max($0.05, 0.007% × L.price)
       (1c absolute minimum margin — $0.05 — OR 0.7 basis-points relative — whichever is larger.
       On SPY @ $739 that is max($0.05, $0.052) ≈ $0.05. The margin exists so a single tick of
       noise doesn't fire; it is intentionally lighter than the close-back-margin used in
       v15.2-draft Change A because we have only one tick to act on, not a closed bar.)
    (b) AND the PREVIOUS closed 5m bar's close was ≥ L.price - $0.05
       (the bar that JUST closed before this tick was at or above the level — i.e. the level
       has not been broken on a previous bar; the live-price branch must be the FIRST cross)
    (c) AND `live_spy_fetched_at_et` is within 60 seconds of `now_et` (stale-quote guard)

- **live_price_first_bar_level_reclaim** (BULL trigger, mirror): a named level L qualifies if
  same conditions 1-3 above AND `L.type ∈ {"resistance", "psychological", "transition",
  "broken_to_resistance"}` (BULL side reclaims resistance-class levels).

  Fires iff:
    (a) live_spy_last > L.price + max($0.05, 0.007% × L.price)
    (b) AND the PREVIOUS closed 5m bar's close was ≤ L.price + $0.05
    (c) AND `live_spy_fetched_at_et` within 60s of `now_et`

  (BULL uses `live_spy_last` not `live_spy_bid` because a reclaim is a buying signal and last-trade
  price is the most defensible "we are above" indicator. BEAR uses bid because a break-down is a
  selling signal and bid is the most defensible "we can sell into this" indicator.)

**The trigger DOES NOT bypass any other filter.** A live-price level break with VIX < 17.30
(filter 8 BEAR FAIL) does not fire. A live-price level break with ribbon spread < 30¢ (filter 6
FAIL) does not fire. A live-price level break inside a macro hard-veto window does not fire.

**Trigger counts as 1 trigger toward filter-10 (BEAR) / filter-11 (BULL).** It satisfies the
"level-tied" requirement because it IS a level-cross trigger by construction. It can combine
with `ribbon_flip` (most likely co-firing companion at the RTH open on a gap day) to give
2 triggers, which is more than enough for the BEAR `≥ 1` threshold and just meets the BULL `≥ 2`
threshold.
```

---

## Change C — add filter-10 / filter-11 listing of the new triggers (10-min-window-conditional)

**Current (heartbeat.md line 342, end of BEARISH filter 10):**

```
... REQUIRE **≥1** of 4 triggers (RATIFIED v11: was ≥2; sweep showed config B = ≥1 trigger gives
27 trades / 59% WR / -$546 vs 13 trades / 46% WR / -$742 baseline). Triggers: level_reject /
ribbon_flip / multi-day_confluence / **sequence_rejection**. HTF as score-modifier means the
15-min lag doesn't veto a clean 5-min rejection.
```

**Proposed replacement (only the trigger-list clause):**

```
... REQUIRE **≥1** of 4 (or 5 in the first-bar window) triggers. Triggers: level_reject /
ribbon_flip / multi-day_confluence / **sequence_rejection** / **live_price_first_bar_level_break**
(v15.3 NEW — available ONLY when 09:35:00 ET ≤ now_et < 09:45:00 ET, see TRIGGER DEFINITIONS
v15.3 first-bar live-price triggers block above). HTF as score-modifier ...
```

**Current (heartbeat.md line 364, end of BULLISH filter 11):**

```
... REQUIRE **≥2** of 4 triggers ... Triggers: level_reclaim / ribbon_flip / multi-day_confluence
/ **sequence_reclaim**. **Defensive level-tied requirement still applies**: need at least one of
{level_reclaim, confluence, sequence_reclaim} (no pure ribbon_flip-only entries).
```

**Proposed replacement:**

```
... REQUIRE **≥2** of 4 (or 5 in the first-bar window) triggers ... Triggers: level_reclaim /
ribbon_flip / multi-day_confluence / **sequence_reclaim** / **live_price_first_bar_level_reclaim**
(v15.3 NEW — available ONLY when 09:35:00 ET ≤ now_et < 09:45:00 ET, see TRIGGER DEFINITIONS
v15.3 first-bar live-price triggers block above). **Defensive level-tied requirement still
applies**: need at least one of {level_reclaim, confluence, sequence_reclaim,
live_price_first_bar_level_reclaim} (no pure ribbon_flip-only entries).
```

---

## Change D — insert gate G2b into the pre-execution gate sequence

**Current (heartbeat.md line 434, gate G2):**

```
| G2 | Trigger on closed bar | `developing_setup.score == score_max` AND triggers_fired references
the LAST CLOSED bar (not the live bar) | score below max OR trigger from live bar |
```

This gate would BLOCK a live-price trigger because by construction it does NOT reference the last
closed bar. We need to permit live-price triggers AS A NARROW EXCEPTION inside the first-bar
window only.

**Proposed replacement of G2 + insert of G2b:**

```
| G2 | Trigger on closed bar | `developing_setup.score == score_max` AND ANY of:
  (a) triggers_fired all reference the LAST CLOSED bar
  (b) triggers_fired include `live_price_first_bar_*` AND G2b PASSES
  | score below max, OR live-bar trigger that is NOT `live_price_first_bar_*` |
| G2b | First-bar live-price window | IF firing trigger includes `live_price_first_bar_*`:
  `09:35:00 ET ≤ now_et < 09:45:00 ET` AND firing level L satisfies (tier ∈ {Carry,Active}) AND
  (stars ≥ 2) AND (source regex /PMH\|PML\|premarket high\|premarket low\|Carry\|carry/i) AND
  `live_spy_fetched_at_et` within 60s of `now_et` AND (for BEAR) prior_closed_bar.close ≥ L.price
  - $0.05 / (for BULL) prior_closed_bar.close ≤ L.price + $0.05 | any check FAILS |
```

G5/G7/G1/G10/first-entry-lock/G6/G6b are UNCHANGED.

---

## Synthetic reproducer of 2026-05-15 09:40 fast-V

> This pseudocode demonstrates the closed-bar branch MISSING the trade and the live-price branch
> CATCHING it for the same SPY 09:40 5m bar OHLC. The actual smoke test that runs this against
> real 5/15 data is `backtest/autoresearch/v15_3_live_price_trigger_smoke.py`.

```python
# Inputs (from data/spy_5m_2025-01-01_2026-05-15.csv, 2026-05-15 RTH bars):
#   09:30 bar OHLC = (741.79, 741.93, 739.31, 740.17)   # RTH open red candle
#   09:35 bar OHLC = (740.17, 740.21, 739.06, 739.16)   # touches PML 739.04 but no margin break
#   09:40 bar OHLC = (739.16, 740.10, 738.62, 738.66)   # break DOWN through PML on close
#   09:45 bar OHLC = (738.66, 739.67, 737.96, 739.65)   # wick to 737.96, V-bounce, CLOSE ABOVE PML
#   09:50 bar OHLC = (739.65, 740.70, 738.83, 740.43)   # bounce continues
# Named level: PML = 739.04 (tier=Active, stars=2, source="2026-05-15 premarket low — 08:20 ET bar")

PML = 739.04
MARGIN = max(0.05, 0.00007 * PML)   # = $0.052 ≈ $0.05

# ---- branch A: v15.1 CLOSED-BAR rule (current production) ----
# Heartbeat tick at wall-clock 09:46:38 ET (the real fill time)
now_et = "09:46:38"
last_closed = "09:40 bar"     # bar at index time=09:40, close_time=09:45 ≤ now_et
last_closed_OHLC = (739.16, 740.10, 738.62, 738.66)
# level_reject check: bar.high > level AND bar.close < level
level_reject_fires = (last_closed_OHLC[1] > PML) and (last_closed_OHLC[3] < PML)
# 740.10 > 739.04 AND 738.66 < 739.04 → TRUE → ENTER_BEAR at this tick
# But "now" SPY is back in the V-bounce: spot at 09:46 ≈ 739.0 (post-09:45 wick → recovering)
# Bracket order goes in at 739.0-area spot, fills around premium $3.14, then the bar continues
# bouncing to 739.65 by 09:50 → stop hits at $2.51 → -$770 loss.
assert level_reject_fires is True
print("BRANCH A (closed-bar v15.1): ENTRY at 09:46 ET on confirmed close break — FILLS INTO BOUNCE")

# ---- branch B: v15.3 LIVE-PRICE first-bar trigger (proposed) ----
# Heartbeat tick at wall-clock 09:41 ET (during the 09:40 bar in-flight)
now_et = "09:41:00"
# We are INSIDE the first-bar window (09:35 ≤ now_et < 09:45)
# Live quote read returns: SPY bid ~$738.95 (price is travelling from 739.16 open → 738.62 low)
live_spy_bid = 738.95
# Previous closed bar = 09:35 bar (OHLC closed at 09:40 ET)
prior_closed_bar_close = 739.16
# Trigger check:
#   (a) live_spy_bid < PML - max($0.05, 0.007% × PML)
#       738.95 < 739.04 - 0.052 = 738.988 → 738.95 < 738.988 → TRUE
#   (b) prior_closed_bar.close ≥ PML - $0.05
#       739.16 ≥ 738.99 → TRUE (level not previously broken)
#   (c) live_spy_fetched_at_et within 60s of now_et: TRUE
trigger_a = live_spy_bid < (PML - MARGIN)
trigger_b = prior_closed_bar_close >= (PML - 0.05)
trigger_c_stale = False
fires = trigger_a and trigger_b and (not trigger_c_stale)
assert fires is True
print("BRANCH B (live-price v15.3): ENTRY at 09:41 ET on live cross — CATCHES THE LEG DOWN")

# Net effect:
#  - Branch A entry premium ~ $3.14 (entry around 739.0 spot post-bounce)
#  - Branch B entry premium ~ $3.55 (entry around 738.95 spot pre-bounce; option delta -0.4 →
#    additional $0.40 of intrinsic on the 740P = +$0.16/contract minimum vs branch A,
#    plus +$0.20 extrinsic from buying earlier in the volatility expansion = roughly $3.34-$3.55)
#  - The 09:45 bar low of 737.96 would have hit ~$4.10-$4.30 premium on the 740P =
#    +$0.55-$0.75/contract favor before V-bounce. Profit-lock chandelier arms at +5% =
#    $3.34 × 1.05 = $3.51, then trails 20% off HWM ~$4.20 → stop trails to $4.20 × 0.80 = $3.36,
#    floor moves to $3.34 × 1.10 = $3.67. Exit at first downward 20% off HWM ~$3.67 = scratch-to-tiny-win.
#  - Estimated branch B P&L on this exact trade: ~ +$50 to +$300 (vs branch A's −$770).
```

The asymmetric outcome is the whole point: on a fast-V-reversal bar at a named ★★+ level in the
RTH open window, closed-bar confirmation enters into the bounce while live-price catches the
break before it reverses. On a true clean break (no V-reversal), both branches enter at roughly
the same time — live-price 30-90 seconds earlier, but the trade trajectory is the same.

---

## Failure modes (false-positive scenarios)

This is a NEW trigger path. It is bounded in time (10 min) and bounded in level set
(PML/PMH/Carry only, ★★+ only). But it CAN misfire. Honest enumeration:

1. **Wick-only level cross without follow-through.** SPY ticks 1 cent below PML, the live-bid
   read catches the cross, the engine enters, then SPY immediately reclaims. The trade enters
   into a noise wick.
   - **Mitigation:** the $0.05 margin (or 0.007% — whichever is larger) absorbs single-tick
     noise of 1-4 cents. PML 739.04 requires the live bid to be ≤ $738.99 to fire — a real cross,
     not a wick.
   - **Residual risk:** a 6-cent wick that closes back is still a fire. Profit-lock chandelier
     arms only at +5% favor; this trade will likely hit premium stop -20% if the wick reverses
     immediately. Worst-case loss is bounded.

2. **Chop-through scenarios where price oscillates across the level multiple times in 5 minutes.**
   The "previous closed bar close ≥ L.price - $0.05" gate only checks ONE bar back. If the level
   has been crossed and reclaimed already in the premarket or first 09:35 bar, this gate falsely
   allows the next live-price cross to fire.
   - **Mitigation:** the gate requires the LAST CLOSED bar (which is 09:35 bar inside the
     09:35-09:45 window) to have closed at or above the level. If 09:35 closed below, the level
     is already broken on a closed bar and the closed-bar trigger (`level_reject`) takes over —
     no need for the live-price path.
   - **Residual risk:** if 09:35 closed exactly at L.price ± $0.05 and 09:40 in-flight is
     oscillating, the live-price branch could fire on a chop tick. Rare in practice for ★★+
     levels at the RTH open.

3. **Stale quote.** If `quote_get` returns a cached or stale price, the live cross detection is
   meaningless.
   - **Mitigation:** the 60-second freshness check on `live_spy_fetched_at_et`. Live ticks
     normally arrive every 1-3 seconds during RTH; 60s is generous and any stale read aborts the
     trigger.
   - **Residual risk:** TradingView MCP returns a `last` value that lags real OPRA by 1-3 seconds.
     That is acceptable for level-cross detection at the 5-second granularity we operate on.

4. **Macro hard-veto bypass.** A live-price trigger could fire DURING a macro hard-veto window
   (e.g., FOMC at 09:45 + bias inheritance). The new trigger path must STILL respect every other
   filter and gate.
   - **Mitigation:** Change B's text explicitly states the trigger does not bypass filters 1-9.
     Change D's gate G2b is in addition to G5/G7/G1/G10/first-entry/G6/G6b — every other gate
     runs as normal. Live-price trigger inside macro hard-veto = no fire.
   - **Residual risk:** none — the gate sequence is hard.

5. **Volume gate (filter 9) reads 0.7 × 20-bar avg of the LAST CLOSED bar.** During the 09:40
   in-flight tick, the last closed bar is 09:35 which has volume 938K — comparable to morning
   averages, likely passes. But on a real fast-V where the 09:40 in-flight bar IS the impulse,
   the 09:35 bar's volume is the pre-impulse volume. The filter could pass even on a low-quality
   setup.
   - **Mitigation:** the live-price trigger requires the level-cross to be REAL (margin), the
     ribbon to be BEAR-stacked with ≥30¢ spread, the VIX to be rising and > 17.30, and macro to
     be clear. Filter 9 is one of nine — not load-bearing alone.
   - **Residual risk:** on a low-vol RTH open with a tiny gap, the live-price trigger could fire
     on a chop-style cross. Backtest must measure the false-positive rate.

6. **Wrong-direction trade on a sweep-style bar.** A bar that wicks BELOW a level and closes
   ABOVE is a defended level (a "bullish sweep" per the v15.2 draft). A live-price trigger that
   fires on the down-wick mid-bar would catch a doomed bearish trade. This is the same class of
   foot-gun as the 5/14 09:58 ENTER_BULL but mirror-image.
   - **Mitigation:** v15.2's `bullish_sweep` blocker can be ADDITIVELY combined with v15.3 — when
     the 09:40 bar closes (09:45 ET), the engine re-evaluates the position. If `bullish_sweep`
     fires on the closed 09:40 bar (close > level + margin, wick < level - margin), the position
     should EXIT immediately via stop logic. This is partially covered by the existing chart-stop
     condition (close > rejection_level + $0.50 buffer) — but the v15.2 sweep blocker is a clean
     mirror.
   - **Residual risk:** the live-price trigger DOES fire early, before the bar closes. If the
     bar then reverses and becomes a sweep, the trade is in a hole. Premium stop -20% (v15) and
     profit-lock chandelier limit the damage.

7. **Multiple ★★+ levels within $0.30 of each other.** PML, Carry, and a Reference psychological
   level can all stack near the same price. The trigger could fire on the first-touched level
   while the operational level is the one $0.20 below it.
   - **Mitigation:** filter the levels to `tier ∈ {Carry, Active}` AND `stars ≥ 2` AND source
     regex matches — psychological reference levels (tier=Reference) are excluded.
   - **Residual risk:** if multiple Active ★★+ levels cluster, the trigger fires on the FIRST
     one crossed. Acceptable — this is a feature, not a bug, of the open-drive setup.

---

## Hard gates summary

The branch is NOT a relaxation of v15.1. Every gate v15.1 ratifies still applies:

| Gate | v15.1 behavior | v15.3 behavior for live-price branch |
|---|---|---|
| Filter 1 (time gate) | `09:35 ET ≤ now_et < 15:00 ET` | UNCHANGED. Live-price branch is a SUBSET inside this. |
| Filter 5 (ribbon stack) | BEAR / BULL must be stacked | UNCHANGED. Live-price trigger does NOT fire if ribbon is MIXED. |
| Filter 6 (spread ≥ 30¢) | Required | UNCHANGED. |
| Filter 8 (VIX gates) | BEAR > 17.30 + rising; BULL < 17.20 or falling; BULL hard cap 22 | UNCHANGED. |
| Filter 9 (vol confirmation) | 0.7× 20-bar avg | UNCHANGED — uses LAST CLOSED bar's volume. |
| Filter 10 / 11 (trigger count) | BEAR ≥ 1, BULL ≥ 2 | UNCHANGED — live-price counts as 1 trigger. |
| Macro hard-veto (≤120 min) | Hard block counter-trend | UNCHANGED. |
| First-entry-after-stop lock | Block re-entry on same setup after stop | UNCHANGED. |
| G5 (kill switch) | Block | UNCHANGED. |
| G7 (PDT) | Block at 3 day-trades / 5d for sub-$25K | UNCHANGED. |
| G1 (setup in playbook) | Block if name not in `strategy/playbook.md` | UNCHANGED — same setup names. |
| G2 (trigger on closed bar) | Required | RELAXED to allow `live_price_first_bar_*` IF G2b passes. |
| **G2b (NEW — first-bar live-price window)** | n/a | Required (window + level + freshness). |
| G6 / G6b (sizing caps) | Per-trade 50% / per-tier max premium | UNCHANGED. |
| Liquidity gate | delta in [0.30, 0.55], OI ≥ 500 | UNCHANGED. |
| Iron law (filled before write) | Required | UNCHANGED. |

The branch ADDS ONE GATE (G2b) and RELAXES ONE GATE (G2) and only for triggers that pass G2b.
That is the entire surface area of the change. Nothing else is touched.

---

## Validation evidence

| Claim | Evidence |
|---|---|
| Closed-bar rule is the source of the 09:46 ET fill lag on 5/15 | `journal/2026-05-15.md` lines 174-178, 247-249 |
| 09:40 bar OHLC verified | `backtest/data/spy_5m_2025-01-01_2026-05-15.csv` lines 30994 |
| 09:45 bar V-reversal verified (wick 737.96, close 739.65 ABOVE PML 739.04) | same file line 30995 |
| Live-price trigger fires at ~09:41 ET on 738.95 ish bid | `backtest/autoresearch/v15_3_live_price_trigger_smoke.py` |
| Closed-bar branch does NOT fire on 09:45 bar close (above level) | same smoke test, Case 2 |
| Setup conditions valid (BEAR ribbon, VIX rising, gap-down) | `journal/2026-05-15.md` lines 34-50 |
| PML 739.04 qualifies under ★★+ Active filter | `automation/state/key-levels.json` lines 159-191 |

---

## Risks to consider (J review)

1. **The branch has NOT been backtested on historical data.** The 5/15 trade is the only example
   in the journal. Need to scan 16 months of RTH-open bars for: (a) first-bar level crosses,
   (b) follow-through vs V-reversal rate, (c) the trade outcome under both branches. Tools
   exist in `backtest/autoresearch/` to do this — must be wired before ratification.

2. **The $0.05 / 0.007% margin is empirically tuned to one event.** Need to sweep margins in
   {$0.03, $0.05, $0.08, $0.10} and report fire rate + true-positive rate. The 5/15 setup would
   fire at any of these because the live bid was ~$738.95 vs PML 739.04 = $0.09 below.

3. **The 09:35-09:45 ET window is empirically tuned to one event.** Need to test 09:35-09:40
   (more conservative — only first bar) vs 09:35-09:50 (looser — extends into the second
   closed bar's window). The fast-V class is heavily concentrated in the first 10 minutes; the
   data should confirm.

4. **Profit-lock chandelier interaction is not yet specced.** When the live-price trigger fires
   at 09:41 ET and the position is open, the chandelier still arms at +5% favor. But what if
   the 09:40 bar closes BACK ABOVE the level (a sweep — true on 5/14 09:55, NOT true on 5/15
   09:40)? The position is in a hole. Should the closed-bar reversal force-exit or just let the
   chandelier + premium stop do their job? Recommend: let the existing exits do their job
   (chandelier doesn't arm at -20%, premium stop fires at -20% on entry premium — bounded loss).

5. **Coupling with v15.2 sweep blocker.** v15.3 should be specced as ADDITIVE to v15.2 (not
   instead-of). v15.2's `bullish_sweep` blocker prevents the 5/14 09:58 mirror foot-gun;
   v15.3's live-price trigger prevents the 5/15 09:40 fast-V foot-gun. They are orthogonal.

6. **Two-account behavior.** Gamma-Safe is conservative — does the live-price branch apply to it
   or is it Gamma-Bold-only? Recommend: BOTH. Live-price is a TIMING fix, not a size/aggression
   knob. The v15.1 closed-bar lag affects Safe and Bold equally. Strike/sizing per existing
   tier table remains untouched.

7. **`tier == "Carry"` vs `role == "broken_to_support"` for PML.** Today's PML 739.04 has
   `tier == "Active"` (not `"Carry"`) and `role == null` (not `"broken_to_support"`). The
   proposed filter `tier ∈ {Carry, Active}` catches it. But the v15.2 draft uses
   `role == "broken_to_resistance"` for some downstream logic. Need to confirm the v15.3 filter
   is internally consistent. Recommend: tier+stars+source-regex as proposed; do NOT use role.

---

## What happens before this ships to production

1. DRAFT written (this file)
2. Smoke test written (`backtest/autoresearch/v15_3_live_price_trigger_smoke.py`) that asserts
   correct firing on 5/15 09:40 and correct non-firing on a counter-example
3. J reviews on weekend
4. J runs full historical backtest:
   `python backtest/run.py --start 2025-01-01 --end 2026-05-15 --label v15.3_live_price_trigger --real-fills`
   with the v15.3 branch wired into `backtest/lib/filters.py` per OP-4 (no code drift)
5. Verify: no regression on the 7 J-edge days
   - 4/29, 5/01, 5/04 winners must still take the same entries
   - 5/05, 5/06, 5/07×2 losers must not get WORSE (additional false positives in the first-bar
     window would be a regression)
6. Verify: fast-V days from 16-month backfill where the closed-bar branch entered into a bounce —
   the live-price branch should improve the outcome. Need ≥3 examples to ratify.
7. Verify: no fast-V cases where the live-price branch fires on a wick that immediately reverses
   to a sweep (the v15.2 sweep-blocker territory).
8. If GREEN: copy Change A-D into production `heartbeat.md`, bump `rule_version` in `params.json`
   to `"v15.3"`, update `premarket.md` `RULE_VERSION_EXPECTED`, update
   `automation/prompts/heartbeat-v15.2-draft.md` to note coexistence per OP-4.
9. Append L40 to `docs/LESSONS-LEARNED.md` with the ratification.

## Pre-merge gate

`python crypto/validators/runner.py` must show **OVERALL: PASS** at the moment of merge (per
OP-26 — every heartbeat.md edit triggers the harness check). v15.3 does not add a new primitive
to `crypto/lib/`; the live-price trigger is a heartbeat-only doctrine change. But the closed-bar
rule it coexists with is canonical in `crypto/lib/bar_reader.py` and must stay green.

---

_Last edited: 2026-05-17 by autonomous session. DO NOT deploy without J ratification._
