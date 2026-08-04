# PIPELINE CHAIN MAP — 2026-08-03 (the if-this-then-that walk)

> **J's failure shape, verbatim:** *"we didn't account for those three things to happen, so the
> fourth thing couldn't happen, and we didn't trade — that's not gonna fly."*
>
> This document walks the COMPLETE dependency chain for all 5 SPY arms, link by link, with each
> link's (a) preconditions, (b) failure behavior **verified from code this session** (file:line
> cited), (c) staleness/retry, (d) the multi-link CONJUNCTIONS that have historically killed
> trades. It ends with the single-point-of-failure map and what was CLOSED tonight vs what
> stays OPEN. Written 2026-08-04 00:12–02:00 ET (market closed, `et_clock` verified).
> Everything below was read from HEAD this session — nothing recalled from memory.

**Tonight's ships (this lane):** ① L246 ordering fix — the full-send floor-rescue
(`5fa89536`, 17 guard tests, RED-proofed, fleet suite 365/365). ② Content alarms in both
liveness watchers (`9fd87d85`, 15 guard tests + organic proof: today's real 33/35/35
FLOOR_WALL now alarms). Details in §5.

---

## 1. The two pipelines

- **CORE (`mcp_heartbeat`): safe-2, bold-2** — `Gamma_HeartbeatCore` → `setup/scripts/heartbeat_core.py`,
  1/min RTH. One process, two accounts (`ACCOUNTS` dict :126). Places its own orders
  (`CORE_PLACES_ORDERS` default 1).
- **FLEET (`fleet_rest`): safe-3, risky-1, risky-3** — `automation/state/fleet/fleet_live.py`
  consuming `shared-signal.json`, which `build_shared_signal.py` derives from the CORE's own
  `core-decisions.jsonl` rows. **The fleet has no independent perception: every fleet link
  chains BEHIND the entire core chain.** One brain, five wallets.

---

## 2. CORE chain — link by link (`heartbeat_core.py`)

