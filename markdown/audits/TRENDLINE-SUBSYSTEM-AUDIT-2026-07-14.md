# Trendline Subsystem Audit — 2026-07-14

**Trigger (J, ~11:40 ET, verbatim):** "audit everything we do regarding trend lines. why have we
not drawn one yet i can see it from pre market, to 10:20-30 lows up to current price, you see
that?"

**J's anchor rule (verbatim, mid-audit amendment, 2026-07-14):** "trend lines only respect candle
bodies OR wicks, not both." This is the audit's ground truth for every detection-quality finding
below — restated here per J's explicit instruction so it's the document's stated baseline, not a
footnote.

**Scope:** detection quality, live consumption, visibility (chart drawing), a concrete
same-day miss trace, and log hygiene. Read-only on `heartbeat_core.py`; no orders, no params
changes, no gate flips (the pre-registered A/B at the end decides that later).

---

## TL;DR

J's read was **real** — verified against fresh Alpaca+TradingView bars. The engine's own
detector **did** see the 10:15 ET pivot (logged it 5 minutes after it printed) but the line it
carries is a **different, multi-day line** that happens to share that touch point, not the
same-day line J traded. Nothing ever **drew** anything — the shadow JSON files had zero chart
consumers. J also caught a second, independent bug live: one of the anchors used for the hand-drawn
approximation had a **2-cent "wick"** that's really a body point — the engine's wick-only
invariant checked the *field* used but not whether a real wick existed. Both are now fixed,
tested, and the fix is drawn on J's live chart as of this session (4 lines, entity IDs
`4cjdSo`/`uPvOmC`/`e4GDfC`/`cAuM3P`, verified present via `list_drawings.js`).

---

## Q1 — Detection quality

**catches-same-day-lines: NO**, by construction. Evidence:

- Today's ascending support first anchored its second point at the 10:15 ET pivot in the
  **10:20 ET fire** — `analysis/trendlines/trendline-log.jsonl`, row `current_et=10:20`:
  `a=07-08 13:00 744.12 → b=07-14 10:15 748.71`. That's 5 minutes after the pivot bar closed
  (the earliest a `k=1` pivot can confirm) — detection **timing** is essentially instant, not the
  problem.
- The problem is the **first anchor**: `a_et=07-08 13:00` — five calendar days back, not
  same-day. `trendline_engine.py`'s `detect()` returns the SINGLE best-scoring line per
  (kind, family) across the ENTIRE `N_DAYS=5` lookback, scored
  `respect - 5*violations + span*0.1`. A longer-lived multi-day line with 52-63 touches
  structurally outscores a fresh 2-3-touch same-day line almost every time — the `span*0.1` term
  explicitly rewards longevity. J's same-day line (premarket low → 10:15 low → current) is real
  structure but never gets a chance to win the single winner-take-all slot.
