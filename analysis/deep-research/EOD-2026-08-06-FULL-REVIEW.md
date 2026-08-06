# EOD FULL REVIEW — Thursday 2026-08-06

**Synthesist pass over four investigative lanes + independent re-derivation of every load-bearing number.**
Clock verified at write time: `setup/scripts/et_clock.py` → `2026-08-06 17:10:27 Thursday EDT, market_hours=False`.
Broker truth re-pulled live this session via `automation/state/fleet/fleet_broker.py#load_creds()`. All five arms are PAPER (`paper-api.alpaca.markets`).

---

## FOR J — 12 LINES MAX

- **Day +$1,464.00** broker-verified equity delta (option gross $1,465.00, fees $0.94, crypto −$0.03). All 5 arms flat. ✅
- **The week is 4 sessions, not 3** — all accounts were born Mon 08-03. Book **$25,000 → $28,667.55 = +14.67%.** Per-day: +534 / +3,624 / −1,935 / +1,465.
- ⚠️ **Tuesday is 98% of the week.** The other three sessions net **+$64** across all five arms. n=4 → expectancy is undefined. Don't read a trend.
- ❌ **The brief's "CENTRAL QUESTION OF THE DAY" is void.** The 14:21 long was `bollinger_squeeze` on the **secondary** exec path, not a filter-5 bull fire. Filter 5 blocked **386/386** armed rows — it never cleared, not once, all day. Same broker order id (`b7f663e6`) confirms it in three independent lanes.
- Filter-5 counterfactual, **corrected in review**: a realizable earlier-entry policy = **−$120** over 3 episodes, not the −$471 first reported (that summed 13 overlapping entries on one contract). No lever either direction at n=1.
- 🚨 `structure_shift_confirmation` is **not dormant — it is dead.** Already A/B'd over 391 days on 2026-07-28: **DO_NOT_ARM, 1/5 gates, −$46.** It has now cost two sessions of re-derivation. Stop briefing it as upside.
- **Silence cost $911.35** (38% of the achievable day). And safe-3's standing root cause was **wrong**: not signal-absent — its `min_triggers=2` blocked the exact put risky-3 made **+$828** on.
- 🎯 **ONE DECISION FOR YOU:** safe-2 runs `cash_settlement`, bold-2 runs `margin_pdt`. Both accounts read **multiplier=4 (margin)**, and **both param docs justify themselves with accounts that no longer exist.** Enforcing parity today would have made **$0 instead of +$1,465.** No key touched.
- 📉 **$210 of today was a coin flip** — safe-2 and risky-3 are configured identically and saw the same quote 3 cents apart at 12:04. 82 of 98 shared polls disagreed.
- ✅ **Shipped:** 4 code commits, **79 guards green, RED-proofed by source mutation.** Chart auto-draw + auto-CLEAN is live and scheduled (your June levels are off the chart and can't re-accumulate). The autopsy "money left on the table" figure was **90.5% ORACLE artifact** — quarantined.
- ⚠️ **Still open:** 2 HIGH research-harness defects (one silently **sign-flips** a P&L), an unidentified writer injecting synthetic rows into the live decision ledger, 23 chart lines of unprovable authorship.
- **Tomorrow:** safe-2 / safe-3 / risky-1 / risky-3 all clear to trade. **bold-2 is hard-blocked (3/3 PDT, rolls off 2026-08-12).**

---

## 1. The day and the week, reconciled and graded

### 1a. Today reconciles to the cent

Re-derived live from `/v2/orders` and `/v2/account` on all five arms:

| Arm | Account | Option gross | Equity Δ | Legs | Note |
|---|---|---|---|---|---|
| safe-2 | PA3POKNV46VG | **+$339.00** | +$338.64 | 5 | put +$375, call −$36 |
| bold-2 | PA3WEBXJU67N | $0.00 | $0.00 | 0 | SILENT |
| safe-3 | PA32T7Q1O20H | $0.00 | $0.00 | 0 | SILENT |
| risky-1 | PA3S9N1IV0A4 | **+$296.00** | +$295.75 | 3 | |
| risky-3 | PA3V7JT25H6Z | **+$830.00** | +$829.61 | 3 | |
| **BOOK** | | **+$1,465.00** | **+$1,464.00** | 11 | |

Residual $1.00 = today's unposted fees ($0.94 at exactly **$0.025/contract-side**: safe-2 12×, risky-1 10×, risky-3 16×) + a BTC round trip of **−$0.0302** inside the safe-2 account at 20:45 ET on 08-05. **Unexplained: $0.00.**

> ⚠️ **The brief's `+$1,460.80` is unsourced.** Its per-arm figures (338.45 / 294.55 / 827.80) match neither gross nor equity delta, and a repo-wide grep finds them in no P&L producer. Variance −$4.20 vs gross, −$3.20 vs equity. Use the broker numbers.
>
> Note: `fills-ledger.jsonl` matched broker truth exactly — 11 rows, all `attribution=engine`, prices identical. Zero drift on that surface.

### 1b. The week is four sessions, not three

All five accounts were created **2026-08-03 between 13:00 and 13:02 UTC** at $5,000 each. Monday was omitted from the brief entirely.

| Session | Book gross |
|---|---|
| Mon 08-03 | +$534.00 |
| **Tue 08-04** | **+$3,624.00** |
| Wed 08-05 | −$1,935.00 |
| Thu 08-06 | +$1,465.00 |
| **Week gross** | **+$3,688.00** |

Book $25,000 → **$28,667.55 net = +$3,667.55 (+14.67%)**. The $20.45 difference is fees charged since creation.

Per-arm week: safe-2 +730 / bold-2 +479 / safe-3 +782 / risky-1 +1,344 / risky-3 +353.

**Tuesday is 98.3% of the gross. Ex-Tuesday, all five arms across three sessions net +$64.00.**

### 1c. The put trade — luck vs configuration

All three trading arms bought P770 within 15 seconds of the 770.24 prior-close break (10:31:53 / 10:32:06 / 10:32:08 ET). Per-contract realized:

| Arm | Entry | Per-contract | vs ORACLE¹ | TP1 config |
|---|---|---|---|---|
| safe-2 | 1.28 | **$125.00** | 82.2% | `tp1_premium_pct=1.0` (+100%) |
| risky-3 | 1.28 | **$103.75** | 68.3% | `tp1_premium_pct=1.0` (+100%) |
| risky-1 | 1.23 | **$59.20** | 37.7% | `exit_patch` at +50% |

¹ **ORACLE** = 1-minute session high (2.80). **Not live-executable. Never mixed into an executable column.**

- **safe-2 vs risky-3 is 100% quote luck.** Identical config, identical entry, identical TP1 trigger level (2.56). At the 12:04 poll safe-2's stream showed bid **2.53**, risky-3's showed **2.56**. risky-3 fired; safe-2 missed by 3 cents, got a second bite at 2.71. **82 of 98 shared polls disagreed by ≥1 cent** (max 9c) between two arms polling the same contract the same minute.
- **$210.00 of today's P&L rode on that 3-cent divergence** (safe-2 −$58 / risky-3 +$152 under swapped streams).
- **risky-1's gap is configuration, not luck.** At +100% TP1 it makes $126.40/ct → +$336.00 instead of +$296.00.
- Luck $210 vs config $336 → **62%.** Per-contract, $21.25 vs $67.20 → 32%. **The TP1-level A/B is underpowered at this n** — the measurement noise is the same order as the effect.

### 1d. Archetype→setup coupling: the diversification is largely illusory

The setups did not mix. Both gap-go days were **pure BULLISH_RECLAIM** (21/21 placements). The single red day was **VWAP_CONTINUATION-dominated** (10/14). Today was **pure BEARISH_REJECTION** — all three arms in the same contract, same direction, same minute.

**Five arms is one bet per day sized five ways.** The book's daily variance is not being reduced by arm count; it is being multiplied by it.

### 1e. Process grade

| Dimension | Grade | Why |
|---|---|---|
| **Entry execution** | **A−** | Three arms in within 15s of a clean prior-close break. The trigger did its job. |
| **Exit execution** | **B+** | All three TP1'd. The −8% stop on the losing call **saved ~$189** vs holding to the bell. |
| **Reconciliation** | **A** | $0.00 unexplained across five arms. |
| **Instrumentation truth** | **D → fixed** | The fill funnel credited a secondary-path fill to the primary pipeline. An entire downstream brief built a false "central question of the day" on it. **Fixed + guarded tonight.** |
| **Evidence hygiene** | **C+** | One lane published a **4× inflated** counterfactual (−$471 vs a realizable −$120) and another committed unreproduced firing-rate numbers into a source docstring. Both caught in review before reaching J — but they were caught, not prevented. |
| **Day, overall** | **B−** | Correct trade, honest money, lying instruments. |
| **Week, as evidence** | **UNDEFINED** | n=4, one day is 98% of it, 3 of 4 days were gap-go/gap-fade (22.5%/15.9% of the 391-day population → ~2× over-sampled), and $210 of today alone was a measurable coin flip. **Consistent with a positive edge AND with three flat days plus one gap-go.** |

---

## 2. The 14:21 long — verdict, and whether filter 5 makes us structurally late

### 2a. The premise was false. Three lanes proved it independently, on the same order id.

`core-decisions.jsonl` row `2026-08-06T14:21:03`, account=safe:
- top-level **`verdict = HOLD`**, `setup = None`, `exec = None`
- `bull_blockers = [5, 11]`
- the real order sits in **`extra_exec[0] = {setup: "bollinger_squeeze", action: "PLACED", broker.id: "b7f663e6-…"}`**
- broker `/v2/orders` → `14:21:55 safe-2 buy 3 @ 1.08 SPY260806C00769000` **id `b7f663e6`** — identical.

**Verdict census for the whole day:** HOLD 763 / ENTER_BEAR 8 / SKIP_BULLISH_FILL_BAR 2 / SKIP_STRUCTURE_VETO 1 = **zero ENTER_BULL**.
**Filter 5 sits in `bull_blockers` on 386/386 armed safe rows and the set is never empty.** Ribbon on live rows: BEAR 296 / MIXED 90 / BULL 0.

The brief's shed sequence `[5,7,10,11] → [5,11] → [5]` is real. **`[5]` was the floor.** There was no "filter 5 finally cleared → fired" event. The trade came from a lane (`heartbeat_core._route_extra_setups` → `setup_dispatch.py`) that **does not consult the numbered bull cascade at all.**

### 2b. Was it a late entry, or a correct entry that lost? Neither, precisely.

Broker truth: buy 3 @ 1.08 (14:21:55) → sell 3 @ 0.96 (14:26:04) = **−$36.00 in 4.2 minutes.**

Priced on real OPRA (396 1-min bars, C769):
- post-entry high **1.10** → best possible was **+$2.00/ct**. It essentially never worked.
- max adverse **−$98/ct**; 15:55 close **−$75/ct**.

**It bought within one cent of the top of the entire move, and the −8% stop — the validated cell for `bollinger_squeeze`, not a defect — saved roughly $189 versus holding to the bell.** Under the primary `ribbon_ride` exit shape the same entry loses **−$144** (ORACLE-labeled counterfactual).

**Bad entry. Excellent exit.** The opposite of the story the brief expected. n=1.

### 2c. Does filter 5 make us structurally late? — CORRECTED FIGURE

Thirteen minutes across the session had `bull_blockers == [5]` exactly. Priced through the **production** exit core (`walk_exit_manager` → `plan_exit_actions`, never the simulator):

| Cluster | Minutes | Cells | First-cell P&L | Cluster sum |
|---|---|---|---|---|
| A | 13:56–14:00 | 5 | **+$24** | −$6 |
| B | 14:16–14:18 | 3 | **−$141** | −$336 |
| C | 14:26–14:30 | 5 | **−$3** | −$129 |

> ❌ **The originally-reported "−$471 total, strictly worse" is a recombination artifact and is withdrawn.** Those 13 cells are overlapping entries on ONE contract; no policy can take all 13. 71.3% of the −$471 came from a single 3-minute cluster.
>
> ✅ **Realizable figure: enter at the first eligible minute of each episode = +24 − 141 − 3 = −$120.00 over 3 trades (−$40/trade).**
> Median individual cell **−$15**, and **8 of 13 cells BEAT the actual −$36.**

**Honest verdict:** at n=1, filter 5 neither clearly saved nor clearly cost money. Per-trade the counterfactual (−$40) and the actual (−$36) are a wash. The strong claim ("filter 5 saved money") dies with the inflated number; the weak claim survives — **there is no evidence here that filter 5 made us late.** Fill-lag sensitivity (next-min open vs decision-min close) moved the total by $6 — stable.

Also note: those 13 counterfactual cells are **BULLISH_RECLAIM** entries at a different strike. Comparing them to a `bollinger_squeeze` trade is apples-to-oranges anyway. The right framing is: *had filter 5 been off, the bull path would have fired 3 episodes for −$120.*

### 2d. 🚨 The fallback lever is not dormant — it was measured and killed

`analysis/recommendations/structure-shift-cascade-ab-2026-07-28.json` A/B'd **the exact staged wiring** over 391 days:

- **VERDICT: DO_NOT_ARM**, delta **−$46.00**, gates **1/5** (only g2)
- g3 delta-minus-best **−$625.00**; g4 two negative preempted days (2025-09-17, 2026-06-25); **g5: the 07-27 anchor the build existed for was NOT captured**
- Pre-reg #1 (standalone predicate) also NULL at 1/5
- The prereg states verbatim that the bull side is a **"proven no-op for entries"**

**Brief correction:** `detect_structure_shift_bull` **does** exist (`backtest/lib/structure_shift.py:126`) and **is** called (`filters.py:1279`). The asymmetry is in the *wiring*: on the bear side the shift is an OR-alternative to filter 5 itself (`filters.py:1495-1503`); on the bull side it only waives a −1 HTF-disagreement score demerit. Bull filter 5 (`filters.py:1173-1175`) is an unconditional `ribbon.stack != "BULL"` test.

**Action: reclassify it in every brief and doc from "dormant capability awaiting quantification" to "MEASURED AND KILLED 2026-07-28."** It has now consumed two sessions of re-derivation.

### 2e. The systemic gap underneath all of this (2nd occurrence → not an incident)

A row's top-level `verdict` describes the **primary path only**. A real broker order placed via `extra_exec` is **invisible to any verdict scan.** `monday_verify.py:342-355` already documents the identical shape on `2026-08-03T13:21:03` (+$67.85). Two occurrences = systemic (**C7 / L244**). This session's own briefing drew a wrong root cause from it and framed a whole lane around a trade the primary pipeline never made.

---

## 3. The two silent arms + the account-type question, stated for one read

### 3a. What the silence cost

**$911.35 combined** — bold-2 $564.90 (qty 5) + safe-3 $346.45 (qty 3), priced on real OPRA through the live `plan_exit_actions`. Against a broker-true day of $1,464.00, the achievable day was **~$2,375** — **the silence was 38.4% of it.**

> ⚠️ The lane's parity check on that number was misstated: it compared a **put-only** replay against safe-2's **full-day net** (which includes the unrelated −$36 call and $0.55 of fees). Correct parity delta is **−$28.55 / −7.6%**, not +$8.00 / 2.4%. Still an acceptable pass, and the error direction is **conservative** — mirroring safe-2's realized exit path gives ~$981 combined. **$911.35 is the floor, not the ceiling.**

### 3b. bold-2 — PDT hard block, confirmed, with new nuance

Ledger: `RISK_DENY_PDT` ×3 at **10:32:48 / 10:34:01 / 10:34:56 ET**, each on `verdict=ENTER_BEAR` with reason *"passed scoring + all entry gates."*

**New nuance the brief did not have:** at **10:31:54** — the exact minute safe-2 filled — bold-2 was blocked by `require_bearish_fill_bar`, *not* PDT. Lifting PDT alone puts it in at ~10:32:48, roughly 45 seconds later than modeled.

### 3c. safe-3 — ❌ THE STANDING ROOT CAUSE IS WRONG

The brief's *"safe-3 = signal-absent, not gates"* held Wednesday. **It is false for Thursday.**

`BEARISH_REJECTION_RIDE_THE_RIBBON` fired and safe-3 logged **`gate: 1 triggers < 2`** for five straight ticks (10:32:04 → 10:36:04), with `setup_name` and `quality=BASE` present on the row. **The signal was there.**

Clean discriminator — same shared signal, same minute:

| Arm | Gate | Outcome |
|---|---|---|
| safe-3 | `min_triggers = 2` | **BLOCKED** |
| risky-3 | `min_triggers = 1` | **+$827.80** |
| risky-1 | full_send | **+$294.55** |

**The gate is the entire difference.** Caveat with teeth: `min_triggers=2` is safe-3's **designed** selectivity as the tight arm, not a bug. One day cannot judge a selectivity knob — the same gate is what keeps it out of chop. **Do not touch it on n=1.**

### 3d. 🎯 THE ACCOUNT-TYPE DECISION — everything J needs, in one block

**The facts, all broker-verified live this session:**

| | safe-2 | bold-2 |
|---|---|---|
| Account | PA3POKNV46VG | PA3WEBXJU67N |
| `pdt_gate_mode` | **`cash_settlement`** | **`margin_pdt`** |
| `multiplier` | **4** | **4** |
| `shorting_enabled` | true | true |
| `regt_buying_power` | 2× equity | 2× equity |
| Equity | $5,727.91 | $5,477.71 |
| Day-trades used (5bd) | **8** | **3** |
| Param doc cites account | `PA3DHPT7KIQE` — **deleted** | `PA33W2KUAT40` — **deleted** |

- `pattern_day_trader` and `daytrade_count` are **entirely absent** from the Alpaca payload — not null, **missing** — which is why `acct.get(...) or 0` yielded a fictitious 0. (This is a deeper root cause than "reads None.")
- **If margin is real: bold-2 is correct and safe-2 is the defect** — safe-2 has taken 8 day-trades in 4 sessions on a sub-$25K margin account behind a gate that structurally cannot see them.
- **Harmless today.** Alpaca paper returns no PDT fields at all, so the broker enforces nothing either way. It becomes a real compliance exposure the moment `GAMMA_CORE_ARMED=1`.
- **The cost of "fixing" it is the whole day.** All three trading arms are already over 3-in-5 (8 / 8 / 9). **Enforcing parity today would have produced $0 instead of +$1,465.** bold-2 is the live control proving exactly that.
- ⚠️ **`fleet_pdt_enforce` is ONE key away from jailing all three fleet arms.** The guard is `bool(params.get("fleet_pdt_enforce")) and bool(arm.get("live"))` — and `live=True` is **already set** on FLEET-TIGHT-S, FLEET-FULLSEND-R and FLEET-LOOSE-R. Flipping that key is not a two-step; it is immediate.
- Forward context: FINRA has approved eliminating the trade-count rule (12-month interim, firms may apply either regime), so bold-2's constraint **may not exist by the time we arm live.**

**Recommendation (yours to overrule):** leave both keys as-is on paper; gate the correctness fix to live-arming. **Neither key was touched.** This is OP-0 #4 — a genuine fork with real money on both sides and a stale premise on both param docs.

### 3e. Fleet arms were never in this conversation

safe-3 / risky-1 / risky-3 emit **no `bull_blockers` field at all** (175/175 rows: `action=HOLD`, *"no qualifying setup (no strategy fired)"*). They run the strategy registry, not the numbered cascade. **Filter 5 cannot explain fleet silence** — different code path entirely.

---

## 4. What SHIPPED vs what is PREREG-only

### 4a. Shipped — code, guarded, RED-proofed, committed

All eight commits verified on disk with `git show <sha> --stat` (L247), all timestamped **16:31–16:49 ET, post-close**. **Nothing pushed.**

| Commit | What | Guard | RED-proof |
|---|---|---|---|
| **3a953a70** | `fill_funnel.py` **fill-provenance split** (`filled_primary` / `filled_extra` / `filled_unattributed`) + **synthetic-row quarantine** (`armed=false` AND `core_tick_id=null` excluded and **disclosed** via `synthetic_core_rows_excluded`, per C7 — never silently dropped) | `test_fill_funnel_guard.py` ×3 incl. the non-vacuous other direction | ✅ mutation 1 → `assert 2 == 1` FAIL; mutation 2 → `assert 0 == 1` FAIL; mutation 3 → `assert 3 == 0` FAIL; source restored byte-identical |
| **57076d38** | `tv_cdp.py` + `draw_key_levels.py` — **headless chart auto-draw + auto-CLEAN**, registered as `Gamma_ChartAutoDraw` (08:35 ET + every 30 min to 16:05). $0, no LLM, no MCP. | `test_draw_key_levels_2026_08_06.py` ×15 | ✅ 5 mutations incl. AST-based `removeAllShapes()` ban |
| **47c79f0b** | `compute_trendlines.py` — lexicographic latest-CSV bug + manual staleness filter + provenance stamps | `test_compute_trendlines_2026_08_06.py` ×8 | ✅ 3 mutations |
| **44578c44** | `hypotheses-settled.json` registry + **`DIAGNOSTIC_COUNTERFACTUALS = {"hold_to_time"}`** ORACLE quarantine in `trade_autopsy.py` | `test_trade_autopsy_settled_oracle_2026_08_06.py` ×16 | ✅ 4 mutations |
| 83dcdadd / 9219b16c / ab86acb7 / 8c8e2ffa | Artifacts + queue entry only | — | — |

**Re-run fresh by me this session:**
- 5 guard suites (`fill_funnel` + `draw_key_levels` + `compute_trendlines` + `autopsy_settled_oracle` + `fleet_pdt_parity`) → **79 passed in 1.73s**
- Curated safety gate → **59 passed, PASS — safe to commit**
- `git status --porcelain` on `params.json`, `aggressive/params.json`, `heartbeat_core.py`, `filters.py`, `CLAUDE.md`, `fleet_live.py` → **empty. Trading path untouched.**

**Scheduler state verified live:** `Gamma_ChartAutoDraw` Ready, last=0, **next 08/07 06:35** (08:35 ET). `Gamma_LaunchTV` / `Gamma_Premarket` / `Gamma_HeartbeatCore` / `Gamma_Trendlines` all Ready, last=0.

#### 🚨 The biggest single fix: the "money left on the table" number was 90.5% fake

`hold_to_time` is a counterfactual with `premium_stop −95% / tp1 999 / runner 999 / qty 1.0` — full position, effectively no stop, held to the time exit. **It wins "best counterfactual" on every trend day by construction** and loses on reversal days. Because `stop_cost_vs_best = max(ALL counterfactuals) − actual`, that structural win *became* the headline number J has been reading weekly.

Across 118 historical autopsy rows: it won on **30 rows (25.4%)** but authored **$62,778.00 of $69,350.80 = 90.5% of the dollars.** Worst single row: actual **−$104.00** → **$7,080.00** claimed.

It was never shippable — **−95% is outside doctrine's −50% catastrophe cap**, and *"hold-longer book-wide"* is already GRAVEYARDED at −$451.50/21. It also contaminated a second hypothesis (`exit_shape_dominated`) fed by the same column. It is now **quarantined, not deleted** — reported separately as `oracle_best_pnl` / `oracle_delta_vs_actual` with a not-shippable note, and the honest `exit_beat_theta` tag still uses it.

#### Chart auto-draw: safety by construction, not by convention

- Touches **only** `horizontal_line` shapes — your trendlines, rays and rectangles are out of reach structurally.
- Removes a line only when provably its own (recorded `entity_id` **OR** a `[G] ` text tag for orphan recovery).
- **Never** calls `removeAllShapes()` — pinned by an AST guard that strips docstrings first (a naive text scan fired on the warning comment itself).
- `--sweep-legacy` is the sole exception, authorized **only** by exact price match against `deprecated_levels`, dry-run unless `--apply`, every removal logged.
- **Idempotency is the actual fix:** three consecutive runs held 50 → 50 shapes (removed 11, drew 11, each time). Before: 43 shapes / 27 horizontal lines accumulated, including your exact complaint — `PMH 732.62` and `PML 728.50` sitting ~$38 below a 768.50 spot.
- Fail-open proven: forcing `CDP_PORT=9999` → `SKIPPED_TV_DOWN`, exit 0, drawn-list preserved.

### 4b. PREREG-only — nothing arms on n=1

| ID | What | Why not shipped |
|---|---|---|
| **PREREG-EXTRA-SETUP-VERDICT-VISIBILITY-2026-08-06** | Emit `verdict=ENTER_EXTRA_<setup>` (or `extra_exec_placed:true`) on any row whose `extra_exec` holds a PLACED with a non-empty `exec.symbol`. Additive field, zero scoring/gating change. Guard: assert both the 08-06T14:21:03 and 08-03T13:21:03 rows are discoverable by a top-level-verdict scan. | ~15 downstream consumers read this ledger. **Needs a blast-radius pass BEFORE the edit, not after.** |
| **Filter-5 population cost** | Price a BULLISH_RECLAIM entry at each `bull_blockers==[5]` release over the 391-day population. | ⚠️ **Under-scoped as filed.** The ledger has **27 such rows in SEVEN clusters** (09:46, 11:26, 11:41, 12:21, 13:56, 14:16, 14:26) — the filed moment list names only the three afternoon ones and would silently drop four morning clusters. **Regenerate the moment list from the ledger before anyone runs it.** Must be CONDITIONAL — "filter-5 deletion" is already graveyarded. |
| **PREREG-BOLLINGER-SQUEEZE-RECENCY-CLOCK-2026-08-06** | Freeze a kill criterion now: n≥8 fills or 10 further sessions, whichever first; negative realized expectancy → `extra_setup_exec_armed.bollinger_squeeze = false`. Mirrors the 07-25 `vwap_continuation` disarm precedent. Live record today: **n=2, +$32.00** (08-03 +$67.85, 08-06 −$36.00). | n=2. |
| **BREAKDOWN-VOCABULARY-GAP** (queue) | The four live setups are all rejections/reclaims requiring price to approach a level and **turn**. A level that breaks and keeps going is untradeable by construction. Prereg names the traps so the naive version isn't rebuilt: **C20/L102/L219** (proximity gates *anti-correlate* with breakouts — every level trigger we own is proximity-based), **C27** (measure population frequency FIRST; levels break constantly, >80% of days = noise), **C28** (ribbon is lagging). | Deliverable is a frozen prereg with frequency measured before any build. |
| **VWAP_CONTINUATION watch** | 17 placements this week, concentrated on the only red session. | Logged so the next session extends rather than rediscovers. n far too small. |

> Today's put worked *because* 770.24 broke and ran — but the engine entered it as a **rejection of the reclaim attempt**, i.e. through the only door we own. We got paid by a breakout using breakout-blind vocabulary.

### 4c. Explicitly NOT done, on purpose

No params changed. No `pdt_gate_mode` key flipped. No gate armed or disarmed. No order placed. Nothing pushed. No trading-path file touched by any commit.

---

## 5. Debts — cleared and still owed

### ✅ Cleared tonight

| Debt | Evidence |
|---|---|
| **FLEET-PDT-PARITY RED-proof** (task #103, owed since 08-06 ship) | Source mutation with market verified closed. Baseline 11 passed @ sha256 `061764f1…8737b46`. **M1** (revert to null broker field, the original defect) → **4 failed** incl. the named regression test. **M2** (enforcement unconditional, C14 dead-knob) → 1 failed. **M3** (fail-CLOSED instead of fail-open) → 1 failed. Source restored **byte-identical** (sha re-verified) → 11 passed. I re-ran it independently: green. |
| **TV watchdog heal verification** (deferred) | Killed **every** TradingView process (0 procs, CDP DEAD) at ~16:26 ET with the market verified closed, ran the real scheduled entry point `run-tv-watchdog.ps1` → **9 procs, new PID 1728 @ 16:27:44 ET, CDP HTTP 200**, still stable at 16:34. Discriminating: pre-fix the child `powershell.exe` never executed a line, so a dead TV could not be revived. Historical bug evidence intact in `tv-watchdog.jsonl` (`relaunch_kill_FAILED` 07-31 15:55, 07-31 16:00, 08-05 08:50). |
| **Recurring autopsy hypothesis** (`stop_inside_noise_floor`, emitted 5× since 07-08, never once run) | Settled registry filed with verdict `REGIME_CONDITIONAL_NOT_SHIPPABLE` + `revisit_condition` requiring a **pre-registered** regime classifier. `HYP_DEDUPE_DAYS=7` is a cooldown, not an answer. |
| **J's chart showing June levels** (2nd ask) | Auto-draw + auto-CLEAN shipped, scheduled, visually verified. Two independent causes found: (a) `key-levels.json` had correctly retired 732.62/728.50 into `deprecated_levels` but **nothing ever removed the drawings**; (b) two June entries were still in the **ACTIVE** array with `draw_needed=true`, ~$35 below spot. |
| **"Trendline feed dead → trigger can never fire"** | ❌ **Refuted.** `detect_trendline_rejection_bearish` computes its line in-process from `prior_bars` and **has never read `trendlines.json`.** It was the **sole trigger** on all 8 ENTER_BEAR rows today and produced **100% of the day's P&L.** The stale file was a separate legacy producer with **zero code consumers**; the live organ (`trendline_engine.py` → `trendlines-live.json`) was fresh at 16:00 ET. |

### ⚠️ Still owed / open

| # | Item | Severity |
|---|---|---|
| 1 | **SWEEP-2:** `exit_shape_parity_study.py#replay_position` omits `structure_stop_enabled`/`trigger_level` from `ExitState.from_entry`, so `stop_mode='structure'` silently degrades to a −20% premium stop. Measured error on today's real trade: **−$76.80 reported vs +$338.45 truth — $415.25, sign flipped.** `structure_stop_enabled=true` in BOTH params files, so **every live core position since v15.3** runs structure mode. Prior studies built on this helper are biased **pessimistic**. Not audited for which. | **HIGH** |
| 2 | **SWEEP-1:** `stop_width_population_grid.py#get_bars` writes its cache CSV **unconditionally after a failed fetch** → a poisoned empty cache that returns 0 bars forever after. Trigger proven live: hardcoded `end={date}T20:15:00Z` lands inside Alpaca's last-15-min embargo on same-day fetches → 403. Same family as L241 but worse — **L241 returned nothing; this persists the nothing.** Two poisoned files deleted and refetched this session. | **HIGH** |
| 3 | **Unidentified writer** injecting `armed=false / core_tick_id=null` synthetic rows (spy 751.0, vix 16.0, spread 10) into production `core-decisions.jsonl` at 04:16:32 ET. Quarantined at the reader; **the producer is unknown.** | MED |
| 4 | **23 horizontal chart lines** of unprovable authorship remain on J's chart, incl. 7 blank-text lines at full float precision (e.g. 737.6775648144016). Chart drawings are not git-revertible → the sweep stops at unprovable authorship. Inspect: `draw_key_levels.py --dry-run --sweep-legacy`. **Needs J.** | MED |
| 5 | **`compute_trendlines.py:15-17` docstring** carries firing-rate numbers (653 fires / 1.69 per day / 2.18% of bars) that **did not reproduce** in review (991 / 2.56 / 3.51% at production constants over the same 387-session population). The **day-level** figure holds (183 days / 47.3% vs claimed 185 / 47.8%). Error direction is conservative — the true rate is *higher*, so the refutation is *stronger* — but unreproduced numbers are now committed as fact with no method note. **Correct or annotate.** | MED |
| 6 | **Stale pre-fix artifact** in `queue.md` line 4099: `T-AUTOPSY-H-2026-08-06-left-on-table` shows `sum_stop_cost: 7718.0`, emitted before tonight's oracle quarantine landed. Won't recur; the number is still sitting there. | LOW |
| 7 | **Settled-registry provenance typo:** `hypotheses-settled.json` lists `H-2026-07-29-stop-noise`; the queue actually holds `H-2026-07-20-stop-noise`. Dedupe matches on `mechanism`, not on the id list, so this is **cosmetic** — but it's wrong in a durable record. | LOW |
| 8 | **SWEEP-3:** `connectivity-gate.ps1:199` and `preflight-gate.ps1:96` both emit `healed = [bool]$Heal` — a verbatim echo of the **request** switch, not any outcome. Mitigated: neither is a gate-logic defect, both compute their real verdict from live node checks, and connectivity-gate also emits a true `tv_heal_action`. (`_shared.ps1:881` does it correctly, from a post-action probe.) | LOW |
| 9 | **`Gamma_ChartAutoDraw` has fired once, manually, through the scheduler chain.** First unattended run is 08/07 08:35 ET. **MONDAY-VERIFY equivalent still owed.** | LOW |
| 10 | **CLAUDE.md account table is stale** — documents `PA3DHPT7KIQE` / `PA33W2KUAT40`; live is `PA3POKNV46VG` / `PA3WEBXJU67N`. Doctrine deliberately not edited by any lane. | LOW |
| 11 | **`compute_trendlines.py` / `trendlines.json` retirement** recommended (zero consumers) but not actioned — a surface-consolidation judgment call, not a bug. | LOW |

---

## 6. Tomorrow — Friday 2026-08-07

### PDT headroom (live, via `pdt_tracker.fetch_day_trades_used_5d`, 17:13 ET)

| Arm | Used (5bd) | Roll-off | Gate mode | **Tomorrow** |
|---|---|---|---|---|
| **safe-2** | 8 | 2026-08-11 | `cash_settlement` (PDT not applied) | ✅ **CLEAR** |
| **bold-2** | 3 | **2026-08-12** | `margin_pdt` — 3/3 used | ❌ **HARD BLOCKED** |
| **safe-3** | 6 | 2026-08-11 | fleet: log-always / enforce-never | ✅ **CLEAR** |
| **risky-1** | 8 | 2026-08-11 | fleet: log-always / enforce-never | ✅ **CLEAR** |
| **risky-3** | 9 | 2026-08-11 | fleet: log-always / enforce-never | ✅ **CLEAR** |

**bold-2 will be silent tomorrow. That is expected and correct under its current key — not a new failure. Do not chase it.**

### What is armed

- **Directions:** BEAR + BULL both enabled on core (`enable_bullish=true`, both params files).
- **Core extra-setups armed:** `bollinger_squeeze` ✅, `vwap_reclaim_failed_break` ✅, `double_bottom_base_quiet` ✅. Disarmed: `vwap_continuation` ❌, `vix_regime_dayside` ❌.
- **Core exits:** `structure_stop_enabled=true`, `tp1_premium_pct=0.5` on safe-2's core path (the `ribbon_ride` registry entry carries its own 1.0).
- **Fleet gates:** safe-3 `min_triggers=2` (tight) / risky-3 `min_triggers=1` (loose) / risky-1 full_send. **Unchanged — deliberately, on n=1.**
- **Scheduler:** `Gamma_LaunchTV` 06:00, `Gamma_Premarket` 06:30, **`Gamma_ChartAutoDraw` 06:35 (first unattended run)**, `Gamma_HeartbeatCore` + `Gamma_Trendlines` 07:30 local. All Ready, all last-result 0.
- **TradingView:** up — 9 processes, PID 1728, CDP port 9222 HTTP 200.

### What to watch

1. **`Gamma_ChartAutoDraw`'s first unattended fire (08:35 ET).** Confirm shape count is stable, not growing, and no June-era prices reappear.
2. **The funnel's new provenance line.** It should now read *"N from primary ENTER verdicts; M from SECONDARY extra_exec […] — NOT a primary ENTER"*. If a fill shows up as `filled_unattributed`, that is a new path nobody has mapped.
3. **`synthetic_core_rows_excluded` > 0** on tomorrow's funnel = the unknown writer is still active. That is the discriminating signal for open item #3.
4. **The first autopsy run post-quarantine.** `stop_cost_vs_best` should drop hard and `oracle_*` should carry the difference. If the headline number stays inflated, the quarantine missed a path.
5. **Whether all four live arms take the same contract again.** Four sessions, four days of ~zero setup diversity (§1d). If Friday is a fifth, the "five arms" framing needs retiring in favor of "one bet, five sizes."
6. **bollinger_squeeze**, if it fires: that is n=3 against a kill criterion nobody has frozen yet.

---

## Appendix — refuted or discarded, do not report as fact

Six load-bearing claims in the incoming brief did not survive re-derivation, plus two lane claims corrected in review:

| Claim | Status |
|---|---|
| "The 14:21 long is the first fire after filter 5 finally cleared" | ❌ **FALSE** — `bollinger_squeeze` on the secondary path; filter 5 never cleared (386/386 rows blocked, 0 ENTER_BULL all day). Order id `b7f663e6` matched across ledger and broker in 3 lanes. |
| "Trendline feed DEAD → `trendline_rejection` can never fire" | ❌ **FALSE** on the causal link — the detector computes in-process and never reads that file. It fired at 10:31 as the **sole** trigger and made 100% of the day. The file is also no longer stale. |
| "bold-2 / safe-3 SILENT, 4th consecutive session" | ❌ **FALSE** — accounts are 4 sessions old; bold-2 traded 08-04 (+$479), safe-3 traded 08-03 and 08-04 (+$782). Both are on **two** consecutive silent sessions. |
| "safe-3 silence = signal-absent, not gates" | ❌ **FALSE for today** — signal present, `min_triggers=2` blocked it 5 ticks running. (Held Wednesday.) |
| "WEEK: Tue/Wed/Thu = +$3,134" | ❌ **INCOMPLETE** — Monday 08-03 (+$534) omitted; broker per-day is 534 / 3,624 / −1,935 / 1,465 = **+$3,688** gross. |
| "DAY +$1,460.80" and its per-arm split | ❌ **UNSOURCED** — matches no P&L producer in the repo. Broker: gross **$1,465.00**, equity Δ **$1,464.00**. |
| Lane claim: "earlier entry is strictly worse, −$471" | ❌ **WITHDRAWN** — recombination of 13 overlapping entries on one contract; 71% from a single 3-min cluster; 8/13 cells beat the actual. Realizable figure **−$120** over 3 episodes. Direction survives, magnitude does not. |
| Lane claim: "silence-cost parity check PASS at +$8.00 / 2.4%" | ❌ **MISSTATED** — compared a put-only replay against a full-day net. Correct: **−$28.55 / −7.6%**, still a pass, error direction **conservative** (true silence cost may be ~$981). |

**Also discarded as a research direction:** `structure_shift_confirmation` as bull-side upside. It is not dormant — it is a completed 391-day A/B with verdict **DO_NOT_ARM** (1/5 gates, −$46, anchor not captured). Any future brief that lists it as untapped capability is re-opening a closed file.

---

*Sources: `EOD-2026-08-06.md`/`.json`, `EOD-2026-08-06-FILTER5.md`/`.json`, `EOD-2026-08-06-SILENT-ARMS.md`/`.json`, `EOD-2026-08-06-INSTRUMENTS.md`. Broker figures, PDT counts, scheduler state, guard suites and safety gate all re-derived live at 17:10–17:15 ET 2026-08-06.*
