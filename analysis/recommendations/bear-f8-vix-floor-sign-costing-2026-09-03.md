# BEAR-F8-VIX-FLOOR-COSTING-REPLAY -- sign-only costing (pre-registered)

**Filed:** 2026-09-03 (Sonnet, per Fable's SCOPE RAISED note on `BEAR-F8-VIX-FLOOR-COSTING-REPLAY`,
`automation/overnight/queue.md` line 2595). **Status: SHAPE-MENU INPUT, NOT A SHIP PROPOSAL.**
This is a 10-30 brainstorm input on whether blocker 8 (the bear-side VIX floor: needs
VIX > 17.30 AND rising, `backtest/lib/filters.py`) is costing edge or earning its keep. It does
NOT price dollars (no option pricing, no `exit_manager_walk`/walker -- both are blocked pending
`WALKER-MARKET-STAGE-FILL-ROOT-FIX` per the original item's `depends:` line) and it does NOT
recommend any change to `filters.py`, `params.json`, or any live gate. **Sign only.**

## Why sign-only, not dollars

The original item (`BEAR-F8-VIX-FLOOR-COSTING-REPLAY`, filed 01:48 ET from the sole-blocker
miner's first live run) asked for `postfix_gate_costing.py`'s full dollar replay, explicitly
gated `depends:WALKER-MARKET-STAGE-FILL-ROOT-FIX` because that replay prices exits with the
walker, and the walker's magnitude fidelity is still under repair (see
`WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK`, filed same night). Fable's SCOPE RAISED note
(03:57 ET) authorized a walker-free interim read: does SPY itself move further in the refused
population's favor than in the entered population's favor, using only spot price -- no premium,
no Greeks, no walker. That is what this report answers.

## Frozen rule (written before any number below was computed)

**Population R (refused).** Every bear HOLD row in `automation/state/core-decisions.jsonl`
between 2026-08-05 and 2026-09-01 inclusive (the same 20-trading-day rolling window the
sole-blocker miner used, `automation/state/gate-registry-status.json#sole_blocker_miner`,
`rolling_window="2026-08-05..2026-09-01"`) where `armed is True` and `bear_blockers == [8]`
exactly (the C15 sole-blocker convention -- multi-blocker rows are cascade cohorts and don't
belong to filter 8 alone). Rows from BOTH accounts (`safe`, `bold`) are pooled before
clustering, because the two accounts fire the same underlying market signal within seconds of
each other (verified: 464 raw safe ticks + 462 raw bold ticks cluster to the SAME 53 episodes
whether clustered per-account or pooled -- the miner's "106 events" is 53+53 double-counted
across accounts, not 106 distinct market moments). Contiguous ticks (gap <= 15 minutes,
`EVENT_CLUSTER_GAP_MINUTES` convention used throughout `postfix_gate_costing.py` /
`gate_expiry_check.py`) fold into one episode; the episode's entry timestamp/price/VIX are the
FIRST tick's own `ts_et` / `spy` / `vix` fields from that row (an exact spot tick, not a bar
close).

**Population E (entered).** Every actual bear (put) entry in the SAME 20-session window from
`analysis/trades-enriched.jsonl`, restricted to `right == "P"`, `attribution == "engine"`,
`unbalanced == False`, and `arm` in `{safe-2, bold-2}` (the two arms core-decisions.jsonl's
`safe`/`bold` accounts map to -- fleet arms `risky-1/risky-3/safe-1/safe-3` excluded so both
populations are read off the identical account pair). Each trade's entry price/VIX/time are
NOT read from `trades-enriched.jsonl` (which carries option premiums, not SPY spot) -- they are
joined to the matching `core-decisions.jsonl` row with the same account and a `verdict`
starting `ENTER_BEAR` at or within 120 seconds before the trade's `entry_ts_et` (closest match
kept). A trade with no match within tolerance is dropped and disclosed as UNVERIFIED-excluded.

**Walk parameters** (median hold / MFE / MAE) are estimated once, from the FULL-HISTORY set of
core-arm (`safe-2`/`bold-2`) engine bear trips (`right=="P"`, not just the 20-session window --
wider n for a more stable median), using the same core-decisions ENTER_BEAR join for entry
price. For each trip: hold_min from `trades-enriched.jsonl` directly; MFE (points) = entry
price minus the lowest SPY low reached in `[entry_ts, entry_ts + hold_min]`; MAE (points) =
highest SPY high reached in that window minus entry price (both walked on **SPY 5-minute bars**
-- `backtest/data/spy_5m_2026-05-19_2026-09-02.csv` is the only granularity available in
`backtest/data/`; no 1-minute SPY file exists in this repo. **Disclosed per the task's own
fallback instruction** -- every "walk forward" step below inherits this 5-minute resolution,
which cannot resolve intrabar (sub-5-minute) sequencing.). median_hold / median_MFE / median_MAE
across that set are the ONLY three numbers carried into the walk-forward test below -- neither
population's own individual hold/MFE/MAE is used for its own outcome call, so R and E are
walked under an identical yardstick.

