# heartbeat v15.2 — DRAFT change proposal

> **Status: DRAFT — not deployed. J ratifies on weekend per rule 9 + OP-24.**
>
> This draft proposes targeted edits to `automation/prompts/heartbeat.md` to port two crypto-harness-validated primitives into the SPY engine:
>   - `level_reclaim` / `level_reject` with explicit close-back-margin (currently fragile to wick-only crosses)
>   - `bearish_sweep` / `bullish_sweep` as a BLOCKER on counter-direction triggers
>
> Both primitives are unit-tested + live-validated in `crypto/lib/levels.py` and `crypto/lib/sweep.py`. The v14_sweep T1 test reproduces the 2026-05-14 09:55 SPY bar (the bar that misfired the 09:58 ENTER_BULL) and correctly classifies it as bearish_sweep. Production would have BLOCKED the entry under this draft.
>
> **What this draft does NOT change:**
> - Trigger count thresholds (still ≥1 bear / ≥2 bull)
> - VIX gates, time window, score thresholds, macro bias inheritance
> - Strike selection, sizing, exit doctrine
> - Source of truth for params (still `params.json`)
>
> **Single load-bearing change:** the bullish ENTER trigger now requires the LAST CLOSED BAR's close to be `≥ 0.03%` above the level (about $0.22 on SPY at $735), AND the bar must NOT be a sweep-up of that level. Same mirror for bearish.

---

## Change A — tighten `level_reject` (replace line 346)

**Current (heartbeat.md line 346):**
```
- **level_reject** (single-bar): `bar.high > level AND bar.close < level` on last closed bar.
```

**Proposed:**
```
- **level_reject** (single-bar): on the LAST CLOSED 5m bar (close_time + 5min ≤ now_et, per v15.1 fix),
  `bar.high > level + 0.5c AND bar.close < level - 22c` (which is 0.03% below level on SPY @ $735).
  This is a CLEAN rejection — wick through, close back with margin. Source-of-truth implementation:
  `crypto.lib.levels.classify_bar_at_level(bar, level, min_margin_pct=0.05)` returns "reject" iff
  these conditions hold AND the bar was on the origin side at open.

  Wick-only crosses without margin: NO LONGER count as level_reject. Use `bearish_sweep`
  instead (below) — they're a different signal: failed-rejection / liquidity grab, NOT a
  clean rejection.
```

---

## Change B — add explicit `level_reclaim` definition (insert at line 348)

**Current:** `level_reclaim` is referenced in line 364's BULLISH trigger list but never defined in the prompt body. The model has to infer the mirror of level_reject — that's a doctrine gap.

**Proposed (insert after line 348):**
```
- **level_reclaim** (single-bar, BULLISH mirror of level_reject): on the LAST CLOSED 5m bar,
  `bar.low < level - 0.5c AND bar.close > level + 22c` (0.03% above level on SPY @ $735),
  AND `bar.open < level` (bar started below, closed above with margin — clean reclaim).
  Source-of-truth: `crypto.lib.levels.classify_bar_at_level(bar, level, min_margin_pct=0.05)`
  returns "reclaim".
```

---

## Change C — NEW gate: `bearish_sweep` blocks BULLISH entry (insert near line 350)

**Current:** No primitive exists for "failed reclaim" / "liquidity grab" / "wick-up-close-down." The 5/14 09:55 SPY bar — high 745.47 above PMH 745.43, close 744.43 below — was indistinguishable from a `level_reclaim` under the old fuzzy definition. The 09:58 ENTER_BULL fired on this in-progress bar reading. With the v15.1 closed-bar fix, the engine would now see close 744.43 — but the doctrine still doesn't tell it "this is a sweep, BLOCK the bullish trigger."

**Proposed (insert near line 350, before "BULLISH (11)"):**
```
**Sweep detection — failed reclaim / liquidity grab (NEW 2026-05-16, prevents 5/14 09:58 misfire class):**

- **bearish_sweep** (up-sweep blocks BULL): on the LAST CLOSED 5m bar,
  `bar.high > level + 16c AND bar.close < level - 36c` (about 0.02% wick excess + 0.05% close-back on SPY @ $735),
  AND prior 3 closed bars all closed BELOW level (clean prior setup, not chop).
  Source-of-truth: `crypto.lib.sweep.detect_sweeps(bars, [level], min_wick_pct=0.02, min_close_back_pct=0.05, clean_prior=3)`
  returns a SweepHit with direction "up".

- **bullish_sweep** (down-sweep blocks BEAR): mirror — bar.low < level - margin AND bar.close > level + margin
  with clean prior 3 bars closed above. Source-of-truth: same function, direction "down".

**Effect on triggers:**

- If `bearish_sweep` fires on the bullish entry's intended level: **HARD BLOCK** of `level_reclaim`,
  `multi_day_confluence`, and `sequence_reclaim` triggers tied to that level for the next 3 closed bars.
  Bullish ribbon_flip alone is insufficient per defensive level-tied requirement.

- If `bullish_sweep` fires on the bearish entry's intended level: **HARD BLOCK** of `level_reject`,
  `multi_day_confluence`, `sequence_rejection` triggers tied to that level for the next 3 closed bars.

**Rationale:** A sweep + reverse close means the level was DEFENDED, not broken. Trading WITH the sweep
direction (in this example, BEARISH after a bearish_sweep) is OK — but trading AGAINST it is the
exact 5/14 09:58 misfire pattern. The bar pierced PMH 745.43 (potential reclaim), then closed
$1.00 BELOW (sweep complete). The bullish trade fired anyway because the engine read the in-progress
mid-bar high as "reclaim confirmed." Closed-bar filter (v15.1) caught half of this; sweep blocker
catches the other half.
```

