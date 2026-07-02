# GATE PROVENANCE AUDIT — 2026-07-02

> J's directive: *"What other rules could possibly block us? Run the scenarios… I'm tired of 'the engine saw it, didn't act.' We have three risky accounts — if we're one gate away from a trade, a risky account should take it. Claude made a bunch of these rules, not me."*
>
> Scope: every control between **signal scored** and **order placed**, both paths (heartbeat_core → engine_cli/gates.py + fleet_live/shared-signal). Ledger window: **2026-06-02 → 2026-07-02** (4,082 core ticks + 4 fleet arms ~3,900 rows). Raw counts + scenario rows: [`analysis/gate-audit-2026-07-02.json`](../../analysis/gate-audit-2026-07-02.json).
>
> READ-ONLY audit — no engine/params file touched (heartbeat_core.py under separate surgery tonight). The `first_entry_lock`/`quality-lock` deletion is happening separately per J's order; it is scored here only as the **type specimen**.

---

## 1. Inventory — every control between score and order

Legend — **Prov**: J = J-ratified (rule/changelog citation), C = Claude-invented. **Ev**: scorecard in `analysis/recommendations/` (cited) or NONE. **Blk30d**: blocked would-be entries, last 30 days, as *episodes* (distinct signal, not tick-spam rows; raw row counts in the JSON). **Verdict**: KEEP / RELAX-FOR-RISKY / KILL-CANDIDATE / UNKNOWN.

### A. Safety class (never relax — J's 10 rules + SEC-style fail-closed)

| # | Control | Where | Prov | Ev | Blk30d | Verdict |
|---|---|---|---|---|---|---|
| S1 | Daily kill-switch (−30%/−50% SoD, per-account) | risk_gate.py:321-333 + circuit-breaker.json | J (Rule 5) | rule | 0 | KEEP |
| S2 | PDT check (≥3 DT & <$25K) | risk_gate.py:339-344 | J (Rule 7) | rule | 0 | KEEP |
| S3 | Broker FLAT-verify before entry | heartbeat_core.py:966 + risk_gate.py:351 (C11/L47) | J (Rule 4) | rule | 20 eps (NOT_FLAT: 15 core + 21 extra-rows) — *working as intended: position was genuinely open* | KEEP |
| S4 | Per-trade risk cap 30%/50% + v15 tier max-premium | risk_gate.py:395-426 | J (Rule 6) | rule | 2 eps (RISK_DENY_RISK_CAP ×6 rows, all extra setups at shrunken equity) | KEEP |
| S5 | min_contracts ≥3 (2 TP + 1 runner) | risk_gate.py:381-386 | J (Rule 6) | rule | 0 core (blocks Bold vwap_cont arming — documented) | KEEP |
| S6 | Entry ceiling 15:00 ET (`entry_no_trade_after_et`, FIX1) | heartbeat_core.py:148-164, 936; fleet_live.py:215-229 | J (v15.1 "theta will kill us after 3") | doctrine | 0 since FIX1 shipped | KEEP |
| S7 | Entry floor 09:35 (`entry_no_trade_before_et`) | filters.py:1075-1087 (scoring blocker 1) | J (v15) | doctrine | 0 — **BUT SEE FINDING F3: it leaked. Safe+Bold PLACED at 09:30:03 today** (trigger bar = prior-session bar passes the bar-time check; no wall-clock check) | KEEP + FIX |
| S8 | One-entry-per-tick (`SKIP_TICK_ENTRY_TAKEN`) | heartbeat_core.py:1137-1176 | C (2026-07-01) | none needed (one-position invariant) | 1 ep | KEEP |
| S9 | EOD flatten 15:55 / time stop 15:40 | Gamma_EodFlatten + exit path | J | rule | n/a (exit) | KEEP |
| S10 | risk_gate fail-closed on unreadable input | risk_gate.py:226-315 | C (SEC 15c3-5 pattern) | design | 1 ep (risky-3 "premium missing" ×4 — a *feed* gap, not a gate) | KEEP |

### B. Engine entry gates (gates.py GATE_ORDER, armed via params)

