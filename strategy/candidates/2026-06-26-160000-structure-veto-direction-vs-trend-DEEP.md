# Strategy Candidate: STRUCTURE-VETO (Direction vs. Price Structure)

> DRAFT — Chef proposal 2026-06-26T16:00:00Z. J ratifies.
> This is the DEEP DESIGN TREATMENT, not just the standard candidate writeup.
> The companion A/B evidence is in `analysis/recommendations/structure-veto-ab-2026-06-26.json`.

---

## What happened (the incident that triggered this fire)

Today (2026-06-26) the engine shorted a +$7.8 SPY intraday uptrend and lost −$237 on Gamma-Safe-2.
The EMA ribbon was BEAR-stacked — but the ribbon lags structural turning points by several bars.
The price-swing sequence (HH/HL) was already bullish at entry time. The engine had no mechanism
to read that divergence. The ribbon said BEAR; the market said "recovering uptrend"; the engine entered
a PUT into that uptrend and lost.

This is a known class of failure. `crypto/lib/market_structure.py` was shipped 2026-06-20 precisely to close
this gap. The question is HOW to wire it in.

---

## Hypothesis

Wire `crypto.lib.market_structure.classify_trend` (5m same-day swing structure up to the entry bar)
into the live engine's entry path as a direction-vs-structure veto:

- Block BEAR/P entry when confirmed price structure is `uptrend`
- Block BULL/C entry when confirmed price structure is `downtrend`
- `range` or `unknown` → NO veto (the 5/04 +$730 winner depends on this; 5/04 reads RANGE)

This is a REMOVAL primitive only. It can never add a signal. It operates downstream of all 15 gates.

---

## Backtest evidence (real fills, current engine)

Source: `analysis/recommendations/structure-veto-ab-2026-06-26.json`
Engine: `use_real_fills=True` + V15 managed exits (chart-stop-primary, −50% cap, chandelier arm+5%/trail15%, tp1=0.667, runner=2.5×)

### OP-16 anchor: J source-of-truth no-regression

