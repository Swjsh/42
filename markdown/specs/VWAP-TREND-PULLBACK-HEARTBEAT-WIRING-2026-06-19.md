# VWAP_TREND_PULLBACK — heartbeat wiring proposal (PROPOSE-ONLY, Rule 9)

**Status: PROPOSE-AND-PING-J.** This is the EXACT heartbeat.md addition that makes the
live engine TRADE the H4 VWAP trend-day pullback. It is **not applied** — it touches live
prose (Rule 9). Per OP-16/OP-22 it is *ready to ship after-hours* because the ship bar is met:
OOS positive AND walk-forward ≥ 0.70 AND sub-window stable AND A/B scorecard filed. **J's role
= REVOKE**, not approve.

- **Scorecard (filed):** [`analysis/recommendations/vwap-trend-pullback-LIVE.json`](../analysis/recommendations/vwap-trend-pullback-LIVE.json)
- **Live detector (BUILT, parity-verified, gym-green):** [`backtest/lib/watchers/vwap_trend_pullback_watcher.py`](../backtest/lib/watchers/vwap_trend_pullback_watcher.py)
- **Parity test:** `backtest/tests/test_vwap_trend_pullback_watcher.py::test_parity_with_batch_detector`
- **Ratify harness:** `backtest/autoresearch/vwap_pullback_ratify.py`

## Why this is the path to profit

The edge is genuinely +EV on real OPRA fills, OOS-stable, causal, and DSR PASS — and it was
**trading nothing** because no live code fired it. The observation half is now wired (the
watcher is registered, so the unified WATCH_ONLY layer already logs it). This proposal wires
the **execution** half: one new named entry branch.

| Metric (ATM, real fills, n=92) | Value |
|---|---|
| Expectancy / trade | **+$45.88** (ITM1 +$63.31) |
| Win rate | 42.4% |
| Total P&L (17 mo) | +$4,221 |
| OOS exp/trade | **+$69.22** (OOS > IS) |
| OOS sign-stable | ✅ True |
| Walk-forward median | **1.679** (gate ≥ 0.70) |
| Sub-window hurt | 1/4 (gate ≤ 1) |
| DSR | PASS |
| drop-top-5 mean | +$25.43 (broad-based, not lottery) |
| Both directions + | ✅ C +$51.79 / P +$37.49 |
| Causality (future-poison) | **PASS** (no look-ahead) |

**HONEST caveat (load-bearing):** the WF series is **bimodal** — 4 negative OOS months
(2025-07..2025-10) then **7 consecutive positive** (2025-11..2026-05). The recent run + median
WF clear the gate, but the edge is **regime-sensitive** and bled in 2025 mid-year. Ship at
**BASE size only**; do NOT scale on the recent streak. Strikes are proxy (nearest-cached, L58),
not real ★★★ levels; n=92 over 17 months is **modest**. This is a SHIP with a watch, not a
slam-dunk.

---

## THE EXACT ADDITION

Insert a new setup branch parallel to the BEARISH / BULLISH branches. Three pieces:

### Piece 1 — add to the candidate setup list (heartbeat.md "Scoring" preamble, ~line 313)

> Current text: *"For each candidate setup (BEARISH_REJECTION_RIDE_THE_RIBBON or
> BULLISH_RECLAIM_RIDE_THE_RIBBON):"*

Change to add the third setup, and its independent first-entry lock key (the isolation
guarantee at line 315 already anticipates `VWAP_TREND_PULLBACK` as a future key — it is
explicitly listed there):

```
For each candidate setup (BEARISH_REJECTION_RIDE_THE_RIBBON, BULLISH_RECLAIM_RIDE_THE_RIBBON,
or VWAP_TREND_PULLBACK):
```

### Piece 2 — the new scoring + entry branch (new section after the BULLISH branch)

