# OPUS WORKPACKAGE — finish the multi-symbol lane (2026-08-20, authored by Fable)

> **For the executing worker.** Audit behind this plan:
> `analysis/deep-research/MULTI-LANE-FIDELITY-AUDIT-2026-08-20.md` — read it first. One-line
> diagnosis: *the fork is faithful code in an unfaithful world; we copied the brain and forgot
> the eyes.* Your job is the eyes.
>
> **Standing rules that bind every WP:** shadow/paper only; the no-order-path AST guard on
> `multi/core.py` must stay green; never import or modify the SPY engine; never blend this
> lane's evidence with SPY's or the crypto twin's; every new param gets vary-and-assert; every
> guard gets RED-proofed (break it, quote the failure, restore); fail loud — and specifically,
> **never let an exception path and an empty-result path converge on one symptom** (that
> exact class cost this lane a full trading day — see
> `_lesson-inbox/api-error-masqueraded-as-market-condition-2026-08-20.md`).
> ET via zoneinfo; the box runs Mountain time. Commit via `setup/scripts/commit_scoped.py`.

---

## WP-0 — IDENTITY: make it the intraday machine (decision already made — encode it)

**Why first:** every later WP depends on which business this lane is in. J's directive is
explicit: replicate the engine with recent green evidence — the **intraday** SPY machine — on
more names. The multi-day model the lane currently carries was inherited from the weekly lane,
whose signal died a five-cut null-gate death. Multi-day is not "killed forever"; it is
**deprioritized until the intraday replication has evidence**.

**Do:**
1. `automation/state/multi/params.json`: add a top-level `"mode": "intraday_v1"` block —
   same-day exits (time-stop 15:50 ET analogue), expiry = nearest listed (0–3 DTE acceptable,
   from the LIVE chain as already built), overnight/weekend holds forbidden in v1. Keep the
   multi-day fields under a clearly-labeled `"_dormant_multiday"` block rather than deleting —
   provenance, and cheap to revive with evidence.
2. `multi/lib/exits.py`: honor the mode — in intraday mode the expiry-flatten schedule and a
   same-day time-stop apply; days-to-live/weekend logic dormant.
3. Update program doc §9a status line + one CHANGELOG entry.

**Acceptance:** params vary-and-assert proves the mode knob changes exit behavior; tests green;
docs updated. **Guard:** a test that intraday mode NEVER produces an overnight-hold decision.

## WP-1 — TIMEBASE + CADENCE: 5-minute bars, minute-class evaluation on the watchlist

**Why:** production evaluates ~78 closed 5m bars/day/symbol; the lane evaluates ~6.5 1H bars.
This alone predicts a near-zero entry rate regardless of edge.

**Do:**
1. `fetch_bars` → support `5Min` (and `15Min` for the HTF stack). **Use the BATCH endpoint**
   `GET /v2/stocks/bars?symbols=A,B,C` — one request for the whole watchlist, not per-symbol
   loops. Both known Alpaca traps are already encoded (explicit `start`; pagination); keep them.
2. Two-tier cadence, honoring the funnel: **funnel refresh every 15 min over 72 names (cheap:
   batch daily/hourly bars + scanners); scoring tick every 5 min over the ≤5 watchlist** on 5m
   bars. Rearm `Gamma_MultiCore` accordingly (or a sibling task `Gamma_MultiScore5m`) — keep the
   09:35 start, `MultipleInstances IgnoreNew`, and the verify-block pattern of
   `install-multi-core.ps1`.
3. Rate-limit arithmetic goes IN THE COMMIT MESSAGE: watchlist tick = 1 batch bars call + ≤5
   chain/quote calls every 5 min ≈ well inside 200/min. Show the numbers.

**Acceptance:** a live RTH tick evaluates 5m bars for the watchlist (ledger rows carry
`timeframe: "5Min"` + the trigger bar's ET timestamp); cascade shows evaluable-bar counts per
day within 10% of production's ~78. **Guard:** closed-bar test at 5m granularity (a bar whose
close time is in the future must be dropped — C6).

## WP-2 — CONTEXT PARITY: feed the fork what production eats

**Why:** `vix_*`, `htf_15m_bars`, `level_states`, `fhh_level` are all None today. The filters
were designed against these inputs; without them the fork is a different strategy wearing the
same code.

