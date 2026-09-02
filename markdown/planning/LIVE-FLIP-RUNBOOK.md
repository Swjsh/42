# Live-Flip Runbook — ONE account, real money

> Operational procedure only. No prose padding. This is a checklist, not an argument for
> going live — that argument (and the current answer) lives in `setup/scripts/go_live_gate.py`
> and [`FABLE-FULL-AUDIT-2026-09-01.md`](../../analysis/deep-research/FABLE-FULL-AUDIT-2026-09-01.md)
> (successor to the 08-27/08-28 TASK A1/A2/B2/C2 findings and the 08-29 review). **As of
> tonight's fresh run the gate reads RED on statistics and prod-shadow, PASS on operations,
> reconciliation and behaviour (behavioural PASS is UNVERIFIED — see §0)** — see §0. Nothing
> in this document is a license to execute; it is the procedure to follow **once** the gate
> reads GREEN as redefined in §0 and J has said so in chat.
>
> Design context (why ONE account): `ONE-ACCOUNT-TRANSITION-2026-08-18.md`. Account selection
> history: `TWO-ACCOUNT-CONSOLIDATION-HANDOFF-2026-08-29.md`. Gate math this runbook is
> downstream of: `setup/scripts/go_live_gate.py`. Queue item tracking this rewrite:
> `automation/overnight/queue.md` → `RUNBOOK-REWRITE-AGAINST-LIVE-CAPS`.
> Every step below that touches money, credentials, or the ARMED flag is J's action alone
> (OP-0 #1) — Claude executes the read-only/preparation steps and reports; it never flips
> live money on its own judgment, no matter how green the gate reads.

---

## 0. Current status (fresh 2026-09-01, 21:22 ET — `go_live_gate.py`)

Run `backtest/.venv/Scripts/python.exe setup/scripts/go_live_gate.py` for the live number.
Snapshot at time of writing:

| Criterion | Verdict | Detail |
|---|---|---|
| 1. Statistical (CI-lower>1.0, all 4 active arms, as-traded+ex-best-day+cost-adj, **full lifetime history**) | **FAIL** | CI-lower 0.33–0.41 on every arm (safe-3 0.356, safe-2 0.333, risky-1 0.412, bold-2 0.347) vs the 1.0 bar. Per §0a this is now a lifetime-robustness disclosure, not the arming bar — see below. |
| 2. Operational (named guardrail tests) | **PASS 6/6** | `eod_flatten_coverage_all_5_arms`, `eod_flatten_read_failure_fails_open`, `never_average_down_no_stacked_entry`, `killswitch_threshold_parity_rule5`, `orphan_position_adoption`, `dead_mans_switch_open_position_on_process_death` — the dead-man's switch shipped 2026-09-01 (`setup/scripts/dead_mans_switch.py`, task `Gamma_DeadMansSwitch`) closed the one gap that blocked this group. |
| 3. Reconciliation (ledger vs live broker equity, window 2026-08-03..08-31) | **PASS 4/4** | safe-3/safe-2/risky-1/bold-2 all reconcile fee-adjusted within tolerance. |
| 4. Behavioural (rule breaks / manual overrides, trailing 20 trading days) | **PASS_UNVERIFIED** | 0 rule breaks, 0 manual-attribution fills in window — but `rule-breaks.jsonl` was last written 2026-05-18, before this window even starts, so a clean ledger is indistinguishable from an abandoned one. Reported PASS_UNVERIFIED, not a bare PASS, since 2026-09-01 (FABLE-FULL-AUDIT W5). |
| 5. Prod-shadow (dedicated shadow arm, net of costs) | **FAIL — INSUFFICIENT_DAYS** | Wired 2026-09-01 to `automation/state/prod-shadow-designation.json`: candidate **safe-3**, window 2026-09-01→2026-09-29 (min 20 scored days), extended-clock view to **2026-10-30** (40 days). `days_scored=0/20` tonight — the window just opened. |

**One governing clock (decided 2026-09-01, Gamma-decides, revoke = `git revert`):** the frozen-config
window opened 2026-09-01. The 09-29 gate re-run is a **checkpoint**, not an arming date. The
first real arming *decision* is at the TIGHT-LADDER close, **2026-10-30**, on ≥40 scored days
(`../../analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md`). "GREEN for arming" means: criterion 5 (prod-shadow,
scored on the frozen window, net of costs, all three views) PASS, plus criteria 2–4 PASS.
Criterion 1 (pooled lifetime per-arm CI-lower) is reported as a lifetime-robustness disclosure
only — it structurally cannot clear on a history that includes an engine no longer run,
and softening it would be bar-softening in the wrong direction (the frozen window is the
harder, cleaner test). Base case, stated honestly: no real money in 2026; the path that keeps
"before 2027" alive requires the frozen window to score like the post-08-11 era, not like July.
Full derivation: FABLE-FULL-AUDIT-2026-09-01.md §2 and §7.

**Do not start §2 below until criterion 5 reads PASS (not INSUFFICIENT_DAYS) in a run from
that same day, with criteria 2–4 also PASS.**

---

## 1. Account selection

**The first-live candidate is safe-3** (FLEET-TIGHT-S, account `PA3…T20H`), designated
2026-09-01 as the prod-shadow arm scored in §0 row 5. Why: J's 2026-08-29 consolidation
directive retires safe-2 at window close and keeps safe-3 + risky-1
(`TWO-ACCOUNT-CONSOLIDATION-HANDOFF-2026-08-29.md`); safe-2 is the only active arm negative
on its full sample (−$7.20/day, trade-level Kelly −0.022) and is the arm scheduled for
retirement — putting a retiring arm's profile first live was the original (2026-08-28)
mistake in this runbook, corrected here. safe-3 is full-sample positive (+$32.35/day,
trade-level Kelly +0.057) with no live secondary-lane defect, and reconciles clean
(§0 row 3).

**History, one line:** the 2026-08-28 version of this runbook recommended safe-2 first on
ATM-simplicity and lowest observed max-DD-% grounds; that recommendation is superseded — see
`FABLE-FULL-AUDIT-2026-09-01.md` §4 item 7 for the correction and its evidence.

**safe-2, bold-2, risky-1 stay PAPER**, unchanged, per `ONE-ACCOUNT-TRANSITION-2026-08-18.md`
§3 — they remain the laboratory; the live account is the product. (risky-3 was retired
2026-08-29 and re-tasked to the weekly non-SPY lane — it is not part of this selection.)

---

## 2. Pre-flip verification (Day −1, same day as the flip decision)

All of these are checks, not actions. Every box must be checked before §3.

1. [ ] `go_live_gate.py` run fresh **today** — criterion 5 PASS (not INSUFFICIENT_DAYS) and
   criteria 2–4 PASS (§0). Criterion 1 remains a disclosure, not a blocker (§0).
2. [x] **Dead-man's switch built AND drilled at the "built" bar** — `setup/scripts/dead_mans_switch.py`
   shipped 2026-09-01, task `Gamma_DeadMansSwitch` (weekdays /2 min 09:32–15:58 ET), pytest
   13/13 green + RED-proofed (`STALE_MIN=999999` → 4 failed), gate criterion 2 shows PASS.
   **Still open — the live-drill bar, distinct from the built bar:** kill `Gamma_HeartbeatCore`
   mid-session with an open **PAPER** position **on safe-2 — the retiring arm, never the
   prod-shadow candidate (safe-3)** — ≥5 times across different times of day, and confirm the
   dead-man's switch flattens each within 12 minutes (broker-verified, not state-file-verified).
   This drill has not been run as of 2026-09-01; do not treat the built-and-unit-tested switch
   as equivalent to a field-drilled one.
3. [ ] safe-3's reconciliation is clean (§0 row 3, PASS) — no gap to root-cause for the
   candidate arm itself. (The 08-28 version of this item referenced a safe-3/risky-3
   reconciliation gap; that gap is closed per the 09-01 reconciliation re-run, and risky-3 is
   retired — see §1.)
4. [ ] **Options market-data tier confirmed for the live account: real-time, signed OPRA**
   (`Algo Trader Plus`, ~$99/mo) — not accepted-as-delayed. `analysis/data-tier/summary.json`
   (2026-09-01, 16:20 ET) shows all 4 paper arms currently on `option_opra_ok: false` /
   INDICATIVE (delayed trades, modified quotes); every historical paper fill and premium-floor
   check used this derived feed. Buying the live-account data tier does not by itself fix
   filter-10's SIP-ratified `vol_mult=0.7` running on IEX volume — that pairing is a queued
   post-freeze item (FABLE-FULL-AUDIT §4 item 3) and must land before this box is checked.
5. [ ] **Early-close calendar awareness shipped, both halves.** Verified live against Alpaca's
   broker calendar: 2026-11-27 and 2026-12-24 both close 13:00 ET. As of 2026-09-01,
   `heartbeat_core._is_rth` is a fixed clock (`weekday()<5 and 9.5<=h<=16.0`) with no calendar
   awareness, and `engine_health.market_is_open()` is holiday-aware but never called by the
   engine and discards the `close` field — a 0DTE opened before 13:00 on either date has no
   automated exit before expiry. Both halves must ship before this box is checked: (a)
   `calendar.json` persists the `close` field, (b) `_is_rth` / entry cutoffs / EOD-flatten
   become calendar-relative. Frozen file (`heartbeat_core.py`) — ships at 09-29 thaw, well
   ahead of 11-27.
6. [ ] **Broker-sweep-aware time stop ≤15:20 shipped.** Alpaca's own options docs (fetched
   live 2026-09-01): from 15:30 ET on expiry day Alpaca evaluates every expiring position and
   liquidates an ITM long the account cannot afford to exercise "while it's still ITM" —
   before our current 15:40 time-stop / 15:52 EOD-flatten. Prereg filed 2026-09-01:
   `prereg-time-stop-broker-sweep-2026-09-01.json` (`time_stop_et 15:40 → ≤15:20`). Must be
   shipped (not merely pre-registered) before this box is checked.
