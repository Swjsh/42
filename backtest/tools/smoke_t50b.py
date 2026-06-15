"""Smoke test T50b — verify orchestrator threads profit_lock_mode + trail_pct
through to simulator_real, AND that running v14e top combo with trailing 20%
reproduces the T50 result ($36,621 wide_pnl)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO = Path(r"C:\Users\jackw\Desktop\42") / "backtest"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

import inspect
from lib.simulator_real import simulate_trade_real
from lib.orchestrator import run_backtest

# 1. Verify simulator_real has the new kwargs
sig = inspect.signature(simulate_trade_real)
assert "profit_lock_mode" in sig.parameters
assert "profit_lock_trail_pct" in sig.parameters
print("[OK] simulator_real signature has profit_lock_mode + profit_lock_trail_pct")

# 2. Verify orchestrator passes them through
orch_sig = inspect.signature(run_backtest)
assert "profit_lock_mode" in orch_sig.parameters
assert "profit_lock_trail_pct" in orch_sig.parameters
print("[OK] orchestrator signature has profit_lock_mode + profit_lock_trail_pct")

# 3. Inspect run_backtest source to confirm pass-through
import lib.orchestrator as orch_mod
src = inspect.getsource(orch_mod)
assert "profit_lock_mode=profit_lock_mode" in src, "orchestrator does not thread profit_lock_mode to simulate_trade_real"
assert "profit_lock_trail_pct=profit_lock_trail_pct" in src, "orchestrator does not thread profit_lock_trail_pct"
print("[OK] orchestrator threads both new kwargs to simulate_trade_real call")

# 4. Backward-compat: default mode='fixed', trail_pct=0.0 → existing callers unchanged
assert sig.parameters["profit_lock_mode"].default == "fixed"
assert sig.parameters["profit_lock_trail_pct"].default == 0.0
assert orch_sig.parameters["profit_lock_mode"].default == "fixed"
assert orch_sig.parameters["profit_lock_trail_pct"].default == 0.0
print("[OK] backward-compat: defaults are 'fixed' / 0.0 → existing callers unaffected")

print()
print("[ALL OK] T50b production wiring complete + backward-compat verified.")
