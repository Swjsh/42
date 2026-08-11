# Gamma Checklist Gap Map — J's mental checklist vs. the live entry decision

> **Question:** J's framing — "A person needs a whole checklist when they go into a trade: risk
> tolerance, sizing, entries, exits, what's the market doing, what's the VIX doing, are we
> approaching a key level, what does the 4-hour look like, the 15-minute, do we have CPI today."
> Does the live engine actually consult that checklist, item by item, at the moment it decides
> to enter?
>
> **Method:** read-only trace of the LIVE decision path only — `setup/scripts/heartbeat_core.py`
> (core Safe/Bold engine, 1-min tick) → subprocess call into `backtest/lib/engine/engine_cli.py`
> → `backtest/lib/engine/score.py` + `backtest/lib/engine/gates.py` → `backtest/lib/risk_gate.py`,
> plus the fleet fan-out (`automation/state/fleet/fleet_executor.py` + `fleet_live.py`) and
> `automation/state/params.json` / `automation/state/aggressive/params.json`. Every STATUS below
> is backed by a quoted line or an explicit "searched X — absent" note. No files were modified;
> this is the only file this audit wrote.

**STATUS legend:** WIRED-LIVE = consulted by code that runs on every real entry tick.
PARTIALLY WIRED = some slice is live, the rest is dormant/logged/disarmed. SHADOW-ONLY = computed
and stored, never reaches a live decision. ABSENT = no live consumer found.

---

## 1. The gap map

| # | Checklist item | STATUS | One-line verdict |
|---|---|---|---|
| 1 | Risk sizing (per-trade cap, min contracts, equity) | **WIRED-LIVE** | `risk_gate.check_order` is the single authority; called on every entry, both lanes. |
| 2 | Daily loss kill switch | **WIRED-LIVE** | Per-account file latch + realised-drawdown check, both lanes. |
| 3 | PDT / day-trade budget | **PARTIALLY WIRED** | Core: real cash-settlement gate. Fleet: computed but not enforced by default. |
| 4 | VIX level + VIX character/trend | **PARTIALLY WIRED** | Level is a hard gate. 5d/20d MA + intraday-slope character is plumbed but dormant/disarmed. |
| 5 | Key-levels proximity | **PARTIALLY WIRED** | File is read + per-level-expiry checked; a whole-file staleness incident (2026-07-30) shows the freshness check is incomplete; feed is point prices, not zones. |
| 6 | Multi-timeframe context (1m/5m/15m/1h/4h/daily) | **PARTIALLY WIRED (mostly SHADOW-ONLY)** | Only 5m is scored. 15m reaches the free-model prompt as text. Daily/hourly/proper-15m trend-alignment is computed every 5 min and explicitly logged-only. No 4h anywhere. |
| 7 | News / economic calendar (CPI/FOMC/NFP) | **ABSENT** (on the live deterministic path) | Built for the retired prose heartbeat; never ported to `heartbeat_core.py`/`gates.py`. |
| 8 | Trend/regime context (ribbon, market_structure HH/HL/BOS/CHoCH) | **PARTIALLY WIRED** | Ribbon stack is the scoring backbone (live). Only a narrow `classify_trend` slice of `market_structure.py` is live, as a binary veto; the full BOS/CHoCH engine is its own docstring's "telemetry only." |
| 9 | Time-of-day entry gates | **WIRED-LIVE** | Floor/ceiling enforced twice per lane (ladder + `_execute`), plus 4 of the 15 gates are time-window gates. |
| 10 | Spread/liquidity check at entry | **PARTIALLY WIRED** | A raw premium-dollar floor is real and validated. Bid-ask spread/delta/OI thresholds in params are confirmed dead knobs; NBBO is reconstructed but only as telemetry. |
| 11 | Recency/edge-confirmation gating | **PARTIALLY WIRED** | Real, but fleet-lane-only, sizing-clamp-only (never a go/no-go), one strategy family only. Core Safe/Bold path never reads it. |
| 12 | Position correlation / book-level exposure across arms | **ABSENT** | One shared signal fans out to up to 6 independently-gated arms; no code sums exposure across them. |

Detail for each item follows, then the complete verdict-function input list, then the ranked
top-5 ABSENT items by this week's own post-mortems.

---

## 2. Item detail

