# SWARM CONSULT: AUDIT -- Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engin

**Filed:** 2026-06-26T18:13:27 ET
**Mode:** `audit`
**Cost:** $0.0000
**Elapsed:** 34.9s
**Perspectives:** 1 / 3 succeeded

## Question

Audit Project Gamma (autonomous 0DTE SPY options trader + self-improvement engine) for what it is OBVIOUSLY missing or should already be doing AUTONOMOUSLY. List the top 6-8 concrete, ranked, actionable gaps Gamma should self-identify RIGHT NOW: better tools it isn't using, existing infrastructure not connected, next-order implications, and what the operator will point at NEXT. Be specific; avoid generic advice.

## Context (provided)

```
RECENT STATUS (top):
## [2026-06-26 ~11:50 ET] STAGED (ship after the close, rule 9) — direction-block re-audit: 5 stale-block UNBLOCKS + 4 dormant validated setups to ENABLE

> **Signal J wakes to (OP-25).** 15-agent audit re-validated EVERY direction-block on the CURRENT engine (real fills + managed exits). Splits J's "missing trades" 3 ways. Full evidence: workflow `audit-direction-blocks-revalidate` output. Applies as ONE reversible commit AFTER 15:55 ET (rule 9), autonomous under standing authorization (OP-22), reported for REVOKE. **PRE-SHIP CHECK owed:** confirm the 4 dormant setups are OFF by config, not a deliberate recency-drawdown HOLD (recency_check gate / license_monitor) — verify before flipping `enabled=true`.
>
> **UNBLOCK (5 — stale on the new engine, now block winners):**
> - `params.json` `midday_trendline_gate` true→false (Safe bear; removed cohort +$849/WR71%)
> - `params.json` `entry_bar_body_pct_min` 0.20→0.0 (Safe bear doji; amputates 5 fat-tail winners)
> - `aggressive/params.json` `require_bearish_fill_bar` true→false (Bold; +$917 winners suppressed — REVOKE-note, OOS n=5 thin, conf 6)
> - `aggressive/params.json` `block_conf_lvl_rec_afternoon` true→false (Bold; leaky gate, costs $779 shields $0)
> - **VIX_BULL_HARD_CAP 18→22** (Safe bull) — TWO synced edits: `params.json` `vix_entry_thresholds.bull_hard_cap` 18.0→22.0 AND `backtest/lib/filters.py:805` `VIX_BULL_HARD_CAP` 18.0→22.0 (hardcoded — drifts if separated) + `heartbeat.md` filter 9 "VIX<18"→"VIX<22". This is what blocked today's 9:50/11:15 calls.
>
> **ENABLE (4 dormant VALIDATED setups — the real missing volume):** flip `enabled=true` on `vwap_continuation` (side already `both`, both_dirs_positive=True), `vwap_reclaim_failed_break`, `vix_regime_dayside` (side already `both`), `gap_and_go` (set the latter two side→`both` per TARGET STATE).
>
> **KEEP (still block real losers — do NOT touch):** `filter_10_min_triggers_bull`=2 (unblock = −$26,572), `block_bull_1100_1200`, `VIX_BULL_LOW_THRESHOLD` (F8), `block_level_rejection`, `vix_bear_hard_cap`=23, OP-16 ribbon BULLISH_RECLAIM lock (re-tested: FAILS — drop-top5 −$1,573, 2/6 quarters). `block_elite_bull` = INCONCLUSIVE → needs a narrowed carveout, not a blind flip.
>
> **NEXT (deeper fix, validates after this ships):** the structure-veto / ribbon-lag trend-read fix (wire `crypto/lib/market_structure.classify_trend` to veto entries fighting confirmed price structure — stop shorting into uptrends). market_structure.py exists + gym-validated but was never wired into the live engine.

## [2026-06-26 ~11:39 ET] FIXED — the never-blind beacon was serving a STALE price (and an INVERTED ribbon) all morning; `sort=asc`+`limit` truncated the newest bars off

> **Signal J wakes to (OP-25).** The beacon `spy` read **731.86** at 11:32 ET while live SPY was **734.66** (~$2.80 stale); 731.86 also appeared at 07:34 ET — stuck, not lagging. The morning's own 09:45 "FIXED" entry (below) quotes "beacon spy=731.86 ribbon=BEAR" as proof the eye was *alive* — that very value was the stale read, and the BEAR was an inverted-ribbon artifact. The eye was never-blind but **never-fresh**.
>
> **Root cause:** `sight_beacon._fetch_alpaca_bars` requested `start={now−5d}&limit=300&sort=asc`. The 5-day window holds ~390 5m bars but `limit=300` caps the response — with **`sort=asc` the cap keeps the OLDEST 300 and truncates the newest off the tail** (`next_page_token` set, confirming dropped bars). So `bars[-1]` (= `spy` + `last_bar`) froze on a prior-session bar (`2026-06-25T17:45Z`, c=731.86) and the ribbon EMAs were computed over yesterday's window → stale price AND a backwards BEAR stack. EMAs "appeared to update" only because the `now−5d` floor slides each run, jittering the oldest-300 set while the tail stayed pinned. Reproduced directly: asc→`bars[-1]`=731.86 (yesterday); desc→`bars[0]`=735.34 (today, ~3 min old); live trade 735.62.
>
> **FIX (surgical, ribbon/EMA logic untouched):** fetch **`sort=desc`** (newest-first, so the `limit` cap drops the *old* tail) then `reversed()` back to oldest→newest so the ribbon still seeds correctly and `bars[-1]` is the NEWEST bar. Verified live: `spy` 731.86→**735.78** (within cents of the live trade), `last_bar` →**2026-06-26T15:35Z** (today), ribbon corrected **BEAR→BULL** (fast>pivot>slow, price above all). Beacon written + fleet shared-signal refreshed clean. Only the Alpaca path was affected (yfinance fallback returns ascending+untruncated); no other change.
>
> **Why it matters:** `build_shared_signal` falls back to the beacon's price/ribbon when the core ledger is stale/blind — a stale/inverted beacon corrupts the fleet signal exactly when the never-blind guarantee is supposed to save it.
>
> **Pending:** local commit + after-hours push (RTH push discipline).

## [2026-06-26 ~10:55 ET] FIXED — the armed engine could not place ANY option order (Alpaca rejects option brackets); simple-entry fallback shipped + proven live

> **Signal J wakes to (OP-25).** Checked "are we trading good today" → found the engine SEES + DECIDES correctly but placed **zero** orders. Bold fired a valid `BEARISH_REJECTION_RIDE_THE_RIBBON` put entry 5× (10:36–10:40, SPY $730P ×5 @ $0.96, bear 7/10, "passed scoring + all entry gates") — every one `PLACE_FAIL`.
>
> **Root cause:** `fleet_broker.place_bracket` submits `order_class=bracket` (entry+TP+stop), falls back to `oto` — **Alpaca rejects BOTH for options** (`code 42210000 "complex orders not supported for options trading"`, HTTP 422). The arm-gate dry-tested *sizing* but `dry=True` returns before the real `place_bracket`, so today was the **first time the armed engine actually tried to place a live option order** — and the placement mechanism is fundamentally incompatible with Alpaca options. Textbook "validated in sim, never placed live" (L47/L76/C11). NOT bold-specific — safe fails identically once it clears its entry gate.
>
> **FIX:** options can't use broker brackets → place a **simple limit entry** and let the tick-managed `exit_manager` own TP/stop (the architecture already built for exactly this; `GAMMA_CORE_MANAGES_EXITS=1`). Added `simple_fallback` param to `place_bracket` (gated: a simple entry has no broker stop, so it's placed ONLY when the caller manages exits — else stays the safe `PLACE_FAIL` no-op, never a naked long / C2). `heartbeat_core._execute` passes `simple_fallback=CORE_MANAGES_EXITS`.
>
> **PROVEN LIVE (not just sim):** placed a non-filling simple limit (buy $0.05 on a $0.95 option) on safe-2 through the fixed path → Alpaca **accepted** (`id=751b1d23…, status=pending_new, _simple_fallback=True`), cancelled clean, account stayed flat. 106/106 fleet tests green. Engine reloads per-tick (fresh process/min) → fix is live; on the next valid ENTER it places simple + the exit loop manages it (−50% cap + TP1 + runner + 15:50 time-stop + `Gamma_EodFlatten` backstop). Quality-lock + is-flat prevent over-trading.
>
> **Open follow-ups:** (1) the live exit-actuator market-sell path is now exercised for the first time on the first real fill — watch it. (2) `free_eval` veto lane `analyst` throws KeyError (1 of 2 free models down → veto is effectively single-model; non-blocking).

RECENT COMMITS:
667cb3d feat(engine): Wave 3 â€” dormant-setup dispatch layer (foundation, log-only, gated)
26832c0 feat(engine): SHIP structure-veto + 2 unblocks + popup fix â€” Wave 2, all guard-gated
667217a feat(engine): EOD 2026-06-26 â€” engine repairs + direction-block audit + structure-veto + trendline engine
56b7dfd feat: portable self-correction handoff skill (J-directed, drains skill-inbox)
ffdca68 docs(shadow-eval): Hermes ENSEMBLE-ELIGIBLE â€” 7/7 DT = 100% across 4 dates
c9ab472 ï»¿feat(shadow-eval): Hermes+Qwen challengers wired; CLAUDE-INDEX-FOLD-BATCH applied
b4f796d docs: encode L187 (scoped pathspec commit false-REDs the safety gate)
b9d2f9f share: self-correction skill package for work Claude
d90d9da test: track ribbon_cli.py + pin the live TV-hang fallback CLI contract
174a6d8 feat(research): cap-admission guard + research-integrity guards + CBOE OI banker
5b6e30c feat(github-audit): scheduled task fires every 2 days, Discord ping on findings
7bb7c17 docs: encode L186 (hardcoded param-value in prose goes stale on ruling) + tighten OP-25 ratchet baseline

```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 9.7s, cost $0.0000_

