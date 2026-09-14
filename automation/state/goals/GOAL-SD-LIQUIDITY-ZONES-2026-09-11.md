# GOAL: SD-LIQUIDITY-ZONES-2026-09-11

> J verbatim (2026-09-11 ~23:30 ET, mid-turn, after the most-touched level cap was built):
> *"what we really need is true supply and demand liquidity zones fined them and find the
> indicator an get it on the chart /goal"*
>
> Earlier the same evening: *"remove all lines other than the most touched ones, there are too
> many"* — shipped as the MOST-TOUCHED cap in `refresh_levels_intraday.py` (22 → 6 lines). That
> cap is the **stopgap**; this goal is the **destination**: the engine's level source becomes
> supply/demand bases and liquidity pools, not swing pivots and memory prices.

## WHY (audit evidence, not taste)
`FABLE-FULL-AUDIT-2026-09-11` §2b: since 08-17 the engine anchored 13 signals on same-day 3-bar
swing pivots (−$586, September −$1,237, 8 of 10 lost) and 15 on multi-day MEMORY prices (−$106,
Sept −$811), while the structural class (prior-day / premarket / session highs-lows) made
+$3,037. None of those sources is a supply/demand zone in the trader's sense: a **base** (the
last opposing candle(s) before a displacement move) whose body-to-wick range is the zone, plus
**liquidity** resting at equal highs/lows, swing extremes and prior-day/week H/L. J's own
doctrine already says levels are ZONES (2026-07-17) and the play is zone → wait for the return →
structure shift (2026-07-28). The feed never produced zones of that kind.

## THE THREE DELIVERABLES
1. **Indicator on the chart.** A supply/demand + liquidity study on the live SPY 5m layout,
   surviving `Gamma_LaunchTV` (08:00 ET) restarts, readable headlessly (`data_get_pine_boxes` /
   `data_get_pine_lines` via CDP). Candidates, in order: `Smart Money Concepts [LuxAlgo]` (order
   blocks = S/D bases, EQH/EQL = liquidity, FVG, premium/discount), `Order Blocks & Breaker
   Blocks [LuxAlgo]`, `Liquidity Swings [LuxAlgo]`, `Supply and Demand Visible Range [LuxAlgo]`
   (last: visible-range recompute makes it unstable as a feed). If no community script can be
   added headlessly, port an open-source S/D-zone script under its licence into our own Pine via
   `pine_new` / `pine_set_source` / `pine_smart_compile` — its boxes are ours to read.
2. **Zones as a level source — SHADOW FILE FIRST.** `heartbeat_core._read_level_records` filters
   on expiry and ±$12 only (no tier or role filter — the 2026-09-10 WS-E finding), so a
   "Reference" zone in `key-levels.json` WOULD enter the entry gate. Zones therefore go to
   `automation/state/sd-zones.json` (schema: `{zones:[{low, high, mid, kind: supply|demand|
   liquidity, origin_ts, touches_uniform, source_study}]}`), drawn by the existing drawer from that
   file, scored by the same uniform respect count the cap uses. Promotion into `key-levels.json`
   as an anchor class is a pre-registered checkpoint row (09-29 if it only REMOVES anchors,
   10-30 if it adds them).
3. **The definition, written down** (fold into `markdown/0dte/playbook.md` "Levels" section, no
   new doc): what counts as a supply/demand base and a liquidity pool here, how the chosen
   indicator's rules map onto that, and what does NOT count (a 3-bar pivot, a memory price).

## DONE-WHEN
- (a) `chart_get_state` lists the study on the SPY 5m layout after a `Gamma_LaunchTV` cycle;
  `data_get_pine_boxes(study_filter=...)` returns ≥ 1 zone during RTH; screenshot in
  `journal/screenshots/` and linked from the PROGRESS LOG.
