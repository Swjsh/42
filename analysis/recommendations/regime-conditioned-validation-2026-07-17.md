# Regime-conditioned validation — the 2025-vs-2026 reference-class adjudication (2026-07-17)

> Resolves `analysis/recommendations/REGIME-REFERENCE-CLASS-ADJUDICATION-2026-07-17.md` (Fable/Opus
> frame). Prereg: `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`
> (frozen `content_sha256_16=1b927e10e84e7fa3`, verified by preflight before any run). Code:
> `backtest/tools/regime_classifier.py`, `regime_conditioned_validator.py`,
> `regime_conditioned_self_validation.py`, `regime_conditioned_readjudication.py`. Raw output:
> `analysis/recommendations/regime-conditioned-validation-2026-07-17.json` +
> `regime-conditioned-readjudication-2026-07-17.json`.

## THE VERDICT, up front

**The methodology EARNS RIGHTS (self-validation passed cleanly) — but when actually applied to
the 5 parked candidates, ZERO of them flip to PASS.** The honest synthesis: this is closer to
**(A) recency-overfitting** than (B) genuine regime break, but with an important nuance
regime-conditioning surfaced that a flat "(A), full stop" answer would have missed — see
per-candidate detail below. No live config touched. No candidate ships.

## Step 1 — self-validation (the gate)

| cohort | kind | n | target bucket | n_bucket | verdict | correct? |
|---|---|--:|---|--:|---|:--:|
| NLWB full real-fills | known-bad | 23 | MID_uptrend | 9 | FAIL | YES (killed) |
| confluence fresh95 | known-bad | 38 | MID_uptrend | 21 | FAIL | YES (killed) |
| double-top real-fills | known-bad | 354 | MID_uptrend | 125 | FAIL | YES (killed) |
| pure-noise placebo (seed 20260717) | known-bad | 40 | MID_uptrend | 20 | FAIL | YES (killed) |
| vwap_continuation ITM-2/-8% (LIVE) | known-good | 163 | MID_uptrend | 89 | **PASS** (5/5 gates, WF=1.359, BH-FDR p=0.005) | YES (survived) |
| OP-16 anchor trades (n=7, all 2026) | known-good, qualitative | 7 | MID_uptrend | — | all 7 dates coherently labelled | YES (no coverage gap) |

**All 4 known-bad cohorts correctly killed. The one known-good cohort with enough n for the full
ladder cleared all 5 gates cleanly** (not a near-miss — WF=1.359, BH-FDR p=0.005, survives
dropping its top-3 OOS trades, both regime-halves stable). OP-16 anchor dates all resolve to a
coherent, available regime label (no classifier blind spot). Per the prereg's precommitted
criteria: **EARNS_RIGHTS.**

## Step 2 — the tautology check (is regime just a calendar proxy?)

Global, over all 389 trading days 2025-01-02..2026-07-08: **Cramér's V = 0.2135** between regime
label and calendar year — low-to-moderate, NOT a near-1 tautology. No candidate's target bucket
triggered the `degenerate_regime_proxy_flag` (>=90% concentrated in one year); the closest was
`pct_bucket_dated_2026` in the 27-33% range across every cohort tested (a bucket that's roughly
1/4-to-1/3 2026-dated, 2/3-to-3/4 2025-dated — genuinely mixed, not a calendar re-skin).

**A real, disclosed limitation found along the way (fable-too-good hunt, not swept aside):** one
regime bucket — **`MID_uptrend`** — covers **53.0% of all 389 trading days** (206 days: 149 in
2025, 57 in 2026). Because the target-bucket rule is "modal bucket among the candidate's own
episodes," **any candidate whose trades spread broadly across the calendar will default to this
same dominant bucket** — and in practice, 3 of the 4 known-bad cohorts, the one known-good
cohort, all 7 OP-16 anchor dates, and 3 of the 5 re-adjudicated parked candidates ALL resolved to
`MID_uptrend`. For those, "regime-conditioned" validation is honestly closer to **"chronological
(not calendar-year) split within the broadest slice of history"** than a narrow VIX/trend-specific
test — a real, useful mechanism (it still removes the arbitrary Jan-1-2026 boundary and it still
correctly separated known-bad from known-good), but a humbler one than "tests the candidate in
its own specific regime." The one case that resolved to a DIFFERENT bucket — elite-bear
(`MID_downtrend`, a bear-side candidate correctly routing to a downtrend regime) — is reassuring
face-validity that the classifier isn't purely arbitrary, but the dominance of MID_uptrend is a
structural property of THIS 18-month window (it was mostly a grinding-up, moderate-VIX tape) that
any regime-conditioned method built on it should carry forward as a disclosed caveat, not a hidden
one.

## Step 3 — re-adjudication of the 5 parked candidates (EARNS_RIGHTS unlocked this step)

