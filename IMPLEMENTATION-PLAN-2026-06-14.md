# Project Gamma — Staged Implementation Plan
**Date:** 2026-06-14 · Companion to DEEP-REVIEW + DOCTRINE-CONSOLIDATION · **Status:** executing

Reversibility-first, methodical, staged. Each stage is independently committable with a validation gate (in-process, not wall-clock) and a rollback.

## Decisions locked (J)
- OP-11 self-improvement loop = TOP priority: build + test + validate in-process this effort.
- OP-16 = re-enable edge_capture floor, recalibrated to real-fills.
- OP-22/25 → "compound, don't accumulate" + footprint caps.
- Part A (8 OPs) approved; lesson collapse approved; graduation work = 2nd, right after OP-11.

## Judgment calls made autonomously (J away 2026-06-14)
- **GitHub push needs J auth** → all commits local; push deferred to J with exact command.
- **Secrets** → gitignore `.mcp.json` (keeps live auth working, keys never enter history); scrub only the *stale/dead* embedded keys from tracked `heartbeat.md`. No change to working key values.
- **OP-11 reproducer** → "staged-not-applied" REVOKE model (read-only on production state); fixture window chosen from cached real-fills data incl. a known anchor day.
- **OP-16 floor** → I run the real-fills measurement and set a recommended floor from data; documented for J to REVOKE.
- **Stage 5 (live params C3 fix)** → applied only after OP-11 validates, with before/after backtest + git revert path (weekend window, paper, reversible).
- **Windows-only steps** (Task Scheduler wiring, disabling crypto tasks, PS execution) → I author scripts; J runs them (Linux sandbox can't touch Windows Task Scheduler).

## Stages
0. **Reversibility & secret scrub** — gitignore secrets+venvs+data hoards, scrub stale keys, `git init`, baseline commit. Gate: `git grep` finds no keys; `git ls-files` count sane.
1. **Doctrine consolidation** — CLAUDE.md → 8 OPs + 18-lesson index; OP-E rewrite; full prose stays in LESSONS-LEARNED.md. Gate: net deletion, no dangling Lxx refs.
2. **OP-11 in-process reproducer** (TOP) — stage synthetic candidate → per-bar dual eval (`shadow.py`/`orchestrator`) → EOD diff scorecard → auto_ratify verdict → staged params bump w/ REVOKE → rollback. Gate: `pytest test_op11_loop.py` green, offline, deterministic.
3. **Graduate 8 lesson families to assertions** — look-ahead, dead-knob, pythonw path, premium-stop, rate-pool sentinel, broker-drift, silent-zero-obs, unreachable-tiers. Each ships a negative test. Re-run Stage 2 after.
4. **Re-enable OP-16 floor** — recalibrate from real-fills measurement; gate: production passes, known-garbage fails.
5. **Reconcile params.json C3** — v15.3 body vs version; cross-account rule_version; stronger pin-check. Gate: before/after backtest explains every behavior change. (Kill-switch-sensitive; weekend only.)
6. **Freshness watchdog + fail-open guard** — slim STATUS header; guard fails OPEN, exempts J's interactive session, self-expires. Gate: fail-open regression test (BLOCK impossible).
7. **Crypto → pre-merge gate + footprint caps** — retire 24/7 grinder, keep crypto/lib, prune ~1.5 GB, OP-G caps. Gate: dry-run trace before any disable/delete.

**Final:** push coordination (J auth) + full-history secret re-scan.

Full rationale, file refs, risks, and per-stage detail: see chat plan from the Plan architect (this doc is the executable summary).
