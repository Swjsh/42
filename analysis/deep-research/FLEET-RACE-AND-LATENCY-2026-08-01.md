# FLEET WRITE/READ RACE FIX + FILL-LATENCY INSTRUMENT -- 2026-08-01

**WEEKEND-TWELVE Next-Twelve #4 + #5 (WS2 relaunch).** Dry-run/paper only. No orders placed
this session. No params/exit_manager/gate-registry/daily_context files touched.

---

## 1. THE RACE (#4) -- design, fix, RED-proof, replay

**Mechanism.** `heartbeat_core.py`'s `main()` writes the SAFE core-decisions.jsonl row, then
the BOLD row ~1s later (two sequential per-account passes, each doing its own network/scoring
work). `Gamma_FleetExecutor` ticks independently every 3 min (`Interval PT3M`, confirmed live
via `Get-ScheduledTask`) -- NOT synchronized with `Gamma_HeartbeatCore`'s `PT1M`. On
2026-07-31, a fleet read at **12:16:02.508** landed 0.45s after the safe row and 0.5s before the
bold row: `build_shared_signal.build()` ran TWO independent "latest row for this account today"
scans -- the top-level/safe scan picked up the FRESH 12:16 row (`bull_score=11`, A+
`BULLISH_RECLAIM_RIDE_THE_RIBBON`), the `signal['bold']` scan picked up the STALE 12:15 row
(`bull_score=9`, no fired trigger). Result: `signal['bold']['bull']['passed']` stayed `False`
even though the A+ setup was sitting in the safe row -- risky-3 (which reads `signal['bold']`)
never saw it at its freshest tick. Full forensic reconstruction:
`analysis/deep-research/WINNER-AUTOPSY-2026-07-31-1219.md`.

**Fix (additive, JSONL append-only shape preserved).**
- `setup/scripts/heartbeat_core.py`: `main()` now generates one `core_tick_id` (microsecond ET
  timestamp) per invocation and threads it into both accounts' `run_account()` calls, so every
  row logged this tick carries the identical id (new `"core_tick_id"` field, purely additive).
  After the per-account loop, `main()` writes `automation/state/core-decisions-tick.json`
  (atomic temp-file + `os.replace`, overwritten never appended) with that id -- but ONLY when
  BOTH accounts logged a real (non-exception) row this invocation.
- `automation/state/fleet/build_shared_signal.py`: resolves `_last_complete_core_tick_id(today)`
  ONCE per `build()` call (fails open to `None` -- missing/stale/wrong-day/corrupt marker -->
  the exact pre-fix two-independent-scans behavior, byte-identical) and pins EVERY block that
  reads core-decisions.jsonl (top-level/safe, `signal['bold']`, `probe`, `ladder`, `full_send`)
  to that SAME tick. `sig["core_tick_id"]` is now also emitted on the signal itself (see §2).
- In passing: `main()`'s error branch never carried a `"verdict"` key, so the tick summary
  print (`f"{r.get('verdict'):16}"`) raised `TypeError` on a real account exception -- caught by
  this session's own new marker test exercising that branch for the first time. Fixed
  (`"verdict": "ERROR"` now mirrors the ledger row one line below).

**RED-proof.** `backtest/tests/test_fleet_tick_pairing_race_2026_08_01.py`, 5/5 green:
- Write side: both accounts share one `core_tick_id` per invocation; the marker lands only
  after both log clean; an errored account withholds the marker entirely.
- Read side, reproducing Friday's EXACT interleaving (a complete 12:15 tick + 12:16's SAFE row
  present, BOLD row deliberately absent): the BITE test proves the OLD logic (no marker on
  disk) genuinely mismatches -- top-level sees the fresh 12:16 row (`bull_score=11`) while
  `signal['bold']` sees the stale 12:15 row (`bull_score=9`, `passed=False`). The fix test,
  same seeded data plus the marker, proves BOTH sides now agree on the SAME (older, but
  consistent) tick. A third test proves the marker advances the instant the pair completes.

**Replay** (`backtest/tools/fleet_tick_race_replay_2026_08_01.py`, dry-run, calls the REAL
shipped `build()` against reconstructed point-in-time snapshots of the real 2026-07-31 ledger
rows -- nothing synthesized except `core_tick_id`, assigned via each row's own minute-floor,
disclosed in the script). Two cadences x two logic versions:

| Cadence | Old logic | New logic |
|---|---|---|
| **3-min (live, PT3M)** | first ENTER-eligible read 12:19:01.000 -- hole **178.0s** | first ENTER-eligible read 12:19:01.000 -- hole **178.0s** |
| **1-min (candidate, PT1M)** | first ENTER-eligible read 12:17:02.508 -- hole **59.5s** | first ENTER-eligible read 12:17:02.508 -- hole **59.5s** |

