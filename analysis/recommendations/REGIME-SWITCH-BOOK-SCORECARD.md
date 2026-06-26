# REGIME-SWITCH BOOK SCORECARD — does regime ALLOCATION beat directional-ALWAYS?

**Run date:** 2026-06-21 (Sunday, markets closed — research only, $0, no live edit, no orders)
**Verdict: `SWITCH_DEAD`.** Regime allocation between the directional sleeve and the iron-condor
sleeve does **not** beat directional-always on any axis, at any tested threshold.

---

## The research question (#3 thesis)

Don't GATE per-trade and don't change STRUCTURE per-edge — **ALLOCATE between two classes by
REGIME**: run the directional theta-payer (`vwap_continuation`, ATM, -8% stop — the LIVE sleeve)
on TREND days, and the theta-harvester (iron condor LEAD config) on CHOP days. The claimed value
is *right-tool-for-the-regime* — deploy the harvester when the directional sleeve bleeds in chop.

This is a **research green/red** that would gate the heavy wide-band condor fetch (4b). It is NOT
a ship test (the condor leg is null-failing-standalone + data-constrained by the ±$5 OPRA band).

## Method (byte-for-byte sleeve reuse — no money-path edits)

- **Universe:** 365 trading days, 2025-01-02 .. 2026-06-18 (SPY frame ∩ OPRA cache).
- **TREND sleeve:** live `vwap_continuation` detector → `simulator_real` real-OPRA fills,
  strike_offset=0 (ATM/Safe-2), premium_stop_pct=-0.08, qty=3, v15 exits — identical to
  `recency_check.simulate_set`.
- **CHOP sleeve:** `simulator_credit` + `multileg_structures`, IC / 10:30 ET / short_offset=2 /
  wing=2 / pt_frac=0.50 / stop_mult=1.5 / $0.65 commission — identical to the
  `PIVOT-PREMIUM-SELLING-SCORECARD.md` LEAD cell.
- **Causal classifier:** trend_strength_20d (prior closes vs prior SMA20), VIX spot/slope @09:30,
  MES overnight range / 14d ATR, prior RTH range / 14d SPY ATR — all strictly ≤ the morning
  decision bar; thresholds learned from **IN-SAMPLE terciles (pre-2026)** only.
- **Recency window:** last **25 TRADING DAYS** of the universe (canonical `recency_check`
  definition — NOT days-with-trades).
- **Harness:** `backtest/autoresearch/_regime_switch_book.py` (base) +
  `backtest/autoresearch/_regime_switch_sweep.py` (108-cell threshold × NEUTRAL sweep).

---

## RESULT — base classifier (IS terciles)

Regime distribution (universe): **TREND=47, CHOP=55, NEUTRAL=263** (non-degenerate).

### The load-bearing thesis check — condor vs directional on the classifier's OWN CHOP days

| On the 55 CHOP days | Directional | Iron Condor | Condor − Directional |
|---|---:|---:|---:|
| Real-OPRA P&L | **+$1,202.44** | +$459.60 | **−$742.84** |

