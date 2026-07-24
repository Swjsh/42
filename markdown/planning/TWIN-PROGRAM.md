# THE TWIN PROGRAM — operating system for the 24/7 crypto twin (Fable design, 2026-07-11)

> Account live as of 2026-07-11 (~09:04 ET): dedicated paper acct PA38EG1JTFBT, crypto_status
> ACTIVE, twin `account_status: LIVE`. This doc is the THINKING; build order at the bottom.
> Standing doctrine: the twin validates MECHANISM, never edge. Twin P&L = health gauge.
> Twin findings may only propose changes to CODE, never to SPY parameters.

## Reframe
SPY = ~1 uncontrolled experiment/day. The twin = unlimited CONTROLLED experiments, any hour.
Don't wait for the market to exercise a code path — SCHEDULE the path.

## Value streams (ranked)
1. **Scenario scheduler / path-coverage battery.** Force every exit lifecycle branch through
   REAL paper fills daily (TP1→trail, structure-stop, cat-cap, max-hold, restart-with-open
   -position). Scoreboard: paths exercised / paths green, per day. A HOLD-all-day twin
   validates nothing — coverage-oriented by design, opposite of production selectivity.
2. **Twin Gauntlet.** `twin_gauntlet --paths <changed>` forces N real lifecycles through a
   just-changed code path and diffs vs expected. Conductor hook: trading-path commits without
   a gauntlet pass get flagged. This mechanizes "fix → live-verified in minutes."
3. **Transferable execution research.** Broker-interaction mechanics are instrument-agnostic:
   fill-poll reconciliation (T-AUDIT-03 class), exit refire dedupe (F7 class), partials,
   passive-limit entry machinery (T-W5) runs LIVE here and graduates on real fills before SPY.
4. **Chaos drills (weekly).** Injected failures we'd never dare on SPY: process kill
   mid-position, corrupt state file, stale feed, breaker mid-trip. Resilience ledger.
5. **Detector telemetry (shadow).** Pattern-grammar rules log-only on live crypto: firing
   rates, repaint-safety, C6 closed-bar discipline. Never edge claims.
6. **Learn-loop reps.** Autopsy/funnel/hypothesis machinery cycles dozens of times daily.
   Twin-hypothesis lane restricted to CODE fixes.

## Design decisions (the subtle stuff)
- **UNIT-LOT MODE (required):** fractional crypto would silently skip integer-qty arithmetic
  (2/1 TP1-runner split, int floors). Twin trades qty=3 fixed units (1 unit = small BTC
  quantum) so exit_manager.from_entry's exact production integer paths run live.
- **Long-only limitation:** Alpaca crypto can't short → bear-side (P) lifecycles stay
  fixture-tested (side-mirrored unit tests). Documented gap, not hidden.
- **Attribution discipline:** every row/fill/journal entry twin-tagged; firm brief gets a
  TWIN line with the path-coverage scoreboard (P&L small, labeled health-only).
- **Param freeze:** twin signal/exit params change only for COVERAGE reasons, never chasing
  twin P&L. No new symbols until BTC mechanics prove limiting.
- **Fee model note:** Alpaca crypto taker fees ≠ options economics — one more reason twin
  P&L is never comparable/transferable.

## ROI metric (honesty rail)
`mechanism_bugs_caught_before_RTH` (twin-attributed findings that produced a code fix before
the next SPY session). If not accumulating within ~2 weeks, re-examine the program.

## Build order
- **B1 (now, Sonnet):** unit-lot mode + scenario scheduler + path-coverage scoreboard state.
- **B2 (now, Sonnet):** twin gauntlet + conductor hook; attribution + twin-autopsy lane +
  firm-brief scoreboard line.
- **B3 (SHIPPED 2026-07-15, Fable worker lane):** entry_manager live measurement on twin
  (graduate T-W5). See "B3 shipped" section below.
- **B4 (SHIPPED 2026-07-15, Sonnet overnight lane):** weekly chaos drill + resilience
  ledger. See "B4 shipped" section below.
- **B5 (queued):** pattern-grammar shadow telemetry on twin.
- **Doctrine:** CLAUDE.md one-liner proposal (propose-only) folding the amended crypto
  boundary + this program's existence; memory entry. **DRAFTED 2026-07-23 (conductor,
  TWIN-DOCTRINE-FIRST-DEPLOY) — pending J ratification, see "Doctrine proposal" below.**

