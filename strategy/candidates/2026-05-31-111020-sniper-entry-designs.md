# Strategy candidate: SNIPER ENTRY MECHANICS — beating the retest wick

> DRAFT — Chef proposal 2026-05-31T11:10:20Z. J ratifies.

---

## Hypothesis

The engine enters BULLISH_RECLAIM (and BEARISH_REJECTION) on **next-bar fill** after the trigger bar
closes. In a low-VIX slow-grind market, the reclaimed level gets retested on the following bar —
a routine 5m wick that pushes the premium down 8-15%, firing the tight premium stop BEFORE
the trend resumes. The entry is structurally one bar too late: by the time we fill on the open
of bar N+1, the retest wick is happening right under our feet.

The fix: enter EARLIER (at trigger bar close or during the trigger bar) so that the retest wick
is BEHIND US at fill, not ahead. Alternatively: a proximity-aware stop that treats a bar-N+1
retest wick at the reclaim level as noise rather than invalidation.

**Motivating failure:** 2026-05-28 SPY +$4.39 clean trend day. Engine entered 751C calls at
10:15 on next-bar fill. Shallow retest dip (<$0.50 on SPY) fired the -8% premium stop.
SPY continued to 755 without the position. SAFE: -$10.5/c. BOLD: -$40.0/c.

**Source:** `analysis/missed-week-2026-05-26_29.md` + `journal/2026-05-28.md` + L76.

---

## Backtest evidence

This is a DESIGN proposal — no engine backtest has been run yet (the 6-10 designs below are
written to be backtest-implementable). Edge_capture and sharpe numbers require a full grinder
run per OP-16 methodology. The candidate is filed to (a) encode the designs before they are
lost, (b) provide exact trigger specs for the Kitchen to cook, and (c) rank the designs by
impact × implementability so the highest-value one goes first.

- Train window: N/A — pre-backtest
- Test window: N/A
- edge_capture: TBD — floor gate (≥771) cannot be verified until backtest runs
- aggregate_sharpe: TBD
- final_score: TBD
- top5_pct: TBD
- positive_quarters: TBD
- max_drawdown: TBD
- real_fills_validated: no

---

## The problem decomposed

### Why next-bar entry fails in low-VIX grind

On a slow bull grind day (VIX 15-16, SPY +0.4-0.8%/day):

1. Trigger bar closes at 10:12 ET: SPY reclaims the level at $750.00, ribbon flips BULL.
2. Engine evaluates filters at bar close (~10:12:30 ET), places limit at mid on bar N+1 open.
3. Bar N+1 (10:15 ET): opens at $750.10, routine retest dip to $749.50 (−$0.60 on SPY).
4. At entry premium of $1.31 (ATM call), a $0.60 SPY dip = ~−$0.25 on the call = −19% premium.
5. Premium stop at −8% fires at $1.21 during the retest — well before the $0.60 dip is done.
6. Bar N+1 CLOSES at $750.80. SPY grinds to $755 over next 2 hours. Engine never re-enters.

The issue is not the stop math — it is the entry timing. A one-bar delay puts the entry
directly into the retest, not above it.

### Why earlier entry is structurally better

If the engine fills at the CLOSE of the trigger bar (or during the trigger bar via live-price):
- Entry at bar N close: $750.00. Call premium: $1.20.
- Bar N+1 retests $749.50 (−$0.50 SPY). Call dips to $1.10 (−8.3% vs $1.20 entry).
- Still fires stop at exactly the same premium threshold — BUT the SPY dip is smaller from
  a lower entry point, and the position cost basis is better positioned for the grind.

The real gain: entering at the RECLAIM BAR CLOSE means the stop reference is the reclaimed
level ($750.00), not the post-retest recovery open ($750.10). The $0.10 slippage advantage
is small; the structural advantage is that the RETEST WICK IS THE TRIGGER BAR ITSELF — we
filled at its close, so we are long from a level that already showed buyers absorbing sellers.

---

## The 8 designs (ranked by impact × implementability)

### Design 1 — LIMIT-AT-TRIGGER-CLOSE (highest impact, very implementable)

**Slug:** `limit_at_trigger_close`
**Rank:** #1 — fixes the core problem directly, no new conditions needed

