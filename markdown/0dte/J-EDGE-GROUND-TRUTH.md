# J's Edge as Automation Ground Truth — the Two-Tier Design

> **Status: DESIGN + SPEC (propose-only, Rule 9).** Nothing here is wired into
> `j_edge_tracker`, `regime_book`, `params.json`, or the heartbeat. This doc defines
> *how* J's real winning trades become the automation's ground truth and setup
> definitions — the "data rules" payoff. Authored 2026-06-19.
>
> **Companion docs:** [`markdown/0dte/J-WEBULL-EDGE-2021-2023.md`](J-WEBULL-EDGE-2021-2023.md)
> (the 2021-23 ledger + style stats), [`markdown/0dte/J-EDGE-SETUP-SPECS.md`](J-EDGE-SETUP-SPECS.md)
> (the per-archetype automation specs parameterized from his winners),
> [`markdown/research/REGIME-AWARE-BOOK.md`](../research/REGIME-AWARE-BOOK.md) (the book the specs slot into).
>
> **Inputs read:** `backtest/autoresearch/j_edge_tracker.py`,
> `backtest/lib/engine/regime_book.py`, `analysis/webull-j-trades/winner_setups.json`,
> `analysis/webull-j-trades/j_roundtrips.csv`, `analysis/webull-j-trades/j_style_stats.json`.

---

## 0. The thesis, in one paragraph

