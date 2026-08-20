# WEEKLY-OPTIONS PROGRAM — the second lane (living doc)

> **Status (2026-08-18 ~23:00 ET): MACHINERY BUILT + FIRST VERDICT IN — the v1 signal is DEAD.**
> Ingestion, multi-day walk, delta-matched selection, exits, gates and the null harness are all
> built, guarded and committed. Their first act was to kill the v1 signal: all four expiry arms
> lose and every one FAILS the random-entry null
> ([`WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md`](../../analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md)).
> Nothing is armed; `params.json` is untouched; no account exists. **The lane is not dead — the
> signal is.** Next work is signal diagnosis (§9b phases 8+), not wiring a trigger that loses.
>
> **Original status line, kept for provenance:** PHASE 0 — DESIGN COMPLETE, BUILD PENDING. J directed the expansion 2026-08-18
> ("turn this from a 0DTE shop into a full-blown option shop"). Research + design synthesis:
> [`analysis/deep-research/OPTIONS-SHOP-EXPANSION-2026-08-18.md`](../../analysis/deep-research/OPTIONS-SHOP-EXPANSION-2026-08-18.md).
> This file is the program's ONE canonical home — status line above updates as phases land
> (OP-22: append here, never a parallel doc). Supersedes-in-part:
> [`CROSS-TICKER-BRAINSTORM-2026-07-10.md`](CROSS-TICKER-BRAINSTORM-2026-07-10.md) (banner added there).
>
> **Update log:** 2026-08-18 — created (design ratified by J's directive; nothing armed, no code shipped yet).

---

## 1. What this program is — and is not

- **Is:** a second, isolated trading lane — directional **weekly options** (calls/puts, long
  premium) on a pilot basket of liquid non-SPY underlyings, traded on the SAME edge thesis as
  the core shop: **level interaction** (rejection, reclaim, S/R flip+retest) per FOCUS-DOCTRINE
  §2. Multi-day holds (the point of weeklies), shadow-first, paper-only.
- **Is not:** a scaling of a proven edge (the SPY book fails live-readiness today — WR 21–27%,
  negative expectancy, all 5 arms, `analysis/recommendations/live-readiness.json` 2026-08-18).
  This is **edge-search**: the hypothesis is that the level thesis pays better on ~18–19%/day
  theta surfaces (broker-verified 3DTE ATM, all six pilot names) than on 0DTE SPY's
  100%-same-day cliff. If the hypothesis is wrong, the kill criteria in §8 fire.
- **Non-comparability doctrine (crypto-twin rules):** weekly-1 P&L is NEVER evidence for or
  against any SPY parameter, and vice versa. Findings here propose changes to weekly files
  only. The SPY book and its doctrine are untouched by this program's existence.
- **Relationship to the 10 rules:** the 10 rules apply verbatim (no setup no trade, trigger
  discipline, defined stop, no adding, per-account kill switch, journal-everything, Gamma
  vetoes). The v15 *mechanics* under them are re-derived for weeklies in §4.

## 2. The universe (verified 2026-08-18 — re-verify cadence before relying on a specific day)

**Pilot basket (v1):** **GLD, QQQ** → **+NVDA after 2026-08-26 earnings** → wave 2: TSLA, AAPL.
**Parked:** RIVN (Friday-only; $0.17–0.19 ATM premium where the spread is 11–19% — our own
sub-$0.20 noise-floor lesson; sizing-to-cap needs ~75 contracts). **Avoid:** XBI, NIO, DIA.

| Fact (2026-08-18) | GLD | QQQ | NVDA | TSLA | AAPL | RIVN |
|---|---|---|---|---|---|---|
| Expiry cadence (live-chain-verified) | **Daily** | **Daily** | M/W/F | M/W/F | M/W/F | Fri-only |
| ATM weekly spread (closing quote) | 2.7% | 1.1% | **2.15%** | 3.8% | 8%* | 11–19% 🚨 |
| 3-contract ATM cost vs $1,580 cap | $891 ✅ | $1,632 ⚠️ OTM-1 | $837 ✅ | $1,569 ⚠️ | $969 ✅ | n/a |
| Next earnings | none (ETF) | none (ETF) | **8/26 AMC** | ~late Oct | 10/29 | ~Nov |

*AAPL closing print; 35K OI says it tightens intraday — verify before first trade.
Unpublicized finding: GLD/XLF/SMH quietly run TRUE DAILY expiries (same as SPY/QQQ/IWM).
NVDA's 8/26 Wednesday expiry is NOT LISTED (earnings that day) — expiry-selector must read
the actual chain, never assume a calendar. Full 30-name tier tables: synthesis doc, Finding 1.

## 2b. HOT ≠ TRADEABLE — the sector screen's actual finding (2026-08-18 night)

J asked to trade "what's hot, what's the sector." Both halves were run: the heat scanner ranks
the sectors, and a live options-liquidity screen asks whether the hot names can actually be
traded at $5K. **They mostly cannot, and that is the finding.**

Heat ranking (own data, independently reproducing the night's web research):
**GDX +21.7% 1M RS (#1)** · XLE (#2) · XLV (#3, already weakening) · laggards XLU/XLC/XLY.

Now the same names put through the options screen (ATM, nearest expiry ≥3 DTE):

| Tradeable at $5K | spread | | Hot but UNTRADEABLE | spread |
|---|---|---|---|---|
| QQQ | 1.7% | | AEM *(+37%, hottest name)* | **45.4%** |
| IWM | 2.0% | | WPM *(+28%)* | **95.5%** |
| GLD | 2.7% | | FNV | 42.8% |
| CVX | 2.9% | | B *(Barrick, +21%)* | 42.4% |
| XOM | 3.6% | | GDX *(the ETF itself)* | 20.7% |
| *(NEM 7.6%, SLV 6.1%, XLE 10.7% = tier 2)* | | | PSX / MPC | 39.6% / 43.7% |
| | | | XLV / JNJ / LLY | 44.8% / 15.8% / 16.1% |

**The actionable rule this produces:** *express a hot theme through its most liquid vehicle, not
its best-performing name.* Gold is the #1 theme — and the way to trade it is **GLD at 2.7%**,
not the miners at 20–95%. Energy is #2 — and the way to trade it is **XOM/CVX directly** (3.6%
/ 2.9%), not XLE (10.7%) or the refiners (~40%). A 45% spread means a trade must gain 45% just
to break even; no edge survives that, so chasing the hottest *name* is how this lane would have
bled out quietly.

This also retires the "expand to many tickers" impulse honestly: after screening, the genuinely
tradeable weekly universe for this account is **small — roughly QQQ, IWM, GLD, XOM, CVX, plus
the already-known SPY/NVDA/AAPL/TSLA tier**. Breadth is constrained by liquidity, not by ideas.

⚠️ **Caveat, and it is real:** these quotes were snapshotted ~23:00 ET on the free INDICATIVE
feed. After-hours spreads run wider than intraday. Evidence they are still informative: GLD
screened 2.7% here and 2.7% in the independent daytime screen, QQQ 1.7% vs 1.1% — liquid names
are stable while illiquid ones blow out. So the TIER1 set is trustworthy; the AVOID
classifications for mid-liquidity names (NEM, COP, JNJ) should be **re-verified during RTH**
before being treated as final. Open-interest came back empty from this feed — a known gap.

## 3. Where it trades — the `weekly-1` arm

**ONE new dedicated Alpaca paper account.** Never on the SPY core accounts:
`fleet_broker.is_flat_spy_options`/`close_all_spy_options` (+4 duplicate sites, §5) filter
`startswith("SPY")` — a TSLA/GLD position on a core account is invisible to the flat-check and
EOD-flatten (an automated, permanent C11). Never a repointed SPY arm (evidence-trail
destruction — the 2026-07-11 repoint scar). Never per-sector accounts before evidence
(the r=0.846 "one bet in five sizes" lesson). Split per-underlying only after the basket
clears the fleet `promotion_gate` (n≥30 clean, OOS+, WF≥0.70, sub-window stable, anchor-no-regression).

Planned `accounts.json` arm entry (added as `pending_build` at build time — schema precedent:
the futures arms already sit in the same array with their own `instrument` values):

```json
{
  "id": "weekly-1",
  "display_name": "WEEKLY-BASKET (paper, pending)",
  "status": "pending_build", "execution": "weekly_rest", "live": false,
  "fidelity": "real_fills", "broker": "alpaca_weekly",
  "account_number": null,
  "key_ref": "automation/state/fleet/secrets.json :: accounts.weekly-1",
  "instrument": "WEEKLY_OPTION_MULTI",
  "underlyings": ["GLD", "QQQ", "NVDA", "TSLA", "AAPL"],
  "config_source": "automation/state/weekly/params.json",
  "starting_equity": 5000.0,
  "note": "Edge-search lane. Crypto-twin non-comparability doctrine: P&L never SPY evidence. Multi-day holds — EXEMPT from same-day EodFlatten by design. Kill criteria: WEEKLY-OPTIONS-PROGRAM.md §8."
}
```

## 4. The v1 rule set (weekly mechanics under the unchanged 10 rules)

| # | 0DTE mechanic | Weekly v1 rule | Why |
|---|---|---|---|
| 1 | Level entry, chart-structure stop | **Keeps** — same trigger logic on daily/4h/1h zones per symbol | Core edge thesis transfers |
| 2 | SPY only | Per-ticker liquidity gate: ATM spread ≤5% of premium AND real OI, checked at entry time | Single names vary; closing screens lie |
| 3 | Expiry = today | **Min DTE ≥3 at entry**: Mon–Tue entries may use this-Friday; Wed–Fri entries use NEXT Friday. Selector reads the live chain (earnings gaps exist) | Same-week bought midweek is already on the steep decay curve |
| 4 | Delta = tier table | **0.40–0.70Δ** (ATM to slightly ITM) | Directional-swing convention; survives adverse days |
| 5 | Flat by 15:50 ET | **Days-to-live budget set at entry (default 3 trading days)** + theta budget (exit if premium bleeds >40% with thesis unprogressed) + **close by Friday 15:30 ET — NO weekend holds in v1** | Replaces EOD-flatten; kills weekend gap+theta class entirely |
| 6 | Overnight never happens | Overnight holds allowed Mon–Thu at **×0.5 size multiplier** on the standard formula; reduce into close | Chart stop is inert overnight; single-name gaps ~2× SPY |
| 7 | No earnings exist | **Earnings blackout: no entry ≤3 sessions before that name's print; never hold through any print.** IV-rank logged per entry (favor IVR 0–30) | IV crush beats correct direction; MIT-documented retail leak |
| 8 | −50% catastrophe premium cap | **Keeps** (both sides) | Long premium unchanged |
| 9 | TP1 +30–100%/trail/runner | Shapes inherited as STARTING values, re-fit on real weekly fills before trusted | %s were validated on SPY fills only (Class B by evidence) |
| 10 | Long premium only | **Keeps for v1.** Debit spreads deferred to v2 (exit_manager can't price spread P&L; don't ship two unknowns) | Consequence accepted: v1 simply never trades event windows |
| 11 | Min 3 contracts, 30% cap | **Keeps** (min 3 = 2 TP + 1 runner; 30% of weekly-1 equity) | Sizing doctrine transfers |
| 12 | Kill switch −30%/day | **Keeps, per-account** on weekly-1, isolated from all SPY arms | Rule 5 verbatim |

## 5. Wiring map — what actually changes (from the coupling audit, file:line verified 2026-08-18)

**Reused as-is (proven symbol-generic — crypto twin imports them verbatim):**
`automation/state/fleet/exit_manager.py` (all %-of-premium; `TIME_STOP_ET` is already
params-configurable — weekly params set the Friday close-out instead),
`fleet_executor.py`, `strategies.py` (exit shapes), `backtest/lib/risk_gate.py`,
`crypto/lib/market_structure.py`, most of `fleet_broker.py`.

**Generalize (small, mechanical):**
- `fleet_broker.py:82-129,466-484` — `open_spy_option_positions`/`is_flat_spy_options`/
  `open_spy_option_positions_checked`/`close_all_spy_options` → take `symbol_root(s)`.
- Same fix propagated to the 4 duplicate sites: `setup/scripts/atomic_bracket_guard.py:84`
  (also fix the `symbol[9]` fixed-index OCC parse — wrong for 4-char roots),
  `entry_location_shadow.py:99`, `fast_path_executor.py:359,369`, `trade_today_watcher.py:81`.
- `crypto/lib/strike_selection.py:184` — `atm_strike = round(spot)` assumes $1 strikes; needs
  per-symbol strike-increment awareness (TSLA/NVDA/AAPL trade $2.50/$5 rungs at these prices).

**New (genuinely absent logic):**
- `weekly_expiry_selector` — resolve target Friday (or M/W) from the LIVE chain per §4 rule 3;
  never calendar-assume (NVDA 8/26 is missing from the chain).
- `weekly_core` — thin SEE/DECIDE: per-symbol level zones (daily/4h/1h) + market_structure +
  the §4 gates → shadow ledger → (later) fleet ACT lane. **`heartbeat_core.py` is NOT reused**
  — its SEE/DECIDE is SPY-entangled (its own crypto-twin precedent says the same) and its
  expiry logic is `_et_now()` (heartbeat_core.py:2445).
- Per-symbol state: `automation/state/weekly/{params.json, key-levels-<sym>.json, shadow-ledger.jsonl}`
  — the existing key-levels/today-bias schemas are symbol-less by design; we do NOT attempt the
  503-file `"spy"`-field rename.
- Sector-heat scanner (§6) + nightly weekly-lane premarket task (levels per basket symbol).
- Scheduled tasks at build time: `Gamma_WeeklyCore` (RTH cadence TBD at build), `Gamma_WeeklyLevels`
  (premarket), `Gamma_SectorHeat` (nightly). weekly-1 is EXEMPT from same-day EodFlatten by design.

**Explicitly not touched:** `heartbeat_core.py`, SPY params files, the 10 rules, all SPY arms.
**Zero backtest history exists for any new symbol** (spy_5m/OPRA caches are SPY-only by
construction) — the lane starts as a mechanism trial; real fills are the only evidence.

## 6. Sector-heat scanner (the "what's hot, when" instrument) — $0, nightly

15 tickers (11 SPDRs + SMH, GDX, IWM; SPY benchmark) from daily bars (Alpaca/yfinance):
RS-vs-SPY (1w/1m/3m) + simplified RRG quadrant (Leading/Weakening/Lagging/Improving) +
MA-stack score + top-10-holdings breadth + dollar-volume-change flow proxy →
cross-sectional composite → rank; top-3 sectors get their liquid top-10 holdings ranked.
Output: `analysis/sector-heat/{date}.json` + one-line verdict into the premarket brief.
**Selection layer ONLY — never an entry signal; the §4 gates still decide every trade.**
Full formula + schema: synthesis doc Finding 5. Seasonality worth encoding: September
trend-conditional gate (SPX vs 200dma); earnings-cluster calendar (semis run offset fiscal
years). Killed folklore: "sell in May", gold-September (sources contradict).

Current snapshot (2026-08-18, goes stale fast): 🔥 XLE +9.9%/1M · XLV +6.6% (3M leader) ·
XLK +5.6% but rolling over. 🥶 XLU/XLRE/XLC. Backdrop: 30-yr ~5.3% (2-decade high), VIX ~15.8,
FOMC 9/16, NVDA 8/26 · MRVL 8/27 · AVGO 9/2.

## 7. Build order (order-of-operations only — no time estimates)

**Phase 0 — autonomous, no J dependency (queued: `automation/overnight/queue.md` WEEKLY-OPTIONS-BUILD):**
1. `automation/state/weekly/params.json` (v1 rules §4 encoded; own kill-switch/cap/hold-model).
2. Generalize the SPY-prefix helpers + 4 duplicate sites + strike-increment fix (§5) — with
   guard tests that RED on regression (engine-wins loop rule).
3. `weekly_expiry_selector` + tests against the live chain (incl. the NVDA-8/26-missing case).
4. Sector-heat scanner + first `analysis/sector-heat/{date}.json`.
5. `weekly_core` SHADOW mode: levels for GLD+QQQ, would-be entries/exits → shadow ledger.
   Pre-registration frozen before first row (see §8).
6. Add `weekly-1` to `accounts.json` as `pending_build` (blast-radius check first: confirm
   fleet_executor skips non-active arms — the futures-arm precedent says yes, verify anyway).
7. TV watchlist + journal scaffolding (`journal/` entries tag `arm=weekly-1`).

**Phase 1 — J, blocking (~5 minutes, the ONLY human steps):**
8. Pick login → dashboard **Open New Paper Account** ($5,000 suggested) → confirm options
   Level 3 shows → generate key+secret → paste directly into gitignored
   `automation/state/fleet/secrets.json` under `accounts.weekly-1` (never through chat).

**Phase 2 — autonomous, after the key lands:**
9. `load_creds()`/`get_account()` read-only self-check; fill real account number into
   accounts.json; dry-run the new symbol-scoped flat-check against the (flat) account.
10. Shadow → paper: first real weekly-1 orders only after the §8 shadow bar clears.
11. Wave 2 symbols (NVDA post-8/26, TSLA, AAPL) + debit-spread v2 design — each gated on §8.

## 8. Pre-registered gates and kill criteria (frozen 2026-08-18, before any data exists)

- **Shadow → paper bar:** ≥10 valid shadow signals across ≥10 distinct sessions, with sane
  mechanism (entries at levels, exits per §4, no gate misfires). <10 signals in 20 sessions =
  the setup doesn't occur on these surfaces → **kill or re-scope universe.**
- **Paper evidence bar:** the fleet's own `promotion_gate` (n≥30 clean trades, OOS-positive
  framing per real fills, WF≥0.70 where applicable, anchor-no-regression vs doing nothing).
- **Program kill:** after ≥30 real-fills trades, basket expectancy below the CONCURRENT SPY
  book's → kill the lane, fold lessons, keep the scanner if it independently earns its keep.
- **Scanner kill:** top-3 sector picks show no lift vs equal-weight null after 60 sessions.
- **Safety halt:** any position-visibility incident (C11 class) → lane halts until root-caused.
- **Live money:** never without J (OP-0 #1) — unchanged, forever, regardless of paper results.

## 9a. THE MULTI-SYMBOL LANE (v2) — WHERE "TRADE OTHER NAMES" ACTUALLY STANDS

> J, 2026-08-19: *"I still don't really know where that stands."* Fair. This section is the
> one-glance status surface for the original ask — trading names beyond SPY. Update it in place.

**What v1 got wrong (owned):** asked to trade other names, I invented a NEW signal for them
(level-interaction) and spent a night proving *it* fails. "My new signal failed" is not "other
names failed." **The engine we actually trade on SPY — `filters.py`'s 0-11 score driving
`ribbon_ride` / `vwap_continuation` / `vwap_reclaim_failed_break` — had never been pointed at
another ticker.** That is what the multi lane fixes.

**The v2 approach, per J's directive:** *"copy the entire spy engine and then paste it… you
don't touch the original, and then you make it so we trade other names… nothing should say hard
coded for spy."* A fork, not a refactor. The SPY engine is never imported or modified.

| Component | State |
|---|---|
| Account **PA38EG1JTFBT** ($9,628 — highest paper balance, options L3) | ✅ wired by REFERENCE (no secret copied); `verify_account()` refuses on account mismatch |
| Shared-account crypto safety | ✅ enforced in code — OCC-only filters; this lane cannot see or close the twin's BTC, and vice versa |
| ~70-name universe + LIVE liquidity gate | ✅ **SCREENED 2026-08-20: 11 TIER1 + 31 TIER2 = ~42 of 70 workable.** This CORRECTS §2b's "the tradeable universe is small (5 names)" — that was a 19-name screen at a 5% gate; a 70-name screen at the lane's 8% gate is far broader. TIER1: SPY 1.2%, SLV 1.8%, GLD 2.6%, NFLX 2.7%, PLTR 2.8%, SOFI 3.7%, IWM 3.8%, HOOD 3.8%, QQQ 3.9%, BAC 4.3%, RIVN 4.8%. Several are cheap enough to hold concurrently (SOFI $162/3-lot, RIVN $188, BAC $279, SLV $342). **RIVN screens TIER1 here after being parked in §2b** — that parking was based on a single after-hours snapshot at a different expiry. Prices spot-verified against daily bars. |
| Scanner stack (movers / actives / news / gap+RVOL / composite) | ✅ 31 tests; flagged MRNA on all 4 scanners at 9.8x RVOL |
| Broker + position layer | ✅ 39 tests; crypto-safety + fail-loud RED-proofed |
| Signal/scoring core (SPY score, symbol-generic) | 🔄 building |
| Sizing / risk / expiry | 🔄 building |
| Engine tick (`multi/core.py`) | ✅ **COMPLETE end-to-end.** funnel → signal → risk → expiry → strike → liquidity → sizing → WOULD_PLACE row. 12 guards including an AST-parsed no-order-path test (RED-proofed: injecting `place_bracket` fails it by line number, and a second guard independently flags it as a non-read broker call). |
| Live shadow run over the universe | ✅ **RUNS.** 40 symbols → funnel filtered 35 → 5 examined → 1 directional → real contract selected. Chain reads dropped 40→1. |
| **Scheduled: `Gamma_MultiCore`** | ✅ **REGISTERED + VERIFIED** — 09:35 ET daily, repeating every 15 min for 6h10m, NextRunTime confirmed non-null. **15-min, not 1-min**: this is a multi-day lane, the funnel already cuts to ≤5, and a multi-day thesis does not change between minutes — copying the SPY engine's 1/min cadence would be cargo-culting the number instead of the reason. |
| **THE MISSING LINK (found + fixed)** | 🐛 Filter 10 requires a LEVEL-TIED trigger; `core.py` passed **no levels**, so it vetoed **100% of symbols on every tick, forever**, while reading as “no setups today”. The SPY engine's level source is a single-symbol file whose schema has no symbol field — it cannot generalize. Built `multi/lib/levels.py` (swing pivots, prior day/week extremes, price-scaled round numbers, ATR-deduped so one price is one level). Directional signals **0 → 3** immediately. Found by the participation cascade, not by luck. |
| Paper orders | ⬜ gated on shadow evidence |

**Separation guarantees:** not registered in the SPY fleet's `accounts.json` (that file is read
by the live SPY executor); own params, own state dir, own ledger. Its P&L is never SPY evidence
and vice versa. Because the account is shared with the crypto twin, **account equity is not
evidence for either program** — each reads its own ledger.

## 9c. CLASSIFICATION, AWARENESS, AND THE NOISE FUNNEL (J's questions, 2026-08-19)

### What is this thing called, and how does it classify?

J: *"how does this new arm get classified? ...obviously we can say the spy arm or whatever."*

The existing taxonomy had one level and it was overloaded. Made explicit now — **two levels:**

| Level | Meaning | Members |
|---|---|---|
| **LANE** | an instrument/universe PROGRAM — its own engine, state, ledger, evidence | `spy-0dte` · `multi-symbol` (new) · `futures` · `crypto-twin` · `kalshi` |
| **ARM** | a RISK PROFILE inside one lane — differs ONLY by sizing/gates/stop | spy-0dte: safe-2, bold-2, safe-3, risky-1, risky-3 |

This matters because the standing rule *"arms are risk profiles, NOT strategies"* was being
strained: the new lane is not a sixth risk profile on SPY, it is a different **lane** with a
different instrument universe. Inside it, `multi-1` is currently its only arm; future
`multi-safe` / `multi-bold` arms would be risk-profile variants **within** the lane, exactly
like the SPY fleet.

**Formally:** LANE `multi-symbol` · ARM `multi-1` · instrument class `MULTI_SYMBOL_OPTION` ·
account `PA38EG1JTFBT` (shared with the crypto-twin lane; see the equity-is-not-evidence note in
§9a) · status SHADOW.

### How does Gamma become aware of it?

Four surfaces, in order of what a fresh session actually reads:

1. **`CLAUDE.md` tech-stack table** — one row, the minimum for a cold-start session to know the
   lane exists (context-budget-constrained; a pointer, not a description).
2. **This program doc** — the canonical home (§9a status, §9c design). MAP.md picks it up via
   `markdown/README.md` on the next vault sync; MAP.md is GENERATED and never hand-edited.
3. **`automation/state/multi/params.json`** — the machine-readable truth an engine reads.
4. **Its own ledgers** — `shadow-ledger.jsonl`, `participation-cascade.jsonl`, `watchlist.json`.
   Per the non-comparability doctrine these are the lane's ONLY evidence; account equity is not,
   because two programs share that curve.

### How does it pick what to trade out of ~72 names?

J: *"how does it filter out the noise of seventy different names?"* — **a funnel that narrows by
RANKING, never by thresholding** (`multi/lib/watchlist.py`):

| Stage | Keeps | Ranked on |
|---|---|---|
| 0 · universe | ~72 | static membership |
| 1 · liquidity | ≤40 | tightest live spread (measured NOW, not from a screen) |
| 2 · attention | ≤15 | **relative volume**, + %-move and scanner corroboration |
| 3 · setup | ≤5 | the engine's own 0–11 score |
| 4 · admission | ≤3 | risk / correlation / sector caps |

**Why ranked and not thresholded** — the two failure modes are opposite and both have bitten
this shop. Too loose is the "shotgun not sniper" problem (J, 2026-07-09). Too tight is L199 —
*"6 arms, 700 signals, 0 trades."* A threshold cut can match NOTHING on a quiet day; a ranked
cut always yields something to look at. **Guard:** `test_funnel_is_never_empty_on_a_quiet_day`,
RED-proofed — replacing the stage-2 ranked cut with a threshold immediately empties the
watchlist and the test names the failure.

**Why relative volume carries stage 2:** it is the only field comparable across a $18 stock and
a $700 ETF. A 5% day means something entirely different for SOFI than for JNJ; a 9.8× RVOL
reading means the same thing for both. Measured 2026-08-19: the scanner stack put MRNA at 9.8×
with all four scanners firing, on the day its $120 call ran open-to-high **+1,121%**.

Expensive per-symbol work happens on **5 names, not 72**. `stage_counts` is the funnel's own
participation cascade — "why is the watchlist empty" is a one-read answer, not an investigation.

### What it deliberately does NOT do

It does not predict. Every field is a backward-looking measured fact. Ranking by attention says
*"something is happening here"* — never *"this will continue."* Whether attention-ranked names
continue or fade is an open empirical question, unproven, and the entry decision still belongs
to the engine's own blockers.

## 9b. NIGHT RUN 2026-08-18 → 08-19 — the work order + progress ledger

> J went to bed 2026-08-18 ~21:44 ET with explicit standing authorization: *"do you have
> permission to build this out and backtest and device things and test and strategize and build
> all night… map it out, and then put yourself into a loop and get it done… don't skip anything."*
> This section is the MAP + the live progress ledger. **Any session resuming this work reads
> here first.** Update the checkboxes in place; do not create a parallel run doc (OP-22).
>
> **Standing authorization covers:** build, wire, test, backtest, experiment, screen, fix,
> document, commit — all paper/shadow, all git-revertible.
> **Still needs J (queued, never attempted autonomously):** (1) create the weekly-1 Alpaca paper
> account, (2) provision its API key, (3) arm live money (OP-0 #1), (4) two judgment calls —
> overnight-trim semantics and GLD's expiry-day cutoff class.

| # | Phase | Scope | State |
|---|---|---|---|
| 1 | **Stage-A core build** | 6 workstreams (signal core, earnings feed, expiry selector, exit gate, risk gates, sector heat) + weekly_core integrator + participation cascade | ✅ **DONE**, commit `b89e5f6c`. 8 agents, 0 errors. |
| 2 | **Review remediation** | Fix every CRITICAL/IMPORTANT the code review returns; re-run guards; verify the two LIVE-file edits (`exit_manager.py`, `option_pricing_real.py`) are provably inert for the SPY book | ✅ **DONE.** Review verdict `ship_with_fixes`: **0 critical, 1 important** — `check_capital_commitment` silently counted a malformed open position as $0 committed (understates exposure → overstates affordability → fails open in the one direction that over-commits). Fixed fail-closed; my own new guard then caught that a *missing* `qty` key still defaulted to 0 — fixed too. RED-proofed (4 fail on revert). **Live-book safety verified by running the suites myself, not by trusting the review:** 250 weekly + 109 pre-existing SPY tests green; `exit_manager`'s new fields never read by `plan_exit_actions`; `option_symbol` byte-identical for SPY across ~136 call sites. Notable worker override: the expiry agent verified against J's own WeBull fills that vendors emit OCC roots **unpadded** and implemented that over the formal 6-char OSI spec I had specified. |
| 3 | **Data ingestion** | `fetch_weekly_option_data.py` — liquidity-FILTERED contract selection (probe finding: coverage is volume-gated; filter by OI/volume BEFORE fetching or the set fills with 2-bar phantom series). Expiry-day bar handled specially (11-07 probe showed low 0.07 / 381k vol — pathological). Cache + coverage manifest | ✅ **DONE.** 180,873 real daily bars / 11,629 liquid contracts (GLD+QQQ, expiries 06-01→08-14), 10,309 with ≥5-bar multi-day paths. Integrity clean (0 flag-mismatch / 0 post-expiry / 0 hi<lo / 0 negative). **Two real bugs caught and fixed:** (a) paper key 401s against `api.alpaca.markets` — the contracts endpoint needs `paper-api`; (b) expiry-window and bar-window shared a start date, silently truncating 275 contracts (2.4%) to their expiry-day bar while still reporting "99% coverage" — fixed via `BAR_LOOKBACK_DAYS=45`, truncation 275→53, rows +37%. Regression guard RED-proofed. Data is gitignored (regenerable); the script is committed. |
| 4 | **Multi-day backtest harness** | `multiday_walk.py` + `weekly_fill_model.py` — position spans sessions, overnight gap-as-jump, weekend exclusion, %-of-spread fills. Disclose/fix the known zero-slippage optimism in `exit_manager_walk.py` BEFORE trusting any number | ✅ **DONE**, commit `68c0e239`. Delegates every exit decision to the LIVE `plan_weekly_exit_actions` (no live/backtest drift by construction). **Adverse-first resolution** is the headline safeguard: daily bars can't order a session's high vs low, so every ambiguous session is resolved against us — RED-proofed (disabling it makes a stop-breaching session book a win). Gaps fill at the open (stop is inert overnight); expiry-day exits use the open (pathological lows). Spread modeled explicitly at the live gate's 5% ceiling — pessimistic on purpose. Every row carries its disclosures. **The `exit_manager_walk.py` optimism concern is moot for this lane: it does not route through that module.** 11 guards green; smoke-tested on real cached bars. |
| 5 | **Freeze the prereg** | `analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json` — frozen BEFORE any result is looked at | ✅ **DONE**, commit `a346f111`. Genuinely frozen pre-result. Paired within-subject (every signal → a position in all 4 arms). Primary metric = % return on premium, explicitly NOT win rate (the edge is a right tail). Pre-committed decision rule incl. what a NULL authorizes, so it can't be re-sliced until something wins. Holm across 3 contrasts; random-entry-null at MAX mandatory. Position-size normalization named as the #1 confound (fixed contract counts would let the cheapest arm win as a pure leverage artifact). |
| 6 | **RUN the expiry experiment** | J's explicit ask: same-week vs next-week vs 2-weeks-out vs monthly. Paired/matched (same signal, N contracts), delta-matched, %-return-on-premium primary, Holm-corrected across the 3 contrasts, per-arm real-vs-synthetic completeness disclosed | 🔄 **PREREQ CLEARED**, commit `031094a7`. Density probe: **185 signals / 134 distinct sessions** (GLD 94/85, QQQ 91/88) → **SUFFICIENT** vs the prereg's n≥30. Distribution healthy: direction ~50/50, confluence spread 1–5, max 2/session, fires on 34–39% of sessions (under C27's >80% noise alarm). **Two silent bugs fixed in `bars.py` en route** — a missing `start` made every fetch return ZERO bars on all feeds, and missing pagination capped history at ~1 month while looking complete (192→1,505 hourly bars). **BS/IV solver DONE**, commit `8992d743` — delta-matching needs derived greeks (cached bars carry none); refuses to fabricate a vol in the vega dead zone, and the round-trip test caught a real bug where bisection's early-return bypassed that guard on the common path. **Data extended**: cache now spans Oct-2025→Aug-2026 expiries, **862K bars / 34,358 contracts**, so every arm incl. the 30-DTE monthly control has real contracts. **EXECUTED.** 171 paired signals (of 185) across the 3 weekly arms + 80 monthly-control. **Verdict: the which-Friday question is MOOT — every arm loses and every arm FAILS the random-entry null.** Full write-up: [`WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md`](../../analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md). Contrasts were Holm-significant (longer DTE = better median, shorter DTE = fatter right tail) but they compare *losing* strategies and authorize nothing. |
| 6b | **Findings to carry into the experiment** (from the density probe) | — | ⚠️ **CONCENTRATION:** `round_numbers` produces **~55% of all signals** (54/94 GLD, 48/91 QQQ) — and that family's increment heuristic was flagged *by its own author* as an unvalidated judgment call. Per C4, disclose this concentration in every downstream result; if the strategy pays, check whether it pays *only* through round numbers. ⚠️ **DEAD FAMILY:** `structure_hh_hl_lh_ll` produced **ZERO signals on both symbols** — either it never lands near price or it is redundant with `swing_high_low`. Investigate before trusting the 5-family design; a family contributing nothing is a dead knob (C14). |
| 7 | **RUN the strategy backtest** | The level-interaction thesis on weeklies, multi-day holds, across the basket. Random-entry-null MAX gate before ANY result is called promising | ✅ **DONE — and the answer is NEGATIVE.** Folded into phase 6's run (the expiry experiment IS the strategy backtest, paired across arms). **All four arms lose (−8% to −14% mean) and ALL FAIL the random-entry null gate.** Mechanism: `theta_budget` is the dominant exit (48–64%) — the trigger enters, price doesn't progress, decay kills it; only 12–22% reach TP1. Full adjudication: [`WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md`](../../analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md). |
| 8 | **Sector + universe screen** | J's ask ("different sectors, what's hot when"): run the heat scanner for real; screen a WIDE options-liquidity universe (not just the 6 named); report what is genuinely tradeable at $5K | ✅ **DONE.** Heat scanner live (14/14 scored, GDX/XLE/XLV top-3, independently reproducing the night's web research). Liquidity screen over 19 names → **HOT ≠ TRADEABLE**: the hottest name (AEM +37%) carries a 45% spread; WPM 95%. Tradeable set is small: QQQ/IWM/GLD/CVX/XOM. Rule extracted: *express a theme through its most liquid vehicle, not its best performer* (gold → GLD not miners; energy → XOM/CVX not XLE/refiners). Full table + RTH re-verify caveat: §2b. |
| 9 | **Wiring** | Scheduled tasks (EarningsRefresh, WeeklyLevels, WeeklyCore, FridayFlatten+Verify), `state_freshness_audit` registration, journal schema w/ lot linkage, `weekly-pulse` skill, obsidian sync block | ⏸️ **DEFERRED, deliberately — not skipped.** Registering recurring tasks to run a trigger that is *proven* not to work would create daily noise, a new C7 silent-failure surface, and the exact 'machinery that measures nothing' the pre-build critics flagged. **Unblocks the moment a signal variant clears the null gate** — the wiring spec is written (§5, §7) and unchanged, so it is a build task, not a design task. The one piece worth doing regardless is the earnings feed, which is already built and guarded (`031094a7`).
| 10 | **Shadow dry-run** | Run `weekly_core` against recent history; read the participation cascade. **The L199 question: does the gate stack EVER fire?** A lane that never trades is the #1 program risk | ✅ **ANSWERED EARLY, by better evidence than a dry-run.** The L199 zero-participation risk is **not realized**: the density probe fired 185 signals over 134 distinct sessions, and the experiment then walked 684 real positions end-to-end through selection→sizing→exits. The gate stack demonstrably fires. The lane's problem is the opposite of L199 — it trades plenty, and loses. A shadow dry-run would add nothing this did not already prove. |
| 11 | **Docs + commit + morning brief** | Fold corrections into this doc + the research record; commit in reviewable chunks; write J's morning brief incl. the 4 things needing him | ⬜ |

| 12 | **VARIANT #1 — daily trigger** (post-verdict experiment: is the 1H trigger too fast for a multi-day thesis?) | Scale the design up one timeframe, preserving slow-zone/fast-trigger separation: **zones from WEEKLY, trigger on DAILY** (zones-and-trigger both on daily would be circular — a daily BOS *is* a break at a daily swing). Weekly bars aggregated from daily; incomplete trailing week dropped | 🔄 **DENSITY MEASURED.** On GLD+QQQ alone: **29 signals — just under the prereg's n≥30**, i.e. the variant is ~85% less frequent than v1 (185→29), as expected when the trigger timeframe scales up. **Broadening to the 9 screened-liquid names restores power: 463 signals / 3.6yr → SUFFICIENT.** **RUN AND REFUTED.** 129 paired signals over 8 liquid symbols. The variant is **materially WORSE**: SAME_WEEK −23.5% (vs −8.1%), NEXT_WEEK −22.4% (vs −13.5%), and the **right tail SHRANK on every arm** (23.4%→17.1%, 18.7%→8.5%). Still fails the null gate. **The timeframe mismatch was not the cause — slowing the trigger moves away from the only thing that pays.** Leading hypothesis is now: the trigger detects VOLATILITY, not DIRECTION. Full write-up in the experiment doc. |

**Ordering rule:** phases 3→7 are the evidence spine and run in order. Phase 8 is independent and
may interleave. Phase 10 gates any claim that the lane "works." **Nothing in this list arms
anything or places an order.**

**Standing discipline for every iteration:** no result is reported as promising until it clears
the random-entry-null MAX gate; every new param gets a vary-and-assert; every producer fails
loudly; anything that looks too good gets the artifact hunt BEFORE it gets written up.

## 9. Documentation architecture (how/where this program journals)

- **This file** — canonical program state (status line + append log).
- `analysis/deep-research/OPTIONS-SHOP-EXPANSION-2026-08-18.md` — frozen research record.
- `automation/state/weekly/shadow-ledger.jsonl` — shadow decisions (machine).
- `journal/YYYY-MM-DD.md` + `journal/trades.csv` — weekly-1 trades journal WITH `arm=weekly-1`
  tags, same Rule-8 discipline as SPY.
- `analysis/sector-heat/{date}.json` — scanner output.
- ROADMAP.md carries the program as a PROPOSED row; MAP.md picks this file up via
  markdown/README.md on next vault sync. Dated studies FOLD here per OP-22.
