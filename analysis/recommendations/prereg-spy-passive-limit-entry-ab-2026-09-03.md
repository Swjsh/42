# PREREG — SPY 0DTE Passive-Limit Entry A/B (EDGE-1-PASSIVE-LIMIT-GRADUATION, next step)

**Status:** FROZEN PRE-REGISTRATION — NOT YET EXECUTED. Document-only fire; no code touched
by this file. Frozen 2026-09-03 04:41 ET (`et_clock.py`, quoted below).

**Source queue item (`automation/overnight/queue.md`, verbatim):**
> `EDGE-1-PASSIVE-LIMIT-GRADUATION (HIGH, execution-alpha, SEC-DERA-verified) :: Graduate
> entry_manager (T-W5) passive-limit entries: TWIN-B3 live measurement on the crypto twin ->
> SPY A/B. Halves the dominant measured loss driver (transaction costs = >70% of retail 0DTE
> losses; non-marketable limits cost ~$0.021-0.028 vs $0.05 marketable). TWIN-B3 leg SHIPPED
> 2026-07-15 (live A/B accruing on twin; first passive fill +6.13bps). NEXT gate: >=20 twin
> passive fills in automation/state/crypto-twin/entry-quality.json -> then write the frozen
> SPY A/B pre-registration (delta=0.10/patience=3/cancel). :: depends:none ::
> status:in-progress-live-measuring`

**Graduation bar (`markdown/planning/TWIN-PROGRAM.md` §B3, verbatim):** "GRADUATION BAR FOR
SPY (documented, NOT implemented): >= 20 twin passive FILLS accrued in entry-quality.json
with fill-rate + improvement stats, THEN a frozen SPY A/B pre-registration (entry-2's frozen
params: delta=0.10, patience=3, policy=cancel) before any SPY path change. Twin numbers
inform MECHANISM only -- never SPY evidence." **Bar is exceeded 13x over** (258 fills vs the
20-fill gate) — this document is that pre-registration.

---

## 1. Hypothesis + the twin evidence as PRIOR

**Hypothesis:** a passive limit resting inside the spread (delta=0.10 below the ask/mid,
patience 3 polls, cancel-then-marketable on timeout) fills often enough, and cheaply enough
when it fills, to beat paying the marketable spread on SPY 0DTE options — net of the cost of
the entries it misses or delays.

**Prior — `automation/state/crypto-twin/entry-quality.json`, read 2026-09-03
(`updated_utc: 2026-09-03T08:05:37.628902+00:00`, `ab_counter: 677`):**

| cohort | attempts | fills | misses | fill_rate | abandonment_rate | avg time-to-fill | avg improvement |
|---|---|---|---|---|---|---|---|
| **passive** | 339 | 258 | 81 | 0.7611 | 0.2389 | 30.362 s | **+$33.40/BTC = +4.86 bps** |
| **marketable** | 339 | 339 | 0 | 1.0 | 0.0 | 0.281 s | **-$3.32/BTC = -0.33 bps** (pays the spread) |

Exact fields quoted: `passive.avg_improvement_usd_per_btc: 33.3979`,
`passive.avg_improvement_bps: 4.8607`, `passive.avg_time_to_fill_sec: 30.362`,
`passive.fill_rate: 0.7611`, `passive.abandonment_rate: 0.2389`;
`marketable.avg_improvement_usd_per_btc: -3.3155`, `marketable.avg_improvement_bps: -0.3274`.
First live rep (TWIN-B3, 2026-07-15 03:57 UTC): limit BUY 0.0024 BTC @ $64,764.15 vs ask
$64,803.88/bid $64,724.41, filled at 60.7s, +$39.73/BTC = +6.13 bps.

**Explicit caveat (load-bearing, do not skip):** this is a BTC spot prior, not SPY option
evidence. BTC/USD spot spreads on the twin's venue are continuous-market, sub-basis-point-
tight, deep-book microstructure; 0DTE SPY option spreads are quote-driven, width-in-cents
(often a large fraction of premium on OTM/cheap contracts), and can gap or widen sharply
intraday. `entry_manager.py`'s own docstring (T3, `entry-exit-matrix-t3-entries.md`) is the
only SPY-shaped evidence for this mechanism and it is a BACKTEST exhibit (741P: market@0.96 ->
limit@0.77, -$57.60 -> +$231.00 on the identical exit shape), not a live SPY fill. Twin
numbers inform MECHANISM only per the graduation bar text above — they are not and cannot be
promoted to a SPY improvement/fill-rate forecast.

