# GAP_AND_GO (H2b) — heartbeat wiring proposal (PROPOSE-ONLY, do NOT apply)

> **Status: PROPOSE-AND-PING-J.** This is the exact, ship-ready edit to trade
> H2b gap-and-go live. It is NOT applied (Rule 9: heartbeat.md / params.json
> changes are J-ratified). The detector, tests, and scorecard ARE shipped (engine
> code, not doctrine). J's role per OP-22/OP-25 is REVOKE, not approve — but the
> bull-side gating question below genuinely needs J's call before applying.

## Why this ships under ship-validated-wins

Scorecard: [`analysis/recommendations/gap-and-go-LIVE.json`](../analysis/recommendations/gap-and-go-LIVE.json).
Config = **ATM, chart-stop-only** (the live detector's config; the doctrinally-correct
exit for a first-strike entry per L51/L55/C2 and the live CHART-STOP-PRIMARY doctrine).

| Gate | Result |
|---|---|
| Causality (no look-ahead) | **PASS** — 96/96 signals, `_gap_and_go_causality_audit.py` |
| OOS positive | **PASS** — 70/30 OOS +$68.6/trade |
| WF median ≥ 0.70 | **PASS** — median WF_norm **+1.866**, all 3 cuts OOS-positive |
| Sub-window stable | **PASS** — 6/6 quarters positive |
| DSR | **PASS** (PSR ≈ 1.000) |
| Both directions positive | **PASS** — C and P both +EV |
| Drop-top-5 robust | **PASS** — +$15.62/trade after removing 5 biggest winners |
| A/B scorecard filed | **PASS** — this proposal + gap-and-go-LIVE.json |
| Live-detector parity | **PASS** — `test_gap_and_go_watcher.py` core == research over 363 days |

Headline (ATM, chart-stop-only): **n=84, exp +$41.6/trade, WR 72.6%, total +$3,494.**
(ITM-1 stronger: exp +$59.2, WR 71.8% — ATM is the conservative default.)

**The discovery scorecard understated this.** Its published +$35.24 / 42.9% used the
v14 default premium stop (−8%), which choked the setup (2026-Q2 = 10/11 premium-stopped
→ WF FAIL). Chart-stop-only is the correct exit and lifts it to WR 72.6% / WF PASS.
Both configs are in the scorecard for audit.

## Live-ability shape (why an open-block, not a scoring filter)

Gap-and-go is a **once-per-day OPEN-bar setup**: it fires on the **first RTH bar
(09:30 ET close)** off the overnight gap + that bar's green/red confirmation, entry
at the **next bar open (~09:35 ET)**. It does NOT match the per-tick continuous-scoring
rubric (which scores against the last closed bar every tick). So it wires as a
dedicated open-block evaluated ONCE, right after the 09:30 bar closes, BEFORE the
normal Scoring section. The live detector `detect_gap_and_go_setup(ctx, prior_rth_close=...)`
already encodes the exact logic; the heartbeat just calls it and routes the signal
through the SAME execution + risk_gate path as a normal entry.

---

## EXACT EDIT — add to `automation/prompts/heartbeat.md`

Insert a new subsection in the **Entry branch** (after `### First-entry-after-stop check`,
line ~322, BEFORE `### Scoring` at line 324):

````markdown
### GAP_AND_GO open-bar setup (NEW — H2b, propose-ready; gate on `params.gap_and_go_enabled`)

> Once-per-day continuation entry off the opening gap. Validated real-OPRA fills,
> chart-stop-only: exp +$41.6/trade, WR 72.6%, n=84, DSR PASS, WF median +1.87 (all
> OOS+), 6/6 quarters +, both directions +. Causality 96/96 PASS. Scorecard:
> `analysis/recommendations/gap-and-go-LIVE.json`. Detector (validated, parity-tested):
> `backtest/lib/watchers/gap_and_go_watcher.py#detect_gap_and_go_setup`.

Read `params.json#gap_and_go_enabled` (default `false` until applied). Evaluate ONLY
when ALL of:
- `gap_and_go_enabled == true`
- the last closed 5m bar is the day's FIRST RTH bar (start == 09:30 ET) — i.e. this
  is the 09:35 ET tick acting on the just-closed 09:30 bar. (Skip on every other tick.)
- `current-position.status == null` (flat) AND flat-verified vs Alpaca (the existing
  09:30-reconcile in `### Flat verification` applies).
- filters 2 (news clear) and 3 (budget>risk) and 4 (day-trades≥1) PASS, and the
  MACRO BIAS INHERITANCE hard-veto is NOT active.

Compute:
- `prior_rth_close` = prior trading day's RTH close (from `today-bias.json#prior_close`,
  the same value premarket already records).
