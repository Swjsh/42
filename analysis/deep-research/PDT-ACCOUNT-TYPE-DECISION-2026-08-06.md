# PDT / ACCOUNT-TYPE DECISION PAGE — 2026-08-06

> **For J. Facts assembled, keys untouched, nothing changed.** One decision at the bottom.
> Every broker number below live-read 2026-08-06 ~18:55 ET via each arm's own REST creds
> (read-only `GET /v2/account` + `GET /v2/account/activities/FILL`).

## 1. What the broker actually says (all 5 live arms, born 2026-08-03)

| Arm | Account # | Equity | `multiplier` | `pattern_day_trader` | `daytrade_count` | `shorting_enabled` | `cash` | `regt_buying_power` |
|---|---|---|---|---|---|---|---|---|
| safe-2 (core) | PA3POKNV46VG | $5,727.91 | **4** | **null** | **null** | true | =equity | 2x equity |
| bold-2 (core) | PA3WEBXJU67N | $5,477.71 | **4** | **null** | **null** | true | =equity | 2x equity |
| safe-3 | PA32T7Q1O20H | $5,780.15 | **4** | **null** | **null** | true | =equity | 2x equity |
| risky-1 | PA3S9N1IV0A4 | $6,338.46 | **4** | **null** | **null** | true | =equity | 2x equity |
| risky-3 | PA3V7JT25H6Z | $5,343.32 | **4** | **null** | **null** | true | =equity | 2x equity |

- All 5 are **margin-shaped** (`multiplier=4`, Reg-T BP = 2x, shorting on). None is cash-shaped.
- Alpaca PAPER reports **no PDT telemetry at all** (`pattern_day_trader`/`daytrade_count`/`daytrading_buying_power` all null).
- **Behavioral proof the paper broker does NOT enforce PDT:** this week safe-2 ran 8 day-trades
  in the rolling window, risky-1 8, risky-3 9 — **zero broker rejections, zero PDT flags.**

## 2. What our own docs claim (vs that reality)

| Doc | Claim | Reality 2026-08-06 |
|---|---|---|
| `automation/state/params.json#_pdt_gate_mode_doc` | "Gamma-Safe-2 (**PA3DHPT7KIQE**) is a **CASH** account — verified live: multiplier=**1**" | safe-2 is **PA3POKNV46VG** (PA3DHPT7KIQE no longer exists post-reset); reads multiplier=**4**. Stale on BOTH the account number and the account type. |
| `automation/state/aggressive/params.json#_pdt_gate_mode_doc` | "**PA33W2KUAT40** is now a 4x MARGIN account" | bold-2 is **PA3WEBXJU67N**. The margin *mechanism* claim matches today's reads; the account number is stale. |

Both provenance docs cite accounts that no longer exist. The **modes** they justify are still what
the code runs (safe-2 `cash_settlement`, bold-2 `margin_pdt`) — the *premise* under safe-2's mode
(cash account) is no longer true of the current account.

## 3. What actually gates entries today (code, verified paths)

| Arm | Mode | Enforced? | Mechanism |
|---|---|---|---|
| safe-2 | `pdt_gate_mode=cash_settlement` | **YES (core)** | settled-cash pool via `settlement_ledger.py` — no day-trade counting at all. Premised on a cash account; the account now reads margin. |
| bold-2 | `pdt_gate_mode=margin_pdt` | **YES (core)** | `pdt_tracker` real count >= 3 & equity < $25K → `RISK_DENY_PDT`. This is a **self-imposed** rule — the paper broker demonstrably does not enforce it (section 1). Blocked Wed+Thu this week; unblocks **2026-08-12**. |
| safe-3 / risky-1 / risky-3 | pinned `margin_pdt` (`fleet_executor.py:1125`) | **NO — LOG-ONLY** (FLEET-PDT-PARITY, shipped 08-06) | true count logged per tick (`day_trades_true`); gate binds on legacy `daytrade_count` = null → 0. `params.fleet_pdt_enforce` default FALSE. Flipping it TRUE today would instantly jail all three arms (counts 6/8/9). |

## 4. What Alpaca's own docs say about the rule itself (fetched tonight via alpaca MCP)

Source: docs.alpaca.markets "Understanding FINRA's New Intraday Margin Rule and the End of PDT":

- FINRA's Rule 4210 overhaul **replaces the legacy PDT framework**: the $25,000 threshold and the
  "4 trades in 5 days" count are **eliminated**, replaced by a risk-based **Intraday Margin Level
  (IML)** system (standard $2,000 Reg-T minimum applies).
- **12-month interim period**: firms may apply EITHER legacy PDT or the new intraday-margin rule,
  per account, while transitioning. (Alpaca paper's null-PDT telemetry + non-enforcement is
  consistent with the new framework / non-enforcement on paper.)
- 0DTE-specific: expiration of a long option is explicitly an IML-reducing transaction — the new
  rule margins 0DTE properly instead of counting trades.
- Matches the 2026-07-14 research already in-repo (`CASH-ACCOUNT-DAY-TRADING-REGULATIONS-2026-07-14.md`:
  "FINRA retired even the margin version 2026-06-04").

## 5. Cost of the current mixed posture (this week, real fills)

- bold-2 sat **hard-blocked Wed 08-05 + Thu 08-06** (and stays blocked Fri + Mon + Tue) on a
  self-imposed legacy-PDT count the broker doesn't apply and FINRA is retiring. Thursday was a
  +$1,465 book day bold-2 could not participate in.
- The other margin-shaped arms traded 6-9 day-trades each with zero consequence — so the book's
  weekly evidence is generated under rules bold-2 alone is denied.
- safe-2's settlement gate never visibly bound this week (equity $5.7K vs typical $300-600 entries).

## 6. The decision (J's call — three coherent options, facts only)

| Option | What it means | One-line change |
|---|---|---|
| **A. Match the broker (no PDT on paper)** | bold-2 rejoins the fleet Monday; all 5 arms uniform; live-money PDT question re-decided at live-arming time (per OP-0 #1 that already needs J). | aggressive/params.json `pdt_gate_mode: margin_pdt -> cash_settlement` (or a new `none_paper` mode) |
| **B. Enforce legacy PDT everywhere (train-for-live discipline)** | All 5 arms jailed at 3 DT/5bd — at this week's rate (6-9 DTs/arm) most arms sit blocked most days; weekly evidence rate collapses. | set `fleet_pdt_enforce: true` + safe-2 -> `margin_pdt` |
| **C. Keep the mixed status quo** | bold-2 alone keeps paying the legacy-PDT tax through Tue 08-11; docs stay stale. | none (fix the 2 stale doc fields regardless) |

**Whatever the pick: the two `_pdt_gate_mode_doc` fields should be re-verified against the
live accounts above** — both currently cite dead account numbers as their provenance.

---
*Assembled by Lane 7 (Monday readiness), 2026-08-06 evening. Data: read-only broker pulls; no
keys, params, or modes were modified. Rolling-window math + per-day counts:
`MONDAY-READINESS-2026-08-09.md` section 3.*
