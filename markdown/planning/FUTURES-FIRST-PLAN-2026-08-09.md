# FUTURES-FIRST PLAN — audited state + Opus orchestration brief

> Written 2026-08-09 (Sunday) per J's directive: *"I would rather prioritize futures over crypto…
> do a full audit on both, write up a plan, and I'll have Opus orchestrate. We need to get the
> futures going… figure out who we can use [broker]… let's get futures training this week."*
> Audit facts below were read live this session, not recalled.
> Broker-selection research runs in parallel → `analysis/deep-research/FUTURES-BROKER-RESEARCH-2026-08-09.md`
> (Opus: read it before WS-F1; if it has not landed, WS-F0 blocks on it).

---

## 1. AUDIT — crypto program (verdict: HEALTHY, keep as maintenance-mode mechanism lane)

| Component | Live state (read 2026-08-09 14:43 ET) | Verdict |
|---|---|---|
| **Gym** (53 validators, `crypto/validators/`) | Scorecards current through 08-07, fires 17:00 ET daily via Gamma_GymSession | ✅ working; it is a REGRESSION SUITE, not a trading floor |
| **Twin** (Gamma_CryptoTwin, 24/7) | Alive — last tick 2 min before this audit; 15,244 decision rows | ✅ mechanism validator doing its job |
| Twin organic book | n=37 round trips, 8.1% WR, −$4.04 | Working as designed: **mechanism proof, never edge evidence** (standing doctrine) |
| **Kitchen** (24/7 R&D daemon) | Daemon alive (pid live), **3,085 completed tasks**, $0 paid-tier today | ✅ J's "brainstorming should be automated" IS automated. The honest gap is CONVERSION: the search machinery is honest enough to keep returning nulls (181 pre-registered cells → 0 ships is the historical record) |
| **Dashboard display** | **NO crypto/gym tile exists.** The only dashboard hit is an API route (`dashboard/app/api/personas/route.ts`) | ❌ J's question "where do I see the crypto gym on the dashboard" — answer: **nowhere, today**. WS-F6 fixes this |

**Crypto plan: FREEZE at maintenance.** The twin keeps running (it catches real bugs — 2 pre-existing
ones so far, and it corroborated the re-entry-bleed mechanism during the 08-04 audit). The gym keeps
scoring. No expansion (no ETH add, no perps venue, no leverage work) unless the futures lane is
blocked on something only crypto can falsify. Rationale: J's stated priority, and crypto's one
unique property (24/7 reps) is matched by futures (~23h/day Sun–Fri) on the instrument J actually
wants to trade.

---

## 2. AUDIT — futures program (verdict: MORE BUILT THAN IT LOOKS, dormant at the front end)

| Component | Live state | Meaning |
|---|---|---|
| **Docs** | `markdown/futures/`: CONTRACT-SPECS, MARGIN-LEVERAGE-RISK, SESSIONS-ROLLOVER-TAX, SOURCES, REVIVAL-PLAN | Foundational knowledge already written — sessions/rollover/leverage homework is DONE |
| **SSR shadow** (Gamma_SsrShadow) | **LIVE** — ran 08-07 19:03 ET; frozen spec `ssr-v1`; NQ + GC configs, watermarks current; **0 round trips so far** | The forward-evidence clock is already ticking. Arming bar (frozen): ≥20 closed round trips AND positive expectancy AND beats-null. Nothing armable yet |
| **Futures mirror** (Gamma_FuturesMirror) | Ready, ran 08-07; produces `automation/state/futures/` (account.json, decisions.jsonl, edge3-sim fills/position) | A sim spine already exists |
| **Edge #3 sim** (mes-mnq-div) | Fleet arm `mes-mnq-div-futures` defined: "MES leads → trade MNQ laggard on ≥2-bar divergence"; task `Gamma_FuturesEdge3Sim` registered but **has never run** | Built, never exercised — same class as the vwap import-death; must be exercised or deleted |
| **Linear-sim arm** (mes-linear-sim) | Defined: "THE OPTION TAX IS THE KILLER, NOT THE READ — same strategy on a linear instrument" | This is the thesis that makes futures attractive for OUR engine: our directional read may be fine while 0DTE friction (25–33% spread + theta) eats it. MES friction is ~1 tick |
| **Disabled tasks** | Gamma_FuturesEod / FuturesHeartbeat / FuturesPremarket — Disabled since June | Pre-revival era; superseded, clean up or re-register per WS-F3 |
| **History (do not relitigate)** | Phase-1 batteries KILLED twice; SSR batteries KILLED at FDR except 5 short-side PULSE cells → forward shadow only | **The plan must not promise edge.** It promises infrastructure + shadow reps + honest gates |
| **Open item** | Old note: "J owes PROD-token rotation" (2026-07-02 revival) | Re-verify whether still relevant before Phase 0 |

**The honest framing for Opus:** we are not "porting a profitable engine to futures" — the options
engine's live record is one +$996 week on a −$1,372 base. We are porting **infrastructure that
works** (deterministic tick loop, exit_manager, risk_gate, kill switches, twin pattern, canonical
battery, shadow-clock discipline) to an instrument whose friction doesn't tax the read 25% per
round trip. The mes-linear-sim note IS the hypothesis. It gets tested, not assumed.

---

## 3. THE PLAN — workstreams for Opus

**Standards that bind every WS (non-negotiable):** paper/SIM only — live futures is OP-0 #1 AND a
new venue, double J-gate. J creates any account and generates any keys himself; keys go to the
gitignored store (`.mcp.json` pattern / `automation/state/fleet/secrets.json`), never chat, never
tracked files. No net-new paid vendor without J's explicit OK (free sims/demos are fine). Frozen
prereg committed BEFORE any runner (git-provable). Canonical battery + BH for any edge claim.
Twin/sim P&L is never edge evidence. Every new daemon ships with a liveness alarm ON DAY ONE (the
crypto twin once went dark 4 days unnoticed — that lesson is paid for). Guards + RED-proof + one-line
revert + REVOKE on everything. Order-of-operations only — no calendar promises.

