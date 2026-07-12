# Ledger Forensics — Where The Real Money Actually Went

**Research stream 1 of 5, J-requested 2026-07-11.** Scope: decompose Project Gamma's real
(paper-broker) fills by mechanism, with dollars attached. Read-only — no params touched, no
orders placed.

**Method note up front:** all "engine" statistics in this report are **per-EPISODE** (entry to
fully-flat), reconstructed with the identical grouping algorithm `trade_autopsy.py` uses
(`reconstruct_positions()` in `backtest/tools/exit_shape_parity_study.py`), reimplemented here
read-only against `automation/state/fills-ledger.jsonl` — the broker-truth fill ledger
(`broker_fills.py`'s pull from Alpaca `/v2/account/activities/FILL`). This is deliberate: this
project has a documented scar (C31) where per-sell-order grouping instead of per-episode
grouping inverted a result. Every number below is episode-level unless explicitly marked
"round-trip" (a different, LEG-level unit `automation/state/pnl-statement.json` uses that can
count one episode as 2+ rows when an exit splits into TP1 + runner legs).

---

## 1. Headline

| | |
|---|---|
| **Net P&L, all 6 accounts, options only** | **-$1,424.99** |
| Engine-attributed | **-$1,698.99** (n=109 episodes) |
| Manual-attributed (J's own hand trades, embedded in same accounts) | **+$274.00** (n=3 episodes) |
| Closed episodes total | **112** |
| Date range | **2026-06-26 → 2026-07-09** (9 unique trading days) |
| DTE | 112/112 = 0 (100% pure 0DTE, confirmed, no surprises) |

**This is a thin, early sample.** 9 trading days, 109 engine episodes. The project's own "live
threshold" bar (CLAUDE.md) is ≥20 trades **per account** — only safe-1 (24) and risky-3 (27)
clear it; safe-3 (19), risky-1 (19), safe-2 (17-20) are close; bold-2 (3-5) is nowhere close.
Treat every per-account number below as directional, not final.

**Cross-check (independent method):** `automation/state/pnl-statement.json` (broker_fills.py's
own FIFO round-trip computation, generated 2026-07-10T20:05 UTC, includes crypto) reports
**-$1,427.50** total realized P&L across all 6 accounts for the same window. That includes 160
crypto micro-fills (BTC/USD twin/test trades) this report excludes by scope. Delta = **$2.51**,
fully explained by crypto. **The two independently-computed methods agree to within $2.51** —
the episode reconstruction is sound.

**One reconciliation footnote, disclosed rather than hidden:** of the $2.51 gap's parent
comparison, the *attribution split* (engine vs manual) differs from pnl-statement.json by
exactly one episode: `safe-2 SPY260626P00732000` (2026-06-26) — entry was an **engine** order
(matched to a core-decisions.jsonl exec row), but the exit fill's `order_id` is untagged
(broker_fills.py's own convention then calls the whole round-trip "manual" because it tags by
the fill that closes the FIFO match, not the entry). This episode is -$237.00. This report
counts it as "engine" (attribution of the entry decision); pnl-statement.json's per-account
`engine_pnl` for safe-2 counts it as "manual". Both conventions are defensible; we flag it
rather than pick silently. **This is the only attribution disagreement found across 112
episodes** — everything else reconciles exactly.

**Pre-fleet historical era (2026-04-29 → 2026-06-18, separate account, separate method — NOT
blended into anything above):** journal/trades.csv (manually-curated, pre-dates
`broker_fills.py`) shows **+$2,352.00 across 14 trades** on the old, now-retired core "Safe-1"
account. **76.3% of that entire era's P&L came from ONE day** (2026-05-14: two trades, +$295
and +$1,500, = +$1,795 of the +$2,352 total). These are the same trades CLAUDE.md's OP-16 cites
as "J's edge source-of-truth" anchor trades — the doctrine itself already labels them
exceptional (C24: "Anchor trades are one-off exceptional setups"). n=14 is below the n<10
floor... no, above it, but the concentration makes it uninformative as a rate; it is not a
comparable dataset to the fleet-era numbers above (different accounts, different execution
path, no broker-truth ledger coverage — `fills-ledger.jsonl`'s own `BACKFILL_SINCE` starts
2026-06-25, so this era literally has no broker-pulled record at all, only the hand journal).

---

## 2. Top loss mechanisms, ranked by $ (engine-only, n=109, evidence quoted)

The loss story is **not** five independent mechanisms — it is overwhelmingly **one** mechanism
(the premium stop), decomposed below by the cuts that show where it concentrates. Presenting
overlapping cuts as if they were separate dollars would double-count; they aren't presented that
way here.

| Rank | Mechanism | n | $ | % of engine losing-episode $ |
|---|---|--:|--:|--:|
| 1 | **Premium-stop, Calls** (mostly `BULLISH_RECLAIM_RIDE_THE_RIBBON`) | 75 | **-$1,490.99** | 52.9% |
| 2 | **Premium-stop, Puts** (mostly `BEARISH_REJECTION_RIDE_THE_RIBBON`) | 19 | **-$978.00** | 34.7% |
| 3 | **Unresolved-exit-reason losses** (decision-log join failed, mostly a 06-30 data gap) | 6 | **-$319.00** | 11.3% |
| 4 | Ribbon-flip losses | 2 | -$22.00 | 0.8% | n<10, no info |

Total engine losing-episode $: **-$2,817.99** (n=95 losing episodes of 109). Rows 1+2 = **all**
94 premium-stop exits system-wide (94/109 = **86% of every engine trade placed exits via
premium stop** — this is the dominant exit path, not one path among several).

**Evidence for #1/#2 — the stop is firing almost immediately, not after the setup has had time
to work:**
- Median hold time on a losing episode: **3.0 minutes**. n=95.
- **84 of 109 engine episodes (77%) are both held ≤15 minutes AND losing**, for -$2,221.99 —
  larger in magnitude than the entire net loss because the (rare) winners needed much longer
  holds to arrive (see §3).
- **Session cut is the sharpest single predictor found:** every MORNING-bucket (entry <11:00 ET)
  engine episode this window exited via premium stop. n=34/34, **0% win rate**, **-$1,463.99** —
  fully contained inside rows 1+2 above, not additional dollars, but it is where within the stop
  mechanism the damage concentrates hardest (34 losses, zero wins, zero exceptions).
- Fleet arms are running a **-20%-ish premium stop**, not the core-account "-50% catastrophe
  cap" the top-level strategy doctrine describes. Confirmed two ways: (a) a sampled fleet
  placement row (`automation/state/fleet/safe-1/decisions.jsonl`, 2026-06-29 entry) carries
  `"premium_stop_pct": -0.2` explicitly in its exit shape; (b) the empirical pct-move
  distribution on the 94 premium-stop exits is **median -20.0%, min -60.0%, max +10.0%**
  (n=94) — centered exactly on -20%, not -50%. **The chart-stop-primary / -50%-cap doctrine in
  CLAUDE.md's "The strategy" section does not describe what the fleet arms are actually running
  this window.**
- One illustrative fill-level artifact worth naming: `safe-1 SPY260706C00753000`, entry $0.10 ×
  8, tagged exit_reason=`premium_stop`, exit fill printed at **$0.11** (+10% pct-move, pnl
  **+$8.00**) — a "stop" that closed above entry. At penny prices the stop-trigger reference and
  the actual fill price can diverge on a wide/thin spread. This corroborates the
  already-flagged noise-floor finding (`journal` memory,
  2026-07-08): **55 of 94 premium-stop exits (59%) are on sub-$0.20 entries**, -$566.00, WR 1.8%
  — the single largest premium-tier cohort by count, and the tier most exposed to spread noise
  reading as a stop trigger.

**Evidence for #3:** 5 of the 6 unresolved episodes land on 2026-06-30 — the fleet's *second*
trading day. This reads as an early decision-log coverage gap (exit-action logging wasn't fully
wired yet), not a distinct trading mechanism. -$319.00 of real money is still real money, but it
is a **visibility gap**, not an edge finding — flagged for the engine team, not the strategy
team. (74% of this bucket, -$237.00, is the single mixed-attribution episode described in §1.)

---

## 3. Cohorts with n≥10 AND positive expectancy — **none survive**

Two cohorts cross both bars on the surface. Both collapse under the concentration check.

| Cohort | n | expectancy | WR | top-3-day concentration |
|---|--:|--:|--:|--:|
| Premium tier $0.20-0.50 | 22 | +$4.50/trade | 9.1% | **89.6%** — CONCENTRATED |
| Time-of-day MIDDAY | 42 | +$10.79/trade | 16.7% | **89.6%** — CONCENTRATED |

**Both are the same three trades wearing different labels.** All three of 2026-07-02's biggest
winners — `risky-3 SPY260702P00742000` (+$491, runner_target), `safe-1 SPY260702P00742000`
(+$306, runner_target), `bold-2 SPY260702P00740000` (+$290, be_stop) — are simultaneously
MIDDAY-bucket AND $0.20-0.50-tier trades. Combined: **+$1,087** from 3 trades on 1 day.

- Remove those 3 trades from the $0.20-0.50 tier: $99 - $1,087 = **-$988** (net negative).
- Remove those 3 trades from MIDDAY: $453 - $1,087 = **-$634** (net negative).

**Verdict: there is no cohort in this dataset — by setup, direction, premium tier, session,
exit reason, account, or any cross of those — that is both n≥10 and durably positive.** The
only mechanism that produced real winners (runner_target, n=2; be_stop, n=1 — 3 episodes
total, all n<10, no information on their own) required holding **75-120 minutes**, in direct
tension with the 77%-of-trades-cut-in-≤15-minutes finding in §2. That tension (not a verdict) is
the one thing in this data that looks like a real, if unproven, lead — see §4.

---

## 4. What we cannot conclude yet

- **VIX-regime interaction: unmeasurable this window.** Every VIX reading across
  2026-06-25→2026-07-10 (n=8,723 readings pulled from `core-decisions.jsonl`) fell inside
  **15.19-20.64** — the market simply did not move during this sample. All 109 engine episodes
  bucket into a single "NORMAL(15-20)" regime. This is a real market-condition observation, not
  a join bug (verified against the raw per-day min/max), but it means **VIX regime cannot be
  ruled in or out as a factor from this data** — there is no variation to correlate against.
- **21% of episodes (23/112) have no resolved setup_name** (join against
  `fleet/{arm}/decisions.jsonl` placement rows / `core-decisions.jsonl` exec rows, ±120s of the
  entry fill). This is concentrated in the core accounts: 13 of safe-2's ~20 episodes, because
  `core-decisions.jsonl` (8,730 rows) contains only 91 rows with a resolvable `exec.broker`
  block system-wide, most of them for the fleet-arm-mapped period, not because of anything about
  those specific trades — a decision-logging coverage gap, not a signal.
- **Exit-reason resolution is 95% (106/112)** — good, but not complete; see §2's #3.
- **The n=109 engine sample is still below this project's own live-graduation bar** (≥20/account)
  for most individual arms. Every ranking above is a **read on 9 days**, not a verdict on the
  strategies.
- **A live doctrine claim does not reconcile with this report and we cannot resolve it from
  available data.** CLAUDE.md OP-16 states bull/calls are "net-positive on real OPRA fills
  (+$5,586 / 56% WR, chef-bull-scope-ab 2026-06-26)". We traced that number to
  `analysis/recommendations/chef-bull-scope-ab-2026-06-26.json`: it is a **simulated backtest**
  (`"window": "2025-01-02..2026-06-18"`, n=25 bull trades, Sharpe/MDD/edge_capture fields
  throughout — a sim-output shape, not a broker-fill reconciliation), replayed on real OPRA
  options bars — which is a different evidentiary class from actual Alpaca paper-broker fills
  (this report's dataset, n=80 Call episodes, **-$1,572.99, WR 1.2%**, 2026-06-26→07-09). Per
  this project's own rule (C1, and this task's hard rule): sim and real fills are never blended
  into one table, and they are not blended here. We are not asserting the sim number is wrong —
  an 18-month backtest and a 9-day live window can legitimately diverge. We ARE flagging that
  **the doctrine text's "real OPRA fills" phrasing is imprecise** (it's simulated-on-real-bars,
  not broker-executed), and that **the actual broker-paper evidence available today points the
  opposite direction from the doctrine's stated bull-positive conclusion.** This needs more
  live-fills volume before either number should move policy on its own.
