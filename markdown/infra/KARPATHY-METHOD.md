# Karpathy Method — Eval-First, Data Flywheel, Shadow Mode

> Relocated from CLAUDE.md OP-11 on 2026-06-26 (context-leanness trim). Eval-first gate + FORBIDDEN FRAMING stay inline in CLAUDE.md.

## Loop architecture

- **INNER loop:** heartbeat fires production AND shadow version in parallel; shadow is read-only. Controller: `automation/state/shadow-version.json`.
- **MID loop (daily):** `append_today.py` feeds data flywheel. EOD-summary 8b/8c runs drift check + shadow diff scorecard. Premarket Step 1d gates on severity.
- **OUTER loop (weekly):** shadow dominates 5-of-7 with positive margin → auto-generates A/B scorecard (`auto_ratify`). Premarket auto-bumps params.json Monday. J's role = REVOKE, not approve.

## Reproducibility

`backtest/lib/repro.py` — `run_id = {date}_{code_hash[:8]}_{data_hash[:6]}_{params_hash[:6]}`. Historical runs stay frozen.

## Loss walk

EOD-summary 7i generates per-loss chart-walk in `journal/losses/`. Weekly-review 3.5 clusters fingerprints → R-NNNN candidates.

## Cost

~$0.15/day total (shadow eval + data flywheel + drift check).
