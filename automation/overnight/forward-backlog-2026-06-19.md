# Forward backlog — post all-night-loop (2026-06-19)

> The high-value BOUNDED work is done (16 commits, blueprint Waves A-D + loop cycles 1-6). What remains is DELIBERATE-FUTURE / conductor-appropriate / J-gated work — NOT 2am-grind. Ranked by leverage. The conductor (once enabled) or the next deliberate session drains this.

## Tier 0 — the strategic priority (from tonight's research)

- [ ] **EXIT/REGIME refinement of BEARISH_REJECTION** (HIGH, the #1 leverage). Tonight's research (#22/#23/#26) converged hard: the mean-reversion bounce family is dead/anti-edge, and `BEARISH_REJECTION_MORNING` (J's confirmed PUT-winner setup) is the ONLY entry that fires WITH J's edge (real-fills +$134/+$197 on 4/29). The full-window real-fills collapse is an EXIT/REGIME problem, not entry-selection. Focus engineering on: when to ride vs cut (the chart-stop win is the first step), regime gates (VIX character, ribbon state), and the sub-pockets where it's +EV. This is where the money is. Research -> propose (Rule 9).

## Tier 1 — finish the decision-library migration (the architectural north star)

- [ ] **Decision-lib Phase 3** (MED). engine/score.py (P1) + engine/gates.py (P2) are extracted + parity-locked. Next: build `engine_cli.py` (stdin/stdout shim so the live heartbeat can call the engine) + start the N>=5-trading-day READ-ONLY shadow (reuse shadow-version.json controller). The shim is bounded/safe now; the shadow window is calendar-bound. Per markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md.
- [ ] **Decision-lib Phase 4** (J-GATED). Live cutover: heartbeat consults engine verdict via the shim; prose collapses to a thin wrapper; codegen retires gamma-sync. ONLY after Phase 3 shadow agrees >=99% (100% on ENTER ticks). Rule 9 / J revoke.

## Tier 2 — unblock + decide

- [ ] **Production ★★★ key-levels archive** (MED). The watcher real-fills validations (#22/#23/#26) are all on synthetic ★★ PDH/PDL proxies — no historical archive of the production ★★★ levels J draws. This understates the level-keyed setups' true edge. Building a rolling key-levels archive would let watcher validation use real levels (and may change the RETIRE verdict for BRM, which missed 5/04 on proxies).
- [ ] **Watcher-fleet RETIRE decision** (J review, Rule 9). The bounce family (floor_hold_bounce, close_ceiling_fade, named_level_second_test) is conclusively dead-as-tradeable under every tested exit/regime/inversion (scorecards: watcher-exit-sweep.json, bounce-family-rescue.json). Propose formal retirement to WATCH_ONLY-archive so they stop consuming engineering. J approves.

## J-ratification queue (Rule 9 — surface in the next brief)
- Bold kill-switch threshold: aggressive breaker -60% vs Rule-5/params -50% — which is canonical?
- Safe chart-stops change goes LIVE Monday (premium -0.50 catastrophe cap, chart-stop primary) — review markdown/research/CHART-STOPS-2026-06-18.md.
- Enable (when ready): Gamma_HealthBeacon, Gamma_Conductor, Gamma_DiscordResponder (install scripts wired, not auto-enabled).
