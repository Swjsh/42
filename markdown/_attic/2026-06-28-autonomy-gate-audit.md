# Autonomy Gate Audit — 2026-06-28

> J: *"full audit on every single autonomous piece of r&d… we need the engine to self-improve…
> we have it built, make it auto."* This is that audit + what got closed in the same pass.
> Method: 5 parallel sub-agents (Sonnet) traced each subsystem; every claim re-verified against files.

## The loop (what self-improves now)

```
research (kitchen 24/7 + grinders, 144k tested) → real-fills/OOS/A-B validation
   → conductor / Gamma_Drive emit a proposal
       · doc/lesson fold ............... auto-ships (OP-25 path)
       · validated trading edge ........ auto-ships (OP-11 path: eval_bar_cleared + scorecard)
       · un-validated change ........... DRAFT + ping J  (waits)
   → autonomy_actuator: auto-approve → snapshot → SAFETY GATE → commit  (J = REVOKE)
   → params.json flag / staged-challengers.json  → engine trades it on PAPER
   → [ARM live = J's switch, untouched]
```

The **apply hop had never once fired** before tonight — that was the headline gate.

## Gates found, and disposition

| # | Gate | Verified state | Action this pass |
|---|------|----------------|------------------|
| 1 | **Apply hop** — actuator "never self-approves", waited on human `ship <id>` | REAL — 0 applies in the loop's life | **CLOSED**: `auto_approve_pending()` (OP-25 doc folds + OP-11 eval-cleared edges). Fired: 3 lessons auto-folded, gate caught 2. |
| 2 | **Apply loop never self-clears** — chained folds stuck at `needs_structured_apply` | REAL — 8 stuck | **CLOSED**: `drain_already_applied()` closes no-op duplicates; genuinely-stale held (not guessed). |
| 3 | **Research→deploy** — no validated trading edge ever became an applyable proposal (op11 path dormant) | REAL — Rail-4 routed ALL params changes to "wait for J" | **CLOSED**: conductor.md ships params deploys that clear the FULL bar; actuator re-verifies the scorecard (wf≥0.70 / OOS+ / anchor-no-regression) before applying. Reward-hack hole closed. |
| 4 | **Gamma_Drive** (nightly opus "drive like J" loop) disabled | REAL — Disabled + a stop-flag was dropped | **CLOSED**: stop-flag removed, task re-enabled (Ready). Fires 20:00 ET, hard-capped $8/fire, off-switch intact. |
| 5 | Reviewer glob strands grinder outputs | **NOT a real bug** — grinder files are named `*chef-nemo-grinder*` (glob catches them); leaderboard has 166 lines (promotions happening). Agent erred. | None — left as-is (changing it would risk a regression). |
| 6 | `Gamma_SelfAudit` "never ran" | **NOT a real bug** — the "1999" was a sentinel; it's firing 17:30 ET (3 runs logged). | None. |
| 7 | G4 vwap_continuation enabled-but-not-routed to `_execute` | REAL — dead knob on live path | **Open** — recency-gated; conductor can auto-arm once `license_monitor` greens. Next. |
| 8 | 7 genuinely-stale doc folds + 2 op25-baseline-RED folds | REAL (low value) | Held — need re-authored apply_ops (lesson-author's job). |

## What STAYS human (correct gates — OP-25 fail-open)

- **`GAMMA_CORE_ARMED`** (shadow→live placement) — set only in `run-heartbeat-core.ps1`. The deploy chain never touches it.
- **Fleet `live:true`** per paper account + `SCORING_PEAK_LIVE` — J flips to activate live REST arms.
- **Alpaca key rotation**; **EOD-flatten 3-fail manual fallback** (0DTE expiry emergency).

## Shipped this pass (all on `main`, each one-tap revertible)

`7b74ed3` auto-approver · `0756ec3` self-clearing drain · `d7f0a7b` research→deploy + scorecard verification ·
plus `b8aa15f/a2feb86/f558314` (3 lessons auto-folded by the loop itself). Gamma_Drive re-enabled.

Every fix carries a graduated guard (`backtest/tests/test_autonomy_auto_approve.py`) that REDs on regression.
