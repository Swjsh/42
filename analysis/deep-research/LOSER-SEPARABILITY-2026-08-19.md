# LOSER SEPARABILITY — is there ANY pre-entry observable that tells winners from losers?

**2026-08-19, after the close.** Clock verified this session, first action:
`python setup/scripts/et_clock.py` → **`2026-08-19 18:02:06 Wednesday EDT, market_hours=False`**.
Adversarial research only. No engine file touched, no gate changed, no `params*.json` edited,
no config proposed. Read `MAP.md` + `markdown/doctrine/LESSONS-LEARNED.md` themes C4/C14/C20/
C22/C27 before starting per the assignment; the null hypothesis below is the default.

> J's ask: *"figure out why we got into the losers and how we could either potentially knock out
> them, or maybe that's the whole thing... It's not gonna be a win rate strategy. It's gonna be
> about getting paid on the ones that pay and then cutting our losses small."*

---

## ⛔ VERDICT: **NOT SEPARABLE**

No pre-entry feature tested — score, ribbon, VIX, spread, time-of-day, trigger set, quality
tier, moneyness, entry premium, distance to nearest level, day-of-week, free-model consensus —
survives contact with a counterfactual. Every candidate that "looked" like a filter either (a)
destroyed more winner-dollars than loser-dollars, (b) reversed sign in leave-one-day-out, or (c)
was carried by 1-2 days out of ~22. The one candidate that survives leave-one-day-out
(time-of-day) is the same regime-conditional trap this repo already refuted for a sibling
account (L125) — see §5.

**The single cleanest exhibit:** 2026-08-13, bold-2, side C, `level_reclaim+confluence`,
score 11/5, VIX 14.41→14.57, spread 106.4¢→105.8¢, premium $1.04→$0.98 — **two waves 110
minutes apart with a near-identical feature vector. One paid +$534. The other cost −$85.**
Nothing measurable at entry time distinguishes them. This is the general pattern, not an outlier.

---

## THE RIGHT-TAIL ARITHMETIC (this is the real answer)

Population: 63 real, engine-attributed round trips (`core-decisions.jsonl` PLACED rows joined
to `fills_fifo.mine_real_arm_fills`, safe-2 + bold-2, 22 sessions, 2026-06-26→2026-08-19).

| | value |
|---|---|
| Winners | 17 (27.0%) |
| Losers | 46 (73.0%) |
| Avg winner | **+$278.80** |
| Avg loser | **−$111.60** |
| Win/loss size ratio | 2.50× |
| **Breakeven win rate required** (given these sizes) | **28.59%** |
| **Actual win rate** | **26.98%** |
| Margin vs breakeven | **−1.6 points** |
| Net P&L, this population | **−$392.00** |
| Top 1 trade | $614 = **13.0%** of all winner-dollars |
| Top 3 trades | $1,531 = **32.3%** of all winner-dollars |
| Top 5 trades | $2,281 = **48.1%** of all winner-dollars (5 of 63 trades = 7.9% of the book) |

**It is a right tail — confirmed. Nearly half of every dollar the winners produce comes from 5
trades out of 63.** But at the realized win/loss sizes over this window, the win rate needed to
break even (28.6%) is *higher* than the win rate actually delivered (27.0%). The book is not
failing because losers are too frequent in an abstract sense — it is running **1.6 points below
its own breakeven line**. That gap is well inside sampling noise for n=63 (see §6), so this is
not "the strategy is broken" — it is "the margin for error is thin, and there is currently none
to spare." Any change that shrinks the average winner or grows the average loser removes the
only thing keeping this profitable at all.

**Scope note (declared, not buried):** the full real-fills book across all 5 arms (safe-2,
bold-2, safe-3, risky-1, risky-3 — 303 round trips, 35 sessions, 2026-06-26→2026-08-19) nets
**−$1,805**. This study's n=63 core-only population is 20.8% of that book. The negative
book-wide number is a fact from the same ledger this study uses (`fills-ledger.jsonl`,
`attribution=="engine"`) — reported here for honesty, not analyzed further; it is a different
question (fleet-arm performance) than the one this document answers (pre-entry separability).

---

## 1. Data, method, and disclosed coverage gaps

- **Population definition (per assignment):** every `action=="PLACED"` row in
  `automation/state/core-decisions.jsonl` (66 rows total, accounts `safe`/`bold` only — this
  file does not cover the fleet arms), joined by `(arm, symbol, closest entry_ts within 20 min)`
  to `automation/state/fleet/fills_fifo.mine_real_arm_fills("safe-2"/"bold-2")`
  (per L258 convention: coarse-key match alone is unsound, time-bound every join).
