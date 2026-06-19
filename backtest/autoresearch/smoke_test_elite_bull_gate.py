"""Quick smoke test: verify deployed BLOCK_ELITE_BULL_VIX15_17.5 gate
matches A/B scorecard numbers when run from params.json."""
import sys
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

# Load deployed params (production)
params = json.loads((ROOT / "automation/state/params.json").read_text())

PROD = dict(
    use_real_fills=True,
    premium_stop_pct_bear=params.get("premium_stop_pct_bear", -0.10),
    premium_stop_pct_bull=params.get("premium_stop_pct", -0.08),
    tp1_qty_fraction=params.get("tp1_qty_fraction", 0.667),
    runner_target_premium_pct=params.get("runner_max_premium_pct", 2.50),
    time_stop_minutes_before_close=params.get("time_stop_minutes_before_close", 20),
    midday_trendline_gate=params.get("midday_trendline_gate", True),
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=params.get("per_trade_risk_cap_pct", 0.30),
    block_level_rejection=params.get("block_level_rejection", False),
    block_elite_bull=params.get("block_elite_bull", False),
    block_elite_bull_vix_low=params.get("block_elite_bull_vix_low", 0.0),
    block_elite_bull_vix_high=params.get("block_elite_bull_vix_high", 999.0),
)

if __name__ == "__main__":
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print(f"  block_elite_bull={PROD['block_elite_bull']}, "
          f"vix_low={PROD['block_elite_bull_vix_low']}, "
          f"vix_high={PROD['block_elite_bull_vix_high']}")
    assert PROD['block_elite_bull'] is True, "block_elite_bull not in params!"
    assert PROD['block_elite_bull_vix_low'] == 15.0, f"vix_low mismatch: {PROD['block_elite_bull_vix_low']}"
    assert PROD['block_elite_bull_vix_high'] == 17.5, f"vix_high mismatch: {PROD['block_elite_bull_vix_high']}"

    print("Running OOS with production params...")
    oos = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **PROD)
    oos_pnl = sum(t.dollar_pnl for t in oos.trades)
    oos_n   = len(oos.trades)
    oos_skips = len([d for d in oos.decisions if d.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"])

    print(f"\n  OOS (production params): n={oos_n}, pnl={oos_pnl:+,.0f}")
    print(f"  OOS SKIP_ELITE_BULL events: {oos_skips}")

    # Expected from A/B scorecard (CAND row): n=22, pnl=+3,509
    assert oos_n == 22, f"UNEXPECTED OOS n={oos_n}, expected 22"
    assert abs(oos_pnl - 3509) < 50, f"UNEXPECTED OOS pnl={oos_pnl}, expected ~3509"

    print(f"\n  SMOKE TEST PASSED: OOS n={oos_n} pnl={oos_pnl:+,.0f} matches A/B scorecard.")
    print(f"  Gate active in production. Block: ELITE+level_reclaim when 15 <= VIX < 17.5")
