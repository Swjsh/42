# EOD winners dial-in — 2026-08-03 (all four trades)

> **Written 2026-08-03 evening** (clock verified via `setup/scripts/et_clock.py`: 16:41 ET at analysis start — market closed; box runs Mountain, ET = local+2). All wall-clock times **ET**; OPRA bar stamps converted UTC→ET explicitly.
> **Data:** real broker fills (`fills-ledger.jsonl`, equities re-verified against `GET /v2/account` per arm this session) + real 1-min OPRA trade bars + the engines' **own recorded per-tick quotes** (`decisions.jsonl` / `core-decisions.jsonl` `exit_pass` rows). Zero synthetic premiums.
> **Machinery:** every policy replay runs through the REAL `exit_manager.plan_exit_actions`; menu = `winner_autopsy.EXIT_MENU` verbatim; conventions = winner-autopsy standard (entry+1, threshold fills). Full cell data: [`EOD-2026-08-03-WINNERS.json`](EOD-2026-08-03-WINNERS.json).

> ## ⛔ n=4 IS AN ANECDOTE.
> Every counterfactual dollar in this document is computed over **four trades on one gap-up trend day**. Nothing here ratifies a sizing, exit, hold, or anchor change beyond what is already staged and evidenced elsewhere. Graveyard collisions are flagged inline. Oracle bounds are labelled **ORACLE** and are not achievable by any live rule.

---

## 1. The one thing

**The clean lever today was SIZE, not exits.** The same four entries at qty 10 with the engine's own exit behavior pay **$1,342 vs the realized $534** — inside every Rule-6 cap (≤ 10.6% of equity vs 30/50% limits), with zero change to PDT usage. SHIP C (already staged, risky-3-only, premium < $0.50 → qty 10) captures **+$176** of that gap. "Hold the runner longer" looks bigger on paper (+$1,686 runner-only, +$4,386 never-scale-at-all) **but that is the graveyard's book-wide NULL shape** (hold-longer = **−$451.50 across 21 winners**), the two "hold" cells in the menu are **one policy double-counted** (C14 dead-knob, documented 07-31), and **today's own 13:21 trade disproves it at the close** — the 757C runner held to 15:59 makes **+$19 vs the trail's +$26**. The exit **minute**, not the exit rule, dominates every hold cell (07-31 §4.4a, reproduced today).

| | Realized | Best staged/defensible | Hold-longer fantasy |
|---|--:|--:|--:|
| Day (4 winners, gross) | **$534.00** ($533.22 net of fees) | qty-10 same fills: **$1,342** (ANECDOTE n=4) | unprotected hold-to-15:50: $4,920 ⚠ graveyard NULL + ORACLE-adjacent |

---

## 2. The four trades — broker truth

| Arm | Symbol | Entry (fill × qty) | Limit (anchor) | TP1 | Runner | Realized | Equity check |
|---|---|---|---|---|---|--:|--:|
| safe-3 | 754C | 09:42:04 · 0.37 × 3 | **0.42** | 2 @ 0.92 (10:03) | 1 @ 0.72 (10:05) | **+$145.00** | $5,144.85 ✓ |
| risky-1 | 754C | 09:42:05 · 0.37 × 5 | **0.41** | 3 @ 0.60 (09:54) | 2 @ 0.75 (10:04) | **+$145.00** | $5,144.76 ✓ |
| risky-3 | 754C | 09:42:06 · 0.38 × 5 | 0.38 (=fill) | 3 @ 0.73 (10:01) | 2 @ 0.735 (10:05) | **+$176.00** | $5,175.76 ✓ |
| safe-2 | 757C | 13:21:50 · 0.53 × 3 | **0.57** | 2 @ 0.74 (13:31) | 1 @ 0.79 (13:40) | **+$68.00** | $5,067.85 ✓ |

