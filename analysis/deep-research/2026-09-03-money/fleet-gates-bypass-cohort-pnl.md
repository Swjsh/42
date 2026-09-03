# G3 — What the bypass cost or earned

Stamp: 2026-09-03T13:30 ET (session ran through ~14:20 ET, market open). Read-only. Builder:
`backtest/tools/fleetgates_bypass-cohort-pnl.py` (scratch, re-runnable). Full per-arm/per-cohort/
per-VIX-band/per-day JSON: `analysis/deep-research/2026-09-03-money/fleet-gates-bypass-cohort-pnl.json`.
Answers queue item **G3**, building on `veto-scope-safe-3.md`'s mechanism proof (this session's
established context).

## Verdict up front

**For safe-3: net POSITIVE to date ($752, 13 trades, PF 2.08), but that is entirely today's
luck — drop the single best day (today, 2026-09-03) and the bypass cohort is net NEGATIVE
(-$188, 11 trades, mean -$17/trade).** Population-wide (all 4 named arms, ribbon-strategy
entries only) the bypass cohort is breakeven ($33, 38 trades, PF 1.01) and — same story —
negative (-$1,564, 34 trades) with today dropped. The "both-passed" (non-bypass) control
cohort is **also a net loser** everywhere measured (safe-3 -$203, population -$1,325), so this
is not "bypass bad, control good" — both cohorts lose money on this sample; the bypass cohort
is not distinguishably worse, and on the tiny n available it is not distinguishably better
either. **This is a small-sample, one-day-dominated read, not a resolved edge question** —
every bootstrap CI on the arm-level cuts straddles zero.

Today (09-03) is the sharpest single data point: safe-3's 2 bypass entries (11:07, 11:22 ET)
both won (+$507, +$433 = **+$940**); its 2 non-bypass entries the same day (09:42, 10:17 ET)
both lost (-$270, -$65 = -$335). Net safe-3 today: **+$605**, entirely because the bypass
trades outperformed the "safe would also have entered" trades on this one day.

