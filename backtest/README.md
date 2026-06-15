# Backtest — Project Gamma

> Historical replay of the heartbeat decision tree against real SPY 5-minute bars.
> Validates whether the playbook setups are real edge or storytelling on n=3.

**Status:** Built 2026-05-07. Scope: BEARISH_REJECTION_RIDE_THE_RIBBON only (the one CONFIRMED setup).

---

## Why this exists

Real-trade sample: **n=3**. Statistical inference on n=3 is storytelling.

This tool replays the heartbeat's filter checklist against 60 days of historical 5-min bars,
simulates bracket-order fills, and outputs trade rows in the same schema as `journal/trades.csv`.

**What it answers:**
- Real hit rate on a meaningful n (~30-150 candidate triggers over 60 days)
- Whether vol-baseline-1.3x / ribbon-spread-30c / VIX-17.20-17.30 / HTF-alignment thresholds are real or overfit
- Performance by `iv_regime` and `tod_bucket` with statistically meaningful sample
- Drawdown the live-deployment threshold actually faces

**What it does NOT do:**
- Run on a daily ritual. This is a one-shot tool, run on demand.
- Replace paper trading. Approximated option pricing differs from real fills.
- Modify any production state. Output goes to `analysis/backtests/` only.

---

## Quick start

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Fingerprint the Saty Pivot Ribbon periods (one-time, populates lib/ribbon_config.json)
python tools/fingerprint_ribbon.py

# Fetch 60 days of SPY + VIX 5-min data via yfinance
python tools/fetch_data.py --start 2026-03-01 --end 2026-05-06

# Run validation against the 3 known historical trades
pytest tests/test_e2e_known_trades.py -v

# Run the full backtest
python run.py --start 2026-03-01 --end 2026-05-06
```

Results land in `analysis/backtests/{from}_{to}/`:
- `trades.csv` — trades.csv-compatible per-trade rows
- `decisions.csv` — per-bar filter scores
- `summary.md` — hit rate, expectancy, drawdown, by_iv_regime, by_tod_bucket

---

## Data source

**Primary:** `yfinance` Python package — fetches SPY + VIX 5-min bars for the last ~60 days.
Free, no API key, reputable (Yahoo backs many tools).

**Fallback:** drop manually-downloaded CSVs into `data/` with schema:
```
timestamp_et,open,high,low,close,volume
2026-05-06T09:35:00-04:00,729.45,729.97,729.35,729.78,80653
```

**Future upgrade path (not built):** Polygon.io paid tier for >60-day history and tick-level option chain.
The current setup is sufficient for the n=30-150 trigger sample needed to validate filter thresholds.

---

## Engine architecture

```
backtest/
├── README.md (this file)
├── requirements.txt
├── data/                          # CSV input (you drop here, fetch_data.py populates)
│   ├── spy_5m_{from}_{to}.csv
│   └── vix_5m_{from}_{to}.csv
├── fixtures/                      # Test fixtures (3 known trades' chart data)
│   ├── spy_2026-04-29.csv
│   ├── spy_2026-05-01.csv
│   └── spy_2026-05-04.csv
├── lib/
│   ├── ribbon.py                  # Saty Pivot Ribbon (Fast/Pivot/Slow + Conviction)
│   ├── filters.py                 # 10 bearish + 11 bullish filters
│   ├── pricing.py                 # Black-Scholes for ATM 0DTE option premium
│   ├── simulator.py               # Bracket-order fill simulation (TP1/runner/stops/time)
│   ├── archetypes.py              # Similarity scoring vs canonical examples
│   └── ribbon_config.json         # Detected periods (from fingerprint_ribbon.py)
├── tools/
│   ├── fingerprint_ribbon.py      # Detects Saty Pivot Ribbon periods from live values
│   └── fetch_data.py              # yfinance pull → CSV in data/
├── tests/                         # TDD — must pass before trusting any output
│   ├── test_ribbon.py
│   ├── test_filters.py
│   ├── test_pricing.py
│   ├── test_simulator.py
│   └── test_e2e_known_trades.py   # Reproduce 4/29, 5/1, 5/4 within tolerance
└── run.py                         # Orchestrator
```

---

## Validation gate

**Before trusting any 60-day stats, the engine must:**

| Test | Pass criteria |
|---|---|
| Reproduce 4/29 entry | Fire BEARISH_REJECTION at 10:25:51 ±1 bar |
| Reproduce 5/4 entry | Fire BEARISH_REJECTION at 10:27:50 ±1 bar |
| Reject 5/1 anticipation | DO NOT fire at 13:09 (anticipation entry — wrong) |
| Capture 5/1 real trigger | Fire at 13:36 (real trendline rejection) |
| P&L tolerance | Each trade's simulated P&L within ±20% of actual ($342, $470, $730) |

If any of these fail, the engine has a bug. We fix before drawing conclusions.

---

## Pricing model — what we model and what we don't

**Modeled:**
- ATM 0DTE option premium via Black-Scholes
- IV proxied as `VIX/100`
- Time to expiry as fractional days remaining until 16:00 ET
- Strike = round(SPY, $1)
- Delta computed at entry; tracked across bars

**NOT modeled:**
- Bid-ask spread (we use mid)
- Theta acceleration in last 30 min (BS underestimates this — be conservative)
- Greeks beyond delta + theta (vega and gamma effects in fast moves)
- Real fill slippage

**Implication:** simulated P&L will be optimistic vs real fills by ~5-15%. The summary.md
flags this. For directional-edge questions ("does the setup work?"), this is faithful enough.
For production accuracy, you need historical option chain data which requires CBOE DataShop or similar.

---

## Conservative simulation rules

- If a 5-min bar's range touches both TP1 premium and stop premium: assume **stop fills first**.
- No look-ahead bias: filters at bar N can only see bars 1..N-1 closed.
- Ribbon EMAs computed only on closed bars (no intra-bar peek).
- Trigger fires only on bar-close events, never mid-bar.
- 15:50 ET time stop hard.
