# J-Regime Filters — C1 (VIX) / C2 (trend-vs-range day) / C3 (year transfer)

> Campaign angle of [`J-DATA-RESEARCH-MASTER-PLAN.md`](J-DATA-RESEARCH-MASTER-PLAN.md) §C.
> **Method (anti-overfit):** J's Webull data (668 SPX-family round-trips, 2021-23) *defines* each regime hypothesis and the threshold to try; OUR 2025-26 SPY real OPRA fills *validate* it forward (chronological OOS, all-4-sub-windows-positive, the gate's own OOS, DSR, drop-top5, both-sides). A gate tuned to a known-bad window with no clean own-OOS is **DEAD**, not a win.
> **Honesty:** J's raw SPX-family book is net **−$12,885 (WR 46.9%, PF 0.75)**. This work locates *where the edge is least-bad / positive*, not a claim that his book prints.
>
> Scripts: [`backtest/autoresearch/j_regime_split.py`](../backtest/autoresearch/j_regime_split.py) (his split) · [`backtest/autoresearch/j_regime_forward_validate.py`](../backtest/autoresearch/j_regime_forward_validate.py) (our forward fills).
> Data: scorecard at [`analysis/recommendations/j-regime-filters.json`](../analysis/recommendations/j-regime-filters.json); raw splits at `analysis/webull-j-trades/_j_regime_split.json` + `analysis/recommendations/j-regime-vwap-vix-gate.json`. VIX for J's dates: `analysis/webull-j-trades/vix_daily_2021_2023.json` (^VIX daily via yfinance; day-open = causal 09:30 proxy).

---

## TL;DR verdicts

| Angle | Verdict | One-line |
|---|---|---|
| **C1 VIX regime** | **WATCH** | VIX *level* doesn't discriminate (winner mean VIX 24.65 vs loser 25.01) and doesn't fix VWAP-continuation. But its **inverse** — a realized-**volatility floor (rvol ≥ 9 bps)** — lifts VWAP-continuation to **all-sub-windows-positive with a clean own-OOS** on the scorecard exit config. The most promising lever found. |
| **C2 trend vs range day** | **WATCH** | J's strongest, most robust split: **trend days breakeven, chop days catastrophic** (−$56/t). His one positive decent-N cell is **bull/trend (+$13/t, PF 1.30, n=116)**. But ADX/day-type gates do **not** transfer to our VWAP-continuation (they're among the worst). Real J-behavioral insight; dead as a live gate on our setup. |
| **C3 year/regime transfer** | **WATCH (flag)** | His book is **85% one regime (2022 bear)** → cannot prove cross-regime robustness. Stable cross-year pattern: **bull-side > bear-side every year**. Mild **transfer-risk flag on gap-and-go** (LIVE put-only): J's own history backs a *bullish* lean, not a bearish edge. |

---

## C1 — VIX regime → a realized-volatility floor (WATCH)

### What J's data says
Splitting his 668 SPX-family trades by VIX band at the day open (doctrine bands: low <16, mid 16–19, high ≥19):

| VIX band | n | exp/trade | PF | read |
|---|---|---|---|---|
| low (<16) | 63 | **−$64.14** | 0.49 | worst per-trade |
| mid (16–19) | 37 | **+$44.54** | 2.20 | only positive band — but thin + 2023-driven |
| high (≥19) | 568 | −$18.47 | 0.75 | 85% of his book (2022 bear) |

**Crucial caveat:** winner mean VIX (24.65) ≈ loser mean VIX (25.01). VIX *level alone barely separates outcomes* — the band result is a sample-mix artifact, not a per-trade VIX edge (cf. L154/L167: a level anomaly ≠ a per-trade option edge). So a naive "trade mid-VIX" gate is not trustworthy.

### Forward test on our VWAP-continuation fills
**Does a VIX gate take VWAP-continuation from 6/7 → 7/7 (all sub-windows OOS-positive) with its own OOS clean?**

- **VIX gate: NO.** The prior sweep ([`vwap-trend-pullback-regime-gate.json`](../analysis/recommendations/vwap-trend-pullback-regime-gate.json)) already found **0 winners** across one-sided `vix_lt_X`, `vix_falling`, ADX, range-ratio, rvol-ceiling. Its diagnosis: the bad months (2025-07..10) were **LOW-VIX (median 16.7), low realized-vol (6.1 bps), low morning-move** — the *opposite* of a low-VIX gate. Confirmed here: every two-sided VIX band (16-19/15-20/16-22/14-19) stays bimodal (`all_sub_windows_positive = False`).
- **Realized-volatility FLOOR: YES** (on the scorecard exit config). This is the lever J's combined finding pointed to — his dead tails bleed; the VWAP bad-months were the dead-tape summer. Require enough volatility to trade:

**`rvol ≥ 9 bps`, scorecard (−8% premium-stop) config:**

| metric | value |
|---|---|
| n / retention | 31 / 0.34 |
| exp/trade | **+$70.10** |
| IS → OOS | +$57.53 → **+$96.50** (sign-stable) |
| 4 sub-windows | `[104.26, 24.75, 81.85, 73.83]` → **all positive** |
| both sides + | yes |
| drop-top5 | +$23.44 (robust) |
| DSR | PASS |
| OOS months positive | 3/3 |
| **own-OOS** (thr derived IS-only, applied unseen OOS) | **generalizes; full series still all-sub-positive** |

