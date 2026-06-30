# Roadmap: from "parts + demos" → "autonomous + trading"

> J 2026-06-29: *"What are we working on now? What's next? Let's NOT rush it — break it down
> methodically, everybody's got their own tasks, so we're not trying to do it all at once."*
>
> **Principle:** one owner per phase, each phase GATED on the prior (no skipping ahead), no
> fake timelines — order-of-operations only. Phase 0's self-check makes every later phase
> VISIBLE + verified, so we never again think something's running when it crashed.

## The honest starting point
We have **tools that work when run, but mostly run by hand**, and **no validated edge to
trade** in this regime. The gap is three things: (a) wire the tools into loops that run
themselves, (b) find a validated edge, (c) J can see all of it without asking. (c) is done.

---

## Phase 0 — STICK + VISIBLE  ✅ (this session)
**Owner:** `Gamma_SelfCheck` (autonomous, every 30 min) + Gamma.
- `self_check.py` verifies the ACTUAL work (not exit codes) → STATUS.md + Discord on
  DEGRADED/BROKEN, GREEN = silent. `gamma_status.py` = on-demand human view.
- Killed the em-dash silent-crash class (23 `run-*.ps1` BOM-swept + `test_run_ps1_ascii_or_bom`).
- **Exit (watch for):** self-check runs clean across several real fires; J reads state without asking.

## Phase 1 — Wire the research pipeline into the autonomous kitchen  (task #10)
**Owner:** Gamma builds the wiring · `kitchen_daemon` runs it · the smart-review gate
(shadow-scored vs Gamma, <85% = Gamma-in-loop) filters.
- design-swarm + discovery-ledger + FDR become a kitchen task-chain (generate → review → run)
  that runs ITSELF, instead of me invoking it.
- **Gated on:** Phase 0 (so we SEE it running).
- **Exit:** the kitchen autonomously emits FDR-screened candidates to
  `analysis/recommendations/`, visible in `gamma_status`.

## Phase 2 — Grow the validated inventory 2 → 6  (task #11)
**Owner:** `chef` (R&D) generates + validates · Gamma reviews each (OP-33 in-loop) ·
`treasurer` sizes per arm.
- Push candidates through the design-swarm: the discovery survivors (incl. the **regime-gated
  rejection edges** — short rejections in high-VIX, fade-long in low-VIX), J's documented
  winners (4/29, 5/01, 5/04 — validate the *population* not the anchors), the SwjshAK reservoir.
- Each survivor (OOS-stable + beats null + anchor-clean) → `strategies.py` → assigned to arm(s).
- **Gated on:** Phase 1 (the autonomous pipeline produces the candidates).
- **Exit:** 3–6 validated strategies on `strategies.py`, each on an arm — the 6 arms trade
  DIFFERENT strategies under different gates/regimes, not the same 2.

## Phase 3 — The Reframe Engine / meta-loop  (task #12) — runs in PARALLEL
**Owner:** Gamma (Opus, weekly `Gamma_StepBack`) · `friction_distiller` (nightly) feeds it ·
`conductor` routes {infrastructure} reframes, `_chef-inbox` gets {strategy-frame} ones.
- The Constraint Provenance Audit on the top recurring friction (currently `regime_dependence`,
  222 days). This is Pipeline 2 (Opus, rare) — HARD-separate from Phases 1–2 (free swarm).
- Independent of the others; it questions the FRAME while they work the box.

## Phase 4 — TRADE (the goal)
**Owner:** `pilot` / `heartbeat_core` executes · Gamma + J arm.
- When ≥1 validated edge exists AND an arm is populated → the engine trades it (paper first;
  **live arming needs J** — OP-0 #1).
- **HARD GATE:** a real validated edge. We don't have one in this regime yet — the discovery
  engine found regime-gated candidates; they need real-OPRA-fills confirmation (Phase 2) first.
- **Exit:** the engine takes validated trades; J sees them in `gamma_status`.

---

## Ownership at a glance
| Phase | Driver | Autonomous component | Gate |
|---|---|---|---|
| 0 Stick+Visible | Gamma | `Gamma_SelfCheck` | ✅ done |
| 1 Wire pipeline | Gamma | `kitchen_daemon` chain | Phase 0 |
| 2 Inventory 2→6 | `chef` + Gamma + `treasurer` | the kitchen pipeline | Phase 1 |
| 3 Reframe loop | Gamma (Opus) | `friction_distiller`→`Gamma_StepBack` | parallel |
| 4 Trade | `pilot` / `heartbeat_core` | the engine | validated edge + J arms |

**We do not skip ahead.** A phase isn't "started" until its gate is GREEN, and each is owned
by one driver so we're not doing it all at once. The self-check is the through-line: every
phase reports its real state, so "is it running?" is answered by `gamma_status`, not by asking me.