### WS-F0 — Broker decision (BLOCKS F1; needs J once)
Read `FUTURES-BROKER-RESEARCH-2026-08-09.md` when it lands. Adopt its recommendation unless its own
caveats break on contact. **J's single action: create the sim account at the chosen venue + put
keys in the gitignored store.** Everything else is Claude-side. If account creation stalls, the
fallback is the data-only path (WS-F2 proceeds on free/delayed data; WS-F3's twin trades a local
fill simulator exactly as edge3-sim already does — zero external dependency).

### WS-F1 — Broker adapter (the twin pattern, ported)
`setup/scripts/futures_twin_core.py` following `crypto_twin_core.py`'s proven shape: thin broker
adapter + **exit_manager / risk_gate / kill_switch imported verbatim** (that reuse is what made the
crypto twin cheap and is the whole point). MES only to start. Contract-notional sizing (a premium-%
stop means nothing here — stops are POINTS; read MARGIN-LEVERAGE-RISK.md first). Session model from
SESSIONS-ROLLOVER-TAX.md: 23h sessions, maintenance break, weekly close — **no RTH assumptions
anywhere** (grep for hardcoded 09:30/16:00 in anything reused). Chaos drills like the crypto twin
had. Liveness alarm day one.

### WS-F2 — Data spine
Per broker research (venue feed vs databento vs delayed CME). Requirements: 1-min bars MES (+MNQ
for edge-3), ET-disciplined via `lib/et_frame.py` (the DST scar is paid for — reuse it), provenance
stamped per DATA-PROVENANCE.md, cache under `backtest/` with the existing lineage pattern. Backfill
enough history to run the battery (existing SOURCES.md lists free candidates).

### WS-F3 — The futures twin goes live (SIM)
Scheduled task (registry + SCHEDULED-TASKS.md), 1-min cadence during futures sessions. Force-fire
scenario drills first (entry/TP1/stop/cat-cap/flatten), then organic. Clean up the June-era
Disabled tasks (FuturesEod/Heartbeat/Premarket): re-register what WS-F3 supersedes, delete the
rest — no zombie registry entries. P&L on the CLOSED path from day one (the crypto twin shipped
without it and the gap cost weeks).

### WS-F4 — Exercise or delete Edge #3
`Gamma_FuturesEdge3Sim` has NEVER run. Decide by evidence: run it on the sim spine for its own
pre-registered window. If its prereg is stale or missing, freeze one first. If it fails its bar,
DELETE the arm and the task (compound, don't accumulate). The MES→MNQ divergence idea is exactly
the kind of thing the battery exists to kill quickly.

### WS-F5 — Strategy vocabulary port (research lane, prereg-gated)
Port the LEVEL/STRUCTURE vocabulary (key levels, market_structure BOS/CHoCH, the entry-quality
signature) to MES RTH first — same tape hours as our SPY evidence, so priors transfer most
honestly. Frozen prereg per cell; canonical battery; BH across cells; the graveyard applies (do
not re-test killed families on a new instrument without stating why the instrument changes the
mechanism — the "option tax" thesis IS such a statement for exit-shape families, NOT for entry
families). SSR shadow keeps its frozen ssr-v1 spec untouched; a new MES config is a NEW prereg,
never an edit to the running one.

### WS-F6 — Display (J's literal ask)
Dashboard tiles: (a) crypto gym scorecard (GREEN/YELLOW/RED + validator count + last run), (b)
twin status (alive, last tick, organic book), (c) futures lane (SSR shadow progress vs its
arming bar, futures-twin status once WS-F3 lands). Also add the same three lines to HOME.md via
obsidian_vault_sync (the vault is now the reading surface). Read-only, $0, fail-open.

### WS-F7 — Futures risk rails (before ANY organic sim entry)
Futures-specific kill switches: per-session loss cap in DOLLARS (not %-of-premium), max
contracts=1 MES to start, overnight-position policy (twin: flat before maintenance break
initially), rollover handling (SESSIONS-ROLLOVER-TAX.md), and the liquidation-distance assertion
adapted from the perps planning work (margin call distance must never be inside the catastrophe
stop). Guard-tested, RED-proofed. **Rule 5/6 analogues stated in writing before the first organic
entry.**

### WS-C1 — Crypto maintenance freeze (small)
Document the freeze (this doc is the record); dashboard tile from WS-F6 covers visibility; twin
and gym keep their schedules; no new crypto work items enter the queue unless tagged
`futures-blocked-falsifier`.

**Suggested execution shape for Opus:** F0 → F1+F2 parallel → F3 → F4+F5+F6+F7 parallel. F6 can
start immediately (needs nothing from F0–F3 for the crypto/SSR tiles).

---

## 4. What needs J (the complete list)

1. **Create the sim account** at the venue the broker research recommends + keys to the gitignored
   store. (The one true blocker; everything else proceeds without you.)
2. Nothing else. Priority call (futures > crypto) is treated as made — this doc is the REVOKE
   surface for it.

---

## 5. Standing questions this plan deliberately does NOT answer

- Whether futures have edge for us. Unknown. Two battery generations said no on the old shapes.
  The linear-instrument thesis is plausible and unproven — that is what the shadow clocks are for.
- Live futures money. Not on the table until: proven sim edge at the canonical bar + J's explicit
  arming (OP-0 #1) + venue funded by J.