- **Matched: 63 / 66 PLACED rows** (3 unmatched — likely PLACE_FAIL/unfilled, not investigated
  further, immaterial to the question).
- **⚠️ Disclosed gap, not resolved:** `fills_fifo` finds **101** real closed round trips for
  safe-2+bold-2 over this window, not 66. The 38 unmatched round trips are **not silently
  dropped from awareness** — they cluster on specific days as rapid same-symbol re-entry bursts
  (e.g. 2026-07-06: 1 logged `PLACED` row in `core-decisions.jsonl` but **8** real round trips
  on the same symbol within 90 minutes, netting small $ amounts each). This is consistent with
  a re-entry decision-logging gap (same failure family as L07/L26 — the execution path fires but
  the *decision* log does not always get a fresh `PLACED` row for a same-day re-entry). **This
  is flagged as an open finding for a future session, not investigated further here** — fixing
  a logging gap is out of scope for a research-only task, and the 38 missing rows have no
  pre-entry feature vector to test regardless.
- **Features extracted (all knowable strictly at entry time, C6-clean):** bull/bear score (own
  side + margin vs. opposing side), ribbon state, htf_15m, spread_cents, VIX, minutes since
  09:30 open, trigger set (incl. confluence flag, trigger count), quality_tier/quality_rank
  (`exec` block), strike moneyness (side-normalized ITM/OTM %), entry premium, day-of-week,
  free-model vote count, and distance to nearest `levels_active` entry (available on 46/63 rows
  — this field was only added to the schema 2026-07-28 onward; reported as a subset, not
  imputed).
- **Feature NOT built, disclosed as a gap:** *"which filters had just released."* The only
  candidate signal (`bear_blockers`/`bull_blockers` arrays) describes the **losing side's**
  blocker state, not a released gate on the **winning side** — it does not answer the intended
  question and reverse-engineering the real thing (a tick-by-tick gate-state diff before each
  entry) was judged out of scope for this pass. Not forced into a weak proxy.
- **Cross-check against prior coverage (Obsidian brain rule):** `analysis/entry-quality/
  admissibility-battery.json` already tests a *different* feature family (5m/1m market
  structure presence, BOS/CHoCH agreement) over a related 235-event population. Zero of its 5
  cells reach the pre-registered BH q≤0.10 bar — 3 REJECT/WATCH, 2 FORWARD_SHADOW_CANDIDATE
  (not ratified). That is an independent null result on a different feature set, over a
  different (larger, all-arm) population. Two independent scans, two nulls.

---

## 2. Continuous features — winner vs. loser distributions (n=63, 17W/46L)