Shapes (verified from the engines' own tick records, not assumed): safe-3 TP1 +100% / trail 15%; risky-1 TP1 +50% / trail 15%; risky-3 TP1 +100% / trail 20%; safe-2 (core extra-setups route) TP1 +30% / trail 15% / **−8% premium stop**. All TP1 splits `int(qty × 0.667)`. Fleet time stop 15:50; core 15:40. All three fleet entries = the same 09:42 `BULLISH_RECLAIM_RIDE_THE_RIBBON` ELITE signal @ trigger 750.98.

**What the contracts did after we left:** 754C printed a day high of **$4.61 at 15:28** (+1,113–1,146% over our fills — we were flat by 10:05). 757C printed **$1.73 at 15:02**, then bled to **0.72 by 15:59**. The morning wave melted up all day; the afternoon wave peaked and faded. Both facts drive everything below.

---

## 3. (a) Sizing — the grid

Construction: same real fill prices and times, legs split by the engine's own `int(qty × tp1_qty_fraction)`. Flat-slippage assumption disclosed: 754C traded **130,915 contracts** during the 09:42–10:05 hold (353,110 full day), 757C 70,815 during 13:21–13:41 — selling 6–7 rather than 2–3 contracts into those books is a rounding error, but it *is* an assumption. **ANECDOTE n=4.**

| Cell (per trade) | safe-3 | risky-1 | risky-3 | safe-2 | Day |
|---|--:|--:|--:|--:|--:|
| **Actual** (3/5/5/3 lots) | 145.00 | 145.00 | 176.00 | 68.00 | **534.00** |
| qty 5 (split 3/2) | 235.00 | 145.00 | 176.00 | 115.00 | 671.00 |
| **qty 10, engine split 6/4** | 470.00 | 290.00 | 352.00 | 230.00 | **1,342.00** |
| qty 10, 7/3 two-leg | 490.00 | 275.00 | 351.50 | 225.00 | 1,341.50 |
| qty 10, 5/3/2 (leg-3 rides to time stop) ⚠ | 1,110.00 | 959.00 | 1,009.50 | 325.00 | 3,403.50 |
| qty 10, 5/3/2 (leg-3 to 15:59) ⚠ | 1,030.00 | 879.00 | 929.50 | 221.00 | 3,059.50 |

- **Rule 6:** qty 10 max notional today = $530 (safe-2) / $370–380 (754C wave) = **7.4–10.6% of $5,000 equity** — far inside Safe 30% / Bold 50%. Shrink-not-deny unaffected. Min-3-contracts satisfied at every size.
- **PDT:** these paper accounts **do not expose `daytrade_count`** (raw account payload carries no day-trade field — probed this session). Under FINRA matched-round-trip counting, each arm consumed **1 day trade today regardless of qty**, 4 arms × 1 = structurally spread across the fleet; **qty does not change the count**. Whether a **3-leg** scale-out burns 1 or 3 under Alpaca's strict pairing is **UNVERIFIED on paper** (field absent) — verify before any multi-leg shape ever nears live money.
- **SHIP C** (staged, applies tonight): risky-3-only, premium < $0.50 → qty 10. Today it fires (0.38 < 0.50) and is worth **+$176** (352 vs 176). It does NOT cover safe-3 (right premium, wrong arm) or safe-2 (0.53 ≥ 0.50). The other arms' qty-10 cells are **not covered by any staged change** — they are the A/B evidence SHIP C's kill-criterion window will generate.
- **⚠ Schema finding:** a **three-leg scale-out is not expressible in `exit_manager` today** (two-stage TP1+runner design — same class as the 07-31 "the knob J is imagining does not exist" finding). The 5/3/2 and 7/3 rows are constructions requiring a code change, and the 5/3/2 leg-3 ride **collides with the hold-longer graveyard family** (flagged ⚠) — it is 84% "unprotected hold" by P&L weight on the 754C wave.

---

## 4. (b) Hold-longer — runner-leg variants on the real path

Construction: keep the actual TP1 legs; replace the actual runner exit. **Ribbon-flip: the ribbon read BULL on all 772 core ticks today — the flip exit was structurally incapable of firing** (same as 07-31: BEAR count zero). **Trendline-break: the engine's live wick-primary support line logged 79 ticks today — 72 INTACT / 7 TESTING / 0 BROKEN — a confirmed-break exit never fires either.** Both therefore degenerate to the arm's time stop (15:50 fleet → 754C close 4.02; 15:40 core → 757C close 1.24).

| Runner variant | safe-3 (1 ct) | risky-1 (2 ct) | risky-3 (2 ct) | safe-2 (1 ct) | Day Δ vs actual |
|---|--:|--:|--:|--:|--:|
| **Actual trail exit** | 35.00 | 76.00 | 71.00 | 26.00 | — |
| To ribbon-flip → **never fired**, = time stop ⚠ | 365.00 | 730.00 | 728.00 | 71.00 | **+1,686.00** |
| To trendline-break → **never fired**, = time stop ⚠ | 365.00 | 730.00 | 728.00 | 71.00 | +1,686.00 |
| To 15:59 close ⚠ | 325.00 | 650.00 | 648.00 | **19.00 (−7 vs actual)** | +1,434.00 |

⚠ **Graveyard, flagged on every cell:** hold-longer is the book-wide NULL — **−$451.50 across all 21 winners** (07-31 population run). Take-profit-earlier ×3 DEAD, pre-TP1 trailing lock ×4 DEAD, level-target exit 0/144 DEAD. Today is one day, and it is *exactly the day shape that flatters holding* (gap-go melt-up).

**The honest structure of today's evidence:**
- On the **09:42 wave**, every hold cell wins huge — the 754C never looked back and the trail's 15–20% band was the whole cost.
- On the **13:21 wave, holding to the close LOSES to the shipped trail** (+19 vs +26). At the core's own 15:40 stop it still wins (+71) — and between 15:40 and 15:59 the same cell swings from +71 to +19. **The exit minute dominates the exit rule** — 07-31 §4.4(a) reproduced on fresh data.
- **Regime-conditional hold:** the day-type early-classifier is **NULLED** (C22 family — backward-looking classifiers anti-correlate with exactly the regimes that pay). A live-expressible proxy exists and is **pre-registered below — NOT armed**.

### PRE-REGISTERED (measurement only, frozen here, NOT armed)

> **PROXY-HOLD-2026-08-03:** At the tick where TP1 fires, tag the trade `gap_go_candidate` iff **ribbon == BULL AND ribbon spread_cents ≥ 150 AND VIX < 17**. (Today all four TP1 ticks pass: spreads 268/320/320/205c, VIX 16.08/16.25/16.21/15.57, ribbon BULL ×4.) Nightly winner-autopsy accrues, per tagged trade, runner-to-time-stop vs actual-trail P&L on real OPRA. **Decision bar: n ≥ 20 tagged trades, net positive, and regime-stratified (the tag must separate winners of the hold from losers — today's safe-2 shows a tagged trade where holding to the close loses).** No live knob moves before that bar; this paragraph is the pre-registration of record.

---

## 5. (c) The anchor-bug tax — precisely, both directions

Mechanism (staged SHIP A fixes it tonight): exits anchor to the **limit** price, not the **fill** (240/240 historical legs). Today's per-trade truth, from the engines' own ticks:

| | safe-3 | risky-1 | risky-3 | safe-2 |
|---|--:|--:|--:|--:|
| Anchor (limit) vs fill | 0.42 vs 0.37 | 0.41 vs 0.37 | 0.38 = 0.38 | 0.57 vs 0.53 |
| TP1 threshold: wrong → right | 0.84 → 0.74 | 0.615 → 0.555 | 0.76 (=) | 0.741 → 0.689 |
| First engine tick ≥ right / ≥ wrong | 10:00:04 / 10:03:03 | 09:53:03 / 09:54:03 | 10:01:03 (=) | 13:28:03 / 13:31:03 |
| Extra full-size exposure (engine-eye) | **3 min** | 1 min | 0 | 3 min |
| Pre-TP1 stop (wrong anchor) | 0.21 (−43% of fill) | 0.205 | 0.19 | **0.5244 (fill −1.06%!)** |
| SHIP-A replay delta (fix − bug) | **−$34.45** | −$18.00 | $0.00 | −$10.40 |

- **Today, the late TP1s left NOTHING — they captured MORE.** The tape was rising through every delay window, so the wrong (higher) thresholds sold higher: the bug-anchored replay beats the fill-anchored replay by **$62.85** across the four (of which **$48.40** is the clean TP1-threshold component; $14.45 is safe-3's convention-sensitive trail knock-on). safe-3's real TP1 fill (0.92 into the 10:03 spike) beat even its wrong threshold by +$16 over the modeled 0.84. **SHIP A recovers zero dollars on this day-shape and would have realized ~$63 less.**
- **What SHIP A actually buys — the other tail:** safe-3 ran 3 ticks at full size, +100%-unrealized, protected only by a cat stop sitting at **−43% below fill** (0.21). On a fade from 10:00, that position gives back the entire trade to a stop that was never supposed to be the exit. And safe-2's wrong-anchor stop sat at **0.5244 = 1.06% below its own 0.53 fill** — a one-tick wiggle from a whipsaw stop-out of what became +$68 (its worst tick, 0.55 at 13:22, cleared by 2.6¢). **The bug's cost is asymmetric risk, not average dollars; today was its favorable tail.** SHIP A ships tonight as staged — this table is its honest price on melt-up days, stated in advance.
- Correction to this morning's package (substance stands, window wrong): safe-3's above-true-TP1 zone was **09:59–10:02** (tick best 0.73→0.81), not "09:51–09:56"; the ticks show best < 0.70 before 09:58.
- Parity control (bug-anchored replay vs actual fills): safe-3 −3.00, risky-1 −38.40, risky-3 −5.20, safe-2 −4.00. The risky-1 gap is the known bar-low-vs-quote-sample artifact (bar lows pierce trail stops the 1-min quote sampling missed). **Treat ±$5–38/trade as the error bar on every replay cell in this document**; the SHIP-A deltas are within-convention (both sides share the artifact).

---

## 6. (d) Capture rate

| Measure | Value | Label |
|---|--:|---|
| Realized, 4 winners | **$534.00** | broker fills |
| Best single fixed policy (`trail_only_no_tp1` = `hold_to_time_stop`) | $4,920.00 | ⚠ graveyard NULL shape; **one policy counted twice** (C14 duplicate — with `arm_scope=post_tp1` and no TP1 the lock never arms; menu is 6 distinct policies, not 7) |
| **Capture vs best fixed policy** | **10.9%** | **ANECDOTE n=4 < 8 floor — winner_autopsy itself refuses to headline this** |
| vs per-trade best | 10.9% | HINDSIGHT (same cells win everywhere) |
| vs oracle (sell all at post-entry high) | 9.1% of $5,867 | **ORACLE — unachievable, bounds only** |
| Best *live-shaped* policies for comparison | `all_out_at_tp1_100` $645 / `tp1_100_trail_10` $645.60 / `tp1_100_trail_20` $627.40 | realized $534 ≈ 83–85% of these |
| **Book capture (population, n=21, standing)** | **101.9%** | winners-only; the anecdote and the book disagree — **the book wins** |

Per-trade: safe-3 13.2% (best variant $1,095) · risky-1 8.0% ($1,825) · risky-3 9.7% ($1,820) · safe-2 **37.1%** ($183.40 — its best variant is `tp1_100_trail_20`, a live-shaped policy, not a hold). This is the same shape as 07-31: the single melt-up day screams "hold longer" at ~10% capture while the 21-winner population says our shipped exits beat every fixed policy. **Winners-only caveat applies to every column: these policies are scored only on trades that already won.**

Note: safe-2's menu cells run under the winner-autopsy 15:50 convention; its live core stop is 15:40 (closes 1.13 vs 1.24) — affects only its two hold cells, by ~$33.

---

## 7. Schema/visibility findings (not results)

1. **Three-leg scale-out inexpressible** — `exit_manager` is two-stage by design; any 5/3/2 shape needs a code change first (§3).
2. **`trail_only_no_tp1` ≡ `hold_to_time_stop`** on all 4/4 today (as on 21/21 on 07-31) — the C14 duplicate is still in `EXIT_MENU`; "hold longer *with* protection" remains untested because pre-TP1 arming is itself graveyarded.
3. **The safe-2 entry has NO decision row** — core-decisions.jsonl carries zero ENTER/extra-setup rows today (the 13:21:50 entry is visible only via `entry-claim.json`, the broker, and later `exit_pass` ticks; the primary path was logging SKIP_ELITE_BULL at 13:21:03). An order-placing path with no decision-ledger row is the L244 shape — flagged for a standalone fix.
4. Ribbon-flip exit: 0 fireable ticks in 772 (second consecutive session) — corroborates the standing ribbon-exit-redundancy finding; no action here.

---

## 8. Method / biases

- Realized = broker fills; replays = real 1-min OPRA via the real `plan_exit_actions` (threshold fills, entry+1, intrabar-optimistic → variants flattered vs realized; bias runs against the shipped exits, not for them).
- Structure stops unmodelled in replays (replay never supplies `last_closed_5m_close`); zero structure stops fired live today, and price never approached trigger 750.98 post-entry — divergence ≈ 0 today.
- Sizing cells assume flat slippage at 2–3× leg size (volume disclosed §3). Engine-tick counterfactuals use the engine's own recorded quotes — no hindsight feed.
- Sources: `automation/state/fills-ledger.jsonl` · `automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl` · `automation/state/core-decisions.jsonl` · `analysis/trendlines/trendline-log.jsonl` · `automation/state/fleet/accounts.json` · live `GET /v2/account` ×5 · OPRA `v1beta1/options/bars` ×2 symbols · `analysis/staged/AFTER-CLOSE-PACKAGE-2026-08-03.md` · compute: scratchpad `lens1_compute.py` (reuses `winner_autopsy` + `exit_shape_parity_study` + `exit_manager`; conventions unchanged).
