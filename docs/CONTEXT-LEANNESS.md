# Context-Leanness Loop — full spec

> Shipped 2026-06-16. Keeps `CLAUDE.md` (the always-loaded prefix) under a hard
> token budget so cache-read cost stays low. Canonical reference; CLAUDE.md and
> the `context-leanness` skill point here.

## Why this exists

Every token in `CLAUDE.md` is cache-written then **cache-read on EVERY Claude
Code turn**. Token forensics (`analysis/token-forensics/`) showed cache reads
dominate the bill (billions of tokens over days), so the always-loaded prefix is
the single most-multiplied cost lever in the system. On 2026-06-16 CLAUDE.md was
trimmed 17,813 -> ~7.4K tokens by moving reference-only blocks to `docs/`; this
loop keeps it lean automatically so it cannot silently re-bloat.

## Benchmarks / guard scores

Single source of truth: `setup/scripts/context_audit.py`.

| Score | Tokens (budget 8000) | Meaning | Action |
|---|---|---|---|
| GREEN | < 7600 (<95%) | lean | none |
| YELLOW | 7600-8000 (95-100%) | near ceiling | trim at next after-4pm block (nag only) |
| RED | > 8000 (>100%) | over budget | auto-trim after hours; manual any time |

Token method: `tiktoken cl100k_base` if importable, else `bytes/3.6` estimate.
Status keys off token thresholds, not rounded percent.

## File map

| File | Role |
|---|---|
| `setup/scripts/context_audit.py` | Engine. `report` / `check` (writes state, fails open) / `verify` (integrity gate). Owns budget + thresholds + invariants. |
| `setup/scripts/check-context-budget.ps1` | Guard. Scores + alerts always; `-AutoFix` trips Claude on RED via `Invoke-ClaudeWithRetry`, gated by `Test-MarketHours` + rate-limit cooldown. Fails open. |
| `.claude/skills/context-leanness/SKILL.md` | The skill Claude runs to trim: measure -> back up -> relocate -> dedupe -> verify -> log. |
| `automation/prompts/context-leanness-autofix.md` | Prompt the guard hands Claude on a RED auto-trip. |
| `setup/scripts/register-context-guard.ps1` | One-time registration of `Gamma_ContextGuard` (16:10 ET daily). |
| `automation/state/context-budget.json` | Latest score/state. Read by the session-start digest. |
| `setup/scripts/session-start-digest.ps1` | Emits a `Context budget:` line every wake (in-context alert). |
| `docs/LESSONS-CHRONOLOGICAL-LOG.md`, `docs/KITCHEN-SPEC.md` | Reference blocks relocated out of CLAUDE.md (verbatim). |
| `docs/archive/CLAUDE-md-pre-trim-2026-06-16.md` | Verbatim backup of the pre-trim soul file. |

## The closed loop

```
session-start digest --shows--> "Context budget: GREEN (7372/8000 tok)"  <- every wake
        ^
Gamma_ContextGuard (16:10 ET) --> check-context-budget.ps1 -AutoFix
        |                                 |
        |               context_audit.py check -> context-budget.json
        |                                 |
        |                 RED + after-hours + not rate-limited?
        |                                 | yes
        +------- Invoke-ClaudeWithRetry --+  (harness: lock/disk/retry/hidden)
                                |
            Claude loads SKILL.md -> measure > back up > relocate to docs/ >
            dedupe > VERIFY > log > re-check -> GREEN
```

## HARD safety boundary (also enforced by the skill)

- NEVER change rule semantics, account numbers/params, kill-switch %, the
  `Current rule version` pin, or the refusals. Structural edits only.
- NEVER edit during market hours (09:30-15:55 ET). The guard's auto-trip is
  blocked in that window (Rule 9). Manual runs must defer too.
- ALWAYS back up first; if `context_audit.py verify` fails after an edit,
  RESTORE the backup and abort (flag in STATUS.md). A failed trim is a no-op.
- This is the interactive/after-hours Claude only. The Kitchen daemon's OP-31
  guardrail (never touch CLAUDE.md) is unchanged.

## Operate it

```bash
# See where the tokens are + relocation candidates
python setup/scripts/context_audit.py report

# Score + refresh state json (what the digest reads)
python setup/scripts/context_audit.py check

# Integrity gate (run AFTER any edit; exit 1 on any failure)
python setup/scripts/context_audit.py verify
```

Manual guard run (PowerShell): `powershell -File setup\scripts\check-context-budget.ps1`
Add `-AutoFix` to let it self-heal on RED (after hours only).

## Activate the autonomous daily guard (run once on Windows)

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\jackw\Desktop\42\setup\scripts\register-context-guard.ps1"
```

After registering, move `Gamma_ContextGuard` from "## Proposed" to "## Active" in
`automation/state/SCHEDULED-TASKS.md` and bump the count (governance: the audit
flags Active-but-unregistered as STALE_REGISTRY_ENTRY).
