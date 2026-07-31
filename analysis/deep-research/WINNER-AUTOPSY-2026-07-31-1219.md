# WINNER AUTOPSY — risky-3, 2026-07-31 12:19 ET, SPY 746C

> ## ⚠️ THIS IS AN ANECDOTE. n = 1.
> This document is a **DESCRIPTIVE forensic reconstruction of ONE trade**. It ratifies
> nothing, proposes nothing, and arms nothing. Every mechanism named below is a description
> of what the code did on this one afternoon — **not** evidence that the code is wrong.
> A single trade cannot support an exit change. Any generalizable hypothesis that falls out
> of this narrative belongs in a **pre-registered study** with a proper sample, an OOS split
> and a BH-FDR correction. Treating this page as a mandate would be the single worst
> possible use of it.
>
> **RUNNER-COHORT SANCTITY.** The runner leg examined here exited at `stage="trail"` — it is
> a *member in good standing* of the RUNNER_TRAIL cohort (35 winners, +$15,774, the book's
> entire profit engine) and it **won** (+45%). Nothing in this autopsy is an argument against
> that cohort. See §7.

**Frames used throughout.** All wall-clock times are **ET** (verified via
`setup/scripts/et_clock.py` → `2026-07-31 17:32:11 Friday EDT`; this box runs Mountain, ET =
local + 2). Broker order timestamps arrive from Alpaca in **UTC** and are converted to ET
here (16:19:03Z = 12:19:03 ET). Repo state files (`decisions.jsonl`, `core-decisions.jsonl`)
are **ET-stamped at the source**. SPY bars are **Alpaca SIP**. Option prices are **real OPRA**
— either 1-minute traded bars (`/v1beta1/options/bars`) or the **live NBBO the engine itself
read at each tick** and logged into `exit_pass` (`fleet_broker.get_option_quote_hilo`:
`best = ask`, `worst = bid`). **No synthetic/Black-Scholes prices appear anywhere in this
document.**

---

## 0. THE HEADLINE CORRECTION, BEFORE ANYTHING ELSE

**There were TWO trades on risky-3 on 2026-07-31, not one.** They have been conflated.

| | Trade A — *the one J likes* | Trade B |
|---|---|---|
| Entry | **12:19:03 ET**, 5× `SPY260731C00746000` @ **$0.33** | 13:25:05 ET, 5× `SPY260731C00747000` @ **$0.52** |
| Trigger level | 743.25 | 745.31 |
| Exits | TP1 3× @ $0.65 (12:34:04) · runner 2× @ $0.48 (12:43:03) | all 5× @ $0.36 (13:52:04) |
| Exit rule | **TP1 target**, then **chandelier trail** | **structure stop** (closed-5m break) |
| Realized | **+$126.00** | **−$80.00** |

**J asked: *"did we sell it at, like, thirteen forty five when we closed in the ribbon?"***

**Direct answer: your instinct was right about a 13:45 bar — but it was the OTHER trade, and
it was not the ribbon.**

* **Trade A's runner was gone by 12:43:03 ET** — 69 minutes before 13:52. It exited on the
  **chandelier trailing floor**, not a ribbon flip.
* **The ribbon never flipped all day during either hold.** `ribbon: "BULL"` on *every single*
  `core-decisions.jsonl` tick from 12:15:03 through 12:44:03. `make_ribbon_flip_fn` returns
  True for a CALL only when the stack reads `"BEAR"` — it returned **False at every tick**.
* The **13:45 5m bar** *is* the bar that killed **Trade B**: it closed at **745.29** (SIP), and
  the engine logged `last_closed_5m_close: 745.295` against `trigger_level: 745.31` — a
  **1.5-cent** break. `_structure_stop_hit` fired on the next fleet tick, 13:52:03.

Day P&L for the arm: **+$46.00 net** (equity 12:19 tick `$2,076.35` → 15:52 tick `$2,121.95`
= **+$45.60**; the $0.40 delta is fees).

---

## 1. WHY THE ENGINE GOT IN, AND WHY IT PICKED 746

