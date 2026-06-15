# Strategy Candidate: BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON (DRAFT — WATCH-ONLY)

**Status:** DRAFT — NOT LEADERBOARD-ELIGIBLE. Live watcher data (2026-05-24) shows net negative expectancy across all confidence tiers. Historical scan P&L was SPY-proxy inflated (L50 lesson). See live watcher analysis below.  
**OP-21 classification:** WATCH-ONLY (stay-watch, do not promote)  
**Created:** 2026-05-19  
**Scan completed:** 2026-05-19 (overnight session) — 4 signals, 3 wins, 75% WR — OP-21 historical gate: PASS (scan-level; BUT scan P&L was `drop_2h × contracts`, not OPRA real fills)  
**Real-fills validation:** 2026-05-19 — 0/4 wins, -$263.52 total. -6% stop fires within 10 min on all signals (scanner had timezone bug — all signals were opening-range bars). See OP-20 Disclosure.  
**Live watcher audit (2026-05-24):** 66 deduped closed observations from `bearish_reversal_at_level_watcher` (correct 11:00-14:30 ET gate). **ALL conf: N=61 WR=41.0% exp=-$3.55 (NEGATIVE).** HIGH conf: N=10 WR=50.0% exp=-$13.32 (IS exp=-$26.44, OOS exp=-$0.20 — WF guard fires, both periods negative). Medium conf: N=45 WR=35.6% exp=-$7.34. Low conf: N=6 WR=66.7% exp=+$41.08 (N too small). **Combined-pool analysis was contaminated by 4 historical scan entries that used SPY-price proxy P&L (not OPRA real fills) — this inflated overall stats. True signal is net negative.**  
**Related:** OP-23 (SNIPER_LEVEL_BREAK), T-2026-05-19-02, Config F27 candidate spec

---

## Problem Statement

J's 5/01 +$470 trade is NEVER captured by any VIX/ribbon relaxation because the root cause is structural:
- SPY ribbon was BULL-stacked ALL DAY on 5/01 (F5 = structural hard block on bear setup)
- J entered 721P at 13:36 on a **trendline rejection** — not a ribbon continuation, but a reversal
- The engine correctly identifies a BULL-ribbon day and fires BULLISH setups (calls), not bearish
- No amount of F6/F7/F8 relaxation fixes F5 (ribbon direction = structural gate)

**The setup J traded on 5/01 is a different archetype**: reversal at key level when price is extended and the trend is exhausted, DESPITE an active bull ribbon.

---

## Proposed Setup: BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON

### Trigger conditions (ALL required)

