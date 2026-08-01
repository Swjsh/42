# Regime Library — deterministic day archetypes (WS6, built 2026-08-01)

**What this is:** every trading day in the verified population tagged with ONE
mechanical archetype computed from RTH 5m OHLC alone. No LLM, no indicators, no
trading verdicts. The concrete instrument for *"is the recent market a different
animal than the population my evidence came from?"*

**Not to be confused with** `backtest/lib/regime_classifier.py` — that is the
pre-open, lookahead-safe strategy ROUTER (MACRO_VETO/GAP_DAY/...). This library is
POST-HOC (uses the whole session): it may slice studies and stamp *yesterday*,
never feed a live entry decision for the same day.

| Piece | Path |
|---|---|
| Artifact | `analysis/regime-library/day-archetypes.json` |
| Builder | `backtest/tools/build_day_archetypes.py` (`--check` = byte-identity verify) |
| Slicing helper | `backtest/lib/regime_slice.py` (pure stdlib — `per_archetype_rows()` one-call) |
| Premarket stamp | `automation/scripts/regime_stamp.py` → `automation/state/regime-stamp.json` + `today-bias.json#regime_context` (Gamma_RegimeStamp 08:22 ET) |
| Guards | `backtest/tests/test_regime_library_guards.py` (22 tests, mutation-RED-proofed) |

## Data lineage + frame

- `spy_5m_2025-01-01_2026-07-22.csv` (master, authoritative ≤ 2026-07-22 — untouched by the 2026-07-31 OPRA backfill) + newest `spy_5m_2026-05-19_*.csv` rolling file for later days (end-date parsed from filename). Same two-file rule as `g2_trendline_bypass_ab_2026_08_01.py`. VIX identical lineage.
- The 2024 backfill lineage is deliberately **not read** (verified population starts 2025-01-02; feed seams are a known corruption source).
- **Frame: et-v2** (DST-correct), explicit opt-in per `backtest/lib/et_frame.py`. New pipeline, no wall-v1 scorecard to match — and wall-v1 would clip the last true trading hour on EST-month days, corrupting session OHLC.
- Determinism: byte-identical re-run given identical inputs (sorted keys, fixed rounding, no timestamps in the body; provenance = input sha256). Verified at build: two consecutive builds → sha256 `8f1bf155…` both.

## Day accounting (population block, honest counts)

394 data-days in 2025-01-02..2026-07-31: **386 full** (78 bars) + **3 exchange half-days** (2025-07-03, 2025-11-28, 2025-12-24) + **4 truncated-tail** (feed missing the final 25 min: 2025-01-31, 2025-03-03, 2025-12-03, 2025-12-31 — close = last bar on file, disclosed via `session` flag) + **1 incomplete** (2026-06-15, 12 bars → `data-incomplete`, excluded from all distribution stats). Replay populations quoted elsewhere (e.g. "391") may exclude short sessions — **join on date, never on count**; `regime_slice` buckets unknown dates as `UNTAGGED` loudly.

VIX attach: first/last bar in the RTH window per day (master granularity is coarser early on, so "open" may be the first in-window print, not 09:30:00 exactly; premarket quotes like today-bias `vix_at_open` will differ slightly by definition).

## Archetype definitions (spec 1.0.0 — frozen; change = version bump)

Features per session: `o,h,l,c`, `gap% = 100·(o−prior_c)/prior_c`, `range% = 100·(h−l)/o`, `body% = 100·(c−o)/o`, `close_loc = (c−l)/(h−l)`, `open_loc = (o−l)/(h−l)`, `t_high/t_low` = fraction of session elapsed at the FIRST bar printing the extreme.

Cascade — first match wins (gap mechanism > reversal shape > trend > pin > residual):

| # | Archetype | Mechanical rule (thresholds in `thresholds` block of the JSON) |
|---|---|---|
| 1 | **gap-fade** | \|gap%\| ≥ 0.30 AND the gap FILLS (touches prior close) AND closes back through the open against the gap direction |
| 2 | **gap-go** | \|gap%\| ≥ 0.30 AND never fills AND closes beyond the open in the gap direction |
| 3 | **V-reversal** | range% ≥ 0.50, low printed in first half (`t_low` ≤ 0.50), excursion below open ≥ 55% of range, closes in top 30% (`close_loc` ≥ 0.70) |
| 4 | **inverted-V** | mirror of V: early high, pop above open ≥ 55% of range, closes in bottom 30% |
| 5 | **trend-up** | body% ≥ 0.60, opens in bottom 40% of range, closes in top 25% |
| 6 | **trend-down** | body% ≤ −0.60, opens in top 40%, closes in bottom 25% |
| 7 | **pin-day** | range% ≤ 0.50 AND \|body%\| ≤ 0.12 (closes where it opened) |
| 8 | **range-chop** | residual — no mechanism resolved |

Precedence consequence, documented and guard-pinned: **2025-04-09** (the +9.75% tariff-pause rip) is labeled `gap-fade` — it gapped down significantly, filled, and closed above the open; the V shape lives in its features (`close_loc` 0.94). Landmark pins: 2025-04-03/04 crashes = `gap-go`; 2026-07-31 = `V-reversal`.

Thresholds were chosen by inspecting the population distribution during the 2026-08-01 build (descriptive taxonomy design — no P&L, no fitting to outcomes).

## Distribution — full population vs last 25 days (at build, 2026-08-01)

Assignable days: 393. Last-25 window: 2026-06-26..2026-07-31. **Mix L1 distance: 0.22** (0 = identical mix, 2 = disjoint).

| Archetype | Full pop | Full % | Last 25 | Last-25 % |
|---|---|---|---|---|
| range-chop | 159 | 40.5% | 9 | 36.0% |
| gap-go | 87 | 22.1% | 5 | 20.0% |
| gap-fade | 62 | 15.8% | 4 | 16.0% |
| trend-up | 28 | 7.1% | 1 | 4.0% |
| pin-day | 21 | 5.3% | 1 | 4.0% |
| trend-down | 15 | 3.8% | 1 | 4.0% |
| V-reversal | 12 | 3.1% | 3 | 12.0% |
| inverted-V | 9 | 2.3% | 1 | 4.0% |

Read: the recent market is **modestly V-ier** (12% vs 3.1% V-reversal — 3 of the last 25 days) and slightly less trend-up/pin than the population baseline; otherwise the mix is close to baseline (L1 0.22). This table regenerates on every build; the live morning version is the `regime_context` line in `today-bias.json`.

## Regenerate / verify

```
backtest/.venv/Scripts/python backtest/tools/build_day_archetypes.py          # rebuild
backtest/.venv/Scripts/python backtest/tools/build_day_archetypes.py --check  # byte-identity
backtest/.venv/Scripts/python -m pytest backtest/tests/test_regime_library_guards.py -q
```

The premarket stamp task (`Gamma_RegimeStamp`, 08:22 ET) rebuilds the artifact each
weekday morning so "yesterday" is always tagged, then writes the one-line stamp.