7. [ ] OPRA/real-time data tier confirmed (J) — this is the same tier decision as item 4;
   restated here as the explicit J-only purchase decision (Prohibited Actions: Claude does
   not buy subscriptions).
8. [ ] **Phone-reachable HALT drilled from J's phone.** BUILT 2026-09-01 (TASK B5-phone-halt,
   `setup/scripts/halt_command.py`): Discord `HALT <arm>` / `HALT ALL` / `HALT <arm> FLATTEN` /
   `RESUME <arm>` from J's allowlisted Discord account trips the per-account circuit breaker
   the engine actually reads — core arms via the root/aggressive `circuit-breaker.json`
   heartbeat_core's entry gate reads every tick, fleet arms via
   `automation/state/fleet/<arm>/circuit-breaker.json`, which fleet_live.py's
   `_load_or_arm_breaker` reads every `Gamma_FleetExecutor` tick (1 min) — and optionally
   flattens via `fleet_broker.close_all_spy_options(live=True)`, refusing FLATTEN outright on
   any failed broker read. pytest 52/52 green, RED-proofed. **Still open — the drill, distinct
   from the built bar:** no actual phone→Discord→inbox→responder round trip has been run yet,
   and `Gamma_DiscordResponder` is currently quiet-mode-disabled (self-restores ~23:00 ET) —
   more importantly, its scheduled-task trigger only fires 16:00–~09:30 ET (after-hours); it
   does **not** fire at all during 09:30–15:55 ET RTH today, so a phone HALT sent mid-session
   would sit unprocessed until the next after-hours tick. Drill from J's phone (ideally
   during RTH, to prove the real end-to-end latency) AND close the RTH scheduling gap before
   this box is checked. Queue item: `PHONE-HALT-COMMAND` (`automation/overnight/queue.md`).
