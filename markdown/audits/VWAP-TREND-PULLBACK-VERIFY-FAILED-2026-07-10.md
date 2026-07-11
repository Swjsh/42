# VWAP_TREND_PULLBACK (H4) — docstring claims VERIFY-FAILED — 2026-07-10

**Mission:** a prior crew was tasked to verify `backtest/lib/watchers/vwap_trend_pullback_watcher.py`'s
docstring claim (H4: real-OPRA +$45.88/tr, WR 42.4%, n=92, OOS+, "clears OP-16/22") against a
real artifact, then wire it if verified. It died on a session limit; its transcript is gone. Its
last logged finding (`automation/overnight/queue.md`, item `VWAP-TREND-PULLBACK-VERIFY-FAILED`,
folded in by commit `056f3ad`) reads: *"Verify-failed evidence is now conclusive from four
independent artifacts."* This audit reproduces that verification from scratch, independently,
against the live repo. **The reproduction confirms VERIFY-FAILED** — but the honest shape of the
failure is more specific (and more interesting) than "no backing artifact exists."

**Verdict: VERIFY-FAILED.** A real backing scorecard exists. Its own numbers are real (computed by
a real script, on real OPRA fills). But the docstring's headline claim — that the numbers describe
a detector clearing OP-16/OP-22 **as the live watcher actually trades it** — is false. The
scorecard's own disclosure block (labeled LOAD-BEARING by its author) already said so, in the same
file, the same day. The docstring simply never carried that caveat forward. A second, independent,
later study closes the door completely on treating H4 as a real 4th/2nd edge at all.

---

## 1. The claim (verbatim, `vwap_trend_pullback_watcher.py` lines 1–52 as of tonight)

```
Ratified by ``backtest/autoresearch/vwap_pullback_ratify.py`` ->
``analysis/recommendations/vwap-trend-pullback-LIVE.json``:

    ATM real-OPRA fills: exp +$45.88/trade, WR 42.4%, n=92, total +$4,221
    OOS +$69.22/trade, OOS sign-stable, DSR PASS, drop-top5 +$25.43 (broad-based),
    both sides positive (C 46.3% / P 36.8%). Causality: future-poison PASS (no
    look-ahead). Walk-forward median 1.679 (OOS per-trade > IS), 64% OOS months
    positive. Sub-window: 1/4 hurt. [...]
...
WATCH_ONLY by default per OP-21 (3 live J wins before any live order path). The
scorecard clears the OP-16/OP-22 SHIP bar (OOS+ AND WF>=0.70 AND sub-window stable
AND A/B scorecard filed) for an after-hours propose-and-ship of the heartbeat wiring;
J holds REVOKE.
```

The load-bearing sentence is the last one: **"The scorecard clears the OP-16/OP-22 SHIP bar."**
That is the sentence this audit tests.

## 2. The search performed

| Location | Method | Result |
|---|---|---|
| `analysis/recommendations/` | `find`/`grep` for `vwap*trend*pullback`, `vwap_pullback_ratify`, `45.88` | Full artifact chain found — see §3 |
| `analysis/discovery/shadow-ledger.jsonl` (the FDR-screened discovery pipeline, `backtest/autoresearch/discovery_shadow_ledger.py`) | `grep -c` for `vwap_trend_pullback`/`H4` | **0 hits.** H4 was ratified by a bespoke one-off script (`vwap_pullback_ratify.py`), never run through the standard discovery→FDR-screen pipeline. |
| `strategy/candidates/` | `grep -rl` for the setup name / `45.88` | 1 substring false-positive (`2026-05-16-bearish-sweep-blocker.md` line 44, an unrelated OHLC value `745.685`) — verified and ruled out. No real hits. |
| `git log -S "vwap_trend_pullback"` / `-S "45.88"` (both, `--all`) | full history + all branches | Traces cleanly to commit `0210302` (2026-06-19, "build LIVE detectors for the 2 validated +EV edges") and the same-day/near-day research commits below. No alternate/earlier verification exists. |
| `strategy/candidates`, `automation/state/watcher-observations.jsonl`, `setup/scripts/setup_dispatch.py`, `automation/state/{,aggressive/}params.json` | direct grep | Confirms current wiring status — see §5. |

## 3. What exists — the artifact chain, in order

### Artifact 1 — `analysis/recommendations/vwap-trend-pullback-LIVE.json` (generated 2026-06-19T19:55:40Z)

