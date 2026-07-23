# Mirror-Parity Audit — 2026-07-22

> J-directed, high priority: "every bear strategy can be a bull strategy — fix that." Facts-first
> census of every bear-side setup's bull mirror, every gate that blocks bull specifically, and
> whether each blocking gate's evidence still matches CURRENT config (ATM strike + SS-B exit).
> Companion to [`bull-requalification-2026-07-22.json`](../../analysis/recommendations/bull-requalification-2026-07-22.json)
> (Part 2 — the owed re-eval) and its human-readable summary,
> [`bull-requalification-2026-07-22.md`](../../analysis/recommendations/bull-requalification-2026-07-22.md).

**Primary prior art, cited not duplicated:** [`DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md`](DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md)
already ran a file:line census of all 15 `GATE_ORDER` gates + the pre-gate structure veto one
week before this audit, and explicitly recommended "re-test `block_elite_bull` at ATM, run
`block_bull_1100_1200` at ATM not OTM-2" as the #1 item in its one-battery fix list. **This
audit executes that specific recommendation** (Part 2) and updates its verdict table with the
result. Nothing below re-litigates work that document already did correctly — it adds the ATM
replay that document called for but did not itself run, plus a fresh 2026-07-22 recheck of
which gates are armed today (configs drift week to week).

---

## 1. Strategy registry — does a bull mirror exist in CODE?

`automation/state/fleet/strategies.py` (the shared strategy registry every fleet account trades)
has exactly 2 entries. Both are **direction-agnostic by construction** — the module's own
comment: *"the side comes from which side-block (bull/bear) fired. No per-strategy direction
lock."*

| Strategy | Bear entry_setup | Bull entry_setup | Exit shape | Mirror status |
|---|---|---|---|---|
| `RIBBON_RIDE` | `BEARISH_REJECTION_RIDE_THE_RIBBON` | `BULLISH_RECLAIM_RIDE_THE_RIBBON` | SS-B (shared, identical both sides) | **FULL PARITY** — same file, same exit shape, same strategy object |
| `VWAP_CONTINUATION` | `VWAP_CONTINUATION` | `vwap_continuation` (case-insensitive same setup) | `-0.06/+0.40/0.8/fixed` (shared) | **FULL PARITY** — one setup name fires both directions off the same side-block |

Extra setups outside the fleet registry (core-Safe `heartbeat_core.py` dispatch only —
`vwap_reclaim_failed_break`, `vix_regime_dayside`): both configured `side: "both"` in
`automation/state/params.json` (`j_vwap_reclaim_fb_side`, `j_vix_dayside_side`), both ARMED.
**Full parity at the strategy/setup-name level.** At this layer, OP-16's "direction is not a
scope" is already true in code — the asymmetry lives entirely downstream, in the 15 entry gates
and 2 scoring filters below.

---

## 2. Gate-by-gate census — `backtest/lib/engine/gates.py` `GATE_ORDER` (15 gates)

Columns: **Live (Safe / Bold)** = armed value as of 2026-07-22 (`automation/state/params.json` /
`automation/state/aggressive/params.json`, verified this session). **Evidence date** = when the
value currently armed was last ratified. **Evidence config** = strike tier + exit shape that
ratification evidence was generated under. **Current config** = ATM (Safe core path, confirmed
live since ≥2026-06-18, fills-verified 2026-07-11 — [`2026-07-11-strike-tier-reconciliation.md`](../deep-research/2026-07-11-strike-tier-reconciliation.md))
+ SS-B exit (shipped 2026-07-09/10). **STALE/CURRENT** = does the evidence match today's config.

