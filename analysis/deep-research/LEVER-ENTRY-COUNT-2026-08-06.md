# LEVER 4 — STOP THE BLEED AT THE SOURCE: entry COUNT and entry ADMISSIBILITY

**Generated** 2026-08-06 evening ET · **Clock verified this session:** `python setup/scripts/et_clock.py` → `2026-08-06 16:45:26 Thursday EDT`, `market_hours=False`. Analysis-only; **no trading-path file was touched**.

**Pre-registration** `analysis/recommendations/lever-entry-count-prereg-2026-08-06.json` — commit **bf8dec8d**, frozen **before** the runner existed (git-provable).
**Verification** 76/76 assertions PASS, re-derived from the raw ledger by a second independent code path that does *not* import the runner or the shared position-reconstruction helper.

---

## VERDICT

> **PREREG — CAP-3, and one narrower fix the brief did not name.**
>
> Two cells clear the Tuesday hard gate and every other gate: **CAP-3 per (arm, date, contract)** and a **post-hoc SAME-BAR cooldown** that ports the CORE lane's already-shipped churn guard to the fleet lane. Neither separates from chance. Both are does-no-harm, not evidence.
>
> **The brief's "strongest candidate in the whole workflow" — restoring vwap_continuation's validated one-entry-per-day contract — FAILS the brief's own Tuesday hard gate at −$900, and the deeper reason is worse than the gate: the setup loses money in BOTH configurations.**

| Lever | Tue 08-04 | Wed 08-05 | Thu 08-06 | 26-day book | ex-Wed | Days harmed | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| **CAP-3 / contract** | **$0.00** | **+$653** | **$0.00** | **+$720** | +$67 | **0** | **PREREG** |
| **SAME-BAR cooldown** (post-hoc) | **+$144** | **+$202** | **$0.00** | **+$497** | +$295 | **0** | **PREREG** |
| CAP-4 / contract | $0.00 | +$451 | $0.00 | +$463 | +$12 | 0 | PREREG (n=3, starved) |
| CAP-5 / contract | $0.00 | $0.00 | $0.00 | $0.00 | $0.00 | 0 | NULL (no-op) |
| **once/day, vwap only** | **−$900** | +$1,058 | $0.00 | +$158 | −$900 | 1 | **REJECT** |
| once/day, all setups | −$2,527 | +$1,058 | $0.00 | −$1,485 | −$2,543 | 3 | REJECT |
| DAY-CAP 3 / 4 / 5 / 6 | −$2,003 / −$1,211 / −$631 / −$678 | +$970 / +$768 / +$317 / $0 | $0.00 | −$399 / −$76 / −$127 / −$537 | — | 2/1/1/1 | **all REJECT** |
| V-d1 (last closed 5m agrees) | +$179 | +$145 | **$0.00** | +$1,242 | +$1,097 | 1 (−$15) | SHADOW |
| session-high-in-levels ×4 | −$600 / −$529 / −$529 / −$529 | $0 / $0 / +$1,446 / +$1,935 | $0.00 | −$600 / −$449 / +$997 / +$1,486 | — | 1 | **all REJECT** |
| time cooldown 5/10/15/30 min | −$1,133 / −$465 / −$989 / −$514 | +$601 / +$856 / +$607 / +$1,058 | $0.00 | −$156 / +$1,020 / +$253 / +$1,417 | — | 1 | GRAVEYARD_COLLISION |
| COMB CAP-3 + V-d1 (post-hoc) | +$179 | +$798 | $0.00 | +$1,902 | +$1,104 | 1 (−$15) | SHADOW |

Populations: **A = 208 real-broker-fill positions over 26 ET dates (2026-06-26..2026-08-06), net +$1,782.01.** **B = the 391-day engine-fullhist replay (191 trades, 141 traded days, 387 calendar RTH days).**

---

## 1. CAP-3 — the only pre-registered cell that clears every gate

