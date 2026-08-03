# EOD 2026-08-03 — Lens 4: Process + Infrastructure Scrutiny

> Audit window: 16:41–17:10 ET Monday 2026-08-03 (clock verified via `setup/scripts/et_clock.py`:
> `2026-08-03 16:41:30 Monday EDT, market_hours=False` — the tasking's "~14:50 ET, market open"
> assumption was stale; market was CLOSED for this entire audit, which let post-16:00 fires
> (monday_verify 16:15, WinnerAutopsy 16:25) be scored directly). Zero live trading-path files
> touched; the two fixes shipped are instrument/test-layer only (`fill_latency.py`,
> `exit_shape_parity_study.py`, tests). All broker reads via `fleet_broker` (fresh keys).
> As of 16:41 ET the staged AFTER-CLOSE-PACKAGE (Ships A/B/C) had **not yet been applied**
> (`git log` clean of both ship commits; `params.json` still `block_elite_bull: true` per
> monday-verify ws1) — noted as fact for the applying session, not this lens's job.

---

## 1. Reconciliation — zero-tolerance ledger audit

### 1a. Broker truth ↔ fills-ledger ↔ decision rows: CLEAN

- **15/15 broker fill *events* ↔ 15/15 `fills-ledger.jsonl` rows** — exact match on
  (arm, order_id, side, qty); partials split identically (risky-1 TP1 = 3×1@0.60,
  risky-3 runner = 2×1@0.74/0.73). Zero in-ledger-not-broker; zero missing-in-ledger.
- **12/12 order-legs have a decision row**: 9 fleet legs in `automation/state/fleet/{arm}/decisions.jsonl`,
  3 safe-2 legs in `automation/state/core-decisions.jsonl` (entry at `extra_exec[0].exec.broker.id`,
  exits at `exit_pass[0].actions[0].broker.id` — see §2).
- **Exit-state mutations ↔ fills**: every `exit-state.json` is `{}` post-flat; safe-2's file
  mtime = 13:40:04 ET = its runner-exit minute exactly. safe-3 TP1 tick 10:03:03 flips
  `tp1_filled` + ratchets stop 0.21→0.42→0.8075 (HWM 0.95 × 0.85); safe-2 ratchets
  0.5244→0.57→0.6545→0.748→0.7905 (HWM 0.93 × 0.85) and exits runner 0.79 > TP1 0.74 —
  the "trail ratcheted ABOVE tp1" designed behavior, confirmed in ledger and broker.

### 1b. Equity reconciliation — to the penny modulo unposted fees

| Arm | Acct # | Gross from fills | Equity − $5,000 start | Residue | Residue / contract sold |
|---|---|--:|--:|--:|--:|
| safe-3 | PA32T7Q1O20H | +$145.00 | **+$144.85** | −$0.15 | $0.050 (3 sold) |
| risky-1 | PA3S9N1IV0A4 | +$145.00 | **+$144.76** | −$0.24 | $0.048 (5) |
| risky-3 | PA3V7JT25H6Z | +$176.00 | **+$175.76** | −$0.24 | $0.048 (5) |
| safe-2 | PA3POKNV46VG | +$68.00 | **+$67.85** | −$0.15 | $0.050 (3) |
| bold-2 | PA3WEBXJU67N | $0.00 | **$0.00** | 0 | — |
| **Total** | | **+$534.00** | **+$533.22** | **−$0.78** | |

Equity deltas match the established facts *exactly*. The −$0.78 book-wide residue is
regulatory-fee-shaped (≈$0.048–0.050 per contract **sold**, zero on the no-trade arm), but the
activities endpoint returned **zero fee rows today** — Alpaca paper posts reg-fee activities
late. **UNVERIFIED until the fee rows post — re-pull activities tomorrow; if no fee rows appear
dated 08-03/08-04, this residue is unexplained and goes back on the board.**
PDT note: `daytrade_count` was absent from all 5 account payloads (could not verify broker-side);
by pair-math each traded arm consumed 2 day-trades today (TP1 + runner vs same-day entry), so
3/5bd margin limits are live tomorrow: 1 DT headroom per traded arm until Thursday.