### 1. Risk sizing — WIRED-LIVE

| Evidence | File:line |
|---|---|
| `check_order()` full signature (equity, start_of_day_equity, proposed_qty, premium, ... params) | `backtest/lib/risk_gate.py:215-230` |
| RISK_CAP / MAX_PREMIUM_TIER rule (notional = premium×qty×100 vs. tighter of the two) | `backtest/lib/risk_gate.py:487-525` |
| MIN_CONTRACTS rule (`qty_i < min_contracts` → deny) | `backtest/lib/risk_gate.py:477-485` |
| Live equity fetched fresh from broker every entry attempt (`/v2/account`) | `setup/scripts/heartbeat_core.py:1909-1915` |
| qty = `params["min_contracts"]`, then clamped by `rg.max_affordable_qty` | `setup/scripts/heartbeat_core.py:2027-2031` |
| `rg.check_order(...)` is the actual call site | `setup/scripts/heartbeat_core.py:2033-2039` |
| `per_trade_risk_cap_pct: 0.3` (Safe) / `0.5` (Bold); `min_contracts: 3` | `automation/state/params.json:271,88`; `automation/state/aggressive/params.json:129` |

Fleet lane: identical authority, called from `fleet_executor.finalize()` inside
`fleet_live.decide_arm()` (`automation/state/fleet/fleet_live.py:380-386`), plus a 2026-08-03
"shrink-not-deny" pre-clamp (`fleet_executor.py:384-413`) that narrows an over-cap tiered qty
down to `max_affordable_qty` before the gate ever sees it — same cap math, no re-typed literal.

### 2. Daily loss kill switch — WIRED-LIVE

| Evidence | File:line |
|---|---|
| `killed = bool(cb.get("tripped")) or (STATE / "kill-switch").exists()` | `setup/scripts/heartbeat_core.py:1948` |
| KILL_SWITCH rule: explicit-bool latch OR `equity <= sod_equity*(1-kill_pct)` | `backtest/lib/risk_gate.py:364-379` |
| `daily_loss_kill_switch_pct: 0.3` (Safe) / `0.5` (Bold) | `automation/state/params.json:272`; `aggressive/params.json:130` |
| Fleet per-arm breaker, armed from live equity at first run each day | `automation/state/fleet/fleet_live.py:150-172` (`_load_or_arm_breaker`) |

