# H4 — PROFIT-LOCK SCOPE (arm at +5% favor pre-TP1 vs today's post-TP1-only)

**Stamp:** 2026-09-03T10:24 ET (task) · run executed same session, market OPEN, no broker/network calls, cached data only.
**Slug:** `profit-lock-scope` · JSON: [`profit-lock-scope.json`](profit-lock-scope.json)
**Scripts:** `backtest/tools/money_profit_lock_scope.py` (main walk), `backtest/tools/money_profit_lock_scope_finalize.py` (WR/PF + sub-window addendum) — both READ-ONLY, no trading-path file touched, no orders placed, nothing armed.

## Verdict (headline)

**MIXED — do not ship as tested.** `profit_lock_arm_scope='full'` (arm the chandelier at +5% favor before TP1 fires, vs today's live `'post_tp1'`) is net **positive on the one arm whose dollar figures this session can trust** (safe-2: +$2,578.41 over 88 round trips, bootstrap 95% CI **[$0.59, $55.86]/trade — barely excludes zero**), driven by rescuing small pre-TP1 "orphan band" losers (WR 29.5%→36.4%, PF 0.73→1.40 in the replay). But the SAME trusted arm shows the effect is **not recency-stable** (most recent chronological quarter, 2026-08-18..09-02, is **net -$327.45**) and **directly hurts 3 of the 4 named big winning days** (08-06, 08-27, 08-28: -$880.90 combined on safe-2 alone, incl. two winners cut to **exactly $0**). This reproduces the exact failure mode the frozen 2026-08-06 prereg flagged as its single most probable risk and never got measured — it has now been measured, and the risk is real.

## 1. Prior artifacts — verdicts quoted verbatim (read before this run, per task)

### `profit-lock-arm-scope-prereg-2026-08-06.json`
- **Status at freeze: "FROZEN — runner NOT yet built."** No runner was ever built or committed after this freeze — confirmed this session: `grep -ril "arm-scope" analysis/` returns only this one prereg file, no result artifact. **This session's run is the first empirical execution of that hypothesis, ~4 weeks after it was frozen.**
- Motivating finding: "the orphan band" — a closed round trip whose peak premium reached ≥+50% over entry but whose TP1 never filled. Measured real fills (engine attribution, entry premium ≥$0.20): **n=10, winners=0, realized_total=-$1,510, mean/contract=-$31.50** — every one gave back 100%+ of a ≥50% unrealized gain.
- Negative result constraining the fix: "Lowering TP1 to +50% blanket is NET NEGATIVE and is NOT the fix" — counterfactual rescue of orphan band +$2,922 vs cost on the ≥100%-MFE/TP1-fired cohort -$3,235, net **-$313**. Static TP1 height is not the lever; the arming CONDITION is the candidate axis instead.
- Explicit self-warning, quoted verbatim: *"the 08-04 trend-day winner is the exact trade a 12.5% trail armed at +5% favor is most likely to cut short. That is the single most probable failure mode and the anchor gate above exists to catch it."* **This session's replay confirms that exact concern generalizes to 08-06/08-27/08-28 as well** (08-04 itself came back flat-to-positive for safe-2 in this replay — see §6).
- Gates pre-registered (never run to a verdict): net_positive_on_full_population AND MFE≥100%+TP1-fired-cohort flat-or-better AND orphan_band_improves AND OOS_positive AND WF≥0.70 AND sub_window_stable AND anchor_no_regression (08-04 C769 runner must not be stopped early).

### `dynamic-exits-prereg-2026-08-09.json` / `dynamic-exits-forward-prereg-2026-08-09.json`
- Verdict (quoted): **"CONTROL_HOLDS, all 5 candidates"** — none of DYN-ATR-CAT/DYN-STRUCT-CAT/DYN-TP-ATR/DYN-TRAIL-ATR/DYN-ALL cleared the auto-ratify bar on the 191-trade historical population.
- Graveyard addition (quoted): *"DYN-TP-ATR-any-k-near-1.0 ... convergently bad on BOTH populations"*; *"DYN-ALL-bundling ... underperforms every one of its own component axes"*.
- Explicitly out of scope both times (quoted): *"Every candidate below inherits CONTROL's profit_lock_arm_scope='post_tp1' unchanged ... Not touched. Verified by construction."* **Neither dynamic-exits study ever tested arm-scope — disjoint from this session's question, not a repeat.**

### `profit_lock_sweep.json` (2026-06-17, predates STOP-B/structure stops)
- Every profit-lock variant tested — including the mildest, `trail tighter: thr=0.05 trail=0.15` (the SAME trail width the current live shape now uses) — **lost money on BOTH IS and OOS vs the no-lock baseline, on BOTH accounts.** SAFE: trail-0.15 IS delta **-$1,136.79**, OOS delta **-$4,062.04**. AGG: IS delta **-$6,040.29**, OOS delta **-$1,165.13**. Gate label `L155` (graveyard lesson). **This is a negative prior against profit-lock generally**, though it predates STOP-B (2026-07-09 structure stops) and used a different (pre-STOP-B) exit shape entirely — disclosed as a real prior, not dismissed.

### `regime-chandelier-sweep.md` (2026-06-19, BEARISH_REJECTION only)
- Verdict (quoted): **"the regime-conditional / underlying-move chandelier is the WRONG direction here — a TIGHTER fixed trail wins."** `fixed_premium_15` (15% trail vs v15's 20%) was the clean promote-candidate on both strikes (ATM Δ+$1,358.8, ITM2 Δ+$1,175.6, sign-flip). **This is a DIFFERENT axis (trail WIDTH once armed) from H4 (arm TIMING/scope)** — already adopted: `canonical_shape()` confirms the live shape's `trail_pct=0.15`, i.e. the regime-chandelier-sweep's own winning width is already the value this session's control AND treatment both use. Caveats disclosed there (anchor_fills=1, DSR weak, no OOS/WF split) still apply and are inherited unresolved.
- Net read: no prior study has ever tested the arm-SCOPE axis (pre-TP1 vs post-TP1) on the current, structure-stop-era exit shape. This session is the first.

## 2. Method

Replayed all **n=394** scored round trips in `analysis/pain-ledger/mae-mfe.json` through the **production** `automation/state/fleet/exit_manager.py#plan_exit_actions` (read-only import, never re-implemented), via `backtest/lib/exit_manager_walk.walk_exit_manager` reached through `setup/scripts/pdt_blocked_counterfactual.py`'s already-tested `_price_via_walker("exit_manager", ...)` adapter and `canonical_shape(date)` date-keyed exit-shape resolver (byte-identical resolution logic reused, not rewritten). CONTROL = `canonical_shape(date)` unchanged (`profit_lock_arm_scope='post_tp1'`, live default). TREATMENT = same shape, `profit_lock_arm_scope='full'`.

- **Joined** mae-mfe (mfe_pct, entry/realized $) to `analysis/trades-enriched.jsonl` (vix, exit_reason, trigger_level, ret_pct_of_premium) by (date, arm, symbol) + nearest entry-timestamp — **394/394 matched cleanly** (no unmatched rows).
- **Bars:** 1-minute cache-only read of `backtest/data/highres/` first (372/394 native coverage; 14 files with an alternate raw-UTC schema were normalized after being caught as a bug — see Deviations), falling back to the 5-minute `backtest/data/options/` cache (`option_pricing_real.load_contract_bars`, also cache-only, returns `None` on miss). **0/394 trades skipped** — full coverage.
- **No network calls** — both bar loaders are cache-only; the 1-min loader deliberately does NOT call `_option_bars_1min_cache.fetch_1min_cached` (which has a live-REST fallback forbidden by this task's hard constraints).
- **No look-ahead:** the walker ticks bar-by-bar strictly forward from the entry bar using only the trade's own recorded entry premium/qty/side and that date's canonical exit shape — the same convention every existing consumer of this harness already uses (C6).

## 3. Harness fidelity this run (governs which dollars are trustworthy)

Sign agreement (control-walk P&L sign vs actual broker `realized_pnl` sign), this run:

| Arm | n | sign_agreement | Dollar figures trusted? |
|---|--:|--:|---|
| **safe-2** | 88 | **92.05%** | **YES — only arm above the 85% bar** |
| bold-2 | 42 | 92.86% | NO (per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md's per-arm magnitude-fidelity table, aggregate_ratio 6.44 — this session's sign check alone does not clear that bar) |
| safe-3 | 63 | 85.71% | NO (that same table shows safe-3's replay **sign-flips net**: actual +$750 vs replay -$93) |
| risky-3 | 94 | 77.66% | NO |
| risky-1 | 83 | 74.70% | NO |
| safe-1 | 24 | 91.67% | NO (not in the go-live `ACTIVE_ARMS`/gate-scored set; no independent magnitude anchor exists for it) |
| **Pooled, all arms** | 394 | 84.01% | **NO — do not read the pooled dollar total** |

This reproduces, independently, `analysis/harness-fidelity/WALKER-MAGNITUDE-2026-09-03.md`'s and `analysis/deep-research/WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md`'s finding that **only safe-2 individually clears the walker's magnitude-fidelity bar**; every other arm's replay diverges from broker truth by more than the fidelity criterion allows, in both directions. Per this task's hard instruction, **only safe-2's dollars are reported as trustworthy below; every other arm is sign-only** (direction of the effect, not its size).

A concrete example of why: on 2026-08-04, three risky-1/risky-3 rows near-zero MFE (0.0–0.08) show CONTROL walk P&L of **+$814 to +$2,880** against **actual realized losses of -$40 to -$144** — a severe control-vs-actual divergence unrelated to the treatment being tested, confirming these arms' replay is not fit to trust for magnitude on this population.

## 4. Frequency — losers with MFE ≥ threshold that ended at the catastrophe cap

"Ended at cap" defined as `exit_reason=='premium_stop' AND ret_pct_of_premium<=-40%` (disclosed heuristic — `trades-enriched.jsonl`'s own `_meta` block flags 65/276 `premium_stop`-labeled rows as mislabeled per a known upstream stage-label bug; the raw label's median ret_pct is only -17.08%, so the label alone is not proof of a real catastrophe hit. The -40%..-60% band contains 34/44 `premium_stop` rows vs only 7 `structure_stop` rows — used as the cleaner proxy).

| MFE threshold | n losers ≥ threshold | n ended at cap | % of that bucket ending at cap | % of ALL 279 losers |
|---|--:|--:|--:|--:|
| ≥10% | 127 | 27 | 21.3% | 45.5% |
| ≥15% | 107 | 27 | 25.2% | 38.4% |
| ≥20% | 87 | 27 | 31.0% | 31.2% |

Read: the SAME 27 trades sit in every bucket (all 27 cap-hits had MFE ≥20%) — a fixed, small, high-conviction "orphan band" core, consistent with the 2026-08-06 prereg's own n=10 (that was engine-attribution-only, entry≥$0.20, one date-window snapshot; this is the full 44-day, all-arm population). **45.5% of all losing round trips in this book had a real favorable excursion (≥10% MFE) before ending at the cap** — the orphan band is not a rare edge case, it is nearly half of the loss population.

## 5. Dollar effect — safe-2 (TRUSTED)

| | Total P&L | WR | PF | Gross profit | Gross loss |
|---|--:|--:|--:|--:|--:|
| CONTROL (live, post_tp1) | -$1,688.41 | 29.5% | 0.73 | $4,481.69 | $6,170.10 |
| TREATMENT (full) | +$890.00 | 36.4% | **1.40** | $3,134.69 | $2,244.69 |
| **Δ (full − control)** | **+$2,578.41** | +6.8pp | +0.67 | | |
| Actual broker truth (same 88 rows) | -$96.00 (span P&L, not comparable 1:1 to walker totals — different fill-price convention) | 25.0% | 0.92 | $3,961.00 | $4,296.99 |

Bootstrap 95% CI on per-trade Δ (n=88, 5,000 resamples): **mean $29.30/trade, CI [$0.59, $55.86]**. The interval excludes zero but its lower bound sits at $0.59 — a real but thin, barely-significant effect on the pooled 8-week window.

**Give-back accounting:** 34/88 trades improved under `full` (mean net effect positive), 8/88 got worse, 46/88 unchanged (both scopes agreed post-TP1 or neither ever armed). `g3_ex_best`: removing the single largest positive-delta trade (2026-08-05 P772, +$431.25) leaves **+$2,147.16 — still positive**, so the aggregate result is not a single-trade artifact.

## 6. Sub-window / recency stability (safe-2, trusted)

| Window | n | Δ (full − control) |
|---|--:|--:|
| H1 (2026-07-02 .. 2026-08-04) | 44 | +$1,659.66 |
| H2 (2026-08-05 .. 2026-09-02) | 44 | +$918.75 |
| Q1 (07-02..07-17) | 22 | +$527.01 |
| Q2 (07-17..08-04) | 22 | +$1,132.65 |
| Q3 (08-05..08-17) | 22 | +$1,246.20 |
| **Q4 (08-18..09-02, MOST RECENT)** | 22 | **-$327.45** |

**Not recency-stable.** The effect is monotonically front-loaded and the most recent 3-week quarter — which covers this week's -$1,322 book after the 08-27/28 peak the task brief names — is net NEGATIVE. Per this project's own standing doctrine (recency > aggregate, memory note 2026-07-31), a positive-but-aging aggregate with a negative most-recent quarter is not a ship signal on its own.

## 7. Would this have blocked/hurt the big winning days? — YES, on 3 of 4

Named anchor days (08-06, 08-13, 08-27, 08-28), safe-2 rows (trusted):

| Date | Symbol | Actual | Control | Full | Δ | MFE | Control stage → Full stage |
|---|---|--:|--:|--:|--:|--:|---|
| 08-06 | SPY260806P00770000 | +$375 | +$276.00 | **$0.00** | **-$276.00** | 118.8% | time_stop → profit_lock_floor |
| 08-06 | SPY260806C00769000 | -$36 | -$162.00 | -$162.00 | $0 | 0.9% | premium_stop → premium_stop |
| 08-13 | SPY260813C00777000 (x2 legs) | +$332/+$181 | +$9.00/+$188.40 | unchanged | $0/$0 | 162%/127% | structure_stop / tp1+trail (both unchanged) |
| 08-13 | SPY260813P00776000 | -$69 | -$94.50 | -$94.50 | $0 | 0.0% | premium_stop → premium_stop |
| 08-27 | SPY260827C00768000 | +$138 | +$438.50 | **$120.15** | **-$318.35** | 57.6% | tp1+trail → profit_lock_floor |
| 08-27 | SPY260827C00771000 | +$184 | +$193.40 | +$193.40 | $0 | 108.5% | tp1+trail → tp1+trail (unchanged) |
| 08-28 | SPY260828C00771000 | +$527 | +$550.55 | **$0.00** | **-$550.55** | 156.3% | tp1+trail → profit_lock_floor |
| 08-28 | SPY260828P00770000 | -$270 | -$264.00 | $0.00 | **+$264.00** | 22.2% | premium_stop → profit_lock_floor |

**safe-2 total on the 4 named days: -$880.90.** Two of the book's biggest single-trade winners (08-06 P770, control-replay $276→$0; 08-28 C771, control-replay $550.55→$0) are **cut to exactly zero** under `full` — the pre-TP1 trail arms on an early favorable tick and gets stopped back out at breakeven before the trade's real move develops, exactly the failure mode the frozen prereg warned about. Only one row (08-28 P770, a loser) benefits. Across ALL arms (sign-only), the same 4 days: **17 rows hurt, 4 helped, 21 unchanged, net -$6,923 pooled (untrusted magnitude, but the 17-vs-4 hurt/help ratio is a believable directional signal independent of dollar fidelity).**

**08-04 bonus check** (the literal trade the 2026-08-06 prereg named as the highest-risk anchor, "the 08-04 C769 runner +223% MFE"): safe-2's SPY260804C00769000 row shows **MFE 126.9%, Δ=$0 — unchanged**, because TP1 already fired before the trail could arm early (once TP1 fills, `profit_lock_armed` is set unconditionally regardless of scope — see exit_manager.py's own comment on this). **The literal named anchor trade is NOT harmed**; the newly-discovered harm is on three OTHER big-winner days this prereg never checked.

## 8. Per-regime (VIX), safe-2 only — trusted

| Regime | n | Δ total | Bootstrap mean [95% CI] |
|---|--:|--:|---|
| VIX<15 | 16 | +$206.95 | $12.93 [-$80.73, $87.19] — CI includes 0 |
| VIX 15–17 | 51 | +$1,327.46 | $26.03 [-$8.84, $60.37] — CI includes 0 |
| VIX>17 | 21 | +$1,044.00 | $49.71 [$1.58, $99.82] — CI excludes 0 |

Only the VIX>17 (elevated-vol) bucket individually clears a CI excluding zero; the calm and mid regimes do not — the aggregate safe-2 significance (§5) is carried disproportionately by higher-vol days. **VIX regime data was only populated for safe-2/bold-2 in `trades-enriched.jsonl`; fleet arms (risky-1/3, safe-1/3) carry no VIX field (264/394 rows fall in an "unknown" bucket) — a real, disclosed data gap, not computed here.**

## 9. Concentration

- **All-arm pool (untrusted):** top-3 |Δ| trades = 12.4% of total absolute delta — NOT a single-trade artifact, but the #1 and #2 rows are both 08-04 risky-3 rows already flagged as walker-unreliable (§3).
- **safe-2 (trusted):** top-3 |Δ| trades = 19.1% of total absolute delta: 08-28 C771 (-$550.55), 08-05 P772 (+$431.25), 08-27 C768 (-$318.35) — two of the three top movers are the anchor-day harms from §7.

## 10. The named 2026-09-02 770C example trade

**Could not be located.** No `SPY*C00770000` fill appears in `automation/state/fills-ledger.jsonl` or `automation/state/core-decisions.jsonl` for 2026-09-02 (that session's traded call strikes were 765–768). `mae-mfe.json` was generated 2026-09-02T16:26:57 ET and may predate this specific trade, or it may be a still-open/2026-09-03 live position — which this READ-ONLY, no-broker-call session cannot verify. **UNVERIFIED, disclosed rather than fabricated or guessed at.**

## 11. Conclusion

The orphan-band mechanism is real and large (45.5% of all losers had ≥10% MFE before capping) and `profit_lock_arm_scope='full'` measurably rescues a chunk of it on the one arm this session can trust (WR +6.8pp, PF 0.73→1.40, aggregate Δ +$2,578 over 88 trades, ex-best-trade still positive). But the SAME trusted evidence shows the fix is **not free**: it is not stable in the most recent 3 weeks (Q4 negative), and it **truncates 3 of the 4 named big winning days to a combined -$880.90**, including two trades cut to exactly $0. This is precisely the risk the frozen 2026-08-06 prereg identified by name and never measured — now measured, and confirmed live. Five of six arms' dollar figures cannot be trusted at all this session (walker magnitude-fidelity fails per-arm for bold-2/risky-1/risky-3/safe-3, sign-flips for safe-3) and VIX-regime evidence for fleet arms does not exist in the current data. **Recommendation: do not ship `profit_lock_arm_scope='full'` as tested.** A narrower candidate (e.g., a higher arm threshold than +5%, or a ladder that only activates after some minimum time-in-trade / minimum favorable excursion rather than the first +5% tick) is a plausible next step but must be its own fresh pre-registration against data not yet seen by this run, per this codebase's own no-repick-after-seeing-results discipline (the 394-trade population here is now SEEN data for the +5%/15%-trail cell).

## Deviations from a clean run (disclosed)

- 14/394 1-minute cache files for 2026-08-05 carried an undocumented alternate schema (`timestamp`/UTC-ISO/`trade_count`/`vwap` instead of `timestamp_et`) — the same anomaly `WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` flagged for that date. Found, diagnosed (raw UTC, verified 13:30Z = 09:30 ET open), and normalized in the loader rather than silently skipped or mis-parsed as already-ET.
- `pdt_blocked_counterfactual.py`'s `spy_by_day()` throws a pandas `FutureWarning` on mixed-offset timestamp parsing — pre-existing in that module, not touched (read-only import), does not affect correctness of the values used here (cosmetic warning only).
- Fleet arms' `ribbon_tick_df` (used for `ribbon_flip` exits) only reconstructs for safe-2/bold-2 (the only arms `ARM2ACCOUNT` maps to a core `account`); fleet arms (risky-1/3, safe-1/3) replay without a ribbon-flip lane, a pre-existing limitation of the reused harness, not newly introduced.
