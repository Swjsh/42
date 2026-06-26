# B7 — vwap_continuation +VIX-REGIME-GATE A/B scorecard

## VERDICT: DEAD — the VIX-regime gate does NOT improve the live edge (it over-filters, removing WINNERS)

**Headline (both tiers, all 16 sweep cells):** NO cell clears all 9 gates + (a)(b)(c). The gate
LIFTS the small OOS-2026 slice (best ITM-2 cell OOS $165–$254/tr vs baseline $106) — but this is an
**OOS-small-sample mirage**, not a real edge improvement:

- **(a) FAIL — full-sample per-trade DROPS or washes:** the headline-best ITM-2 cell gives
  full-sample $54.4/tr vs baseline **$78.3** (−$23.9); the least-aggressive cut (lm=0.25) is a
  wash ($86 vs $78). Tightening the cut only inflates the tiny OOS slice while the larger
  full sample stays flat-to-worse.
- **(c) FAIL — the SKIPPED days are PROFITABLE on every cell** (ITM-2 skipped set $74–$90/tr;
  ATM $46–$65/tr). A good gate removes losers; this one removes **net winners**. That is the
  decisive no-regression failure (the whole reason the OOS slice looks better is survivorship
  on the OOS days the gate happened to drop, not signal alpha).
- **(d) FAIL — gated subset breaks g5 (full drop-top5 < 0), g6 (IS-first-half < 0), g9 (OOS drop-top5
  None/<=0 once n shrinks), and g7 null drop-top5 doesn't beat null-mean** at the cut that maximizes OOS.

**The live baseline is already the edge.** vwap_continuation un-gated: full-sample $78.3/tr, OOS
$105.6/tr, posQ 6/6, top5-day 20.6%, OOS-drop-top5 $62.5 (ITM-2). The VIX-regime gate does not
beat it on the metric that matters (full-sample per-trade + no-regression). **Do NOT ship the gate
— keep the live edge un-VIX-gated.** Per-tier "LEAD" labels below are an artifact of the best-cell
picker maximizing delta-OOS; the (a)(b)(c)(d) checks are the binding verdict and they FAIL.

> Lesson echo (C4/C5): a per-trade lift seen ONLY on the OOS slice while full-sample drops is the
> classic small-OOS survivorship trap — verify the SKIPPED set is the losers (it isn't here) before
> believing a regime gate "found alpha". OOS-alone improvement is necessary-but-not-sufficient.

---

Window: `2025-01-02..2026-05-15` | trading days: 342 | baseline signals: 158 on 158 days

**Favorable regime (edge#4, causal):** `vix_level <= (trailing_median - low_margin) AND (slope_rule) vix_slope5 <= 0` (median_bars=78, slope_bars=5)

**Question (Angle C):** does VIX-regime-gating LIFT the live `vwap_continuation` per-trade expectancy? The gate must (a) improve per-trade exp, (b) not skip a J winner-day anchor, (c) the SKIPPED set must be net <=0 (removes losers), (d) still clear all 9 gates on the gated subset.

## TIER `ITM2_live` (strike_offset=-2, stop=-0.08)

| metric | BASELINE | GATED (best cell) | SKIPPED set | delta (gated-base) |
|---|---|---|---|---|
| n trades | 149 | 26 | 123 | — |
| full-sample per-trade $ | 78.29 | 54.39 | 83.35 | -23.9 |
| **OOS(2026) per-trade $** | 105.62 (n=42) | 254.12 (n=5) | 85.56 | **+148.5** |
| OOS drop-top5 /tr (g9) | 62.5 | None | — | — |
| full drop-top5 /tr (g5) | 64.34 | -11.29 | — | — |
| positive quarters | 6/6 | 4/5 | — | — |
| top5-day % | 20.6% | 116.8% | — | — |
| WR % | 51.7 | 46.2 | 52.8 | — |

**Best gated cell:** low_margin=1.0, slope_rule=not_rising | taken_signals=28, skipped_signals=130

- (a) improves OOS exp: **True** | improves full exp: **False**
- (b) anchor winner-days skipped: **NONE (pass)**
- (c) SKIPPED set net per-trade <=0 (removes losers): **False** (skipped exp=$83.35)
- (d) 9-gate clear on gated subset: **False** | null_pass=False | no_truncation=True | chart_stop_only_exp=$75.58
  - null: max=$32.52 mean=$-3.52
- **FAILS:** (a)full_exp_no_lift gated=54.39 base=78.29; (c)skipped_set_profitable exp=83.35 (gate removed WINNERS); g5_full_drop_top5=-11.29<=0; g6_is_h1_exp=-15.98<=0; g9_oos_drop_top5=None<=0; g7_null beats_max=True drop_beats_mean=False (null_max=32.52 null_mean=-3.52)

### TIER verdict: **LEAD**

## TIER `ATM_safe2` (strike_offset=0, stop=-0.08)

| metric | BASELINE | GATED (best cell) | SKIPPED set | delta (gated-base) |
|---|---|---|---|---|
| n trades | 149 | 26 | 123 | — |
| full-sample per-trade $ | 48.33 | 35.81 | 50.97 | -12.52 |
| **OOS(2026) per-trade $** | 59.81 (n=42) | 201.36 (n=5) | 40.68 | **+141.55** |
| OOS drop-top5 /tr (g9) | 26.45 | None | — | — |
| full drop-top5 /tr (g5) | 35.84 | -13.07 | — | — |
| positive quarters | 6/6 | 4/5 | — | — |
| top5-day % | 28.3% | 129.5% | — | — |
| WR % | 51.7 | 50.0 | 52.0 | — |

**Best gated cell:** low_margin=1.0, slope_rule=not_rising | taken_signals=28, skipped_signals=130

- (a) improves OOS exp: **True** | improves full exp: **False**
- (b) anchor winner-days skipped: **NONE (pass)**
- (c) SKIPPED set net per-trade <=0 (removes losers): **False** (skipped exp=$50.97)
- (d) 9-gate clear on gated subset: **False** | null_pass=False | no_truncation=True | chart_stop_only_exp=$26.83
  - null: max=$21.06 mean=$-2.13
- **FAILS:** (a)full_exp_no_lift gated=35.81 base=48.33; (c)skipped_set_profitable exp=50.97 (gate removed WINNERS); g5_full_drop_top5=-13.07<=0; g6_is_h1_exp=-15.85<=0; g9_oos_drop_top5=None<=0; g7_null beats_max=True drop_beats_mean=False (null_max=21.06 null_mean=-2.13)

### TIER verdict: **LEAD**
