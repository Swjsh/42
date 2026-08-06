# TP1 REACHABILITY — the full grid (Lane 2, 2026-08-06)

**VERDICT: DO_NOT_ARM tonight. One cell — `R_tp100_f50` (keep TP1 at +100%, sell HALF instead
of 2/3 when it hits) — passes 7 of 8 gates and 3 of 4 auto-ratify bar components, is the ONLY
BH-FDR survivor in a 28-cell family (p=0.0026), helps the runner anchor (+$628.05), and fails
exactly one frozen gate: G4 sub-window stability, on DISPERSION (only 2 of 4 sub-windows carry
≥5 changed trades; all four windows are positive). The bar is not softened to ship. Prereg
stays FROZEN with its forward clock. Every other cell in the grid is refuted, most of them
brutally.**

- Frozen prereg: `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json`
  (commit `24c4832d`, committed BEFORE the runner existed — git-provable).
- Runner: `backtest/tools/tp1_reachability_2026_08_06.py` (51.8s, 32 cells).
- Scorecard (every cell disclosed): `analysis/recommendations/tp1-reachability-2026-08-06.json`.
- Exits re-derived ONLY through `walk_exit_manager` → the REAL
  `exit_manager.plan_exit_actions`. Never simulator_real.

## 0. Validity — quoted, not asserted

| check | result |
|---|---|
| popA CONTROL reconciliation vs source replay | **0 mismatches** (VOID rule not triggered) |
| runner anchor cohort | **n=35, $15,497.25** — matches catcap to the cent |
| Monday 08-03 CONTROL realized vs broker-verified header | **$534.00 vs $534.00, diff $0.00** |
| null cell `R_tp100_f667` on popA | delta **$0.00** (grid reproduces the registry shape exactly) |
| week CONTROL day totals (real fills) | 534.00 / 3,624.00 / −1,935.00 / 1,465.00 — the broker-verified week |

Population A = the pinned 391-day replay (n=191, real OPRA, entries frozen, 15:40 time stop).
Population B = the FULL 4-session week 2026-08-03..06, all 5 arms, real broker fills,
sequential one-position walks per arm-day; week deltas measured against **CONTROL_WALK**
(replay divergence Mon −36.00 / Tue +1,992.00 / Wed +452.94 / Thu −207.60 is therefore NOT in
any reported delta).

## 1. Mechanical distinction (required by the lane, stated before the numbers)

A **reachable TP1** banks a partial and THEN arms the post-TP1 lock
(`exit_manager.py:483-496`: TP1 fill → sell `int(qty*fraction)`, runner_stop→BE,
`profit_lock_armed=True`; `:506-516`: chandelier trail on the runner). That machinery is
**validated live** — risky-1's +50% `exit_patch` fired it on 08-05 for +$347 while siblings
rode to the −50% cap. The five-times-dead cell is `profit_lock_arm_scope="full"`
(`:389-395`): it arms the trail on the FULL position BEFORE any profit banks. **Every cell in
this grid keeps `arm_scope="post_tp1"`.** What the grid SHARES with the graveyard is the
result-side risk — early profit extraction damaging the runner cohort — which is why
G3 anchor-no-regression was frozen as the operative veto. The grid confirmed that veto's
bite everywhere except the fraction-only column.

## 2. The grid — popA aggregate Δ / runner-cohort Δ (dollars vs CONTROL)

| tp1 \ fraction | f=0.50 | f=0.667 (live) | f=0.80 |
|---|---|---|---|
| +30% | **−8.15** / −6,461.50 | −2,032.85 / −8,355.15 | −2,607.70 / −8,999.65 |
| +40% | −167.95 / −5,308.70 | −2,104.20 / −7,070.00 | −2,504.20 / −7,635.40 |
| +50% | −903.25 / −3,775.95 | −2,865.80 / −5,615.70 | −3,283.45 / −6,130.05 |
| +75% | −408.55 / −1,718.45 | −1,920.65 / −2,948.10 | −2,209.20 / −3,164.40 |
| +100% | **+910.05 / +628.05** | 0.00 / 0.00 (null) | −148.35 / −76.35 |

**Monotone in fraction at all five TP1 levels** (sell less at TP1 → strictly better popA
aggregate). The f=0.667 column reproduces catcap's D-axis and E2-2026-07-28 to the cent —
replication, not discovery.

