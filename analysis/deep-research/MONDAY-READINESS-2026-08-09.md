# MONDAY READINESS — verified 2026-08-06 evening (for the 2026-08-10 open)

> Lane 7 of the Thursday-evening parallel session. Clock verified at start:
> `2026-08-06 18:46:58 Thursday EDT / market_hours=False` (`et_clock.py`).
> Everything below is a **fresh check run this session**, not recalled state.

## VERDICT: READY, with two named exceptions

1. **bold-2 cannot trade until Wed 08-12** (its own enforced PDT gate — see §3).
2. **Ghost workflow `wf_6db746c8-a74` still alive** at 19:13 ET (4 agents, idle 391.9m) —
   owned by the Fix+Ship lane (S4); deliberately not touched by this lane to avoid a
   double-cleanup collision. If S4 didn't get to it, it is still there.

---

## 1. TV watchdog — argv fix PROVEN, and a second masked defect found + fixed + shipped

**The owed proof (argv fix shipped 08-06 morning UNPROVEN):**
- Staged the real failure live: TV up (procs born 16:27 ET) + CDP dead 8,462s.
- Ran the REAL path (`run-tv-watchdog.ps1` → `Invoke-TvLaunchSafe -Kill`). The launch child
  **executed for real** (log: `Launching TradingView with --remote-debugging-port=9222`,
  tab navigated, layout restored — pre-fix, not a single line of the launch script ran)
  and CDP healed on :9222.

**NEW defect exposed by the proof (pre-fix it was masked):**
`Invoke-TvLaunchSafe`'s `& powershell.exe $psArgs 2>&1 | Out-File` pipeline **blocked until
TradingView itself exited** — `launch_tv_debug.ps1` starts TV via `Process.Start` /
`UseShellExecute=$false` with no redirection, so TV inherits the child's stdout handle and
the pipeline can never complete. Live repro: the healing tick hung 12+ min past a successful
heal (watchdog PID 29204 confirmed alive/blocked); production `Gamma_TvWatchdog`
(`ExecutionTimeLimit=PT4M`) would be killed before `Test-CdpReady`/verdict-logging ran —
the 2026-07-31 `*_FAILED` escalation was unreachable in exactly the scenario it was built for.

**Fix shipped (commit `273a113b`):** `Start-Process` + sidecar-file redirection +
`Wait-Process` on the child only; `CdpTimeoutSec` 12→90 (measured cold boot-to-CDP >29s —
a 12s poll flags every real heal as FAILED).

**End-to-end proof after the fix** (kill TV → real watchdog script):
```
watchdog EXIT=0 elapsed=67s
"tv_action": "relaunch_fresh_healed"        (tv-watchdog-status.json, 2026-08-06T23:09:30Z)
2026-08-06 19:08:27 ET RELAUNCH_FRESH no TV process and CDP dead - launching
tv_health_check: cdp_connected=true, chart_symbol=BATS:SPY, resolution=5, api_available=true
```
**Guards:** `backtest/tests/test_tv_launch_argv_2026_08_05.py` — the file the argv fix cited
but never wrote (L249 class), 5 tests incl. a functional hang-repro; + existing
`test_tv_launch_safe_2026_07_06.py`; **12/12 green**. **RED-proofed** by 3 source mutations
(argv splat back → 2 failed; blocking pipe back → 2 failed; timeout 12 → 1 failed), restored
byte-identical (sha256 `7ca02ee1...` verified), green re-run.
**Revert:** git-revert `273a113b` (single commit, one function + guard + STATUS entry).

*Open observation (not chased tonight):* the 16:27 ET TV instance came up **without** CDP
and sat that way ~2.4h until this drill killed it — consistent with the pre-fix hang killing
a relaunch tick mid-flight. Post-fix the watchdog now completes and self-verifies, which is
the systemic cover for this shape; Friday's 08:05-16:00 watchdog cadence is the live test.

## 2. Chart auto-draw — registered, fired, chart verified

- `Gamma_ChartAutoDraw`: **State=Ready**, weekly Mon-Fri trigger 08:35 ET + `PT30M`
  repetition for `PT7H30M` (08:35-16:05 ET), LastResult=0. NextRun 08-07 08:35 ET.
