# RESET-PLAN-2026-08-01 — paper-account normalization brief + post-reset runbook

> WS12 (weekend grind, Saturday 2026-08-01; live reads + dry-runs executed 12:34–12:47 ET).
> ALL PAPER. The only step Claude cannot do is the Alpaca dashboard reset click itself
> (no API exists — verified 2026-07-31, `.claude/skills/alpaca-paper-reset/SKILL.md`).
> Everything below the click is prepared, dry-run-proven, and guarded tonight.

## VERDICT — recommended reset targets

| Arm | Account | Equity now (live) | Target | Tier landed | Strike | Ceiling$ after |
|---|---|---|---|---|---|---|
| safe-2 (CORE-SAFE) | PA3DHPT7KIQE | $1,160.30 | **$2,500** | SAFE [2K,10K) | ATM | $2.50 |
| safe-3 (FLEET-TIGHT-S) | PA32RD49OB0Q | $1,967.81 | **$2,500** | BOLD [2K,10K) | OTM-2 | $2.50 |
| bold-2 (CORE-BOLD) | PA33W2KUAT40 | $1,197.52 | **$2,500** | BOLD_CORE [2K,10K) | OTM-2 | $2.50 |
| risky-1 (FLEET-FULLSEND-R) | PA3W17FD8G19 | $1,756.87 | **$2,500** | BOLD_CORE [2K,10K); full-send lane ATM (PROBE table) | OTM-2 / ATM | $2.50 |
| risky-3 (FLEET-LOOSE-R) | PA31WIU8X15Q | $2,121.61 | **$2,500** | BOLD_CORE [2K,10K); ladder/probe lanes ATM (PROBE table) | OTM-2 / ATM | $2.50 |
| crypto-twin | PA38EG1JTFBT | $9,826.97 | **DO NOT RESET** | — | — | — |

**$2,500, not the FOCUS-DOCTRINE default $2,000** — because **$2,000 sits EXACTLY ON the
[$2K,$10K) tier boundary** (§4). $2,500 is the minimum equity at which every arm's premium
ceiling covers the full typical ATM band ($1.30–$2.50), and it buys $500 of drawdown buffer
before any tier flap. Fallback if the dashboard only offers fixed choices: $2,000 exact
(still lands INSIDE [2K,10K) per `pick_tier`'s half-open semantics — but with zero buffer
and a $2.00 ceiling that refuses the $2.01–$2.50 top of the ATM band; disclose if used).

Crypto twin is excluded: 24/7 evidence continuity (skill precondition) + the concurrent
latency drill owns that lane tonight.

---

## 1. Why now — Friday proved tier boundaries are load-bearing

- **risky-3 was $76.35 over the $2K boundary** ($2,076.35), resolved the closer OTM-2
  strike, cleared the $0.30 `min_entry_premium` floor, and took the day's winning trade —
  while the two arms below the boundary (safe-3 $1,967 → OTM-3, risky-1 pre-extension →
  OTM-3) were refused by the same floor.
- Current equity spread $1,160–$2,122 puts the 5 SPY arms in **two different strike
  brackets** with premium ceilings from $1.16 to $2.12. The champion/challenger grid is
  supposed to compare GATES at equal capital; today it compares bankrolls.
- The 2026-07-30 deadlock incident (safe-2: equity $1,160 → ceiling $1.16 < ATM $1.42–2.01
  all session → 9× RISK_DENY, arm structurally blind) is the same mechanism from the other
  side. `sizing_deadlock_diag.py` was built for it; its live table is quoted in §3.

## 2. Live equity snapshot — Alpaca REST, 2026-08-01 12:35–12:47 ET

Read via `fleet/secrets.json` creds (5 SPY arms — same path as `accounts_status.py`) +
`automation/state/crypto-twin/secrets.json` (twin). All 5 SPY arms **FLAT** (cash == equity;
Saturday, no positions) — the skill's flat-before-reset precondition is already satisfied.

