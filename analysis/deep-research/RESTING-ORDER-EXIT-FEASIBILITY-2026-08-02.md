# Resting-order exit feasibility — 2026-08-02

**Question:** can the polled exit trigger become a resting broker order, collapsing the sampling gap (`analysis/pain-ledger/sampling-gap.json`, $2,793.30 measured) to zero for whatever it covers?

**Verdict: PARTIAL YES on capability, NO-SHIP tonight.** Alpaca's options endpoint accepts `stop` and `stop_limit` order types LIVE — this contradicts Alpaca's own docs, which name only market/limit as supported. `trailing_stop` is genuinely rejected. This makes a resting-order mirror **mechanically possible** for the two static/discretely-ratcheted stop stages (premium_stop + be_stop, $2,261.60 of the $2,793.30, 81%), **not directly possible** for the continuously-ratcheting chandelier trail via a native trailing-stop type ($531.70, 19%) — that leg would need manual periodic re-pricing, which reintroduces a smaller version of the same staleness problem. Nothing is armed. This report is the evidence base for a J-reviewed shadow-mode pre-registration, not a ship.

---

## 1. Broker capability — docs vs live reality

### 1.1 What Alpaca's docs say (quoted)

`mcp__alpaca__fetch_alpaca_doc("us/options-trading-overview")`, section "Trading Overview":

> **Supported:** Options symbol · Time in force of day · **Market and limit order types** · Ability to replace and cancel orders · Level 1 + 2 option strategies
>
> **Not supported:** Extended hours · Fractional or notional order support

The options-specific error table on the same page lists, among the `POST /v2/orders` (single-leg) rejection reasons: `invalid option order_type` / `invalid options order_type` / `invalid order type for options trading` (all HTTP 422, code `42210000`) — consistent with a narrow allow-list. The MCP tool's own `place_option_order` schema independently encodes the same belief: `type` is documented as `"market" or "limit"` only, and `time_in_force` as `"day" only`.

**Docs verdict as written: only `market` and `limit` are supported for options. No `stop`, `stop_limit`, or `trailing_stop`.**

### 1.2 What the live broker actually does (the decisive test)

