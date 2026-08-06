# PREREG — LEVER 1: THE DAILY LOSS CAP / CIRCUIT BREAKER

**Frozen 2026-08-06, after the close.** Clock verified this session:
`python setup/scripts/et_clock.py` → `2026-08-06 16:45:23 Thursday EDT`, `market_hours=False`.

This document is committed **BEFORE** the runner exists. Git-provable via
`git merge-base --is-ancestor <this commit> <runner commit>`.

Analysis only. Arms nothing, ships nothing, touches no trading-path file.

---

## 1. Question

J, verbatim (2026-08-06): *"we need to dial in on how to NOT LOSE TWO THOUSAND DOLLARS on
Wednesday... we gotta KEEP OUR LOSSES SMALL so that way our wins can stack."*

**Does a daily loss cap / circuit breaker cap a Wednesday-shaped day near −$500 WITHOUT
costing Tuesday (+$3,617) or Thursday (+$1,461)?**

Prime lead (from the brief, not re-derived here): Rule 5's kill switch is −30% of SoD equity
(Safe) / −50% (Bold+Risky). On 2026-08-05 risky-3 lost 24.5% of SoD — **48.9% of its own kill
budget**, headroom −$1,526.62 remaining. The existing daily stop has never been tested at any
other value.

---

## 2. Populations (both real, never mixed in one column)

**A. THE BOOK — real broker fills.**
`automation/state/fills-ledger.jsonl`, rows with `attribution=="engine"` AND `is_option` AND
NOT `is_crypto`, reconstructed into positions by the repo's single canonical definition
(`exit_shape_parity_study.reconstruct_positions`), closed positions only.
26 ET dates, 2026-06-26 .. 2026-08-06. SPY options only (the brief's per-arm/day totals are
all-in and include a crypto-twin residual; both are correct, different scopes).

**B. THE REPLAY — 391-day population.**
`analysis/recommendations/engine-fullhist-replay-2026-07-23.json` `trades`: 191
RIDE_THE_RIBBON-family trades over 141 traded days inside a 387-calendar-RTH-day window
(2025-01-02 .. 2026-07-22). Entries frozen on real OPRA; exits already re-walked through the
**real production exit core** (`exit_manager.plan_exit_actions` via
`exit_manager_walk.walk_exit_manager`). Sequential, one position at a time.
**SCALE CAVEAT, pre-declared:** Population B is ONE arm at qty 3. It can validate a per-arm
or sequence-shaped breaker MECHANISM across 141 independent days. It structurally CANNOT
validate a fleet-level dollar threshold, and it cannot produce a Wednesday (its worst day in
387 RTH days is −$825).

---

## 3. Start-of-day equity — provenance, frozen

The %-of-SoD ladder needs a REAL per-arm, per-date start-of-day equity. Sources, in priority
order, all of them broker reads logged at the time:

| Arm(s) | Source | Field | Coverage |
|---|---|---|---|
| safe-1, safe-3, risky-1, risky-3 | `automation/state/fleet/{arm}/decisions.jsonl` | `equity` on the FIRST tick of the ET date with `flat==true` | fleet-arm tick log |
| safe-2 (CORE-SAFE), bold-2 (CORE-BOLD) | `automation/state/daily-loss-guard-{date}.jsonl` | `equity` on the `REARMED` row for `account` in {safe, bold} | from 2026-07-09 |
| cross-check, 2026-08-03..08-06 | Alpaca `account/portfolio/history?period=3M&timeframe=1D` via `fleet_broker._request` | prior-session close equity | post-reset only |

**Pre-declared gap handling.** The five live paper accounts were re-created on ~2026-07-30
(all funded $5,000; portfolio history is zero before then), so the pre-reset accounts' broker
history is GONE. Any `(arm, date)` cell with **no** real SoD equity is left **UNCAPPED** in
the %-ladder — the breaker simply cannot arm there. This is conservative: it can only
UNDERSTATE a %-cell's saving, never inflate it. Coverage (positions and dollars covered vs
total) is reported in every %-table. **No SoD equity is interpolated, extrapolated, or
reconstructed.** The absolute-dollar ladder needs no equity and runs on the full 26-date book.

**Equity-regime disclosure, pre-declared.** Arm equity was ~$1,160–$2,122 pre-reset and
~$4,500–$6,200 post-reset. A fixed dollar cap therefore means a very different % of SoD in the
two eras. Every absolute-dollar cell reports the era split.

---

## 4. Counterfactual semantics — FROZEN

1. **Realized P&L only.** A position's P&L becomes known to the engine when its LAST exit fill
   prints (`close_ts` = max exit-fill timestamp). Nothing is known earlier.
2. **Sequential and PATH-CONSISTENT.** Entries are walked in chronological order. A position
   the rule BLOCKS never happens, so its P&L never enters the running total that gates later
   entries. *(This differs from Lane 0's `loss_anatomy_instrument_2026_08_06.day_breaker`,
   which summed the ORIGINAL closed set — including positions its own rule would have blocked
   — and therefore over-blocks. Both are computed; the path-consistent walk is PRIMARY, the
   Lane-0 shape is reported as `naive_*` for continuity and the difference is disclosed.)*
3. **Blocks NEW entries only.** A position already open when the breaker trips runs to its
   actual exit. It is NOT force-liquidated. This matches Rule 5's real semantics ("day closed
   for that account") and is the conservative choice.
4. **Resets at the ET date boundary.** No carry-over.
5. **Realized-only is strictly LATER-tripping** than the live equity-based Rule-5 switch, which
   also sees unrealized mark-to-market. **Every saving reported is therefore a FLOOR** on what
   an equity-based breaker at the same threshold would have saved — and, symmetrically, every
   Tuesday/Thursday cost reported is a FLOOR on what it would have cost.
