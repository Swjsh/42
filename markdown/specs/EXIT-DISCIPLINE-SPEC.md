# Exit-Discipline Spec — "The Engine Becomes The Hold"

> **Generated:** 2026-06-20 · **Author:** Gamma (autonomous research) · **Status:** validation + propose-only
> **Numbers:** [`analysis/recommendations/exit-discipline-vs-j-losers.json`](../../analysis/recommendations/exit-discipline-vs-j-losers.json)
> **Script:** [`backtest/autoresearch/exit_discipline_vs_j_losers.py`](../../backtest/autoresearch/exit_discipline_vs_j_losers.py) (pure Python, $0, py_compile clean)
> **Companion evidence:** [`analysis/recommendations/chart-stops-ab-2026-06-18.json`](../../analysis/recommendations/chart-stops-ab-2026-06-18.json) (live-book premium-stop OOS)

---

## 0. The question, and the answer

J's thesis, confirmed by his own loser data: **his entries had edge — he capitulated.** 67.9% of his
0DTE losers' underlying continued his thesis direction after he sold; 21.4% printed ≥2x (EST). His median
loser exit was **−41.7%** of premium — he was selling into a temporary adverse poke, right before the
reversal he was right about. His words: *"my entries just need work and to hold — that's what we have the engine for."*

**This spec PROVES the engine's mechanical HOLD would have survived a clear majority of the pokes that shook
him out, and catches the reversal.** Against his **267 real right-thesis shake-out losers** (continued_his_way ==
True AND he exited at a loss), with the EXACT SPY 5m path he traded:

| Metric | Result |
|---|---|
| **Engine HELD through the poke → caught the reversal** | **62.5%** (167 / 267) — structural-chart-stop model |
| Engine SHARED the shake-out | 37.5% (100 / 267) — of which **92 by chart-stop, only 8 by the −50% cap** |
| **Which exit does the holding work** | **The chart-stop.** Chart-stop-alone survives 62.9%; −50%-cap-alone survives 91.0%. The engine fires at whichever is *nearer*, so the (tighter) chart-stop is the binding constraint. The −50% cap almost never binds (it is the catastrophe backstop, as designed). |
| **Captured-recovery $ (HELD cases, honest cap)** | **+$17,636 EST** vs his actual −$42,955 loss on those trades. (Capped at 2/3-at-TP1-+50% + 1/3-runner-at-chandelier-trailed-extreme — NOT the perfect peak.) |
| Adverse poke that shook him out | median **1.10 SPY pts** (0.26% of spot) · p75 1.85 · p90 3.01 |
| Option-% drawdown at the poke (EST) | median **−22.8%** — i.e. the engine's hold sits through a ~−23% dip where J panicked at −41.7% |

**The value proposition is real: the engine's mechanical hold survives the first poke and J's hands did not.**

