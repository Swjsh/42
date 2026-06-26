# Plan 2 — Higher-Timeframe Context Layer (the zoom-out)

> J's 2026-06-24 insight: "do we even zoom out ever to like the 4h chart and see what the market has done over the past week or 2, like where larger supply/demand zones are, or where key levels have been respected for the past X days."

## The gap
The engine reads the **5m chart** + a single `htf_15m` stack. It does **not** zoom out to 4H / daily / multi-week structure. So it plays intraday levels blind to: larger supply/demand zones, where price has ranged over 1–2 weeks, and which levels have been *respected vs broken* over the past X days. A 5m level inside a fat HTF demand zone is a very different trade than the same level in no-man's-land.

## Scope (research → spec → build)
1. **Audit current HTF handling** — what `htf_15m` actually does; is anything above 15m read? (likely nothing.)
2. **4H + daily structure** — pull 4H/1D OHLCV (TV MCP / Alpaca), detect swing structure (HH/HL/LH/LL) over the past 1–2 weeks.
3. **Supply/demand zones** — larger HTF S/D zones (consolidation-before-impulse), drawn as bands not lines.
4. **Level-respect history** — for each named level, how many times it was respected vs broken over the past X days (a respect-score). Reuse/extend the key-levels benchmark work (`markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md`).
5. **Value test** — does HTF context improve the key-level plays (today's reclaim sat where in the HTF picture)? Gate or confluence-modifier, not a veto.

## Deliverable
- HTF context module spec + a `htf_4h` / `daily_zones` / `level_respect_score` signal added to the read.
- Value assessment vs the anchor days. If it lifts edge → wire as a confluence input under OP-22.

## Owner / status
Background research agent (spawned 2026-06-24). Advisory/spec first; no live changes until validated.
