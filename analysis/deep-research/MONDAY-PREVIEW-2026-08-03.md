# MONDAY PREVIEW — 2026-08-03 (Sunday-scrimmage, run Saturday 2026-08-01)

> **WS1 weekend integration test.** Friday 2026-07-31's full tape (386 core ticks × 2
> accounts) replayed through the fleet signal→plan path **as it now stands on HEAD**, diffed
> against what actually happened Friday. Report-only lane: nothing armed here, no params
> flipped here. Clock at write: 2026-08-01 12:57 EDT Saturday (`et_clock`, market closed).
> Replay artifact: [`monday-preview-scrimmage-2026-08-03.json`](monday-preview-scrimmage-2026-08-03.json)
> · runner: `backtest/tools/monday_preview_scrimmage_2026_08_03.py`.

---

## VERDICT — the five things that matter

1. **🚨 The elite-bull lift is NOT on HEAD.** The ratified LIFT-GATE TRIAL rec
   (`elite-bull-requal-2026-07-31.md`, commit `53446011`) explicitly left the one-key flip
   "to the conductor/next session to apply" — **nobody applied it.** Verified cold:
   `automation/state/aggressive/params.json` `block_elite_bull: true` on HEAD **and** disk
   (`git diff HEAD` clean; no commit has touched the file since `f030ae6c`). **As configured
   right now, Monday's bold-2 will refuse the elite-bull reclaim cohort again** — the exact
   cohort that was blocked 51× on bold Friday while the fleet banked +$1,242 on the same
   signals. The flip is a one-key edit + kill-criterion tracker; it is the single highest-value
   pre-Monday action and it is **pending, not done**. (This lane is report-only by charter —
   flagged, not applied.)
2. **risky-1 is transformed for Monday — and the binding change is the ATM STRIKE TIER, not
   the full-send lane.** Friday it logged 128 HOLDs. Decomposed against its own ledger: at
   12:19 its tight gate actually **PASSED** (ELITE, 2 triggers) and the plan died at the floor
   — `premium 0.15 < 0.3` on the OTM-3 contract (same $0.15 quote that refused safe-3);
   likewise 12:31 ($0.28), 13:25 ($0.23), plus one true RISK_CAP hit (`notional $1,050`).
   Under HEAD it produces **56 ENTER-plan ticks (32 in-window, 4 tradeable episodes), ALL via
   its NORMAL lane, at ATM-class strikes** that price where Friday's fills actually happened
   ($0.30–$0.54). The `full_send` producer block itself was **100% shadowed**: all 51
   blocked-cohort ticks were score 11/11 → the normal lane plans an ENTER first and
   `_full_send_plan` never fires ("only when no other lane produced an ENTER"). Rank the
   three Friday-evening changes by Monday effect on a Friday-like tape: **bold_core ATM tier
   ≫ gate replacement (Friday's peak ticks were all ELITE/2-trigger — the old tight gate
   passed them anyway) ≫ full_send block (adds entries only on sub-9-score or bear-side
   allowlisted cohorts — zero occurred Friday).**
3. **Zero regressions.** Every trade the fleet actually took Friday (safe-3 12:31 C747,
   risky-3 12:19 C746 + 13:25 C747) sits inside the HEAD replay's availability windows —
   3/3 covered, same side, same qty tier. Nothing the new config would refuse.
