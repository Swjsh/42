# FAVORABLE-EXTREME-ENTRY study -- FAVORABLE-EXTREME-ENTRY-2026-07-17

Generated: 2026-07-17T17:21:53.519840. Source: `backtest/tools/favorable_extreme_entry_study.py`. Pre-reg: `analysis/recommendations/prereg-favorable-extreme-entry-2026-07-17.json`.

## The exemplar

2026-07-17 14:03:03 ET bollinger_squeeze PUT, SPY745P @ $1.01, entry bar 14:00-14:05 O=744.60 H=745.10 L=744.38 C=744.63 (upper wick $0.47) -- fill landed near the bar's HIGH right before SPY rolled to a 743.23 close, +$105. The fill was INCIDENTAL (1-min heartbeat tick sampled mid-spike), not deliberately targeted -- that's the question this study interrogates.

## PART A -- real-fills entry-location characterization (correlational, not gated)

### PRIMARY (decision-log live-tick spot) -- n=30

| bucket | n | mean $pnl | win rate | total $pnl |
|---|--:|--:|--:|--:|
| favorable_extreme | 5 | $-29.0 | 0.2 | $-145.0 |
| neutral | 10 | $7.3 | 0.4 | $73.0 |
| adverse_extreme | 15 | $-17.87 | 0.1333 | $-268.0 |

Wick-caught (fill in a house-standard wick zone AGAINST signal direction, favorability>=0.70): n=0, mean $None, win_rate=None -- vs not-wick-caught: n=30, mean $-11.33, win_rate=0.2333.

### SECONDARY (bar-close proxy, lower confidence) -- n=119

| bucket | n | mean $pnl | win rate | total $pnl |
|---|--:|--:|--:|--:|
| favorable_extreme | 37 | $12.27 | 0.0811 | $454.0 |
| neutral | 24 | $48.12 | 0.2083 | $1155.0 |
| adverse_extreme | 58 | $-8.98 | 0.069 | $-521.0 |

Wick-caught (fill in a house-standard wick zone AGAINST signal direction, favorability>=0.70): n=0, mean $None, win_rate=None -- vs not-wick-caught: n=119, mean $9.14, win_rate=0.1008.

**Correlational, on incidental fills -- this is a precondition check, not a causal claim.**

## PART B -- pre-registered A/B (entry_manager-driven resting entry vs immediate marketable)

### SAFE

Tier **ATM** (so=0), equity=$1724.59, qty=3, time_stop=15:40:00, signal universe n=6057, confirmation-triggered n=2619.

Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean=0.0, oos_delta_mean=0.0, wf_delta=None, ladder=FAIL.

| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |
|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|
| delta0.05|cancel|cancel_none | 2619 | 1570/1049 | $-10.8821 | $-19.2627 | None | FAIL | 538/$53.66 | 1616/$10.27 | False | False | False |
| delta0.05|cancel|cancel_0.15 | 2619 | 1570/1049 | $20.5706 | $27.6814 | 1.3457 | PASS | 404/$28.02 | 412/$15.56 | False | False | False |
| delta0.05|cancel|cancel_0.30 | 2619 | 1570/1049 | $18.0586 | $25.0866 | 1.3892 | PASS | 469/$40.34 | 624/$18.93 | False | False | False |
| delta0.05|convert|cancel_none | 2619 | 1570/1049 | $-10.3396 | $-29.9718 | None | FAIL | 944/$-51.96 | 1675/$0.82 | False | False | False |
| delta0.05|convert|cancel_0.15 | 2619 | 1570/1049 | $20.8429 | $16.9724 | 0.8143 | PASS | 808/$-82.68 | 471/$-18.69 | False | False | False |
| delta0.05|convert|cancel_0.30 | 2619 | 1570/1049 | $18.3309 | $14.3776 | 0.7843 | PASS | 873/$-67.82 | 683/$-4.98 | False | False | False |
| delta0.1|cancel|cancel_none | 2619 | 1570/1049 | $0.7933 | $-17.6218 | -22.2138 | FAIL | 393/$76.27 | 1566/$32.6 | False | False | False |
| delta0.1|cancel|cancel_0.15 | 2619 | 1570/1049 | $23.1565 | $21.0486 | 0.909 | PASS | 272/$53.74 | 310/$38.83 | False | False | False |
| delta0.1|cancel|cancel_0.30 | 2619 | 1570/1049 | $22.7613 | $18.0372 | 0.7924 | PASS | 323/$62.04 | 511/$42.04 | False | False | False |
| delta0.1|convert|cancel_none | 2619 | 1570/1049 | $-1.8972 | $-20.5274 | None | FAIL | 942/$-61.69 | 1676/$20.03 | False | False | False |
| delta0.1|convert|cancel_0.15 | 2619 | 1570/1049 | $20.9317 | $17.7335 | 0.8472 | PASS | 797/$-94.21 | 407/$-10.77 | False | False | False |
| delta0.1|convert|cancel_0.30 | 2619 | 1570/1049 | $19.8693 | $15.0202 | 0.756 | PASS | 866/$-79.23 | 619/$6.86 | False | False | False |
| delta0.15|cancel|cancel_none | 2619 | 1570/1049 | $6.5426 | $-7.6308 | -1.1663 | FAIL | 287/$92.51 | 1476/$52.66 | False | False | False |
| delta0.15|cancel|cancel_0.15 | 2619 | 1570/1049 | $22.5941 | $21.447 | 0.9492 | PASS | 172/$62.54 | 212/$64.27 | False | False | False |
| delta0.15|cancel|cancel_0.30 | 2619 | 1570/1049 | $22.25 | $20.7388 | 0.9321 | PASS | 217/$73.01 | 382/$63.11 | False | False | False |
| delta0.15|convert|cancel_none | 2619 | 1570/1049 | $4.9369 | $-11.4756 | -2.3245 | FAIL | 953/$-64.05 | 1665/$34.06 | False | False | False |
| delta0.15|convert|cancel_0.15 | 2619 | 1570/1049 | $21.786 | $17.0494 | 0.7826 | PASS | 784/$-104.15 | 340/$-13.57 | False | False | False |
| delta0.15|convert|cancel_0.30 | 2619 | 1570/1049 | $19.9838 | $17.0151 | 0.8514 | PASS | 864/$-86.77 | 538/$8.22 | False | False | False |

**SAFE: NULL RESULT (KILL).** Closest cell: `delta0.05|cancel|cancel_0.15` (3/5 gates, verdict_ladder=PASS, n=2619, IS=$20.5706, OOS=$27.6814) -- fails: ['anchor_no_regression', 'bh_fdr_survivor'].

