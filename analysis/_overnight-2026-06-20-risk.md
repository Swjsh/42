# Overnight Risk + Money Audit — DRAFT for J (2026-06-20)

> Autonomous overnight audit. **PROPOSAL ONLY — nothing applied.** No params/doctrine touched.
> Ground truth pulled live from Alpaca at audit time (both accounts flat, daytrade_count 0, PDT false).

## 0. Live ground truth (audit-time)

| Account | # | Equity (live) | SMA / last | Multiplier | DT count | PDT | Position |
|---|---|---|---|---|---|---|---|
| Gamma-Safe-2 | PA3S2PYAS2WQ | **$2,000.00** | 2,000 | **4 (margin)** | 0 | false | FLAT (cleared 06-02) |
| Gamma-Risky-2 | PA33W2KUAT40 | **$1,648.75** | 1,673.16 | **1 (cash)** | 0 | false | FLAT (closed 06-18) |

Both positions confirmed flat in `current-position-{safe,bold}.json`. Safe-2 cleared 06-02 (IRON_LAW stale-pending sweep). Bold closed 06-18 after a −$24 exit (broker stop leg missing from bracket — see Finding R4).

CLAUDE.md still lists Safe-2 $2,000 / Risky-2 $1,673 — Risky-2 has drifted to **$1,648.75** (−$24.41 vs the doc). Cosmetic, but the account-context table is stale.

---

## 1. Sizing math vs current equity

### Safe-2 ($2,000) — sits EXACTLY on the tier boundary (Finding R1, key issue)

Tier match in `risk_gate.py:177` is half-open **`equity_min <= equity < equity_max`**. At exactly $2,000 the account therefore lands in the **2000–10000 tier**, NOT the 0–2000 tier:

| Knob | 0–2000 tier | **2000–10000 tier (ACTIVE at $2,000)** |
|---|---|---|
| strike_offset (v15) | OTM-3 | **OTM-2** |
| base_qty / elite_qty | 3 / 3 | **5 / 8** |
| max_premium_pct_of_account | 0.40 ($800) | **0.30 ($600)** |
| structure | 2 TP + 1 runner | 3 TP + 1 cons + 1 agg runner |

This is almost certainly **not** what the doctrine intended. CLAUDE.md's account block explicitly says *"At $2K Safe account → OTM-2 strikes, 5 base / 8 elite contracts"* — so the **2000–10000 tier is the intended one** and the code agrees. GOOD: code and doctrine are consistent here. BUT it is fragile: a single losing tick that drops equity to $1,999.99 silently flips the account to OTM-3 / 3-contracts / $800 cap mid-campaign. The boundary is a **knife-edge**. Recommend documenting the half-open rule explicitly and/or moving the $2K seed a few dollars off the boundary so a tiny P&L wiggle doesn't re-tier the whole strategy.

**Per-trade hard-gate check (Safe-2 @ $2,000, OTM-2, base qty 5):**
- v15 hard gate: `qty × premium × 100 > equity × max_pct(0.30) = $600` → reduce qty.
- At a typical OTM-2 0DTE premium ~$1.50: 5×$1.50×100 = **$750 = 37.5% > 30%** → gate forces qty **4** ($600). With min_contracts 3, that's fine.
- At max_premium_per_contract $3.30 (worst case): 5×$3.30×100 = $1,650 = 82.5% → gate forces qty **1**, which **violates min_contracts 3** ($3.30×3×100 = $990 = 49.5% of equity, still > 30% cap). **There is a premium band where min-3 and the 30% cap are mutually unsatisfiable** → the trade must be SKIPPED (correct), but verify the live heartbeat resolves this as SKIP, not as a forced sub-3 entry. This is the same class as the 06-15 Bold sizing violation (Finding R3).

### Risky-2 ($1,648.75) — in the 0–2000 tier

| Knob | Value | $ at $1,648.75 |
|---|---|---|
| per_trade_risk_cap_pct | 0.50 | **$824.38** max premium/trade |
| daily_loss_kill_switch_pct | 0.50 | floor **$824.38** (−$824 = day done) |
| base_qty / elite_qty (0–2000) | 5 / 5 | — |
| min_contracts | 5 | — |
| max_premium_per_contract | $5.00 | 5×$5×100 = $2,500 worst case |

**Finding R2 — min_contracts 5 collides with the 50% cap AND with cash buying power.**
- 5 contracts × $5.00 (max premium) × 100 = **$2,500 = 152% of equity** — far over the 50% cap AND over the $1,648.75 cash buying power (multiplier 1 = no margin, hard ceiling).
- Even at a modest $1.65 premium: 5 × $1.65 × 100 = **$825 = 50.0%** — exactly on the cap. **Any premium above ~$1.65 forces a min-3-style conflict on a min-FIVE floor.** Aggressive's `position_sizing_tiers` 0–2000 demands base_qty 5 with NO downsize path documented; the only relief is the per_trade cap reducing qty, but min_contracts 5 blocks reduction below 5. **Result: at any premium > ~$1.65, Risky-2 cannot place a compliant trade** (qty 5 over cap, qty <5 under floor) → should SKIP. This is the structural twin of the 06-15 incident.

**Recommendation (DRAFT, J ratify):** lower aggressive `min_contracts` from 5 → 3 for the 0–2000 tier specifically, OR add an explicit "min_contracts is advisory below the cap" downsize path. At a sub-$2K cash account, a 5-contract floor is economically incompatible with a 50% risk cap unless premium is < $1.65. The Safe account already uses min_contracts 3 and it composes correctly.

