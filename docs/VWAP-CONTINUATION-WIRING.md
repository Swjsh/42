# VWAP_CONTINUATION (J_VWAP_CONT) — flip-ready DORMANT wiring

> **Status: SHIPPED DORMANT / PROPOSE-AND-PING-J.** J's near-daily trading edge,
> implemented end-to-end and **one flag-flip from live**. The detector, tests,
> registration, params keys, and heartbeat block ARE shipped (engine code + dormant
> doctrine). The setup is **OFF by default** (`params.j_vwap_cont_enabled = false` →
> the heartbeat block is inert → zero behavior change). It is NOT auto-live because it
> clears **6 of 7** OP-22 gates (misses strict all-cuts-OOS-positive on a soft recent
> quarter). **J flips it.** J's role per OP-22/OP-25 is REVOKE, not approve — but
> because this is a 6/7 with a recent-Q caveat AND touches the bull-side direction
> (OP-16), the flip is explicitly J's call.

## What this is

J's own dominant, repeatable winning pattern — **VWAP-ALIGNED MORNING CONTINUATION** —
mined from his **313 real Webull winners** (`backtest/autoresearch/webull_daily_pattern_miner.py`):
his CALL winners sit above session VWAP (74%), his PUT winners below it (81%); the
VWAP-aligned class wins 63.7% vs 45.7% counter-VWAP (a sign-flip in expectancy: +$26 vs
−$19/trade), and it fires on **92% of his trading days**. The morning band (≤10:30 ET)
is the sweet spot (69% WR / +$32), and his highest-WR trigger is the breakout/continuation.

This was translated **structurally** (VWAP-relation / time-of-day / side are scale-free,
so his 2021-23 SPX rule maps directly onto 2025-26 SPY) into a **causal** detector and
run through the full OP-22 stack on **real OPRA fills** with the live CHART-STOP-ONLY
config — `backtest/autoresearch/j_daily_pattern_ratify.py` →
[`analysis/recommendations/j-daily-pattern-LIVE.json`](../analysis/recommendations/j-daily-pattern-LIVE.json).

## Why it ships (the validated numbers)

Headline variant **J_VWAP_CONT / ATM**, chart-stop-only, real OPRA fills 2025-01..2026-06:

| Metric | Value |
|---|---|
| n (filled trades) | **153** |
| Expectancy | **+$38.3 / trade** |
| Win rate | **76.5%** |
| Total | **+$5,860** |
| Frequency | **fires 42.1% of days = 2.11/wk (NEAR-DAILY)** |
| Both directions + | C +$26.0 / 77.4% · P +$53.3 / 75.4% |
| Drop-top-5 | **+$24.45 / trade** (broad-based, not 5-winner-driven) |
| OOS (70/30) | **+$24.12 / trade, sign-stable** |
| DSR | **PASS** (PSR ≈ 1.000) |

The **VIX-gated** variant (`J_VWAP_CONT_VIXGATE` / ITM-1) is the strongest single cell —
n=152, exp **+$50.5**/trade, WR **77.6%**, WF median **+0.962**, q+ **5/6** — because the
put-side VIX-character gate (C5: puts only when as-of VIX 5-bar slope ≥ 0) lifts the put
book and trims the recent-quarter drag. Available behind `j_vwap_cont_put_vix_gate`.

## The honest gate tally — 6 of 7 (NEAR-SURVIVOR, not a clean auto-ship)

OP-22 ship bar = OOS+ AND WF-median≥0.70 AND **all-cuts-OOS-positive** AND q≥60% AND
DSR-not-FAIL AND both-dirs+ AND drop-top5-robust.

| Gate | J_VWAP_CONT/ATM | J_VWAP_CONT/ITM1 | VIXGATE/ITM1 |
|---|---|---|---|
| OOS positive | **PASS** (+$24.1) | **PASS** (+$34.6) | **PASS** (+$49.1) |
| WF median ≥ 0.70 | 0.546 ✗ | **0.721 PASS** | **0.962 PASS** |
| **all-cuts-OOS-positive** | **FAIL** | **FAIL** | **FAIL** |
| sub-window stable (q≥60%) | **PASS** (4/6) | **PASS** (4/6) | **PASS** (5/6) |
| DSR not FAIL | **PASS** | **PASS** | **PASS** |
| both directions + | **PASS** | **PASS** | **PASS** |
| drop-top5 robust | **PASS** | **PASS** | **PASS** |
| Live-detector parity | **PASS** — core == research over 363 days | | |

**The one failing gate** (`all-cuts-OOS-positive`) fails on exactly one window: the most
recent OOS slice (cut 0.80 → 2026-Q2). That quarter is **−$60.8/trade OOS** and is the
sole negative window across all three cuts. Root causes (both disclosed in the scorecard):
**partial OPRA coverage** (the cache ends ~2026-05-29, so the recent slice is thin) and a
**put-side bear-chop patch** (the VIX gate, when enabled, recovers most of it: VIXGATE
2026-Q2 = −$34.0 vs ungated −$64.9). This is **the same class** as the already-shipped H4
VWAP-pullback edge — regime-soft in a recent window, structurally sound across the full
sample — so it ships **DORMANT/flip-ready with the caveat**, not as a clean auto-live.

The other knock: **near-daily, not every-day.** It fires ~2.1×/week (42% of days), which
clears the ≥2/wk "daily-tradeable" floor but is not literally daily — J's own pattern
also only set up on the days the tape was one-sided off the open.

