# FABLE FULL-PROJECT REVIEW — 2026-08-29

> Fable 5 judgment session, J-directed ("full fable 5 review on entire project… advise based on facts and data… how do we start trading futures and other stocks… I want to be making money before next year").
> Clock verified at start: `2026-08-29 11:36:02 Saturday EDT / market_hours=False` (`et_clock.py`).
> Method: MAP→HOME→SHADOW→gate orientation, fresh `go_live_gate.py` re-run (11:42 ET), two Sonnet fact-pack fan-outs (per-arm economics; expansion lanes), every number below quoted from a source produced or re-run THIS session. Judgment-suite ch. 04 discipline applied.
> **This document arms nothing.** Live-money arming stays J's decision alone (OP-0 #1).

---

## VERDICT — one paragraph

The machine is excellent; the edge is not yet proven. On the freshest gate (re-run today, 4-arm roster): **P(book edge ≤ breakeven) = 37%**, every arm's PF CI-lower sits at 0.29–0.41 vs the 1.0 bar, and removing ONE day (2026-08-04) flips the whole 42-day book to **−$2,240**. But August's broker-verified window is genuinely better (+$3,660 across the 4 surviving arms over 20 sessions), the post-08-10 stop-ratchet era runs **$200/session vs $4/session before it**, and the losing arm's mechanism is identified. The credible path to real money before January is: **fix the mis-specified live threshold, freeze the config, score a clean September window with the gate, and if it clears, J arms ONE small live account in October.** Expansion (futures/other symbols) is not a 2026 money source: five lanes are already built and running, and **every non-SPY signal tested so far has failed its own null** — the blockers are signals and two narrow J-unlocks, not machinery.

---

## 1. The measured truth (fresh gate, 2026-08-29 11:42 ET)

