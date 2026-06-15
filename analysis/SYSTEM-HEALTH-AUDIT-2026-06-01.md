# System Health + Uptime Audit — 2026-06-01 (20:11 ET, J-requested)

**Verdict: the "no TV = no trades" hole is closed and verified. Task registry was lying (claimed 35, reality 15) — now reconciled and GREEN. Two code-level window-leak risks fixed. Fleet is clean except two leftover Claude sessions that need your call.**

---

## 1. ROOT CAUSE — why TV was dark this morning

Not "Gamma can't turn TV on." TV *was* launched at 08:00. The hole is that **nothing watched it after that.**

Evidence chain:
- `Gamma_LaunchTV` ran **08:00:01** today, result `0x0` (success).
- Every TradingView process on the box started **10:37 AM**.
- **Nothing in the codebase launches TV except the 08:00 task** → the 10:37 start was a *manual* relaunch (you).
- `heartbeat.md` has **zero** references to TV / CDP / port 9222 / relaunch → when the chart goes dark mid-session, the engine keeps logging blind `HOLD`s and never notices.

**Net: ~09:30→10:37 ET the engine was blind (≈67 min into the session). It would have stayed blind until 08:00 tomorrow if you hadn't relaunched.** (Today specifically, the post-10:37 setups were `bull 9/11` near-misses blocked by spread-chop, so no *filled* trade was provably lost — but the blind window is the unacceptable part.)

---

## 2. FIXED + VERIFIED

| # | Fix | Verification |
|---|---|---|
| 1 | **`Gamma_TvWatchdog`** — new task, every 5 min 08:05–16:00 ET weekdays. Checks CDP:9222; relaunches TV if dead (kill+relaunch if hung, fresh launch if gone); idempotent no-op when live. Also flags a stale `Gamma_Heartbeat` to STATUS.md. Reuses the proven launcher — no new launch logic. $0/day. | Registered (Interactive logon, 5-min repeat). Ran direct → `exit 0`, `tv_action: healthy`. Ran via full scheduler chain → `LastTaskResult: 0`, status rewritten, **no window leak** (checked: zero stray console/wscript/powershell windows). |
| 2 | **Window-leak fixes** in `backtest/autoresearch/_launch_grinders.py` (lines 55, 71) — the two `subprocess.run` calls (wmic + taskkill) had no `CREATE_NO_WINDOW`. Flagged RED by the 06:00 leak audit. Added the flag. | `CREATE_NO_WINDOW` already defined at module top; both calls now pass it. |
| 3 | **Task registry reconciled.** `SCHEDULED-TASKS.md` claimed **35 active**; reality is **15**. The daily audit was permanently RED (23 STALE entries). Rewrote `## Active` to the real 15; moved nuked tasks to a `## Reference` section (knowledge kept, parser ignores). | `audit_scheduled_tasks.py` → **HEALTH: GREEN**, 15=15, no flags. |
| 4 | **CLAUDE.md synced** — stale "9 tasks" → accurate 15; added `Gamma_TvWatchdog` to the lifecycle table. | — |

---

## 3. SCORECARD

| Area | Status | Notes |
|---|---|---|
| TradingView / CDP | 🟢 GREEN (now self-healing) | Up now (BATS:SPY 5m, api_available). Watchdog covers 08:05–16:00. |
| Heartbeat | 🟢 GREEN | Fired all day (last 15:54, result 0x0). Now watched for staleness by TvWatchdog during RTH. |
| Window leaks | 🟢 GREEN | 2 code-level risks fixed. No leaked windows in live process scan. Real-time leak *detector* (`WindowLeakDetectorKeepalive`) is offline since the reset — daily static scan still runs via `Gamma_CryptoDaily`. |
| Scheduled tasks | 🟢 GREEN | 15 tasks, all justified, all hidden-window, registry = reality. |
| Process fleet | 🟢 GREEN | kitchen daemon, sniper grinder (2h, self-exits), crypto grinder all healthy consoleless pythonw. No orphans. |
| Daemons / Claude sessions | 🟢 GREEN | Both leftover sessions cleared (19452 self-exited, 30744 killed). |

---

## 4. NEEDS YOUR CALL

