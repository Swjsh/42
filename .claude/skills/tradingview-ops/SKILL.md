---
name: tradingview-ops
description: The expert reference playbook for reading the SPY 0DTE chart via the TradingView MCP — the canonical tool-per-intel READ sequence (price bars, VIX, ribbon/EMAs/VWAP, key levels, chart health) with exact params + gotchas, the connectivity guard that runs FIRST, the write-op + restore-state discipline, and the failure -> cause -> heal table. Invoke whenever a tick / pilot / persona needs to read or touch the TV chart, or when diagnosing a TV MCP read failure. Makes every TV interaction bulletproof. DOC skill — no scripts; it teaches the correct tool calls, it does not wrap them.
---

# Skill: tradingview-ops — play the TV MCP like a fiddle

This is the **canonical expert playbook** for the TradingView MCP (`mcp__tradingview__*`, 78 tools against a live TradingView Desktop chart). Read it before any chart read so a tick, a `/pilot` fire, or any persona reads the SPY 0DTE chart *perfectly* — right tool, right params, every gotcha pre-handled.

> **Why this exists.** TV MCP read failures are silent and decision-changing: an in-progress bar that *looks* closed (L34), a CDP port that died after long runtime (heartbeat-mcp-self-test), an indicator read against the wrong name, a level read while the indicator is hidden. Each one quietly poisons a tick. This skill encodes the correct sequence so none of them happen by accident.
>
> **Source of truth it serves.** Production read doctrine is `automation/prompts/heartbeat.md` (Step 2 + the "VIX" / "SPY 5m + ribbon" / "SPY 15m HTF" blocks). This skill is the *expert reference* for the MCP layer those steps ride on — when they disagree, **heartbeat.md wins** (Rule 9 — no mid-session doctrine drift).

---

## 0 — THE CONNECTIVITY GUARD (non-skippable, runs FIRST)

**Never read the chart for a decision without first confirming the chart is reachable, correct, and live.** A read on a dead/wrong/stale chart is worse than no read — it returns plausible-looking garbage.

The guard is the **`connectivity-gate`** skill — the FUNCTIONAL head-to-toe gate (the functional superset of `preflight-gate`). It answers one question: *is the full path TV-read -> decision -> Alpaca-order proven working RIGHT NOW?* Two layers, one verdict (`GREEN` / `RED`), with the exact failed node + a heal hint. **Run it at the top of any tick that might enter and before any pilot order.**