*(Included because J asked. The `block_elite_bull` requalification and the $0.30 premium-floor
audit are other agents' lanes and are not adjudicated here.)*

**The setup fired on the core engine at 12:16:02 ET** and was **blocked there**
(`core-decisions.jsonl`, account `safe`):

```json
{"ts_et":"2026-07-31T12:16:02","account":"safe","spy":743.54,"ribbon":"BULL","htf_15m":"BULL",
 "vix":17.24,"verdict":"SKIP_ELITE_BULL_LEVEL_RECLAIM","side":"C",
 "setup":"BULLISH_RECLAIM_RIDE_THE_RIBBON","bull_score":11,"bear_score":4,
 "triggers":["level_reclaim","confluence"],"bull_blockers":[],
 "reason":"blocked by entry gate block_elite_bull",
 "bull_reclaim_level_raw":743.25,"trigger_level_exact":743.25,
 "trigger_bar_et":"2026-07-31T12:10:00-04:00",
 "shadow_triggers_fired":["wick_reclaim","pullback_hold"]}
```

* **Bull score 11/11, `bull_blockers` EMPTY** — a maximal-conviction read.
* Trigger: **reclaim of the 743.25 level** on the **12:10 5m bar** (closed 12:15), plus
  `confluence`. Two shadow detectors (`wick_reclaim`, `pullback_hold`) agreed.
* Context was *not* uniformly bullish. `context_bundle` at that tick: `daily: downtrend
  (0.867)`, `hourly: uptrend (0.800)`, `m15: downtrend (0.733)`, **`alignment_score: -1`**.
  The engine took a bull trade against a −1 multi-timeframe alignment score. It won anyway.

**Why risky-3 and nobody else.** `build_shared_signal.py` wrote the signal at **12:19:01** with
`production_action: SKIP_ELITE_BULL_LEVEL_RECLAIM`, spot 743.54
(`automation/state/logs/fleet-executor-signal-2026-07-31.python.log`). risky-3 is the only arm
configured to trade through that verdict — `accounts.json` gives it
`gate_params.hard_skip_verdicts: []` and `gate_override.min_triggers: 1`. Its own note calls it
"the live RISKY/minimum-viable-gate tier". It ticked at **12:19:02**, one second after the
signal landed.

**Why strike 746.** risky-3 is *risky* sizing → `V15_BOLD_TIERS`. Equity **$2,076.35** falls in
the `$2,000–$10,000` tier → `strike_offset = -2` (**OTM-2**). For a call,
`strike = round(spot) - strike_offset = round(743.54) + 2 = ` **746**. Pure table lookup
(`crypto/lib/strike_selection.py#pick_strike`). This was the arm's **normal** pass, not a probe
entry — a probe entry would have used `PROBE_STRIKE_TIERS` (ATM = 744).

**A coincidence worth writing down, because J independently named it.** The engine's own
`levels_active` list at that tick contained **746.30** — and **746.30 was the day's high,
printed at 09:34 ET** (it was simultaneously the OR5, OR15 *and* OR30 high; the first five
minutes made the entire morning high). The OTM-2 table picked a strike sitting **exactly at the
morning high J is asking about**. See §8.

The full log line:

```
12:19:02  ENTER_BULL  risky-3  equity 2076.35  flat=true
  reason:    "ribbon_ride C (ELITE); qty clamped 12->5: recency RED"
  risk_code: ALLOW   strike 746  prem 0.30  qty 5  trig 743.25
  placement: {"symbol":"SPY260731C00746000","mid":0.30,"entry_px":0.34,
              "tp":0.60,"tp1_premium_pct":1.0,"tp1_qty_fraction":0.667,
              "stop":0.17,"premium_stop_pct":-0.5,
              "stop_display":"STRUCTURE@743.25 (cat -50%)","stop_mode":"structure",
              "profit_lock_mode":"trailing","exit_managed":true,"placed":true}
```

Sizing note: the arm wanted **12 contracts** and was **clamped to 5** by
`_apply_recency_min_sizing` ("recency RED"). Broker fill: **5 @ $0.33**, 12:19:03.936 ET,
order `f36f386c`, `status: filled`.

---

## 2. THE CONTRACT THE ENGINE SIGNED AT ENTRY

`ExitState.from_entry` resolved this position's exit shape **once**, at entry, and never
re-evaluated it. This is the whole of what the engine was "thinking" for the next 24 minutes:

| Field | Value | Source |
|---|---|---|
| `stop_mode` | **`structure`** | `RIBBON_RIDE.exit` + `structure_stop_enabled` + a live `trigger_level` — all three required |
| `trigger_level` | **743.25** | the level the reclaim triggered off |
| `catastrophe_stop_pct` | **−0.50** → stop $0.17 | premium stop **demoted to a catastrophe cap** under v15.3 chart-stop-primary |
| `tp1_premium_pct` | **+1.00** → TP1 at ask ≥ **$0.68** | `RIBBON_RIDE` SS-B cell |
| `tp1_qty_fraction` | 0.667 → `int(5 × 0.667)` = **3** TP1, **2** runner | `exit_manager.from_entry` |
| `profit_lock_mode` | **`trailing`** (chandelier) | SS-B cell |
| `trail_pct` | **0.20** | **risky-3's `params_patch.exit_patch`** — the arm's whole reason to exist ("the intended 'rides it better' arm") vs the registry's 0.15 |
| `runner_target_pct` | **99.0** → $34.00 | SS-B cell's deliberate **"tgt-none"** |
| `profit_lock_arm_scope` | `post_tp1` (default) | pre-TP1 lock NOT armed |
| `time_stop_et` | 15:50 | fleet threads `params.time_stop_et` |
| `entry_premium` | **$0.34** | ⚠️ see the note below |

**⚠️ Fidelity note (disclosed, not adjudicated).** `ExitState.entry_premium` was seeded from
`placement.entry_px = 0.34` — the **limit price**, not the **$0.33 fill**. Proven by the logged
`RATCHET_STOP … new_stop_premium: 0.34` at TP1 (`runner_stop -> BE`). The "break-even" floor was
therefore set **3% above true break-even**, and the TP1 trigger was $0.68 instead of $0.66.
**On this trade it changed nothing** — the option never traded between 0.66 and 0.68 on any
minute bar (12:33 high 0.67, 12:34 high 0.67, 12:35 high 0.71), so TP1 fired on the same tick
either way, and the trail floor dominated the BE floor from 12:37 onward. Recorded as an
observation only.

**The runner had no reachable upside exit, by design.** `runner_target_pct = 99.0` means the
runner target was **$34.00** on a $0.33 contract. This is not a bug — the SS-B cell's comment
says so explicitly: *"runner_target 99.0 == the cell's tgt-none (runner exits via
structure/trail/EOD only)"*. From the moment TP1 filled, the runner's **only** exits were:
structure break, ribbon flip, trailing floor, or the 15:50 time stop.