| # | Link | Preconditions | Failure behavior (verified) | Staleness/retry | Ledger visibility | Alarm |
|---|------|---------------|------------------------------|-----------------|-------------------|-------|
| C1 | RTH gate + params read | weekday 09:30–16:00 (`_is_rth` :162); `params.json` parseable | `main()` catches ANY `run_account` exception → **verdict=ERROR row logged** (:2432-2444); tick marker withheld | none — next minute retries | ERROR row | ERROR rows carry no `armed:true` → a crash-day reads 0 armed ticks → `engine_liveness` DID_NOT_RUN/PARTIAL fires ✅ |
| C2 | SPY 5m bars — `_fetch_spy_5m` :279 | `.mcp.json` creds; Alpaca data REST up; **feed=iex** | uncaught exception → C1's ERROR row; empty bars → empty df | 15s timeout, no retry within tick | ERROR or SKIP_NO_DATA | **CLOSED TONIGHT**: SKIP_NO_DATA dominance >30% → `FEED_DEAD_INSIDE_RUNNING_ENGINE` content alarm |
| C3 | Payload build — `_build_payload` :562 | ≥80 RTH bars; ribbon seeds; trigger bar = n−2 | `None` → **SKIP_NO_DATA** row (:1148) | trigger bar is 5–10 min old BY DESIGN (backtest parity) | SKIP_NO_DATA | same as C2 ✅ |
| C4 | VIX — `_fetch_vix` :326 | yfinance reachable | **fallback `(0.0, 0.0)` — SILENT WRONG-BEHAVIOR**: vix=0 makes the bear VIX-floor (17.3) unreachable AND passes the bull VIX-cap (<17.2). Not a no-trade failure — a *changed-gates* failure | 10s timeout, no retry | `vix: 0.0` on rows (only if you knew to look) | **CLOSED TONIGHT**: vix_zero dominance >30% → `VIX_FEED_DEAD` content alarm. Behavior itself unchanged (see §6-O5) |
| C5 | Levels — `_read_levels` :412 ← `key-levels.json` (Gamma_Premarket 08:30 + intraday refresh + WS3 hysteresis) | file readable, levels unexpired (`_level_expired` fail-open keeps :393), within ±12 of spot | unreadable → `([], [])` → blind | today-dated expiry check; **known 15-min latency exhibit: 749.33 entered levels_active 09:44:03** (EOD §4.3, measure-first queued) | `blind:true` + `levels_active` on EVERY row (2026-07-30) | blind-block (`SKIP_NO_LEVELS` + `logger.critical` :1382) already ships; **CLOSED TONIGHT**: blind dominance >30% now also a day-level content alarm |
| C6 | Verdict — `_engine_verdict` :687 → `engine_cli` subprocess (score + filters 1–11 + 15 gates + structure veto) | subprocess succeeds in 30s | fail → **SKIP_BAD_INPUT** (fail-closed, named) | 30s timeout | SKIP_BAD_INPUT + why-not provenance (blockers/raw triggers, 2026-07-27) | counted with C2's alarm ✅ |
| C7 | Score ladder — `_apply_score_ladder` :1091 | arm's `score_ladder_floor` set | **config truth: NO arm carries the key today → lane INERT** (verified accounts/params this session) | n/a | `entry_lane: score_ladder` when fired | n/a (dormant by config) |
| C8 | Decision ladder order :1332-1440 | — | stale-trigger FIRST (always wins the label), then blind-block, ceiling (15:00), floor (09:35), sight-staleness ($1.00 divergence, fail-open :245), free-model veto | sight check = live trade quote, fail-open None | named SKIP_* rows each | routine; VETOED_BY_MODELS audited by free-model harness |
| C9 | `_execute` :1861 — creds/equity/PDT/settlement/kill | secrets.json; broker account GET; pdt_tracker; settlement ledger | NO_CREDS / **EQUITY_FETCH_FAIL** (fail-closed per attempt) | no retry within tick | named statuses | **CLOSED TONIGHT**: ≥3 infra-fail exec statuses/day → `BROKER_INFRA_FAILURES` alarm |
| C10 | Flat check `fb.is_flat_spy_options` (_execute :1943) | positions GET | **FAIL-OPEN: `get_positions` returns `[]` on error (`fleet_broker.py:78-79`) → reads FLAT during a positions-endpoint outage** | none | invisible when wrong | **OPEN — O1 in §6** (narrow Rule-4 hole; orders-side half was closed 2026-08-02, positions-side was not) |
| C11 | Tier/strike (`strike_selection`) + premium (ask+buffer) | quote exists | no quote → **NO_PREMIUM** (fail-closed) | none | named | in C9's infra alarm ✅ |
| C12 | min_entry_premium floor ($0.30) | premium ≥ floor | **SKIP_MIN_PREMIUM_FLOOR** (fail-closed; masks NOT_FLAT/kill since floor runs before `check_order`) | none | named | fleet-side wall now alarmed (§3 F7); core floor-hits are rare (ATM tier) |
| C13 | risk_gate.check_order (Rule 5/6/7, settlement mode) | all inputs readable | **fail-closed UNREADABLE_INPUT on ANY missing/NaN input** (`risk_gate.py:272-338`) | none | RISK_DENY_* | routine (by design) |
| C14 | Idempotency claim + broker open-orders (:1820-1860, 2026-08-02) | claim TTL 180s; orders GET | claim/query layers **fail CLOSED for placement** (SKIP_DUPLICATE_CLAIM / SKIP_ORDER_QUERY_ERROR / cancel-raced-fill refusals) | TTL 180s | named | in C9's infra alarm ✅ |
| C15 | Placement → fill poll → **reanchor (SHIP A)** — `_reconcile_fill` :1529, `_reanchor_after_reconcile` :1604 | order accepted; fill polls ≤4 | PLACE_FAIL fail-closed; fill unknown → keeps limit anchor + logs (never guesses) | poll ≤4×0.6s | exec row + broker sub-object | PLACE_FAIL in infra alarm ✅; SHIP A behavior = watch first fills Tuesday |
| C16 | Exit registration + per-tick management (`CORE_MANAGES_EXITS=1` via run-heartbeat-core.ps1) | registration succeeds | registration failure never aborts an accepted entry (logged); manage pass errors logged in `exit_pass` | every tick | exit_pass rows | live_watch (WS7) recons positions↔exit-state ✅ |
| C17 | Extra-setups lane (`_route_extra_setups` :2330) — the ONLY other order path | non-ENTER primary verdict; not structure-veto; not blind | fires under `extra_exec` key — **3 counters were blind to it** (EOD §6) | cooldown per setup | `extra_exec` (nested — the visibility bug) | **OPEN — owned elsewhere** (task_8be87fea + ws1/participation/self-check, EOD queue) |
| C18 | EOD flatten 15:55 (Gamma_EodFlatten ×2) | task fires | independent scheduled task | daily | its own logs | monday_verify/task-result checks |

