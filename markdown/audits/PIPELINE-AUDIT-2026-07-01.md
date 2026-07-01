# Full-Pipeline Audit — 2026-07-01 (evening)

> Commissioned by J: "audit the entire pipeline from free swarm theorization → kitchen → winners → engine mapping → Alpaca." 7-agent evidence-based recon (1.26M tokens, 264 tool calls), every claim verified against live state/code/logs, not docs. Companion to the 2026-06-30 adversarial audit ("rig never traded"; motion-vs-function disease).

## Executive summary

**The pipeline is broken at every single handoff — but the failure map is now exact, and it is smaller than it looks.** The research side genuinely produces (8,835 grid combos, ~18k stress runs, ~745 kitchen candidates, 16 FDR-significant edge groups in 30 days) and the engine genuinely ticks (766 decisions today, stable since the 06-25 deterministic rebuild). What's missing is the middle: **no automated handoff between research and engine has ever completed once.** Meanwhile the one strategy that CAN trade fires so rarely (or so late) that the rig has ~2 engine fills lifetime on the core accounts.

**The buried good news: today at 11:22 ET the rig completed its first-ever engine-driven end-to-end round trips** — 4 fleet arms placed marketable-limit ENTER_BULL orders (fix #15 pricing), all accepted + filled by 11:25, exit actuator closed all 4 at 11:34 via premium_stop with accepted broker exit orders. Small losses (−$12/−$20 per arm — and the elite-bull gate that blocked the core engine from this trade was right). The see→decide→place→fill→manage→exit machinery is proven to work when a signal reaches it.

## The break map (research → engine → broker)

| # | Handoff | Status | Root cause (evidence) |
|---|---------|--------|----------------------|
| 1 | Kitchen stage5 → pipeline_promoter | **NEVER ran once; crash-looping now** | argparse argv leak: `kitchen_daemon.py:938` runs `shotgun_scalper_stage5.main()` in-process; its `parse_args(None)` reads the daemon's own `run` argv → `SystemExit(2)` escapes `except Exception` (:944) → whole daemon dies 1–7s after claiming; poison task is priority=high and self-regenerating → claimed first on every 5-min keepalive restart. 10 daemon deaths today. |
| 2 | pipeline_promoter → params.json | **Dead code** | Zero executions ever (no promote_*.json, no promoter keys in params). Even if fixed: its output key `{watcher}_stage5_cleared` is read by NOTHING, and its promotable watcher names (shotgun_scalper, sniper_level_break) have no detector/dispatcher in the engine. Stale-scorecard fallback would gate on 2026-05-16 data. |
| 3 | Validated setup → order (the keystone) | **WATCH_NOT_ARMED forever** | Execution requires `params['extra_setup_exec_armed'][setup]==True` (`heartbeat_core.py:943-949`); the key is ABSENT from both params files and NOTHING in the promotion chain writes it. vwap_continuation (J's #1 edge, n=153, +$38.3/tr, WR 76.5%) fired 15 real times → all terminated WATCH_NOT_ARMED. Playbook falsely labels it "LIVE". |
| 4 | Grinder → contender-rank → promote_keeper | **Producer dead, consumer restamping** | mass-grind-progress.jsonl frozen at 06-26 10:23; Gamma_ContenderRank (30-min) restamps byte-identical JSON with fresh dates 6 days running (verified by diff). promote_keeper re-proposes the same stale IS-only contender; no scheduled OOS check exists to clear proposals (`eval_bar_cleared` flips only by hand — happened once, badly: pk-2026-06-28-001). |
| 5 | Kitchen reviewer → leaderboard | **Hallucinated gate, no consumer** | 7/7 recent auto-promotions cleared the OP-16 floor on the literal LLM string "inferred edge_capture=$25000"; `_LEADERBOARD.md` is read by zero production code. |
| 6 | Discovery FDR / design-swarm / stress-swarm | **No consumers at all** | fdr-screen.json (16 significant edge groups, 06-29), design-swarm latest.json, stress ledger (19×960 runs): OP-32's "FDR → real-fills → arm" chain is prose-only; one-shot manual runs, no scheduled task, nothing reads the outputs. |
| 7 | params.json → engine behavior | **Dozens of ratified keys silently ignored** | heartbeat_core reads only ~36 keys. Dead: `entry_no_trade_after_et` 15:00 (→ today's 10 ENTER_BEAR at 15:51-15:55, all PLACE_FAIL "expires soon"), Bold's premium stops −7%/−5% (hardcoded −50%), `block_elite_bull_vix_low/high` (GATE_KEYS omission → block at ALL VIX), `vix_entry_thresholds.bull_hard_cap`, strike/sizing tiers, macro vetoes, liquidity gates, `v15_profit_lock_mode` (the one auto-promoted change ever = behaviorally inert; live exits come from hardcoded fleet RIBBON_RIDE registry). Ratifications were lost in the 06-25 LLM→deterministic port; nothing reconciles params against actual consumers. |
| 8 | ENTER verdict → fill (core accounts) | **Still unproven post-#15** | Placement tries bracket → OTO (two guaranteed 422s "complex orders not supported for options") → simple. Core accounts' only post-fix attempts were 15:51-15:55 (inside Alpaca's 0DTE cutoff) → 10 PLACE_FAIL. **Fleet path proved #15 works** (4 fills 11:22). |

## Strategy inventory (16 families audited)

- **Can reach an order today:** BEARISH_REJECTION_RIDE_THE_RIBBON only (22 ENTER lifetime, 2 engine fills, today's 10 all late+rejected). BULLISH_RECLAIM wired but 0 ENTER lifetime — all 3 unblock levers audited and correctly closed (elite block KEEP; min_triggers FAILS_WALK_FORWARD on full history; sequence_reclaim dead-coupled).
- **Validated-positive but stuck at the exec-arm wall:** vwap_continuation (strongest scorecard on file; closest-to-armable — needs ONE params key + the recency-RED call), vwap_reclaim_failed_break (OOS +$72/tr), vix_regime_dayside (OOS +$79/tr; also needs vix_intraday feed), double_bottom_base_quiet (enable key never created — invisible even to WATCH).
- **Validated-positive with NO wiring at all:** bollinger_squeeze (WF 1.43 OOS>IS, n=303), vwap_pullback (+$64.77/tr, "SHIPPABLE" since 06-21), ORB_RETEST_LONG (WF PASS, WR 81%), NLWB (promotion never completed).
- **Contested/dead:** gap_and_go (06-28 re-run: 0 robust cells; also its feed is broken — 100% SKIP_NO_FEED today — and its `side` knob is dead in dispatch), range-scalp DIES_ON_SLIPPAGE, ~64 premium-axis families dead (C3), GEX ideas calendar-gated (~8/60-90 days banked).
- Three disjoint hardcoded strategy menus (engine_cli literals / setup_dispatch 5-tuple / fleet 2-entry REGISTRY); adding any new family = hand-editing code. No automated path from analysis/recommendations/ into any of them.

## What actually crashes (J: "crashing all the time")

The trading core does NOT crash (full-session ticks daily since 06-26, zero heals). The periphery does, loudly:
1. **TradingView/CDP** — watchdog kill+relaunched 16× today (3 mid-RTH full process deaths), 40× on 06-29; relaunches don't stick. (Engine survives via sight beacon — TV crashes no longer blind it.)
2. **Kitchen daemon** — crash-looping right now (break #1). kitchen-status.json hardcodes `daemon_alive:true` at write time → GREEN while dead.
3. **watcher_grader** — same KeyError 'direction' (runner.py:483) 3 trading days straight; 362/584 observations ungraded; scheduler shows LastTaskResult=0 (wrapper swallows exit 1).
4. **Premarket LLM tick** — tree-killed at 540s on 07-01 (stale bias all morning), silent exit-0 fail 06-30.
5. **Discord bridge/watcher daemons** — bridge dead ~90 min this afternoon; trade-watcher restarted 3× today.
6. Dead scheduled tasks: Gamma_Grind_all (0x41306, dead since 06-25), Gamma_Grind_Vwap (never ran — dark one-time-trigger), Funnel_0..5 (dead since 06-26).
7. Noise burying signal: crypto drift RED spams STATUS.md every 30 min; PS 5.1 `-NoNewline` error every 5 min from crypto keepalive.

## Why the autonomy loop never fixed this (the "missing puzzle piece")

The loop functions exactly as designed — and the design points away from trading:
1. **Reward function has no trading-function field**: conductor_outcome counts items-drained/lessons/tests. A fire adding 41 tests scores like one making an order fill. 0 of the last 30 fires touched order placement, entry reachability, or exit execution.
2. **Rail-4 + Stage-1 skip rule**: params/heartbeat/filters/orders are propose-only AND the conductor is told to SKIP such items → effort flows to guards/lessons/probes (the only freely-shippable surface).
3. **task_scorer bugs bury J's own directives**: `depends:none (annotation)` parses as a real dependency → J's 06-24 HIGH items (RIBBON-LAG trigger, POSITION-MONITOR-1MIN, TRAILING-STOP-WIRING, DYNAMIC-EXIT-LOGIC) invisible for ~7 days; EXPENSIVE_RE halves "design/research" items; QUICK_WIN_RE bonuses doc-folds. Current ready list: zero trading-path items, five doc-folds.
4. **The loop silences its own function alarms**: "ENGINE CANNOT ENTER" RED → reclassified GREEN (5de3e73); the sequence_reclaim structural defect → pinned by a guard instead of fixed (fix surface is rail-4).
5. **Disjoint backlogs**: the 06-30 audit's fix-order (#14-19) lives in the interactive TaskList; the conductor reads only queue.md/STATUS.md → the autonomy loop literally cannot see the plan.
6. **G14**: the v15.3 PRIMARY exit (ribbon-flip-back) has no live consumer (`ribbon_flip_back_fn=None`) — blocked on an unrecognized status string.
7. **11 J-gated proposals pending**, incl. the revert of the bad live params change (cd-2026-06-29-001 — tp1 0.8/fixed still live), G7 EOD-flatten activation, and an ID collision (cd-2026-06-28-002 used twice) making the approve bus ambiguous.

## Visibility layer status

Today's free-tier EOD journal claims "ENTER signals: 0" (there were 10), invents a SKIP_TV_DATA_STALE window that never happened, and omits the fleet's 4 real fills. loop-state.json shows ticks_today=0 against 766 real ticks (legacy artifact). The instruments J reads still contradict ground truth in both directions.

## Recommended fix order (draft — pending J's answers to the 4 questions asked 2026-07-01 evening)

1. **Money path first (engine → fill, core accounts):** wire `entry_no_trade_after_et` into the hot path; stop attempting bracket/OTO (go straight to marketable simple limit); prove one core-account fill intraday. Add a fill-rate/function instrument (orders placed / accepted / filled per day) to self_check + glance.
2. **Arm the armable:** create `extra_setup_exec_armed` and arm vwap_continuation on Safe-2 paper (pending J's trade-bar answer); wire the missing feeds (gap_and_go prior_day_close; honor `side` knobs); add `db_base_quiet_enabled`.
3. **Reconcile params → consumers:** automated test that every params key has a live reader (kills the dead-knob class); restore the ratified keys lost in the 06-25 port (premium stops, VIX bands, entry ceiling).
4. **Fix the research bridge:** stage5 argv leak (one-line: pass `argv=[]`), promoter → a key the engine actually reads, scheduled OOS check for promote_keeper, retire the hallucinated leaderboard gate, kill the ContenderRank restamper until the grinder runs.
5. **Re-aim the autonomy loop:** add fills/trades/P&L to the outcome metric; fix task_scorer depends/regex bugs; merge backlogs (audit tasks → queue.md); adjudicate the 11 pending proposals.
6. **Crash triage:** kitchen poison pill (same as #4), watcher_grader KeyError, premarket timeout, TV watchdog stickiness, silence the noise spam.