| # | Gate (params key) | file:line | Armed | Prov | Ev | Blk30d | Verdict |
|---|---|---|---|---|---|---|---|
| G1 | block_level_rejection | gates.py:246-254 | Safe✓ Bold✗ | C (auto-ratified OP-22) | level-rejection-gate-01.json (WF 0.842) | 0 | KEEP |
| G2 | trendline_requires_ribbon_flip | gates.py:256-264 | neither | C | none | 0 | dormant — ignore |
| G3 | **block_elite_bull + VIX band** | gates.py:266-277 | Safe [0,25)✓ Bold [15,18)✓ | C (auto-ratified) | safe_block_elite_bull_all_vix.json (WF 3.89); block_elite_bull_vix_high_18.json | **18 eps / 90 rows — #1 blocker** | **RELAX-FOR-RISKY** (Safe [0,25) = a de-facto permanent ELITE-bull ban; keep on Safe, drop/narrow on risky arms) |
| G4 | block_bull_ribbon_flip | gates.py:279-282 | neither (key absent both params) | C | cohort A/B (chef-bull-scope-ab) | 0 | dormant — ignore |
| G5 | block_bull_1100_1200 | gates.py:284-291 | Safe✓ Bold✗ | C (auto-ratified) | safe_bull_1100_1200_gate.json (OOS n=1!) | 0 | UNKNOWN — evidence thin (n_oos=1); A/B re-run spec'd §5 |
| G6 | block_bull_morning_agg | gates.py:293-303 | ✗ (J ordered removed 2026-06-24) | C→J-killed | agg_block_bull_morning_afternoon.json | 0 | dead — precedent for G3 relax |
| G7 | **require_bearish_fill_bar** | gates.py:305-318 | Safe✗ Bold✓ | **J-ratified 2026-06-17** ("i apprve to ad d this") | fill-bar-gate-sweep.json (OOS +$1,153, WF 18.5 — Bold; Safe REJECTED) | **7 eps / 21 rows — #2 blocker** | KEEP on Bold control; **RELAX-FOR-RISKY-LOOSE** (also remove from `_HARD_SKIP_VERDICTS` for loose arms — see F4) |
| G8 | **min_ribbon_momentum_cents** | gates.py:320-328 | Safe **=0 → SEMI-ARMED (BUG)** | J-ratified v15.3, then **J-reverted** (L107: gate removed profitable trades, WF −1.308) | reverted evidence NEGATIVE | **3 eps / 16 rows that should be 0** | **KILL-CANDIDATE #1** — see F1 |
| G9 | max_ribbon_duration_bars | gates.py:330-341 | Safe=999 (truly inert: window 150 < 999) | J-reverted (L107) | negative | 0 | KILL (remove key for hygiene) |
| G10 | midday_trendline_gate | gates.py:343-351 | ✗ both | mixed | negative on Bold | 0 | dead — ignore |
| G11 | block_conf_lvl_rej_midday_afternoon | gates.py:353-363 | ✗ both | C | removed 06-18 (WF 0/6) | 0 | dead |
| G12 | block_conf_lvl_rec_afternoon | gates.py:365-375 | Bold✓ (documented "KEPT but DEAD") | C | zero-impact | 0 | KILL (hygiene) |
| G13 | entry_bar_body_pct_min (bear doji) | gates.py:377-383 | Safe 0.20✓ Bold✗ | C (auto-ratified) | safe_entry_body_gate.json (WF 7.19, OOS +$566) | 2 eps / 5 rows — **both today, both would-be winners** (see scenario 4) | KEEP on Safe; RELAX-FOR-RISKY |
| G14 | entry_bar_body_pct_min_bull | gates.py:385-395 | ✗ both | C | none | 0 | dormant |
| G15 | vix_bear_hard_cap | gates.py:397-401 | Safe 23.0✓ Bold✗ | C (auto-ratified) | safe_vix_bear_hard_cap.json (cleanest gate, SW 0/3) | 0 (VIX <19 all month) | KEEP |
| G16 | structure_veto (SKIP_STRUCTURE_VETO) | engine_cli.py:567-590 | Safe✓ Bold✗ (key absent) | C (2026-06-26 −$237 incident) | A/B thin (IS +$583, OOS $0) | 0 | KEEP (fail-open, protects 5/04 anchor) |

### C. Scoring-side hard blockers (filters.py — before the gates)