---

## 3. THE HOLD, TICK BY TICK

**Cadence disclosure.** `Gamma_FleetLive` ticks risky-3 every **3 minutes**, not every minute.
Nine ticks cover the hold — **all nine are present, none missing**. The 1-minute OPRA/SIP bars
in the right-hand block below are the *real* tape between those ticks; the engine did **not**
see them. That gap is itself part of the story (§5).

Columns: `ask`/`bid` are the **real NBBO the engine read** (logged in `exit_pass`).
`HWM` is **derived** as the running max of those asks seeded at `entry_premium` — it is not
directly logged, but the derivation is **verified against two logged values**
(`runner_stop 0.552 = 0.69 × 0.80` at 12:37, and `new_stop_premium 0.34 = entry_premium` at TP1).
`unrl%` is marked off the **bid** against the **$0.33 fill** (liquidation value).
`struct dist` = `closed5m − 743.25`; positive = structure intact.

| tick ET | SPY 1m c | ask (best) | bid (worst) | unrl% | HWM | TP1? | runner stop | bid − stop | ribbon | closed 5m | struct dist | engine action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **12:19:02** | 743.30 | — | — | — | — | no | 0.17 (cat) | — | BULL | — | — | **ENTER_BULL 5× 746C, limit 0.34 → fill $0.33** |
| 12:22:03 | 743.84 | 0.41 | 0.40 | +21% | 0.41 | no | 0.170 | +0.230 | BULL | 743.30 | +0.05 | HOLD |
| 12:25:03 | 743.96 | 0.54 | 0.49 | +48% | 0.54 | no | 0.170 | +0.320 | BULL | 743.30 | +0.05 | HOLD |
| 12:28:02 | 744.13 | 0.41 | 0.40 | +21% | 0.54 | no | 0.170 | +0.230 | BULL | 744.28 | +1.03 | HOLD |
| 12:31:02 | 744.77 | 0.58 | 0.57 | +73% | 0.58 | no | 0.170 | +0.400 | BULL | 744.28 | +1.03 | HOLD |
| **12:34:02** | 744.78 | **0.69** | 0.64 | +94% | **0.69** | **YES** | 0.170→**0.340** | +0.470 | BULL | 744.38 | +1.13 | **`SELL_PARTIAL ×3 [tp1] "tp1 @ +100%"` + `RATCHET_STOP [tp1] "runner_stop->BE"` → fill 3 @ $0.65** |
| 12:37:03 | 744.63 | 0.59 | 0.58 | +76% | 0.69 | YES | 0.340→**0.552** | **+0.028** | BULL | 744.81 | +1.56 | `RATCHET_STOP [trail] "runner_stop trail/arm"` — **trail arms** |
| 12:40:04 | 744.69 | 0.58 | 0.57 | +73% | 0.69 | YES | 0.552 | **+0.018** | BULL | **MISSING** | **MISSING** | HOLD — *see below* |
| **12:43:02** | 744.26 | 0.51 | **0.50** | +52% | 0.69 | YES | 0.552 | **−0.052** | BULL | 744.535 | +1.28 | **`SELL_ALL ×2 [trail] "runner_stop @ 0.55"` → fill 2 @ $0.48** |
| 12:46:03 | 744.59 | — | — | — | — | — | — | — | BULL | — | — | flat |

**MISSING data, stated as MISSING and not interpolated.** At **12:40:04** the fleet row reads
`"reason": "no live signal"` and `exit_pass[0].last_closed_5m_close: null`. The shared signal
was stale/unreadable at that instant, so `_structure_stop_hit` received `None` and
**the structure-stop check was silently skipped on that tick** (documented fail-open:
*"False whenever either input is missing"*). It made no difference — the closed 5m bar was
745-ish, more than a dollar above the 743.25 level — but the engine was, for that one tick,
**structurally blind and trading on the trail alone.**

### The real 1-minute OPRA tape the engine could not see

