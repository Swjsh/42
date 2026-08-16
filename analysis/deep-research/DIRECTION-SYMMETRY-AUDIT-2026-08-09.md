# DIRECTION SYMMETRY AUDIT — 2026-08-09

**Verdict: RED. Every asymmetric numeric knob in the live config makes CALLS harder to enter than PUTS — four of four. And 24 params `_doc` entries describe knobs that do not exist as live keys, including the one that made me misreport the VIX picture to J twice in an hour.**

Instrument: [`direction_symmetry_audit.py`](../../setup/scripts/direction_symmetry_audit.py) → `automation/state/direction-symmetry.json`. Reads the existing 23-gate registry + both live params files + `gate_expiry_check`'s own verdicts. No new registry, no network, no LLM, $0.

## Why it exists

J, 2026-08-09: *"i dont understand the gripe witth 'calls' vs PUTS, you're very keen on bear setups. we need to play both sides of the market, period."*

He was right, and the reason it went unnoticed is structural: the asymmetry is not in any one place. It is a trigger count here, a macro threshold there, a stop width somewhere else — **each individually ratified with its own passing scorecard.** Nobody ever summed them and asked what the *total* entry bar is for a call versus a put. This makes that a nightly traffic light instead of something J has to catch in prose.

This is not a new preference. It is ratified doctrine — **OP-16: "direction is NOT a scope, validation is."**

## Finding 1 — the entry bar is uniformly harder for calls

| account | knob | bull | bear | effect |
|---|---|--:|--:|---|
| safe | `filter_10_min_triggers` | **2** | **1** | a call needs **twice** the triggers |
| safe | `macro_soft_threshold` | **10** | **7** | a call needs a higher macro score |
| bold | `macro_soft_threshold` | **10** | **7** | same on Bold |
| bold | `premium_stop_pct` | **−0.05** | **−0.07** | a call is **stopped out sooner** |

**Four of four disfavour bull.** Not one knob anywhere makes a put harder to take or hold.