- Fired via `Start-ScheduledTask` 19:11 ET: `chart-autodraw.json` → `status: OK`, spot
  768.64, **removed 11 stale** `[G]` drawings, **drew 11 fresh** levels — every drawn
  raw_label dated `2026-08-06` or a current `MEMORY_*` (PRIOR DAY HIGH 776.85 … INTRADAY
  RTH LOW 767.46, SHELF 754.71). shapes 50→50 (removes only its own tag — J's manual
  drawings untouched).
- **Independent cross-check** via `draw_list`: all 11 new entity_ids present on the chart
  (`KcMUr7`…`QjtH9T`), all 11 removed ids absent. No June-vintage `[G]` lines remain.

## 3. PDT ledger entering next week (real fills, pulled per-arm tonight)

**Day-trade counts this week** (a day-trade = same option symbol bought AND sold same ET day;
`pdt_tracker` definition, computed from each arm's own FILL activities):

| Arm | Mon 08-03 | Tue 08-04 | Wed 08-05 | Thu 08-06 | wk total |
|---|---|---|---|---|---|
| safe-2 | 1 | 3 | 2 | 2 | 8 |
| bold-2 | 0 | 3 | 0 | 0 | 3 |
| safe-3 | 1 | 5 | 0 | 0 | 6 |
| risky-1 | 1 | 4 | 2 | 1 | 8 |
| risky-3 | 1 | 5 | 2 | 1 | 9 |

**Two window definitions matter** (they disagree by one day):
- **ENFORCED (what the rig's code does):** `pdt_tracker` window = today + 5 preceding
  business days (6bd wide, documented-conservative). A date D rolls off at **D+6bd**:
  08-03 trades leave 08-11, 08-04 → 08-12, 08-05 → 08-13, 08-06 → 08-14.
- **Strict FINRA rolling-5bd** (X-4bd..X): one day earlier per date (08-03 leaves 08-10 …).

**Projection, ASSUMING FRIDAY 08-07 ADDS ZERO DAY-TRADES** (labeled assumption — bold-2 is
blocked Friday and *cannot* add; every other arm can, which would raise its numbers):

| Arm | Mon 08-10 | Tue 08-11 | Wed 08-12 | Thu 08-13 | binding? |
|---|---|---|---|---|---|
| safe-2 | 8 in-window (FINRA hr 0) | 7 (hr 0) | 4 (hr 1) | 2 (hr 3) | **NO** — core gates safe-2 on `cash_settlement` (settled cash), not day-trade counts. Informational. |
| **bold-2** | **3 — BLOCKED** | **3 — BLOCKED** | **0 — UNBLOCKS 08-12** | 0 (hr 3) | **YES — core enforces** `margin_pdt`: `RISK_DENY_PDT` at count>=3 & equity<$25K. Cross-checked vs production code: `fetch_day_trades_detail` → `rolloff_date: 2026-08-12`. (Strict-FINRA reading would free it Tue 08-11; the shipped tracker is 1 day more conservative.) |
| safe-3 | 6 in-window (hr 0) | 5 (hr 0) | 0 (hr 3) | 0 (hr 3) | **NO — LOG-ONLY** |
| risky-1 | 8 (hr 0) | 7 (hr 0) | 3 (hr 2) | 1 (hr 3) | **NO — LOG-ONLY** |
| risky-3 | 9 (hr 0) | 8 (hr 0) | 3 (hr 2) | 1 (hr 3) | **NO — LOG-ONLY** |

*(cell = enforced-window count entering that day; "hr" = strict-FINRA headroom if legacy
margin-PDT applied that day)*

**What the LOG-ONLY fleet gate will report vs what binds:** every fleet tick logs
`day_trades_true` (Monday: 6 / 8 / 9) + `pdt_enforced=false`, while the risk gate binds on
the legacy `daytrade_count` — null on Alpaca paper → 0 → never blocks. Core safe-2 binds on
settled cash (no visible constraint at current sizes); **core bold-2 is the only arm with an
enforced day-trade cap — dark Mon+Tue, back Wed 08-12.**

## 4. Account-type facts for J — assembled, keys untouched

Full page: **`analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md`**. Headlines:
- All 5 live accounts read **multiplier=4 / shorting_enabled=true** (margin-shaped);
  `pattern_day_trader`/`daytrade_count` **null** — and behaviorally the paper broker enforced
  nothing at 8-9 day-trades/arm this week.
- **Both** `_pdt_gate_mode_doc` provenance fields cite dead account numbers
  (PA3DHPT7KIQE / PA33W2KUAT40); safe-2's "CASH account, multiplier=1" premise is stale.
- Alpaca docs (fetched tonight): FINRA's Rule 4210 overhaul **eliminates the PDT framework**
  ($25K threshold + trade counting) for a risk-based intraday-margin system; 12-month interim
  where firms may apply either. bold-2's block is a self-imposed legacy rule.
- Three coherent options laid out (match-broker / enforce-everywhere / status-quo); J owns it.

## 5. Instrument sweep — trading-critical scheduled tasks

**24/24 trading-critical tasks GREEN** — `Ready`, `LastTaskResult=0x0`, today's fires at the
right times, next fires correct for Fri 08-07: LaunchTV (08:00 ET), TvWatchdog (5-min, last
16:00 ET), LevelRefresh (5-min, live at 19:08 ET), **HeartbeatCore (last 15:55 ET, next
09:30 ET Fri)**, SightBeacon, EodFlatten + _Aggressive (15:55 ET) + EodFlattenCore
(15:52 ET), ChartAutoDraw, ViolinMetric (17:35), WinnerAutopsy, RegimeAttribution (17:45),
Premarket (08:30), Preopen/PremarketReadiness, RegimeStamp (08:22+08:40), EmaSnapshot,
FleetExecutor (next 09:31 ET), OpenBellStatus (09:36), LiveWatch, ThetaClock, Morning/EodBrief,
ShadowSignalAudit.

- Full fleet: `audit_scheduled_tasks.py` counts 97 active + 19 disabled registered (my
  root-path scan saw 115 — 1-task path-scoping discrepancy, not chased); **1 non-zero
  result** = `Gamma_Grind_all` (0x41306, Disabled, dead since 06-25 — documented in the
  registry's Disabled section).
- 19 disabled — all carry documented/annotated disables (grind/funnel family, retired LLM
  heartbeats, futures trio, Drive/ManagerOverseer/DailyReview/ConductorRTH/EveningNarrative).
- `audit_scheduled_tasks.py` verdict **RED** — decomposed honestly: 8 flags are
  CANDIDATE_FOR_REMOVAL housekeeping on the long-dead grind/funnel tasks; 2 SILENT_TASK
  flags (`Gamma_ConductorWeekend` 67h, `Gamma_TwinChaos` 112h) are **auditor cadence-model
  false positives** — both are weekend-/weekly-scoped tasks read against a generic 26h
  expectation on a Thursday. No trading-critical task is silent.
- Registry count drift persists (registry text says 106 active/9 disabled; live = 97
  enabled/19 disabled + this morning's ChartAutoDraw row) — chronic, known since 07-25,
  not reconciled tonight (registry hygiene, not a trading risk).
- `bg_status`: 2 COMPLETE runs, 1 RUNNING (tonight's active lane), and the S4 ghost
  `wf_6db746c8-a74` (14/18, 4 agents, idle 391.9m) — **still present**, S4's to clean.

## 6. github_audit

```
[SCAN] 10154 tracked files in 54.0s
VERDICT: GREEN -- safe to push
```
Not pushed (orchestrator pushes after github_audit, per lane orders).

---

## Monday-morning expectations (inherit these)

- 08:00 ET LaunchTV → 08:05+ watchdog every 5 min — **first live exercise of the fixed
  heal path**; a relaunch tick now finishes in ~67s and writes `*_healed`/`*_FAILED` truthfully.
- 08:35 ET ChartAutoDraw draws Monday's levels; stale [G] lines auto-cleaned every 30 min.
- 09:30 ET HeartbeatCore: safe-2 + fleet arms free to trade; **bold-2 will log
  `RISK_DENY_PDT` on any entry until Wed 08-12 — that is correct behavior, not a defect**
  (unless J takes Option A on the decision page before the open).
- Friday 08-07 trades will ADD to every non-bold-2 arm's Monday windows — re-read the §3
  table after Friday's close if precision matters (the LOG-ONLY gate logs the true counts
  per tick regardless).
