# The autonomous futures lane — how it works, what it proves, what it doesn't

> Built 2026-08-09 per [FUTURES-FIRST-PLAN-2026-08-09](../planning/FUTURES-FIRST-PLAN-2026-08-09.md)
> (WS-F1 broker adapter · WS-F2 data spine · WS-F3 twin live · WS-F6 display · WS-F7 risk rails).
> Every fact below was read from live state or a fresh run during the build session, not recalled.

---

## The one-paragraph version

An autonomous MES lane now runs every 5 minutes during RTH on a **local fill simulator**,
gated by **dollar-denominated risk rails**, fed by a **live bar spine with a never-blind
staleness watchdog**, journaling every decision to `journal/futures/`. It places no real
orders and touches no broker credentials. The broker is a **swappable parameter**, so the
still-unresolved venue question stopped being a blocker instead of staying one. Fills are
**SIMULATED** — mechanism evidence, never edge evidence.

---

## Why the venue stopped being the blocker

The broker research J commissioned ([FUTURES-BROKER-RESEARCH-2026-08-09](../../analysis/deep-research/FUTURES-BROKER-RESEARCH-2026-08-09.md))
recommends **Tastytrade sandbox** as the start-this-week pick. We already have it wired:
cert account `5WW73759`, adapter `backtest/futures/tastytrade_paper.py`, order path proven
to route in July.

What actually blocked it was never really settled. On 2026-07-07 a routed order came back
`Rejected: Session offline`, which was recorded as *"the sandbox account is not provisioned
for futures"*. Re-probing the same account on 2026-08-09 returned a **different and more
specific** error:

```
tif.futures_session_not_active: The Futures trading session is not currently active.
```

That is a **market-hours** condition, not a permissions one — and the account's own
trading-status endpoint reports `is_futures_enabled: true`. Both observations are equally
consistent with "futures are fine, the session simply was not active". **So the July
diagnosis is UNCONFIRMED**, and the lane was built to not care either way.

`Gamma_FuturesBrokerProbe` (18:05 ET daily, just after the Sunday reopen) runs the identical
dry run while the session IS open and writes the answer to
`automation/state/futures/broker-probe.jsonl`:

| Hypothesis | Prediction when the session is open |
|---|---|
| **H1** account not futures-approved | dry run still fails, permissions / buying-power error |
| **H2** session-hours artifact | dry run validates, returns a buying-power effect, no errors |

A dry run is broker-side validation on a **sandbox** account: it routes nothing, fills
nothing, and cannot touch money.

---

## Architecture

```
                      futures_trader_runner.py          (Gamma_FuturesTrader, 5m RTH)
                                 │
                      futures_trader_core.run_tick()
                                 │
    ┌────────────────┬───────────┴───────────┬──────────────────┐
   SEE             DECIDE                   ACT              JOURNAL
    │                │                       │                  │
futures_live_data  should_take_v3        make_broker()    futures_journal
 (+ watchdog)      futures_risk_rails    ├─ fillsim  ◄── default, no account
                                          └─ tastytrade ◄── armed + provisioned only
```

| Module | Job |
|---|---|
| `backtest/futures/futures_session.py` | The CME session model: Sun 18:00 → Fri 17:00 ET, 17:00–18:00 maintenance break, RTH, holidays. Every "is it open" answer comes from here. |
| `backtest/futures/futures_live_data.py` | Live 5m bars (yfinance `MES=F`/`MNQ=F`) + provenance + the never-blind staleness watchdog. |
| `backtest/futures/futures_risk_rails.py` | Rules 5/6 in **dollars and points**, incl. the liquidation-distance assertion. |
| `backtest/futures/futures_trader_core.py` | The tick. Broker-agnostic see → decide → act. |
| `backtest/futures/futures_journal.py` | `journal/futures/` — trades ledger, daily log, mistakes file. |
| `backtest/futures/futures_eod.py` | The session review — tick coverage, funnel, round trips, post-hoc rule audit. |
| `backtest/futures/futures_drills.py` | Force-fire the lifecycle + replay real bars. |
| `setup/scripts/futures_trader_runner.py` | The scheduled entry point + liveness beacon. |
| `setup/scripts/futures_broker_probe.py` | Settles the H1/H2 venue question with evidence. |

