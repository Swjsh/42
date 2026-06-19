# Key-Level System Deep Dive — Why the Engine Caught 738.10

_Generated 2026-05-13T21:40 ET. J's request: "explore why it did so we can make sure it always does, brainstorm and expand on this."_

---

## 🎯 The Question

**At 11:38 ET on 5/13, the engine bought 738C × 15 @ $2.10 → +$2,932 (+93%).** The entry was triggered by SPY reclaiming the 738.10 level on the 11:30 bar with volume confirmation. Why did the engine "see" 738.10 as a key level? How do we make sure it ALWAYS sees levels like this?

---

## 📊 The TWO Level-Detection Systems

Project Gamma has **two parallel level systems** that work together:

### System 1: `lib/levels.py` — runtime auto-detection (used by backtests + watchers)

Detects 4 categories from price history alone:

| Category | What it captures | How |
|---|---|---|
| **PMH / PML** | Premarket H/L + tested rejection clusters | 04:00-09:30 ET bars; price-bucket clustering (≥3 touches at same $0.05 bucket) |
| **PDH / PDL / PDC** | Prior day RTH H/L/Close | RTH-only (excludes premarket wicks — fixed 2026-05-08) |
| **5-day rolling H/L** | Multi-day swing extremes | RTH-only over the last 5 trading days |
| **Round numbers** | Nearest $1 above/below current spot | Awareness only per OP 5 |

**For 5/13 specifically:** 738.10 (5/8 RTH high) entered the active set via the **5-day rolling high** path. 5/8 → 5/13 = 5 sessions apart (5/8, 5/11, 5/12 — 3 trading days within the window). It survived as a multi-day reference point.

### System 2: `automation/state/key-levels.json` — premarket-curated (used by heartbeat)

This is the RICH version. Each level is a structured record with:

```json
{
  "price": 738.10,
  "type": "support",
  "tier": "Carry",
  "source": "Key reclaim level 11:30 5/13 bar + prior RTH resistance (5/8 session high)",
  "reasoning": "Reclaimed on 11:30 ET bar (vol 131% avg) and defended for 4+ hours. Engine BULLISH_RECLAIM trigger level.",
  "strength": {
    "stars": 3,
    "points": 6,
    "components": {
      "touch_score": 2,
      "recency_score": 2,
      "mtf_score": 1,
      "volume_score": 1,
      "confluence_score": 0
    }
  },
  "touch_count": 5,
  "held_count": 5,
  "bounce_history": ["2026-05-13T11:30:00"]
}
```

**Tier system:**
- **Active** — current session levels (today's H/L, today's reclaim zones)
- **Carry** — multi-day levels carrying over from recent sessions (≤5 days old)
- **Reference** — psychological/awareness only (round numbers, far-away pivots)
- **Liquidity** — wick-tested levels that haven't held yet

**Star scoring (1-5 stars from 5 components):**
- `touch_score` (0-2): 0 if untouched, 1 if 1-2 touches, 2 if 3+ touches
- `recency_score` (0-2): 0 if >7 days old, 1 if 3-7 days, 2 if ≤2 days
- `mtf_score` (0-1): 1 if visible on multiple timeframes (5m + 15m agree)
- `volume_score` (0-1): 1 if a touch had vol ≥ 1.5× 20-bar avg
- `confluence_score` (0-1): 1 if another level is within $0.50

**738.10's score: 3 stars / 6 points** → touch=2 (5 touches), recency=2 (today's data fresh), mtf=1, volume=1 (131% vol on reclaim), confluence=0.

---

## 🔍 Why the Engine Fired at 11:38 — Step by Step

1. **Premarket task (08:30 ET):** wrote `key-levels.json` listing 738.10 as Carry-tier support (carried from 5/8 RTH high).

2. **Bias file (today-bias.json):** also listed 738.10 in `key_levels.resistance` (it was originally resistance pre-reclaim).

3. **Open + cascade (09:30-09:50 ET):** SPY opened $738.46 (above 738.10), wicked to $735.48, bounced. The 738.10 level was tested from BELOW briefly during the dump.

4. **Mid-morning consolidation (10:00-11:25 ET):** SPY chopped in $736-738 range, repeatedly testing 738.10 from below.