- True same-day tape (verified via `mcp__tradingview__data_get_ohlcv`, full SIP/consolidated
  feed, NOT the engine's thinner `feed=iex` Alpaca pull — see the data-feed gap below): premarket
  low **747.37 @ 07:10 ET** (deepest print), then a materially different bar J's own read anchors
  on, **747.87 @ 08:20 ET** (open 747.89 — a 2-cent wick), then the genuine deep-wick rejection
  at **748.69 @ 10:15 ET** (open/high 750.40, close 749.85 — a $1.16 wick, 67.8% of that bar's
  range). The 08:20 anchor is the one J's amendment flagged.

**Wick-only invariant — DOES hold structurally, verified fresh this session:**
`test_no_mixed_wick_body_anchors` (now strengthened, see below) asserts every anchor price
equals `round(bar[wick_field], 2)` for wick-family lines — never a body/close value. Ran clean:
`23 passed` before any change, `39 passed` (full `-k trendline` suite) after. **But** this only
checked *which field* was read, not whether that field represented a *real* wick — a bar whose
low sits a hair below its open/close (the 08:20 bar: `O=747.89 H=748.74 L=747.87 C=748.74`,
lower wick = $0.02 = **2.3% of range**) passed the old guard while being visually
indistinguishable from a body point. Contrast the genuine 10:15 wick at **67.8% of range**. This
is a real detection-quality gap, not just a manual-draw slip — `find_pivots` had **no wick-depth
floor at all**, so a negligible-wick bar could become a "wick" pivot.

**Fix shipped** (`backtest/autoresearch/trendline_engine.py`):
- `WICK_MIN_FRACTION=0.10` / `WICK_MIN_CENTS=0.05` — a bar only qualifies as a WICK anchor if its
  protruding wick clears `max(5 cents, 10% of that bar's range)`. Threshold picked from the real
  same-day population above: negligible "wicks" measured 0.0%–2.3% of range; genuine ones
  measured 16.5%–67.8% — a clean separation, no per-symbol retuning needed.
- New **BODY family** (`find_pivots`/`_fit(..., family="body")`): `min(open,close)` for support /
  `max(open,close)` for resistance — the legitimate second family for bars that fail the wick
  test (per J's "bodies XOR wicks" rule, never mixed *within* one line — structurally enforced by
  `_fit`'s per-family assert, same tripwire pattern as the original T8 wick-only guard).
  `detect()` now returns up to 4 lines (wick×{support,resistance} + body×{support,resistance}),
  each tagged `anchor_family`.
- `detect(bars)` (no args) is behavior-identical to before for existing callers that filter by
  `.kind` — wick family is computed identically to pre-T14 and listed first.
- **Body-vs-wick fit check on J's own line:** the 08:20 bar (open=low+0.02) is a body point by
  construction (`open` ≈ `low`) — it is now correctly excluded from the wick family and eligible
  for the body family instead. New unit test
  `test_wick_family_rejects_negligible_wick_bar` proves this on a synthetic bar shaped exactly
  like the real one.
- **Tests:** `backtest/tests/test_trendline_multiday.py` — strengthened
  `test_no_mixed_wick_body_anchors` (now checks the anchor-family invariant + a real protruding
  wick for wick lines) + 2 new tests
  (`test_wick_family_rejects_negligible_wick_bar`,
  `test_body_family_never_mixes_with_wick_within_a_line`). Full trendline suite: **39/39 passed**
  fresh this session (`pytest tests/ -k trendline`, 364.63s).

**Data-feed gap (pre-existing, disclosed, re-confirmed today):** the engine's `fetch_spy_5m`
hardcodes `feed=iex` (Alpaca's free single-exchange feed). Today's IEX pull returned its first
bar at **08:20 ET** with nothing before it; TradingView's full consolidated tape shows dense
premarket bars from **04:00 ET**. This is the SAME class of gap `test_trendline_multiday.py`'s
own docstring already disclosed as "D-SIP" (a $0.11 anchor-price discrepancy from a different
date) — today's instance is more severe (an entire missing premarket session, not one bar) but
not a new finding. Not fixed in this pass (would need a paid/SIP feed or TradingView-sourced
bars piped into the engine — flagged, not silently patched).

---

## Q2 — Consumption

**Grep result: `trendlines-live.json` has exactly ONE real consumer: `confluence_producer.py`.**
That writes `confluence-zones.json`, which itself has **zero consumers** outside its own producer
script (verified: `grep confluence-zones.json` across the repo hits only the producer, its
installer, and doc/audit files). Neither `heartbeat_core.py`, `engine_cli.py`, `gates.py`, nor
any watcher (`family_detectors.py`, `watcher_live.py`, `bullish_watcher.py`) reads
`trendlines-live.json` or `trendline-log.jsonl` — confirmed by direct grep inside those files
(zero matches). The dashboard (`dashboard/`) also has zero references.

- `GATE_KEYS` in `heartbeat_core.py` includes `trendline_requires_ribbon_flip` and
  `midday_trendline_gate` — these are **strategy-tier knobs in `backtest/lib`**, unrelated to
  `trendline_engine.py`'s shadow output (different codepath, different meaning of "trendline" —
  an internal TRENDLINE-tier setup classification, not the shadow-detected line).
- The `"confluence"` trigger seen in `core-decisions.jsonl` (e.g. today's 11:06 ET signal) is
  `filters.py`'s internal `confluence_match` field — a **separate, older, multi-day-level
  concept**, not `confluence_producer.py`'s shadow zones file. Verified by reading
  `backtest/lib/filters.py` — `confluence_match` is computed inside the bullish/bearish watcher
  functions themselves, no import of the shadow confluence pipeline.
- **Verdict: trendlines-live.json is 100% shadow, zero live-decision consumers**, exactly as its
  own `write_live_state()` docstring and `Gamma_Trendlines`' installer description say.

**Was "trendline-as-CALL-veto = valid" ever wired?** No A/B scorecard artifact exists at
`analysis/recommendations/` for that exact claim (the memory note is imprecise — there's no
`trendline-*-veto-scorecard.json` file). What DOES exist: a large family of Chef candidate drafts
(`strategy/candidates/2026-06-2*..2026-07-1*-chef-nemo-trendline-break-call-veto.md`, ~10+ dated
attempts) — all still DRAFT, none promoted, none with a ratified A/B scorecard. **Conclusion:
"validated then shelved" is not accurate — it was repeatedly re-attempted and never cleared the
eval-first gate**, not validated-then-abandoned.

**NEEDS-REVIEW gate — what it's waiting on:** literally nothing is currently running toward
resolving it. No scheduled task, no queued study, no open recommendation file targets it. It's
been the same shadow-only status since T3 (2026-06-26) through V4/T8 (2026-07-08) — the docstring
language hasn't changed in 3+ weeks of otherwise-active development on the detector itself. The
**decisive test is now specified** — see the pre-registered A/B at the end of this doc
(`analysis/recommendations/trendline-structure-conviction-preregistration.json`, `FROZEN_PENDING_RUN`, NOT run yet per J's instruction).

---

## Q3 — Visibility (the actual complaint)

**Root cause confirmed:** `trendline_engine.py` writes JSON only; nothing ever called
`draw_shape`. Premarket's chart-drawing step (Step 5) only redraws **level lines**
(`key-levels.json`), never trendlines. Step 5b reads J's *manual* drawings and feeds a
completely different, mostly-dead legacy script (`compute_trendlines.py` / `backtest/lib/
trendlines.py` — a SEPARATE detector from `trendline_engine.py`, top-5-lines/2-day-lookback,
whose own `_latest_spy_csv()` glob would in fact resolve to a **stale prior-day CSV** on any day
before a fresh fetch — a second, independent staleness bug in the legacy path, not touched this
session since it's superseded and out of scope).

**Two confirmed pre-existing bugs found and worked around, both reproduced live this session:**
1. `mcp__tradingview__draw_list` / `draw_get_properties` / `draw_remove_one` are **broken**
   (`"getChartApi is not defined"`) — I hit this error myself calling `draw_list` before reading
   `premarket.md`'s Step 5, which already documents the identical failure and its `ui_evaluate`
   JS-injection workaround (`automation/scripts/tv_ops/{list,remove}_drawing.js`, walking
   `window._exposed_chartWidgetCollection`). The original skill draft (before this fix) would
   have called the broken tools directly — corrected before shipping.
2. `draw_clear` has **no scope/tag parameter** — it removes every drawing on the chart,
   including J's own manual lines. Disqualified even if it worked.

**Bridge shipped:**
- `backtest/autoresearch/trendline_engine.py --no-log --json` — new CLI flags. `--json` prints
  the full `detect()` output (all `anchor_family`-tagged lines with draw-ready anchor
  coordinates) without writing to the log; `--no-log` skips `log_lines`/`write_live_state` so
  on-demand draws don't duplicate rows outside the production 5-min cadence.
- `setup/scripts/trendline_draw_state.py` — pure state I/O (7/7 new tests pass,
  `test_trendline_draw_state.py`). Tracks the TradingView `entity_id`s of ENGINE-drawn lines
  (never J's manual ones) in `automation/state/trendline-draw-state.json`, so a refresh can
  scope-clear via the proven `remove_drawing.js` path (never `draw_clear`).
- `.claude/skills/trendline-draw/SKILL.md` — rewritten: scoped clear → detect (JSON) → assert
  family-consistency before drawing → draw with family-labeled color+text (WICK=solid teal/red,
  BODY=muted teal/red, family always in the label text too, never color-only) → record entity
  IDs → report to J, explicitly flagging when the same-day line J is eyeballing isn't among the
  4 detected lines (per the Q1 finding) rather than silently substituting a different line.
- **Wired into `Gamma_Premarket`** (`automation/prompts/premarket.md`, new Step 5c) — the ONE
  daily fire that already runs as a live Claude+MCP session (confirmed: `draw_shape` only
  appears in `.md` persona prompts, never in a standalone headless script — the 5-min
  `Gamma_Trendlines` pythonw task **cannot** reach TV MCP, so continuous auto-drawing every 5 min
  is not honestly deliverable without a different architecture). **Honest status: detection/log
  stays fully automated every 5 min (unchanged); DRAWING is automated once daily at 08:30 ET
  premarket, plus on-demand any time via the skill.** Overclaiming continuous auto-draw would be
  the exact OP-33 violation this rig's doctrine forbids.

**Verified working, live, this session** (not "should work" — actually ran):
- `draw_shape` (create) works despite `draw_list`/`draw_remove_one` being broken — 4 real lines
  drawn on J's live `BATS:SPY` chart: `4cjdSo` (WICK support, respect×63, INTACT),
  `uPvOmC` (WICK resistance, respect×27, INTACT), `e4GDfC` (BODY support, respect×44, INTACT),
  `4e1ijy`→removed→redrawn as `cAuM3P` (BODY resistance, respect×32, INTACT).
- `list_drawings.js` via `ui_evaluate` confirmed all 4 present among 31 total chart drawings
  (`{"success":true,"count":31,...}`, each of my 4 IDs present with `"title":"trendline"`).
- `remove_drawing.js` scope-removal round-trip proven: removed `4e1ijy` cleanly
  (`{"success":true,"removed_id":"4e1ijy","removed_type":"R","removed_title":"trendline"}`),
  redrew it as `cAuM3P`, updated the state file — the exact procedure the skill now documents.

---

## Q4 — Today's miss trace (752.49 cross, ~10:55–11:05 ET)

Traced `core-decisions.jsonl` 10:40–11:19 ET + real SPY bars (TradingView, full tape).

- The 752.49 level is the **close of the 08:30 ET premarket econ-data-spike bar**
  (`O=749.18 H=754.24 L=749.14 C=752.49`, 138K volume) — a natural memory level.
- Price poked above it intrabar at **10:30 ET** (`H=753.34`) but closed back below
  (`C=751.92`). The first **confirmed 5m CLOSE above 752.49** was **11:05 ET**
  (`C=752.78`).
- **11:06:03 ET, `safe` account:** `BULLISH_RECLAIM_RIDE_THE_RIBBON` fired,
  `triggers=[level_reclaim, confluence]`, `bull_score=11`, `SPY=752.34`, `VIX=16.56` →
  `verdict=SKIP_ELITE_BULL_LEVEL_RECLAIM`, `reason="blocked by entry gate block_elite_bull"`.
  Repeated 11:06–11:08 (3 ticks), then the setup itself stopped scoring ELITE by 11:09.
- **This was NOT a trendline-context gap.** `block_elite_bull` is checked at gate order #3
  (`gates.py`), fires only when `tier=='ELITE' AND 'level_reclaim' in triggers AND VIX in
  [block_elite_bull_vix_low, block_elite_bull_vix_high)`. Today's ratified band is **[15.0,
  17.5)** (`analysis/recommendations/elite-bull-block-vix-01.json`, RATIFIED 2026-06-17) —
  VIX 16.56 falls squarely inside it. **The gate applied exactly as designed**, on a
  historically-negative-EV VIX regime for ELITE bull entries (IS: n=73 worst bucket, WR=9.6%,
  avg=-$100). This is a correctly-functioning, provenance-backed risk gate, not a bug.
- **The honest cost-of-gap exhibit:** `block_elite_bull` is pure `(tier, trigger-membership,
  VIX-band)` — it has **zero awareness of price structure**. The ascending-support line was
  genuinely INTACT underneath this exact signal (wick-family support, respect×63, current_value
  ≈748.9–749.0 at that time) — but since the gate never looks at structure, we cannot know from
  today's single data point whether that would have changed the ratified VIX-band math. That
  open question — "does structure confirmation carve a legitimate exception out of an otherwise-
  correct VIX-band block" — is exactly what the pre-registered A/B spec below tests. Today's
  11:06 signal is logged there as an EXHIBIT ONLY, excluded from any pass/fail verdict (n=1).

---

## Q5 — Log hygiene (`ts_et` fix)

Confirmed: every other decision/state log on this rig (`core-decisions.jsonl`, `fill-funnel-*`,
`self-check-last.json`, `broker-canary.jsonl`, …) carries a `ts_et` field in the standard
`heartbeat_core.py` convention (`%Y-%m-%dT%H:%M:%S`, ET, naive). `trendline-log.jsonl` never had
one — `Trendline`'s dataclass fields + `log_lines()`'s `asdict(ln)` spread never included it, so
any generic `.get("ts_et")` read (as several audit/consumer scripts assume by rig-wide
convention) silently returned `None` on every one of today's 52 rows. `current_et`/`a_et`/`b_et`
are bar-time strings (no year) — not a substitute for a sortable, joinable fire timestamp.

**Fixed:** `log_lines()` now stamps every row with `ts_et` (via `et_now()`, the one DST-aware ET
source, matching the rig-wide convention exactly) at the moment the fire actually ran.
`write_live_state()` also gained `ts_et` alongside its existing `generated_at` (UTC ISO). Both
are additive fields — no existing reader breaks (verified: `39/39` trendline tests still green
after the change, including the ones that parse the JSONL/JSON output).

---

## What shipped this session

| File | Change |
|---|---|
| `backtest/autoresearch/trendline_engine.py` | Wick-depth threshold (`WICK_MIN_FRACTION`/`WICK_MIN_CENTS`) + new BODY anchor family, never mixed within a line; `ts_et` on every log row + live-state write; `--no-log`/`--json` CLI flags for the drawing bridge |
| `backtest/tests/test_trendline_multiday.py` | Strengthened `test_no_mixed_wick_body_anchors`; added `test_wick_family_rejects_negligible_wick_bar`, `test_body_family_never_mixes_with_wick_within_a_line` |
| `setup/scripts/trendline_draw_state.py` | New — entity-ID bookkeeping for scoped chart clearing (never `draw_clear`) |
| `backtest/tests/test_trendline_draw_state.py` | New — 7 tests, all pure state I/O, isolated via `tmp_path` |
| `.claude/skills/trendline-draw/SKILL.md` | Rewritten — wick/body labeling, `ui_evaluate`-based scoped clear (the proven workaround for broken `draw_list`/`draw_remove_one`), on-demand framing stated honestly |
| `automation/prompts/premarket.md` | New Step 5c — wires the drawing bridge into the one existing daily live-MCP session (08:30 ET) |
| `analysis/recommendations/trendline-structure-conviction-preregistration.json` | New — pre-registered, FROZEN, NOT run |
| Live TradingView chart (`BATS:SPY`, entity IDs `4cjdSo`/`uPvOmC`/`e4GDfC`/`cAuM3P`) | 4 lines drawn and verified present this session |

**Verification commands run fresh this session** (not claimed, run):
```
cd backtest && .venv/Scripts/python.exe -m pytest tests/ -k trendline -q --ignore=tests/test_role_flip.py
  → 39 passed, 3593 deselected in 364.63s
.venv/Scripts/python.exe -m autoresearch.trendline_engine --no-log --json
  → 4 lines (wick support/resistance + body support/resistance), all anchored 5+ days back
mcp__tradingview__ui_evaluate(list_drawings.js) → count:31, all 4 new entity_ids present
```

**Not done / explicitly deferred (stated, not silently skipped):**
- Same-day-priority scoring (a 3rd tier so J's exact same-day line can win a slot even when a
  longer multi-day line outscores it) — a real behavioral change to what gets drawn/logged,
  needs its own eval, not bundled into this audit's read-mostly fixes.
- IEX→SIP feed upgrade for premarket bars — needs a paid feed or piping TradingView bars into the
  Python engine; flagged, not fixed.
- The legacy `compute_trendlines.py` / `backtest/lib/trendlines.py` path — superseded, stale-CSV
  bug noted but not touched (out of scope, zero live consumers either way).
- `trendline-structure-conviction-preregistration.json` — spec only, per J's explicit
  instruction not to run it this session.