---

## 2. Kill-switch sanity

| Account | SoD basis | kill_pct | Kill floor | Notes |
|---|---|---|---|---|
| Safe-2 | $2,000 | 0.30 | **$1,400** (−$600) | OK. Matches CLAUDE.md "−$600/day". |
| Risky-2 | $1,673.16 (last SMA) | 0.50 | **$836.58** (−$836) | OK structurally. |

- Kill logic (`risk_gate.py:327`): `equity <= sod_equity*(1-kill_pct)` — sound, isolated per account (Safe halt does NOT halt Bold), matches Rule 5. **No issue.**
- **Watch:** kill floor keys off *start-of-day* equity. Confirm the heartbeat reads a fresh SoD snapshot each morning, not a stale cached value — a stale SoD on a gapped-down open would mis-place the floor. (Verification item, not a confirmed bug.)

---

## 3. PDT / cash-settlement

- **Safe-2: margin account (multiplier 4), equity $2,000 < $25K.** PDT rule fully applies: **3 day-trades / rolling 5 business days.** daytrade_count currently 0. `risk_gate.py:339` enforces `day_trades >= 3 AND equity < $25K → deny`. Correct. **Risk note:** at $2K with OTM-2 5-contract entries, 3 round-trips burns the weekly PDT budget fast; a stop-out + re-entry on a different setup can consume 2 day-trades in one session. No code issue, but the PDT budget is the *binding* constraint on Safe-2's trade frequency, tighter than the kill switch. Worth surfacing in the daily brief.
- **Risky-2: CASH account (multiplier 1).** PDT 3-trade rule does **NOT** apply to cash accounts — instead **settlement (T+1 for options proceeds) is the constraint.** `risk_gate.py` only models the margin-PDT path; it does **not** model cash-settlement / good-faith-violation risk. **Finding R5:** with $1,648.75 cash and no margin, rapid same-day re-entries can spend unsettled proceeds → good-faith violation / 90-day restriction risk. Recommend a cash-account settlement guard (or at minimum a journal flag) for Risky-2. Low probability at current 0DTE cadence (proceeds from a same-day exit are generally available for closing, but a fresh *opening* buy on unsettled cash is the trap).

---

## 4. L168 sizing-up risk + behavioral findings

- **L168** (J's 667 real trades: 1–2 lots +$4,576 / 3+ lots −$17,461; scaled-in −$327/trade): the killer is **sizing-UP / adding after a loss**. CLAUDE.md notes `risk_gate has no post-loss size throttle`. Confirmed — `risk_gate.py` has no consecutive-loss size reduction. `first_entry_after_stop_blocked: true` blocks a *same-setup* re-entry but does NOT throttle size on a *different* setup after a loss. **Finding R6 (DRAFT):** propose an additive, opt-in post-loss size throttle (e.g., after a same-day stop-out, next entry capped at min_contracts regardless of base/elite qty) — directly encodes L168. Additive, off by default, J ratifies before live.
- **Finding R3 / R4 (already-logged, re-flagged for closure):**
  - R3: 06-15 Bold SIZING VIOLATION — 5×$2.06 = $1,030 = 92% of $1,122 equity (G6b exceeded). Trade notes say "FIX-5a code gate now prevents this." **Verify FIX-5a is live in the aggressive heartbeat** — this audit found min_contracts 5 still structurally conflicts with the 50% cap (Finding R2), so confirm the gate SKIPs rather than force-enters.
  - R4: 06-18 Bold −$24 exit — **broker stop leg was MISSING from the bracket** (simple order filled instead of bracket). C11 (broker = source of truth) + L47/L76 (atomic brackets). **This is the highest-severity live finding:** a position rode with NO broker-side stop; only a manual/heartbeat market-close caught it. Recommend a post-fill bracket-integrity assertion (verify all 3 legs present within N seconds of fill; if stop leg missing → emit RED + place a standalone stop immediately).

---

## 5. Prioritized recommendations (all DRAFT — J ratifies)

| # | Severity | Finding | Proposed action (additive, not applied) |
|---|---|---|---|
| R4 | **HIGH** | 06-18 bracket shipped with no stop leg | Post-fill bracket-integrity check; auto-place standalone stop if missing |
| R2 | **HIGH** | Risky-2 min_contracts 5 vs 50% cap vs cash BP — no compliant trade above ~$1.65 premium | Lower agg 0–2000 min_contracts 5→3, OR document advisory downsize; verify SKIP path |
| R6 | MED | No post-loss size throttle (L168) | Opt-in throttle: post-stop next entry → min_contracts qty |
| R5 | MED | Cash-account settlement not modeled for Risky-2 | Cash-settlement guard / good-faith-violation flag |
| R1 | MED | Safe-2 on the $2,000 tier knife-edge | Document half-open `<` rule; consider seeding a few $ off boundary |
| R3 | LOW | Verify FIX-5a (06-15 sizing gate) actually SKIPs | Confirm in aggressive heartbeat; same root as R2 |
| — | LOW | CLAUDE.md account table stale (Risky-2 $1,673 vs live $1,648.75) | Refresh doc figure |

**Nothing in this file has been applied.** No params edited, no doctrine changed, no trades touched. All items require J ratification (or, where they clear the OP-22 auto-ship bar with an A/B scorecard, after-hours autonomous ship — but R2/R6 change risk semantics on live accounts, so J ratifies).