**Trigger description:**
When BULLISH_RECLAIM fires (all filters pass on bar N close), place a GTC **limit buy at the
midpoint of bar N's ask** during the last 15 seconds of bar N (before the bar closes). In
practice for the heartbeat (3-min ticks): the bar close IS the evaluation moment. The
implementation: when filters pass, use bar N's close price as the fill rather than bar N+1's
open. This is a fill-model change, not a signal change.

**Backtest implementation:**
Change `entry_fill_model` in `simulator_real.py` from `next_bar_open_plus_slippage` to
`trigger_bar_close_plus_slippage` when `early_entry_mode = True`. Slippage $0.02 applied at
trigger bar close price.

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary — the missed-week failure)
- BEARISH_REJECTION_RIDE_THE_RIBBON (symmetric — earlier fill before retest wick up)
- ORB_RETEST_LONG (secondary — ORH retest entry would benefit)

**Failure mode it fixes:**
Entry on bar N+1 open into the retest wick — the retest wick fires the premium stop before
the trend resumes. With trigger-bar-close fill, the stop reference is anchored to the reclaim
point, not the retest-wick low.

**Failure mode it introduces:**
- More fills on "false reclaims" — bar N may look like a reclaim at close but bar N+1
  immediately closes back below the level. Mitigation: the existing filter set (ribbon flip,
  VIX gate, volume 1.3×) already screens for bar N quality. False reclaim rate should not
  increase vs current.
- Requires live-tick implementation in production heartbeat to submit limit at bar N close
  rather than waiting for bar N+1 open. In backtest, this is a fill-model flag.

**Stop interaction:**
Stop reference level is UNCHANGED — it remains the reclaim level (level − $0.50 chart stop).
The stop dollar amount may shrink slightly because entry premium is lower (bar N close is
typically lower than bar N+1 open after a reclaim on a grind day due to time-value decay
within the 3-min bar). Net effect: slightly better R:R.

**Falsification criteria:**
- Backtest shows WR DECREASES vs baseline by ≥5pp: early fill catches more false reclaims
  than it avoids retest-wick stops. REJECT.
- edge_capture on J anchor days DROPS: the -8% premium stop becomes more exposed at an earlier
  fill price, causing 4/29 or 5/04 to hit stop before the move. REJECT.
- Premium-stop fires MORE frequently per trade than baseline (counter to intent). REJECT.

**Implementability:** HIGH. One parameter change in simulator_real.py + heartbeat.md limit-order
timing adjustment.

---

### Design 2 — RETEST-WICK TOLERANCE ZONE (high impact, implementable)

**Slug:** `retest_wick_tolerance`
**Rank:** #2 — addresses the stop misfire without changing entry timing

**Trigger description:**
After BULLISH_RECLAIM entry on bar N+1, if bar N+1 has a retest wick that brings SPY within
$0.15 of the reclaim level AND the bar N+1 CLOSES above the level, treat this as a "healthy
retest" and suppress the premium stop for that bar. The premium stop reactivates from bar N+2
onward at the original reference.

**Backtest implementation:**
Add a `retest_tolerance_bars = 1` parameter. In the first `retest_tolerance_bars` bars after
entry: if `current_bar.low >= (reclaim_level - 0.20)` AND `current_bar.close > reclaim_level`:
skip premium stop check for this bar. Chart stop (SPY close below reclaim_level − $0.50) still
active. From bar N+2: normal premium stop resumes.

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary)
- BEARISH_REJECTION_RIDE_THE_RIBBON (symmetric: after bear entry, bar N+1 wick up to level
  but closes below = healthy retest, suppress premium stop that tick)

**Failure mode it fixes:**
The premium stop firing on a noise retest wick within the first 3-minute bar after entry —
before SPY has had time to move away from the entry level.

**Failure mode it introduces:**
Holding through genuine reversals disguised as "retests." A true reversal: bar N+1 wicks to
the level AND CLOSES back below it — this triggers the chart stop regardless (chart stop always
active). The only added risk: a bar that approaches the level, closes above, then bar N+2
immediately fails below. This is small-sample risk, not structural.

**Stop interaction:**
Chart stop fully active at all times. Premium stop suppressed for 1 bar post-entry ONLY when
bar closes above the reclaim level. This is the minimal safe version. A more aggressive version
suppresses for 2 bars but that is NOT recommended here — the second bar has no structural reason
to expect a retest.

