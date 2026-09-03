"""PREMARKET DRY-RUN for Monday June 1, 2026.
Reads Friday 5/29 close data, builds key levels, VIX context, and a tradeable bias hypothesis.
Writes to analysis/daily-brief/2026-06-01-premarket-dry-run.md so Gamma is oriented for open."""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import sniper_matrix as SM
from lib.ribbon import compute_ribbon, ribbon_at

DATA = REPO / "data"
OUT = REPO.parent / "analysis" / "daily-brief"
OUT.mkdir(parents=True, exist_ok=True)

spy_raw = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-05-29.csv")
spy_raw["timestamp_et"] = SM._to_et(spy_raw["timestamp_et"])

fri = dt.date(2026, 5, 29)
fri_bars = spy_raw[spy_raw["timestamp_et"].dt.date == fri].sort_values("timestamp_et")
rth = fri_bars[(fri_bars["timestamp_et"].dt.time >= dt.time(9,30)) &
               (fri_bars["timestamp_et"].dt.time < dt.time(16,0))]

pdh = float(rth["high"].max())
pdl = float(rth["low"].min())
pdc = float(rth.iloc[-1]["close"])
pdo = float(rth.iloc[0]["open"])

# Ribbon at Friday close
all_rth = spy_raw[(spy_raw["timestamp_et"].dt.time >= dt.time(9,30)) &
                  (spy_raw["timestamp_et"].dt.time < dt.time(16,0))].reset_index(drop=True)
ribbon = compute_ribbon(all_rth["close"])
last_idx = len(all_rth) - 1
last_ribbon = ribbon_at(ribbon, last_idx)

# VIX proxy from our file
vix_raw = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-05-29.csv")
vix_raw["timestamp_et"] = SM._to_et(vix_raw["timestamp_et"])
vix_fri = vix_raw[vix_raw["timestamp_et"].dt.date == fri]
vix_fri_rth = vix_fri[(vix_fri["timestamp_et"].dt.time >= dt.time(9,30)) &
                      (vix_fri["timestamp_et"].dt.time < dt.time(16,0))]
vix_close = float(vix_fri_rth.iloc[-1]["close"]) if len(vix_fri_rth) else 15.0
vix_regime = "LOW" if vix_close < 15 else "MID" if vix_close <= 22 else "HIGH"
bull_eligible = vix_close < 17.20

# Prior week range
week_bars = spy_raw[spy_raw["timestamp_et"].dt.date.isin([dt.date(2026,5,26),dt.date(2026,5,27),
                    dt.date(2026,5,28),dt.date(2026,5,29)])]
week_high = float(week_bars["high"].max())
week_low = float(week_bars["low"].min())

