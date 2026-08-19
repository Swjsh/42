# ☀️ MORNING BRIEF — the weekly-options night run (2026-08-18 → 08-19)

> Written for J waking up. Everything below is committed and reversible. **Nothing is armed,
> no account exists, no order was ever placed, `params.json` for the SPY book is untouched.**

---

## 🎯 THE ONE-LINE ANSWER

**You asked which Friday is better. The answer is that the question is moot — the signal
underneath it has no edge, and we now have hard evidence rather than a hunch.**

The lane's machinery got built, and the first thing it did was kill the strategy it was built
to test. That is the machinery working.

---

## 📊 What the experiment found

684 positions walked across 862,000 real option bars. Pre-registration frozen *before* any
result existed.

| Expiry arm | mean return | median | tail ≥+30% |
|---|---|---|---|
| Same week (7 DTE) | **−8.1%** | −41.6% | 23.4% |
| Next week (14 DTE) | **−13.5%** | −33.1% | 18.7% |
| Two weeks out (22 DTE) | **−13.6%** | −27.8% | 14.0% |
| Monthly (29 DTE, control) | **−11.4%** | −19.4% | 10.0% |

**Every arm loses. Every arm fails the random-entry null** — the trigger does not beat entering
on random days. Per the frozen decision rule: nothing ships.

**Why it loses:** 56% of trades die on the theta budget — enter, price doesn't move, decay eats
it. Only 17% reach the first target. Winners average +72%, losers −40%, and at a 25% win rate
the winners would need **+119%** to break even. A 47-point gap. Not a tuning problem.

**No hidden winner:** every zone family, both directions, both symbols lose. Removing
`round_numbers` (55% of signals) makes it slightly *worse*, not better.

---

## 🔍 The finding you'll actually use: HOT ≠ TRADEABLE

Your "trade what's hot, what's the sector" question got both halves answered, and the second
half is the valuable one.

Our scanner ranks **gold miners (GDX, +21.7%) #1**, energy #2 — independently reproducing what
the web research found from different sources. Then the options screen:

- **AEM** — the single hottest name, +37% — quotes a **45% spread**
- **WPM** (+28%) — **95% spread**
- **GDX** itself — 21%
- Meanwhile **GLD is 2.7%**, **XOM 3.6%**, **CVX 2.9%**, **QQQ 1.7%**

**Rule: express a hot theme through its most liquid vehicle, not its best performer.** Gold →
GLD, not miners. Energy → XOM/CVX, not XLE or refiners. A 45% spread means gaining 45% just to
break even.

This also answers the "more than six tickers" question honestly: after screening, the genuinely
tradeable weekly universe here is **small** — QQQ, IWM, GLD, XOM, CVX plus the known
SPY/NVDA/AAPL/TSLA tier. **Breadth is limited by liquidity, not by ideas.**

---

## 🐛 Six real bugs caught, all fixed and guarded

Worth knowing because several would have silently corrupted results:

1. **Bar fetch returned ZERO bars on every feed** — no `start` param, so Alpaca defaulted to
   today-only. Looked exactly like "this symbol has no data."
2. **History silently capped at ~1 month** — no pagination, and with newest-first sorting the
   truncation was invisible. Fixed: 192 → 1,505 bars.
3. **Option ingest truncated 275 contracts** to a single expiry-day bar while the manifest
   reported "99% coverage."
4. **Capital-commitment gate failed OPEN** — a malformed position counted as $0 committed,
   overstating what a new trade could afford.
5. **IV solver fabricated vols** — the bisection's early return bypassed the identifiability
   guard on the *common* path; a contract with no vol information solved "successfully."
6. **Paper keys 401 against the live API host** (contracts endpoint needs `paper-api`).

---

## ✅ What's built and committed

Ingestion · multi-day walk (positions spanning sessions, gap-as-jump, adverse-first
resolution) · delta-matched strike selection via solved IV · expiry selector reading the live
chain · theta budget + corrected flatten schedule · concurrency/correlation/kill-switch gates ·
earnings calendar (yfinance + Nasdaq cross-check) · sector heat scanner · participation cascade
· the random-entry null harness.

**A dangerous bug in my own frozen design, caught by research:** I had set the Friday flatten at
15:30 ET. That is past Alpaca's real 3:15pm order cutoff *and* past the 3:00pm do-not-exercise
cutoff — a long option left to auto-exercise would deliver shares this account can't afford.
Corrected to a 14:45/14:50/14:55 three-tier schedule.

---

## 🚦 What I did NOT do, and why

- **Did not wire scheduled tasks** (phase 9). Registering recurring jobs to run a proven-losing
  trigger creates daily noise and a new silent-failure surface. Spec is written; it unblocks the
  moment a variant clears the null gate. Deferred deliberately, not skipped.
- **Did not touch the SPY book.** The two shared files I edited (`exit_manager.py`,
  `option_pricing_real.py`) were verified provably inert — I ran the pre-existing SPY suites
  myself (109 tests) rather than trusting the review's claim.

---

## 👉 THE FOUR THINGS THAT NEED YOU (nothing is urgent)

1. **Create the `weekly-1` Alpaca paper account** + provision its key into the gitignored
   `secrets.json`. ~5 minutes. **But see below — I'd wait.**
2. **Decide overnight-trim semantics**: one-time entry cut, or nightly-compounding halving?
3. **Confirm GLD's expiry-day cutoff class** (3:15pm general vs 3:30pm SPY/QQQ class) — not
   stated publicly; I assumed the tighter one.
4. **Live money** — permanently yours alone (OP-0 #1).

**My recommendation on #1: don't create the account yet.** There is nothing worth trading on it
until a signal variant clears the null gate. The account is the last step, not the first.

---

## 🔭 Where I'd go next (ranked, with reasons)

1. **Timeframe mismatch** — the trigger fires on a *1-hour* structure shift to justify a
   *multi-day* hold. That's the most likely single cause of the failure. Test a daily-bar trigger.
2. **Zone quality needs a different measure** — confluence is proven dead (ρ=−0.05, p=0.23; my
   earlier "it ranks backwards" read was noise from n=57, corrected in the record). If quality
   matters it needs untouched-level age or volume-at-level, not a count of nearby zones.
3. **Is it detecting volatility rather than direction?** ~50/50 direction split, both losing. If
   so the correct expression is non-directional — which this lane deliberately doesn't trade.
4. **`structure_hh_hl_lh_ll` produced zero signals** on both symbols. Unexplained; one hour of
   inspection before trusting the five-family design.

---

## 📁 Where everything lives

- Program doc (canonical, with the full phase ledger): `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md` §9b
- The verdict + failure diagnosis: `analysis/deep-research/WEEKLY-EXPIRY-EXPERIMENT-2026-08-18.md`
- Frozen prereg: `analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json`
- Sector + liquidity screens: `analysis/sector-heat/2026-08-18.json`, `analysis/weekly-lane/universe-liquidity-screen.json`
- Commits: `e4f949ca` `b89e5f6c` `68c0e239` `a346f111` `031094a7` `8992d743` `0d7fe5a1` `8295f376` `1136bed0`

**Bottom line: the lane is not dead — the v1 signal is. We spent the night building the
apparatus that can tell the difference, and it earned its keep on day one by refusing to let a
losing strategy look promising.**
