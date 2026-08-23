# PROFITABILITY ORDER — three sectors, one ranking (2026-08-23)

> Written Sunday 2026-08-23 (weekend window) by the Fable session J asked: "figure out what we
> need to do to become profitable in the three sectors — futures, 0DTE SPY, other option trading."
> Synthesized from three independent lane audits (0DTE / futures / other-options) run fresh this
> session against on-disk evidence. Every number below carries its source file. Actionable items
> filed in `automation/overnight/queue.md` (six new entries, 2026-08-23) so the conductor drains
> them; this doc is the adjudication record.

---

## FOR J — the verdict in 10 lines

- **Nobody is profitable today.** 0DTE book **−$1,941 over 35 sessions** (303 trips, WR 23.10% vs 25.24% breakeven — a 2.14pp gap). Futures sim **−$100/8 trades**, both edges sub-threshold. Other-options: every v1 signal correctly killed.
- **All the near-term profit leverage is in 0DTE SPY.** Futures and other-options have no matured positive edge to ship; 0DTE has one matured lever + one governance leak worth ~170% of the deficit combined.
- **#1 SHIP: `R_tp100_f50`** (TP1 sell-half at +100%) — its re-open clock EXPIRED (risky-1 n=31≥30) and sat unactioned. Sole BH survivor of 28 cells, **+$1,174 scaled ≈ 60% of the WR gap**, pre-written kill bar. Re-adjudicate → paper-ship any evening.
- **#2 STOP THE LEAK: watcher lane.** Non-ribbon setups are **−$2,139 = 110% of the whole deficit** (VWAP_CONTINUATION alone −$1,470) with **no ratification record** on the only deep population we own. Provenance audit → no record ⇒ SHADOW. This is your own gate-provenance rule, not a P&L filter.
- **#3 GATES COSTING MONEY NOW:** `require_bearish_fill_bar` refuses a cohort earning **+$46.15/tr (n=34)** — full G-battery before any flip. Bear core itself is RED on the fresh window (**−$16.71/tr, n=31**) while bull flipped GREEN (+$2.45/tr).
- **DO NOT TOUCH:** stops (0/34 cells pass; tightening decapitates $3,035 of winners), the −50% cat-cap (validated KEEP, watch closed), conviction ladder (arming would have cost $675), day-throttle (forward reading is negative), chop-blocking (kills the best cohort).
- **Futures = let the clocks run, fix the spec.** Edge #3 at 11/20 trips, mean **$23.84 vs $71.46 validated** (flashing amber, verdict at n=20 by its own rail). SSR shadow 17/20 but **fails beats_null** and is scored on unfundable full-size NQ/GC → respec to MNQ/MGC (ssr-v2). No live-arming path exists regardless (OP-0 #1 + new venue, double-gated).
- **Other options = one hypothesis left, everything else stays dead.** Port `build_shared_signal.py` (the real 58%/+4.9σ signal) symbol-generic through the retained null harness under a fresh prereg. Weekly/multi v1 signals stay killed; no account provisioning until a signal clears null. Kalshi: $0 RTH liquidity re-run decides the venue before you spend a key.
- **Trust repair that gates everything:** the fleet-replay harness has 2 known REDs (risky-1 sequence_rejection parity, bar 1801) — FABLE-ESCALATION already filed; until adjudicated, all replay-derived evidence (incl. #1's scaling) reads with a quarantine caveat.
- **Your only J-steps:** none this weekend. Kalshi API key only IF the RTH survey clears the spread gate. Everything else ships autonomously under the standing rails.

---

## Sector 1 — 0DTE SPY: the profit center (all ranked actions live here)

**Where the money actually goes** (canonical: `analysis/deep-research/WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19.md`, 303 trips):

- Only **44 TP1 exits** make money (+$14,514). Stops subtract **$16,088** (premium −$10,090, structure −$5,998). Ribbon flip ≈ 0.
- Core ribbon setups (n=228): **+$198**. Watcher setups (n=75): **−$2,139**. Same WR — a payoff-shape problem, not a hit-rate problem.
- Day dispersion >> arm dispersion: one day (08-04, +$3,613) = 186% of the deficit; 5 losing days in the last 15 sum to −$8,692. Confirms the standing doctrine: the day can't be pre-selected; damage control + right-tail capture are the levers, not day-picking.

**Matured instrument verdicts this weekend** (full table in the audit; sources inline):

| Instrument | Verdict | Evidence |
|---|---|---|
| R_tp100_f50 | **RE-ADJUDICATE** — one gate short, and it's a POWER gate (see §1a) | synthesis §2/#1 + prereg scorecard |
| Catastrophe cap −50% | **KEEP, watch CLOSED** | CATASTROPHE-CAP-DECISION-2026-08-09 (n=13, control beats all variants) |
| Strike clamp / MINCON / TRAIL_25 / re-entry cooldown | **ALL REFUTED** (3 of 4 died at leave-best-2-out) | synthesis §3 |
| stop_mode structure-vs-premium | **PENDING** (n=10/20; current +$498 but sign has flipped twice in a week; date-paired live split favors structure +$4.48 vs −$24.60/tr) | stop-mode-shadow-summary.json |
| Day-throttle T-2/T-6 | **PENDING 11 sessions**; forward reading currently NEGATIVE (−$306) vs in-sample hope | day-throttle-shadow-summary.json |
| Conviction ladder | **NOT SHIP-ELIGIBLE** — 98.1% block rate, arming = −$675; underlying C5 signal broken | conviction-shadow-report.json |
| Entry-quality V-d1/V-e3 | shadow-only, thin (+$65 n=161 / +$449 n=4 fails F3) | entry-quality/shadow-summary.json |

### §1a — CORRECTION (Opus review pass, same evening): what R_tp100_f50 actually failed on

The first pass of this doc said "clock expired, re-adjudicate → ship." Reading the frozen cell record
directly (`analysis/recommendations/tp1-reachability-2026-08-06.json`, cell `R_tp100_f50`) sharpens it,
and the sharper version changes the ACTION:

- **It fails exactly ONE gate: `G4_subwindow_stable`.** G1, G2, G3, G5, G6, G7, G8 all pass; bar
  components `OOS_positive`, `WF_ge_0.70` (0.80), `anchor_no_regression` all pass. `p_value_raw=0.002617`.
- **G4 failed for lack of POWER, not for instability.** All four sub-windows are POSITIVE:
  2025H1 +$228.95 (n=4) · 2025H2 +$333.20 (n=13) · 2026Q1 +$253.20 (n=4) · 2026Q2p +$94.70 (n=10).
  G4 requires delta ≥ 0 in **≥3 windows holding ≥5 changed trades** — only TWO windows qualify, so a
  pass is arithmetically unreachable. Cause: `popA_tp1_fire_rate = 0.2042` — TP1@+100% touches ~1 trade in 5.
- **`G3_runner_anchor` is +$628.05** — the prereg's declared "operative veto" is not merely survived, it is
  positive. This cell does not damage the runner cohort that pays for the book.
- **Therefore the resolution is MORE DATA, never a softer gate.** The prereg is explicit ("the bar is not
  softened to ship"; P4 predicted no cell would clear). Re-reading a failed gate as "only technically failed"
  is the forking-paths anti-pattern. The legitimate move — already precedented THIS WEEKEND on
  `structure_veto_enabled` — is to extend the population past the frozen end date through the live OPRA
  cache date, leave all 8 gate definitions byte-identical, and let G4 pass or fail with adequate power.
- **The prereg's own named resolution instrument is risky-1's LIVE +50% arm**, not a replay re-run — which
  usefully routes around the fleet-replay quarantine. ⚠️ But note the **axis mismatch**: risky-1's live arm
  varies the TP1 LEVEL (+50% vs +100%); the frozen cell varies the QTY FRACTION (0.5 vs 0.667) at a fixed
  +100% TP1. They share the "early extraction damages runners" risk, they are NOT the same knob. Live
  corroboration is a bounding proxy and must be reported as one.

Dispatched accordingly (extend-population re-run under frozen gates + live-arm corroboration + VOID check).

### §1c — RESULT of the extended re-adjudication: DO_NOT_ARM STANDS, and the path is closed

Run: `analysis/recommendations/tp1-r50-readjudication-2026-08-23.json` (tools
`backtest/tools/tp1_r50_readjudication_2026_08_23.py` + `_live_arm_` + `_assemble_`). Commit `97f3c864`.

- **Forward clock legitimately MET** — risky-1's live +50% arm (`exit_patch={tp1_premium_pct:0.5,
  stop_mode:structure}`) has **n=35** ribbon fills post-2026-08-03 in `journal/trades.csv`, cross-validated
  against n=35 `placed=true` ENTER rows in the arm's `decisions.jsonl` (34/35 matched within 15s). Not premature.
- **popA extended 191 → 213** (22 new entries, 2026-07-23..2026-08-21 via `read_cache_last_date()`).
- **VOID check PASS, 0 mismatches** — after the runner self-caught and fixed a real DST bug: a DST-aware UTC
  conversion shifted every winter bar 1h against this repo's deliberately DST-naive fixed `-04:00` convention,
  producing 16 winter-dated mismatches. Exactly the documented DST-frame artifact class. The VOID tripwire worked.
- **G4 STILL FAILS**, and the finding is now structural, not statistical:

| Window | Delta | n_changed | Qualifies (≥5)? |
|---|---:|---:|:---:|
| 2025H1 | +$228.95 | 4 | no |
| 2025H2 | +$333.20 | 13 | yes |
| 2026Q1 | +$253.20 | 4 | no |
| 2026Q2p_ext | +$151.95 | 14 | yes |

  **2025H1 and 2026Q1 are CLOSED calendar windows permanently stuck at n_changed=4.** A forward extension can
  only ever grow the newest window, so **at most 2 of 4 windows can ever qualify against a ≥3 requirement**.
  G4 is unreachable for this cell by construction — not data-starved, structurally impossible. All four windows
  remain positive; the cell is still positive everywhere it is measured. It simply cannot be certified by G4.
- **Live-arm proxy weakly CONTRADICTS the damage risk** (risky-1 ahead +$1,050 on n=25 shared signals; +$513 on
  the n=6 runner-leg proxy) — but n=6 and the level-vs-fraction axis mismatch make this suggestive, not evidence.
- **Disclosed gap:** G6/G7/G8 were carried forward from the 2026-08-06 scorecard, not re-run on population B.
  Immaterial to the verdict (G4 blocks regardless) but it means the week-population gates are not fresh.

**ADJUDICATION (Opus): DO NOT SHIP. Do NOT re-spec G4 to let this cell through.** Rewriting a gate after seeing
which cell it blocked is the forking-paths anti-pattern, and the prereg is explicit that the bar is not softened.
The cell is EXHAUSTED via this prereg. Two follow-ons filed instead, both honest:
1. **Forward shadow instrument** — R_tp100_f50 has the profile of a real candidate (7/8 gates, positive in all 4
   windows, runner-anchor **+$628**, p=0.0026, sole BH survivor) blocked only by an unreachable power gate. The
   uncontaminated way to resolve it is FORWARD counterfactual evidence on data nobody has seen, following the
   established stop_mode / day-throttle shadow pattern. Any new backtest prereg on this same data is already
   contaminated — we have seen the answer.
2. **G4 design question, forward-only** — fixed-calendar-window stability gates have a structural blind spot for
   low-fire-rate knobs (this cell fires on 20.4% of trades). An equal-N window split would test the same property
   with adequate power. That is a change for FUTURE preregs; it must never be applied retroactively to this one.

### §1b — CORRECTION (Opus review pass): the watcher-lane leak was already mostly closed

The first pass ranked "watcher lane bleeding −$2,139 = 110% of the deficit" as action #2. The provenance audit
([WATCHER-LANE-PROVENANCE-2026-08-23](WATCHER-LANE-PROVENANCE-2026-08-23.md)) falsifies the premise:

- **Only 2 of the 4 families can place live orders.** `vwap_continuation` (the −$1,469.94 worst offender) and
  `vix_regime_dayside` were **DISARMED 2026-07-25** (`params.json#extra_setup_exec_armed=false`), fleet-path leak
  closed 2026-08-12. `journal/trades.csv` confirms **zero fills since** — the params read is not stale.
- The −$2,139 was measured over 2026-06-26..08-19, a window that mostly **predates** those disarms. The forward
  dollar value of "shadow the watcher lane" is therefore far smaller than ranked. **Action #2 is DEMOTED.**
- **BOLLINGER_SQUEEZE = RATIFIED** and stays armed: it is the only watcher family with a population-scale study
  (373-day, n=303–325, IS/OOS, WF 1.44–1.59, dir-null PASS).
- **The one genuinely contestable armed family is `VWAP_RECLAIM_FAILED_BREAK`** (Safe-2 + risky-1/-3 + safe-3):
  ratified on n=76 real fills only, and live WR has diverged to **12.5% (n=8) vs its 55.3% backtest**. n=8 is
  FAR too small to act on — disarming on that would be acting on noise, the same error this audit just corrected.
  It gets a forward clock, not a disarm.

**Two structural findings worth more than the original action:**
1. **No deep population exists for ANY non-ribbon family.** popA (391-day, n=191) is ribbon-only, and the TP1
   prereg states it explicitly: *"popA cannot test vwap (ribbon-family population)... ineligible to ship from this
   study REGARDLESS of gates."* Every non-ribbon family is structurally condemned to thin, real-fills-scale
   evidence. That is a systemic evidence gap, not a per-family oversight.
2. **A prereg is deadlocked.** `vwap-family-killcheck-prereg-2026-08-18` requires 20 live sessions or n≥25 forward
   positions, but its strategy was disarmed six days BEFORE the prereg was frozen — zero fills, so it can never
   resolve. A forward clock that cannot tick is not evidence-in-progress, it is a dead instrument.

**Queue items filed:** `TP1-R50-READJUDICATION` (HIGH) · `WATCHER-LANE-PROVENANCE-AUDIT` (HIGH) · `BEARISH-FILL-BAR-G-BATTERY` (MED-HIGH). Pre-existing `FABLE-ESCALATION-RISKY1-SEQUENCE-REJECTION-PARITY-GAP` stays ranked with them — risky-1 is the worst arm on the 10-day window (−$571) and the parity gap sits on its entry-quality gate.

## Sector 2 — Futures: mature the clocks, don't force them

- **Edge #3 (MES→MNQ divergence):** 11/20 round trips, mean **$23.84 vs $71.46 validated** (33% — under the 50% kill line, but its rail only adjudicates at n≥20). No action except let it fill. `AUTONOMOUS-FUTURES-LANE.md` is stale (still shows n=6/$134 — the drift went from too-good to shortfall).
- **SSR shadow:** 17/20, +$27,336 absolute BUT **fails beats_null** (unmanaged hold +$30,828 — the managed exits subtract) AND is scored on unfundable full-size NQ/GC. Filed `FUTURES-SSR-V2-RESPEC`. A v2 respec restarts a fundable clock; it does not rescue v1's null fail.
- **Broker (real-fills) lane:** venue approval is settled (`H2_SESSION_ARTIFACT` = the zero-BP field is a cert-env red herring; a real /MESU6 fill exists 08-09) but the lane is thrashing: 1 order attempt `placed=false` with empty diagnostics, **36 `broker_position_vanished` / 0 `filled`** (24h cert wipe). The 08-21 diagnosability patch needs one live-session re-attempt Monday to classify the rejection.
- **Bookkeeping bugs found (fix dispatched this session):** HOME.md shows SSR "0 round trips" — key mismatch in `obsidian_vault_sync.py` (`n_closed_round_trips` vs the file's `n_round_trips`); `journal/futures/trades.csv` is missing 3 of 8 sim trades (all of 08-10, including the first stop-out).
- **Live-arming:** blocked by standing doctrine (OP-0 #1 + new venue, double-gated) independent of performance. Correct; unchanged.

## Sector 3 — Other options: stop spending until there's a new question

- **Weekly (GLD/QQQ):** v1 + variant-1 both dead by their own preregs (all 4 expiry arms lose −8..−14%, fail null; variant-1 strictly worse). No weekly-1 account exists and none should until a signal clears null. Machinery + doctrine doc stay.
- **Multi-symbol:** STOPPED_ON_NULL stands. Levels-transplant hypothesis **falsified** ("the levels ARE the edge" was wrong); the harness itself proven calibrated via SPY control (58.23%/+4.89σ @ +10min). Salvage = the null harness + symbol-generic infra + `multi/evaluate.py` read surface. Banned: sweeps, more names, re-slices.
- **The one live hypothesis (filed `MULTI-SIGNAL-PORT-BUILD-SHARED-SIGNAL`):** port production `build_shared_signal.py` to a symbol argument and adjudicate through the retained harness under a fresh prereg — with a right-tail channel in the gate, per the calibration doc's own finding that mean-return-only gates under-measure this engine's edge class.
- **Kalshi (filed `KALSHI-RTH-LIQUIDITY-RERUN`):** shadow idle since 08-09 (no task ever registered). $0 RTH liquidity re-run settles whether the index series is genuinely spread-blocked before J spends effort on an API key; BTC dailies are the fallback venue.

## Cross-sector strategic read

### ⭐ THE PATTERN BOTH LANES SHARE: the EXITS are destroying the value

Surfaced by running the 0DTE and futures adjudications side by side on 2026-08-23. Neither lane's evidence was
collected to answer this, and both answer it anyway:

- **0DTE SPY:** of $14,514 made at TP1, stops give back **$16,088** (premium_stop −$10,090, structure_stop
  −$5,998); ribbon_flip ≈ 0. Only ONE exit stage makes money. And 0/34 stop-mode/width cells pass their gates —
  tightening destroys more winner-dollars than it saves ($3,034.88 of eventual winners dug past −20% MAE).
- **Futures SSR:** absolute expectancy is POSITIVE (+$27,335.69 over 17 round trips) but it **FAILS beats_null**
  — an unmanaged hold to the same closing bar returns **+$30,828.09**. The exit management subtracts ~$3,500.
- **Same signature, two independent instruments, different asset classes:** entries find something; the exit
  policy hands a chunk of it back. In 0DTE the right tail (44 TP1 exits) is the entire P&L; in SSR the right tail
  is what the managed exit truncates.

This reframes where the remaining edge work belongs. Both lanes have been optimising ENTRY gates (structure_veto,
require_bearish_fill_bar, conviction ladder, entry-quality tiers — and this weekend all three of the entry-side
levers came back negative or already-closed). The measurement keeps pointing at exits, and the exit knobs that
have been tested were mostly tested as *tightening* (stops, throttles, earlier profit-taking), which is the
direction that kills the right tail. **The untested direction is exits that protect the right tail rather than
truncate it** — and note that R_tp100_f50, the one cell that survived 7/8 gates with a POSITIVE runner anchor,
is exactly a right-tail-preserving change (bank less at TP1, leave more runner). That is a coincidence worth
treating as a hypothesis, not a conclusion.

⚠️ Honest caveat: this is a PATTERN across two lanes, not a validated finding. It has not been through a null
test, and "exits are the problem" is an easy story to tell about any losing book. It earns a pre-registered
investigation, not a parameter change.

## Cross-sector strategic read (original)

The SPY-calibration finding is the biggest single takeaway of the weekend: **the engine's edge is not direction-prediction, it's right-tail premium harvest** (direction ~58% @ +10min and gone by +60min, while the P&L lives in 44 TP1 exits). Two lanes (weekly, multi) were killed by mean-return/direction null gates that under-measure exactly that edge class. Verdicts stand (they failed at every horizon), but **every future lane's prereg gets a right-tail/hit-rate channel alongside mean-return** — encoded in the MULTI-SIGNAL-PORT queue item's spec.

---

*Successor context: WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19 (0DTE canonical), MULTI-LANE-STAGE-A-VERDICT-2026-08-20 + MULTI-LEVELS-TRANSPLANT-VERDICT-2026-08-21 (multi kills), WEEKLY-EXPIRY-EXPERIMENT-2026-08-18 (weekly kill), AUTONOMOUS-FUTURES-LANE.md (futures, partially stale — see §2).*
