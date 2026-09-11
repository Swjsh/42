# SWARM CONSULT: AUDIT -- Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engin

**Filed:** 2026-08-30T00:20:38 ET
**Mode:** `audit`
**Cost:** $0.0000
**Elapsed:** 68.4s
**Perspectives:** 1 / 5 succeeded

## Question

Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT. Be specific; avoid generic advice.

## Context (provided)

```
RECENT STATUS (top):
## [2026-08-29T12:21 ET] risk-gate: OK — PREREG-TIGHT-LADDER-2026-08-28 5 controls shipped (max 5 contracts, $1,000/position, skip-conflict, 4 entries/day, -$400 daily stop), commit `4245d4ce`

**Picked because the tight-ladder forward window opens 2026-09-01 09:30 ET and the prereg it's measured against described controls the engine did not enforce — a pre-registration describing controls the engine lacks is worthless. Clock verified `2026-08-29 12:21:51 Saturday EDT market_hours=False` (`et_clock.py`) before touching anything. PAPER ONLY — no live arming, no secret rotation.**

**Blast radius (grep-verified, not assumed):** `max_same_day_roundtrips` consumers traced to `risk_gate.check_settlement`, fed a REAL per-arm daily count from `settlement_ledger.get_settlement_status` (`len(ledger entries)`, not a stub) on BOTH the core path (`heartbeat_core._execute` → `check_order`'s cash_settlement branch, `pdt_gate_mode=cash_settlement` on both core files) and the fleet path (`fleet_executor.finalize` → `check_settlement` directly, gated by `fleet_settlement_gate_enabled=true`, confirmed true in both params files). Found `check_daily_premium_budget` (2026-08-28) is a DIFFERENT, currently-shadow-only mechanism (`loss-armed-budget-forward-prereg-2026-08-28.json`, its own forward window opens the SAME day as this ship) — did NOT arm `daily_premium_budget_dollars`/`_pct_of_equity`, which would have silently graduated that separate experiment out of shadow mid-window. The new `-$400` dollar-loss trigger reuses `equity_f`/`start_of_day_equity_f` (already-mandatory, already-validated on every existing `check_order` caller) instead of the unwired `realized_pnl_today` kwarg, so arming it needed zero new caller plumbing and cannot newly deny every order the way a fresh required kwarg would. Traced the qty pipeline in `fleet_executor.finalize` (`_qty_for` → recency/full-send clamps → NEW `cap_entry_qty` → existing `_shrink_qty_to_affordable`) and `heartbeat_core._execute` (`min_contracts` → NEW `cap_entry_qty` → existing `max_affordable_qty` clamp); both existing shrink helpers already guarantee "qty >= min_contracts or 0/deadlock", and `cap_entry_qty` carries the identical invariant — composition proven (property test, 350-case sweep) to never produce qty < 3.

**Verified, quoted (OP-33):** RED-proofed via `git stash push` on just the 5 implementation files (`risk_gate.py`, `heartbeat_core.py`, `fleet_executor.py`, both params files) — `pytest backtest/tests/test_tight_ladder_controls_2026_08_29.py` → `ImportError: cannot import name 'CODE_DAILY_LOSS_DOLLARS'` (whole module fails to collect). `git stash pop` restored the fix → `394 passed`. Full regression sweep across every file touched by the qty pipeline + the fleet/core sizing test suites: `1151 passed, 1 failed` — the 1 failure (`test_arm_display_names.py`) plus 5 more in `test_six_account_routing.py` are **pre-existing, unrelated, confirmed via `git diff --stat -- accounts.json` (empty)**: yesterday's risky-3 retirement (`e4dab06e`) left those fixtures stale (still expect 3 active fleet_rest arms, now 2). OPEN, not fixed here — out of scope (account-roster subsystem, not sizing/risk). The repo's real pre-commit curated safety gate (6 suites) ran automatically on commit: `59 passed, PASS`. Fixed 5 pre-existing tests whose hardcoded expected codes were a direct, understood consequence of the new caps intercepting earlier than the old RISK_CAP/shrink-not-deny path (each documents why inline; shrink-not-deny itself stays covered by its untouched sibling test). Found and fixed a real gap while verifying: `explain_block()`'s deadlock telemetry didn't know about the two new caps (`test_deadlock_matches_check_order_over_grid` caught it) — fixed LOCALLY inside `explain_block` only, deliberately not in `max_affordable_qty`/`_effective_per_trade_cap_dollars` (19 repo-wide callers including `simulator_real.py` + several `backtest/tools/edge_matrix_*.py` research scripts — folding a live-only control in there would silently change backtest results, out of scope for this ship).

**3 worked cases, end-to-end through the real shipped params (not synthetic fixtures):** Safe (min_contracts=3): $0.75→5 contracts/$375; $2.50→4 contracts/$1,000; $4.00→SKIP. **Bold (min_contracts=5) diverges and is worth flagging**: because $1,000/5=$200/contract, Bold's OWN conflict boundary is **$2.00, not $3.33** — $2.50 premium is ALSO a SKIP for Bold, not 4 contracts. Same $1,000/5-contract values shipped to both accounts per spec; the boundary is naturally tighter wherever min_contracts is higher.

**Historical bind rate, quantified (not assumed) per the coordinator's ask:** independently checked `journal/trades.csv` (`entry_px`, clean account_id rows, n=517): premium > $2.00 (Bold's real conflict boundary) hit **3.0% of Bold-side fills (5/164)**, 0.4% Safe-side; **0.0% of either side ever exceeded $3.33** (max seen: $3.14 safe / $2.37 bold) — confirms the prereg's own "conflict never yet occurred" but reveals Bold's tighter effective boundary would have bound a real, non-trivial ~3% of its own history, not 0%. The -$400 daily stop's "9 times in 42 days" figure is the prereg's own (Addendum 2 S2.4) — cited, not independently re-derived this session (time budget; the position-cap figures above ARE independently verified). Max-contracts/max-position-dollars will otherwise rarely bind at current ($5K-ish) equity — weighted verification effort toward the daily-stop mechanism accordingly, per the coordinator's note.

**Coordination check (mid-task, verified before proceeding — not taken on faith):** independently confirmed commit `d6f55f7a`, `analysis/deep-research/FABLE-FULL-REVIEW-2026-08-29.md` (entry directly above this one), and `queue.md`'s `SAFE-2-EXIT-SHAPE-AB-PREREG` (status:pending) all exist exactly as described, including the literal freeze language ("no trading-path changes except pre-registered kill-type risk reductions"). This ship IS that sanctioned category and IS pre-registered (`PREREG-TIGHT-LADDER-2026-08-28.md`) — lands 2026-08-29 (today), before Monday 08-31 open, before the freeze. **Zero key overlap with SAFE-2-EXIT-SHAPE-AB-PREREG**: that item touches `tp1_premium_pct`/`stop_mode` via `exit_patch` on safe-2; this ship touches `max_contracts_per_entry`/`max_position_dollars`/`max_same_day_roundtrips`/`daily_loss_kill_switch_dollars` — disjoint, and per the original task scope the exit ladder (rungs, TP1, trail, structure stop, catastrophe cap) was never touched.

**Revert (any single key, byte-identical; each key's own `_doc` field in both params files repeats this):** delete `max_contracts_per_entry` / `max_position_dollars` / `daily_loss_kill_switch_dollars`, or set `max_same_day_roundtrips` back to `5`, in `automation/state/params.json` and `automation/state/aggressive/params.json`. Full revert: `git revert 4245d4ce` (11 files, no registered task to unwind, nothing else depends on the new codes/function existing).

**OPEN for J:** none — paper-only, sanctioned, pre-registered, no live/secret/irreversible action. **OPEN, not handled (flagged, not spawned as a chip per standing correction — J doesn't click those):** the 6 pre-existing `test_six_account_routing.py`/`test_arm_display_names.py` failures from yesterday's risky-3 retirement (accounts.json fixtures now stale) — self-contained, unrelated to this ship, next session picks up.

**Rail 4 (paper trading-path code + config edited — risk_gate.py/heartbeat_core.py/fleet_executor.py/params.json/aggressive/params.json — a real behavior change, guard+revert+REVOKE per standing paper-autonomy authorization):** guards are the RED/GREEN proof + 1151-test regression sweep + 59/59 curated safety gate above (a); revert is `git revert 4245d4ce` or any single params key above (b); this STATUS entry is the REVOKE report (c).

---

## [2026-08-29T16:34 ET] futures lane REVIVED — 2 silent outages + 1 margin exposure closed, health surface shipped, commit `587599f8`

**Entered on J: "this needs to be up and running as in proper paper trading logging full daily review and audit just like 0dte… are we wired into anything paper trading yet? by monday 100%." Judgment at Fable tier; all four implementation packages routed to Sonnet workers per §1 routing.**

**ANSWER TO THE QUESTION: yes — tastytrade SANDBOX, account `5WW73759`, ~$2,000, a real paper broker (not a simulator).** Auth re-verified live this session. Permissions were NEVER the blocker: `futures_heartbeat_core.py`'s own docstring records the 2026-08-09 end-to-end proof (dry run validated, BP effect −$2.52 · resting order Routed→**Live** · marketable order **FILLED** 1 `/MESU6` @ 7,772.50, held, closed, flat) — all while `futures_buying_power` read 0.0 and `is_futures_approved` read false, because **the cert environment simply does not populate those fields.**

**Why nothing has traded since — TWO silent outages, both reporting healthy:**
1. **fillsim book-of-record dead 15 sessions** (2026-08-14→): `is_flat()` considered only `status=="open"` while `place_bracket()` also refused on `pending_entry`, so a stale unfilled limit made the engine believe it was flat while every placement was refused. 60 `ENTER_REFUSED` rows, equity frozen at exactly $1,899.83, and `futures_eod` graded **GREEN every single day**.
2. **broker lane placed 0 of 8 armed orders** (2026-08-20→): the sandbox intermittently returns `502 Bad Gateway` + `ReadTimeout`; `place_bracket` caught the transport error and logged it through `logging.getLogger(__name__)` with **no handler configured anywhere**, so ledger rows read `placed:false` with no reason. The 3-week "H1_PERMISSIONS" story was a taxonomy bug — a bare `else` mapped ANY exception to permissions.

**MARGIN EXPOSURE closed (the one that could have cost money Monday):** the armed leg placed **qty=2 GTC brackets on a 2-session overnight horizon with no flatten path of its own**, on a $2K account — directly against `markdown/futures/MARGIN-LEVE
[truncated]
```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 36.9s, cost $0.0000_

### Consensus Points
Only Perspective 5 succeeded; Perspectives 1-4 failed due to technical errors (model unavailability, empty content, payment requirements). Thus, consensus is limited to Perspective 5's analysis, which identified these concrete gaps from the provided context:
- Futures premarket producer (Gamma_FuturesPremarket) has never fired (rc=267011, no successor)
- Futures health check (`futures_health.py`) is fail-open (returns GREEN on failure)
- `record_mistake()` has zero call sites; `journal/futures/mistakes.md` absent
- Futures missing from `go_live_gate.py` (blocks live trading path)
- Quiet mode blacks out Sunday 18:00 ET session weekly (known exemption unimplemented)
- 6 pre-existing test failures from risky-3 retirement (stale `accounts.json` fixtures)
- No live trading/secret rotation path (explicitly "PAPER ONLY")
- No unified portfolio risk across 0DTE options and futures margins
- Pre-registration process appears manual (no automated validation against engine capabilities)
- Bold account's $2.00 conflict boundary binds ~3% of historical fills but isn't reflected in sizing logic

### Key Disagreements
No substantive disagreements exist since only Perspective 5 provided actionable analysis. The failures of Perspectives 1-4 were purely technical (infrastructure/access issues), not analytical divergences. Perspective 5's rigor is evidenced by:
- Direct quoting of context (e.g., "NEVER fired", "fail-open", "0 call sites")
- Tracing specific code paths and verification methods (e.g., grep-verified blast radius)
- Distinguishing between newly shipped controls and pre-existing issues
- Quantifying historical impact (3.0% bind rate for Bold account)
- Identifying scope boundaries (e.g., noting test failures are "out of scope" for the current ship)

### Synthesized Recommendation
Project Gamma's most critical autonomous gaps center on broken futures infrastructure and missing feedback loops. The system has shipped sophisticated controls (tight-ladder risk gate, health surfaces) but fails to close core operational loops: futures premarket analysis never runs, mistake recording is dead code, and health checks default to pass. This creates a dangerous illusion of safety while critical paths remain unautomated and unlearned. The operator will next point at the futures premarket producer's permanent silence (rc=267011) as evidence of neglected infrastructure, especially since the health surface was recently shipped but remains fail-open. Priority must shift from adding new controls to verifying existing ones execute and feed improvement cycles.

### Confidence in Synthesis
**6/10** - Based on 1/5 perspectives succeeding. While Perspective 5's analysis is rigorous and context-grounded, the absence of cross-perspective validation reduces confidence. The technical failures of other perspectives were unrelated to analytical quality (model access/issues), so Perspective 5's findings are likely valid, but synthesis would benefit from additional viewpoints to catch blind spots (e.g., regime detection, correlation monitoring).

### Single Most-Important Next Action
**Fix the Gamma_FuturesPremarket task to fire reliably** by:  
1. Checking why it returns rc=267011 (likely missing dependency or config error)  
2. Ensuring it has a successor task in the orchestration DAG  
3. Verifying it runs before market open (09:00 ET) to inform futures lane decisions  
*Execute today*: `grep -r "Gamma_FuturesPremarket" --include="*.py" .` to locate the task definition, then inspect its trigger conditions and error logs from the last 267k cycles.

### Watch-For Signal
**If the futures premarket producer starts firing regularly but Gamma_FuturesHealth remains fail-open**, this invalidates the synthesis that broken feedback loops are the primary gap. Instead, it would indicate the system can execute tasks but lacks proper safety validation—shifting focus to health check rigidity over task execution. Specifically, a GREEN health return during a simulated futures_health.py crash (e.g., `kill -9 $(pgrep -f futures_health)`) would confirm the fail-open flaw is critical and unrelated to premarket execution.

## Individual perspectives

### Perspective 1: `cerebras:zai-glm-4.7`

**FAILED** -- `all_lanes_failed (tried ['cerebras:zai-glm-4.7', 'meta-llama/llama-3.3-70b-instruct:free', 'qwen/qwen3-coder:free']): NotFoundError: Error code: 404 - {'error': {'message': 'This model is unavailable for free. The paid version is available now - use this slug instead: qwen/qwen3-coder', 'code': 404}, 'user_id': 'user_37luJnwxpk0HYbXnEZhUPm6TH2Q'}`

### Perspective 2: `nvidia/nemotron-3-super-120b-a12b:free`

**FAILED** -- `all_lanes_failed (tried ['nvidia/nemotron-3-super-120b-a12b:free']): empty_content`

### Perspective 3: `openai/gpt-oss-120b:free`

**FAILED** -- `all_lanes_failed (tried ['openai/gpt-oss-120b:free', 'cerebras:gpt-oss-120b']): APIStatusError: Error code: 402 - {'message': 'Payment required to access this resource. Visit your billing tab.', 'type': 'payment_required_error', 'param': 'quota', 'code': 'payment_required'}`

### Perspective 4: `google/gemma-4-31b-it:free`

**FAILED** -- `all_lanes_failed (tried ['google/gemma-4-31b-it:free', 'cerebras:gpt-oss-120b']): APIStatusError: Error code: 402 - {'message': 'Payment required to access this resource. Visit your billing tab.', 'type': 'payment_required_error', 'param': 'quota', 'code': 'payment_required'}`

### Perspective 5: `nvidia/nemotron-3-ultra-550b-a55b:free`

_Elapsed 28.9s, 4527 in / 2500 out, cost $0.0000_

Let me analyze this audit request carefully. The user is asking me to audit Project Gamma - an autonomous 0DTE SPY options trading system - for what it's "obviously missing or should already be doing autonomously." They want me to identify the top 6-8 concrete, ranked, actionable gaps.

But wait - the MODE says "AUDIT (adversarial pre-ship review)" and asks me to produce specific sections about failure modes, impacts, rule violations, etc. This seems like a template for reviewing a specific proposed change, but the actual question is asking for a general audit of the system's gaps.

Let me re-read the context. The context shows two recent status entries:
1. Risk gate controls shipped (tight ladder controls)
2. Futures lane revived - two silent outages fixed, health surface shipped

And recent commits show work on: quiet-mode, autofire, cockpit, cost meter, gamma_watcher, hooks, companion.

The question asks: "Audit Project Gamma... for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW"

But the MODE instructions say to produce sections about failure modes of a "proposed change." There's no specific proposed change here - this is a general audit request.

I think the MODE instructions are a template that was applied incorrectly, or the user wants me to audit the SYSTEM as if it were a proposed change. Given the context, I should interpret this as: audit the current state of Project Gamma based on the recent status/commits, identifying gaps.

Let me analyze what I can see from the context:

**From the risk-gate status (2026-08-29T12:21):**
- Tight ladder controls shipped: max 5 contracts, $1000/position, skip-conflict, 4 entries/day, -$400 daily stop
- Paper only, no live arming
- Pre-registration described controls the engine lacked
- 394 tests passed after fix, 1151 regression sweep (1 pre-existing failure unrelated)
- 6 pre-existing test failures from risky-3 retirement (stale fixtures)
- Historical bind rate: Bold's tighter boundary would have bound ~3% of history
- -$400 daily stop triggered "9 times in 42 days" per prereg

**From futures lane status (2026-08-29T16:34):**
- Two silent outages: fillsim book-of-record dead 15 sessions, broker lane placed 0 of 8 armed orders
- Margin exposure closed (armed leg with qty=2 GTC brackets overnight on $2K account)
- Health surface shipped: futures_health.py with 5 checks, wired into self_check.py and MAP.md/HOME.md
- Gamma_FuturesHealth task registered (30 min) and proven firing
- futures_eod now degrades YELLOW/RED on refusal sessions
- Still open: futures premarket producer (NEVER fired), post-trade autopsy (none exists), record_mistake() dead code, futures absent from go_live_gate.py, quiet mode blacks out Sunday 18:00 ET session

**From recent commits:**
- Quiet mode fixes (linger presence hold, hold blackout during fullscreen, close console leaks)
- Autofire fixes (classifier past-tense gap, second safety pass)
- Cockpit features (autofire_cards.py, goal-to-card linkage, context-alarm cards, WHAT-CHANGED digest)
- Cost meter (live cost meter)
- Gamma_watcher (command center watches itself)
- Hooks (deferral guard)
- Companion fix (card fires silent no-op)
- Army view fits one screen

Now, what is OBVIOUSLY missing? Let me think as an adversarial reviewer who knows this system:

1. **Futures premarket producer NEVER fired** - This is explicitly called out. Gamma_FuturesPremarket has NEVER fired (rc=267011, no successor). This means no premarket analysis for futures.

2. **No post-trade autopsy for futures** - Explicitly called out as "none exists"

3. **record_mistake() is dead code** - 0 call sites, journal/futures/mistakes.md absent. The learning loop is broken.

4. **Futures absent from go_live_gate.py** - Can't go live even if paper works

5. **Quiet mode blacks out Sunday 18:00 ET session open every week** - This is a known issue with a recommended fix (essential exemption for wscript chain)

6. **6 pre-existing test failures** from risky-3 retirement - stale fixtures in accounts.json, test_six_account_routing.py and test_arm_display_names.py

7. **No live trading yet** - Everything is paper only. The risk-gate status says "PAPER ONLY — no live arming, no secret rotation"

8. **Secret rotation not implemented** - Mentioned as not done

9. **The -$400 daily stop uses equity_f/start_of_day_equity_f instead of realized_pnl_today** - This is a design choice but could be a gap if equity includes unrealized

10. **Bold account's tighter boundary ($2.00 vs $3.33) binds 3% of history** - Known but not addressed

11. **Futures health is fail-open** - "fail-open" means it passes if checks fail? That's dangerous

12. **No integration between 0DTE and futures risk systems** - They seem separate

13. **No unified portfolio risk view** - SPY options and futures margins not aggregated

14. **The "self-improvement engine" - where is it?** - The context mentions "self-improvement engine" in the question but I don't see evidence of autonomous improvement

15. **No automated parameter optimization** - Parameters seem manually set/pre-registered

16. **No regime detection** - Not mentioned

17. **No correlation monitoring between strategies** - 0DTE and futures could be correlated

18. **The "queue.md" has pending items** - SAFE-2-EXIT-SHAPE-AB-PREREG is pending

19. **No kill switch for futures** - Only 0DTE has daily_loss_kill_switch_dollars

20. **Futures uses tastytrade SANDBOX with ~$2000** - Very small, not representative

21. **No automated rollover for futures contracts** - MESU6 mentioned, but what about expiration?

22. **The "gamma_watcher watches itself" but what watches gamma_watcher?** - Infinite regress

23. **No disaster recovery / backup verification** - Not mentioned

24. **No automated compliance/audit trail verification** - Only manual status entries

25. **The pre-registration system exists but seems manual** - PREREG-TIGHT-LADDER-2026-08-28.md created manually?

Let me rank the top 6-8 most critical, concrete, actionable gaps:

1. **Futures premarket producer never fired** - Critical path for futures trading, explicitly broken
2. **No post-trade autopsy for futures** - Learning loop broken, can't improve
3. **record_mistake() dead code** - Mistake recording broken for futures
4. **Futures absent from go_live_gate.py** - Blocks live trading path
5. **Quiet mode blacks out Sunday session** - Known schedule conflict, weekly
6. **6 pre-existing test failures** - Technical debt, indicates fragile test infrastructure
7. **No live trading / secret rotation** - System never validated live
8. **Futures health is fail-open** - Safety system defaults to pass
9. **No unified portfolio risk** - SPY + futures margin not aggregated
10. **No automated regime detection** - Flying blind on market conditions

But the question asks for "better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT."

Let me refine to be more specific to the codebase context:

1. **Gamma_FuturesPremarket task never fires (rc=267011)** - The premarket analysis pipeline for futures is completely dead. No successor task. This means zero premarket context for futures decisions.

2. **futures_health.py is fail-open** - "fail-open" means if the health check crashes or times out, it returns GREEN. This defeats the purpose of the health surface that was just shipped.

3. **record_mistake() has 0 call sites + journal/futures/mistakes.md absent** - The mistake recording infrastructure exists but is unwired. The self-improvement loop cannot close.

4. **Futures missing from go_live_gate.py** - The live-arming gate doesn't know futures exists. Even if paper works perfectly, cannot go live.

5. **Quiet mode blacks out Sunday 18:00 ET session** - The wscript chain exemption is documented but not implemented. Weekly recurring outage.

6. **6 pre-existing test failures from risky-3 retirement** - accounts.json fixtures stale, test_six_account_routing.py and test_arm_display_names.py failing. Indicates no automated fixture update on account roster changes.

7. **No secret rotation / live arming path** - "PAPER ONLY — no live arming, no secret rotation" explicitly called out. The entire live path is untested.

8. **No unified margin/portfolio risk across 0DTE + futures** - SPY options use cash settlement, futures use margin. No cross-asset risk aggregation. The -$400 daily stop only covers 0DTE.

9. **Pre-registration process is manual** - PREREG-TIGHT-LADDER-2026-08-28.md created by hand? No automated prereg validation against engine capabilities.

10. **Bold account's $2.00 conflict boundary binds 3% of history** - Known tighter bound not reflected in position sizing logic (only skip-conflict at $3.33).

Now, the MODE instructions ask for specific sections about a "proposed change" but this is a general audit. I think I should follow the spirit of the MODE - be adversarial, specific, rigorous - but adapt to the actual request which is a system audit.

Actually, re-reading the prompt: "Your job: identify everything that could go WRONG with the proposed change." But there IS no proposed change in the question. The question is "Audit Project Gamma... for what it is OBVIOUSLY missing."

I think the MODE block might be a copy-paste error, or the user wants me to treat the "current state" as the "proposed change" and audit it. Or perhaps the "proposed change" is implicit: the system as currently configured continuing to operate.

Given the explicit instruction "If the proposal is solid, say so plainly — don't manufacture risk" and the detailed MODE sections, I should probably produce the MODE sections but applied to the system's current trajectory/state.

But the user ALSO explicitly asked: "List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW"

These are two different output formats. The MODE says "Produce these sections in order: 1. Most likely