### 1c. Fill-latency instrument (7-stage, shipped Saturday) — captured 3/3, but its clock was broken

- Scope disclosure honored: instrument covers fleet_rest **entry** fills only (safe-3/risky-1/risky-3);
  today that population = 3, and it scored **3/3, 0 missing-instrumentation, 0 no-decision-row** —
  the 4 new instrumentation fields flowed end-to-end on their first live day. safe-2/bold-2 are
  out of scope by design (disclosed in the module docstring).
- **DEFECT (found + fixed this audit):** `_parse_iso` claimed "naive == ET" but resolved naive
  stamps in the box's LOCAL zone (Mountain) — first live rows showed `bar_close→verdict = 7563.0s`
  and `verdict→signal = −7141.0s` (off by exactly the 2h zone gap). Fixed: naive → `ET_TZ`
  attach (from `et_clock`) before epoch conversion. Guards RED-proofed (8/9 fail pre-fix, 9/9 pass
  post-fix); `analysis/pain-ledger/latency.json` regenerated with corrected numbers.
- **Corrected decomposition (all 3 fills, 09:42 wave):**

| Hop | safe-3 | risky-1 | risky-3 |
|---|--:|--:|--:|
| trigger-bar label → core verdict | 363.0s | 363.0s | 363.0s |
| verdict → signal written | 59.0s | 59.0s | 59.0s |
| signal → arm plan | 2.03s | 3.15s | 4.22s |
| plan → submit | 0.52s | 0.49s | 0.40s |
| submit → broker-submitted | 0.083s | 0.098s | 0.100s |
| broker-submitted → fill | 0.117s | 0.177s | 0.123s |

  **Decision→fill ≈ 61–64s** (verdict 09:41:03 → fills 09:42:04–06); the fleet hop
  (signal→fill) is **2.8–5.0s**. Versus Friday's 12:19 winner (4m03.9s pipeline,
  1-second-stale snapshot): the placement side is now sub-second and the whole
  bar→fill path ≈ 425s is dominated by the trigger-bar's own 5-minute duration + the
  09:41 verdict tick (the "bar_close" stage is the bar *label* = open time — semantics
  documented, not a defect). No 07-31-class stall today.
- **Why the nightly copy was stale (root-caused, fixed, restored):** see §3 WinnerAutopsy row.

---

## 2. The systemic find: the `extra_exec` path is invisible to the new instruments (L244 recurs)

**safe-2's +$67.85 came from `bollinger_squeeze` — an extra-setups placement
(`heartbeat_core._route_extra_setups`) recorded INSIDE a tick whose primary verdict was
`SKIP_ELITE_BULL_LEVEL_RECLAIM`** (13:21:03 row: primary elite-bull blocked by gate; extra branch
`extra_exec[0]` = PLACED, limit 0.57, fill 0.53, triggers BB_SQUEEZE_RECENT + BAND_BREAK_UP +
VOLUME_CONFIRM; NBBO at plan 0.55/0.55). Not a J-intent (`j-intents.json`: 1 intent, 07-29,
expired). The journal DID capture it (Rule 8 ok: "Secondary-setup placements (extra_exec, 1
PLACED)"). But every *counter* that reads top-level actions reported the core as flat today:

| Surface | What it said | Truth |
|---|---|---|
| monday-verify ws1 | "Actual entries 2026-08-03: **safe-2=0**, bold-2=0, …" | safe-2 entered 13:21, +$67.85 |
| participation-daily (16:10 ET) | safe **fills: 0**, verdict YELLOW "safe=0/2-4" | 1 filled position, 3 legs |
| self-check 16:39 → STATUS.md | "PARTICIPATION DEGRADED … safe=0/2-4 bold=0/2-4" | safe participated |
| live-watch ws7 entries list | 3 entries (fleet lane) | by-design fleet-only, but the *label* reads like the day's total |

