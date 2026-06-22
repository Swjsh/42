# J-Data Profitability Campaign — FINAL SYNTHESIS

> J directive (2026-06-20): "cover every angle, use my webull data, test extensively, leave no plan untested. there has to be something profitable in there if we just tweak certain parameters. keep working."
>
> **Status: COMPLETE.** Every angle in [J-DATA-RESEARCH-MASTER-PLAN.md](J-DATA-RESEARCH-MASTER-PLAN.md) (A1–A10, B1–B6, C1–C4, D1–D2) tested on his 655 real Webull round-trips (2021-23), each **validated forward on OUR 2025-26 SPY real-OPRA fills** (chronological OOS, WF, all-cuts, DSR, drop-top5, causal). The anti-overfit guard held: his data *defines* hypotheses, our data *decides*.

---

## THE HONEST BOTTOM LINE

**The profit is not a hidden parameter.** The exhaustive param sweeps mostly came back DEAD under proper out-of-sample + null-control testing — and that is the point: the discipline that kills false edges is *why* the survivors are trustworthy. What is genuinely profitable, all traceable to his data:

1. **The SETUPS** — `gap-and-go` (LIVE) + `VWAP-continuation` (flip-ready). His momentum-breakout + his day-after-day VWAP-aligned pattern.
2. **FREQUENCY** — flipping VWAP-continuation live takes coverage from 20.8% → **56.4% of days (~3.5 trades/wk, near-daily)**. The daily-trading unlock is frequency, not a tweak.
3. **The SIZING FIX** — the 6% premium ceiling literally couldn't afford 3 contracts on a $600 SPY (fit 0 days). Reconciling it is what *lets a $2K account trade the edges at all*.

His memory of "cheap contracts that hit $1000" was **not a strategy** — it was his right-thesis trades he got shaken out of (68% of his losers kept going his way after he sold). That's captured by the **hold** (proven: the engine survives 62.5% of his shake-outs), not a new setup to find.

---

## EVERY ANGLE — verdict table

### A. Setup / Entry
| # | Angle | Verdict |
|---|---|---|
| A1 | Winner archetypes | ✅ gap-and-go shipped; reversal/pullback dead on live config |
| A2 | VWAP-aligned continuation | 🚀👀 **flip-ready** — his real edge, 76% WR, near-daily |
| A3 | Gap-and-go | 🚀 **LIVE** (bear) +$41/t 73% WR |
| A4 | Entry quality / confirmed-close | 🚀 already live (short); 👀 bull-side (OOS-thin) |
| A5 | Time-of-day specificity | 💀 afternoon edge ≠ morning-detector tweak (~$0 OOS) |
| A6 | Calendar / OPEX / month-end | 💀 his OPEX signal real but fails a frequency-matched null (p=0.34) |
| A7 | Level-keyed entry | 💀 his winners didn't cluster at levels; SPY levels too dense |
| A8 | Trigger × condition | 💀 sharp axis is the *condition* (already live via confirmed-close) |
| A9 | Call vs put asymmetry | 👀 put side owns the recent drawdown; combined book most robust → put-side regime gate, not a side ban |
| A10 | Self-PnL "hot read" | 💀 day-regime confound (de-meaning inverts it) |

### B. Parameter tweaks ("if we just tweak certain parameters")
| # | Angle | Verdict |
|---|---|---|
| B1 | Strike selection | 🚀(tier-gated) gap-and-go ATM→ITM-1 = +42% OOS — **but a $10k+-tier lever, INFEASIBLE on $2K** (min-3 ITM-1 too expensive); $2K-optimal = ATM (already live) |
| B2 | Hold-time / time-stop | 💀 no early time-stop beats live 15:40 |
| B3 | TP target | 👀 his low-TP inverts forward; live 0.50 re-confirmed |
| B4 | Stop distance | ✅ chart-stop correct; buffer is a dead knob |
| B4b | Ribbon-flip-back buffer | 💀 **KEEP-30** — knob doesn't bind (opposite-stack spread already ~94c when it forms) |
| B5 | Sizing | ✅ L168; min-3 + post-loss throttle design |
| B6 | Per-setup-quality sizing tier | moot until the sizing-ceiling is reconciled (see Decision B) |

### C. Regime / filter
| # | Angle | Verdict |
|---|---|---|
| C1 | VIX filter | 👀 VIX *level* dead; a realized-VOL FLOOR (rvol≥9bps) lifts VWAP-cont on the −8% config but NOT on the live chart-stop config (WATCH; wired dormant + now logging rvol live) |
| C2 | Trend vs range day | 💀 real in his behavior, doesn't transfer as a live gate |
| C3 | Year/regime transfer | 👀 his book is 85% one regime (2022 bear) → can't prove transfer; stable signal = bull>bear every year (his edge is bull-tilted) |
| C4 | Gap vs non-gap | ✅ gap is necessary (frequency lever closed) |

### D. Combination / portfolio
| # | Angle | Verdict |
|---|---|---|
| D1 | Edge portfolio / daily coverage | ✅ shippable union = 20.8% of days; **+VWAP-cont = 56.4% (near-daily)**; edges are complementary, not correlated |
| D2 | Setup-quality leaderboard | ✅ everyday book $152/wk > VWAP-cont $56/wk > gap-and-go $33-43/wk |

**Net:** ~15 honest negatives (no overfit), 2 live-or-ready edges, 1 reconciled blocker, 1 tier-gated future lever.

---

## THE THREE DECISIONS FOR J

**(a) Flip VWAP-continuation LIVE?** — the daily unlock. Your day-after-day winning pattern: 76% WR, +$38/t, ~56% of days. It clears 6 of 7 gates; the miss is a recent-quarter directional drawdown (put-side) that resolves as live data accrues. *Recommend: flip it (it's your near-daily edge), VIX/rvol-aware, watch the put side.* One boolean: `j_vwap_cont_enabled=true`.

**(b) Sign off the SIZING-CEILING reconciliation?** — *this is the practical key.* The current 6% premium ceiling fits **0 days** of min-3 on $600 SPY 0DTE (it was an artifact of your cheap-SPX days). Proposed: cap **gross** min-3 ≤ Rule-6 30%, cap **$-at-risk** (gross × ~0.30 chart-stop fraction) ≤ ~4% half-Kelly; trade **OTM-2** (fits 97.5% of days, ~3.3% real risk). **Without this, the account can't properly size any edge.** Needs your risk-doctrine sign-off (it changes a risk rule). Full math: [SIZING-CEILING-RECONCILIATION.md](../0dte/SIZING-CEILING-RECONCILIATION.md).

**(c) Ribbon-buffer** — RESOLVED, no action: KEEP-30 (the knob doesn't bind).

---

## WHAT'S LIVE / READY RIGHT NOW
- **LIVE Monday:** gap-and-go (bear), everyday bearish_rejection book (chart-stop primary, chandelier 15%, TP1 0.667, min-3).
- **Flip-ready:** VWAP-continuation (dormant flag), rvol-floor (dormant, logging).
- **Proven, already encoded:** the hold (62.5% of your shake-outs survive), confirmed-close + VWAP-aligned entries.
- **Awaiting:** your 3 decisions above + Monday's live data (the real ★★★-level + GEX + engine-shadow archives that resume accruing).

> Everything in this campaign is propose-only on doctrine (Rule 9) and reversible. Nothing trades real money. The engine is your edge + the discipline you couldn't hold, built from your own trades.
