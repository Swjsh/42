# Mistakes — Project Gamma

> Read this every Monday morning before market open.
>
> A "mistake" here means a **rule break** or a **process failure**, not a losing trade. A losing trade that followed every rule is correct execution. A winning trade that broke a rule is still a mistake — and the kind that breeds future ruin if not flagged.

---

## Format

```markdown
## YYYY-MM-DD — <one-line summary>
**Rule broken:** <which rule, exact citation>
**What I did:** <factual>
**Why I did it:** <emotional / situational driver>
**Outcome:** $X / R / "got lucky"
**Pattern? Have I done this before?:** <reference past entries>
**Fix:** <process change to prevent recurrence>
```

---

## Entries

## 2026-06-15 — Bold Rule 6 sizing violation (5 contracts vs 2 allowed at $1,122 equity)

**Rule broken:** Rule 6 — per-trade risk cap 50% of Bold equity
**What happened:** Engine entered 5 × $2.06 = $1,030 cost = 91.8% of $1,122. Bold cap is 50% = $561 max = floor($561/$206) = **2 contracts**. Entered 3 excess contracts.
**Why it happened:** Code gate FIX-5a was not yet active at time of entry — the contract count was not enforced at the order-placement step. Engine used available-equity sizing logic without capping at the 50% rule.
**Outcome:** +$552 (got lucky — violation worked in our favor this time). Per-contract P&L was exceptional (+$110.40/contract vs J-anchor benchmarks of $23–$73/contract).
**Pattern?** First Rule 6 breach on Bold account. 6/2 ghost entry (mistakes.md) was Rule 4. Sizing discipline has not been tested under adverse conditions — the danger is a 91.8%-exposure entry on a losing day would trigger the kill switch on a single bad trade.
**Fix:** FIX-5a code gate now active (committed 2026-06-15). Add a unit test asserting `position_cost <= 0.50 × account_equity` before any Bold ENTER_BULL/BEAR tick fires. Verify gate is running before next trading day open.

---

## 2026-06-02 — Bold double-entry → orphaned GHOST position (state drift)

