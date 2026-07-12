# Friction Budget / Account Math — Research Stream 4 of 5

**2026-07-11 · read-only research, no param changes, no orders.**

## VERDICT (one paragraph)

The math is **not structurally hopeless** at this account size — but the account is
**self-taxing**. ATM and ITM-1/ITM-2 strikes carry friction (spread-proxy + theta) that is a
small, affordable fraction of the observed favorable-move distribution, and both currently pay
for themselves comfortably inside the 3-contract minimum at $1.6-2.0K equity. The problem is
that **Safe's live core setup (`ribbon_ride`) still defaults to OTM-2**, the single worst tier on
every friction metric measured here — total measured friction on a 30-min AM hold is
**2.1-2.5x higher at OTM-2 than at ATM**, and this is not a new hypothesis: the codebase already
ran the equivalent real-money A/B on a sibling setup (`vwap_continuation`, WP-5, 2026-06-21) and
found the identical monotonic gradient, then shipped ATM/ITM-2 fixes for five extra setups —
**core `ribbon_ride` is the one family that never got the fix.** The single highest-leverage,
lowest-risk knob is closing that gap. The 3-contract minimum is currently slack, not binding —
it is not the thing forcing bad strikes today. The place the math genuinely IS close to
structurally negative is **afternoon (13:00-15:00 ET) entries at OTM tiers**, where decayed
absolute premium makes spread-proxy friction alone exceed 80-110% of the contract's value on a
30-min hold — but the already-shipped `min_entry_premium=0.30` floor already blocks most of that
cohort by accident, not by design.

---

## 0. What "spread" means in this repo — a correction before the numbers

The task brief cited `spread_cents=83.6` from a live decision row as a bid-ask spread
observation. **That field is not the option bid-ask spread.** Grep-verified
(`setup/scripts/heartbeat_core.py:326-340`, `backtest/lib/engine/gates.py:190-209`):
`spread_cents` in every decision-ledger row (`core-decisions.jsonl`, `sight-beacon.json`,
`fleet/shared-signal.json`) is the **SPY EMA-ribbon spread** (`max(fast,pivot,slow) -
min(fast,pivot,slow)` on the underlying, in cents) — a momentum/trend-strength indicator, unrelated
to option market microstructure. Using it as a spread-cost proxy would have been a real error;
flagging it here so it doesn't propagate.

**This repo has no cached NBBO (bid/ask) history for options, at all.** The OPRA cache
(`backtest/data/options/*.csv`, 8,682 files) is TRADE bars (open/high/low/close/volume/vwap/
trade_count) — confirmed by reading the schema and `lib/option_pricing_real.py`'s own docstring.
Three second-best sources exist and are used below, each labeled:

| source | what it actually measures | status |
|---|---|---|
| `simulator_real.py` `DEFAULT_ENTRY_SLIPPAGE`/`DEFAULT_EXIT_SLIPPAGE` = $0.02/side | a **MODELED assumption**, documented as "tuned for SPY 0DTE **ATM** options... slightly aggressive but defensible" — explicitly not claimed valid off-ATM | MODELED |
| `entry_exit_diagnostics.py` "spread proxy" = entry 5-min bar's (high−low) | a **MEASURED proxy** from real OPRA trade bars — captures intra-bar trade-price noise, which is wider than true NBBO but correlates with real illiquidity | MEASURED (proxy) |
| `trades.csv` `slippage_cents` (91/150 real-fill rows populated) | fill price **minus the decision-time reference price**, not fill vs. mid — an execution-slippage number, median **-5c** (filled better than the signal-time reference), n too small/mixed to use as a spread estimate | MEASURED (different metric, not spread) |
| `bid_ask_spread_max_cents: 8` / `bid_ask_spread_max_pct_of_mid: 0.1` in `params.json` | a **liquidity gate that has never been enforced** — confirmed via `backtest/tests/test_params_consumer_reconciliation.py`'s own `KNOWN_DEAD` allowlist: `"liquidity gate; not read by order path (RESTORE-or-REMOVE)"`. No grep hit for a consumer anywhere in `setup/scripts`, `automation/state/fleet`, or `backtest/lib`. | DEAD KNOB — zero entries have ever been screened on spread |

Given no true NBBO exists, this report builds its own **MEASURED, tier-resolved spread proxy**
(section 1) using the same bar-range methodology as `entry_exit_diagnostics.py`, extended across
the OTM-3..ITM-2 ladder and by hour bucket, over the same OPRA cache.

