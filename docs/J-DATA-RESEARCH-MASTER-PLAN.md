# J-Data Research Master Plan — "leave no plan untested"

> J directive (2026-06-20, going out): "cover every angle, use my webull data, test extensively, document it so you can work through it methodically, leave no plan untested. there has to be something profitable in there if we just tweak certain parameters. keep working."
>
> **Method (non-negotiable, the anti-overfit guard):** his Webull data (analysis/webull-j-trades/, 655 round-trips 2021-23) DEFINES each hypothesis + the parameter value to try. OUR 2025-26 SPY data + real OPRA fills VALIDATES it forward (chronological OOS, WF≥0.70, all-cuts-OOS, DSR, drop-top5, causal/L166). A param "tuned till it looks good on his data" with no OOS lift is DEAD, not a win. Every angle gets a verdict: **SHIP** (clears the bar live), **WATCH** (promising, OOS-thin), **DEAD** (honest negative — still counts as tested). Ship only what clears; flip live only what's 7/7 incl recent quarter.
>
> **Status legend:** ✅ DONE · 🔄 TESTING · ⬜ UNTESTED · 💀 DEAD · 🚀 SHIPPED/LIVE · 👀 WATCH

---

## A. SETUP / ENTRY angles (what to trade)

| # | Angle | Hypothesis (from his data) | Status | Result |
|---|---|---|---|---|
| A1 | Winner archetypes | momentum-breakout 41% / pullback 26% / reversal 19% / trend-cont 14% | ✅ | gap-and-go shipped; reversal dead; pullback dead-on-live-config |
| A2 | VWAP-aligned continuation | trade the side price is on vs VWAP (64% WR, 92% of days) | 🚀/👀 | VWAP-continuation flip-ready (6/7, recent-Q soft) |
| A3 | Gap-and-go | gap + confirming bar → continuation | 🚀 | LIVE (bear), +$41/t WR 72.6% |
| A4 | Entry quality / confirmed-close | wait for 5m close in your direction (57% vs 33% WR) | 🚀/👀 | live (short); bull-side WATCH (OOS-thin) |
| A5 | **Time-of-day specificity** | his winners' SHARPEST exact window (9:35-10:00 vs 10:00-10:30 vs 11:00-13:00); tighten entry window | 💀 | DEAD — his sharp cells are afternoon (11:00 +17%pct, 13:00); morning detector window-tighten = +$0.6 OOS lift (noise), extend-to-13:00 = +$0.0. Afternoon edge is a *different setup*, not a tweak. [j-entry-specificity.json] |
| A6 | **Day-of-week / OPEX / month-end / event-day** | directional/edge pattern by calendar bucket | ⬜ | — |
| A7 | **Level-keyed entry** | did his winners cluster at PDH/PDL/round/overnight levels (a level-tied trigger) | ⬜ | — |
| A8 | **Trigger × condition sharpness** | which trigger (breakout/pullback/reclaim) × which condition is his sharpest cell | 💀 | DEAD as a tweak — sharp axis is the CONDITION (aligned&confirmed, his best cell=pullback 62%WR/+22%pct), already captured by the live detector + the shipped confirmed-close gate (A4). breakout-ONLY restriction drops the pullback half → OOS −$26.3. reclaim is the trap (37%WR), already structurally excluded. [j-entry-specificity.json] |
| A9 | **Call vs put asymmetry** | separate optimal rules per side (his calls vs puts differ in WR/timing) | 👀 | WATCH (call) — the put side is the ENTIRE source of the 2026-Q2 drag (−$154/t); calls dodged it (+$8). CALL-only lifts most-recent OOS +$16.4 (WF 2.08). BUT sides are anti-correlated across quarters (puts owned 2025-Q2/Q3) → combined book most robust; PUT-only=DEAD. Fix = put-side regime gate (C1), not a side ban. [j-entry-specificity.json] |
| A10 | **Self-PnL state** | did he trade sharper in some streak/regime (beyond revenge L168) — a "hot read" condition | ⬜ | — |

## B. PARAMETER-TWEAK angles ("if we just tweak certain parameters")

