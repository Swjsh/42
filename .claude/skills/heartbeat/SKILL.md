---
name: heartbeat
description: Run ONE standardized SPY 0DTE heartbeat tick by hand (state -> preflight -> 5m chart -> score gates -> HOLD/ENTER -> write loop-state). Wraps the production doctrine in automation/prompts/heartbeat.md with a fixed, ordered tool sequence so a manual tick never dead-ends on a malformed ToolSearch call. Use for ad-hoc "tick now" / "what would the engine do this minute" fires. Production auto-ticks run via the deterministic Python engine Gamma_HeartbeatCore (heartbeat_core.py, every 1 min RTH, $0, no LLM on the hot path); the LLM Gamma_Heartbeat was RETIRED/disabled 2026-06-25. This is the MANUAL ad-hoc entry point only — never the production tick.
context: fork
agent: pilot
allowed-tools: Bash Read Grep Glob Write Edit
---

# Skill: heartbeat (manual tick)

You are running ONE heartbeat tick by hand, as Pilot, in a forked context.

The `/insights` report (2026-06-18) found 6+ near-identical heartbeat sessions, one of which **failed entirely on a malformed, unparseable ToolSearch call**. This skill removes that failure mode: it gives you a single fixed sequence with the exact tools pre-named, so you never improvise a tool lookup mid-tick.

> **Authoritative doctrine is `automation/prompts/heartbeat.md`** (the v15 rubric). NOTE: production no longer runs this as an LLM prompt — the live engine is deterministic code (`heartbeat_core.py` / `Gamma_HeartbeatCore`) that encodes the same rubric; the LLM `Gamma_Heartbeat` was retired 2026-06-25. This skill is the MANUAL harness around the doctrine, NOT the production path. When in doubt, the doctrine file + `engine_cli` win.

---

## Step 0 - PRE-FLIGHT GATE (non-skippable)

Run the unified readiness gate first:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File "C:/Users/jackw/Desktop/42/setup/scripts/preflight-gate.ps1" -Quiet
echo "preflight_exit=$?"
```

- `preflight_exit=1` (RED) -> **STOP.** Emit one line `ERROR_PREFLIGHT | {failed checks}` and exit. Do NOT read the chart or place anything.
- `0` (GREEN/YELLOW) -> proceed. If YELLOW, carry the degraded check into your reason clause.

---

## Step 1 - READ STATE (6 files, Safe account)

Read exactly these, in order. Use the documented default on any missing file (never crash, never invent):

1. `automation/state/loop-state.json`        (missing -> `session_init`)
2. `automation/state/today-bias.json`
3. `automation/state/circuit-breaker.json`   (`tripped:true` -> emit `TRIPPED`, exit)
4. `automation/state/current-position.json`  (missing -> flat / `null`)
5. `automation/state/key-levels.json`
6. `automation/state/params.json`            (Safe source of truth, `rule_version: v15.3`)

**Skip gates (before any chart read):** `kill-switch` file exists -> `PAUSED`, exit. `circuit-breaker.tripped` -> `TRIPPED`, exit.

---

## Step 2 - LIVE MARKET DATA (fixed MCP tool sequence)

Call these exact tools - do NOT search for alternatives:

| Need | Tool | Notes |
|------|------|-------|
| Market open? | `mcp__alpaca__get_clock` | if `is_open:false` -> this is a dry-run; never place orders |
| SPY 5m bars | `mcp__tradingview__data_get_ohlcv` | `count=3, summary=true`. **CLOSED-BAR FILTER:** drop the in-progress bar[-1] (`bar_close_et = bar.time + 5min` must be `<= now_et`). |
| Ribbon / indicators | `mcp__tradingview__data_get_study_values` | Saty Pivot Ribbon; validate ribbon within +/-2% of price else `ERROR_TV` |
| Spot quote | `mcp__tradingview__quote_get` | sanity-check last vs bars |
| Account / equity | `mcp__alpaca__get_account_info` | for sizing + kill-switch math |

**Chart MUST be SPY 5m.** If `chart_get_state` shows another symbol/timeframe, restore with `chart_set_symbol("BATS:SPY")` + `chart_set_timeframe("5")` before scoring. (Wrong-timeframe was a flagged stall cause.)

VIX: reuse `loop-state.vix_cache` unless stale (>10min, or position open and >4min, or within +/-0.20 of a threshold) per heartbeat.md.

---

## Step 3 - SCORE THE GATES

Apply the v15.3 rubric from `automation/prompts/heartbeat.md` (Entry branch / Position branch). Do not re-derive it here - read the doctrine if you need the exact filter list and thresholds. The 11 filters are binding; a numeric alert is corroboration, never an override.

- **Position open** -> Position branch: TP1 / runner / stop / time-stop / trail logic.
- **Flat** -> Entry branch: all gates must pass for `ENTER_BULL` / `ENTER_BEAR`; else `HOLD` / `SKIP_*` / `WATCH_ONLY`.

---

## Step 4 - OUTPUT (one line only)

Print exactly one line, the production format:

```
HB#{n} {hh:mm} {ACTION} | spy={x} ribbon={spread}c({stack}) vix={x}({dir}) bear={n}/10 bull={n}/11 htf={15m_stack} | {one_clause_reason}
```

ACTIONs: `HOLD HOLD_DEV ENTER_BULL ENTER_BEAR EXIT_TP1 EXIT_RUNNER EXIT_STOP EXIT_TIME SKIP_STALE SKIP_LIQUIDITY SKIP_NEWS PAUSED TRIPPED ERROR_TV ERROR_ALPACA ERROR_PREFLIGHT WATCH_ONLY`.

---

## Step 5 - WRITE STATE (change-only)

- Append the decision row to `automation/state/decisions.jsonl` (include `account_id:"safe"`).
- Update `automation/state/loop-state.json` only on change (tick index, vix_cache, last_bar_timestamp, htf_15m).
- Iron-law: any write to `trades.csv` / `current-position.json` exit rows MUST be backed by a same-tick `mcp__alpaca__get_order_by_id` fill verification. Estimated marks are NOT fills.

---

## Hard limits

- **Place an order ONLY IF:** market open AND the invocation prompt explicitly authorizes it AND all 10 rules + v15.3 pass. Otherwise this is observe-only.
- NEVER modify `heartbeat.md`, `params*.json`, or `CLAUDE.md` (Rule 9).
- NEVER call `mcp__alpaca_aggressive__*` (this is the Safe path; Bold is a separate task).
- Budget: a manual tick should cost < $0.40. One pass, no loops.

---

## Cross-references

- **Doctrine (source of truth):** `automation/prompts/heartbeat.md`
- **Pre-flight:** `preflight-gate` skill (Step 0)
- **Persona:** `.claude/agents/pilot.md`
- **Production path:** `Gamma_HeartbeatCore` — the deterministic PYTHON engine (`heartbeat_core.py`, every 1 min RTH, $0, no LLM/MCP/CDP on the hot path). The LLM `Gamma_Heartbeat` was retired/disabled 2026-06-25. This manual skill is ad-hoc review only and does not affect production.