9. [ ] **Whole-engine null study PASS on the frozen window.** Pre-registered 2026-09-01
   (`prereg-whole-engine-null-2026-09-01.json`, analysis-only, freeze-compatible): random
   entry times through `walk_exit_manager` on real OPRA, buy-ATM-call/put-daily baselines,
   opposite-direction, scored on post-08-11, frozen-window, and SPY-down days. As of
   2026-09-01 book P&L correlates +0.23 with SPY's daily return and the sample has never seen
   VIX >20.64 or a down day worse than −2.01% — "edge" and "long beta in a calm up-tape" are
   currently indistinguishable. This study must actually run and the engine must beat both
   nulls (95th percentile) *and* be positive on SPY-down days before this box is checked.
10. [ ] **After-tax target written.** SPY options are equity options — ordinary short-term
    gains plus wash-sale exposure at ~500 round trips/yr with same-day same-symbol
    re-entries (the wash-sale pattern by construction); no after-tax number exists yet and no
    CPA has been consulted. Write an after-tax version of the $100–200/day target before this
    box is checked. (XSP is Section 1256 — 60/40, wash-sale exempt, cash-settled, which also
    removes the 15:30-sweep/assignment risk in items 5–6 — evaluate it in the lab as a
    separate research item, not as a substitute for this box.)