Isolation is real (Safe/Bold/each fleet arm reads its own `circuit-breaker.json`), matching Rule
5. One live nuance found in passing: `fleet_live.py` carries a same-night (2026-08-10) fix noting
the kill switch used to *also* freeze the exit-management pass on a tripped arm ("planned but
PLACED NOTHING... The stop-loss stopped working at exactly the moment the account was losing the
most") — now corrected so exits still fire live when tripped, entries stay blocked
(`fleet_live.py:846-863`). Not a gap in this checklist item; noted because it is the most recent
edit to the kill-switch code path.

### 3. PDT / day-trade budget — PARTIALLY WIRED

| Lane | STATUS | Evidence |
|---|---|---|
| Core (safe-2/bold-2) | **WIRED-LIVE** | `pdt_gate_mode: "cash_settlement"` (`params.json:10`); settlement ledger read at `heartbeat_core.py:1944-1947`, passed into `check_order` at `heartbeat_core.py:2038-2039`; gate logic at `risk_gate.py:385-446` (denies when notional exceeds today's still-settled cash, or `same_day_entries_used >= max_same_day_roundtrips`). |
| Fleet (safe-3/risky-1/risky-3) | **PARTIALLY WIRED** | Pinned to legacy `margin_pdt` mode regardless of the core key (`params.json` `_pdt_gate_mode_doc`: "fleet_executor.py's separate arms are EXPLICITLY pinned back to 'margin_pdt'"). The TRUE trailing-5-day count is computed and **logged** every tick (`fleet_live.py:125-147,757-790`, `day_trades_true`/`day_trades_source`) but only **enforced** when `params.fleet_pdt_enforce` (absent/False by default) AND `arm.live` are both true: `enforce_true = bool(params.get("fleet_pdt_enforce")) and bool(arm.get("live"))` (`fleet_live.py:789`). Live comment: "flipping it blind would instantly jail all three arms (6/7/8 >= 3)." |

### 4. VIX level and VIX character/trend — PARTIALLY WIRED

**Level — WIRED-LIVE.**

| Evidence | File:line |
|---|---|
| Gate #15 `vix_bear_hard_cap`: blocks BEAR when `vix_now >= cap` | `backtest/lib/engine/gates.py:415-419` |
| Gate #3 `block_elite_bull` VIX band: blocks ELITE bull inside `[vix_low, vix_high)` | `backtest/lib/engine/gates.py:266-277` |
| `vix_bear_hard_cap: 23.0`; `block_elite_bull_vix_low/high: 0.0/25.0` | `automation/state/params.json:84,196-197` |
| Live VIX fetch (yfinance `^VIX` 5m, now + prior) every tick | `setup/scripts/heartbeat_core.py:326-338` |

**Character/trend — PARTIALLY WIRED (plumbed, dormant/disarmed).**

- `vix_5d_ma`/`vix_20d_ma` are computed (`heartbeat_core.py:341-361`) and threaded all the way
  into `BarContext` (`backtest/lib/filters.py:101-102`), but their only consumer is a **hardcoded
  module constant**, not a params flag: `VIX_DECLINING_REQUIRED_BEAR = False`
  (`backtest/lib/filters.py:44`), which gates the read at `filters.py:1523,1530`. The wiring is
  real; the gate is off at the source, not at params.json.
- `vix_intraday` (median-78 + slope-5, "VIX regime dayside" character) is fetched live only when
  `j_vix_dayside_enabled` (`params.json:132`, currently `true`) and feeds
  `vix_regime_dayside_watcher.py` via the dispatch roster (`setup_dispatch.py:149`) — but
  `extra_setup_exec_armed.vix_regime_dayside: false` (`params.json:94`), disarmed 2026-07-25 on
  real evidence: "5 live trades 0% WR -$153" (`params.json:316-317`). It detects and logs a
  shadow signal every tick; it places nothing.
- `vix_entry_thresholds` (`params.json:77-82`) is self-documented vestigial in its own doc
  string: **"NOT read by the live order-placing path... Do not cite this block as a live VIX
  gate a 3rd time"** (`params.json:82`).

### 5. Key levels proximity — PARTIALLY WIRED

| Evidence | File:line |
|---|---|
| Feed: `automation/state/key-levels.json`, read every tick | `setup/scripts/heartbeat_core.py:412-428` (`_read_levels`) |
| Membership test is a flat **$12 point-distance band**: `abs(p - spy) <= 12`, `p = lv.get("price")` | `setup/scripts/heartbeat_core.py:421-423` |
| Per-level freshness: a level whose `expires_at` is a prior ET date is dropped | `setup/scripts/heartbeat_core.py:393-409` (`_level_expired`) |
| Level-state (role/bounce-history) replay for filter-10 sequence triggers | `setup/scripts/heartbeat_core.py:501-544` |

**What "freshness" does *not* cover:** the check above is per-level (`expires_at`), not
file-wide. The engine's own 2026-07-30 incident writeup, embedded verbatim in the source,
documents that the *whole file* going stale (`Gamma_LevelRefresh` missed a fire, every level
still carried yesterday's `expires_at`) produced `levels_active == []` on 386 of 386 rows for a
full session, and the engine "did not halt, warn, or degrade" — it silently fell back to its
worst-performing trigger family (`heartbeat_core.py:1021-1057`). The fix shipped
(`SKIP_NO_LEVELS` blind-block, `heartbeat_core.py:1060-1104,1351-1402`) refuses a no-anchor entry
when blind; it does not detect or repair file-wide staleness itself.

**Zone vs. price:** the live feed builds a flat list of scalar floats (`round(float(p), 2)`),
not `[lo, hi]` ranges — confirmed at the read site (`heartbeat_core.py:412-428`). Whether
`filters.py`'s downstream touch-detection applies its own tolerance band was not traced in this
pass (out of the explicit file list); flagged here as the load-bearing distinction J's own prior
directive names (`feedback_levels_are_zones_2026_07_17`) but not independently re-verified today.

### 6. Multi-timeframe context — PARTIALLY WIRED, mostly SHADOW-ONLY

| Timeframe | Computed? | Reaches the entry verdict? |
|---|---|---|
| 5-minute | Yes — the entire scoring window | **Yes** — `score_bar`/`evaluate_gates` run on 5m bars exclusively. |
| 15-minute (synthetic, resampled from 5m) | Yes, every tick (`_htf_15m_stack`) | **Soft only.** Reaches the 2-model free-veto prompt as text (`_veto_snapshot`: `"HTF15m={bc['htf_15m_stack']}"`) — an LLM can *veto* on it, but no deterministic gate (`GATE_ORDER`, `GATE_KEYS`) reads `htf_15m_stack`. |
| Daily / hourly / real 15m (trend-alignment via 3-TF vote) | Yes, every ~5 min, off-tick | **No.** Explicitly logged-only. |
| 4-hour | **Never computed anywhere found.** | N/A |

Evidence:
- 15m synthetic stack: `_htf_15m_stack()`, `setup/scripts/heartbeat_core.py:483-492`; consumed
  only in the free-model snapshot string, `heartbeat_core.py:762`.
- Daily/hourly/15m producer: `setup/scripts/context_bundle_producer.py` — docstring: "multi-
  timeframe TREND-ALIGNMENT context bundle... NEVER factors the multi-timeframe trend into
  whether/how strongly it acts" (lines 1-10); runs `crypto.lib.market_structure.analyze_structure`
  on each of 3 timeframes (line 212); fetches `daily(~190d)/hourly(~3wk)/15m(~5d)` bars
  (`context_bundle_producer.py:619-645`). No 4h fetch anywhere in the file.
- The consumer side confirms the wall: `heartbeat_core.py._read_context_bundle` docstring —
  **"this bundle is LOGGED ONLY this phase... nothing on the score/gates/_derive_tier path reads
  it"** (`heartbeat_core.py:436-447`), and the `bar_ctx["context_bundle"]` comment repeats it:
  **"build_bar_context... reads ONLY its own named fields off bar_ctx — this key is never one of
  them... Zero-behavior-change by construction"** (`heartbeat_core.py:650-658`).

**Nearest artifact:** `automation/state/context-bundle.json` (fresh every ~5 min, RTH), and its
per-timeframe engine `crypto/lib/market_structure.py`. Both exist, run, and are already attached
to every decision row — they are simply never read by the code that decides.

### 7. News / economic calendar (CPI/FOMC/NFP) — ABSENT (on the live path)

- Direct grep of `setup/scripts/heartbeat_core.py` for `macro_hard_veto|today-bias|news\.json|
  macro-calendar` returns **zero matches** (the only hit in that file for any of the related
  terms is an unrelated dead-knob comment about `bid_ask_spread_max_cents`).
- The full 15-gate `GATE_ORDER` (`backtest/lib/engine/gates.py:127-143`, read in full) contains
  no calendar/news gate.
- `params.json`'s `macro_hard_veto_minutes` / `macro_soft_modifier_minutes` /
  `macro_soft_bull_threshold` / `macro_soft_bear_threshold` (`params.json:276-279`) are listed,
  by the repo's *own* reconciliation test, as confirmed-dead: **"macro-bias v2; not wired to any
  consumer (RESTORE-or-REMOVE)"** (`backtest/tests/test_params_consumer_reconciliation.py:
  119-123`, the `KNOWN_DEAD` registry).
- **Why the data exists at all:** `setup/scripts/macro_calendar.py`'s own docstring says these
  artifacts were built to feed **"heartbeat filter 2... a hard no-trade veto"** — but that names
  `automation/prompts/heartbeat.md`, the LLM prose heartbeat that `heartbeat_core.py`'s own
  module docstring says was **retired 2026-06-25** ("no LLM on the hot path"). The calendar
  machinery was never re-pointed at the deterministic engine.

**Nearest existing artifacts (all present on disk, all unconsumed by the live gate/score path):**
`automation/state/news.json`, `automation/state/macro-calendar.json`, and
`today-bias.json#news_calendar` (produced by `premarket.md` Step 1b from the same feed).

### 8. Trend/regime context — PARTIALLY WIRED

**Ribbon stack — WIRED-LIVE, the scoring backbone.** `ribbon_now`/`ribbon_history` (fast/pivot/
slow/spread_cents/stack from `backtest/lib/ribbon.py`) drive scoring directly and 2 of the 15
gates (momentum #8, duration #9) walk the ribbon history frame (`gates.py:320-359`).

**`market_structure.py` (HH/HL/BOS/CHoCH) — narrow live slice, rest is shadow.**

- The module's own docstring states its status plainly: **"NOTE (live-wiring blocker): this
  lives in crypto/lib for gym validation + the read-only chart-read skill... Until then this is
  telemetry only."** (`crypto/lib/market_structure.py:29-32`).
- The ONE function actually imported live is `classify_trend()` — a coarse "last two highs +
  last two lows, jointly directional or not" read (`market_structure.py:100-122`) — called from
  `engine_cli._classify_sameday_5m()` (`backtest/lib/engine/engine_cli.py:192-224`), which feeds
  the **structure-veto** gate: `gate_params["structure_veto_enabled"]` = `true`
  (`params.json:309`), applied at `engine_cli.py:633-648`. Effect: block a P(bear) entry in a
  confirmed "uptrend", block a C(bull) entry in a confirmed "downtrend". **By design it does
  NOT veto chop:** `_veto_side()`'s own comment — "range / unknown => NO veto (fail-open;
  preserves 5/04 +$730 range reversal)" (`engine_cli.py:177-189`).
- The rich engine — `walk_structure` (BOS/CHoCH state machine), `label_swings` (HH/HL/LH/LL),
  `analyze_structure` (confidence, event history) — is **not called anywhere on the live entry
  path**. Confirmed absent from `setup_dispatch.py`'s `DISPATCH_ROSTER` (7 named detectors,
  `setup_dispatch.py:145-161`; no market-structure entry) and absent from `gates.py`. Its only
  live-adjacent use is inside the SHADOW-ONLY `context_bundle_producer.py` (item 6).

### 9. Time-of-day entry gates — WIRED-LIVE

| Evidence | File:line |
|---|---|
| `entry_no_trade_before_et: "09:35"`, `entry_no_trade_after_et: "15:00"` | `automation/state/params.json:44-46` |
| Core: floor/ceiling checked in the verdict ladder AND again inside `_execute` (belt-and-suspenders for the extra-setup route) | `heartbeat_core.py:167-202` (defs), `1403-1413` (ladder), `1884-1892` (`_execute` re-check) |
| Fleet: identical mirror functions | `automation/state/fleet/fleet_live.py:430-460` (defs), `488-495` (`_place_live`) |
| 4 of the 15 `GATE_ORDER` gates are time-window gates: `block_bull_1100_1200` (#5), `block_bull_morning_agg` (#6), `midday_trendline_gate` (#10), `block_conf_lvl_rej_midday_afternoon`/`block_conf_lvl_rec_afternoon` (#11-12) | `backtest/lib/engine/gates.py:127-143,284-393` |

### 10. Spread/liquidity check at entry — PARTIALLY WIRED

| Sub-check | STATUS | Evidence |
|---|---|---|
| Raw premium-dollar floor (`min_entry_premium`) | **WIRED-LIVE** | `params.json:48` = 0.3; enforced pre-sizing at `heartbeat_core.py:2016-2026` (`SKIP_MIN_PREMIUM_FLOOR`); own validated evidence cited inline (sub-$0.20 fills cost ~$685/week — `params.json:49` doc). |
| NBBO (bid/ask/spread) reconstruction | **Logged only** | Reconstructed from the SAME mid/entry_px this tick already priced, "purely additive telemetry with zero new network round-trips" — never gates (`heartbeat_core.py:2000-2015`). |
| `bid_ask_spread_max_cents`, `bid_ask_spread_max_pct_of_mid`, `delta_min_abs`, `delta_max_abs`, `liquidity_strike_retries_max` | **ABSENT** | Repo's own `KNOWN_DEAD` registry: **"liquidity gate; not read by order path (RESTORE-or-REMOVE)"** (`backtest/tests/test_params_consumer_reconciliation.py:126-130`). Also self-documented in-line: **"bid_ask_spread_max_cents was a dead knob with zero consumers"** (`heartbeat_core.py:2000-2002`). |
| `open_interest_min` | **ABSENT** | Not in `KNOWN_DEAD` only because a gym validator's docstring mentions the literal string — and that validator's own comment says why it doesn't count: `"open_interest_min": "liquidity threshold, prose-referenced not key-named"` (`crypto/validators/v25_filter_gates.py:104`). No code anywhere reads a live option's open interest. |

### 11. Recency/edge-confirmation gating — PARTIALLY WIRED

| Evidence | File:line |
|---|---|
| Reader: `_recency_verdict()` — tri-state RED/YELLOW/GREEN off `recency-confirmation.json#headline` | `automation/state/fleet/fleet_executor.py:258-296` |
| Effect: `_apply_recency_min_sizing()` — RED clamps qty **down** to `min_contracts`; never a block | `automation/state/fleet/fleet_executor.py:321-351` |
| Scope: `ribbon_ride` strategy only, fleet lane only (`recency_min_size_enabled: true`) | `automation/state/params.json:89-90` |
| Explicit exclusion of the core lane, in the key's own doc: **"heartbeat_core.py's primary-account sizing (min_contracts + max_affordable_qty) does not import fleet_executor and is untouched."** | `automation/state/params.json:90` |

Other files consuming `recency-confirmation.json` — `task_scorer.py`, `autonomy_actuator.py`,
`contender_oos_check.py`, `license_monitor.py` — gate **R&D/capital-allocation** decisions
(which strategies get built/promoted), not live trade entries; not counted as entry-path wiring.

### 12. Position correlation / book-level exposure across arms — ABSENT

- Architecture, in the module's own words: **"Reads ONE shared signal per heartbeat tick... and
  fans it out to every active arm... Each arm applies its own FROZEN policy... on top of the
  shared signal, then the SAME `risk_gate.check_order`... decides whether the order may be
  placed."** (`automation/state/fleet/fleet_executor.py:1-16`).
- `risk_gate.check_order`'s complete parameter list (`backtest/lib/risk_gate.py:215-230`,
  quoted in full under §1 above) contains no cross-account input — no aggregate notional, no
  peer-arm position count, no correlation term. Each call is scoped to exactly one account's own
  equity/kill-switch/flat-state.
- Direct search for a book-level concept (`book_exposure|portfolio_cap|aggregate_notional|
  total_book|combined_risk|correlation`, whole-repo, `*.py`) returns only 2 files, both offline
  one-off research tools (`backtest/tools/exit_leak_decompose.py`,
  `backtest/autoresearch/_b9_cap_aware_rescore.py`) — neither is in the entry/execution path.
  `fleet_executor.py` itself: zero matches for `book|exposure|correlation|concurrent_position|
  max_open|combined_risk` (explicit grep).
- Up to 6 arms trade this signal today (`automation/state/fleet/accounts.json`: `safe-1, safe-2,
  safe-3, bold-2, risky-1, risky-3`, plus 2 futures arms out of scope). This week's own retro
  shows the correlated result in practice, even though it isn't framed as a "book exposure"
  defect: **"every arm green"** (08-04, +$3,624) and **"every arm red"** (08-07, −$2,687)
  (`analysis/deep-research/2026-08-11-audit/TWO-WEEK-ENGINE-RETRO.md:12,15`).

**Nearest artifact:** none. The closest analog is the *per-account* `circuit-breaker.json` files
(`heartbeat_core.py:1907`, `fleet_live.py:150-172`) — each stops ONE arm after ITS OWN daily
loss; nothing sums them.

---

## 3. Complete input list — the core engine's verdict function

"The verdict function" = `backtest/lib/engine/engine_cli.py::decide_payload()`, invoked as a
subprocess from `heartbeat_core._engine_verdict()` (`heartbeat_core.py:703-711`, `python -m
backtest.lib.engine.engine_cli`, payload piped via stdin). The payload is assembled entirely by
`heartbeat_core._build_payload()` (`heartbeat_core.py:578-700`). Its return value is the complete
input surface — nothing else reaches the verdict:

```python
# heartbeat_core.py:698-700
return {"bar_ctx": bar_ctx, "gate_params": gate_params, "score_params": score_params,
        "spy_df": bars_all, "ribbon_df": ribbon_series,
        "sameday_5m_bars": sameday_5m_bars}
```

| Top-level key | Contents | Built at |
|---|---|---|
| `bar_ctx` | see table below | `heartbeat_core.py:635-659` |
| `gate_params` | the 18 `GATE_KEYS` pulled from `params.json` (block_level_rejection, trendline_requires_ribbon_flip, block_elite_bull(+vix band), block_bull_ribbon_flip, block_bull_1100_1200, block_bull_morning_agg, require_bearish_fill_bar, min_ribbon_momentum_cents, max_ribbon_duration_bars, midday_trendline_gate, block_conf_lvl_rej_midday_afternoon, block_conf_lvl_rec_afternoon, entry_bar_body_pct_min(+_bull), vix_bear_hard_cap, structure_veto_enabled, structure_shift_confirmation_enabled) | `heartbeat_core.py:135-151` (list), `:660` (built) |
| `score_params` | `enable_bullish` (hardcoded `True`); `bear_kwargs`/`bull_kwargs` = time window + `f9_vol_mult`/`f10_vol_mult` + `min_triggers` | `heartbeat_core.py:663-671` |
| `spy_df` | full 150-bar OHLCV window (list of dicts, no timestamps) — feeds gate #7 (look-ahead fill-bar) | `heartbeat_core.py:594-598,613,699` |
| `ribbon_df` | full ribbon series aligned to the window — feeds gates #8-9 (momentum/duration) | `heartbeat_core.py:598-599,699` |
| `sameday_5m_bars` | today's 5m bars through the trigger bar, WITH timestamps — feeds `structure_veto`'s `classify_trend` | `heartbeat_core.py:672-687` |

`bar_ctx` fields (built `heartbeat_core.py:635-659`; validated 1:1 by
`engine_cli.build_bar_context`, `engine_cli.py:368-442`):

| Field | Meaning | Reaches scoring/gates? |
|---|---|---|
| `bar_idx`, `timestamp_et` | trigger-bar index + ISO timestamp (2nd-to-last fetched 5m bar) | index only |
| `bar` (O/H/L/C/V) | the trigger bar itself | **yes** — the entry bar |
| `prior_bars` | history through the trigger bar (no look-ahead) | **yes** — scoring window |
| `ribbon_now`, `ribbon_history` | fast/pivot/slow/spread_cents/stack, current + last 3 | **yes** |
| `vix_now`, `vix_prior` | spot VIX, this bar / prior bar | **yes** (gates #3, #15) |
| `vol_baseline_20`, `range_baseline_20` | 20-bar trailing means | **yes** (filter-9/10 volume checks) |
| `levels_active`, `multi_day_levels` | key-levels.json, $12-band, non-expired | **yes** |
| `htf_15m_stack` | synthetic 15m ribbon resample | **no** — free-model prompt only (item 6) |
| `level_states`, `fhh_level` | replayed role/bounce-history + first-hour-high | **yes** (filter-10 sequence triggers) |
| `vix_5d_ma`, `vix_20d_ma` | prior-day VIX MAs | **plumbed, gate hardcoded off** (item 4) |
| `context_bundle` | daily/hourly/15m trend alignment | **no** — logged only (item 6) |
| `vix_intraday` | median-78+slope-5 VIX series (only if `j_vix_dayside_enabled`) | feeds a shadow-only extra-setup detector (item 4) |

**What is never in this payload at all:** an account's equity, kill-switch state, day-trade
count, or settled cash (those are resolved later, only for the winning side, inside `_execute`);
any other arm's position or exposure; news/calendar state; option bid/ask/delta/OI; anything
above 15-minute resolution.

---

## 4. Top 5 ABSENT/effectively-absent items, ranked by this week's own post-mortems

Ranked against `analysis/deep-research/2026-08-11-audit/TWO-WEEK-ENGINE-RETRO.md` §6 "Open
defects, ranked" (this week's dated, dollar-quantified record) plus this session's own findings.
Ranks 1-2 are directly named with dollar figures in that retro; ranks 3-5 are structural
absences confirmed by code this session that the retro does not yet dollar-quantify — stated
honestly as such, not force-fit to a number that isn't there.

| Rank | Gap-map item | This week's evidence | Mechanism link |
|---|---|---|---|
| **1** | **#8 Trend/regime context — chop discrimination** | Retro defect #1: **"Chop-day entries — the single largest loss driver (08-07 −$2,687; 08-11 mid-day −$636)... ER30 is the candidate discriminator; shadow only, 0/25"** (`TWO-WEEK-ENGINE-RETRO.md:70-71`). | `structure_veto`'s own design explicitly passes chop through: *"range / unknown => NO veto"* (`engine_cli.py:177-189`). The one candidate regime discriminator (ER30) is shadow, 0-for-25 forward days. This is the most expensive named gap this week and it is mechanically the same hole this audit's item 8 found. |
| **2** | **#6 Multi-timeframe context (esp. daily/hourly trend continuation)** | Retro defect #3: **"Trend-continuation blindness — 113 consecutive no-setup ticks while SPY fell 1.6 pts"** (`TWO-WEEK-ENGINE-RETRO.md:74`). | The engine's setup family is rejection/reclaim-at-a-level only; it has no "ride an established trend with no fresh level touch" trigger. The one signal that would name a continuation regime — `context_bundle`'s daily/hourly/15m alignment vote — is computed every 5 min and is, by its own producer's docstring, explicitly excluded from acting: *"NEVER factors the multi-timeframe trend into whether/how strongly it acts"* (`context_bundle_producer.py:8`). |
| **3** | **#12 Book-level exposure / correlation across arms** | Not named as a $ defect in this week's retro by that title, but this is the concern named in this task's own framing ("all-arms-same-signal pile-ins"), and the retro's daily table shows the mechanism firing both ways: **"every arm green"** (08-04) / **"every arm red"** (08-07) (`TWO-WEEK-ENGINE-RETRO.md:12,15`); defect #4, **"safe-3 took zero trades 08-11 — unexplained; a fifth of the book idle"**, is the inverse (participation, not pile-in) symptom of the same missing book-level view (`TWO-WEEK-ENGINE-RETRO.md:75`). | One shared perception, N independently-gated arms, zero aggregate cap (§2 item 12). Real dollar cost this week is not separately broken out from the correlated per-arm P&L above — flagged honestly as inferred risk, not a measured loss line. |
| **4** | **#7 News/economic calendar awareness** | No specific dollar loss surfaced in the files read this session; included because it is a complete, zero-consumer gap on a named CLAUDE.md checklist item (rule 1, "no setup, no trade" implicitly assumes the setup accounts for known catalysts) and has prior documented history: `macro_calendar.py`'s own motivating incident describes a **3+ week** blind spot before this producer even existed. | The producer exists and runs; it was built for, and only ever wired to, the retired LLM heartbeat. Zero-cost, mechanical fix (thread `today-bias.json#news_calendar`/`macro-calendar.json` into a 16th `GATE_ORDER` gate) is unshipped. |
| **5** | **#4/#10 VIX character + liquidity/delta/OI thresholds** | Not named in this week's top defects; the two items are grouped here because both are "half-built, mostly dead-knob" gaps of similar (lower, so far) measured urgency — VIX *level* is already a hard live gate, and premium liquidity is already proxied by the validated `min_entry_premium` floor, so the missing pieces (VIX-MA/slope character, bid-ask/delta/OI) are refinements, not open holes. | `VIX_DECLINING_REQUIRED_BEAR = False` hardcoded (`filters.py:44`); 6 liquidity params confirmed dead by the repo's own reconciliation ratchet (§2 item 10). |

---

## Files read (evidence provenance)

`setup/scripts/heartbeat_core.py` (full, 2488 lines) · `backtest/lib/risk_gate.py` (full,
1042 lines) · `backtest/lib/engine/gates.py` (full, 423 lines) ·
`backtest/lib/engine/engine_cli.py` (full, 755 lines) · `crypto/lib/market_structure.py` (full,
281 lines) · `automation/state/fleet/fleet_executor.py` (to line 906/1330) ·
`automation/state/fleet/fleet_live.py` (full, 962 lines) · `automation/state/params.json` (full,
318 lines) · `automation/state/aggressive/params.json` (targeted grep) ·
`backtest/lib/filters.py` (targeted) · `backtest/tests/test_params_consumer_reconciliation.py`
(full) · `crypto/validators/v25_filter_gates.py` (targeted) · `setup/scripts/setup_dispatch.py`
(targeted) · `setup/scripts/context_bundle_producer.py` (targeted) ·
`setup/scripts/macro_calendar.py` (targeted) ·
`analysis/deep-research/2026-08-11-audit/TWO-WEEK-ENGINE-RETRO.md` (targeted, for §4's ranking
evidence only). No file outside this deliverable was written.