**(a) Two leftover Claude-code sessions** (rate-limit-pool risk if alive at 09:30 — L54/L62/L68; there is NO auto-guard since OP-32 was nuked):
- PID **19452** — started 5/31 21:23 (~23h old), `--model sonnet-4-6 --resume` (old resumed session).
- PID **30744** — started today 16:11 (~4h old), `--model default`, computer-use/spawn-task tools (looks like a spawned/cowork session).
- (PID 21528 = this Opus session, leave it.)
- Kill command if you want them gone: `Stop-Process -Id 19452,30744 -Force`

**(b) The EOD / post-trade reflection pipeline is GONE** (nuked in the 5/23 reset, never re-added): no `EodSummary`, `AnalystEodReview`, `DailyReview`, `ManagerDailyVerify`, `GymSession`, `WeeklyReview`, and — most importantly — **`GhostOrderReconciler`** ($0, detects silent MCP order-placement failures). Run-scripts all still exist; re-registering is fast. Held off because you said "no unnecessary sch tasks" and most of these cost LLM $.

---

## 5. Recommendation
- **GhostOrderReconciler** ($0, pure Python) is the one I'd re-add regardless — it answers "are we actually getting filled" and is a pure uptime/health win, no cost.
- Kill the two leftover sessions before tomorrow's open.
- The rest of the EOD pipeline is a cost/scope call — your preference.

---

## 6. RESOLUTION (J answered, executed 2026-06-01 ~21:35 ET)

- **Sessions:** killed both. ✅
- **EOD pipeline:** J chose **Full pipeline** → re-registered **12 tasks** via the hidden chain:
  `GhostOrderReconciler` (1-min mkt-hrs), `ScoutPremarket` (05:30), `SwarmPremarket` (08:15), `EodSummary` (16:00), `SniperShadowEOD` (16:05), `EodDeepDive` (16:30), `DailyReview` (16:30), `AnalystEodReview` (16:45), `GymSession` (17:00), `ManagerDailyVerify` (17:30), `TreasurerWeekly` (Sun 16:00), `WeeklyReview` (Sun 18:00).
- **Total now: 27 tasks. Audit GREEN (27=27, all hidden).** GhostReconciler smoke-tested via scheduler chain → `exit 0`.
- **Added cost: ~$2.75/day LLM** (within $100/mo OP-3 budget).
- **NOT re-added** (deliberate): `ChartVisionObserver` ($67/mo), `SessionGuard`/`MarketHoursCircuitBreaker` (the lockout firewall), real-time leak detector + other engine-eyes. Listed in the registry `## Reference` if you want any later.
- First live run of the restored pipeline: tomorrow's close (EOD tasks 16:00→17:30 ET) + 05:30/08:15 premarket.

---

## 7. TRADE-PATH + GYM VALIDATION (overnight — "test everything now, not tomorrow")

### Trade path — live-verified, both accounts
- Both ACTIVE, options L3, not blocked, not PDT, **FLAT**, no open orders. Safe $747.11, Bold $1,245.63 (live). MCP order-path auth works for both.
- **Both engines are internally version-consistent (Safe v15.3==v15.3, Bold v15.2==v15.2) → neither self-kill-switches → both WILL trade tomorrow.**

### Gym (`gym_session.py`, prod-env)
| Audit | Result |
|---|---|
| crypto-gym (42 validators) | GREEN |
| heartbeat-mcp-self-test (TV CDP) | GREEN |
| chart-data-verify | GREEN — *was YELLOW, fixed by backfill* |
| heartbeat-tick-audit | GREEN — *was RED, fixed by backfill* |
| pin-chain-verify | RED — Bold v15.2 vs canonical v15.3 (ruling below) |
| heartbeat-pulse-check | RED — 15-min tick gaps 10:00–10:48 = this morning's TV-down window; watchdog fixes forward |
| watcher-state-inspector | MISSING — audit didn't run today (minor) |

> The "pandas ModuleNotFoundError" in my first gym run was MY error (ran system python, not the venv-injected path the scheduled tasks use). Re-run in prod-env: clean. Not a real bug.