**Live SPY option spread reading: NONE YET.** Checked both live surfaces:
- `analysis/pain-ledger/latency.json` — this is a fill-pipeline LATENCY decomposition
  (`bar_close_ts` -> `core_verdict_ts` -> ... -> `fill_ts`), explicitly `"INSTRUMENT ONLY --
  descriptive, never load-bearing for any trading/gate decision"`. It has no bid/ask/spread
  field at all — it cannot answer "how wide is the SPY 0DTE spread," only "how long did the
  pipeline take" (e.g. 2026-09-02 safe-3 total_s 427.073, dominated by the 363s
  bar-close-to-verdict stage, not order mechanics).
- `automation/state/xsp-spread-recorder-status.json` (`xsp_spread_recorder.py`, installed via
  `setup/scripts/install-xsp-spread-recorder.ps1`) is the dedicated instrument for this and
  it exists, but as read 2026-09-03 04:4x ET its own status file shows
  `"last_cycle_rows_written": 0`, `"skip_reason": "outside RTH window (09:35-15:55 ET
  weekdays)"` — zero rows written since it started (`started_at_et:
  2026-09-03T04:37:49`), and no `xsp-spread-tape-*.jsonl` file exists on disk yet (checked
  `automation/state/` — none found). **No live SPY/XSP spread-width reading exists as of this
  writing.** The frozen bars in §3 below therefore cannot be sized against a known spread
  width; they inherit the twin's n-based gate instead (see §3).

---

## 2. SPY A/B design (mirrors TWIN-B3 exactly, `markdown/planning/TWIN-PROGRAM.md` §B3)

**Mechanism as it exists today (verified, `automation/state/fleet/entry_manager.py`, T-W5):**
- `EntryState.from_signal(symbol, side, signal_premium, delta, patience_ticks, policy)` sets
  `limit_price = round(signal_premium * (1 - delta), 4)`.
- `plan_entry_action(state, *, ask)` is the pure per-tick decision core: fills when
  `ask <= limit_price - 0.01` (mirrors `t3_entry_matrix.entry_fill`'s `bar_low <= L - 0.01`
  tolerance); otherwise holds until `elapsed_ticks >= patience_ticks`, then resolves per
  `policy` (`"cancel"` -> `CANCEL`/status `missed`; `"convert"` -> `CONVERT` at the current
  ask/status `converted`).
- **STATUS TODAY: SHADOW ONLY.** The module's own docstring states it plainly: "No arm
  places an order through this module yet." The only production entry path for every live
  SPY arm remains the marketable simple limit `ask + entry_cross_buffer`
  (`automation/state/fleet/fleet_live.py:553`, `fb.marketable_limit_price` — verified by
  grep; also referenced from `heartbeat_core.py:1140` for the mcp_heartbeat/CORE accounts).
  A `shadow_entry_actuator.py` is referenced in the module docstring as the read-only replay
  driver but does **not exist on disk today** (only its output,
  `automation/state/entry-shadow.jsonl`, 98 rows, last dated 2026-07-06, does) — the shadow
  read-only harness that would produce a live-tick-quality SPY fill-rate reading has gone
  stale/unmaintained since early July. This is disclosed, not fixed, by this document.
- **Frozen knobs (entry-2, reused verbatim, unchanged from the twin):** `delta=0.10`,
  `patience_ticks=3`, `policy="cancel"` (not `"convert"` — a missed passive entry is
  abandoned, not chased at market, so the abandonment-cost question in this design is real
  rather than smoothed away by an automatic fallback).

**A/B randomization (mirrors `crypto_twin_core.place_entry_ab`'s even/odd `ab_counter`
alternation exactly, substituting a per-signal id for the twin's persisted counter since the
fleet path already carries a stable per-tick id — `core_tick_id` in
`analysis/pain-ledger/latency.json` — that survives restarts, which a mutable counter does
not):** for each qualifying entry signal, take the signal id's parity — **even -> marketable
(control, byte-identical to today's path)**, **odd -> passive** (`entry_manager`'s T-W5
machinery: rest a limit at `signal_mid * (1 - 0.10)`, poll patience=3 one-minute ticks,
cancel-then-fall-back-to-marketable on timeout, matching this document's twin-mirrored design
brief). Deterministic, not random-seeded — same reproducibility property TWIN-B3 has.

