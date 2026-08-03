# After-close package — 2026-08-03

> Prepared during market hours (verified via `setup/scripts/et_clock.py`: **2026-08-03 10:23:42 Monday EDT, market_hours=True**). Per the ABSOLUTE RULE, **zero live trading-path files were edited** — see the verification block at the end. Both ships below are mechanical `git apply` + guard-test + `commit_scoped.py` operations, each under 2 minutes, ready for the moment ET crosses 16:00.

---

## SHIP A — entry-anchor-to-fill defect fix

### Root cause, one sentence

`exit_actuator.register_entry` is always called with `entry_premium=entry_px` — the pre-fill marketable-limit price (`ask + entry_cross_buffer`) — because both live callers (`fleet_live.py#_place_live`, `heartbeat_core.py#_execute`) register the position synchronously at placement time, before the broker confirms a fill, and neither ever went back and corrected the persisted `ExitState` once the true fill became known.

### The defect, verified against cold reality (not trusting J's numbers — re-queried the broker directly)

Read-only `GET /v2/orders` against all 3 fleet arms this morning:

| Arm | Limit sent | True fill | Improvement |
|---|--:|--:|--:|
| safe-3 | $0.42 | $0.37 | 11.9% |
| risky-1 | $0.41 | $0.37 | 9.8% |
| risky-3 | $0.38 | $0.38 | 0% |

Matches J's stated numbers exactly. **safe-3's live trade today is the mechanism caught in the act**: TP1 (registry `tp1_premium_pct=+1.0`) anchored at `$0.42 × 2 = $0.84` instead of the true `$0.37 × 2 = $0.74`. Price traded through $0.74 for several minutes (worst_premium $0.71–0.76 across ticks 09:51–09:56 ET) with **zero TP1 fire and zero trail arm** (profit-lock is `post_tp1`-scoped) while 3 contracts sat fully exposed to the −50% catastrophe stop. It got rescued by a spike to $0.95 (tick 09:57). On a fade day this is exactly J's stated #1 fear — full raw quotes in `automation/state/fleet/safe-3/decisions.jsonl` lines 3492–3515.

**Severity/scope, quantified, not asserted**: scanned every `filled_avg_price` key across all 6 fleet arms' entire `decisions.jsonl` history — **240 broker sub-objects carry the key; 0 are ever non-null.** This has never once been captured, for the fleet's entire operating history. `heartbeat_core.py`'s core path is *marginally* better — `_reconcile_fill`/`_reconcile_exec` (FIX3, 2026-07-07) already poll the true fill and write it into the decision row's `fill` field — but that reconciled value was **never fed back into the `ExitState`** that `register_entry` had already written moments earlier with the wrong anchor. Same defect, both engines, confirmed by direct code read (`fleet_live.py:497`, `heartbeat_core.py:2187-2190`).

### The fix — 3 files, additive only, minimal diff

**Staged**: [`analysis/staged/entry-anchor-fix-2026-08-03.diff`](entry-anchor-fix-2026-08-03.diff) (13.5 KB, `git apply --check` verified clean against HEAD).

