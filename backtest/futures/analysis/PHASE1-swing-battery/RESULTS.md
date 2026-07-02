# PHASE 1 — MES Multiday Swing Battery — RESULTS

> **VERDICT: `DOES_NOT_TRANSFER`** (bottom rung of the pre-registered ladder, [DESIGN.md](DESIGN.md) §5, committed 3c31bf2 *before* grinding).
> **The honest kill, stated plainly: the theta thesis was wrong for this seed pile.** Removing option carry and giving the direction reads a linear instrument (MES, 1–5 day ATR-stop holds) does **not** rescue them. The E2 level+VWAP context *reverses sign* out-of-sample (the opposite direction makes money in 2026); the RRW-short FDR family either loses on train at its tradeable frequency (vol≥1.5) or fires too rarely to test (vol≥2.5 → 3–4 test trades). 0 of 12 tested cells clears BH-FDR.

Run: 2026-07-02, `swing_battery.py`, one process, `backtest/.venv`, 7.4s runtime, $0.
Data: `MES_1m_continuous.csv` (Databento GLBX.MDP3, back-adjusted continuous, md5 `22f02f1d45d3…` per results.json), 508,586 ETH 1m bars 2025-01-01 18:00 → 2026-06-12 16:59 ET, 367 trading days. Costs charged on every trade incl. nulls: $1.24 commission + 2×1 tick slippage = **$3.74/RT**. 1 MES contract, $5/pt; all $ are per-contract.

## Funnel

| Stage | Count |
|---|---|
| RRW superset events (bear, RTH 5m, MES-scaled knobs) | 2,220 |
| E2 superset events (level-touch + VWAP-aligned, both dirs) | 7,863 |
| Signal combos × exit shapes | 24 × 36 = 864 cells |
| Train-eligible cells (train n ≥ 15 AND train exp > 0) | 149 |
| Selected to the ONE test pass (top-K rule, ≤3/combo) | 12 |
| BH-FDR survivors (α = 0.1) vs random-entry null | **0** |
| Full-gate survivors / weak-core survivors | **0 / 0** |

Per-combo event counts (full period): RRW vol≥1.5 = 146–197, RRW vol≥2.5 = 32–45, E2 = 346–489, E2+structure = 175–247, RRW+structure vol≥1.5 = 38–55, **RRW+structure vol≥2.5 = 0** (daily-downtrend alignment and the high-volume RRW gate never co-occur — MES ran 5,900 → 7,437 over the window).

## The 12 tested cells (train-ranked, one test pass)

| Combo | Shape | Train n / exp | Test n / exp | p (rand-null) | FDR | Opp-dir exp | Test maxDD |
|---|---|---|---|---|---|---|---|
| B_e2_t0.001_full | s2.0_2x_h5_ff | 53 / **+127.88** | 27 / **−103.32** | 0.799 | ✗ | **+96.77** | 4,477 |
| B_e2_t0.001_full | s2.0_3x_h5_ff | 53 / +127.88 | 27 / −103.32 | 0.849 | ✗ | +96.77 | 4,477 |
| B_e2_t0.001_full | s2.0_trail_h5_ff | 55 / +110.35 | 30 / −97.88 | 0.934 | ✗ | +93.71 | 4,887 |
| A_rrw_w0.5_lb12_v2.5 | s1.5_3x_h3_ff | 15 / +120.59 | **4** / +214.70 | 0.162 | ✗ | −235.84 | 229 |
| A_rrw_w0.5_lb12_v2.5 | s2.0_2x_h3_ff | 15 / +120.59 | 4 / +214.70 | 0.205 | ✗ | −325.60 | 229 |
| A_rrw_w0.5_lb12_v2.5 | s2.0_3x_h3_ff | 15 / +120.59 | 4 / +214.70 | 0.164 | ✗ | −325.60 | 229 |
| A_rrw_w0.35_lb12_v2.5 | s1.5_3x_h3_ff | 16 / +101.88 | 4 / +221.88 | 0.159 | ✗ | −235.84 | 229 |
| A_rrw_w0.35_lb12_v2.5 | s2.0_2x_h3_ff | 16 / +101.88 | 4 / +221.88 | 0.193 | ✗ | −325.60 | 229 |
| A_rrw_w0.35_lb12_v2.5 | s2.0_3x_h3_ff | 16 / +101.88 | 4 / +221.88 | 0.140 | ✗ | −325.60 | 229 |
| A_rrw_w0.35_lb6_v2.5 | s1.5_3x_h3_ff | 15 / +114.59 | **3** / +32.09 | 0.407 | ✗ | −151.21 | 229 |
| A_rrw_w0.35_lb6_v2.5 | s2.0_2x_h3_ff | 15 / +114.59 | 3 / +32.09 | 0.488 | ✗ | −216.90 | 229 |
| A_rrw_w0.35_lb6_v2.5 | s2.0_3x_h3_ff | 15 / +114.59 | 3 / +32.09 | 0.404 | ✗ | −216.90 | 229 |

