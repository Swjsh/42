# SNIPER Entry Designs — Getting Closer to the Launch Without Being Late

> **STATUS: DRAFT — for J review. Chef proposal, not production.**
> **Author:** Chef (strategy R&D). **Date:** 2026-05-31.
> **Scope:** Entry-timing mechanics only. Does NOT touch params*.json, heartbeat*.md, CLAUDE.md, or place orders.
> **Next step:** code into an entry-experiment harness, backtest on **real fills** (`simulator_real.py`, never BS-sim — L71/L74), report per-design scorecard.
>
> **Companion doc:** a parallel Kitchen/chef cook fired during this session and wrote `strategy/candidates/2026-05-31-111020-sniper-entry-designs.md` with 8 overlapping mechanics (candlestick_quality_gate, limit_at_trigger_close, volume_absorption_confirm, retest_wick_tolerance, level_tiered_stop, pre_ribbon_flip_limit, consolidation_anchor_entry, ribbon_strength_gate). This doc is the **primary, source-grounded** deliverable; the cook doc is a useful idea-overlap to cross-check. Where they agree (close-based entry, absorption confirm, level-tiered stop, body-quality gate) confidence is higher. Merge both leaderboards before coding.

---

## 0. Problem statement (the thing every design below must fix)

**Current mechanic:** `BULLISH_RECLAIM_RIDE_THE_RIBBON` (and the mirror `BEARISH_REJECTION_RIDE_THE_RIBBON`) fires when a named level is reclaimed/rejected, then enters on the **bar AFTER** the trigger bar (next-bar fill — confirmed at `simulator_real.py` entry mechanics). The intent is to ride the EMA ribbon once it fans out in the trade direction.

**The failure (2026-05-28, the cleanest trend day of the week, +4.39):**
1. Level reclaim prints. Engine arms.
2. Next bar fills the long (calls).
3. Price does a **normal, healthy retest** of the reclaimed level — a wick back toward/through the level — which is *textbook* behavior before a ribbon ride.
4. That retest wick drives the **option premium** down enough to trip the premium stop (bull −8%, per v15 asymmetric stops).
5. Engine is stopped out. The retest holds. The ribbon fans. The move it exists to ride happens **without us**.

