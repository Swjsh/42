# Entry execution cost — what the marketable-limit-plus-buffer mechanism actually costs us

> **Written 2026-08-02 03:17 ET** (verified via `setup/scripts/et_clock.py` — market closed, weekend). Git sha at time of writing: `cb30dcd2`.
> **Data:** real broker fills (`automation/state/fills-ledger.jsonl`), real logged engine quotes (`automation/state/core-decisions.jsonl`, `automation/state/fleet/{arm}/decisions.jsonl`), real OPRA option bars (`backtest/data/options/*.csv`, extended this session for 9 previously-uncached symbols), real trade P&L (`journal/trades.csv`). Zero synthetic/Black-Scholes premiums anywhere in this document.
> **Scope:** measurement + one narrowly-scoped, pre-registered A/B. Zero edits to `heartbeat_core.py`, `fleet_live.py`, `fleet_broker.py`, `fleet_executor.py`, `params.json`, `aggressive/params.json`, or any other DO-NOT-TOUCH path — this lane is read-only over the trade path, additive-only over the OPRA cache (9 new symbol files, no existing file touched).

---

## 1. The one thing

**`entry_cross_buffer` is a bare code default — `params.get("entry_cross_buffer", 0.03)` in both `heartbeat_core.py` and `fleet_live.py` — that has never once appeared in `params.json`, `aggressive/params.json`, or any fleet arm's `accounts.json` override, in this repo's entire git history. It was never ratified, never A/B'd, never examined since the day the marketable-limit mechanism shipped (2026-06-30).** It costs a real, mechanical **$1,422** across the 105 real fills this measurement could price. A narrow, pre-registered test of cutting it from $0.03 to $0.015 **clears every gate on real fill history** — 17 of 17 trading days strictly positive, zero regression on the 10 real runner-cohort winners, 94.3% fill rate retained — for a conservative, causally-clean **+$678** over the measured window (the full pre-registered number is $853; $175 of that is a smaller, partly base-rate-driven "avoided historical losses" component, disclosed separately below, not hidden in the headline).

**This is not shipped.** The concrete change — one new key in `params.json` and `aggressive/params.json` — is blocked by this lane's own DO-NOT-TOUCH scope on both files. It is proposed verbatim in §5 for whoever owns those files next.