## 3. FLEET chain — link by link (`fleet_live.py` / `fleet_executor.py` / `build_shared_signal.py`)

| # | Link | Preconditions | Failure behavior (verified) | Staleness/retry | Ledger visibility | Alarm |
|---|------|---------------|------------------------------|-----------------|-------------------|-------|
| F1 | Shared signal produced (`build_shared_signal`) ← core-decisions.jsonl | **the ENTIRE core chain C1–C6** + producer task | no core row → empty blocks (fail-closed) | pinned to `core_tick_id` (08-01 race fix) | signal file content | inherits core alarms; F2 catches consumption |
| F2 | Signal consumed — `_load_signal` :93 | file exists, parses, `written_at` ≤ 420s | missing/stale → every arm logs a `signal_status != "ok"` HOLD row — **arms tick but are functionally dead** | 420s staleness gate | `signal_status` per row | **CLOSED TONIGHT**: stale-signal dominance >30%/arm → `SIGNAL_STALE_WALL` |
| F3 | Creds + account + breaker | secrets.json entry; account GET | **ERROR row, arm skipped this tick** (fail-closed) :606-612 | none | `action: ERROR` | **CLOSED TONIGHT**: ≥3 ERROR rows/arm/day → `ARM_ERRORS` |
| F4 | Flat read `fb.is_flat_spy_options` :616 | positions GET | **FAIL-OPEN → same hole as C10** (§6-O1) | read ONCE per tick, before exits/prefetch/decide — time gap to placement | invisible when wrong | **OPEN — O1** |
| F5 | Exit-management pass (`ea.manage_tick`, runs FIRST) | registered exit state | errors caught → `exit_pass` error rows, entry pass continues | ribbon-flip fn + closed-5m-close fail-open on stale signal | exit_pass | live_watch ✅ |
| F6 | plan_all (gates→tier→qty; probe/ladder/full-send rescue lanes) | pure | **probe**: risky-3, allowlist `{SKIP_BULL_1100_1200}` only; **ladder**: INERT (no floor key on any arm — config truth); **full-send**: risky-1, 5-veto allowlist | n/a | plan reason strings | see F7 for the shadowing fix |
| F7 | finalize: floor → boost (SHIP C) → shrink → risk_gate | premium resolved (prefetch `get_option_mid` → None → est_premium → None → UNREADABLE deny) | floor fail-closed; **L246 DEFECT (FIXED TONIGHT): a doomed OTM ENTER plan shadowed the full-send rescue because plan_all's "no ENTER in plans" ran pre-floor. Now: floor-killed plan → `floor_rescue_plan` → rescue re-finalized at its OWN ATM strike's REAL premium — floor + NOT_FLAT + kill + PDT + Rule 6 all re-bind; denied rescue annotates the original row** (`fleet_executor.py::floor_rescue_plan`, `fleet_live.decide_arm`, commit `5fa89536`) | rescue premium = fresh quote at decision time | `FULL_SEND cohort=… ; floor_rescue after SKIP_MIN_PREMIUM_FLOOR` / `…floor_rescue denied: <code>` | **CLOSED TONIGHT**: ≥10 floor-kills/arm/day → `FLOOR_WALL` alarm (= the ATM-prereg baseline count) |
| F8 | `_place_live`: ceiling/floor → quotes → claim+orders guard → POST → **fill poll + reanchor (SHIP A)** | quote two-sided; guards pass | every refusal is a named SKIP row; fill unknown → limit anchor kept + stderr log | claim TTL 180s; poll 4×0.6s | placement dict per row | infra-shaped refusals visible per-row; day-level via F3 |
| F9 | Exit registration + reanchor | register_entry succeeds | failure never aborts entry (logged) | — | decisions.jsonl | live_watch ✅ |
| F10 | EOD flatten (fleet_eod) | task fires | independent | daily | logs | monday_verify |

