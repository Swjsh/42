# J-DAILY-TRADING-BOOK — what we actually trade every day, and what $2K can make

> Campaign synthesis (angles **D1 portfolio/coverage**, **D2 leaderboard**, **B1 strike-feasibility**) from
> [markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md](../research/J-DATA-RESEARCH-MASTER-PLAN.md). Turns the validated/candidate edges
> into the actual daily book.
>
> **Real fills / real chain prices. Honest.** Built by `backtest/autoresearch/daily_book_synthesis.py`
> (reuses the validated detectors + the real-OPRA fill loader; does NOT re-derive any edge). Scorecard:
> [`analysis/recommendations/daily-book-synthesis.json`](../../analysis/recommendations/daily-book-synthesis.json).
> Source scorecards: `gap-and-go-LIVE.json`, `j-daily-pattern-LIVE.json`, `chart-stops-ab-2026-06-18.json`.
> Window: 2025-01-02 .. 2026-05-29 (bounded by real OPRA option coverage), 351 trading days.

---

## TL;DR — the three answers

1. **What do we trade, in priority order?** (D2) The **everyday bearish-rejection book** is the P&L engine
   ($230/trade full-history, ~0.7 trades/wk). The **VWAP-continuation** edge is the *frequency* engine
   (~2.3 trades/wk, but a 6-of-7 WATCH, not yet live). **Gap-and-go puts** are a sharp, rare add (~0.5/wk).

2. **Can we trade daily? + how much can $2K make?** (D1) **No — not from the shippable set.** The two LIVE
   edges (everyday book + gap-and-go puts) cover only **~21% of days (~1.1 trades/wk)** and are
   **complementary** (they barely overlap — 7 shared days, Jaccard 0.10). Blended that's roughly
   **$300-900/mo on $2K** depending on how much of the everyday book's full-history edge survives OOS.
   **Daily-or-near-daily coverage (56% of days) is only reachable if the VWAP-continuation WATCH is flipped live.**

3. **B1 — is the +42% ITM-1 gap-and-go tweak affordable on $2K?** **The +42% edge is REAL but the strike
   is INFEASIBLE as a $2K default.** Min-3 SPY 0DTE puts cost **$550-810** at real OPRA prices (SPY is a
   ~$600 underlying) = **27-40% of equity** — the doctrinal **6% ceiling ($120) is unreachable at any strike
   with a validated edge.** Under the **live 40% ceiling**, ITM-1 fits only **46%** of days. **The
   feasible-optimal strike on $2K is ATM** (best verified edge on the days it fits, fits 82% of days);
   **OTM-1** is the fits-every-day (100%) fallback.

---

## D2 — THE LEADERBOARD (priority order = OOS edge × frequency)

Ranked by **weekly-edge $ = (expectancy/trade) × (trades/week on our 2025-26 tape)** — the task's
co-equal edge-and-frequency metric. "OOS exp" is from each filed scorecard (the honest forward number);
"full exp" is full-window.

