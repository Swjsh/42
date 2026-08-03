# EOD 2026-08-03 — LENS 2: Why every arm didn't trade + the 09:25 candle

> Written ~16:50–17:10 ET 2026-08-03 (post-close; `et_clock.py` verified 16:52:09 EDT market_hours=False).
> Data: SIP stock bars + Alpaca options 1-min bars pulled fresh this session via fleet_broker creds;
> decision ledgers `automation/state/core-decisions.jsonl` + `automation/state/fleet/*/decisions.jsonl`.
> Machine-readable twin: [`EOD-2026-08-03-PARTICIPATION.json`](EOD-2026-08-03-PARTICIPATION.json).
> Discipline: real-fills P&L is the only P&L authority; every replay number below is SIM on real
> OPRA-derived minute bars and is labeled so; n=4 replay entries = ANECDOTE.

---

## 1. Per-arm funnel — today only

Final tick counts (extends the ~14:50 established facts: cores finished 386 armed ticks/account,
fleet arms 384; "74+ elite skips" finalized at **51 armed SKIP_ELITE per core account, 102 total**
across both cores; +1/account 09:30 row where the elite verdict was stale-actioned).

| Arm | Ticks | ENTER (filled) | NO_TRIGGER | GATE_BLOCKED | NOT_FLAT | SIZING (min-premium floor) | Other |
|---|--:|--:|--:|--:|--:|--:|--:|
| **safe-2** (core) | 386 | **1** — 13:21 bollinger_squeeze 3×757C@0.53 (extra-setups route; primary lane never entered) | 329 | 51 block_elite_bull + 6 stale_trigger_bar | — (19 exit-mgmt ticks) | 0 | extra route: 53 fired tick-signals → 48 WATCH_NOT_ARMED (vwap_cont 40, gap_and_go 5, vix_dayside 3), 1 PLACED, 4 cooldown |
| **bold-2** (core) | 386 | **0** | 329 | 51 block_elite_bull + 6 stale_trigger_bar | 0 | 0 | **no extra route exists on bold** (no `extra_signals` key on any row) |
| **safe-3** (fleet) | 384 | **1** — 09:42 3×754C@0.37 | 317 (+18 no-live-signal) | 1 entry_window_09:35 (the 09:31 plan) | 14 | 33 | — |
| **risky-1** (fleet) | 384 | **1** — 09:42 5×754C@0.37 | 317 (+18) | 1 entry_window_09:35 | 12 | 35 | full-send lane: **0 fires — structurally shadowed, see §1.2** |
| **risky-3** (fleet) | 384 | **1** — 09:42 5×754C@0.38 | 317 (+18) | 1 entry_window_09:35 | 12 | 35 | probe lane: inert (elite not in probe allowlist — by design); ladder: disarmed |

### 1.1 bold-2's zero — exactly two doors, both provably shut, no third path

- **Door 1 (bull): `block_elite_bull`.** Every one of the 52 tick-minutes where a bull setup scored
  (all ELITE 11/11 `level_reclaim`+`confluence`) logged `blocked by entry gate block_elite_bull`.
  The other 334 ticks had NO scored bull setup at all (raw bull triggers appeared on 125 ticks but
  never survived scoring outside the elite verdicts).
- **Door 2 (bear): never openable.** Bear blockers on ALL 386 ticks include **#5 (ribbon/structure
  never BEAR — ribbon was BULL on all 386 bold + 386 safe armed ticks)** and **#8 (VIX floor — VIX
  15.56–16.03 all day, below the 17.3 bear floor, exactly as `today-bias.json` pre-registered:
  "bear IS VIX-blocked")**; most ticks also carried #9/#10 (no bearish breakdown/seller-pressure
  bar). Max bear score all day: 7 — never passed.
- **Third path: none exists.** Bold rows carry no `extra_signals`/`extra_exec` (the extra-setups
  route is wired on safe only), no probe lane (risky-3 only), no ladder (disarmed), no full-send
  (risky-1 only). Checked every bold row key today: zero third-path artifacts. **No tick had a
  third door bold-2 missed** — its day was fully determined by the elite gate + the VIX/ribbon
  bear wall. SHIP B opens Door 1; §3 shows what that buys and what it does NOT (the afternoon
  premium floor).

### 1.2 NEW mechanism finding — risky-1's full-send lane is shadowed by its own floor-doomed plan

