# crypto/CLAUDE.md — Mini-doctrine for the crypto validation harness

> This file extends the project-root `CLAUDE.md`. Read both.

## What lives here

This folder is a **24/7 validation harness for chart-reading and decision-tree primitives** that the SPY 0DTE engine depends on. Crypto markets never close, so we can validate bar-reading, indicator, and pattern-recognition logic anytime.

## What lives elsewhere (do NOT cross-contaminate)

| Belongs in `crypto/` | Belongs in project root |
|---|---|
| Bar-reading / closed-bar logic tests | SPY heartbeat production logic |
| Indicator math validation (RSI/EMA/VWAP) | params.json / params_safe.json / params_bold.json |
| Candlestick pattern recognition tests | Live trade execution, journal, mistakes log |
| Trendline / level-detection unit tests | Doctrine evolution (CLAUDE.md, OP additions) |
| Multi-source data parity checks | Strategy playbook, kill switches, dual-account orchestration |

## Operating principles (specific to this folder)

1. **No live orders.** This folder NEVER places crypto orders. If we ever trade crypto, it goes in a separate folder. Hard rule.

2. **Pure Python validators, no LLM in the loop.** Validators are deterministic data-processing scripts. Zero recurring LLM cost. Reproducible.

3. **Multi-source by default.** Every validator that hits live data MUST be runnable against ≥ 2 of: Coinbase REST, yfinance, Alpaca crypto MCP. If sources disagree, the validator must report it — never silently pick one.

4. **Time math always in UTC, displayed in ET when user-facing.** Crypto runs on UTC; SPY runs on ET. To translate cleanly, internal types are tz-aware UTC. Display layers convert.

5. **Validators are scorecards, not just pass/fail.** Output: a JSON scorecard with `verdict`, `evidence`, `seconds_since_close`, `source_disagreement_count`, etc. Machine-readable. Reusable.

6. **If a validator finds a bug in a primitive, the primitive gets fixed in `crypto/lib/`, the production SPY heartbeat is updated to use the corrected primitive, and an OP/L entry is appended to root CLAUDE.md.** This is the value loop.

7. **New validators arrive via `validator-author` (OP-29 Skills Pipeline).** Analyst drops a finding in `strategy/candidates/_validator-inbox/`; overnight wake fire invokes `validator-author`; it writes `crypto/validators/v{NN}_{slug}.py` (with `run_offline()` + `run_live()` per the v01-v22 contract), appends entries to `runner.py` stages list, runs the full gym, and bumps the OP-26 stage count in root CLAUDE.md ONLY if the gym is green. Engine-benefit autonomy per OP-22 — no weekend ratification needed because validators only add coverage, they don't modify live-trading doctrine. Manual override: J or interactive Gamma can still write a validator by hand following the same v01-v22 pattern (file naming, runner.py registration, gym-must-be-green-before-OP-26-bump).

## Style

- Many small files. One responsibility each.
- Pure functions where possible. No global state in `lib/`.
- Dataclasses for value types (Bar, BarSeries, ValidationResult).
- Type hints everywhere.
- No comments explaining what; only why-it's-non-obvious.
- Pandas only inside `data_sources.py` ingestion + `indicators.py` math. Don't pass DataFrames around.

## Cost discipline

- Validators run on-demand (zero recurring cost).
- If we later add a 24/7 heartbeat for crypto, it must be programmatic (cron-fired Python), not LLM-in-loop. Budget cap: $5/mo.
- Coinbase REST is rate-limited to 10 req/s public. yfinance is unlimited. Alpaca crypto MCP follows project key quota.
