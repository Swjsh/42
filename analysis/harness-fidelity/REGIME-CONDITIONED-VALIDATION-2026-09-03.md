# REGIME-CONDITIONED-VALIDATION-2026-09-03

RESEARCH. Runs the frozen METHOD prereg `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json` and adds a go-live-gate regime-coverage disclosure. Evidence status only -- no params/heartbeat/live file touched, no orders.

Generated: 2026-09-02T23:32:38.381692

## Method verdict (reproduced)

- **self_validation_verdict:** EARNS_RIGHTS
- reproduced cleanly: True
- known-bad verdicts: {'nlwb_full_real_fills': 'FAIL', 'confluence_real_fills_fresh95': 'FAIL', 'double_top_real_fills': 'FAIL', 'pure_noise_random_entry_placebo': 'FAIL'}
- known-good vwap_continuation verdict: PASS
- OP-16 anchor dates all labelable: True
- fail reasons: []

**overall_status_for_prereg: RUN_COMPLETE_EARNS_RIGHTS**

## VIX-band extension

- base (frozen) file: `backtest\data\vix_5m_2025-01-01_2026-07-08.csv` through 2026-07-08
- extension file: `backtest\data\vix_5m_2026-05-19_2026-09-02.csv`, added 40 days through 2026-09-02
- VIX frame seasonality check: winter_offset=-0500 summer_offset=-0400 fixed_offset_defect_suspected=False
  - VIX offset varies by season as expected (real tz-aware writer) -- et-v2 re-parsing is NOT needed for this VIX file. The winter-timestamp defect documented in backtest/lib/et_frame.py applies to the SPY/OPRA wide files (fixed -04:00 year-round), not the VIX master.

## Trend-cache boundary (data gap, disclosed)

- cache_last_bar_date: 2026-07-14 (+5d guard)
- Every date after cache_last_bar_date + staleness_guard_days is labeled trend='unknown' (reason=trend_cache_stale_past_...), never computed from a stale bar window. Extending this would require re-deriving daily bars from intraday SPY data, which the prereg's own classifier spec forbids.

## Real trade record regime coverage (analysis/trades-enriched.jsonl)

n_trades_total=403 n_trend_unknown_stale_trades=269

| regime | n_trades | n_distinct_dates | pnl_total | pnl_mean_per_trade |
|---|---|---|---|---|
| LOW_unknown | 60 | 7 | 1470.0 | 24.5 |
| MID_downtrend | 112 | 9 | -1425.0 | -12.72 |
| MID_unknown | 209 | 24 | 340.0 | 1.63 |
| MID_uptrend | 22 | 4 | 202.0 | 9.18 |

## Go-live gate evidence window regime coverage (automation/state/core-decisions.jsonl)

lifetime_dates (6): ['2026-08-26', '2026-08-27', '2026-08-28', '2026-08-31', '2026-09-01', '2026-09-02']

n_trend_unknown_stale=6 of 6 dates

| date | regime | vix_band | trend |
|---|---|---|---|
| 2026-08-26 | MID_unknown | MID | unknown |
| 2026-08-27 | MID_unknown | MID | unknown |
| 2026-08-28 | LOW_unknown | LOW | unknown |
| 2026-08-31 | LOW_unknown | LOW | unknown |
| 2026-09-01 | LOW_unknown | LOW | unknown |
| 2026-09-02 | MID_unknown | MID | unknown |

## Interpretation (disclosure only -- no_ship_clause)

The regime-conditioned method earned rights 2026-07-17 (reproduced clean here). Applying its VIX-band half to the go-live gate's own evidence window (the dates above) shows LOW/MID bands only, zero HIGH days -- consistent with, not new information beyond, go-live-gate.json's own calm-only disclosure. The TREND half of the label cannot currently be computed for any of those dates (cache stale since 2026-07-14) -- the regime-conditioned method cannot yet fully characterize the live evidence window it would need to in order to add anything past what go-live-gate.json and REGIME-STRESS-2026-09-02.md already disclose. This is a genuine, disclosed capability gap, not a finding about the engine.