- **Whether the one mixed-attribution episode (§1, -$237, engine entry / untagged exit) was a
  deliberate manual rescue of a bad engine position or a logging gap** cannot be determined from
  the ledger alone — no journal entry or decision row explains the exit.
- **The 75-120-minute hold time on the only 3 real winners vs. the 3-minute median hold on
  losers is a pattern, not a finding** — n=3 winners is far below any n<10 floor. It is exactly
  the kind of thing `trade_autopsy.py`'s own rolling-window hypothesis detector is built to
  chase with more data; it should not be acted on from n=3.

---

## Appendix — full cohort tables (engine-only, n=109 unless noted)

**By account/arm (all attributions; engine-only equity-normalized in parens):**

| Arm | n (all) | $ (all) | $ (engine only) | % of starting equity |
|---|--:|--:|--:|--:|
| risky-1 | 19 | -$486.00 | -$486.00 | -24.3% (of $2,000) |
| safe-2 | 18 | -$477.99 | -$639.99* | -24.0% to -32.0%* |
| risky-3 | 27 | -$274.00 | -$274.00 | -13.7% (of $2,000) |
| safe-3 | 19 | -$272.00 | -$272.00 | -13.6% (of $2,000) |
| safe-1 | 24 | -$242.00 | -$242.00 | -12.1% (of $2,000) |
| bold-2 | 5 | +$327.00 | +$215.00 | +13.0% (of $1,648.75) — **n<10, no info** |

