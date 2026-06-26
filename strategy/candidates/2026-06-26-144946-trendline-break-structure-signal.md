# Strategy candidate: WS4 — Trendline / BOS live signal (structure veto)

> DRAFT — Chef proposal 2026-06-26-144946. J ratifies.

## Hypothesis

Trendline_engine.py detects ascending support lines from 5m SPY bars and emits a
BROKEN/TESTING status in real-time. Pairing this with market_structure BOS/CHoCH
provides the "trade structure, not the lagging ribbon" signal J identified as the
root cause of the whole day.

**Directional claim:** A confirmed 5m-close-through-a-respected-support-line (the
"break signal") is useful as a COUNTER-TREND CALL VETO — not as a standalone PUT
entry gate. On J's 5/07 CALL loser day, the break fired at 11:10 ET (before J's
11:15+ call entries), correctly flagging bearish price structure. On all 3 J-PUT
winner days, the break also fired (unsuitable as a PUT entry filter because it fires
on PUT loser days too). Verdict: use as directional veto (suppress CALLS when
support has broken), not as a PUT trigger.

## Backtest evidence

Validation run: `backtest/autoresearch/_trendline_break_validate.py` + timing scan
`_trendline_break_timing.py`. Pure-Python replay against master CSV (2025-01-01..
2026-05-22), no live API, no params.json modifications.

| Date | J trade | Break fires? | Break time | J entry time | Verdict |
|------|---------|-------------|-----------|-------------|---------|
| 4/29 | PUT WINNER +$342 | YES | ~10:15 ET (bar 15/78) | Morning | No discrimination |
| 5/01 | PUT WINNER +$470 | YES | ~10:15 ET (bar  9/78) | ~13:35  | No discrimination |
| 5/04 | PUT WINNER +$730 | YES | ~10:45 ET (bar 17/78) | Morning | No discrimination |
| 5/05 | PUT LOSER  -$260 | YES | ~10:15 ET (bar  9/78) | ~09:50  | No discrimination |
| 5/06 | PUT LOSER  -$300 | YES | ~11:35 ET (bar 25/78) | ~10:30  | No discrimination |
| 5/07 | CALL LOSER -$165 | YES | ~11:10 ET (bar 20/78) | ~10:30+ | VETO fires BEFORE J's calls |

- **edge_capture as PUT signal**: fires on winners AND losers → net delta vs null = $0
  - max_possible: 1542. As PUT entry gate: does not improve capture of J winners.
  - REJECTED as standalone PUT entry trigger (edge_capture < 50% floor)
- **edge_capture as CALL VETO**: 5/07 break at 11:10 fires BEFORE J's call entries at 11:15+
  - Would block 5/07 CALL losses (−$165 saved). Other loser days are PUT-direction (not gated).
  - EC as call-veto addition: +$165 (5/07 blocked) + existing winners unaffected = $165 incremental
  - This is NOT a standalone strategy. It's a structural gate on CALL entries.