**The nuance that keeps this honest:** by *gate count* bear actually carries more direction-specific gates (3 armed vs bull's 1) — `vix_bear_hard_cap`, `require_bearish_fill_bar`, and a third. So the bias is not "more rules against bull". It is that **bull's constraints sit on the entry-quality axis (how good a setup must be), while bear's sit on regime/confirmation axes (when and how to confirm).** A higher quality bar compounds against volume in a way a confirmation bar does not.

## Finding 2 — four direction-specific gates run on stale evidence

`block_bull_1100_1200`, `block_level_rejection`, `entry_bar_body_pct_min`, `vix_bear_hard_cap` — all four have **no opposite-side twin** and **evidence older than 45 days**.

The weakest is `block_bull_1100_1200`: a standing bull-only time veto ratified 2026-06-18 on **n=11, −$89**. Eleven trades, eighty-nine dollars, two months ago, still refusing every call in an hour of every session. Under J's own standing directive (*recency > aggregate; every armed gate needs a revalidation clock*), that is exactly the profile that should have expired.

Corroborating precedent: the one bull gate that *did* get a revalidation clock — `block_elite_bull` — came back **RED**, its refused cohort worth **+$1,841 over 17 days**, and is currently lifted on a trial. The gate that got measured turned out to be costing money.

## Finding 3 — 24 phantom documented knobs

A `_<key>_doc` whose `<key>` is absent from live params. These read exactly like config to anyone auditing `params.json` — human or model — and cannot fire.

The one that bit: **`_vix_bull_hard_cap_doc`** describes, in convincing scorecard-citing detail, a gate that *"blocks all CALL entries when VIX>=18"*. `vix_bull_hard_cap` **exists in neither params file and is enforced nowhere in code.** I reported it to J as a live bull constraint — and the real picture is the reverse: bear has a VIX hard cap (23.0), bull has none.

That is L249's shape (*"files' own comments claim behaviour the code doesn't deliver"*) but worse, because a params `_doc` sits inside live config rather than beside source. **A phantom on one side manufactures an asymmetry that does not exist** — which is precisely how it corrupted a direction audit.

Full list of 24 in the JSON. Mostly retired experiments (`j_vwap_cont*`, `j_vix_dayside*`, `bollinger_squeeze`, `gap_and_go`, `tighter_stop`). The detector separates these from legitimate **TRIAL_NOTE** docs (2 found), whose target is a suffixed label of a live key — otherwise it would cry wolf on the repo's own annotation convention and get ignored.

## What this does NOT claim

No knob is wrong *because* it is asymmetric. A direction-specific gate is legitimate when its evidence is direction-specific and current. The instrument's job is to ensure every asymmetry is **chosen**, not inherited — and right now four of them are inherited from June on samples as small as n=11.

Nothing was flipped by this audit. It is descriptive and proposes nothing.

## Next

The single highest-leverage row is `filter_10_min_triggers_bull` 2→1 — one integer, the largest bar, and the top of the entry funnel. Pre-registered separately: [`prereg-trigger-parity-2026-08-09.json`](../recommendations/prereg-trigger-parity-2026-08-09.json).

## Reproduce

```bash
backtest/.venv/Scripts/python.exe setup/scripts/direction_symmetry_audit.py
```

---

## FORWARD MEASUREMENT 2026-08-16 — the harder-gated side is the BETTER side

> This audit established the asymmetry **structurally** (four of four knobs disfavour bull). It
> never priced it. Here is the P&L, from the FIFO real-fills authority
> (`fills_fifo.mine_real_arm_fills`, `attribution=='engine'` only), 282 round trips
> 2026-06-26..2026-08-14. Descriptive only — nothing armed, no knob touched.

### Raw round trips

| window | side | n | net | exp/trade | WR | avg win |
|---|---|--:|--:|--:|--:|--:|
| since 07-20 | **BULL** | 106 | **+$419** | **+$3.95** | 28.3% | **$322** |
| since 07-20 | BEAR | 72 | −$1,729 | **−$24.01** | 31.9% | $139 |
| since 08-01 | BULL | 92 | −$333 | −$3.62 | 27.2% | $333 |
| since 08-01 | BEAR | 53 | −$360 | −$6.79 | 35.8% | $157 |

**The mechanism is the tail, not the hit rate.** Bear's raw WR is *higher* in both windows, yet
it loses far more per trade — because bull's average win is **2.2× bear's** ($322 vs $139). On
a book the 2026-08-15 review already established as tail-dependent, the side with no right tail
is the side that bleeds.

### The correction that matters: these are not independent samples

`LEVER-CORRELATION-2026-08-06` (r = 0.846, forward-checked 2026-08-16) says the fleet is one
bet in five sizes. Counting one **(date, symbol) cluster** as one signal — however many arms
took it — the raw counts are inflated **2.3×–3.5×**:

| window | side | independent signals | raw RTs | inflation | per signal | signal WR |
|---|---|--:|--:|--:|--:|--:|
| since 07-20 | **BULL** | 37 | 106 | 2.9× | **+$11.3** | **27.0%** |
| since 07-20 | BEAR | 28 | 72 | 2.6× | **−$61.8** | **14.3%** |
| since 08-01 | BULL | 29 | 92 | 3.2× | −$11.5 | 27.6% |
| since 08-01 | BEAR | 15 | 53 | 3.5× | −$24.0 | 13.3% |

**Two things fall out, and the second is the one nobody has accounted for:**

1. **Raw WR FLATTERS the bear side, and reverses the ranking.** Raw: bear 31.9% vs bull 28.3%.
   Per independent signal: bear **14.3%** vs bull **27.0%** — bear's advantage does not merely
   shrink, it inverts to roughly half. Bear's losing signals are spread across more arms than
   its winning ones, so per-round-trip counting double-counts its wins. Any direction
   comparison quoted in round trips is measuring arm count as much as edge.

2. **⚠️ CLAUDE.md's bull re-eval bar is stated in the inflated unit.** OP-16 says bull "stays
   enabled pending honest re-eval at **n ≥ 20**". At the measured 2.9×–3.5× inflation, n=20
   round trips can be as few as **6–7 independent signals**. The bar is far weaker than it
   reads. (The same line's cited evidence — "bull n=80 WR 1.2% −$1,573" — is a July 9-day
   window and is now stale: bull is 17.2% WR over 174 RTs all-time, 28.3% since 07-20.)

### What this does and does not say

**DOES:** the four knobs this audit found — all of which make a call harder to enter or hold —
sit on the side that has outperformed on every recent window, in both units. That is a
measurable cost to the RED, not just an aesthetic asymmetry, and it is exactly J's 2026-08-09
objection ("we need to play both sides of the market, period") showing up in dollars.

**DOES NOT:** license flipping any knob. Eval-first (OP-11) applies and this is descriptive
evidence, not a scorecard. Specifically:
- **Neither side is profitable.** Bull is ~breakeven at best (+$11.3/signal since 07-20,
  −$11.5 since 08-01). "Better" here means "less bad".
- **n is genuinely small in the honest unit** — 15 bear signals since 08-01. One 4-arm cluster
  moves these totals by more than the totals (2026-08-14: −$1,497; 2026-08-13: +$2,151).
- Bull's low WR with a large average win means its result is carried by very few trades; that
  is a fragile distribution to re-tune a gate on.

**The concrete next step** is a pre-registered symmetry test on the four named knobs, sized in
INDEPENDENT SIGNALS rather than round trips. Writing the prereg is the gate; this measurement
is the motivation for it, and the unit correction above should be inherited by any study that
follows.