`setup/scripts/go_live_gate.py` re-run this session (yesterday's copy had a stale operational FAIL from the risky-3 retirement breakage — re-verified: `test_eod_flatten_coverage_2026_08_18.py` → `8 passed`).

| Criterion | Verdict | Detail |
|---|---|---|
| 1. Statistical | **FAIL** (all 4 arms) | CI_lo: safe-2 0.292 · bold-2 0.358 · safe-3 0.356 · risky-1 0.412 (bar: >1.0 on as-traded AND ex-best-day AND cost-adjusted). Book rollup CI [0.40, 3.25], **P(PF≤1)=0.372** |
| 2. Operational | **FAIL** (1 of 6) | 5/6 guards PASS. Only gap: **dead-man's-switch** — no independent watchdog flattens an open position if the engine process dies. `NO TEST FOUND`, confirmed a real unclosed gap, not a missing test |
| 3. Reconciliation | **PASS** | 08-03..08-28 broker vs ledger, fee-adjusted diff ≤ $0.97 on every arm |
| 4. Behavioural | **PASS** | 0 rule breaks, 0 manual/mixed fills in 20-day window |
| 5. Prod-shadow | **FAIL** | NOT_WIRED — no designated go-live shadow arm exists |

**Broker-verified August P&L (window 2026-08-03..08-28, 20 trading days), per account first per doctrine:**

| Arm | Broker P&L | ≈/day | Last-10-sessions expectancy | Trend |
|---|---:|---:|---:|---|
| safe-3 | **+$852.70** | $43 | **+$51.32/trade** (WR 50%, n=22) | 📈 improving sharply |
| risky-1 | **+$1,495.12** | $75 | +$20.92/trade (n=39) | ➡️ stable positive |
| bold-2 | **+$749.47** | $37 | +$21.92/trade (n=25) | ➡️ stable positive |
| safe-2 | **+$563.04** | $28 | **−$1.91/trade** (n=22) | 📉 deteriorating |
| risky-3 | −$254.34 | — | −$19.40/trade | ⛔ retired 2026-08-28 (correct call — see §2) |

Sources: gate output (this session), `analysis/recommendations/live-readiness.json` (re-run 11:39 ET), `automation/state/fills-ledger.jsonl` mined via `fills_fifo.mine_real_arm_fills` (engine-attributed only).

**The two honesty anchors that must frame every read of the table above:**

1. **Concentration.** Ex-best-day (2026-08-04, book +$3,624 that day) the 42-day book is **−$2,240**; bold-2's entire lifetime profit is smaller than its share of that one day; 7 of the top-20 all-time winners in `analysis/winner-autopsies/SIGNATURE.md` come from 08-04 alone. This one-day dependence has been disclosed since the 08-06 week order ("Tuesday was 98.3% of gross") and is exactly what the gate's ex-best-day view exists to price.
2. **No statistical proof yet.** No arm clears |t|>2 on expectancy at current n. The last two green days (+$1,893.79 / +$1,301.00) were checked for a config cause: **no engine-path commit landed 08-26/08-27** — they were favorable tape hitting already-validated setups. Real, but regime-dependent; two days don't change the CI.

---

## 2. What's working, what isn't — mechanisms, not vibes

**Working (keep, protect):**
- **The right-tail exit machine.** Exits ≥1.3× entry premium are 26% of fills but carry **$23,236 of $24,879** total winner dollars (SIGNATURE.md, 517 fills / 128 waves). Median loser dies at 0.82× — small. The engine's shape is "lose small often, get paid on impulse legs," and the chandelier/structure-stop doctrine measurably beats the alternatives it was tested against.
- **The post-08-10 `pre_tp1_ladder` era.** Wave WR 22.5%→37.5%, net **$4/session → $200/session** (34 pre vs 14 post sessions). SIGNATURE.md itself labels this directional, not ratified — but it's the single best evidence the machine is improving rather than drifting.
- **Structure stops over premium stops — now with a natural experiment.** 08-28: bold-2 and risky-3 bought the *identical* 773C 65 seconds apart; bold-2 (`stop_mode=structure`) rode it to +195%, risky-3 (`stop_mode=premium`) stopped out −19% two minutes later. That head-to-head plus the lifetime bleed (−$676, WR 26%) is what retired risky-3. Data-driven kill, correctly executed, account already repurposed to weekly-1.
- **Ops integrity.** Reconciliation to the cent on all arms; 0 rule breaks in the window; the overnight conductor fires closed a FULL-SUITE RED, a 1.7GB/day disk leak, and a 2-month silent free-model outage in the last 48h. The quiet-mode weekend blackout examined this session is **working as designed** (114 tasks restore at 23:00 ET tonight; trading chain exempt).

**Not working (attack, in order):**
1. **safe-2 is the drag, and the mechanism is identified but unproven.** Its exit profile is registry CORE — TP1 at +100%, which accounts.json's own doc calls "effectively unreachable on 0DTE." So safe-2 structurally rides winners round-trip back to losses; risky-1's `exit_patch {tp1_premium_pct: 0.5, stop_mode: structure}` is the one shape that converts moves into banked partials. Proxy evidence: +$1,050 delta in risky-1's favor on 25 shared ribbon signals (`analysis/recommendations/tp1-r50-readjudication-2026-08-23.md` Part 3) — **never isolated as a single-variable A/B. That A/B is this weekend's #1 pre-registration** (§6, item 3).
2. **The live threshold in CLAUDE.md measures a strategy we don't run** — full §3.
3. **Two go-live plumbing gaps** — dead-man's-switch (build) and prod-shadow designation (decide + wire). Both closeable this weekend by fires; neither needs new research.
4. **Weekly synthesis cadence lapsed.** The last WEEK ORDER is 2026-08-10 (written 08-06). Three weeks of armed-state changes live only in STATUS/queue scroll. Revive the Thursday synthesis.
5. **Silent non-placements in the futures mirror.** 8 real-order attempts since 08-20, 0 confirmed placements, **7 rows with no reason logged** — a C7 violation inside a lane that reports itself "armed."

---

## 3. The doctrine contradiction blocking "live" — needs J this weekend (Rule 9)

`CLAUDE.md:65` live threshold: *"≥ 20 trades, WR ≥ 45%, positive expectancy, ≤ 2 rule breaks."*

The engine that actually emerged — through honest kills of every scalper-shaped alternative — is a **low-WR right-tail machine**: arm WRs run 24.4–35.9% lifetime (live-readiness, re-run today), while each arm's *breakeven* WR given its payoff shape is 23–35%. A 45% WR bar would only ever pass a strategy this project has repeatedly killed; meanwhile it fails arms that are genuinely profitable (safe-3: WR 30.5% lifetime, +$26.97/trade expectancy since 08-03). **The bar measures the wrong shape.** The instrument that measures the right thing already exists and already runs: `go_live_gate.py`'s day-level bootstrap PF criterion with ex-best-day and cost-adjusted views.

**Proposed rewording for J to ratify (weekend, in writing, per Rule 9)** — replace the CLAUDE.md:65 threshold with:

> **Live threshold (per account independently):** go-live gate GREEN — day-level bootstrap **PF CI-lower(2.5%) > 1.0 on as-traded, ex-best-day, and cost-adjusted views** over ≥20 scored trading days, PLUS operational guards green, reconciliation green, 0 rule breaks in window, and the designated prod-shadow arm green net of costs. Measured only by `setup/scripts/go_live_gate.py`. (WR remains a diagnostic, not a bar.)

This is *stricter* than the old bar where it matters (it prices concentration and costs) and honest where the old bar was wrong (it doesn't demand a WR the payoff structure never needed. J's actual historical failure mode — the WeBull −$17K pattern — was averaging-down and oversizing, both already guarded by code; no part of that protection is loosened by this change.)

---

## 4. Futures and other symbols — the honest state of every lane

J's ask: "how can we start doing more like trading futures and other stocks that are not just SPY." Answer: **we already are — five lanes are built and running.** What's missing is not machinery. Full fact pack cross-validated against ledgers this session:

| Lane | Status | Evidence to date | The one blocker | Owner |
|---|---|---|---|---|
| **Futures — MES mirror** | Shadow + technically armed since 08-20, 0 fills | 94 round trips, **+$2,102**, positive expectancy — but **fails its null**: same-horizon ES buy-and-hold made ~$24K (bull tape; being long anything won) | `beats_null: false`; plus 7/8 order attempts refused with **no reason logged** | Claude (log fix + null keeps scoring) |
| **Futures — tastytrade sandbox (real fills)** | Auth intermittent; verdict muddled | A real MES fill **did** happen 2026-08-09 (`SCHEDULED-TASKS.md:154`); since then `is_futures_approved:false`, and the 08-27/08-28 "H1_PERMISSIONS" verdicts are **ReadTimeouts mislabeled by a fallback else-branch** in `futures_broker_probe.py:110-126` | Contradictory evidence: one real fill vs approved:false vs an uncited "cert env is equities-only" claim | Claude first (fix probe taxonomy + auth flakiness, then ONE real small test order); **J fallback**: check tastytrade dashboard, or open free Tradovate demo |
| **Futures — edge #3 (MES→MNQ divergence)** | Accruing | 13/20 round trips, mean $24.22 vs validated $71.46; verdict at 20 trips (needs ≥$35.73 mean to avoid INVESTIGATE_QUOTE_QUALITY) | 7 more round trips | Nobody — pure accrual |
| **Futures — SSR shadow v2** | Accruing, dying | 11 round trips, **−$2,280**, worse than its own losing null | Needs a sign flip + 9 trips; heading for a clean kill | Nobody — let the clock kill it |
| **Weekly options (GLD/QQQ), arm weekly-1** | Account wired, **zero trades by design** | `PA3V7JT25H6Z` ($4,283.92, ex-risky-3, confirmed in accounts.json). Signal v1 **dead** (all 4 expiry arms fail the random-entry null, −8% to −14% mean); daily-trigger variant **refuted worse** (−23%) | **No signal has cleared a null.** Machinery deliberately unscheduled until one does | Claude — new trigger *family* (both kills say the current family detects volatility, not direction; a third timeframe rescale is banned by its own history) |
| **Multi-symbol options (multi-1)** | Stopped-not-dead | 7,489 signals / 9 symbols failed the null at every horizon (STAGE-A verdict 08-20); read-only telemetry still accrues; **harness preserved** to adjudicate any future signal in one session | Same as weekly: signal, not machinery | Claude/P1 swarm |
| **Kalshi — weather lane** | Live daily, 0 trades | 7 cities, ~19 predictions each, best city **n=15/20** scored days; bar = 20 days AND hit≥45% AND MAE≤1.6°F | ~5 more settled days; **then J's API key + RSA .pem** (only J can do this) | Accrual now; **J** for the key |
| **Trendline shadow** | Accruing daily | 4,786 event rows through 08-28; last computed verdict (08-20): +0.041 SPY pts/trade, above null, **CI [−0.039, +0.124] straddles zero**, top-3 sessions >100% of profit | CI + concentration; also verdict 9 days stale — recompute | Claude (recompute), then accrual |

**The doctrine line for expansion (unchanged, and the data this week re-earned it):** every non-SPY lane that has run a null test has failed it. These lanes are **edge-search**, not income. The only instrument with a live positive point-estimate and a path to real money in 2026 is the SPY 0DTE core. New symbols/instruments get capital the same way SPY did — by surviving pre-registered kills — and the harnesses to run those kills in a single session now exist for options-on-anything, futures, and event contracts. That IS the expansion program working; three dead signals in three weeks is the system saving money, not failing.

---

## 5. "Making money before next year" — the dated, honest plan

**Where money actually stands (all paper):** 4 active arms ≈ $23.7K combined equity; August pace +$183/day book-wide ($28–75/day per arm vs the $100–200/day/account RATIFIED target — not there yet at this tier, and the target's own doctrine says scaling comes from compounding tiers, not more trades).

**The plan (each step gated by evidence, not the calendar):**

| When | What | Bar |
|---|---|---|
| **This weekend (08-29/30)** | J ratifies §3 threshold rewording + one-account consolidation (§5 ROADMAP, r=0.846 says the fleet is one bet in five sizes — consolidating for live is the RECOMMENDED move and directly serves the money goal). Fires close the two gate gaps (dead-man's-switch build; prod-shadow designation) and freeze the prereg for safe-2's exit A/B. **Config freeze declared** for the scoring window: no trading-path changes except pre-registered kill-type risk reductions | Written, committed |
| **Sep 1 → ~Sep 29** (Mon 08-31 start; 20 trading days, Labor Day 09-07 out) | The clean scoring window. Engine runs untouched; gate re-scored weekly (add trailing-20td recency view per J's recency doctrine); prod-shadow arm accrues net-of-cost | Gate criterion: **PF CI_lo > 1.0 on all three views** on at least the go-live candidate arm(s) |
| **Early October** | If GREEN → J arms **ONE** live account at the current tier (OP-0 #1, J's call alone, `LIVE-FLIP-RUNBOOK.md`). If RED → another window; **no arming on a red gate, period** (Rule 10 exists for exactly this moment) | Gate GREEN |
| **Oct–Dec** | Live compounding at validated size; paper fleet continues as the laboratory; tier ladder governs scale-up | Recency-confirmation stays CONFIRM |

**Expectation-setting, no sugar-coat:** if September confirms, "making money before next year" is real — live fills with real dollars in Q4, plausibly tens of dollars a day at the entry tier, compounding from there. **$100–200/day per account is the ≥$5K-tier outcome of that compounding, realistically 2027-Q1 territory, not a Dec-31 state.** And if the window scores like July did, the correct amount of real money deployed on this edge is $0 — the gate saying so is the product working. What makes January *money* possible at all is that the evidence machine (gate, preregs, reconciliation, shadow clocks) is already built; the only missing input is 20 clean days.

---

## 6. Ranked actions (queued for the maintenance-band fires; J items marked)

1. 🔧 **DEAD-MANS-SWITCH** (HIGH, build): independent watchdog task — if the engine process is dead while a position is open, flatten via broker REST. Closes go-live operational gate. Guard: new pytest RED-proofed by simulated process death.
2. 🔧 **PROD-SHADOW-DESIGNATION** (HIGH, wire): designate a dedicated go-live shadow arm, stated window in writing, scored by `statistical_criterion()` net of the A1 cost model (gate's own recommendation verbatim).
3. 🧪 **SAFE-2-EXIT-SHAPE-AB** (HIGH, trading-path, prereg-first): single-variable — safe-2 adopts `exit_patch {tp1_premium_pct: 0.5, stop_mode: structure}`; bold-2 stays CORE control. Frozen forward clock (≥20 round trips or 15 sessions); kill = safe-2 stays negative OR control outperforms. Sanctioned by FULL-PAPER-AUTONOMY + prereg discipline; ships before the window opens Monday or not at all (freeze).
4. 🔧 **GO-LIVE-GATE-RECENCY-VIEW** (MED): add trailing-20td scoring alongside aggregate (J's recency-over-aggregate doctrine applied to the gate itself).
5. 🔧 **FUTURES-PROBE-TAXONOMY-FIX** (MED): ReadTimeout must not map to H1_PERMISSIONS; mirror lane must log a reason on every non-placement (7/8 currently silent); then ONE real small sandbox order on a confirmed-open GLOBEX session to settle the permissions question with fresh evidence.
6. 📋 **WEEK-ORDER-REVIVAL** (MED): produce WEEK-ORDER-2026-08-31 Thursday-cadence synthesis; 3 weeks lapsed.
7. 🧹 **TRENDLINE-VERDICT-RECOMPUTE** (LOW) + close stale queue item `T-KALSHI-DEAD-2026-08-20` (false positive per `desk_allocator.py` 08-21 fix).

**J's five (nothing else needs you):**
- ✅/❌ Ratify the §3 live-threshold rewording (Rule 9, this weekend).
- ✅/❌ Ratify one-account consolidation for the live flip (ROADMAP Gate 4, recommendation: YES).
- 🔑 Kalshi API key + .pem when you want that lane armable (~5 days from its first city clearing).
- 🔑 Futures execution: if the sandbox re-test fails — 2 minutes in the tastytrade dashboard to check futures approval, or open a free Tradovate demo.
- ❓ Confirm whether you disabled `Gamma_CryptoTwin`/`Gamma_KitchenSeeder` on 08-28 (~21:20 MT). Quiet-mode restores everything at 23:00 ET tonight; if the disable was yours and deliberate, say so and we'll pin them off.

---

## 7. Session verification log (OP-33)

- `et_clock.py` → `2026-08-29 11:36:02 Saturday EDT market_hours=False`
- `go_live_gate.py` re-run 11:42 ET → RED; operational now 5/6 (quoted above); recon PASS ×4; output preserved in `analysis/go-live-gate.md`/`.json`
- `pytest backtest/tests/test_eod_flatten_coverage_2026_08_18.py -q` → `8 passed in 0.18s` (stale-FAIL proof)
- `live_readiness.py` re-run 11:39 ET → per-arm numbers quoted in §1/§3
- Quiet-mode: `quiet-mode-restore.json` recorded 11:37 ET, 114 tasks held, RosterLiveness/Conductor/CryptoTwin/KitchenSeeder/WinnerAutopsy all present → restore 23:00 ET tonight; weekend-daytime blackout is BY DESIGN (`quiet_mode.py` bands + starvation-fix lesson 08-26)
- Sonnet fact packs: per-arm economics (fills-ledger mined via `fills_fifo.mine_real_arm_fills`, cross-checked against gate reconciliation — matched); expansion lanes (ledger-first, cross-validated vs `desk-allocation.json` computed 02:10 today)
- UNVERIFIED items are labeled inline (§2 safe-2 mechanism single-variable; §4 tastytrade cert-env quote; §4 trendline verdict staleness)
