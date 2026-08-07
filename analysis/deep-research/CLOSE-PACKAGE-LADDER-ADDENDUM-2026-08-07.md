# CLOSE-PACKAGE ADDENDUM — 2026-08-07 (orchestrator merges at 15:55)

> Lanes append sections below. Do NOT overwrite another lane's section.

## LANE 4 — SIZE ANATOMY (staged for close)

Full artifact: `analysis/deep-research/SIZE-ANATOMY-2026-08-07.md` + `.json`.
Runner: `backtest/tools/size_anatomy_2026_08_07.py` (day totals assertion-reconciled).

**For J's close brief (4 lines):**

- **−$629 was not oversize.** 6.8% of combined Rule-5 kill budgets (no arm above 10.1% of its
  own); ~$22.50/contract; every arm sized exactly per the frozen 2×3 grid — 28 contracts =
  3 (core min) + 8 (safe ELITE tier) + 5 (full-send clamp) + 12 (bold ELITE tier), first
  session the design fully expressed (ELITE + recency GREEN + 4 arms on one shared signal).
  Worst per-contract loss was the SMALLEST position (safe-2, −$51/ct — 64s-earlier 1.67 entry):
  entry timing, not size.
- **Dollar-risk normalization {1.5/2/3}% — REFUTED, no prereg staged.** At $5–6K equities the
  min-contract floors bind 44–50 of 51 week positions → the three cells are the SAME policy
  (shrink variant byte-identical at all f). Best shippable cell: week +$406 but G4 runner −$423,
  sub-window sign-flip, and LEVER-SIZING-2026-08-06 cell (e) already refuted the family on the
  26-day book. Wednesday still −$1,388 in every legal cell — sizing cannot cap a Wednesday.
- **Open finding (no proposal tonight): book-level correlation is unbudgeted.** Per-arm caps are
  all honest; there is no cross-arm budget when 4 arms take one signal. That is the real "$629"
  mechanism.
- **risky-3 OTM-2 revert n=1 forward datapoint:** 12 × $0.62 = $744 notional (13.9% eq), −$204 —
  smaller dollar exposure than ATM-at-12 would have carried into the same stop. Logged, no
  conclusion.

**Cross-lane pointer for the LADDER lane:** `backtest/tools/arm_score_ladder_replay.py` EXISTS
(siblings `ladder_fullhist_replay.py`, `ladder_subset_prereg.py`; evidence in
`analysis/arm-ladder/` — ARM-LADDER-V1-2026-07-27, LADDER-FULLHIST-2026-07-27,
LADDER-SUBSET-VERDICT-2026-07-28). `accounts.json` holds DISARMED score_ladder_doc state on
safe-3 (floor=9: −$10,903/332tr vs +$5,307 baseline) and risky-1 (floor=8: −$16,642/725tr), and
risky-3's armed bear-only ladder. The 07-27 replay tested a FLOOR (score>=N admits), NOT tonight's
demote-not-veto semantics (demotable blockers subtract demerits; non-demotable stay absolute) —
the prereg must state that distinction or the old NULL will be miscounted as evidence against the
new mechanism. Sizing note for the ladder prereg: ladder entries on risky arms will size at bold
tier qty (12 at ELITE, not min) unless the prereg pins qty — the 07-27 armed ladder deliberately
used min_contracts; tonight's should state its sizing explicitly.

## LANE 3 — TV BAR REPLAY WALKTHROUGH (staged for close)

Full artifact (committed a6b17332): `analysis/deep-research/FRIDAY-TV-REPLAY-2026-08-07.md`
— 9 replay screenshots inline, phone-scrollable, binary-vs-ladder annotated at every decision
point on J's own chart (SPY 5m, TV MCP replay, produced intraday 12:07–12:30 ET, no
trading-path file touched, tv_health_check GREEN at exit).

**For J's close brief (3 lines):**

- **The tape shows exactly what J said, 4th ask:** 09:40 close over PDH 771.82 → 11/11 entry
  (both engines identical, −$629 book on the 09:55 dump, stops 10:01–10:02) → then 91 minutes
  (10:15–11:45) of ELITE-grade refusals while SPY ran 770.50 → 773.91 with no meaningful
  pullback — first refused tick 10:15:03 (score 10, sole blocker F10, level_reclaim+confluence
  @770.46, VIX 15.04).