---

## The data spine — and the two-month hole it closed

**The bars were stale by two months.** `backtest/data/futures/MES_5m_continuous.csv` ends
**2026-06-12**. Anything calling itself a "live futures tick" on top of that file was reading
June bars while believing it was reading the tape. That was a bigger blocker than the broker
and nothing was watching for it.

Three rules the spine enforces:

1. **The validated master is never mutated.** It is a roll-adjusted continuous series that
   existing scorecards were computed on; appending raw front-month bars to it would splice an
   unadjusted series onto an adjusted one and fabricate P&L across the seam. Live bars go to
   `MES_5m_live.csv`.
2. **Live trading reads the live file only** — not master+live concatenated. They are separated
   by a multi-week hole, and any indicator whose lookback straddles it computes across a gap it
   cannot see. yfinance serves 60 days of 5m history, deeper than any warmup this engine needs.
3. **Every append is provenance-stamped** into `automation/state/futures/data-provenance.jsonl`.

**Measured, not assumed:** `MES=F` and `ES=F` look interchangeable on a spot check (same last
close), but across 1,028 overlapping 5m bars they differ — max |close diff| **0.75 pts** (MES vs
ES) and **9.00 pts** (MNQ vs NQ). They are separate books tracking the same index. The spine
always fetches the **micro** ticker we actually trade.

**Yahoo futures quotes are DELAYED** (~10–15 min, CME licensing). Honest for bar-close decisions;
**not** a real-time execution feed. Real-time, if ever needed, is the TradingView CME add-on at
$7.00/month — the cheapest path the research found, and still net-new recurring spend that
needs J's OK.

### The watchdog
`freshness()` is session-aware by construction: staleness only means something while CME is open
and has been open long enough to print a bar. Verdicts: `GREEN` / `YELLOW` / `RED` / `BLIND` /
`CLOSED` / `WARMUP`. **Only GREEN authorizes an entry.** A watchdog that screams all weekend gets
muted, and a muted watchdog is not a watchdog.

---

## The risk rails (WS-F7)

Every rail is in **dollars and points** — a "−50% catastrophe cap" is meaningless when there is
no premium to halve. Defaults are the ones already written down for the $2K sandbox:

| Rail | Default | Why |
|---|---|---|
| `max_contracts` | **1 MES** | Plan's starting posture. Raising it is a ratification event with a scorecard, not an edit. |
| `per_trade_risk_cap` | **$100** | A full stop cannot cost more. Rule 6 analogue. |
| `session_loss_cap` | **$200** | Rule 5 analogue, evaluated against realized P&L + this trade's worst case. |
| `account_floor` | **$1,600** | −20% of $2,000. Absolute. |
| `liquidation_distance` | day margin $500/contract | **The load-bearing rail.** |
| session window | RTH only, no entry within 30m of the 17:00 ET settlement stop | Day margin reverts to overnight past the cutoff; a $2K account cannot carry it. |
| rollover | no new entry within 8 days of expiry | Liquidity leaves the front month at Rollover Thursday. |
| data freshness | GREEN only | Never-blind. |

**The liquidation-distance rail** is the one that matters most: our stop must fire *before* the
broker's margin call. Free equity above posted day margin is the cushion; if a full stop costs
more than that cushion, the broker liquidates first — at its price, plus fees.

> **Honest caveat, found by the guard tests:** under the *default* rails this rail is currently
> **shadowed** — `account_floor` ($1,600) and `per_trade_risk_cap` ($100) are strictly tighter at
> every reachable size, so they reject the dangerous combinations before liquidation distance is
> ever consulted (C15: gates interact multiplicatively). It becomes the binding constraint only at
> larger accounts or a raised per-trade cap. It is correct, tested, and currently redundant — and
> the test suite says so explicitly rather than passing vacuously.

**Fail-closed for entries, fail-open for exits.** No rail can block an exit or a flatten. A risk
system that can trap you in a position is a bigger risk than the one it manages.

Guards: `backtest/tests/test_futures_risk_rails.py` — **50 tests, RED-proofed twice** (neutering
the liquidation rail fails the suite; so does removing it from the sizing path).

---

## What has actually been proven

### Lifecycle drills — 6/6
`python -m futures.futures_drills --scenarios`