`SKIP_ELITE_BULL_LEVEL_RECLAIM` **is** in `build_shared_signal.FULL_SEND_ALLOWED_VERDICTS` and
`FULL_SEND_LIVE=True`, so risky-1's full-send lane (ATM strike via `PROBE_STRIKE_TIERS`, min size)
should have rescued the afternoon elite ticks its normal OTM-2 lane lost to the $0.30 floor. It
fired **zero times**. Root cause (code-read, `fleet_executor.py`): the full-send precondition is
`if not any(p.action == "ENTER" for p in plans)` — evaluated **inside `plan_all`, before
`finalize()`** — while the `min_entry_premium` floor "lives in fleet_executor.finalize(), not in
the orchestrator" (that module's own words). On every afternoon elite tick the normal lane emitted
an ENTER plan (759C @ ~$0.07), full-send saw "an ENTER exists" and stood down, then finalize()
floor-killed the plan → net HOLD. **The rescue lane runs only when the plan list is ENTER-free,
but the verdict that empties the list lands one stage later.** L246-class ordering defect;
flagged for after-hours fix + guard (NOT fixed in this read-only session). Today's cost on
risky-1: all ~28 afternoon elite tick-signals (6 clusters) had an ATM rescue path (757C priced
$0.50+, clears the floor) that never ran.

### 1.3 The afternoon premium-floor wall — the $5K rebuild un-fixed the ATM participation fix

The fleet's 33–35 SIZING blocks/arm and core-bold's 28 replay blocks (§3) are the SAME mechanism:
at **$5,000 equity the `bold_core` strike table's $2K–$10K tier = OTM-2** (its ATM row covers only
$0–$2K). Every bold-tier arm priced afternoon elite reclaims at 758/759/760C = **$0.06–$0.18 <
$0.30 floor**. The 2026-07-17 (core Bold) and 2026-08-01/03 (fleet) ATM extensions were all
written against the $0–2K tier; **yesterday's $5K rebuild silently moved every arm off that tier
and resurrected the exact floor collision those extensions were built to kill** (C14/L234 family:
a fix scoped to a lineup that moved). Queue item filed in §5 — pre-reg an ATM extension for the
$2K–$10K tier; do NOT arm tonight.

---

## 2. The 09:25 / 749.53 forensic

### 2.1 The tape (SIP, bar-by-bar)

Premarket was flat 750.2–751.4 from 08:00 (1-min vol baseline ~6.2K shares). Then:

| ET (1-min) | O | H | L | C | Vol | Note |
|---|--:|--:|--:|--:|--:|---|
| 09:25 | 751.16 | 751.16 | 750.64 | 750.66 | 32,571 | dump starts (5× baseline) |
| 09:26 | 750.69 | 750.69 | 750.49 | 750.53 | 26,964 | |
| 09:27 | 750.51 | 750.57 | 750.25 | 750.38 | 84,262 | 14× baseline |
| 09:28 | 750.38 | 750.64 | 750.00 | 750.09 | 77,160 | |
| 09:29 | 750.10 | 750.15 | **749.33** | 749.39 | 62,480 | **premarket low = 749.33 exactly** |
| 09:30 | 749.44 | 750.30 | **748.80** | 749.75 | 658,397 | RTH open: undercut flush to 748.80, reclaim |
| 09:31–09:34 | → | → | → | 750.74 | ~857K | steady recovery |
| 09:35 (5m bar 09:30–35) | 749.44 | 751.32 | 748.80 | **750.74** | 1,515,036 | undercut-and-reclaim "spring" bar |

**J's read verified with one correction:** the dump-and-bounce is real, high-volume (5–14×
premarket baseline), and the bounce level is **749.33, not 749.53** — the tape low printed
749.33 to the cent, which is byte-identical to the 749.33 support in `today-bias.json`. The
opening candle is exactly the interesting shape J called: gap-open 749.44, flush through the
premarket low to 748.80 (tagging the 748.8 bias support), then a 1.9-point reclaim close at
750.74 on 1.5M shares.

### 2.2 What the engine saw, tick by tick (core rows, both accounts identical)

| Tick | Engine state | Why no action |
|---|---|---|
| 09:25–09:29 (premarket) | not ticking (RTH-only); **premarket bars are structurally outside the trigger frame** — the engine's 5m trigger bars are RTH bars only | the bounce bar can never be a trigger bar |
| 09:30–09:35 | last closed 5m bar = **Friday 15:50/15:55** → `SKIP_STALE_TRIGGER` ×6/account (09:30 tick even scored Friday's stale 748.5 reclaim as ELITE before the stale guard caught it) | stale-bar guard (correct behavior) |
| 09:36–09:40 | opening bar (09:30–35) scoreable: **raw `level_reclaim`+`confluence` DID fire** (`bull_triggers_raw`), bull_score 9 | **filter 1: bar_time 09:30 < 09:35 hard window** + filter 7 (bullish vol-divergence) → triggers stripped, verdict HOLD |
| 09:41 | 09:35–40 bar: ELITE 11/11 reclaim of 750.98, SPY 751.86 | cores: `block_elite_bull` (SHIP B lifts); fleet: **entered 09:42** 754C 0.37–0.38 |

**Level-map timeliness:** 749.33 was NOT in the engine's `levels_active` at the bounce (nearest
mapped: 749.46/749.65/748.5); it first appeared at the **09:44:03** tick — the intraday level
refresh learned the level ~15 minutes after the tape respected it. The engine traded the 750.98
reclaim instead; the fleet's 09:31 ENTER plan (751C @0.99 off Friday's stale 748.5 signal) was
refused by `SKIP_EARLY_ENTRY` (09:35 floor) — which, note, was the *stale* signal being refused,
not the bounce.