**Walk-forward outcome rule**, applied per R-episode and per E-trade using the fixed
median_hold/median_MFE/median_MAE from above (never the entry's own trade stats):
- Window = `[entry_ts, entry_ts + median_hold]` on SPY 5-minute bars, starting from the bar
  containing/at-or-before `entry_ts`.
- FAVOURABLE_price = entry_price - median_MFE (SPY must trade down to or below this to count
  favourable -- puts profit when SPY falls).
- ADVERSE_price = entry_price + median_MAE (SPY must trade up to or above this to count
  adverse).
- Bars are walked in time order. A bar whose `low <= FAVOURABLE_price` AND whose
  `high < ADVERSE_price` (adverse not touched) -> **FAVOURABLE**, stop. A bar whose
  `high >= ADVERSE_price` AND whose `low > FAVOURABLE_price` -> **ADVERSE**, stop. A bar that
  touches BOTH thresholds (5-minute bars cannot show which happened first intrabar) is resolved
  **ADVERSE by pre-registered tie-break** -- conservative against the hypothesis that refusing
  entries costs edge, so the tie-break cannot manufacture a positive-sounding result for
  Population R. If neither threshold is touched by the end of the window -> **FLAT**.
- Report per population: n, FAVOURABLE / ADVERSE / FLAT %, and a session-clustered bootstrap CI
  (resample TRADING DAYS with replacement, not individual episodes/trades -- `numpy` default_rng
  **seed=1337**, **n=2000** resamples, 2.5th/97.5th percentile) on the FAVOURABLE rate.
- Difference R - E on the FAVOURABLE rate, with a matching session-clustered bootstrap CI (same
  2000 resamples, sessions drawn once per iteration from the union of the 20-session window,
  applied to both populations' episodes/trades that fall in the resampled sessions that
  iteration).

**VIX stratification of R**: split R's 53 episodes by the first tick's own `vix` field into
`VIX < 15.5` and `15.5 <= VIX <= 17.3` (the coded floor is 17.30; nothing in the window sits
above it by construction, since that's exactly what "sole-blocked by filter 8" means). Report n
and FAVOURABLE/ADVERSE/FLAT % per bin -- no CI (bin n's are small; point estimates only,
disclosed as such).

## Verdict vocabulary (frozen before running)

- **F8_COSTS_EDGE** -- R's FAVOURABLE-rate bootstrap CI-lower bound is strictly greater than
  E's point-estimate FAVOURABLE rate. (Refused setups would sign-only have out-performed what
  the engine actually captured -- the floor is plausibly leaving money on the table.)
- **F8_EARNS_ITS_KEEP** -- R's FAVOURABLE-rate bootstrap CI-upper bound is strictly less than
  E's point-estimate FAVOURABLE rate. (Refused setups would sign-only have under-performed what
  the engine actually captured -- the floor is plausibly doing its job.)
- **INCONCLUSIVE** -- neither condition holds (CIs overlap E's point estimate, or n is too thin
  to resolve either direction).

No other verdict label is valid for this report. Whatever the result, this feeds the 10-30
shape menu only -- it does not authorize, and this report will not recommend, any change to
`filters.py` / `params.json` / any live gate. The full-dollar version stays blocked on
`WALKER-MARKET-STAGE-FILL-ROOT-FIX` per the original item.

---

## Results

**Verified this session:** `backtest/.venv/Scripts/python.exe backtest/tools/bear_f8_sign_costing.py`
ran clean, wrote `bear-f8-vix-floor-sign-costing-2026-09-03.json` alongside this file.
`backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bear_f8_sign_costing.py -q` ->
**10 passed**.

### Walk parameters

From n=46 core-arm (`safe-2`/`bold-2`) engine bear trips (of 70 full-history candidates; 24
dropped for no ENTER_BEAR join within 120s -- see caveat below):

| median hold | median MFE (favourable, pts) | median MAE (adverse, pts) |
|---|---|---|
| 24.10 min | 0.620 | 0.420 |

**UNVERIFIED / caveat:** the 24 dropped trips have a median hold of **1.0 min** vs **24.1 min**
for the 46 that joined -- the join-drop is NOT random, it skews hard toward very short holds
(median hold 1.0 vs 24.1, n=24 vs n=46). `median_hold_min` above is very likely biased UPWARD
relative to the true population (these short-hold trips have no matching `ENTER_BEAR` tick in
`core-decisions.jsonl` within 120s -- looked at one case, 2026-07-06 13:36-13:41 safe-2: five
sub-1-minute round trips with core-decisions showing continuous `HOLD`/no side the whole time,
an older-window data-provenance gap this report does not attempt to root-cause). A shorter true
median hold would tighten both the FAVOURABLE and ADVERSE price thresholds and could shift the
walked outcomes in either direction -- this is a disclosed limitation of the sign-only method,
not a re-run-until-it-looks-better attempt.

