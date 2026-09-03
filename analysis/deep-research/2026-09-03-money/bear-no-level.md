# H6 — Bear entries without a level

**Stamp:** 2026-09-03T10:24 ET (report finalized ~11:15 ET same session) · **Slug:** `bear-no-level`
**Verdict: REFUTED.** The proposed rule ("bear requires a named level, `range_position >= 0.25`") is not supported by the data and, applied literally, would have zeroed the single best bear day in the sample (2026-08-06, +$1,501) — one of the four protected "big winning days." Do not ship.

Builder: `backtest/tools/money_bear-no-level.py` (read-only, cached data only, no broker/network calls). Full machine-readable output: `bear-no-level.json`, plus raw per-trade dumps `bear-no-level-raw-bear-trades.json` / `bear-no-level-raw-bull-trades.json`.

---

## 1. Population and method

- **Source of truth for outcomes:** `analysis/pain-ledger/mae-mfe.json` (n=394 real, OPRA-bar-scored engine fills, `attribution==engine`). Filtered to `setup == BEARISH_REJECTION_RIDE_THE_RIBBON`, `date >= 2026-07-01` → **94 bear trades**, and the bull mirror `BULLISH_RECLAIM_RIDE_THE_RIBBON` → **195 bull trades**. This spans all six live arms (safe-2, bold-2, safe-1, safe-3, risky-1, risky-3).
- **Level/conviction/HTF context** comes from `automation/state/core-decisions.jsonl` (only safe/bold write it directly). Fleet-arm trades (safe-1/3, risky-1/3) were joined to the same ledger: `automation/state/fleet/build_shared_signal.py` confirms every fleet arm inherits `side`/`setup`/`trigger_level_exact` from whichever core account (safe or bold) produced that minute's `ENTER_*` verdict — it is one broadcast signal, not six independent computations, so joining on (date, side, setup, nearest timestamp) is valid for all arms.
- **Match quality:** 92/94 bear trades matched (median time offset ≈0.03 min, max 3.3 min); 195/195 bull trades matched. The 2 unmatched bear trades (08-12 −$81, 08-20 −$18, both small losers) are excluded and listed in the JSON; they don't move any conclusion.
- **Bootstrap:** 5,000 resamples, seed 42, 2.5/97.5 percentile CI, on trade-level `realized_pnl`.
- **No look-ahead:** every joined field (`trigger_level_exact`, `range_position`, `htf_15m`, `vix`, time-of-day) is read from the core-decisions row **at the entry tick itself** (nearest-minute match, ≤6 min tolerance), never from a later tick.

### ⚠️ Load-bearing caveat: pseudo-replication

This population is **92 bear trades spread over only 23 distinct trading days**, because up to 4 arms fire the *same* signal on the same day. Several of the groupings below are dominated by a handful of calendar days:

| Group | n trades | n **distinct days** | days |
|---|---|---|---|
| has_level | 16 | **4** | 07-17, 07-23, 07-27, 07-29 |
| no_level | 76 | 21 | (spans the whole window) |
| range_position ≤0.15 | 14 | **4** | 08-17, 08-20, 08-28, 09-01 |
| time 09:30–10:00 | 11 | **3** | 07-02, 07-08, 08-21 |
| htf_15m disagrees | 13 | **6** | 07-07, 07-21, 08-05, 08-12, 08-13, 08-28 |
| VIX<15 | 12 | **4** | 08-12, 08-13, 08-14, 08-28 |

Every trade-level statistic below should be read with this in mind: an n=14/16 "trade count" is often really an n=4-day event count with 3-4x pseudo-replication. This is disclosed, not fixed — a true day-level test wants many more independent days than this book has produced.

---

## 2. Core finding: `trigger_level_exact` is a TIME variable, not a random split

`has_level = trigger_level_exact is not None`. The hypothesis frames this as "some entries have a level, some don't." The data shows something structurally different: **every bear fill since 2026-08-05 (44 straight trades, 15 distinct days through 09-01) fired via `trendline_rejection` alone** — `trigger_level_exact` is `None` on literally 100% of them, including the ribbon-flip/trendline-only cohort the engine has used continuously for a month. This is confirmed **not** to be the "blind" incident described in `heartbeat_core.py`'s own comments (stale key-levels.json, `levels_active==[]`): spot-checking core-decisions rows for these ticks shows `blind: false` and 7–15 `levels_active` present every time — the engine is sighted, levels exist, they're just never the ones the trigger anchored to.

