# WATCHER-LANE GATE-PROVENANCE AUDIT — 2026-08-23

> Spawned by [[analysis/deep-research/WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19|WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19]] §2 item #4
> ("AUDIT THE PROVENANCE OF THE NON-RIBBON 'WATCHER' LANE — governance, not a filter"). That doc's own
> kill criterion for opening this audit: *"if the audit surfaces a ratification record with
> popA-equivalent depth, close the question and leave the families alone. If it surfaces none, they
> belong in shadow until they have one — but that is J's call, not something this data supports as a
> statistical filter."* This document is that audit. Read-only investigation; nothing armed or disarmed
> here. Disposition is J's call (or Opus adjudication) — this file reports evidence, not a verdict.

---

## ⛔ CORRECTION TO THE AUDIT PREMISE — 2 of the 4 named families are NOT currently armed

The audit request assumed all four families (BOLLINGER_SQUEEZE, VIX_REGIME_DAYSIDE,
VWAP_RECLAIM_FAILED_BREAK, VWAP_CONTINUATION) are "currently able to place live orders." Read fresh
from `automation/state/params.json` (the source of truth per CLAUDE.md — "rule mismatch = kill-switch
event") plus real-fill dates in `journal/trades.csv`, that is only true for **2 of the 4**:

| family | `extra_setup_exec_armed` value | last real fill | currently order-capable? |
|---|---|---|---|
| BOLLINGER_SQUEEZE | `true` | 2026-08-20 | **YES** |
| VWAP_RECLAIM_FAILED_BREAK | `true` | 2026-08-20 | **YES** |
| VIX_REGIME_DAYSIDE | `false` (disarmed 2026-07-25) | 2026-07-21 | **NO** — WATCH_NOT_ARMED |
| VWAP_CONTINUATION | `false` (disarmed 2026-07-25 core; fleet-enforced 2026-08-12) | 2026-08-12 | **NO** — WATCH_NOT_ARMED |

Both disarms are already-executed governance actions (`params.json` line 323,
`_extra_setup_exec_armed_disarm_doc_2026_07_25`), not something this audit is proposing. The real-fill
cutoff dates (2026-07-21 and 2026-08-12) line up exactly with the disarm commits, confirming the params
read is live-accurate, not stale documentation. **The per-family findings below still cover all four
(as asked), but the disposition question for VIX_REGIME_DAYSIDE and VWAP_CONTINUATION is "should they
stay disarmed / get a real prereg before any re-arm" — they are not bleeding money today.**

---

## Per-family verdict table

| Family | Armed where (file · key) | Which arms | Ratifying artifact(s) | Evidence scale | Verdict |
|---|---|---|---|---|---|
| **BOLLINGER_SQUEEZE** | `automation/state/params.json`: `bollinger_squeeze_enabled=true` + `extra_setup_exec_armed.bollinger_squeeze=true`. Armed 2026-07-02, commit `004e7eaa` "WIRE-BOLLINGER". | Safe-2 core only (`heartbeat_core.py` dispatch). **Absent from `strategies.py` REGISTRY → fleet arms (safe-3/risky-1/risky-3) never trade it.** Bold/aggressive never armed (doc-confirmed, no key in `aggressive/params.json`). | `analysis/recommendations/family-grind-bollinger_squeeze.json` (2026-06-25) + `bollinger-squeeze-fresh-reverify.json` (2026-07-02 re-verify) | **POPULATION-SCALE.** Full history 2025-01-01..2026-07-01 (373 trading days), n=303→325 raw signals / n=312 scored, IS(2025)/OOS(2026) split, WF 1.443–1.588, OOS+ on both the original grind and the fresh re-verify, positive quarters 6/6–7/7, dir-null PASS (`family_directional: false`), port-parity PASS. **Closest of the four to popA-equivalent depth.** | **RATIFIED** — real population-scale evidence, independently re-verified once. Gap: predates the OP-11 4-part auto-ratify bar (no `anchor_no_regression` check against the *current* live book, no BH-FDR sibling comparison) — it was validated under the project's earlier "family-grind" P1→P4 methodology, not the newer G1-G8/auto-ratify apparatus used since ~2026-08-06. |
| **VIX_REGIME_DAYSIDE** | `automation/state/params.json`: `j_vix_dayside_enabled=true` but `extra_setup_exec_armed.vix_regime_dayside=false` → **currently WATCH_NOT_ARMED.** Was armed 2026-07-01, disarmed 2026-07-25 (`_extra_setup_exec_armed_disarm_doc_2026_07_25`). | Was Safe-2 core only — never in `strategies.py` REGISTRY, never armed on Bold. | `analysis/recommendations/b5-vix-regime-dayside.json` + `vix_regime_dayside.json` (2026-06-21) | **REAL-FILLS SCALE, not population-scale.** n=76 total / n=21 OOS. 8/8 of the project's contemporaneous anti-cherry-pick gates (n≥20, OOS>0, IS-H1>0, ≥4/6 positive quarters, drop-top5>0, beats coin-flip AND same-day null, no-truncation) — a real, disclosed battery, but an order of magnitude short of population depth. | **THIN at arm-time; LIVE-FALSIFIED on arrival.** 5 live paper trades, 0% WR, −$153 (params.json disarm note). Disarmed same week as vwap_continuation for the same reason. **Correctly already in shadow.** |
| **VWAP_RECLAIM_FAILED_BREAK** | `automation/state/params.json`: `j_vwap_reclaim_fb_enabled=true` + `extra_setup_exec_armed.vwap_reclaim_failed_break=true`. Armed 2026-07-01 (Safe-2), extended to fleet 2026-08-04 (`FLEET-VWAP-RECLAIM-EXTENSION-RISKY3`, prereg frozen before arming). | Safe-2 core (ATM cell) **+ fleet arms** (risky-1, risky-3, safe-3 via `strategies.py` REGISTRY, each arm's own gate/sizing applies). Bold/aggressive: **DORMANT** (`aggressive/params.json` `j_vwap_reclaim_fb_enabled=false`, WATCH_ONLY per OP-21 pending 3 live J confirmations). | `analysis/recommendations/RECLAIM-RESCUE-SCORECARD.md` + `sub-struct_vwap_reclaim_failed_break.json` + `SUBTRACTIVE-SELECTION-SCORECARD.md` (2026-06-21) | **REAL-FILLS SCALE.** n=76, OOS(2026) n=18 +$32.33/tr, **independently reproduced to the cent by a second metric+gate harness** (not the author's own `evaluate_cell`) — the single strongest real-fills-tier study of the four. Self-disclosed soft spot: OOS/tr sits *below* the same-day random-entry null mean → "the OOS lift is largely day+side SELECTION, not reclaim-trigger precision" (scorecard's own words). | **THIN by population-depth standard** (n=76, same order as VIX_REGIME_DAYSIDE) **but the best-evidenced of the three real-fills studies**, with its own limitation disclosed rather than hidden. See live-vs-backtest gap below — this is the one worth the most scrutiny right now. |
| **VWAP_CONTINUATION** | `automation/state/params.json`: `extra_setup_exec_armed.vwap_continuation=false` → **currently WATCH_NOT_ARMED on every path.** Core-disarmed 2026-07-25 (commit `e0356fb1`); fleet path kept trading it 18 more days on a params-read gap the fleet executor never consulted (own docstring: "43 fills after the disarm date... still filling on 2026-08-12"), closed by commits `e816178d`/`e3a44956` on 2026-08-12. Zero fills since (`journal/trades.csv` last row 2026-08-12). | Was Safe-2 core + fleet arms (risky-1, risky-3 — the leak itself proves fleet membership). Bold/aggressive: dormant since the 2026-06-21 qty-floor kill (CHANGELOG), never re-armed. | `analysis/recommendations/j-daily-pattern-LIVE.json`, `vwapcont-exit-ab-ship-gate.json` (multiple studies, n=149–153) | **REAL-FILLS SCALE**, largest n of the four (149–153) — but **self-graded as incomplete by its own arming doc**: `params.json`'s `_j_vwap_cont_doc` literally calls it a *"6-of-7 OP-22 NEAR-SURVIVOR... MISSES strict all-cuts-OOS-positive"* before it was armed. | **THIN by its own author's admission at arm-time, and LIVE-FALSIFIED twice**: core disarmed 2026-07-25 after 0-for-12 (−$357); fleet leaked another −$1,046 for 18 more days on a governance/plumbing gap, not a re-approval. **Already correctly disarmed.** See the stalled kill-check prereg below — a second, more specific problem. |

---

## Does ANY deep population exist that can validate the watcher families?

**Confirmed, quoted verbatim, exactly as the task asked:** `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json`
(`cells_frozen.VWAP_EXPLORATORY_WEEK_ONLY.SHIP_ELIGIBILITY`):

> "NONE. popA cannot test vwap (ribbon-family population). These cells are DESCRIPTIVE / n-small
> labeled, ineligible to ship from this study REGARDLESS of gates. Frozen now."

`popA` there is the 391-day, n=191, real-OPRA, entries-frozen replay population
(`analysis/recommendations/engine-fullhist-replay-2026-07-23.json`) — the deepest population this repo
owns, and it is built **exclusively from ribbon-family entries** (`BEARISH_REJECTION_RIDE_THE_RIBBON` /
`BULLISH_RECLAIM_RIDE_THE_RIBBON`). It structurally cannot score a VWAP-family or Bollinger-family
signal because those setups never fire in that population's entry stream. The same TP1-reachability
prereg's `popB` (the 4-session real-broker-fills week) is genuine cross-family evidence but is, by its
own admission, "single-day week numbers are anecdote-scale by construction" — not depth, breadth.

**The plain finding:** with the single exception of BOLLINGER_SQUEEZE — which has its own,
independently-built 373-day full-history population (`family-grind-bollinger_squeeze.json`, a different
lineage from popA but comparable in span) — **no deep population in this repo can validate any of the
other three watcher families.** VIX_REGIME_DAYSIDE, VWAP_RECLAIM_FAILED_BREAK, and VWAP_CONTINUATION
were each ratified on a one-off real-fills-scale backtest (n=76–153) run once in June/July 2026 and
never revisited at population scale. That is not a defect unique to this repo's process — real-fills
studies are the correct methodology for a shape that only exists in the live book's own entry stream —
but it means their evidentiary depth is a full order of magnitude short of what ribbon-family decisions
get to lean on, and no mechanism in this codebase currently closes that gap.

---

## Two things this audit surfaced beyond the ratified/thin/no-record table

### 1. The 2026-08-18 vwap_continuation kill-check prereg is stalled and cannot complete

`analysis/recommendations/vwap-family-killcheck-prereg-2026-08-18.json` is a live, `FROZEN_PREREG_FORWARD`
mechanism study asking whether vwap_continuation's entries produce a right-tail at all (MFE-based, not
P&L-tuning — a legitimate, well-designed question). Its measurement protocol says:

> "vwap_continuation keeps trading paper unchanged through the window -- TRADE-TO-LEARN standing. The
> forward evidence is the paper fills themselves." ... window: "the next 20 sessions with at least one
> vwap_continuation fill, OR n>=25 forward scored positions, whichever comes first."

But `extra_setup_exec_armed.vwap_continuation` has been `false` on **every execution path** since
2026-08-12 — six days *before* this prereg was frozen — and `journal/trades.csv` confirms zero
vwap_continuation fills since. **The prereg's forward gate (K3: n≥25 forward positions) can never be
met while the strategy stays disarmed; its `verdict_ladder` is permanently stuck at `EXTEND`.** This
looks like a documentation/awareness gap at freeze time (the author either didn't check current arm
status or expected a re-arm that never happened) rather than a deliberate design. Flagging it here so a
future session doesn't read "prereg open, in progress" and assume evidence is quietly accumulating — it
is not, and cannot, under the current state.

### 2. VWAP_RECLAIM_FAILED_BREAK's live win rate has diverged sharply from its ratifying backtest

The ratifying scorecard (`RECLAIM-RESCUE-SCORECARD.md`) measured WR 55.3% / OOS +$32.33/tr on n=76
backtest fills. Per the parent synthesis doc's fresh recompute (2026-08-19, all 303 real round trips),
live real fills for this family are **n=8, WR 12.5%, net −$419.49** — armed and currently the family
still bleeding the most per-trade of anything still live. This is exactly the kind of live/backtest gap
the disclosed "day+side selection, not trigger precision" caveat in the original scorecard predicted
could happen, but n=8 live is too small to call it confirmed or refuted on its own — it is a small-n
warning sign layered on top of an already-thin (n=76) ratification, not a verdict.

---

## Recommended disposition per family (advisory — J's / Opus's call, not executed here)

- **BOLLINGER_SQUEEZE — keep armed.** The one family with population-scale ratification. Worth a cheap
  follow-up: an `anchor_no_regression`-style check of its current 17 live fills against the fresh-reverify
  cell, since ~7 weeks have passed since the last re-verify and no one has looked since.
- **VIX_REGIME_DAYSIDE — leave disarmed.** Already correctly in shadow since 2026-07-25. Do not re-arm
  without a population-scale prereg first — it never had one, only n=76 real-fills, and it live-falsified
  immediately (0-for-5).
- **VWAP_RECLAIM_FAILED_BREAK — the contestable one.** Best-evidenced of the three real-fills-tier
  families (independently reproduced 8/8 gates) but still an order of magnitude short of population
  depth, still armed, and its 8 live fills so far run far below the backtest's win rate. This is the
  family where "keep armed" vs "move to shadow pending a population-scale prereg (same shape as the
  2026-08-18 vwap_continuation kill-check)" is a genuine judgment call — flagging for J/Opus rather than
  defaulting either way.
