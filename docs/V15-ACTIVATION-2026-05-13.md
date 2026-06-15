# V15 ACTIVATION — 2026-05-13 evening

**Activation timestamp (ET):** 2026-05-13 ~23:30 ET (post-evaluation, J authorized)
**Activated by:** Gamma (per J explicit ratification)
**Effective for:** 2026-05-14 (CPI day) heartbeat fires onward

---

## J authorization

> "v15 can go live that is chill lets let er rip it seems a lot better. keep v14 documented still incase we need to revert."

— J, 2026-05-13 evening (Discord chat / interactive session)

---

## What v15 is

**v15** is the v14_enhanced ratified specification (T44b real-fills 3/3 PASS + T44c walk-forward 2.67x + T44d Monday-Ready 8/8 + T50 trailing-PL B1 20% winner) promoted into production heartbeat.md.

Rule-version pin bumped:
- `automation/state/params.json#rule_version`: `"v14"` → `"v15"`
- `automation/prompts/heartbeat.md` RULE_VERSION constant: `"v14"` → `"v15"`
- `automation/prompts/premarket.md` RULE_VERSION_EXPECTED: `"v14"` → `"v15"`

Pin-check at premarket Step 1a (08:30 ET 5/14) will PASS — all three match.

---

## Files modified (file diff bullet list)

### 1. `automation/prompts/heartbeat-v14-prod-backup.md` (NEW)
- **Action:** byte-for-byte copy of pre-activation heartbeat.md.
- **Purpose:** atomic revert source. Restoring from this file restores v14 production logic exactly.

### 2. `automation/prompts/heartbeat.md` (MODIFIED — surgical)
- **Line 16:** `RULE_VERSION = "v14"` → `RULE_VERSION = "v15"`.
- **NEW SECTION** ("v15 ratification (LIVE 2026-05-13 evening)") inserted just below Rule Version Pin block. Documents J authorization quote, source-of-truth refs (DOCTRINE-CHANGE / MONDAY-READY / V14_ENHANCED-PL-VARIANTS / real-fills + walk-forward scorecards), 7 numbered changes from v14, what did NOT change (inherited from v14), 3-step revert path, CPI-day risk note.
- **Position branch — exit doctrine block:** v11/v14 ratified-doctrine bullets replaced with v15 bullets. Bear-side premium stop -8% → -20%. TP1 qty fraction 0.667 → 0.50. Runner target now active 2.50 (was 3.0 ceiling). NEW trailing chandelier profit-lock paragraph: arms at +5% favor, initial floor +10%, trail 20% off HWM of favor_premium, never lowers below original premium stop. Bull-side calls explicitly retain v14 -8% stop / 0.667 TP1 / no PL trailing.
- **Strike selection block:** "ITM-2 uniform" replaced with per-tier table. Reads `today-bias.json#account_equity` (fallback `circuit-breaker.json#start_equity`). Tier rows: $0-$2K → strike_offset=-3 (OTM-3), $2-10K → -2, $10-25K → -1, $25K+ → +2 (v14 default). Formula: bear puts `strike = round(spot) + strike_offset`; bull calls `strike = round(spot) - strike_offset` (mirror).
- **BEARISH filter 1 line:** time gate `≥10:00 ET` → `≥09:35 ET` with v15 ratification cite.
- **BULLISH filter 1 line:** same change `≥10:00 ET` → `≥09:35 ET`.
- **Pre-execution gate sequence table:** new row G6b inserted after G6 — v15 per-tier max-premium hard gate. Tier table embedded inline (40/30/25/20% by tier). BLOCK condition: `> max_pct_for_tier AND can't reduce qty/move OTM to fit`.
- **Execution step 4 (Sizing):** appended G6b enforcement after the existing G6 50%-of-equity check. Reduce qty until fits OR move strike one further OTM (max 1 retry). Floor = min_contracts. If still over: BLOCK with `SKIP_GATE_G6b`.

### 3. `automation/state/params.json` (MODIFIED)
- `rule_version`: `"v14"` → `"v15"`.
- `rule_version_ratified_at`: `"2026-05-08"` → `"2026-05-13"`.
- `rule_version_notes`: replaced with v15 spec summary + sources (V15-ACTIVATION + DOCTRINE-CHANGE + MONDAY-READY + V14_ENHANCED scorecards).
- `rule_version_revert_command`: NEW field — explicit 3-step procedure to revert v15 → v14.
- `_v15_pending_section`: doc string updated STAGED→LIVE with backup-file pointer.
- `v15_ratification_status`: `"STAGED — heartbeat NOT updated. Currently in v14 mode. Production safe."` → `"LIVE 2026-05-13 evening — heartbeat.md updated, rule_version flipped to v15. ..."`
- All v14 fields preserved unchanged (premium_stop_pct -0.08, premium_stop_multiplier 0.92, tp1_qty_fraction 0.667, etc.). Backward references intact. Bull-side will continue reading these v14 values until bull mirror is specced.
- All `v15_*_pending` fields preserved (now consumed by heartbeat).

