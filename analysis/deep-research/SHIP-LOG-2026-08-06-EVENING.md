# SHIP-LOG — 2026-08-06 evening, Lane 1 FIX+SHIP (S1–S4)

> Clock verified at lane start: `2026-08-06 18:46:35 Thursday EDT / market_hours=False`
> (`setup/scripts/et_clock.py`). All commits via `commit_scoped.py`, pathspec-scoped.
> Suites quoted fresh after every ship: fleet suite (automation/state/fleet/) + curated
> safety gate (backtest/tests/run_safety_gate.py) + touched test files.

## Verdict line

**3 of 4 sanctioned items shipped clean; the 4th (S2 SAMEBAR) shipped DISARMED because its
own ship-gate replay disproved the measured benefit and met the prereg kill criterion on
day 0.** One collateral C14 miss (replay-harness table vocabulary) was caught and fixed in
the same session. The fleet replay harness's 6 pre-existing REDs are now on STATUS.md
`## Known broken` (they weren't anywhere before — the exact C7 gap KEEP-LOSSES flagged).

---

## S1 — test_fleet_sizing_miss_is_distinguishable_from_deadlock — commit `36acbbab`

**Root cause (one sentence):** the TEST was stale, not the code — commit `c2cb9f72`
(2026-08-03) deliberately shipped SHRINK-NOT-DENY (SIZING-SCALING-DECISION-2026-08-03.md:
wholesale-deny cost 96% of a controlled population's P&L at the $2K tier boundary), so a
sizing miss at an affordable premium now legitimately ALLOWs at `max_affordable_qty`, while
the wiring guard (last touched pre-ship in `9b25aa79`) still pinned the old DENY contract.

**Fix:** test updated to pin the NEW distinguishability shape — sizing miss → `ALLOW` at
shrunk qty (`3 <= qty < 30`) + `"shrink-not-deny"` note in reason + `binding=None`
(additive-only invariant); deadlock → `RISK_CAP` + `binding.deadlock=True` (unchanged).

- **RED-proof:** `_shrink_qty_to_affordable` mutated to return the original qty →
  `1 failed, 6 passed`; restored byte-identical (sha256 `2c04004b...`, `git diff` clean) →
  `7 passed`.
- **Suites:** fleet `368 passed` · safety gate `59 passed ... Safe to commit` · file 7/7.
- **Revert:** `git revert 36acbbab`.

---

## S2 — FLEET-SAME-BAR-COOLDOWN — prereg `55880b45` → wiring `7598c20d`, shipped **DISARMED**

**Ordering proof:** `git merge-base --is-ancestor 55880b45 7598c20d` → `PREREG-IS-ANCESTOR-OF-WIRING: PROVEN`.

**What was built (exact core-contract mirror):**
- `build_shared_signal.py`: `trigger_bar_et` threaded core-decisions → shared-signal
  (`_map_core_row` passthrough + sig emission; absent/None on beacon fallback → fail-open).
- `fleet_live.py`: consult in `_place_live` BEFORE any broker call (same key shape
  `(arm, setup) -> trigger_bar_et` string equality via `exit_actuator.same_bar_cooldown_active`,
  same try/except fail-open as heartbeat_core.py:2375) + stamp via `record_entry_bar` ONLY on
  `placed=True` (mirror of core's `_TAKEN` contract, heartbeat_core.py:2410) — both gated on
  one flag `FLEET_SAME_BAR_COOLDOWN`.
- Guards: `automation/state/fleet/test_fleet_same_bar_cooldown.py` (8 tests: vary-and-assert
  same-bar-blocked / new-bar-allowed / different-setup-allowed, fail-open ×2, no-stamp-on-
  refusal, flag-off byte-equivalence, default-disarmed pin) + the
  `test_vwap_cont_once_per_day_process_scope_2026_08_05.py` parity pin inverted per its own
  original instruction.

**The ship-gate replay FAILED — and that is the finding.** Method: every real placed fleet
entry (per-arm decisions.jsonl, `placement.placed=true`) joined to its OWN core tick via
`core_tick_id` → core-decisions `trigger_bar_et` (exactly the value the live consult reads),
walked through the exact production functions in time order:

| Day | Entries (risky arms) | Engine trigger bars | Blocked |
|---|---|---|---|
| Tue 08-04 | risky-3 09:46 / 09:50 / 09:54 / **09:57** / 10:35 | 09:35 / 09:40 / 09:45 / **09:45** / 10:25 | **09:57 only** |
| Wed 08-05 | both arms 09:58 / 10:06 / 10:10 / 10:14 / 10:18 | 09:50 / 09:55 / 10:00 / 10:05 / 10:10 | **none** |

- The blocked Tue 09:57 763C leg is **+$524.00 on real fills** (EOD-2026-08-04-ENGINE.md:464)
  — the exact "rescue" LEVER-ENTRY-COUNT §2d said the rule preserves.
- Wednesday blocks nothing — the measured +$202 does not exist under production bar identity.
- **Mechanism:** the study keyed entries to WALL-CLOCK last-closed 5m bars; the engine's
  `trigger_bar_et` (bar-cache append + trig_idx=n−2) lags tick-phase-dependently, so
  bar-EQUALITY relations — the entire content of a same-bar rule — do not transfer. L251
  sibling; lesson filed:
  `automation/overnight/_lesson-inbox/2026-08-06-samebar-wallclock-vs-engine-bar-identity.md`.
- Net on the motivating tape **−$524** → prereg kill criterion #1 (blocks a winner > +$150)
  met on day 0 → **DO-NOT-ARM**, recorded in
  `analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json`.

**Shipped state:** flag default `False` (pinned by guard); mechanism + plumbing land so a
forward re-measure keyed to the REAL bar identity is possible. Note the mechanism still
correctly guards the true sub-bar churn shape (core's own 07-20 exhibit); the only two-day
fleet evidence says blocking that shape costs money (the one blocked leg was the winner).

- **RED-proof:** consult short-circuited (`if False`) → `2 failed` (blocked-test + inverted
  parity pin), restored byte-identical (sha256 `31e0c692...`) → `10 passed`.
- **Suites:** fleet `378 passed` · safety gate `59 passed` · touched files `20 passed`.
- **Revert (of the disarmed code):** `git revert 7598c20d`. **Arm:** flip flag True — only
  after a re-measure clears the prereg gates.

---

## S3 — ATM-TIER-EXTENSION per-arm kill on risky-3 — commits `3ac1d7b2` + `f3a30ad8`

**Mandate:** the extension's own frozen kill bar
(`atm-tier-extension-2k10k-prereg-2026-08-03.json`: n≥10 fills/arm, net<0 → revert) is MET
by risky-3 (n=14 fills, **−$653**) and NOT by risky-1 (n=11, **+$903**).

**Mechanism (why not the prereg's own one-line revert):** that revert edits shared
`V15_BOLD_CORE_TIERS` row 2 in place — consumers are core bold-2 (heartbeat), j_intent bold,
risky-1, safe-3, i.e. it would execute the kill on every arm that did NOT meet the bar. The
per-arm kill instead ships `V15_BOLD_CORE_PRE_EXT_TIERS` (bold_core exactly as it stood
2026-07-18→08-04) + `_tiers_for_arm` branch `"bold_core_pre_ext"` + risky-3
`accounts.json params_patch.strike_tier_table = "bold_core_pre_ext"`.

**Quoted resolutions at $5,000 equity (run fresh, before/after):**

| Arm | BEFORE | AFTER |
|---|---|---|
| risky-1 | ATM offset 0, strike(C,748)=748 | ATM offset 0, strike(C,748)=748 (unchanged) |
| risky-3 | ATM offset 0, strike(C,748)=748 | **OTM-2 offset −2, strike(C,748)=750** |

risky-3's $0–2K band stays ATM (the 2026-08-01 extension is not part of this kill).

- **Guards:** `test_atm_tier_extension_risky3_kill_2026_08_06.py` 6/6 (incl. C14
  vary-and-assert: same arm dict with patch flipped back resolves ATM again; shared-table-
  untouched pin) + updated pins in `test_fleet_strike_tier_floor_collision_2026_07_31.py`
  and `test_bold_core_strike_tier_2026_07_15.py`.
- **RED-proof:** accounts.json mutated back to `bold_core` → `1 failed`; restored
  byte-identical (sha256 `4f14e77d...`) → `6 passed`.
- **Collateral C14 miss, caught same-session:** `backtest/tools/fleet_arm_replay.py` keeps
  its own `_NAMED_TABLES` vocabulary → 2 replay tests died on
  `ValueError: unknown strike tier table name 'bold_core_pre_ext'`. Fixed in `f3a30ad8`
  (table registered + the atm-coverage heuristic test updated: risky-3 at $2.5K correctly
  flips BACK to anchor-covered since pre_ext == its fill history; the ATM-divergence exhibit
  moved to risky-1). `2 passed` after fix.
- **Suites:** fleet `378 passed` · safety gate `59 passed`.
- **Un-kill (one line):** risky-3 `strike_tier_table` back to `"bold_core"`.

---

## S4 — ghost workflow `wf_6db746c8-a74` — verified already dead, transcripts preserved

- Location: `~/.claude/projects/C--Users-jackw-Desktop-42/21375492-.../subagents/workflows/wf_6db746c8-a74/`
  (19 agent transcripts; 5 non-terminal: `a9a3ebe… a9f4aad… aac80c9… af34900… af41947…`).
- `TaskStop` attempted on all 5 non-terminal agent ids → `No task found` every one.
- Full `Win32_Process` scan: ZERO surviving processes from the run's spawn windows
  (01:39–02:50 and 09:31–10:41 local); the only claude-code CLI process is this lane's own.
- The "4 agents, idle 391.9m" liveness report is a transcript-mtime inference (last write
  12:41 ET; 19:13 − 12:41 = 392m exactly) — file-presence, not process-liveness.
- Nothing killed because nothing was alive; **no transcript deleted**.

---

## Commit ledger (this lane)

| # | Commit | What |
|---|---|---|
| 1 | `36acbbab` | S1 test un-staled (shrink-not-deny contract) |
| 2 | `55880b45` | S2 frozen prereg (BEFORE wiring, ancestry proven) |
| 3 | `7598c20d` | S2 wiring + guards + OUTCOME (DISARMED) + lesson |
| 4 | `3ac1d7b2` | S3 risky-3 per-arm kill (table + branch + patch + guards) |
| 5 | `f3a30ad8` | S3 collateral: replay-harness table vocabulary + test |
| 6 | (this file + STATUS.md) | ship log + REVOKE surface + Known broken |

## Open items handed off (NOT handled by this lane)

1. **6 pre-existing fleet-replay REDs** (3× test_replay_fleet_arms + 3× anchor_pass_rate)
   — now logged in STATUS.md `## Known broken`; unowned; risky-3 produced 75% of Wednesday.
2. **SAMEBAR forward re-measure** — the only path to arming the disarmed cooldown: re-run
   the LEVER-ENTRY-COUNT counterfactual keyed to `trigger_bar_et` (the plumbing shipped
   tonight makes the forward ledger carry it), then judge against the frozen prereg gates.
3. **D1–D9 defects** — harness lane's scope, untouched here.