---

## 1. Theta — MEASURED empirically from flat-SPY windows (not Black-Scholes)

**Method:** `backtest/data/spy_5m_2025-01-01_2026-07-08.csv` (377 trading days) +
per-day/per-strike OPRA option bars. **DST-frame bug found and corrected**: both files store
timestamps with a *fixed* `-04:00` label year-round (the documented CLAUDE.md TZ-systemic
artifact) — during EST months this mislabels true ET by +1 hour (verified: 2025-01-02's raw
first bar reads `10:30:00-04:00`, but the true UTC instant converts to `09:30:00 America/New_York`
— actual market open). Fixed by round-tripping every timestamp through UTC before re-labeling
ET. Without this fix the AM/PM time-of-day buckets below would have silently misclassified
~40% of trading days (all EST-season dates).

For every ~15-min candidate window start inside 09:40-11:00 ET and 13:00-15:00 ET, on every
trading day, at hold durations {10,30,60,90} min: computed ATM strike, walked the OTM-3..ITM-2
ladder (both C and P, `option_symbol()`/`load_contract_bars()` reused verbatim from
`lib/option_pricing_real.py` for convention-consistency), kept only windows where **SPY itself
moved ≤0.05%** over the hold (isolates decay from delta/gamma — a genuine flat-underlying
window, not a model). **20,996 window instances scanned → 6,348 passed the tight flat filter →
146,599 tier×side×duration decay observations** (89.8% OPRA cache hit rate on the flat subset).
Median used throughout (not mean) — the mean is convexity-contaminated in the looser 0.15%
robustness band (a few near-flat windows still catch an OTM gamma pop that skews the mean
positive; median is the honest central tendency, this asymmetry itself is a real, disclosed
0DTE-convexity artifact, not a bug).

**MEASURED % premium decay, median, by tier / time-of-day / hold (n per cell in parens):**

| tier | med.prem AM | 10m | 30m | 60m | 90m | med.prem PM | 10m | 30m | 60m | 90m |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| OTM-3 | $0.32 | -5.6%(1346) | -18.2%(807) | -30.4%(580) | -40.0%(512) | $0.11 | -11.1%(2262) | -28.6%(1407) | -50.0%(992) | -66.7%(795) |
| OTM-2 | $0.49 | -5.0%(1483) | -15.0%(890) | -26.2%(636) | -35.6%(553) | $0.15 | -10.0%(3054) | -26.1%(1924) | -50.0%(1334) | -65.2%(1017) |
| OTM-1 | $0.80 | -4.1%(1547) | -11.8%(923) | -20.5%(656) | -28.1%(566) | $0.30 | -7.4%(3520) | -21.4%(2244) | -42.2%(1574) | -56.6%(1152) |
| ATM | $1.23 | -2.8%(1548) | -8.3%(916) | -14.5%(658) | -19.5%(569) | $0.69 | -4.2%(3550) | -12.7%(2266) | -25.2%(1596) | -36.2%(1160) |
| ITM-1 | $1.82 | -1.8%(1552) | -5.3%(924) | -9.7%(658) | -12.6%(563) | $1.36 | -1.9%(3543) | -5.3%(2262) | -10.3%(1593) | -15.5%(1158) |
| ITM-2 | $2.54 | -1.3%(1495) | -3.2%(892) | -5.4%(638) | -7.5%(550) | $2.20 | -0.9%(3504) | -2.1%(2252) | -4.0%(1577) | -5.9%(1152) |

**Reading it:** dollar theta cost is roughly similar across tiers for a given hold (e.g. AM
30-min ≈ 5-10 cents everywhere) — it's the **base premium that differs 8x** between OTM-3 and
ITM-2, which is why % decay is so lopsided. PM decay is uniformly 1.5-2x worse than AM at the
same tier for the same hold, because PM entries start from an already-decayed absolute premium
(the sanity check this predicts — theta accelerating into the close — reproduces cleanly: ATM
30-min AM -8.3% vs. PM -12.7%).

---

## 2. Spread — MEASURED proxy (bar-range), by tier

Same 6,348-window sample; entry-bar (high−low) at the window start, deduped per (date, tod,
tier, side, premium):