- **The reachable-TP1 axis stays dead at every fraction.** Even the gentlest new cell,
  `R_tp30_f50` (aggregate −8.15), destroys the runner anchor (−$6,461.50) and Tuesday
  (−$2,547.64). Frozen prediction P1 confirmed: smaller fractions shrink the damage, never
  flip it. The lane's "$1,682 of Wednesday" (reconfirmed here: `R_tp50_f667` Wed +$1,683.25)
  remains purchasable ONLY at ~2× that cost on Tuesday (−$2,906.24) plus a −$5,615.70 anchor
  hole. Settled twice before; now settled at three fractions.
- **`R_tp75_*`**: intermediate everywhere, clears nothing. Grid-fill complete.
- **TP1 fire rates** (popA walks): +30% fires on 41.4% of trades, +50% on 29.3%, +100% on
  20.4%.

## 3. The one cell that almost shipped — and the gate that stopped it

`R_tp100_f50`: TP1 stays at +100% (unchanged trigger), but when it hits, sell **half** instead
of 2/3 — one more contract keeps riding the validated post-TP1 chandelier.

| gate | value | pass |
|---|---|---|
| G1 popA aggregate | **+$910.05** | ✅ |
| G2 ex-best-trade | +$725.10 | ✅ |
| G3 runner anchor | **+$628.05** (helps the profit engine) | ✅ |
| G4 sub-window stable | 2025H1 +228.95 (n=4) / 2025H2 +333.20 (n=13) / 2026Q1 +253.20 (n=4) / 2026Q2p +94.70 (n=10) | ❌ **FAIL — dispersion** |
| G5 drop-best-day | +$725.10 | ✅ |
| G6 Tuesday HARD | **+$1,060.20** | ✅ |
| G7 week total | +$593.95 | ✅ |
| G8 BH-FDR q=0.10 | p=0.002617, the ONLY survivor of 28 | ✅ |
| OOS (2026) | +$347.90 | ✅ |
| WF | 0.80 ≥ 0.70 | ✅ |

**Why G4 failed, plainly:** the frozen rule requires delta ≥ 0 in ≥3 sub-windows that each
contain ≥5 changed trades. Only 31 of 191 trades change under this cell (only +100%-reachers
with qty where `int(qty·frac)` differs), so just two windows (2025H2, 2026Q2p) reach the
5-changed-trade floor — and 2 < 3 fails by construction. **All four windows are positive**;
the gate failed on evidence *dispersion*, not on any negative window. The prereg's verdict
rule is ANY-gate-fail → DO_NOT_ARM, and the lane's instruction is "do not soften the bar to
ship." So it does not ship tonight. That is the whole story: not refuted — **under-dispersed**.

**Robustness signals that survive honest scrutiny:** dose-response coherent (f=0.80 mirror
cell is −148.35 — selling MORE at +100% hurts, selling LESS helps, at every level);
not single-trade luck (ex-best +725.10) nor single-day luck (drop-best-day +725.10); WF 0.80;
positive in all four sub-windows and all four week sessions net of the risky-1 decomposition
below (Tue +860.70, Wed $0.00, Mon +1.00, Thu −30.95).

**What this cell does NOT do: fix Wednesday.** Its Wednesday contribution is exactly $0.00
(no +100% fire on Wednesday). Wednesday's exit-config money stays where catcap left it —
buyable only by the Tuesday-killing reachable-TP1 lever.

## 4. Disclosed layering artifact — and a free side finding on risky-1's live A/B

Per the frozen (catcap-inherited) convention, the cell patch is OUTERMOST and overrides
risky-1's own `tp1_premium_pct=0.5` exit_patch. So on the week, `R_tp100_f667` is NOT a null
cell: it measures **removing risky-1's live +50% TP1** — Mon +55.50 / Tue +199.50 /
**Wed −788.50** / Thu +296.70 = **−$236.80**. Read the other direction: **risky-1's live +50%
arm patch is week-net POSITIVE (+$236.80), all of it Wednesday defense** — the live A/B arm is
earning its keep this week. (n=1 week; its own A/B clock keeps running.)
The `R_tp100_f50` week vector net of this shared revert: Mon +1.00 / Tue +860.70 / Wed 0.00 /
Thu −30.95 = **+$830.75 pure fraction effect**. popA numbers are uncontaminated (no arm
patches there).

