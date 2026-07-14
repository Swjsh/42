# DATA-PROVENANCE — backtest/data feed strata

> Living doc. Which data source produced which rows of the cached bar files, and the
> rules that keep new rows provenance-consistent. Born from the **premarket-volume
> incident (2026-07-14)**; append new strata/incidents here, don't fork dated copies.

## Why this matters

`backtest/data/*.csv` looks homogeneous but is a **patchwork of feeds** with different
volume semantics. Volume-based work (RVOL, volume-confirmation gates, premarket tape
reads) that spans a feed seam compares apples to oranges. Price (OHLC) is near-identical
across these feeds; **volume is not**.

## Feed strata — spy_5m canonical chain (`spy_5m_2026-05-19_*.csv`)

| Rows | Source | Premarket vol | RTH vol scale | Notes |
|---|---|---|---|---|
| 2026-05-19 .. 2026-05-29 (seed) | **Alpaca SIP** | ✅ real (66 bars/day) | consolidated (SIP) | Seed also carried post-market rows to 19:55 |
| 2026-06-01 .. 2026-07-14 **RTH only** | **yfinance** (Yahoo consolidated) | — | ~7% ABOVE Alpaca SIP (06-10: 51.7M vs 48.3M) | Bounded stratum: ends 2026-07-14 |
| 2026-06-01 .. 2026-07-14 **premarket** | **Alpaca SIP** (repaired 2026-07-14) | ✅ real | consolidated (SIP) | Replaced in place; RTH rows untouched (verified value-identical) |
| 2026-07-15 onward | **Alpaca SIP** (full session) | ✅ real | consolidated (SIP) | `append_today.py` SPY path switched off yfinance |

## Other files

| File(s) | Source | Volume caveat |
|---|---|---|
| `spy_5m_2025-*` masters (built by `extend_data_v2.py`) | **Alpaca IEX** | 🚨 IEX volume ≈ 2-4% of consolidated. NEVER mix with SIP/Yahoo volume in one calc. Premarket window starts 09:00 ET (13:00Z), not 04:00. |
| `spy_5m_2026-05-08_*` chain (retired May chain) | yfinance appends | Premarket volume = 0 for sessions ≥ 2026-05-13. NOT repaired (superseded; repair tool works on it if ever needed). |
| Intermediate `spy_5m_2026-05-19_<06-01..07-10>.csv` snapshots | seed + yfinance | Premarket volume = 0 for sessions ≥ 06-01. NOT repaired — superseded daily snapshots; consumers auto-discover the latest end-date file. |
| `vix_5m_*` | yfinance | VIX is an index — volume is legitimately absent. Unaffected. |
| `data/highres/SPY_1m_*` | Alpaca **IEX** | Same IEX volume caveat. |
| `data/options*` | Alpaca OPRA | Separate pipeline, unaffected. |

## The incident (2026-07-14) — summary

- **Symptom:** every 5m premarket bar (04:00–09:25 ET) had `volume=0` for all 29 sessions
  2026-06-01..2026-07-13 in `spy_5m_2026-05-19_2026-07-13.csv`; 09:15–09:25 bars missing
  entirely (63 bars/session instead of 66).
- **Root cause:** `append_today.py` fetched SPY from **yfinance**, whose extended-hours
  intraday bars carry no volume and drop those 3 bars. The appender had done this since
  its **first fire (2026-05-13)** — the "2026-06-01 onset" was a provenance seam, not a
  behavior change: rows ≤05-29 came from the Alpaca-SIP seed, rows ≥06-01 from appends.
- **Proof of seed provenance:** Alpaca SIP re-fetch of 2026-05-27 matches the seed bar-for-bar
  (premarket vol 1,196,584; 08:30 bar 27,319). IEX same day: 6 bars / 2,711 shares — useless.
- **Fix (shipped 2026-07-14 evening):**
  - `backtest/tools/alpaca_bars.py` — SIP fetch (04:00–16:00 ET, DST-correct, 403-proof
    clamp for the Basic-plan 15-min delay, `sip_aged_at()` age gate).
  - `append_today.py` SPY path → Alpaca SIP; waits ≤25 min for the session to age
    (EOD task fires 16:00:33 ET; full session aged 16:16 ET; backtest venv is reaper-exempt);
    way-too-early runs NOOP instead of appending a partial day. yfinance remains a loud,
    ledger-flagged fallback (`source` field in `data-versions.jsonl`).
  - `backtest/tools/repair_premarket_volume.py` — replaced the dead premarket rows in the
    two newest chain files with SIP bars; RTH rows verified value-identical; originals in
    `backtest/data/_backup_premarket_zero/`; ledger rows `action=premarket_repair` carry
    old/new hashes.
  - Guards: `test_premarket_volume_alive_in_latest_chain` +
    `test_append_today_spy_uses_alpaca_sip` in `backtest/tests/test_graduated_guards.py`.
- **Side effect fixed:** a midday manual append used to write a partial day the next-day
  window would never re-fetch; the age gate now NOOPs those runs.

## Rules

1. **Canonical chain appends = Alpaca SIP only.** Never IEX for anything volume-bearing;
   never yfinance for extended hours.
2. **Disclose the stratum** when any volume calc spans 2026-05-29/06-01 or 2026-07-14/07-15
   RTH seams (~7% Yahoo-vs-SIP level shift), or touches the IEX masters.
3. **New bar producers register here** (file pattern, feed, window, volume semantics)
   before their output is consumed.