### Fixed tonight
1. **Bold circuit-breaker stale equity** — was armed at $1,535.83 (pre-5/29 loss); re-armed to live $1,245.63.
2. **Bold breaker never re-armed daily (root cause)** — premarket re-armed Safe's breaker but had no aggressive step. Added the aggressive-breaker reset to `premarket.md`.
3. **Safe kill-switch % mis-documented** — `premarket.md` said "50% of equity"; Rule 5 + the live file are **30%**. Fixed the text to 30%.
4. **Today's bars backfilled** (`append_today.py`: 141 SPY + 144 VIX) → fixed 2 gym audits.

### NEEDS YOUR RULING (Rule 9 — did NOT touch live trading doctrine)
1. **Should Bold get the v15.3 RIBBON CONVICTION GATE?** v15.3 (ribbon spreading ≥5c/3bars + freshness ≤15 bars + no-midday-single-trendline) went live on **Safe today** per your "engine didn't perform well, needs updated." Bold is still on v15.2 without it — and Bold is down −19%. Queued a Kitchen backtest (port-vs-not, 16-mo real-fills IS/OOS). Real fork: the gate makes Bold MORE selective, which cuts against "aggressive = all setups."
2. **Bold kill-switch %**: `aggressive/heartbeat.md` + breaker use **−60%**; CLAUDE.md Rule 5 says Bold **−50%**. Doc-vs-code conflict on a kill switch. Left behavior unchanged (−60% live). Which is right?

### Kitchen
Healthy — daemon alive, 368 cooks done, 23 queued, $0.016 today (free tier). One transient seeder JSON-parse miss at 22:20 (free-tier flakiness, self-recovers; daemon keeps cooking). Queued the v15.3→Bold question.

---

## 8. ENGINE-IMPROVEMENT FINDINGS — overnight backtest (updating live, last 23:17 ET)

Two independent streams, cross-validated:

**A. Missed-week infinite sweep** (overfit the 4 chop days, by design): 4,450 combos, 0 errors.
- Baseline (≈production): **0/4 green, −10/c.** Best found: **4/4 green, +210/c.**
- **EVERY** 4/4-green config uses a **wide stop (−45 to −55%)**; production −8% never survives a single day.
- **Trailing profit-lock CAPS the winners** on chop days: fixed-PL configs hit +210/c, the same config with the trailing chandelier only +31/c. The chandelier is exiting runners into the chop-and-recover.

**B. Full-history OP-16 grinder** (anchor-safe, 2025-01→2026-05-07, real fills): 140/432 combos, 6 keepers.
- Keepers favor **`super_stop` −15 to −20%** (vs production −8%), `level_stop` −10/−12, `trendline_stop` −6/−8. **Same direction: wider stop.**

### Convergent, deployable direction (cross-validated, NOT overfit)
**The premium stop is too tight.** Both streams agree. Defensible value = widen toward **−15 to −20%** (the anchor-safe range) — **NOT** the −55% missed-week overfit (that would blow up on trend-against days).

