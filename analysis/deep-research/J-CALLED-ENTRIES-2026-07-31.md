# J-CALLED ENTRIES REPLAY — 2026-07-31 (+ 07-30)

**Lane:** replay J's four post-close called entries · verify tape · name the refusing mechanism · price them on real OPRA · one-mechanism candidate spec for lane 4.
**Frozen pre-reg:** `backtest/tools/j_called_entries_replay_2026_07_31.py` module docstring, et_clock `2026-07-31 16:51:57 Friday EDT` (stamped BEFORE any fetch/run). All cells reported.
**Data:** SIP 5m SPY (`backtest/data/spy_5m_2026-05-19_2026-07-31.csv`) · real OPRA 5m (Alpaca v1beta1, fetched in-memory) · `automation/state/core-decisions.jsonl` · `journal/trades.csv` broker fills.
**Label:** n=4 (+1 alt) **ANECDOTE**. Hindsight-narrated entry *timing* (J called these after close); the *mechanism* evidence is NOT hindsight — three of four had detectors fire LIVE in the decision log at/near the called minute (see grade table). Nothing here arms anything.

---

## 1. Tape verification (SIP, bar by bar)

**J is verified to pennies on 3 of 4 anchors; every deviation found is stated here.**

| # | J's words | SIP truth | Verdict |
|---|---|---|---|
| e1 | "long off the 737.68 wick/bottom ~10:15–10:20" | 10:15 bar low **737.68 EXACT** = RTH low of day; bar closes back up 738.605. Inside our SHELF_737.05_738.65 (w5). | ✅ exact |
| e2 | "long ~11:30 at the 739.7x level" | 11:30 bar low **739.81**, closes 740.74; our shelf line is 739.73 (J earlier called 739.72 — 1c from file). Tape bounce printed **8c above** the shelf line, i.e. inside the zone, not a penny-touch. | ✅ zone-true (8c) |
| e3 | "~12:10–12:15 off the 742.97-retest bounce, primo entry" | Retest lows 12:05 **742.46** / 12:15 **742.78**; SIP premarket low is **742.79 @ 08:40**, not 742.97 (−18c vs J's number; our file: MEMORY_RES 742.90, SHELF 743.25). 12:10 bar closes 743.55 = first close above the 743.25 shelf. | ✅ structure right, pm-low figure −18c off |
| e4 | 07-30 "737.6–737.85 line: rode 10:05–10:20, flipped on the dump, broke back through on the 12:00 power candle, bounced 12:40 and rode" | 10:05–10:20 lows 737.38–737.62 riding the line ✅ · dump to RTH low 734.59 @ 11:15 ✅ · 12:00 bar closes **738.28** on 770K vol (2× neighbors) ✅ · 12:40 retest low **737.755** inside the line, then 13:00→739.95, day high 742.45, close 741.71 ✅ | ✅ all four beats |
| — | (brief context) "close ~748.5 area" 07-31 | 15:50 close 748.595 ✅; the final 15:55 bar sold to 746.82. | ✅ w/ final-bar note |

The anchors J keeps calling are the **persistent w5 shelves in our own levels file** (737.05–738.65 band, 739.73, 743.25/742.90). The 07-30 line 737.6–737.85 sits inside the same 737.05–738.65 multi-week shelf that framed 07-31's low.

---

## 2. What the engine saw at each moment (core-decisions.jsonl, account=safe; bold mirrors)

Bull filters legend: F5 ribbon BULL-stacked · F7 vol-divergence · F8 VIX<17.20-or-falling · F10 buyer pressure · F11 triggers. **Entry pass is binary: all 11 filters (score 11).**

| # | Window | Raw detections | Score path | Named refusing mechanism |
|---|---|---|---|---|
| e1 | 10:14–10:35 | `level_reclaim`+`confluence` raw from 10:14; **shadow `wick_reclaim` LIVE-fired 10:21–10:35** (6 min after the wick) | peak 9–10, never 11 | **Blockers {5,8,10}** — ribbon stack is definitionally BEAR at a V-bottom, VIX rising during the crash, buyer-pressure marginal. No verdict but HOLD ever printed. |
| e2 | 11:29–11:45 | 11:29–11:35: **no trigger at all** (price held ABOVE the shelf — `detect_level_reclaim` requires `low<level<close` cross, a touch-and-hold can't fire it); **shadow `pullback_hold` LIVE-fired 11:41–11:45**, `wick_reclaim` 11:36+ | 7–9 | **Missing trigger class** (touch-and-hold at a level) + blockers {5,8}/{8,10} on the confirm bars. |
| e3 | 12:00–12:30 | `level_reclaim`+`confluence` @ **743.25**; 12:16–12:18 **bull 11/11 PASSED**, tier ELITE (again 12:27–12:30) | **11** | **`block_elite_bull` — the ONLY refusing mechanism.** `SKIP_ELITE_BULL_LEVEL_RECLAIM`, ribbon BULL, htf BULL, VIX 17.2. 111 such skips 09:31–15:55 (55 safe + 56 bold). |
| e4 | 07-30 all RTH | **`levels_active` = [] on 776/796 rows — the engine was level-BLIND all session** (root-caused + repaired that evening: `analysis/deep-research/BLIND-ENGINE-REPAIR-2026-07-30.md`). Only self-anchored detections possible; shadow `trendline_reclaim` fired 11:55–12:25. | ≤9 | **Empty level feed** → no level trigger could exist; the 12:00 reclaim and 12:40 retest were invisible. Worse: the engine went the OTHER way — `ENTER_BEAR` 11:31–11:46 near the low (risky-3 filled 733P/734P, **−$275** broker-true), bold blocked by `require_bearish_fill_bar`. Under the shipped SKIP_NO_LEVELS rail those 11 ENTER_BEARs are now refused. |

**Cross-check that the signal was tradeable:** the ungated fleet arms took e3's exact signal live — risky-3 `ENTER_BULL` 12:19 (trigger_level **743.25**, 746C @ 0.33, +$126 on the position) and safe-3 12:31 (747C @ 0.30, +$75). Day P&L: risky-3 +$45.60 (a later 13:25 re-entry gave back $80), safe-3 +$74.88 — the week's first green day, produced by the one signal class the cores refused ×111.

---

## 3. What each would have PAID (real OPRA replay — **n=4 ANECDOTE**)

Conventions (frozen pre-run): fill = open of first OPRA 5m bar ≥ trigger-bar close; qty 3; exits via the REAL `exit_manager.plan_exit_actions` (`walk_exit_manager`), entry+1 strict; structure stop at the named level, catastrophe −50%; time stop 15:50. Ribbon flip-back exits cannot fire (ribbon_tick_df=None — disclosed; on these paths price never returned to the levels, so structure stops never triggered either). Full legs in `J-CALLED-ENTRIES-2026-07-31.json`.

| # | Contract (ATM=round(trig close)) | Fill | MFE / MAE after fill | CORE-CONTROL (tp1 1.0/.667, trail .15) | ZONE-RIDE (trail .20) | HOLD-to-15:45 (diagnostic) |
|---|---|---|---|---|---|---|
| e1 | SPY260731C00739000 | 10:20 @ $1.98 | +392% / **+9.6%** (never below fill) | **+$550.75** (runner_stop 3.53) | +$530.00 | +$2,142 |
| e2 | SPY260731C00741000 | 11:35 @ $1.46 | +434% / +5.5% | **+$605.85** (runner_stop 4.60) | **+$914.00** (rode to time_stop) | +$1,695 |
| e3 | SPY260731C00744000 | 12:15 @ $1.06 | +351% / −12.3% | **+$330.40** (runner_stop 2.24) | +$317.20 | +$906 |
| e4 | SPY260730C00738000 | 12:45 @ $1.51 | +276% / +7.9% | **+$522.45** (runner_stop 3.71) | +$508.00 (time_stop) | +$699 |
| e4alt | same, 12:00 power candle | 12:05 @ $1.77 | +221% / −22.6% | +$548.45 | +$534.00 | +$621 |
| **Σ primary 4** | | | | **+$2,009.45** | **+$2,269.20** | +$5,442 |

- **All 4 profitable under BOTH engine-native exit shapes.** Worst MAE −22.6% (e4alt) — no path ever approached the −50% catastrophe cap; three of four never traded below the fill at all.
- **Walk fidelity validated against broker truth:** risky-3's real 12:19 746C fill re-walked under ZONE-RIDE → +$138.60 vs +$126 broker-realized (walk ~10% optimistic: limit-level fills vs the arm's real prints 0.65/0.48). Direction and shape agree.
- Entry slippage is unmodeled (bar-open print as fill); numbers are upper-bound-flavored. The MFE column shows the conclusion survives any realistic slippage haircut.

---

## 4. Grade table — J vs engine

| # | J (post-close call, tape-verified) | Engine live behavior | Engine loss vs J (CORE shape) |
|---|---|---|---|
| e1 | LONG the wick-defense of a w5 shelf → paid | HOLD (blockers 5,8,10); its own `wick_reclaim` detector saw it — shadow-only | −$551 forgone |
| e2 | LONG the touch-and-hold at 739.7x → paid | HOLD; no live trigger class; its own `pullback_hold` detector saw it — shadow-only | −$606 forgone |
| e3 | LONG the retest-reclaim → paid ("primo") | **Scored it 11/11 ELITE and refused it 111×** (`block_elite_bull`) | −$330 forgone (cores); fleet took it +$201 |
| e4 | LONG the line-reclaim/retest → paid | Level-blind (empty feed, since repaired); **shorted the low instead** (−$275 broker-true on risky-3) | −$522 forgone + real −$275 |

J: 4/4 directionally right, to-the-penny anchors, all four paid. Engine: 0/4 taken, 1 counter-trade loss. **Engine's own detectors (live or shadow) recognized the moment in all three sighted cases** — the failures are wiring/gating, not perception.

---

## 5. THE PATTERN — one named mechanism (deliverable for lane 4's designer)

**All four calls are the same trade: a defended touch of a PERSISTENT multi-session shelf (w5) — entered on the defense, not on the late close-cross confirmation.** Three refusal mechanisms stack on top of the same blind spot:

1. **Trigger geometry:** the only live bull level trigger (`detect_level_reclaim`, `filters.py:771`) requires `low < level AND close > level` on one bar — it can only fire AFTER the move. A wick-defense (e1) or touch-and-hold (e2, e4-12:40) never crosses, so it never fires. The codebase already knows this: `detect_pullback_hold_bullish`'s own docstring names it as root cause.
2. **Trend-stack blockers:** F5 (ribbon BULL-stacked) + F8 (VIX) + F10 (buyer pressure) are definitionally lagging at a V-bottom/zone-touch — e1's entire refusal was {5,8,10}. A shelf-defense lane that inherits them can never buy a defended low.
3. **`block_elite_bull`:** kills the one variant that DOES pass (e3, 111×/day). Its evidence (24 fills, 0% WR, −$885) is 100% old-broken-feed; its own written re-eval condition ("n≥20 under corrected feed") is now the binding fact — post-fix days 07-28..07-31, and on the first post-fix day with a clean bull tape the blocked class was the only profitable signal (fleet-verified).
4. (Structural, already repaired) the whole mechanism is levels-file-dependent — 07-30's empty feed disabled every geometry; SKIP_NO_LEVELS rail now guards this.

### Candidate detector spec — `shelf_hold_reclaim` (DO NOT IMPLEMENT in this lane)

- **Anchor class (the scope, not a knob):** levels from compiler v2 with `weight ≥ 5 AND touches ≥ 3` (persistent shelves + memory levels; `key-levels.json` fields `weight/touches/span_sessions`); zone band = the file's own `zone_width` (levels-are-zones, J 2026-07-17 — band never hand-picked).
- **Admission geometries (OR, one mechanism, all at the anchor class):**
  - **A. wick-defense** = existing `detect_wick_reclaim_bullish` (low reaches zone, lower wick ≥ max($0.15, 50% of range), close ≥ level − $0.10) — LIVE-fired at e1;
  - **B. touch-and-hold** = existing `detect_pullback_hold_bullish` (dip into zone, hold ≥ k bars above zone floor, close above hold-window high) — LIVE-fired at e2;
  - **C. close-cross reclaim** = existing live `detect_level_reclaim` — at this anchor class, routed WITHOUT `block_elite_bull` until the gate re-qualifies under its own written condition.
- **Entry:** next bar after geometry confirms (entry+1, ruling 2026-07-25). Direction: bull (bear mirror = separate pre-reg, not assumed).
- **Filters kept hard:** F1 time gates, F9 VIX<22, spread sanity, SKIP_NO_LEVELS blind rail, structural no-add (C31).
- **Filters demoted to PRE-REG A/B AXES (not inherited hard):** F5 ribbon-stack {require / drop / replace-with-htf_15m≠BEAR}, F8 VIX-direction {on/off}, F10 buyer pressure {on/off}. Evidence for demotion: e1's exact refusal set {5,8,10}; e3 passed all three ⇒ they are not what distinguishes winners here.
- **Stop:** structure stop at zone floor (`level − zone_width`), catastrophe −50% cap (chart-stop-primary v15.3). **Exit lanes to A/B:** registry CONTROL vs ZONE-RIDE (this replay: ZONE-RIDE +13% over CONTROL on n=4 — anecdote).
- **Validation bar (unchanged canon):** frozen pre-reg → full-population replay through `walk_exit_manager` on real OPRA (levels-v2 retro feed per `backtest/tools/levels_v2_retro_ab.py` / `LEVELS-V2-RETRO-2026-07-28.md`) → per-trade expectancy + OOS + concentration + anchor no-regression + BH-FDR. **Graveyard respected:** no re-test of pre-TP1 trailing locks, BE-floor-via-fixed, exit-all-at-touch, zone-banded cross detector, score ladders, structure-shift standalone/cascade.
- **Prior art to cite in the pre-reg:** `pullback_hold_bull_replay.py`, `bull_elite_atm_decision_log_mining.py`, `bull_gate_atm_ssb_requalification.py` (existing bull-gate re-qual tools), PNL-ATTRIBUTION-2026-07-28 (money is level-tied: +$6,895/66tr level-tied vs −$1,830/124tr trendline-only).

### Immediate, separate, smaller fact for the designer

`block_elite_bull`'s re-eval condition is now met in spirit: its entire 24-fill/0%-WR evidence base predates the levels-v2 compiler (7b4aa3f4, shipped 07-27 evening), and on 07-31 it refused 111 rows of the only signal class that made money. Re-qualifying that ONE gate (its own n≥20-under-corrected-feed condition, via `bull_gate_atm_ssb_requalification.py`) is a narrower, faster lane than the new detector — and e3 alone is recovered by it.

---

## 6. Caveats (all of them)

- **n=4, post-close narration.** The P&L is what J's *stated* entries pay, not proof of a repeatable live policy. Timing hindsight is real for e1/e2/e4; e3 is not hindsight (the engine itself passed 11/11 and a live arm took it).
- Entry fills are bar-open prints, no slippage/spread model; walk validated ~10% optimistic vs the one broker-true cell. MFE margins (221–434%) dwarf any plausible haircut.
- Ribbon flip-back exits not modeled (df=None); on these paths structure stops also never triggered, so exit-shape differences show up only in trail/tp1/time behavior.
- 07-31 SIP file's final bar (15:55) closes 746.82 after a 748.595 15:50 close — "close ~748.5" is true of 15:50, not the last print.
- The 111-skip count is 55 safe + 56 bold (both cores gated identically); fleet's green day came from 3 fills on the same signal class, minus one giveback re-entry.
- Diagnostic columns (HOLD-to-15:45, ORACLE) are bounds, not mechanisms — listed to size the miss, never to propose "just hold".

*Analysis only: no live config, param, gate, or order was touched. Tool: `backtest/tools/j_called_entries_replay_2026_07_31.py` (read-only replay; no guard test required — no live-path change shipped).*
