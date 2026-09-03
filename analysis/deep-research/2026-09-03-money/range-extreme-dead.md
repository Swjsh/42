# H2 DEAD COMPONENT — conviction.py C4 `range_extreme`, 0.0% hit rate

**Stamp:** 2026-09-03T10:24 ET (report generated 10:49 ET, `et_clock.py` confirms `market_hours=True` — live engine is running; read-only throughout, no broker/network calls, no edits to `conviction.py` or `heartbeat_core.py`)
**Verdict: SUPPORTED.** C4 is a dead knob — but not the "missing input" kind. It's fully wired, computes a real number every tick, and that number's population sits on the opposite side of 0.5 from what the threshold requires, for a structural reason.

---

## Root cause, one sentence

C4 `range_extreme` was calibrated on a **mean-reversion** exhibit (a bounce entry *at* the range low/high), but the two live triggers that feed it — `BULLISH_RECLAIM_RIDE_THE_RIBBON` and `BEARISH_REJECTION_RIDE_THE_RIBBON` — are **continuation** setups that structurally fire near the session extreme *in their own trade direction* (calls near the session high, puts near the session low), the mirror-opposite polarity from what the threshold rewards. So the threshold is mathematically reachable (0.30 / 0.70 are not impossible values) but **empirically unreachable for 100% of the current trigger taxonomy**.

This is the **third**, independent defect on this same component's short life:
1. 2026-08-12 — C2's `source.startswith("shelf")` vs `"daily_context_shelf"` substring bug (already fixed, per `conviction.py`'s own inline note).
2. 2026-08-14 (`974ca235`) — C4 read `bc.get("bars_prior")`, producer wrote `prior_bars`: a transposed key that degraded C4 on 102/102 rows since birth (already fixed).
3. **This one** — C4 now computes cleanly (0 degraded rows post-fix) but the threshold's *polarity* doesn't match the live trigger family's *shape*.

---

## Trace

**`setup/scripts/conviction.py:293-318`** (C4):
```
pos = (c - lo) / (hi - lo)
if s == "P" and pos >= (1.0 - RANGE_EXTREME_PCT):   # puts want pos >= 0.70
    rng = W_RANGE_EXTREME
elif s == "C" and pos <= RANGE_EXTREME_PCT:          # calls want pos <= 0.30
    rng = W_RANGE_EXTREME
```
Design rationale in the file's own comment (lines 293-296): *"Puts want the TOP of the envelope, calls the BOTTOM… distinguishes J's 12:35 bounce (a long at the range LOW) from the engine's 38 entries (longs fired mid-flush and at the range TOP)."* That's a reversal/bounce thesis.

**`setup/scripts/heartbeat_core.py:677, 940-950`** (the caller): `hi, lo = bc.get("session_high"), bc.get("session_low")` — computed as the trigger day's high/low **through and including the trigger bar** (`_sess = win.iloc[:trig_idx+1]`). This part is correct and intentional (fixed 2026-08-14 specifically to be session-scoped, not the 1.9-session 150-bar window). But it means the current bar's own high/low feed the envelope it's being measured against.

**The mismatch:** `RIDE_THE_RIBBON` triggers fire *after* a directional push has already happened. A `BULLISH_RECLAIM` call, by the time it triggers, has already pushed price up toward (or to) the session high — so `trigger_close` sits close to `session_high`, i.e. `pos` near 1.0. A `BEARISH_REJECTION` put has already pushed price down toward the session low — `pos` near 0.0. The C4 rule wants the opposite for each side.

---

## Vary-and-assert (`backtest/tools/money_range_extreme_probe.py`, Part 1)

Fed `score_conviction()` directly (no ledger, synthetic inputs) to prove the arithmetic itself is correct:

| case | pos | range_extreme | expected | pass |
|---|---|---|---|---|
| call at range low (pos=0.05) — textbook good | 0.05 | 1 | 1 | ✅ |
| put at range high (pos=0.95) — textbook good | 0.95 | 1 | 1 | ✅ |
| call at range high (pos=0.95) — textbook BAD per design | 0.95 | 0 | 0 | ✅ |
| call at exact threshold (pos=0.30, inclusive) | 0.30 | 1 | 1 | ✅ |
| missing `envelope_high` | — | 0 (degraded, not silent 0) | degraded | ✅ |

**All 5/5 pass.** The function does exactly what its docstring says. The defect is not here.

---

## Empirical distribution (Parts 2-3)

Read all 5 ledgers (`core-decisions.jsonl` + 4 fleet arms) the shadow report itself reads, post-fix rows only (`ts_et >= 2026-08-14T19:15:22`), n=482 to match the report exactly (n grew to 512 by the time this probe ran, because the market is open today, 2026-09-03 — reported both ways, see JSON).

| side | n | setup (100% of side) | pos range | pos mean | rule needs | hits under current rule | hits if polarity flipped |
|---|---|---|---|---|---|---|---|
| C (call) | 270 | `BULLISH_RECLAIM_RIDE_THE_RIBBON` | 0.336 – 1.000 | **0.812** | ≤ 0.30 | **0** | 192 |
| P (put) | 242 | `BEARISH_REJECTION_RIDE_THE_RIBBON` | 0.000 – 0.445 | **0.138** | ≥ 0.70 | **0** | 186 |