6. **Scope of a "session"** = one `(arm, ET date)` for per-arm levers, one `(ET date)` for
   fleet levers.

---

## 5. The grid — FROZEN

### L1-PCT — per-arm daily loss cap, % of that arm's REAL SoD equity
`{4, 6, 8, 10, 12, 15, 20, 25, LIVE}` where **LIVE** = 30% for safe-1/safe-2/safe-3 and 50%
for bold-2/risky-1/risky-3 (CLAUDE.md Rule 5; confirmed in each arm's live breaker file).

### L1-ABS — per-arm daily loss cap, absolute dollars
`{150, 250, 400, 600, 800, 1200}`

### L1-FLEET-ABS — fleet-wide pooled realized-day cap, absolute dollars
`{150, 250, 400, 500, 600, 750, 800, 1000, 1200, 1500}`
(500/750/1000/1500 retained for continuity with the Lane 0 table.)

### L1-FLEET-PCT — fleet-wide pooled cap, % of pooled SoD equity
Same % ladder as L1-PCT. Pooled SoD = Σ over arms with a real SoD equity that date.

### L2-CONSEC — consecutive-loss breaker
Halt the arm for the remainder of the session after **N consecutive losing closed round
trips**, `N ∈ {2, 3, 4, 5}`. Ordering is by **close time**. Frozen streak rule:
`pnl < 0` → increment; `pnl > 0` → reset to 0; `pnl == 0` → unchanged.
Also run at fleet scope (streak over all arms' closes pooled), reported separately.

### L3-RETRACE — day-peak retrace halt
Halt when realized day P&L falls `X%` below its intraday realized **peak**,
`X ∈ {20, 30, 40, 50}`. Two pre-declared arming variants, BOTH reported:
- `peak>0`: arms as soon as the running realized total is positive.
- `peak>=100`: arms only once the running realized total has reached +$100.
Per-arm scope primary; fleet scope reported.

### Comparator rows (not new levers; for calibration only)
- CAP-3 entries per `(arm, symbol, date)` — the lever already on the table.
- Lane 0's naive (path-inconsistent) fleet breaker, for continuity.

---

## 6. Gates — FROZEN

**HARD GATE (shipping).** Any cell with `tuesday_delta < −$0.005` — i.e. any cell that costs
more than $0.00 on **2026-08-04** — is **REJECTED FOR SHIPPING**. It is still computed and
still reported, flagged `REJECTED_TUESDAY`. Tuesday is the no-harm test.

**Reported, non-disqualifying:** `thursday_delta`; `n_days_harmed` on the 26-date book;
`worst_harm`; the 141-traded-day replay's `total_delta`, `n_days_harmed`, `n_days_helped`.

**Verdict ceiling, pre-declared: PREREG.** Any threshold selected from a 26-date book is
in-sample by construction. No cell in this study can be graded SHIP. The deliverable is a
ranked table plus a single frozen candidate threshold for a forward confirming run.

---

## 7. Summary statistics — FROZEN definitions

Computed over the set of **BLOCKED positions** for each cell:

- `upside_surrendered` = Σ `pnl` over blocked positions with `pnl > 0`
- `loss_prevented` = Σ `−pnl` over blocked positions with `pnl < 0`
- **`insurance_cost_ratio` = `upside_surrendered / loss_prevented`** — *dollars of upside
  surrendered per dollar of tail loss prevented.* Lower is better; `< 1.0` means the cell is
  net-positive on its blocked positions alone. Undefined (`null`) when nothing was prevented.
- `bind_rate_arm_sessions` = (# `(arm, date)` sessions where the breaker armed at any point) /
  (# `(arm, date)` sessions the arm actually traded)
- `bind_rate_calendar` = (# dates where ≥1 arm armed) / (# dates traded)
- `n_positions_blocked`, `n_days_harmed`, `n_days_helped`

Pre-declared reading of bind rate: *a cap that fires on ~2% of sessions is cheap insurance;
one that fires on ~40% is a different animal and must be judged as a strategy change, not as
a guard.*

---

## 8. Graveyard check — pre-declared, before any number is computed

This lever is **NOT**: stop width in either direction; stopped-then-paid / wider-stop-rescue;
pre-TP1 profit-lock arming (`profit_lock_arm_scope="full"`); hold-longer; hold_to_time_stop;
trail_only_no_tp1; take-profit-earlier; level-target exits; filter-5 deletion; filter-8 relax;
regime standdown; min-contracts changes; wick closed-bar entry; bull-vix-soft-mode; the
arm-looseness knob; per-setup TIME cooldown; late-day or open standdown.

It requires **no forecast** — it is purely reactive to already-booked realized loss, which is
what separates it from the graveyarded regime standdown (a pre-emptive classifier bet whose
classifier failed on 2026-08-02 at 20.9% 8-way accuracy vs a 39.1% majority baseline).

Its nearest LIVE relative is **Rule 5 itself**. This study re-parameterises an existing guard;
it does not invent a new one.

---

## 9. Artifacts this study will produce

- `analysis/deep-research/LEVER-DAILY-CAP-2026-08-06.md`
- `analysis/deep-research/LEVER-DAILY-CAP-2026-08-06.json`
- `backtest/tools/lever_daily_cap_2026_08_06.py` (runner)
- `backtest/tools/lever_daily_cap_verify_2026_08_06.py` (independent re-derivation of every
  headline number from the RAW ledger by a second code path)
