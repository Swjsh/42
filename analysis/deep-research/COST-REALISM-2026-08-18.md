# Cost Realism — What a Real Account Costs vs What Paper Reports (2026-08-18)

> J's ask, verbatim intent: *"What are we doing about documenting, like, how much it would cost
> to get in the trades, taxes, fees? ... basically, like, a one to one, to try and copy what it
> would be like if we're trading a real account, so that's a seamless transition."*
>
> Instrument: [`setup/scripts/cost_model.py`](../../setup/scripts/cost_model.py) (`--json`
> writes [`analysis/recommendations/cost-model.json`](../recommendations/cost-model.json)).
> Tests: [`backtest/tests/test_cost_model.py`](../../backtest/tests/test_cost_model.py), 45/45
> green, RED-proofed (see Testing section). Read-only this whole session: no params edited, no
> orders placed, nothing armed.

---

## VERDICT

**Real regulatory fees — which Alpaca PAPER is already charging for real, just not counting
anywhere — turn a −$2,071.00 as-traded book into −$2,200.82 (−6.3% worse, 289 real round trips
across the 5 active arms, 2026-06-29 → 2026-08-17). The bigger question — does paper's fill
quality also hide a spread cost on top of that — is only HALF resolved: entries measure
realistic (HIGH confidence, see Section 3), but exits are UNVERIFIED this session. Trust
−$2,200.82 as the number backed by measurement; treat −$5,068.82 (+144.7%) as the honest
worst-case if exits turn out less realistic than entries, not as the answer.**