```
      o     h     l     c    vol        SPY 1m
12:34 0.66  0.67  0.61  0.65  1951      744.80 / 744.81 / 744.64 / 744.78
12:35 0.66  0.71  0.63  0.69  2960      744.78 / 745.03 / 744.72 / 744.90   <-- TRUE PEAK 0.71
12:36 0.68  0.69  0.56  0.56  2060      744.90 / 744.92 / 744.53 / 744.53
12:37 0.57  0.61  0.55  0.59  1314      744.52 / 744.66 / 744.49 / 744.63
12:38 0.58  0.59  0.50  0.51  1441      744.61 / 744.63 / 744.35 / 744.44   <-- first print AT/BELOW the 0.552 floor
12:39 0.52  0.57  0.51  0.55  1360      744.42 / 744.62 / 744.40 / 744.55
12:40 0.55  0.61  0.54  0.58  1242      744.53 / 744.77 / 744.53 / 744.69
12:41 0.59  0.59  0.46  0.47  1598      744.71 / 744.71 / 744.23 / 744.25
12:42 0.46  0.51  0.42  0.50  1471      744.25 / 744.45 / 744.09 / 744.37
12:43 0.50  0.51  0.45  0.48   779      744.38 / 744.43 / 744.19 / 744.26   <-- engine fills here
```

---

## 4. THE DECISION POINTS — WHY IT HELD, IN MECHANISM TERMS

`plan_exit_actions` evaluates a **fixed, ordered** set of conditions. At each HOLD tick, *every
one of them was false*. Naming which:

### Pre-TP1 (12:22 → 12:31) — four ticks, four HOLDs

Order of checks (`exit_manager.py` lines 360-449), all evaluated against the same tick:

1. **structure stop** — `_structure_stop_hit("C", 743.25, closed_5m)` needs `close < 743.25`.
   Closed 5m closes were **743.30, 743.30, 744.28, 744.28**. Never below. Nearest: the 12:22
   and 12:25 ticks, where the closed bar sat **5 cents** above the level. *That was the closest
   this trade ever came to being stopped out.*
2. **catastrophe cap** — `worst_premium <= 0.17`. Bids were 0.40 / 0.49 / 0.40 / 0.57. Never
   close; the option never traded below $0.26 after entry.
3. **time stop** — 15:50. Not remotely.
4. **ribbon flip back** — needs stack `"BEAR"` for a call. Stack was `"BULL"` at all nine ticks.
5. **TP1** — `best_premium >= 0.68`. Asks 0.41 / 0.54 / 0.41 / 0.58. The **12:25 tick came
   closest to a premature-looking miss**: ask 0.54, while the true tape had printed **0.57** at
   12:24 — the engine's 3-minute sample landed on the pullback.

The 12:28 tick is worth flagging as texture: the ask **fell back from 0.54 to 0.41** (−24%)
while SPY was *up* 17 cents. The engine did not react, because nothing in its rule set reacts to
a drawdown that does not touch a floor. It simply held.

### TP1 (12:34:02) — the only "action" decision of the entire hold

`best_premium 0.69 >= entry 0.34 × (1 + 1.0) = 0.68` → `SELL_PARTIAL qty=3`, then
`RATCHET_STOP → BE 0.34`. The code returns immediately after TP1 — **it does not apply the trail
on the TP1 tick.** That matters: the trail only armed on the *next* tick.

### Post-TP1 (12:37, 12:40) — the two ticks it nearly died

Order flips slightly (structure → ribbon → runner target → trail floor → time stop):

| tick | structure | ribbon | runner target $34.00 | trail floor | verdict |
|---|---|---|---|---|---|
| 12:37:03 | 744.81 > 743.25 ✅ intact | BULL, no flip | ask 0.59 — unreachable by design | bid **0.58** vs floor **0.552** | HOLD by **$0.028** |
| 12:40:04 | **MISSING (skipped)** | BULL, no flip | ask 0.58 | bid **0.57** vs floor **0.552** | HOLD by **$0.018** |

**These are the moments it came closest to exiting.** For two consecutive ticks — six minutes —
the runner sat **under three cents** above its trailing floor, in a contract whose NBBO spread
was one cent. It survived on the width of a single tick of the bid.

### 12:43:02 — the exit

`worst_premium 0.50 <= new_runner_stop 0.552` → `SELL_ALL qty=2`, `stage="trail"`,
`reason="runner_stop @ 0.55"`. Order `ac400fc9`, market sell, filled **2 @ $0.48** at
12:43:03.846 ET.

---

## 5. THE HIGH-WATER MARK, AND WHAT EACH LEG KEPT OF IT

**True peak (real OPRA traded price): `$0.71`, in the 12:35:00–12:35:59 minute bar**, on 2,960
contracts of volume. SPY that minute: open 744.78, **high 745.03**, low 744.72, close 744.90 —
its high-water mark for the entire hold.

**Engine-observed HWM: `$0.69`** (NBBO ask, sampled 12:34:02). The engine's 3-minute cadence
means it **never saw the 0.71 print.**

### Capture

Peak profit per contract = `0.71 − 0.33` = **$0.38**. Peak-value ceiling on 5 lots = **$190.00**.

| Leg | Qty | Exit | Realized | % of peak *price* kept | % of peak *profit* captured | Giveback |
|---|---|---|---|---|---|---|
| **TP1** | 3 | $0.65 @ 12:34:04 | **+$96.00** (+97.0%) | **91.5%** | **84.2%** | **$18.00** |
| **Runner** | 2 | $0.48 @ 12:43:03 | **+$30.00** (+45.5%) | **67.6%** | **39.5%** | **$46.00** |
| **Total** | 5 | — | **+$126.00** | — | **66.3%** | **$64.00** |

