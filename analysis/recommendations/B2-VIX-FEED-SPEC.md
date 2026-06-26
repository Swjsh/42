# B2 — VIX intraday feed spec (edge #4 `vix_regime_dayside`) — PINNED

**Status:** `VIX_FEED_PINNED` — reconstruction reproduces the scorecard EXACTLY (0 diff).
**Run date:** 2026-06-21 · **Harness:** `backtest/autoresearch/_b2_vix_feed_parity.py` · $0, markets closed.
**Machine output:** `analysis/recommendations/B2-vix-feed-parity.json`
**Scorecard under test:** `analysis/recommendations/b5-vix-regime-dayside.json`

---

## What this resolves

Edge #4 has TWO blockers to going live. This is the SECOND, independent of WP-0:

> The regime classifier needs an **intraday VIX series** (trailing-median-78 + 5-bar causal
> slope). The live `BarContext` only carries `vix_now` / `vix_prior` — no VIX history. So the
> watcher reads an OPTIONAL `ctx.vix_intraday`; absent it, `favorable_regime()` returns `None`
> → SKIP (fail-open). Today that seam is **never fed**, so edge #4 is inert even if the flag
> flips. This task reconstructs the feed offline and PINS the exact spec the heartbeat must
> thread into `ctx.vix_intraday` so the LIVE watcher makes the SAME decision the scorecard did.

## Verdict — VIX_FEED_PINNED

The reconstructed feed, run through the **live watcher's pure core**
(`detect_vix_regime_dayside_core`), reproduces the **research detector**
(`_b5_vix_regime_dayside.detect_opt_signals`) that produced the scorecard with **zero
divergence** across all 8 swept cells.

| slope_rule | low_margin | research n | watcher n | intersect | onlyR | onlyW | jaccard |
|---|---|---|---|---|---|---|---|
| not_rising | 0.00 | 111 | 111 | 111 | 0 | 0 | 1.000 |
| **not_rising** | **0.25** | **84** | **84** | **84** | **0** | **0** | **1.000** |
| not_rising | 0.50 | 58 | 58 | 58 | 0 | 0 | 1.000 |
| not_rising | 1.00 | 34 | 34 | 34 | 0 | 0 | 1.000 |
| any | 0.00 | 111 | 111 | 111 | 0 | 0 | 1.000 |
| any | 0.25 | 84 | 84 | 84 | 0 | 0 | 1.000 |
| any | 0.50 | 58 | 58 | 58 | 0 | 0 | 1.000 |
| any | 1.00 | 34 | 34 | 34 | 0 | 0 | 1.000 |

*(window 2025-01-02..2026-05-29, hard-windowed to the OPRA cache last day)*

- **Primitive parity:** `causal_vix_median` and `vix_slope` in the watcher are **byte-identical**
  (`np.allclose atol=1e-9`) to the research versions on the same array. No detector drift (C14).
- **Scorecard n_signals reproduced EXACTLY** on the original 05-15 window the scorecard used
  (104 / 80 / 55 / 37 per cell — every cell `OK`). The validated cell = **80 signals @ 05-15**,
  growing to **84 @ 05-29** as the window extends; the live core matches the research core on
  the extended window too (84 = 84).
- **Last signal date = 2026-05-29** (== OPRA cache last day; no signal silently beyond the
  real-fills coverage edge — the C-DATA blind-spot guard holds).

No parity bug. The feed is safe to wire.

---

## THE PINNED SPEC — what the live heartbeat MUST reproduce in `ctx.vix_intraday`

The heartbeat must build `ctx.vix_intraday` so that, sliced and fed through the watcher's
`causal_vix_median(78)` / `vix_slope(5)`, the per-bar regime arrays equal what the offline
reconstruction produces. Concretely:

1. **Source** — CBOE `^VIX` **5-minute RTH closes** (the same series cached in
   `backtest/data/vix_5m_*.csv`). Use the **close** column, not open/high/low.

2. **Alignment to the SPY 5m grid** (`_align_vix`, byte-for-byte):
   - SPY bar timestamps → `tz America/New_York` → convert to **UTC**.
   - VIX timestamps parsed `utc=True`.
   - Build a VIX `close` Series indexed by UTC, **dedupe** (`~index.duplicated(keep='first')`).
   - `reindex` onto the SPY UTC index with **`method='ffill'`** (carry the last VIX print
     forward across the 5m SPY grid — VIX and SPY 5m grids are not always identical).
   - `fillna(0.0)` is the ONLY backstop and only bites in deep pre-history warmup; it must
     **never** fire inside the 09:35–11:30 ET window on a real session (verified — no 0.0 VIX
     in any fired cell).

3. **Trailing median** — `pandas.rolling(78, min_periods=max(5, 78//4)=19).median().shift(1)`.
   - `78` ≈ one RTH day of 5m bars. **`shift(1)`** is load-bearing: a bar never sets its own
     baseline (C6 causality).

4. **5-bar slope** — `vix[i] - vix[i-5]` (the ML #2 feature). Causal; `NaN` for `i < 5`.

5. **Timezone for the entry window** — the 09:35–11:30 **ET** morning gate is evaluated in
   **America/New_York**, NOT UTC (L165 / L61). The VIX *alignment* round-trips through UTC, but
   the time-of-day gate is ET.

6. **Causality / as-of** — every VIX input (level, median, slope) is read at-or-before the
   **just-closed** candidate bar; entry fills the **NEXT** bar open. The median's `shift(1)`
   plus the slope's pure backward difference make the whole regime a function of bars `<=` the
   current bar only.

7. **The `ctx.vix_intraday` seam contract** — a `list` / `np.ndarray` of 5m VIX closes aligned
   to `ctx.prior_bars` (**newest last**), carrying **>= 78 prior bars** of history so the
   median/slope have their warmup. The watcher computes the causal regime over the FULL series
   then **tail-slices** to today's RTH frame (`vix_full[-n_rth:]`). Feeding fewer than
   `n_rth` values → the wrapper returns `None` (SKIP, never guess).

### Validated LIVE cell (the only one to wire)

| param | value |
|---|---|
| `low_margin` | **0.25** (VIX `<=` trailing_median − 0.25) |
| `slope_rule` | **not_rising** (`vix_slope5 <= 0`) |
| `strike_offset` | **0** (ATM — Safe-2 ship cell, C29) |
| `premium_stop_pct` | **−0.08** (isolated key `j_vix_dayside_premium_stop_pct`) |
| tier | **ATM_safe2** (ITM-2 at the same cell is a truncation artifact — NOT shipped) |
| live flag | `params.j_vix_dayside_enabled` (default FALSE — DORMANT until J + 3 confirmations) |

---

## Wiring note (for the heartbeat author — out of scope for this task, markets closed)

The heartbeat already reads `vix_now` from the TV/Alpaca VIX feed each tick. To feed
`ctx.vix_intraday` it must additionally retain the **today-session 5m VIX close history**
(plus >= 78 bars of prior-day tail for warmup) as a rolling buffer, aligned to `ctx.prior_bars`,
and set it on the context with `object.__setattr__(ctx, "vix_intraday", arr)` (BarContext is
frozen). With that single seam fed, edge #4 makes the exact decision validated here — no other
detector change required. This is a pure wiring change; the math is PINNED and parity-proven.

## Reproduce

```
backtest/.venv/Scripts/python.exe backtest/autoresearch/_b2_vix_feed_parity.py
# -> analysis/recommendations/B2-vix-feed-parity.json  (verdict VIX_FEED_PINNED, exit 0)
```