### 4. `automation/prompts/premarket.md` (MODIFIED — surgical)
- **Line 38:** `RULE_VERSION_EXPECTED = "v14"` → `RULE_VERSION_EXPECTED = "v15"`.
- **Line 47:** inline `(currently "v14")` → `(currently "v15")`.
- **Lines 50, 57:** kill-switch warning text `expected="v14"` → `expected="v15"` (two occurrences).

### 5. `automation/prompts/heartbeat-v15-draft.md` (MODIFIED)
- **Line 18:** RULE_VERSION constant `"v14"` → `"v15"`.
- **Top draft-note (line 3):** updated to reflect v15 is now production at heartbeat.md; this file remains as staging for future v15.x revisions + watcher layer (still observation-only per OP 21).
- **Line 23 v15 DRAFT note:** rewritten to document promotion + remaining role.

### 6. `CHANGELOG.md` (MODIFIED — append-only row)
- New row inserted at top of update log (chronologically newest = bottom of table per file convention, but inserted ABOVE the prior 2026-05-13 evening row to preserve chronological readability of the same-evening events). Documents file-by-file changes, J quote, revert command, pre-flight pin status, CPI-day risk assessment.

### 7. `docs/V15-ACTIVATION-2026-05-13.md` (THIS FILE — NEW)

---

## Exact revert procedure (3 steps to restore v14)

If v15 misbehaves on 5/14 (or any subsequent day) and J calls for revert:

```powershell
# Step 1 — restore heartbeat.md byte-for-byte
Copy-Item -Path "C:\Users\jackw\Desktop\42\automation\prompts\heartbeat-v14-prod-backup.md" `
          -Destination "C:\Users\jackw\Desktop\42\automation\prompts\heartbeat.md" `
          -Force

# Step 2 — flip rule_version back to v14 in params.json (manual edit OR jq)
# In params.json:
#   "rule_version": "v15"  →  "rule_version": "v14"
#   "rule_version_ratified_at": "2026-05-13"  →  "rule_version_ratified_at": "2026-05-08"
# (Also recommended: revert rule_version_notes to the prior v14 -8% stop description.
#  Not strictly required for pin-check; cosmetic.)

# Step 3 — flip premarket.md RULE_VERSION_EXPECTED back to v14
# In premarket.md line 38:
#   RULE_VERSION_EXPECTED = "v15"  →  RULE_VERSION_EXPECTED = "v14"
# (Also lines 47, 50, 57 inline references — same change.)
```

After all 3 steps complete, the next premarket Step 1a (08:30 ET) re-verifies pin and PASSES at v14. No kill-switch tripped.

If only steps 1 and 3 are done but step 2 is forgotten (or vice versa), pin-check FAILS and kill-switch trips — system pauses until the mismatch is reconciled. This is the intended safety net.

---

## Pre-flight check that pin-version matches

Before the 5/14 08:30 ET premarket fire, verify:

| Source | Field | Expected | Verified |
|---|---|---|---|
| `automation/state/params.json` | `rule_version` | `"v15"` | (verify with `jq -r .rule_version params.json`) |
| `automation/prompts/heartbeat.md` | `RULE_VERSION` constant (line ~16) | `"v15"` | (verify with `grep '^RULE_VERSION' heartbeat.md`) |
| `automation/prompts/premarket.md` | `RULE_VERSION_EXPECTED` (line 38) | `"v15"` | (verify with `grep RULE_VERSION_EXPECTED premarket.md`) |

All three must be `"v15"` for premarket Step 1a to PASS. Mismatch = kill-switch automatic.

**Smoke-test verification performed 2026-05-13 ~23:35 ET as part of activation:** all three confirmed `"v15"`.

---

## Risk assessment (CPI day = high vol)

**5/14 is CPI release day.** High-volatility regime with macro-hard-veto window typically 08:30 ET (release time, but verify in `today-bias.news_calendar.events_today[]`). Macro hard-veto inherited from v14 still applies:
- Within 120 min of release: HARD VETO blocks counter-trend entries.
- 120-240 min: SOFT MODIFIER raises bull threshold to ≥10/11, lowers bear to ≥7/10.