### Per-population table

| Population | n | FAVOURABLE % | ADVERSE % | FLAT % | FAVOURABLE rate (point) | 95% CI (session-clustered bootstrap, seed 1337, n=2000) |
|---|---|---|---|---|---|---|
| **R (refused, sole blocker-8)** | 53 | 26.4% | 58.5% | 15.1% | 0.264 | [0.167, 0.364] |
| **E (entered, actual bear fills, same window)** | 31 (of 39 candidates; 8 dropped, no ENTER_BEAR join within 120s) | 41.9% | 38.7% | 19.4% | 0.419 | [0.188, 0.656] |

**R - E difference on FAVOURABLE rate:** point = **-0.155**, 95% CI = **[-0.436, +0.090]**
(session-clustered, same 2000 resamples). CI spans zero.

### VIX stratification of R (n=53, point estimates only, no CI)

| VIX bin | n | FAVOURABLE % | ADVERSE % | FLAT % |
|---|---|---|---|---|
| VIX < 15.5 | 28 | 25.0% | 60.7% | 14.3% |
| 15.5 <= VIX <= 17.3 | 25 | 28.0% | 56.0% | 16.0% |

No meaningful gradient between the two VIX bins inside the refused population -- both sit close
to R's overall 26.4%.

### Verdict

**F8_EARNS_ITS_KEEP** -- E's point-estimate FAVOURABLE rate (0.419) sits strictly ABOVE R's
bootstrap CI-upper bound (0.364). Sign-only, the entries the engine actually took moved further
in the profitable direction (net of the identical median-hold/MFE/MAE yardstick) than the
episodes blocker 8 refused. This is directional agreement with the real-fills finding already
in `CLAUDE.md` C31/L168/L203 context (bear side RED_CONCENTRATED, n=31, -$1.77/tr) -- a floor
that keeps the engine OUT of the weaker-looking calm-VIX chop is, by this sign-only read, not
obviously costing edge.

**This does not settle the question.** R's CI-lower (0.167) is well below E's point estimate
too, so the gap is not enormous relative to the CI width, n is modest (53 vs 31), the join-drop
hold-time bias above is unresolved, and this is still a SPY-spot proxy for what would actually
be an option P&L -- theta/spread/slippage on a calm-VIX, thin-premium day (exactly what the
playbook's own VIX<15 prose warns about) could easily flip a spot-FAVOURABLE outcome into a
dollar-loss, which is precisely why the full-dollar replay stays blocked on
`WALKER-MARKET-STAGE-FILL-ROOT-FIX` rather than being declared answered here.

### UNVERIFIED items (explicit)

1. Walk-parameter median_hold likely biased upward (join-drop skews toward short holds, see
   above) -- not corrected, disclosed only.
2. 8 of 39 (21%) Population-E candidate trades and 24 of 70 (34%) walk-parameter candidate
   trades dropped for no `ENTER_BEAR` join within 120 seconds -- root cause not investigated
   (older-window data-provenance gap, out of this report's scope).
3. 5-minute SPY bar granularity (no 1-minute SPY file exists in `backtest/data/`) cannot resolve
   intrabar sequencing; same-bar double-touches are resolved ADVERSE by the pre-registered
   conservative tie-break, not by evidence of true intrabar order.
4. Sign-only by design -- no theta, spread, slippage, or fill-quality effects are modeled. This
   is NOT the dollar answer the original item asked for.

### Queue closure text

`BEAR-F8-VIX-FLOOR-COSTING-REPLAY` SCOPE RAISED sub-task: **DONE** (sign-only interim read).
Verdict **F8_EARNS_ITS_KEEP** (E favourable-rate point 0.419 > R favourable-rate CI-upper
0.364; R-E CI [-0.436, +0.090] spans zero) -- directionally consistent with "the VIX floor is
not obviously costing edge on calm-VIX bear chop," but NOT a ship signal: CIs are wide (n=53/31),
the walk-parameter hold-time estimate is disclosed-biased, and dollars (theta/spread/slippage)
are still unmodeled. The original item's full-dollar ask remains `depends:
WALKER-MARKET-STAGE-FILL-ROOT-FIX` / `WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK` and is
UNBLOCKED only for the walker-free interim read, not for the dollar replay. Feeds the 10-30
shape menu as one data point, no gate/filter/param change made or proposed.