| # | Control | Where | Prov | Blk30d | Verdict |
|---|---|---|---|---|---|
| F10a | min_triggers (bear 1 / bull 2 Safe; bull 1 Bold) | filters.py:953-959, 1303-1311 | J (v11/v12 asymmetry, ratified) | inside 3,871 HOLDs (not separable in ledger) | KEEP; already the fleet gate axis |
| F10b | level_tied_required | filters.py:957, 1309 | J (Rule 1: no setup no trade) | ditto | KEEP |
| F8/9 | VIX entry thresholds + volume filter 9 (0.7×) | filters.py:1108-1138 | J-era ratified | ditto | KEEP |
| Fmacro | macro_hard_veto_minutes=120 | params only — **NOT WIRED into heartbeat_core/engine_cli** (was LLM-heartbeat prose; LLM retired 06-25) | J doctrine | 0 (dead knob, C14) | UNKNOWN — decide: wire or delete key |

### D. Post-verdict, pre-order (heartbeat_core exec path)

| # | Control | Where | Prov | Ev | Blk30d | Verdict |
|---|---|---|---|---|---|---|
| X1 | **quality-lock** (`SKIP_QUALITY_LOCK`) + first_entry_after_stop lock | heartbeat_core.py:718-867, 975-980; risk_gate.py:363-376 | **C** (orchestrator-parity port 2026-06-25; params note says "was in risk-rules.md doctrine" but no J ratification of the live port) | NONE (no A/B ever) | 3 eps / 19 rows — **cost today's 11:46 winning bear re-entry** | **TYPE SPECIMEN — J ordered DELETED (separate change tonight). Excluded from ranking.** |
| X2 | 2-free-model veto (`VETOED_BY_MODELS`) | heartbeat_core.py:495-554 | C (2026-06-25 design) | NONE | **0 vetoes in entire ledger history** | UNKNOWN — it has never fired; either it's free insurance or a dead latency tax. Spec: log votes for 30 more days; if still 0 vetoes AND 0 saves, demote to async shadow. |
| X3 | NO_PREMIUM / EQUITY_FETCH_FAIL | heartbeat_core.py:1005, 960 | C (fail-closed) | design | ~1 ep | KEEP (infra guard, not a gate) |
| X4 | PLACE_FAIL when exits not engine-managed (C2) | heartbeat_core.py:1047-1052 | C (C2 doctrine: no stopless entry) | doctrine | 4 eps / 16 rows (the G1 arm-both-flags scar) | KEEP — but env-flag wiring must be guarded (run-heartbeat-core.ps1 sets both) |
| X5 | extra-setup exec-arm map (`extra_setup_exec_armed`) | heartbeat_core.py:1128-1134 | J-ratified (trade-to-learn 2026-07-01) | per-setup scorecards | 4 eps WATCH_NOT_ARMED (gap_and_go — deliberately unarmed) | KEEP |
| X6 | G15 tz-crash in `_prior_fill_stopped` | heartbeat_core.py:798-809 | bug, **fixed today** (guard test_tz_quality_lock_2026_07_02) | — | 6 ERROR ticks 11:50-11:55 killed Bold's ALLOW path | fixed; dies with X1 anyway |

### E. Fleet path (shared-signal → fleet_live → arms)

