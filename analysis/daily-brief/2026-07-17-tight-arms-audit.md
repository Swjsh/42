# Tight-arm audit — why safe-3 and risky-1 didn't mirror the 13:01/13:51 winners — 2026-07-17

> J: "I would have expected 3 safe and/or 3 bold take the same trade." Scope: safe-3 (safe x
> tight) and risky-1 (risky x tight) vs core Safe (4 engine trades) / core Bold (1 engine trade)
> / risky-3 (loose gate, +$248). Coordinates with `2026-07-17-fleet-attribution-audit.md` (the
> risky-3 "+$248/zero-ENTER" visibility-layer bug — unrelated root cause, same day's data;
> pnl-statement.json numbers below are cross-checked against and agree with that audit's fill
> IDs, with one correction noted in §3).

## 1. VERDICT FIRST

**Both misses trace to the tight arms' own `gate_override` (`min_triggers: 2` +
`require_confluence_or_sequence: true`) doing exactly what it was designed to do — both
winning signals fired on a single trigger (`trendline_rejection`, no confluence/sequence tag).
That is not a bug; it is the tight cell's whole reason to exist.** But the accumulated evidence
on whether that selectivity has *earned* its keep just changed materially: the 07-16 redesign's
blocked-cohort sample was 0-for-4, -$85 (net loss) through 07-15. Today adds the first clean,
apples-to-apples comparable since then — risky-3 (identical signal, loose gate) filled the
13:51 signal and banked **+$233** on it alone. Extended sample: **n=5, 1-for-5 by count, but
net +$148** (flips the sign from the 07-16 report's headline number). n=5 is nowhere near a
ship bar (the redesign's own multi-testing floor is n≥30), so **nothing changes tonight** —
but "REFUTED, don't re-propose" is now stale language; filed a pre-reg extending the re-test
(§5) instead of either shipping the loosen or re-closing the question.

Separately: the *first* signal (13:01) is **not** a clean tight-gate attribution — risky-3's
own gate passed it fine but the trade died downstream to `SKIP_MIN_PREMIUM_FLOOR` ($0.23 <
$0.30) at the fleet's shared OTM-3 strike table, which safe-3 and risky-1 also use. Had the
tight gate let it through, the same premium floor almost certainly kills it too. Recency-RED
sizing clamp: confirmed live (any_red=true) but had **zero effect** on either arm today —
their sub-$2K equity tier already sizes at `min_contracts`, so the clamp is a structural no-op
at this account size regardless of RED/YELLOW/GREEN.

---

## 2. Signal trace — walked through the actual pipeline, not theory

### 2a. What the core ledger recorded (`automation/state/core-decisions.jsonl`, ground truth)

| Time (ET) | Account | Verdict | Triggers | Score (bear/bull) | Notes |
|---|---|---|---|---|---|
| 13:01:03 | safe | `ENTER_BEAR` **PLACED** | `['trendline_rejection']` (1) | 7/5 | Core Safe's 746P win, +$241 per J's brief |
| 13:01:20 | bold | `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | `['trendline_rejection']` (1) | 7/5 | Hard C14 skip — bold's own entry blocked here, unrelated to fleet gates |
| 13:51:03 | safe | `ENTER_BEAR` (NOT_FLAT — core Safe already held the 13:01 position) | `['trendline_rejection']` (1) | 9/6 | Brain's verdict still ENTER_BEAR; execution skipped only because core-Safe's OWN account was occupied |
| 13:51:21 | bold | `ENTER_BEAR` **PLACED** | `['trendline_rejection']` (1) | 9/6 | Core Bold's 743P win, +$191 per J's brief |

Both winning signals: **exactly one trigger, no confluence/sequence tag.** This is the load-bearing fact for everything below.

### 2b. How `build_shared_signal.py` turns that into the fleet's ONE shared `strategies[]` list

`fleet_executor.plan_all` runs the FIX2 path (`EMIT_STRATEGIES=True` default) — when
`signal['strategies']` is present, **every fleet arm reads the identical, single, per-tick
list**; the older per-arm safe/bold perception routing (`_perception_for_arm`) is bypassed
entirely for this path. `build()`'s own logic (`build_shared_signal.py:538-548`) picks which
ledger perception feeds that shared list:

```
s_bear, s_bull = bear, bull                      # default: SAFE-perception (top-level)
if use_peak:
    bold = sig.get("bold") or {}
    if bold.bear.passed or bold.bull.passed:
        s_bear, s_bull = bold.bear, bold.bull    # BOLD-perception wins if IT passed
```

- **At 13:01**: bold's ledger row was the hard-skip verdict → `passed_scoring_peak` returns
  `False` for a `_HARD_SKIP_VERDICTS` action regardless of score/trigger
  (`build_shared_signal.py:585-590`) → bold block did not pass → falls back to the SAFE block,
  which DID pass (core Safe's own `ENTER_BEAR`). `strategies[]` this tick = one `ribbon_ride P`
  entry, `triggers=['trendline_rejection']`, `quality=BASE`.
- **At 13:51**: bold's ledger row IS `ENTER_BEAR` → bold block passes →
  `strategies[]` this tick is built from the BOLD block instead, same
  `triggers=['trendline_rejection']`, `quality=BASE`.

Either way, **both safe-3 and risky-1 see the identical single-trigger `strategies[]` entry**
on both ticks — confirmed live, not just by code reading (§2c).

### 2c. `_gate_check` — the block, confirmed against the real decision rows

`fleet_executor._gate_check` (called from `_plan_from_strategies` before strike/premium are
even computed):

```python
min_trig = g.get("min_triggers")                     # 2 for safe-3 AND risky-1
if len(triggers) < int(min_trig): return f"{len(triggers)} triggers < {min_trig}"
elite = _is_elite(blk)                                # confluence flag OR sequence_* trigger
if g.get("require_confluence_or_sequence") and not elite: return "requires confluence/sequence"
```

A lone `trendline_rejection` trigger fails **both** conditions independently. Live proof —
`automation/state/fleet/{safe-3,risky-1}/decisions.jsonl`, byte-identical rows for both arms:

| Time (ET) | Arm | Reason (verbatim) |
|---|---|---|
| 13:04:02 | safe-3 | `gate: 1 triggers < 2` |
| 13:04:02 | risky-1 | `gate: 1 triggers < 2` |
| 13:52:02 | safe-3 | `gate: 1 triggers < 2` |
| 13:52:02 | risky-1 | `gate: 1 triggers < 2` |
| 13:55:02 | safe-3 | `gate: 1 triggers < 2` |
| 13:55:02 | risky-1 | `gate: 1 triggers < 2` |

These are the *only* 3 `gate:`-prefixed HOLDs either arm logged all day — one for the 13:01
signal's tick, two for the 13:51 signal's (it stayed live 2 ticks before the ELITE 4-trigger
confluence version fired at 13:56/13:58, which BOTH arms correctly entered — see §4).

### 2d. Would loosening have actually captured the trade? Discriminated per signal

`risky-3` (loose gate, `min_triggers=1`) shares safe-3/risky-1's **same** OTM-3 strike table
(`strike_tier_table` resolves to `"bold"` for all three fleet_rest arms — safe-3 via explicit
`params_patch`, risky-1/risky-3 via `config_source: "inherit bold"`), so it is the correct
counterfactual for "what would the tight arms have gotten if their gate had passed."

- **13:01 signal**: risky-3's gate passed (min_triggers=1 clears a lone trigger) but the trade
  died at 13:04 to `risk_code: SKIP_MIN_PREMIUM_FLOOR`, `reason: "premium 0.23 < min_entry_premium
  floor 0.3"`, strike 743 (`fleet/risky-3/decisions.jsonl`, verbatim row). Since safe-3/risky-1
  price the same OTM-3 strike off the same table, they would very likely have hit the identical
  floor had the gate let them through — **the tight gate is not cleanly the binding constraint
  for this miss.**
- **13:51 signal**: risky-3's gate passed AND the premium cleared the floor — `ENTER_BEAR` 743P
  @ $0.39-0.41, qty 5, `quality=BASE`, at 13:52:02/13:52:03 (fleet log vs pnl-statement.json
  show $0.39-0.41 for the same fill; using pnl-statement.json's broker-truth $0.39 below). This
  is a **clean, comparable miss**: same strike, same timing window, same account family — the
  ONLY thing that differed from safe-3/risky-1 was the gate.

---

## 3. Precise fills — `automation/state/pnl-statement.json` (broker-truth `round_trips`, cross-checked against `journal/trades.csv`)

| Arm | Symbol | Qty | Entry | Exit | P&L | Entry->Exit (ET) |
|---|---|---|---|---|---|---|
| safe-3 | 741P | 1+2 | 0.48 | 0.48 | **$0.00** | 11:07:04 -> 11:13:02 (structure_stop) |
| safe-3 | 742P | 3 | 0.33 | 0.33 | **$0.00** | 13:58:03 -> 15:40:03 (time_stop_15:50) |
| risky-1 | 741P | 5 | 0.48 | 0.48 | **$0.00** | 11:07:05 -> 11:13:03 (structure_stop) |
| risky-1 | 742P | 5 | 0.33 | 0.33 | **$0.00** | 13:58:04 -> 15:40:04 (time_stop_15:50) |
| risky-3 | 741P | 2+3 | 0.46 | 0.49 | +$15.00 | 11:07:06 -> 11:13:03 (structure_stop) |
| risky-3 | 743P | 3 | 0.39 | 0.98 | +$177.00 | 13:52:03 -> 15:16:04 (tp1) |
| risky-3 | 743P | 2 | 0.39 | 0.67 | +$56.00 | 13:52:03 -> 15:28:04 (trail) |

**safe-3 net: $0.00. risky-1 net: $0.00. risky-3 net: +$248.00** — matches the daily-brief
QUANT block (`analysis/daily-brief/2026-07-17.md`) and `2026-07-17-fleet-attribution-audit.md`'s
own fill-ID reconciliation exactly, **with one correction**: that audit's prose states safe-3's
741P leg entered "@0.45" for "+$9" net across its two trades (~+$18 total). `pnl-statement.json`
(the file both reports cite as source) and `journal/trades.csv` (`notes` field: *"Source:
pnl-statement.json (T1 broker-truth round_trips)"*) both independently show entry=exit=$0.48 on
that leg, **$0.00**, not +$9 — the earlier audit appears to have read a decision-time quoted
premium (fleet log's `ENTER` row shows an *estimated* 0.45) rather than the broker-confirmed
round-trip. safe-3's honest net today is **$0.00, not ~+$18**. (risky-1 and risky-3 numbers in
that audit already matched exactly; only the one safe-3 figure is corrected here.)

**"Their 4 zero-net fills each"**: 2 entries + 2 exits = 4 fills per arm, both trades scratched
at literally identical entry/exit premium (real mechanical stops, not synthetic/rehearsal —
confirmed present in `trade-today.json`'s real `fills[]` array, not `rehearsal_probes[]`).

---

## 4. Recency-RED clamp — item 2

`automation/state/recency-confirmation.json`: `headline.any_red: true` →
`fleet_executor._recency_verdict()` reads **RED**. `recency_min_size_enabled: true` in both
`automation/state/params.json` and `aggressive/params.json` — **the gate is live, not
dormant.** But `grep`-ing every fleet-arm `decisions.jsonl` for today's `"clamp"` mentions
returns **zero matches** for safe-3/risky-1/risky-3 — the clamp never fired for any of them.

Why: `_apply_recency_min_sizing` only *shrinks* qty (`min(qty, min_contracts)`), and at these
arms' sub-$2,000 equity, `position_sizing_tiers`' own $0-2,000 row already sets `elite_qty ==
min_contracts` (safe: 3==3; bold-table: 5==5 — bold's $0-2,000 row doesn't even upsize on
ELITE). The clamp is a structural no-op at this account size regardless of the recency verdict
— **not** a second, independent suppressor of today's misses. Worth flagging forward: once
these arms cross the $2,000 equity tier (elite_qty jumps to 8/12), the RED clamp will start
actually biting — today it simply never got the chance to.

---

## 5. Extended blocked-cohort ledger + verdict

| Source | n | Record | Net P&L |
|---|---|---|---|
| 07-16 redesign (`SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md` §2, safe-3 row) | 4 | 0-for-4 | -$85.00 |
| 2026-07-17 (this audit, 13:51 signal only — 13:01 excluded, no comparable fill) | 1 | 1-for-1 | +$233.00 |
| **Extended total** | **5** | **1-for-5 (20%)** | **+$148.00** |

The sign flips, but n=5 is still far below even the *original* OP-11 floor (≥15), let alone the
07-16 redesign's own tightened multi-testing floor (≥30) for anything reopened by this pivot.
**Verdict: genuinely open, not shippable either direction tonight.** Per the task instruction,
nothing is flipped. Filed:

- **Pre-reg**: `analysis/recommendations/safe3-risky1-gate-retest-preregistration.json` — freezes
  the cohort definition (any tick where a fleet_rest tight arm's `_gate_check` returns
  `"... triggers < min_triggers"` or `"requires confluence/sequence"` AND a same-strike-table
  loose/probe sibling (risky-3) fills the identical signal) and the pass bar (n≥30,
  `risky-3`-mirrored realized P&L, before any `gate_override` change ships) so the next
  qualifying fill anywhere in the fleet auto-accretes evidence without re-litigating scope.
- **Queue item**: `automation/overnight/queue.md` — `SAFE3-RISKY1-GATE-RETEST-EXTEND` (this
  week, needs-pre-reg category, references the pre-reg above).
- **Secondary, distinct lever flagged (not pre-reg'd, just noted)**: safe-3 and risky-1 share
  risky-3's OTM-3 strike-table premium-floor exposure (the §5 THIS WEEK item #2 in the 07-16
  redesign, "nearer strike table for risky-3") — today's 13:01 miss shows that exposure isn't
  risky-3-only, it applies to all three fleet_rest arms alike. Worth folding into that existing
  item's scope rather than opening a new one.

---

**Files referenced**: `automation/state/core-decisions.jsonl`, `automation/state/fleet/accounts.json`,
`automation/state/fleet/build_shared_signal.py`, `automation/state/fleet/fleet_executor.py`,
`automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl`,
`automation/state/pnl-statement.json`, `journal/trades.csv`,
`automation/state/recency-confirmation.json`, `automation/state/params.json`,
`automation/state/aggressive/params.json`,
`markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md`,
`analysis/daily-brief/2026-07-17.md`, `analysis/daily-brief/2026-07-17-fleet-attribution-audit.md`.