```markdown
**VWAP_TREND_PULLBACK (H4 — data-discovered, WATCH→LIVE 2026-06-19) — score against the LAST CLOSED 5m bar.**

> Source of truth for the structure: backtest/lib/watchers/vwap_trend_pullback_watcher.py
> (detect_vwap_trend_pullback_setup). The live watcher fleet (Gamma_WatcherLive) already
> computes this signal every 5 min and writes it to watcher-observations.jsonl with
> setup_name="VWAP_TREND_PULLBACK". This branch PROMOTES that observation to an order when
> the structural gates pass. Scorecard: analysis/recommendations/vwap-trend-pullback-LIVE.json.
> Ratified per OP-16/OP-22 (OOS+, WF 1.679, sub-window stable, causality PASS, DSR PASS).

Read the freshest VWAP_TREND_PULLBACK row from watcher-observations.jsonl for THIS account
(apply the same schema-guard + date-match + freshness ≤10 min filters as the WATCH-ONLY layer).
If no fresh row, this setup does not fire this tick.

ENTRY CONDITIONS (all must hold — they ARE the detector's gates, restated for the live read):
1. **time IN [09:35 ET, 15:00 ET)** — continuous entry window; theta kills after 15:00. Honor
   the same 11:30–12:00 ET no-trade window as BEARISH (`entry_no_trade_window_et`).
2. **news clear** — not inside `today-bias.news_calendar.no_trade_window[]`.
3. **budget > risk** AND **day-trades ≥ 1** (PDT-aware, same as other setups).
4. **trend established (the watcher's first gate):** the first 6 RTH bars all closed on the
   SAME side of the as-of session VWAP (uptrend → calls, downtrend → puts). The watcher row's
   `direction` carries this; trust it (it is causal + parity-tested).
5. **fresh VWAP tag in-trend (the watcher's trigger):** the row's `triggers_fired` includes
   `vwap_pullback_tag` and the row is ≤ 10 min old (this IS the entry bar). One entry/day —
   the detector enforces one signal/day; the first-entry lock (Piece 1) enforces no re-entry.
6. **direction ↔ regime sanity:** calls only when ribbon stack is not BEAR; puts only when not
   BULL (a light corroboration — the trend-day structure is the primary signal, ribbon is a veto
   not a driver). If ribbon contradicts, `SKIP_VWAP_RIBBON_CONTRA`.

STRIKE: per the v15 per-tier table (OTM-3 at $1K / OTM-2 at $2–10K / OTM-1 at $10–25K / ITM-2
at $25K+). The edge was validated ATM and ITM1; map to the account tier at execution (same
strike logic as the other setups — do NOT hardcode).

SIZING: **min-3 floor + per-trade premium ceiling ~6% of equity** (markdown/research/SIZING-STUDY-2026-06-19.md).
BASE tier qty (this is a WATCH→LIVE setup; no ELITE upsize until a live archive accrues). The
post-loss throttle (if/when wired) applies normally.

STOP: **chart/structural ONLY** (premium stop DISABLED, per L51/L55/C2 — first-strike level
entries get violent initial counter-moves that blow premium stops). The chart stop is the
session extreme against the trade as of the entry bar:
  - uptrend (calls): session MIN low to date — from the watcher row's `stop_price`.
  - downtrend (puts): session MAX high to date — from the watcher row's `stop_price`.
In the live order, apply the standard $0.50 LEVEL_STOP_BUFFER beyond `stop_price` (same buffer
the simulator and other watcher-sourced entries use) so the live chart stop matches simulation.

EXIT STACK (v15, UNCHANGED): TP1 at +30% premium fallback OR the next chart level past entry;
move runner to break-even after TP1; chandelier profit-lock (arms +5% favor, trails 20% off HWM);
15:50 ET hard time stop. tp1_qty_fraction 0.50, runner target 2.5×.

If all conditions pass and the pre-execution gate sequence (G5/G7/G1/...) is clear, this is the
tick's ONE action: emit `ENTER_BULL` (calls) or `ENTER_BEAR` (puts), place the atomic bracket
via `place_option_order`, and journal the entry thesis BEFORE the order (Rule 8). Log
`setup_name: "VWAP_TREND_PULLBACK"` on the decisions.jsonl + current-position rows.
```

### Piece 3 — first-entry-lock key registration

No code change needed: line 315 of heartbeat.md already names `VWAP_TREND_PULLBACK`-class setups
as carrying their own independent lock key. The lock filter (line 317–320) keys strictly on
`setup_name`, so a VWAP_TREND_PULLBACK stop-out blocks only VWAP_TREND_PULLBACK re-entry, never
BEARISH/BULLISH (and vice-versa). ✅ already structured.

---

## Conflict / interaction notes (proactive second-order review)

- **One-action-per-tick budget:** the branch competes with BEARISH/BULLISH for the single
  per-tick action. Recommended priority: keep BEARISH_REJECTION first (J's proven #1 edge), then
  BULLISH_RECLAIM, then VWAP_TREND_PULLBACK. A trend-day VWAP tag and a fresh ribbon-flip
  rejection rarely co-fire (different bar structure), but if they do, the J-anchored setup wins.
- **No mid-session change (Rule 9):** ship this in an after-hours window, never 09:30–15:55 ET.
- **Dual-account symmetry (C9/L42/L49):** add the identical branch to BOTH
  `automation/prompts/heartbeat.md` (safe) and the aggressive heartbeat. Use `gamma-sync` to keep
  them aligned, and run the pytest suite after.
- **Revert path:** delete the VWAP_TREND_PULLBACK branch (Piece 2) and drop it from the candidate
  list (Piece 1). The watcher stays registered and reverts to pure WATCH_ONLY observation — no
  order path. Zero residue.
- **Cost:** ~0. One extra watcher-row read per tick (already on disk). No new MCP/Python/chart calls.

## Go-live checklist (for the after-hours apply step)

1. Apply Pieces 1+2 to BOTH heartbeats (gamma-sync).
2. Confirm `params.json` strike/sizing/exit knobs already cover the new setup (they are
   setup-agnostic — no new keys required; the chart-stop-only posture uses the existing
   premium-stop-disable convention).
3. Run `pytest backtest/tests/ -q` + `crypto.validators.runner --skip-replay` → green.
4. Premarket next session: confirm the watcher feed shows VWAP_TREND_PULLBACK rows logging
   WATCH_ONLY (already happening once the registration ships).
5. Flip to execution. Monitor the live archive; promote to ELITE sizing only after ≥ 20 live
   trades + WR ≥ 45% + positive expectancy (the standard per-account live threshold).
```
