# SIZING & COMPOUNDING — turning the one real edge into an account that grows (2026-06-20)

> **Status: ANALYSIS + DESIGN (Rule 9 — nothing live changed).** No edit to `risk_gate.py`,
> `params.json`, or either heartbeat. Markets closed. Ratification of any change is a separate
> after-hours step. This is the forward, per-trade-distribution Kelly/compounding companion to
> the historical-behavior study [`SIZING-STUDY-2026-06-19.md`](SIZING-STUDY-2026-06-19.md)
> (which designed the 6% premium ceiling from J's Webull ledger). This doc stress-tests that
> ceiling against the survivor edge's *own* compounding math — and finds a tension.

- **Sim:** `backtest/autoresearch/_sel_vwap_sizing.py` (pure Python + pandas; `$0`; deterministic; no live orders)
- **Schema:** `analysis/recommendations/sel-vwap-sizing.json` + `analysis/recommendations/vwap-sizing.json` (alias)
- **Edge under study:** `vwap_continuation` — our ONE survivor of ~32 strategies. Detector is
  BYTE-FOR-BYTE `j_daily_pattern_ratify.detect_j_vwap_continuation` (live port =
  `backtest/lib/watchers/vwap_continuation_watcher.py`), survivor structure **ITM-2 / −8% premium
  stop / v15 exits**, real OPRA fills via `lib.simulator_real.simulate_trade_real` (C1).
- **Window:** 2025-01-02 .. 2026-05-15 (342 trading days). IS = 2025, OOS = 2026.

---

## TL;DR

1. **The edge is real and survives the full gauntlet.** 149 real-fills trades, WR 51.7%,
   **+$78.29/trade at qty-3 ($26.10/contract)**, OOS-2026 **+$105.62/trade**, IS-2025 +$67.56,
   **6/6 positive quarters**, top-5-day concentration only 20.6%, both sides positive (C +$84, P +$71),
   beats a 20-seed random-entry null by **$82/trade** ($78 vs −$4), sign-stable at chart-stop-only.
   **All 8 mandatory gates PASS → `edge_validated=true`.**

2. **Kelly is NOT the binding constraint — Rule 6 + the 6% premium ceiling always bind first.**
   On the empirical distribution (risk denominator = stop-defined avg loss $24.24/contract,
   *not* full premium), **full-Kelly f\* = 0.28, half-Kelly = 0.14**, ruin-bounded ceiling 0.325.
   Half-Kelly *wants* 11–144 contracts depending on tier — but the 30% cap / 6% ceiling / min-3
   floor clamp the actual recommendation to **3–6 contracts**. Kelly here is academic; the governor
   is Rule 6.

3. **True risk-of-ruin is ~0% — but small ITM-2 accounts face a STRAND-trap.** The −8% premium
   stop caps per-trade loss so tightly that **no Monte-Carlo path hits the 50% impairment floor**
   from P&L. The real small-account danger is different: at **$5K, ITM-2 throttled to min-3 by the
   6% ceiling grows so slowly that 46.7% of paths get STRANDED** (drift down to ~$2.4K where min-3
   ITM-2 no longer fits the 30% cap, locking the account out) before reaching $10K. The current
   30%-cap rule (sizes 6 at $5K) escapes this **100% of the time**.

4. **$2K (Safe-2 today) cannot trade the edge's strike at all.** 3× ITM-2 ($250/contract) = $750 =
   37.5% of $2K, over the 30% cap. The account is structurally below where the edge lives. The v15
   ladder's OTM-2 fallback is affordable (3× $62 = 9.3% equity) but **captures only 27% of the edge
   magnitude — a 73% haircut** ($7/contract OTM-2 vs $26/contract ITM-2).

**Headline recommendation:** half-Kelly is the operating *principle*, but it is dominated by Rule 6
at every tier, so the concrete call is a **tiered contract table** (below). The most important
finding is structural: **the 6% premium ceiling — designed to cap revenge-sizing — also throttles
the survivor edge into a strand-trap on small ITM-2 accounts.** The ceiling and min-3 conflict
below ~$12.5K for ITM-2; today they are reconciled by trading the cheaper OTM-2 strike, which
sacrifices 73% of the edge. That trade-off is the real decision for J / Treasurer.

---

## 1. The per-trade distribution (real fills, the truth)

| Metric | qty-3 | per-contract |
|---|---:|---:|
| n trades | 149 | 149 |
| Win rate | 51.7% | 51.7% |
| Expectancy | **+$78.29** | **+$26.10** |
| Median P&L | — | +$14.40 |
| Mean win | — | +$73.17 |
| Mean loss | — | −$24.24 |
| Best / Worst | — | +$181.13 / −$74.56 |
| Std dev | — | $57.53 |
| Median entry premium | — | $2.50 / share ($250/contract) |

**IS/OOS:** IS-2025 +$67.56/tr (n=107) · OOS-2026 **+$105.62/tr** (n=42) — the edge is *stronger*
out-of-sample, the opposite of the futures-trap artifact we reject.
**Quarters:** 6/6 positive. **Concentration:** top-5 winning days = 20.6% of P&L; drop them entirely
and per-trade is still **+$64.34**. **Direction:** C +$84.07/tr (WR 53.7%, n=82) · P +$71.23/tr
(WR 49.3%, n=67) — both sides carry.

### Gate gauntlet (all mandatory, deterministic, no cherry-picking — anti-pattern 2.10)

| Gate | Result | Detail |
|---|:--:|---|
| n ≥ 20 | PASS | n = 149 |
| OOS per-trade > 0 | PASS | +$105.62 |
| **IS per-trade > 0** (reject single-regime artifact) | PASS | +$67.56 |
| positive quarters ≥ 4/6 | PASS | 6/6 |
| top-5-day < 200% | PASS | 20.6% |
| drop-top-5-days > 0 | PASS | +$64.34/tr |
| beats random-entry null (20 seeds) | PASS | strat +$78.29 vs null −$4.26 |
| sign stable at chart-stop-only (no truncation) | PASS | −0.99 stop → +$79.59/tr |

→ **`edge_validated = true`.** Sizing below is built on a validated distribution, not a hope.

---

## 2. Fractional-Kelly on the empirical distribution

Kelly maximizes `E[log(1 + f·R)]` over the **empirical** per-contract returns (not a 2-outcome toy).
The crucial modeling choice: **R = per-contract $PnL ÷ stop-defined $-at-risk ($24.24 avg loss),
NOT ÷ full premium.** A stopped option trade only risks the stop distance, not the whole premium —
so the avg realized loss is the honest Kelly denominator.

| Quantity | Value |
|---|---:|
| Mean return per unit-risk | 1.077 |
| Std return per unit-risk | 2.373 |
| Worst in-sample return | −3.08 (i.e. worst loss = 3.1× the avg loss) |
| **Full-Kelly f\*** | **0.28** |
| **Half-Kelly** | **0.14** |
| Quarter-Kelly | 0.07 |
| Ruin-bounded f ceiling (1/|R_min|) | 0.325 |

**Interpretation:** f\* is *interior* (0.28 < the 0.325 wipeout ceiling) — a real optimum, not a
grid artifact. But "fraction of equity at risk = 0.14" translates to **dozens of contracts** at
every account size, because each contract only risks ~$24. **The 30% cap, the 6% premium ceiling,
and the min-3 floor all bind far below Kelly.** Practically: *Kelly says bet much bigger than Rule 6
allows; Rule 6 is the active governor, and that is the conservative, correct outcome on an n=149 /
16-month sample.* Half-Kelly is retained as the stated operating principle and as the throttle for
any future tier where premiums get cheap enough that Kelly *could* bind.

---

## 3. Account-growth curve & risk-of-ruin (5,000-path Monte-Carlo bootstrap)

Each path resamples the joint (P&L, premium) per-trade outcomes with replacement at the observed
~2.3 signals/week cadence, sizes contracts at current equity under each regime, compounds, and
stops at the next tier target, at 50% impairment ("ruin"), at "stranded" (equity > 50% but can no
longer afford the min trade), or at timeout. "Ruin" = equity ≤ 50% of start.

### $2K → $5K → $10K → $25K → $50K (ITM-2 sizing)

| Start → Target | Regime | P(hit) | P(ruin) | **P(strand)** | med max-DD | med weeks |
|---|---|:--:|:--:|:--:|:--:|:--:|
| **$2K → $5K** | half-Kelly (ITM-2) | — | — | — | — | **INFEASIBLE** — ITM-2 won't fit 30% cap |
| $2K → $5K | current rule (30% cap) | 0.869 | 0% | **13.1%** | 6.5% | 12.5 |
| **$5K → $10K** | half-Kelly (ITM-2, 6%-ceiling→min-3) | 0.533 | 0% | **46.7%** | 4.3% | 29 |
| $5K → $10K | current rule (30% cap) | **1.00** | 0% | **0%** | 6.7% | 9 |
| **$10K → $25K** | half-Kelly | 1.00 | 0% | 0% | 3.3% | 57 |
| $10K → $25K | current rule | 1.00 | 0% | 0% | 8.2% | 11.5 |
| **$25K → $50K** | half-Kelly | 1.00 | 0% | 0% | 2.4% | 41 |
| $25K → $50K | current rule | 1.00 | 0% | 0% | 7.0% | 8.5 |

*(full-Kelly-ruinbounded and quarter-Kelly are identical to half-Kelly at every tier — the 6%
ceiling clamps all three to the same contract count, confirming Kelly never binds.)*

**Reading it:**
- **P(ruin) = 0% in every feasible cell.** The −8% premium stop makes per-trade loss small enough
  that no realistic sequence drains the account to half. Risk-of-ruin is *not* the threat here.
- **The threat is STRANDING the small ITM-2 account.** At $5K, throttling to min-3 ITM-2 (because
  the 6% ceiling would otherwise allow only 1 contract) grows the account so slowly that a normal
  drawdown drifts it below the ~$2.4K line where 3× ITM-2 no longer fits the 30% cap — and it locks
  out. 46.7% of half-Kelly paths strand. The faster 30%-cap rule clears $10K before that can happen.
- **Above $10K the danger vanishes** for both regimes — there is enough equity that min-3 ITM-2 is a
  small fraction and drawdowns can't strand it. The trade-off there is pure speed (current rule
  ~5× faster to target) vs drawdown (current rule deeper DD: 8% vs 3%).

