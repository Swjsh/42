# Monday 2026-05-18 — Key Levels (Carried From 5/15 Close)

> Reference for setting TV alerts and SHOTGUN_SCALPER target identification.
> Last updated: 2026-05-15 evening (post-EOD).

## Structural levels (set TV alerts on these)

| Price | Type | Stars | Notes |
|---|---|---|---|
| 745.43 | Resistance | ★★★ | 5/14 PMH (CPI gap-up high) — may be retired if not retested |
| 744.35 | Resistance | ★★ | 5/15 PMH (04:00 ET premarket bar) |
| 741.84–741.93 | Resistance | ★★ | 5/15 RTH open rejection zone (multi-touch through session) |
| 740.00 | Psychological | ★ | Round number / ribbon Pivot EMA neighborhood |
| 739.04 | Support | ★★ | 5/15 PML (08:15 ET premarket bar) |
| 738.86 | Support | ★★ | R2 pivot flipped-to-support (reference) |
| 738.10 | Support | ★★★ | Carry — 5-touch hold. **Carry tier expired 5/15 18:00**, but structurally still load-bearing. Premarket should re-promote if respected. |
| 737.96 | Support | ★★ | 5/15 RTH session low — NEW level for Monday |
| 737.44 | Support | ★ | 5/15 EOD wick low (15:55 bar) |

## TV alert setup (manual — auto-create failed tonight)

Set these alerts on the TradingView SPY chart for Monday:

1. **Crossing 744.35** — "PMH 5/15 test"
2. **Crossing 741.84** — "5/15 RTH open rejection level"
3. **Crossing 740.00** — "Round number / Pivot EMA"
4. **Crossing 739.04** — "5/15 PML support"
5. **Crossing 738.10** — "Carry 5-touch support — PRIMARY FLIP"
6. **Crossing 737.96** — "5/15 RTH session low"

If alert support stays broken in the MCP DOM automation, J can set these manually in TV via the alert button. Cost: 30 seconds.

## SHOTGUN_SCALPER pre-staged scenarios for Monday

### Bearish (if open near 744.35 or 741.84)
- **T1 OPEN_REJECTION:** if 09:30 bar wicks above 744.35 then closes below open → PUT @ ITM-1 of 744 (P744). Target: 740.00 then 739.04. Single exit at target.
- **T2 LEVEL_REJECT_LIVE:** if any 5m bar wicks into 744.35 (within $0.10) then prints lower-high with vol ≥ 1.5× → PUT @ OTM-1. Target: 741.84 then 740.

### Bullish (if open near 738.10 or 737.96)
- **T1 OPEN_REJECTION:** if 09:30 bar wicks below 737.96 then closes above open → CALL @ ITM-1 (C737). Target: 739.04 then 740.
- **T2 LEVEL_REJECT_LIVE:** if any 5m bar wicks below 738.10 then prints higher-low + vol ≥ 1.5× + close above 738.10 → CALL @ OTM-1. Target: 740.00 then 741.84.

### Trendline (T3)
- Identify intraday trendline of ≥3 touches over ≥30 min — wait for clean break + retest before firing.

## Premarket prep checklist for 5/18 (Gamma_Premarket auto)

- [ ] Re-evaluate Carry tier of 738.10 — promote back if respected Monday
- [ ] Add new Active levels from any after-hours / pre-market action
- [ ] Set TV alerts manually if auto failed again
- [ ] Verify SHOTGUN_SCALPER watcher is firing in `automation/state/watcher-observations.jsonl`
- [ ] Bold account: verify $1,000 seed visible in Alpaca paper dashboard (per CLAUDE.md account context section)