**Falsification criteria:**
- Net P&L on retest-tolerance entries is WORSE than baseline (more losses held past the wick).
- Chart stop fires MORE often with tolerance active (means the wick isn't a healthy retest —
  it's actual failure). REJECT design.
- edge_capture on 5/05, 5/06, 5/07 (J loser days) INCREASES (more loss on those days because
  stop is suppressed on what would have been a correct stop). REJECT.

**Implementability:** HIGH. Requires tracking `bars_since_entry` counter in simulator_real.py
and a `reclaim_level` reference passed through the exit loop.

---

### Design 3 — PRE-RIBBON-FLIP LIMIT (medium-high impact, medium implementability)

**Slug:** `pre_ribbon_flip_limit`
**Rank:** #3 — enters one bar BEFORE the ribbon flip confirmation

**Trigger description:**
When filters 1-9 PASS (all context/structure filters) AND the ribbon is in MIXED state (Fast
and Slow not yet fully reordered) AND the CURRENT BAR is a strong buyer-pressure bar (green,
vol ≥ 2.0× baseline, close ≥ 80% of bar range = closes at the top), place a limit at the
bar's close. Do NOT wait for the ribbon to fully flip (filter 5). The ribbon flip will be
confirmed on the NEXT bar — by which time the retest wick has already happened.

**Backtest implementation:**
Modify `evaluate_bullish_setup()`: add a branch where `ribbon_now == MIXED` is accepted
(currently blocked by filter 5) IF AND ONLY IF:
- `bar.close > bar.open` (green)
- `bar.volume >= 2.0 * vol_baseline_20` (strong buyer pressure)
- `(bar.close - bar.low) / (bar.high - bar.low) >= 0.80` (closes at the top of the bar)
- All other filters still pass

This fires ONE bar earlier than the current BULL flip confirmation. The fill is still at bar N
close (or N+1 open as fallback).

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary)

**Failure mode it fixes:**
Missing the flip bar because the fill happens one bar after the flip is confirmed, into the
retest. By entering on the MIXED→BULL transition bar (when it's a high-quality buyer-pressure
bar), the position is established before the ribbon fully flips, but the bar quality (green,
high volume, closes at top) confirms buyers are in control.

**Failure mode it introduces:**
False BULL early entries on MIXED ribbon days that fail to complete the flip. The protection:
requiring vol ≥ 2.0× baseline + closes at 80% of range ensures a committed buyer bar, not
noise. But this will still produce more false entries than the current confirmed-flip approach.
Back-of-envelope: MIXED ribbon days where a strong green bar does NOT lead to full flip: ~30%
of the time in chop (L65 lesson: watcher confidence scoring is already a partial proxy).

**Stop interaction:**
Stop reference is the level tested by bar N's wick (the MIXED bar). Chart stop: level − $0.50.
Premium stop: standard −8%. Since entry is earlier (lower premium cost on a MIXED-ribbon day
vs confirmed-BULL day), the dollar stop is smaller — this IS the intended benefit.

**Falsification criteria:**
- WR on MIXED-ribbon entries (new branch) < 45%: the early entry catches too many failed flips.
- edge_capture on 4/29 or 5/04 decreases: the pre-flip entry fires a different bar than J's
  confirmed-flip entry, resulting in earlier stop-out before J's winning bar closes.
- The gain from eliminated retest-wick stops is less than the loss from false MIXED entries.

**Implementability:** MEDIUM. Requires adding a MIXED-ribbon branch to `evaluate_bullish_setup()`,
plus a high-quality bar gate (4 conditions). The risk of breaking existing validators is real —
any validator that asserts "ribbon must be BULL for bullish setup" will break. Must add a new
validator sub-test for the MIXED-entry branch.

---

### Design 4 — CONSOLIDATION-ANCHOR ENTRY (high impact, medium implementability)

**Slug:** `consolidation_anchor_entry`
**Rank:** #4 — enters at the BASE of the consolidation (before the breakout bar) rather than
at the breakout bar itself

**Trigger description:**
When N≥3 consecutive bars form a tight consolidation (each bar range ≤ 50% of 20-bar avg range,
all closes within a $0.40 band) FOLLOWED by a breakout bar (close ≥ $0.30 above consolidation
high on vol ≥ 1.5×), place the limit at the CLOSE OF THE LAST CONSOLIDATION BAR — i.e.,
enter BEFORE the breakout bar closes. This is an anticipatory entry at the support floor
of the consolidation.