---

## Change D — reference the canonical implementations (insert at line 343)

**Proposed (insert after line 343 "TRIGGER DEFINITIONS"):**
```
> **Canonical implementations** (per CLAUDE.md OP-26 — single source of truth):
> - `crypto.lib.bar_reader.last_closed_bar(series, now)` — closed-bar filter
> - `crypto.lib.levels.classify_bar_at_level(bar, level, min_margin_pct=0.05)` — level event classification
> - `crypto.lib.sweep.detect_sweeps(bars, levels, min_wick_pct=0.02, min_close_back_pct=0.05, clean_prior=3)` — sweep / failed-breakout
> - `crypto.lib.volume.is_volume_confirmed(bar, prior_bars, threshold=1.5, length=20)` — volume gate
>
> If model output disagrees with these functions, the FUNCTION is right; report the divergence in
> `automation/state/decisions.jsonl` so EOD audit catches the doctrine drift.
```

---

## Validation evidence

| Claim | Evidence |
|---|---|
| Closed-bar filter prevents reading in-progress bars | `crypto/benchmarks/replay_5_14.py` — 46/46 ticks corrected. 16-month replay: 44,096 ticks, 0% NEW leak rate. Max OLD misread $18.38. |
| Level event classification is correct | `crypto/validators/v05_levels.py` — 10/10 offline tests pass (T5 RECLAIM, T6 BREAK, T7 REJECT, T8 HOLD). Live BTC validation passing on every grinder iteration. |
| Sweep detector catches the 5/14 09:55 bar | `crypto/validators/v14_sweep.py` T1 — exact synthetic reproduction of OHLC 745.02 / 745.47 / 744.25 / 744.43 at PMH 745.43. Detector fires `bearish_sweep` direction="up". 5/5 offline tests pass. |
| Same primitives work on live data 24/7 | `Gamma_CryptoRegression` task — 28/28 stages PASS every 30 min. Foot-gun catch rate 130/130 = 100% in latest 24h window. |

## Risks to consider (J review)

1. **`min_margin_pct=0.05` is calibrated on BTC bars at $78K. SPY at $735 = much smaller absolute moves.** Translation: 0.05% on $735 = $0.367. That's wider than my proposed $0.22 in Change A. Should I use $0.22 (≈0.03%) or $0.367 (0.05%)? Question for J.

2. **Tighter level_reject reduces the trigger fire rate.** v12's "≥1 bear trigger" threshold may need to drop to "≥1" still or change to "≥2 bear" to compensate. Backtest required before deploy.

3. **Sweep block uses prior-3-bars clean prior.** On bars right after a level break (e.g., immediately after reclaim), the prior 3 won't be on origin side → sweep won't fire. That's intentional — but means if the SAME level is being retested twice in 15 min, only the FIRST retest is sweep-protected.

4. **No mirror against `sequence_*` triggers explicitly.** The proposed sweep block only mentions level_reclaim/level_reject. Should sequence_reclaim/sequence_rejection also be blocked on sweep? Likely yes; need explicit text.

---

## What happens before this ships to production

1. ✅ DRAFT written (this file)
2. ⏳ J reviews on weekend
3. ⏳ J runs backtest: `python backtest/run.py --start 2025-01-01 --end 2026-05-14 --label v15.2_with_sweep_block --real-fills --strategy v15.2`
4. ⏳ Verify: no regression on the 7 J-edge days (4/29, 5/01, 5/04 winners; 5/05, 5/06, 5/07×2 losers). Edge_capture per OP-16 must hold.
5. ⏳ Verify: SPY-equivalent sweep tests on the historical CSV — sweep detector fires on at least 3 historical sweep bars including 5/14 09:55.
6. ⏳ If GREEN: copy DRAFT changes A-D into production heartbeat.md, bump `rule_version` in params.json to "v15.2" + premarket.md RULE_VERSION_EXPECTED. Per OP-4 (no code drift) update both code paths.
7. ⏳ Append L38 to LESSONS-LEARNED.md with the ratification.

## Pre-merge gate

`python crypto/validators/runner.py` must show **OVERALL: PASS** at the moment of merge. If any validator regressed, the port is unsafe.

---

_Last edited: 2026-05-16 by autonomous session. DO NOT deploy without J ratification._
