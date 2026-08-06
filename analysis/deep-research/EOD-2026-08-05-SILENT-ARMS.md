# LENS 4 — THE SILENT ARMS: why bold-2 and safe-3 took zero legs on 2026-08-05

> Scope: Wednesday 2026-08-05. Written 2026-08-06 ~11:30 ET. **Market was OPEN while this was
> written** (`et_clock.py` → `market_hours=True`), so this lens is READ-ONLY analysis plus two
> commits of code that was *already running live*. No trading-path behaviour was changed.

---

## VERDICT

**Two silent arms, two completely different causes, and PDT is the dominant cause of neither.**

| arm | silent because | dominant blocker | PDT's actual role |
|---|---|---|---|
| **bold-2** (CORE-BOLD) | **gated silence** — it saw the trade and was refused | `FREE_MODEL_VETO` **13×** | 3× only, and all 3 fired *after* the decisive tick |
| **safe-3** (FLEET-TIGHT-S) | **signal-absent silence** — there was nothing to refuse | `ARM_GATE` **30×**, but only **1 signal in 384 ticks** | **zero** — its risk gate never fired once |

**The prime suspect is falsified for both arms.** The brief asked me to test PDT first rather than
assume it. Tested:

- **safe-3** — `risk_code` is `None` on **all 383** of its HOLD rows. The risk gate never denied
  anything, so a dead PDT gate cannot explain a silence it was never consulted about.
- **bold-2** — PDT *is* real and *did* fire, but only **3×** (11:49, 11:50, 11:55), all **after**
  the one tick that mattered. At **11:48:02**, the single tick where sibling safe-2 placed the
  put, bold-2's verdict was **`VETOED_BY_MODELS`** — the free-model entry check, not PDT.

---

## 1. The decisive tick, paired by `core_tick_id`

Both core accounts evaluate the same tick stream (386 ticks each on 08-05). Only **one** tick all
day produced a placement, and the two arms split on it:

```
11:46:02  bar=11:40  side=P | safe=VETOED_BY_MODELS   bold=VETOED_BY_MODELS
11:47:02  bar=11:40  side=P | safe=VETOED_BY_MODELS   bold=VETOED_BY_MODELS
11:48:02  bar=11:40  side=P | safe=PLACED  ←──────    bold=VETOED_BY_MODELS   ← THE FORK
11:49:02  bar=11:40  side=P | safe=VETOED_BY_MODELS   bold=RISK_DENY_PDT
11:50:03  bar=11:40  side=P | safe=VETOED_BY_MODELS   bold=RISK_DENY_PDT
11:55:04  bar=11:45  side=P | safe=VETOED_BY_MODELS   bold=RISK_DENY_PDT
```

The free-model veto is **stochastic across arms on identical input** — safe and bold got opposite
answers at 11:48 on the same bar, the same side, the same setup. That is the mechanism that
decided bold-2's entire Wednesday.

**bold-2's full 386-tick distribution:** 360 HOLD (no setup) · 13 `VETOED_BY_MODELS` ·
6 `SKIP_STALE_TRIGGER` · 4 `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` · 3 `RISK_DENY_PDT` · **0 PLACED**.

**safe-3's full 384-tick distribution:** 383 HOLD · 1 ERROR (`account fetch: 500`) · `placement.placed
= false` on all 383 · **0 PLACED**. Reasons: 351 *"no qualifying setup (no strategy fired)"*,
16 *"gate: requires confluence/sequence"*, 14 *"gate: 1 triggers < 2"*, 2 *"no live signal"*.

---

## 2. The silence is REAL, not a ledger artifact — and I nearly reported it wrong

Before trusting "zero legs" I checked for a second execution path, and **found one**.

`core-decisions.jsonl` carries an **`extra_exec`** array. A row can read `action: HOLD`,
`reason: "no setup passed scoring (neither bear nor bull)"`, `setup: None` at the top level while
nested inside `extra_exec` is a **real broker order**. That is exactly what happened to safe-2 at
10:01:

```
core_tick_id 2026-08-05T10:01:02  account=safe  action=HOLD  setup=None
  extra_exec[1] = {"setup": "vwap_reclaim_failed_break", "action": "PLACED",
                   "symbol": "SPY260805C00777000", "qty": 3, "premium": 1.6,
                   "broker": {"id": "f9366c6f-…"}}   ← a real fill at 10:01:58 @ 1.61
