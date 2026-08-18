---
name: alpaca-paper-reset
description: Re-fund an Alpaca PAPER arm. Alpaca REMOVED reset — the only mechanism is delete + create-new, which J must do himself (Claude cannot create accounts or handle keys). Claude does everything around it: pre-checks, roster mapping, rewiring, verification.
---

# alpaca-paper-reset

Bring a starved paper arm back to a working premium ceiling.

## ⛔ READ THIS FIRST — "reset" no longer exists

Alpaca's own docs (verified live 2026-08-02 via `search_alpaca_docs` → `us/paper-trading`):

> *"We've updated the dashboard to allow you to **create and delete** paper accounts, **rather than
> resetting them**."* … *"Don't forget to generate new API keys for any newly created account."*

There is **no reset button and no reset API endpoint** (`search_alpaca_api_specs` for reset/balance
returns only `PATCH /v2/account/configurations`, which cannot change equity). The docs also state:
*"You cannot change the account balance after it is created."*

**Consequence: re-funding = DELETE the account + CREATE a new one.** That yields a NEW account
number and NEW API keys, and every config surface must be rewired. This is the same operation that
caused the 2026-07-10 accidental-deletion incident and forced the safe-2 repoint.

### Division of labor (non-negotiable)
| Step | Who |
|---|---|
| Delete a paper account | **J** — permanently deleting data |
| Create a new paper account | **J** — Claude does not create accounts |
| Generate / copy API keys | **J** — Claude never handles key values |
| Everything else below | **Claude** |

This split holds even in the paper sandbox and even when J says it's fine — it is a standing limit,
not a risk judgement. Do not re-litigate it; just do the large part that IS Claude's.

## Is churning the account even necessary? (ask this FIRST)

Two independent levers decide whether an arm can trade. Diagnose which one binds before deleting
anything — account churn is expensive and often not the actual constraint.

1. **WHICH strike gets picked** — `crypto/lib/strike_selection.py` tier tables, keyed on equity.
   - `V15_SAFE_TIERS` is **ATM on both sides of $2,000** → for an arm on this table the $2K boundary
     is a **no-op** and funding changes nothing about strike choice.
   - `V15_BOLD_TIERS` is OTM-3 below $2K, OTM-2 above → the boundary is real here.
   - `V15_BOLD_CORE_TIERS` is **ATM below $10K** (ATM-TIER-EXTENSION-2K-10K 2026-08-04; was $2K) — strictly better for floor clearance.
   - Fleet arms resolve via `fleet_executor._tiers_for_arm`: risky-* by id-prefix and safe-3 by an
     explicit `params_patch.strike_tier_table="bold"` all land on the BOLD table. Evidence
     (`analysis/recommendations/bold-strike-axis-2026-07-15.json`): OTM-3 clears the $0.30
     min-premium floor on 34% of afternoon signals vs ATM's 97%, ATM +$28.77/tr OOS.
   - **So repointing the tier table is a free, revertible, evidence-backed alternative to funding**
     for the strike half of the problem. Queue item: `FLEET-STRIKE-TIER-ATM-EXTENSION`.
2. **WHETHER the chosen contract is affordable** — the premium ceiling, `equity x risk_cap /
   (min_contracts x 100)`. Only equity moves this. Run
   `python setup/scripts/sizing_deadlock_diag.py` for the live table.
   Targets: **$2,500 → a $2.50 ceiling** for both shapes (safe 30%/3ct, bold 50%/5ct), which covers
   the full typical ATM 0DTE band of $1.30–2.50. $2,000 gives only $2.00 AND sits exactly ON the
   `[2K,10K)` tier boundary (`pick_tier` is half-open: $2,000.00 already resolves upward), so
   **$2,500, never $2,000** — guard-pinned by
   `backtest/tests/test_reset_plan_tier_boundaries_2026_08_01.py`. If that suite is RED the target
   is stale; re-derive before acting.

**Rule of thumb:** if the tier table is the binding problem, fix the table. Only churn the account
when the *premium ceiling* is what's starving the arm.

## Live roster — VERIFY, the Alpaca labels lie

Alpaca's UI labels drift from our arm names (a repoint renames our side, not theirs). Always map by
**account number**, never by the label shown in the switcher. Source of truth:
`automation/state/fleet/accounts.json`; canonical view `python setup/scripts/accounts_status.py`.