## B3 shipped (2026-07-15) — passive-limit entry LIVE A/B (stream 3, EDGE-1 graduation)

**What runs now:** every LIVE twin entry (organic or scenario-forced) routes through
`crypto_twin_core.place_entry_ab`, which deterministically ALTERNATES cohorts off
`automation/state/crypto-twin/entry-quality.json`'s persisted `ab_counter` (even →
marketable = the pre-B3 market-order path byte-identical; odd → passive = entry_manager's
T-W5 machinery run live). The passive actuator (`setup/scripts/crypto_twin_entry_quality.py`)
rests a REAL limit at mid-spread (non-marketable by construction), drives
`entry_manager.plan_entry_action` as the patience/cancel governor (patience=3 + policy=cancel
= entry-2's frozen pre-registration, reused verbatim; delta is the one crypto-recalibrated
knob, computed per-entry so the limit lands mid-spread), keeps the BROKER as fill authority
(C11), handles the fill-during-cancel race, and flattens partial-fill crumbs (unit-lot
integrity). Every attempt → entry-quality.json aggregates (fill rate / abandonment /
time-to-fill / price improvement vs the ask-at-signal baseline, $/BTC + bps) + one
tier-tagged mechanism-only `ENTRY_QUALITY` journal row. Passive misses surface as
`PASSIVE_ENTRY_MISSED` (scheduler-compatible: branch simply retried later, never a false
INCIDENT). Fail-open: any passive-path degradation falls back to the marketable path.

**First live rep (2026-07-15 03:57 UTC, quoted in STATUS.md):** limit BUY 0.0024 BTC @
$64,764.15 vs quote ask $64,803.88 / bid $64,724.41 — rested 60.7s, FILLED at the limit →
real improvement **$39.73/BTC = 6.13 bps** vs the marketable baseline. Order id
`6ca7aa4b-6f2f-4ba2-869d-41339774e471`.

**ROI ledger (mechanism_bugs_caught): the FIRST rep caught 2 real pre-existing bugs:**
1. **Sell-qty round-up** — `place_crypto_order` `round(qty,8)` requested 1e-9 more BTC than
   the fee-shaved balance (0.0023964 vs 0.002396399 held) → Alpaca 403 on the SELL_ALL.
   Fixed: sells FLOOR to 8dp. Guard: `test_sell_qty_floors_never_rounds_up`.
2. **Failed close deleted the record** — `manage_positions` ran `del positions[symbol]`
   despite the broker `_error`, orphaning real holdings with no exit-managed record. Fixed:
   failed SELL_ALL/max-hold closes KEEP the record (pre-tick state restored) and journal
   `CLOSE_FAILED`; retried next tick. Guards:
   `test_manage_positions_failed_*_keeps_position_for_retry`.