| | Book-wide (5 arms, correlated — see disclosure below) |
|---|---|
| **As-traded** (what trades.csv/HOME.md currently report) | **−$2,071.00** |
| **Fee-adjusted** (real OCC+ORF+TAF+SEC+CAT, empirically measured) | **−$2,200.82** |
| **Fee + spread-adjusted, Scenario A** (exits mirror entries' measured realism) | **−$2,200.82** |
| **Fee + spread-adjusted, Scenario B** (conservative exit-spread placeholder) | **−$5,068.82** |

This book was **already losing on paper before any adjustment.** Fees make it a little worse.
The unresolved exit-spread question could make it much worse, or not worse at all — this
report does not paper over that gap with a single fake-precise number.

---

## 1 — What was already modeled (STEP 1: LIVE vs DEAD)

Grepped `backtest/`, `setup/scripts/`, `automation/` for commission/fee/slippage/spread/ORF/
TAF/OCC/SEC-fee handling. Two genuinely separate things exist; neither is what this task needed,
and tracing each one's actual read path (not just grep) matters here.

### LIVE — real, consumed by running code

| What | Where | Consumed by | Scope |
|---|---|---|---|
| Entry/exit **slippage** ($0.02/contract default each side) | [`backtest/lib/simulator_real.py`](../../backtest/lib/simulator_real.py) `DEFAULT_ENTRY_SLIPPAGE`/`DEFAULT_EXIT_SLIPPAGE`, mirrored in `simulator_real_trailing.py` | Every single-leg backtest simulation (the strategies actually live-trading: `ribbon_ride`, `vwap_continuation`) | Backtest **simulation** of hypothetical past days. Re-baselined 2026-08-12 (exit-slippage asymmetry bug fix, guarded by `test_exit_slippage_symmetry_2026_08_12.py`). Calibration note in the module: *"typical spread 0.04-0.10"* for SPY 0DTE ATM options — this repo's own working number, corroborated loosely by this session's own measurement (Section 3). |
| **Entry execution-cost decomposition** (latency drift, spread crossed, cross-buffer, price improvement) | [`backtest/tools/entry_execution_cost_2026_08_02.py`](../../backtest/tools/entry_execution_cost_2026_08_02.py) | Reads REAL logged quotes (`core-decisions.jsonl` exec.nbbo/premium/entry_px, fleet `decisions.jsonl` placement.mid/entry_px) against REAL fills. Writes `analysis/recommendations/entry-execution-cost-2026-08-02.json`. | Execution **quality/timing**, not fees or commission — a different question than this task. Re-run this session (`--no-fetch`) and reused directly for Section 3 below. |
| **Crypto-twin friction calibration** | [`setup/scripts/crypto_twin_friction_calibration.py`](../../setup/scripts/crypto_twin_friction_calibration.py) | Real crypto-twin paper fills | Prior art for "measure friction from real paper fills" methodology — explicitly NOT an SPY-options-dollars analog (crypto taker-fee economics differ; its own docstring says so). Doesn't answer this task's question, but is the closest existing precedent for the *shape* of this instrument. |
| `entry_cross_buffer` ($0.03, marketable-limit padding on entries) | `heartbeat_core.py` / `fleet_broker.marketable_limit_price` | Every real entry order | Not a fee model — it's how aggressively the engine crosses the spread on entry. Directly relevant to Section 3 (the spread question), not to Section 2 (fees). |

### DEAD (for what's actually trading) or NEVER BUILT

| What | Where | Status |
|---|---|---|
| **Commission** ($0.65/contract/side, explicitly `# Alpaca paper = 0.0 (knob)`) | [`backtest/lib/simulator_credit.py`](../../backtest/lib/simulator_credit.py) `DEFAULT_COMMISSION`, mirrored in `simulator_debit.py` | LIVE as code (consumed by `debit_spread_ab_study.py` and other multi-leg spread A/B research), but **not applicable to what's live-trading today.** `spread_executor.py` (the multi-leg order machinery these simulators exist for) is explicitly *"BUILT DISARMED... NOTHING imports this on the live path yet."* The 5 real-fills arms trade single-leg long calls/puts only (`ribbon_ride`, `vwap_continuation` per `accounts.json`'s `strategy_set`) — this commission constant has never touched a real dollar. |
| **Commission/fees in the single-leg backtest simulator** | `simulator_real.py`, `simulator_real_trailing.py` | **Never built.** Grepped for `commission` — zero hits in either file. Slippage is modeled (see LIVE table); regulatory fees and commission are not, not even as an acknowledged $0 placeholder, in the simulator that actually estimates the live strategies' historical performance. |
| **Regulatory fees on REAL fills** (OCC/ORF/TAF/SEC/CAT) | Alpaca charges these for real (Section 2) — but [`setup/scripts/broker_fills.py:102`](../../setup/scripts/broker_fills.py) hits `/v2/account/activities/FILL` specifically (a type-scoped REST path, verified by reading the literal URL construction, not the docstring). `FEE`-type activities are **structurally never fetched.** | **The gap this whole task is about.** Every `real_pnl` in `fills-ledger.jsonl` → `fills_fifo.py` → `trades.csv` → every EOD digest/dashboard number has silently excluded fees Alpaca is actually debiting from the account. This is not a modeling choice anyone made — it's an unbuilt pipe. `cost_model.py` (this session) is the first thing in the repo to apply them, and does so offline/retroactively rather than by wiring a new ingestion path into the live pipeline (out of scope — "arm nothing, edit no params" per this task's brief). |

**Net:** the assumption "paper trading is frictionless" was already half-wrong before this
session started — Alpaca has been charging real regulatory fees the whole time. What was
actually true is narrower: *this repo has never counted them.*

---

## 2 — The real fee stack (STEP 2)