Docs turned out to be **incomplete**. Live PAPER test against fleet arm `safe-1` (account `1160.24` equity, ACTIVE), canary symbol `SPY260803P00650000` (0DTE-Monday $650 put, ~$90 OTM given SPY's mid-$740s range that week, real close $0.01 — chosen to be inert even if accidentally marketable), qty=1, BUY side (isolates order-TYPE validation from position/coverage checks):

| Order type | HTTP | Result | Quoted response |
|---|---|---|---|
| `stop` (stop-market) | 200 | **ACCEPTED**, `status: "accepted"` | `order_type: "stop"`, `stop_price: "0.02"`, `expires_at: "2026-08-03T20:15:00Z"` |
| `stop_limit` | 200 | **ACCEPTED**, `status: "accepted"` | `order_type: "stop_limit"`, `stop_price: "0.02"`, `limit_price: "0.03"` |
| `trailing_stop` (trail_price form) | 422 | **REJECTED** | `{"code": 42210000, "message": "invalid order type for options trading"}` |
| `trailing_stop` (trail_percent form) | 422 | **REJECTED** | same code/message — not a parameter-form issue, the type itself is blocked |
| `limit` (positive control) | 200 | ACCEPTED (expected — proves the harness/creds/symbol aren't the reason anything else failed) | `order_type: "limit"` |

Every accepted order was cancelled within the same script run (`DELETE /v2/orders/{id}` → HTTP 204) and independently re-verified flat afterward (see §1.4).

**Differential probe (SELL-to-open, same symbol/types)** — checks *where* in the pipeline each type fails, since a shallow accept could still mean "accepted-and-ignored":

| Order type | HTTP | Result |
|---|---|---|
| `stop` | 500 | `{"code": 50010000, "message": "internal server error occurred"}` — an unhandled server-side case on this specific (uncovered-short × stop-type) combination, **not** a clean type-rejection. Flagged as a vendor-reliability signal, not evidence against the mechanism — see §1.3. |
| `stop_limit` | 403 | `{"code": 40310000, "message": "insufficient options buying power for cash-secured put (required: 64996.92, available: 1160.24)"}` — this is the **real cash-secured-put collateral calculator** ($650 × 100 × 1 = $65,000, matches to the dollar) computing a genuine business-logic answer. This order type reached deep, options-specific logic — strong evidence it is substantively processed, not accepted-and-discarded. |
| `trailing_stop` | 422 | Same clean `invalid order type for options trading` as the buy side — uniform rejection regardless of side. |

Raw transcripts: `backtest/tools/_canary_option_order_types_2026_08_02.py` (reproducible — re-run any time) → `analysis/deep-research/_canary_option_order_types_2026_08_02.result.json`.

### 1.3 Reading this honestly (this is a "too good" result — treated accordingly)

An undocumented capability accepted live, on the first try, on the exact mechanism the task needed, is exactly the shape of result that deserves suspicion before celebration. What was and wasn't checked:

- **Confirmed:** the order-entry validation layer accepts `stop`/`stop_limit` for a single-leg option order and processes them deep enough to run real business logic (the cash-secured-put buying-power check on the sell-to-open probe).
- **NOT confirmed — market was closed (Sunday) all session:** whether a resting `stop` order actually **triggers** correctly when the option's own last trade/quote crosses `stop_price`, what price reference it triggers against (own NBBO vs last trade — undocumented, since the docs don't even acknowledge the type exists), what happens in a real fill, and whether triggering converts to a marketable order the way equity/crypto stops do. Acceptance is necessary but **not sufficient** proof of a working mechanism.
- **NOT confirmed:** identical behavior on **sell-to-close of a real long** (the actual production use case). The BUY-side test cleanly isolates order-type validation (no coverage confound) and the SELL-to-open probe shows `stop_limit` reaching options-specific logic on the sell side too — both support the type being genuinely side-agnostic at the validation layer — but neither is a literal sell-to-close test, which requires an open position, which requires a fill, which requires market hours. Disclosed gap, not glossed over.
- **A genuine new data point, not a clean one:** the plain `stop` sell-to-open 500'd instead of cleanly rejecting or accepting. Undocumented features that 500 on some input combinations are a real signal that this code path is not fully hardened on Alpaca's side. This is a vendor-reliability argument *for* caution, independent of anything in our own design.
- **Paper vs production:** this was tested on Alpaca PAPER only (per project scope — paper is all this account trades). A paper sandbox occasionally has different validation than production; no specific evidence of that here, but it's an unverified assumption this finding rests on.

**Bottom line: the capability is real enough to design around, not proven enough to trust blind.** That is exactly the shape of finding that should produce a shadow-mode plan, not a ship.

### 1.4 Flat-verification (no order left resting)

Independent second check, via a fresh Python process (not the test script's own self-report):

```
all open SPY-option positions on safe-1: NONE
ALL open orders on safe-1 (any symbol): [] (none)
```

Confirmed after both the primary run and the consolidated re-run in `backtest/tools/_canary_option_order_types_2026_08_02.py`.

---

## 2. Mechanical analysis — why this isn't just "add a bracket leg"

The naive version of this idea — mirror the stop as a plain resting **limit** sell — is a dead end for a structural reason worth naming, because it's what most people reach for first: a limit sell order priced *below* the current market is, by definition, immediately marketable (it crosses the book right away, at whatever the current bid is) — not a dormant order waiting for price to fall there. `fleet_broker.marketable_limit_price()`'s own docstring already encodes this same fact from the other direction ("a sell uses bid − buffer" to force a fill). A plain limit order can only passively wait for a **favorable** move (a take-profit, priced above market); it cannot express "wait for an adverse move, then exit" — that's what a genuine conditional order type (`stop`/`stop_limit`) is *for*. This is why §1's live test — not the docs, not inference from our own code's bracket-rejection history — is the only way to answer the question: the docs said the needed primitive doesn't exist for options; it does.

All four scored exit stages in `exit_manager.py` are exactly this "adverse-move" shape — `plan_exit_actions` checks `worst_premium <= runner_stop` for `premium_stop`/`profit_lock_floor` (pre-TP1) and `worst_premium <= new_runner_stop` for `trail`/`be_stop` (post-TP1) — confirmed by reading the source this session (`automation/state/fleet/exit_manager.py:412`, `:508`). None of them can be expressed as a plain resting limit. All of them *can* be expressed as a resting `stop`/`stop_limit`, mechanically, per §1.

---

## 3. Design: the hybrid, and its failure modes

### 3.1 The honest shape (as the task anticipated)

`exit_manager.plan_exit_actions` stays the brain — unchanged, unedited (it is read-only for me this session and I have not touched it; `git status --porcelain` on it is clean both before and after this research). It still computes the chandelier floor, TP1, catastrophe cap every tick. The change would be additive: when a `RATCHET_STOP` action is emitted, instead of only persisting the new level in-memory (today's behavior — see §3.2), also mirror it as a resting `stop` (or `stop_limit`, for slippage-bounding — see §3.3) order on the broker, amended via `PATCH /v2/orders/{id}` (`replace`) when the floor ratchets. `fleet_broker.replace_stop_order()` already exists with exactly this signature — see §3.2.

### 3.2 A load-bearing fact this research turned up: the current architecture deliberately chose NOT to do this

`exit_actuator.py:300-308`, on handling `RATCHET_STOP` today:

> "The runner stop ratchet is realized lazily: we PERSIST the new stop level in the ExitState and let the per-tick worst<=stop check enforce it (**a tick-managed stop, not a resting broker order**), so no order_id plumbing is required and **a missed tick can't strand a stale resting stop**."

`fleet_broker.replace_stop_order()` — the PATCH-based primitive a resting-order design would need — already exists in the codebase and is **currently unused** (dead/vestigial, per house convention C14). This isn't an oversight: the comment states the rationale explicitly, and it is *precisely* the failure mode the task asked me to evaluate (§3.4, item 4). Adopting a resting-order mirror doesn't just add a feature — it deliberately **reverses a considered past design decision** that traded sampling-gap cost for operational simplicity. That trade-off should be named to J explicitly, not smuggled in as a pure upgrade.

### 3.3 Guardable vs genuinely new risk (per failure mode named in the task)

| Failure mode | Verdict | Reasoning |
|---|---|---|
| **A resting stop can be picked off by a spread blip a polled check would have ridden through.** | **Genuine new risk, not eliminated, partially mitigated.** The *current* system already decides off a single NBBO snapshot (`fleet_broker.get_option_quote_hilo` — one `(ask, bid)` read per tick, confirmed in `exit_manager_walk.py`'s docstring and `exit_actuator.py:254-260`), so this isn't a new *kind* of risk — it's a new *frequency*: from ~131 discrete looks (this dataset's whole exit population) to continuous exposure, all day, for every open position. Using `stop_limit` instead of plain `stop` bounds the worst fill price (at the cost of a "held," unfilled position if the market gaps clean through the limit floor — a different failure, not a free lunch). **Not quantified this session** — see §4. |
| **An amend that races a fill can double-exit or leave a naked order.** | **Guardable, with existing house patterns.** Alpaca's own replace endpoint is defensive here: the documented replace-error table includes `cannot replace order in {status} status` / `order already replaced` — a race gets rejected, not silently corrupted. The actuator must treat a replace rejection as "re-derive truth from the broker," never "assume it worked" — exactly the `symbol_position_qty_checked()` / `open_buy_orders_checked()` pattern **already shipped this session** (`fleet_broker.py`, dated 2026-08-02, "ORDER-LEVEL IDEMPOTENCY GUARD") for the entry side. Extending that pattern to a resting-exit-order actuator is consistent with a convention this exact codebase just finished establishing, not a new invention. |
| **A stale resting order after a TP1 partial-fill has the wrong quantity.** | **Guardable, but with a real non-zero window.** The replace-error table's `qty must be > filled_qty` implies qty is a legitimate replace parameter, so a TP1 fill can be followed by one PATCH that both re-sizes and re-prices the resting order to `runner_qty`. The window between the TP1 fill and that PATCH landing is real and cannot be shrunk to zero — must be disclosed as a residual risk, not solved away. |
| **The engine must never end the day with an unmanaged resting order.** | **Strongly guardable — mostly already true by construction.** Options order `time_in_force` supports `"day"` **only** (confirmed both in the docs and in every accepted response's own `expires_at` field — e.g. `"2026-08-03T20:15:00Z"`, ~15 min past the 16:00 ET close for settlement). Any resting stop auto-expires same-day regardless of our own code. Belt-and-suspenders: an explicit pre-close cancel of any known-open exit orders (via `cancel_all_orders` or a symbol-scoped cancel) ahead of `Gamma_EodFlatten` would remove reliance on the vendor's own expiry as the *only* backstop — cheap to add, should be part of any real design. |

### 3.4 What I will NOT propose tonight

No diff to `exit_manager.py`, `exit_actuator.py`, or `fleet_broker.py`. No flag flip. Per task scope, this section is a design **sketch** for J's REVOKE surface, not a build.

---

## 4. Capturable dollars — honest, stage-by-stage, netted against an unquantified cost

Re-derived fresh this session (not read stale from disk): `python setup/scripts/sampling_gap_ledger.py` re-run produced a byte-identical result to the committed file except the `_meta.generated_at_et` timestamp (`git diff` confirms — every dollar figure, every count, every one of the 131 scored events matches exactly). This is the RED-proof for every number below.

| Stage | n | sampling_gap_$ | Mirrorable via resting `stop`/`stop_limit`? |
|---|--:|--:|---|
| `premium_stop` | 121 | $2,257.60 | **Cleanly.** Static per position — set once at entry, ratcheted at most once (to breakeven) at TP1. A resting order's freshness is not a concern; only "did we notice the cross in time" was ever the problem, and that's exactly what a resting order fixes. |
| `be_stop` | 1 | $4.00 | Same shape as `premium_stop` (single discrete ratchet). Statistically meaningless alone (n=1) but structurally identical, so bucketed with it. |
| `trail` | 9 | $531.70 | **Partially / uncertain.** Chandelier — ratchets continuously with the HWM. A resting mirror only reflects the LAST level we bothered to PATCH-replace; between reprices it can be *more generous* than the freshly-computed floor would want, giving back some profit on the ratchet-staleness side even as it fixes the trigger-miss side. The ledger's `sampling_gap` field doesn't decompose these two effects — I cannot honestly split this $531.70 further without inventing a number. |
| `profit_lock_floor` | 0 | $0.00 | Never fired in this history (empirically moot), but structurally identical to `trail` (continuous ratchet) — the $0 is a fact about this dataset, not a property of the mechanism. |
| **Total** | **131** | **$2,793.30** | — |

**Cleanly-capturable ceiling: `premium_stop` + `be_stop` = $2,261.60 (81.0% of the measured leak).**
**Uncertain, needs a real measurement to resolve: `trail` = $531.70 (19.0%).**

**Netting against pick-off risk (§3.3, row 1): I do not have a dollar figure for this, and I am not going to invent one.** The $2,261.60 ceiling assumes zero pick-off cost and zero operational-failure cost — it is an **upper bound on the win**, not a forecast. The honest reason I can quantify the upside but not the downside from tonight's data alone: nobody has built a "how often does the NBBO tick through a level and immediately recover" counter against this book's real tick history yet. That is the single most valuable thing a shadow-mode run would produce — it measures both effects simultaneously from the same real tape, instead of modeling them separately from partial data.

---

## 5. Blast radius — 5-minute option-bar cache used for exit-walk purposes

**Verified mechanism (not re-diagnosed — this is a previously-documented, already-quantified issue):**

- `backtest/lib/option_pricing_real.py` reads `backtest/data/options/{symbol}.csv`, populated at **5-minute** granularity (`backtest/tools/fetch_option_data.py:75` and `expand_opra_cache.py:175` both fetch `"timeframe": "5Min"`; the module's own `OptionBar` dataclass docstring: *"One 5-min bar from the option chain."*).
- This is the **root** of the exposure. Two shared "walk" engines are built directly on it: `backtest/lib/simulator_real.py` (+ `simulator_real_trailing.py`, `simulator_debit.py`, `simulator_credit.py`) and `backtest/lib/exit_manager_walk.py` — the latter's own docstring names the ceiling explicitly: *"1-minute for today's real fills, 5-minute for historical backtests where only 5-min OPRA is cached."* Even the harness built to FIX the exit-fidelity problem (iteration 6 of GOAL-REPLAY-TODAY-GREEN, below) still inherits 5-min resolution for any non-today historical backtest.

**Already known and quantified — `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` (2026-07-17, iterations 2/3/6):** at 5-min resolution, `simulate_trade_real`'s profit-lock/stop model zeroed 3 of 5 `core_safe` entries to exactly $0.00 that live ran to +$241/+$105/−$56. Re-running at 1-min resolution (iteration 3) made it *worse* (5/5 zeroed), later root-caused (iteration 6) as `simulate_trade_real` reading the WRONG exit shape entirely — "a DEEPER divergence than the 5-min vs 1-min bar gap... not an approximation of the right shape, the WRONG shape entirely." `exit_manager_walk.py` was built specifically to fix this by driving the REAL `exit_manager.plan_exit_actions` on real 1-min OPRA bars, achieving 6/6 faithful for today's replays.

**Already partially mitigated — tonight's own sibling lane:** `backtest/tools/level_target_exit_study.py` (`RESOLUTION FIX` docstring, this session) independently root-caused the *exact* citation in this task's prompt — verified on `SPY260709C00750000`/risky-3: "the real position stopped out on a dip to $0.40 inside a 5-min bar whose own open was $0.52... a $475 phantom gain in the harness alone" — and fixed it for its own population by preferring a 1-minute fetch with a disclosed 5-minute fallback (`load_option_bars(..., prefer_1min=True)`).

**Scale (measured, not guessed):** `simulator_real` is referenced by **~250+ `.py` files** (capped at the query limit — the true count is higher); `option_pricing_real` is imported **directly** by **108 files**. This is effectively the entire `backtest/autoresearch/` + `backtest/tools/` R&D corpus — hundreds of one-shot study scripts spanning weeks — and every OOS/WF number in `analysis/recommendations/*.json` that was computed via `simulator_real` or an un-1-min-patched `exit_manager_walk` call ultimately traces back to this cache. Enumerating all ~250+ with individual one-liners would be noise, not signal; the risk is systemic, not file-specific. Named below are the highest-**stakes** consumers — ones whose conclusions are currently load-bearing in live doctrine or were the direct subject of tonight's other work, not an exhaustive list:

| File | One-line risk |
|---|---|
| `backtest/tools/structure_stop_study.py` (69 importers) | Feeds `structure_stop_enabled`, the **LIVE** v15.3 chart-stop-primary flag in both `params.json` files — a 5-min-bar softness here is the highest-stakes single item on this list. |
| `backtest/tools/ribbon_ride_strike_exit_ab.py` (38 importers) | SS-B lineage — basis for the currently-LIVE chandelier trail / `tp1_qty_fraction` knobs cited in CLAUDE.md's strategy header. |
| `backtest/tools/arm_score_ladder_replay.py` | Harness behind the SCORE LADDER arms doctrine (CLAUDE.md absorbed lesson, J 2026-07-27) — a live fleet-parallel A/B structure. |
| `backtest/tools/pong_resting_limit_study.py` + `_pong_prereg_builder.py` | Tonight's own sibling research (both accounts KILLED) — used `load_contract_bars` for its own exit replay; if it had cleared, that verdict would inherit this exact softness. |
| `backtest/tools/bold_fullhist_replay.py`, `engine_fullhist_replay.py` | Full-history "state of the book" replays — broad-scope conclusions built on the 5-min cache throughout. |
| `backtest/tools/exit_variant_ab.py`, `trail_width_exit_ab.py`, `catastrophe_stop_shakeout_ab.py`, `class_conditional_exits_ab.py`, `t4_exit_matrix.py` | Exit-shape-focused A/B studies — directly about stop/trail mechanics, so directly and specifically exposed to this exact resolution gap. |
| `analysis/recommendations/*.json` (≈100+ files) | Every ratification scorecard produced by a tool above inherits the same softness transitively — not fixed individually here, just named as the downstream ledger to treat with the appropriate discount. |

Not fixed — surfaced only, per task scope.

---

## 6. Recommendation

1. **Do not arm anything.** Nothing on the live exit path changed tonight; `exit_manager.py` remains untouched (verified clean before and after).
2. **If J wants to pursue this:** the next step is a **shadow-mode pre-registration** — mirror the resting `stop`/`stop_limit` order alongside (never instead of) the current poller, for N sessions, comparing what the resting order *would have* filled against what the poller *actually* got, on `premium_stop`/`be_stop` positions only first (the cleanly-mirrorable 81%). That single dataset answers both open questions from §1.3 and §4 at once: does it actually trigger correctly, and what's the real pick-off cost — without risking a cent, since shadow mode never becomes the authoritative exit.
3. **`trail` stays poll-only** until/unless the shadow data on the simpler stages justifies the added complexity of continuous re-pricing.
4. **Sizing the fix vs. the problem:** even the full, uncapped $2,793.30 is a structural floor, not the headline leak — J's own framing (`$100-200/day = ONE clean +30% level trade`) means this whole investigation is optimizing a residual on the order of one to two winning days' worth of edge, spread across 40 days of history. Worth building once validated; not worth rushing.

---

## Guards / reproducibility

- Dollar figures: `python setup/scripts/sampling_gap_ledger.py` (deterministic, re-run this session, byte-identical to committed except timestamp).
- Live broker evidence: `python backtest/tools/_canary_option_order_types_2026_08_02.py` (idempotent — places nothing that survives the run; independently re-verified flat via a separate process, §1.4).
- `exit_manager.py`, `exit_actuator.py`, `fleet_broker.py`, `fleet_live.py`, `fleet_executor.py`: read-only this session — `git status --porcelain` clean on all five, checked immediately before writing this report.

## Commit shas

See final commit message for this file + the canary script + the refreshed ledger timestamp.