| Drill | Result |
|---|---|
| entry fill | ✅ resting limit fills on touch |
| TP1 partial | ✅ realizes 1 of 2, leaves the runner open, equity 2,000 → 2,098.76 |
| full stop | ✅ flat, −$51.24 |
| gap through stop | ✅ fills at the bar **open** (7,775), **not** the stop (7,790) — a gap must never be rewarded with the stop price |
| forced flatten | ✅ demanded 5m before the settlement stop |
| no stacking | ✅ second bracket refused |

### Replay drill — real bars, no look-ahead
`python -m futures.futures_drills --replay --days 3` → [`analysis/futures-replay-drill-2026-08-09.json`](../../analysis/futures-replay-drill-2026-08-09.json)

- **234 ticks** across 3 real RTH sessions (2026-08-05 → 08-07)
- **57 signals seen → 4 entries** (the rails rejected 3 more on sizing: stop too wide for 1 MES at the $100 cap)
- **4 placed → 4 filled → 4 TP1**, net **+$21.29** simulated on $2,000
- 0 errors

A 5-day run over the same window produced 5 trades (4 TP1 + 1 stop) at **−$2.70** — the extra
session contained the stop-out. Both numbers are **SIMULATED fills on an in-sample replay against
a filter fitted elsewhere**. They say the machinery is correct. They say **nothing** about edge.

> A bug the drills caught: `run_tick` was reading `process_quote`'s return as `{"events": [...]}`
> when it actually returns a flat `{"event": ...}` dict. The fill engine worked perfectly and the
> tick would have recorded **zero exits forever**. That is precisely what drills are for.

---

## What this is NOT evidence of

- **Not edge.** Simulated fills, in-sample replay, a filter validated on a different (roll-adjusted)
  frame than the one it is now fed. Any edge claim needs the canonical battery on its own frozen
  prereg — not this ledger.
- **Not a broker record.** `journal/futures/trades.csv` carries a mandatory `fills` column
  (`SIMULATED` / `BROKER`). Any consumer aggregating without filtering on it is producing a number
  that means nothing.
- **Not permission to size up.** 1 MES is the posture until a scorecard says otherwise.

---

## Edge #3 — exercised, not deleted (WS-F4)

The plan recorded `Gamma_FuturesEdge3Sim` as *"registered but has never run"*. **Half right, and
the half that's wrong matters:** the scheduled task genuinely has never fired
(`LastTaskResult 267011` = never run), but the **script** has — 6 closed round trips, 18 fill
events, sessions spanning 2026-07-20 → 08-06.

| Metric | Value |
|---|---|
| closed round trips | **6** of the 20 its own falsification rail requires |
| total | +$804.33 |
| mean/trade | **+$134.06** vs validated OOS **+$71.46** |
| verdict | `PENDING_MORE_DATA` (by its own frozen rail) |

**Verdict: exercise, don't delete.** It has forward evidence and a working falsification clock;
it is not deletable. It is also **nowhere near promotable** — and the mean running **1.9× the
validated OOS at n=6** is a too-good-to-be-true flag, not a green light. Re-verified this session:
runs clean, exit 0, correctly noops outside RTH. Task is `Ready`, next fire Monday 09:30 ET.

---

## The review loop — and why tick coverage leads it

`Gamma_FuturesEod2` (16:12 ET weekdays, read-only) writes `analysis/futures-eod/<date>.md`
and `automation/state/futures/eod-summary.json`.

**The headline metric is TICK COVERAGE, not P&L.** Every other number on the digest is
conditional on the engine having been awake, and a lane that quietly stops ticking otherwise
produces a *perfect-looking* review: zero trades, zero errors, zero rule breaks. So a
`DARK`/`RED` coverage verdict forces the whole digest RED and prints an explicit *"read these
as unknown, not as zero"* banner. **"No trades today" and "the engine was dead today" must
never render identically.**

This earned itself immediately: grading 2026-08-07 returns `DARK` (0/78 ticks) — correct, the
lane did not exist yet — rather than a clean zero-trade day.

