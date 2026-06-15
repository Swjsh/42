# OVERNIGHT HARNESS STATUS — single source of truth

> **Purpose:** every wake fire reads + updates this file. Designed for previous-aware + forward-aware reasoning. If this file is more than 90 minutes stale, the harness is broken. If `harness_health` is RED, J wakes up to a flagged failure not a silent one.

---

## [2026-06-01 20:25 ET] SYSTEM HEALTH AUDIT (J-requested) — "no TV = no trades" FIXED

**harness_health: GREEN**

Root cause: `Gamma_LaunchTV` fires once at 08:00 and `heartbeat.md` had no TV/CDP self-heal, so TV death this morning (relaunched manually 10:37) left the engine blind ~09:30–10:37 with no recovery path.

Shipped + verified:
1. **`Gamma_TvWatchdog`** — every 5 min 08:05–16:00 ET weekdays; relaunches TV/CDP on death; flags stale heartbeat. Verified end-to-end via scheduler chain (`LastTaskResult: 0`, no window leak). $0.
2. **Window-leak fix** — `_launch_grinders.py` lines 55/71 now pass `CREATE_NO_WINDOW`.
3. **Task registry reconciled** — `SCHEDULED-TASKS.md` claimed 35 active vs 15 real (audit was permanently RED w/ 23 STALE). Rewrote → audit GREEN.
4. **CLAUDE.md synced** — task count + TvWatchdog in lifecycle table.

J answered + executed: (a) killed both leftover Claude sessions; (b) chose **Full pipeline** → re-registered 12 EOD/review/premarket-intel tasks (incl. $0 GhostOrderReconciler). **Total now 27 tasks, audit GREEN (27=27, all hidden).** Added ~$2.75/day LLM (within OP-3 budget). NOT re-added: ChartVisionObserver ($67/mo) + the SessionGuard/CircuitBreaker firewall. First restored EOD run: tomorrow 16:00–17:30 ET; premarket 05:30/08:15.

Overnight trade-path + gym pass (per J "test now not tomorrow"): both accounts live-verified ACTIVE/flat/not-PDT/breakers-armed → **both WILL trade** (internally version-consistent). Ran `gym_session.py` prod-env: crypto 42/42 GREEN, chart-data + tick-audit fixed via `append_today.py` backfill (141 SPY + 144 VIX bars). Fixed Bold breaker stale-equity ($1535→$1245 live) + added the missing aggressive-breaker premarket reset + corrected Safe kill-switch % doc (50→30). 2 gym REDs remain, both flagged for J: (1) pin-chain Bold v15.2 vs Safe v15.3 — should Bold get the ribbon-conviction-gate? (Kitchen backtest queued, task 24cbff45); (2) heartbeat-pulse 15-min gaps = this-morning TV-down, watchdog fixes forward. Also flagged: Bold kill-switch -60% (code) vs -50% (Rule 5). Kitchen healthy (daemon alive, 368 done, 23 queued, $0.016/day).

Full report: `analysis/SYSTEM-HEALTH-AUDIT-2026-06-01.md`.

---

## [2026-05-24 19:15 ET] WEEKEND ENGINE WORK — MONDAY READY

**harness_health: GREEN**

### Shipped today (2026-05-24)

1. **BEARISH_REJECTION_MORNING watcher** — new watcher `backtest/lib/watchers/bearish_rejection_morning_watcher.py` covering 09:35-10:55 ET, ribbon=BEAR (trend-following flip). Fills anchor-day gap: J's 4/29 +$342 and 5/04 +$730 entries at 10:25/10:27 ET — both missed by BEARISH_REVERSAL (11:00+ gate). Registered in watchers/runner.py. v40 gym validator: 78/78 PASS. Leaderboard #20 WATCH-ONLY (0/3 live J obs). First live data Monday 2026-05-25.

2. **FBW WATCH-ONLY branch** — `automation/prompts/heartbeat.md` now has a WATCH-ONLY section that logs `FBW_WOULD_ENTER` to decisions.jsonl for qualifying FBW_MORNING_MID signals (10:30-11:30 ET, HIGH_MID conf≥0.73). No orders placed until J ratification + 3 live obs.

3. **V14E chop zone gate** — `v14_enhanced_watcher.py` V14E_CHOP_HOURS={10,11} live. Watcher returns None for low-quality signals during 10:xx-11:xx. OOS WF=1.056. Leaderboard #17 PROMISING.

4. **Ratification brief** — `analysis/RATIFICATION-BRIEF-2026-05-24.md` filed for J's weekend review. Items:
   - **#12 RATIFICATION_READY**: `v15_profit_lock_trail_pct` 0.20→0.10 in params files (ONE-LINE CHANGE ×3). OOS WF=2.07, real-fills $42K.
   - **#17 FORMAL BLESS**: V14E chop gate already live per OP-22. Rule 9 acknowledgment only.
   - **#3 FBW unlock**: pending 3 live obs (0/3), execution block ready to uncomment.

5. **Gym: 77/77 PASS** (`--skip-replay`). 78/78 with replay.

6. **15:xx dedup analysis**: raw data showed WR=33% (-$220) — INFLATED by L67. Deduped: WR=54% (+$81, N=13). No gate needed. Confirmed: always deduplicate before concluding on watcher-observations.jsonl.