One mechanism, three surfaces telling J "core didn't trade" on a day core banked +$67.85 —
exactly the L244 shape (fill-funnel monitor blind to a 2nd execution path) recurring in
instruments built *after* L244 was written. **Fix direction (queued, not shipped —
`heartbeat_core.py` was read-only today):** either (a) counters scan `extra_exec[].exec.broker`
alongside top-level actions, or (b) the tick row gains a cheap top-level marker
(e.g. `extra_entered: true`) so naive counters can't miss it. Note `trade-today.json`
(Gamma_TradeToday — the instrument L244 built) got it RIGHT: `spy_fills_today: 12` including
safe-2 — the newer instruments didn't inherit its lesson.

---

## 3. Guard / task health — every named instrument, quoted

PowerShell `Get-ScheduledTaskInfo` times are local MT (= ET−2). All results below converted to ET.

| Task | Last fire (ET) | Result | Output freshness / verdict |
|---|---|--:|---|
| Gamma_HeartbeatCore | 15:55:01 | 0 | 772 armed rows today (386/account, both `armed:true`); 51+51 `SKIP_ELITE_BULL_LEVEL_RECLAIM` (final count — the "74+" mid-day figure grew to 102); 12 `SKIP_STALE_TRIGGER` at open |
| Gamma_FleetExecutor | 16:01:02 | 0 | 384 safe-3 rows today; 2 `ENTER_BULL` = 09:31 `SKIP_EARLY_ENTRY` (gate held) + 09:42 placed |
| Gamma_LiveWatch (1-min) | 16:10:00 | 0 | 401 RTH fires 09:25–16:10 (~405 expected), 41 in_trade ticks — consistent with 24min fleet + 19min safe-2 holds; CLOSED marker written 16:06 |
| Gamma_ThetaClock (1-min) | 16:00:00 | 0 | **The 29/29-empty question, answered on REAL positions: 86 rows today across 2 contracts — `broker_snapshot=0`, ALL 86 = `sqrt_time_decay_model_est`.** The broker-greeks feed still returns nothing usable; the closed-form estimator carried the day. Streak holds, now with real-position evidence |
| Gamma_RegimeStamp | 08:22:03 | 0 | GREEN (monday-verify ws6): stamp + today-bias `regime_context` same-day, organic 08:22 fire proven |
| Gamma_MondayVerify (16:15) | 16:15:01 | 0 | **Registered AND fired.** Checks: ws7 GREEN, ws6 GREEN, ws3 GREEN, theta GREEN, ws1 GREEN, ws11 NOT_EXERCISED (recency window didn't advance) → overall NOT_EXERCISED. Caveat: ws1's "safe-2=0" line is wrong (§2) — the checker worked; its entry counter is blind |
| Gamma_GateExpiryCheck | 01:00 (nightly) | 0 | `gate-registry-status.json` fresh 01:01 ET; `block_elite_bull.overall = RED` ("refused cohort would have EARNED…") — the Ship-B-supporting instrument still current; next fire 01:00 tonight |
| Gamma_Trendlines (5-min) | 16:00 | 0 | 377 rows today; families: wick-support 108 / wick-res 79 / body-support 111 / body-res 79; statuses TESTING 74 / BROKEN 145 / INTACT 158. Max-respect **wick support: respect_count 63, violations 0, still TESTING at 15:50 (current_value 757.92)** — the "respected ×50, TESTING ~757.4 @ 14:40" fact extended to close: tested, never confirmed-broke |
| Gamma_LevelRefresh (5-min) | 16:38 | 0 | Hysteresis (Sat WS3 fix) live: 171 runs logged, `hysteresis_held` fired 80× across 17 levels; worst flicker 743.25 at **5 flips vs Friday's pre-fix 14×** — improved 64%, not yet zero |
| Gamma_EodFlatten / Core / Aggressive | 15:52–15:55 | 0 | Nothing to flatten (all flat since 13:40) — correct no-ops |
| Gamma_WinnerAutopsy (16:25) | 16:25:01 | "0" | **SILENT FAILURE, root-caused + fixed + restored.** Result 0 is the wscript hidden-shim's exit code (C8) — two `pythonw winner_autopsy` processes were found still alive 20+ min after the fire, hung in the OPRA fetcher's 20/40/80s retry ladder. Root cause (one sentence): `exit_shape_parity_study.fetch_option_bars` hardcoded `creds_all.get("safe-1")` — the arm RETIRED in yesterday's account rebuild — so every bar fetch 401'd (proven live: safe-1→401, safe-3/bold-2→200) and the fail-open fetcher turned a dead key into "0 bars", starving winner-autopsy + pain-ledger + the fill-latency fold. L234's exact shape. Fixed: `_live_data_creds()` probes arms and caches the first live key; guards RED-proofed; product regenerated 17:05 ET (25 winners incl. today's 4, capture_vs_best_policy 0.8981, winners-only sample; pain-ledger 164/165) |
| Gamma_FreeManager (20-min) | 16:53 | **1** | Failing repeatedly: `manager-log.jsonl` "phase: pick, ok: false, lane: ollama::qwen3:14b" 16:13/16:33/16:53 — local ollama pick failing. Only red LastTaskResult among today's fired tasks. Non-trading; needs its own look |
| Gamma_TvWatchdog / LaunchTV | 16:00 / 06:00 | 0 | TV kept alive all session (526+ armed ticks corroborate) |
| Gamma_BrokerFills | 16:05 | 0 | fills-ledger complete (§1a) |

