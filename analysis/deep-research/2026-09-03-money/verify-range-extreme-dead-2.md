# VERIFY (REPRODUCTION lens) — H2 DEAD COMPONENT (range-extreme-dead)

**Stamp:** 2026-09-03T10:53 ET (`et_clock.py` confirms `market_hours=True`). Read-only throughout — no broker/network calls, no edits to `conviction.py`, `heartbeat_core.py`, or any trading-path file.

**Verdict: SUPPORTED, with one confirmed inaccuracy in a secondary (non-decision-bearing) table.** The finding's core claim — C4 `range_extreme` fires 0/482 post-fix, for a structural polarity-mismatch reason, not a coding bug — is reproduced exactly, including the dollar-effect counterfactual and its bootstrap CI down to the individual trade and the cent. One table in the original report ("Empirical distribution, Parts 2-3") is mislabeled: it presents numbers from a different (larger) population than the one its own prose claims.

---

## Method

Independent script: `backtest/tools/money_verify_range_extreme_dead_2.py`. Does **not** import `conviction.py`, `conviction_shadow_report.py`, or `fills_fifo.py` for the population/join logic (only imports `conviction.py` for one standalone Part-1 spot-check, run separately at the terminal, not inside the script). Re-parses the 5 raw decision ledgers and raw `fills-ledger.jsonl` from scratch, reimplements the FIX_BOUNDARY partition, the FIFO round-trip miner, and the ±120s greedy join independently.

`FIX_BOUNDARY_ET` independently re-derived: `git log --format='%h %ad %s' --date=iso-strict -1 974ca235` → `2026-08-14T17:15:22-06:00` (box is Mountain, no DST split in August) → `+2:00` → `2026-08-14T19:15:22` ET. Matches the finding's constant exactly.

## What reproduced exactly

| Claim | Finding | My reproduction | Match |
|---|---|---|---|
| n post-fix, dates ≤2026-09-02 | 482 | 482 | ✅ |
| Fleet ledgers (risky-1/risky-3/safe-1/safe-3) conviction-row count | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | ✅ |
| `range_extreme` hit rate, 482-row population | 0/482 (0.0%) | 0/482 (0.0%) | ✅ |
| `range_extreme` degraded count, 482-row population | 0 | 0 | ✅ |
| Part-1 code-correctness (score_conviction arithmetic) | 5/5 synthetic cases pass | Spot-checked 2 of the 5 cases directly (call@pos0.05→1, call@pos0.95→0) | ✅ |
| Counterfactual flips block→allow (482-row population) | 47 | 47 | ✅ |
| Counterfactual flips allow→block | 0 | 0 | ✅ (structurally guaranteed — score can only move +0/+1) |
| Outcome-joined newly-allowed trades | n=5 | n=5, **identical 5 rows** (same ts_et, account, side, pnl, pos, orig_total, floor) | ✅ |
| Sum / mean / WR | −$148 / −$29.60 / 20% | −$148.00 / −$29.60 / 20.0% | ✅ |
| Bootstrap 95% CI on mean (n=5) | [−$93.00, +$66.40] | [−$93.00, +$66.40] (own 5,000-resample bootstrap, seed 42, different RNG implementation) | ✅ |
| session envelope computed *through* the trigger bar (mechanism) | `_sess = win.iloc[:trig_idx+1]` | Confirmed by direct read of `heartbeat_core.py:941-950` | ✅ |
| Part-4 polarity-flip logic can only ever raise the score | qualitative claim | Confirmed: current rule reads 0 on literally every row in this population (by construction, since hit rate is 0%), so `new_total = total - 0 + fixed_re ≥ total` always | ✅ |

The $-effect evidence — the only number in this finding that could matter for a "money" decision — reproduces to the cent, including which 5 specific trades compose it and the CI. This is the strongest part of the finding and it holds up completely under independent re-derivation from raw `fills-ledger.jsonl` (own FIFO miner, own join, own bootstrap).

## What did NOT reproduce: population mislabeling in the "Empirical distribution" table

The report's Parts 2-3 table (`range-extreme-dead.md` lines 55-62, and `range-extreme-dead.json`'s `empirical_distribution.by_side`) states:

> "post-fix rows only (`ts_et >= 2026-08-14T19:15:22`), **n=482 to match the report exactly**"

and then presents:

| side | n | pos min | pos mean |
|---|---|---|---|
| C | 270 | 0.336 | 0.812 |
| P | 242 | 0.000 | 0.138 |

I reproduced this table two ways:

- **Restricted to the actual 482-row population** (dates ≤ 2026-09-02, matching the shadow report's own generation timestamp `2026-09-02T16:33:44`): **C n=240, min=0.445, max=1.000, mean=0.819**; P n=242, min=0.000, max=0.445, mean=0.138 (P is unaffected).
- **Unrestricted, live as of today** (2026-09-03, market open): **C n=270, min=0.336, mean=0.812** — this exactly matches the numbers the report printed under its "n=482" claim.

The extra 30 calls are today's (2026-09-03) live session, confirmed directly: `dates after 09-02: ['2026-09-03'] count: 30`. The report's own JSON (`range-extreme-dead.json`) does separately label `n_post_fix_rows_report_matched: 482` and `n_post_fix_rows_live_at_probe_run: 512` in its `_meta`/`empirical_distribution` header and says both would be "reported BOTH ways" — but only **one** `by_side` table is actually present, and it is the 512-row (live) one, not the 482-row (report-matched) one its own prose claims. This is an internal inconsistency: the number 270 is real and correctly computed, but it is not the number the surrounding text says it is.

**Materiality:** low for the verdict, real for precision. The qualitative conclusion — calls cluster near the *top* of the range (rule needs bottom), puts cluster near the *bottom* (rule needs top), zero overlap with the threshold either way — holds identically under both populations (0.819 vs 0.812 mean for calls; identical for puts). The decision-relevant Part-4 counterfactual ($-effect, CI, flip counts) **did** correctly use the 482-restricted population throughout (independently confirmed above) — the mislabeling is confined to the descriptive min/mean/n table in Parts 2-3, which does not feed the counterfactual math.

## A second, smaller inaccuracy: "100% of C/P rows" overstates setup homogeneity

The report states (both `.md` root-cause paragraph and `.json` `root_cause.one_sentence`) that the two named triggers are "100% of C/P rows." Within the correctly-restricted 482-row population, **19 rows (2 calls, 17 puts) carry `setup: null`**, not one of the two named setups. I traced all 19: every one is a `SKIP_STRUCTURE_VETO` verdict (conviction is shadow-scored on any sided verdict, not only `ENTER` — `setup` is apparently only assigned once a verdict clears to a named entry), firing on `trendline_rejection` / `level_reclaim` / `confluence` triggers — the same conceptual trigger family the report's mechanism describes, just vetoed before being named. This does not contradict the causal mechanism (these rows are still continuation-shaped, structure-vetoed variants of the same setups), but "100%" should read "~96% (463/482) by name; the remaining 19 are same-trigger-family rows blocked pre-naming by the structure veto."

## Independently re-verified, unchanged from the finding

- **Fleet coverage gap** (0 conviction rows in all 4 fleet ledgers, both pre- and post-fix): confirmed, own parse of all 4 fleet `decisions.jsonl` files, 0 rows containing `"conviction"` in any of them.
- **Cannot have blocked a winner**: structurally re-confirmed — since the current (unflipped) rule scores `range_extreme=0` on all 482 rows, `new_total` can only equal or exceed `total`, so `would_block` can only flip BLOCK→ALLOW, never the reverse. This is not an empirical claim, it is guaranteed by the arithmetic (`new_total = total − orig_re + fixed_re`, `orig_re` is always 0 here, `fixed_re ∈ {0,1}`).
- **08-27 marginal newly-allowed loser** (`2026-08-27T09:47:05`, bold, call, −$40): present in my independently-joined trade list, byte-for-byte.
- **No trading-path file touched**: confirmed via this session's own edits — only `backtest/tools/money_range_extreme_probe.py` (prior agent), `backtest/tools/money_verify_range_extreme_dead_2.py` (this script), and files under `analysis/deep-research/2026-09-03-money/` were written this session.

## Bottom line for the parent decision

Nothing here changes the SUPPORTED verdict or the `INSTRUMENT_ONLY` / no-live-change conclusion. The dollar evidence (n=5, CI straddles zero, inconclusive) is real and independently reproduced exactly. The one defect found — a mislabeled population in a descriptive table, plus a "100%" that should be "~96%" — is a report-precision issue, not a refutation of the mechanism or the counterfactual math. Recommend the original report's Parts 2-3 table be corrected to either (a) explicitly use the 512-row live population and drop the "n=482 to match the report exactly" framing, or (b) swap in the true 482-row numbers (C: n=240, min=0.445, mean=0.819).

## Files

- Independent script: `backtest/tools/money_verify_range_extreme_dead_2.py`
- Its raw JSON output: `analysis/deep-research/2026-09-03-money/verify-range-extreme-dead-2.json`
- This note: `analysis/deep-research/2026-09-03-money/verify-range-extreme-dead-2.md`