**Backtest implementation:**
Detect N-bar-consolidation:
```python
def detect_consolidation(bars: pd.DataFrame, idx: int, n_bars: int = 3,
                         max_range_mult: float = 0.50, max_band_dollars: float = 0.40) -> bool:
    window = bars.iloc[idx-n_bars:idx]
    bar_ranges = (window['high'] - window['low']).values
    avg_range = vol_baseline(bars, idx)  # 20-bar avg range
    if (bar_ranges > max_range_mult * avg_range).any():
        return False  # any bar too wide = not a real consolidation
    band = window['close'].max() - window['close'].min()
    return band <= max_band_dollars
```
Entry: close of bar `idx-1` (last consolidation bar), before bar `idx` (breakout bar) closes.
This requires a live-tick approach in production (enter during the consolidation period using
the last confirmed bar). In backtest: fill at `bars.iloc[idx-1]['close'] + slippage`.

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON — the consolidation IS the post-reclaim retest compressed
  into N bars. Entering at the consolidation base = entering below the eventual breakout wick.
- BEARISH_REJECTION (symmetric: bearish consolidation after a resistance test)

**Failure mode it fixes:**
The retest wick problem is eliminated: the entry IS at the consolidation base, which is the
support level the engine is trying to defend. No next-bar entry into a wick exists because
the fill happened during the consolidation, not after the breakout.

**Failure mode it introduces:**
- Requires 3-bar consolidation to form, which means missing trades where the reclaim goes
  immediately vertical (no consolidation). Miss rate on "V-launch" days: est. 30-40%.
- Entry at consolidation base means holding through potentially N additional bars before
  breakout confirms — time-value decay on 0DTE calls.
- False consolidation breaks: sometimes a "consolidation" is actually a distribution top —
  the breakout goes DOWN, not up. The buyer-pressure bar at breakout (vol ≥ 1.5×, green)
  is the guard against this, but it will fire after entry.

**Stop interaction:**
Stop is the CONSOLIDATION LOW (bottom of the N-bar band) minus $0.20. This is TIGHTER than
the chart stop at the reclaim level (since consolidation is above the reclaim level). Benefit:
better R:R. Risk: the consolidation low is closer to current price, so chart noise is more
likely to fire it.

**Falsification criteria:**
- Miss rate on J-winner days (4/29, 5/01, 5/04) due to no consolidation: if any anchor day
  goes immediately vertical and this design misses it, REJECT unless another design covers.
- WR on consolidation-anchor entries < 50%: the distribution-top false-break risk is too high.
- Time decay: per-contract P&L worse than next-bar fill because the extra bars held eat theta.

**Implementability:** MEDIUM. Bar-pattern detection (consolidation detector) is a new primitive.
`backtest/lib/filters.py` already has the geometry utilities needed. Requires N-bar lookback
in the simulator. Production wiring: heartbeat needs to track consolidation state across ticks.

---

### Design 5 — VOLUME-ABSORPTION CONFIRMATION ENTRY (high impact, medium implementability)

**Slug:** `volume_absorption_confirm`
**Rank:** #5 — enters ONLY when the retest bar shows high buy-side absorption

**Trigger description:**
After the standard BULLISH_RECLAIM fires (bar N), wait for bar N+1 (the retest bar). If bar
N+1:
- Wicks DOWN to within $0.30 of the reclaim level (the expected retest)
- AND closes ABOVE the reclaim level + $0.10 (closes back above, retest held)
- AND has volume ≥ 1.5× 20-bar avg (buyers absorbed the retest sellers)
Then enter at the CLOSE of bar N+1.

This converts the retest wick from a threat into a confirmation. The entry happens AFTER the
wick prints, not before.

**Backtest implementation:**
After BULLISH_RECLAIM fires on bar N, set a `pending_absorption_entry` flag. On bar N+1:
```python
if (bar_n1.low <= reclaim_level + 0.30 and
    bar_n1.close >= reclaim_level + 0.10 and
    bar_n1.volume >= 1.5 * vol_baseline):
    entry = bar_n1.close + slippage  # absorption confirmed
else:
    cancel_pending_entry()  # retest failed — don't chase
```

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary)
- BEARISH_REJECTION_RIDE_THE_RIBBON (symmetric: after bear trigger, wait for upward retest
  of the rejection level that closes back below it on volume)
