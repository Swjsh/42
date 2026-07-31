# BLIND-ENGINE REPAIR — 2026-07-30

**VERDICT: YES for unanchored entries — the engine can no longer take a bear/bull entry with an empty level set. NOT "blindness is impossible."**

Proof, run by me at 20:14 ET tonight against the real ledger with the shipped predicate (not a mock, not a claim):

```
DAY          rows  has_key  blind  ENTER_intents  BLOCKED_by_rail
2026-07-27     778        6      6              0               0
2026-07-28     772      772      0              7               0
2026-07-29     751      751      0             10               0
2026-07-30     796      796    776             11              11
```

All **11 of today's ENTER_BEAR verdicts become SKIP_NO_LEVELS**; **0 of the 17 ENTERs on the two sighted days change**. Polarity probe on the live module:

```
is_blind {}        -> True      # missing data reads as blind (fail-CLOSED)
is_blind levels=[] -> True
is_blind levels=[x]-> False
flag absent        -> True      # rail is ON with a zero-line params diff
flag false         -> False     # explicit revoke works
anchored none      -> False
anchored 740.0     -> True
```

**What it does NOT close:** an entry that computes its *own* anchor from today's bars (fhh_level_rejection) still fires with an empty key-level file — deliberate, that anchor is real and belongs to the profitable cohort. And `j_intent_executor.py` (J's own called trades) has no blindness check at all — a recursive grep of `setup/scripts/` and `automation/state/fleet/` finds `SKIP_NO_LEVELS` / `_is_blind` / `_SIGHT_FAILURE_VERDICTS` in exactly two files: `heartbeat_core.py` and `build_shared_signal.py`.

Session clock: `python setup/scripts/et_clock.py` → `2026-07-30 20:09:49 Thursday EDT / market_hours=False`. HEAD `c6f27af3` on `main`, nothing pushed.

---

## 1. What broke, and what is actually fixed

Six code commits landed (`1ee3b1d4`, `7cf306d2`, `9b25aa79`, `90a0e826`, `748a0753`, `54b27c00`) plus one docs commit. Every PROOF cell below is output I re-ran myself tonight, not a quoted workstream claim. Anything I could not re-derive is marked **UNVERIFIED**.