**STATUS.md noise finding:** the 30-min self-check appended the identical "TRENDLINE-DRAW never
marked today" DEGRADED block **14× today** — a retention-cap/dedupe candidate (OP-22), and the
16:39 instance carries the false "safe=0" participation line (§2).

---

## 4. The morning's finds — followed through

### 4a. Orphaned idempotency guard (committed live today, `b80b799c` 09:24 ET)
- **Guard present, never needed to block — proven, not assumed.** Claim files written for
  exactly the 4 arms that entered (`{arm}/entry-claim.json`: fleet trio 09:42:03, safe-2
  13:21:49; bold-2/safe-1 none — never entered). Order-level skip vocabulary
  (`SKIP_ENTRY_CLAIM_ACTIVE` / `SKIP_OPEN_ORDER` / `SKIP_CANCEL_RACED_FILL` /
  `SKIP_BROKER_UNREADABLE`): **zero fires across all 4 ledgers today** — no duplicate-order
  condition ever arose.
- The adjacent cooldown layer DID work in anger: `SKIP_COOLDOWN_SAME_BAR` ×4 (13:22–13:25,
  all safe/bollinger_squeeze) — the persisting signal was correctly refused re-entry for 4
  ticks after the 13:21 placement.
- Cosmetic: safe-2's claim `claimed_at_et` is tz-naive while the fleet trio's carry `-04:00`;
  `_claim_active` treats naive as ET so behavior is correct — worth normalizing someday, not urgent.

### 4b. Entry-anchor near-miss #1 (safe-3, quantified from the tick ledger)
- Entry fill 0.37, registered anchor 0.42 (limit) → TP1 threshold 0.84 instead of true 0.74.
- Best-premium walk: first crossed **0.74 at 10:00:04** (best 0.81); TP1 actually fired
  **10:03:03** on the 0.95 spike (sold 2@0.92). **TP1-delay window = 3 minutes / 3 ticks**
  (10:00, 10:01, 10:02 — best 0.81/0.76/0.77). No drawdown materialized in the window (worst
  0.74–0.76); today the delay *paid* +$36 on the TP1 legs (0.92 vs ~0.74) — luck, not design.
- Protection during the whole pre-TP1 ride was **structure stop 750.98 (chart primary,
  `stop_mode: structure`) + premium floor 0.21** (−43.2% vs true basis — the limit-anchor makes
  the floor *tighter*, per the package). The real exposure: at the 10:00 peak the position held
  ~+$132 unrealized with no profit-lock (post-TP1-scoped) — an adverse 5m structure break
  would have surrendered it down to the structure-stop exit (bounded below by 0.21 = −$48);
  ~**$180 swing unprotected for 3 minutes**.
- **Correction to this morning's package doc:** its cited tick times ("worst 0.71–0.76 across
  09:51–09:56, rescued by 0.95 spike at 09:57") are ~6 minutes early — the ledger shows that
  premium pattern at 09:58–10:02 with the spike at 10:03. Substance unchanged; timestamps wrong.