| Section | What it answers |
|---|---|
| **Coverage** | Did the lane fire its ~78 scheduled ticks? `GREEN` ≥90% · `YELLOW` ≥70% · `RED` >0 · `DARK` none |
| **Funnel** | signals seen → qualified → entered, with the **rail** that rejected each drop. A lane seeing 57 signals and taking 0 is either disciplined or broken; only the breakdown tells you which |
| **Round trips** | closed trades from **one** fill class — `SIMULATED` and `BROKER` are never mixed |
| **Rule audit** | every entry re-checked **after the fact, independently of the pre-trade gate** — a bypassed or mis-wired gate is invisible to a check that only runs inside that same gate |

`eod-summary.json` is itself in the freshness manifest, so a dead *reviewer* is caught too —
otherwise the last digest pins forever and the lane looks reviewed when nobody reviewed it.

---

## Visibility (WS-F6)

J's literal question was *"where do I see the crypto gym on the dashboard"* and the honest answer
was **nowhere**. `HOME.md` now generates an **Other lanes** section:

- **Futures** — trader verdict + last tick, sim book equity/day/trade count, feed freshness per
  instrument, Edge #3 progress vs its arming bar, SSR shadow round trips.
- **Crypto** — gym scorecard verdict + per-audit YELLOW/RED breakout, twin last-journal-row liveness.

The crypto tile immediately surfaced **4 YELLOW audits** that had no surface before.

Both futures beacons are registered in `automation/state/state-freshness-manifest.json`, so the
existing monitor alarms on staleness rather than a new monitor being built:

| File | Criticality | Max age |
|---|---|---|
| `futures/trader/heartbeat.json` | high | 20 min |
| `futures/data-freshness.json` | **critical** | 20 min |

The beacon is written on **every** fire including HOLDs — that is the only way to distinguish
"quiet market" from "lane is dead". Wired day one, deliberately: the crypto twin once went dark
four days unnoticed because nothing watched a producer that only spoke when it traded.

---

## Operating it

```bash
# one tick by hand
python -m futures.futures_trader_core --tick --instrument MES

# read-only snapshot
python -m futures.futures_trader_core --status

# data
python -m futures.futures_live_data --append MES MNQ
python -m futures.futures_live_data --check MES        # exit 1 if not GREEN/CLOSED/WARMUP

# drills
python -m futures.futures_drills --scenarios
python -m futures.futures_drills --replay --days 5

# journal + review
python -m futures.futures_journal --summary --fills SIMULATED
python -m futures.futures_eod --print                    # today's session review
python -m futures.futures_eod --date 2026-08-07 --print  # any past session
```

| Task | Cadence | What |
|---|---|---|
| `Gamma_FuturesTrader` | 5 min, 09:30–16:00 ET wd | the autonomous lane |
| `Gamma_FuturesEod2` | 16:12 ET wd | the session review (tick coverage leads) |
| `Gamma_FuturesBrokerProbe` | 18:05 ET daily | settles the H1/H2 venue question |
| `Gamma_FuturesEdge3Sim` | 09:30 ET wd | MES→MNQ divergence forward clock |
| `Gamma_SsrShadow` | 15 min, 03:00–17:15 ET wd | SSR forward shadow |
| `Gamma_FuturesMirror` | daily | mirror-shadow sim spine |

**Revert:** `Unregister-ScheduledTask -TaskName "Gamma_FuturesTrader" -Confirm:$false`

---

## What still needs J

1. **Nothing to start the lane** — it runs on simulated fills today.
2. **A real venue**, only if tonight's probe returns H1 (account genuinely not futures-approved).
   Then it is J's call between the research's runner-up (**Interactive Brokers paper** via
   `ib_async`, $0.25/contract, needs a real account application) and asking Tastytrade support
   directly whether cert accounts can be futures-enabled.
3. **$7/month TradingView CME add-on** — only if delayed bars ever stop being good enough. Not
   needed for a 5-minute bar-close strategy.
4. **Live money** — out of scope entirely: OP-0 #1 *and* a new venue, double-gated.

Prop firms are **not** a path here — see [PROP-FIRM-RESEARCH-2026-08-09](../../analysis/deep-research/PROP-FIRM-RESEARCH-2026-08-09.md):
every candidate's daily-loss rule is 6–10× tighter than ours, ~1–2% of entrants ever see a payout,
and most "funded" capital is simulated anyway.