**Verdict on J's candle:** (i) **pre-window AND pre-frame** — the 09:25–29 bounce bar is
premarket and can never trigger; the opening bar's reclaim WAS seen raw at 09:36 but is
structurally barred by the 09:35 bar-time filter (plus vol-divergence), so the first actionable
expression of the move was the 09:41 tick → fleet fill 09:42. Between the bounce (749.33,
09:29) and first fill (751.86, 09:42) the tape moved +2.5 points.

### 2.3 The 09:35 window across prior sessions — pre-registered, NOT armed

Ledger evidence of the same first-5-minutes pattern (a fully-scored verdict existing before
09:36): fleet `SKIP_EARLY_ENTRY` placements on **2026-07-10 and 2026-08-03** (1/arm each);
core stale-actioned ELITE verdicts at the open on **2026-07-16 (4 rows), 2026-07-31 (10 rows),
2026-08-03 (2 rows)**. That is repetition across 4 distinct sessions, but thin — and today's
opening-bar reclaim was ALSO vol-divergence-blocked (filter 7), so the window was not the sole
binding constraint. Per the lens directive: **pre-registration filed in the JSON twin
(`prereg_entry_window_ab`), nothing armed.** Frozen hypothesis: admitting (a) trigger bars from
09:30 (window 09:35→09:31) and separately (b) premarket 5m bars into the trigger frame, each as
its own arm, replayed over all ledger days with ≥1 first-15-min raw trigger; gates n≥20 events,
OOS-positive, sub-window stable, drop-best no-worse; kill = negative at n≥20. Runner not built
tonight; the pre-reg freezes the question before any peeking.

---

## 3. Today under tomorrow's engine (SHIP A anchors + SHIP B elite lift + SHIP C sizing)

**Method (all SIM, labeled):** sequential one-position walk per account over the 51 armed elite
tick-signals (11 clusters), entries at the tick-minute option bar OPEN (real fills today landed
1–3s after tick), exits per the exact `exit_manager.plan_exit_actions` ordering (structure →
catastrophe → time → TP1; post-TP1 trail 15% off HWM, runner target 99× = never, time stop
15:40), fills realized at the triggering minute's CLOSE, ribbon_ride registry shape (TP1 +100%
sell 2/3, catastrophe −50%, structure stop on 5m close < trigger). Strikes per live tier tables
at $5K: **safe ATM, bold OTM-2**. Floors enforced: $0.30 min premium, 15:00 entry ceiling,
PDT≤3 (strict reading), one-position.

**Walker validated against today's 3 real fleet round-trips first** (same bars, actual limit
anchors): risky-3 err **−$0.76**, safe-3 **+$10.15**, risky-1 **−$32.76** (the live exit manager
samples point-quotes once/minute, not full bar ranges — both-sided bias, disclosed). Treat
per-trade sim numbers as ±$35.

### 3.1 The cores — what SHIP B buys (SIM, n=4 entries = ANECDOTE)

| Account | Admitted | Pre-empted (NOT_FLAT) | Blocked | Day P&L (SIM) | vs actual |
|---|---|--:|--:|--:|--:|
| **safe-2** | 3 — 09:41 752C@1.18×3 → TP1 2@2.16 (10:03) + trail 1@2.03 (10:04) = **+$281**; 11:51 756C@0.77×3 → TP1 2@1.61 (13:34) + trail 1@1.49 (13:38) = **+$240**; 13:51 757C@0.95×3 → time-stop 3@1.24 (15:40) = **+$87** | 40 | 8 (15:00 ceiling) | **+$608** | actual +$67.85 (bollinger trade — which this world PRE-EMPTS at 13:21, position open) → **+$540 delta** |
| **bold-2** | 1 — 09:41 754C@0.39×5 → TP1 3@0.81 (09:59) + trail 2@0.73 (10:00) = **+$194** | 14 | **28 SIZING min-premium (OTM-2 758/759/760C @ $0.06–0.18)** + 8 ceiling | **+$194** | actual $0 |

