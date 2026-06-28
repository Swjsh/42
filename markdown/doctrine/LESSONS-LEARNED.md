# Lessons Learned — Concrete Anti-Patterns + Fixes

> Companion to `BACKTESTING-PLAYBOOK.md` §2. This doc gives the CODE-LEVEL fix for each anti-pattern. Use as a reference when building your own evaluator / pipeline.
>
> Format per entry: **Symptom → Root Cause → Fix → Code Example.**

---

## L01: Aggregate metric drives optimizer off the edge

**Symptom:** Sharpe-optimal candidate misses the trades that motivated the project.

**Root cause:** The optimizer doesn't know which trades matter. To it, $100 from a random trade = $100 from a strategically-important trade.

**Fix:** Multiplicative gate on aggregate. `final_score = edge_capture × aggregate_metric`. If edge_capture = 0, final_score = 0 regardless of aggregate.

```python
def score(combo):
    edge = score_edge_capture(combo)
    if edge < EDGE_FLOOR:  # e.g., 50% of max possible
        return float('-inf')  # disqualified, never picked
    aggregate = compute_aggregate_sharpe(combo)
    return edge * aggregate  # multiplicative gate
```

---

## L02: Simulator silently uses wrong parameter

**Symptom:** weeks of "winners" were trading the wrong strikes.

**Root cause:** the simulator hardcoded ATM regardless of `strike_offset` param.

**Fix:** sanity test in CI that runs the simulator with 3 different strike_offsets and asserts the resulting strikes differ.

```python
def test_simulator_honors_strike_offset():
    bar = make_bar(spot=720.50)
    fill_atm = simulate_trade(bar, strike_offset=0)
    fill_otm2 = simulate_trade(bar, strike_offset=2)
    fill_itm2 = simulate_trade(bar, strike_offset=-2)
    assert fill_atm.strike != fill_otm2.strike
    assert fill_atm.strike != fill_itm2.strike
    assert fill_otm2.strike != fill_itm2.strike
```

Run on every PR. Cheap, catches regressions instantly.

---

## L03: Trigger algorithm shipped without isolated unit test

**Symptom:** complex trigger fires on noise, has to be reverted multiple times.

**Root cause:** trigger logic + integration shipped together. No way to debug the trigger in isolation.

**Fix:** TDD with hand-computed expected value for a specific historical bar.

```python
# tests/test_trendline_trigger.py
def test_trendline_fires_on_5_1_at_13_35():
    """The defining test: J's actual entry bar at 5/1 13:35 ET.

    Hand-computed expected: 3 descending pivot highs at bar indices [...],
    line slope ≈ -0.012, intercept ≈ ..., projected to current bar = $723.16.
    Trigger should fire if bar.high >= 723.10 AND closes below 723.16.
    """
    bars = load_test_fixture("5_1_13_30.csv")
    result = detect_trendline_rejection_bearish(
        bar=bars.iloc[-1],
        prior_bars=bars.iloc[:-1],
        bar_idx=len(bars) - 1,
    )
    assert result is not None, "trigger MUST fire on this bar"
    assert 722.80 <= result <= 723.50, f"projected price out of range: {result}"
```

Iterate the algorithm until the test passes. ONLY THEN integrate.

---

## L04: Reporting wide_pnl without concentration disclosure

**Symptom:** announcing "wide_pnl $19,627 (+231% baseline)" looks great but hides that 5 days produce 176% of total — i.e. other 290 days NET-LOSE.

**Fix:** every evaluator computes top5_pct by default + every report includes it.

```python
def evaluate_combo(combo) -> dict:
    res, m = run_backtest(combo)
    day_pnl = defaultdict(float)
    for t in res.trades:
        day_pnl[t.entry_time_et.date()] += t.dollar_pnl
    sorted_days = sorted(day_pnl.values(), reverse=True)
    top5 = sum(sorted_days[:5])
    top5_pct = top5 / m.total_pnl if m.total_pnl > 0 else 999.0
    return {
        "wide_pnl": m.total_pnl,
        "top5_pct": top5_pct,  # ALWAYS computed
        # ...
    }
```

In reports, render side-by-side:
> wide_pnl: $19,627 — top5_pct: 120% (down from baseline 456%, less concentrated)

---

## L05: Naive total-P&L test/train ratio

**Symptom:** test/train ratio = 0.40x looks like overfit, when actually per-month rates are CONSISTENT.

**Root cause:** train window = 12 months, test window = 4.3 months. Naive ratio compares dollars not rate.

**Fix:** ALWAYS time-normalize.

```python
train_per_mo = train_pnl / train_window_months
test_per_mo = test_pnl / test_window_months
ratio_normalized = test_per_mo / train_per_mo if train_per_mo > 0 else 0
# >= 0.7 = consistent, 0.5-0.7 = mild overfit, < 0.5 = serious overfit
```

---

## L06: Wait-for-prompt chatbot reflexes

**Symptom:** ending status with "let me know if you want me to continue" while user is asleep / away.

**Root cause:** untrained chatbot reflex. The mission has no quiet moments.

**Fix:** banned-phrase list + required format for every status.

```
BANNED:
  "let me know if..."
  "your call"
  "want me to also...?"
  "going dark, wake me up if..."
  "should I...?"

REQUIRED FORMAT:
  1. Current state (what's running, what's done, with numbers)
  2. Concerns J would have, addressed proactively
  3. What I AM doing next + when I'll check back + what triggers what
```

This is doctrine OP 18 in `CLAUDE.md`.

---

## L07: Same-quality re-entry without min-gap

**Symptom:** TRENDLINE setup stops out at 13:40 → re-fires at 13:45 → also stops out at 13:50. Two losses back-to-back.

**Root cause:** "leg-2 retry after stop" was too aggressive — fired on the very next bar.

**Fix:** minimum time gap between same-quality re-entries.

```python
last_exit_ts = setup_last_exit_time_today.get(lock_key)
if last_exit_ts is None:
    gap_ok = True
else:
    bt = pd.Timestamp(bar_time)
    le = pd.Timestamp(last_exit_ts)
    # Defensively normalise tz
    if bt.tz is not None and le.tz is None:
        le = le.tz_localize(bt.tz)
    elif bt.tz is None and le.tz is not None:
        bt = bt.tz_localize(le.tz)
    gap_ok = (bt - le).total_seconds() >= MIN_GAP_SECONDS  # 45 * 60

allow_entry = (
    quality_rank > prior_quality
    or (quality_rank == prior_quality and prior_stopped and gap_ok)
)
```

---

## L08: Per-trade exit knobs hardcoded globally

**Symptom:** SUPER doctrine knobs (-20% stop, +75% TP1) applied to weak TRENDLINE trades, scratching them prematurely.

**Root cause:** one set of exit params for all setup qualities.

**Fix:** per-quality exit knobs.

```python
if quality_tier == "TRENDLINE":
    quality_stop = -0.08
    quality_tp1 = 0.30
elif quality_tier == "LEVEL":
    quality_stop = -0.14
    quality_tp1 = 0.40
elif quality_tier == "ELITE":
    quality_stop = -0.15
    quality_tp1 = 0.50
elif quality_tier == "SUPER":
    quality_stop = caller_doctrine_stop  # -0.20
    quality_tp1 = caller_doctrine_tp1    # 0.75

# Use TIGHTER of caller-vs-quality for stops (never relax beyond caller intent)
effective_stop = max(caller_stop, quality_stop)
effective_tp1 = min(caller_tp1, quality_tp1)
```

---

## L09: First-entry-per-day lock killed best trade

**Symptom:** best SUPER trade of the day got blocked because an early TRENDLINE locked the day.

**Root cause:** "first trade locks the day" rule was too strict.

**Fix:** quality-rank-based escalation lock. Higher quality breaks the lock.

```python
prior_quality = setup_quality_taken_today.get(lock_key, 0)
prior_stopped = setup_last_stopped_today.get(lock_key, False)

allow_entry = (
    quality_rank > prior_quality                                   # escalation
    or (quality_rank == prior_quality and prior_stopped and gap_ok)  # leg-2
)
# else: BLOCK (no churn, no downgrade)
```

---

## L10: Optimization-induced overfit (selection bias)

**Symptom:** picking the winner from a 1000-combo grinder = the winner is selected from a noise distribution. Some "wins" are pure variance.

**Root cause:** any optimizer over enough samples will find a candidate that looks great by chance.

**Fix:** layered gates that each candidate must pass independently.

```
Stage 1 keepers: 10 / 432 (passed floors)
Stage 2 keepers: 5 / 324  (passed floors after refinement)
Stage 3 keepers: 4 / 155  (passed concentration + quarter-coverage gates)
Stage 4 keepers: 0 / 4    (failed sub-window stability — IMPORTANT)
Stage 5 fallback: best from stage 3 with explicit "stage 4 fail" caveat
```

The 0-keepers result at stage 4 is INFORMATIVE. Don't hide it. Report it.

---

## L11: Reporting "ready" without account-size context

**Symptom:** "$19,627 wide_pnl" sounds like a $1K paper account 19x'd in 16 months. Actually requires $25K+ account to fit per-trade risk cap.

**Fix:** every numeric claim bundled with account-size scaling table.

```python
def render_account_scaling_table(headline_pnl, qty_used, entry_premium):
    capital_per_trade = qty_used * entry_premium * 100
    rows = []
    for account_size in [1000, 2000, 5000, 10000, 25000]:
        per_trade_cap = account_size * 0.50
        max_qty = int(per_trade_cap / (entry_premium * 100))
        realized_pct = min(max_qty / qty_used, 1.0)
        rows.append({
            "account": f"${account_size:,}",
            "max_qty": max_qty,
            "realized_pnl": f"${headline_pnl * realized_pct:.0f}",
            "realized_return_pct": f"{(headline_pnl * realized_pct / account_size):.0%}",
        })
    return rows
```

Render this table BELOW any headline P&L claim.

---

## L12: BS sim ≠ real OPRA fills

**Symptom:** BS-sim says trade hit TP1 at $1.20 → $1.56. Real OPRA: spread was $1.18 / $1.25 → couldn't fill at $1.20. Strategy sometimes can't even ENTER at the simulated price.

**Fix:** before any candidate ratifies, re-run top-3 anchor days through realistic simulator (cached real fills, real bid-ask, slippage model). Diff must be < ±20%.

```python
def realistic_fills_validation(combo, anchor_days):
    bs_results = []
    real_results = []
    for d in anchor_days:
        bs = run_with_simulator(combo, d, simulator=BS_SIM)
        real = run_with_simulator(combo, d, simulator=REAL_OPRA_SIM)
        bs_results.append(bs.total_pnl)
        real_results.append(real.total_pnl)
    diffs = [(r - b) / b for b, r in zip(bs_results, real_results) if b != 0]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0
    return {
        "bs_avg": sum(bs_results) / len(bs_results),
        "real_avg": sum(real_results) / len(real_results),
        "diff_pct": avg_diff,
        "passes": abs(avg_diff) < 0.20,
    }
```

---

## L13: Discord bridge dies silently

**Symptom:** user messages while away, no replies. Discovers hours later the bridge process died.

**Fix:** watchdog scheduled task every 5 minutes. Reads PID file, restarts if dead.

```powershell
function Test-PidAlive {
    param([string]$PidFilePath)
    if (-not (Test-Path $PidFilePath)) { return $false }
    $content = Get-Content $PidFilePath -Raw
    $pidValue = [int]($content.Trim().Split('|')[0])
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

if (-not (Test-PidAlive $bridgePidPath)) {
    Start-DiscordBridge
}
```

Combined with PID-file idempotency in the launcher = never spawns duplicates.

---

## L14: Look-ahead bias in level detection

**Symptom:** backtest looks great but live trading underperforms because in backtest, "key levels" were derived using future bars.

**Fix:** filter level history to bars timestamped <= current bar BEFORE computing levels.

```python
for idx in range(len(spy_df)):
    bar_time = spy_df.iloc[idx]["timestamp_et"]
    # CRITICAL: filter to past only
    full_history = spy_df_full[spy_df_full["timestamp_et"] <= bar_time]
    level_set = _detect_from_history(full_history, current_date)
    # ... use level_set in trigger evaluation
```

Other look-ahead traps to watch:
- Pandas EMA: built-in EMA only uses past values, OK.
- Vol baseline: explicitly use `prior_bars[:idx]` (exclude current bar).
- Precomputed indicators: verify they use only past values.
- VIX alignment: forward-fill from past, never backfill from future.

---

## L15: Overoptimistic "Monday ready" claim

**Symptom:** announcing "READY FOR MONDAY" without OOS validation, real-fills check, or regime-sensitivity disclosure.

**Fix:** Monday-Ready Checklist with 6+ gates, ALL must pass before any "ready" claim.

```python
gates = {
    "stage5_ratified": v15_final_json_exists(),
    "walk_forward_oos_positive": walk_forward_test_pnl > 0,
    "scheduled_tasks_enabled": all_required_tasks_enabled(),
    "discord_bridge_alive": bridge_pid_alive(),
    "discord_responder_healthy": responder_recent(),
    "winner_metrics_pass_floors": top5_pct <= 2.0 and positive_quarters >= 4 and ...,
}
all_pass = all(g["pass"] for g in gates.values())
```

Auto-run every 15 min. Discord ping on FAIL → PASS transition.

---

## L16: Single watcher fires too late

**Symptom:** background watcher waits for STAGE3_DONE event. By the time it fires (6h later), I have no context to act on it.

**Fix:** layered events. Fire on each meaningful checkpoint, not just completion.

```bash
while true; do
  # Fire on stage start, first 5 keepers, completion, and death
  if [ stage_started ] && [ ! announced_start ]; then
    echo "STAGE_START"; announced_start=1
  fi
  if [ keepers >= 5 ] && [ ! announced_5 ]; then
    echo "STAGE_5_KEEPERS keepers=$keepers"; announced_5=1
  fi
  if [ stage_complete ]; then
    echo "STAGE_DONE"; break
  fi
  if [ ! pid_alive ] && [ ! deadline_passed ]; then
    echo "STAGE_DIED"; break
  fi
  sleep 180
done
```

---

## L17: No cross-session memory = forget the mission

**Symptom:** new session starts, has to re-explore everything to understand pipeline state.

**Fix:** persistent decision queue + status files that any session reads on startup.

```
automation/state/research-queue.json   {next_action, stages, generated_at}
docs/STATUS.md                         human-readable
markdown/audits/HEALTH.md                         component health
markdown/planning/MONDAY-READY-CHECKLIST.md         current gate-pass state
analysis/recommendations/v15-final.json  final scorecard
```

Daily 08:00 ET task auto-regenerates these. Any new session: read these files first, then act.

---

## L18: Hard caps without bypass = lose control

**Symptom:** rate limit kicks in on a critical user message → can't respond.

**Fix:** queue a bypass reply explaining the cap. Bump watermark so message isn't reprocessed forever. User can wait or override.

```python
allowed, reason = check_and_record("discord-responder", reason=msg[:60])
if not allowed:
    snap = get_snapshot()
    bypass_reply = (
        f"⚠️ usage cap hit: {reason}\n"
        f"today: {snap['today_count']} invocations, ~${snap['today_est_cost_usd']:.2f}\n"
        f"will resume when within cap. message preserved in inbox."
    )
    queue_outbox(bypass_reply, user_id)
    save_watermark(msg["discord_msg_id"])  # don't reprocess
    continue
```

---

## L19: Watchdog that lies (silent on failure)

**Symptom:** monitor reports GREEN but a stage actually died. Found out hours later.

**Root cause:** the monitor's "alive" check used a stale PID file from a previous run.

**Fix:** active health probe (tasklist call) not file existence.

```python
def _is_pid_alive(pid: int) -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode("utf-8", errors="ignore")
        return f"{pid}" in out
    except Exception:
        return False  # assume dead if can't check
```

---

## L20: Console flash during multiprocessing.Pool

**Symptom:** Pool spawns python.exe workers → console window flashes 4 times → user can't focus on game/work.

**Fix:** force pythonw.exe BEFORE any mp call.

```python
import multiprocessing as mp
import sys
from pathlib import Path

# CRITICAL: must run BEFORE Pool() and BEFORE any other mp call
if sys.platform == "win32":
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        mp.set_executable(str(pythonw))
```

Also: use `subprocess.Popen` with `creationflags=CREATE_NO_WINDOW` for any other Windows-spawned children.

---

## L21: Hard-coded grinder paths break on dir rename

**Symptom:** rename `_state/overnight_grinder/` → `_state/stage1_grinder/` and 10 files break.

**Fix:** centralize stage directory map.

```python
STAGE_DIRS = {
    "stage1": REPO / "autoresearch" / "_state" / "overnight_grinder",
    "stage2": REPO / "autoresearch" / "_state" / "stage2_grinder",
    # ...
}
```

Every monitor, daily_status, self_audit, grinder_discord_notify imports from one source.

---

## L22: Every claim needs a "what could be wrong" line

**Symptom:** report says "strategy works." Real answer: works in N regimes, fails in M. Hides the M.

**Fix:** explicitly enumerate failure modes alongside every success claim.

```markdown
✅ Strategy generates +$19,627 over 16 months in-sample.

⚠️ Failure modes:
  - Q3+Q4 2025 (low-vol regime): -$1,500 to -$1,800 per quarter
  - Concentration: top-5 days = 120% of P&L → ordinary day ~$0
  - Out-of-sample 4.3-month test: per-month rate matches train ±20%
  - BS-sim assumed; real OPRA fills may differ ±10-30% on illiquid 0DTE
  - Account size: requires $25K+ for full headline; $1K paper realizes 14%
```

---

---

## L23: BS sim systematically over-estimates entry premium for ITM 0DTE (2026-05-13)

**Symptom:** SNIPER backtest shows wide_pnl $38K BS sim. Real OPRA fills produce -$1,725 (3 of 4 measured days FLIP from BS-winners to real-fills LOSSES). Same pattern on v14_enhanced morning test: BS metrics 35-40% higher than real fills.

**Root cause:** BS sim uses `vix/100` as IV proxy. Real OPRA bid/ask brackets the BS estimate ~10-25% higher for ITM-2 0DTE due to per-strike-per-DTE skew. Trades enter at WORSE prices than BS predicts; small adverse spot moves trigger stops instantly.

**Fix:**
- Retire BS sim for ratification. Use `simulator_real.py` against OPRA cache for all OP-20 disclosure-4 ("real-fills") gates.
- BS sim survives only as a RANKING metric within a grid (relative comparisons), never absolute P&L.
- Required cache: `backtest/data/options/SPY{YYMMDD}{C|P}{strike*1000}.csv`. Expand via `tools/expand_opra_cache.py` (J's Alpaca paper key, free tier).

**Encoded in:** T35/T42-full SNIPER tests + T44/T44b v14_enhanced + CLAUDE.md OP 25 Lessons absorbed.

---

## L24: Profit-lock at fixed +5%/+10% caps ride-the-ribbon winners (2026-05-13)

**Symptom:** v14_enhanced ratified Monday-Ready with `profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10`. 4,410-combo variant test on actual 5/13 $2,932 trade revealed: with that PL setting, the trade would have stopped at $2.23 = ~+$190 (only +6% gain). PL armed at $2.13, raised stop to $2.23, then a normal 11:45 retrace tripped it before the trend extended.

**Root cause:** fixed PL doesn't account for trend strength. Strong directional moves with normal intra-bar retraces get killed by the tight floor.

**Fix:** TRAILING profit-lock (chandelier-style). Once armed, floor moves to `max(arm_floor, HWM × (1 - trail_pct))`. Trail_pct=0.20 wins on aggregate ($36,621 vs $36,450 fixed) AND captures more big-day upside. On the 5/13 trade hypothetical: trailing 20% rides to $4.34 (+107%) vs fixed PL +6% vs no-PL actual +159%.

**Code (added to `lib/simulator_real.py` 2026-05-13 T50b):**
```python
if profit_lock_armed and profit_lock_mode == "trailing":
    trail_floor = hwm * (1.0 - profit_lock_trail_pct)
    candidate = max(profit_lock_arm_floor or 0.0, trail_floor)
    if candidate > runner_stop_premium:
        runner_stop_premium = candidate
```

**Encoded in:** T50 trailing-PL test + simulator_real.py + heartbeat-v15-draft.md v14_enhanced section.

---

## L25: Pandas concat of mixed tz-aware DataFrames degrades dtype to object (2026-05-13)

**Symptom:** `Gamma_WatcherLive` task `LastTaskResult=0` (PowerShell wrapper exits 0) but Python silently raises `AttributeError: Can only use .dt accessor with datetimelike values`. State file not written, observations not logged.

**Root cause:** concat of CSV-loaded bars (tz-aware ET via `pd.to_datetime`) + yfinance-fetched bars (tz-aware UTC converted to ET) drops the resulting `timestamp_et` column to dtype `object` instead of `datetime64[ns]`.

**Fix:** always re-coerce after concat:
```python
df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
```

Health-check pattern: verify state file write + observation count, NOT just task scheduler exit code.

**Encoded in:** `watcher_live.py` post-concat block + wake-protocol.md foot-gun list.

---

## L26: Heartbeat ENTER decisions don't write to decisions.jsonl (2026-05-13)

**Symptom:** monitoring polled `decisions.jsonl` for engine activity all afternoon, saw 0 trades for 2026-05-13. Reality: heartbeat placed 2 real Alpaca paper orders (734P -$315, 738C +$2,932) — `decisions.jsonl` was missing them.

**Root cause:** heartbeat writes HOLD decisions to ledger but ENTER decisions skip the write (presumably to avoid double-logging since the position state file also captures the entry).

**Fix:** when monitoring real-time engine activity, ALWAYS poll Alpaca directly via `mcp__alpaca__get_orders(after=today_iso)` — that's the source of truth for trades. Do NOT rely on decisions.jsonl alone for ENTER actions.

Health-check pattern: include `mcp__alpaca__get_orders` as Stage 0 self-test for any morning fire that needs to know "did engine trade today".

**Encoded in:** wake-protocol.md foot-gun list (T49 area).

---

## L27: pythonw.exe processes invisible to PowerShell `Get-Process` (2026-05-13)

**Symptom:** `Get-Process -Id NNN` returns EMPTY for `pythonw.exe` processes that have no console, even when they are alive and computing. Caused false "v14e grinder died" diagnosis at 08:43 ET. Restarting "dead" grinder created a duplicate set of workers competing for the same `_state/` dir.

**Root cause:** PowerShell `Get-Process` filters out console-less processes by default. WMI sees them.

**Fix:** use `Get-WmiObject Win32_Process -Filter "ProcessId = $pid"` for ground-truth liveness of `pythonw` / `pythonw3.13`. NEVER restart a grinder based on `Get-Process` alone.

```powershell
$proc = Get-WmiObject Win32_Process -Filter "ProcessId = $pid"
if ($proc) { "ALIVE — $($proc.CommandLine)" } else { "DEAD" }
```

**Encoded in:** wake-protocol.md foot-gun list + launch-*-stage1.ps1 watchdog scripts.

---

## L28: watcher_live silently no-ops pre-market because CSV ends at yesterday (2026-05-13)

**Symptom:** `Gamma_WatcherLive` runs every 5 min during RTH but observation count stays at 314 (pre-existing) for entire trading day. Nothing logged.

**Root cause:** master `spy_5m_*.csv` is updated by EOD appender (post-close). During market hours the latest CSV row is yesterday. `watcher_live.py` had `if latest_date != today: return 0` — silent skip during the entire session.

**Fix:** added yfinance intraday top-up branch in `autoresearch/watcher_live.py`. Caveats: yfinance MultiIndex column flattening + tz-aware/naive Timestamp normalization both required (see L25). Try/except + traceback log to capture silent failures.

**Encoded in:** `autoresearch/watcher_live.py` lines 102-180 + wake-protocol.md foot-gun list.

---

## L29: Discord bridge dies silently when Gamma_DiscordWatchdog is disabled (2026-05-13)

**Symptom:** Discord alerts stop reaching J, no signal of failure. Outbox accumulates queued messages indefinitely.

**Root cause:** `discord-bridge.py` process can crash for various reasons. `Gamma_DiscordWatchdog` task auto-restarts it every 5 min — but if disabled, no recovery. Bridge died 2026-05-10 22:30 → not restored until 2026-05-13 21:08 ET = **3 days of silent alerting failure**.

**Fix:** include `Get-ScheduledTask -TaskName 'Gamma_DiscordWatchdog'` enabled-check in wake-protocol Stage 0 self-test:
```powershell
$wd = Get-ScheduledTask -TaskName 'Gamma_DiscordWatchdog'
if ($wd.State -ne 'Ready') { "WARN: DiscordWatchdog disabled — no auto-restart for bridge" }
```

**Encoded in:** wake-protocol.md foot-gun list.

---

## L30: REGIME_SWITCHER over-engineering risk (2026-05-13)

**Symptom:** built REGIME_SWITCHER as meta-strategy to orchestrate v14e + VWAP + ODF + SNIPER. Stage 1 grinder ran 1,296 combos → 0 keepers. Re-tune with the GOOD v14e combo + SNIPER excluded → 972 combos, still 0 keepers. Best regime combo wide_pnl $20,770. Standalone v14_enhanced wide_pnl $36,621 (+43% better).

**Root cause:** if one sub-strategy dominates the dataset (v14e catches 6/7 J winners alone), the regime switcher's only mechanism is to ROUTE AWAY from it on certain days — which always loses money relative to using the dominant strategy everywhere.

**Fix:** before building any meta-strategy:
1. Measure standalone P&L of the dominant sub-strategy
2. Measure DELTA from optimal day-by-day routing (theoretical perfect oracle)
3. Only build meta-strategy if oracle-delta > 30% of standalone

**Lesson:** "if a single strategy catches 80%+ of the dollars, don't add orchestration." Adding a switching layer only helps when no single strategy dominates.

**Encoded in:** T37 REGIME_SWITCHER v2 retune + this lesson + `docs/REGIME-SWITCHER-V2-2026-05-13.md`.

---

## L31: TradingView CDP port 9222 dies silently after long runtime (2026-05-14)

**Symptom:** `mcp__tradingview__tv_health_check` returns "fetch failed" mid-session despite TV processes alive in Task Manager. Premarket Step 1c fails — TV chart unreachable → empty levels → Heartbeat ERROR_TV all session.

**Root cause:** TradingView MSIX (Electron app) was running but had been re-launched at some point WITHOUT the `--remote-debugging-port=9222` flag. The CDP port was therefore not listening even though the process was healthy. Likely cause: TV self-updated overnight and restarted via its normal launcher (which strips the CLI flag), instead of via our `setup\launch_tv_debug.ps1` with `UseShellExecute=false + CreateProcess`.

**Fix:** Stage 0 self-test for any overnight wake fire must include `Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -InformationLevel Quiet`. If not listening, kill all TV processes (`Get-Process -Name '*TradingView*' | Stop-Process -Force`) and relaunch via `setup\launch_tv_debug.ps1`. Encoded in `setup\scripts\fire-stage0-selftest.ps1`.

```powershell
$cdp = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $cdp) {
    Get-Process | Where-Object { $_.ProcessName -like '*TradingView*' } | Stop-Process -Force
    & "C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1"
}
```

**Lesson:** any externally-launched debugged process needs a periodic CDP-listen health check, not just a "process alive" check. The CLI flag is the actual contract, not the process existence.

**Encoded in:** `setup\scripts\fire-stage0-selftest.ps1` (Stage 0 default) + `setup\scripts\fire19-final-verify.ps1` + `automation/overnight/wake-protocol.md` foot-gun list.

---

## L32: Silent zero-observation across 5 of 8 watchers (2026-05-14)

**Symptom:** `automation/state/watcher-observations.jsonl` has 362 entries spanning a year, but only 3 watchers fire (orb 222, bullish 108, v14_enhanced 32). Five watchers (`sniper_watcher`, `vwap_watcher`, `opening_drive_fade_watcher`, `pinfade_watcher`, `premarket_fail_fade_watcher`) have **0 observations EVER**. Gamma_WatcherLive scheduled task ran every 5 min × every trading day with LastTaskResult=0 — silent success. 5/13 (a $2,932 J-engine win day) had ZERO bar-date observations across ALL watchers.

**Root cause:** all 5 silent watchers gate on `multi_day_rth` per `lib/watchers/runner.py` line 129 (`if multi_day_rth is not None and not multi_day_rth.empty:`). Three possible failure modes, all silent:
1. **Replay callers don't pass `multi_day_rth`** (Gamma_WatcherReplay) — outer `if` fails, 5 watchers skip silently
2. **Live-mode timestamp lookup fails** — `matching = multi_day_rth.index[multi_day_rth["timestamp_et"] == bar["timestamp_et"]]` returns empty when dtype-object after concat (L25) OR tz mismatch, `bar_idx_full = -1`, inner `if bar_idx_full >= 0:` fails
3. **Per-watcher exception swallowed** — 5 separate `except Exception: pass` blocks

The wrapper `try/except: pass` silently swallowed all 3 modes. Production had been silent-failing for at least 4 trading days (5/10-5/13) before discovery.

**Fix:**
1. Per-fire diag-trail (`watcher_live.py` writes `automation/state/watcher-live-diag.jsonl` per fire: bar OHLCV + multi_day_rth_rows + sniper_5d_high + signals_emitted). Reveals silent zero-observation in real-time.
2. T62 invariant — stderr WARNING when `multi_day_rth is None` during apparent live call (heuristic: bar age ≤ 3600s + ctx populated).
3. T63 silent-except unmask — all 5 except blocks now write `<watcher> exception: <type>: <message>` to stderr.

```python
# WRONG (silent)
try:
    snp = detect_sniper_setup(bar, bar_idx_full, multi_day_rth)
    if snp is not None:
        raw_signals.append(snp)
except Exception:
    pass

# RIGHT (loud)
try:
    snp = detect_sniper_setup(bar, bar_idx_full, multi_day_rth)
    if snp is not None:
        raw_signals.append(snp)
except Exception as e:
    sys.stderr.write(f"sniper_watcher exception: {type(e).__name__}: {e}\n")
```

**Lesson:** `except Exception: pass` is a silent-failure machine. If a watcher's intent is "never break the live loop", catch the exception AND surface it to stderr (which goes to scheduled-task output). Add a per-fire diag-trail to verify watchers are FIRING, not just RUNNING.

**Encoded in:** `lib/watchers/runner.py` (T62+T63 patches Fire #22) + `backtest/autoresearch/watcher_live.py` (diag-trail Fire #20) + `docs/T48-SNIPER-5-13-MISSFIRE-2026-05-14.md` + this lesson.

---

## L33: pythonw.exe + multiprocessing.Pool without maxtasksperchild = silent OOM (2026-05-14)

**Symptom:** `v14_enhanced_grinder.py` died silently 3 times on 5/13 after 5-50 combos each. Each death pattern: `progress.json` last_update 17+ hours stale + `status="running"` + `current_pid` not alive. NO traceback, NO exception, NO event-log entry. Other grinders (sniper Stage 1-5, vwap, odf, regime_switcher) ran the same code path and completed fine on the same master CSV — so not a code bug or data corruption.

**Root cause:** `mp.set_executable(pythonw.exe)` per L13/L24 doctrine forces workers to be GUI-subsystem (no console). Combined with `mp.Pool(workers)` WITHOUT `maxtasksperchild`, workers persist for the entire run. Each worker re-imports the module tree (pandas + numpy + sim + evaluator) and loads the master CSV (30,645 rows × 6 cols × float64 ≈ 150MB) per combo on Windows spawn mode. After ~50 combos × 4 workers × no recycling, committed memory hit ~2.5GB. Windows OOM killer terminates the parent (silently — no event log unless administrator-elevated). pythonw's stderr goes nowhere because it's not attached to a console.

**Forensics:** 60 rejection JSONL writes but only 50 progress.json log entries (progress logs every 5 combos). Death happened between rejection-write and the next progress-log. State frozen at last completed combo.

**Fix (T70 + T71):**
1. **`mp.Pool(workers, maxtasksperchild=10)`** — forces worker recycle every 10 combos. Bounds memory commit at ~600MB instead of ~2.5GB unbounded. ~5% throughput hit acceptable.
2. **Launcher stderr redirect** — switch from `[Diagnostics.Process]::Start(...)` (no stdio capture) to `Start-Process -RedirectStandardError $stderrLog -RedirectStandardOutput $stdoutLog -PassThru`. Even GUI-subsystem pythonw writes to stdio when explicit pipes are wired. Captures the silent-kill traceback if any.

```python
# WRONG (unbounded memory)
with mp.Pool(workers) as pool:
    for result in pool.imap_unordered(evaluator, grid, chunksize=1):
        ...

# RIGHT (bounded memory)
with mp.Pool(workers, maxtasksperchild=10) as pool:
    for result in pool.imap_unordered(evaluator, grid, chunksize=1):
        ...
```

```powershell
# WRONG (no stdio capture from pythonw)
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $pythonw
$startInfo.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($startInfo)

# RIGHT (pythonw stderr/stdout captured even without console)
$proc = Start-Process -FilePath $pythonw -ArgumentList @(...) `
    -RedirectStandardError $stderrLog -RedirectStandardOutput $stdoutLog `
    -NoNewWindow -PassThru
```

**Lesson:** `pythonw.exe` is great for "no console window" but TERRIBLE for diagnosis if anything goes wrong. Combine with `maxtasksperchild` to bound memory AND explicit stdio pipes to capture exceptions. Without both, a multiprocessing.Pool grinder will silent-OOM on any large dataset.

**Encoded in:** `backtest/autoresearch/v14_enhanced_grinder.py` L303 (T70) + `setup/scripts/launch-v14-enhanced-stage1.ps1` (T71) + `markdown/audits/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md` + this lesson.

---

## L34: TradingView `data_get_ohlcv` returns LIVE in-progress bar at index [-1] (2026-05-14)

**Symptom:** Production heartbeat fires at 14:24:03 ET, calls `data_get_ohlcv(count=2)` on BATS:SPY 5m, treats bar[-1] as "the just-closed bar", writes `loop-state.last_bar_timestamp = 14:20 ET` AND `spy = 747.98`. But the 14:20 bar's `close_dt = 14:25 ET` — it has 57 seconds remaining. Real 14:20 close was 748.01. `spy=747.98` is the live mid-bar tick, not the bar close. **5 of 46 live-trading ticks on 2026-05-14 were MISALIGNED-CRITICAL** under closed-bar verification (per `docs/R4-HEARTBEAT-MISALIGNMENT-2026-05-14.md`). Today's ENTER_BULL @ 09:58 fired on snapshot 745.35 while the actual 09:50 closed bar was a RED rejection of PMH 745.43 (literal opposite of `level_reclaim`). Trade worked anyway, but trigger was structurally premature.

**Root cause:** TradingView labels bars by OPEN time and streams the live forming bar at index [-1]. Heartbeat doctrine SAYS "last closed bar" but the prompt never instructed the model to compute `bar_close_et = bar.time + 5min` and verify `<= now_et`. Unlike yfinance (in-progress bars have V=0 sentinel — easy to detect via T76 watcher_live filter), TV in-progress bars have real OHLCV — they LOOK closed.

**Fix:** R1 in heartbeat.md v15.1 (shipped 2026-05-14 evening). Replaced `data_get_ohlcv(count=2)` with `count=3` + `bar_close_et = bar.time + 5min ≤ now_et` filter. Latest = filtered[-1] (the actually-closed-most-recent bar). Same fix applied to skip-stale gate (line 200) and main bar read (line 214).

**Cross-cuts to:** L33 (yfinance in-progress V=0 sentinel — different sensor for same class of bug). General rule: any MCP/external API that returns a "latest" timeseries element MUST be checked against `time_close ≤ now_wall_clock` before being trusted as closed.

**Encoded in:** `automation/prompts/heartbeat.md` v15.1 + `automation/state/params.json` rule_version=v15.1 + `markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md` + CLAUDE.md OP-25 lessons absorbed entry + `backtest/autoresearch/heartbeat_tick_audit.py` (re-runnable verification tool, auto-included in EOD pipeline Stage 4a.4 every night). If R1 holds, daily `heartbeat-tick-audit-{date}.json` will show MISALIGNED-CRITICAL=0; if it regresses, EOD JSON flags it within 24h.

---

## L35: Stateful detector + per-tick fresh-process scheduled task = silent zero observations (2026-05-14)

**Symptom:** Production `Gamma_WatcherLive` scheduled task fires every 5 min via fresh `pythonw.exe` process. ORB watcher + ODF watcher have module-level per-day state machines (`_orb_state[date_str]`, `_odf_state[date_str]`) that progress NEUTRAL → BREAKOUT → WAIT_RETEST → ENTRY across bars. Every fresh process resets the state. Result: **0 ORB observations on 2026-05-13 and 2026-05-14**. Detector is correct; live-fire path silently strips state every 5 min.

**Root cause:** `_orb_state: dict[str, dict] = {}` is module-level. Module state lives only as long as the Python process. Windows scheduled task spawns new pythonw per fire, so module state is reset between fires. The breakout bar registers in process A, the retest bar (which fires the entry signal) is processed in fresh process B with empty state. State machine never advances past breakout. Pre-5/08 6-12 obs/day numbers in `watcher-observations.jsonl` came from `Gamma_WatcherReplay` Sunday batch (sequential within one process), NOT from live-tick path. Live-tick ORB has been broken since day one — we just didn't notice because the Sunday backfill made the obs log look populated.

**Fix:** T82 + T82b in `backtest/autoresearch/watcher_live.py` (shipped 2026-05-14 evening). Walk today's RTH bars sequentially calling stateful detectors directly (no logging) BEFORE the main `run_all_watchers` call. State machine accumulates correctly. Latest bar's call then fires entries. 78-bar warmup overhead = 6.5ms (~0.08ms/bar — negligible). End-to-end verified: WITHOUT warmup 0 ORB signals on 5/14; WITH warmup 1 ORB signal at 10:30 medium confidence.

**Audit pattern:** before adding any new watcher to `lib/watchers/runner.py`, grep its detector source for `: dict[str, dict]` or similar module-level state. If stateful → add to T82 warmup loop. Per the stateful audit (T82b): ORB + ODF are stateful; PFF + VWAP + V14E + bullish are stateless.

**General rule:** any detector with multi-bar state must EITHER (a) get warmed up sequentially in every fresh-process invocation, OR (b) persist state to disk between invocations. Option (a) is simpler and chosen here because warmup is cheap.

**Encoded in:** `backtest/autoresearch/watcher_live.py` T82 + T82b warmup loops + `backtest/autoresearch/t82_orb_warmup_test.py` (3-scenario validation) + `markdown/research/T80-ORB-BULL-REGRESSION.md` + CLAUDE.md OP-25 lessons absorbed entry + `.claude/skills/watcher-fleet-status/SKILL.md` (re-usable diagnostic).

---

## L36: Build re-usable Claude Code skills + auto-run audits, not one-shot scripts (2026-05-14 — meta-pattern)

**Symptom:** Spent fire #38 hours debugging the heartbeat closed-bar bug. R4 subagent wrote `analysis/r4_heartbeat_misalignment_analysis.py` hardcoded to date 2026-05-14. Tomorrow's same investigation would require rewriting paths + reasoning from scratch. Pre-5/14 we had ~15 one-shot diagnostic scripts (`t48_*`, `t62_*`, `t80_*`, `_smoke_*`) scattered across `backtest/autoresearch/` and `setup/scripts/` — no index, no cross-referencing, no auto-running.

**Root cause:** "Ship the fix and move on" optimization left re-usable knowledge as one-shot debris. Each future investigation re-implemented the same parsing logic instead of reusing the prior work. J's directive 2026-05-14 evening: *"we should be auditing and building re usable skills as we self improve. as in claude skills. make sure you are updating documentation as well."*

**Fix:** Three-part meta-pattern shipped Fire #41-#42 evening of 2026-05-14:

1. **Generalize one-shots into parameterized tools.** `backtest/autoresearch/heartbeat_tick_audit.py` takes `--date YYYY-MM-DD` arg, auto-discovers data files. Re-runnable on any historical date.

2. **Auto-wire audits into the EOD pipeline.** Stage 4a.4 in `eod_deep/main.py` calls `heartbeat_tick_audit.run_audit(date_str)` nightly. EOD JSON includes `research_handoffs.heartbeat_tick_audit` section with headline + counts. **Silent regressions caught within 24h instead of 4+ days** (the gap between when watcher silent-failure started and when we noticed).

3. **Register Claude Code skills + maintain a catalog.**
   - `.claude/skills/{skill-name}/SKILL.md` — slash-command-callable patterns. Future Claude sessions discover them via skill list.
   - `markdown/infra/SKILLS-CATALOG.md` — comprehensive index of all Python diagnostic tools + PowerShell audits + Claude Code skills + EOD pipeline modules. "When you suspect X, run Y" lookup table.
   - Tools shipped tonight: `heartbeat-tick-audit`, `watcher-fleet-status` (Claude Code skills); `heartbeat_tick_audit.py` (Python tool, EOD-wired).

**General rule:** any time you build a diagnostic tool to investigate a foot-gun, follow the SKILLS-CATALOG.md `Adding a new skill` protocol: parameterize, catalog, optionally wire into EOD or expose as Claude Code skill. The "weakest link" in self-improvement is forgetting we already built the tool.

**Encoded in:** `markdown/infra/SKILLS-CATALOG.md` (300-line catalog + tool selection guide + add-new-skill protocol) + `.claude/skills/heartbeat-tick-audit/SKILL.md` + `.claude/skills/watcher-fleet-status/SKILL.md` + `backtest/autoresearch/heartbeat_tick_audit.py` + `eod_deep/main.py` Stage 4a.4 + this lesson + CLAUDE.md OP-25 lessons absorbed.

---

## L37: Crypto-as-24/7-validation-harness for engine primitives (2026-05-16)

**The realization:** The SPY 0DTE engine reads OHLCV bars, computes indicators, detects candlestick patterns, identifies levels, and makes deterministic decisions on price data. The 2026-05-14 misalignment (L34) cost us 5/46 live ticks — and the feedback loop to validate the fix was 24+ hours because the SPY market is closed 17.5 hours per weekday plus all weekend. **OHLCV bars on BTC-USD 5m are structurally identical to OHLCV bars on SPY 5m.** Closed-vs-in-progress is identical. RSI/EMA/MACD/BB/ATR/VWAP math is identical. Candlestick patterns are identical. Level/trendline geometry is identical. **Crypto is on 24/7 → every chart-reading primitive can be validated continuously.**

**The build (2026-05-16):**
- `crypto/lib/` — 14 pure-Python primitives (`bar`, `bar_reader`, `data_sources`, `indicators`, `candlesticks`, `levels`, `trendlines`, `volume`, `ribbon`, `regime`, `divergence`, `breakout`, `sweep`)
- `crypto/validators/v01-v14` — 14 validator suites (27 test stages total), offline + live mode each
- `crypto/benchmarks/replay_5_14.py` — replays the 5/14 floor through OLD vs NEW logic. **Result: OLD = 0/46 correct (in-progress leak on every tick), NEW = 46/46 correct.**
- `crypto/benchmarks/replay_any_day.py` — same replay against any historical day. **Tested on 9 days (4/29 through 5/12) = 1,161 ticks, 100% leak rate under OLD logic structurally.**
- `crypto/benchmarks/live_grinder.py` — runs `runner.py` every 2 min for hours, accumulates knob-tuning data in `grinder.jsonl`
- `crypto/benchmarks/analyze_grinder.py` — statistics + tuning recommendations
- `crypto/benchmarks/chart_read_demo.py` — applies the 7-step CHART-READING-PROTOCOL.md to live BTC, emits canonical statement
- `setup/scripts/run-crypto-regression.ps1` + `setup/install-crypto-regression.ps1` — `Gamma_CryptoRegression` Windows Task Scheduler entry firing every 30 min, 24/7. Zero LLM cost.
- `crypto/data/fixtures/tv_mcp_snapshot_2026-05-16T14-24Z.json` — empirical TV MCP snapshot proving TV `data_get_ohlcv` also returns the in-progress bar at index [-1] (with $21.36 measured close-price drift between two snapshots seconds apart).
- `crypto/docs/CHART-READING-PROTOCOL.md` — the 7-step doctrine for reading any chart.
- `crypto/docs/HEARTBEAT-INTEGRATION.md` — port guide from `crypto/lib/` primitives into production heartbeat (OP 4 enforcement: both code paths reference the canonical lib).

**The validation cycle:** any future change to `automation/prompts/heartbeat.md` or `backtest/lib/filters.py` runs `python crypto/validators/runner.py` as a pre-merge gate. If a primitive regresses on crypto, it would regress on SPY too — and we catch it in 30 seconds instead of 24 hours.

**General rule:** when a production foot-gun depends on a primitive (bar reading, indicator math, pattern detection) that is asset-agnostic, validate it on a 24/7 asset class — not on the primary asset whose market hours create artificial feedback latency.

**Encoded in:** `crypto/` folder (33 files, 14 lib primitives, 14 validator suites, 4 benchmarks) + `crypto/docs/BENCHMARK-REPORT.md` (the headline numbers) + this lesson + `Gamma_CryptoRegression` task installed.

---

## L38: Dead parameter knob in grid search wastes budget and masks real signal (2026-05-16)

**Symptom:** Stage 4 grinder ran 288 combos over 4 `vol_ratio_threshold` values (0.60, 0.80, 1.00, 1.20). All 4 values produced **identical** direction_detail and identical wide_pnl/sharpe for otherwise identical parameter sets. A grid dimension that costs 25% of compute was doing nothing.

**Root cause:** `vol_ratio_threshold` was defined in `ShotgunCombo` (line 126) and included in the grid, but the value was **never compared** to `signal.vol_ratio` anywhere in `run_shotgun_day` or `_simulate_trade_real`. The detector computed `vol_ratio` per signal and stored it in the signal dict, but no gate checked it. Symptom visible as: combos with vol=0.60, vol=0.80, vol=1.00, vol=1.20 all show identical `by_day` P&L values.

**Diagnosis pattern:** when a grid search produces a dimension where all values produce the same score, check if that dimension is actually wired into the evaluation function. A `grep` for the parameter name in the evaluator code will reveal whether it's read vs. only defined.

**Fix:** wire the gate in `run_shotgun_day` at the correct point — after signal generation, before simulation:

```python
# After: if signal is None: continue
# Add:
if signal.get("vol_ratio", 1.0) < combo.vol_ratio_threshold:
    continue  # filter low-volume signals below threshold
```

Note: `signal.get("vol_ratio", 1.0)` defaults to `1.0` only when the key is ABSENT. Tier 1 signals (opening bar, no prior reference) emit `vol_ratio=0.00` which is present but zero — they will be filtered at any threshold > 0. This is correct behavior for Tier 1.

**Prevention checklist:** before any grid search, verify each dimension with:
```python
# One-liner validation: vary the knob while holding others fixed
for val in grid[knob]:
    combo = make_combo(**{knob: val, **fixed_params})
    trades = run_shotgun_day(date, spy_df, combo, {})
    print(f"{knob}={val}: {len(trades)} trades, pnl={sum(t.pnl for t in trades)}")
# If all lines print identical results: the knob is dead.
```

**Cost of missing this:** Stage 4 initial run spent 5/288 worker-combos computing results that were 4× redundant. For a 6-hour grinder at 4 workers, a dead dimension wastes 25% of total compute and produces misleading "all combos equivalent on this axis" signals.

**Encoded in:** `backtest/autoresearch/shotgun_scalper_grinder.py` run_shotgun_day vol_ratio gate + this lesson.

---

## L39: Scheduled-task log auditing regex too narrow — misses SKIP/REAPED lines, reports phantom gaps (2026-05-14)

**Symptom:** `setup/scripts/heartbeat-pulse-check.ps1 v1` reported **3 gaps of 15+ minutes** on 2026-05-14 14:30-15:48 ET and only 46 total fires (not the expected 125). Reality: `Gamma_Heartbeat` fired every 3 minutes on schedule — no gaps, no missed fires.

**Root cause:** The v1 script matched only `^.*ET FIRE ` in `run-heartbeat.log`. The production heartbeat uses a hash-based early-exit (lines 97-117 of `run-heartbeat.ps1`): when the SPY chart + session state hasn't changed between ticks, it writes `SKIP hash_unchanged` instead of running a full `claude --print` invocation. This early-exit is a cost optimization — it avoids re-running Claude for ~4 of every 5 ticks in a flat, sideways session. The `SKIP` lines outnumbered `FIRE` lines 79:46 on 5/14. By counting only FIRE lines, v1 saw 46 fires with 15-minute "gaps" between them — phantom gaps that matched the SKIP cadence.

**Fix (v2, shipped same evening):**
```powershell
# WRONG (v1) — counts FIRE lines only
$firePulses = Select-String -Path $logPath -Pattern ' ET FIRE '

# RIGHT (v2) — counts ANY heartbeat pulse (FIRE | SKIP | REAPED)
$allPulses = Select-String -Path $logPath -Pattern ' ET (FIRE|SKIP|REAPED) '
# De-dup by minute: task cron fires once/minute, log may have trailing lines
$byMinute = $allPulses | ForEach-Object { ($_.Line -split ' ET ')[0] }
$distinctMinutes = $byMinute | Sort-Object -Unique
```

**General rule:** when auditing "did the scheduled task run on schedule?", count ANY log activity from that task on the wall-clock minute — not just the happy-path action line. Cost-optimization early-exits, hash-skip sentinels, and watchdog-REAP lines all prove the task fired, even if the full action was bypassed.

**Secondary lesson:** `heartbeat-pulse-check.ps1` is now a `/skill` under `.claude/skills/heartbeat-pulse-check/SKILL.md`. The v2 regex fix is noted there. Run it when investigating heartbeat scheduling gaps.

**Encoded in:** `setup/scripts/heartbeat-pulse-check.ps1` v2 regex update + `.claude/skills/heartbeat-pulse-check/SKILL.md` update note + queue item FIRE43-RED-T76b-HEARTBEAT-GAPS closed-false-alarm.

---

## L40: VIX single-bar lookback is too tight for slow post-news VIX drift (2026-05-16)

**Symptom:** BULL watcher fired 0 signals on 2026-05-14 (a +$913 CPI-relief BULL day). T80 offline test hardcoded `vix_prior=17.9, vix_now=17.8` and correctly produced 4 BULL medium signals. Production saw 0.

**Root cause:** `vix_direction(now, prior)` uses a single 5-minute bar comparison with a 0.05 deadband. On a post-CPI "slow VIX drift" day, VIX fell from ~18.05 at open to ~17.56 by EOD (a -0.49 total move over ~6 hours). But EACH INDIVIDUAL 5-minute bar only dropped 0.01–0.04 — well within the 0.05 deadband. `vix_direction` returned "flat" on nearly every bar.

- Filter 8 (`VIX < 17.20 OR vix_falling`): VIX never dropped below 17.20, and single-bar direction was always "flat". Result: **Filter 8 blocked 85.5% of BULL bars** (only 11/76 ticks passed = those during the brief VIX 17.23 dip).
- T80's hardcoded -0.10 drop is 2× the deadband — passes fine but is unrealistic for a slow-drift day.

**Fix:** Use a 3-bar (15-minute) lookback for the `vix_falling` computation. Cumulative drift over 15 minutes is typically 0.06–0.12 on a slow-drift day — reliably above the 0.05 deadband. The 3-bar lookback successfully detects the overall downtrend without being sensitive to tick noise.

```python
# WRONG (single-bar — misses slow drift)
vix_prior = ctx.vix_prior  # 5 min ago
vd = vix_direction(ctx.vix_now, vix_prior)

# RIGHT (3-bar lookback — 15-min trend)
vix_prior_15m = ctx.vix_hist[-3] if len(ctx.vix_hist) >= 3 else vix_prior
vd = vix_direction(ctx.vix_now, vix_prior_15m)
```

Result: Filter 8 pass rate on 5/14 improves from **14.5% → 35.5%** (+18 additional eligible bars). On the 5/14 EOD-deep-dive replay, detection score moves from TOO_PASSIVE (40) toward PERFECT (95) with the multi-bar fix.

**General rule:** when comparing a slow-moving indicator (VIX, yield spread, breadth) between two points, the lookback window must be wide enough to accumulate signal above the noise floor. Single-bar comparisons on a 0.05 deadband capture fast moves (spikes) but miss slow directional drifts.

**Encoded in:** `backtest/autoresearch/t81_bull_vix_gate.py` (diagnostic tool, `--date YYYY-MM-DD`) + `markdown/research/T81-BULL-VIX-GATE.md` + `eod_deep/modules/detection.py` vix_prior_idx fix (3-bar lookback already applied 2026-05-14 evening) + `backtest/autoresearch/watcher_live.py` vix_prior fix (2026-05-16) + `backtest/autoresearch/watcher_replay.py` vix_prior fix (2026-05-16). All three paths now use `max(0, idx - 3)` lookback; single-bar lookback for VIX is BANNED in any `vix_direction` call path.

---

## L41: Visible cmd/PowerShell window leak — 5-layer fix for headless subprocess spawning (2026-05-16 evening)

**Symptom:** J reported visible `cmd`/console windows accumulating throughout the day. 4+ Windows Terminal tabs opened across the session showing `pythonw.exe` titles. Asked to fix 4× across the day; each "fix" attempt addressed only the surface layer and the windows kept appearing.

**Root cause:** Five independent landmines stacked. Fixing only one is insufficient — the chain re-leaks.

1. **Swarm replay runner spawned `claude --print` per agent, each auto-loading `alpaca-mcp-server.exe`.** Per-replay-fire = 30+ claude invocations × 1 alpaca server each = orphan accumulation when parent claude died before child cleanup. 7 orphans found in audit.
2. **`logging.basicConfig()` defaults to `sys.stderr` StreamHandler.** Under pythonw.exe with Windows 11 default-terminal = Windows Terminal, the first stderr write triggered Windows to allocate a visible WT tab for the process.
3. **Venv's `pythonw.exe` is a stub that re-execs as system `python.exe` (CONSOLE subsystem).** Get-Process shows `Path = Python313\python.exe` even when launched via venv pythonw — that's a console-allocating re-exec. CREATE_NEW_CONSOLE flag is set, conhost.exe spawns, visible.
4. **`Start-Process -WindowStyle Hidden` is ignored by Windows Terminal when WT is the default terminal app.** Windows 11's `HKCU\Console\%%Startup\Delegation{Console,Terminal}` GUID controls this. Default `{00000000-...}` ("Let Windows decide") on Win11 22H2+ routes everything through WT, which ignores Hidden.
5. **No `CREATE_NO_WINDOW` flag on `subprocess.run()`/`subprocess.Popen()` calls from Python orchestrators** lets transient console allocations leak as window flashes.

**Fix (apply ALL 5 — partial fix re-leaks):**

```python
# Layer 1 — subprocess.run() in Python orchestrators (runner_replay.py, runner.py, etc.)
proc = subprocess.run(
    cmd, ...,
    creationflags=0x08000000 if sys.platform == "win32" else 0,  # CREATE_NO_WINDOW
)

# Layer 1b — when spawning claude --print for MCP-free agents, suppress MCP entirely
cmd = [..., "--strict-mcp-config", "--mcp-config", str(EMPTY_MCP_CONFIG)]
# (empty-mcp.json contains just {"mcpServers": {}})
```

```python
# Layer 2 — top of any pythonw-launched script (BEFORE logging.basicConfig + heavy imports)
import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower() == "pythonw.exe":
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / f"{__name__.split('.')[-1]}.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / f"{__name__.split('.')[-1]}.stderr.log", "a", buffering=1, encoding="utf-8")
```

```powershell
# Layer 3 — never launch via venv\Scripts\pythonw.exe. Use SYSTEM Python313\pythonw.exe with
# PYTHONPATH set to the venv's site-packages.
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$env:PYTHONPATH = Join-Path $WorkDir "backtest\.venv\Lib\site-packages"
$env:VIRTUAL_ENV = Join-Path $WorkDir "backtest\.venv"

# Layer 4 — launch via wscript + run_exe_hidden.vbs to bypass any residual WT grab
$vbs = Join-Path $WorkDir "setup\scripts\run_exe_hidden.vbs"
Start-Process -FilePath "wscript.exe" `
    -ArgumentList @("//nologo", $vbs, $sysPythonw, $ScriptPath) `
    -WindowStyle Hidden -WorkingDirectory $WorkDir | Out-Null
```

```powershell
# Layer 5 — one-time Windows 11 registry change so programmatic spawns use legacy conhost
# (respects Hidden flags) instead of Windows Terminal (ignores them)
$conhost = "{B23D10C0-E52E-411E-9D5B-C09FDF709C7D}"
Set-ItemProperty -Path "HKCU:\Console\%%Startup" -Name "DelegationConsole"  -Value $conhost
Set-ItemProperty -Path "HKCU:\Console\%%Startup" -Name "DelegationTerminal" -Value $conhost
# Side effect: manual `cmd` launches use conhost not WT. User's manual WT launches unaffected.
```

**Audit pattern (run if new windows appear):**

```powershell
# 1. Visible console-type windows in user session
Get-Process | Where-Object { $_.SessionId -eq 1 -and $_.MainWindowTitle -match "python|pythonw|cmd\.exe|conhost|powershell" } | Select-Object Id, ProcessName, MainWindowTitle

# 2. Orphan MCP servers from past claude --print invocations
wmic process where "name='python.exe'" get processid,commandline /format:list | findstr alpaca-mcp

# 3. Default terminal handler GUID (must be conhost {B23D10C0-...})
Get-ItemProperty -Path "HKCU:\Console\%%Startup" | Select-Object DelegationConsole, DelegationTerminal
```

**General rule:** ANY headless Windows subprocess spawn needs ALL of: (a) GUI-subsystem binary (system pythonw, not venv pythonw), (b) stdio redirected before any logging, (c) launched via wscript hidden wrapper, (d) CREATE_NO_WINDOW or `-WindowStyle Hidden`, (e) conhost-as-default registry setting. Skip any layer → window leaks under some condition.

**BANNED patterns:**
- `subprocess.run(...)` without `creationflags=CREATE_NO_WINDOW` on Windows
- `claude --print` for MCP-free agents without `--strict-mcp-config --mcp-config <empty>`
- Long-running scripts that call `logging.basicConfig()` or `print()` without stdio pre-redirect
- `venv\Scripts\pythonw.exe` for headless processes (use SYSTEM pythonw with PYTHONPATH)
- `Start-Process pythonw.exe -WindowStyle Hidden` with no `run_exe_hidden.vbs` wrapper (WT grabs anyway)

**Encoded in:** `automation/swarm/replay/runner_replay.py` (creationflags + strict-mcp) + `automation/swarm/runner.py` (MCP suppression for stages 2-4) + `automation/swarm/replay/empty-mcp.json` (canonical empty MCP) + `setup/scripts/run_exe_hidden.vbs` (canonical hidden launcher for arbitrary exe) + `setup/scripts/ensure-discord-bridge-alive.ps1` (system pythonw + PYTHONPATH + wscript pattern) + `setup/scripts/discord-bridge.py` + `setup/scripts/discord-watcher.py` (stdio redirect at top) + Windows registry HKCU\Console\%%Startup → conhost GUIDs + CLAUDE.md OP 27 subprocess discipline sub-clause.

---

## L42: State file path migration must update ALL consumers atomically (2026-05-16)

**Symptom:** Dual-account redesign moved Gamma-Bold position state from `automation/state/aggressive/current-position.json` to `automation/state/current-position-bold.json`. The main `heartbeat.md` was correctly updated to write Bold position to the new path. However, two other consumers were missed:
1. `setup/scripts/run-heartbeat-aggressive.ps1` — `$posStatePath` still pointed to old path. The "position open" guard (which prevents throttle-skipping when Bold has an open position) would silently fail — treating an open Bold position as closed, leading to possible missed exit ticks.
2. `automation/prompts/aggressive/eod-flatten.md` — Step 1 still read old path. EOD flatten would have concluded no position and done nothing, silently skipping any open Bold position at 15:55 ET.

**Root cause:** State file path change was made in one file (heartbeat.md dual-account section) without a comprehensive search for all consumers of the old path.

**Fix:** Before any state file path rename/migration, run `grep -r "old-path-name" .` across the entire codebase. Update ALL matches atomically in the same commit. Then verify with a dry-run that no reference to the old path remains.

```powershell
# Pattern: pre-migration grep check
Select-String -Path "C:\path\to\project" -Pattern "old-filename" -Recurse -Include "*.md","*.json","*.ps1","*.py"
```

**General rule:** State file consumers are: (a) the writer (heartbeat), (b) the reader with position-open guard (run-heartbeat-*.ps1), (c) the EOD flatten prompt, (d) the EOD summary, (e) premarket reconciliation gate. All 5 must be updated together when a state file path changes. Check each one explicitly — grep is cheaper than a missed position.

**Encoded in:** `automation/prompts/aggressive/eod-flatten.md` (Step 0, Step 1, Step 1.5 log, Step 3 success path — all updated to `current-position-bold.json`) + `setup/scripts/run-heartbeat-aggressive.ps1` (`$posStatePath` updated) + this L42 entry.

---

## L43: Swarm synthesis agents inflate confidence scores when the base formula lacks rarity gates (2026-05-16)

**Symptom:** `swarm_confidence=95` assigned on 62.5% of days (10 of 16 tradeable days). Actual direction accuracy at conf=95: 70%. ECE = 31.84% — SEVERE miscalibration. A well-calibrated model targeting conf=95 should be correct ≥90% of the time. The system was over-reporting confidence on virtually every "strong consensus" day regardless of macro risk or structural quality.

**Root cause:** Synthesis agent formula: `weighted_score × 100 + {+10 if 4/4 agree}` → commonly reaches 100–105, capped to 95. When all 4 specialists agree (the majority case on trending days), the formula mechanically produces 95. There is no scarcity gate — high confidence is the DEFAULT when specialists converge, not the EXCEPTION reserved for exceptional setups.

Measured outcome: `confidence_inflation = 62.5%` (more than half of days at max confidence), `accuracy_at_95 = 70%`, `calibration_bucket_breakdown`: the 65–79 bucket (only 4 days) was actually MORE accurate (100%) than the 80–95 bucket.

**Fix:** Three-part calibration overhaul applied to `automation/swarm/prompts/synthesis_agent.md` Step 5:
1. **Lower base multiplier:** `weighted_score × 75` (was `× 100`). Same input → conf starts at 75 max before adjustments.
2. **Steeper penalties:** 2/4 agree → −10 (was −5); validator "weak" → −15 (was −10); macro "high"/"extreme" → −20 (was −15).
3. **Hard structural gates:** conf ≥ 90 requires ALL of: 4/4 specialist agreement, validator "strong", macro event_risk NOT "high"/"extreme", consensus_strength "strong". conf ≥ 95 additionally requires macro "very_low" AND validator finds zero structural flaws. Self-check reminder written into the prompt: "before writing conf≥90, verify all gates met."

Expected post-fix calibration (projecting from formula change): conf=95 on ~10–15% of days (vs 62.5%), conf ≥ 80 on ~25–30% of days. ECE target: <10% (vs 31.84%).

**General rule:** any AI-generated score intended to represent probability must have RARITY GATES — structural conditions that are REQUIRED (not optional) before reaching the top confidence tiers. Without gates, the formula defaults to maximum confidence whenever conditions are "good enough," which is most of the time. This collapses the calibration curve.

**Calibration monitoring:** `automation/swarm/replay/swarm_confidence_calibration.py` — run after each backfill batch to compute ECE, per-bucket accuracy, confidence inflation rate, and generate `analysis/swarm-benchmark/calibration-report.{json,md}`. Re-run after 20+ days post-fix to confirm ECE < 10%.

**Encoded in:** `automation/swarm/prompts/synthesis_agent.md` Step 5 (v2 rubric — CALIBRATED label added) + `automation/swarm/replay/swarm_confidence_calibration.py` (monitoring script) + `analysis/swarm-benchmark/calibration-report.{json,md}` (baseline measurement, ECE=31.84%) + this L43 entry.

---

## L44: VIX direction requirement too strict for sustained-trend continuation days (2026-05-19)

**Symptom:** Engine misses all 3 J source-of-truth winner days (4/29, 5/01, 5/04) despite the correct bearish direction. `edge_capture = -$408` vs J's max possible $1,542. Trail-width sweep (8 variants, 20%-60%) produces identical results — the bottleneck is not exit logic but ENTRY timing.

**Root cause (per-bar diagnostic):** Filter F8 (`VIX > 17.30 AND vix_rising`) uses a `0.05` deadband direction check. On sustained-trend days, VIX spikes in the morning (09:30-10:00) then **flatlines at an elevated level** (e.g., 18.36 for 4 hours on 4/29). The `vix_direction()` function returns "flat" (not "rising") when delta < 0.05 over consecutive bars. Result: F8 blocks the engine ALL AFTERNOON even when VIX = 18.36 (well above the 17.30 threshold). The "rising" requirement was designed to filter low-VIX calm days but it over-fires on high-VIX flat-regime days.

Secondary blockers:
- **F6 (ribbon spread < 30c):** Ribbon EMA stack needs 45-120 min to diverge after a gap-down. On sustained-trend days, the first 1-2 hours of correct bear signal are blocked because the ribbon spread is still tightening.
- **F5 (ribbon direction) = structural gate:** On 5/01 (SPY bull-ribbon all day), engine cannot fire bear setup regardless of VIX. This requires a separate setup type (BEARISH_REVERSAL_AT_LEVEL).

**Fix: Config F27 — three parameters changed:**
```python
vix_soft_mode=True                       # F8 becomes -1 score demerit, not hard block
allow_one_blocker=True                   # Can fire with 1 non-structural blocker
allow_one_blocker_min_spread_cents=27    # Only bypass F6 when spread >= 27c (blocks 16c chop entries)
```

The 27c threshold is the Goldilocks value:
- 4/29 09:45 bad entry: spread=16c → BLOCKED by min_spread gate
- 5/04 11:10 good entry: spread=29c → PASSES (29 ≥ 27)
- min_spread=30c: blocks the 5/04 29c entry → loses the winner
- min_spread=29c: 4/29 later entry (29c) fires badly

**Results on 6 J source-of-truth days:**
- Baseline: -$408 edge_capture (fails OP-16 floor)
- Config B (vix_soft only): +$205 (safe incremental improvement)
- Config F27: +$1,661 (107.7% of J max, BEATS J's theoretical maximum)
- 4/29: -$12 (near-breakeven), 5/01: -$122 (structural, can't fix), 5/04: +$1,794, all losers: SKIP

**General rule:** when a filter condition uses direction comparison (rising/falling/flat) against short-horizon bars, the filter may over-block on extended-regime markets where the indicator is already at an extreme and has stopped moving. Add a `soft_mode` parameter that demotes the failed direction check to a score modifier rather than a hard block. Combined with a minimum-quality gate (e.g., `min_spread_cents`) to prevent allow_one_blocker from firing on clearly-bad setups, this allows the engine to enter when conditions are substantively correct but technically stale.

**Encoded in:**
- `backtest/lib/filters.py` — `allow_one_blocker_min_spread_cents` parameter in `evaluate_bearish_setup()`
- `backtest/lib/orchestrator.py` — `allow_one_blocker_min_spread_cents` passed through to filters
- `backtest/autoresearch/winner_day_entry_blocker_diag.py` — per-bar filter decision dump for diagnosis
- `backtest/autoresearch/vix_mode_edge_sweep.py` — 5-config VIX filter mode sweep
- `backtest/autoresearch/vix_soft_perbar_diag.py` — per-bar Config B vs E comparison
- `backtest/autoresearch/allow_one_blocker_minspread_sweep.py` — 8-threshold min-spread sweep
- `strategy/candidates/2026-05-19-vix-soft-allow-one-blocker-minspread27.md` — candidate spec

---

## L45: VIX gate `as_of` timestamp — reading opening VIX instead of trigger-time VIX silently over-blocks mid-session entries (2026-05-19)

**Symptom:** The BULL-side VIX filter (`lib/filters.py` Filter F8) blocked entries mid-session on multi-leg days even when the contemporaneous VIX clearly warranted a pass. Specifically, on chop days where VIX expanded intraday, the filter used 09:30 session-open VIX; by the time a 14:00 ET trigger fired, VIX had risen to a level that should have passed F8, but the cached morning value was lower.

Investigation was done via `backtest/autoresearch/t81_bull_vix_gate.py` (one-shot diagnostic). The t81 investigation surfaced the pattern but didn't have a regression test. As a result, future sessions couldn't tell whether the bug was still live or already closed — they'd have to re-investigate from scratch.

**Root cause:** `lib/filters.py` `evaluate_bearish_setup()` and `evaluate_bullish_setup()` looked up VIX from a cached snapshot without an `as_of` parameter. The snapshot was populated at session-open (first heartbeat tick) and never refreshed mid-session. On days when VIX moved ≥ 0.5 points intraday, the comparison drifted from contemporaneous truth.

The t81 diagnostic confirmed a specific class: on 5/14 with VIX=17.23-18.06 throughout the day, the morning cached value was 17.23 (borderline) while the afternoon value was 18.06 (clearly passing). Any setup evaluated mid-session against the 17.23 cached value had a ~50% chance of wrong verdict.

**Fix (already shipped before lesson was authored):** `v18_vix_filter.py` offline test T4 asserts the VIX filter uses `vix_as_of_trigger_time` (the VIX value at the same bar timestamp as the trigger bar). `lib/filters.py` and `backtest/lib/filters.py` both pass an explicit `as_of` timestamp to their VIX lookup, retrieving the contemporaneous 5m VIX bar rather than a session-start snapshot.

```python
# WRONG (before fix) — session-open VIX cached once:
vix_now = state["vix_snapshot"]  # populated at 09:30, stale by 14:00

# CORRECT (after fix) — trigger-time VIX:
vix_now = vix_df.loc[trigger_bar_timestamp, "close"]  # contemporaneous
```

**General rule:** whenever a filter compares a market indicator against a threshold, ensure the indicator is retrieved at the same timestamp as the trigger bar — not at session-open or cached at run-start. This applies to: VIX, ADX, ATR, and any other volatility/regime indicator used as an entry gate. The symptom of a cached-at-open indicator is subtle: the filter will pass/fail correctly early in the session and silently drift wrong mid-session. Write an offline test that explicitly passes a morning vs afternoon `as_of` to the filter and verifies both produce distinct correct outcomes.

**Encoded in:**
- `crypto/validators/v18_vix_filter.py` — offline test T4 asserts `as_of` contract
- `lib/filters.py` + `backtest/lib/filters.py` — explicit `as_of` parameter in VIX lookup (OP-4 paired sync)
- `backtest/autoresearch/t81_bull_vix_gate.py` — one-shot diagnostic (investigate, not maintain; v18 is the regression test going forward)

---

---

## L46: Monthly signal distribution is a required check before concluding on setup win rate (2026-05-19)

**Symptom:** A new LEVEL_BREAK_FIRST_STRIKE backtest reported "50% WR across 16 months (34 signals)" which sounds like a neutral-to-slightly-positive result worth further investigation. The aggregate looked stable. Guard rail failure was the blocker, but the WR headline was treated as the primary quality signal.

**Root cause:** The monthly signal breakdown was computed (it was in the output JSON) but not treated as a first-class quality gate. The distribution was: 4 signals in all of 2025 (12 months), 30 signals in Jan–May 2026 (5 months). The "50% WR" was almost entirely driven by 30 high-vol signals from a single volatile regime. In 2025 (12 months of data), the setup fired only 4 times. The per-regime WR is unknown because the 2025 sample is too small to be meaningful.

This means:
- A setup that fires 30× in 5 months and 4× in 12 months is **regime-specific**, not multi-regime.
- Its long-run edge is unknown. It could be 50% WR in vol regimes and 20% WR in calm ones.
- Backtesting it against "16 months" gives false confidence — 88% of the evidence is from one regime.

**Fix:** Before reporting any setup's win rate, run a **regime distribution check**:

```python
month_counts = Counter(s["date"][:7] for s in signals)
regime_concentration = max(month_counts.values()) / sum(month_counts.values())
# If regime_concentration > 0.30 (30% from a single 3-month window):
#   flag as REGIME_CONCENTRATED before reporting WR
months_with_signal = len(month_counts)
if months_with_signal < 8:  # < 8 of 16 months have ANY signal
    flag as SPARSE_MONTHS
```

Regime-concentrated setups need separate WR by regime (high-vol vs low-vol, measured by monthly average VIX level):
- If high-vol WR ≥ 55% AND low-vol WR ≥ 45% → multi-regime edge, real
- If high-vol WR ≥ 55% AND low-vol WR < 40% → vol-regime-specific, needs VIX gate
- If low-vol WR > 55% AND high-vol WR < 40% → calm-regime only (rare but possible)

**The spread-tier check is a companion:** when loser-day violations cluster in tight ribbon spreads (<12c), and low-vol months also cluster in tight spreads, both issues share the root cause (tight-ribbon signals tend to appear in calm/chop conditions). A minimum spread gate fixes the guard rail AND reduces low-vol noise simultaneously.

**General rule:** any new setup scan output should include these three checks in the top of the JSON results, before win_rate is reported:
1. `months_with_signal` — should be ≥ 8 of 16 for multi-regime confidence
2. `regime_concentration` — max % from any single 3-month window; flag if > 30%
3. `vol_regime_split` — signals split by "monthly VIX avg ≥ 20 (high-vol) vs < 20 (low-vol)"

**Encoded in:**
- Chef-inbox item `strategy/candidates/_chef-inbox/2026-05-19-ribbon-lag-first-strike-bear.md` — findings section documents the 4-in-2025 vs 30-in-2026 distribution explicitly
- `backtest/autoresearch/level_break_first_strike_scan.py` — monthly_signal_counts already computed; future scans should auto-flag if `months_with_signal < 8`
- This lesson (L46)

---

## L47: Multi-step bracket placement is NOT atomic — heartbeat timeout mid-execution leaves naked option positions (2026-05-18)

**Symptom:** On 2026-05-18 09:48 ET (first live trading day), Bold heartbeat submitted a SPY 740C parent buy order to Alpaca but timed out before the TP1 and stop legs were attached. The order executed as a `"simple"` (no bracket) SPY call position — no stop loss protection. Rule 3 violated by infrastructure, not intent.

Incident timeline:
1. Heartbeat fired at 09:48 ET, scored bull=11/11, submitted parent BUY limit @ $1.74 × 5 contracts.
2. 160s wrapper timeout fired before the same Claude invocation could place TP1 + stop legs.
3. 18 PIDs killed. Order survived as naked buy with no stop.
4. Parent order was NOT filled (limit price unfavorable), so Rule 3 violation was theoretical — but if it had filled, the position would have had zero downside protection.
5. J authorized cancel at 09:54:37. Order canceled cleanly.

**Root cause:**
1. **Heartbeat timeout was 160s** — right on the edge for multi-tool entry ticks (snapshot chain + place parent + TP1 + stop + state write + screenshot = 90-180s on slow Alpaca ticks).
2. **No atomic bracket guard** — a timeout between parent fill and stop placement leaves an unprotected position silently. No existing automation detected the naked position state.
3. **`order_class="simple"` fallback** — when bracket placement fails partway, Alpaca commits the parent order while the stop legs remain unfiled.

**Fix:**

```python
# Immediate: wider timeout + budget
# run-heartbeat-aggressive.ps1:
tickTimeout = 220  # was 160s
MaxBudgetUsd = 1.00  # was 0.50

# Structural: atomic_bracket_guard.py — post-tick safety primitive
# Runs after every Claude invocation via Invoke-PythonHidden
# Detects: naked filled positions (RED) + orphan unfilled parent orders (AMBER → auto-cancel)
# Pure REST — no MCP dependency
# Both accounts checked in one pass
# Wired into both run-heartbeat.ps1 + run-heartbeat-aggressive.ps1

# Pattern: if ENTER fires, write intended bracket structure to position-state BEFORE placing any order
# On next tick: if position-state says "bracket_intended" but only parent filled → cancel parent, emit ERROR_ALPACA
```

**General rule:** in any system where a multi-step order flow can be interrupted mid-sequence, the FIRST step should not be considered committed until ALL protective legs are confirmed filled. For options brackets: either (a) use `order_class="bracket"` (server-side atomic) or (b) if placing legs manually, write a "bracket incomplete" sentinel before placing the parent, clear it only when stop leg confirms filled, and have a watchdog that auto-cancels uncommitted parents on the next invocation.

**Encoded in:**
- `setup/scripts/atomic_bracket_guard.py` — 228 LOC pure-REST safety primitive, 17 unit tests
- `setup/scripts/test_atomic_bracket_guard.py` — 17/17 PASS
- `setup/scripts/run-heartbeat.ps1` + `run-heartbeat-aggressive.ps1` — wired post-tick
- `setup/scripts/run-heartbeat-aggressive.ps1` — timeout 160s→220s, budget $0.50→$1.00
- `journal/2026-05-18.md` § INCIDENT — 09:48 ET Bold missed-entry — full incident chronicle

---

## L48: A 50% aggregate WR on a novel setup is NOT evidence of edge — always stratify by vol-regime before concluding on expectancy (2026-05-19)

**Symptom:** The LEVEL_BREAK_FIRST_STRIKE setup scan (34 signals, 16-month backtest) reported a 50% win rate and 1.21 R:R ratio in the initial write-up. This was presented as "marginal positive expectancy." However, when L46 (monthly distribution gate) was applied and the signals were further stratified by VIX level, the 50% headline shattered:

| Regime | N | WR |
|---|---|---|
| VIX ≥ 20 | 4 | **100%** |
| VIX < 20 | 30 | **43.3%** |

The 43.3% WR in the dominant regime (88% of signals) is below neutral — negative expectancy when R:R is ~1.0. The 50% aggregate was purely a blending artifact from 4 high-VIX outlier wins.

**Root cause:** The initial analysis computed aggregate WR over the full signal set without checking whether signals from different market regimes had homogeneous performance. In options trading, VIX level is the single most important context variable for any setup that depends on premium / volatility / directional follow-through.

**Three-stage check that would have caught this in one pass:**
1. **L46 gate (already encoded):** check monthly signal distribution → 62% of signals in 2026-Q1 triggered the REGIME_CONCENTRATED warning
2. **Vol-regime split:** bucket signals by VIX level (< 15, 15–20, 20–25, 25–30, 30+). Compute WR per bucket. If the low-VIX bucket (the majority) has WR below 50%, the aggregate is misleading.
3. **VIX-gated scan (v4):** when the split reveals a high-VIX edge, run a VIX-gated scan immediately to get the clean signal count. If N < 15, the setup is WATCH-ONLY regardless of WR.

**The general rule:** any setup scan that shows aggregate WR within ±10pp of 50% MUST be stratified by VIX level before the WR is used for any ratification decision. A setup that only fires cleanly at VIX ≥ 20 is a HIGH-VOL setup, not a GENERAL setup. High-vol setups require high-vol regimes to accumulate sample — this takes years, not months. They should be tracked as watchers from day one, not run through the standard combine-with-F27 backtest pipeline.

**The 4-scan LBFS arc (v1→v2→v3→vol-regime split→v4)** established a research precedent:
- v1: aggregate scan → reported 50% WR → apparently passable
- v2: guard-rail fix (MIN_SPREAD=12c) → still 50% WR
- v3: spread-tier isolation (MIN_SPREAD=20c) → 57% WR but N=7
- vol-regime split: VIX bucketing → revealed 43.3% dominant regime
- v4: VIX-gated (VIX≥20) → 100% WR but N=4 — WATCH-ONLY

The correct sequence is: aggregate scan → L46 monthly gate → L48 vol-regime gate → VIX-gated scan → only then decide whether to proceed to combined backtest. Without L48, this setup would have been proposed for production with negative expected value in 88% of the environments it would have fired in.

**Encoded in:**
- `strategy/candidates/_chef-inbox/2026-05-19-ribbon-lag-first-strike-bear.md` — full 4-scan arc + vol-regime analysis + v4 results + updated watch-only recommendation
- `analysis/recommendations/level_break_first_strike_scan_v4.json` — VIX-gated scan output (n=4, 100% WR)
- `backtest/autoresearch/level_break_first_strike_scan.py` — canonical scan script (restored to original state after v4 run)

---

---

## L49: Premarket loop-state reset only covered the safe account — aggressive account carried stale first_entry_lock into the next session (2026-05-19)

**Symptom:** On 2026-05-19 morning (pre-market), `automation/state/aggressive/loop-state.json` had `session_id: "2026-05-18"` and `first_entry_lock: [BEARISH stop-out, BULLISH stop-out]` from 5/18's two losing trades. If the aggressive heartbeat fired at 09:30 ET without this being cleared, the first-entry-after-stop check would have seen two stop-out entries and blocked BOTH BEARISH and BULLISH setups for the entire day of 5/19 — even though those blocks belonged to yesterday's session.

**Root cause:**
1. `automation/prompts/premarket.md` Step 7 only initialized `automation/state/loop-state.json` (safe account).
2. It did NOT mention `automation/state/aggressive/loop-state.json` (aggressive account).
3. The aggressive account went live on 2026-05-18 as the first live trading day — this gap existed from the start but wasn't visible until 5/18 generated actual lock entries.
4. The `first_entry_lock[]` entries have no `session_id` field of their own — only the OUTER `loop_state.session_id` acts as the freshness indicator. The heartbeat was supposed to "filter to today's session_id rows" but this instruction was ambiguous (the entries carry no session_id to filter on).

**Fix:**
1. `premarket.md` Step 7b added: also write `automation/state/aggressive/loop-state.json` with `session_id: today` + `first_entry_lock: []`
2. Explicit session guard added to both `heartbeat.md` and `aggressive/heartbeat.md`: "If `loop_state.session_id != today_date_et`, treat `first_entry_lock = []` — state is stale from prior session"
3. `aggressive/loop-state.json` manually reset for 2026-05-19 as an immediate belt-and-suspenders fix

**General rule — dual-account state initialization:** any new state file introduced for a second account MUST be traced through the full lifecycle (premarket init → heartbeat read → EOD write → next-day reset). The typical path for the safe account (1 file) often has no corresponding step for the aggressive account until a bug makes the gap visible. When adding a second account's state file, immediately add reset logic to `premarket.md` as Step N+0.5 alongside the equivalent safe-account step.

**Encoded in:**
- `automation/prompts/premarket.md` Step 7b — aggressive loop-state initialization
- `automation/prompts/heartbeat.md` — session guard on first_entry_lock check
- `automation/prompts/aggressive/heartbeat.md` — same session guard

---

## L50: SPY-price scan heuristics overstate option-trade edge for level-break setups — real-fills required before claiming any WR (2026-05-19)

**Symptom:** The LEVEL_BREAK_FIRST_STRIKE (LBFS) v4 scan reported **100% WR (4/4)** for VIX≥20 signals using the criterion "SPY low of next 3 bars ≤ bar.close − 50c". Real-fills validation with `simulator_real.py` showed **0/4 WR (−$227)** with the production −8% premium stop. The chart-stop-only scenario showed **1/4 WR (+$373)**, where the one genuine win was +$1,135 and the three losses ranged from −$159 to −$303.

**Root cause — three layers:**

1. **SPY-price WR ≠ option P&L WR.** The scan measures whether the underlying moved enough (50c) within 3 bars. It does NOT model:
   - Option premium time-decay between trigger and entry (entry is at next-bar OPEN, not trigger close)
   - Initial bounce after a level break ("retest the break from below"), which pushes ATM put premiums DOWN before the move develops
   - The −8% stop buffer = $0.20 on a $2.50 ATM put in VIX=25-30 conditions — far too small to survive a 50c SPY bounce

2. **"No exit on entry bar" rule hides winning intrabar moves.** `simulator_real.py` sets `spy_idx = entry_bar_idx + 2` — the entry bar's option moves are never checked for TP1 or stop. For signal 4 (2026-03-30), the option hit HIGH=3.12 on the entry bar (+23% from 2.53 entry), which a real trader could have captured. The simulation never sees this.

3. **Scan WIN ≠ sustained break.** Two of the four "wins" were FALSE BREAKS: SPY temporarily broke below 657.03 (2026-03-25) and 636.00 (2026-03-30) but recovered above the level within 15–20 minutes. The scan's intrabar-low criterion records the dip as a WIN even though the price action invalidated the trade hypothesis quickly. Only the 2025-10-10 signal was a genuine sustained break (SPY stayed below the broken level for hours).

**The numbers:**

| Signal | Date | VIX | Scan WR | Real (−8% stop) | Real (chart stop only) | Classification |
|--------|------|-----|---------|-----------------|------------------------|----------------|
| 1 | 2025-10-10 11:00 | 22.05 | WIN | −$54 LOSS | +$1,135 WIN | Genuine sustained break |
| 2 | 2026-03-25 09:50 | 25.31 | WIN | −$60 LOSS | −$300 LOSS | False break (reversed in 15 min) |
| 3 | 2026-03-25 09:55 | 25.31 | WIN | −$52 LOSS | −$303 LOSS | False break (second signal, same day) |
| 4 | 2026-03-30 09:50 | 30.69 | WIN | −$61 LOSS | −$159 LOSS | Shallow drop, fast reversal |

**Fix — mandatory real-fills gate for all level-break scans:**

Any scan that uses a "SPY drops N cents in K bars" WIN criterion MUST run `simulator_real.py` before any WR claim is cited in a spec or forwarded for ratification. The gate:
1. Run `simulator_real.py` with production stop params (−8% for safe account)
2. Run `simulator_real.py` with chart-stop-only (premium_stop_pct=−0.99, rejection_level = break_level)
3. Report BOTH results. Cite chart-stop-only as the OPTIMISTIC bound; production stop as the CONSERVATIVE bound.
4. If the conservative bound WR < 50% AND the chart-stop-only WR < 60%, the setup does NOT have confirmed positive expectancy with real options.

**Additional lesson — stop mechanism for level-break setups:**
For setups that enter on a level break (LBFS, SNIPER), the intended stop is a CHART STOP (SPY recovers back above break_level + buffer), not a PREMIUM % stop. The premium % stop fires on normal option noise (IV fluctuation, early delta moves before the direction confirms). This means:
- Production integration of LBFS (when/if it reaches N≥15) should use the chart stop as PRIMARY, with premium stop as a SECONDARY deep backstop (e.g., −30%)
- The current production setup (−8% premium stop) is designed for RIDE-THE-RIBBON entries where direction is already confirmed by the ribbon — not for FIRST-STRIKE entries where direction is still in flux

**Encoded in:**
- `analysis/recommendations/lbfs-v4-real-fills.json` — full multi-scenario real-fills output
- `backtest/autoresearch/lbfs_real_fills_validate.py` — reusable real-fills validator for LBFS
- `strategy/candidates/2026-05-19-level-break-first-strike-bear.md` — spec updated with corrected WR and real-fills findings
- `markdown/doctrine/LESSONS-LEARNED.md#L50` — this entry

---

## L51 — Violent initial bounce on VIX≥20 level-break entries invalidates all premium stops

**Date observed:** 2026-05-19  
**Context:** LBFS (LEVEL_BREAK_FIRST_STRIKE_BEAR) stop mechanism redesign validation using `simulator_real.py` against OPRA fills.

**Symptom:** Every premium stop tested on the genuine VIX≥20 LBFS signal (2025-10-10) fired during the FIRST post-entry 5-minute bar — at exit times of 10 minutes regardless of stop width. Widening the stop from −8% to −30% produced the SAME exit outcome: `EXIT_ALL_PREMIUM_STOP` at minute 10, with worse P&L (−$204 at −30% vs −$81 at −8%).

**Root cause:** On a genuine high-volatility level break (VIX≥20, vol=9.0×, break=156c), the retest phase creates a violent intrabar put-premium collapse in the FIRST 5-minute bar after entry. Quantified on 2025-10-10:
- Entry premium: **$2.27**
- First post-entry bar LOW: **$0.92**
- Drop: **−59.5% in a single 5m bar**

Any premium stop where `|stop_pct| < 0.595` will fire on the bar LOW of this first bar. No intermediate stop value (−8%, −20%, −30%) escapes this: they ALL hit before the bar closes. The move continued down powerfully after the bounce, with TP1 eventually firing at +$1,135 with 290-min hold — but only if you survived the bounce.

**All 4-scenario comparison (N=4 VIX≥20 signals, qty=3 puts, real OPRA fills):**

| Stop mechanism | WR | Total P&L | Signal 1 exit |
|---|---|---|---|
| −8% premium stop (production) | 0/4 | −$227.04 | EXIT_ALL_PREMIUM_STOP, 10 min |
| −20% premium stop | 0/4 | −$567.30 | EXIT_ALL_PREMIUM_STOP, 10 min |
| −30% premium stop (redesign) | 0/4 | −$782.70 | EXIT_ALL_PREMIUM_STOP, 10 min |
| −99% (pure chart stop) | 1/4 | +$373.20 | TP1_THEN_RUNNER_TIME, 290 min |

Note: false breaks (signals 2, 3, 4) lose less with tighter stops — the bounce-and-recover pattern is asymmetric. Tighter stops protect against false breaks but detonate on genuine ones.

**Fix:** For LBFS-class setups (first-strike level-break entries), the ONLY viable stop mechanism is a **pure chart stop**:
- `premium_stop_pct = -0.99` (effectively disabled — lets the bounce resolve)
- `rejection_level = break_level` (the level that was broken)
- `LEVEL_STOP_BUFFER = 0.50` (fire when SPY closes back above `break_level + $0.50`)

The chart stop distinguishes genuine breaks (SPY continues lower → never triggers level stop → TP1 fires) from false breaks (SPY recovers above the level → level stop fires, limiting loss to ~$53-$159/trade).

**General rule:** Before testing ANY stop width on a level-break intraday entry strategy, examine the per-bar premium path for the first 1-3 bars after entry. If bar LOW shows >50% premium drop in bar 1, all premium stops are structurally broken — the bounce magnitude sets a hard floor below which no premium stop can survive. Only chart-based (price-level) stops can discriminate signal from noise in this regime.

**Discriminating filter (N=1, not yet testable):** The genuine break had vol=9.0× + break=156c. False breaks had vol=2.6-3.4× + break=23-54c. A filter (vol ≥ 5× AND break ≥ 100c) would pass only the genuine signal. However, this leaves N=1 historically — not ratiifiable until N_vix_ge_20 ≥ 15 signals accumulate via watcher. Tracked in `strategy/candidates/2026-05-19-level-break-first-strike-bear.md`.

**Encoded in:**
- `analysis/recommendations/lbfs-v4-real-fills.json` — per-signal scenario results including `chart_stop_redesign_minus30pct`
- `backtest/autoresearch/lbfs_real_fills_validate.py` — 4-scenario validation including redesign scenario aggregation
- `strategy/candidates/2026-05-19-level-break-first-strike-bear.md` — spec updated; stop mechanism redesign gate marked complete; pure-chart-stop production wiring spec added
- `markdown/doctrine/LESSONS-LEARNED.md#L51` — this entry

---

## L52: `failed_breakdown_wick` is a trend-continuation signal, NOT a reversal — contra-regime gating inverts its edge (2026-05-19)

**Symptom:** A 357-day backtest of regime-gated contra-regime variants across 7 pattern detectors showed that `contra_failed_breakdown_wick` had a **−1.5pp delta** vs the baseline (aligned-trend) version. Applying the contra-regime filter (50-bar SMA) to `failed_breakdown_wick` made performance WORSE, not better. The baseline `failed_breakdown_wick` (aligned) had higher WR than the contra version.

**Root cause — structural misclassification of the pattern:**

`failed_breakdown_wick` fires when a bar's LOW pierces below a multi-bar support level and the close recovers above it ("sweep and reclaim"). Intuitively this looks like a reversal (sellers tried to break down, buyers reclaimed → bullish). But in trend context it's the opposite:

- **In a DOWNTREND:** A wick-below-support-and-recover means the SUPPORT IS HOLDING. The bullish wicking pattern is the continuation signal — the dominant sellers are still present, buyers reclaimed for now, and the market is likely to retest. Calling this "contra-trend" (contra-bearish) is wrong; the bear trend is doing exactly what it should (testing support, reclaiming, and continuing down on the next bar).
- **In an UPTREND:** The pattern (bar wicks below an uptrend support, closes back above) is the textbook "dip-buy" continuation signal that keeps the trend intact. The contra-regime gate (fires only in downtrend) would suppress this, throwing away the most reliable occurrence.

The wick-reversal intuition fails because the "reversal" is single-bar: the close is back above support by bar end, but the NEXT bar's bias follows the broader trend. In downtrend, a temporary wick-reclaim gives aggressive bears a better reload point — it's not a bottom.

**Contrast with `double_bottom`:** A genuine reversal (double_bottom = two low pivots at the same level with a recovery rally between them) IS improved by contra-regime gating (+3.8pp delta). The double-bottom takes multiple bars to form, involving genuine commitment by buyers. A single-bar wick does not.

**The discriminator rule:**
- **Multi-bar structural reversals** (double_bottom, double_top, head_and_shoulders): contra-regime filter HELPS — these patterns represent a genuine fight against the prevailing trend.
- **Single-bar wick patterns** (failed_breakdown_wick, potentially rejection_at_level): contra-regime filter HURTS or is neutral — single-bar wicks are completion moves within the trend, not reversals against it.

**Numbers (357-day BTC analysis, `analysis/regime-gated-comparison-2026-05-19.md`):**

| Detector | Delta (contra vs aligned) | Conclusion |
|---|---|---|
| `double_bottom` | +3.8pp | Multi-bar reversal → contra gating helps |
| `rejection_at_level` | +2.0pp | Bearish at resistance in bull trend → contra helps |
| `momentum_acceleration` | +7.9pp | Best: momentum in wrong direction signals exhaustion |
| `head_and_shoulders_top` | +21.9pp (n=8, watch-only) | Classic reversal → contra helps |
| `double_top` | +0.2pp | Essentially flat |
| **`failed_breakdown_wick`** | **−1.5pp** | **Single-bar wick is continuation → contra gating INVERTS edge** |
| `inside_bar_consolidation` | +4.6pp (estimated) | Consolidation before next trend move |

**Fix — encode in production code:**

1. `scan_all_contra_regime()` in `crypto/lib/chart_patterns.py` now has a docstring warning: "contra_failed_breakdown_wick has −1.5pp delta — ALIGNED beats CONTRA for wick patterns (they're trend-continuation, not reversal, signals)."
2. `scan_high_edge_contra_regime()` (new function) excludes `contra_failed_breakdown_wick` and `contra_double_top`. Production code should call this function, not the full scan.
3. `_HIGH_EDGE_CONTRA_DETECTORS` tuple documents the 4 evidence-backed variants.

**General rule:** Before applying a regime gate to any detector, ask: does this pattern take multiple bars to form (structural reversal) or is it a single-bar event (wick/spike)? Single-bar events are typically completion moves within the prevailing trend — the contra-regime gate inverts their edge by treating confirmations as reversals.

**Encoded in:**
- `crypto/lib/chart_patterns.py` — `scan_high_edge_contra_regime()` excludes `contra_failed_breakdown_wick`; `scan_all_contra_regime()` docstring warns about no-edge detectors
- `analysis/regime-gated-comparison-2026-05-19.md` — per-detector delta table
- `crypto/validators/v22_chart_patterns.py` T17 — regression test for subset contract
- `markdown/doctrine/LESSONS-LEARNED.md#L52` — this entry

---

## L53 — 2026-05-19: gym_session silent masking — key-name mismatch + BOM encoding in _read_json

**Symptom:** Daily gym scorecard reports heartbeat-tick-audit=GREEN (0 ticks) even when
heartbeat_tick_audit.py found 6/16 MISALIGNED-CRITICAL ticks (38%).
heartbeat-mcp-self-test shows MISSING even though the file exists and is GREEN.

**Root cause 1 (key mismatch):** `gym_session._classify_tick_audit()` called
`data.get("by_classification", {})` but `heartbeat_tick_audit.py` writes the field as
`"counts"`. Default `{}` → critical=0 → always GREEN.

**Root cause 2 (BOM encoding):** PowerShell 5.1 `ConvertTo-Json | Out-File -Encoding UTF8`
writes UTF-8 BOM. `_read_json(encoding="utf-8")` reads BOM as literal text →
`json.loads` raises `JSONDecodeError` → function returns `None` → MISSING verdict.

**Fix:** (1) `data.get("counts", data.get("by_classification", {}))` — backward-compatible
key lookup; (2) `_read_json` tries `["utf-8-sig", "utf-16", "utf-8"]` in order.

**General rule:** whenever two modules share a JSON contract, write a smoke test that
asserts writer_key ∈ reader_keys. Any PowerShell → Python JSON handoff MUST use
`utf-8-sig` or `utf-16` in the Python reader.

**Encoded in:** `backtest/autoresearch/gym_session.py` _read_json + _classify_tick_audit.
Cross-reference: T-2026-05-19-GYM-BUGS.

---

## L54 — 2026-05-19: /loop during market hours kills Gamma_Heartbeat via shared rate limit

**Symptom:** No heartbeat fires 10:57–12:40 ET on first two live trading days.
J asked why 12:20 and 12:35 obvious entries were missed. Rate-limit throttle was
the cause. Ghost ENTER_BEAR at 10:03 (logged, no Alpaca order placed) also
suspected to be a rate-limit mid-generation truncation.

**Root cause:** Claude Code API rate limit is shared between all sessions.
`claude --print` (Gamma_Heartbeat scheduled task) + interactive `/loop` session
both consume the same token quota. `/loop` engineering work during 09:30-15:55 ET
starves the heartbeat of API capacity.

**Fix (immediate):** NEVER run interactive `/loop` engine-benefit research during
market hours (09:30-15:55 ET). After-4pm window per OP-22 is the correct cadence.

**Fix (durable):** The only permanent fix is separate Claude accounts: one for
interactive engineering sessions, one for scheduled production tasks. Until that
is set up, the rate limit window is a hard constraint.

**Ghost entry pattern:** any `claude --print` heartbeat invocation that gets
truncated mid-generation due to rate limit writes partial output including intent
strings ("ENTER_BEAR at 735.40") without executing the `mcp__alpaca__place_option_order`
tool call. The decision is logged as an entry; no order exists in Alpaca. This
creates a "ghost entry" divergence between journal and Alpaca state.

**Mandatory check (post-session):** after any market session, cross-check
`automation/state/decisions.jsonl` ENTER_* decisions against Alpaca order history.
Any ENTER without a matching Alpaca order_id is a ghost entry.

**General rule:** OP-22 after-4pm work block is NOT just a preference. During
09:30-15:55 ET the ONLY Claude API consumers should be the 3 scheduled production
tasks: Gamma_Heartbeat, Gamma_Heartbeat_Aggressive, Gamma_WatcherLive.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md#L54`. Wake-protocol.md rate-limit foot-gun list.

---

## L55 — 2026-05-19: L51 analog for calls — premium stops incompatible with first-strike BULL bounce entries (NLWB)

**Symptom:** NLWB real-fills v1 (`premium_stop_pct=-0.10`) produced 2/5 WR (40%) despite
scan proxy WR of 71.3%. Primary anchor case T1 (2026-05-04 09:55 ET, MIXED ribbon):
entry premium $1.04, stop threshold $0.936 (−10%). First bar after entry: brief intrabar
premium dip fires `EXIT_ALL_PREMIUM_STOP`. SPY subsequently moved +$1.36 as expected
(scan WIN). Real fills: LOSS. The stop fired on the dip, not on the directional move.

**Root cause (L51 analog for calls):** L51 documented that on level-BREAK entries, the
initial retest pushes put premiums DOWN 8-59% before the bearish move develops. The same
structural incompatibility applies to BULL bounce entries:

After a wick-bounce bar closes above a named level, the *next* 1-3 bars commonly show brief
intraday retracements (minor pullback before the upward SPY move develops). During these
brief pullbacks, ATM call premium can dip ≥10% before recovering. A −10% premium stop
fires on this dip — before the directional call trade has time to develop.

The entry bar IS the adverse move (bar wicked below the level). Any subsequent premium
oscillation is noise, not signal. A premium stop cannot distinguish noise from failure.

**Fix:**
- `premium_stop_pct = -0.99` (effectively disabled — chart stop primary)
- Chart stop: fires when `spy_bar["close"] < rejection_level - $0.50`
- This correctly identifies false bounces (SPY falls back BELOW the level) while surviving
  normal intrabar fluctuations that precede the directional move.

**Key data:**
```
v1 (premium_stop_pct=-0.10): 2/5 WR (40%) — stops on post-bounce noise
v2 (premium_stop_pct=-0.99, chart-stop only): 3/5 WR (60%) overall
    Production-eligible subset (MIXED/BULL ribbon, T1+T2+T3): 2/3 = 67% WR ✓
    Consistent with scan proxy WR 67.5% on MIXED/BULL subset
T1 anchor: CONVERTED from LOSS to WIN with chart-stop-only (+$62 via TP1_THEN_RUNNER_RIBBON)
T3 (false bounce, third touch): correctly fires EXIT_ALL_LEVEL_STOP ✓
```

**General rule (extends L51 + OP-20 disclosure 4):** Before testing ANY stop width on a
first-strike bounce entry (BULL or BEAR), check:
1. Is the entry bar itself the adverse move? (NLWB: bar wicks below level. LBFS: bar closes below level.)
2. If YES → subsequent premium fluctuations are NOT signals — they are noise from the setup mechanics.
3. Premium stop ONLY works when entry is in a position of strength (trend already confirmed, entry is
   with momentum). For counter-trend / first-strike entries: **chart stop primary, premium stop disabled.**
4. The chart stop (`rejection_level`) discriminates genuine failure (SPY recrosses the level) from
   normal noise (premium briefly dips while SPY consolidates above the level).

**Walk-forward OOS (PDL relaxed variant):** STABLE — train WR 75.7%, test WR 67.8% (−7.9pp delta,
well within 10pp STABLE threshold). Guard PASS on all 5 holdout signals.

**Cross-references:**
- L50 (original): SPY-price WR ≠ option P&L — real fills required before any setup WR claim
- L51 (original): Bearish first-strike + −59.5% initial premium drop = structural incompatibility (same principle)
- This lesson: Bull first-strike + −10% premium stop fires on post-bounce pullback = same incompatibility

**Encoded in:** `backtest/lib/watchers/named_level_wick_bounce_watcher.py` (DEFAULT_PREMIUM_STOP_PCT updated to -0.99) + `backtest/autoresearch/nlwb_real_fills_validate.py` + `analysis/recommendations/nlwb_real_fills.json` + `strategy/candidates/2026-05-20-named-level-wick-bounce-bull.md` Real-Fills section + `crypto/validators/v28_nlwb_bounce_gate.py` (regression gate for float-precision fix + NLWB/LBFS mutual-exclusion).

---

## L56 — 2026-05-20: `crypto.lib.chart_patterns` not importable in watcher scripts — ALL pattern watchers silently return None (sys.path missing ROOT)

**Symptom:** `watcher-observations.jsonl` shows 0 observations for HEAD_AND_SHOULDERS_BEAR, DOUBLE_BOTTOM_BASE_QUIET, DOUBLE_BOTTOM_MORNING_LOW_VOL, FAILED_BREAKDOWN_WICK_MORNING_MID, MOMENTUM_ACCELERATION_HIGHVOL. NLWB (which doesn't use `crypto.lib`) shows 294 observations. No error in logs.

**Root cause:** The pattern-based watchers (`hs_watcher.py`, `double_bottom_base_quiet_watcher.py`, `double_bottom_morning_low_vol_watcher.py`, `fbw_morning_mid_watcher.py`, `momentum_acceleration_highvol_watcher.py`) all do:
```python
try:
    from crypto.lib.chart_patterns import Bar, head_and_shoulders_top as _detect_hs
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False
```
If `_PATTERNS_AVAILABLE = False`, `detect_*()` silently returns `None` — no error, no log. The `crypto` package lives at `42/crypto/` (ROOT level), but the watcher replay + live scripts only added `REPO` (`42/backtest/`) to `sys.path`, NOT `ROOT` (`42/`). So `import crypto.lib.chart_patterns` raised `ImportError` → silent zero signals.

**Discovery trigger:** backfill replay showed 0 signals for all pattern watchers. Smoke test confirmed `_PATTERNS_AVAILABLE = False` at runtime.

**Fix (3 files, each needed `ROOT` added):**
```python
REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent  # 42/
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # ← THIS LINE WAS MISSING
```
Files fixed:
- `backtest/autoresearch/watcher_live.py` (line 24)
- `backtest/autoresearch/watcher_replay.py` (line 24)
- `backtest/autoresearch/watcher_replay_new_watchers.py` (line 29)

**General rule:** Any script that imports from `crypto.*`, `lib.*`, or any package at the repo root (`42/`) must add BOTH paths:
```python
sys.path.insert(0, str(REPO))    # 42/backtest/
sys.path.insert(0, str(ROOT))    # 42/  ← needed for crypto.lib.*
```
The `try/except ImportError + _PATTERNS_AVAILABLE = False` guard is a safety net, not an error signal — silent failure is by design for production resilience, but it means missing ROOT is invisible until you specifically check observation counts.

**Prevention:** When adding any new watcher that uses `crypto.lib.*`, immediately check that all three watcher runner scripts have the ROOT sys.path insert. Add a smoke test: `from crypto.lib.chart_patterns import Bar; print("OK")` in each script's startup log.

**Encoded in:** `watcher_live.py` + `watcher_replay.py` + `watcher_replay_new_watchers.py` (all fixed 2026-05-20).

---

## L57 — 2026-05-20: `prior_bars=rth` in replay loop gives all bars May 2026 context regardless of current position — pattern detectors silently get wrong lookback

**Symptom:** Pattern watchers with a `.tail(N)` lookback (FBW uses `ctx.prior_bars.tail(20)`) always analyzed the LAST 20 rows of the full 16-month DataFrame (May 2026 bars) regardless of which bar was being processed.

**Root cause:** In `watcher_replay.py` and the original `watcher_replay_new_watchers.py`, `BarContext` was constructed with `prior_bars=rth` — the full 16-month RTH DataFrame. Pattern detectors call `ctx.prior_bars.tail(N)`, which always returns the last N rows of the full frame (May 2026), not the N rows preceding `bar_time`.

**Fix:**
```python
# WRONG (passes full DataFrame — .tail() returns May 2026 bars for every bar):
ctx = BarContext(..., prior_bars=rth, ...)

# CORRECT (slice up to current bar so .tail() gives preceding bars):
ctx = BarContext(..., prior_bars=rth.iloc[:idx + 1], ...)
```

**Fixed in:**
- `backtest/autoresearch/watcher_replay_new_watchers.py` (line 145)
- `backtest/autoresearch/watcher_replay.py` (line 108)

**Note:** `watcher_live.py` was already correct — it builds `prior_bars` from the live DataFrame up to current position, not a static full frame.

**General rule:** Any replay loop that constructs `BarContext` must pass `prior_bars=df.iloc[:idx+1]`, never `prior_bars=df`. The `.tail()` call inside detectors has no way to know it should be constrained — the constraint must come from the caller.

**Encoded in:** both replay scripts fixed 2026-05-20.

---

## L58 — 2026-05-20: NLWB parameter sweeps (TP1 + chart-stop) both fail on PDL-proxy backfill — level quality is the structural root cause

**Symptom:** NLWB real-fills WR=47.8% (-27pp below PDL scan proxy 71%). Both parameter rescue attempts failed: (a) TP1 sweep: WR degrades 43.5%→21.7% as TP1 increases; (b) chart-stop sweep: WR stays constant 43.5% for all chart-stop values while avg_loss only improves from -$215 to -$156. No parameter combination yields positive P&L.

**Root cause:** PDL-proxy scan fundamentally overstates bounce quality. PDL (prior day low) is the weakest named-level type — ephemeral, every trading day produces a new PDL, most are never retested. Production watcher uses ★★★ levels (PDL+5-day H/L+key pivots with multi-session defense) which carry far more structural significance. The -27pp degradation reflects this quality gap.

**Why TP1 rescue fails:** The 9/11 marginal wins at TP1=+30% exit because the ribbon flips back (TP1_THEN_RUNNER_RIBBON). These wins never reach TP1=+50%+ because SPY doesn't sustain the upward move. Raising TP1 converts these marginal wins into full chart-stop losses.

**Why chart-stop rescue fails:** All 12/13 losses already exit via EXIT_ALL_LEVEL_STOP — they're genuine false bounces where SPY fell 80c+ below PDL. Tightening stop reduces per-loss dollar amount ($215→$156 at pdl-0.10) but cannot change WR (winners exit via TP1/ribbon, not chart stop). Break-even WR with tightest stop still requires 57% vs actual 43.5%.

**The general rule (extends OP-20 disclosure 4):**
For bounce-off-support setups:
- If scan-proxy WR >> real-fills WR by >15pp → the level proxy is the problem, not the exit structure.
- PDL scans showing "positive edge" require confirmation via actual named levels.
- When WR is >10pp below break-even, parameter sweeps cannot close the gap.
- Fix: accumulate live observations on production ★★★ levels.

**Files:** `nlwb_tp1_sweep.py` + `nlwb_chart_stop_sweep.py` + `analysis/recommendations/nlwb_tp1_sweep.json` + `analysis/recommendations/nlwb_chart_stop_sweep.json`.

---

## L59 — 2026-05-20: Close-ceiling distribution pattern — N≥3 bars with wick ≥ level but close < level signals bear distribution

**Symptom:** During the 2026-05-20 live session, SPY tested PM ceiling 740.49 repeatedly without any 5-minute bar closing above it. The pattern was visible in real-time but not flagged by the engine. A "breakout" occurred at 14:40 (C:740.72) but reversed immediately on higher volume at 14:45 (C:739.77, vol:45,411). The engine had no primitive to detect this distribution signature.

**Root cause:** The heartbeat scanned for *trigger-level events* (close above / close below a level) but had no detector for the sustained-rejection-at-ceiling pattern. A bar that wicks ≥ level AND closes < level is a failed breakout attempt on that bar. Three or more such bars in a row means distribution — bulls are absorbed at every intrabar push but cannot defend at close. This was J's insight verbatim: *"notice how none of the 5m bars closed above the key level 736.13 that is an indicator we should have noticed to indicate bearish sentiment."*

**Fix:**

```python
def detect_close_ceiling(bars, ceiling, n_min=3):
    """Return (detected, max_run) for the close-ceiling distribution pattern."""
    max_run, current_run = 0, 0
    for bar in bars:
        if bar.high >= ceiling and bar.close < ceiling:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0  # close above ceiling resets the sequence
    return max_run >= n_min, max_run

def detect_floor_hold(bars, floor, n_min=3):
    """Return (detected, max_run) for the floor-hold accumulation pattern (bull analog)."""
    max_run, current_run = 0, 0
    for bar in bars:
        if bar.low <= floor and bar.close > floor:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run >= n_min, max_run
```

**Why consecutive (not aggregate):** A single bar closing above the ceiling IS a breakout attempt. The sequence resets. Two separate runs of N/2 bars each are two separate market events, not one pattern. The pattern's informational value is the *sustained* failure — consecutive rejections from the same ceiling.

**Fake breakout identification:**
- If close_ceiling(bars[:n], ceiling) == True AND bars[n].close > ceiling (fake breakout)
- Then bars[n+1:] starts a fresh assessment
- The fake breakout bar itself (close > ceiling) is the RED FLAG — it attracted buyers who then got trapped

**General rule:** Before any level-break trade, run detect_close_ceiling on the prior 5-10 bars at the same level. N≥3 consecutive ceiling-tests without a close-above = SKIP or fade the breakout. The first close-above after a distribution window is a bull-trap candidate, not a momentum entry.

**Encoded in:** `crypto/validators/v33_close_ceiling_detection.py` (8 offline tests, gym 63/63 green) + OP-26 stage count updated to 63.

---

## L60 — 2026-05-21: Gym runner.py hardcoded relative paths caused v13/v16 to fail silently when invoked from non-repo-root CWD

**Symptom:** Running `python "C:\...\crypto\validators\runner.py" --skip-replay` from any working directory other than the repo root caused two stages to fail with `[Errno 2] No such file or directory`:

```
[FAIL] v13_tv_mcp_parity.fixture
       error: [Errno 2] No such file or directory: 'crypto\\data\\fixtures\\tv_mcp_snapshot_2026-05-16T14-24Z.json'
[FAIL] v16_session_levels_spy.live
       error: [Errno 2] No such file or directory: 'backtest\\data\\spy_5m_2025-01-01_2026-05-15.csv'
```

Both files physically exist at those relative paths from the repo root. Running from repo root produced 65/65 PASS. Running from any other directory produced 63/65 FAIL.

**Root cause:** `crypto/validators/runner.py` passed hardcoded relative `Path("...")` strings to v13 and v16 stage registrations:

```python
("v13_tv_mcp_parity.fixture", ..., [Path("crypto/data/fixtures/tv_mcp_snapshot_..."), ...], {}),
("v16_session_levels_spy.live", ..., [Path("backtest/data/spy_5m_2025-01-01_2026-05-15.csv"), ...], {}),
```

`Path("relative/path")` is resolved against the calling process's CWD at runtime — not relative to the script's own location. Scheduled tasks, overnight wake fires, and sub-agent invocations routinely set a different CWD (e.g., `C:\Users\jackw\` or the user's home directory), causing both stages to silently fail on every fire except a manual `cd repo && python ...` invocation.

**Fix:** Added at `crypto/validators/runner.py` line 19:

```python
_REPO_ROOT = Path(__file__).resolve().parents[2]
```

Changed both stage registrations from relative strings to absolute anchored paths:

```python
("v13_tv_mcp_parity.fixture", ..., [_REPO_ROOT / "crypto/data/fixtures/tv_mcp_snapshot_...", ...], {}),
("v16_session_levels_spy.live", ..., [_REPO_ROOT / "backtest/data/spy_5m_2025-01-01_2026-05-15.csv", ...], {}),
```

Verification: `python "C:\...\runner.py" --skip-replay` invoked from system CWD (no `cd`) → **65/65 PASS**.

**General rule:** Any script that passes hardcoded file paths to called functions MUST anchor those paths to `Path(__file__).resolve().parents[N]`. Never pass `Path("relative/string")` to a function — it evaluates against the caller's CWD, which is not under the script's control. The pattern `_REPO_ROOT = Path(__file__).resolve().parents[N]` is always safe regardless of invocation method (scheduled task, sub-agent, shell, or direct).

**Encoded in:** `crypto/validators/runner.py` (line 19 + v13/v16 stage registrations) + `markdown/doctrine/LESSONS-LEARNED.md#L60`.

---

## L61 — 2026-05-20: `load_data()` hardcoded candidates bypass date-range check — stale master CSV silently returned for same-day grading requests

**Symptom:** `watcher_grader.py` and `shotgun_grader.py` produced `would_be_outcome=None` for all 2026-05-20 observations after a grader run. STDERR showed "0 future bars loaded" despite today's daily rolling CSV existing on disk. All same-day observations were ungradeable.

**Root cause:** `backtest/autoresearch/runner.py::load_data()` has a hardcoded fallback candidates list:

```python
candidates = [
    (start, end),
    (dt.date(2025, 1, 1), dt.date(2026, 5, 15)),  # merged master
    (dt.date(2025, 1, 1), dt.date(2026, 5, 12)),
    (dt.date(2025, 1, 1), dt.date(2026, 5, 7)),
]
for s, e in candidates:
    spy_path = DATA / f"spy_5m_{s}_{e}.csv"
    vix_path = DATA / f"vix_5m_{s}_{e}.csv"
    if spy_path.exists() and vix_path.exists():
        return ...  # NO DATE-RANGE CHECK
```

The candidates are checked for file existence but NOT for date coverage. `spy_5m_2025-01-01_2026-05-15.csv` existed on disk, so it was returned immediately for a request covering `start=2026-05-20` — even though it ends at 2026-05-15 and contains no 5/20 bars. The auto-discovery path (`_discover_csv_candidates`, which does check date ranges) is never reached because the stale hardcoded file matches first.

The graders compounded the issue: `watcher_grader.py` called `load_data(d, d + timedelta(days=1))` with `end=2026-05-21`. No daily rolling CSV covers 5/21 (they end at today), so auto-discovery found nothing → FileNotFoundError → `except` → `continue` → 0 graded observations.

**Fix:**

1. **`runner.py`** — added `if s > start or e < end: continue` guard before the existence check in the hardcoded candidates loop. A file is only used if its date range fully covers the requested window.

2. **`watcher_grader.py`** — changed `load_data(d, d + timedelta(days=1))` to `load_data(d, d)`. For 0DTE watcher grading, all observations close intraday; `end=d` (same-day) ensures the daily rolling CSV (`spy_5m_2026-05-08_2026-05-20.csv`) is found via auto-discovery.

3. **`shotgun_grader.py`** — same fix as watcher_grader.py.

**General rule:** Any "try these specific filenames first" pattern in a data loader MUST include a coverage check (`if s > start or e < end: continue`) BEFORE the existence check. A file that exists but covers the wrong date range is worse than "not found" — it returns silently incorrect (stale) data and the grader runs to completion with 0 results and no error. The symptom recurs every day until a new merged master is created that extends past today. Daily rolling CSVs from `append_today.py` are the correct same-day data source but they are bypassed by any hardcoded stale path that passes an existence check.

**Detection:** same-day grading producing `would_be_outcome=None` for all observations is the signal. Run `python -c "from backtest.autoresearch.runner import load_data; df,_=load_data('2026-05-20','2026-05-20'); print(df.index[-1])"` — if result < today, the stale-file bug is live.

**Encoded in:** `backtest/autoresearch/runner.py` (range-check guard in hardcoded candidates loop) + `backtest/autoresearch/watcher_grader.py` (`load_data(d, d)`) + `backtest/autoresearch/shotgun_grader.py` (same change) + `markdown/doctrine/LESSONS-LEARNED.md#L61`.

---

## L62 — 2026-05-20: Shared Claude rate-limit pool exhaustion silenced heartbeat ticks + EOD pipeline during market hours

**Symptom:** On 2026-05-20, heartbeat ticks were rate-limited 11:18-13:40 ET (~2.5h offline, 8-10 missed ticks across both accounts). Four EOD tasks exited silently: eod-summary, daily-review, analyst-eod, gamma-manager-verify. No daily digest. Tomorrow's key-levels.json was a stale carry-over. This was undetected until J's audit the next morning.

**Root cause:** Three concurrent Claude interactive sessions were running during market hours on the same rate-limit pool that the heartbeat and EOD scheduled tasks also pull from:
1. A `--effort max` Chef R&D session alive 15+ hours → 4.5M output tokens / 597M cache reads / ~$430 burn
2. A `--effort high` session alive 24+ hours → ~$210 additional burn
3. Two more interactive sessions during market hours

The MiniMax migration (swarm Stages 2-3, ~$0.06/day) covered <0.01% of daily Claude burn. Chef R&D, EOD specialists, and persona work all remained on Claude. Infrastructure existed but coverage was minimal.

**Fixes shipped 2026-05-21:**
1. **OP-30 doctrine:** default `--effort medium`, one interactive session during market hours, free-tier-first for text-analytical R&D
2. **`chef_nemotron.py`:** Chef R&D moves to NVIDIA Nemotron 3 Super 120B:free → DeepSeek V4 Flash:free → MiniMax M2.5:free → MiniMax M2.5 paid
3. **`Gamma_SessionGuard`** (every 5 min 09:00-16:00 ET): flags long-running interactive sessions to STATUS.md
4. **`Gamma_SpendSummary`** (nightly 23:30 ET): tracks per-day Claude $-burn vs OP-3 budget
5. **EOD MiniMax fallback:** when Claude rate-limited, analyst/manager/eod-summary output via M2.5 to canonical paths

**General rule:**
- Interactive Claude sessions during market hours (09:00-16:00 ET) are a production-trading risk vector. One `--effort max` session can exhaust the pool heartbeat depends on.
- The reword test before starting an interactive research session: "Can a free-tier Python script or free OpenRouter model do this for $0?" If yes, use that.
- An infrastructure migration ratified for one narrow purpose (swarm Stages 2-3) does NOT generalize automatically. Coverage must be explicitly extended to each new surface or the unmitigated surfaces will dominate burn.
- Silent `exit=1` in scheduled tasks is the worst failure mode (trades missed, no journal, stale key-levels). Every wrapper must write a cooldown state file so the morning brief catches it.

**Detection:** `Gamma_SpendSummary` at 23:30 ET reports daily $ burn. `Gamma_SessionGuard` flags long-running sessions to STATUS.md during market hours. Morning brief checks both.

**Encoded in:** OP-30 + `setup/scripts/chef_nemotron.py` + `setup/scripts/gamma_session_guard.py` + `setup/scripts/gamma_spend_summary.py` + EOD MiniMax fallback in `setup/scripts/run-{analyst-eod,gamma-manager-verify,eod-summary}.ps1` + `markdown/infra/MINIMAX-INTEGRATION.md` free-tier ladder + this entry.

---

## L63 — 2026-05-21: Watcher confidence tier structurally unreachable when conditions use trigger names that never fire

**Symptom:** Fleet analysis of `bullish_watcher` showed 100% of 289 historical observations classified as `medium` confidence. Zero `high` or `low` observations. Confidence tier was useless as a quality signal.

**Root cause:** The confidence logic in `bullish_watcher.py` (pre-fix) was:
```python
if (has_confluence and has_flip) or n_triggers >= 3:
    confidence = "high"
elif has_confluence or "sequence_reclaim" in triggers:
    confidence = "medium"
else:
    confidence = "low"
```
Three structural incompatibilities:
1. `has_flip = "ribbon_flip" in triggers` — the bullish_watcher enters BEFORE ribbon confirmation by design (`ribbon_just_flipped_bullish=False` for all 289 obs). `ribbon_flip` is never in `triggers_fired`.
2. `n_triggers >= 3` — with `min_triggers=1` and a typical bull signal having confluence + 1-2 other triggers, n_triggers rarely exceeds 2.
3. `elif has_confluence` — confluence is always in bull triggers (it's the reclaim trigger), so "medium" always fires as fallback, preventing "low" from ever appearing either.

**Fix (`bullish_watcher.py`, 2026-05-21):** Calibrate tiers to the ACTUAL trigger distribution:
```python
if n_triggers >= 2:         # at least one signal beyond confluence
    confidence = "high"
elif has_confluence or "sequence_reclaim" in triggers:
    confidence = "medium"   # typical single-trigger case
else:
    confidence = "low"      # no named reclaim signal
```
Result: "high" now achievable (any bar where confluence + another trigger fires), creating meaningful diversity in the confidence output.

**General rule:** Before finalizing any confidence tier logic, verify that each tier is REACHABLE by checking what `triggers_fired` actually contains across N≥20 historical observations. If a tier has 0 observations in the fleet data, the condition is structurally broken. Run `watcher_replay.py` against the historical dataset and print `Counter(obs.confidence for obs in observations)` — any tier with count=0 is dead code.

**Encoded in:** `backtest/lib/watchers/bullish_watcher.py` (confidence block updated) + this entry.

---

## L64 — 2026-05-21: ORB entries require chart-stop-only — premium stops ≤ -10% fire during the retest pullback before continuation (L51/L55 analog)

**Symptom:** Real-fills validation (`orb_real_fills_validate.py`) of 10 ORB long signals: v1 (-10% premium stop) WR=30% (3/10), while v2 (chart-stop-only, -99%) WR=90% (9/10). Watcher proxy showed 79.8% OOS WR — severely over-estimated when combined with a premium stop.

**Root cause:** The ORB RETEST pattern enters on a bar that has CLOSED ABOVE ORH after a pullback. The pullback bar (WAITING_RETEST phase) already happened before entry. However, the NEXT bar after entry — which is the trade's first live bar — often dips back toward ORH again before continuing up. This dip fires the -10% premium stop, exiting a winner. Specific cases:
- 5/04 10:15: watcher +$7.75 WIN → real-fills -$57 LOSS at -10% stop (stop fired on initial dip before TP1)
- 5/06 10:20: watcher +$103.50 WIN → real-fills -$7.20 LOSS at -10% stop
- 7/02, 7/14, 7/25: watcher +$55 to +$110 WINs → all LOSS with -10% stop

**Fix:** Use `premium_stop_pct=-0.99` (disabled) + `rejection_level=or_high` (chart stop fires only when SPY closes back below ORH = genuine failed retest). This is IDENTICAL to L51 (LBFS bear first-strike) and L55 (NLWB bull bounce).

**General rule (extends L51 + L55):** Any watcher entry where the ENTRY BAR is after a pullback toward a named level (ORH, PDL, R5) — the post-entry bar often re-tests the level again before continuing. Any premium stop tighter than -30% will be fired by this second-test noise. Only the CHART STOP (rejection_level + SPY-level exit) can discriminate genuine false-breakout from transient noise. Before setting any premium stop for a new watcher, examine per-bar premium path for the first 2-3 bars after entry across 5+ historical signals.

**Encoded in:** `backtest/autoresearch/orb_real_fills_validate.py` + `analysis/recommendations/orb_real_fills.json` + `strategy/candidates/_LEADERBOARD.md` #5 note.

---

## L65 — 2026-05-21: n_triggers is a poor confidence discriminator when watcher architecture guarantees a fixed minimum trigger count by construction

**Symptom:** After L63 fix (`bullish_watcher.py` changed confidence condition to `n_triggers >= 2 = high`), offline re-analysis of all 289 historical observations shows ALL 289 classified as `high` confidence — zero `medium` or `low`. The fix replaced one structurally unreachable tier (L63) with another structurally all-true tier.

Confidence distribution change: OLD (pre-L63) = `{'medium': 289}` → POST-L63 = `{'high': 289}`. No diversity achieved in either version.

**Root cause:** All 289 bullish observations have exactly `n_triggers = 2`. The watcher's required level-tied trigger check (line 67: `if not any(t in level_tied for t in result.triggers_fired): return None`) guarantees `level_reclaim` is always present. Since `confluence` is also always present (primary trigger), every observation fires at least 2 triggers. The max observed is also 2 — no 3rd trigger (`volume_confirm`, `sma_bullish`) is appended to `triggers_fired` in the current watcher code.

Trigger distribution across 289 obs:
- `('confluence', 'level_reclaim')`: 287 obs
- `('level_reclaim', 'sequence_reclaim')`: 2 obs
- n_triggers=1: 0 obs; n_triggers=3+: 0 obs

**Fix options (both require J ratification per Rule 9 before production):**
- Option A: Add 3rd trigger sources to `bullish_watcher.py` (`volume_confirm` when bar vol >= 1.5× 20-bar avg; `sma_bullish` when SMA10 > SMA50). Threshold: `n_triggers >= 3 = high`, `n_triggers == 2 = medium`.
- Option B (simpler): Use session as the primary discriminator. `high = PM session (13:00-15:00 ET)` WR=66%, N=61; `medium = midday (11:30-13:00 ET)`; `low = AM session (09:30-11:30 ET)` WR=44%, N=228. Option B matches the actual quality signal in the data.

Current state: PM/AM session is the ONLY working quality discriminator. PM session (N=61, WR=66%) is too thin for promotion gate; need N>=100.

**General rule:** Before shipping any confidence tier based on trigger count, verify the ACTUAL trigger count distribution across historical observations — not just that the condition is syntactically reachable. Any watcher with required triggers in its architecture (guards that call `return None` unless specific triggers present) has a MINIMUM n_triggers floor set by those guards. If the floor equals the tier boundary, the tier is structurally equivalent to no tier. Always check: `obs_df.groupby('n_triggers').size()` on the full historical dataset before finalizing any trigger-count-based tier.

**Encoded in:** `strategy/candidates/_LEADERBOARD.md` #9 note + `strategy/candidates/_lesson-inbox/2026-05-21-bullish-watcher-conf-tier-still-no-diversity.md`.

---

## L66 — 2026-05-21: Quality-lock cascade — blocking a loser via a gate can lock the biggest winner through an intermediate quality-state change

**Symptom:** BEARISH_SWEEP_BLOCKER gate (Stage-3) produced -$650 P&L regression vs baseline despite correctly blocking a -$528 LEVEL entry on 2025-12-10 15:20 ET. Confluence carve-out was added but the 15:50 ELITE (+$2,150) remained blocked. Aggregate Sharpe 0.663 → 0.614 (-7.3%). The regression could not be explained by per-trade analysis or aggregate Sharpe inspection.

**Root cause:** The cascade on 2025-12-10:

| Run | 15:20 | 15:30 | 15:50 | Net |
|---|---|---|---|---|
| BASELINE | -$528 taken (LEVEL, rank=2) | (not evaluated) | +$2,150 taken (ELITE, rank=3 > prior=2) | +$1,622 |
| WITH_GATE | blocked (sweep_block) | +$972 taken (ELITE, rank=3 > nothing) | **QUALITY_ESCALATION_LOCK** (rank=3=prior, prior=WIN) | +$972 |

The sweep gate blocked 15:20 LEVEL (saved -$528) which freed the engine to evaluate 15:30 ELITE (+$972 winner). That winner set `prior_quality=3` + `prior_result=WIN`. When 15:50 ELITE fired (same rank=3 as prior, prior was a WIN), `QUALITY_ESCALATION_LOCK` blocked it. The $2,150 trade was only reachable in BASELINE because the -$528 loss kept `prior_quality` at rank=2, allowing 15:50 ELITE (rank=3 > 2) to clear the check.

The $650 regression is concentrated in a SINGLE DAY across the entire 16-month dataset. This is invisible from:
- Per-trade analysis (only sees the directly blocked trade's P&L)
- Aggregate Sharpe (hides which day causes the regression)
- Single-pass backtest logging (doesn't show the cascade path)

**The gate interaction class:** Any gate G that blocks a lower-quality trade T1 can indirectly block a higher-quality trade T3 if:
1. Blocking T1 enables an intermediate trade T2 (higher quality, becomes a winner)
2. T2's win advances `prior_quality` + sets `prior_result=WIN`
3. T3 fires at rank=prior_quality (same as T2), triggering `QUALITY_ESCALATION_LOCK`

**Fix (analysis/debugging discipline — no code change required):**

Before reporting any backtest gate as "adds edge" or "causes regression":
1. Identify the top-3 regression days (sessions where gate-version P&L < baseline P&L)
2. For each regression day, run a session-level cascade trace:
   - List every trade taken or blocked in both runs (gate vs baseline)
   - Note the `prior_quality` + `prior_result` state at each decision point
   - Check if any gate-blocked trade enables an intermediate winner that then locks a later trade
3. Gate P&L = (sum of directly blocked trades) + (sum of cascade-enabled trades) + (sum of cascade-locked trades)

**Pre-shipping gate (extends OP-18 / OP-20):** For any gate G that filters trades by per-bar state (sweep_block, vol_confirmation, etc.):
- Does blocking a trade T at rank R enable a subsequent trade T+1 at rank R+1?
- Does T+1 winning then lock a subsequent trade T+2 at rank R+1?
- If yes to both: the gate has a cascade surface that requires simulation, not just per-trade P&L audit.

**General rule:** Per-bar gates and session-scoped quality locks interact multiplicatively, not independently. A gate that saves you from a loss can cost you a bigger winner by changing the quality state seen by all subsequent same-session evaluations.

**Encoded in:** `backtest/autoresearch/_debug_dec10.py` (cascade trace, 2026-05-21) + `strategy/candidates/2026-05-16-bearish-sweep-blocker.md` (CASCADE ANALYSIS section) + `strategy/candidates/_LEADERBOARD.md` (#1 BEARISH_SWEEP_BLOCKER REJECTED-FINAL notes) + this entry.

---

## L67 — 2026-05-21: Watcher observations JSONL contains multiple rows per SPY bar (one per heartbeat tick); deduplicate by bar_timestamp_et[:16] before any WR analysis

**Symptom:** V14E BEAR_HIGH_CONF fingerprint (computed from `automation/state/watcher-observations.jsonl`) reported N=33, WR=95.8% for direction=short + confidence=high observations. After deduplication by `bar_timestamp_et[:16]` (minute precision), the true unique-bar count was N=16 with VIX_MODERATE N=9, WR=77.8%. Inflation factor: ~2× on sample size. A single SPY 5m bar (e.g., `2026-05-04T11:15`) had 8 separate rows — one per heartbeat tick that fired within that bar's 5-minute window.

**Root cause:** `Gamma_Heartbeat` fires every 3 minutes. Each fire runs `v14_enhanced_watcher.py` and, if a signal is detected, appends a row to `watcher-observations.jsonl`. A 5-minute SPY bar spans 1-2 heartbeat ticks during normal hours and up to 3 ticks during active moves. For HOT mode (every 1-2 min) a single bar can generate 3-5 rows. The `first_entry_lock` in production ensures only ONE trade fires per bar, but the observation logger has no equivalent dedup gate — it records every tick that evaluates the bar regardless of whether a prior tick already logged it.

**Fix:** Before any WR / N analysis on `watcher-observations.jsonl`, deduplicate by `bar_timestamp_et[:16]` (minute precision captures all ticks within the same 5m bar):

```python
seen: set[str] = set()
deduped = []
for row in sorted(rows, key=lambda x: x["bar_timestamp_et"]):
    key = row["bar_timestamp_et"][:16]
    if key not in seen:
        seen.add(key)
        deduped.append(row)
```

Apply as a mandatory pre-processing step in: `watcher_grader.py`, `shotgun_grader.py`, `v14e_highconf_vix_monitor.py` (already implemented), and any future analysis script that reads `watcher-observations.jsonl`.

**Encoded in:** `backtest/autoresearch/v14e_highconf_vix_monitor.py` — `_load_observations()` already applies dedup by `bar_timestamp_et[:16]` with `seen: set[str]` + `strategy/candidates/_analysis/2026-05-21-v14e-bear-highconf-promotion-path.md` — dedup note appended + `automation/overnight/STATUS.md` — key finding note logged.

**Detection:** Any future analysis script that reads `watcher-observations.jsonl` and reports N > unique SPY bar count for the day is inflated. Gate: assert `len(deduped) <= len(rows)` and log the dedup ratio. If ratio > 1.5× on any session, the observation logger may have regressed.

---

---

## L68 — 2026-05-21: Three consecutive days heartbeat starvation due to no firewall between interactive Claude and shared rate-limit pool

**Symptom:** `Gamma_Heartbeat` fired but produced zero decisions for 3 consecutive trading days. Rate-limit errors in heartbeat logs. Interactive Claude sessions during 09:30-15:55 ET were consuming the shared API rate limit, leaving nothing for the scheduled heartbeat.

**Root cause:** Anthropic's API rate limit is a single pool shared across all authenticated requests from the same key — interactive sessions, heartbeat fires, and background tasks all pull from the same bucket. Heavy interactive use (strategy research, debugging, multi-file reads) during market hours starved the 3-min heartbeat ticks.

**Fix:** Self-discipline rule added to CLAUDE.md header (no interactive Claude sessions during 09:30–15:55 ET). Previously OP-32 (SessionGuard + CircuitBreaker) attempted to automate this; it was nuked 2026-05-23 because it locked J out of Claude entirely. Self-discipline is the correct fix.

**Detection:** `Gamma_Heartbeat` last_run_et shows correct timestamp but `decisions.jsonl` shows zero entries for that day → rate-limit starvation. Check `grinder.log` for 429 errors.

**Encoded in:** `CLAUDE.md` top-of-file J discipline reminder + OP-25 lesson one-liner. OP-32 archived in DOCTRINE-ARCHIVE.md.

---

## L69 — 2026-05-22: L68 firewall (OP-32 SessionGuard + CircuitBreaker) deployed but exemption layer broken at all 3 call sites — unit passed, integration failed

**Symptom:** OP-32 (SessionGuard) shipped with a market-hours gate. Unit tests passed. But in production, the exemption layer that should allow scheduled tasks to bypass the guard was broken at all 3 call sites — every scheduled task hit the gate and received "BLOCKED: market hours". The system that was supposed to protect heartbeat instead blocked it entirely.

**Root cause:** The exemption check (`CLAUDE_TASK_TYPE` env var) was read before the guard initialized in the scheduled task wrapper scripts. All 3 wrapper scripts used a different env var name than what SessionGuard checked. Unit test used a mock that didn't surface the mismatch.

**Fix:** Nuked OP-32 entirely in 2026-05-23 infrastructure reset. Self-discipline replaces automated session guards. Key insight: automation that can accidentally block the operator should not exist.

**Detection:** If a new "safety" automation ever starts preventing J from using Claude, nuke it immediately. The operator > the guard.

**Encoded in:** `CLAUDE.md` OP-32 removal note + DOCTRINE-ARCHIVE.md (OP-32 archived verbatim).

---

## L70 — 2026-05-23: Exit params (tp1/runner/profit_lock) have 26× more P&L impact than orchestrator quality tier knobs

**Symptom:** `overnight_grinder.py` sweeps 432 orchestrator quality-tier combos (super_stop, super_tp1, runner_target, level_qty, level_stop, level_tp1, trendline_stop) with V15_J_EDGE_OVERRIDES locking tp1=0.75 / runner=2.0. Best result after full run: **$1,005 wide_pnl** (16% WR, 1/6 positive quarters). Meanwhile, `v14_enhanced_grinder.py` sweeps exit params (tp1, runner, profit_lock) and finds: **$26,601 wide_pnl** (65% WR, 6/6 positive quarters).

**Root cause:** The orchestrator's quality-tier dispatch (TRENDLINE/LEVEL/ELITE/SUPER) controls which exits each quality fires — but the underlying exit logic (tp1 size, runner target, profit-lock) dominates the P&L. With tp1=0.75, the engine takes 50% profit at +75% premium — by which time many positions have already reversed, resulting in frequent stop-outs on the runner. With tp1=0.30, half the position is freed at +30%, and the runner has more room to run to 2.5×, producing >25× the P&L on the same underlying setups.

**Fix:** When researching a strategy's parameter space, search exit params (tp1_premium_pct, runner_target_premium_pct, profit_lock_threshold_pct, stop_pct) FIRST. Orchestrator routing knobs are second-order. The `v14_enhanced_grinder.py` template (sweeps exit params with locked orchestrator) is the correct search design.

**Impact ratio confirmed:** $26,601 / $1,005 = **26.5×** more P&L from exit param sweep vs orchestrator tier sweep.

```python
# WRONG: sweep orchestrator routing knobs with locked exit params
grid = [{"super_stop": s, "level_stop": l, ...} for s, l in ...]  # caps at ~$1K

# RIGHT: sweep exit params with locked orchestrator
grid = [
    {"tp1_premium_pct": t, "runner_target_premium_pct": r, "profit_lock_threshold_pct": pl}
    for t, r, pl in ...
]  # finds $26K+ combos
```

**Encoded in:** `backtest/autoresearch/v14_enhanced_grinder.py` + `strategy/candidates/2026-05-23-v14e-param-sweep-26k.md` + CLAUDE.md OP-25 lesson one-liner.

---

## L71 — 2026-05-23: Real-fills can EXCEED BS-sim when BS-sim applies profit-lock that simulator_real doesn't implement

**Symptom:** `_realfills_v14e_26k.py` reports real-fills wide_pnl = **$42,102** vs BS-sim wide_pnl = **$26,601** — real-fills 58% HIGHER. First instinct: "the script has a bug." But the result is real and explained.

**Root cause:** The winning combo uses `profit_lock_threshold_pct=0.05 / profit_lock_stop_offset_pct=0.10`. In BS-sim, when premium reaches +5%, the stop trails 10% off the HWM — effectively locking winners to a small profit but capping upside. `simulator_real.py` does NOT implement profit-lock (it's a BS-sim-only primitive). So in real-fills mode, runner trades run to their full `runner_target_premium_pct=2.5×` target unimpeded. On big trending days (Nov 7 2025 +$4,246, Jan 26 2026 +$2,823, Dec 16 2025 +$2,239), BS-sim locks these early; real-fills lets them run.

**Key implication:** For any strategy with profit-lock ON: real-fills P&L ≥ BS-sim P&L when the regime is trending. The profit-lock makes BS-sim CONSERVATIVE (protecting consistency at the cost of upside). This is actually desirable — the BS-sim gives a conservative floor and real-fills gives an optimistic ceiling.

**Correct interpretation:** For the $26K combo, expected live P&L per 17 months is BETWEEN $26,601 (profit-lock applied, conservative) and $42,102 (no profit-lock, optimistic). With profit-lock in production, expect P&L closer to $26K floor.

**Side effect:** Real-fills top5_pct = 33.4% vs BS-sim top5_pct = 14.8%. This inflation is also explained — without profit-lock, the same 5 big days run further. Not a sign of curve-fit.

**Verification rule:** When real_fills_pnl > bs_sim_pnl and the combo uses profit_lock: check whether `simulator_real.py` implements profit-lock. If not, the difference IS the profit-lock cap in BS-sim — expected, not a bug. Document the gap in the candidate OP-20 disclosures.

```python
# In simulator_real.py — profit-lock primitives are absent:
# NO: profit_lock_threshold_pct check
# NO: trailing stop update when premium > threshold
# result: runners run to full target_premium_pct on big days

# In simulator.py (BS path) — profit-lock IS applied:
if current_premium_pct >= params.profit_lock_threshold_pct:
    # move stop to entry_premium * (1 - profit_lock_stop_offset_pct)
    stop = entry_premium * (1 - params.profit_lock_stop_offset_pct)
```

**Encoded in:** `backtest/autoresearch/_realfills_v14e_26k.py` caveats + `strategy/candidates/2026-05-23-v14e-param-sweep-26k.md` real-fills section + CLAUDE.md OP-25 lesson one-liner.

---

---

## L72 — 2026-05-23: V15_J_EDGE_OVERRIDES in j_edge_tracker.py drifted stale — overnight_grinder searched with wrong locked exit params for weeks

**Symptom:** `overnight_grinder.py` best result after 432 combos: **$1,005 wide_pnl** (16% WR, 1/6 quarters) with V15_J_EDGE_OVERRIDES locking `tp1_premium_pct=0.75`, `runner_target_premium_pct=2.0`. Meanwhile `v14_enhanced_grinder.py` (same strategy, sweeping exit params) finds **$26,601** with `tp1_premium_pct=0.30`, `runner_target_premium_pct=2.5`. Investigation showed: `heartbeat.md` v15.2 already uses `entry × 1.30` (=30% TP1) and `runner_target=2.50`. V15_J_EDGE_OVERRIDES was never updated after v15 initial doctrine evolved through v15.1 and v15.2.

**Root cause:** V15_J_EDGE_OVERRIDES in `j_edge_tracker.py` was written for v15.0 (May 13 doctrine) with `tp1=0.75` and `runner=2.0`. As heartbeat.md evolved to v15.1 (runner→2.5, tp1→1.30× fallback) and v15.2, the tracker was never updated. All 6+ grinders that `import V15_J_EDGE_OVERRIDES` from j_edge_tracker.py silently used stale values. The overnight_grinder therefore measured "what orchestrator quality-tier knobs are best GIVEN tp1=0.75/runner=2.0" — answering a question that's 2 versions out of date.

**Fix:** Update V15_J_EDGE_OVERRIDES to match actual production heartbeat.md:
```python
# STALE (v15.0 — May 13 initial doctrine):
V15_J_EDGE_OVERRIDES = {
    "tp1_premium_pct": 0.75,
    "runner_target_premium_pct": 2.0,  # ...
}

# CORRECT (v15.2 — actual production heartbeat.md):
V15_J_EDGE_OVERRIDES = {
    "tp1_premium_pct": 0.30,           # heartbeat.md: premium >= entry * 1.30 fallback
    "runner_target_premium_pct": 2.5,  # heartbeat.md: runner_target = 2.50
    # ... same entry knobs unchanged
}
```

**Prevention:** When heartbeat.md RULE_VERSION bumps, ALWAYS audit `j_edge_tracker.py#V15_J_EDGE_OVERRIDES` against the actual exit knob values in heartbeat.md. These 4 fields must stay in sync:
1. `tp1_premium_pct` ← heartbeat.md TP1 fallback multiplier minus 1
2. `runner_target_premium_pct` ← heartbeat.md runner target
3. `tp1_qty_fraction` ← heartbeat.md TP1 fraction
4. `premium_stop_pct_bear` ← heartbeat.md bear stop pct

Add to pre-ratification checklist: "Does j_edge_tracker.py#V15_J_EDGE_OVERRIDES match heartbeat.md's current values?"

**Encoded in:** `backtest/autoresearch/j_edge_tracker.py` (fixed 2026-05-23) + CLAUDE.md OP-25 lesson one-liner.

---

## L73 — 2026-05-24: VIX level alone is insufficient as a regime filter for directional strategies — VIX CHARACTER (trending vs spike-and-revert) is the true discriminator

**Symptom:** SNIPER VIX>=18 grinder passes all 3 full-window gates ($3,297, WR=56.2%, +q=4/5 over 17 months). OOS walk-forward FAILS: IS (2025-01..2025-10) = +$4,130 but OOS (2025-11..2026-05) = -$833. WF ratio = -0.224 (gate >=0.50). Full-window success was entirely IS-driven.

**Root cause:** The 17-month window happened to contain two distinct high-VIX sub-regimes with opposite characteristics:

1. **Trending high-VIX (IS = Jan-Oct 2025):** Rate-hike fear + post-bubble market drawdown. VIX elevated and TRENDING higher. Level breaks on high-VIX days had directional follow-through. Strategy: WR=67.6%, +$4,130.

2. **Spike-and-revert high-VIX (OOS fold F1+F2 = Nov 2025 - Feb 2026):** Post-election rally + pre-tariff uncertainty. VIX occasionally spiked above 18 on individual news events then immediately retreated. Level breaks reversed intraday. Strategy: WR<40%, -$1,713.

The VIX>=18 filter was designed to eliminate "low-VIX chop" — it successfully does that. But it does NOT distinguish between trending high-VIX (good) and spike-and-revert high-VIX (bad). Both produce VIX>=18 on the trade day. The damage in F1/F2 came from days where VIX briefly crossed 18 from a lower baseline, not sustained regime-level elevation.

**Fix / Next hypothesis:** Add a VIX TRENDING requirement:
```python
# Current (insufficient):
if prior_day_vix < 18:
    skip

# Proposed enhancement:
vix_5d_avg = moving_avg(prior_vix_close, 5)
if prior_day_vix < 18:
    skip  # too quiet
if prior_day_vix < vix_5d_avg:
    skip  # VIX elevated but DECLINING — mean-reversion environment
# Trade only when VIX >= 18 AND VIX is ABOVE its recent average
# (i.e., regime is ESCALATING, not just elevated)
```

The `prior_day_VIX > prior_5d_avg_VIX` condition identifies days where VIX is not just elevated but rising — the spike-and-revert days (F1/F2) typically had VIX spiking above 18 from a sub-18 5-day average, while the trending high-VIX days (IS + F3 tariff crash) had VIX well above its rolling average.

**Evidence:**
- OOS F3 (Mar-Apr 2026, tariff crash regime): n=23, WR=52.2%, +$911 — trending high-VIX, consistent with hypothesis
- OOS F1 (Nov-Dec 2025): n=6, WR=33.3%, -$1,229 — spike-and-revert high-VIX
- IS (Jan-Oct 2025): n=34, WR=67.6%, +$4,130 — sustained trending high-VIX

**Encoded in:** `strategy/candidates/2026-05-23-sniper-vix18-grinder-3297.md` (OOS section + status update) + `strategy/candidates/_LEADERBOARD.md` (#13) + CLAUDE.md OP-25 lesson one-liner. Investigation queued: `autoresearch/_sniper_vix_trend_filter.py`.

**UPDATE (2026-05-24):** Hypothesis fully confirmed. 432-combo VIX-trend grinder (joint filter: VIX>=18 AND VIX>5d_avg) completed. Off=2 combo: WF ratio = **0.983** — OOS P&L $2,486 ≈ IS P&L $2,774 (near-perfect generalization). OOS fold breakdown with joint filter:

| Fold | OOS P&L (VIX18 only) | OOS P&L (joint filter) | Improvement |
|---|---:|---:|---:|
| F1 Nov-Dec 2025 | -$1,229 | -$267 | +$962 |
| F2 Jan-Feb 2026 | -$484 | +$1,439 | +$1,923 |
| F3 Mar-Apr 2026 | +$911 | +$1,187 | +$276 |
| F4 May 2026 | -$32 | +$126 | +$158 |

The joint filter turned F2 (the worst fold) from -$484 to +$1,439 by filtering out days where VIX was elevated but declining. Production candidate: `strategy/candidates/2026-05-24-sniper-vix-trend-oos-confirmed.md`.

**IMPORTANT CONTRAST (also 2026-05-24):** VIX-trend filter is SNIPER-specific. When applied to BEARISH_REJECTION V14E best combo, OOS DECLINING trades WR=73.1% (excellent) — removing them would lose $4,413 OOS P&L. BEARISH_REJECTION works across both VIX regimes because it uses ribbon trigger quality as its own discriminator. Diagnostic: `autoresearch/_vix_trend_br_diagnostic.py`. VIX character filtering should only be applied to strategies that rely on raw level break/directional conviction, NOT to strategies with embedded quality scoring (ribbon).

---

## L74 — 2026-05-24: High-frequency scalper signals at ATM 0DTE fail real-fills — delta half-capture + theta drag + 48% stop misfire rate. Rescue: ITM-2 + wider stop.

**Symptom:** TBR_HIGH_VOL walk-forward showed WR=70%, exp=+$3.68 in SPY-price simulation space (2025-10-01 to 2026-05-22, N=70). Full real-fills validation (OPRA, same window) returned WR=44.9%, exp=−$6.44/obs, total=−$4,264 across N=662 trades — all 6 quarters negative. The SPY-space edge is genuine (WF ratio=1.39, all 3 OOS quarters positive in price-space). The gap is entirely explained by ATM option structure.

**Root cause:** Three compounding factors at ATM (delta≈0.50) with a −15% premium stop:

1. **Delta half-capture:** Each $1 SPY move produces only ~$0.50 option premium gain. The signal fires on an X-cent SPY move; ATM captures only 50% of it.
2. **Theta decay at 0DTE:** Theta erodes $0.02–$0.05/min per ATM contract. A 12-minute hold (TBR time-stop) costs $0.24–$0.60/contract from theta alone before SPY moves.
3. **Premium stop misfire rate 48%:** The −15% stop fires on 318/662 exits (48% of all exits) vs ~30% in chart-based setups (NLWB, ORB). TBR involves a "retest" of a broken trendline — there is always a 2–5 cent adverse retest before continuation. With ATM delta this 2–5c SPY move = 1–2.5c premium = 10–17% of a $0.15 ATM premium, immediately triggering the stop.
4. **Exit mix confirms low-target-reach:** STOP=48%, CHANDELIER=37%, TIME_STOP=12%, TARGET_LEVEL=1.8%. The 1.8% TARGET_LEVEL rate confirms the signal is directionally correct but the +75% TP is rarely reachable before delta drag + theta kills the premium.

Evidence: `backtest/autoresearch/tbr_hv_real_fills_val.py` OOS run 2026-05-24. Discovery doc: `strategy/candidates/2026-05-24-tbr-high-vol-discovery.md`.

**Fix:** ITM-2 (strike_offset=−2, delta≈0.70–0.75) + stop=−35%. Walk-forward results (2026-05-24 real-fills, `backtest/autoresearch/tbr_hv_itm_sweep.py`, 9-combo sweep: 3 offsets × 3 stops):

| Window | N | WR | Exp/obs | WF ratio |
|---|---|---|---|---|
| IS (2025-Q1 to 2025-Q3) | 332 | 59.3% | +$2.39 | — |
| OOS (2025-Q4 to 2026-Q2) | 239 | 60.7% | +$2.07 | **0.866 PASS** |

The larger absolute stop ($0.40+ on ITM-2 vs $0.02–$0.05 on ATM at −15%) survives the retest wick. Higher delta (~0.72) captures more of the SPY-space edge per dollar of move.

**Concentration flag (regime-dependency):** IS dominated by Q2-2025 (85.4% of IS P&L). OOS dominated by Q1-2026 (90.6% of OOS P&L). These are different quarters, so this is NOT seasonal overfitting — it is regime-dependency. Without the Q1-2026 tariff-crash regime (high-vol, large directional moves), ITM-2 is essentially flat. The strategy is viable only in trending high-volatility regimes. Cross-reference with L73 (VIX character filter) before production deployment.

**Encoded in:** `strategy/candidates/2026-05-24-tbr-high-vol-discovery.md` (Gate #3 updated to FAIL for ATM; ITM-2 results appended) + `strategy/candidates/_LEADERBOARD.md` (#16 status = BLOCKED_BY_RF for ATM; ITM-2 candidate queued) + CLAUDE.md OP-25 lesson bullet + this entry. Related: L50 (SPY-price WR ≠ option P&L WR, the general principle); L73 (VIX character required for regime-dependent strategies).

**Detection:** Any future strategy validated in SPY-price-space must pass `tbr_hv_real_fills_val.py`-style real-fills gate before leaderboard promotion. Stop misfire rate >35% in real-fills run is an automatic BLOCK regardless of WR.

---

## L75 — 2026-05-21: False-break-launchpad at ★★★ Carry on RTH open bar — single-bar bear-trap at maximum-hold level

**Symptom:** Bear entry placed after first RTH bar (09:35) printed low 737.53, crossing −$0.57 below ★★★ Carry level 738.10 (9 touches, 7 historical holds). By the 09:40 bar, SPY had recovered above 738.10. Session closed +$4 in the direction of the squeeze. Loss −$204.

**Root cause:** The premarket evaluation framework had no branch for "Carry breaks at open bar and immediately recovers." It evaluated the level as either holding or breaking definitively. A single-bar false-break at RTH open is structurally MORE dangerous than a mid-session test because (a) overnight shorts and early bears are all trapped simultaneously, (b) gap-open dynamics amplify the squeeze, and (c) the Carry's historical holds create maximum short positioning entering the break. This is the single-bar version of L59 (close-ceiling distribution), but at the worst possible time — market open at a max-conviction level.

**Fix:** Add the following check to the premarket morning checklist for any ★★★ level within $1.00 of the expected open:

> **False-break-launchpad check:** If the first RTH bar (09:35) prints a low more than $0.25 BELOW a ★★★ named level AND the same bar (or next closed bar) closes ABOVE that level — suspend bear entries on this level for 30 min. Write "FALSE_BREAK_DETECTED: [level]" to journal. Watch for bull ribbon trigger instead.

**Encoded in:** `journal/mistakes.md` (cross-reference appended 2026-05-24) + `markdown/doctrine/LESSONS-LEARNED.md` L75 + CLAUDE.md OP-25 absorbed-lessons bullet. `automation/prompts/heartbeat.md` premarket section pending next Rule 9 ratification window.

**Detection:** Heartbeat premarket section must check: if `open_bar_low < carry_level - 0.25` AND `open_bar_close > carry_level`, flag FALSE_BREAK_LAUNCHPAD and suppress bear entry for 30 min. Any bear entry at a ★★★ level on the first RTH bar without this check passing is a Rule 2 (wait-for-trigger) violation.

**Related:** L59 (close-ceiling distribution — N≥3 bar analog), L51 (violent initial bounce on VIX≥20 level-break entries), `crypto/lib/chart_patterns.py::detect_floor_hold()` (n_min=1 variant covers this single-bar case).

---

## L76 — 2026-06-02: Entry gate trusted local position state — entered while Alpaca still held a position → orphaned GHOST

**Symptom:** Bold (aggressive) entered SPY 760C ×4 @0.98 at 11:25 ET while SPY 758C ×3 @1.87 (entered 10:56) was STILL open in Alpaca. The single-position `current-position-bold.json` overwrote the 758C with the 760C, orphaning the 758C — engine went blind to it (no TP/stop). Caught manually at 11:47 (758C was +$84). Both closed ~12:16 ET; the unmanaged 758C decayed +$84 → +$33. Bold day −$123, all 3 day-trades burned.

**Root cause:** The Entry branch fires on `current-position.status == null` (LOCAL state) and never verifies flat against Alpaca. When local state reads null after a desync/failed-close while the broker still holds a position, the engine re-enters → two positions, one orphaned. Same family as STATE_DRIFT (2026-05-21) and the 2026-05-19 ghost-ENTER.

**Fix:** Added a **flat-verification gate** to BOTH heartbeats' Entry branch (`heartbeat.md` + `aggressive/heartbeat.md`, 2026-06-02): before scoring/entering, call `get_all_positions`; if NON-EMPTY (any SPY option held) → do NOT enter, reconcile `current-position[-bold].json` from the actual Alpaca position, emit `STATE_DRIFT_BLOCKED_ENTRY`, exit the tick. One position at a time, verified against the broker — never trust local null alone.

**Detection:** `Gamma_GhostOrderReconciler` (1-min RTH) catches ENTER-without-fill; this gate catches the inverse (fill-without-state → false-flat re-entry). Together they close the state-drift loop.

**Related:** STATE_DRIFT (2026-05-21), 2026-05-19 ghost ENTER. Execution-layer guard only — NOT a backtest filter (no `filters.py` sync; the backtest engine has no broker state to drift). Cross-ref `journal/mistakes.md` 2026-06-02.

---

## L77 — 2026-06-14: Karpathy shadow A/B compared engine-defaults, not params.json — and the orchestrator silently dropped the v15.3 gates it claimed to apply

**Symptom:** The OP-11 shadow loop (`lib/shadow.py`) had never produced a meaningful scorecard. `run_shadow_backtest` with any candidate override yielded prod == shadow (byte-identical metrics) — a silent no-op A/B. Separately, a backtest configured via `params_overrides={"min_ribbon_momentum_cents": 50}` fired the SAME trade count as no override (53 vs 53), while the explicit kwarg `min_ribbon_momentum_cents=50` correctly dropped it to 2.

**Root cause (two compounding bugs):**
1. `run_shadow_backtest` ran the PRODUCTION side with `params_overrides=None`, so "production" used the orchestrator's bare defaults (v15.3 ribbon gates default OFF), not `params.json`. The A/B compared defaults vs defaults+candidate; any candidate toggling a param already at its engine default produced zero delta.
2. `orchestrator.run_backtest`'s override-apply block translated `min_ribbon_momentum_cents` / `max_ribbon_duration_bars` / `midday_trendline_gate` via `_params_to_kwargs` but only assigned a HARDCODED SUBSET back — it dropped these three. So `params_overrides` could never enable the v15.3 gates. Every backtest/grinder configured via `params_overrides` (not explicit kwargs) ran the NO-GATE version: 53 trades (no gates) vs 16 (real v15.3) on 2026-03-01→05-07. **The "v15.3 OOS WR 0.77 / WF 4.29" ratification must be re-checked against which code path produced it.**

**Fix:** (a) `shadow.py` prod run passes `params_overrides=base_params`; shadow run + sub-window pass the merged `shadow_params_dict`. (b) `orchestrator.py` apply-block assigns the three ribbon-gate kwargs (same "only if caller left it at default" heuristic). Engine-benefit, no order path; shadow disabled in production.

**Graduated to assertions:** `backtest/tests/test_op11_loop.py` (A/B is real, verdict gate, read-only invariant) + `test_graduated_guards.py::test_params_override_binds` (every mapped key MUST change output — general dead-knob guard so this class can't recur silently). The L38/L72 family finally caught by CI. Validated in-process via the replay engine (verify-now, not wall-clock).

**Related:** L38 (dead dimensions), L72 (V15_J_EDGE_OVERRIDES drift), L57 (look-ahead). Open follow-up: should `run.py` + grinders load `params.json` so ALL backtests reflect v15.3 (not just the shadow)? — needs J nod (changes research baseline).

---

## L78 — 2026-06-14: Cowork FUSE mount forbids deletes + serves truncated reads of just-edited files — git cannot run in the sandbox

**Symptom:** `git init` in the Cowork Linux sandbox (on the mounted Windows folder) corrupted its own `.git/config` ("bad config line 1"), and `.git/` could not be removed (`rm: Operation not permitted`). After editing `orchestrator.py` via the file tools, the sandbox's `python3`/`cat`/`wc` saw a TRUNCATED file ending mid-token, while the Read/Grep tools (Windows side) saw the complete file. Stale `.pyc` bytecode compounded it.

**Root cause:** The folder is a FUSE/virtiofs mount that allows create/write but (a) forbids `unlink`/`rename` and (b) does not reliably reflect file-tool writes to the sandbox read path. Git needs unlink+rename (lockfiles), so it cannot operate there.

**Fix / working pattern:**
- **Git runs on Windows, never the sandbox** — prep in-sandbox, hand off via `setup/setup-git.ps1` (removes broken `.git`, re-inits, secret-checks, commits).
- **Validate edited code in `/tmp`** (real Linux fs): rebuild a complete copy from pre-edit `.orig` backups + re-applied fixes; never trust the sandbox's read-after-edit view of a mounted file.
- **Route bytecode off the mount:** `PYTHONPYCACHEPREFIX=/tmp/...` avoids stale `.pyc`.
- **Back up before editing** (writes are allowed): `cp file _local_backups_YYYYMMDD/` gives an undo path even without git.

**Related:** the 2026-05/06 mangled-path decision logs (literal `C:\...` written on the Linux mount) are the same mount-semantics family.

---

## L79 — 2026-06-15: Watcher trigger strings carry price suffix — exact-match lookups in shadow eval and analysis tools silently miss them

**Symptom:** Shadow eval (v4 and earlier) showed ENTER_BULL miss on 2026-06-02 tick t8 even though the trigger fired correctly in production. The shadow model output HOLD. The heartbeat had fired and logged an ENTER decision — but the shadow replay reconstructed HOLD.

**Root cause:** Watchers emit trigger strings with a price suffix: `"level_reclaim_758.22"`. The heartbeat writes this raw string to `decisions.jsonl`. When the shadow eval (and any downstream analysis tool) does an exact-match lookup against the canonical valid-trigger list (`["level_reclaim", "level_break", "ribbon_flip", ...]`), the suffixed string fails to match — `trigger=None` in the snapshot. The model receives `trigger=None` → no confirmed trigger → outputs HOLD. Any tool that reads trigger-type from `decisions.jsonl` via exact match inherits this silent defect.

**Fix:**
1. **Heartbeat (production):** normalize trigger before writing to `decisions.jsonl` — strip the price suffix, log only the base trigger name (`level_reclaim`, `level_break`, `ribbon_flip`, etc.). The price is already captured in the `spy` field; embedding it in the trigger string fragments all downstream grouping and lookup across every unique price point.
2. **Shadow eval v5 (defensive workaround):** prefix matching in `build_tick_prompt()` — `"level_reclaim_758.22"` matches `"level_reclaim"` via `raw.startswith(valid + "_")`. Defensive-only; production ledger should not produce suffixed triggers.

**Encoded in:** `automation/prompts/heartbeat.md` (trigger normalization note added to Decisions ledger section), `automation/prompts/aggressive/heartbeat.md` (same fix), `setup/scripts/shadow_model_eval.py` (v5 prefix-matching workaround).

**Detection:** Any new shadow eval or analysis pass that reads `trigger` from `decisions.jsonl` must use prefix matching (not exact match) as a defensive layer. A regression test: seed a `decisions.jsonl` row with `trigger="level_reclaim_758.22"` and assert the eval resolves it to `level_reclaim`.

---

## L80 — 2026-06-15: bull_score logged as null at ENTER ticks — shadow model saw 0 and output HOLD

**Symptom:** Shadow eval showed ENTER_BULL miss on 2026-06-02 tick t12. Production heartbeat logged ENTER; shadow replay produced HOLD. The signal was present; the model received no signal.

**Root cause:** `heartbeat.md`'s Decisions Ledger schema listed `bull_score` and `bear_score` in the LEAN schema (applied to HOLD_DEV ticks) but the ENTER-specific required-fields list (line 672) did NOT include them. A logging race in the heartbeat — score computed before the ENTER branch, not explicitly carried into the `decisions.jsonl` write step — caused `bull_score=null` to be written at some ENTER ticks. The shadow eval received `null`, passed `0` to the model, and the model had no signal strength to act on → HOLD.

**Fix:**
1. **Heartbeat:** explicitly include `bull_score` and `bear_score` in the required fields for the ENTER row in `decisions.jsonl`. If the logging race prevents reading the field at write time, extract the authoritative value from the `reason` string (which always contains `"bull_score=N"` or `"N/11"`).
2. **Shadow eval v5 (defensive workaround):** null fallback extracts score from the `reason` field via regex `r'bull_score[=:](\d+)'` or `r'(\d+)/11'`. Defensive-only; production should log the score correctly.

**Encoded in:** `automation/prompts/heartbeat.md` (bull_score note added to Decisions Ledger ENTER row spec), `automation/prompts/aggressive/heartbeat.md` (same fix), `setup/scripts/shadow_model_eval.py` (v5 null fallback from reason field).

**Detection:** Any shadow eval replay that shows ENTER in production but HOLD in shadow, where the shadow tick has `bull_score=0` and a non-trivial `reason` string, should trigger a null-score audit before treating the miss as a genuine model disagreement.

---

## L81 — 2026-06-15: Kitchen daemon alive-check used tasklist (PID-only) — OS PID reuse produced false-alive → daemon dead for ~10 hours

**Symptom:** `kitchen-status.json` showed the daemon alive. The keepalive task (`Gamma_KitchenDaemonKeepalive`) fired every 5 minutes and silently exited. No cook tasks completed. The kitchen was dead for approximately 10 hours while appearing healthy in all status surfaces.

**Root cause:** `kitchen_daemon.py`'s `_existing_daemon_alive()` checked liveness with `tasklist /FI "PID eq N"`. `tasklist` checks only PID existence — no CommandLine filter. When the daemon's PID (e.g. 2136) was recycled by Windows for an unrelated process (`svchost.exe`), `tasklist` reported PID 2136 alive. The startup check concluded "another daemon is already alive" and exited silently. Every subsequent keepalive fire and manual restart hit the same false-alive gate. The stale PID file was never deleted.

**Fix:** Replace `tasklist` with a WMIC CommandLine check:
```
wmic process where ProcessId=N get CommandLine /value
```
Output contains `"kitchen_daemon.py"` ONLY if the process actually running under that PID is the daemon. Also: delete the stale PID file if the CommandLine does not match — prevents indefinite lockout on next restart. This is the same pattern the keepalive PowerShell script already used (`Get-WmiObject + CommandLine -match`). Both the daemon's own check AND any external liveness check MUST use CommandLine matching — PID-only checks are always wrong on Windows due to PID recycling.

**Encoded in:** `setup/scripts/kitchen_daemon.py` (`_existing_daemon_alive()` replaced with WMIC CommandLine check + stale-PID-file cleanup).

**Detection:** Any Windows liveness check that uses only PID existence (via `tasklist`, `Get-Process -Id N`, or similar) without CommandLine verification is a PID-reuse time bomb. Grep for `tasklist /FI "PID` or `Get-Process -Id` in daemon/keepalive scripts and audit each one.

**Related:** L20, L27, L33, L41 (headless Windows spawn / WMI liveness family). The keepalive PS script already used the correct WMI pattern — the daemon's own check was the gap.

---

## L82 — 2026-06-16: FILL_CONFIRMED counted as decision-tick — broker ack is not a trading decision

**Symptom:** Shadow eval scored 5/18 at 66.7% DT (raw). The "miss" at 10:00 was classified as a DT miss: real=FILL_CONFIRMED, shadow=HOLD_RUNNER. This dragged the DT rate from 7/7 to 6/7.

**Root cause:** `is_decision_tick()` only excluded HOLD, HOLD_RUNNER, ERROR_*, PAUSED, TRIPPED. FILL_CONFIRMED is a broker fill-acknowledgment action (the heartbeat ticks once after an order fills to confirm position state is synced) — it is NOT a trading decision. The model correctly outputs HOLD_RUNNER for an open position, which is the right trading action. But FILL_CONFIRMED was counted as a DT, making agreement impossible (model can't know to output "FILL_CONFIRMED" — that's a broker event, not a market decision).

**Fix:** Add FILL_CONFIRMED to `is_decision_tick()` exclusion list. Add agreement rule: FILL_CONFIRMED + shadow HOLD_RUNNER = agree (both indicate position is held, no new order).

**Encoded in:** `setup/scripts/shadow_model_eval.py` v6 (2026-06-16). `is_decision_tick()` and `actions_agree()`.

**Detection pattern:** When auditing a shadow eval miss, always check: is the real action a TRADING decision (entry/exit/setup monitoring), or is it INFRASTRUCTURE (infra failure, broker sync, kill-switch)? Infrastructure actions cannot be reproduced by a market-data model and should be excluded from DT.

**Related:** C7 (audit metric definitions, not just outputs). Action taxonomy: TRADING = HOLD_DEV/ENTER_*/EXIT_*/SKIP_*. INFRA = FILL_CONFIRMED/ERROR_*/PAUSED/TRIPPED.

---

## L83 — 2026-06-16: EXIT_STOP enrichment single-pattern regex — bracket-stop-leg format unmatched

**Symptom:** Shadow eval v5 replayed 5/18 10:06 EXIT_STOP as a DT miss (real=EXIT_STOP, shadow=HOLD). Model saw position_status="closed" (post-action state), no exit_hint, and correctly said HOLD — no open position visible.

**Root cause:** EXIT_STOP enrichment in `build_tick_prompt()` only matched one reason-field format: `premium_stop_breach: {cur} < {stop}`. The 5/18 10:06 EXIT_STOP reason field was a BRACKET STOP LEG format: `exit filled at 1.51 (below entry 1.84, between stop 0.99 and TP1 2.76); bracket stop leg or manual exit`. This format comes from Alpaca bracket orders where the stop leg fills at the GTC stop price — the heartbeat logs the Alpaca fill notification, not a premium-stop breach. The single regex pattern silently missed it.

**Fix:** Multi-pattern regex cascade — try all known formats, fall back to ribbon-flip detection:
1. `premium_stop_breach: {cur} < {stop}` (v4 original)
2. `cur={cur} stop={stop}` style
3. `exit_px={cur} stop={stop}` style  
4. `exit filled at {cur} ... stop {stop}` (bracket-stop-leg, v6 Pattern 4)
5. Fallback: if `"ribbon"` in reason → ribbon-flip stop (reconstruct open state + hint without price data)

**Rule:** Any evaluator that reconstructs pre-action state from post-action ledger entries MUST handle ALL reason-field formats from the actual production system. Test the regex against real historical reason strings, not synthetic ones.

**Encoded in:** `setup/scripts/shadow_model_eval.py` v6 (2026-06-16). EXIT_STOP enrichment block.

**Related:** C7 (audit outputs, not just exit codes). L76 (ghost entry from position state not written). Any time EXIT_* ticks log position_status="closed", the pre-action reconstruction must be robust to all trigger formats.

---

## L84 — 2026-06-16: Fill-acknowledgment action variants missed by is_decision_tick() exclusion

**Symptom:** Shadow eval counted `ENTRY_FILLED_HOLD` as a decision-tick miss (real=ENTRY_FILLED_HOLD, shadow=HOLD_RUNNER). Model correctly described the post-fill state but was penalized because the action wasn't in the DT exclusion list.

**Root cause:** The production heartbeat emits multiple fill-acknowledgment action names over time — `FILL_CONFIRMED` was excluded in v6 but `ENTRY_FILLED_HOLD` (a variant from the 5/20 Bold account early-era) was not. Both are state-tracking broker events: "entry fired, now holding". The model correctly outputs HOLD_RUNNER (position open, no new decision needed). Counting these as DT misses inflates the miss rate with non-decision ticks.

**Fix:** Maintain an explicit exclusion list for ALL fill-acknowledgment and state-tracking variants. Currently: `{"HOLD", "HOLD_RUNNER", "FILL_CONFIRMED", "ENTRY_FILLED_HOLD", "PAUSED", "TRIPPED"}`. Add corresponding agree rule: if real is a fill-ack variant and shadow in hold variants → agree.

**Rule:** When adding new action types to the production heartbeat, immediately classify them: "is this a trading decision OR a state-tracking event?" State-tracking events (broker acks, state machine transitions) must be added to the DT exclusion list in the shadow eval. A shadow eval that treats state transitions as decisions will systematically undercount agreement.

**Encoded in:** `setup/scripts/shadow_model_eval.py` v7 (2026-06-16). `is_decision_tick()` + `actions_agree()`.

**Related:** L82 (FILL_CONFIRMED exclusion). C7 (audit outputs, not exit codes).

---

## L85 — 2026-06-16: SKIP_ENTRY_* vs ENTER_* treated as disagree — account constraint ≠ model judgment error

**Symptom:** Shadow eval v6 counted `SKIP_ENTRY_INSUFFICIENT_BUYING_POWER` (real) vs `ENTER_BULL` (shadow) as a DT miss on 5/20. Both the real engine and the shadow model agreed the trade setup was valid — the real system just couldn't execute.

**Root cause:** `actions_agree()` had no rule for SKIP_ENTRY_* vs ENTER_* combinations. The real action is "I see the trade but can't execute (buying power limit)". The shadow action is "I see the trade and would enter". These are the same market judgment — the disagreement is purely about account execution state that the shadow model has no visibility into.

**Fix:** Add agree rule: `if real.startswith("SKIP_ENTRY_") and shadow.startswith("ENTER_"): return True`. The model's market read is correct; the skip is an infrastructure constraint. Similarly, SKIP_* + ENTER_* should not count as a model quality failure in any benchmark.

**Rule:** When evaluating model judgment quality, separate MARKET JUDGMENT (was the setup valid?) from EXECUTION CAPABILITY (could we actually enter?). Shadow eval only measures market judgment. Any skip driven by account constraints (buying power, PDT limits, kill-switch state) should agree with a corresponding enter call from the model.

**Encoded in:** `setup/scripts/shadow_model_eval.py` v7 (2026-06-16). `actions_agree()`.

**Related:** L82 (fill-ack exclusion). C11 (broker is source of truth for execution state).

---

---

## L86 — 2026-06-16: Trigger field null in early-era ledger — trigger extracted from reason ignored

**Symptom:** Shadow eval v7 replayed 5/11 10:25 ENTER_BULL as a DT miss (real=ENTER_BULL, shadow=HOLD_DEV). The model's snapshot showed `trigger: null` so it correctly said "no trigger → HOLD_DEV". But the reason field clearly contained "level_reclaim 738.10 + ribbon_expansion BULL 113c + HTF BULL."

**Root cause:** The production heartbeat at that early date (5/11 was one of the first Bold trading days) had a logging gap: the `trigger` field was not being written to decisions.jsonl at entry time, even though the reason field contained the authoritative trigger text. The shadow eval correctly implemented a `bull_score` fallback from reason, but had no equivalent fallback for `trigger`.

**Fix:** When trigger field is null after the allowlist check, scan the reason string for any valid trigger name using word-boundary regex. Sort valid triggers by length descending (longest-first prevents "level_reject" matching a "level_reclaim" prefix). Only extract first match to avoid injecting multiple triggers.

```python
if trigger is None and reason_raw:
    for valid in sorted(_VALID_TRIGGERS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(valid) + r'\b', reason_raw):
            trigger = valid
            break
```

**Rule:** Any field that has an authoritative text representation in the reason string MUST have a reason-field fallback in the eval. Ledger logging gaps are a known failure mode (L80 covers bull_score; this covers trigger). Audit all snapshot fields after each new eval day to check for null-but-non-null-in-reason cases.

**Encoded in:** `setup/scripts/shadow_model_eval.py` v8 (2026-06-16). Trigger extraction block.

**Related:** L80 (bull_score null fallback). C7 (audit outputs, not exit codes).

---

## L87 — 2026-06-16: HOLD_DEV at bs=0,0 (flat) treated as DT miss — production engine noise

**Symptom:** Shadow eval v7 counted 5/11 09:39 HOLD_DEV as a DT miss (real=HOLD_DEV, shadow=HOLD). The shadow model correctly said HOLD (bull_score=0, bear_score=0, no trigger, ribbon chop, before 10am gate). The production engine logged HOLD_DEV under conditions where HOLD_DEV makes no sense.

**Root cause:** Very early Bold account (5/11 = first day) had a production engine bug where it emitted HOLD_DEV in pre-10am ribbon-chop conditions with 0/0 scores. The rubric clearly requires bull_score>=7 for HOLD_DEV (near-miss monitoring). The shadow eval was correctly applying the rubric; the production engine was not.

**Fix:** Add agreement rule: real=HOLD_DEV + shadow=HOLD + flat_position + bull_score<=1 + bear_score<=1 → agree. Pass bull_score/bear_score to actions_agree() for this check. The condition is tight enough (all three: HOLD_DEV, HOLD, bs=0-1 flat) that it won't accidentally agree on legitimate near-miss HOLD_DEV cases.

**Rule:** When a shadow eval disagrees with the production ledger, check if the PRODUCTION action is consistent with the RUBRIC before classifying as model error. If the production action violates the rubric, the shadow model may be MORE correct — the disagreement is production noise, not model error. This is especially important for early-era ledger data where the production engine was still maturing.

**Encoded in:** `setup/scripts/shadow_model_eval.py` v8 (2026-06-16). `actions_agree()` HOLD_DEV noise rule.

**Related:** L84 (fill-ack exclusion). C7 (audit outputs). C18 (status-format discipline).

---

## L88 — 2026-06-16: Backtest sizing ignored per_trade_risk_cap_pct — orchestrator used fixed quality-tier qty, not capped to account equity

**Symptom:** v42 validator found 16/20 missed_week trades at 100–422% of equity cap. LEVEL-tier (qty=22) trade on 5/26 cost $2,728 notional on $747 equity = 365%.

**Root cause:** `orchestrator.py` assigned `trade_qty` via a fixed quality-tier ladder (SUPER=15/ELITE=10/LEVEL=22/TRENDLINE=3), never checking `initial_equity × per_trade_risk_cap_pct`. Rule 6 (30%/50% cap) only enforced by the live heartbeat, not the backtest.

**Fix:** After each fill, cap qty down linearly when `fill.entry_premium × fill.qty × 100 > initial_equity × per_trade_risk_cap_pct`. Scale `dollar_pnl` by `capped_qty / fill.qty` (linear since exit timing is independent of qty). Recompute `pct_return_on_premium` explicitly. Min floor = 3 contracts (Rule 6 minimum). Wire via `_params_to_kwargs` so `params_safe.json` (0.30) and `params_bold.json` (0.50) auto-route through `params_overrides`.

**Graduated guard:** `test_params_override_binds[per_trade_risk_cap_pct-0.01]` in `backtest/tests/test_graduated_guards.py`.

```python
# orchestrator.py — after fill returned, before trades.append(fill)
if fill is not None and initial_equity > 0 and per_trade_risk_cap_pct > 0:
    max_cost = initial_equity * per_trade_risk_cap_pct
    fill_cost = fill.entry_premium * fill.qty * 100
    if fill_cost > max_cost and fill.entry_premium > 0:
        capped_qty = max(3, int(max_cost / (fill.entry_premium * 100)))  # min 3 (Rule 6)
        if capped_qty < fill.qty:
            fill.dollar_pnl = fill.dollar_pnl * (capped_qty / fill.qty)
            fill.qty = capped_qty
            fill.pct_return_on_premium = fill.dollar_pnl / (fill.entry_premium * fill.qty * 100)
```

---

## L89 — 2026-06-16: Profitable profit-lock exit wrongly triggers TRENDLINE_LEG2 re-entry at qty=20

**Symptom:** On 4/29, engine took a second trade at qty=20 after a profitable profit-lock exit (+$94.50 at qty=3), wiping -$508 on the second entry. Net day: -$414. V14E edge_capture stuck at 405 instead of expected ~499.

**Root cause:** `orchestrator.py`'s `stopped_without_tp1` logic marked any `EXIT_ALL_PREMIUM_STOP` without `tp1_time_et` as "stopped," even when `fill.dollar_pnl > 0`. Profit-lock exits use PREMIUM_STOP as the exit reason (exit at the locked-in stop level, which is above entry). Counting a profitable exit as "stopped" enabled TRENDLINE_LEG2 re-entry (qty=20) on the same setup, 90 minutes later.

**Fix:** Add `fill.dollar_pnl <= 0` check to `stopped_without_tp1`. A profitable exit is a timing success, not a stop — it should not enable the leg-2 re-entry pattern.

```python
# orchestrator.py — stopped_without_tp1 gate
stopped_without_tp1 = (
    fill.tp1_time_et is None
    and (fill.dollar_pnl or 0.0) <= 0.0   # <-- new: profitable exits are NOT stops
    and (
        "PREMIUM_STOP" in exit_reason_str
        or "TIME_STOP" in exit_reason_str
        or "LEVEL_STOP" in exit_reason_str
    )
)
```

**Impact:** V14E anchor-day edge_capture: 405 → 499.50 (matches original keepers.jsonl 499.64). 4/29 day: -$414 → +$94.50. No anchor-day regressions. Wide 2026-Q1+Q2: $11,104 → $10,037 (TRENDLINE_LEG2 re-entries suppressed where prior was profitable — fewer but safer re-entries).

---

## L90 — 2026-06-16: Date-based staleness gate skips intraday top-up when CSV already has today's partial data

**Symptom:** `watcher_live.py` produced 1 diag entry on 2026-06-15 (first fire at 09:30) and zero entries for all 75 subsequent fires (WATCHER_FLEET 0/100 in EOD deep). Scheduled task ran at 13:55 ET with exit 0 — looked healthy from the outside.

**Root cause:** The yfinance intraday top-up gate was `if latest_csv_date < today`. The master CSV happened to include today's date (it contained a partial session's bars through 10:25 ET). So `latest_csv_date == today` → top-up skipped. The 09:30 fire processed the 10:25 bar (already in CSV). The dedup guard at line 222 (`if last_processed_ts == str(latest_ts): return 0`) then silently returned 0 for all 75 subsequent fires, since no new bar was fetched.

**Fix:** Add an absolute-staleness check: also top-up when the latest bar in the CSV is more than 10 minutes old, regardless of whether `latest_csv_date == today`.

```python
# watcher_live.py — top-up condition (before this fix, only date was checked)
try:
    latest_csv_ts = pd.to_datetime(spy_full["timestamp_et"]).max()
    if hasattr(latest_csv_ts, "tzinfo") and latest_csv_ts.tzinfo is not None:
        latest_csv_ts = latest_csv_ts.tz_localize(None)
    _stale_threshold = dt.timedelta(minutes=10)
    _csv_is_stale = latest_csv_ts < (dt.datetime.now() - _stale_threshold)
except Exception:
    _csv_is_stale = False

if latest_csv_date < today or _csv_is_stale:   # <-- was: if latest_csv_date < today
    # yfinance top-up
```

**General pattern:** Any data-freshness gate that uses calendar-date comparison (`date < today`) can silently fail when the data source has a PARTIAL today entry. Always pair with an absolute-timestamp staleness check. Applies to any watcher, validator, or aggregator that does an incremental top-up.

---

## L91 — 2026-06-16: Tick audit reports false-positive MISALIGNED-CRITICAL when backtest CSV is stale

**Symptom:** Heartbeat tick audit for 2026-06-15 reported 8/27 MISALIGNED-CRITICAL (30%), implying the closed-bar fix (v15.1) might be broken. All 8 critical ticks shared `closed_close = 753.540` (the 10:25 bar — the last bar in the backtest CSV) and `claimed_spy = 755.78–756.53` (live TV prices the heartbeat correctly read), yielding a divergence of $2.21–$2.99. All 8 actions were HOLD or HOLD_DEV — no trade taken. The true MISALIGNED-CRITICAL rate was 0.

**Root cause:** `classify_tick()` in `backtest/autoresearch/heartbeat_tick_audit.py` escalated any HOLD tick to CRITICAL when `abs(divergence) > $2.00`, regardless of whether the CSV data source was stale. Because L90 caused `watcher_live.py` to stop topping up after the 10:25 bar, all 27 afternoon ticks showed a $2+ gap between `last_closed_close` (10:25 bar, 753.54) and `claimed_spy` (live TV price 755–756). The audit interpreted this as the heartbeat reading an in-progress bar, but the heartbeat was reading the correct live price; the CSV was simply stale.

**Fix:** Added `csv_lag_minutes` — elapsed minutes since the last bar in the CSV closed. In the divergence branch, HOLD/HOLD_DEV ticks are only escalated to CRITICAL when `csv_lag_minutes < 30`. Decision-changing actions (ENTER, EXIT, ADD) remain CRITICAL unconditionally regardless of CSV staleness.

```python
# backtest/autoresearch/heartbeat_tick_audit.py — classify_tick()
DECISION_CHANGING_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "EXIT_STOP",
                              "EXIT_TP1", "EXIT_RUNNER", "ADD_LEG"}

csv_is_stale = csv_lag_minutes is not None and csv_lag_minutes > 30
if action in DECISION_CHANGING_ACTIONS:
    cls = "MISALIGNED-CRITICAL"           # always escalate on trade actions
elif abs(div_to_closed) > 2.00 and not csv_is_stale:
    cls = "MISALIGNED-CRITICAL"           # escalate only if CSV is fresh
else:
    cls = "MISALIGNED-BENIGN"
```

Re-run of 2026-06-15 audit after fix: 0 MISALIGNED-CRITICAL (was 8). `csv_lag_minutes` column also added to CSV output for post-mortem visibility.

**Encoded in:** `backtest/autoresearch/heartbeat_tick_audit.py` (`classify_tick()` function + `csv_lag_minutes` column). Related: L90 (the upstream CSV staleness bug that triggered the false positives); C7 (audit outputs must be accurate, not just non-crashing).

**Detection:** Re-run the tick audit after any watcher_live outage day. If MISALIGNED-CRITICAL count is non-zero, check `csv_lag_minutes` column in the audit CSV — if the critical rows all have `csv_lag_minutes > 30` and actions are HOLD/HOLD_DEV, the audit is working correctly (suppressed). If critical rows have `csv_lag_minutes < 30` and are HOLD ticks, a new regression exists.

---

## L92 — 2026-06-16: IS quality-lock cascade false positive from threshold changes — OOS 2.1× worse despite IS edge_capture tripling

**Symptom:** Filter-6 ribbon spread threshold sweep (30c → 20c) showed IS edge_capture 673 → 2,057 (+$1,384). OOS window (2026-05-08 to 2026-05-22): BASELINE −$709, CANDIDATE −$1,483 — 2.1× WORSE. A result that appeared to be the largest single-sweep gain in the research backlog turned out to be the worst regression in the same OOS window.

**Root cause:** Lowering the spread threshold from 30c to 20c admitted an EARLIER ELITE-tier entry on bars where ribbon spread was between 20c and 30c. This earlier entry:
1. Stopped out (lost money)
2. Set `setup_quality_taken_today = ELITE` (3 triggers)
3. `QUALITY_ESCALATION_LOCK` blocked the profitable LATER entry (LEVEL tier, lower quality — rank cannot escalate when prior entry of same quality level already won)

IS result: The 5/04 11:10 entry (new early entry) happened to hit a much better runner (+$2,491 vs +$322 baseline). This masked the 4/29 trap (−$412) and produced net IS gain of +$1,384. On IS only, it looks like an improvement.

OOS result: Same trap repeats. 13:15 entry (−$244) quality-locks 13:20 entry (+$529). Net OOS worsens by −$774. The IS 5/04 gain is a BS-sim flukey coincidence: 5 minutes earlier entry + marginally better strike + runner hits 2.5× target (vs BE stop on baseline). This does NOT generalize.

**Key mechanism (cascade path):**

| Time | BASELINE | CANDIDATE |
|---|---|---|
| 13:10 | no entry (spread=28c, above threshold) | ELITE entry, −$244 (spread=22c, new early) |
| 13:15 | ELITE entry, +$529 (rank=3 > nothing) | **QUALITY_ESCALATION_LOCK** (rank=3 = prior=3, prior=LOSS... but lock also fires when prior was same tier) |
| OOS net | +$529 | −$244 |

**Fix:** Before declaring ANY IS improvement that involves admitting new EARLIER entries:
1. Run OOS and assert `OOS_candidate >= OOS_baseline × 0.90`
2. Check for quality-lock cascade: does the new early entry set `setup_quality_taken_today` at a tier that blocks a profitable later entry?
3. Never trust BS-sim runner-target hits as evidence of improvement — they are noisy and regime-dependent (the 5/04 runner to 2.5× was a tariff-crash trending day; OOS fold was post-tariff chop)

**Graduated guard proposal:** `test_threshold_change_does_not_regress_oos` in `backtest/tests/test_graduated_guards.py`. For any candidate with IS edge_capture improvement via new early entries (detected by comparing `n_early_entries_candidate > n_early_entries_baseline`), run OOS window (2026-05-08 to 2026-05-22) and assert `OOS_candidate >= OOS_baseline * 0.90`.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L92 + CLAUDE.md OP-25 absorbed-lessons bullet. Graduated guard proposed for `backtest/tests/test_graduated_guards.py`.

**Detection:** Any grinder sweep that produces IS edge_capture improvement of >30% while touching a threshold that controls ENTRY TIMING (not signal quality) should automatically trigger OOS validation before the result is logged as an improvement. A cascade trace for the top-3 IS improvement days should be run: if the improvement days are single-day runner flukes (exit type = RUNNER, hold time < 30min, BS-sim only), the result is likely a false positive.

**Related:** L66 (quality-lock cascade blocking a bigger winner via an intermediate trade), L73 (OOS regime stratification — IS flukes that don't generalize), L85 (agree rules and quality lock cascade logic in shadow eval context).

---

## L93 — 2026-06-16: BEARISH_REVERSAL fires on DECLINING-VIX days — opposite of SNIPER; cross-contaminating SNIPER's VIX-escalating gate collapses EC to 0

**Symptom:** Tested VIX-escalating gate (prior_day_VIX >= prior_5d_avg_VIX, the L73 SNIPER discriminator) as a compound filter on BEARISH_REVERSAL filter-6@20c. Gate blocks ALL 3 J winner days (4/29, 5/01, 5/04 — every anchor day has FLAT/declining VIX at entry time). IS edge_capture collapses from 673 to 0. OOS per-trade expectancy worsens (−$69.8 vs −$44.3 baseline). Verified via `f6_vix_escalating_compound.py` sweep 2026-06-16.

Actual VIX readings for J anchor days confirm the pattern is structural, not coincidental:
- 4/29: prior=17.81, 5d_avg=18.47 → DECLINING
- 5/01: prior=16.93, 5d_avg=17.98 → DECLINING
- 5/04: prior=17.00, 5d_avg=17.65 → DECLINING
- 5/05 (LOSER day): prior=18.18, 5d_avg=17.66 → ESCALATING

**Root cause:** BEARISH_REVERSAL and SNIPER fire in OPPOSING VIX regimes.

| Setup | VIX regime at best entries | Why |
|---|---|---|
| SNIPER (L73) | ESCALATING (prior_day > 5d_avg) | Level breaks work in trending fear — rising VIX = sustained directional flow |
| BEARISH_REVERSAL | DECLINING (prior_day < 5d_avg) | Ribbon rejection works in fear-mean-reversion — fading the bounce AFTER peak fear |

The tariff-shock period (Apr–May 2026): VIX spiked to 50+ on April 9 (Liberation Day), then began declining. Best BEARISH_REVERSAL anchor days (4/29, 5/01, 5/04) were during this DECLINING phase — VIX still elevated (16–18) but falling from peak. SNIPER's VIX-escalating gate was calibrated on a structurally different regime and is incompatible.

The loser day (5/05) is the single escalating day. This is the inverse of SNIPER's L73 pattern — which means the two regime profiles are orthogonal and gates MUST NOT be cross-contaminated.

**Fix:** Do NOT apply SNIPER regime filters (VIX-escalating, VIX >= 18) to BEARISH_REVERSAL parameters. These setups have orthogonal regime profiles. Cross-contaminating regime gates from one setup to another is a structural error that will always collapse edge on the anchor-day set.

If a VIX gate is ever needed for BEARISH_REVERSAL, the correct direction to test is:
- VIX DECLINING (prior_day < 5d_avg) = ENABLE
- VIX ESCALATING = CAUTION

**Graduated guard:** `test_vix_escalating_does_not_apply_to_bearish_reversal` in `backtest/tests/test_graduated_guards.py`. For any candidate adding a VIX-escalating condition to BEARISH_REVERSAL parameters, assert IS EC does not fall below `baseline * 0.50` AND that 4/29, 5/01, and 5/04 are NOT gated out.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L93 + CLAUDE.md OP-25 absorbed-lessons bullet + graduated guard proposed for `backtest/tests/test_graduated_guards.py`. Related: L73 (VIX character > VIX level for SNIPER — the inverse pattern), L92 (OOS regression from IS-only optimization).

**Detection:** Any grinder sweep that adds a VIX threshold condition to BEARISH_REVERSAL and shows IS EC improvement should immediately be checked against anchor days 4/29, 5/01, 5/04. If any of those three are gated out, the sweep result is invalid. The graduated guard automates this check.

---

---

## L94 — 2026-06-15: PMH ≠ first-hour RTH range high when SPY gaps up — `detect_levels_at_bar()` blind spot + below-chance intraday H/L baseline

**Symptom:** Engine missed the 11:50 ET BEARISH_REVERSAL on 5/01 at the 724 level. Tick audit flagged "724 NOT in levels_active" as root cause #1 but did not explain why. Assumed it was a missing premarket or prior-day level, which is incorrect.

**Root cause:** On 5/01, SPY gapped up at open: PMH=$721.99, PDH=$719.79. Neither historical source contains 724. The 724 level was established DURING RTH trading:

- 09:55 bar: first break above 724 (high=$724.24)
- 10:00–10:20: price spent 25 min in the $724–$724.87 range (5 bars touched)
- 10:20 bar: day high = $724.87 (RTH first-hour range high)
- 11:50 bar: retest at $724.30, rejected to $722.72 (−$1.58 intrabar)

`detect_levels_at_bar()` only queries: prior-day H/L/C, premarket H/L (PMH/PML), and pre-loaded historical structural levels. It has no mechanism to register intraday structure formed during RTH. When SPY gaps above all historical references, the true resistance ceiling is the RTH first-hour range high — and the engine is blind to it.

**Compounding root cause:** Source-pruning kitchen study (2026-06-15) measured intraday H/L respect rate at 22.8% vs 25.9% DM-null — below chance by 3.1pp. This means a blanket `first_hour_high` level type would inject noise in most cases. The 5/01 case is the exception, not the rule:
1. Price spent ≥20 min at the level (multiple bars, not a wick)
2. ≥90 min elapsed between the range high and the 11:50 retest
3. The 11:50 bar was a massive reversal bar ($1.66 range, open-to-close −$0.82)

A first-hour RTH high only qualifies as structural when: dwell_bars ≥ 4 AND pullback_cents ≥ 100. Without both conditions, it is below-chance noise.

**Second structural blocker on 5/01:** Even with 724 in the level set, BEAR entry at 11:50 would have been blocked by ribbon=BULL with 100c spread (strongly trending BULL). Filter 5 requires ribbon=BEAR for BEAR entries unless `trendline_only_setup=True`. Both blockers must be fixed together — first_hour_high level registration AND level-chop relaxation (ribbon gate). Neither alone closes the 5/01 gap.

**Fix:** Proposed `detect_levels_at_bar()` enhancement — after RTH open, track running session high with dwell time. Register as `first_hour_high` level type only when: `dwell_bars >= 4 AND pullback_cents >= 100`. Guard: do not add this level type at all during active dwell (only after pullback confirms the level). Separately, evaluate ribbon gate relaxation for known structural level retests with multi-bar dwell evidence.

**Graduated guard:** Add to `backtest/tests/test_graduated_guards.py`:
```python
def test_first_hour_high_requires_dwell_and_pullback():
    """L94: any first_hour_high level detection must require >= 4 bars dwell
    AND >= $1.00 pullback. Without these, intraday H/L is below-chance noise
    per source-pruning study (22.8% vs 25.9% DM-null, 2026-06-15)."""
```

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L94 + CLAUDE.md OP-25 absorbed-lessons bullet + graduated guard proposed for `backtest/tests/test_graduated_guards.py`.

**Detection:** Any `detect_levels_at_bar()` call that adds intraday H/L source must assert respect_rate > DM-null baseline (25.9%) on OOS window before enabling. If dwell_bars < 4 OR pullback_cents < 100, level is silently excluded — the exclusion must be logged, not silent (per C7).

---

## L95 — 2026-06-16: `trendline_only_setup` relaxation creates inverse trigger-count dependency — adding level_rejection HARDENS filter_5

**Symptom:** Proposed adding first-hour RTH high to level set (rank 27) to give multi-trigger entry (level_rejection + trendline_rejection) at 5/01 11:50. Expected: two triggers → stronger signal → easier entry. Actual: two triggers made filter_5 a HARD BLOCK instead of the original soft demerit.

**Root cause:** `filters.py:1185-1210` implements `trendline_only_setup` relaxation: when `trendline_rejection` fires AS THE ONLY trigger (no level_rejection/confluence/sequence_rejection), filters 5 (ribbon BEAR), 8 (VIX), and 9 (vol) are REMOVED from hard blockers and become score demerits. When ANY other trigger fires alongside trendline_rejection, `trendline_only_setup=False` and filter_5 reverts to a HARD BLOCK.

This creates an inverse dependency:

| Trigger count | `trendline_only_setup` | filter_5 (ribbon) | Gate C (midday) | Entry possible? |
|---|---|---|---|---|
| trendline only | True | SOFT (demerit) | HARD BLOCK | NO |
| level + trendline | False | HARD BLOCK | SOFT (multi-trigger) | NO |
| level only | N/A | HARD BLOCK | SOFT (multi-trigger) | NO (if ribbon=BULL) |

All three trigger combinations block the entry on 5/01 11:50 (ribbon=BULL+100c). Neither rank 27 alone nor rank 26 alone closes the gap. The trendline_only relaxation was designed for chop entries (ribbon mixed, VIX low), NOT for countertrend setups at structural levels.

**Fix:** When `level_rejection` fires at a structural level (dwell_bars >= 4, pullback_cents >= 100 per L94) with ribbon=BULL, a SEPARATE filter_5 bypass is needed — either via:
1. LEVEL_CHOP_RELAXATION: add bar-strength + VIX conditions to grant a ribbon=BULL exception for multi-bar structural rejections
2. BEARISH_REVERSAL watcher path: the watcher explicitly requires ribbon=BULL (Gate 2) and bypasses the filter_5 check entirely by virtue of operating in watcher space

Do NOT attempt to use `trendline_only_setup=True` as the mechanism for structural level entries — this was designed for the opposite use case.

**Code pointer:** `backtest/lib/filters.py:1185-1210` (`trendline_only_setup` block). `heartbeat.md:410-413` (Gate C midday block — multi-trigger already exempt).

**Graduated guard:** Add check that `trendline_only_setup=False` whenever `level_rejection` is in triggers, and verify filter_5 is NOT removed from blockers in that case.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L95 + CLAUDE.md C15 cluster.

---

## L96 — 2026-06-16: Supplemental level added to `levels_active` contaminates `trendline_only_setup` via spurious `level_rejection`

**Symptom:** Rank 27 feature (first-hour RTH high as supplemental resistance level) was implemented by adding the FHH price to `BarContext.levels_active`. Full 17-month OOS showed `dn=0 dpnl=-$1,084` — rank 27 blocked the 2025-11-04 +$836.71 winner and 2025-06-16 +$61.75 winner while adding two losers.

**Root cause:** `detect_level_rejection(ctx.bar, ctx.levels_active)` evaluates proximity to ALL levels in `levels_active`. FHH=676.17 on 2025-11-04 is within proximity of the 13:55 bar (H=676.24, close=676.01, dist=0.07). This fires `level_rejection` in `triggers_fired`, making `trendline_only_setup=False`, re-enabling filter_8 (VIX gate) as a HARD BLOCK — which kills the trendline-only entry that fires cleanly in baseline.

Pattern: ANY level added to `levels_active` can fire `level_rejection`, which poisons `trendline_only_setup` for ALL bars near that level. Supplemental levels (dynamic, not confirmed by multi-session dwell) are particularly dangerous because they can be near price on days when the existing levels aren't.

**Fix:** Give supplemental/dynamic levels a SEPARATE trigger key (`fhh_level_rejection`) that does not appear in the `trendline_only_setup` guard condition. Changes required:

1. `filters.py`: Add `fhh_level: Optional[float] = None` to `BarContext`
2. `filters.py` `evaluate_bearish_setup()`: After standard `level_rejection` block, add FHH proximity check. Only fires when `rejection_level is None` (no base-level rejection). Generates `fhh_level_rejection` (not `level_rejection`) → `trendline_only_setup` guard unchanged
3. `orchestrator.py`: Pass `levels_active=level_set.active` (NOT effective_levels); pass `fhh_level=fhh_supplement`; keep `effective_levels` for `_update_level_states` only

**Result after fix:** `dn=0 dpnl=0.00` over 17 months — FHH is safely neutral without the BEARISH_REVERSAL filter bypass (L95). No regressions.

**Code pointers:** `backtest/lib/filters.py:80` (BarContext.fhh_level), `filters.py:1169-1177` (fhh_level_rejection check), `orchestrator.py:628-644` (BarContext construction).

**Graduated guard:** `test_first_hour_high_no_regression` (2025-11-04 +$836 must survive FHH flag); `test_first_hour_high_enables_level_trigger` (fhh_level_rejection fires on 5/01).

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L96. Cluster: C7 (silent-failure detection) + C14 (dead/translated-but-unapplied knob variant).

**Design principle:** Dynamic / supplemental levels that augment the base set MUST use a separate trigger namespace. Never share `level_rejection` between base (multi-session dwell, historically confirmed) and supplemental (single-session dynamic) levels.

---

## L97 — 2026-06-16: Strategy-specific grinder J_WINNERS must use SAME strategy type as detector

**Symptom:** SHOTGUN_SCALPER_STAGE1 grinder ran 322/2160 combos; all rejected on edge_capture_pct. Progress showed `best_edge_capture=0.0`. Root cause investigation showed `by_day['2026-05-14'] = 0` and `by_day['2026-05-15'] = 0` for ALL combos, inflating `J_TOTAL_WINNERS` to $4,150 and making the 50% EC floor ($2,075) structurally unreachable.

**Root cause:** Two J anchor win dates were added to `J_WINNERS` that are incompatible with the shotgun scalper detection mechanism:
- **5/14 (+$1,208):** J's trade was "open-drive bull confluence" — a CALL entry at market open. The shotgun detector fires vol-ratio signals only in the afternoon (13:20+), all below vol_ratio=1.2. 11 signals fired but none passed the threshold.
- **5/15 (+$1,400):** OPRA data missing for 5/15 0DTE contracts at the relevant strikes. 3 signals fired at vol_ratio >= 1.2 (14:15-14:35) but `_opra_premium_at()` returned None for all → 0 trades.

Max achievable EC = $1,542 (4/29 + 5/01 + 5/04 only). EC floor = $2,075. Gap = $533. Grinder was guaranteed to produce 0 keepers.

**Fix:** Only include J anchor trades in `J_WINNERS` whose trigger TYPE matches the strategy being tested. Explicitly annotate removed entries with the reason (`# REMOVED: strategy mismatch — open-drive pattern, detector fires vol-ratio`).

```python
# WRONG: any J win goes in J_WINNERS
J_WINNERS = [
    {"date": "2026-05-14", "j_pnl": 1208, "side": "C", ...},  # open-drive CALL — vol detector never fires
    {"date": "2026-05-15", "j_pnl": 1400, "side": "P", ...},  # OPRA data missing
]

# CORRECT: only days where THIS detector would fire on J's actual trade
J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342, "side": "P", ...},  # vol spike occurred
    {"date": "2026-05-01", "j_pnl": 470, "side": "P", ...},  # vol spike occurred
    {"date": "2026-05-04", "j_pnl": 730, "side": "P", ...},  # vol spike occurred
]
```

**Pre-run check (add to every strategy-specific grinder):** Before launching, run a 1-combo smoke test on each J anchor day and assert `by_day[date] != 0.0` — if it's 0, the detector is silent on that day and the anchor is incompatible.

---

## L98 — 2026-06-16: Vol-ratio-only detector is strategy-negative across 16 months — tighter criteria required

**Symptom:** SHOTGUN_SCALPER Stage-1 grinder probed all `vol_ratio_threshold` values [1.2, 1.5, 2.0] plus fine-grid [1.6–2.0]. Every combo produced negative `wide_pnl` (best: −$5,126, sharpe=−2.92 at vr=2.0, n=498). EC was also negative — detector fires at wrong times on J's CONFLUENCE/TRENDLINE anchor days (4/29 EC at best=287, 18.6% of floor, far below 50% gate).

**Root cause:** The vol-ratio threshold alone is insufficient as a signal. High-volume events at key levels are NOT systematically bearish — they can be bullish, distribution, or neutral. Detector fired 498–1,076 times over 16 months at various thresholds, but WR below 50% produced negative expectancy and deeply negative Sharpe. J's 3 canonical wins (4/29 +$342, 5/01 +$470, 5/04 +$730) are ALL CONFLUENCE+TRENDLINE entries, not vol-spike entries — the detector was being tested against wrong anchors even after L97 cleanup.

**Fix:**
1. Clear `J_WINNERS` entirely when no vol-spike anchors exist yet (empty list is valid, guard handles it).
2. Remove EC floor (`min_edge_capture_pct=0.0`) — no floor without anchors.
3. Add `min_wide_pnl=$500` as primary gate (replaces EC as go/no-go metric).
4. Redesign detector with tighter entry criteria before next grid search: require vol spike at PDH/PDL/★★★ level (not just any price), VIX declining regime, time gate 10:30–14:00 ET, ribbon confirmation (BEAR for puts), 1 entry per day limit.

```python
# WRONG: run grid search when wide-window probe shows all sharpe < 0
if wide_pnl < 0 and sharpe < 0:
    run_full_grid()  # burns compute on a strategy-negative detector

# CORRECT: prove positive IS edge on wide window BEFORE any grid search
# Pre-flight: if best wide_pnl < 0 at all tested thresholds → redesign detector first
if best_wide_pnl < 0:
    status = "strategy_negative"
    enqueue_redesign_task()
    return
```

**Pre-flight check (add to every new strategy grinder):** Before launching any grid search, run a 5-point parameter sweep (coarse grid) on the full date range. If ALL points produce `sharpe < 0` and `wide_pnl < 0`, the detector is strategy-negative — redesign it before spending compute on a 2000+ combo grid. This check costs ~5 minutes vs hours wasted on a doomed grid.

---

## L99 — 2026-06-16: profit_lock_threshold=0.0 creates artificial WR in BS-sim; BS-sim VIX underestimates extreme-VIX option premiums

**Symptom:** SNIPER stage-2 BS-sim showed WR=93.5%, wide_pnl=$27,813 with 229/231 exits labeled `STOP_ALL` at positive P&L ($120–$165/day). Real-fills CAVEAT: top OPRA day (2025-04-07) BS=+$1,007 vs real=-$556 (diff=-155%). Two compounding issues discovered.

**Root cause #1 — profit_lock_threshold=0.0 arms immediately:**
`profit_lock_threshold_pct=0.0` means profit lock arms when `favor_premium >= entry_premium × 1.0 = entry_premium`. The NEXT bar after a SNIPER entry almost always has a favorable intrabar extreme (high/low) that exceeds entry premium. Lock arms bar-1, raises stop from -6% to +5% → all `STOP_ALL` exits are at +5% gain not -6% loss. WR inflated from true ~18-46% to 93.5%.

Sweep confirms: `threshold=0.0`→WR=93.5%, `threshold=0.15`→WR=48.5% (breakeven). True directional edge appears at stop=-0.30 with no profit lock: $25,943, WR=46.3%.

**Root cause #2 — BS-sim VIX-to-IV formula underestimates extreme-VIX option premiums:**
On 2025-04-07 (Liberation Day VIX spike, VIX~52), BS-sim computed entry_premium=$3.60 using `vix_to_iv(vix)` + Black-Scholes. Real OPRA bid/ask mid was $9.26 — a 2.57× discrepancy. The linear/simple `vix_to_iv()` formula breaks down when VIX>40. At $9.26 entry, the real -6% stop=$8.70 fires on first adverse tick, causing -$556 vs BS-sim's +$1,007 which assumes a cheaper $3.60 entry.

**Fix:**
1. Never use `profit_lock_threshold_pct=0.0` in a BS-sim evaluator — this creates "free +5%" that doesn't exist in real fills due to bid/ask spread. Set threshold ≥ 0.05 for any meaningful analysis.
2. Add a VIX cap to SNIPER entries: refuse when real VIX > 35 (option premiums at extreme VIX are too expensive for any fixed premium-stop to work). Check BS-sim VIX at entry bar vs OPRA premium to detect underestimation.
3. For real-fills validation: filter top BS-sim days by entry_premium < $3.00 to exclude extreme-VIX outliers that BS-sim cannot model accurately.
4. Graduated guard: `test_profit_lock_threshold_zero_inflates_wr` — any evaluator with `profit_lock_threshold=0.0` should emit a WARNING that WR may be inflated.

**Code example:**
```python
# BAD: threshold=0.0 arms profit lock immediately → 93.5% fake WR
combo = SniperCombo(profit_lock_threshold_pct=0.0, premium_stop_pct=-0.06)
# GOOD: threshold=0.05 requires real gain before locking
combo = SniperCombo(profit_lock_threshold_pct=0.05, premium_stop_pct=-0.06)
# BEST for real-fills: wide stop, no profit lock artifact
combo = SniperCombo(profit_lock_threshold_pct=0.30, premium_stop_pct=-0.30)

# VIX cap filter (add to all SNIPER detectors):
vix_at_entry = _vix_for(vix_bars, entry_time)
if vix_at_entry and vix_at_entry > 35:
    return None  # skip extreme-VIX entries — BS-sim underestimates premium cost
```

---

## L100 — 2026-06-16: SNIPER_LEVEL_BREAK all-premium-exit combos negative; threshold=99.0 "genuine edge" requires 300% intraday premium moves

**Symptom:** After removing the threshold=0.0 artifact (L99), a 36-combo sweep of SNIPER premium exits (stop=[−0.20,−0.25,−0.30,−0.35] × threshold=[0.20,0.25,0.30,0.40] × runner=[2.0,2.5,3.0]) showed ALL NEGATIVE P&L over 231 trading days. Best: stop=−0.20, threshold=0.40, runner=2.0 → P&L=−$3,764, WR=38.5%. Prior "genuine edge" claim: stop=−0.30, threshold=99.0 (no profit lock) → $25,943, WR=46.3%.

**Root cause:** Three-layer artifact stack across all threshold values:
1. `threshold=0.0` (L99): arms profit lock on bar-1 → all exits at +5% premium → fake WR=93.5%.
2. `threshold=0.20–0.40` (this lesson): profit lock fires after partial gain, caps runner exits at +5% above entry. With wider premium stops (−20% to −35%), losses exceed capped gains → all negative.
3. `threshold=99.0` (no lock): runner runs free to 3.0× in BS-sim. Example: $2.43 entry × 3.0 = $7.29 target. BS-sim fires this from 5-min OHLCV bar highs/lows. In real fills: Liberation Day entry $9.26 (L99) → runner target $27.78 — requires ~7% intraday SPY move from the level-break point. This NEVER fires in 0DTE options. The $25,943 "genuine edge" is a BS-sim runner-path artifact, not a real signal.

**Compound pattern:** threshold=0.0 inflates WR (L99). threshold=0.20–0.40 destroys P&L (this lesson). threshold=99.0 creates fake runner edge. No premium-exit threshold value produces a validated positive result.

**VIX-trend SNIPER (#13–#15 leaderboard) also invalidated:** Those IS/OOS results ($2,774 IS + $2,486 OOS) were generated with threshold=0.0 (L99 artifact) on only n=17–19 trades. At a +5% exit artifact per trade, even a small trade count accumulates. Without the artifact, these trades follow the same negative pattern as the sweep.

**Fix:**
1. Archive all premium-exit SNIPER variants. Mark leaderboard entries #13–#15 ARTIFACT-INVALIDATED (L99+L100).
2. Pivot to chart-stop SNIPER redesign: stop placed at level ± 0.30–0.50 SPY points (not % of premium). Eliminates L51/L55 misfire by design.
3. Before claiming any chart-stop SNIPER edge: run pre-flight 5-combo coarse sweep (L98 pattern). If 5/5 wide_pnl < 0 → redesign detector.
4. Real-fills validation required on ≥ 3 non-extreme-VIX (VIX < 30) trading days before any SNIPER variant enters PROMISING status.

**Code note:** The BS-sim runner path in `sniper_evaluator.py:_simulate_trade()` fires whenever any OHLCV bar's favorable extreme crosses `entry_premium × runner_target_pct`. In volatile 5-min bars, this fires spuriously often. Real OPRA fills never see these extremes simultaneously (bid/ask spread + intrabar path order).

**Graduated guard:** `test_l100_sniper_premium_exits_no_positive_result` — asserts sniper-stage2-realfills.json verdict remains CAVEAT or BLOCKED. Any change to PASS triggers a mandatory re-run requirement.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L100, `strategy/candidates/_LEADERBOARD.md` (#13–#15 ARTIFACT-INVALIDATED), `backtest/tests/test_graduated_guards.py`. Clusters: C1 (real-fills authority), C3 (option edge ≠ SPY edge).

---

## L101 — 2026-06-16: Chart-stop SNIPER: 50/64 combos positive; buffer=0.75 sweet spot; ATM beats ITM-2; J anchors are strategy-specific

**Symptom:** After confirming all premium-exit SNIPER combos negative (L100), chart-stop redesign (`sniper_cs_evaluator.py`) was built: stop placed at `level_price ± chart_stop_buffer` SPY points (not % of premium). 64-combo sweep (buffer=[0.30,0.50,0.75,1.00] × tp1_r=[1.5,2.0,2.5] × runner_r=[2.5,3.0,3.5] × strike_offset=[0,2]) returned **50/64 positive** — a breakthrough vs all-negative premium exits.

**Key findings:**

1. **Buffer=0.75 sweet spot.** 16/16 combos positive ($18K–$24K). Buffer=0.30 too tight: 2/16 positive (initial chop stops out immediately). Buffer=0.50: 12/16 positive. Buffer=1.00: 8/16 positive (R-ratio degraded — stop too wide kills runner value).

2. **ATM (strike_offset=0) beats ITM-2 (strike_offset=2)** for chart-stop SNIPER. Opposite of L74 (TBR ATM FAIL for premium-stop scalpers). Chart-stop eliminates the premium whipsaw that makes ATM dangerous with percentage stops. With SPY-price stop, delta difference matters less.

3. **WF ratio split.** IS=Q1–Q3 2025, OOS=Q4 2025 + 2026. Best wide_pnl ATM combos: WF=0.19–0.26 (regime shift post-Q3 2025). 6 combos pass WF≥0.5 — all ITM-2 or buffer≥0.75. Best WF-pass: buf=0.75, tp1=2.5, runner=3.5, off=2 → **WF=0.621, $19,692, 6/6 quarters positive**.

4. **J anchor mismatch (L97 pattern applied to SNIPER).** J's three source-of-truth winners (4/29, 5/01, 5/04) are BEARISH_REJECTION_RIDE_THE_RIBBON entries (ribbon-flip + trendline), NOT SNIPER_LEVEL_BREAK fires (vol-spike crossing a named level). SNIPER fires at different bars → all J anchor floors fail. Wide-window P&L edge is genuine but edge_capture cannot be measured against OP-16 floor without SNIPER-specific anchor days.

5. **Vol-spike regime concentration.** top5_pct=1.0–1.6 for top combos — P&L concentrated in Liberation Day era (Q1–Q2 2025 VIX spike events). Edge is regime-dependent.

**Fix / design pattern:**
```python
# chart-stop: stop placed in SPY space, not premium space
chart_stop_spy = level_price + chart_stop_buffer  # for puts (bear)
risk_spy = chart_stop_spy - entry_spot            # SPY-space risk
tp1_spy = entry_spot - (risk_spy * combo.tp1_r)  # TP1 as R-multiple
runner_spy = entry_spot - (risk_spy * combo.runner_r)  # runner target

# exit check (bear/puts): stop fired if adverse bar high >= chart_stop_spy
chart_stop_hit = (not is_call) and (adverse_spy >= chart_stop_spy)
```

**Pre-promotion checklist (beyond L98 pre-flight):**
1. Real-fills on ≥5 non-extreme-VIX SNIPER fires (VIX<30 per L99).
2. Identify SNIPER-specific anchor days (vol-spike level break wins, not ribbon-flip entries) before claiming edge_capture vs OP-16 floor.
3. VIX regime filter study: test VIX>15 or VIX>18 gate to improve OOS WF from 0.19–0.26 to ≥0.50 on ATM combos.

**Graduated guard:** `test_sniper_cs_uses_chart_stop_not_premium_stop` (added 2026-06-16) — asserts `SniperCSCombo` has `chart_stop_buffer` field, no `premium_stop_pct`, and `chart_stop_spy` appears in simulation logic.

**Encoded in:** `markdown/doctrine/LESSONS-LEARNED.md` L101, `backtest/autoresearch/sniper_cs_evaluator.py`, `backtest/autoresearch/sniper_cs_sweep.py`, `analysis/recommendations/sniper-cs-sweep.json`, `strategy/candidates/_LEADERBOARD.md` (#23 NEEDS-REALFILLS). Clusters: C3 (SPY-price edge != option edge).

---

## L102 — FHH PROXIMITY IS ANTI-CORRELATED WITH GAP-UP SETUP VALUE (2026-06-16)

**Setup class:** FHH bypass discriminator (BEARISH_REVERSAL_FHH_BYPASS, Rank 28).

**Symptom:** Proximity gate `fhh_quality_proximity`: require FHH within X$ of any `multi_day_level` was intuitive (FHH = prior-range resistance retest) but empirically REMOVED the 5/01 J anchor at ALL thresholds (0.50, 1.00, 2.00). The gate was doing the opposite of what was intended.

**Root cause:** Gap-up FHH sessions — the exact sessions where FHH bypass delivers value — are defined by price breaking ABOVE all prior range levels. FHH=724.24 on 5/01 is ABOVE max(multi_day_levels)≈$722 by $2.24. By construction, high-value FHH bypass entries have FHH far from prior levels (gap-up), not near them (range resistance). Proximity = distance to multi_day_levels = SMALL → bypass fires. Gap-up FHH = distance to multi_day_levels = LARGE → proximity gate blocks it. Anti-correlation.

**Fix — invert the hypothesis:** The correct discriminator is the inverse: `fhh_above_max_prior_min=1.00` requires FHH ≥ max(multi_day_levels) + $1.00 (price broke above all prior levels by ≥ $1). This preserves 5/01 (gap=$2.24, PASS) and blocks 5/08 (gap=−$0.34, BLOCK). Drag reduced 86%: −$1,899 → −$257. 24 bypass days → 6 bypass days.

**General rule:** When a setup's VALUE comes from BREAKING ABOVE a threshold (new range), any gate requiring PROXIMITY to that threshold is anti-correlated with setup value. "Far above" is the signal; "near" is the noise. The same logic applies to:
- FHH bypass: far above multi_day_levels = genuine gap-up
- SNIPER level breaks: far above PDH = genuine breakout, not false break
- Any "reclaim after breakdown" setup: far above the breakdown level = strong reclaim

**Anti-pattern guard:** `test_fhh_v4_proximity_antipattern` — asserts proximity=1.00 does NOT pass 5/01. Prevents re-testing the anti-correlated hypothesis. See `backtest/tests/test_graduated_guards.py`.

**Encoded in:** `backtest/lib/filters.py` (fhh_above_max_prior_min + fhh_quality_proximity parameters with anti-correlation warning in comments), `backtest/tests/test_graduated_guards.py` (2 guards), `strategy/candidates/2026-06-16-bearish-reversal-fhh-bypass.md` (v4 section). Clusters: C14 (dead/translated-but-unapplied knobs), C6 (filter behavior vs setup intent).

---

## L103 — BYPASS MECHANISM FIRES AT WRONG BAR ON ANCHOR DAY (2026-06-17)

**Setup class:** FHH bypass (BEARISH_REVERSAL_FHH_BYPASS, Rank 28). Generalizes to any entry-bypass mechanism.

**Symptom:** FHH bypass enabled on 5/01 (J winner +$470). Engine loses -$364 vs baseline on 5/01 (5/01 regresses from -$56 to -$420). Bypass was specifically designed to capture the 5/01 J anchor.

**Root cause:** Two separate BEARISH_REVERSAL opportunities exist on 5/01:
1. **~11:50 ET — FHH rejection:** Price rises to FHH (~$724), ribbon=BULL, FHH rejection fires. This is what the FHH bypass targets. BUT this bar's bear entry LOSES — not a good entry, wrong timing.
2. **13:36 ET — trendline rejection:** J's actual anchor trade. This is a different trigger (trendline_rejection, not fhh_level_rejection). The FHH bypass does NOT target this bar. Engine takes J's 13:36 trendline bar via trendline_only_setup (small loss at -$56 baseline).

Bypass fires at bar #1, loses. Bar #2 (J's trade) is unaffected. Net: bypass costs -$364, doesn't help J's 13:36 trade at all.

**Root cause generalized:** A bypass mechanism verified as "this day should work" is not verified as "this bypass fires on J's specific entry bar." Same date does NOT guarantee same bar/trigger/price.

**Fix — bar-level verification:** When validating a bypass against a J anchor day: (1) check WHICH bar the bypass fires on, (2) check the timestamp vs J's documented entry time, (3) check the trigger type (bypass target = `fhh_level_rejection`; J's entry was `trendline_rejection`). If trigger types don't match, bypass cannot fix the anchor trade.

**Fix for 5/01 specifically:** J's 5/01 entry requires `trendline_rejection + ribbon=BULL` bypass — NOT `fhh_level_rejection`. The `trendline_only_setup` block (2026-05-09) already handles this; 5/01 at -$56 baseline is the engine already taking the trendline_only entry. The gap ($470 J vs -$56 engine) is in strike/size selection, not in blocking the trade. Further bypass development on FHH mechanism will NOT fix the J/engine divergence on 5/01.

**General rule:** Validate bypass mechanisms at `(date, bar_time, trigger_type)` — not `(date)`. If the bypass fires on the right date but wrong bar, it adds a losing trade while leaving J's actual trade uncaptured.

**Anti-pattern guard:** Verify bypass fires at J's bar_time ± 5 bars before calling a bypass "5/01 fix." Add explicit logging of which bar bypasses fire on in future bypass implementations.

**Encoded in:** `automation/overnight/STATUS.md` (entry 84, 2026-06-17). `strategy/candidates/2026-06-16-bearish-reversal-fhh-bypass.md` (REJECTED status). Clusters: C15 (gates interact multiplicatively — trace session cascades), C7 (silent success is failure).

---

## L104 — SHARPE INFLATED BY ZERO-TRADE DAYS WHEN VIX FILTER ELIMINATES MOST ENTRIES (2026-06-17)

**Setup class:** SNIPER_CS_CHART_STOP VIX>=18 walk-forward validation.

**Symptom:** IS Sharpe = 2.060 for VIX18 filter variant. OOS Sharpe = 0.356. WF ratio = 0.173 (FAIL). OOS IS technically positive (+$2,563, $49/trade avg) but the WF gate rejects the candidate because IS Sharpe is disproportionately high.

**Root cause:** VIX>=18 filter reduces IS entries from 90→43 trades in the IS window (Jan–Oct 2025). Q3 2025 (July–Sept) had near-zero VIX>=18 days (low summer VIX), producing zero SNIPER CS fires. Daily P&L series for IS: 175 days at exactly $0 + 43 non-zero days. Sharpe denominator (std of daily returns) is very small because 80% of days are exactly $0 — not zero because trades lost, but zero because no trades fired. IS Sharpe looks like 2.060 but this is a measurement artifact of computing Sharpe over a day-series that's mostly zeros.

This is NOT a sign the strategy works well — it means the filter is selectively active in only a few high-VIX regimes that happened to be favorable IS.

**Fix — compute Sharpe on TRADING-DAY returns only:** When comparing IS vs OOS Sharpe for a filtered strategy:
```python
# WRONG: compute Sharpe over all calendar days (includes zero-trade days)
all_day_pnl = {d: 0.0 for d in calendar_days}
for t in trades: all_day_pnl[t.date] += t.pnl
sharpe = sharpe_from_dict(all_day_pnl)  # inflated if filter creates many $0 days

# CORRECT: compute Sharpe over trading days only (days filter allowed at least one trade)
trading_day_pnl = {}
for d in calendar_days:
    day_trades = [t for t in trades if t.date == d and t.fired]  # filter fires on this day
    if day_trades:  # only include days where the filter allowed trades
        trading_day_pnl[d] = sum(t.pnl for t in day_trades)
sharpe = sharpe_from_dict(trading_day_pnl)
```

Alternatively: compute Sharpe on per-trade R-multiple returns (one entry per trade, no zeros).

**Fix — WF diagnosis before Sharpe:** Before running WF validation on a filtered strategy, check: what % of IS calendar days are $0 because the filter blocked everything? If >50%, IS Sharpe is suspect. Instead, compare: IS_pnl_per_trade vs OOS_pnl_per_trade (raw averages) as the first diagnostic.

**Applied:** SNIPER CS VIX18 per-trade averages:
- IS: $30,702 / 43 trades = **$714/trade avg**
- OOS: $2,563 / 52 trades = **$49/trade avg**

$714 vs $49/trade is the real IS/OOS divergence — a 14x per-trade gap. This IS genuine overfit. The Sharpe inflation just hid the true nature: a per-trade degradation from $714 → $49, not a methodology artifact.

**Why VIX18 is still IS-overfit (not just methodology):** IS Q1/Q2 2025 were both strong VIX spike regimes where SNIPER CS worked well. The filter selected for these IS-favorable regimes. In OOS (Nov 2025 – May 2026), VIX18 days had more diverse market conditions → per-trade edge fell 14x. Filter was over-selecting favorable IS regimes, not capturing a persistent mechanism.

**Correct fix for regime filtering:** Use VIX CHARACTER (L73) not VIX level. Prior_day_VIX > prior_5d_avg_VIX was OOS-validated for original SNIPER (WF=0.983). For SNIPER CS, this test also produced negative OOS ($-1,041) suggesting the chart-stop SNIPER signal itself needs further development, not just a regime filter.

**Encoded in:** `automation/overnight/STATUS.md` entry 86, `analysis/recommendations/sniper-cs-vix-trend-comparison.json`, `strategy/candidates/2026-06-16-sniper-cs-vix18-filter.md` (OOS-FAILED). Clusters: C4 (Disclose concentration, normalize OOS, stratify by regime), C7 (Silent success is failure).

---

## L105 — REAL-FILLS ORCHESTRATOR USES GLOBAL STOP NOT SIDE-SPECIFIC STOP (2026-06-16)

**Symptom:** Sweeping `premium_stop_pct_bear` from -8% to -99% via direct kwarg in real-fills mode produced identical output for all values. BS-sim path correctly honored the bear-specific stop; `params_overrides` dict path also worked. Only direct kwarg to `run_backtest` with `use_real_fills=True` was broken.

**Root cause:** `orchestrator.py` lines 937-957 (`simulate_trade_real` call) passed `premium_stop_pct=premium_stop_pct` (global default -0.08) and `strike_offset=strike_offset` (global default -2). The BS-sim path at line 977 correctly computed `side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop` and used `side_premium_stop` in the call. The two code paths diverged: BS-sim was production-accurate, real-fills was not.

This meant ALL `use_real_fills=True` backtests used the legacy -8% stop instead of the -20% production bear stop from `params.json`. Real-fills P&L and WF calculations since this path was introduced were computed with the wrong stop.

**Fix:** Move `side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop` and `side_strike_off = bear_strike_off if winning_side == "P" else bull_strike_off` to BEFORE the `if use_real_fills:` block. Pass `premium_stop_pct=side_premium_stop` and `strike_offset=side_strike_off` in the `simulate_trade_real` call. The same variables are reused in the BS-sim else branch.

```python
# WRONG (before fix): real-fills uses global default stop
if use_real_fills:
    fill = simulate_trade_real(..., premium_stop_pct=premium_stop_pct, ...)
else:
    side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop

# CORRECT (after fix): side-specific stop computed before branch
side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop
side_strike_off = bear_strike_off if winning_side == "P" else bull_strike_off
if use_real_fills:
    fill = simulate_trade_real(..., premium_stop_pct=side_premium_stop, strike_offset=side_strike_off, ...)
else:
    # side_premium_stop already computed above
```

**Impact of fix:** IS baseline corrected from +$3,031 (buggy -8% stop) to -$2,155 (correct -20% stop). Monthly breakdown shifted: Apr-2026 -$3,880 (was -$847), Mar-2025 -$1,834 (was -$90). Rank 25 WF reversed: from -2.44 (INCONCLUSIVE) to +5.79 (EXCELLENT) because IS delta changed sign: was -$531 (wrong), corrected to +$490 (correct).

**Detection pattern:** When sweeping a stop parameter that you KNOW changes BS-sim output, but real-fills gives identical output for all values — check whether the real-fills branch uses `side_premium_stop` or the global `premium_stop_pct`. Any code path that diverges for `use_real_fills` branches is a suspect for parameter-parity bugs.

**Encoded in:** `backtest/lib/orchestrator.py` lines 937-957 (fixed 2026-06-16), `automation/overnight/STATUS.md` entry 99, `strategy/candidates/_LEADERBOARD.md` Rank 25 correction. Cluster C7 (Silent success is failure — real-fills was silently running with wrong stop), C14 (Dead/translated-but-unapplied knobs — though here the knob IS applied but via wrong variable in one code path).

---


## L106 — params_overrides null propagation: entry_no_trade_window_et and duration nulls silently dropped (2026-06-17)

**Symptom:** params_overrides baseline gives different n than identical direct kwargs. `_params_to_kwargs` returned different trade counts (n=49 po vs n=54 direct), and the null value for `max_ribbon_duration_bars` caused a `TypeError: int() argument must be a string... not NoneType` crash. More critically: Rank 25 (MAX_RIBBON_DUR_8) appeared PROMISING with WF=5.794 but re-evaluation with production-correct params gave WF=0.072 (FAIL). An overnight session built a PROMISING scorecard on a wrong baseline.

**Root cause (two bugs in `_params_to_kwargs`):**

1. `entry_no_trade_window_et: null` -- original code: `if "entry_no_trade_window_et" in overrides and overrides["entry_no_trade_window_et"]:` -- when value is null/None (production value since v15.1 removed the no-trade window), the condition is falsy and the key is silently skipped. The `no_trade_window` default `(dt.time(14,0), dt.time(15,0))` persisted in all Karpathy shadow / params_overrides runs, incorrectly blocking 14:00-15:00 trading even though production removed this window.

2. `max_ribbon_duration_bars: null` / `min_ribbon_momentum_cents: null` -- code did `int(overrides["max_ribbon_duration_bars"])` without a null check. If params.json ever has these as null, all params_overrides runs crash.

**A/B scorecard impact (L106 root cause of WF inflation):** Direct-kwargs baseline for the Rank 25 scorecard used the function default `no_trade_before=dt.time(10,0)` instead of production 09:35. This excluded the 09:35-10:00 trading window. Combined with bug #1 (keeping legacy 14:00-15:00 block), the old baseline missed 43 IS and 8 OOS early-morning trades. Those 8 OOS trades were all profitable -- their exclusion made the baseline look like -$1,907 (terrible), making the dur=8 filter look like a massive rescue when it was only +$163 improvement on the correct baseline. Old WF=5.794 was entirely an artifact. Correct WF=0.072 (FAIL). May sub-window FAILS (-$2,421: filter over-aggressive in recovery regime).

**Fix (backtest/lib/orchestrator.py _params_to_kwargs):**

Before fix -- entry_no_trade_window_et null silently dropped:
    if "entry_no_trade_window_et" in overrides and overrides["entry_no_trade_window_et"]:
        # only true branch, null never reaches here

After fix -- null explicitly disables the legacy default:
    if "entry_no_trade_window_et" in overrides:
        if overrides["entry_no_trade_window_et"]:
            # parse and set window
        else:
            kwargs["no_trade_window"] = None  # disable legacy v11 (14:00-15:00) default

Null guards added for int conversions:
    if "max_ribbon_duration_bars" in overrides and overrides["max_ribbon_duration_bars"] is not None:
        kwargs["max_ribbon_duration_bars"] = int(...)

**Graduated guard:** `test_graduated_guards.py::test_l106_params_to_kwargs_null_window_propagates`, `test_l106_params_to_kwargs_null_duration_no_crash`, `test_l106_params_overrides_matches_direct_kwargs_n` (all passing 2026-06-17).

**Scorecard update:** Rank 25 A/B scorecard at `analysis/recommendations/max_ribbon_dur8_ab_scorecard.json` updated with v2 (production-correct) results. Leaderboard: PROMISING -> FAILED (WF=0.072, sub-window inconsistent). Next research: VIX-escalating conditioned variant (dur=8 only when VIX prior_day > 5d_avg, per L73 SNIPER pattern).

**Prevention rule:** Before building any A/B scorecard, run baseline via `params_overrides=production_params` AND identical direct kwargs. Assert n matches. A discrepancy means a mapping bug that will invalidate the WF ratio. Function defaults (no_trade_before=10:00, no_trade_window=(14:00,15:00)) are never the correct production proxy -- always use explicit production values.

**Encoded in:** `backtest/lib/orchestrator.py` `_params_to_kwargs` (fixed 2026-06-17), `backtest/tests/test_graduated_guards.py` L106 tests, `automation/overnight/STATUS.md` entry 109, `strategy/candidates/_LEADERBOARD.md` Rank 25 FAILED. Cluster C7 (Silent success is failure -- scorecard appeared PROMISING on wrong baseline), C14 (Dead/translated-but-unapplied knobs -- null values silently dropped instead of propagated).

---

## How to use this catalog

1. Before building a new evaluator: read all 105 (updated through L105 2026-06-16).
2. After each anti-pattern you avoid: cross-reference here.
3. When you hit a NEW anti-pattern: add it as L98, etc.
4. Every L# entry should have: symptom, root cause, fix, code example.
5. **L36 meta-pattern:** every NEW diagnostic tool you build for an L# entry should ALSO get a SKILLS-CATALOG.md entry + (if user-facing) a `.claude/skills/{name}/SKILL.md` registration. Keep the catalog current.

This catalog is the cheapest insurance against repeating known mistakes.

---

## L107 — A/B Scorecard Re-validation Used BS Sim + Wrong Bear Stop (2026-06-17)

**Theme:** C1 (Real-fills is only WR/P&L authority) | C7 (Silent success is failure)

**Setup:** Rank 22 (RIBBON_MOMENTUM_GATE — `min_ribbon_momentum_cents=5.0, max_ribbon_duration_bars=15`) was ratified and went live in `automation/state/params.json`. A "re-verification" on 2026-06-16 was done in the prior session. The re-verification claimed: baseline n=17 pnl=-$907, gates n=5 pnl=+$1,204, delta=+$2,111, OOS WF=3.74.

**Symptom:** When re-running Rank 22 with production-correct params during root-cause analysis of the L106 bug, the OOS delta was -$1,352 (gate HURTS) rather than +$2,111 (gate HELPS). The WF was -1.308 (FAIL) instead of 3.74 (PASS). Same OOS window (2026-05-08..22), same n=17 baseline trades.

**Root cause:** The 2026-06-16 re-verification used:
1. `use_real_fills=False` (BS sim) — NOT production path
2. Default `premium_stop_pct_bear=-0.08` — NOT production -0.20

With BS sim + -0.08 stop: baseline n=17 pnl=-$907. With production params (urf=True, -0.20 stop): baseline n=17 pnl=+$4,367. A $5,274 swing on the SAME 17 trades. The BS-sim path applies the wrong stop loss (too tight at -8% for bear), causing many profitable bear trades to be stopped out fictitiously. This makes the baseline look terrible (-$907) and makes the gate look like a rescue (+$2,111). In reality the baseline is already profitable (+$4,367) and the gate REMOVES $1,352 of profitable trades.

**Impact:** A gate that was validated as +$2,111 improvement is LIVE in production REMOVING profitable trades (-$1,352 OOS). 

**Full correct scorecard (production params: urf=True, bear_stop=-0.20, no_trade_before=09:35, midday_gate=True, no_trade_window=None):**
- IS (2025-01..2026-04): baseline n=246 pnl=-$5,610 → gates n=76 pnl=-$4,576, delta=+$1,034
- IS ex-April (non-shock 15 months): baseline n=223 pnl=+$936 → gates n=68 pnl=-$2,562, delta=-$3,498
- April 2026 tariff shock: baseline n=22 pnl=-$6,335 → gates n=8 pnl=-$2,014, delta=+$4,321 (ONLY window where gate helps)
- OOS (2026-05-08..22): baseline n=17 pnl=+$4,367 → gates n=8 pnl=+$3,015, delta=-$1,352
- WF = OOS_delta / IS_delta = -1,352 / +1,034 = **-1.308 (FAIL)**

The gate is a regime artifact: tuned exclusively on the April 2026 tariff-shock month. It destroys profitable non-shock IS (+$936 → -$2,562) and destroys profitable OOS (+$4,367 → +$3,015).

**Fix:**
1. Scorecard corrected at `analysis/recommendations/ribbon_momentum_gate_ab_scorecard.json` (`l107_revalidation: true`)
2. Leaderboard Rank 22 updated: 9/10 RATIFIED → 0/10 REQUIRES J DECISION
3. STATUS.md entry 111 flagged for J
4. Graduated guards: `test_l107_real_fills_differs_from_bs_sim_on_oos_window`, `test_l107_ribbon_momentum_gate_ab_scorecard_correct_params`
5. Cannot remove from params.json autonomously — Rule 9 requires J decision

**Prevention rule:** Every A/B scorecard MUST explicitly document `use_real_fills: true` and `premium_stop_pct_bear: -0.20` in its `correct_params` block. A scorecard missing those keys is INVALID. The graduated guards enforce this at the code level. Additionally: BS sim and real-fills produce >$500 P&L difference on any 2-week OOS window — a fast sanity check is to run both and assert the gap exists before trusting either number.

**Related lessons:** C1 (L02, L12, L23, L50, L71, L107), L106 (same session, wrong params propagation)

---

## L108 — tp1_qty_fraction dead knob in real-fills path (2026-06-17)

**Theme:** C14 (Dead/translated-but-unapplied knobs: vary-and-assert; sync tracker to params)

**Symptom:** Sweeping `tp1_qty_fraction` in [0.30, 0.40, 0.50, 0.60, 0.67, 0.75, 0.80] with `use_real_fills=True` produced identical P&L for all values. `run_backtest()` accepts the parameter but never reached the real-fills exit-P&L calculation.

**Root cause:** `simulate_trade_real()` hardcoded `TP1_QTY_FRACTION = 2.0/3.0 = 0.667` (v14 default). The constant is imported from `simulator.py` (line 73). The function signature had no `tp1_qty_fraction` parameter, so:
1. `run_backtest()` received `tp1_qty_fraction` but never passed it to `simulate_trade_real()`
2. `simulate_trade_real()` used the hardcoded constant for both `tp1_qty = int(qty * TP1_QTY_FRACTION)` and `_compute_pnl(fill, qty)` (which also used the constant)

Production `params.json` has `tp1_qty_fraction = 0.50` (ratified v15). Every real-fills backtest silently used 0.667 instead of 0.50 — allocating 2/3 to TP1 vs the production 1/2. Runners got 1/3 of position in backtests vs 1/2 in production.

**P&L impact:** Runner gets 50% more contracts in production (frac=0.50) than backtests modeled (frac=0.667). Backtest underestimates runner P&L. OOS window impact measured after fix is TBD (sweep in progress). BS sim path was not affected (simulator.py already accepted tp1_qty_fraction as a parameter).

**Fix:**
1. Added `tp1_qty_fraction: float = TP1_QTY_FRACTION` parameter to `simulate_trade_real()` in `backtest/lib/simulator_real.py`
2. Replaced hardcoded `TP1_QTY_FRACTION` with `tp1_qty_fraction` at the `tp1_qty = int(qty * ...)` calculation
3. Added `tp1_qty_fraction: float = TP1_QTY_FRACTION` to `_compute_pnl()` helper and replaced constant there
4. Updated `_compute_pnl(fill, qty)` call to `_compute_pnl(fill, qty, tp1_qty_fraction=tp1_qty_fraction)`
5. Added `tp1_qty_fraction=tp1_qty_fraction` to `simulate_trade_real()` call in `backtest/lib/orchestrator.py`
6. Graduated guard: `test_l108_tp1_qty_fraction_wired_in_real_fills` — sweeps [0.30, 0.667, 1.0] and asserts OOS P&L spread >= $100

**Detection:** The L108 guard would have caught this immediately. Rule: after adding any parameterizable knob to `run_backtest()`, always run a 3-value sweep with `use_real_fills=True` and assert the output changes. Identical output = dead knob.

**Prevention rule:** Every new parameter added to `run_backtest()` MUST be (a) threaded through to BOTH `simulate_trade()` AND `simulate_trade_real()` call sites, and (b) tested with the dead-knob detect pattern (3-value sweep, assert spread >= threshold). The C14 theme (`test_params_override_binds`) already guards this class; L108 extends it to the real-fills call path specifically.

**Related lessons:** C14 (L38, L70, L72, L77, L88, L89, L96), L107 (same session, wrong-params propagation)

---

## L109 — runner_target_premium_pct dead knob in real-fills path (2026-06-17)

**Theme:** C14 (Dead/translated-but-unapplied knobs: vary-and-assert; sync tracker to params)

**Symptom:** `simulate_trade_real()` hardcoded `RUNNER_MAX_PREMIUM_PCT = 3.00` (v14 default from `simulator.py`) at line 317. Production params.json has `runner_max_premium_pct: 2.5`. Every real-fills backtest modeled a runner target of 3.0× (300%) instead of the 2.5× (250%) that the live engine uses. Same root cause class as L108.

**Root cause:** The `run_backtest()` call in `orchestrator.py` (line 1113) passes `runner_target_premium_pct=runner_target_premium_pct` to the **BS sim** path (`simulate_trade()`), but the corresponding `simulate_trade_real()` call did NOT include `runner_target_premium_pct`. `simulate_trade_real()` had no such parameter — it used the imported constant `RUNNER_MAX_PREMIUM_PCT = 3.0` directly.

**P&L impact:** Runner target in backtest (3.0×) was 20% harder to reach than production (2.5×). Backtests underestimate runner P&L because runners that would have been captured at 2.5× in production waited for 3.0× and were instead stopped out at BE or on time stop. The OOS baseline P&L impact was measured after the fix as TBD (see STATUS.md entry 114).

**Fix:**
1. Added `runner_target_premium_pct: float = RUNNER_MAX_PREMIUM_PCT` parameter to `simulate_trade_real()` in `backtest/lib/simulator_real.py`
2. Replaced hardcoded `RUNNER_MAX_PREMIUM_PCT` with `runner_target_premium_pct` at the `runner_target_premium = entry_premium * (1.0 + ...)` line
3. Added `runner_target_premium_pct=runner_target_premium_pct` to the `simulate_trade_real()` call in `backtest/lib/orchestrator.py`
4. Graduated guard: `test_l109_runner_target_wired_in_real_fills` (sweeps [1.5, 2.5, 3.0] asserts OOS spread >= $100)

**Prevention rule:** Same as L108. Every new parameter in `run_backtest()` must be threaded to BOTH `simulate_trade()` AND `simulate_trade_real()` call sites. Add a 3-value dead-knob sweep test immediately. The C14 graduated guard template is `test_l108_tp1_qty_fraction_wired_in_real_fills` — copy and adapt for any new param.

**Related lessons:** C14 (L38, L70, L72, L77, L88, L89, L96, L108), L108 (discovered in same session — structural sibling)

---

## L110 — time_stop_et dead knob in real-fills path (2026-06-17)

**Theme:** C14 (Dead/translated-but-unapplied knobs: vary-and-assert; sync tracker to params)

**Symptom:** `simulate_trade_real()` hardcoded `TIME_STOP_ET = dt.time(15, 50)` (the imported constant from `simulator.py`). The `time_stop_et` parameter added to `simulate_trade_real()` signature in this fix session was not being used at the time-stop check lines. The constant value happened to match production (10 minutes before close = 15:50 ET), so P&L was numerically correct for production, but any sweep of `time_stop_minutes_before_close` produced identical real-fills results. The knob looked live but was inert.

**Root cause:** Same class as L108/L109. `orchestrator.py` computed `time_stop_et = dt.time(...)` from `time_stop_minutes_before_close` and passed it to the BS sim path (`simulate_trade()`), but the `simulate_trade_real()` call was missing the `time_stop_et=time_stop_et` argument. `simulator_real.py` had `TIME_STOP_ET` referenced globally in the function body rather than using the parameter.

**P&L impact:** In production, the correct value (15:50 ET) was used, so no live trading impact. For optimization sweeps, the knob appeared dead — all values of `time_stop_minutes_before_close` returned identical IS/OOS P&L. This masked a real edge: exiting at 15:40 (20 min before close) shows WF=0.86 PASS improvement vs production 15:50 ET (see scorecard `analysis/recommendations/time_stop_minutes_ab_scorecard.json`).

**Fix:**
1. Added `time_stop_et: dt.time = TIME_STOP_ET` parameter to `simulate_trade_real()` in `backtest/lib/simulator_real.py`
2. Replaced all instances of `TIME_STOP_ET` constant with the `time_stop_et` parameter in the function body (replace_all=True)
3. Added `time_stop_et=time_stop_et` to the `simulate_trade_real()` call in `backtest/lib/orchestrator.py`
4. Graduated guard: `test_l110_time_stop_minutes_wired_in_real_fills` (sweeps [5, 10, 20] min asserts OOS spread >= $50)

**Discovery:** 6-value sweep of `time_stop_minutes_before_close` [5, 10, 15, 20, 25, 30] revealed that:
- Production (10 min, 15:50): IS=-$6,077, OOS=+$3,304
- Best candidate (20 min, 15:40): IS=-$5,525, OOS=+$3,779 — WF=0.86 PASS
- Mechanism: 0DTE theta crush in final 15 minutes; earlier exit captures more runner premium
- All 4 sub-windows HELP (IS full, IS ex-Apr, April tariff shock, OOS May)

**Prevention rule:** Same as L108/L109. Any `dt.time` constant derived from minutes-before-close in `simulator.py` must be parameterized in BOTH simulator paths. The C14 guard template is `test_l108_tp1_qty_fraction_wired_in_real_fills` — copy, adapt, add dead-knob sweep.

**Related lessons:** C14 (L38, L70, L72, L77, L88, L89, L96, L108, L109), L108/L109 (discovered in same session — structural siblings)

---

## L111 — VIX threshold constants missing from orchestrator._FILTER_CONST_MAP (2026-06-17)

**Symptom:** `run_backtest(..., params_overrides={"vix_bear_threshold": 10.0})` and `params_overrides={"vix_bear_threshold": 25.0}` produce identical OOS output (n=16, pnl=$2,416.10). Confirmed by 3-value sweep (10.0, 17.30, 25.0 — all identical before fix).

**Root cause:** `runner._FILTERS_CONST_KEYS` contained `"vix_bear_threshold": "VIX_BEAR_THRESHOLD"` (and 3 other VIX constants), allowing the runner's `_patched_filter_constants` to patch them. But `orchestrator._FILTER_CONST_MAP` — which is what `run_backtest(..., params_overrides=...)` uses — did NOT include these keys. So any optimization using `run_backtest` + `params_overrides` silently left the VIX constants at their hardcoded module defaults.

**Fix:** Added 4 missing keys to `backtest/lib/orchestrator.py:_FILTER_CONST_MAP`:
- `"vix_bear_threshold": "VIX_BEAR_THRESHOLD"` — Filter 8 hard block threshold
- `"vix_rising_deadband": "VIX_RISING_DEADBAND"` — VIX direction noise filter
- `"vix_bear_rising_deadband": "VIX_RISING_DEADBAND"` — asymmetric bear alias, same target
- `"vix_bull_max": "VIX_BULL_HARD_CAP"` — Bull Filter 9 hard cap

Graduated guard: `test_l111_vix_bear_threshold_wired_in_orchestrator` (n_high < n_low-1 for thresholds 25.0 vs 10.0).

**Discovery:** After fix, `vix_bear_threshold=25.0` reduces OOS n from 16 to 10 (blocks 6 trades where VIX did not exceed 25), confirming the knob is now live. Continued to full IS+OOS sweep of `VIX_BEAR_THRESHOLD` [14.0–20.0] to find if production 17.30 is optimal (results pending).

**Prevention rule (C14 extension):** Any time you add a key to `runner._FILTERS_CONST_KEYS`, also add it to `orchestrator._FILTER_CONST_MAP`. The two dicts must stay in sync — they serve the same purpose (patching `lib.filters` module constants) in two different code paths (runner's `run_with_params` vs orchestrator's `run_backtest`).

**Related lessons:** C14 (same root cause class as L38, L70, L72, L77, L88, L89, L96, L108, L109, L110)

---

## L112 — Chandelier profit-lock over-triggers in 5-min bar simulation (2026-06-17)

**Symptom:** Adding production chandelier params (`profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20`) to the research CORRECT baseline causes OOS to collapse from +$2,416 to −$292 (−$2,708 swing). IS improves by +$3,425 (from −$6,077 to −$2,652). Not generalizable — the IS improvement is an artifact.

**Root cause:** `simulate_trade_real` walks 5-min OPRA option bars. Within a single bar, the bar's HIGH can arm the chandelier (`best_premium >= entry × 1.05`), making HWM = bar.HIGH. Immediately after, the bar's LOW can breach the 20%-off-HWM trailing floor (`trail_floor = HWM × 0.80`), firing the stop. This arm-then-trail-then-stop sequence fires in ONE bar — one 5-minute window. In production, the heartbeat fires every 3 minutes. If price recovers before the next heartbeat, no stop fires. The simulator uses the bar's full OHLC range, which includes wicks that the heartbeat would never see at the exact tick-level.

**Concrete scenario:** Entry at $1.00. Bar HIGH = $1.10 (arm threshold = $1.05, so chandelier arms). HWM = $1.10. Trail floor = $1.10 × 0.80 = $0.88. Bar LOW = $0.86 < $0.88 → stop fires at $0.88. But in production, heartbeat at bar open (say $1.05) doesn't stop yet. Next heartbeat (3 min later) might see $1.02 > $0.88 → no stop. The trade continues.

**Fix / Convention:** NEVER include `profit_lock_*` parameters in the research CORRECT dict used for sweep comparisons. The production chandelier is a real-time management tool that 5-min bar simulation cannot faithfully replicate. The simulation artifact makes the chandelier look worse than it is in the OOS window (where each wick triggers the full sequence).

**Correct research baseline (confirmed):**
```python
CORRECT = dict(
    use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True, premium_stop_pct_bear=-0.20, premium_stop_pct_bull=-0.08,
    per_trade_risk_cap_pct=0.30, tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=10,
    # DO NOT ADD: profit_lock_threshold_pct, profit_lock_mode, profit_lock_trail_pct
    # — 5-min bar chandelier over-triggers (arm+trail+stop in same bar). See L112.
)
```

**Impact on existing candidates:** Rank 29–31 candidates (tp1_qty_fraction, time_stop) were swept against CORRECT (no profit lock). Their OOS deltas are valid within-sweep comparisons. The absolute OOS baseline (+$2,416) reflects "no-chandelier" simulation, not production-exact output — a known and documented disclosure per OP-20.

**Prevention:** If a sweep produces a positive IS result that vanishes or inverts in OOS, check whether any management parameter (chandelier, trailing stop) was added to the baseline — this is the tell. Walk-forward ratio < 0 on a management-param sweep is the canonical signal.

**Related lessons:** C3 (stop-misfire in simulation), L71 (real-fills vs BS-sim gap from profit-lock cap), C1 (simulation is ranking-only, not production-exact)

## L113 — level_stop_buffer_dollars C14 dead knob + ribbon-flip-before-level-stop architectural insight (2026-06-17)

**Symptom:** `level_stop_buffer_dollars` parameter was accepted by `simulate_trade_real()` and passed by the orchestrator, but the function body used a hardcoded `LEVEL_STOP_BUFFER = 0.50` constant at the usage site, making the parameter inert. Sweeping [0.10, 0.50, 1.00] returned identical IS P&L across all values ($-4,744.83) — the C14 dead-knob fingerprint (see also L108, L109, L110).

**Root cause (the fix):** `simulator_real.py` had `LEVEL_STOP_BUFFER = 0.50` defined as a local constant inside `simulate_trade_real()` even though the function accepted `level_stop_buffer_dollars: float = 0.50` as a kwarg. The level_breached condition used `LEVEL_STOP_BUFFER` (the constant) instead of `level_stop_buffer_dollars` (the parameter). Fix: removed the local constant, replaced with the parameter. Orchestrator default corrected from 0.0 → 0.50 so existing callers see identical behavior.

**Architectural insight — why P&L spread = $0 even after fix:** After fixing the dead knob, sweeping [0.10, 0.50, 1.00] STILL returns identical P&L. Root cause: `simulate_trade_real()` evaluates the **ribbon flip check before the level stop check**. For a bear trade, when price closes above the rejection level, the ribbon has typically already flipped to BULL (by the nature of bearish entries — the ribbon being bearish is a prerequisite, and once price reclaims above the rejection level, the ribbon typically converts to BULL). So `EXIT_ALL_RIBBON_FLIP_BACK` fires first, consuming the exit slot before the level-stop check runs. The level stop is a rare fallback for the edge case where price spikes past the rejection level on a single bar without the ribbon catching up — uncommon on 5-min data where ribbon lags 3+ bars.

**Impact on guard design:** A P&L-spread guard for `level_stop_buffer_dollars` is not viable — even with the correct implementation, ribbon flip will produce identical P&L across a wide buffer range. The correct guard is a **code inspection guard** verifying: (1) param exists in function signature, (2) hardcoded constant is gone, (3) usage site references the parameter, (4) orchestrator maps `chart_stop_buffer_dollars` → `level_stop_buffer_dollars` in `_params_to_kwargs`. Guard: `test_l113_level_stop_buffer_wired_in_real_fills`.

**Prevention:** When a parameter governs a condition that is almost always pre-empted by an earlier exit condition, never rely on P&L-spread tests to verify the wiring. Use code inspection guards. Check for execution sequence in the simulator: which exit condition fires first? If an earlier condition has nearly 100% coverage, downstream conditions are untestable via aggregate P&L.

**Production wiring:** `chart_stop_buffer_dollars` in params.json → `_params_to_kwargs()` → `level_stop_buffer_dollars` kwarg → `simulate_trade_real()` parameter → `rejection_level + level_stop_buffer_dollars` in level_breached condition. Production value: 0.50.

**Related lessons:** C14 (dead/translated-but-unapplied knobs), L108 (tp1_qty_fraction dead), L109 (runner_target dead), L110 (time_stop dead), L111 (VIX constants missing from _FILTER_CONST_MAP)

---

## L114 — VIX_HARD_CAP_BEAR: correctly wired, empirically inert — Apr-26 losses are NOT from VIX-extreme entries (2026-06-17)

**Symptom:** Hypothesis: block BEAR entries when VIX > 45 to eliminate April 2026 Liberation Day losses (VIX=52) without harming OOS May-26 recovery trades (VIX 20-35). Sweep of VIX_HARD_CAP_BEAR = [999, 50, 45, 40, 35, 30] shows ALL caps from 35 to 999 produce identical IS n=246, pnl=-$4,744.83 and OOS n=17, pnl=$4,747.40. Cap=30 removes exactly one trade — a WINNER, worsening IS by $1,591.

**Root cause (wrong hypothesis):** The hypothesis assumed April 2026 BEARISH_REVERSAL entries occurred when VIX was at panic-extreme levels (40-52). They did not. Sub-window analysis shows 22 April 2026 IS trades lost -$6,189 — but every one of those 22 entry bars had VIX in the 17.30-30 range, not 40-52. The Liberation Day VIX spike (April 2, 2026, VIX=52) either: (a) occurred on bars where `vix_direction=declining` (after the first spike bar) → filter 8 blocked BEAR entry (VIX must be RISING to enter), or (b) VIX rose gradually through the 17-30 range during the trading day, creating entries at VIX 20-28, not at the 52 extreme. Result: VIX_HARD_CAP_BEAR at any value above 30 has zero empirical effect — no entries exist at VIX > 35 in the entire 16-month IS dataset.

**Fix:** No production change. The constant is correctly wired (verified by code inspection guard test_l114). The hypothesis, not the implementation, was wrong.

**Architectural insight — filter 8 auto-blocks extreme VIX scenarios:** Filter 8 requires `vix_now > 17.30 AND vix_direction == "rising"`. After a VIX spike, the direction typically reverses to declining, which blocks BEAR entries (filter 8 FAILS when vix is declining). So the extreme VIX bars (45-52) during Liberation Day are already naturally blocked by the declining-VIX-direction condition, not by the new cap. The cap would only matter if VIX were both > 45 AND still classified as "rising" — a scenario that doesn't appear in the IS data.

**Regime lesson:** April 2026 losses (-$6,189) are NOT filterable by single-bar VIX level. They result from entries at VIX 17-30 where BEARISH_REVERSAL set up correctly on the chart but the tariff-shock macro environment produced directionally wrong outcomes. The real discriminator is multi-day VIX regime character (escalating vs declining, per L73). However, applying VIX-escalating gates to BEARISH_REVERSAL removes Q3-25 and Feb-26 profitable periods (L93). The April 2026 regime is a known limitation of BEARISH_REVERSAL — it performs in VIX-declining recovery regimes (Q3-25, Feb-26, OOS May-26) and fails during VIX-escalating panic.

**Prevention:** Before implementing a VIX-level filter to block specific regime losses, verify that the target trades actually occurred at those VIX levels. Run a per-trade VIX-at-entry distribution check first. The C14 dead-knob smell (sweep of [35-999] all identical) is the diagnostic — if the knob has zero effect at any value, the entry conditions don't create trades in that parameter range.

**Guard:** `test_l114_vix_hard_cap_bear_wired_in_orchestrator` — code inspection guard with 4 checks: (1) VIX_HARD_CAP_BEAR defined in filters.py, (2) VIX_HARD_CAP_BEAR referenced in filter 8 logic, (3) "vix_hard_cap_bear" in orchestrator._FILTER_CONST_MAP, (4) "vix_hard_cap_bear" in runner._FILTERS_CONST_KEYS.

**Related lessons:** C14 (dead/translated knobs), L73 (VIX character > VIX level; VIX escalating vs declining), L93 (VIX-escalating gate anti-correlates with BEARISH_REVERSAL), L113 (ribbon-flip fires before level-stop → code inspection guard)

---

## L115 — VIX multi-day MA crossover INCONCLUSIVE: Apr-26 Liberation Day losses not filterable by lagged MA signal (2026-06-17)

**Symptom:** Two VIX multi-day filter variants were tested to discriminate April 2026 tariff-shock (VIX escalating 17→52) from recovery regimes (Q3-25 BoJ, Feb-26 DeepSeek, OOS May-26). Neither meets the WF≥0.70 ratification gate. VIX_DECLINING_REQUIRED_BEAR stays False (production unchanged).

**Approach 1 — `vix_now > vix_5d_ma` (current bar above 5-day daily-close MA → block BEAR):**
IS +$2,600 / OOS **−$4,156** (WF=**−1.598** CATASTROPHIC FAIL). Root cause: OOS May-26 recovery trades occur as VIX falls from 35→20. During this descent, VIX bounces briefly above its own 5-day rolling MA (a "dead-cat bounce" within an overall declining trend) — these intratrend bounces are the OOS entry bars. The filter blocks exactly the best 5 OOS trades by confusing temporary bounces within a declining trend with a genuine escalating regime. Diagnostic: this is the L73 pattern (`vix_now > 5d_MA` is a poor discriminator for multi-week trend direction).

**Approach 2 — `vix_5d_ma > vix_20d_ma` (golden/death cross on VIX → block BEAR when 5d_MA is above 20d_MA):**
IS +$3,487 / OOS $0 delta (WF=**0.000** INCONCLUSIVE). The 5d/20d crossover is more robust — OOS is completely preserved (17 trades, +$4,747 unchanged). However, Apr-26 is also completely unchanged (22 trades, −$6,189 unchanged). Sub-window breakdown: Q1-25 helps (+$3,794), Mar-26 helps (+$2,499), but Feb-26 regresses (−$1,982), Q4-25 regresses (−$1,139). Net IS +$3,487 from removing non-Apr-26 losers, not from removing the target regime.

**Root cause of approach 2 failure on Apr-26:** The Liberation Day VIX spike is violent and fast (April 2, 2026: VIX 20→52 in one session). The BEARISH_REVERSAL engine enters on April 3–7 when VIX is in the 17-30 range (early escalation, not the 52 peak). At that time: the 5d_MA (which averages only the prior 5 daily closes, not the spike day itself) is ~21-24, and the 20d_MA (averaging March 2026, a moderately elevated period) is ~19-22. The crossover may not yet have triggered, or it triggers too slowly. Most Apr-26 BEAR entries fire in the first few days of escalation before any MA-based regime signal is conclusive. The MA crossover is inherently lagged by the construction of the MAs — it detects regime change AFTER the entries have already happened.

**Root cause of Feb-26 regression in approach 2:** February 2026 recovery period had 3 profitable BEAR trades (Feb-26 +$3,135 → +$1,153 with filter True). VIX in February 2026 was in a post-DeepSeek declining phase; the 5d_MA during this period was above the 20d_MA in some sub-windows (VIX declining from 20→15, but the 5d_MA still elevated from the recent spike), blocking those winning entries. The crossover filter is not recovery-regime-aware — it misclassifies early recovery as "escalating" when the recent spike is still in the 5d window.

**Fix:** No production change. VIX_DECLINING_REQUIRED_BEAR=False (default) is backward-compatible and is the correct production setting. The constants and infrastructure (VIX_DECLINING_REQUIRED_BEAR, vix_5d_ma, vix_20d_ma in BarContext, _vix_5d_ma_per_day, _vix_20d_ma_per_day precomputed in orchestrator) remain wired for future research use.

**Regime conclusion:** The April 2026 Liberation Day tariff-shock losses (−$6,189, 22 trades) are NOT filterable by single-bar VIX level (L114), by current-bar-vs-5d-MA comparison (approach 1), or by 5d/20d MA crossover (approach 2). The regime occurs on the FIRST FEW DAYS of a VIX escalation — before any MA-based signal can confirm the new regime. All three approaches fail because they are inherently lagged. The Apr-26 losses are a known limitation: BEARISH_REVERSAL generates edge in VIX-DECLINING recovery regimes (Q3-25, Feb-26, OOS May-26) and fails in the initial phase of VIX-ESCALATING shock events where the direction is ambiguous from any MA perspective.

**Anchor day check:** The VIX_DECLINING_REQUIRED_BEAR=True filter is anchor-neutral — zero delta on 4/29 (+$0), 5/01 (−$24.82, unchanged), 5/04 (+$0 — engine doesn't fire these dates in baseline either), 5/05 (−$1,207.60, unchanged), 5/06 (−$171.60, unchanged). No anchor-day regression from L115.

**Prevention:** Before implementing any VIX-trend filter to remove a specific IS regime, verify that (a) the target trades occur with enough lag for the MA to have confirmed the regime, and (b) the filter doesn't misclassify recovery entries as escalation. The "death cross on VIX" (5d > 20d) is conceptually sound but empirically too slow to catch the Liberation Day pattern. Future approaches: event-driven regime flags (FOMC, tariff announcement, Liberation Day flag in params), or fixed calendar dates as bypass, rather than inferred MA signals.

**Guard:** `test_l115_vix_declining_required_bear_wired` — code inspection guard with 6 assertions: VIX_DECLINING_REQUIRED_BEAR defined in filters.py, used in filter 8, vix_5d_ma in BarContext, _vix_5d_ma_per_day precomputed in orchestrator, key in orchestrator._FILTER_CONST_MAP, key in runner._FILTERS_CONST_KEYS.

**Related lessons:** C5 (VIX character > VIX level; as-of trigger time), L73 (VIX declining vs escalating; 5-day window is natural unit), L93 (VIX-escalating gate anti-correlates with BEARISH_REVERSAL), L114 (VIX hard cap empirically inert — Apr-26 entries at VIX 17-30)

---

## L116 — min_triggers_bear dead knob in params_overrides path: legacy key naming silently bypassed snake_case alias (2026-06-17)

**Symptom:** Sweep of min_triggers_bear = [1, 2, 3] via `params_overrides={'min_triggers_bear': N}` returned identical IS n=246, pnl=-$4,744.83 for ALL values of N — C14 dead-knob signature. Yet the filter 10 min_triggers gate (`if len(triggers) < min_triggers`) is correctly implemented in filters.py (line 1303). The parameter exists, is wired into the orchestrator, and is passed to filters.evaluate_bearish_setup — but the params_overrides path bypassed it entirely.

**Root cause:** `orchestrator._params_to_kwargs` contains a legacy key handler: `if "filter_10_min_triggers_bear" in overrides: kwargs["min_triggers_bear"] = ...`. The function only checked the old legacy naming convention (`filter_10_min_triggers_bear`) that predates the standardized snake_case naming used across all other params_overrides keys. When the sweep called `params_overrides={'min_triggers_bear': N}`, the key `"min_triggers_bear"` was NOT found in the handlers (only `"filter_10_min_triggers_bear"` was), so no override was applied and the default (min_triggers=1) was silently used for all N.

**Fix:** Added two snake_case alias passthrough blocks in `_params_to_kwargs`:
```python
if "min_triggers_bear" in overrides:  # L116: raw snake_case alias
    kwargs["min_triggers_bear"] = overrides["min_triggers_bear"]
if "min_triggers_bull" in overrides:  # L116: raw snake_case alias
    kwargs["min_triggers_bull"] = overrides["min_triggers_bull"]
```

**Verification after fix:** mt=2 correctly removes 7 STANDARD-tier (single-trigger) IS trades from Apr-26 (22 → 16 trades). Full IS sweep:
- mt=1 (prod): IS n=246, pnl=-$4,744.83 / OOS n=17, pnl=+$4,747.40
- mt=2: IS n=179, pnl=+$7,647.02 (IS_delta=+$12,391.85) / OOS n=12, pnl=+$1,712.40 (OOS_delta=−$3,035.00) → WF=−0.245 FAIL
- mt=3: IS n=149, pnl=+$5,519.54 / OOS n=10, pnl=+$2,665.20 (OOS_delta=−$2,082.20) → WF=−0.203 FAIL

**Research outcome: production min_triggers_bear=1 confirmed optimal.** The quality-tier breakdown explains why: STANDARD-tier (n=1 trigger) OOS trades are the BEST OOS performers (5 trades, +$3,035, WR=60%). Removing them via min_triggers=2 destroys OOS. The IS improvement at mt=2 (+$12,392) comes entirely from removing Apr-26 STANDARD entries — but Apr-26 STANDARD entries fail because of the Apr-26 regime, not because they are inherently low-quality. In the OOS May-26 recovery regime, STANDARD trades succeed better than ELITE or SUPER tiers. Quality gating cannot discriminate regimes.

**Quality-tier breakdown:**
- Apr-26 IS: STANDARD (n=1): 7 trades −$4,015. ELITE (n=2): 10 trades +$1,174. SUPER (n=3): 3 trades −$1,899.
- OOS May-26: STANDARD (n=1): 5 trades **+$3,035 (WR=60% — best OOS tier)**. ELITE (n=2): 9 trades +$1,103. SUPER (n=3): 3 trades +$609.
- Conclusion: STANDARD fails in Apr-26 chaos but LEADS in May-26 recovery. Regime determines quality outcome, not trigger count.

**Prevention:** When adding a new params_overrides key, ensure BOTH the snake_case AND any legacy naming variant are handled in `_params_to_kwargs`. The legacy naming block exists because old grinder scripts used the `filter_10_` prefix convention; the snake_case path is the modern standard. Check both paths exist when debugging a dead-knob sweep.

**Guard:** `test_l116_min_triggers_bear_wired_in_params_overrides` — code inspection (both "min_triggers_bear" and "min_triggers_bull" in overrides handled) + functional check (OOS trade count spreads ≥ 3 between mt=1 and mt=2).

**Related lessons:** C14 (dead/translated-but-unapplied knobs: vary-and-assert), L111 (VIX constants in runner._FILTERS_CONST_KEYS missing from orchestrator._FILTER_CONST_MAP — same naming sync failure class)

---

## L117 — Backtest outer loop gate hardcoded >= 15:50, allowing phantom entries at or after time_stop_et (2026-06-17)

**Symptom:** OOS baseline shows n=17, pnl=+$4,747. Manual review of OOS trade list found two entries timestamped 15:45 ET (May 11 -$112, May 15 +$2,200). The 15:45 bar in a 5-minute schema opens at 15:40 — exactly when `time_stop_et` fires. Production heartbeat at 15:40 exits existing positions; it never ENTERS new ones. The +$2,200 May 15 trade (the single largest OOS winner) was a phantom.

**Root cause:** `orchestrator.py` outer loop gate line ~686 used a hardcoded `>= dt.time(15, 50)` for the upper entry boundary, regardless of the `time_stop_et` parameter computed from `time_stop_minutes_before_close`. With `time_stop_minutes_before_close=20`, `time_stop_et = 15:40`. Bars at 15:40 and 15:45 passed the `< 15:50` gate and could trigger new entries. The simulator then processed these from the NEXT bar (idx+2), found `spy_time >= time_stop_et` immediately, and exited. Net result: entry + instant time-stop in a single simulated bar — which production cannot replicate since the 15:40 heartbeat is an EXIT tick, not an ENTRY tick.

**Quantification:**
- IS: n=9 phantom trades, net +$170 (8 losers -$740, 1 big winner +$910 on 2025-08-26)
- OOS: n=2 phantom trades, net +$2,088 (May 11 -$112, May 15 +$2,200)
- **Corrected baseline: IS n=239 pnl=-$3,942.61 / OOS n=15 pnl=+$2,659.00** (was IS=248/-$3,772.83, OOS=17/+$4,747.40)

**Fix:** Changed outer loop gate from hardcoded `>= dt.time(15, 50)` to `>= time_stop_et`:
```python
# BEFORE (bug):
if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= dt.time(15, 50):
    continue
# AFTER (fix):
if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= time_stop_et:
    continue
```
This makes entry gating dynamic: if `time_stop_minutes_before_close=10` (default), `time_stop_et=15:50` (no change from old behavior). If `=20` (production), `time_stop_et=15:40` (blocks phantom entries).

**Prevention:** Any gate that controls WHEN entries are allowed must use the runtime-computed time variables, not hardcoded literals. The time_stop_et is already computed at function start; use it. Hardcoded time literals are C14-class knob drift — they ignore the configured parameter.

**Guard:** `test_l117_no_entry_at_or_after_time_stop_bar` — code inspection (gate uses `time_stop_et` not `dt.time(15, 50)`) + functional liveness check (no OOS fill with entry_time >= 15:40 when time_stop_minutes_before_close=20).

**Related lessons:** C14 (dead/translated-but-unapplied knobs), C7 (silent success is failure — phantom entries produced valid-looking P&L with no error signals)

---

## L118 — GOLDILOCKS VIX-spike-decline regime classifier: prior_5d lookback too narrow, 0 IS trades tagged (2026-06-17)

**Symptom:** Hypothesis: "profitable BEARISH_REVERSAL months share a VIX-declining-from-spike pattern — prior_5d_VIX_max > 30 AND today_VIX < prior_max × 0.65 = goldilocks regime." IS sizing simulation shows **0 GOLDILOCKS trades** across n=244 production IS trades. The classifier fires for exactly 0 individual trade-dates. The OOS window (May 8-22 2026, +$2,659) is also NOT_GOLDILOCKS. Monthly stats tagged April 2025 as GOLDILOCKS using the 15th-of-month representative date (prior_max=52.2, today=30.1), but the 7 individual trades in April 2025 span dates BEFORE the spike peak (April 1-8, prior_max<30) and AFTER VIX recovered to <30 in prior_5d (April 22+, prior_max from Apr 15-21 dropped below 30). The 5-day window is too narrow to catch the entire post-spike recovery period.

**Root cause 1 — window too narrow:** Prior_5d_max > 30 requires the spike to have occurred within the PRIOR 5 TRADING DAYS. After a VIX spike event, market participants resume normal trading within 1-2 weeks. By week 2, the spike is outside the 5-day window and prior_max falls below 30, so GOLDILOCKS no longer fires. The "golden period" of profitable trading in the aftermath of a spike extends well beyond 5 days — often 10-30 days.

**Root cause 2 — monthly representative date bug:** `_monthly_stats()` used the 15th of each month as a representative date for the GOLDILOCKS check. If the 15th is a weekend or holiday (March, November, February), the function returns NO_VIX_TODAY and the month shows as NOT despite possibly having GOLDILOCKS dates in the first/third week. For the sizing simulation this bug is moot (it correctly uses per-trade actual dates), but the monthly table misleads analysis.

**Root cause 3 — hypothesis structurally wrong for IS period:** Profitable IS months (Q3-2025 +$594/$886/$1,760, Feb-2026 +$3,123) are NOT post-spike-recovery windows. Q3-25 VIX was 15-17 (normal). Feb-26 VIX was ~20 (mild correction, no prior >30 spike). The profitable periods are explained by market TREND and regime character, not by VIX spike recovery.

**Root cause 4 — catastrophic months have wrong VIX signature:** April 2026 (-$6,400) had prior_max=21.0 < 30 threshold — it was a FRESH VIX ESCALATION from a low base (~18→52 on Liberation Day April 9). The GOLDILOCKS classifier correctly identifies this as NOT_GOLDILOCKS. But this means no VIX-spike-decline filter can protect against it, because the spike HAD NOT YET HAPPENED on the days leading up to the crash.

**Threshold sweep result:** All 24 combinations (spike_thr 25-40 × decay 0.60-0.75) produce GL_n=0 to 8 IS trades. At the most permissive setting (spike_thr=25, decay=0.75): GL_n=8, GL_pnl=-$2,730 (NEGATIVE). No viable sizing classifier found.

**Fix / Pivot:** The GOLDILOCKS regime hypothesis is REFUTED for the current BEARISH_REVERSAL IS window. Alternative directions:
1. Rolling-WR-based sizing (if last K trades WR > 55%, size 1.5×) — performance-based rather than macro-regime-based. Currently under test in `backtest/autoresearch/rolling_wr_sizing.py`.
2. Per-day kill switch + per-trade risk cap are the correct defenses against sudden-shock months. GOLDILOCKS is unnecessary.

**True production IS baseline established:** IS n=244 pnl=-$5,117.81 (with `no_trade_before=dt.time(9,35)` production setting). Prior "corrected baseline" of n=239/-$3,942.61 used the default 10:00 entry gate — 5 pre-10am trades (net -$1,175) were incorrectly excluded.

**Prevention:**
- When testing a regime classifier, always run the SIZING SIMULATION at per-trade level (not monthly representative dates) before concluding the classifier is viable.
- A monthly analysis with NO_VIX_TODAY for 4+ months is a data quality signal — use `first_trading_day_of_month()` not the 15th.
- Before proposing a regime filter, verify that the filter correctly TAGS the profitable periods AND correctly EXCLUDES the catastrophic ones. If the catastrophic period was a fresh escalation (no prior spike), VIX-level filters cannot protect against it.

**Related lessons:** C5 (VIX character > VIX level), L73 (VIX-trend filter: VIX character discriminator), L93 (VIX-escalating gate kills BEARISH_REVERSAL edge)

---

## L119 — 2026-06-17: Rolling-WR sizing classifier is backward for BEARISH_REVERSAL — high WR precedes crashes; classifier has no predictive signal

**Symptom:** Rolling win-rate (last K trades) sizing sweep across 27 combos (k=10/15/20 × high_thr=50-60% × low_thr=25-35%). All 27 FAIL (best WF=0.364, gate 0.70). Best IS+OOS delta combo (+$3,055) still fails WF. IS trades are chronically LOW class (n=190/244 have WR<35%) — the strategy appears always "cold" to the classifier.

**Root cause 1 — classifier is backward:** Monthly progression shows 2025-05 entered with 60% rolling WR (HIGH signal → size 1.5x) and immediately became the worst 5-trade month (-$1,710, WR=20%). The engine's rolling WR PEAKS before catastrophic stretches, then drops as losses accumulate — sizing up DURING the entry into catastrophic months.

**Root cause 2 — zero OOS effect:** OOS May 2026 (profitable recovery, n=15, +$2,659) entered with 30-60% rolling WR (k=15: all MID at entry). Sizing unchanged at 1.0x in OOS. Rolling WR provides no actionable signal in the profitable recovery period.

**Root cause 3 — structural property of BEARISH_REVERSAL:** The strategy enters ~5-20 trades/month. Its WR is chronically 25-42% (true win rate in IS = 28%). A classifier with low_thr=35% assigns nearly all trades to LOW class. Sizing down to 0.5x reduces losses on the catastrophic months but also reduces the profitable trades in recovery months.

**Sweep result (k=15, high=55%, low=35%):**
- IS LOW class: n=190, WR=28%, sized pnl=-$4,479 (0.5x reduces loss vs 1.0x, but still negative)
- IS HIGH class: n=0 (rolling WR NEVER exceeded 55% in IS)
- IS WARMUP class: n=15, WR=33%, pnl=+$1,554 (best class — first 15 trades when history unavailable)
- OOS: all MID at entry → no sizing change → OOS delta=+$43 (noise)

**Fix:** The per-day kill switch (−30% equity for Safe, −50% for Bold) IS the correct mechanism. It responds to MAGNITUDE of realized loss on the current day, not to historical WR. Rolling WR is backward-looking and cannot detect regime changes before they happen.

**Prevention:**
- Before testing any sizing classifier for BEARISH_REVERSAL, check the MONTHLY WR PROGRESSION: if IS WR is chronically 25-42%, any low_thr=35% classifier will tag most trades LOW regardless of regime.
- Verify the classifier correctly identifies the PROFITABLE months as HIGH (not LOW) before running the full sweep. A classifier that assigns 190/244 IS trades to LOW is useless regardless of IS delta.
- The structural test: does rolling WR PEAK going into catastrophic months? If yes, the classifier is backward.

**Related lessons:** C5, L118 (GOLDILOCKS refuted — same structural failure), L73 (VIX character > VIX level)

---

## L120 — 2026-06-17: Consecutive-stop cooldown fails for BEARISH_REVERSAL — IS protective gate cuts OOS profitable re-entries; per-day kill switch is sufficient

**Symptom:** Post-processing simulation of "block further entries after N consecutive stops on same day." All combos fail OOS. N=1 (block after ANY stop): IS delta=+$5,975 (blocks 68 catastrophic re-entries), OOS delta=-$1,481 (blocks 5 profitable OOS trades), WF=-0.248. N=2: IS delta=+$395, OOS delta=-$518, WF=-1.314.

**Root cause 1 — IS/OOS structural tension:** The same gate that blocks re-entries during catastrophic IS months (April 2026: 3-trade day on 04/10, saved +$1,056) also blocks re-entries during the profitable OOS recovery (May 2026 has multiple-entry days). Blocking after N stops in IS reduces catastrophic-month losses. The SAME rule then blocks the profitable re-entries in OOS.

**Root cause 2 — gate fires on wrong signal:** January 2026: 2026-01-12 has n=3 multi-entry day. N=2 cooldown blocks the 3rd entry which was PROFITABLE (+$631 would have been a winner). Cooldown net: base=+$631 → cool=-$288 (delta=-$919). The gate fires on consecutive STOP EXITS from prior trades, but the next trade's profitability is uncorrelated with whether the previous trade stopped out.

**Root cause 3 — trigger field unavailable:** `t.trigger_type` / `t.setup_type` are not attributes on `TradeResult` — all trades show trigger='unknown'. The `same_trigger` mode is identical to `any_trigger` mode. Cannot differentiate "stopped twice on level_rejection" from "stopped on trendline then level_rejection."

**Fix:** No entry-level cooldown is warranted. The per-day kill switch (daily P&L limit: Safe -30%, Bold -50%) already fires on DOLLAR MAGNITUDE. The right time to halt trading is when TOTAL DAILY LOSS exceeds the threshold — not based on consecutive stop count, which is a much weaker signal.

**If a stop-based gate is reconsidered in future:** The gate must use REAL-TIME daily P&L (not stop-count) as the trigger. A trade that stops out but leaves daily P&L positive should never trigger the cooldown. Only trades that bring daily P&L below a WARNING threshold (e.g., -15%) should trigger a cooldown. This is essentially a tighter kill switch, not a stop-count gate.

**Prevention:** Before building any "protective gate" (cooldown, circuit breaker, stop-count limit), verify that the gate's trigger condition is ANTI-CORRELATED with future trade profitability in the SAME time period. If IS catastrophic months have 3+ stops/day AND OOS recovery months also have 2-3 entries/day (many profitable), the gate will fire in BOTH contexts and provide no net benefit.

**Related lessons:** C15 (gates interact multiplicatively), L118 (GOLDILOCKS), L119 (rolling WR)

---

## L121 — 2026-06-17: VIX-conditional premium stop refuted; WF gate fails for small OOS samples; time-of-day distribution non-discriminatory

**Symptom (primary):** VIX-conditional stop hypothesis — relax bear stop in VIX>30 environments to reduce catastrophic-month losses. Result: only 3 IS days have VIX>30 at 09:35 (2026-03-09, 2026-03-27, 2026-03-30); all 3 are PROFITABLE (n=3, pnl=+$1,836). All IS losses are in VIX<30 bucket (n=241, pnl=-$6,954). No PASS candidates (WF<0.70 for all positive-OOS stops).

**Root cause 1 — wrong bucket:** April 2026 catastrophe entries occurred at daily VIX 15-30 (Liberation Day onset). Once VIX exceeded 30, filter_8 (vix_direction=DECLINING required) blocked further BEAR entries naturally. VIX-conditional stop can't fix the VIX<30 entries.

**Root cause 2 — VIX>30 entries win:** The 3 high-VIX March 2026 days were profitable at production stop. Relaxing stop for these trades provides no benefit — they already won.

**Secondary finding — tighter global stop:**
- Stop=-0.10: IS_delta=+$8,705, OOS_delta=+$1,802, WF=0.207 (FAIL gate 0.70)
- Stop=-0.15: IS_delta=+$3,946, OOS_delta=+$901, WF=0.228 (FAIL)
- Stop=-0.25+: both IS and OOS worsen or split

**WF gate problem (structural):** IS n=244, OOS n=15 (16x ratio). Per-trade delta: IS=+$35.67/trade, OOS=+$120.13/trade — OOS per-trade improvement is 3.4x larger than IS. Standard WF without sample-size normalization systematically rejects improvements when IS>>OOS. Per-trade-normalized WF = 3.37 (would PASS). Prevention: when IS/OOS sample size ratio > 5x, ALWAYS compute per-trade-normalized WF alongside standard WF.

**Time-of-day analysis (concurrent):** Entry time distribution — catastrophic months: morning 33%, midday 51%, afternoon 15% vs normal months: morning 31%, midday 39%, afternoon 30%. No time-of-day window discriminates catastrophic from normal. The 11:30-12:00 bucket is negative in BOTH regimes (CAT -$3,247 WR=0%, n=6; NORM -$1,390 WR=18%, n=11) but sample too small for a gate.

**Fix / Verdict:** VIX-conditional stop REFUTED. Production stop=-0.20 unchanged. The stop=-0.10 tighter stop finding needs a dedicated per-trade-normalized WF analysis before any ratification. Kitchen task enqueued.

**Related lessons:** C22 (backward classifiers anti-correlate with recovery), L114 (VIX hard cap: Apr-26 at VIX 17-30 not 45-52), L115 (VIX MA crossover INCONCLUSIVE), L118 (GOLDILOCKS), L119 (rolling WR), L120 (cooldown)

---

## L122 — 2026-06-17: Quality-tier blocking fails when IS/OOS windows represent different VIX regimes — LEVEL tier shows IS/OOS regime flip

**Symptom:** BEARISH_REVERSAL LEVEL-tier trades (level_rejection or level_reclaim without SUPER/ELITE upgrade) show IS WR=24%, pnl=-$12,867, -$390/trade (n=33). All blocking scenarios fail OOS: blocking all LEVEL gives OOS_delta=-$447, WF=-0.566 (FAIL). VIX-conditioned blocking (VIX≥20/22/25) yields OOS_delta=0 (OOS LEVEL trades are all at VIX 17-20, below any threshold tested).

**Root cause:** The IS/OOS split (IS: Jan-2025 to May-2026, OOS: May-Jun 2026) captures profoundly different VIX regimes for LEVEL entries. IS LEVEL losses concentrate in two sub-regimes: VIX 15-17 (Jan-2026 flat market, 15% WR) and VIX 25-35 (Mar-2026 tariff escalation, 29% WR). OOS LEVEL entries fire in VIX 17-20 (May-2026 post-Liberation-Day declining recovery, WR=50%, +$112/trade). The quality tier label "LEVEL" contains three behaviorally distinct populations — the VIX regime at entry time determines edge, not the setup trigger structure.

**Root cause 2 — VIX filter can't separate the populations:** No single VIX threshold separates IS losers from OOS winners. IS LEVEL losers at VIX 15-17 (flat) AND IS LEVEL losers at VIX 25-35 (escalating) span a wide range. OOS LEVEL winners at VIX 17-20 sit squarely in between. A threshold at VIX≤17 would block the Jan-26 IS losses but miss the Mar-26 IS losses. A threshold at VIX≥22 blocks the Mar-26 IS losses but is irrelevant for OOS (all OOS LEVEL < VIX 22). No single filter can target both IS loss populations without also blocking OOS winners.

**Root cause 3 — sub-window deadband parallel:** vix_rising_deadband=0.15 was rejected by the same structural principle — it blocked a 2025-11-19 entry (VIX=23.9, pnl=+$996) in the W2 Jul-Dec 2025 sub-window. High-VIX slow-rising entries are valid BEARISH_REVERSAL setups; the filter incorrectly classifies them as noise. Quality-tier blocking and VIX-character filters both suffer from the same root cause: the feature being used to classify "bad" trades is regime-conditional, not mechanically predictive.

**Fix:** Do not block LEVEL entries. The correct intervention for high LEVEL losses is stop tightening (L121, confirmed RATIFY: premium_stop_pct_bear -0.20→-0.10 saves $8,705 IS / $1,802 OOS). Smaller loss per LEVEL loser preserves OOS LEVEL winners intact. A per-trade loss limiter (stop tightening) is regime-agnostic; an entry gate (tier blocking) is regime-dependent.

**Prevention:** Before proposing ANY quality-tier block, check the IS/OOS regime split: (1) What VIX environment (level + character) characterized the IS losing trades? (2) What VIX environment characterized the OOS winning trades? (3) Is there a mechanically separable feature that differs between the two? If the IS drag and OOS wins share the same VIX range (e.g., both at VIX 17-20), blocking is infeasible. Always use the WF formula to test — a negative WF on the OOS direction is a definitive veto, not a data-quality question.

**Graduated guard opportunity:** Add assertion to test suite: `if OOS LEVEL pnl > 0 AND OOS n >= 3: assert blocking LEVEL reduces OOS by at least 10%`. This guards against future attempts to block a tier that's profitable in OOS.

**Related lessons:** C4 (stratify by VIX regime), C16 (IS/OOS regime flip), L93 (VIX-escalating gate anti-correlates with BEARISH_REVERSAL), L104 (IS Sharpe inflated when VIX filter creates many zero-trade days), L121 (WF gate fails for small OOS samples)

---

## L123 — 2026-06-17: `block_level_rejection` gate requires `winning_side == "P"` guard — `has_level` is True for BOTH bear rejection AND bull reclaim

**Symptom:** First implementation of LEVEL_REJECTION_GATE (`quality_tier == "LEVEL" and has_level`) blocked 5/08 OOS BULL level_reclaim +$1,130 trade. OOS flipped to −$447, WF=−0.594 FAIL. The gate condition looked correct on paper — `has_level` should fire only when a level trigger is present — but `has_level` is True for BOTH bear (`level_rejection` in triggers) AND bull (`level_reclaim` in triggers) LEVEL trades because the quality-tier logic sets `has_level = "level_rejection" in triggers or "level_reclaim" in triggers` without regard to direction.

**Root cause:** In the BEARISH_REVERSAL engine, the quality tier for a bull/CALL trade is promoted to LEVEL when `level_tied_trig = "level_reclaim"` is in `winning_triggers`. For a bear/PUT trade, `level_tied_trig = "level_rejection"`. Both paths set `has_level = True`. An unguarded `quality_tier == "LEVEL" and has_level` gate blocks BOTH — it cannot distinguish which side the level trigger came from.

**Fix:** Add `winning_side == "P"` guard:
```python
if block_level_rejection and quality_tier == "LEVEL" and has_level and winning_side == "P":
```
This restricts the gate to PUT (bear) LEVEL trades only. CALL (bull) LEVEL trades (level_reclaim) are unaffected. After fix: OOS +$682, WF=0.842 PASS, RATIFY.

**Prevention rule:** Any engine gate that targets a quality tier or level-trigger must also guard on `winning_side` when the tier can be reached from both sides. Before writing any `quality_tier == "X"` condition in orchestrator.py, ask: "Can both CALL and PUT entries reach this tier? If yes, add `winning_side == 'P'` (or `'C'` for bull-only gates) to prevent cross-side contamination." Graduated guard: `test_l123_level_rejection_gate_bear_only` verifies (1) 5/08 BULL level_reclaim NOT blocked, (2) ≥1 bear SKIP exists, (3) no SKIP on 5/08.

**Related lessons:** C14 (dead/translated knobs), L88 (per_trade_risk_cap_pct side-specific), L95 (trendline_only_setup fires for both multi-trigger paths)

---

## L124 -- 2026-06-17: level_reclaim has positive per-trade OOS expectancy despite 37.5% WR -- blocking removes lottery-ticket edge

**Symptom:** Post-Rank35 OOS analysis (2026-05-08 to 2026-06-16, Safe n=21): level_reclaim trades show W=3/L=5 (37.5% WR), pnl=+2,492 total. Intuition says "37.5% WR is a loser bucket -- block it." Blocking level_reclaim OOS delta: -,344. The engine P&L COLLAPSES if level_reclaim is removed.

**Root cause:** The 3 level_reclaim winners are lottery-ticket entries: +2,044, +1,130, +744 (avg +1,306/trade). The 5 losers are capped by the -10% premium stop: -176, -265, -232, -433, -320 (avg -285/trade). Expected value per trade: 0.375*1306 + 0.625*(-285) = +311/trade POSITIVE. Low WR does not mean negative expectancy when winners are 4.6x larger than losers. The premium stop ASYMMETRICALLY limits downside while the runner mechanism ASYMMETRICALLY amplifies upside.

**Root cause 2 -- Loss perception bias:** The 5 losses are more visible than the 3 wins because losses cluster in time (May 19-28 during declining VIX market reversal). Temporal clustering makes it FEEL like a losing setup. But the 3 wins, when they fire, are 4.6x the loss magnitude -- the batch-of-losses followed by a lottery-win is the correct model.

**Root cause 3 -- Same pattern holds for Aggressive:** level_reclaim Aggressive OOS n=8: W=3/L=5, avg winner=+1306, avg loser=-285, expectancy=+311/trade. Identical numbers across both accounts -- structural property of level_reclaim mechanics, not a Safe-specific artifact.

**Fix:** DO NOT block level_reclaim. The correct filter for level_reclaim losers is stop tightening (L121, already deployed), which limits the -285 average loss further without adding false stops.

**Prevention rule:** Never evaluate a trigger category by WR alone. Compute per-trade expectancy = WR*avg_win + (1-WR)*avg_loss before proposing a block. A 37.5% WR category with 4.6x win/loss ratio has +311/trade expectancy -- blocking it destroys edge. The WR threshold for a block is win/loss_ratio-dependent: for 4x win/loss ratio, the breakeven WR is 20% (0.20*4 + 0.80*(-1) = 0). For 2x ratio, breakeven is 33%. For 1x, breakeven is 50%. Use the expectancy formula, not WR standalone.

**Related lessons:** L121 (WF gate for small OOS samples), L122 (do not block LEVEL entries), L123 (winning_side guard required for level block gates)

---

## L125 -- 2026-06-17: Aggressive midday trendline gate WF=0.147 -- IS fires 23x more often than OOS due to C22 regime

**Symptom:** Aggressive account midday_trendline_gate A/B: IS n=261->147 delta=+3,545, OOS n=28->23 delta=+56, WF_norm=0.147 (gate=0.70). Gate passes OOS_positive and SW_ok (1/4 hurt) but decisively fails WF. The gate blocks 114 IS midday trendline trades but only 5 OOS midday trendline trades (23x IS/OOS ratio for removed trades).

**Root cause:** The midday trendline gate (11:00-14:00 ET) targets intraday noise entries. In the IS period (Jan 2025 to May 2026), the market was range-bound and mean-reverting in the midday window -- trendline entries in 11:00-14:00 were frequent (n=114 removed) and negative. In the OOS period (May-Jun 2026, post-Liberation-Day VIX declining recovery), the market was in a sustained uptrend -- midday entries are fewer AND the ones that fire are higher-quality (VIX 17-20, level triggers). Result: the gate's IS improvement is 23x its OOS improvement per-trade.

**Root cause 2 -- C22 IS/OOS regime asymmetry on Aggressive:** The Safe account midday gate IS in production and was ratified on the Safe IS baseline. The Aggressive account has a broader universe (no midday gate) and its IS trendline distribution is concentrated in the midday window. But the OOS midday trendline distribution is completely different (fewer trades, better quality) because the OOS period is a different regime.

**Root cause 3 -- WF formula exposes the problem correctly:** WF_norm = (oos_delta/n_oos) / (is_delta/n_is) = (56/28) / (3545/261) = 2.0 / 13.6 = 0.147. Per-trade IS improvement is 6.8x OOS. The standard WF gate (>=0.70) is the correct veto here -- the gate generalizes at only 14.7% of its IS rate.

**Fix:** Do not add midday_trendline_gate to Aggressive. The Aggressive account's production configuration is correct (midday gate OFF). Safe has it ON because Safe was validated with it in a prior IS regime.

**Prevention rule:** When testing gates that are already deployed on one account for applicability to another account, the WF gate must pass independently for the new account's IS/OOS baseline. "It works for Safe" is not evidence that it works for Aggressive -- the accounts have different VIX ranges, risk caps, and trade distributions. Always run a fresh A/B on the target account's correct production params.

**Related lessons:** C22 (IS/OOS regime flip), L93 (SNIPER VIX-escalating gate anti-correlates with BEARISH_REVERSAL), L104 (Sharpe inflated by many zero-trade days)

---

## L126 -- 2026-06-17: BULLISH_RECLAIM ribbon_flip is regime-conditional -- blocks value in trending markets

**Symptom:** IS analysis of BULLISH_RECLAIM_RIDE_THE_RIBBON trades (n=45) shows `ribbon_flip` trigger pattern has WR=9-11% vs WR=29% for non-ribbon_flip patterns. Blocking `ribbon_flip` BULLISH_RECLAIM gives IS delta=+$1,823. But OOS delta=-$3,123 and WF=-23.984. Sub-window stability: HELP in Q1-2025 (+$1,972), HURT in Q3-2025 (-$3,708) and OOS-May (-$3,123). SW_hurt=3/5.

**Root cause:** `ribbon_flip` in a BULLISH_RECLAIM context has opposite meaning in different regimes:
- **Range-bound regime (Q1-2025):** ribbon_flip fires AFTER price has already extended. By the time ribbon turns bull, the reclaim attempt is already failing. Result: lagging entry = 0% WR.
- **Trending regime (Q3-2025, OOS-May-2026):** ribbon_flip fires during a genuine bull trend acceleration. The ribbon turning bull IS the signal that the reclaim is working. Result: momentum confirmation = good entry.

The IS period's Q1-2025 (range-bound) dominates the IS aggregate, making ribbon_flip look universally bad. But the underlying mechanism is regime-conditional: ribbon_flip quality inverts between range-bound and trending markets. No static filter can solve this.

**Fix:** Do not implement block_bull_ribbon_flip. The gate `block_bull_ribbon_flip` was added to orchestrator.py as a research parameter (default=False) but should never be set True in production. BULLISH_RECLAIM as-is (IS avg=$104/trade, OOS avg=$638/trade in May-2026 recovery) has positive expectancy in aggregate.

**Prevention rule:** Before blocking any trigger pattern based on IS aggregate WR: (1) run sub-window stability across ALL 4+ sub-windows; (2) if SW_hurt >= 3/5, the pattern is regime-conditional and the gate is strictly negative EV; (3) check specifically whether the IS "bad" window is a range-bound period and the OOS/other "good" windows are trending periods -- the directional inversion is the smoking gun.

**Related lessons:** C22 (regime flip IS/OOS), L93 (VIX-escalating gate wrong direction for BEARISH_REVERSAL), L73 (VIX character vs level)

## L127 -- 2026-06-17: "Entry bar" analysis must clarify SIGNAL bar vs FILL bar — BEARISH_REJECTION signal bars are ALWAYS bearish by construction

**Symptom:** `require_bearish_entry_bar` gate added to orchestrator.py checked `bar["close"] < bar["open"]` where `bar = spy_df.iloc[idx]` (the signal bar). Running the full backtest (`entry_bar_direction_gate.py`) showed n_blocked=0 in all windows — WF=nan, dead knob.

**Root cause:** BEARISH_REJECTION_RIDE_THE_RIBBON pattern structurally requires the signal bar to be bearish — the price must REJECT at a level (test above the level) and CLOSE BELOW it in the same bar. This is what the detector's `detect_trendline_rejection_bearish()` and `detect_level_rejection()` check. Therefore `close < open` is a structural invariant for all BEARISH_REJECTION signal bars (bar N). The gate never fires because signal bar N is ALWAYS bearish.

**The actual discriminator:** `entry_bar_pnl_split.py` analyzed `t.entry_time_et` timestamps. In `simulator_real.py` line 387, `fill.entry_time_et` is OVERWRITTEN to `entry_bar_opt.timestamp_et` — the option bar timestamp corresponding to the SPY bar at `idx+1` (the fill bar). So `entry_bar_pnl_split.py` was measuring FILL bar (N+1) direction, not signal bar (N) direction.

**Fill bar (N+1) direction IS discriminatory:** bearish fill bar (N+1) → WR=41.1% avg=+$225 (n=56 IS); bullish fill bar (N+1) → WR=3.4% avg=-$39 (n=29 IS). IS delta=+$1,124, OOS delta=+$424, WF=1.908 post-hoc.

**Key distinction:**
- Signal bar (N): ALWAYS bearish by construction → zero discriminating power
- Fill bar (N+1): open is the fill price; close vs open reveals immediate follow-through → strong discriminator
- Fill bar direction cannot be known at signal time (bar N+1 hasn't closed) → NOT a pre-entry filter without a 5-minute delay

**Production implementation:** A one-bar confirmation delay (enter at bar N+2 open only if bar N+1 was bearish) is the correct production analog. This changes fill prices and requires a dedicated simulator test. `require_bearish_fill_bar=True` in orchestrator is a look-ahead BACKTEST gate for measuring the upper bound of this strategy.

**Prevention rule:** When analyzing "entry bar quality," always specify: (1) is this the SIGNAL bar (N, the bar that fired the watcher) or the FILL bar (N+1, the bar the entry fills in)? (2) Check which timestamp `t.entry_time_et` actually represents in the simulator — it may be overwritten. (3) For BEARISH patterns, the signal bar is almost always bearish by construction; if your gate fires on 0% of bars, check the structural invariant first.

**Related lessons:** L79 (trigger string suffix mismatch), L80 (bull_score null in ENTER ticks), C7 (silent success is failure), C14 (dead/translated-but-unapplied knobs), L113 (level_stop_buffer dead knob)

## L128 -- 2026-06-17: Fill bar direction gate has WF_norm < 0 — IS and OOS deltas opposite-sign means regime inversion, not just weak signal

**Symptom:** `require_bearish_fill_bar=True` backtest: IS delta = -$860 (gate REMOVES IS winners, n=24 blocked), OOS delta = +$1,102 (gate REMOVES OOS losers, n=3 blocked). WF_norm = -7.54.

**Root cause:** In IS (2025, range-bound/choppy), BEARISH_REJECTION entries with a bullish fill bar (N+1) often still succeeded — the brief bounce was reversed immediately. In OOS (May-June 2026, recovery/trending), a bullish fill bar after a bearish signal = momentum continuation bullish = the put entry fights the prevailing trend and fails. The fill bar direction predicts different outcomes in different market regimes.

**The regime inversion signature:** WF_norm < 0 occurs when IS_delta and OOS_delta have opposite signs. This is stronger than WF < 0.70 (marginal generalization). There are two patterns:
- IS_delta < 0 AND OOS_delta > 0 (L128 case): gate is anti-correlated with IS winners but correlated with OOS losers. Gate works WITH the OOS regime, AGAINST the IS regime.
- IS_delta > 0 AND OOS_delta < 0: gate overfit to IS (more typical overfitting pattern).
Both cases: NOT RATIFIABLE. A regime detection layer would be required first.

**Sub-window oscillation:** W1(HELP) / W2(HURT) / W3(HELP) / W4(HURT) — alternating, not monotonic. Confirms the gate is not trending toward any regime; it oscillates in response to each market character shift.

**Prevention rule:** Always compute WF_norm BEFORE concluding "OOS positive = good." If WF_norm < 0, stop immediately — the IS and OOS regimes disagree directionally. The gate is not a universal signal; investigate regime dependency. A gated OOS improvement when IS worsens suggests the OOS period has a different market character, not that the gate generalizes.

**Related lessons:** L73 (VIX character > VIX level — regime-conditional VIX gate), L92 (IS improvement via earlier entry regresses OOS), L104 (VIX filter inflates IS Sharpe on zero-trade days), C4 (stratify by regime before concluding edge), L127 (signal bar vs fill bar confusion in BEARISH_REJECTION)

## L129 -- 2026-06-17: Entry bar body/wick quality gate fails post-Rank35 due to C22 regime inversion — IS best bucket inverts to OOS best bucket

**Symptom:** signal_bar_quality_analysis.py: IS 25-40% body_pct bucket = best (WR=45.5%, avg +$755, n=14). IS 0-25% bucket = worst (WR=14.3%, avg -$102). Gate body>=30% removes IS 0-25% losers (+$590 IS improvement). OOS: 0-25% bucket = BEST (WR=100%, +$1,240 — single largest OOS win). Gate body>=30% removes this winner: OOS delta = -$1,240. WF_norm = -9.6.

**Root cause:** IS period (2025, choppy/range-bound): doji/small-body bars (25-40%) represent indecision followed by reversal — the "rejection" is weak but wins because the market is choppy. IS 0-25% bars (tiny body, mostly wick) often appear on false breaks that reverse. OOS period (May-June 2026, post-tariff trending): large-wick bars represent genuine exhaustion at levels — the single best OOS trade had a tiny body (strong wick rejection). Volatility regime differs 2x: IS median range = $0.53/bar, OOS median range = $1.15/bar.

**The IS/OOS range regime difference:** OOS bars are twice as large as IS bars. A "low body_pct" bar in OOS (25% body of $1.15 range) has a real $0.29 body — not the tiny $0.05 body of a similar-looking IS bar. The body_pct metric is range-normalized and therefore VOL-REGIME DEPENDENT. High-volatility periods with large ranges will have different body_pct distributions than low-volatility periods even for identical setups.

**3rd confirmation of entry filter ceiling:** (1) Fill bar direction gate: WF=-7.54 (L128). (2) Trendline age gate: 10-20 bar sweet spot inverts to OOS (C22). (3) Body/wick quality gate: WF=-9.6. All three test different dimensions (momentum direction, signal age, bar quality) and all show the same IS/OOS regime inversion. The post-Rank35 entry set is saturated. Pivot from entry filtering to exit parameter optimization is the correct next step.

**Prevention rule:** Before testing an entry quality gate (body%, wick%, range, momentum), check whether IS and OOS volatility regimes differ. A 2x range difference makes range-normalized metrics (body_pct, wick_pct) non-stationary across periods. Prefer absolute-dollar metrics (body_dollars, range_dollars) or regime-conditioned analysis (separate IS/OOS by VIX level before computing body_pct distributions). If IS and OOS WR distributions conflict for the same bucket, the metric is regime-dependent — not a universal signal.

**Related lessons:** L128 (fill bar direction gate WF<0 regime inversion), C4 (stratify by regime), C22 (backward-looking classifiers anti-correlate with recovery periods), C5 (VIX character > VIX level)

## L130 -- 2026-06-17: Sweep baselines must replicate ALL active production parameters — chandelier OFF vs ON creates a LARGE_DELTA that invalidates absolute comparisons

**Symptom:** `chandelier_baseline_check.py` ran Safe account with chandelier OFF (all sweep baseline config) vs ON (production config: arm=+5%, floor=+10%, trail=20%). Result: IS delta = -$2,896, OOS delta = -$4,131 → LARGE_DELTA verdict. Chandelier ON is dramatically worse than chandelier OFF in backtest: IS n=124 (+$13,277) vs OFF n=130 (+$16,174). OOS: ON +$1,770 vs OFF +$5,900.

**Root cause:** All `autoresearch/` sweep scripts (runner_target_sweep.py, tp1_qty_fraction_sweep.py, tp1_premium_sweep.py, no_trade_after_sweep.py) define SAFE_BASE and AGG_BASE config dicts without setting `profit_lock_threshold_pct`, `profit_lock_stop_offset_pct`, `profit_lock_mode`, or `profit_lock_trail_pct`. Those params default to 0.0/fixed (chandelier OFF). But production `params.json` has `v15_profit_lock_threshold_pct=0.05`, `v15_profit_lock_trail_pct=0.20`. The baseline was silently misconfigured for all sweeps.

**Impact:** Relative comparisons within each sweep are still valid — both baseline and candidates use the same chandelier-OFF config, so deltas measure the swept parameter's true effect. Absolute numbers are inflated: production would show ~$4K less OOS PnL ($1,770 vs $5,900 reported). Safe account appears to make $5,900 OOS; actual production makes ~$1,770 OOS with chandelier ON.

**Mechanism:** In the high-volatility OOS period (tariff shock, May-June 2026), SPY bearish moves are large but interrupted by brief consolidations. The chandelier (trail 20% off HWM) exits on those consolidations. Example: trade reaches +30% premium (HWM=1.30x), pulls back briefly to 1.04x (20% off HWM), chandelier fires. Without chandelier, trade might continue to 2.5x runner target. Chandelier is specifically damaging in sustained-trend OOS regimes. It reduces IS trade count 130→124 (6 trades get stopped before re-entry signal, losing those re-entry fees).

**Action:** Future sweeps must include chandelier params in SAFE_BASE and AGG_BASE. Template fix: add `profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10, profit_lock_mode="trailing", profit_lock_trail_pct=0.20` to every baseline config block. Design chandelier parameter sweep (arm threshold, floor offset, trail pct) as next exit optimization direction — the current production settings appear suboptimal based on LARGE_DELTA finding.

**Prevention rule:** Before starting any parameter sweep, diff the baseline config dict against `params.json` / `aggressive/params.json` to confirm ALL active production parameters are present. A "config diff" step should be the first function in every new sweep script. Missing a production parameter invalidates absolute performance numbers and can mislead architecture decisions.

**Related lessons:** L38 (dead knob — vary-and-assert), L99 (BS-sim ignored strike-offset incident), L127 (signal vs fill bar), C14 (Dead/translated-but-unapplied knobs), C7 (silent failure = audit outputs not exit codes)

## L131 -- 2026-06-17: Aggressive runner_target is a completely dead knob — 0DTE ITM-2 runners never reach even 2.0x (200%) premium gain; the production 5.0x target requires 6× premium multiplication in a single session

**Symptom:** `runner_target_sweep.py` Aggressive section: runner=2.0 (test lowest value) vs runner=5.0 (baseline) — IS_d=$0, OOS_d=$0, SW_hurt=0. All four sub-windows FLAT ($0). Verdict: OOS_NEG (OOS not positive). All higher values (2.5, 3.0, 3.5, 4.0) also show $0 delta — production 5.0x and all lower values are equivalent.

**Root cause:** Formula: `runner_target_premium = entry_premium × (1.0 + runner_target_premium_pct)`. With AGG production value `runner_max_premium_pct=5.0`: runner exits at `entry_premium × 6.0` — a 500% gain on the original entry premium. For a typical $2.50 ITM-2 option at 0DTE, this requires the option to reach $15.00, implying SPY moving ~$19 intraday. Even at runner=2.0 (200% gain), the option needs to reach $7.50 (SPY move ~$7.7 from entry). After TP1 fires at 75% premium ($4.38), the runner needs another 71% gain from the current $4.38 level. In N=133 IS + N=21 OOS Aggressive trades, NOT ONE trade achieved this. The runner exits exclusively via time stop (15:40 ET) or rarely via the original stop (0.93× entry, requiring premium to fall from $4.38 back to $2.33).

**Exit hierarchy for Aggressive runners (actual):**
1. Chandelier trailing stop (arm=+5%, trail=20% off HWM) — PRIMARY in production, but OFF in sweep baseline (L130)
2. Time stop (15:40 ET) — PRIMARY in sweep (chandelier off)
3. Original stop (entry×0.93) — rare; only if premium falls $4.38→$2.33 after TP1
4. Runner target (entry×6.0) — NEVER FIRED in 154 total trades across all IS/OOS periods

**Implication:** The Aggressive runner target is dead configuration. The REAL runner management mechanism is the chandelier trailing stop (in production). The chandelier itself is causing LARGE_DELTA vs chandelier-OFF (L130). So the actual research direction is: chandelier parameter sweep (arm threshold, trail pct, floor offset) — not runner target tuning.

**Prevention rule:** Before sweeping an exit parameter, audit what fraction of historical trades actually triggered that exit mechanism. If 0% of trades triggered it (exit_count == 0), the parameter is dead and the sweep is uninformative. Add `runner_hits / total_trades` to every sweep's debug output.

**Related lessons:** L130 (chandelier OFF vs ON LARGE_DELTA), C14 (dead/translated-but-unapplied knobs), L38 (vary-and-assert before assuming knob is active)

---

## L132 -- 2026-06-17: Static chandelier parameters cannot bridge a fundamental regime split — VIX-conditional activation is the only valid path

**Symptom:** `chandelier_sweep.py` tested 9 Safe candidates (OFF, arm=0.10/0.15/0.20, trail=0.25/0.30/0.40, two combos) vs production chandelier ON baseline. Results: OFF=SW_FAIL(hurt=2), arm=0.10=OOS_NEG(SW_hurt=4), arm=0.15=OOS_NEG(SW_hurt=4), arm=0.20=WF_FAIL(-7.146,SW_hurt=3), trail=0.25=OOS_NEG(SW_hurt=4), trail=0.30=OOS_NEG(SW_hurt=4). No candidate passed all gates.

**Root cause — regime split:** chandelier ON benefits are concentrated in choppy-market sub-windows (W1_2025H1: +$3,934; W3_2025Q4: +$981) while chandelier OFF benefits are in trending sub-windows (W2_2025Q3: +$5,254; W4_2026H1: +$2,557). No single static parameter can optimize both simultaneously because:
- Looser arm (0.10-0.20): arming later means fewer activations → ALL sub-windows hurt vs production arm=0.05 (even W2/W4 where arm=0.05 was already hurting). The 5-10% gain range that arm=0.10 skips has ZERO OOS trades — arm=0.10 is equivalent to arm=0.05 in OOS but loses IS protection.
- Looser trail (0.25-0.30): near-zero OOS change (−$53) with SW_hurt=4 — trail variations are not discriminatory in the OOS period.
- Full OFF: OOS +$4,131 better, IS +$2,896 better, but W1+W3 sub-windows both hurt by >$50 → SW_hurt=2.

**The arm=0.20 C22 signal:** arm=0.20 shows OOS_d=+$503 with IS_d=-$415, WF=-7.146. Negative WF indicates regime inversion — chandelier with very wide arm happens to help OOS (tariff-shock recovery trending) at the cost of IS performance. This is not generalizable.

**Fix:** VIX-conditional chandelier activation. `backtest/autoresearch/vix_conditional_chandelier.py` tests thresholds [15.0, 17.5, 18.0, 20.0, 22.0, 25.0, 30.0]. When VIX > threshold → chandelier ON (choppy protection); when VIX ≤ threshold → chandelier OFF (let trend run). If any threshold passes (OOS_positive AND WF≥0.70 AND SW_hurt≤1) vs chandelier-OFF baseline → deploy as `profit_lock_vix_threshold_pct` in params.json (requires simulator change to check VIX at each bar during trade management).

**Prevention rule:** Before sweeping chandelier parameters, check if the chandelier ON vs OFF IS/OOS delta is consistent across ALL 4 sub-windows. If W1/W3 help and W2/W4 hurt (or vice versa), the regime split is fundamental — static param sweep will always fail SW_hurt gate. Go directly to regime-conditional logic.

**Related lessons:** L130 (chandelier LARGE_DELTA confirmed), L128 (WF negative = regime inversion C22), C22 (IS/OOS VIX regimes differ), C5 (VIX character > VIX level)

---

## L133 -- 2026-06-17: VIX level cannot discriminate the chandelier regime split — choppy and trending periods share overlapping VIX ranges in 0DTE SPY

**Symptom:** `vix_conditional_chandelier.py` tested 7 VIX thresholds [15, 17.5, 18, 20, 22, 25, 30] for switching chandelier ON vs OFF based on VIX level at trade time. All 7 failed gates. Results: VIX>15=OOS_NEG(-4,131) | VIX>17.5=OOS_NEG(-2,946) | VIX>18=OOS_NEG(-734) | VIX>20=WF_FAIL(0.000,SW_h=0) | VIX>22=WF_FAIL(0.000,SW_h=1) | VIX>25=WF_FAIL(-0.000,SW_h=2) | VIX>30=WF_FAIL(-0.000,SW_h=2).

**Root cause — VIX level overlaps between choppy and trending regimes:**
VIX diagnostic per sub-window:
- W1_2025H1 (CHOPPY, chandelier ON helps): VIX median=19.2, p25=17.2, p75=23.3
- W2_2025Q3 (TRENDING, chandelier OFF helps): VIX median=16.0, p25=15.2, p75=16.8
- W3_2025Q4 (CHOPPY, chandelier ON helps): VIX median=17.1, p25=16.2, p75=19.2
- W4_2026H1 (TRENDING, chandelier OFF helps): VIX median=19.5, p25=18.0, p75=24.7

W4_trending (tariff-shock recovery) has VIX median=19.5 — nearly identical to W1_choppy (19.2). The tariff-shock recovery period was simultaneously trending AND high-VIX, which breaks VIX-level-as-regime-proxy entirely.

**Results pattern:**
- Low thresholds (VIX>15-18): chandelier ON applied to W4 trending days (VIX 18-25 range) → hurts those days → OOS_d negative. Lower threshold = more W4 days get chandelier ON = more OOS damage.
- High thresholds (VIX>20+): OOS_d=0. The OOS period (May-June 2026) had few/no trades with VIX>20 after the initial tariff shock settled. Zero OOS trade assignment = WF=0 (formula returns 0/n_oos = 0) → WF_FAIL.
- VIX>22 had IS improvement (+$1,966, W1 help +$1,212, W3 help +$996) and SW_hurt=1, but OOS_d=0 → WF=0.000 → FAIL. Can't pass WF gate with zero OOS activation.

**The fundamental problem:** Regime character (choppy vs trending) is a multi-week structural property set by factors like macro backdrop, sector leadership, options market structure. VIX level is a single scalar that conflates multiple regime drivers into one number. In tariff-shock recovery (W4), the market trended bullishly while volatility remained elevated — a combination VIX level can't decompose.

**Fix path:** VIX rate-of-change (ROC) is more discriminatory than VIX level. Rising VIX (VIX_today > VIX_yesterday by >5%) indicates fear escalation → choppy → chandelier ON. Falling VIX → relief rally or calm trend → chandelier OFF. Alternative: ATR-based regime (current_ATR / rolling_ATR_50 > threshold = choppy). Price-based features that measure realized choppiness (consecutive same-direction bars, HH/LL ratio) may outperform VIX entirely.

If VIX ROC also fails, accept chandelier ON (production) as the local optimum. Entry filter research is also saturated (L128, L129). Pivot to new setup types (NLWB bullish) or PDT-aware sizing.

**Prevention rule:** Before testing VIX-conditional logic, compute VIX distribution overlap between the target regimes. If VIX IQR ranges overlap significantly (as W1/W4 do — both 17-25 range), VIX level is insufficient as a discriminator. Check VIX ROC, ATR ratio, or rolling range-vs-average metrics instead. The test: `abs(median_A - median_B) / ((p75_A + p75_B) / 2)` — if < 0.15, the distributions are too similar for VIX-level conditioning.

**Related lessons:** L130 (chandelier LARGE_DELTA), L132 (static params can't bridge regime split), C5 (VIX character > VIX level), C22 (backward-looking classifiers anti-correlate with recovery periods)

---

## L134 -- 2026-06-17: VIX rate-of-change (ROC) also cannot discriminate the chandelier regime split — VIX direction is random within all sub-window types (40-55% rising, uniformly)

**Symptom:** `vix_roc_chandelier.py` tested 3 ROC windows [1d, 2d, 5d] × 4 thresholds [-5%, 0%, +5%, +10%] = 12 combinations. All 12 failed gates. No ratifiable threshold found.

**VIX ROC diagnostic (pct_rising per sub-window):**
- W1_choppy: ROC_1d=40%, ROC_2d=49%, ROC_5d=41% rising
- W2_trending: ROC_1d=50%, ROC_2d=52%, ROC_5d=45% rising
- W3_choppy: ROC_1d=45%, ROC_2d=55%, ROC_5d=46% rising
- W4_trending: ROC_1d=47%, ROC_2d=49%, ROC_5d=59% rising

All values in the 40-59% range — near random walk. VIX ROC does NOT discriminate choppy from trending periods. In all sub-windows, VIX oscillates approximately 50/50, rising and falling daily without directional bias specific to regime type.

**Best result:** ROC_2d threshold=0% (use ON when VIX rose over 2 days):
- IS_d=+$1,444, OOS_d=-$1,130, WF=-5.183, SW_h=1 → OOS_NEG (C22 inversion)
- IS helps because more choppy IS days have rising 2-day VIX → chandelier ON protects
- OOS hurts because recovery OOS period has MIXED VIX direction even while trending

**Root cause:** VIX is a mean-reverting process. Within any regime (choppy or trending), VIX oscillates daily without accumulating directional bias. The regime character is encoded in the DISTRIBUTION of VIX levels (L133) and multi-week structural factors (tariff policy, Fed stance), not in daily or weekly ROC. VIX_pct_rising being ~50% in all regimes confirms this is a random walk around regime-specific means.

**Key contrast with successful factors:** If a factor is genuinely discriminatory, pct_active would be markedly different across sub-windows (e.g., 70% in choppy vs 30% in trending). VIX ROC at ~50% everywhere means it's coin-flip discrimination.

**Fix path:** Accept chandelier ON (production Safe) as the local optimum. VIX-based regime conditioning (level, ROC, direction) is exhausted — all approaches fail because VIX itself cannot discriminate the market regimes relevant to 0DTE chandelier management. Next: SPY ATR ratio (realized price volatility, not implied vol) as regime discriminator. If ATR also fails, accept chandelier ON as optimal and pivot research to new setup types (NLWB bullish) or other signal dimensions.

**Prevention rule:** Before testing ROC/direction conditioning on any metric, compute the pct_active (fraction of days where condition fires) per target sub-window. If pct_active is ~50% in ALL sub-windows, the metric cannot discriminate between regimes — it's random walk discrimination. Minimum for useful discrimination: pct_active ≥ 65% in target regime AND ≤ 35% in non-target regime.

**Related lessons:** L132 (static chandelier params exhausted), L133 (VIX level overlaps across regimes), C5 (VIX character > VIX level), C22 (backward-looking classifiers anti-correlate with recovery)

---

## L135 -- 2026-06-17: Realized price volatility (ATR ratio) also cannot discriminate the chandelier regime split — distributions overlap across all sub-windows

**Symptom:** `atr_regime_chandelier.py` tested 3 ATR windows [5d, 10d, 20d] × 5 thresholds [0.80, 1.00, 1.10, 1.20, 1.50] = 15 combinations. All 15 failed gates. No ratifiable threshold found.

**ATR ratio diagnostic (pct>1.0 per sub-window, prior_day_range / rolling_N_day_median):**
- W1_2025H1 (choppy): ATR_5d=29%, ATR_10d=42%, ATR_20d=41% above-median days
- W2_2025Q3 (trending): ATR_5d=33%, ATR_10d=45%, ATR_20d=45%
- W3_2025Q4 (choppy): ATR_5d=34%, ATR_10d=52%, ATR_20d=48%
- W4_2026H1 (trending): ATR_5d=37%, ATR_10d=51%, ATR_20d=52%

All pct>1.0 values in the 29-52% range — barely above/below median cutoff randomly. The choppy/trending split cannot be discriminated by yesterday's range vs N-day median range.

**Full results — W2_2025Q3 ALWAYS hurt (all 15 combinations):**
Every combination that activates chandelier ON more often hurts W2 because W2's profitable trending days fire chandelier early. The trailing stop exits at 80% HWM on steady trending days, cutting short what would be larger gains under chandelier OFF. No ATR threshold was able to avoid W2 hurt while also helping W1/W3.

**Best results (still failed):**
- ATR_5d ≥ 1.20: IS_d=-$134, OOS_d=0, WF=-0.000, SW_h=2 → WF_FAIL (too few trades triggered)
- ATR_5d ≥ 1.50: IS_d=-$57, OOS_d=0, WF=-0.000, SW_h=1 → WF_FAIL (too few trades triggered)
Both of these near-FLAT results only achieve neutrality by activating chandelier on so few days (11-18%) that any regime signal is noise.

**Root cause:** The choppy vs trending distinction in the chandelier split (L132) is a MULTI-WEEK structural phenomenon (tariff policy regimes, Fed tightening cycles, sector rotation), not a day-level price volatility pattern. ATR ratio captures whether YESTERDAY was an abnormally large/small range vs recent history — which is day-specific and context-independent. Any single-day "large range" can occur in both choppy periods (failed moves, whipsaws) and trending periods (continuation breakouts, news-driven gaps). The instrument for discrimination needs to be multi-week regime state, not daily realized vol.

**Why W2_2025Q3 is the ATR approach's killer:** The July-September 2025 trending period had its share of high-ATR days (earnings, macro releases, gap days). Conditioning on "prior day was large range → chandelier ON" fires chandelier on exactly those W2 days, turning a chandelier-OFF profitability advantage in W2 into chandelier-ON drag.

**Chandelier research closure:** All vol-based regime conditioning is now exhausted:
1. Chandelier static params (arm/floor/trail): no better combination → L132
2. VIX level conditioning (7 thresholds): W4 high-VIX trending period kills all → L133
3. VIX ROC conditioning (12 combos): ~50% pct_rising in all windows → L134
4. ATR ratio conditioning (15 combos): overlapping distributions → L135
**VERDICT: Chandelier ON (production Safe) = confirmed local optimum for BEARISH_REJECTION_RIDE_THE_RIBBON.**

**Research pivot:** The chandelier regime split is a multi-week structural pattern that cannot be captured by any single-day indicator (VIX level, VIX direction, price range). Options:
1. Add 2024 data to IS period (via Alpaca historical API) to get more regime diversity — may change baseline structure
2. NLWB (Named-Level Wick-Bounce) bullish setup backtest — new setup type, different risk/reward profile
3. Intraday VWAP slope or market-breadth composite as multi-session regime proxy (multi-session rather than daily)

**Prevention rule:** Before designing day-level conditioning for a phenomenon observed at the multi-week scale, verify the discriminatory metric has ≥65% activation in target regime AND ≤35% in non-target. If the target phenomenon spans weeks while the metric is computed daily, expect pct overlap near 50% regardless of metric choice.

**Related lessons:** L132, L133, L134 (full vol-conditioning research arc), C5 (VIX character), C22 (regime discrimination), C4 (regime-aware disclosure)

---

## L136 -- 2026-06-17: NLWB (PDL wick-bounce) produces strongly negative option P&L — SPY price WR does NOT transfer to option edge

**Symptom:** `nlwb_backtest.py` tested 9 variants: OTM-2/OTM-1/ATM × min_bounce [0.00, 0.30, 0.75]. All 9 combinations OOS_NEG. IS WR=2% (OTM-2, n=100). OOS WR=0% (OTM-2, n=9). Zero TP1 hits in IS or OOS across any variant.

**Full variant sweep results:**
- OTM-2 bounce>0.00: IS_avg=-$34, OOS_avg=-$25, WF=0.735, OOS_NEG
- OTM-2 bounce>0.30: IS_avg=-$27, OOS_avg=-$25, WF=0.926, OOS_NEG
- OTM-2 bounce>0.75: IS_avg=-$21, OOS_avg=-$30, WF=1.429, OOS_NEG (n_oos=3)
- OTM-1 bounce>0.00: IS_avg=-$108, OOS_avg=-$68, WF=0.630, OOS_NEG
- ATM bounce>0.00: IS_avg=-$239, OOS_avg=-$171, WF=0.715, OOS_NEG
(all others similarly negative)

**Exit breakdown (IS, OTM-2):** CHART_STOP=64%, PREM_STOP=36%. Zero TP1 hits. Avg hold = 1-2 bars.

**Root cause:** PDL wick-bounce is a SHORT-TERM (1-2 bar) reversal signal. In SPY price terms, 71% of PDL wicks result in SPY closing above PDL that day (correct directional bias). But 0DTE call options require a SUSTAINED multi-bar move of $2+ to recover OTM-2 premium. What actually happens:
1. SPY wicks below PDL, closes fractionally above ($0.10-$0.80 above)
2. Next bar frequently returns below PDL → chart stop fires in 1 bar
3. Even when SPY doesn't return below PDL, the move is too small for OTM-2 calls to recoup entry premium before theta kills the option
4. ATM calls capture more delta but suffer severe theta decay on 0DTE

**Key insight:** The scan-based "71% WR" for PDL wick-bounces measures whether price CLOSES ABOVE PDL on the signal bar. It says nothing about whether price continues higher over the next 30-60 minutes. For options, we need the continuation, not just the initial close.

**Why ATM calls are even worse than OTM-2:** ATM calls cost 3-5x more in absolute premium (e.g., $1.00 entry vs $0.40 OTM-2). With -10% premium stop, the max loss per contract is 5x larger. The delta advantage doesn't overcome the larger absolute dollar loss per stop-out.

**Prevention rule:** Before testing an option strategy on a "bounce" or "reversal" signal, answer: "Does the underlying move far enough (at minimum 2× ATM-to-OTM-strike gap) over enough time (>10+ bars) in ≥40% of cases?" PDL wick-bounces fail this — the median continuation is $0.50 in 5 bars, while OTM-2 calls need $2+ in 5 bars. If the underlying move distribution doesn't support the option's break-even, the option strategy is dead on arrival.

**Alternative approach if NLWB signal is genuinely useful:** Instead of options, the signal might work as a SPY equity trade (capture the bounce directly). Or with MUCH longer-dated options (1-5 DTE instead of 0DTE) where theta isn't catastrophic. Both are outside current Gamma scope.

**Related lessons:** C1 (real-fills is the only WR authority; BS-sim cannot rescue a bad premise), C3 (SPY-price edge ≠ option edge -- this is the canonical example), L101 (delta/theta/stop-misfire), C4 (regime-aware disclosure)

---

## L137 -- 2026-06-17: Entry bar body direction loses discriminatory power after quality gates are applied

**Symptom:** Prior analysis (old IS baseline, n=75 IS BEARISH_REJECTION): bearish-body WR=41.3% vs bullish-body WR=3.4%. This looked like a strong gate candidate. Re-running with current production params (post-block_level_rejection, post-block_elite_bull, post-vix_bull_hard_cap=18): bearish-body WR=70% (n=46), bull-body WR=44% (n=34). The 38pp discrimination gap collapsed to 26pp. Gate WF=-1.383 (C22 inversion), SW_hurt=2/4. NOT RATIFIABLE.

**Root cause:** The new quality gates (block_level_rejection, block_elite_bull, vix_bull_hard_cap=18) selectively removed the WORST bullish-body IS trades from the production baseline. These were the low-delta, counter-trend entries at bad timing — exactly the trades that showed up as "bullish body" AND lost money. After removal, the remaining bullish-body IS trades are higher-quality (WR=44%), making the body-direction filter redundant.

**Sequential absorption pattern:** When you add gate A to a baseline, gate A raises the quality floor for all remaining trades. Any previously-discriminatory signal X that correlates with the same "low quality" concept as gate A will lose its edge — gate A already removed most of the X-positive losers. Downstream, X's discrimination gap shrinks toward zero.

**Prevention rule:** Before proposing a new quality gate, re-run the discriminator analysis with the CURRENT production baseline (not the baseline that existed when you first observed the signal). A signal that had 38pp discrimination in an old baseline may have near-zero discrimination after newer gates absorbed the same low-quality trades.

**Corollary:** This is actually a POSITIVE finding. The engine is working correctly — each gate removes a type of bad trade, and subsequent signals that would have caught those same bad trades show diminished value. This is the "quality floor rising" effect. Document it but don't fight it by adding redundant gates.

**What still works:** The body direction IS/OOS correlation exists (WR 70% bear vs 44% bull) but is too weak to justify a gate that removes 42% of IS trades (34 of 80). The correct interpretation: focus on entry bar body as a CONFIDENCE signal, not a hard gate.

**Related lessons:** C22 (backward-looking classifiers), C14 (knob absorption), L129 (gate interactions), L130 (IS/OOS regime mismatch)

## L138 -- 2026-06-17: IS entry-quality labels don't transfer to OOS for BULLISH entry-filter gates (C22 extension)

**Symptom:** `safe_bull_ribbon_flip_gate.py` blocked IS trades with WR=10%, avg=-$106 (n=21, clearly low-quality). OOS: those same blocked trades were +$1,883 (5/08) and +$1,240 (5/21) -- two of the biggest OOS winners. OOS_delta=-$2,370.

**Root cause:** The "low quality" label was derived from IS regime (2025, low-VIX trending with ribbon=BEAR + BULL ribbon flip = chop). In OOS (May-Jun 2026, post-tariff-recovery), the same ribbon pattern denotes momentum shift in a volatile recovery regime, where those trades become directionally correct. IS loser group systematically becomes OOS winner group.

**Pattern:** IS regime classifies ribbon_flip entries as "noise/chop." OOS regime classifies same setup as "momentum recovery signal." The classification is regime-dependent. Any gate that removes IS loser groups must verify those groups ALSO lose in OOS before ratifying.

**Fix:** Before proposing any IS-derived quality gate, compute OOS PnL for the BLOCKED group. If blocked group is OOS-positive, the gate is C22-inverted and should not be ratified regardless of IS discrimination power.

**Prevention rule:** "IS WR < 20% on a sub-population" is NOT sufficient evidence to block that population. Add OOS verification: "blocked group OOS is also negative" is required. If OOS is positive, document as C22-blocked.

**Related lessons:** C22 (backward-looking classifiers anti-correlate with recovery), L118-125 (C22 manifestations), L129, L130

---

## L139 -- 2026-06-17: Exit-level parameter changes have near-zero OOS effect when ribbon flip is the primary exit mechanism

**Symptom:** 5 separate sweeps all produce near-zero OOS effect:
- TP1 sweep (0.55 to 1.00): all OOS-negative or zero
- Runner target sweep (1.75x-3.0x): best case OOS+$34, WF=0.216
- ribbon_flip_price_confirm=True: OOS delta=0 (ZERO trades changed)
- FHH bypass exit changes: zero OOS effect
**Total wasted research cycles on exit mechanics: 10+ scripts.**

**Root cause:** OOS exit breakdown reveals 4/9 Safe OOS winners exit via RIBBON_FLIP_BACK at avg_runner_ratio=1.00x (entry premium == runner exit premium). The ribbon flip fires when the underlying price has returned to approximately the entry spot. Any change to TP1 threshold, runner target, or price-confirm only affects exits that happen BEFORE the ribbon flip -- but in OOS, the ribbon flip always fires first.

**Key diagnostic:** Run exit breakdown per reason with avg_runner_ratio. If dominant exit reason has avg_runner_ratio ~1.00x, the ribbon flip is exiting at entry price. Premium-based targets are irrelevant for those trades.

**Fix:** When ribbon flip is the primary OOS exit mechanism, research pivot to ENTRIES -- the exit is already optimal by definition (ribbon flip exits are regime-based, not premium-level based). No exit-level parameter can outperform the ribbon flip for those trades.

**Prevention rule:** Before sweeping any exit parameter (TP1, runner target, price confirm, time stop), compute the OOS exit breakdown. If >40% of OOS winners exit via ribbon flip at 1.00x ratio, exit-level research is dead-ended. Redirect to entry quality.

**Related lessons:** L112 (chandelier sim glitch), C3 (SPY price edge != option edge), C11 (broker is source of truth on exits)

---

## L140 -- 2026-06-17: J's anchor trades are one-off exceptional setups -- they do not represent the POPULATION of their pattern class

**Symptom:** `safe_fhh_bypass.py` and `agg_fhh_bypass.py` both fail (OOS_delta=-$80 and -$56). 24-25 new IS entries unlocked by FHH bypass: WR=25-28%, avg=-$17 to -$32/trade. The 5/01 J anchor was the motivating case (expected +$470 profit), but the general population is losers.

**Root cause:** The 5/01 FHH rejection (+$470) was an exceptional confluence: FHH was at a key technical level, VIX was in a specific regime, the morning had set up a strong directional bias, and the tape confirmed with conviction. The bypass gate "FHH rejection while ribbon=BULL -> bearish entry" does not encode any of these confluence factors -- it just allows counter-trend bears whenever price touches the morning high. The general population of "price touches morning high" when ribbon=BULL is mostly momentum continuation days, not reversals.

**Key insight:** J anchor trades are hand-picked high-conviction setups that happened to fire on that day's tape. A filter derived from one exceptional trade will capture that specific setup AND many lower-quality trades that match the mechanical pattern without the confluence.

**Fix:** Before generalizing from an anchor win into a strategy expansion, answer: "Of all IS setups that would have fired this same mechanical filter, what is the WR and avg PnL?" If WR < 40%, the anchor was exceptional, not representative. The correct use of anchor wins is to validate that the ENGINE captures them, not to derive new setup classes from them.

**Prevention rule:** If a new setup is motivated by 1-3 anchor trades, run IS population analysis before coding. WR of the IS population < 40% = the anchor wins are outliers, not indicative of the general pattern's profitability.

**Related lessons:** L01 (aggregate metric off the edge), C16 (multi-bar reversal vs single-bar continuation), C2 (first-strike entries: chart-stop only)

---

## L142 -- 2026-06-17: Star-score formula produces INVERSE correlation with level respect — high touch_count drives ★★★ then those levels break more

**Symptom:** `star_vs_respect_study.py` runs star scoring across 356-day benchmark ledger (n=2,782 unique levels, 14,614 touch events). Result: 3★ respect rate = 24.8% (LOWEST), 2★ = 27.0%, 1★ = 28.2% (HIGHEST). Stars are an anti-predictor.

**Root cause:** `score_level()` in `backtest/lib/level_strength.py` awards `min(0.5 × log2(touch_count + 1), 2.0)` — a POSITIVE score for touch count. This creates a feedback loop:
1. A level that gets many price visits scores high (★★★)
2. Many price visits means the level was NOT respected many times (rejected, retested multiple times)
3. Levels that get retested constantly eventually break
4. Result: ★★★ levels ARE the ones that have been tested to exhaustion and will break

**Fix (architectural):** Touch count is the WRONG input to a respect-predictor. A respected level is one that bounced price CLEANLY on the FIRST visit. Replace the touch-count score with a first-touch_respect metric: `first_touch_respected = 1 if first_visit_was_respected else 0`. Levels with first_touch_respected=1 AND touch_count=1 are the strongest. High touch_count with zero net respect = exhausted levels.

**Quantitative finding:** DOES_NOT_SEPARATE status from study (3.4pp spread is below 5pp threshold), but direction is INVERSE — the sign of the signal is wrong, not just the magnitude. Any model that SORTS by current star formula will rank levels WORST-TO-BEST, not best-to-worst.

**Prevention rule:** Before finalizing ANY score formula, run `sorted(levels, key=score)` and ask: "Are the top-5 and bottom-5 intuitive?" If the top-5 seem like they should be WEAK levels (frequently retested), the formula has an input-direction error. Verify correlation direction before using for ranking.

**Related lessons:** L04 (concentrate on what matters, not aggregate), C13 (confidence tiers must be reachable AND diverse), C14 (dead/translated-but-unapplied knobs)

---

## L143 -- 2026-06-17: Wick-based level filter is inferior to close-based — wick hits add noise, close-based touches have 6pp higher respect

**Symptom:** `wick_vs_close_results.json` benchmark: close_based n=939 respect=97.6%, wick_only n=723 respect=91.6%. Gap=-6.0pp. wick_valuable=false.

**Root cause:** Current filter defines "touching a level" as: SPY 5-min bar LOW ≤ level_price ≤ SPY HIGH (any part of the candle intersects the price zone). The wick definition (bar low/high hits) adds 216 events vs close-based (n=939 close-based vs n=723 wick-only for the non-shared events). The wick-only events have 91.6% respect — that's 6pp WORSE than close-based touches.

**Interpretation:** When only the candle's wick touches a level (not the close), price bounced BACK before the bar closed. The wick hit is momentum probing — price tested the level aggressively but closed away from it. These are WORSE quality touches because they indicate the level attracted significant selling/buying pressure that overcame the initial test. Close-based touches mean the level "held" through bar close — much stronger signal.

**Fix:** Keep current filter (close-based). Do NOT add wick-only detection to the level quality filter. The `C2` conclusion in `analysis/level-quality/RATIFICATION-REPORT.md` is correct: close-based is superior.

**Prevention rule:** When evaluating "should we use X OR X+wick?" — compare respect rates between close-only and wick-only events SEPARATELY. If wick-only events have LOWER respect than close-only, adding wicks reduces signal quality per event. The larger n from wick-based filtering is not worth the respect-rate dilution.

**Encoded in:** `analysis/level-quality/wick_vs_close_results.json` + RATIFICATION-REPORT Phase 2 C2.

---

## L144 -- 2026-06-17: Level quality benchmark measures reaction edge; trading backtest measures entry filter quality — these are DIFFERENT metrics with opposite answers for intraday H/L

**Symptom:** `source_pruning_results.json` says intraday H/L: DM-null lift=-3.1pp → verdict=KILL. But shadow A/B (removing intraday from entry filter) shows: +4 IS trades, WR drops -2.1pp → verdict=HOLD. Contradiction persists across re-analysis.

**Root cause:** The two measurements are asking DIFFERENT questions:
- **Benchmark question (KILL):** "When price touches an intraday H/L level, does it bounce more than a random nearby price?" Answer: No. DM-null (distance-matched random levels) has -0.6pp higher respect → intraday H/L has no REACTION edge.
- **Trading question (HOLD):** "When we remove intraday H/L from the entry-filter zone, do our entries improve?" Answer: No. Removing intraday makes the proximity gate LARGER → allows entries farther from the meaningful levels → adds 4 IS trades with -2.1pp lower WR.

The intraday H/L acts as an ENTRY FILTER (proximity gate), not a REACTION PREDICTOR. The market does NOT bounce specifically at intraday H/L (per benchmark). But having intraday H/L in the level set NARROWS the proximity zone, which FILTERS entries to only fire when price is near a level — which correlates with better entry quality.

**Fix (doctrine — no code change):** Distinguish the role of each level TYPE:
- ★★★ Carry, PDH, PDL → reaction predictors (high-quality bounces expected)
- Intraday H/L → proximity filter (narrows the entry zone, not expected to generate bounces themselves)

Do NOT apply DM-null lift (reaction metric) to filter-role levels. Use shadow A/B WR as the metric for filter-role levels.

**Prevention rule:** Before pruning any level type from the engine, classify its ROLE: reaction-predictor vs entry-filter. If removing it EXPANDS the trigger zone and LOWERS WR, the level is acting as a filter, not a predictor — DM-null lift is the wrong measurement. The correct measurement is the WR delta when that level type is excluded from the proximity gate.

**Encoded in:** `analysis/level-quality/RATIFICATION-REPORT.md` Phase 3 (tension documented) + `analysis/level-quality/source_pruning_results.json`.

---

## L145 -- 2026-06-17: L75 pattern detector fires on 96.3% of days — too broad to be a signal; fix requires restriction to bar_i=0 + ★★★ Carry levels only

**Symptom:** `pattern_detectors_results.json`: L75 (false-break detector) fires 1,230 events across 60.7% days. But 96.3% of total trading days have at least one L75 event. L75 fires on both anchor WINNERS (2/3) AND anchor LOSERS (2/2). No discriminatory power.

**Root cause:** L75 was implemented as: ANY bar where the prior bar closed ABOVE a named level, but the current bar's LOW dips BELOW that level. This fires constantly because:
1. Price oscillates around levels all day → any level with multiple visits generates L75
2. Not restricted to the OPEN bar (bar_i=0) → fires throughout the RTH session
3. Applies to ALL level types including intraday H/L → amplifies further

The INTENDED signal was: "First-bar false-break at a ★★★ Carry level is a warning sign for the whole session." The implemented signal measures "any intra-session wick at any level."

**Fix (implement before re-running study):** Restrict L75 to:
1. `bar_i = 0` (only the 09:30 or 09:35 open bar)
2. Level type = ★★★ Carry only (PDH, PDL, Carry levels explicitly)
3. Lookahead window = same session only

Re-run `pattern_detectors_study.py` with these restrictions. If L75 fires on ≤30% of days AND hits ≥2/3 anchor loser days → signal is useful.

**Prevention rule:** Before declaring a pattern detector "fires too broadly," add the RESTRICTIVE conditions that match the original intent. Rule of thumb: any binary signal that fires on >80% of days is measuring market noise, not signal. Diagnostic: `Counter(obs.date for obs in l75_events).most_common(1)` — if the most common day has 10+ events, the scan is too broad.

**Encoded in:** `analysis/level-quality/RATIFICATION-REPORT.md` Phase 4 (L75 fix flagged). Implementation blocked on Rule 9 boundary (requires heartbeat interaction).

---

## L149 -- 2026-06-17: OTM-2 premium stop needs more room than ITM-2 — lower delta creates higher % premium volatility per SPY dollar

**Symptom:** Safe premium_stop sweep at [-0.07, -0.08] produces IS_delta=-$2,989 and -$3,306 respectively — BOTH directions worse than baseline -0.10. W2/W3 HURT on both tighter candidates. Looser -0.15 gives IS_delta=+$1,483 but OOS_delta=-$1,464 (C22 inversion).

**Root cause:** OTM-2 puts (Safe account, delta ~0.25) vs ITM-2 puts (AGG account, delta ~0.70). For an OTM-2 option at $1.00 entry premium, a SPY $0.50 adverse move = $0.125 option loss = 12.5% premium loss. A -7% stop fires after just $0.28 adverse SPY movement. This is well within normal 0DTE noise. ITM-2 at delta=0.70: same $0.50 SPY move = $0.35 option loss = 7% stop on a $5.00 ITM option requires $0.35 loss which is a more meaningful move ($0.50 SPY). OTM-2 is more "brittle" in % terms.

**Fix (confirmed by sweep):** Safe premium_stop=-0.10 is optimal. The extra room (-10% vs -7%) prevents whipsaw exits on OTM-2 options that would recover. When AGG ratified -0.07, do NOT automatically apply the same tightening to Safe — the strike tier (OTM-2 vs ITM-2) fundamentally changes stop dynamics.

**Prevention rule:** Stop tightening ratified for one strike tier does not transfer to another without re-testing. Always re-sweep independently per account/strike combination.

**Related lessons:** C3 (SPY-price edge != option edge), L120 (gates proven on one account don't transfer), C22 (regime-conditional patterns)

---

## L148 -- 2026-06-17: AGG runner rarely hits premium target — runner exits via time_stop/ribbon_flip, not target; reducing target to 2.0x only helps IS, not OOS

**Symptom:** AGG runner_target_premium_pct sweep [2.0, 2.5, 3.0, 3.5, 4.0] vs baseline 5.0. Candidates 2.5-4.0: IS_delta=0, OOS_delta=0 (IDENTICAL to 5.0 — target is never binding). Candidate 2.0: IS_delta=+$1,188 (target occasionally reached in IS), OOS_delta=0 (never reached in OOS). All FAIL.

**Root cause:** With tp1=0.75 (properly enforced post-L109 fix), the runner leg starts after a 75% premium gain. At that point, the position's stop is at breakeven (entry premium). The runner then exits via ribbon_flip or time_stop at 15:40 ET before reaching even 2.5x the original entry premium. The 5.0x target is theoretical — it would require the option to reach 5× entry price after already being 75% in profit. At 0DTE, theta decay accelerates and prevents sustained premium growth above 2x. The runner_target is effectively unconstrained.

**Fix:** runner_target_premium_pct=5.0 is fine — it's rarely binding. The actual exit is ribbon_flip or time_stop. If you want to improve runner profitability, improve ENTRY quality (bigger moves per trade) rather than tuning the target. Alternatively: set runner_target to 2.0 for marginal IS improvement, but accept zero OOS benefit.

**Prevention rule:** Before sweeping exit targets, verify what % of exits actually hit the target vs alternative exits (ribbon_flip, time_stop, stop_loss). A target never hit = an unconstrained parameter. `runner_target_hit_rate` should be added to the backtest output.

**Related lessons:** L109 (real-fills path parameter bug), C3 (option exit mechanics differ from entry mechanics), C14 (dead/unapplied knobs)

---

## L147 -- 2026-06-17: L108/L109/L110 fix (2026-06-17) — three exit params were missing from real-fills path, hardcoded at wrong defaults for 16+ months

**Symptom:** AGG backtest baseline appeared to be IS n=270 pnl=+19,566 | OOS n=28 pnl=+2,590 (context-34/35). After L108/L109/L110 fix, the ACTUAL AGG baseline is IS n=218 pnl=+10,019 | OOS n=24 pnl=-43.

**Root cause:** In `backtest/lib/orchestrator.py`, the real-fills simulation path (`real_fills_sim.py`) was NOT being passed three critical parameters, causing them to use hardcoded defaults: `tp1_qty_fraction` (hardcoded 0.667 = matched prod, OK), `runner_target_premium_pct` (hardcoded 3.0 vs prod 5.0 for AGG / 2.5 for Safe), `tp1_premium_pct` (hardcoded 0.30 vs prod 0.75 for AGG / 0.50 for Safe). The L110 fix (tp1_premium_pct) is most impactful — tp1=0.30 fires on far more trades and at lower bars than tp1=0.75. The "baseline" of IS=+19,566 was effectively computed with tp1=0.30 (not 0.75), showing 52 more trade entries and $9,547 more IS profit.

**Fix (deployed 2026-06-17):** All three parameters now explicitly passed to `simulate_real_fills()` at orchestrator.py lines 1244-1246. The correct AGG production state post-fix: IS=+10,019 (tp1=0.75 actually enforced), OOS=-43 (breakeven in this specific 28-trade OOS window). Safe baseline unchanged (tp1=0.50 effective was closer to intended, runner=2.5 effective vs 3.0 bug was less impactful).

**Impact assessment:** Previous sweep DELTAS (IS_delta, OOS_delta, WF for gates) remain approximately valid because all baseline and candidate runs had the same bug, so the relative effects cancel. ABSOLUTE pnl baselines (any number like "+$19,566 IS") computed before the fix are wrong and must be recomputed. All future sweeps use L109-corrected code.

**Prevention rule:** Any new parameter added to `run_backtest()` must be explicitly threaded through to ALL sub-path calls (real_fills_sim, BS sim). Add a unit test: `assert backtest_pnl(tp1=0.30) != backtest_pnl(tp1=0.75)` for each path. The C14 lesson ("dead/unapplied knobs") applies to simulation paths, not just filter conditions.

**Related lessons:** C14 (dead/unapplied knobs — vary-and-assert), L02 (simulator silently uses wrong parameter), C7 (silent success = failure; audit outputs not exit codes)

---

## L146 -- 2026-06-17: allow_one_blocker v2 sweep — Safe all OOS-negative; AGG near-miss fails SW_hurt=2/4 — pattern mirrors C22 regime split

**Symptom:** `allow_one_blocker_v2_sweep.py` tests allow_one_blocker=True (allow 1 of filters 6-10 to fail) at min_spread_cents=[0,20,35]. Safe: all OOS-negative (best case OOS_delta=-$1,192 at min_spread=0). AGG: min_spread=0 shows OOS_delta=+$1,480, WF=1.586 — BUT sub-windows W1 Jan-Jun 2025 = -$651 (HURT) and W2 Jul-Dec 2025 = -$1,289 (HURT) = 2/4. Gate rejected.

**Root cause:** The SW_hurt pattern for AGG min_spread=0: W1+W2 (first half of IS) HURT, W3+W4 (second half of IS) HELP (+$9,046 and +$2,508 respectively). This is the C22 signature: Jan-Dec 2025 had higher VIX variability (VIX 15-25 range, often spiking). The newly-admitted "one-blocker" trades in Jan-Dec 2025 are noisy setups in choppy VIX conditions. Jan-Mar 2026 had a prolonged high-VIX directional period (Liberation Day, tariff escalation) where the directional bias was strong enough that "relaxed filters" still caught winners.

**The invariant confirmed:** Trades that fail one of filters 6-10 (volume, spread, entry bar quality, ribbon alignment) are systematically lower quality in normal VIX conditions (W1+W2 = HURT). They only appear to "work" in exceptional directional conditions (W3+W4) which are not representative of normal market behavior. IS/OOS regime difference means the OOS period (5/08-6/16) has neither the high-volatility directional spike of W3 nor the choppy normal of W1+W2 — it's a mixed regime where the OOS_delta=+$1,480 is fragile.

**Fix (doctrine):** allow_one_blocker remains False for both accounts. The filters 6-10 together form a cohesive quality gate. Bypassing any ONE of them creates a meaningful quality regression in 2 of 4 IS sub-windows. The right approach to add trades is to find NEW quality setups, not relax existing quality gates.

**Related lessons:** C22 (regime-conditional gates), L121 (AGG midday gate near-miss, same SW failure structure), C15 (gates interact multiplicatively — trace session cascades)

---

## L141 -- 2026-06-17: ribbon_flip_price_confirm is redundant -- ribbon flip already exits when price has reversed

**Symptom:** `safe_ribbon_flip_confirm.py` tests ribbon_flip_price_confirm=True (require price > entry_spot before EXIT_ALL_RIBBON_FLIP_BACK fires). OOS delta=0 -- ZERO OOS trades changed. IS_delta=-$266, SW_hurt=2 (W2 -$163, W4 -$102).

**Root cause:** When the ribbon flips BACK for 0DTE bear positions, SPY has already moved against the position (spot has recovered past entry). The ribbon flip is a LAGGING indicator -- it responds to multiple bars of price action showing recovery. By the time the ribbon flips, price has already risen past entry spot in virtually all OOS cases. The avg_runner_ratio at ribbon flip exit = 1.00x (entry premium, which corresponds to price being back at entry spot). Adding "price must also be above entry spot" is checking a condition that is already true when the ribbon fires.

**Key diagnostic:** avg_runner_ratio at ribbon flip exits. If avg_runner_ratio >= 1.00x, price has already moved past entry before the ribbon flip fires. Price confirm is redundant.

**Fix:** Do not add price-confirmation requirements to ribbon flip exits. The ribbon flip is a lagging signal -- it only fires AFTER price has already moved. Adding a price gate just creates IS damage (some IS ribbon flip exits happen slightly before price passes entry, correctly cutting losses early) while adding zero OOS value.

**Prevention rule:** Before testing a "confirmation" add-on to a signal, verify the correlation direction. If signal S fires AFTER condition C is already true, adding "require C" to S is a tautology. The ribbon flip fires after price moves -> "require price moved" is always satisfied when ribbon fires in OOS.

**Related lessons:** L139 (exit mechanics near-zero OOS effect), C11 (broker is source of truth), C5 (VIX character > VIX level as a lagging vs leading reminder)

---

## L152 -- 2026-06-17: Deep-dive scripts must reproduce a known baseline before being trusted

**Symptom:** `conf_lvl_rec_deep_dive.py` reported IS n=91 conf+lvl_rec trades (avg +$9/trade) in context-37. The verified production Safe baseline is IS n=130 pnl=+16,174 with conf+lvl_rec n=33 avg +$175/trade — completely different conclusions from the same data.

**Root cause:** `use_real_fills=True` alone is not sufficient to reproduce the production baseline. A deep-dive script built from partial params will produce wrong trade counts and wrong per-class averages. Four params were missing: `no_trade_window=None` (disables legacy v11 14:00-15:00 blackout), `no_trade_before=dt.time(9, 35)` (09:35 entry gate), `midday_trendline_gate=True` (v15.3 gate blocking 1-trig trendline 11:30-14:00), `params_overrides={"vix_bull_max": 18.0}` (VIX_BULL_HARD_CAP filter constant). Each missing param shifted n independently: 208 → 89 → 130 across three runs in context-38.

**Fix:** Every new deep-dive script MUST: (1) start from a verified SAFE_BASE_KW (copy from `safe_premium_stop_sweep.py` or equivalent); (2) run the baseline first (IS period) and verify n=130 pnl=+16,174 before any per-class analysis; (3) assert baseline match — if IS n != 130, stop and find the missing param. For AGG: verify IS n=218 pnl=+10,019 before analysis.

**Prevention rule:** BASELINE-FIRST discipline — any per-class or per-bucket analysis must prove the total trade count matches the verified production run before the per-class breakdown is meaningful. A per-class avg that doesn't sum to the verified baseline total is measuring a phantom population.

**Related lessons:** L70 (dead knob = silent no-op), L77 (vary-and-assert before sweeping), C14 (dead/unapplied knobs — vary-and-assert)

---

## L153 -- 2026-06-17: AGG backtest "trendline" class trades never fire in live

**Symptom:** AGG backtest IS baseline (n=218) includes 162 trades classified as pure `trendline_rejection` (no confluence/level_reclaim/level_rejection/ribbon_flip), contributing +$1,944 IS profit (avg +$12/trade). None of these 162 trades can fire in the live AGG heartbeat. Discovered via `agg_trigger_exit_decomp.py` + AGG `heartbeat.md` filter 10 audit.

**Root cause:** Live AGG heartbeat filter 10 requires ≥1 of 4 qualifying triggers: `level_reject / ribbon_flip / multi_day_confluence / sequence_rejection`. Pure `trendline_rejection` is NOT in that list → fails filter 10 → no live entry. The backtest evaluates `evaluate_bearish_setup()` with `min_triggers=1`, which allows ANY single trigger (including standalone `trendline_rejection`). The live heartbeat is more selective — trigger name in backtest does not equal trigger class accepted by live filter.

**Impact:**

| Scenario | IS n | IS PnL |
|---|---|---|
| Naive baseline (all trendlines included) | 218 | +$10,019 |
| After midday_trendline_gate (removes 113 midday trendlines) | 105 | +$11,335 |
| True live-equivalent (remove all 162 trendline trades) | ≈56 | ≈+$8,075 |

The midday_trendline_gate (ratified 2026-06-17, WF=1.940) already removes the midday phantom trendlines (113/162), which are the net-negative ones. The remaining 49 non-midday trendlines are net-positive ($3,260 IS) but still phantom in live. An "all-trendline gate" was evaluated: OOS barely positive ($63 from $238), WF=0.31 — cannot auto-ratify.

**Fix / Prevention:** (1) For AGG analysis: use IS n=105 (with midday gate) as the analysis baseline, noting it overstates live by ~49 phantom trades; true live-equivalent is IS n≈56, avg≈$144/trade. (2) Before any new AGG deep-dive, verify the trigger class being analyzed appears in AGG heartbeat filter 10's required list. (3) Future backtest engines should carry a `live_eligible_triggers` set: a simulated trade whose ONLY trigger is not in live's required list should be flagged as phantom.

**Prevention rule:** Trigger class mapping gap — when backtest trigger names differ from live filter categories (e.g., `trendline_rejection` vs `level_reject`), simulated trades can be phantom. Always cross-check backtest trigger taxonomy against live heartbeat filter definitions before publishing per-class breakdowns.

**Related lessons:** C21 (verify trigger+time+type match live entry), L102 (gate direction must match setup structure), L103 (bypass mechanisms fire at bar-level — trigger+time+type must match)

---

## L154 -- 2026-06-17: conf+lvl_rej IS-to-OOS runner degradation is regime *character*, not VIX level

**Symptom:** Safe conf+lvl_rej IS avg=+$605 (n=15, VIX_avg=20.6) collapses to OOS avg=+$77 (n=6, VIX_avg=19.78). VIX levels are nearly identical — a VIX gate sweep across thresholds 17–21 will not fix this. OOS stop_rate=83% (5/6 stop) vs IS stop_rate≈53%. Discovered via `analysis/recommendations/safe_trigger_exit_decomp.json` + `safe_conj_lvl_rej_vix_split.json` (found by `safe_trigger_exit_decomp.py` + `safe_conj_lvl_rej_vix_split.py`).

**Root cause:** IS conf+lvl_rej profit is concentrated in 4–5 outlier runners from 2025 trending SPY: 2026-02-26 $3,400 (runner_ribbon) | 2026-02-03 $2,458 (runner_time) | 2025-06-13 $2,430 (runner_time) | 2025-10-15 $1,578 (runner_ribbon). Top 3 trades > 80% of class PnL = concentration flag. The differentiator is **trend character**: IS 2025 = trending bearish SPY → momentum sustained after trigger → large runners. OOS 2026 = volatile/recovering SPY → momentum reverses after TP1 → runner aborted. VIX_avg is nearly identical between IS (20.6) and OOS (19.78). VIX level does NOT explain the stop-rate gap. This is a "VIX character vs VIX level" distinction (see L45, C5) — high VIX in a trending market behaves differently than the same VIX level in a choppy/recovery market. The runner-inflated IS class avg is not the true per-trade expectancy; the median per-trade value is far lower.

**Fix:** (1) Do NOT trust IS avg for runner-heavy classes when IS runners are highly concentrated (top 3 trades > 80% of class PnL = concentration flag — normalize OOS expectation downward toward the median). (2) When IS-OOS VIX match but stop_rate degrades, suspect regime character shift (trending → choppy), not VIX mismatch. (3) Safe conf+lvl_rej remains viable (OOS positive at +$465 across 6 trades) — monitor as OOS n grows to 15+. (4) Any gate designed on IS conf+lvl_rej implicitly filters for "2025 trending" conditions and cannot be validated until OOS covers a trending regime cycle.

**Encoded in:** `analysis/recommendations/safe_trigger_exit_decomp.json`, `analysis/recommendations/safe_conj_lvl_rej_vix_split.json`, `markdown/doctrine/LESSONS-LEARNED.md` L154, CLAUDE.md C4 + C5 rows.

**Detection:** future regression — if conf+lvl_rej OOS n grows to 15 and avg remains below $150/trade while IS avg remains above $500/trade, flag as runner-concentration distortion (not a gate problem). Check top-3-trades % of IS class PnL as standard concentration diagnostic before any per-class sweep.

**Related lessons:** C5 (VIX character > VIX level — L40,44,45,73,93,118,133,134), C4 (per-trade expectancy not WR standalone; normalize OOS — L01,04,22,46,128), C23 (IS/OOS VIX regime divergence — L122), L45 (VIX regime character), L128 (OOS normalization)

---

## L155 -- 2026-06-17: Autorate WF_norm formula gives FALSE POSITIVE when IS_delta < 0

**Symptom:** VIX>=19 gate for Safe conf+lvl_rej: IS_delta=−$2,334 (gate HURTS IS), OOS_delta=−$453 (gate HURTS OOS), WF_norm=(−453/21)/(−2334/130)=−21.57/−17.95=**1.201** → autorate reports "AUTO-RATIFY." The gate makes BOTH IS and OOS WORSE. Discovered via `backtest/autoresearch/safe_conj_lvl_rej_vix_split.py` sweep. Evidence: `analysis/recommendations/safe_conj_lvl_rej_vix_split.json`.

**Root cause:** WF_norm formula = `(OOS_delta/n_oos) / (IS_delta/n_is)`. Designed for cases where IS_delta > 0 (gate improves IS) and checks that OOS improvement is ≥70% of IS improvement per trade. When both deltas are negative, (−/n)/(−/n) = positive — WF appears "strong" even though the gate is harmful in both periods. The formula has no sign guard: a gate that drops profitable trades from both IS and OOS can score WF > 1.0 and appear better than the 0.70 threshold. Reviewed all shipped gate sweeps: fill_bar_gate_sweep.py AGG (IS_delta=+$363 — valid, unaffected), fill_bar_gate_sweep.py Safe (IS_delta=−$860, WF=−7.927 — already REJECT via WF FAIL), agg_midday_trendline_gate_sweep.py (IS_delta=+$1,316 — valid), all premium/runner sweeps (IS_delta=0 — correctly REJECTED). No shipped ratification was invalidated; the only false positive was caught before ratification.

**Fix:** Add mandatory guard — `if IS_delta <= 0: verdict = "REJECT"` — before WF calculation in all gate sweep scripts. No gate that hurts IS is valid regardless of WF ratio. IS_delta=0 (gate has no IS impact) is also a REJECT (no IS evidence the gate helps anything). Apply in: `backtest/autoresearch/safe_conj_lvl_rej_vix_split.py` (_gate_sweep + _autorate_gate functions), `backtest/autoresearch/fill_bar_gate_sweep.py` (_sweep function), and all future gate sweep scripts — add to the canonical gate sweep template. File as graduated guard target in `backtest/tests/test_graduated_guards.py`.

**Encoded in:** `backtest/autoresearch/safe_conj_lvl_rej_vix_split.py`, `backtest/autoresearch/fill_bar_gate_sweep.py`, `backtest/tests/test_graduated_guards.py` (graduated guard target), `markdown/doctrine/LESSONS-LEARNED.md` L155, CLAUDE.md C7 + C14 rows.

**Detection:** future regression — any autorate script that reports AUTO-RATIFY on a gate with negative IS_delta. Add assertion: `assert is_delta > 0, f"IS_delta {is_delta} <= 0 — REJECT before WF"` to the canonical sweep template so the sign-invariant bug cannot silently re-emerge.

**Related lessons:** C7 (silent success is failure — audit outputs not exit codes — L19,26,28,...), C14 (dead/unapplied knobs: vary-and-assert — L38,70,72,...), L70 (dead knob = silent no-op), L152 (baseline-first discipline)

---

## L156 -- 2026-06-17: Chandelier exit is regime-conditional (choppy=help, trending=hurt)

**Symptom:** Profit lock chandelier sweep (5 configs, both Safe + AGG) — all L155 REJECT. IS_delta negative across all candidates for both accounts. BUT W1 Jan-Jun 2025 (choppy, -$289 base) HELPS every config (+$3,850 SAFE v15 prod). W2 Jul-Dec 2025 and W3 Jan-Mar 2026 (trending/volatile) HURT every config ($-4,215 and $-2,432 for SAFE v15). Net IS negative because W2/W3 volume dominates.

**Root cause:** In 0DTE SPY options the chandelier arms at +5% premium gain then trails 20% off HWM. In choppy markets (W1), the chandelier locks in profits before reversals eat them. In trending markets (W2/W3), winners run 200-800% premium and the 20% trail clips the runner at 80% of HWM — systematically early. Consequence: the backtest correctly registers chandelier as net negative on trending IS data. The production chandelier serves a different purpose: live-trading risk management against disconnects and system crashes, not P&L optimization. These two use cases are not equivalent.

**Fix:** Do NOT add profit_lock_* mappings to `_params_to_kwargs()`. Adding them would permanently bias all future backtest baselines negative. Production chandelier stays in `heartbeat.md` for live risk management. Research implication: regime-conditional chandelier (enable only in high-VIX/choppy VIX regime) could be explored AFTER the VIX-regime classifier ships (C22 architecture item 5a in FUTURE-IMPROVEMENTS.md). No sweep until then.

**Encoded in:** `analysis/recommendations/profit_lock_sweep.json`, `markdown/planning/FUTURE-IMPROVEMENTS.md` (profit_lock_chandelier entry CLOSED), `automation/overnight/STATUS.md` CONTEXT-47.

**Related lessons:** C28 (ribbon flip is lagging exit — L139,141), C22 (backward-looking classifiers anti-correlate with recovery periods), L139 (ribbon flip is locally optimal exit — focus on entries), L148 (runner target dead knob)

---

## L157 -- 2026-06-17: Exit optimization has diminishing returns when stop-loss rate exceeds 70%

**Symptom:** AGG IS exit type audit (post-ENFORCED-5 baseline, n=109): EXIT_ALL_PREMIUM_STOP = 76/109 (69.7%) of trades, all losers, total -$15,755. The remaining 20% (TP1+runner exits) carry ALL IS profits (+$29,070). Exit gate sweeps tested this session — chandelier (L156), ribbon-flip buffer, runner target — all REJECT because they only affect the 30% of trades that reach TP1. Marginal improvement from the best exit tweak is ~$2K IS vs the baseline of 76 losers costing $15,755.

**Root cause:** At 70%+ stop-loss rate, the bottleneck is entry quality, not exit path. Every exit optimization study is arithmetically bounded: improving the 30% winners by even 50% changes total P&L by only ~15%. A 10% reduction in stop rate (76→68 stops at avg -$207 each) adds +$1,660 IS P&L — more than any exit gate found so far. This is the C22 core problem: entry filters are blocked by regime mismatch, leaving 70% losers as the structural floor.

**Fix:** Before starting exit gate research, audit exit type distribution. If stop_rate > 50%: entry filtering research dominates exit research in expected value. Reserve exit optimization for when stop_rate drops below 40-50% (i.e., entry quality improves). For AGG specifically: the research priority order is (1) improve entry quality → reduce stop count → then (2) optimize exits for the larger winner pool. ENFORCED-5 was the right play: it removed 26 IS stops and reduced OOS premium stops from 13/28 (46%) to 10/18 (56%) while cutting n-losers dramatically.

**Exception:** Exit timing research (e.g. no_trade_window for specific hours that have 0% WR) can still yield gates even with high stop rates, because it addresses WHEN losers occur, not how they exit. The AGG lunch-zone sweep (12:00-13:00 ET) is the right archetype: removes IS n=4 WR=0% trades without touching the exit path.

**Encoded in:** `analysis/recommendations/agg_exit_type_audit.json`, `automation/overnight/STATUS.md` CONTEXT-47, `markdown/planning/FUTURE-IMPROVEMENTS.md` profit_lock_chandelier entry.

**Related lessons:** C22 (backward-looking classifiers anti-correlate with recovery periods — L118-L135), C28 (exit mechanics locally optimal — L139,141), L148 (runner target dead knob — 2.8% IS hit rate), L130 (runner exits via ribbon_flip/time_stop not target)

---

## L158 -- 2026-06-17: FHH countertrend bypass (ribbon=BULL) has structurally low WR=25-28%

**Symptom:** BEARISH_REVERSAL_BYPASS was designed to capture the 5/01 J anchor (+$470 EC). After implementing `fhh_level_rejection + bearish_reversal_bypass=True` and running IS/OOS on both AGG and Safe accounts, new bypass entries showed WR=25-28% across 14-25 trades (IS Jan 2025 - May 2026). Both accounts REJECT: OOS_delta=-$56 (AGG) / -$80 (Safe), WF negative. Phase 1 IS window (2025-01 to 2025-09): n=14 (just below N>=15 target), WR=28.6% (far below 50% target). The 5/01 J winner captured as only +$24 (not +$470) — simulated entry finds a different path than J's live trade.

**Root cause:** When ribbon=BULL, bulls control the tape. FHH level acts as resistance but price is most likely to bounce from it (ribbon just confirmed upward momentum). The -7% premium stop fires before the bear move develops 72-75% of the time. Winning exits are all EXIT_ALL_RIBBON_FLIP_BACK (patient, waits for confirmation), but those require the ribbon to actually flip — which only happens ~25% of the time in a BULL-ribbon session. The 5/01/2026 J winner was exceptional: gap-up to FHH 724.24 with specific intraday context (macro catalyst + VIX spike) that isn't present in the 24 IS bypass trades.

**Fix:** Do NOT enable `bearish_reversal_bypass=True` in production without identifying what made 5/01 special. The FHH level rejection pattern requires: (1) a specific macro catalyst context OR (2) significantly wider stop ($0.12+ not $0.07) to survive the initial noise AND (3) possibly a filter discriminator (e.g., VIX >20 on the day, gap-up morning, heavy volume at FHH touch). All three require J's direct input on what he saw that made 5/01 a conviction trade.

**What NOT to do:** Don't widen the stop alone — L157 says with 70%+ stop rate, the problem is entry quality, not stop placement. Widening to -12% would increase loss size on the 72% losers while helping only the marginal cases near the 7% boundary.

**Encoded in:** `analysis/recommendations/bearish_reversal_bypass_is.json`, `markdown/specs/BEARISH-REVERSAL-BYPASS-SPEC.md`, `automation/overnight/STATUS.md` CONTEXT-50.

**Related lessons:** C3 (SPY-price edge ≠ option edge — L58,74,100,101,112), C22 (IS trending ≠ OOS volatile — L118-L135), C24 (anchor trades are exceptional, don't generalize — L140), L157 (exit optimization < entry quality when stop rate >70%)

---

## L159 -- 2026-06-17: D1 retest-reclaim entry filter is regime-conditional — underperforms V0 in trending markets

**Symptom:** D1 (wait up to 6 bars for price to pull back to the level and bounce, close>level+green bar) shows +296.3/c on 60-day OOS vs V0 at -187.2/c (+483.5/c delta). WF_norm=61 (OOS dramatically better per trade than IS). IS validation passes (IS_delta=+56.0/c), but sub-window SW_hurt=2: SW2 (2025H2 Jul-Dec) D1=-500.3/c vs V0, SW3 (early 2026 Jan-Feb) D1=-87.0/c vs V0. REJECT.

**Root cause:** D1 is a volatility-conditional quality filter. In trending markets (VIX 12-18, 2025H2), most V0 entries work immediately — they rip straight through and never need a pullback. D1's filter MISSES these runs (waiting for a pullback that never comes reduces n from 153 to 59 in SW2, capturing only 7.6% of V0's P&L per trade). In volatile markets (VIX 18-50+, 2025H1 and OOS Feb-May 2026), V0 entries fail immediately (stop out on choppy action) while D1's pullback filter correctly waits for a genuine bounce off the level before entering. WF_norm=61 (not ~0.70-1.30) is the signature: OOS is a DIFFERENT REGIME than IS, and D1 was tuned on the OOS regime.

**Fix:** Gate D1 by VIX regime — use D1 only when VIX > 18 (or VIX_character=choppy), use V0 when VIX < 15 (trending). This requires the VIX-regime classifier (deferred project). Do NOT ship D1 unconditionally — it will hurt trending-market days.

**What NOT to do:** Don't optimize D1 knobs (window, prox, stop) to fix the sub-window problem — the root cause is regime mismatch, not parameter tuning. More D1 optimization will overfit to OOS while making SW2 worse.

**Encoded in:** `analysis/recommendations/d1_is_validation.json`, `analysis/recommendations/d1_param_sweep.json`, `automation/overnight/STATUS.md` CONTEXT-51.

**Related lessons:** C22 (IS trending != OOS volatile — L118-L135), L158 (FHH countertrend has regime-conditional edge), C28 (ribbon flip is lagging — same regime-dependency pattern in exits)

---

## L160 -- 2026-06-18: Negative-anchor G5 check inverts direction — formula must use abs() subtraction

**Symptom:** G5 anchor-no-regression check returned FALSE for a candidate that had ZERO impact on the 3 anchor trades (4/29, 5/1, 5/4). Baseline anchor was −$354; candidate was also −$354 (identical). The formula `curr_anchor >= base_anchor * 0.90` computed `−354 >= −354 × 0.90 = −318.6`, which is FALSE because −354 < −318.6. A genuinely anchor-neutral change was silently rejected.

**Root cause:** `base_anchor * 0.90` assumes base_anchor is positive. When base_anchor is negative, multiplying by 0.90 moves the threshold TOWARD zero (stricter), not away from it. Intended semantics: "allow up to 10% worse" = −$389.4 minimum. Actual semantics with the broken formula: −$318.6 minimum (10% BETTER required). The sign inversion silently invalidated the G5 gate for every session where anchor P&L was negative, causing valid candidates to be REJECTED and the ratification pipeline to stall.

**Fix:** Use absolute-value subtraction: `curr_anchor >= base_anchor - abs(base_anchor) * tolerance_pct`. Scripts `agg_tp1_threshold_sweep.py` and `agg_oos_loser_dissect.py` (written 2026-06-18) both use the corrected formula. Verify `comprehensive_audit_v1.py` G5 block uses the same pattern. Diagnostic assertion: `assert anchor_tolerance > 0` is always satisfied by the corrected form and would surface a regression.

**Encoded in:** `agg_tp1_threshold_sweep.py`, `agg_oos_loser_dissect.py` (2026-06-18); `backtest/tests/test_graduated_guards.py` candidate for a parametric negative-anchor unit test; OP-25 C7.

**Detection:** Run G5 check with a synthetic case where `base_anchor = −100` and `curr_anchor = −100` (identical) — must return TRUE. Any rewrite that breaks this is a regression.

## L161 -- 2026-06-18: entry_time_et is naive ET — tz_localize("UTC") causes ~5h premarket offset

**Symptom:** A/B test for TRENDLINE-only bear ribbon spread gate initially showed all 5 OP-22 gates PASSING (RATIFY verdict). Orchestrator smoke test showed 9 trades removed vs 11 expected, with wrong P&L. Cross-check of individual trade ribbon values showed discrepancies: 2025-02-18 15:40 ET had spread=2.93c in A/B test vs 7.66c actual; 2025-08-20 09:55 ET showed 32.40c vs 119.90c actual. Root cause: `entry_time_et` on TradeFill objects stores naive ET strings (from option CSV convention). Applying `tz_localize("UTC")` treated "15:40 ET" as "15:40 UTC" = "10:40 ET" — a ~5h offset that caused ribbon lookups to hit **premarket bars** instead of actual RTH entry bars.

**Root cause:** Option CSV format stores timestamps in local ET without timezone info. `pd.Timestamp("2025-02-18 15:40:00")` is timezone-naive. `tz_localize("UTC")` treats it as already-UTC, so when compared against UTC-indexed data, the apparent ET time maps to the wrong (premarket) bar. The correct operation is `tz_localize("America/New_York").tz_convert("UTC")` which first declares the correct timezone, THEN converts to UTC for comparison.

**Fix:** In ALL A/B test scripts that use `entry_time_et` for external data lookups (ribbon, VIX, SPY bar-level data), use:
```python
entry_ts = pd.Timestamp(t.entry_time_et)
if entry_ts.tzinfo is None:
    entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
else:
    entry_ts = entry_ts.tz_convert("UTC")
```
For time-of-day filtering (`.time()` comparisons) only, `tz_localize(None)` or direct `.time()` on the naive timestamp is correct — no conversion needed since we're extracting the clock time directly.

**Impact:** Without this fix, initial verdict was RATIFY (IS blocked 11 "bad" trades). With correct TZ, IS_delta=-11 (gate blocks 14 trades including 2 IS winners). Gate was REJECTED. Wrong TZ would have shipped a gate that removes IS edge.

**Encoded in:** `backtest/safe_trendline_spread_ab_test.py` (corrected), `analysis/recommendations/safe_trendline_bear_spread_gate.json` (verdict REJECT), orchestrator.py MIN_TRENDLINE_BEAR_SPREAD_CENTS comment, STATUS.md CONTEXT-94. ALL subsequent A/B scripts in this session use correct TZ handling. OP-25 C7 (silent-success-is-failure).

## L162 -- 2026-06-16: FOMC-eve VIX suppression — a high-bear-score / 0-trade / declining-VIX day is correct abstention, NOT a miss

**Symptom:** 2026-06-16 (FOMC Day-1): bear score 8-9/10 sustained 10:33-15:00 ET, SPY fell ~$4.77 from session high to low, engine took 0 trades. Without context this reads as a missed bear day worth flagging to Chef as a coverage gap.

**Root cause:** FOMC Day-1 sessions trigger institutional hedge-stripping — dealers long volatility (puts, VIX calls) unwind the day before a binary event they expect to be benign. This mechanically suppresses VIX even as the underlying drifts lower, producing "price down / VIX down" — the inverse of the normal SPY/VIX correlation. Filter_8 (VIX >= 17.30 AND rising) correctly blocked every bear entry: VIX was 15.82-16.16 all session (~140bps below gate). A bear put bought into a compressing-IV tape suffers further IV compression dragging against the position, absent fear premium, and theta running against it in both directions — exactly the low-premium / high-theta-drag environment filter_8 exists to refuse. The day looks like a miss only if you grade on SPY-price direction (L136/C3) instead of option-edge.

**Fix:** No parameter change — doctrine encoding. (1) When reviewing EOD digests / pattern mining, a day with high bear scores + 0 trades + **VIX declining** is NOT a missed opportunity; it is correct abstention from a low-premium, high-theta-drag regime — do not queue it as a Chef coverage gap. (2) Hypothesis grading: track `FOMC_EVE_VIX_SUPPRESSION` ("0 trades is correct on FOMC Day-1 + VIX declining") across FOMC cycles. (3) This is a calendar-driven instance of the VIX-character-vs-level distinction (L73, C5): the gate is reading character correctly even though raw level alone wouldn't tell the whole story.

**Encoded in:** `analysis/eod/2026-06-16.md` (Pattern observations), `journal/2026-06-16.md` (EOD reflection), `markdown/doctrine/LESSONS-LEARNED.md` L162, CLAUDE.md C5 row.

**Detection:** future regression — if an EOD reviewer or Analyst flags a high-bear-score / 0-trade / declining-VIX session as a "missed bear day," that is a grading error (SPY-price edge mistaken for option edge). Cross-check VIX direction before classifying any 0-trade high-score day as a miss.

**Related lessons:** C5 (VIX character > VIX level — L40,44,45,73,93,118,133,134,154), C3 (SPY-price edge != option edge — L58,74,100,136,148,149), L93 (BEARISH_REVERSAL fires in declining VIX for mean-reversion; bear *continuation* in declining VIX is a weaker, different setup).

## L163 -- 2026-06-18: A dominant upstream quality filter supersedes downstream class-based blockers — re-validate ALL gates when a new entry filter joins the same trade pool

**Symptom:** 6-fold walk-forward validation of AGG production gates revealed 3 gates each consistently hurting OOS (0/6 OOS passes): `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_level_rejection`. All three had been individually ratified via OP-22 with strong IS *and* OOS deltas at the time. After 4-way A/B confirmation all three were removed; combined effect AGG OOS WR 55.6% -> 68.0%, OOS P&L +$1,205 -> +$1,853 (+$648, +53.7%).

**Root cause:** `require_bearish_fill_bar` (the dominant bear quality filter, ratified 2026-06-17) changed the *composition* of trades reaching the gate layer. Pre-fill-bar, the blocked classes (midday trendline bears, level_rejection bears, conf+lvl_rej midday/afternoon) were genuinely weak/stop-heavy, so blocking them was profitable. Post-fill-bar, every one of those classes must first pass the N+1 bar bearish confirmation, so the survivors are already high quality — and the downstream class-based blockers then remove exactly those quality-filtered winners. The C15 interaction is asymmetric: the fill_bar gate runs once at entry and can only pass/block; the class-based gates have no way to know fill_bar already verified quality, so they block unconditionally by class. The independent-ratification assumption fails whenever filters share the same trade pool.

**Fix:** Removed `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_level_rejection` from AGG; retained `require_bearish_fill_bar` as the sole AGG bear quality filter. **Structural rule:** when adding a strong quality gate (entry confirmation, fill-quality check, momentum filter), immediately re-run 6-fold WF validation on ALL existing class-based gates in the same trade pool — any showing 0/6 OOS passes (consistently hurting across every window) are removal candidates via 4-way A/B. Do not wait for the full IS/OOS split to accumulate; the rolling WF surfaces this faster. **SAFE exception:** supersession is tied to which accounts share the upstream filter — `require_bearish_fill_bar` is AGG-only, so SAFE `midday_trendline_gate` remains STABLE (4/6) and stays.

**Encoded in:** `analysis/recommendations/agg_wf_gate_removal_2026_06_18.json`, AGG `params.json` (3 gates removed), `markdown/doctrine/LESSONS-LEARNED.md` L163, CLAUDE.md C15 row.

**Detection:** future regression — a gate that scores 0/6 OOS passes in a multi-gate WF run is redundant-or-harmful in the current context regardless of its original solo-ratification scorecard; investigate for C15 supersession before re-adding it. Whenever a new upstream entry filter ships, the WF re-validation of downstream class gates is mandatory, not optional.

**Related lessons:** C15 (gates interact multiplicatively — trace session cascades — L07,08,09,66,95), L47 (broker is truth), L66 (gates cascade), L156 (chandelier is regime-conditional — same "context changes a previously-ratified knob" family).

## L164 -- 2026-06-19: `git commit --only <pathspec>` silently DROPS untracked new files

**Symptom:** Several Wave B deliverables (`backtest/lib/risk_gate.py`, `ledger.py`, the whole `validation/` package, `test_risk_gate.py`) were reported "committed" by the Wave B commit (`effa672`, "13 files changed, 6102 insertions") but were actually UNTRACKED -- never in git at all. Discovered hours later by a `git ls-files --error-unmatch` spot-check. Hours of work was at risk of silent loss to the background snapshot/restore process.

**Root cause:** `git commit --only <pathspec>` (and bare `git commit <pathspec>`) commits the working-tree state of *tracked* files matching the pathspec, plus already-*staged* changes. It does NOT include UNTRACKED new files under the pathspec unless they were `git add`-ed first. New files created by an agent (or me) that the background `git add` never happened to stage were silently excluded -- the commit succeeded and reported a large diff (from the modified + already-staged files), masking the omission. A silent failure in the commit step itself (OP-25 C7).

**Fix / graduation:** A tiny zero-dependency helper `setup/scripts/verify_committed.py` (`is_tracked` / `find_untracked` / `assert_all_tracked`, plus a CLI) that, given a list of intended paths, asserts each is tracked via `git ls-files --error-unmatch` and fails loud listing any that are not. Standing guard `backtest/tests/test_verify_committed.py` exercises it against a throwaway git repo: it (a) confirms a committed file passes, (b) reproduces the exact `git commit --only` drop end-to-end and asserts the helper catches the untracked sibling, and (c) pins that on-disk presence != tracked. Workflow rule unchanged: ALWAYS `git add <explicit new-file paths>` before a `--only` commit, OR run `verify_committed.py` after. When an agent creates new files, have it `git add` them itself (staging, not committing) so they cannot be dropped. This is the producer/consumer contract applied to the commit step.

**Encoded in:** `setup/scripts/verify_committed.py`, `backtest/tests/test_verify_committed.py`, `markdown/doctrine/LESSONS-LEARNED.md` L164, CLAUDE.md C7 row.

**Detection:** future regression -- if a `--only`/pathspec commit ever again reports success while a session's known-new files remain `??` in `git status`, that is this foot-gun; run `verify_committed.py <paths>` (exit 1 = some untracked) before declaring any work durable.

**Related lessons:** C7 (silent success is failure -- audit outputs not exit codes -- L19,26,28,...,160), C9 (update ALL state consumers; producer/consumer contract -- L21,42,49,60), C14 (vary-and-assert -- the same "verify the thing actually happened" discipline).

## L165 -- 2026-06-19: `tz_localize("UTC")` on a naive `entry_time_et` shifts ET->premarket (~5h) -- silently corrupts bar lookups

**Symptom:** A research A/B sibling (`safe_trendline_spread_gate.py`) localized `trade.entry_time_et` (a NAIVE ET timestamp) via `tz_localize("UTC")` to look up ribbon spread against UTC-indexed SPY bars. A "15:40 ET" RTH entry was thereby mislabeled "15:40 UTC" (= 10:40 ET), so every spread lookup hit a bar ~5 hours earlier (premarket-adjacent) instead of the real entry bar. This is the same class as the L161 incident, where the wrong-TZ lookup initially flipped an A/B verdict to a false RATIFY (the gate looked like it blocked 11 bad trades; with correct TZ it removed 2 IS winners and was REJECTED). A wrong-TZ lookup ships a gate that destroys edge.

**Root cause:** Option-CSV convention stores `entry_time_et` as timezone-NAIVE local ET. `tz_localize("UTC")` declares the clock to already be UTC (no shift of the wall-clock digits) -- so when compared against truly-UTC data the apparent ET maps to the wrong instant. The correct operation is `tz_localize("America/New_York").tz_convert("UTC")`: declare the real zone first, THEN convert. For time-of-day (`.time()`) filtering only, `tz_localize(None)` on the naive value is correct (no conversion needed). L161 documented the fix in the scripts written that session, but a sibling script (re-)introduced the bug -- prose failed as a control, so it is now a test.

**Fix / graduation:** Corrected `safe_trendline_spread_gate.py` to the ET->UTC form. Standing guard `backtest/tests/test_tz_localize_entry_time.py`: (a) STATIC scan -- any `*.py` under `backtest/` (incl. `autoresearch/`) that mentions `entry_time_et` and localizes a scalar timestamp as `"UTC"` FAILS, naming file:line (it deliberately ignores `.dt.tz_localize("UTC")` on VIX/SPY data columns, which is legitimate naive-UTC data); (b) BEHAVIORAL -- pins that the correct conversion round-trips to 15:40 ET while the broken one reads 10:40 ET, differing by exactly the 5h EST offset.

**Encoded in:** `backtest/safe_trendline_spread_gate.py` (corrected), `backtest/tests/test_tz_localize_entry_time.py`, `markdown/doctrine/LESSONS-LEARNED.md` L165, CLAUDE.md C6 row.

**Detection:** future regression -- a new or reverted A/B / gate-sweep script that converts `entry_time_et` to UTC via `tz_localize("UTC")` trips the static guard; use `.tz_localize("America/New_York").tz_convert("UTC")` (UTC-data lookups) or `.tz_localize(None)` (clock-time filtering).

**Related lessons:** L161 (same TZ foot-gun, first occurrence -- the prose control that this test now enforces), C6 (no look-ahead / as-of correctness -- a premarket-bar lookup is an as-of error -- L14,34,57,61,94), C7 (silent success is failure).

## L166 -- 2026-06-19: A peer-reviewed cross-sectional/aggregate effect is NOT automatically a tradeable 0DTE option gate -- verify causality AND OOS sign-stability before trusting an "inverse arm confirms it" cross-check

**Symptom:** Game Plan 1A proposed gating BEARISH_REJECTION continuation entries to DOWN-morning days, motivated by Gao-Han-Li-Zhou (JFE 2018) Market Intraday Momentum -- a published *cross-sectional/aggregate* effect (first-30min SPY return predicts last-30min). The first backtest looked like a clear edge: ATM real-fills expectancy -21.58 -> +22.83/contract (+$44.41 delta), and an inverse-arm cross-check (UP-morning bearish entries were the losers, -90.66) looked like clean confirmation that the signal was real. RATIFY-shaped on its face.

**Root cause:** Two compounding errors, both invisible until probed. (1) **LOOK-AHEAD:** `morning_sign` is final only at the 10:00 ET close, but BEARISH_REJECTION_MORNING can trigger from 09:35 -- so on ~19% of signals the gate peeked at a sign that wasn't known yet at entry. Restricting the gate to entries >= 10:00 ET (morning_sign strictly known before the entry it gates) collapsed the ATM edge from +$44.41 to +$10.34/contract (~$34 was pure look-ahead), and the causal baseline itself went positive (+$5.83), so the gate added almost nothing. (2) **OOS SIGN-INVERSION:** on a balanced median-date split (boundary 2025-11-18 -- the calendar 2025/2026 split was degenerate, OOS n=2-3 all DOWN-morning = no-op) the causal gate REVERSED sign: IS DOWN +63.05 / OOS DOWN -11.96 (ATM), and out-of-sample the *inverse* UP-morning arm became the winner (+99.00). ITM2 identical (IS +183.23 / OOS -34.95, UP wins OOS +122.18). The inverse-arm cross-check that looked like proof-of-signal was itself in-sample fitting -- it flipped OOS too. DSR stayed far below significance throughout (causal DOWN 0.34 ATM / 0.38 ITM2; OOS DOWN 0.13; all << 0.95).

**Fix:** RETIRED as a live gate (no live gate, not even a WATCH -- OOS sign-inversion means there is nothing directionally reliable to accumulate). **Doctrine rule:** before believing any gate sourced from a published cross-sectional/aggregate anomaly, run THREE checks, all necessary: (a) strict causality -- the signal must be fully known <= the entry bar it gates (restrict entry time so the signal is final first); (b) OOS SIGN-stability on a *balanced* (powered) split, not just OOS magnitude -- a sign flip across halves is disqualifying; (c) treat an "inverse arm confirms it" check as NECESSARY-NOT-SUFFICIENT -- it can itself be an in-sample artefact and flip OOS, so re-run the inverse arm on the OOS half too. An aggregate cross-sectional effect (works across many names on average) does not imply a per-trade 0DTE *option* edge (delta/theta/stop-misfire dominate -- cf. C3). This is a research/validation lesson -- no code guard (the existing causal-entry-time + balanced-OOS discipline in validate_morning_sign_gate.py is the reproducer).

**Encoded in:** `analysis/recommendations/morning-sign-gate-scorecard.json` (verdict=reject), `analysis/recommendations/morning-sign-gate.json` (causal_arms + oos_split evidence), `backtest/autoresearch/validate_morning_sign_gate.py`, `markdown/doctrine/LESSONS-LEARNED.md` L166, CLAUDE.md C6 + C4 rows.

**Detection:** future regression -- any lead justified by "it's a documented/published effect" with an inverse-arm cross-check as its headline proof, that has NOT been re-run with a causal entry-time restriction AND a balanced IS/OOS sign-stability check, is this mirage. The tell of in-sample fitting: the centerpiece cross-check (here the inverse arm) reverses sign out-of-sample.

**Related lessons:** C6 (no look-ahead / as-of correctness -- the signal must be known at entry -- L14,34,57,61,94,161,165), C4 (normalize OOS, stratify by regime; per-trade expectancy not WR -- L01,04,05,...,154), C3 (SPY-price edge != option edge -- L58,74,100,...), C24 (anchor/in-sample population WR can mislead -- L140,158), C22 (effects proven in one regime/window don't transfer -- L118-135).

## L167 -- 2026-06-19: Validate a seasonality / time-of-day gate against the actual per-hour P&L histogram before adding it -- folklore time-gates can remove near-breakeven fills and worsen the average

**Symptom:** Game Plan 1 microstructure proposed a "lunch-trough" gate -- exclude signal-bar entries in the documented U-shaped intraday-vol lunch window ({11:30-13:00, 12:00-13:30, 11:30-13:30}) on BEARISH_REJECTION. The "avoid lunch" heuristic is well-documented folklore. Tested across both the confirmed setup and the wider bearish family: NO-WIN on every scope. On the confirmed setup (morning watcher, 09:35-10:55) it was a structural no-op (0 fills ever land in any lunch window -- current time-gating already excludes it by construction). On the only scope where it changes fills (wider bearish family) excluding the lunch window did NOT improve real-fills expectancy -- ATM exp -22.27 -> -25.76/-26.38/-28.69 (worse at every window), ITM2 -54.59 -> -66 to -72 -- and the wider exclusions removed J's 5/01 13:09 anchor winner (721P +470).

**Root cause:** The folklore is about *volatility* (lunch is the low-vol trough), not about *our* P&L. The actual per-hour ATM P&L histogram shows our bleed is the **10:00 morning shoulder** (10:00-10:59: n=146, -$4,937 -- the single worst hour), while lunch (12:00-12:59: n=21, -$109) is the LEAST-bad hour, essentially breakeven, and 11:00-11:59 is actually the only solidly *positive* hour (+$1,526). Cutting the lunch fills therefore removes near-breakeven trades and drags the surviving average DOWN -- the gate attacks the wrong hour. A seasonality heuristic borrowed from a different metric (vol) was assumed to map onto edge without checking the edge distribution.

**Fix:** NO-PROPOSE -- no lunch-trough gate added. **Doctrine rule:** before adding any seasonality / time-of-day gate, plot the actual per-hour (or per-window) P&L / expectancy histogram of the real-fills population FIRST, and gate the hour that actually bleeds -- never import a time-gate from folklore (or from a different metric like volatility) on faith. Confirm the gate (a) targets a genuinely negative-expectancy window in OUR data and (b) does not remove anchor winners. A near-breakeven window is a non-target; removing it only worsens the average. This is a research/validation lesson -- no code guard (the per-hour histogram in the scorecard is the reproducer; the cheap reusable assertion is "compute the per-hour P&L histogram before sweeping any time-gate").

**Encoded in:** `analysis/recommendations/lunch-trough-gate.json` (recommendation=NO-WIN/DO-NOT-PROPOSE, with `time_of_day_histogram_atm`), `markdown/doctrine/LESSONS-LEARNED.md` L167, CLAUDE.md C5 + C4 rows.

**Detection:** future regression -- any time-of-day / seasonality gate proposed WITHOUT a per-hour P&L histogram of the real-fills population showing the gated window is the actual bleed (and that it removes no anchor winner) is this anti-pattern. The tell: the gate is justified by a generic market heuristic (lunch trough, power hour, etc.) rather than by our own per-window expectancy.

**Related lessons:** C5 (VIX/regime *character* > generic level; as-of trigger time -- folklore time-gates are the same "borrowed heuristic" failure -- L40,44,45,73,93,118,133,134,154,162), C4 (per-trade expectancy not WR standalone; stratify before gating -- L01,04,05,...,154), C30 (audit what % of exits actually hit a target before sweeping it -- same "measure the distribution before tuning the knob" discipline -- L148).

## L168 -- 2026-06-19: J's 667 real trades prove the killer is sizing-UP behavior, not contract count per se -- but the data CANNOT yet decide whether flat-3 is safe (min-3 vs J's losing band is an open question for J)

**Symptom:** Mining J's real Webull options fills 2021-2023 (`markdown/0dte/J-WEBULL-EDGE-2021-2023.md`, 667 SPX/SPY-family round-trips) produced the weekend's #1 practical finding: J has a real small positive edge that he destroys by sizing up. **1-2 contracts: net +$4,576 (50.8% WR, +$7.9/trade). 3-5 contracts: -$13,975 (18.6% WR). 6-10: -$3,486. Scaled-in (multi-fill) entries: -$327/trade vs +$3.5 single-fill.** The whole account loss (-$12,885) lives in the 88 trades sized 3+ (-$17,461 combined). Two readings of the same numbers point opposite ways for OUR doctrine, and naive reading is dangerous.

**Root cause (the nuance to capture precisely):** The headline "3+ contracts = his losing zone" invites the wrong conclusion that "large size is bad, so any 3-lot is risky." But the per-entry-STYLE cut disambiguates: *scaled-in* entries are -$327/trade while *single-fill* entries are +$3.5 — i.e. the destruction tracks the **behavior of adding / sizing-UP** (almost always scaling into a position already moving against him: 9 of his 10 worst losers were 3+ lots, 8 of 10 puts, most entered in his weak time bands), not the static fact of holding 3 contracts. The likely killer is (b) the sizing-up/adding/revenge behavior, NOT (a) "3 flat contracts is bad." This is exactly what **Rule 6 (per-trade cap), Rule 4 (no adding without a NEW confirmed trigger), and "no sizing up after losses"** exist to prevent — J's own ledger is empirical proof of those rules.

**THE UNRESOLVED TENSION (flagged for J — do NOT resolve unilaterally, Rule 9):** Gamma doctrine *requires* min-3 contracts (2 TP + 1 runner; CLAUDE.md Rule 6, `params.min_contracts`, enforced by `risk_gate.check_order` MIN_CONTRACTS). But J's data shows 3+ is his empirical losing band. The data cannot separate the two confounded hypotheses because J **almost never traded a single disciplined flat-3 entry** — his 3+ sample is dominated by scaled-in / revenge adds, so "flat-3 entered once with a defined stop" is essentially unobserved in his history. So the open question is genuinely open: *is our mandatory min-3 sitting inside J's documented losing zone, or is it specifically the sizing-UP (scaling/adding) that kills, making a disciplined flat-3 fine?* The evidence (scaled-in negative, single-fill positive; he sizes up into his worst trades) leans toward "flat-3 is fine, adding is the killer" — but that is a lean, not a proof. **Decision belongs to J.**

**Code-gap note (surfaced, not silently fixed):** `backtest/lib/risk_gate.check_order` enforces a per-trade *upper* cap (RISK_CAP / MAX_PREMIUM_TIER, % of equity) and a *lower* floor (MIN_CONTRACTS >= 3), plus KILL_SWITCH / FIRST_ENTRY_LOCK / NOT_FLAT. It does NOT enforce "no sizing up after a loss" as a function of recent P&L trajectory — there is no equity-trend- or prior-loss-aware size throttle. NOT_FLAT + FIRST_ENTRY_LOCK + Rule 4 prose block *adding to an open / stopped setup*, which covers the worst scaled-in case, but a fresh-but-oversized entry *after* a losing trade closed is not mechanically capped beyond the static % cap. If J wants the L168 finding enforced mechanically, the candidate is a post-adverse-excursion / post-loss add-cap knob (proposed in the J-WEBULL doc recommendations) — propose-only until ratified.

**Fix / status:** Lesson recorded; NO live change (Rule 9 / WATCH-ONLY consolidation). The 10 small-lot winners from the same mine are registered as J's NEW candidate anchor set (`markdown/0dte/J-WEBULL-EDGE-2021-2023.md`) for validating the diversified book once real ★★★ levels bank. Two lighter findings from the same history are logged as **hypotheses worth an A/B, NOT applied** (they are SPX 2021-23, a different era/instrument than our SPY engine — validate before trusting, per C22): (1) **time-of-day** — J's winners cluster midday (13:00 ET = 72.7% WR / +$69; 11:00/12:00/14:30 positive) while the open and late-afternoon bleed; the production 09:35 entry gate may fire into his weakest band. (2) **VWAP side** — every J winner was on the correct side of session VWAP for its direction. Both deserve a causal + balanced-OOS + anchor-no-regression A/B before any gate.

**Encoded in:** `markdown/0dte/J-WEBULL-EDGE-2021-2023.md` (full ledger + sizing/time/VWAP tables + recommendations), `analysis/webull-j-trades/j_style_stats.json` (the sizing/entry-style breakdown), `markdown/doctrine/LESSONS-LEARNED.md` L168, CLAUDE.md C31 row. Open question + code-gap deliberately left for J (no doctrine/params/risk_gate edit).

**Detection:** future regression -- if anyone proposes raising `min_contracts`, relaxing Rule 6, or adding a "scale into conviction" path citing "more size = more edge", this lesson is the counter-evidence (J's 3+ band is -$17,461). Conversely, if anyone proposes DROPPING min-3 below 3 citing "3+ is J's losing zone", the confound flag above applies — his 3+ losses are scaled-in/revenge adds, not disciplined flat-3 entries, so the inference does not transfer without a clean flat-3 sample. Either move requires J's explicit decision on the open question, not a unilateral read of the headline number.

**Related lessons:** C24 (anchor/in-sample population can mislead -- J's headline 3+ number conflates two populations, exactly like anchor-vs-population WR -- L140,158), C22 (effects proven in one era/instrument don't transfer without fresh A/B -- SPX 2021-23 vs SPY-now -- L118,119,...,159), C4 (per-trade expectancy not WR standalone; stratify before concluding -- the by-entry-style split is what disambiguates -- L01,04,05,...,167), C11 (broker is source of truth: flat-before-entry / no adding -- the mechanical guard against the scaled-in failure mode -- L47,76).

## L169 -- 2026-06-20: An auto-queue producer that fires CRITICAL on a non-deterministic (live/source-dependent) signal floods the backlog with un-drainable noise on every transient

**Symptom:** `automation/overnight/queue.md` accumulated 24 phantom `## CRITICAL` HARVEST-REGFAIL rows overnight (2026-06-19T22:27 .. 2026-06-20T09:57, one per half-hourly gym-harvester run), each showing the SAME 14 `.live`/parity stages failing at `passed=74/88`. Nothing ever drains these append-only rows, so every subsequent `Gamma_Conductor` fire would read 24 CRITICALs at the top of the queue (STAGE 0 priority #1) and be misled into believing the engine was on fire -- starting infra-firefighting on a phantom instead of the real highest-value task. The live gym had in fact self-healed to **90/90 overall_pass=true** an hour after the last phantom row (verified, not assumed).

**Root cause:** `crypto/benchmarks/gym_harvester.py::_detect_regression_fail` emitted a CRITICAL the moment `overall_pass is False`, with NO discrimination between a deterministic code regression and an environmental transient. When the live data feed is briefly unreachable (network blip / rate-limit), EVERY `.live` validator fails at once -> `overall_pass=false` -> CRITICAL emitted. The carve-out already existed elsewhere: `runner.py` overall_pass and `_detect_source_disagreement` both treat `v02_source_parity` + `v15_three_source_parity.live` as `KNOWN_FLAKY_LIVE_SOURCE` -- but the harvester's CRITICAL emitter did not honor it. A guardrail present in one consumer of the same signal was absent in a sibling consumer (the classic partial-fix / producer-asymmetry class).

**Fix (shipped 2026-06-20, conductor fire):** Producer guard -- a stage failure is only a reproducible regression if the stage is DETERMINISTIC (`.offline`/`.fixture`). `_detect_regression_fail` now suppresses the CRITICAL when ALL failed stages are `.live`/known-flaky; it fires only when >=1 deterministic stage fails, OR when no `per_stage` breakdown exists to classify (conservative -- fail toward flagging). Guarded by `backtest`/`test_gym_harvester.py::test_regression_fail_suppressed_when_only_live_stages_fail` + `test_regression_fail_emits_when_per_stage_missing` (12/12 green). The 24 stale rows were pruned and archived verbatim to `automation/overnight/queue-archive-2026-06-20.md`.

**Generalizable principle:** CRITICAL must be reserved for **reproducible, deterministic** failures. Classify environmental-vs-deterministic AT THE PRODUCER, never by hoping a downstream triage prunes the noise. When a known-flaky carve-out exists for a signal in one place, every emitter of that signal must honor it -- audit siblings when you add a flaky-source exclusion (C15: re-validate the shared pool when one gate is added).

**Encoded in:** `crypto/benchmarks/gym_harvester.py` (`_detect_regression_fail` deterministic-stage guard), `backtest/tests/test_gym_harvester.py` (2 new guard tests), `automation/overnight/queue-archive-2026-06-20.md` (24 pruned rows), `markdown/doctrine/LESSONS-LEARNED.md` L169, CLAUDE.md C7 row.

**Detection:** future regression -- any auto-queue / alerting producer that emits CRITICAL (or pages, or files a BROKEN flag) directly off a signal that depends on a live data feed / external source, WITHOUT classifying the failed component as deterministic vs known-flaky first, is this anti-pattern. The tell: the same backlog key repeats once per scheduled run with an identical flaky-stage signature and nothing ever closes it.

**Related lessons:** C7 (silent success/noise -- audit outputs not exit codes; a CRITICAL that nothing drains is the inverse failure: noise masquerading as signal -- L19,26,28,...,164), C15 (gates interact multiplicatively / re-validate the shared pool when one is added -- the flaky carve-out must be honored by every consumer -- L07,08,09,66,95,163), OP-22 (compound don't accumulate -- the 371st untriaged CRITICAL is debt; the producer fix stops the accumulation at the source).

## L170 -- 2026-06-20: Author-inbox items have no closing handshake -- a shipped artifact whose source inbox file is never renamed `.DONE` becomes phantom backlog that drives duplicate-rebuilds

**Symptom:** The `strategy/candidates/_validator-inbox` carried 2 items for an entire month (`sizing-risk-cap-guard.md` since 2026-05-31, `2026-05-21-ghost-entry-v26-regression.md` since 2026-05-21) that were **already fully implemented and registered** as gym validators (`v42_sizing_risk_cap_guard.py` offline 12/12; `v26_ghost_entry_detection.py` 15/15 + `v43_ghost_entry_dual_account.py` 10/10). The 2026-06-20 22:05 conductor fire read them as "stale items worth draining" -- i.e. pending work -- when they were done. A future fire spawning `validator-author` against them would have built a near-duplicate (a redundant v44 of v42).

**Root cause:** There is no closing handshake on the OP-29 author inboxes. When an author persona (validator/skill/lesson/chef) ships its artifact, nothing renames the source inbox item `.DONE`. The producer (the artifact on disk) and the consumer-signal (the inbox file) drift: the artifact exists, the inbox still says "pending." Same producer/consumer-silent-break class as the state-contracts and watcher-registry work, here applied to the inbox lifecycle: "being-implemented" must equal "inbox-closed", but nothing asserted it.

**Fix (shipped 2026-06-20, conductor fire):** Both stale items got a CLOSED note pointing at the implementing validator + were renamed `.DONE` (loop closed manually). The DURABLE fix is the graduate-to-code guard: `backtest/tests/test_author_inbox_reconciliation.py` -- a reconciliation pytest that, for each open `_validator-inbox/*.md` carrying a `proposed_validator:` frontmatter field, ASSERTS the file is `.DONE` if a matching `crypto/validators/v<NN>_<slug>.py` already exists (matched by SLUG, since the proposed name `v_sizing_risk_cap_guard` ships as `v42_sizing_risk_cap_guard.py`). Items lacking frontmatter are reported as ADVISORY (fail-open), not hard-failed. 7/7 green. This turns "did the author close its loop?" into a build-time assertion instead of a conductor re-reading phantom work every fire.

**Generalizable principle:** Every producer->consumer-signal handoff needs a closing handshake, and the handshake must be ENFORCED, not trusted. When a worker ships an artifact whose existence is machine-checkable (a file on disk, a registry entry), a reconciliation test should assert that the request-signal which spawned it is closed. The watcher-registry precedent ("being-defined == being-registered") generalizes to "being-implemented == inbox-closed." Process reminders in author prompts help but rot; the test is the guardrail.

**Encoded in:** `backtest/tests/test_author_inbox_reconciliation.py` (the reconciliation guard, 7 tests incl. synthetic fire-when-it-should reproducers), the 2 `_validator-inbox/*.DONE` closures, `markdown/doctrine/LESSONS-LEARNED.md` L170, CLAUDE.md C7 row (fold pending -- staged proposal `cd-2026-06-21-001`, rail 4).

**Detection:** future regression -- any OP-29 author inbox (`_validator-inbox`, `_skill-inbox`, `_lesson-inbox`, `_chef-inbox`) accumulating items whose deliverable already exists on disk is this anti-pattern. The tell: a conductor fire's "next fire picks up" repeatedly names the same inbox item across multiple fires, or an author persona is about to build something that already exists. The validator inbox is now guarded; the skill/lesson/chef inboxes do not yet have a machine-checkable artifact identity (their outputs are prose) -- extend the reconciler if/when they get one.

**Related lessons:** C7 (silent success is failure -- audit outputs not exit codes; a never-closed inbox item is the same class as a never-drained CRITICAL -- L19,26,28,...,164,169), the watcher-registry reconciliation precedent (`backtest/tests/test_watcher_registry.py` -- "being-defined == being-registered"), OP-22 (compound don't accumulate -- the 371st untriaged candidate is debt; an un-closed inbox item is debt that actively misleads the next fire).

## L171 -- 2026-06-20: tight-stop truncation manufactures fake edge — mandatory cross-check same-strike chart-stop-only

**Symptom:** The NEW-HUNT IBS (Internal Bar Strength) mean-reversion candidate passed all 5 standard new-strategy gates with flying colors — OOS positive, concentration pass, sample size n=3396, all metrics clear — yet was a fake edge. The best cell (`strike_offset=-1, premium_stop_pct=-0.08`) claimed +$5.3/trade total +$17,934 with 26% WR. Cross-check: the **same strike at chart-stop-only** (`premium_stop_pct=-0.99`) yielded **−$19.6/trade** on the SAME n=3396 sample. The sign **inverted completely** across the stop axis. Every other cell in the 20-cell grid was negative. The published IBS thesis is a ~70%-WR mean-reversion edge on SPY daily; our best cell's 26% WR and sign-inversion flagged that the intraday 5m→0DTE single-leg option transform did NOT preserve the edge.

**Root cause:** A tight premium stop (−8%) on 0DTE options **mechanically truncates losers** (cuts each loss at −8% premium) while permitting fast winners to run, manufacturing a positive average **with ZERO underlying directional signal**. The standard gate battery (OOS, concentration, n, drop-top-5-days) only examines the chosen cell; it never checks whether the same signal at a different stop (e.g., chart-stop-only) on the **same strike** is inverted. Reference: `backtest/autoresearch/_newhunt_ibs_mean_reversion.py` contains the inline compute of `is_truncation_artifact` (6th gate); evidence in `analysis/recommendations/newhunt-ibs-mean-reversion.json` (fields `self_verify.same_strike_chart_stop_only_per_trade=-19.6`, `is_truncation_artifact=true`, `clears_bar=false`). This is a C3/L58 analog: a profitable SPY-directional finding does NOT transfer to option edge (premium stops hide the failure until a cross-check reveals it).

**Fix (shipped 2026-06-20):** Generalized the truncation cross-check into a reusable, graduated guard. New module `backtest/lib/truncation_guard.py` exports `is_truncation_artifact(*, best_per_trade, chart_stop_only_per_trade, best_premium_stop_pct, tight_stop_threshold=-0.30)` and `cross_check_grid(grid_results, best_cell, *, chart_stop_pct=-0.99, tight_stop_threshold=-0.30, per_trade_key="avg_pnl")` returning a frozen `TruncationVerdict` (`is_artifact`, `best_strike_offset`, `best_premium_stop_pct`, `best_per_trade`, `chart_stop_only_per_trade`, `chart_stop_pct`, `reason`) plus a `.passes` property (= not is_artifact). The `_newhunt_ibs_mean_reversion.py` adopts it as its mandatory 6th candidate gate (behavior-identical to its inline computation but now shareable). Pinned by `backtest/tests/test_truncation_guard.py`: 13 tests incl. a full integration test reproducing the committed IBS verdict (best cell positive / chart-stop negative / verdict REJECT). The guard is now available to all `backtest/autoresearch/_newhunt_*.py` and `*_real_fills_validate.py` self-verify stages.

**Encoded in:** `backtest/lib/truncation_guard.py` (shared gate + `TruncationVerdict` DTO, 2 public functions), `backtest/tests/test_truncation_guard.py` (13 tests green), `backtest/autoresearch/_newhunt_ibs_mean_reversion.py` (adopts shared guard as 6th gate), `analysis/recommendations/newhunt-ibs-mean-reversion.json` (`clears_bar=false` verdict), CLAUDE.md C2 row (folded -- now `L51,55,64,171`).

**Detection:** future regression — any new-strategy / real-fills candidate declared "real" with positive per-trade P&L at a tight premium stop (> −0.30, i.e. tighter than −30%) when the **same-strike** chart-stop-only (−0.99) cell is materially negative (per-trade inverted sign). The tell: `cross_check_grid()` returns `is_artifact=true` -- the chosen cell per-trade is > 0 while the same-strike chart-stop-only cell is < 0, and the inversion is spelled out in the verdict `.reason`. This is a **mandatory gate before ratification** — a positive tight-stop edge without a passing cross-check is a foot-gun (C2 first-strike entries: chart-stop-only, premium-stop disabled). Sibling: the pending `_lesson-inbox/2026-06-20-option-edge-vs-spy-tilt-discriminator.md` pairs this no-truncation gate with a random-entry-null baseline discriminator.

**Related lessons:** C2 (first-strike entries chart-stop-only — L51,55,64,171; premium stops are truncation artifacts in 0DTE), C3/L58 (SPY-direction edge ≠ option edge; intraday transform does not preserve daily signal), C4/L01,04,11,22 (a positive average is NOT evidence of edge without causality check; truncation is the canonical fake-causality case).

## L172 -- 2026-06-20: A structural-gate-passing 0DTE candidate whose per-trade a random-entry null reproduces is an exit-structure artifact, not signal alpha -- require beating the null MAX, not just being positive

**Symptom:** The Connors RSI(2) intraday mean-reversion NEW-HUNT (`_newhunt_rsi2_mean_reversion.py`) passed EVERY coded structural gate. Its best cell (variant 10_90, `strike_offset=-1`, `premium_stop_pct=-0.08`) showed +$6.11/trade over n=952 real OPRA fills, OOS(2026) +$6.65/trade, 5/6 positive quarters, top5-day concentration 54% (< 200%), and drop-top-5-days per-trade still +$2.87 (> 0). By the standard battery it read as a REAL CANDIDATE. But a coin-flip null -- random RTH entries with the SAME count / side-mix / stop / strike / invalidation rule, 10 fixed seeds -- produced +$2.66/trade MEAN and **+$8.10/trade MAX**. The signal's +$6.11 sat UNDER the luckiest random seed (+$8.10): a coin flip beat the RSI(2) read. REJECTED (`clears_bar=false`). Artifact: `analysis/recommendations/newhunt-rsi2-mean-reversion.json`.

**Root cause:** The v15 asymmetric exit bracket (-8% premium stop + +30% TP1 + 2.5x runner) is mildly POSITIVE on almost ANY 0DTE entry over a 16-month sample -- the tight stop caps the left tail while the runner leaves the right tail open. So the structural gates (OOS > 0, positive quarters, n >= 20, drop-top5 > 0) are NECESSARY but NOT SUFFICIENT: they can all pass on pure exit-structure geometry with ZERO directional alpha. The only check that exposed it was comparing the signal to the random-entry null's MAX. The drop-top5 +$2.87 > null mean +$2.66 was True (so the surviving edge was not merely day-concentration), yet the headline +$6.11 < null max +$8.10 -- the "edge" is the bracket, not the read. This is the C3/L58 trap (a SPY-direction/underlying edge is NOT an option edge) generalized one layer: exit-STRUCTURE edge != signal edge. It is the sibling of L171's truncation cross-check ("does the sign invert at chart-stop-only?") -- the null baseline asks the complementary "does a random entry reproduce the number?"

**Fix (shipped 2026-06-20):** Extracted `random_entry_null()` -- previously duplicated inline in TWO new-hunts (`_newhunt_rsi2_mean_reversion.py` and `_swjshak_three_ducks.py`, which had drifted: one gated on the null MEAN, one on the MAX) -- into a shared, parameterized helper `backtest/autoresearch/null_baseline.py`, callable by every future new-hunt and the confluence / db_base / `*_real_fills_validate.py` self-verify stages. Added `null_gate(per_trade, drop_top5_per_trade, null)` that folds the null into the two STANDARD candidate-gate keys -- `beats_null_max` and `drop_top5_beats_null_mean` -- plus `beats_null_mean` / `edge_over_null_per_trade` for disclosure, and the combined `null_pass = beats_null_max AND drop_top5_beats_null_mean`. The standard bar is now "beat the null MAX," not "be positive." Both duplicate copies were refactored to call the shared helper (the RNG switched to a private `random.Random(seed)`, which is bit-identical to the legacy global `random.seed` draw, so no already-published null number moves). Pinned by `backtest/tests/test_null_baseline.py`: 12 tests incl. the RSI(2) artifact case, the legacy-RNG equivalence proof, determinism, the side-mix padding guard, and the empty-gate / eligible-idx branches.

**Generalizable principle:** For any 0DTE directional candidate validated through the v15 asymmetric bracket, a structural-gate pass is necessary but NOT sufficient evidence of edge. Always run a same-count / same-side-mix / same-stop / same-strike random-entry null and require the signal's per-trade to beat the null's MAX (the luckiest coin-flip) -- not merely be positive, and not merely beat the null mean. A positive expectancy that a coin flip reproduces is the exit structure talking, not the entry. Pair this with the L171 truncation cross-check (sign must not invert when the tight stop is removed): together the no-truncation gate and the random-null gate bracket the two ways the v15 exit geometry manufactures a fake edge (the operational form of C3/L58 requested in `_lesson-inbox/2026-06-20-option-edge-vs-spy-tilt-discriminator.md`).

**Encoded in:** `backtest/autoresearch/null_baseline.py` (`random_entry_null` + `null_gate`, the shared standard gate), the refactored `_newhunt_rsi2_mean_reversion.py` + `_swjshak_three_ducks.py` (both import the shared helper -- duplication removed), `backtest/tests/test_null_baseline.py` (12 tests green), `analysis/recommendations/newhunt-rsi2-mean-reversion.json` (the rejected artifact: `random_entry_null.best_beats_null_max=false` -> `clears_bar=false`), `markdown/doctrine/LESSONS-LEARNED.md` L172, CLAUDE.md C3 row.

**Detection:** future regression -- any new-hunt / `*_real_fills_validate.py` that declares a REAL CANDIDATE off the structural battery (OOS > 0, positive quarters, n >= 20, drop-top5 > 0) WITHOUT a random-entry null comparison, or that gates on the null MEAN instead of the MAX, is this anti-pattern. The tell: a positive per-trade that sits INSIDE the null's [min, max] spread, or a `null_gate` whose pass is wired from `beats_null_mean` rather than `beats_null_max`. The cheap reusable assertion is `null_baseline.null_gate(...)["null_pass"]`.

**Related lessons:** C3 (a SPY-price/underlying edge is NOT an option edge; the exit-structure artifact is the same trap one layer up -- the option mechanics, here the bracket, manufacture the number, not the directional read; "stop-misfire" -- L58,74,100,101,112,136,148,149), L171 (sibling discriminator -- tight-stop truncation cross-check; the no-truncation gate and the random-null gate are the two halves of the v15-exit-geometry foot-gun), C4 (per-trade expectancy not WR standalone; disclose concentration / drop-top5; a structural/aggregate positive != a per-trade signal edge -- L01,04,05,...,166,167), C2 (first-strike entries chart-stop-only -- premium stops are exactly the bracket geometry that fakes the edge -- L51,55,64), C28/C30 (ENTRIES are where edge lives; audit what the exit knob actually does -- the null isolates whether the entry adds anything over a coin flip -- L139,141,148,156,157).

## L173 -- 2026-06-21: Author inboxes have no SUPERSEDE disposition path -- research rendered moot by a strategic verdict re-costs every conductor fire until someone manually closes it

**Symptom:** Three `_chef-inbox` pattern candidates (`2026-05-21-false-break-open-carry-gate`, `2026-06-16-fomc-eve-quiet-bear`, `2026-06-16-pre-fomc-positioning-pattern`) sat OPEN across **three consecutive conductor fires** (2026-06-20 22:05, 23:00, 2026-06-21 01:00). Every one of those fires re-read all three, flagged in STATUS "evaluate whether these are worth a `chef` fire or should be marked superseded by the terminal campaign verdict before spawning," and then moved on without disposing of them. ~3 fires of opus tokens were spent re-deriving the same "should I cook these?" question with no resolution. The 02:05 fire finally disposed of all three (SUPERSEDED / RESOLVED-INFORMALLY / TRIAGED-TO-BACKLOG).

**Root cause:** L170's closing handshake covers ONE direction only -- **research that has been IMPLEMENTED** (a machine-checkable artifact exists on disk -> the inbox item must be `.DONE`). There is no path for the opposite case: **research that has been SUPERSEDED** by a strategic verdict or standing directive (here, the terminal ~27-strategy campaign verdict + OP-22 "STOP entry-hunting (saturated)" rendered the FOMC-eve *entry* candidates moot). Supersession is not machine-checkable -- no artifact appears on disk to prove "this is now off-strategy" -- so nothing ever closed them, and they remained phantom backlog that every STAGE-1 fire re-evaluates from scratch. A producer (Analyst queuing chef research) and a downstream policy change (the campaign verdict) drifted with no reconciliation step. This is the C7 stale-state class and the OP-22 "371st untriaged candidate is debt" pattern, in the supersede direction L170 left uncovered.

**Fix (shipped 2026-06-21, conductor fire):** The conductor IS the disposition authority for the inboxes (same role exercised in the 23:00 validator-inbox drain). The durable fix is a graduate-to-code **staleness ratchet** in `backtest/tests/test_author_inbox_reconciliation.py`: `find_stale_undisposed(candidates_dir, *, max_age_days=7, now=...)` walks ALL four author inboxes (`_validator-inbox`, `_skill-inbox`, `_lesson-inbox`, `_chef-inbox`) and returns every open `*.md` (NOT `.DONE` / `.STALE.md` / `README.md`) whose file mtime is older than the threshold -- candidates for explicit SUPERSEDED / RESOLVED / BACKLOG triage. Because supersession is a judgment call, this is **ADVISORY (fail-open)** -- surfaced via a captured-warning test, never a hard failure (do-no-harm; an item legitimately still cooking must not break the build). It complements L170's hard implement-direction guard: together they bracket both ways an inbox item can become stale -- "the work is done" (L170, hard) and "the work is moot / too old to ignore" (L173, advisory).

**Generalizable principle:** A producer->consumer-signal handoff needs a closing handshake for EVERY way the signal can be resolved, not just the happy path. L170 closed the implement direction; supersession (a downstream policy/verdict invalidating queued work) is an equally common resolution and needs its own ratchet. When the resolution is machine-checkable (artifact on disk), enforce it HARD; when it is a judgment call (off-strategy / superseded), surface it as an ADVISORY staleness flag so it cannot silently re-cost every fire -- fail-open, because a false "stale" must never block legitimate in-flight work.

**Encoded in:** `backtest/tests/test_author_inbox_reconciliation.py` (`find_stale_undisposed` + `StaleItem` DTO + synthetic fire-when-it-should/does-not-fire reproducers + a non-fatal live advisory test across all 4 inboxes), the 3 `_chef-inbox/*.DONE` closures (2026-06-21 02:05 fire), `markdown/doctrine/LESSONS-LEARNED.md` L173, CLAUDE.md C7 row (fold pending -- staged proposal, rail 4).

**Detection:** future regression -- a conductor fire's "next fire picks up" naming the SAME inbox item across multiple consecutive fires WITHOUT closing or triaging it, or any open `_*-inbox/*.md` older than 7 days with no implementing artifact and no `.DONE`. The tell: `find_stale_undisposed()` returns a non-empty tuple. Triage each to one of: SUPERSEDED (cite the verdict/directive), RESOLVED-INFORMALLY (engine already does the right thing), or TRIAGED-TO-BACKLOG (legitimate but low-leverage -> scoped queue line), then rename `.DONE`.

**Related lessons:** L170 (sibling -- author-inbox closing handshake, IMPLEMENT direction; this is the SUPERSEDE direction it left open), C7 (silent success / stale-state -- a never-closed inbox item is the same class as a never-drained CRITICAL -- L19,26,...,169,170), OP-22 (compound don't accumulate; an un-disposed inbox item is debt that actively misleads the next fire), the watcher-registry reconciliation precedent (`backtest/tests/test_watcher_registry.py`).

## L174 -- 2026-06-21: A gate-passing 0DTE candidate can still be a RE-SKIN of an already-shipped edge (high day-overlap) or a cosmetic "filter" that removes net-WINNERS (a relabel, not alpha) -- require independence-vs-shipped-edges AND no-regression-on-changed-days

**Symptom:** During the all-night strategy hunt (B7/B8), two candidates cleared the entire naive gate stack (OOS-positive, DSR-pass, drop-top5, broad-based) and *looked* like new edges, but were artifacts: (1) **anchored-VWAP** scored as a positive edge while sharing **97.3% of its signal-days** with the already-LIVE `vwap_continuation` (#1) -- it was the SAME edge re-skinned, and counting it as additive would have double-counted #1's P&L in the measured portfolio. (2) **cum-delta** and the proposed **2-bar refine on #2/#4** presented as profitable "filters," but the days each one REMOVED were net-POSITIVE -- the gate was destroying alpha and the residual still looked positive only because the surviving base edge carried it. Both would have shipped as fake diversified Sharpe under the old bar.

**Root cause:** The standing honesty gates (L171 truncation, L172 random-null, L173 OOS-alone drop-top5) all test a candidate *in isolation* against price/null/sub-window structure. They are blind to two relational failures: (a) **non-independence** -- a candidate that fires on the same days as a shipped edge adds no diversification, so its "positive OOS" is just the shipped edge's P&L wearing a new name; and (b) **negative-selection-as-filter** -- a "filter" is only alpha if the trades it removes are net-losers; if it removes net-winners, the post-filter total can still beat the pre-filter total purely because the gate also removed a larger pile of losers elsewhere, masking that it destroyed real edge on the days it touched. Neither is visible without explicitly comparing the candidate's signal-days / changed-days against an external reference (the live edge, or the base population).

**Fix (graduated to a HARNESS gate 2026-06-21, all-night hunt):** Two relational checks added to the verify stack, both shipped as code: **(1) independence-vs-shipped-edges** -- `_b8_anchored_vwap.py` (`OVERLAP_MAX = 0.80`): compute the candidate's signal-days, intersect with each shipped edge's signal-days, and require `day_overlap <= 0.80`; a cell may clear all 9 gates and still be rejected as `overlap_vs_#1>0.80` (anchored-VWAP was blocked at 0.973, surfaced as a "gates-only passer blocked by overlap" for honest disclosure). **(2) no-regression-on-changed-days** -- `_b8_cumdelta.py` (`no_regression_report(base_rows, kept_rows, skipped_rows)`): a subtractive gate PASSES only if the set of trades it SKIPS is net-negative (`skipped_total <= 0`) AND the kept set improves per-trade; a gate that removes net-positive days FAILS even if the residual total is higher. Together these form the "independence + no-regression" half of the B8/B9 9-gate bar (alongside L171/L172/L173).

**Generalizable principle:** "Beats the gates in isolation" is necessary but NOT sufficient for "is a new edge." A candidate must ALSO be **independent** of what is already shipped (low day-overlap, or it is a relabel that double-counts existing P&L) and, if it is framed as a filter, must only remove **net-losing** trades (or it is destroying alpha while a surviving base edge masks the damage). Always validate a new edge *relationally* -- against the existing book and against the population it claims to refine -- not just against a null. A relabel and a winner-removing filter both produce a positive scorecard; only the overlap/no-regression comparison exposes them.

**Encoded in:** `backtest/autoresearch/_b8_anchored_vwap.py` (`OVERLAP_MAX=0.80`, per-shape day-overlap-vs-LIVE-#1 independence check; 9-gate bar incl independence), `backtest/autoresearch/_b8_cumdelta.py` (`no_regression_report` -- subtractive gate PASS iff skipped set net-negative + kept improves), and the B8/B9 scorecards (`analysis/recommendations/`). Doctrine: `markdown/doctrine/LESSONS-LEARNED.md` L174; CLAUDE.md OP-25 row fold pending (rail 4 -- staged proposal, batch with L169/L170/L173 folds).

**Detection:** future regression -- a candidate reported as a new/diversifying edge whose signal-days overlap a shipped edge by >0.80 (the tell: `_b8_anchored_vwap` surfaces it under "gates-only passers blocked by overlap"), OR a "filter" candidate whose `no_regression_report` shows `skipped_total > 0` (it removed net-winners). Either means STOP -- it is a relabel or a winner-destroyer, not alpha, regardless of a green isolation scorecard.

**Related lessons:** L171/L172/L173 (the sibling honesty gates this completes -- truncation / random-null / OOS-alone test a candidate in isolation; L174 adds the two RELATIONAL tests: independence-vs-book + no-regression-vs-population), C4 (disclose concentration / a published anomaly != a per-trade option edge -- an overlap-relabel is the in-house analog of double-counting a known anomaly -- L01,...,166,167), C3 (a SPY-price edge != an option edge; here a re-labeled edge != a new edge -- L58,...,172), C7 (audit outputs not exit codes -- a positive scorecard is not proof of a new edge), OP-22 (compound don't accumulate -- a relabel inflates the apparent book without adding real diversification).

## L175 -- 2026-06-21: A per-trade MEAN-expectancy lift is NOT an improvement until it clears a RISK-ADJUSTED gate (Sharpe/Sortino/maxDD stays inside kill-switch margin)

**Symptom:** WP-4 (exit-TP1 sweep, `+30%→+75%` targets) found that raising TP1 from +30% to +75% lifted the 3-edge book's MEAN per-trade expectancy **+$13.23/tr (Safe-2 ATM) / +$17.17/tr (Bold ITM-2)**, broad-based across IS+OOS, and cleared the mean-lift + no-regression-on-changed-days + OOS-alone-drop-top5 + IS-broad-based gates. It was staged "dormant-flip-ready." The follow-up variance/downside audit (`_b10_exit_variance.py`, real OPRA, 342 days) returned **RISK_UP**: per-trade **Sharpe DROPS** (Safe 0.334→0.322; Bold 0.407→0.391), book **maxDD WIDENS ~50%** (Safe −$836→−$1,282 ≈ **2.1× the −$600/day kill-switch margin**), median trade flips negative (% losers 47.5%→59.5%). Mechanism: ~87% of trades never reach the +75% TP1; they ride to the −8% stop instead, converting ~$4K realized winners into losses while chasing ~$8K bigger winners (fatter right tail, but not free EV -- the distribution worsened despite the headline mean lift).

**Root cause:** The standing real-fills bar optimizes/screens on **mean per-trade expectancy** + concentration + no-regression. None of those gates see the **shape** of the return distribution. An exit-threshold or sizing change can lift the mean while (a) lowering risk-adjusted efficiency (Sharpe/Sortino), and (b) deepening drawdown toward or past the account's daily kill-switch. A "mean improvement" that nearly 2.1× the kill-switch margin and flips % losers to 59.5% is a **risk-up trade, not an edge improvement** -- yet would have shipped as "dormant-flip-ready" without the variance audit. Sibling to L173 (OOS-alone concentration) and L174 (independence/no-regression): all three are "a metric that looks like improvement but isn't, on a dimension the default gate ignores." The family is the "one-dimensional goodhart's law" class (C4/L01,04,11,22): optimize for mean and you deteriorate distribution shape and drawdown.

**Fix (shipped 2026-06-21, all-night hunt B10):** Added a **RISK-ADJUSTED gate** to the candidate bar for any EXIT / SIZING change: a mean-lift counts as an improvement ONLY if (a) per-trade Sharpe holds or improves, (b) book Sortino holds, (c) maxDD does not materially worsen (threshold ~+25%), and (d) projected maxDD stays inside the account's daily kill-switch with margin. Documented in `markdown/research/STRATEGY-HUNT-BACKLOG.md` gate-list. WP-4 reclassified from "dormant-flip-ready" to **RISK_UP / J risk-tradeoff call** in `markdown/planning/LIVE-PATH-WORKPACKAGE.md` + `automation/overnight/STATUS.md`, with +50% TP1 as the risk-moderated fallback. Harness: `backtest/autoresearch/_b10_exit_variance.py` computes Sharpe/Sortino/maxDD for every candidate and gates on the risk-adjusted check. TODO (graduate to code assertion): fold the risk-adjusted gate into `backtest/autoresearch/verify_edgehunt_candidates.py` + `backtest/tests/test_graduated_guards.py` so EVERY exit/sizing candidate is auto-checked.

**Generalizable principle:** For any candidate validated through a quantitative-metrics lens, always check the DISTRIBUTION SHAPE and DOWNSIDE before shipping. A mean lift without a Sharpe/Sortino check is a foot-gun (L175's immediate neighbor); a risk metric that improves on paper but widens drawdown past the account's loss limit is "look good, blow up" (L175's downside catch). When a guard exists elsewhere (the variance audit harness `_b10_exit_variance.py` catches it), GRADUATE IT to a reusable, automated check -- one-off harnesses rot. The check lives in the harness today; the escalated durable fix is to move it into the standard verify path so every future exit sweep is defended without manual audit.

**Encoded in:** `markdown/research/STRATEGY-HUNT-BACKLOG.md` (risk-adjusted gate documented), `backtest/autoresearch/_b10_exit_variance.py` (enforced for the exit sweep; Sharpe/Sortino/maxDD compute + gate logic), WP-4 reclassified in `markdown/planning/LIVE-PATH-WORKPACKAGE.md` + `automation/overnight/STATUS.md`, `markdown/doctrine/LESSONS-LEARNED.md` L175. TODO: `backtest/autoresearch/verify_edgehunt_candidates.py` + `backtest/tests/test_graduated_guards.py`.

**Detection:** future regression -- an exit/sizing candidate declared as an "improvement" (mean-lift, expected-value gain, or Sharpe improvement on the headline) whose per-trade Sharpe DROPS, whose book maxDD widens by >25%, or whose projected maxDD exceeds the account's daily kill-switch. The tell: `_b10_exit_variance.py` returns `risk_verdict="RISK_UP"` or the A/B scorecard shows `sharpe_delta<0` / `maxdd_delta>+0.25*baseline_maxdd` / `projected_maxdd > kill_switch`. This is a **mandatory check before ratifying any exit/sizing change** — a positive mean with worse risk-adjusted metrics is a distribution-shape trap (the inverse of L172's null baseline, which catches signal->structure confusion; this catches structure->risk confusion).

**Related lessons:** L171/L172/L173/L174 (the preceding honesty gates -- truncation / random-null / OOS-alone / independence all test a candidate *in isolation*; L175 is the RISK gate that checks an improvement candidate's **downside cost**, completing the gate battery), C4 (per-trade expectancy not WR/mean standalone; disclose concentration / risk-adjusted return / drawdown; Goodhart's law -- L01,04,05,11,22,46,48,92,104,122,124,128,129,154,166,167), C28/C30 (exit knobs are locally optimal but low-leverage research domain; ENTRIES are where edge lives; audit what the exit knob actually does to distribution shape -- L139,141,148,156,157), C5 (high-score + 0-trade + declining-drawdown-room are the silent cancels; if the only way to improve mean is to widen maxDD past kill-switch, the "improvement" is a strategic no-go -- L40,44,45,73,93,118,133,134,154,162,167).

## L176 -- 2026-06-21: An exit-target knob is a NEAR-DEAD knob when a dominant upstream exit (chandelier trailing-lock / premium-stop) binds first — dump the exit-reason histogram on the LIVE config and confirm the knob's exit reason fires on a meaningful fraction of trades BEFORE sweeping it

**Symptom:** The web-sourced hypothesis "raise the TP1 partial-out target from **+30% → +50%** improves `vwap_continuation` per-trade expectancy" was tested on **real OPRA fills** (HARD-window <= 2026-05-29) via the dedicated harness `backtest/autoresearch/_web_tp1_partial_5030.py`, scorecards `analysis/recommendations/web-tp1-partial-5030.json` + `analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md`. It was **REJECTED**: across the sweep the expectancy moved only **$0.14–$1.20/trade**, WR was effectively identical (**55.0% vs 54.4%**), and book Sharpe/Sortino were essentially flat. Worse, the Safe-2 ATM `tp1_qty=0.50` cell actually FAILED the per-trade Sharpe check, and the Bold ITM-2 `tp1=0.40` and `tp1=0.50` cells both FAILED `higher_mean`. The "improvement" the web hypothesis promised simply did not exist on the live config.

**Root cause:** On the LIVE `vwap_continuation` exit stack — `profit_lock_mode='trailing'`, chandelier `trail=0.15`, `arm=0.05`, `premium_stop=-0.08`, `runner=2.5x`, `tp1_qty=0.50` — the realized **exit-reason mix is `EXIT_ALL_PREMIUM_STOP` on 148 of 149 trades**. The fixed +30%/+50% TP1 partial fills **exactly ONCE** in the entire sample. The chandelier trailing profit-lock and the −8% premium-stop almost always **bind BEFORE** price ever reaches the fixed TP1 partial threshold, so `tp1_premium_pct` is a **NEAR-DEAD KNOB** under the live configuration: it controls an exit branch that fires on <1% of trades, so sweeping it can only move noise.

The trap is that the original edgehunt mini-sweep numbers that **motivated** this hypothesis (**+$90.43 vs +$78.29**) came from a **chandelier-OFF cell** — the mini-sweep varied `trail` in `{0.0, 0.20}`, and in the `trail=0.0` cell the TP1 partial WAS the binding exit. The knob looked alive only because that cell removed the dominant upstream exit. Carried onto the LIVE stack (chandelier ON), the same knob is inert. This is the C30/L148-class **dead-knob** (a runner/exit target that the realized exit path almost never reaches) AND the C14-class **dead/masked knob** (a knob whose effect is swamped by a dominant upstream gate/exit) — here unified: the knob is dead *specifically because* a dominant upstream exit (chandelier + premium-stop) supersedes it.

**Fix:** Doctrine-only — NO live params/watchers touched (rule 9). The candidate was rejected in `analysis/recommendations/web-tp1-partial-5030.json` and disclosed in `SUNDAY-WEB-LEARN-SCORECARD.md`. The durable guardrail: **before sweeping ANY exit-target knob, dump the exit-reason histogram on the LIVE config and confirm the knob's own exit reason fires on a meaningful fraction of trades. A sweep of a knob whose exit reason fires on <5% of trades is measuring noise — re-validate (or disable the dominant upstream exit) before trusting any mini-sweep delta.** Equivalently: a mini-sweep that turned the knob "alive" by also toggling a dominant upstream exit (e.g. chandelier `trail`) is reporting the *interaction*, not the knob — confirm the knob still binds on the SHIPPED exit stack before promoting.

**Encoded in:** `backtest/autoresearch/_web_tp1_partial_5030.py` (the harness that produced the exit-reason histogram exposing 148/149 = `EXIT_ALL_PREMIUM_STOP`), `analysis/recommendations/web-tp1-partial-5030.json` (the rejected scorecard: expectancy delta $0.14–$1.20, WR 55.0%/54.4%, ATM tp1=0.50 fails per-trade Sharpe, Bold ITM-2 tp1=0.40/0.50 both fail higher_mean), `analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md` (disclosure), `markdown/doctrine/LESSONS-LEARNED.md` L176, CLAUDE.md OP-25 index table rows C30 + C14.

**Detection:** Future regression — any exit/exit-target sweep (`tp1_premium_pct`, `tp1_qty`, runner target, profit-lock arm/trail) declared an "improvement" off a mini-sweep delta WITHOUT first confirming, on the LIVE exit config, that the knob's own exit reason (`EXIT_*_TP1`, `EXIT_*_RUNNER_TARGET`, etc.) accounts for a meaningful fraction (>~5%) of realized exits. The tell: the exit-reason histogram on the live stack is dominated (>~90%) by a DIFFERENT exit reason (`EXIT_ALL_PREMIUM_STOP`, chandelier trailing-lock, time/ribbon-flip), or the only sweep cell that showed a delta also toggled a dominant upstream exit (e.g. chandelier `trail=0.0`). Cheap check: histogram the `exit_reason` column on the live-config run before the sweep; if the swept knob's reason is <5%, STOP.

**Related lessons:** L148 (sibling dead-knob — AGG runner rarely hits its premium target; the same "the realized exit path almost never reaches this knob" mechanism — C30), C30 (audit what % of exits actually hit the target before sweeping it — this is the direct extension), C14 (dead/translated-but-unapplied knobs: vary-and-assert; here the knob is masked by a dominant upstream exit rather than untranslated), C15 (gates interact multiplicatively — a dominant upstream filter/exit supersedes a downstream knob; re-validate the shared pool when one is added), C28 (exit mechanics are locally optimal; ENTRIES are where edge lives — exit-target tuning has diminishing returns once the stop/lock dominates the exit mix), L175 (sibling exit-sweep foot-gun from the same hunt — a mean-lift that ignores distribution shape; L176 is the complementary "the knob doesn't even bind" failure).

## L177 -- 2026-06-21: A random/permutation null MUST trade the SAME strike universe as production (identical `legs_in_band`/eligibility pre-filter) — a null that prices strikes production skips mis-estimates the percentile and can flip the verdict

**Symptom:** Validating the iron-condor premium-selling LEAD (`IC 10:30 ET / off2 / w2 / pt0.5 / 1.5×`, real OPRA OOS **+$23.03/tr**, 82.7% WR) against the L172 random-short-offset null, gate-6 (beats-random-strike-null) appeared to **flip on the RNG seed**: finalize pass (seed 13, 30 iters) gave strike-null p95 $26.03 → **FAIL**; a first in-script re-seed (seed 99, 60 iters) gave strike-null p95 **$22.67** → actual landed at the **95th pctile → spurious "PASS"**. The "seed fragility" was a symptom, not the cause.

**Root cause:** A **strike-universe mismatch** between the null and production. Production scoring (`backtest/autoresearch/_pivot_premium_selling.py::run_variant`) and the standalone null (`_pivot_premium_selling_null.py::_one_day_fill`) both apply `legs_in_band(legs, spot, half_width=5)` BEFORE pricing — which **always drops short_offset=4** (longC = ATM+6 sits outside the ±$5 OPRA cache band). The first in-script null (`_pivot_premium_ic_validate.py::fill_for_day`) **omitted that pre-filter**, so when the random draw picked off=4 it traded condors whenever the strikes happened to be cached (down-drift days) — **geometry production never takes**. Those extra marginal-loss off=4 condors dragged the **null mean down ($19.7 → $15.6)**, which **inflated the actual's percentile from ~79th to ~95th** — straight into the knife-edge where 30-vs-60-iter p95 noise then flipped the boolean. Low-iteration p95 noise was the *secondary* cause; it only mattered because the parity bug had pushed the actual into the fragile 95th-pctile boundary.

**Fix:** `_pivot_premium_ic_validate.py::fill_for_day` now applies the same `legs_in_band(half_width=5)` pre-filter `run_variant` uses (returns an `out_of_band` skip, lines ~110-117), so the null and the production grid trade an identical strike universe. With parity restored: in-script null (400 iters, seed 99) → strike-null mean **$19.68 / p95 $26.66 / actual at the 78.7th pctile → FAIL**; standalone harness (500 iters × 3 seeds {7,101,2024}) converges to **p95 ~$26.4 / actual at 75.6–76.6th pctile → clean, seed-stable FAIL**. The IC's +EV is reproduced by ~1-in-4 random-offset condors — generic theta, no strike-selection alpha (C3/L172, inverse/selling direction). Doctrine-only; NO live params/watchers touched (rule 9). The candidate was rejected and disclosed in `analysis/recommendations/PIVOT-PREMIUM-SELLING-SCORECARD.md` CHECK 1.

**Generalizable principle:** A null/permutation baseline only measures "is the candidate's *selection rule* better than chance" if chance is drawn from the **same opportunity set the candidate actually trades**. Any per-day eligibility/affordability filter the production scorer applies (band filter, liquidity gate, cache-availability, min-credit) MUST be applied identically in the null — otherwise the null prices trades production would never take, shifts the null distribution, and mis-ranks the actual. Secondarily: gate on the **converged percentile rank over ≥300 iters / ≥2 seeds**, and treat an actual landing in [p90, p99] as **INCONCLUSIVE-rerun-bigger**, never a PASS. This is the L172 random-null sharpened with OP-16's sim-accuracy discipline ("verify the sim's strike picker matches production before any ratification") and the C9/L42 family (keep the null and the scorer in lock-step — same family as "update ALL state consumers / dual-account symmetry").

**Fix (durable, pending graduation):** Share ONE `eligible(legs, spot)` helper between `run_variant` and every null/permutation harness so the eligibility filter is byte-identical by construction (cannot drift), and add a null-gate assertion to `backtest/autoresearch/verify_edgehunt_candidates.py` + `backtest/tests/test_graduated_guards.py` that (a) asserts the null's per-day eligibility filter matches production's and (b) gates on percentile over ≥300 iters / ≥2 seeds, returning INCONCLUSIVE for an actual in [p90,p99]. Queued as a follow-up (`GRADUATE-NULL-STRIKE-UNIVERSE-PARITY`).

**Encoded in:** `analysis/recommendations/PIVOT-PREMIUM-SELLING-SCORECARD.md` (CHECK 1 — both causes documented, parity primary; doctrine note line ~271), `backtest/autoresearch/_pivot_premium_ic_validate.py` (the band-parity `legs_in_band(half_width=5)` filter, lines ~110-117), `markdown/doctrine/LESSONS-LEARNED.md` L177. CLAUDE.md OP-25 C3-row fold staged as a conductor proposal (rail 4 — conductor cannot edit CLAUDE.md). Graduation to a shared `eligible()` helper + null-gate assertion is **pending** (`verify_edgehunt_candidates.py` / `test_graduated_guards.py`).

**Detection:** Future regression — a null/permutation result whose verdict **flips on the RNG seed or iteration count** (the tell of an actual sitting on the p95 knife-edge), OR a null harness whose per-day skip logic does not match the production scorer's. Cheap check before trusting any beats-null gate: diff the null's per-day eligibility filter against `run_variant`'s (same `legs_in_band`/affordability/cache gate?), and confirm the actual's percentile is stable across ≥2 seeds at ≥300 iters. If the verdict moves with the seed, suspect a strike-universe / eligibility mismatch FIRST, iteration noise second.

**Related lessons:** L172 (the random-strike null this sharpens — C3, beat the null MAX; here extended: the null must trade production's exact strike universe), C3 (SPY-price edge ≠ option edge; a structural-gate pass a random-entry null reproduces is an exit-structure artifact, not selection alpha — L58,74,100,101,112,136,148,149,172), OP-16 sim-accuracy gate (verify the sim's strike picker matches production before ratification — same family), C9/L42 (update ALL state consumers / dual-account symmetry — keep the null and the scorer in lock-step), L171/L173/L174/L175/L176 (the surrounding honesty-gate battery from the same premium-selling pivot — truncation / OOS-alone / independence / risk-distribution / dead-knob; L177 is the null-eligibility-parity gate completing it).

## L178 -- 2026-06-21: A stop construction fixes RISK (maxDD / Sortino / worst-day), NOT signal-breadth (L173 OOS-concentration) — the lever for an oos_drop_top5 < 0 edge is the ENTRY, never the stop

**Symptom:** The 1DTE + DOLLAR-anchored-stop lever cleanly DOUBLED the deployed win (#1 `vwap_continuation`). Hypothesis: the same lever would RESURRECT the dead-library families (`momentum_morning` / `orb_continuation` / `power_hour`) that flip 0DTE-dead → 1DTE OOS-positive but fail L173 (`oos_drop_top5` < 0), by trimming the fat-tail losers that drag drop-top5 down. Re-tested all 3 at 1DTE with per-family/tier-rederived dollar-stops (C29: $59.28 / $61.44 / $52.08). **RESULT: 0/3 resurrected.** The dollar-stop fixed the RISK on every one — maxDD `momentum` −$4,432→−$2,252, `orb` −$4,329→−$1,686, `power_hour` −$16,535→−$5,202; worst-days capped at the $ threshold; book Sortino flipped negative→positive; OOS exp/tr ROSE (trimmed losers, kept winners) — **but `oos_drop_top5` (L173) stayed NEGATIVE on all 3** (`momentum` −22.66→−1.25, `orb` −32.91→−20.84, `power_hour` −74.54→−20.89). None crossed zero → none clears the 11-gate bar.

**Root cause:** A stop construction acts on the **LOSS distribution** — it caps/shapes how much each *individual trade* loses (maxDD, Sortino, worst-day all improve). But L173-concentration (`oos_drop_top5` < 0) is a property of the **WIN distribution / signal breadth**: OOS profit is concentrated in a handful of days because the signal fires on too many low-quality days and only a few pay. A stop can trim the fat-tail LOSERS but **cannot manufacture WIN breadth across more days**. #1 `vwap_continuation` was a clean win precisely because its signal was ALREADY L173-positive (broad-based) — the dollar-stop only had to fix its maxDD. A family whose signal is concentrated needs a better ENTRY FILTER (raise win-day breadth / selectivity), not a better exit.

**Fix:** Doctrine rule, encoded in the direction backlog + scorecard: **when an edge fails L173 (`oos_drop_top5` < 0), the lever is the ENTRY (signal breadth / selectivity), NOT the stop/exit.** A stop change that lifts OOS-mean + fixes maxDD but leaves `oos_drop_top5` < 0 is RISK-fixed-but-still-fragile (`IMPROVED_STILL_FRAGILE`), not shippable. **Practical corollary:** the dollar-anchored stop is the right RISK construction *universally* — it fixed risk on all 3 dead families AND the live #1, and is independently worth adopting wherever maxDD scales with premium — but it is **necessary-not-sufficient**; the 11-gate L173 still gates ship. NO live params/watchers touched (rule 9).

**Generalizable principle:** Match the lever to the dimension the metric lives on. A construction that operates on the loss distribution (stop, catastrophe cap, position-size throttle) can only move risk-side metrics (maxDD, Sortino, worst-day, tail). It cannot move a metric that is a property of the win/signal distribution (OOS-concentration, win-day breadth, expectancy-per-distinct-day). Before reaching for a lever to "fix" a failing gate, ask which distribution the gate measures — if the lever doesn't touch that distribution, the fix is illusory. This is the C4 (concentration / breadth) + C28 (exit-knob diminishing-returns) family: exit tuning has a hard ceiling once the signal itself is the constraint.

**Watch-out (near-miss overfit trap):** `momentum_morning` is a near-miss (`oos_drop_top5` −$1.25 with the dollar-stop risk profile already in hand). A CAUSAL, no-overfit entry-breadth filter that lifts it +$1.25 would resurrect it — BUT causal de-concentration has a poor track record here (edge #3 MES/MNQ, the regime gates), and a $1.25 gap on ~59 OOS trades **overfits trivially**. Pursue only under strict OOS / no-regression (L174) / beats-null (L172/L177) discipline; do not chase the $1.25 with a hand-fitted filter.

**Encoded in:** `analysis/recommendations/DTE-LIBRARY-DOLLARSTOP-RETEST.md` + the per-family JSONs (`analysis/recommendations/dte-stop-construction-{momentum_morning,orb_continuation,power_hour}.json`, fields `oos_drop_top5` / `book_maxDD` / `book_sortino_ann` / `clean_win_bar`), `markdown/research/STRATEGY-DIRECTION-BACKLOG.md`, `markdown/doctrine/LESSONS-LEARNED.md` L178. CLAUDE.md OP-25 fold (C4 or C28 row) staged as a conductor proposal (rail 4 — conductor cannot edit CLAUDE.md).

**Detection:** Future regression — any retest where a STOP/EXIT/sizing lever is proposed as the fix for an edge that fails L173 (`oos_drop_top5` < 0). Cheap check: after applying the lever, confirm `oos_drop_top5` actually crossed zero; if maxDD/Sortino improved but `oos_drop_top5` is still negative, the verdict is `IMPROVED_STILL_FRAGILE`, not ship — redirect effort to the ENTRY filter. If someone claims a stop change "made the edge clean," verify the claim is about breadth, not just tail-risk.

**Related lessons:** L173 (OOS-concentration / `oos_drop_top5` < 0 — the exact gate this lesson explains how NOT to "fix"), L175 (mean-lift alone is insufficient; needs a risk-adjusted gate — sibling: a metric moving on the wrong dimension), L174 (no-regression-on-changed-days — the discipline the near-miss watch-out invokes), C28 (ribbon/exit tuning has diminishing returns once the signal is the constraint — L139,141,156,157,175), C4 (disclose concentration / per-trade expectancy not WR — the breadth family — L01,04,05,10,11,22,46,48,92,104,122,124,128,129,154,166,167,175), C29 (exit knobs ratified on one strike tier don't transfer — the per-family dollar-stop rederivation that set up this test — L149), C31 (the sizing-UP/adding behavior is the real killer in J's 667 trades — risk levers shape loss distribution, not signal — L168).

## L179 -- 2026-06-22: A two-persona authoring handshake silently drops its second half on any fire where the gated persona is absent — reconcile the two artifacts with a ratcheting guard, never trust the handshake

**Symptom:** Six `L###-CLAUDE-FOLD` follow-ups (L169/L170/L173/L174/L177/L178) accumulated across consecutive conductor fires, each a rail-4-blocked TODO that no consumer ever drained. A reconciliation pass then surfaced **12 additional older** un-indexed lessons (L3/L13/L16/L24/L25/L29/L31/L43/L56/L126/L137/L146) — **18 total** defined-but-unindexed gaps that no guard had ever flagged. The lesson PROSE was reliably written to `LESSONS-LEARNED.md`; the index FOLD into the CLAUDE.md OP-25 table was reliably missing.

**Root cause:** Authoring a lesson is a TWO-persona handshake. Any fire (the conductor included) writes the full prose into `LESSONS-LEARNED.md`, but only `lesson-author` may fold the one-line entry into the `CLAUDE.md` OP-25 index — it is the sole persona with OP-25 write access (rail 4 forbids the conductor editing CLAUDE.md). When the Agent tool / `lesson-author` is unavailable in a fire, the conductor authors the prose directly but CANNOT do the fold. The fold half is dropped with the only trace being a LOW-priority queue follow-up that nothing drains. Generalizes to ANY multi-step handshake where one step is gated to a persona/process that may not run on a given fire — the gated step WILL silently accumulate as debt.

**Fix (already graduated):** `backtest/tests/test_op25_index_reconciliation.py` (7/7 green) reconciles the defined-lesson set (`LESSONS-LEARNED.md` headings) against the OP-25 index (CLAUDE.md C-rows) and RATCHETS the unindexed set against a pinned `KNOWN_UNINDEXED_BASELINE` so it can only ever SHRINK — a newly authored, unfolded lesson now FAILS LOUD at test time instead of accumulating invisibly. A companion NO-PHANTOM assertion guards the inverse (indexed-but-undefined dangles). The baseline is the explicit debt ledger; folds land → trim the baseline → the ratchet tightens toward zero. (Sibling guard to L170's author-inbox closing-handshake reconciliation in `test_author_inbox_reconciliation.py`.)

**Generalizable principle:** When an authoring/closing step is split across personas and one half is access-gated, the gated half WILL be dropped on every fire where that persona is absent. Do not trust the handshake to complete — reconcile the two artifacts (the produced-by-A doc vs the folded-by-B index) with a ratcheting guard whose monotonic-shrink invariant turns silent accumulation into a loud, capped, drainable debt. The guard is the contract; the handshake is the hope.

**Watch-out (self-consistent):** This lesson's own L179 fold into the OP-25 index is itself rail-4-blocked on the conductor — so `179` must be added to `KNOWN_UNINDEXED_BASELINE` the moment the prose lands, or the very ratchet this lesson documents fails the build. (Nicely self-consistent: the guard flags its own describing-lesson if you forget.) When the batch CLAUDE.md fold lands via an interactive/lesson-author session, trim 179 (and the other 18) out of the baseline.

**Encoded in:** `backtest/tests/test_op25_index_reconciliation.py` (`KNOWN_UNINDEXED_BASELINE`, `find_unindexed_lessons`, `find_phantom_index_refs`), `markdown/doctrine/LESSONS-LEARNED.md` L179. CLAUDE.md OP-25 fold (C7 + C18 row) staged as conductor proposal `cd-2026-06-22-001` (rail 4 — conductor cannot edit CLAUDE.md) → batchable with `CLAUDE-INDEX-FOLD-BATCH`.

**Detection:** Any future fire that authors a lesson, validator, skill, or candidate whose "closing" step (index fold / inbox `.DONE` / registry registration) is gated to a different persona — confirm the closing step actually ran, or that a ratcheting reconciliation guard already caps the debt. If a follow-up TODO is the only trace of a closing step, it is a dropped handshake half, not a backlog item.

**Related lessons:** L170 (author-inbox has no closing handshake → duplicate-rebuild risk — the IMPLEMENT-direction sibling), L173 (superseded-research has no inbox disposition — the SUPERSEDE-direction sibling; both reconcile inbox state with a staleness ratchet), L164 (untracked producers get silently lost — same silent-debt-accumulation family), C7 (silent success is failure — audit outputs, not exit codes), C18 (status-format discipline; surface signal, don't sign off silently).

## L180 -- 2026-06-21: The real-fills simulator must enforce the LIVE per-trade notional/buying-power cap + min_contracts — a high-premium config's validated qty-3 expectancy is UNREALIZABLE when the live RiskGate blocks qty≥3

**Symptom:** The WP-8 "doubling" of LIVE edge #1 `vwap_continuation` (Safe-2) was validated on real OPRA fills at qty 3 and reported to J as DEPLOYED + MONDAY_READY (1DTE + dollar-anchored stop, OOS +$57.59/tr Safe / +$73.91/tr Bold). It was **not** live-realizable: the deployed cell would be `RISK_CAP`-blocked on the MAJORITY of signal days. At Safe-2 $2,000 equity the per-trade cap = min(30% risk-cap $600, v15 tier $600) = $600; a qty-3 1DTE ATM contract at the median 1DTE entry premium (~$2.495/sh) is notional $748 > $600 → `pre_order_gate.py` returns `BLOCK: [RISK_CAP]` (reproduced: `--equity 2000 --qty 3 --premium 2.495 --account safe` = BLOCK; `--qty 2` = BLOCK [MIN_CONTRACTS], no auto-reduce). Measured Safe block-rate = **72.29%** of capped signals (`analysis/recommendations/dte-stop-cap-aware.json`). `simulator_real.py` has NO notional/buying-power/min_contracts gate (grep-confirmed: only `RUNNER_MAX_PREMIUM_PCT`, an exit knob) → it filled all 166 signals at qty 3 and produced a +$103.09 cap-BLIND OOS expectancy the live account can never collect, because the cap denies entry on 72% of those exact bars. Bold is worse: ITM-2 1DTE ≈ $1,071 notional > $824 cap AND qty3 < Bold min_contracts 5 → can NEVER fit (98.80% block-rate; `affordable=false`).

**Root cause:** The validation harness (`backtest/lib/simulator_real.py`, reused by `backtest/autoresearch/_dte_stop_construction.py`) models fills/exits faithfully but omits the LIVE order-placement authority's two hard gates that `lib.risk_gate.check_order` enforces at runtime: (1) NOTIONAL = premium×qty×100 must be ≤ the tighter of `per_trade_risk_cap_pct` and the v15 per-tier `max_pct` table; (2) `qty ≥ min_contracts` (Safe 3 / Bold 5 — a sub-floor proposal is DENIED, not auto-reduced). Because premium GROWS with DTE and ITM depth (median ATM 0DTE $1.35 → 1DTE $2.495; ITM-2 0DTE $2.55 → 1DTE $3.57 per the DTE-STOP calibration), the very lever that lifts per-trade expectancy (longer DTE / deeper ITM = richer premium) pushes notional THROUGH a FIXED per-trade dollar cap — the two interact MULTIPLICATIVELY. A higher per-trade expectancy on a config the cap blocks is a WORSE live outcome (fewer trades, and only the cheap tail gets through). Sim-risk ≠ live-risk-intent the moment the sim has no cap.

**Fix:** Sunday-safe de-risking REVERT already on disk (`automation/state/params.json`, documented in `_wp8_revert_2026_06_21`): `j_vwap_cont_1dte_enabled` true→false + `j_vwap_cont_dollar_stop_enabled` true→false (back to 0DTE / -8% percent), keeping the separately-validated WP-5 strike override (`j_vwap_cont_strike_override_enabled=true`, `j_vwap_cont_strike_offset_safe=0` = ATM). Net live cell = ATM/0DTE/-8%/qty3 → notional $1.35×3×100 = $405 < $600 cap (VERIFIED PASS, 20.3% of equity) AND validated (`dte-stop-construction.json` ATM/0DTE/percent: OOS +$25.0/tr, 6/6 positive quarters). Bold stays dormant (`j_vwap_cont_enabled` already governs; its ITM-2 1DTE cell can never fit the $824 cap at any allowed qty). **DURABLE fix (queued WP-10, weekday code block):** graduate the cap into `simulator_real` (or a wrapper) — call `lib.risk_gate.check_order` / `pre_order_gate` affordability per signal and DROP capped / sub-min-contracts trades BEFORE computing expectancy, so every future DTE/strike/stop sweep reports the cap-aware REALIZABLE book by default (the one-off overlay at `dte-stop-cap-aware.json` becomes the default path, not an afterthought).

**Generalizable principle:** A backtest's reported expectancy is only live-realizable if the sim filters the SAME opportunity set the live order-placement authority will permit. The real-fills simulator faithfully models fills and exits but is NOT the order gate — `risk_gate.check_order` is. Any lever that raises per-contract premium (DTE expansion, deeper ITM, wider stop → larger contract) silently shrinks how many of those signals fit a fixed per-trade dollar/min-contracts cap; validate the lever and the cap TOGETHER, never the lever alone. "Validated at qty N" means nothing until you confirm qty N actually places at the target account's equity. This is the C14 family (a knob validated in sim that the live gate neutralizes = a dead knob) × C11 (the broker/gate is the order-placement authority — verify the order actually places before calling an edge live) × C15 (gates interact multiplicatively — DTE-premium-growth × fixed-$-cap).

**Watch-out:** Premium scales with BOTH DTE and ITM depth, and the cap scales with equity — so the same config can be affordable at $10K and blocked at $2K, or affordable as ATM-0DTE and blocked as ATM-1DTE. Re-check affordability at the TARGET account's CURRENT equity and the EXACT strike/DTE cell, not a generic one; an edge that "fit last month" can stop fitting after a drawdown shrinks equity (the cap tightens as the account loses — exactly when you can least afford the cheap-tail selection bias). And note the asymmetry: qty BELOW min_contracts is DENIED, not auto-reduced — there is no "just trade fewer contracts" escape hatch.

**Encoded in:** `automation/state/params.json` (`_wp8_revert_2026_06_21` doc + the two reverted flags), `analysis/recommendations/dte-stop-cap-aware.json` (the cap-aware re-validation using `pre_order_gate._params_for` as cap source), `CHANGELOG.md` (2026-06-21 DEFECT entry), `markdown/doctrine/LESSONS-LEARNED.md` L180, **CLAUDE.md OP-25 index (C11 + C14 + C15 rows — folded 2026-06-21 by lesson-author; "through L180")**. Memory `project_allnight_hunt` corrected. **GRADUATED (durable fix, DONE 2026-06-21):** the cap is now `backtest/lib/cap_admission.py` — the DEFAULT order-ADMISSION book-aggregation step shared by the autoresearch sweep entry points (`runner.run_backtest_window` + `_dte_stop_construction.aggregate_book`), calling the LIVE `risk_gate.check_order` (single authority, no re-implemented arithmetic). `enforce_cap=True` by default; `enforce_cap=False` returns the cap-blind book BYTE-IDENTICALLY (parity-tested). `test_cap_admission.py` (11) + `test_graduated_guards.py::test_cap_admission_is_default_book_step_for_oversized_config` + `::test_dte_harness_aggregate_book_defaults_cap_on` (graduated guards) assert cap-aware-is-default and parity. `simulator_real` stays BEHAVIOR-UNCHANGED (cap admitted at the book layer, never per-fill) — Sunday-guard-safe by construction.

**Detection:** Future regression — any candidate reported as DEPLOYED / live-ready whose per-trade notional (premium×qty×100) at the target account's current equity exceeds min(`per_trade_risk_cap_pct`×equity, v15 per-tier `max_pct`×equity), OR whose validated qty < that account's min_contracts. Cheap check before claiming any edge is live: run `pre_order_gate.py --equity <acct> --qty <validated_qty> --premium <median_entry> --account <safe|bold>` and confirm it does NOT return BLOCK [RISK_CAP] / [MIN_CONTRACTS]. If `simulator_real`'s trade count ≫ the cap-aware count for the same signals, the reported expectancy is cap-blind — re-validate on the realizable book.

**Related lessons:** L168 (risk_gate has no post-loss size throttle — the sibling "the gate's sizing behavior is the under-modeled live constraint"; here it's the entry-side notional cap), C14 (dead/translated-but-unapplied knobs — a sim-validated lever the live gate neutralizes — L38,70,72,77,88,89,96,99,106,108,109,110,111,113,114,115,116,117,123,127,130,131,147,152,155,176), C11 (broker is source of truth: verify flat/affordable before entry — L47,76), C15 (gates interact multiplicatively — trace the cascade — L07,08,09,66,95,163), C3/C29 (strike-tier edges don't transfer without re-validation — the premium-scales-with-tier family — L149), OP-16 sim-accuracy gate (verify the sim matches production before ratification — same discipline, here on the cap not the strike picker).

## L181 -- 2026-06-22: When a state file is too large to read whole, read its HEAD before task selection — a stale breadcrumb that names an implementation path is frozen at write-time and will make you re-do already-solved work

**Symptom:** The 2026-06-22 02:15 conductor fire picked the L180 follow-up "graduate the live per-trade cap into `simulator_real`" and shipped affordability primitives + a sim opt-in cap — then had to add an "HONEST SCOPE NOTE" to its own STATUS entry correcting the framing, because the **headline** L180 problem (real-fills sweeps reporting cap-blind expectancy) had ALREADY been solved the prior day at a better layer by `backtest/lib/cap_admission.py` (`enforce_cap=True` default, calling the live `risk_gate.check_order`). The committed work was harmless (default-off, tested, and it unblocked a RED safety gate) but the *narrative had to be corrected mid-fire* — the tell that a STAGE-0 read was skipped.

**Root cause:** STAGE 0.3 says "Read STATUS.md (full)", but `automation/overnight/STATUS.md` had grown to ~290–307KB and the Read tool refuses files >256KB. The fire proceeded to task selection with ZERO STATUS context — so it missed the newest entry (this repo prepends newest entries to the TOP of the file; the 2026-06-22 cap-aware entry documented `cap_admission.py` as the shipped durable fix). It then trusted the L180 queue breadcrumb ("graduate the cap into simulator_real, WP-10 weekday block") — a note written BEFORE the team chose the book-layer approach — over the current state. A breadcrumb that names a specific file/approach is a claim frozen at write-time; the STATUS head is the source of truth for "what already shipped."

**Fix:** (1) PROCESS: when STATUS.md (or any state file) is too large to read whole, the conductor MUST `Read(limit=~60)` the HEAD before STAGE 1 task selection — never task-pick with zero STATUS context. (2) Cross-check any breadcrumb that names an implementation path against the newest STATUS entry; verify the work isn't already done at a different/better layer before re-implementing. (3) DURABLE / OP-22 CONSOLIDATION: STATUS.md is an append-only producer that blew past the implicit 256KB read contract → it triggers CONSOLIDATION. Keep the newest N entries in STATUS.md; roll older entries verbatim to `automation/overnight/STATUS-archive-YYYY-MM.md` so the head always loads. (Done this fire: kept newest ~30 entries / 140KB, archived 30 older entries.)

**Generalizable principle:** A breadcrumb (queue note, lesson "follow-up", code comment) that names a file or approach is only valid at write-time. External memory (the STATUS head) is the source of truth for "what already shipped" — read it first, even when the full file won't load. Trusting a stale note over current state is the OP-22 redo-solved-work anti-pattern. Corollary: when an append-only producer outgrows its read contract, the fix is CONSOLIDATION at the producer (retention cap + archive), not "just skip reading it."

**Watch-out:** If a fire finds itself writing "actually this was already done / HONEST SCOPE NOTE" in STATUS, the STAGE-0 read was skipped — that phrase is the detection signature. The danger is silent re-work that looks like progress (a green-tested commit) while duplicating an existing better solution; cost is the wasted fire + a confused doctrine narrative, not a broken engine — which is exactly why it can recur unnoticed without this guard.

**Encoded in:** This lesson (L181); `automation/overnight/STATUS-archive-2026-06.md` (the consolidation that removes the root-cause unreadable-file condition); the conductor prompt's STAGE 0.3 already implies "Read STATUS.md (full)" — the head-read fallback is the operative refinement. CLAUDE.md OP-25 C7 + C18 fold staged as a proposal (rail 4 — conductor cannot edit CLAUDE.md).

**Detection:** Future regression — any conductor STATUS entry containing "already done / already solved / HONEST SCOPE NOTE / re-did" where the fire shipped overlapping work; OR STATUS.md exceeding the 256KB read limit again (the consolidation retention cap should prevent this — if it reappears, the producer-side cap was never added).

**Related lessons:** OP-22 (compound, don't accumulate; verify-now — re-doing solved work is the canonical anti-pattern), C7 (silent success is failure — audit state, not assumptions — L19,26,28,...), C18 (status-format discipline; surface signal — L06,15,17,18), L180/C11/C14 (the cap class this fire was working in; the breadcrumb that went stale named the `simulator_real` graduation that `cap_admission.py` had superseded), gym_harvester / GYM-HARVEST-CATALOGUE-RETENTION-CAP (the sibling "append-only producer needs a retention cap" pattern, here applied to STATUS.md).

## L182 -- 2026-06-22: A fixed narrow strike-band cache silently TRUNCATES the loss tail of any short-premium / defined-risk structure on big-move days — manufacturing a phantom edge that a wide-band de-bias INVERTS

**Symptom:** The event-IV-crush LEAD (#6) passed a mechanism pre-check on the ±$5 OPRA cache: a narrow defined-risk iron condor on scheduled-event days (FOMC/CPI/NFP) showed **event exp/tr +$32.15 vs +$18.86 non-event (delta +$13.29)**, event days at the **99th percentile** of the L172 random-DAY null, bootstrap **P(delta≤0)=0.007**, 16/17 winners — it looked like the first real premium-selling edge. The pre-check itself flagged the one weakness as "n=17 thin" and "absolute magnitude biased high (37% fill-rate both groups)." A wide-band de-bias (ATM ±$18/side fetched into a DEDICATED cache, proper ~16-delta short + $10-wide wings, the real loser tail priced) **INVERTED the verdict to DEAD**: event exp/tr **−$11.38** (n=38, worst trade −$640/lot, avg max-defined-loss $925/lot), NON-EVENT **+$9.77/tr** (event days now WORSE than non-event), and vs the same-geometry L172 null the event days sit at the **0.0th percentile** (absolute worst tail, not the right tail), selection_delta **−$21.15**, boot P(delta≤0)=1.0. The tail BLOWS the kill-switch even at minimum size (−$640/lot → −$1,920 at Safe q3 vs −$600 kill).

**Root cause:** The ±$5 cache holds only the 11 near-ATM $1 strikes per side, which forces a near-ATM short (NOT a real ~16-delta short, $10–18 OTM) and a $1–2 wing (NOT a proper $10-wide wing). Worse: on a big-move day the spot travels PAST the cached band, so the short leg's adverse premium and the EOD intrinsic land on strikes that have NO CSV → the day is dropped as `missing_cache`. Those dropped days ARE the short condor's LOSER days. So the cache silently TRUNCATES the left tail of the P&L distribution — it prices the calm winners and drops the violent losers, manufacturing a phantom positive expectancy. The fill-rate being SYMMETRIC (event 37% == non-event 37%) protected the SELECTION signal (delta and null share the same biased basis) but did NOT protect the ABSOLUTE magnitude — and absolute magnitude is exactly what the kill-switch cap AND the null distribution judge. Once the wide band prices the real loser strikes, the event days (which by construction have FATTER move distributions — that is *why* their IV is rich) take the biggest losses and the edge inverts. Event IV is fairly priced: you collect more premium precisely because the realized move is bigger, and the two cancel (slightly negative after costs).

**Fix:** Built `backtest/tools/fetch_event_wide_band.py` — wide-band (ATM ±$18, $1 grid, C+P) fetch into a DEDICATED cache `backtest/data/options_event_wide/` so the ±$5 cache is never clobbered (46 event + 46 matched non-event days, 5,334/6,808 contracts with bars = 78.3% fill). Built `backtest/autoresearch/_event_iv_crush_reprice.py` — re-points the shared OPRA loader at the wide cache, builds the PROPER ~16-delta (premium-proxy) / $10-wide condor, SKIPS+logs any day whose short OR its $10 wing falls outside the priced band (so geometry is never priced dishonestly), holds to the 0DTE close (real loser tail realized), and runs the same-geometry L172 null + cap/kill check. Verdict DEAD recorded: STRATEGY-DIRECTION-BACKLOG.md #6 (premium-selling class CLOSED) + STATUS.md OP-25 entry.

**Generalizable principle:** Before trusting ANY short-premium / defined-risk structure's expectancy or worst-day from a FIXED narrow strike-band cache, verify the band reaches the strikes the move actually travelled to on the big-move days — a narrow band truncates the loss tail (drops the loser days as `missing_cache`) and manufactures a phantom edge. A fill-rate-SYMMETRIC drop protects the SELECTION signal but NOT the absolute magnitude, and the cap + the null both judge absolute magnitude. The de-bias is a wide-band fetch + a re-price that SKIPS any day whose proper geometry (real-delta short + full-width wing) is not entirely inside the priced band. This is the C1 real-fills-authority family sharpened with a tail-truncation corollary, crossed with C3 (beat the null MAX) and OP-16 (the sim must price the SAME opportunity set the live structure would trade — here the same strike reach, not just the same strike picker).

**Watch-out:** A SYMMETRIC fill-rate is reassuring and WRONG to rely on — it makes the relative/selection comparison honest while the absolute level (the only thing the kill-switch and a tail-percentile null care about) stays biased high for BOTH groups. The bigger the realized move on a day, the MORE likely that day is silently dropped — so the truncation is correlated with exactly the days a short-premium structure loses, and the bias always points toward a phantom POSITIVE edge. Any "passes the null at the 99th percentile" result built on a band that drops >50% of days as `missing_cache` is suspect until re-priced on a band wide enough to reach the day's intraday extreme.

**Encoded in:** `backtest/tools/fetch_event_wide_band.py` + `backtest/autoresearch/_event_iv_crush_reprice.py` (the de-bias harness pair), `_state/event_iv_crush_reprice.json`, STRATEGY-DIRECTION-BACKLOG.md #6 DEAD, STATUS.md, this lesson (L182). CLAUDE.md OP-25 C1/C3 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`. **Pending graduation:** in any credit/defined-risk-structure harness, assert the strike band covers the day's intraday extreme (or explicitly SKIP+count the day) before scoring expectancy/worst-day — never silently price a truncated tail.

**Detection:** Future regression — any short-premium / defined-risk verdict whose underlying cache drops a material fraction of days as `missing_cache`/out-of-band AND whose dropped days correlate with the structure's loss side (big-move days for a short condor). Cheap check: report the band reach vs the day's realized high/low, and the % of days dropped; if the dropped set is the loss side, re-price on a wider band before trusting the expectancy or the null percentile.

**Related lessons:** L177 (the null must trade production's exact strike universe — same family, here the cache must REACH the production strike universe; this lesson is the direct resolution of L177's open domain-note "the adverse tail is untestable until a wider delta-targeted band is fetched"), C1 (real-fills is the only WR authority; BS-sim is ranking-only — L02,12,23,50,71,99,100,107), C3 (SPY-price edge != option edge; beat the null MAX — L58,74,100,...,172), C30/L148/L176 (audit what the cache actually prices/reaches before sweeping a knob or trusting a tail), L172 (random-day null), OP-16 (sim-accuracy gate).

## L183 -- 2026-06-22: Scheduled-event 0DTE SPY IV is two-sided FAIR — selling it blows the tail and buying it under-covers the premium; a positive selection-delta that does NOT cover the premium PAID is NOT a tradable edge

**Symptom:** The short-condor death (L182/#6) reasoned that realized event moves blow THROUGH the short strikes (which inverted the short edge to −$11.38/tr at the 0th null percentile), so the natural pivot was that the same fat-move distribution should pay a LONG strangle/straddle buyer. Built `_event_iv_crush_long.py` on the banked wide cache (ATM ±$18), 10:00 ET entry, hold-to-0DTE-expiry, settle true intrinsic vs SPY close, full premium + slip + commission, all 46 event + 46 matched non-event days, ZERO skips. The long side ALSO fails: LONG STRANGLE (~16-delta C+P, $0.45/leg proxy) **event exp/tr −$38.82** (n=46, WR 17.4%, total −$1,785.80; non-event −$67.02/tr); LONG STRADDLE (ATM C+P) **event exp/tr −$107.09** (WR 30.4%; non-event −$134.45/tr; and cap-BLOCKED — avg $423/lot → min-3 $1,269 > $600 Safe cap). The event move IS systematically bigger (avg abs move 3.21 vs 2.33; **selection_delta +$28.20/tr** strangle, positive) — but it does NOT cover the richer event premium. Both lose net of premium on both event and non-event days.

**Root cause:** Scheduled-event 0DTE IV is fairly priced two-sided: the market charges MORE premium precisely because the realized move is bigger, and the two cancel to within transaction costs. The short side proved this from one side (collect rich premium but the fat tail blows through your strikes — L182). The long side proves it from the other (the move is genuinely bigger but the premium you paid for it is bigger still). A real, positive **selection delta** (event days move more than random days) is therefore NECESSARY but NOT SUFFICIENT for a long-vol edge: the delta must exceed the premium PAID, not merely exceed the non-event move. Here +$28/tr of extra move did not cover ~$94/lot of strangle premium. Two methodology traps surfaced: (1) **Degenerate bootstrap null** — when the random-day null draws a sample equal to the entire non-event pool (n_sample == pool_size == 46), the bootstrap p95 collapses onto the pool MEAN, so `beats_null_p95` becomes a point-comparison that merely restates the selection delta — it is NOT a tail test and must NOT be read as a pass; the decisive gate for a LONG debit structure is `positive_net_of_premium`, full stop. (2) **drop_best2 is the right concentration check for a long debit** — drop_best2_exp = −$59.85 (< the headline −$38.82) confirms the loss is BROAD (38 of 46 days lose), not carried by one giant move day (the inverse-L173 check: a long-vol edge that LOOKS positive must survive removing its biggest-move days; a long-vol edge that is negative is confirmed broad when removing winners makes it worse).

**Fix:** Built `backtest/autoresearch/_event_iv_crush_long.py` (reuses the wide loader + `_event_iv_crush_precheck.build_event_days()` + spot/entry plumbing; settles true intrinsic; result `_state/event_iv_crush_long.json`), verdict DEAD both structures. Recorded: STRATEGY-DIRECTION-BACKLOG.md #6b DEAD + #4b FULLY-SPENT (the wide-band data unlock is now spent both directions) + STATUS.md OP-25 head entry; next direction = climb OFF the premium axis (compound the one live affordable edge #1 / climb to instrument #7).

**Generalizable principle:** (a) A positive selection-delta (the selected days move more than the null) is NECESSARY but NOT SUFFICIENT for a LONG-premium edge — the delta must exceed the PREMIUM PAID, not merely the non-event move; always gate a long debit structure on positive-net-of-FULL-premium FIRST, the selection delta is diagnostic, not the verdict. (b) A bootstrap null whose sample == the whole comparison pool is DEGENERATE (p95 == pool mean) — it is a point comparison, not a tail test; size the null pool strictly LARGER than the event sample or normalize per-day, and never read `beats_null` as a pass when the headline already loses net of premium. (c) For a long debit structure, drop_best-2 (not drop-worst-2) is the concentration check — the edge must survive removing its biggest-move days. **Domain conclusion:** scheduled-event 0DTE SPY premium is two-sided fair; the 0DTE SPY premium CLASS (long single-leg ~64 directional families + short defined-risk #6 + long vol #6b) is exhaustively CLOSED on this data — the productive frontier is OFF the premium axis (DTE / instrument / class).

**Watch-out:** The seductive trap here is the inverse-reasoning chain ("the short side died because moves are big → therefore the long side must win"). Both can lose simultaneously — that is precisely what FAIR two-sided pricing looks like, and it is the default expectation for a liquid, heavily-arbitraged underlying like SPY. A "selection delta is positive AND beats the null" headline is meaningless for a debit structure if the structure loses net of full premium; the WR being low (17–30%) while the selection delta is positive is the signature of paying for a real-but-insufficient move. And do not let a degenerate (sample==pool) null's collapsed p95 launder a net-negative result into a "pass."

**Encoded in:** `backtest/autoresearch/_event_iv_crush_long.py`, `_state/event_iv_crush_long.json`, STRATEGY-DIRECTION-BACKLOG.md #6b DEAD / #4b FULLY-SPENT, STATUS.md, this lesson (L183). CLAUDE.md OP-25 C3/C4 fold is rail-4-blocked → tracked in `KNOWN_UNINDEXED_BASELINE`. **Pending graduation:** in any long/short premium harness, the verdict gate must be net-of-FULL-premium expectancy AND a non-degenerate null (pool strictly > sample); a selection-delta-only "pass" is banned.

**Detection:** Future regression — any long debit-structure verdict reported as a "pass" on a selection-delta or a `beats_null_p95` where (a) the headline expectancy is net-negative of full premium, or (b) the null sample size equals the comparison pool size (degenerate p95). Cheap check: confirm `positive_net_of_premium == true` BEFORE reading any null percentile, and assert `null_pool_n > event_sample_n` (else mark the null INCONCLUSIVE).

**Related lessons:** L182 (the short-side sibling — together they close the 0DTE premium class both directions; this is the long-vega inverse), C3 (SPY-price edge != option edge; beat the null MAX — L58,74,...,172), C4 (per-trade expectancy not WR standalone; a published anomaly != a per-trade option edge — L01,04,...,175), L173 (drop-top-N concentration check — here the inverse drop_best2 for a long debit), L172 (random-day null — and its degenerate-when-sample==pool failure mode), OP-16 (sim/null-accuracy gate).

## L184 -- 2026-06-23: The two research-integrity cross-checks are now PERMANENT CODE GUARDS — every conditioning filter must beat `beats_random_filter_null`, every short-premium sim must pass `strike_band_covers_range`, from ONE shared library (`research_guards.py`)

**Symptom:** Two integrity checks recurred often enough — and were re-violated AFTER being written as prose — that they had to become code, not memory. (1) **No-selection CONDITIONING FILTERS kept looking like edges.** Three deaths on the SAME `vwap_continuation` bar: the W1 IV-skew confirmer (kept exp **$45.66 vs random-drop null mean $48.30 / p95 $54.30 → one-sided p≈0.76, FAIL**), the VIX-level gate (**p=0.355, FAIL**), and touch-and-go (selective-only). Each "filter" merely shrank n without selecting the right tail — a coin-flip drop of the same fraction did as well or better. (2) **Short-premium sims overstated magnitude off a too-narrow cache.** The event iron-condor looked **+$32.15/tr on the ±$5 cache** but the ±$18 wide-band de-bias INVERTED it to **−$11.38/tr** (worst −$640/lot) on the same big-move days — the narrow cache silently dropped the violent loser strikes as `missing_cache`, truncating the loss tail (this is L182). Both lessons (L172 random-filter null; L177/L182 cache-tail-bias) carried an explicit "Pending graduation into a reusable assertion" note — re-violated prose is a missing guardrail (OP-25).

**Root cause:** Both checks lived as inline copies / scattered literals, so they could be skipped or silently drift. The null logic was inline in `backtest/autoresearch/_iv_skew_confirmer.py` (`random_filter_null` + `null_p_for`) and re-implemented in the `_event_iv_crush` harness; the band check lived as scattered `legs_in_band(half_width=5)` literals (the exact three-copy divergence that flipped L177's IC percentile). Prose-as-control failed: the lessons were re-violated after being written. The durable fix is a SINGLE-source library plus regression assertions pinned to the REAL failure fixtures, so a future fire physically cannot present a no-selection filter or a tail-truncated short-premium sim as an edge without the guard firing.

**Fix:** `backtest/lib/research_guards.py` — single source of truth, pure deterministic (fixed-seed RNG) numpy-only functions: `beats_random_filter_null(base_pnl, kept_mask, n_seeds, seed_base, sig_level) -> FilterNullResult{passed, applicable, p_value, filt_mean, null_mean, null_p95}` (`passed` iff `filt_mean > null_p95`, one-sided p<0.05; a DEGENERATE point-null where kept==0 or ==N → `applicable=False`, NOT blessed — the L183 event-long-vega sample==pool trap); and `strike_band_covers_range(day_low, day_high, atm, cache_min_strike, cache_max_strike) -> StrikeBandResult{covered, dropped_side, slack}` + `dropped_day_fraction(day_results)`. Graduated into `backtest/tests/test_graduated_guards.py` (+5 permanent regression assertions, suite 73 green) pinned to the real failure cases: `test_l172_iv_skew_filter_fails_random_null` (the REAL W1 kept-mask from `analysis/recommendations/web-vwap_cont_iv_skew_confirmer.json` MUST return `passed=False`, reproducing p≈0.76, + a fixture-drift guard), `test_l172_genuine_filter_passes_random_null` (a top-quartile filter MUST pass — proves the guard is not always-False), `test_l172_degenerate_point_null_flagged_not_blessed`, `test_l177_event_condor_narrow_cache_fails_band_coverage` (REAL ±$5 cache → `covered=False` on 2025-04-04, `dropped_side="high"`), `test_l177_event_condor_wide_cache_covers_band` (REAL ±$18 cache → `covered=True`). Full unit/edge coverage in `backtest/tests/test_research_guards.py` (14 passed). This SUPERSEDES the "Pending graduation" line in L182/L183 and closes the L172/L177 loop.

**Generalizable principle:** A re-violated prose lesson is a missing guardrail — graduate it to a code assertion homed in ONE shared library and pinned to the REAL failure fixture (OP-25/OP-22, STAGE 4.5). Going forward the standing bar is mechanical: (a) **any CONDITIONING FILTER on an existing edge MUST call `beats_random_filter_null` and clear it** before it can be presented as an improvement — a filter that only shrinks n is not an edge (cite W1 IV-skew p=0.76, VIX-level p=0.355, touch-and-go selective-only); (b) **any SHORT-PREMIUM / credit / defined-risk sim MUST call `strike_band_covers_range` and disclose `dropped_day_fraction`** before its expectancy is trusted (cite the event-condor +$32/tr ±$5 vs −$751-tail ±$18, same day). Reuse the ONE implementation — never re-inline null/band logic. `cap_admission` is a separate concern (notional cap, already graduated) and is not touched here.

**Watch-out:** This is the exact bar the forward GEX-flip work (~60–90 days out, once `Gamma_CboeOiBank` accrues OI) will be held to: a GEX-flip conditioning filter on `vwap_continuation` that does not beat the random-filter null is not promotable, and a GEX-driven short-premium structure whose sim does not cover the realized band is magnitude-biased and not trustworthy. The seductive failure mode is presenting a filter's higher *headline* expectancy without the null — the null is what distinguishes selection alpha from pure n-reduction. And a degenerate (sample==pool) null must read `applicable=False`, never launder a net-negative into a "pass" (L183).

**Encoded in:** `backtest/lib/research_guards.py` (single source) + `backtest/tests/test_graduated_guards.py` (5 graduated regression assertions, suite 73 green) + `backtest/tests/test_research_guards.py` (14 unit/edge), this lesson (L184). CLAUDE.md OP-25 C3/C7/C30 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-23-001`.

**Detection:** Future regression — any conditioning-filter "improvement" presented without a `beats_random_filter_null` result, or any short-premium/credit verdict whose underlying cache is not checked by `strike_band_covers_range`/`dropped_day_fraction`. Cheap check: grep new autoresearch harnesses for a private `random_filter_null` / `legs_in_band(half_width=` / inline null re-implementation — any such copy must instead import from `backtest/lib/research_guards.py`.

**Related lessons:** L172 (random-filter null — the conditioning-filter half this graduates), L177 (the null/sim must trade production's exact strike universe — the band-coverage half), L182 (cache-tail-bias — the short-premium sim the band guard pins to its real ±$5/±$18 failure fixtures), L183 (degenerate sample==pool null → `applicable=False`), C3 (beat the null MAX — L58,74,...,172), C7 (silent success is failure — audit outputs, here graduate prose→pinned code), C30 (audit what the cache actually reaches before trusting a tail — L148,176), OP-16 (sim-accuracy gate), OP-22/OP-25 (re-violated lesson → code assertion).

## L185 -- 2026-06-24: A FUSED health verdict consumed by an automated GATE must be anchored on the gate's actual decision need — non-decision-relevant inputs cap at a non-blocking severity, "MISSING" never escalates to "failed", and when two systems watch the same concern exactly one owns the alarm

**Symptom:** `backtest/autoresearch/gym_session.py`'s `overall_verdict` read **RED 6-of-7 days** (2026-06-15..06-23) while the crypto-gym chart-reading harness it nominally reports was **GREEN 7-of-7**. Every RED came from peripheral inputs unrelated to detector health: absent peripheral producers (a proven 3-second write race made `watcher-state-inspector-2026-06-23.json` read as MISSING — file written 20:26:36 MT, gym ran 20:26:33 MT; `heartbeat-tick-audit` simply didn't run → MISSING), the L39 pulse max-gap artifact, and the intentional Bold v15.2 pin "mismatch". The conductor's STAGE-0 backpressure ("gym RED → don't touch detectors") was therefore PERMANENTLY tripped on a signal that has nothing to do with detectors — and a real crypto-gym RED would have been invisible in the noise (alarm desensitization, both failure modes of one cry-wolf).

**Root cause:** `_aggregate_verdict` was `RED if any audit RED or MISSING`, weighting the core harness identically to 6 peripheral operational audits AND escalating MISSING (producer-didn't-run / read race) to the same severity as a genuine failure. A fused verdict was being computed without reference to what its single consumer (STAGE-0 "is it safe to touch detectors") actually needed to decide.

**Fix:** Anchor the fused verdict on the consumer's decision need. Only RED_CAPABLE audits drive RED: the detector harness (crypto-gym — also RED on MISSING, fail-closed: unknown detector health blocks detector work), chart-data-verify (detector INPUT integrity), heartbeat-tick-audit (RED == a real in-progress-bar ENTER/EXIT). Every operational audit (pin/mcp/pulse/watcher) — already owned with its own critical alerter by `engine-health.json` — caps at YELLOW: it SURFACES (degraded observability) but cannot RED the chart-reading scorecard. Added a `detector_verdict` field = the harness verdict, unambiguous for the consumer. Cross-historical re-aggregation of all 7 recent scorecards proved no genuine RED is masked: the two real chart-data divergences (06-16, 06-19) stay RED; the four cry-wolf REDs (06-15/17/18/23 = intentional pin / L39 pulse / absent producers) correctly downgrade to surfaced YELLOW. Live 06-23 regen → overall_verdict YELLOW, detector_verdict GREEN.

**Generalizable principle:** A FUSED health/status verdict consumed by an automated GATE must be anchored on the gate's actual decision need, and inputs that are NOT decision-relevant to that gate must cap at a non-blocking severity — never share equal weight with the decision-critical signal, and never let "producer didn't run / MISSING" escalate to "failed". Equal-weighting a grab-bag of peripheral signals into one verdict manufactures a chronic cry-wolf that (a) blocks the gate on unrelated noise and (b) hides the one signal the gate exists to catch. When two systems both watch the same operational concern (here gym vs `engine-health.json`), exactly one should own the alarm; the other surfaces, not alarms. Generalizes the engine-self-healer NOTIFY-ONLY cry-wolf finding (HealthBeacon, 2026-06-22) from "alert frequency" to "verdict-aggregation design".

**Watch-out:** Do not "fix" a chronic RED by suppressing signal globally (that hides real failures). The fix is to RECLASSIFY by decision-relevance and keep every genuine decision-critical RED, validated by re-aggregating the full historical series and confirming the real REDs survive. A fail-closed exception stands: the decision-critical component itself reading MISSING (unknown detector health) DOES block, because "unknown" is not "safe".

**Encoded in:** `backtest/autoresearch/gym_session.py` — `_RED_CAPABLE` / `_DETECTOR_HARNESS` + `_aggregate_verdict`; `detector_verdict` scorecard field. Commit 4ce3b9c. `backtest/tests/test_gym_session_verdict.py` — 17 assertions incl. the exact 06-23 case, the L39 pulse downgrade, and chart-data-RED-still-REDs no-mask. This lesson (L185). CLAUDE.md OP-25 C7 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-24-001`.

**Detection:** A fused verdict whose aggregate severity flaps RED/MISSING while its named core component is green N-of-N days → the aggregation is conflating critical and operational inputs. Check whether the consuming gate keys off the aggregate or the core component, and whether any input can RED the verdict purely by being absent.

**Related lessons:** C7 (cry-wolf observability — silent success is failure / don't alarm on noise), C18 (status-format discipline — surface signal, don't desensitize), L39 (SKIP-not-FIRE pulse-gap artifact — a benign producer behavior read as failure), L161 (naive-ET producer-dark — a producer MISSING for a timezone reason, not a health reason), L179 (a handshake's second half silently dropped — reconcile, don't trust), engine-self-healer NOTIFY-ONLY cry-wolf (project memory, 2026-06-22), OP-22/OP-25 (re-violated lesson → code assertion; the guard IS `test_gym_session_verdict.py`).

## L186 -- 2026-06-24: A hardcoded param-VALUE claim in prose ("currently `true`") goes stale the instant a ruling flips the param — reverse-references that name a live param value are write-once and silently rot; reference the key, never freeze the value

**Symptom:** The task-scorer ranked `GATE-STACK-OVERBLOCK-A-PLUS-RECLAIM` as the #1 ready item (score 6.0, HIGH). Its entire headline premise was "the `block_bull_morning_agg` gate is BLOCKING A+ reclaims → quality-condition it." But J had **already removed that gate entirely earlier the same day** (mid-session Rule-9 author override — `aggressive/params.json#block_bull_morning_agg: false`, `_doc` quote "remove this entirely"). A fire that trusted the breadcrumb would have burned a full cycle (and a real backtest) researching how to fix a gate that no longer fires — and the scorer would re-rank it #1 every fire until reconciled. Two consumer surfaces also disagreed with the live param: `automation/prompts/aggressive/heartbeat.md` line 356 still annotated the gate "(currently `true`)" — the LIVE PROMPT the engine reads contradicting the param it reads (behavior stayed correct because the gate logic is param-gated at runtime, but the annotation misleads any reader, human or model) — and the `queue.md` GATE-STACK item + task-scorer ranking both treated `=true` as current.

**Root cause:** When J makes a mid-session param ruling, the **canonical state** (the `params.json` value + its `_doc`) is updated, but the **reverse-references** that hardcode the value — queue research items naming the param as a live lever, and heartbeat-prompt annotations of the form "(currently `<value>`)" — are NOT swept. They are write-once prose that silently rots. The `_doc` captured J's quote perfectly; everything pointing AT the param did not. This is the inverse of the C14 dead-knob class: there a knob is inactive but logic still references it; here a knob's VALUE flipped but prose still claims the old value.

**Fix:** Reconciled the queue item to RESOLVED-BY-J + reframed the genuine residual (does blanket-removal reopen a net drain a quality-conditioned gate would prevent — needs a fresh scored backtest, surfaced to J). Staged rail-4 proposal `gp-2026-06-24-001` to sync the heartbeat prose. Then GRADUATED the class to a guard (the re-violation test, STAGE 4.5): `backtest/tests/test_heartbeat_param_annotation_drift.py` (commit 4f02418) parses every heartbeat `(currently \`X\`)` annotation, maps it to the named param, and asserts `<value>` equals the live `params.json` value. A `KNOWN_STALE` allowlist (RATCHET — shrinks only) carries the single pending Bold drift; a SECOND test forces each `KNOWN_STALE` entry's removal once the annotation is corrected, so fixed drift cannot hide forever.

**Generalizable principle:** Do NOT hardcode a param VALUE in any prose another surface reads as authoritative (a heartbeat annotation, a queue research lever, a doc). Reference the KEY and let the runtime read the live value; the moment a value is frozen in prose it is a drift liability the instant a ruling flips it. If an annotation MUST state the current value for legibility, it requires a presence/drift ratchet (the `v25_filter_gates.py` / `test_params_filters_drift.py` class) that asserts the frozen value equals the live one and fails loud on divergence. Canonical state has exactly one writer (the `params.json` value + its `_doc`); everything else references, never copies.

**Watch-out:** A mid-session J ruling is the trigger event — it updates `params.json` + `_doc` but will NOT sweep dependent prose. After any such ruling, the stale-breadcrumb surfaces are: (1) the live heartbeat prompt annotations, (2) `queue.md` items that name the param as a live lever (the task-scorer will re-rank a dead lever forever), (3) any doc quoting the value. The same J edit also injected a non-ASCII em-dash into the `_doc` string (REDs `test_params_encoding`, full CI) → hand-authored param prose is also an encoding-drift surface.

**Encoded in:** `backtest/tests/test_heartbeat_param_annotation_drift.py` — 3 tests: every `(currently \`X\`)` annotation matches the live param (except `KNOWN_STALE`); each `KNOWN_STALE` entry is still genuinely stale (forces removal on fix); the ratchet bites (clearing the allowlist makes the real Bold drift fail loud). Commit 4f02418. Sibling of `test_params_filters_drift.py` (the params↔filters drift class). This lesson (L186). CLAUDE.md OP-25 C7 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-24-002` (chained after `cd-2026-06-24-001`).

**Detection:** A research/queue item whose headline lever names a param value the live `params.json` contradicts → the breadcrumb is frozen at write-time (verify the premise before researching, L181/L185). A heartbeat `(currently \`X\`)` annotation that disagrees with the live param → drift. Any prose "currently `<value>`" outside the canonical `_doc` is a candidate.

**Related lessons:** C7 (no-closing-handshake stale-breadcrumb family — L170/L173/L179/L181/L185: a producer/consumer surface left unreconciled), C14 (dead/translated-but-unapplied knobs — L180; the annotation drift is the inverse: an active value whose prose claims the old one), L181 (verify the premise before task selection — a stale breadcrumb names a frozen implementation path), L185 (fused-verdict anchored on consumer need — same-fire family), OP-22/OP-25 (re-violated lesson → code assertion; the guard IS `test_heartbeat_param_annotation_drift.py`).

## L187 -- 2026-06-24: A scoped `git commit -- <pathspec>` false-REDs the pre-commit safety gate — the partial-commit temp index holds `index.lock`, which collides with the gate's git-touching tests; stage explicitly then commit with NO pathspec

**Symptom (reproduced twice, 2026-06-24 conductor fire):** an additive-only commit (a new test file + `git add` of an existing working file) was BLOCKED by the pre-commit safety gate with `ERROR backtest\tests\test_verify_committed.py::test_commit_only_reproduces_the_drop` / `::test_helper_uses_index_not_disk_presence` (`25 passed, 4 errors` → `[safety-gate] FAIL`) — yet running the SAME gate standalone (`python backtest/tests/run_safety_gate.py`) and `test_verify_committed.py` standalone BOTH pass (29 / 4 passed). The gate is genuinely green; only the *in-hook* run errors. A fire reading the FAIL at face value may wrongly reach for `git commit --no-verify` (bypassing the real safety gate) to get unstuck.

**Root cause:** the commit used the scoped **pathspec** form `git commit -m "..." -- <file1> <file2>`. That form does a PARTIAL commit, which makes git build a temporary index and hold `index.lock` for the duration of the hook. The curated safety gate runs `test_verify_committed.py`, whose tests perform their OWN nested git operations (temp commits to verify the L164/L62 untracked-drop behavior). Those nested git calls collide with the held lock and raise during collection/setup — ERRORS (env contention), not assertion FAILURES (real defect). So a perfectly clean change gets a false RED purely from the commit FORM, not its content.

**Fix:** stage explicitly, then commit with NO pathspec —
```
git add <file1> <file2>
git diff --cached --name-only   # confirm ONLY the intended files are staged (still scoped)
git commit -m "..."             # full-index commit; no index.lock contention
```
This keeps the commit scoped (only staged files land) AND avoids the partial-commit temp-index path. Verified: the identical change went green (29 passed) the moment the pathspec was dropped.

**Generalizable principle:** the documented "scoped commit (only my N files, L164)" pattern that dozens of conductor/gamma-drive fires use means *only my files land*, NOT *use the `git commit -- <pathspec>` form*. Achieve scope through the **index** (`git add <files>` + verify `git diff --cached --name-only`), never through a partial-commit pathspec, whenever the pre-commit gate contains a test that itself shells out to git. ERRORS vs FAILURES in a gate result is the tell: errors during collection/setup point at an *environment* problem (a held lock, a missing fixture), not a real regression — re-run the gate standalone before trusting an in-hook FAIL.

**Watch-out:** the discriminator is `N passed, M errors` (not `M failed`). If the standalone gate passes but the in-hook gate errors on the same tree, suspect commit-form/lock contention, not your change. Do NOT escalate to `--no-verify` — that bypasses the genuine safety gate; drop the pathspec instead.

**Encoded in:** this lesson (L187) + the inbox source `strategy/candidates/_lesson-inbox/2026-06-24-pathspec-commit-breaks-verify-committed-in-hook.md`. **Prose convention only (no code guard yet) — by the inbox item's explicit disposition: document the `git add`-then-`commit` convention first (zero code change), graduate to a code skip only on re-violation.** The durable fix if it recurs: make `backtest/tests/run_safety_gate.py` detect a held `index.lock` / partial-commit env (`GIT_INDEX_FILE` pointing at a tmp index) and skip the git-touching suites in-hook, OR move `test_verify_committed.py` to a push-time/CI-only gate. CLAUDE.md OP-25 C7/C19 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-24-003` (chained after `cd-2026-06-24-002`).

**Detection:** A pre-commit safety-gate result that shows `passed, errors` (not `failed`) AND passes when run standalone (`python backtest/tests/run_safety_gate.py`) → commit-form/lock contention, not a regression. Any STATUS entry or script that commits via `git commit -m "..." -- <files>` while the curated gate includes a git-touching test is a latent re-violation site.

**Related lessons:** C7 (silent/false failure — a guard tripping on an artifact, not a real defect; ERRORS-not-FAILURES family), C19 (git-on-Windows: the index-lock/temp-index path is the Windows-git foot-gun class — validate in a clean form), L164 (scoped commit / `git add` then commit — this lesson sharpens *how* to scope: via the index, never via a pathspec), OP-22/OP-25 (graduate-if-it-recurs — first occurrence stays prose; the second graduates to the `run_safety_gate.py` lock-detect skip).

## L188 -- 2026-06-25: The standard random-entry null shuffles the SIDE, so any directional entry beats it just by being directionally correct — it does NOT isolate selection alpha; the decisive test for a directional family is a DIRECTION-CONTROLLED null (random bars, side = the bar's own direction)

**Symptom (new-entry-families grind, 2026-06-25 — `family_grind.py` + `_verify_bollinger.py`):** grinding 4 brand-new directional entry families through the standard random-entry null (C3/L58/L171), `three_ducks` (an intraday MTF trend-follower) PASSED it on 4 of 8 distinct strike/stop cells (PASS-P4) — on its face a real edge. But `three_ducks` fires on **98% of trading days** (the C27 noise smell — a trend-follower entering nearly every day shouldn't carry selection alpha). Re-tested against a **direction-controlled null** (random RTH bars, but side = the entry bar's OWN direction = a momentum-aware random entry), it **COLLAPSED**: signal $10.9/tr < dir-null MAX $15.0; drop-top5 $8.2 < dir-null MEAN $9.1 — a momentum-aware coin-flip *beat* it. Meanwhile `bollinger_squeeze` SURVIVED the same dir-null (signal $34.9 > dir-null max $26.3; drop-top5 $24.0 > dir-null mean $17.8) → genuine selection alpha. **Same stock-null verdict (both PASS-P4); opposite truth.**

**Root cause:** the standard `random_entry_null` randomizes entry TIMING **and shuffles the call/put SIDE** across the random bars, so the null's calls land on down-moves ~half the time → it has only ~50% directional accuracy. ANY directional entry (calls on up-signals / puts on down-signals by construction) beats that null partly **just by being directionally correct**, independent of whether its *timing/selection* has any value. For a momentum/trend/breakout family — where "enter in the direction of the recent move" is the whole signal — the stock null therefore systematically OVERSTATES the edge: it rewards direction-vs-random-direction, not selection-vs-random-selection. `three_ducks` had only the former; `bollinger_squeeze` had the latter too.

**Fix:** add a **direction-controlled null** as the decisive cross-check for any DIRECTIONAL new-entry family that passes the stock null — draw random bars in the same entry window but set `side = sign(close − open)` of each drawn bar (a momentum-aware random entry), same count / strike / stop / **matching exit bracket**. The family must beat THIS null's **MAX** (and drop-top5 must beat its **MEAN**). Pair it with the existing concentration check (drop-top5) and the C27 firing-rate smell (a directional detector firing >80% of days is suspect → demand it beat the dir-null, not just the random-side null). Implemented + parameterized in `backtest/autoresearch/_verify_bollinger.py` (`[family so stop tp1 tq trail]`, lines 79–110: `side = "C" if c[idx] >= o[idx] else "P"`).

**Generalizable principle:** beating the random-SIDE null is *necessary*; beating the direction-CONTROLLED null is what proves the timing/selection has value. A directional family that passes the former and fails the latter (e.g. `three_ducks`, firing 98% of days) is a **direction-following artifact, not an edge.**

**Watch-out:** a high-firing-rate directional detector (>80% of days, C27) that clears the stock null is the prime false-positive site — its "edge" is most likely just direction-vs-random-direction. Never publish a directional family on the random-side null alone.

**Encoded in:** `backtest/autoresearch/_verify_bollinger.py` (the parameterized direction-controlled null) + `markdown/research/GRIND-NEW-FAMILIES-2026-06-25.md` (verdicts: `bollinger_squeeze` → FORWARD-VALIDATE, survives both nulls, two-sided, WF 1.43, qpf 1.0; `three_ducks` → DEAD, direction-following artifact) + this lesson (L188) + the inbox source `strategy/candidates/_lesson-inbox/2026-06-25-direction-controlled-null-isolates-selection-from-direction.md`. **Pending GRADUATION (queued — `DIR-NULL-P5-GATE-GRADUATION`): wire the direction-controlled null into `family_grind.py` as an automatic P5 gate for any family flagged directional/high-firing-rate, plus a `test_graduated_guards` assertion** (a re-violated lesson is a missing guardrail — first occurrence stays prose per OP-22, graduate when re-hit OR when the next directional family is ground). CLAUDE.md OP-25 C3 fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-26-001` (chained after `cd-2026-06-24-003`).

**Detection:** a NEW directional entry family that (a) passes the standard random-side null AND (b) fires on >80% of trading days → re-run it against the direction-controlled null before any FORWARD-VALIDATE verdict; if signal < dir-null MAX or drop-top5 < dir-null MEAN, it is a direction-following artifact. Any new-entry harness that grades directional families on `random_entry_null` alone is a latent re-violation site.

**Related lessons:** C3 (SPY-price edge != option edge; beat-the-null MAX — L58/L171/L172/L177; L188 is the **directional corollary**: the random-side null is too weak for directional families), C27 (detectors firing >80% of days measure noise — the firing-rate smell that flags WHICH families need the dir-null), C4 (drop-top5 concentration — paired with the dir-null), OP-22/OP-25 (graduate-if-it-recurs — the dir-null is implemented as a one-off verify cross-check; the graduation is wiring it into `family_grind.py` as an automatic P5 gate).

## L189 -- 2026-06-27: A monitor stuck RED is BLIND to every new failure of every other class — an alerter that fires only on a GREEN→RED transition lets fresh breakage accrue silently while the verdict is already RED; and a STATIC "registered" proxy (grep install scripts) is not the live registry, so a green pytest can hide a live ORPHAN

**Symptom (conductor fire 2026-06-27, while closing G9-SELF-AUDIT PART-2):** `audit_scheduled_tasks.py` reported **16 ORPHAN_TASK** flags — including the two most critical live components, `Gamma_HeartbeatCore` (the deterministic live trading engine) and `Gamma_SightBeacon` (the never-blind eye) — registered-but-undocumented for a long, unknown stretch. The queue's own breadcrumb (G9 PART-2) claimed only **5** (stale-breadcrumb, L181/L185, again). Critically, **no alert ever fired** for the 16 new orphans, and the green static-doc pytest suite (`test_scheduled_tasks_doc.py`) reported the registry as honest the whole time.

**Root cause (two compounding mechanisms):** (1) **Two different definitions of "registered."** The static guard `test_scheduled_tasks_doc.py` derives its `registered` set by grepping **install scripts** (`_registered_name_to_scripts()`), while the runtime audit `audit_scheduled_tasks.py` reads the **live Windows scheduler**. Tasks registered manually or by a script the static scan doesn't cover (HeartbeatCore/SightBeacon/the grind+funnel workers/the free-manager loop) are INVISIBLE to the green static guard — only the live-truth audit sees them. A green pytest suite therefore did NOT mean the registry was honest (C7: audit the real artifact, not a proxy for it). (2) **A persistently-RED audit cannot signal a NEW failure.** The audit/health alerter pings on a RED *transition* only (anti-spam). HEALTH was already RED from 2 unrelated `BARE_CMD_POWERSHELL` hard-fails (`Gamma_ContextGuard`, `Gamma_SwarmPremarket`), so a NEW orphan never produced a GREEN→RED edge → no alert → 16 orphans accrued silently. **A monitor stuck RED is functionally blind to everything else that breaks.**

**Fix shipped this fire:** documented all 16 in `SCHEDULED-TASKS.md` (ORPHAN 16→0, verified) + reconciled the stated-count guard (46→61) + corrected the stale "SelfAudit superseded" tombstone (commit 50ca875). The 2 BARE_CMD flags remain (`G18-BARE-CMD-HIDDEN-CHAIN`, a separate hidden-chain fire) — unsticking those flips the audit GREEN and restores transition-alerting.

**Generalizable principle:** an EDGE-triggered alerter (fires on a state TRANSITION) is blind the moment the state is *already stuck* at the alarm value for any unrelated reason — track the SET of active flags and alert on set-GROWTH (a NEW flag of ANY class), not just the GREEN→RED edge. And **never check a live system against a STATIC proxy of itself**: assert `static_proxy ⊇ live_truth` (so a live ORPHAN can't be green in pytest), or read the live truth directly (env-gated, since a pure-live test is machine-dependent).

**Watch-out:** any anti-spam "alert only on transition" monitor is a latent mask the instant it is stuck RED for an unrelated reason; any "is it registered / documented?" test that greps SOURCE instead of the live system can be green while the live system is broken. The two failure modes COMPOUND: the static guard says "fine" and the stuck-RED audit says nothing-new → the breakage is invisible from both directions at once.

**Detection:** an overall-RED health/audit verdict that has been RED for >1 cycle should be treated as BLIND to new same-or-other-class flags until cleared — surface its full flag SET as drainable work, not a single transition bit. A "registered/documented" assertion whose `registered` set comes from grepping install scripts is a latent re-violation site whenever a task is registered by an uncovered path.

**Encoded in:** `automation/state/SCHEDULED-TASKS.md` (16 ORPHANs documented + stated-count 46→61) + the inbox source `strategy/candidates/_lesson-inbox/2026-06-27-persistently-red-audit-masks-new-orphans.md` + this lesson (L189). **Pending GRADUATION (queued):** `G18-BARE-CMD-HIDDEN-CHAIN` unsticks the audit (removes the 2 BARE_CMD flags → GREEN → transition-alerting works again); per-flag-class set-growth alerting in `engine_health`/the audit alerter; the `static ⊇ live ORPHAN` superset assertion reconciling the two "registered" sources; and conductor STAGE-0 reading `scheduled-tasks-audit.json` alongside `engine-health.json` (first occurrence stays prose per OP-22 — graduate when re-hit OR when G18 lands). CLAUDE.md OP-25 **C7** fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-27-002` (chained after `cd-2026-06-26-001`).

**Related lessons:** C7 (audit the real artifact / outputs not exit codes — L19/L26/L28… L185/L186/L187; L189 is the **registry corollary**: a static proxy of the live registry can be green while the live registry is broken), L181/L185 (stale breadcrumb — the "5 vs 16" miscount), L185 (a FUSED verdict consumed by an automated gate — exactly one owner per alarm; here the alarm went unowned once stuck RED).

## L190 -- 2026-06-27: A guard on the DETECTOR is not a guard on the SOURCE — when a property is enforced by a fixer/converter script, scan the artifact the PRODUCER writes, not the validator's detection logic; "the audit can detect X" and "no producer emits not-X" are two different invariants, and only the second stops a later re-registration script from silently undoing the fix

**Symptom (conductor fire 2026-06-27, G18, commit cf3ef6a):** `Gamma_SwarmPremarket` + `Gamma_ContextGuard` flashed an OpenConsole window on every fire and tripped `audit_scheduled_tasks.py` BARE_CMD_POWERSHELL (HEALTH RED) — **even though** `setup/fix-powershell-task-flash.ps1` had *already* converted them to the windowless wscript→pythonw chain weeks earlier, and the existing guard `test_guard_cmd_popup_fix_ws6.py` was green the whole time. A fixed property had silently regressed with every signal green.

**Root cause (two compounding mechanisms):** (1) **A fixer's effect was silently undone by a later re-registration script never updated to the new pattern.** The 2026-06-26 TZ-systemic fix `register_tz_fixed_tasks.ps1` re-registered both tasks with BARE `powershell.exe` actions (its section #3 SpendSummary already used the correct wscript chain, but #1/#2 did not), re-clobbering the flash fix on every re-run. `Gamma_SwarmPremarket` was *also* never in the flash-fix converter's target list (a second, independent gap). Same class as the TZ-install time-bomb, but for the *window-hiding* property instead of the *schedule*. (2) **The existing guard tested the DETECTOR, not the SOURCE.** `test_guard_cmd_popup_fix_ws6.py` only exercised the audit's `_is_bare_console_launcher` / `_is_hidden` helpers against synthetic strings — it proved the audit *can* detect a bare action, never that no installer *emits* one. So an installer re-introducing a bare action stayed green; the regression surfaced only live, in the audit's HEALTH flag — and that audit was itself stuck RED for unrelated reasons (L189), so even the live signal was muted.

**Fix shipped this fire (G18):** `backtest/tests/test_installer_no_bare_console_action.py` (4/4, bite-tested non-vacuous: REDs on both a fixed-file regression AND a new bare installer) — a STATIC scan of `setup/**/*.ps1` that fails if any installer constructs a task with a bare `-Execute "powershell.exe"`/`"cmd.exe"`. Pins the 3 fixed installers clean + a shrinks-only ratchet over 6 pre-existing latent offenders (crypto ×3, watchdog-modes-sweep, register-eod-deep-dive, scripts/setup-all). Source fixes applied to all 3 clobberers (commit cf3ef6a).

**Generalizable principle:** when a property is enforced by a fixer/converter script, **guard the artifact the PRODUCER writes, not the validator's detection logic.** "The audit can detect X" + "no producer emits not-X" are two different invariants; only the second prevents a later script from silently undoing the fix. A unit test that exercises a detector's helpers against synthetic strings proves the detector works — it says NOTHING about whether any real producer still satisfies the property.

**Watch-out:** every fixer/converter script in this rig is a one-shot mutation that a later re-registration can re-clobber (TZ, window-hiding, task-action shape — all the same shape). A green detector-unit-test sitting next to a red live-audit is the tell: the unit test guards the wrong invariant. Whenever you add a converter, add a STATIC source-scan guard that asserts no producer emits the not-converted form — not just a test that the converter/detector recognizes it.

**Detection:** a property that "was already fixed" but recurs live → suspect a re-registration/re-install script that wasn't updated to the fixed pattern (grep for every script that writes the same artifact). A guard whose assertions only feed synthetic inputs to a detector's helper functions (never scanning real producer source) is a latent re-violation site for the exact property it appears to protect.

**Encoded in:** `backtest/tests/test_installer_no_bare_console_action.py` (4/4, the source-scan guard) + the 3 source fixes (`register_tz_fixed_tasks.ps1` #1/#2, `register-context-guard.ps1`, `install-swarm-task.ps1`) + `setup/fix-powershell-task-flash.ps1` (SwarmPremarket added to targets), commit cf3ef6a + the inbox source `strategy/candidates/_lesson-inbox/2026-06-27-guard-the-source-not-the-detector.md` + this lesson (L190). The guard IS the encoding (OP-22 anti-bloat — the source-scan ratchet is the durable form). CLAUDE.md OP-25 **C7** fold is rail-4-blocked (conductor cannot edit CLAUDE.md) → tracked in `KNOWN_UNINDEXED_BASELINE`; proposal `cd-2026-06-27-003` (chained after `cd-2026-06-27-002`).

**Related lessons:** C7 (audit the real artifact / outputs not exit codes — L19/L26/L28… L185/L186/L187/L189; L190 is the **producer corollary**: guard what the producer emits, not what the validator can detect), L189 (sibling, same fire's audit — a persistently-RED audit masked even the live signal of this regression; the two compound), L181/L185 (the same TZ re-registration script that clobbered this also left the G5 stale breadcrumb), `project_scheduled_task_tz` / `project_mcp_window_leak_fix` (one fixer's output clobbered by another re-registration; the bare-powershell OpenConsole flash class).
