# TV Indicator-Parity Oracle — Saty Pivot Ribbon vs backtest lib.ribbon

**Run:** 2026-07-22 ~20:20-20:45 ET (after-hours, no heartbeat contention) · Bar Replay on BATS:SPY 5-min, chart `4HTVHI0m`
**Days:** 2026-07-17, 2026-07-21, 2026-07-22 · 9 checkpoints/day × 3 days = 27 checkpoints, 5 EMAs each
**Engine side:** `backtest/lib/ribbon.py::compute_ribbon` (13/20/48, SMA-seeded) + conviction EMAs (13/51) from `backtest/lib/ribbon_config.json`, computed over the **RTH-only** close series of `backtest/data/spy_5m_2026-05-19_2026-07-22.csv` — the exact scope `heartbeat_core._build_payload` / `setup/scripts/dojo/engine_step.py` feed it (RTH-filter first, ribbon over the whole frame).
**TV side:** `data_get_study_values` at the replay cursor (TV renders 2dp; ±$0.005 rounding floor).
**Tolerance:** |diff| > $0.05 = DRIFT · > $0.25 = CRITICAL.

## VERDICT: **CRITICAL** — session-scope mismatch, not broken math

**Root cause (one sentence):** J's TV chart computes its EMAs over **extended-hours bars** (premarket 04:00 + after-hours to 20:00 — confirmed live: 19:55 ET bars on chart), while the engine/backtest ribbon is **RTH-only**, so every overnight/premarket move creates a divergence that is largest at the open (**up to $6.40** on the gap-down 07-17) and persists in the 48/51 EMAs into the afternoon.

Three separate parities were measured; only the last one fails:

| Layer | Result | Worst |diff| |
|---|---|---|
| **Bar data** (cache close vs TV close, same bar) | ✅ PARITY_OK | $0.040 (median ~$0.01) — SIP cache vs BATS-only feed |
| **EMA math at matched series scope** (cache incl. premarket vs TV render) | ✅ ~OK (residual explained below) | $0.383 |
| **Engine ribbon vs what J's chart renders** (RTH-only vs ETH chart) | 🚨 **CRITICAL** | **$6.403** (07-17 09:30, Slow EMA) |

24/27 checkpoints have at least one EMA beyond the $0.25 CRITICAL line on the engine-vs-render comparison. Only 07-22 14:00/14:45/15:30 were DRIFT-or-better.

## Checkpoint table — engine (RTH-only, live scope) vs TV render

diff = ours − TV, in $. F/P/S = Fast(13)/Pivot(20)/Slow(48); FC/SC = conviction (13/51 per fingerprint config). `dC` = cache close − TV close (data-layer check).

| Date | Bar (ET) | dC | dF | dP | dS | dFC | dSC | Flag |
|---|---|---|---|---|---|---|---|---|
| 07-17 | 09:30 | −0.017 | +5.541 | +5.398 | +6.403 | +5.141 | +6.120 | 🚨 CRITICAL |
| 07-17 | 10:15 | −0.040 | +1.208 | +2.561 | +4.569 | +1.698 | +4.485 | 🚨 CRITICAL |
| 07-17 | 11:00 | −0.030 | −0.030 | +0.875 | +2.869 | +0.160 | +3.035 | 🚨 CRITICAL |
| 07-17 | 11:45 | +0.000 | +0.098 | +0.448 | +2.001 | +0.148 | +2.180 | 🚨 CRITICAL |
| 07-17 | 12:30 | −0.020 | −0.107 | +0.173 | +1.269 | −0.007 | +1.509 | 🚨 CRITICAL |
| 07-17 | 13:15 | −0.020 | −0.164 | +0.102 | +0.767 | −0.004 | +1.052 | 🚨 CRITICAL |
| 07-17 | 14:00 | +0.008 | +0.072 | −0.090 | +0.480 | −0.158 | +0.687 | 🚨 CRITICAL |
| 07-17 | 14:45 | −0.010 | +0.330 | −0.099 | +0.513 | −0.050 | +0.485 | 🚨 CRITICAL |
| 07-17 | 15:30 | +0.010 | +0.230 | −0.112 | +0.494 | −0.060 | +0.343 | 🚨 CRITICAL |
| 07-21 | 09:30 | +0.000 | −2.331 | −2.112 | −1.491 | −2.231 | −1.357 | 🚨 CRITICAL |
| 07-21 | 10:15 | +0.020 | −0.504 | −0.804 | −0.998 | −0.464 | −0.933 | 🚨 CRITICAL |
| 07-21 | 11:00 | −0.028 | −0.410 | −0.331 | −0.817 | −0.180 | −0.681 | 🚨 CRITICAL |
| 07-21 | 11:45 | −0.009 | −0.200 | −0.014 | −0.671 | +0.050 | −0.458 | 🚨 CRITICAL |
| 07-21 | 12:30 | −0.005 | −0.160 | +0.078 | −0.606 | +0.090 | −0.325 | 🚨 CRITICAL |
| 07-21 | 13:15 | +0.005 | −0.139 | +0.017 | −0.577 | −0.019 | −0.263 | 🚨 CRITICAL |
| 07-21 | 14:00 | +0.000 | −0.084 | +0.002 | −0.472 | −0.034 | −0.203 | 🚨 CRITICAL |
| 07-21 | 14:45 | −0.010 | +0.052 | +0.013 | −0.333 | +0.012 | −0.150 | 🚨 CRITICAL |
| 07-21 | 15:30 | +0.010 | −0.003 | −0.009 | −0.251 | −0.013 | −0.115 | 🚨 CRITICAL (S only, borderline) |
| 07-22 | 09:30 | −0.040 | +2.071 | +2.250 | +1.957 | +2.181 | +1.782 | 🚨 CRITICAL |
| 07-22 | 10:15 | +0.010 | +0.157 | +0.986 | +1.153 | +0.567 | +1.248 | 🚨 CRITICAL |
| 07-22 | 11:00 | −0.005 | +0.219 | +0.456 | +0.760 | +0.239 | +0.884 | 🚨 CRITICAL |
| 07-22 | 11:45 | +0.000 | −0.099 | +0.274 | +0.380 | +0.131 | +0.621 | 🚨 CRITICAL |
| 07-22 | 12:30 | +0.000 | −0.145 | +0.173 | +0.093 | +0.075 | +0.419 | 🚨 CRITICAL (SC) |
| 07-22 | 13:15 | +0.000 | −0.054 | +0.031 | −0.057 | −0.044 | +0.250 | ⚠️ DRIFT (SC at line) |
| 07-22 | 14:00 | −0.020 | +0.034 | −0.069 | −0.059 | −0.106 | +0.143 | ⚠️ DRIFT |
| 07-22 | 14:45 | −0.008 | +0.078 | −0.052 | +0.016 | −0.042 | +0.097 | ⚠️ DRIFT |
| 07-22 | 15:30 | +0.010 | +0.026 | −0.077 | +0.057 | −0.074 | +0.061 | ⚠️ DRIFT |