| feature | winner mean | loser mean | Cohen's d | % losers inside winner range |
|---|---|---|---|---|
| score_own (winning side's score) | 9.41 | 9.52 | **−0.07** | 93.5% |
| score_margin (own − opposing) | 3.71 | 3.41 | 0.10 | 100.0% |
| spread_cents | 108.1 | 97.5 | 0.11 | 93.5% |
| VIX | 15.69 | 15.98 | −0.20 | 80.4% |
| minutes since open | 172.6 | 150.0 | 0.23 | 82.6% |
| n_triggers | 1.41 | 1.76 | **−0.49** | 80.4% |
| moneyness_pct (side-normalized) | −0.04% | −0.03% | −0.09 | 95.7% |
| entry_premium | $0.85 | $0.95 | −0.29 | 89.1% |
| n_free_go (free-model votes) | 1.00 | 1.17 | −0.20 | 100.0% |
| level_dist_pct (n=46 subset) | 0.026% | 0.029% | −0.14 | 93.8% |

By convention |d|≥0.5 is a "moderate" effect and every serious quant screen wants ≥0.8 before
trusting it as usable. **Nothing here clears 0.5.** `n_triggers` (−0.49) is the closest thing to
a signal in this table — winners average fewer triggers (1.41 vs 1.76) — and it is examined as
a counterfactual below. Every other feature overlaps 80-100% between winners and losers: a
loser and a winner look statistically the same at entry time on every one of these axes.

## 3. Categorical features

| feature | best bucket (n, WR, total $) | worst bucket (n, WR, total $) |
|---|---|---|
| day-of-week | Tuesday (15, 46.7%, **+$1,147**) | Friday (13, 15.4%, **−$1,124**) |
| htf_15m | BEAR (22, 36.4%, +$294) | MIXED (17, 17.6%, −$648) |
| ribbon | MIXED (5, 40.0%, −$92) | BEAR (24, 29.2%, −$193) |
| side | P (34, 29.4%, −$326) | C (29, 24.1%, −$66) |
| account | safe (34, 26.5%, +$10) | bold (29, 27.6%, −$402) |
| by-trigger | trendline_rejection (30, 33.3%, **+$133**) | level_rejection (5, 0.0%, **−$814**) |

**Day-of-week is the single largest categorical spread** (Tue +$1,147 vs Fri −$1,124) — and it
is exactly the shape flagged in C4/C22: a feature that "explains" the data because the sample is
small (13-16 entries per weekday over 4-5 calendar instances of each), not because Tuesday is
mechanically different from Friday. No day-of-week counterfactual is proposed below for that
reason — this is the textbook small-N regime-flip trap the assigned lessons warned about before
a single test was run.

**`level_rejection` (n=5, 0% WR, −$814 total)** looks damning but n=5 is too small to act on —
one bad trade at that size is −$160 to −$400 and the whole bucket moves. Not proposed as a gate.

---

## 4. Counterfactual P&L — every candidate tested, full history, not just today

Each row: apply the filter (block the described entries) across **all 63 real trades**, report
net P&L with vs. without, and whether the filter would have *also* removed winners.

| candidate | n blocked | Δ net P&L (whole history) | winners blocked ($/n) | losers blocked ($/n) | leave-one-day-out |
|---|---|---|---|---|---|
| Block VIX > median (15.34) | 31 | **−$348 (WORSE)** | $2,826 / 10 | −$2,478 / 21 | **unstable** — 2/22 folds positive |
| Block score_margin ≤ 2 (bottom tercile) | 21 | **−$6 (dead knob)** | $1,281 / 5 | −$1,275 / 16 | unstable — 4/22 positive |
| Block spread_cents ≥ 106.4¢ (top quartile) | 16 | **−$1,383 (WORSE)** | $2,528 / 6 | −$1,145 / 10 | stable — **all 22 folds negative** (wide spread trades robustly PAY) |
| Block quality_rank < median | 0 | $0 (field only on 5/63 rows) | — | — | n/a, insufficient coverage |
| Block level_dist_pct ≥ top quartile (n=46 subset) | 12 | **−$35 (dead knob)** | $1,354 / 5 | −$1,319 / 7 | unstable — 3/22 positive |
| Block entries w/o `confluence` (keep only confluence) | 30 | **−$183 (WORSE)** | $2,126 / 10 | −$1,943 / 20 | unstable — 3/22 positive |
| **Block 11:30–13:00 ET ("midday")** | 21 | **+$1,072 (BETTER)** | $875 / 4 | −$1,947 / 17 | **stable — all 22 folds positive** |

Six of seven candidates are either net-negative to apply or a dead knob (Δ inside noise, <2% of
book). **Every single one that "worked" on a WR-only read (VIX>median, tight-spread-only,
confluence-only) makes the book worse in dollars** — the exact pattern C14/C24 warn about:
blocking a lower-WR bucket that has positive expectancy because its rare winners are large.

**One candidate — time-of-day — is directionally robust. It gets the full adversarial workup
next**, per the assignment's step 4, because it is the only one that survived step 3.

---

## 5. Adversarial attack on the one survivor: "block 11:30–13:00 ET"

- **Headline:** blocking this 90-minute window removes 21/63 entries (**one third of the entire
  population**) and improves net P&L by +$1,072 (base −$392 → kept +$680). Win rate inside the
  window is 19.0% vs. 31.0% outside.
- **Day concentration (the check the assignment specifically demands):** midday P&L by day
  ranges from −$355 (2026-07-27) to +$300 (2026-08-04) across 11 distinct midday-touched days.
  **The single worst day is 33.1% of the window's total negative dollars. The worst TWO days are
  66.1%.** That is a concentration ratio this project's own doctrine (C4) treats as a hard stop
  on trusting an aggregate number.
- **VIX confound check:** midday VIX mean 15.60 vs. non-midday 16.05 — **not a VIX proxy**, the
  regimes are statistically identical.
- **Day-of-week confound check:** midday entries are 26-42% of each weekday's total (Mon 14%,
  Tue 27%, Wed 38%, Thu 42%, Fri 38%) — roughly proportional, not concentrated on one weekday.
  **Not simply a day-of-week proxy** either.
- **The exact trap this repo already fell into and reversed (L125, 2026-06-17):** a midday
  trendline gate was tested for the Aggressive account on this exact logic — IS-period midday
  entries looked bad, the gate improved the IS backtest, and it **failed walk-forward (WF=0.147
  vs. 0.70 gate)** because the IS-losing midday regime and the OOS-winning midday regime were
  different market character, not the same mechanism. This study has no separate IS/OOS split
  (n=63 is too small to hold one out and still have power), so **it cannot rule out that this is
  the identical trap** — a regime-conditional artifact of *this specific* 22-day window rather
  than a mechanism.
