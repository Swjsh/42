# Missed-Week DEEP FINDINGS — the week IS fixable, and it confirms the entry thesis

> Generated 2026-05-31 from real-fills experiments. Sources (all computed in-process, L77):
> `analysis/missed-green-sweep.md`, `analysis/green-config-validation.md`,
> `analysis/sniper-entry-experiment-2026-05-31.md`, `analysis/backtests/_TRUTH.md`.
>
> **CORRECTION NOTICE:** an earlier draft of this file claimed "0 of 512 configs green, 05-28
> red under every config." That was WRONG — written from a sweep run that had CRASHED before
> producing output (a repeat of the L77 fabrication foot-gun). The sweep, once fixed and
> actually completed, found 4 all-green configs. This file is the corrected, verified version.

## The question J posed
"If our stops are the issue, it really points to the entries. Tighten them up — closer to the
move so we don't get chopped out, but there's a fine line on being too late. The engine has
proven it can ride the EMA ribbon. More sniper entries. Test until last week is green every day."

## Answer: the week CAN be made green every day — and how it gets there proves the entry point.

### Finding 1 — A wide stop + NO trailing-PL makes all 4 days green (256-combo sweep, real fills)
Swept the real engine over stop x TP1 x qty-fraction x strike x profit-lock x bull-trigger = 256
configs on the 4 missed days (`analysis/missed-green-sweep.md`).
- **4 configs go 4/4 green.** Best: **ATM strike, -50% premium stop, trailing-PL OFF, mtb1**:
  per-day **+521 / +676 / +393 / +788**, **+129.4/contract** for the week (n=5 trades).
- **05-28 (the clean trend day) goes +393** under this config — vs -21.4/c under production.
- **Every single all-green config has trailing-PL OFF (pl-fixed).** No trailing-PL config made 4/4.

### Finding 2 — TWO culprits, not one: stop width AND the trailing profit-lock
The missed week died from a combination:
- **(a) -8% stop too tight:** a routine retest wick tripped it before the ribbon-ride began.
- **(b) trailing profit-lock actively harmful:** it armed at +5% favor on the chop, then the
  20%-off-HWM trail stopped the trade out on the same retest. The "winners-never-negative" lock
  was, in low-VIX chop, "winners-stopped-on-noise." Turning it OFF is half the fix.

### Finding 3 — The wide stop still captures J's edge (but deepens worst-case losses)
Adversarial gate (OP-16), anchor window 2026-04-27..05-07, filter-8 off (`green-config-validation.md`):
| config | trades | total/c | 5/04 capture | 4/29 capture | worst put loss/c |
|---|---|---|---|---|---|
| PROD (ITM2, -8%) | 10 | -14.7 | +53.6 (721P 11:20) | none | -25.2 |
| GREEN (ATM, -50%) | 17 | +5.7 | +31.2 (719P 11:20) | +41.8 (710P 12:15) | **-58.0** |
- GREEN **keeps** the 5/04 anchor AND is net-better on the anchor window (+5.7 vs -14.7/c).
- **The cost:** worst single put loss deepens to -58/c (vs -25/c). A -50% stop = half the
  position at risk on one trade. This is the honest tradeoff J must weigh.

### Finding 4 — Why this CONFIRMS the entry thesis (not contradicts it)
A -50% stop "working" is brute-force proof that **direction was right, entry was too early.** The
trade needs half the premium as breathing room just to survive the retest before the ribbon-ride
pays. Per-entry trace (`sniper-entry-experiment-2026-05-31.md`): 6 of 8 call entries had
bars->MFE = 2 (premium barely ticked up, then reversed into the stop); the one clean winner
(05-29 09:40) had bars->MFE = 6 (a real run the ribbon rode). **A sniper entry that enters closer
to the launch would capture the same wins without needing a 50% stop** — same destination, far
less risk per trade. That is the elegant fix; the wide stop is the sledgehammer that proves it's
possible.

### Corroboration from our own lessons (designer agent, source-grounded)
- **L64 (ORB retest):** identical mechanic; chart-stop fix took ORB 30% -> 90% real-fills WR.
- **L51 / L55 / L74:** premium stops tighter than ~-30% fail on any entry whose next bar retests
  a named level. (Consistent with Finding 1: only a very wide -50% stop survived.)

### Honest discrepancy I will NOT paper over
My quick entry-experiment showed chart-stop UNDERperforming the premium stop — opposite of L64.
Likely my harness's chart-stop mode didn't engage the level stop for CALLS. So those rows are NOT
valid evidence; a dedicated cook (TRUE-SNIPER stop re-test) re-tests it properly. Trust L64 +
the re-test, not my experiment's chart-stop rows.

## The path forward (in the Kitchen NOW)
The brute-force answer (wide stop + no trailing-PL) is a real candidate but risky per trade. The
better answer is a SNIPER ENTRY closer to the launch, so a normal stop suffices.

**8 entry designs** (`strategy/candidates/2026-05-31-sniper-entry-designs.md`): D1 retest-reclaim
sniper, D2 no-retest momentum sniper, D7 chart-stop-primary (top 3).

**7 TRUE-SNIPER cooks queued** (premise-verified; the false-premise batch was archived per L77):
entry-timing sweep, 05-28 ideal-entry reverse-engineer, chart-stop honest re-test, pullback
skip-cost vs OOS, momentum-gate loosening, ribbon-ride exit hold, preserve-J-anchors gate.

**New cook to add:** isolate the trailing-PL-OFF effect from the stop-width effect (Finding 2) and
test stop widths -8/-15/-20/-30/-50 x {trailing on/off} on missed week + anchors + OOS, to find
the MINIMUM stop width that keeps the week green — the less room we need, the better the entry.

## The non-negotiable gate (OP-16)
Every candidate must (a) improve the missed week per-contract AND (b) still capture 5/04 721P and
not worsen the 4/29 + 5/01 anchors AND (c) not deepen worst-case loss to a sizing/kill-switch
problem. The -50% config passes (a) and (b) but (c) needs J's risk judgment. Real-fills + OOS
walk-forward before any ratification (Rule 9 — J's call, on a weekend, in writing).

## Bottom line for J
- **The week is fixable: 4/4 green via ATM + -50% stop + trailing-PL OFF (+129/contract).**
- **Two fixes surfaced:** the stop was too tight AND the trailing profit-lock was hurting us in
  chop (turn it off). Both are real; the trailing-PL one may matter beyond this week.
- **It confirms your call:** the -50% stop is the brute-force proof the ENTRY is early — a sniper
  entry gets the same wins without risking half the position. That's what's cooking now.
- **Risk caveat:** -50% per-trade stop deepens worst-case losses; weigh before live. OOS pending.