J's real winning trades are the richest ground truth Project Gamma has. They come in
**two populations that must be kept separate** because one is backtestable on our data
and one is not. The **3 in-era 2026 SPY anchors** (CLAUDE.md OP-16) sit inside our
2025-26 5m bar data *and* our OPRA option-quote cache, so they are **executable
backtest gates** — the engine can be run on those exact days and graded against J's
real P&L. J's **2021-2023 Webull SPX winners** are a far richer, balanced (bull+bear)
real-fills set, but they are **era-and-instrument-gapped**: SPX (not SPY), 2021-23 (not
2025-26), and entirely below our data floor. They cannot be a 2025-26 backtest input.
They serve a different, equally important role: a **pattern-level ground-truth
profile** — they define *what a J winner looks like* (archetype, VWAP alignment,
time-of-day, hold, size), which the automation's setup specs are parameterized *from*
and validated *against* at the pattern level. **Tier 1 gates the backtest; Tier 2
gates the setup definitions.** Conflating them would either (a) pretend 2021-23 SPX is
backtestable on 2025-26 SPY data (it isn't), or (b) throw away the richest behavioral
ground truth we have because it can't be replayed bar-for-bar. The two-tier design
uses each for exactly what it can prove.

---

## 1. Why two tiers — the data boundary is empirical, not asserted

The split is forced by **what data physically exists**, verified 2026-06-19:

| Data layer | Coverage on disk | Source |
|---|---|---|
| **5m SPY/VIX bars** | **2025-01-01 → 2026-06-16** | `backtest/data/spy_5m_*.csv`, `vix_5m_*.csv` |
| **OPRA option-quote cache** | **2025-01-02 (SPY250102) → 2026-05-29 (SPY260529)** | `backtest/data/options/*.csv` — 8,100 contract files |
| **1m high-res (anchor days)** | the 3 OP-16 anchor contracts present | `backtest/data/highres/SPY2604*.csv`, `SPY2605*.csv` |

Against that boundary:

- **The 3 OP-16 anchors are inside both layers.** Verified — `SPY260429P00710000.csv`,
  `SPY260501P00721000.csv`, `SPY260504P00721000.csv` all exist in the OPRA cache *and*
  as 1m high-res. `j_edge_tracker.score_candidate` already runs the engine on these days
  with `runner.load_data` and grades against J's real P&L. **They are executable today.**
- **J's Webull winners are below the floor by ~2-4 years.** Earliest is 2022-03-14;
  the data floor is 2025-01-01 (bars) / 2025-01-02 (OPRA). There is **no SPX or SPY
  bar/quote data for 2021-2023 in the repo at all.** A bar-for-bar backtest of these
  trades is *impossible on current data* — not "hard," not "lower-fidelity," but
  **literally unservable** (`runner.load_data` raises `FileNotFoundError` for any 2021-23
  window). The `winner_setups.json` features were reconstructed from *Alpaca IEX SPY 5m
  bars pulled live for each winner date* into `winner_candles.json` — a one-off
  research pull, **not** the backtest data path, and SPY-as-proxy-for-SPX, not the
  traded instrument.

So the boundary is not a modeling choice — it is the edge of the dataset. Tier 1 is
"what we can replay"; Tier 2 is "what we can characterize but not replay." Honesty
about this is mandated (the task brief, and lesson C22: gates proven on one era/account
don't transfer to another without fresh validation).

---

## 2. Tier 1 — In-Era Backtest Anchors (the executable edge-capture gate)

**What it is.** The 3 bearish 2026 SPY winners + 4 losers already in `j_edge_tracker`.
These are the OP-16 source-of-truth trades. They stay exactly as they are — this tier
is **unchanged by this design**; the design only *names* it as Tier 1 and clarifies its
scope relative to Tier 2.

| Role | Trades | In OPRA cache? | Backtestable? |
|---|---|---|---|
| **Winners (engine MUST take)** | 4/29 710P (+$342) · 5/01 721P (+$470) · 5/04 721P (+$730) | ✅ all 3 | ✅ yes |
| **Losers (engine MUST skip / lose less)** | 5/05 722P (−$260) · 5/06 730P (−$300) · 5/07 734C (−$45) · 5/07 737C (−$120) | ✅ all 4 | ✅ yes |

**How it gates automation (unchanged from OP-16):**

```
edge_capture = sum(engine_pnl on J's winning days)
             - sum(max(0, engine_loss on J's losing days))
```

- Max possible = **$1,542** (capture all 3 winners, add zero loss on the 4 loser days).
- `final_score = edge_capture × aggregate_sharpe`.
- A candidate with `edge_capture < $771` (50%) is **REJECTED** regardless of aggregate.
- Implemented in `j_edge_tracker.score_candidate` / `print_score_card`; run with real
  fills (`params["use_real_fills"]=True`) so the gate uses OPRA, not BS-sim (lesson C1).

**Scope honesty.** Tier 1 is **bearish-only** (all 3 winners are puts) and **n=3
winning days**. That is its known limitation — it can verify the engine captures J's
*bearish-continuation* edge and skips his *chop-trap* losers, but **by construction it
cannot reward a bull or mean-reversion setup** (there is no up-day winner to capture).
This is the exact selection-bias trap documented in `REGIME-AWARE-BOOK.md §1` and
`fleet-standalone-regime.json#method_contrast`. Tier 1 is necessary but **not
sufficient** to validate a multi-directional book — which is precisely why Tier 2 exists.

**This tier does not change.** No new days are added to `j_edge_tracker.J_WINNERS`.
The Webull winners are *not* SPY-2026 and are *not* backtestable, so adding them to the
Tier-1 list would silently break the gate (`runner.load_data` would raise on their
dates). They live in Tier 2 instead.

---

## 3. Tier 2 — Historical Pattern Ground Truth (the setup-definition gate)

**What it is.** J's 10 top Webull winners (5 bull / 5 bear, 2022-2023 SPX), with the
look-ahead-free archetype/VWAP/time/hold features already computed in
`analysis/webull-j-trades/winner_setups.json` (9 of the 10 have full feature rows; the
10th, 7/22 3950P, is in the ledger). This is the **balanced, multi-directional,
real-fills behavioral profile** Tier 1 lacks.

**What it proves — and what it explicitly does NOT.**

| Tier 2 CAN establish | Tier 2 CANNOT establish |
|---|---|
| *What a J winner looks like*: archetype, VWAP side, entry time-of-day, hold duration, size, prior-30m drift, new-extreme-or-not. | A 2025-26 SPY backtest P&L number. The instrument (SPX) and era (2021-23) are wrong and the data does not exist. |
| Which **archetypes** carry his real edge (pullback-continuation, trend-continuation, momentum-breakout, reversal-off-extreme), as a *population* profile. | That any single archetype's *population* WR is positive — n=9 hand-coarse, no VIX/level overlay (`J-WEBULL §"Step 3" caveat`). |
| The **parameter envelopes** the automation specs are drawn from (entry-window, hold-ceiling, VWAP-alignment requirement, 1-2 lot sizing — L168). | That those envelopes are *optimal* on 2025-26 SPY. They are *J's observed* values, to be re-validated in-era before any promotion. |
| **Direction balance** (5 bull / 5 bear) — corroborating that the edge is two-sided, not bear-only. | Anchor-no-regression in the OP-16 sense (these are not OP-16 trades and have no engine-replay P&L). |

**How it gates automation (the setup-definition gate):**

A setup spec in `markdown/0dte/J-EDGE-SETUP-SPECS.md` is **"J-grounded"** iff:

1. Its archetype appears in J's winner population (`winner_setups.json#archetype`), AND
2. Its entry conditions, trigger, VWAP-alignment rule, time-window, hold-ceiling, and
   sizing are **derived from the matching winners' feature rows** (not invented), AND
3. The spec's caveats disclose n, the era/instrument gap, and that the parameters are
   *observed envelopes*, not optimized values.

A spec that fails any of these is **not J-grounded** — it may still be a research
candidate, but it cannot claim J's real edge as provenance.

**Tier 2 is a PROVENANCE + DEFINITION gate, not a P&L gate.** It answers "is this
automated setup a faithful encoding of something J actually does profitably, at the
pattern level?" — it does **not** and **cannot** answer "does it make money on 2025-26
SPY?" That second question is answered only by an **in-era validation** (§5).

---

## 4. How the two tiers compose — the promotion pipeline

The two tiers are **sequential gates on the same promotion**, mapping cleanly onto the
existing `regime_book` `WATCH_ONLY → REGIME_ACTIVE` lifecycle (`REGIME-AWARE-BOOK.md §6`):

```
  J's Webull winners (2021-23 SPX)            J's 3 SPY anchors (2026)
            │                                          │
            ▼                                          ▼
   ┌──────────────────┐                    ┌──────────────────────────┐
   │  TIER 2           │                    │  TIER 1                   │
   │  pattern ground   │                    │  in-era backtest anchors  │
   │  truth            │                    │  (j_edge_tracker, OPRA)   │
   └────────┬─────────┘                    └────────────┬─────────────┘
            │ defines + parameterizes                    │ edge_capture ≥ 50%
            │ the SETUP SPEC                              │ + anchor-no-regression
            ▼                                            ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  regime_book SetupSlot: WATCH_ONLY                                │
   │  (spec authored, archetype→regime mapped, parameters from J data) │
   └──────────────────────────────┬────────────────────────────────────┘
                                  │  + in-era real-fills re-validation (§5)
                                  │    on REAL ★★★ levels, OOS sign-stable,
                                  │    DSR PASS, A/B scorecard filed
                                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  regime_book SetupSlot: REGIME_ACTIVE  (a one-line data edit)     │
   └─────────────────────────────────────────────────────────────────┘
```

**The rule:** Tier 2 gets a setup *defined and into the book as `WATCH_ONLY`* with
honest J-grounded provenance. **Promotion to `REGIME_ACTIVE` additionally requires the
existing `REGIME-AWARE-BOOK.md §6.1` bar**, of which Tier 1 (`edge_capture` +
anchor-no-regression) is one clause **for the bearish slot**, and an **in-era
re-validation** (§5 below) is the clause that substitutes for "anchor-no-regression" on
the **non-bearish** slots (which have no Tier-1 anchor by construction — see §6.1 bar 4:
*non-bearish slots need J's own logged winners for that setup*). Tier 2 is the
*upstream definition* gate; Tier 1 + in-era re-validation are the *downstream
promotion* gates. Neither alone is sufficient.

**Concretely, per direction:**

- **Bearish setups** (VWAP_TREND_PULLBACK bear-side, GAP_AND_GO bear-side,
  BEARISH_REJECTION): Tier 2 defines the spec; **Tier 1's `edge_capture` gate applies
  directly** (the 3 anchors are bearish), plus §6.1 bars 1-3,5.
- **Bullish / mean-reversion setups** (VWAP_TREND_PULLBACK bull-side, GAP_AND_GO
  bull-side, BULLISH_RECLAIM): Tier 2 defines the spec; **Tier 1 cannot gate them**
  (no bull anchor). Their promotion gate is §6.1 bars 1-3,5 **plus the in-era
  re-validation in §5** standing in for bar 4 — and per §6.1, **J's own logged 2026
  SPY bull winners** before going active. Until J banks bull winners on the live SPY
  engine, the bull specs stay `WATCH_ONLY` no matter how good the 2021-23 profile looks.

---

## 5. What a full era-matched validation would need (future option — a bigger lift)

The honest gap: **we cannot today turn the Webull winners into a 2025-26 backtest
number.** To *close* the gap — i.e. to backtest J's 2021-23 archetypes on matched data —
would require a **net-new data pull**, flagged here as a future option, not this task:

1. **A 2021-2023 SPY (or SPX/XSP) 5m bar pull** covering 2021-06-09 → 2023-10-03 (J's
   ledger span). ~2.3 years × ~78 5m bars/day × ~250 days/yr ≈ **45,000 bars** per
   instrument. Source: a vendor with that history (Polygon, Databento, Alpaca's older
   archive). Lands as `backtest/data/spy_5m_2021-06-09_2023-10-03.csv` so
   `runner.load_data` auto-discovers it.
2. **A 2021-2023 OPRA option-quote pull** for the strikes J actually traded (the
   `j_roundtrips.csv` symbols), so a *real-fills* replay is possible. This is the
   expensive part — OPRA history at 0DTE granularity for ~668 family round-trips is a
   large, possibly paid, pull. Lands under `backtest/data/options/` matching the
   existing `SPYYYMMDD{C,P}NNNNNNNN.csv` naming (or an SPXW-namespaced sibling).
3. **A VIX 5m series** for the same span (`vix_5m_2021-06-09_2023-10-03.csv`) so the
   regime classifier and VIX-character gates run.
4. **Instrument-scale reconciliation.** SPX ≈ 10× SPY; J's SPXW strikes map to SPY at
   /10. Either replay on SPX-native data (then no scale conversion, but the engine's
   strike-offset / sizing tiers are SPY-calibrated) or replay on SPY with the /10 map
   (then verify the strike picker matches — the OP-16 *sim-accuracy gate*: BS-sim
   ignoring strike_offset invalidated a whole weekend once).
5. **A regime-stratified, OOS-split re-eval** of each archetype on that matched data,
   filed as `analysis/recommendations/{archetype}-jera-validation.json`.

**Cost/effort flag:** items 1-3 are a data-acquisition lift (likely paid OPRA history);
item 4 is the same sim-accuracy discipline OP-16 already mandates; item 5 is a standard
eval run once the data lands. **Until then, Tier 2 remains a pattern gate, not a
backtest gate — and this design does not pretend otherwise.** The recommended sequencing
is to first exhaust the *in-era* path (re-validate the specs on 2025-26 real ★★★ levels
as the live archive banks, per `REGIME-AWARE-BOOK.md §6.1 bar 1`), since that data
already exists and the patterns transfer; the 2021-23 pull is the second-order
confirmation, worth it only if the in-era results justify the data spend.

---

## 6. The honest headline (do not overclaim)

- J's 2021-23 family book was **net −$12,885** over 667 round-trips (46.9% WR). The
  *edge* lives in his **small (1-2 lot), well-timed, trend/VWAP-aligned** trades
  (+$4,576 on 1-2 lots); the *account* went negative on **oversized, mistimed,
  counter-trend puts** (−$17,461 on 3+ lots). See `J-WEBULL-EDGE-2021-2023.md`.
- **What transfers to automation:** the *archetype definitions*, the *VWAP-alignment
  requirement*, the *midday time-of-day signal*, the *1-2 lot sizing discipline* (L168),
  and the *direction balance*. These are pattern-level truths that are instrument- and
  era-robust (a VWAP pullback in a trend is the same structure on SPX-2022 and SPY-2026).
- **What does NOT transfer:** a P&L claim, a WR claim, or any "this setup makes $X"
  number. Those require in-era validation (§5) the data does not yet support.
- **The data-rules payoff, precisely stated:** his winners *define and validate the
  setup specifications* (Tier 2) and his in-era anchors *gate the backtest* (Tier 1).
  His winners do **not** become a backtest P&L input — that would be the overclaim the
  era gap forbids.

---

## 7. Files

| File | Role |
|---|---|
| `markdown/0dte/J-EDGE-GROUND-TRUTH.md` | **This doc** — the two-tier design. |
| `markdown/0dte/J-EDGE-SETUP-SPECS.md` | The per-archetype automation specs parameterized from J's winners + the archetype→regime_book-slot mapping. |
| `markdown/0dte/J-WEBULL-EDGE-2021-2023.md` | The 2021-23 ledger, style stats, top-10 winners/losers, archetype tally. |
| `markdown/research/REGIME-AWARE-BOOK.md` | The regime book the specs slot into; §6 promotion lifecycle. |
| `backtest/autoresearch/j_edge_tracker.py` | **Tier 1** implementation (unchanged) — `edge_capture` on the 3 SPY anchors. |
| `backtest/lib/engine/regime_book.py` | The `WATCH_ONLY` book the specs target (unchanged). |
| `analysis/webull-j-trades/winner_setups.json` | **Tier 2** source — archetype/VWAP/time/hold feature rows. |
| `analysis/webull-j-trades/j_roundtrips.csv` | Full reconstructed ledger (1,221 round-trips; filter `is_spx_family` + `result=win`). |

**Next real step (not this task):** as the live ★★★ archive banks ~20-30 days,
re-validate each J-grounded spec on 2025-26 real levels (the in-era path), file
per-regime A/B scorecards, and promote any slot that clears `REGIME-AWARE-BOOK.md §6.1`
— a one-line data edit, not a rebuild. The 2021-23 era-matched pull (§5) is a
second-order future option.