---

## 4. Conjunction kills — the named multi-link failures

1. **TODAY (wall #1): rebuild → tier-shift → OTM-2 → floor** = 4 links. $5K equity moved every
   bold-tier arm into the $2K–10K bracket (= OTM-2 in `bold_core`), the afternoon elite cluster
   priced $0.06–0.18, ALL under the $0.30 floor → whole afternoon floor-walled for 4 of 5 arms.
   No single link failed; the CONJUNCTION killed the afternoon. **Tonight: the conjunction now
   ALARMS same-day (FLOOR_WALL, organically proven on today's ledgers: 33/35/35). The cure is
   ATM-TIER-EXTENSION-2K-10K (task #73, in flight in another lane).**
2. **TODAY (wall #2, L246): floor × rescue-lane ordering** — the rescue built for exactly this
   floor collision fired 0 times EVER because the doomed plan it would replace counted as an
   ENTER at plan time. **FIXED tonight (§5).**
3. **Friday's shape: feed-fix → gate-stale-evidence** — a data-side fix re-enabled flow into a
   gate armed on stale evidence (block_elite_bull, 111 blocks of an 11/11 setup). The gate-expiry
   /revalidation-clock rail exists (`gate_expiry_check`, WS11 additive routing); SHIP B lifted the
   gate with a frozen kill.
4. **749.33 latency: level-producer → levels_active 15 min late** — the tape respected the level
   at 09:29; it entered `levels_active` 09:44:03. Per EOD: MEASURE across sessions before any fix
   (queued; not re-derived here).
5. **09:25 bounce: premarket-frame × entry-window × filter-7** — three independent
   correct-by-design links conjoined into "structurally untradeable" (A/B pre-registered W1/W2,
   runner NOT built — deliberately unarmed).
6. **Post-SHIP-B note on the full-send lane:** with `block_elite_bull` lifted, elite ticks no
   longer produce the cohort veto that feeds `signal['full_send']` — the rescue's elite material
   dries up BY DESIGN (it rescues *vetoed* cohorts; an unvetoed elite tick trades normally...
   subject to the floor, which is the ATM-extension's job, and — if SHIP B's kill re-blocks —
   the rescue lane is standing ready again. The other 4 allowlisted vetoes still feed it either way).

## 5. Shipped tonight (this lane)

- **① `5fa89536` — L246 ordering fix.** `fleet_executor.floor_rescue_plan` (pure, fail-closed
  eligibility: floor verdict only; never rescues a rescue; full-send arms only) +
  `fleet_live.decide_arm(rescue_premium_fetch=…)` re-finalizing the rescue at its own strike's
  real quote + `run()` wiring. **RED-proof recorded** (16 fail → 17 pass), vary-and-assert (C14)
  both directions, floor NEVER bypassed (re-asked at ATM), every risk guard re-binds
  (NOT_FLAT/KILL_SWITCH/PDT proven by guards). Fleet suite **365/365**.
  *Revert: `git revert 5fa89536`.*
- **② `9fd87d85` — content alarms** in `engine_liveness_check` (+`FEED_DEAD_INSIDE_RUNNING_ENGINE`,
  `BLIND`, `VIX_FEED_DEAD`, `BROKER_INFRA_FAILURES`) and `fleet_liveness_check`
  (+`SIGNAL_STALE_WALL`, `FLOOR_WALL`, `ARM_ERRORS`, rescue-denied tally). **Additive + fail-open**:
  status/exit codes untouched; alarms ride the existing `reason` string (auto-surfaces through
  `engine_health.check_session_ran` / `check_fleet_ticked` + `daily_brief`'s `alarm_line` + CLI)
  plus structured keys. **Organic proof (cold reality, this session):** fleet check on today's
  REAL ledgers → `FLOOR_WALL 33/35/35` on safe-3/risky-1/risky-3, matching the EOD's hand-derived
  counts; core → RAN 772 clean (it genuinely was). 15 guard tests; existing liveness suites green
  (86 passed combined). *Revert: `git revert 9fd87d85`.*

## 6. OPEN items (honest ledger — none silent, all named)

| ID | Item | Mechanism (precise) | Proposed close |
|----|------|---------------------|----------------|
| O1 | **Fail-open flat read on BOTH placement paths** | `fleet_broker.get_positions` returns `[]` on error → `is_flat_spy_options`=True during a positions-endpoint outage → `check_order` sees flat → placement guards check ORDERS only (positions re-checked only in the stale-cancel branch) → **a held position + positions-outage + fresh signal can stack a second entry (Rule 4)**. Narrow window (early flat read → placement), never observed live; orders-side half was closed 2026-08-02, positions-side was documented as wrong-for-placement and left | add `spy_flat_checked(creds) -> (flat, ok)` fail-CLOSED variant in fleet_broker; consult it INSIDE `_place_live`/`_execute` placement blocks (mirror of `open_buy_orders_checked`'s design + its "missed entry cheap, double entry not" doctrine). Deliberately NOT shipped at 01:30 with another lane concurrently editing fleet files — needs its own RED-proof session |
| O2 | Probe/ladder lanes share the L246 shadowing shape | same "no ENTER in plans" precondition; probe's only cohort (`SKIP_BULL_1100_1200`, SAFE ledger) coexisting with a floor-doomed normal plan is possible in principle | extend `floor_rescue_plan` eligibility to probe (risky-3) behind its own vary-and-assert — small, but per C14 discipline gets its own test pass, not a silent broadening of tonight's fix |
| O3 | `extra_exec` blind counters (safe-2's +$67.85 invisible to monday_verify ws1 / participation-daily / 16:39 self-check) | EOD §6 | **owned elsewhere** (task_8be87fea + EOD after-hours queue) — not re-derived here |
| O4 | Level→levels_active latency (749.33, 15 min) | producer cadence + hysteresis interplay | measure across sessions first (EOD directive), then propose |
| O5 | VIX=0.0 *behavior* (gates silently flip) | C4 — tonight ships the ALARM only; changing fetch-failure behavior (e.g. fail-closed HOLD on vix=0 at an armed tick) is an edge-affecting change | needs its own A/B/prereg — an alarm was the correct first move (see the bull-vix-soft-mode graveyard entry) |
| O6 | ~~Ladder lane inert~~ **RESOLVED during this walk — not an open item.** The ladder was deliberately DISARMED 2026-07-27 ~23:30 ET **on evidence** (390-day fullhist replay `e65ed269`: floor=9 −$10,903/332tr, floor=8 −$16,642/725tr vs baseline +$5,307 — ALL floors lose), with RE-ARM override notes inline in `params.json:15`, `aggressive/params.json:19`, `accounts.json:42/109`. MEMORY's "SCORE LADDER arms" note simply predates the same-night disarm. Machinery + guards intact/inert; the narrow LADDER-SUBSET-PREREG stays queued | one hygiene line only: risky-3's `score_ladder_doc` (`accounts.json:152`) still reads "armed 2026-07-27" though its key was revoked with the rest — stale doc string, not a live lane |

**Bottom line for Tuesday:** the floor-wall conjunction that killed today's afternoon now (a)
alarms same-day on every arm, (b) has a live rescue path on risky-1 (the "speculative trades
that safe arms don't take" J named as the account's entire point), and (c) has its structural
cure in flight in task #73. The fleet's blindness classes (stale signal, creds death, feed death
inside a running engine, VIX-feed death, key-levels death) each now have a named, tested,
fail-open alarm wired into surfaces J already reads.
