---
name: alpaca-paper-reset
description: Drive the Alpaca dashboard (browser) to reset paper-account equity — J signs in first, Claude clicks through the reset for each account. No API exists for this.
---

# alpaca-paper-reset

Reset one or more Alpaca PAPER accounts to a target equity via the dashboard, because
**Alpaca has no public API endpoint for paper reset** (verified 2026-07-31; the reset
button is dashboard-only).

## CHOSEN TARGETS (2026-08-01 normalization — WS12)

**$2,500 per SPY arm** (safe-2, bold-2, safe-3, risky-1, risky-3); **crypto twin NOT
reset**. Full rationale + the dry-run-proven post-reset runbook:
`analysis/deep-research/RESET-PLAN-2026-08-01.md`. Short form: $2,000 sits EXACTLY ON the
[$2K,$10K) strike-tier boundary (`pick_tier` is half-open — $2,000.00 already resolves the
upper bracket, $1,999.99 the lower), so $2,500 lands every arm cleanly INSIDE [2K,10K)
with $500 of buffer and a $2.50 premium ceiling (= covers the typical ATM band $1.30–2.50;
at $2,000 the ceiling is $2.00 and refuses the band's top). Boundary assumptions are
guard-pinned by `backtest/tests/test_reset_plan_tier_boundaries_2026_08_01.py` — if that
suite is RED, this target is stale; re-derive before resetting. Dashboard fallback: if the
reset dialog refuses a custom amount, use $2,000 exact (same tier, zero buffer — disclose
in STATUS).

## Preconditions — hard rules
1. **J must already be signed in** to https://app.alpaca.markets in the browser pane.
   Claude NEVER touches the login form, never types credentials, never handles 2FA.
   If a login screen appears at any point: STOP and tell J.
2. PAPER accounts only. If the UI context suggests a LIVE account anywhere in the flow,
   STOP immediately — do not click anything — and report.
3. Reset destroys open positions and order history on that paper account. Verify the
   account is FLAT first (positions via MCP) and warn J if it is not.

## Accounts (roster as of 2026-07-31 — verify against fleet/accounts.json, it drifts)
| Arm | Account # | Where |
|---|---|---|
| safe-2 (CORE-SAFE) | PA3DHPT7KIQE | primary login's paper account list |
| bold-2 (CORE-BOLD) | PA33W2KUAT40 | same |
| safe-3 / risky-1 / risky-3 | PA32RD49OB0Q / PA3W17FD8G19 / PA31WIU8X15Q | fleet accounts — may live under the same login's paper-account switcher |
| crypto twin | PA38EG1JTFBT | separate creds — usually NOT reset (24/7 evidence continuity; ask J first) |

## Flow (per account)
1. `tabs_context` → confirm an app.alpaca.markets tab exists and J is authenticated
   (read_page shows the dashboard, not a login form).
2. Use the paper-account switcher (top-left account dropdown in the classic layout) to
   select the target account number. `read_page` to confirm the account number shown
   matches the target — never trust position on screen alone.
3. Open the account/gear menu → "Reset Paper Account" (wording has varied:
   "Reset account", "Reset paper trading account"). If a target-equity input is offered,
   enter J's requested amount (standing choice **$2,500** per RESET-PLAN-2026-08-01 —
   supersedes the old bare-$2,000 default, which sits exactly ON the [$2K,$10K) tier
   boundary; CONFIRM the number with J once per session, not per account).
4. The confirm dialog is an IRREVERSIBLE-class click → this skill runs only when J has
   asked for the reset in this session; restate the account number + amount in one line
   before clicking confirm.
5. After reset: verify via MCP (`get_account_info` for core arms / `accounts_status.py`
   for fleet arms) that equity matches the target. Screenshot as proof.
6. Repeat for the next account. Final step: run
   `python setup/scripts/accounts_status.py` and report the table.

## After all resets
Follow `analysis/deep-research/RESET-PLAN-2026-08-01.md` §7 — the executable, dry-run-
proven runbook (equity verify, deadlock diag, breaker/SoD handling, annotation updates,
STATUS note). Highlights:
- Rerun `python setup/scripts/sizing_deadlock_diag.py` and confirm every arm's ceiling —
  at the $2,500 target expect **$2.50 every arm** (proven `--equity 2500`); at a $2,000
  fallback expect $2.00 (still binding for premiums >$2; tell J the number).
- Note the reset in STATUS.md (equities are load-bearing inputs to risk math).
- Breakers: weekend/pre-08:30 reset self-heals (premarket `daily_loss_guard.rearm()` +
  fleet date-rollover re-arm). MID-STREAM reset needs the forced re-arm in the runbook's
  step 4B — a stale low SoD makes the kill switch far too LOOSE on the new bankroll.
- Update `fleet/accounts.json` `starting_equity` annotations + `accounts_status.py`
  BASELINE (runbook step 6), and reconcile bold-2's multiplier/pdt_gate_mode (step 5).

## Known UI drift
Alpaca redesigns periodically. If the described controls aren't found: read_page the
whole dashboard, find reset affordances by text search ("reset"), and proceed only when
the control's context unambiguously says PAPER. Update this file when the flow changes.
