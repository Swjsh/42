# SWARM CONSULT: DECIDE -- Is the Gamma 0DTE engine ALREADY trading bull (BULLISH_RECLAIM), making the 'bea

**Filed:** 2026-06-28T23:05:12 ET
**Mode:** `decide`
**Cost:** $0.0017
**Elapsed:** 37.6s
**Perspectives:** 3 / 3 succeeded

## Question

Is the Gamma 0DTE engine ALREADY trading bull (BULLISH_RECLAIM), making the 'bear-only' state a doctrine-prose artifact rather than a code gap? Or is there a real code/config gap preventing bull entries? If wired, what is the single highest-value action + guard to make bull genuinely work and not silently regress?

## Context (provided)

```
CLAIM TO ADVERSARIALLY VERIFY: "The Gamma engine ALREADY trades bull (BULLISH_RECLAIM) — it is NOT bear-only in code. The 'bear-only' appearance is stale DOCTRINE PROSE + the fact bull fires rarely, NOT a missing wiring."

CODE EVIDENCE (setup/scripts/heartbeat_core.py — the live deterministic engine):
1. Line 410: kwargs hardcode "enable_bullish": True. The engine SCORES bull on every tick.
2. Live decisions log: last 200 ticks -> bull_scored=200/200 (bull_score 4-5/11 computed every tick). ENTER_BULL=0, ENTER_BEAR=6 (consistent: backtest fires ~25 bull trades / 18 months = ~1.4/mo, so 0 in 1-2 days is expected).
3. Placement path: `if v in ("ENTER_BEAR","ENTER_BULL"): rec["exec"] = _execute(account, verdict, payload, params, dry=not ARMED)`. Bull executes via the IDENTICAL path as bear. No bear-only exec gate on the core path.
4. side mapping: side = "P" if ENTER_BEAR else "C"; setup name maps to "BULLISH_RECLAIM_RIDE_THE_RIBBON" for C.
5. The orchestrator default is enable_bullish=True (RATIFIED v12 "symmetric setup hunting").

VALIDATION EVIDENCE (real OPRA fills, current engine, all dated 2026-06-26 unless noted):
- chef-bull-scope-ab (real_fills=True, current engine, 2025-01..2026-06-18): UNBLOCK(bull+bear) vs KEEP(bear-only): total $6423 vs $836; Sharpe 0.156 vs 0.046; 25 bull trades, bull_pnl=+$5586, bull_wr=56%; LESS concentrated (top5 1.29 vs 4.45). Bull is strongly net-positive.
- OP-16 final_score REJECTS UNBLOCK only because edge_capture=-1220 (< 771 floor) — but edge_capture is IDENTICAL in both arms (delta 0.0). It is tanked by an ORTHOGONAL anchor-day bug: on 2026-04-29 (a J WIN day) the engine takes -$1365. That is a bear/sizing problem on anchor days, NOT a bull problem. Using edge_capture to block bull is a mis-fire.
- block_elite_bull [0,25): VALIDATED + RATIFIED 2026-06-18 (all 5 OP-22 gates: G1 IS +113, G2 OOS +63, G3 WF 3.89, G4 SW-hurt 1, G5 anchor-clean). It is SURGICAL — only blocks the confluence+level_reclaim ELITE combo (14 IS: 12 losers). It does NOT block the profitable non-elite reclaim bulls.
- f8 VIX<17.2 bull block: validated KEEP (blocks 3 net-loser bulls, -$892).
- elite-bull VIX 15-18 block: validated RATIFY (4/4 OOS losers).

DOCTRINE STATE (the drift):
- CLAUDE.md OP-16: "Setup scope lock: BEARISH_REJECTION_RIDE_THE_RIBBON only until J proves otherwise. BULLISH_RECLAIM stays DRAFT until J has 3 live wins on it."
- J's recorded standing feedback: "scoped bearish only should NOT exist; each account trades ALL validated setups BOTH directions. Direction isn't a scope — validation is. Bull-blocks were A/B-validated on the OLD engine; re-audit when the engine changes."
- J's CURRENT direct order (2026-06-28): "we need bull strats wired in why tf is it only bear still."

CURRENT EXECUTION MODE: heartbeat_core runs WATCH/shadow by default (GAMMA_CORE_ARMED=0). Arming (paper or live) flips GAMMA_CORE_ARMED=1. Live-money arming needs J (OP-0). Paper validation does not.

THE QUESTION FOR THE SWARM: Given all the above, is the claim TRUE (bull is already wired; the gap is doctrine prose + rare firing, not code)? Or is there a REAL code/config gap that prevents bull from being taken that I have missed? If there is a gap, name it specifically with the file/mechanism. If the claim is true, what is the single highest-value action to make bull genuinely "work" per J's intent — and what guard locks it in so it cannot silently regress?

```

