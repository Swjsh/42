# EXPANDED GATE TEST (all cached OOS days, real fills only, no BS_FALLBACK)

307 real-fills trades / 345 OOS days. G_NO_midday_trendline is new: blocks the 24-loser pattern the autopsy exposed.

| gate | n | WR | total/c | per-trade/c |
|---|---|---|---|---|
| ALL production (real fills only) | 307 | 0.3 | +1169 | +3.8 |
| G_conf_required | 119 | 0.27 | +874 | +7.3 |
| G_ge2trig | 146 | 0.29 | +1288 | +8.8 |
| G_not_midday | 161 | 0.35 | +1383 | +8.6 |
| G_conf_OR_ge2trig | 146 | 0.29 | +1288 | +8.8 |
| G_conf_AND_not_midday | 76 | 0.33 | +761 | +10.0 |
| G_ge2trig_AND_not_midday | 94 | 0.34 | +1006 | +10.7 |
| G_NO_midday_trendline **← new** | 218 | 0.31 | +1562 | +7.2 |
| G_BEAR_only | 187 | 0.32 | +234 | +1.3 |
| G_BULL_only | 120 | 0.28 | +935 | +7.8 |
| G_BEAR_conf | 16 | 0.38 | +298 | +18.6 |
| G_BEAR_ge2trig | 26 | 0.35 | +353 | +13.6 |

## Key comparisons
- G_conf_AND_not_midday: +10.0/trade vs base +3.8 (lift +6.2/c), n=76, WR 0.33, total +761/c
- G_ge2trig_AND_not_midday: +10.7/trade vs base +3.8 (lift +6.9/c), n=94, WR 0.34, total +1006/c
- G_NO_midday_trendline: +7.2/trade vs base +3.8 (lift +3.4/c), n=218, WR 0.31, total +1562/c
- G_BEAR_conf: +18.6/trade vs base +3.8 (lift +14.8/c), n=16, WR 0.38, total +298/c
- G_BEAR_ge2trig: +13.6/trade vs base +3.8 (lift +9.8/c), n=26, WR 0.35, total +353/c

## Verdict: which is the strongest LARGE-SAMPLE (n>=30) gate?
  1. G_ge2trig_AND_not_midday: +10.7/trade, WR 0.34, n=94, total +1006
  2. G_conf_AND_not_midday: +10.0/trade, WR 0.33, n=76, total +761
  3. G_ge2trig: +8.8/trade, WR 0.29, n=146, total +1288
  4. G_conf_OR_ge2trig: +8.8/trade, WR 0.29, n=146, total +1288
  5. G_not_midday: +8.6/trade, WR 0.35, n=161, total +1383