lines = [
    "# Premarket Dry-Run — Monday June 1, 2026",
    "",
    "> Generated autonomously 2026-05-31 from verified Alpaca SIP data. VIX is a VIXY proxy.",
    "> This is a simulation of what Gamma_Premarket will produce at 08:30 ET Monday.",
    "",
    "## Price Context (from Friday May 29 close)",
    "",
    f"| Level | Price | Type |",
    f"|---|---|---|",
    f"| Friday RTH High | {pdh:.2f} | PDH (resistance) |",
    f"| Friday Close | {pdc:.2f} | PDC |",
    f"| Friday Open | {pdo:.2f} | — |",
    f"| Friday RTH Low | {pdl:.2f} | PDL (support) |",
    f"| Week High | {week_high:.2f} | 4-day range top |",
    f"| Week Low | {week_low:.2f} | 4-day range bottom |",
    f"| Round number | 755.00 | Psychological |",
    f"| Round number | 750.00 | Psychological (week low area) |",
    "",
    "## Ribbon (Friday close)",
    f"Stack: **{last_ribbon.stack if last_ribbon else 'UNKNOWN'}**  ",
    f"Fast: {last_ribbon.fast:.2f} | Pivot: {last_ribbon.pivot:.2f} | Slow: {last_ribbon.slow:.2f}  " if last_ribbon else "",
    f"Spread: {last_ribbon.spread_cents:.0f}¢" if last_ribbon else "",
    "",
    "## VIX Context (Friday close proxy)",
    f"VIX proxy close: **{vix_close:.2f}** ({vix_regime} regime)  ",
    f"Bull eligible (VIX < 17.20): **{'YES' if bull_eligible else 'NO'}**  ",
    f"Bear eligible (VIX > 17.30 rising): **NO** (VIX comfortably below threshold)",
    "",
    "## Monday June 1 Macro Calendar",
    "- **NO PRE-MARKET HIGH-IMPACT DATA** — clean open",
    "- ISM Manufacturing: **JUNE 2** 10:00 ET (not today)",
    "- NFP: June 5. FOMC: June 16-17.",
    "- Monday June 1 is a FREE session — no macro blocks on the tape.",
    "",
    "## Engine Status",
    "- Both accounts FLAT, 0/3 PDT used (reset), ACTIVE",
    "- Safe: $747.11 | Bold: $1,535.83",
    "- VIX in MID regime: BEARISH_REJECTION eligible if VIX >17.30 rising (currently NOT)",
    "- BULLISH_RECLAIM eligible (VIX <17.20) — DRAFT status, needs 3 live J wins",
    "",
    "## Ribbon Gate Status (pending ratification)",
    f"The RIBBON_MOMENTUM_GATE (WF=3.74, RATIFICATION_READY) is LIVE in orchestrator.py but",
    f"OFF by default until J ratifies. Production runs standard v15.2 rules.",
    "",
    "## Falsifiable Hypotheses for June 1",
    "",
    "**Primary (base case — SPY near highs, low VIX, no catalysts):**",
    f"SPY opens near {pdc:.2f} and grinds higher in the first 90 minutes. The ribbon at open",
    f"is likely {'BULL' if last_ribbon and last_ribbon.stack == 'BULL' else 'mixed'}-stacked from",
    f"Friday's {pdc:.2f} close. First meaningful test: whether Friday's high {pdh:.2f} acts as resistance.",
    f"Invalidation: gap below {pdl:.2f} (Friday low) on open OR VIX spikes above 17.30.",
    "",
    "**Bear setup condition (BEARISH_REJECTION would fire):**",
    f"If SPY rallies to {pdh:.2f}+ and fails with a rejection candle, ribbon BEAR-stacks,",
    f"VIX ticks above 17.30 rising → bearish rejection setup. Level: {pdh:.2f} area.",
    "RIBBON_GATE qualification: need spread widening ≥5¢, stack fresh ≤20 bars.",
    "",
    "**Bull setup condition (BULLISH_RECLAIM — DRAFT, monitor only):**",
    f"If SPY dips to {pdl:.2f}–755.00 and reclaims with ribbon flip to BULL → bull reclaim.",
    "Not live in production (DRAFT status, OP-16 scope lock). Heartbeat will log but not trade.",
    "",
    "## What to watch in the first 15 minutes",
    f"1. **Gap direction from {pdc:.2f}**: >+0.5% = gap-and-go setup for BULLISH_RECLAIM",
    f"2. **Ribbon spread at 09:40**: widening from open = trend forming; compressing = chop day",
    f"3. **PDH {pdh:.2f} hold vs break**: if SPY pops above and holds, first support = {pdc:.2f}",
    f"4. **VIX at open**: any move toward 17.30 = bear setup window opens",
    "",
    "## RIBBON_GATE pre-trade checklist (for manual reference)",
    "Before entering ANY setup today, check:",
    "- [ ] Ribbon spread widened ≥5¢ in last 15 minutes (3 bars)?",
    "- [ ] Ribbon has been stacked ≤20 bars in current direction?",
    "- [ ] If 11:30-14:00 ET: does setup have ≥2 triggers or a level_rejection?",
    "If all three: ENGINE ENTERS. If any fail: skip or wait for next setup.",
]

(OUT / "2026-06-01-premarket-dry-run.md").write_text("\n".join(lines), encoding="utf-8")
print("wrote 2026-06-01-premarket-dry-run.md")
print(f"PDH={pdh:.2f} PDL={pdl:.2f} PDC={pdc:.2f} ribbon={last_ribbon.stack if last_ribbon else '?'} VIX={vix_close:.2f}")
