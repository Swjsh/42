# Gate-Recency Audit — 2026-08-08

> **Mission:** J standing doctrine (2026-07-31, verbatim): *"the same thing that worked on day 372 ago is not gonna work on day 162 ago."* Dynamic market — recency beats aggregate. Every armed gate needs a revalidation clock. Motivating scar: `block_elite_bull` blocked a perfect 11/11 setup 111 times same-session on stale evidence (2026-07-31).
>
> Machine-readable companion: [`gate-recency-audit-2026-08-08.json`](gate-recency-audit-2026-08-08.json). Read-only audit — no production file was touched.

---

## Method (verify before you trust the table)

- **Inventory sources:** `automation/state/params.json` + `automation/state/aggressive/params.json` (every `block_*`/`enable_*`/gate-ish key), `backtest/lib/engine/gates.py` (`GATE_ORDER`, the 15 canonical entry gates — verbatim source of truth), `backtest/lib/engine/engine_cli.py` (`structure_veto_enabled` wiring), `setup/scripts/heartbeat_core.py` (free-model veto, risk_gate calls, extra-setup routing, scoring-filter kwarg wiring), `backtest/lib/filters.py` (the numbered scoring filters 1–11, a layer *upstream of* `GATE_ORDER`), `automation/state/fleet/strategies.py` (confirmed: no independent per-entry filters beyond setup-name matching), and a repo-wide `grep block_` under `automation/` and `backtest/lib/engine/`.
- **Provenance sources:** `analysis/recommendations/*.json`/`.md`, `markdown/audits/*.md`, plus two pre-existing instruments I used as cross-validation (not blindly copied): `automation/state/gate-registry.json` + `automation/state/gate-registry-status.json` (J's own gate-expiry checker, `Gamma_GateExpiryCheck`, run **2026-08-07**) and `automation/state/param-provenance.json`. Where a gate is also covered by that instrument's own OPRA-replay P&L verdict, I cite it explicitly and note when it agrees or disagrees with my raw tick counts.
- **Recent-window counts are MINE, freshly mined this session**, not copied from the existing instrument (which uses a different 25-day window). I streamed `automation/state/core-decisions.jsonl` (23,505 rows, both Safe and Bold write to this ONE file — there is no live separate aggressive ledger) and took the **last 15 distinct trading days present in the ledger with `armed=true`: 2026-07-21 → 2026-08-07** (10,073 rows in-window; Safe 5,007 armed ticks / 13 days present, Bold 5,008 / 13 days present).
- **Filter-layer correction (caught and fixed mid-audit):** the scoring layer's numbered filters mean *different things on the bull side vs the bear side* despite sharing a number. I verified this against `filters.py`'s actual `blockers.append()` call sites and `heartbeat_core.py:661-670`'s kwarg wiring, not just code comments, after an initial mis-attribution. See the JSON's `filter_layer_caveat` for the exact mapping.
- **Staleness formula (as specified):** `days_since_last_validation × recent_blocks_last_15_trading_days`. Unknown provenance uses a 180-day proxy, flagged per row.

---

## Ranked table (17 scored gates; 15 more inert/doctrine gates listed below the fold)

| Gate | Setting | Last validated → verdict then | Blocks (15d) | Staleness score | Recommendation |
|---|---|---|---:|---:|---|
| **1. `filter_10_min_triggers_bull`** | Safe=2, Bold=1 (bear floor=1 both) | **UNKNOWN** — no dated scorecard; inherited v11/v12 doctrine | 551 (275+276) | **99,180** | REVALIDATE |
| **2. `filter_9_vol_multiplier`** (bear) | 0.7 both | UNKNOWN — v11-era, no post-v15 re-check found | 43 (21+22) | **7,740** | REVALIDATE |
| **3. `require_bearish_fill_bar`** | Bold=true, Safe=false | 2026-06-17 → Bold IS+$363/OOS+$1,153 | 52 (Bold) | **2,704** | REVALIDATE |
| **4. `extra_setup_exec_armed.vwap_continuation`** | Safe=**false** (disarmed) | 2026-07-25 → 0-for-12 real fills, -$357 combined | 169 signals suppressed | **2,366** | REVALIDATE (sanity check, not a P&L claim) |
| **5. `block_conf_lvl_rec_afternoon`** | Bold=true, Safe=off | 2026-06-18 → self-contradictory doc (see notes) | 31 (Bold) | **1,581** | REVALIDATE |
| 6. `structure_veto_enabled` | Safe=true, Bold=false | 2026-06-26 → Safe +$583 IS, $0 OOS | 34 (Safe) | 1,462 | REVALIDATE |
| 7. `free_model_veto` | both=true | 2026-07-09 (bugfix, never P&L-checked) | 43 core / 62 total | 1,290 | REVALIDATE |
| 8. `entry_bar_body_pct_min` | Safe=0.2, Bold=off | 2026-06-18 → Safe OOS+$566 | 11 (Safe) | 561 | REVALIDATE |
| 9. `block_bull_1100_1200` | Safe=true, Bold=false | 2026-06-18 → thin n=11 IS/n=1 OOS | 6 (Safe) | 306 | REVALIDATE |
| 10. `extra_setup_exec_armed.vix_regime_dayside` | Safe=**false** (disarmed) | 2026-07-25 → 0-for-5, -$153 | 17 suppressed | 238 | REVALIDATE (sanity check) |
| **11. `pdt_gate_mode` (Bold=`margin_pdt`)** | Bold self-imposed legacy PDT | **2026-08-06** → self-imposed, broker doesn't enforce, $1,465 foregone one day alone | 49 (Bold) | 98 *(see caveat)* | **ACT ON PENDING DECISION** |
| 12. `block_level_rejection` | Safe=true, Bold=false | 2026-06-17 → Safe IS+$13,181/OOS+$682 | 1 (Safe) | 52 | KEEP |
| 13. `block_elite_bull` | **both=false** (trial since 2026-08-03) | 2026-08-03 → trial armed on fresh real-fill evidence | 0 *(325 pre-disarm)* | 0 | KEEP / MONITOR TRIAL |
| 14. Liquidity-gate bundle (6 keys) | armed-looking, e.g. `bid_ask_spread_max_cents=8` | **CONFIRMED DEAD** — zero code consumers | 0 (cannot fire) | 0 | RETIRE-CANDIDATE |
| 15. Macro-veto bundle (4 keys) | `macro_hard_veto_minutes=120` etc. | **CONFIRMED DEAD** — zero code consumers | 0 (cannot fire) | 0 | RETIRE-CANDIDATE |
| 16. `vix_bear_hard_cap` | Safe=23.0, Bold=false | 2026-06-18 → cleanest gate in the census | 0 (VIX quiet all summer) | 0 | KEEP |
| 17. `min_entry_premium` | 0.3 both | **2026-07-31** → "DO NOT TOUCH", freshly reconfirmed | ~0 | 0 | KEEP |

Row 11's staleness *score* is low by the mechanical formula (evidence is only 2 days old) — it is elevated to the executive digest below because it is the single most concretely dollar-quantified "costing money right now" exhibit in this audit. Formula and editorial judgment disagree here on purpose; both are shown.

### Cross-validated against J's own gate-expiry instrument (`gate-registry-status.json`, run 2026-08-07)

Where that instrument's independent OPRA-replay P&L check exists, it agrees directionally with my raw counts:

| Gate | Their P&L verdict (2026-07-02..2026-08-06 window) |
|---|---|
| `structure_veto_enabled` | **RED** — refused cohort would have earned +$32.69/tr, n=11 |
| `require_bearish_fill_bar` | **RED** — refused cohort would have earned +$22.96/tr, n=36 |
| `block_conf_lvl_rec_afternoon` | GREEN — refused cohort would have lost -$29.02/tr (stale docs, but not currently costing) |
| `entry_bar_body_pct_min` | GREEN — refused cohort would have lost -$1.97/tr (thin margin) |
| `block_bull_1100_1200` | YELLOW — refused cohort +$240.35/tr but n=3, under the n=10 floor |
| `block_level_rejection` | GREEN — refused cohort would have lost -$41.76/tr, n=1 |
| `vix_bear_hard_cap` | STALE_UNVERIFIED — 0 fires, cannot be checked |
| `block_elite_bull` | INERT — not armed, nothing to measure |

Rows without a P&L verdict above (`filter_10_min_triggers_bull`, `filter_9_vol_multiplier`, the two disarmed extra setups, `pdt_gate_mode`, the two dead bundles) are outside that instrument's scope — its miner only walks `GATE_ORDER` + two named vetoes + fleet config, not the scoring-filter layer, the extra-setup lane, or risk_gate config modes. That gap is exactly what this broader audit adds.

---

## Notable findings beyond the ranked table

- **The scoring-filter layer is a real, separate gate class.** `backtest/lib/filters.py`'s numbered filters (1–11) sit *upstream* of `GATE_ORDER` and decide whether a side passes scoring at all. Two of them have live params knobs and made the top of the ranked table (`filter_9_vol_multiplier`, `filter_10_min_triggers_bull`). A third — the bull-side "buyer pressure" volume check (a *different* mechanism, despite also being called "filter 10" in bull-side code comments) — fires 374 times/15d but has **fresh, in-progress provenance**: `analysis/deep-research/FEED-DIVERGENCE-F10-F7-2026-08-07.md` (dated yesterday) root-caused it to IEX under-printing consolidated volume 1.3–8.2% bar-to-bar, and `analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json` has a fix already pre-registered and queued (a dormant `filter_10_vol_multiplier_bull` override key exists in code, just not yet set). No action item from me here — J's own pipeline is already ahead of this one. Flagged so the 374/15d figure doesn't get read as neglect.
- **Two full bundles of params.json keys are confirmed dead, not just unvalidated.** The 6-key "liquidity gate" (`bid_ask_spread_max_cents`, `bid_ask_spread_max_pct_of_mid`, `delta_min_abs`, `delta_max_abs`, `open_interest_min`, `liquidity_strike_retries_max`) and the 4-key "macro veto" (`macro_hard_veto_minutes`, `macro_soft_modifier_minutes`, `macro_soft_bull_threshold`, `macro_soft_bear_threshold`) have **zero code consumers anywhere in the repo**, confirmed by three independent, dated sources: `backtest/tests/test_params_consumer_reconciliation.py`'s pytest-guarded `KNOWN_DEAD` allowlist (proven non-vacuous by its own bite test), `automation/state/param-provenance.json` (every key tagged `status: "BARE"`), and a direct code-comment admission in `heartbeat_core.py:2002` ("`bid_ask_spread_max_cents` was a dead knob with zero consumers"). This costs nothing today (a gate that can't fire can't bind), but it is a false-confidence risk: params.json's own doc text describes "Hard rejections per risk-rules.md" that do not exist in the live order path.
- **`pdt_gate_mode` is really two stale-premise findings, not one.** Bold's `margin_pdt` mode is actively costing (see digest #1). Safe's `cash_settlement` mode was built for an account (`PA3DHPT7KIQE`) that no longer exists after the 2026-08-03 reset — the *current* safe-2 account reads `multiplier=4` (margin-shaped), contradicting the cash-account premise the mode assumes. Per the 2026-08-06 memo it "never visibly bound this week," so it isn't costing money today, but the doc citations on both modes are stale and the memo already asks for both to be re-verified regardless of which of its 3 options J picks.
- **`block_bull_ribbon_flip`'s CODE is correctly inert; its DOCTRINE TEXT is a separate kill-candidate.** `gate-registry.json` flags that `markdown/doctrine/BULL-DIRECTION-ACTIVATION.md` describes this gate as "active," citing figures that trace back to `LESSONS-LEARNED.md` L126 — whose own verdict is the *opposite* ("Do NOT implement... OOS delta -$3,123"). Not re-audited further here (outside this session's file-write scope); flagged so it isn't mistaken for validated-and-armed by a future reader.