**GRADUATION BAR FOR SPY (documented, NOT implemented):** ≥ 20 twin passive FILLS accrued
in entry-quality.json with fill-rate + improvement stats, THEN a frozen SPY A/B
pre-registration (entry-2's frozen params: delta=0.10, patience=3, policy=cancel) before
any SPY path change. Twin numbers inform MECHANISM only — never SPY evidence.

**Known boundary (pre-existing, noted not changed):** exit_manager's `time_stop_15:50` means
any twin position entered 15:50–23:59 ET closes on the next tick via time_stop (graded
always-acceptable). Entry measurement is unaffected; lifecycle reps skew to 00:00–15:50 ET.

## B4 shipped (2026-07-15, Sonnet overnight lane) — weekly chaos drill + resilience ledger

**What runs now:** `setup/scripts/twin_chaos_drill.py` — four failure injections against the
REAL twin, run one at a time, each restoring clean state before the next starts. Every drill
drives REAL production functions (`crypto_twin_core.run_tick`/`place_entry`/`load_breaker`/
`_risk_gate_check`, `crypto_twin_broker`'s REST calls, `crypto.lib.kill_switch.tick`) — the
module invents zero new decision logic, it only injects, observes, restores, and journals.

1. **process_kill_mid_position** — opens a real `CHAOS_DRILL_PROCESS_KILL`-tagged position,
   launches a real managing tick as a subprocess (the exact `crypto_twin_health.py --live`
   entrypoint), force-kills it mid-flight (`TerminateProcess`), then proves a fresh tick
   recovers via `classify_recovery()`'s decision table. Force-flattens at the end regardless.
2. **corrupt_state_file** — malforms `exit-state.json`'s bytes, proves `_load_positions`
   fails OPEN (never raises), restores the exact original bytes.
3. **stale_feed** — feeds `run_tick` a bar closed 3h stale via the real injectable
   `raw_bars` param, proves `bar_reader`'s staleness verdict fires (`HOLD_BAD_BARS`, zero
   order risk, WATCH-mode by construction).
4. **breaker_mid_trip** — overwrites `breaker.json` with a LATCHED-tripped doc (healthy
   current_equity, isolating the latch property), proves the real
   `load_breaker -> kill_switch.tick -> risk_gate.check_order` chain halts (`code=KILL_SWITCH`),
   restores the exact original bytes, proves the same chain re-arms.

Each rep appends one row to `automation/state/crypto-twin/resilience-ledger.jsonl`:
`{drill, injected_at, observed_at, recovered, recovery_path, notes, evidence}`. Registered
weekly via `Gamma_TwinChaos` (Sunday 03:00 ET / 01:00 MT, `install-twin-chaos-drill.ps1`,
same flash-free `wscript->run_exe_hidden.vbs->pythonw` chain + reaper-exemption pattern as
`Gamma_CryptoTwin`/`Gamma_TwinSentinel`). Twin-only by construction
(`crypto_twin_core._assert_twin_namespace` static+runtime guard) — never touches SPY/fleet/
core state, params, or orders. Guards: `backtest/tests/test_twin_chaos_drill.py` (30/30) +
`test_twin_chaos_drill_reaper_exemption.py` (13/13).

**First live drill cycle (2026-07-15, build session):** all 4 drills `recovered: true`
against the real twin. `stale_feed` — `HOLD_BAD_BARS`, staleness correctly detected, zero
new orders. `breaker_mid_trip` — real HALT (`code=KILL_SWITCH`), real RE-ARM (`code=ALLOW`),
`breaker.json` restored byte-identical. `corrupt_state_file` — fail-open confirmed,
`exit-state.json` restored byte-identical. `process_kill_mid_position` — real BTC/USD entry
at $64,697.78, the managing subprocess genuinely killed mid-flight
(`killed_before_completion: true`), recovery classified `STATE_CONSISTENT_WITH_BROKER`,
force-flattened clean. Twin verified flat post-drill (`exit-state.json: {}`,
`scenario-state.json: {}`). A first process-kill rep at the 2.5s default timeout finished
before the kill landed (honestly logged as a weaker rep, still recovered) — added a
`--kill-after-sec` CLI knob after observing the twin's real managing tick completes faster
than that on calm BTC; the retry at 0.3s produced a genuine mid-flight kill.

**Bug caught + fixed same session (mechanism_bugs_caught):** the first two offline
pytest runs silently wrote fake test rows into the REAL `resilience-ledger.jsonl` —
`cfg`'s `state_dir` was tmp_path-isolated but `append_resilience_row`'s `ledger_path`
defaulted to the real production path regardless of `cfg`. Caught by inspecting the ledger
after the first live run and finding fake-broker-shaped rows (`"$65,000.00"`, `"no twin
creds"`) interleaved with genuine ones. Fixed by threading `ledger_path` through every
`drill_*()` function, resolved inside the function body rather than as a bound default —
the identical bug class `force_flatten_position`'s `close_fn` default hit first (caught by
its own offline test before this one landed, itself a repeat of the exact class
`twin_gauntlet.py`'s `_write_last_result` docstring and `trade_autopsy.py` already
document: "a default parameter is snapshotted ONCE when the function is defined"). 18
polluted rows removed from the real ledger; 5 genuine rows kept.

## B2 interfaces (gauntlet <-> scenario scheduler) -- shared doc comment, 2026-07-11

