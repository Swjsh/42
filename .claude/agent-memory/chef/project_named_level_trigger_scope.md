---
name: named-level-trigger-scope
description: Scope map for the named-level bounce/rejection (RIBBON-LAG) trigger validation — detectors, real-fills harness, anchor-data gaps
metadata:
  type: project
---

Named-level bounce/rejection trigger (queue RIBBON-LAG-PRICE-STRUCTURE-TRIGGER + RANGE-SCALP-REGIME): counter-ribbon entry on a confirmed rejection/reclaim candle at an Active/Carry named level, ITM + tight target (anti-theta), outer-band only, hard cap 2-3/session.

**Why:** validates whether the engine can capture the two ribbon-lag misses — 2026-06-26 ~09:41 PML 728.50 reclaim (LONG, held: ribbon BEAR) and 2026-06-24 ~09:30-09:35 PMH 737.11 rejection (SHORT, missed: ribbon lag).

**How to apply:** three WATCH_ONLY detectors already exist (all `backtest/lib/watchers/`):
- `named_level_wick_bounce_watcher.py` (NLWB) — single-bar wick BELOW named support + close back ABOVE. **Ribbon gate MIXED/BULL — would NOT fire on the 06-26 BEAR-ribbon long as-is** (needs counter-ribbon relaxation). OP-21 real-fills FAILED on PDL proxy (WR 47.8%, both rescue paths closed) — but on ★★★ levels untested.
- `bearish_rejection_morning_watcher.py` — 09:35-10:55 ET, ribbon=BEAR (enter WITH flip), high within $0.50 of ★★★ resistance + close >=15c below. On 06-24 the 09:35 bar (H737.29, C736.36, 75c below PMH, bear candle) PASSES the rejection geometry — but only if ribbon already BEAR; the miss was ribbon LAG at 09:30.
- `named_level_second_test_watcher.py` — two-touch higher-low/lower-high, 09:45-14:30, 30-min cooldown, ★★+ via level_source.load_named_levels.

All three: `metadata.promotion_status="WATCH_ONLY"`, live gate 0/3, never actuate.

**Real-fills harness** = `backtest/lib/simulator_real.py::simulate_trade_real` (real OPRA bars, next-bar-open entry +$0.02 slip, `strike_offset` NEGATIVE=ITM; cap_equity/cap_params for L180 live-cap awareness). Driven exactly like vwap was via `backtest/autoresearch/mass_grind_vwap.py` (standalone detector -> per-signal `simulate_trade_real` -> `strategy_space_grind.metrics_for`; run `GAMMA_GRIND_WORKERS=8 backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_vwap`, `--smoke` for one cell). SINGLE process only (OPRA-cache deadlock).

**BLOCKING DATA GAP (key):** OPRA option-bar cache `backtest/data/options/` STOPS at 260618 (2026-06-18). 06-24 SPY 5m bars exist (`spy_5m_2025-05-19_2026-06-25.csv`) but its 0DTE contracts are NOT cached; 06-26 has NO SPY 5m bars yet AND no options. So real-fills on EITHER anchor cannot run until OPRA + SPY bars for 06-24/06-26 are fetched. A mass-grind today validates only the historical population through 06-18, not the two motivating anchors.

**VERDICT 2026-06-26 — BOTH SIDES REJECTED on real fills. Primitive CLOSED.**
- **SHORT** (rejected 2026-06-26, prior fire): killed three ways — `level-rejection-gate-01` RATIFIED (exact SHORT subset IS n=22 avg -$584/trade, production `block_level_rejection=true` blocks it); `level-quality-benchmark` 3,202 levels show respect 0.250 vs 0.255 DM-null + reaction 1.798 vs 1.807 null = NO reaction edge (C3/L143/L183); vol-gate anti-correlates. Candidate `2026-06-26-counter-ribbon-named-level-rejection-SHORT.md`.
- **LONG** (rejected 2026-06-26, this fire): built `backtest/autoresearch/_edgehunt_named_level_bounce.py` (fork of `_edgehunt_vwap_continuation`, byte-identical `simulate_trade_real` + null harness). STRUCTURAL-PROXY levels (PDH/PDL/PDC/PMH/PML — key-levels.json not archived; the BLOCKER above). Real OPRA 2025-01-02..2026-06-18, 365 days, 538 sigs (265 long). **12-cell LONG grid all lose: exp -$38..-$51/trade, OOS all neg, WR 36-46%, 0/6 positive quarters, 0/12 beat the random-entry null** (real -$38..-$50 vs null_max -$0.46..-$9.78 at same days/sides/times → level selection WORSE than random, C3/L183). Exit-hist: 167/253 PREMIUM_STOP + 71 RIBBON_FLIP_BACK = counter-ribbon fade run over by trend. Candidate `2026-06-26-counter-ribbon-named-level-bounce-LONG.md` (leaderboard #40).
- **DO NOT re-propose** counter-ribbon level bounce/rejection without NEW structure (e.g. premium-SELLING / spread, per find-direction-autonomously). Do NOT relax the NLWB BEAR-blocks ribbon gate — relaxing it makes the setup strictly worse. Theta note: ITM+tight is right for vwap WITH-trend continuation, irrelevant for a fade — it realizes the loss faster (premium-stop), doesn't rescue it.
- **Only way to revisit:** fetch OPRA+SPY 2026-06-19..06-26, proxy-test ONLY the 2 anchor days (off-chance the 2 specific ★★★ levels differ from the 365-day proxy population — but a -$38..-$50/trade proxy that loses to random does not promote).
- **RE-CONFIRMED HOLD 2026-06-26 (adversarial OP-22 re-verify):** all 5 ship gates FAIL. OOS neg (-$38.72 best cell), WF=null (no WF on a money-loser), 0/6 quarters, anchor UNTESTABLE (data gap unchanged — OPRA still 06-18, no anchor contracts), beats-null FAIL BOTH sides (LONG 0/12 vs null-MAX; SHORT respect 0.250<0.255 DM-null). Overtrade caps (2-3/sess, outer-band, confirmed-candle, no-re-entry, range-break stand-down) NOT implemented in any of the 3 detectors — nothing to "hold". SHORT promotion would REGRESS OP-16: flips ratified `block_level_rejection` true→false on Safe (WF=0.842, captures +$1,478 on 4/29 J-winner). ITM+tight does NOT survive theta (167/253 PREMIUM_STOP) — realizes the fade loss faster, doesn't rescue it. Verdict stands; primitive permanently closed pending NEW anchor real-fills.
