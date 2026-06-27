# PRE-SHIP CHECK — direction-block UNBLOCK + dormant-setup ENABLE batch

> Owed by the STATUS [2026-06-26 ~11:50 ET] STAGED entry: *"confirm the 4 dormant setups are OFF by config, not a deliberate recency-drawdown HOLD (recency_check gate / license_monitor) — verify before flipping `enabled=true`."*
> Run: 2026-06-26 ~19:50 ET (conductor fire). Verdict authority: `automation/state/recency-confirmation.json` (run 2026-06-22, the weekly CONFIRM-BEFORE-CAPITAL gate; window 2026-05-14..2026-06-18; real OPRA fills; cap-aware realizable book).

## VERDICT: the 2 still-dormant enables FAIL the pre-ship check — HOLD them.

The recency gate's rule (verbatim): **"NO live flip while an edge's recency verdict is RED; capital scaling on an edge WAITS for CONFIRM."**

| Setup (ATM tier, what would go live) | Per-edge recency | Combined-book recency |
|---|---|---|
| `vwap_continuation` (#1, already LIVE base-size) | YELLOW (recent −$34.63/tr, n=7<10; full-OOS +$56.46) | — |
| `vwap_reclaim_failed_break` (#2, STAGED→enable) | YELLOW (recent −$40.56/tr, n=5<10; full-OOS +$13.66) | **Safe-2 ATM book {#1+#2+#4} = RED** (n=17 ≥ floor, −$8.01/tr, *clear*) |
| `vix_regime_dayside` (#4, STAGED→enable) | YELLOW (recent +$61.8/tr, n=5<10) | **Bold ATM book {#1+#2} = RED** (n=10 ≥ floor, −$60.12/tr, *clear*) |
| `gap_and_go` (STAGED→both; LIVE=enabled side=put) | NOT in recency tracker | — (no recency basis — see flag) |

**Why this resolves AGAINST flipping #2/#4:** individually they read YELLOW (small-n wobble, gate does not hard-kill), but the *realistic* live state — running them together with the already-live #1 — is the **book**, and both the Safe-2 and Bold ATM books carry a CLEAR recency-RED verdict (n ≥ floor, negative). The gate forbids a live flip into RED. This matches the standing read (memory `project_allnight_hunt_2026_06_21`): the edges are in a ~2.2σ recency drawdown → HOLD per recency_check; license_monitor pings J on the RED→green transition so the enable ships the first eligible day.

## SECONDARY CATCH — the STAGED "ONE reversible commit" was applied PARTIALLY

Live SAFE/BOLD params vs. the STAGED intent (verified 2026-06-26 ~19:50 ET):

| Change | Staged | Live now | State |
|---|---|---|---|
| `params.json#midday_trendline_gate` | true→false | **false** | APPLIED |
| `params.json#entry_bar_body_pct_min` | 0.20→0.0 | **0.2** | NOT applied |
| `params.json#vix_entry_thresholds.bull_hard_cap` | 18→22 | **22.0** | APPLIED |
| `filters.py:805 VIX_BULL_HARD_CAP` | 18→22 | **22.0** (comment: "WS2 unblock 2026-06-26") | APPLIED |
| `params.json#gap_and_go_enabled` | enable | **True** (side=put) | APPLIED |
| `params.json#j_vwap_cont_enabled` | enable | **True** (side=both) | APPLIED (pre-existing live edge #1) |
| `params.json#j_vwap_reclaim_fb_enabled` | enable | **False** | NOT applied — **HOLD per recency** |
| `params.json#j_vix_dayside_enabled` | enable | **False** | NOT applied — **HOLD per recency** |
| `params.json#structure_veto_enabled` (the "NEXT" deeper fix) | wire | **True** | APPLIED |
| `aggressive/params.json#require_bearish_fill_bar` | true→false | **True** | NOT applied |
| `aggressive/params.json#block_conf_lvl_rec_afternoon` | true→false | **True** | NOT applied |

The SAFE direction-block UNBLOCKS (A/B-validated, not recency-gated) + structure-veto landed; the Bold unblocks, `entry_bar_body`, and the 2 recency-held enables did not. So the live engine is in a consistent-but-incomplete state, NOT the "one atomic commit" the STATUS entry described.

## RECOMMENDATION (rail-4 — conductor does NOT apply; J decides)

1. **Do NOT enable `j_vwap_reclaim_fb`/`j_vix_dayside`** until the Safe-2 ATM book recency verdict clears RED→YELLOW/CONFIRM. `license_monitor` already watches this transition and will ping J. This is the correct, already-encoded HOLD — leave them dormant.
2. **`gap_and_go_enabled=True` deserves its own basis** — it is a WATCH→LIVE candidate with NO entry in the recency tracker. Flag for J: was this enable A/B-validated, or did it ride the batch without a recency floor? If un-validated, propose reverting to dormant until it has a fills basis.
3. **Bold unblocks + `entry_bar_body`**: finish or formally drop — the partial-apply leaves intent ambiguous. J ruling (Rule 9).
