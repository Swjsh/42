# RECOVERED AUDIT TAIL — unknown-unknown audit wf_a6e5356c-0e7 (G10, recovered 2026-07-08)

> The 2026-07-07 unknown-unknown audit CONFIRMED 11 findings; the synthesis feed truncated after 5, leaving ~6 unread. Recovered VERBATIM from the workflow journal on disk (no re-run). Cross-ref against G1-G17 done where noted.

## Finder findings (27)

**F1. RIBBON_MOMENTUM_GATE is LIVE and blocking bear entries on Safe — doctrine believes it is DISABLED (0 != None); the gate was explicitly reverted as HARMFUL**
- severity: CRITICAL
- evidence: The claim is FALSE — 0 arms the gate. backtest/lib/engine/gates.py:322 `_rmom_thresh = params.get("min_ribbon_momentum_cents", None)`; line 323 `if _rmom_thresh is not None and ctx.bar_idx >= 3:` — 0 is `not None`, so the gate ARMS. Line 327 `if _rmom < _rmom_thresh:` fires SKIP when the 3-bar ribbon-spread change is negative (contracting). heartbeat_core.py:125-133 lists `min_ribbon_momentum_cent

**F2. structure_veto (Claude-invented directional gate) is armed live on Safe with thin, non-OOS evidence — same shape as the deleted re-entry-lock scar**
- severity: MED
- evidence: Provenance is Claude-invented (not J-directed) and evidence is thin/non-OOS. Scorecard analysis/recommendations/structure-veto-ab-2026-06-26.json: `"wrong_way_removed_full": 2`, `"removed_losers_full": 2`, `"oos_delta_pnl": 0.0`, `"full_delta_pnl": 582.9` — the ENTIRE benefit is 2 trades removed in 2025Q1 train (`"2025Q1": {"delta_pnl": 573.9, "removed_trades": 2}`), with ZERO OOS improvement acro

**F3. Combined Safe-2 ATM book is RED (recent exp -$36.5/tr, n=14, 0 win-days) yet all 3 member setups stay armed for paper capital routing**
- severity: HIGH
- evidence: automation/state/recency-confirmation.json (run_date 2026-07-06) line 426: books.Safe2_ATM_1+2+4 "verdict": "RED", line 427 reason "recent exp $-36.5/tr NEGATIVE, n=14 >= floor 10 (clear)"; recent_window lines 404-414: n_trades 14, total_dollar -510.96, win_days 0, loss_days 7, worst_day -121.2. Its 3 members (lines 398-400: vwap_continuation/ATM, vwap_reclaim_failed_break/ATM, vix_regime_dayside/

**F4. vix_regime_dayside armed for paper on a scorecard whose validation window ends 2026-05-15 -- before the negative regime it is now losing in**
- severity: HIGH
- evidence: Scorecard analysis/recommendations/vix_regime_dayside.json (run_date 2026-06-21) line 21: "last real-fill 2026-05-15 (data load capped at 2026-05-15). ~14d real-fills blind spot exists from 2026-05-29 to 2026-06-18 but is NOT reached by this run"; line 22 opra_blind_spot_assert last_fill_date 2026-05-15. The arming doc params._j_vix_dayside_armed_2026_07_01 cites "OOS +$79.49/tr n=21" as the ship 

**F5. double_bottom_base_quiet and bollinger_squeeze are armed for paper capital with NO recency-confirmation entry at all**
- severity: MED
- evidence: automation/state/recency-confirmation.json edges block tracks ONLY ['vwap_continuation','vwap_reclaim_failed_break','vix_regime_dayside'] (lines 51, 219, 329) -- double_bottom_base_quiet and bollinger_squeeze are absent from edges and from every book (books members lines 398-400 and 433-435 list none of them). Yet both are armed: params.json extra_setup_exec_armed.double_bottom_base_quiet = true a

**F6. Core-account exit shape diverges from the logged plan AND from CLAUDE.md v15.3 doctrine — plain ribbon entries are managed at tp1 +150% / stop -20%, not the +75%/-50% the ledger advertises**
- severity: HIGH
- evidence: heartbeat_core.py:1009-1012 registers the exit_shape for a plain (non-override) core entry from strategies.by_name('ribbon_ride').exit.to_dict(), which I ran live and returns {'premium_stop_pct': -0.2, 'tp1_premium_pct': 1.5, 'profit_lock_mode': 'fixed', 'trail_pct': 0.125, 'runner_target_pct': 2.5}. So the ENFORCED exit is tp1 +150% / stop -20% / profit_lock_mode='fixed'. Confirmed live: the bold

**F7. Exit engine re-fires a full-size market SELL_ALL every tick while the prior exit order is still pending_new — 5 duplicate market sells placed on one 3-lot position (07-06)**
- severity: MED
- evidence: exit_actuator.py:124-146 loops states, and for any position with broker.get_position_qty>0 (line 125-131) it calls em.plan_exit_actions and executes the resulting SELL_ALL via broker.market_sell (line 146) with NO check for an already-open sell order on that symbol. fleet_broker.market_sell (fleet_broker.py:292-304) has no in-flight dedup either. Live proof: SPY260706P00750000 (safe) got a ribbon_

**F8. Positions not registered via register_entry are completely unmanaged — manage_tick only iterates the persisted exit-state, never reconciles against broker positions**
- severity: MED
- evidence: exit_actuator.manage_tick (exit_actuator.py:119-124) does states=load_states(arm_id); if not states: return []; and iterates ONLY states.items(). A grep of exit_actuator.py for get_positions/open_spy_option_positions/reconcile/orphan returned no matches — there is no broker-position reconciliation. Registration only happens in _execute on a PLACED core/extra entry (heartbeat_core.py:1019-1020), wr

**F9. Live exit engine ignores params time_stop_et=15:40; hardcoded 15:50 rides 10 extra min of theta**
- severity: HIGH
- evidence: automation/state/params.json:31 `"time_stop_et": "15:40"` and :32 `"time_stop_minutes_before_close": 20`. But automation/state/fleet/exit_manager.py:39 `TIME_STOP_ET = _time(15, 50)` and :195 `time_stop_now = now_et >= time_stop_et` where plan_exit_actions(...:166) defaults `time_stop_et: _time = TIME_STOP_ET`. The live caller exit_actuator.py:139-140 `dec = em.plan_exit_actions(st, best_premium=.

**F10. Core ribbon entry's stop is hardcoded -0.20 / -0.50, never reads ratified params premium_stop_pct=-0.5**
- severity: HIGH
- evidence: For a core ribbon entry setup_name='BEARISH_REJECTION_RIDE_THE_RIBBON', heartbeat_core.py `_SETUP_EXIT_OVERRIDES` (816-831) has NO entry -> `_xov is None`, so :953 `_stop_pct = ... else -0.50` (a hardcoded literal, not params.get('premium_stop_pct')), and the registered exit shape at :1010-1012 `_s = _strat.by_name('ribbon_ride'); _shape = _s.exit.to_dict()` pulls strategies.py:70 `ExitShape(premi

**F11. Ratified profit-lock knobs (trail 0.125, arm 0.05, mode) unread on live core path; ExitShape hardcodes them**
- severity: MED
- evidence: On the core ribbon path the exit shape comes from strategies.py:70 ExitShape whose profit-lock fields are class DEFAULTS (strategies.py:35-37 `runner_target_pct=2.5, trail_pct=0.125, profit_lock_arm_pct=0.05`) with `profit_lock_mode='fixed'` — hardcoded, not read from params. Grep for v15_profit_lock_trail_pct / v15_profit_lock_threshold_pct / runner_max_premium_pct across the live consumer surfac

**F12. max_premium_per_contract=3.3 (VALIDATED status) has zero live reader — only %-based cap is enforced**
- severity: MED
- evidence: automation/state/params.json:44 `"max_premium_per_contract": 3.3`. Repo-wide grep (worktrees excluded) finds it only in params files, backtest/lib/contracts/models.py (a dataclass field declaration, not applied), a B9 rescore autoresearch script, and archived backtest metadata — NEVER in heartbeat_core.py, risk_gate.py, or the order path. risk_gate.check_order enforces per_trade_risk_cap_pct and v

**F13. Liquidity gate params (delta/OI/spread/retries) confirmed dead — no order-path reader**
- severity: MED
- evidence: Grep for all six keys across the repo (worktrees excluded) hits only params.json, param-provenance.json, the crypto validator v25_filter_gates.py (a different instrument subsystem), the reconciliation test, and frozen backtest metadata — never heartbeat_core.py, fleet_broker.py, or risk_gate.py. The strike/premium selection in heartbeat_core._execute (908-932) picks strike by offset and prices via

**F14. filter_10_level_tied_required and ribbon_min_spread_cents declared in models.py but applied in no live behavior path**
- severity: LOW
- evidence: Grep in backtest/lib shows both only in backtest/lib/contracts/models.py:83-84,135-136 as dataclass FIELD declarations, plus ribbon_min_spread_cents in vwap_rejection_detector.py (a separate detector). Neither appears in orchestrator.py (grep 'filter_10_level_tied_required|ribbon_min_spread_cents' in orchestrator.py = No matches) nor in heartbeat_core's GATE_KEYS/score_params pass-through (heartbe

**F15. Expired key-level (expires_at 2026-06-30, still tier=Active) is fed to the live engine 7 days later, inside the $12 decision band**
- severity: HIGH
- evidence: automation/state/key-levels.json line 41-48: {"price": 741.61, "label": "PML_2026-06-30", "tier": "Active", "expires_at": (via _level) ... } — its expires_at is 2026-06-30T16:00 yet tier is still 'Active' and it is present in the LIVE levels array with as_of 2026-07-07. Computed check: spot_at_compute=747.49, dist(741.61)=5.88 <= 12 so it IS in-band. heartbeat_core.py:288-301 _read_levels filters 

**F16. Master SPY CSV has a ~38x IEX->SIP volume seam at 2026-03; any backtest/scorecard spanning it mixes two incompatible volume regimes**
- severity: MED
- evidence: backtest/data/spy_5m_2025-01-01_2026-06-18.csv monthly median RTH 5m volume (computed): 2026-01=11,958; 2026-02=12,534; 2026-03=483,135; 2026-04=453,296; 2026-05=311,350; 2026-06=478,182 — a ~38x discontinuity exactly at the 2026-03 boundary (IEX-thin before, full-SIP after). Confirmed live IEX vs SIP today: IEX RTH 5m median 14,358 vs SIP 409,345 = 28.5x (fetched via Alpaca REST this session).

**F17. Live SPY hot path reads thin IEX feed (28.5x below SIP); provenance risk for any absolute-volume calibration**
- severity: LOW
- evidence: heartbeat_core.py:209 `f"...&limit=600&feed=iex&adjustment=raw&sort=asc"` (also refresh_levels_intraday.py:70, sight_beacon.py:85 — all feed=iex). Live IEX RTH 5m median 14,358 vs SIP 409,345 (28.5x, fetched this session). The consuming gate is a self-relative ratio: filters.py:160 `if bar['volume'] < vol_mult * vol_baseline` and :980 same for bull — baseline and bar are both IEX, so the ratio is 

**F18. Per-tick VIX (latest bar) is joined to the SPY trigger bar (2nd-to-last, one bar older) — a ~5-10 min intra-tick skew**
- severity: LOW
- evidence: heartbeat_core.py:424-425 `trig_idx = n - 2` (trigger = 2nd-to-last SPY bar; last bar is the forward fill-confirmation bar). heartbeat_core.py:432 `vix_now, vix_prior = ... _fetch_vix()`, and _fetch_vix (line 221-233) returns yfinance ^VIX 5m Close[-1]/Close[-2] — i.e. the LATEST VIX bar, ~5-10 min NEWER than the SPY trigger bar's timestamp. The two feeds are different sources (Alpaca IEX SPY vs y

**F19. Engine placed ZERO orders today — every autonomous ENTER blocked by NOT_FLAT because the day's only real entries were placed MANUALLY, not by heartbeat_core**
- severity: CRITICAL
- evidence: core-decisions.jsonl 2026-07-07 has 18 ENTER_BEAR verdicts, and EVERY one records `action=NOT_FLAT, exec={'status':'NOT_FLAT'}, symbol=None, NO_BROKER` (10:46-14:35 safe+bold). Zero rows have exec.status=PLACED today. Meanwhile the broker (mcp__alpaca__get_orders / mcp__alpaca_aggressive__get_orders, after 2026-07-07) shows the ONLY option BUY-to-open entries carry `client_order_id: "gamma-manual-

**F20. fill_funnel reports a FALSE RED 'PLACEMENT BROKEN' today — it miscounts every NOT_FLAT skip as a failed broker placement**
- severity: HIGH
- evidence: fill_funnel.py:144 computes `attempted = bool(ex) and (kind=='core' or ...)`. A NOT_FLAT skip returns `exec={'status':'NOT_FLAT'}` (heartbeat_core.py:901) which is truthy, so attempted=True; broker.get('id') is absent so accepted=False; _evaluate (fill_funnel.py:238) then flags `attempted>0 and accepted==0` as RED 'PLACEMENT BROKEN'. Reproduced deterministically: feeding a `{'exec':{'status':'NOT_

**F21. Core-decisions PLACED rows are never reconciled to fills — broker status frozen at 'pending_new', filled_qty=0 forever**
- severity: HIGH
- evidence: All 7 lifetime engine PLACED rows show the immediate POST response only: 07-02 09:30 safe `id=38d0cb8d coid=8d58710e... bstatus=pending_new filled_qty=0`; 07-02 12:51 safe `bstatus=pending_new filled_qty=0`; 07-06 14:21 safe `pending_new`; 06-26 both `pending_new`. No later row ever updates these to filled/canceled. On 07-06, trades.csv has 8 fills all tagged `RECONCILE_FILL: recorded by EOD-flatt

**F22. gap_and_go is enabled but structurally dead — the prior-close feed key is absent from today-bias.json, so it SKIP_NO_FEEDs on 100% of ticks (2298x)**
- severity: MED
- evidence: setup_dispatch.py:499 reads prior close from today-bias.json keys `('prior_day_close','prior_close','prev_close','prior_rth_close')` (and key_levels sub-keys). Current today-bias.json (date=2026-07-07) has NONE of them: top-level keys are `['bias','bias_note','bold_equity',...,'key_levels',...,'vix_bias']` with no close, and `key_levels={resistance,support,ema_fast,ema_pivot,ema_slow,sma_50,...}` 

**F23. Today's real manual trades were never journaled to trades.csv (0 rows for 2026-07-07 despite 3 broker round-trips)**
- severity: MED
- evidence: `grep -c '^2026-07-07' journal/trades.csv` = 0. Yet the broker shows completed round-trips both accounts today: safe BUY 5x 747P @0.82 (14:00 UTC) → TP1 SELL 4x @1.2575 (14:14) → EOD SELL 1x @0.69 (19:45); bold BUY 3x 750P @2.14 → TP1 SELL 2x @3.15 → EOD SELL 1x @3.39. None of these six fills appear in trades.csv. Contrast 07-06, where EOD-flatten at least backfilled 8 RECONCILE_FILL rows — today 

**F24. Fill-funnel counts NOT_FLAT skips as failed placement attempts -> self-check pings J a FALSE 'PLACEMENT BROKEN' RED every day the engine holds a position**
- severity: HIGH
- evidence: setup/scripts/fill_funnel.py:144 `attempted = bool(ex) and (kind == "core" or ...)` treats ANY non-empty exec dict as a placement attempt. Today's core ENTER rows carry `exec = {"status": "NOT_FLAT"}` (verified in core-decisions.jsonl 2026-07-07T10:46:03 safe: `"exec": {"status": "NOT_FLAT"}`, action=NOT_FLAT) -- the engine's broker flat-check returned not-flat and it NEVER called the broker, so `

**F25. gap_and_go setup is structurally dead -- 100% SKIP_NO_FEED:prior_rth_close_unavailable for 6+ straight trading days because premarket stopped writing prior_day_close**
- severity: MED
- evidence: core-decisions.jsonl: gap_and_go fired=false with skip_reason 'SKIP_NO_FEED:prior_rth_close_unavailable' on all 386 safe ticks 2026-07-07 (and blocked 378-386 ticks/day every day 06-30..07-07, 0 fires ever). Root cause quoted in setup_dispatch.py:497-499: '_get_prior_rth_close' reads today-bias.json keys ('prior_day_close','prior_close','prev_close',...) and the comment warns 'it MUST be in this l

**F26. crypto-regression task fires green (scheduler 0x0) while v53_setup_dispatch.live has failed 191 consecutive fires at 0% pass**
- severity: LOW
- evidence: crypto/data/scorecards/drift_report.json (generated 2026-07-07T21:27:26Z) reports `consecutive_fail_streak: 191` (was 91-92 on 07-03 per STATUS.md:503-514, now 191). automation/state/logs/crypto-regression-2026-07-07.log: 'runner exit=1 ... crypto-regression FAIL (exit=1)' -- yet Get-ScheduledTaskInfo shows Gamma_CryptoRegression LastResult 0x0 (wrapper swallows the runner's exit=1). Stage v53_set

**F27. Macro/news calendar silently stale 23 days -- premarket bias runs on a stale event calendar; weekly-review producing no dated log since Jun 28**
- severity: LOW
- evidence: automation/state/macro-calendar.json last written 2026-06-14 (23 days stale; STATUS.md:21 flags 'Macro calendar STALE 22 days ... threshold 7 ... Sunday weekly-review has silently failed for 3+ weeks running'). automation/state/logs/ has weekly-review dated logs only through weekly-review-2026-W26.log (Jun 28) -- no W27/W28 despite Gamma_WeeklyReview LastRun 7/6 result 0x0.

## Verifier verdicts (12)

**V1. verdict=CONFIRMED severity=MED**
- All four links reproduced from primary sources against the LIVE core engine (Gamma_HeartbeatCore -> setup/scripts/heartbeat_core.py, per SCHEDULED-TASKS.md:71 and run-heartbeat-core.ps1:28; heartbeat_core does NOT import fast_path_executor -- grep no matches -- so its own _execute at :842 is the path).

LINK 1 (core entry has no override): heartbeat_core.py:905-906 sets setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON"/"BULLISH_RECLAIM_RIDE_THE_RIBBON". _SETUP_EXIT_OVERRIDES (:816-831) contains ONL

**V2. verdict=CONFIRMED severity=HIGH**
- SCORECARD (stale window): analysis/recommendations/vix_regime_dayside.json:6 "run_date":"2026-06-21"; :7 "hard-windowed via data load to 2026-05-15"; :21 "last real-fill 2026-05-15 (data load capped at 2026-05-15; ~14d real-fills blind spot exists from 2026-05-29 to 2026-06-18 but is NOT reached by this run)"; :22 opra_blind_spot_assert last_fill_date "2026-05-15"; :28 oos_2026 {n:21, exp_dollar:79.49, sign POSITIVE}; :77-78 VERDICT "SHIPPABLE", shippable true.
ARMED ON THAT BASIS: automation/st

**V3. verdict=CONFIRMED severity=HIGH**
- Independently reproduced from primary sources; ET now = 2026-07-07T17:54 (PowerShell, not Bash TZ), matching key-levels.json as_of 2026-07-07T17:53:36-04:00.

LINK 1 (code exists, no expiry check): setup/scripts/heartbeat_core.py:288-301 `_read_levels` — line 295 is the ONLY filter: `if isinstance(p,(int,float)) and abs(p - spy) <= 12: active.append(round(float(p),2))`. No expires_at, no date, no tier check. grep for expires_at/expired/expiry in heartbeat_core.py returns only the OCC option-symb

**V4. verdict=CONFIRMED severity=MED**
- Every cited link independently reproduced from primary source.

1. PARAMS (the "ratified" knob): automation/state/params.json:31 `"time_stop_et": "15:40"` and :32 `"time_stop_minutes_before_close": 20`. Documented as live doctrine, not a sweep artifact: :16 `_exits_section` says "...+ 15:40 time stop... Time stop 15:40 ET (L110)"; markdown/research/J-PARAM-TWEAKS.md:103 "NONE — keep `time_stop_et = 15:40`."

2. HARDCODED LIVE DEFAULT: automation/state/fleet/exit_manager.py:39 `TIME_STOP_ET = _ti

**V5. verdict=CONFIRMED severity=HIGH**
- Chain reproduced to the 4th link from primary sources:

(1) CODE — setup/scripts/fill_funnel.py:144: `attempted = bool(ex) and (kind == "core" or str(ex.get("mode", "LIVE")).upper() == "LIVE")`. For a core ENTER row, `exec={"status":"NOT_FLAT"}` makes `bool(ex)` True and kind=="core", so it is counted as an attempt. There is NO exclusion of NOT_FLAT (contrast SKIP_LATE_ENTRY which carries exec=null → bool(ex) False → NOT_ATTEMPTED). fill_funnel.py:88-91: empty `broker` → `_fail_reason` returns "

**V6. verdict=CONFIRMED severity=MED**
- All cited primary sources reproduced verbatim and the routing chain traced to placement.

1. recency-confirmation.json (run_date 2026-07-06, line 3): book "Safe2_ATM_1+2+4" (L394) members vwap_continuation/ATM, vwap_reclaim_failed_break/ATM, vix_regime_dayside/ATM (L399-401); recent_window n_trades 14, total_dollar -510.96, win_days 0, loss_days 7, worst_day -121.2, sign NEGATIVE (L404-413); "verdict": "RED" (L426), reason "recent exp $-36.5/tr NEGATIVE, n=14 >= floor 10 (clear)" (L427). Gate to

**V7. verdict=CONFIRMED severity=MED**
- Reproduced end-to-end from primary sources.

CODE: setup/scripts/fill_funnel.py:144 `attempted = bool(ex) and (kind == "core" or str(ex.get("mode","LIVE")).upper()=="LIVE")` — for core rows `attempted` is just `bool(ex)`, no check that ex.status is a real placement outcome. Line 149 `accepted = bool(broker.get("id"))`. Line 152 appends `_fail_reason(broker)` -> "no broker response recorded" (fill_funnel.py:91). _evaluate line 238 `if a["attempted"]>0 and a["accepted"]==0:` -> line 249-251 sets r

**V8. verdict=CONFIRMED severity=HIGH**
- Every link reproduced from primary sources.

(1) MECHANISM — 0 arms the gate: backtest/lib/engine/gates.py:322 `_rmom_thresh = params.get("min_ribbon_momentum_cents", None)`; :323 `if _rmom_thresh is not None and ctx.bar_idx >= 3:`; :327 `if _rmom < _rmom_thresh:` → :328 `return GateBlock("min_ribbon_momentum_cents", "SKIP_RIBBON_MOMENTUM_GATE", ...)`. 0 is not None → gate ARMS. With thresh=0, SKIP fires when the 3-bar ribbon spread change `_rmom < 0` (spread contracted).

(2) LIVE PARAMS = 0: a

**V9. verdict=CONFIRMED severity=HIGH**
- Independently reproduced from primary sources on 2026-07-07.

1) core-decisions.jsonl (automation/state/core-decisions.jsonl, 772 rows for 2026-07-07): 18 ENTER_BEAR verdicts. Parsed all 18: 13 action=NOT_FLAT exec={'status':'NOT_FLAT'} symbol=None (safe 10:46-10:50 ET; bold 12:11-14:35 ET) + 5 action=SKIP_LATE_ENTRY exec=None (safe 15:46-15:50 ET). Across ALL 772 rows for today the action tally is {HOLD:702, SKIP_ELITE_BULL_LEVEL_RECLAIM:4, NOT_FLAT:13, SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY:25, S

**V10. verdict=CONFIRMED severity=HIGH**
- Every load-bearing claim independently reproduced from primary sources. (File path in the finding was `automation/prompts/heartbeat_core.py`; the real live file is `setup/scripts/heartbeat_core.py` — confirmed as the file `Gamma_HeartbeatCore` runs via automation/state/SCHEDULED-TASKS.md:71 and run-heartbeat-core.ps1. Line numbers match.)

1) THE PLAN LOGS PARAMS-DERIVED tp/stop, cosmetically. setup/scripts/heartbeat_core.py:950-957 — for a plain ribbon entry `_xov = _SETUP_EXIT_OVERRIDES.get("b

**V11. verdict=CONFIRMED severity=HIGH**
- Core-decisions PLACED entry rows are frozen at the immediate POST response and never reconciled to fills; independently reproduced from primary sources.

CODE (defect mechanism): heartbeat_core.py:979 `plan["status"] = "PLACED" if not res.get("_error") and not res.get("_refused") else "PLACE_FAIL"` — status is set from the POST response ONLY; line 980 `plan["broker"] = res` stores the raw POST body. No poll follows: `grep poll_fill/get_order_by_id setup/scripts/heartbeat_core.py` returns NOTHING

**V12. verdict=? severity=?**
- (truncation note) The findings JSON was truncated mid-fifth-item (time_stop_et defect), and the PLAUSIBLE/unverified sections never arrived. I'll synthesize from the four fully-verified CONFIRMED items plus the fifth (whose evidence block is complete enough to rank), and flag the missing tail explicitly rather than invent it.

---

# AUDIT BRIEF — unknown-unknowns hunt, 2026-07-07

**Decision question: what's silen


---

## Status cross-ref (recovered 2026-07-08, loop G10)

**Already addressed (this loop or prior fixes):**
- F9 (time_stop_et 15:40 ignored) — SHIPPED, exit_actuator FIX 2026-07-07.
- F16/F17 (IEX->SIP 38x volume seam / thin live feed) — LINKED to D-SIP ($99/mo, verified G15).
- F19/F24 (NOT_FLAT blocks ENTER + false PLACEMENT-BROKEN) — KNOWN (manual-coexistence; FIX4 memory).
- F21 (PLACED rows never reconciled to fills) — CONFIRMED + now standing-MONITORED by G9 (0 reconciled fills across all arms).

**NEW — queued to queue.md Active backlog (not fixed tonight):**
- **F1 (CRITICAL, VERIFIED LIVE 2026-07-08):** `min_ribbon_momentum_cents=0` in Safe params ARMS the RIBBON_MOMENTUM_GATE (gates.py:322 `is not None` — 0 != None), blocking entries whenever the 3-bar ribbon spread contracts. Intended-off (0) but code needs `null` for off. Strong KILL candidate ("reverted as harmful"); recommended fix 0->null completes the intended revert. **Entry-path -> A/B or J nod first.**
- F2 (structure_veto armed on thin non-OOS evidence — gate provenance), F3 (Safe-2 ATM book RED -$36.5/tr yet 3 setups stay armed — disarm review), F7 (exit engine re-fires SELL_ALL every tick while pending_new), F26 (v53_setup_dispatch 191 consecutive failed fires while scheduler shows green), F23/F27 (manual trades unjournaled / macro calendar stale 23d).

Full verbatim finder + verifier text above. This recovery cost ONE disk read (no workflow re-run).