- ORB_RETEST_LONG (this IS already the ORB state-machine logic — the ORB watcher waits for
  the retest-held close, which is why ORB has WR=81.8% real-fills)

**Failure mode it fixes:**
Stops firing on the retest wick because the entry WAITS for the wick to complete and the bar
to close above the level. By definition, the entry can only happen after the wick is behind us.

**Failure mode it introduces:**
- Sometimes bar N+1 does NOT produce a clean retest-and-close-above: instead it gaps up and
  runs. In this case the absorption entry MISSES the move. Miss rate: est. 25-35% on strong-
  momentum reclaim days.
- On strong trend days (like 5/04 +$4.39), the entry will often be one bar later than current
  (bar N+2 instead of N+1). This misses some initial move but enters with confirmation.
- False absorption signal: bar N+1 looks like absorption (closes above level) but bar N+2
  immediately fails below. Rare but possible.

**Stop interaction:**
Stop is the reclaim level (same chart stop). Entry is at bar N+1 close (slightly higher than
N+1 open), so the stop dollar amount is SLIGHTLY LARGER than Design 1. Premium stop −8% from
bar N+1 close premium. Net: very similar to current stop mechanics but entry is better-quality.

**Falsification criteria:**
- Miss rate >40%: too many entries skipped because bar N+1 goes directly vertical (no retest).
- WR decreases vs baseline: the absorption confirmation adds no quality signal.
- edge_capture on anchor days (4/29, 5/04) decreases because bar N+1 went vertical and absorption
  entry missed.

**Implementability:** HIGH. State machine is simple: pending_entry flag + bar N+1 check. The
ORB watcher already implements this exact pattern — the code can be directly adapted.

---

### Design 6 — CANDLESTICK QUALITY GATE (medium impact, high implementability)

**Slug:** `candlestick_quality_gate`
**Rank:** #6 — adds a bar-quality filter to screen out low-confidence reclaim bars

**Trigger description:**
The existing BULLISH_RECLAIM trigger fires when buyer_pressure_bar() is True (green + vol ≥ 1.3×).
Add a SECOND quality gate: the trigger bar must ALSO be one of:
- A hammer candle (close at top, lower wick ≥ 50% of range) — classic support bounce
- A bullish marubozu (body ≥ 75%, wicks ≤ 10%) — pure momentum bar
- OR have body_ratio ≥ 0.65 (closes decisively in the upper 65% of its range)

Bars that are green and high-volume but close in the middle of their range (body_ratio < 0.50)
are "indecision" bars — they look bullish but close weak, suggesting the reclaim is contested.
These produce the retest wicks that fire stops.

**Backtest implementation:**
Add to `evaluate_bullish_setup()`:
```python
from .filters import is_hammer, is_bullish_marubozu, is_decisive_bar
if not (is_hammer(bar) or is_bullish_marubozu(bar) or is_decisive_bar(bar, min_body_ratio=0.65)):
    score -= 1  # soft gate — reduces score by 1, doesn't hard-block
    # OR: hard block (filter 9.5): if none of these, return False
```

The soft version reduces score. The hard version eliminates borderline entries. Start with hard
block, backtest both.

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary)
- BEARISH_REJECTION_RIDE_THE_RIBBON (symmetric — bearish shooting star / marubozu)

**Failure mode it fixes:**
Entering on "contested reclaim" bars (green, some volume, but close in the middle) that are
likely to produce a retest. The body-quality gate is already available in `filters.py`
(`is_decisive_bar`, `is_hammer`, `is_bullish_marubozu`) — wiring is trivial.

**Failure mode it introduces:**
Missing valid reclaims that happen to print with a middle-close (e.g., J's 5/01 leg1 was
described as "anticipation entry" with a partial bar). Check: what were the body ratios on
4/29, 5/01, 5/04 trigger bars? If anchor bars fail this gate, REJECT or demote.

**Stop interaction:**
Unchanged. Entry same as current (bar N+1 open). The gate reduces FREQUENCY (fewer fires)
but doesn't change stop mechanics per trade.

