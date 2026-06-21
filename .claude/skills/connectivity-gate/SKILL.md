---
name: connectivity-gate
description: FUNCTIONAL head-to-toe pre-trade connectivity gate. The functional SUPERSET of preflight-gate. Two layers - LAYER 1 (process: TV CDP port + TV proc + alpaca-mcp proc, via connectivity-gate.ps1, no MCP) then LAYER 2 (functional MCP round-trips: TV reads live+fresh data, Alpaca clock/account/positions reachable, flat-verified, VIX readable). Returns ONE verdict (GREEN/RED) + the EXACT failed node + a heal hint. Invoke at the top of every heartbeat tick that might enter, before any pilot order, and at premarket. Fails CLOSED for trading (RED = no entry) but NEVER locks out the human.
---

# Skill: connectivity-gate

The hardening layer J asked for: *"make skills that include connectivity checks so the engine is hardened head to toe."*

`preflight-gate` proves the substrate is **alive** (port listening, processes running). That is necessary but NOT sufficient: **"process alive" != "functionally working."** A TV process can be up with CDP listening while `data_get_ohlcv` returns stale/cached bars; an alpaca-mcp process can be running while the key is 401 and `get_account_info` returns nothing. This gate adds the FUNCTIONAL layer: **can the engine actually READ live data and REACH the account, end-to-end, before it places an order.**

One question, one verdict: **is the full path TV-read -> decision -> Alpaca-order proven working RIGHT NOW?**

> Per CLAUDE.md OP-25 ("silent failure is the only true failure"): every failure is a LOUD, NAMED node with a heal hint - never a dead tick.
> Cross-refs: **L47 / C11** (broker is source of truth - verify flat before entry), **C7** (audit outputs not exit codes - "process alive" is an exit code, "data is fresh" is an output), TV-CDP-silent-death lesson (2026-05-14 01:14 ET - port can listen while reads fail).

---

## HARD CONSTRAINT - do not disrupt J's chart

**If J is live-charting on TradingView Desktop in another session, do NOT make disruptive TV MCP calls.**

- `chart_get_state`, `data_get_ohlcv`, `quote_get` are **reads** - generally safe, but `quote_get`-on-VIX requires a `chart_set_symbol` round-trip (set VIX -> read -> restore SPY) which **changes the visible chart**. If J is on the chart, **SKIP the VIX symbol-swap** and use the cached VIX instead (see node `VIX_READABLE`).
- Any **write** that fixes a wrong chart (`chart_set_symbol`, `chart_set_timeframe`) must be **deferred** when J is on the chart: report node `TV_CHART_WRONG` as a degraded-but-not-blocking note, do NOT silently re-point his chart.
- The TV **heal** (relaunch via `setup/launch_tv_debug.ps1`) kills ALL TradingView processes including J's. NEVER pass `-Heal` / run the relaunch while J is on the chart. The off-switch belongs to the human (OP-32 scar: a market-hours firewall locked J out on 2026-05-22 - any guard MUST fail open).

The autonomous heartbeat/`Gamma_Heartbeat` task owns the chart during 09:30-15:55 ET and CAN do the swap-and-restore safely. A **manual** Claude session during market hours must assume J may be on the chart and prefer cached/read-only paths.

---

## Layers

### LAYER 1 - PROCESS (cheap, MCP-free, testable now)

Run the substrate script. It probes the port/process layer and emits the first nodes. **No MCP calls** - safe to run while J charts.

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1"
```

Fastest variant (raw port/proc only, skips the chained data-verify + sched-pulse sub-audits):

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1" -ProcessOnly
```