**1. Consensus points**  
*(Only Perspective 1 succeeded; its observations are taken as the baseline consensus.)*  
- The four dormant setups (`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`, `gap_and_go`) are being flipped to `enabled=true` without confirming that the `recency_check` gate or `license_monitor` is actually permitting them.  
- If either gate is still suppressing the setups, the config change will be a no‑op now but could trigger a synchronized burst of entries once the gate releases, overwhelming the exit manager.  
- The beacon fix only repaired the Alpaca path; the yfinance fallback still returns ascending, untruncated bars, so a feed fallback will again produce a stale price and inverted ribbon, corrupting the shared signal.  
- The OP‑22 “standing authorization” for the reversible commit lacks an automated rollback trigger (circuit‑breaker) that would auto‑revert the `enabled` flags on adverse outcomes.  
- Adding four new entry streams increases strategy crowding, slippage, and market‑impact risk, especially for low‑volume 0DTE SPY options.  
- The exit manager is sized for the historical mix; the extra streams risk exceeding its concurrency limits and dropping TP/stop updates.  
- A sudden rise in active setups can push the `license_monitor` past its internal threshold, causing silent throttling (`PLACE_FAIL`) while logs still show “entry accepted,” creating a hard‑to‑diagnose mismatch.  

**2. Key disagreements**  
- Perspectives 2 and 3 failed to load (model‑unavailable errors), so no observable disagreements exist. With only one successful perspective, there is nothing to split on.  

