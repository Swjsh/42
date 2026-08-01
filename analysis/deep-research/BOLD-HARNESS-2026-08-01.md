# BOLD-SHAPE REPLAY HARNESS — 2026-08-01 (WEEKEND-TWELVE Next-Twelve #8)

**Verdict: harness built, anchored, and its first consumer finding is a LOUD FLAG.** Every
prior fullhist-replay tool in this repo walked Safe's shape. Bold now has its own
(`backtest/tools/bold_fullhist_replay.py`), anchored against 6/7 real bold-2 engine fills,
with `block_elite_bull` wired as an input so pre/post-trial counterfactuals are one call
apart. Its first real consumer — re-running Friday's elite-bull blocked-cohort under Bold's
TRUE shape (qty=5, not the qty=3 that study used for both accounts) — finds that the
evidence armed tonight's trial (`+$867.00`, cited from `safe_sequential_hold_qty3`) was
**never bold-2's own number**, and bold-2's own cohort at its true sizing is a coin-flip
total (`+$7.80`, n=5) propped up by ONE trade, with drop-best strongly negative
(`-$535.00`). The trial's forward kill-criterion (n≥10 fills or 10 sessions, net<0 →
re-block) still stands as the live guard and is doing real work — this finding does not
override it — but J should know the disclosed justification moved.

---

## 1. Why this exists