---

## 4. Concrete per-tier sizing recommendation (Rule 6 + 6% ceiling respected)

Half-Kelly operating point, clamped by the 30% risk cap, the 6% premium ceiling, and the min-3
floor; where ITM-2 (the edge strike) is unaffordable, drop to the OTM-2 affordable execution.

| Equity | Strike | **Rec. contracts** | Binding constraint | Premium % of equity | E[$/trade] |
|---:|---|:--:|---|:--:|---:|
| **$2,000** (Safe-2) | **OTM-2** | **3** | min-3 floor (ITM-2 infeasible) | 9.3% | **+$21** |
| **$5,000** | **ITM-2** | **3** | min-3 floor (6% ceiling would say 1) | 15.0% | **+$78** |
| **$10,000** | **ITM-2** | **3** | min-3 floor (6% ceiling would say 2) | 7.5% | **+$78** |
| **$25,000** | **ITM-2** | **6** | 6% premium ceiling | 6.0% | **+$157** |

ITM-2 half-Kelly *wants* 11 / 28 / 57 / 144 contracts at these tiers — every recommendation is a
Rule-6 clamp, never Kelly. **Note the conflict at $5K–$10K:** min-3 ITM-2 costs 7.5–15% of equity,
*above* the 6% ceiling. **Rule-6 min-3 is a hard floor and wins** — but that is precisely the
sizing that strands the $5K account (§3). The two rules pull opposite directions below ~$12.5K.