| # | Edge | OOS exp/trade | Full exp/trade | Trades/wk | **Weekly-edge $** | OOS stability | Ship status |
|---|---|---|---|---|---|---|---|
| **1** | **Everyday bearish-rejection book** (live engine, chart-stop-primary) | n/a¹ | **+$229.7** | 0.66 | **$152** | edge_capture invariant +$1,340 (no J-edge regression), DSR PASS PSR 0.998, total +$16.7k | **LIVE** (production heartbeat) |
| **2** | **VWAP-continuation** (J's daily edge, ATM, both sides) | +$24.1 | +$38.3 | **2.31** | **$56** | NEAR-SURVIVOR 6/7: OOS+, WF +0.55/+0.72/+0.96, q+ 5/6, DSR PASS, both-dirs+, drop-top5 +$24.5; FAILS strict all-cuts-OOS+ (recent-Q2 window neg) | **WATCH** / dormant flip-ready (`j_vwap_cont_enabled=false`) |
| **3** | **Gap-and-go PUT, ITM-1** (the B1 +42% strike) | +$90.0 | +$59.2 | 0.48 | **$43** | all-cuts-OOS+ ✅, WF +1.39, q+ 6/6, DSR PASS, drop-top5 +$31.7 | **SHIP edge / strike INFEASIBLE on $2K** (see B1) |
| **4** | **Gap-and-go PUT, ATM** (current LIVE strike) | +$68.6 | +$41.6 | 0.48 | **$33** | all-cuts-OOS+ ✅, WF +1.87, q+ 6/6, DSR PASS, drop-top5 +$15.6 | **LIVE** (`gap_and_go_enabled=true, side=put`) |

¹ The everyday book's chart-stops-ab scorecard reports edge_capture + total P&L on the full real-fills
window (n=26→50 depending on window), not a single OOS exp/trade slice — its robustness proof is
anchor-no-regression + DSR, not a WF cut. Its **full-history $229.7/trade is not OOS-deflated**, so the
weekly-edge $152 is an upper bound (see D1 honesty note).

**Read of the ranking:** by raw weekly-edge the everyday book wins, but it's **low-frequency** (fires ~2-3×/month).
The VWAP-continuation edge is **lower per-trade but 3-4× more frequent**, which is why it is the lever that turns
"a few times a month" into "most days." Gap-and-go is the **sharpest per-trade** but rare and feasibility-capped on $2K.

---

## D1 — PORTFOLIO COVERAGE: can we trade (near-)daily, and the $2K P&L picture

**The key question:** if we run the shippable edges *together*, what % of days has ≥1 setup, and what's the
blended expectancy? Computed on OUR 2025-26 tape by taking each edge's **per-day signal dates** and unioning them.

### Coverage (351 trading days in window)

| Set | Fire-days | **Coverage %** | Trades/wk | Verdict |
|---|---|---|---|---|
| **Shippable** = everyday book ∪ gap-and-go put | 73 | **20.8%** | ~1.1 | **NOT daily** — ~1 setup/wk |
| **Shippable + VWAP-cont** (if WATCH flipped live) | 198 | **56.4%** | ~3.5 | **NEAR-DAILY** (every other day) |

- Everyday book fires **46 days (13.1%)**; gap-and-go put fires **34 days (9.7%)**; VWAP-cont fires **162 days (44.6%)**.

### Correlated or complementary? → **COMPLEMENTARY** (this is the good news)

The edges fire on **different days**, so stacking them genuinely *adds* coverage rather than doubling up:

| Pair | Overlap days | Jaccard | Read |
|---|---|---|---|
| everyday book ∩ gap-and-go put | **7** | 0.10 | nearly disjoint — gap-and-go fires at the open on gap days; the book fires intraday on rejections |
| gap-and-go put ∩ VWAP-cont | 18 | 0.10 | low overlap |
| everyday book ∩ VWAP-cont | 23 | 0.12 | low overlap |

Only **7 days** in the shippable set had 2 edges fire at once. Low correlation = the union coverage is real,
not redundant. It also means a portfolio kill-switch rarely has to choose between two simultaneous signals.

### Blended expectancy + realistic monthly P&L on $2K

Using the **feasible-optimal gap-and-go strike (ATM, edge $113.6 on the days it fits $2K)** + the everyday book:

| Metric | Value |
|---|---|
| Blended trades/week (shippable set) | **~1.14** |
| Blended expectancy / trade | ~$181 (weighted by each edge's frequency) |
| Blended weekly $ | ~$206 |
| **Blended monthly $ on $2K** | **~$893 (≈45% of $2K)** ← optimistic upper bound |
| Realistic monthly $ (OOS-deflating the book) | **~$300-500/mo** (see honesty note) |

**Honesty note (do not over-read the $893):** the everyday-book figure ($229.7/trade) is full-history and
**not OOS-deflated** — the book's gap-and-go-style OOS slices run lower. The blend also sums each edge's
(exp × fire-days) and on the 7 overlap days the engine trades **one** position (one account, one position
at a time), so realized P&L sits **at or below** the headline. Treat **$893/mo as the ceiling and ~$300-500/mo
as the realistic central case** for the shippable set on $2K. **Frequency, not edge size, is the binding
constraint.** The single biggest P&L lever is not a sharper edge — it is **flipping VWAP-continuation live to
roughly triple the trade count** (and roughly triple the realistic monthly $, modulo its softer per-trade edge).

### Verdict on "trade daily"

**Daily-or-near-daily is NOT achievable from the shippable set alone (~1 trade/wk, 21% of days).** It becomes
**near-daily (56% of days, ~3.5 trades/wk) only with the VWAP-continuation near-survivor flipped live.** The
honest state: we are a **~1 trade/week shippable engine** today; the path to a daily book runs entirely through
graduating the VWAP-continuation WATCH (its lone failing gate is the recent-Q2 OOS window under partial OPRA
coverage — a coverage/regime caveat, not a structural break).

---

## B1 — FEASIBLE-OPTIMAL STRIKE ON $2K (the +42% ITM-1 finding, stress-tested)

**Batch 1 found gap-and-go ATM→ITM-1 = +42% OOS edge.** This block answers: **is that affordable on $2K?**
Real OPRA put entry premiums at the 09:35 ET fill (next bar after the 09:30 confirmation), min-3 contracts,
on the 34 gap-down put-signal days.

| Strike | Real premium (median/p10/p90) | **Min-3 cost (median)** | Fits **6% ceiling** ($120) | Fits **live 40% ceiling** ($800) | Real-fills edge on fitting days | Filed OOS exp |
|---|---|---|---|---|---|---|
| **ITM-1** (the +42% strike) | $2.70 / 2.01 / 3.33 | **$810** | **0%** | **45.8%** | +$99.6 | +$90.0 |
| **ATM** (current live) | $2.28 / 1.53 / 2.88 | **$683** | 0% | **81.8%** | **+$113.6** | +$68.6 |
| **OTM-1** | $1.84 / 1.09 / 2.44 | **$552** | 0% | **100%** | +$95.8 | n/a (no filed tier) |

### The headline finding

**Min-3 SPY 0DTE puts cost $550-810 at real prices = 27-40% of a $2K account, because SPY is a ~$600
underlying.** The doctrinal **6% premium ceiling ($120) implies max $0.40/contract for min-3 — unreachable at
any strike that has a validated edge** (only OTM-5+ lottery tickets cost that little, and those have no
validated gap-and-go edge). **So on $2K the 6% ceiling and min-3 are mutually incompatible for this setup.**

Two ceilings exist and they disagree:
- **6% = the SIZING-STUDY *recommendation*** (`markdown/research/SIZING-STUDY-2026-06-19.md`) — prudent in
  principle, but it was derived for J's cheap **OTM-3** ($0.30-0.40) style, **not** for ATM/ITM gap-and-go
  on a $600 underlying. It is **NOT yet ratified into params**.
- **40% = what `params.json` `v15_max_premium_pct_of_account[$0-2K]` actually enforces TODAY** ($800). This is
  the binding real-world gate, and it is *deliberately* loose at the $0-2K tier (the params doc: "max $400…
  forces OTM bias even if v14 chooses ITM-2" — written when SPY math was different).

### Feasible-optimal strike on $2K: **ATM** (with OTM-1 as the fits-every-day fallback)

- **ITM-1 is INFEASIBLE as a blanket $2K default**: it busts the live $800 ceiling on **>half the days**
  (fits only 46%). Its +42% edge is real but you cannot put on min-3 of it most mornings without exceeding the
  account's own premium gate. **The +42% ITM-1 win is a higher-tier ($10k+) lever, not a $2k one.**
- **ATM is the feasible-optimal**: fits 82% of days under the live ceiling, and on the days it fits its
  real-fills edge is actually the **highest** ($113.6/trade) — and it is already the LIVE strike with a filed
  all-gates-pass scorecard. **No change needed to trade gap-and-go on $2K: stay ATM.**
- **OTM-1 is the only strike that fits 100% of days** and keeps a solid +$95.8 edge — the correct fallback on
  the ~18% of high-premium mornings where even ATM min-3 would breach the ceiling, and the natural default if
  the 6%-spirit ceiling is ever tightened (it still won't reach 6%, but it minimizes the breach).

**Recommended $2K gap-and-go rule:** trade **ATM**; if ATM min-3 > live ceiling that morning (high-IV open),
**step out to OTM-1** rather than skip. Reserve **ITM-1 for the $10k+ tier** where its premium is a small % of
equity and its +42% edge is fully harvestable. (This matches the existing per-tier strike ladder direction:
deeper strikes as equity grows.)

---

## What this means for the engine (propose-only — Rule 9; J holds REVOKE)

1. **Do NOT flip `gap_and_go_watcher.DEFAULT_STRIKE_OFFSET 0→−1 globally.** The B1 batch-1 recommendation is
   correct on edge but **infeasible on the $2K Safe account.** Gate the ITM-1 strike to the **$10k+ tier**;
   keep **ATM** at $0-2K (step to OTM-1 on high-premium opens). This is a per-tier override, exactly like the
   existing `v15_strike_offset_per_tier` ladder.
2. **The daily-book unlock is VWAP-continuation, not a strike tweak.** Flipping `j_vwap_cont_enabled=true`
   (per OP-16, J's call on side) is the single change that moves coverage from 21% → 56% of days and roughly
   triples the trade count. It is a 6-of-7 WATCH; the gating decision is J's (its caveat is recent-Q2 OOS
   under partial OPRA coverage).
3. **The 6% ceiling needs a doctrine reconciliation.** As written it is incompatible with min-3 on SPY 0DTE.
   Either (a) accept the live ~30-40% premium-of-equity reality at the $0-2K tier for these setups, or
   (b) re-derive the ceiling per-underlying-price. Flagged here; not changed.

---

## Reproduce / files

- Synthesis script: `backtest/autoresearch/daily_book_synthesis.py` (`backtest/.venv/Scripts/python.exe …`)
- Scorecard JSON: `analysis/recommendations/daily-book-synthesis.json`
- Inputs (filed, reused): `gap-and-go-LIVE.json`, `j-daily-pattern-LIVE.json`, `chart-stops-ab-2026-06-18.json`
- Master plan rows: D1 + D2 in `markdown/research/J-DATA-RESEARCH-MASTER-PLAN.md`

**Caveats:** (1) real-OPRA cache ends ~2026-05-29 → coverage window stops there. (2) Proxy strikes (L58):
the exact requested strike is used for B1 premiums (no nearest-strike fallback, so a few cache-missing days
drop out: ATM priced 22/34, ITM-1 24/34, OTM-1 22/34 days). (3) Everyday-book exp is full-history, not
OOS-deflated — the blended monthly $ is an upper bound. (4) Propose-only; OP-21 live gate (3 live J
confirmations) still stands for gap-and-go; J holds REVOKE.