| # | Gate | Side | Live: Safe / Bold | Evidence date (file) | Evidence config | STALE / CURRENT |
|---|---|---|---|---|---|---|
| 1 | `block_level_rejection` | bear only | **true** / `false` | 2026-06-17 `level-rejection-gate-01.json` | pre-SS-B, pre-ATM-confirm, generic OTM ladder | STALE (bear-only, out of this audit's bull scope) |
| 2 | `trendline_requires_ribbon_flip` | not side-keyed (tier==TRENDLINE, either side) | off / off | 2026-06-17, HOLD (WF=-1.371 FAIL) | pre-SS-B | N/A — unarmed, no bull-blocking effect |
| 3 | **`block_elite_bull`** | **bull only** (`level_reclaim` + tier==ELITE) | **Safe: true, VIX[0,25)** / **Bold: true, VIX[15,18)** | Safe: 2026-06-18 (extend) + **2026-07-10 SS-B revalidation** (`block-elite-bull-ssb-revalidation.json`, KEEP); Bold: 2026-06-18 only | Safe 07-10 revalidation: **SS-B exit (current) but strike_offset=-2 (OTM-2, STALE)** — explicitly pinned in its own pre-reg §`strike_convention`. Bold: pre-SS-B, pre-ATM, never revalidated at all. | **STALE on strike (Safe); STALE on everything (Bold)** — see Part 2 for the ATM-corrected re-test |
| 4 | `block_bull_ribbon_flip` | bull only | **off / off** (absent both files) | 2026-06-17, REJECTED (WF=-23.984) — arming was never shipped | N/A | N/A — code correctly stays off; nothing to unblock |
| 5 | **`block_bull_1100_1200`** | **bull only**, 11:00-12:00 ET | **Safe: true** / Bold: off (absent) | 2026-06-18 orig + 2026-06-26 revalidation (real fills, PASS) | 06-26 revalidation used **OTM-2 strike** (per 07-15 audit finding) — pre-ATM, pre-SS-B | **STALE** — see Part 2 |
| 6 | `block_bull_morning_agg` | bull only, Bold-scoped | **off / off** (Bold explicitly disabled 2026-06-24, J-directed) | 2026-06-18 ratify → J killed 06-24 after a real false-positive veto | pre-SS-B | N/A — J-decision-gated, do not re-arm without J (per `automation/overnight/queue.md:296`) |
| 7 | `require_bearish_fill_bar` | **bear only** — **no bull mirror exists in code at all** | off / **Bold: true** | 2026-06-17 ratify → 2026-06-26 revalidation FAILED 3/5 gates, never re-shipped | pre-SS-B | STALE (bear-only, out of bull scope, but flagged: Bold is trading on a gate whose own revalidation failed) |
| 8-9 | `min_ribbon_momentum_cents` / `max_ribbon_duration_bars` | not side-keyed | off / off | 2026-06-16/17 REJECTED | pre-SS-B | N/A — mechanically inert both accounts |
| 10 | `midday_trendline_gate` | bear-tied (`trendline_rejection`-only trigger) | off / off | 3-way contradictory provenance (07-15 audit finding, unresolved) | pre-SS-B | N/A — out of bull scope |
| 11 | `block_conf_lvl_rej_midday_afternoon` | bear-tied (`level_rejection` trigger) | off / off | REJECTED both accounts | pre-SS-B | N/A — out of bull scope |
| 12 | `block_conf_lvl_rec_afternoon` | **bull-tied** (`level_reclaim` trigger) — structural mirror of #11 | off / **Bold: true ("KEPT but DEAD", 0 impact)** | 2026-06-26 revalidation verdict **"UNBLOCK_SUPPRESSES_WINNERS"** (removes a +$1,034 winner) — never applied | pre-SS-B, suspected timestamp-keying bug in the revalidation itself (07-15 audit) | STALE — a gate whose own re-test says UNBLOCK is still armed on Bold |
| 13 | `entry_bar_body_pct_min` | bear only | **Safe: 0.20** / off | 2026-06-18 ratify → 2026-06-26 audit recommended UNBLOCK, queued, **never shipped** | pre-SS-B, pre-ATM | STALE (bear-only, out of bull scope) |
| 14 | **`entry_bar_body_pct_min_bull`** | **bull only — literal code-level mirror of #13** | **off / off** (absent both files) | `j-entry-quality.json` 2026-06-20: tested at 0.20, OOS **-$1,240** (n=1!), WF=-4.622, verdict **WATCH** (never ratified) | pre-SS-B, pre-ATM, n=1 (thin) | N/A — unarmed; the mirror **exists in code, is simply never armed, on a study too thin to act on** |
| 15 | `vix_bear_hard_cap` | **bear only — no bull-ceiling mirror exists** (bull's only VIX gate is #3's band, a different mechanism) | Safe: 23.0 / **Bold: absent entirely** | 2026-06-18 ratify | pre-SS-B narrative | STALE (bear-only, out of bull scope) |

**Bold-vs-safe scope note:** Bold's `block_elite_bull` band is narrower ([15,18) vs Safe's
[0,25)) and has **never once been revalidated since its 2026-06-18 ratification** — Part 2 of
this audit is Safe-scoped only (matches the existing 2026-07-10 SS-B study's scope); Bold's
`block_elite_bull` remains an open gap, flagged for a follow-up, not run here.

---

## 3. Filters outside `GATE_ORDER` that key on side==C

`gates.py`'s 15 are not the whole story — `backtest/lib/orchestrator.py:778-779` resolves a
**separate** per-direction trigger-count filter that structurally treats bulls as needing MORE
confirmation than bears:

```python
bear_min_triggers = min_triggers_bear if min_triggers_bear is not None else min_triggers
bull_min_triggers = min_triggers_bull if min_triggers_bull is not None else max(2, min_triggers)
```

| Param | Safe (live) | Bold (live) | Effect |
|---|---|---|---|
| `filter_10_min_triggers_bear` | 1 | 1 | bear needs only 1 confirming trigger |
| `filter_10_min_triggers_bull` | **2** | 1 | **Safe bulls need DOUBLE the confirming triggers bears need; Bold has parity (1/1)** |

This is a genuine, currently-armed, Safe-specific asymmetry that is NOT one of the 15
`GATE_ORDER` gates — it lives in `_apply_param_overrides` (`orchestrator.py:350-357`) and the
default fallback itself (`max(2, min_triggers)`) is asymmetric **even when unconfigured**. The
2026-07-01 wide-window re-audit of exactly this lever
([`bull-unblock-structural-widewindow-2026-07-01.json`](../../analysis/recommendations/bull-unblock-structural-widewindow-2026-07-01.json))
found the min_triggers_bull 2→1 relaxation IS/OOS sign-flips (IS -$299.70, OOS +$907.28, `walk_forward.both_positive: false`) — inconclusive, not re-tested here (still OTM strike, pre-SS-B; carried forward as a known-stale open item, not re-run this session for time).

**No `min_triggers_bear`-style asymmetry exists for anything else scanned** (`allow_one_blocker`,
`vix_soft_mode`, `sweep_blocker_enabled` are all bear-only carve-outs sitting inert per the
07-15 audit — none currently armed, so no live bull effect).

---

## 4. Summary — is the premise true?

**"Bull side is functionally dead" is partially true, not fully.** Two live gates in `GATE_ORDER`
block bull specifically on Safe (`block_elite_bull`, `block_bull_1100_1200`), both on STALE
evidence (wrong strike tier at minimum, wrong exit shape at the 2026-06-18 originals). One
scoring filter (`filter_10_min_triggers_bull=2` vs bear's `1`) makes Safe bulls structurally
harder to trigger than bears, unrelated to the gates. **But bulls are NOT gate-starved to zero
fills** — Part 2's current-config real-fills count found **n=24 engine-attributed bull fills
since SS-B shipped (2026-07-09), across 5 of 6 fleet arms** — the mirror capability fires in
production today. The honest finding is not "bulls can't fire," it's "bulls fire, on stale-
evidence gates, and have gone 0-for-24 since the current exit shape shipped" (Part 2 detail).

---

## 5. What this audit does NOT do (per task scope)

No params.json/gates.py/filters.py/heartbeat_core.py edit was made. No gate was unblocked. The
verdicts in Part 2 (`bull-requalification-2026-07-22.json`) are recommendations for the
orchestrator to adjudicate — this document and its companion are evidence, not a ship.
