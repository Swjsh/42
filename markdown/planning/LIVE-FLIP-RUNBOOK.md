# Live-Flip Runbook — ONE account, real money

> Operational procedure only. No prose padding. This is a checklist, not an argument for
> going live — that argument (and the current answer) lives in `analysis/go-live-gate.json`
> and the TASK A1/A2/B2/C2 findings (2026-08-27/28). **As of 2026-08-28 the gate reads RED
> on 4 of 5 criteria** — see §0. Nothing in this document is a license to execute; it is the
> procedure to follow **once** the gate reads GREEN and J has said so in chat.
>
> Design context (why ONE account, why safe-2 first): `ONE-ACCOUNT-TRANSITION-2026-08-18.md`.
> Gate math this runbook is downstream of: `setup/scripts/go_live_gate.py`.
> Every step below that touches money, credentials, or the ARMED flag is J's action alone
> (OP-0 #1) — Claude executes the read-only/preparation steps and reports; it never flips
> live money on its own judgment, no matter how green the gate reads.

---

## 0. Current status (fresh 2026-08-28)

Run `backtest/.venv/Scripts/python.exe setup/scripts/go_live_gate.py` for the live number.
Snapshot at time of writing:

| Criterion | Verdict | Distance to green |
|---|---|---|
| 1. Statistical (CI-lower>1.0, all 5 arms, as-traded+ex-best-day+cost-adj) | **RED** | CI-lower sits at 0.17–0.30 vs the 1.0 bar on every arm (full trading history, not just August) |
| 2. Operational (guardrail tests pinned+green) | **RED** | Dead-man's-switch (heartbeat death with an open position) has NO test and NO independent watchdog — the one gap that blocks this group alone |
| 3. Reconciliation (ledger vs live broker equity, all 5 arms) | **RED** | safe-2/bold-2/risky-1 reconcile clean net of known fees; safe-3 (−$74) and risky-3 (+$231) do not — unexplained, needs its own investigation before either is trusted |
| 4. Behavioural (rule breaks / manual overrides, trailing 20 trading days) | **GREEN** | 0 rule breaks, 0 manual-attribution fills in window |
| 5. Prod-shadow (dedicated shadow arm net of costs) | **RED** | NOT_WIRED — no such arm exists yet, see gate JSON for detail |

**Do not start §2 below until this table reads all-GREEN in a run from that same day.**

---

## 1. Account selection

**Recommendation: safe-2 (`PA3POKNV46VG`, CORE-SAFE).** Not risk-free, just the least-bad
first pick:

- ATM strike selection (`V15_SAFE_TIERS`) is the simplest tier to reason about live — no
  strike-tier flip at $10k/$25k equity the way Bold's ladder has (L149/C29 — verify current
  equity keeps it on the ATM rung before flipping).
- Lowest max-drawdown-% in the 19-day observed window (12.77% vs bold-2's 15.73%,
  TASK A2 finding) — the metric that matters most for "will this trip J's $3k fear first."
- Matches the account's own doctrine intent (conservative-first, Rule 6 30% cap vs Bold's 50%).

**Counter-consideration, stated honestly:** TASK A2's compounding bootstrap found bold-2 had
*lower* ruin-risk (probability of ever seeing a ≥50% drawdown) over 12 months — 3.6% vs
safe-2's 12.4% — because bold-2's daily-return distribution happened to be less fat-tailed in
the observed sample. That is one 19-day sample; it is not strong enough to override the
max-DD-% and strike-simplicity case above. If J prefers bold-2, swap every "safe-2" below for
"bold-2" and re-derive the equivalent gate numbers — the procedure is identical either way.

**The other 3 arms (bold-2, safe-3, risky-1, risky-3) stay PAPER**, unchanged, per
`ONE-ACCOUNT-TRANSITION-2026-08-18.md` §3 — they remain the laboratory; the live account is
the product.

---