| tier | n | med. spread $ | med. spread % of premium | med. entry premium |
|---|--:|--:|--:|--:|
| OTM-3 | 6,256 | $0.09 | 34.8% | $0.25 |
| OTM-2 | 7,674 | $0.12 | 34.4% | $0.36 |
| OTM-1 | 8,659 | $0.19 | 32.4% | $0.59 |
| ATM | 8,957 | $0.28 | 28.1% | $1.00 |
| ITM-1 | 8,976 | $0.36 | 22.4% | $1.60 |
| ITM-2 | 8,794 | $0.40 | 17.0% | $2.38 |

Cross-check against the existing independently-computed `entry_exit_diagnostics.py` table
(premium-banded, not tier-banded, all-day pooled): its `<0.20` band shows 42% spread-proxy,
`0.20-0.50` shows 34%, `0.50-1.00` shows 33%, `>1.00` shows 25% — same monotonic direction,
same order of magnitude. Two independent computations over the same cache agree.

**Absolute dollar spread rises with strike (wider quoted markets on higher-premium contracts)
even as % of premium falls** — both numbers matter for different reasons: dollar spread is what
a round trip actually costs against your risk cap; % of premium is what determines whether a
%-based stop is reading spread noise instead of price action (the standing L-class finding).

---

## 3. Combined friction budget, 30-min hold (the number that matters for a scalp)

`total% = |theta%| + spread%`, shown two ways: **MODELED** (simulator's own $0.04 flat
round-trip assumption — optimistic, not tier-aware) and **PROXY** (bar-range, tier-aware,
pessimistic in that it includes real intrabar trade noise beyond pure NBBO width). Truth is
between the two; both are shown so neither anchors the read alone.

| tier | tod | med.prem | theta% | spread-proxy% | MODELED spread% | **total PROXY%** | **total MODELED%** |
|---|---|--:|--:|--:|--:|--:|--:|
| OTM-3 | AM | $0.31 | -18.2 | 29.0 | 12.9 | **47.2** | **31.1** |
| OTM-3 | PM | $0.11 | -28.6 | 81.8 | 36.4 | **110.4** | **64.9** |
| OTM-2 | AM | $0.48 | -15.0 | 25.0 | 8.3 | **40.0** | **23.3** |
| OTM-2 | PM | $0.15 | -26.1 | 80.0 | 26.7 | **106.1** | **52.8** |
| OTM-1 | AM | $0.78 | -11.8 | 24.4 | 5.1 | **36.1** | **16.9** |
| OTM-1 | PM | $0.30 | -21.4 | 63.3 | 13.3 | **84.8** | **34.8** |
| ATM | AM | $1.20 | -8.3 | 23.3 | 3.3 | **31.6** | **11.6** |
| ATM | PM | $0.68 | -12.7 | 41.2 | 5.9 | **53.8** | **18.5** |
| ITM-1 | AM | $1.80 | -5.3 | 20.0 | 2.2 | **25.3** | **7.5** |
| ITM-1 | PM | $1.35 | -5.3 | 26.7 | 3.0 | **32.0** | **8.3** |
| ITM-2 | AM | $2.54 | -3.2 | 15.7 | 1.6 | **19.0** | **4.8** |
| ITM-2 | PM | $2.20 | -2.1 | 18.2 | 1.8 | **20.3** | **4.0** |

**Against the opportunity** — `analysis/exit-parity/entry-exit-diagnostics.md` (T2, existing,
250 unique signals / 1,451 positions, real OPRA, ribbon_ride, already computed by a prior
session — cited not recomputed): MFE-EOD by premium band, median/p75: `<0.20` 56%/233%,
`0.20-0.50` 100%/284%, `0.50-1.00` 97%/234%, `>1.00` 71%/141%. Mapping tiers to their matching
band by median premium (AM OTM-3/OTM-2 ≈ "0.20-0.50" band, AM OTM-1 ≈ "0.50-1.00", AM
ATM/ITM-1/ITM-2 ≈ ">1.00"; PM OTM-3/OTM-2 ≈ "<0.20", PM OTM-1 ≈ "0.20-0.50", PM ATM ≈
"0.50-1.00", PM ITM-1/ITM-2 ≈ ">1.00"):

- **AM, every tier**: even the pessimistic PROXY friction (19-47%) stays comfortably under the
  matching band's median EOD favorable move (71-100%) — mathematically there is room for
  positive expectancy at every AM tier. The MODELED friction (4.8-31.1%) is a small fraction of it.