### The deeper truth — the real "engine didn't perform well"
Full-history keepers (even those passing the anchor floors) show **~16% win rate and NEGATIVE aggregate P&L** across 2025–26 (only 2026-Q1 positive). Partly by OP-16 design (capture J's big edge days, accept some bleed) — but the bleed is too severe (the missed week lost ALL 4 days). Wider stops reduce chop losses but won't fix the bleed alone. The bleed needs **SELECTIVITY** — fewer, higher-quality entries — which is precisely what **v15.3's ribbon conviction gate** does, and which **Bold still lacks**.

### Recommendation for J (Rule 9 — flagged, not applied)
1. **Widen the premium stop −8% → −15/−20%** (both streams agree).
2. **Pair with selectivity** (v15.3 ribbon gate on BOTH accounts) to cut the low-WR bleed.
3. **Do NOT deploy −55%** (overfit to 4 days).
All gated on anchor no-regression — the full-history grinder is that gate.

### Next driver ticks
When the full-history grinder finishes (~02:00 ET, 432 combos), launch a focused follow-up sweep on the converged region (`super_stop` −12 to −22 × selectivity knobs) to pin the optimal moderate stop. Live leaderboard: `analysis/missed-infinite-sweep.md`.

### Tick log
- **00:06 ET** — Streams healthy (missed-sweep 12,075 combos, converged on the +209/c overfit; grinder 420/432). Kitchen "stall" was a FALSE ALARM — daemon (PID 11400) is correctly running the overnight_grinder as its claimed `grinder_sweep` task, not hung; the 3 queued selectivity cooks run the moment it finishes.
  - **NEW KEY FINDING: exit-param tuning is TAPPED OUT.** The grinder's best aggregate `wide_pnl` ≈ **−$62** even after 420 combos across the full exit space (stops/tp1/runner/PL). Break-even is the ceiling for exit tuning. → Widening stops fixes the *chop* but cannot make the engine aggregate-positive. **SELECTIVITY (entry quality) is the only remaining lever** — re-confirms the v15.3 ribbon-gate direction. The focused follow-up should pivot from exit-sweeps to selectivity backtests.
- **00:55 ET — THE ANSWER IS ALREADY ON THE LEADERBOARD.** Grinder finished clean (432/432, best aggregate −$62 → exits confirmed tapped out). Mined the 3 selectivity cooks + `_LEADERBOARD.md`: the engine's bleed comes from 3 entry buckets, and **each already has a validated gate that is OOS/real-fills-PASS but stuck un-ratified:**
  - **#21 MIDDAY_TRENDLINE_GATE — `RATIFICATION_READY`.** Block single-trigger trendline entries 11:30–14:00. Real-fills OOS: +3.8 → **+7.2/trade (+89%)**, +1,562/c (highest of all configs tested), anchor PASS (5/04 kept, 4/29 loser suppressed), concentration PASS. Blocked only on J Rule 9.
  - **#22 RIBBON_MOMENTUM_GATE (= v15.3 ribbon conviction) — `RATIFICATION_READY`, 9/10.** WF 3.74, OOS WR 0.47 **+26.9/c**, 11/12 OOS months positive, anchor PASS. It IS wired into the backtest engine (offline-validated). Live on Safe as v15.3 today; **Bold still lacks it.**
  - **#17 V14E_BEAR_TIME_OF_DAY_GATE** — AM-chop quality elevation. OOS WF 1.056 + real-fills (PM +$31.8 vs AM −$5.0). Live in watcher, not heartbeat.
  - **#3 V14E_BEAR_ONLY_GATE** — drop the bull branch (bull WR 48% −$3,642 vs bear 58% +$1,492).

  ### ⇒ BOTTOM LINE FOR J
  Exit tuning is maxed (~break-even ceiling — proven across 432 + 20,625 combos). **The real engine improvement is to RATIFY THE VALIDATED SELECTIVITY STACK.** #21 and #22 are `RATIFICATION_READY` *right now*. v15.3 (ribbon gate on Safe today) was step 1; **#21 MIDDAY_TRENDLINE_GATE is the obvious next ratify** (+89%/trade, highest-tested), and **port #22 to Bold**. The only untested piece is whether the gates COMPOUND or OVER-FILTER when stacked — queued to the Kitchen this tick. No more exit-param sweeps needed.
- **01:44 ET** — Compound-stack cook (25e0c3bc) completed but is **reasoning-only** (free-tier Nemotron can't write+run a novel 4-gate backtest; all anchor deltas "requires Stage-1 backtest", conf 4/10). Honest limitation: Kitchen LLM cooks *analyze* existing results well but can't *execute* new multi-gate backtests. It does confirm: (a) the 4 gates are orthogonal (time-of-day / ribbon / chop / direction); (b) **ratify ORDER = #21 first** (+89%, standalone-validated) → **#22** → #17/#3 (already watcher-deployed = low-effort heartbeat flip); (c) real risk = conjunctive **over-filter** (could cut trade count too far). The empirical stack number still needs a proper Stage-1 backtest — already a queued leaderboard gate (#21 "grinder A/B sweep queued", #22 "V14E compound test queued"), NOT a rush-it-overnight job (multi-gate backtest wiring is L70–72-class bug-risk). **The actionable answer is unchanged + complete: ratify #21, port #22 to Bold** (both individually RATIFICATION_READY); the stack is a follow-up optimization. Findings have converged — driver cadence stretched to conserve; autonomous cookers (sweep + grinder rotation + Kitchen) keep grinding $0 through RTH.