```

Any tool answering "did this arm trade?" from the top-level `action` field reports **safe-2 = 1
trade** when the broker shows **2**. This is L244 replayed (a monitor blind to a second execution
path). Re-counted across **both** paths:

| account | top-level PLACED | extra_exec PLACED | **TRUE total** | broker option buys |
|---|---|---|---|---|
| safe-2 | 1 | 1 | **2** | **2** ✅ reconciles |
| bold-2 | 0 | 0 | **0** | **0** ✅ silence confirmed |
| safe-3 | 0 | *(no extra_exec lane at all)* | **0** | **0** ✅ silence confirmed |

Note the structural asymmetry this exposed: **bold-2 has zero `extra_exec` rows all day.** safe-2
is evaluated against a second strategy family (`vwap_reclaim_failed_break`, `vwap_continuation`)
that bold-2 never sees. Part of "bold-2 trades less" is not a gate at all — it is a **smaller
strategy surface**.

---

## 3. What the silence cost — or SAVED

Wednesday was a **−$1,943.66** day. Pricing the counterfactual honestly, on real fills.

**Real, realised outcomes on the one contract bold-2 would have bought** (`SPY260805P00772000`):

| arm | qty | P&L | per-contract | TP1 outcome |
|---|---|---|---|---|
| risky-1 | 5 | **+$347.00** | **+$69.40** | **fired** (+50% reachable TP1) |
| risky-3 | 8 | −$664.00 | −$83.00 | never fired (+100% shape) |
| safe-2 | 3 | −$255.00 | −$85.00 | never fired (+100% shape) |

Lens 3 (`EOD-2026-08-05-PUT.md`) proved the discriminator is **TP1 reachability**, not hold-time:
the put's ask peaked **+63%/+69%**. bold-2's `tp1_premium_pct = 0.75` (**+75%**) and the ribbon
registry shape (**+100%**) are **both above that peak** — so bold-2's TP1 was unreachable *either
way*, which places it in the risky-3/safe-2 bucket, not risky-1's.

> **ORACLE BOUND (counterfactual — never mix into a live-executable column):** bold-2 taking the
> put lands at **−$83 to −$85 per contract**. At the 3–8 contract range its siblings actually
> used, that is **≈ −$249 to −$680**. bold-2's realised Wednesday was **−$0.54**.

**safe-3** has no counterfactual contract to price — its silence began upstream of side/strike
selection (1 signal all day). It ended **−$0.68** against participants' −$140.39, −$339.76 and
−$1,462.29.

**Plainly: on Wednesday, not trading was the best outcome available, and both silent arms got it.**
Framing either as a failure would be wrong.

---

## 4. The cross-day control — and why I am NOT calling this a working filter

The obvious next claim is "the gates are regime-smart." I ran the control before making it.
**On Tuesday 08-04 (+$3,617 record day), BOTH silent arms TRADED:**

| arm | Tue 08-04 | Wed 08-05 |
|---|---|---|
| bold-2 | **TRADED** — 3 filled (49 signals, 38 ENTER) | silent (20 signals, 16 ENTER, 0 filled) |
| safe-3 | **TRADED** — 5 filled (17 signals, 17 ENTER) | silent (**1 signal**, 0 ENTER) |

So the gates are **selective, not statically restrictive** — they participated on the winning day
and abstained on the losing day.

**I am explicitly refusing to sell that as an edge.** `n = 2 days`. Worse, the mechanism undercuts
the flattering story: safe-3's abstention was **upstream signal absence** (17 signals → 1), which
is the tape changing, not a gate deciding. And bold-2's abstention rests on a **stochastic
free-model veto** that gave safe-2 the opposite answer on the identical tick — a coin-flip is not
a regime filter. Suspicion scales with how good it looks (`/fable-too-good`).

**Scored prediction that came true:** the 08-04 audit wrote *"the −6% stop on a chop day — that is
the treadmill, and it is the day we have not seen yet."* Wednesday delivered it: 10 round trips on
`C00776000`, zero winners, −$1,279. That prediction is hereby marked **CORRECT**.

---

## 5. Does anything survive BOTH days?

On this lens's axis (participation/gating): **no static change survives both days.**

- Tightening entry gates to prevent Wednesday would have suppressed Tuesday's +$3,617.
- Loosening to capture more of Tuesday would have added legs to Wednesday's treadmill.
- The one thing that helped on **both** days is Lens 3's finding, not mine: **a REACHABLE TP1**.
  risky-1 was the best arm both days and both times it had fired a **+50%** TP1 first. That is an
  exit-side property, and Lens 3 already documents why it does not ship on 2-day evidence.

**Honest answer: the real lever here is regime-conditional, and I cannot prove the regime is
detectable live at entry time.** The trend-alignment tag that would be the obvious detector is
already **KILLED** with the opposite sign (`trend-alignment-correlation.md`, n=250/90 OOS, OOS
fully-aligned mean −$148.43 vs fully-fighting +$200.40, beats-null False). I am not re-picking it.

---

## 6. SHIPPED

Both items below were **already written and running live but sat UNCOMMITTED** — the highest-risk
thing I found today. Uncommitted live code is one stray `git checkout` in another lane from
silently reverting production mid-session (C34/C35). Committing changed **no** runtime behaviour
(the on-disk file was already the executing version); it removed the revert hazard.

| commit | what |
|---|---|
| `e3ec740b` | **FLEET-PDT-PARITY** — `fleet_live.py` + `test_fleet_pdt_parity.py` |
| `3ba20e09` | **per-arm silence instrument** — `fill_funnel.py` + `test_fill_funnel_why.py` |

### 6a. FLEET-PDT-PARITY (task #94) — verified live, then committed

`fleet_live.py:729-734` now routes through `pdt_tracker.fetch_day_trades_used_5d`, exactly as
`heartbeat_core.py` already did for core accounts:

```python
day_trades_legacy = int(acct.get("daytrade_count", 0) or 0)
day_trades_true, day_trades_source = _true_day_trades_5d(arm_id, creds, acct)
enforce_true = bool(params.get("fleet_pdt_enforce")) and bool(arm.get("live"))
day_trades = day_trades_true if enforce_true else day_trades_legacy
```

**Live proof (today's ledger, 08-06):** 123/123 safe-3 rows carry `day_trades_true`,
`day_trades_source = "pdt_tracker"` on 123/123, `pdt_enforced = False`.
**`day_trades_true = 6` while the legacy field reads `0`** — the dead gate is now measured. Limit
is 3, so safe-3 has been over the PDT line and structurally blind to it.

- **Log always / enforce never (default):** `fleet_pdt_enforce` absent → `enforce_true = False`.
  Visibility only. Correct, given `params.json #_pdt_gate_mode_doc` calls the margin-PDT block
  "a fictional constraint" after it killed 4 real core entries on 2026-07-14.
