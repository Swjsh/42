# Time-stop band measurement -- 2026-09-01

Measures `prereg-time-stop-broker-sweep-2026-09-01` (time_stop_et 15:40 -> 15:20).
Source: `analysis/trades-enriched.jsonl` (391 rows) + `backtest/data/spy_5m_2026-05-19_2026-09-01.csv` + live Alpaca 1m option bars.

## VERDICT: SHIP

[15:20,15:40] band carries 0.00% of post-2026-08-11 gross winner dollars (< 5% ship line)

## 1. Band census

- [15:20,15:40] exits: n=3, P&L=$-52.0, share of lifetime gross winner $=0.010148, share of post-08-11 gross winner $=0.0
- [15:25,15:40] strict exits: n=2, P&L=$218.0, share of lifetime gross winner $=0.010148, share of post-08-11 gross winner $=0.0
- lifetime gross winner $=22960.0 (n=391); post-08-11 gross winner $=11424.0 (n=156)

## 2. Give-up: positions still open at 15:20 ET (moving the stop earlier)

- n still open at 15:20: 16
- n MEASURED (1m OPRA bar found at/before 15:20): 16
- n UNVERIFIED (no bar): 0
- total give-up $ (measured rows only): -294.0

## 3. Sweep exposure: positions open through 15:30 ET

- n open through 15:30: 13
- classification counts: {"OTM": 8, "ITM": 3, "NEAR_ATM": 2}
- n ITM or near-ATM (the broker-sweep exposure set): 5

Full row-level detail: `analysis/recommendations/time-stop-band-2026-09-01.json`.
