# 2026-07-14 Trendline-Break Exhibit (G4) — n=1, honestly labeled anecdote

**Status: RESOLVED — the described break did not happen.** This report was commissioned to
reconstruct a "~12:10-12:15 ET" trendline break that, per the task brief, had already happened.
Real-time verification (below) caught that it hadn't — at commission time real ET was 11:56 ET, the
window was still 15-20 min in the future. Rather than fabricate a reconstruction, this report held,
did the legitimate prep work that doesn't depend on the outcome, then waited (bounded, live) until
12:20 ET — the full described window plus a buffer — and checked real bars. **SPY never came
within ~$1 of the support line in that window; it did not break.** Sections 2-5 are the real,
sourced findings that don't depend on the break (J's line reconstruction, the engine's actual
bull-side capture failure this morning, the live exit/strike rules). Section 6 is the definitive,
evidence-based "it didn't happen" resolution. Section 7 is the review synthesis.

---

## 0. Verdict

- **The described break did not occur.** Checked twice, independently, after the full 12:00-12:20
  ET window closed: (1) real SPY 1-min bars (Alpaca IEX) ranged **750.02-751.04** the entire
  window — never within ~$1 of the ~749 support line; (2) the live engine's own tick log
  (`core-decisions.jsonl`) shows `bear_score` **falling** from 8 to 4 across 12:10-12:20 ET and
  `HOLD` on every one of 22 ticks. See §6 for the full evidence and the most-plausible explanations
  for the mismatch with J's chart observation (different time window, a different specific line,
  or a feed/tick-level rounding difference at the wick — not resolvable without J's own screenshot).
- **What's real regardless of the break:** the engine tried to capture the morning's ACTUAL bull
  structure (752-ish reclaim, SUPER tier) six times across two accounts between 10:36-10:38 ET —
  and filled **zero** of them. Three free-model vetoes, one min-premium-floor skip, one PDT deny,
  one more veto. `trade-today.json`: `spy_fills_today: 0` as of this report. This is the more
  actionable, fully-resolved finding of the morning session.