*safe-2 engine figure depends on the §1 attribution-convention footnote; pnl-statement.json's
convention gives -$403.00 for the same underlying fills.

**By setup name:** `BULLISH_RECLAIM_RIDE_THE_RIBBON` n=65, -$1,236.00, WR 1.5%, expectancy
-$19.02 · `BEARISH_REJECTION_RIDE_THE_RIBBON` n=24, -$138.00, WR 12.5%, expectancy -$5.75 ·
unresolved n=20, -$324.99.

**By direction:** Calls n=80, -$1,572.99, WR 1.2%, expectancy -$19.66 · Puts n=29, -$126.00, WR
20.7%, expectancy -$4.34. **Puts are meaningfully less bad than Calls on every axis this
window** — consistent with §2's Call-heavy premium-stop concentration.

**By entry premium tier:** <$0.20 n=55, -$658.00, WR 1.8% · $0.20-0.50 n=22, +$99.00, WR 9.1%
(concentrated, see §3) · $0.50-1.00 n=26, -$803.00, WR 15.4% (worst per-trade expectancy,
-$30.88) · >$1.00 n=6, -$336.99, WR 0% (n<10, no info).

**By time-of-day:** MORNING n=34, -$1,463.99, WR 0.0% · MIDDAY n=42, +$453.00, WR 16.7%
(concentrated, see §3) · AFTERNOON n=33, -$688.00, WR 0.0%.