1. **F5 inverted gate**: Ribbon stack = BULL (opposite of normal bear setup requirement)
2. **Extended trend**: SPY has trended UP ≥ $3.00 from RTH open before the reversal setup
3. **★★★ level rejection**: SPY touches a named ★★★ level (PDH, 5d_high, PMH, monthly open, or J-designated carry level) AND the bar closes ≥ 15c BELOW the level (rejection body)
4. **Volume confirmation**: volume ≥ 2.0× 20-bar avg at the rejection bar (higher threshold than normal 1.5× because we're fading the trend)
5. **Time gate**: only fires AFTER 11:00 ET (avoids early morning chop/fake-outs)
6. **HTF_15M divergence**: 15m HTF does NOT show strong bull momentum (e.g., 15m last bar = red/flat, OR price approaching upper Bollinger band)

### Why this is different from current BEARISH_REJECTION_RIDE_THE_RIBBON
- Current setup: BEAR ribbon already established → riding continuation
- This setup: BULL ribbon (trend in progress) → fading at exhaustion level
- This setup is COUNTERTREND, which means:
  - Higher false-positive rate → stricter volume/level threshold
  - Shorter hold time (ride the initial move, not the trend)
  - Smaller runner target (1.5× instead of 2.0×)
  - Tighter stop (-6% instead of -8%)

### Exit rules (WATCH-ONLY defaults)
- TP1: +25% (take partial earlier than continuation setup)
- Runner target: 1.5× entry premium
- Stop: -6% premium stop (tighter — countertrend setup has less runway)
- Time stop: 15:00 ET hard (same as entry gate)

---

## Evidence

### 5/01 J trade anatomy
- SPY opened ~$521, rallied to ~$523-524 zone (bull ribbon, continuation)
- J's trendline: declining resistance from prior days, connecting ~722 area at 13:36
- At 13:36: SPY touches 721-722 → rejects → closes below trendline
- VIX: 16.87 (low, flat — not the elevated VIX that the bear setup prefers)
- This was a textbook trendline/level rejection on a bull ribbon day — a FADE of the morning trend

### Historical scan results (completed 2026-05-19)

Scanner: `backtest/autoresearch/bull_ribbon_reversal_scan.py`  
Output: `analysis/recommendations/bull_ribbon_reversal_scan.json`

| Date | Time | Level | Body | Vol | VIX | Drop 2h | Result |
|------|------|-------|------|-----|-----|---------|--------|
| 2025-04-23 | 13:35 | 543.19 | 132c | 3.8× | 28.4 | $4.87 | **WIN** |
| 2026-03-23 | 13:40 | 659.80 | 181c | 3.3× | 25.0 | $0.60 | loss |
| 2026-03-23 | 13:50 | 659.80 | 22c | 2.1× | 25.0 | $2.48 | **WIN** |
| 2026-03-31 | 14:05 | 641.46 | 25c | 2.5× | 25.8 | $3.24 | **WIN** |

**342 days scanned | 131 bull-ribbon days | 4 signals | 3 wins | 75% WR**  
Avg drop on wins: $3.53 | Avg drop on loss: $0.60 | Expectancy est: $93.75/signal

**OP-21 historical gate: 3/3 PASS ✓**

**Important caveat on J's 5/01:** J's 5/01 +$470 trade was a TRENDLINE rejection, not a static PDH/5DH/monthly-open level. The scanner only detects hard auto-computable levels. J's 5/01 would NOT appear in this scan. The 4 signals above are J-day-independent analogs — similar setup archetype, different specific level type. Full coverage of J's trendline-based entries would require pulling drawn levels from `automation/state/key-levels.json` (future enhancement).

**Same-level double-fire issue (2026-03-23):** Two consecutive signals at the same level (659.80). The first was a loss, the second was a win. A live engine would need a same-level cooldown to avoid duplicate entries. The second signal had a much smaller rejection body (22c vs 181c) — counter-intuitive but the large-body first failure may have "cleared" overhead supply, making the second entry cleaner.

---

## OP-21 Required Gates

- [x] 3+ historical wins: **3/3 PASS** (3 wins in 4 signals across Jan 2025 – May 2026)
- [ ] 3+ live J-confirmed: **0/3** — WATCH-ONLY until met
- [ ] Positive expectancy over 16-month backfill: **directionally positive** ($93.75 est.) — N=4 too small for confidence, needs watcher data
- [ ] Per-confidence-tier expectancy positive: **not enough data** (all 4 signals had similar VIX 25–28 context)
- [ ] Complement score (not cancel existing setup): **structurally YES** — fires on BULL ribbon days (38.3% of days); F27/baseline bears fire on BEAR ribbon days. No signal overlap.
- [ ] J's explicit ratification: **not yet**

**DO NOT add to production heartbeat.md until all OP-21 gates pass.**

---

## Implementation plan (post-ratification)

If OP-21 gates pass, the implementation would be:
1. Add `evaluate_bearish_reversal_at_level()` to `backtest/lib/filters.py`
2. Wire as a second `evaluate_*` call in `orchestrator.py` (after the main bearish setup check)
3. Write validator `crypto/validators/v23_bull_ribbon_reversal.py` for gym
4. Add watcher `lib/watchers/bull_ribbon_reversal_watcher.py` for live watch-only tracking
5. Weekend ratification once OP-21 gates pass

### Same-level cooldown (dedup logic) ✓

The 2026-03-23 double-fire at level 659.80 (13:40 loss → 13:50 win, 10 min apart) exposes
a dedup requirement for the live engine. Without a cooldown, a failed first attempt at a
level on the same day would immediately re-enter on the next bar's rejection body.

**Rule:** same-level cooldown = **1 bar minimum (5 minutes) between signals at the same
level (within $0.50 tolerance) on the same day.** Implementation:

```python
# Pseudocode for filter state
_last_fire_by_level: dict[str, tuple[date, datetime]] = {}  # level_key -> (date, ts)

def _level_key(level: float) -> str:
    return str(round(level * 2) / 2)   # round to $0.50 grid

def _same_level_cooldown_ok(level: float, trade_date: date, bar_ts: datetime,
                              cooldown_bars: int = 1) -> bool:
    key = _level_key(level)
    if key not in _last_fire_by_level:
        return True
    last_date, last_ts = _last_fire_by_level[key]
    if last_date != trade_date:
        return True
    return (bar_ts - last_ts).total_seconds() >= cooldown_bars * 300   # 5 min per bar
```

Note: the 03-23 second signal had a much smaller rejection body (22c vs 181c) and still
won — suggesting the first large-body failure may have "cleared" overhead supply. A
cooldown of 1 bar prevents duplicate entry but still allows the second (cleaner) entry.
Extending the cooldown to 2 bars (10 min) would be more conservative for a live engine.

---

## OP-20 Disclosure (mandatory before any ratification claim)

**Real-fills validation completed 2026-05-19.**

| Disclosure item | Detail |
|---|---|
| Account-size assumption | qty=3 contracts (~$1K paper account, $150-500 total premium at entry) |
| Simulator used | `simulator_real.py` — OPRA cache, real fills. NOT Black-Scholes. |
| Strike selection | ITM-2 (strike_offset=-2): for puts, strike = ATM+2. 3 of 4 signals used fallback strikes (exact strike not in OPRA cache; nearest available used instead) |
| TP1 / runner knobs | Standard simulator defaults (+30% TP1, +300% runner); spec WATCH-ONLY knobs (+25% / 1.5×) would exit earlier — losses may be slightly worse at spec knobs |
| Out-of-sample status | N=4 signals over 16 months — statistically insufficient; OP-21 requires 3+ live J-confirmed observations |
| **CRITICAL — Timezone bug in scanner** | `bull_ribbon_reversal_scan.py` used UTC times for the 11:00 ET gate. All 4 scan signals fire at 09:35-10:05 ET (OPENING RANGE), not post-11:00 ET as the spec requires. As correctly designed (post-11:00 ET): **N=0 valid historical signals in 342 days.** The 4 signals validated here are opening-range setups — a DIFFERENT archetype. |
| Concentration | All 4 signals cluster at 09:35-10:05 ET (scanner UTC bug — appeared as 13:35-14:05 in raw output). Not post-11:00 ET countertrend setups. Correctly-timed (post-11:00 ET) setup has N=0 historical observations. |
| Failure mode | Opening-range volatility causes -6% stop to fire within 10 min. Post-11:00 ET version untested — no confirmed historical examples. |
| Blow-up scenario | Max loss = 6% premium x 3 contracts = ~$70-100/signal; multiple consecutive losses possible on low-signal-rate setup (4 signals in 16 months) |

**Real-fills results:**

| Date | Time | Scan result | Real-fills P&L | Exit | Strike used | Note |
|------|------|-------------|---------------|------|-------------|------|
| 2025-04-23 | 13:35 | WIN ($4.87 drop) | **-$63.90** | Premium stop (-6%) | P540 (fallback from P544) | OTM-2 used due to cache miss |
| 2026-03-23 | 13:40 | loss ($0.60 drop) | **-$69.84** | Premium stop (-6%) | P660 (exact ITM-2) | Expected loss; real-fills agrees |
| 2026-03-23 | 13:50 | WIN ($2.48 drop) | **-$48.06** | Premium stop (-6%) | P660 (fallback from P662) | Scan WIN flipped to real loss |
| 2026-03-31 | 14:05 | WIN ($3.24 drop) | **-$81.72** | Premium stop (-6%) | P645 (fallback from P643) | Scan WIN flipped to real loss |

**Total: -$263.52 over 4 signals. Scan-to-real agreement: 1/4 (25%).**

**OP-20 verdict: REAL-FILLS NEGATIVE. Scan-estimated $93.75/signal expectancy does NOT survive real OPRA fills.**

The root cause is not a wrong directional signal — SPY did drop on 3 of 4 days. The issue is that these are opening-range bars (09:35-10:05 ET, scanner UTC bug made them appear as "13:35-14:05"). At open, 0DTE options have elevated IV and wide bid-ask spreads; the -6% stop fires on the first adverse tick before SPY direction resolves. The premium on 2025-04-23 P540 dropped from $3.55 (entry) to a low of $1.85 (option bar low) before recovering to $4.87. The -6% stop fired within 10 minutes.

**Required before any live consideration:** widen stop to -12% OR switch to delayed entry (enter 1 bar after the signal bar when premium has stabilized) OR both. Run second real-fills pass with these adjustments.

---

## Research queue

Per T-2026-05-19-02 in queue.md:
- [x] Build `backtest/autoresearch/bull_ribbon_reversal_scan.py` — scan 16 months for historical examples
- [x] Backtest basic version (time >11:00 + ★★★ level + vol 2.0× + bull ribbon)
- [x] Calculate expectancy and per-quarter stability
- [x] Write to `analysis/recommendations/bull_ribbon_reversal_scan.json`
- [x] Real-fills validation: run `simulator_real.py` on 2025-04-23, 2026-03-23 ×2, 2026-03-31 — **DONE 2026-05-19**. Script: `backtest/autoresearch/bull_ribbon_reversal_realfills_validate.py`. Output: `analysis/recommendations/bull_ribbon_reversal_realfills.json`. Result: **0/4 wins, -$263.52 total**. See OP-20 Disclosure section below.
- [ ] Stop mechanics R&D: test wider stop (-12%) or delayed entry (wait 1 bar post-signal) to see if real-fills can recover scan-level win rate before watcher promotion
- [ ] Trendline level detection: extend scanner to use `automation/state/key-levels.json` drawn levels
- [x] Same-level dedup logic: implement cooldown (1 bar minimum) to prevent double-fire on same level same day — **DONE 2026-05-19**. Pseudocode added to Implementation plan above.
- [x] Watcher wiring: `bearish_reversal_at_level_watcher.py` built and registered in `backtest/lib/watchers/runner.py` — **DONE 2026-05-19**. Correctly implements 11:00-14:30 ET gate using `ctx.timestamp_et.time()` (ET-aware, no timezone bug). Watch-only per OP-21.
- [ ] Live observation: log 3 live J-confirmed observations before any promotion
- [ ] Late-day premium decay analysis: measure expected premium remaining at 14:00 ET for ATM 0DTE puts
- [ ] J review + ratification for any live trading consideration

---

## OP-20 Disclosure Block — Full (Track 2 sprint, 2026-05-19)

*This section completes all 6 mandatory OP-20 items. Supplementary to the brief table above.*

### 1. Account-size assumption

- **Watch-only — no live orders placed.**
- Simulated with **qty=3 contracts** (minimum per rule 6; consistent with Gamma-Safe-1 $1K paper context).
- At $1K paper account, 3× ATM puts at $2.50–$4.50 premium = $750–$1,350 notional (75–135% of equity).
  This **exceeds the 30% Gamma-Safe per-trade risk cap**. Sizing must be 1 contract at the $1K tier
  if this setup is ever promoted. The expectancy numbers in this spec are stated in 3-contract terms
  for comparability with the scan output; real $1K deployment would be ~1/3 of these figures.

### 2. Sample-bias disclosure

- **N = 4 signals** from a 342-day scan (Jan 2025 – May 2026). Extremely thin sample.
- **CRITICAL: Scanner timezone bug.** The scanner reads SPY timestamps as UTC-aware and calls
  `.time()` to get the local time — but returns UTC (4h ahead of ET). The "11:00 ET" time gate
  is checking 11:00 UTC = 07:00 ET (pre-market). All 4 signals fire at **09:35–10:05 ET
  (the opening range)**, not post-11:00 ET as the spec intends.
  - As designed (truly post-11:00 ET): **0 valid historical signals in 342 days.**
  - The 4 signals above are OPENING RANGE rejections — a different setup archetype entirely.
- **Regime concentration:** All 4 signals with VIX 25.0–28.4. No signals in low-VIX (<20) or
  extreme-VIX (>30) environments.
- **Quarter concentration:** 0 signals in Q1-2025, Q3-2025, Q4-2025. 1 in Q2-2025, 3 in Q1-2026
  (2 of which on the same day). Effective independent observations: ≤ 3 dates.
- **Overfitting risk: HIGH.** 6 filter conditions producing 4 signals from 342 days is a severe
  ratio (1.2% hit rate). The filters likely describe these 4 bars rather than a general pattern.

### 3. Out-of-sample test result

**Not performed. Cannot be performed at N=4.**

Minimum credible walk-forward: 30+ signals. With 4 signals across 16 months, a 50/50 split
yields 2 observations per window — statistically meaningless. Any OOS test result would have
error bars wider than the signal itself.

Required before OOS is meaningful: fix the scanner timezone bug, re-run on corrected 11:00 ET
gate, accumulate 30+ signals (estimated 3–5 additional years at current signal rate), then
perform proper walk-forward validation.

### 4. Real-fills check

**Completed 2026-05-19.** Script: `backtest/autoresearch/bull_ribbon_reversal_real_fills.py`  
Output: `analysis/recommendations/bull_ribbon_reversal_real_fills.json`  
Knobs: ATM strike (watch-only), TP1 +25%, runner 1.5×, stop −6%, qty=3

| Date | Actual ET (scan shows UTC) | Strike | Entry $ | Exit reason | Hold | P&L |
|------|---------------------------|--------|---------|-------------|------|-----|
| 2025-04-23 | 09:35 ET (scan: "13:35") | P540 (OTM-2 proxy; ATM=542 not cached) | $3.55 | PREMIUM_STOP −6% | 10 min | **−$63.90** |
| 2026-03-23 | 09:40 ET (scan: "13:40") | P658 (exact ATM — full cache hit) | $2.84 | PREMIUM_STOP −6% | 10 min | **−$51.12** |
| 2026-03-23 | 09:50 ET (scan: "13:50") | P660 (exact ATM — full cache hit) | $2.67 | PREMIUM_STOP −6% | 10 min | **−$48.06** |
| 2026-03-31 | 10:05 ET (scan: "14:05") | P645 (ITM-4 proxy; ATM=641 not cached) | $4.54 | PREMIUM_STOP −6% | 10 min | **−$81.72** |
| **TOTAL** | | | | | | **−$244.80** |

**Real-fills verdict: 0/4 wins. All signals hit the −6% premium stop within 10 minutes.**

Root cause: these are opening-range bars (09:35–10:05 ET). At open, options have elevated IV and
wide bid-ask spreads. The bull ribbon is actively trending; any initial rejection body is followed
by immediate mean-reversion as bulls absorb supply. The −6% stop fires on the first adverse tick
of the next bar. SPY does eventually drop on 3 of 4 days, but after the option has already stopped
out. This confirms that opening-range stops need to be wider or use a delayed-entry mechanism.

### 5. Failure-mode enumeration

1. **Scanner timezone bug → 0 real post-11:00 ET signals.** The primary failure: the setup as
   specified has never been observed in 342 days. This invalidates the 3/3 OP-21 win gate
   against the intended post-11:00 ET archetype.

2. **V-shaped recovery.** Opening-range level rejections on bull-ribbon days almost always see
   immediate V-recovery as trend resumes. All 4 real-fills confirm this pattern.

3. **False rejection body in opening volatility.** Large rejection bars (181c on 03-23) appear
   in opening range as volatility settles, then completely reverse. High vol_ratio at open
   reflects spike in opening volume, not sustained bearish conviction.

4. **Premium stop too tight for opening-range holds.** −6% stop designed for post-11:00 ET
   (lower IV, tighter spreads, more directional options). At 09:35–10:05 ET, ATM options
   routinely move ±10–15% on a single 5-minute bar due to wide bid-ask and IV uncertainty.

5. **Same-level re-entry without cooldown.** The 03-23 double-fire is an execution risk: without
   the 1-bar cooldown (documented in Implementation plan), the engine would enter twice at the
   same level within 10 minutes, doubling the loss on an already-losing signal.

6. **Worst-case blow-up:** Max loss = 6% × entry premium × 300 (3 contracts). At $4.50 entry:
   ~$81 per signal. Four consecutive losses = −$325. On a $1K account with 3 contracts, this is
   a 32.5% drawdown from 4 signals — approaching the 30% daily kill switch for Gamma-Safe.

### 6. Concentration disclosure

- **Signal rate:** 4 signals / 342 days = 1.2% of trading days. ~1 signal per quarter.
- **Date concentration:** 2 of 4 signals on same day (2026-03-23), same level (659.80). Treating
  these as 4 independent observations overstates evidence by ~33%.
- **Quarter concentration:** 75% of signals in Q1-2026. Zero signals in Q3-2025, Q4-2025.
  The setup has no evidence of working in trending low-VIX markets (Q3/Q4 2025 were such).
- **Regime bias:** 100% of signals in VIX 25–28 "elevated but not panic" regime. No evidence
  for VIX < 20 (normal trending days) or VIX > 30 (high-panic regime).
- **P&L concentration:** All 4 real-fills are losses. No P&L to concentrate.

### OP-20 verdict (Track 2)

**BLOCKED — NOT promotion-ready.**

Critical blockers (must resolve before watcher promotion):
1. Fix scanner timezone bug in `bull_ribbon_reversal_scan.py` (ET vs UTC confusion)
2. Re-run scan with corrected time gate — expect 0 signals; confirm post-11:00 ET archetype exists
3. Real-fills currently 0/4 wins; stop mechanics require R&D (−12% stop or delayed entry)
4. Sample size N=4 (≤3 independent dates) — insufficient for any statistical claim
5. Account-size constraint: $1K paper requires 1-contract sizing, not 3

**Status confirmed: WATCH-ONLY — DRAFT.** No watcher promotion until items 1–3 resolved.