This is the cheap first check. It wraps the existing `preflight-gate.ps1` (which itself chains `heartbeat-mcp-self-test` + `chart-data-verify` + `heartbeat-pulse-check`) and re-expresses the result as a flat node list. **If LAYER 1 is RED, STOP** - LAYER 2 functional round-trips would fail anyway. Read the failed node + heal hint from stdout or:

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\connectivity-gate-latest.json"
```

LAYER 1 nodes:

| Node | PASS criteria | FAIL -> heal hint |
|------|---------------|-------------------|
| `TV_CDP_PORT` | CDP port 9222 listening | relaunch TV via `setup/launch_tv_debug.ps1` - **ONLY if J not on chart** |
| `TV_PROCESS` | >=1 TradingView process alive | relaunch TV - **ONLY if J not on chart** |
| `ALPACA_MCP` | >=1 `*alpaca-mcp*` process alive (WMI cmdline probe, L27) | **CANNOT-AUTO-HEAL** - needs J to restart with key validation |
| `PREFLIGHT_SUBSTRATE` | `preflight-gate` verdict != RED (data-freshness + sched-task pulse) | inspect `preflight-gate-latest.json`; `preflight-gate.ps1 -Heal` |

### LAYER 2 - FUNCTIONAL (the new hardening - executed via MCP by the heartbeat/pilot)

**This layer is PROSE the heartbeat/pilot executes with its own MCP access. The substrate script does NOT run it.** Run it ONLY after LAYER 1 is GREEN. Each node below has an EXACT MCP call + EXACT pass criteria + the node name to report on failure.

#### Node `TV_DATA_LIVE` - TV read works AND is fresh (not stale/cached)

```
mcp__tradingview__data_get_ohlcv(symbol="BATS:SPY", interval="5m", count=3, summary=true)
```

- **PASS:** returns **>= 2 bars** AND the latest **CLOSED** bar timestamp is within **~10 minutes** of now (ET). (A 5m chart's last closed bar is at most ~5 min old plus a small read margin during RTH.)
- **FAIL -> node `TV_DATA_STALE`** if the latest closed bar is older than ~10 min (cached/frozen feed - the classic CDP-listening-but-feed-dead failure).
- **FAIL -> node `TV_DATA_DEAD`** if the call errors or returns < 2 bars (read path broken).
- **Heal hint:** relaunch TV via `setup/launch_tv_debug.ps1` (process layer fix for a dead feed) - **ONLY if J is NOT on the chart**. If J is on the chart, report RED + do NOT relaunch; the heartbeat that owns the chart will recover on its own next session-start, a manual session must abstain.

#### Node `TV_CHART_CORRECT` - chart is on the right symbol + timeframe

```
mcp__tradingview__chart_get_state()
```

- **PASS:** state shows symbol == `BATS:SPY` AND timeframe == `5m` (the production read context).
- **FAIL -> node `TV_CHART_WRONG`** otherwise.
- **Heal:** the autonomous heartbeat sets it back (`chart_set_symbol("BATS:SPY")` -> `chart_set_timeframe("5")`). **If J is on the chart, do NOT re-point it** - treat as a degraded note, not a hard block (J may be intentionally on another symbol/TF; the heartbeat's own read steps set their context per-tick anyway). This node is **SOFT** (see GREEN/RED rule).

#### Node `MARKET_OPEN` - Alpaca reachable AND market open

```
mcp__alpaca__get_clock()
```

- **PASS (for trading):** call succeeds AND `is_open == true`.
- **`is_open == false` -> node `MARKET_CLOSED`** - this is **NOT an error**. It is a legitimate no-trade state (pre/post market, weekend, holiday). The gate returns a non-trading verdict, not RED-as-failure. Heartbeat emits its normal closed/HOLD path.
- **call errors -> node `ALPACA_UNREADABLE`** (clock unreachable = alpaca-mcp functionally dead even if the process is alive).
- **Heal hint:** `ALPACA_UNREADABLE` -> **CANNOT-AUTO-HEAL, needs J** (key validation / mcp restart). Emit Discord alert; do NOT place orders.

#### Node `ACCOUNT_REACHABLE` - account state actually returns

```
mcp__alpaca__get_account_info()
```

- **PASS:** returns an object with a numeric `equity`.
- **FAIL -> node `ALPACA_UNREADABLE`** (process alive but key 401 / functionally dead - the exact failure `preflight-gate` cannot see).
- **Heal hint:** **CANNOT-AUTO-HEAL, needs J.** This is the canonical "process alive != working" catch.

#### Node `FLAT_VERIFIED` - broker confirms no conflicting open position before a NEW entry

```
mcp__alpaca__get_all_positions()
```

- **PASS (before a NEW entry):** no open SPY 0DTE option position on the **Safe** account. (Broker is source of truth - L47 / C11. Never enter a second leg on a position the engine forgot.)
- If a SPY 0DTE position IS open: this is **not a connectivity failure** - it is a **state** node. The gate reports `POSITION_OPEN` so the caller routes to MANAGE (TP/stop/runner), not ENTER. Only a NEW-entry tick treats `POSITION_OPEN` as block-the-entry.
- **Bold account symmetry (L49 / C9):** the `Gamma_Heartbeat_Aggressive` task runs its OWN connectivity-gate against `mcp__alpaca_aggressive__get_all_positions` / `..._get_clock` / `..._get_account_info`. **The Safe heartbeat prompt is SAFE-ONLY and must NEVER call `mcp__alpaca_aggressive__*`** (scope corrected 2026-06-18). Same node names, separate verdict, separate JSON.
- **Heal hint:** none - this is a state read; if it errors, fold into `ALPACA_UNREADABLE`.

#### Node `VIX_READABLE` - VIX available for the gates

The VIX gates (filter 8: VIX>17.30 AND rising; `vix_bear_hard_cap`; etc.) need a VIX value. Prefer the **cached** VIX to avoid a chart swap:

```
read automation/state/loop-state.json -> vix_cache = { value, prior_value, dir, fetched_at }
```

- **PASS (cached path):** `vix_cache.value` is a number in `[5, 100]` AND `fetched_at` is recent enough for the gate (cached is acceptable; note that `cached`/`flat` dir does NOT pass filter 8 by itself - that is a gate rule, not a connectivity failure).
- **Live refresh (heartbeat-owned chart ONLY):** `chart_set_symbol("TVC:VIX")` -> `quote_get` -> validate `description` matches /VIX|VOLATILITY/i AND `last` in `[5,100]` -> restore `chart_set_symbol("BATS:SPY")`. **NEVER do this swap if J is on the chart** - use cache only.
- **FAIL -> node `VIX_UNREADABLE`** only if there is no usable cache AND (no live refresh available because J is charting, OR the live refresh fails validation). VIX-unreadable is **SOFT for entry** (the VIX gate can abstain rather than the whole gate going RED) unless a VIX-gated setup is the only candidate - see GREEN/RED rule.

---

## The ONE verdict - GREEN / RED rule

Classify each node as **HARD** (a failure means the order path is broken - RED) or **SOFT** (degraded, the engine can still safely abstain/route without a hard block).

| Node | Layer | Class |
|------|-------|-------|
| `TV_CDP_PORT`, `TV_PROCESS`, `ALPACA_MCP`, `PREFLIGHT_SUBSTRATE` | process | **HARD** |
| `TV_DATA_LIVE` (-> `TV_DATA_STALE`/`TV_DATA_DEAD`) | functional | **HARD** |
| `MARKET_OPEN` (clock-reachable part) | functional | **HARD** |
| `ACCOUNT_REACHABLE` (-> `ALPACA_UNREADABLE`) | functional | **HARD** |
| `FLAT_VERIFIED` (positions readable) | functional | **HARD** to read; `POSITION_OPEN` = route-to-MANAGE, not RED |
| `TV_CHART_CORRECT` (-> `TV_CHART_WRONG`) | functional | **SOFT** (heartbeat sets its own per-tick read context; never re-point J's chart) |
| `VIX_READABLE` (-> `VIX_UNREADABLE`) | functional | **SOFT** (VIX gate abstains) unless the only candidate is a VIX-gated setup |

**Rules:**

1. **GREEN** = all HARD nodes PASS. Cleared to evaluate/enter. (SOFT nodes may be degraded - note them, but proceed.)
2. **RED** = any HARD node FAILS. **No entry.** Report the verdict as `RED :: node=<EXACT_FAILED_NODE> :: <heal hint>`. Exactly one named node is the headline (the first HARD failure in head-to-toe order: process nodes -> TV_DATA -> clock -> account -> positions).
3. **MARKET_CLOSED** = `get_clock.is_open == false` -> this is **NOT RED**. It is a clean no-trade verdict; the heartbeat takes its normal closed/HOLD path. Do not alert as a failure.
4. **POSITION_OPEN** = `get_all_positions` shows an open SPY 0DTE -> route the tick to **MANAGE**, not ENTER. Not RED.
5. **Fail CLOSED for trading, fail OPEN for the human.** RED blocks the *entry*. RED NEVER kills/blocks J's interactive session and NEVER relaunches TV while J is on the chart (OP-32).

Head-to-toe order (so the headline node is the FIRST thing broken along the path):

```
TV_CDP_PORT -> TV_PROCESS -> ALPACA_MCP -> PREFLIGHT_SUBSTRATE      (LAYER 1 process)
  -> TV_DATA_LIVE -> TV_CHART_CORRECT                                (can I SEE live SPY?)
  -> MARKET_OPEN -> ACCOUNT_REACHABLE -> FLAT_VERIFIED               (can I REACH + safely act on the account?)
  -> VIX_READABLE                                                     (do I have the gate inputs?)