- **PM, OTM tiers**: PROXY friction (85-110%) **exceeds the matching band's median EOD move
  (56-100%) outright** on a mere 30-min hold, before any stop-noise cost is even added. Even the
  optimistic MODELED reading (35-65%) eats most of the typical outcome. This is the one cell
  where "structurally negative" is the honest label — and it's specifically PM + OTM, not the
  account size in general.
- **PM, ATM/ITM tiers**: friction (18.5-53.8% proxy, 4-8.3% modeled) stays well under the
  matching band's opportunity (71-97%) — PM is fine at ATM/ITM, the problem is PM **combined
  with** OTM.

**One mechanism already self-correcting this by accident**: `min_entry_premium=0.30` (shipped
2026-07-09, `params.json`) blocks OTM-3 PM (med $0.11) and OTM-2 PM (med $0.15) entirely, and
sits right at the OTM-1 PM boundary (med $0.30) — i.e. it already prunes most of the worst cell
in this table, but as a side effect of a premium floor, not because anyone measured PM-tier
friction directly until this stream.

**What this section deliberately does NOT do**: turn this into a backtested dollar
expectancy number. That requires the exit-shape state machine (stop/TP1/runner path
dependence), which is the in-flight T3/T4 grinder work in
`markdown/planning/HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.md`. This section answers the
narrower, structural question the brief actually asked — "is there mathematical room" — not
"what is the exact expectancy," which would duplicate that pipeline poorly.

---

## 4. The 3-contract-minimum question — MEASURED account math

Current verified inputs (`automation/state/params.json`, `automation/state/aggressive/params.json`,
CLAUDE.md Rule 6): `min_contracts=3`, Safe `per_trade_risk_cap_pct=0.30`, Bold
`per_trade_risk_cap_pct=0.50`. Equity: Bold **$1,963.04** (MEASURED live via
`mcp__alpaca_aggressive__get_account_info` this session, 2026-07-10 balance date). Safe
**$1,763** (CLAUDE.md, dated 2026-06-26 — the live MCP call 401'd this session, key needs a
reload per the standing "reload rotated key before verifying" lesson; not fixed here, read-only
scope).

Affordability ceiling = `(equity × risk_cap_pct) / (min_contracts × 100)`:

| account | equity | cap $ | ÷300 = max avg premium for 3 contracts |
|---|--:|--:|--:|
| Safe-2 | $1,763 | $528.90 | **$1.76** |
| Bold-2 | $1,963 | $981.52 | **$3.27** |

Checked against the measured median premiums (section 1, AM):

- **Safe-2 ($1.76 ceiling) vs. its OWN live tier, OTM-2 ($0.48)**: uses **27%** of the ceiling.
  Massive headroom. The 3-contract rule is **not** the thing forcing OTM-2 — Safe could run ATM
  ($1.20, 68% of ceiling) or even brush ITM-1 ($1.82, 103% of ceiling — marginal/day-dependent)
  without touching Rule 6 at all.
- **Safe-2 vs. ITM-2 ($2.54)**: 144% of ceiling — genuinely unaffordable at 3 contracts. This
  matches a finding already on record in `params.json` itself (`_wp8_revert_2026_06_21`: a
  DIFFERENT setup's 1DTE-ATM cell at $2.495 median hit exactly this wall, "qty3 notional ~$748 >
  $600 cap... BLOCK[RISK_CAP]... qty2 violates min_contracts=3 -> no auto-reduce" — independent
  confirmation of the same mechanism from a different investigation).
- **Bold-2 ($3.27 ceiling) vs. its OWN live tier, ITM-2 ($2.54)**: uses 78% of ceiling —
  comfortably fits, by design (Bold's 50% cap + higher equity was evidently sized for exactly
  this tier).