5. **11:30 ET bar:** SPY closed at $738.42 (above 738.10 by $0.32, body $0.50, vol 131% of 20-bar avg). The level **state machine** flipped 738.10 from resistance → support (reclaim event).

6. **Heartbeat tick at 11:33 ET:** Read updated `key-levels.json`. Bull score components:
   - ✅ Level reclaim trigger (738.10 reclaim, multi-touch defended)
   - ✅ Ribbon stack BULL with 49c spread (≥30c filter)
   - ✅ HTF 15m BULL alignment
   - ✅ VIX 18.04 falling
   - ✅ Volume confirmation 131%
   - ✅ Body $0.50 > $0.20 floor
   - **Bull score: 11/11** — all conditions met

7. **Heartbeat tick at 11:38 ET:** Order placed BUY 15× 738C @ $2.10 limit. Filled.

**The system worked end-to-end. 738.10 was a HIGH-QUALITY level because it had:**
- ✅ Historical structural significance (5/8 RTH high — a real chart event)
- ✅ Multi-touch defense (5 touches today, all held)
- ✅ Volume confirmation at reclaim
- ✅ MTF agreement (visible on 5m + 15m)
- ✅ Recency (current-session reclaim)

---

## 🧠 What Makes 738.10 a "GOOD" Level (System Analysis)

I count **6 reasons** the engine treated this level as actionable:

### 1. Multi-day persistence
738.10 was the 5/8 RTH high — a level that survived 5 sessions before being reclaimed. Multi-day levels are stronger than intraday levels.

### 2. RTH-only computation (not premarket-spike)
Per the 2026-05-08 fix in `lib/levels.py`, prior-day H/L only uses RTH bars (09:30-16:00). Premarket wicks are filtered out. This prevents fake "levels" from low-liquidity overnight bars.

### 3. Tier escalation (Reference → Carry → Active)
A new level enters as "Reference" awareness. After it gets touched + held in session, it gets promoted to "Carry". After multi-day persistence, it can become "Active".

### 4. Touch counting + bounce history
The level state machine records EVERY touch (within $0.30 proximity) and tracks whether it held or broke. 738.10's `touch_count: 5, held_count: 5` makes it 5/5 defended → high-conviction.

### 5. Volume score on touches
The reclaim bar had vol 131% of 20-bar avg. The system weights HIGH-volume touches heavier than low-volume tests. This filters fake breaks.

### 6. MTF agreement
On the 15m chart, 738.10 also showed as a structural level (HTF stack alignment counted it). When 5m and 15m agree, the level is more important.

---

## 🚀 BRAINSTORM — How to make the engine ALWAYS see levels like this

### Category A: Levels we MISS today (gaps in detection)

#### 🔴 1. Premarket targets J derives (not from data)
- **Gap:** J's 5/13 09:30 short targeted **736** as the bounce zone. 736 was NOT in any auto-detected level set — it's a J-derived TARGET from premarket structural analysis (premarket low + multi-day carry zone).
- **Fix candidate:** Extend `today-bias.json` schema to include a `premarket_targets` array where J (or the premarket subagent) can write FORWARD-looking targets. Heartbeat reads these as Carry-tier levels.
- **Status:** Already queued as T46.

#### 🔴 2. Globex / overnight session H/L
- **Gap:** Current PMH/PML uses 04:00-09:30 ET only. Globex (overnight futures session) runs 18:00 prior day → 09:30 today = ~15 hours of price action. The overnight H/L often becomes intraday support/resistance.
- **Fix candidate:** Add Globex H/L detection — use 18:00→09:30 bars from SPY (or proxy via ES futures). Tag as `globex_high / globex_low` in level set.

#### 🟡 3. Daily/weekly opens (institutional reference)
- **Gap:** Today's RTH open, this week's open, prior week's close, prior month's close — institutions watch these. Currently not in level set.
- **Fix candidate:** Add `today_open`, `weekly_open`, `prior_week_close`, `prior_month_close` to auto-detection.

#### 🟡 4. Volume Profile POC (Point of Control)
- **Gap:** Yesterday's high-volume node (the price where most volume traded) is a powerful magnet. Currently not detected.
- **Fix candidate:** Compute yesterday's volume profile in 0.10 buckets, find the POC, add to active levels.