**Corrected 2026-08-18** (account-identity alignment audit): every row below except crypto twin was
still showing its PRE-2026-08-02-wipe account number -- and the Safe-1/Safe-2 row was never even
correct at that, a documentation-only error separate from the wipe (see
`analysis/deep-research/ACCOUNT-IDENTITY-ALIGNMENT-2026-08-18.md`). Account numbers below are
re-verified against `automation/state/fleet/accounts.json` as of 2026-08-18. The Alpaca UI **label**
column is NOT re-verified -- five of six accounts were deleted and recreated 2026-08-02, so any
custom dashboard nickname from before that date may no longer apply. Re-check the switcher by
**account number**, never by a remembered label, per the section below.

| Alpaca label | Account # | Our arm | Login |
|---|---|---|---|
| *(re-verify live)* | PA3POKNV46VG | **safe-2** (CORE Safe) | swjsh.chief |
| *(re-verify live)* | PA32T7Q1O20H | safe-3 (fleet) | swjsh.chief |
| "crypto" | PA38EG1JTFBT | **crypto twin — DO NOT DELETE** | swjsh.chief |
| *(re-verify live)* | PA3WEBXJU67N | bold-2 (CORE Bold) | jack.watergun |
| *(re-verify live)* | PA3S9N1IV0A4 | risky-1 (fleet) | jack.watergun |
| *(re-verify live)* | PA3V7JT25H6Z | risky-3 (fleet) | jack.watergun |

⛔ **The crypto twin is never re-funded.** It runs 24/7, carries the organic ladder A/B and 155+
lifetime orders of evidence continuity, and deleting it destroys a running experiment. It also sits
near $9.8K — it has no funding problem. If a flow ever proposes touching it, stop.

## Flow

### Claude — before
1. `python setup/scripts/accounts_status.py` — live equity for every arm.
2. `python setup/scripts/sizing_deadlock_diag.py` — premium ceilings; identify which arms are
   actually starved. **Prioritize by ceiling, not by convenience.**
3. Verify the target arm is **FLAT** (no positions, no open orders) — deletion destroys history:
   ```python
   import sys; sys.path.insert(0, "automation/state/fleet")
   import fleet_broker as fb
   c = fb.load_creds()["<arm>"]          # NOTE: load_creds() takes NO arguments
   print(len(fb.open_spy_option_positions(c)), len(fb.open_buy_orders(c, None)))
   ```
4. Record the OLD account number and equity so the rewire is auditable.

### J — the dashboard part
5. Account switcher, **upper-left corner** of the dashboard (shows current account + "Paper - PAxxx").
6. Delete: switcher → **Account Settings** → find the account → **Delete Account**.
   (The "Delete Account" button on the portfolio card deletes the account you are *currently in* —
   confirm the switcher shows the intended account number first.)
7. Create: switcher → **Open New Paper Account** → set the starting balance to **$2,500**.
8. Generate API keys for the new account and put key+secret straight into the gitignored store —
   `automation/state/fleet/secrets.json` (fleet arms) or the project-root `.mcp.json` (core arms).
   Never paste keys into chat; never hand-transcribe them.

### Claude — after
9. Read back the NEW account number via the API and confirm equity == $2,500.
10. Rewire every surface: `accounts.json` (account_number + starting_equity), `secrets.json` /
    `.mcp.json` entry names, `accounts_status.py` BASELINE, and any doc quoting the old number.
    `git grep` the OLD account number to prove zero stragglers.
11. **Reload the MCP server** for a rewired core arm before verifying — a stale key returns 401 and
    looks like a broken account.
12. Rerun `sizing_deadlock_diag.py`; confirm the ceiling is $2.50.
13. **PDT provenance**: a new account has no day-trade history. Check the PDT gate does not inherit
    the old account's count (this exact bug was fixed once already — see the PDT provenance task).
14. **Breakers**: start-of-day equity caches are load-bearing for the kill switch. A weekend/
    pre-08:30 change self-heals via the premarket re-arm; a MID-SESSION change needs the forced
    re-arm in `analysis/deep-research/RESET-PLAN-2026-08-01.md` §7 step 4B — a stale low SoD makes
    the kill switch far too loose on the new bankroll.
15. Note it in STATUS.md and update this table if labels changed.

## Known drift
Alpaca redesigns periodically, and it already removed the reset flow this skill was originally
written for. If the described controls are missing, `read_page` the dashboard, locate controls by
text, and confirm the context unambiguously says PAPER before anything destructive. Update this file
in the same session — a skill that documents a flow the vendor deleted is worse than no skill.
