# Skill: heartbeat-tick-audit

Verify the heartbeat read the correct CLOSED 5m bar (not the in-progress one) for every tick on a given day. Quantify how many decisions today would have differed under correct closed-bar reading.

> Per `markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md` + `docs/R4-HEARTBEAT-MISALIGNMENT-2026-05-14.md`. R1 closed-bar fix shipped in heartbeat.md v15.1 — this skill verifies the fix held day-over-day.

---

## When to invoke

- Daily, automatically — already wired into `backtest/autoresearch/eod_deep/main.py` Stage 4a.4 (Gamma_EodDeepDive at 16:05 ET runs it without prompting)
- Manually when J questions a specific tick's decision
- Manually when investigating a "weird" trade entry/exit timing
- After ANY change to `automation/prompts/heartbeat.md` — verify the change didn't reintroduce the in-progress bug
- When tomorrow morning's eod-deep JSON shows `misaligned_critical_count > 0` — investigate per-tick CSV

---

## Steps

1. **Run the audit on the target date:**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.heartbeat_tick_audit --date YYYY-MM-DD
```

Replace `YYYY-MM-DD` with the date to audit (must have heartbeat-{date}.log + spy_5m_*.csv covering it).

2. **Read the headline output:**

```
=== Heartbeat Tick Audit — 2026-05-14 ===
Headline: 5 of 46 live-trading ticks (11%) were MISALIGNED-CRITICAL on 2026-05-14
Counts: {'ALIGNED': 9, 'MISALIGNED-BENIGN': 32, 'MISALIGNED-CRITICAL': 5, 'STALE_PAUSED': 26, 'NO_DATA': 27, 'NO_BAR': 0}
```

3. **Interpret the verdict:**

| MISALIGNED-CRITICAL count | Verdict |
|---------------------------|---------|
| **0** | ✅ R1 closed-bar fix HELD — heartbeat correctly reads closed bars |
| **1-2** | 🟡 Partial — open the per-tick CSV at `automation/state/heartbeat-tick-audit-{date}.csv`, find the critical tick(s), check if the action was a real entry or a transient HOLD |
| **3+** | 🔴 R1 may not be working — heartbeat may still read in-progress bars. Investigate immediately + check `automation/prompts/heartbeat.md` lines 200 + 214 still have `count=3 + bar_close_et <= now_et` filter |

4. **Read the human-readable report:** `docs/HEARTBEAT-TICK-AUDIT-{date}.md` — has the per-tick CSV preview + critical ticks table + R1 verification verdict.

5. **If CRITICAL count > 0 and you want to know which ticks:**

```powershell
# Filter the CSV for critical ticks only
Import-Csv "automation\state\heartbeat-tick-audit-YYYY-MM-DD.csv" | Where-Object { $_.classification -eq "MISALIGNED-CRITICAL" } | Format-Table tick_id, fire_at, decision, claimed_spy, last_closed_close, divergence_dollars
```

---

## Output files (per date)

| File | What |
|------|------|
| `automation/state/heartbeat-tick-audit-{date}.csv` | Per-tick row with classification + divergence + bar values |
| `automation/state/heartbeat-tick-audit-{date}.json` | Summary dict with counts + headline + first 3 critical ticks (machine-readable) |
| `docs/HEARTBEAT-TICK-AUDIT-{date}.md` | Human-readable report with R1 verdict |

---

## Caveats

1. CSV is yfinance-sourced (per OP-13 dataset). yfinance 5m bars may diverge from TradingView's IBKR feed by 1-3 cents on individual bars (consolidated vs single-venue). ALIGNED tolerance is $0.05 to absorb this.
2. STALE_PAUSED ticks are post-kill-switch — system was already locked out of trading, so a stale cached SPY value can't change behavior. They count separately so the "live trading" denominator stays clean.
3. CRITICAL is a heuristic — flags WRONG bar + decision-changing action. Doesn't prove the alternate decision; flags risk.

---

## Cross-references

- **Audit tool source:** `backtest/autoresearch/heartbeat_tick_audit.py`
- **R1 fix shipped in:** `automation/prompts/heartbeat.md` (RULE_VERSION v15.1)
- **Original audit doc:** `markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`
- **Bug discovery doc:** `docs/R4-HEARTBEAT-MISALIGNMENT-2026-05-14.md`
- **CLAUDE.md OP-25 lesson absorbed:** "TradingView `data_get_ohlcv` returns the LIVE IN-PROGRESS bar at index [-1]" (2026-05-14 evening entry)