**3. Synthesized recommendation**  
Project Gamma should treat the imminent enable‑of‑the‑four dormant setups as a high‑risk change and first institute a pre‑flight autonomous verification that both the `recency_check` gate and `license_monitor` are explicitly allowing the setups; only then flip the `enabled` flags. Simultaneously, patch the yfinance beacon path to request `sort=desc` (or otherwise guarantee the newest bar is retained) so that any feed fallback cannot reintroduce a stale price/inverted ribbon. Finally, attach a lightweight circuit‑breaker to the OP‑22 commit that monitors for a sudden surge in losing trades or exit‑manager overload and automatically reverts the `enabled` flags if thresholds are breached.  

**4. Confidence in synthesis**  
**5/10** – The synthesis rests on a single successful perspective; the absence of the other two viewpoints reduces confidence, though the points are detailed and grounded in the recent status logs.  

**5. Single most‑important next action**  
Run an autonomous check **right now** (before market close) that queries the `recency_check` gate and `license_monitor` status for each of the four setups and logs `PASS` only if both return `ALLOW`; if any return `BLOCK`, abort the `enabled=true` flip and alert the operator via the existing silent‑log channel (no popup).  

**6. Watch‑for signal**  
If, after the setups are enabled, the system logs a rapid increase in entry attempts (> 2× the baseline rate) **or** the exit manager begins dropping TP/stop updates (evidenced by missing `EXIT_UPDATE` logs) **or** the beacon falls back to yfinance and reports a price stale by > $1.00 with an inverted ribbon, then the synthesis is invalidated and the proposed safeguards have failed.

## Individual perspectives

### Perspective 1: `nvidia/nemotron-3-super-120b-a12b:free`

_Elapsed 25.2s, 3313 in / 2500 out, cost $0.0000_