| Arm | Account | Status | Equity | last_equity | Multiplier |
|---|---|---|---|---|---|
| safe-2 | PA3DHPT7KIQE | ACTIVE | $1,160.30 | $1,160.36 | 1 (cash) |
| safe-3 | PA32RD49OB0Q | ACTIVE | $1,967.81 | $1,967.81 | 1 (cash) |
| bold-2 | PA33W2KUAT40 | ACTIVE | $1,197.52 | $1,197.52 | **1 — see note** |
| risky-1 | PA3W17FD8G19 | ACTIVE | $1,756.87 | $1,756.87 | 1 (cash) |
| risky-3 | PA31WIU8X15Q | ACTIVE | $2,121.61 | $2,121.61 | 4 (margin) |
| crypto-twin | PA38EG1JTFBT | ACTIVE | $9,826.97 | $9,835.90 | 4 (margin) |

**bold-2 multiplier note:** `aggressive/params.json#pdt_gate_mode` was flipped to
`margin_pdt` 2026-07-20 because the account then read multiplier=4. It reads **1** today.
Its own doc says "revert to cash_settlement IF the account reads multiplier=1 again" — but
a reset may re-provision the account again, so the reconciliation is a POST-reset runbook
step (§7 step 8), not a tonight edit.

## 3. Current tier / strike / clearance / ceiling per arm

Strike tables (all in `crypto/lib/strike_selection.py`, resolved per arm as annotated):

- `V15_SAFE_TIERS`: [0,2K) ATM · [2K,10K) ATM · [10K,25K) +1 · [25K+) ITM-2 — safe-2
  (heartbeat_core, account=="safe").
- `V15_BOLD_TIERS`: [0,2K) OTM-3 · [2K,10K) OTM-2 · [10K,25K) OTM-1 · [25K+) ITM-2 —
  safe-3 (params_patch `strike_tier_table="bold"`, documented-deliberate cheap-OTM choice).
- `V15_BOLD_CORE_TIERS`: [0,2K) ATM · [2K,10K) OTM-2 · [10K,25K) OTM-1 · [25K+) ITM-2 —
  bold-2 (heartbeat_core since 2026-07-18) + risky-1/risky-3 normal lanes
  (`strike_tier_table="bold_core"`, armed 2026-08-01 pre-registered).
- `PROBE_STRIKE_TIERS` (fleet_executor): ATM through $10K — risky-1 full-send lane
  (`_full_send_plan`), risky-3 ladder (`_ladder_plan`) + probe lanes. Standalone table by
  design; **unchanged by any sub-$10K reset target.**

Floor-clearance rates (fraction of signals whose entry premium clears the $0.30
`min_entry_premium` floor) are strike-offset-indexed, from the 391-day real-OPRA strike-axis
study `analysis/recommendations/bold-strike-axis-2026-07-15.json`:
ATM 0.9795 overall / 0.9688 afternoon · OTM-1 0.8072 / 0.7099 · OTM-2 0.6280 / 0.5276 ·
OTM-3 0.4167 / 0.3376 · ITM 1.0.

**At CURRENT equity** (ceilings = live `sizing_deadlock_diag.py` output, quoted verbatim):

| Arm | Equity | Tier now | Strike now | Floor clearance (all/pm) | Ceiling$ now | Binds |
|---|---|---|---|---|---|---|
| safe-2 | $1,160.30 | SAFE [0,2K) | ATM | 0.98 / 0.97 | **$1.16** | risk_cap |
| safe-3 | $1,967.81 | BOLD [0,2K) | OTM-3 | 0.42 / 0.34 | $1.96 | risk_cap |
| bold-2 | $1,197.52 | BOLD_CORE [0,2K) | ATM | 0.98 / 0.97 | **$1.19** | risk_cap |
| risky-1 | $1,756.87 | BOLD_CORE [0,2K) | ATM (both lanes) | 0.98 / 0.97 | $1.75 | risk_cap |
| risky-3 | $2,121.61 | BOLD_CORE [2K,10K) | OTM-2 (ATM ladder/probe) | 0.63 / 0.53 | $2.12 | risk_cap |

Reading: safe-2 and bold-2 clear the FLOOR fine (ATM) but their **ceilings ($1.16/$1.19)
refuse most of the typical ATM band $1.30–$2.50** — the 2026-07-30 deadlock, still live
today. safe-3 clears its ceiling fine but its OTM-3 strike **fails the floor on ~58% of
signals (66% afternoon)**. Two different starvation mechanisms, both equity-positional.

## 4. The $2,000 boundary problem (why not the FOCUS-DOCTRINE default)

`strike_selection.pick_tier` uses half-open intervals `equity_min <= equity < equity_max`:

- **$2,000.00 exactly lands in [2K,10K), NOT [0,2K).** On the bold tables that means
  OTM-2 the moment the account touches $2,000 — $1,999.99 → ATM (bold_core) / OTM-3 (bold),
  $2,000.00 → OTM-2. One cent flips the strike class.
- Resetting TO $2,000 puts every arm ON that edge: the first losing day drops it into the
  other bracket, the first winning day holds it — tier identity flaps with day-1 P&L.
  risky-3 crossing this boundary mid-week is exactly how Friday's asymmetry happened.
- Ceiling at $2,000 = equity × cap / (min_contracts × 100) = **$2.00 for BOTH profiles**
  (0.30×2000/300 and 0.50×2000/500) — refuses the $2.01–$2.50 top of the typical ATM band
  (2026-07-30 session printed $1.42–$2.01; full-send doc: ATM midday frequently >$2.00).
- On the SAFE table the $2K boundary changes nothing (ATM both sides) — the boundary is
  load-bearing only for the three bold-table arms + safe-3. But equal capital across the
  grid is itself load-bearing (§1), so all five move together.

**$2,500 per arm:**

- Cleanly INSIDE [2K,10K): $500 (20%) of drawdown before any tier flap.
- Ceiling $2.50 both profiles (verified via `sizing_deadlock_diag --equity 2500`, §7 step 3)
  = the MINIMUM equity that covers the full $1.30–$2.50 typical ATM band
  (safe: 2.50×3×100/0.30 = $2,500 exactly).
- Kill switches (Rule 5): safe arms −30%/day = −$750; bold arms −50%/day = −$1,250.
  Per-trade caps (Rule 6): $750 / $1,250.
- Qty tiers move up with the bracket (ratified v15 sizing structure, not a WS12 change):
  safe base/elite 3/3 → 5/8; bold 5/5 → 8/12. `risk_gate` notional caps still clamp — at
  OTM-2 premiums (~$0.50–1.20) qty 8 × $1.20 × 100 = $960 < $1,250 cap fits; ATM qty-5
  full-send at $2.50 = $1,250 = exactly cap.
- Still a "$2K-class" account per FOCUS-DOCTRINE ($100–200/day = one clean +30% level
  trade; that lens is unchanged at $2,500).

## 5. What each arm trades AFTER reset to $2,500

| Arm | Table → tier | Strike | Floor clearance (all/pm) | Ceiling$ | Net effect vs today |
|---|---|---|---|---|---|
| safe-2 | SAFE → ATM | ATM | 0.98 / 0.97 | $2.50 | ceiling unblinds ($1.16→$2.50); strike unchanged |
| safe-3 | BOLD → OTM-2 | OTM-2 | 0.63 / 0.53 | $2.50 | floor-refusal halves (0.42→0.63 clearance); keeps its deliberate OTM lane |
| bold-2 | BOLD_CORE → OTM-2 | OTM-2 | 0.63 / 0.53 | $2.50 | ceiling unblinds ($1.19→$2.50); strike ATM→OTM-2 (§6a) |
| risky-1 | BOLD_CORE → OTM-2; full-send ATM | OTM-2 / ATM | 0.63 / 0.98 | $2.50 | full-send strike UNCHANGED; its refusal band $1.75–2.50 opens (§6b) |
| risky-3 | BOLD_CORE → OTM-2; ladder+probe ATM | OTM-2 / ATM | 0.63 / 0.98 | $2.50 | same tier as today, +$378 capital, ceiling $2.12→$2.50 |

## 6. Honest disclosures — what the reset changes, pauses, or destroys

a. **ATM-under-$2K evidence accrual PAUSES.** Core Bold's sub-$2K ATM tier (wired
   2026-07-18, falsification rail = first n≥20 fills expectancy check) and the fleet
   `bold_core` extension (pre-registered 2026-08-01,
   `fleet-strike-tier-atm-extension-prereg-2026-08-01.json`, n≥20-fill gates) both gate on
   fills in the [0,2K) bracket. At $2,500 that bracket goes dormant; the preregs stay
   registered — nothing is falsified, waived, or edited — and the evidence clock resumes if
   any arm draws back below $2K (one bad bold day from $2,500 can do it: −50% = $1,250).
   The alternative (hold one bold arm sub-$2K to keep collecting) was REJECTED: it breaks
   equal-capital comparability and leaves that arm boundary-adjacent — Friday's exact
   pathology.