| # | Control | Where | Prov | Blk30d | Verdict |
|---|---|---|---|---|---|
| E1 | passed derives from production verdict (base path) | build_shared_signal.py (v1 default) | C | structural: **no arm can be looser than production on the base path** | RELAX — scoring-peak already mitigates (live since 06-25) |
| E2 | `_HARD_SKIP_VERDICTS` = {SKIP_BULLISH_FILL_BAR…} in scoring-peak | build_shared_signal.py:469-477 | C, no A/B | today: made Bold's fill-bar SKIP binding on the loose arms' scoring-peak block too | **RELAX-FOR-RISKY** (fold into gate-profile tiers) |
| E3 | Signal staleness 420s | fleet_live.py:48 | C | ~0 | KEEP |
| E4 | gate_override min_triggers 2 / require_confluence (tight arms) | accounts.json grid | J-sanctioned grid design (2026-06-25) | 15 rows "1 triggers < 2" (tight arms sat out today's 11:49 bear — by design) | KEEP (it IS the experiment) |
| E5 | "A+ gate: confidence missing, need >= 0.65" (safe-3) | fleet strategies/executor | C | 4 rows — **blocks on a field the signal never carries = always-block when it fires** | **KILL-CANDIDATE #4 (fix or remove)** |
| E6 | per-arm circuit breaker + first-entry-lock.json prior stops | fleet_live.py:111-147 | J (Rule 5) / C port | 0 | KEEP breaker; prior-stops follows X1's fate |
| E7 | cap-aware qty auto-reduce | fleet_live.py:190-199 | C (fixes silent RISK_CAP starve) | enabling, not blocking | KEEP |

---

## 2. Top-5 blocked scenarios (real ledger rows; SPY-forward from subsequent ticks)

**#1 — TODAY'S LOCKOUT, 2026-07-02 11:46→12:15 ET (quality-lock + fill-bar + tz-crash, compounded).**
Safe scored **ENTER_BEAR** (TRENDLINE, 1-trigger) on *every tick* 11:46–12:15 @ SPY 745.38→743.86. All killed by `SKIP_QUALITY_LOCK` (rank 1 = prior rank 1; the 09:30 bear entry held the lock; leg-2 gap arithmetic never re-opened it). Bold scored the same bear but `require_bearish_fill_bar` skipped 11:46-11:49 + 12:11-12:15, and the **G15 tz-crash killed its quality-lock ALLOW path 11:50-11:55 (6 ERROR ticks)**. SPY −0.87 in 30m, **−2.10/−2.34 in 60m** — a clean winner. Entry finally happened 12:51 (both PLACED, ~$2.50 of SPY move surrendered). **The three risky arms partially caught it:** safe-1 + risky-3 (loose) ENTER_BEAR 11:49, placed=True; safe-3 + risky-1 (tight) blocked by their own `min_triggers 2` — so J's "a risky account should take it" *did* happen on 2 of 4 fleet arms, but both CORE accounts he watches sat out.

**#2 — block_elite_bull, 2026-07-01 11:21 + 11:31 (Safe+Bold).** BULLISH_RECLAIM ELITE (`level_reclaim+confluence`, VIX 16.2) blocked at SPY 748.47/749.29; +30/60m: 0.00/+0.57 and −0.48/−0.30 — a scratch. **Counter-case 2026-07-02 10:16:** same block at 750.98 → SPY **−4.13/−4.87** — the gate saved a full stop-out. This gate is doing real (mixed, net-positive-per-its-scorecard) work on Safe — the problem is it fires ~4×/week and NOTHING in the fleet trades the blocked cohort, so we never collect live evidence either way.

**#3 — require_bearish_fill_bar (Bold), 2026-07-02 11:46/12:11/12:52.** Three bear signals blocked; SPY next 60m: −2.10, −2.34, −2.32 — all three would have won. Counter-case 06-25 14:10 (+2.50 = saved) and 07-02 13:54/14:04 (+2.62/+2.74 = saved). Net today it was the wrong day for the gate; its scorecard (OOS +$1,153, WF 18.5) still stands. Correct move is not deletion — it's that the loose risky arms shouldn't inherit it via `_HARD_SKIP_VERDICTS` (E2).

**#4 — SKIP_DOJI_ENTRY_BAR (Safe), 2026-07-02 12:56–13:00.** Bear signal on a small-body bar @742.90; SPY −1.55/−1.94 next 30/60m — 2 would-be winners blocked while Bold (gate off) was already in the 12:51 put. Evidence-backed on Safe (WF 7.19), but this is exactly the class a risky arm should take.

**#5 — SKIP_RIBBON_MOMENTUM_GATE (Safe), 06-25 14:10 / 06-26 10:36 / 06-26 15:51 — the gate that shouldn't exist.** `min_ribbon_momentum_cents=0` was set as "Gate A DISABLED" (L107 revert), but `gates.py:322` treats **0 as an armed threshold** (`is not None`) — it blocks any entry where ribbon spread *narrowed* over 3 bars. 16 rows / 3 episodes on a gate J reverted for being harmful. Outcomes mixed (+2.50, −0.58, +0.17), but that's irrelevant: **the ratified config says OFF, the engine runs it ON.** (Bold is immune only because its params file lacks the key.)

**Bonus anti-story (gates misallocated):** while the quality-lock was blocking Safe's winning bear re-entry at 11:46, the same account's `vwap_continuation` extra-setup path **PLACED 6 CALL entries between 09:55 and 10:25 into a −4.9 SPY slide** (equity 1692→1517 across the rows) — the churn J's actual rules (Rule 4: new trigger required) exist to stop went unblocked, because the extra-setup route re-fires on the same morning signal and the quality-lock keys per-setup rank ties don't catch same-rank re-entries after non-stop exits. The lock punished the right trade and missed the wrong one.

---

## 3. KILL / RELAX ranked list (expected trades-unblocked per week)

Excluded: X1 quality-lock (already ordered deleted — ~0.7 eps/wk on core, would be rank #2).

| Rank | Item | Action | Trades unblocked/wk | Risk |
|---|---|---|---|---|
| 1 | **G3 block_elite_bull on RISKY arms** (keep Safe/Bold controls) | remove from risky gate-profile | ~4.2 eps/wk (the #1 blocker; 90 rows/30d) | Scorecard says the Safe cohort is net-negative — that's WHY it goes to risky arms only, at bold sizing floor qty; live data settles it |
| 2 | **G8 min_ribbon_momentum_cents=0 semi-armed BUG** | fix: treat 0 as off (gates.py `if _rmom_thresh:` or pop the key from Safe params) + graduated guard | ~0.7/wk on SAFE (core account!) | none — restores the RATIFIED L107 revert; current state is a C14 inverse (knob believed dead, actually alive) |
| 3 | **E2 `_HARD_SKIP_VERDICTS` fill-bar hard-skip for loose arms** | make per-arm (loose arms ignore it) | ~1.6/wk on risky-3/safe-1 | fill-bar stays on Bold control where it's validated |
| 4 | **G13 doji gate on RISKY arms** | remove from risky gate-profile | ~0.5/wk | validated on Safe only; Bold never had it |
| 5 | **E5 safe-3 "A+ confidence" gate** | fix (populate confidence) or delete | ~0.2/wk | it can never pass as written — pure dead-block |
| 6 | G9/G12 hygiene (duration=999, conf_lvl_rec Bold) | delete keys | 0 (inert) | removes future foot-guns |
| 7 | F3 09:35 floor wall-clock leak | add `now_et >= 09:35` check beside the ceiling check | −1 trade/wk (this *adds* a block) | it's J doctrine; today's 09:30:03 entries violated it |
| 8 | X2 model-veto | 30-day vote audit, then demote-or-keep | 0 direct | latency/token cost only |

---

## 4. Per-arm gate-profile design — gate-strictness AS the risk profile

**Doctrine fit:** arms are RISK profiles, not strategies. The 2×3 grid already varies `min_triggers`; this extends the gate axis to the **full gate stack** — same strategy menu everywhere, different *tolerance*. Exactly what J asked for: "if we're one gate away, a risky account should take it."

### Tier definitions

**NEVER-RELAX (all tiers, hard floor):** kill-switch (S1) · PDT (S2) · flat-verify (S3) · risk caps + tier max-premium (S4) · min_contracts (S5) · entry floor 09:35 **wall-clock-fixed** (S7) · entry ceiling 15:00 (S6) · one-entry-per-tick (S8) · EOD flatten/time-stop (S9) · fail-closed input handling (S10) · level_tied_required (F10b — Rule 1) · catastrophe −50% cap.

| Gate | SAFE (full stack) | BASE (control) | RISKY (minimum viable) |
|---|---|---|---|
| min_triggers | 2 + confluence/sequence (tight) | production (bear 1 / bull 2) | 1 |
| block_elite_bull | ✓ [0,25) | ✓ per account params | **✗** |
| require_bearish_fill_bar | per account params | per account params | **✗** (and not inherited via _HARD_SKIP) |
| entry_bar_body_pct_min (doji) | ✓ 0.20 | per account params | **✗** |
| block_bull_1100_1200 | ✓ | ✓ | **✗** |
| vix_bear_hard_cap | ✓ 23 | ✓ 23 | ✓ 26 (wider, never off — VIX≥23 evidence is the cleanest gate) |
| structure_veto | ✓ | ✓ | ✓ (fail-open, protects the 5/04 anchor — keep everywhere) |
| block_level_rejection | ✓ | per account params | **✗** |
| free-model veto | ✓ | ✓ | **✗** (sync latency cut; votes still logged async) |
| min_ribbon_momentum / duration | OFF (bug-fixed) | OFF | OFF |

Mapping to the existing grid: SAFE tier = safe-3/risky-1 (tight), BASE = safe-2/bold-2 (controls, untouched), RISKY = safe-1/risky-3 (loose). No new accounts needed — the loose arms *become* the minimum-viable-stack arms.

### Config expression (one evening, each step guarded + single-key revertible)

1. **accounts.json**: extend each fleet arm's `gate_override` with a `"gate_profile": "safe"|"base"|"risky"` key + a `"gate_params"` dict of explicit gate-key overrides (e.g. risky: `{"block_elite_bull": false, "require_bearish_fill_bar": false, "entry_bar_body_pct_min": 0.0, "hard_skip_verdicts": []}`). Absent key = today's behavior byte-identical.
2. **build_shared_signal.py**: emit the RAW two-sided scores + triggers + gate verdict per side (it already carries most of this); make `_HARD_SKIP_VERDICTS` read the arm's `gate_params.hard_skip_verdicts` at consume time instead of a module constant. Guard: `test_shared_signal_scoring_peak_per_arm`.
3. **fleet_executor.plan_all**: apply the arm's `gate_params` when deriving passed/qualifying (it already applies `min_triggers`/`require_confluence_or_sequence` — this generalizes the same mechanism). Guard: replay_fleet_arms A/B — risky profile must reproduce today's 11:49 entry AND add the 10:16 elite-bull entry.
4. **G8 bug fix**: `gates.py:323` → `if _rmom_thresh:` (0/None both off) **or** remove the key from Safe params. One line + graduated guard `test_g8_momentum_zero_is_off` (REDs on regression). *(Engine file — schedule after tonight's surgery lands.)*
5. **Measurement plan**: `fill_funnel.py` per arm, N=10 trading days: signals-seen → gate-passed → placed → filled → P&L per tier. Compare RISKY vs BASE control per the existing `promotion_gate` (OOS+, WF ≥0.70, beat-control margin with multiple-comparison correction). If the relaxed cohort bleeds, the revert is per-arm single-key (`gate_profile: "base"`).
6. **Revert:** delete `gate_profile`/`gate_params` keys → byte-identical current behavior.

Per-day cost: $0 (same ticks, same feeds; free-model veto removal *reduces* token use). OP-3 clean.

---

## 5. UNKNOWNs needing an A/B (spec'd)

1. **G5 block_bull_1100_1200** — OOS n=1. Spec: re-run the 4-way A/B on fresh OPRA through 2026-07-01, Safe config, cascade-adjusted; kill if OOS_delta ≤ 0 or WF < 0.70.
2. **X2 model-veto value** — 0 vetoes ever. Spec: 30-day vote ledger audit (`free_eval.votes`), count would-have-vetoed dissents vs realized trade outcomes; if veto-correlation with losers < chance, demote to async shadow.
3. **Fmacro macro_hard_veto** — dead knob on the deterministic path. Spec: decide wire-or-delete; if wired, A/B on event-day cohort (FOMC/CPI/NFP dates) before arming.

## 6. Bug/leak findings (filed, not fixed here — engine under surgery)

- **F1 (G8):** `min_ribbon_momentum_cents=0` is SEMI-ARMED on Safe — gates.py treats 0 as a live threshold; blocks narrowing-ribbon entries. 16 rows/30d on a J-reverted gate. Fix = 1 line or key removal + guard.
- **F2 (X6):** Bold quality-lock tz-crash — already fixed today (guard `test_tz_quality_lock_2026_07_02`); dies with the lock deletion anyway.
- **F3 (S7):** 09:35 entry floor leaks at the open — 09:30:03 PLACED entries today (trigger bar = prior-session bar passes the bar-time check). Needs a wall-clock floor beside the FIX1 ceiling.
- **F4 (E2/E1):** loose fleet arms inherit Bold's fill-bar skip through `_HARD_SKIP_VERDICTS`, and the base signal path can never be looser than production — both fold into the gate-profile design.
- **F5 (churn):** vwap_continuation re-placed 6× (09:55–10:25) into a −4.9 slide on Safe — the extra-setup route lacks the Rule-4 "new trigger" re-entry discipline the quality-lock was *supposed* to provide. When X1 is deleted, replace with a per-setup **stop-based** cooldown (J's actual rule: re-entry only after a NEW confirmed trigger), not a quality-rank lock.
- **F6 (E5):** safe-3 "A+ gate: confidence ≥ 0.65" blocks on a field the signal never populates — always-block. Fix or delete.

---

*Ledger evidence: `analysis/gate-audit-2026-07-02.json` (verdict/action/exec counts, per-gate episode counts, scenario rows with SPY +30/60m, today's full 11:00-12:59 window, per-fleet-arm reason histograms).*