**Falsification criteria:**
- Any J-winner anchor day trigger bar fails the quality gate: REJECT (edge_capture drops).
- Reduction in fires > 50%: filter is too tight, eliminates too much edge.
- WR improvement after gate < 3pp: quality gate adds friction but no real edge.

**Implementability:** VERY HIGH. All three detection functions already exist in `backtest/lib/filters.py`.
Wiring requires 3 lines in `evaluate_bullish_setup()`. Zero new code, just connecting existing
primitives. This is the cheapest experiment to run.

---

### Design 7 — LEVEL-TIERED STOP DISTANCE (medium impact, high implementability)

**Slug:** `level_tiered_stop`
**Rank:** #7 — widens the chart stop proportionally to level quality (★★★ levels get more room)

**Trigger description:**
The current chart stop is a FLAT $0.50 buffer below the reclaim level (level − $0.50). In
low-VIX conditions, a $0.50 dip on a ★★★ high-quality level is normal noise (the level has
MANY prior touches, buyers come in more slowly). Widen the chart stop proportionally:
- ★★★ level (≥5 touches): stop = level − $0.75
- ★★ level (3-4 touches): stop = level − $0.50 (current)
- ★ level (1-2 touches): stop = level − $0.35 (less trust)

**Backtest implementation:**
Pass `level_stars` (already available in `key-levels.json` via heartbeat's level-quality scoring)
into the stop calculation:
```python
stop_buffer = {3: 0.75, 2: 0.50, 1: 0.35}.get(level_stars, 0.50)
chart_stop = reclaim_level - stop_buffer
```

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (primary — especially on ★★★ named levels)
- BEARISH_REJECTION_RIDE_THE_RIBBON (bear entries at ★★★ resistance: extra $0.25 room on
  the upper side)
- ORB_RETEST_LONG (ORH star-rating from the OR quality filter could gate stop width)

**Failure mode it fixes:**
Chart stop firing on a $0.60 retest dip at a ★★★ 8-touch level that historically has always
recovered — the level HAS THE HISTORY to justify the wider stop.

**Failure mode it introduces:**
Larger dollar loss on genuine failures at ★★★ levels. A ★★★ level that truly breaks costs
more with the wider stop. Net: if ★★★ levels have WR ≥ 70%, the extra stop cost is justified.
If WR < 55%, wider stop destroys expectancy.

**Stop interaction:**
ONLY changes chart stop distance. Premium stop (−8%) is unchanged. In low-VIX environments,
the premium stop often fires first — so the chart-stop widening alone may not solve the problem
unless paired with Design 1 (earlier entry) or Design 2 (retest tolerance).

**Falsification criteria:**
- ★★★ level WR < 60%: wider stop at high-quality levels is not justified.
- Per-trade expected value (exp $ per trade) decreases with wider stop.
- Anchor day (5/05 — J loser) fires wider stop and produces MORE loss than baseline.

**Implementability:** VERY HIGH. `level_stars` field is in `key-levels.json`. Requires passing
it through `BarContext.levels_active` or as a separate field. The formula change is 3 lines.

---

### Design 8 — MULTI-BAR RIBBON STRENGTH GATE (lower impact, lower implementability)

**Slug:** `ribbon_strength_gate`
**Rank:** #8 — requires the ribbon to be "trending cleanly" before entry, not just flipped

**Trigger description:**
After the ribbon flips BULL on bar N, require the ribbon to have been BEAR for ≥ 3 bars before
the flip (ribbon held the bear direction consistently, not bouncing). A ribbon that has been
MIXED→BEAR→BULL→BEAR→BULL (cycling) is a compression zone — the "flip" is noise, not momentum.
Only enter on the FIRST CLEAN FLIP from a sustained BEAR period.

**Backtest implementation:**
Count consecutive BEAR ribbon states before bar N:
```python
consecutive_bear = 0
for prior_ribbon in reversed(ribbon_history[:-1]):  # exclude current (BULL) bar
    if prior_ribbon == RibbonState.BEAR:
        consecutive_bear += 1
    else:
        break
if consecutive_bear < 3:
    return False  # ribbon was cycling — not a clean setup
```

**Which strategies it applies to:**
- BULLISH_RECLAIM_RIDE_THE_RIBBON (filter on FIRST CLEAN flip from sustained BEAR)
- BEARISH_REJECTION_RIDE_THE_RIBBON (symmetric: BULL sustained ≥3 bars before BEAR flip)

**Failure mode it fixes:**
Entries on ribbon oscillation days (chop with repeated BULL↔BEAR flips) — these are the worst
cases for both premium stops AND retest wicks because there is no real directional momentum.
A 3-bar sustained prior direction gate blocks entries in true chop.

**Failure mode it introduces:**
Missing valid reclaims on days where the ribbon JUST flipped for the first time on bar N (prior
bars N-1, N-2 were MIXED or briefly BULL). This is a meaningful miss risk on days like 4/29
where the ribbon flip happens quickly. Must verify anchor days.

**Stop interaction:**
Unchanged. The gate reduces fire frequency in chop, which means stop/trade is the same quality
but fewer stops paid in choppy environments.

**Falsification criteria:**
- Any anchor day trigger bar has < 3 prior consecutive BEAR bars: design misses J's anchors. REJECT.
- WR improvement < 3pp: ribbon-strength requirement adds friction with no quality gain.
- Fire rate drops > 60%: filter is too conservative.

**Implementability:** MEDIUM. `ribbon_history` is already in `BarContext`. The consecutive-count
loop is simple. Risk: `RIBBON_FLIP_LOOKBACK_BARS = 3` is the existing constant — this design
requires exactly 3 or more prior BEAR bars, which matches the lookback depth exactly. If the
lookback is too short to detect sustained trends (e.g., a 20-bar sustained BEAR with only 3-bar
history), the filter under-counts. May need to increase `RIBBON_FLIP_LOOKBACK_BARS` to 6-8.

**Falsification criteria:**
- Lookback increase (3→6) changes any anchor day result.
- Consecutive-bear count excludes J's 4/29 or 5/04 anchor entries.

---

## Priority ranking: impact × implementability

| Rank | Design | Impact | Impl | Notes |
|---:|---|---|---|---|
| 1 | LIMIT-AT-TRIGGER-CLOSE | Very High | Very High | One param change; fixes root cause |
| 2 | RETEST-WICK TOLERANCE ZONE | High | High | 1-bar stop suppression; safe guard intact |
| 3 | VOLUME-ABSORPTION CONFIRM | High | High | ORB watcher is the proof-of-concept |
| 4 | CANDLESTICK QUALITY GATE | Medium | Very High | Zero new code — existing primitives |
| 5 | LEVEL-TIERED STOP | Medium | Very High | 3 lines; needs level_stars in BarContext |
| 6 | PRE-RIBBON-FLIP LIMIT | High | Medium | MIXED ribbon branch; validator changes needed |
| 7 | CONSOLIDATION-ANCHOR ENTRY | High | Medium | New primitive needed; miss rate risk |
| 8 | RIBBON STRENGTH GATE | Medium | Medium | Lookback constraint; anchor day risk |

**Recommended execution order for Kitchen:**
1. First: Design 6 (Candlestick Quality Gate) — 30-minute implement, immediate edge read
2. Second: Design 1 (Limit-at-Trigger-Close) — fill model change, direct miss-week test
3. Third: Design 5 (Volume Absorption Confirm) — port from ORB watcher
4. Then: Designs 2, 7, 8 as refinements
5. Design 4 (Consolidation-Anchor) is a research direction, not a near-term cook

**Combo proposal:** Design 1 + Design 6 together. Enter at trigger-bar close ONLY on high-quality
candlestick bars (hammer/marubozu/decisive-body ≥ 0.65). This eliminates retest-wick exposure
(earlier fill) AND screens for contested-reclaim bars (quality gate). Expected: highest WR of
any single combination.

---

## Disclosures (per OP-20)

1. **Account-size assumption:** All analysis in terms of per-contract P&L (strategy-neutral
   across account sizes). Missed-week data from SAFE (ATM, qty=15) and BOLD (ITM-2, qty=15)
   configs — not equity-scaled. For a $1K account (qty=3), missed-week losses scale proportionally.

2. **Sample-bias disclosure:** Motivating failure sample is N=4 days (2026-05-26..29) during a
   low-VIX grind regime (VIX 15-16). All four days closed at-or-above open (SPY bull bias).
   This regime (low-VIX, slow grind, bull direction) is NOT the same regime as J's confirmed
   anchor wins (4/29, 5/04 — high-VIX, sharp reversal, bear direction). The entry mechanics
   designs are derived from the bull-reclaim failure mode, but most designs apply symmetrically
   to bear-rejection. The low-VIX bull-grind finding may not generalize to high-VIX conditions.

3. **Out-of-sample test result:** No OOS test conducted — this is a DESIGN proposal with no
   backtest yet. Each design includes falsification criteria that constitute its OOS gate. The
   Kitchen should run full-window backtests (2025-01-01..2026-05-22) with OOS split at 2025-10-31.

4. **Real-fills check:** No OPRA real-fills validation conducted. The missed-week analysis DID
   use real OPRA fills (OPRA 5m grid), but the entry-timing designs have not been tested against
   actual option premiums at different entry times within the same bar. Real-fills check is
   mandatory before any design is promoted (OP-20 disclosure 4, L50).

5. **Failure-mode enumeration:** Each design above contains an explicit "Failure mode it
   introduces" section. The primary cross-cutting failure mode: these designs trade off
   false-positive retest stops for miss rate on V-launch days. Any design with miss rate
   >35% on J-winner anchor days must be REJECTED per OP-16, regardless of aggregate improvement.

6. **Concentration:** N/A (no backtest run). When the Kitchen runs these, top5_pct must be
   computed and disclosed. If any design produces top5_pct > 75% (five days driving 75%+ of
   P&L), flag as concentration risk.

---

## Knob changes proposed

These are DESIGN-TIME knob proposals. None should be written to params.json until at minimum:
(a) Kitchen backtest run with real-fills confirms edge_capture ≥ 771, (b) J weekend ratification.

| Design | Knob | Current | Proposed | Location |
|---|---|---|---|---|
| 1 | `entry_fill_model` | `next_bar_open` | `trigger_bar_close` | simulator_real.py param |
| 2 | `retest_tolerance_bars` | `0` (not implemented) | `1` | simulator_real.py param |
| 5 | `absorption_confirm_enabled` | `false` | `true` | filters.py flag |
| 6 | `min_trigger_body_ratio` | `0.0` (not enforced) | `0.65` | filters.py constant |
| 6 | `require_hammer_or_marubozu` | `false` | `true` (soft mode) | filters.py flag |
| 7 | `chart_stop_buffer_by_stars` | `{*: 0.50}` (flat) | `{3: 0.75, 2: 0.50, 1: 0.35}` | params.json |
| 8 | `min_prior_ribbon_bars` | `0` | `3` | filters.py constant |

---

## Pre-merge gate

Each individual design, when Kitchen-run, must pass:

```
1. python crypto/validators/runner.py — all PASS (no existing validator must regress)
2. edge_capture >= 771 (50% of max 1542) per OP-16
3. Anchor anchor-day check: J's 4/29, 5/01, 5/04 engines still fires (not blocked by new gate)
4. J loser days (5/05, 5/06, 5/07) do not generate MORE loss than baseline
5. Walk-forward: OOS/IS ratio >= 0.50
6. Real-fills: OPRA P&L deviation from SPY-proxy < 25%
```

Current validator status: not run (design-only proposal). When Kitchen implements any design,
runner.py must be verified before and after.

---

## My confidence (1-10) and why

**4/10** — This is a design document, not a validated candidate. The 4/10 reflects:
- High confidence (8/10) that the retest-wick problem is real and correctly diagnosed
- Low confidence (2/10) in specific parameter values for any design without a backtest
- Medium confidence (5/10) that Designs 1+6 combined will show improvement in Kitchen backtest
- The missed-week sample (N=4 days, single regime) is too small for any design to claim
  definitive edge at this stage

The strongest single bet: **Design 6 (Candlestick Quality Gate)** — it requires zero new code,
directly filters the "contested reclaim" bar pattern that produces retest wicks, and all the
detection primitives are already in `backtest/lib/filters.py`. If it fails, the failure is
informative (anchor day bars don't have decisive bodies). If it passes, it's cheap to deploy.

Second strongest bet: **Design 1 (Limit-at-Trigger-Close)** + **Design 2 (Retest Tolerance)** as
a pair — one shifts the entry timing, the other gives the stop one bar of breathing room. Together
they directly address the mechanical failure: entry into the retest wick.