The `has_level=True` cohort (n=16) is entirely confined to **four days in one two-week window** (07-17 → 07-29) that predates the current trendline-only stretch. So `has_level` vs `no_level` is confounded almost one-for-one with **early-July vs. everything-since**, not a random mix of good/bad entries drawn from the same regime. Any causal read of the comparison below is unreliable for that reason — reported anyway, per instructions, with this caveat load-bearing.

## 3. `has_level` × outcome (bear)

| Group | n | days | sum PnL | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|---|
| **has_level** | 16 | 4 | −$803.0 | **−$50.19** | [−113.76, 4.69] | 25.0% | 0.28 |
| **no_level** | 76 | 21 | +$900.0 | **+$11.84** | [−32.14, 59.11] | 31.6% | 1.17 |
| baseline (all bear) | 92 | 23 | +$97.0 | +$1.05 | [−39.82, 41.24] | 30.4% | 1.02 |

Bootstrap difference (no_level − has_level), 5,000 resamples: **mean +$62.82/trade, 95% CI [−$10.51, +$145.93]**, with **95.3% of resamples favoring no_level over has_level** — the opposite sign from H6's prediction. Not fully significant at the conventional two-sided 95% threshold (the CI just touches zero), but the point estimate, the win rate, and the profit factor all point the same (wrong-for-H6) direction. Given the n=4-day confound above, the honest read is: **this dataset does not show a level-anchor edge on the bear side — if anything the sign is opposite — but it also cannot cleanly separate "no level" from "later/different regime."**

## 4. `range_position` × outcome (bear) — and why it can't test "since 07-01"

`conviction.components.range_position` is a **shadow-only** instrument (`conviction.would_block` never gates a live order — confirmed in `heartbeat_core.py`). It was also **broken from birth through 2026-08-13**: the producer read `bc.get("bars_prior")` instead of the actual key `"prior_bars"`, so `hi`/`lo` were always `None` and the component degraded on every tick ever recorded, until the fix landed 2026-08-14 (see the in-code incident note at `_score_conviction_shadow`). Coverage confirms this precisely:

| Month | bear trades with range_position | bear trades total |
|---|---|---|
| 2026-07 | 0 | 48 |
| 2026-08 | 17 | 41 |
| 2026-09 | 3 | 3 |

So **78% of the requested "since 2026-07-01" bear population (74/94) has no `range_position` at all** — the instrument simply didn't exist for most of the window the hypothesis names. What data does exist:

| range_position bucket | n | days | sum PnL | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|---|
| extreme_low (0.00–0.15) — "shorting the low" | 14 | 4 | **+$425.0** | **+$30.36** | [−71.0, 131.4] | **50.0%** | 1.43 |
| low (0.15–0.35) | 4 | 3 | −$258.0 | −$64.5 | [−182.0, 99.5] | 25.0% | 0.43 |
| mid (0.35–0.65) | 2 | 1 | +$162.0 | +$81.0 | [80.0, 82.0] | 100% | ∞ |
| missing (pre-instrument) | 72 | 21 | −$232.0 | −$3.22 | [−48.1, 45.7] | 25.0% | 0.95 |

**The `extreme_low` bucket — exactly the zone H6 flags as bad ("shorting the low of the day") — is net positive** in the only 4 days it can be measured. Two of those 4 days are the specific ones the hypothesis names: 08-28 (4 losers, −$705, all rp≈0.08) and 09-01 (rp 0.121/0.005/0.002 — 1 winner +$338, 2 losers −$260, net +$78 that day). H6's specific claim replicates directionally on those two days individually (both are net negative or mixed) but is overwhelmed in the 4-day aggregate by 08-17 (+$360) and 08-20 (+$692 across 7 trades, a strong trend day). **This bucket does not support H6 as a general bear rule; it supports it only on the two named days, at n=7 trades total.**

## 5. Time of day (bear)

| Bucket | n | days | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|
| **09:30–10:00 (open)** | 11 | 3 | **−$89.36** | **[−118.82, −65.55]** | **0.0%** | 0.00 |
| 10:00–11:30 | 12 | — | +$108.08 | [−33.52, 274.85] | 50.0% | 4.20 |
| 11:30–13:30 (midday) | 40 | — | −$20.62 | [−86.40, 47.85] | 27.5% | 0.78 |
| 13:30–15:00 (afternoon) | 29 | — | +$20.97 | [−28.24, 72.14] | 37.9% | 1.48 |

