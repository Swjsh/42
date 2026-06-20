# Stepped Profit-Lock Doctrine (T75 — DRAFT)

> **Created 2026-05-14T11:30 ET** from live 745C trade. J directive: "we need to be SAFE and not HOME RUN HITTERS to grow this account. but still ride the wave as much as we can."
> Today's trade: 745C runner reached +118% with v15 trailing 20%. Trail floor at +118% was 74¢ below current premium = $370 giveback on 5 contracts. J's instinct: tighten as % grows.
> **Status: DRAFT — weekend research project. NOT for live trading until A/B backtested vs current `trailing` mode.**

---

## The problem v15 trailing solves vs doesn't solve

| Mode | What it does | Failure mode |
|---|---|---|
| `fixed` (v14e default before T50) | Arms at +5%, sets fixed floor at +10% | Caps ride-the-ribbon at +10% — kills big-day capture |
| `trailing` (v15 LIVE) | 20% chandelier off HWM | At extreme gains (+100%+), the 20% trail gives back too much realized profit |
| **`stepped` (T75 PROPOSAL)** | Trail tightens with gain tier | Best of both — wide trail early (breathing room), tight late (lock secured gain) |

## The proposed stepped table

```python
STEPPED_RUNGS = [
    # (gain_pct_threshold, trail_pct_from_HWM)
    (0.00, 0.20),   # 0-50% gain: 20% trail (wide, lets it breathe)
    (0.50, 0.15),   # 50-100% gain: 15% trail
    (1.00, 0.10),   # 100-150% gain: 10% trail (tight)
    (1.50, 0.05),   # 150%+ gain: 5% trail (last leg lock)
]
```

### How it works on today's 745C trade

- Entry $1.67
- HWM $3.69 = +121% gain
- Current rung: 100-150% tier → **10% trail** (vs current 20%)
- Floor = $3.69 × 0.90 = $3.32 (vs current 20% floor = $2.95)
- **Difference: $185 better protection on 5 contracts**

### How it works on a chop day (e.g., 5/12)

- Entry $1.50, peak $1.80 (+20%)
- Current rung: 0-50% tier → **20% trail** (same as v15)
- Floor = $1.80 × 0.80 = $1.44
- Identical to v15 — no regression on small winners

### How it works on a moonshot (e.g., 4/29 J's 710P)

- Entry $0.94, peak $1.30 (+38%)
- Current rung: 0-50% → 20% trail → $1.04 floor
- 1.5x scale: $1.41 = +50% rung → 15% trail → $1.20 floor
- 2x scale: $1.88 = +100% rung → 10% trail → $1.69 floor
- v15 trailing: would hold at 80% off HWM throughout = $1.04 → $1.13 → $1.50
- **Stepped locks $190 MORE on the way up** than constant 20% trail.

---

## Implementation plan (~2 hours)

### Step 1: code (already shipped — verify)
`backtest/lib/simulator_real.py` has `STEPPED_RUNGS` constant + `_stepped_floor` helper (T50b Fire #14 5/13). Confirm:
- `mp.set_executable(pythonw.exe)` still works
- Default mode='fixed' for backward-compat
- New profit_lock_mode='stepped' threads through orchestrator

### Step 2: backtest A/B (weekend overnight grinder)
Use `backtest/autoresearch/v14_enhanced_pl_variants.py` framework. Add stepped mode to the test grid:
- A: current v15 trailing 20%
- B1-B4: stepped variants (tier breakpoints + trail pcts)

Metric:
- wide_pnl over 16mo
- top5_pct concentration
- per-J-anchor capture (must not regress 4/29, 5/04, 5/12)
- max drawdown
- **NEW: realized_giveback_pct** = (peak_unrealized - final_realized) / peak_unrealized. Measures how much of paper-gain we converted to realized. Stepped should win on this.

### Step 3: ratification (per OP 20)
- Walk-forward TRAIN/TEST per-month ratio ≥ 0.5
- 4-of-4 J anchors protected (4/29, 5/04, 5/12, 5/13)
- Concentration top5_pct ≤ 0.40
- Real-fills check on top-3 days

### Step 4: v16 ratification (Sunday)
- Bump `params.json#rule_version` to "v16"
- Update heartbeat.md `RULE_VERSION = "v16"`
- Update premarket.md `RULE_VERSION_EXPECTED = "v16"`
- v15 backup preserved at `heartbeat-v15-prod-backup.md`
- Add to CHANGELOG.md
- Add OP-23-style operating principle for stepped-PL invariants

---

## Honest risks

1. **Backtest regret bias.** Stepped will look great in hindsight on big-day-winner samples. On NEXT real moonshot, the 10% tight trail at +100% might cut the winner short of a +300% blow-off-top.
2. **Whipsaw risk.** Tight 10% trail at +100% gain on chop-day-with-fast-pullback gets clipped 80% of the time. Need to verify against the 4/29 dataset where premium often pumps and dumps within 5-10 bars.
3. **Live vs backtest fidelity.** Stepped needs HWM updates within the bar — Alpaca only gives EOD bar data live. The heartbeat ticks every 3 min so HWM update is rate-limited.
4. **Doctrine creep.** Adding tier breakpoints adds 4 new knobs to tune. Each tunable is a new failure mode.

## Alternative considered & rejected

**Tightening the global trail % from 20% to 12%.** Would help today's trade but would CUT short the 5/12 J trade where the runner needed 25% breathing room to ride through midday consolidation. Stepped is better because it adapts to the gain tier.

---

## Next steps

1. **Run backtest grinder** Saturday morning (`weekend-research-pipeline.ps1` task)
2. **Review scorecard Sunday** — if stepped wins ≥10% over trailing on capture + ≤5% regression on chop days → ratify
3. **Live first session Monday 5/18** as v16

---

## Today's lesson absorbed (LESSONS-LEARNED L34 candidate)

**At extreme gains (+100%+), constant-percentage trailing gives back too much realized profit.** Stepped trails that tighten with gain-tier are the right doctrine. Discovered live on 5/14 v15 first session 745C trade — J's instinct: "we need to tighten as % grows."

Encoded in: this spec, T50b `_stepped_floor` code (shipped), T75 weekend backtest queue.
