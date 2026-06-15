# Loop v2 — adaptive cadence + context continuity

> Built 2026-05-05 after grading v1 at B+/B (cadence, continuity). v1 ran on a fixed 180s ScheduleWakeup tick with no state persistence outside the conversation context. v2 fixes both with minimal added complexity.
>
> **Two changes. That's it.** Adaptive cadence (mode-driven) + a single state file (`loop-state.json`) read at every wake-up.

---

## Why v1 wasn't good enough

| Problem | Symptom | Cost |
|---|---|---|
| **Fixed 180s tick** | Burns cache and tokens during dead market hours; too slow when a setup is developing | ~17 ticks today, 3 of them on a stalled bullish range — wasteful |
| **State lives only in conversation context** | After context compaction (mid-session today), state had to be rehydrated from a session summary | Fragile — long sessions risk losing the working memory |
| **No bar-transition awareness** | Some ticks fired mid-bar, returning identical data to the prior tick | Wasted reads |

v1 worked. v2 makes it cheaper and tougher.

---

## Cadence v2 — three modes, one rule each

The loop has three cadence modes. The mode is computed at the *end* of every tick from the filter snapshot. The next `ScheduleWakeup.delaySeconds` comes from the mode.

| Mode | Tick interval | When it activates | Why |
|---|---|---|---|
| **HOT** | **120s** | ≥ 3 of 5 entry filters passing simultaneously, OR ribbon spread < 35c, OR 2+ consecutive red bars (for puts) / green bars (for calls) closing in a row | Setup is developing — need to catch the trigger bar before it closes |
| **BASE** | **180s** | Anything not HOT or COOL | Normal market scanning |
| **COOL** | **270s** | Ribbon spread > 60c AND VIX flat for last 3 ticks AND no filter score change for last 3 ticks | Market is one-directional and quiet — no setup likely, conserve cache |

**Hard rules:**
- All three modes stay **inside the 5-min cache TTL** (max 270s). Cache miss = ~5x token cost on the next tick. Worth avoiding except for the EOD jump.
- **No 300s ticks ever** during market hours. It's the worst-of-both: cache miss without amortization.
- The EOD wake-up (15:30 → 15:50) is the *only* allowed cache miss, since it's a single 1320s sleep with nothing to scan in between.

**Skip-the-bar rule:** at every wake-up, compare `last_bar_timestamp` from `loop-state.json` to the current latest bar. If equal AND the current bar's volume hasn't grown by ≥ 30%, skip the SPY/VIX read and reschedule another tick at 60s. Saves a full read cycle when we wake mid-bar and nothing has changed.

**Mode transition log:** every mode change writes a one-line entry to `loop-state.json#mode_transitions[]`. Helps post-session analysis: did we go HOT correctly when the 2:30 PM setup was developing?

---

## Continuity v2 — `loop-state.json`

Single JSON file. **Read at the start of every tick. Written ONLY when state actually changes.** Most ticks change nothing — those ticks skip the write. This keeps disk writes proportional to information density, not tick count.

### Write triggers (write only when ≥1 of these is true)

| Trigger | Why |
|---|---|
| `last_bar_timestamp` changed (new bar appeared) | New data is the only thing worth persisting |
| `current_mode` changed | Mode transitions are decision points |
| Filter score increased OR developing setup escalated | We're approaching an entry — capture it |
| Filter score crossed below 2 of 5 after being ≥3 | Setup deflated — capture the failure point |
| Setup placed (paper order fired) | Always |
| Setup blocked (a setup *would* have fired but failed a filter) | Capture for forensics |
| Session boundary (start, EOD, kill-switch) | Always |

**Steady-state cost:** during chop where price drifts and filters stay constant, the loop-state file is read every tick but **not written**. Today (5/5) had ~17 ticks but would have had ~7-9 writes under v2 — a ~50% reduction.

**Long-term cost:** ~250 trading days × ~10 writes/day = ~2,500 writes/year on a single ~3KB JSON file. Negligible disk wear (modern SSDs handle 10⁶+ rewrites per cell). Token cost is bounded by the file size, not the write count.

### Schema v2 (lean — current state only, no history bloat)

