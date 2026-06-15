# MONDAY 2026-05-11 — Morning Playbook

> What to do when you wake up Monday. 1-page action list.
> Generated 2026-05-10 night by Gamma after weekend grind.

---

## 1. BREW COFFEE → READ THESE 3 FILES IN ORDER

1. **`docs/STATUS.md`** ← daily auto-generated 08:00 ET, the freshest snapshot
2. **`docs/MONDAY-READY-CHECKLIST.md`** ← all 6 ratification gates pass/fail
3. **`docs/WATCHER-REPORT.md`** ← yesterday's signals + rolling 7d/30d watcher P&L

That's all. ~5 min total reading.

---

## 2. THE ONE DECISION

**Ratify v15-final or not.** Per CLAUDE.md rule 9.

The candidate is in `analysis/recommendations/v15-final.json`. Summary:

| Metric | Value | vs Baseline | Per OP 20 disclosure |
|---|---|---|---|
| 4/29 BEAT-J | $655 | +$283 | requires bear setup like 4/29 morning |
| 5/04 BEAT-J | $2,418 | $0 (held) | only fires on confluence days |
| edge_capture | $3,056 | +$287 (198% of J's $1,542) | J-edge primary, your trades |
| wide_pnl (16mo) | $19,627 | +$15,972 (+437%) | requires $25K+ account; $1K paper realizes ~14% |
| top5_pct | 120% | down from 456% | concentration acceptable |
| positive_quarters | 4/6 | — | LOSES Q3+Q4 2025 (low-vol) |
| Walk-forward OOS | $2,657 (4.3mo of 2026) | per-month rate consistent | OOS-validated |

**To ratify:** reply `yes` on Discord OR edit `automation/state/params.json`:

```diff
- "tp1_premium_pct": 0.30,
+ "tp1_premium_pct": 0.75,
- "premium_stop_pct_bear": -0.08,
+ "premium_stop_pct_bear": -0.20,
- "runner_target_premium_pct": 3.0,
+ "runner_target_premium_pct": 2.0,
- "tp1_qty_fraction": 0.667,
+ "tp1_qty_fraction": 0.5,
- "min_triggers_bear": 2,
+ "min_triggers_bear": 1,
- "strike_offset_bear": -2,
+ "strike_offset_bear": 0,
```

Plus orchestrator-side per-quality knobs are baked into `lib/orchestrator.py` (already shipped).

**To reject:** do nothing. v14 production stays active, Monday trades on it.

---

## 3. WHAT'S ALREADY AUTOMATED (no action needed from you)

### Today (Monday 2026-05-11)
| Time | Task | Action |
|---|---|---|
| 08:00 | Gamma_LaunchTV | TradingView starts with CDP |
| 08:00 | Gamma_DailyStatus | STATUS.md regenerates |
| 08:30 | Gamma_Premarket | Levels + today-bias + falsifiable hypothesis |
| 08:30 | Gamma_WatcherMorningReport | WATCHER-REPORT.md regenerates |
| 09:30+ | Gamma_Heartbeat | every 3 min, scans setups, places trades if v15-final ratified |
| 09:30+ | Gamma_WatcherLive | every 5 min, runs all watchers, Discord pings on medium signals |
| 09:30+ | Gamma_GrinderMonitor | hourly, restarts dead grinders |
| 09:30+ | Gamma_SelfAudit | hourly, RED Discord ping on issues |
| 09:30+ | Gamma_DiscordResponder | every 5 min, replies to your Discord messages |
| 15:55 | Gamma_EodFlatten | safety net flatten any open 0DTE |
| 16:00 | Gamma_EodSummary | EOD reflection + backtest sync |
| 16:30 | Gamma_DailyReview | predictions vs actual + tomorrow's levels |
| 17:00 | Gamma_WatcherReplay | replay+grade rolling 30 days |

20 Gamma_* tasks total, all Ready.

---

## 4. WATCHERS — WHAT TO LOOK FOR ON DISCORD

You'll get Discord pings during market hours when any watcher fires:

🔴 **HIGH** confidence signal — both filters confirming
🟡 **MEDIUM** confidence — one filter confirming (the +EV slice — see WATCHER-REPORT)
🟢 **LOW** suppressed by filter (won't ping)

Format:
```
🟡 orb_watcher: ORB_RETEST_LONG (medium)
entry=$732.50 stop=$731.30 tp1=$734.10 runner=$735.70
reason: ORH 731.18 broken at 731.55, retested at 731.20 held + green close 731.62, bullish SMA, vol=high
```

**Watchers are LOG-ONLY.** They don't trade. They build evidence for OP 21 promotion (3+ live wins required + 16-month positive expectancy).

---

## 5. KNOWN LIMITATIONS (per OP 20 disclosure)

1. **Strategy is regime-fragile.** Loses money in low-vol summer/fall (Q3+Q4 2025 = -$1,500/quarter). Currently in Q2 2026 high-vol regime — strategy works HERE.
2. **Account size matters.** $1K paper account = qty cap to 4 contracts = 14% of headline P&L. To realize the full $19K/16mo wide_pnl, need $25K+ equity.
3. **5/01 BS-sim discrepancy.** Engine takes the 13:35 trendline bar but BS pricing + ribbon data divergence = -$22 vs J's +$470. Known limitation; needs TV-aligned data feed or new trigger to fix.
4. **PIN-FADE disabled.** 16-month backfill showed 1.9% WR / -$7,900 net. Needs ground-up rebuild of theta-grading + classifier.
5. **Bullish in DRAFT per OP 16.** Watcher logging only; needs 3+ live wins before live trading.

---

## 6. IF SOMETHING BREAKS — DEBUG ORDER

1. Read `docs/HEALTH.md` (auto-updated hourly) — RED gates show what's wrong
2. Check `automation/state/self-audit.json` for component-by-component status
3. Check `automation/state/discord-bridge.pid` exists and PID alive (`Get-Process -Id ...`)
4. Discord me — Gamma_DiscordResponder will reply within 5 min
5. Look at `automation/state/logs/` for component logs

---

## 7. KEY KNOWLEDGE TRANSFER DOCS (for future reference)

- **`docs/BACKTESTING-PLAYBOOK.md`** — comprehensive transferable playbook, 10 sections
- **`docs/LESSONS-LEARNED.md`** — 22 anti-patterns with code-level fixes
- **`docs/FUTURE-IMPROVEMENTS.md`** — queued improvements (don't distract)
- **`CLAUDE.md`** — soul file with all 22 operating principles

---

**TL;DR:** Read 3 files, decide on ratification, then go about your day. Engine handles the rest.
