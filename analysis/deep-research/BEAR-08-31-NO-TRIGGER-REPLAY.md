# BEAR-08-31-HIGH-SCORE-NO-TRIGGER-REPLAY

**Filed:** 2026-09-03, from queue item `BEAR-08-31-HIGH-SCORE-NO-TRIGGER-REPLAY` (MED, freeze-compatible replay+report only). Investigated 2026-09-03 (Sonnet, replay-only — no filter/trigger/rule changes made).

**Scope note on method:** the queue item asked for a replay via `backtest/tools/historical_replay.py` or a "sole-blocker miner's per-tick path." Neither is the right tool here — `historical_replay.py` is an *exit-layer* replay over already-filled trades (re-walks exit_manager on known fills; explicitly cannot reconstruct new signals per its own docstring), and no `sole_blocker` per-tick trigger-eval script exists in the repo (grepped `setup/scripts/`, `backtest/`: the only `sole_blocker` hits are `gate_expiry_check.py`/tests, an unrelated "sole blocker" concept for gate expiry). The live engine's `automation/state/core-decisions.jsonl` rows for 2026-08-31 already carry the full per-tick decomposition needed — `bear_score`, `bear_triggers_raw` (which trigger sub-conditions evaluated true), `bear_blockers` (which numbered gate refused entry), `bear_rejection_level_raw`, and `levels_active` — so this is a direct read of that ledger plus the real SPY 5-min bars (`backtest/data/spy_5m_2026-05-19_2026-08-31.csv`), not a re-simulated replay. This is a faithful substitute for the requested tool, not a shortcut around it — the ledger IS the deterministic per-tick trigger evaluation the queue asked to see.

---

## Headline finding

**All 55 of the flagged bear≥9-no-trigger ticks on 2026-08-31 (safe account; bold account mirrors) were blocked by exactly one gate: blocker `8` = "VIX gate (needs VIX > 17.30 AND rising)"** (name table: `setup/scripts/gamma_cockpit_data.py:80-89`). VIX ranged **15.08–15.44** all session — nowhere near the 17.30 floor. In every one of the 55 ticks, `bear_triggers_raw` shows the trigger-detection layer itself firing true: `level_rejection` alone (10 ticks), `level_rejection + confluence` (35 ticks), or `level_rejection + confluence + trendline_rejection` (10 ticks). So the trigger conditions the queue asked about (level proximity band, wick/body rule, min_triggers, ribbon state, time gate) were **not** what refused these ticks — they all passed. The sole refusal was a VIX-regime filter, a mechanism outside the five sub-conditions the queue enumerated.

## Episode table

7 contiguous episodes (≤5 min gap merge), all inside a **765.0–766.2 SPY range** (≈$1.2 total range for the session) with **VIX flat 15.08–15.44**:

| Episode (ET) | Ticks | SPY range | Rejection level(s) | Trigger combo(s) | Blocking sub-condition |
|---|---|---|---|---|---|
| 09:46–09:50 | 5 | 765.81 | 766.30 | level_rejection+confluence | VIX gate (VIX 15.24–15.33, need >17.30 & rising) |
| 10:01–10:15 | 15 | 765.54–766.22 | 766.30 → 765.72 | level_rejection[+confluence] | VIX gate (15.25–15.44) |
| 11:41–11:45 | 5 | 765.545 | 765.46/765.49 | level_rejection | VIX gate (15.15–15.16) |
| 12:01–12:10 | 10 | 765.11–765.36 | 765.92 → 765.21 | level_rejection+confluence+trendline_rejection | VIX gate (15.12–15.17) |
| 12:41–12:45 | 5 | 765.36 | 765.46/765.90 | level_rejection+confluence | VIX gate (15.17–15.22) |
| 13:21–13:25 | 5 | 765.73 | 765.91/765.98 | level_rejection+confluence | VIX gate (15.15–15.16) |
| 13:31–13:40 | 10 | 765.29–765.47 | 765.54 | level_rejection+confluence | VIX gate (15.08–15.13) |

**Sub-condition histogram (55/55 ticks):** VIX gate (blocker 8) = 55 (100%). No level-in-band failure, no wick/body failure, no min_triggers failure, no ribbon-state failure, no time-gate failure appeared anywhere in the 55.

## SPY 5-min bars, episode windows (source: `backtest/data/spy_5m_2026-05-19_2026-08-31.csv`)

Representative two episodes (full set pulled for all 7, same character throughout — tight, low-volume chop):

```
09:40 O766.25 H766.64 L765.78 C765.805  V440,961
09:45 O765.83 H766.21 L765.724 C766.12  V165,776   <- ep1 starts here, price already reversing UP off 765.72
09:50 O766.11 H766.53 L765.78 C766.52   V335,809
09:55 O766.48 H766.71 L766.08 C766.18   V357,824

11:55 O766.06 H766.12 L765.31 C765.4199 V171,013
12:00 O765.42 H765.42 L765.06 C765.16   V235,588   <- ep4 (12:01-12:10)
12:05 O765.14 H765.21 L764.98 C765.135  V253,151
12:10 O765.13 H765.77 L765.08 C765.71   V202,974   <- reverses back UP within the same bar
12:15 O765.715 H765.76 L765.27 C765.5801 V207,768
```