**By exit reason:** premium_stop n=94, -$2,468.99, WR 1.1% · unresolved n=6, -$319.00 ·
ribbon_flip n=6, +$2.00 (n<10) · runner_target n=2, +$797.00 (n<10) · be_stop n=1, +$290.00
(n<10).

Full episode-level data (112 rows, all fields): written to scratchpad during this research run,
not committed to the repo (research artifact, not a doctrine file).

---

## Data sources used (all read-only)

- **Primary/authoritative:** `automation/state/fills-ledger.jsonl` (broker-truth, Alpaca FILL
  activities, 421 raw fills → 261 SPY option fills → 112 reconstructed episodes), the same file
  `trade_autopsy.py` reads.
- **Cross-check:** `automation/state/pnl-statement.json` (independent FIFO round-trip
  computation from the same ledger).
- **Setup-name / exit-reason join:** `automation/state/fleet/{safe-1,safe-3,risky-1,risky-3}/decisions.jsonl`
  + `automation/state/core-decisions.jsonl` (filtered `account` field for safe-2→safe,
  bold-2→bold), matched to fills by nearest `broker.created_at` within 120s (mirrors
  `trade_autopsy.py`'s own `_closest_broker_created_row`).
- **VIX series:** `automation/state/core-decisions.jsonl`'s `vix` field (8,723 readings),
  nearest-within-30min join.
- **Historical/secondary, NOT blended:** `journal/trades.csv` (pre-2026-06-25 rows only; has
  known CSV-quoting defects in ~24 of 150 rows from unescaped commas in the notes field —
  financial columns [date, dollar_pnl, setup, side] are at fixed low indices unaffected by the
  defect and were extracted positionally, not via DictReader).
- **NOT used as ground truth, cited once for contrast only:**
  `analysis/recommendations/chef-bull-scope-ab-2026-06-26.json` (simulated backtest, see §4).
- Excluded from scope: 160 crypto (BTC/USD) fills in the same ledger (crypto twin — separate
  mechanism-only validation lane per `markdown/planning/TWIN-PROGRAM.md`, never blended with SPY
  edge numbers by standing doctrine).