| candidate | target bucket | n_bucket | regime IS-mean | regime OOS-mean | WF | verdict | flips to PASS? |
|---|---|--:|--:|--:|--:|---|:--:|
| elite-bear-level-reject-gate (goal L1) | MID_downtrend | 8 | −$133.20 | +$112.79 | −0.85 | INSUFFICIENT_REGIME_SHIFT | **NO** |
| bold-strike-axis ATM vs OTM-3 | MID_uptrend | 168 | +$1.95 | +$3.57 | 1.83 | FAIL (sub-window + BH-FDR + concentration) | **NO** |
| fleet strike tier (risky-3) | — (no separate cohort; inherits bold-strike ATM, per WF-GATE-METHODOLOGY's own disposition) | — | — | — | — | inherits FAIL above | **NO** |
| zone-rejection-band (bold, fixed_0.75) | MID_uptrend | 9 | −$475.00 | −$239.50 | 0.50 | FAIL (regime-OOS still negative) | **NO** |
| pong-resting-limit (safe, no_cancel\|tp30_structure_t12) | MID_uptrend | 671 | +$7.39 | +$6.68 | 0.90 | FAIL (sub-window + BH-FDR) | **NO** |

**None of the 5 parked candidates flip to PASS.** Detail per candidate:

- **elite-bear L1**: the negative-then-positive signature PERSISTS even inside a single regime
  bucket (MID_downtrend, chronologically split — not a calendar artifact by construction). That's
  mildly interesting evidence against "pure calendar noise," but n_bucket=8 is thin, sub-window
  stability fails (second half swings −$266 alone), and the concentration check reproduces the
  ORIGINAL study's own finding almost exactly: dropping the top-3 trades takes the regime-OOS mean
  to exactly $0.00. Still an n=3-driven artifact, just no longer a calendar-year-driven one.
  Verdict stays INSUFFICIENT_REGIME_SHIFT — unresolved, not flipped.
- **bold-strike ATM**: this is the most informative result. Regime-conditioning genuinely REMOVES
  the calendar confound here — is_delta_mean flips from strongly negative (calendar-IS 2025:
  −$0.63/tr per the original delta-WF study) to barely POSITIVE (+$1.95/tr, regime-IS) and WF
  clears 0.70 (1.83). But it then fails on the gates that actually test whether that's a real
  population effect: BH-FDR p=0.46 (nowhere near significant), sub-window instability (first
  regime-IS half is −$34/tr), and the concentration check — the "edge" evaporates to −$26/tr once
  the 3 largest OOS trades are excluded. **Honest read: the calendar-year framing was masking that
  this was never a real edge, not that a real regime-dependent edge was being wrongly rejected by
  calendar-year.** This is a meaningfully different, MORE useful finding than the original
  INSUFFICIENT_REGIME_SHIFT park — it says WHY, not just THAT.
- **fleet strike / risky-3**: no independently-computed cohort exists (documented in
  `WF-GATE-METHODOLOGY-2026-07-16.md`: risky-3 shares the exact same `V15_BOLD_TIERS` table as
  core Bold via `fleet_executor.py#_tiers_for_arm`) — inherits the ATM result above by construction,
  not a separate finding.
- **zone-rejection-band**: regime-conditioning makes this candidate look WORSE, not better — both
  regime-IS and regime-OOS deltas are negative. Unambiguous, no calendar-confound story here at all.
- **pong-resting-limit**: near-identical shape to the original calendar study (which was blocked
  only by `anchor_no_regression`, at 4/5 gates). Under regime-conditioning it clears the core WF
  bar (0.90) but fails BH-FDR (p=0.19) and sub-window stability — the SAME underlying fragility
  (a large-n book whose aggregate edge doesn't survive stricter checks) the original anchor-date
  check was also catching, just via a different gate this time.

## Answer to THE QUESTION

**(A) recency-overfitting is the better-supported reading for these 5 specific candidates** — not
because the regime-conditioned methodology was rejected (it wasn't; it earned the right to
adjudicate cleanly), but because when actually pointed at each candidate, none of them produce a
robust, population-level, statistically-significant edge once the calendar-year framing is
removed. The clearest case (bold-strike ATM) shows this precisely: removing the calendar confound
does change the sign of the IS-delta, but the underlying "edge" still doesn't survive
concentration/significance scrutiny — the calendar boundary was never the actual problem, it was
a coincidental correlate of a handful of outsized trades. **The honest goal ceiling stands: not
all parked candidates can be made green via generalizable tuning — that is a valid terminal
state, reported plainly, not forced.**

## What did NOT happen

No `automation/state/params.json`, `automation/state/aggressive/params.json`, or
`crypto/lib/strike_selection.py` file touched. No orders placed. No candidate's evidence status
was upgraded to SHIP-READY. Calendar-WF (`WF-GATE-METHODOLOGY-2026-07-16.md`) remains the
standing gate; this study is a SUPPLEMENTARY lens that was earned honestly and, applied for real,
agrees with the calendar verdict on 4/5 candidates and adds diagnostic color (not a flip) on the
5th (bold-strike ATM).

## Files

- Prereg (frozen before any run): `analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json`
- Classifier: `backtest/tools/regime_classifier.py`
- Validator: `backtest/tools/regime_conditioned_validator.py`
- Self-validation runner + raw output: `backtest/tools/regime_conditioned_self_validation.py` →
  `analysis/recommendations/regime-conditioned-validation-2026-07-17.json`
- Re-adjudication runner + raw output: `backtest/tools/regime_conditioned_readjudication.py` →
  `analysis/recommendations/regime-conditioned-readjudication-2026-07-17.json`