**Plain-language read (BEARISH_REJECTION_RIDE_THE_RIBBON playbook, `markdown/0dte/playbook.md`):** a discretionary trader watching this tape would see repeated shallow pokes at micro-levels inside a sub-$1.50 band with immediate reclaim — not a clean single-bar rejection candle "with wide range, opens high, closes near low, volume ≥1.5× recent average" (the playbook's own trigger #1 language, mirrored from its bullish twin at line 161). The bars show small-range candles reversing within 1 bar each time (e.g. 12:00–12:10: down to 764.98 then straight back to 765.77 in the next bar). It is a plausible micro level-touch, not a decisive breakdown. **Status note:** `BEARISH_REJECTION_RIDE_THE_RIBBON` itself is `OBSERVATION (demoted 2026-W28)` in the playbook — n=29, hit_rate 24.14%, below the 40% demote floor — so even a clean fire here would have been trading a demoted, unconfirmed setup.

**VIX-doctrine cross-check (important, not in the queue's original framing):** the playbook's own prose VIX rule for puts (line ~48) is *"VIX should be rising OR already above 20 ... VIX below 15 = do not enter puts (market too complacent, premiums too thin, moves fizzle)."* Actual VIX all 7 episodes: 15.08–15.44 — sitting almost exactly on the playbook's own "too complacent" floor, not merely failing the engine's numeric gate. The **engine's coded gate (17.30 AND rising) and the playbook's written prose (20 OR rising) are two different thresholds for the same doctrine** — a provenance mismatch worth flagging on its own, but on this day both formulations point the same direction: don't enter puts at VIX ~15.

## 09-01 / 09-02 comparison

| Date | Total ticks | Bear≥9 | Bear≥9 no-trigger | Blocker | VIX range | Episodes |
|---|---|---|---|---|---|---|
| 2026-08-31 | 386 | 55 | 55 | 100% blocker `8` (VIX gate) | 15.08–15.44 | 7 |
| 2026-09-01 | 386 | 67 | 60 | 100% blocker `8` (VIX gate) | 15.30–16.33 | 12 |
| 2026-09-02 | 386 | 0 | 0 | n/a | n/a | 0 |

09-01 reproduces the **identical signature** — same sole blocker, VIX still under the 17.30 floor all session (drifting up toward 16.3 by the close but never crossing). 09-02 shows none of it — zero bear≥9 ticks at all, a materially different day shape (not investigated further; out of scope for this replay).

## Classification: **D (mixed)** — mechanically B-shaped, substantively C-leaning

- **Not A** (level-producer gap): `levels_active` was populated (17 levels on the first episode alone) and `bear_rejection_level_raw` resolved to a specific in-band level on every tick. The level feed was not empty or stale.
- **Mechanically B:** the trigger-evaluation layer (level_rejection / confluence / trendline_rejection) fired true on 100% of these ticks — a real, distinct rule (the VIX floor gate, blocker 8) is what refused entry, not a level/wick/min_triggers/ribbon/time sub-condition. That gate's numeric threshold (17.30 AND rising) doesn't match the playbook's own written VIX prose (20 OR rising, floor 15) — a genuine rule-provenance question.
- **Substantively C-leaning:** on the SPY 5-min bars, the price action was tight, low-volume, sub-$1.50-range chop — not the decisive rejection candle the playbook's trigger #1 describes — and VIX sat at the playbook's own "too complacent, do not enter puts" floor (15.08–15.44) all session. Even under the playbook's own (looser) VIX prose, most of these ticks would not have cleanly confirmed. The underlying setup is also demoted (OBSERVATION, not CONFIRMED).

**One-sentence conclusion:** 08-31 (and 09-01, same signature) were VIX-gate refusals inside a sub-$1.50 chop range on a demoted setup — the trigger layer correctly detected micro level-touches, but neither the engine's coded VIX floor nor the playbook's own written VIX doctrine would call this session's price action a confirmable rejection, so `conductor_outcome.py`'s `regressing`/zero-enters label reflects a plausible legitimate quiet stretch rather than a proven detector bug, though the 17.30-vs-20 VIX-threshold provenance mismatch between the coded gate and the playbook prose is a real open question.

**If B were the dominant read** (it is not, per above): the prereg for 10-30 would test whether the coded VIX gate's `>17.30 AND rising` threshold should instead match the playbook's written `>20 OR rising` (a materially looser bar), on forward data only, following the existing stop_mode/day-throttle shadow-instrument pattern — not applied retroactively, not shipped now.

## UNVERIFIED / not checked this fire

- Bold-account ticks were not independently pulled (safe account used as the representative account; per CLAUDE.md doctrine bear_blockers/triggers are direction-scored, not per-account-strategy, so this is expected to mirror, but not independently confirmed byte-for-byte).
- Whether blocker 8's `17.30 AND rising` threshold itself has a ratification record (a prereg, an A/B scorecard) was not traced — only its current behavior and its mismatch with the playbook's prose were established.
- 09-02's zero-bear≥9 day shape was not investigated (bullish day? different regime?) — out of this item's scope.
- No chart/TradingView visual replay was done; this reads the ledger + raw OHLCV bars only, not a rendered chart.