B2 shipped `setup/scripts/twin_gauntlet.py` (the requester/poller/reporter) +
`setup/scripts/twin_gauntlet_conductor_hook.py` (the advisory conductor/nightly-guard
flag) + the autopsy/firm-brief twin integrations. This section is the CURRENT, single
copy of the queue contract both crews' code should agree on (mirrored in
twin_gauntlet.py's own module docstring -- if the two ever drift, THIS file + a fresh
read of both modules' docstrings is the tie-break, not either crew's memory).

**gauntlet-queue.jsonl** (`automation/state/crypto-twin/gauntlet-queue.jsonl`, WE write,
the scenario scheduler READS, APPEND-ONLY): one REQUEST row per requested path --
`{request_id, path, n, requested_at_utc, requested_at_et, timeout_min, status:
"REQUESTED", source: "twin_gauntlet"}`. Rows are never rewritten in place -- a
consumer's claim/progress state belongs in path-coverage.json, never a mutated queue row.

**path-coverage.json PROPOSED schema** (what twin_gauntlet.py's poller + firm_brief.py's
scoreboard suffix read): `{"paths": {"<path_id>": {"status": "green"|"red", "last_request_id",
"last_updated_utc", "n_green_today", "n_total_today", "last_incident", "evidence": [...]}}}`.
`record_path_result()` in twin_gauntlet.py is a ready-made writer matching this shape.

**KNOWN SCHEMA MISMATCH (found 2026-07-11, verified live against B1's actual in-flight
file, NOT a guess):** B1's real `path-coverage.json` (as of this commit) uses a
DIFFERENT shape -- top-level `{"date_utc", "branches": {"<BRANCH_NAME>": {"tier":
"LIVE"|"SIM", "status": "PENDING"|"IN_PROGRESS"|"NOT_YET_COVERED"|..., "count_today",
"last_exercised_utc", "last_result"}}}`. B1's branch names map 1:1 onto twin_gauntlet's
`PATH_REGISTRY` path ids by a simple prefix/case transform:

| B1 branch name (LIVE tier) | twin_gauntlet path id |
|---|---|
| `ENTRY_TP1_TRAIL` | `tp1_trail` |
| `ENTRY_STRUCTURE_STOP` | `structure_stop` |
| `ENTRY_CAT_CAP` | `catastrophe_cap` |
| `ENTRY_MAX_HOLD` | `max_hold` |
| `RESTART_OPEN_POSITION` | `restart_open_position` |
| `ORGANIC_SIGNAL` | `entry` |
| `ENTRY_TP1_TRAIL_BEAR` / `_STRUCTURE_STOP_BEAR` / `_CAT_CAP_BEAR` (SIM tier) | no twin_gauntlet equivalent yet -- bear-side lifecycles are fixture-only per this doc's "Long-only limitation" |

Both crews independently converged on the SAME conceptual 6-branch (now 9, +3 bear/SIM)
coverage battery -- good design-coherence signal, just a naming/schema reconciliation
left undone. At B2's commit time, B1's `status` vocabulary had not yet reached a
terminal/"passed" value in the live file (every branch was PENDING/IN_PROGRESS/
NOT_YET_COVERED, `last_result` null everywhere) -- there was nothing yet to verify a
"success" literal against, so B2 deliberately did NOT guess-adapt its reader to an
unobserved, still-settling status value (a wrong guess would silently show "0 green"
even after B1's scheduler starts succeeding, which is worse than an honest "no
path-coverage data yet"). CORROBORATED same session (STATUS.md, "Gamma_TwinSentinel"
entry, a THIRD concurrent crew): the real enum is `status ∈ {PENDING, IN_PROGRESS,
NOT_YET_COVERED, GREEN, INCIDENT}` and a tested parser already exists --
`crypto_twin_health.summarize_path_coverage()` (per that entry) / twin_sentinel.py's
`parse_path_coverage()`. Whoever reconciles B2's `paths`/green-red reader against B1's
real `branches`/status shape should crib from THAT parser (already fighting this exact
battle, already tested against the real producer) rather than writing a third one.