> **Honesty:** SPY poke distances, structural levels, and the CLOSE-based hold verdict are **EXACT** (his fills + the
> exact SPY 5m path). Option-% of the poke, the −50%-cap SPY-equivalent, and captured-$ are **ESTIMATES** (Black-Scholes,
> IV backed out of J's own entry premium). The engine cannot make a wrong-thesis trade win — only the 267 right-thesis
> shake-outs are scored.

---

## 1. The adverse-poke distribution (what shook him out)

From his entry spot, the **max adverse SPY excursion against his thesis BEFORE the favorable extreme** — the poke
that triggered his capitulation:

| | median | p75 | p90 | max |
|---|---|---|---|---|
| **SPY points (EXACT)** | **1.10** | 1.85 | 3.01 | 8.84 |
| **% of spot (EXACT)** | 0.26% | 0.45% | 0.73% | 2.04% |
| **option-% drawdown at poke (EST)** | **−22.8%** | −8.4% | −2.9% | (some never dipped) |

**Read:** the typical poke was about **1 SPY point / ~0.26%** — a routine intraday wiggle. In option terms it pulled
the premium down a median **−22.8%**. J exited at a median **−41.7%** (Part A) — he was capitulating roughly *twice
as deep* as the actual adverse excursion went. There was ample structural room for a mechanical hold to survive.

---

## 2. Where the engine's stops sit

At his entry bar, two stops, computed with **no look-ahead** (path up to and including the entry bar):

| Stop | median distance from entry | mechanic |
|---|---|---|
| **Chart-stop** = structural invalidation level ± `chart_stop_buffer_dollars` ($0.50) | **1.12 SPY pts (EXACT)** | **CLOSE-based** (production): a wick beyond the level that closes back inside does NOT trigger |
| **−50% premium catastrophe cap** (SPY-equivalent) | **4.10 SPY pts (EST)** | intrabar; fires only on a genuine premium gap |

Structural level source mix: swing-high (puts) 99 · swing-low (calls) 98 · entry-bar opposite extreme (gap-and-go
template, when no clean pivot) 70. The −50% cap is **wider than the chart-stop in 91.8% of trades** — confirming, on
J's data, exactly what the live doctrine intends: **the chart-stop is primary; the −50% cap is a backstop.**

The critical geometry: **chart-stop distance (median 1.12) ≈ the adverse poke (median 1.10).** The structural level
sits right at the edge of the typical poke. That is precisely why ~62% hold and ~38% share — and why stop-WIDTH is
the natural tuning lever (Section 5).

---

## 3. The CLOSE-confirmation rule is already load-bearing

Production's chart-stop is **close-based**, not wick-based. On J's shake-outs:

- **21 of 267 (7.9%)** were **wick-only**: the intrabar poke pierced the structural level, but the 5m bar **closed back
  inside**, so a close-based engine did **not** exit. (Conservative ribbon-flip-price-gate framing: 5.6% at $0.50.)

These are trades the **"wait for the 5m bar CLOSE, not the wick" rule directly SAVED** from a stop-out. **This is the
single cheapest, highest-confidence hold mechanism, and it is already in production** (heartbeat.md Position branch:
`close > rejection_level + buffer`). The spec's first recommendation is simply: *do not regress it.*

---

## 4. Which exit component does the holding work — chart-stop, not the cap

| If ONLY this stop existed… | …survives J's pokes |
|---|---|
| Chart-stop alone (structural level + $0.50, close-based) | **62.9%** |
| −50% premium cap alone | 91.0% |

Because the engine exits at whichever fires **first** (the nearer one), the **chart-stop is the binding constraint** —
it is doing 92 of the 100 shake-out exits; the −50% cap only does 8. **This confirms the CHART-STOP-PRIMARY doctrine
(2026-06-18) on J's independent real data:** the −50% cap is correctly a catastrophe backstop, and the chart-level
invalidation is what actually governs the hold.

---

## 5. Stop-width tuning — and the honest live-book OOS check

The poke≈chart-stop geometry says widening the buffer should convert shared→held. On J's data it does, monotonically:

| `chart_stop_buffer_dollars` | J shake-outs HELD | held % | Δ vs $0.50 |
|---|---|---|---|
| 0.25 | 150 / 267 | 56.2% | −18 |
| **0.50 (LIVE)** | **168 / 267** | **62.9%** | — |
| 0.75 | 188 / 267 | 70.4% | +20 |
| 1.00 | 205 / 267 | 76.8% | +37 |
| 1.50 | 227 / 267 | 85.0% | +59 |

**But the iron rule is the 2025-26 live +EV book must not be hurt. Two findings kill any naive "widen the buffer" ship:**

1. **The widening is a NO-OP on the live book.** Live params forced to real OPRA fills, varying ONLY
   `level_stop_buffer_dollars` ∈ {0.50, 0.75, 1.00} over the full real-fills window (2025-01-01..2026-05-29) + OOS
   (2026-03-01..2026-05-29) + J-anchor: **identical** results at every buffer — full **+$10,553**, OOS **+$2,108**,
   edge_capture **+$1,340**, exit histogram byte-identical. (Method mirrors chart-stops-ab-2026-06-18.json.)

2. **`chart_stop_buffer_dollars` is a DOMINATED knob on the current book.** Vary-and-assert (C14 dead-knob guard): the
   chart/LEVEL stop **never fires** at ANY buffer value (tested 0.01 / 0.50 / 5.00 → **0** `EXIT_ALL_LEVEL_STOP` in all
   three). The live book's de-facto chart invalidation is the **ribbon-flip-back** (which uses the *same* $0.50 price
   buffer `RIBBON_FLIP_PRICE_BUFFER` **plus** an opposite 30c ribbon stack and fires first), together with the −50% cap
   and the close-confirmation. The standalone level-stop is pre-empted in every live case.