- **The concrete kill shot:** the largest individual midday entry this filter would have
  blocked is **2026-08-19 11:49, +$195 — the exact "won big" wave from today's own worked
  example in this assignment.** A filter derived from this window's aggregate would have cut the
  best trade of the day used to motivate the question. Two of its other blocked winners are
  +$375 (2026-08-04) and +$290 (2026-07-02) — not small. Blocking 33% of the book to buy +$1,072
  net, while cutting winners worth $875 including one of the book's better trades, is not a free
  lunch; it is a coin that could easily flip on the next 20 sessions the way L125's did.

**Verdict on this candidate: NOT RECOMMENDED, NOT RATIFIED, NOT SHIPPED.** It clears the
mechanical bars this document set (LOO-stable, no VIX/DOW confound) but fails the qualitative
bar this project has already paid for once (L125's WF=0.147) and openly display 2-day
concentration. Filed here as a **flagged-not-actioned observation** for a future session with a
larger n to re-test with a proper IS/OOS split — not as a recommendation, per the no-manufactured-
recommendation instruction.

---

## 6. What killed each candidate — one line each

- **VIX** — no discrimination (Cohen's d −0.20); blocking the "bad" VIX half removes more
  winner-dollars than loser-dollars; unstable in leave-one-day-out. Matches C5/L118/L121: VIX
  *level* has never separated this engine's winners from losers, only VIX *character* might, and
  this population is too small to test character (rate-of-change, spike-decay) reliably.
- **Score margin** — dead knob. Δ = −$6 across the whole history, noise-sized against a $4,740
  gross-winner base. Own-side score bucketed at integer resolution is **non-monotonic**
  (score=8 avg +$98, score=10 avg **−$110**, score=11 [the modal, max bucket, n=25] avg only
  +$4) — high score is not a proxy for quality here.
- **Spread_cents (illiquidity proxy)** — robustly the OPPOSITE of a filter: wide-spread entries
  pay, every leave-one-day-out fold agrees. Blocking them costs money in a structurally stable
  way. Do not build a spread gate from this data.
- **Quality_rank** — field only populated on 5/63 rows (recent schema addition); no statement
  possible, disclosed as insufficient coverage rather than forced to a conclusion.
- **Distance to nearest key level** — near-zero effect (d=−0.14) on the 46/63 rows where the
  field exists; dead knob (Δ=−$35). Consistent with the existing entry-quality-ledger battery,
  which also found no ratifiable structure-distance cell.
- **Confluence (multi-trigger) vs. single-trigger** — the *opposite* of the intuitive read:
  `trendline_rejection` (single trigger, n=30, +$133 total) modestly outperforms `confluence`
  (multi-trigger "higher quality" entries, n=33, **−$575 total**). Keeping only confluence
  entries makes the book worse by $183. `n_triggers` has the largest Cohen's d in this whole
  study (−0.49) and it points the *opposite* direction from what "more confirmation = better
  entry" doctrine would predict — flagged as the most interesting residual finding, but n is too
  small (30 vs 33) and the effect is still only "moderate," not "actionable."
- **Midday time-of-day** — the lone LOO-stable, confound-clean candidate; killed on
  qualitative grounds (§5): 2-day concentration (66%), 33% of the whole book blocked, and it
  is the exact structural shape (IS-only regime artifact) that L125 already proved fails
  walk-forward for a sibling account on this exact type of window.

---

## Bottom line for J

**The losers are not separable from the winners with anything the engine knows at entry time.**
The same setup, same triggers, same score, same VIX, same spread, minutes apart — pays once,
costs once. That is not a data problem to be solved with a better filter; it is what a low-WR,
right-tail options strategy looks like from the inside, and every attempt in this repo's own
history to turn a post-hoc "bad bucket" into a pre-entry gate has either destroyed more winner
dollars than it saved (this study, §4) or looked great in-sample and died on walk-forward
(L118-L126, L145, L250, L256 — six independent prior refutations of this exact move).

The honest lever is not "keep out of the losers" — it is the arithmetic in the headline: **at
current average winner ($279) and average loser ($112) size, 28.6% win rate breaks even; the
book is running 27.0%, 1.6 points short.** That gap is closeable by making winners bigger or
losers smaller (the exit side — already this repo's stated edge lane, see
`analysis/winner-autopsies/SIGNATURE.md`), not by refusing more of the trades that already look
identical to the ones that pay.
