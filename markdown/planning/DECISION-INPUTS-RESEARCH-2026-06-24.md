# Decision-Inputs Research — Volume / Events / Regime (2026-06-24)

> J's 2026-06-24 ask: *"what other indicators may help us see that — like volume, what current events were going on, or market status overall."* This is the read-only value assessment for **Plan 3** ([PLAN-3-DECISION-INPUTS.md](PLAN-3-DECISION-INPUTS.md)). Advisory only — no production code/params touched.
>
> **The bar (C3/C4):** an input only earns wiring if a confluence/size/regime use of it **beats the null** on real-fills history. A SPY-price read that a random-entry null reproduces is an exit-structure artifact, not option alpha. **Never a blunt veto** — surviving inputs wire as a confluence modifier, a size multiplier, or a regime switch.
>
> **Scope note:** the directional **premium class is exhaustively closed** (~64 long families + short/long defined-risk all dead — see [STRATEGY-DIRECTION-BACKLOG.md](../research/STRATEGY-DIRECTION-BACKLOG.md)). These three inputs are not new signals; they are **conditioners on the one live edge** (`vwap_continuation`, ATM/0DTE, `params.json#j_vwap_cont_enabled=true`) and the dormant edges #2/#4. The question is which of them measurably *improves* that edge, not whether they create a new one.

---

## TL;DR value table