- **Safe is already PDT-constrained for the rest of today** (`RISK_DENY_PDT`, "7 day-trades in 5d…
  blocks a 4th day-trade", fired 10:38:03 ET). Any later same-day PUT round-trip on Safe — trendline
  break or not — very likely hits the identical gate. This bounds what a "would-be" Safe P&L can
  honestly claim: the realistic broker-side outcome for Safe today may be a risk-gate deny, not a fill.

---

## 1. Real-time verification (the check that mattered)

```
$ python setup/scripts/et_clock.py
2026-07-14 11:56:31 Tuesday EDT
market_hours=True
```
```
mcp__alpaca__get_clock -> {"is_open": true, "timestamp": "2026-07-14T11:56:08.080339493-04:00", ...}
```
Both independent clocks (local machine, remote broker) agree to within 23 seconds. SPY 5m bars
(SIP feed) through 11:55 ET show price at 751.08, having spent the whole morning in a 747.4-753.9
band — no support violation, no close beyond any live trendline's break level. The described
12:10-12:15 dump had not printed. This report proceeded on real data only from that point forward;
see §6 for how (and when) the break window was actually resolved.

---

## 2. J's hand-drawn line, reconstructed from real bars

J's description: anchored at the premarket wick low (~747.4), respected at the 10:20-10:30
recovery lows (749.8-750.0), then later higher lows. Reconstructed from real Alpaca SIP 5-minute
SPY bars (not TradingView's exact tape, see caveat below):

| Point | Time (ET) | Bar O/H/L/C | Wick-valid? (T14 rule: protrusion ≥ max($0.05, 10% of range)) |
|---|---|---|---|
| Candidate low #1 | 07:05 | O 747.71 / H 747.94 / L **747.4619** / C 747.56 | wick_len 0.098 vs threshold 0.048 → **valid wick** |
| Candidate low #2 (true session low, 5m) | 07:10 | O 747.50 / H 748.29 / L **747.37** / C 748.28 | wick_len 0.13 vs threshold 0.092 → **valid wick, and lower/closer to J's "~747.4"** |
| Respect A | 10:20 | O 749.85 / H 750.88 / L **749.78** / C 750.13 | wick_len 0.068 vs threshold **0.110 → FAILS** the T14 wick-depth gate (borderline, ~62% of the required depth) |
| Respect B | 10:25 | O 750.11 / H 751.30 / L **749.96** / C 750.71 | wick_len 0.15 vs threshold 0.134 → **valid wick** |

**Finding:** the true premarket wick-low anchor at 5-minute resolution is **747.37 @ 07:10 ET**,
not 747.46 — both are legitimate wicks, but 747.37 is the deeper/lower one and the closer numeric
match to J's stated "~747.4". More importantly: **the first of the two 10:20-10:30 "respect" bars
J cited (749.78 @ 10:20 ET) technically fails the wick-protrusion rule the team shipped TODAY**
(2026-07-14, `WICK_MIN_FRACTION=0.10`) — its wick is only 62% of the required depth. This is
exactly the class of case that rule was built to catch (per the rule's own docstring: bars that
are "visually a body point... not a wick"). It is not necessarily wrong to eyeball it as a
respect — the rule's tolerance is a heuristic, not gospel — but it is a **borderline call worth
a second look with J**, not a clean pass. The second respect (749.96 @ 10:25 ET) passes cleanly.

Line A(07:10, 747.37) → B(10:25, 749.96): slope ≈ +0.0345/5m-bar. Projected through the rest of
the morning, this line sat at roughly **748.7-749.1** across 11:00-11:55 ET — consistent with
`trendline-log.jsonl`'s independently-detected WICK support line (`a=744.12→b=748.71`,
`break_level≈749.0` as of 11:50-11:55 ET) being in the same neighborhood, even though it is a
**different, older, multi-day line** (see §3).

**Caveat on data provenance:** this reconstruction uses Alpaca SIP 5-minute bars pulled live via
MCP, not the exact TradingView chart J drew on. Consolidated-tape 5m bars from different vendors
can differ by a cent or two at the wick; the anchor prices above should be read as "consistent
with J's description," not a pixel-exact replica of his drawing.

---

## 3. Why the engine's OWN shadow trendline is a DIFFERENT line entirely

`automation/state/trendlines-live.json` (T14, current as of this report) shows the engine's
best-scoring WICK support line as:

```
SUPPORT [WICK] 07-08 13:00@744.12 -> 07-14 10:15@748.71 | line now ~749.0 | respected x63 | INTACT
```

This is **not** J's line. Two structural reasons, both grounded in `trendline_engine.py` (read
only, not modified — a separate audit crew owns this file today):

1. **`fetch_spy_5m()` is RTH-only by explicit design** (`# RTH only (09:30-16:00 ET == 13:30-20:00
   UTC)`, line 153-154). J's anchor (07:05-07:10 ET) is **premarket** — it is structurally
   impossible for the engine's own candidate pool to ever contain it. This is not a scoring
   preference, it's an exclusion at the data-fetch layer.
2. **`N_DAYS=5` multi-day lookback + best-score selection** (`score = respect - 5*violations +
   span*0.1`) systematically favors older, longer-lived, more-touched lines over a fresh
   single-day line — the live line's anchor A is from **six days ago** (07-08). Even restricting
   to RTH, a fresh intraday line competes on `respect_count` against a line that's had 5 days to
   accumulate touches; it will usually lose on score alone.

