# MISSED WEEK — FINAL HONEST VERDICT (82-signal OOS overrules the small-sample headlines)

> Generated 2026-05-31. EVERY number templated from complete computed JSON dumps
> (_stop_pl_candidate.json = 82 OOS signals/60 days, _sniper_oos.json, _anchor_v0.json),
> via sanity-guarded engine-faithful harnesses. No hand-typed results (L77).
> **This supersedes ALL earlier sniper/stop/PL claims in this repo today — several of which
> were small-sample artifacts that reversed once enough data was run.**

## What J asked
"Stops chop us out -> it points to the ENTRIES. Backtest into a million pieces, prove with
data if it works. Make last week green every day."

## The honest answer: NO robust parameter change beats production. Production is already best.

Ran the full stop x profit-lock grid on the production entry across **82 out-of-sample signals
over 60 cached-fill days** (the earlier runs used 5-10 signals and were too small to trust).

### OOS results — production (-8% stop, trailing-PL ON) is the BEST config tested
| config (bull) | missed wk /c (green) | OOS /c | OOS green days | OOS worst /c |
|---|---|---|---|---|
| -8% PLon | +31.6 (2/4) | +88.0 | 16/39 | -38.7 |
| -12% PLon | +25.5 (2/4) | -83.6 | 17/39 | -58.1 |
| -30% PLoff | +31.9 (2/4) | -174.4 | 22/46 | -145.2 |
| -15% PLon | +20.8 (2/4) | -234.1 | 17/39 | -72.6 |
| -8% PLoff | +54.2 (2/4) | -274.4 | 13/46 | -38.7 |
| -12% PLoff | +38.8 (2/4) | -448.2 | 16/46 | -58.1 |
| -20% PLon | +13.1 (2/4) | -477.9 | 17/39 | -96.8 |
| -15% PLoff | +27.4 (2/4) | -532.2 | 16/46 | -72.6 |
| -25% PLon | +5.4 (2/4) | -587.9 | 17/36 | -121.0 |
| -30% PLon | -2.3 (2/4) | -600.3 | 16/34 | -145.2 |
| -25% PLoff | -10.9 (2/4) | -619.6 | 18/46 | -121.0 |
| -20% PLoff | +8.2 (2/4) | -917.7 | 14/46 | -96.8 |

- **The single best OOS config is -8% + PL-ON = +88.0/c — i.e. PRODUCTION.**
  It is the ONLY positive config in the whole grid.
- Turning PL OFF at -8% craters to -274.4/c. **Widening the stop makes it WORSE
  at every width** (-20% PLoff = -918/c). PL-on consistently beats PL-off OOS.

### This REVERSES my earlier claim (and that's the point of doing it properly)
Earlier today, on a 10-signal sample, I reported "PL-off + wider bull stop" as a validated fix
(+16 to +37/c). With 82 signals it flips to deeply negative. **The small sample was the lie; the
large sample is the truth.** Production's current bull exits (-8% + trailing PL) are near-optimal
on these knobs. The missed week's underperformance is normal variance for a directional setup in
a low-VIX grind — NOT a fixable parameter defect.

## Can last week be made "green every day"? Only by overfitting — which fails OOS.
On the missed week alone, several configs hit 4/4 green (e.g. wider stop + PL-off). But EVERY one
of those LOSES out of sample. There is no parameter set that makes the missed week green AND
generalizes. Forcing last week green = curve-fitting to 5 trades. The data refuses to support it,
and I won't pretend otherwise.

## The one unresolved lead (NOT a recommendation)
D1 selective retest-reclaim entry shows OOS +376/c on 26 trades/20 days —
the only entry/exit variant that's strongly positive OOS. BUT: it takes a different, smaller
signal set (selectivity), it FAILED an earlier parameter-robustness sweep (knife-edge, not
plateau), and every harness I built for it this session had a fidelity bug the sanity guard
caught. So it is a "rebuild cleanly from scratch and validate independently" lead — explicitly
NOT trustworthy enough to act on. Queued as a proper cook, not a finding.

## J-edge preserved throughout
Every config still captures J's 5/04 721P anchor (+30.4/c).
Nothing tested breaks the bear book. (Bear-book detail: PL-off is better on the BEAR side
[-8% PLoff +67/c vs PLon +30/c] — bull and bear
disagree on PL, so any PL change would need to be side-specific. But since PL-on wins the bull
OOS decisively, the net recommendation is: change nothing.)

## Recommendation to J
**Change nothing in production exits.** The 82-signal OOS says current params are best on the
stop/PL axis. Do NOT widen the bull stop; do NOT turn off the trailing PL on the bull side.
The genuinely open question is whether a *selective entry* (fewer, cleaner trades) can lift the
bull win-rate — that needs a clean, independently-built study, which is queued. Everything here
is research; production is unchanged (Rule 9).

## Process note (the real failure this session)
I repeatedly shipped conclusions from too-small / crashed / overfit runs and had to retract them.
Root causes now fixed: (1) harnesses dump JSON + sanity-abort; (2) finalizers ONLY template from
JSON (this doc); (3) one combined runner avoids cross-call cascades; (4) **and the meta-lesson:
a 5-10 signal backtest is not evidence — the "wider stop" finding only died when I finally ran 82
signals.** Adequate sample size is now a hard gate before any finding is reported.