**LAYER 1 — process (cheap, MCP-free, safe while J charts):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1"
# nodes: TV_CDP_PORT, TV_PROCESS, ALPACA_MCP, PREFLIGHT_SUBSTRATE (this last wraps preflight-gate.ps1)
```

If LAYER 1 is RED -> **STOP**; LAYER 2 round-trips would fail anyway. Read the failed node + heal hint from `automation/state/connectivity-gate-latest.json`.

**LAYER 2 — functional (the hardening; PROSE the heartbeat/pilot executes with its OWN MCP access, only after LAYER 1 is GREEN).** "Process alive" != "functionally working" — a TV process can listen on 9222 while `data_get_ohlcv` returns stale bars; an alpaca-mcp process can run while the key is 401 and `get_account_info` returns nothing. The LAYER 2 nodes — exact MCP call -> exact pass criteria -> node name on failure:

| Node (head-to-toe path order) | MCP call | PASS | FAIL node |
|---|---|---|---|
| `TV_DATA_LIVE` | `data_get_ohlcv(BATS:SPY, 5m, count=3, summary=true)` | ≥2 bars AND latest **closed** bar within ~10 min of now_et | `TV_DATA_STALE` (feed frozen) / `TV_DATA_DEAD` (errors or <2 bars) |
| `TV_CHART_CORRECT` (SOFT) | `chart_get_state` | symbol == `BATS:SPY` AND timeframe == `5m` | `TV_CHART_WRONG` (degraded note, not a hard block) |
| `MARKET_OPEN` | `mcp__alpaca__get_clock` | call succeeds AND `is_open == true` | `MARKET_CLOSED` (clean no-trade, NOT RED) / `ALPACA_UNREADABLE` (clock errors) |
| `ACCOUNT_REACHABLE` | `mcp__alpaca__get_account_info` | object with numeric `equity` | `ALPACA_UNREADABLE` (process alive but 401 — the catch preflight can't see) |
| `FLAT_VERIFIED` | `mcp__alpaca__get_all_positions` | no open SPY 0DTE on **Safe** before a NEW entry | `POSITION_OPEN` -> route to MANAGE, not RED |
| `VIX_READABLE` (SOFT) | cached `loop-state.vix_cache` (preferred), else live swap | value in `[5,100]`, recent enough | `VIX_UNREADABLE` (VIX gate abstains) |

**Verdict rule:** `GREEN` = all HARD nodes pass (SOFT nodes may be degraded — note + proceed). `RED` = any HARD node fails -> **no entry**; report `RED :: node=<EXACT_FAILED_NODE> :: <heal hint>` (the FIRST HARD failure in the path order above is the headline). `MARKET_CLOSED` and `POSITION_OPEN` are **routing states, not failures**. **Fail CLOSED for trading, fail OPEN for the human** — RED blocks the entry, never J's session.

> **HARD CAVEAT (operator on the chart — this is THE constraint while J is live-charting).** The TV heal (relaunch via `setup/launch_tv_debug.ps1`, or `heartbeat-mcp-self-test.ps1 -Heal`) kills **all** TradingView processes including J's. **NEVER pass `-Heal` / relaunch TV while J is on the chart** (OP-32 scar: a market-hours firewall locked J out on 2026-05-22 — every guard MUST fail open). And the VIX node's live refresh does a `chart_set_symbol` round-trip that **changes J's visible chart** — when J may be on the chart, **SKIP the VIX swap and use the cache**, and report a wrong chart (`TV_CHART_WRONG`) as a degraded note rather than silently re-pointing it. The autonomous `Gamma_Heartbeat` task owns the chart 09:30–15:55 ET and CAN swap-and-restore safely; a **manual** session during market hours must assume J is on the chart and prefer cached / read-only paths. (MEMORY: "Don't disturb user (highest priority)".)

---

## 1 — THE CANONICAL READ SEQUENCE (tool-per-intel)

For each piece of intel the engine needs, here is the *exact* tool, the *exact* params, and the gotcha that bites if you skip it. Call these tools by name — **do not improvise a `ToolSearch` lookup mid-tick** (a malformed lookup once failed an entire heartbeat session; that is why the `heartbeat` skill pins the sequence).

Always call **`chart_get_state` first** in a fresh session: it returns the symbol, timeframe, and the full list of loaded indicators *with their entity names* — which you need to target study reads and to confirm the guard's symbol/TF invariant.

### 1a. Price bars — `data_get_ohlcv`

```
mcp__tradingview__data_get_ohlcv(symbol="BATS:SPY", interval="5", count=N, summary=true)
```

- **`summary=true` ALWAYS** unless you specifically need every individual bar (the server's own guidance: "ALWAYS pass summary=true unless you need individual bars"). Summary is far cheaper in tokens; raw bars are only for a backtest-grade pull.
- **`count`**: production uses `count=3` for the live-decision read (enough for closed `Latest` + `Prior` after the in-progress bar is dropped). Use more only when you need lookback (e.g. `count=2` on the 15m HTF refresh).
- **`symbol="BATS:SPY"`** — the canonical venue (single-venue IBKR-style feed the engine is calibrated to). Not `SPY`, not `AMEX:SPY`.

**THE CLOSED-BAR GOTCHA (load-bearing — R1, v15.1 fix; the L14/L34/L57/L94/L161 look-ahead family):**

> TradingView labels bars by **OPEN** time and streams the **live, in-progress** bar at index **[-1]**. That in-progress bar has real-looking OHLCV — it does **not** look unfinished (unlike yfinance, whose in-progress bars carry a V=0 sentinel — L33). If you treat `bars[-1]` as "the just-closed bar" you read a mid-bar tick as a close and fire on a price that never closed.

The fix, applied to **every** decision-driving bar read:

```
now_et = current ET wall-clock
for each bar: bar_close_et = bar.time + 5min
keep only bars where bar_close_et <= now_et
Latest = filtered[-1]   # the actually-closed most-recent bar
Prior  = filtered[-2]
# the raw, unfiltered bars[-1] (in-progress) MUST NOT feed any score or write
```

Real incident this prevents: an `ENTER_BULL` once fired on a transient mid-bar high of 745.35 when the actual closed 09:50 bar was a 745.02 PMH **rejection** — the literal opposite of the trigger (L34). Verified day-over-day by the `heartbeat-tick-audit` skill (`MISALIGNED-CRITICAL` must stay 0).

**Staleness corollary:** after filtering, if `Latest.time == loop-state.last_bar_timestamp` AND the volume delta vs the prior bar is `< 30%`, the feed has not advanced — emit `SKIP_STALE` and exit (no state write). And per the §0 guard: if `Latest` close-time is more than ~10 min behind `now_et`, the feed is frozen — treat as `ERROR_TV`, not as a valid quiet bar.

### 1b. VIX — symbol-swap, then **restore** (or reuse cache)

VIX has no dedicated quote tool for an off-chart symbol; you read it by swapping the chart symbol, quoting, and swapping back:

```
mcp__tradingview__chart_set_symbol("TVC:VIX")
mcp__tradingview__quote_get()        # read `last`
mcp__tradingview__chart_set_symbol("BATS:SPY")   # RESTORE — mandatory
```

- **Validate the read:** `description` matches `/VIX|VOLATILITY/i` AND `last` in `[5, 100]`. Out of range -> discard, keep prior cache, do not let a bad VIX pass filter 8.
- **Compute direction** off the cached prior: `rising` if `value > prior + 0.05`, `falling` if `value < prior - 0.05`, else `flat`.
- **PREFER THE CACHE — especially while J may be on the chart.** Production keeps `loop-state.vix_cache = {value, prior_value, dir, fetched_at}` and **only refreshes** if: no cache, OR `now - fetched_at > 10min`, OR a position is open AND `>4min`, OR the cached value is within `±0.20` of a threshold (17.20 / 17.30 / 18.00). Otherwise **reuse** and set `dir="cached"` for the emit. A symbol-swap flickers the chart — during market hours the cached VIX is the right call; a swap is the disrupt-J path and should be the exception, not the default. (`cached`/`flat` does not, by itself, pass filter 8 — that is intentional.)
- **Restore is non-negotiable.** If a swap throws between set and restore, the chart is left on `TVC:VIX` and every subsequent SPY read is wrong. Treat "left on VIX" as an `ERROR_TV` and restore before any further read.

### 1c. Ribbon / EMAs / VWAP — `data_get_study_values`

```
mcp__tradingview__data_get_study_values()   # returns current numeric values for ALL visible studies
```

- Pulls the live values from every **visible** indicator: the **Saty Pivot Ribbon** (fast / pivot / slow EMA), **VWAP**, and the **50-EMA**. The engine reads ribbon stack + spread, VWAP side, and the 50-EMA from here.
- **Sanity gate (production):** the ribbon values must sit within **±2%** of price. If they don't (indicator not loaded, stale pane, wrong instrument), emit **`ERROR_TV`** — do not score on a ribbon that's detached from price.
- **FULL indicator-name requirement** (the classic gotcha): when you *add* or *target* a study you must use its full TradingView name — **`"Relative Strength Index"`, not `"RSI"`**; `"Volume Weighted Average Price"`, not `"VWAP"`. Short names silently fail to match. (Applies to `chart_manage_indicator` and to any `study_filter`.)
- **Null-handling — never crash:** if an expected study is absent from the returned set (e.g. ribbon EMAs missing because the indicator isn't loaded), **log `ema_read_failed`** (or `ERROR_TV` for the ribbon specifically) and continue with the gate treated as unmet — do not throw, do not fabricate a value. A missing indicator is a known, recoverable state.

### 1d. Key levels — Pine read tools, with `study_filter`

Custom levels are drawn by a Pine levels indicator (`line.new` / `label.new` / `table.new` / `box.new`). Read them with the matching Pine tool, and **always pass `study_filter`** to target that one indicator by name:

| Intel | Tool | Note |
|---|---|---|
| Horizontal price levels (PDH/PDL, carry, key S/R) | `data_get_pine_lines(study_filter="<levels indicator name>")` | returns deduplicated, sorted price levels |
| Text annotations w/ prices ("PDH 745.4", "Bias Long") | `data_get_pine_labels(study_filter=...)` | the label text carries the level's identity |
| Session-stats / dashboard tables | `data_get_pine_tables(study_filter=...)` | formatted rows |
| Price zones | `data_get_pine_boxes(study_filter=...)` | `{high, low}` pairs |

- **The indicator MUST be VISIBLE.** These Pine read tools return data only for indicators currently drawn on the chart — a hidden levels indicator returns nothing (looks like "no levels", which is a silent wrong-read). Confirm visibility via `chart_get_state` first; if hidden, that's a config problem to flag, not a "no levels today".
- **`study_filter` is required** to avoid pulling lines from *other* indicators (VWAP bands, ribbon, etc.) into your level set. Get the exact indicator name from `chart_get_state`.
- **Dedup + sort** before use, and reconcile against `automation/state/key-levels.json` (the engine's own level state) — the chart is the visual source, the JSON is what the gates score. Divergence between them is worth a flag.

### 1e. Chart state / health — the meta tools

| Tool | Use |
|---|---|
| `chart_get_state` | symbol, timeframe, **and the full indicator list with entity names** — call FIRST in a session; it feeds the §0 invariant check and every `study_filter` |
| `tv_health_check` | is the CDP bridge alive and responsive (read-only — safe while J is on the chart) |
| `tv_discover` | enumerate reachable TV targets / panes when health is ambiguous |
| `quote_get` | real-time spot snapshot (last/OHLC/volume) — a cheap sanity cross-check that `Latest` close ≈ live last |

---

## 2 — WRITE OPERATIONS (use sparingly; NEVER while J is on the chart)

Reads are safe and frequent; **writes mutate J's live chart** and are the disrupt-J path. The discipline: *touch the minimum, restore the state, and skip entirely if J may be looking.*

| Write op | Tool | Discipline |
|---|---|---|
| Change symbol | `chart_set_symbol` | only as part of an atomic **set -> read -> restore** (the VIX pattern, §1b). Never leave the chart on a non-SPY symbol. |
| Change timeframe | `chart_set_timeframe` | same — the 15m HTF read does `set("15") -> read -> set("5")` to restore. Leaving it on 15m breaks the next 5m tick. |
| Draw a level | `draw_shape(horizontal_line / trend_line / rectangle / text)` | only premarket / off-hours; tag what you drew so it can be cleared. Don't clutter J's live chart mid-session. |
| Add / remove a study | `chart_manage_indicator` | **FULL names** ("Relative Strength Index"); adding/removing a study repaints J's chart — off-hours only. |
| Change study inputs | `indicator_set_inputs` | mutates a live indicator's settings — off-hours only; record prior value to restore. |
| Toggle visibility | `indicator_toggle_visibility` | note that hiding the levels indicator breaks §1d Pine reads. |

**The three write rules:**
1. **Atomic restore.** Any symbol/timeframe change is a temporary excursion — restore `BATS:SPY` / `5m` in the same logical operation, even on the error path. A throw between set and restore leaves a poisoned chart.
2. **Off-hours only for structural writes** (draw, add/remove indicator, set inputs). During RTH the chart is J's instrument and the engine's read surface — don't repaint it.
3. **If J may be on the chart, do not write at all.** Prefer cached reads. The cost of a flickered chart on a live operator outweighs any convenience. (MEMORY: highest-priority "don't disturb user".)

> **Orders are NOT a TV operation.** Execution is Alpaca only (`mcp__alpaca__place_option_order`). The TV MCP never places, modifies, or cancels an order. `replay_trade` is a *backtest-replay* construct, not a live order — don't confuse it.

---

## 3 — FAILURE MODES -> CAUSE -> HEAL

| Symptom | Likely cause | Heal |
|---|---|---|
The symptom -> cause -> heal rows below; the **node** column is the `connectivity-gate` node name to report (so the headline failure is the exact broken path segment).

| Symptom | Node | Likely cause | Heal |
|---|---|---|---|
| `data_get_ohlcv` returns **"fetch failed"** / empty | `TV_DATA_DEAD` (after `TV_CDP_PORT`) | TV **CDP port 9222 dead** (silent death after long runtime) — TV processes can be alive while the port stopped listening | `tv_health_check` to confirm; then relaunch via `setup/launch_tv_debug.ps1` (or `heartbeat-mcp-self-test.ps1 -Heal`: kill+relaunch, wait ~8s, re-probe). **Only if J is NOT on the chart.** This is the §0 connectivity-gate heal path. |
| Bars look right but **decision fired on a price that never closed** | (not a gate node — a scoring bug) | in-progress `bars[-1]` used as a close (the L34 bug) | apply the §1a close-time filter (`bar_close_et <= now_et`); verify with `heartbeat-tick-audit` (`MISALIGNED-CRITICAL` must be 0) |
| `Latest` close-time **> ~10 min behind now** | `TV_DATA_STALE` | feed frozen / CDP half-alive / chart not updating | treat as RED (not a quiet bar); `tv_health_check`; cross-check `chart-data-verify` (CSV/yfinance/TV three-way); relaunch TV if CDP is the culprit AND J is off the chart |
| `data_get_study_values` **missing the ribbon / EMAs**, or ribbon **>2% off price** | `ERROR_TV` (scoring) | indicator not loaded, hidden, or stale pane; wrong instrument on chart | log `ema_read_failed` / emit `ERROR_TV`; confirm symbol+indicators via `chart_get_state`; off-hours re-add with the **full name** |
| `data_get_pine_lines` returns **nothing** (looks like "no levels") | (config flag) | levels indicator **hidden** or wrong `study_filter` | `chart_get_state` to confirm the indicator is visible and grab its exact name; pass it as `study_filter`; if genuinely hidden, flag a config problem (don't accept "no levels") |
| Wrong instrument's bars / ribbon detached | `TV_CHART_WRONG` (SOFT) | chart left on **another symbol or timeframe** (e.g. VIX swap not restored, or J navigated away) | if engine owns the chart: restore `chart_set_symbol("BATS:SPY")` + `chart_set_timeframe("5")` before scoring. **If J is on the chart: do NOT re-point — report degraded note.** |
| VIX read absurd (e.g. 0 or 9999) or chart **stuck on TVC:VIX** | `VIX_UNREADABLE` (SOFT) | bad quote, or a symbol-swap that threw before restore | discard the read, keep prior `vix_cache`; force-restore `BATS:SPY` (engine-owned chart only); VIX gate abstains rather than blocking the whole tick |
| `get_account_info` / `get_clock` empty though alpaca-mcp process is alive | `ALPACA_UNREADABLE` | key 401 / functionally dead (the catch preflight can't see) | **CANNOT-AUTO-HEAL — needs J** (key validation / mcp restart); emit Discord alert; do NOT place orders |
| Everything reads "fine" but values disagree with CSV/yfinance | (data drift) | data-source drift (consolidated vs single-venue) **or** a wrong-bar match | run `chart-data-verify` (1-3¢ divergence is normal; `>$0.10` is RED — stale cache or wrong bar) |

**General heal principle:** any "latest" timeseries element from any external API must be checked against `time_close <= now_wall_clock` before it's trusted as closed (L34's general rule). Silent success is the only true failure — a read that *returns* but returns wrong is the dangerous case, so the audits (`chart-data-verify`, `heartbeat-tick-audit`, `heartbeat-mcp-self-test`) exist to catch reads that "worked" but lied.

---

## 4 — THE GOTCHAS TABLE (memorize)

| # | Gotcha | The rule |
|---|---|---|
| G1 | **In-progress bar at [-1]** looks closed (real OHLCV, no sentinel) | filter `bar_close_et = bar.time + 5min <= now_et`; use `filtered[-1]` (L14/L34/L57/L94/L161) |
| G2 | `summary=true` is the default, not the exception | always pass it on `data_get_ohlcv` unless you truly need every bar |
| G3 | **Full indicator names only** | `"Relative Strength Index"` not `"RSI"`; short names silently no-match (`chart_manage_indicator`, `study_filter`) |
| G4 | **`study_filter` required** on every Pine read | otherwise you mix lines/labels from other indicators into your set |
| G5 | **Pine reads need the indicator VISIBLE** | a hidden levels indicator returns nothing → looks like "no levels" (a silent wrong-read) |
| G6 | **VIX = swap + restore** (or cache) | always restore `BATS:SPY`; prefer the cache during market hours; never leave the chart on `TVC:VIX` |
| G7 | **Timeframe excursions must restore** | the 15m HTF read restores to 5m; leaving 15m breaks the next 5m tick |
| G8 | **CDP can die silently** while TV is alive | `tv_health_check` / port-9222 probe is the load-bearing liveness check, not "is TV running" |
| G9 | **MSIX CDP-port launch** | TradingView Desktop is MSIX; only `setup/launch_tv_debug.ps1` (direct process create, `UseShellExecute=$false`) passes `--remote-debugging-port=9222`; a normal launch strips the flag → no MCP |
| G10 | **TV process count is 10–14** | parent + child renderers; any count > 0 means "alive" — the CDP-port check decides reachability, not the count |
| G11 | **`BATS:SPY` is the canonical symbol** | not `SPY` / `AMEX:SPY`; the engine is calibrated to this venue |
| G12 | **Ribbon must be within ±2% of price** | else the indicator is detached/stale → `ERROR_TV`, don't score |
| G13 | **Don't crash on a missing study** | log `ema_read_failed` / treat gate unmet; never fabricate a value |
| G14 | **Writes repaint J's live chart** | structural writes off-hours only; if J may be on the chart, read-only + cached |

---

## What this skill NEVER does

- Place / modify / cancel an order (that is Alpaca; the TV MCP is read + chart-control only).
- Modify `heartbeat.md`, `params*.json`, or any doctrine (Rule 9).
- Run the destructive TV-relaunch heal while J may be on the chart (the off-switch is J's; never disrupt his chart).
- Treat a hidden indicator, a frozen feed, or an in-progress bar as valid data.

---

## Cross-references

- **Connectivity guard (THE guard, run FIRST):** `connectivity-gate` skill → `setup/scripts/connectivity-gate.ps1` (LAYER 1 process) + the LAYER 2 functional MCP round-trips (TV_DATA_LIVE / MARKET_OPEN / ACCOUNT_REACHABLE / FLAT_VERIFIED / VIX_READABLE). It is the functional **superset** of `preflight-gate` (which it wraps as its `PREFLIGHT_SUBSTRATE` node → `setup/scripts/preflight-gate.ps1`). Run `connectivity-gate`, not both.
- **MCP liveness + heal (substrate):** `heartbeat-mcp-self-test` skill → `setup/scripts/heartbeat-mcp-self-test.ps1`; TV launcher `setup/launch_tv_debug.ps1`.
- **Data-trust cross-check:** `chart-data-verify` skill (CSV vs yfinance vs TV three-way).
- **Closed-bar verification:** `heartbeat-tick-audit` skill (`MISALIGNED-CRITICAL` day-over-day).
- **Production read doctrine (source of truth):** `automation/prompts/heartbeat.md` — Step 2, the "VIX" / "SPY 5m + ribbon" / "SPY 15m HTF" blocks; the `heartbeat` skill pins the fixed tool sequence.
- **Look-ahead lesson family:** `markdown/doctrine/LESSONS-LEARNED.md` L14 (level look-ahead), L34 (in-progress `data_get_ohlcv` bar — the canonical closed-bar lesson), L57 (`prior_bars` lookback), L94 (first-hour-high dwell), L161 (naive-ET tz). CLAUDE.md Lessons index C6 (no look-ahead / as-of correctness).
- **Operator-disturbance rule:** CLAUDE.md "Don't disturb user (highest priority)" + the J market-hours discipline reminder (no interactive sessions / chart-disrupting writes 09:30–15:55 ET).