### 4c. Entry-anchor near-miss #2 (safe-2 — NEW, not in the package)
- The bollinger_squeeze profile runs a **−8% premium stop**. Anchored to limit 0.57 → stop
  0.5244. True fill 0.53 → **effective stop room −1.1%, not −8%** — the mis-anchor consumed
  ~85% of the stop's intended room; the stop sat $0.006 below cost basis. One spread-wobble
  tick below 0.5244 in the first minutes (worst walked 0.55–0.61 — it never came) would have
  scratched a trade that went on to bank +$68. **Sharpest live quantification of Ship A's
  mechanism yet, and on the STOP side, not the TP side.**
- TP1 side: true threshold 0.689 first crossed 13:28 (best 0.71); wrong threshold 0.741
  crossed 13:31 → fired 13:31, sold 2@0.74. 3-minute delay; paid +$10 by luck.
- n=1 each; anecdotes labeling per discipline — the 105-fill replay in the package remains the
  evidence base; these two are today's live exhibits of the same mechanism.

---

## 5. Cost — today's automation spend vs lean baseline

- `spend-daily.jsonl` (today's row lands 21:30 ET): last 5 days notional Claude accounting
  $126–$277/day (subscription pool, not API bills — the $117–$1452 anomaly was resolved
  2026-07 as notional), sessions 11→28/day rising through the weekend push.
- Today's countable LLM traffic: **swarm-calls 195 rows, minimax-calls 143 rows** (07-31: 16
  minimax calls = $0.0465 → today ≈ **$0.42 est** — 9× call-count growth in 3 sessions;
  small but real dollars on the only non-free lane: **watch it in tonight's SpendSummary**).
  EOD analytics (eod-summary, analyst) both ran `free-tier-primary`, ok=True, $0.00.
- Runaways: none found — every 1-min/5-min cadence firing today is by-design (HeartbeatCore,
  LiveWatch, ThetaClock, CryptoTwin, keepalives). The only failing task is Gamma_FreeManager
  (exit 1, §3). The WinnerAutopsy hang was a one-shot per fire (2 stuck pythonw, killed), not
  a spawner.

---

## 6. Ship list from this lens (done tonight / queued)

**Shipped by this audit (instrument/test layer, market closed, RED-proofed, committed):**
1. `setup/scripts/fill_latency.py` — naive stamps now resolve as ET (`ET_TZ`), never box-local.
2. `backtest/tools/exit_shape_parity_study.py` — `_live_data_creds()` probe replaces the dead
   hardcoded safe-1 key pick (unblocks the whole nightly WinnerAutopsy product).
3. Guards: `test_fill_latency_tz_2026_08_03.py`, `test_exit_parity_data_creds_2026_08_03.py`
   (8/9 RED pre-fix → 9/9 green post-fix) + de-flaked
   `test_fill_latency_2026_08_01.py::test_place_live_returns_submit_ts_before_the_broker_post`
   (hardcoded 15:00Z fixture vs real wall clock — only passed before 11:00 ET; now structural).
4. Nightly product manually restored for today (latency.json corrected; winner-autopsy 25
   winners; pain-ledger 164/165).

**Queued (needs heartbeat_core / checker edits — not touched today):**
- Make monday_verify ws1 + participation-daily + self-check `extra_exec`-aware (§2) — or add a
  top-level `extra_entered` marker to the tick row. Until then, treat "safe=0 participation"
  lines as suspect on any extra-setups day.
- Gamma_FreeManager ollama pick failure (exit 1 ×3 this afternoon).
- STATUS.md self-check dedupe (14 identical DEGRADED blocks today).
- Sweep for OTHER hardcoded-arm cred picks repo-wide (`get("safe-1"` grep found only this one
  in live-path instruments; a fuller audit of retired-arm references is cheap insurance).
- Verify the −$0.78 fee residue posts as activities rows (§1b); if not, reopen.
- Normalize safe-2 claim-file timestamps to tz-aware (cosmetic).
