# HANDOFF 3 — Next session continuation (post 2026-06-15 fixes)

**Paste this whole file as the first message of a new Claude chat in this project.**
Read top to bottom before doing anything. Do NOT re-do work from HANDOFF-2.

---

## State as of 2026-06-15 evening

Four fixes shipped (see `PROGRESS-2026-06-15.md` for details):

| Fix | Status | Notes |
|---|---|---|
| FIX 5a — G6b code gate | ✅ SHIPPED | `automation/scripts/pre_order_gate.py`. 9/9 tests pass. |
| FIX 2 — Broker stop-loss | ✅ SHIPPED (prompt only) | Stop formula explicit in both heartbeats. Needs first live-trade verification. |
| FIX 4 — EOD reconciliation | ✅ SHIPPED | EOD-flatten now queries Alpaca fills. 2026-06-15 trade partially journaled. |
| FIX 1 — API key isolation | ✅ WIRED | Scripts ready. **J needs to create the key and write to `.heartbeat-api-key`.** |

---

## J action items (before next trading day)

### 1. Create isolated heartbeat API key (HIGHEST PRIORITY — prevents tomorrow's blind window)
```
console.anthropic.com → API Keys → Create new → copy the key
Then write it to: C:\Users\jackw\Desktop\42\automation\state\.heartbeat-api-key
```
One-liner in PowerShell (replace with actual key):
```powershell
"sk-ant-api03-XXXX" | Out-File -FilePath "C:\Users\jackw\Desktop\42\automation\state\.heartbeat-api-key" -Encoding utf8 -NoNewline
```
Cost: ~$5–10/day. Without this, interactive Claude sessions continue to starve the heartbeat.

### 2. Runner P&L reconciliation for 2026-06-15 ✅ DONE (2026-06-15 evening session)
Runner closed at **$2.45** @ 15:45 ET (Alpaca fill order e173a355-90b3-41ab-825c-77a9ea369a8e). P&L = +$78.
trades.csv runner row updated. Total Bold day P&L: TP1 +$474 + runner +$78 = **+$552** (+49% on $1,122 account).

### 3. Run git on Windows (once — gets rollback safety net live)
```
cd C:\Users\jackw\Desktop\42
setup\setup-git.ps1
```
Then push to GitHub. Until this runs, there's no rollback if a file gets corrupted.

### 4. Confirm FIX 2 (broker stop-loss) on first paper trade
After next entry: check the order's bracket in Alpaca — `stop_loss` should NOT be null. If it's still null, the Alpaca MCP schema may reject stop_loss for option brackets → escalate to next session's fix queue.

---

## Open deferred items (needs J direction, do NOT act without explicit go-ahead)

### OP-16 strategy gap
Engine captures little of J's anchor edge under real fills. The edge-floor gate (`edge_capture >= 771`) isn't discriminating well. See `DEEP-REVIEW-2026-06-14.md §OP-16`. This is a strategy call — needs J to define what the next 20 live trades should look like before tuning.

### v15.3 parity for grinders
Currently `run.py` and grinders don't load `params.json` as their base — they use engine defaults. This means all offline backtests run the "no-gate" v15 (53 trades) not the real v15.3 (16 trades). Changing this would shift the entire research baseline. Wait for J's explicit go-ahead.

### Bold ribbon-conviction gate
The gym flagged (2026-06-01 STATUS.md): Bold account is still v15.2 (no ribbon-conviction gate), Safe is v15.3. Kitchen has a backtest queued (`task 24cbff45`). When the cook result arrives, session can ratify — but don't act until J confirms he wants Bold on v15.3.

---

## What to do next session (autonomous path if J is away)

Priority order:

1. **Runner reconciliation (step 2 above):** pull Alpaca fills and complete the 2026-06-15 trades.csv runner row. Takes ~5 min.

2. **Kitchen steering:** Read `automation/state/kitchen-status.json` + last review in `analysis/kitchen-review/`. Steer the kitchen: enqueue any high-value tasks missing from the queue. Bold ribbon-conviction backtest result may have arrived — review it.

3. **Strategy research — J-edge deep dive:** the 4/29, 5/01, 5/04 wins are all morning (10:25 ET) BEARISH_REJECTION ribbon-flip-at-level. The `bearish_rejection_morning_watcher.py` was built but has 0/3 live J observations. Queue more OOS validation with real fills — does this watcher's edge hold in May/June?

4. **EOD summary for 2026-06-15:** Analyst persona can now grade the day properly since trades.csv is populated. Run: `claude --agent analyst "grade 2026-06-15: safe account flat, bold +$474 TP1 + runner UNKNOWN. Score the trade vs 10 rules, flag the sizing violation."` after J confirms runner exit price.

5. **Build the runner-reconcile tool:** rather than manual Alpaca queries, write a small Python script `automation/scripts/reconcile_runner.py` that reads `journal/trades.csv` for rows with `exit_px=UNKNOWN`, queries Alpaca fills for those dates, and completes the rows. This makes FIX 4's reconciliation work end-to-end without manual intervention.

---

## Environment notes (from L78, still applies)

- Git runs on Windows only (`setup/setup-git.ps1`). Don't try `git` from a Linux sandbox session.
- Sandbox Python = 3.10; Windows Python = 3.13. Validate in `/tmp` if in Linux, run authoritative tests on Windows.
- `NEVER run heavy interactive Claude work during 09:30–15:55 ET` — starves the heartbeat rate-limit pool. After-hours only.

---

## Key file locations (quick reference)

| What | Where |
|---|---|
| Pre-order gate (code-enforced G6b) | `automation/scripts/pre_order_gate.py` |
| Heartbeat (safe) | `automation/prompts/heartbeat.md` |
| Heartbeat (bold/aggressive) | `automation/prompts/aggressive/heartbeat.md` |
| EOD flatten (safe) | `automation/prompts/eod-flatten.md` |
| EOD flatten (bold) | `automation/prompts/aggressive/eod-flatten.md` |
| Graduated guard tests | `backtest/tests/test_graduated_guards.py` |
| Progress log | `PROGRESS-2026-06-15.md` |
| Params (safe) | `automation/state/params.json` |
| Params (bold) | `automation/state/aggressive/params.json` |
| Isolated API key (create this) | `automation/state/.heartbeat-api-key` |
| Trades log | `journal/trades.csv` |