- **VWAP_CONTINUATION — leave disarmed**, and separately: either re-arm it specifically to let the
  2026-08-18 kill-check prereg gather the forward evidence it was designed to collect, or mark that
  prereg `VOID_STALLED` so it stops reading as "in progress" to the next session. Doing neither leaves a
  live-looking instrument silently measuring nothing.

---

## Verification notes

- Every artifact path cited above was opened and read this session (not recalled from doc prose).
- Arm status was read fresh from `automation/state/params.json` and `automation/state/aggressive/params.json`
  on 2026-08-23, cross-checked against real fill dates in `journal/trades.csv` (independent confirmation
  the params read isn't stale).
- `strategies.py` REGISTRY membership was read directly (`automation/state/fleet/strategies.py:198`) to
  determine fleet-arm applicability, not inferred from doc comments.
- Scope discipline: this audit does not propose, and explicitly rules out per the task, any P&L-based
  kill of the lane — §3.6 of the parent synthesis already refuted that framing (64% of the lane's
  deficit concentrates in one day, 2026-08-05).

---

[[analysis/deep-research/WINNERS-AND-LOSSES-SYNTHESIS-2026-08-19|parent synthesis]] ·
[[analysis/deep-research/TP1-REACHABILITY-2026-08-06|TP1 reachability prereg (the popA-cannot-test-vwap source)]] ·
[[MAP|MAP.md]]