```

That sequence IS the trade path **TV-read -> decision -> Alpaca-order**, checked in order, so the named failed node tells you exactly which segment of the path is broken.

---

## When to invoke

- **Top of every heartbeat tick that might place an order** - run LAYER 1 first (cheap); if GREEN and the tick is a potential ENTER, run the LAYER 2 functional nodes before scoring. (A pure HOLD/MANAGE tick can rely on LAYER 1 + the reads it already does.)
- **Before any manual `/pilot` order** - full LAYER 1 + LAYER 2.
- **Premarket** - LAYER 1 (and LAYER 2 `MARKET_OPEN` will correctly report `MARKET_CLOSED` pre-09:30; that is the expected premarket verdict).
- **On demand** when J asks "is the engine actually wired end to end / can it really trade right now?"

---

## How it composes with `preflight-gate`

`connectivity-gate` is the **functional SUPERSET**; `preflight-gate` is the **process substrate** it builds on.

- `preflight-gate` answers *"are the pieces alive?"* (port listening, processes running, sched-task firing, CSV fresh).
- `connectivity-gate` answers *"does the whole path actually work end to end?"* (TV returns FRESH live bars, Alpaca clock+account+positions actually RETURN, VIX is available).
- LAYER 1 of this skill **calls `preflight-gate.ps1`** under the hood (the `PREFLIGHT_SUBSTRATE` node) - so you do not run both separately. Run `connectivity-gate` and it includes the preflight substrate, then adds the functional round-trips on top.

| | preflight-gate | connectivity-gate |
|---|---|---|
| Layer | process / infra | process **+ functional** |
| Catches | dead port, dead proc, stale CSV, dead sched-task | all that **PLUS** frozen-but-listening TV feed, 401-but-alive alpaca-mcp, market-closed, position-already-open, VIX-unreadable |
| MCP calls | none | LAYER 2 round-trips (TV read, alpaca clock/account/positions) |
| Verdict | GREEN/YELLOW/RED (worst-of-3) | **GREEN/RED** (+ exact failed node) + MARKET_CLOSED / POSITION_OPEN routing |

---

## What this skill NEVER does

- Place orders.
- Modify keys, `params.json`, `heartbeat.md`, or any doctrine (Rule 9).
- Re-point J's chart (`chart_set_symbol`/`_timeframe`) or relaunch TV **while J is on the chart** (OP-32 - human holds the off-switch; any guard fails open).
- Call `mcp__alpaca_aggressive__*` from the Safe path (scope is SAFE-ONLY; Bold runs its own gate - L49).
- Turn `MARKET_CLOSED` or `POSITION_OPEN` into a false "RED failure" - those are routing states, not connectivity failures.

---

## Cross-references

- **Substrate script (LAYER 1):** `setup/scripts/connectivity-gate.ps1` -> `automation/state/connectivity-gate-latest.json`
- **Process substrate it wraps:** `preflight-gate` (`setup/scripts/preflight-gate.ps1`) -> `heartbeat-mcp-self-test`, `chart-data-verify`, `heartbeat-pulse-check`
- **Production tool contracts (LAYER 2):** `automation/prompts/heartbeat.md` (Alpaca tool reference table; VIX swap-and-restore at the VIX section; SAFE-only scope note)
- **VIX cache:** `automation/state/loop-state.json#vix_cache`
- **Consumed by:** `heartbeat` / `Gamma_Heartbeat` (entry ticks), `pilot` manual fires, premarket.
- **Lessons:** OP-25 (silent failure is the only true failure), **L47 / C11** (broker source of truth - verify flat), **C7** (audit outputs not exit codes), TV-CDP-silent-death (2026-05-14), OP-32 / L54 (never lock out the human), L49 / C9 (dual-account symmetry, separate verdicts).
