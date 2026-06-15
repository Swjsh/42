# SELECTIVITY GATE test — does conviction concentrate the OOS edge? (real fills)

Production OOS trade set: 68 trades / 60 cached-fill days. Each gate FILTERS that exact set (no re-run). This tests J's 'more sniper entries' thesis.

| gate | n | WR | total/c | per-trade/c | green days/traded |
|---|---|---|---|---|---|
| ALL (production, ungated) | 68 | 0.32 | +272 | +4.0 | 18/46 |
| G1: confluence required | 19 | 0.42 | +490 | +25.8 | 8/16 |
| G2: >=2 triggers | 25 | 0.4 | +500 | +20.0 | 10/20 |
| G3: not MIDDAY | 35 | 0.4 | +555 | +15.9 | 14/31 |
| G4: confluence OR >=2 trig | 25 | 0.4 | +500 | +20.0 | 10/20 |
| G5: (conf OR >=2trig) AND not-midday | 17 | 0.47 | +448 | +26.4 | 8/16 |
| G6: >=2 triggers AND not-midday | 17 | 0.47 | +448 | +26.4 | 8/16 |
| G7: confluence AND not-midday | 15 | 0.47 | +424 | +28.3 | 7/14 |

## Verdict
- Ungated production: +272/c total, +4.0/trade, WR 0.32, n=68.
- **Best viable gate (n>=15): G7: confluence AND not-midday -> +28.3/trade (WR 0.47, n=15, keeps 22% of trades, total +424/c).**
- Per-trade lift vs ungated: +24.3/c (BETTER). Total higher P&L on far fewer trades = higher quality + less PDT/capital usage.

**This is the ratifiable lead (DRAFT for J, Rule 9):** a SELECTIVITY gate (require confluence or >=2 triggers, optionally skip midday) maps directly to existing params (filter_10_min_triggers_bull/bear, confluence_min_signals) — no new code. Validate via grinder + walk-forward, compare edge_capture x sharpe per OP-16, then gamma-sync. It is exactly J's 'sniper entries' instinct, now backed by a 68-trade segmentation that agrees across confluence, trigger-count, AND time-of-day.