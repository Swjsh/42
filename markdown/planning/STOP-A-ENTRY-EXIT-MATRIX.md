# ⛔ STOP CHECKPOINT A — ENTRY & EXIT MATRIX

**To: Opus / Fable / J. From: the executor of HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.**
**Status: T1–T4 + the P5 guard shipped & verified. NOTHING TRADING-PATH SHIPPED. T5/T6 blocked on your sign-off.**

This is the package the handoff routes here ("T2 report + T3/T4 exploratory results go to Opus/Fable/J. Nothing ships"). Read the 3 findings, then the ONE decision, then the pre-registered T5 list. Every number below is from a committed, guarded artifact — links inline.

---

## THE ANSWER IN ONE LINE

**The money leak is the EXIT, not the read — the shipped `-20%/+150%` shape LOSES −$757 on the 79 real fleet fills while a wider-stop / partial-scalp / trailing shape makes +$1,053–1,574 on the SAME fills. Passive entry is a real but CONDITIONAL second lever (it only pays when there's a stop to give headroom to). Neither ships until the T5 confirmatory pass + P5 gate + anchor clear it.**

---

## FINDING 1 — the shipped exit harvests its own winners (ranked #1; highest-confidence, real-fill-anchored)

- **Diagnostic (T2, [entry-exit-diagnostics.md](../../analysis/exit-parity/entry-exit-diagnostics.md)):** across 250 signals × the strike ladder, a −20% stop harvests **55–62% of eventual +150% winners in EVERY premium band**; +150% is reached by only **22–40%** while **+30/+50% by 58–82%**. The stop sits inside the noise floor (median 10-min MAE −15% to −29%) and, on sub-$0.20 contracts, is only **2 ticks** wide.
- **Exit sweep (T4, [entry-exit-matrix-t4-exits.md](../../analysis/recommendations/entry-exit-matrix-t4-exits.md)):** shipped control = **$22.91/tr @ 15% WR**; the leading redesigned shapes (wide/no stop + partial-scalp + trailing runner) = **$67–93/tr**, and survive **drop-top-3** ($44–65) and **qpf 1.0**.
- **⚑ ANCHOR (decisive, real fills):** replayed on **79 real fleet positions**, the shipped control **LOSES −$757**; all top-5 finalists make **+$1,053 to +$1,574** (`no-regression = Y`). This is the 741P exhibit at population scale — the shipped shape loses money on the actual trades the fleet took.
- **⚠️ THE COST (do not skip):** the no-stop rides carry **worst-decile −$989/tr and maxDD ≈ −$5,034 at qty 10** — which EXCEEDS a $2K account, so on a real arm the −30/−50% kill switch fires first. **The fix is NOT "remove the stop."** The per-band data says the cheap **<$0.20 band wants a MODERATE −25/−30% stop, not none**; the richer bands tolerate the ride. The right shape is *widen + partial-scalp + trailing, sized under the kill switch* — a judgment call this checkpoint owns.

## FINDING 2 — passive entry is a stop-headroom lever, not a universal win (ranked #2)

- **Entry sweep (T3, [entry-exit-matrix-t3-entries.md](../../analysis/recommendations/entry-exit-matrix-t3-entries.md)):** a limit fill at `signal×(1−δ)` pushes the SAME stop δ% further from the signal (free headroom) but misses the winners the bar never dips to. Priced NET of misses:
  - **scalp exit (−35/+50): passive WINS big** (+19 to +90 net vs market) — and even the honest *cancel* policies (real ~38% misses) beat pay-up.
  - **control exit (−20/+150): passive wins ONLY with a premium floor** ($0.50 floor flips it +9/+10).
  - **no-stop ride: passive LOSES** — no stop means the headroom protects nothing, so the misses are pure cost.
- **So entry policy and exit shape are COUPLED.** "Entry offset IS stop headroom" (J's hypothesis) is **confirmed — conditionally**. The joint optimum can't be read off the two marginals; it needs the combined grid (deferred to T6, per the handoff).
- Secondary: `convert-to-market at window end` adds a *delay* edge (entering one bar later dodges the signal-bar premium spike — defect #2), separable from the limit edge; the `cancel` rows are the clean passive-fill test.

## FINDING 3 — the premium floor is real and nearly free (ranked #3)

- Sub-$0.20 contracts (55/79 of the real fleet's entries) have 2-tick stops and a **42% spread-to-premium proxy** — %-anything is spread noise there (defect #1).
- A premium floor lifts even the market baseline (control $22.91 → **$34.68 at floor $0.50**) and amplifies the passive edge everywhere. It interacts with strike-tier selection (a floor is "pick a richer strike or skip").

---

## THE ONE DECISION FOR THIS CHECKPOINT

**Pick what advances to the T5 confirmatory OOS pass** (pre-registered below, per ground rule 12 — no re-picking after seeing OOS). The judgment you own:
1. **How much tail to accept for winner-capture, at what qty, under the kill switch** (Finding 1's cost).
2. **Whether to couple a scalp exit with a passive limit entry** (Finding 2's interaction) or keep exits/entries independent.
3. **Whether to set a global premium floor** (Finding 3) and at what level.

Route: exit shapes + entry policy are STRATEGY properties → P1/backtest confirmatory (T5). The *frame* question ("is the whole 0DTE-single-leg premium-shape search the right game vs a DTE ladder / spreads") is an Opus/P2 call, not this file's.

## PRE-REGISTERED T5 CANDIDATES (v2 after Fable review — frozen BEFORE any confirmatory run)

Written to [`entry-exit-matrix-stop-a-preregistration.json`](../../analysis/recommendations/entry-exit-matrix-stop-a-preregistration.json) **(v2)**. T5 runs the confirmatory battery on EXACTLY these; auto-ratify bar = fresh-slice positive AND WF ≥ 0.70 AND sub-window-stable AND anchor_no_regression AND **P5 pass on a FRESH grind**.

**Exit (ribbon_ride, both directions), ≤3 — each with its own quoted full-population cell:**
1. `exit-A` **−50/+150/sell66/trail15/tgt-none** — the strongest *wireable* cell: exp $42.99, drop-top-3 $17.88, qpf 0.833, WF 2.06, rank 65/2016. Zero new knobs (live −50 cap convention).
2. `exit-B` **per-band stop (−25/−35/−50 by premium band) on exit-A's body** — tests T2/T4's band refinement; needs one new knob (entry-time band-resolved stop). Drop if no lift over exit-A.
3. `exit-C` **−35/+50/sell80/trail15/2.5x — PAIR-ONLY with entry-2** — standalone it's weak (exp $13.19, rank 609/2016); T3 shows it wins only WITH the passive limit entry (+$25–65 net of misses).

**Entry (≤2):**
1. `entry-1` **market + premium_floor $0.30** — cheapest change (control exp $22.91 → $36.62 at the floor).
2. `entry-2` **limit−10%/patience-3/cancel + floor $0.30** — passive headroom, paired with exit-C only.

> **v1→v2 amendment (Fable review, 2026-07-08 late, BEFORE sign-off/OOS):** v1's exit-1 (−30/+50/sell80/trail15) was registered without quoting its own cell — which is exp **$7.42, drop-top-3 −$2.78 (negative), qpf 0.5, rank 830/2016**: already failing in exploratory. Replaced. Full rationale in the pre-registration's `amendment_log`.

---

## DISCLOSURES & WHAT'S OWED (nothing hidden)

- **Frictionless** fills at trigger levels (no spread/queue); **5-min OPRA** bars (touch stops; **1m-close stop timing owed on live data**); **premium-only replay** (ribbon/level/chart exits OFF, same as the anchor tool); **qty-10 absolute $ ignore the kill switch + per-trade cap** → relative-to-control and the real-fill anchor are the trustworthy signals, absolute $/tr is optimistic.
- **ribbon_ride ONLY.** vwap_continuation is a separate setup path the generic backtest doesn't emit → **its entry/exit matrix is owed** (ground rule 11, per-strategy scope).
- **ATR-scaled + delta-mapped chart stops omitted** — not expressible in real-fills mode (no per-fill delta; same gap `strategy_space_grind` documents). Not faked.
- **P5 gate:** every exploratory winner is a **non-survivor** — the P5-hard-gate ([test_p5_shape_gate.py](../../backtest/tests/test_p5_shape_gate.py)) will BLOCK any of them from arming until it passes a fresh P5 grind or J signs a waiver. The two CURRENT live shapes are on **PROVISIONAL (unsigned) waivers** ([p5-shape-waivers.json](../../automation/state/p5-shape-waivers.json)) — **J to sign, replace (via T5), or retire.**
- **Effective-n:** 250 unique signals (191 bear / 59 bull); T2 pooled 1,451 positions across strikes but reports unique-signal counts (ground rule 8).

## THE STOP (ground rule 5 + DoD #5)

**No live/paper exit-shape or entry-path change ships without this checkpoint's sign-off.** T5 (confirmatory OOS + scorecards) and T6 (fleet paper A/B) are BLOCKED until then. If you approve, the next executor runs T5 on the pre-registered list → produces `analysis/recommendations/entry-exit-matrix-{date}.json` A/B scorecards → **STOP CHECKPOINT B**.

---

## DoD status (handoff §DEFINITION OF DONE)

1. ✅ `engine-contract.md` exists, auto-regenerated (folded into Gamma_FirmBrief), drift-guard RED-proofed & green.
2. ✅ T2 diagnostics report with per-band tables exists; T3/T4 grids cite it.
3. ✅ T3+T4 ran on the **full OPRA population** (250 signals, not the 17); filed with fill-model disclosures, drop-top-3, per-band splits; P5-hard-gate guard red-proofed & green.
4. ✅ This STOP A package delivered (NOT acted on). Pre-registration frozen for T5.
5. ✅ Zero live/paper shape or entry-path changes. No grid knob tuned after seeing OOS (OOS not yet run). No position-count quoted as n.

_Commits: T1 `c11aa1d` · P5-gate `d7d9ae2` · T2 `d8581a6` · T4 `df6ed7b` · T3 `7d81b22` · this package (below)._

---

## FABLE REVIEW ADDENDUM (2026-07-08 late — read before signing)

The execution above was independently re-verified. **The core finding STANDS** — anchor parity confirmed (actual realized on the 79 positions **−$893** vs replayed control **−$757**: the replay measures the real book) and the ranking survives the entry-bar sensitivity probe (skipping bar 0 moves the leaders ≤$0.65 and actually *improves* control +$12.63 — the bias ran against the winners' favor, not for it). Corrections made in this review, all committed:

1. **P5 gate read 15 of 86 survivors** (truncated summary instead of `mass-grind-phase5.jsonl`) — fixed; scar re-verified against the FULL 86 (still 0 hits — the waiver justifications stand, now stronger).
2. **The old grind's lock/trail axis was a DEAD KNOB** — orchestrator never translated `profit_lock_mode`/`profit_lock_trail_pct` from overrides (L342-346 translate only tp1/frac/target); **181/181 fixed-vs-trailing P4 pairs are byte-identical**. The entire P5 universe never tested trailing. T4 (which drove exit_manager directly) is the FIRST genuine trailing sweep. Any fresh grind must pass lock/trail as **kwargs**.
3. **The engine-contract card §3 was wrong-in-production**: with `GAMMA_CORE_MANAGES_EXITS=1` (run-heartbeat-core.ps1:12), control arms register the **strategies.py ribbon_ride shape** for generic ribbon entries — params tp/stop are plan-log values (options can't bracket). Card corrected + entry-policy section added (`ask + $0.03` marketable, no floor, no patience).
4. **New two-lane discrepancy surfaced by the corrected card:** `vwap_continuation` trades **−8%/+30%** on fleet arms (strategies.py) but **−6%/+40%** on core arms (params keys `j_vwap_cont_*`). Same strategy, two shapes. Provenance owed — J decision or T5 scope.
5. **Pre-registration amended to v2** (before sign-off/OOS — see amendment_log): v1's exit-1 was already dead in its own exploratory cell (drop-top-3 negative, rank 830/2016).
6. **T5's holdout was undefined in v1** (the exploratory window incl. its internal "OOS" is burned — it was visible during ranking). v2 defines 4 confirmatory layers: fresh OPRA slice (≥2026-06-19), growing real-fills anchor, fresh P5 grind (trail wired), 2-week forward paper.
7. T2's percentile column relabeled to the **worst-quartile** (deep tail: MAE-10m worst-q −43%/−35%/−32%/−27% by band); T4 anchor now states **17 unique signals / 7 days / one regime** (ground rule 8).

**Execution grade: the work is sound and honest; every defect found was in instrument completeness or labeling, none in the direction of the finding.** Next executor's work order: [`HANDOFF-2026-07-11-CONFIRM-AND-WIRE.md`](HANDOFF-2026-07-11-CONFIRM-AND-WIRE.md).