The 09:30–10:00 bucket is the single tightest, most one-sided CI in this entire study — **11/11 trades lost money**, CI entirely below zero. It is also the smallest and most day-clustered (3 days: 07-02, 07-08, 08-21). This is a real candidate finding but is **out of scope for H6** (H6 asked about levels, not entry timing) and is not costed further here — flagged for a separate pre-registered hypothesis, not shipped.

## 6. HTF 15m stack agreement (bear)

| Bucket | n | days | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|
| agrees (htf_15m == BEAR) | 54 | — | +$3.81 | [−37.87, 47.84] | 35.2% | 1.06 |
| **disagrees (htf_15m == BULL)** | 13 | 6 | **−$116.54** | [−235.47, 2.16] | **7.7%** | 0.19 |
| neutral (MIXED) | 25 | — | +$56.24 | [−22.60, 151.52] | 32.0% | 2.29 |

Shorting against a BULL 15m HTF stack has a 7.7% win rate over 13 trades / 6 days — CI barely touches zero. Directionally strong, out of scope for H6, flagged for future work.

## 7. VIX regime (bear)

| Regime | n | days | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|
| VIX<15 | 12 | **4** (08-12,13,14,28) | **−$106.42** | **[−155.75, −59.50]** | **8.3%** | 0.01 |
| VIX 15–17 | 51 | — | +$45.33 | [−18.90, 109.04] | 39.2% | 1.73 |
| VIX>17 | 29 | — | −$32.34 | [−81.52, 15.55] | 24.1% | 0.51 |

Note this VIX<15 bucket is the **same 4 days** as the VIX-regime driver behind the H6-named 08-14/08-28 losses — i.e. it's largely the same signal as "recent quiet-VIX bear entries were bad," restated. Not independent evidence.

## 8. Bull mirror (`BULLISH_RECLAIM_RIDE_THE_RIBBON`) — opposite pattern, and it's the well-powered one

| Group | n | sum PnL | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|---|
| **has_level** | 146 | +$4,113.0 | **+$28.17** | [−9.22, 66.46] | 35.6% | 1.40 |
| **no_level** | 49 | −$853.0 | **−$17.41** | **[−22.02, −13.31]** | **2.0%** | 0.01 |

| range_position bucket | n | mean PnL | 95% CI | WR | PF |
|---|---|---|---|---|---|
| mid (0.35–0.65, good reclaim location) | 31 | **+$124.16** | **[45.48, 207.00]** | **58.1%** | 4.71 |
| high (0.65–0.85, bad — near range top for a call) | 13 | **−$50.77** | **[−79.77, −20.92]** | **15.4%** | 0.13 |
| extreme_high (0.85–1.00) | 18 | +$0.50 | [−50.56, 57.28] | 27.8% | 1.01 |

This is the clean, statistically decisive result in this study: on the **bull** side, both "has a named level" and "reclaimed from the middle of the range rather than the top" are strongly, significantly predictive (CIs that don't cross zero, n in the dozens not single digits). This matches existing doctrine (`CLAUDE.md`'s "every dollar the engine has ever made is level-tied" narrative, C1/C4/C25 lessons) and is **not a new finding** — it's a reconfirmation. The asymmetry with bear is the interesting part: **the location/level-quality mechanism that clearly works for bull reclaims does not show up in the bear data over this window**, whether because bear moves (breakdowns) are structurally faster/less orderly around named levels, or — more likely given §2 — because the bear "has_level" sample is too small and too time-confounded to detect it even if it's real.

---

## 9. Costing the proposed rule

