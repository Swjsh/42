# Heartbeat provenance & evidence (relocated from `automation/prompts/heartbeat.md`)

> **Why this file exists.** The live Safe heartbeat prompt (`automation/prompts/heartbeat.md`)
> is fired headless every 3 min via `claude --print` on Haiku. A ~103KB prompt was heavy enough
> that a context-loaded tick could emit its `HB#` line yet exit before completing the end-of-prompt
> state-write (decisions.jsonl froze at the 10:23 tick on 2026-06-25; loop-state observed empty `{}`).
> The durable fix (2026-06-25) trims the hot prompt toward Bold's proven-reliable weight class by
> moving **reference/evidence prose** here — the rule LOGIC stays in the prompt, the rule NUMBERS
> live in `params.json`, and the WHY/provenance lives here. Nothing was lost; it was consolidated.
> The persistence guarantee itself is now independent of prompt weight via
> `setup/scripts/heartbeat_persist_writer.py` (deterministic post-tick decisions writer).

This doc is the canonical home for the ratification history, A/B evidence, and validation summaries
that used to be inlined in the hot prompt. The prompt now points here.

---

## Rule version history (v11 → v15.3)

**`RULE_VERSION = "v15.3"`** (verified daily at premarket Step 1a vs `params.json#rule_version`;
mismatch → kill-switch). Every rule VALUE is read from `automation/state/params.json` at tick time.

### v15 (LIVE 2026-05-13 evening)
> J authorization: *"v15 can go live that is chill lets let er rip it seems a lot better. keep v14 documented still incase we need to revert."*
> Source: `markdown/0dte/V15-ACTIVATION-2026-05-13.md` + `analysis/recommendations/v14_enhanced-real-fills.json` (3/3 OP-20 gates) + `v14_enhanced-walkforward.json` (TRAIN $18,549 / TEST $17,901 = 2.67x).

What changed v14 → v15 (BEAR-side BEARISH_REJECTION_RIDE_THE_RIBBON only; bull mirror stayed v14):
1. **Entry time gate:** `time ≥ 09:35 ET` (was `≥ 10:00 ET`).
2. **Strike per account-equity tier** (was uniform ITM-2): $0-2K → OTM-3 (`-3`); $2-10K → OTM-2 (`-2`); $10-25K → OTM-1/ATM (`-1`); $25K+ → ITM-2 (`+2`).
3. **Premium stop bear-side:** SUPERSEDED 2026-06-18 by CHART-STOP-PRIMARY (now a −50% catastrophe cap). History: −8% (v14) → −20% (v15.0) → −10% (TIGHTER_STOP 2026-06-17, IS +$8,705 / OOS +$1,802) → −50% cap (2026-06-18, real-fills A/B total $8,160 → $16,671, edge_capture invariant +$1,340).
4. **Profit-lock trailing chandelier** (was static breakeven-after-TP1): arm at `favor ≥ entry × 1.05`; initial floor `entry × 1.10`; trail **12.5%** off HWM (WP-6 2026-06-21: 15%→12.5%, Safe-only; exp +$10.00/tr, OOS +$14.97/tr, Sortino 11.83→13.80, maxDD equal, posQ 6/6; scorecard `analysis/recommendations/SUNDAY-WEB-LEARN-SCORECARD.md`). Stop never lowers below original premium-stop.
5. **TP1 split:** `tp1_qty_fraction = 0.667` (Rank-31 2026-06-16, WF=1.08, OOS +44%).
6. **Runner target:** `2.50` active target (was 3.0 ceiling).
7. **Per-tier max-premium hard gate (G6b):** $0-2K→40%, $2-10K→30%, $10-25K→25%, $25K+→20%.

Inherited from v14: all 10 BEARISH filters except filter 1; all 11 BULLISH filters; v13b quality-tier sizing; first-entry-after-stop lockout; macro hard-veto tiers; ribbon-flip-back exit; chart stop; iron-law gate; gate sequence G5/G7/G1/G2/G10/G6.

### v15.1 (LIVE 2026-05-14 evening)
> J authorization: *"any time between 9:35 - and 3pm is fair game for ENTRIES. theta will kill us after 3. we must exit before EOD. dont ask me for 'my call' keep shipping and building and fixing and improving."*

1. **14:00-15:00 ET no_trade_window REMOVED** — continuous 09:35-15:00 ET entry window.
2. **Entry cutoff hardened 15:50 → 15:00 ET** (existing positions still flatten 15:50 hard stop; EodFlatten 15:55 safety net).
3. **R1 closed-bar fix** — SPY 5m reads use `count=3` + `bar.time + 5min ≤ now_et` filter (discards the in-progress bar TV returns at [-1]). Docs: `markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`.