**Mechanism (not a date fit):** the rvol ≥ 9 floor removes **88% of the dead-summer bad-month trades** (their median rvol was 6.2 vs the 9 floor). It filters the structural quiet-tape feature those months shared. Surviving 31 trades median **+$41.4** (not outlier-driven).

### Exact param (if pursued)
```
vwap_continuation_realized_vol_floor_bps = 9.0
# = stdev of session 5m close-to-close log-returns (open → current bar), in bps;
#   require >= 9.0 at the VWAP-continuation trigger to take the entry.
```
**Why WATCH not SHIP (honest blockers):**
1. **n = 31 < 35** (the project's winner-bar sample threshold; clears the advisory `evidence_n ≥ 15` but not the stricter 35).
2. **Config-sensitive.** All-sub-positive holds on the −8% config but **not** on the **live chart-stop-only (−0.99)** config the watcher actually trades — there one sub-window is negative (+$132 OOS, but bimodal). C29/L149: exit knobs don't transfer across stop configs. (The combo `rvol≥6 & vix<22` *is* all-sub-positive on chart-stop, n=43, but one side is slightly negative.)
3. **Not computed live.** No `realized_vol` exists in loop-state / the VWAP watcher today — a small new live feature is required before it can gate the engine.

**Recommendation:** wire dormant (default-off param) and **start logging `realized_vol_bps` at every live VWAP-continuation trigger**; promote to SHIP once N≥35 accumulates live **and** it holds on the chart-stop config.

---

## C2 — Trend day vs range day (WATCH)

### What J's data says — his single most robust split
Day-type from a **data-driven range-ratio tercile** (path/net of intraday 5m closes) over the 205 reliable cached days (≥60 RTH bars): trend = efficient move (low tercile), range = chop (high tercile).

| day type | n | exp/trade | WR |
|---|---|---|---|
| **trend** | 211 | **−$1.38** | 51.7% |
| mixed | 188 | −$15.46 | 44.7% |
| **range/chop** | 209 | **−$56.43** | 43.5% |

His edge is **monotonic in day-type** — he is roughly breakeven on trend days and hemorrhages on chop. His one genuinely positive, decent-N cell:

- **bull / trend: +$13.28/t, PF 1.30, WR 52.6%, n=116** (Wilson LCB 0.436).
- worst cell in the whole book: **bear / range: −$78.39/t, PF 0.35, n=109**.

### Forward test on our data
**NO transfer.** ADX/trend-strength and range-ratio gates were swept on our VWAP-continuation fills and are **among the worst** (`adx_ge_20` −$13.99, `adx_ge_25` −$20.70; `range_ratio_le_2.0` not OOS-sign-stable). None make all sub-windows positive. Why: VWAP-continuation *already* selects a directional pullback context, and the bad period was a **low-volatility** artifact, not a chop-vs-trend one. The **volatility floor (C1)** is the live-tradeable cousin of "avoid dead days"; ADX is not.

**Recommendation:** Keep C2 as a **J-behavioral insight** — his chop-day losses are the bleed (a "skip chop" discipline would have helped *him*). Do **not** build a day-type router for our engine off this; it does not validate forward.

---

## C3 — Year / market-regime transfer-risk (WATCH / flag)

### What J's data says
| year | n | exp/trade | WR | note |
|---|---|---|---|---|
| 2021 | 20 | −$13.40 | 45% | tiny |
| 2022 | 556 | −$17.37 | 45.7% | **85% of his book — the bear year** |
| 2023 | 92 | −$32.17 | 54.4% | higher WR, worse exp (bigger losses) |

His data is **overwhelmingly one macro regime** (2022 bear) — so it **cannot establish cross-regime robustness**. The one stable cross-year pattern is side asymmetry:

| year | bull exp / PF | bear exp / PF |
|---|---|---|
| 2022 | −$4.01 / 0.93 | −$30.17 / 0.64 |
| 2023 | −$9.58 / 0.89 | −$72.58 / 0.50 |

**Bull-side is less-bad than bear-side in every year.** VIX-high band is negative in all three years (sign-stable bleed). VIX-mid is positive only in 2023 (not transferable).

### Transfer-risk verdict on our book
- **gap-and-go (LIVE, put-only / bearish): MILD FLAG.** It was validated on our fills independently (that stands), but **J's own multi-year history does not corroborate a bearish edge** — his bear side is his worst cross-regime. Treat gap-and-go's bear edge as *our-data-specific*, not J-backed; keep BASE size, don't scale on the assumption his history supports it.
- **VWAP-continuation: CORROBORATED on side asymmetry.** J's bull > bear matches our forward result (C-side +$51.79 > P-side +$37.49 in `vwap-trend-pullback-LIVE.json`). The bull lean is the cross-regime-stable read.
- **General:** J's data is a **directional-bias corroborator only**; our 2025-26 forward tests remain the authority on regime transfer.

---

## Bottom line for the campaign
1. **The shippable thread is a volatility floor, not a VIX gate.** `rvol ≥ 9 bps` on VWAP-continuation is the bimodality-killer the prior VIX sweep couldn't find — clean own-OOS, all-sub-positive on the scorecard config. Held back to **WATCH** only by n=31, exit-config sensitivity, and the need for a new live rvol feature.
2. **VIX level is DEAD** for this fix; **day-type is DEAD** as a live gate (real as J-behavior).
3. **Transfer-risk is a soft flag**, not a kill: J's history is one regime and leans bullish — a small caution on our bear-only gap-and-go, a corroboration of VWAP-continuation's bull tilt.