---

## 5. The decision this surfaces for J / Treasurer

The 6% premium ceiling (ratified-in-design 2026-06-19 to stop revenge-sizing) and the survivor
edge's compounding math **collide on small ITM-2 accounts.** Three coherent resolutions, in order
of how well they grow the account while honoring the 10 rules:

1. **Tier the strike to the account (what the v15 ladder already does).** Trade OTM-2 below ~$10K,
   ITM-2 above. Honors every rule, never strands. **Cost: 73% edge haircut while small** — the $2K
   account earns +$21/trade instead of +$78. Slowest compounding, zero strand risk. *Safest; this
   is the status quo and it is defensible.*
2. **Raise the per-account capital so ITM-2 fits min-3 inside 30%.** Min-3 ITM-2 ($750) is < 30% of
   any account ≥ $2,500. **Funding Safe-2 to ~$2.5–3K immediately unlocks the full ITM-2 edge** and
   removes the strand-trap (above $10K, P(strand)=0). This is the highest-leverage single change:
   it converts a +$21/trade account into a +$78/trade account for ~$1K of capital.
3. **Relax the 6% ceiling toward a 30%-cap-only rule with the post-loss throttle** (the throttle
   from `SIZING-STUDY-2026-06-19.md` neutralizes revenge-sizing without a hard premium ceiling).
   The 30%-cap rule grows fastest and never strands in the MC — but carries deeper drawdowns (8%
   vs 3%) and re-opens the size-up surface the ceiling was meant to close. Only attractive *paired*
   with the post-loss throttle.

**Gamma's read:** **(2) then (1).** Fund Safe-2 to ≥ $2.5K so the validated ITM-2 edge is reachable
(largest, cheapest improvement), and keep the OTM-2 ladder as the documented fallback for any
account that dips below the ITM-2 affordability line. Hold the 6% ceiling as the *revenge-sizing*
guard it was designed for, but recognize it is a throttle on the edge below $12.5K, not a free
constraint. None of this is a mid-session change (Rule 9) — it is a weekend/after-hours ratification
item for J, paired with the existing sizing-study throttle design.

---

## Caveats (honest)

- **Stationarity is the load-bearing assumption.** The MC assumes future trades are drawn from the
  observed 16-month / n=149 distribution. A regime shift (vol collapse, edge decay) breaks all of it.
- **Kelly fraction = fraction of equity at risk** under a stop-defined risk denominator. Full-Kelly
  on n=149 over-bets; half-Kelly is the floor of safety, and Rule 6 enforces far below even that.
- **The edge is measured at ITM-2.** OTM-2 / OTM-3 carry a large haircut (73% at OTM-2). Sizing math
  is only valid for the strike it was measured on — applying ITM-2 expectancy to an OTM execution
  overstates the edge by ~4×.
- **Real-fills authority (C1):** every number here is real OPRA fills; BS-sim was never used.
  Coverage 94.3% (9 cache-miss of 158 signals).