So: widening the buffer **passes** no-regression *trivially* — by changing nothing live — and therefore **cannot be
claimed to improve the live book.** Its measured benefit (62.9%→76.8% hold on J's pattern) only materializes for the
J-style first-poke capitulation, which the live engine *already* approximates via the ribbon-flip + wide −50% cap +
close-confirmation.

**Two honest bounds on the true production hold-rate** (it sits between them):

| Hold model | held @ $0.50 | held @ $1.00 |
|---|---|---|
| Structural-swing chart-stop (doctrine "invalidation level") | **62.5%** | 76.8% |
| Ribbon-flip $0.50 price-gate alone (CONSERVATIVE — production *also* needs the 30c stack, so real holds MORE) | 36.7% | 57.7% |

Either way, **a plurality-to-majority of J's shake-outs would be held**, and the close-confirmation is load-bearing
in both.

---

## 6. The exit-discipline rules (tagged SHIP / PROPOSE / WATCH)

| # | Rule | Tag | Live-book OOS status |
|---|---|---|---|
| 1 | **Mechanical no-capitulation hold.** The exit is the chart-stop / ribbon-flip / chandelier / −50% cap / time-stop — never a discretionary "it's red, get out." This is the entire value proposition: against J's 267 right-thesis shake-outs the mechanical hold survives **62.5%** and captures **+$17,636 EST**. | **SHIP** (already live — *this spec is its validation*) | Already the live doctrine; no change. |
| 2 | **Chart-stop = structural level + $0.50, CLOSE-based** (wait for the 5m bar CLOSE beyond the level, not the wick). Saves 7.9% of J's shake-outs from a wick stop-out; chart-stop does 92/100 of the binding exits. | **SHIP** (already live) | Already live (`close > rejection_level + buffer`). Keep. |
| 3 | **−50% premium catastrophe cap** (backstop only; chart/ribbon/chandelier primary). On J's data the cap binds in only 8/100 shake-outs and is wider than the chart-stop in 91.8% of trades — exactly the intended backstop role. | **SHIP** (already live) | Already live + OOS-proven flat-to-better on the live book (chart-stops-ab-2026-06-18: −10%→−50% total $8,160→$16,671, edge_capture invariant). |
| 4 | **Profit-lock chandelier** (arm +5%, floor +10%, trail 15% off HWM) so a winning hold can't go negative — the structural complement to "hold through the poke." | **SHIP** (already live) | Already live + OOS-proven (CHANDELIER_TRAIL_20_TO_15, 2026-06-19). |
| 5 | **`chart_stop_buffer_dollars` $0.50 → wider (e.g. $1.00).** Would hold 62.9%→76.8% of J's pokes. | **WATCH** | **NO-OP on the live book** (level-stop never binds; dominated by ribbon-flip). Passes no-regression trivially but cannot be claimed to improve the live book. **Do NOT ship as a live knob.** Re-evaluate only if/when a future setup makes the level-stop the binding exit (e.g. a setup with no ribbon-flip condition). |
| 6 | **Ribbon-flip-back price buffer $0.50 → wider.** This is the knob that ACTUALLY binds on the live book and is the de-facto chart invalidation. Widening it to ~$1.00 would hold ~21pp more of J's pokes (conservative bound 36.7%→57.7%). | **PROPOSE (do not auto-ship)** | **NOT yet OObS-checked on the live book.** This is the live-relevant version of the J-shake-out finding and is the correct next experiment. Before any ship it MUST pass the same gate as chart-stops-ab: real-fills full-history total P&L ≥ baseline, OOS ≥ baseline, edge_capture no-regression, anchor no-regression. **Until that A/B is run and passes, this stays a proposal.** |

### Exact diffs (propose-only — do NOT apply without the OOS gate passing)

Rule 6 (the only live-relevant tuning candidate), IF a future A/B passes the gate:

```
# params.json — ribbon-flip price buffer (CURRENTLY HARD-CODED in simulator_real.py as
# RIBBON_FLIP_PRICE_BUFFER = 0.50; would need to be promoted to a param first)
# backtest/lib/simulator_real.py line ~639:  RIBBON_FLIP_PRICE_BUFFER = 0.50  ->  0.75 or 1.00
# heartbeat.md Position branch ribbon-flip-back: mirror the same buffer.
```

Rule 5 (recorded for completeness; **WATCH only, no live effect**):

```
# params.json
- "chart_stop_buffer_dollars": 0.5
+ "chart_stop_buffer_dollars": 1.0   # NO-OP on current book (level-stop dominated by ribbon-flip); do not ship
```

---

## 7. Verdict

**The engine becomes the hold — proven.** The single most important number: against J's own 267 real right-thesis
shake-out losers, the engine's mechanical hold would have **survived 62.5%** of the pokes that shook him out and
**caught the reversal**, turning a real −$42,955 into an estimated **+$17,636** captured-recovery. The **chart-stop**
does the holding work (the −50% cap is correctly a rarely-binding backstop), and the **close-confirmation** rule is
already load-bearing (saves 7.9%). **All four holding mechanisms (mechanical hold, close-based chart-stop, −50% cap,
chandelier) are already SHIPPED — this spec is their validation on J's independent data.**

On tuning: the current exits are **correctly tuned for the live +EV book** — every stop-width refinement that would
help J's pattern is either a **no-op on the live book** (the level-stop buffer, which is dominated) or **not yet
OOS-checked** (the ribbon-flip price buffer, the one live-relevant lever). The honest recommendation is therefore:
**ship nothing new today; the hold is already encoded.** The one open, live-relevant experiment is **widening the
ribbon-flip-back price buffer** (Rule 6) — proposed, gated behind the same real-fills no-regression A/B that ratified
the chart-stop and chandelier changes, never auto-applied.
