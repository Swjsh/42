# OPRA 0DTE Option-Bar Cache — Backfill Report (2026-07-22)

## Verdict

**The requested backward extension to 2026-01-02 was already done — verified, not re-fetched.**
The mission brief's stated baseline ("current cache covers roughly 2026-05-18..2026-07-17,
~40 trading days") was stale. Cold-reality check (`analysis/edge-matrix/day-inventory-2026-07-23.json`,
freshly built 2026-07-22, plus file mtimes) shows the OPRA cache already had real fills for
**381 of 386 SPY-covered trading days, spanning 2025-01-02 → 2026-07-17** — done in a prior
session (`backtest/data/options/*.csv` mtimes ≈ 2026-05-13). The only genuine gap was the 5
most recent trading days (2026-07-15, 16, 20, 21, 22), which this session closed.

**Final state: 386/386 SPY-covered trading days now have real OPRA fills (100%).**
Cannot extend earlier than 2025-01-02 without first extending the underlying SPY/VIX 5m master
(`backtest/data/spy_5m_2025-01-01_*.csv` — 2025-01-01 is its hard floor); that's a different
tool (`extend_data_v2.py`) and out of this mission's scope.

## What was verified (before trusting the "already done" finding)

An extraordinary result ("the whole mission is already done") gets an artifact hunt before
being trusted, per doctrine. Checks run this session:

| Check | Result |
|---|---|
| Day-inventory audit (386 SPY days vs 381 OPRA days) | 5-day gap identified, all at the trailing/recent edge, none in the "backward" target range |
| Pre-existing cache spot-check: `SPY260102C00678000` (2026-01-02) vs fresh Alpaca fetch | 79/79 rows, **identical** |
| Pre-existing cache spot-check: `SPY250102C00580000` (2025-01-02) vs fresh Alpaca fetch | 75/75 rows, **identical** |
| `2025-12-15` directory listing sanity (guessed strike 600 was wrong — actual ATM ~676-680) | Confirms real, day-appropriate strike grids, not placeholders |
| File mtimes on pre-existing cache | 2026-05-13 (2+ months old — a real prior session, not fabricated just now) |

## Method — fetcher reused, no new auth path

- **Reused** `backtest/tools/expand_opra_cache.py` (the general-purpose OPRA backfill tool
  already in the repo, built for exactly this: `option_symbol()`, `fetch_contract_bars()`,
  `already_cached()`, `write_cache()`, `write_empty_sentinel()`), which itself uses
  `backtest/tools/_alpaca_creds.py#resolve_alpaca_creds()` — the same key-resolution path
  (env vars → project-root `.mcp.json` `alpaca` server env block) used everywhere else in
  this repo. No new auth path written, no key values printed or copied.
- **New:** `backtest/tools/_backfill_opra_recent_gap.py` — a thin wrapper that imports those
  same functions and targets just the 5 missing days, computing strike range as
  `[floor(day_low)-3, ceil(day_high)+3]` by $1 (per this mission's spec) using the RTH low/high
  pulled from `backtest/data/spy_5m_2026-05-19_2026-07-22.csv` (the newest rolling master that
  actually covers those dates — the full-window `spy_5m_2025-01-01_*.csv` masters only go
  through 2026-07-14). Both C and P.
- Zero order-placing modules imported or touched. Market-data reads only.

## Work performed this session

| Metric | Value |
|---|---|
| Days attempted | 5 (2026-07-15, 07-16, 07-20, 07-21, 07-22) |
| Days succeeded | 5 / 5 |
| Days skipped (no data) | 0 |
| Days failed | 0 |
| Contracts fetched | 136 (all new; 0 already cached) |
| Empty responses | 0 |
| HTTP errors / 429s | 0 |
| Elapsed | 67s (sequential, 0.35s sleep ≈ 170 req/min, under the 180/min cap) |

Per-day strike range fetched (both C+P):

| Date | RTH low | RTH high | Strike range | Contracts |
|---|---|---|---|---|
| 2026-07-15 | 750.20 | 755.58 | 747–759 | 26 |
| 2026-07-16 | 747.88 | 754.57 | 744–758 | 30 |
| 2026-07-20 | 741.51 | 748.73 | 738–752 | 30 |
| 2026-07-21 | 744.18 | 749.04 | 741–753 | 26 |
| 2026-07-22 | 746.37 | 750.02 | 743–754 | 24 |

## Post-fetch verification

- `lib/option_pricing_real.load_contract_bars()` parsed all 136 new CSVs cleanly — 136/136 OK, 0 parse failures.
- 3 random new contracts (`SPY260716C00746000`, `SPY260715C00753000`, `SPY260720C00752000`) re-fetched
  live from Alpaca and diffed against the cached CSV — **identical row-for-row** in all 3 cases.

## Final coverage map

- **Span:** 2025-01-02 → 2026-07-22 (387 unique expiry dates on disk; 386 of those are SPY-covered
  trading days per the day-inventory, all now with real OPRA fills; the 387th, 2026-06-15, has
  OPRA data but no SPY 5m bars in the current master — a pre-existing, unrelated anomaly, not
  touched this session).
- **Total cache:** 8,955 CSV files + 13 empty-sentinel files, ≈42.0 MB on disk (`backtest/data/options/`, gitignored — not committed).
- **Floor:** 2025-01-02, set by the underlying SPY/VIX 5m master's own floor (2025-01-01). Alpaca's
  historical-options coverage note (~Feb 2024 onward, spotty early) was never tested against —
  no reason to, since the master itself doesn't go back that far. Extending earlier requires
  extending the SPY/VIX master first (`extend_data_v2.py` / `merge_data.py`), out of scope here.

## Quota / rate-limit behavior

No 429s encountered at any point (136 sequential requests, 0.35s spacing ≈ 170 req/min, under
the 180 req/min budget). No backoff was ever triggered. Job ran as a single short-lived venv
Python process (reaper-exempt per `_shared.ps1#EXEMPT_DAEMONS` convention), well under any
plausible reaper window.

## Files touched

| File | Change |
|---|---|
| `backtest/tools/_backfill_opra_recent_gap.py` | **NEW** — reusable recent-gap backfill tool (imports `expand_opra_cache.py`'s fetch/write/auth functions) |
| `analysis/edge-matrix/opra-backfill-progress.json` | **NEW** — resumable progress record for this run (completed, 0 errors) |
| `analysis/edge-matrix/day-inventory-2026-07-23.json` | **AMENDED** — `has_opra`/`n_opra_files` flipped for the 5 newly-filled days, `opra_days` 381→386, `manual_amendments` log added (machine-readable diff). `day_type`/`gap_pct`/`vix_band` for those 5 rows and `heldout_days` (frozen last-25% boundary) deliberately **not** recomputed — see amendment log for why. |
| `analysis/edge-matrix/day-inventory-2026-07-23-summary.md` | **AMENDED** — short dated note pointing at this report |
| `analysis/edge-matrix/OPRA-BACKFILL-REPORT.md` | **NEW** — this report |

No commits made. `backtest/data/` stays gitignored (not committed) per instructions.

## What's left, if ever wanted

- Extending before 2025-01-02 needs the SPY/VIX 5m master extended first — different tool, different mission.
- The 2026-06-15 SPY-bars anomaly (OPRA present, SPY 5m absent) is unrelated to this mission and was left as-is; flagged here for visibility only.