**Net: even setting aside the shadow-vs-armed gate (A/B NEEDS-REVIEW, doctrine-known), the engine
literally cannot represent the specific premarket-anchored line J drew today** — not a
scoring/threshold tuning problem, a candidate-pool problem. Worth flagging to whoever owns the
in-flight subsystem audit (not edited here per this task's constraints).

---

## 4. What the engine actually did this morning (core-decisions.jsonl, both accounts)

### 4a. Bull side — the 752-ish reclaim (752.49 level from `today-bias.json`'s falsifiable prediction)

A real, SUPER-tier `BULLISH_RECLAIM_RIDE_THE_RIBBON` fired on **both accounts**, six times across
10:36:03-10:38:25 ET (SPY ≈ 752.01, `trigger_level_exact: 751.75`, `triggers: [level_reclaim,
ribbon_flip, confluence]`, `bull_score` 10). **All six attempts failed to fill:**

| ts_et | account | gate that killed it | detail |
|---|---|---|---|
| 10:36:03 | safe | `VETOED_BY_MODELS` | both free-model lanes cited HTF(BEAR)/ribbon(BULL) conflict + "unrealistic" 30c spread |
| 10:36:32 | bold | `VETOED_BY_MODELS` | same conflict cited by both lanes |
| 10:37:03 | safe | `VETOED_BY_MODELS` | same |
| 10:37:20 | bold | `SKIP_MIN_PREMIUM_FLOOR` | free-model veto cleared this time, but premium $0.24 < `min_entry_premium` $0.30 |
| 10:38:03 | safe | `RISK_DENY_PDT` | free-model veto cleared, but "7 day-trades in 5d at equity $1,747 < $25,000 — PDT rule blocks a 4th day-trade" |
| 10:38:25 | bold | `VETOED_BY_MODELS` | conflict cited again |

`trade-today.json` (`spy_fills_today: 0`, `ever_filled: true` [prior days], `fills: []`) and
`current-position.json` (`status: null`) confirm broker truth: **zero fills today**, on either
account, as of this report. The engine correctly identified real structure (bull_score up to 11,
tier SUPER) and could not get a single leg filled — three different gates stacked across six
attempts in under 2.5 minutes (C15: gates interact multiplicatively). At 11:06-11:08 ET a further
attempt was blocked by `block_elite_bull` (`SKIP_ELITE_BULL_LEVEL_RECLAIM`); nothing fired after.

### 4b. Bear side — structurally VIX-gated all morning

`today-bias.json` (written 09:15 ET): VIX 16.80 is below the `bear_min_exclusive_and_rising`
threshold (17.30) — "BEAR entries are VIX-filter-BLOCKED today regardless of chart structure."
Confirmed live: VIX printed 16.2-16.9 across the entire 09:30-12:02 ET window sampled from
`core-decisions.jsonl` (never approached 17.30). `bear_score` reached at most 8 (bull reached 11)
and never mattered — no `ENTER_BEAR`/`BEARISH_REJECTION` attempt appears in the log at all through
noon, because the VIX gate blocks the setup before scoring would even matter. **The CPI-driven
morning bearish bias (today-bias.json's own bearish read) was, by the doctrine's own admission,
untradeable on the bear side all morning purely on VIX level — independent of whether any bear
chart structure existed.**

---

## 5. What a trendline-break PUT WOULD trade under, if triggered (rules only — see §6 for outcome)

**No playbook setup named "trendline break" exists.** `BEARISH_REJECTION_RIDE_THE_RIBBON` (the
only live PUT setup) is a *rejection-at-resistance* pattern (2-of-3: level rejection, ribbon flip,
confluence) — structurally different from a *support-breakdown*. There is no armed/named
equivalent of "ascending support line breaks." What follows is an ANALYST-CONSTRUCTED overlay
using the actual live rules that would govern any PUT position on this account today, not a claim
that the live setup-detector would have literally tagged this as `BEARISH_REJECTION`.

**Confirmation convention (sourced, not invented):** first 5-minute bar whose CLOSE prints more
than `trendline_engine.py`'s own `TOL=$0.10` below the line's live `break_level` — the exact
convention that module already uses for its own violation-counting, and that mirrors
`exit_manager.py`'s (flag-gated) structure-stop docstring: "the first CLOSED 5m SPY bar beyond the
level." **Note this $0.10 buffer is an ENTRY-confirmation robustness margin only** — it is
deliberately looser than the LIVE exit-side structure-stop check (`_structure_stop_hit`, zero
buffer, strict `close > trigger_level`) and than the SS-B certified cell's own `STRUCTURE_BUFFER`
(0.0). Using a buffer for entry-confirmation but not for the exit-side structure check matches how
both pieces are actually built in this codebase — they answer different questions (robust enough
to call it a break vs. exact level for managing an open position) — not an inconsistency I
introduced.

**Strike (live rule, not sim):** Safe equity ≈ $1,747 → `crypto/lib/strike_selection.py`
`V15_SAFE_TIERS`, `$0-$2,000` tier → **offset 0 (ATM)**. `strike = round(spot)` for a put.

**Qty:** `min_contracts` base (3) → `risk_gate.max_affordable_qty` clamp → `risk_gate.check_order`
final authority (Rule 6: 30% equity cap Safe). **PDT check applies at this same gate** — see below.

**Exit shape — the REAL live cell** (`automation/state/fleet/strategies.py::RIBBON_RIDE`, the only
strategy whose `entry_setups` covers `BEARISH_REJECTION_RIDE_THE_RIBBON`; params.json confirms
`structure_stop_enabled: true` is live TODAY, so `stop_mode="structure"` resolves for real):

```
premium_stop_pct=-0.20 (flag-off fallback only — NOT what's live)
catastrophe_stop_pct=-0.50   <- the actual live cap in structure mode
tp1_premium_pct=+1.00 (sell 66.7% at +100%)
tp1_qty_fraction=0.667        <- NOT the CLAUDE.md-summarized 0.8; strategies.py overrides params (known drift, C29-adjacent)
profit_lock_mode="trailing", trail_pct=0.15, arm at +5% favor (DEFAULT_PROFIT_LOCK_ARM_PCT)
runner_target_pct=99.0 (effectively unconstrained — runner exits only via structure/ribbon-flip/trail/EOD, C30)
profit_lock_arm_scope="post_tp1" (default, not overridden) <- matches the task's requested live scope
stop_mode="structure": exit on first CLOSED 5m bar beyond trigger_level; catastrophe -50% backstops between closes
```

**Known gap:** `exit_manager.nearest_active_level` (the structure-stop's trigger_level source when
no exact `rejection_level` is threaded) reads `key-levels.json` horizontal levels only — it has
**no native trendline input**. Even if the trendline engine were wired live, today's structure-stop
would need a new provenance path to consume a trendline's break_level as `trigger_level`; that
wiring doesn't exist. For this exhibit's mechanical walk, the trendline's own break_level is used
directly as `trigger_level` (the natural choice), flagged here as a gap, not a claim it's wired.

**PDT gate — the finding that bounds the whole exercise for Safe:** the `RISK_DENY_PDT` at
10:38:03 ET ("7 day-trades in 5d… blocks a 4th day-trade") is a same-day, same-account constraint.
Nothing between then and any later trendline-break window changes Safe's rolling day-trade count
downward (it only ages out day-by-day). **Any same-day Safe round-trip PUT — this setup or any
other — very likely hits the identical `RISK_DENY_PDT` gate**, independent of the trendline
signal's quality. This is verified/re-checked live in §6, not assumed.

---

## 6. The actual break window — resolved live: **no break occurred**

Real ET clock was polled to **12:20:04 ET** (bounded live wait via a background monitor loop —
`et_clock.py`, 30s cadence, screenshots of every poll available) before writing this section, so
the ENTIRE 12:00-12:20 ET window — the described break time plus a 5-10 minute buffer — is now
resolved with real, closed bars. **It did not break.**

**SPY 1-minute bars, 12:00-12:19 ET (Alpaca IEX, live):** range **750.02 - 751.04** the whole
window. Low print: 750.02 @ 12:03 ET. The support line computed in §2 sat at roughly **748.7-749.0**
across this same window (A=07:10@747.37, B=10:25@749.96, slope +0.0345/5m-bar, projected to
12:00-12:20 ET). **SPY never got within ~$1.00 of the line, let alone closed below it.** No 5m
close ever printed below `line_value - $0.10` (§5's confirmation convention) — the trigger the
would-be PUT entry needed never fired.

**Corroborated independently by the live engine's own tick log** (`core-decisions.jsonl`,
12:10:04-12:20:04 ET, both accounts, 22 rows): `verdict: HOLD` on every single tick.
`bear_score` **declined** from 7-8 (12:10 ET) to **4** (12:16-12:20 ET) — the tape got LESS
bearish through the window, not more. VIX drifted 16.57 → 16.74, still ~0.56 short of the 17.30
bear-entry gate. Price action for the actual 12:00-12:20 ET window was a shallow ~$1 pullback
(751.6 → 750.0) that stabilized and chopped sideways — a normal midday lull, not a breakdown.

**Conclusion:** the "~12:10-12:15 ET dump through the trendline" described in this task's brief
did not happen in this session, on this instrument, in this window — checked against two
independent live sources (raw SPY tape AND the engine's own real-time scoring) after the full
window plus buffer had closed. This is not "the break happened but data was thin" — the bars are
clean, liquid, RTH bars and they show a boring, range-bound 20 minutes. **No entry, no exit, no
would-be P&L can be honestly produced for an event that did not occur.** Sections 2-5 above stand
on their own as real findings (J's line reconstruction, the engine's actual bull-side capture
failure, the VIX gate, the live exit/strike rules) independent of this non-event. If J observed a
break on his own chart in real time that these bars don't show, the likely explanations are (in
order of plausibility): a different/later time window than 12:10-12:15, a different line than the
one reconstructed in §2 (there were, per J, at least two low-quality lines drawn by a session
today — worth asking which line specifically), or a chart read against a different data feed
(TradingView consolidated tape can print a wick Alpaca's IEX/SIP 1-min bars round differently at
the very tip) — not a discrepancy this report can resolve without J's own chart screenshot from
the moment.

---

## 7. Review synthesis — what a "full research agent on trendlines and their breaks" should fix

Ranked by what's actually load-bearing, not by discovery order. All n=1/today-only except where
noted otherwise.

1. **The engine's trendline candidate pool structurally excludes premarket anchors.**
   `fetch_spy_5m()`'s RTH-only filter (§3) means no multi-day, no-tuning fix can ever surface a
   line like J's today — the anchor bar is never in the data. If premarket-anchored lines matter
   to J's actual trading (this one did — it's the whole reason for this exhibit), RTH-only needs
   to become a parameter, not a hardcoded filter. This is a scope decision for whoever owns
   `trendline_engine.py` next (not edited here per this task's constraints).
2. **Best-of-5-days scoring will rarely surface the freshest single-day line**, even once RTH-only
   is relaxed — an old, long-lived, well-touched line will usually out-score a fresh one on
   `respect - 5*violations + span*0.1`. If the goal is "draw the line J would draw today," the
   engine may need a **per-day candidate alongside** the multi-day best line, not a replacement of
   it — both are legitimate reads, they answer different questions.
3. **The T14 wick-depth threshold (10%/5c) is a real quality filter but produces borderline calls**
   worth spot-checking against J's eye, not just auto-trusting (§2: the 10:20 ET bar was 62% of
   the required wick depth — a plausible respect to a human, a fail to the current rule). Not a bug
   to fix; a "second-look" list to generate for lines with a near-miss wick (e.g., 50-100% of
   threshold) rather than silently dropping them to the body family.
4. **No live trigger exists for "ascending support breaks down"** — confirmed by direct code read:
   `detect_trendline_rejection_bearish` (backtest/lib/filters.py) is resistance-rejection only
   (`require_decreasing=True`); `BEARISH_REJECTION_RIDE_THE_RIBBON` is a rejection-at-level
   pattern, not a support-breakdown pattern. If a support-break IS meant to be tradeable (this
   exhibit's whole premise), it needs a **new, named playbook setup** with its own 3-example
   confirmation bar per the playbook's own promotion process (`markdown/0dte/playbook.md` §"How a
   setup gets into this playbook") — not an ad-hoc overlay on `BEARISH_REJECTION`.
5. **The exit machinery for a hypothetical trendline-break trade already exists and is validated**
   (`strategies.py::RIBBON_RIDE`, live `structure_stop_enabled: true`) — the missing piece is
   purely the ENTRY trigger + a trendline-aware `trigger_level` provenance path into
   `exit_manager.nearest_active_level` (today it only reads horizontal `key-levels.json`, no
   trendline input). This is the smaller, more mechanical half of the build.
6. **Gates stack multiplicatively and killed a real SUPER-tier setup 6/6 times this morning**
   (§4a) — worth its own look independent of trendlines: two free-model vetoes, one premium
   floor, one PDT deny, all inside 2.5 minutes on a setup that scored well. If free-model veto
   false-positive rate on HTF/ribbon divergence is a recurring pattern (not just today), that's
   exactly what the existing free-model-audit-harness doctrine (CLAUDE.md OP-32 wire-in) is for —
   feed today's 3 veto reasons into it rather than treating this as a one-off.
7. **Safe's PDT budget is exhausted for the rest of today** (§5) — mechanically true regardless of
   any trendline finding. Worth a standing glance-able instrument (`day_trades_used_5d` per
   account, surfaced before market open) rather than discovering it via a `RISK_DENY_PDT` string
   in `core-decisions.jsonl` after the fact.

**What this exhibit does NOT claim:** that a trendline-break setup (had one existed and had a break
actually occurred — neither was true today, §6) would have been profitable, that the engine
"should have" traded anything today, or that any of the above are bugs rather than deliberate,
documented scope boundaries. n=1, and today's n=1 is specifically a **non-event** — the motivating
premise didn't hold up under real-time verification. This still motivates the broader study (the
gaps in §7 are real and evidenced independent of today's specific price action); it proves nothing
about trendline-break profitability alone, because no break happened to measure.
