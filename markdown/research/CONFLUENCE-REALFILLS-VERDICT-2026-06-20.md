# Confluence / Structure — Real-Fills Verdict (KILL as a trigger) — 2026-06-20

> **J's challenge:** "I don't believe a word until I see you've backtested it to infinity."
> **Answer:** done — on real OPRA option fills (C1, the only WR authority), 16 months, OOS-split, every quarter, every VIX band. **The signal loses money as a 0DTE trigger.** This supersedes the SPY-direction proxy ([STRUCTURE-EDGE-STUDY](STRUCTURE-EDGE-STUDY-2026-06-20.md)), which was explicitly *not* an option-edge claim (C3/L58).
> **Harness:** [`backtest/autoresearch/confluence_real_fills_validate.py`](../../backtest/autoresearch/confluence_real_fills_validate.py) → `simulate_trade_real`. Entry = fresh BOS/CHoCH + confluence bias agrees + conviction ≥ T; CALL (bull) / PUT (bear), ATM, qty 3, chart-stop-only (−99% premium), v15 exits, 45-min cooldown.

## The numbers (conviction sweep, real fills)

| Conviction ≥ | n | WR | Total P&L | Avg/trade | Pos quarters | OOS 2026 |
|---|---|---|---|---|---|---|
| 50 | 1,047 | 60.5% | **−$23,406** | −$22 | **0/6** | −$5,188 |
| 65 | 907 | 59.1% | **−$24,631** | −$27 | **0/6** | −$5,709 |
| 80 | 178 | 53.4% | **−$6,883** | −$39 | **0/6** | −$2,068 |
| 95 | 38 | 50.0% | −$200 | −$5 | 3/6 | **−$198** (n=9) |

Raw: `analysis/recommendations/confluence-real-fills-fresh{50,65,80,95}.json`.

## What it means

1. **The 60% win-rate is a TRAP.** High WR + negative expectancy = wins are small, losses are full premium decay on a wrong-direction 0DTE option. This is exactly the C3/L58 lesson (SPY-price edge ≠ option edge) and OP-14 (WR is not the metric) — made concrete with real fills.
2. **No selectivity rescue.** Tightening conviction 50→80 keeps it deeply negative and **0/6 quarters** the whole way. Only at conviction ≥95 does a tiny bull subset go nominally positive (**+$258 over 15 trades**) — but with **401% top-5-day concentration and a NEGATIVE OOS** (−$198, n=9). That is survivorship noise (anti-pattern 2.10), not edge. I am not shipping it.
3. **The bull-tilt is real but RELATIVE, not profitable.** Bull consistently loses less than bear (e.g. at ≥50: bull −$11.6/trade vs bear −$38.8/trade). The directional asymmetry corroborates the J-data bull-tilt — but "less negative" is not an edge.

## Direct consequence for the LIVE fleet (load-bearing)

The `market_structure_watcher` (added observe-only 2026-06-20, fleet 28→30) fires on exactly these fresh BOS/CHoCH events. **This backtest is its promotion test, and it FAILS** — real-fills negative, 0/6 quarters. **Do NOT promote `market_structure_watcher` (or `double_top_watcher`) to a live trigger.** They stay WATCH_ONLY / awareness telemetry. (Double-top still warrants its own isolated real-fills run; queued.)

## What the structure/confluence layer IS good for (unchanged, now evidence-backed)
- Situational awareness / narration (the `chart-read` wizard read), conflict detection, and as a **screen** — never a trigger or a sizing input.

## Disclosure (OP-20)
- **Authority:** real OPRA fills; supersedes any SPY-direction proxy.
- **Per-trade expectancy** reported, not WR alone (OP-14).
- **Concentration** shown per cut (the ≥95 "win" is 401% top-5).
- **No grid was cherry-picked:** this is a 4-point principled sweep; the one positive cell is explicitly called out as noise, not a survivor.
- **Account scaling:** qty=3 ATM ≈ $300–600/trade; the losses fit within (and would repeatedly trip) the $2K Safe per-trade cap — i.e. trading this live would bleed the account.

## Verdict
**KILL as a trigger. KEEP as awareness.** The rigor did its job: it stopped a 60%-win-rate signal that would have lost ~$23K over 16 months from ever reaching a live order.