**Thesis NOT supported.** On the days the classifier calls "chop", the directional sleeve
*out-earns* the condor by $742.84. Swapping in the harvester gives up directional P&L — the
opposite of the thesis. (And on its 47 TREND days the directional sleeve actually netted
−$158.32 — the classifier's "trend" label is not where directional makes its money either.)

### Book metrics — switched vs both baselines

| Book | FULL total | Sharpe | Sortino | maxDD | OOS total | Recency-25d total | Recency-25d maxDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| **DIRECTIONAL-ALWAYS** (live, baseline to beat) | **$7,065.96** | **3.883** | **5.753** | −$454.56 | **$2,377.28** | −$224.64 | −$312.96 |
| SWITCHED (NEUTRAL→directional) | $6,323.12 | 3.693 | 5.021 | −$454.56 | $2,347.96 | −$224.64 | −$312.96 |
| SWITCHED (NEUTRAL→condor) | $2,077.48 | 2.909 | 1.575 | −$324.76 | $1,147.92 | −$84.20 | −$158.20 |
| SWITCHED (NEUTRAL→abstain) | $301.28 | 0.537 | 0.188 | −$436.80 | $328.12 | −$122.40 | −$122.40 |
| CONDOR-ALWAYS (IC LEAD every day) | $2,077.48* | 2.909 | 1.575 | −$324.76 | $1,147.92 | −$84.20 | −$158.20 |

\* condor-always ≡ the NEUTRAL→condor switched book here because TREND/CHOP both also route to
the condor only on a subset; the condor-every-day class total is the $2,077.48 / sharpe 2.909 /
sortino 1.575 line — far below directional-always on every risk-adjusted measure.

### The 4 bars, every NEUTRAL policy

| Bar | NEUTRAL=directional | NEUTRAL=condor | NEUTRAL=abstain |
|---|:--:|:--:|:--:|
| 1. risk-adjusted UP vs directional (Sharpe+Sortino+maxDD) | ❌ | ❌ | ❌ |
| 2. recency-25d chop drawdown reduced | ✅ | ✅ | ✅ |
| 3. no-regression on switch days | ❌ | ❌ | ❌ |
| 4. OOS-positive | ✅ | ✅ | ✅ |
| **ALL PASS** | **❌** | **❌** | **❌** |

Bar 2 passes trivially because routing *away* from the bleeding directional sleeve in the recent
window cuts the drawdown — but it does so by sacrificing far more upside elsewhere (bar 1, bar 3
both fail). No-regression fails hard: on the 318 days the book switches away from directional,
the book made $6,481.44 vs the $7,224.28 directional-alone would have made = **−$742.84 net**.

---

## RESULT — threshold + NEUTRAL sweep (108 cells)

6 trend-quantile splits × 6 overnight-quantile splits × 3 NEUTRAL policies:

- **Cells passing ALL bars: 0 / 108.**
- **Cells where the condor beats directional on the classifier's OWN CHOP days: 0 / 108.**
- **Best cell by (ALL_PASS, Sortino, total):** trend_q=(0.15,0.85), on_q=(0.33,0.67),
  NEUTRAL=directional → FULL $6,931.56 / Sharpe 3.842 / Sortino 5.515 / maxDD −$454.56 —
  still strictly *below* directional-always ($7,065.96 / 3.883 / 5.753), bar fails.
- **Best THESIS cell** (max condor − directional on CHOP days): trend_q=(0.15,0.85),
  on_q=(0.33,0.67) → dir $320.00 vs condor $185.60 = **−$134.40**; thesis still not supported.

There is **no causal threshold** in the grid at which deploying the condor on a regime subset
out-earns leaving the directional sleeve on.

---

## VERDICT: `SWITCH_DEAD`

| Requirement for SWITCH_WINS | Result |
|---|:--:|
| Beats directional-always on risk-adjusted return (Sortino up, maxDD down) | ❌ Sortino 5.02–5.52 < 5.75; total always lower |
| Reduces/flips the recency-25-trading-day chop drawdown | ⚠️ only by sacrificing upside (bar 1+3 fail) |
| No-regression: CHOP-switch days net-beat directional-alone | ❌ −$742.84 net on switch days |
| OOS-positive | ✅ (but lower than directional-always's $2,377) |
| **Best of 108 swept cells passes all bars** | **❌ 0/108** |

**Why it fails (C1 / C3 / L172):** the premise — "directional bleeds in chop, harvester won't" —
does not hold at the per-day-regime level on **real OPRA fills**. The directional sleeve's tight
-8% stop + ATM theta-payer structure keeps it *net-positive on the classifier's own chop days*
(+$1,202), while the iron condor (generic theta, not strike-selection alpha, and capped by the
±$5 OPRA band / $2 wings) caps the upside. Allocating to the harvester only surrenders P&L. The
recency-25d directional RED (−$224.64) is real, but it is a *time-clustered* drawdown, not a
*regime-separable* one — no morning-causal regime label isolates it.

## Implication for direction 4b (wide-band condor fetch)

This research green was the **gate** for the heavy wide-band condor OPRA fetch. **The gate is
RED → do NOT spend the heavy fetch on regime-allocation.** A wide-band condor would only change
the CHOP-sleeve magnitude; it cannot reverse a −$742.84 thesis deficit driven by the directional
sleeve being *positive* on chop days. The condor remains a standalone-null-failing,
data-constrained line — keep it shelved unless a *different* research question (not regime
allocation) motivates the fetch.

## Honest caveats carried

- Real OPRA fills only (C1, the WR authority); per-day EXPECTANCY, not WR (OP-14).
- IC sleeve is null-failing-standalone (L172) + data-constrained (±$5 band) — this was never a
  ship test, and the SWITCH_DEAD verdict means it does not graduate to one.
- Directional-always remains the live approach; nothing here changes production (Sunday money-path
  guard — no live edit, no orders).

**Artifacts:**
`backtest/autoresearch/_state/regime_switch_book/results.json` (base),
`backtest/autoresearch/_state/regime_switch_book/sweep_results.json` (108-cell sweep).