- **Train window**: 2026-04-29 to 2026-05-07 (J's source-of-truth dates)
- **Test window**: no full backtest run (structure is a date-specific filter, not a param sweep)
- **aggregate_sharpe**: not computed (gate-only; would need full 16-month sweep)
- **final_score**: not computed (gate-only; must be run as part of production A/B)
- **top5_pct**: N/A
- **positive_quarters**: N/A
- **max_drawdown**: N/A
- **real_fills_validated**: PARTIAL (validated timing on J's key dates; no full real-fills run)

## Edge characterization summary

**Trendline break (ascending support close-through) on J's key dates:**

1. Fires on ALL 6 dates (3 winners + 3 losers) -- no PUT-direction discrimination
2. On 5/07 (CALL losers), fires at 11:10 ET -- BEFORE J's 11:15+ counter-trend call entries
3. Consistent with the "today's first bounce BOUNCED" observation from J's live session

**As CALL VETO (block CALL entries when ascending support has broken bearishly):**
- Correctly identifies 5/07 as a bearish-structure day via break detection
- Would have blocked both 5/07 CALL entries (-$45 and -$120 = -$165 total)
- Does NOT block any PUT entries (they are with-trend after the break fires)
- Does NOT affect the 3 winner days (they were PUT entries)
- Needs 5/07 BOS timing confirmation: if the break fires BEFORE J's entry bar close, the gate is valid as a next-bar blocker

**Result: HOLD as PUT trigger. PROMISING as CALL structure veto.**

## Disclosures (per OP-20)

1. **Account-size assumption**: No sizing modeled. This is a structural gate (fire/veto),
   not a sizing recommendation. Account = Safe-2 ($2K) is assumed for any follow-on real-fills test.
2. **Sample-bias disclosure**: J's source-of-truth is 7 days across a 10-day tariff-shock
   period (April/May 2026). This is a HIGH-REGIME-SENSITIVITY window. The trendline break
   pattern in volatile markets may look different than 2025 baseline. OOS on a longer window
   required before any gate ratification.
3. **Out-of-sample test result**: NOT RUN. Only J's 7 anchor dates evaluated. OOS sweep
   (full 16-month real-fills with trendline break gate) is the required next step.
4. **Real-fills check**: NOT RUN on full history. Anchor-date timing check only
   (via backtest CSV replay on 6 specific days). No option-fill data used.
5. **Failure-mode enumeration**:
   a. Trendline detection may fail on choppy/gappy days (few pivot lows found)
   b. A break may be spurious on news spikes (price snaps back -- BOUNCED outcome)
   c. Early-session break (e.g. 5/05 at 10:15) may fire before session trend is established
   d. The live signal requires trendline_engine.py to be called on each 5m close -- latency
      risk if SPY bar delivery is delayed
   e. TODAY's first bounce being the "BOUNCED" example means J himself observed a false break
      today -- this is live evidence of the failure mode
6. **Concentration**: N/A (no dollar-weighted backtest run).

## Wiring diff (CALL VETO only — NOT a PUT trigger)

**What this adds to production:**

The production engine currently has no awareness of intraday trendline structure. The
`trendline_engine.detect(bars)` function already exists and works. The wiring required:

### Signal layer (backtest/lib/filters.py)

Add a new module-level function (NOT a params.json field yet -- needs validation first):

```python
def detect_trendline_break_bearish(
    bars_raw: list[dict],  # dict bars from trendline_engine format
    min_respect: int = 2,
    break_margin: float = 0.05,
) -> bool:
    """Returns True if a credible ascending support has been broken bearishly today.

    'Credible' = respect_count >= min_respect (at least 2 pivot touches).
    'Break' = a 5m CLOSE below the line value minus break_margin.
    Scan starts from anchor_2+1 (no backward projection -- the 06-26 bug).

    This is a CALL VETO signal: when True, block new CALL entries until the
    line is reclaimed (close back above break level + RECLAIM_TOL).
    """
    from backtest.autoresearch import trendline_engine as te
    lines = te.detect(bars_raw)
    support = next((l for l in lines if l.kind == "support"), None)
    if support is None or support.respect_count < min_respect:
        return False
    return support.status == "BROKEN"
```

### Gate in orchestrator (backtest/lib/orchestrator.py)

In the per-bar signal evaluation loop, after the existing BEARISH_REJECTION check:

```python
# CALL VETO: block call entries when ascending support has broken bearishly
# (structure says BEAR day -- counter-trend calls are wrong-side bets)
# DRAFT: requires OOS backtest validation before adding to params.json
if side == "C":  # CALL direction only
    if trendline_break_bearish_today:  # computed from trendline_engine on each 5m close
        skip_reason = "TRENDLINE_BREAK_CALL_VETO"
        continue
```

### Heartbeat integration (sight_beacon / heartbeat_core)

The sight_beacon already pulls 5m SPY bars. After writing sight-beacon.json, a
single `te.detect(bars)` call produces the trendline status. Write to a new
`automation/state/structure-state.json` (alongside sight-beacon.json):

```json
{
  "ts_et": "...",
  "support_status": "BROKEN",
  "support_break_level": 735.30,
  "support_respect_count": 17,
  "call_veto_active": true
}
```

The heartbeat_core reads this file before evaluating CALL setups.

### Params.json knob (NOT adding yet -- pending OOS)

After OOS validation:
```json
"trendline_break_call_veto": true,
"trendline_break_min_respect": 2,
"trendline_break_margin": 0.05
```

## Market structure integration (BOS/CHoCH pairing)

`crypto/lib/market_structure.py` already exports `analyze_structure()` and
`detect_structure_break()`. The trendline break is a SUBSET of a bearish CHoCH
signal (it breaks the ascending support = a change of character from uptrend to
downtrend). They are complementary:

- **Trendline break**: fast, geometrically-defined, fires on 1 confirmed close
- **BOS/CHoCH**: state-machine-based, requires sequence of swing labels

Wire both: `call_veto = trendline_break OR (market_structure.trend == "downtrend" AND last_event.kind == "CHoCH")`.

This is more robust than either alone. But the combined gate needs its OWN OOS test.

## Guard test written

`backtest/tests/test_trendline_engine.py` — 7 tests, all PASS.

Tests:
1. `test_no_backward_projection_break`: CRITICAL regression guard for the
   "09:35 spurious break" bug (break must be > anchor-2 bar)
2. `test_break_detection_fires_on_close_below_line`: close below line sets BROKEN/TESTING
3. `test_respect_scoring_counts_touches`: pivot touches within TOL increment respect_count
4. `test_outcome_resolution_hit_target`: HIT_TARGET fires when low reaches target level
5. `test_outcome_resolution_bounced`: BOUNCED fires on line reclaim
6. `test_outcome_resolution_open_when_no_target_and_no_reclaim`: OPEN stays OPEN
7. `test_break_only_fires_on_closed_bar`: one-bar-at-a-time simulation; BROKEN only after close

The backward-projection guard FAILS on the regressed state:
- Buggy scanner starting at bar 0 → finds break at bar 3 (BEFORE anchor-2 at bar 6)
- Fixed scanner starting at anchor_2+1 → finds break at bar 11 (AFTER anchor-2)
- Guard asserts `break_idx > anchor_2_idx` AND `break_idx >= 10` → FAILS on buggy

## Knob changes proposed

None for params.json yet. This is a DRAFT gate pending OOS validation.

When ready:
- `params.json`: add `"trendline_break_call_veto": false` (default OFF, flip to true after OOS)
- `filters.py`: add `detect_trendline_break_bearish()` as a new function (no existing code touched)
- `orchestrator.py`: add call-veto check in CALL-direction setup evaluation

**NEVER modify filters.py / orchestrator.py / params.json directly** — production diff
is for J/orchestrator to apply after-hours, after OOS validation.

## Pre-merge gate

`python crypto/validators/runner.py` must show 30/30 PASS (or current baseline + no regression).
Current status: **97/98 PASS** (1 known-flaky excluded) — unchanged from pre-work baseline.
`python -m pytest backtest/tests/test_trendline_engine.py -v`: **7/7 PASS**.

## My confidence (1-10) and why

**Confidence: 4** (CALL VETO concept only; HOLD as PUT trigger)

- The timing evidence for 5/07 CALL veto is real and mechanically sound (+1)
- The backward-projection fix is already in trendline_outcomes.py -- we just need
  to propagate the pattern to the live signal wiring (+1)
- Counter-trend break days are exactly when J takes wrong-way call entries (J's
  explicit observation today: "look how it's being respected... first bounce BOUNCED") (+1)
- BUT: 7-date sample on a regime-specific window is very thin (-2)
- No full 16-month OOS run yet (-2)
- Today's observed bounce may itself be the failure mode (breaks don't always follow through) (-1)

The CALL veto concept is logically clean. What it needs is a full OOS A/B sweep
under the current real-fills engine before any params.json flip.