**1. Most likely failure mode**  
The engine will flip `enabled=true` on the four dormant setups (`vwap_continuation`, `vwap_reclaim_failed_break`, `vix_regime_dayside`, `gap_and_go`) **without confirming that the `recency_check` gate or `license_monitor` is actually allowing them**. If either gate is still suppressing the setups (e.g., a recent drawdown has triggered a temporary hold that hasn’t cleared), the config flip will be a no‑op for the strategy logic but the system will log “setup enabled” and later, when the gate finally releases, a burst of entries will fire all at once. Because the setups were validated on stale data (pre‑audit) and the market regime may have shifted, the synchronized burst will likely hit adverse price action, generating a string of losing 0DTE fills that the exit manager will try to manage simultaneously, overwhelming the tick‑loop and causing missed TP/stop updates.

**2. Worst‑case impact on J's environment**  
A sudden surge of losing option fills will drive the account P&L sharply negative within a few minutes. The system’s self‑healing logic will attempt to flatten positions via `Gamma_EodFlatten` and the exit manager, but because the exit loop is already saturated, the flatten may be delayed or partial. The resulting P&L dip will trigger the operator’s external monitoring (e.g., a personal P&L alert or a Discord ping if the operator has opted‑in for loss alerts), causing an unsolicited interruption during market hours—contradicting the “do not disturb the user” principle.

**3. Worst‑case impact on Pilot/Heartbeat**  
Heartbeat will continue to emit stale or incorrect signals because the beacon fix only addressed the Alpaca path; the yfinance fallback still returns ascending, untruncated bars, but the shared‑signal fallback logic now prefers the beacon price when the core ledger is stale. If the Alpaca feed experiences a hiccup (e.g., rate‑limit throttling) and the system falls back to yfinance, the beacon will again deliver a stale price (yfinance’s 5‑minute cache can be ~1‑2 min old) and an inverted ribbon, corrupting the fleet signal and causing Heartbeat to issue opposite‑direction entries on the very strategies that were just enabled. This creates a feedback loop: bad signal → bad entries → larger losses → more self‑healing attempts → further signal degradation.

**4. Rule 9 / Rule 10 / OP violations**  
- **Rule 9**: The plan to ship the changes “after the close” is compliant, but the *verification* step (“confirm the 4 dormant setups are OFF by config, not a deliberate recency‑drawdown HOLD”) is being performed **mid‑session** (the audit note appears at ~11:50 ET). If the operator decides to act on that verification before 15:55 ET and flips the flags early, it constitutes a mid‑session rule change.  
- **Rule 10**: If the `recency_check` gate is actively blocking the setups (i.e., the rule says “do not trade when recency_check fails”), enabling them via config would violate Rule 10 because the trade would proceed despite a rule‑based block. The system would then be placing trades that the rule explicitly forbids.  
- **OP‑22**: The change relies on “standing authorization (OP‑22)” for an autonomous, reversible commit. However, OP‑22 requires that the change be *reversible without human intervention* and that the system can *self‑heal* if the commit proves harmful. The current plan lacks an automated rollback trigger (e.g., a circuit‑breaker that watches for a sudden rise in losing trades and auto‑reverts the `enabled` flags). Without that, the standing authorization is insufficient.

**5. Hidden second‑order effects**  
- **Strategy crowding**: Enabling `vwap_continuation` and `gap_and_go` adds two more intraday mean‑reversion/momentum models that are highly correlated with existing `vwap_reclaim_failed_break`. Simultaneous activation can increase effective position size on the same micro‑structure signals, raising slippage and market‑impact costs, especially in low‑volume 0DTE SPY options.  
- **Exit‑manager strain**: The exit manager was sized for the historical mix of strategies. Adding four new entry streams increases the average number of open contracts per tick, potentially exceeding the designed concurrency limits of the `exit_manager` loop and causing dropped TP/stop updates.  
- **License‑monitor drift**: The `license_monitor` tracks overall strategy‑license usage. A sudden increase in active setups may push the license usage over its internal threshold, causing the monitor to silently throttle new entries (returning `PLACE_FAIL`) while still logging “entry accepted,” creating a mismatch between perceived activity and actual fills that is hard to diagnose without extra telemetry.  
- **Beacon‑

### Perspective 2: `deepseek/deepseek-v4-flash:free`

**FAILED** -- `NotFoundError: Error code: 404 - {'error': {'message': 'This model is unavailable for free. The paid version is available now - use this slug instead: deepseek/deepseek-v4-flash', 'code': 404}, 'user_id': 'user_37luJnwxpk0HYbXnEZhUPm6TH2Q'}`

### Perspective 3: `minimax/minimax-m2.5:free`

**FAILED** -- `NotFoundError: Error code: 404 - {'error': {'message': 'This model is unavailable for free. The paid version is available now - use this slug instead: minimax/minimax-m2.5', 'code': 404}, 'user_id': 'user_37luJnwxpk0HYbXnEZhUPm6TH2Q'}`