## 2. Pre-flip verification (Day −1, same day as the flip decision)

All of these are checks, not actions. Every box must be checked before §3.

1. [ ] `go_live_gate.py` run fresh **today** — GREEN on all 5 criteria (§0 table).
2. [ ] Dead-man's-switch built AND drilled: kill `Gamma_HeartbeatCore` mid-session with an
   open PAPER position, ≥10 times across different times of day, independent watchdog process
   flattens 100% of them within a stated bound (this is new build work — no such mechanism or
   test exists as of 2026-08-28, see `analysis/go-live-gate.json` →
   `criteria.operational.guards.dead_mans_switch_open_position_on_process_death`).
3. [ ] safe-3 and risky-3's reconciliation gaps (§0 row 3) are root-caused and closed, OR
   safe-2/bold-2's clean reconciliation is treated as sufficient because ONLY safe-2 is going
   live — state explicitly which justification is being used; do not silently ignore an
   unexplained gap on arms that stay paper.
4. [ ] Options market-data tier confirmed for the live account: real-time (`Algo Trader Plus`,
   ~$99/mo) or accepted-as-delayed with the risk stated in writing (TASK A1 HIGH finding —
   confirmed this session via a live 403 on SIP data with the paper keys; the live account's
   own tier has not been separately confirmed).
5. [ ] Live Alpaca account exists, funded, and its API keys are **NOT** the paper keys — J
   creates the account and funds it (Claude cannot create accounts or move money; Prohibited
   Actions).
6. [ ] `automation/state/fleet/secrets.json` gets a NEW entry (e.g. `safe-2-live`) with the
   live key/secret/base_url (`https://api.alpaca.markets`, not `paper-api`). The existing
   `safe-2` (paper) entry is untouched. Gitignored per CLAUDE.md secrets rule — never commit.
7. [ ] `accounts.json` gets a NEW arm row for the live account with `status: "paused"` and
   `live: false` — visible to tooling (accounts_status.py, go_live_gate.py) but not tradeable.
   This is a NEW row, not a mutation of the existing `safe-2` paper row — the two must be able
   to run side by side without either shadowing the other.
8. [ ] Confirm PDT/margin status on the live account (Alpaca margin account by construction —
   no cash-account product exists, per `REGULATORY-BROKER-LANDSCAPE-2026-08-18.md`) and that
   day-trade counting is understood for the funding tier chosen.
9. [ ] J has said, in chat, in this session or a fresh one, that arming is authorized. This is
   the ONLY step in this runbook that is not a technical check — it is OP-0 #1, and no
   quantity of green gates substitutes for it.

---

## 3. The flip (ordered, each step reversible on its own)

Every step here that sets `live: true` or `GAMMA_CORE_ARMED=1` is executed **by J**, not
Claude — Claude prepares, verifies, and reports; it does not flip the flag.

1. **Dry run, no orders.** Point the live account's credentials at a read-only connectivity
   check (`accounts_status.py`-style REST calls, `get_clock`/`get_account`/`get_option_chain`)
   for at least one full session. Confirm quotes are live/fresh and NOT the delayed feed
   flagged in §2.4. Zero orders placed.
2. **J flips the live arm's row to `status: "active"`, `live: true` in accounts.json** and
   sets `GAMMA_CORE_ARMED=1` scoped to that ONE arm only. The paper `safe-2` row is untouched
   and keeps running — the live and paper arms coexist as separate accounts, separate keys,
   separate state files.
3. **First trade watched live**, not left unattended — J present at the terminal, watching,
   touching nothing (see §4 Day 1 and the TASK B2 finding on J's own WeBull intervention
   reflex — the whole point of Day 1 is proving that reflex does not fire).
4. **Confirm the fill reconciles** same-day: run `go_live_gate.py`'s reconciliation criterion
   (or `accounts_status.py`) against the live account before market close.

---

## 4. First-week size ramp