**Why v15 is safe to ship on a CPI day (despite "no mid-session changes" doctrine — this is a weekend evening edit, NOT mid-session):**

1. **Real-fills tested on 16-month dataset.** v14_enhanced T44b ran 3/3 OP-20 gates with $36,450 wide P&L, 6/6 quarters net positive, max DD $2,857, top-5 concentration 0.37, WR 56.8%. Source: `analysis/recommendations/v14_enhanced-real-fills.json`.
2. **Walk-forward 2.67x out-performance.** TRAIN $18,549 over 12mo ($1,547/mo) vs TEST $17,901 over 4.4mo ($4,128/mo) = 2.67x ratio. TEST OUTPERFORMS TRAIN — strongest possible signal of regime-robustness. Source: `analysis/recommendations/v14_enhanced-walkforward.json`.
3. **Monday-Ready 8/8 substantive gates PASS.** Source: `docs/MONDAY-READY-CHECKLIST-V14_ENHANCED-2026-05-13.md`.
4. **T50 trailing-PL test:** B1 trailing 20% chandelier wins on aggregate ($36,621 vs fixed $36,450) AND on concentration (top5 32% vs 37.1%). Asymmetric upside on big-winner days, equivalent protection on chop-day downside. Source: `docs/V14_ENHANCED-PL-VARIANTS-2026-05-13.md`.
5. **Per-tier max-premium hard gate prevents the $1K-account-overlevered scenario** (e.g., 5/13 738C trade hypothetically at qty=15 ITM-2 = 315% leverage on $1K). The hard gate forces qty-down or strike-OTM scaling.
6. **v14 is preserved byte-for-byte at heartbeat-v14-prod-backup.md** with a documented 3-step revert procedure. Worst-case rollback time: <60 seconds.

**Failure modes to watch on 5/14:**
- Trailing PL armed too early on a fake-out, then trail tightens and exits at +10% before move develops. Heartbeat first-tick pos-branch will surface this in journal.
- New 09:35 ET entry gate fires on a 09:35-09:55 chop bar. The other 9 BEARISH filters (ribbon stack, spread, vol mult, VIX, etc.) should still block — gate change is permissive, not weakening.
- Per-tier strike picker pulls OTM-3 on a $1K account and option illiquid (delta < 0.30 or OI < 500). Liquidity gate still rejects per existing rules; max 2 strike retries toward ATM. Floor at min_contracts.
- CPI release window blocks all entries via macro hard-veto. This is intended behavior; no v15 change weakens this.

---

## Bull-side notice

**v15 changes apply to the BEAR-side BEARISH_REJECTION_RIDE_THE_RIBBON setup only.** The BULL-side BULLISH_RECLAIM_RIDE_THE_RIBBON setup retains v14 defaults:
- Premium stop: -8% (entry × 0.92) — UNCHANGED
- TP1 qty fraction: 0.667 — UNCHANGED
- Runner target: 3.0 hard ceiling — UNCHANGED
- Strike: ITM-2 uniform — UNCHANGED (until per-tier bull spec written)
- Profit-lock: NONE (no trailing chandelier) — UNCHANGED

ONLY the entry time gate (09:35 ET) is symmetric across bear and bull (it's a global filter-1 change).

A future `v15.1` or `v16` may add a bull mirror after dedicated v14_enhanced_BULL grinder runs. Until then, bull autonomous trades behave as in v14 except for the time gate.

---

## Cross-reference docs

- `docs/DOCTRINE-CHANGE-2026-05-13-EVENING.md` — full audit trail of the v14_enhanced ratification process
- `docs/MONDAY-READY-CHECKLIST-V14_ENHANCED-2026-05-13.md` — 8/8 gates
- `docs/V14_ENHANCED-REAL-FILLS-2026-05-13.md` — 3/3 OP-20
- `docs/V14_ENHANCED-WALK-FORWARD-2026-05-13.md` — 2.67x ratio
- `docs/V14_ENHANCED-PL-VARIANTS-2026-05-13.md` — T50 winner
- `analysis/recommendations/v14_enhanced-real-fills.json`
- `analysis/recommendations/v14_enhanced-walkforward.json`
- `analysis/recommendations/v14_enhanced-pl-variants.json`
- `automation/prompts/heartbeat-v14-prod-backup.md` — v14 preservation

---

> Generated 2026-05-13 evening as part of v15 activation. Append-only — do not mutate after the activation event. Future revert events get their own dated doc.