| # | Angle | Hypothesis | Status | Result |
|---|---|---|---|---|
| B1 | **Strike selection** | his winners' optimal moneyness (ATM/OTM-1/OTM-2/ITM-1); tweak strike_offset per setup | 🚀 | **SHIP** — his OTM-1/2 doesn't transfer; **gap-and-go ATM→ITM-1 = +$35/t (+42%) OOS, all gates pass** (DEFAULT_STRIKE_OFFSET 0→-1). `docs/J-PARAM-TWEAKS.md` |
| B2 | **Hold-time / time-stop** | when his winners PEAKED → optimal hold ceiling / time-stop per setup | 💀 | **DEAD** — his winners peak ~30min but no early time-stop beats live 15:40 forward; v15 chandelier already captures the fade |
| B3 | **TP target** | the % gain at which his winners typically peaked → optimal TP1 / runner target | 👀 | **WATCH** — his low-TP (~15%) INVERTS forward; sweep re-confirms live tp1=0.50 is OOS-optimal (no change) |
| B4 | Stop distance | adverse-poke distribution → optimal chart-stop width | ✅ | chart-stop correct; buffer dead-knob; ribbon-flip-back is the binding stop (B4b open) |
| B4b | **Ribbon-flip-back buffer** | the knob that actually binds the stop live — is it clipping too early | ⬜ | — |
| B5 | Sizing | 1-2 lots +EV / 3+ catastrophic | ✅ | L168; min-3 + ~6% premium ceiling + post-loss throttle design |
| B6 | **Per-setup-quality sizing tier** | size up his historically-sharpest setup cells | ⬜ | — |

## C. REGIME / FILTER angles

| # | Angle | Hypothesis | Status | Result |
|---|---|---|---|---|
| C1 | **VIX level/character filter** | his winners vs losers by VIX regime → a per-setup VIX gate (may fix VWAP-cont recent-Q softness) | 👀 | VIX *level* DEAD (winner VIX 24.65≈loser 25.01; every band stays bimodal). INVERSE — realized-VOL FLOOR (rvol≥9bps) — lifts VWAP-cont to all-sub-windows-positive w/ clean own-OOS on −8% config (n=31, WATCH). [J-REGIME-FILTERS.md](J-REGIME-FILTERS.md) |
| C2 | **Trend-day vs range-day** | which of his setups worked on which day-type → a day-type router | 👀/💀 | J's strongest split (trend −$1.4/t vs chop −$56/t; bull/trend +$13/t PF1.30 n=116) but ADX/day-type gates DEAD on our VWAP-cont fwd (worst gates). Real J-behavior, dead as live gate. |
| C3 | **Year/market-regime (2021 bull / 2022 bear / 2023 chop)** | does his edge hold across regimes or only one (transfer risk) | 👀 | Book 85% one regime (2022 bear)→can't prove transfer. Stable: bull>bear EVERY year → mild flag on gap-and-go (put-only); corroborates VWAP-cont bull tilt. |
| C4 | Gap vs non-gap day | gap-and-go = gap days only | ✅ | gap is necessary (frequency lever closed) |

## D. COMBINATION / PORTFOLIO angles

| # | Angle | Hypothesis | Status | Result |
|---|---|---|---|---|
| D1 | **Edge portfolio** | stack the validated edges (gap-and-go + VWAP-cont + …) — combined frequency, expectancy, correlation, daily coverage | ⬜ | — |
| D2 | **Setup-quality leaderboard** | rank ALL his setup cells by historical edge × frequency → the priority order to trade | ⬜ | — |

---

## Execution log (updated each cycle as agents complete)

