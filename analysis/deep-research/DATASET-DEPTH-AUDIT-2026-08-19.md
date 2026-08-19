# What dataset should we actually be testing on? — 2026-08-19

> J: *"research this and put the engine through a lot of tests and figure out what the dataset
> is best."* This is the dataset half. Every number below was measured this session, not recalled.

---

## VERDICT

**Our engine-replay depth is 35 trading days. It could be ~400+ for $0 on the key we already
own. That single constraint is the binding limit on every backtest claim this project makes —
and it is why "OOS" here has never meant what the word usually means.**

Second finding: the engine-stress harness runs 120 perturbations of **one seed day**. Its
limit is breadth, not run count.

---

## What we actually have

| dataset | depth | what it is good for |
|---|---|---|
| **Real fills** (`fills-ledger.jsonl`) | **303 round trips, 35 days** (2026-06-26 → 08-19) | The only win-rate authority (C1). But 5 arms share one signal at r=0.846, so this is ~60–90 independent decisions, not 303. |
| **Decision log** (`core-decisions.jsonl`) | **29,651 rows, 43 days** | Engine reasoning — scores, blockers, ribbon, VIX. Rich, but carries no outcome; must be joined to fills. |
| **SPY 5m cache** (`spy_sip_cache`) | **35 trading days** | ⚠️ **THE BOTTLENECK.** Engine replay needs this. It spans exactly the same window as our live trading. |
| SPY 1m (`highres/SPY_1m_*`) | **9 days** | Too thin to matter. (The 1,045 files in that dir are mostly per-contract option CSVs, not underlying.) |
| Option contracts (`data/options`) | **14,797 CSVs**, back to 2024-01-18 | Deep — but only usable where matching underlying bars exist. |
| OPRA 1m (`opra_1m_cache`) | 72 files, 2026-06-26 → 08-06 | Narrow slice. |

## The consequence nobody has stated plainly

**We cannot out-of-sample test the engine on any period that predates our own live trading.**
The SPY bars the replay needs start 2026-06-26 — the same day the fills start. So every
"OOS" claim in this repo is a *within-window* split of a 35-day sample that is itself one
market regime (a single VIX regime, one directional character).

That is not a reason to distrust the work done so far. It IS the reason a 390-day claim and a
35-day claim have appeared side by side in these docs and confused people: the 390-day figures
come from the **option-level** grinder, the 35-day figures from **engine replay**. Different
datasets, different questions, and they should never be quoted as if interchangeable.

## The fix is free, and it is one fetch

Verified live this session against our existing Alpaca key — `/v2/stocks/SPY/bars` served
full RTH 5m bars for every probe date:

| probe | bars returned | first close |
|---|---:|---|
| 2024-01-02 | 79 | 472.28 |
| 2025-01-02 | 79 | 590.90 |
| 2025-06-02 | 79 | 589.37 |

So **~400+ trading days of SPY 5m are one backfill away, at $0**, on the key already wired.
That takes engine replay from 35 days to a window that actually spans multiple VIX regimes,
several directional characters, and a real train/test split.

### ⚠️ The trap that must be handled, or the backfill is worse than useless

The cache stores **naive ET** timestamps (`"t": "2026-08-19T04:00:00"`). Today that is EDT
(−04:00). **Any date before the DST change is EST (−05:00).** This repo has a documented scar
here — the OPRA store is pinned at −04:00 year-round, and naive joins produced *winter
look-ahead*. A backfill that writes naive local time across a DST boundary reintroduces that
bug across ~2 years of data, silently, and every downstream backtest inherits it.

**Any backfill must go through `backtest/lib/et_frame.py` and be verified on a winter date
(e.g. 2025-01-02) against a summer date before a single file is written.**

## The stress harness has the same shape of problem

`run-engine-stress-swarm.ps1` is well built — $0, free-model evaluated, market-hours guarded
(it correctly SKIPped four times today and fired at 17:53 ET after close). But its ledger shows:

```
runs 120 | ok 120 | errors 0 | seeds: ["2026-07-23"]
```

**120 runs, one seed day.** Perturbing a single session 120 ways measures robustness *to
perturbation*, not robustness *across market conditions*. With 35 days available today (and
400 after a backfill), seeding across days is strictly more informative per run than adding
more perturbations of one day.

Its recent batches also returned **negative total P&L** (−228.2, −166.3 across 135 trades),
which is worth reading alongside the live book rather than in isolation — but on one seed day
it cannot distinguish "the engine is fragile" from "2026-07-23 was a bad day."

## Recommended order (nothing here is armed or actioned)

1. **Backfill SPY 5m to 2024-01-01**, DST-correct, verified on a winter date. Unlocks everything else. $0.
2. **Re-seed the stress swarm across days**, not one day. Same run budget, far more signal.
3. **Then, and only then**, re-run the era/OOS questions — because for the first time there would be a genuine out-of-sample period.
4. Keep quoting real fills as the WR authority (C1), and keep labelling the 303 round trips as ~60–90 independent decisions.
