# GOAL: ENGINE-VISION-2026-07-08

> J verbatim (2026-07-08 ~08:30 ET, premarket): "the engine's blind, build all this
> shit out."

**FOLDED 2026-08-29 (OP-22)** from the pre-`/goal`-schema original at
`automation/state/engine-vision-goal.md`, which is now a tombstone pointing here.
Reformatted-not-rewritten copy. **ARCHIVED / TERMINAL — `active-goal.json` does not
point here.**

## DONE-WHEN
(Reconstructed retroactively.) The engine gains multi-day level memory, gap-fill
awareness, live trendline reads, and level-rejection detection — each shipped as
DETECT/ALERT (safe, notify-only) at minimum, with the ENTRY-feed half either A/B-
validated and shipped or explicitly held `[B]` NEEDS-REVIEW pending supervised A/B.
A KILL verdict on an entry-setup hypothesis (backed by direct evidence, not assumed)
counts as DONE-WHEN met for that item.

## OPERATING RULES
1. `et_clock` each iteration for logging; market-hours was NOT read-only for this
   goal specifically — J explicitly authorized building through the session because
   the live engine (pure Python, pool-independent) does not share context with
   interactive Claude.
2. Every build is entry-path (changes what the engine sees/enters): red-proofed
   guard + A/B validation (real-fills / OOS where possible) + REVOKE note + path-
   scoped commit + pre-commit gate PASS or revert. More entries != better — no
   blind level-source addition or gate removal without the A/B.
3. If a build can't be cleanly validated in-session, ship the DETECT/LOG/ALERT half
   (safe, notify-only) and mark the ENTRY-feed half NEEDS-REVIEW.
4. Update this file + STATUS each item; commit each; surface real status (OP-33).

_(2026-08-29 addendum, current-schema clauses postdating this goal: CONFIG FREEZE
2026-08-31→~09-29 on trading-path changes; `conductor_outcome.py record` per fire;
`model:"sonnet"` on every fan-out; STATUS.md at OPEN/CLOSE only.)_

## QUEUE
- [x] V0 F1-GATE A/B — `min_ribbon_momentum_cents=0` disabled (was arming a supposedly
    "disabled" gate, blocking Safe entries on a contracting ribbon, fired 29x live).
    A/B: removing it recovered a +$585 cohort (n=14, survives slippage) = J's
    big-down-day-put edge. Guard red-proofed. Engine unblocked for the open.
- [x] V1 MULTI-DAY LEVEL MEMORY (producer) — `level_memory.py` → `key-levels.json`:
    multi-day memory-weighted levels, remembered rejection/dump levels, candle-
    bottom clusters as zones. Live-captured J's exact levels (747.41≈747.43,
    746.7≈746-zone, 745.88≈745.98).
- [x] V1b schedule the level_memory producer — `Gamma_LevelMemory` every ~10min RTH,
    hidden pythonw chain, verified firing.
- [x] V1c wire consumers — reject-ping on a memory-level rejection (30-min dedup,
    notify-only); dashboard/self-check display the memory map.
- [B] V1-entry NEEDS-REVIEW (= G11 from the overnight-improve goal) — merging memory
    levels into LIVE key-levels.json (filter-10 entries) needs a supervised A/B, not
    an unvalidated in-session ship.
- [x] V2 GAP-FILL AWARENESS — fixed the DEAD prior-close feed (100% SKIP_NO_FEED);
    emits unfilled overnight-gap levels as magnet/target levels.
- [x] V3 LIVE TRENDLINE READS (shadow) — `trendline_engine.py` wired to
    `trendlines-live.json`, `Gamma_Trendlines` scheduled (5min RTH, verified). Entry-
    wire (veto/BOS trigger) left NEEDS-REVIEW.
- [x] V4 LEVEL-REJECTION → CONTINUATION — DETECT/ALERT ships via V1c. Entry setup
    **KILLED** by direct evidence: all 4 ribbon_rejection variants failed incl.
    SELECTIVE + exitgrid + holdgrid. Level-memory keying inherits the kill (the
    selective battery already proved it doesn't rescue this family). Mechanism:
    directionally right, theta kills the option (C3).
- [x] Vtrade OP-33e instrument — `Gamma_TradeToday` (every 2min RTH) pings J on the
    engine's first SPY-option fill; verified firing.

## J-DECISIONS
(none explicitly deferred beyond V1-entry, which is a `[B]` NEEDS-REVIEW rather than
a `[B-J]` — the DETECT/ALERT half already ships safely; only the entry-feed wiring
needed a supervised A/B.)

## PROGRESS LOG
- 2026-07-08 08:30 ET: engine verified armed/firing/flat/pool-independent; TV
  relaunched; F1 confirmed still blocking. Queue created (V0-V4).
- 2026-07-08 08:44 ET (V0 DONE): F1 disabled, +$585 cohort A/B, guard red-proofed.
  Engine unblocked for the open.
- 2026-07-08 08:56 ET (V1 producer DONE): live-captures J's exact levels. Shadow-only
  (safe). Follow-ups queued.
- 2026-07-08 09:01 ET (V1b DONE, verified firing): 12 levels, exit 0.
- 2026-07-08 09:12 ET (V1c DONE): reject-ping wired, verified (747.41 reject).
- 2026-07-08 09:22 ET (V2 DONE): prior_rth_close derived from timestamped bars
  (751.31) → dispatch fallback resolves it (was 100% SKIP_NO_FEED).
- 2026-07-08 09:31 ET (Vtrade DONE, market OPEN): OP-33e instrument built, verified
  firing.
- 2026-07-08 09:40 ET (V3 DONE, shadow): trendlines visible engine/dashboard-side.
  Entry-wire NEEDS-REVIEW.
- 2026-07-08 09:44 ET (V4 DONE — KILL, measured): all 4 rejection-continuation
  variants failed. **ENGINE-VISION BUILD COMPLETE.**

## HONEST STATE
Terminal as of 2026-07-08 ~09:44 ET. Market dumped SPY 747.8→743.99 (-3.8pts/13min,
J's bearish call) during this window: 28 ticks, ALL HOLD, 0 ENTER. **F1-off + gap-
alive + vision did NOT make the engine enter a clear dump** — the entry frontier
remained gated elsewhere (structure_veto, RED-book, no discrete trigger on a grind-
down). 0 fills that session. This goal shipped vision + visibility + one blocker fix
(F1); entry-wiring was explicitly left as the next, separate fight — check current
repo state before assuming V1-entry is still unshipped.
