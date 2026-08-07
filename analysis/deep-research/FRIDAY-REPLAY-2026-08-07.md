# FRIDAY-REPLAY-2026-08-07 — Lane 3: replay today end-to-end

**Run:** 2026-08-07, market-hours READ-ONLY lane (clock verified `python setup/scripts/et_clock.py` → `2026-08-07 12:01:30 Friday EDT market_hours=True` at session start; all replay work touched zero trading-path files).
**Tool:** `backtest/tools/friday_replay_2026_08_07.py` · raw cells: `analysis/deep-research/_friday_replay_raw_2026_08_07.json` · summary: `FRIDAY-REPLAY-2026-08-07.json`.
**Pricing labels:** every counterfactual $ cell is **EST** (BS, single least-squares IV over today's 6 real morning fills; same-day OPRA is 403-walled until ~16:21 ET). No ORACLE cells exist in this artifact. Evening re-price on real OPRA = staged addendum.
**Scope:** core lane (safe/bold) only. Fleet arms carry standing anchor-fidelity REDs (`test_anchor_pass_rate` safe-3/risky-1/risky-3, STATUS.md Known broken) — no fleet replay claims made here; fleet facts below are broker-fill facts, not replay facts.

---

## Verdict (one screen)

1. **Fidelity: GREEN.** 34/34 trigger bars replay to the live verdict on BOTH core accounts (safe 34/34, bold 34/34; full-field 33/34 safe, 34/34 bold). Both live entries (09:40-trigger → 09:46 fills; 12:00-trigger → 12:06 fills) and all 24 refusal-window HOLD bars reproduce exactly, blocker-set for blocker-set. Nothing needs quarantine on the core lane.
2. **The Wednesday spiral shape did NOT recur.** One entry per arm at 09:46-09:47, one stop at 10:01-10:02, **zero re-entries** through the whole 10:15→11:55 refusal window. The engine's next entry (12:06) came on a clean fresh signal (blockers `[]`), not a chase loop.
3. **NEW since the workflow snapshot: a second live wave at 12:06-12:07** — safe-2 3x 773C@1.11, safe-3 8x 773C@1.10, risky-1 5x 773C@1.09, risky-3 12x 775C@0.31 (bold-2 dark, PDT). Trigger bar 12:00, trigger 772.89, OPEN as of ~12:45 ET. The replay reproduces this ENTER_BULL.
4. **The 10:15 exhibit bar was blocked by FILTER 7, not filter 10.** Blocker rotation quoted below. Day-level EST cross-check: **f7-relaxed +$58 vs HEAD −$83 vs f10-relaxed −$151** (3-lot safe-core lens). Relaxing f10 alone entered one bar LATER (10:20-trigger, 773C) into the 10:40 pullback and made today WORSE. Today's tape argues the **F7 cell is the binding one** at the first refusal; it does NOT support the F10-relax story on its own. n=1 day, EST — this routes to Lane 2's frozen preregs (BULL-F10 runner + new F7 prereg), it does not ship anything.
5. **Filter 11 is a co-blocker on 12 of 24 refusal-window bars** — on those bars relaxing f7+f10 both still HOLDs. The "one rotating sole blocker" framing holds on only 9 bars ([7]×1, [10]×7, [11]×1).
6. **Morning trade = PAY-shape entry that lost (variance), not a BLEED-cohort entry.** Signature cells quoted below; neither shipped shadow rule (V-d1, V-e3) would have refused it.
7. **Tier revert first live verdict: PASS** — 774C = OTM-2 exactly as shipped, qty 12 = elite tier (SHIP-C boost correctly no-op), and the 12:07 second fill (775C@0.31 x12) is also tier-consistent. First-tick check from WEEK-ORDER-2026-08-10: **PASS both halves** (risky-3 strike = spot+2; siblings ATM).
8. **f10 volume-provenance suspicion: REFUTED within live, CONFIRMED as a live-vs-backtest hazard.** Live bar volume and vol_baseline_20 come from the SAME IEX fetch (`heartbeat_core._fetch_spy_5m`, `feed=iex` — quoted below). But IEX-vs-SIP f10 pass rates diverge on today's tape (14.3% vs 29.6%), with **5 disagreement bars all inside the refusal window** — a SIP-fed backtest battery will overstate live f10 pass rates. Direct blast-radius flag for the BULL-F10 prereg runner.

---

## 1. Fidelity replay (L3-1)

**Method** (nothing re-implemented): per 5m trigger bar, `heartbeat_core._build_payload` → `heartbeat_core._engine_verdict` (the exact functions `run_account()` calls live; engine_cli subprocess does score_bar + all gates). Injection seams (the dojo `engine_step.py` pattern):

- **Bars:** the live engine's OWN feed, refetched via the byte-identical URL shape `heartbeat_core._fetch_spy_5m` uses (`timeframe=5Min ... limit=600&feed=iex`, 7d window). Not the SIP backtest cache — the live engine has never seen SIP.
- **VIX:** the per-tick `vix` values the live engine recorded in `core-decisions.jsonl` (the exact numbers it consumed), 5m-aligned; daily MAs from the prior-days-only vix cache.
- **Levels:** the per-tick `levels_active` array from the live ledger (exact injection). Reconstructing levels from the CURRENT key-levels.json instead matches the live-recorded set on only **2/34 bars** — the intraday level refresher churns the file, so any today-replay that reads the current file is NOT replaying what live saw. The live-recorded injection sidesteps this entirely.

**Result:**

| account | trigger bars | replayed OK | verdict match | full-field match |
|---|---|---|---|---|
| safe | 34 | 34 | **34/34** | 33/34 |
| bold | 34 | 34 | **34/34** | 34/34 |

The single safe non-verdict mismatch (10:05 bar): live `bull_score 10, blockers [10]` vs replay `9, [10, 11]` — same HOLD either way. Mechanism: live ticks score against a *forming* last bar; the replay's last bar is complete. One trigger visible live on the partial bar isn't present on the completed bar, so filter 11's min_triggers flips. Same class of artifact, opposite direction, on the 12:00 entry group: live's own reclaim anchor flipped **772.89 → 773.11 mid-group** (ticks 12:06-12:08 vs 12:09-12:10); the replay (complete bar) lands 773.11, matching the last live ticks. The live 12:06 FILL is anchored at 772.89.

**Both live entries reproduce exactly** — 09:40-trigger: `ENTER_BULL C BULLISH_RECLAIM_RIDE_THE_RIBBON bull 11/11, blockers [], triggers level_reclaim+ribbon_flip+confluence, trigger 771.53, spy 772.045` field-for-field vs the live row; 12:00-trigger: `ENTER_BULL, blockers []` ditto. Zero spurious replay entries anywhere.

## 2. The live day (broker + ledger truth, updated past the 11:46 workflow snapshot)

| time ET | event |
|---|---|
| 09:46-09:47 | All 4 active arms long off the 09:40 trigger bar (771.53 reclaim): safe-2 3x772C@1.67 · safe-3 8x772C@1.33 · risky-1 5x772C@1.33 (two fills 1+4) · risky-3 12x774C@0.62. bold-2 dark (PDT). |
| 10:01-10:02 | All stopped on the 5m close 771.30 < 771.53: −$153 / −$176 / −$95 / −$204. One stop each, no re-entry. |
| 10:15-11:55 | 24 trigger bars, every tick HOLD on both core accounts while SPY ran 770.50 → 773.66. Blocker rotation in §5. |
| 12:06-12:07 | Second wave: safe-2 3x773C@1.11 · safe-3 8x773C@1.10 · risky-1 5x773C@1.09 · risky-3 12x775C@0.31, trigger bar 12:00 (772.89 reclaim, blockers cleared naturally). **OPEN at time of writing.** |

Broker-verified (risky-3 read-only GET): equity $4,946.08, SOD $5,342.98; fills 13:47:09Z buy 12@0.62 → 14:02:09Z sell 12@0.45 → 16:07:10Z buy 12@0.31.

## 3. The morning trade vs our own shipped standards (L3-2)

Factors computed by the SAME frozen code that built the signature (`entry_quality_ledger.py` rebuilt including today; ENTRY-QUALITY-2026-08-06 definitions):

| factor | 09:46 entry | historical cell (n, $) |
|---|---|---|
| b: trigger class | **tied** (771.53, level_reclaim+confluence) | tied: n=61, **+$68.4/entry, 41% WR** vs bare −$14.5 |
| a: 1m/5m structure | **BLIND** (≈3 closed 5m bars — detectors abstain) | BLIND(5m): n=54, +$780; the shipped quorum rule is abstain-not-block on early entries |
| d: V-d1 last-5 agreement | **agree (up)** | agree: n=198, +$3,038 vs disagree −$1,242 |
| e: time bucket | **0930-0959** | n=45, **+$1,050** (best morning bucket) |
| f: VWAP side | above | above: n=177, +$1,575 |
| c: dist to session extreme | fill spot 771.57 vs session high 772.34 → **0.77** (near_0.5_1.5: n=19, −$247); off trigger close 772.045 → 0.30 (hug: n=3, n-small) | the one soft cell |

**Verdict: PAY-cohort shape that lost = variance.** The BLEED signature (−$103/entry, 0% WR) requires *no structure AND bare* — this entry was tied + structure-BLIND + V-d1-agree + best time bucket. Neither frozen shadow rule fires: V-d1 agrees; V-e3/R-PRES-1m abstains under 20 closed 1m bars. The one against-cell: it bought 0.3-0.8 below a 1-minute-old session high on a PDH push (771.82) that then failed by $0.5 — the same "buy the push near the extreme" softness the c-factor flags, but that cell is n=19/-$247 descriptive, not a gate. Chop-meter context (descriptive, from today's bars): failed PDH push (−0.75 pullback) then a steady 3-hour grind 770.5→773.9 — a trend-up day after a failed open push, not the Wednesday chop archetype.

## 4. Tier revert — first live verdict (L3-3): **PASS**

- **Config as shipped** (commit `3ac1d7b2`, last night): `accounts.json` risky-3 `params_patch.strike_tier_table='bold_core_pre_ext'` → `fleet_executor._tiers_for_arm` → `V15_BOLD_CORE_PRE_EXT_TIERS` (its $2K-10K row = **OTM-2**, "the killed extension row, pre-08-04 value"). Verified in source + live accounts.json this session.
- **Strike:** broker equity $4,946 → $2K-10K band; `pick_strike(772.045, equity, 'C', pre_ext) = 774` — recomputed this session, equals the actual fill. **Strike = spot+2 ✓** (WEEK-ORDER first-tick check half 1). Siblings ATM: safe-3/risky-1 filled 772C = ATM off 772.045 ✓ (half 2). **PASS.**
- **Qty 12 = `elite_qty` at the $2K-10K bold sizing tier** (base 8 / elite 12; the 09:46 signal was tier SUPER). **NOT the SHIP-C boost**, two independent ways: 0.62 ≥ 0.50 (condition false) AND boost qty 10 < plan 12 (boost never shrinks — `fleet_executor.finalize()` requires `_b_qty > _boosted_qty`). Affordability: 12×$0.62×100 = $744, no shrink needed. As designed.
- **Second fill consistency:** 12:07 775C@0.31 x12 = OTM-2 off ATM-773 at equity ~$5.1K ✓; SHIP-C condition met (0.31<0.50) but again no-op vs plan 12 ✓.
- **Loss profile per premium dollar (morning stop):** risky-3 OTM-2 −27.4% (0.62→0.45) vs ATM arms: safe-2 −30.5% (1.67→1.16), safe-3 −16.5%, risky-1 −14.3%. Mid-pack on %, smallest notional deployed ($744 vs $501-$1,064). One trade — the per-arm OTM-2-vs-ATM A/B needs its prereg n, not today's n=1.

## 5. The refusal window + variant replay (L3-4)

**Blocker rotation, replay == live on every bar** (safe; f5/f6/f8/f9 passed throughout; filter identities from `backtest/lib/filters.py`: 7 = `_bullish_volume_divergence_failed` — red recovery bar with ≥ volume within 2 bars of a green breakout; 10 = `buyer_pressure_bar_v11` — green trigger bar + vol ≥ 0.7×20-bar baseline; 11 = min_triggers(2) + level-tied requirement):

```
10:00 [7,10,11]   10:05 [10]|[10,11]*  10:10 [7,10,11]  10:15 [7]        10:20 [10]
10:25 [10]        10:30 [7,10,11]      10:35 [7,10,11]  10:40 [10,11]    10:45 [10,11]
10:50 [7,10,11]   10:55 [7,10,11]     11:00 [10,11]    11:05 [10]       11:10 [10,11]
11:15 [7,10,11]   11:20 [10]          11:25 [11]       11:30 [7,10,11]  11:35 [7,10,11]
11:40 [10]        11:45 [10]          11:50 [7,10]     11:55 [7,10]     12:00 [] ENTER
```
(*the one live/replay field diff, §1. Sole-blocker bars: [7]×1, [10]×7, [11]×1; f11 co-blocks 12/24.)

**Variants** — in-memory `disable_filters` injected into the payload's `bull_kwargs` (engine_cli's own documented mechanism; `filters.py` untouched), sequential one-position walk through `walk_exit_manager` → the REAL `exit_manager.plan_exit_actions` (never simulator_real), safe-core shape (structure stop primary, cat −50%, TP1 +100%/0.667, trail 15% post-arm), ATM, qty 3, **all premiums EST**:

| variant | entries | trades | day P&L (EST, 3-lot) |
|---|---|---|---|
| HEAD | 2 | 09:40T stop@10:00 −$41 · 12:00T stop@12:15 −$41† | **−$83** |
| f10-relaxed | 3 | + 10:20T 773C stopped 10:45 (771.82 anchor) −$68 | **−$151** |
| f7-relaxed | 2 | 09:40T −$41 · **10:15T 772C rides 10:21→12:20 tape-end +$100 (OPEN)** | **+$58** |
| f7+f10 | 2 | identical trades to f7-relaxed | **+$58** |

† EST-walk conservative cell: the walk anchors trade 2's stop at the completed-bar reclaim 773.11 and stops on the 12:15 5m close 773.06; the LIVE position is anchored at 772.89 and still open.

**Reading it straight:** at the first refusal (10:15-trigger, the exhibit bar) the sole blocker was **f7** — its "volume-divergence" pattern (the 10:05 green push bar followed by the 10:10 red bar on ≥ volume) is exactly the shelf-before-breakout shape here, and it repeatedly co-fired through the window. f10-relax alone doesn't touch 10:15 (f7 still blocks), enters at the NEXT bar on a worse strike into the 10:40 pullback, and loses more than HEAD. **The +$4,535/2d refusal-value attribution to f10 from the 08-03 gate table gets no support from today** — today's binding-cell evidence points at f7 (and at f11's co-blocking). All EST, n=1 day: this is INPUT to Lane 2's frozen BULL-F10 prereg runner and the F7 prereg (both in flight this session as L2-3/L2-4), not a shippable conclusion.

**EST calibration honesty:** least-squares IV 0.196 over the 6 real fills; residuals −16% (the rich 1.67 print — the marketable-limit pay-up at the vertical push; the 1.33 fills 30s later price to +0.4%), +0.3%, +3.1%, +12.7%, **+29.4%** (774C stop — OTM quote noise). Directional cells only, never cents. HEAD trade 1 walk exits the same bar live stopped (10:00/10:01 ✓) but EST P&L −$41 vs live −$153, mostly the entry-print gap.

## 6. f10 provenance (C14/C7 check) — suspicion tested, not assumed

- **Within live: REFUTED.** `heartbeat_core._fetch_spy_5m` is ONE fetch (`feed=iex`); `_build_payload` computes `vol_baseline_20` from that same frame (line ~599). Bar volume and baseline cannot be cross-feed on the core path. Bull entries firing 09:46 + 12:06 confirm f10 is alive on IEX volumes.
- **Live-vs-backtest: CONFIRMED hazard.** f10 arithmetic on today's RTH bars: IEX pass rate **14.3%** (5/35) vs SIP **29.6%** (8/27); green-bar rates 42.9% vs 51.9%. **Disagreement bars 10:20, 10:25, 11:05, 11:10, 11:20 — all inside the refusal window** (SIP passes where live-IEX blocked). A 391-day SIP battery (the BULL-F10 prereg runner's population) will overstate live pass rates on exactly the marginal-volume bars the filter exists to gate. Flagged to Lane 1/2; a per-feed sensitivity cell belongs in that runner's disclosure.

## 7. Caveats

- **EST everywhere** in §5 (BS constant-IV; no skew/IV-path; residuals up to ±29%). Evening real-OPRA re-price addendum is part of the staged package below.
- **n=1 day** for every counterfactual; f7-relax's winner is OPEN at tape end (12:20), not a booked result; the full-day answer needs the 15:40/15:50 tape.
- Forming-bar artifacts (§1) bound tick-level fidelity: 1 field-diff bar in 68, plus the documented anchor flip on the 12:00 group. Verdict-level fidelity is 68/68.
- Fleet replay deliberately out of scope (standing anchor REDs); fleet statements are broker-fill facts.
- The 12:06 wave was still open at write time — day P&L will move after this artifact.

## Staged for close (Lane 3's package)

Lane 3 recommends **NO trading-path change at 15:55 from this lane** — today's f7/f10/f11 evidence is n=1-day EST and belongs to Lane 2's frozen preregs (already in flight). The only staged item is mechanical and read-only:

1. **Evening OPRA re-price addendum** (after ~16:21 ET): rerun `backtest/tools/friday_replay_2026_08_07.py variants` with real OPRA contract bars substituted for the EST frames (772C/773C/774C/775C, 1-min), append `## OPRA addendum` to this file + refresh the JSON. Guard: cells must keep their EST-vs-OPRA delta visible. Revert: git-revert of the addendum commit; no engine surface involved.