### v15.3 (LIVE 2026-06-01; chart-stop-primary 2026-06-18)
- **Ribbon conviction gate** (Gates A-D): 16-month real-fills, ribbon gate alone OOS WR 0.77 +28.3/c WF 4.29 (48 signals); with V14E exits OOS WR 0.73 +25.7/c WF 3.78; all 12 threshold combos WR ≥ 0.71; anchor 5/6 PASS. Source: `analysis/recommendations/ribbon-gate-wf-scorecard.md`.
- **Chart-stop-primary** (2026-06-18): chart-level / ribbon-flip-back / chandelier are primary; premium stop demoted to a −50% catastrophe cap both sides. Real-fills (n=26): primary −10%/−8% → $8,160 WR 38%; −50% cap → $16,671 WR 65%; edge_capture invariant +$1,340. Scorecard `analysis/recommendations/chart-stops-ab-2026-06-18.json`.

**Revert (v15 → v14):** `cp automation/prompts/heartbeat-v14-prod-backup.md automation/prompts/heartbeat.md`; set `params.json#rule_version` = `"v14"`; set `premarket.md` `RULE_VERSION_EXPECTED = "v14"`. Premarket Step 1a re-verifies the pin next 08:30 ET fire. To revert chart-stops to premium-primary: `params.json#premium_stop_pct_bear: -0.10`, `premium_stop_pct: -0.08`.

---

## Ported backtest gates E–I — evidence

These five BLOCK gates were ported from `backtest/lib/orchestrator.py` to the live prompt 2026-06-18
(closing a live/backtest parity gap). Each is config-gated by its `params.json` key (no-op when
`false`/`0`/`null`). **Revert any gate by setting its key false/0/null** — no prompt edit needed.

| Gate | params key (current) | Evidence | Scorecard |
|---|---|---|---|
| E — vix_bear_hard_cap | `vix_bear_hard_cap` (23.0) | IS n=9 blocked WR=0% (+$790); OOS n=6 WR=17% (+$420); WF=0.797 | `safe_vix_bear_hard_cap.json` |
| F — block_level_rejection | `block_level_rejection` (true) | Largest edge: IS +$13,181 / OOS +$682 / WF=0.842, 0 hurt sub-windows, anchor +$1,478 (4/29). BULL `level_reclaim` NOT blocked. | `level-rejection-gate-01.json` |
| G — entry_bar_body_pct_min | `entry_bar_body_pct_min` (0.20) | IS n=113→98 (WR=31.2%) +$295; OOS n=24→20 (WR=0%) +$566; WF=7.193. BEAR-side only. | `safe_entry_body_gate.json` |
| H — block_bull_1100_1200 | `block_bull_1100_1200` (true) | Worst TOD: IS n=11 WR=9.1% (−$89); OOS n=1 (−$42); WF=5.22 | `safe_bull_1100_1200_gate.json` |
| I — block_elite_bull | `block_elite_bull` (true), `_vix_low` (0.0), `_vix_high` (25.0) | IS_delta +$113; OOS_delta +$63; WF=3.890 (removes conf+lvl_rec bull losers across VIX band) | `safe_block_elite_bull_all_vix.json` |

Gates A–D evidence: Gate C midday-trendline = −8.6/trade OOS (307 trades); Gate D afternoon
conf+lvl_rec = IS+$412 OOS+$176 WF=2.644 (`safe_time_class_gate.json`). **Revert A–D:**
`params.json#midday_trendline_gate: false, min_ribbon_momentum_cents: 0, max_ribbon_duration_bars: 999, block_conf_lvl_rec_afternoon: false`.

Filter 9 vol-multiplier (0.7×) sweep: 1.3×=$1,768/4-of-4, 1.0×=$2,136/4-of-4, **0.7×=$3,053/4-of-4**, off=$1,922/3-of-4. Filter ≥1-trigger (bear) sweep: ≥1 → 27 trades/59% WR/−$546 vs ≥2 → 13 trades/46% WR/−$742.

---

## Flag-gated morning setups — validation summaries

All four are **default-OFF / inert** in production; the prompt keeps a compact executable block for
each (so flipping the flag activates it). Full validation evidence + wiring docs:

- **GAP_AND_GO** (`gap_and_go_enabled`, default false): once-per-day opening-gap continuation, chart-stop-only. exp +$41.6/trade, WR 72.6%, n=84, DSR PASS, WF median +1.87 (all OOS+), 6/6 quarters +, both dirs +, causality 96/96. Detector `backtest/lib/watchers/gap_and_go_watcher.py`. Scorecard `analysis/recommendations/gap-and-go-LIVE.json`. Wiring `markdown/specs/GAP-AND-GO-HEARTBEAT-WIRING-PROPOSAL.md`.
- **VWAP_CONTINUATION** (`j_vwap_cont_enabled`, default false): J's near-daily morning VWAP continuation. exp +$38.3/trade, WR 76.5%, n=153, fires 42% of days, both dirs + (C +$26.0/77.4%, P +$53.3/75.4%), DSR PASS, OOS +$24.12. 6-of-7 OP-22 near-survivor. Detector `backtest/lib/watchers/vwap_continuation_watcher.py`. Scorecard `analysis/recommendations/j-daily-pattern-LIVE.json`. Doc `markdown/specs/VWAP-CONTINUATION-WIRING.md`.
- **VWAP_RECLAIM_FAILED_BREAK** (`j_vwap_reclaim_fb_enabled`, default false): subtractive sibling — failed counter-trend move that reclaims with-trend. Clears all 8 anti-cherry-pick gates @ ITM-2 (OOS +$72/trade, posQ 5/6). OTM-2 FAILS (C29) → Safe-2 ships ATM, Bold ITM-2. Isolated exit knobs: `j_vwap_reclaim_fb_premium_stop_pct` (-0.08), `_tp1_pct` (0.30), `_stop_buffer` (0.25). Detector `backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py`. Scorecards `analysis/recommendations/SUBTRACTIVE-SELECTION-SCORECARD.md` + `RECLAIM-RESCUE-SCORECARD.md`.
- **VIX_REGIME_DAYSIDE** (`j_vix_dayside_enabled`, default false): VWAP day-trend side directionally, but only in favorable VIX regime (LOW level + not-rising slope). ATM cell clears all 8 gates (OOS +$79.49/trade, drop-top5 +$25.91, posQ 5/6, n=76/oos=21). ITM-2 is a truncation artifact → Safe-2/ATM-only. Isolated knobs: `j_vix_dayside_low_margin` (0.25), `_slope_rule` ("not_rising"), `_premium_stop_pct` (-0.08), `_tp1_pct` (0.30). Detector `backtest/lib/watchers/vix_regime_dayside_watcher.py`. Scorecard `analysis/recommendations/b5-vix-regime-dayside.json`.

All four use the A5 deterministic callable `backtest/lib/live_order_resolver.py#live_order_params`
to resolve strike/expiry/stop/qty (flags OFF ⇒ byte-identical to today's config). Each carries its
own first-entry lock key. C29: strike/stop validated per account — never assume transfer.

---

## Watcher signal layer — design notes

The unified WATCH-ONLY block (replaced the per-watcher ORB + FBW branches 2026-06-18) reads the
whole `Gamma_WatcherLive` fleet (`backtest/lib/watchers/runner.py#WATCHERS`, the registry is the
single source of truth) and logs `WATCH_ONLY` rows to decisions.jsonl so the live ledger sees every
watcher, not just two. **It NEVER places an order** — OP-21 live gate stands (every setup needs 3
live J wins before any live execution path; activating execution is a Rule-9 change). Cost ≈ 0 (one
extra file read per tick + a few decisions rows). Revert to the prior ORB+FBW branches:
`git show d0c8ac0:automation/prompts/heartbeat.md`. Back-compat: `ORB_RETEST_LONG` →
`ORB_WOULD_ENTER`, `FBW_MORNING_MID` → `FBW_WOULD_ENTER` (EOD greps these legacy strings).

---

## Other provenance one-liners

- **Numeric alert** (Step 0a): the L2 `numeric_pulse.py` ($0, every 15s RTH) writes alerts when confidence ≥ 0.65 AND is_contra_trend AND within $0.50 of a ★+ level (+5.8pp avg edge per 16-mo backtest). Alert is corroboration, never authorization.
- **BTC cross-signal** (Step 0c, SOFT-ADOPT 2026-06-16): FORENSIC ONLY, zero gate authority. After 40+ tagged entries, test WR_aligned vs WR_misaligned; promote only if ≥8pp lift with N≥20/bucket → `analysis/recommendations/btc-ribbon-spy-cross.json`.
- **Filter 9 / 11:30-12:00 no-trade window** (ENFORCED-4, auto-ratified 2026-06-17): signal bar in 11:30-12:00 ET skipped. IS avg −$112 stop=88.9%; OOS avg −$424 n=1; both regimes agree; `entry_no_trade_window_et: ["11:30","12:00"]`.
- **MACRO BIAS / regime_label**: see prompt's MACRO BIAS INHERITANCE table (kept inline — it is executable). The 2026-05-07 12:30 FOMC chop-trap is the canonical hard-veto case.
