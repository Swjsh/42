# CORE BOLD Tape Audit — 2026-07-17

_Full-tape audit of PA33W2KUAT40 ("bold" ledger account), Bold's FIRST confirmed round trip._
_Sources: `automation/state/core-decisions.jsonl` (account==bold, 386 ticks), broker orders (Alpaca
`alpaca_aggressive`, order-by-id verified), real OPRA option bars (1Min/5Min, `get_option_bars`),
`journal/2026-07-17.md`, `crypto/lib/strike_selection.py`, `automation/state/aggressive/params.json`,
`automation/state/fleet/{strategies.py,exit_manager.py,exit_actuator.py}`. READ-ONLY on config —
no params/strike_selection/heartbeat_core edits made._

**Verdict: WIN, +$191 (+9.7% day), equity $1,963.04 → $2,153.84 — crosses the $2K strike-tier
boundary.** But two premises in the brief need correcting before the rest of the analysis lands:
the $0.30 premium floor killed **zero** signals today (a different, Bold-specific gate did the
killing), and the OTM-3→OTM-2 graduation is **not** a "next session" event — `pick_strike()` reads
**live** broker equity every tick, so it was already active for any signal after 14:30 ET today.

---

## 1. Tape narrative

386 ticks, 09:30:04–15:55:04 ET. Action distribution: HOLD 351, `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`
15, `NOT_FLAT` 7 (in-position, correct), `SKIP_STALE_TRIGGER` 6, `SKIP_LATE_ENTRY` 6, `PLACED` 1.
Every trigger fired was bear-side (P) — zero bull triggers all session (ribbon BEAR/MIXED all day,
matches the premarket bias). 29 "signal" ticks (any non-HOLD verdict) = 15 fill-bar-gate skips + 14
`ENTER_BEAR` verdicts.

### Premium-floor kill count: **ZERO**

Grepped every bold row today for `PREMIUM_FLOOR` (primary path `exec.status`, extra-setup
`extra_exec[].status`, `free_eval`) — **0 hits**. `min_entry_premium=0.30` (aggressive/params.json)
never once rejected a Bold entry today, morning or afternoon. The floor didn't even come close: the
one signal that reached `_execute` priced OTM-3 743P at **mid 0.40 / filled 0.38**, comfortably
clear of 0.30.

The premise "how many did the floor kill" assumes the floor was the binding constraint. It wasn't.
The actual kill mechanisms today, in order of volume:

| Gate | Count | Morning (09:30–12:00) | Afternoon (12:00–16:00) | Note |
|---|---|---|---|---|
| `require_bearish_fill_bar` | 7 | 4 (11:06–11:09) | 3 (13:01–13:03) | Bold-only, J-ratified 2026-06-17. Blocks entry until the N+1 bar closes bearish. **Safe does NOT run this gate** (tested and REJECTED on Safe — IS_delta -$860, anchor FAIL, per `aggressive/params.json`'s `_require_bearish_fill_bar_doc`) — this is why core:safe fired at 11:06 (SPY744P x3, ACCEPTED) on the identical ELITE-tier bear=10 signal that Bold's fill-bar gate killed the same minute. |
| `require_bearish_fill_bar` (post-trade) | 8 | — | 3 (14:37, 14:49–14:50) + 5 (15:41–15:45, moot — already past ceiling) | |
| `SKIP_LATE_ENTRY` (15:00 entry ceiling) | 6 | — | 6 (15:06–15:15) | Fired AFTER the winning trade closed (14:30 ET) — see §3, these are the ones that matter for the graduation question. |
| `NOT_FLAT` | 7 | — | 7 (13:52–13:59) | Correct behavior — position already open, no new entry attempted. |
| **Premium floor** | **0** | **0** | **0** | Never the bottleneck today. |

Morning (09:30–11:06): **zero triggers of any kind.** The engine sat flat/HOLD for the first 96
minutes before the day's first bear setup even fired. First activity at 11:06:33 ET.

### Full trigger timeline (all 29 signal ticks)

| Time ET | Verdict/Gate | Triggers | bear/bull | SPY | Outcome |
|---|---|---|---|---|---|
| 11:06:33–11:09:23 (4x) | `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | level_rejection, confluence | 10/6-7 | 744.31 | Killed — fill-bar gate |
| 13:01:20–13:03:18 (3x) | `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | trendline_rejection | 7/5-6 | 746.32 | Killed — fill-bar gate |
| **13:51:21** | **`ENTER_BEAR` → PLACED** | trendline_rejection | 9/6 | 745.52 | **FILLED — the winner** |
| 13:52:17–13:59:16 (7x) | `ENTER_BEAR` → NOT_FLAT | trendline_rejection→confluence stack | 8-10/6-7 | 745.52→744.94 | Benign — already in position |
| 14:37:04, 14:49:44–14:50:24 (3x) | `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | level_rejection/trendline_rejection | 9-10/5-6 | 743.67→743.26 | Killed — fill-bar gate |
| 15:06:04–15:15:04 (6x) | `ENTER_BEAR` → SKIP_LATE_ENTRY | level_rejection/trendline_rejection | 8-10/6-7 | 743.85→743.38 | Killed — 15:00 entry ceiling |
| 15:41:04–15:45:04 (5x) | `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` | trendline_rejection | 9-10/5-6 | 742.81 | Killed — fill-bar gate (moot, already past 15:00) |

---

## 2. The winning trade — full reconstruction

**Setup:** BEARISH_REJECTION_RIDE_THE_RIBBON, `trendline_rejection`, bear 9 / bull 6, tier TRENDLINE.
**Strike:** OTM-3 per `V15_BOLD_TIERS` ($0-2K tier, offset -3): SPY 745.52 → ATM 746 → 743P.

| Leg | Time (ET) | Qty | Price | $ | Rule |
|---|---|---|---|---|---|
| ENTRY (buy_to_open) | 13:51:32 | 5 | 0.38 (limit 0.43, mid 0.40) | -$190.00 | `ENTER_BEAR` trendline tier, `require_bearish_fill_bar` cleared |
| TP1 (sell_to_close, market) | 14:27:04 | 3 | 0.85 | +$255.00 | `tp1 @ +100%` — ribbon_ride SS-B shape (`tp1_premium_pct=1.0`, `tp1_qty_fraction=0.667`; int(5×0.667)=3) |
| Runner (sell_to_close, market) | 14:30:04 | 2 | 0.63 | +$126.00 | `runner_stop @ 0.75` — 15% chandelier trail off HWM ~0.88 |
| **Total** | | | | **+$191.00** | |

All 3 broker orders verified filled via `get_order_by_id` (75bcb5fe / cac459b6 / ca96e0d0) — matches
the exit_pass ledger exactly. Structure stop (invalidation: 5m close > 745.98) never came close to
firing — SPY stayed 744.9→743.4 the whole hold. **Pure profit-taking exit, zero stop involved.**

One correction to the plan-log: `_execute`'s logged `tp: 0.70` (mid×1.75, from the generic
`params.json` display field) is **cosmetic** — the actual enforced TP1/trail shape comes from
`strategies.py`'s `ribbon_ride` (SS-B, certified 2026-07-09, `tp1_premium_pct=1.0` /
`tp1_qty_fraction=0.667` / `trail_pct=0.15` / `stop_mode=structure`). This split (tp1 in
`_execute`'s plan dict vs the shape actually registered with `exit_manager`) is pre-existing,
documented, and already reconciled in `queue.md`'s `LIVE-SHAPE-VS-CERTIFIED-SSB-DELTA` item
(closed 2026-07-15: live matches certified) — not a new bug, just worth naming so the "+100%" label
in the exit ledger doesn't read as a typo against the "0.70" plan-log field.

### Exit counterfactual (real OPRA 743P prints, same grid style as the Safe audit)

| Scenario | Mechanism | Runner treatment | Result |
|---|---|---|---|
| **(a) ACTUAL** | SS-B chandelier trail (15% off HWM) | Sold 2@0.63 at 14:30 ET | **+$191** |
| **(b) NO TRAIL — hold runner to hard time-stop** | `time_stop_et=15:40` (aggressive/params.json), TP1 split kept | 2 contracts at the 15:40 ET print (743P traded 0.53–0.83 that minute, close 0.65) | ≈ **+$195** (TP1 +$141, runner ≈+$54) — a wash, inside the bar's own noise band |
| **(c) NO TP1 SPLIT — full 5-lot rides to time-stop** | No scale-out at all | 5 contracts at the same 15:40 ET print (~0.65) | ≈ **+$135** — **worse than actual by ~$56**, because it forfeits the 0.85 TP1 print entirely |
| (d) hindsight upper bound — NOT rule-achievable | Full 5-lot held to the day's peak print | 5 contracts @ 1.08 (~15:20-15:25 ET, SPY's session low) | +$350 — flagged only because it shows real meat was on the table intraday; the chandelier had already exited by 14:30 and cannot re-arm a closed position, so this was never reachable under the actual rule set |

**Read:** SPY did keep falling into the close on net (745.6 → 742.4, -3.2pts), but not monotonically —
a hard bounce to 744.56 by 14:50 ET, a fresh session low at 742.36 (15:20 ET, premium spiked to
1.08), then another bounce to 743.97 by the 15:40-15:50 window, then a final leg down into the
close. The actual TP1+trail exit landed right at a local low (13:51 entry → 14:30 exit, premium
0.38→0.68 range) just before that 14:30-14:50 bounce would have eaten into an unhedged runner — so
(b) shows the trail neither helped nor hurt materially on THIS trade (the bounce reversed before
15:40), while (c) confirms the TP1 split itself is what made the trade — skipping it costs real
money. The (d) hindsight figure is not a criticism of the exit; a live position can't see the 15:20
low coming, and by 14:30 there was no position left to trail into it.

---

## 3. Graduation impact — the "next session" premise is wrong

**`pick_strike()` reads LIVE broker equity on every tick** (`heartbeat_core.py:1258-1261`, a fresh
`GET /v2/account` inside `_execute`, no start-of-day cache). There is no session boundary in the
tier lookup. Equity crossed $2,000 at **14:30:04 ET TODAY** (the runner fill) — any `ENTER_BEAR`/
`ENTER_BULL` verdict reaching `_execute` from that instant forward would have priced **OTM-2 (744P
at the entry's own strike math)**, not OTM-3, regardless of calendar day. "Next session picks OTM-2"
undersells it — Bold graduated intraday, mid-tape, the moment the winning trade closed.

In practice this didn't matter today: no `ENTER_BEAR`/`ENTER_BULL` verdict fired in the 14:30–15:00
ET window (the only window where equity was >$2K AND before the 15:00 ceiling). The 6 late signals
(15:06–15:15 ET) that WOULD have priced at the new tier were killed earlier in the gate ladder by
`SKIP_LATE_ENTRY` — the ledger never actually computed a strike/premium for them (`_execute` returns
before ever reaching `pick_strike` when the ceiling gate fires first). So today produced no live
OTM-2 fill to point to. But real OPRA quotes let us build the natural experiment anyway:

| Signal (ET) | SPY | OTM-3 strike/premium | OTM-2 strike/premium | Floor (0.30) clearance |
|---|---|---|---|---|
| 15:06 | 743.845 | 741P ≈ 0.13-0.14 | 742P ≈ 0.23-0.26 | **Neither clears** |
| 15:11 | 743.38 | 740P ≈ 0.09 | 741P ≈ 0.17 | **Neither clears** |
| 15:12 | 743.38 | 740P ≈ 0.11 | 741P ≈ 0.17-0.21 | **Neither clears** |
| 15:13 | 743.38 | 740P ≈ 0.12 | 741P ≈ 0.22 | **Neither clears** |
| 15:14 | 743.38 | 740P ≈ 0.12-0.14 | 741P ≈ 0.23-0.26 | **Neither clears** |
| 15:15 | 743.38 | 740P ≈ 0.15-0.17 | 741P ≈ 0.28-0.31 | **OTM-2 barely clears at the bar's close (0.31); OTM-3 does not** |

(1-minute OPRA bars, `SPY260717P00740000/741000/742000`, real trades, `n`=31-284 per bar — not
synthetic.)

**Reading:** on TODAY's actual late-session quotes, the OTM-2 graduation would have rescued **1 of
6** near-miss signals from the premium floor (15:15, and only at the bar's close, not its open) —
being one strike closer to the money is not enough by itself once spot has drifted $2-3 away from
strike this late in a 0DTE session; both tiers were mostly too cheap. This is evidence, not a
verdict on the parked ATM-vs-OTM-3 strike-axis question (that stays with J / the regime-shift
adjudication per the task's own scope fence) — it just says the floor-clearance benefit of a
one-notch tier bump is real but modest in this specific sample, consistent with
`crypto/lib/strike_selection.py`'s own docstring citing OTM-3's ~34% afternoon floor-clearance rate
from the frozen `bold-strike-axis-2026-07-15.json` study (an ATM cell clears ~97%; OTM-2 sits
between the two, and today's 6-signal sample (1/6 = 17%) is directionally consistent with that
gradient, not a contradiction of it).

**No `strike_selection.py` edits made** — this section is evidence for the record, not a change.

---

## 4. Watch item: tier-boundary flapping — NO hysteresis exists

`pick_tier()` (`crypto/lib/strike_selection.py:142-154`) is a pure `[equity_min, equity_max)`
bucket lookup with **zero memory** — no dwell time, no debounce band, no "sticky" lock once a tier
is entered. Confirmed by direct trace: `_execute` re-fetches live equity and re-calls `pick_strike`
independently on every tick that reaches it; nothing caches yesterday's or this morning's tier.
Repo-wide grep for `hysteresis` finds exactly one unrelated use (a level-touch alert debounce in
`level_alert_daemon.py`) — none on the strike-tier path. The only existing test
(`test_bold_core_strike_tier_2026_07_15.py::T9`) checks boundary **inclusivity** at exactly $2,000,
not repeated **crossing** behavior.

Bold's equity ($2,153.84) sits **7.7% above** the $2,000 line — a single average-to-bad loss
(catastrophe cap -50% on a 5-lot at ~$0.40 premium ≈ -$100, or two lesser losses) puts it back under
$2,000 and OTM-3 resumes; a second win pushes it back over. With live per-tick re-evaluation (§3),
this isn't a hypothetical multi-day drift — it can flip **within a single session**, mid-tape,
exactly like today's boundary-crossing did.

**Flagged, not implemented** (task scope: flag only). Queue item filed below.

---

## 5. Deliverables filed

- This file.
- `automation/overnight/queue.md`: `BOLD-TIER-BOUNDARY-HYSTERESIS-SPEC` (LOW, spec-only, queued below).
- `automation/overnight/STATUS.md`: one-line pointer (below).