**Honest reading, not the target-shaped one.** At the CURRENT 3-min cadence, the fix does NOT
shrink this specific historical hole -- the fleet structurally never got a chance to look
between 12:16 and 12:19, so both old and new logic land on the same 12:19 read (old by a lucky
coincidental restale onto 12:18's still-valid data; new by deliberate design onto the identical
row). What the fix guarantees, verified by the replay's own `top-level tick=` column, is that
the SAFE and BOLD perceptions inside one signal NEVER again describe two different ticks --
at 12:16:02.508 under the new logic both sides read 12:15 (consistently stale); under the old
logic top-level silently read 12:16 while bold silently read 12:15 (a real mismatch that
happened not to flip the aggregate outcome in this specific case, but is exactly the class of
defect that DID flip the outcome for real on 07-31, and would with a differently-shaped signal).
**The 180s->60s collapse the task asks for is a property of the 1-min cadence, not of the race
fix in isolation** -- the fix is the PRECONDITION that makes 1-min cadence safe from mismatched
pairs, not the thing that shrinks the hole by itself. See §3 for why 1-min cadence is not
shipped tonight regardless.

---

## 2. THE LATENCY INSTRUMENT (#5) -- fields, summary, scope

**Instrument, not redesign (per task scope) -- 4 new additive fields, zero behavior change:**

| Field | Where written | What it captures |
|---|---|---|
| `sig["core_tick_id"]` | `build_shared_signal.build()` | the exact core tick this signal is pinned to (join key) |
| `row["core_tick_id"]` | `fleet_live.run()` | passthrough of the above onto the arm's own decision row |
| `row["signal_written_at"]` | `fleet_live.run()` | the signal's own `written_at`, captured here because shared-signal.json is overwritten every tick and never archived |
| `placement["plan_ts"]` | `fleet_live.run()`, just before `_place_live()` | this arm's own "about to act" instant (more precise than the shared per-tick `now`) |
| `placement["submit_ts"]` | `fleet_live._place_live()`, just before the broker POST | OUR wall-clock, distinct from `broker.submitted_at` (Alpaca's own clock) -- the gap is real network latency |

Already-present fields reused, not duplicated: core-decisions.jsonl `ts_et` (core verdict ts),
`trigger_bar_et` (bar close), `shared-signal.json` `written_at` (signal ts), broker
`submitted_at`/`created_at` (already riding inside `placement.broker`), and
`automation/state/fills-ledger.jsonl`'s `ts_et` (the TRUE fill instant -- confirmed the
entry-order response `fleet_live.py` logs is only the INITIAL POST, `status="pending_new"`,
`filled_at: null` on the real 07-31 row; the fills ledger, built separately by
`fleet_journal_bridge.py`'s broker-activity reconciliation, is the only durable source of the
real fill).

**New module** `setup/scripts/fill_latency.py`: pure JSONL joins (fills-ledger.jsonl x
`{arm}/decisions.jsonl` x core-decisions.jsonl, keyed by `order_id` then `core_tick_id`), zero
network/OPRA cost. Computes 6 consecutive hops (bar_close->core_verdict->signal_written->plan
->submit->broker_submitted->fill) + total, honesty-rails excluded-and-counted (never
fabricated) below `MIN_RESOLVABLE_STAGES=2`. Scope: the 3 `fleet_rest` arms (safe-3/risky-1/
risky-3) -- safe-2/bold-2 (`mcp_heartbeat`) have no separate "fleet read" hop and are
explicitly out of scope, disclosed in the module docstring.

**Per-day summary, wired into the existing nightly fire** (no new scheduled task): folded into
`Gamma_WinnerAutopsy`'s 16:25 ET fire, mirroring the `pain_ledger` fold exactly (same
`last_payload["fill_latency"]` pattern, same fail-open try/except, same
`analysis/pain-ledger/` directory -> `latency.json`).

**Verified against real 2026-07-31 data** (scratch output, not yet written to production):
the 3 real fleet entry fills that day each resolve exactly 2 stages
(`broker_submitted_ts`->`fill_ts`, both already-existing fields) -- 0.098s / 0.121s / 0.180s.
The earlier 5 hops are correctly `None` (those 4 fields did not exist before this session).
This is the expected, disclosed state: **every fill from Monday 2026-08-03 onward will carry
all 7 stages automatically; historical fills stay honestly partial.**

RED-proof: `backtest/tests/test_fill_latency_2026_08_01.py`, 14/14 green (pure-function unit
tests for the decomposition/summary math + an end-to-end `build_ledger()` over synthetic
fixtures shaped exactly like the real schemas, plus direct tests on `_place_live`'s
`submit_ts`, `build()`'s `core_tick_id`, and `run()`'s row-level fields).

---

## 3. CADENCE VERDICT (#5.3) -- NOT SAFE, exactly what blocks it