- `gap = first_bar.open / prior_rth_close - 1`.
- Gap-UP (`gap >= +0.0025`) AND first bar GREEN (`close > open`) → **CALLS** (bull).
- Gap-DOWN (`gap <= -0.0025`) AND first bar RED (`close < open`) → **PUTS** (bear).
- SKIP if `|gap| > 0.015` (news-driven runaway) or `|gap| < 0.0025` (no real gap) or
  the first bar did not confirm the gap direction (that is a fade, not a go).

If a side fires:
- **strike**: per-tier (v15 `strike_offset_per_tier`) — ATM is the validated default;
  the live per-tier picker (OTM-2 at $2K Safe) is acceptable (ITM-1 tested stronger,
  OTM proxy directionally valid per L58). Use the account's normal tier.
- **stop = CHART STOP only** = the first RTH bar's OPPOSITE extreme (calls: first-bar
  LOW; puts: first-bar HIGH). Premium stop = the standard −50% catastrophe cap
  (`premium_stop_pct` / `premium_stop_pct_bear`) — already the live default. DO NOT
  set a tight premium stop; that is exactly what choked this setup (−8% → WR 42.9%).
- **sizing**: min 3 contracts (`min_contracts`), premium ceiling ~6% equity
  (`markdown/research/SIZING-STUDY-2026-06-19.md`); `risk_gate.check_order` is the authority.
- **TP / runner / time stop**: the standard v15 stack (TP1 chart-level OR +50% premium
  fallback, `tp1_qty_fraction`; runner 2.5×; 15:50 ET hard time stop). No special exits.
- Route through the SAME `### Pre-execution gate sequence` + `### Execution steps` as a
  normal entry. Log to `decisions.jsonl` with `setup: "GAP_AND_GO"` and
  `trigger: "gap_and_go_open"`. Journal the pre-trade thesis before the order (Rule 8).
- **One per day**: after a gap-and-go entry (or an explicit skip), do not re-evaluate
  this block today.

If no side fires, fall through to the normal `### Scoring` section unchanged (a
non-gap or unconfirmed-gap day just trades the normal book).
````

## EXACT EDIT — add to `automation/state/params.json`

```json
  "gap_and_go_enabled": false,
  "_gap_and_go_doc": "H2b opening-gap continuation, WATCH->LIVE candidate. false until J ratifies. When true: first-RTH-bar gap>=0.25% + confirming bar (green->calls / red->puts), entry next bar, CHART-STOP-ONLY (first-bar opposite extreme), standard v15 TP/runner/time-stop. Validated real-fills chart-stop-only: exp +$41.6/WR 72.6%/n=84, DSR PASS, WF median +1.87 all-OOS+, 6/6 quarters +, both dirs +, causality 96/96 PASS. Detector: backtest/lib/watchers/gap_and_go_watcher.py. Scorecard: analysis/recommendations/gap-and-go-LIVE.json. Revert: set false.",
```

## THE ONE QUESTION FOR J (genuinely needs your call)

Gap-and-go's **call side** is independently +EV in the scorecard (both directions
positive). But CLAUDE.md OP-16 keeps **all bull-side new entries DRAFT until J has 3
live wins on a bull setup** (BULLISH_RECLAIM is still DRAFT). Gap-and-go calls are a
*different, separately-validated* setup — but the doctrine is doctrine. Two options:

- **(A) Ship BOTH directions** (calls + puts). The data supports it; gap-up-and-go is
  the larger sub-sample (C n=55 vs P n=29). Requires J to extend the bull-side
  green-light to this specific setup.
- **(B) Ship PUT side only first** (bear gap-and-go), mirroring the
  BEARISH_REJECTION-only scope lock, accumulate live confirmations, add calls later.
  More conservative; respects the current bull-DRAFT posture; leaves edge on the table
  (the call side is the bigger sample).

Recommendation: **(A)** — the call side cleared the same independent bar (DSR PASS,
OOS+, both-dir+); gating it to (B) forfeits the larger half of a validated edge. But
this is a Rule-6/OP-16 doctrine call, so it is J's to make.

## Revert

Set `params.json#gap_and_go_enabled: false` (a no-op flip — the open-block becomes
inert without touching heartbeat.md). The detector + tests stay in tree (engine code).

## Provenance / repro

- Detector: `backtest/lib/watchers/gap_and_go_watcher.py` (+ `test_gap_and_go_watcher.py`, 13 tests incl. full-dataset parity).
- Causality audit: `backtest/autoresearch/_gap_and_go_causality_audit.py` (96/96 PASS).
- Walk-forward: `backtest/autoresearch/gap_and_go_walk_forward.py` (+ exit-sensitivity `gap_and_go_exit_wf.py`).
- Scorecard generator: `backtest/autoresearch/gap_and_go_ratify.py` → `analysis/recommendations/gap-and-go-LIVE.json`.
- Gym: 87/87 PASS after registering the watcher (`crypto.validators.runner --skip-replay`).
