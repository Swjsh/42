## [2026-08-13 16:37:45 Thursday EDT] GREEN -- interactive session: full trade review + 5 live-path fixes shipped

**J directives this session:** (1) full review of every trade today from all angles, (2) fix account
sizing, (3) no more CMD popups, (4) work the 8-item queue.

### Day: +$1,748 across 15 discrete round trips (8 winners +$2,517 / 7 losers -$769)

**The discriminator** -- all 8 winners hit +25% within **4-6 minutes**; all 7 losers **NEVER** did.
Zero overlap (winners MFE >= +69%, losers <= +24%). Acting on it as an EXIT is worth only +$117
today (the structure stop already exited at similar prices); its value is as a signal-quality
readout, and nothing currently consumes it.

Full forensics on ~500,000 real OPRA prints: `analysis/deep-research/FULL-TRADE-REVIEW-2026-08-13.md`

### Shipped (each guard-tested and RED-proofed by source mutation)

| fix | what it closes |
|---|---|
| `min_contracts` equity scaling | the only sizing knob that was an absolute COUNT; authored at $2K, live equity $5,501. The recency clamp used that FLOOR as a CEILING, overriding a risk gate that computed 8 back to 3. Restores the validated risk FRACTION (3->8), not the 5.6x proportional figure. |
| `eod_flatten` checked read | a timed-out `/v2/positions` returned `[]`, logged "already flat", and returned. On 0DTE that is expiry, not a delayed exit. |
| window-leak allowlist scope | a console host inherited "Claude Code" from its parent title and was silently exempted. |
| leak-detector keepalive recycle | the detector was ALIVE and polling for 88h (3.18M polls) detecting NOTHING, while the keepalive reported "detector alive" every 5 min. |
| 47 tasks off the venv pythonw | **A/B: venv 9 leaks/10 launches vs system pythonw + PYTHONPATH 0/10.** Verified before/after: 24 leaks in 16:10-16:19 ET -> **0** in 16:20-16:29. |

Also: SSR futures arming bar now discloses it is scored on ~$1.79M notional against a ~$5,500
book ($15,832 headline -> ~$1,583 fundable); CLAUDE.md's TP1 claim corrected (it is a STRATEGY
setting, not per-account -- three different values existed for one account).

### Corrections I had to make to my own work (recorded so the pattern is visible)

- Reported the day as +$1,619, then +$1,485 -- both wrong; FIFO reconstruction gives **+$1,748**.
- Claimed "140/140 tasks on the hidden chain". That check tested `wscript OR pythonw` in the
  action; it answered "no bare powershell" (true) and I presented it as "no leaks" (false).
- Scope of the venv leak reported as 20, then 7, then **47** -- `schtasks /fo csv` TRUNCATES the
  `Task To Run` column. **Any task-action audit must use `/xml`.**
- Attributed the popup recovery to my allowlist fix; it was the RESTART. The fix is still correct
  and closes a separate blindness.
- Nearly shipped the sizing fix half-landed -- two clamps run back-to-back and `risky-1` is
  `full_send=true`, so scaling one would have been a no-op on the exact arm it targeted.

### The theme

Six independent surfaces today reported GREEN over a live failure: `exit=0` while an arm sat past
its stop, `leaks_total 0` across 3.18M polls, a stale `min_contracts` that still looked valid, a
truncated CSV column, "already flat" on an unreadable account, and a futures P&L in unfundable
contracts. **A success signal that means "nothing raised" is not a success signal.**

### Open (not fixed, deliberately)

- `get_positions` still fails open to `[]` -- documented as correct for the exit manager's
  per-tick retry. Today's failures were CORRELATED (15 min straight), which is when that
  reasoning stops holding. Left in place; a guard pins the premise so a change is deliberate.
- Cost-recovery and trendline-at-level preregs are FROZEN but their runners have not been run.

---

## [2026-08-13T16:15:03 ET] YELLOW -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-13 -- 4 GREEN / 1 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 121 tick(s) showed in_trade>0. 50 real fill(s) dated 2026-08-13: safe-2@09:51, bold-2@09:51, safe-2@09:52, safe-3@09:52, risky-1@09:52, risky-3@09:52, bold-2@09:52, safe-2@09:53, bold-2@09:53, safe-2@09:56, bold-2@09:56, safe-2@09:57, bold-2@… |
| WS6 regime stamp | YELLOW | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-13, generated_at_et=2026-08-13T16:07:03-04:00 (hhmm=16:07, in 08:15-08:40 window=False). today-bias.json date=2026-08-13, regime_context.stamp_date=2026-08-13 (present=True, dates_match=True). one_liner='Yesterday 2026-08-12 (Wed) = range-chop (range 0.47%, gap +0.56%… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 59 distinct near-price levels. Worst: 775.64 flipped 4x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 22 time(s) across 4 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-13 window_end=2026-08-12 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=21 (delta +11 vs baseline n=10) exp=$-19.76/tr, verdict_moved=False. bull now: RED n=17 exp=$-8.71/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-13T16:00:04 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 403 theta-clock row(s) dated 2026-08-13 across 6 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=403, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-13 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-13`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-12] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-07-09..2026-08-12), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-08-12). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=RED
> - **Books:** Safe2_ATM_1+2+4=CONFIRM ($243.05); Bold_ATM_1+2=CONFIRM ($1197.2)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: #4 ATM — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-08-12T16:15:04 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-12 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 117 tick(s) showed in_trade>0. 117 real fill(s) dated 2026-08-12: risky-1@09:46, risky-3@09:46, safe-2@09:51, safe-2@09:52, risky-1@09:52, risky-3@09:52, bold-2@09:52, safe-2@09:53, bold-2@09:53, bold-2@09:53, safe-2@09:54, safe-3@09:54, bold… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-12, generated_at_et=2026-08-12T08:40:03-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-12, regime_context.stamp_date=2026-08-12 (present=True, dates_match=True). one_liner='Yesterday 2026-08-11 (Tue) = range-chop (range 0.70%, gap +0.19%,… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 64 distinct near-price levels. Worst: 772.47 flipped 6x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 126 time(s) across 20 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-12 window_end=2026-08-11 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=17 (delta +7 vs baseline n=10) exp=$-22.0/tr, verdict_moved=False. bull now: GREEN n=12 exp=$8.25/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-12T16:00:03 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 340 theta-clock row(s) dated 2026-08-12 across 8 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=340, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-12 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-12`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-11T16:15:03 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-11 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 134 tick(s) showed in_trade>0. 50 real fill(s) dated 2026-08-11: risky-1@09:46, risky-3@09:46, risky-3@09:51, risky-1@09:52, risky-1@09:55, risky-3@09:55, safe-2@11:51, safe-2@11:52, risky-1@11:52, safe-2@11:53, bold-2@11:53, safe-2@11:54, bo… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-11, generated_at_et=2026-08-11T08:40:02-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-11, regime_context.stamp_date=2026-08-11 (present=True, dates_match=True). one_liner='Yesterday 2026-08-10 (Mon) = pin-day (range 0.44%, gap -0.07%, cl… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 60 distinct near-price levels. Worst: 772.26 flipped 5x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 42 time(s) across 7 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-11 window_end=2026-08-10 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=12 (delta +2 vs baseline n=10) exp=$-42.75/tr, verdict_moved=False. bull now: GREEN n=12 exp=$8.25/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-11T16:00:04 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 252 theta-clock row(s) dated 2026-08-11 across 4 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=252, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-11 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-11`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## Live watch