## Synthesis (actionable)

_Model: `nvidia/nemotron-3-super-120b-a12b:free`, elapsed 18.2s, cost $0.0000_

**Consensus points**  
- The engine already scores and can execute bull entries (`enable_bullish=True`, identical execution path as bear).  
- The “bear‑only” perception is stale doctrine/prose, not a missing wiring.  
- Bull is validated as profitable (backtest, real OPRA fills) and only blocked by surgical, orthogonal filters (VIX/elite blocks).  
- To make bull genuinely work per J’s intent we must align doctrine with the actual code and add a guard that prevents silent regression.

**Key disagreements**  
| Perspective | Guard proposal | Reasoning |
|-------------|----------------|-----------|
| 1 (Nemotron) | CI guard: fail build if `enable_bullish` not `True` or unit test doesn’t produce `ENTER_BULL`. | Prevents regression at commit time; relies on tests/CI. |
| 2 (GPT‑OSS) | Runtime post‑verdict guard in `heartbeat_core.py`: assert `rec["exec"]` is set for `ENTER_BULL` (log critical error if not) + doctrine update. | Detects regression immediately at execution time; more direct and observable. |
| 3 (Gemma) | Only doctrine update (no code guard). | Considers code already correct; guard unnecessary. |

**Most rigorous**: Perspective 2’s runtime guard is the strongest because it catches a regression the moment the engine fails to turn a bull verdict into an execution, regardless of CI/test coverage or future flag changes. It complements the doctrine fix with an observable, fail‑fast signal.

**Synthesized recommendation**  
Update the doctrine (e.g., `CLAUDE.md`) to remove the “BEARISH_REJECTION_RIDE_THE_RIBBON only” scope lock and explicitly state that `BULLISH_RECLAIM_RIDE_THE_RIBBON` is an active, validated setup wired by default. Then add a runtime guard in `heartbeat_core.py` immediately after the verdict‑to‑exec block that logs a critical error (or raises) if `verdict == "ENTER_BULL"` and `rec["exec"]` is `None`/missing, ensuring any future change that breaks the bull path is surfaced instantly.

**Confidence in synthesis**  
9 – All three perspectives agree on the core diagnosis (doctrine stale, bull wired) and on the need to align documentation; the only split is guard placement, and the runtime guard is the most rigorous and directly observable.

**Single most‑important next action (executable today)**  
1. Edit `CLAUDE.md` (or the doctrine file that defines setup scopes) to delete the bear‑only scope lock and add a line such as:  
   `# BULLISH_RECLAIM_RIDE_THE_RIBBON is an ACTIVE, validated setup; enable_bullish=True by default.`  
2. In `setup/scripts/heartbeat_core.py`, locate the block that handles verdicts (around the `if v in ("ENTER_BEAR","ENTER_BULL"):` line) and insert after the `_execute` call:  
   ```python
   if v == "ENTER_BULL" and rec.get("exec") is None:
       logger.critical("BULL execution guard FAILED: ENTER_BULL verdict did not produce exec")
       # Optionally raise an exception to halt the heartbeat in paper/live mode
   ```  
   (If a logging framework is not yet imported, add the necessary import at the top.)

**Watch‑for signal**  
If after deploying the change the decision logs continue to show `ENTER_BULL` verdicts (score ≥ threshold) **and** either:  
- The new critical error message appears (guard fires), **or**  
- No `exec` field is populated for those verdicts (i.e., bull entries still fail to reach the broker),  