11. [ ] **Duplicate-tick monitor clean 20 days.** The heartbeat task's fire-and-forget wrapper
    (`wscript → run_exe_hidden.vbs → pythonw`) defeats Task Scheduler's overlap guards
    (`MultipleInstances=IgnoreNew`); overlapping live ticks are ledger-proven (3 distinct
    `core_tick_id`s in one minute, 08-11; a −$371 duplicate-entry incident 08-14). Entries are
    now claim-locked; exits are not. A duplicate-tick monitor over `core-decisions.jsonl` is
    queued as the interim control until the pidfile-mutex + vbs fix lands (post-freeze,
    09-29). This box requires 20 clean monitored days, not just the monitor existing.
12. [ ] **Weekly / multi-day circuit breaker decided.** Only the weekly non-SPY lane currently
    has one; the core SPY arms do not. Decide (build or explicitly waive) before this box is
    checked.
13. [ ] `automation/state/fleet/secrets.json` gets a NEW entry (e.g. `safe-3-live`) with the
    live key/secret/base_url (`https://api.alpaca.markets`, not `paper-api`). The existing
    `safe-3` (paper) entry is untouched. Gitignored per CLAUDE.md secrets rule — never commit.
14. [ ] `accounts.json` gets a NEW arm row for the live account with `status: "paused"` and
    `live: false` — visible to tooling (accounts_status.py, go_live_gate.py) but not
    tradeable. This is a NEW row, not a mutation of the existing `safe-3` paper row.
15. [ ] Confirm PDT/margin status on the live account (Alpaca margin account by construction)
    and that day-trade counting is understood for the funding tier chosen.
16. [ ] Live Alpaca account exists, funded, and its API keys are **NOT** the paper keys — J
    creates the account and funds it (Claude cannot create accounts or move money; Prohibited
    Actions).
17. [ ] J has said, in chat, in this session or a fresh one, that arming is authorized. This
    is the ONLY step in this runbook that is not a technical check — it is OP-0 #1, and no
    quantity of green gates substitutes for it.

---

## 3. The flip (ordered, each step reversible on its own)

Every step here that sets `live: true` or `GAMMA_CORE_ARMED=1` is executed **by J**, not
Claude — Claude prepares, verifies, and reports; it does not flip the flag.

1. **Dry run, no orders.** Point the live account's credentials at a read-only connectivity
   check (`accounts_status.py`-style REST calls, `get_clock`/`get_account`/`get_option_chain`)
   for at least one full session. Confirm quotes are live/fresh, signed-OPRA (not the
   indicative feed flagged in §2.4). Zero orders placed.
2. **J flips the live arm's row to `status: "active"`, `live: true` in accounts.json** and
   sets `GAMMA_CORE_ARMED=1` scoped to that ONE arm only. The paper `safe-3` row is untouched
   and keeps running — the live and paper arms coexist as separate accounts, separate keys,
   separate state files.
3. **First trade watched live**, not left unattended — J present at the terminal, watching,
   touching nothing (the whole point of Day 1 is proving J's manual-intervention reflex does
   not fire — see the analyst finding on this pattern in `journal/mistakes.md`).
4. **Confirm the fill reconciles** same-day: run `go_live_gate.py`'s reconciliation criterion
   (or `accounts_status.py`) against the live account before market close.

---

## 4. First-week size ramp

No code in this repo currently ramps size automatically. The ramp below is a **manual,
temporary override** of the live arm's `min_contracts`, set by J, reverted to the configured
value only at the end of a clean Week 1. **No ramp step may require a config edit** — the
frozen/live `risk_gate.py` hard-denies below `MIN_CONTRACTS`, so the ramp starts at the floor
the code already enforces, not below it.

| Day | Contracts | Condition to proceed to the next row |
|---|---|---|
| Day 1 | **3** (the risk_gate floor: `MIN_CONTRACTS>=3` hard-denies 1) at **≤$0.50 premium** | No abort trigger (§5) hit. Reconciles same-day. |
| Days 2–3 | 3 | Day 1 clean. No manual override, no rule break. |
| Days 4–5 | up to 4 | Days 2–3 clean AND week-to-date P&L is not a new max drawdown vs the paper arm's own trailing distribution. |
| Week 2 | live caps: **5 contracts / $1,000 per position / $400 per day** | Week 1 completed with **zero** §5 triggers across all 5 days. |

