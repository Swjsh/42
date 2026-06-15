# Skill: backtest-compare

Run the current strategy against ALL historical days in `backtest/data/`. Output a P&L-per-day table. Flag every day that regressed >$50 vs the prior baseline. Do NOT declare improvement unless every day is flat-or-better.

---

## When to invoke

- After ANY change to `backtest/lib/`, `backtest/autoresearch/config.py`, or `automation/state/params.json`
- Before ratifying a new rule version
- When J asks "did this change hurt anything?"

---

## Steps

1. **Run the comparison script:**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python tools\compare.py
```

2. **Interpret the output:**
   - Table columns: Date | Current P&L | Baseline P&L | Delta | Status
   - `REGRESSED` = that day is worse by >$50 — the change broke something
   - `improved`  = that day is better by >$50
   - `—`         = within ±$50, flat

3. **Read the VERDICT line at the bottom — that is the canonical answer:**
   - `REGRESSION DETECTED` → Do NOT declare improvement. Find what broke it and fix it.
   - `IMPROVEMENT` → Every day is flat-or-better. Safe to advance the baseline.
   - `NEUTRAL` → No significant change. Baseline unchanged.

4. **If the run produced IMPROVEMENT and the change should be kept**, advance the baseline:

```powershell
python tools\compare.py --save
```

   This backs up the old baseline and freezes the current run as the new reference.

---

## Baseline file

Stored at: `analysis/backtests/baselines/current.json`

First-ever run creates the baseline automatically. Subsequent runs always compare against it.

To compare against a specific historical baseline:

```powershell
python tools\compare.py --baseline analysis\backtests\baselines\current.2026-05-10_120000.bak.json
```

---

## Rules this enforces

- OP 20: Non-theatre validation. Every change must show full per-day evidence.
- OP 17: First-try shipping discipline. Regressions block the change, not "we'll fix it later".
- Principle 16: J-edge is primary. A day that regressed = engine failing J on that session.

---

## When the baseline doesn't exist yet

The script prints a table of current P&L per day and saves it as the baseline. Run again after a change to begin comparing.

---

## Exit codes

- `0` = IMPROVEMENT or NEUTRAL (no regressions)
- `1` = REGRESSION detected (change broke at least one day by >$50)

Use in hooks: if `compare.py` exits 1, the change is blocked.