**Arms — PAPER ONLY (read `automation/state/fleet/accounts.json`, all `broker` values are
Alpaca paper / custom_rest-to-Alpaca-paper; no arm in this repo is live-money armed today,
`GAMMA_CORE_ARMED` is unset per OP-0 #1):**

| arm | execution | status | why chosen / excluded |
|---|---|---|---|
| **risky-1** (`FLEET-FULLSEND-R`, acct `PA3S9N1IV0A4`) | `fleet_rest` | active | **CHOSEN.** The only active SPY 0DTE arm that is (a) not `safe-3` (excluded per explicit task instruction — see that row's own note for the prod-shadow-attribution correction), and (b) not on the `mcp_heartbeat` CORE production path (`safe-2`/`bold-2`). Its entry order is placed by `fleet_live.py:_place_live` -> `fb.marketable_limit_price`, the exact call site this A/B would branch. Caveat: risky-1 already carries its own live experiments (REACHABLE-TP1 exit_patch, full-send lane, ATM strike table) — this A/B is a confound layered on an already-non-control arm, disclosed not hidden. |
| safe-3 (`FLEET-TIGHT-S`) | `fleet_rest` | active | **EXCLUDED per explicit task instruction.** **Correction of record:** verified `setup/scripts/prod_shadow.py` (module docstring + `DEFAULT_BASE_ARM`) and its live output `analysis/prod-shadow/summary.json` (`generated_et: 2026-09-02T14:20:02`) — the prod-shadow instrument's `base_arm` is **safe-2 (CORE-SAFE, PA3POKNV46VG)**, not safe-3. The docstring is explicit: "safe-2 ... is the specific arm A2 identified as the live-eligible core candidate." This session's own memory note ("prod-shadow = safe-3", 2026-09-01 full audit) does not match the current code/output and is flagged here as stale/unreconciled, not treated as fact. safe-3 is excluded from this A/B anyway, on the standing instruction alone (independent of the prod-shadow label) — but the reason given to J should be "instructed exclusion," not a prod-shadow claim this document cannot verify. |
| safe-2 (`CORE-SAFE`), bold-2 (`CORE-BOLD`) | `mcp_heartbeat` | active | **EXCLUDED.** These are the CORE production-mirror accounts driven by the live heartbeat engine (`heartbeat_core.py`), not fleet lab arms — the grid's own doc calls them "the untouched safe/risky baseline the grid is measured against." Not the place for an unvalidated execution-mechanism experiment. |
| risky-3 (`FLEET-LOOSE-R`) | `fleet_rest` | **retired** 2026-08-28 | **EXCLUDED.** No longer a SPY arm — its account (`PA3V7JT25H6Z`) was repurposed to `weekly-1` (multi-underlying, non-SPY, `status: pending_build`). Re-arming it would collide with the weekly-1 wiring per its own `_retired_doc`. |

**Result: exactly one candidate arm, risky-1.** This is not a two-arm A/B across accounts —
it is TWIN-B3's own single-account, alternate-by-signal design, transplanted.

**Frozen per-fill metrics (mirrors `entry-quality.json`'s existing schema):**
1. `improvement_usd` / `improvement_bps` — passive fill price vs the **marketable mid at
   signal time** (not vs the marketable fill price, which is itself already paying the
   spread — mirrors the twin's `baseline_ask`/`baseline_bid` convention).
2. `time_to_fill_sec`.
3. `abandonment` — miss/cancel count and rate.
4. **The metric the twin cannot show — OPPORTUNITY COST of the abandoned (`policy=cancel`)
   entries:** for every `missed` passive entry, record (a) signal-to-eventual-fill slippage
   — the SPY/option price move between the original signal tick and whenever the position is
   actually established (immediately, since `policy=cancel` means no auto-fallback order is
   placed by `entry_manager` itself; this fires the SAME-TICK marketable fallback the fleet
   already runs, priced at the post-abandonment ask) and (b) the realized P&L of that
   fallback fill vs a same-signal control-cohort trade, so the 23.89%-abandonment prior isn't
   silently netted out of the headline number the way a naive "average improvement across
   fills only" would.

---

## 3. Frozen bars, verdict vocabulary, ship rule

**Frozen sample-size bars (BEFORE any data is read under this A/B):**
- `n_fills >= 60` per cohort (passive and marketable), **AND**
- `>= 20 trading days` elapsed since the A/B started on risky-1.
Both conditions required (matches the twin's own >=20-fill floor scaled up ~3x for the wider
SPY option spread/premium variance this document's §1 caveat flags, and matches the standing
`go_live_gate.py` convention of pairing a fill-count floor with a trading-day floor rather
than either alone).

**Verdict vocabulary (fixed, no new terms introduced mid-run):**
- `SHIP` — ship rule below is met.
- `WATCH` — bars not yet met; keep accruing, no verdict yet.
- `NO-SHIP` — bars met, ship rule fails (mean improvement CI-lower <= 0, or per-signal
  expectancy worse than control).
- `KILL` — any kill-switch or catastrophe-cap event with the passive/cancel-then-marketable
  path as a proximate cause (fail-open into the marketable fallback is the existing
  `entry_manager` design, so this should be structurally rare, but the verdict exists so a
  live breach is never absorbed into `NO-SHIP` language).

**Ship rule (both required):**
1. Mean `improvement_bps` (fills-only) 95% bootstrap CI-lower > 0, **net of abandonment
   cost** — i.e. computed over ALL attempts (fills at their improvement, abandons at their
   opportunity-cost slippage from §2.4), not fills-only. This is the one place this design
   deliberately diverges from the twin's own headline number, which reports fills-only
   improvement and abandonment rate as two separate stats rather than one blended figure —
   because the twin's marketable-control fill_rate is 1.0 (crypto never misses a marketable
   fill) while SPY illiquidity/gaps could make abandonment costlier here.
2. No worse expectancy per signal (passive-cohort $/signal, not $/fill, must not be
   statistically worse than the marketable-cohort $/signal on the same signal population).

---

## 4. Freeze / Rule-9

- **September config freeze (2026-08-31 -> ~2026-09-29, 20 scored trading days,
  `project_september_clean_window_plan_2026_08_29` memory / `FABLE-FULL-REVIEW-2026-08-29.md`):
  no trading-path changes on any actively-trading SPY arm except pre-registered kill-type risk
  reductions.** risky-1 IS actively trading (fleet_rest, status active) inside this window —
  it is not exempt from the freeze merely because it is paper. **Honest correction of the
  task's framing:** every currently-active SPY arm (safe-2, bold-2, safe-3, risky-1) is inside
  the frozen scoring window right now; none of them is "paper-only so it could start earlier"
  in the sense of dodging the freeze — paper-vs-live-money is a different axis from
  in-freeze-vs-not. The only arms outside the freeze (risky-3 retired, weekly-1
  pending_build/non-SPY, mes-* futures) are excluded from this A/B for the reasons in §2's
  table, not available as an early-start substitute.
- **Earliest actual wiring start: 2026-09-29** (the freeze checkpoint), on risky-1, once the
  September scoring window closes. This document itself (a frozen pre-registration, no code
  change) is freeze-compatible and can be written and filed now — writing a prereg is
  explicitly listed as freeze-compatible measurement/documentation work elsewhere in
  `queue.md` (e.g. the 2026-09-03 `BEAR-08-31-...-REPLAY` item's own framing: replay/report
  work proceeds now, a trigger-rule *change* waits for 10-30).
- **2026-10-30 remains the outer decision date** referenced by this session's briefing for
  any SPY-facing wiring decision generally (go-live-gate cadence / "10-30 decision" framing
  used elsewhere this session for trigger-rule changes) — this A/B's wiring is a narrower,
  execution-mechanism change on a paper lab arm, not a trigger-rule or live-money change, so
  it is gated by the nearer 09-29 freeze checkpoint above, not by 10-30 itself. If, after
  09-29, the wiring is not shipped before 10-30 for any reason, treat 10-30 as the hard
  outer bound consistent with the rest of the session's SPY-wiring framing.

---

## 5. Build step (structured, for whoever executes this after 09-29)

```yaml
build_step:
  file: automation/state/fleet/fleet_live.py
  symbol: _place_live
  must_contain: entry_manager.plan_entry_action
```

Concretely: `_place_live` (currently `fleet_live.py:495-...`, entry pricing at line 553 via
`fb.marketable_limit_price`) branches on the qualifying signal id's parity. Even -> unchanged
(`fb.marketable_limit_price`, byte-identical control). Odd -> construct
`entry_manager.EntryState.from_signal(..., delta=0.10, patience_ticks=3, policy="cancel")`,
drive `entry_manager.plan_entry_action` tick-wise against live quotes (mirrors
`setup/scripts/crypto_twin_entry_quality.py`'s actuator shape for the twin), journal every
attempt to a new `automation/state/fleet/risky-1/entry-quality.json` (own file, same schema
as the twin's, never shared/merged with `automation/state/crypto-twin/entry-quality.json` —
crypto-twin non-comparability doctrine applies here exactly as it does to weekly-1). Fail-open
identical to the twin: any passive-path exception falls back to the existing marketable path
so a bug in the new code can never block an entry outright.

## 6. Revert

One line, byte-identical: remove the parity branch in `_place_live` (or set a kill flag
analogous to `crypto_twin_core`'s pattern) so every entry resolves through
`fb.marketable_limit_price` again, exactly as today. No other file requires changes — this
document, `entry_manager.py`, and `entry-quality.json`-shaped output are purely additive.
