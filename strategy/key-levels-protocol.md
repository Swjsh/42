# Key Levels Protocol

> Born 2026-05-05 after Gamma drew "721.58 — multi-day swing low" on the chart without ever verifying it against actual chart data. The level was inherited from a stale `today-bias.json` and labeled with authority. If we'd built a hypothesis around it, we'd have been trading off a phantom.
>
> **Rule from now on: a level does not exist until it passes this protocol. Inherited values are not sources. "I think that's the swing low" is not a source. The chart is the source.**

---

## The five mandatory fields

Every level — every single one, no exceptions — must have all five of these before it gets drawn on the chart or written to `key-levels.json`:

### 1. **Source**
Must cite a **specific bar** in chart data. Format: `{timeframe} bar at {ISO timestamp} — {what about that bar made this a level}`.

✅ Valid: `"5-min bar at 2026-05-05T13:30:00-04:00 — bar low 721.49 was the session's lowest print"`
✅ Valid: `"1D bar at 2026-05-01 — daily low 720.47, swing low for the week"`
❌ Invalid: `"multi-day swing low"` (not a source — that's a description)
❌ Invalid: `"inherited from today-bias.json"` (pointer to maybe-bad data)
❌ Invalid: `"chart shows support around here"` (vibes, not a bar)

### 2. **Tier**
Must be classified as one of four tiers. Each tier has different verification requirements (see § Verification).

| Tier | What it is | Verification cadence | Example |
|---|---|---|---|
| **Active** | Established by today's session — defended, broken, or printed today | Re-verify daily during premarket | "Today's session low at 721.49" |
| **Carry** | Multi-day swing high/low, defended over multiple sessions | Re-verify every 5 trading sessions | "5/1 daily low at 720.47" |
| **Reference** | Major weekly/monthly structural level, far from current price | Re-verify monthly | "4/23 daily low at 702.28" |
| **Liquidity** | Volume-derived or institutionally-significant price (HVN, LVN, POC, AVWAP, dealer wall, dark-pool block) — not chart-structural but proven by where money trades | Re-verify daily (intraday VP) or weekly (dealer/dark-pool) | "5-day VP HVN at 723.45 — 3 sessions traded heaviest here" |

**Liquidity tier — sub-types:**
- `vp_poc` — Point of Control (highest-volume price in the visible profile)
- `vp_vah` / `vp_val` — Value Area High / Low (70% of volume bracketed)
- `vp_hvn` — High Volume Node (local volume peak away from POC)
- `vp_lvn` — Low Volume Node (volume gap — fast-traverse zone)
- `avwap` — Anchored VWAP from a named swing point
- `gamma_call_wall` — strike with the most call open interest above spot
- `gamma_put_wall` — strike with the most put open interest below spot
- `max_pain` — strike that minimizes total in-the-money option intrinsic value at today's expiry
- `dark_pool_block` — price band with significant prior-session off-exchange (TRF) volume

Liquidity-tier levels are **promoted into key-levels.json** during premarket (Steps 3b–3c) and EOD (dark-pool aggregation). They are **never** created during heartbeat — same protection as the other tiers.

**Use in setups:**
- HVN / POC / max-pain / gamma-walls = **magnet levels** — natural TP1 anchors and rejection zones
- LVN = **fast zone** — if price enters, expect rapid traversal (favours runner targets)
- AVWAP from a recent swing low = **dynamic support** — institutional algo benchmark
- Dark-pool blocks = **passive support/resistance** — institutional accumulation footprint, no direction signal

Liquidity levels do NOT replace chart-structural levels (PMH/PML, swing points). They **complement** them. When a Liquidity level coincides with a chart-structural level (within ±$0.10), the confluence is recorded explicitly in the `reasoning` field and the level is treated as higher-conviction.

### 3. **Verification**
The level must be verified **against the chart at the appropriate timeframe** before it gets drawn. Specifically:

- **Active levels** → verified on the trade timeframe (5-min default).
- **Carry levels** → verified by switching chart to 1D, reading the actual swing point, switching back to trade timeframe.
- **Reference levels** → verified by switching chart to 1D or 1W as appropriate.

The verification must include the exact bar timestamp + the OHLC value pulled from `data_get_ohlcv`. If the value isn't pulled live from the chart, the level isn't verified.

`verified_at` is a timestamp field — when the level was last cross-checked against the chart.

### 4. **Reasoning**
A one-sentence string answering: **"Why does this matter for tomorrow's hypothesis?"**

If the answer is "I don't know" or "it's a round number" → the level is `Reference` tier at best, more likely doesn't get drawn.

✅ Valid: `"10:20 AM bullish reclaim launched here — first paper-validated bullish setup observation"`
✅ Valid: `"Ribbon Slow EMA lifted above this at 3:10 PM, confirmed as dynamic support"`
❌ Invalid: `"could be important"`
❌ Invalid: `"it's a round number"` (round numbers go in `psychological` type with explicit acknowledgment)

### 5. **Type**
Classification of *what kind* of level it is. Pick exactly one:

| Type | Means |
|---|---|
| `resistance` | Capped price (recent high, rejected level, supply zone) |
| `support` | Held price (recent low, defended level, demand zone) |
| `transition` | Was one type, broken — now likely the opposite, with weaker conviction |
| `psychological` | Round number / Fibonacci / VWAP — meaningful by convention, not by chart structure |

Round numbers (720.00, 722.00, 725.00) **always** go under `psychological` — never label them as `support` or `resistance` unless the chart has *also* defended/rejected them via actual price action.

### 6. Strength score (added 2026-05-08 v3)

Every level now carries a `strength` object computed from 5 components:

```json
"strength": {
  "stars": 1 | 2 | 3,
  "points": 0-8,
  "components": {
    "touch_score": 0-2,        // touches of this level in last 30 days RTH bars
    "recency_score": 0-2,      // days since last touch (≤1 day = 2pts, ≤5d = 1pt)
    "mtf_score": 0-2,          // multi-timeframe agreement (5m only = 0, +15m = 1, +1D = 2)
    "volume_score": 0-1,       // cumulative touch-bar volume vs 20-bar avg
    "confluence_score": 0-1    // 1 if another level within $0.30
  }
}
```

**Star ratings (0-8 points → 1/2/3 stars):**
- ★★★ (5+ pts) — proven structural level, highest priority for triggers + drawing
- ★★ (3-4 pts) — meaningful, secondary priority
- ★ (0-2 pts) — fresh or thin evidence, awareness only

**Caps:**
- Round-number levels (`is_round_number: true`) capped at ★ unless confluent
- Pivot points (`is_pivot_point: true`) capped at ★★

**Touch counting rules:**
- RTH bars only (premarket noise excluded)
- $0.05 tolerance — bars within 5¢ of the level count as a touch
- Held vs broken: hold = bar tagged level then closed away (rejection); break = bar closed past level (penetration)
- Volume sums across all touch bars

The heartbeat reads `strength.stars` to prioritize levels — when filter 10 needs a "level-tied trigger," the highest-star levels within proximity are preferred.

### 7. Additional schema v3 fields

| Field | Purpose |
|---|---|
| `respect_count` | Total times level held on test (refresh-ready alternative to bounce_history.length) |
| `broken_count` | Total times level was broken cleanly |
| `touch_count` | Total touches in last-30-day RTH window |
| `last_touched_at` | ISO timestamp of most recent touch |
| `recency_days` | Days since last touch |
| `volume_at_touches` | Cumulative volume across all touch bars |
| `mtf_agreement` | 1=5m only, 2=+15m, 3=+1D |
| `confluence_center` | Average price of confluence group (if confluent) |
| `confluence_member_count` | How many levels share this confluence |
| `hypothesis_prior` | Per-level hit rate from past predictions ({hits, misses, hit_rate}) |
| `is_round_number` | Boolean — true for $5/$1-increment psychological levels |
| `is_pivot_point` | Boolean — true for floor-trader pivots; `pivot_label` says which (P/R1-3/S1-3) |

### 8. Role + bounce_history (added 2026-05-07 — captures stairstep / lower-highs patterns)

After the 2026-05-07 missed 735.40 rejection sequence (LH 736.12 → 735.61 → 735.41), levels now track multi-bar pattern memory. Two new optional fields:

**`role`** — one of `null | "broken_to_resistance" | "broken_to_support"`. Set when a level breaks definitively (5-min close past it by >$0.10). The `type` field stays as written for human readability; `role` is what the heartbeat reads to evaluate triggers.

**`broken_at`** — ISO timestamp when the role flipped.

**`bounce_history[]`** — array of retest events at the level after it broke. Each entry:
```json
{ "time_et": "HH:MM", "high_reached": <float>, "outcome": "rejected_close_lower" | "broken_back_through" | "rejected_close_below_round_number" }
```
For `broken_to_resistance`, `high_reached` is the bounce-bar's high. For `broken_to_support`, replace with `low_reached`.

**Heartbeat rule:** if `bounce_history.length >= 3 AND highs are strictly decreasing AND last_closed_bar.close < level.price` → the `sequence_rejection` trigger fires (counts toward filter 10's "≥2 of 4 triggers" requirement).

**Who maintains:**
- Premarket: when loading carry-over levels with `role != null`, preserve `bounce_history` from yesterday (rolling window of last 5 entries).
- Heartbeat: when a level retest happens (bar's high reaches within ±$0.10 of a `broken_to_resistance` level), append a row to that level's `bounce_history` array. State write only when bounce_history grows.
- EOD-summary: on level break (close past level by >$0.10), flip `role` and reset `bounce_history` to empty.

This is the schema fix for the 2026-05-07 12:30 candle miss — the system now has multi-bar memory of how a level has been behaving.

---

## When can levels be created or modified?

| Routine | Can do |
|---|---|
| **Premarket (08:30 ET)** | Create, modify, deprecate (Active, Carry, Reference, Liquidity-VP, Liquidity-dealer). Promote intraday VP HVN/LVN/POC and gamma walls/max pain into Liquidity tier from today's chart + option chain. |
| **EOD (15:55 + 16:30 ET)** | Create (Active tier — promoting today's tested chart levels; Liquidity-dark-pool — aggregating today's TRF block prints for tomorrow). Modify (annotate "tested at 14:30"). Deprecate (mark "broken cleanly"). |
| **Heartbeat (during market hours)** | **Cannot create or modify levels.** Can only mark a level as `tested` / `broken` / `defended` in `loop-state.json` for forensic record. |
| **Daily Review (16:30+)** | Suggest level changes for tomorrow's premarket — but doesn't write to `key-levels.json` directly. Premarket implements. |
| **J (manual)** | Anything, anytime, no protocol gate. Manually-drawn lines are read by premarket as `user_drawn` and respected. |

The heartbeat-can't-create-levels rule is what protects the rig from intraday noise spawning phantom levels. If the chart prints a touch at 723.85, the heartbeat doesn't draw a line at 723.85 — it logs the print to `loop-state.json#last_filter_score.note` and moves on. EOD or premarket decides if that print earned the right to become a level.

---

## Stale data handling

Every level has a `verified_at` timestamp and an `expires_at` derived from tier:

| Tier | Verification window |
|---|---|
| Active | 24 hours from verification — re-verified each premarket |
| Carry | 5 trading sessions |
| Reference | 30 trading sessions |
| Liquidity (intraday VP) | 24 hours — re-verified each premarket |
| Liquidity (dealer levels: gamma walls, max pain) | 24 hours — recomputed each premarket from today's option chain (positions roll off at expiry) |
| Liquidity (dark-pool block) | 5 trading sessions — re-verified weekly |
| Liquidity (AVWAP from anchor) | until anchor invalidated (anchor swing broken cleanly) |

**When premarket reads `key-levels.json`:**
1. For every level with `verified_at` past its window → drop into a `pending_reverification` queue.
2. For each pending level: re-check against chart at appropriate timeframe.
3. If the level is still valid (price still respected/relevant) → bump `verified_at` to today, redraw if needed.
4. If the level is no longer valid (price has blown through and consolidated past it) → move to `deprecated_entity_ids[]` and don't draw.

**Inherited levels with missing fields:** if a level in carry-over `key-levels.json` is missing any of the five mandatory fields → it's **dropped**, not propagated. Better to have fewer correct levels than more wrong ones.

---

## The drawing checklist (run before EVERY `draw_shape` call)

Before calling `mcp__tradingview__draw_shape` for a level, verify:

```
[ ] Source field is a specific bar timestamp + timeframe + what made it a level
[ ] Tier assigned (Active / Carry / Reference)
[ ] Verification done — actual chart data was pulled within the last hour for this level
[ ] Reasoning written — one sentence on why it matters tomorrow
[ ] Type assigned (resistance / support / transition / psychological)
[ ] Color matches type per workflow/daily-review.md convention
[ ] Round numbers correctly tagged as `psychological` not `support/resistance`
```

If any box is unchecked → don't draw. Stop and verify first.

This is the protocol. Skip a step → the level is invalid and drawing it pollutes tomorrow's hypothesis.

---

## Self-audit on existing levels

Any time `key-levels.json` is loaded, run a self-audit:

1. For each level, check all 5 mandatory fields are present and well-formed.
2. For each level, check `verified_at` is within tier window.
3. Print a one-line summary: `5 levels loaded, 4 valid, 1 dropped (missing source: 721.58)`.
4. Drop invalid levels rather than use them.

The audit happens automatically in premarket. If the audit drops a level that J considers important, he can manually re-add it via the chart and premarket will pick it up as `user_drawn`.

---

## Why this matters

Levels are the **first** input to every decision the rig makes:
- The bias is calibrated against levels.
- The setups trigger on levels.
- The hypothesis grades against levels.
- The Daily Review judges levels.

If a level is wrong, **everything downstream is wrong**. The 721.58 incident was a one-off because it didn't fire a setup today. Tomorrow it could be the line a put position is sized against. The fix is making the protocol unskippable, not promising to be more careful.

The cost of this protocol is ~30 seconds of verification time per level per premarket. The cost of not having it is unknowable but unbounded.