**Proposed rule (as given):** bear entry requires (a) a named level within the zone width (`trigger_level_exact is not None`, using the engine's own $0.25 `LEVEL_MATCH_TOL`) AND (b) `range_position >= 0.25`.

| Variant | Allowed n | Allowed mean PnL | Blocked n | Blocked mean PnL | Δ mean PnL vs. baseline |
|---|---|---|---|---|---|
| A: level only | 16 | −$50.19 | 76 | +$11.84 | **−$51.24/trade** |
| B: level AND range≥0.25 | 16 | −$50.19 | 76 | +$11.84 | **−$51.24/trade** (identical to A) |

**Variant B is untestable as a combined condition with this data** — every `has_level` trade predates the `range_position` instrument (§4), so the range gate never actually binds on top of the level gate; A and B are numerically identical by construction, not because the range gate is irrelevant.

Both variants: shipping this rule keeps only 16 of 92 trades (17%), and the **kept population is the worse-performing one** (mean −$50.19 vs. the +$1.05 baseline it's carved from) while the **discarded 76 trades were the profitable side of the book** (+$900 total). This is the opposite of what a filter is supposed to do.

### Named-day check (does it kill winners?)

| Day | Bear trades | Bear PnL | Would rule block them? | Verdict |
|---|---|---|---|---|
| **2026-08-06** (protected big winner) | 3 (all safe-2/risky-1/risky-3, same strike) | **+$1,501.0** | **YES — blocks all 3** | **FAILS the protected-day check** |
| 2026-08-13 (protected big winner) | 2 | −$269.0 | Yes (both losers) | day's win came from bull, unaffected |
| 2026-08-27 (protected big winner) | 0 | $0 | n/a | no bear trades that day |
| 2026-08-28 (protected big winner) | 4 | −$705.0 | Yes (all losers) | day's win came from bull, unaffected |
| 2026-08-07 (H6-named bear day) | 0 | $0 | n/a | that day's −$2,687 was 100% bull |
| 2026-08-14 (H6-named bear day) | 3 | −$268.0 | Yes (all losers) | rule would have avoided this loss |

**Decisive: the rule blocks all 3 trades on 2026-08-06, the single largest bear win in the entire dataset and one of the four days this task explicitly protects.** That alone disqualifies shipping it as written, independent of the aggregate stats above. On the other 5 named days it would only have removed losers (net effect across all 6 named days: forgoes +$1,501, avoids −$1,242 → net **−$259** worse), which is a mild reinforcement of the aggregate finding, not a save.

---

## 10. Verdict and disposition

- **H6 as stated: REFUTED.** The `trigger_level_exact=None` fact is real and now describes essentially the entire recent bear book (100% since 08-05), not a distinguishing bad subgroup. In the trades where a comparison is even possible, the level-anchored cohort performed *worse*, not better, though that comparison is confounded with an earlier, generally-worse two-week stretch (07-17→07-29) and rests on only 4 distinct days.
- **The specific `range_position <= 0.12` "shorting the low is bad" claim does not replicate** in the only 4 days (n=14 trades) where it's measurable — that bucket is net +$425, WR 50%. It replicates only on the two literal days named in the hypothesis (08-28, 09-01) at n=7.
- **`change_class = KILL_TYPE_REDUCTION` was tested and produces a `proposed_change = NONE`** — no live rule change is recommended from this investigation.
- **The instrument doing real work here is the bull-side level/range_position signal** (§8), which is statistically solid but not new — it reconfirms existing "levels are the edge" doctrine rather than proposing a change.
- **Two out-of-scope leads worth their own pre-registered hypothesis, NOT shipped from this report:** (a) bear entries in the 09:30–10:00 ET open window have lost on 11/11 trades (3 days, CI entirely negative); (b) bear entries against a BULL 15m HTF stack have a 7.7% WR (13 trades, 6 days). Both are smaller-n, day-clustered, and untested against the big-winning-day set — they need their own A/B before any action, per this project's eval-first gate (OP-11/16).

## Data sources
- `analysis/pain-ledger/mae-mfe.json` (n=394 real fills, builder `setup/scripts/pain_ledger.py`)
- `automation/state/core-decisions.jsonl` (37,517 rows, read-only)
- `automation/state/fleet/build_shared_signal.py` (read for signal-provenance confirmation only)
- `setup/scripts/conviction.py`, `setup/scripts/heartbeat_core.py` (read for range_position/trigger_level_exact semantics and the 2026-08-14 bug-fix date)
- Builder script: `backtest/tools/money_bear-no-level.py`
- Full JSON: `analysis/deep-research/2026-09-03-money/bear-no-level.json`, raw trade dumps alongside it.

**UNVERIFIED / not done:** no live broker or market-data calls were made (per hard constraint); all figures are from cached ledgers already on disk as of this session. Day-level (rather than trade-level) bootstrap was not additionally computed beyond the distinct-day disclosure in §1 — flagged as a natural next step if this hypothesis is revisited with more data (the book needs many more bear trading days before `has_level` and time-of-day/HTF/VIX splits stop being dominated by single-digit-day counts).