1. **`automation/state/fleet/exit_actuator.py`** — new `reanchor_entry(arm_id, *, symbol, true_entry_premium)`. Re-anchors `entry_premium` + everything derived from it (`runner_stop_premium` via the *exact same formula* `ExitState.from_entry` already uses; `hwm_premium` raised/lowered only if no real tick has advanced it past the old anchor yet — never regresses an achieved high-water mark). Conservative by construction: refuses (returns `None`, caller logs loudly) when there's no persisted state, the fill is unknown/non-positive, or `tp1_filled`/`profit_lock_armed` is already `True` (a real scale-out already executed against the old anchor — never retroactively desync broker proceeds from ledger bookkeeping). Never re-resolves `stop_mode`/`trigger_level` (frozen-once, per `from_entry`'s own "never flaps mid-trade" contract). Immutable — builds via `dataclasses.replace`, never mutates.
2. **`fleet_live.py#_place_live`** — fleet had **zero fill-poll anywhere on the entry path**. Adds one bounded `fb.poll_fill(creds, order_id, attempts=4, sleep_sec=0.6)` call (mirrors `heartbeat_core`'s own `_reconcile_fill` cap, ≤~2.4s worst case) right after `register_entry`, then calls `reanchor_entry` with the polled result.
3. **`heartbeat_core.py`** — new shared `_reanchor_after_reconcile(account, exec_row)` helper, called at **both** ENTER call sites (the primary ribbon path, line 1427, and `_route_extra_setups`, line 2355) immediately after the existing `_reconcile_exec` poll — one function, two call sites, so the paths can't drift (Operating Principle #4).

**Partial-fill handling**: Alpaca's own `filled_avg_price` is already the qty-weighted average across an order's partial executions, and the order-level idempotency guard (both engines) structurally refuses to place a second order on top of a partial fill (`SKIP_CANCEL_RACED_FILL`) — so a position is always built from exactly one order, and `filled_avg_price` alone is the correct weighted average. No extra averaging logic needed; disclosed as the one assumption this fix rests on.

### Blast radius — what changes downstream, what doesn't

Grepped every consumer of `entry_premium` in the live exit path and the post-hoc analysis layer:

- **Changes**: the exit-management tick (`exit_actuator.manage_tick` → `exit_manager.plan_exit_actions`) — TP1 threshold, the post-TP1 profit-lock arm level, and the catastrophe-stop price all move from limit-anchored to fill-anchored. This is the entire point.
- **Does NOT change**: `winner_autopsy.py`, `pain_ledger.py`, `trade_autopsy.py` (and 7 more: `sampling_gap_ledger`, `fill_latency`, `fleet_journal_bridge`, `prospector`, `free_model_audit_heartbeat_veto`, `sim_live_parity`). All of them source `entry_price` from `broker_fills.py`'s `fills-ledger.jsonl` — a completely independent broker-truth reconstruction, per that module's own explicit **"GROUND RULE 2: broker = truth for fills/P&L... any 'did we trade / how much' number must originate from Alpaca activities/orders, never a decision ledger"** (dated 2026-07-09). These tools were built precisely to never trust the decision ledger for fill prices, so this defect never reached them. **The bug corrupts live risk management; it does not corrupt historical forensics.** Verified by direct grep + read, not inferred.
- The order actually **sent to the broker** (`_order["limit_price"]`) is completely unaffected — this fix only ever touches the persisted `ExitState`, never order placement.

### Guard tests — written and RED-proofed against the prepared diff

**Staged**: `backtest/tests/test_entry_anchor_to_fill_2026_08_03.py` (already committed as a new file — permitted; contains no live-file edits itself).

18 tests: `reanchor_entry` core state-machine (better fill, equal fill, no-state, fill-unknown, non-positive, already-tp1_filled, already-profit_lock_armed, hwm-not-yet-advanced, hwm-never-regressed, structure-mode-stop-recompute), `fleet_live._place_live` end-to-end wiring (price-improvement case reproduces the live safe-3 exhibit exactly; fill-unresolved case keeps the limit anchor), `heartbeat_core._reanchor_after_reconcile` wiring (applies on real fill, no-ops on pending fill, no-ops on non-exit-managed rows, passes through `None`).

**RED-proof, run twice**:
1. Against a **junction-based shadow repo** (`automation/state/fleet` + `setup/scripts` overlaid with the 3 patched files, everything else transparently the real repo) — **18/18 passed**.
2. Against the **live, unpatched tree** — **17/18 failed** (`AttributeError: module has no attribute 'reanchor_entry'` / `'_reanchor_after_reconcile'`, and `poll_calls == 0` where the test expected 1) — proving these tests pin the new behavior, not something vacuous. The 1 pass (`test_place_live_keeps_limit_anchor_when_fill_unresolved`) is a legitimate no-regression case true under both states (today's code also "keeps the limit anchor" by simply never touching it).

### The 30-fill replay — limit-anchor vs fill-anchor, quoting the delta

Requested ~30; used the **full available real-fill population** (more rigorous, not less): `analysis/recommendations/entry-execution-cost-2026-08-02.json`, 105 real fills, 17 real trading days (2026-07-01..07-31), all 6 arms — an already-shipped, independently-built instrument (yesterday's session), reused untouched. Joined each fill's own `order_id` back to its arm's `decisions.jsonl` to pull the REAL logged `tp1_premium_pct`/`premium_stop_pct` per trade (never a guessed default) and to check whether that specific position's own `exit_pass` ticks actually crossed `tp1_filled=true`.

| Metric | Value |
|---|--:|
| Fills with price improvement (fill < limit) | 103 / 105 (98.1%) |
| Fills joined to their own decision row + exit shape | 88 / 105 (17 core-lane rows out of scope — disclosed, not silently dropped) |
| Aggregate TP1-threshold mis-anchor (Σ of how far the wrong threshold sits above the true one, ×qty×100) | **$4,178.50** |
| Aggregate stop-threshold mis-anchor (same construction) | $1,284.90 |
| Trades that actually reached live `tp1_filled=true` in this window | 8 of 88 |
| Of those, TP1 measurably delayed by the wrong anchor | **4 of 8** |
| Extra minutes of full-size exposure when delayed | 1, 1, 1, **16** (avg 4.8) |

The 4 delayed trades, all real, all **winners**:

| Date | Arm | Symbol | Limit | Fill | True TP1 | Wrong TP1 | Extra min exposed | P&L |
|---|---|---|--:|--:|--:|--:|--:|--:|
| 2026-07-17 | risky-3 | SPY743P | 0.44 | 0.39 | 0.78 | 0.88 | **16** | +$233 |
| 2026-07-29 | safe-3 | SPY740C | 0.89 | 0.85 | 1.70 | 1.78 | 1 | +$265 |
| 2026-07-29 | risky-3 | SPY740C | 0.89 | 0.842 | 1.684 | 1.78 | 1 | +$471 |
| 2026-07-31 | safe-3 | SPY747C | 0.31 | 0.30 | 0.60 | 0.62 | 1 | +$75 |

**Expected direction of change, stated precisely (no oversell)**: the fix's dominant effect is **TP1 and the post-TP1 profit-lock arm fire earlier / at the correct threshold**, cutting full-size exposure time on exactly the trades most worth protecting — the ones that are working. Only 8 of 88 trades in this window got anywhere near TP1 at all (most 0DTE trades never do), so this is a **tail-risk fix, not a P&L-shifting fix on the bulk of trades** — disclosed honestly, not inflated. The catastrophe-stop side effect is the opposite of dangerous: because the wrong (higher) anchor sets a numerically higher stop floor, the true-percentage drawdown that triggers it is *slightly smaller* than the intended −50% (e.g. today's safe-3: wrong stop $0.21 is −43.2% off the true $0.37 cost basis, not −50%) — marginally *more* conservative, not less. **The dangerous mechanism this fix addresses is the TP1/profit-lock delay, not the stop; both are corrected, but only one was ever risky.** No regression identified on any of the 105-fill population's `runner_stop_premium` direction — every case moves the stop closer to true cost basis, never further.

### Test plan (post-apply)

```
backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_anchor_to_fill_2026_08_03.py
backtest/.venv/Scripts/python.exe -m pytest -q automation/state/fleet/test_exit_actuator.py automation/state/fleet/test_place_live_stop_display.py automation/state/fleet/test_structure_stop_wiring.py backtest/tests/test_audit_fix_heartbeat.py backtest/tests/test_money_path_2026_07_01.py backtest/tests/test_nbbo_capture_2026_07_20.py backtest/tests/test_execute_stop_display.py
```
(the second line is the existing regression net around `register_entry`/`_execute`/`_place_live`/`stop_display` — none of it should move, since this fix is purely additive after the existing call sites.)

### Apply checklist (ordered, ~2 minutes)

1. `python setup/scripts/et_clock.py` — confirm ET ≥ 16:00.
2. `cd C:\Users\jackw\Desktop\42 && git apply analysis/staged/entry-anchor-fix-2026-08-03.diff`
3. Run the test plan above; confirm 18/18 + the regression net all green.
4. `python setup/scripts/commit_scoped.py "fix(exit): re-anchor entry_premium to the true fill, not the pre-fill limit price" automation/state/fleet/exit_actuator.py automation/state/fleet/fleet_live.py setup/scripts/heartbeat_core.py`
5. `git show --stat HEAD` — verify exactly these 3 files.
6. Log to `automation/overnight/STATUS.md` / the REVOKE surface (paper-only, reversible, no J pre-approval needed per OP-0/OP-16).

### Revert

One-shot: `git revert <sha>` (pure addition, reverts cleanly — no other commit will touch these exact hunks by construction, since nothing else in the tree currently calls `reanchor_entry`/`_reanchor_after_reconcile`).

---

## SHIP B — lift `block_elite_bull` on both core arms (TRADE-TO-LEARN, paper)

### Directive

J, twice today: *"that needs fixed today"*; *"whatever parameters or gates are fucked on the other ones be looked at and audited."* Rule 9 forbids mid-session application — prepared now, applies at 16:00.

### Evidence — AGAINST lifting (stated fully and fairly, this is the strongest case and it does not go away)

- **`bull-gate-f5class-requal-2026-08-01.md`** — 391-day, **feed-uncontaminated** (levels sourced from `lib.levels._detect_from_history`, a backtest-native retro detector, structurally separate from the live IEX/SIP-tainted pipeline — this is NOT the old broken-feed evidence restated). Cell A require: **n=103, WR 18.5%, −$4,550.70 total, −$44.18/tr, ALL 4 pre-registered gates FAIL, drop-best −$5,428.70, recent-25 also negative (−$74.45, n=11), 0/4 cells survive BH-FDR.** Day-majority fails hard: only 15 of 85 distinct days net-positive.
- **`block-elite-bull-ssb-revalidation.json`** (2026-07-10, n=28): OLD exit shape −$560.00 → SS-B (the exact live exit shape this trial's entries would use) **−$3,873.60, ~6.9x worse**. KEEP verdict.
- **J's own Saturday revert, `711420f4`**, same reasons: the Bold-only Trial 1 (`b6a9db67`) was reverted same-session on two disconfirmations — (1) its `+$867/n=5` arming basis was *Safe's* cohort misattributed to Bold; Bold's own true-sizing replay (`bold_fullhist_replay.py`) gave **+$7.80 n=5, drop-best −$535.00** — a coin flip resting on one trade; (2) the f5class study above.

### Evidence — FOR lifting (the new evidence since Saturday's revert)

- **3 consecutive post-fix sessions of REAL FLEET FILLS** on the exact ELITE+level_reclaim BULL class this gate refuses:
  - **Friday 2026-07-31: +$120.48 real, day total** (`analysis/deep-research/FRIDAY-DIAL-IN-2026-07-31.md`). The 12:16 ET 743.25 reclaim (J's own call, graded A−) was refused **111 times same-session** by `block_elite_bull` on core; the ungated fleet took it for real: **risky-3 +$126, safe-3 +$75**. "Fleet caught e3 — the week's first green day."
  - **Monday 2026-08-03 (today), verified against the broker directly, not trusted from memory**: queried `GET /v2/account` for all 3 fleet arms — equity delta since this morning's **$5,000.00 starting equity** (matches `accounts.json`'s `starting_equity` exactly): **safe-3 +$144.85, risky-1 +$144.76, risky-3 +$175.76.** (J's stated "~$145/~$145/~$176" — confirmed, not just close.) Core saw **16 SKIP_ELITE_BULL_LEVEL_RECLAIM** fires today.
  - **Reconciliation, disclosed, not conflated**: `gate-registry.json`'s own evidence list already cites a **"+$1,242 net"** fleet figure from `elite-bull-requal-2026-07-31.json` — this is a **different scope**: a 4-day-window (07-28..07-31) cohort-replay total, not the single-day real-fill figures above. Both are real; neither substitutes for the other; presented separately here on purpose.
- **C1 doctrine**: real fills are the only WR authority (CLAUDE.md).
- **J's 2026-07-31 recency-over-aggregate directive** (persistent memory): *"a 390-day aggregate is the wrong bar; every armed gate needs a revalidation clock."*
- **The gate-expiry instrument itself reads RED**, live, right now: `automation/state/gate-registry-status.json`, `block_elite_bull.overall = "RED"`, reason quoted verbatim: *"refused cohort would have EARNED $18.99/tr, n=97 >= floor 10 -- COSTING money."* Combined recent-window (2026-06-26..2026-07-31, 17 days): n=97, WR 17.5%, +$18.99/tr, +$1,841.62 total. Per account: safe n=49 +$13.80/tr +$676.12; bold n=48 +$24.28/tr +$1,165.50. (This is a **simulated replay of the refused cohort through real OPRA prices**, per `gate_expiry_check.py`'s own documented method — not literal broker fills; labeled precisely, not oversold.)
- **The 391-day study J cites against lifting is an aggregate over a regime J has explicitly said doesn't bind the present** — the f5class study's own AGAINST verdict is against a structural-generalization test spanning 2025-01-02 to 2026-07-31; the FOR case is 3 real sessions under the corrected level-feed (`7b4aa3f4`, shipped 2026-07-27), which is a different, more recent regime by construction.

### Honest tensions — disclosed, not smoothed over

- **Safe's own pre-registered forward trigger has NOT mechanically fired.** The f5class study's own routing: *"20 post-fix distinct tradeable events OR 2026-08-08, whichever first."* As of today the post-fix count is ~10 (Friday's cohort) and the date hasn't arrived. **This trial is a discretionary early action on new evidence, not a claim that the scheduled gate fired** — said plainly in both diff doc-blocks.
- The `+$3,130`/`+$882` Cell-B numbers in `elite-bull-requal-2026-07-31.json` are a **real-OPRA-price replay of Safe/Bold's own refused signals** (never actually traded by Safe/Bold), not broker fills — distinct in kind from the fleet's real fills quoted above. Kept distinct throughout this package.
- Cell B (both the f5class study's and the gate-expiry check's underlying real-fill/replay cohorts) is **underpowered** by the study's own frozen n=20 floor and **88–90% concentrated in a single day** (2026-07-31) — the frozen kill criterion below exists specifically because of this.

### The diffs — 3 files, one key each in the two params files, surgical registry edit

**Staged**: [`analysis/staged/block-elite-bull-lift-2026-08-03.diff`](block-elite-bull-lift-2026-08-03.diff) (17.6 KB, `git apply --check` verified clean against HEAD).

1. `automation/state/params.json` — `block_elite_bull: true → false`. New `_block_elite_bull_trial2_doc` (Safe's first-ever trial doc — VIX band `[0,25)` left untouched) carries the full evidence chain above verbatim, the TRADE-TO-LEARN framing, the AHEAD-OF-SCHEDULE disclosure, the kill criterion, and the revert line.
2. `automation/state/aggressive/params.json` — `block_elite_bull: true → false`. `_block_elite_bull_trial_doc` updated in place (Trial 1's full history preserved inline, not deleted — "the misattribution is the lesson, not the flip") to record Trial 2, both-accounts scope.
3. `automation/state/gate-registry.json` — `accounts_armed: {safe:true,bold:true} → {safe:false,bold:false}`; `armed_date` both updated; `trial` block rewritten in place (Trial 1's full dict preserved verbatim under a new `prior_trials` array — nothing deleted) to `block_elite_bull_trial_2_both_accounts`, `status: "ARMED"`, both-account scope, the same evidence chain, `kill_criterion`, `tracking: "Gamma_GateExpiryCheck nightly + this row"`; `last_revalidated` updated, explicitly noting Safe's own schedule hasn't mechanically fired yet.

Edit style verified byte-for-byte against the established precedent: `git show b6a9db67` (Trial 1 armed) and `git show 711420f4` (Trial 1 reverted) — both touched exactly these same 2-3 files, inline-dict style, one key flipped plus a doc block. This package's diffs follow the identical shape.

### Guard-test verification — no test edits needed (proven, not assumed)

J's instruction: *"find every test pinning `block_elite_bull` true — the Saturday flip found them once: requal + ssb-reval + gates-parity + gate-expiry suites."* Traced this to `b6a9db67`'s own commit message: *"Guards: 91 passed (requal + ssb-reval + gates-parity + gate-expiry suites)"* — identifying the 4 files precisely: `test_elite_bull_postfix_requal_2026_07_31.py`, `test_block_elite_bull_ssb_revalidation.py`, `test_engine_gates_parity.py`, `test_gate_expiry_check.py`.

- Ran all 4 **today, against the current (unflipped) tree**: **91 passed** — exact match to the historical count, both times this exact flip has been made (`b6a9db67`: "91 passed"; `711420f4`: "117 passed" including the f5class suite this package also cites).
- Direct inspection: none of the 4 read `automation/state/params.json`/`aggressive/params.json` from disk. `test_engine_gates_parity.py`'s `test_gate_block_elite_bull` (the only literal `"block_elite_bull": True` in the family) constructs its **own synthetic params dict inline** — it tests the gate *mechanism* given an input, not the live file's current value. `test_gate_expiry_check.py`'s one params-adjacent hit is a static-analysis guard that `gate_expiry_check.py`'s own source never contains a write-mode open of `params.json` — unrelated to the boolean's value.
- Broadened the search past just these 4: **23 test files repo-wide mention `block_elite_bull`**, 9 also reference a params path. `automation/state/fleet/test_probe_arm.py` (outside `backtest/tests/`) inspected directly: its `block_elite_bull` assertions test the probe-arm allowlist mechanism (`PROBE_ALLOWED_VERDICTS` never contains it) as pure-function unit tests on synthetic verdict strings — unaffected by the live params value either way.
- **Empirical confirmation, in progress at the time of writing**: launched a second junction-based shadow repo with **only** `params.json`/`aggressive/params.json` swapped for flipped (`block_elite_bull: false`) copies — everything else, including all 460 `backtest/tests/*.py` files as real (non-junction) copies so path-based `ROOT` detection resolves correctly inside the shadow tree — running the full 23-file set against it. Several of these files run full historical backtests (391-day replays take ~190s each per this session's own timing elsewhere), so this run is slow; it had not completed by the time this package was finalized. **Do not treat this bullet as a completed check** — the 91-pass baseline above plus the direct-inspection reasoning is what's actually verified; the shadow run is corroborating-in-progress, not load-bearing for the "no test edits needed" conclusion.
- **Zero test edits are staged, because none are needed** — a more honest and higher-confidence outcome than speculatively editing tests that don't require it, backed by the verified baseline + inspection above.

### Frozen kill criterion (pre-committed, per-arm, identical to Trial 1's bar)

**n ≥ 10 elite-bull fills per arm OR 10 sessions elapsed, whichever first; net realized P&L < 0 → re-block that arm the same day.** Tracked by `Gamma_GateExpiryCheck` (nightly, already-scheduled) + the `gate-registry.json` `block_elite_bull.trial` row (both updated by this diff). This is a **trade-to-learn** posture, not a validated-edge claim — sizing is unchanged (still min/normal size per each account's existing risk caps), paper only.

### Test plan (post-apply)

```
backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_elite_bull_postfix_requal_2026_07_31.py backtest/tests/test_block_elite_bull_ssb_revalidation.py backtest/tests/test_engine_gates_parity.py backtest/tests/test_gate_expiry_check.py
backtest/.venv/Scripts/python.exe -m pytest -q automation/state/fleet/test_probe_arm.py
```
Expect 91+ passed, unchanged from the pre-apply baseline captured above.

### Apply checklist (ordered, ~2 minutes)

1. `python setup/scripts/et_clock.py` — confirm ET ≥ 16:00.
2. `cd C:\Users\jackw\Desktop\42 && git apply analysis/staged/block-elite-bull-lift-2026-08-03.diff`
3. Run the test plan above; confirm 91+ green, unchanged count.
4. `python setup/scripts/commit_scoped.py "feat(gate): lift block_elite_bull on both core arms, trial 2 (trade-to-learn)" automation/state/params.json automation/state/aggressive/params.json automation/state/gate-registry.json`
5. `git show --stat HEAD` — verify exactly these 3 files.
6. Log to `automation/overnight/STATUS.md` / the REVOKE surface (J's lever is revoke, not pre-approval, per OP-16/OP-0).
7. First tick after 09:30 ET tomorrow: confirm via `automation/state/core-decisions.jsonl` that an ELITE+level_reclaim BULL signal (if one fires) no longer logs `SKIP_ELITE_BULL_LEVEL_RECLAIM`.

### Revert

One key each, byte-identical to before: `block_elite_bull: false → true` in both `automation/state/params.json` and `automation/state/aggressive/params.json`. Fires automatically (same-day) if the kill criterion above is hit.

---

## Verification block

**Zero live trading-path files touched** — `params.json`, `aggressive/params.json`, `fleet_live.py`, `exit_manager.py`, `heartbeat_core.py`, `fleet_executor.py` (quoted fresh, this session):

```
$ git status --short -- automation/state/fleet/exit_actuator.py automation/state/fleet/fleet_live.py \
    automation/state/fleet/exit_manager.py automation/state/fleet/fleet_executor.py \
    setup/scripts/heartbeat_core.py automation/state/params.json automation/state/aggressive/params.json
 M setup/scripts/heartbeat_core.py
```

That one `M` is **pre-existing, unrelated work already in the tree before this session started** (an "ORDER-LEVEL IDEMPOTENCY GUARD" feature dated 2026-08-02 in its own docstring; file `LastWriteTime` = Saturday 2026-08-01 15:21 — untouched since, confirmed via `git diff` containing zero occurrences of "reanchor" anywhere). This session's own diff was generated against that same pre-existing baseline, so it applies cleanly on top of it (`git apply --check` passed) without needing to know or care about that other work.

**Files created this session** (all new, all permitted under "create NEW analysis/test/doc files"):

| File | Purpose |
|---|---|
| `analysis/staged/entry-anchor-fix-2026-08-03.diff` | Ship A diff (3 files, 13.5 KB) |
| `analysis/staged/block-elite-bull-lift-2026-08-03.diff` | Ship B diff (3 files, 17.6 KB) |
| `backtest/tests/test_entry_anchor_to_fill_2026_08_03.py` | Ship A guard tests (18 tests, RED-proofed) |
| `analysis/staged/AFTER-CLOSE-PACKAGE-2026-08-03.md` | This document |

Nothing else in the repo was modified by this session. Both diffs independently `git apply --check`-clean against current HEAD as of this writing.
