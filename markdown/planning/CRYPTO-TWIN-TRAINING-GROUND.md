# CRYPTO TWIN — the 24/7 training ground (J requirement, 2026-07-10 evening)

> **J (verbatim intent):** "Time is our biggest obstacle… take the 24/7 crypto gym idea and map
> it to our code so we don't wait for the next day to validate the engine seeing things. This is
> a REQUIREMENT… get an MCP that trades crypto and just replicate the engine there and use that
> as a training ground. I can't keep fixing four things and waiting for the next day."
>
> **Doctrine note:** this is J's written weekend rule-change (Rule 9 compliant). Crypto's
> "gym-only" boundary is amended: crypto remains NOT an edge/P&L instrument — it becomes the
> engine's LIVE MECHANISM-VALIDATION environment. Its P&L is a health metric, never evidence
> for SPY parameters.

## The one-sentence design

Run the SAME engine code (heartbeat_core → gates → risk_gate → placement → exit_manager →
journal → autopsy) against BTC/USD on Alpaca **crypto paper** (already wired — same MCP, same
creds, `place_crypto_order` exists; $0, no new vendor), 24/7 on a 5-minute cadence, in a fully
separate state namespace — so any fix shipped at any hour is exercised against live-moving
markets within minutes instead of waiting for the next 09:30 ET.

## What it validates (and what it deliberately does not)

| Validates 24/7 (mechanism) | Does NOT validate (edge) |
|---|---|
| signal→gate→risk→order→fill→exit→journal loop end-to-end | whether any setup is profitable on SPY |
| exit engine behavior on REAL paper fills (structure stop, TP1, trail, cat cap) | SPY-specific params (VIX gates, tiers) |
| state integrity: restarts, watermarks, exit-state round-trips, races | strike/premium economics (no options) |
| gate ORDERING + telemetry attribution (tonight's bug class) | anything requiring OPRA/options data |
| funnel/autopsy/visibility instruments on live data | crypto trading as a business |
| soak: hours-long positions, session rollovers, weekend continuity | |

## The 1:1 mapping

| SPY engine concept | Crypto twin |
|---|---|
| SPY 5m closed bars (Alpaca REST) | BTC/USD 5m closed bars (`get_crypto_bars`, same client) |
| RTH 09:30–15:55 window | 24/7; "session" = UTC day for VWAP/level anchoring; entry window gates configurable OFF or mapped to a synthetic session for gate-testing |
| Key levels (PDH/PDL/memory) | prior-UTC-day H/L/C + intraday H/L + the same G11 memory-map code on crypto bars |
| Ribbon/EMA/VWAP/structure detectors | identical code — bars are bars |
| Option premium + %-stops | spot position; % price moves ARE the premium analog (structure stop = close through level, cat cap = % adverse, TP1/trail identical in %) |
| Sizing tiers / strikes | fixed tiny notional ($200/entry paper), min-qty analog preserved so risk_gate paths execute |
| PDT | none (removes a blocker class; PDT code paths still exercised via injected fixtures in tests) |
| Kill-switch (daily loss on SOD equity) | identical logic, UTC-day anchored |
| EOD flatten 15:52 | max-hold flatten (e.g. 6h) so the flatten path fires several times daily |
| Fill funnel / autopsy / firm brief | same instruments, `crypto-twin` namespace + one glance line |

## Architecture (reuse-maximal)

- `setup/scripts/crypto_twin_core.py` — a thin runner that imports the REAL modules
  (heartbeat_core's stages where importable, exit_manager, risk_gate, the watcher detectors)
  with a `TwinConfig` (symbol, bar source, session anchors, notional). Where heartbeat_core is
  too SPY-entangled to import cleanly, extract the stage into a shared function BOTH call —
  never fork-and-drift (the two-lane vwap scar).
- State: `automation/state/crypto-twin/` (decisions.jsonl, exit-state, breaker, funnel) —
  zero writes outside it. Reads production CODE, never production STATE.
- Account: dedicated paper account from the roster NOT in fleet_rest/core (attribution-clean).
- Schedule: `Gamma_CryptoTwin` every 5 min, 24/7 (wscript chain); keepalive-classed;
  exempt-listed for the reaper.
- Monitor: the participation-cascade + funnel instruments run on its namespace; a
  `twin-health.json` glance line lands in the firm brief ("TWIN: n entries, n exits, loop
  latency, last incident").

## The flywheel this buys

1. Ship a fix at 20:00 → twin exercises the same code path by 20:10 → funnel/autopsy verify on
   REAL paper fills by 21:00. **Iteration: days → hours, any hour, weekends included.**
2. This weekend is the first proof: build tonight → 48h soak Sat/Sun (crypto trades) → Monday's
   SPY open inherits a twin-verified engine instead of a hope-verified one.
3. Every future trading-path PR gains a "twin-soak" gate: N clean twin round-trips before RTH.

## Build order (crews launch at session-limit reset ~20:30 ET)

1. **T1 (tonight):** TwinConfig + bar adapter + the see→decide loop ticking on BTC 5m, decisions
   logging, NO orders. Verify: live rows with real crypto bars.
2. **T2 (tonight):** placement + exit management on crypto paper (place/fill/manage/close a real
   tiny BTC paper round-trip), breaker + flatten. Verify: one complete lifecycle in the ledger.
3. **T3 (weekend):** funnel/autopsy/glance wiring + Gamma_CryptoTwin registration + 48h soak
   with the incident log as the deliverable.
4. **T4 (Sunday):** soak report → fold findings → doctrine row + SCHEDULED-TASKS + CLAUDE.md
   proposal for the amended crypto boundary (propose-only).

## Kill criteria / honesty rails

- The twin's P&L never appears in any edge scorecard; its numbers are labeled MECHANISM-HEALTH.
- If twin behavior diverges from SPY-engine behavior on the same code path, that's a FINDING
  (config leak or hidden SPY coupling), not a tuning opportunity.
- Cost: $0 (existing Alpaca paper + free bars). LLM cost: none on the hot path (pure Python).
