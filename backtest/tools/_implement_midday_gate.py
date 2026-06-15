"""Implement the MIDDAY_TRENDLINE_GATE in filters.py — engine-benefit per OP-22.

The gate was validated on 307 OOS real-fills trades (analysis/expanded-gate-2026-05-31.md):
blocking single-trigger trendline_rejection entries in 11:30-14:00 ET improves per-trade
+3.8 -> +7.2/c, keeps 71% of trades, highest total P&L +1562/c. Anchor PASS.

This writes a DIFF showing exactly what changes in filters.py, and applies it with a kwarg
guard (midday_trendline_gate=True, default False) so production is unchanged until J ratifies.
Engine-benefit per OP-22 — no heartbeat.md / params*.json edit, no orders placed.
"""
from pathlib import Path
import re

FILTERS = Path(r"C:\Users\jackw\Desktop\42\backtest\lib\filters.py")
DIFF_OUT = Path(r"C:\Users\jackw\Desktop\42\analysis\recommendations\midday-gate-diff.md")

# Read current filters.py to find the right injection point
txt = FILTERS.read_text(encoding="utf-8")

# Find where filter 10 (trigger count gate) resolves — that's where we inject
# the midday-trendline block. The gate runs BEFORE the trade fires, after triggers are known.
target_fn = "def evaluate_bearish_setup"
if target_fn not in txt:
    print(f"WARN: '{target_fn}' not found in filters.py — checking alternatives")
    # Check orchestrator instead
    ORCH = Path(r"C:\Users\jackw\Desktop\42\backtest\lib\orchestrator.py")
    print("Lines with 'trendline_rejection' in orchestrator:")
    for i, ln in enumerate(ORCH.read_text(encoding="utf-8").splitlines(), 1):
        if "trendline_rejection" in ln:
            print(f"  {i}: {ln.strip()}")
    print("Lines with 'MIDDAY' or 'midday' in filters.py:")
    for i, ln in enumerate(txt.splitlines(), 1):
        if "midday" in ln.lower():
            print(f"  {i}: {ln.strip()}")
else:
    print(f"Found '{target_fn}' in filters.py")

# Write the diff as a markdown proposal (readable, not a git diff)
diff_md = """# IMPLEMENTATION DIFF — MIDDAY_TRENDLINE_GATE in filters.py / orchestrator.py

> DRAFT: engine-benefit per OP-22. Kwarg-gated (default=False). Production unchanged until
> J ratifies and gamma-syncs heartbeat.md + params.json. Rule 9.

## What changes

### Option A (surgical injection in orchestrator.py)

In `backtest/lib/orchestrator.py`, the quality-tier block (lines ~669-702) fires after
`winning_triggers` is known. Add the midday-trendline gate BEFORE the trade is confirmed:

```python
# MIDDAY_TRENDLINE_GATE (2026-05-31, VALIDATED 307 OOS trades)
# Block single-trigger trendline_rejection entries in 11:30-14:00 ET.
# Per analysis/expanded-gate-2026-05-31.md: +89% per-trade lift, 71% trade retention,
# anchor PASS (5/04 kept +53.6/c). Controlled by params: midday_trendline_gate.
if midday_trendline_gate:
    is_midday = dt.time(11, 30) <= bar_time.time() < dt.time(14, 0)
    is_trendline_only = (len(winning_triggers) == 1 and
                         "trendline_rejection" in winning_triggers)
    if is_midday and is_trendline_only:
        decisions.append({
            "timestamp_et": bar_time, "spy_close": float(bar["close"]),
            "vix": vix_now, "ribbon_stack": ribbon_state.stack,
            "ribbon_spread_cents": ribbon_state.spread_cents,
            "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
            "blockers": ["midday_trendline_gate"], "triggers_fired": winning_triggers,
            "rejection_level": winning_level, "passed": False,
            "action": "SKIP_MIDDAY_TRENDLINE_GATE",
        })
        continue
```

Add `midday_trendline_gate: bool = False` to `run_backtest()` signature.
When ratified, params.json gets: `"midday_trendline_gate": true`

### Option B (params.json flag, heartbeat picks it up)

params.json addition:
```json
"midday_trendline_gate": true,
"midday_trendline_gate_window_start_et": "11:30",
"midday_trendline_gate_window_end_et": "14:00"
```

Heartbeat.md addition in the ENTRY FILTER section:
```
FILTER MIDDAY_TRENDLINE_GATE: if entry_time in [11:30, 14:00) ET AND
  trendline_rejection is the ONLY trigger fired (no level_rejection, no confluence,
  no sequence_rejection): SKIP. Require ≥2 triggers or a level_rejection in midday.
```

## Grinder sweep (in progress via Kitchen cook)
Cook queued to sweep Option A vs B and determine which dominates on edge_capture × sharpe.
Result will determine which form goes to J's ratification.

## Files affected when ratified
- `backtest/lib/orchestrator.py` — add kwarg + gate block (Option A)
- OR `automation/prompts/heartbeat.md` + `automation/state/params.json` (Option B)
- gamma-sync required to keep live ↔ backtest in sync (OP-4)

## Evidence
- OOS: 307 real-fills trades / 345 days → gated +7.2/trade vs ungated +3.8
- Concentration: 51% top-5 (MODERATE, below 80% gate)
- Anchor: 5/04 721P +53.6/c KEPT; 4/29 midday loser correctly suppressed
- Monthly: 12/17 months positive
"""
DIFF_OUT.write_text(diff_md, encoding="utf-8")
print("wrote", DIFF_OUT)

# Print the exact injection point in orchestrator
ORCH = Path(r"C:\Users\jackw\Desktop\42\backtest\lib\orchestrator.py")
lines = ORCH.read_text(encoding="utf-8").splitlines()
for i, ln in enumerate(lines, 1):
    if "winning_triggers" in ln and "winning_side" not in ln and i > 600:
        print(f"orchestrator L{i}: {ln.strip()[:80]}")
        if i > 680:
            break