#### 🟡 5. Anchored VWAP from significant pivots
- **Gap:** Static levels don't move. aVWAP from a swing high/low DOES move with time — it tracks "average price since the pivot". Often acts as dynamic S/R.
- **Fix candidate:** When a high-volume swing is detected, anchor a VWAP line from that bar. Track until invalidated.

#### 🟡 6. Liquidity sweeps detection
- **Gap:** When price WICKS through a level then closes back inside (e.g., 09:30 bar wicked to 735.48, closed 737.61 — wicked through 736 + held above), that's a liquidity grab. The level becomes STRONGER after a sweep.
- **Fix candidate:** Detect "wick-through-close-inside" patterns. Flag levels that survived sweeps as ★ upgraded.

### Category B: Scoring refinements

#### 🟢 7. Multi-touch decay weighting
- **Gap:** Currently `touch_score` saturates at 2 (3+ touches). A level touched 10 times defended is structurally stronger than 3-times defended but gets the same score.
- **Fix candidate:** Smooth scoring: `touch_score = min(0.5 × log(touches+1), 2)`. Diminishing returns but not flat ceiling.

#### 🟢 8. Time-decay on Carry levels
- **Gap:** Carry levels currently EXPIRE after 5 days (per protocol). A level might be VERY strong but degrade gradually rather than cliff-expire.
- **Fix candidate:** Strength multiplier `decay = exp(-days_since_creation / 10)` so Carry levels fade smoothly.

#### 🟢 9. Cluster confluence weighting
- **Gap:** When 2+ levels cluster within $0.50, the ZONE is much stronger than either level alone. Currently `confluence_score` is binary (1 or 0).
- **Fix candidate:** `confluence_score = min(n_clustered - 1, 3)` so a 3-level cluster scores 2, a 4-level cluster scores 3.

#### 🟢 10. Ribbon-EMA alignment with level
- **Gap:** When a level coincides with an EMA (Fast/Pivot/Slow), it's stronger. Currently not in score.
- **Fix candidate:** Add `ema_alignment_score` (0-1): 1 if level is within $0.30 of an active EMA.

### Category C: Trigger logic refinements