- [2026-08-13T12:53:01 ET] THETA STALL :: safe-2 SPY260813P00776000 qty=3 :: est theta burn -5.34 vs est delta gain +0.00 over last 15min (mid=0.395, unrealized=-38.09%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T12:49:01 ET] THETA STALL :: bold-2 SPY260813P00776000 qty=5 :: est theta burn -5.70 vs est delta gain +0.00 over last 15min (mid=0.435, unrealized=-32.81%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T11:52:01 ET] THETA STALL :: safe-3 SPY260813C00776000 qty=3 :: est theta burn -5.52 vs est delta gain -27.00 over last 15min (mid=0.845, unrealized=-25.66%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T11:49:01 ET] THETA STALL :: bold-2 SPY260813C00776000 qty=5 :: est theta burn -6.60 vs est delta gain +0.00 over last 15min (mid=0.905, unrealized=-9.28%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T11:48:01 ET] THETA STALL :: risky-1 SPY260813C00776000 qty=5 :: est theta burn -5.15 vs est delta gain -10.00 over last 15min (mid=0.985, unrealized=-14.04%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T10:38:01 ET] THETA STALL :: risky-3 SPY260813C00781000 qty=10 :: est theta burn -5.50 vs est delta gain +0.00 over last 15min (mid=0.305, unrealized=-11.11%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T10:18:02 ET] THETA STALL :: safe-2 SPY260813C00777000 qty=3 :: est theta burn -6.06 vs est delta gain -1.50 over last 15min (mid=1.94, unrealized=84.47%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-13T10:18:02 ET] THETA STALL :: safe-3 SPY260813C00777000 qty=3 :: est theta burn -6.27 vs est delta gain -1.50 over last 15min (mid=1.94, unrealized=74.31%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T10:17:01 ET] THETA STALL :: risky-3 SPY260812C00775000 qty=10 :: est theta burn -5.50 vs est delta gain +0.00 over last 15min (mid=0.395, unrealized=5.71%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T10:17:01 ET] THETA STALL :: safe-2 SPY260812C00773000 qty=3 :: est theta burn -5.16 vs est delta gain +0.00 over last 15min (mid=1.055, unrealized=1.98%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T10:17:01 ET] THETA STALL :: safe-3 SPY260812C00773000 qty=3 :: est theta burn -5.22 vs est delta gain +0.00 over last 15min (mid=1.055, unrealized=0.98%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T10:14:01 ET] THETA STALL :: risky-1 SPY260812C00773000 qty=5 :: est theta burn -5.25 vs est delta gain +0.00 over last 15min (mid=0.945, unrealized=0.0%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T10:11:01 ET] THETA STALL :: bold-2 SPY260812C00773000 qty=5 :: est theta burn -5.20 vs est delta gain +0.00 over last 15min (mid=1.025, unrealized=-4.76%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-12T09:54:01 ET] THETA STALL :: risky-3 SPY260812P00771000 qty=8 :: est theta burn -5.28 vs est delta gain +0.00 over last 15min (mid=0.755, unrealized=10.0%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T14:40:03 ET] THETA STALL :: risky-1 SPY260811P00770000 qty=5 :: est theta burn -6.70 vs est delta gain -15.00 over last 15min (mid=0.645, unrealized=6.9%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T13:55:02 ET] THETA STALL :: safe-2 SPY260811P00771000 qty=3 :: est theta burn -5.04 vs est delta gain +0.00 over last 15min (mid=0.465, unrealized=-10.2%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T13:39:01 ET] THETA STALL :: risky-1 SPY260811P00771000 qty=5 :: est theta burn -5.35 vs est delta gain -95.00 over last 15min (mid=0.715, unrealized=-6.41%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T13:38:01 ET] THETA STALL :: bold-2 SPY260811P00771000 qty=5 :: est theta burn -6.05 vs est delta gain -100.00 over last 15min (mid=0.675, unrealized=-17.72%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T12:03:01 ET] THETA STALL :: safe-2 SPY260811P00772000 qty=3 :: est theta burn -5.46 vs est delta gain +0.00 over last 15min (mid=0.685, unrealized=-13.58%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T12:02:02 ET] THETA STALL :: bold-2 SPY260811P00772000 qty=5 :: est theta burn -5.15 vs est delta gain -87.50 over last 15min (mid=0.735, unrealized=-20.23%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T12:01:01 ET] THETA STALL :: risky-1 SPY260811P00772000 qty=5 :: est theta burn -6.95 vs est delta gain +0.00 over last 15min (mid=0.655, unrealized=-25.88%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-11T09:57:01 ET] THETA STALL :: risky-3 SPY260811P00771000 qty=10 :: est theta burn -6.50 vs est delta gain +0.00 over last 15min (mid=0.485, unrealized=-4.17%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a NEW stalled-position threshold crossing; never re-fired for the same position. Producer: setup/scripts/theta_clock.py._

---

## [2026-08-11T05:30 ET] CONDUCTOR: OK -- SELF-AUDIT-ORGAN-TIMEOUT-AND-DEDUP-LEDGER-REVERSION (priority-3, self-audit gaps) -- commit `44061a57`, REVOKE surface

**Task picked (priority-3 per STAGE 1: self-audit gaps):** function-first (fill_funnel)
and engine-health (state_freshness) were both clean at fire start (1/21 stale = the
already-known, non-critical `futures/data-freshness.json` self-heal-on-next-live-tick
entry). Read `analysis/self-audit/new-gaps-flagged.md` and found its last batch/triage
was 2026-08-08 -- 3 days silent for a daily-firing organ. Investigated live rather than
assuming: `Gamma_SelfAudit` (Get-ScheduledTaskInfo-equivalent check) shows
`LastTaskResult=0` on 2026-08-10, but `analysis/self-audit/gap-log.jsonl` (the dedup
ledger, distinct from the properly-committed `new-gaps-flagged.md`) hadn't gained a new
timestamp since 2026-07-13 -- a full month.

**2 root causes, both real, both fixed:**
1. `self_audit.py`'s outer `subprocess.run(..., timeout=300)` to `swarm_consult.py` was
   SMALLER than swarm_consult's own worst-case internal budget
   (`PERSPECTIVE_TIMEOUT_S=240 + SYNTHESIS_TIMEOUT_S=300 = 540s`) -- silently killed and
   swallowed by a bare `except Exception: return 0`. Live log evidence:
   `self-audit.stdout.log` shows `TimeoutExpired` on 2026-08-09 AND 2026-08-10
   (2 consecutive full-audit failures, exit-0 to Task Scheduler both times).
2. `gap-log.jsonl` -- self_audit.py's ONLY dedup-key source -- is the SAME
   tracked-but-rarely-committed hazard class as the 4 prior STATE-FILE-REVERSION rounds
   (2026-07-14/07-20/07-21/08-10), just a 5th file family outside `automation/state/`.
   Last real commit: the 2026-07-14 data-loss-recovery (`41889a0f`). Effect: already-
   triaged gaps were silently re-flagged "new" and re-triaged from scratch for ~4 weeks,
   masked because `new-gaps-flagged.md` (a separate, correctly-committed narrative file)
   kept growing normally the whole time -- a producer's visible output looking healthy
   is not evidence its internal state is.

**Fix:** `SWARM_SUBPROCESS_TIMEOUT_S=600` (named constant, cross-file drift guard);
`gap-log.jsonl` gitignored + `git rm --cached` (5th instance of the established remedy,
new `SELF_AUDIT_GAP_LOG` category in `test_ledger_gitignore_guard.py`);
`self_check.check_self_audit_organ_alive()` (DEGRADED-only daily liveness check on the
ledger's own newest timestamp, mirrors `check_regime_stamp_daily`/
`check_scout_premarket_fresh`'s "verify the artifact, not the exit code" pattern) so a
future recurrence surfaces within a day, not a month.

**Verified (OP-33):** 23 new/extended guard tests, RED-proofed via rename-and-restore
(L238, not `git stash`) against pre-fix HEAD source -- 11/11 correctly failed pre-fix
(`AttributeError`/assertion misses), 23/23 green post-fix. Full
self_check+self_audit+gitignore suite: 221/221 green. Curated safety gate: 59/59 PASS.
`git show 44061a57 --stat` confirms exactly the 7 intended files (L247 discipline).
Lesson filed: `_lesson-inbox/self-audit-organ-timeout-and-dedup-ledger-reversion-2026-08-11.md`.

**Rail-4 clear:** zero live-order/params/heartbeat_core/filters/placement/exit/CLAUDE.md
files touched -- pure self-improvement-organ infra (self_audit.py, self_check.py, 2 new
test files, .gitignore, the untracked ledger). **REVOKE:** `git revert 44061a57` (7 files).

---

## [2026-08-11T01:08 ET] CONDUCTOR: OK -- VERIFY-2026-08-10-ZERO-FILLS-DESPITE-ACCEPTED-ORDERS (FUNCTION-FIRST) -- commit `1d43c599`, REVOKE surface

**Task picked (priority-1, FUNCTION FIRST per STAGE 1):** queue.md's own
"next fire: run `fill_funnel.py` for 2026-08-10 FIRST" flag, filed after
`conductor_outcome.py metric` reported `orders_accepted=9, fills=0` for
2026-08-10 -- the exact entry->order->fill funnel break shape that outranks
everything else in the conductor prompt.

**Verdict: NOT a real break.** `fill_funnel.py --date 2026-08-10` = **GREEN**
across all 5 arms (core:bold/core:safe/fleet risky-1/risky-3/safe-3): 9
accepted, 6 filled, 6 exited. The `fills=0` reading was a metric-timing
artifact: `conductor_outcome.py`'s function snapshot reads `journal/
trades.csv`, which `fleet_journal_bridge.py` backfills from broker-truth on
its OWN separate schedule well after the trading day ends. 3 fires overnight
(08-10 22:40 / 08-11 00:50 / 01:55 ET) all fired BEFORE that backfill landed
and honestly recorded `fills:0` for a day that traded fine -- re-running
`trading_function_snapshot()` live (this fire, after the backfill caught up)
returned `fills:11`.

**Fixed the metric, not just the symptom:** `compute_metric()` now
reconciles the function fields (fills/orders_accepted/enters/distinct_setups/
extra_exec) per `trading_day` to the MAX seen across the full outcome
history before computing `function_latest`/`trend`/`function_score_avg` --
safe because these fields are monotonically non-decreasing as a completed
day's ledgers backfill (nothing un-fills). Read-layer only;
`conductor-outcomes.jsonl` itself is never rewritten (append-only ledger
intact). 5 new guard tests (`test_conductor_outcome_backfill_reconciliation.py`),
RED-proofed via `git stash` (1/5 correctly failed pre-fix on the direct
reconciliation assertion). Corrected (not weakened) 2 pre-existing trend
tests in `test_conductor_outcome_function.py` whose fixtures used one
literal `trading_day` string for both halves of an older-vs-recent
comparison as a convenience shorthand -- the new (correct) reconciliation
blends same-day snapshots, so gave each half a distinct realistic day
instead; same assertions, same intent. Full blast radius (conductor_outcome
+ conductor_gate_precheck + conductor_budget suites): 93/93 green. Curated
safety gate 59/59 PASS. `git show 1d43c599 --stat` confirms exactly the 4
intended files (source fix + 2 test files + 1 lesson-inbox write).

**Lesson filed:** `_lesson-inbox/2026-08-11-conductor-outcome-backfill-lag-
false-alarm.md` -- general pattern: a consumer reading a value written by
two producers on different schedules (live tick + separate backfill job)
cannot trust a single point-in-time read as final; reconcile to best-known
value when the field is provably monotonic, or the race reads as a false
signal to every downstream consumer.

**Rail-4 clear:** zero trading-path files touched (params/heartbeat_core/
filters/placement/exit/CLAUDE.md) -- pure conductor self-measurement code +
2 test files + 1 lesson write. **REVOKE:** `git revert 1d43c599` (4 files,
clean).

---

## [2026-08-11T01:15 ET] KNOWN BROKEN: 2 pre-existing test failures, NOT caused by tonight's exit work

Surfaced while running the twin suite after wiring the pre-TP1 ladder into the crypto twin.
Both were verified pre-existing by A/B, so neither is a regression from tonight -- but they
were failing silently and nobody had flagged them (C7). Filed, not fixed: fixing them is out
of scope for the exit lane and would be a drive-by.

1. `test_twin_gauntlet.py::test_dry_mode_all_six_paths_pass_by_default` -- the `max_hold`
   path FAILs. Root cause: the scenario asserts `journal[-1]["event"] == "CLOSED"`, but the
   twin now writes `CLOSED` then `EXIT_FILLED`, so the last row is EXIT_FILLED and the check
   misses. PROOF IT IS NOT THE LADDER: `run_dry(['max_hold'], overrides={'exit_shape': <ladder
   keys removed>})` FAILs identically. The journal-ordering change predates 2026-08-10.
   Fix when picked up: assert on the presence of a CLOSED/max_hold_flatten row in the tail,
   not on strict last-row position.

2. `test_free_model_audit_twin_review.py::test_wired_in_real_registry_and_end_to_end_against_the_real_sidecar`
   -- asserts `result["correct"] is True` against the LIVE twin-health sidecar. It depends on
   current sidecar content, so it is environment-coupled by construction and will flap.
   Fix when picked up: pin a fixture sidecar for the assertion and keep the live read as a
   separate, non-blocking smoke.

Everything else in the twin + fleet suites is green: fleet 379 passed, twin/crypto 880 passed.

## [2026-08-10T21:54 ET] CONDUCTOR: OK -- STATE-FRESHNESS-REVERSION-FOLLOWUP-3 (5 producers manually refreshed) -- REVOKE surface N/A (no code changed)

**Task picked (priority-2, Engine RED):** `engine-health.json` flagged `state_freshness`
RED at fire start -- 7/21 stale. NOT the git-reversion class from the two prior fires
tonight (verified those 6 files stay correctly untracked+gitignored, `git status
--porcelain` clean). This time it's a NEW class.

**Root cause (verified live):** `context-bundle.json`/`confluence-zones.json`/`trade-
today.json`/`ema-snapshot.json`/`news.json`/`premarket-readiness.json` carried
weeks-stale INTERNAL content stamps (07-14 through 07-27) despite their scheduled tasks
(`Gamma_ContextBundle`, `Gamma_Confluence`, `Gamma_TradeToday`, `Gamma_EmaSnapshot`,
`Gamma_MacroCalendar`, `Gamma_PremarketReadiness`) firing all day with clean
`LastTaskResult=0` and zero hits in `self_check.py`'s masked-exit check. Manually
re-running all 5 underlying producers via the EXACT scheduled-task invocation chain
worked instantly -- confirms the producer CODE is fine; something about the unattended
firing specifically silently no-ops. **Precise mechanism NOT conclusively found this
fire** (rail-3 bounded) -- investigated and RULED OUT `run_cmd_hidden.py` code drift
(byte-identical to HEAD since 07-14) and `Principal.LogonType` (identical
`Interactive`/`jackw` across working and broken tasks). Flagged as
`RUN-CMD-HIDDEN-OFF-DESKTOP-PROVENANCE` in queue.md with concrete evidence for a future
fire to pick up with live instrumentation.

**Fix:** manually re-ran all 5 producers -- `state_freshness_audit.py` verdict went 7/21
stale (RED) -> 1/21 stale (the 1 remaining, `futures/data-freshness.json`, is a
DIFFERENT already-fixed-in-code issue from tonight's 18:45 fire, self-heals on
tomorrow's live tick). `engine-health.json` re-run confirms `state_freshness` RED only
on that 1 expected-quiet entry.

**Lesson filed:** `_lesson-inbox/state-freshness-detector-no-remediator-2026-08-10.md` --
2nd instance of "a detector without an automatic remediator re-violates on its own
schedule" (L252's rule). `state_freshness_audit.py` correctly flagged RED the ENTIRE
3-4 week gap and nothing ever auto-re-ran the flagged producer. Queued
`STATE-FRESHNESS-AUTO-REMEDIATOR` (HIGH) to close that gap structurally.

**Rail-4 N/A:** zero trading-path files touched; zero code changed. Only regenerated
JSON/state files via their own existing, unmodified producers (byte-identical output to
what those scripts would produce on their next legitimate scheduled fire) + 1
lesson-inbox write + 3 queue.md items. Nothing to revert.

---

## [2026-08-10T21:05 ET] CONDUCTOR: CORRECTION to the 20:43 entry below -- the "absorbed by 658ecc79" claim was WRONG, re-verified and re-shipped

**What actually happened (OP-33: caught by re-verifying my own claim, not trusting it):** the
20:43 entry below claimed the first 6 files' untrack landed correctly, just under another
session's commit message (`658ecc79`). That was a misread -- I checked `git ls-files` (which
reflects the INDEX) and treated "empty" as proof of a committed state, without separately
checking `git cat-file -e HEAD:<path>` (which reflects what's actually COMMITTED). Re-checking
directly: all 8 target files (the original 6 + the 2 found in the completeness pass below) were
STILL PRESENT IN HEAD after three separate `git commit -- <paths>` invocations, each of which
silently printed "no changes added to commit" despite `git diff --cached` correctly showing a
staged `D` for every path -- root cause of that specific git behavior not resolved this fire
(flagged below, not chased further -- the fix itself was not blocked by it).

**Resolution:** verified the full shared index held EXACTLY these 8 staged deletions and
nothing foreign (`git diff --cached --name-only`, 8 lines, all mine) before doing a plain
(non-pathspec) `git commit` -- safe specifically because nothing else was staged to absorb.
Commit `cd7a3824`. Re-verified post-commit via `git cat-file -e HEAD:<path>` (not `ls-files`)
for all 8: all ABSENT from HEAD, confirmed untracked. Guard suite 10/10 green. Working-tree
disk content for all 8 files verified intact and JSON-parseable.

**New, real finding for a future fire (not chased further this fire, rail-3 bounded):**
`git commit -m ... -- <pathspec>` on this checkout silently declined to commit an otherwise-
valid staged deletion three times in a row tonight, with no error and a misleading "no changes
added to commit" message even though `git diff --cached -- <same paths>` showed a real diff.
Mechanism not identified (possibly interaction with `.gitignore` + a freshly-`rm --cached`
path in the SAME invocation, possibly hook-related, possibly a genuine git quirk on this
Windows/git-bash setup) -- worth a dedicated investigation if it recurs, since pathspec-scoped
commits are this repo's own prescribed defense against shared-index absorption
(`commit_scoped.py`) and a silent failure mode in that exact mechanism is a real gap.

---

## [2026-08-10T20:43 ET] CONDUCTOR: OK -- STATE-FRESHNESS-REVERSION-FOLLOWUP-2 (6 files untracked) -- REVOKE surface

**Task picked (priority-2, Engine RED):** `engine-health.json` flagged `state_freshness`
RED at fire start -- 6 live-path producers stale 2026-07-14/07-15, up to 27 days:
`key-levels-memory.json`, `prior-rth-close.json`, `trade-today.json`, `confluence-zones.json`,
`ema-snapshot.json`, `context-bundle.json`.

**Root cause (verified live, one sentence):** all 6 are tracked-but-rarely-committed
(last commit = 2026-07-14/07-15, the SAME commit as the 2026-07-14 `git stash drop`
data-loss incident) while their Task-Scheduler-run producers keep rewriting them every
5-10min all day (confirmed: `LastTaskResult=0`, and `level_memory_producer.py`'s own
stdout log shows fresh today's-date content computed AND written every cycle) -- so a
tree-wide git op in the shared checkout kept reverting the on-disk file back to the stale
committed snapshot between checks. Identical mechanism, and the identical established fix,
as the 2026-07-14/07-20/07-21 incidents already closed for LEDGERS/STATE_SNAPSHOTS/
DECISION_GATING_SNAPSHOTS in `backtest/tests/test_ledger_gitignore_guard.py` -- the 2026-07-21
triage was a partial sweep (~76 tracked files reviewed, 13 fixed) and simply missed these 6.

**Fix:** `git rm --cached` (untrack, disk content untouched) + `.gitignore` entries, mirroring
the 3 prior rounds exactly. New `STATE_FRESHNESS_REVERSION_FOLLOWUP_2` list + 2 guard tests
(`test_state_freshness_reversion_followup_2_are_{gitignored,untracked}`) in the same file.
Full guard suite 8/8 green (4 pre-existing + 4 new). Working-tree copies verified intact and
JSON-parseable post-fix.

**Live-caught a NEW instance of the L271 shared-index-absorption class while shipping this**
(not a new lesson -- an already-documented recurring hazard of this multi-session checkout):
the first commit this fire (`27cb218d`) landed the `.gitignore` + guard-test edits correctly,
but between my `git rm --cached` staging and the commit, a CONCURRENT other session ran a bare
`git commit` (`658ecc79`, "fix: move pre-TP1 trail arm +40% -> +75%; ship day-replay tool" --
unrelated trading-path work, not mine) that swept the staged untrack of these 6 files into ITS
OWN commit before my scoped follow-up could land. End state is fully correct and independently
re-verified after the fact (`git ls-files` empty + `git check-ignore` IGNORED for all 6, pytest
8/8 green, disk content intact) -- only the commit attribution is under someone else's message.
Disclosing per the established L271 remedy (transparency, not a force-rewrite of shared history
that would risk clobbering the other session's legitimate concurrent work).

**Found + flagged (not fixed, rail-3 out of scope):**
`backtest/tests/test_state_freshness_audit.py::test_date_axis_quiet_before_producer_ready_time`
is flaky pre-existing -- reproduced FAILING on main with this fire's changes fully stashed out
(baseline, before any of my edits). Compares a fixture file's age against the REAL wall clock
instead of a frozen one, so it silently crosses its own 20min budget as real time passes since
whatever epoch the fixture assumes. Not touched this fire (pre-existing, different file/module).

**Rail-4 clear:** additive-only (`.gitignore` + test extension) + index-untrack only (disk
content unchanged either way) -- zero trading-path files touched. Revert: the untrack is
reversible via `git add -f <path>` if ever needed, though per the established doctrine here
(3 prior identical incidents) re-tracking these files would be reintroducing the vulnerability,
not a fix.

**Why this outranked the queue:** Engine RED (STAGE 1 priority-2) outranks HIGH/MED backlog by
design -- this is the SAME class of active, self-flagged, silently-blind-for-27-days problem
the conductor exists to close before adding new artifacts, and it was the last remaining
`state_freshness` RED after tonight's earlier futures-freshness fix.

Cost this fire: ~$5 (live root-cause trace across producer logs + Task Scheduler introspection
+ git history, established-pattern fix + 2-test guard, a live git-index-absorption incident
mid-flight requiring re-verification and disclosure, queue/STATUS writeup).

---

## [2026-08-10T18:45 ET] CONDUCTOR: OK -- FUTURES-FRESHNESS-SNAPSHOT-NEVER-PERSISTED fix (commit a6d7e581) -- REVOKE surface

**Task picked (priority-2, Engine RED):** `engine-health.json` flagged `state_freshness`
RED at fire start -- `automation/state/futures/data-freshness.json` dated 2026-08-09
despite a fully clean 2026-08-10 live session (heartbeat/dispatch GREEN,
`Gamma_FuturesTrader LastTaskResult=0`).

**Root cause (verified, one sentence):** `futures_trader_core.refresh_data()` -- the
function the LIVE 5-min futures tick actually calls every cycle -- read
`fld.FRESHNESS_FILE` to decide whether to rate-limit its own re-fetch, but never
called `fld.write_freshness_snapshot()` to persist it back; only
`futures_live_data.py`'s own `--append`/`--check` CLI entry points ever wrote that
file, so the persisted snapshot silently froze at whatever a manual CLI run last
wrote while the underlying live bar cache kept refreshing correctly through a
separate call (`fld.append_live`, invoked directly). Exactly the C7 class
(`futures_live_data.py`'s own docstring names this pattern -- a fetcher whose watchdog
only the CLI writes is not a watchdog on the live loop).

**Fix (additive, one function):** `refresh_data()` now calls
`fld.write_freshness_snapshot((root,), interval)` on every call, both branches
(refetch and rate-limited-skip), so the persisted file always reflects the real live
tick cadence. Also fixed an adjacent latent bug found while reading the function: the
`data_refresh_failed` exception handler referenced an undefined `paths` name -- would
have raised `NameError` and masked a real fetch failure with a crash instead, the
first time `append_live` ever actually raised.

**RED-proofed:** `backtest/tests/test_futures_refresh_data_persists_freshness.py` (3
new tests) -- isolated tmp-path monkeypatching reproduces the exact caught bug (stale
on-disk snapshot survives a live tick untouched pre-fix), proves the file gets
re-persisted every call post-fix, and proves a failed fetch no longer raises
`NameError`. Full futures suite re-run clean: `test_futures_trader_core.py` +
`test_futures_heartbeat.py` + `test_futures_mirror_shadow.py` +
`test_futures_risk_rails.py` = 177/177 green, no regression. Curated safety gate
59/59 PASS (ran automatically at commit time).

**Rail-4 clear:** single function, additive-only, one commit --
`git revert a6d7e581` cleanly undoes it. Touches only the futures live-data refresh
path (paper/mechanism-evidence lane per the module's own EVIDENCE STATUS section, no
order placement/decision logic) -- guard + revert + this REVOKE report satisfy rail
4, no J pre-approval needed.

**Lesson filed:**
`strategy/candidates/_lesson-inbox/futures-freshness-watchdog-never-wired-to-live-tick-2026-08-10.md`
for lesson-author to encode as the next L## (candidate C7 fold: "a self-monitoring
snapshot is only trustworthy if the live tick loop writes it, not just the CLI").

**Why this outranked the queue:** Engine RED (STAGE 1 priority-2) outranks HIGH/MED
backlog items by design -- an unaddressed `engine-health.json` RED is exactly the
class of active, self-flagged problem the conductor exists to close before adding new
artifacts.

Cost this fire: ~$3.3 (root-cause trace across 2 modules + 1 scheduled-task
inspection, fix + 2-bug adjacent repair, 3-test guard authored/run, 177-test
blast-radius re-run, commit + stash-recovery detour, queue/lesson/STATUS writeup).

**Autonomy metric note:** `conductor_outcome.py metric` reports `trend: regressing`
(net_improvement 85 over last 20 fires, cost/drained $0.76). Flagging per OP-22 --
next fire should prefer another loop-closing item (drain, not accumulate) over a new
artifact until this trends back to stable/improving.

---

## [2026-08-10T01:xx ET] CONDUCTOR: OK -- TWIN-ESCALATION-BACKLOG-TRIAGE + TWIN-TS-UTC-DRIFT guard -- commit pending -- REVOKE surface

**Task picked (priority-4 queue): 9 `TWIN-ESCALATION` rows sitting `status:pending` in
queue.md's "Twin escalations" section since 2026-07-14 (some 27 days stale), each tagged
"dispatch a Sonnet investigation" and never actually investigated.** Read STAGE 0-1
first: engine-health.json GREEN, self-check GREEN, no funnel anomaly (market closed,
pre-open). No HIGH queue items or self-audit gaps outranked this.

**Did:** investigated all 9 individually with live evidence (not guessed):
- 07-14, 07-17, 07-19 TICK_GAPs: all ONE already-diagnosed episode (07-14
  `PC-SLEEP-7H-OVERNIGHT` manual-sleep incident, already root-caused in queue.md's
  "Needs J's own hands"; STATUS.md's own 2026-08-09 FuturesBrokerLane note already
  admits "the crypto twin once went dark 4 days unnoticed" -- that IS 07-15..07-19/20).
  CLOSED, no new work needed.
- 07-23 BREAKER_TRIPPED: working as designed (daily UTC latch, auto-rolls next day;
  breaker.json live-verified `tripped: false`, 18 clean days since). CLOSED.
- 07-26, 07-29 TICK_GAP+LOW_UPTIME: a real, distinct, roughly-weekly partial-day uptime
  pattern, already self-identified by the self-audit-gaps organ (2026-08-06 batch:
  "tick-rate watchdog, auto-restart"). TRIAGED, not guessed at -- filed as
  `TWIN-UPTIME-WATCHDOG` (multi-session scope, needs a real design).
- 07-30 TICK_GAP (31.3min): noise, barely over threshold, same-day self-resolve. CLOSED.
- 08-08 ACCOUNT_REGRESSION: self-resolved (twin-sentinel.json live-verified this fire:
  `account_status: "LIVE"`, GREEN, zero reasons). CLOSED.
- **08-04 TICK_GAP (29400.0 min = 20.4 days): ROOT-CAUSED as a FALSE POSITIVE, not a
  real outage.** 29400.0 min is an EXACT match (2026-07-15T04:00:00 UTC ->
  2026-08-04T14:00:01 UTC = precisely 29400 min) to a confirmed data-integrity bug: a
  still-unlocated writer sometimes appends a `HOLD_BAD_BARS`/"bar feed not ok:
  stale_data" row to `decisions.jsonl` with `ts_utc` FROZEN at 2026-07-15T04:00:00 while
  `ts_et` (from `et_now()`, no injectable override anywhere I traced) stays genuinely
  fresh -- 16 confirmed occurrences 2026-07-15..2026-08-09 (grep-verified; `ts_et` spans
  6+ real calendar dates, `ts_utc` byte-identical every time).

**Full call-chain read to find the writer, not guessed -- ruled OUT:**
`crypto_twin_core.run_tick`/`_decision_row` (confirmed live via interpreter
introspection against the exact running source: no uncommitted diff, no stale .pyc,
`now = now_utc or datetime.now(timezone.utc)` computed fresh every call),
`crypto_twin_scenarios.run_scenario_tick`, `crypto_twin_health.run_tick_with_health`
(same fresh-clock chain all the way to the scheduled task's actual command line, which
I read directly via `Get-ScheduledTask` -- confirmed it runs the main checkout, not a
worktree), `twin_gauntlet.py`'s DRY fixtures (isolated tmp_dir + a DIFFERENT frozen
date, 2026-01-01), `twin_chaos_drill.drill_stale_feed` (the obvious suspect by name --
source read confirms it uses real wall clock + writes deliberately/by-design for
visibility). **Producer not found within this fire's bounded budget -- flagged, not
guessed at**, filed as `TWIN-TS-UTC-DRIFT-PRODUCER` (queue.md) with the exact ruled-out
list so a future fire starts past this ground instead of repeating it.

**Consumer-side FIX shipped instead** (neutralizes the false-positive class regardless
of who the writer turns out to be -- defense in depth, matches this repo's own
"broker/source-of-truth over single-signal-trust" discipline): `twin_sentinel.py`'s
`evaluate_tick_freshness` now cross-checks a row's `ts_utc` against its `ts_et` via two
new helpers (`_row_effective_utc`, `_et_naive_to_utc_approx`, DST-aware through
`et_clock.et_offset_hours` -- never a hardcoded -4/-5, per the TZ-systemic lesson) and
substitutes the ts_et-derived UTC whenever the two disagree by >30min. `ts_et` has no
injectable override in any traced call path, so it's the more trustworthy field on a
corrupted row.

**RED-proofed:** 5 new tests in `backtest/tests/test_twin_sentinel.py` (including the
exact 07-15/08-04 row reproduced verbatim) confirmed to FAIL cleanly when the guard is
git-stashed (`AttributeError: no attribute '_row_effective_utc'`), PASS restored.
`test_twin_sentinel.py` 69/69 green. Full twin-suite regression sweep: 587/589 green --
2 pre-existing failures (`test_free_model_audit_twin_review.py::test_wired_in_real_
registry_and_end_to_end_against_the_real_sidecar`, `test_twin_gauntlet.py::
test_dry_mode_all_six_paths_pass_by_default`) confirmed via stash-and-rerun to predate
this change (fail identically with `twin_sentinel.py` stashed back to its pre-fire
state) -- **flagged, not fixed** (out of this fire's scope, no root cause established).

**Rail-4 clear (PAPER-only surface):** the crypto twin trades a PAPER Alpaca crypto
account for mechanism-validation only (never real money, never SPY/futures capital).
`twin_sentinel.py` is a read-only monitoring/judgment module -- this change touches
monitoring logic only, not `params.json`/`heartbeat_core.py`/any live order-placement
path. Guard + revert + this REVOKE report satisfy rail 4; no J pre-approval needed.

**REVOKE:** `git revert <this commit>` (2 files: `setup/scripts/twin_sentinel.py`
additive-only -- new helper functions + 2 import additions, no existing return value
changes for any row whose ts_utc/ts_et already agreed, i.e. every normal tick;
`backtest/tests/test_twin_sentinel.py` 5 new tests appended, none modified).

**9/9 queue backlog items closed** (7 CLOSED outright, 2 TRIAGED into a scoped
follow-up), 2 new well-scoped follow-ups filed (`TWIN-TS-UTC-DRIFT-PRODUCER`,
`TWIN-UPTIME-WATCHDOG`) instead of silently dropping the genuine-but-multi-session
findings.

Cost this fire: ~$7.9 (deep root-cause investigation -- 6 modules read in full,
live interpreter introspection, scheduled-task command-line verification, git-diff/pyc
staleness checks -- before landing on the consumer-side fix; RED-proof + regression
sweep + writeup).

---

## [2026-08-09] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 10tr $+29.00 ($+2.90/tr, 50.0% WR) [7d/7 day+side buckets -- 10 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 39d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 3tr $-99.00 ($-33.00/tr, 33.3% WR)
> -   WARNING CORRELATED: 2026-07-28 side=P fired in BOTH bollinger_squeeze+vwap_reclaim_failed_break -- same underlying day-call, not independent
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-08-09 ~18:30 ET] SHIP: THE REAL-BROKER LANE — futures now trades on an actual broker — REVOKE surface

**`Gamma_FuturesBrokerLane` registered and fired.** The futures lane now runs on a REAL broker
connection (Tastytrade SANDBOX, fake money), not only the local simulator.

**Why two lanes and not a switch.** The obvious move after proving the sandbox works was to flip
the default. That would have been wrong: the cert environment **wipes positions and orders every
24 hours** — fine for checking fills, disqualifying for a book of record whose journal needs
continuity. So both run the SAME deterministic tick:

| Lane | Task | Backend | Job |
|---|---|---|---|
| Book | `Gamma_FuturesTrader` | `fillsim` | persistent book of record, continuous journal |
| Parity | `Gamma_FuturesBrokerLane` | `tastytrade` | **real fills**, real acceptance, real slippage |

Same bars, same watcher fleet, same `should_take_v3`, same dollar rails — only the backend
differs. **Divergence between them IS the signal.** A simulator that quietly disagrees with the
broker is the failure mode every backtest in this repo is ultimately exposed to, and until
tonight nothing could detect it.

**🚨 Three bugs found building it — all the same family: *"it works when I run it" proves nothing
about how the scheduler runs it.***

1. The adapter reads `TT_SECRET` from `os.environ`. A scheduled task has no shell to export it
   into, so it **silently failed to authenticate while the tick still reported
   `simulated_fills: false`** — exactly how phantom `BROKER` rows enter a ledger whose entire
   interpretability rests on that column. Creds now load in-process from the gitignored
   `.env.tastytrade`, and an unconnected broker lane HOLDs with `broker_not_connected` rather
   than degrading into a half-lane.
2. Per-backend state dirs resolved from an **import-time frozen mapping**, which silently
   defeated monkeypatch isolation — the replay drill started writing into real state again, the
   same contamination bug from earlier this session wearing a different hat. `lane_paths()` now
   reads module globals at CALL time. Two leaked rows from the broken intermediate build removed.
3. The 24h wipe reads as "we lost a fill" unless something says otherwise, which would strand the
   lane in a permanent no-stack HOLD. `_reconcile_broker_reset` logs it explicitly — never
   silently — and clears the local record. It never runs on the simulator, where a disagreement
   would be a real bug in our own engine.

**Proven before registration** (CME open, cert `5WW73759`, fake money): dry run validated
(bp −$2.52) · resting order `Routed`→`Live`, cancelled clean · marketable order **FILLED** 1
`/MESU6` @ **7,772.50**, held, closed, flat · full tick `connected=true`, equity read from the
broker, GREEN live feed · scheduler fire `LastTaskResult=0`, beacon advanced.

**Guards:** `TestLaneIsolation` + `TestBrokerLaneSafety` (9 new). The parity lane's beacon is in
the freshness manifest — if it dies, the book keeps producing clean-looking SIMULATED numbers
with nothing left to check them against, and **the absence of a contradiction reads exactly like
agreement**.

**Unchanged:** live futures money is OP-0 #1 **plus** a new venue — double-gated, and not
reachable from either task's config.

**REVOKE:** `Unregister-ScheduledTask -TaskName "Gamma_FuturesBrokerLane" -Confirm:$false`
(the fillsim book lane keeps running untouched — the lanes are independent).

**⚠️ Flagged, NOT fixed (not mine):** `test_state_freshness_audit::test_fresh_file_is_green` is
flaky — it asserts the LIVE audit is GREEN, and `key-levels.json` intermittently crosses its 20m
budget while the live audit reads GREEN seconds later. Likely a mis-specified budget: the window
is declared 24/7 but `refresh_levels_intraday` only rewrites the file when there is something to
write, so age grows after hours. Produces weekend false-REDs. Pre-existing; worth a deliberate
pass on the SPY monitoring semantics rather than a drive-by edit.

---


### DEGRADED: self-check 2026-08-12T20:39:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 48 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 48x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 4 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

## Kitchen
Kitchen: alive, queue 43 pending, last cook 0 min ago, today $0.00, model=openrouter::nvidia/nemotron-3-super-120b-a12b:free

### DEGRADED: self-check 2026-08-12T21:09:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 51 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 51x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 4 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-12T21:39:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 54 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 54x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 4 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-12T22:09:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 57 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 57x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 4 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-12T22:39:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 60 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 60x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 5 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-license-monitor.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-12T23:09:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 63 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 63x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 5 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-license-monitor.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### WARN: spend-summary threshold breach
- ts: 2026-08-13T03:30:14+00:00
- date_et: 2026-08-12
- total: $820.97 (threshold $30.00)
- claude: $820.93  minimax: $0.03
- claude_sessions: 26

### DEGRADED: self-check 2026-08-12T23:39:57
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- FILL-FUNNEL RULE-BLOCKED[core:safe]: 21 ENTER refused by the risk gate (rule enforcement working, NOT a placement fault): 21x safe: 5 same-day entries already placed >= sanity cap 5 (params.max_same_day_roundtrips)
- SETTLEMENT-BLOCKED[safe]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,311.40, $3,670.40 remaining, 5 entries placed today).
- SETTLEMENT-BLOCKED[bold]: 5/5 same-day entries used (sanity cap reached) -- pdt_gate_mode=cash_settlement would refuse the next entry (SOD settled $5,212.94, $3,207.94 remaining, 5 entries placed today).
- TRENDLINE-DRAW never marked today (2026-08-12) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-12 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-12.log shows 66 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 66x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-12.log shows 5 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-conductor.ps1 (exit=[1], 2x), run-kitchen-reviewer.ps1 (exit=[1], 1x), run-license-monitor.ps1 (exit=[1], 1x), run-scout-premarket.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T01:39:56
- CANDIDATES-UNTRACKED: 21 untracked files under strategy/candidates/ (threshold 20) -- live chef/kitchen/prospector pipeline state accumulating with no commit history / no disk-loss recovery path. Batch `git add --pathspec-from-file` + commit to clear (see STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22).

### DEGRADED: self-check 2026-08-13T02:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 1x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T02:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 4 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 4x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T03:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 7 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 7x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T03:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 10 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 10x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T04:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 13 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 13x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T04:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 16 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 16x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T05:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 19 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 19x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T05:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 22 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 22x). Check the named script's own stderr log for the real cause.

- [2026-08-13 04:00:02] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-08-13 04:00:02] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-08-13 04:00:02] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-08-13.md

### DEGRADED: self-check 2026-08-13T06:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 25 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 25x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T06:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 28 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 28x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T07:09:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 31 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 31x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T07:39:56
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 34 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 34x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T08:09:56
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 37 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 37x). Check the named script's own stderr log for the real cause.

### BROKEN: premarket 2026-08-13
- PREMARKET SILENT FAILURE: claude exit=1 but today-bias.date=2026-08-12 != today 2026-08-13 (no fresh bias written). Engine would open on a STALE bias.


### DEGRADED: premarket 2026-08-13
- PREMARKET DEGRADED: deterministic fallback covered for the failed LLM step (today-bias.date=2026-08-12 != today 2026-08-13 (no fresh bias written). Engine would open on a STALE bias.)


### DEGRADED: self-check 2026-08-13T08:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 40 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 40x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T09:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 43 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 43x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T09:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T10:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T10:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.

### DEGRADED: self-check 2026-08-13T11:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T11:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T12:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T12:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T13:09:56
- BROKER UNREACHABLE: bold-2 TimeoutError (network/timeout -- likely transient).
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T13:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T14:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T14:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T15:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-13T15:39:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 2 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x), run-kitchen-seeder.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-08-13T20:00:41+00:00
- task: eod-summary
- date_et: 2026-08-13
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

## Known broken
- [2026-08-13T16:07:55 ET] shadow_signal_audit: newly ORPHANED/DRIFTED: confluence_zones. A detector produces output no decision path consumes (C7 at architecture scale). See analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md.

### DEGRADED: self-check 2026-08-13T16:09:56
- PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).
- TRENDLINE-DRAW never marked today (2026-08-13) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- SCOUT STALE: scout_output.json generated_at='2026-08-11T09:30:04Z' for_session_date='2026-08-11', today=2026-08-13 -- Gamma_ScoutPremarket did not refresh today (task LastTaskResult can read 0 even when the agent produced nothing new -- exit-code success is not evidence here). Non-load-bearing (addendum only); run-scout-premarket.ps1 to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-13.log shows 45 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 45x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-13.log shows 2 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-kitchen-reviewer.ps1 (exit=[1], 1x), run-kitchen-seeder.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.
