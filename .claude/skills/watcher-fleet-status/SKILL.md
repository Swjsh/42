# Skill: watcher-fleet-status

Audit the 8 production watchers (orb / bull / v14e / sniper / vwap / odf / pff / pinfade) for silent-failure patterns. Returns per-watcher observation count over the last N days + flags any watcher silent for ≥3 consecutive days during market hours.

> Per `markdown/research/T80-ORB-BULL-REGRESSION.md` — silent zero-observation across N days = silent failure (the only true failure mode per OP-25). Pre-T82 fix, 4-of-8 watchers were silent for 4+ days without anyone noticing because everything reported "success."

---

## When to invoke

- Daily, automatically — hooks into EOD via `audit-silent-watcher-days.ps1`
- Manually when J asks "are the watchers firing?"
- After ANY change to `backtest/lib/watchers/runner.py` or `backtest/autoresearch/watcher_live.py`
- After a trading day with NO `watcher-observations.jsonl` entries (suspicious silence)
- When investigating a specific J-trade-day to see if any watcher caught J's setup

---

## Steps

1. **Quick observation count (last 14 days):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\audit-silent-watcher-days.ps1"
```

Output: per-watcher observation count by date.

2. **Deep dive on today's bars (if any watcher silent):**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python autoresearch\_smoke_watchers.py
```

This calls each watcher's detector function DIRECTLY on today's bars (bypassing the runner.py confidence filter). Tells you whether the detector ITSELF returned None vs whether the runner suppressed a low-confidence signal.

3. **If a watcher silent on a date that should have had fires (e.g., a big-move day):**

```powershell
# For ORB silence: re-run with the T82 warmup pattern
cd C:\Users\jackw\Desktop\42\backtest
python autoresearch\t82_orb_warmup_test.py
```

This 3-scenario test discriminates: stateful-state-machine bug vs detector bug vs filter bug.

4. **Interpret the verdict:**

| Pattern | Verdict | Action |
|---------|---------|--------|
| All watchers fire ≥1×/day except weekends | ✅ Healthy | No action |
| 1 watcher silent 1 day | 🟡 Likely no eligible setup | Check `t80_orb_bull_regression.py` for that day to confirm |
| 1 watcher silent 3+ consecutive days | 🟡 Investigate detector | Run direct-call test |
| Multiple watchers silent same day(s) | 🔴 Live-fire path bug | Run `t48_sniper_513_diag.py` pattern |
| ALL watchers silent for a session | 🔴 watcher_live.py broken | Check `watcher-live-diag.jsonl` for `signals_emitted=0` pattern + bar V=0 in-progress bug (T76) |

---

## Known false-silent patterns (NOT bugs)

- **Sniper silent EVER (since 2026-05-14):** intentionally retired by J directive. See `lib/watchers/runner.py` lines 154-168.
- **Pinfade silent EVER (since 2026-05-10):** disabled by `_PINFADE_ENABLED = False` flag (16-month verdict 1.9% WR / -$7.9K net).
- **VWAP silent on gap-and-go days:** correct skip — price never returns to VWAP within $0.10 proximity. Not a bug. See `_smoke_vwap_diag.py` for per-filter chokepoint trace.
- **ODF silent on trending days:** correct skip — no drive-then-fade pattern. Fires on chop mornings.
- **PFF silent if premarket level held all day:** correct skip — first-3-RTH-bars window only.

---

## Stateful watcher list (warmup needed in watcher_live.py)

Per T82 + T82b audits:

| Watcher | Stateful? | Warmup status |
|---------|-----------|---------------|
| ORB | YES (`_orb_state` HOD/LOD ratchet) | ✅ T82 shipped |
| ODF | YES (`_odf_state` ratchet + stall) | ✅ T82b shipped |
| PFF | NO | n/a |
| VWAP | NO | n/a |
| V14E | NO | n/a |
| Bullish | NO | n/a |
| Pinfade | DISABLED | n/a |
| Sniper | RETIRED | n/a |

**2 of 2 stateful detectors covered by warmup.** If a NEW stateful watcher is added, the audit must extend `watcher_live.py` T82 warmup loop (see SKILLS-CATALOG.md adding-new-skill protocol).

---

## Output files

- `automation/state/watcher-observations.jsonl` — append-only log of every fired observation (since 2026-04-23)
- `automation/state/watcher-live-diag.jsonl` — per-fire diag trail (signals_emitted + bar values + sniper_5d_high), shipped Fire #20 2026-05-14
- `markdown/research/T80-ORB-BULL-REGRESSION.md` — root-cause doc for the stateful-watcher silent-failure pattern

---

## Cross-references

- **T80 root cause doc:** `markdown/research/T80-ORB-BULL-REGRESSION.md`
- **T82 fix doc:** mentioned in CLAUDE.md OP-25 lessons absorbed 2026-05-14 evening
- **Direct watcher tests:** `backtest/autoresearch/_smoke_watchers.py` + `_smoke_vwap_diag.py`
- **CLAUDE.md OP-25 lesson:** "Stateful watchers + per-tick fresh-process scheduled tasks = silent zero observations"
