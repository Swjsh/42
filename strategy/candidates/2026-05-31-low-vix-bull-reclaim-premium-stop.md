# DRAFT CANDIDATE — Low-VIX BULLISH_RECLAIM exit fix (premium-stop chop)

> **STATUS: DRAFT for J. Not ratified. Rule 9 — exit-rule changes are J's, on a weekend, in writing.**
> Generated 2026-05-31 from the missed-week backtest (machine offline 05-23..05-30, J moved house).

## The observation (real-fills, missed week 2026-05-26..29)

Low-VIX (15-16) bull grind, SPY +0.85% over 4 days, every target day closed at/above open.
Production v15.2 correctly fired **BULLISH_RECLAIM calls WITH the trend** — but still lost
net per-contract because almost every loss was `EXIT_ALL_PREMIUM_STOP`:

| Config | missed-days per-contract | W/L | dominant exit |
|---|---|---|---|
| SAFE (ATM, -8% stop) | **-$10.6** | 1W/3L | EXIT_ALL_PREMIUM_STOP |
| BOLD (ITM-2, -15% stop) | **-$117.4** | 2W/6L | EXIT_ALL_PREMIUM_STOP |

Only 05-29 (clean trend day) won. 05-26/27/28 reclaim-calls were stopped on shallow retest
dips, then SPY resumed higher without them. Authoritative detail: `analysis/backtests/_TRUTH.md`,
`analysis/missed-week-2026-05-26_29.md`.

## Hypothesis
A bull-reclaim entry sits right at the reclaimed level. In low-VIX grind, a normal retest
wick trips the tight premium stop before continuation. Bull analog of L51 / L55 / L74. The
premium stop is the wrong exit primitive for this entry in this regime.

## Candidate variants to backtest (Chef / Kitchen — edge_capture x sharpe per OP-16)
1. **Chart-stop in low-VIX bull:** when VIX<16 AND side=C AND setup=BULLISH_RECLAIM, use
   chart stop (reclaimed_level - 0.50) instead of premium stop. Measure vs current.
2. **Regime-widened premium stop:** bull stop -8% -> -15%/-20% when VIX<16.
3. **Trigger-quality gate:** require confluence (not lone level_reclaim) for bull reclaims
   when VIX<16 — fewer, cleaner shots.
4. **Combo:** chart-stop + confluence-gate.

## Gates before this can be ratified (OP-16 / OP-11 eval-first)
- BULLISH_RECLAIM is still DRAFT scope (OP-16 scope lock: needs 3 live J wins). This
  candidate does NOT promote it — it only proposes a better exit IF/when bull reclaims are taken.
- Must show: improves missed-week per-contract WITHOUT regressing the J-edge anchor
  (5/04 721P +$804 captured 2026-05-31) or the bear-side BEARISH_REJECTION book.
- Real-fills + OOS walk-forward required (L50). No BS-sim-only claims (L71/L73).

## Provenance / caveats (OP-20)
- SPY + option fills: REAL Alpaca SIP / OPRA 5m.
- VIX on target days: RECONSTRUCTED (VIXY x 0.648, calibrated to last real VIX 16.82 on
  05-22). Regime gates (bull<17.20) cleared all week regardless, so the proxy doesn't change
  the qualitative finding.
- Backtest qty is quality-tier fixed (not equity-capped) — use per-contract P&L.

## Kitchen
Cook task enqueued 2026-05-31 (id 0e03a763) to backtest variants 1-4 on real OPRA fills.