- The 09:41 admission is 1 minute AHEAD of the fleet's real 09:42 fills at the same signal
  (cores tick :03s, fleet lags one producer cycle) — bold's sim entry 0.39 vs fleet's real 0.37/0.38 ✓ consistent.
- **The headline inside the headline: SHIP B alone opens bold-2's MORNING only.** All six
  afternoon elite clusters stay shut behind the OTM-2/$0.30-floor wall (§1.3) — same wall that
  floor-blocked all three fleet arms 33–35× each today. Safe-2 (ATM tier) is the only account
  whose strike table could monetize the afternoon: +$327 of its +$608 comes from the 11:51 and
  13:51 clusters.
- Every one of the 51 armed elite ticks is accounted: safe 3 admitted + 40 pre-empted + 8
  ceiling-blocked; bold 1 + 14 + 36 (28 floor + 8 ceiling).
- Graveyard/no-oversell check: this is ONE bull-trend day replayed under recency logic; the
  391-day aggregate for unblocking elite-bull remains NEGATIVE (bull-gate-f5class-requal). SHIP B
  ships as TRADE-TO-LEARN with its frozen kill criterion (n≥10 fills/arm or 10 sessions,
  net<0 → re-block) — this preview is the recency case, not a validated edge.

### 3.2 The fleet — what SHIP A + SHIP C change (sim-vs-sim so walker bias cancels)

| Arm | SHIP A effect today (fill-anchor sim − limit-anchor sim) | Note |
|---|--:|---|
| safe-3 | **−$39** | fill-anchored TP1 0.74 fires 09:58 instead of riding to the lucky 0.92 spike (10:03); today the wrong anchor got PAID for its risk — the fix trades lucky-late-capture for protection. This is the same trade whose wrong anchor left it 12 minutes from the −50% cap with zero TP1 (§the known defect); on a fade day that's −$100+ of unprotected exposure. |
| risky-1 | ~$0 | TP1 target 0.615→0.555 crosses in the same minute bar |
| risky-3 | $0 | limit = fill (0.38) — no anchor error to fix |
| **risky-3 SHIP C** | **+$175.76** | qty 5→10 @0.38 (<$0.50): exact 2× of the real fills = +$351.52 day. $380 notional = 7.6% of equity, far inside Rule 6. ANECDOTE by definition (n=1 signal); the A/B is the evidence. |

SHIP A's aggregate case remains the 105-fill replay in the after-close package (TP1 mis-anchor
$4,178.50; 4/8 TP1-reaching trades delayed): a tail-risk fix, not a P&L add — today's −$39 on
safe-3 is consistent with that framing and is the honest cost of protection stated plainly.

---

## 4. Scoreboard — actual vs tomorrow-engine (SIM, anecdote-labeled)

| Arm | Actual (real fills) | Tomorrow-engine day (SIM) |
|---|--:|--:|
| safe-3 | +$144.85 | +$116 (SHIP A protection cost on the spike) |
| risky-1 | +$144.76 | +$112 (walker bias −$33 on this arm; SHIP A ≈ $0) |
| risky-3 | +$175.76 | +$351.52 (SHIP C 2×, actual-fill arithmetic) |
| safe-2 | +$67.85 | +$608 (3 elite entries; bollinger pre-empted) |
| bold-2 | $0 | +$194 (morning only; afternoon floor-walled) |
| **Total** | **+$533.22** | **~+$1,380 (SIM, n=4 new entries, one trending day — ANECDOTE)** |

---

## 5. Follow-ups filed (none armed tonight)

1. **FULL-SEND-SHADOWED-BY-FLOOR-DOOMED-PLAN** (§1.2) — fix the ordering (full-send should also
   rescue plans that finalize() floor-kills) + vary-and-assert guard; lesson-inbox candidate
   (C14/C15 family).
2. **ATM-TIER-EXTENSION-2K-10K prereg** (§1.3) — the $5K rebuild moved every bold-tier arm off
   the ATM participation fix; pre-register extending `bold_core`'s ATM row to the $2K–$10K tier
   (n≥20-fill gates, falsification = floor-block rate does not drop OR net worse than baseline).
3. **prereg_entry_window_ab** (§2.3, frozen in the JSON twin) — 09:31 window arm + premarket-frame
   arm; runner to be built after-hours; do NOT arm.
4. **Level-refresh latency** (§2.2) — 749.33 respected at 09:29, mapped at 09:44. Measure the
   premarket-low→levels_active lag across sessions before proposing anything.
