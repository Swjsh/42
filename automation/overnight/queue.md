# OVERNIGHT TASK QUEUE — conductor work backlog

> Format: `- [ ] <id> (<priority>) :: <description> :: depends:<...> :: status:<pending|in_progress|blocked>`
> **OP-22 discipline:** this file holds REAL, drainable work. Machine-generated regression/harvest noise lives in `## Archived 2026-06-19` (rolled up) and verbatim in `queue-archive-2026-06-19.md`. When you finish an item, move it to `## Completed`. When you add HARVEST/REGFAIL auto-noise, it does NOT belong here unless it names a concrete, actionable engine fix.
>
> **Triaged 2026-06-19** (OP-22 compound-don't-accumulate pass): 172 stale auto-generated CRITICALs + harvest data-points archived; gym is 88/88 green (CONTEXT-107/109) so the EDGE_REGRESSION_FAIL "CRITICALs" were false alarms that nothing drains. Active backlog below is the genuinely-real remainder, ranked by leverage. Full pre-triage file preserved verbatim at `automation/overnight/queue-archive-2026-06-19.md`.

---

## Active backlog

> Ranked by leverage. Most of the deepest work is tracked in the live TaskList + `cook-queue.jsonl` (see `automation/state/cook-queue-summary.md`); items here are the conductor-visible ones that need a human-or-Claude decision or are not yet owned by another loop.

### Tier 1 — engine correctness / loose ends from tonight (CONTEXT-106..109)

> The 3 BP-* loose ends are CLOSED (2026-06-19) — see `## Completed`. STAIRSTEP-REDESIGN remains the one open Tier-1 item (genuine eval-first redesign, not a quick fix).

- [ ] STAIRSTEP-REDESIGN (MED) :: STAIRSTEP_CONTINUATION eval-first redesign — currently RETIRED 2026-06-18 (anti-J-edge; detector returns None, v45 gym PASS confirms 0 post-retirement fires). Any future promotion needs eval-first / J redesign: (1) docstring + v45 gym fixture used FABRICATED bar values (not the real 5/07 tape); (2) 5/07 is a J LOSS day; every tested logic fix worsened edge_capture. :: depends:none :: status:pending

### Tier 2 — J-ratification proposals (DRAFT, awaiting J ruling per Rule 9)

> These are NOT blocked-on-J foot-guns — they are genuine Rule-9 doctrine changes that need J's explicit call. Surface in the next brief; do not auto-ship.

- [ ] J-RULING-BOLD-KILLSWITCH (HIGH, Rule-9) :: Bold kill-switch threshold conflict: `aggressive/circuit-breaker.json` trips at **-60%** but CLAUDE.md Rule 5 + `aggressive/params.json#daily_loss_kill_switch_pct` say **-50%**. Which is canonical? (CONTEXT-107 Q1.) :: depends:none :: status:awaiting-j-ratification
- [ ] J-RULING-BOLD-STRIKE-OFFSET (MED, Rule-9) :: Bold strike offset: `aggressive/params.json#strike_offset_itm: 2` matches Safe's; `run_dual_account.py` docstring claims Safe=ATM/Bold=ITM-2. Likely stale docstring (per-tier selection happens in heartbeat) — verify intended. (CONTEXT-107 Q2.) :: depends:none :: status:awaiting-j-ratification
- [ ] HEARTBEAT-SPY-LOGGING-CLARIFICATION (LOW, Rule-9) :: heartbeat.md output format says `spy={x}` without defining whether x is `Latest.close` (v15.1 closed-bar result) or the live quote. In practice Claude logs the live/in-progress price → ~$0.50-$1.50 false divergence on HOLD ticks → audit false positives. Fix: add note `spy=Latest.close (NEVER in-progress bar / quote_get live price)`. Zero trading-logic change. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-05-WAKE-FIRE-REVIVAL (HIGH, Rule-9) :: Wake fires were paused (burned Max-plan quota). With MiniMax in place they can resume cheap. Option A (hybrid: Claude orchestrates, MiniMax generates content, ~$0.20-0.40/fire) recommended over Option B (pure-MiniMax, ~$0.05-0.15/fire, medium risk). Full proposal in archive. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-06-INTRADAY-SWARM (MED, Rule-9) :: Add `Gamma_SwarmIntraday` 12:00 ET re-run of swarm Stages 2-4 for a mid-session bias sanity check (~$0.07/fire, ~$1.50/mo). Requires OP-28 amendment (intraday swarm currently undefined). :: depends:none :: status:awaiting-j-ratification
- [ ] MM-07-VALIDATOR-MULTI-PASS (LOW, Rule-9) :: 3-pass swarm validator (technical / macro / level contrarian) instead of 1-pass devil's-advocate. ~$0.007/fire. :: depends:none :: status:awaiting-j-ratification

### Tier 3 — research items not owned by the cook-queue loop

- [ ] RIBBON-SPREAD-PER-TIER-DESIGN (MED) :: `ribbon_min_spread_cents=30` applies globally to ALL quality tiers (LEVEL/ELITE/SUPER). Hypothesis: ELITE/SUPER setups tolerate a tighter spread. Design a per-tier spread table + backtest. (Also in cook-queue, source=claude.) :: depends:none :: status:pending
- [ ] PHASE2-C1-BIAS-EMA-NULLS (MED) :: In `automation/state/today-bias.json` the fields `ema_fast`/`ema_pivot`/`ema_slow`/`sma_50` are null. Trace which script writes them + why they land null; fix the producer. (Also in cook-queue, source=gamma-steering.) :: depends:none :: status:pending
- [ ] SAFE-VIX-CONDITIONAL-SIZING (MED) :: Quality sizing (bearish_streak>=3 OR vol_ratio 1.0-1.5) failed G3 WF due to regime-dependence. Re-test the SAME criteria gated on VIX regime (NEUTRAL 17.5-22 was the profitable band per CONTEXT-103). (Also in cook-queue, context-86-followup.) :: depends:none :: status:pending
- [ ] SAFE-MULTIDAY-APPROACH-GATE (MED) :: When price within $0.30-0.50 of a multi_day level (PDH/PDL/weekly), trigger on APPROACH rather than exact touch. (Also in cook-queue, gamma-autonomous.) :: depends:none :: status:pending

### Tier 4 — long-standing low-priority carry-overs (verify still relevant before picking up)

- [ ] T60 (LOW) :: TradingView MCP J-drawn-line capture → key-levels.json (`j_drawn` source, tier=Active). :: status:pending
- [ ] T101 (MED) :: Capture ≥5 TV MCP fixtures at different bar-cycle phases for `crypto/data/fixtures/` (v13_tv_mcp_parity test cases). :: status:pending
- [ ] T102 (MED) :: Investigate v02 source-parity drift (~23% iterations disagree >0.05% Coinbase vs yfinance). Deeper diagnostic: log WHICH bar disagreed; consider Alpaca crypto as 3rd source for 2-of-3 voting. :: status:pending
- [ ] EOD-PHASE-2.2/2.3/2.4 (MED, weekend) :: EOD deep-dive remaining: tight fingerprint matching (2.2), hit-rate+expectancy via OPRA fills (2.3), real impls for 9 stub modules (2.4). Multi-day window work. :: status:pending
- [ ] SHOT-DISCORD-ALERT (LOW) :: Wire shotgun-scalper stage5 completion into `discord-watcher.py` (pattern from `check_v15_appeared()`). :: status:pending
- [ ] T24 / T25 / T16 / T17 / T106 / T107 (LOW) :: Misc one-shots: mtf_confluence spec (T24), grinder-concurrency-audit (T25), refactor sniper_evaluator (T16), verify today-bias schema (T17), full-history in-progress-leak replay (T106), per-tick chart_read replay forensic tool (T107). Verify relevance before starting — several predate the 05-23 reset. :: status:pending

---

## Archived 2026-06-19 (resolved / stale — preserved, not deleted)

> **Conservative archive.** Nothing deleted. The 172 machine-generated lines below are rolled up here; the full verbatim text of every one is preserved in `automation/overnight/queue-archive-2026-06-19.md` (1164 lines, byte-identical pre-triage copy). Resolution rationale is recorded per cluster.

### Cluster A — 62 stale HARVEST-REGFAIL / EDGE_REGRESSION_FAIL "CRITICAL" items (2026-05-30 .. 06-18)

**Verdict: ALL STALE / FALSE-ALARM. Archived.** These were auto-emitted by `gym_harvester.py` every time a single live-source-jitter validator blipped during a half-hourly regression run. Root causes, all benign:
- The bulk (passed=64/78) flagged ONLY the `KNOWN_FLAKY_LIVE_SOURCE` validators (`v02_source_parity` + `v15_three_source_parity.live`) — live Coinbase/yfinance/Alpaca BTC-bar timing jitter, NOT engine-correctness gates (per T-2026-05-17-07, runner.py carve-out). `overall_pass` already excludes them.
- The `v25_filter_gates.offline` (passed=83/84) blips were the v25 presence-guard during authoring/edit windows; gym is **88/88 green WITH replay** as of CONTEXT-107 (2026-06-18, commit 244b9e5) and CONTEXT-109 (88/88, commit chain 5d247c6…). The v25 presence guard was adversarially re-proven that same night.
- The single `v41_midday_trendline_gate.live` / `v42_sizing_risk_cap_guard.offline` / `v43_ghost_entry_dual_account.offline` blips (06-16) were transient new-validator authoring windows, all green afterward.
- The original file already carried the note **"No active CRITICAL items"** (queue line 126) + a prior dismissal of 17 such items — nothing ever drained these because they are not real work.

**If a future regression is REAL** (gym < 88 on a non-flaky stage), it surfaces via `gym-scorecard-{date}.json` + STATUS.md `## Known broken`, not here. Do not re-queue raw harvester REGFAILs into the active backlog.

IDs archived (verbatim text in archive file): HARVEST-REGFAIL-20260618-100011 … 100036; HARVEST-REGFAIL-20260617-100026; HARVEST-REGFAIL-20260616-100020 … 100023; HARVEST-REGFAIL-20260601-100019 … 100024; HARVEST-REGFAIL-20260531-100012 … 100035; HARVEST-REGFAIL-20260530-220615; HARVEST-REGFAIL-20260521-100012 (was already marked resolved).

### Cluster B — ~110 HARVESTED-FROM-GYM data-point items (RSI/REGIME/RIBBON/SWEEP/BREAKOUT/FOOTGUN, 2026-05-20 .. 06-18)

**Verdict: CATALOGUE-ONLY, no SPY action. Archived.** Every one is an informational BTC-gym observation (e.g. "BTC RSI=18 oversold", "v09_regime TREND_DOWN 72% of bars", "v14_sweep liquidity-grab at 65000", "v01_live foot-gun caught — bar correctly rejected"). The items that were processed (the `[x]` ones, 100007/100008/100014-100016/100111/100112/100243-100245) ALL closed as `completed-informational` / `completed-catalogued` / `validator-working-correctly` with **no doctrine change** — confirming the entire class is data-flywheel exhaust, not drainable work. SPY 0DTE has no measured edge-correlation to BTC RSI/regime extremes; the swarm `correlation_analyst` already consumes BTC trend as context.

These are exactly the OP-22 "371st untriaged candidate is debt" pattern. The `gym_harvester` retention cap should prune them; they are archived here rather than acted on. Full IDs + text in the archive file (HARVEST-REGIMEEXT-*, HARVEST-RSIEXTREME-*, HARVEST-RIBBONFLIP-*, HARVEST-SWEEP-*, HARVEST-BRKCLUSTER-*, HARVEST-FOOTGUN-*).

### Cluster C — duplicated gym-session RED roll-up blocks (T-GYM-2026xxxx)

**Verdict: STALE DUPLICATES. Archived.** ~30 near-identical "gym-session RED for {date}" blocks (many the same date repeated 6-8×), almost all reducing to `pin-chain-verify (RED): rule_version=unknown` or `heartbeat-pulse-check (RED): max gap 15.02min`. The pulse-check 15.02-min "gap" is the known hash-unchanged-skip artifact (L39 — the early-exit writes SKIP not FIRE). The `rule_version=unknown` is the pin-chain reading a transient state. Current gym is GREEN. These were never individually actionable. Verbatim in archive file.

### Cluster D — completed historical work (TONS, 2026-05-13 .. 06-15)

**Verdict: DONE. Retained in archive file.** The pre-triage queue was ~70% `[x]`-completed items spanning the SNIPER pipeline, VWAP/ODF/v14_enhanced/REGIME_SWITCHER research arcs, the FIRE-19..43 self-heal series, the ENGINE-BENEFIT loop cycles (watcher fleet, NLWB/HS/FBW real-fills validations), the SWARM calibration arc, the MiniMax migration, and the level-detection T51-T59 series. All complete; full text preserved verbatim in `queue-archive-2026-06-19.md` for audit history. Not re-listed here to keep this file lean.

### Notable items folded into the Active backlog above (so nothing real is lost in the archive)

- MM-05/06/07 (J-ratification) → promoted to Active Tier 2.
- HEARTBEAT-SPY-LOGGING-CLARIFICATION + the two CONTEXT-107 J-rulings → Active Tier 2.
- The 4 CONTEXT-106 deferred findings (account_id, shadow-ratify, stray crypto __init__, stairstep) → Active Tier 1 (also filed as cook-queue tasks).
- The genuinely-open low-pri carry-overs (T60, T101, T102, EOD-2.2/2.3/2.4, SHOT-DISCORD-ALERT, T24/25/16/17/106/107) → Active Tier 4 with a "verify still relevant" caveat.

### Still-open items intentionally LEFT in the archive (superseded / dead-research, do not resurrect without J)

- SNIPER everything (T35/T31/T42b/T42c/T42d/T43/T44/T44d, T14, sniper-v2) — SNIPER was INVALIDATED on real fills (`docs/SNIPER-FINAL-VERDICT-2026-05-13.md`, 0 keepers) and the loop was retired. OPRA-dependent re-runs are moot.
- T40 (swap Gamma_Heartbeat → heartbeat-v15-draft) — superseded; v15 shipped live 2026-05-13, and CONTEXT-106 made heartbeat.md SAFE-only. The draft is historical.
- T72/T73/T74 (v14_enhanced grinder memory sidecars) — v14_enhanced is research-only; mitigations T70/T71 already shipped.
- SWARM-BROKE-N20-GATE / SWARM-TESTED-MIXED-N20-GATE / SWARM-CALIBRATION-FORMULA-V3 (awaiting-J) — need live accumulation to cross N≥20; not drainable now.
- The seeder/T2xx CHEF-tagged seeds (T201-T205), EOD-PHASE-3/3.B, OPRA-BACKFILL-5-14, REGISTER-EOD-DEEPDIVE-CRON — either subsumed by the live Kitchen loop or weekend multi-day work.
- T29/T2026-05-21 watch-accumulation items (MOMENTUM-HIGHVOL-VIX25-RETEST, HS-WATCHER-LIVE-ACCUMULATION) — blocked on live-observation accumulation, not on the conductor.

---

## Completed

### 2026-06-19 — Tier-1 loose-end close-out (verify-first pass)

- [x] BP-ACCOUNT-ID-ENFORCE (HIGH) :: **CLOSED — write-side enforcement added.** Consumer side was already done (eod-summary.md step 1 + line ~215 default-by-file). The gap was the WRITE side: the canonical writer `backtest/lib/ledger.py#append_decision` did NOT stamp `account_id`. Fix: added `account_id_for_path()` (base `decisions.jsonl`->`safe`, `aggressive/` or `*-bold*`->`bold`, matching the consumer's default-by-file rule) and `append_decision` now stamps it on every NEW row unless the producer set it explicitly (immutable copy, no caller-dict mutation). `account_id` added as documented Optional on `DecisionRowModel` (legacy rows still validate). Tests: 4 new in `backtest/tests/test_ledger_writer.py` (path map both slash styles, safe-stamp, bold-stamp, explicit-respected, every-row-carries-it) — `9 passed`. `test_state_contracts.py` still `16 passed`.
- [x] BP-SHADOW-RATIFY-CONTRACT (HIGH) :: **ALREADY DONE (verified, not re-done).** eod-summary 8c header reads "file+field contract fixed 2026-06-18"; section 8c (lines 379-437) now reads `automation/state/shadow-model-decisions.jsonl` with `real_action`/`shadow_action`/`agree` (verified against producer `setup/scripts/shadow_model_eval.py` ~889-903), NOT the old `decisions.jsonl`+`version`/`would_have_action`. No action needed.
- [x] BP-STRAY-CRYPTO-INIT (LOW) :: **ALREADY DONE (verified, not re-done).** `backtest/crypto/__init__.py` does not exist (only `backtest/crypto/data/` remains); the de-sprawl wave already removed it. No `backtest.crypto` import surface to break. No action needed.
- [x] OP11-STALE-TEST (was a known failing test, not a formal queue id) :: **CLOSED.** `backtest/tests/test_op11_loop.py::test_shadow_loop_closes_and_is_read_only` failed `(7, X) != (7, X)`: the shadow override `min_ribbon_momentum_cents: 3.0` was a NO-OP vs the prod arm (prod runs full params.json with rmom=0 / gate OFF -> 7 trades; all 7 already clear a 3c bar). Empirically probed the real shadow path on the test window: 3.0 and 8.0 don't diverge; **10.0c is the divergence cliff** (filters 3 of 7 -> 4 trades, `(4, 3081.61)`); 10/12/15 share the same 4-trade plateau. Fix: override changed to **15.0** (stable plateau, margin off the cliff) so the read-only invariant is now exercised against a GENUINELY divergent A/B (not weakened — still asserts byte-identical params.json after a shadow run). `python -m pytest backtest/tests/test_op11_loop.py -q` -> **11 passed**. Gym `python -m crypto.validators.runner --skip-replay` -> **86/87 overall_pass=True**.

(historical completions preserved verbatim in `automation/overnight/queue-archive-2026-06-19.md`)

## Blocked
(none active — Rule-9 J-ruling items live in Active Tier 2, which are decisions not blocks)