b. **Full-send experiment covariate shift.** Strike path unchanged (PROBE table, ATM), but
   the 50%-cap refusal band moves from >$1.75 to >$2.50 → MORE full-send fills per day.
   The kill criterion (n≥10 sessions, P&L + fill-count vs gated arms,
   `full_send_vs_gated.py --since`) keeps running; annotate the reset date so the
   before/after fill-rate jump is attributed to equity, not to the profile. Same class of
   note for risky-3's score-ladder lane.
c. **Broker-side history is DESTROYED per account** (positions, orders, P&L history —
   Alpaca reset semantics; the account NUMBER and keys survive, verified skill design).
   Local ledgers (journal/trades.csv, decisions.jsonl, per-arm fleet ledgers,
   winner-autopsy inputs) are the historical record and are untouched. Consumers that read
   broker fill history must treat 2026-08-0X (reset date) as an epoch: `pdt_tracker`'s 5-day
   day-trade count correctly reads 0 post-reset; any core-strategy-recency broker-fills read
   (WS11, in flight) must not misread "n=0 since reset" as "no evidence ever".
d. **Kill-switch $ anchors jump** with the new SoD equity: safe-2 −$348→−$750/day,
   bold-2 −$599→−$1,250/day. That is Rule 5 working as written (% of SoD), disclosed here
   because the absolute daily-loss exposure roughly doubles vs today's depressed equities.
   Combined worst-case across 5 arms: −$4,750/day (paper).
e. **safe-1 (retired)** shares broker account KIQE with safe-2 — resetting KIQE also wipes
   the retired arm's broker-side residue. Its history lives in its own local
   decisions/breaker files (preserved, per its `_retired_doc`).
f. **PDT/settlement unchanged by target:** every sub-$25K margin account stays 3-day-trades/
   5bd (risky-3 today; bold-2 if re-provisioned margin); cash accounts stay settlement-
   gated (`settlement_ledger`). $2,500 vs $2,000 does not move any PDT threshold.

## 7. POST-RESET RUNBOOK — every command dry-run-proven tonight (Sat 12:35–12:47 ET)

**Precondition:** J signed into https://app.alpaca.markets (Claude never touches login/2FA).
Preferred window: this weekend or Monday BEFORE 08:30 ET (breakers then self-arm on the
post-reset equity with zero manual touches — step 4A).

1. **Reset each SPY account via the skill** (`.claude/skills/alpaca-paper-reset/SKILL.md`),
   target **$2,500** each: safe-2 PA3DHPT7KIQE → bold-2 PA33W2KUAT40 → safe-3 PA32RD49OB0Q
   → risky-1 PA3W17FD8G19 → risky-3 PA31WIU8X15Q. **Skip crypto twin PA38EG1JTFBT.**
   Flat-check per account before its click (all 5 verified flat today, §2; re-verify if
   running later: skill step 5 / `mcp__alpaca__get_all_positions` for core arms).
2. **Verify equity, all arms** —
   `python setup/scripts/accounts_status.py`
   → expect five rows ≈ $2,500.00. PROVEN tonight (returned live table §2).
   NOTE: the script's `BASELINE = 2000.0` will flag "not $2,000" on every arm until step 6
   updates it — expected, not an error. Core-arm cross-check via MCP:
   `mcp__alpaca__get_account_info` (safe-2) / `mcp__alpaca_aggressive__get_account_info`
   (bold-2).
3. **Rerun the deadlock instrument** —
   `python setup/scripts/sizing_deadlock_diag.py`
   → expect every arm CEILING$ = 2.50, BINDS = risk_cap. PROVEN tonight at
   `--equity 2500` (all five arms returned CAP$ 750/1250, CEILING$ 2.50).