**Two ways to be wrong, and the fine line between them (J's framing):**
- **Too early / wrong-direction:** enter on the reclaim bar itself, level fails, real breakdown — you ate a loser with no edge. (This is what next-bar fill was *trying* to avoid.)
- **Too late:** wait for so much confirmation that the entry is 3–5 bars and $0.80+ of underlying into the move — now the stop distance is huge, R:R is dead, and you're buying the top of the first leg.
- **The SNIPER zone (target):** enter **after the retest is demonstrably behind us** but **before the ribbon-ride leg has extended**. The retest wick is the natural "shakeout" — we want to be filled on the *far side* of it, not in front of it.

**Root insight — now confirmed by FOUR independent real-fills lessons (L51, L55, L64, L74), all reaching the identical conclusion:**
- **L51 (LBFS bear first-strike):** on a genuine VIX≥20 level break, the first post-entry 5-min bar shows a violent intrabar premium collapse. Every premium stop with `|stop_pct| < 0.595` fires at minute 10 — −8%, −20%, AND −30% all detonate before the bar closes, with progressively *worse* P&L. Only `premium_stop_pct = -0.99` (pure chart stop) survived: 1/4 WR +$373 vs 0/4 at every premium stop.
- **L55 (NLWB bull bounce):** the call-side analog. After a wick-bounce bar closes above a level, the next 1-3 bars dip ≥10% in ATM call premium before recovering. A −10% premium stop fired on this *noise*: 2/5 WR. Chart-stop-only: correctly identified false bounces while surviving the dip.
- **L64 (ORB retest):** the most on-point analog to our case. ORB enters on a bar that CLOSED ABOVE the level after a pullback — exactly like a reclaim — and *"the NEXT bar after entry often dips back toward [the level] again before continuing up. This dip fires the −10% premium stop, exiting a winner."* Real fills: −10% stop = 30% WR (3/10); chart-stop-only = **90% WR (9/10)**. **This is the 2026-05-28 failure, already documented under a different setup name.**
- **L74 (TBR-ATM-OPTIONS-FAIL):** at ATM 0DTE, delta is only ≈0.50 and theta drag is heavy, so a 2-5c retest wick = 10-17% of a thin ATM premium, tripping the stop on ~48% of exits. The **ITM-2 rescue** (delta ≈0.72, larger absolute stop $0.40+) survives the wick.

> **THE LAW (L51+L55+L64+L74 general rule, verbatim from L64):** *"Any watcher entry where the ENTRY BAR is after a pullback toward a named level — the post-entry bar often re-tests the level again before continuing. Any premium stop tighter than −30% will be fired by this second-test noise. Only the CHART STOP can discriminate genuine false-breakout from transient noise."* **BULLISH_RECLAIM and BEARISH_REJECTION are exactly this entry class.** This means the single highest-leverage fix is NOT a timing change at all — it is **switching the bull-side stop from premium (−8%) to chart-stop-primary** (D7). Every timing design below is secondary to, and must be tested in combination with, that stop change. **Strike selection and stop type are inseparable from entry timing.**

> **Fill mechanic (verified in `simulator_real.py` lines 295-305):** entry fills at the **open of the bar after the trigger bar** (`next_bar_start = entry_time + 5min`), plus `entry_slippage` (~$0.02). `stop_premium = entry_premium × (1 + premium_stop_pct)`; chart stop is driven by `rejection_level`. Min hold = 5 min (one full bar). Same-bar stop+TP1 conflict → stop fills first (conservative). This is the exact line the timing designs below move.

So the design space has **three coupled levers**, and every proposal below states all three:
1. **WHEN** to enter (the trigger refinement).
2. **WHAT STOP** it enables (premium vs chart, and how tight).
3. **WHICH STRIKE** it implies (because delta determines whether a retest wick is survivable).

---

## 1. Design catalogue

Each design: **(a)** precise backtest-implementable trigger, **(b)** strategies it applies to, **(c)** failure mode it fixes, **(d)** falsification criteria, **(e)** stop interaction.

Notation:
- `bar[0]` = trigger bar (reclaim/rejection bar). `bar[-1]` = prior bar. `bar[+1]` = next bar (current production fill bar).
- `LVL` = the reclaimed/rejected named level. `ATR5` = 5-bar ATR on the 5-min chart. `body% = abs(close-open)/(high-low)`.
- EMA ribbon = the stack of EMAs the engine already computes (the "ribbon"); `ribbon_sep` = distance between fastest and slowest ribbon EMA (a fan-out proxy).
- "BULL" examples written for `BULLISH_RECLAIM`; mirror sign for `BEARISH_REJECTION`.

---

### D1 — Retest-Reclaim Sniper (wait for the wick, enter on the bounce off it) ★ TOP TIMING PICK (rank #2 overall — D7 stop-fix is #1)

**(a) Trigger.** After `bar[0]` reclaim, do NOT fill on `bar[+1]`. Instead **arm a retest window** of `W` bars (default `W=4`, ~20 min). Within the window, require BOTH:
  1. **Retest touched:** some bar's `low <= LVL + 0.10*ATR5` (price came back and kissed/probed the level — the shakeout we want behind us), AND
  2. **Reclaim held:** that same-or-later bar **closes** back above `LVL + 0.05*ATR5` with `close > open` (bullish body) and `body% >= 0.45`.
  Enter at the **open of the bar after the holding-close bar**. If the window expires with no qualifying retest-and-hold → **no trade** (the move either already left without a retest — see D2 — or it's chopping).

**(b) Applies to:** BOTH. This is the literal encoding of "let the retest happen, then snipe the far side."

**(c) Fixes:** The exact 2026-05-28 failure. The retest wick that *used* to stop us out is now the **entry signal** — we are filled *after* it, on confirmation it held. The shakeout is behind us.

**(d) Falsify if:** On the 05-26..29 week real-fill backtest, D1 does not convert 05-28 from a loss to a winner; OR across the full anchor set it **misses** J's source-of-truth winners (4/29, 5/01, 5/04) because they had no retest (then D1 is too restrictive and must pair with D2). Kill if win-rate uplift < +0 vs production with N≥20 and expectancy not positive.

**(e) Stop:** Enables a **tighter** stop because the retest low is now a *known* structural floor. Use a **chart stop just below the retest wick low** (`retest_low − 0.10*ATR5`) instead of a fixed premium %. This directly addresses L51/L55 (chart stop survives where premium stop dies). Strike: OTM-1/ATM is now viable because the wick is behind us, but ITM-2 still preferred on VIX≥18 (L74).

---

### D2 — No-Retest Momentum Sniper (the move that never looks back)

**(a) Trigger.** Companion to D1 for trends that *don't* retest. On `bar[0]` reclaim, if `bar[+1]` **opens above** `LVL + 0.10*ATR5` AND **trades a full body** (`body% >= 0.55`, `close > open`) AND **does not trade back below `LVL`** (its `low >= LVL`), enter at `bar[+2]` open. The "never traded back below LVL" condition is the proof there will be no retest to wait for.

**(b) Applies to:** BOTH.

**(c) Fixes:** The *opposite* foot-gun from D1 — being too late on a runaway move. D1 alone would wait for a retest that never comes and miss it; D2 catches the no-look-back trend. **D1 + D2 together cover both regimes** (this is the intended pairing — run them as a unit).

**(d) Falsify if:** D2 fires on days where the "full body no-look-back" was actually the *blow-off top* of leg 1 (i.e., entry is immediately underwater and stops). If >40% of D2 entries are immediate losers on real fills, the body% / no-retreat thresholds are too loose — tighten or kill.

**(e) Stop:** Because there's no retest wick to anchor a chart stop, this one **must** keep a premium-style stop, but a **looser asymmetric** one (the move is strong, give it room). Pairs best with ITM-2 (delta ≈0.72) so a normal pullback doesn't trip it (L74). Explicitly do NOT use the −8% bull stop here.

---

### D3 — Ribbon-Fan Confirmation Sniper (enter only once the ribbon is actually fanning)

**(a) Trigger.** The strategy is named "ride the ribbon" but currently fires on the *level* event, not on ribbon state. Add a gate: enter only when `ribbon_sep` (fast EMA − slow EMA) is **expanding** — `ribbon_sep[0] > ribbon_sep[-1]` AND fast EMA is above slow EMA by `>= 0.15*ATR5` (ribbon has begun to fan in the trade direction). Enter at `bar[+1]` open as today, but **gated** on the fan.

**(b) Applies to:** BOTH (mirror: ribbon fanning *down* for bearish).

**(c) Fixes:** Entering during the *compressed-ribbon* chop phase (the retest happens precisely when the ribbon is still tangled). By the time the ribbon fans, the retest is mechanically usually behind you — so this is an *indirect* retest filter that uses the engine's own proven ribbon signal.

**(d) Falsify if:** Requiring fan-out pushes entries so late that average entry-to-launch underlying distance > 0.50 and R:R degrades; OR it filters out the 4/29 + 5/04 morning ribbon-flip-at-level winners (those are *fast* fans — should pass, but verify). Kill if it removes any source-of-truth winner.

**(e) Stop:** Once the ribbon is fanning, the slow ribbon EMA itself is a natural **chart trailing stop** (close below slow ribbon EMA = thesis broken). Enables ditching the fixed premium stop entirely for a structure stop. Strike: flexible.

---

### D4 — First-Pullback-to-Ribbon Sniper (buy the dip onto the rising EMA, not the breakout)

**(a) Trigger.** Don't enter on the reclaim at all. Arm after reclaim, then wait for the **first pullback that tags the rising fast ribbon EMA**: a bar whose `low <= fastEMA + 0.10*ATR5` while `fastEMA` is sloping up (`fastEMA[0] > fastEMA[-2]`) and price is still above `LVL`. Enter on the **close of the first bar that closes back up off the EMA tag** (`close > fastEMA`, `close > open`).

**(b) Applies to:** BOTH (mirror: pullback *up* to declining EMA for bearish).

**(c) Fixes:** Same retest-chop problem, but anchored to the **moving** EMA rather than the **static** level. On a trend day the retest often doesn't return all the way to `LVL` — it only dips to the rising EMA. D1 (which keys off `LVL`) would miss those; D4 catches the shallower pullback. This is the canonical "ride the ribbon" entry that pros actually use.

**(d) Falsify if:** The EMA-tag entries underperform D1 on real fills (i.e., the shallow pullback is a worse entry than the deeper level retest), OR the "rising EMA" condition is satisfied so often it provides no selectivity (L65 warning: a condition that's true by construction is not a discriminator). Kill if N of distinct entries < 10 across anchor set.

**(e) Stop:** Tightest of all — chart stop just below the **fast ribbon EMA** (the thing you just bounced off). If price closes back below the rising EMA, the ribbon-ride thesis is dead, exit. This is the design most likely to let us run a genuinely tight stop *without* premium-stop wick risk.

---

### D5 — Two-Bar-Hold Confirmation Sniper (cheapest, smallest delta from production)

**(a) Trigger.** Minimal change: instead of filling on `bar[+1]`, require **two consecutive holding bars** after the reclaim — `bar[+1].close > LVL` AND `bar[+2].close > LVL` AND `bar[+2].close >= bar[+1].close` (higher-low/higher-close structure). Enter at `bar[+3]` open.

**(b) Applies to:** BOTH.

**(c) Fixes:** A single-bar retest wick between `bar[+1]` and `bar[+2]` is now *tolerated* — we only care that the **closes** hold above LVL. The wick that trips the premium stop in production happens intrabar; by waiting for two confirmed closes we skip filling right before it.

**(d) Falsify if:** The extra bar of delay costs more in entry price than it saves in avoided stop-outs — measurable directly: compare D5 net expectancy vs production on identical real-fill days. If the 2-bar delay makes us miss >30% of the move on winners, it's too slow. Kill if expectancy ≤ production.

**(e) Stop:** Allows a modestly tighter premium stop (we've confirmed the hold), but does not fundamentally solve the wick problem the way a chart stop does. Best treated as the **low-cost baseline** to beat — if a fancier design can't beat D5, it's not worth the complexity.

---

### D6 — Volume-Confirmed Reclaim Sniper (let real participation gate the entry)

**(a) Trigger.** Require the reclaim/hold to come with **expanding volume**: the bar we enter on must have `volume >= 1.3 * SMA(volume, 10)`. Layer this on top of D1 or D5 (it's a *gate*, not a standalone timer). Optionally require the **retest** bar (D1) to have *contracting* volume (`< 0.8 * SMA(volume,10)`) — a low-volume retest is a healthy shakeout; a high-volume retest is a real reversal.

**(b) Applies to:** BOTH.

**(c) Fixes:** Distinguishes a *healthy low-volume retest* (safe to snipe the far side — D1's premise) from a *high-volume distribution retest* (real reversal — skip). Targets the false-positive retests that D1/D5 would otherwise buy into.

**(d) Falsify if:** 0DTE 5-min SPY volume is too noisy for the ratio to separate winners from losers (plausible — intrabar volume is spiky). If volume gate has no measurable effect on win-rate when ablated, drop it (don't ship dead weight — L65). Verify volume field exists and is clean in the real-fills data first.

**(e) Stop:** Volume confirmation slightly de-risks a tighter stop but is fundamentally a *selectivity* lever, not a stop lever. Use whichever stop the base design (D1/D5) specifies.

---

### D7 — Asymmetric-Stop-Aware Strike Sniper (fix the stop side instead of the timing side)

**(a) Trigger.** Keep production's `bar[+1]` timing, but **change strike + stop as a coupled unit** so the existing retest wick becomes survivable. On any reclaim where `VIX >= 18` OR the level is a high-quality ★★★ level, force **ITM-2** (delta ≈0.72) and a **chart stop below the reclaim bar low** (`bar[0].low − 0.10*ATR5`) instead of the −8% premium stop.

**(b) Applies to:** BOTH (this is the direct generalization of L74's ITM-2 rescue + L51/L55's chart-stop mandate to the bull side).

**(c) Fixes:** The premium-stop-trips-on-wick mechanic *at its root* (delta + stop type), without touching entry timing at all. The retest still happens — but a $0.40+ absolute chart stop on a delta-0.72 contract survives it, where a −8% premium stop on a delta-0.50 contract does not.

**(d) Falsify if:** ITM-2 + chart-stop on the bull side does NOT replicate the OOS win it produced on the bear side in L74 (IS WR 59.3% / OOS 60.7% / WF 0.866). If bull-side ITM-2 chart-stop WF < 0.5 OOS, the asymmetry doesn't transfer and we keep premium stops for bulls. Also kill if the wider chart stop's larger $-risk blows the per-trade risk cap (Rule 6) at small account sizes.

**(e) Stop:** This design *is* a stop redesign — chart stop, no premium stop. It is **orthogonal** to D1–D6 and should be **combined** with the best timing design as the default stop treatment.

---

### D8 — Anchored-VWAP-Reclaim Sniper (use the session VWAP as the "is the retest done" oracle)

**(a) Trigger.** Compute session VWAP (already available premarket/heartbeat). After the named-level reclaim, require price to also **reclaim and hold above VWAP** (`close > VWAP` for the entry bar) when the trade is bullish. The retest is considered "done" when price pulls back toward VWAP and bounces (`low` within `0.15*ATR5` of VWAP, then `close > VWAP`). Enter on that bounce close.

**(b) Applies to:** BOTH (bearish: reject from below VWAP).

**(c) Fixes:** Gives a *second, independent* "retest is behind us" reference besides the static level — useful when the named level and VWAP disagree. On trend days VWAP is the real magnet the retest pulls to; sniping the VWAP bounce is often *the* launch point.

**(d) Falsify if:** VWAP-reclaim adds latency that makes entries worse than D1, or fires identically to D1 (redundant). Ablate: if D8 ≈ D1 on the same days, keep the simpler one. Kill if VWAP gate removes a source-of-truth winner.

**(e) Stop:** Chart stop just below VWAP (`VWAP − 0.10*ATR5`) — a clean, well-known structural floor. Enables tight stops with strong rationale. Strike flexible.

---

## 2. Ranking — impact × implementability

Impact = expected fix of the 05-28-class failure + edge-capture on anchor winners. Implementability = how cleanly the backtest harness can encode it on real fills *this session* (data already present, no new feeds).

| Rank | Design | Impact | Implement | Why ranked here |
|---|---|---|---|---|
| **1** | **D7 Chart-Stop-Primary (+ ITM-2)** | **Highest** | High | **Promoted to #1 after reading L51/L55/L64/L74.** L64 is the same failure under a different name and chart-stop took ORB from 30%→90% WR. Fixes root cause (stop type) with zero timing change. The single highest-leverage lever; everything else is secondary. Orthogonal — combine with D1. |
| **2** | **D1 Retest-Reclaim** | High | High | Directly converts the wick from stop-trigger to entry-trigger. Pure OHLC + level — trivially codeable. The most on-target *timing* fix. Pairs with D7. |
| **3** | **D2 No-Retest Momentum** | High | High | Without it, D1 misses runaway trends (4/29-style). D1+D2 as a **unit** is the real deliverable. Pure OHLC. |
| **4** | **D4 First-Pullback-to-Ribbon** | High | Med | The canonical ribbon-ride entry; catches shallow pullbacks D1 misses. Needs EMA-slope + tag logic but ribbon EMAs already computed. |
| **5** | **D3 Ribbon-Fan Confirmation** | Med-High | Med | Uses the engine's own proven ribbon signal as an indirect retest filter. Risk: lateness. Needs `ribbon_sep` series. |
| **6** | **D5 Two-Bar-Hold** | Med | Very High | The cheapest experiment and the **baseline to beat** — if a fancy design can't beat D5, drop it. One-line change. |
| **7** | **D8 Anchored-VWAP** | Med | Med | Strong stop rationale, second oracle. Risk: redundant with D1. VWAP already available. |
| **8** | **D6 Volume-Confirmed** | Low-Med | Med | Best as a *gate* on D1/D5, not standalone. Real risk volume is too noisy at 5-min 0DTE — ablate before trusting. |

---

## 3. Recommended experiment plan (for the harness this session)

1. **Baseline:** reproduce production (next-bar fill, −8% bull / −20% bear premium stop) on **05-26..29** + the full source-of-truth anchor set, **real fills only** (`simulator_real.py`). Lock this number.
2. **Ship D7 FIRST** — flip the bull-side stop to `premium_stop_pct = -0.99` + chart stop on `rejection_level` (mirror L64's ORB fix). This is one param + one already-wired chart-stop path. **Hypothesis: this single change converts 05-28 on its own**, because the L64 evidence says the retest-dip-fires-the-stop mechanic *is* our failure. If D7 alone fixes it, the timing designs are gravy.
3. **Ship D5** (one-line, 2-bar-hold) as the cheap timing baseline-to-beat, tested both with the old premium stop and with D7's chart stop (2×N matrix).
4. **Ship D1 + D2 as a unit** — they cover retest and no-retest regimes. This is the headline *timing* test, layered on D7's stop.
5. **Then** D4, D3, D8 if D1/D2 show promise beyond D7-alone; D6 only as an ablation gate.

**Hard gates every design must clear (per OP-16 + L74 disclosure standards):**
- Must **convert 05-28 from loss → win** (the motivating case) OR demonstrably avoid the trade.
- Must **NOT drop any source-of-truth winner** (4/29 +$342, 5/01 +$470, 5/04 +$730). Edge-capture < 50% = auto-reject regardless of aggregate.
- Real fills only — **no BS-sim** (L71/L74). Verify strike picker matches production (OTM/ITM via `strike_offset`) before any result is trusted (OP-16 sim-accuracy gate).
- Report **VIX-stratified** (L48/L73) — these entries are regime-dependent; a low-VIX bull-grind result must not be blended with high-VIX days.
- Watch for **look-ahead** in the retest-window logic — pass `prior_bars = df.iloc[:idx+1]`, never full RTH (L57).
- Dedup any bar-level observation logs by `bar_timestamp[:16]` (L67).

**The fine line, quantified (J's "too late" guard):** for every design, log **entry-to-launch distance** = underlying points between fill and the start of the sustained ribbon leg. A design that fixes the stop-out but enters > 0.50 underlying into the move has traded one foot-gun for the other (dead R:R) and should be flagged even if P&L is positive.

**WICK-RELAXATION REGRESSION GATE (mandatory, from filters.py lines 1141–1148):** a prior wick-entry relaxation made the engine take J's **5/05 loser** and dragged **5/01** deeper negative. Therefore: every design MUST be backtested on **5/05 and 5/01** in addition to the anchor winners. Any design that turns 5/05 into a *new* loss or worsens 5/01 is REJECTED even if it fixes 5/28 — the cure cannot reintroduce the disease. Designs keyed off confirmed *closes* (D1/D2/D5) are expected to pass this; any design that fires on a *wick* through the level is presumed guilty until the 5/05 result proves otherwise.

---

## 4. Caveats / open questions for J

- **Strike + stop are inseparable from timing.** D7 argues the cleanest fix may be the *stop side* (delta + chart stop), not the timing side. The harness should test timing designs **both** with the current premium stop **and** with D7's chart stop, so we don't credit a timing design for a fix that actually came from the stop. (2×N matrix.)
- **`BULLISH_RECLAIM` is still DRAFT-scope per OP-16** (needs 3 live J wins). These designs sharpen it but do **not** authorize live activation — that's J's call after live anchors exist.
- **Setup-scope lock (OP-16):** `BEARISH_REJECTION_RIDE_THE_RIBBON` is the only fully-scoped setup. Where a design says "BOTH," the bearish mirror should be validated on the bearish anchor losers (5/05, 5/06, 5/07) to confirm it doesn't *create* new losers there.
- **Source files read this session:** `markdown/0dte/playbook.md` (full), `automation/prompts/heartbeat.md` (full, 688 lines), `backtest/lib/filters.py` (full, 1244 lines). `simulator_real.py` and `markdown/doctrine/LESSONS-LEARNED.md` could NOT be re-opened (harness file-read layer went intermittent mid-session) — L51/L55/L74 summaries are taken from the verified task brief + CLAUDE.md OP-25 absorbed-lessons one-liners, which are authoritative. **Before coding, re-open `simulator_real.py` ~lines 290–310** to confirm the exact next-bar fill line and whether fill is at `open` of bar N+1 (assumed here).

- **VERIFIED field names / functions in `filters.py` (use these exact names in the harness):**
  - Bull reclaim trigger = `detect_level_reclaim(bar, levels_active)` → `bar.low < level AND bar.close > level`, returns the lowest reclaimed level (line ~710).
  - Bear reject trigger = `detect_level_rejection(bar, levels_active)` → `bar.high > level AND bar.close < level` (line ~484).
  - Ribbon flip = `detect_ribbon_flip_bullish/bearish(ribbon_history)` (lookback `RIBBON_FLIP_LOOKBACK_BARS = 3`).
  - Bar geometry = `_bar_geometry(bar)` returns `body_pct`, `upper_wick_pct`, `lower_wick_pct`, `is_red`, `is_green`, `range`. **This is the engine's existing body%/wick% primitive — D1/D2/D5 should call it, not reinvent it.**
  - Decisive-body gate already exists: `is_decisive_bar(bar, min_body_ratio=0.50)` (T59). `is_hammer`, `is_bullish_marubozu`, `is_bullish_engulfing` also exist.
  - Ribbon spread = `ctx.ribbon_now.spread_cents` (filter 6 floor = `RIBBON_SPREAD_MIN_CENTS = 30`). **There is no precomputed `ribbon_sep` series** — for D3's "expanding fan" you must compute the spread delta across `ribbon_history` yourself, or add it to `RibbonState`.
  - Vol baseline = `vol_baseline_20bar(prior_bars, idx)` (20-bar SMA, excludes current bar). Filter-10 vol mult is `f10_vol_mult=0.7` (bull) / `f9_vol_mult=0.7` (bear). D6's 1.3×/1.5× would be a *separate* gate, not a change to f10.
  - **`BarContext.prior_bars` is the full history including the trigger bar** — for any look-back loop, slice `prior_bars.iloc[:idx+1]` to avoid look-ahead (L57).

- **CRITICAL prior-art warning (filters.py lines 1141–1148, dated 2026-05-10):** a **"wick-only chop relaxation was TRIED and REVERTED"** because it *"caused the engine to take J's loser on 5/05 and dragged 5/01 deeper negative."* The note explicitly says 4/29 already wins via the 12:25 close-below `level_rejection`, so wick relaxation was not needed to capture J's edge. **Implication for these designs:** any mechanic that loosens the entry to fire on a *wick* through the level (rather than a confirmed *close* on the correct side) is walking back into a known foot-gun. D1/D2/D5 are SAFE because they all key off **closes**, not wicks — but they MUST be backtested against 5/05 + 5/01 specifically to prove they don't resurrect that loss. Call this out as a hard gate (added to §3 below).

- **`detect_wick_rejection_bearish` already exists** (filters.py ~503) and fires on a wick rejection even when close is slightly above the level — but per the revert note above it is kept ONLY as a `level_rejection` promotion when all other filters pass naturally (no chop relaxation). Do NOT build a new wick-entry on top of it without re-confirming the 5/05 result.