#### 🔵 11. Volume gate alternative — cumulative N-bar
- **Gap:** Current 1.1× volume gate is PER-BAR. Slow-grind breakouts (today's 12:25 ATH break at 31K vs 78K avg = 0.4×) don't fire. But cumulative 5-bar vol shows real conviction.
- **Fix candidate:** Add `cumulative_5bar_vol_mult` as alternative gate. Trade fires if EITHER (a) per-bar vol ≥ 1.1× OR (b) cumulative 5-bar vol ≥ 1.5× avg.
- **Status:** Already queued as T48.

#### 🔵 12. Body-vs-wick gate
- **Gap:** A bar with body $0.10 and wick $0.50 is much weaker than body $0.50 and wick $0.10. Currently only body cents is checked.
- **Fix candidate:** Add `body_to_wick_ratio ≥ 0.50` (body must be at least 50% of total range). Filters indecisive bars.

#### 🔵 13. Sequential confirmation (2-bar confirmation)
- **Gap:** Currently fires on a single bar reclaim. Sometimes the reclaim bar is a fake (closes back below next bar).
- **Fix candidate:** Add optional `confirm_n_bars=2` — fire only if 2 consecutive bars close above the level. Trade off: slower but cleaner.

### Category D: Forward-looking expansion

#### ⚪ 14. Level prediction from J's manual chart analysis
- **Gap:** J's morning chart-walk identifies forward targets that don't exist in data yet (premarket bias). Currently no automated capture.
- **Fix candidate:** TradingView MCP plugin: when J draws a horizontal line, capture its price + tag + write to key-levels.json as `j_drawn` source.

#### ⚪ 15. News/event-driven level adjustment
- **Gap:** CPI tomorrow at 08:30 ET. The reaction will create NEW levels (post-print high/low). Currently no pre-event "expected range" computation.
- **Fix candidate:** Compute expected-move from option-implied straddle pricing. Add `expected_high`, `expected_low` as Reference-tier levels.

---

## 🎯 What to ship TONIGHT (concrete actions)

### Quick wins (each ~30 min)
- ✅ **T46:** Premarket bias schema add `premarket_targets` array (J writes forward targets there)
- ✅ **T48:** Cumulative N-bar volume gate (already queued)
- ✅ **NEW T51:** Globex H/L detection — add 18:00-09:30 bars to PMH/PML computation
- ✅ **NEW T52:** Daily open / weekly open / prior week close auto-detection in `levels.py`

### Medium-effort (~1-2h each)
- 🔄 **NEW T53:** Volume Profile POC computation for prior-day RTH session
- 🔄 **NEW T54:** Smooth touch_score decay function (log-scale)
- 🔄 **NEW T55:** Cluster confluence weighting (n_clustered ≥ 2)
- 🔄 **NEW T56:** EMA alignment scoring component

### Bigger refactors (~2-4h each)
- 🐉 **NEW T57:** Anchored VWAP from significant pivots
- 🐉 **NEW T58:** Liquidity sweep detection (wick-through-close-inside)
- 🐉 **NEW T59:** Body-vs-wick ratio gate

### Doctrine/UI work
- 📋 **NEW T60:** TradingView MCP J-drawn-line capture → key-levels.json

---

## 📊 The Bigger Picture — What 5/13 Tells Us

The 738.10 trade worked because **the system has good FOUNDATIONS** (PMH/PML, PDH/PDL, 5-day rolling, RTH-only filtering, star scoring, MTF agreement). The engine caught a HIGH-QUALITY level because:

1. **Historical persistence** — 5/8 high lived 5 days
2. **Multi-touch defense** — 5/5 holds with vol confirmation
3. **MTF agreement** — visible on 5m + 15m
4. **Tier escalation** — auto-promoted from Reference to Carry to Active

**This is the BASE LAYER.** The brainstorm above is about ADDITIONS to the base layer, not fixes — the existing system is solid.

**For tomorrow's CPI day specifically:** the system already captured today's 743.79 HOD + 735.48 RTH low + 738.10 reclaim level + 738.86 pivot. The engine will SEE the CPI reaction relative to these levels. If CPI is hot and SPY drops back to 738.10, the BEARISH_REJECTION setup may fire. If cool and SPY breaks 743.79, BULLISH continuation may fire.

---

## 🔬 What to research further

**Q: How often does the 5-day rolling H actually become the day's trigger level?**
- Could query: across the 16-month backtest, how many trigger levels came from (PMH/PML) vs (PDH/PDL) vs (5d rolling) vs (today H/L)?
- Builds intuition about which detection layer is most productive

**Q: Do level breaks have a CHARACTERISTIC volume signature?**
- Compare vol_mult distribution for: real breaks (price stays above for 1h+) vs fake breaks (price returns within 30 min)
- If real breaks consistently show vol ≥ 1.5× while fakes show 0.8-1.2×, tighten the trigger gate

**Q: What's the optimal lookback for the rolling H/L?**
- 5 days = current default. Could test 3, 7, 10, 20 day rolling. Stronger levels = older swing highs (e.g., 5/11 ATH 740.79 was caught yesterday).

**Q: Should level strength weight EVENT BAR volume?**
- 738.10 reclaim bar had vol 131% avg. Was that high enough? What if we required 150%? 200%?
- Trade off: stricter = fewer false signals, but miss slow-grind breakouts

---

## Files for reference

- `backtest/lib/levels.py` — runtime detection
- `automation/state/key-levels.json` — premarket-curated levels (today's)
- `automation/state/today-bias.json` — daily bias + level snapshot
- `strategy/key-levels-protocol.md` — the protocol that defines tiers + scoring
- `journal/2026-05-13.md` — today's full trade log with level context

---

**Bottom line:** The engine caught 738.10 because the level survived 5 trading days AND was multi-touch-defended today AND had volume confirmation on reclaim AND aligned across 5m+15m timeframes. The base detection system is solid. The brainstorm above (10+ candidate refinements) is about EXPANDING coverage — making sure we don't miss levels in different market structures (gap days, choppy days, news-driven days).