**Do:**
1. **VIX**: fetch independently (Alpaca `get_index_values`/`^VIX`, or the existing free path the
   sight-beacon uses — read `setup/scripts/sight_beacon.py` for the precedent; do NOT read the
   SPY lane's state files — separation). Compute 5d/20d MAs from daily VIX closes. Cache in
   `automation/state/multi/vix.json` with freshness stamps; STALE > 20 min during RTH = pass
   None AND write a `context_degraded` cascade count (degraded ≠ silent).
2. **HTF stack**: 15m bars for watchlist names via the same batch fetch; wire
   `htf_15m_bars=` through `build_signal`.
3. **Level states**: port the SPY engine's LevelState reclaim/reject mechanics (read
   `build_shared_signal.py`'s handling; fork, never import) into a per-symbol
   `automation/state/multi/level-states-{SYM}.json`, updated each tick from 5m closes against
   the levels `multi/lib/levels.py` already computes. This is the memory J's philosophy runs on
   ("wait for the RETURN to the zone").
4. **Input-parity checklist test**: a structural test asserting `build_signal` is called with
   every input production supplies (no silent Nones for vix/htf/level_states). RED-proof by
   removing one kwarg.

**Acceptance:** ledger rows show non-None vix/htf fields during RTH; `context_degraded` visible
when a feed is stale. **Kill condition for the WP:** if VIX genuinely cannot be fetched free,
say so in STATUS and ship with `vix_regime` logged-degraded — do NOT fake a value.

## WP-3 — BLOCKER VISIBILITY: make "why did it HOLD" a one-read answer

**Why:** today's 178 HOLDs are opaque; scores are logged but blockers are not. Diagnosis
required manual probes. This is the participation cascade's missing bottom half.

**Do:** stamp `bear_blockers` / `bull_blockers` / `bear_triggers` / `bull_triggers` (names, not
just numbers — map F5=ribbon_stack, F6=ribbon_spread, F7=vol_divergence, F9=breakdown_bar,
F10=level_tied_trigger, F11=sweep/htf) onto every HOLD row; nightly rollup
`analysis/multi-lane/blocker-histogram-{date}.json` + a line in `multi_status.py` ("top blocker
today: F10 level_tied_trigger, 61%"). **Acceptance:** the histogram exists after one RTH day and
`multi_status.py` prints it. **Guard:** a HOLD row without a blockers field fails a test.

## WP-4 — THE EVIDENCE GATE: intraday null harness BEFORE any paper order

**Why:** the lane has zero evidence its scoring pays on non-SPY names. The weekly lane's
harness (paired walk + random-entry-null at MAX) exists and is parameterized — adapt, don't
rebuild. This is the gate that killed the weekly signal honestly; nothing ships around it.

**Do:**
1. Ingest **intraday (1–5 min) option bars** for 3–5 TIER1 names (NVDA, QQQ, GLD to start) via
   the existing `fetch_weekly_option_data.py` patterns (OI-screened; coverage is volume-gated —
   disclose per-arm completeness, never one global %).
2. Replay the WP-1/WP-2 signal over 60–90 days of 5m underlying bars (no look-ahead: the
   strict-slicing pattern from `weekly_signal_density_probe.py`), walk fills through real
   intraday option bars with the 5% pessimistic spread model where quotes are absent, adverse-
   first resolution on ambiguous bars.
3. Run the **random-entry null at its MAX** on the same population. Pre-register the decision
   rule BEFORE looking (copy the frozen-prereg pattern, `analysis/recommendations/prereg-multi-
   intraday-<date>.json`): ship-to-paper requires beating the null MAX; a null result is
   shippable as "the fork does not transfer" and stops the lane cleanly.

**Acceptance:** prereg frozen before results; report with per-arm data-completeness disclosure;
verdict stated in one line at the top. **This WP gates WP-5 absolutely.**

## WP-5 — PAPER ORDERS (only if WP-4 passes)

Wire the tick's WOULD_PLACE through `broker.place_bracket(armed=True)` behind a NEW explicit
`params.mode_armed_paper: true` that a human sets — the AST no-order-path guard on `core.py`
moves to a dispatcher module so the guard itself stays meaningful. Journal via
`multi/lib/journal.py` (entry/exit rows, trade_id). First day at min size, 1 concurrent
position. **Acceptance:** first real paper fill journaled end-to-end with exit. **Never**
`live: true` — that is J's alone (OP-0 #1).

## WP-6 — HYGIENE (parallel, small)

- OI is None on the indicative feed → `min_open_interest` can never bind. Replace with a
  `min_contract_volume_today` gate (volume IS present) and delete or explicitly mark the OI
  knob dormant. C14: no knob that cannot bind.
- `multi_status.py`: add blocker-histogram line (WP-3) + mode banner (WP-0).
- Nightly: fold a one-line multi-lane summary into the existing EOD surfaces.

---

## Order and dependencies

WP-0 → WP-1 → WP-2 → (WP-3 ∥ WP-6) → one clean RTH shadow day with full context → WP-4 → WP-5.

**Definition of done for the program:** either (a) WP-4 passes and WP-5 journals real paper
round-trips, or (b) WP-4 returns null and the lane is stopped with the verdict written — both
are completed outcomes. What is NOT a completed outcome is a lane that ticks forever in a
starved context producing HOLDs nobody can interpret. That is where it stands tonight; these
six WPs are the distance between that and an answer.
