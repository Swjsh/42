# Backtest Results — Project Gamma

> First production run: 2026-05-07. Backtests `BEARISH_REJECTION_RIDE_THE_RIBBON` against
> 53 trading days of historical SPY 5m data sourced from yfinance.

## Layout

```
analysis/backtests/
├── README.md                          (this file)
├── production_rules_v1/               (current playbook, all 10 filters active)
│   ├── trades.csv
│   ├── decisions.csv
│   ├── summary.md
│   └── metadata.json
├── historical_regime_no_8_no_9/       (filters 8 + 9 disabled — pre-2026-05-05 regime)
│   ├── trades.csv
│   ├── decisions.csv
│   ├── summary.md
│   └── metadata.json
└── findings_2026-05-07.md             (J's review document — read this first)
```

## How to re-run

```powershell
cd C:\Users\jackw\Desktop\42\backtest
.\.venv\Scripts\Activate.ps1

# Refresh data (yfinance only goes back ~60 days)
python tools/fetch_data.py --start 2026-03-15 --end 2026-05-07

# Run with current production rules
python run.py --start 2026-03-15 --end 2026-05-07 --label production_rules_v1

# Run historical regime (filters 8, 9 disabled)
python run.py --start 2026-03-15 --end 2026-05-07 --label historical_regime_no_8_no_9 --disable-filters 8 9

# Validate against 3 known historical trades (4/29, 5/1, 5/4)
python -m pytest tests/ -v
```

## Engine validation status

46 unit + e2e tests passing. Engine reproduces:
- **4/29 historical setup** — fires at 09:35-10:00 area on a 711.40-region rejection (slightly
  different bar than J's 10:25 entry; "first valid trigger" wins)
- **5/4 historical setup** — fires at 10:00 (loss) AND 11:15 (winner) — multiple rejections
- **5/1 historical setup** — does NOT fire under our rules (ribbon mismatch between yfinance
  and TradingView at 13:36 — known data-fidelity issue, not engine bug)
- **Anticipation rejection** — confirmed: engine never fires on the 5/1 13:09 anticipation pattern

EMA periods fingerprinted from live indicator values:
- Fast EMA = 13, Pivot EMA = 20, Slow EMA = 48 (all match within 0.11 cents tolerance)