**Survivor table: empty.**

## What killed each seed

1. **E2 (at-named-level + VWAP-aligned) — sign flip OOS.** Train (2025): +$110–128/trade on n=53–55. Test (2026 H1): −$98 to −$103/trade on n=27–30, WR 37–40%, and the **opposite-direction null earns +$94–97/trade on the same entries** — in 2026 the profitable trade was to FADE the context. Test half-1 (Jan–Mar) is the damage (−$248/tr); half-2 recovers to ≈ flat (+$12–33/tr). This is a regime-dependent read, not a durable direction signal (C22 signature: backward-looking context classifiers anti-correlate across regime shifts). p=0.80–0.93 — indistinguishable-from-or-worse-than random entries with the same exits.
2. **RRW-short, tradeable frequency (vol≥1.5, 146–197 events)** — never reached the test: the best of all 36 exit shapes on train is **negative** (−$4.75 to −$20.71/trade, n=37–40). The SPY options battery's "beats random but loses money" cohort is simply "loses money" once expressed 1:1 on the linear instrument at swing horizons.
3. **RRW-short, rare cohort (vol≥2.5, 32–45 events)** — train-positive (+$102–121/tr, n=15–16) and test-positive (+$32–222/tr) with the opposite direction losing (−$151 to −$326) — the *sign pattern* a real edge would show — but **n=3–4 test trades**. p=0.14–0.49. Statistically empty; not evidence, and explicitly not a WEAK rung under the pre-registered ladder (BH-FDR fail).
4. **Structure filter (daily BOS/CHoCH alignment)** — only 39 daily structure events in 18 months; downtrend states are rare in this window, so the filter zeroes out the RRW vol≥2.5 cohort entirely and roughly halves E2 without changing its character. No structure-filtered cell reached the top-12.

## Exit/hold matrix findings (train-level, descriptive)

- **Weekend holds are not paid for:** across 288 matched train pairs (both sides n≥10), hold-weekend vs flat-Friday delta = **−$44.71/trade mean, −$31.22 median; only 33% of pairs favor holding the weekend.** Among the 12 tested cells, every one selected the flat-Friday variant on train merit. First actionable general finding of the battery: *any* future MES swing spec should default flat-by-Friday.
- **At swing-scale ATR stops, exits are dominated by the clock, not the levels:** tested-cell exit mixes are FRIDAY/TIME ≈ 23:4 (E2 fixed-target) and TIME 22 / TRAIL_STOP 8 (trail). 1.0–2.0× daily-ATR stops (≈60–140 MES pts) are rarely hit inside 3–5 days, so many (stop, target) shapes collapse onto identical trade paths — the effective matrix is smaller than 36.
- **Drawdown:** the E2 tested cells carried test maxDD of **$4,477–4,887 per contract** against negative P&L — unacceptable on any rung.

## Verdict rationale (pre-registered ladder)

`DOES_NOT_TRANSFER` — no tested cell clears BH-FDR (α=0.1) with positive test expectancy. Nothing reaches the opposite-direction, concentration, stability, or drawdown gates because nothing passes the first gate. Phase 2/3 of the futures revival are **not unlocked by this battery**: there is no validated swing edge to wire a broker path for. The plan's gate discipline (`FUTURES-REVIVAL-PLAN §2f`: "everything else waits on one seed clearing this") holds — published as a kill.

**What this does NOT kill:** (a) the RRW vol≥2.5 rare cohort — direction-consistent both periods, opposite-direction loses, but unpowered at 45 events/18mo; it would need years of data or a relaxed-but-validated gate to power a test — parked, not disproven; (b) intraday futures expressions (this battery tested 1–5 day holds only); (c) seeds outside this pile. Any follow-up must be a NEW pre-registered battery — no knob-turning on this one.

## Caveats (beyond DESIGN.md §7)

- The plan doc's claim that cached bars are RTH-only was **wrong** — data is full ETH Globex (verified: hours 0–23, 1,380 bars/day median). This battery benefited: overnight stop hits and gap fills are walked on real overnight bars, not modeled.
- ATR warmup drops signals before ~2025-01-23 (first 14 daily bars); E2 dedupe is first-per-day-per-direction; boundary trades entered ≤2025-12-31 but exiting in 2026 count as train (≈1/cell).
- Train regime (2025: 5,917 → ~5,650 with a deep drawdown and recovery) vs test regime (2026 H1: grind up to 7,437) differ materially; with 18 months there is no way to stratify further — this is exactly what the opposite-direction null is for, and it fired.
- 12 tested cells came from 4 signal combos (cap ≤3/combo) — the train stage concentrated merit heavily; 137 other eligible cells were selected away, their test data remains unburned.
