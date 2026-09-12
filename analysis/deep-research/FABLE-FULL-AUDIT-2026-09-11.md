# FABLE FULL AUDIT — 2026-09-11 (Fri, after close)

> **J's question (verbatim):** "I fear the project was over engineered or something by Opus because he's been rambling a lot lately.. we need a full audit. why are we all of a sudden now losing every day and cant play any levels properly"
>
> Successor to [`FABLE-FULL-AUDIT-2026-09-01.md`](FABLE-FULL-AUDIT-2026-09-01.md). Every number below was re-derived this session from `journal/trades.csv`, `automation/state/pnl-statement.json`, `automation/state/core-decisions.jsonl`, `git log`, and the SPY daily cache. Re-check commands are inline. Nothing here quotes a prior doc as evidence.

---

## 0. Verdict

1. **Nothing in the trading path changed.** Core engine (`heartbeat_core.py`), fleet signal (`build_shared_signal.py`), gates, exits and both `params.json` files were last touched **2026-08-29**; every hunk since 08-25 is fleet-status routing, a ledger `date` key, the tight-ladder qty cap, and a SUPER-tier *label*. 939 commits landed between 08-20 and 09-11 — **zero on the signal**. September is not a regression Opus introduced. It is the engine's true shape meeting a tape that does not pay it.
2. **The engine is a range-day machine, not a level machine.** Day P&L vs SPY daily range: **corr 0.62** (vs 0.13 with direction). All 7 days with range ≥ $5 were green (**+$6,615**); the 7 days with range < $3.50 were 5 red (**−$3,830**). The two tightest days in September (09-10 $3.36, 09-11 $2.72) are its two biggest losers. September compressed; the P&L followed.
3. **"Levels" — most of what the engine reclaims are not levels J would draw.** The active-level set doubled (median 10 on 08-13 → 22 on 09-11, one every ~$1.20 in the ±$12 band). By trigger anchor since 08-17: prior-day / premarket / session H-L **11 signals +$3,037**; same-day 3-bar swing pivots (re-anchored every 5 min) **13 signals −$586, September 10 signals −$1,237 (8 of 10 lost)**; multi-day MEMORY levels 15 signals −$106 (Sept −$811). (A signal = one 3-minute entry slot across all arms.) 09-11 exhibit: premarket bias said *no-trade* and named 756.64 / 757.81 / 763.70; the engine bought a reclaim of `INTRADAY_SWING_LOW` 764.63 (formed ~30 min earlier) and of `INTRADAY_SWING_HIGH` 766.08 (the day's high on a $2.72 range day). Structure stop = first 5m close back through the anchor → 11 of 17 legs stopped inside 5 minutes.
4. **The book number is four copies of one trade.** All arms fire on the same signal within ~15 s. On 09-11 two signals (10:01, 10:51) × 4 arms = −$791 of the −$619 day. Per account September is **−$68 to −$498** with 3–5 red days each. A bleed, not a blow-up.
5. **Over-engineering is real and measurable (§3), and it costs money in three specific places — but it is not what lost this week's money.** Cutting machinery will not fix the signal. It will make the signal *visible*, which is the precondition for fixing it.

---

## 1. What actually happened (broker-truth, `pnl-statement.json` per_day)

| Day | Book | safe-2 | bold-2 | safe-3 | risky-1 | SPY range | Note |
|---|---:|---:|---:|---:|---:|---:|---|
| 09-01 | +78 | +218 | −140 | — | — | 5.18 | bear day, safe-2 TP |
| 09-02 | −699 | −126 | −15 | −213 | −345 | 4.69 | 12 legs, ALL structure stops |
| 09-03 | +734 | −312 | +129 | +605 | +312 | 6.54 | safe-2 gate-blocked from the 11:06 winner (§3a) |
| 09-04 | +338 | +213 | +125 | 0 | 0 | 3.85 | **both are J's manual exits**; engine 0 |
| 09-08 | −116 | −21 | −95 | 0 | 0 | 4.52 | |
| 09-09 | 0 | 0 | 0 | 0 | 0 | 3.45 | no trades; **engine stopped ticking 15:06** (§3c) |
| 09-10 | −790 | 0 | −190 | −280 | −320 | 3.36 | one bear signal, 4 arms, all stopped |
| 09-11 | −619 | −219 | −75 | −180 | −145 | 2.72 | 27 legs; bias said no-trade |
| **Sept** | **−1,074** | **−247** | **−261** | **−68** | **−498** | | engine −$1,412, J manual +$338 |

Last three sessions: −$1,525, all engine. Re-check: `python -c "import json;d=json.load(open('automation/state/pnl-statement.json'));[print(k,v) for k,v in sorted(d['per_day'].items()) if k>='2026-09-01']"`

---

## 2. The four mechanisms

### 2a. Range pays the engine; direction does not (n = 21 sessions, 08-11..09-11)

| Bucket | Days | Book P&L |
|---|---:|---:|
| SPY range ≥ $5.00 | 7 | **+$6,615** (7/7 green) |
| $3.50–$5.00 | 7 | −$663 |
| < $3.50 | 7 | **−$3,830** (5/7 red) |
| Up day > +0.3% / down < −0.3% / flat | 7 / 8 / 6 | +$2,196 / +$1,011 / **−$1,085** |

Correlations: range **0.62**, |return| 0.35, trend-efficiency 0.20, signed return 0.13. Exit mix confirms the shape: Aug 11–31 winners-exits (tp1+trail) : structure stops = **60 : 55**; September **14 : 35**. The engine buys the first close through a nearby line and needs the day to run. When it does not, the very next 5m close takes the position out. *Caveat: daily bars are the IEX cache (ranges approximate); this is 21 days and partly mechanical (right-tail exits require range by construction). It is a diagnosis, not a gate — the chop battery run 09-08 tested 12 admissibility rules and none cleared multiplicity.*

### 2b. Anchor quality — what the reclaim/rejection was actually "of" (all arms, 08-17..09-11, 158 legs joined to their ENTER tick)

| Trigger anchor class | Signals | Legs | Total | September |
|---|---:|---:|---:|---:|
| PRIOR_DAY H/L/C + premarket H/L + session H/L | 11 | 37 | **+$3,037** | +$506 |
| SHELF (multi-week, `daily_context`) | 6 | 19 | +$148 | +$198 |
| none / unnamed price (ribbon-only rejection, no key level) | 18 | 34 | +$836 | +$145 |
| MEMORY_* (multi-day memory map, G11 wire 07-09) | 15 | 41 | −$106 | **−$811** |
| **INTRADAY_SWING_* (same-day 3-bar pivot, rewritten every 5 min)** | 13 | 27 | **−$586** | **−$1,237** (10 signals, 8 lost) |

The swing source has existed since 06-29 (`refresh_levels_intraday._swing_levels`: most recent 3-bar pivot, no age or hold requirement). What changed is the tape: on the 08-19 trend day it paid (+$741 on two signals); on September's compressed days it fires on noise. **This is the concrete answer to "can't play levels properly": the engine gives a pivot from 20 minutes ago the same standing as yesterday's high.** Post-hoc and n = 13 signals (signal = 3-minute entry slot across arms, as the instrument defines it) — hence a pre-registration (§5), not a flip. Re-check: `backtest/.venv/Scripts/python.exe backtest/tools/trigger_anchor_class_read.py --since 2026-08-17`.

### 2c. Correlation across arms

Signals taken by ≥ 3 arms: 27 signals **+$1,839**; by 1–2 arms: 89 signals +$283. The shared signal is where both the wins and the losses live (MAP.md already says so: "they lose together"). Arms are risk profiles by J's directive — not changing — but every "book" number J reads should be divided by ~4 before it is compared to a per-account target.

### 2d. It is the FIRST entry of the session that loses, not the churn

September positions: **first entry per arm/setup/day −$2,059; re-entries after a stop +$980** (09-03's 11:06 winners were all re-entries after the 09:42 stop-out). Aug: +$1,597 / +$755. The losing entries are the session's first reclaim (09:41 on 09-03, 10:01 on 09-11, 11:17 on 09-02, 12:11 on 09-10) — the moment the tape has produced the least structure. See §4 for why the re-entry lock stays dead.

---

## 3. Over-engineering — measured, and where it actually costs

| Metric | Value |
|---|---:|
| Commits 08-20 → 09-11 (23 days) | **939** (09-02 + 09-03 alone: 290 — 60 feat / 59 docs / 48 fix) |
| Commits since the 08-31 freeze, by path | tests 223 · setup/scripts 190 · automation/state 185 · analysis 173 · markdown 108 · journal 4 · **signal 0** |
| `heartbeat_core.py` | **3,309 lines** (J's own coding rule caps a file at 800); `filters.py` 2,342; `risk_gate.py` 1,724 |
| Entry-refusal vocabulary | 26 `SKIP_*` reasons in the core + 15 canonical gates + 2 shadow scorers that gate nothing |
| Scripts that read or write `key-levels.json` | **20** |
| `Gamma_*` scheduled tasks | **195 registered, 23 enabled at 22:00 ET** -- *corrected same night:* 135 of the 172 Disabled are the nightly quiet-mode blackout (they ran that day); **37 were actually parked**; 6 unregistered 09-11, 1 held, 30 stay for named reasons ([map](../audits/task-registrations-2026-09-11.md)) |
| Tests | 943 files, 13,856 tests (full suite currently RED, 8 failures) |
| Markdown files | > 6,700 (MAP.md's count; `find` sees ~10,400) |

Where it costs:

- **(a) A gate fitted on 11 trades blocked the month's best trade.** `block_bull_1100_1200` (ratified 06-18: IS n=11, OOS n=1, total IS benefit +$89) refused safe-2 at 11:06–11:09 on 09-03 with bull score 11, `level_reclaim + confluence`, while the three fleet arms took the same signal for **+$1,049**. safe-2 ended the month's best day **−$312**. The gate-expiry instrument reads YELLOW (evidence age 85 d) because its in-window floor is n ≥ 10 — it cannot see a single-day miss this size. Re-check: `python - <<EOF` over `core-decisions.jsonl` for `2026-09-03T11:0`, account `safe`.
- **(b) The level feed doubled under a freeze that only guards engine files.** The freeze hook protects `heartbeat_core.py` / `filters.py` / `params.json`; the 20 level producers feed the same entry gate and are not covered. Median active levels: 10 (08-13) → 15 (08-27) → 22 (09-11). More lines within $12 of spot = more first-close-through triggers on noise.
- **(c) Two silent engine outages in one week.** 09-09: both accounts' last tick **15:06:14/17** (started 09:40, 319 ticks vs 386) — no STATUS line, no alarm. 09-11: **97 consecutive `ERROR` ticks 12:16–13:04** (`HTTP 504`), flagged only post-hoc, endpoint unrecorded. Same box runs 188 launches/hour at 06:00 and hides ~730 console windows a day.
- **(d) The premarket got the day right and nobody consumed it.** 09-11 `today-bias.json`: *no-trade*, "wait for a confirmed trigger off 756.64/757.81 or the 763.7 PMH". The engine reads `no_trade_window_et` from params only; the bias is overwritten every morning with **no archive**, so whether "no-trade" days should be sat out is unmeasurable today. (09-09 premarket fired 09:40, swarm failed, regime stamp stale.)
- **(e) Reports that print noise.** 09-10 journal: "54 missed setups, −$839 left on the table — engine captured 0% of available edge." The missed setups *lost* money. An instrument that scores a negative number as missed edge is attention debt.

---

## 4. Claims killed this audit — do not re-find them

| Claim | Verdict | Evidence |
|---|---|---|
| "Opus's September changes broke the engine" | **KILLED** | `git diff` 08-25 → HEAD on every signal/exit/params file: routing, labels, qty cap only |
| "Re-instate the first-entry / re-entry lock (risk-rules.md 05-07)" | **KILLED** | re-entries after a stop = **+$1,735** Aug+Sep; the lock kills 09-03's winners. J's 07-02 deletion holds on the numbers |
| "Arm the conviction gate — it would have blocked the losers" | **KILLED** | C4 sidecar would-block cohort **+$1,084** (n=45): it blocks winners. KILL stands |
| "Add a chop / range admissibility gate" | **NOT SUPPORTED** | CHOP-DEFENSE battery 09-08: 12 cells, 0 cleared BH q ≤ 0.10. §2a is diagnosis, not a gate |
| "The bear side is the problem" | **PARTIAL** | Sept BEAR 12 legs WR 17% −$858 and bear rejections fire with no named level; but BULL −$554 too. Both bleed on flat days |
| "V-d1 (refuse when last 5m bar closed against)" | **NULL** | forward: blocked winners $2,195 vs losers $2,130. V-e3 (no BOS/CHoCH yet on 1m) is the only forward survivor: 8 blocked, all losers, +$715 — awaiting F4/F5 |

---

## 5. What ships, and when (decided; revoke = `git revert <sha>`)

**Tonight (this commit):**
- This audit; `analysis/recommendations/prereg-trigger-anchor-level-class-2026-09-11.md` — a **risk-REDUCTION candidate for the 09-29 checkpoint**: exclude `INTRADAY_SWING_*` as reclaim/rejection *anchors* (the level stays drawn; it just cannot be the trigger). Forward clock 09-14 → 09-28 on the frozen config; frozen kill criterion inside. Ratifying instrument `backtest/tools/trigger_anchor_class_read.py` (one table, no scheduled task).
- `STATUS.md ## Known broken`: 09-09 15:06 engine stop (unflagged), level-feed density drift, `Gamma_LedgerArchive` disabled → `key-levels-archive/` dead since 07-02, bias has no history.

**09-29 checkpoint:** the anchor exclusion, only if its forward gates pass. Nothing else from this audit is a reduction.

**10-30 window:** retire `block_bull_1100_1200` (expansion; evidence §3a). Decide bias consumption ("no-trade" → engine sits out) only after ≥ 20 archived bias days exist — that archive is the instrument gap; it is one line in an existing producer, not a new task.

**Complexity — recommendation, not executed (J's tooling, J's call):**
1. **Build-freeze to match the config freeze**: no new instruments, shadow lanes, sidecars or reports until 10-30. The parked task registrations get deleted, not parked (dry-run map first; never the restore lists) -- *done 09-11: 6 removed, see the map.* The bigger number is the 158 tasks that run every trading day; retiring those is per-task, on evidence. *Correction, same night:* the 09-08 "dead LLM flatteners" claim is STALE — both ran exit=0 with useful reconcile appends on 09-10 and 09-11; the real hazard is the harness's 120 s timeout tree-kill (22 pids at 15:57 on 09-10, target unknown). Decision deferred to evidence, not retired. → `GOAL-SUBTRACTION-2026-09-11` on the ladder.
2. **One surface per question.** HOME.md already answers "how did we do"; the journal's "Engine Misses" block and the kitchen's fabricated-artifact stream (11% of 4,437 files) go.
3. **Let the freeze protect the whole trading path**, level producers included (`refresh_levels_intraday.py`, `level_memory_producer.py`, `daily_context.py`, `context_levels.py`). *Done same night:* added to `setup/hooks/doctrine.py#FROZEN_TRADING_PATH` with the hook test extended.

---

### 5a. Same night, J's two directives (after reading this audit)

1. *"remove all lines other than the most touched ones, there are too many"* → **shipped 2026-09-11 23:38 ET**: the level feed keeps only the 3 most-respected levels above and 3 below spot (uniform touch count, see CHANGELOG 2026-09-11). Live: 22 → 6. Applied under the freeze override on J's directive; **the clean scoring window restarts 2026-09-14**.
2. *"what we really need is true supply and demand liquidity zones … find the indicator an get it on the chart /goal"* → `GOAL-SD-LIQUIDITY-ZONES-2026-09-11` at the top of the ladder. §2b's anchor-class table is the evidence it stands on; the cap is triage until zones replace pivots and memory prices as the anchor source.

## 6. UNVERIFIED / limits

- SPY ranges come from the IEX daily cache (volume ~1.2M/day = IEX only); OHLC is approximate.
- §2b is post-hoc on 13 swing-anchored signals; two of August's three were winners (+$741). The prereg exists precisely because this is not yet evidence.
- The 09-11 504 root cause is undiagnosed (the ledger row does not name the endpoint).
- Whether the premarket bias has skill cannot be measured — no history exists.
- `levels_active` in the ledger is a price list, not labels; the anchor class was resolved through the conviction shadow's `matched_level_label` (core account, 08-17 onward) and joined to fleet fills by entry minute. 14 of 172 legs did not join.

---

## 7. Line & level consolidation (J directive 2026-09-12 ~00:0x ET: "make sure engine only trades what it should be looking at line and level wise")

**What reaches the entry decision (traced):** `heartbeat_core` reads three line files -- `key-levels.json` (the entry-anchor set, ±$12, expiry-filtered), `confluence-zones.json` and `trendlines-live.json` (both feed the **shadow-only** conviction scorer; no branch acts on them). The fleet arms mirror the core's verdicts (`build_shared_signal` reads `core-decisions.jsonl`) and keep their own copy of the level reader only for the structure-stop level. The bear side had **five** trigger types (`level_rejection`, `fhh_level_rejection`, `sequence_rejection`, `ribbon_flip`, `trendline_rejection`); the bull side three (`level_reclaim`, `wick_reclaim`, `confluence`).

**What was actually trading (08-01..09-11, ENTER ticks joined to fills):**

| Anchor class of the filled signal | Signals | Legs | WR | P&L | ex-top-2 |
|---|---:|---:|---:|---:|---:|
| Key level (± confluence) | 72 | 243 | 43% | **+$2,455** | |
| **Trendline-only** -- the in-engine fitter's descending line through the last 3 pivot highs, no key level | **37** | 79 | 47% | +$1,084 | **−$1,137** (Jul +266/−955 · Aug +939/−1,282 · Sep +145/−406) |
| FHH-only / sequence-only / ribbon-flip-only | 0 | 0 | | | |

ENTER verdict ticks: 566 level-anchored vs **342 trendline-only** (37%). That line is computed inside `filters.detect_trendline_rejection_bearish`, is **never drawn on J's chart**, and the 2026-09-10 TA dial-in showed the same fitter class reproduces **0 of 24** of J's own lines. It is not a line J is looking at.

**Consolidated (all under `GAMMA_FREEZE_OVERRIDE` on J's directive; guard `test_line_level_consolidation_2026_09_12.py`, RED 6 failed → GREEN 351 passed / 4 skipped across 20 suites):**
- **C1 trendline anchor OFF.** `trendline_anchor_enabled=false` in both params files → `GATE_KEYS` → `engine_cli` flip point → `filters.evaluate_bearish_setup` skips the detector, so `trendline_rejection` never enters `triggers` and a trendline-only bar fails filter 10. Level-anchored bars byte-identical. Orchestrator got the parity kwarg (default legacy). Live check: both accounts' `gate_params` carry `False`. Revert: set `true`.
- **C2 cap authority on the read side.** When `key-levels.json` carries `level_cap`, `heartbeat_core._read_level_records` and the fleet's `_active_level_prices` return only levels the MOST-TOUCHED cap stamped (`touch_rank`). A level any other writer injects between 5-minute refreshes is invisible to the engine until the refresher scores it. 20 scripts touch that file; the cap is now the one gate. Live check: 6 stamped in-band levels, both readers return exactly those 6.
- **C3 the last armed non-level extra setup disarmed.** `double_bottom_base_quiet` (armed 2026-07-01 trade-to-learn, 0 placements and 0 extra-signal actions in 73 days) → `false`. Every `extra_setup_exec_armed` value is now `false`. `test_money_path_2026_07_01` pin updated with the reason.

**Left as is, deliberately:** `fhh_level_rejection` (first-hour high -- a level J watches; never traded alone in the window), `sequence_rejection` / `ribbon_flip` (never anchored a fill alone), MEMORY levels (inside the cap), the shadow reads of confluence zones and live trendlines (feed a scorer nothing acts on -- subtraction candidates for `GOAL-SUBTRACTION`, with the six `Gamma_Trendline*` tasks). `SKIP_LOW_CONVICTION` has no live branch (comments only).

**Honest cost:** the trendline-only class was net positive over the window (+$1,084) on the strength of two trades (+$1,501, +$720). J's directive removes it; the ex-top-2 sign says the class was not paying its way. Forward read: `trigger_anchor_class_read.py` will show zero trendline-only signals from 09-14; the 10-30 review compares the level-anchored class against this table.