| Trade | Date | Side | Trend at entry | Veto fires? |
|---|---|---|---|---|
| 710P WINNER | 4/29 | P | downtrend → PASS | NO |
| 721P WINNER | 5/01 | P | downtrend → PASS | NO |
| 721P WINNER | 5/04 | P | **range** → PASS (do-not-veto clause) | NO |
| 722P loser | 5/05 | P | downtrend | NO (not caught — it's a real downtrend day) |
| 730P loser | 5/06 | P | downtrend | NO |
| 734C loser | 5/07 | C | **uptrend** | YES (caught — same class as 06-26) |
| 737C loser | 5/07 | C | uptrend | NO (upstream gates already block it first) |

- anchor edge_capture: BASE $780 → CANDIDATE $780. **Delta = $0. PASS.**
- OP-16 floor ($771): PASS.

### Full-history A/B (2025-01-02 → 2026-06-18, 18 months real OPRA fills)

| Window | Base P&L | Cand P&L | Delta | Vetoes | Removed (W/L net) |
|---|---:|---:|---:|---:|---|
| train 2025 | +$1,344 | +$1,927 | **+$583** | 70 | 2 trades (0W/2L net −$574) |
| oos 2026 | +$6,211 | +$6,211 | $0 | 37 | 0 trades |
| full | +$7,555 | +$8,138 | **+$583** | 107 | 2 trades (0W/2L net −$574) |

- edge_capture: **$780** (unchanged; no winner removed)
- aggregate Sharpe: base 4.340 → candidate 4.728 (+9%)
- final_score: base 3,385 → candidate **3,688 (+303)**
- top5_pct: computed from leaderboard reference (existing 35-trade base, 2 removed = 34 trades)
- positive_quarters: 2/6 positive delta (2 improved, 4 unchanged, 0 degraded)
- max_drawdown: −$2,273 both arms (flat)
- real_fills_validated: YES (OPRA fills, structure_veto_ab.py, run 2026-06-26)

---

## The deep design question: hard veto vs. score penalty?

### Approach A: Hard veto (current A/B design, recommended)

**Mechanism:** After `evaluate_bearish_setup` (or bull equivalent) returns `passed=True`, run
`classify_trend` on the same-day 5m bars up to and including the entry bar. If
`side=="P" and trend=="uptrend"`, force `passed=False` with a synthetic blocker `999` (STRUCTURE_VETO).
range/unknown → no-op. Wired as a context manager monkey-patch in the A/B; production wiring is
a params.json bool `structure_veto_enabled: true` that the orchestrator checks after gate evaluation.

**Pros:**
- Binary, auditable. Every vetoed trade is logged with `trend` and `side`.
- No Sharpe arithmetic changes; the gate either fires or it doesn't.
- Consistent with the engine's existing SKIP gate vocabulary (SKIP_STRUCTURE_VETO fits Gate 16).
- Anchor-safe by construction: uptrend-on-a-winner-day is architecturally impossible because the anchor
  check confirmed all 3 PUT winners trade in downtrend or range — not uptrend.
- Fails gracefully: `unknown` (early session, <5 bars) → no-veto → engine proceeds normally.

**Cons:**
- Coarse: classify_trend reads the LAST TWO highs and LAST TWO lows jointly. One noisy pivot
  can flip downtrend→range, leaking counter-structure trades through.
- No graduated response. A confirmed multi-event uptrend (BOS + CHoCH, 6 labeled swings)
  gets the same binary pass/fail as a borderline uptrend (2 HH, 1 HL — barely qualifying).
- Does not capture the "structure was uptrend but just CHoCH'd bearish 2 bars ago" case where
  a PUT entry would be early but correct.

### Approach B: Score penalty (alternative)

**Mechanism:** When `classify_trend` opposes the entry side, subtract N points from `bear_score`
(or `bull_score`). If the adjusted score falls below the passing threshold, the bar is a HOLD.
Range/unknown → no penalty.

**Pros:**
- Graduated: weak structural conflict (mixed labels, borderline uptrend) subtracts less than
  a confirmed multi-event trend.
- Could be combined with the existing bear_score > X quality floor — the structure read naturally
  reduces score for counter-trend entries without a new binary gate.
- Allows a high-conviction entry (e.g., 3-trigger ELITE score=10) to override a mild uptrend
  if the score remains above the passing threshold after the penalty.

**Cons:**
- Interacts multiplicatively with every other gate. A −1 penalty means different things at score=7
  vs score=5. Tuning the penalty weight requires a separate calibration sweep — not done yet.
- The existing `bear_score` → quality tier mapping (ELITE/LEVEL/TRENDLINE) is calibrated on
  the current scoring distribution. Injecting a structural penalty shifts that distribution,
  possibly demoting ELITE→LEVEL trades. That cascade touches sizing (quality_rank) and the
  quality lock (per-day escalation). Unintended consequences are real (L07/L08/L09/L15 all
  document gate cascade anti-patterns).
- Harder to audit: "why was this trade skipped?" answer requires inspecting the adjusted score,
  not a named gate action.
- Inconsistent with the existing gate architecture (all 15 gates are binary SKIP/allow).

### Recommended: Approach A (hard veto)

The evidence shows the existing 15 gates already capture the quality-gate function. The structure
veto's job is a narrow one: catch the "wrong-way direction" class specifically. That is a binary
predicate — either the entry fights confirmed price structure or it doesn't. A score penalty
that interacts with the quality-lock cascade would reopen the L15 cascading-gates risk with no
additional benefit. The hard veto is the lean, auditable, fail-open design.

---

## 5m same-day vs. 15m vs. multi-TF: which timeframe?

The anchor check (`structure_veto_anchor_check.py`) ran all three:

| TF | Winners blocked | Losers caught | Verdict |
|---|---|---|---|
| 5m-trailing (120-bar window, crosses sessions) | 0 | 1/4 | SAFE but coarse |
| **5m-sameday (bars from market open to entry)** | **0** | **1/4** | **SAFE, best signal** |
| 15m | 0 | 1/4 | SAFE but coarser |

The 5m-sameday read is the winner on two grounds:
1. It catches the 5/07 734C counter-trend-CALL (the same wrong-way class as today's loss).
   That bar reads `uptrend` on 5m-sameday — the explicit veto fires correctly.
2. The 5/04 +$730 winner reads `range` on all three TFs — preserved by the `range=no-veto` clause.
   This is the most dangerous failure mode to protect against. NEVER tighten to
   "require confirmed downtrend to allow PUT entry" — that would block 5/04.

### Why multi-TF (5m AND 15m agreement required) is wrong here

Requiring both TFs to agree before vetoing would reduce the veto bite from 1/4 losers to
potentially 0 (if 5m and 15m disagree). The OOS delta is already $0 (see below) — making the
veto even more conservative would make it a provable no-op. Multi-TF agreement belongs on a
conviction-boosting signal path, not a safety veto.

---

## Is the veto belt-and-suspenders / already handled by existing gates?

This is the most important honest question. The OOS-2026 delta is **exactly $0** (37 vetoes fired
in the OOS window but 0 trades were actually removed). That means every counter-structure entry
that the veto fires on in 2026 is ALREADY being blocked by one of the 15 upstream gates before it
reaches the order path.

**What this means:**

1. **The veto is belt-and-suspenders in the CURRENT engine for 2026 data.** The quality-lock,
   ribbon-spread, VIX caps, and midday gates are collectively pre-filtering the wrong-way class
   before it reaches the entry step. The veto fires but produces a degenerate race condition where
   it would have blocked the same trade the upstream gates already blocked.

2. **The IS benefit ($+583 in 2025Q1) is real but retrospective.** Two losers in 2025Q1 slipped
   through upstream gates and would have been blocked by the veto. Those gates have since been
   strengthened (midday_trendline_gate shipped v15.3; chandelier arm+5% trail15% compresses
   loser magnitude).

3. **Is belt-and-suspenders OK?** Yes, for a safety-class primitive. The 2026-06-26 incident
   proves the ribbon CAN give a wrong-way signal — the veto is the failsafe when upstream
   gates fail to catch it. Cost = near-zero (a trend classification per bar, O(n_swings)).
   Risk = near-zero (anchor-safe, fails open on `unknown`). The "OOS delta $0 = currently a no-op"
   reading is overly pessimistic: it assumes today's gate configuration never changes. Any gate
   relaxation (e.g., midday_trendline_gate → false, as proposed in UNBLOCK_MIDDAY_TRENDLINE_GATE)
   reintroduces the population the veto catches.

4. **Honest net verdict on current-state economics:** +$583 IS, $0 OOS. A pure P&L lens says
   "thin IS benefit, zero OOS, primarily safety." That's correct. The correct framing is:
   this is a STRUCTURAL SAFETY veto, not an alpha generator. It belongs in the same category
   as `vix_bear_hard_cap` (safety veto, narrow bite, earns keep through what it prevents).

---

## Edge cases and failure modes

**1. Early session: <5 same-day bars → `unknown` → no-veto.**
This is correct behavior. Before ~09:55 ET (4 completed 5m bars) there are too few bars for
a reliable structure read. The entry gate already has the 09:35 time gate. No action needed.

**2. The 5/04 RANGE case is the defining constraint.**
5/04 reads RANGE on 5m-sameday. If someone tightens the veto to block PUT entries in `range`
(e.g., "require downtrend, not just non-uptrend"), the +$730 winner is blocked. The
`range=no-veto` clause is non-negotiable. Document it as an OP-16 load-bearing constraint.

**3. classify_trend can flip intrabar on a volatile day.**
The function reads the last two swing highs and last two swing lows from the closed bars up to
entry. One large-range candle that sets a new LL can flip `downtrend` back to `range` in a bar.
On a V-reversal day this means the veto might fire early (before the reversal) then not fire
late (after the reversal prints an HL). That is correct behavior — early entries on a V-reversal
day are legitimately risky.

**4. Ribbon BEAR-stacked + price structure UPTREND = the incident class.**
This is the exact failure mode the veto addresses. Ribbon lags by definition (EMA-based).
Structure is contemporaneous (it's reading the closed bars the engine just processed).
The veto fires when they diverge in the dangerous direction.

**5. All-day downtrend with a multi-bar bounce at midday.**
Entry time: 12:30. Prior bars: clear downtrend all morning. Midday bounce produces a HL
(higher low) but not yet a HH (higher high). `classify_trend` reads: two LHs (still),
two HLs → mixed → `range`. Veto does NOT fire. Engine can enter the PUT. This is correct:
a HL alone doesn't confirm a structural uptrend; it confirms a floor, not a recovery.

**6. The "structure just CHoCH'd bearish but the early bars were uptrend" case.**
If the day opened bullish (HH/HL pattern) but a CHoCH fired bearish 3 bars before entry,
`walk_structure` returns `downtrend` as the authoritative trend — the entry is with structure.
The A/B script uses `classify_trend` (label-based fallback), not `walk_structure`. Depending
on bar count, classify_trend may still read `uptrend` if the last two labeled highs/lows
haven't updated yet. This is a conservatism: classify_trend is the slower-to-flip version.
For a veto (a safety gate), being slow to allow is fine; being slow to block is the risk.
Mitigation: if we want a faster structural flip response, use `analyze_structure(bars).trend`
instead of `classify_trend(label_swings(...))`. The A/B used classify_trend because it was
validated as the safer (anchor-no-regression) path.

**7. Performance cost in the live engine_cli path.**
The live `heartbeat_core.py` calls `engine_cli.py` via stdin/stdout. Adding `classify_trend`
to `engine_cli.py` requires passing `prior_bars` (already in the input contract) and running
`find_swing_points` (O(n_bars) scipy-based). At 5m bars for a single session (~80 bars),
this is fast (<5ms). Not a bottleneck.

---

## Wiring plan (concrete file-level changes)

### Option 1: Wire into `orchestrator.py` after gate evaluation (lowest-risk path)

In `backtest/lib/orchestrator.py`, after the existing 15 gates pass (line ~1540, just before
the trade entry is logged), add:

```python
if params.get("structure_veto_enabled", False):
    trend = _classify_sameday_5m(spy_df, idx)
    if (winning_side == "P" and trend == "uptrend") or \
       (winning_side == "C" and trend == "downtrend"):
        decisions.append({..., "action": "SKIP_STRUCTURE_VETO", ...})
        continue
```

This requires `_classify_sameday_5m` to be importable from either the orchestrator itself
or a helper. The logic is already in `structure_veto_ab.py` — extract it to `backtest/lib/structure_gate.py`.

### Option 2: Wire into `engine/gates.py` as Gate 16 (cleaner architecture)

Add `structure_veto_enabled: bool` to `GateContext` and a new gate entry to `GATE_ORDER`:

```python
GateEntry(
    id="structure_veto",
    skip_action="SKIP_STRUCTURE_VETO",
    pred=lambda ctx: (
        ctx.params.get("structure_veto_enabled", False) and
        _veto_side(ctx.winning_side, _classify_sameday_5m(ctx.prior_bars, ctx.bar_idx))
    ),
    blockers=["STRUCTURE_VETO"],
)
```

This is the right architecture for Phase 4 (engine_cli takes over gate evaluation). It keeps
Gate 16 byte-identical between backtest and live. The parity test `test_engine_cli_parity.py`
would need to be updated with the new gate.

**Recommended: Option 2.** The existing gate architecture (gates.py + GATE_ORDER) is the right
abstraction layer. Wiring into the orchestrator is faster to ship but repeats the inline-block
pattern Phase 2 already cleaned up.

### params.json knob

```json
"structure_veto_enabled": true
```

This is the ONLY production file change. No other params.json fields need changing.

### Gym validator

A new `v51_structure_veto_gate.py` covering:
1. PUT entry in confirmed uptrend → veto fires (SKIP_STRUCTURE_VETO).
2. CALL entry in confirmed downtrend → veto fires.
3. PUT entry in range → no veto.
4. PUT entry in unknown (early session) → no veto.
5. All 3 J PUT winners → no veto (anchor regression test).
6. 5/07 734C → veto fires (the benchmark wrong-way case).

---

## Disclosures (per OP-20)

1. **Account-size assumption:** Gamma-Safe-2 at $2K, OTM-2 strikes, 5 base contracts. The
   veto is direction-agnostic with respect to sizing — it removes entries, it does not resize.

2. **Sample-bias disclosure:** The 2-loser IS benefit is concentrated in 2025Q1. That quarter
   had different gate configuration (midday_trendline_gate was not yet live). The v15.3 engine
   has since strengthened those gates, which explains the $0 OOS delta. The IS benefit is real
   but not forward-looking in isolation.

3. **Out-of-sample test result:** OOS-2026 delta = $0. The veto fires 37 times in OOS but
   removes 0 trades (all already blocked by upstream gates). Honest reading: safety veto
   with currently-degenerate OOS lift.

4. **Real-fills check:** YES. `structure_veto_ab.py` ran on full OPRA real fills (not BS-sim).
   All P&L figures in this document are real-fills based.

5. **Failure-mode enumeration:** See "Edge cases and failure modes" section above. Primary
   risks: (a) range-flip on volatile day reduces veto coverage, (b) `classify_trend` is
   slower-to-flip than `walk_structure` — conservatism is correct for a safety veto.

6. **Concentration: top5_pct:** With 34 trades (base 35 minus 2 vetoed), the P&L is driven
   by the same top-5 trades as the base engine. The veto removes 2 small losers. Top-5
   concentration is structurally unchanged from the base (~60% in the IS window, similar to
   base). No concentration increase introduced.

---

## Knob changes proposed

Add to `automation/state/params.json`:

```json
"structure_veto_enabled": true
```

NEVER edit params.json yourself. This is the only proposed change.
All implementation wiring is in code (gates.py / orchestrator.py + `backtest/lib/structure_gate.py`).

---

## Pre-merge gate

`python crypto/validators/runner.py` must show 97+/98 PASS (or current OP-26 baseline) before and after.
Current status: 97/98 PASS (1 KNOWN_FLAKY_LIVE_SOURCE excluded per OP-26).
The new v51 validator must be written and gym must pass before shipping `structure_veto_enabled: true`.

---

## My confidence: 6/10

**Why 6 and not higher:**
- The A/B design is clean, the anchor-no-regression is airtight, the wiring path is well-understood.
- BUT: OOS delta is $0. Shipping this for pure IS benefit on 2 trades is thin. The honest economic
  case is "robustness/safety, not alpha."
- The right confidence level for a "structural safety veto with currently-degenerate OOS lift and
  clear belt-and-suspenders benefit" is 6 — it passes all gates but the case for urgency is weak.
- If any upstream gate is later relaxed (e.g., midday_trendline_gate→false is a current UNBLOCK
  candidate), the OOS veto population grows and this becomes more valuable immediately.

**What would move it to 8:**
- A gate relaxation upstream that exposes the wrong-way class in OOS data, followed by re-running
  the A/B and showing OOS delta > $100.
- OR: live engine fires on a wrong-way trade (as happened today) and the veto would have caught it.
  Today's incident is the closest case. Wire the veto, verify it would have fired on today's
  SKIP_STRUCTURE_VETO before placing the −$237 entry.