**Had the runner simply gone out with TP1 at $0.65, it would have made $64 instead of $30.
Staying in cost this trade $34.**

### The runner's $0.23/contract giveback, decomposed exactly

| # | Component | $ / ct | Mechanism |
|---|---|---|---|
| 1 | Peak the engine never sampled | **0.020** | true traded high $0.71 (12:35) vs sampled ask HWM $0.69 (12:34:02) — the 3-minute cadence |
| 2 | The mechanical trail band | **0.138** | `floor = HWM × (1 − trail_pct)` = `0.69 × 0.80` = **0.552**. **Structural**: a chandelier cannot exit until price has already given back `trail_pct`. |
| 3 | Sampling gap at the firing tick | **0.052** | the bid was already **0.50** — 5.2¢ *under* the floor — when the 12:43:02 tick first observed it. Prints at/below 0.552 began in the **12:38** bar (low 0.50). |
| 4 | Market-order fill slippage | **0.020** | observed bid 0.50 at 12:43:02 → filled 0.48 at 12:43:03.846 |
| | **Total** | **0.230** | = $0.71 − $0.48 ✔ |

*(Caveat on row 3: a traded print at 0.50 implies the NBBO bid was ≤ 0.50 at that instant under
normal trade-through rules; historical NBBO quote replay returned HTTP 404 on this data plan, so
the engine's own tick-logged NBBO is the only quote record. Disclosed.)*

**Component 1 changed nothing.** Had the engine sampled the true 0.71, the floor would have been
`0.71 × 0.80 = 0.568` — still breached at the same 12:43:02 tick by the same 0.50 bid. Recorded
for completeness, not as a cause.

**Component 3 is the only one where the 3-minute cadence plausibly cost money, and it cost it in
an unintuitive direction:** the floor was first breached around **12:38** at a bid of ~$0.50, and
by the time the engine looked at 12:43 the bid was… also $0.50. A 1-minute cadence would have
exited at roughly the same price. **The cadence did not materially harm this exit.**

---

## 6. THE TWO EXITS — RULE, CODE PATH, LOG LINE

### Exit 1 — TP1, 3 contracts @ $0.65, 12:34:04.014 ET

**Rule: TP1 partial target.** Not a trail, not a stop, not the ribbon.

Code path — `automation/state/fleet/exit_manager.py`, pre-TP1 branch (d):

```python
tp1_level = entry * (1.0 + state.tp1_premium_pct)          # 0.34 * 2.0 = 0.68
if best_premium >= tp1_level and state.tp1_qty > 0:
    sell_n = min(state.tp1_qty, open_qty)
    actions.append(ExitAction("SELL_PARTIAL", qty=sell_n,
                              reason=f"tp1 @ +{int(state.tp1_premium_pct*100)}%", stage="tp1"))
    be = entry                                              # ratchet runner stop to BE
    new_state = replace(state, tp1_filled=True, hwm_premium=hwm,
                        runner_stop_premium=round(be, 4), profit_lock_armed=True)
```

Logged (`risky-3/decisions.jsonl`, 12:34:02):

```json
{"symbol":"SPY260731C00746000","open_qty":5,"best_premium":0.69,"worst_premium":0.64,
 "tp1_filled":true,"runner_stop":0.34,"stop_mode":"structure","trigger_level":743.25,
 "last_closed_5m_close":744.38,
 "actions":[{"kind":"SELL_PARTIAL","qty":3,"stage":"tp1","reason":"tp1 @ +100%","placed":true,
             "broker":{"id":"4455cf18-...","qty":"3","type":"market","side":"sell",
                       "position_intent":"sell_to_close"}},
            {"kind":"RATCHET_STOP","stage":"tp1","new_stop_premium":0.34,
             "reason":"runner_stop->BE","enforced":"tick_managed"}]}
```

Broker: order `4455cf18`, `filled_qty 3`, `filled_avg_price 0.65`, `filled_at
2026-07-31T16:34:04.014934Z` = **12:34:04.014 ET**.

### Exit 2 — Runner, 2 contracts @ $0.48, 12:43:03.846 ET

**Rule: chandelier trailing floor.** ✅ **NOT** a ribbon flip. ✅ **NOT** the structure stop.
✅ **NOT** the EOD flatten. ✅ **NOT** the time stop. ✅ **NOT** the catastrophe cap.

Code path — `exit_manager.py`, post-TP1 branch:

```python
if profit_lock_armed and state.profit_lock_mode == "trailing":
    trail_floor = hwm * (1.0 - state.trail_pct)             # 0.69 * (1 - 0.20) = 0.552
    new_runner_stop = max(new_runner_stop, trail_floor)
...
if worst_premium <= new_runner_stop:                        # 0.50 <= 0.552  -> TRUE
    actions.append(ExitAction("SELL_ALL", qty=open_qty,
                              reason=f"runner_stop @ {round(new_runner_stop,2)}",
                              stage="trail" if state.profit_lock_mode == "trailing" else "be_stop"))
```

Logged (12:43:02):

```json
{"symbol":"SPY260731C00746000","open_qty":2,"best_premium":0.51,"worst_premium":0.50,
 "tp1_filled":true,"runner_stop":0.552,"stop_mode":"structure","trigger_level":743.25,
 "last_closed_5m_close":744.535,
 "actions":[{"kind":"SELL_ALL","qty":2,"stage":"trail","reason":"runner_stop @ 0.55",
             "placed":true,"broker":{"id":"ac400fc9-...","qty":"2","type":"market",
                                     "side":"sell","position_intent":"sell_to_close"}}]}
```

Broker: order `ac400fc9`, `filled_qty 2`, `filled_avg_price 0.48`, `filled_at
2026-07-31T16:43:03.846536Z` = **12:43:03.846 ET**.

**The `stage` label is `"trail"` — this exit is, by the engine's own taxonomy, a
RUNNER_TRAIL exit, and a winning one.**

### For completeness — Trade B's exit, the one J may be remembering

**13:52:04 ET, 5 @ $0.36, `stage="structure_stop"`, `reason="structure_stop @ 745.31"`.**
The **13:45–13:50 5m bar closed at 745.29** (SIP) against a 745.31 trigger — a **1.5-cent**
invalidation. Code path: `_structure_stop_hit("C", 745.31, 745.295) → 745.295 < 745.31 → True`,
checked **before** the catastrophe cap per the 2026-07-09 SS-B ordering fix. That trade lost
**−$80.00**.

---

## 7. THE OBSERVATION — WHY THE RUNNER UNDERPERFORMED TP1

> *Stated as mechanism and evidence. **No fix is proposed here** — the `exit-counterfactual`
> lane owns proposals. n = 1.*

### The mechanism, in one sentence

**TP1 is a *price-target* exit that fires the instant the ASK touches a level; the runner is a
*give-back* exit that structurally cannot fire until the BID has already fallen 20% off the
high-water mark — so on any move that peaks and reverses without making a substantially higher
high, the runner is arithmetically guaranteed to realize less than TP1.**

### The arithmetic that made it inevitable

For the runner to have beaten TP1's realized $0.65, its trailing floor had to exceed $0.65:

```
floor = HWM x (1 - 0.20) > 0.65   ->   HWM > 0.8125
```

**The option needed to reach an ask of $0.8125.** Its true peak was **$0.71** — it fell
**$0.10, or 13% of premium, short** of the level at which staying in could possibly have paid.

### The moment it became inevitable

* **12:34:02** — TP1 fills at $0.65 with the HWM at $0.69. From this instant the runner is
  committed: no upside exit exists (`runner_target = $34.00`), so the only paths are a new high
  above $0.8125, or the floor.
* **12:35:59** — the peak prints at **$0.71** and the bar closes at 0.69. **This is the moment
  the divergence became determined.** The option never trades above $0.71 again while the
  position is open; every remaining path now leads to the floor.
* **12:38** — the first print at/below **$0.50** puts the bid under the 0.552 floor. **The
  outcome is now sealed**; only the engine's 3-minute cadence delays the mechanical consequence
  by five minutes.
* **12:43:02** — the engine observes it and sells.

### Three compounding structural facts, stated plainly

1. **The trail band is wide relative to this contract.** `trail_pct = 0.20` on a $0.69 contract
   is a **$0.138** band. The NBBO spread at the HWM was **$0.05 (7% of price)**. The entire
   trail tolerance was **under three spread-widths**. This is risky-3's own A/B knob — the arm
   exists *specifically* to test a **looser** trail than the registry's 0.15 ("the intended
   'rides it better' arm").

   **🚨 On this one trade, the looser trail was the worse setting — the opposite of the arm's
   design thesis.** Applying each trail width to the *same logged bids*:

   | `trail_pct` | floor off HWM 0.69 | first tick where `bid ≤ floor` | observed bid there |
   |---|---|---|---|
   | 0.125 (module default) | 0.6038 | **12:37:03** | 0.58 |
   | 0.15 (`RIBBON_RIDE` registry) | 0.5865 | **12:37:03** | 0.58 |
   | **0.20 (risky-3, LIVE)** | **0.552** | **12:43:02** | **0.50** |

   The registry's 0.15 would have exited **six minutes earlier at a bid $0.08 higher** — call it
   ~$0.09/ct after the same ~2¢ market-order slippage, i.e. roughly **+$18 on 2 contracts**.
   **n = 1. This is one trade and it proves nothing about trail width** — a trail that exits
   earlier on a peak-and-fade necessarily exits earlier on a continuation too, and the
   RUNNER_TRAIL cohort's +$15,774 was earned on continuations. Recorded because it is true and
   because it is the exact opposite of what a casual reading of "the runner gave back" would
   suggest. **Do not touch `trail_pct` on the strength of this row.**
2. **The HWM is set on the ASK; the exit is tested against the BID.** The trail is therefore
   asymmetric by one full spread before any price movement occurs at all. `get_option_quote_hilo`
   documents this deliberately: *"best (ask) drives TP1 / runner-target reach, worst (bid) drives
   the stop."*
3. **The runner had no target.** `runner_target_pct = 99.0` is the SS-B cell's certified
   "tgt-none" — the runner is *designed* to exit only on invalidation (structure / ribbon /
   trail / EOD). On a trade where the underlying held its structure the whole way, the trail was
   the *only* live exit in the set. It did exactly its job.

### What is NOT in this observation — and must not be read into it

* ❌ **"Sell all 5 at TP1."** This is **`exit-all-at-touch`**, already in the **EXIT GRAVEYARD**.
  Do not re-litigate it as new.
* ❌ **"Take profit earlier."** **`take-profit-earlier` (3 iterations)**, graveyard.
* ❌ **"Use a BE floor instead of the trail."** **`BE-floor via profit_lock_mode fixed`**,
  graveyard.
* ⚠️ **"Tighten the trail."** This trade *does* contain a signal on that axis (§7 fact 1: 0.15
  would have exited 6 min earlier at a bid $0.08 higher) — but it is **n = 1 on a peak-and-fade**,
  the exact regime a tighter trail flatters. Any move on `trail_pct` needs the full RUNNER_TRAIL
  cohort re-run with a no-regression gate. **Not actionable from this page.**
* ❌ **"The trail cohort is broken."** **This runner won.** +$30, +45.5%, `stage="trail"`. It is
  a *contributing member* of the 35-winner / +$15,774 RUNNER_TRAIL cohort that is the book's
  entire profit engine. An n=1 autopsy of a **winner** is not evidence against the mechanism
  that produced the win.

---

## 8. WHAT WE WERE SEEING — AND THE LEVEL J NAMED

J: *"what's the height of day, the start of the day, nine thirty, that would be a good take
profit, high of day in the beginning of the day or something."*

**The engine had that exact number in its hand and no rule that could use it.**

* SPY opened **744.68** at 09:30 and printed **746.301** at **09:34** — the day's high until
  13:27, and simultaneously the **OR5, OR15 and OR30** high.
* At entry, `levels_active` contained **746.30** — three levels above the entry: `744.31`,
  `744.98`, **`746.30`**, then `746.55`, `748.09`, `748.50`.
* The strike the OTM-2 table selected was **746** — the option only goes meaningfully ITM if
  SPY reclaims that morning high.
* **No exit rule in `exit_manager.py` references any level above the entry.** `stop_mode =
  "structure"` references **only this position's own entry `trigger_level` (743.25)** — i.e.
  levels are used *exclusively as downside invalidation*, never as an upside target. This is a
  **known, documented gap**, disclosed verbatim in risky-3's own `accounts.json` note:
  *"the ideal 'stop referenced to the nearest key level ABOVE the entry trigger' knob does not
  exist in ExitShape yet"* — and the `STRUCTURE-STOP-REFERENCE-LEVEL` (REF-ZONE) investigation
  closed **NO-SHIP** on 2026-07-20 (single-anchor-trade artifact, sub-window sign-flip).

### 🚨 The honest constraint this trade puts on that idea

**A 746.30 take-profit would NOT have improved this leg.** SPY's high during the entire hold was
**745.03** (12:35). It did not reach 746.301 until **13:27** — **44 minutes after the runner had
already exited**. A level-target exit at 746.30 would have required the position to *survive the
12:38–12:43 trail breach first*, which under the current rule set it could not.

So: J's instinct points at a real, documented, unbuilt capability — but **this trade is not
evidence for it**, and any pre-registration must confront that the level-target and the trail
would have been in direct conflict here.

### Hindsight tape — descriptive only, NOT a counterfactual P&L claim

*(Recorded because it is factually what happened and J will ask. It is **not** a claim that
holding was achievable: a hold path would have had to survive the 12:38 floor breach, the
13:45 structure break that killed Trade B, and the 15:50 time stop.)*

| ET | SPY | 746C (real OPRA, o/h/l/c) |
|---|---|---|
| 12:43 *(runner exits $0.48)* | 744.26 | 0.50 / 0.51 / 0.45 / 0.48 |
| 13:27 *(first touch of the 09:34 high)* | 746.40 h | 1.05 / **1.22** / 1.00 / 1.01 |
| 14:30 | 746.22 | 0.77 / 0.87 / 0.77 / 0.85 |
| 15:30 | 747.10 | 1.62 / 1.62 / 1.18 / 1.31 |
| 15:49 *(last bar before the 15:50 time stop)* | 748.50 | 2.18 / **2.50** / 2.18 / 2.50 |
| 15:54 *(SPY day high 748.895)* | 748.60 | 2.82 / **2.83** / 2.58 / 2.58 |

The 746C's **day high was $2.83**. The runner sold at **$0.48**.

---

## 9. FACTS LEDGER — everything asserted above, with its source

| Fact | Value | Source |
|---|---|---|
| Clock frame | 2026-07-31 17:32:11 EDT, market closed | `setup/scripts/et_clock.py` |
| Entry fill | 5 @ $0.33, 12:19:03.936 ET | Alpaca order `f36f386c`, `filled_avg_price 0.33` |
| TP1 fill | 3 @ $0.65, 12:34:04.014 ET | Alpaca order `4455cf18` |
| Runner fill | 2 @ $0.48, 12:43:03.846 ET | Alpaca order `ac400fc9` |
| Trade B entry/exit | 5 @ $0.52 13:25:05 / 5 @ $0.36 13:52:04 | orders `faa78137`, `2fc111bb` |
| Realized Trade A | **+$126.00** | `(0.65−0.33)×3×100 + (0.48−0.33)×2×100` |
| Arm equity delta | $2,076.35 → $2,121.95 = **+$45.60** | `risky-3/decisions.jsonl` |
| True option peak | **$0.71 @ 12:35** | real OPRA 1m bar `/v1beta1/options/bars` |
| Engine HWM | **$0.69 ask @ 12:34:02** | derived from `exit_pass`, cross-verified by `0.552 = 0.69 × 0.80` |
| Trail floor | **$0.552** | `exit_pass.runner_stop` @ 12:37, 12:40, 12:43 |
| `trail_pct` | **0.20** | `accounts.json → risky-3.params_patch.exit_patch` |
| `runner_target_pct` | **99.0** (= $34.00) | `strategies.py → RIBBON_RIDE.exit` |
| Ribbon state, whole hold | **BULL**, every tick | `core-decisions.jsonl` 12:15:03 → 12:44:03 |
| Structure never broken (Trade A) | closed 5m ≥ 743.30 vs 743.25 | `exit_pass.last_closed_5m_close` |
| Missing tick data | `last_closed_5m_close: null` @ 12:40:04 | `risky-3/decisions.jsonl`, `reason: "no live signal"` |
| Trade B invalidating bar | 13:45 5m close **745.29** vs 745.31 | Alpaca SIP 5m + `exit_pass` (745.295) |
| Day high / low | 748.895 @ 15:54 / 737.68 @ 10:16 | Alpaca SIP 1m |
| Pre-entry day high | **746.301 @ 09:34** (= OR5/OR15/OR30 high) | Alpaca SIP 1m |
| 746.30 in engine's level map | yes, `levels_active` @ 12:16:02 | `core-decisions.jsonl` |
| Strike math | `round(743.54) + 2 = 746` (OTM-2, $2K–$10K tier) | `crypto/lib/strike_selection.py#V15_BOLD_TIERS` |
| Synthetic prices used | **NONE** — all OPRA/SIP | — |

---

## 10. CANDIDATE MATERIAL FOR PRE-REGISTRATION (raw, unranked, NOT proposals)

Listed only so the pre-registration lane has this trade's raw material. **Every item requires a
proper sample, an OOS split, BH-FDR, and a RUNNER_TRAIL-cohort no-regression check before it is
anything at all.**

1. **Capture rate as a standing metric.** `realized_profit / (peak_profit × qty)` per winner,
   split TP1-leg vs runner-leg. This trade: **66.3% overall / 84.2% TP1 / 39.5% runner.** One
   trade tells us nothing; a distribution over the 35-winner cohort might.
2. **The "runner needs `HWM > realized_TP1 / (1 − trail_pct)` to beat TP1" identity.** This is
   arithmetic, not a hypothesis — but *how often* winners clear that bar is an empirical
   question the book can answer.
3. **Ask-HWM vs bid-test asymmetry.** Whether the one-spread asymmetry is material varies with
   spread/premium ratio; this contract's was 7%.
4. **Upside level-target exits.** J's idea. Constrained hard by §8: on this trade it would not
   have fired. Prior work `STRUCTURE-STOP-REFERENCE-LEVEL` / REF-ZONE closed **NO-SHIP**
   2026-07-20 — any new formulation must be materially different and must say why.
5. **Trail width on the risky-3 arm.** §7 fact 1 shows the arm's own looser 0.20 patch was the
   worse setting *on this trade*. The arm exists to A/B exactly this; the fleet paper ledger
   **is** the forward A/B. This row is one observation to add to it — **not** a reason to change
   the knob. Requires the full RUNNER_TRAIL cohort + no-regression gate.
6. **`entry_premium` seeded from limit, not fill.** A correctness observation (§2), not an edge
   idea. Immaterial here; should be verified as immaterial in general before anyone touches it
   (`fable-blast-radius` — `ExitState.from_entry` is a shared surface used by both
   `heartbeat_core` and `fleet_live`).

---

*Author: winner-autopsy lane, 2026-07-31 evening (after-hours). Market closed. No code changed,
no parameter touched, nothing ratified. Sources: `automation/state/fleet/risky-3/decisions.jsonl`,
`automation/state/core-decisions.jsonl`, `automation/state/fleet/exit_manager.py`,
`automation/state/fleet/exit_actuator.py`, `automation/state/fleet/strategies.py`,
`automation/state/fleet/accounts.json`, `automation/state/logs/fleet-executor-signal-2026-07-31.python.log`,
Alpaca paper broker orders (risky-3 / PA31WIU8X15Q), Alpaca OPRA option bars, Alpaca SIP equity bars.*