- (b) `automation/state/sd-zones.json` refreshed by an EXISTING fire (the level refresher or
  premarket), fail-open when TV is down, with `touches_uniform` per zone; the drawer draws zones
  from it as boxes/lines; `engine_health` does not go RED when the file is absent.
- (c) playbook "Levels" section carries the definition + the indicator mapping (one section).
- (d) `backtest/tools/trigger_anchor_class_read.py` reports an `SD_ZONE` class once zones exist:
  the forward read (≥ 10 sessions) compares zone-anchored respect rate / P&L against the
  MEMORY and INTRADAY classes. Promotion prereg filed with F1–F5 gates and a kill criterion.
- (e) KILL if: no candidate indicator is readable headlessly AND the Pine port fails to compile;
  or zones do not out-respect the uniform-touch levels over the 10-session read.

## QUEUE
- [x] (a) add the indicator to the live layout via `chart_manage_indicator` (try the candidates in order), confirm `data_get_pine_boxes` reads it, confirm it persists across a TV relaunch, screenshot.
- [x] (b) `sd-zones.json` producer inside the existing refresher fire (CDP read → zones → uniform touches), drawer support, fail-open + guard test.
- [x] (c) playbook "Levels" section: S/D base + liquidity definition, indicator mapping, what is NOT a zone.
- [x] (d) `SD_ZONE` class in `trigger_anchor_class_read.py` + forward clock + promotion prereg (09-29 / 10-30 row).
- [B] (e) 10-session read → promote / extend / kill, recorded here and in STATUS. **BLOCKED ON CALENDAR/DATA ACCRUAL, not on J or on effort:** `automation/state/sd-zone-forward-clock.json.eligible_for_forward_read` must be `true` (≥10 archived trading-day sessions in `journal/sd-zones-archive/`) before this read counts as evidence — see `prereg-sd-zone-anchor-promotion-2026-09-12.md` §3, which explicitly forbids a mid-accrual peek from counting. First possible archived session is 2026-09-14 (Monday); at one session/trading-day the clock cannot clear before roughly **2026-09-25**. **UNBLOCK CONDITION (check before re-opening to `[ ]`):** read `sd-zone-forward-clock.json`, confirm `eligible_for_forward_read == true`, THEN flip this back to `[ ]` (or straight to `[~]` and do the read) — do not re-open it just because a session wants work to do.
- [x] (f) what-if shadow lane — a deterministic $0 EOD script that PLAYS each day's zone touches itself (zone → wait for the return → confirmation → hypothetical entry → walk the real production exit-stack) across a pre-registered confirmation x exit x strike grid, so evidence accrues even on a day the engine takes zero fills (2026-09-14: 0 engine fills, but SPY bounced clean off the 757.88-758.58 demand zone ~10:56-11:06 ET). Rule set frozen in `prereg-sd-zone-anchor-promotion-2026-09-12.md` §9 (DESCRIPTIVE companion — does not alter §3-6's own gates). See PROGRESS LOG entry below for files/tests/task/result.

## PROGRESS LOG
- 2026-09-11 23:4x ET (Fable, audit session): goal authored on J's mid-turn directive; placed at the
  TOP of the ladder — `GOAL-SUBTRACTION-2026-09-11` re-queued right behind it (its item (a) is done;
  (b)–(e) remain). The MOST-TOUCHED cap shipped the same night as the stopgap (see STATUS).
