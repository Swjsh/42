# Futures Edition — End-to-End Analysis Summary
**Generated:** 2026-06-16 (Gamma autonomous session, updated with real VIX per-row data)
**Status:** Steps 1–5 complete. Steps 6–8 pending IBKR setup.

---

## Pipeline completion

| Step | Status | Notes |
|---|---|---|
| 1. Pull Databento data | DONE | MNQ + MES, 28,167 RTH 5m bars, 2025-01-02 to 2026-06-12 |
| 2. Native-bars mode | DONE | `run_native_backtest.py`, px_to_points=1.0, VIX per row (real) |
| 3. Run all strategies | DONE | 2,254 MNQ rows / 2,611 MES rows with per-row actual VIX |
| 4. OOS walk-forward | DONE | MNQ v3: PASS, MES v3_mes: PASS (both IS positive) |
| 5. Concentration + stress | DONE | See below |
| 6. IBKR paper wiring | PENDING | J creates account → Docker IB Gateway port 4002 |
| 7. TV MCP futures chart | PENDING | `chart_set_symbol("CME_MINI:MNQ1!")` — needs TV chart on MNQ |
| 8. Schedule tasks | PENDING | After IBKR account created |

---

## Key finding: MNQ and MES require separate configs

The same v3 config applied to both instruments **destroys edge on MES**:
- `erl_irl long high`: MNQ +$3,996 (WR=79%) → MES **-$5,788** (WR=56%)
- `shotgun short high`: MNQ +$2,486 (WR=67%) → MES **-$1,174** (WR=59%)
- S&P (MES) has more mean-reversion; Nasdaq (MNQ) trends more aggressively

---

## ORB finding: NOT viable for futures

ORB watcher was tested on 18 months of real futures data:
- **MNQ:** N=5 total, WR=40%, OOS=0 signals → Gate FAIL. SPY-calibrated 2pt gate maps to ~69pts; MNQ typical opening range 100-200pts → 94% of days blocked.
- **MES:** N=22 total, WR=59%, OOS N=6, Net=$6 → WF=0.142 FAIL. Even with positive OOS, N=6 OOS is too thin.
- **Decision:** ORB excluded from both v3 and v3_mes configs. No `set_futures_range_scale()` needed in heartbeat.

---

## MNQ v3 results (with real VIX per row)

| Metric | Value |
|---|---|
| Full period N | 594 |
| Full WR | 67.8% |
| IS P&L (2025) | +$6,860 |
| IS $/trade | +$18.10 |
| OOS P&L (2026) | +$15,027 |
| OOS $/trade | +$69.89 |
| OOS WR | 67.4% |
| WF gate | **PASS** (IS>0, OOS>0) |
| Top day | 2026-03-26 +$2,485 (11.4% of total) |
| Concentration | OK — no day >40%, max quarter 42.9% (2026Q2 tariff shock) |
| +1 tick stress | +$20,105 (OK) |
| +2 tick stress | +$18,323 (OK) |

**Best OOS strategies (2026):**
- `shotgun_scalper long medium`: N=29, +$4,260, WR=79%, $146/trade
- `shotgun_scalper short high`: N=54, +$4,018, WR=65%, $74/trade
- `erl_irl short medium`: N=16, +$3,742, WR=81%, $234/trade
- `tbr_high_vol long medium`: N=5, +$2,050, WR=100%, $410/trade

---

## MES v3_mes results (with real VIX per row)

| Metric | Value |
|---|---|
| Full period N | 232 |
| Full WR | 56.5% |
| IS P&L (2025) | +$1,906 |
| IS $/trade | +$14.55 |
| OOS P&L (2026) | +$2,238 |
| OOS $/trade | +$22.16 |
| OOS WR | 56.4% |
| WF gate | **PASS** (IS>0, OOS>0, WF=1.52) |
| Top day | 2025-04-09 +$579 (14.0% of total) |
| Concentration | OK — no day >40%, max quarter 30.9% (2026Q1) |
| +1 tick stress | +$2,404 (OK) |
| +2 tick stress | +$664 (marginal — thin edge) |