## Why it wires as a morning-block, not a scoring filter

J_VWAP_CONT is a **once-per-day morning setup**: it resolves the trend side from the first
3 RTH bars, then takes the **first in-trend continuation bar ≤ 10:30 ET** (breakout or
shallow VWAP pullback), entry at the next bar open, chart-stop only. It does NOT match the
per-tick continuous-scoring rubric, so — exactly like GAP_AND_GO — it wires as a dedicated
block evaluated each morning tick BEFORE `### Scoring`, gated on its flag, routing the
signal through the SAME execution + `risk_gate` path as a normal entry.

## What shipped (engine code + dormant doctrine)

- **Live detector:** `backtest/lib/watchers/vwap_continuation_watcher.py` — pure causal
  core (`detect_vwap_continuation_core` + `trend_side` + `vix_slope`) + the streaming
  `BarContext` wrapper (`detect_vwap_continuation_setup`). Chart-stop only; both
  directions; warmup-safe; one-entry-per-day module state; optional VIX put-gate.
- **Registration:** `backtest/lib/watchers/runner.py` `WATCHERS` (WATCH_ONLY observation
  layer) — `WATCHER_COUNT` 27 → **28**. Also re-exported from `lib/watchers/__init__.py`.
- **Parity + unit tests:** `backtest/tests/test_vwap_continuation_watcher.py` — 21 tests.
  The headline is **full-dataset PARITY**: the live core reproduces
  `j_daily_pattern_ratify.detect_j_vwap_continuation`'s signals EXACTLY across all 363
  days — for the plain, breakout-only, AND VIX-gated variants — so the scorecard's numbers
  are claimable for the LIVE detector (L153). Plus unit tests for the VWAP-side logic, the
  VIX gate (rising allows / falling blocks puts), the morning cutoff, causality (warmup),
  and one-entry-per-day.
- **Params (DORMANT, default OFF):** `automation/state/params.json`
  - `j_vwap_cont_enabled: false` — the master flag (false = inert).
  - `j_vwap_cont_side: "both"` — both directions validated +, BUT see the OP-16 note below.
  - `j_vwap_cont_put_vix_gate: false` — opt-in C5 VIX put-gate (the stronger cell).
  - `_j_vwap_cont_doc` — full provenance + revert.
- **Heartbeat block (DORMANT):** `automation/prompts/heartbeat.md` → `### VWAP_CONTINUATION
  morning setup` (own first-entry lock key `VWAP_CONTINUATION`, ≤10:30 morning-window gate,
  VWAP-side + breakout/pullback trigger + optional VIX-gate recognition, per-tier strike,
  chart-stop, min-3 + ~6% premium ceiling, standard v15 exits, routed through the normal
  pre-exec gate + `risk_gate`). **Gated on `j_vwap_cont_enabled != true → SKIP`** → falls
  through to `### Scoring` unchanged when off.

Pin-sync: the params values (`enabled`/`side`/`put_vix_gate`, gap thresholds, cutoff,
chart-stop-only) and the heartbeat block describe the SAME rule — a drift between them is a
kill-switch event (rule-version pin check, premarket Step 1a).

## THE ONE FLIP TO MAKE J'S DAILY EDGE TRADE

Edit `automation/state/params.json`:

```json
  "j_vwap_cont_enabled": true,
```

That single change activates the heartbeat block. Nothing else is required — the detector,
gates, sizing, exits, and risk_gate routing are all already wired.

Direction / gate choices when flipping:
- **`j_vwap_cont_side`** — keep `"both"` to trade J's full validated edge (calls + puts,
  both cleared the bar). **OP-16 caveat:** the doctrine keeps bull-side new entries DRAFT
  until J has 3 live wins on a bull setup, so going live with `"both"` is **J's explicit
  call**. Set `"put"` for the OP-16-conservative bear-only first step (forfeits the call
  half, which is the larger and equally-validated side).
- **`j_vwap_cont_put_vix_gate`** — set `true` to use the stronger VIX-gated cell (lifts the
  put book and trims the recent-Q drag); leave `false` for the headline cell.

## Revert

Set `params.json#j_vwap_cont_enabled: false` (a no-op flip — the block becomes inert
without touching `heartbeat.md`). The detector + tests + registration stay in tree (engine
code). J holds REVOKE per Rule 9 / OP-25.

## Provenance / repro

- Profile (Part A): `backtest/autoresearch/webull_daily_pattern_miner.py` →
  `analysis/webull-j-trades/j_daily_rules.json` + `j_winner_features.json`.
- Validation (Part B): `backtest/autoresearch/j_daily_pattern_ratify.py` →
  [`analysis/recommendations/j-daily-pattern-LIVE.json`](../analysis/recommendations/j-daily-pattern-LIVE.json)
  (real OPRA fills, OP-22 stack + co-equal frequency metric, chart-stop-only).
- Live detector + parity/unit tests: `backtest/lib/watchers/vwap_continuation_watcher.py`
  + `backtest/tests/test_vwap_continuation_watcher.py` (21 tests, 363-day parity).
- Gym: `crypto.validators.runner --skip-replay` → 87/87 PASS after registering the watcher.
- OP-21 live gate still stands: accumulate WATCH_ONLY observations → 3 live J confirmations
  before any further scope expansion.
```