- **Window census (182 HOLD ticks): 70 ladder-admissible** — cells (10,[10])×54, (10,[7])×10,
  (9,[7,10])×6 → BOTH risky rungs (8 and 7) enter at 10:15; the other 112 ticks carry F11
  (bare-confirmation, −$103/entry 0%-WR cohort) and stay refused on EVERY rung — the ladder
  ≠ filter deletion, demonstrated on today's own tape.
- **No oversell:** ladder buys the same 09:46 loss AND the 12:06 re-entry (score-11 cells);
  at ~12:25 the 12:06 position was underwater (spy 771.5 vs 773C @ ~1.10, EST). Narrative ≠
  net-positive proof — that stays on the LADDER lane's sequential walks + battery.

**Dojo/tooling scars for the replay harness (fold into `dojo_session.py`):** (1) a leftover
"Continue your last replay?" modal silently blocks VISUAL replay while the API keeps stepping —
dismiss `[data-name="warning-dialog"]` before `replay_start`; (2) `replay_autoplay` speed is not
honored (~3 bars/s at "1000ms"; "143ms" ran ~98 bars in <6.5s and auto-exited at the live edge) —
fine control is `replay_step` only; (3) API-driven replay keeps painting live bars right of the
yellow cursor — the cursor line + OHLC readout are the frame's authority.


## LANE 1 — SCORE LADDER (staged for close)