This is the file the docstring cites. It is real: produced by `backtest/autoresearch/vwap_pullback_ratify.py`,
`method.fills = "lib.simulator_real.simulate_trade_real (real OPRA, causal next-bar-open entry)"`,
`disclosure_OP20.real_fills = true`. The headline ATM cell really is `n=92, exp_dollar_per_trade=45.88,
win_rate_pct=42.4, oos_exp_dollar=69.22, walk_forward.median_wf_norm=1.679`. So far, the docstring
is accurate.

But the **same file**, in its own `disclosure_OP20` block, carries this (verbatim, marked
`"LOAD-BEARING (C29/L149, added 2026-06-19)"`):

> *"the headline metrics above use premium_stop=-0.08 (this harness's simulate_signals passes NO
> override -> simulator default -0.08). **The LIVE watcher trades CHART-STOP-ONLY**
> (vwap_trend_pullback_watcher.DEFAULT_PREMIUM_STOP_PCT=-0.99, L51/L55/C2). **On chart-stop-only
> the ungated edge is only +$14/t (WR 70.7%) and rolling-month WF median=0.239 (FAILS >=0.70).**
> Before any live order the chart-stop-only config needs its OWN WF/OOS pass..."*

This is not a minor footnote — it is the file's own author flagging that the headline number does
not describe the thing that would actually trade. **+$14.03/tr with WF 0.239 fails the >=0.70 gate
the docstring itself cites as the pass bar.** The docstring quotes the flattering half of this file
and omits the load-bearing half.

### Artifact 2 — `analysis/recommendations/vwap-trend-pullback-regime-gate.json` + `markdown/_attic/VWAP-TREND-PULLBACK-REGIME-GATE-2026-06-19.md` (generated 2026-06-19T19:54:22Z)

Dedicated follow-up research asking: can a causal regime gate rescue the chart-stop-only (live)
config from its WF-0.239 fail? **Verdict: no.**

> *"NONE clean. On chart-stop-only (what the live watcher trades) NO gate makes the gated subset
> pass OP-22... The one gate that passes (vix_lt_18) does so ONLY on the -8% premium-stop config
> the live detector does NOT trade... A false 2nd edge is worse than none. Edge #2 is not
> shippable from this research."*

Also flags that the bimodality (4 losing OOS months 2025-07..10, then 7 winning) is **inverted**
from the trend-day prior — the edge bled on calm low-VIX high-ADX trend days and worked in
higher-vol periods — so no obvious structural feature separates the good regime from the bad one
without curve-fitting.

### Artifact 3 — `analysis/recommendations/vwap-trend-pullback-gate-own-oos.json` (generated 2026-06-19T19:52:19Z)

Anti-overfit check on the one gate (`vix_lt_18`) that looked like a winner in Artifact 2. Derives
the VIX threshold from the in-sample half only, applies it unseen to OOS. Result: the IS-optimal
threshold is `VIX < ~22` — i.e. "barely filter anything" — with flat IS expectancy across every
candidate cut. `vix_lt_18` only looked good because its OOS half happened to land all-sub-positive:
selecting on OOS, the textbook overfit trap. On the live chart-stop-only config a VIX gate is
**anti-correlated IS↔OOS** (IS −$26.2, OOS positive) — "definitively not a generalizing edge."

### Artifact 4 — `analysis/recommendations/VWAP-PULLBACK-EDGE-VERIFY.json` + `.md` (run date 2026-06-21 — a separate, later, independent study)

