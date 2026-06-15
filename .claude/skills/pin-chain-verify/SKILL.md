# Skill: pin-chain-verify

Verify the rule_version pin chain matches across `params.json` + `heartbeat.md` + `premarket.md`. AUDIT, DIAGNOSE, REPORT proposed-fix-diff if mismatched. NO auto-edit (rule 9 — production prompt changes require J authorization).

> Per CLAUDE.md OP-4 (no code drift) + rule 9 (no mid-session rule changes). Premarket Step 1a kill-switches the day on pin mismatch. This skill catches drift BEFORE premarket detects it, and surfaces a precise fix-diff for J to authorize.

---

## When to invoke

- **Daily, automatically** — every overnight wake fire as part of Stage 0 self-test
- **After ANY rule_version bump** to verify all three pins moved together
- **When premarket Step 1a fires `RULE_VERSION_DRIFT` warning** — confirms which file is wrong
- **After a `git pull` or branch switch** that may have brought in mismatched files
- **Before ratifying a v## scorecard** to ensure backtest doctrine == production doctrine (OP-4)

---

## Steps

1. **Run the verification:**

```powershell
cd C:\Users\jackw\Desktop\42\backtest
python -m autoresearch.pin_chain_verify
```

2. **Read structured JSON:**

```powershell
Get-Content "C:\Users\jackw\Desktop\42\automation\state\pin-chain-verify-latest.json"
```

3. **If RED, give the proposed fix diff to J for authorization:**

```
The output's `proposed_fix_diff` array contains, per file:
  - file path
  - current value
  - proposed value (matches canonical)
  - manual_command (a one-liner J can paste — but DO NOT run automatically)
  - warning: NEVER auto-run; rule 9 forbids mid-session production-prompt edits
```

---

## Verdict criteria

| Verdict | Trigger |
|---------|---------|
| **GREEN** | `params.json#rule_version` == `heartbeat.md` RULE_VERSION == `premarket.md` RULE_VERSION_EXPECTED |
| **RED** | Any of the three pins diverge from `params.json` |
| **(no YELLOW)** | Pin chain has no in-between state — match or don't |

---

## Healing actions

| Condition | Action |
|-----------|--------|
| RED (any mismatch) | **NO auto-heal.** Outputs `proposed_fix_diff` with the exact line + value to change. J authorizes manually. The skill's manual_command is a one-liner; J can paste & run after review. |

**Rationale (rule 9 — sacred):** Production prompts (`heartbeat.md`, `premarket.md`) drive live trading decisions. Auto-edits during market hours violate the no-mid-session-changes rule. Even outside market hours, prompt edits should be reviewed by J + propagate through CHANGELOG.md. This skill makes the fix surgical (exact line + value) but never applies it.

**Aggressive variant note:** `automation/prompts/aggressive/heartbeat.md` may legitimately diverge if J runs aggressive on a different rule_version. The tool flags but tags `note: aggressive-variant-may-be-intentionally-divergent-confirm-with-J`.

**Drafts (`heartbeat-v15-draft.md`, `premarket-v15-draft.md`, `heartbeat-v14-prod-backup.md`)** are NOT in the pin chain — they're version-pinned by filename + content. The skill reports their versions for situational awareness but doesn't flag them as RED.

---

## Output files

| File | What |
|------|------|
| `automation/state/pin-chain-verify-latest.json` | Verdict + production pin chain + draft versions + mismatches + proposed fix diff |
| stdout | Human-readable per-source pin + verdict |

JSON schema:
```json
{
  "skill": "pin-chain-verify",
  "verdict": "GREEN|RED",
  "reason": "human description",
  "canonical_rule_version": "v15.1",
  "rule_version_ratified_at": "2026-05-14",
  "production_pin_chain": {
    "params.json":  {"version": "v15.1", "line": null},
    "heartbeat.md": {"version": "v15.1", "line": 16},
    "premarket.md": {"version": "v15.1", "line": 38},
    "aggressive/heartbeat.md": {"version": "v15.1", "line": 16}
  },
  "draft_versions": {
    "heartbeat-v15-draft.md": {"version": "v15", "line": 16}
  },
  "mismatches": [],
  "proposed_fix_diff": [],
  "heal_action": "no-op"
}
```

---

## Caveats

1. **The aggressive variant may legitimately differ.** Don't auto-fix without confirming with J.
2. **Drafts are advisory.** A `heartbeat-v15-draft.md` showing v15 while prod is v15.1 is correct — drafts get retired or merged after ratification.
3. **`params.json` is the canonical source.** If params.json is wrong, everything else cascades wrong. Fix params.json FIRST (manually, after J confirms), then re-run pin-chain-verify to validate the rest.
4. Exit codes: `0` for GREEN, `1` for RED.

---

## Cross-references

- **Tool source:** `backtest/autoresearch/pin_chain_verify.py`
- **Companion skill:** `gamma-sync` (full sync — code AND prompts; uses this verify after sync)
- **Production pin enforcement:** `automation/prompts/premarket.md` Step 1a (kills the day on drift)
- **CLAUDE.md operating principle:** OP-4 (no code drift), rule 9 (no mid-session changes)
- **Canonical config:** `automation/state/params.json` (with extensive header doc explaining the pin contract)