**Reconciliation options for B1/the reviewer (either is fine, pick one):**
1. B1's scenario scheduler calls `twin_gauntlet.record_path_result(path_id, status="green"/"red",
   ...)` directly once a branch resolves (translating BRANCH_NAME -> path_id per the table
   above) -- zero new code on B1's side beyond the translation, reuses B2's already-tested
   writer/atomic-write.
2. OR a small adapter (either module) translates B1's `branches`/status vocabulary into
   the `paths`/green-red shape once B1's terminal "success" status literal is known.

**gauntlet-last.json** (`automation/state/crypto-twin/gauntlet-last.json`, twin_gauntlet.py
writes after every `twin_gauntlet` CLI run, DRY or LIVE): `{"ts_et", "mode": "DRY"|"LIVE",
"overall": "PASS"|"FAIL", "paths": {"<path_id>": "PASS"|"FAIL"}}`. firm_brief.py's TWIN
line reads this fail-open for the "gauntlet: PASS 20:41" clause.

**THE ONE-LINE HOOK** (not yet called by anything -- B1's crypto_twin_scenarios.py exists
on disk as of this commit but does not yet import twin_gauntlet):
```python
import twin_gauntlet as tg
for req in tg.pending_requests():   # every REQUESTED row not yet reflected in path-coverage.json
    ...  # force req["path"]'s lifecycle req["n"] times via the twin's real exit path
    tg.record_path_result(req["path"], status="green"/"red", request_id=req["request_id"], evidence=[...])
```

**Conductor hook file->path mapping** (`setup/scripts/twin_gauntlet_conductor_hook.py`'s
`TRADING_PATH_FILES`): `exit_manager.py`/`exit_actuator.py` -> all 5 exit-lifecycle paths;
`fleet_executor.py`/`fleet_live.py`/`heartbeat_core.py` -> all 6 paths (orchestration
layer, mapped broadly/conservatively); `strategies.py`/`build_shared_signal.py`/
`risk_gate.py` -> `entry` only. Watermark:
`automation/state/crypto-twin/gauntlet-conductor-watermark.json` (shared by both call
sites: `run-conductor.ps1` primary, `setup/guard_runner_slow.py` nightly fallback --
idempotent, dedup by newest implicated commit sha).

## Doctrine proposal (drafted 2026-07-23, conductor, TWIN-DOCTRINE-FIRST-DEPLOY — propose-only, PENDING J RATIFICATION)

This closes the last open "Build order" line above. The conductor rail-4 carve-out that
lets an autonomous fire ship PAPER trading-path edits does NOT cover `CLAUDE.md` itself
(doctrine stays J-first, full stop) — so this section is a DRAFT for J to ratify, not a
shipped change. Nothing in CLAUDE.md has been edited by this fire.

**Why now, not invented:** the conductor hook (`twin_gauntlet_conductor_hook.py`) has
been advisory-flagging trading-path commits without a gauntlet pass since B2 (2026-07-11)
— this proposal is the practice that's already running getting a doctrine anchor, not a
new behavior being bolted on.

**Proposed CLAUDE.md text** (one sentence appended to existing OP-31, same bullet the
Kitchen already lives in — both are 24/7 free-tier-ish autonomous R&D loops, so folding
saves a whole new numbered OP and its context-budget cost):

> **Twin-first deploy (2026-07-23):** any new watcher/detector/exit-lifecycle feature runs
> 24-48h on the 24/7 crypto twin (paper, mechanism-validation only — twin P&L is never SPY
> evidence) before touching a SPY execution path. Spec: [`TWIN-PROGRAM.md`](markdown/planning/TWIN-PROGRAM.md).

**Context-budget honesty (OP-33):** `check-context-budget.ps1` reads YELLOW 8848/9000
(98%) as of this draft. The proposed sentence is ~60 tokens — lands at ~8923/9000, stays
YELLOW, does NOT cross the 9000 RED line, but leaves near-zero headroom for the next
addition. Flagging this rather than silently accepting it; a dedicated context-leanness
trim pass (last one: 2026-07-21) is due again soon, independent of this proposal.

**Ratification path:** filed as `conductor-proposals.jsonl` proposal id
`gp-2026-07-23-twin-doctrine-001` (no `eval_bar_cleared` — this is doctrine, not a
validated edge, so it does NOT auto-apply; it sits pending until J replies `ship
gp-2026-07-23-twin-doctrine-001` on Discord or approves on the companion wrist card).
Once approved, `AutoApply` performs the single exact-string OP-31 replacement, runs the
safety gate, commits, and the memory entry below is confirmed live.
