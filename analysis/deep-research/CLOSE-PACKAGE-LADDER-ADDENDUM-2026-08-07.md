# CLOSE PACKAGE — LADDER ADDENDUM, 2026-08-07 (LANE 1)

> Separate file by design; the orchestrator merges at 15:55. Full build narrative + every
> cell: [SCORE-LADDER-BUILD-2026-08-07.md](SCORE-LADDER-BUILD-2026-08-07.md). Prereg
> (frozen BEFORE the runner, git-provable): `a780122e`; runner+guards+patch: `3b3072a9`.

## Verdict

**SHIP the BULL-ONLY score-ladder-rung lane to the two risky arms tonight** — the frozen
gates pass. **Bear stays OUT (two strikes). Safe arms stay binary — that IS the ladder.**

| Gate (frozen in prereg a780122e) | risky-3 rung 7 | risky-1 rung 8 |
|---|---|---|
| G-WEEK: added P&L 08-03..07 > 0 | **+$3,028 PASS** (Fri cell EST, partial) | **+$3,028 PASS** |
| G-POP: avg/added-trade > −$5, not killed-shape | +$0.86/tr on 822tr **PASS** | −$0.85/tr on 755tr **PASS** (killed shape was ≈−$20/tr) |
| G-HONEST: all cells reported | PASS (build doc §4) | PASS |

- The ladder **takes today's 10:14 miss** (score 10/11, sole blocker filter 10) and the
  10:24 f7-blocked tick that caught the 770.50→773.17 run (+$457 EST at qty5).
- It does NOT touch the 09:46 PDH morning loser — that was a BINARY entry (score 11,
  zero blockers); no admission rule was involved. The ladder's job today was the missed
  window, and it takes it.

**Headlined caveats (read before arming):** population is ~FLAT for the ship shape (+$706
r7 / −$644 r8 over 390d); the positive story is the **2026 regime slice (+$2,920 /
+$1,799)** + the week — recency-first per J's 2026-07-31 doctrine, stated not smuggled.
Drop-best fails everywhere (week ex-Tue −$356). Chop days fire 19-31 rescues (Wed −$1,555);
a 3-rescue/day cap (probe-lane precedent) would have made the week +$4,054 and is the
staged fast-follow, deliberately NOT in the minimal patch. Friday's final cell needs the
post-16:21 re-run (below).

## Tonight's runbook (after 15:55 ET; every step reversible)

```
# 1. re-price Friday on real OPRA once the same-day 403 lifts (~16:21 ET)
backtest/.venv/Scripts/python.exe backtest/tools/ladder_rung_replay_2026_08_07.py \
    --ledger 2026-08-07 --sides C --no-est --out-tag friday-final
#    If the full-day Friday bull-only added cell goes NEGATIVE enough to flip G-WEEK
#    (week added <= 0), STOP — do not arm; file the cell and report.

# 2. apply the dormant patch (verified: git apply --check rc 0 on 3b3072a9's tree)
git apply analysis/arm-ladder/score-ladder-rung-2026-08-07.patch

# 3. flip the guards from RED-proof mode to enforcing: in
#    backtest/tests/test_score_ladder_rung_2026_08_07.py remove the two
#    @pytest.mark.xfail(...) decorators (admit + producer tests). Same commit as step 2.

# 4. verify
backtest/.venv/Scripts/python.exe -m pytest \
    backtest/tests/test_score_ladder_rung_2026_08_07.py \
    automation/state/fleet/test_probe_arm.py \
    automation/state/fleet/test_full_send_arm.py -q
#    expect: rung suite 10 passed + 1 (accounts guard) -- see step 5 note; fleet suites green.

# 5. ARM (accounts.json gate_override; SAME commit must update
#    test_live_accounts_carry_no_rung_key_yet to assert the intended keys):
#      risky-3 gate_override += "score_ladder_rung": 7
#      risky-1 gate_override += "score_ladder_rung": 8
#    safe-3 / safe-2 / bold-2: NO key (binary controls).

# 6. commit via commit_scoped.py (patch files + tests + accounts.json), report for REVOKE.
```

**REVOKE (J, any time, no deploy):** delete the two `score_ladder_rung` keys from
`automation/state/fleet/accounts.json` — next tick is byte-identical binary. The patch
itself can also be reverted wholesale (`git revert` of the ship commit).

**Monday watch-items:** (a) per-day rescue count per arm — if a chop day fires >5 rescues,
the 3/day cap fast-follow gets its live evidence; (b) `pdt_enforced` is `false` on both
risky arms (live truth, mirrored in the replay) — the lane adds day-trades that a future
enforcement flip would cap at 3/5d; (c) forward paper ledger vs this replay's Friday cell
(EST calibration was mean −$0.085 on 22 priced ticks).

## What the patch does (mechanism in one breath)

For an arm carrying `gate_override.score_ladder_rung`, a SCORING-refused tick whose ONLY
active bull blockers are DEMOTABLE {5 ribbon-stack, 7 vol-divergence, 8 VIX-soft, 10 buyer
pressure} enters when the logged bull_score (= 11 minus one point per blocker,
filters.py:1273 — the demerits ARE the score) clears the arm's rung. NON-DEMOTABLE stays
absolute on every rung: filter 1 (entry window), 6 (spread), 9 (VIX hard cap), 11
(trigger-count + level-tied — the −$103/entry 0%-WR bare-confirmation cohort), 12 (sweep),
risk_gate (Rule 4/5/6/7), $0.30 premium floor, EOD flatten. Bull only. Absent key =
byte-identical binary (C14 guard). This is NOT filter deletion, NOT filter-8 relax, NOT
the killed raw-floor lane — per-arm score-conditional admission with the safe arms as the
in-fleet control.

## The patch (dormant — NOT applied; market was open during this build)

Also on disk at `analysis/arm-ladder/score-ladder-rung-2026-08-07.patch`
(`git apply --check` → rc 0).

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
