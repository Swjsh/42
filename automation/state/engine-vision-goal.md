# ENGINE-VISION BUILD — make the engine SEE what J sees (J: "the engine's blind, build all this shit out")

**Started:** 2026-07-08 ~08:30 ET (J directive, premarket). The engine is blind to the
market-structure reads J does naturally (verified 08:25 live: key-levels.json had 5 stale
late-June levels; no multi-day memory / trendline / gap / clustering wired). Build them.

**Engine keeps trading while this builds** — verified the live engine is pure Python (system
pythonw, run-heartbeat-core.ps1), armed (GAMMA_CORE_ARMED=1), fires 09:30-15:55 ET, reads SPY
via REST (no TV/CDP/pool dependency). My interactive coding does NOT starve it. Both accounts
FLAT (no NOT_FLAT block). So I build here while the engine runs its own session.

## OPERATING RULES (every iteration)
1. `et_clock` each iteration for logging; but market-hours is NOT read-only here (engine is
   pool-independent — J explicitly authorized building through the session).
2. Every build is ENTRY-PATH (it changes what the engine sees/enters). So each ships with:
   a **red-proofed guard** + an **A/B validation** (does adding this vision help or add noise?
   real-fills / OOS where possible) + **REVOKE note** + path-scoped commit + pre-commit gate
   PASS or revert. **Do NOT blindly add a level source or remove a gate without the A/B** — more
   entries != better (last night's whole lesson). A kill is a valid outcome.
3. If a build can't be cleanly validated in-session -> ship the DETECT/LOG/ALERT half (notify-
   only, safe) and mark the ENTRY-feed half NEEDS-REVIEW (like G11). Awareness ships even when
   the entry-wiring needs J.
4. Update this file + STATUS each item. Commit each. Surface real status (OP-33).

## QUEUE (ordered; `[ ]`todo `[~]`wip `[x]`done `[B]`blocked)
- [ ] V0 F1-GATE A/B (trade-today unblock) — `min_ribbon_momentum_cents=0` ARMS a "disabled" gate that blocks Safe entries on a contracting ribbon (fired 29x live). Run the on/off A/B through the REAL engine on real fills: does removing it improve edge capture or was it protecting us? If removing helps -> disable (null) + guard + REVOKE (unblocks entries TODAY). If it protects -> keep, relabel, mark F1 resolved-as-correct. **Decision by data, not by "J wants trades."**
- [ ] V1 MULTI-DAY LEVEL MEMORY (live) — wire `level_memory.py` -> `key-levels.json` so the engine sees: (a) multi-day memory-weighted levels (the 739.50 "bounced here last Thursday" read), (b) remembered rejection/dump levels (747.43), (c) candle-bottom CLUSTERS as zones (746.0/745.98/746.12). = G11 + validation. TRAP: filter-10 entry blast radius + the contradictory-role foot-gun (one polarity/price, dedup at producer). A/B the ENTER set (extra/missed + real-fills) before wiring to entries; ALERT half already ships (G5 emit_reject_alert).
- [ ] V2 GAP-FILL AWARENESS — J: "gaps always get filled." (a) Fix the DEAD prior-close feed (recovered-audit F22/F25: gap_and_go 100% SKIP_NO_FEED, prior_rth_close_unavailable). (b) Emit unfilled overnight-gap levels into key-levels as magnet/target levels the engine reads. A/B whether gap-target levels improve entries/exits.
- [ ] V3 LIVE TRENDLINE READS — wire `trendline_engine.py` (exists, NOT on the live path) into the tick so the engine sees drawn/auto trendlines (J's trendline) as levels + a rejection veto/trigger. A/B the trendline signal (it's a CALL-veto per the trendline memory; validate as trigger separately).
- [ ] V4 LEVEL-REJECTION -> CONTINUATION — the "jacked off 746.10 and keeps dumping" read. `level_memory.emit_reject_alert` (built G5) fires the ping; add the rejection-continuation SETUP (reject a high-memory level -> enter continuation with the level as stop). A/B on real fills; honest prior: ribbon_rejection_wick was already killed (0/24 BH-FDR) — this is the LEVEL-memory variant, validate fresh, don't assume.

## TRADE-TODAY WATCH (engine's own session — visibility, not build)
- Engine: armed + fires 09:30 ET + FLAT. fill_funnel + self_check emit status (alert delivery
  fixed last night G5). J gets a ping if it enters / if a real break occurs.
- HONEST: 0 reconciled fills EVER (G9). Removing F1 (V0) + adding vision (V1-V4) raises the odds
  a setup fires + isn't blocked, but the placement->fill gap is separate. Watching the funnel.

## PROGRESS LOG
- 2026-07-08 08:30 ET: engine verified armed/firing/flat/pool-independent; TV relaunched; F1 confirmed still blocking. Bowl created (V0-V4). Looping.