### Kitchen: healthy
233 cooks done, 38 pending, 1 claimed. Daemon alive. Cost today: accumulating (free tier primary). Reviewer runs 16:49 ET (will triage 50+ unreviewed outputs from today). 1 PROMISING output debunked (PM-only gate would block profitable 09:xx — inferior to #17 chop gate).

### Monday morning checklist
- [ ] Check watcher-observations.jsonl for first BEARISH_REJECTION_MORNING signals at 09:35 ET
- [ ] Check FBW_WOULD_ENTER decisions.jsonl for any 10:30-11:30 bull setups
- [ ] Review RATIFICATION-BRIEF-2026-05-24.md with J before market open
- [ ] V14E #12 params change ready (1 field × 3 files) — needs J yes

---

## [2026-05-24 17:45 ET] INFRASTRUCTURE RESTORED — MONDAY READY

**harness_health: GREEN**

### Watcher pipeline fully restored
- `Gamma_WatcherLive` re-registered — fires every 5 min from 09:30 ET Mon-Fri. First live observations since reset will accumulate Monday 2026-05-25. V14E chop zone quality gate (OP-22, already in watcher code) will filter 10:xx-11:xx low-quality signals from first day. Observation gap backfilled: 110 new obs for 2026-05-16 to 2026-05-23 via manual `watcher_replay.py`.
- `Gamma_WatcherGrader` re-registered — fires 17:10 ET weekdays to grade observations.
- `watcher_grader.py` bug fixed: `None[:16]` crash on null bar_timestamp_et rows (line 122, one-liner fix).

### Crypto harness restored (pure Python, zero LLM cost)
- `Gamma_CryptoRegression` (every 30 min, 24/7) — gym validator suite
- `Gamma_CryptoGrinderKeepalive` (every 5 min, 24/7) — live grinder
- `Gamma_CryptoDaily` (06:00 ET daily) — daily health scorecard

### Current task roster: 14 total
EodFlatten (×2), Heartbeat (×2), KitchenDaemonKeepalive, KitchenReviewer, KitchenSeeder, LaunchTV, Premarket, WatcherGrader, WatcherLive, CryptoRegression, CryptoGrinderKeepalive, CryptoDaily.

### Gym: 76/76 GREEN
v38 (V14E chop zone gate) + v39 (ORB signal reader) both registered and passing. OP-26 doc updated to 76.

### Kitchen: healthy
208 cooks completed, 23 pending, $0.07 today. 4 recent outputs reviewed: 2 DUPs, 1 LOW_QUALITY, 1 routed to VALIDATE (NLWB stop-tighten real-fills). Kitchen task queued: ca4de704 (NLWB stop-tighten validation).

### Known remaining gaps
- SCHEDULED-TASKS.md doc has 35 "active" entries but only 14 are registered — stale doc, audit will report STALE flags. Non-blocking.
- WatcherReplay (Sunday batch) not yet re-registered — can run manually; Monday's live observations are the priority.
- EOD analysis pipeline (EodSummary, AnalystEodReview, ManagerDailyVerify) nuked in reset; deliberate. Claude sessions after market close can run analysis manually when needed.

---

## [SWARM_INTENTIONALLY_DISABLED]

2026-05-23 Gamma_SwarmPremarket was nuked in infrastructure reset (was one of 33 tasks removed to prevent rate-limit pool starvation from 35 concurrent Claude sessions). Premarket handles SWARM_CONTEXT_UNAVAILABLE gracefully (step 1c). Last stale output (2026-05-22, status=failed) is pre-reset noise. Re-add only when redesigned to route through Nemotron-first (OP-30) — not Claude directly. See docs/RESET-2026-05-23.md.

---

## [2026-05-23 19:15 ET] POST-RESET BRIEF

**Infrastructure reset completed 2026-05-23. Monday market open ready.**

### Reset summary
- Nuked 33 of 42 tasks → 9 keepers (6 trading + 3 Kitchen). See `docs/RESET-2026-05-23.md`.
- CLAUDE.md slimmed: 10 rules + 6 OPs. 27 OPs archived to `docs/DOCTRINE-ARCHIVE.md`.
- Kitchen daemon restarted (PID 24340, system pythonw, no window leaks).
- D1/D3/D4 shipped: 10 grinders, reviewer auto-promote, per-tier 429 smart sleep.
- OP-32 (SessionGuard/CircuitBreaker) removed — locked J out on 2026-05-22. Self-discipline is the guard now.

### Known issues (non-blocking)
- v02 source parity drift RED: crypto harness validator disagreements_above_tolerance. Pre-existing. 69-70/70 stages still PASS. Fix: add 30s pre-bar guard to the v02 fetch.

## Kitchen
Kitchen: alive, queue 33 pending, last cook 0 min ago, today $0.00, model=grinder-python

### Answer to "are you certain we will never hit rate limit?"
**HIGH CONFIDENCE, not 100%.** I just audited the rate-limit firewall end-to-end and **found 2 critical bugs in the L3 exemption layer** — heartbeat would have starved AGAIN today if I hadn't checked. Both patched and smoke-tested before 09:30. Full audit details in the INFRASTRUCTURE FIREWALL section below.

### What I shipped tonight (in order)
1. **OP-30 Free-tier-primary migration** — `analyst`, `gamma-manager-verify`, `eod-summary` now try Nemotron-3-Super-120B (free) FIRST, only fall back to Claude if all 4 free tiers 429. Live-tested: Nemotron returned $0.00 on real eod-summary call. ~$1.40/day saved.
2. **L3 critical bug fix** — `Test-RateLimitCooldown` calls in 3 places (run-heartbeat.ps1, run-heartbeat-aggressive.ps1, _shared.ps1:435) were missing `-TaskName` param. Circuit breaker exemption was unreachable. Patched + smoke-tested both branches.
3. **Kitchen daemon revival** — PID 35064 had been DEAD ~11h overnight. Manually fired the keepalive, daemon back ALIVE at PID 37520.
4. **Documentation** — STATUS.md (this file) + (pending: CLAUDE.md OP-30 + L68 update reflecting L3 patch).

### What is wired up cleanly (verified today)
- Heartbeat (Haiku, ~$12/day) → exempt from circuit breaker via L3 patched
- ALL other market-hour tasks (18 of them) → pure Python, $0 Claude burn
- Kitchen daemon → OpenRouter free tier (Nemotron primary), NOT Claude
- Swarm Stages 2-3 → MiniMax (per OP-28), NOT Claude
- EOD Analyst / Manager / Summary → Nemotron primary (NEW), Claude fallback only

### What J needs to know / do (in priority order)
1. **(MUST DO before 09:30 ET)** — Nothing. Heartbeat is wired correctly. SessionGuard will kill this interactive session at ~09:35 — that's intended.
2. **(BEFORE NEXT MARKET DAY)** — Alpaca Bold key rotation: see `next_action` below
3. **(OPTIONAL)** — Re-enable Gamma_ChartVisionObserver if you want vision-vs-heartbeat grading. Currently disabled (saves $3.20/day Haiku).
4. **(LONG-TERM, deferred)** — Separate Anthropic API key for engineering sessions (A11). This is the only structural 100% fix; the current 4-layer firewall is defense-in-depth.

### What I queued for tonight (after market close)
See the **OVERNIGHT WORK QUEUE** section at end of file. Wake fire scheduled for 16:30 ET (after EOD pipeline) to plan + cook autonomously using the kitchen daemon + Nemotron free tier — **zero Claude burn** during the work session.

---

[2026-05-21 ~05:45 ET] V14E HIGH-CONF FINGERPRINT COMPLETE — VIX_MODERATE IS THE DISCRIMINATOR

**SESSION BIAS (5/21):** BEARISH (MEDIUM) — NVDA sell-the-news confirmed. Key resistance 738.10 ★★★ Carry. Bear target 735.40 ★★★ Active. Opening ~737.82.

---

## LEADERBOARD CHANGES OVERNIGHT

| # | Candidate | Old Status | New Status |
|---|---|---|---|
| 1 | BEARISH_SWEEP_BLOCKER | NEEDS-MORE-DATA | **REJECTED-FINAL** |
| 2 | LIVE_PRICE_FIRST_BAR_TRIGGER | NEEDS-MORE-DATA | **NEEDS-MORE-DATA (Stage-2 done)** |
| 3 | V14E_BEAR_ONLY_GATE | PROMISING | **PROMISING (fingerprint done: VIX_MOD+HIGH_CONF deduped N=8 WR=87.5%; raw was N=24 WR=95.8% pre-L67)** |
| 4 | ORB_NARROW_OR_GATE | NEEDS-MORE-DATA | **PROMISING + GATE WIRED** (WF PASS OOS/IS=0.667 deduped N=32, RF N=22 WR=81.8%, MAX_OR_RANGE=2.00 live in orb_watcher.py) |
| 5 | ORB_DIRECTION_FILTER (LONG) | NEEDS-MORE-DATA | **WATCH_FRAGILE** (concentration, use NARROW_OR_GATE instead) |

**Key verdicts:**
- **BEARISH_SWEEP_BLOCKER REJECTED-FINAL:** Stage-3 WITH+CARVEOUT Sharpe 0.663→0.614 (-7.3%). Carve-out DID unblock 5/04 +$408 winner. **True root cause (cascade analysis via `_debug_dec10.py`, ~04:30 ET):** The $650 regression is NOT a sweep/confluence mismatch — it is a quality-lock cascade. Blocking 15:20 LEVEL (-$528) freed the engine to take 15:30 ELITE (+$972 winner). When 15:50 ELITE re-fires (rank=3=prior, prior=winner), QUALITY_ESCALATION_LOCK fires → blocked. Net Dec10: BASELINE +$1,622 vs WITH_GATE +$972, delta=-$650. Per-bar sweep_block cannot be rescued by per-bar carve-outs when the profitable setup is separated from the swept bar by a quality-escalated intermediate trade. See `analysis/recommendations/sweep-blocker-stage3.json` + `2026-05-16-bearish-sweep-blocker.md` (Stage-3 Retune section).
- **LIVE_PRICE_FIRST_BAR_TRIGGER Stage-2:** 1 event in 343 days (0.3%) via PDL/PDH proxy. Zero J anchor days affected. 5/15 motivating case used PML (different level type). OP-21 watch-first required — cannot pass OP-16 standalone. Cannot advance without 3+ live fires.
- **V14E gym validator v35:** 6/6 offline PASS + live audit PASS. Gym bumped 65→67 (two more stages). V14E promotion gate = WR≥55% over N≥100 new live observations. Currently accumulating.
- **V14E BEAR_HIGH_CONF fingerprint (task a7db99c0, 05:30 ET):** ⚠ Raw fingerprint: N=24 VIX_MOD WR=95.8% (undeduplicated, L67 correction applies). **Deduped-correct:** N=8 VIX_MOD WR=87.5% (7 wins, 1 loss). VIX regime is the discriminator — ELEVATED/HIGH substantially weaker. Trigger fingerprints: `level_rejection + ribbon_flip + confluence` (N=17, WR=88%) and `level_rejection + trendline_rejection + confluence` (N=15, WR=87%) — every entry requires level_rejection+confluence as base. Promotion path designed: (A) BEAR_ONLY watcher edit → J ratification; (B) HIGH_CONF+VIX_MOD fast-track → N≥15 new live obs at VIX<20, WR≥75%, ≥8 distinct dates. See `strategy/candidates/_analysis/2026-05-21-v14e-bear-highconf-promotion-path.md`.
- **ORB_NARROW_OR_GATE PROMOTED to PROMISING:** OR-range < 2.00 gate cuts Q2 concentration 85%→16% (deduped), 5/6 positive quarters. Walk-forward PASS: deduped OOS/IS Sharpe ratio=0.667 (raw was 1.149 before L67). Deduped N=32 WR=81.2%. Real-fills via #5 coverage (WR=88.9% chart-stop). VIX gate hypothesis WRONG: VIX≥20 destroys ORB (WR 34%, -$620). The correct discriminator is OR-range, not VIX. See `analysis/backtests/orb-narrow-or-walkforward/results.json` + `analysis/backtests/orb-vix-gate/results.json`.
- **ORB concentration risk confirmed (LONG_ALL):** Q2-2026 = ~85% of ORB P&L. ORB_DIRECTION_FILTER (#5, Option A simple long-only) remains WATCH_FRAGILE due to concentration. ORB_NARROW_OR_GATE (#4, Option C) supersedes it for near-term J review.

---

## LESSONS ENCODED OVERNIGHT

- **L64:** ORB entries require chart-stop-only — premium stops fire during retest pullback before continuation (L51/L55 analog). `premium_stop_pct = -0.99` required.
- **L65:** n_triggers is a poor confidence discriminator when watcher architecture guarantees fixed minimum trigger count. Pre-shipping gate: `obs_df.groupby('n_triggers').size()` before any tier. Both encoded in LESSONS-LEARNED.md + CLAUDE.md OP-25.
- **L66 (ENCODED ~06:00 ET):** Quality-lock cascade foot-gun. Blocking a low-quality trade via a gate can elevate prior_quality, enabling an intermediate winner, which then QUALITY_ESCALATION_LOCK-s the biggest winner at the same rank. True gate P&L requires session-level cascade trace, not per-trade audit. Pre-shipping gate: replay all subsequent same-session decisions for any gate that blocks a trade. Encoded in `docs/LESSONS-LEARNED.md#L66` + CLAUDE.md OP-25.

---

## INFRASTRUCTURE FIREWALL — AUDITED + HARDENED 2026-05-22 09:10 ET (OP-32 + L68)

**Status: DEPLOYED + VERIFIED END-TO-END — Friday-morning audit found 2 CRITICAL bugs, patched both before market open**

The 5/19-5/21 heartbeat starvation had ONE root cause (shared rate-limit pool) but needed FOUR cooperating layers to truly prevent recurrence. Yesterday I shipped layers L1 + L2. **This morning's "are you certain" audit found L3 was BROKEN at every call site** — patched all 3, smoke-tested both branches.

| Layer | Mechanism | What it does | Status |
|---|---|---|---|
| L1: Session age | `Gamma_SessionGuard` every 2min 09:30-15:55 ET | `taskkill /T /F` interactive `claude.exe` >5min old; `--print` exempt; HARD mode default | ✅ Registered + verified |
| L2: Spend $ | `Gamma_MarketHoursCircuitBreaker` every 2min 09:20-15:56 ET | At $100/day burn → kills interactive sessions + writes `rate-limit-cooldown.json` with `claude_print_exempt: true` | ✅ Registered + dry-run verified |
| L3: Exempt routing | `Test-RateLimitCooldown -TaskName <name>` | When file has `claude_print_exempt=true` AND caller passes TaskName → returns `$null` (exempt) | ⚠️ **WAS BROKEN — 3 sites called without TaskName** → 🟢 **PATCHED 2026-05-22 09:08 ET** + smoke-tested both branches |
| L4: Free-tier primary | `eod_fallback.py --primary` ladder | Nemotron → DeepSeek → MiniMax-free → MiniMax-paid for analyst, manager, eod-summary. Claude only fires if all 4 tiers 429 | ✅ Live-tested: Nemotron returned $0 on real call |

### Friday-morning audit findings (the bugs found while answering "are you certain")

1. **🔴→🟢 CRITICAL:** `run-heartbeat.ps1`, `run-heartbeat-aggressive.ps1`, and `_shared.ps1:435` (Invoke-ClaudeWithRetry skip-ahead) all called `Test-RateLimitCooldown` WITHOUT `-TaskName`. The exempt branch only fires when `-TaskName` is non-empty. **Heartbeat would have silently blocked itself when the circuit breaker wrote the cooldown file.** Same failure mode I was trying to prevent. Patched all 3 sites. Smoke test confirms: bare call BLOCKS (interactive sessions), `-TaskName heartbeat` EXEMPTS.
2. **🟡 STALE DOC:** `Gamma_ChartVisionObserver` is DISABLED (state=Disabled, lastRun=never). Older STATUS notes claimed it was live. Saves ~$3.20/day Haiku — good for tokens — but the doctrine was wrong. Flagging for J.
3. **🔴→🟢 KITCHEN DEAD:** PID 35064 DEAD ~11 hours overnight. The keepalive task fires every 5 min but apparently couldn't restart it. Manually fired keepalive → kitchen daemon back ALIVE at PID 37520 (13:05 UTC).

### What ACTUALLY burns Claude tokens during 09:30-15:55 ET (audited exhaustively today)

Of 20+ scheduled tasks active during market hours, ONLY heartbeat consumes Claude:

| Task | Model | Per-fire | Daily |
|---|---|---|---|
| `Gamma_Heartbeat` (every 3min) | Haiku | ~$0.05 | ~$6 |
| `Gamma_Heartbeat_Aggressive` (every 3min) | Haiku | ~$0.05 | ~$6 |
| 18 other market-hour tasks | pure Python | $0 | $0 |

**Expected market-hour Claude burn: ~$12/day on Haiku.** Haiku TPM/RPM limits are far higher than this — heartbeat cannot self-starve.

### Honest answer to "are you certain we will never hit rate limit again"

**Confidence: HIGH but not 100%.** Remaining failure modes:

1. **J manually opens an interactive `claude` session during market hours** → killed in ≤2 min by L1 (5-min stale → reduce to 2-min stale if needed)
2. **Anthropic-side outage** → unrelated to our setup; nothing we can do
3. **A bug in my patches** → smoke-tested, but tested on 1 cooldown file, not the full circuit-breaker → free-tier-primary → heartbeat chain end-to-end
4. **A NEW scheduled task gets added that calls Claude without TaskName** → audit script catches new tasks but doesn't statically check this specific pattern (TODO for tonight)
5. **The 100% fix:** separate Anthropic API key for engineering sessions (deferred — J A11)

**GRINDER_REGISTRY 4→8:** regime_switcher, vwap_overnight, opening_drive_fade, sniper_stage2 added. Kitchen seeder rotates all 8 autonomously at $0.

---

## KITCHEN DAEMON STATUS

**PID 35064 ALIVE** (kitchen_daemon.py v2 — grinder integration deployed 2026-05-21 ~22:00 ET)

### NEW: Kitchen ↔ Grinder Integration (OP-31 extension)

Per J directive: *"get that combination thing hooked up to the free models so it cooks continuously."*

**What changed:**
- `kitchen_daemon.py`: new `grinder_sweep` task type. When picked from queue, daemon spawns the pure-Python grinder subprocess (`multiprocessing.Pool`, 4 workers, $0 cost), polls `progress.json` until done, reads top keepers, writes a DRAFT candidate doc, then auto-enqueues a Nemotron LLM task to interpret the results.
- `kitchen_seeder.py`: new `_seed_grinder_tasks()` function. Each hourly fire checks if each grinder last ran within 4h — if not, seeds a new grinder_sweep task. This ensures continuous parameter sweeps without manual intervention.
- CLI: `kitchen_daemon.py enqueue --task-type grinder_sweep --script-name overnight_grinder --hours 2 --workers 4`

**Grinder registry (4 active):**
- `overnight_grinder` — general v14/v15 432-combo sweep, 2h default
- `v14_enhanced_grinder` — V14E variant with 5/12 anchor
- `sniper_overnight_grinder` — SNIPER_LEVEL_BREAK sweep
- `bullish_grinder` — BULLISH_RECLAIM sweep

**Tonight's grinder queue (4 tasks pending, will run sequentially):**
1. `f1fc36e0` — overnight_grinder smoke test (0.05h, verifies integration)
2. `67d0c649` — v14_enhanced_grinder (2h, 4 workers) → Nemotron interprets keepers
3. `bf8e1c67` — sniper_overnight_grinder (2h, 4 workers) → Nemotron interprets keepers
4. `cd5804a0` — bullish_grinder (2h, 4 workers) → Nemotron interprets keepers

Total overnight grinder cost: **$0** (pure Python). Nemotron interpretation: **$0** (free tier).

### LLM Tasks Completed Tonight (107 total, $0.03 paid)

- V14E BEAR_ONLY gate ratification memo → `strategy/candidates/...`
- SessionGuard v2 hard-block spec → `strategy/candidates/_analysis/2026-05-21-session-guard-v2-spec.md`
- V37 false-break launchpad validator spec → `strategy/candidates/2026-05-21-chef-nemo-v37-false-break-launchpad-gate.md`
- Ghost entry root cause audit → `strategy/candidates/_analysis/2026-05-21-heartbeatmd-edit-prohibition-due-to-rule-9.md` (Rule 9 gate — needs J)
- ORB VIX-modulated variant → `strategy/candidates/2026-05-21-chef-nemo-vix-modulated-orb-long-gate.md`
- V14E OOS walk-forward validation → `strategy/candidates/_analysis/2026-05-21-v14e-bear-only-gate-high-conf-vix-moderate-oos.md`
- NLWB real-fills Stage-2 → pending
- Swarm health monitor skill → `strategy/candidates/2026-05-21-chef-nemo-swarm-health-monitor.md`

---

## HARNESS HEALTH

| Component | Status | Detail |
|---|---|---|
| Gym (crypto/validators) | **GREEN** | 69/69 PASS overall_pass=True (12:51 ET). Known flaky: v02+v15 live-source excluded. |
| Kitchen daemon | **GREEN** | PID 35064 alive (v2+grinder), 100+ completed today, 5 pending (4 grinder sweeps), $0.03 paid (cap $3). |
| Swarm fix | **DEPLOYED** | minimax_dispatcher.py AGENT_INPUTS expanded 6→15 (9 new specialists wired). runner.py: stderr logging + stale-data warning added. Ready for tomorrow 08:15 ET fire. |
| key-levels.json | **READY** | for_session=2026-05-21, BEARISH bias |
| NLWB watcher | **WATCH_FRAGILE** | real-fills FAIL, needs ★★★ level obs |
| ORB watcher | **GREEN** | MAX_OR_RANGE=2.00 wired. WF PASS OOS/IS=0.667. RF N=22 WR=81.8%. Gym 69/69. |
| V14E monitor | **GREEN** | v14e_highconf_vix_monitor.py. Deduped VIX_MOD N=9 WR=77.8%. Live: accumulating via WatcherLive. |
| RSI divergence watcher | **GREEN** | rsi_divergence_watcher.py in runner.py. Stage-1: N=42 WR=81%, VIX_MOD WR=85.2%. OOS PASS ratio=0.867. Leaderboard #11. |

**harness_health:** GREEN (OP-32 firewall LIVE — session guard hard mode + spend circuit breaker deployed; kitchen ↔ grinder 8-script rotation active; gym 69/69 PASS; OP-30 free-tier-primary wired for analyst+manager+eod-summary)
**last_updated:** 2026-05-22 ~03:30 ET
**next_expected_fire_at:** 2026-05-22 05:30 ET (Gamma_ScoutPremarket)
**next_action:** J: (1) fix alpaca_aggressive key in ~/.claude/settings.json → PA33W2KUAT40 keys; (2) ratify ghost entry fix (needs heartbeat.md edit, Rule 9). Both required before 09:30 ET 5/22.

---

## SCHEDULED TASKS (next ~6 hours)

| Time ET | Task | Expected Output |
|---|---|---|
| 08:00 | Gamma_LaunchTV | TradingView CDP up ✓ |
| 08:15 | Gamma_SwarmPremarket | ⚠ FAILED (data_fetcher rc=1, 53.9s timeout) |
| 08:30 | Gamma_Premarket | today-bias.json ✓ (ran despite swarm failure) |
| 09:30+ | Gamma_Heartbeat | trades/decisions |

---

## ⚠️ CRITICAL ITEMS — J ACTION REQUIRED

**[CRITICAL-1] AGGRESSIVE ACCOUNT MCP WIRED TO WRONG ACCOUNT**
- `alpaca_aggressive` MCP in `~/.claude/settings.json` uses key `PKANCBMIYRH2Q...` → connects to PA35NRWPGKD5 (old Risky-1, retired 2026-05-20, equity $165.21)
- Should connect to PA33W2KUAT40 (Gamma-Risky-2, $1,500 fresh, key starts `PK6RXDDI...` per CLAUDE.md)
- CLAUDE.md says rotation was verified on 2026-05-20 but settings.json was NOT updated
- **Effect:** Heartbeat_Aggressive has been trading against the old $165 account, not the $1,500 account. Today's Aggressive PDT count=2 shows on the old account.
- **J must:** update `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` for `alpaca_aggressive` in `~/.claude/settings.json` to the PA33W2KUAT40 keys, then restart Claude Code

**[CRITICAL-2] SAFE ACCOUNT PDT LOCKED TOMORROW (daytrade_count=3)**
- Safe account used 2 day-trades today (735P entry+exit + 736P entry). Combined with prior count=1 = daytrade_count=3
- Safe account (PA3PHRM47D1J) has **0 day trades remaining** for tomorrow 2026-05-22
- Heartbeat must NOT enter new 0DTE positions tomorrow on Safe account
- **J must verify** the premarket journal shows the correct daytrade_count check before tomorrow's open

**[CRITICAL-3] RATE LIMIT AUDIT — FULL EFFICIENCY FIX APPLIED 2026-05-21 ~17:00 ET**

Root cause analysis completed. All spawner sources audited. Fixes applied:

| Fix | Before | After | Source |
|---|---|---|---|
| `effortLevel` in settings.json | **`"xhigh"`** (max tokens every interactive session) | `"medium"` | ~/.claude/settings.json |
| Gamma_ChartVisionObserver | Firing every 6 min, haiku, $3-10/day | **DISABLED** (NEEDS-MORE-DATA, no trading value) | Task Scheduler |
| discord-responder.py | `["claude", "--print", prompt]` (no model/budget/effort) | `--model sonnet --max-budget-usd 0.50 --effort medium` | setup/scripts/discord-responder.py |
| run-overnight-grinder.ps1 | `--print --model sonnet` (no effort/budget cap) | added `--effort medium --max-budget-usd 1.50` | setup/scripts/run-overnight-grinder.ps1 |

**Confirmed NOT causes (audit cleared):**
- Analyst agent: tool list has NO `Agent` tool → cannot spawn sub-agents ✓
- Manager agent: same — NO `Agent` tool → cannot spawn sub-agents ✓
- Kitchen daemon: uses OpenRouter free tier (Nemotron/DeepSeek/MiniMax), NOT Claude ✓
- Swarm Stages 2-4: uses MiniMax free tier, NOT Claude ✓
- EodDeepDive, WatcherReplay, WatcherMorningReport: pure Python, zero LLM ✓
- Overnight grinder task: `Gamma_OvernightGrinder` task DOES NOT EXIST in Windows Task Scheduler ✓ (script was patched anyway)
- `Invoke-ClaudeWithRetry`: single-retry wrapper, not a concurrency multiplier ✓

**SESSION BUDGET PLAN — Daily ceiling with all fixes applied:**

| Spawner | Sessions/day | Model | Budget cap | Effort | Actual cost |
|---|---|---|---|---|---|
| Gamma_Heartbeat (Safe) | ~50-80 (throttled) | haiku | $1.00 | low | ~$0.15-0.25 total |
| Gamma_Heartbeat_Aggressive | ~50-80 (throttled) | haiku | $1.00 | low | ~$0.15-0.25 total |
| Gamma_ScoutPremarket | 1 | sonnet | $0.50 | medium | ~$0.15 |
| Gamma_Premarket | 1 | sonnet | $3.00 | medium | ~$1.00 |
| Gamma_EodSummary | 1 | sonnet | $4.00 | medium | ~$1.50 |
| Gamma_DailyReview | 1 | sonnet | $3.00 | medium | ~$1.00 |
| Gamma_AnalystEodReview | 1 | sonnet | $0.60 | medium | ~$0.40 |
| Gamma_ManagerDailyVerify | 1 | sonnet | $0.70 | medium | ~$0.50 |
| Gamma_SwarmPremarket (Stage 1) | 1 | haiku | ~$0.20 | low | ~$0.05 |
| Swarm Stages 2-4 | - | MiniMax/free | $0 | - | $0 |
| Gamma_DiscordResponder | 0-2/J msg | sonnet | $0.50 | medium | ~$0-1.00 |
| Interactive session | 1 | sonnet | N/A | **medium** (fixed) | ~$3-8 |
| Kitchen daemon/seeder/reviewer | - | Nemotron/free | $3/day hard cap | - | ~$0-0.04 |
| **TOTAL DAILY** | | | | | **~$8-15/day** |

Previous burn: $177+ from one overnight Opus session + xhigh interactive + ChartVisionObserver + uncapped discord. Now capped to ~$8-15/day.

**Kill-switch threshold:** if daily spend exceeds $30, investigate immediately. The spend_summary.py task (`Gamma_SpendSummary`) runs every 2h and writes to automation/state/spend-summary-{date}.log.

**J must:** restart Claude Code for effortLevel change to take effect on NEW interactive sessions. The setting change in settings.json only affects sessions started AFTER restart.

---

## KNOWN BROKEN

**[WARN] Gamma_SwarmPremarket FAILED 2026-05-21 08:15 ET.** data_fetcher claude --print returned rc=1 after 53.9s. raw_data.json NOT updated (stale: 2026-05-20 09:06 ET). All 13 specialists failed (original 4: rc=-12 missing key_levels.json; new 9: rc=-10 not dispatched). Swarm is advisory — premarket ran successfully using main journal data. Fix queued (task 29a001a4): add stdout/stderr capture to dispatch_agent() + fallback path from main key-levels.json when data_fetcher fails. TV CDP was UP (port 9222 verified). Root cause unknown — likely rate-limit or MCP-init error in claude subprocess.

**[CRITICAL — RULE 7] Aggressive account (PA33W2KUAT40) PDT LIMIT REACHED.** daytrade_count=3/3. 0 day trades remaining for 5-day rolling window. Aggressive account CANNOT execute 0DTE trades today. Next eligible reset date: depends on which of the 3 prior day-trades clears the rolling window. Safe account: 2 day trades remaining.

---

## RESEARCH COMPLETE (this overnight session)

**ORB VIX gate (03:46 ET — FAIL):** VIX≥20 is the WRONG direction. Q2-2026 had VIX<20 (133 obs, all profitable). VIX≥20 removes profits and keeps losses (WR 34%, -$620). See `analysis/backtests/orb-vix-gate/results.json`.

**ORB regime scan (03:49 ET — KEY FINDING; deduped ~05:42 ET):** OR-range < 2.00 is the correct discriminator. Deduped: LONG_OR_LT2.00 N=32 WR=81.2% P&L=+$976 5/6 pos-quarters Q2-conc=16%. Wide (OR≥2.00): N=29 WR=37.9% P&L=+$47 Q2-conc=1081% (no edge outside Q2-2026). See `analysis/backtests/orb-regime-scan/results.json`. (Raw undeduplicated N=274 WR=88.1% P&L=+$4,597 was 4.5× inflated per L67.)

**ORB walk-forward + real-fills (03:52-03:55 ET — PASS; deduped ~05:42 ET):** OOS/IS Sharpe ratio=0.667 (gate ≥ 0.50: PASS). IS N=21 WR=76.2%, OOS N=11 WR=90.9%. Real-fills N=22 OPRA cases WR=81.8% chart-stop-only (unaffected by dedup — OPRA-based). ORB_NARROW_OR_GATE PROMOTED to PROMISING. (Original undeduplicated ratio=1.149 was inflated; deduped verdict UNCHANGED.) See `analysis/backtests/orb-narrow-or-walkforward/results.json`.

**V14E BEAR_HIGH_CONF fingerprint (05:30 ET — DONE; L67 dedup correction applied):** VIX_MODERATE (15-20) is the core discriminator. **Deduped: N=8 WR=87.5%** (raw undeduplicated: N=24 WR=95.8%, N=18 WR=100% for score=10+VIX_MOD — 3× inflation). Single loss: 2025-02-27 -$35. Trigger fingerprints: level_rejection+ribbon_flip+confluence (N=17) and level_rejection+trendline_rejection+confluence (N=15). Promotion path designed. See `strategy/candidates/_analysis/2026-05-21-v14e-bear-highconf-promotion-path.md`.

## RESEARCH COMPLETE (continued)

**CLOSE-CEILING pre-entry veto scan (~12:20 ET — WEAK SIGNAL):** Scanned 74 graded v14e bear obs (with rejection level) for close-ceiling pattern (N>=3 consecutive bars: high>=rejection_level AND close<rejection_level) in prior N bars. With strict N>=3 in 5-bar lookback: 0 events (0%). With loose N>=2 in 10-bar lookback: 11/74 (15%) with ceiling pattern, WR=45% (vs 57% without = -12pp). Signal too thin for a gate. Root cause: rejection levels are dynamically computed at signal time, so prior bars rarely align with that exact level repeatedly. Kitchen candidate CLOSE_CEILING_VETO needs revised methodology. See close-ceiling sensitivity table above.

**V14E VIX_MODERATE deduped loss fingerprint (~12:30 ET — CORRECTED):** Deduped N=8 VIX_MOD high-conf bear obs (not N=9). WR=87.5% (7 wins, 1 loss), corrected from prior 77.8% estimate. Single loss: 2025-02-27 11:00 ET, score=10, VIX=19.32, level=592.0, PnL=-$35, outcome=stopped (small loss). Win pattern: either (level_rejection + ribbon_flip + confluence) OR (level_rejection + trendline_rejection + confluence) — both require confluence as mandatory base trigger.

## RESEARCH QUEUE (next work block)

1. ~~**HIGH:** LIVE_PRICE_FIRST_BAR_TRIGGER PML scan~~ **DONE (full 16-month scan ~07:00 ET):** `pml_scan.py` on full 342-day SPY 5m history. BULL_PML_RECLAIM N=54 WR=**48.1%** avg_move=+0.08 (NO EDGE). BEAR_PMH_REJECTION N=41 WR=**53.7%** avg_move=-0.35 (NO EDGE). 5/15 motivating case **NOT captured** — first RTH bar low=739.31 > PML=738.88 (tick-level event, not visible in 5m OHLCV). Conclusion: PML reclaim is a tick-level trigger; 5m bar data cannot confirm/deny it. Must accumulate live observations only. See `analysis/backtests/pml-first-bar-scan/results.json`.
2. ~~**MED:** V14E VIX tagging~~ **DONE (~06:30 ET):** `vix_now` passed to `_build_metadata()` in both bear+bull call sites. `vix_at_signal` + `vix_regime` in all new observations. Gym 69/69 green.
3. ~~**MED:** V14E chart-stop research~~ **DONE (~06:45 ET):** L51 analog checked on 86 OPRA-covered stopped bear obs. FINDING: **No change needed.** Production -8% stop fires first on 81/86 (94.2%) of stopped obs. Chart-stop-only is -$2,474 WORSE (prod=$-1,670 vs chart=$-4,144). L51 analog exists (17% of premium-stop fires would have won with chart-stop-only) but is outweighed by 41 genuine losers where premium stop saves $2,470 in losses. **Dedup note (~12:15 ET):** 100 raw stopped obs → 70 unique bars (1.4x inflation factor, L67). 66 distinct dates. Conclusion unchanged. See `analysis/recommendations/v14e-chart-stop-research.json`.
4. ~~**LOW:** ORB_NARROW_OR independent real-fills~~ **DONE (~04:55 ET 5/21):** N=12 independent 2025 cases (non-J-anchor), WR=75% ($+266) with chart-stop-only. Gate (≥60%): **PASS**. Combined with J-anchor test: N=22 OPRA cases, combined WR=81.8%. 3 watcher losers became real wins via L64 (chart-stop saved premium-stop misfires). See `analysis/recommendations/orb_narrow_or_real_fills.json`.


**ORB dedup analysis (~05:40 ET) + script dedup fix (~05:42 ET):** Raw 143 narrow-OR obs = 32 unique bars (4.5× multi-tick inflation, same pattern as V14E L67). Deduped stats: N=32, WR=81.2%, P&L=+$976. Q1-2025 "failure" (0/3 raw) is 1 unique loss on 2025-03-25 (-$42). Q2-2026 concentration drops from 45% raw → 16% deduped. Walk-forward deduped OOS/IS Sharpe=0.667 (PASS; was 1.149 undeduplicated). All three ORB analysis scripts now apply L67 dedup gate: `orb_regime_scan.py`, `orb_narrow_or_walkforward.py`, `orb_vix_gate.py`. Engine-feature spec updated. See `analysis/recommendations/orb-engine-feature-spec.md`.

- [2026-05-21 04:05:37 RESOLVED] crypto-harness drift RED — v02_source_parity + v15_three_source_parity.live are KNOWN_FLAKY (timing jitter, excluded from overall_pass). No engine bug.

- [2026-05-21 05:05:37 RESOLVED] crypto-regression FAIL (exit=1) — Root cause: v23_orb_warmup fixture had OR range=$3.00 which was blocked by newly-wired MAX_OR_RANGE=2.00 gate. Fix: updated fixture to ORL=740.5 (range=$1.50). Full run (70/70 PASS incl. benchmark) confirmed at 05:22 ET. Next cron fire (05:35 ET) should show PASS.

- [2026-05-21 05:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 74.07% in last 24h (60/81) | stage v15_three_source_parity.live pass rate dropped to 83.95% in last 24h (68/81) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 06:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json
- [2026-05-21 ~12:10 ET RESOLVED] window-leak compliance GREEN -- `walk_forward_combination_validator.py:48` fixed (added `_CREATE_NO_WINDOW` constant + `creationflags=_CREATE_NO_WINDOW`). Audit now 0 flags.

[2026-05-21 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-05-21.md

- [2026-05-21 06:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 73.75% in last 24h (59/80) | stage v15_three_source_parity.live pass rate dropped to 83.75% in last 24h (67/80) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 06:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 73.75% in last 24h (59/80) | stage v15_three_source_parity.live pass rate dropped to 83.75% in last 24h (67/80) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 07:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.5% in last 24h (58/80) | stage v15_three_source_parity.live pass rate dropped to 83.75% in last 24h (67/80) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 07:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.25% in last 24h (57/80) | stage v15_three_source_parity.live pass rate dropped to 83.75% in last 24h (67/80) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 08:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.0% in last 24h (56/80) | stage v15_three_source_parity.live pass rate dropped to 83.75% in last 24h (67/80) | v02 source parity drift in 30.91% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 08:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 69.88% in last 24h (58/83) | stage v15_three_source_parity.live pass rate dropped to 84.34% in last 24h (70/83) | v02 source parity drift in 31.2% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-21T12:43:28+00:00
- date_et: 2026-05-21
- total: $390.75 (threshold $30.00)
- claude: $390.70  minimax: $0.04
- claude_sessions: 5

- [2026-05-21 09:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.25% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:30:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2100min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1525min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=653min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:35:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2105min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1530min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=658min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 09:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.25% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:40:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2110min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1535min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=663min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:45:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2115min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1540min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=668min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:50:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2120min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1545min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=673min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T13:55:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2125min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1550min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=678min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:00:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2130min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1555min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=683min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: spend-summary threshold breach
- ts: 2026-05-21T14:00:03+00:00
- date_et: 2026-05-21
- total: $416.89 (threshold $30.00)
- claude: $416.84  minimax: $0.05
- claude_sessions: 15

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:05:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2135min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1560min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=688min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 10:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.2% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:10:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2140min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1565min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=693min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:15:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2145min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1570min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=698min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:20:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2150min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1575min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=703min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:25:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2155min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1580min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=708min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:30:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2160min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1585min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=713min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:35:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2165min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1590min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=718min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 10:35 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00735000 qty=3 entry=0.69]

- [2026-05-21 10:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 30.96% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:40:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2170min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1595min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=723min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:45:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2175min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1600min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=728min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 10:49 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00735000 qty=3 entry=0.69]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:50:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2180min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1605min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=733min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T14:55:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2185min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1610min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=738min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:00:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2190min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1615min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=743min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:05:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2195min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1620min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=748min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 11:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 30.96% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:10:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2200min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1625min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=753min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:15:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2205min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1630min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=758min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:20:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2210min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1635min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=763min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 11:21 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:25:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2215min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1640min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=768min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:30:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2220min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1645min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=773min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:35:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2225min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1650min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=778min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 11:35 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

- [2026-05-21 11:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.06% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:40:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2230min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1655min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=783min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:45:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2235min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1660min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=788min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:50:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2240min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1665min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=793min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 11:50 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T15:55:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2245min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1670min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=798min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:00:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2250min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1675min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=803min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: spend-summary threshold breach
- ts: 2026-05-21T16:00:17+00:00
- date_et: 2026-05-21
- total: $467.99 (threshold $30.00)
- claude: $467.93  minimax: $0.06
- claude_sessions: 61

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:05:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2255min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1680min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=808min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 12:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.25% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:10:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2260min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1685min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=813min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:15:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2265min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1690min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=818min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:20:01+00:00
- count: 3
- mode: soft
  - pid=12324 age=2270min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1695min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=21328 age=823min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:25:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2275min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1700min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:30:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2280min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1705min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:35:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2285min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1710min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 12:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.25% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:40:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2290min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1715min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:45:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2295min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1720min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:50:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2300min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1725min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T16:55:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2305min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1730min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:00:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2310min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1735min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:05:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2315min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1740min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 13:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 31.25% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:10:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2320min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1745min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:15:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2325min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1750min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:20:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2330min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1755min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:25:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2335min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1760min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:30:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2340min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1765min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:35:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2345min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1770min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 13:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 30.52% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:40:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2350min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1775min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:45:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2355min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1780min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:50:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2360min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1785min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T17:55:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2365min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1790min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:00:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2370min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1795min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: spend-summary threshold breach
- ts: 2026-05-21T18:00:19+00:00
- date_et: 2026-05-21
- total: $467.99 (threshold $30.00)
- claude: $467.93  minimax: $0.06
- claude_sessions: 81

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:05:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2375min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1800min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 14:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 30.52% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:10:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2380min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1805min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:15:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2385min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1810min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:20:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2390min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1815min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:25:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2395min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1820min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:30:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2400min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1825min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:35:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2405min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1830min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 14:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.26% in last 24h (62/87) | stage v15_three_source_parity.live pass rate dropped to 85.06% in last 24h (74/87) | v02 source parity drift in 30.52% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:40:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2410min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1835min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:45:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2415min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1840min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:50:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2420min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1845min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 14:50 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T18:55:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2425min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1850min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:00:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2430min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1855min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 15:05 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:05:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2435min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1860min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 15:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.11% in last 24h (61/87) | stage v15_three_source_parity.live pass rate dropped to 83.91% in last 24h (73/87) | v02 source parity drift in 31.69% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:10:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2440min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1865min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:15:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2445min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1870min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 15:18 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:20:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2450min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1875min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:25:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2455min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1880min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:30:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2460min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1885min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 15:34 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:35:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2465min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1890min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

- [2026-05-21 15:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 67.86% in last 24h (57/84) | stage v15_three_source_parity.live pass rate dropped to 82.14% in last 24h (69/84) | v02 source parity drift in 33.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:40:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2470min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1895min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:45:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2475min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1900min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### WARN: session-guard market-hours flag
- ts: 2026-05-21T19:50:01+00:00
- count: 2
- mode: soft
  - pid=12324 age=2480min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
  - pid=3592 age=1905min action=warn cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`
- [2026-05-21 15:50 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260521P00736000 qty=3 entry=0.66]

### WARN: spend-summary threshold breach
- ts: 2026-05-21T20:00:05+00:00
- date_et: 2026-05-21
- total: $501.69 (threshold $30.00)
- claude: $501.63  minimax: $0.07
- claude_sessions: 118

- [2026-05-21 16:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 80.95% in last 24h (68/84) | v02 source parity drift in 35.9% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 16:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 79.76% in last 24h (67/84) | v02 source parity drift in 37.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 21:00:02] gym-session (2026-05-21) → **RED** :: see `automation\state\gym-scorecard-2026-05-21.json`
- [2026-05-21 17:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 78.57% in last 24h (66/84) | v02 source parity drift in 37.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 17:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 78.57% in last 24h (66/84) | v02 source parity drift in 37.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-21T22:00:03+00:00
- date_et: 2026-05-21
- total: $526.32 (threshold $30.00)
- claude: $526.25  minimax: $0.07
- claude_sessions: 122

- [2026-05-21 18:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 78.57% in last 24h (66/84) | v02 source parity drift in 37.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 18:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (56/84) | stage v15_three_source_parity.live pass rate dropped to 78.57% in last 24h (66/84) | v02 source parity drift in 37.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 19:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.67% in last 24h (57/83) | stage v15_three_source_parity.live pass rate dropped to 78.31% in last 24h (65/83) | v02 source parity drift in 35.76% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 19:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.73% in last 24h (58/82) | stage v15_three_source_parity.live pass rate dropped to 78.05% in last 24h (64/82) | v02 source parity drift in 33.72% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-22T00:00:03+00:00
- date_et: 2026-05-21
- total: $526.32 (threshold $30.00)
- claude: $526.25  minimax: $0.07
- claude_sessions: 122

- [2026-05-21 20:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.5% in last 24h (58/80) | stage v15_three_source_parity.live pass rate dropped to 76.25% in last 24h (61/80) | v02 source parity drift in 31.69% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 20:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.15% in last 24h (57/79) | stage v15_three_source_parity.live pass rate dropped to 75.95% in last 24h (60/79) | v02 source parity drift in 31.35% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 21:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.15% in last 24h (57/79) | stage v15_three_source_parity.live pass rate dropped to 75.95% in last 24h (60/79) | v02 source parity drift in 31.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 21:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.43% in last 24h (55/77) | stage v15_three_source_parity.live pass rate dropped to 75.32% in last 24h (58/77) | v02 source parity drift in 31.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-22T02:00:03+00:00
- date_et: 2026-05-21
- total: $533.86 (threshold $30.00)
- claude: $533.76  minimax: $0.10
- claude_sessions: 122

- [2026-05-21 22:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.43% in last 24h (55/77) | stage v15_three_source_parity.live pass rate dropped to 75.32% in last 24h (58/77) | v02 source parity drift in 31.4% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-22T02:12:43+00:00
- date_et: 2026-05-21
- total: $536.30 (threshold $50.00)
- claude: $536.21  minimax: $0.10
- claude_sessions: 122

- [2026-05-21 22:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.23% in last 24h (52/73) | stage v15_three_source_parity.live pass rate dropped to 76.71% in last 24h (56/73) | v02 source parity drift in 31.06% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-05-22T02:44:42+00:00
- task: eod-summary
- date_et: 2026-05-21
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-05-21 23:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 73.61% in last 24h (53/72) | stage v15_three_source_parity.live pass rate dropped to 79.17% in last 24h (57/72) :: see crypto/data/scorecards/drift_report.json

- [2026-05-21 23:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 78.26% in last 24h (54/69) | stage v15_three_source_parity.live pass rate dropped to 84.06% in last 24h (58/69) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 00:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.41% in last 24h (54/68) | stage v15_three_source_parity.live pass rate dropped to 86.76% in last 24h (59/68) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 00:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.1% in last 24h (53/67) | stage v15_three_source_parity.live pass rate dropped to 89.55% in last 24h (60/67) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 01:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 78.46% in last 24h (51/65) | stage v15_three_source_parity.live pass rate dropped to 90.77% in last 24h (59/65) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 01:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 78.46% in last 24h (51/65) | stage v15_three_source_parity.live pass rate dropped to 90.77% in last 24h (59/65) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 02:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.78% in last 24h (49/63) | stage v15_three_source_parity.live pass rate dropped to 90.48% in last 24h (57/63) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 02:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.42% in last 24h (48/62) | stage v15_three_source_parity.live pass rate dropped to 90.32% in last 24h (56/62) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 03:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.67% in last 24h (46/60) | stage v15_three_source_parity.live pass rate dropped to 90.0% in last 24h (54/60) :: see crypto/data/scorecards/drift_report.json
- [2026-05-22 03:30:01] AMBER: pattern_gym drift -- double_top -13.3pp, failed_breakdown_wick 14.1pp

- [2026-05-22 03:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.67% in last 24h (46/60) | stage v15_three_source_parity.live pass rate dropped to 90.0% in last 24h (54/60) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 04:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.27% in last 24h (45/59) | stage v15_three_source_parity.live pass rate dropped to 89.83% in last 24h (53/59) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 04:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.86% in last 24h (44/58) | stage v15_three_source_parity.live pass rate dropped to 89.66% in last 24h (52/58) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 05:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.86% in last 24h (44/58) | stage v15_three_source_parity.live pass rate dropped to 89.66% in last 24h (52/58) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 05:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.0% in last 24h (42/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

[2026-05-22 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-05-22.md

- [2026-05-22 06:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.0% in last 24h (42/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 06:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.0% in last 24h (42/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 07:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.79% in last 24h (43/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 07:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 78.57% in last 24h (44/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 08:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 80.36% in last 24h (45/56) | stage v15_three_source_parity.live pass rate dropped to 89.29% in last 24h (50/56) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 08:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.13% in last 24h (43/53) | stage v15_three_source_parity.live pass rate dropped to 88.68% in last 24h (47/53) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 09:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.59% in last 24h (39/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

---

## [2026-05-22 09:14 ET] OVERNIGHT WORK QUEUE (plan-and-cook tonight after 16:00 ET)

Everything below is queued for the kitchen daemon (Nemotron free tier, $0 burn) + manual Claude work after market close. **NOTHING in this queue fires before 16:00 ET** — heartbeat protected, no token contention with production during market hours.

### Priority 1 — VERIFICATION (must finish tonight)
- [ ] Run gym after circuit breaker writes a real cooldown file mid-session and verify both heartbeats SKIP nothing (true end-to-end test of L3 patch)
- [ ] Audit script that statically detects ANY `Invoke-Claude*` call missing `-TaskName` (prevents L69 from recurring on future PS1 wrappers)
- [ ] Verify Friday's market-hour Claude burn was actually $12 (not $50+) — pull spend-2026-05-22.json and confirm heartbeat-only

### Priority 2 — DOCUMENTATION SYNC
- [ ] CLAUDE.md OP-30 needs the new free-tier-primary path documented (currently OP-30 says "free-tier-first" but doesn't list which tasks were migrated 2026-05-21/22)
- [ ] SCHEDULED-TASKS.md verify `Gamma_MarketHoursCircuitBreaker` row exists + accurate (was added but worth re-checking)
- [ ] CLAUDE.md note that `Gamma_ChartVisionObserver` is currently DISABLED (saves $3.20/day Haiku — doc claims live)

### Priority 3 — KITCHEN AUTONOMY (Nemotron free tier — $0)
- [ ] Cook 5 NLWB level-promotion candidates using only ★★★ levels (not PDL)
- [ ] Cook variant of v14e BEAR_ONLY with VIX_MOD discriminator
- [ ] Cook ORB_NARROW_OR with revised cooldown (current is 4h, sweep 2/4/6/8h)
- [ ] Brainstorm 3 new strategy ideas from Friday's tape

### Priority 4 — CHEF / ANALYST PIPELINE
- [ ] Analyst EOD via free-tier primary (auto-fires 16:45 ET, will be first live run of OP-30 flip)
- [ ] Manager daily verify via free-tier primary (auto-fires 17:30 ET)
- [ ] Verify EOD summary written via Nemotron has the right format for tomorrow's premarket consumption

### Priority 5 — IF TIME
- [ ] Re-enable Gamma_ChartVisionObserver IF J approves on read of this brief (potential $3.20/day extra burn on Haiku is well within margin)
- [ ] Static-analysis test ensuring no PS1 wrapper calls Claude without TaskName

---

## NEXT WAKE FIRE PLAN

The kitchen daemon (PID 37520, alive) will pick up grinder/cook tasks autonomously through the day. No interactive Claude session is needed. After market close, the EOD pipeline will fire on its scheduled cadence (16:00→16:45→17:30). All three analytical tasks now route Nemotron-primary by default.

I will be killed by Gamma_SessionGuard at ~09:35 ET (intended). Continuation work happens autonomously via the scheduled-task / kitchen ecosystem.

---

## [2026-05-22 09:32 ET] GHOST RECONCILER SHIPPED + LIVE

Per J directive "ship reconcile" at 09:25 ET. Verified live for first market open fire.

| Item | Status |
|---|---|
| Script `setup/scripts/ghost_order_reconciler.py` (pure Python urllib REST, no Claude/no MCP) | shipped |
| Wrapper `setup/scripts/run-ghost-reconciler.ps1` (OP-27 L42 hidden-window chain) | shipped |
| Task `Gamma_GhostOrderReconciler` every 1 min 09:30-15:55 ET weekdays | state=Ready, nextRun=09:30 |
| SCHEDULED-TASKS.md registry row | added |
| Dry-run last 24h | 0 ghosts (expected) |
| Live exit | clean exit 0 |
| Cost | **$0/day** |

**Logic:** for each ENTER in `decisions.jsonl` aged 60-600s, query Alpaca orders both accounts; if no order-symbol match within ±180s of the decision timestamp → GHOST. Writes `automation/state/ghost-reconciler-{date}.jsonl` + appends RED block to STATUS.md.

**V1 = alert-only** (per OP-21 watch-first). Auto-place deferred to V2 — risks: double-fill, stale-premium fill, PDT-violating re-attempt. After J observes 1 week of V1 alerts and confirms which can be safely auto-replaced, we promote.

**What J sees today if a ghost happens:** RED block in STATUS.md showing `SAFE|BOLD <symbol> qty=N entry_premium=$X.XX setup=<name> decision_at_utc=<ts>`. Operator decides: place manually on Alpaca paper, or skip.

This closes the "we haven't been getting in many trades" gap — Safe heartbeat ghost entries (the 5/19-5/21 silent failures) will now be VISIBLE within 60 seconds of the missed placement.

### WARN: session-guard market-hours flag
- ts: 2026-05-22T13:30:02+00:00
- count: 1
- mode: hard
  - pid=10440 age=726min action=killed cmd=`C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.142\claude.exe --output-fo`

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T13:32:06+00:00
- ts_et: 2026-05-22T09:32:06
- spend_today_usd: $100.30
- threshold_usd: $100
- sessions_killed: [36452]
- kill_failed: []
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T13:34:06+00:00
- ts_et: 2026-05-22T09:34:06
- spend_today_usd: $107.33
- threshold_usd: $100
- sessions_killed: [41516]
- kill_failed: []
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

- [2026-05-22 09:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.55% in last 24h (38/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T13:46:05+00:00
- ts_et: 2026-05-22T09:46:05
- spend_today_usd: $111.62
- threshold_usd: $100
- sessions_killed: [25280]
- kill_failed: []
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T13:52:04+00:00
- ts_et: 2026-05-22T09:52:04
- spend_today_usd: $125.62
- threshold_usd: $100
- sessions_killed: [33140]
- kill_failed: []
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

### WARN: spend-summary threshold breach
- ts: 2026-05-22T14:00:05+00:00
- date_et: 2026-05-22
- total: $126.46 (threshold $30.00)
- claude: $126.43  minimax: $0.03
- claude_sessions: 10

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T14:04:04+00:00
- ts_et: 2026-05-22T10:04:04
- spend_today_usd: $131.86
- threshold_usd: $100
- sessions_killed: [42772]
- kill_failed: []
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

- [2026-05-22 10:05:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.51% in last 24h (37/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 10:35:38] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.51% in last 24h (37/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 11:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.51% in last 24h (37/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

### CRITICAL: market-hours-circuit-breaker fired
- ts_utc: 2026-05-22T15:24:08+00:00
- ts_et: 2026-05-22T11:24:08
- spend_today_usd: $156.25
- threshold_usd: $100
- sessions_killed: []
- kill_failed: [24960]
- claude_print_exempt: true  # Gamma_Heartbeat keeps trading
- cooldown_reset_in: 60 min
- action_required: review interactive session usage; restart if needed after cooldown

- [2026-05-22 11:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.51% in last 24h (37/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

### WARN: spend-summary threshold breach
- ts: 2026-05-22T16:00:11+00:00
- date_et: 2026-05-22
- total: $167.80 (threshold $30.00)
- claude: $167.77  minimax: $0.03
- claude_sessions: 38

- [2026-05-22 12:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 73.47% in last 24h (36/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 12:35:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.43% in last 24h (35/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json

- [2026-05-22 13:05:37] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 71.43% in last 24h (35/49) | stage v15_three_source_parity.live pass rate dropped to 87.76% in last 24h (43/49) :: see crypto/data/scorecards/drift_report.json
- [2026-05-23 15:16:34] AMBER: pattern_gym drift -- double_top -12.8pp, failed_breakdown_wick 17.4pp

- [2026-05-23 15:16:34] crypto-harness drift RED :: v02 source parity drift in 100.0% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

[2026-05-23 15:16:34] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-05-23.md

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-05-23T19:17:25+00:00
- task: analyst
- date_et: 2026-05-23
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-05-23T19:19:01+00:00
- task: manager
- date_et: 2026-05-23
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-05-23 15:35:37] crypto-harness drift RED :: v02 source parity drift in 100.0% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

## Kitchen
Kitchen: alive, queue 26 pending, last cook 0 min ago, today $0.00, model=?
[2026-05-24 11:38:56] validator-author: shipped v37_tbr_high_vol_gate (offline + live PASS) -- gym 71/71 -> DOCTRINE-ARCHIVE.md OP-26 updated

## Known broken

- [SWARM_INTENTIONALLY_DISABLED] 2026-05-23 Gamma_SwarmPremarket was nuked in infrastructure reset (was one of 33 tasks removed to prevent rate-limit pool starvation from 35 concurrent Claude sessions). Premarket handles SWARM_CONTEXT_UNAVAILABLE gracefully (step 1c). Last stale output (2026-05-22, status=failed) is pre-reset noise. Re-add only when redesigned to route through Nemotron-first (OP-30) — not Claude directly. See docs/RESET-2026-05-23.md.

- [2026-05-24 12:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 92.59% in last 24h (25/27) | stage v08_ribbon.live pass rate dropped to 85.19% in last 24h (23/27) | stage v09_regime.live pass rate dropped to 85.19% in last 24h (23/27) | stage v15_three_source_parity.live pass rate dropped to 74.07% in last 24h (20/27) | stage v37_tbr_high_vol_gate.offline pass rate dropped to 90.0% in last 24h (9/10) | stage v39_orb_signal_reader.offline pass rate dropped to 87.5% in last 24h (7/8) | v02 source parity drift in 90.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-24 13:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.1% in last 24h (27/29) | stage v08_ribbon.live pass rate dropped to 86.21% in last 24h (25/29) | stage v09_regime.live pass rate dropped to 86.21% in last 24h (25/29) | stage v15_three_source_parity.live pass rate dropped to 75.86% in last 24h (22/29) | stage v37_tbr_high_vol_gate.offline pass rate dropped to 91.67% in last 24h (11/12) | stage v39_orb_signal_reader.offline pass rate dropped to 90.0% in last 24h (9/10) | v02 source parity drift in 54.29% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-24 13:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.33% in last 24h (28/30) | stage v08_ribbon.live pass rate dropped to 86.67% in last 24h (26/30) | stage v09_regime.live pass rate dropped to 86.67% in last 24h (26/30) | stage v15_three_source_parity.live pass rate dropped to 76.67% in last 24h (23/30) | stage v37_tbr_high_vol_gate.offline pass rate dropped to 92.31% in last 24h (12/13) | stage v39_orb_signal_reader.offline pass rate dropped to 90.91% in last 24h (10/11) | v02 source parity drift in 38.0% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-05-24 14:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 93.94% in last 24h (31/33) | stage v08_ribbon.live pass rate dropped to 87.88% in last 24h (29/33) | stage v09_regime.live pass rate dropped to 87.88% in last 24h (29/33) | stage v15_three_source_parity.live pass rate dropped to 78.79% in last 24h (26/33) | stage v37_tbr_high_vol_gate.offline pass rate dropped to 93.75% in last 24h (15/16) | stage v39_orb_signal_reader.offline pass rate dropped to 92.86% in last 24h (13/14) :: see crypto/data/scorecards/drift_report.json

- [2026-05-24 14:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 94.59% in last 24h (35/37) | stage v08_ribbon.live pass rate dropped to 89.19% in last 24h (33/37) | stage v09_regime.live pass rate dropped to 89.19% in last 24h (33/37) | stage v15_three_source_parity.live pass rate dropped to 81.08% in last 24h (30/37) | stage v39_orb_signal_reader.offline pass rate dropped to 94.44% in last 24h (17/18) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 18:05:59] crypto-harness drift RED :: latest cron fire FAILED (2026-05-30T22:06:00.421741+00:00) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 18:05:59] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 18:05:59] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-05-30 18:05:59] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-05-30 18:05:59] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-05-30.md

- [2026-05-30 18:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-30T22:27:16.560400+00:00) | fail streak: 2 consecutive fires :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 18:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 18:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-30T22:57:16.497875+00:00) | fail streak: 3 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/3) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/3) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/3) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/3) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/3) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/3) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/3) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/3) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/3) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/3) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/3) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/3) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/3) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/3) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 18:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 19:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-30T23:27:16.552337+00:00) | fail streak: 4 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/4) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/4) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/4) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/4) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/4) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/4) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/4) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/4) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/4) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/4) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/4) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/4) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/4) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/4) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 19:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 19:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-30T23:57:16.530242+00:00) | fail streak: 5 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/5) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/5) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/5) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/5) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/5) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/5) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/5) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/5) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/5) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/5) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/5) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/5) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/5) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/5) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 19:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 20:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T00:27:16.550467+00:00) | fail streak: 6 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/6) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/6) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/6) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/6) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/6) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/6) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/6) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/6) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/6) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/6) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/6) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/6) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/6) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/6) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 20:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 20:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T00:57:16.529020+00:00) | fail streak: 7 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/7) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/7) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/7) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/7) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/7) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/7) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/7) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/7) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/7) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/7) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/7) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/7) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/7) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/7) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 20:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 21:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T01:27:16.552863+00:00) | fail streak: 8 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/8) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/8) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/8) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/8) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/8) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/8) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/8) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/8) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/8) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/8) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/8) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/8) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/8) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/8) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 21:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 21:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T01:57:16.558411+00:00) | fail streak: 9 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/9) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/9) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/9) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/9) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/9) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/9) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/9) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/9) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/9) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/9) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/9) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/9) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/9) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/9) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 21:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 22:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T02:27:16.551437+00:00) | fail streak: 10 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/10) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/10) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/10) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/10) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/10) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/10) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/10) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/10) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/10) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/10) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/10) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/10) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/10) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/10) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 22:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 22:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T02:57:16.546585+00:00) | fail streak: 11 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/11) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/11) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/11) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/11) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/11) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/11) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/11) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/11) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/11) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/11) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/11) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/11) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/11) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/11) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 22:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 23:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T03:27:16.578500+00:00) | fail streak: 12 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/12) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/12) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/12) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/12) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/12) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/12) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/12) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/12) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/12) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/12) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/12) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/12) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/12) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/12) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 23:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-30 23:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T03:57:16.556483+00:00) | fail streak: 13 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/13) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/13) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/13) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/13) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/13) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/13) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/13) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/13) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/13) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/13) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/13) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/13) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/13) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/13) :: see crypto/data/scorecards/drift_report.json

- [2026-05-30 23:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-30.log

- [2026-05-31 00:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T04:27:16.602858+00:00) | fail streak: 14 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/14) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/14) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/14) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/14) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/14) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/14) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/14) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/14) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/14) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/14) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/14) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/14) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/14) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/14) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 00:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 00:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T04:57:16.596163+00:00) | fail streak: 15 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/15) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/15) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/15) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/15) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/15) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/15) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/15) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/15) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/15) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/15) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/15) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/15) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/15) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/15) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 00:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 01:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T05:27:16.605237+00:00) | fail streak: 16 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/16) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/16) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/16) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/16) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/16) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/16) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/16) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/16) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/16) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/16) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/16) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/16) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/16) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/16) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 01:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 01:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T05:57:16.567418+00:00) | fail streak: 17 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/17) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/17) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/17) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/17) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/17) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/17) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/17) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/17) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/17) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/17) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/17) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/17) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/17) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/17) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 01:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 02:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T06:27:16.609549+00:00) | fail streak: 18 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/18) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/18) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/18) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/18) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/18) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/18) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/18) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/18) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/18) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/18) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/18) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/18) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/18) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/18) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 02:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 02:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T06:57:16.617870+00:00) | fail streak: 19 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/19) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/19) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/19) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/19) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/19) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/19) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/19) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/19) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/19) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/19) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/19) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/19) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/19) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/19) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 02:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 03:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T07:27:16.631134+00:00) | fail streak: 20 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/20) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/20) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/20) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/20) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/20) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/20) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/20) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/20) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/20) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/20) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/20) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/20) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/20) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/20) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 03:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 03:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T07:57:16.642152+00:00) | fail streak: 21 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/21) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/21) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/21) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/21) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/21) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/21) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/21) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/21) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/21) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/21) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/21) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/21) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/21) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/21) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 03:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 04:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T08:27:16.609769+00:00) | fail streak: 22 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/22) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/22) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/22) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/22) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/22) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/22) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/22) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/22) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/22) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/22) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/22) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/22) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/22) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/22) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 04:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 04:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T08:57:16.643455+00:00) | fail streak: 23 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/23) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/23) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/23) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/23) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/23) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/23) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/23) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/23) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/23) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/23) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/23) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/23) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/23) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/23) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 04:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 05:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T09:27:16.642949+00:00) | fail streak: 24 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/24) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/24) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/24) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/24) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/24) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/24) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/24) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/24) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/24) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/24) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/24) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/24) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/24) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/24) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 05:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 05:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T09:57:16.650531+00:00) | fail streak: 25 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/25) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/25) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/25) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/25) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/25) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/25) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/25) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/25) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/25) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/25) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/25) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/25) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/25) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/25) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 05:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 06:00:02] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-05-31 06:00:02] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-05-31 06:00:02] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-05-31.md

- [2026-05-31 06:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T10:27:16.654951+00:00) | fail streak: 26 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/26) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/26) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/26) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/26) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/26) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/26) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/26) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/26) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/26) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/26) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/26) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/26) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/26) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/26) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 06:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 06:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T10:57:16.689448+00:00) | fail streak: 27 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/27) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/27) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/27) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/27) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/27) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/27) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/27) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/27) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/27) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/27) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/27) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/27) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/27) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/27) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 06:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 07:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T11:27:16.661192+00:00) | fail streak: 28 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/28) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/28) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/28) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/28) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/28) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/28) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/28) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/28) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/28) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/28) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/28) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/28) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/28) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/28) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 07:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 07:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T11:57:16.662605+00:00) | fail streak: 29 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/29) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/29) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/29) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/29) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/29) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/29) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/29) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/29) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/29) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/29) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/29) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/29) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/29) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/29) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 07:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 08:27:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T12:27:16.703693+00:00) | fail streak: 30 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/30) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/30) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/30) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/30) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/30) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/30) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/30) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/30) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/30) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/30) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/30) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/30) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/30) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/30) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 08:27:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 08:57:16] crypto-harness drift RED :: latest cron fire FAILED (2026-05-31T12:57:16.679317+00:00) | fail streak: 31 consecutive fires | stage v01_closed_bar.live pass rate dropped to 0.0% in last 24h (0/31) | stage v02_source_parity pass rate dropped to 0.0% in last 24h (0/31) | stage v03_indicators.live pass rate dropped to 0.0% in last 24h (0/31) | stage v04_candlesticks.live pass rate dropped to 0.0% in last 24h (0/31) | stage v05_levels.live pass rate dropped to 0.0% in last 24h (0/31) | stage v06_trendlines.live pass rate dropped to 0.0% in last 24h (0/31) | stage v07_volume.live pass rate dropped to 0.0% in last 24h (0/31) | stage v08_ribbon.live pass rate dropped to 0.0% in last 24h (0/31) | stage v09_regime.live pass rate dropped to 0.0% in last 24h (0/31) | stage v10_divergence.live pass rate dropped to 0.0% in last 24h (0/31) | stage v11_breakout.live pass rate dropped to 0.0% in last 24h (0/31) | stage v12_multi_timeframe.live pass rate dropped to 0.0% in last 24h (0/31) | stage v14_sweep.live pass rate dropped to 0.0% in last 24h (0/31) | stage v15_three_source_parity.live pass rate dropped to 0.0% in last 24h (0/31) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 08:57:16] crypto-regression FAIL (exit=1) - see C:\Users\jackw\Desktop\42\automation\state\logs\crypto-regression-2026-05-31.log

- [2026-05-31 09:27:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 3.12% in last 24h (1/32) | stage v02_source_parity pass rate dropped to 3.12% in last 24h (1/32) | stage v03_indicators.live pass rate dropped to 3.12% in last 24h (1/32) | stage v04_candlesticks.live pass rate dropped to 3.12% in last 24h (1/32) | stage v05_levels.live pass rate dropped to 3.12% in last 24h (1/32) | stage v06_trendlines.live pass rate dropped to 3.12% in last 24h (1/32) | stage v07_volume.live pass rate dropped to 3.12% in last 24h (1/32) | stage v08_ribbon.live pass rate dropped to 3.12% in last 24h (1/32) | stage v09_regime.live pass rate dropped to 3.12% in last 24h (1/32) | stage v10_divergence.live pass rate dropped to 3.12% in last 24h (1/32) | stage v11_breakout.live pass rate dropped to 3.12% in last 24h (1/32) | stage v12_multi_timeframe.live pass rate dropped to 3.12% in last 24h (1/32) | stage v14_sweep.live pass rate dropped to 3.12% in last 24h (1/32) | stage v15_three_source_parity.live pass rate dropped to 3.12% in last 24h (1/32) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 09:57:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 6.06% in last 24h (2/33) | stage v02_source_parity pass rate dropped to 6.06% in last 24h (2/33) | stage v03_indicators.live pass rate dropped to 6.06% in last 24h (2/33) | stage v04_candlesticks.live pass rate dropped to 6.06% in last 24h (2/33) | stage v05_levels.live pass rate dropped to 6.06% in last 24h (2/33) | stage v06_trendlines.live pass rate dropped to 6.06% in last 24h (2/33) | stage v07_volume.live pass rate dropped to 6.06% in last 24h (2/33) | stage v08_ribbon.live pass rate dropped to 6.06% in last 24h (2/33) | stage v09_regime.live pass rate dropped to 6.06% in last 24h (2/33) | stage v10_divergence.live pass rate dropped to 6.06% in last 24h (2/33) | stage v11_breakout.live pass rate dropped to 6.06% in last 24h (2/33) | stage v12_multi_timeframe.live pass rate dropped to 6.06% in last 24h (2/33) | stage v14_sweep.live pass rate dropped to 6.06% in last 24h (2/33) | stage v15_three_source_parity.live pass rate dropped to 6.06% in last 24h (2/33) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 10:27:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 8.82% in last 24h (3/34) | stage v02_source_parity pass rate dropped to 8.82% in last 24h (3/34) | stage v03_indicators.live pass rate dropped to 8.82% in last 24h (3/34) | stage v04_candlesticks.live pass rate dropped to 8.82% in last 24h (3/34) | stage v05_levels.live pass rate dropped to 8.82% in last 24h (3/34) | stage v06_trendlines.live pass rate dropped to 8.82% in last 24h (3/34) | stage v07_volume.live pass rate dropped to 8.82% in last 24h (3/34) | stage v08_ribbon.live pass rate dropped to 8.82% in last 24h (3/34) | stage v09_regime.live pass rate dropped to 8.82% in last 24h (3/34) | stage v10_divergence.live pass rate dropped to 8.82% in last 24h (3/34) | stage v11_breakout.live pass rate dropped to 8.82% in last 24h (3/34) | stage v12_multi_timeframe.live pass rate dropped to 8.82% in last 24h (3/34) | stage v14_sweep.live pass rate dropped to 8.82% in last 24h (3/34) | stage v15_three_source_parity.live pass rate dropped to 8.82% in last 24h (3/34) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 10:57:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 11.43% in last 24h (4/35) | stage v02_source_parity pass rate dropped to 11.43% in last 24h (4/35) | stage v03_indicators.live pass rate dropped to 11.43% in last 24h (4/35) | stage v04_candlesticks.live pass rate dropped to 11.43% in last 24h (4/35) | stage v05_levels.live pass rate dropped to 11.43% in last 24h (4/35) | stage v06_trendlines.live pass rate dropped to 11.43% in last 24h (4/35) | stage v07_volume.live pass rate dropped to 11.43% in last 24h (4/35) | stage v08_ribbon.live pass rate dropped to 11.43% in last 24h (4/35) | stage v09_regime.live pass rate dropped to 11.43% in last 24h (4/35) | stage v10_divergence.live pass rate dropped to 11.43% in last 24h (4/35) | stage v11_breakout.live pass rate dropped to 11.43% in last 24h (4/35) | stage v12_multi_timeframe.live pass rate dropped to 11.43% in last 24h (4/35) | stage v14_sweep.live pass rate dropped to 11.43% in last 24h (4/35) | stage v15_three_source_parity.live pass rate dropped to 11.43% in last 24h (4/35) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 11:27:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 13.89% in last 24h (5/36) | stage v02_source_parity pass rate dropped to 13.89% in last 24h (5/36) | stage v03_indicators.live pass rate dropped to 13.89% in last 24h (5/36) | stage v04_candlesticks.live pass rate dropped to 13.89% in last 24h (5/36) | stage v05_levels.live pass rate dropped to 13.89% in last 24h (5/36) | stage v06_trendlines.live pass rate dropped to 13.89% in last 24h (5/36) | stage v07_volume.live pass rate dropped to 13.89% in last 24h (5/36) | stage v08_ribbon.live pass rate dropped to 13.89% in last 24h (5/36) | stage v09_regime.live pass rate dropped to 13.89% in last 24h (5/36) | stage v10_divergence.live pass rate dropped to 13.89% in last 24h (5/36) | stage v11_breakout.live pass rate dropped to 13.89% in last 24h (5/36) | stage v12_multi_timeframe.live pass rate dropped to 13.89% in last 24h (5/36) | stage v14_sweep.live pass rate dropped to 13.89% in last 24h (5/36) | stage v15_three_source_parity.live pass rate dropped to 13.89% in last 24h (5/36) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 11:57:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 16.22% in last 24h (6/37) | stage v02_source_parity pass rate dropped to 16.22% in last 24h (6/37) | stage v03_indicators.live pass rate dropped to 16.22% in last 24h (6/37) | stage v04_candlesticks.live pass rate dropped to 16.22% in last 24h (6/37) | stage v05_levels.live pass rate dropped to 16.22% in last 24h (6/37) | stage v06_trendlines.live pass rate dropped to 16.22% in last 24h (6/37) | stage v07_volume.live pass rate dropped to 16.22% in last 24h (6/37) | stage v08_ribbon.live pass rate dropped to 16.22% in last 24h (6/37) | stage v09_regime.live pass rate dropped to 16.22% in last 24h (6/37) | stage v10_divergence.live pass rate dropped to 16.22% in last 24h (6/37) | stage v11_breakout.live pass rate dropped to 16.22% in last 24h (6/37) | stage v12_multi_timeframe.live pass rate dropped to 16.22% in last 24h (6/37) | stage v14_sweep.live pass rate dropped to 16.22% in last 24h (6/37) | stage v15_three_source_parity.live pass rate dropped to 16.22% in last 24h (6/37) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 12:27:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 18.42% in last 24h (7/38) | stage v02_source_parity pass rate dropped to 18.42% in last 24h (7/38) | stage v03_indicators.live pass rate dropped to 18.42% in last 24h (7/38) | stage v04_candlesticks.live pass rate dropped to 18.42% in last 24h (7/38) | stage v05_levels.live pass rate dropped to 18.42% in last 24h (7/38) | stage v06_trendlines.live pass rate dropped to 18.42% in last 24h (7/38) | stage v07_volume.live pass rate dropped to 18.42% in last 24h (7/38) | stage v08_ribbon.live pass rate dropped to 18.42% in last 24h (7/38) | stage v09_regime.live pass rate dropped to 18.42% in last 24h (7/38) | stage v10_divergence.live pass rate dropped to 18.42% in last 24h (7/38) | stage v11_breakout.live pass rate dropped to 18.42% in last 24h (7/38) | stage v12_multi_timeframe.live pass rate dropped to 18.42% in last 24h (7/38) | stage v14_sweep.live pass rate dropped to 18.42% in last 24h (7/38) | stage v15_three_source_parity.live pass rate dropped to 18.42% in last 24h (7/38) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 12:57:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 20.51% in last 24h (8/39) | stage v02_source_parity pass rate dropped to 20.51% in last 24h (8/39) | stage v03_indicators.live pass rate dropped to 20.51% in last 24h (8/39) | stage v04_candlesticks.live pass rate dropped to 20.51% in last 24h (8/39) | stage v05_levels.live pass rate dropped to 20.51% in last 24h (8/39) | stage v06_trendlines.live pass rate dropped to 20.51% in last 24h (8/39) | stage v07_volume.live pass rate dropped to 20.51% in last 24h (8/39) | stage v08_ribbon.live pass rate dropped to 20.51% in last 24h (8/39) | stage v09_regime.live pass rate dropped to 20.51% in last 24h (8/39) | stage v10_divergence.live pass rate dropped to 20.51% in last 24h (8/39) | stage v11_breakout.live pass rate dropped to 20.51% in last 24h (8/39) | stage v12_multi_timeframe.live pass rate dropped to 20.51% in last 24h (8/39) | stage v14_sweep.live pass rate dropped to 20.51% in last 24h (8/39) | stage v15_three_source_parity.live pass rate dropped to 20.51% in last 24h (8/39) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 13:27:16] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 22.5% in last 24h (9/40) | stage v02_source_parity pass rate dropped to 22.5% in last 24h (9/40) | stage v03_indicators.live pass rate dropped to 22.5% in last 24h (9/40) | stage v04_candlesticks.live pass rate dropped to 22.5% in last 24h (9/40) | stage v05_levels.live pass rate dropped to 22.5% in last 24h (9/40) | stage v06_trendlines.live pass rate dropped to 22.5% in last 24h (9/40) | stage v07_volume.live pass rate dropped to 22.5% in last 24h (9/40) | stage v08_ribbon.live pass rate dropped to 22.5% in last 24h (9/40) | stage v09_regime.live pass rate dropped to 22.5% in last 24h (9/40) | stage v10_divergence.live pass rate dropped to 22.5% in last 24h (9/40) | stage v11_breakout.live pass rate dropped to 22.5% in last 24h (9/40) | stage v12_multi_timeframe.live pass rate dropped to 22.5% in last 24h (9/40) | stage v14_sweep.live pass rate dropped to 22.5% in last 24h (9/40) | stage v15_three_source_parity.live pass rate dropped to 22.5% in last 24h (9/40) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 13:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 24.39% in last 24h (10/41) | stage v02_source_parity pass rate dropped to 24.39% in last 24h (10/41) | stage v03_indicators.live pass rate dropped to 24.39% in last 24h (10/41) | stage v04_candlesticks.live pass rate dropped to 24.39% in last 24h (10/41) | stage v05_levels.live pass rate dropped to 24.39% in last 24h (10/41) | stage v06_trendlines.live pass rate dropped to 24.39% in last 24h (10/41) | stage v07_volume.live pass rate dropped to 24.39% in last 24h (10/41) | stage v08_ribbon.live pass rate dropped to 24.39% in last 24h (10/41) | stage v09_regime.live pass rate dropped to 24.39% in last 24h (10/41) | stage v10_divergence.live pass rate dropped to 24.39% in last 24h (10/41) | stage v11_breakout.live pass rate dropped to 24.39% in last 24h (10/41) | stage v12_multi_timeframe.live pass rate dropped to 24.39% in last 24h (10/41) | stage v14_sweep.live pass rate dropped to 24.39% in last 24h (10/41) | stage v15_three_source_parity.live pass rate dropped to 24.39% in last 24h (10/41) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 14:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 26.19% in last 24h (11/42) | stage v02_source_parity pass rate dropped to 26.19% in last 24h (11/42) | stage v03_indicators.live pass rate dropped to 26.19% in last 24h (11/42) | stage v04_candlesticks.live pass rate dropped to 26.19% in last 24h (11/42) | stage v05_levels.live pass rate dropped to 26.19% in last 24h (11/42) | stage v06_trendlines.live pass rate dropped to 26.19% in last 24h (11/42) | stage v07_volume.live pass rate dropped to 26.19% in last 24h (11/42) | stage v08_ribbon.live pass rate dropped to 26.19% in last 24h (11/42) | stage v09_regime.live pass rate dropped to 26.19% in last 24h (11/42) | stage v10_divergence.live pass rate dropped to 26.19% in last 24h (11/42) | stage v11_breakout.live pass rate dropped to 26.19% in last 24h (11/42) | stage v12_multi_timeframe.live pass rate dropped to 26.19% in last 24h (11/42) | stage v14_sweep.live pass rate dropped to 26.19% in last 24h (11/42) | stage v15_three_source_parity.live pass rate dropped to 26.19% in last 24h (11/42) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 14:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 27.91% in last 24h (12/43) | stage v02_source_parity pass rate dropped to 27.91% in last 24h (12/43) | stage v03_indicators.live pass rate dropped to 27.91% in last 24h (12/43) | stage v04_candlesticks.live pass rate dropped to 27.91% in last 24h (12/43) | stage v05_levels.live pass rate dropped to 27.91% in last 24h (12/43) | stage v06_trendlines.live pass rate dropped to 27.91% in last 24h (12/43) | stage v07_volume.live pass rate dropped to 27.91% in last 24h (12/43) | stage v08_ribbon.live pass rate dropped to 27.91% in last 24h (12/43) | stage v09_regime.live pass rate dropped to 27.91% in last 24h (12/43) | stage v10_divergence.live pass rate dropped to 27.91% in last 24h (12/43) | stage v11_breakout.live pass rate dropped to 27.91% in last 24h (12/43) | stage v12_multi_timeframe.live pass rate dropped to 27.91% in last 24h (12/43) | stage v14_sweep.live pass rate dropped to 27.91% in last 24h (12/43) | stage v15_three_source_parity.live pass rate dropped to 27.91% in last 24h (12/43) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 15:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 29.55% in last 24h (13/44) | stage v02_source_parity pass rate dropped to 29.55% in last 24h (13/44) | stage v03_indicators.live pass rate dropped to 29.55% in last 24h (13/44) | stage v04_candlesticks.live pass rate dropped to 29.55% in last 24h (13/44) | stage v05_levels.live pass rate dropped to 29.55% in last 24h (13/44) | stage v06_trendlines.live pass rate dropped to 29.55% in last 24h (13/44) | stage v07_volume.live pass rate dropped to 29.55% in last 24h (13/44) | stage v08_ribbon.live pass rate dropped to 29.55% in last 24h (13/44) | stage v09_regime.live pass rate dropped to 29.55% in last 24h (13/44) | stage v10_divergence.live pass rate dropped to 29.55% in last 24h (13/44) | stage v11_breakout.live pass rate dropped to 29.55% in last 24h (13/44) | stage v12_multi_timeframe.live pass rate dropped to 29.55% in last 24h (13/44) | stage v14_sweep.live pass rate dropped to 29.55% in last 24h (13/44) | stage v15_three_source_parity.live pass rate dropped to 29.55% in last 24h (13/44) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 15:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 31.11% in last 24h (14/45) | stage v02_source_parity pass rate dropped to 28.89% in last 24h (13/45) | stage v03_indicators.live pass rate dropped to 31.11% in last 24h (14/45) | stage v04_candlesticks.live pass rate dropped to 31.11% in last 24h (14/45) | stage v05_levels.live pass rate dropped to 31.11% in last 24h (14/45) | stage v06_trendlines.live pass rate dropped to 31.11% in last 24h (14/45) | stage v07_volume.live pass rate dropped to 31.11% in last 24h (14/45) | stage v08_ribbon.live pass rate dropped to 31.11% in last 24h (14/45) | stage v09_regime.live pass rate dropped to 31.11% in last 24h (14/45) | stage v10_divergence.live pass rate dropped to 31.11% in last 24h (14/45) | stage v11_breakout.live pass rate dropped to 31.11% in last 24h (14/45) | stage v12_multi_timeframe.live pass rate dropped to 31.11% in last 24h (14/45) | stage v14_sweep.live pass rate dropped to 31.11% in last 24h (14/45) | stage v15_three_source_parity.live pass rate dropped to 31.11% in last 24h (14/45) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 16:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 32.61% in last 24h (15/46) | stage v02_source_parity pass rate dropped to 28.26% in last 24h (13/46) | stage v03_indicators.live pass rate dropped to 32.61% in last 24h (15/46) | stage v04_candlesticks.live pass rate dropped to 32.61% in last 24h (15/46) | stage v05_levels.live pass rate dropped to 32.61% in last 24h (15/46) | stage v06_trendlines.live pass rate dropped to 32.61% in last 24h (15/46) | stage v07_volume.live pass rate dropped to 32.61% in last 24h (15/46) | stage v08_ribbon.live pass rate dropped to 32.61% in last 24h (15/46) | stage v09_regime.live pass rate dropped to 32.61% in last 24h (15/46) | stage v10_divergence.live pass rate dropped to 32.61% in last 24h (15/46) | stage v11_breakout.live pass rate dropped to 32.61% in last 24h (15/46) | stage v12_multi_timeframe.live pass rate dropped to 32.61% in last 24h (15/46) | stage v14_sweep.live pass rate dropped to 32.61% in last 24h (15/46) | stage v15_three_source_parity.live pass rate dropped to 32.61% in last 24h (15/46) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 16:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 34.04% in last 24h (16/47) | stage v02_source_parity pass rate dropped to 27.66% in last 24h (13/47) | stage v03_indicators.live pass rate dropped to 34.04% in last 24h (16/47) | stage v04_candlesticks.live pass rate dropped to 34.04% in last 24h (16/47) | stage v05_levels.live pass rate dropped to 34.04% in last 24h (16/47) | stage v06_trendlines.live pass rate dropped to 34.04% in last 24h (16/47) | stage v07_volume.live pass rate dropped to 34.04% in last 24h (16/47) | stage v08_ribbon.live pass rate dropped to 34.04% in last 24h (16/47) | stage v09_regime.live pass rate dropped to 34.04% in last 24h (16/47) | stage v10_divergence.live pass rate dropped to 34.04% in last 24h (16/47) | stage v11_breakout.live pass rate dropped to 34.04% in last 24h (16/47) | stage v12_multi_timeframe.live pass rate dropped to 34.04% in last 24h (16/47) | stage v14_sweep.live pass rate dropped to 34.04% in last 24h (16/47) | stage v15_three_source_parity.live pass rate dropped to 34.04% in last 24h (16/47) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 17:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 35.42% in last 24h (17/48) | stage v02_source_parity pass rate dropped to 29.17% in last 24h (14/48) | stage v03_indicators.live pass rate dropped to 35.42% in last 24h (17/48) | stage v04_candlesticks.live pass rate dropped to 35.42% in last 24h (17/48) | stage v05_levels.live pass rate dropped to 35.42% in last 24h (17/48) | stage v06_trendlines.live pass rate dropped to 35.42% in last 24h (17/48) | stage v07_volume.live pass rate dropped to 35.42% in last 24h (17/48) | stage v08_ribbon.live pass rate dropped to 35.42% in last 24h (17/48) | stage v09_regime.live pass rate dropped to 35.42% in last 24h (17/48) | stage v10_divergence.live pass rate dropped to 35.42% in last 24h (17/48) | stage v11_breakout.live pass rate dropped to 35.42% in last 24h (17/48) | stage v12_multi_timeframe.live pass rate dropped to 35.42% in last 24h (17/48) | stage v14_sweep.live pass rate dropped to 35.42% in last 24h (17/48) | stage v15_three_source_parity.live pass rate dropped to 35.42% in last 24h (17/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 17:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 36.73% in last 24h (18/49) | stage v02_source_parity pass rate dropped to 30.61% in last 24h (15/49) | stage v03_indicators.live pass rate dropped to 36.73% in last 24h (18/49) | stage v04_candlesticks.live pass rate dropped to 36.73% in last 24h (18/49) | stage v05_levels.live pass rate dropped to 36.73% in last 24h (18/49) | stage v06_trendlines.live pass rate dropped to 36.73% in last 24h (18/49) | stage v07_volume.live pass rate dropped to 36.73% in last 24h (18/49) | stage v08_ribbon.live pass rate dropped to 36.73% in last 24h (18/49) | stage v09_regime.live pass rate dropped to 36.73% in last 24h (18/49) | stage v10_divergence.live pass rate dropped to 36.73% in last 24h (18/49) | stage v11_breakout.live pass rate dropped to 36.73% in last 24h (18/49) | stage v12_multi_timeframe.live pass rate dropped to 36.73% in last 24h (18/49) | stage v14_sweep.live pass rate dropped to 36.73% in last 24h (18/49) | stage v15_three_source_parity.live pass rate dropped to 36.73% in last 24h (18/49) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 18:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 39.58% in last 24h (19/48) | stage v02_source_parity pass rate dropped to 33.33% in last 24h (16/48) | stage v03_indicators.live pass rate dropped to 39.58% in last 24h (19/48) | stage v04_candlesticks.live pass rate dropped to 39.58% in last 24h (19/48) | stage v05_levels.live pass rate dropped to 39.58% in last 24h (19/48) | stage v06_trendlines.live pass rate dropped to 39.58% in last 24h (19/48) | stage v07_volume.live pass rate dropped to 39.58% in last 24h (19/48) | stage v08_ribbon.live pass rate dropped to 39.58% in last 24h (19/48) | stage v09_regime.live pass rate dropped to 39.58% in last 24h (19/48) | stage v10_divergence.live pass rate dropped to 39.58% in last 24h (19/48) | stage v11_breakout.live pass rate dropped to 39.58% in last 24h (19/48) | stage v12_multi_timeframe.live pass rate dropped to 39.58% in last 24h (19/48) | stage v14_sweep.live pass rate dropped to 39.58% in last 24h (19/48) | stage v15_three_source_parity.live pass rate dropped to 39.58% in last 24h (19/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 18:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 41.67% in last 24h (20/48) | stage v02_source_parity pass rate dropped to 35.42% in last 24h (17/48) | stage v03_indicators.live pass rate dropped to 41.67% in last 24h (20/48) | stage v04_candlesticks.live pass rate dropped to 41.67% in last 24h (20/48) | stage v05_levels.live pass rate dropped to 41.67% in last 24h (20/48) | stage v06_trendlines.live pass rate dropped to 41.67% in last 24h (20/48) | stage v07_volume.live pass rate dropped to 41.67% in last 24h (20/48) | stage v08_ribbon.live pass rate dropped to 41.67% in last 24h (20/48) | stage v09_regime.live pass rate dropped to 41.67% in last 24h (20/48) | stage v10_divergence.live pass rate dropped to 41.67% in last 24h (20/48) | stage v11_breakout.live pass rate dropped to 41.67% in last 24h (20/48) | stage v12_multi_timeframe.live pass rate dropped to 41.67% in last 24h (20/48) | stage v14_sweep.live pass rate dropped to 41.67% in last 24h (20/48) | stage v15_three_source_parity.live pass rate dropped to 41.67% in last 24h (20/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 19:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 43.75% in last 24h (21/48) | stage v02_source_parity pass rate dropped to 37.5% in last 24h (18/48) | stage v03_indicators.live pass rate dropped to 43.75% in last 24h (21/48) | stage v04_candlesticks.live pass rate dropped to 43.75% in last 24h (21/48) | stage v05_levels.live pass rate dropped to 43.75% in last 24h (21/48) | stage v06_trendlines.live pass rate dropped to 43.75% in last 24h (21/48) | stage v07_volume.live pass rate dropped to 43.75% in last 24h (21/48) | stage v08_ribbon.live pass rate dropped to 43.75% in last 24h (21/48) | stage v09_regime.live pass rate dropped to 43.75% in last 24h (21/48) | stage v10_divergence.live pass rate dropped to 43.75% in last 24h (21/48) | stage v11_breakout.live pass rate dropped to 43.75% in last 24h (21/48) | stage v12_multi_timeframe.live pass rate dropped to 43.75% in last 24h (21/48) | stage v14_sweep.live pass rate dropped to 43.75% in last 24h (21/48) | stage v15_three_source_parity.live pass rate dropped to 43.75% in last 24h (21/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 19:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 45.83% in last 24h (22/48) | stage v02_source_parity pass rate dropped to 39.58% in last 24h (19/48) | stage v03_indicators.live pass rate dropped to 45.83% in last 24h (22/48) | stage v04_candlesticks.live pass rate dropped to 45.83% in last 24h (22/48) | stage v05_levels.live pass rate dropped to 45.83% in last 24h (22/48) | stage v06_trendlines.live pass rate dropped to 45.83% in last 24h (22/48) | stage v07_volume.live pass rate dropped to 45.83% in last 24h (22/48) | stage v08_ribbon.live pass rate dropped to 45.83% in last 24h (22/48) | stage v09_regime.live pass rate dropped to 45.83% in last 24h (22/48) | stage v10_divergence.live pass rate dropped to 45.83% in last 24h (22/48) | stage v11_breakout.live pass rate dropped to 45.83% in last 24h (22/48) | stage v12_multi_timeframe.live pass rate dropped to 45.83% in last 24h (22/48) | stage v14_sweep.live pass rate dropped to 45.83% in last 24h (22/48) | stage v15_three_source_parity.live pass rate dropped to 45.83% in last 24h (22/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 20:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 47.92% in last 24h (23/48) | stage v02_source_parity pass rate dropped to 41.67% in last 24h (20/48) | stage v03_indicators.live pass rate dropped to 47.92% in last 24h (23/48) | stage v04_candlesticks.live pass rate dropped to 47.92% in last 24h (23/48) | stage v05_levels.live pass rate dropped to 47.92% in last 24h (23/48) | stage v06_trendlines.live pass rate dropped to 47.92% in last 24h (23/48) | stage v07_volume.live pass rate dropped to 47.92% in last 24h (23/48) | stage v08_ribbon.live pass rate dropped to 47.92% in last 24h (23/48) | stage v09_regime.live pass rate dropped to 47.92% in last 24h (23/48) | stage v10_divergence.live pass rate dropped to 47.92% in last 24h (23/48) | stage v11_breakout.live pass rate dropped to 47.92% in last 24h (23/48) | stage v12_multi_timeframe.live pass rate dropped to 47.92% in last 24h (23/48) | stage v14_sweep.live pass rate dropped to 47.92% in last 24h (23/48) | stage v15_three_source_parity.live pass rate dropped to 47.92% in last 24h (23/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 20:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 50.0% in last 24h (24/48) | stage v02_source_parity pass rate dropped to 43.75% in last 24h (21/48) | stage v03_indicators.live pass rate dropped to 50.0% in last 24h (24/48) | stage v04_candlesticks.live pass rate dropped to 50.0% in last 24h (24/48) | stage v05_levels.live pass rate dropped to 50.0% in last 24h (24/48) | stage v06_trendlines.live pass rate dropped to 50.0% in last 24h (24/48) | stage v07_volume.live pass rate dropped to 50.0% in last 24h (24/48) | stage v08_ribbon.live pass rate dropped to 50.0% in last 24h (24/48) | stage v09_regime.live pass rate dropped to 50.0% in last 24h (24/48) | stage v10_divergence.live pass rate dropped to 50.0% in last 24h (24/48) | stage v11_breakout.live pass rate dropped to 50.0% in last 24h (24/48) | stage v12_multi_timeframe.live pass rate dropped to 50.0% in last 24h (24/48) | stage v14_sweep.live pass rate dropped to 50.0% in last 24h (24/48) | stage v15_three_source_parity.live pass rate dropped to 50.0% in last 24h (24/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 21:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 52.08% in last 24h (25/48) | stage v02_source_parity pass rate dropped to 45.83% in last 24h (22/48) | stage v03_indicators.live pass rate dropped to 52.08% in last 24h (25/48) | stage v04_candlesticks.live pass rate dropped to 52.08% in last 24h (25/48) | stage v05_levels.live pass rate dropped to 52.08% in last 24h (25/48) | stage v06_trendlines.live pass rate dropped to 52.08% in last 24h (25/48) | stage v07_volume.live pass rate dropped to 52.08% in last 24h (25/48) | stage v08_ribbon.live pass rate dropped to 52.08% in last 24h (25/48) | stage v09_regime.live pass rate dropped to 52.08% in last 24h (25/48) | stage v10_divergence.live pass rate dropped to 52.08% in last 24h (25/48) | stage v11_breakout.live pass rate dropped to 52.08% in last 24h (25/48) | stage v12_multi_timeframe.live pass rate dropped to 52.08% in last 24h (25/48) | stage v14_sweep.live pass rate dropped to 52.08% in last 24h (25/48) | stage v15_three_source_parity.live pass rate dropped to 52.08% in last 24h (25/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 21:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 54.17% in last 24h (26/48) | stage v02_source_parity pass rate dropped to 47.92% in last 24h (23/48) | stage v03_indicators.live pass rate dropped to 54.17% in last 24h (26/48) | stage v04_candlesticks.live pass rate dropped to 54.17% in last 24h (26/48) | stage v05_levels.live pass rate dropped to 54.17% in last 24h (26/48) | stage v06_trendlines.live pass rate dropped to 54.17% in last 24h (26/48) | stage v07_volume.live pass rate dropped to 54.17% in last 24h (26/48) | stage v08_ribbon.live pass rate dropped to 54.17% in last 24h (26/48) | stage v09_regime.live pass rate dropped to 54.17% in last 24h (26/48) | stage v10_divergence.live pass rate dropped to 54.17% in last 24h (26/48) | stage v11_breakout.live pass rate dropped to 54.17% in last 24h (26/48) | stage v12_multi_timeframe.live pass rate dropped to 54.17% in last 24h (26/48) | stage v14_sweep.live pass rate dropped to 54.17% in last 24h (26/48) | stage v15_three_source_parity.live pass rate dropped to 54.17% in last 24h (26/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 22:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 56.25% in last 24h (27/48) | stage v02_source_parity pass rate dropped to 50.0% in last 24h (24/48) | stage v03_indicators.live pass rate dropped to 56.25% in last 24h (27/48) | stage v04_candlesticks.live pass rate dropped to 56.25% in last 24h (27/48) | stage v05_levels.live pass rate dropped to 56.25% in last 24h (27/48) | stage v06_trendlines.live pass rate dropped to 56.25% in last 24h (27/48) | stage v07_volume.live pass rate dropped to 56.25% in last 24h (27/48) | stage v08_ribbon.live pass rate dropped to 56.25% in last 24h (27/48) | stage v09_regime.live pass rate dropped to 56.25% in last 24h (27/48) | stage v10_divergence.live pass rate dropped to 56.25% in last 24h (27/48) | stage v11_breakout.live pass rate dropped to 56.25% in last 24h (27/48) | stage v12_multi_timeframe.live pass rate dropped to 56.25% in last 24h (27/48) | stage v14_sweep.live pass rate dropped to 56.25% in last 24h (27/48) | stage v15_three_source_parity.live pass rate dropped to 56.25% in last 24h (27/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 22:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 58.33% in last 24h (28/48) | stage v02_source_parity pass rate dropped to 52.08% in last 24h (25/48) | stage v03_indicators.live pass rate dropped to 58.33% in last 24h (28/48) | stage v04_candlesticks.live pass rate dropped to 58.33% in last 24h (28/48) | stage v05_levels.live pass rate dropped to 58.33% in last 24h (28/48) | stage v06_trendlines.live pass rate dropped to 58.33% in last 24h (28/48) | stage v07_volume.live pass rate dropped to 58.33% in last 24h (28/48) | stage v08_ribbon.live pass rate dropped to 58.33% in last 24h (28/48) | stage v09_regime.live pass rate dropped to 58.33% in last 24h (28/48) | stage v10_divergence.live pass rate dropped to 58.33% in last 24h (28/48) | stage v11_breakout.live pass rate dropped to 58.33% in last 24h (28/48) | stage v12_multi_timeframe.live pass rate dropped to 58.33% in last 24h (28/48) | stage v14_sweep.live pass rate dropped to 58.33% in last 24h (28/48) | stage v15_three_source_parity.live pass rate dropped to 58.33% in last 24h (28/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 23:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 60.42% in last 24h (29/48) | stage v02_source_parity pass rate dropped to 54.17% in last 24h (26/48) | stage v03_indicators.live pass rate dropped to 60.42% in last 24h (29/48) | stage v04_candlesticks.live pass rate dropped to 60.42% in last 24h (29/48) | stage v05_levels.live pass rate dropped to 60.42% in last 24h (29/48) | stage v06_trendlines.live pass rate dropped to 60.42% in last 24h (29/48) | stage v07_volume.live pass rate dropped to 60.42% in last 24h (29/48) | stage v08_ribbon.live pass rate dropped to 60.42% in last 24h (29/48) | stage v09_regime.live pass rate dropped to 60.42% in last 24h (29/48) | stage v10_divergence.live pass rate dropped to 60.42% in last 24h (29/48) | stage v11_breakout.live pass rate dropped to 60.42% in last 24h (29/48) | stage v12_multi_timeframe.live pass rate dropped to 60.42% in last 24h (29/48) | stage v14_sweep.live pass rate dropped to 60.42% in last 24h (29/48) | stage v15_three_source_parity.live pass rate dropped to 60.42% in last 24h (29/48) :: see crypto/data/scorecards/drift_report.json

- [2026-05-31 23:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 62.5% in last 24h (30/48) | stage v02_source_parity pass rate dropped to 56.25% in last 24h (27/48) | stage v03_indicators.live pass rate dropped to 62.5% in last 24h (30/48) | stage v04_candlesticks.live pass rate dropped to 62.5% in last 24h (30/48) | stage v05_levels.live pass rate dropped to 62.5% in last 24h (30/48) | stage v06_trendlines.live pass rate dropped to 62.5% in last 24h (30/48) | stage v07_volume.live pass rate dropped to 62.5% in last 24h (30/48) | stage v08_ribbon.live pass rate dropped to 62.5% in last 24h (30/48) | stage v09_regime.live pass rate dropped to 62.5% in last 24h (30/48) | stage v10_divergence.live pass rate dropped to 62.5% in last 24h (30/48) | stage v11_breakout.live pass rate dropped to 62.5% in last 24h (30/48) | stage v12_multi_timeframe.live pass rate dropped to 62.5% in last 24h (30/48) | stage v14_sweep.live pass rate dropped to 62.5% in last 24h (30/48) | stage v15_three_source_parity.live pass rate dropped to 62.5% in last 24h (30/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 00:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 64.58% in last 24h (31/48) | stage v02_source_parity pass rate dropped to 58.33% in last 24h (28/48) | stage v03_indicators.live pass rate dropped to 64.58% in last 24h (31/48) | stage v04_candlesticks.live pass rate dropped to 64.58% in last 24h (31/48) | stage v05_levels.live pass rate dropped to 64.58% in last 24h (31/48) | stage v06_trendlines.live pass rate dropped to 64.58% in last 24h (31/48) | stage v07_volume.live pass rate dropped to 64.58% in last 24h (31/48) | stage v08_ribbon.live pass rate dropped to 64.58% in last 24h (31/48) | stage v09_regime.live pass rate dropped to 64.58% in last 24h (31/48) | stage v10_divergence.live pass rate dropped to 64.58% in last 24h (31/48) | stage v11_breakout.live pass rate dropped to 64.58% in last 24h (31/48) | stage v12_multi_timeframe.live pass rate dropped to 64.58% in last 24h (31/48) | stage v14_sweep.live pass rate dropped to 64.58% in last 24h (31/48) | stage v15_three_source_parity.live pass rate dropped to 64.58% in last 24h (31/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 00:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 66.67% in last 24h (32/48) | stage v02_source_parity pass rate dropped to 60.42% in last 24h (29/48) | stage v03_indicators.live pass rate dropped to 66.67% in last 24h (32/48) | stage v04_candlesticks.live pass rate dropped to 66.67% in last 24h (32/48) | stage v05_levels.live pass rate dropped to 66.67% in last 24h (32/48) | stage v06_trendlines.live pass rate dropped to 66.67% in last 24h (32/48) | stage v07_volume.live pass rate dropped to 66.67% in last 24h (32/48) | stage v08_ribbon.live pass rate dropped to 66.67% in last 24h (32/48) | stage v09_regime.live pass rate dropped to 66.67% in last 24h (32/48) | stage v10_divergence.live pass rate dropped to 66.67% in last 24h (32/48) | stage v11_breakout.live pass rate dropped to 66.67% in last 24h (32/48) | stage v12_multi_timeframe.live pass rate dropped to 66.67% in last 24h (32/48) | stage v14_sweep.live pass rate dropped to 66.67% in last 24h (32/48) | stage v15_three_source_parity.live pass rate dropped to 66.67% in last 24h (32/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 01:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 68.75% in last 24h (33/48) | stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) | stage v03_indicators.live pass rate dropped to 68.75% in last 24h (33/48) | stage v04_candlesticks.live pass rate dropped to 68.75% in last 24h (33/48) | stage v05_levels.live pass rate dropped to 68.75% in last 24h (33/48) | stage v06_trendlines.live pass rate dropped to 68.75% in last 24h (33/48) | stage v07_volume.live pass rate dropped to 68.75% in last 24h (33/48) | stage v08_ribbon.live pass rate dropped to 68.75% in last 24h (33/48) | stage v09_regime.live pass rate dropped to 68.75% in last 24h (33/48) | stage v10_divergence.live pass rate dropped to 68.75% in last 24h (33/48) | stage v11_breakout.live pass rate dropped to 68.75% in last 24h (33/48) | stage v12_multi_timeframe.live pass rate dropped to 68.75% in last 24h (33/48) | stage v14_sweep.live pass rate dropped to 68.75% in last 24h (33/48) | stage v15_three_source_parity.live pass rate dropped to 68.75% in last 24h (33/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 01:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 70.83% in last 24h (34/48) | stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) | stage v03_indicators.live pass rate dropped to 70.83% in last 24h (34/48) | stage v04_candlesticks.live pass rate dropped to 70.83% in last 24h (34/48) | stage v05_levels.live pass rate dropped to 70.83% in last 24h (34/48) | stage v06_trendlines.live pass rate dropped to 70.83% in last 24h (34/48) | stage v07_volume.live pass rate dropped to 70.83% in last 24h (34/48) | stage v08_ribbon.live pass rate dropped to 70.83% in last 24h (34/48) | stage v09_regime.live pass rate dropped to 70.83% in last 24h (34/48) | stage v10_divergence.live pass rate dropped to 70.83% in last 24h (34/48) | stage v11_breakout.live pass rate dropped to 70.83% in last 24h (34/48) | stage v12_multi_timeframe.live pass rate dropped to 70.83% in last 24h (34/48) | stage v14_sweep.live pass rate dropped to 70.83% in last 24h (34/48) | stage v15_three_source_parity.live pass rate dropped to 70.83% in last 24h (34/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 02:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 72.92% in last 24h (35/48) | stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) | stage v03_indicators.live pass rate dropped to 72.92% in last 24h (35/48) | stage v04_candlesticks.live pass rate dropped to 72.92% in last 24h (35/48) | stage v05_levels.live pass rate dropped to 72.92% in last 24h (35/48) | stage v06_trendlines.live pass rate dropped to 72.92% in last 24h (35/48) | stage v07_volume.live pass rate dropped to 72.92% in last 24h (35/48) | stage v08_ribbon.live pass rate dropped to 72.92% in last 24h (35/48) | stage v09_regime.live pass rate dropped to 72.92% in last 24h (35/48) | stage v10_divergence.live pass rate dropped to 72.92% in last 24h (35/48) | stage v11_breakout.live pass rate dropped to 72.92% in last 24h (35/48) | stage v12_multi_timeframe.live pass rate dropped to 72.92% in last 24h (35/48) | stage v14_sweep.live pass rate dropped to 72.92% in last 24h (35/48) | stage v15_three_source_parity.live pass rate dropped to 72.92% in last 24h (35/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 02:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 75.0% in last 24h (36/48) | stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) | stage v03_indicators.live pass rate dropped to 75.0% in last 24h (36/48) | stage v04_candlesticks.live pass rate dropped to 75.0% in last 24h (36/48) | stage v05_levels.live pass rate dropped to 75.0% in last 24h (36/48) | stage v06_trendlines.live pass rate dropped to 75.0% in last 24h (36/48) | stage v07_volume.live pass rate dropped to 75.0% in last 24h (36/48) | stage v08_ribbon.live pass rate dropped to 75.0% in last 24h (36/48) | stage v09_regime.live pass rate dropped to 75.0% in last 24h (36/48) | stage v10_divergence.live pass rate dropped to 75.0% in last 24h (36/48) | stage v11_breakout.live pass rate dropped to 75.0% in last 24h (36/48) | stage v12_multi_timeframe.live pass rate dropped to 75.0% in last 24h (36/48) | stage v14_sweep.live pass rate dropped to 75.0% in last 24h (36/48) | stage v15_three_source_parity.live pass rate dropped to 75.0% in last 24h (36/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 03:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 77.08% in last 24h (37/48) | stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) | stage v03_indicators.live pass rate dropped to 77.08% in last 24h (37/48) | stage v04_candlesticks.live pass rate dropped to 77.08% in last 24h (37/48) | stage v05_levels.live pass rate dropped to 77.08% in last 24h (37/48) | stage v06_trendlines.live pass rate dropped to 77.08% in last 24h (37/48) | stage v07_volume.live pass rate dropped to 77.08% in last 24h (37/48) | stage v08_ribbon.live pass rate dropped to 77.08% in last 24h (37/48) | stage v09_regime.live pass rate dropped to 77.08% in last 24h (37/48) | stage v10_divergence.live pass rate dropped to 77.08% in last 24h (37/48) | stage v11_breakout.live pass rate dropped to 77.08% in last 24h (37/48) | stage v12_multi_timeframe.live pass rate dropped to 77.08% in last 24h (37/48) | stage v14_sweep.live pass rate dropped to 77.08% in last 24h (37/48) | stage v15_three_source_parity.live pass rate dropped to 77.08% in last 24h (37/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 03:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 79.17% in last 24h (38/48) | stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) | stage v03_indicators.live pass rate dropped to 79.17% in last 24h (38/48) | stage v04_candlesticks.live pass rate dropped to 79.17% in last 24h (38/48) | stage v05_levels.live pass rate dropped to 79.17% in last 24h (38/48) | stage v06_trendlines.live pass rate dropped to 79.17% in last 24h (38/48) | stage v07_volume.live pass rate dropped to 79.17% in last 24h (38/48) | stage v08_ribbon.live pass rate dropped to 79.17% in last 24h (38/48) | stage v09_regime.live pass rate dropped to 79.17% in last 24h (38/48) | stage v10_divergence.live pass rate dropped to 79.17% in last 24h (38/48) | stage v11_breakout.live pass rate dropped to 79.17% in last 24h (38/48) | stage v12_multi_timeframe.live pass rate dropped to 79.17% in last 24h (38/48) | stage v14_sweep.live pass rate dropped to 79.17% in last 24h (38/48) | stage v15_three_source_parity.live pass rate dropped to 79.17% in last 24h (38/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 04:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 81.25% in last 24h (39/48) | stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) | stage v03_indicators.live pass rate dropped to 81.25% in last 24h (39/48) | stage v04_candlesticks.live pass rate dropped to 81.25% in last 24h (39/48) | stage v05_levels.live pass rate dropped to 81.25% in last 24h (39/48) | stage v06_trendlines.live pass rate dropped to 81.25% in last 24h (39/48) | stage v07_volume.live pass rate dropped to 81.25% in last 24h (39/48) | stage v08_ribbon.live pass rate dropped to 81.25% in last 24h (39/48) | stage v09_regime.live pass rate dropped to 81.25% in last 24h (39/48) | stage v10_divergence.live pass rate dropped to 81.25% in last 24h (39/48) | stage v11_breakout.live pass rate dropped to 81.25% in last 24h (39/48) | stage v12_multi_timeframe.live pass rate dropped to 81.25% in last 24h (39/48) | stage v14_sweep.live pass rate dropped to 81.25% in last 24h (39/48) | stage v15_three_source_parity.live pass rate dropped to 81.25% in last 24h (39/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 04:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 83.33% in last 24h (40/48) | stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) | stage v03_indicators.live pass rate dropped to 83.33% in last 24h (40/48) | stage v04_candlesticks.live pass rate dropped to 83.33% in last 24h (40/48) | stage v05_levels.live pass rate dropped to 83.33% in last 24h (40/48) | stage v06_trendlines.live pass rate dropped to 83.33% in last 24h (40/48) | stage v07_volume.live pass rate dropped to 83.33% in last 24h (40/48) | stage v08_ribbon.live pass rate dropped to 83.33% in last 24h (40/48) | stage v09_regime.live pass rate dropped to 83.33% in last 24h (40/48) | stage v10_divergence.live pass rate dropped to 83.33% in last 24h (40/48) | stage v11_breakout.live pass rate dropped to 83.33% in last 24h (40/48) | stage v12_multi_timeframe.live pass rate dropped to 83.33% in last 24h (40/48) | stage v14_sweep.live pass rate dropped to 83.33% in last 24h (40/48) | stage v15_three_source_parity.live pass rate dropped to 83.33% in last 24h (40/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 05:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 85.42% in last 24h (41/48) | stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) | stage v03_indicators.live pass rate dropped to 85.42% in last 24h (41/48) | stage v04_candlesticks.live pass rate dropped to 85.42% in last 24h (41/48) | stage v05_levels.live pass rate dropped to 85.42% in last 24h (41/48) | stage v06_trendlines.live pass rate dropped to 85.42% in last 24h (41/48) | stage v07_volume.live pass rate dropped to 85.42% in last 24h (41/48) | stage v08_ribbon.live pass rate dropped to 85.42% in last 24h (41/48) | stage v09_regime.live pass rate dropped to 85.42% in last 24h (41/48) | stage v10_divergence.live pass rate dropped to 85.42% in last 24h (41/48) | stage v11_breakout.live pass rate dropped to 85.42% in last 24h (41/48) | stage v12_multi_timeframe.live pass rate dropped to 85.42% in last 24h (41/48) | stage v14_sweep.live pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 85.42% in last 24h (41/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 05:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 87.5% in last 24h (42/48) | stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) | stage v03_indicators.live pass rate dropped to 87.5% in last 24h (42/48) | stage v04_candlesticks.live pass rate dropped to 87.5% in last 24h (42/48) | stage v05_levels.live pass rate dropped to 87.5% in last 24h (42/48) | stage v06_trendlines.live pass rate dropped to 87.5% in last 24h (42/48) | stage v07_volume.live pass rate dropped to 87.5% in last 24h (42/48) | stage v08_ribbon.live pass rate dropped to 87.5% in last 24h (42/48) | stage v09_regime.live pass rate dropped to 87.5% in last 24h (42/48) | stage v10_divergence.live pass rate dropped to 87.5% in last 24h (42/48) | stage v11_breakout.live pass rate dropped to 87.5% in last 24h (42/48) | stage v12_multi_timeframe.live pass rate dropped to 87.5% in last 24h (42/48) | stage v14_sweep.live pass rate dropped to 87.5% in last 24h (42/48) | stage v15_three_source_parity.live pass rate dropped to 87.5% in last 24h (42/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 06:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-06-01 06:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-06-01 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-01.md

- [2026-06-01 06:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 89.58% in last 24h (43/48) | stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) | stage v03_indicators.live pass rate dropped to 89.58% in last 24h (43/48) | stage v04_candlesticks.live pass rate dropped to 89.58% in last 24h (43/48) | stage v05_levels.live pass rate dropped to 89.58% in last 24h (43/48) | stage v06_trendlines.live pass rate dropped to 89.58% in last 24h (43/48) | stage v07_volume.live pass rate dropped to 89.58% in last 24h (43/48) | stage v08_ribbon.live pass rate dropped to 89.58% in last 24h (43/48) | stage v09_regime.live pass rate dropped to 89.58% in last 24h (43/48) | stage v10_divergence.live pass rate dropped to 89.58% in last 24h (43/48) | stage v11_breakout.live pass rate dropped to 89.58% in last 24h (43/48) | stage v12_multi_timeframe.live pass rate dropped to 89.58% in last 24h (43/48) | stage v14_sweep.live pass rate dropped to 89.58% in last 24h (43/48) | stage v15_three_source_parity.live pass rate dropped to 89.58% in last 24h (43/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 06:57:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 91.67% in last 24h (44/48) | stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v03_indicators.live pass rate dropped to 91.67% in last 24h (44/48) | stage v04_candlesticks.live pass rate dropped to 91.67% in last 24h (44/48) | stage v05_levels.live pass rate dropped to 91.67% in last 24h (44/48) | stage v06_trendlines.live pass rate dropped to 91.67% in last 24h (44/48) | stage v07_volume.live pass rate dropped to 91.67% in last 24h (44/48) | stage v08_ribbon.live pass rate dropped to 91.67% in last 24h (44/48) | stage v09_regime.live pass rate dropped to 91.67% in last 24h (44/48) | stage v10_divergence.live pass rate dropped to 91.67% in last 24h (44/48) | stage v11_breakout.live pass rate dropped to 91.67% in last 24h (44/48) | stage v12_multi_timeframe.live pass rate dropped to 91.67% in last 24h (44/48) | stage v14_sweep.live pass rate dropped to 91.67% in last 24h (44/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 07:27:15] crypto-harness drift RED :: stage v01_closed_bar.live pass rate dropped to 93.75% in last 24h (45/48) | stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) | stage v03_indicators.live pass rate dropped to 93.75% in last 24h (45/48) | stage v04_candlesticks.live pass rate dropped to 93.75% in last 24h (45/48) | stage v05_levels.live pass rate dropped to 93.75% in last 24h (45/48) | stage v06_trendlines.live pass rate dropped to 93.75% in last 24h (45/48) | stage v07_volume.live pass rate dropped to 93.75% in last 24h (45/48) | stage v08_ribbon.live pass rate dropped to 93.75% in last 24h (45/48) | stage v09_regime.live pass rate dropped to 93.75% in last 24h (45/48) | stage v10_divergence.live pass rate dropped to 93.75% in last 24h (45/48) | stage v11_breakout.live pass rate dropped to 93.75% in last 24h (45/48) | stage v12_multi_timeframe.live pass rate dropped to 93.75% in last 24h (45/48) | stage v14_sweep.live pass rate dropped to 93.75% in last 24h (45/48) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (45/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 07:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 08:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 08:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 09:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 09:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 10:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 10:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 11:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 11:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 12:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 12:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 13:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 13:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 14:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-01 14:47 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 14:48 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 14:52 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 14:55 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]

- [2026-06-01 14:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-01 14:58 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:01 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:04 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:07 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:10 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:13 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:16 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:18 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:22 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:25 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]

- [2026-06-01 15:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-01 15:28 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:32 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]
- [2026-06-01 15:33 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260601C00758000 qty=5 entry=1.8]

- [2026-06-01 15:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 16:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 16:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 17:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 17:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 18:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 18:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 19:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 19:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 20:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 20:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 21:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 21:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 02:15:05] gym-session (2026-06-01) → **RED** :: see `automation\state\gym-scorecard-2026-06-01.json`
- [2026-06-02 02:17:11] gym-session (2026-06-01) → **RED** :: see `automation\state\gym-scorecard-2026-06-01.json`
- [2026-06-02 02:22:23] gym-session (2026-06-01) → **RED** :: see `automation\state\gym-scorecard-2026-06-01.json`
- [2026-06-01 22:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 22:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 23:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-01 23:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 00:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 00:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 01:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 01:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 02:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 02:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 03:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 03:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 04:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 04:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 05:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 05:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

[2026-06-02 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-02.md

- [2026-06-02 06:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 06:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 07:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 07:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 08:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 08:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 09:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 09:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 10:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-02 10:56 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]

- [2026-06-02 10:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-02 10:58 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]
- [2026-06-02 11:01 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]
- [2026-06-02 11:06 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]
- [2026-06-02 11:09 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]
- [2026-06-02 11:21 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87]
- [2026-06-02 11:26 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]

- [2026-06-02 11:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-02 11:28 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:31 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:35 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:37 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:40 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:43 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:46 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:49 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:47 ET] RED GHOST-POSITION (Bold): Alpaca shows 2 open (758C qty3 +$84 GHOST/untracked + 760C qty4 -$100 tracked); current-position-bold.json tracks only 760C. Root cause: Bold took a 2nd entry (760C) while 758C open -> single-position state file overwrote/orphaned the 758C. Risk: +$84 winner unmanaged + next aggressive tick may mismatch-kill-switch Bold. Recommend close 758C to lock +$84 + resolve mismatch. Root-cause Bold double-entry state bug at close.
- [2026-06-02 11:52 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 11:55 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]

- [2026-06-02 11:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-02 11:58 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 12:02 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 12:04 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 12:08 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 12:10 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]
- [2026-06-02 12:13 ET] RED: atomic-bracket-guard found 2 naked SPY 0DTE option position(s) [bold:SPY260602C00758000 qty=3 entry=1.87, bold:SPY260602C00760000 qty=4 entry=0.98]

- [2026-06-02 12:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 79.17% in last 24h (38/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 12:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
- [2026-06-02 13:18 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260602C00761000 qty=3 entry=0.13]
- [2026-06-02 13:25 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260602C00761000 qty=3 entry=0.13]

- [2026-06-02 13:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 13:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 14:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 14:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 15:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 15:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-06-02T20:00:47+00:00
- task: eod-summary
- date_et: 2026-06-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-02 16:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-06-02T20:45:40+00:00
- task: analyst
- date_et: 2026-06-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-02 16:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 21:00:01] gym-session (2026-06-02) → **RED** :: see `automation\state\gym-scorecard-2026-06-02.json`
- [2026-06-02 17:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-06-02T21:31:14+00:00
- task: manager
- date_et: 2026-06-02
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-02 17:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.08% in last 24h (37/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 18:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.0% in last 24h (36/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 18:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 19:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 19:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 30.33% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 20:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.05% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 20:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.1% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 21:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.1% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 21:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.1% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 22:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 30.47% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 22:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 23:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-02 23:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.92% in last 24h (35/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 00:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.83% in last 24h (34/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 00:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 30.03% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 01:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.1% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 01:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.28% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 02:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.28% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 02:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.23% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 03:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.14% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 03:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.14% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 04:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.14% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 04:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.14% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 05:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.14% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 05:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.38% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

[2026-06-03 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-03.md

- [2026-06-03 06:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 35.5% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 06:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.57% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 07:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 39.35% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 07:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 39.35% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 08:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 39.35% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 08:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 62.5% in last 24h (30/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 39.35% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 09:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.87% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 09:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.33% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 10:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.24% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 10:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.24% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 11:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.39% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 11:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.58% in last 24h (31/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 37.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json
- [2026-06-03 12:21 ET] RED: atomic-bracket-guard found 1 naked SPY 0DTE option position(s) [safe:SPY260603C00758000 qty=3 entry=0.2]

- [2026-06-03 12:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (32/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 36.59% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 12:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 34.57% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 13:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.68% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 13:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.83% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 14:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.88% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 14:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 33.88% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 15:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 34.03% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-03 15:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.75% in last 24h (33/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 34.03% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-06-03T20:01:15+00:00
- task: eod-summary
- date_et: 2026-06-03
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

[2026-06-06 13:47:30] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-06.md

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-06-06T17:50:23+00:00
- task: analyst
- date_et: 2026-06-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-06-06T17:54:18+00:00
- task: manager
- date_et: 2026-06-06
- route: free-tier-primary
- ok: True
- cost_usd: 0.0043

- [2026-06-06 14:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 33.33% in last 24h (1/3) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 14:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 50.0% in last 24h (2/4) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 15:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 60.0% in last 24h (3/5) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 15:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 66.67% in last 24h (4/6) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 16:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (5/7) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 16:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 75.0% in last 24h (6/8) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 17:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 77.78% in last 24h (7/9) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 17:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 80.0% in last 24h (8/10) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 18:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 81.82% in last 24h (9/11) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 18:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 83.33% in last 24h (10/12) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 19:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 84.62% in last 24h (11/13) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 19:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 85.71% in last 24h (12/14) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 20:27:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 86.67% in last 24h (13/15) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 20:57:15] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 87.5% in last 24h (14/16) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 21:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 88.24% in last 24h (15/17) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 21:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 88.89% in last 24h (16/18) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 22:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 89.47% in last 24h (17/19) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 22:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 90.0% in last 24h (18/20) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 23:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 90.48% in last 24h (19/21) :: see crypto/data/scorecards/drift_report.json

- [2026-06-06 23:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 90.91% in last 24h (20/22) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 00:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 91.3% in last 24h (21/23) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 00:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (22/24) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 01:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 92.0% in last 24h (23/25) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 01:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 92.31% in last 24h (24/26) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 02:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 92.59% in last 24h (25/27) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 02:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 92.86% in last 24h (26/28) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 03:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 93.1% in last 24h (27/29) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 03:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 93.33% in last 24h (28/30) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 04:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 93.55% in last 24h (29/31) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 04:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (30/32) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 05:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 93.94% in last 24h (31/33) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 05:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.12% in last 24h (32/34) :: see crypto/data/scorecards/drift_report.json

[2026-06-07 06:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-07.md

- [2026-06-07 06:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.29% in last 24h (33/35) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 06:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.44% in last 24h (34/36) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 07:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.59% in last 24h (35/37) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 07:57:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.74% in last 24h (36/38) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 08:27:16] crypto-harness drift RED :: stage v15_three_source_parity.live pass rate dropped to 94.87% in last 24h (37/39) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 09:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 92.68% in last 24h (38/41) -- but v15 (3-source) = 95.12% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 09:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 90.48% in last 24h (38/42) -- but v15 (3-source) = 95.24% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 10:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 90.7% in last 24h (39/43) -- but v15 (3-source) = 95.35% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 10:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 90.91% in last 24h (40/44) -- but v15 (3-source) = 95.45% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 11:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.11% in last 24h (41/45) -- but v15 (3-source) = 95.56% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 11:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.3% in last 24h (42/46) -- but v15 (3-source) = 95.65% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 12:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.49% in last 24h (43/47) -- but v15 (3-source) = 95.74% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 12:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 13:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.84% in last 24h (45/49) -- but v15 (3-source) = 95.92% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 13:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 14:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 14:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 15:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 15:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 16:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 16:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 17:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 17:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 91.67% in last 24h (44/48) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 18:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 89.58% in last 24h (43/48) -- but v15 (3-source) = 97.92% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 18:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 87.5% in last 24h (42/48) -- but v15 (3-source) = 95.83% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 19:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 93.75% in last 24h (45/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 19:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 20:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 85.42% in last 24h (41/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 20:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 83.33% in last 24h (40/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-07 21:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 81.25% in last 24h (39/48) | stage v15_three_source_parity.live pass rate dropped to 91.67% in last 24h (44/48) :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 15:21:39] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 42.47% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 15:21:39] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

[2026-06-08 15:21:39] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-08.md

- [2026-06-08 15:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 42.47% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 15:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 42.47% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-06-08T20:01:04+00:00
- task: eod-summary
- date_et: 2026-06-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-08 16:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 57.14% in last 24h (8/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 44.62% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-06-08T20:45:48+00:00
- task: analyst
- date_et: 2026-06-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-08 16:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (7/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 52.15% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 21:00:01] gym-session (2026-06-08) → **RED** :: see `automation\state\gym-scorecard-2026-06-08.json`
- [2026-06-08 17:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 42.86% in last 24h (6/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 59.68% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-06-08T21:33:04+00:00
- task: manager
- date_et: 2026-06-08
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-06-08 17:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 42.86% in last 24h (6/14) | stage v15_three_source_parity.live pass rate dropped to 71.43% in last 24h (10/14) | v02 source parity drift in 65.95% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 18:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (7/14) | stage v15_three_source_parity.live pass rate dropped to 78.57% in last 24h (11/14) | v02 source parity drift in 61.29% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 18:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 57.14% in last 24h (8/14) | stage v15_three_source_parity.live pass rate dropped to 85.71% in last 24h (12/14) | v02 source parity drift in 53.76% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 19:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) | stage v15_three_source_parity.live pass rate dropped to 92.86% in last 24h (13/14) | v02 source parity drift in 46.24% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 19:57:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 38.92% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-08 20:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 64.29% in last 24h (9/14) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 38.71% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 15:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 80.0% in last 24h (4/5) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 16:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (4/6) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 16:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 57.14% in last 24h (4/7) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 34.48% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 17:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (4/8) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 44.12% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 17:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 44.44% in last 24h (4/9) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 50.86% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 18:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (5/10) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 45.8% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 18:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 45.45% in last 24h (5/11) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 41.38% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 19:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (6/12) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 38.99% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 19:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 53.85% in last 24h (7/13) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 35.63% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 20:27:16] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 50.0% in last 24h (7/14) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 32.98% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 20:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 53.33% in last 24h (8/15) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact | v02 source parity drift in 30.69% of last-24h iterations :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 21:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 56.25% in last 24h (9/16) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 21:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 58.82% in last 24h (10/17) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 22:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 61.11% in last 24h (11/18) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 22:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 63.16% in last 24h (12/19) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 23:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 65.0% in last 24h (13/20) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-14 23:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 66.67% in last 24h (14/21) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 00:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 68.18% in last 24h (15/22) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 00:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 69.57% in last 24h (16/23) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 01:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 70.83% in last 24h (17/24) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 01:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 72.0% in last 24h (18/25) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 02:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 73.08% in last 24h (19/26) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 02:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 74.07% in last 24h (20/27) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 03:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.0% in last 24h (21/28) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 03:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 75.86% in last 24h (22/29) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 04:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

[2026-06-15 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-06-15.md

- [2026-06-15 04:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 76.67% in last 24h (23/30) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 04:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 77.42% in last 24h (24/31) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

- [2026-06-15 05:27:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 78.12% in last 24h (25/32) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json
