# Loss walk — 2026-05-15 09:46 BEARISH_REJECTION_RIDE_THE_RIBBON

## Trade snapshot
- Entry: 09:46:38 ET @ $3.14 — 10 contracts, SPY260515P00740000 (740P 0DTE)
- Exit: 09:50:32 ET @ $2.37 — exit_reason: STOP_PREMIUM (limit $2.47 stuck → market fill)
- P&L: −$770 (−24.5% on premium)
- Hold: 4 min | MAE: $0.77 ($3.14 → $2.37) | MFE: $0 (no favorable excursion post-entry)
- cf_time_stop_pnl: +$410 (held to 15:50 ET) | cf_high_water: −$770 (entry was the peak)

## Trigger conditions at entry
- Bear score: 10/10 (all filters passed)
- Triggers fired: PML 739.04 break on closed 09:40 bar (close 738.66)
- Ribbon stack: BEAR, spread 57¢ (Fast 739.73 / Pivot 739.98 / Slow 740.30)
- HTF 15m: null (not available at entry time)
- VIX: 19.20 (rising direction) — bear VIX gate PASSED
- IV regime: MID (VIX 19.20)
- tape_assistance: unfavorable

## Chart walk — what J's eye would have seen

*(TradingView replay screenshots unavailable in non-interactive session — narrative from bar data)*

### One-paragraph narrative
The 09:30 RTH bar opened at 741.84 and rejected immediately (bearish open). The 09:35 bar continued lower to 739.15, touching the PML 739.04 level. The 09:40 bar was the key bar: its low was 737.96 (breaking through both PML 739.04 AND Carry ★★★ 738.10), but it closed at 738.66 — a hammer-like reversal candle that suggests buyers absorbed the dump. By the time the closed-bar R1 filter confirmed the break at 09:45 and entry was placed at 09:46, SPY had already bounced from 737.96 → 738.64 and was continuing toward 739.83. The structural setup (BEAR ribbon, PML break, VIX elevated) was sound, but the entry occurred precisely at the point where the bear impulse had exhausted and buyers were in control. This is the "fast-dump-fast-reverse" pattern where closed-bar confirmation systematically lags the actual signal by one full bar.

## Filter audit
- Filter 1 (session timing 09:35–15:00): PASS ✓ — entry at 09:46 within window
- Filter 2 (macro blackout): PASS ✓ — no RTH news block today
- Filter 3 (ribbon stack BEAR): PASS ✓ — BEAR 57¢ at entry
- Filter 4 (spread ≥30¢): PASS ✓ — 57¢ > 30¢
- Filter 5 (BEAR stacked): PASS ✓
- Filter 6 (spread confirmed): PASS ✓
- Filter 7 (no vol divergence): PASS ✓
- Filter 8 (VIX gate — rising ≥17.30): PASS ✓ — VIX 19.20 rising
- Filter 9 (vol multiplier ≥0.7×): PASS ✓
- Filter 10 (trigger fired): PASS ✓ — PML break on closed bar
- All 10 filters: PASS ✓

**Filter audit result:** No filter failure. Every filter correctly passed. The loss was not a filter miss — it was an execution-timing structural issue.

## Candidate filter that would have blocked this loss
`bar_reversal_size_cents: no_gate → SPY_reversal_from_bar_low >= 50c blocks entry`

If the 09:40 bar had a wick-to-close range ≥ 50¢ (wick was 737.96, close was 738.66 = 70¢ reversal), a "hammer candle" filter would have blocked this entry. Current system has no filter on bar reversal magnitude after a level break. The level broke, but the bar structure was a hammer (long lower wick, close near open) — a classically ambiguous pattern that can represent either exhaustion or absorption.

Alternative formulation: `post_break_bar_close_above_level: if 5m bar that breaks the level also closes ABOVE the level (re-test scenario), require next bar to confirm direction before entering.`

The 09:40 bar closed at 738.66, which is BELOW PML 739.04 — so the "level still broken" check passed. The hammer reversal structure is the uncaptured signal here. Worth testing in backtest.

**Not LOSS_INHERENT** — there is a candidate filter. Variance played a role, but the hammer structure at 09:40 was a yellow flag the system missed.

## Pattern fingerprint (for D2 mining)
`BR|MID|NULL|unfavorable|stop_premium|hammer_reversal_after_break`
