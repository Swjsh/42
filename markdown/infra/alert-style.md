# Discord Alert Style — Phone-First, Bulleted, Emoji-Tagged

> Per J's 2026-05-09 PM ask: "concise and bulleted and emojis when appropriate. Easy to read at a glance from my phone. Don't spam me."

## Rules

1. **Lead with an emoji + 4-word headline.** Never bury the lede.
2. **Body: max 5 bullets.** Each bullet ≤ 60 chars.
3. **Numbers in bold.** Make them scannable.
4. **One alert per real change.** Watcher milestones MUST debounce — never 4 in 4 minutes.
5. **No prose paragraphs.** Lists or tables only.
6. **Cite filenames in code ticks** so J can copy them on phone.

## Emoji legend

- 🟢 / 🔴 — go / stop, healthy / failed
- ⚠️ — warning (drift, near-miss, edge case)
- 🚨 — critical (kill-switch, position mismatch)
- 📊 — research / backtest result
- ✅ — done, gate passed, milestone hit
- 💰 — P&L, money
- ⏱️ — schedule, ETA, time-sensitive
- 🔧 — fix / repair / restart
- 🤖 — autonomous action taken
- 📥 — message received from J
- 📤 — message sent to J
- 🛑 — refuse / blocked

## Templates

### v15 ratification ready
```
📊 v15 ready
- 🏆 winner: seed **6** (val_pnl **+$2295**)
- ✅ robust 4/5 windows
- 📁 `analysis/recommendations/v15.json`
- ⏱️ awaits your review
```

### Phase transition
```
✅ PHASE 0 done (60/60)
- 33 robust candidates
- top: seed 6 (**+$2295**)
- ETA PHASE 4: ~10 min
```

### Critical alert
```
🚨 KILL-SWITCH TRIPPED
- today P&L: **-$48** (-50%)
- no new entries this session
- file: `automation/state/kill-switch`
```

### Build complete
```
🤖 wired #4 parallel EOD
- swap pending Mon test
- run: `setup\scripts\test-multi-agent-gamma.ps1`
```

### Process restart
```
🔧 discord-bridge restarted
- pid: 31448
- last alive: 4m ago
```

## Anti-patterns (don't do)

- ❌ Multi-paragraph status reports
- ❌ Restating the same milestone 4 times
- ❌ "Just FYI..." kind of fluff
- ❌ Writing markdown headers (####) inside Discord — they don't render the same
- ❌ Sending status when nothing changed since last alert