## 5. vwap axis — a structurally dead knob this week

All 15 `W_*` cells: **$0.00 delta on every session.** 13 vwap-attributed week positions were
walked; none ever reached even +30% MFE before its −6% premium stop/exit, so no TP1 level in
the grid can express and fraction changes have nothing to act on (any fire would have moved
P&L via the `int(qty·frac)` split — zero everywhere proves zero fires). Matches the live
ledger (vwap median MFE +1.5%). Week-only, n-small, descriptive by prereg; ship-ineligible by
prereg. The vwap TP1 lever, if one exists, is an entry-quality question, not an exit knob.

## 6. The reachability reconciliation the lane demanded

Two "conflicting" published claims, now bridged — the measure gap dominates, the population
gap is small:

| measure | population | median MFE | reach +100% |
|---|---|---|---|
| unconditional post-entry session max (bar HIGH) — **upper bound** | 391-day replay, n=191 | +83.8% | 45.0% |
| **in-trade under CONTROL walk** (bar-OPEN point-sample, truncated at actual exit) | 391-day replay, n=191 | **+15.2%** | **21.5%** |
| live-ledger `best_premium` (in-trade, production exit manager's own eyes) | recent live book, n=124 | +16.3% | 14.0% |

The lane's "only 14% ever reach +100%, median +16.3%" was the RIGHT measure (in-trade);
catcap's 45%/+83.8% was the labeled upper bound. Same-measure popA lands at 21.5%/+15.2%;
the residual 21.5%→14% gap is population/regime (391 days incl. trends vs the recent
VIX-pinned book). Quote each number only with its measure + population attached.

## 7. Caveats — stated, not buried

1. **The changed-cohort is thin by construction**: `R_tp100_f50` changes only 31 of 191
   trades (~1.6/month). That is WHY G4 failed; it is also why the +$910.05 should not be
   annualized in anyone's head.
2. Week deltas are anecdote-scale (4 sessions, 47 positions, 9 suppressions in re-walked
   cells) and carry the Thursday quote-luck noise floor ($210 on a 3-cent stream divergence).
3. popA contract bars are 5-minute OPRA — the known one-directional intra-bar under-detection
   (magnitude $1,821.75 aggregate, `option_pricing_real` disclosure) applies EQUALLY to all
   cells; relative deltas are the gated quantity.
4. Suppression coupling: in ribbon cells, changed exit times alter which later real entries
   survive (e.g. the −63.84 "vwap" split inside `R_tp75_f50` is suppression interaction, not
   a vwap shape effect). Not separated here; disclosed.
5. Three unattributed positions HELD_AT_REAL in every cell (arithmetically inert), same two
   as catcap plus Monday's safe-2 757C.
6. The runner-anchor cohort total carries catcap's disclosed $276.80 selection-rule gap vs
   EXIT-LEAK's published number; deltas unaffected.
7. No ORACLE column anywhere; every number is live-executable under the real exit engine.

## 8. Forward clock (frozen; restated)

Re-adjudicate when **risky-1's live +50% arm reaches n≥30 ribbon fills post-2026-08-03**, or
by **2026-09-05**, whichever first. For `R_tp100_f50` specifically, the binding evidence is
+100%-TP1 fires (~20% of entries, ~31 changed trades in 19 months): the honest path to
clearing G4-as-frozen is MORE fires — i.e. re-run this exact frozen grid at the clock with
the accumulated live book appended, no new knobs, no re-tuned gates. If the cell is real, the
dispersion cures itself; if it was luck, the windows will say so.

## 9. Artifacts

| path | what |
|---|---|
| `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json` | frozen prereg, commit `24c4832d` |
| `analysis/recommendations/tp1-reachability-2026-08-06.json` | A/B scorecard, all 30 tested+null cells |
| `analysis/deep-research/TP1-REACHABILITY-2026-08-06.json` | full per-cell detail + week positions |
| `backtest/tools/tp1_reachability_2026_08_06.py` | the runner |
| `backtest/tools/_pull_monday_broker_fills_2026_08_03.py` + `backtest/data/_week_orders_2026_08_03.json` | Monday book (read-only pull, reconciled $534.00 = header) |
