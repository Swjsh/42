# Candidate — GEX_FLIP_REGIME_TAG (pre-registration, DATA-GATED)

**Filed:** 2026-07-21 · **Author:** conductor (AFTERHOURS, acting as chef — Agent tool unavailable this fire) · **Status:** DATA-GATED / PRE-REGISTERED (not yet run — accrual floor not cleared)

**Routed from:** `strategy/candidates/_chef-inbox/2026-07-09-prospector-gex_flip_from_banked_cboe.md` (Gamma_Prospector 2026-07-09, dedupe_key `gex_flip_from_banked_cboe`)

## Why this is a pre-reg, not a backtest

`gex_regime.assess_backtest_feasibility()` is unconditional: `can_backtest_now: False` — GEX needs a daily full-chain OI+gamma snapshot archive, which cannot be reconstructed from the OPRA price-only cache. `Gamma_CboeOiBank` has been banking that archive daily since 2026-06-22. **As of this fire: 23 sessions on disk** (`journal/gex-archive/*.json`, latest `2026-07-21-cboe.json`, `gex_archive_health.py`'s own floor note: "~60-90 sessions" needed for a well-powered split). 23 < 60 — **not ready.** This candidate exists so that the day the floor clears, the design is already fixed and nobody re-derives it under time pressure (avoids a post-hoc "pick the split that works" bias). Cross-ref: `CLIMB-LADDER-NEXT-RUNG-IS-CLASS` in `automation/overnight/queue.md`, and standing project memory `project_instrument_rung_closed_climb_to_class` (class rung = calendar-gated, do not re-litigate feasibility every fire — just watch the count).

## Pre-registered design (frozen — do not tune after the floor clears)

**Regime tag (per prior session, look-ahead-safe):**
For each `journal/gex-archive/{D}-cboe.json` (schema: `session_date`, `by_symbol.SPY.contracts[]` with `strike/right/open_interest/gamma`, `by_symbol.SPY.spot` captured ~13:55 ET intraday, NOT the 16:00 close):
1. Build `GammaContract` rows via the existing `from_alpaca_snapshot`-equivalent adapter for the CBOE archive shape (new thin adapter needed — the archive's `by_symbol.SPY.contracts` shape is close to but not identical to the Alpaca snapshot shape; DO NOT reuse `from_alpaca_snapshot` unmodified, write `from_cboe_archive_snapshot` mirroring it 1:1 on field names).
2. Call `compute_gex_regime(contracts, spot=archived_spot)` → `regime` (`long_gamma_pin` / `short_gamma_trend` / `flat`) and `zero_gamma_flip`.
3. **Regime tag for date D is used only for trading day D+1** (the next trading session) — this is what makes the join look-ahead-safe: D's archive is fully known before D+1's open. (C6 discipline: no same-day use of a value captured at 13:55 to explain that same day's earlier-session trades.)

**Join key:** `trade_entry_date (ET calendar date, from decisions.jsonl / real-fills log) == archive_session_date + 1 trading day` (skip weekends/holidays via the existing trading-calendar helper already used by the backtest — do not hand-roll a new one, C9-adjacent).

**Null hypothesis (frozen, exact):** Trade outcome (P&L per trade, MFE, stop-hit rate) for BEARISH_REJECTION / LEVEL_REJECT ("fade"-style) and BULLISH_RECLAIM / trend-continuation setups is **independent** of whether the prior session closed in `short_gamma_trend` (below flip) vs `long_gamma_pin` (above flip) regime.

**Directional hypothesis under test (from the prospector finding):** continuation/breakout setups outperform in `short_gamma_trend` (prior day negative-gamma → dealer hedging amplifies moves); fade/reversion setups outperform in `long_gamma_pin` (prior day positive-gamma → dealer hedging dampens moves).

**Metric / instrumentation (reuse, don't re-derive — C14/C17):** split existing real-fills trade log by regime tag, compute per-regime `probe_stats.summarize_trades` (mean/median/expectancy), `probe_stats.significance` (n<10 floor), `probe_stats.day_concentration` (top-3-day % > 150% flag), `probe_stats.base_verdict`. Do **NOT** hand-roll a new significance/concentration threshold for this candidate.

**OP-16 pass bar (this is a regime TAG feeding an existing setup, not a new standalone setup):** apply the SAME anchor-no-regression + edge_capture discipline used for every other gate/veto in `_LEADERBOARD.md` (e.g. `STRUCTURE_VETO_DIR_VS_TREND`, `VIX_BULL_HARD_CAP_UNBLOCK` rows) — compute `edge_capture` delta on J's 3 anchor trading days with the regime filter ON vs OFF; regression on any anchor winner = REJECT regardless of aggregate lift. Aggregate must also clear `INCONCLUSIVE_MIN_N=10` per regime bucket and NOT be `CONCENTRATION_TOP3_PCT_MAX`-flagged.

**Caveat to disclose when run (do not silently drop):** the archived `spot` is captured ~13:55 ET, not the 16:00 close — the regime tag is a same-session-close *proxy*, not the literal close. GEX regime rarely flips in the last ~2h of a session but this is unverified for our specific archive; flag it explicitly in the eventual write-up rather than asserting "closed on."

## Data floor tracking

- **Needed:** ≥ 60 sessions (soft floor) / 90 (well-powered), per `gex_archive_health.py`.
- **Have (this fire, 2026-07-21):** 23 sessions, accruing daily, zero gaps (`engine-health.json` `gex_archive` check GREEN).
- **At current 1-session/trading-day accrual rate:** ~37 more trading days to the 60-session soft floor (~mid-September 2026), ~67 more to 90 (~late October 2026). A future fire should re-check the count via `gex_archive_health.py`, NOT re-derive this estimate from scratch.

## Next action (when floor clears)

Write `backtest/autoresearch/gex_flip_regime_ab.py` implementing exactly the join/null/metric above, using `probe_stats` for the numbers and this file's frozen design for the split. Until then: **no code to write, no data to fetch** — this file IS the deliverable.

## Disposition

`strategy/candidates/_chef-inbox/2026-07-09-prospector-gex_flip_from_banked_cboe.md` renamed `.DONE` (pre-registration filed; the item's own "bounded FIRST deliverable" is this document, not a backtest). `_LEADERBOARD.md` updated with a `DATA-GATED` row.