| Input | Used today? | Incremental value | Disposition |
|---|---|---|---|
| **Volume — filter 9/10 mult (0.7×)** | YES (live, near-no-op) | Knob is set BELOW average = "red/green bar" only. Real lever unused. | **KEEP, re-test as RVOL** (vary-and-assert per C14) |
| **Volume — divergence gates (f7)** | YES (live) | Structural invalidation, cheap. No isolated A/B but low-risk. | **KEEP as-is** |
| **Volume profile / HVN-LVN-POC** | BUILT, not entry-wired | POC/VA *fade* fails L172 null (edge_over_null −$1.06/tr) + truncation guard. As a *fade entry* = DEAD. | **DROP as a trigger; TEST as confluence-only** |
| **Reclaim/rejection volume confirm** | NO | Never isolated-tested on real fills. Cheapest highest-value volume test. | **TEST — the #1 volume experiment** |
| **Catalyst — blackout / macro-bias veto** | YES (live, defensive) | Blackout + counter-trend hard-veto + soft threshold-bump. Defensible. | **KEEP** |
| **Catalyst — size modifier** | flag exists, OFF | `enable_size_modifier_windows=false`, dormant placeholder. Directional-near-event A/B = DEAD (pre-FOMC −$58/tr). | **DROP size-up; consider size-DOWN test only** |
| **Regime — VIX direction/slope** | YES (live, filter 8 + edge #4) | `vix_rising`/`vix_falling` already gate filter 8; `vix_slope5` in dormant edge #4. C5 honored. | **KEEP; thread intraday VIX series to un-block edge #4** |
| **Regime — ribbon stack + conviction** | YES (live, hard gate) | Filter 5 stack + Gate A/B/C. Trend/chop proxy already live via ribbon. | **KEEP** |
| **Regime — trend-vs-chop strategy switch** | DRAFT, watch-only | Per-day regime switch *to a condor* = DEAD (directional out-earns harvester on its own chop days). | **DROP structure-switch; KEEP regime as a per-edge SIZE/ON-OFF dial** |
| **Regime — breadth proxy** | swarm-only (advisory) | `internals_output.json` exists but never reaches the entry gate; no real-fills test. | **TEST as a forward-banked confluence tag (low priority)** |

---

## 1. VOLUME

### What's used today
- **Filter 9 (bear) / Filter 10 (bull)** — `breakdown_bar_bearish` / `buyer_pressure_bar_v11` require `bar.volume >= vol_mult × 20-bar SMA`. Live `filter_9_vol_multiplier = 0.7` (`automation/state/params.json:34`; `backtest/lib/filters.py:135-162`, `:976-982`). **0.7× is BELOW average** — by design (`filters.py:147-149`, `heartbeat.md:452`): it catches J's *morning* rejection bars before volume builds. Net effect: the filter is **effectively just "red bar" (bear) / "green bar" (bull)** — the volume dimension is near-inert at 0.7×. The heartbeat sweep that ratified it (1.3×=$1,768 / 1.0×=$2,136 / **0.7×=$3,053** / off=$1,922, 4-of-4 J anchors) shows *tighter* volume gating HURT on the anchor set — i.e. raw bar-volume-vs-baseline is not a clean confluence signal at entry.
- **Filter 7 — volume divergence** (`volume_divergence_failed` / `_bullish_volume_divergence_failed`, `filters.py:503-527`, `:985-1005`): a breakdown bar followed by an opposite recovery bar with `vol >= breakdown vol` invalidates the setup. Cheap structural guard, live both sides.
- **No RVOL / relative-volume / climax / volume-spike gate exists** anywhere in the entry path (confirmed by full-repo search).

### Volume profile (HVN/LVN/POC) — built but not an edge
- **Implemented**: `backtest/lib/level_strength.py:423-445` (`VolumeProfile`, `compute_volume_profile`) → POC/VAH/VAL. Wired into `key-levels.json` Liquidity tier by `automation/scripts/compute_levels.py:331-354` (prior-day RTH, $0.10 bins, 70% value area, ±$5 of spot). **HVN/LVN nodes are NOT implemented** — only POC/VAH/VAL.
- **As a fade ENTRY it is DEAD on real fills.** `analysis/recommendations/b4-volume_profile_poc.json` (2026-06-21): best cell (developing profile, ATM, −8% stop) = +$1.19/tr, but **fails 4 gates** — `drop_top5_gt0=false`, `is_half_gt0=false`, **`beats_null=false`** (edge_over_null = **−$1.06/tr**; random-entry null MEAN +$2.25/tr *beats* the signal), and `no_truncation=false` (chart-stop-only flips to −$24.75/tr = the positive average was a stop-truncation artifact). Verdict: `NOT A CANDIDATE`. This is the textbook C3/L58 outcome — a real underlying-profile read that theta+delta erase in 0DTE.

### Reclaim/rejection VOLUME confirmation — the untested gap
- **Never isolated-tested.** `level_strength.py` includes `volume_at_touches` as one *scoring* component, but there is **no A/B that asks "does a volume-confirmed reclaim/rejection at a named level beat an unconfirmed one"** on real-fills option P&L. The closest is `analysis/recommendations/vwap-cont-rvol-floor.json`: an **RVOL floor** (session realized-vol bps/bar) on the live `vwap_continuation` edge. It improves WR (84.8% at floor 9.0, n=46) but **fails the full OP-22 gate** (`all_cuts_oos_positive=false`, WF median 0.27<0.70) — 6/7, a near-miss, dormant. That tested *session* vol, not *bar-at-level* volume.

### How to wire (and the experiment to run)
- **KEEP filter 9/10 at 0.7×** (don't tighten — anchor sweep says tightening hurts) but **re-test relative volume as a CONFLUENCE TAG, not a gate**: add an `rvol_at_signal = bar.volume / 20-bar SMA` field to the `vwap_continuation` signal set and A/B whether `rvol >= k` (k swept 1.2–2.0) lifts per-trade expectancy on real fills. **Method:** reuse the `vwap-cont-rvol-floor.json` harness (bar-RVOL instead of session-RVOL) through `lib.simulator_real`; must clear the L172 random-entry null + L171 truncation guard + drop-top5. This is the single highest-value, lowest-cost volume experiment.
- **DROP volume-profile as a trigger** (null-failed). **OPTIONAL**: keep POC/VAH/VAL as a *confluence corroborator* on an *already-validated* level trigger (i.e., +1 confluence weight when the rejected level coincides with POC/VA-edge), only if that confluence variant independently beats the null — do NOT resurrect it as a standalone fade.

---

## 2. CURRENT EVENTS / CATALYSTS

### What's used today (defensive, live)
- **Filter 2 — news clear**: a tick SKIPs if `now_et` is inside any `today-bias.news_calendar.no_trade_window[]` (`heartbeat.md:445`, `:543`). Windows are built premarket (Step 1b) from `macro-calendar.json` HIGH/MED events. `enable_news_no_trade_windows=true` (`params.json:225`).
- **Macro-bias inheritance v2 (hard veto + soft modifier)** (`heartbeat.md:554-584`): reads `events_today[]` for `{fomc, cpi, nfp, pce}`. `0<min≤120` → **HARD VETO** counter-trend entries; `120<min≤240` → **SOFT** (bull ≥10/11, bear ≥7/10); `>240` → standard. `regime_label` (FOMC_EVE_SUPPRESSION / FOMC_DAY_HARD_VETO / FOMC_DAY_SOFT) written to loop-state for context.
- **Scout** (`.claude/skills/scout/SKILL.md`, `automation/scout/state/scout_output.json`) produces `macro_calendar_today[]`, `news_top_5[]`, `catalysts_in_session[]`, `risk_regime_call`, `today_no_trade_windows[]`. **Advisory** — it seeds premarket's bias write; it does **not** directly gate a tick. Note `news.json` is currently stale (`as_of 2026-06-15`, today-bias flags 10-day-stale calendar); the PCE 06-25 overhang lives only in `today-bias.upcoming_events`.

### Is a catalyst ever a SIZE modifier? No.
- `enable_size_modifier_windows=false` (`params.json:226`) — a **dormant placeholder**; premarket emits `size_modifier_windows: []` and no heartbeat code consumes it. Catalysts only *blackout* or *bump thresholds*; size never changes.

### Evidence on trading near catalysts
- **Directional pre-event = DEAD.** `analysis/recommendations/pre-fomc-announcement-drift.json`: pre-FOMC morning entries = **−$58.07/tr** (n=9), 2/8 gates, does not beat the null, L173-negative. No directional edge from being near a scheduled event.
- Event *premium structures* (short condor / long strangle, backlog #6/#6b) are also DEAD once the wide-band tail is priced — but that's a structure test, not a directional-level conditioner.

### How to wire
- **KEEP** the blackout + counter-trend hard-veto + soft threshold-bump exactly as-is — these are *risk* controls (prevent the 05-07 chop-trap), and they're defensible without an edge claim. Do **not** frame them as alpha.
- **DROP "size UP near a catalyst"** — there is no evidence a level-play near a catalyst pays *more*; the directional-near-event test is negative.
- **The only catalyst experiment worth running** is a **size-DOWN / participation dial**, not a veto: does halving size (or requiring +1 confluence) on `vwap_continuation` signals within N hours of a HIGH event reduce drawdown without surrendering expectancy? This is a *risk-adjusted* test (L175 Sortino/maxDD), no-regression-exempt because it never zeroes a day. Lower priority than the volume RVOL test — the macro-bias veto already removes the worst pre-event window.

---

## 3. MARKET STATUS / REGIME

### What's used today
- **VIX *character*, not just level — already honored (C5).** Filter 8 live: bear = `VIX>17.30 AND vix_rising` (cached/flat does **not** pass); bull = `VIX<17.20 OR vix_falling` (`heartbeat.md:451`, `:549`; `filters.py:106-112` `vix_direction` with 0.05 deadband). Direction is a *required* dimension, not optional. The dormant edge #4 (`j_vix_dayside`, `params.json:90-97`) uses an intraday **`vix_slope5`** + trailing-median regime — the cleanest VIX-character use in the repo — but it's inert because the live `BarContext` doesn't yet thread an intraday VIX series (the detector SKIPs rather than guess).
- **Trend-vs-chop via ribbon — already live.** Filter 5 (ribbon BEAR/BULL stack, hard gate) + the v15.3 conviction gates: Gate A ribbon spread Δ≥5¢/3bars (accelerating), Gate B freshness ≤15 bars, Gate C midday single-trendline block. Ribbon-flip-back is a primary *exit*. SPY-vs-MA trend is effectively read through the EMA ribbon stack; SPY-vs-VWAP through the VWAP-family edges.
- **Regime label** is written for context (`heartbeat.md:578-584`) but does **not** switch strategy live.

### Trend-vs-chop strategy SWITCH — tested, dead as a structure switch
- The per-day **regime-switch-to-a-condor** experiment is **DEAD** (backlog #3): on the classifier's own 55 chop days the live directional sleeve out-earned the iron condor +$1,202 vs +$460 (−$743), 0/108 swept cells passed. The premise "directional bleeds in chop, the harvester won't" does **not** hold on real fills — the tight −8% ATM structure stays net-positive in chop. The DRAFT `REGIME_SWITCHER` (`markdown/0dte/regime_switcher.md`, `backtest/lib/regime_classifier.py`) that routes ODF/SNIPER/v14e/VWAP per regime remains watch-only and unvalidated on real fills.

### Breadth proxy — exists, never reaches the gate
- `automation/swarm/state/internals_output.json` (sector XLK/XLF/XLE rotation → `breadth: narrow|broad`) is a **daily swarm advisory**, consumed only by the 6-agent synthesis, **never** by a heartbeat filter. No TICK / advance-decline / McClellan / %-above-MA in the live path, and no real-fills test of breadth as an entry conditioner.

### How to wire
- **KEEP** VIX-direction filter 8 and the ribbon stack/conviction gates — they already encode "market status" the right way (character + trend-structure).
- **Highest-value regime action: thread an intraday VIX series into `BarContext`** so the *validated* dormant edge #4 (`j_vix_dayside`, OOS +$79/tr ATM, clears all 8 gates) can actually fire. This is the one regime input that is *already validated* and only blocked on plumbing — it is a deployment task, not a research task.
- **DROP the trend-vs-chop structure switch** (directional wins its own chop days). Instead, use regime as a **per-edge SIZE / participation dial** (the surviving framing from #3 and the volranker work): a causal morning trend/chop label SIZES the live edge up on its broad winner-days rather than switching it off — but note the volranker sizing result (#9) only pays at $25K+ accounts, so this is forward-banked, not actionable at the current $2K.
- **Breadth: lowest priority.** If tested, forward-bank `breadth` as a *confluence tag* on `vwap_continuation` signals and check it beats the null before any wiring — it is unproven and not on the critical path.

---

## Recommended order of work (all read-only research first, ship under OP-22 if it clears)

1. **Bar-RVOL-at-signal confluence test on `vwap_continuation`** (volume) — cheapest, attacks the one near-inert live knob; reuse `vwap-cont-rvol-floor.json` harness with bar-RVOL; gate on L172 null + L171 truncation + drop-top5.
2. **Thread intraday VIX series into `BarContext`** (regime) — un-blocks the *already-validated* edge #4; deployment, not discovery.
3. **Catalyst size-DOWN / participation dial** (events) — risk-adjusted test (L175), no-regression-exempt; secondary to (1).
4. **POC/VA as confluence-only corroborator** and **breadth forward-bank tag** — lowest priority, only if they independently beat the null.

Everything that fails its null stays DROPPED and gets a one-line entry so it isn't re-hunted (C7/L172).