**Rule broken:** Rule 4 (one position at a time / no second entry without closing the first) + Rule 8 (process — engine lost track of a live position).
**What happened:** Bold entered SPY 758C ×3 @1.87 (10:56 ET), then entered SPY 760C ×4 @0.98 (11:25 ET) while the 758C was STILL open in Alpaca. The single-position `current-position-bold.json` overwrote the 758C record with the 760C, orphaning the 758C — engine went blind to it (no TP/stop). Caught manually at 11:47 (758C was +$84). Both closed ~12:16 ET: 758C +$33 (decayed from +$84 because unmanaged), 760C −$156.
**Why it happened:** the Entry branch fires on `current-position.status == null` (LOCAL state) without verifying flat against Alpaca. State read null after a desync/failed-close while Alpaca still held the 758C → engine entered again.
**Outcome:** −$123 Bold (−9.9%); the 760C −$156 dominated; the ghost cost ~$51 of unrealized gain it couldn't manage. Bold also burned all 3 day-trades (PDT maxed).
**Pattern? Have I done this before?:** YES — same family as 2026-05-21 STATE_DRIFT and 2026-05-19 ghost ENTER. State-vs-Alpaca desync is recurring.
**Fix:** Added a FLAT-VERIFICATION gate to BOTH heartbeats' Entry branch (2026-06-02): call `get_all_positions` before entering; if non-empty → reconcile state from Alpaca + emit `STATE_DRIFT_BLOCKED_ENTRY` + do NOT enter. Also: today's bull-reclaim-in-chop bleed is exactly the case for ratifying the selectivity stack (#21/#22/#3).

---

## 2026-05-21 — False-break-launchpad at ★★★ Carry 738.10 on RTH open bar

**Rule broken:** Rule 2 — "Wait for the trigger." Bear entry placed on a false break of a ★★★ Carry level at the 09:35 open bar. The bar recovered above the level by 09:40; premarket framework had no branch for single-bar recovery at a maximum-hold level.
**What happened:** 09:35 bar printed low 737.53 (−$0.57 below ★★★ Carry 738.10, 9 touches 7 holds). Bear entry taken. By 09:40 bar SPY had recovered above 738.10, creating a trapped-short squeeze. Session closed +$4 in bull direction.
**Outcome:** −$204.
**Fix:** Add FALSE_BREAK_LAUNCHPAD check to premarket: if open bar low > $0.25 below ★★★ level AND close above level → suspend bear entries for 30 min, log FALSE_BREAK_DETECTED, watch for bull ribbon trigger. See L75 in markdown/doctrine/LESSONS-LEARNED.md for the full encoding.

- See [L75 in markdown/doctrine/LESSONS-LEARNED.md](../markdown/doctrine/LESSONS-LEARNED.md#L75) for the full encoding.

---

## 2026-05-19 — Ghost ENTER_BEAR (infrastructure process failure)

**Rule broken:** Rule 8 (process) — "Journal every trade in real time." The decisions.jsonl recorded ENTER_BEAR at 10:03 ET with no corresponding Alpaca order. The journal implied an entry that never happened.
**What happened:** `Gamma_Heartbeat` tick HB#11 at 10:03 ET generated ENTER_BEAR reasoning text (bear=8/10, BEARISH_REJECTION_RIDE_THE_RIBBON @735.40) but the `mcp__alpaca__place_option_order` tool call was never executed. Zero orders in Alpaca for either account.
**Why it happened:** The `/loop` interactive engineering session was running during market hours (09:30-15:55 ET), sharing the Claude Code API rate-limit pool with the heartbeat scheduled task. The `claude --print` invocation for HB#11 was throttled mid-generation. The ENTER_BEAR intent text was written before the rate limit hit; the Alpaca tool call came after and was cut off.
**Outcome:** $0 P&L (no order placed — lucky). The 1h43min subsequent blackout (10:57-12:40 ET) meant the engine missed two potential J-quality bull entries at 12:20 and 12:35 ET. Estimated missed opportunity: $100-$350 on conservative bull setups.
**Pattern:** New pattern — rate-limit starvation. Not a repeat of prior mistakes.
**Fix:** HARD RULE from L54: never run interactive Claude sessions (/loop, manual research, engineering cycles) during 09:30-15:55 ET market hours. The only Claude API consumers during live trading should be Gamma_Heartbeat, Gamma_Heartbeat_Aggressive, and Gamma_WatcherLive. Permanent fix: separate Claude accounts for production vs engineering.

## 2026-05-18 — auto-flags

- **RULE_3_INFRA_NAKED_PARENT** (low) — 09:48 ET Bold heartbeat timeout mid-bracket-placement: parent BUY limit (739C × 5 @ $1.74) submitted to Alpaca without stop leg due to wrapper kill before stop placement. Order canceled by J at 09:54:37 before fill — Rule 3 near-miss, not an actual breach. Trade row: N/A. Fix: add atomic bracket guard (cancel parent immediately if stop leg placement fails on timeout).

### 2026-05-11 — Untracked 738C trade + EOD-flatten partial fill → 200-share assignment

**Rule broken:** Three rules, in order of severity.
1. **Rule 8** — "Journal every trade in real time. Pre-trade thesis before order. Fill and exit recorded after." The 5/11 738C 0DTE trade (qty=15 @ $2.01 entry, 10:25:58 ET) was placed via Alpaca `access_key` source but **never logged to the journal trade table.** The 5/11 journal stops mid-tape at 12:40 ET and was never closed out.
2. **Rule 3** — "Defined stop on entry. Premium stop or chart stop. Mechanical." Order trail shows ONLY a TP1 limit at $3.09. **No stop-loss order was placed.** TP at +54%, no stop.
3. **"All flat by EOD"** — EOD-flatten task (`Gamma_EodFlatten`) ran at 15:45 ET and market-sold but only 13 of 15 contracts filled. The remaining **2 contracts went to expiry ITM and were assigned → 200 shares of SPY @ $738 = $147,600 cost basis added to the account.**

**What happened:** J's Claude usage cap exceeded on 5/11 → live monitoring stopped → trade was placed (manually or via stale automation, source=`access_key` not `alpaca::auto`) but never journaled. EOD-flatten attempted to close all 15 but partial-filled 13. Two contracts settled into stock assignment Tuesday morning. Position carried for two days unnoticed.

**Why it happened (each layer):**
1. Live session went silent at ~12:40 ET on 5/11 (token cap or session disconnect). Journal write stopped.
2. EOD-flatten code does single-shot market sell. If partial-fills on illiquid 0DTE near close, leftover quantity is NOT retried.
3. Position-state file (`current-position.json`) was never updated when the 738C was opened — it still showed the 734C exit from 5/07.
4. No alert fired when EOD-flatten partial-filled. No alert fired when assignment posted Tuesday morning.

**Outcome:** ~−$2,273 net P&L on the trade leg. 200-share SPY long carried for 2 days unnoticed. Sell orders queued 2026-05-12 23:30 ET for 5/13 09:30 open. Equity now ~$98,825 (was $101,098 pre-trade).

**Pattern:** Same shape as 2026-05-05 ("Gamma saw the setup forming, then went passive") and 2026-05-07 ("disabled rig mid-session"). All three failure modes share the same root: **monitoring stops the moment the live session drops, but the trade leg does not.**

**Fix (4 changes):**
1. **EOD-flatten retry-until-zero.** The task must loop until `qty_available == 0` for every option position OR escalate to Discord ping after 3 failed attempts. Single-shot market sell is insufficient near close.
2. **Position-state writer hook on EVERY fill.** Any Alpaca fill (regardless of `source=`) must write to `current-position.json`. Currently only the heartbeat writer updates it.
3. **Daily reconciliation gate.** Premarket Step 1 must compare Alpaca's `get_all_positions` against `current-position.json` and HALT (kill-switch) on any mismatch — exactly what triggered correctly on 5/11 10:30 ET for the aggressive account, but for the SAFE account this check did not exist.
4. **Stop-on-entry enforcement.** Any TP-only order placed without a paired stop must be flagged. Add a watcher to detect bracket-incomplete orders.

---

### 2026-05-01 — Anticipation entry (entered before the trigger fired)
*(Logged retroactively on 2026-05-04 during project kickoff. The trade pre-dates the rules; we log it because the **pattern** is what matters going forward.)*

**Rule broken:** "Wait for the trigger" (CLAUDE.md hard rule #2). I had the bearish bias right but entered at 13:09 *before* SPY had tested the descending trendline — the trigger for the setup hadn't fired yet.

**What I did:** Bought 10 SPY 721 puts at $0.46 at 13:09 EDT, anticipating the trendline rejection. SPY rallied up to test the trendline (against me); premium dropped to $0.19. At 13:36 SPY tested and was rejected by the trendline — *this* was the actual trigger, and I added 10 more at $0.19. Exited 20 contracts at $0.56 at 14:47 for +$470 / +72%.

**Why I did it:** Bias felt strong, conviction was high, didn't want to "miss" the move. Conflated "I see a setup forming" with "the setup has fired."

**Outcome:** +$470. **The trade making money is not the lesson.** The math: if I'd waited and only taken the 13:36 trigger entry at $0.19, profit would have been +$370 on $190 risk = **+194%** instead of +72%, with **less than a third of the capital deployed and a cleaner stop.** Anticipation cost return *and* added risk.

**Pattern:** First entry on this strategy. Watching specifically for: (a) any future urge to enter on bias before the trigger fires, (b) any 0DTE entry without an explicit stop level pre-defined, (c) deploying capital before the math has been run.

**Fix:**
1. **Trigger-first rule.** No entry until the actual setup-defined event has happened (e.g., trendline test + rejection candle, level break + retest). Bias is not enough.
2. **State the trigger out loud before entry.** Gamma will refuse to log a pre-trade thesis that doesn't include the specific event that just occurred.
3. **Defined stop, mandatory.** Premium or chart-based, before any order is placed.

---

---

### 2026-05-05 — Gamma saw the setup forming, confirmed it out loud, then went passive

**Rule broken:** Gamma's job is to be ready to act, not to wait for J to re-ping. Once I said "setup is ripe, ribbon at maximum compression, price at the knife's edge" — that was the moment to start a loop, watch every candle, and call the shot when it fired.

**What happened:** J described the setup (723 rejection, EMA compression). I read the chart, confirmed every element was in place, said "do not anticipate, watch for the close." The trigger fired ~10 minutes later — price broke below Fast EMA (723.44) and Pivot EMA (723.35). I was not watching. J caught it manually on Weebull (SPY 722P, entered personally, up ~7% when flagged). Alpaca paper account got nothing.

**Why it happened:** No loop was running. I responded to J's message, gave the analysis, and went idle. The system has no autonomous watching between J's messages.

**Outcome:** Missed paper trade. Real-money trade caught by J manually. The setup was clean — BEARISH_REJECTION_RIDE_THE_RIBBON, all context filters present, 2/3 triggers fired (level rejection at ~723.50 + ribbon break).

**Pattern:** This is the exact problem the heartbeat architecture was designed to solve. Without a loop running, Gamma is reactive only.

**Fix:**
1. **The loop must start the moment a setup is "forming."** When I say "ribbon is at max compression, price at the knife's edge" — that sentence is the trigger to start watching on a 3-min cycle, not to wait for J.
2. **Paper trade automation must be live.** Alpaca paper MCP is loaded. Once J confirms paper-trading authorization in CLAUDE.md, every confirmed trigger gets a paper order placed immediately — no J involvement required.
3. **Build the Task Scheduler heartbeat this week.** Today is proof the manual session model breaks the moment J isn't staring at the chat.

---

### Notes for the future-me reading this on a Monday
The 5/1 trade made money. The next one with the same anticipation-entry pattern won't necessarily. The reason this rule exists is to fire when conviction is highest — that is exactly when bias-without-trigger feels most justified, and exactly when it isn't.

---

### 2026-05-07 — Missed the textbook 735.40 rejection (system + Gamma chain failure)

**Rule broken:** Multiple. Filter set was too strict on a textbook setup AND Gamma was disabling/rebuilding the rig instead of watching the chart while the trigger fired.

**What happened:** SPY tested 735.40 (today's drawn resistance). 11:35 bar broke above (high 736.11). 11:40 bar wicked $0.72 above to 736.12 then closed back inside (rejection candle). 11:50 first close back below 735.40 ($0.03 below). 12:00 confirmation close at 735.10 with 53K vol. 12:35-12:45 break-and-run to 733.03 (-$2.37 in 45 min from rejection level). Volume on the breakdown bars: 50K, 76K, 58K — heavy.

A 735P entered at 11:55 close (avg $0.85 mid) would have been worth $2.00+ by 12:45 (+135%). Expected playbook P&L on 3 contracts (2 TP at +30%, 1 runner toward 730): +$255-450.

**Why we missed it (every layer of the failure chain):**
1. **Filter 9 too strict.** breakdown_bar_bearish requires `close < open AND close < Fast EMA AND body in lower 40% of range AND vol ≥ 1.3×`. The 11:50 and 12:00 trigger bars closed below the level but body shape didn't satisfy "lower 40%" — they were tight bars near the low but with longer wicks. Filter 9 blocked.
2. **Filter 10 too strict.** Required `htf_15m_stack != BULL`. The 15-min ribbon was still BULL (it lags the 5-min by design). Even with all other conditions firing, filter 10 alone would have blocked.
3. **Heartbeat task was disabled** at 11:35 ET — exactly when the trigger window opened. Gamma was running structural cleanup of prompts/budgets after the morning's audit work.
4. **Sonnet escalation flooded** before the disable. Between 10:51 (HB#3 set next_tick_model=sonnet) and 11:35, Task Scheduler fired 12 Sonnet ticks every 3 min. ALL of them timed out at 150s because the prompt was too heavy for the budget. Burned ~$6 of subscription quota on heartbeats that produced zero output.
5. **No alert path.** Even when 12:04 manual tick correctly identified the near-miss (bear 8/10), nothing alerted J. Just a CSV row.
6. **Backtest from this morning already flagged this.** R-BT-01 finding: filter 9 (`close < Fast EMA`) and the body-shape requirement would have vetoed home-run setups historically. We had the data. We didn't act on it.

**Outcome:** Real-money cost = $0 (no live trade). Paper cost = ~$255-450 in expected setup P&L. Process cost = J had to watch the chart manually because the rig was offline.

**Pattern:** This is identical in shape to 2026-05-05 ("Gamma saw the setup forming, then went passive") — but with a new flavor. Then it was "no loop running." Today it's "loop disabled while doing infra work mid-session." The lesson is the same: **when J is in the chat and price is moving, Gamma should NOT be doing prompt engineering.**

**Fix:**
1. **Relax filter 9** — drop the "body in lower 40%" sub-clause. Keep `close < open AND close < Fast EMA AND vol ≥ 1.3× 20-bar avg`. The body shape requirement was eliminating clean rejection bars (which often have wicks).
2. **Soften filter 10's HTF requirement** — make it a score modifier (`-1 to score if HTF disagrees`), not a hard block. Score ≥ 8/10 or ≥ 9/11 still passes if HTF disagrees but other conditions are clean.
3. **Never do prompt cleanup during market hours.** Cleanup work is for AFTER 16:00 ET. During market hours, only configuration changes that don't disable the rig.
4. **Add a "near-miss alert"** — when bear ≥ 8 or bull ≥ 9 with a known-too-strict filter blocking, dashboard-dialogue.json#claude_status writes "ALERT" + claude_reasoning describes what would have fired. J can override manually if he sees it.

---

### 2026-05-07 — Counter-trend BULL entry into pre-FOMC bear sequence (-$45)

**Rule broken:** No explicit rule was broken — the system fired correctly per its codified rules. But the rules themselves missed the multi-bar bearish pattern J was reading on the chart. **Pattern: counter-trend chop trap.**

**What happened:** At 12:30 ET the heartbeat fired ENTER_BULL on a 734C 0DTE call. Entry premium $0.73, qty 3, total $219 deployed. The system saw:
- Ribbon BULL-stacked (104¢ spread)
- HTF BULL
- VIX 17.33 falling (cleared filter 8 via `OR` path: VIX<17.20 OR vix_falling)
- Bull score 10/11
- A green bounce bar off 733.55 support with 63K vol

12 minutes later (12:42) ribbon flipped BEAR and the bracket stop fired at $0.58. Loss capped at -20.5% (-$45). Stop logic worked.

**Why the system was on the WRONG SIDE:** J was reading a 90-min multi-bar pattern that the system can't see:
- 11:35 break above 735.40 (high 736.11) = first false breakout
- 11:40 rejection wick at 736.12 (close 735.84) = lower high #1
- 12:00 first close back below 735.40 (close 735.10) = level confirmed broken
- 12:15 retest bounce capped at 735.61 = lower high #2
- **12:30 third retest capped at 735.41** (the literal level being tested from BELOW, role-reversed) = lower high #3
- 12:30 close 734.84 (closed below 735 round number) = stairstep continuation confirmed

The system saw "5m ribbon BULL + bounce off 733.55 + HTF BULL + bull 10/11" → went long. But the bigger picture was:
- THREE consecutive lower highs at the broken-resistance level
- Each bounce a smaller bull attempt = classic distribution
- Pre-FOMC macro context (de-risk) trumping all 5m bull signals

**Pattern recognition gaps in the rules:**
1. **No lower-highs counter.** Three rejections in a row at a level is overwhelming bear evidence. Rules don't track sequence.
2. **No role-reversal awareness.** When 735.40 broke at 11:35, nothing in `key-levels.json` flagged "this is now resistance until reclaimed." Each retest treated as fresh.
3. **No stairstep / break-and-extend detection.** Each support break (735.40 → 733.55 → 733 → 732 → 731 → 730) was an independent event to the system. J saw the cumulative pattern.
4. **No macro bias inheritance.** FOMC catalysts make pre-decision tape reliably bearish. The system entered LONG calls 90 min before FOMC despite the obvious macro lean.

**Outcome:** Real-money cost = $0 (paper). Paper cost = -$45 + opportunity cost of missing the 735.40 short setup (~$255-450 potential). Process cost = J had to debug live what the system was doing wrong.

**Pattern:** Counter-trend chop trap. The system enters on a single-bar reclaim signal while the broader pattern is screaming continuation. Risk: this can repeat any time price chops between a broken level and a deeper support, with the system buying every micro-bounce.

**Fix (queued for tonight, NOT mid-session per rule 9):**
1. **Lower-highs / lower-lows counter** — track last 3 bounces at any level; if all 3 made progressively lower highs and final close is below the level, +2 score modifier toward bear (or -2 for bull on inverse).
2. **Role reversal flag** — when a key level breaks definitively (5-min close past it by >$0.10), mark `key-levels.json#level.role = "broken_to_resistance"` (or support). On retest, only count as rejection if rejected from the broken side.
3. **Sequence-aware confluence trigger** — a sequence of 2+ bars at decreasing highs above a broken level = the "confluence" trigger for filter 10 fills automatically.
4. **Macro pre-event bearish lean** — if `today-bias.news_calendar.events_today` has FOMC/CPI/NFP within 4 hours, default bias is "drift bearish, breakouts fade" until premarket explicitly overrides.

**Logging gaps surfaced:**
- The trade FIRED at 12:30 but `trades.csv` was never written by the system. Manual backfill done.
- `decisions.jsonl` only has 3 rows (10:30, 10:33, 10:51) — every tick after that failed to append. Heartbeat logging discipline needs verification.


### 2026-05-08 — Wasted 3 hours of compute on a broken-gate autoresearch sweep

**Rule broken:** Operating principle 8 — "no deferral, no fallback to manual." Should have caught the gate misconfig before launch, not after 45 wasted iterations.

**What I did:** Launched the 3-mode (strict/balanced/aggressive) × 15-iter autoresearch sweep with hard gates calibrated for the OLD bear-only strategy (40% WR floor, 20-trade min, $0 expectancy floor). The new bullish-enabled baseline is 15-27% WR. Result: every single iteration was rejected at the WR gate. 3 hours of compute. 0 KEEPs across all 45 iterations.

**Why I did it:** I had the bullish baseline data (171 trades, 15.2% WR) printed in the terminal 30 seconds before launch. I noted "bullish bleeds" but didn't think to verify the gate floor was reachable. Optimised for "ship the run" instead of "verify the gate calibration."

**Outcome:** Real cost: 3 hours of CPU + J's frustration ("you kinda fucked up, bro"). Hidden upside: 7 of the 45 iterations were actually *winners* under sane gates — including aggressive iter 7 with +$1,799 P&L / 32% WR / sharpe 3.22 on the validate window. They were destroyed by the gate.

**Pattern? Have I done this before?** Yes — same family as "shipping a feature without exercising it end-to-end first." Operating principle says fix-on-find; corollary should be "verify-on-launch."

**Fix:**
1. **Pre-flight gate sanity check** — before any sweep, run baseline backtest, print "baseline WR=X gate floor=Y gap=Z", refuse to launch if gap > some threshold. (To be added to `autoresearch/loop.py`.)
2. **Smart watchdog** — after each batch reads history.jsonl, counts KEEPs, flags 0-KEEPs-in-a-row patterns and writes a report file. (To be built — `autoresearch/watchdog_report.py`.)
3. **Recalibrated gates** — WR floor 40%→10%, trades 20→10, expectancy $0→-$10, W/L 1.20→0.80. Documented in `config.py`.
4. **Memory entry** — saved as `feedback_autoresearch_wiring.md` in personal memory so the gate-sanity-check rule survives across sessions.

**Logging gap:** The watchdog log showed "RUNNING" 6 times in a row but never surfaced the fact that every iteration was reverting. A "running" check is not a "making progress" check.


### 2026-05-18 — First-live-day Bold missed entry — heartbeat timeout left naked unbracketed parent order (rule-3 violation by infrastructure)

**Rule broken:** Rule 3 — "Defined stop on entry. Premium stop or chart stop. Mechanical. Stated in journal *before* entry." Bracket order intent included TP1 + stop legs, but wrapper killed claude.exe 10s after parent BUY submitted and before legs got placed. Naked SPY 5/18 739C × 5 @ $1.74 sat on book ($870 = 87% of $1K equity) with NO stop.

**What I did:** Bold heartbeat 09:48:02 fired bull=11/11 (clean BULLISH_RECLAIM on 09:45 bar's failed-breakdown wick into 737.56 / 2.3× vol / ribbon BULL 45c / VIX 18.43 falling). Engine called bracket order. Parent submitted 09:50:33. Wrapper hit 160s wall-clock at 09:50:43 and tree-killed 18 PIDs including claude mid-bracket. Parent persisted as `order_class: "simple"` (Alpaca fallback). Next 2 ticks reported pending_fill / ERROR_ALPACA. J spotted at 09:54, I cancelled at 09:54:37.

**Why:** Wrapper had `tickTimeout=160s` + `MaxBudgetUsd=0.50` — sized for HOLD ticks (60-90s) not ENTRY ticks (snapshot chain + 3-leg bracket + state writes + screenshot = 90-180s). Underestimated entry-tick variance under live Alpaca latency.

**Outcome:** Order never filled. **Counterfactual: SPY 738.86 (09:48) → 740.89 (09:50) → 741.35 (09:55). 739C est worth $2.40-2.70 by 09:55 vs $1.74 entry = +$330-480 (+38-55%) on 5 contracts. MISSED.** Setup valid, engine right, infrastructure failed.

**Pattern? Yes — same family as 5/15 −$770:** wrapper sized for HOLD ticks doesn't survive ENTRY ticks. Should have caught in pre-flight by exercising end-to-end entry path in paper before go-live.

**Fix shipped mid-session (infra only, no doctrine touch):**
- `setup/scripts/run-heartbeat.ps1` MaxBudgetUsd 0.50 → 1.00
- `setup/scripts/run-heartbeat-aggressive.ps1` MaxBudgetUsd 0.50 → 1.00, tickTimeout 160s → 220s (haiku) / 150s → 180s (sonnet)
- Unbracketed parent cancelled 09:54:37

**Queued for after-4pm work block tonight:**
1. **Atomic-bracket guard** — if parent submits but TP1/stop fail (timeout/kill/Alpaca rejection), IMMEDIATELY cancel parent. Heartbeat prompt wraps order placement in try/finally that cancels on partial failure, OR post-tick reconciler checks within 1 tick of any pending_fill whether brackets exist + cancels if not.
2. **VIX threshold drift audit** — Bold loop-state reported `vix_above_threshold_18_43_>_17_20_required` but `aggressive/params.json#vix_entry_thresholds.bull_max_exclusive_or_falling` = 20.00. Verify if `aggressive/heartbeat.md` hardcodes 17.20. If drift confirmed, sync via gamma-sync.
3. **L## entry to `markdown/doctrine/LESSONS-LEARNED.md`:** "Heartbeat timeout during multi-step bracket placement leaves naked parent. Rule 3 violation by infrastructure. Mitigation: wider entry-tick timeout + atomic-bracket guard + orphan-order reconciler."
4. **Wrapper post-kill hook** — log "parent order submitted before kill" to `orphan-orders-{date}.jsonl` so next-tick reconciler picks up immediately rather than discover-by-poll.

**Logging gap:** Wrapper logged TIMEOUT_KILL + killed PIDs but did NOT log "parent order submitted before kill — manual reconciliation may be required." Next tick discovered the pending_fill by Alpaca polling 70s later.
