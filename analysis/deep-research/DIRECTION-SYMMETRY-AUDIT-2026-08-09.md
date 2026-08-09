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