## Gates excluded from ranking (doctrine / structural, not statistical edges)

`risk_gate` safety class (`KILL_SWITCH`/`RISK_CAP`/`MIN_CONTRACTS`/`NOT_FLAT`/`SETTLEMENT`) is J's Rules 4–7 directly — a regulatory/doctrine floor is never "wrong" for costing money, so it's inventoried (NOT_FLAT fired 43×Safe/18×Bold, RISK_DENY_RISK_CAP 15×Safe/4×Bold in the window) but not scored. Same treatment for the `09:35–15:00 ET` entry window (SKIP_LATE_ENTRY fired 32×Safe/12×Bold — J's explicit v15.1 operating-hours rule) and the unconditional `SKIP_STALE_TRIGGER` data-integrity guard (73×Safe/72×Bold — high frequency here is a *good* sign, it's catching stale bars by design) and `SKIP_NO_LEVELS` (0 fires — the level-feed-staleness incidents this guards against are historical, not present now). Full list with counts in the JSON's `inert_or_doctrine_gates_not_individually_ranked`.

15 more gates are currently fully inert (off, or off-by-J-override, or off-and-correctly-so per prior doctrine) with 0 recent blocks: `trendline_requires_ribbon_flip`, `block_bull_ribbon_flip`, `block_bull_morning_agg` (J-killed directly), `min_ribbon_momentum_cents`, `max_ribbon_duration_bars`, `midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `entry_bar_body_pct_min_bull`, plus 3 currently-armed-and-allowing (not blocking) extra setups (`vwap_reclaim_failed_break`, `double_bottom_base_quiet`, `bollinger_squeeze`). Full detail in the JSON.

---

## Executive digest — which 1-3 gates are most likely costing money RIGHT NOW

1. **`RISK_DENY_PDT` (Bold, `pdt_gate_mode=margin_pdt`)** is the clearest dollar-quantified cost found: a self-imposed legacy-PDT rule the paper broker doesn't even enforce, hard-blocking Bold 08-05/08-06/08-07 and continuing through 08-11 — 49 fires in 15 days, and Thursday 08-06 alone was a +$1,465 book day Bold couldn't join. A decision memo with 3 named options has sat open 2 days; this audit takes no side, only flags it's unresolved and actively costing.
2. **`structure_veto_enabled` (Safe)** and **`require_bearish_fill_bar` (Bold)** are both independently RED per J's own gate-expiry instrument as of yesterday: refused cohorts would have earned +$32.69/tr (n=11) and +$22.96/tr (n=36) — both 6+ weeks past their revalidation interval, on evidence that was thin even at inception (n=2 IS-only; Bold-only validation the fleet lane inherits globally).
3. **Honorable mention, not yet dollar-proven:** Safe's `filter_10_min_triggers_bull=2` (double Bold's own 1, double bear's own floor) sole-blocked 551 bull ticks in 15 days with zero dated evidence for the asymmetry — the single largest volume-suppressor in the audit and a plausible reason OP-16's bull re-eval cohort is stuck at n=10. Flagged as the top REVALIDATE candidate precisely *because* it has no $ evidence yet, unlike #1/#2.