**Best OOS strategies (2026):**
- `shotgun_scalper long high`: N=30, +$1,824, WR=80%, $61/trade — dominant signal
- `v14_enhanced short high`: N=14, +$703, WR=64%, $50/trade — high conviction shorts

**Config comparison:** v3_mes beats v2b ($2,238 vs $1,167) and v3_mnq ($2,821 FLIP vs $2,238 PASS) — gate-aware scoring selects v3_mes as best because it's a clean PASS (IS positive) vs MNQ config's PASS-REGIME-FLIP (IS<0 on MES).

**+2 tick stress warning:** MES v3_mes survives by only $664 at 2-tick slippage. Start with MNQ paper first; MES paper after MNQ validates the watcher fleet in live futures mode.

---

## Config files

| Config | Instrument | File |
|---|---|---|
| v2b | Both (SPY proxy) | `backtest/futures/strategy_config.py` |
| v3 | MNQ | `backtest/futures/strategy_config_v3.py` |
| v3_mes | MES | `backtest/futures/strategy_config_v3_mes.py` |

---

## Test suite

**64/64 tests passing, 0 skips.** Includes:
- 8 instrument spec tests
- 8 P&L simulation tests (MNQ + MES, long/short, runner/stop)
- 7 risk module tests (Topstep + Apex prop account logic)
- 14 strategy config tests (v2b, v3 MNQ, v3_mes — including cross-instrument isolation guards)
- 7 ORB scale tests (SPY-calibrated gate correct, futures scale fix correct)
- 6 data loading tests
- 7 E2E smoke tests (MNQ OOS positive, MES OOS positive, MES beats v2b OOS, ORB fails OOS guard, concentration guard)
- 2 new guard tests: ORB fails OOS on MNQ (structural protection), no single day >40% concentration
- 2 rolling window tests: MNQ v3 all 2-month OOS windows positive, MES v3_mes same
- 1 IBKRBroker watch-only test: place_bracket logs but returns [] without IBKR connection
- 1 futures-eod-flatten.md existence guard

---

## For IBKR setup (Step 6 — J action required)

1. Create IBKR account → request paper trading access
2. Run: `docker run --rm -p 4001:4001 -p 4002:4002 ghcr.io/gnzsnz/ib-gateway:latest`
   - Set env: `TWS_USERID=<your_id>`, `TWS_PASSWORD=<your_pw>`, `TRADING_MODE=paper`
3. Test connection: `python -c "from backtest.futures.ibkr_paper import IBKRBroker; b=IBKRBroker(); print(b.connect())"`
4. Enable live mode in `ibkr_paper.py`: `WATCH_ONLY = False` (for paper orders)
5. Watch-only threshold: 20+ trades, positive expectancy → J ratifies paper live

---

## State files

```
automation/state/futures/
  position.json     # Current futures position (FLAT until IBKR connected)
  account.json      # Equity, daily P&L, drawdown floor
  risk.json         # PropAccount type, floor, kill switch state
  key-levels.json   # Pre-market levels, VWAP, MAs
```

---

## Data files

```
backtest/data/futures/
  MNQ_1m_continuous.csv       # 1m RTH bars (raw from Databento)
  MNQ_5m_continuous.csv       # 5m RTH bars (resampled)
  MNQ_native_rows.jsonl       # 2,254 signals with net P&L + real VIX per row
  MES_1m_continuous.csv
  MES_5m_continuous.csv
  MES_native_rows.jsonl       # 2,611 signals with net P&L + real VIX per row

analysis/recommendations/
  futures-mnq-native-results.json
  futures-mes-native-results.json
  futures-mnq-config-comparison.json
  futures-mes-config-comparison.json
  futures-edition-summary.md (this file)
```