**Finding: there is no order-level idempotency guard in `fleet_live.py`'s entry path.** The
ONLY guard against double-entering the same signal is `fb.is_flat_spy_options()` (`len(
open_spy_option_positions()) == 0`) -- a broker POSITIONS query. It does not see WORKING
orders. `_place_live()` submits a marketable limit and returns immediately with the broker's
INITIAL response (typically `status="pending_new"`); it never calls `fb.poll_fill()` (which
exists and is used elsewhere -- `crypto_twin_core.py`, `j_intent_executor.py`,
`dress_rehearsal.py` -- but NOT here). Confirmed by direct read of `is_flat_spy_options`
(`automation/state/fleet/fleet_broker.py:89`) and by grep across
`fleet_live.py`/`fleet_executor.py`/`fleet_broker.py` for any `claimed`/`in_flight`/
`entry_lock`/`pending_entry` concept: zero matches. (`exit_actuator.same_bar_cooldown_active`
exists and IS a real per-arm/per-setup dedup, but it is wired ONLY into
`heartbeat_core._route_extra_setups` -- the extra-setup lane -- never into `fleet_live.py`'s
primary entry path.)

**The failure mode this enables at 1-min cadence:** tick N places an order that has not yet
filled/reflected as a position by tick N+1 (60s later, vs 180s of buffer today).
`_place_live()`'s own stale-order-cancel loop (`for _o in fb.open_buy_orders(...): cancel_order
(...)`, added for the marketable-limit repricing case) does NOT re-check flatness after
attempting the cancel -- if the cancel fails because tick N's order filled in the same instant
(a genuine cancel-vs-fill race at the broker), tick N+1 proceeds to place a SECOND order
regardless. This is a structural gap, not a hypothetical one -- confirmed by reading the code
path line by line, not inferred.

**Why 3-min cadence has been safe in practice, and 1-min would shrink but not require the
same margin:** every real fill measured this session (§2) filled in well under 0.2s
(broker_submitted->fill: 0.098-0.180s), so in NORMAL conditions a 60s tick gap is enormous
headroom. But "large headroom in the common case" is not "provably safe," and the task's own
bar is proof, not odds -- especially since the SAME persistent-signal shape that caused the
07-31 miss (an identical A+ verdict held for 3 consecutive 1-min core ticks) is exactly the
shape that would exercise this gap hardest at 1-min cadence.

**Verdict: NOT SHIPPED.** `Gamma_FleetExecutor` stays at `PT3M`; no scheduled-task or registry
change made. **What would close the gap** (not built tonight -- this is instrumentation-scope,
not a fix): gate `_place_live()`'s entry on `fb.open_buy_orders(creds, symbol)` being empty IN
ADDITION to `flat` (rejects the tick-N+1 double-place outright), or a short-TTL per-arm
"order submitted this tick, awaiting fill confirmation" claim file consulted the same way
`exit_actuator.same_bar_cooldown_active` already is for the extra-setup lane. Either is a
small, mechanical, testable addition -- flagged as a follow-on, not attempted here because it
is a behavior change (a NEW gate), not logging.

---

## 4. FILES

| Path | Change |
|---|---|
| `setup/scripts/heartbeat_core.py` | `core_tick_id` stamped on every row; `TICK_MARKER` + `_write_tick_marker`; `main()` marker-write-on-complete-pair; error-branch `verdict` fix |
| `automation/state/fleet/build_shared_signal.py` | `_last_complete_core_tick_id` + `core_tick_id` threaded through every core-ledger read; `sig["core_tick_id"]` emitted |
| `automation/state/fleet/fleet_live.py` | `core_tick_id`/`signal_written_at` on the arm row; `plan_ts`/`submit_ts` on the placement dict |
| `setup/scripts/winner_autopsy.py` | additive `fill_latency` fold, mirrors the `pain_ledger` fold |
| `setup/scripts/fill_latency.py` | new -- the latency decomposition module |
| `backtest/tests/test_fleet_tick_pairing_race_2026_08_01.py` | new -- 5 tests, race fix RED-proof |
| `backtest/tests/test_fill_latency_2026_08_01.py` | new -- 14 tests, latency instrument RED-proof |
| `backtest/tools/fleet_tick_race_replay_2026_08_01.py` | new -- dry-run replay tool (no orders) |

**Test tally this session:** 396/397 green across the full fleet + race + latency + winner-
autopsy/pain-ledger suites (1 pre-existing failure, `test_fleet_keystone_consumer.py::
test_keystone_signal_drives_loose_arm_to_enter`, a "recency RED" sizing-data drift confirmed
unrelated by direct before/after comparison on unmodified code -- not touched, not in scope).
Plus 4 other pre-existing failures found and confirmed unrelated during the broader consumer
sweep (`test_1min_determinism_hash_pinned`, `test_1min_pinned_total_pnl_per_arm[core_bold-
99.0]`, `test_engine_attributed_true_via_extra_exec_2026_07_16_incident`, and 3 in
`test_money_path_2026_07_01.py`'s vwap/extra-route class -- none import
`build_shared_signal`/`heartbeat_core`, confirmed by diff-hunk-range non-overlap).

Author: fleet-race + latency-instrument lane, 2026-08-01 (Saturday, off-hours build window).
Market closed. Paper/dry-run only throughout.
