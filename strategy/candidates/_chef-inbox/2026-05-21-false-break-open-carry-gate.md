# Chef research item: False-break-at-open ★★★ Carry gate

> Queued by Analyst 2026-05-21. Chef picks up at next fire.

## Observation
On 2026-05-21, SPY had a ★★★ Carry level at 738.10 (9 touches, 7 holds). At the 09:35 open bar, SPY printed low 737.53 (−$0.57 through the level). By 09:40, SPY had closed back above 738.10. The engine entered a BEARISH_REJECTION trade at 10:35 ET — valid by all 10 rules — but the 738.10 false-break-and-recovery at open was the signal that trapped shorts were fueling a bull squeeze. Session closed +$4 above entry. Loss: −$204.

The L59 floor_hold pattern requires N≥3 consecutive bars wicking through a level but closing above it. This was a single-bar version at the open, which may warrant a different (faster) detection threshold.

## Hypothesis to test
**Pre-entry gate:** When a ★★★ named level (Carry, Active, multi-day structure) is breached at the RTH open bar (09:35) and the NEXT closed bar recovers above the level (close > level), suspend bear entries for 30 min (until 10:05 ET). During this window, watch for bull ribbon confirmation.

## Backtest specification
- Date range: 2025-01-01 to 2026-05-21 (full 16-month cache)
- Engine flag: `false_break_open_suspension_minutes=30` (test 0 / 15 / 30 / 45 as variants)
- Entry pattern: BEARISH_REJECTION_RIDE_THE_RIBBON only
- Gate condition: open_bar_low < level − $0.25 AND next_bar_close > level
- Measurement: WR and P&L on gated days (with gate) vs control (without gate)
- Edge_capture floor (per OP-16): must hit ≥$771 to be PROMISING on J anchor days

## Why now
2026-05-21: cost −$204 on a bear trade that entered AFTER a false-break recovery signal at 738.10 that the premarket checklist had no branch to detect. This is the single-bar version of L59 (floor_hold). The same mechanism (trapped shorts → bull fuel) applies at open breaks more violently than mid-session.

## Prior art
- L59 (2026-05-20): N≥3 bar close-ceiling distribution pattern — this is the put/bear analog
- L51: initial bounce on VIX≥20 level-break entries = premium stop incompatible (related: bounce dynamics on level breaks)
- floor_hold detection in `crypto/lib/chart_patterns.py::detect_floor_hold()` — can be called with n_min=1 for single-bar variant