The live caps ($1,000/position, $400/day, 5 contracts → worst trade ≈ $500, 9% of a ~$5.6K
account) are far tighter than Rules 5/6's doctrine text (30%/50% of equity) — protect the
caps, not the doctrine prose (`FABLE-FULL-AUDIT-2026-09-01.md` §3.1). Any single §5 trigger at
any point **freezes the ramp at the current size** (does not necessarily revert — see §5 for
which triggers demand immediate revert vs freeze-and-review).


### 4a. What month ONE actually looks like, in dollars (2026-09-02)

The gate answers *"is the edge real?"*. It does not answer the question a person asks before
turning on real money. This does. Day-level bootstrap, 20,000 ordered 20-day months resampled
with replacement over trading DAYS (trades within a day are correlated), 2c/contract exit
slippage plus the real OCC/ORF/TAF/SEC/CAT fee model. Ordered, because **max drawdown is a
path statistic** — two months with the same total differ in how deep they go.
Producer: `setup/scripts/first_live_month_model.py` → `analysis/first-live-month/<arm>.json`.

| arm | | P(month<0) | month p5 | month median | maxDD p95 |
|---|---|---|---|---|---|
| **safe-3** *(prod-shadow)* | uncapped | 0.322 | −$1,821 | +$651 | −$2,553 |
| **safe-3** | **with −$400/day cap** | **0.164** | **−$684** | **+$1,083** | **−$1,294** |
| safe-2 | uncapped | 0.577 | −$1,965 | −$217 | −$2,293 |
| safe-2 | with cap | 0.577 | −$1,965 | −$217 | −$2,293 |
| bold-2 | with cap | 0.379 | −$1,550 | +$349 | −$2,072 |
| risky-1 | with cap | 0.219 | −$1,213 | +$1,147 | −$1,947 |
| risky-3 | with cap | 0.374 | −$1,632 | +$428 | −$2,119 |

**Three things this says that nothing else on the board said.**

1. **The −$400/day cap is doing most of the work on safe-3.** It roughly halves the chance of
   a down month (0.322 → 0.164), cuts the 5th-percentile month by 62% (−$1,821 → −$684) and the
   95th-percentile drawdown by 49% (−$2,553 → −$1,294). The ramp in §4 above reaches that cap
   only in **Week 2** — so Week 1 runs in the *uncapped* column, where a bad month is −$1,821
   and a bad path is −$2,553, about **48% of a ~$5.3K account**.
2. **The cap has never bound on safe-2 — by $8.67.** safe-2's worst observed day is −$391.33
   against a −$400 cap, which is why its capped and uncapped rows are identical. The control is
   untested on that arm, not proven harmless on it.
3. **safe-3 is the better arm on this measure** (P(month<0) 0.164 vs safe-2's 0.577, median
   +$1,083 vs −$217), which is consistent with it being the designated prod-shadow arm — but
   see the limits below before reading that as a green light.

**Limits, and they are load-bearing.** A bootstrap cannot produce a day worse than the worst
day it was given, and every arm's history here is **calm-regime** — the gate discloses zero
days with VIX>20 and zero days down more than 1%. So every tail above is a **LOWER BOUND on a
stressed month, not a forecast of one**. Days are resampled i.i.d., discarding autocorrelation,
so if bad days cluster the real drawdowns are deeper. And none of this touches criterion 1,
which still FAILS on every arm (CI-lower 0.333–0.412 against a 1.0 bar): *this is what the
month looks like IF the edge is real, and the gate does not say it is.*

**Method cross-check.** The 2026-09-01 audit computed safe-2 independently and got
P(month<0)=0.55, p5 −$1,895, maxDD p95 −$2,225. This producer, written from the A1 bootstrap's
fee model but with its own path logic, gets **0.577 / −$1,965 / −$2,293** on the same arm —
agreement to a few percent on all three. The numbers above are reproducible, not a one-off.

---

## 5. Abort criteria — any ONE of these triggers §6 immediately, no discretion

- **A realized day loss of −$400** (the enforced live-caps daily bound — supersedes the old
  −30%-of-equity framing, which at this account tier is a much looser number than the caps
  actually enforce).
- **A single trade loses $500** (the live-caps per-position bound: $1,000/position at a ≤50%
  catastrophe-cap loss ≈ $500 worst case).