Full build narrative + every cell: `analysis/deep-research/SCORE-LADDER-BUILD-2026-08-07.md`.
Prereg (frozen BEFORE the runner, git-provable): `a780122e`; runner+guards+patch `3b3072a9`.
Harness: `backtest/tools/ladder_rung_replay_2026_08_07.py` (found + audited the existing
`arm_score_ladder_replay.py` / `ladder_fullhist_replay.py` / inert `score_ladder_floor`
hooks first — nothing rebuilt; the killed raw-floor lane's numbers are reference cells).

**Verdict: SHIP the BULL-ONLY score-ladder-rung lane to the two risky arms tonight — the
frozen gates pass. Bear stays OUT (two strikes: July raw-floor −$16,642/725tr AND
rung-semantics re-measure −$16,631/843tr). Safe arms stay binary — that IS the ladder.**

| Gate (frozen a780122e) | risky-3 rung 7 | risky-1 rung 8 |
|---|---|---|
| G-WEEK: added P&L 08-03..07 > 0 | **+$3,028 PASS** (Fri EST, partial day) | **+$3,028 PASS** |
| G-POP: avg/added-trade > −$5, not killed-shape | +$0.86/tr / 822tr **PASS** | −$0.85/tr / 755tr **PASS** |
| G-HONEST: all cells reported | PASS | PASS |

- The ladder **takes today's 10:14 miss** (bull 10/11, sole blocker f10) and the 10:24
  f7-blocked tick that caught the 770.50→773.17 run (+$457 EST, qty5). It does not touch
  the 09:46 PDH loser (that was a binary score-11 entry — no admission rule involved).
- Mechanism in one breath: for an arm carrying `gate_override.score_ladder_rung`, a
  scoring-refused tick whose ONLY active bull blockers are DEMOTABLE {5 ribbon, 7 vol-div,
  8 VIX-soft, 10 buyer-pressure} enters when the logged bull_score (= 11 − 1/blocker,
  filters.py:1273 — the demerits ARE the score) clears the rung. NON-DEMOTABLE absolute on
  every rung: f1 window, f6 spread, f9 VIX-hard, f11 trigger-count/level-tied (the
  −$103/entry 0%-WR bare cohort), f12 sweep, risk_gate, $0.30 floor, EOD. Absent key =
  byte-identical binary (C14 guard). NOT filter deletion / NOT filter-8 relax / NOT the
  killed raw-floor lane (blocker identity ignored there; per-arm score-conditional here,
  safe arms as in-fleet control).

**Headlined caveats:** population ~FLAT for the ship shape (+$706 r7 / −$644 r8 over 390d,
qty3) — the positive story is the **2026 slice (+$2,920 / +$1,799)** + the week
(recency-first per J 2026-07-31, stated not smuggled). Drop-best fails everywhere (week
ex-Tue −$356). Chop days fire 19-31 rescues (Wed −$1,555); a 3-rescue/day cap
(probe-lane precedent) would have made the week **+$4,054** — staged fast-follow,
deliberately NOT in the minimal patch. Mixed-lane per-side slices were caught as a
selection artifact (/fable-too-good) — ship numbers are true bull-only LANE walks.
EST calibration: mean −$0.085 / max $0.39 on 22 engine-priced ticks.

**Tonight's runbook (after 15:55 ET; each step reversible):**

```
# 1. Friday final cell on real OPRA (same-day 403 lifts ~16:21):
backtest/.venv/Scripts/python.exe backtest/tools/ladder_rung_replay_2026_08_07.py \
    --ledger 2026-08-07 --sides C --no-est --out-tag friday-final
#    If the full-day Friday cell flips G-WEEK (week added <= 0): STOP, file, report.
# 2. git apply analysis/arm-ladder/score-ladder-rung-2026-08-07.patch   (--check rc 0 verified)
# 3. Remove the two @pytest.mark.xfail decorators in
#    backtest/tests/test_score_ladder_rung_2026_08_07.py (RED-proof -> enforcing).
# 4. pytest that suite + test_probe_arm.py + test_full_send_arm.py -- all green.
# 5. ARM accounts.json gate_override: risky-3 "score_ladder_rung": 7, risky-1: 8
#    (same commit updates test_live_accounts_carry_no_rung_key_yet to assert the keys).
# 6. commit_scoped.py, report for REVOKE.
```

**REVOKE (J, any time):** delete the two `score_ladder_rung` keys — next tick is
byte-identical binary. **Monday watch:** per-day rescue counts (>5 on a chop day = the
3/day-cap fast-follow gets its live evidence); `pdt_enforced=false` on both risky arms
(mirrored + disclosed); forward ledger vs the Friday EST cell.

RED-proof quoted (HEAD, --runxfail): `2 failed` (admit + producer tests), suite normal
mode `6 passed, 3 skipped, 2 xfailed`. Accidental-arming guard REDs if accounts.json
grows the key outside step 5.

**The patch (dormant — NOT applied; market open during this build):** also at
`analysis/arm-ladder/score-ladder-rung-2026-08-07.patch`.

## LANE 2 — SCORE-LADDER-V2 DEMERIT REPLAY (staged for close) — verdict + cross-lane reconciliation

Prereg `c2ec28f3` (frozen 12:35 ET before any run — DOUBLE-demerit arithmetic pinned by the
task's worked example: score 10, sole blocker f10, demerit 1 → adjusted 9). Full evidence:
`analysis/deep-research/SCORE-LADDER-REPLAY-2026-08-07.md` + 5 JSON mirrors. Runners:
`backtest/tools/score_ladder_replay_2026_08_07.py` (population, 398d, occupancy lanes),
`score_ladder_week_live_2026_08_07.py` (live-tape week, real OPRA — 253 leading-edge OPRA
contracts backfilled first), `score_ladder_today_est_2026_08_07.py` (today, EST k=1.0293
calibrated on 47 real anchors), `score_ladder_shadow_nightly.py` (standing $0 instrument).
Guards: `backtest/tests/test_score_ladder_v2_admission_2026_08_07.py` 11/11 + RED-proofed.

**LANE 2 verdict under its own frozen gates: DO NOT ARM — PREREG + shadow clock.** Failing
cells named: G_wednesday (rung 7 −$1,143 / rung 8 −$405 vs the frozen −$300 allowance — the
776/777C chase re-opens, mildly, at rung 8), G_week at J's rung 7 (−$59.60 live-tape), BH
q=0.10 null everywhere, bull-cohort sub-window T2 negative. Passing cells: population net +
tail at all ship rungs (displacement-driven: extras −$1.1K..−$2.1K, displaced binary losers
−$6.8K..−$6.9K — disclosed, not edge), Tuesday IMPROVED +$1,243.90 (both instruments), Mon
+$738 / Tue +$1,244 = J's exact missed runners, today's 10:15 ADMITTED (adjusted 9).

**Cross-lane reconciliation (LANE 1 vs LANE 2 — for the orchestrator's merge):**

- **The evidence AGREES once conventions align.** Bull-only week positive in both lanes
  (LANE 2 rung-8 bull-only ≈ +$1,454 qty3 Mon–Thu + positive Fri EST ≈ LANE 1's +$3,028
  at qty5 incl. Fri). Bear side dead in both (LANE 2 population extras −$4.6K/−$6.4K; LANE 1
  −$16.6K/−$11.8K at its wider admission — three strikes with July's raw floor). Safe arms
  binary in both. Chop/fade days are where every ladder variant bleeds (LANE 1: Wed −$1,555,
  19–31 rescues/chop-day; LANE 2: Wed −$405 at its tighter rung-8, −$1,143 at rung 7).
- **The verdicts differ on two axes, not on the data:** (1) admission arithmetic — LANE 1
  single-demerit (logged score ≥ rung: rung 7 admits ≤4 demotable blockers), LANE 2
  double-demerit (task-pinned: rung 8 admits ≤1) — J's *words* ("a ten out of eleven")
  read closer to LANE 1; the task brief's *worked example* pins LANE 2; (2) gate strictness —
  LANE 1 froze added-P&L>0 + avg/tr>−$5 (passes), LANE 2 froze week-vs-binary + a
  Wednesday −$300 allowance + BH (fails).
- **If the orchestrator ships LANE 1's runbook tonight** (its gates passed; J's 4-ask
  standing): LANE 2's evidence argues for two amendments, both cheap: (a) prefer the
  TIGHTER admission on the riskier arm (both lanes show chase bleed scales with admission
  width — LANE 2's ≤1-demotable cohort cut Wednesday from −$1,143 to −$405); (b) take LANE
  1's own staged 3-rescue/day cap seriously as a fast-follow — it is the single lever both
  lanes' Wednesday cells point at. Bear stays out regardless. If it does NOT ship, LANE 2's
  shadow nightly (`Gamma_LadderShadow`, 16:40 ET weekdays — registration staged below) runs
  the forward clock either way, and measures the demerit-v2 cohort even under a LANE 1 arm.
- **Do not double-arm:** LANE 1's `score_ladder_rung` patch and any future LANE 2 arming are
  the SAME lane in spirit — one admission rule per arm, ever. LANE 2 defers to LANE 1's
  patch as the shipping vehicle if J/orchestrator arms tonight.

**LANE 2 staged items:** (1) register `Gamma_LadderShadow` 16:40 ET weekdays →
`backtest\.venv\Scripts\pythonw.exe backtest\tools\score_ladder_shadow_nightly.py` (append
SCHEDULED-TASKS.md; $0; no trading-path surface) + run once for today post-16:21; (2) frozen
forward arm bar for the demerit cohort (≥10 sessions, extras>0, no session <−$500 qty3,
negative sessions avg ≥−$300) recorded in the runner docstring; (3) do NOT re-arm the old
raw-floor `score_ladder_floor` keys (dead semantics). Final Friday EST numbers refresh in
the last pre-close run of `score_ladder_today_est_2026_08_07.py`.

```diff
diff --git a/automation/state/fleet/build_shared_signal.py b/automation/state/fleet/build_shared_signal.py
--- a/automation/state/fleet/build_shared_signal.py
+++ b/automation/state/fleet/build_shared_signal.py
@@ -940,32 +940,44 @@ def _probe_passed_blocks_from_row(row: "dict | None") -> dict:
 #     entry's chart-stop anchor; no level, no trade.
 LADDER_LEVEL_TIED = frozenset({"level_rejection", "fhh_level_rejection", "confluence",
                                 "sequence_rejection"})
+# Bull mirror (2026-08-07, SCORE-LADDER-RUNG, prereg a780122e): the level-tied trigger
+# names filters.py's own bull filter-11 defensive gate uses (filters.py:1269).
+LADDER_LEVEL_TIED_BULL = frozenset({"level_reclaim", "confluence", "sequence_reclaim"})
 _LADDER_EMPTY = {"available": False, "score": 0, "triggers_raw": [], "level": None,
-                 "blockers": [], "reason": None}
+                 "blockers": [], "vix": None, "reason": None}
 
 
 def _ladder_block_from_row(row: "dict | None") -> dict:
-    """Pure row -> ladder block (bear side only for v1 -- bull stays out until its own
-    pre-registered evidence exists; the 2026-07-27 10:06 bull-9 fired mid-fade and would
-    have lost, so bull needs the study first, not a mirror-image flip)."""
-    out = {"bear": dict(_LADDER_EMPTY)}
+    """Pure row -> ladder block. v1 (2026-07-27) was bear-only; 2026-08-07 adds the bull
+    side + a `vix` field on both blocks (SCORE-LADDER-RUNG, prereg a780122e) -- pure
+    additive producer data, same inertness contract as probe/full_send: every reader keys
+    off its own per-arm config key, so emission alone changes nothing downstream."""
+    out = {"bear": dict(_LADDER_EMPTY), "bull": dict(_LADDER_EMPTY)}
     if row is None:
         return out
     verdict = str(row.get("verdict") or "")
     reason = str(row.get("reason") or "")
     if verdict != "HOLD" or "no setup passed scoring" not in reason:
         return out
-    raw = [t for t in (row.get("bear_triggers_raw") or []) if isinstance(t, str)]
-    level = row.get("bear_rejection_level_raw")
-    score = row.get("bear_score") or 0
-    if not any(t in LADDER_LEVEL_TIED for t in raw):
-        return out
-    if not isinstance(level, (int, float)):
-        return out
-    out["bear"] = {"available": True, "score": int(score), "triggers_raw": raw,
-                   "level": float(level),
-                   "blockers": list(row.get("bear_blockers") or []),
-                   "reason": f"score {score} blocked (blockers {row.get('bear_blockers')})"}
+    vix = row.get("vix") if isinstance(row.get("vix"), (int, float)) else None
+    for key, tied, sk, bk, tk, lk in (
+        ("bear", LADDER_LEVEL_TIED, "bear_score", "bear_blockers",
+         "bear_triggers_raw", "bear_rejection_level_raw"),
+        ("bull", LADDER_LEVEL_TIED_BULL, "bull_score", "bull_blockers",
+         "bull_triggers_raw", "bull_reclaim_level_raw"),
+    ):
+        raw = [t for t in (row.get(tk) or []) if isinstance(t, str)]
+        level = row.get(lk)
+        score = row.get(sk) or 0
+        if not any(t in tied for t in raw):
+            continue
+        if not isinstance(level, (int, float)):
+            continue
+        out[key] = {"available": True, "score": int(score), "triggers_raw": raw,
+                    "level": float(level),
+                    "blockers": list(row.get(bk) or []),
+                    "vix": vix,
+                    "reason": f"score {score} blocked (blockers {row.get(bk)})"}
     return out
 
 
diff --git a/automation/state/fleet/fleet_executor.py b/automation/state/fleet/fleet_executor.py
--- a/automation/state/fleet/fleet_executor.py
+++ b/automation/state/fleet/fleet_executor.py
@@ -900,6 +900,15 @@ def plan_all(
         ladder_plan = _ladder_plan(arm, signal, equity, params, arm_id, spot)
         if ladder_plan is not None:
             plans.append(ladder_plan)
+    # SCORE LADDER RUNG (2026-08-07, prereg a780122e -- J 4th+ ask: "why are we sitting out
+    # of anything that's a ten out of eleven?"). Demotable-demerit admission, BULL ONLY (the
+    # bear side has two strikes -- see _ladder_rung_plan). Fires ONLY for an arm carrying
+    # gate_override.score_ladder_rung; absent key = byte-identical binary behavior
+    # (guard: backtest/tests/test_score_ladder_rung_2026_08_07.py, C14 vary-and-assert).
+    if not any(p.action == "ENTER" for p in plans):
+        rung_plan = _ladder_rung_plan(arm, signal, equity, params, arm_id, spot)
+        if rung_plan is not None:
+            plans.append(rung_plan)
     # FULL-SEND (2026-07-31, J directive: "we should just be getting in shit and seeing if it
     # works"). Third and loosest rescue lane, same shape/contract as probe + ladder: fires ONLY
     # for an arm carrying gate_override.full_send, ONLY when no other lane produced an ENTER,
@@ -1031,6 +1040,80 @@ def _ladder_plan(
                      trigger_level=float(level))
 
 
+# --- SCORE LADDER RUNG (2026-08-07, prereg a780122e) --------------------------------------
+# J's words define it: an arm's admission threshold is a SCORE, not a gate cascade. For rung
+# arms, DEMOTABLE bull filters {5 ribbon-stack, 7 vol-divergence, 8 VIX-soft, 10 buyer
+# pressure} no longer veto -- each already costs its scorer demerit (exactly 1 point each:
+# filters.py:1273 `bull_score = 11 - len(blockers)`, so the logged score IS the adjusted
+# score) -- and the arm enters when score >= gate_override.score_ladder_rung. NON-DEMOTABLE
+# gates stay absolute on every rung: filter 1 (entry window), 6 (spread), 9 (VIX hard cap),
+# 11 (trigger count + level-tied -- the measured -$103/entry 0%-WR bare-confirmation
+# cohort), 12 (sweep), plus risk_gate / min_entry_premium / EOD flatten downstream, all
+# untouched (same contract as the probe/ladder/full-send lanes).
+# BULL ONLY -- the bear side has TWO strikes: the raw-floor lane (-$16,642/725tr, DISARMED
+# 2026-07-27) and the rung-semantics bear lane re-measured on the same 390-day population
+# (-$16,631/843tr rung 7, -$11,758/466tr rung 8, held-out negative --
+# analysis/arm-ladder/LADDER-RUNG-2026-08-07-population.json). Bull evidence: population
+# +$3,647/433tr rung 7 (+$8.4/tr, survives drop-best, held-out last-25% +$2,526), week
+# 2026-08-03..07 added +$3,028/arm (LADDER-RUNG-2026-08-07-week-bullonly.json; Friday
+# cells EST-priced, labeled).
+_RUNG_DEMOTABLE_BULL = frozenset({5, 7, 8, 10})
+
+
+def _ladder_rung_plan(
+    arm: Mapping[str, Any], signal: Mapping[str, Any], equity: float,
+    params: Mapping[str, Any], arm_id: str, spot: Any,
+) -> Optional[EntryPlan]:
+    """Min-size ribbon_ride BULL entry off signal['ladder']['bull'] under rung semantics.
+    Same shape/contract as _ladder_plan: min_contracts hard clamp (never _qty_for),
+    PROBE_STRIKE_TIERS, risk_gate/finalize() downstream completely untouched, and the raw
+    detection's own level rides as trigger_level (a rung entry is never stop-less).
+    Fail-closed everywhere: absent/garbage key, block, blockers, or level -> None, and the
+    caller's verdict stands unmodified. Instant de-arm: delete the config key."""
+    g = arm.get("gate_override") or {}
+    rung = g.get("score_ladder_rung")
+    if rung is None:
+        return None
+    try:
+        rung_i = int(rung)
+    except (TypeError, ValueError):
+        return None
+    if (signal.get("bull") or {}).get("passed") is True:
+        return None   # scope fence: this lane rescues SCORING-failed ticks only
+    ladder = signal.get("ladder")
+    if not isinstance(ladder, Mapping):
+        return None
+    blk = ladder.get("bull")
+    if not isinstance(blk, Mapping) or blk.get("available") is not True:
+        return None
+    score = int(blk.get("score") or 0)
+    level = blk.get("level")
+    if score < rung_i or not isinstance(level, (int, float)):
+        return None
+    try:
+        blockers = {int(b) for b in (blk.get("blockers") or [])}
+    except (TypeError, ValueError):
+        return None   # unreadable blockers: cannot prove demotable-only -> no trade
+    if not blockers <= _RUNG_DEMOTABLE_BULL:
+        return None   # a NON-DEMOTABLE blocker is active -> absolute veto, on any rung
+    if spot is None:
+        return _hold(arm_id, "C", "SCORE_LADDER_RUNG", "score-ladder-rung: no spot in signal")
+    strike = strike_selection.pick_strike(float(spot), float(equity), "C", PROBE_STRIKE_TIERS)
+    try:
+        qty = int(params.get("min_contracts", 3))
+    except (TypeError, ValueError):
+        qty = 3
+    trigs = list(blk.get("triggers_raw") or [])
+    quality = "ELITE" if any("confluence" in str(t).lower() for t in trigs) else "BASE"
+    reason = (f"SCORE_LADDER_RUNG rung={rung_i} score={score} "
+              f"blockers={sorted(blockers)} trig=" + "+".join(trigs))
+    return EntryPlan(arm_id, "ENTER", "C", "BULLISH_RECLAIM_RIDE_THE_RIBBON", strike, qty,
+                     quality, reason,
+                     strategy=strategies.RIBBON_RIDE.name,
+                     exit_shape=_exit_shape_dict(strategies.RIBBON_RIDE, arm),
+                     trigger_level=float(level))
+
+
 # --- FLOOR-RESCUE eligibility (2026-08-03, L246-class ORDERING FIX) -----------------------
 # THE DEFECT (EOD-2026-08-03-FULL-REVIEW.md section 4.2, "0 fires EVER vs 35 floor-blocks
 # today"): plan_all's full-send precondition ("no ENTER in plans") runs at PLAN time, but the
```