**Candidate costing:** killing safe-role bypass entries (safe-3 + safe-1, KILL-TYPE, can only
remove trades) would have **removed $752 of net profit** from safe-3 to date (-$188 pre-today
plus +$940 from today's two trades) — net negative for the candidate if judged today, net
POSITIVE (+$188 avoided losses) if judged on yesterday's close. The broader "every arm inherits
its own role's gates" cut
removes **$1,323** system-wide (also dominated by two single days: 08-06 $1,126 for the risky
arms' mirror-direction case, and today's $940 for safe-3) — drop the single best day and it's
still **+$197**, the one cut in this whole analysis that stays positive after that stress test.

---

## Method, joins, and what "cohort" means here

1. **Population**: every real order placement (`placement.placed == true`) logged as
   `action: ENTER_BULL|ENTER_BEAR` in each arm's `automation/state/fleet/<arm>/decisions.jsonl`.
   The engine re-logs the same strategic verdict every tick a position stays open even when no
   new order goes out (`placed: false`, `symbol: null`) — those re-logs are **excluded**
   (confirmed by inspection: risky-1 2026-06-21..24 shows 4 consecutive `ENTER_BEAR` rows for
   one held position, only the first `placed: true`). Skipping this fix inflated cohort C to
   3-4x its real size with phantom "unmatched" rows (a bug caught and fixed mid-session, not
   silently left in) — real-placement counts: safe-3 68, risky-1 90, risky-3 96, safe-1 24.
2. **Scope restricted to ribbon-sourced setups** (`BULLISH_RECLAIM_RIDE_THE_RIBBON`,
   `BEARISH_REJECTION_RIDE_THE_RIBBON`). `VWAP_CONTINUATION`/`VWAP_RECLAIM_FAILED_BREAK` entries
   have no safe/bold perception split in `build_shared_signal.py` (they're sourced from
   `fleet_market.vwap_strategy_block`, an independent network detector) — comparing their entry
   tick's core-row verdict to the trade's side would compare two unrelated signals. Excluded,
   reported separately (`non_ribbon_strategy_not_applicable` per arm in the JSON) so nothing is
   silently dropped: risky-1 16 trades/-$745, risky-3 22 trades/-$1,316, safe-3/safe-1 zero
   (neither trades VWAP).
3. **Cohort assignment**: for each entry, `core_tick_id` (present on `core-decisions.jsonl` rows
   only from **2026-08-03 09:30:04 ET onward** — before that the field doesn't exist at all)
   keys into that tick's `account=safe` and `account=bold` rows. `want = ENTER_BULL if side==C
   else ENTER_BEAR`.
   - **Cohort A (bypass)**: safe's verdict != want, bold's verdict == want.
   - **Cohort B (both passed)**: both verdicts == want (arm's own entry is not actually a
     bypass — safe's own engine would have taken it too).
   - **Cohort C (other)**: safe alone passed, or neither passed (arm entered anyway — usually
     an arm-level gate-override rescue, not the safe/bold swap mechanism).
   - **Unclassified**: no `core_tick_id` on the row (pre-2026-08-03) — can't be cohort-assigned
     by this ledger at all. safe-3 28 trades/-$16, risky-1 25/-$190, risky-3 38/+$44, **safe-1
     ALL 24 of its trades** (safe-1 retired 2026-07-11, wholly before the join field exists —
     **safe-1 cannot be assessed for this question with the current ledger, full stop**).
4. **P&L source**: `analysis/pain-ledger/mae-mfe.json` (itself built from
   `fills-ledger.jsonl`, `attribution=="engine"` only) for everything through 2026-09-02. That
   ledger was generated 2026-09-02T16:26:57 ET, **before today's trading** — today's fills
   (09-03) are reconstructed directly from `fills-ledger.jsonl` by the same flat-to-flat
   round-trip logic (buy-open, sum sells until quantity returns to 0), verified against a
   manual hand-calc of the two safe-3 bypass trades (+$507, +$433 — matches). After the
   real-placement fix, **0 unmatched trades remain** in any cohort for any arm.
5. **Stats per cut**: n, total $, WR (win/(win+loss), scratches excluded from denominator), PF
   (gross win / abs(gross loss)), mean $/trade + 95% bootstrap CI (5,000 resamples, seed 42),
   top-3-winner gross-win concentration, drop-best-day total.

---

## Per-arm cohort A vs B (ribbon strategies, all-time through today)

| Arm | Cohort | n | $ total | WR | PF | mean $/trade (95% CI) | top-3-win conc. | drop-best-day $ (n) |
|---|---|---:|---:|---:|---:|---|---:|---|
| **safe-3** | A bypass | 13 | **+752** | 30.8% | 2.08 | +57.85 (-48, +184) | 0.86 | **-188** (11) |
| safe-3 | B both-passed | 20 | -203 | 20.0% | 0.89 | -10.15 (-111, +97) | 0.82 | -766 (19) |
| **risky-1** | A bypass | 16 | +104 | 25.0% | 1.09 | +6.50 (-79, +108) | 0.77 | -553 (14) |
| risky-1 | B both-passed | 19 | -146 | 21.1% | 0.93 | -7.68 (-128, +124) | 0.82 | -796 (18) |
| **risky-3** | A bypass | 9 | **-823** | 0%† | 0.00 | -91.44 (-124, -64) | n/a | -783 (8) |
| risky-3 | B both-passed | 21 | -976 | 23.8% | 0.55 | -46.48 (-139, +42) | 0.78 | -1,346 (19) |
| **safe-1** | — | 0 | n/a | — | — | UNCLASSIFIABLE — all 24 real fills predate the 2026-08-03 join key | | |
| **POPULATION** | A bypass | 38 | **+33** | 21.1% | 1.01 | +0.87 (-55, +63) | 0.47 | **-1,564** (34) |
| POPULATION | B both-passed | 60 | -1,325 | 21.7% | 0.78 | -22.08 (-83, +39) | 0.37 | -2,354 (56) |

† risky-3's cohort A is 0-for-9 (all 9 trades losers, CI entirely below zero: the one cell in
this table where the bootstrap CI does NOT cross zero) — the single worst cell in this table,
entirely on `SKIP_BULL_1100_1200` (8 trades, -$619) and one `SKIP_STRUCTURE_VETO` (-$204). Even
risky-3's *best* day in this cohort (08-27) was itself a small loss (-$40) — dropping it barely
moves the total.

**Which gate did the bypassing, cohort A only** (safe's own verdict at the entry tick):

| Gate | Arms firing it | n | $ total |
|---|---|---:|---:|
| `SKIP_BULL_1100_1200` (`block_bull_1100_1200`) | safe-3, risky-1, risky-3 | 28 | +179 |
| `SKIP_STRUCTURE_VETO` (`structure_veto_enabled`) | safe-3, risky-1, risky-3 | 9 | -1 |
| `SKIP_DOJI_ENTRY_BAR` | risky-1 only | 1 | -145 |

`block_bull_1100_1200` is the dominant bypass gate by volume (28 of 38 bypass trades, 74%) and
is roughly breakeven in aggregate. `structure_veto_enabled` — the gate `veto-scope-safe-3.md`
flagged as today's live example — is the second most common and dead flat in aggregate ($-1
over 9 trades). Neither gate shows a clean directional edge in either direction at this n.

---

## VIX bands (safe-3 only — thinnest cut, flag accordingly)

Cohort A never fired above VIX 18 in safe-3's history (n=13 total): `<15` n=5, +$977, WR 60%,
PF 4.67 (today's two wins are in this band); `15-18` n=8, -$225, WR 12.5%, PF 0.48. Cohort B
spans the same two bands with milder numbers (-$32 and -$171). **n too small per band (5-13)
to support any VIX-conditional claim** — reported because asked, not because it's decisive.
Full bands (including risky-1/risky-3) are in the JSON.

---

## The four named winning days (2026-08-06, 08-13, 08-27, 08-28)

Summed across safe-3 + risky-1 + risky-3 (ribbon-strategy entries only):

| Day | Cohort A (bypass) | Cohort B (both-passed) |
|---|---|---|
| 08-06 | 0 trades, $0 | 0 trades, $0 |
| 08-13 | 3 trades, **-$325** (safe-3 -90, risky-1 -155, risky-3 -80) | 4 trades, **+$1,029** |
| 08-27 | 3 trades, **+$616** (safe-3 +303, risky-1 +353, risky-3 -40) | 4 trades, +$745 |
| 08-28 | 0 trades, $0 | 7 trades, +$793 |

**The named winning days are driven by cohort B (legitimate, non-bypass) entries, not by the
bypass.** On 08-13 and 08-28 the bypass cohort had zero or net-negative contribution while the
both-passed cohort carried the day; 08-27 is the one day the bypass cohort clearly helped
(+$616 across 3 arms, though cohort B still out-earned it that day too, +$745). **08-06 had
zero ribbon-strategy fleet-arm trades in cohort A or B** — it is not a bypass day in the
primary direction at all; it only appears in Candidate (b) below, via cohort C's
mirror-direction case (ribbon setups where safe passed and bold — the risky arms' own nominal
role — did not).

---

## September window (2026-09-01 through today 2026-09-03)

| Arm | Cohort | n | $ | Trades |
|---|---|---:|---:|---|
| **safe-3** | A bypass | 4 | **+802** | 09-02: -90, -48 · **09-03: +507, +433** |
| safe-3 | B both-passed | 3 | -383 | 09-02: -48 · 09-03: -270, -65 |
| safe-3 | C other | 1 | -90 | 09-02: -90 (safe passed, bold `SKIP_CONF_LVL_REC_AFTERNOON`) |
| **risky-1** | A bypass | 4 | **+432** | 09-02: -145, -80 · 09-03: +343, +314 |
| risky-1 | B both-passed | 3 | -425 | 09-02: -80 · 09-03: -280, -65 |
| **risky-3** | all cohorts | 0 | 0 | risky-3 fired zero ribbon ENTER decisions in September so far |

September is a 3-day, n=4-per-arm window — descriptively the bypass cohort is up (+802 safe-3,
+432 risky-1) and the control cohort is down, but this is the SAME today-dominated pattern
already flagged, not new information: pull out today and September cohort A is -$138 (safe-3,
2 trades) / -$225 (risky-1, 2 trades) — negative, matching the rest of the pre-today record.

---

## Candidate costing

### (a) "Safe-role fleet arms inherit safe's cohort gates" — KILL-TYPE, safe-3 + safe-1 only

Removes cohort-A entries from safe-3 and safe-1 only (safe-1 contributes 0 — unclassifiable).
**Can only remove trades, never add.**

- Removed: **13 trades, +$752 net** (4 winners removed = $1,450 of foregone gain; 9 losers
  removed = $698 of avoided loss).
- Drop today: removed set flips to **-$188** (11 trades) — i.e. **as of yesterday's close this
  candidate would have been a net positive change** (avoids $188 more than it foregoes);
  **as of today's close it is a net negative change** (foregoes $752, most of it today's two
  trades).
- Named winning days: only 08-13 (-$90 removed → change is +$90 favorable) and 08-27 (+$303
  removed → change is -$303 unfavorable) touched; 08-06/08-28 untouched.
- September: removes +$802 (today's two trades, +$940, minus two 09-02 losers, -$138) — net
  unfavorable for the month so far.
- **Today (09-03) specifically**: this candidate removes exactly safe-3's 11:07 (+$507,
  `SKIP_BULL_1100_1200`) and 11:22 (+$433, `SKIP_STRUCTURE_VETO`) entries — the two trades
  named in the question. Applying it today would have cost the $940.

### (b) "All fleet arms inherit their own role's gates" — safe arms → safe-only, risky arms → bold-only

Same safe-role removal as (a), **plus** a mirror-direction cut for risky-1/risky-3: entries
where bold (their nominal "risky" role's own core account) did NOT pass but safe did — i.e.
risky arms currently ride safe's fallback pass on ticks bold itself blocked.

- Removed system-wide: **29 trades, +$1,323 net** (safe-role $752 + risky-role $571).
- Risky-role removal gate breakdown (what blocked bold): `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`
  (11 trades, +$466) and `SKIP_CONF_LVL_REC_AFTERNOON` (5 trades, +$105) — both bold-only gates
  (safe's config doesn't carry `require_bearish_fill_bar` as a live block in this dataset;
  `SKIP_CONF_LVL_REC_AFTERNOON` never appears on the safe side either).
- **This is the one cut in the whole analysis that survives drop-best-day**: best single day is
  08-06 (+$1,126, both trades on risky arms' mirror case), and with that day dropped the
  removed set is still **+$197** — every other cut in this report flips negative once its best
  day is pulled.
- 08-06/08-13/08-27/08-28: 08-06 now touched (+$1,126 removed, entirely the risky-role mirror
  case — this is the day cohort A itself never fired on), 08-13 +$315, 08-27 +$303, 08-28 $0.
- September: removes +$657 (safe-role's +$802, same as candidate (a), plus risky-1's single
  09-02 mirror-case trade at -$145).
- Today: same two safe-3 trades as (a); no risky-role mirror-case trades fired today.

---

## Plain answer to "has the bypass been net positive or negative for safe-3"

**Population (all-time through today): net positive, +$752, but not robustly so** — PF 2.08
and WR 30.8% look strong only because n=13 and today supplied 2 of the 4 winners and $940 of
the $1,450 gross win total (65%). The 95% bootstrap CI on mean $/trade is (-$48, +$184) —
**crosses zero**, so "positive" is not statistically distinguishable from "flat" at this n.

**Over September specifically: net positive, +$802 over 4 trades**, same caveat — 2 of those 4
trades are today's, and both today's trades won.

**Drop today (the honest stress test, since today is one day and n=2): net negative, -$188
over 11 trades**, mean -$17/trade. This is the number that describes safe-3's bypass cohort
on every day *except* today, and it's a loser.

**Bottom line: the sign of "has the bypass helped safe-3" flips entirely on 2 trades placed in
the last 3 hours of this session.** Nothing here clears a bar for action — no OOS split, no
walk-forward, n=13 total / 11 ex-today. This is a descriptive ledger read (same standing as
`analysis/pain-ledger/mae-mfe.json`'s own "descriptive only" label), not an edge validation.
It answers "what did the bypass cost or earn to date" (the question asked) — it does not answer
"should the bypass be closed," which needs the pre-registration this repo's doctrine requires
before any config-freeze-window change ships.

---

## Caveats

- **safe-1 is entirely unclassifiable** — its whole real-fills history (24 trades, -$300 net
  if matched) predates the 2026-08-03 introduction of `core_tick_id`. Any claim about safe-1's
  bypass exposure is unsupported by this ledger; would need a separate join (e.g. nearest-tick
  timestamp matching against the pre-core_tick_id `core-decisions.jsonl` rows) that this session
  did not build.
- **VWAP-strategy entries are out of scope by construction** (no safe/bold split exists for
  them) — risky-1/risky-3 carry real dollars there (-$745 / -$1,316) that this report doesn't
  attribute to any cohort. Not part of the bypass question, but a reader summing "all of
  risky-1's P&L" from this report's cohorts alone will undercount losses.
- **Today's numbers are live-session reconstructions**, not the audited pain-ledger — verified
  by hand against the raw fills-ledger rows (buy 5@1.17 / sell 3@2.32 + 2@1.98 = +$507; buy
  5@0.74 / sell 3@1.63 + 2@1.57 = +$433) but not run through `pain_ledger.py`'s own MAE/MFE
  bar-walk machinery. Positions still open as of the ledger snapshot (none were, for the arms/
  symbols this report covers — confirmed, no `OPEN_UNFLATTENED` rows in today's cycles for
  safe-3/risky-1/risky-3).
- **Cohort classification is a verdict-field proxy**, not a byte-exact replay of
  `_bold_passed_blocks_from_row`'s `_score_peak_check`/`_HARD_SKIP_VERDICTS` logic (which needs
  raw trigger/score fields this ledger's `verdict` field summarizes). `veto-scope-safe-3.md`
  validated this proxy against real ledger fills for the structure-veto case specifically
  (1:1 match); it is not re-derived from first principles here.
- **All PF/WR/mean figures are DESCRIPTIVE** — no OOS split, no walk-forward, several cells
  have n<10. Treat every number in this report as a population/September snapshot, not a
  forward expectancy claim.