- **Any dead-man's-switch fire** — the switch flattening a position is a near-miss to log and
  abort on, not a recovery to shrug off; it means the primary process died with an open
  position, regardless of how fast the backstop worked.
- **Any Alpaca-initiated liquidation** (`OPEXC`/`OPASN`/`OPEXP` broker activity codes) — the
  15:30 ET broker expiration sweep (§2.6) acting on a position before our own exits did is the
  ITM-assignment risk materializing, not a benign fill.
- **Any unresolved escalation flag at premarket.** Since the 2026-09-01 kill-switch-wiring
  fix, `daily_loss_guard.rearm()` refuses to clear while an escalation is unresolved and
  `engine_health` goes CRITICAL on any escalation flag — an unresolved flag at premarket start
  is itself the abort trigger, not something to clear and continue past.
- **Any duplicate-tick-monitor RED** (§2.11) — a same-minute duplicate `core_tick_id` for this
  account is the overlapping-tick failure mode that produced the 08-14 −$371 incident.
- EOD-flatten fails to close a position for this account (broker-verified, not
  state-file-verified).
- Reconciliation gap (broker vs ledger, net of the known fee model) exceeds the same tolerance
  `go_live_gate.py` uses on this account on any day.
- J manually overrides, early-closes, or resizes a position outside the ramp table in §4 —
  logged as a behavioural-criterion trip even if it "worked."
- 2 or more rule breaks logged against this account in the trailing 5 trading days.

---

## 6. Revert procedure (ordered, reversible)

1. **HALT `<arm>` FLATTEN from the phone** (§2.8's Discord command) — the first action, before
   anything else, the moment any §5 trigger fires and J is not already at the terminal.
2. **J flips `live: false` / clears `GAMMA_CORE_ARMED`** for this arm immediately.
3. **Verify flat on the broker** (not the state file — C11: broker is the source of truth).
   If a position is still open, close it manually; do not wait for the next scheduled
   EOD-flatten tick.
4. **Leave the account funded and dormant.** Claude does not withdraw or transfer funds
   (Prohibited Actions) — if J wants capital pulled, that is J's own action in the Alpaca UI.
5. **Paper fleet is unaffected** — separate accounts, separate credentials, separate state
   files by construction (§2.13–2.14). No further action needed there.
6. **Post-mortem within the same session**: append the trigger and timeline to
   `journal/mistakes.md` (rule-break format) and, if it reveals a new failure class, fold an
   L## entry into `LESSONS-LEARNED.md` per OP-25. Re-run `go_live_gate.py` fresh — expect it to
   read a non-PASS criterion again on whichever the abort exposed; that is correct, not a bug.
7. **Re-entry to live requires re-running this entire runbook from §0** — a prior PASS does
   not carry over. The gate is re-run, not assumed.

---

## 7. What this runbook deliberately does NOT cover

- **Two-account live** — explicitly rejected in `ONE-ACCOUNT-TRANSITION-2026-08-18.md` §3
  (duplicate sample at r=0.846, doubled operational surface, no new information).
- **Automated size-ramp code** — §4's ramp is manual by design until it has been run by hand
  at least once; automating it before that is solving a problem that has not been observed yet.
- **The first-month drawdown shape.** For context (not a bar in this runbook), the retiring
  arm's own historical shape, from `FABLE-FULL-AUDIT-2026-09-01.md` §4 item 6 (20-day-month
  bootstrap, trade-level Kelly): **safe-2, all-history — P(month<0)=0.55, maxDD p95 −$2,225**;
  **safe-2, post-ladder-only — P(month<0)=0.21, maxDD p95 −$1,586**. These are safe-2's shape,
  not safe-3's — safe-3 is the actual live candidate (§1) and its equivalent bootstrap has not
  yet been computed; do not substitute safe-2's numbers for safe-3's when that computation
  lands. The previous version of this runbook cited "TASK A2" ruin figures whose source could
  not be located in this session — those are UNVERIFIED and have been replaced by the figures
  above, which are cited to the audit that re-derived them fresh.
- **Fixing the two remaining RED/FAIL gate criteria in §0** — that is separate build work
  (accumulating prod-shadow days to 20, and treating criterion 1 as a disclosure rather than a
  blocker per the §0 clock decision), tracked in `automation/overnight/queue.md` and the
  audit's §5/§7, not duplicated here.