4. **Start-of-day breaker caches** (the real foot-gun — stale SoD anchors Rule 5 wrong):
   - **4A. Weekend / pre-08:30 reset (preferred):** nothing to touch. Monday 08:30
     Gamma_Premarket runs the deterministic `daily_loss_guard.rearm()` (idempotent,
     LLM-independent) for both CORE breakers, stamping fresh SoD from live (= post-reset)
     equity; the three FLEET breakers (`automation/state/fleet/{safe-3,risky-1,risky-3}/
     circuit-breaker.json`) re-arm on date rollover at the first fleet tick
     (`fleet_live._load_or_arm_breaker`). VERIFY Monday ≥08:31:
     `python setup/scripts/daily_loss_guard.py --account safe --dry-run` (and `bold`) →
     armed-today with equity ≈ 2500. PROVEN tonight: `--rearm --dry-run` returned
     `WOULD_REARM, prior_date 2026-07-31, equity 1160.30/1197.52` (live fetch works).
   - **4B. Mid-stream reset (a trading day AFTER 08:30):** `rearm()` no-ops once stamped
     today, so force it — for each CORE account, rewind the stamp then rearm:
     `python -c "import json,sys; sys.path.insert(0,'setup/scripts'); import daily_loss_guard as g; cfg=g.ACCOUNTS['safe']; p=cfg['breaker']; b=json.loads(p.read_text(encoding='utf-8')); b[cfg['date_field']]='2000-01-01T00:00:00-0400'; p.write_text(json.dumps(b,indent=2),encoding='utf-8'); print(g.rearm('safe', dry_run=False))"`
     (repeat with `'bold'`). PROVEN tonight against COPIES of both breaker files
     (rewind → `rearm()` → `REARMED`, fresh live SoD, today's stamp; live files verified
     untouched, still 2026-07-31). For each FLEET arm breaker, rewind `last_reset` the same
     way; the next fleet tick re-arms from live equity. Then re-verify as in 4A. Skew direction
     if skipped: kill switch anchored to the LOW pre-reset SoD → far too LOOSE on the new
     bankroll (e.g. safe-2 would need −$1,688 from $2,500 to trip a −$348 limit).
   - Settlement ledgers (`automation/state/settlement-ledger.json` + aggressive twin):
     per-day snapshot keyed by `date` — weekend reset self-heals; mid-stream reset leaves
     them CONSERVATIVE-stale (pre-reset entries understate available cash → refuses trades,
     never over-trades) — acceptable, self-heals next session.
5. **Reconcile bold-2 account provenance:** read multiplier from
   `mcp__alpaca_aggressive__get_account_info`. If 1 (cash) → flip
   `aggressive/params.json#pdt_gate_mode` back to `cash_settlement` per that key's own doc;
   if 4 (margin) → keep `margin_pdt`. (Today it reads 1; a reset may re-provision it.)
6. **Update annotations** (consumers verified: `starting_equity` is read only by
   `fleet_executor.run_dry` demo sizing — live path reads broker):
   - `automation/state/fleet/accounts.json`: `starting_equity: 2500.0` on the 5 SPY arms
     + an `update_note_2026_08_0X` recording the reset;
   - `setup/scripts/accounts_status.py`: `BASELINE = 2500.0`;
   - pathspec-commit both.
7. **STATUS.md note** — one entry: date, 5 accounts reset to $2,500, twin untouched,
   breaker verification result, link here.
8. **Report to J** (REVOKE surface): the accounts_status table + sizing table + any
   deviation (e.g. a dashboard preset forced $2,000 — then §4's zero-buffer caveats apply
   and the tier landed is still [2K,10K); note it in STATUS).

## 8. Guard

`backtest/tests/test_reset_plan_tier_boundaries_2026_08_01.py` pins: all four strike-table
boundary sets (0/2K/10K/25K) + per-bracket offsets, the half-open $2,000.00-lands-UP
semantic, the tier every table resolves at $2,500 (and at $2,000), and the ceiling formula
inputs (safe 0.30/3ct, bold 0.50/5ct → $2.50 at $2,500). Any future tier/boundary edit
RED-fails the suite and invalidates this plan loudly. RED-proof run recorded in the commit.

## Provenance

- Live equities + flat-check: Alpaca REST `GET /v2/account` per arm, 2026-08-01 12:35–12:47
  ET (fleet/secrets.json + crypto-twin/secrets.json creds; keys never printed).
- Ceilings: `setup/scripts/sizing_deadlock_diag.py` (live, `--equity 2000`, `--equity 2500`)
  — risk_gate's own math, not re-derived.
- Clearance rates: `analysis/recommendations/bold-strike-axis-2026-07-15.json` (391-day
  real-OPRA, offset-indexed; the study's own caveats apply).
- Breaker semantics: `daily_loss_guard.py` (rearm idempotence read from source + dry-run),
  `fleet_live._load_or_arm_breaker` (date-rollover re-arm read from source).
- Friday boundary incident: WS12 handoff ("established tonight" ledger).