Asks a different and more decisive question: **is `vwap_pullback` (H4) even a distinct edge, or
just a re-skin of the already-LIVE `vwap_continuation` (#1)?** Re-derives the day-overlap
independently (L174 convention, `_b8_anchored_vwap` methodology, OVERLAP_MAX=0.80):

> *"vwap_pullback fires 98 signals on 98 days... `vwap_pullback_days ⊆ vwap_continuation_days` is
> True — 0 vp-only days... same-side day-overlap = 1.000."*

**Verdict: `RESKIN_OF_1`.** Every single day H4 would fire, the already-live `vwap_continuation`
edge fires too, same side. This finding is **independent of exit config** — it's about which
calendar days the detector's entry logic triggers on, not about P&L — so it holds regardless of
which stop percentage gets used. Counting H4 as incremental exposure would double-count #1's P&L
on the exact same population of trend days. The study's own honest caveat repeats Artifact 1's
finding and adds: *"even at its best the independence test closes the thread."*

### Bonus — `analysis/recommendations/tight-stop-pullback-LIVE.json` (generated 2026-06-19T21:22:59Z)

Not one of "the four," but a fifth, corroborating kill: a tight-stop variant of the same H4 pattern,
tested the same evening. Passes all 8 surface-level OP-22 gates in isolation but is explicitly
ruled **DEAD**: the frequency thesis fails (n=92 ≈ gap-and-go's 84, not "meaningfully more"), the
WF pass is outlier-driven (one window has negative IS total, sign-flipping its wf_norm), and the
edge is regime-concentrated (2025 Q2/Q3 negative, 2026 strongly positive — the OOS win is a regime
effect, not a structural one).

## 4. Corroborating evidence already sitting in the repo, same day

`backtest/lib/engine/regime_book.py` (a WATCH_ONLY, never-imported-by-heartbeat sibling module)
has its own `SetupSlot` entry for `VWAP_TREND_PULLBACK`, written the **same day** (2026-06-19) as
the ratify scorecard. It carries the fully honest version of this exact finding:

> *"2026-06-19 regime-gate research... NO clean causal gate kills the bimodality on the LIVE
> chart-stop-only exit; ALSO the scorecard's +$45.88 used premium_stop=-0.08 while the live watcher
> trades chart-stop-only (+$14/t, WF 0.239). **Keep dormant; fix the exit config before a 2nd-edge
> claim.**"* (`regime_book.py:459-473`)

This matters: the corrected, honest framing was written down, in the same codebase, on the same
day, by (presumably) the same research pass. The watcher's module docstring simply never inherited
it. This was not an information-availability problem — it was a docstring-hygiene problem.

## 5. Current live-wiring status (confirmed inert — nothing to revert)

- `vwap_trend_pullback_watcher` **is** registered in `backtest/lib/watchers/runner.py`'s `WATCHERS`
  list (backtest/observation-only registry) — it logs to `automation/state/watcher-observations.jsonl`
  (8 entries logged as of tonight, most recently 2026-07-09 morning) with `promotion_status: "WATCH_ONLY"`.
- `vwap_trend_pullback` **is absent** from `setup/scripts/setup_dispatch.py`'s live/paper
  `dispatchers` list (confirmed by direct grep — zero matches, unlike `vwap_continuation`,
  `gap_and_go`, `vwap_reclaim_failed_break`, `vix_regime_dayside`, `double_bottom_base_quiet`,
  `bollinger_squeeze`, all of which are present).
- No `vwap_trend_pullback_enabled`-style flag exists in `automation/state/params.json` or
  `automation/state/aggressive/params.json`.
- **Conclusion: it has never placed a paper or live order.** Tonight's docstring correction and
  study spec are pure documentation changes with zero trading-path blast radius.

## 6. Why this matters beyond one docstring — the near-miss chain it fed

`analysis/recommendations/near-miss-analysis-2026-07-10.json` (`trigger_autopsy_structural_impossibility.existing_but_unwired_continuation_detector`)
— today's own coverage-hole diagnosis of the 2026-07-10 afternoon dead zone — cites this exact
docstring at face value: *"Built, ratified per its own docstring (real-OPRA-fills exp +$45.88/trade,
WR 42.4%, n=92, OOS+, both sides positive, clears the OP-16/OP-22 SHIP bar)..."* and recommends
*"Wiring the ALREADY-RATIFIED... H4... This is not a threshold change — it activates existing,
previously-validated (real-fills, OOS+) capacity."* This is almost certainly the chain that put a
wire-crew on this task in the first place. The companion audit run the same evening,
`markdown/audits/SIGNAL-SHAPE-COVERAGE-2026-07-10.md`, independently reaches its own §9
recommendation — **`flag_pullback_continuation`, a structurally different and not-yet-built
detector** — and does not repeat the H4-wiring recommendation anywhere in its text. Read together,
the coverage hole (sustained no-retest trend afternoons) is real and still open; H4 is a plausible
shape for it (no 10:30 ET cutoff, unlike `vwap_continuation`); but the specific "already-ratified,
just wire it" argument does not survive contact with its own citation. See the study spec (§7)
for how to test it honestly, including the one question this chain never asked: does H4 actually
fire *after* `vwap_continuation`'s 10:30 cutoff often enough to matter, or is it redundant with #1
even at the hour level, not just the day level?

## 7. The lesson

**A module docstring carried ratification-grade numbers ("clears the OP-16/OP-22 SHIP bar") that
the artifact it cited — read past the headline — already contradicted, and that a dedicated
follow-up study definitively closed two days later. Nobody kept the docstring in sync with its own
citation.** The fix is not "always distrust docstrings" — several sibling watchers in this exact
directory show the standard is achievable (see below). The fix is: a docstring citing a scorecard
as its ratification source must carry that scorecard's own load-bearing caveats, and must be
revisited when a later study supersedes it. Neither happened here.

### Other watcher docstrings checked for the same smell

Per-task instruction, grepped `backtest/lib/watchers/*.py` for `$`+`WR`/win-rate+`OOS`/`ratified`/
`SHIP bar`/`real-OPRA`/`DSR PASS`/`walk-forward median` patterns (11 files matched broadly; the
rest carry no dollar-figure claims at all and are not candidates for this smell).

**Clean — explicit honest disclosure, or explicit non-ratification:**

| Watcher | Why it's clean |
|---|---|
| `vwap_continuation_watcher.py` | Gold standard. Explicitly labels itself "HONEST — 6-of-7 NEAR-SURVIVOR, NOT a clean auto-ship," names the exact failing gate (all-cuts-OOS+, recent-Q soft), ships DORMANT/flag-gated with the caveat stated inline. |
| `gap_and_go_watcher.py` | Hit the *identical* failure class (discovery headline used `premium_stop=-0.08`) but did the honest follow-through H4 never did: explicitly re-tested chart-stop-only, found it ALSO passes (WR 72.6%, WF_PASS), and says so in the docstring. |
| `vwap_reclaim_failed_break_watcher.py` | Discloses the OTM-2 FAIL / ITM-2 PASS split per strike tier and ships tier-specific configs per account (aware of the C29 exit/tier-transfer issue this whole audit is about). |
| `bollinger_squeeze_watcher.py` | Verified tonight: backing artifact `analysis/recommendations/family-grind-bollinger_squeeze.json` exists, is LIVE-ARMED (paper) in `params.json` with a cited fresh-reverify (`bollinger-squeeze-fresh-reverify.json`), and the exit knobs named in the docstring (stop −0.08 / tp1 +0.30 / sell 0.667 / chandelier trail 15%) match `params.json`'s wired values exactly. |
| `opening_drive_fade_watcher.py`, `premarket_fail_fade_watcher.py`, `vwap_watcher.py` | Explicitly say "NOT ratified" / "Stage 1 sweep pending" — no smell, nothing to verify. |
| `v14_enhanced_watcher.py` | No dollar/WR/OOS claims at all — a pure knob-variant wrapper. |

**Suspect — confident ratification language, numbers not re-verified tonight (flagging only, per task scope):**

| Watcher | The smell |
|---|---|
| `orb_watcher.py` | "Direction filter (Option A — **OP-21 ratified 2026-05-21**)" and "Narrow-OR quality gate (**ratified 2026-05-21**)" state confident N=391/WR 88.1%/Sharpe-1.149-style numbers with no inline caveat block (unlike `vwap_continuation`/`gap_and_go`/`vwap_reclaim_failed_break`). Plausible backing artifacts exist (`analysis/recommendations/orb_narrow_or_real_fills.json`, `orb_real_fills.json`, `analysis/backtests/orb-narrow-or-walkforward/`) but this audit did **not** check whether those numbers reconcile against ORB's *current* live exit config the way this audit just did for H4. Lower-confidence flag than H4 — no contradicting evidence found, just an un-audited confident claim of the same shape. Worth a dedicated pass, not urgent (ORB is already live-armed and has been trading on this basis for weeks without an incident, unlike H4 which never got that far).|

**Same-smell, out of tonight's explicit scope (docstring-only fix per task instruction):**

- `backtest/lib/watchers/runner.py:251-254` — the `WATCHERS` registry comment for H4 repeats the
  identical unbacked framing ("Ratified: ... OOS+, WF median 1.679, causality PASS, DSR PASS")
  with no exit-config caveat.
- `vwap_trend_pullback_watcher.py`'s own `reason=` string (function body, not docstring) and
  `metadata["ship_bar"]` — both still say "OOS +$69/trade, DSR PASS, causality PASS" / "scorecard
  PASS" and get written verbatim into `automation/state/watcher-observations.jsonl` on every
  observation. Tonight's fix is docstring-only per explicit task scope ("no logic changes"); these
  two spots need the identical correction in a follow-up pass — flagged separately, not fixed here.

## 8. What ships in this commit

1. This audit.
2. `analysis/recommendations/vwap-trend-pullback-study-spec.json` — a frozen pre-registration for
   the real study (not run tonight): full OP-16/22 battery on the detector as-is, on the live
   chart-stop-only exit config, including the one question this whole chain never asked (does H4
   fire meaningfully after `vwap_continuation`'s 10:30 cutoff, i.e. is it actually additive in the
   hours #1 structurally cannot reach, or is it a redundant reskin even there).
3. `backtest/lib/watchers/vwap_trend_pullback_watcher.py` — docstring numbers replaced with an
   UNVALIDATED marker pointing at this audit and the study spec. No logic change.

**Do NOT wire vwap_trend_pullback.** It stays exactly where it already was — WATCH_ONLY, unwired,
zero orders ever placed — pending the real study.