- **Fail-open (C7):** any fetch failure degrades to the broker field, then 0 — i.e. exactly the
  pre-fix value. An outage can never invent a new block.
- **Guard `test_fleet_pdt_parity.py`: 11/11 green.** Genuine vary-and-assert (C14) — a
  parametrized `params × live → expected` matrix proves the flag is not a dead knob, plus
  source-mirror assertions pinning the real `run()` expressions so the test cannot drift.
- ⚠️ **RED-proof deferred, and I am labelling it rather than skipping it.** A mutation RED-proof
  requires editing `fleet_live.py`, which executes every 60 s. I will not mutate a live trading
  file during RTH. **Owed after 15:55 ET.**
- **Revert:** delete the `fleet_pdt_enforce` key (today's behaviour) — or set it `true` to arm.

### 6b. The standing instrument (OP-33(e)) — J never has to ask again

`fill_funnel.py --date <day>` now closes every session with a per-arm one-liner. Real output, run
fresh this session on 08-05:

```
why each arm did / did not trade:
  core:bold CORE-BOLD (U67N)   DID NOT TRADE -- dominant cause FREE_MODEL_VETO (13x): vetoed by
    the free-model entry check; then 10x ENTRY_GATE_SKIP, 3x RISK_DENY_PDT. 360 of 386 ticks had
    no setup at all.
  core:safe CORE-SAFE (46VG)   TRADED -- 2 filled / 2 exited from 20 ENTER verdicts; also
    blocked 25x (16x FREE_MODEL_VETO, 6x ENTRY_GATE_SKIP, 3x NOT_FLAT)
  fleet:safe-3 FLEET-TIGHT-S (T20H)  DID NOT TRADE -- dominant cause ARM_GATE (30x): blocked by
    this arm's own gate_override; then 1x ERROR. 353 of 384 ticks had no setup at all.
    e.g. "gate: requires confluence/sequence" x16; "gate: 1 triggers < 2" x14
```

It is **`extra_exec`-aware** (it prints the secondary-setup line, so it cannot repeat the L244
blind-spot), **guard-tested 23/23**, **$0** (pure ledger read), and **fail-open**. Critically it
reproduced my hand-derived tick counts **exactly and independently** (13 veto / 3 PDT for bold-2;
16 + 14 = 30 arm-gate for safe-3) — two derivations, one answer.

---

## 7. OPEN / OWED

1. **RED-proof `test_fleet_pdt_parity.py` by source mutation — after 15:55 ET.** Only unproven claim here.
2. **`participation_daily.py` is still `extra_exec`-blind** (no reference to the field). `daily_brief.py`
   and `fill_funnel.py` were both fixed; this third instrument was not. It will under-report any
   `vwap_*`/`bollinger_squeeze` lane trade. Not fixed here — out of lens, flagged OPEN.
3. **The funnel self-reports `[DEGRADED]` on both 08-04 and 08-05.** Unexplained; the why-lines are
   correct, but a header saying DEGRADED on every run trains J to ignore it.
4. **safe-3's real PDT count is 6 against a limit of 3**, now visible but unenforced. Harmless on
   paper. **Must be resolved before `live:true`.**
5. **`accounts.json` lists safe-1 and safe-2 on the SAME account number `PA3POKNV46VG`.** Noticed in
   passing, not investigated. A duplicate-account guard test exists; whether it covers this is unchecked.
6. **6× `SKIP_STALE_TRIGGER` at 09:30–09:35** on bars stamped `15:50`/`15:55` — the *previous*
   session's closing bars leaking into the open. It skipped correctly, so this is cosmetic-but-smelly.

---

## Provenance

- Broker fills: `automation/state/fills-ledger.jsonl` (real Alpaca activities; 14 option buys on
  08-05 — risky-1 ×6, risky-3 ×6, safe-2 ×2, **bold-2 ×0, safe-3 ×0**). Every P&L above is real
  fills, not simulation.
- Decisions: `automation/state/core-decisions.jsonl` (772 strict 08-05 rows, filtered on
  `core_tick_id`, **not** substring — a substring filter pulls in 08-06 rows and inflates counts);
  `automation/state/fleet/safe-3/decisions.jsonl` (384 strict rows).
- Sibling lens cited, not re-derived: `EOD-2026-08-05-PUT.md` (TP1 reachability; it also **corrected
  the brief's premise** that risky-3 had a +40% TP1 at 2.31 — that shape belongs to
  `vwap_continuation`, its ribbon shape was +100%, so no 2.31 target ever existed).
- `n = 2 days` on every cross-day claim. Nothing here is population evidence.