| # | What was broken | Fixed by | PROOF (my run, 20:09–20:20 ET) |
|---|---|---|---|
| 1 | **49 tasks documented Active were `State=Disabled`** — incl. `Gamma_LevelRefresh` and `Gamma_PremarketReadiness`. Their triggers were never malformed. 41 re-enabled. | `7cf306d2` (WS-triggers) | `Get-ScheduledTask Gamma_*` → `total=103 ready=86 disabled=17` (was 45/58). `Gamma_LevelRefresh State=Ready Last=20:08:36 ET Next=20:13:35 ET RC=0` — firing on its 5-min cadence, unattended. `Gamma_PremarketReadiness State=Ready Next=2026-07-31 09:00 ET`. |
| 2 | **The daily task audit skipped disabled tasks before every check** — flipping a task off removed it from checking rather than failing it. Silence read as health. | `7cf306d2` | `python setup/scripts/audit_scheduled_tasks.py` → `DISABLED_BUT_DOCUMENTED_ACTIVE 0`, `NON_REPEATING_TRIGGER 0`, `REPETITION_INTERVAL_MISMATCH 0`. Carrier verified alive: `run-crypto-daily.ps1:83` invokes it; `Gamma_CryptoDaily State=Ready Next=2026-07-31 06:00 ET`. |
| 3 | **The engine had no concept of being blind** — empty level set → silent fallthrough to the trendline-only cohort (−$1,830 / WR .19 / n=124, per PNL-ATTRIBUTION-2026-07-28). | `9b25aa79` + `90a0e826` + `748a0753` (WS-blind-block) | The ledger replay and polarity probe at the top of this file. Rail present in `git show HEAD:setup/scripts/heartbeat_core.py` (`SKIP_NO_LEVELS`, `_is_blind`, `_level_anchored`, `_blind_block_enabled`). |
| 4 | **The fleet's loose lane could re-enter off the refused row** — `risky-3` runs `hard_skip_verdicts=[]` and `_score_peak_check` rates on score+trigger alone; today's blind rows carry `bear_score 8` + `ribbon_flip`. | `748a0753` | `_SIGHT_FAILURE_VERDICTS = frozenset({"SKIP_NO_LEVELS"})` at `build_shared_signal.py:631`, consumed at `:645` inside `_score_peak_check`. Guard `test_blind_no_levels_2026_07_30.py` green. |
| 5 | **Every level check in `engine_health` was suppressed by "market closed"** — at 18:53 ET it read GREEN on the very file that had blinded the engine all session. | `1ee3b1d4` + `90a0e826` (WS-detection) | Live `engine-health.json` right now: `RED levels_blind crit=True "ENGINE TRADED BLIND on 2026-07-30 -- 0 of 770 RTH decision rows carried ANY active key level (bold 0/385; safe 0/385)"` — while the producer already healed (`GREEN levels_file_stale "dated today, 20 level(s) visible, rewritten 1.2m ago"`). Two genuinely independent signals. |
| 6 | **Nothing watched the other producers** — 10 live-path state files were frozen at the 07-29 session, all consumers carried on. | `1ee3b1d4` (WS-silent-failure-audit) | `python setup/scripts/state_freshness_audit.py --json` → `verdict RED, n_entries 17`, 3 non-green (down from 10). Wired non-critical into the beacon: `RED state_freshness crit=false "3/17 live-path state files STALE"`. |
| 7 | **Every RISK_DENY looked like an ordinary oversize deny** — no way to tell "size down" from "no legal qty exists". | `9b25aa79` (WS-sizing) | `python setup/scripts/sizing_deadlock_diag.py` reproduced live against Alpaca — full table in §5. Diagnosis only: nothing armed, no risk knob moved. |
| 8 | **Nothing force-healed a stalled level refresher** (a 6th session's commit, not in the five-workstream brief). | `54b27c00` | `Invoke-LevelRefreshSafe` at `_shared.ps1:838`; relaunch is `powershell.exe -NoProfile -WindowStyle Hidden -NonInteractive -File`. Rides `Gamma_TvWatchdog` (`State=Ready`, ran today `16:00 ET`). No new task registered. |

**Guard evidence, my runs:**

```
136 passed in 2.04s   # 6 new suites: blind_no_levels, levels_blind_detection,
                      # state_freshness_audit, sizing_deadlock_diag,
                      # sizing_deadlock_wiring, level_refresh_watchdog
[safety-gate] PASS -- curated safety gate (6 suites) green ({'passed': 59}).
```

**Zero net regressions — proven, not asserted.** I built a worktree at pre-repair `d625cd40` and ran the failing tests there:

```
pre-repair d625cd40 : 4 failed, 75 passed
HEAD c6f27af3       : 4 failed, 75 passed   # identical names
  test_guard_cmd_popup_fix_ws6::test_run_hidden_vbs_still_recognized
  test_money_path_2026_07_01::TestEntryCeiling::test_extra_route_late_fire_is_skip_late_entry
  test_money_path_2026_07_01::TestVwapContinuationArmed::test_safe_params_arm_vwap_continuation_only
  test_money_path_2026_07_01::TestVwapContinuationArmed::test_fired_armed_vwap_routes_to_execute
```

All four are pre-existing. Worktree removed.

---

## 2. One correction to the incident brief

The brief says the 11:31 ENTER_BEARs were at **"the day's LOW."** From the engine's own ledger:

| Window | Low | High | Close (15:55) |
|---|---|---|---|
| RTH 09:30–15:55 | **729.57 @ 09:31** | 742.27 @ 15:21 | 741.60 |
| From 11:31 onward | **734.885 @ 11:31** | 742.27 @ 15:21 | 741.60 |

734.885 was the low of the **rest of the session**, not the day. The direction of the error is unchanged: the blind short would have been **+6.72 SPY points wrong** by the close. Cited so nobody repeats a number that doesn't survive a check.

---

## 3. What the verifiers refuted or downgraded

None of the five workstreams came back clean. All five were graded MINOR_GAPS or worse.

| Workstream | Grade | What was refuted / downgraded |
|---|---|---|
| triggers | MINOR_GAPS | **False wiring claim, confirmed by me:** `SCHEDULED-TASKS.md:39` and the report say the live-registry drift guard "runs under `Gamma_GuardsNightly`". It does not — `guard_runner.py:47` and `guard_runner_slow.py:124` hardcode `test_graduated_guards.py` as the only pytest target, and `test_scheduled_task_triggers_live.py` appears in no runner. This is the exact L249 anti-pattern the repair was written to close, reproduced in its own docs. Compensated: the daily `audit_scheduled_tasks.py` run under `Gamma_CryptoDaily` IS live and does the drift detection. |
| triggers | — | **Vacuity gap:** rename `## Active` in the registry and the live drift guard passes GREEN on zero parsed rows. |
| triggers | — | **Persistent-RED masking:** the audit sits at 34 flags / health RED, of which 8 `CANDIDATE_FOR_REMOVAL` never self-clear. The next real drift flag lands as one line in a permanently-red report. Verified live tonight: `flags=34 → 8 CANDIDATE_FOR_REMOVAL + 26 SILENT_TASK`. |
| blind-block | MINOR_GAPS | **One guard is vacuous:** `test_score_ladder_rescue_cannot_bypass_the_block` asserts `action in ('SKIP_NO_LEVELS','HOLD')` on a fixture where the ladder never fires — it survives deletion of the entire 52-line blindness branch. The bypass it claims to close is structurally impossible anyway, so the safety claim stands; the test is decoration. |
| blind-block | — | **Docstring cites an unreachable path:** `_level_anchored`'s docstring claims it keeps anchored extra-setup verdicts alive. It doesn't — the G4 lane is blocked *wholesale* when blind. Conservative, but broader suppression than the write-up describes. |
| blind-block | — | `isinstance(False, int) is True` — a JSON `false` in `rejection_level` would read as a valid anchor. Fail-OPEN edge in an entry-blocking predicate. Not reachable today (`engine_cli` emits float or None). |
| detection | MINOR_GAPS | **A reported finding was refuted outright.** The claim that "2026-07-23 and 2026-07-27 were ALSO fully blind days… recurring silently for over a week" is a **schema artifact**, not evidence. `levels_active` did not exist in the ledger before 2026-07-27. My own replay confirms it: `has_key` = 6/778 on 07-27, 772/772 on 07-28. `bool(r.get("levels_active"))` conflates key-absent with empty-list, so every pre-07-28 day reads BLIND. **Do not back-audit those days on this basis.** The documented `--date` backfill path returns a confident false "ENGINE TRADED BLIND" for any date before 07-28. |
| detection | — | **1 of 3 headline surfaces did not deliver on the incident day:** `Gamma_EodBrief` did not fire (Last = 07-29 14:20 local, confirmed by me). The lead-with-the-alarm ordering is correct in code; the surface was silent. |
| detection | — | Alert de-duplication doesn't hold: 4 pings for the same condition in `discord-outbox.jsonl` today, not the once-per-transition the docstring describes. |
| silent-failure-audit | **MAJOR_GAPS** | **The guard suite is wall-clock flaky.** `test_fresh_file_is_green` mixes a frozen fixture clock with the real local clock (`state_freshness_audit.py:300` rounds `now_et - datetime.now()` to an hour offset); it flips red/green depending on the minute you run it, on a byte-identical tree. It passed for me at 20:12 ET. A guard whose result depends on the minute is not a guard. |
| silent-failure-audit | — | **The age axis is wrong by 240 minutes on 2 of 17 files.** `_stamp_datetime` discards the timezone offset, but `confluence-zones.json` and `pnl-statement.json` write genuine UTC. A producer that dies at 09:42 ET reports GREEN with *negative* ages until ~14:20 ET — the false-negative direction. The date axis (the headline fix) is correct everywhere tested. |
| silent-failure-audit | — | **It also corrected the incident brief's own root cause**, and it was right: the trigger was never misconfigured (`MSFT_TaskTimeTrigger Rep=PT5M Dur=P3650D Enabled=True`); the task was switched off. `NextRunTime` on a disabled task is a phantom Windows keeps recomputing. **State, not NextRunTime, is the authority.** |
| sizing | MINOR_GAPS | Report prints three ceilings rounded UP (1.20 / 1.76 / 2.08) where the code correctly floors (1.19 / 1.75 / 2.07). The math used the floored values; only the prose is wrong — but it names three untradeable premiums. |
| sizing | — | `binding` telemetry has never appeared on a real ledger row (all 10 of today's deny rows carry `binding: None` — they predate the commit). The heartbeat_core half of the wiring is proven by source-grep, not by runtime. The fleet half is proven behaviorally. |
| sizing | — | Two commits (`9b25aa79`, `90a0e826`) absorbed another session's in-flight files via a broad `git add`. Nothing was lost — but the commit messages do not describe the safety rail they carry. L239/L247 shape, third occurrence. |
| self-heal (`54b27c00`) | not reviewed | Its stated root cause ("the task's own Task Scheduler config went silently dark") **conflicts with the evidenced diagnosis** (task was `State=Disabled`, 58/103 in one 22:45 ET cluster). Two sessions diagnosed the same event differently. The self-heal is still useful — it relaunches out-of-band and would have healed a disabled task too — but its premise is **UNVERIFIED**. It also RED-proofed via `git stash`, which C34/L238 bans in this repo. |

---

## 4. THE SIBLING RISK — what else can still go dark

From the silent-failure audit's enumeration of 19 live-path artifacts. Ranked by damage potential; only R1 has a directly measured cost.

| Rank | File | Failure if the producer dies | Measured cost |
|---|---|---|---|
| **R1** | `key-levels.json` | THE incident. Levels expire on date rollover, `_read_levels` returns `([],[])`, engine falls to its worst cohort | **$119.23/trade swing** — LEVEL-tied n=66 +$6,894.85 (+$104.47/tr) vs TL-only n=124 −$1,830.10 (−$14.76/tr, WR .19) |
| **R2** | `circuit-breaker.json` ×2 | Holds the **start-of-day equity anchor for Rule 5**. A stale anchor mis-measures the daily-loss kill budget for a whole session | unmeasured, structurally worst |
| **R3** | `today-bias.json` + `prior-rth-close.json` | Both feed the SAME `gap_and_go` prior-close reference — lose both and there is no correct source | unmeasured |
| **R4** | `pnl-statement.json` | The C1 real-fills authority behind every ratification. Corrupts what gets **shipped**, not what gets traded | unmeasured |
| **R5** | `trade-today.json`, `premarket-readiness.json` | J's visibility layer. Exactly the L244 shape — a real trading day reads IDLE | unmeasured |
| **R6** | `key-levels-memory.json` | Multi-day memory levels vanish from the live set — amplifier for R1 | unmeasured |
| **R7** | `ema-snapshot.json`, `news.json` | Stale premarket seeds patched into `today-bias.json` | unmeasured |
| **R8** | `trendlines-live.json`, `confluence-zones.json` | Shadow today — but `confluence_producer` reads three shadow files and emits a confident-looking zone set even when all three inputs are a day old | unmeasured |
| **—** | `current-position.json` / `-bold.json` | **No writer at all** (last written 2026-06-03 / 06-18). `engine_health.check_position` reports GREEN "flat" off both, every fire, forever. A check that looks like coverage and is not. The engine itself correctly uses broker truth (`fb.is_flat_spy_options`), so blast radius is monitoring-only | — |

### Stale RIGHT NOW (20:10 ET)

```
VERDICT: RED  n=17
RED      high     automation/state/trade-today.json     stamp=2026-07-29
RED      high     automation/state/pnl-statement.json   stamp=2026-07-29
YELLOW   medium   automation/state/ema-snapshot.json    stamp=2026-07-29
```

Their tasks are re-enabled and scheduled (`Gamma_TradeToday Next=07-31 09:30 ET`, `Gamma_BrokerFills Next=07-31 09:00 ET`, `Gamma_EmaSnapshot Next=07-31 08:20 ET`) — they self-heal at tomorrow's session. **Until then, any P&L or "did it trade today" surface reads 2026-07-29's book.** That includes tonight's EOD brief.

The engine placed **0 orders** today. Full outcome tally from the 796 rows, my run:

```
HOLD                                 739
SKIP_STALE_TRIGGER                    37
RISK_DENY_RISK_CAP                     9
SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY    9
RISK_DENY_PDT                          1
SKIP_STALE_SIGHT                       1
```

Ten of the eleven ENTER verdicts died at the risk gate; the eleventh (11:35:03) died on a stale sight beacon. No `PLACED`, no `WOULD_PLACE`. So today's real result is **flat** — not the "down $12" the stale statement produces.

Also open, all disclosed by the workstreams:

- `Gamma_LaunchTV` skipped 2026-07-30 entirely despite `State=Ready`, `WakeToRun=True`, correct 06:00 MT DailyTrigger. Different shape from the mass-disable. **Not root-caused.** It is the "no TV = no trades" task. Next run 07-31 08:00 ET.
- **Manifest coverage is 17 files, not everything** — per-arm fleet state (`fleet/<arm>/circuit-breaker.json`, `probe-count.json`, `first-entry-lock.json`, `exit-state.json`, `extra-setup-cooldown.json` × 5 arms) and the `spy_5m` bar caches are uncovered. Manifest edit only, no code.
- 26 `SILENT_TASK` flags remain — the outage backlog, now visible instead of silent. Re-run the audit after Friday's close to confirm they self-clear rather than masking a second problem.

---

## 5. The sizing deadlock — J's call

**The rule collapses to one sentence: an arm cannot trade any contract priced above `equity / 1000`.** (Because `min_contracts / risk_cap_pct` = 10 for both sizing profiles: 3/0.30 and 5/0.50. Exact for Bold at all equities; exact for Safe up to $10K, then the v15 tier tightens it to E/1200, then E/1500.)

The mechanism: `heartbeat_core._execute` sets `qty = min_contracts`, `max_affordable_qty` returns 0, `0` is falsy so the clamp is skipped, `qty` stays at the floor, `check_order` rule 6 denies RISK_CAP. It never reduces below the floor — the refusal is structural, not a sizing miss.

**Per-arm thresholds, my run at 20:16 ET against live Alpaca equities:**

| ARM | ACCOUNT | EQUITY | MIN_C | CAP% | CAP$ | BINDS | **CEILING$** |
|---|---|---|---|---|---|---|---|
| safe-2 | PA3DHPT7KIQE | 1,160.42 | 3 | 0.30 | 348.13 | risk_cap | **1.16** |
| safe-3 | PA32RD49OB0Q | 1,893.04 | 3 | 0.30 | 567.91 | risk_cap | **1.89** |
| bold-2 | PA33W2KUAT40 | 1,197.52 | 5 | 0.50 | 598.76 | risk_cap | **1.19** |
| risky-1 | PA3W17FD8G19 | 1,756.87 | 5 | 0.50 | 878.43 | risk_cap | **1.75** |
| risky-3 | PA31WIU8X15Q | 2,076.69 | 5 | 0.50 | 1,038.35 | risk_cap | **2.07** |

**Historical participation loss** — 190 engine entries over 387 RTH days (2025-01-02 → 2026-07-22, `engine-fullhist-replay-2026-07-23.json`), each arm at current equity:

| ARM | CEIL$ | BLOCKED | %BLOCKED | PnL kept | PnL lost |
|---|---|---|---|---|---|
| safe-2 | 1.16 | 97 | **51.1%** | 2,758.80 | **2,305.95** |
| safe-3 | 1.89 | 23 | 12.1% | 5,884.50 | −819.75 |
| bold-2 | 1.19 | 92 | 48.4% | 4,039.55 | 1,025.20 |
| risky-1 | 1.75 | 32 | 16.8% | 6,521.45 | −1,456.70 |
| risky-3 | 2.07 | 17 | 8.9% | 5,817.75 | −753.00 |

Core Safe is locked out of **half its own entries**, and that half carried +$2,305.95 of the book's +$5,064.75.

### ⚠️ The refund changes the risk picture — read this before choosing

Today's 11 blind shorts were stopped by the risk gate (10: nine `RISK_DENY_RISK_CAP`, one `RISK_DENY_PDT`) and a stale sight beacon (1). That was **luck, not design** — neither guard knows anything about levels. A refund to $2,000 raises every arm's ceiling to exactly $2.00 — my run:

```
python setup/scripts/sizing_deadlock_diag.py --equity 2000
safe-2   2000.00  3  0.30   600.00  risk_cap  2.00
safe-3   2000.00  3  0.30   600.00  risk_cap  2.00
bold-2   2000.00  5  0.50  1000.00  risk_cap  2.00
risky-1  2000.00  5  0.50  1000.00  risk_cap  2.00
risky-3  2000.00  5  0.50  1000.00  risk_cap  2.00
```

safe-2 goes from a $1.16 ceiling to $2.00, and the historical replay puts blocked at 10.0% instead of 51.1%. **The refund removes the accident that saved today.** It is precisely what makes the SKIP_NO_LEVELS rail load-bearing instead of academic.

> **UNVERIFIED —** the sizing workstream reports today's 9 safe denies were at premiums 1.42–2.01, of which 8 would clear a $2.00 ceiling. **I could not reproduce those premiums.** The 07-30 `core-decisions.jsonl` row schema has no premium field (`ts_et, account, verdict, action, reason, spy, vix, bear_score, bear_triggers_raw, bear_rejection_level_raw, levels_active, triggers, setup, side, spread_cents, …`) and the `reason` string on all 10 deny rows is the setup name only, not the arithmetic. Treat "8 of 9 would now clear" as unverified. The *direction* — refund raises the ceiling from $1.16 to $2.00 — is verified above.

### The options — ranked by the workstream, chosen by you

Nothing was applied. All four need J because `min_contracts` is part of Rule 6's own text ("Min 3 contracts (2 TP + 1 runner)"). **None changes `per_trade_risk_cap_pct`.**

| Rank | Option | Effect | Preserves | Breaks / cost |
|---|---|---|---|---|
| **(d)** | **qty-2 floor** | blocked: safe-2 51.1→16.8%, safe-3 12.1→0%, bold-2 48.4→0%, risky-1 16.8→0%, risky-3 8.9→0% | **The runner survives** — 1 TP + 1 runner. The runner cohort is +$15,774 / 35 trades; the book ex-runner is −$10,709, so it IS the profit engine | TP1 becomes a single contract, so `tp1_qty_fraction` (0.8/0.667) no longer expresses — needs an explicit qty-2 policy. Test first: `exit_manager` replay at qty 2. Per-trade P&L scales to ~2/3 of the qty-3 replay dollars — **recovered participation is not recovered P&L** |
| (b) | **Reset to $2,000** | Every arm's ceiling → exactly $2.00; blocked → 10.0% uniformly | Touches no rule at all | **It recurs.** A 25% drawdown from $2K re-blinds the arm below $1,500 for a $1.50 ATM quote. Buys runway, not a fix. Best paired with (d) |
| (a) | **qty-1 floor** | blocked → 0.0% on all five arms | Maximum participation | **Kills the runner outright** — no partial possible, and with it the +$15,774 cohort. Strictly worse than (d) for a marginal gain on safe-2 only |
| (c) | **Premium ceiling per tier** (engine only selects contracts it can afford) | Removes the silent refusal | — | Changes **strike selection**, i.e. a different strike tier. C29/L149: exit and entry knobs do not transfer across tiers. Converts an infrastructure bug into an edge change requiring full re-validation. Highest research cost |

**Evidence caveat, flagged before you can be tempted by (c):** premium bands look like a clean sweet-spot argument — `<$0.90` = −$654.70/44, `$0.90–1.89` = +$6,765.85/121, `>$1.89` = −$1,046.55/25. But the **top 3 trades are 50% of the [0.90, 1.16) band and 56% of the [1.16, 1.89) band.** Ex-top-3, the band safe-2 is refused is +$1,461 over 73 trades (~+$20/tr). Premium is a weak, heavily concentrated predictor. Do not justify (c) on this in-sample slice without a pre-registered OOS test.

**Fact-check correction:** the "7 blocked setups / +$291" framing is wrong. `today-blocked-trades-replay-2026-07-29.json` holds **5** setups, of which **2** were RISK_CAP denies (A @2.57, B @2.60). The risk-cap-attributable share is **+$162**; the other 3 died to VETOED_BY_MODELS and SKIP_LATE_ENTRY.

---

## 6. WHAT CAN STILL GO WRONG

Honest list. Where a repair narrows rather than closes, it says so.

**Narrowed, not closed:**

1. **The mass-disable will recur, and nothing prevents it.** 58/103 tasks flipped `Disabled` in a single ~2026-07-29 22:45 ET cluster. No commit explains it, no `Disable-ScheduledTask` in the repo targets that set, and I confirmed the forensic trail is unavailable: `wevtutil gl Microsoft-Windows-TaskScheduler/Operational` → `enabled: false`. **We fixed the detection, not the cause.** Enabling that log is a system-settings change — J's call, not mine.
2. **The blind rail keys on `levels_active` being *empty*, not *wrong*.** A level file dated today with garbage prices passes both `_is_blind` and `levels_file_stale`. The failure mode "no levels" is closed; "bad levels" is not.
3. **The rail covers two files only.** `heartbeat_core.py` and `build_shared_signal.py`. `j_intent_executor.py` — J's own called trades — has no blindness check. Arguably correct (J is the eye), but it is a real hole in "the engine cannot trade blind."
4. **`state_freshness`'s age axis is blind by 240 min on UTC-stamped files** (`confluence-zones.json`, `pnl-statement.json`) — the false-negative direction. Same-day intraday producer death on those two goes undetected for most of a session. The date axis catches it the next morning.
5. **The self-heal only covers 09:42–15:55 ET** and depends on `Gamma_TvWatchdog` staying enabled. A premarket-window blindness (the 08:30 draw failing) is not self-healed; it is caught by `Gamma_PremarketReadiness` at 09:00 ET — which is the gate that itself did not run today.
6. **Detection is daily + 1-minute, but the drift *pytest* is unscheduled.** `audit_scheduled_tasks.py` runs at 06:00 ET under `Gamma_CryptoDaily` (verified Ready). `test_scheduled_task_triggers_live.py` — the assertion that would have screamed this morning — runs only when someone types it.

**Open and unfixed:**

7. **`Gamma_LaunchTV` did not run today** and is not root-caused. It is the "no TV = no trades" task.
8. **The task audit is permanently RED** (34 flags, 8 of which never self-clear). The next real drift lands as one line in a red report nobody re-reads. This repo already has a lesson on exactly that failure mode.
9. **`check_position` is a decorative GREEN** — reads two files that have had no writer for 57 and 42 days, and can never go RED.
10. **`check_level_feed` is now redundant and still market-hours-suppressed.** One real outage now produces three ping-worthy check names.
11. **The `test_state_freshness_audit` suite is wall-clock flaky.** It was green when I ran it. It will not always be.
12. **`binding` telemetry has never fired on a real row.** And note the interaction: on a blind day the SKIP_NO_LEVELS rail fires *before* `_execute`, so a repeat of today produces **no** sizing telemetry at all. Correct behavior — but don't expect the instrument to speak on the day you most want it to.
13. **Three commits carried another session's work under unrelated messages.** Third occurrence of the L239/L247 shape in this repo. The code is in HEAD and green; the commit history does not describe it.

**What actually protected the account today:** the risk gate (10 of 11) and a stale sight beacon (1). Both by accident — neither knows anything about levels. Not the design. That is the whole reason this repair mattered.

---

## 7. Spoken summary — morning brief

I can no longer take an entry when I have no levels loaded. I replayed today's ledger through the shipped block and all eleven of the shorts I would have placed at eleven thirty-one become a refusal, while the seven and ten entries from the two previous days are untouched.

The cause was not a bad trigger. Forty-nine scheduled tasks that the registry calls active were sitting disabled, including the level refresher and the premarket gate, and the daily audit could not see it because it skipped disabled tasks before every check.

Forty-one are back on. The level refresher is firing every five minutes on its own, and the health beacon is red on today's blindness while correctly reading the level file itself as healed.

Three state files are still showing yesterday's date right now — trade-today, the P&L statement, and the EMA snapshot — so any P&L number you read tonight is Wednesday's book. I placed no orders today.

What stopped those eleven blind shorts was the risk cap on ten of them and a stale price feed on the eleventh, which is luck, not design. If you refund the paper accounts to two thousand, safe two's ceiling goes from one sixteen to two dollars a contract and it stops refusing half its own entries, so the sizing floor is a real decision and I have not made it for you.

And I have not found who disabled those tasks. The Task Scheduler audit log is switched off on this machine, so there is no trail, and nothing yet prevents it happening again.