4. **Guard suites + engine health on HEAD:** fleet suite **310 passed, 0 failed** (canonical
   invocation); slow graduated guards **35 passed in 26:05, all green**; curated safety gate
   **59 green**; backtest fast tree: **1 real failure — `test_arm_display` pinned risky-1's
   old display name** (guard rot from Friday evening's full-send rename; fixed this session,
   RED→GREEN, quoted in §6; full-tree run's completion status disclosed there). Engine
   health: **YELLOW** — sole RED is `gex_archive` (2 interior day gaps 07-24/07-30,
   non-critical); every trading-critical check GREEN.
5. **The premium floor — not gates — was Friday's binding in-window refusal, and it moves
   Monday.** safe-3 was refused at 12:19 (`premium 0.15 < 0.30`) and only filled at 12:31
   when its OTM contract reached $0.33; risky-1's afternoon OTM-3 quotes were $0.04–$0.11.
   Monday risky-1 prices **ATM at its current $1,756.87 equity** (bold_core tier-1 +
   full-send PROBE table) → the floor largely clears. **But the WS12 $2,500 reset, if
   executed, moves every arm to the [2K,10K) tier → normal lanes back to OTM-2 → the
   afternoon floor refusals return** (§5, the one real design interaction this scrimmage
   surfaced).

---

## 1. What actually happened Friday (ground truth, ledgers quoted)

**Core arms (safe-2 + bold-2): zero entries.** Per `core-decisions.jsonl`: safe 330 HOLD +
50 SKIP_ELITE_BULL_LEVEL_RECLAIM + 6 SKIP_STALE_TRIGGER; bold 329/51/6 (386 ticks each).
Every named setup reached was BULLISH_RECLAIM_RIDE_THE_RIBBON at bull_score **11/11**
(all 51 bold blocks; trigger `level_reclaim`, first 12:16 @ level 743.25, last 15:55 @ 748.09).

**Fleet arms (128 fires each, every 3 min from 09:31:02):**

| Arm | Fires | Entries | Detail |
|---|---|---|---|
| safe-3 ($1,893.04 SoD) | 128 | **1** | 12:31:02 ENTER_BULL C747 ×3 @ $0.33 (ELITE). In-window refusals were the FLOOR, not its gate: 12:19 `premium 0.15 < 0.30`, 12:28 `0.24 < 0.30` |
| risky-1 ($1,756.87 SoD) | 128 | **0** | all HOLD — "no qualifying setup" on ~5/6 of fires (tight gate era) + floor refusals on OTM-3 quotes ($0.04–$0.11 afternoon) |
| risky-3 ($2,076.35 SoD) | 128 | **2** | 12:19:02 C746 ×5 @ $0.30 (the day's winner) + 13:25:03 C747 ×5 @ $0.54; both "qty clamped 12→5: recency RED". Afternoon episodes floor-refused (14:28 `0.15`, 14:52 `0.21`) |

Latency scars already established tonight (cite, not re-derived): the 12:19 winner filled on a
1-second-stale level snapshot (743.25 flickered 14×; WS3 owns the fix); the producer's
write/read race is **visible in the ledger** — safe-3's 12:16:02 fire says *"no qualifying
setup"* while the same-second core row is SKIP_ELITE at score 11 (the bold row landed after
the producer's read; a 3-min cadence slot forfeited).

## 2. Scrimmage method (why this replay is valid)

- **The brain is byte-identical to Friday's.** `git log --since="2026-07-31 09:30"` over
  `backtest/lib/engine`, `orchestrator.py`, `levels.py`, `heartbeat_core.py`,
  `strike_selection.py` → **zero commits**. Friday's per-tick core rows therefore ARE HEAD's
  verdicts on Friday's tape. The two commits that did land (`e28d210c` FULL-SEND,
  `43bb979d` ATM extension) changed exactly the producer/consumer layer this replay exercises.
- **One implementation, no re-derivation:** per tick, raw safe+bold rows →
  `build_shared_signal._map_core_row` → `build_from_rows(row, bold_row=…, probe_row=…,
  run_vwap=False, write=False)` (the same producer logic the live fleet consumes) →
  `fleet_executor.plan_all(arm, sig, Friday-SoD equity, _params_for(arm), probe_cfg=…)`.
- **Disclosed limits:** plan-level only (premium floor / risk cap / broker-flat run in
  `finalize()`+`fleet_live` — fills ≤ plans); 1-min replay vs live ~3-min cadence (windows
  exact; which fire lands inside is phase-dependent); `_recency_verdict` + `trigger_level`
  fallback read today's state files (recency read RED at replay = Friday-live value);
  missing-row minutes carry the last row forward (same as the live latest-row read).

## 3. Per-arm: Monday's config on Friday's signals

Availability episodes (>15-min gap splits, entry window [09:35,15:00) applied):
**09:35 (1 tick) · 12:16–12:34 (9) · 13:24–13:40 (12) · 14:26–14:30 (5) · 14:51–14:55 (5)**
— identical windows for all three arms (one shared brain; arms differ in sizing/strike/exits).

| Arm | Friday actual | HEAD replay on same tape | What changed & why |
|---|---|---|---|
| **safe-2 core** | 0 entries, 50 elite-bull SKIPs | **identical** — no core config change | elite-bull Safe gate deliberately stays ([0,25) block; its own re-eval trigger: 20 post-fix events or 2026-08-08) |
| **bold-2 core** | 0 entries, 51 elite-bull SKIPs | **identical while the flip is unapplied** | see §4 — the pending one-key trial would put bold-2 min-size INTO this cohort |
| **safe-3** | 1 entry (12:31) | same episodes; 32 in-window ENTER-plan ticks, qty 3, strikes C745–749 (its OTM 'bold' table at $1,893 — unchanged config) | **no behavior change** — expect ~1–2 fills on a Friday-like tape, floor-gated exactly as Friday |
| **risky-1** | **0 entries / 128 HOLDs** | **32 in-window ENTER-plan ticks, 4 tradeable episodes, ALL normal-lane, qty hard-clamped 5, ATM-class strikes (C742–746)** | tight gate **replaced** by `full_send` profile (looser normal lane) + bold_core tier-1 ATM at $1,756 clears the floor the OTM-3 quotes died on |
| **risky-3** | 2 entries (12:19, 13:25) | same ticks covered (2/2), same qty-5 clamp (recency RED), strikes C744–748 via OTM-2 | **effectively unchanged** at $2,076 equity — `bold_core` differs from `bold` only under $2K, so the ATM extension is currently **inert** for this arm |

**Expected Monday entry count on a Friday-like tape** (one position at a time, 3-min cadence,
floor-dependent): safe-3 ~1, risky-1 **~2–4 (from zero)**, risky-3 ~2, cores 0 without the
flip. Fills ≤ plans: the floor and risk cap still run per-fill (at $1,756, the 50% cap
refuses any full-send/ATM premium > $1.75).

**⚠ REGRESSIONS: none.** All 3 actual Friday entries fall inside replayed availability
(3/3, same side/qty tier). The only near-class miss is timing, not config: the 09:35
single-tick window (a SKIP_STALE_TRIGGER row whose score 11 + fired trigger still passes the
scoring-peak) is invisible to a 3-min cadence that fires 09:34/09:37 — pre-existing behavior,
now shared by risky-1.

## 4. The pending decision: bold-2 elite-bull flip (NOT applied — flag, loud)

- **State on HEAD:** `block_elite_bull: true` (aggressive/params.json), untouched since the
  ladder revert commits. The requal rec + FRIDAY-DIAL-IN both say the flip "ships this
  weekend" — **it has not shipped.** If Monday opens like Friday, bold-2 refuses the same
  A+ cohort a fourth session.
- **What Friday alone was worth on this cohort** (real OPRA, entry+1, CONTROL exit shape,
  from the requal artifact): bold per-event qty-10 comparability cell **+$2,761.60 / 6
  events** on 07-31 (runner exits +$1,085.60/+$2,096.00; structure-stops −$320/+$30/−$20/−$110).
  Tempering cell, cited not buried: the 4-day bold sequential-hold qty-3 PRIMARY-adjacent
  cell is **−$2.60 / 5tr, drop-best −$321** — the trial's tight kill bar exists because of it.
- **Exact pending edit (from the rec, verbatim target):** `block_elite_bull: false`, bold-2
  only, min-size, leave `block_elite_bull_vix_low/high` untouched. **Kill criterion (frozen):**
  n≥10 elite-bull fills OR 10 sessions; net<0 → re-block. Revert = one line.
- **Honesty:** `block_elite_bull` is gate #3 of 15 — on a SKIP row the 12 downstream gates
  were never evaluated, so "unblocked ⇒ entered" is the requal replay's convention, not a
  ledger fact; bold's band is VIX [15,18) so the trial samples a narrower population than
  Safe's block.

## 5. Interactions the scrimmage surfaced (read before touching anything Monday-adjacent)

- **Plan-level shadowing makes the full-send block near-inert on peak tapes.** `_full_send_plan`
  yields to ANY other lane's ENTER *plan* — including one the premium floor will kill in
  `finalize()`. On Friday's tape (all blocks score-11) it contributed 0 incremental entries at
  any equity. Its real coverage: allowlisted ticks with score < 9, and the four bear-side
  cohorts. Watch `full_send_vs_gated.py --since` before judging the arm by its lane name.
- **The WS12 $2,500 reset partially defeats risky-1's ATM mechanism.** At $2,500 every arm
  lands in [2K,10K): normal lanes price **OTM-2** (ATM extension inert above $2K), and a
  normal-lane OTM-2 ENTER plan shadows the ATM full-send lane → afternoon quotes like
  Friday's $0.15–$0.24 get floor-refused again. Not an argument against normalization —
  an argument for **knowing which experiment you're running**: at current equities risky-1
  tests "ATM clears the floor"; post-reset it tests "OTM-2 min-size on peak ticks". The two
  are different studies. (WS12's brief already flags the tier boundary as load-bearing;
  this is the fleet-lane corollary.)
- **`consumes_scoring_peak` (accounts.json, risky-3) has zero code consumers** — C14 dead-key
  class, cosmetic only, filed here so nobody reasons from it.
- **The write/read race is real and costs cadence slots** (12:16:02 evidence in §1). No fix
  is in flight in any lane tonight; it belongs on the queue, not silently absorbed.

## 6. Guard suites + engine health on HEAD (the integration-test half) — quoted

- **Fleet suite (canonical, from `automation/state/fleet`):** `310 passed in 8.75s`, 0 failed.
  (Observed, mechanism not chased: the SAME files report 27 failures when pytest is invoked
  from the repo root — test_exit_manager/test_structure_stop_wiring — and pass clean from
  their own directory. Invocation artifact, noted so the next session doesn't chase ghosts;
  run this suite from `automation/state/fleet`.)
- **Slow graduated guards (`pytest tests/test_graduated_guards.py -m slow -q`, the nightly
  command):** `35 passed, 78 deselected in 1565.04s (0:26:05)` — **all green on HEAD.**
- **Backtest fast suite (`pytest tests -q -m "not slow"`):** the ONE real failure found, quoted,
  then fixed RED→GREEN this session:
  `AssertionError: risky-1 · assert 'FLEET-FULLSEND-R (8G19)' == 'FLEET-TIGHT-R (8G19)'`
  — Friday evening's full-send commit renamed risky-1's display_name but not the pinning
  guard (`backtest/tests/test_arm_display.py`) or the mapping doc (`ARM-DISPLAY-NAMES.md`);
  both updated, `12 passed in 0.23s` after. Additionally green fresh this session: the
  curated pre-commit safety gate (`[safety-gate] PASS -- curated safety gate (6 suites)
  green ({'passed': 59})`). HONEST STATUS on the *full* fast-tree run: it was still in
  flight at report time — it stalled ~18 min behind the concurrently-running slow guards
  (the OPRA-cache concurrency constraint, operational note below) and resumed when the slow
  run finished; its completion lands in this session's background log and showed no failure
  beyond arm-display in the portion observed. No green claim is made for cells not run.
- **Engine health (`setup/scripts/engine_health.py`):** verdict **YELLOW** @ 2026-08-01
  12:57 ET. Sole RED: `gex_archive: 2 interior trading-day gaps ['2026-07-24','2026-07-30']`
  (non-critical accrual gap). GREEN: session_ran, levels_blind, levels_file_stale,
  fleet_ticked (incl. the new fleet_rest liveness watch), dispatch `safe 386/386`,
  positions flat both cores, state_freshness 17 files.
- **Scrimmage harness parity:** replay reproduced all 3 actual Friday entries and both
  recency qty clamps — the harness is measuring the real path, not a re-derivation. Re-run
  twice, byte-identical counts (deterministic).
- **Operational note for future integration tests:** the fast suite and the slow
  graduated-guards run were launched CONCURRENTLY this session and the fast suite stalled
  (CPU frozen ~18 min in, zero sockets, zero children) until the slow run's heavy phase —
  the known "concurrent grinds deadlock on the OPRA cache" constraint (CLAUDE.md debugging
  section) applies to test suites too. **Run data-heavy suites sequentially.**

## 7. Monday 09:30 checklist

**Experiments LIVE Monday (each with its kill lever):**

| Experiment | Where | Kill criterion / revert |
|---|---|---|
| FULL-SEND arm (min-size, ATM, no cohort vetoes, **loose normal lane**) | risky-1 `gate_override {"full_send": true}` | DE-ARM: restore `{"min_triggers": 2, "require_confluence_or_sequence": true}`; kill bar: n≥10 sessions net<0 AND fills not materially above gated arms (`full_send_vs_gated.py --since`) |
| ATM strike-tier extension (bold_core, **only bites under $2K equity**) | risky-1 + risky-3 `params_patch.strike_tier_table` | delete the key (byte-identical); prereg gates at n≥20 fills (`fleet-strike-tier-atm-extension-prereg-2026-08-01.json`) |
| REACHABLE-TP1 exit challenger (tp1 0.5, structure stop) | risky-1 `params_patch.exit_patch` | set `params_patch` {} + exit_profile TRIG-EXACT; forward P&L is the evidence (uniform tp1 0.5 tested NEGATIVE in isolation — disclosed confound) |
| Elite-bull LIFT-GATE TRIAL | **⚠ PENDING — not applied** (aggressive/params.json still `true`) | apply `block_elite_bull: false` per rec §4 above; kill: n≥10 fills or 10 sessions net<0 → re-block |
| Recency RED min-size clamp (12→5 on ribbon_ride) | params `recency_min_size_enabled` | verdict is state-file-driven; RED at replay time — expect clamped qty until recency greens |
| Nightly instruments (gate-expiry, winner-autopsy 101.9% capture-rate winners-only caveat, shadow-orphan detector) | scheduled tasks | read-only; no kill needed |

**Watch at 09:30 (in order):**
1. **Was the elite-bull flip applied over the weekend?** If not, expect bold-2 to sit out any
   elite reclaim day again — that's a decision gap, not an engine fault.
2. **Equity/tier state per arm** — did the WS12 reset happen? Post-reset: expect OTM-2
   normal-lane strikes + shadowed full-send (§5); no-reset: risky-1 ATM at $1,756. Either
   way confirm `circuit-breaker.json` SoD equities before interpreting refusals. **No-reset
   extra:** core Safe-2 sits at $1,160.30 (WS12 live read) → 30% cap = $348 → premium
   ceiling **$1.16/contract at qty 3** — expect RISK_CAP refusals on ATM quotes above that
   (the 07-30 deadlock shape), independent of any gate.
3. **key-levels.json freshness + flicker** — the 743.25 lesson: 14 appear/disappear flips
   Friday. WS3's hysteresis fix **landed Saturday** (`114a7a6b`, after this scrimmage's
   replay) — Monday is its first live session; watch that levels persist instead of blinking,
   and that the fix didn't over-freeze the feed (a level that never updates is the opposite
   failure).
4. **risky-1's first fills** — min-size 5, ATM-class strike, REACHABLE-TP1 exits. If it takes
   materially more than ~2–4 entries on a Friday-like tape, something beyond this scrimmage's
   model is loose — pull `fill_funnel` + this doc's episode table before reacting.
5. **Floor refusals in the ledger** (`premium X < 0.3`) — the expected refusal mode for
   safe-3 all day and for risky-3/risky-1 afternoons if OTM-2-tiered.
6. **Known broken going in:** `gex_archive` accrual gaps (07-24/07-30, RED non-critical);
   Alpaca `/options/bars` 403 "OPRA agreement is not signed" — **needs J's dashboard click**,
   backfills run on the disclosed trade-print fallback until then.

**Kill switches (unchanged, per account, isolated):** Safe-2 −30%/day; Bold-2 −50%; fleet
arms −30%/−50% per circuit-breaker.json. All-flat 15:50 ET; EOD flatten 15:55.

---

*Scrimmage lane WS1. Runner + JSON artifact committed alongside this doc. Nothing armed;
the elite-bull flip and the reset-vs-full-send interaction are the two decisions this
preview hands to the conductor/J, stated plainly above.*
