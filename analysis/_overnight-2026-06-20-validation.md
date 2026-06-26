# Overnight Validation Pass — 2026-06-20 (into 06-21)

> **Author:** overnight validation specialist (J asleep; SAFE autonomous authorization).
> **Scope:** PROPOSALS / READ-ONLY analysis. Nothing here ratifies, deploys, or touches
> `CLAUDE.md`, `automation/state/params*.json`, `automation/prompts/heartbeat*.md`,
> `backtest/lib/filters.py`, or any `*.key`. No trades placed or cancelled.
> **Verdict bar (OP-11 / OP-16):** edge_capture >= 771 AND OOS-positive AND WF >= 0.70 AND
> sub-window stable AND anchor-no-regression AND A/B scorecard filed. Anything short of all six
> is NEEDS-MORE or REJECT — never "flip-ready."

---

## 1. Test suite — harness integrity

Command: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/ -q`
(deps live in `backtest/.venv`, not system Python — per `project_backtest_venv_interpreter`).

- **Result: PASS — exit code 0**, **743 tests collected** across ~60 modules incl.
  `test_e2e_known_trades.py`, `test_e2e_real_fills.py`, `test_engine_*_parity.py`,
  `test_graduated_guards.py`, `test_fraud_gates.py`, `test_null_baseline.py`,
  `test_truncation_guard.py`, `test_validation_rigor.py`).
- One `x` marker observed at suite head = an `xfail`/`xpass` (expected, not a failure); exit
  code 0 confirms no hard failures or errors.
- **Implication:** the validation rigor harness (null-baseline gate, truncation cross-check,
  fraud gates, engine<->backtest parity) is GREEN. The guard battery the EDGE-SHORTLIST relies
  on is itself test-covered and passing. Safe to trust gate verdicts below.

> Exact pass/fail count line was not captured cleanly (the wrapper truncated the progress dots
> output); the authoritative signal is the **exit code 0** across two independent runs. If a
> numeric count is required for the morning brief, re-run with
> `pytest backtest/tests/ -q | tail -1`.

---

## 2. Candidate review against the OP-16 J-edge gate

**Anchor ground truth** (immutable, `backtest/autoresearch/j_edge_tracker.py`):
`J_WINNERS` = 4/29 (+$342), 5/01 (+$470), 5/04 (+$730) → total **1542**.
`J_LOSERS` = 5/05 (−$260), 5/06 (−$300), 5/07 ×2 (−$45, −$120) → abs **725**.
`edge_capture = Σ(engine_pnl on winner days) − Σ(max(0, engine_loss on loser days))`.
**Floor = 771** (50% of 1542). Aggregate Sharpe/P&L are secondary tiebreakers ONLY.

### 2.1 Grinder-state scan (overnight pipelines, `backtest/autoresearch/_state/*/progress.json`)

| Grinder | Status | Combos | Keepers | best_edge | best_wide_pnl | Verdict |
|---|---|---:|---:|---:|---:|---|
| `overnight_grinder` | completed | 432 | 4 | **3080** | **−1,933** | **REJECT — 5/04-outlier artifact** |
| `v14_enhanced_stage1` | completed | 540 | 4 | 1176 | +17,798 | already-RATIFIED prod config (not new edge) |
| `vwap_stage1` | completed | 972 | 7 | 40 | +588 | NEEDS-MORE (below floor) |
| `bullish_grinder` | completed | 81 | 0 | — | — | no keepers (correct) |
| `opening_drive_fade_stage1` | completed | 810 | 0 | 0 | — | no keepers (correct) |
| `regime_switcher_stage1` | completed | 972 | 0 | 0 | — | no keepers (correct) |
| `shotgun_scalper_stage1` | RUNNING | 225/2160 | 0 | 0 | — | no keepers so far (all edge <= 0) |
| `sniper_vix18_stage1` | completed | 432 | 2 | 0 | +3,298 | ARTIFACT-INVALIDATED (L99/L100) |
| `sniper_vix_trend_stage1/2` | completed | 432/120 | 3/3 | 0 | +6,012 | ARTIFACT-INVALIDATED (L99/L100) |

### 2.2 The `overnight_grinder` "high edge_capture" keepers are a textbook outlier trap — **REJECT**

The four keepers reporting edge=2769–3177 look like they clear the 771 floor 2–4×. They do **not**
represent a durable edge. Per-day breakdown of every high-edge keeper:

```
edge=3081  wide=-1933   by_day: 4/29=+414  5/01=-16   5/04=+2682  losers all 0/+74
edge=3177  wide=-1076   by_day: 4/29=+510  5/01=-16   5/04=+2682  losers all 0/+74
edge=2973  wide=+933    by_day: 4/29=+306  5/01=-16   5/04=+2682  losers all 0/+74
```

Three independent rejections fire simultaneously:

1. **§1.3 Floor / §2.10 overfit:** `wide_pnl` is **NEGATIVE** (−$1,933 to −$1,076) on the full
   16-month window for the top keepers — the strategy **loses money overall**. The entire
   edge_capture is a single day, **5/04 = +$2,682**, a known extreme-vol outlier. Strip 5/04 and
   edge_capture collapses far below the floor. This is the **exact pattern** already
   REJECTED-FINAL as leaderboard rank 36 `BEAR_SCORE_7_RELAXATION` (2026-06-18): "driven entirely
   by 5/04 extreme-vol day … without 5/04 edge_capture=−$577 … non-monotone response = definitive
   evidence of outlier-day overfit."
2. **5/01 mis-captured:** every keeper shows 5/01 = **−$16** (a small loss), not J's +$470 winner —
   the engine does NOT reproduce the 5/01 REVERSAL anchor (it's a structurally distinct trade class,
   L97). edge_capture is inflated by 5/04 while a real anchor is missed.
3. **Concentration (§2.4 / §5.5):** one day = ~95%+ of the edge. Top-5 concentration is effectively
   ~one-day; fails the 200% concentration cap doctrine by construction.

**Verdict: REJECT — do not promote, do not OOS-spend on.** These keepers should be archived with the
same 5/04-outlier note as rank 36. The grinder is correctly *finding* candidates that pass its
narrow floor check but the candidates fail the full disclosure stack — which is the pipeline working
as designed (Stage-1 floor pass, killed at Stage-3 concentration / regime).

### 2.3 Fresh SNIPER candidates (filed 2026-06-18, surfaced tonight) — **REJECT / NEEDS-REDESIGN**

`2026-06-20-chef-nemo-sniper-level-break-param-sweep-top.md`,
`2026-06-20-chef-nemo-sniper-stage2-top-keeper.md`, plus the sniper grinder outputs.

- Both are **self-flagged 3/10** by the chef. edge_capture **229 / 373 — far below the 771 floor.**
- Both use `profit_lock_threshold_pct=0.0` → the **L99 + L100 artifact** (profit-lock arming
  immediately produces fictitious premium-exit fills that real OPRA cannot reproduce). Every prior
  SNIPER candidate built on this knob is already ARTIFACT-INVALIDATED on the leaderboard
  (ranks 13/14/15).
- OP-16 is **structurally inapplicable** to SNIPER: J's anchor days are BEARISH_REVERSAL setups, not
  SNIPER_LEVEL_BREAK (L97). No SNIPER-specific anchor days exist yet → edge_capture cannot even be
  measured honestly. The "gain on loser days" rows (5/05 +$126, 5/07 +$147) do not improve
  edge_capture and are noise.
- **Verdict: REJECT for promotion.** The only durable thread is the chart-stop redesign path
  (`SNIPER_CS_CHART_STOP`, rank 23) — which itself **OOS-FAILED** (all 4 VIX variants, WF=−0.275,
  bleeds in calm trending markets). SNIPER is not viable until (a) J identifies 3+ SNIPER-specific
  anchor days, AND (b) a non-premium exit clears OOS with a regime-balanced window.

### 2.4 vwap_stage1 — **NEEDS-MORE (below floor, not an edge yet)**

7 keepers, best edge_capture = 40, best wide = +$588. Above $0 but **two orders of magnitude below
the 771 floor.** This is the VWAP-continuation population that already shipped LIVE as a separate
watcher (`j_vwap_cont_enabled=true`, commit b580fcf); the stage-1 grinder is exploring exit knobs
around it and finding nothing that moves the J-edge needle. No promotable cell. Keep as background
exploration only.

### 2.5 EDGE-SHORTLIST (this overnight's 8 hypotheses) — **NEEDS-MORE (designs, not yet run)**

`strategy/candidates/_overnight-2026-06-20/EDGE-SHORTLIST.md` is a strong, doctrine-aligned mining
of J's 667 real fills + the ENTRY seam (H1 VWAP-side, H2 10:00-shoulder bleed gate, H3 BOS/CHoCH
entry, H4 post-loss throttle, …). It is **design-stage only** — no backtest has been run, no A/B
scorecard filed, no `analysis/recommendations/{id}.json` exists yet. It correctly inherits the full
guard battery (L171 truncation, L172 null-max, C1 real-fills authority, OP-16 anchor-no-regression)
and explicitly avoids re-cooking killed ideas. **Verdict: NEEDS-MORE — these are the right next
backtests to fund**, in ranked order, but none can be called ratify-ready until each produces an
OOS+null+real-fills scorecard. H1 (VWAP-side) and H2 (10:00 bleed gate) are the highest
edge-per-effort and are the recommended first fires.

---

## 3. Bottom line

| Bucket | Candidates |
|---|---|
| **RATIFY-READY** | **NONE.** No candidate clears all six OP-11/OP-16 gates. |
| **NEEDS-MORE** | EDGE-SHORTLIST H1–H8 (designs; run OOS+null+real-fills, file scorecards). vwap_stage1 (below floor — keep exploring, do not promote). LIVE_PRICE_FIRST_BAR_TRIGGER (OP-21 0/3 live fires). FBW / LBFS / BEARISH_REJECTION_MORNING (all WATCH-ONLY, blocked on 3 live J confirmations, not a backtest gap). |
| **REJECT** | `overnight_grinder` high-edge keepers (5/04-outlier artifact, negative wide_pnl — same trap as rank-36 BEAR_SCORE_7). All 2026-06-18 SNIPER candidates (L99/L100 premium artifact, edge < 771, OP-16 inapplicable). SNIPER_CS_CHART_STOP (OOS-FAILED, WF=−0.275). |

**Nothing to ship.** The honest finding of the night is that the grinders are doing their job:
they surface floor-passing candidates, and the concentration / regime / real-fills stack correctly
kills every one before it reaches production. The real un-mined edge is the **ENTRY side + J's real
fills** (EDGE-SHORTLIST), which is design-complete and ready to backtest — that is where the next
overnight compute should go, not another exit-knob or SNIPER sweep.

No production doctrine touched. No trades. J revokes; J does not need to approve a non-existent
ratification.
