# J-Regime Filters — C1 (VIX) / C2 (trend-vs-range day) / C3 (year transfer)

> Campaign angle of [`J-DATA-RESEARCH-MASTER-PLAN.md`](../research/J-DATA-RESEARCH-MASTER-PLAN.md) §C.
> **Method (anti-overfit):** J's Webull data (668 SPX-family round-trips, 2021-23) *defines* each regime hypothesis and the threshold to try; OUR 2025-26 SPY real OPRA fills *validate* it forward (chronological OOS, all-4-sub-windows-positive, the gate's own OOS, DSR, drop-top5, both-sides). A gate tuned to a known-bad window with no clean own-OOS is **DEAD**, not a win.
> **Honesty:** J's raw SPX-family book is net **−$12,885 (WR 46.9%, PF 0.75)**. This work locates *where the edge is least-bad / positive*, not a claim that his book prints.
>
> Scripts: [`backtest/autoresearch/j_regime_split.py`](../../backtest/autoresearch/j_regime_split.py) (his split) · [`backtest/autoresearch/j_regime_forward_validate.py`](../../backtest/autoresearch/j_regime_forward_validate.py) (our forward fills).
> Data: scorecard at [`analysis/recommendations/j-regime-filters.json`](../../analysis/recommendations/j-regime-filters.json); raw splits at `analysis/webull-j-trades/_j_regime_split.json` + `analysis/recommendations/j-regime-vwap-vix-gate.json`. VIX for J's dates: `analysis/webull-j-trades/vix_daily_2021_2023.json` (^VIX daily via yfinance; day-open = causal 09:30 proxy).

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

- **VIX gate: NO.** The prior sweep ([`vwap-trend-pullback-regime-gate.json`](../../analysis/recommendations/vwap-trend-pullback-regime-gate.json)) already found **0 winners** across one-sided `vix_lt_X`, `vix_falling`, ADX, range-ratio, rvol-ceiling. Its diagnosis: the bad months (2025-07..10) were **LOW-VIX (median 16.7), low realized-vol (6.1 bps), low morning-move** — the *opposite* of a low-VIX gate. Confirmed here: every two-sided VIX band (16-19/15-20/16-22/14-19) stays bimodal (`all_sub_windows_positive = False`).
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

---

## C1-RESOLVED — the rvol floor on the LIVE chart-stop config + the bull-side verdict (2026-06-20)

> Script: [`backtest/autoresearch/vwap_cont_rvol_floor.py`](../../backtest/autoresearch/vwap_cont_rvol_floor.py) · Scorecard: [`analysis/recommendations/vwap-cont-rvol-floor.json`](../../analysis/recommendations/vwap-cont-rvol-floor.json) · Live wiring (dormant): [`backtest/lib/watchers/vwap_continuation_watcher.py`](../../backtest/lib/watchers/vwap_continuation_watcher.py) `realized_vol_floor_bps` (default 0.0 = OFF).