Re-derived from the raw ledger by two independent code paths. **It reproduces the already-circulating numbers to the dollar:** +$720 total, Wed +$653, Tue $0.00, Thu $0.00, ex-08-05 +$67, 12 positions removed, 0 days harmed. Of the 12 removed, exactly **one** was a winner and it was **+$6**.

**Broker-truth ordinal ladder, per (arm, date, contract), 26 days:**

| Entry # on the contract | n | P&L | Win rate |
|---|---:|---:|---:|
| 1st | 149 | **+$1,325.01** | 20.1% |
| 2nd | 30 | +$1,070.00 | 13.3% |
| 3rd | 17 | +$107.00 | 23.5% |
| 4th | 9 | −$257.00 | 11.1% |
| 5th+ | 3 | −$463.00 | **0.0%** |

**Reconciliation with the brief's circulating ladder (which reads `1st n=145 −$140`):** the difference is *entirely* Thursday. 149 − 4 = **145**, and $1,325.01 − $1,465.00 = **−$139.99**. The brief's ladder is the 25-day book; this one is the 26-day book. Both correct, asserted in the verifier.

**The sign still flips exactly between 3rd and 4th.** That is the whole case for N=3 and it is a shape argument, not a significance argument.

**Honest disclosure, restated prominently as the brief demands:** **90.7 % of CAP-3's measured benefit is 2026-08-05 — the day that motivated it.** Ex-08-05 it is **+$67 across 7 waves. That is noise.** Within-day permutation **p = 0.366 raw**, Bonferroni ×17 = 1.0, **BH q = 0.796**. It picks no bad *entry*; it sits out one bad *day*.

**Population B cannot test it at all.** The replay's maximum is **2 entries per contract per day** and **3 entries per day** — a cap at N=3 is a structural NO-OP on 391 days. This is a *reportable null*, not a pass. CAP-3 is single-population evidence, forever, unless the fleet runs it forward.

**CAP-4** is directionally identical (+$463, Tue $0, Wed +$451, 0 harmed, zero winners removed) but blocks only **3** positions in 26 days — below the pre-registered frequency floor. It is untested, not passing.
**CAP-5** blocks nothing. NULL.

---

## 2. RESTORE THE VALIDATED CONTRACT — the defect is real, the fix as specified is not

### 2a. The defect is confirmed, again, on Wednesday's real tape

Running `detect_vwap_continuation_setup` bar-by-bar over 2026-08-05's real 5m RTH tape:

| Regime | Fires |
|---|---|
| Fresh process every tick (**today's live fleet**) | `09:55`, `10:05`, `10:10` |
| Persisted per-day state (**the contract**) | `09:55` |

Three closed-bar fires versus one — and the live producer *also* reads the in-progress bar, which is how the ledger got **five** real fills per risky arm. The characterization guard `backtest/tests/test_vwap_cont_once_per_day_process_scope_2026_08_05.py` already pins this. The parity gap is still live at HEAD: the verifier asserts `same_bar_cooldown_active(` is present in `setup/scripts/heartbeat_core.py` and **absent from every fleet source file**.

### 2b. Restoring one-entry-per-day costs Tuesday $900 — a hard REJECT

The 13 blocked positions, broker truth:

| Date | Arm | Time | Contract | vwap entry # | P&L |
|---|---|---|---|---:|---:|
| 08-04 | risky-1 | 09:50:07 | C763 | 2 | **+$640** |
| 08-04 | risky-3 | 09:50:09 | C763 | 2 | −$40 |
| 08-04 | risky-3 | 09:54:07 | C763 | 3 | −$144 |
| 08-04 | risky-3 | 09:57:09 | C763 | 4 | **+$524** |
| 08-04 | risky-3 | 10:35:08 | C765 | 5 | −$80 |
| 08-05 | risky-1/3 | 10:06–10:18 | C776 | 2–5 | −$1,058 total |

Tuesday delta **−$900.00**. The pre-registered hard gate is −$100. **REJECT.**

**The discriminator, asserted both ways:** risky-3's 09:57 **+$524** rescue is the **3rd position on that contract** — so **CAP-3 preserves it** — but the **4th vwap_continuation entry of that arm's day** (09:46 was on C762) — so **once-per-day kills it**. One trade, two keys, opposite outcomes. This is exactly why *once-per-day-per-SETUP*, *cap-N-per-CONTRACT* and *per-setup TIME cooldown* are three different guards and must never be spoken of interchangeably.

### 2c. The deeper problem: the setup loses money in BOTH configurations

`vwap_continuation` has traded live on exactly **two dates**, **17 real fills**, net **−$558.00**.

| Slice | n | P&L |
|---|---:|---:|
| First entry of the day only (the validated contract) | 4 | **−$400.00** |
| Entries 2+ (outside the validated population) | 13 | −$158.00 |

Restoring the contract moves the family from −$558 to −$400. It does **not** make it profitable. The validated cell (`j-daily-pattern-LIVE.json`, n=153, **+$38.3/trade**) is running at **−$32.8/trade** across 17 live fills — **in-contract entries alone are −$100/trade**. The live sample is tiny and two days is not a refutation, but it is emphatically not a reason to spend $900 of Tuesday.

**Recommendation:** restoring once-per-day is defensible as *provenance hygiene* — the engine should not trade outside its validated population — but it is **not a loss-magnitude lever**, and this lane rejects it as one. The number any provenance argument must beat is **−$900 on Tuesday**.

### 2d. The parity fix that actually works — SAME-BAR cooldown (POST-HOC, disclosed)

C3's failure exposed that once-per-day is not the only way to close the gap. The **narrowest** possible fix ports the CORE lane's already-shipped guard verbatim: `exit_actuator.same_bar_cooldown_active` / `record_entry_bar` (the 2026-07-20 EXTRA-SIGNAL-CHURN-COOLDOWN). Rule: *the last-closed 5m trigger bar must ADVANCE before the same arm re-enters the same setup.* **No tunable knob exists** — it is structural.

| | Tue | Wed | Thu | Book | ex-Wed | ex-week | Harmed | Blocked | Winners blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SAME-BAR cooldown | **+$144** | **+$202** | $0.00 | **+$497** | +$295 | +$151 | **0** | 13 | **$15** vs $512 of losers |

It blocks **exactly three** positions across the whole week — risky-3's 09:54 Tuesday (trigger bar 09:45 already claimed by 09:50) and both arms' 10:14 Wednesday (trigger bar 10:05 already claimed by 10:10) — and it **preserves the 09:57 +$524 rescue**, whose 09:50 trigger bar was new. It is **the only cell in the lane that is positive on Tuesday, positive on Wednesday, and harms zero days**, and at **40.6 %** it is the least Wednesday-concentrated positive cell measured.

**It is POST-HOC.** It was not in the frozen prereg; it was written after C3 failed. Its verdict is therefore **capped at PREREG** in this lane regardless of the dollars. Permutation p = 0.332, BH q = 0.766 — no discrimination here either.

---

## 3. Per-DAY total entry caps — all four cells REJECT, cleanly

| N per (arm, date) | Tue | Wed | Book | Harmed |
|---:|---:|---:|---:|---:|
| 3 | **−$2,003** | +$970 | −$399 | 2 |
| 4 | **−$1,211** | +$768 | −$76 | 1 |
| 5 | **−$631** | +$317 | −$127 | 1 |
| 6 | **−$678** | $0.00 | −$537 | 1 |

Every cell destroys Tuesday, and every cell is **net negative over the book**. A bare per-day count cap is not a loss-magnitude control — it is a tax on the day the engine works. This matches LANE 0's independent finding that `corr(n_positions, loss magnitude)` on losing days is only **0.323**. **Kill the family.**

---

## 4. V-d1 — nothing changes, and the first forward session was empty

Re-measured on the 26-day book: **+$1,242**, Tue **+$179**, Wed **+$145**, ex-week **+$918**, blocked-cohort win rate **3.1 %** ($15 of winners vs $1,257 of losers).

Three things are new:

1. **2026-08-06 — the first session of the shadow window frozen in `entry-structure-forward-prereg-2026-08-06.json` — blocked ZERO entries.** Forward delta **$0.00**. Gate F3 (n_blocked ≥ 8) is nowhere near met after one session. The window is **uninformative so far**; that is EXTEND, not evidence.
2. **Multiplicity correction, as demanded.** Raw within-day permutation **p = 0.1163** (this lane, position-unit, 20,000 draws, seed 20260806; the parent study's 0.1447 used a 230-*entry-event* unit — different denominator, same conclusion). **Bonferroni ×17 = 1.000. Benjamini-Hochberg q = 0.746.** It does not come close to the q ≤ 0.10 bar.
3. **Population B is now measured and it is near-inert:** only **2 of 191** trades blocked, delta **+$144.60**, permutation p = 0.497. The ribbon family almost always enters with an agreeing last-closed 5m bar, so the 391-day population **structurally cannot validate V-d1**. It is single-population evidence.

It also **harms one day** (2026-07-28, −$15), failing the does-no-harm gate. **SHADOW — exactly what its own forward prereg already says. This lane changes nothing about it.**

---

## 5. Entry LOCATION — the bad prior held. Clean NULL, recorded loudly.

Rule tested: *refuse a long within X of a same-session high that is ALSO in the engine's own `levels_active` list* (5-cent match tolerance, frozen in the prereg).

| X | Blocked | Tue | Wed | Book | Wed positions blocked | Pop-B proxy |
|---:|---:|---:|---:|---:|---:|---:|
| $0.25 | 2 | **−$600** | $0.00 | −$600 | 0 % | +$704 |
| $0.50 | 5 | **−$529** | $0.00 | −$449 | 0 % | +$1,376 |
| $0.75 | 14 | **−$529** | +$1,446 | +$997 | 64 % | +$1,306 |
| $1.00 | 19 | **−$529** | +$1,935 | +$1,486 | **100 %** | **−$1,174** |

**All four REJECT on the Tuesday hard gate.** Three specific kills:

- **The tight cells block Tuesday's best trade.** At X=$0.25 the rule blocks exactly two positions in 26 days, and one of them is risky-1's 09:50 C763 — **+$640**, the single largest vwap winner in the book. A rule whose *entire* footprint is "don't take the best trade of the week" is not a rule.
- **X=$1.00 blocks 100 % of Wednesday's positions.** Its +$1,935 is not a filter result, it is a **full-day standdown wearing a proximity costume** — including risky-1's +$347 put, the only trade of the day with a confirmed structure event in its direction. The number is real and the mechanism is a lie.
- **Population B refutes the family at the widest band.** The labelled proxy (levels conjunct dropped, since B has no levels log) is **−$1,173.80 with 30 days harmed** at X=$1.00. The looser bands are positive on B but harm 14–23 days each.

Coverage limit as pre-registered: `levels_active` is only logged from **2026-07-28**, so **149 of 208 positions ABSTAIN**. No C7 cell could have reached SHIP even had it passed.

**This is the seventh consecutive rejection of a level-proximity entry gate** (V-b1/b2/b3 × engine/proxy in the parent study, plus all four cells here). The prior was bad and the prior held.

---

## 6. Hard gate audit — Tuesday, per cell

Tuesday's money is genuinely in the repeat entries: **2nd-and-later positions on a contract contributed +$1,437 of Tuesday's +$3,624**, and the +$524 rescue is a 3rd. Cells that clip them are rejected outright.

| Cell | Tue delta | G1 |
|---|---:|---|
| CAP-3, CAP-4, CAP-5 | $0.00 | **PASS** |
| SAME-BAR cooldown | +$144 | **PASS** |
| V-d1 | +$179 | **PASS** |
| CAP-2 | −$524 | FAIL |
| CAP-1 | −$2,197 | FAIL |
| DAY-CAP 3/4/5/6 | −$2,003 / −$1,211 / −$631 / −$678 | FAIL |
| once/day scoped | −$900 | FAIL |
| once/day all setups | −$2,527 | FAIL |
| session-high ×4 | −$600 … −$529 | FAIL |
| time cooldown ×4 | −$1,133 … −$465 | FAIL |

---

## 7. Graveyard check

Run before any verdict. The per-setup **TIME cooldown** family was measured only as the pre-declared contrast and is stamped `GRAVEYARD_COLLISION` in every cell — note the 30-minute cell shows +$1,417 book and Wed +$1,058 but **still loses −$514 on Tuesday**, exactly consistent with the standing "Tue every cell lost" verdict. No other cell collides: this lane touches no stop width, no stopped-then-paid, no profit-lock arm scope, no hold-longer, no take-profit-earlier, no level-target exit, no regime standdown, no min-contracts knob, no late-day or open standdown.

**One collision worth naming out loud:** session-high X=$1.00 is functionally an **open-window standdown**, which LANE 0 already refuted on 391 days (09:30 is the single most profitable entry bucket, +$63.90/entry). Its Wednesday number should not be quoted as a filter result.

---

## Caveats

1. **CAP-3's evidence bar is not met and this document does not claim it is.** 90.7 % of its benefit is the motivating day; ex-08-05 it is +$67 across 7 waves; BH q = 0.796; Population B structurally cannot test it. It clears a **does-no-harm** bar only.
2. **The SAME-BAR cooldown is POST-HOC.** It was written after the pre-registered C3 failed. Its verdict is capped at PREREG by construction. It needs its own forward pre-registration before it is armed.
3. **26 live days, 208 positions, five correlated arms.** LANE 0 measured mean pairwise arm daily-P&L r = 0.787, so the effective independent sample is far smaller than n=208 suggests. Every permutation p in this document is computed on positions treated as exchangeable *within a day*, which is the honest correction available, not a complete one.
4. **The counterfactual is deletion, nothing more.** A blocked position contributes $0. No exit is re-walked, no fill is re-priced, no freed capital is redeployed. Blocking entry k does not change entry k+1's fill. All deltas are therefore silent about the trade that would have happened instead.
5. **Setup attribution is a join, not a ledger field.** 33 of 208 positions (all core-lane extra-setups on older dates) carry no recoverable setup label and **ABSTAIN** from C3/C3b/C4/C5 rather than being blocked on a guess. The vwap_continuation family itself is pinned by symbol+minute in the verifier so the headline does not depend on the join.
6. **Population B is one arm at qty 3, one strategy family.** It validates mechanisms, never fleet thresholds, and it structurally cannot produce a Wednesday.
7. **C7's `levels_active` coverage is 8 of 26 dates.** The Population-B row for C7 is a strictly looser **PROXY** with the levels conjunct dropped — it can refute the family, never validate the rule.
8. **The brief's phrase "the 25-day book" is 26 ET dates** once today is included; the "391-day" population's own metadata says 387 calendar RTH days / 191 trades. Reported as measured.
9. **Tuesday/Wednesday/Thursday totals here are SPY-options-only** (+$3,624.00 / −$1,935.00 / +$1,465.00) versus the brief's all-in figures (+$3,617.19 / −$1,943.66 / +$1,460.80). Both are correct; different scopes.
10. **Nothing was armed.** No `params.json` key, no engine file, no scheduled task was touched. This lane produced measurements and two frozen candidates.

---

## Artifacts

- `analysis/recommendations/lever-entry-count-prereg-2026-08-06.json` (frozen prereg, commit **bf8dec8d**)
- `analysis/deep-research/LEVER-ENTRY-COUNT-2026-08-06.md` (this file)
- `analysis/deep-research/LEVER-ENTRY-COUNT-2026-08-06.json` (all cells, all fields, blocked-position detail)
- `backtest/tools/lever_entry_count_2026_08_06.py` (runner)
- `backtest/tools/lever_entry_count_verify_2026_08_06.py` (independent verifier, 76/76 PASS)
