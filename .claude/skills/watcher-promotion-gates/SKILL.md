# Skill: watcher-promotion-gates

Print a one-screen OP-21 promotion gate status for all 13 registered watchers.
Shows Historical / Walk-Forward / Real-Fills / Live gates with live observation counts
toward each watcher's promotion goal.

> **Source:** `backtest/autoresearch/watcher_promotion_gates.py`
>
> Per OP-21 (Watch-First Promotion Path): every new strategy starts WATCH-ONLY.
> This dashboard tracks progress toward promotion for each watcher in the fleet.

---

## When to invoke

- **Morning briefing** — J asks "which watchers are closest to promotion?"
- **After any live trading session** — check if new live wins were recorded
- **After watcher.py edits** — verify registry is up to date
- **Sunday weekly review** — Treasurer reads this before sizing decisions
- **Before promoting any watcher to heartbeat.md** — confirm all gates are Y

---

## Quick invoke

```powershell
cd C:\Users\jackw\Desktop\42
python backtest/autoresearch/watcher_promotion_gates.py
```

JSON output (for machine consumers):
```powershell
python backtest/autoresearch/watcher_promotion_gates.py --json
```

JSON is written to: `automation/state/watcher-promotion-snapshot.json`

---

## Output interpretation

```
  WATCHER                             STATUS         H WF RF LIVE     READY
  ----------------------------------- -------------- - -- -- -------- -----
  HEAD_AND_SHOULDERS_BEAR             WATCH_STABLE   Y Y  Y  0/3
```

| Column | Meaning |
|--------|---------|
| `H` | Historical gate: Y=WR≥50% N=pass, N=below 50% |
| `WF` | Walk-forward OOS gate: Y=STABLE or IMPROVED, N=DEGRADED |
| `RF` | Real-fills gate: Y=live option P&L WR≥50%, N=fails |
| `LIVE` | `graded_live_wins / needed`. Counts watcher fires where `bar_timestamp_et >= 2026-05-18` AND `would_be_pnl > 0`. |
| `READY` | All 4 gates Y + live_wins >= needed → "READY" |

Status codes:
- `WATCH_STABLE` — all tech gates passed; accumulating live observations
- `WATCH_FRAGILE` — WF or RF gate fails; higher live bar or VIX-regime restriction needed
- `LIVE_ONLY` — no historical possible (no key-levels archive); purely live accumulation
- `OBSERVE_ONLY` — no promotion path (superseded or WR < 50% floor)

---

## Gate thresholds per watcher

| Watcher | H gate | WF gate | RF gate | Live needed |
|---------|--------|---------|---------|-------------|
| hs_bear | WR=55.7% N=185 | +4.0pp STABLE | WR=73.7% N=19 | 3 |
| fbw_morning_mid | WR=74.3% N=35 | +10.1pp STABLE | WR=74.3% N=35 | 3 |
| db_base_quiet | WR=63.9% N=122 | +1.2pp STABLE | WR=63.9% N=122 | 3 |
| nlwb | WR=71.3% N=157 | -7.9pp (PDL proxy) | WR=67.0% N=25 | 3 |
| db_morning_low_vol | WR=67.9% N=109 | **DEGRADED -15.2pp** | WR=67.9% N=109 | 5 (fragile bar) |
| lbfs | VIX>=20 100% N=4 | too thin | not run | 15 VIX-gated |
| bral | WR=75.0% N=4 | too thin | not run | 3 |
| close_ceiling_fade | LIVE_ONLY | LIVE_ONLY | after N>=20 | 20 |
| floor_hold_bounce | LIVE_ONLY | LIVE_ONLY | after N>=20 | 20 |
| momentum_accel_highvol | WR=59.6% N=47 | +6.6pp | **WR=42.9% FAIL** | 15 VIX>=25 |
| hs_near_named | **WR=46.2% FAIL** | not run | not run | OBSERVE_ONLY |
| orb_watcher | medium-conf proxy | too thin | not run | 3 |
| v14_enhanced | prod covers it | STABLE | not separately run | OBSERVE_ONLY |

---

## Adding a watcher to the registry

Edit `WATCHER_REGISTRY` in `backtest/autoresearch/watcher_promotion_gates.py`.
Required fields:
```python
{
    "watcher_name": "<name matching watcher_name field in watcher-observations.jsonl>",
    "display_name": "DISPLAY_NAME_FOR_TABLE",
    "direction": "long|short|mixed",
    "historical_n": int | None,
    "historical_wr": float | None,
    "historical_gate": True | False | None,
    "wf_gate": True | False | None,
    "wf_note": "evidence string",
    "real_fills_gate": True | False | None,
    "real_fills_wr": float | None,
    "real_fills_n": int | None,
    "real_fills_note": "evidence string",
    "live_wins_needed": int | None,
    "overall_status": "WATCH_STABLE|WATCH_FRAGILE|LIVE_ONLY|OBSERVE_ONLY",
    "notes": "one-line notes",
}
```

The `watcher_name` MUST match the `watcher_name` field emitted by the watcher's `WatcherSignal`
object (e.g., from `WatcherSignal(watcher_name="hs_bear", ...)`). Run the script after adding
to verify live counts appear correctly.

---

## Key bug: observed_at vs bar_timestamp_et

The `watcher-observations.jsonl` has two timestamps:
- `observed_at`: when the replay task ran (may be historical replay from 2026-05-10 onward)
- `bar_timestamp_et`: the actual trading bar that triggered the signal

Only `bar_timestamp_et >= LIVE_CUTOFF (2026-05-18)` counts as a live observation.
Using `observed_at` inflates counts because historical replay creates entries with
recent `observed_at` but historical `bar_timestamp_et`. Fixed in the script — always
use `bar_timestamp_et[:10]` for the cutoff comparison.

---

## Output files

- Console table (run any time)
- `automation/state/watcher-promotion-snapshot.json` (machine-readable, written on every run)

---

## Cross-references

- **OP-21** in CLAUDE.md — Watch-First Promotion Path doctrine
- **SKILLS-CATALOG.md** — row for `watcher-promotion-gates`
- **`backtest/lib/watchers/`** — all 20 registered watcher modules
- **`automation/state/watcher-observations.jsonl`** — observation log consumed by this tool
- **`backtest/autoresearch/watcher_replay.py`** — generates historical observations
- **`backtest/autoresearch/watcher_live.py`** — generates live observations
