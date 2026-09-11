# VIX Dead-Zone Map — 2026-07-14

**Queue item:** `VIX-DEADZONE-MAP` (HIGH, gate-interaction, C15). Analysis only — no OPRA grind, no
params/config edits, no orders. Companion to `A6-VETO-GRADE-2026-07-14` (already `status:done`,
16:20 ET) — that item graded the free-model veto layer with real-OPRA counterfactual replay; this
map covers the VIX-gate side and the 5-account participation matrix A6 didn't touch.

**Headline verdict: the queue item's own premise is half wrong.** There is no live "VIX floor
blocks bear" gate. The engine's zero-trade day was driven predominantly by the free-model veto
layer (already graded net **+$565.50 positive** by A6) and five non-VIX structural gates, not by
a VIX-band trap. The one VIX gate that *is* real and *is* wide (`block_elite_bull`, Safe
`[0,25)`) was re-validated KEEP four days ago under the honest SS-B exit shape
(`analysis/recommendations/block-elite-bull-ssb-revalidation.json`, n=28, SS-B total **-$3,873.60**
vs the old exit's -$560.00 — the gate is saving money, not costing it).

---

## 1. Ground truth: what's actually LIVE vs vestigial (read before trusting any VIX number)

The queue item quoted "bear-entry threshold 17.30" and a bull band of "[15,17.5)". Both numbers
exist in `automation/state/params.json`, but **neither gates the live order-placing engine.**

| Key | Value (Safe) | Value (Bold) | Live consumer? |
|---|---|---|---|
| `vix_entry_thresholds.bear_min_exclusive_and_rising` | 17.30 | 15.00 | **NO.** Only consumer in the repo: `setup/scripts/fast_path_executor.py` (a shadow "observer" lane — `mode: "observer"`, never places orders) and `crypto/lib/vix_filter.py` (crypto gym, non-edge scope, CLAUDE.md §"What I will refuse"). `fast-path-decisions.jsonl` last wrote a row **2026-05-20** — 55 days stale, effectively dead. |
| `vix_entry_thresholds.bull_max_exclusive_or_falling` | 17.20 | 20.00 | Same as above — dead lane only. |
| `vix_entry_thresholds.bull_hard_cap` | 22.00 | 30.00 | Same as above. |
| `block_elite_bull_vix_{low,high}` | **[0.0, 25.0)** | **[15.0, 18.0)** | **YES.** `backtest/lib/engine/gates.py` gate #3 of 15 (`evaluate_gates`, the ONE live entry-gate evaluation point consumed by `heartbeat_core.py` via `engine_cli`). Fires **only** on `tier=="ELITE"` + `"level_reclaim" in triggers` (Safe) / confluence (Bold) — a narrow bull sub-tier, not "all bull entries." |
| `vix_bear_hard_cap` | **23.0** | **absent** | **YES on Safe** — gate #15 of 15, blocks ALL bear entries when VIX≥23 (a ceiling, not a floor). **Bold has no key at all** — `params.get("vix_bear_hard_cap", None)` returns `None`, gate never fires on Bold. Undisclosed Safe/Bold asymmetry, flagged below (§6).

I verified this by (a) grepping every consumer of `vix_entry_thresholds` repo-wide (3 hits: a
Pydantic schema field with no logic, the dead shadow lane, and the crypto gym) and (b) reading
`backtest/lib/engine/gates.py`'s docstring, which enumerates its own 15 gates as "a faithful,
verbatim relocation... of the inline entry-gate blocks in `orchestrator.py`" — the canonical,
single source of truth for what actually gates a live tick. Zero `SKIP_VIX` actions appear
anywhere in today's 1,156-tick `core-decisions.jsonl` (grep-confirmed); every VIX-attributed block
today came from `block_elite_bull` (`SKIP_ELITE_BULL_LEVEL_RECLAIM`, 28x) — nothing else.

**This is the load-bearing correction for the queue item.** The "VIX 16.80 < 17.30 floored bear
all day" sentence describes a knob that has been dormant since 2026-05-20 and never gated the
Safe/Bold accounts that actually place orders. It should not be cited again as a live mechanism.

---

## 2. VIX regime base-rate (available history)

**Data available:** `backtest/data/vix_5m_2025-01-01_2026-07-08.csv` — 5-minute `^VIX` bars.
Coverage is NOT uniform: 2025-01-02..2026-01-01 rows are 6 bars/day (daily-close granularity
mislabeled 5m — unusable for an intraday regime read), while **2026-01-02..2026-07-08 carries true
5m density (≥60 RTH bars/day, 124 trading days)** — this is the reliable window and what the stats
below use. (A wider 2021–2023 daily VIX close series exists at
`analysis/webull-j-trades/vix_daily_2021_2023.json` but that's a disjoint market regime, not the
live gates' calibration period, and is not used here. One `forager` FRED-VIXCLS fetch attempt
found in `analysis/manager/` explicitly says *"I have simulated the data retrieval process"* —
fabricated, discarded, not used anywhere in this map.)

VIX read = first RTH bar close at/after 10:30 ET each day (proxy for "the regime during the entry
window"), n=124 days, 2026-01-02..2026-07-08:

| Band | Days | % of sample |
|---|---|---|
| `vix_entry_thresholds` bear floor 17.30 (vestigial, if it WERE live) | 41/124 | 33.1% |
| `vix_entry_thresholds` bull ceiling 17.20 (vestigial, if it WERE live) | 39/124 | 31.5% |
| **`block_elite_bull` Safe band [0,25)** (LIVE, ELITE+level_reclaim bull only) | **110/124** | **88.7%** |
| **`block_elite_bull` Bold band [15,18)** (LIVE, ELITE+confluence bull only) | **52/124** | **41.9%** |
| **`vix_bear_hard_cap` Safe ≥23** (LIVE, ALL bear) | **21/124** | **16.9%** |

VIX(10:30 ET) distribution: mean 19.34, median 18.52, min 14.85, max 29.87, std 3.62.

Today's VIX ranged **16.39–16.88 ET RTH** (core-decisions.jsonl) — inside Safe's [0,25)
`block_elite_bull` band (as are 88.7% of days) and outside Safe's ≥23 `vix_bear_hard_cap` (as are
83.1% of days, i.e. bear was **not** VIX-blocked today at the hard-gate level at all).

---

## 3. Five-account participation matrix (the real gate architecture)

CLAUDE.md's account table lists 2 (Safe-2, Risky-2/Bold); the live roster is 5 active SPY 0DTE
accounts (`automation/state/fleet/accounts.json`, `fleet-v2-grid` schema) + 1 pending
(`mes-linear-sim`, futures, out of scope) + 1 dormant. `safe-1` is retired
(2026-07-11, merged into core Safe).

**Key architecture fact** (`automation/state/fleet/build_shared_signal.py` docstring, verbatim):
*"The fleet's 'one perception' is the SAFE heartbeat's per-tick read... `bear.passed`/`bull.passed`
are derived from the production ACTION [of core:safe]... an arm can only filter production's
signal further, never enter when production held."* **The 3 `fleet_rest` arms cannot see a signal
core:safe didn't already pass.** They inherit Safe's `block_elite_bull`/`vix_bear_hard_cap`
outcome 1:1, then layer their own trigger-count selectivity (tight/loose) on top. Only `risky-3`
(the designated "probe arm") has any bypass, and it is a hash-pinned, single-verdict allowlist —
`{"SKIP_BULL_1100_1200"}` only. `block_elite_bull` is **explicitly excluded** from that allowlist
(its own SS-B revalidation is cited as the reason, §1 above) — no fleet arm ever trades around it.

| Account | Cell | Execution | VIX-gate profile | ELITE+level_reclaim BULL blocked? | ALL BEAR blocked? |
|---|---|---|---|---|---|
| **core:safe** (Gamma-Safe-2) | safe × base (control) | `mcp_heartbeat` | Safe params.json | [0,25) — 88.7% of days | VIX≥23 — 16.9% of days |
| **core:bold** (Gamma-Risky-2) | risky × base (control) | `mcp_heartbeat` | aggressive/params.json | [15,18) — 41.9% of days | **never** (no key) |
| **fleet:safe-3** | safe × tight | `fleet_rest` | inherits core:safe 1:1 + min_triggers=2 & confluence-required on top | [0,25) — 88.7% of days | VIX≥23 — 16.9% of days |
| **fleet:risky-1** | risky × tight | `fleet_rest` | inherits core:safe 1:1 + min_triggers=2 & confluence-required on top | [0,25) — 88.7% of days | VIX≥23 — 16.9% of days |
| **fleet:risky-3** | risky × loose | `fleet_rest`, probe arm | inherits core:safe 1:1 + min_triggers=1 (loosest); probe bypass = `SKIP_BULL_1100_1200` only, NOT VIX | [0,25) — 88.7% of days | VIX≥23 — 16.9% of days |

**Read:** 4 of 5 accounts share ONE VIX-gate profile (Safe's), because 3 of them structurally
cannot diverge from Safe's tick-level pass/fail. Only core:bold runs an independent, narrower
band. This is a concentration risk unrelated to today's specific dead-zone question, but material
to "what fraction of the fleet is exposed to a single gate's mis-calibration" — if Safe's
`block_elite_bull` band were ever wrong, it would silently mute 4/5 accounts at once, not 1/5.
No action recommended here (the gate is KEEP-validated, §1) — flagged for awareness only.

Today's fleet arms confirm the inheritance mechanically: `fill-funnel-2026-07-14.json` shows
`fleet:risky-1` and `fleet:risky-3` at **0 signals / 0 enter** all day (128 ticks each, same as
core), and `fleet:safe-3` at 5 signals / 0 enter — consistent with "can only get stricter than
Safe, never looser."

---

## 4. What actually blocked today (146 gate-fired blocks, zero entries, zero VIX floor)

Full breakdown from `core-decisions.jsonl` (2026-07-14, both core accounts, 1,156 ticks):

| Action | Count | VIX-related? |
|---|---|---|
| `VETOED_BY_MODELS` (free-model veto) | 37 | Indirectly — models cite VIX in their reasoning text, but it is judgment, not a coded threshold. **Already graded by A6**: veto-only accuracy 70.3%, net dollar value **+$565.50 positive today**. |
| `SKIP_ELITE_BULL_LEVEL_RECLAIM` (`block_elite_bull`) | 28 | **Yes — the one real VIX gate.** All 28 fired at VIX 16.39–16.87, both accounts. KEEP-validated (§1). |
| `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | 25 | No |
| `SKIP_STRUCTURE_VETO` | 20 | No |
| `SKIP_STALE_TRIGGER` | 12 | No |
| `SKIP_LATE_ENTRY` | 11 | No |
| `SKIP_DOJI_ENTRY_BAR` | 7 | No |
| `RISK_DENY_PDT` (execution-stage, not a gate) | 4 | No |
| `SKIP_MIN_PREMIUM_FLOOR` (execution-stage) | 2 | No |
| **Total non-HOLD blocks** | **146** | **28/146 = 19.2% attributable to a live VIX gate** |

The two "full-quality signals" the queue item names by hhmm — 10:36 BULLISH_RECLAIM (tier
**SUPER**, not ELITE) and 13:16 BEARISH_REJECTION (tier **TRENDLINE**) — were **not** touched by
`block_elite_bull` at all (that gate only fires on tier ELITE). They died to the free-model veto
(bull: 3 of 4 attempts vetoed; the 4th got a GO but was blocked downstream by
`SKIP_MIN_PREMIUM_FLOOR` at $0.24 < $0.30 floor) and PDT (bull's 5th attempt) / repeated
free-model veto (bear: every 13:16–13:40 attempt vetoed, then the setup itself stopped re-firing
as price moved off the trigger level).

---

## 5. Cost estimate

**A6 already ran the authoritative real-OPRA counterfactual replay for today's 37 veto/GO
decisions** (`analysis/free-model-audit/heartbeat-veto/2026-07-14-scorecard.md`, generated
16:20:51 ET — 1 minute before this session started). Its numbers supersede any proxy replay this
map could add:

- Veto-only accuracy today: **70.3%** (26 TRUE vetoes / 11 FALSE vetoes)
- False vetoes cost **$391.20** in foregone winners; true vetoes saved **$956.70** in avoided
  losers → **net veto value +$565.50 positive today**
- Cumulative (all-time): 68.9% correct-grade rate over 151 evidence points, **not confident**
  (bar is ≥85% over ≥15 points, sustained 3 consecutive runs — same bar as the Nemotron
  shadow-model promotion standard)

**For the ELITE-bull VIX gate specifically**, the cost estimate already exists and is 4 days old,
not something this map needs to re-derive: `block_elite_bull-ssb-revalidation.json`, n=28 elite
bull events, real-OPRA local bars replayed through the live `exit_manager` decision core (SS-B
scope) — **OLD exit shape: WR 25%, total -$560.00. SS-B (honest) exit shape: WR 28.6%, total
-$3,873.60, expectancy -$138.34/trade.** The gate is not costing money; letting the cohort trade
would cost ~7x more than the current -$560 baseline the gate already prevents. **KEEP, re-confirmed.**

**Directional sanity check on today's two headline signals** (SPY price only, no premium replay —
avoids a second OPRA pull on top of A6's): from `core-decisions.jsonl`'s own recorded `spy` field,

- 10:36 BULL entry level 752.01 → SPY chopped 750–753 the rest of the day, closing **752.30** at
  15:50 (net **+$0.29**, effectively flat). Consistent with A6's item-level replay for this exact
  tick (`+$76.20`/`+$72.60`/`+$76.80` on the ~3 attempts) — small, real, but not a "big miss."
- 13:16 BEAR entry level 751.86 → SPY **rose** to 752.6 by 14:20 (adverse to a put) before
  settling 751.9–752.3 into the close. Consistent with A6's item-level replay showing the SAFE
  put leg mostly deeply negative (-$99 to -$138) during the 13:16–13:40 veto window — the veto was
  right on this leg more often than not.

---

## 6. Follow-ups filed to `automation/overnight/queue.md`

Two items appended (§7 below): (a) retire/relabel the vestigial `vix_entry_thresholds` knob so it
stops being read as live doctrine (this map is the second time it's been mis-cited as gating —
first was this queue item itself); (b) disclose+decide the Safe/Bold `vix_bear_hard_cap` asymmetry
(Bold has zero ceiling on bear VIX exposure — not evidence this is wrong, just undocumented and
worth a one-time evidence check).

`A6-VETO-GRADE-2026-07-14` already covers the veto-layer follow-up (next-cadence flag if the
elevated false-veto rate persists) — not duplicated here.

---

## Bottom line

- **No live VIX floor blocks bear entries.** The knob the queue cited is a dormant shadow-lane
  config, not a production gate. Retire the "VIX-floored" framing.
- **The one live, wide VIX gate (`block_elite_bull`, Safe [0,25), 88.7% of days) is
  KEEP-validated** under the honest SS-B exit shape (-$3,873.60 vs -$560.00 old-shape) — it is
  saving money, re-confirmed 4 days ago, not stale evidence.
- **Today's actual zero-trade outcome was the free-model veto layer (37 blocks, not the "22" the
  queue guessed) + five unrelated structural gates (75 more blocks) + PDT/premium-floor at
  execution (6 more).** The veto layer already has same-day evidence (A6) showing it was net
  **+$565.50 positive** today, even while its cumulative accuracy (68.9%) stays below the
  confidence bar (85%) — two different, both-true facts; don't round the second into the first.
- **No re-shaping ships from this map** — nothing here clears the evidence bar for a change
  (the strongest live VIX gate KEEPs; the actual blocker is judgment-graded elsewhere with a net
  positive verdict). Per doctrine, that itself is a valid terminal state.