Every full-history replay tool in this repo (`engine_fullhist_replay.py`,
`elite_bear_level_reject_gate_ab.py`) hand-builds its entry config from
`automation/state/params.json` (Safe). None had a Bold-shaped counterpart. Bold cells in
recent studies were either blind (WS11's core-recency bull supplement never ran Bold) or
Safe-approximated (the elite-bull-requal-2026-07-31.json study's own "bold" cohorts used
qty=3 and qty=10 sizing cells — neither of which is bold-2's real `min_contracts=5`, and its
frozen verdict rule's PRIMARY input was actually SAFE's cohort, not bold's). OP-16's
sim-accuracy gate says: verify the sim matches production before ratification. This harness
is that verification instrument.

## 2. Read first: the source files

| File | Role |
|---|---|
| `backtest/tools/engine_fullhist_replay.py` | Safe's sibling tool — the 386-day/116s walker this harness mirrors. Reused verbatim: `build_ribbon_lookup`, `ribbon_tick_df_for`, `naive_dt`, `match_entries_by_strike_side_time`. |
| `backtest/lib/orchestrator.py#run_backtest` | The ENTRY layer (engine_cli-equivalent score+gate+filter cascade). ~200 kwargs; ~20 are gate/sizing/strike knobs that differ Safe-vs-Bold. |
| `backtest/lib/exit_manager_walk.py#walk_exit_manager` | The EXIT layer — ticks the REAL `exit_manager.plan_exit_actions` core over cached bars. Account-agnostic; takes `exit_shape` as a plain dict. |
| `automation/state/params.json` | Safe's live config. |
| `automation/state/aggressive/params.json` | Bold's live config — read in full 2026-08-01 for this task. |
| `automation/state/fleet/strategies.py#RIBBON_RIDE` | The exit shape BOTH accounts actually ride (see finding #3). |
| `setup/scripts/heartbeat_core.py` | The live engine — read to find the REAL qty formula (line 1835) and the REAL exit-shape registration (line ~1981-1985), both of which diverge from what a naive port of Safe's tool would assume. |
| `crypto/lib/strike_selection.py` | `V15_BOLD_CORE_TIERS` — Bold's live strike ladder (wired 2026-07-18). |
| `backtest/lib/risk_gate.py` | `check_order` — the real MIN_CONTRACTS/RISK_CAP/MAX_PREMIUM_TIER gates, used to derive the correct qty-resolution formula. |

## 3. The three traps (the reason "swap the params file" would have lied)

### 3.1 Sizing — the biggest one

`orchestrator.run_backtest`'s internal `per_trade_risk_cap_pct` scaling
(`orchestrator.py:1917-1932`) is a **no-op in practice**: `backtest/lib/simulator.py`'s
`DEFAULT_QTY = 3` already satisfies that scaling code's own `max(3, ...)` floor, so every
orchestrator-produced `TradeFill.qty` is **3, unconditionally, regardless of account**.
Safe's own `engine_fullhist_replay.py` reuses this `t.qty` as-is — which happens to be
*correct for Safe by luck* (Safe's real `min_contracts` is also 3), not by design.

The REAL live formula (`heartbeat_core.py:1835`):

```python
qty = int(params.get("min_contracts", 3))
afford = rg.max_affordable_qty(equity=equity, premium=mid, params=params)
if afford and qty > afford:
    qty = afford
```

qty = `min_contracts` (Bold=**5**, Safe=3), clamped **down** by affordability, **never
resized up, never resized below the floor** — if even the floor is unaffordable the whole
order is denied (`RISK_CAP`/`MIN_CONTRACTS` deadlock in `risk_gate.check_order`), not
shrunk to fit.

**Confirmed against 7/7 real bold-2 ENGINE-attributed fills** in
`automation/state/fills-ledger.jsonl` (2026-06-26 → 2026-07-28, filtered to
`attribution=="engine"` — J's own manual fills were excluded since this harness models the
engine, not J's discretion): every single one is qty=5. Zero exceptions.

Reusing `t.qty` from `run_backtest` for Bold would have graded every trade at qty=3 instead
of 5 — since exit P&L is (mostly — see §6.3) linear in qty, that is a flat **~40%
understatement of every Bold dollar number**, not a rounding error. `bold_fullhist_replay.py`
ignores `run_backtest`'s qty entirely; `resolve_bold_qty()` re-derives it.

### 3.2 Strike sign convention

`crypto/lib/strike_selection.py`'s `V15_BOLD_CORE_TIERS` (Bold's live strike ladder, wired
2026-07-18) uses the **live-params convention**: positive = ITM, negative = OTM (its own
`OTM-2`/`ITM-2` labels confirm this). `orchestrator.run_backtest`'s `strike_offset` kwargs
use the **inverted simulator convention** (`simulator_real.py:281`, "`strike_offset=-2` ...
ITM-2 for puts"; independently corroborated by several `params.json` docstrings, e.g.
`j_vwap_cont_strike_offset_bold`'s own note "sim -2 = ITM-2").

`bold_fullhist_replay.py#_live_to_sim_strike_offset` negates the tier table's offset before
it reaches `run_backtest`. At bold-2's **current** equity ($1,197.52, live-verified this
session) the resolved tier is ATM (offset 0) — sign-invariant, so this negation is presently
a no-op — **but a future re-run at Bold equity ≥ $2,000 (tier flips to OTM-2, live-offset
-2) would silently invert ITM/OTM without this fix.** Guard-tested
(`test_resolve_bold_strike_offset_matches_v15_bold_core_tiers_negated`) at both the current
ATM tier and the $2K-10K OTM-2 tier specifically so this doesn't regress invisibly once
bold-2's equity grows.

### 3.3 Exit shape is shared, not Bold-specific

`automation/state/aggressive/params.json`'s own top-level exit keys (`premium_stop_pct`
-0.07/-0.05, `tp1_premium_pct` 0.75, `tp1_qty_fraction` 0.667, `runner_max_premium_pct` 5.0)
**read like** Bold's exit shape. They are **vestigial** for the core `ribbon_ride` path once
`GAMMA_CORE_MANAGES_EXITS=1` (confirmed live — `CLAUDE.md`'s conductor doctrine +
`project_p0_g1_manages_exits_guard` memory). `heartbeat_core.py`'s entry path
(`~line 1981-1985`, the `_xov is None` branch — `ribbon_ride`/`RIDE_THE_RIBBON` never has a
`_SETUP_EXEC_OVERRIDES` entry) registers **every** core `ribbon_ride` fill, **both
accounts**, under `strategies.by_name("ribbon_ride").exit.to_dict()` — the exact same dict
object Safe's tool uses. `GAMMA_CORE_MANAGES_EXITS` is a single process-wide env flag read
once at import, not indexed by account — both accounts run in the same process, so this
identity is **structural**, not coincidental.

`bold_fullhist_replay.py` uses the identical shared shape
(`profit_lock_mode="trailing"`, `stop_mode="structure"`, `runner_target_pct=99.0`,
`trail_pct=0.15`). A "Bold-shaped" -7%/+75%/5x exit would have modeled an inert safety
bracket that gets superseded the same tick it's placed, never what `exit_manager` actually
rides.

## 4. Full knob-by-knob translation table

Source: `automation/state/params.json` (Safe, read 2026-08-01) vs
`automation/state/aggressive/params.json` (Bold, read 2026-08-01). ✅ = both this tool and
Safe's tool model it. ⚠️ = disclosed gap, no `run_backtest` kwarg exists for either account.

| Knob | Safe value | Bold value | Modeled? |
|---|---|---|---|
| `strike_offset` (via tier table) | `V15_SAFE_TIERS`: ATM at all tiers under $10K | `V15_BOLD_CORE_TIERS`: ATM $0-2K → OTM-2 $2-10K → OTM-1 $10-25K → ITM-2 $25K+ (**sim-convention-negated**, §3.2) | ✅ |
| `per_trade_risk_cap_pct` | 0.30 | 0.50 | ✅ (via `resolve_bold_qty`, not `run_backtest`'s dead scaling — §3.1) |
| `min_contracts` (real qty formula) | 3 | **5** | ✅ (`resolve_bold_qty`, §3.1) |
| Exit shape (ribbon_ride) | `strategies.RIBBON_RIDE.exit` | **identical dict** (§3.3) | ✅ |
| `filter_10_min_triggers_bear` | 1 | 1 | ✅ same |
| `filter_10_min_triggers_bull` | **2** | **1** | ✅ — Bold needs only ONE confirming trigger for a bull entry |
| `block_level_rejection` | **true** | **false** (removed 2026-06-18) | ✅ — Safe blocks LEVEL-tier bear rejections; Bold does not |
| `block_elite_bull` | true (VIX band 0-25, effectively unconditional) | **INPUT PARAMETER** (currently `false`, trial armed 2026-08-01) | ✅ — the gate under test |
| `block_elite_bull_vix_low/high` | 0.0 / 25.0 | **15.0 / 18.0** | ✅ — Bold's band (when armed) is a narrow 3-point window vs Safe's near-unconditional band |
| `entry_bar_body_pct_min` | 0.2 | **absent → 0.0 (off)** | ✅ — Safe blocks doji/wick-dominant bear entries; Bold does not |
| `block_bull_1100_1200` | true | **absent → false** | ✅ — Safe blocks ALL bull entries 11:00-12:00 ET; Bold does not |
| `block_bull_morning_agg` | absent → false | false (J-disabled 2026-06-24, "remove this entirely") | ✅ same net effect, different provenance |
| `vix_bear_hard_cap` | 23.0 | **absent → gate off entirely** | ✅ — flagged in Bold's own params.json doc as "BOLD-VIX-BEAR-CEILING-GAP" |
| `require_bearish_fill_bar` | absent → false | **true** (J-ratified 2026-06-17) | ✅ — Bold requires a confirming bearish N+1 fill-bar before a bear entry; Safe does not |
| `midday_trendline_gate` | false | false | ✅ same |
| `min_ribbon_momentum_cents` / `max_ribbon_duration_bars` | null / 999 (explicitly disabled) | absent (defaults off) | ✅ same net effect |
| `min_entry_premium` (→ `min_premium_for_level_tiers`) | 0.3 | 0.3 | ✅ same |
| `chart_stop_buffer_dollars` | 0.5 | 0.5 | ✅ same |
| `time_stop_et` | 15:40 | 15:40 | ✅ same |
| `entry_no_trade_before/after_et` | 09:35 / 15:00 | 09:35 / 15:00 | ✅ same |
| `structure_stop_enabled` | true | true | ✅ same |
| `structure_veto_enabled` | true | **absent → false** | ⚠️ real difference, but consumed by `backtest/lib/engine/engine_cli.py`, NOT `orchestrator.run_backtest` — no kwarg exists to model it for **either** account. Pre-existing gap, not introduced here. |
| `pdt_gate_mode` | `cash_settlement` | `margin_pdt` | ⚠️ runtime/state-dependent (day-trade counts / settlement ledger) — no static full-history walk in this repo models either account's version |
| `daily_loss_kill_switch_pct` | 0.30 | 0.50 | ⚠️ runtime/state-dependent (intraday equity path) — not modeled by any orchestrator-based tool |
| `max_premium_per_contract` | 3.3 | 5.0 | ⚠️ additional live pre-order cap outside `run_backtest`'s kwarg surface |
| `v15_max_premium_pct_of_account` | present (tiered) | **absent entirely** | ⚠️ Safe has a SECOND premium-tier cap layered on the 30% risk cap; Bold has no such table — `risk_gate.check_order`'s `MAX_PREMIUM_TIER` check is skipped outright for Bold. Not modeled (same class as above). |

## 5. The tool

`backtest/tools/bold_fullhist_replay.py`. **Separate tool, not a `--account` mode on
`engine_fullhist_replay.py`** — decided by reading, stated in the module docstring: every
gate-study tool in this repo (`elite_bear_level_reject_gate_ab.py`,
`elite_bull_postfix_requal_2026_07_31.py`) hand-builds its own BASE config rather than a
shared parameterized runner, explicitly because `runner.run_with_params`'s allowlist doesn't
cover every live key. Threading `BOLD_BASE_LIVE` + the qty-resolution divergence + the
strike-sign fix + a completely different anchor set through one shared module via a flag
would need as much branching as two focused ~850-line modules, and would break this
established convention. The account-agnostic primitives (`build_ribbon_lookup`,
`ribbon_tick_df_for`, `naive_dt`, `match_entries_by_strike_side_time`) are **imported from**
`engine_fullhist_replay.py`, not copy-pasted — one tested implementation, two callers.

`block_elite_bull` is a **required parameter** (no default) of `bold_base_live()` and
`replay_population()` — task requirement: "the harness must take gate state as an input so
studies can run pre/post-trial counterfactuals." `main()` runs both states
(`pre_trial_block_elite_bull_true`, `post_trial_block_elite_bull_false`) into one scorecard.

CLI: `--anchor-only` (fast, ~2s), `--first-consumer-only` (fast, ~1s), full run (~3.2 min for
both gate states + anchor + first-consumer).

## 6. Verification (OP-16 sim-accuracy gate)

### 6.1 Anchor validation — 6/7 real bold-2 fills reproduce

7 real bold-2 **ENGINE-attributed** round trips (filtered from `fills-ledger.jsonl` to
`attribution=="engine"` — J's manual fills were excluded on purpose; this harness models the
engine, not J's discretion), spanning 2026-06-26 → 2026-07-28, both P and C sides. Every
single one is qty=5, the strongest available confirmation that Bold's real sizing is
unconditionally `min_contracts`, never a scaled amount. 2 of the 9 originally-needed OPRA
contracts (`SPY260723P00735000`, `SPY260727P00737000`) were not yet cached — backfilled this
session via the same trades-aggregation fetch path `elite_bull_postfix_requal_2026_07_31.py`
already built (the `/options/bars` endpoint's known 403 "OPRA agreement is not signed"
issue), both returned via the plain bars endpoint successfully this time.

Pass rule: same win/loss sign AND within `max($60, 30% of |real|)` — a generous, disclosed
tolerance (exact-cent parity isn't expected; `exit_manager_walk.py`'s own FILL-PRICE
CONVENTION docstring documents the resting-order-limit-fill approximation vs real
spread/timing).

| Date | Symbol | Real P&L | Replay P&L | Result |
|---|---|---|---|---|
| 2026-06-26 | SPY260626P00729000 | -$15.00 | -$21.00 | PASS |
| 2026-07-02 | SPY260702P00743000 | -$60.00 | -$48.00 | PASS |
| 2026-07-02 | SPY260702P00740000 | +$290.00 | +$218.80 | PASS |
| 2026-07-17 | SPY260717P00743000 | +$191.00 | +$177.40 | PASS |
| 2026-07-23 | SPY260723P00735000 | -$305.00 | -$390.00 | PASS |
| 2026-07-27 | SPY260727P00737000 | -$355.00 | -$325.00 | PASS |
| 2026-07-28 | SPY260728C00741000 | -$295.00 | -$185.00 | **FAIL** (same sign, $110 outside $88.50 tolerance) |

**6/7 pass (85.7%), all same-sign (7/7)**, clearing the task's N≥5 requirement with margin.
The one failure (07-28 C741) is a real, disclosed divergence — same direction (both losses)
but outside the dollar tolerance, most likely structure-stop level/bar-timing precision (the
same class of imprecision Safe's own `engine_fullhist_replay.py` anchor discloses for its
2026-07-17 day). Per the task's own instruction ("a harness that can't reproduce real fills
is labeled UNVALIDATED and says so on every output") — **this harness is NOT claiming
perfect validation; it is disclosing 6/7 with the one miss named, on every JSON/MD output it
produces** (`anchor_validation` block, `all_pass: false`, printed in the runner's own log
line).

### 6.2 Full population walk — both gate states, 2025-01-02..2026-07-22

Same window as Safe's tool (`engine_fullhist_replay.py`) for apples-to-apples comparability.
Static equity ($1,197.52, live-verified) and strike tier (ATM) throughout — same disclosed
convention as Safe's tool ("both static... NOT a compounding account curve").

| Gate state | `block_elite_bull` | Raw entries | Excluded (no OPRA / risk-cap-deadlock) | Replayed | Total P&L | WR | Avg/trade |
|---|---|---|---|---|---|---|---|
| PRE_TRIAL | true | 334 | 18 / 160 | 156 | +$7,448.40 | 33.3% | +$47.75 |
| POST_TRIAL | false (current, armed 2026-08-01) | 402 | 18 / 182 | 202 | +$6,490.80 | 30.2% | +$32.13 |

**Coverage caveat (disclosed, sizable):** 45-48% of raw entries are excluded via
`n_excluded_risk_cap_deadlock` — bold-2's **current** thin equity ($1,197.52) makes many
historical-window premiums unaffordable at the true 5-contract floor under a static-equity
assumption. This is the same "static equity, not a compounding curve" convention Safe's tool
uses, but the exclusion rate is much higher for Bold given its higher risk-cap-relative qty
floor. Read the population totals as "what Bold's shape would produce **at today's account
size**, applied historically" — not as "what bold-2 actually made."

**Read this window's pre/post-trial delta with real care.** This walk covers 2025-01-02
through 2026-07-22 — entirely **before** the levels-compiler-v2 fix (commit `7b4aa3f4`,
shipped 2026-07-27 evening) that Friday's requalification study exists specifically to
re-test around. Per-tier breakdown confirms the delta is concentrated exactly where
expected: lifting the gate adds 61 new ELITE-tier bull trades (14→75) whose combined
contribution is **-$538.80** (≈ -$8.83/trade average) — roughly breakeven-to-slightly-
negative, consistent with (not contradictory to) the "old era is bad" finding Friday's study
already established from independent evidence (0% WR n=24 real fills, -$1,720 backtest-
detection, -$3,873 OTM-2 SS-B). **This is a novel, independent, much-larger-sample (61 vs
Friday's most-comparable n≤30) confirmation of the same old-era-weak-signal conclusion under
Bold's own true shape for the first time — not fresh counter-evidence against the post-fix
trial.** It should not be read as "the gate lift lost $957 over 386 days, therefore
re-block" — that $957 is old-regime noise the trial's own thesis already discounts.

### 6.3 A finding worth its own line: TP1/runner qty-split truncation

Building the first-consumer re-replay (§7), the "P&L is exactly linear in qty" assumption
that motivated a cheap analytic 5/3 rescale of the source study's qty=3 numbers was
**disproven by its own cross-check**, not assumed away: `tp1_qty_fraction=0.667` means
`int(qty * 0.667)` splits 2/1 (66.7%/33.3%) at qty=3 but 3/2 (60.0%/40.0%) at qty=5 — a
LARGER relative runner allocation at qty=5. Any trade that reaches TP1 and rides a runner
therefore scales **super-linearly**, not linearly, between qty=3 and qty=5. Confirmed exactly
on the one TP1-splitting trade in the cohort (analytic rescale $530.67 vs independent replay
$542.80 — a $12.13 gap on that trade alone; the other 4 non-TP1 trades in the same cohort
match the analytic rescale to the cent). The tool's independent re-replay (not the analytic
shortcut) is what the corrected verdict in §7 is graded on.

## 7. First consumer: the elite-bull blocked-cohort delta (task step 4)

Source: `analysis/recommendations/elite-bull-requal-2026-07-31.json` (verdict `a`, the study
that justified arming tonight's trial, commit `b6a9db67`
`feat(gate): arm the decided elite-bull LIFT-GATE TRIAL on bold-2 (Next-Twelve #1)`).

**Finding #1 — account mismatch.** The frozen verdict rule's `primary_cell` was
`safe_sequential_hold_qty3` — **Safe's** blocked-signal cohort (n=5, +$867.00, drop-best
+$177.40) — not bold-2's own. Bold's own cohort (`bold_sequential_hold_qty3`) was computed
and reported in the same file but was **never the frozen rule's primary input**. The trial
armed on `aggressive/params.json` (the bold-2 account) on evidence drawn from the sibling
account.

**Finding #2 — even the disclosed bold-labeled cohort used the wrong qty.** Both of the
source study's "bold" cohorts (`bold_per_event_qty3`, `bold_sequential_hold_qty3`) size at
qty=3 or qty=10 — neither is bold-2's real `min_contracts=5` (§3.1).

**Finding #3 — the corrected number.** Re-replaying the SAME 5 kept, sequential-hold bold-2
events at the TRUE qty=5 (independent re-walk through `walk_exit_manager`, not an
approximation):

| Cell | n | Total P&L | Drop-best |
|---|---|---|---|
| Friday's cited PRIMARY (Safe's cohort, qty3) | 5 | **+$867.00** | +$177.40 |
| Bold's own cohort, study's qty3 | 5 | -$2.60 | -$321.00 |
| **Bold's own cohort, TRUE qty=5 (this tool, authoritative)** | 5 | **+$7.80** | **-$535.00** |
| (cross-check: analytic 5/3 rescale of the qty3 row) | 5 | -$4.33 | -$535.00 |

Bold's own true-shape total is a **coin-flip** ($7.80 on ~$1-2K of notional per trade — noise
level), not a robust positive. **One single trade** (07-31 12:16 SPY260731C00744000,
+$542.80) is the entire positive total; remove it and the remaining 4 trades net -$535.00.

**Finding #4 — the frozen verdict rule is sign-only, and that's a real gap.** Grading
Bold's own corrected total ($7.80) against the SAME frozen rule (`primary_total>0 AND
fleet_net>0 → verdict 'a'`) still mechanically outputs `'a'` — $7.80 clears `>0` exactly as
$867.00 does. **This is the task's own explicit "say so loudly" trigger** ("If it materially
weakens (sign flip **or drop-best negative**)"): drop-best is strongly negative (-$535.00)
under bold's true shape, a fact the sign-only rule is blind to. The rule's own honesty clause
anticipated exactly this situation ("if (a) fires while PRIMARY drop-best < 0, the rec states
this explicitly as a concentration risk marker") — so this finding is inside the rule's own
disclosed failure mode, not a violation of it. **Reported here as that concentration-risk
marker, explicitly, per the rule's own instruction, since the source study's PRIMARY
(Safe's) never triggered it.**

**What this does NOT change:** the trial's forward kill-criterion (n≥10 elite-bull fills OR
10 sessions, whichever first; net realized < 0 → re-block same day) is a **live, forward,
real-fills guard** — it doesn't depend on Friday's static evidence at all, and it stands
regardless of this finding. This audit does not recommend re-blocking on its own authority
(no live-config edit is in this session's lane, per the task brief); it recommends J know the
disclosed justification was a different account's number, and that bold-2's own number is a
coin flip resting on one trade.

## 8. Guards

`backtest/tests/test_bold_fullhist_replay.py` — 13 tests, all passing:

| Test | Pins |
|---|---|
| `test_resolve_bold_qty_uses_bold_min_contracts_not_safe` | qty formula uses Bold's floor, not Safe's |
| `test_resolve_bold_qty_excludes_never_downsizes` | unaffordable-at-floor excludes, never shrinks below the floor |
| `test_bold_min_contracts_constant_matches_aggressive_params_json` | constant tracks the live source file |
| `test_mistranslated_qty_fails_the_anchor_where_correct_qty_passes` | **RED-proof (task requirement)**: replays a real anchor fill at the correct qty=5 (passes) and the wrong qty=3 (FAILS) through the actual `walk_exit_manager` — end-to-end, not a synthetic assertion |
| `test_live_to_sim_strike_offset_negates` | sign-convention negation, unit level |
| `test_resolve_bold_strike_offset_matches_v15_bold_core_tiers_negated` | sign-convention negation at both the current ATM tier and the $2-10K OTM-2 tier, proving a non-negated offset would diverge |
| `test_bold_tool_uses_the_real_shared_ribbon_ride_exit_shape` | exit-shape-parity (mirrors Safe's own guard) |
| `test_run_backtest_receives_shared_shape_regardless_of_gate_state` | `block_elite_bull` is the ONLY diff between pre/post-trial configs |
| `test_translation_table_pins_against_live_aggressive_params_json` | every hardcoded gate value tripwires against the on-disk source |
| `test_translation_table_differs_from_safe_where_documented` | cross-checks the claimed Safe-vs-Bold differences are real, not accidental |
| `test_block_elite_bull_is_a_parameter_not_a_constant` | no silent default — a caller can never accidentally model the wrong gate state |
| `test_anchor_set_has_at_least_5_engine_attributed_real_fills` | anchor set composition (≥5, all qty=5, all engine-attributed) |
| `test_anchor_validation_passes_majority_within_tolerance` (slow) | ≥5/7 anchors pass, all evaluated anchors agree on direction |

Run: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_bold_fullhist_replay.py -v`
— 13 passed.

## 9. Artifacts

- Tool: `backtest/tools/bold_fullhist_replay.py`
- Guards: `backtest/tests/test_bold_fullhist_replay.py`
- Scorecard: `analysis/recommendations/bold-fullhist-replay-2026-08-01.json` /
  `.md` (population walk, both gate states, anchor validation, first-consumer delta — one
  run produces all three)
- This report: `analysis/deep-research/BOLD-HARNESS-2026-08-01.md`
- One-off OPRA backfill script (scratchpad, not committed):
  `fetch_missing_anchor_puts.py` — reused `elite_bull_postfix_requal_2026_07_31.py`'s own
  `fetch_bars_via_trades` fallback for 2 anchor PUT contracts the prior tool's own hardcoded
  `side="C"` never needed

## 10. Status: UNVALIDATED-WITH-DISCLOSED-GAP, not VALIDATED

Per the task's own instruction: this harness reproduces 6/7 (85.7%) real bold-2 engine fills
within a generous, disclosed tolerance — clearing the N≥5 bar with margin, all same-sign,
but **not** perfect. It carries three disclosed, pre-existing scope gaps shared with every
orchestrator-based tool in this repo (`structure_veto_enabled`, PDT/settlement state,
kill-switch state) and one Bold-specific coverage caveat (45-48% of raw entries excluded at
today's thin equity under the static-equity convention). It should be trusted for
**directional, relative (gate-on vs gate-off), and magnitude-order** conclusions — exactly
how it was used in §7 — not for cent-level production forecasting.