then the synthesis is invalidated – indicating a hidden code/config block beyond the flag or doctrine. Conversely, if bull verdicts begin to produce proper `exec` entries and no guard errors appear, the synthesis holds.

## Individual perspectives

### Perspective 1: `nvidia/nemotron-3-super-120b-a12b:free`

_Elapsed 13.3s, 1619 in / 640 out, cost $0.0000_

**Recommended action**  
Edit `CLAUDE.md` (or the doctrine file that defines setup scopes) to remove the “BEARISH_REJECTION_RIDE_THE_RIBBON only” scope lock and explicitly state that `BULLISH_RECLAIM_RIDE_THE_RIBBON` is an active, validated setup, then add a CI guard that fails the build if `enable_bullish` is not `True` or if a unit test simulating a bull signal does not produce an `ENTER_BULL` verdict.

**Reasoning**  
The code evidence shows bull is already scored, routed through the same execution path as bear, and validated as profitable; the only thing preventing bull from being treated as a first‑class setup is the stale doctrine prose that labels it “DRAFT” and bear‑only. Updating the doctrine aligns the official record with the actual engine state, satisfying J’s directive to wire bull in. Adding a CI guard that checks the `enable_bullish` flag and verifies a bull entry can be generated prevents silent regression if someone later flips the flag or reintroduces a scope lock without notice.

**Confidence**  
9

**Required follow‑up**  
After the change, monitor the decision logs and the CI pipeline to ensure the guard passes and that live/paper logs begin recording `ENTER_BULL` events (even if infrequent) without any new errors.

**If I were wrong, the signal would be**  
If after the doctrine update the engine still never emits an `ENTER_BULL` verdict despite bullish market conditions, indicating a hidden code or config block beyond the flag.

### Perspective 2: `openai/gpt-oss-20b:free`

_Elapsed 15.5s, 1520 in / 772 out, cost $0.0011_

**Recommended action**  
Add a post‑verdict guard in `heartbeat_core.py` that asserts `rec["exec"]` is set whenever `verdict == "ENTER_BULL"` (and log a critical error if not), and update the doctrine prose to remove the “bear‑only” restriction.

**Reasoning**  
The code already scores and executes bull entries; the only barrier is stale prose and the risk of silent regression if a future change inadvertently disables the bull path. A guard that fails fast on a missing bull execution will surface regressions immediately, while the prose update aligns the system state with J’s intent and prevents future mis‑documentation.

**Confidence** 9  

**Required follow‑up**  
After deployment, watch the system logs for any “Bull execution guard failed” messages and verify that bull trades are still being placed during paper and live runs.

**If I were wrong, the signal would be**  
If a future code change removes the `rec["exec"]` assignment for bull verdicts, the guard will trigger a critical error, revealing that the bull path has regressed.

### Perspective 3: `google/gemma-4-31b-it:free`

_Elapsed 8.4s, 1621 in / 287 out, cost $0.0006_

**Recommended action**
Update `CLAUDE.md` and all doctrine prose to remove the "bear-only" scope lock and explicitly state: "Symmetric Setup Hunting is ACTIVE; BULLISH_RECLAIM is wired and enabled by default."

**Reasoning**
The code evidence is deterministic: `heartbeat_core.py` hardcodes `enable_bullish: True`, scores bull on every tick, and uses an identical execution path as bear. The "bear-only" state exists solely in the prose (doctrine drift), creating a psychological block that contradicts both the engine's current logic and J's direct order. The backtest data proves bull is net-positive and the existing blocks (VIX/Elite) are surgical, not global. Any perceived "gap" is a failure of documentation, not a failure of wiring.

**Confidence**
10

**Required follow-up**
Verify the first `ENTER_BULL` signal in the live decision log during the next high-volatility reclaim event to ensure the `_execute` path triggers the correct "C" side mapping.

**If I were wrong, the signal would be**
A `BULLISH_RECLAIM` signal appearing in the logs with a score > threshold but failing to trigger the `_execute` function or resulting in a `None` return from the placement path.
