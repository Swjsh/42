# MULTI-LANE END-TO-END FIDELITY AUDIT — why "nothing is going on" (2026-08-20 night, Fable)

> **J's ask:** *"It's in its infancy… nothing going on. How are we looking at the charts? How are
> we analyzing them? How are we replicating as best we can what the profitable SPY engine is
> doing? Audit it end to end, then come up with plans for an Opus worker to run."*
>
> Method: fresh evidence pulls this session (call sites, live-engine input assembly, today's
> 216-row ledger, filter semantics), not recall. Every claim below carries its source.

---

## VERDICT

**The fork is faithful CODE running in an unfaithful WORLD.** The scoring engine was copied
correctly — scale-invariance proven, AST-verified clean — but it is being fed a context so
starved relative to production that 178/178 HOLD is the *arithmetic* consequence, not a market
condition and not bad luck. Three of its four context inputs are literally `None`.

One sentence: **we copied the brain and forgot the eyes.**

Severity ranking of what makes the lane inert:

| # | Root cause | Severity | Evidence |
|---|---|---|---|
| 1 | **Timeframe + cadence mismatch** — fork evaluates 1-HOUR bars every 15 min; production evaluates **5-MINUTE** bars every minute | 🔴 fatal to signal frequency | `multi/core.py fetch_bars(timeframe="1Hour")`; `build_shared_signal.py:679` "the closed **5m** trigger bar"; task defs |
| 2 | **Starved context** — `vix_now/vix_prior/vix_5d_ma/vix_20d_ma`, `htf_15m_bars`, `level_states`, `fhh_level` all default None/0.0 | 🔴 fatal to filter behavior | `multi/core.py:496-498` passes ONLY bars + levels; production rows carry `vix`, `htf_15m`, level states (`build_shared_signal.py:112,143,675`) |
| 3 | **Hold-model identity error (mine)** — I built the multi lane as a MULTI-DAY lane (min_dte 3, days-to-live 3), inherited from the weekly lane *whose signal died its null-gate death*. J's directive is the **intraday** SPY machine pointed at more names | 🔴 strategic | `automation/state/multi/params.json entry/exits`; J verbatim: "copy what the profitable spy engine is doing" |
| 4 | **Blocker blindness** — shadow rows carry scores but NOT the blocker list, so "why did it HOLD" requires manual probes | 🟡 diagnostic | HOLD-row keys pulled tonight: no `blockers` field |
| 5 | Quote endpoint 400 masquerading as "no quote" | ✅ fixed last night | commit + lesson filed |
| 6 | OI is `None` on the indicative feed → `min_open_interest` gate can never bind (silently passes) | 🟡 dead knob (C14) | tonight's NVDA quote: `open_interest: None`, volume present |

## The fidelity matrix — what production has vs what the fork gets

| Input | SPY live engine | Multi lane today | Faithful? |
|---|---|---|---|
| Bar timeframe | **5m**, closed-bar discipline | **1H** | ❌ 12× coarser |
| Evaluation cadence | every 1 min (~78 evaluable bars/day) | every 15 min (~6.5 bars/day, each seen 4×) | ❌ ~12× fewer trigger opportunities |
| VIX now/prior/5d/20d | live, every tick | `None/0.0` | ❌ |
| HTF 15-minute stack | computed, feeds soft-demerits | `None` | ❌ |
| Level STATES (reclaim/reject memory) | persisted, refreshed intraday | `None` | ❌ |
| Levels themselves | curated `key-levels.json` + intraday refresher + multi-day memory + trendlines | auto swing/prior-period/round from 1H bars | 🟡 partial (breadth-forced, but no memory, no trendlines) |
| Scoring code (0–11, ribbon, ATR tolerances) | v15 filters | faithful fork, scale-invariance proven | ✅ |
| Exit shapes | v15.3 premium mechanics | forked, theta-ordering added | ✅ (unvalidated values, labeled) |
| Hold model | intraday, flat 15:50 ET | multi-day, no weekend | ❌ different business |
| Sizing/risk | 30%/min-3/kill-switch | forked, multi-position aware | ✅ |

**Why 178/178 HOLD follows arithmetically:** a bear entry needs F5 (ribbon BEAR-stacked) AND F6
(ribbon spread ≥ floor) AND F9 (breakdown bar with volume, `vol_baseline_20`) AND F10 (a
level-tied trigger on the CURRENT bar) with zero blockers. On 1H bars the ribbon stacks/unstacks
~12× slower, breakdown-bar volume texture is a different animal, and "trigger on the newest bar"
gets ~6 chances/day instead of ~78 — while HTF/VIX context that production uses is absent
entirely. Multiply those probabilities and a zero-entry day is the expected outcome even if the
edge were real. **This is C15 (gates interact multiplicatively) meeting a 12× timebase error.**

## What today's clean-ish data actually said (post quote-fix caveat)

216 rows: 178 HOLD (all at `action_directional`), 37 liquidity blocks (the now-fixed 400), 1
position-state bootstrap row. The 178 HOLDs are **uninterpretable as strategy evidence** until
roots #1–2 are fixed — they measure the starved context, not the market.

## What is genuinely GOOD and should not be rebuilt

- The fork itself (scale-invariant scoring, symbol-relative tolerances) — the hard part, done.
- The funnel (72→≤5 by ranking, never thresholding) + participation cascade — kept L199 visible.
- Crypto-safety, creds-by-reference, account-mismatch refusal, no-order-path AST guards.
- Exits with theta-before-catastrophe ordering; atomic position state; multi-day journal schema.
- Scanner stack (movers/actives/news/RVOL) feeding attention — verified moving the ranking.
- 301+ tests with RED-proof discipline; six real bugs already caught by running.

**None of the workpackages below rewrite these. They complete the world around them.**

---

## Ranked kill-list (what NOT to do)

1. ❌ Do not tune filter thresholds to make 1H bars fire. That optimizes the wrong timebase into
   looking alive — the exact "translated-but-unapplied knob" family (C14) wearing a new coat.
2. ❌ Do not bolt more scanners on. Candidate discovery is not the bottleneck; context is.
3. ❌ Do not ship paper orders before the intraday null gate runs. The weekly lane earned that
   rule the hard way.
4. ❌ Do not blend this lane's evidence with SPY's or the crypto twin's. Standing doctrine.

## Hand-off

The build plan for an Opus worker: `markdown/planning/OPUS-WORKPACKAGE-MULTI-LANE-2026-08-20.md`
— six ordered workpackages with specs, acceptance criteria, and guards. WP-0/1/2 are the
fidelity fixes (timebase, context, identity); WP-3 restores diagnosis; WP-4 is the evidence gate;
WP-5 is the paper-order path, gated on WP-4.
