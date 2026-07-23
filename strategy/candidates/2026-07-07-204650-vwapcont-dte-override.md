# Strategy candidate: vwap_continuation 2DTE-ATM expiry override

> DRAFT — Chef proposal 2026-07-07 20:46 ET. J/Gamma ratifies. OFFLINE R&D, $0, paper. NOT applied to live params/engine.

## Hypothesis
The night's DTE lever nearly doubled OOS on the ITM-2 tier (multiday_dte_compare: $36→$66).
Claim: on the LIVE **ATM Safe-2 cell** (the armed vwap_continuation cell; ITM-2 unaffordable
at $2k per C29), buying **2DTE and CLOSING SAME DAY** (never held overnight — that is
gap-exposed and loses) with the **static -0.06 stop** lifts OOS per-trade materially over
0DTE. The wiring = one isolated per-setup DTE override (`j_vwap_cont_dte_override`), mirroring
the isolated strike/exit-key pattern, defaulting to 0DTE when absent.

## Backtest evidence — ATM Safe-2 cell (offset=0, stop −0.06, tp1 +0.30)
Real OPRA fills, honest same-day exit (`_dte_expansion_sim.run_cell`), N=156 (0DTE) / 165 (2DTE).

| metric | 0DTE (incumbent) | 2DTE (candidate) |
|---|---|---|
| full n | 156 | 165 |
| full WR | 44.9% | **38.2%** |
| full exp/tr | $37.08 | $54.21 |
| **OOS exp/tr (2026)** | **$28.90** | **$45.04** (+$16.14, +56%) |
| OOS WR | 38.8% | 36.0% |
| OOS drop-top3/tr | $16.74 | $22.39 |
| held-overnight % | 0.0% | 0.6% |
| random-entry null p | **0.005** | **0.0647** |

- edge_capture (OP-16): **uninformative for this family** — vwap_continuation fires ~0 on the
  three J anchor days (5/01 & 5/04 = $0 signal; 4/29 the family is net-negative on BOTH DTEs,
  −$38 at 0DTE / −$92 at 2DTE, no 0DTE→loss regression). This candidate is a per-trade-expectancy
  lever, not an anchor-capture lever (measure by expectancy per project memory `range_scalp_first_vein`).
- aggregate OOS lift: +$16.14/tr (the exact reproduction of the task-context $28.90→$45.04).
- top-concentration: **edge is concentration-driven** — 2DTE wins big in 2025-Q4/2026-Q1, loses hard in 2025-09 (−$182/tr month) and 2026-Q2.
- positive_quarters: **4/6** for 2DTE (much-worse in 2025Q3 −$40.89 and 2026Q2 −$29.11 vs 0DTE).
- max_drawdown: 2DTE variance is higher (WR down 6.7pts, winners bigger) — a wider-tail trade.
- real_fills_validated: **yes** (real OPRA day-T bars, expiry-intrinsic settlement).

## OP-22 gate table (ATM Safe-2 cell) — 2 of 6 FAIL
| gate | result | number |
|---|---|---|
| OOS positive AND 2DTE>0DTE | **PASS** | $45.04 > $28.90 |
| Walk-forward ≥ 0.70 | **FAIL** | **0.556** (10/18 months); degrading 0.67→0.44 first→second half |
| Quarters stable (no much-worse) | **FAIL** | 2025Q3 −$40.89, 2026Q2 −$29.11 vs 0DTE |
| Anchor no-regression | PASS | no J-winner day flips + to − |
| Drop-top3 positive | PASS | 2DTE OOS $22.39/tr |
| Same-day exit unaffected | PASS | held-overnight 0.6% |

**Decisive:** 2DTE is WORSE than 0DTE in **4/4 most-recent months** (2026-03 −$59, -04 −$19,
-05 −$8, -06 −$78) — the recency window that governs arming. The 2DTE random-entry null does
NOT clear significance (p=0.0647): at 2DTE the extra edge is partly "long a rising tape with
more days to drift" (C3/L172), not the trigger. The $45 OOS is genuine but **carried by
2025-Q4/2026-Q1 concentration**, currently in a 4-month losing regime vs the incumbent 0DTE.

## Disclosures (per OP-20)
1. **Account-size assumption:** $2k Safe-2, 30% risk = $600 budget. See sizing risk below — 2DTE breaks the min-3-contracts floor here.
2. **Sample-bias:** OOS = 2026 only (n=50). The +56% lift is not month-stable (10/18 WF).
3. **Out-of-sample:** 2DTE OOS $45.04/tr > 0DTE $28.90 in aggregate, BUT 2DTE loses in all 4 most-recent OOS months.
4. **Real-fills:** yes, real OPRA + expiry-intrinsic settlement; same-day exit confirmed (held 0.6%).
5. **Failure-mode enumeration:** (a) recency regime — 2DTE currently losing 4/4 recent months; (b) concentration — edge in 2 quarters; (c) null p=0.0647 — signal edge degrades at 2DTE; (d) sizing — 2DTE premium 2.33× breaks min-contract floor at $2k; (e) holiday-in-window makes a "2DTE" contract actually 1DTE (picker skips weekends only).
6. **Concentration:** 2DTE OOS drop-top3 $22.39 vs full $45.04 → ~50% of OOS per-trade edge in the top-3 days.