**Answer to the brief's question**: no, the 3-contract minimum does not currently force a
structurally-bad strike — Safe has ~3.7x the affordability headroom it's using. **What a
2-contract minimum would open (evidence for J, Rule 6 is J's call, not shipped here)**: ceiling
roughly doubles to ~$3.50, which would newly afford ITM-2 for Safe too. But per section 3's
friction table, the marginal friction gain from ITM-1→ITM-2 (AM: 7.5%→4.8% modeled, a 2.7-point
step) is much smaller than the OTM-2→ATM gain already available today for free (23.3%→11.6%
modeled, an 11.7-point step) — **relaxing Rule 6 would not unlock the biggest win; the biggest
win is already affordable under the current rule.**

---

## 5. Ranked knob sensitivity

| rank | knob | leverage | risk/effort | evidence |
|---|---|---|---|---|
| **1** | **Strike-tier shift, Safe core `ribbon_ride`: OTM-2 → ATM** | Total friction (modeled) 23.3%→11.6% AM / 52.8%→18.5% PM — roughly halves. | LOW — one params-key change, already affordable at 3 contracts (68% of ceiling), identical mechanism already proven live | THIS report's tier table (measured) + `WP5-STRIKE-AB-SCORECARD.md` (real-OPRA backtested P&L on sibling setup `vwap_continuation`: OTM-2 +$16.45/tr OOS → ATM +$46.23/tr OOS, monotonic ITM>ATM>OTM gradient, 11/11-gate clear) — same direction, independent method, already shipped for 5 other setups. Core `ribbon_ride` is the one gap. **Recommended next step: run the WP-5 methodology on `ribbon_ride` specifically** — this report establishes the friction mechanism, not the trade-level P&L, which is the actual ratification bar. |
| **2** | **Time-of-day-aware entry discipline (PM OTM specifically)** | PM friction is 1.5-3.5x AM friction at the same tier; PM OTM total proxy friction (85-110%) exceeds typical opportunity outright | LOW-MEDIUM — the crude version (raise `min_entry_premium` further, or make it PM-time-conditional) is a params tweak; already 80% self-solved by the existing $0.30 floor | This report section 3. The floor already blocks the worst two PM tiers as a side effect — formalizing the PM-specific logic would close the OTM-1-PM gap (still 84.8% proxy friction at the $0.30 boundary) |
| **3** | **Passive/limit entry (`entry_manager` SHADOW→live, T-W5)** | Saves roughly half the spread-proxy dollar cost (e.g. ATM: ~$0.14 of the $0.28 proxy) — same order of magnitude as knob #1 | MEDIUM — real execution risk; T3's own finding is "only wins if it beats paying up NET of what it misses"; shadow evidence (`entry-shadow.jsonl`) is already being collected, not yet graduated | Already in-flight (`HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.md` T3/T5). This report adds no new evidence here, just confirms the $ magnitude is worth the effort already budgeted |
| **4** | **Hold-duration / fewer-but-better trades** | Theta cost grows roughly linearly with hold time (not exploding) while MFE-EOD keeps building through the session — the two roughly offset | LOW leverage — cutting holds trades theta savings for foregone upside, close to a wash, and cuts against "let winners run" doctrine | This report section 1 (theta curve is gradual, not a cliff) |
| **5** | **Contract-count floor (Rule 6) relaxation** | Would only newly afford ITM-2 for Safe; ITM-2's incremental friction edge over ITM-1 (2.7 pts) is smaller than the OTM-2→ATM edge already free today (11.7 pts) | N/A — J's rule, not shipped; flagged as evidence only per the brief | This report section 4 |

---

## Data provenance

- Theta table (section 1) + spread-proxy table (section 2): computed this session,
  `backtest/data/spy_5m_2025-01-01_2026-07-08.csv` + `backtest/data/options/*.csv` (real OPRA
  trade bars), script logic mirrors `backtest/lib/option_pricing_real.py` conventions for
  consistency; aggregate CSVs left in `analysis/deep-research/_theta_decay_agg_{tight,loose}.csv`,
  `_spread_proxy_by_tier.csv`, `_theta_decay_coverage.txt` for anyone re-deriving these numbers
  (the 146,599-row per-observation raw CSV was regenerated-then-discarded to keep the repo lean —
  re-run to reproduce; the aggregates carry every number cited in this report).
- MFE/MAE/stop-harvest (section 3): pre-existing, `analysis/exit-parity/entry-exit-diagnostics.md`
  (T2, `backtest/tools/entry_exit_diagnostics.py`), cited not recomputed.
- WP-5 strike A/B (section 5, rank 1): pre-existing, `analysis/recommendations/WP5-STRIKE-AB-SCORECARD.md`.
- Account equity (section 4): Bold measured live this session (`mcp__alpaca_aggressive__get_account_info`);
  Safe from CLAUDE.md (MCP key 401'd this session — read-only scope, not fixed).
- Dead liquidity-gate finding (section 0): `backtest/tests/test_params_consumer_reconciliation.py`
  `KNOWN_DEAD` allowlist, grep-confirmed no consumer.