### Detector correction (load-bearing — read this first)
The original C1 row above measured `rvol ≥ 9` on **`detect_vwap_pullback`** (the H4 VWAP-*pullback* survivor), NOT on the **`detect_j_vwap_continuation`** detector the dormant `vwap_continuation_watcher` actually trades. They are different setups (pullback = first in-trend VWAP-tag after a 6-bar one-sided open, any time of day; continuation = J's morning ≤10:30 breakout-OR-pullback, trend set by the first 3 RTH bars). So the C1 result did **not** transfer by assertion — it had to be re-measured on the continuation detector. This section is that re-measurement.

### `realized_vol_bps` — the causal, live-computable definition (GOAL 1a)
```
realized_vol_bps = std( diff( log( session_5m_closes[open .. trigger] ) ), ddof=1 ) * 1e4   # bps/bar
```
Reads only bars[0..trigger] of the session → causal. Identical definition already shipped causally in `j_regime_forward_validate._realized_vol_bps`; now also `vwap_continuation_watcher.realized_vol_bps`. **Cross-checked byte-for-byte identical** between the harness and the live watcher over 40 real signals (0 mismatches) — so the live floor reproduces the validated numbers exactly. Live-computable from the 5m closes the heartbeat already caches.

### GOAL 1 verdict — **WATCH** (no floor reaches 7/7 on the live chart-stop config)
J_VWAP_CONT, real OPRA fills, ATM, **chart-stop-only (premium_stop −0.99 = the live watcher config)**, floor swept over {0,5,6,7,8,9,10} bps:

| floor bps | n | exp $/t | WR | q+ | sub 4/4 | WF med | all-cuts-OOS+ | OP-22 |
|---|---|---|---|---|---|---|---|---|
| 0 (off) | 153 | +38.3 | 76.5% | 67% | 4/4 | +0.55 | **F** | 5/7 |
| 7 | 61 | +65.4 | 85.2% | 83% | 4/4 | +0.43 | **F** | 5/7 |
| 9 | 46 | +66.1 | 84.8% | 83% | 4/4 | +0.27 | **F** | 5/7 |

The floor genuinely **improves** exp/WR and fixes quarter-positivity (67%→83%) and sub-windows — but it does **NOT** reach 7/7 at any threshold. Two persistent blockers:
1. **`all_cuts_oos_positive` = FALSE at every floor.** The lone failing window is the **0.80 cut = 2026-Q2** (the most-recent OOS slice), which is negative pre- AND post-floor and gets *worse* as the floor tightens (−$61 → −$140 → −$219). It is a recent-quarter **directional drawdown**, not a low-vol artifact, so a vol floor cannot fix it.
2. **`wf_median ≥ 0.70` = FALSE.** Chart-stop rolling-WF is structurally weak (max +0.55 ungated); the floor never lifts it past 0.70. Same C29/L149 stop-config pattern that kept H4 pullback dormant.

**own-OOS (anti-curve-fit):** IS-only pick = floor 9 bps (IS exp +$83.11), applied UNSEEN to OOS → +$22.78 (generalizes, sign-stable) — but the full series at that floor is **still not** all-cuts-OOS-positive. So the floor is not curve-fit; it's just insufficient on this exit config.

**The floor IS clean on the −8% premium-stop config** (baseline 7/7; floor 7 also 7/7; own-OOS picks floor 7, generalizes +$82, full-series 7/7) — exactly reproducing the original C1 finding. But the live watcher trades chart-stop, and **exit knobs don't transfer (C29/L149)** — which is precisely why the live verdict is WATCH.

**Exact remaining blocker (for the WATCH ticket):** to flip, either (a) the live exit config must change to −8% premium-stop for this setup AND be re-ratified, OR (b) the 2026-Q2 OOS slice must turn positive as live N accrues. The rvol floor alone does not clear chart-stop.

**Action taken (dormant, zero behavior change):** wired `realized_vol_floor_bps` into `vwap_continuation_watcher` (default **0.0 = OFF = inert**; gym 87/87 green, all parity tests pass). The as-of `realized_vol_bps` is now **logged in metadata at every trigger** so live N accrues toward the ≥35 promotion bar. **NOT flipped, NOT proposed for flip** (J decides). C1 candidate value if ever flipped = 9.0.

### GOAL 2 verdict — **bull-side DOES transfer (corroborated), and is the stronger half**
On the continuation detector, live chart-stop, baseline (no floor):

| side | ATM exp $/t | n | WR | ITM1 exp $/t |
|---|---|---|---|---|
| **C (calls)** | **+25.99** | 84 | 77.4% | +45.21 |
| P (puts) | +53.28 | 69 | 75.4% | +42.62 |

- The call side is **positive, broad-based (n=84, drop-top5 robust), on every config and tier** — genuinely different from gap-and-go calls (which failed standalone as 5 lottery winners). This **corroborates J's historical bull-tilt on OUR 2025-26 fills.** His bull-tilt **transfers** to the continuation detector.
- With the rvol floor the **call side improves MORE than the put side** (chart-stop ATM C +$25.99 → +$74.38 at floor 9; P +$53.28 → +$56.99). With a confirmed-close cut (breakout = real up-bar) the call side stays strong: floor-9 + confirmed = C +$86.04/n=19/WR 89.5%.
- **The 2026-Q2 softness is NOT bull-specific** — it's a recent-quarter drawdown hitting both sides (2026Q2: ATM total −$64.91 across C+P). So the recent bull weakness in the *put-heavy regime* narrative is over-stated for THIS detector: the continuation **call side is the cleaner, more floor-responsive half**, it just shares the generic recent-Q drag that also blocks the put side.
- **Honest caveat:** the put side carries higher raw exp at baseline (the legacy put-heavy regime), but it degrades under the floor while the call side strengthens — consistent with J's "bull > bear every year." There IS a shippable-quality bull edge here; it is gated to WATCH by the same chart-stop/recent-Q blockers as the whole setup, not by any bull-specific failure.

### Bottom line (C1-RESOLVED)
- **rvol floor on the LIVE config: WATCH** (not 7/7). Blocker = chart-stop WF<0.70 **and** the 2026-Q2 OOS slice (a directional drawdown a vol floor can't fix). Clean on −8%, doesn't transfer to chart-stop (C29/L149). Wired dormant (default-off) + now logging live rvol for N-accrual.
- **Bull side: TRANSFERS / shippable-quality** on the continuation detector (broad-based, floor-responsive, drop-top5 robust) — corroborates J's bull-tilt; held to WATCH only by the shared chart-stop/recent-Q gate, not a bull failure.
