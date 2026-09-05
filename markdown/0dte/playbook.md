# Playbook — Project Gamma

> Named setups with explicit context, trigger, entry, stop, and target. Every entry here is earned from real evidence, not theorized.
>
> **Numeric values (premium stop, TP1 multiplier, vol multiplier, time gates, qty tiers) are NOT canonical here — they live in [`automation/state/params.json`](../../automation/state/params.json) (Safe) and [`automation/state/aggressive/params.json`](../../automation/state/aggressive/params.json) (Bold).** When you change a value in this file, change the relevant params.json in the same edit. Drift between this file and params.json is detected at premarket Step 1a (rule-version pin check) and creates a kill-switch.

**Version:** 1.0 setup library (BEARISH_REJECTION CONFIRMED, BULLISH_RECLAIM PAPER-ELIGIBLE)
**Rule version:** v15.3 (Safe) / v15.2 (Bold) — see [`automation/state/params.json#rule_version`](../../automation/state/params.json) for canonical
**Last updated:** 2026-06-21

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

**Status:** **OBSERVATION (demoted 2026-W28)**
<!-- ratified R-0018 from analysis/weekly/2026-W28.md @ 2026-07-12T18:00:00-06:00; demoted per Section 7 tier table: n_trades=29 (>=10), hit_rate=0.2414 (<0.40 demote floor), status was CONFIRMED; cumulative avg_return_pct=+21.28% despite low hit rate (asymmetric payoff, but hit-rate floor is the mechanical gate). Was: CONFIRMED (3 of 3 examples successful) -> paper-testing phase. Revoke by deleting this comment + restoring prior status. -->

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
- **Chart stop (PRIMARY invalidation):** SPY closes a 3-min candle **above** the rejected level + $0.50 buffer (params.json#chart_stop_buffer_dollars). The chart structure failing is the real invalidation — this is the primary stop. Ribbon-flip-back (opposite-stack + spread) is the secondary structural exit. Ribbon condition removed in v11 (tested worse).
- **Chandelier profit-lock:** arms at +5% favor, trails **0.15** off the high-water mark (live registry literal `automation/state/fleet/strategies.py:143` `trail_pct=0.15`; params.json#v15_profit_lock_trail_pct 0.125 is NOT read by the ribbon_ride path -- see EXIT-SHAPE-TRUTH.md; a 2026-09-05 pass briefly wrote 0.125 here from that vestigial key, re-corrected same day) — locks gains as the move runs (v15).
- **Premium stop (catastrophe cap only):** Safe = **−50%** (entry × 0.50, params.json#premium_stop_pct); Bold = **−7% bear** (aggressive params.json#premium_stop_pct_bear). This is a backstop catastrophe cap, NOT the primary stop — chart-stop-primary doctrine (C2). **Drift check: premarket Step 1a verifies prompt + params.json match.**
- **Time stop:** Out by 15:50 ET. No 0DTE held into the close.

### Target / exit — RIDE THE RIBBON (primary management)

Locked at TP1 = **+100% premium** (live RIBBON_RIDE registry value, `automation/state/fleet/strategies.py`; params.json#tp1_premium_pct's own 0.50/0.75 keys are NOT read by the ribbon_ride path -- same vary-and-assert as EXIT-SHAPE-TRUTH/CLAUDE.md C07, doc corrected 2026-09-05 per DOCTRINE-CODE-PARITY-2026-09-05.md C21) at qty fraction 0.667 (sell 2 of 3, live registry value -- the ratified 0.8 never reached the registry, see prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json) based on `scale-out-math.md` analysis. Banks meaningful profit; doesn't clip the natural runner. **TP1 fallback to chart-level (next Active/Carry tier level past entry, $1.50 min distance, no round numbers) per v11 ratification — whichever fires first.**

**TP1 (sell 2 of 3 contracts, qty_fraction 0.667):** when **either** of these fires first —
- Premium ≥ entry premium × 1.50 (i.e., +50% gain), OR
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
- **Chart stop (PRIMARY invalidation):** SPY closes a 3-min candle **below** the reclaimed level + $0.50 buffer (params.json#chart_stop_buffer_dollars). The chart structure failing is the real invalidation — this is the primary stop. Ribbon-flip-back exit requires opposite-stack + 30c spread (params.json#ribbon_flip_back_*) — not just MIXED transition (chop = no real bias).
- **Chandelier profit-lock:** arms at +5% favor, trails **0.15** off the high-water mark (live registry literal `automation/state/fleet/strategies.py:143` `trail_pct=0.15`; params.json#v15_profit_lock_trail_pct 0.125 is NOT read by the ribbon_ride path -- see EXIT-SHAPE-TRUTH.md; a 2026-09-05 pass briefly wrote 0.125 here from that vestigial key, re-corrected same day) — locks gains as the move runs (v15).
- **Premium stop (catastrophe cap only):** Safe = **−50%** (entry × 0.50, params.json#premium_stop_pct); Bold = **−5% bull** (aggressive params.json#premium_stop_pct_bull). This is a backstop catastrophe cap, NOT the primary stop — chart-stop-primary doctrine (C2). **Drift check: premarket Step 1a verifies prompt + params.json match.**
- **Time stop:** Out by 15:50 ET. No 0DTE held into the close.

### Target / exit — RIDE THE RIBBON (primary management)

Same math as bearish version (`scale-out-math.md` analysis applies symmetrically). TP1 = **+100% premium** (live registry value, corrected 2026-09-05 -- see the bearish setup's note above) at qty fraction 0.667 (live registry; the ratified 0.8 never reached the registry).

**TP1 (sell 2 of 3 contracts, qty_fraction 0.667):** when **either** of these fires first —
- Premium ≥ entry premium × 1.50 (i.e., +50% gain), OR
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

### Setup name: VWAP_CONTINUATION (CALLS and PUTS)

**Status:** **DETECTOR LIVE, EXECUTION CURRENTLY DISARMED (2026-08-18 status note)** — `j_vwap_cont_enabled=true` in [`automation/state/params.json`](../../automation/state/params.json), `side='both'` (J's explicit call; bull-side entries remain OP-16-tracked toward 3 live wins), so the detector still fires+logs every tick. But `extra_setup_exec_armed.vwap_continuation=false` since **2026-07-25** (J-approved disarm: 7 live trades, 0% WR, -$204, one of two setups behind 2 of the week's 3 losing days) — no new order has been placed since. Full wiring + validation: [`markdown/specs/VWAP-CONTINUATION-WIRING.md`](../specs/VWAP-CONTINUATION-WIRING.md). Revert: `extra_setup_exec_armed.vwap_continuation=true`.

**Why it exists (Rule 1 mapping):** The live heartbeat's `VWAP_CONTINUATION` block can fire an entry — so it needs a named playbook pattern. This is the entry. Mined from J's 313 real Webull winners and re-validated on our 2025–26 real OPRA fills (2026-06-20): real-fills/ATM n=153, expectancy +$38.3, WR 76.5%, fires ~42% of days (near-daily), both directions positive, drop-top5 robust, DSR PASS.

**Hypothesis:** J's near-daily VWAP-aligned MORNING CONTINUATION edge. When the first 3 RTH closes are all on one side of the (as-of) session VWAP, the session has a directional bias; the first morning bar (≤ 10:30 ET) that continues in-trend — a breakout (fresh in-trend extreme) OR a pullback (shallow VWAP-ward dip then with-trend close) — is the entry.

**Context filters:**
- First 3 RTH closes all the SAME side of session VWAP (as-of, no look-ahead).
- Entry window: first qualifying morning bar ≤ 10:30 ET.
- Optional VIX put-gate (`j_vwap_cont_put_vix_gate`): puts only when as-of VIX 5-bar slope ≥ 0 (C5).

**Trigger:** the first ≤10:30-ET bar that continues in-trend (breakout = fresh in-trend session extreme, OR pullback = shallow VWAP-ward dip then a with-trend close). Entry = next bar open.

**Contract selection:** per account tier — Safe ITM/ATM, Bold ITM-2. Min 3 contracts, ~6% premium ceiling.

**Stop:** **CHART-STOP-ONLY** — the session extreme against the trade is the invalidation. Premium stop is the −50% Safe / −7% bear · −5% bull Bold catastrophe cap only (chart-stop-primary, C2). Standard v15 TP1 (+50% / 0.667), runner, chandelier profit-lock, and 15:50 ET time stop apply.

**Detector:** `backtest/lib/watchers/vwap_continuation_watcher.py` (parity-tested vs `j_daily_pattern_ratify` over 363 days). Scorecard: `analysis/recommendations/j-daily-pattern-LIVE.json`.

---

### Setup name: GAP_AND_GO (PUTS)

**Status:** **IMPLEMENTED — WATCH-ONLY, never execution-armed (corrected 2026-08-18).**

> **2026-08-18 correction, read this first.** `analysis/deep-research/RULE-ENGINE-ALIGNMENT-2026-08-18.md` claimed this setup was *"wired nowhere in code — zero hits in strategies.py, build_shared_signal.py, heartbeat_core.py, or filters.py... the playbook describes a trade the engine has never been able to take."* That claim is **FALSE** — this fix's session independently re-verified by reading the code directly (not trusting the prior audit) and found a real, working, tested implementation: the detector (`backtest/lib/watchers/gap_and_go_watcher.py`), its dispatch wiring (`setup/scripts/setup_dispatch.py`'s `DISPATCH_ROSTER`, which names GAP_AND_GO as one of setup_dispatch's own "PER-DETECTOR STATUS" entries), a dedicated exit-shape override in the live engine (`heartbeat_core.py`'s `_SETUP_EXIT_OVERRIDES["gap_and_go"]`, added 2026-07-18 with its own guard test `test_gap_and_go_exit_wiring_2026_07_18.py`), and a scorecard (`analysis/recommendations/gap-and-go-LIVE.json`). **What IS true, and is the real reason this setup has never traded:** `gap_and_go` has **never appeared as a key in `extra_setup_exec_armed`** (`automation/state/params.json`) — every tick the detector fires+logs (WATCH), but `heartbeat_core._route_extra_setups` gates real order placement on `extra_setup_exec_armed["gap_and_go"] is True`, and that key has been absent since inception. The 2026-06-28 re-validation found "0 robust cells on fresh OPRA + prior-close feed broken" and the exec-arm was never revisited even after the prior-close feed WAS fixed (`prior-rth-close.json`, V2 fix 2026-07-08). Verified this session: **0 rows** for `gap_and_go` in `journal/trades.csv` — it has never placed a single real order, paper or otherwise.

**Why it exists (Rule 1 mapping):** The live heartbeat's `GAP_AND_GO` detector evaluates and logs a signal every RTH tick (`gap_and_go_enabled=true` in [`automation/state/params.json`](../../automation/state/params.json)) — so it needs a named playbook pattern, exactly like any other named pattern here, even though it has never been armed to actually place an order.

**Hypothesis:** H2b opening-gap continuation. When SPY opens with a meaningful gap and the first RTH bar confirms the direction, the gap tends to extend rather than fill.

**Offline validation record (pre-arming — NOT a live-fills record, since it has never been armed):** chart-stop-only backtest against real OPRA option data: expectancy +$41.6, WR 72.6%, n=84, DSR PASS, WF median +1.87 all-OOS-positive, 6/6 quarters positive, both directions positive (we trade puts only per OP-16), causality 96/96 PASS. This is offline evidence from before the 2026-06-28 re-validation reversed course — it does not describe anything the engine has actually done live.

**Context filters:**
- First RTH bar gap ≥ 0.25%.
- Confirming bar: red → puts (calls require `side='both'`, J's bull-side extend per OP-16).
- Standard entry/time gates apply.

**Trigger:** first-RTH-bar gap ≥ 0.25% + a confirming red bar (for puts). Entry = next bar.

**Contract selection:** per account tier. Min 3 contracts, ~6% premium ceiling.

**Stop:** **CHART-STOP-ONLY** — the first-bar opposite extreme is the invalidation. Premium stop is the catastrophe cap only (chart-stop-primary, C2). Standard v15 TP1 (+30% per `j_gap_and_go_tp1_pct`), runner, chandelier, and 15:50 ET time stop apply — declared in `heartbeat_core._SETUP_EXIT_OVERRIDES` but never yet exercised by a real fill.

**Detector:** `backtest/lib/watchers/gap_and_go_watcher.py`, dispatched every RTH tick via `setup/scripts/setup_dispatch.py`. Scorecard: `analysis/recommendations/gap-and-go-LIVE.json`.

**To arm it live (NOT done by this fix — a params.json edit + J ratification, same as any other setup):** add `"gap_and_go": true` to `extra_setup_exec_armed` in `automation/state/params.json` after a fresh re-validation clears the 2026-06-28 "0 robust cells" finding. Whether GAP_AND_GO *should* be armed is J's call, not something this documentation fix decides.

---

### Setup name: VWAP_RECLAIM_FAILED_BREAK (PUTS live; CALLS wired, Bold not armed)

**Status:** **LIVE on core Safe-2 ONLY** — `j_vwap_reclaim_fb_enabled=true` + `extra_setup_exec_armed.vwap_reclaim_failed_break=true` in [`automation/state/params.json`](../../automation/state/params.json) (ATM cell, `side='both'`). **Bold NOT armed** (`j_vwap_reclaim_fb_enabled=false` in [`aggressive/params.json`](../../automation/state/aggressive/params.json) — the validated Bold cell is ITM-2, not ATM, per C29). **Fleet arms (safe-3/risky-1/risky-3) KILLED 2026-08-17** — see the disclosure box below. Real fills confirmed in `journal/trades.csv`.

> **2026-08-18 finding (why this entry exists at all): this setup traded LIVE on real capital with ZERO named pattern in this file**, discovered by `RULE-ENGINE-ALIGNMENT-2026-08-18.md` and closed by this fix. This is a straightforward Rule-1 documentation gap, not a code problem — the code has enforced "matches the code's own setup registry" correctly the whole time; nothing here cross-checked that registry against this file until now.

**Why it exists (Rule 1 mapping):** `heartbeat_core.py`'s G4 extra-setup dispatch can fire a real `VWAP_RECLAIM_FAILED_BREAK` entry on core Safe-2 today — so it needs a named playbook pattern, same as any other live setup.

**Hypothesis:** J_VWAP_RECLAIM_FB (edge #2) — the SUBTRACTIVE/STRUCTURAL sibling of `VWAP_CONTINUATION`. Morning trend establishes (first 3 RTH closes one side of as-of session VWAP) → price breaks VWAP **counter-trend** → the break **FAILS** and price **RECLAIMS with-trend** (≤10:30 ET) → one causal entry/day. The chart stop is the failed-break excursion extreme — the structural invalidation.

**Context filters:** first 3 RTH closes all the same side of session VWAP (as-of, no look-ahead); counter-trend VWAP break; with-trend reclaim by 10:30 ET; standard entry/time gates.

**Trigger:** the with-trend VWAP reclaim following a failed counter-trend break, ≤10:30 ET. Entry = next bar.

**Contract selection:** Safe-2 = ATM (`j_vwap_reclaim_fb_strike_offset_safe=0`). Bold's validated cell is ITM-2 but Bold is not currently armed. Min 3 contracts.

**Stop:** **CHART-STOP** — the failed-break excursion extreme (`j_vwap_reclaim_fb_stop_buffer=0.25` on Safe-2). Isolated premium catastrophe cap **-8%** (`j_vwap_reclaim_fb_premium_stop_pct`, NOT the global -50% cap — this is the setup's own validated cell, sourcing the global cap here would trade an unvalidated shape per C29/L149). Time stop 15:50 ET.

**Target / exit:** TP1 **+30%** (`j_vwap_reclaim_fb_tp1_pct=0.30`), sell 80%, fixed lock — the Safe-2 ATM cell, distinct from `ribbon_ride`'s shape.

**Detector:** `backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py` (GAMMA-SYNC: `backtest/lib/filters.py#detect_vwap_reclaim_failed_break` delegates to the same detector, no drift). Dispatched every RTH tick via `setup/scripts/setup_dispatch.py`.

**Evidence — Safe-2 ATM cell (why it's armed):** clears **all 8 anti-cherry-pick gates** on real OPRA fills (`RECLAIM-RESCUE-SCORECARD.md` rank 1: OOS +$32.33/tr n=18, full +$54.21/tr n=76, WR 55.3%, medPrem $1.395 → qty3 notional ~$419, under the ~$529 30%-of-equity cap at the time of arming). Ratified 2026-07-01 as part of the TRADE-TO-LEARN batch-2 J ratification (paper).

> **Fleet-cohort record — write what's true, not a flattering description.** A SEPARATE, pre-registered fleet-cohort experiment (`analysis/recommendations/fleet-vwap-reclaim-extension-prereg-2026-08-04.json`, frozen 2026-08-04 BEFORE arming, extending this setup to safe-3/risky-1/risky-3) hit its pre-registered "10 sessions or first checkpoint" bar on **2026-08-17** at **cohort n=3, net −$200** — below the frozen bar → **KILLED**: `build_shared_signal.RUN_VWAP_RECLAIM_FB=False` (one-line kill switch). n=3 is a thin sample; disclosed as thin, not cherry-picked away, per this project's own frozen-criteria-don't-get-relitigated rule. **Core Safe-2's lane is explicitly OUTSIDE that fleet prereg's scope** (it runs under the separate, earlier 2026-07-01 trade-to-learn ratification) and continues to trade unaffected by the fleet kill — this is a real, current asymmetry: the identical setup name is DEAD on 3 of 5 arms and LIVE on the other 2 (Safe-2 armed; Bold not armed but never disarmed either — it was simply never turned on).
>
> **Whether VWAP_RECLAIM_FAILED_BREAK should be an approved playbook pattern, given the fleet-cohort kill, is J's call — not this documentation fix's.** This entry documents what the engine actually does today (core Safe-2 continues to trade it live), not an endorsement of the pattern.

---

### Setup name: BOLLINGER_SQUEEZE (CALLS and PUTS)

**Status:** **LIVE on core Safe-2 ONLY** — `bollinger_squeeze_enabled=true` + `extra_setup_exec_armed.bollinger_squeeze=true` in `automation/state/params.json` (WIRE-BOLLINGER, 2026-07-02). Bold/aggressive not armed (Safe-only per the 2026-07-01 mandate). Real OPRA fills confirmed in `journal/trades.csv`, most recently 2026-08-11.

**Why it exists (Rule 1 mapping):** trades live on real Safe-2 capital today — a 2026-08-18 finding (RULE-ENGINE-ALIGNMENT audit), same class of gap as VWAP_RECLAIM_FAILED_BREAK above, closed by this fix.

**Hypothesis:** family-grind survivor off a Bollinger-Band squeeze/breakout family. Trigger set (from real fill notes): `BB_SQUEEZE_RECENT` + `BAND_BREAK_UP`/`BAND_BREAK_DOWN` + `VOLUME_CONFIRM`, confidence medium.

**Contract selection:** ATM, min 3 contracts. Needs ~40 session bars of BB/percentile warmup, so earliest live fire is early afternoon.

**Stop / target:** isolated exit knobs per `heartbeat_core._SETUP_EXIT_OVERRIDES["bollinger_squeeze"]` (own stop/tp1/qty-fraction/profit-lock-mode/trail keys — does not inherit the global or ribbon_ride shape).

**Detector:** `backtest/lib/watchers/bollinger_squeeze_watcher.py`, dispatched every RTH tick via `setup/scripts/setup_dispatch.py`.

---

### Setup name: DOUBLE_BOTTOM_BASE_QUIET (CALLS mirror; validated side per cell)

**Status:** **LIVE (armed) on core Safe-2 ONLY** — `db_base_quiet_enabled=true` + `extra_setup_exec_armed.double_bottom_base_quiet=true` since the 2026-07-01 trade-to-learn ratification. **No confirmed real fill found in `journal/trades.csv` as of 2026-08-18** — absence of evidence, not evidence of a wiring problem; the detector may simply not have matched a live pattern yet.

**Why it exists (Rule 1 mapping):** armed and capable of a real Safe-2 order today — a 2026-08-18 finding, closed by this fix.

**Hypothesis / cell:** best-clearing cell from `edgehunt-double_bottom_base_quiet.json` (2026-06-20): ATM, stop **-0.99** (a chart/time-stop cell, not a premium stop), TP1 **+30%**, runner **2.0×**. 4 of 20 strike/stop cells clear the full candidate-edge bar; best (strike+0/stop-0.99): N=122, WR=63.9%, OOS avg +$26.3/trade.

**Detector:** `backtest/lib/watchers/double_bottom_base_quiet_watcher.py`, dispatched every RTH tick via `setup/scripts/setup_dispatch.py`.

---

### Setup name: VIX_REGIME_DAYSIDE (CALLS and PUTS)

**Status:** **WATCH-ONLY — disarmed 2026-07-25 (J-approved).** Detector still runs+logs every tick (`j_vix_dayside_enabled=true`); `extra_setup_exec_armed.vix_regime_dayside=false` blocks any new order. Was armed on core Safe-2 from 2026-07-01 to 2026-07-25: **5 real trades, 0% WR, -$153** (real OPRA fills, `journal/trades.csv` 2026-07-20/07-21) — one of two setups (with `vwap_continuation`) behind the 0-for-12 combined result that triggered the 2026-07-25 disarm.

**Why it exists (Rule 1 mapping):** the detector fires+logs every tick and DID place 5 real orders in its armed window — a 2026-08-18 finding, closed by this fix.

**Hypothesis:** VIX-regime-conditioned dayside continuation. Trigger set (from fill notes): `VWAP_DAY_TREND_ESTABLISHED` + `VIX_REGIME_FAVORABLE_LOW_NOT_RISING`. Detector: `backtest/lib/watchers/vix_regime_dayside_watcher.py` (also exposed via `backtest/lib/filters.py#detect_vix_regime_dayside`), fed by an intraday VIX series (`heartbeat_core._fetch_vix_intraday`, G6). Isolated exit knobs: `heartbeat_core._SETUP_EXIT_OVERRIDES["vix_regime_dayside"]`.

**Revert to re-arm:** `extra_setup_exec_armed.vix_regime_dayside=true` — not done by this fix; a real re-validation would be the honest prerequisite given the 0% WR record.

---

### Setup name: LEVEL_BREAK_FIRST_STRIKE (bearish breakdown-continuation)

**Status:** **SHADOW-LOGGED ONLY — deliberately never execution-armed.** Detector runs+logs every RTH tick (`j_lbfs_enabled=true`), but `level_break_first_strike` is intentionally absent from `extra_setup_exec_armed` — `setup_dispatch.py`'s own docstring: *"DO NOT add 'level_break_first_strike' to extra_setup_exec_armed without a follow-up study clearing the walk-forward bar."* Zero real fills (consistent with never being armed).

**Why it exists (Rule 1 mapping):** fires+logs a real signal every tick via the same G4 dispatch path as the armed setups above — a 2026-08-18 finding, closed by this fix.

**Hypothesis:** bearish breakdown-continuation on MIXED-ribbon days. Detector: `backtest/lib/watchers/level_break_first_strike_watcher.py`, wired 2026-07-15 (SHADOW-LOGGED).

**Why it's not armed:** the existing N=19 VIX≥20 ATM real-fills cohort shows a positive aggregate (WR 58.8%, +$762.60) but **FAILS a chronological walk-forward split** (IS +$1,351.80 / OOS -$589.20, wf_ratio -0.44 < the 0.70 bar → `STUDY_FAILS_BAR`). A 2026-05-16..07-14 extension scan found 26 new signals, zero at VIX≥20 — no fresh ratifiable evidence. Live arming needs its own follow-up study (`analysis/recommendations/lbfs-shadow-wiring-preregistration.json` / `lbfs-shadow-wiring-revalidation-2026-07-15.json`), explicitly deferred, not this entry's call.

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

### RETIRED — `STAIRSTEP_CONTINUATION` (PUTS or CALLS)

**Status:** **RETIRED 2026-06-18 — structurally anti-J-edge.** Retired, not loosened (rule 5 above). The watcher (`backtest/lib/watchers/stairstep_continuation_watcher.py`) now always returns None; the v45 gym validator (`crypto/validators/v45_stairstep_continuation_gate.py`) asserts the non-firing. Never traded; 0 real-money.

**Why retired (eval-first, decided with data):**

1. **The motivating case was fabricated.** The original entry cited a 5/07 sequence "736.12 → 735.61 → 735.41" pressing 735.40. Those bars do **not** exist in the real 2026-05-07 SPY 5m tape (`backtest/data/spy_5m_2025-01-01_2026-06-16.csv`). The **REAL** descending highs pressing 735.40 (RTH) are **735.59 → 735.55 → 735.50 → 735.39** at 11:30-11:45 ET; price then continued to 729.75 (-$5.65). The 736.10 print is the 10:55-11:00 session-high area, not part of the staircase.

2. **The detector couldn't detect its own pattern.** The shipped `_collect_descending_retests` required each retest high to be a strict *local maximum* (`h > prev`), which a clean consecutive descending staircase can never satisfy — so on the real anchor it fired 0 times.

3. **It is anti-correlated with J's edge (the fatal flaw).** 2026-05-07 is a **J LOSS day**. A descending-stairstep short fires on exactly the chop-into-a-broken-level structure that marks J's LOSS days, and loses on his clean-trend WIN days. Measured over the OP-16 anchor set (`validate_breakout_family` STAIRSTEP stream, look-ahead-neutralized historical levels + `j_edge_tracker` J_WINNERS/J_LOSERS):

| Variant | edge_capture | anti-corr? | WIN-day P&L (4/29,5/01,5/04) | Real-fills exp (16mo) |
|---|---|---|---|---|
| As-shipped (local-max) | **−$364.80** | YES | −$345 (loses on all 3) | — |
| Corrected (collect-all, no local-max) | **−$509.57** | YES | −$412 (loses on all 3) | ATM −$27.57 / ITM2 −$42.54 |

Fixing defect #2 makes it fire **more** and become **more** anti-edge (−510 vs −365); SPY-space proxy looks positive (WR 69.2%, exp +$1.39, N=990) but **real-fills expectancy is negative** on both ATM and ITM2 — a textbook SPY-price-≠-option-edge trap (lessons C3). Both variants profit on J's loss days (5/05 +$647). **No variant clears the OP-16 anchor gate**, so per rule 5 the setup is retired rather than loosened.

**Reproduce:** `python -m crypto.validators.v45_stairstep_continuation_gate --mode both` (retirement gate). Anchor numbers via `backtest/autoresearch/validate_breakout_family.py` STAIRSTEP_CONTINUATION stream with the collectors' local-max filter removed.

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