```json
{
  "schema_version": 2,
  "session_id": "2026-05-05",
  "last_change_at": "2026-05-05T15:28:00-04:00",
  "last_change_reason": "session_end",
  "last_bar_timestamp": 1778009100,
  "current_mode": "BASE",
  "writes_today": 8,
  "ticks_today": 17,

  "spy": {
    "last": 724.85,
    "session_high": 725.04,
    "session_low": 721.49
  },

  "vix": {
    "last": 17.28,
    "session_high": 17.31,
    "session_low": 17.20
  },

  "ribbon": {
    "fast": 724.66,
    "pivot": 724.37,
    "slow": 724.12,
    "spread_cents": 54,
    "stack": "bullish"
  },

  "last_filter_score": {
    "passing": 1,
    "blockers": ["ribbon_stack", "vix", "bar_green", "vol_threshold"]
  },

  "developing_setup": null,
  "key_levels_active_ids": ["OgC9Tb", "IbZoGL", "FI9ZqW", "Ri3dBG", "Y7U2Gm", "s7cwi9"]
}
```

**What's NOT in the state file (deliberately):**
- Filter history → goes to journal `journal/{date}.md` as inline tick log when notable
- Mode transition history → goes to journal at EOD as a single roll-up
- Bar-by-bar OHLCV → already on the chart, never duplicate it on disk
- Long narrative summaries → that's the journal's job

The state file is **resume-ability only**. Anything richer lives in the journal where it can be read by humans without parsing JSON.

### Read protocol (every wake-up)

1. **First action of every tick:** read `loop-state.json`.
2. If `last_tick_at` is < 6 minutes ago → **continuing session**, use state as working memory.
3. If `last_tick_at` is > 6 minutes ago → **session resumed after compaction or break**, read state to rehydrate, then check market state with fresh chart reads.
4. If file doesn't exist → **first tick of session**, initialize from `today-bias.json` and the first chart read.

### Write protocol (every tick)

After the filter evaluation but before scheduling the next wake-up:
1. Update `spy`, `vix`, `ribbon` with current readings.
2. Append the latest filter score to `filter_history` (cap at last 20 entries — drop oldest).
3. If mode changed this tick, append to `mode_transitions[]`.
4. If a developing setup is escalating (filter score growing tick-over-tick), set `developing_setup` to a brief object; clear it when filters drop again.
5. Compute next mode → write to `current_mode`.
6. Pass next mode's interval to `ScheduleWakeup.delaySeconds`.

**The whole write is one atomic file overwrite.** No partial writes, no locks. If a tick crashes mid-write, the worst case is the previous tick's state is still readable — better than corrupted state.

---

## What this enables

| v1 → v2 | Improvement |
|---|---|
| Fixed 180s | Adaptive 120/180/270s based on market state — fewer wake-ups when dead, more when hot |
| State in context only | State on disk, survives compaction, resumes cleanly |
| No bar-transition logic | Skip rule prevents wasted reads on duplicate bars |
| Manual session restart from summary | Future sessions read `loop-state.json` and pick up |

**What it does NOT do** (deliberately):
- No persistent agent process. Loop is still scheduled wake-ups.
- No retry/queue logic. Failed reads still skip the tick (existing behavior).
- No multi-symbol tracking. SPY-only, by design.
- No backtesting / replay. Live only.

The complexity ceiling is one extra JSON file and one mode-selector function. Everything else stays the same.

---

## Implementation order (when J says go)

1. **Write the schema validator** — small JSON schema check at file load. ~20 lines. Catches silent corruption.
2. **Bake the mode selector into the heartbeat prompt** — three rules, three intervals. Document inline.
3. **Test on a Monday session** — instrument the mode transitions, verify the tick budget drops vs today's 17.
4. **Backfill from EOD review** — at 15:50 EOD, the loop writes `mode_transitions` summary into the journal automatically.

No dependencies, no new MCPs, no new infra. Adds one file, one function. Lean.

---

## Open questions

- Should COOL mode be allowed pre-noon? Morning markets are choppy and "directional + quiet" is rare. Probably yes-but-rare. Watch the data.
- Should the 60c COOL threshold scale with VIX? At VIX 25 the absolute spread is meaningless. Leave fixed for now; revisit at VIX > 22.
- HOT mode 120s — is that tight enough? Today's developing setup (2:30–2:41 PM) had 3 ticks across 11 minutes. At 120s we'd have 5–6 ticks in the same window. Probably right. Validate live.