Adverse-selection (summed across all 18 cells' filled episodes): bounce=10906, slice_through=15183.

### BOLD

Tier **OTM-2** (so=-2), equity=$2153.84, qty=3, time_stop=15:40:00, signal universe n=6057, confirmation-triggered n=2472.

Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean=0.0, oos_delta_mean=0.0, wf_delta=None, ladder=FAIL.

| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |
|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|
| delta0.05|cancel|cancel_none | 2472 | 1491/981 | $-5.2401 | $-20.6678 | None | FAIL | 390/$87.96 | 1563/$26.15 | False | False | False |
| delta0.05|cancel|cancel_0.15 | 2472 | 1491/981 | $39.7106 | $48.1887 | 1.2135 | PASS | 272/$52.82 | 323/$42.03 | False | False | False |
| delta0.05|cancel|cancel_0.30 | 2472 | 1491/981 | $38.3576 | $44.7697 | 1.1672 | PASS | 329/$71.65 | 520/$45.01 | False | False | False |
| delta0.05|convert|cancel_none | 2472 | 1491/981 | $-11.2229 | $-31.0041 | None | FAIL | 815/$-79.94 | 1657/$10.87 | False | False | False |
| delta0.05|convert|cancel_0.15 | 2472 | 1491/981 | $34.6934 | $39.094 | 1.1268 | PASS | 685/$-122.12 | 406/$-18.18 | False | False | False |
| delta0.05|convert|cancel_0.30 | 2472 | 1491/981 | $32.0386 | $34.7462 | 1.0845 | PASS | 752/$-101.08 | 612/$1.41 | False | False | False |
| delta0.1|cancel|cancel_none | 2472 | 1491/981 | $11.5294 | $-3.2922 | -0.2855 | FAIL | 258/$134.0 | 1481/$64.09 | False | False | False |
| delta0.1|cancel|cancel_0.15 | 2472 | 1491/981 | $38.779 | $46.4515 | 1.1979 | PASS | 152/$87.01 | 198/$85.6 | False | False | False |
| delta0.1|cancel|cancel_0.30 | 2472 | 1491/981 | $39.3576 | $44.4332 | 1.129 | PASS | 198/$104.62 | 361/$84.17 | False | False | False |
| delta0.1|convert|cancel_none | 2472 | 1491/981 | $2.8114 | $-13.3504 | -4.7486 | FAIL | 818/$-97.17 | 1654/$42.67 | False | False | False |
| delta0.1|convert|cancel_0.15 | 2472 | 1491/981 | $31.0763 | $36.4411 | 1.1726 | PASS | 672/$-151.94 | 326/$-16.42 | False | False | False |
| delta0.1|convert|cancel_0.30 | 2472 | 1491/981 | $30.3674 | $33.7989 | 1.113 | PASS | 747/$-126.28 | 525/$12.03 | False | False | False |
| delta0.15|cancel|cancel_none | 2472 | 1491/981 | $24.0463 | $15.4188 | 0.6412 | FAIL | 162/$183.32 | 1307/$95.77 | False | False | False |
| delta0.15|cancel|cancel_0.15 | 2472 | 1491/981 | $42.7387 | $49.2144 | 1.1515 | PASS | 81/$125.16 | 99/$128.96 | False | False | False |
| delta0.15|cancel|cancel_0.30 | 2472 | 1491/981 | $43.9441 | $48.5772 | 1.1054 | PASS | 112/$150.39 | 195/$127.89 | False | False | False |
| delta0.15|convert|cancel_none | 2472 | 1491/981 | $9.5108 | $-0.6506 | -0.0684 | FAIL | 834/$-107.02 | 1638/$62.76 | False | False | False |
| delta0.15|convert|cancel_0.15 | 2472 | 1491/981 | $32.0719 | $35.9742 | 1.1217 | PASS | 655/$-169.84 | 274/$-29.8 | False | False | False |
| delta0.15|convert|cancel_0.30 | 2472 | 1491/981 | $30.4817 | $34.7859 | 1.1412 | PASS | 742/$-140.93 | 436/$6.51 | False | False | False |

**BOLD: NULL RESULT (KILL).** Closest cell: `delta0.05|cancel|cancel_0.15` (3/5 gates, verdict_ladder=PASS, n=2472, IS=$39.7106, OOS=$48.1887) -- fails: ['anchor_no_regression', 'bh_fdr_survivor'].

Adverse-selection (summed across all 18 cells' filled episodes): bounce=8674, slice_through=13575.

## Overall verdict

any_ship_ready_overall=False (safe=False, bold=False)

## Synthesis -- the answer to J's question

**Verdict: LOCATION MATTERS, but the signal is "avoid the ADVERSE extreme," NOT "chase the favorable extreme" -- and deliberately targeting the favorable extreme via a resting limit does NOT beat the marketable fill. Take the marketable fill; the 14:03 wick was luck.**

**PART A (does entry location correlate with outcome, on real fills?):** WEAKLY, and not the way the exemplar suggested.
- In BOTH populations the **adverse_extreme bucket is the worst** (primary: -$17.87/tr, 13% win; secondary: -$8.98/tr, 6.9% win) -- filling at the WRONG end of the entry bar (bought the put at the bar low / the call at the bar high) is a real negative signal.
- But the gradient is NOT monotonic: **neutral is the BEST bucket in both** (primary +$7.30/tr; secondary +$48.12/tr), not favorable_extreme (primary -$29/tr on n=5; secondary +$12.27/tr). "More favorable = better" is FALSE; "adverse = worse" is the real, weaker correlation.
- **The exemplar pattern is vanishingly rare: `wick_caught` n=0 in BOTH populations.** No tracked real engine fill landed in a house-standard wick-against-signal zone AND the favorable extreme. The 14:03 fill did not even qualify under the (conservative, placement-tick) proxy -- direct confirmation it was incidental, exactly as the honesty frame anticipated. (Disclosure: the placement-tick proxy understates true fill-moment favorability on fast bars; the true favorable population is larger than n shows -- but even generously, the pattern is rare and the favorable bucket does not lead.)

**PART B (does deliberately targeting the favorable extreme beat marketable entry, net of adverse selection?):** NO -- clean KILL on both accounts, and it fails for the SAME reason PONG did.
- The aggregate looks strong and is a trap: **12/18 cells (Safe) and 12-13/18 (Bold) clear oos_positive + wf>=0.70 + sub_window_stable**, the closest cell posting OOS +$27.68/tr (Safe) / +$48.19/tr (Bold) at WF>1.2 on n=2619/2472. Suspicion scales with how good it looks.
- **0/18 cells clear `anchor_no_regression` on EITHER account, and 0/18 survive BH-FDR.** Identical shape to pong-resting-limit-2026-07-17: a resting order sitting at/near a level on a fast, trending day (J's anchor dates) gets run over, not filled favorably -- the regime dependence the full-window aggregate hides.
- **Adverse selection is real but MILDER than PONG's** (this mechanism rests only AFTER a confirmation trigger fired, so it inherits directional confirmation): raw slice-through share ~58% Safe / ~61% Bold across all filled episodes, vs PONG's 74-81%. Notably, with a cancel-watcher the `cancel`-policy cells show POSITIVE deltas on BOTH bounce AND slice sub-populations (e.g. Bold delta0.15|cancel|cancel_0.15: bounce +$125/tr, slice +$129/tr) -- because a post-trigger "slice-through" often means the trade went our way. But this does not rescue the anchor/BH-FDR failure.

## Build-spec-or-honest-kill

**HONEST KILL.** Per the frozen prereg `decision_rule.kill_criterion` (no cell clears all 5 gates on either account), **NO build spec is authorized** -- no `entry_manager.py` / `j_intent_executor` / `params.json` edit. Current immediate marketable-entry semantics stand unchanged.

This is the "location matters but targeting doesn't" outcome the task explicitly anticipated, sharpened by evidence: the location signal that exists is *negative* (avoid adverse-extreme fills), not the *positive* one the exemplar implied (chase favorable-extreme fills). J's directive "we need that every time it presents itself" is answered honestly: **the engine cannot reliably manufacture the 14:03 wick fill -- deliberately resting for it loses the clean runners and gets run over on the exact high-conviction days that matter, and the favorable-extreme location does not even lead the outcome table when it IS caught.** The marketable fill on a confirmed trigger remains the correct default.

**Named, NOT auto-queued follow-ups** (not authorized by this study):
1. The ONE genuinely actionable positive signal here is the mirror of Part A's finding -- an *adverse-extreme AVOIDANCE* filter (skip/deprioritize an entry whose marketable fill lands at the wrong end of its bar), which is a different, simpler mechanism than resting-limit targeting and was not tested here. Would need its own pre-registered A/B.
2. Re-run Part B restricted to range-bound/low-realized-move days only (the same follow-up PONG named) -- the aggregate is likely unrepresentative of the trending days that break it.
3. Correct Part A's primary population with a full 1-min SPY cache so fill-moment favorability is measured at the fill, not the placement tick (this session verified the proxy understates favorability but did not rebuild every row).

## Disclosures

- PART A is CORRELATIONAL on incidental fills, not causal -- no ratification gate applies to it; it is descriptive evidence for whether part B's deliberate mechanism is worth testing, per the task's own framing.
- PART A primary population requires an order_id join between fills-ledger.jsonl and core-decisions.jsonl; rows with no join (no core-decisions.jsonl PLACED record for that order_id -- e.g. exits, or entries placed via a path this study didn't index) are EXCLUDED, not imputed (C7); this undercounts the true fill population, disclosed as a conservative gap, not a silent one.
- PART A's 'fill-implied SPY spot' is the live-tick value sampled at the DECISION TICK that PLACED the matched order (order_id join), which can precede the broker-confirmed fill by up to ~60s (heartbeat cadence) -- not the exact fill-moment tick (no tick-by-tick spot log exists). VERIFIED DIRECTLY on the exemplar itself this session (Alpaca 1-min SPY bars, feed=sip): at order placement (14:03:03 ET) SPY was ~744.59 (matching the logged decision-tick spot almost exactly), but the actual broker fill landed at 14:03:18.9 -- by then SPY had already climbed into the 744.87-745.09 range per the 14:03-14:04 ET 1-min bar (O=744.87 H=745.09). This means the placement-tick proxy systematically UNDERSTATES true fill-moment favorability on fast-moving bars -- a CONSERVATIVE bias, not a random one: the true favorable_extreme population is likely LARGER than what this study's primary population shows, not smaller, and the exemplar's own favorability score under this proxy (0.28, adverse_extreme bucket) is almost certainly an undercount of where the OPTION actually filled. Building a full 1-min SPY cache to correct every primary-population row was scoped OUT of this study for time (a named, disclosed follow-up, not attempted) -- the exemplar-level spot check stands as the verification that the direction of the bias is understated-favorability, not overstated.
- PART A's secondary/lower-confidence population (journal/trades.csv rows with no ledger match) uses the entry bar's OWN CLOSE as a spot proxy -- NOT a live-tick reading -- and is never blended into the primary population's headline numbers.
- journal/trades.csv is independently confirmed INCOMPLETE this same evening (STATUS.md SAFE-TRADES-CSV-JOURNALING-GAP: missing the 14:03 bollinger_squeeze exemplar itself) -- automation/state/fills-ledger.jsonl is used as the PRIMARY ground truth for part A instead, superseding trades.csv where they disagree.
- PART B: MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this candidate mechanism, which does not exist in production.
- PART B reuses pong_resting_limit_study.py's control_outcome()/build_level_by_day()/replay_exit()/compute_delta_wf()/anchor_no_regression()/make_null_sim_fn() functions VERBATIM (imported, not re-derived) for the signal population, control arm, and exit replay -- methodological continuity with today's sibling study.
- PART B's entry_manager.py state machine is discretized to 1 tick = 1 five-minute OPRA option bar (ask=bar.low), materially SLOWER than a live per-second actuator would run -- disclosed as a named open question for the build spec, not resolved here.
- PART B's CONVERT fill price deliberately does NOT reuse plan_entry_action's own returned ask-based fill_price (which would double-dip the SAME bar.low the fill-check tested against) -- it uses bar.close + DEFAULT_ENTRY_SLIPPAGE instead, a disclosed correction for honesty.
- PART B cohort end=2026-07-08 (latest date with a matching SPY+VIX master on disk this session) -- today's 07-17 exemplar itself is NOT inside the statistical population, remaining purely motivating context.
- PART B qty=3 fixed BOTH accounts (disclosed deviation from each account's own live qty knob, matching pong-resting-limit's own precedent).
- PART B min_entry_premium floor (0.30) applied against the candidate's realized fill price and the control's raw entry premium; a signal below floor is dropped and counted (floor_skip), never imputed (C7).
- PART B exit shape is FIXED (tp50/structure/t30), not swept -- entry mechanism is the axis under test, matching pong-resting-limit's own entry_zone_width precedent for fixing a non-central dimension.
- PART B ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local (6-8-worker-ceiling / OPRA-cache-deadlock lesson).