Separately: the dramatic, motivating exhibit (WINNER-AUTOPSY's "$30 lost to latency, 24% of the trade") **does not generalize.** Measured systematically across every real fill this session could price, aggregate latency drift is **$24 — near zero** — and the anchor trade itself, re-measured at the 5-minute OPRA resolution this bulk method can actually reach, shows a *slightly favorable* drift, not a costly one. The n=1 anecdote and the population disagree, and per this repo's own standing convention (WINNER-AUTOPSY's own "the anecdote and the book disagree, and the book wins"), the population wins. Latency is real, it is documented below with full transparency about why it can't be perfectly reproduced at scale, but **it is not the lever this measurement found** — the buffer is.

---

## 2. The mechanism (task 1)

**Where the price comes from.** Both live placement paths — `heartbeat_core.py#_execute` (core: safe-2/bold-2, `execution="mcp_heartbeat"`) and `fleet_live.py#_place_live` (fleet: safe-1/safe-3/risky-1/risky-3) — call the SAME primitive:

```python
entry_px = fb.marketable_limit_price(creds, symbol, side="buy",
                                     buffer=float(params.get("entry_cross_buffer", 0.03)))
```

`fleet_broker.marketable_limit_price` (line 249): `BUY = ask + buffer`, rounded to the cent. The order that actually reaches the broker is a **plain marketable limit** (`_place_simple_entry` / the inline `_order` dict in `fleet_live.py`) — never a bracket (Alpaca rejects bracket/oto for options, code 42210000). TP1/stop are computed separately, off `mid` — **not** off `entry_px` — so the buffer has *zero* interaction with exit management; it only ever affects the entry cost basis of a trade that still crosses. This single fact is what makes §5's A/B tractable without an `exit_manager` replay.

**Provenance check.** Grepped `automation/state/params.json`, `automation/state/aggressive/params.json`, and `automation/state/fleet/accounts.json` (current content + full git history via `git log -p -S "entry_cross_buffer"`): **zero hits, ever.** Every arm — core and fleet, safe and bold — has always run the bare `0.03` code default. Compare to `min_entry_premium` (0.30), which has a full scorecard, a dated ship commit, a 10-test guard, and an independent gate-provenance census entry (`analysis/recommendations/min-entry-premium-2026-07-31.json`, reused untouched by this lane). The buffer has none of that. It is the single largest unexamined constant on the entry path.

**Every consumer**, confirmed by direct grep across the repo:
| Consumer | File | Line (approx) |
|---|---|---|
| Core entry pricing | `setup/scripts/heartbeat_core.py` | ~1932 |
| Fleet entry pricing | `automation/state/fleet/fleet_live.py` | ~389 |
| NBBO reconstruction (telemetry only) | `heartbeat_core.py` (`_nbbo_buf`) | ~1948 |
| Test doubles (6 test files) | `backtest/tests/`, `automation/state/fleet/test_*.py` | various |

No other consumer exists. No consumer reads a different value.

---

## 3. The cost decomposition, in dollars (task 2)

**Population:** 105 real filled entries (order-id-grouped, qty-weighted, all 6 arms — safe-1, safe-2, safe-3, risky-1, risky-3, bold-2 — 17 real trading days, 2026-07-01 through 2026-07-31). 27 earlier fills (2026-06-26 to 2026-06-30) were excluded as **pre-mechanism** — the marketable-limit-plus-buffer code shipped mid-day on 2026-06-30, and those rows show `entry_px == mid` exactly (no buffer applied yet, verified by direct date-clustering, not assumed). 35 fills were excluded for **no matching decision row** (join gaps in the ledgers, disclosed, not guessed around).

**Method:** for every fill, `entry_px` and `mid_decision` come from the engine's own logged numbers (`exec.entry_px`/`exec.premium`/`exec.nbbo` in `core-decisions.jsonl`; `placement.entry_px`/`placement.mid` in the fleet arm's own `decisions.jsonl`) — not modeled. `mid_signal` (the earliest real print reflecting the setup) is reconstructed from real OPRA 5-minute bars, anchored on the *driving decision row's own evaluation timestamp* (see §4 for why, and the correction this session made getting there).

| Component | Definition | Total $ | Avg ¢/contract |
|---|---|--:|--:|
| **spread_crossed** | `ask_at_decision − mid_at_decision` | **$454.00** | 0.93¢ |
| **cross_buffer** | `entry_px − ask_at_decision` (= `entry_cross_buffer`, exactly, every row) | **$1,422.00** | 3.00¢ |
| **latency_drift** | `mid_at_decision − mid_at_signal` | **$24.00** (n=29 resolved / 105) | 0.28¢ |
| **price_improvement** | `entry_px − fill_price` (recovered — limits can fill better than offered) | **−$2,005.01** (a credit) | 4.11¢ |
| **Gross excess cost** (spread+buffer+latency) | | **$1,900.00** | |
| **Net of realized improvement** | | **−$105.01** | |

**Read this carefully.** The engine pays for a padded, spread-crossing limit ($1,900 gross across spread+buffer+latency), but the market gives back more than that in realized price improvement — **0 of 105 fills executed worse than their own offered limit**, and the average fill beat `entry_px` by 4.11¢/contract, more than the buffer itself. Net of that credit, the whole mechanism is close to breakeven-to-slightly-negative-cost in aggregate (**−$105.01**, i.e. a very small net *gain* relative to a hypothetical fill exactly at the signal price). **This does not mean the buffer is free** — see §5: price improvement is a property of *how limit orders execute in a liquid market*, not a reward for the specific amount of padding chosen, and the buffer component is cleanly, mechanically recoverable on its own (proven in §5), independent of whatever improvement the market happens to hand back.

**Latency drift's small n is a resolution limit, not a small effect being hidden.** `trigger_bar_et` (the field this measurement needs to anchor "signal time") only started being logged 2026-07-21 for core, and fleet's own signal-relay timestamp has no direct join key before 2026-08-01 (`fill_latency.py`'s own scope note says the same). Of 105 rows, only 29 resolve a `mid_signal`: all 17 core rows resolve trivially (core has **no separate signal-read hop** — a single `get_option_mid` call serves both the entry-gate check and the entry price, so core's latency drift is a clean, mechanical **$0.00**, not a data gap), and only 12 of 88 fleet rows resolve via OPRA. **Do not read $24 as "latency doesn't matter" with confidence** — read it as "the resolvable subset shows near-zero, and the resolvable subset is one-quarter of the fleet population." This is disclosed, not adjusted away.

### Winners vs losers

| | n | spread_crossed | cross_buffer | latency_drift | price_improvement | Net |
|---|--:|--:|--:|--:|--:|--:|
| **Winners** | 14 | $32.00 | $189.00 | $22.00 (n=9) | −$275.00 | **−$32.00** |
| **Losers** | 85 | $403.00 | $1,167.00 | $2.00 (n=14) | −$1,666.01 | **−$94.01** |
| Unknown P&L | 6 | $19.00 | $66.00 | $0.00 (n=6) | −$64.00 | $21.00 |

Sanity check: 14 winners / 85 losers = 14.1% win rate in the priced subset, matching the FULL `journal/trades.csv` population (18/139 = 13.0%) almost exactly — the priced subset is not a biased slice. **Winners see less than half the per-contract spread cost of losers** (0.36¢ vs 1.01¢/contract) — consistent with winning setups tending to trigger in tighter, more liquid tape, though n=14 is too small to lean hard on that shape. Paying up on a trade that works and paying up on one that doesn't are indeed different economic questions, per the mission's framing — the DATA shows losers absorb roughly 5x the dollar cost of winners simply because there are 6x more of them, not because losers pay a worse *rate*.

### By lane

| | n | cross_buffer | latency_drift | Net |
|---|--:|--:|--:|--:|
| **Core** (safe-2, bold-2) | 17 | $189.00 | **$0.00 (structural)** | +$19.99 |
| **Fleet** (safe-1/3, risky-1/3) | 88 | $1,233.00 | $24.00 (n=12/88) | −$125.00 |

Core executes inline (verdict and entry price come from the same function call) — its buffer cost is real but its latency is architecturally near-zero. Fleet carries 88 of the 105 fills (5x core's volume) and essentially all of the (thin) latency signal this measurement could resolve — consistent with WINNER-AUTOPSY's own finding that the costly latency in the anchor trade was specifically the fleet's shared-signal relay hop, not core's own tick cadence.

---

## 4. Reproducing the anchor trade, and where the reconstruction diverges

The 2026-07-31 12:19 ET risky-3 entry (SPY 746C, WINNER-AUTOPSY's motivating exhibit) is in this population. The pipeline reproduces it **exactly** on every logged field:

| Field | This measurement | WINNER-AUTOPSY |
|---|---|---|
| Fill price | $0.33 | $0.33 ✓ |
| `entry_px` | $0.34 (= ask $0.31 + $0.03) | "$0.33 paid" ✓ |
| `mid_decision` (mid at fill) | $0.30 | "logged mid at 12:19 was exactly $0.30" ✓ |
| `mid_gating` (floor check value) | $0.30 | "cleared by $0.00" ✓ |
| Trade P&L | +$126.00 | +$126.00 ✓ |

Where it **cannot** reproduce WINNER-AUTOPSY's hand-picked number: that document quotes a specific 1-minute print ($0.27 at 12:16) pulled by hand from a live 1-minute MCP fetch. This measurement's OPRA cache is 5-minute bars (the format every other consumer of `backtest/data/options/*.csv` in this repo already uses — `simulator_real.py`, `shadow_entry_backfill.py`). Anchoring on the driving core row's own evaluation instant (12:16:02–12:18:03, not the underlying candle's *start* — a bug this session caught and fixed, see the tool's own docstrings for the paired before/after evidence) lands the reconstruction in the 12:15–12:20 5-minute bar, close **$0.32** — much closer to the hand-verified $0.27 than the first (wrong-bar) attempt's $0.35, but not identical. **This gap is the honest cost of doing this at scale**: a forensic, hand-picked 1-minute reconstruction on one trade is more precise than a systematic 5-minute sweep across 105, and the sweep should not be read as contradicting the hand-forensics — it is answering a different, harder question (*every* trade, not the one that happened to make a good story) with a coarser tool, by necessity.

---

## 5. The buffer-reduction candidate (task 4) — PROPOSED, NOT SHIPPED

**Pre-registered before the runner existed**: `analysis/recommendations/entry-buffer-reduction-prereg-2026-08-02.json`, commit `78979314`, which predates the runner script's own commit `cb30dcd2` (git-provable). Full results: `analysis/recommendations/entry-buffer-reduction-results-2026-08-02.json`.

**Why this candidate and not a passive-limit redesign.** T3 (`analysis/recommendations/entry-exit-matrix-t3-entries.md`) already tested delta-below-signal passive limits with patience/cancel against the live `ride` exit shape and returned **STOP-A** — every disclosed cancel-policy variant *loses* to paying up, at every premium floor tested, because a no-stop ride has no headroom to protect. That result stands untouched. A buffer *reduction* is a different, narrower mechanism: it never risks the entry timing or the exit shape, only the padding on an already-marketable limit — the one lever T3 didn't test and the one lever the measurement above showed has a clean, mechanical, exit-independent dollar value (§2's `cross_buffer` row, because TP1/stop read `mid`, never `entry_px`).

**Method.** For each of 3 candidates (0.01 / 0.015 / 0.02), replayed the 105 real fills: `fill_price <= ask_decision + candidate` ⇒ **still fills**, at the *same* real `fill_price` (disclosed assumption: realized execution price is buffer-independent once the tighter limit still clears it — the limit is a ceiling, not a target; not independently verified against Alpaca's routing internals, the single largest source of uncertainty in this test). A still-filled trade's every `trades.csv` leg shifts by `(0.03 − candidate) × qty × 100`. A **missed** trade's *entire* realized P&L is subtracted — modeled as fully foregone, never backfilled with a synthetic price, per the mission's explicit instruction.

| Candidate | Fill rate | Filled / Missed | Total Δ P&L | Day-majority | Drop-best Δ | Runner-cohort misses | Verdict |
|---|--:|--:|--:|--:|--:|--:|---|
| $0.01 | 81.0% | 85 / 20 | +$865.00 | 16/17 | +$621.00 | **2 of 10** (incl. the anchor trade itself) | **FAIL** |
| **$0.015** | **94.3%** | 99 / 6 | **+$853.00** | **17/17** | **+$659.50** | **0 of 10** | **PASS ALL GATES** |
| $0.02 | 98.1% | 103 / 2 | +$516.00 | 17/17 | +$387.00 | 0 of 10 | **PASS ALL GATES** |

**$0.01 fails on the gate that matters most**: it would have missed the WINNER-AUTOPSY anchor trade *entirely* (fill $0.33 > tighter limit $0.32) — the exact trade that motivated this whole investigation would not have happened under an over-aggressive cut. This is exactly the kind of irony the mission's framing anticipated, and exactly why the runner-cohort gate exists at zero tolerance.

**$0.015 clears every gate, robustly** — not marginally: all 17 trading days show a *strictly positive* delta (no zeros, no near-misses), and none of the 6 real misses is a winner (2 losers, 4 breakeven/small-loser scratches — verified individually, not assumed).

**Suspicion check (the "too good" hunt).** $853 decomposes into **$678 pure mechanical buffer savings** on the 99 trades that still fill (repeatable: every filled trade gets exactly 1.5¢/contract back, regardless of outcome) **+ $175 from "avoiding" the 6 missed trades' own real, mostly-negative P&L.** That second piece is **not** evidence the buffer is smartly screening bad trades — the whole population's average P&L per trade is **−$7.33** (13% win rate), so randomly dropping *any* 6 trades from this population tends to drop losers by sheer base rate, not causal selection. The $175 is plausible under that null and should not be treated as a repeatable edge. **The conservative, causally-clean number is $678 over 17 days (~$40/day) — and that number alone still clears every gate's spirit.**

**Recommendation:** add `"entry_cross_buffer": 0.015` to `automation/state/params.json` and `automation/state/aggressive/params.json`. **Not applied by this lane** — both files are explicitly DO-NOT-TOUCH here. Whoever owns them next can ship this with the evidence already filed, gates already passed, guard tests already green.

---

## 6. Floor interaction, quantified (task 3)

Reused, untouched: `analysis/recommendations/min-entry-premium-2026-07-31.json` (provenance + blocked-cohort replay — the floor's own KEEP verdict stands, not re-litigated here).

This lane's question is the mirror image: **of the trades we actually TOOK, how many cleared the $0.30 floor only because of delay** (i.e., the earlier, un-drifted signal price was itself under $0.30)?

Population: 24 floor-active entries (floor shipped 2026-07-09) with a resolvable `mid_signal`. **1 of 24 (4.2%)** shows the mechanism: `SPY260728C00744000` (safe-3, 2026-07-28) — gating premium $0.33 cleared the floor, but the reconstructed signal-time mid was $0.29, under it. That trade's real P&L was **−$33.00** — a loser. **This is the opposite sign of the WINNER-AUTOPSY anchor's own inference** (which reasoned, correctly, that ITS OWN delay-enabled clearance produced a winner) — the anchor trade itself is not in this 24-row resolvable subset (its `mid_signal` of $0.32, reconstructed above, sits comfortably over $0.30, so by this measurement it would have cleared the floor even without the delay).

**Net:** n=1 is too small to say whether delay-dependent floor clearance is, on balance, good or bad for the book — this measurement found one clean example and it was a loser, directly contradicting a naive read of the anchor trade as representative. **This is the mission's own instruction working as intended**: net the saved cents against the lost trades, and in the one case with enough data to check, there was nothing to net — the "floor cleared because of delay" trade lost money on its own terms. No action is warranted from n=1 either direction; this is reported as a measurement, not a lever.

---

## 7. What this is not

> Nothing in this document ships a change. `heartbeat_core.py`, `fleet_live.py`, `fleet_broker.py`, `fleet_executor.py`, `params.json`, `aggressive/params.json`, `accounts.json` are byte-identical to where they started. The buffer-reduction candidate is PROPOSED with every gate passed and every guard green — arming it requires editing two DO-NOT-TOUCH files this lane does not own.

- **n=29 latency-resolved rows is small.** Core's $0.00 is structural (trust it); fleet's $24 aggregate on 12 rows should not be read as "fleet latency doesn't matter" — it is "the resolvable 14% of fleet fills shows near-zero," a materially weaker claim.
- **The buffer A/B's central assumption — execution price is buffer-independent once cleared — is disclosed, not proven.** If Alpaca's specific price-improvement/routing logic rewards a MORE aggressive (higher) limit with better execution, a smaller buffer could realize *worse* fills than modeled, not just fewer of them. This is the single biggest risk in §5 and is flagged, not buried.
- **Floor interaction is n=1.** Directionally interesting, not actionable alone.
- **This measurement does not touch qty/sizing, exit rules, strike selection, or any regime/level-target/adaptive-sizing logic** — those are out of scope by the mission's own DO-NOT-TOUCH list and untouched here.

---

## 8. Standing artifacts, guards, commits

| Artifact | Path |
|---|---|
| Cost decomposition tool | `backtest/tools/entry_execution_cost_2026_08_02.py` |
| Cost decomposition output (105 rows) | `analysis/recommendations/entry-execution-cost-2026-08-02.json` |
| Cost decomposition guards (25 tests) | `backtest/tests/test_entry_execution_cost_2026_08_02.py` |
| Buffer-reduction pre-registration | `analysis/recommendations/entry-buffer-reduction-prereg-2026-08-02.json` |
| Buffer-reduction runner | `backtest/tools/entry_buffer_reduction_ab_2026_08_02.py` |
| Buffer-reduction results | `analysis/recommendations/entry-buffer-reduction-results-2026-08-02.json` |
| Buffer-reduction guards (13 tests) | `backtest/tests/test_entry_buffer_reduction_ab_2026_08_02.py` |
| This document | `analysis/deep-research/ENTRY-EXECUTION-COST-2026-08-02.md` |

**38/38 guard tests green** (`python -m pytest backtest/tests/test_entry_execution_cost_2026_08_02.py backtest/tests/test_entry_buffer_reduction_ab_2026_08_02.py`). Two of the fixed bugs (`archetype_match_json` column, `load_contract_bars` cache staleness) and one methodology correction (signal anchor = driving row's `ts_et`, not `trigger_bar_et`) were each caught by reproducing the real WINNER-AUTOPSY anchor trade end-to-end and finding it wrong before they were right — that reproduction, not a synthetic mutation pass, is this session's RED-proof; each fix site's docstring carries the exact before/after numbers.

**Commits** (all pathspec-scoped via `commit_scoped.py`, none pushed):
- `bc2cdb6a` — cost decomposition instrument + 25 guards + output
- `78979314` — buffer-reduction pre-registration (before the runner)
- `cb30dcd2` — buffer-reduction runner + 13 guards + results + folded pre-reg

**OPRA cache**: 9 new symbol files added to `backtest/data/options/` this session via `ensure_cached()` (additive only, `ensure_cached` refuses to touch a path that already exists — see its own guard in `entry_execution_cost_2026_08_02.py`). This directory is gitignored (`.gitignore:21,56`), so the addition is invisible to `git status`/this session's commits by design — verified directly on disk instead: the 9 fetched symbols (e.g. `SPY260731C00747000.csv`) did not exist before this session's live fetches and are real Alpaca `/v1beta1/options/bars` responses, not synthetic data.

### Ship-or-measurement-only verdict

**Both.** Tasks 1–3 are measurement, delivered in full with real dollar figures, winners-vs-losers, and the floor-interaction net, exactly as scoped. Task 4 found one candidate — `entry_cross_buffer: 0.03 → 0.015` — that clears every pre-registered gate on real fill history for a conservative +$678 (full method: +$853) over the measured window, with the concrete diff specified and ready, **blocked from application only by this lane's own file-scope boundary**, not by the evidence.