Raw TV reads (close + 5 EMAs per checkpoint) are embedded in the compute script:
`scratchpad/tv_parity_compute.py` (session temp) — full stdout preserved in this fire's transcript.

## Attribution run — same cache, premarket bars INCLUDED

Recomputing the identical EMAs over the cache's **all-session** series (04:00–15:55; the cache carries premarket but **no after-hours 16:00–20:00 bars**) collapses the divergence by ~94%:

- Worst |diff| vs TV: **$0.383** (07-17 10:15 Slow) — vs $6.403 RTH-only.
- Typical |diff|: $0.01–$0.17. Remaining >$0.25 outliers cluster on Slow(48)/Fast(13) around volatile opens.
- Residual is explained by: (a) cache lacks the after-hours bars TV's EMAs also chew (46–48 bars/day missing), (b) TV renders 2dp (±$0.005), (c) BATS-only vs SIP close deltas (≤$0.04/bar, compounding in a 48-EMA).

**Conclusion on the math itself:** `lib/ribbon.py`'s SMA-seeded `ta.ema` replication is sound — fed a series matching TV's scope it lands within ~$0.1–0.4 even without the after-hours bars. The $6 gap is *scope*, not arithmetic.

## What this means (and does NOT mean)

1. **Backtest ↔ live engine parity is NOT in question.** Both sides use the same `lib/ribbon.py` on the same RTH-only scope (heartbeat_core imports the exact backtest ribbon). Self-consistent.
2. **Engine ↔ J's-chart parity FAILS in the first ~90 minutes after any overnight gap.** On 07-17 (gap down) and 07-22 (gap up), the ribbon J sees on TV at the open is dollars away from the engine's internal ribbon; stack/flip states can disagree (values straddle each other differently — e.g. 07-22 09:30 both come out MIXED, but that is luck of the geometry, not guaranteed).
3. **Dojo implication (the reason this oracle exists):** in replay training, J directing from the TV chart and Agent A computing the engine view are looking at **different ribbons in the morning session**. Any "engine disagreed with the chart" note taken before ~13:00 on a gap day must be read with this offset in mind.
4. **The 2026-05-07 fingerprint claim** ("matches TV within ~0.05") in `ribbon.py`/`ribbon_config.json` was captured at a single 09:30 timestamp and does not hold against the live ETH-chart render under gap conditions — the claim is true only at matched series scope.
5. **Conviction EMAs:** TV's Fast Conviction plot ≠ TV's Fast EMA plot (same fingerprinted period 13) at most checkpoints — TV's conviction series is NOT (13, close, chart-TF); the 13/51 fingerprint is an approximation (tracked TV within ±0.34 at matched scope). Nothing in the engine's gates consumes conviction EMAs today (`compute_ribbon` outputs fast/pivot/slow only), so stakes are low, but do not treat `fast_conviction_ema`/`slow_conviction_ema` as certified.

## Recommended follow-ups (not executed here — NO commits per fire spec)

- **Decide the doctrine question explicitly:** is the ribbon's source-of-truth "what J's chart shows" (→ engine must ingest premarket bars into its EMA warmup) or "RTH-only math" (→ J's chart should be flipped to RTH session so eyes match engine)? One-line change either way; today they silently disagree.
- If engine-side: `_build_payload` already receives the full frame before RTH-filtering — seeding the ribbon pre-filter would be a ~2-line, A/B-gated change (every ribbon-gated block filter must be re-validated per the validation-is-the-only-scope rule).
- Extend the 5m cache appends to carry 16:00–20:00 bars if ETH-inclusive ribbon is adopted (currently absent; `DATA-PROVENANCE.md` registry note needed).

## Protocol notes (repeatability)

- Replay driver: `replay_start(date)` anchors at prior-day 19:59:59 ET; fast-forward premarket on 30m TF (11 steps), drop to 5m, then 9-step hops = checkpoints every 45 min, 09:30→15:30. ~35 tool calls/day.
- Only agent touching TV; one chart; replay stopped and chart verified back to realtime BATS:SPY 5m at end (`tv_health_check` PASS 20:45 ET).
- TV values are 2dp renders — sub-cent comparisons are meaningless below $0.01.