No code in this repo currently ramps size automatically — `min_contracts` is a flat
per-account config (TASK A2/B2 finding: the capital curve is flat from $5k to $250k on the
core path). The ramp below is a **manual, temporary override** of the live arm's
`min_contracts`, set by J, reverted to the configured value only at the end of a clean Week 1.

| Day | Contracts | Condition to proceed to the next row |
|---|---|---|
| Day 1 | 1 | No abort trigger (§5) hit. Reconciles same-day. |
| Days 2–3 | 1 | Day 1 clean. No manual override, no rule break. |
| Days 4–5 | 2 | Days 2–3 clean AND week-to-date P&L is not a new max drawdown vs the paper arm's own trailing distribution. |
| Week 2 | configured `min_contracts` (3) | Week 1 completed with **zero** §5 triggers across all 5 days. |

Any single §5 trigger at any point **freezes the ramp at the current size** (does not
necessarily revert — see §5 for which triggers demand immediate revert vs freeze-and-review).

---

## 5. Abort criteria — any ONE of these triggers §6 immediately, no discretion

- Daily loss kill-switch trips (Rule 5, −30% of start-of-day equity for this account).
- A single trade hits the −50% catastrophe cap.
- EOD-flatten fails to close a position for this account (broker-verified, not
  state-file-verified) — this is the ITM-assignment risk materializing.
- The heartbeat process is silent (no tick) for >5 minutes during market hours with this
  account holding an open position, REGARDLESS of whether the dead-man's-switch (§2.2)
  recovers it — a recovery is a near-miss to log, not a pass.
- Reconciliation gap (broker vs ledger, net of the known fee model) exceeds the same tolerance
  `go_live_gate.py` uses ($10 or 2% of the day's broker P&L, whichever is larger) on this
  account on any day.
- J manually overrides, early-closes, or resizes a position outside the ramp table in §4 —
  logged as a behavioural-criterion trip even if it "worked," per standing doctrine (a winning
  trade that broke a rule is still a mistake).
- 2 or more rule breaks logged against this account in the trailing 5 trading days.

---

## 6. Revert procedure (ordered, reversible)

1. **J flips `live: false` / clears `GAMMA_CORE_ARMED`** for this arm immediately — first
   action, before anything else.
2. **Verify flat on the broker** (not the state file — C11: broker is the source of truth).
   If a position is still open, close it manually; do not wait for the next scheduled
   EOD-flatten tick.
3. **Leave the account funded and dormant.** Claude does not withdraw or transfer funds
   (Prohibited Actions) — if J wants capital pulled, that is J's own action in the Alpaca UI.
4. **Paper fleet is unaffected** — separate accounts, separate credentials, separate state
   files by construction (§2.6–2.7). No further action needed there.
5. **Post-mortem within the same session**: append the trigger and timeline to
   `journal/mistakes.md` (rule-break format) and, if it reveals a new failure class, fold an
   L## entry into `LESSONS-LEARNED.md` per OP-25. Re-run `go_live_gate.py` fresh — expect it to
   read RED again on whichever criterion the abort exposed; that RED is correct, not a bug.
6. **Re-entry to live requires re-running this entire runbook from §0** — a prior GREEN does
   not carry over. The gate is re-run, not assumed.

---

## 7. What this runbook deliberately does NOT cover

- **Two-account live** — explicitly rejected in `ONE-ACCOUNT-TRANSITION-2026-08-18.md` §3
  (duplicate sample at r=0.846, doubled operational surface, no new information).
- **Automated size-ramp code** — §4's ramp is manual by design until it has been run by hand
  at least once; automating it before that is solving a problem that has not been observed yet.
- **Fixing the 5 RED criteria in §0** — that is separate build work (dead-man's-switch,
  safe-3/risky-3 reconciliation root-cause, prod-shadow arm design), tracked wherever this
  session's C2 findings land, not duplicated here.