- 2026-09-11 23:43 ET (Fable): **(a) mostly done, live.** `chart_manage_indicator` cannot add community scripts by name
  (`new_study_count 0` for both spellings). What worked: `ui_click` aria-label "Indicators, metrics, and strategies"
  -> `ui_type_text` "Smart Money Concepts" -> `ui_evaluate` click on the row
  `[data-role="list-item"][data-id="PUB;6daafb2cabe6419d98ae25229d2327f8"]` (the `ui_click by=text` matcher
  cannot see list rows; the JS row-click can). `chart_get_state` now lists **Smart Money Concepts [LuxAlgo]**
  (study id `foIsMP`) on BATS:SPY 5m; `data_get_pine_boxes(study_filter="Smart Money")` returns **5 zones**
  (766.32-765.91, 765.30-765.01, 764.64-764.54, 764.14-764.00, 761.85-761.36) -- readable headlessly, so (b)
  has a source. Layout save sent (Ctrl+S) -- **persistence across `Gamma_LaunchTV` UNVERIFIED until Monday's
  08:00 relaunch**; screenshot `smc-luxalgo-added-2026-09-11` captured via `capture_screenshot`. LEFT IN (a):
  confirm the study is still present after the relaunch; trim SMC inputs to order blocks + EQH/EQL (the default
  also paints internal structure labels + FVG + premium/discount, which is the clutter J just asked us to remove).