The regulatory doc from tonight's earlier research
([`markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`](../../markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md),
not edited by this task) already established Alpaca's $0 commission and named which regulatory
categories apply (SEC fee, FINRA TAF, CAT fee — sourced from Alpaca's own page,
[alpaca.markets/support/regulatory-fees](https://alpaca.markets/support/regulatory-fees),
fetched 2026-08-18) but did not itemize dollar figures. This section extends it — with a
better source than a web page: **Alpaca's own live paper-account activity ledger.**

### 2a — Empirical rates (primary source — read live, not estimated)

`mcp__alpaca__get_account_activities_by_type(activity_type="FEE")`, run live this session
against Safe-2 (`PA3POKNV46VG`, 9 trading days, 2026-08-04→2026-08-17, ~45 FEE rows) and
cross-checked against Bold-2 (`PA3WEBXJU67N`). **Alpaca paper is charging these fees for real
— this is not this script's assumption, it's what the account's own ledger shows.** Every rate
below reproduces every single observed dollar amount to the cent (see
`backtest/tests/test_cost_model.py` — each test case is a real observed row, not an invented
example):

| Fee | Rate | Side | How it was pinned down |
|---|---|---|---|
| **Commission** | **$0.00** | n/a | [alpaca.markets/support/what-are-the-commission-fees-per-option-contract](https://alpaca.markets/support/what-are-the-commission-fees-per-option-contract), fetched 2026-08-18: *"Alpaca Trading API users will not encounter any commissions for options trading."* True for paper **and** live — not a paper-vs-live gap. |
| **OCC Clearing Fee** | **$0.025/contract**, rounded UP to the cent, per execution | **Both sides** (observed on buy and sell fills alike — the account shows far more OCC rows per day than closed round trips, consistent with one charge per fill) | Reproduces every observed row exactly: qty 1→$0.03, 2→$0.05, 3→$0.08 (most common), 5→$0.13, 6→$0.15, 10→$0.25. Corroborates a web search of theocc.com's schedule (`$0.025/contract`, direct fetch blocked HTTP 403 — search-synthesized only, so the empirical read is the stronger evidence here, not the web figure). |
| **ORF** (Options Regulatory Fee) | **$0.015/contract**, rounded UP to the cent, aggregated daily | **Both sides** — proved, not assumed: on every single sampled day, the ORF "N contracts" count was **exactly 2×** that same day's TAF "N contracts" count (TAF is sells-only, confirmed below), 9/9 days (e.g. 2026-08-13: TAF "9 contracts" vs ORF "18 contracts"). | Sits between the per-exchange range found via search (NYSE Arca $0.0026, Cboe $0.0017, vs. Nasdaq-family exchanges $0.0080–$0.0200 per the companion regulatory doc) — plausible as a blended rate across Alpaca's real order-routing mix. The empirical $0.015 is used as the model rate; the exchange-by-exchange range is disclosed as context, not a separate scenario, since it's superseded by direct observation. |
| **FINRA TAF** | **$0.00329/contract**, rounded UP to the cent | **Sells only** (confirmed both by Alpaca's own page — *"Based on per share (sells only)"* — and by every observed row) | Reproduces every observed row: 3 contracts→$0.01, 12→$0.04, 9→$0.03, 15→$0.05, 6→$0.02. Matches FINRA's current published rate (effective 2026-01-01, search-corroborated) independently. |
| **SEC Section 31 fee** ("REG" in Alpaca's ledger) | **$20.60 per $1,000,000** of proceeds, rounded UP to the cent | **Sells only** (statutory — a fee on the sale of a security; confirmed by Alpaca's own page) | Reproduces every observed row exactly: $201 proceeds→$0.01, $720→$0.02, $1,140→$0.03, $1,488→$0.04, $678→$0.02, $1,047→$0.03, $633→$0.02, $699→$0.02, $207→$0.01. Matches tastytrade's own dated Commissions & Fees PDF (*"as of April 4, 2026"*, dated 2026-07-30) exactly — already cited in the companion regulatory doc, reused here per this task's instruction. |
| **CAT fee** (Consolidated Audit Trail) | **Flat $0.01/account/trading-day** with any activity | Both (per Alpaca's own page: *"applies to both equity and options trading activities"*) | Empirically **constant** at $0.01 regardless of daily trade count (2 to 10 trades/day in the sample, always exactly $0.01) — **not** a per-contract formula at Gamma's scale. FINRA Rule 6897 ([finra.org/rules-guidance/rulebooks/finra-rules/6897-0](https://www.finra.org/rules-guidance/rulebooks/finra-rules/6897-0), fetched 2026-08-18) assesses CAT fees on the **executing broker**, by aggregate monthly volume (currently $0.000009/executed-equivalent-share per the FINRA CAT Fee 2025-2 schedule) — there is no published per-contract retail rate. Alpaca's $0.01/day is presumably its own internal floor/allocation of that broker-level cost, not a regulator-set number. Immaterial either way (book-wide total: $1.03 across the whole sample).

### 2b — Sides, at a glance

| Fee | Buy (entry) | Sell (exit) |
|---|---|---|
| Commission | — | — |
| OCC clearing | ✅ | ✅ |
| ORF | ✅ | ✅ |
| FINRA TAF | ❌ | ✅ |
| SEC Section 31 | ❌ | ✅ |
| CAT | once/day (not per-side) | |

`backtest/tests/test_cost_model.py::test_fee_breakdown_never_charges_sells_only_fees_on_entry_leg`
pins exactly this table — see Testing section for the RED-proof.

---

## 3 — The spread question (STEP 3, the one that "may dominate every other cost")

**Does Alpaca PAPER fill at the midpoint (optimistic — a real account would lose roughly half
the spread per side that paper never charged) or near the real bid/ask (realistic)?**

### Entry side — MEASURED, HIGH confidence

Every real entry is placed as a marketable limit: `entry_px = real_ask (fetched live from
Alpaca's own options-quotes endpoint) + $0.03 buffer` (`fleet_broker.marketable_limit_price`).
That means `price_improvement = entry_px − fill_price` is a clean, direct measurement — no
reconstruction, no algebra, just two real logged numbers (what we asked for vs. what we got).

Re-ran the existing `backtest/tools/entry_execution_cost_2026_08_02.py --no-fetch` this
session (local ledger data only, no network, n=250 real entry fills across all 6 arms
including retired safe-1):

| Arm | n | avg price_improvement (¢/contract) | avg cross_buffer (¢/contract) |
|---|---|---|---|
| safe-2 | 33 | 2.99 | 3.00 |
| bold-2 | 26 | 3.08 | 3.00 |
| safe-3 | 40 | 2.90 | 3.00 |
| risky-1 | 59 | 3.35 | 3.00 |
| risky-3 | 72 | 3.78 | 3.00 |
| **overall** | **250** | **3.40** | **3.00** |

`price_improvement` clusters right on top of `cross_buffer` (the deliberate $0.03 padding we
always add) for **every single arm.** If paper were filling generously at the NBBO midpoint,
`price_improvement` would run buffer *plus* roughly half the real bid/ask spread — several
more cents, per this repo's own simulator calibration note of a 4–10¢ typical 0DTE spread. It
doesn't. **Paper fills BUY orders at essentially the real quoted ask, not the midpoint.**

(The separately-reconstructed `avg_spread_crossed_cents_per_contract` — ask-vs-mid, i.e. an
attempt at the half-spread itself — is noise-level and sometimes negative, −0.69 to +1.00¢
across arms. That's an artifact of two independent, near-simultaneous live quote calls each
independently rounded to the cent, exactly as the code's own comment discloses — not evidence
of a real wide spread being hidden.)

### Exit side — UNVERIFIED this session

Exits are placed as **market orders** (`fleet_broker.market_sell`), which have no submitted
limit to diff a fill against the way entries do. `exit_actuator.py` *does* fetch a real
bid/ask quote before every exit decision (`best_premium`=ask, `worst_premium`=bid,
`get_option_quote_hilo`) and persists it into each fleet arm's `decisions.jsonl` via the
`exit_pass` key — **the data to build an exit-side mirror of `entry_execution_cost.py` already
exists**, but that instrument was not built this session (scoped out to ship the rest of this
task; a concrete, not vague, follow-up).

**Two scenarios are carried explicitly, not averaged:**

- **Scenario A — zero incremental spread cost.** Assumes exits are as realistic as the
  measured entries (same matching engine, same account). This is the headline in the verdict
  box because it's the one with actual measurement behind it (on the entry side); extending it
  to exits is a disclosed **inference**, not a second measurement.
- **Scenario B — conservative placeholder.** Reuses this repo's own **existing** standing
  backtest assumption, `simulator_real.DEFAULT_EXIT_SLIPPAGE = $0.02/contract`, applied to the
  exit leg of every round trip. Not a new invented number — the number this codebase has used
  for years as its working estimate of 0DTE SPY market-exit cost.

Per this task's honesty requirement: **if you cannot determine paper-fill behavior, say
UNKNOWN and give the range under both assumptions — never split the difference silently.**
That is exactly what Scenario A vs B is. Confidence: entries HIGH (measured, n=250, 6/6 arms
consistent); exits MEDIUM-LOW (mechanism-consistency argument only, not independently
measured).

---

## 4 — Per-arm results (STEP 3 continued)

All figures from `analysis/recommendations/cost-model.json`, generated 2026-08-18T22:09:49 ET
by `cost_model.py` against the live `fills-ledger.jsonl` (engine-attributed round trips only —
J's manual fills excluded, matching this repo's own C11 attribution rule). Cross-validated:
`as_traded_pnl` for every arm matches `automation/state/pnl-statement.json`'s `engine_pnl`
field **exactly**, generated independently the same day by the repo's other canonical P&L
instrument (`broker_fills.py`) — safe-3 −376.00/−376.0, safe-2 −736.00/−736.0, risky-1
−297.00/−297.0, bold-2 −492.00/−492.0, risky-3 −170.00/−170.0.

| Arm | Trips | As-traded | Fees (ex-CAT + CAT) | Fee-adjusted | +Spread (A) | +Spread (B, conservative) |
|---|---:|---:|---:|---:|---:|---:|
| safe-3 | 47 | −$376.00 | $15.17 + $0.20 = $15.37 | −$391.37 | −$391.37 | −$721.37 |
| safe-2 | 69 | −$736.00 | $19.60 + $0.22 = $19.82 | −$755.82 | −$755.82 | −$1,175.82 |
| risky-1 | 68 | −$297.00 | $32.04 + $0.21 = $32.25 | −$329.25 | −$329.25 | −$1,037.25 |
| bold-2 | 26 | −$492.00 | $12.20 + $0.14 = $12.34 | −$504.34 | −$504.34 | −$774.34 |
| risky-3 | 79 | −$170.00 | $49.78 + $0.26 = $50.04 | −$220.04 | −$220.04 | −$1,360.04 |
| **BOOK\*** | **289** | **−$2,071.00** | **$129.82** | **−$2,200.82** | **−$2,200.82** | **−$5,068.82** |

\* **BOOK is a CORRELATED ROLLUP, not 5 independent samples.** All 5 arms trade the SAME
shared signal (`automation/state/fleet/build_shared_signal.py`) and differ only in
sizing/gates/exit shape (`MAP.md`) — arms correlate at **r=0.846**. Read book-wide as one
book's economics under 5 risk profiles, never as 5× the statistical confidence of one arm.

**Why risky-3 pays the most in fees despite the smallest as-traded loss:** most round trips
(79) *and* the largest average contract size (`cheap_contract_qty_boost`: qty 10 when a
contract prices under $0.50, per `accounts.json`) — regulatory fees scale with contract count,
not with P&L.

---

## 5 — Taxes (STEP 4 — NOT tax advice, no bill computed)

This is directional only. **Confirm anything load-bearing with a CPA before real money is on
the field** — nothing here is tax advice.

- **SPY options are NOT Section 1256 contracts.** They're options on an ETF **share** (a
  security), not directly on an index — ordinary short-term capital gains rates apply (almost
  always, given 0DTE holding periods), **and the wash-sale rule applies.**
- **SPX/XSP options ARE Section 1256** ("nonequity options" under IRC §1256(g), broad-based
  index options) — a blended **60% long-term / 40% short-term** rate *regardless of actual
  holding period* (relevant for 0DTE, which by definition never earns long-term treatment any
  other way), mark-to-market at year-end, and **exempt from the wash-sale rule.**
- **Directionally:** if Gamma ever trades SPX/XSP instead of SPY at the same P&L, the
  after-tax edge is meaningfully better — one illustrative source cited in the companion doc
  put it at roughly 26.8% blended effective rate under 1256 vs. up to 37–40.8% ordinary
  short-term on economically-identical exposure. Not recomputed here; treat as illustrative,
  not exact.
- **Alpaca added SPX/SPXW/VIX/VIXW/DJX/XSP support in PAPER ONLY on 2026-07-23** — no live
  date has been announced anywhere as of 2026-08-18. This is not actionable for a live account
  today even if J wants the tax treatment.
- Full sourcing (IRS Form 6781 framework, Section 1256 mechanics, SPX vs. SPXW vs. XSP
  settlement/assignment differences): [`markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`](../../markdown/trading-knowledge/REGULATORY-BROKER-LANDSCAPE-2026-08-18.md)
  section "Tax treatment: SPY vs SPX/XSP" — cited, not re-derived, per this task's instruction.

**This section is intentionally incomplete as a tax computation.** It exists to flag the
directional stakes of a future SPY→SPX/XSP decision, not to produce a number J could use on a
return.

---

## 6 — Limitations (disclosed explicitly, not buried)

1. **Exit-side spread realism is unmeasured.** The single biggest open question in this whole
   report. Section 3 explains exactly what data already exists to close it
   (`exit_pass`/`worst_premium` in fleet decisions.jsonl) and what wasn't built.
2. **OCC's per-execution granularity is simplified.** A multi-leg exit (TP1 + runner, 2 sell
   prints) is technically 2 separate OCC-fee executions on Alpaca's real ledger; this model
   charges OCC once per leg (entry, exit) at the round trip's total qty. Understates OCC by at
   most a few cents on the minority of round trips with a split exit — ORF/TAF/SEC are
   aggregate-based and unaffected. Immaterial at these dollar magnitudes.
3. **Fee rates verified on safe-2 and bold-2 only** (the two accounts reachable via this
   session's wired MCP servers). Applied uniformly to safe-3/risky-1/risky-3 on the assumption
   that Alpaca's fee-simulation engine is uniform across its own paper accounts (all 5 are
   Alpaca paper, regardless of which client hits the REST API) — plausible, matches every
   regulator-set rate found independently via web search, but **not independently re-verified
   per fleet account this session.**
4. **CAT fee's true underlying formula is unknown** — modeled as the empirically-observed flat
   $0.01/account/day, which may just be a floor/rounding artifact at Gamma's trading volume
   rather than Alpaca's actual formula at higher volume. Immaterial either way (book-wide
   total: $1.03).
5. **ORF's "both sides" conclusion rests on one clean cross-day pattern** (2× the TAF contract
   count, 9/9 days) rather than a directly-documented Alpaca statement. Strong internal
   consistency, not a primary-source confirmation of the mechanism.
6. **This is retroactive/offline, not a live pipeline fix.** `cost_model.py` computes what
   fees *should* have subtracted from every historical round trip; it does not (and per this
   task's brief, must not) wire FEE-activity ingestion into `broker_fills.py`/`fills_fifo.py`
   or change any live-reported number. `trades.csv`/`HOME.md`/every dashboard still reports
   the as-traded figure today.
7. **Commission's $0 finding is not itself in doubt** (directly quoted from Alpaca's own
   published rate, true both paper and live) — the only real uncertainty in this whole report
   is the exit-spread question in Section 3.
8. **Taxes are directional only** (Section 5) — not a computed bill, not tax advice.

---

## Testing

`backtest/tests/test_cost_model.py` — 45 tests, all pinned against **real observed Alpaca fee
rows** (not invented examples) for the arithmetic, plus explicit structural guards for the
sides table (Section 2b).

```
45 passed in 0.15s
```

**RED-proofed this session** (not merely asserted): temporarily set `TAF_FEE_PER_CONTRACT` to
10× its real value (`0.0329`) and temporarily patched `fee_breakdown()` to also charge
`taf_fee`/`sec_fee` on the entry leg (simulating the exact "sells-only fee leaks onto a buy"
bug the sides guard exists to catch). Result:

```
FAILED backtest\tests\test_cost_model.py::test_taf_fee_reproduces_observed_alpaca_rows[3-0.01]
FAILED backtest\tests\test_cost_model.py::test_taf_fee_reproduces_observed_alpaca_rows[12-0.04]
FAILED backtest\tests\test_cost_model.py::test_taf_fee_reproduces_observed_alpaca_rows[9-0.03]
FAILED backtest\tests\test_cost_model.py::test_taf_fee_reproduces_observed_alpaca_rows[15-0.05]
FAILED backtest\tests\test_cost_model.py::test_taf_fee_reproduces_observed_alpaca_rows[6-0.02]
FAILED backtest\tests\test_cost_model.py::test_fee_breakdown_both_sides_fees_charged_on_both_legs
FAILED backtest\tests\test_cost_model.py::test_fee_breakdown_never_charges_sells_only_fees_on_entry_leg
7 failed, 38 passed in 0.26s
```

Reverted both mutations; re-ran: `45 passed in 0.15s`. The suite catches both failure modes it
claims to catch.

---

[[MAP]] · [[HOME]] · [[analysis/deep-research/INDEX|deep-research index]]