## Sizing risk (material)
Mean ATM entry premium: **0DTE $1.63 → 2DTE $3.81 (2.33×)**. At the $600 risk budget you afford
**57% fewer contracts (3.7 → 1.6)** — and **1.6 rounds below the Rule-6 min-3-contracts floor**.
2DTE ATM at $2k either can't be sized to 3 lots within the risk cap, or forces a smaller strike
budget. This is a HARD blocker at the current Safe-2 equity independent of the edge question.
(Liquidity itself is fine: 2DTE ATM SPY weeklies are deep — an existing listed expiry, tight spreads.)

## Knob changes proposed (STAGED — do NOT apply)
`automation/state/params.json` (Safe) — ONE new key:
```json
"j_vwap_cont_dte_override": 2
```
Default when absent/0 = 0DTE, byte-identical to today. **Not recommended to set to 2 now** (see verdict).

## Staged picker patch (proposal only — NOT applied)
`setup/scripts/heartbeat_core.py`. Add the override table next to `_SETUP_STRIKE_OVERRIDES`:
```python
_SETUP_DTE_OVERRIDES = {"vwap_continuation": "j_vwap_cont_dte_override"}

def _add_trading_days(start, n):
    if n <= 0:
        return start
    d, added = start, 0
    while added < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d

def _expiry_for_setup(setup_name, now, params):
    key = _SETUP_DTE_OVERRIDES.get(str(setup_name or "").lower())
    if not key:
        return now
    try:
        n = int(params.get(key, 0))
    except (TypeError, ValueError):
        n = 0
    return _add_trading_days(now, n)
```
Then in `_execute`, replace line 1088:
```python
-    expiry = _et_now()
+    expiry = _expiry_for_setup(setup_name, _et_now(), params)
```
`setup_name` is already in scope (line 1069). Every non-vwap setup keeps `now` (0DTE) byte-identical.
Same-day exit is unaffected — exit_manager closes on the entry day regardless of expiry (held 0.6%).
v2 note: `_add_trading_days` skips weekends only; a holiday in the window yields a 1DTE contract —
upgrade to holiday-aware via `automation/state/calendar.json` before any live arm.

## Guard test spec (red-proofed, written + passing)
`backtest/tests/test_vwapcont_dte_override_2026_07_07.py` — 9 passed + 1 xfail.
- `TestReferenceImpl`: override=2 → 2 trading days out; skips weekend; absent/0/None/bad → 0DTE; only the named setup.
- `TestBrokenState`: proves the CURRENT hardcoded `expiry = _et_now()` picks the WRONG (0DTE) expiry when an override is armed — the bug the guard catches (guardian_proven).
- `TestOccSymbolUsesExpiry`: OCC symbol encodes the chosen expiry, differs from 0DTE symbol.
- `TestLiveEngineWired`: xfails until the patch lands, then asserts `heartbeat_core._expiry_for_setup` matches the reference.

## Pre-merge gate
`crypto/validators/runner.py`: passed=103/104. The lone FAIL is `v53_setup_dispatch.live` — a
pre-existing `.live` source condition (its `.offline` twin PASSES); my work is untracked
offline-only files that touch nothing in the dispatch path (confirmed via git status). Not a
break I introduced.

## Verdict: **HOLD**
Fails 2/6 OP-22 gates (WF 0.556 < 0.70; 2 much-worse quarters) AND is in a 4/4-recent-month
losing regime vs 0DTE AND the 2DTE null does not clear p≤0.05 AND sizing breaks the min-3-lot
floor at $2k. The aggregate +56% OOS is a real-but-concentrated 2025-Q4/2026-Q1 artifact, not a
regime-robust edge. **The wiring is staged and ready** — if a later re-run (fresh OOS after the
current regime turns, or at a higher equity tier where 3 lots of 2DTE ATM fit) re-clears all 6
gates, flip `j_vwap_cont_dte_override=2` and apply the picker patch. Until then: do not arm.

## My confidence (1-10) and why
**8** that HOLD is correct: three independent signals (WF, recency, null) converge, and the sizing
floor is a hard blocker at $2k. The +56% aggregate is real but the debugging-discipline read
(diagnose before shipping) shows it's concentration + a favorable-2025-half artifact, not a
robust lever on the ATM cell. Reusable: `backtest/autoresearch/vwapcont_dte_atm_ab.py`.