- 2026-06-20: plan authored. Batch 1 launched: A5 (entry-timing specificity), B1+B2+B3 (strike/hold/TP param tweaks), C1+C2 (VIX/day-type regime). Loop alive to grind the rest.
- 2026-06-20: **A5/A8/A9 COMPLETE** (`j_entry_specificity.py` → `j-entry-specificity.json` + docs/J-ENTRY-QUALITY.md §A5/A8/A9). **A5 DEAD** (afternoon edge ≠ morning-detector window-tighten; OOS lift ~$0). **A8 DEAD** (sharp axis is the condition aligned&confirmed = already live via A4; breakout-only restriction drops his best cell=pullback, OOS −$26). **A9 WATCH** (call-side recency tilt OOS +$16.4/WF 2.08 — the put side owns the entire 2026-Q2 drawdown; but sides anti-correlate across quarters so combined book is most robust → the fix is a put-side regime gate (C1), not a side ban). Net: no clean new ship; one valuable regime-localization (Q2 softness = put-side) that sharpens C1, plus three honest negatives.
- 2026-06-20: **C1/C2/C3 COMPLETE** (`j_regime_split.py` [his split] + `j_regime_forward_validate.py` [our fwd fills] → `j-regime-filters.json` + `j-regime-vwap-vix-gate.json` + docs/J-REGIME-FILTERS.md). Pulled ^VIX daily for his 2021-23 dates (yfinance → `webull-j-trades/vix_daily_2021_2023.json`, 100% coverage of 668 trades). **C1 WATCH** — VIX *level* is DEAD as a discriminator (winner mean VIX 24.65 ≈ loser 25.01) and no VIX band fixes VWAP-cont (all stay bimodal); but the INVERSE of a low-VIX gate — a **realized-VOL FLOOR rvol≥9bps** (motivated by his dead-tail bleed + the VWAP bad-month low-vol signature) — lifts VWAP-cont to **all-4-sub-windows-positive with a clean own-OOS** (thr derived IS-only, applied unseen OOS, still all-sub-pos) on the −8% scorecard config: exp +$70/t, OOS +$96.5, DSR PASS, both-dirs+, drop-top5 robust. Removes 88% of dead-summer bad trades by mechanism, not date-fit. Held to WATCH (not SHIP) by n=31<35, config-sensitivity (one sub-window neg on the live chart-stop config), and the need for a new live rvol feature. **C2 WATCH/DEAD** — J's single most robust split (trend-day −$1.4/t vs chop −$56/t; his one positive decent-N cell = bull/trend +$13/t PF1.30 n=116) but ADX/day-type/range-ratio gates are among the WORST on our VWAP-cont fwd (don't transfer); real J-behavioral bleed insight, dead as a live gate on our setup. **C3 WATCH/flag** — his book is 85% one macro regime (2022 bear) so it CANNOT prove cross-regime robustness; the stable cross-year pattern is bull-side > bear-side EVERY year → a **mild transfer-risk flag on gap-and-go (LIVE put-only): J's own history backs a bullish lean, not a bearish edge** (keep base size), and a corroboration of VWAP-cont's bull tilt. Net: VIX-level DEAD, day-type-gate DEAD, **one promising WATCH lever (vol-floor on VWAP-cont)** + an honest transfer-risk flag. Engine untouched; graduated-guards pytest green; files git-added (no commit).
- 2026-06-20: **B1/B2/B3 COMPLETE** (`j_param_tweaks_partA.py`+`partB.py` → `j-param-tweaks.json` + docs/J-PARAM-TWEAKS.md). Method: his winners DEFINE the value, OUR real-OPRA fills VALIDATE forward. **B1 SHIP** — his OTM-1/2 preference does NOT transfer, but **gap-and-go ATM→ITM-1 is a clean forward win: +$35/t (+42%) OOS exp, all-cuts-OOS+/both-dirs+/DSR-PASS/drop-top5-robust** (param: `gap_and_go_watcher.py DEFAULT_STRIKE_OFFSET 0→-1`). ITM-1 dominates ATM at every TP level. **B2 DEAD** — his winners peak ~30min (he exits ~14min) but no early time-stop beats live 15:40 forward (winner-only stat clips runners; v15 chandelier already handles the fade). **B3 WATCH** — his low-TP (~15% median peak) INVERTS forward; sweep re-confirms live tp1=0.50 is OOS-optimal AND caught a baseline-vs-live default discrepancy (no change). Net: **one ship-grade tweak (ITM-1 on gap-and-go)** + two honest overfit-negatives — exactly what the anti-overfit method is for.