- 2026-09-11 23:43 ET — opened by goal_autopilot
- 2026-09-11 23:52 ET (Fable, continuation 2/3): **(a) DONE, verified by a real relaunch.** Layout read "All changes saved";
  ran `setup/launch_tv_debug.ps1 -Kill` (the same launcher `Gamma_LaunchTV` uses; note that task SKIPS when CDP is
  already live, so Monday 08:00 would not have relaunched anyway) -> TradingView.exe restarted 23:47:09 ET (pid 17872),
  CDP back on 9222, same layout URL. After the relaunch `chart_get_state` still lists **Smart Money Concepts [LuxAlgo]**
  (id `foIsMP`) and `data_get_pine_boxes` returns the same **5 zones** (766.32-765.91 / 765.30-765.01 / 764.64-764.54 /
  764.14-764.00 / 761.85-761.36). Screenshots filed: `journal/screenshots/smc-luxalgo-added-2026-09-11.png` and
  `journal/screenshots/smc-luxalgo-after-relaunch-2026-09-11.png`. INPUT TRIM: `indicator_set_inputs` (in_3 internal
  structure OFF, in_21 swing order blocks ON) reported success but did NOT survive the relaunch (defaults came back);
  re-applied via the page API `study.setInputValues` + Ctrl+S -- **persistence of the trim is UNVERIFIED** until the
  next relaunch (leave it to (b)'s first session: read in_3/in_21 via `getInputValues`; if defaults again, set them
  through the study's settings dialog). SMC input map (positional, read live): in_0 mode, in_3 show internal
  structure, in_10 show swing structure, in_19 internal OBs, in_21 swing OBs, in_29 EQH/EQL, in_33 FVG (off),
  in_48 premium/discount (off). Next item: (b) `sd-zones.json` producer.
- 2026-09-12 00:12 ET (Fable): LINE & LEVEL CONSOLIDATION shipped alongside this goal (audit S7): trendline-only anchors OFF, cap authority on both readers, last extra setup disarmed. From 09-14 the engine's only entry anchors are the capped key levels (+ FHH); item (d)'s SD_ZONE class competes against that baseline, not the old mixed one.
- 2026-09-12 00:3x ET (conductor AFTERHOURS): **(b) DONE.** `refresh_levels_intraday.py` (+3
  siblings) is on `FROZEN_TRADING_PATH` since 2026-09-11, so this could not go "inside the
  existing refresher" as written — instead: brand-new `setup/scripts/sd_zones_producer.py` +
  brand-new `Gamma_SdZonesProducer` task (freeze cannot apply to code/tasks that did not exist
  yet). Two new `tv_cdp.TvChart` methods: `pine_boxes(study_filter)` (Python port of the
  TradingView MCP's `getPineBoxes` — same `_primitivesCollection.dwgboxes` walk) and
  `create_rectangle(point, point2, text)` (mirrors `create_horizontal_line`'s before/after
  id-diff). The producer imports `_uniform_touches`/`_zone_width`/`_spy_bars` from
  `refresh_levels_intraday` READ-ONLY (zero edits to that frozen file) so the respect-count
  math is byte-identical to the ratified most-touched cap. **Verified LIVE against the real
  BATS:SPY chart:** `--dry-run` and a real run both read 10 order-block boxes from `Smart Money
  Concepts [LuxAlgo]` (spot 764.40), classified 5 supply / 5 demand, touches_uniform 1–17,
  wrote `automation/state/sd-zones.json`; `--draw` mode created 10 real `[SD] `-tagged
  rectangles then removed all 10 via `remove_own_drawings` in the same session (chart left
  clean — left OFF by default in the scheduled cadence per J's "too many lines" directive,
  since the LuxAlgo study already paints the same boxes). Guard: new
  `backtest/tests/test_sd_zones_producer_2026_09_12.py` (12/12; the rectangle-vs-horizontal_line
  shape-filter safety test RED-proofed live via a real mutation — reverted). Task installed +
  verified registered (`State=Ready`, real `MSFT_TaskWeeklyTrigger`, `NextRun=09/14/2026
  06:44:00`), documented in `SCHEDULED-TASKS.md` (count 183→184, `test_scheduled_tasks_doc.py`
  5/5). `engine_health.py` never references `sd-zones.json` — its absence/staleness structurally
  cannot turn the engine RED, satisfying that DONE-WHEN clause by construction. Curated safety
  gate 59/59. Rail: neither new file is on `FROZEN_TRADING_PATH` (verified via
  `doctrine.frozen_path_hit`); revert = `git revert <this commit>` +
  `Unregister-ScheduledTask -TaskName Gamma_SdZonesProducer -Confirm:$false`; this entry is the
  REVOKE report. Next: (c) playbook definition, or (d) `SD_ZONE` class in
  `trigger_anchor_class_read.py` (needs a few sessions of `sd-zones.json` history first).
- 2026-09-12 00:4x ET (conductor continuation 1/3): **(c) DONE.** Added a new `## Levels`
  section to `markdown/0dte/playbook.md` (between "How a setup gets into this playbook" and
  "## Setups") defining S/D base (origin candle of a displacement move, a band not a price) vs
  liquidity (EQH/EQL, swing extremes, prior-day/week H-L — where stops cluster, not a base),
  mapping both onto the live `Smart Money Concepts [LuxAlgo]` study (order blocks=bases,
  EQH/EQL=liquidity, FVG/premium-discount left off-scope), naming the current SHADOW-file state
  (`sd-zones.json`, not in the live entry gate), and explicitly excluding the two classes
  `FABLE-FULL-AUDIT-2026-09-11` found losing money as anchors (3-bar `INTRADAY_SWING` pivots
  −$586/−$1,237 Sept; multi-day `MEMORY` prices −$106/−$811 Sept) plus round numbers with no
  structure — while leaving the already-validated PDH/PDL/PMH/PML/RTH-HL class untouched (it is
  liquidity by this section's own definition, +$3,037 in the same audit window). Verified: file
  not on `FROZEN_TRADING_PATH` (`doctrine.frozen_path_hit` → None); playbook-adjacent guard
  suites (`test_playbook_setup_registry_parity_2026_08_18.py`,
  `test_trendline_reclaim_trigger.py`) 8/8 unaffected; curated safety gate 59/59. Doc-only
  change, no code/test needed. Next: (d) `SD_ZONE` class in `trigger_anchor_class_read.py` —
  needs several sessions of `sd-zones.json` accrual before the forward read is meaningful.
- 2026-09-12 01:0x ET (conductor AFTERHOURS): **(d) DONE.** `sd_zones_producer.py` only
  ever overwrote the live `sd-zones.json` in place — a "forward read" comparing sessions
  had no history to read. Shipped: (1) daily archiving — a successful (`status="OK"`,
  non-dry-run) capture also writes `journal/sd-zones-archive/{day}.json` (same one-file-
  per-session convention as `journal/gex-archive/`), last snapshot of the day wins;
  (2) a forward-clock state file `automation/state/sd-zone-forward-clock.json` that
  accrues distinct archived dates and flips `eligible_for_forward_read` at ≥10 — a
  `--dry-run` or a `SKIPPED_TV_DOWN` carry-forward tick deliberately does NOT advance
  either the archive or the clock (would silently inflate "sessions accrued" with days TV
  never actually answered); (3) an `SD_ZONE` overlay in `backtest/tools/
  trigger_anchor_class_read.py` (`--sd-zone` flag, new `sd_zone_read()`) that joins each
  fill's entry to its ENTER tick's live SPY spot (same ±2min tolerance as the existing
  ratified `read()` path) and checks that spot against the day's archived zone list —
  buckets `in_zone` / `out_of_zone` / `no_archive_days` (the last kept structurally
  distinct so a day with no archive can never be silently folded into `out_of_zone`);
  (4) the promotion prereg, `analysis/recommendations/prereg-sd-zone-anchor-promotion-
  2026-09-12.md` — G1–G6 forward gates + kill criterion, explicitly an **EXPANSION**
  candidate (10-30 checkpoint only, never 09-29, since it would ADD a live anchor class),
  gated on the forward-clock eligibility flag before any read counts as evidence.
  **Verified live (OP-33), scoped honestly:** did NOT re-run the real TV/CDP producer this
  fire (Saturday, no live TradingView session — nothing to gain and the archive/clock
  changes are already covered by 5 new offline unit tests that fake the chart, same
  convention as the rest of this module's suite). DID run the real, non-mocked
  `--sd-zone` CLI against the actual `core-decisions.jsonl` / `trades.csv` for
  2026-09-01..09-12: correctly reports 0 in/out-of-zone legs and 7 `no_archive_days`
  (the archive genuinely does not exist yet before today — exactly the expected state,
  proving the new code path runs clean against real data with zero exceptions).
  RED-proofed live: broke `_in_zone`'s bound check, 3 of the new tests failed exactly as
  expected, reverted, green again. 25/25 new+existing tests across both files green
  (18 in `test_sd_zones_producer_2026_09_12.py`, 7 in the new
  `test_trigger_anchor_sd_zone_overlay_2026_09_12.py`). Neither touched file is on
  `FROZEN_TRADING_PATH` (verified via `doctrine.frozen_path_hit`, all None). First
  possible archived session is **2026-09-14** (Monday, `Gamma_SdZonesProducer`'s first
  weekday fire); at one session/trading-day the clock cannot clear before roughly
  **2026-09-25** — item (e) is correctly NOT-BEFORE that date, not idle-blocked, and the
  ladder should not re-pick it earlier than that. REVOKE: `git revert <this commit>` (pure
  addition — no existing function's behavior changed, confirmed by the unchanged-`_cls`
  regression test).
- 2026-09-12 00:37 ET (Fable, interactive): LANE COLLISION on item (b) -- this session built a second (b) in parallel (drawer-hosted CDP capture + a scorer INSIDE the frozen refresher under GAMMA_FREEZE_OVERRIDE, 8 guards GREEN, live smoke 10 boxes) while the 00:10 conductor fire built `sd_zones_producer.py` + `Gamma_SdZonesProducer` (zero frozen-file edits, 12 guards, task registered, ee9bdc19/441a270c). FOLDED to the conductor's; mine discarded before commit (the 2026-09-10 rule stands: do not stretch the freeze override for a shadow file). Kept from mine: `.gitignore` entry for `automation/state/sd-zones.json`, a consumer-side pin (heartbeat_core + fleet never reference the file), STATUS_MD isolation in the producer's dry-run test (its 00:22 cut leaked a `### BROKEN` block into the real STATUS.md -- removed). Independent read of the same CDP walk from this session: 10 boxes (770.48-769.80 down to 757.65-757.25), SMC inputs currently in_3=false / in_21=true (persistence across the NEXT relaunch still UNVERIFIED). ROOT CAUSE of the collision: the item was never flipped to `[~]`; the Stop-hook continuation text now says CLAIM FIRST (guard in setup/hooks/test_doctrine_hooks.py). Cadence UNVERIFIED until the first scheduled fire Mon 2026-09-14 08:44 ET advances `sd-zones.json.as_of`.
- 2026-09-12 01:2x ET (conductor, Stop-hook continuation 1/3): **Corrected item (e)'s marker, did not do the read.** The Stop hook re-triggered on (e) because it was left as a bare `- [ ]` with only prose saying NOT-BEFORE ~2026-09-25 — `goal_next_open_item` only recognizes `[B]`/`[B-J]` as excluded from continuation (per `doctrine.goal_next_open_item`'s own docstring: "a blocked item must never keep re-triggering a continuation; that is what the B/B-J markers exist to prevent"), so a bare `[ ]` with a date in the text still counted as open work needing to be claimed. Doing the actual 10-session read right now would produce a meaningless result (the archive has zero sessions as of today — confirmed by the live `--sd-zone` smoke run in the entry above: `no_archive_days` for every day checked) and would directly violate this goal's own prereg §3 ("nothing is armed, tuned, or peeked at mid-window... a mid-window read for curiosity does not count and must be labeled as such"). Faking a claim/finish on (e) today would be gaming the continuation mechanism, not doing the work. Flipped `- [ ]` → `- [B]` with the unblock condition stated inline (check `sd-zone-forward-clock.json.eligible_for_forward_read == true` before re-opening). No code changed this continuation; this is a goal-bookkeeping-only correction. REVOKE: flip `[B]` back to `[ ]` (not recommended — recreates the false-continuation loop).
- 2026-09-12 01:19 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
- 2026-09-14 13:2x ET (worker-tier build): **(f) DONE.** Built the SD-ZONE WHAT-IF shadow
  lane. Files: `backtest/lib/sd_zone_whatif_sim.py` (pure sim core -- touch/confirmation
  detection, strike math, sizing, the exit-stack walk), `setup/scripts/sd_zone_whatif.py`
  (I/O orchestrator), `setup/scripts/install-sd-zone-whatif.ps1`,
  `backtest/tests/test_sd_zone_whatif.py` (13 new tests) + 4 tests folded into
  `test_sd_zones_producer_2026_09_12.py` covering the new per-15-min intraday zone archive
  (`journal/sd-zones-archive/intraday/{day}/{HHMM}.json`, deliverable A -- the no-look-ahead
  source `sd_zone_whatif.py` needs). Rule set frozen in
  `prereg-sd-zone-anchor-promotion-2026-09-12.md` §9 (appended, §1-8 untouched). Tests:
  `backtest/tests/test_sd_zone_whatif.py backtest/tests/test_sd_zones_producer_2026_09_12.py`
  -- **36 passed** (`36 passed in 1.30s`). Task registered + verified via `schtasks /query`:
  `Gamma_SdZoneWhatIf`, `Status: Ready`, `Schedule Type: Weekly`, `Days: MON, TUE, WED, THU,
  FRI`, `Start Time: 2:20:00 PM` (16:20 ET). SCHEDULED-TASKS.md count 186→187 + new row.
  **FOUND + FIXED IN PASSING (real bug, not mine originally):** 4 pre-existing tests in
  `test_sd_zones_producer_2026_09_12.py` were NOT redirecting `ARCHIVE_DIR`/
  `FORWARD_CLOCK_FILE` off the real repo paths on a real OK-status run -- every pytest pass
  of that module was silently overwriting the REAL `journal/sd-zones-archive/{today}.json`
  (+ forward clock) with fake `751.8-752.2` test zones. Caught live when this session's own
  genuine producer capture was found replaced by test data after running the suite. Fixed
  all 4 (now redirect ARCHIVE_DIR/INTRADAY_ARCHIVE_DIR/FORWARD_CLOCK_FILE to tmp_path);
  regenerated the real 2026-09-14 archive + forward clock with a fresh live producer run
  (`OK symbol=BATS:SPY spot=762.29 n_zones=10`) to undo the corruption. **BACKFILL RESULT
  (F):** 2026-09-12 is a **Saturday** (0 SPY bars, both feeds) -- ran it per instruction
  ("do not fabricate zones for earlier days"), correctly produced 0 rows with warning
  `no SPY bars for 2026-09-12`, not a crash (fixed a real `.get("bars", [])` vs
  `.get("bars") or []` bug this exposed -- Alpaca returns an explicit `bars: null`, not a
  missing key, on an empty window). **2026-09-14 (today) also produced 0 rows** for an
  honest, disclosed reason: the day's one real zone-respecting touch (SPY dipped into the
  757.94-758.58 demand zone at **09:36 ET**, per a synthetic mechanism-validation replay
  below -- the goal's own narrative said ~11:06, actual touch time per real 1-min bars is
  09:36) happened BEFORE this session's first real intraday snapshot (13:07:17 ET) --
  correct no-look-ahead behavior, not a bug: a zone this lane didn't know about yet cannot
  be used to score a touch that already happened. **Mechanism validated separately** (not
  written to the real ledger): re-ran `simulate_day` with a synthetic as-of-09:00 snapshot
  carrying TODAY'S REAL zones -- found the real 09:36 touch, all 3 confirmations fired
  (touch_close/structure_shift/wick_reject), proving detection is live-data-correct.
  **Option-bar pricing is currently blocked**, separately: `exit_shape_parity_study.
  fetch_option_bars` (pre-existing, unmodified) returns `HTTP Error 403: Forbidden` for
  today's 0DTE contracts as of ~13:25 ET -- an upstream data-entitlement/availability
  condition, not new code; the installed 16:20 ET fire runs after intraday option data is
  typically posted, so this should self-heal on its own first real fire. **OPEN ITEMS for
  the next session:** (1) confirm the 16:20 ET fire clears the 403 and actually prices a
  leg once the day has a real post-instrumentation touch; (2) `obsidian_vault_sync.py`'s
  new SD-zone-what-if SHADOW.md block is syntax-checked but UNVERIFIED by a real generator
  run (not executed this session -- out of scope risk of touching other generated
  surfaces). Added `.gitignore` entries for `sd-zone-forward-clock.json` (C34) and
  `journal/sd-zones-archive/` (bloat, same reasoning as `gex-archive`) -- neither was ever
  git-tracked (`git ls-tree HEAD` empty before this build). REVOKE: `git revert <this
  commit>` + `schtasks /delete /tn Gamma_SdZoneWhatIf /f`.

## HONEST STATE
AUTOPILOT CLOSE 2026-09-12 01:19 ET: queue fully terminal (no bare '- [ ] ' item left)
- 2026-09-12 01:58 ET (Fable): INPUT TRIM VERIFIED-FAILED, then made irrelevant. TradingView crashed on its own ~00:45 ET (GPU-process errors after the 21:03 auto-update download); relaunched 01:27 ET via launch_tv_debug.ps1. After that cold relaunch the SMC study was still on the layout (id foIsMP, 4 studies) but its inputs were DEFAULTS again (in_3=true internal structure, in_21=false swing OBs; boxes 10 -> 5) -- so page-API setInputValues + Ctrl+S does not persist. `sd_zones_producer.py` now enforces SD_STUDY_INPUTS {in_3:false, in_21:true} before every box read (fail-open, recorded as `inputs_enforced` in sd-zones.json); live proof 01:57 ET: changed=2, 10 zones. The feed is now deterministic across relaunches and auto-updates. Item (a)'s open question is closed; Monday's 08:44 fire needs no manual step.