`degraded_components` never lists `range_extreme` post-fix (0/482) — this matches the report exactly and confirms the component is computing, not failing to compute. It just never crosses its own line.

---

## Fleet ledgers (task-specified check)

**0 conviction rows in all four fleet ledgers** (`risky-1`, `risky-3`, `safe-1`, `safe-3`) — not degraded, not zero-scoring, **absent**. `_conviction_shadow()` in `heartbeat_core.py` is called only on the core (safe-2/bold-2) tick path; the fleet arms' own executor (`build_shared_signal.py` / `fleet_executor.py`) never calls it. This matches the shadow report's own `"arms": ["core"]` field. Flagged as a **separate, broader** finding — the whole instrument, not just C4, has zero fleet coverage — but it is not part of the H2 verdict (there's no C4 reading on the fleet arms to be dead).

---

## Counterfactual: what a fix would change (Part 4)

Not a proposed live change — conviction has no `SKIP_LOW_CONVICTION` branch anywhere in the engine (`armed: false` in the report, confirmed). This answers the task's literal ask: re-score all 482 post-fix rows with C4's polarity flipped to match the live trigger family (call scores when `pos>=0.70`, put scores when `pos<=0.30` — i.e., "good location" redefined as *continuing in the direction that's already working*, not *bouncing off an extreme*).

- **47 / 482 (9.8%)** rows flip `would_block: True → False`. **0** flip the other way (score can only move +0 or +1 per row, since the current rule already reads 0 everywhere here — structurally cannot have blocked anything that currently clears the floor).
- Of those 47, **5** join to a real fill (±120s match, same join logic as the shadow report — conviction fires on every ENTER tick, most are shadow-scored duplicates with no adjacent order, so a 5/47 join rate is expected, not a data gap).

| ts_et | account | side | pnl | pos | orig total | floor |
|---|---|---|---|---|---|---|
| 2026-08-19 10:41:03 | safe | C | −$69 | 0.964 | 4 | 5 |
| 2026-08-19 10:41:06 | bold | C | −$105 | 0.964 | 4 | 5 |
| 2026-08-21 11:37:04 | bold | C | +$159 | 1.000 | 6 | 7 |
| 2026-08-27 09:47:05 | bold | C | −$40 | 1.000 | 5 | 6 |
| 2026-09-02 13:06:03 | safe | C | −$93 | 0.794 | 4 | 5 |

**n=5, sum −$148, mean −$29.60/trade, WR 20%.** Bootstrap 95% CI on mean pnl (5,000 resamples): **[−$93.00, +$66.40]** — straddles zero, **INCONCLUSIVE**. All 5 are calls (structural: puts in this population tend to sit >1 point below their floor when blocked, so a +1 nudge disproportionately flips calls that were already floor−1).

**Big winning days (08-06, 08-13, 08-27, 08-28):**
- 08-06 / 08-13 predate the fix boundary — not in this population; C4 was 100% degraded there regardless.
- 08-27 / 08-28 are in-population. Because the flip only ever *adds* a point, it **cannot** have blocked any entry that already cleared the floor on those days (structural, not empirical). It does newly-*allow* one marginal entry on 08-27 (09:47:05, bold call, −$40) that the unflipped rule correctly still blocks today. Net effect on winning days if this were ever armed: **adds one loser, touches zero winners.**

---

## Classification (Lessons C14)

**Dead knob, "translated-but-unapplied" subclass** — fully wired, computes a real value every tick, never crosses its own threshold because the threshold's *polarity* was calibrated against a different trade shape (mean-reversion) than the live trigger family produces (continuation). Distinct from a degraded/missing-input dead knob and distinct from the two prior coding defects on this same component (substring bug, transposed key) — this one is a **calibration/design** defect, not a coding defect, and code changes alone (without re-examining the polarity assumption against the live setup taxonomy) won't fix it.

---

## Files

- Probe (read-only, vary-and-assert): `backtest/tools/money_range_extreme_probe.py`
- This report: `analysis/deep-research/2026-09-03-money/range-extreme-dead.md`
- Machine-readable: `analysis/deep-research/2026-09-03-money/range-extreme-dead.json`

## Caveats / what this is NOT

- Not a live-change proposal. No file on the trading path was touched or is being recommended for a change today; the config freeze (through 2026-10-30) is irrelevant here since conviction is fully shadow.
- The n=5 outcome-join is far too thin for any decision (CI straddles zero) — reported because the task asked for a dollar effect with a CI, not because it's evidence either way.
- VIX regime split was not meaningful at n=5 (would be 1-2 trades per bucket) and is omitted for that reason rather than computed and over-interpreted.
- "Flipped polarity" is one candidate redesign among several (e.g. a `location_source`-style dual rule, or retiring C4 in favor of a rule keyed to the trigger family itself) — this report characterizes the mechanism and quantifies one counterfactual, it does not select a design.
