# VERIFY — H2 range-extreme-dead (skeptic pass)

**Stamp:** 2026-09-03T10:53 ET (`et_clock.py`, `market_hours=True`) through ~11:05 ET. Read-only throughout — no writes to `automation/state/**` or `journal/**`, no broker/network calls, no edits to `conviction.py`/`heartbeat_core.py` or any other forbidden file.

**Verdict: NOT REFUTED — CONFIRMED.** Every checkable numeric claim in `range-extreme-dead.md`/`.json` was independently reproduced from a **second, from-scratch implementation** (own JSONL parser, own greedy fill-join, own bootstrap with a different RNG seed) — not merely a re-run of the original probe. All figures matched to the cent.

---

## What I verified, and how

### 1. Re-ran the original probe verbatim
`python backtest/tools/money_range_extreme_probe.py` reproduces the report exactly: n=482 (report-matched population), 47/482 would-block flips, 5 joined trades with pnls `[-69, -105, +159, -40, -93]`, sum -148, mean -29.60. Confirms the script itself is deterministic and matches its own JSON output — necessary but not sufficient (a bug shared between report and re-run would survive this step).

### 2. Independent re-implementation (the real test)
Wrote `verify_range_extreme.py`/`verify_range_extreme2.py` in the scratchpad — new parser reading `core-decisions.jsonl` directly (not importing `conviction_shadow_report.py`'s `load_rows`), new join logic against `fills_fifo.mine_real_arm_fills` (not importing `_attach_outcomes`), new bootstrap (seed=42, 5000 resamples, different from whatever seed the original used).

- **n=482** rows reproduced exactly (own date filter `<= 2026-09-02`, own post-fix boundary).
- **orig_re == 0 for all 482 rows** — confirms the "flip can only add, never subtract" structural claim empirically, not just by code-reading.
- **47 flip rows** (would_block True→False) — exact match.
- **First attempt at the join produced n=6, not 5** — a real discrepancy I chased down rather than reporting blind. Root cause: my first join restricted the candidate pool to only the 47 flip rows, so a flip row (2026-09-02T11:20:05, bold, NOT_FLAT re-score of an *already-open* position) won a match against a round trip that the report's own methodology correctly gives to a *closer, non-flip* row (2026-09-02T11:19:04, PLACED, gap 1.8s vs. 59.2s) one minute earlier. The report's join is a **global** greedy match across all 482 candidate rows (competing for each round trip against every conviction row, not just the subset of interest) — this is the methodologically correct way to avoid the "many-to-one" double-count the module's own docstring warns about (11 real round trips → 34 false joins, the 2026-08-16 class of bug). Once I fixed my script to match that methodology, **n=5, sum=-148.00, mean=-29.60, wins=1, bootstrap 95% CI [-93.00, 66.40]** — exact match to the report, via genuinely independent code. This self-correction is itself evidence the report's join logic is the *correct* one, not merely unchallenged.
- **Total global join count (all 482 rows → real fills): 35** — matches `post_fix_outcomes.n_joined: 35` in the shadow-report population used by the H2 investigation, confirming apples-to-apples reproduction (the *live* file on disk now reads n=512/n_joined=39 because today, 2026-09-03, is a live trading session and rows keep accumulating — consistent with the report's own caveat #1).

### 3. Code and file-system facts, checked directly (not taken on the report's word)
- `conviction.py:293-318` C4 logic, `RANGE_EXTREME_PCT = 0.30` — read directly, matches the report's quoted logic verbatim.
- `heartbeat_core.py:940-950` — `session_hi`/`session_lo` computed as `_sess = win.iloc[:trig_idx+1]` filtered to the trigger day, i.e. **causal**, sliced through the trigger bar only. No look-ahead. Confirms the report's mechanism claim and its own look-ahead-risk disclosure.
- `heartbeat_core.py:568,648` — "conviction is disarmed... there is no SKIP_LOW_CONVICTION" is literal text in the file. `grep -n SKIP_LOW_CONVICTION` finds it nowhere as a live branch. Confirms `armed:false`/no gating claim.
- `automation/state/fleet/{risky-1,risky-3,safe-1,safe-3}/decisions.jsonl` — `grep -c '"conviction"'` returns **0** for all four. Confirms the fleet-coverage-gap finding directly, independent of the probe script.
- `core-decisions.jsonl` — `grep -c '"conviction"'` = 11,718 of 37,541 lines. Sane.
- `git diff --stat` against every forbidden trading-path file (`conviction.py`, `heartbeat_core.py`, `params.json` x2, `filters.py`, `risk_gate.py`, `exit_manager.py`) returns **empty**. `git status --porcelain` shows only the new untracked probe script and the new `2026-09-03-money/` dir. Confirms zero edits to the trading path, as claimed.
- `git show 974ca235` — commit exists, authored 2026-08-14 17:15:22 -0600 (= 19:15:22 ET, matches `FIX_BOUNDARY_ET`), message confirms the transposed-key root cause described. `conviction-shadow-report.json`'s `pre_fix_DO_NOT_POOL`: n=102, `degraded_components.range_extreme: 102` — **100% degraded pre-fix**, exactly as claimed.
- Current live `conviction-shadow-report.json` on disk (regenerated since the H2 report was written, now n=512 including today's session) still shows `component_hit_rate_pct.range_extreme: 0.0` — the 0% reading is not stale, it is current as of this verification pass.

---

## WINNER-KILLER / CONCENTRATION lens

**Would the characterized change have blocked or truncated 08-06/08-13/08-27/08-28, or the right-tail exits?**

Independently re-pulled the real round trips for `safe-2`+`bold-2` on 08-27/08-28 straight from `fills_fifo.mine_real_arm_fills` (not via the report's join):

| date | arm | symbol | entry | pnl | tag |
|---|---|---|---|---|---|
| 08-27 | safe-2 | ...C768000 | 09:41:03 | **+138** | WINNER |
| 08-27 | bold-2 | ...C770000 | 09:41:06 | **+95** | WINNER |
| 08-27 | bold-2 | ...C771000 | 09:47:07 | −40 | LOSER |
| 08-27 | bold-2 | ...C772000 | 11:53:05 | **+159** | WINNER |
| 08-27 | safe-2 | ...C771000 | 12:31:04 | **+184** | WINNER |
| 08-28 | safe-2 | ...C771000 | 10:21:04 | **+527** | WINNER |
| 08-28 | bold-2 | ...C773000 | 10:21:06 | **+509** | WINNER |
| 08-28 | bold-2 | ...P768000 | 13:01:09 | −215 | LOSER |
| 08-28 | safe-2 | ...P770000 | 13:01:10 | −270 | LOSER |

Cross-referenced all **17** C4-flip-eligible rows dated 08-27/08-28 (not just the 1 the report's join found) against this list directly. Confirmed: **exactly one** joins to a real fill (the 09:47:05 bold −$40 loser); the other 16 are unjoined shadow-scored duplicate ticks. **None of the six winners (138/95/159/184/527/509) is touched** — verified by checking every winner's own nearest conviction row: their `range_extreme` is already 0 either way (irrelevant to the flip) and none of them appears in the 47-row flip set. 08-06/08-13 confirmed pre-fix (not in either population). **The report's claim — "adds one loser, touches zero winners" — holds under independent re-derivation, not just under the original script.**

**≤3-trade / one-regime concentration check (done myself, not in the original report):**
- VIX at the 5 joined counterfactual trades: 15.33, 15.33, 15.28, 15.12, 15.43 — **all five sit inside one narrow band (15.1–15.5), the "15–17" bucket**. This is a single-regime artifact, not a diversified sample. The report's own decision to omit a VIX split ("would be 1-2 trades per bucket") is validated by this — a split literally couldn't produce more than one non-empty bucket.
- Top-3-by-|pnl| = `+159, −105, −93` (76.6% of gross dollar magnitude). Removing them leaves `{−69, −40}`, n=2, sum **−109** — still net negative. The sign of the (inconclusive) counterfactual effect is not an artifact of one or two extreme trades in either direction; it stays negative whether or not the top-3 are included, though at n=2-5 none of this should move a decision either way (matches the report's own INCONCLUSIVE framing).
- Per-arm split of the 5: safe×2, bold×3 — spans both core accounts, not concentrated in one.

**Incidental finding, out of scope for H2 but directly on-lens (flagging, not folding into H2's verdict):** independently checking *every* winning round trip's nearest conviction row on 08-27/08-28 (not just the C4-flip subset) shows 4 of the 6 winners (+159, +184, +527, +509) already carry `would_block: true` under the *current*, un-flipped conviction score — for reasons unrelated to C4 (C4 is 0 for them regardless of the flip; some other component/floor combination blocks them). This means the *whole* conviction instrument, exactly as built today, would have blocked most of 08-27/08-28's winners if it were ever armed — a materially different and much larger problem than C4's polarity, and consistent with why the report is right to propose **no live change** here. This does not refute H2 (H2 is scoped to C4 specifically, and explicitly declines to propose arming anything), but it is worth a follow-up flag: any future conviction-arming discussion needs its own winner-killer audit of the *whole* instrument, not just C4.

---

## Assessment

No contradicting evidence found anywhere I could independently check: code logic, causal-computation claim, empirical distributions, the counterfactual dollar figures (down to the exact CI bounds), the fleet-coverage gap, the no-live-branch claim, the pre-fix 102/102 degradation, and the winner-killer lens all reproduce under a second, independently-written implementation. The one place I initially got a different number (n=6 vs. n=5 joins) turned out to be a bug in *my* simplified join, not the report's — chasing it down surfaced the correct reason the report's global-greedy-join methodology is the right one. The report's own hedging (INCONCLUSIVE CI at n=5, no proposed live change, VIX split explicitly and correctly omitted rather than mis-split) holds up under adversarial re-derivation rather than being undercut by it.

**Refuted: No.**
